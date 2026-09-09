# -*- coding: utf-8 -*-
"""KISA 4항목 실험 결과를 한 곳에 모은다.

문제: 결과가 results/par/RULE2_*.txt(새 규칙), EXP_*.txt(구 규칙), FALL_TRACK.txt,
     FIRE_KFOLD/RATIO/LOO.txt, results/_archive/*.txt, runs/*/results.csv 로 흩어져 있고
     침입·배회 규칙 스윕은 로컬 콘솔에만 있어서 비교가 안 된다.
해결: 전부 훑어 하나의 표로 만든다. 재실행하면 갱신된다(실험이 끝날 때마다 돌리면 됨).
출력: results/ALL_RESULTS.md (읽는 표) · results/ALL_RESULTS.json (기계용)
      로컬 결과는 results/local_results.json 에 넣어두면 합쳐진다.
"""
import csv
import json
import re
import subprocess
from datetime import datetime
from pathlib import Path

G = Path("/NHNHOME/WORKSPACE/26mss002_E3/vms")
R = G / "results"
PAR = R / "par"

# "88.89 (정검 8 미검 2 오검 0)  뒤에 설정" 형태
RE_SCORE = re.compile(r"([0-9]+\.[0-9]+)\s*\(정검\s*(\d+)\s*미검\s*(\d+)\s*오검\s*(\d+)\)\s*(.*)")
# "규칙이름  →  75.00  (정검 6 ...)" 형태
RE_ARROW = re.compile(r"(.*?)→\s*([0-9]+\.[0-9]+)\s*\(정검\s*(\d+)\s*미검\s*(\d+)\s*오검\s*(\d+)\)")
ANSI = re.compile(r"\x1b\[[0-9;]*[mK]")


def clean(t):
    return ANSI.sub("", t)


def best_of(path, arrow=False):
    """파일에서 가장 높은 F1 한 줄을 뽑는다."""
    try:
        txt = clean(Path(path).read_text(encoding="utf-8", errors="ignore"))
    except Exception:
        return None
    best = None
    for ln in txt.splitlines():
        m = RE_ARROW.search(ln) if arrow else RE_SCORE.search(ln)
        if not m:
            continue
        if arrow:
            rule, f1, tp, fn, fp = m.group(1).strip(), float(m.group(2)), *map(int, m.groups()[2:5])
        else:
            f1, tp, fn, fp, rule = float(m.group(1)), *map(int, m.groups()[1:4]), m.group(5).strip()
        if best is None or f1 > best["f1"]:
            best = {"f1": f1, "tp": tp, "fn": fn, "fp": fp, "rule": rule}
    return best


def train_info(name):
    """학습 규모·에폭·검증 mAP50 (있으면)"""
    out = {}
    ds = G / f"data/학습데이터/_par/{name}/train.txt"
    if ds.exists():
        out["학습장수"] = sum(1 for _ in open(ds))
    for base in (G / "runs/par", G / "runs"):
        csvf = base / name / "yolo11s/results.csv"
        if csvf.exists():
            rows = list(csv.DictReader(open(csvf)))
            if rows:
                out["에폭"] = len(rows)
                for k in rows[-1]:
                    if "mAP50(B)" in k and "95" not in k:
                        try:
                            out["mAP50"] = round(float(rows[-1][k]), 4)
                        except Exception:
                            pass
            break
    return out


def item_of(name):
    """파일·실험 이름으로 4항목 중 어디에 속하는지 판별"""
    u = name.upper()
    if "FALL" in u or "POSEC3D" in u:
        return "쓰러짐"
    if "LOITER" in u or "배회" in u:
        return "배회"
    if "INTRU" in u or "PERSON_V" in u or "침입" in u:
        return "침입"
    return "방화"


def split_multi(f):
    """RULE2_ALL.txt 처럼 '########## 이름' 으로 여러 실험이 한 파일에 있는 경우 쪼갠다."""
    txt = clean(Path(f).read_text(encoding="utf-8", errors="ignore"))
    if "##########" not in txt:
        return None
    out = {}
    cur = None
    for ln in txt.splitlines():
        if ln.startswith("##########"):
            cur = ln.replace("#", "").strip()
            out[cur] = []
        elif cur:
            out[cur].append(ln)
    res = {}
    for k, lines in out.items():
        best = None
        for ln in lines:
            m = RE_SCORE.search(ln)
            if m:
                f1 = float(m.group(1))
                if best is None or f1 > best["f1"]:
                    best = {"f1": f1, "tp": int(m.group(2)), "fn": int(m.group(3)),
                            "fp": int(m.group(4)), "rule": m.group(5).strip()}
        if best:
            res[k] = best
    return res


def collect():
    data = {"생성": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "항목": {"방화": [], "침입": [], "배회": [], "쓰러짐": []}}
    seen = set()

    def add(item, rec):
        key = (item, rec["실험"], rec["채점"], rec["f1"])
        if key in seen:
            return
        seen.add(key)
        data["항목"].setdefault(item, []).append(rec)

    # 새 규칙 채점 (방화)
    for f in sorted(PAR.glob("RULE2_*.txt")):
        name = f.stem.replace("RULE2_", "")
        multi = split_multi(f)
        if multi:                                   # RULE2_ALL.txt = 여러 모델 묶음
            for k, b in multi.items():
                add("방화", {"실험": k, "채점": "새 규칙", **b, **train_info(k)})
            continue
        b = best_of(f)
        if b:
            add("방화", {"실험": name, "채점": "새 규칙", **b, **train_info(name)})

    # 구 규칙 채점
    for f in sorted(PAR.glob("EXP_*.txt")):
        name = f.stem.replace("EXP_", "")
        b = best_of(f, arrow=True)
        if b:
            add(item_of(name), {"실험": name, "채점": "구 규칙", **b, **train_info(name)})

    # 보관 결과 (중복 없이 한 번만)
    for f in sorted(set(R.glob("_archive/*.txt"))):
        b = best_of(f, arrow=True) or best_of(f)
        if b:
            add(item_of(f.stem), {"실험": f.stem, "채점": "구 규칙(보관)", **b})

    # 쓰러짐 스펙 규칙
    b = best_of(PAR / "FALL_TRACK.txt")
    if b:
        add("쓰러짐", {"실험": "fall_track (트랙별 독립판정)", "채점": "스펙 규칙", **b})

    # ---------- 드라이버(부가 실험) ----------
    extra = {}
    for nm, f in (("K-fold(손라벨)", PAR / "FIRE_KFOLD.txt"),
                  ("24k 비율 스윕", PAR / "FIRE_RATIO.txt"),
                  ("장소 홀드아웃", PAR / "FIRE_LOO.txt"),
                  ("FASDD 5-fold", PAR / "KFOLD_FASDD.txt")):
        if f.exists():
            t = clean(f.read_text(encoding="utf-8", errors="ignore"))
            keep = [l.rstrip() for l in t.splitlines()
                    if ("정검" in l or "→" in l or "fold" in l or "평균" in l or "표준편차" in l)
                    and "Ultralytics" not in l]
            if keep:
                extra[nm] = keep[-25:]
    data["부가실험"] = extra

    # ---------- 로컬 결과 병합 (침입·배회 등) ----------
    lf = R / "local_results.json"
    if lf.exists():
        loc = json.load(open(lf, encoding="utf-8"))
        for item, rows in loc.items():
            for r in rows:
                add(item, {"채점": "스펙 규칙", **r})

    return data


def render(d):
    L = [f"# KISA 4항목 실험 결과 모음", "", f"갱신 {d['생성']}", "",
         "채점 = 배포용 표본 자체채점. 정검/미검/오검은 영상 수. 창 밖 알람은 오검+미검 이중 감점.", ""]

    # 항목별 최고
    L += ["## 항목별 현재 최고", "", "| 항목 | F1 | 정검/미검/오검 | 실험 | 규칙 |", "|---|---|---|---|---|"]
    for item, rows in d["항목"].items():
        if not rows:
            continue
        b = max(rows, key=lambda r: r["f1"])
        L.append(f"| {item} | **{b['f1']}** | {b['tp']}/{b['fn']}/{b['fp']} | {b['실험']} | {b.get('rule','')[:46]} |")
    L.append("")

    for item, rows in d["항목"].items():
        if not rows:
            continue
        L += [f"## {item} ({len(rows)}건)", ""]
        cols = ["실험", "F1", "정검", "미검", "오검", "규칙", "채점", "학습장수", "에폭", "mAP50"]
        L.append("| " + " | ".join(cols) + " |")
        L.append("|" + "---|" * len(cols))
        for r in sorted(rows, key=lambda x: -x["f1"]):
            L.append("| " + " | ".join([
                str(r.get("실험", "")), f"{r['f1']:.2f}", str(r["tp"]), str(r["fn"]), str(r["fp"]),
                str(r.get("rule", ""))[:44], str(r.get("채점", "")),
                str(r.get("학습장수", "")), str(r.get("에폭", "")), str(r.get("mAP50", ""))]) + " |")
        L.append("")

    if d.get("부가실험"):
        L += ["## 부가 실험", ""]
        for nm, lines in d["부가실험"].items():
            L += [f"### {nm}", "", "```"] + lines + ["```", ""]
    return "\n".join(L)


def main():
    d = collect()
    R.mkdir(parents=True, exist_ok=True)
    json.dump(d, open(R / "ALL_RESULTS.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    (R / "ALL_RESULTS.md").write_text(render(d), encoding="utf-8")
    n = sum(len(v) for v in d["항목"].values())
    print(f"결과 {n}건 수집 → {R/'ALL_RESULTS.md'}")
    for item, rows in d["항목"].items():
        if rows:
            b = max(rows, key=lambda r: r["f1"])
            print(f"  {item}: 최고 {b['f1']} ({b['실험']})")


if __name__ == "__main__":
    main()
