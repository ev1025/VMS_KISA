# -*- coding: utf-8 -*-
"""방화 확장 실험 매트릭스.
   축1: 24k 를 '장소 단위'로 분할(Leave-One-Location-Out) → 진짜 일반화 측정
   축2: 24k 혼합 비율 (0% · 10% · 25% · 50% · 100%)
   축3: 사람라벨 오버샘플 배수
   평가: (a) 홀드아웃 장소 mAP  (b) KISA 배포 10편 채점"""
import json, random, shutil, subprocess, sys
from collections import Counter, defaultdict
from pathlib import Path

W = Path("/NHNHOME/WORKSPACE/26mss002_E3"); G = W/"vms"
K24 = G/"data/학습데이터/dataset_24k"
HUMAN = G/"data/학습데이터/human_fire"
WORK = G/"data/학습데이터/mx2"; RUNS = G/"runs/mx2"
PY = str(W/"vms/.venv/bin/python")
WORK.mkdir(parents=True, exist_ok=True); RUNS.mkdir(parents=True, exist_ok=True)


def loc_of(stem):
    """24k 파일명 0001_SM_GAH_00001 → 장소코드 GAH"""
    p = stem.split("_")
    return p[2] if len(p) >= 3 else "UNK"


def k24_by_loc():
    d = defaultdict(list)
    for img in (K24/"images/train").glob("*.jpg"):
        lb = K24/"labels/train"/(img.stem+".txt")
        if lb.exists():
            d[loc_of(img.stem)].append((img, lb))
    return d


def human_pairs():
    out = []
    for img in sorted((HUMAN/"images/train").glob("*.jpg")):
        lb = HUMAN/"labels/train"/(img.stem+".txt")
        if lb.exists(): out.append((img, lb))
    return out


def make(name, k24_train, k24_val, human_train, over):
    """심링크 대신 이미지 목록 txt (중복 줄 = 오버샘플)"""
    ds = WORK/name
    if ds.exists(): shutil.rmtree(ds)
    ds.mkdir(parents=True, exist_ok=True)
    tr = [str(img) for img, lb in k24_train]
    for k in range(over): tr += [str(img) for img, lb in human_train]
    va = [str(img) for img, lb in k24_val]
    NL = chr(10)
    (ds/"train.txt").write_text(NL.join(tr)+NL); (ds/"val.txt").write_text(NL.join(va)+NL)
    (ds/"data.yaml").write_text(NL.join([f"path: {ds}", "train: train.txt", "val: val.txt", "nc: 2", "names: ['fire','smoke']"])+NL)
    return ds, len(tr), len(va)


def train_and_score(ds, name, epochs=50, imgsz=640):
    subprocess.run([PY, "model.py", "train", "--models", "yolo11s", "--data", str(ds/"data.yaml"),
                    "--project", str(RUNS), "--device", "0", "--batch", "64",
                    "--epochs", str(epochs), "--imgsz", str(imgsz), "--extra", "multi_scale=0.5",
                    "--no-export", "--force", "--cache", "ram", "--workers", "8"], cwd=str(W/"vms"), capture_output=True)
    src = RUNS/"yolo11s"
    if not src.exists(): return None, "학습실패"
    dst = RUNS/name
    if dst.exists(): shutil.rmtree(dst)
    src.rename(dst)
    # KISA 배포 채점 (타일)
    r = subprocess.run([PY, str(W/"vms/score_kisa.py"), str(dst/"weights/best.pt"),
                        "--videos", str(W/"vms/data/원본데이터/kisa_배포_방화채점셋/videos"), "--gt", str(W/"vms/data/원본데이터/kisa_배포_방화채점셋/gt"),
                        "--stride", "0.5", "--imgsz", str(imgsz), "--tiles", "--tag", name],
                       capture_output=True, text=True)
    line = ""
    for l in r.stdout.splitlines():
        if "fire만" in l: line = l.strip()
    return dst, line


def main():
    which = sys.argv[1] if len(sys.argv) > 1 else "loo"
    byloc = k24_by_loc(); hp = human_pairs()
    locs = sorted(byloc)
    print("24k 장소:", {k: len(v) for k, v in sorted(byloc.items())}, flush=True)
    print("사람라벨 프레임:", len(hp), flush=True)

    if which == "loo":
        # 장소 하나를 통째로 홀드아웃 (Leave-One-Location-Out)
        for held in locs:
            tr = [p for L in locs if L != held for p in byloc[L]]
            va = byloc[held]
            for over, tag in ((0, "k24only"), (5, "k24+human")):
                ds, n, m = make(f"loo_{held}_{tag}", tr, va, hp if over else [], max(over, 0))
                rd, res = train_and_score(ds, f"loo_{held}_{tag}")
                print(f"  홀드아웃 {held} · {tag}: train {n} val {m} → {res}", flush=True)

    elif which == "ratio":
        # 24k 비율 스윕 (사람라벨 고정)
        random.seed(0)
        allk = [p for L in locs for p in byloc[L]]
        random.shuffle(allk)
        va = allk[:1500]; pool = allk[1500:]
        for pct in (0, 10, 25, 50, 100):
            sub = pool[:int(len(pool)*pct/100)]
            ds, n, m = make(f"ratio_{pct}", sub, va, hp, 5)
            rd, res = train_and_score(ds, f"ratio_{pct}")
            print(f"  24k {pct}% (train {n}) → {res}", flush=True)


if __name__ == "__main__":
    main()
