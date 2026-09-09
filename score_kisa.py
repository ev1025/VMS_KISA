# -*- coding: utf-8 -*-
"""자립형 KISA 방화 채점기 (서버용, VMS 앱 의존 없음. ultralytics + opencv 만).

model(.pt) 하나를 방화 10편에 돌려, 우리가 쓰는 판정 규칙 몇 개로 F1 을 낸다.
규칙: onset = 창(window)에서 hits 번 conf 임계 넘은 순간의 첫 hit 시각.
     SA StartTime = onset + 10초. 정상검출 = GT-2s ~ GT+10s 안.
"""
import argparse, sys, xml.etree.ElementTree as ET
from collections import deque
from pathlib import Path
import cv2
from ultralytics import YOLO, RTDETR

DELAY, BEFORE, AFTER, DESC = 10.0, 2.0, 10.0, "FireDetection"
NAMES = {0: "fire", 1: "smoke"}

def hms_to_s(t):
    h, m, s = (t or "0:0:0").split(":"); return int(h)*3600 + int(m)*60 + int(s)

def gt_start(xml):
    r = ET.parse(xml).getroot()
    al = r.find(".//Alarm")
    return hms_to_s(al.findtext("StartTime")) if al is not None else None

IMGSZ = 640
def dump(model, mp4, stride, tiles):
    cap = cv2.VideoCapture(str(mp4)); fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    step = max(1, round(fps*stride)); i = 0; rows = []
    while True:
        if not cap.grab(): break
        if i % step == 0:
            ok, fr = cap.retrieve()
            if ok:
                best = {"fire": 0.0, "smoke": 0.0}
                crops = [fr]
                if tiles:
                    h, w = fr.shape[:2]
                    crops += [fr[y:y+h//2, x:x+w//2] for x, y in
                              ((0,0),(w//2,0),(0,h//2),(w//2,h//2),(w//4,h//4))]
                for c in crops:
                    r = model.predict(c, conf=0.05, verbose=False, imgsz=IMGSZ)[0]
                    for b in r.boxes:
                        cls = NAMES.get(int(b.cls), "?"); cf = float(b.conf)
                        if cls in best: best[cls] = max(best[cls], cf)
                rows.append((round(i/fps, 2), best))
        i += 1
    cap.release(); return rows

def onset(rows, rule):
    win = deque(maxlen=rule["window"])
    for t, best in rows:
        if rule["kind"] == "fire_only":
            hit = best["fire"] >= rule["fire"]
        elif rule["kind"] == "combined":       # fire 단독 OR (fire+smoke 동반)
            hit = best["fire"] >= rule["fire"] or (best["fire"] >= 0.3 and best["smoke"] >= rule["smoke"])
        else:
            hit = best["fire"] >= rule["conf"] or best["smoke"] >= rule["conf"]
        win.append((t, hit))
        if sum(1 for _, h in win if h) >= rule["hits"]:
            return next(t0 for t0, h in win if h)
    return None

def f1(pairs):
    tp = fn = fp = 0
    for gt, sa in pairs:
        if gt is None:
            fp += len(sa); continue
        ok = any(gt-BEFORE <= s <= gt+AFTER for s in sa)
        if ok: tp += 1; fp += len(sa)-1
        else: fn += 1; fp += len(sa)
    r = tp/(tp+fn) if tp+fn else 0; p = tp/(tp+fp) if tp+fp else 0
    return dict(tp=tp, fn=fn, fp=fp, score=round(2*r*p/(r+p)*100, 2) if r+p else 0.0)

def main():
    global IMGSZ
    ap = argparse.ArgumentParser()
    ap.add_argument("model"); ap.add_argument("--videos", required=True); ap.add_argument("--gt", required=True)
    ap.add_argument("--stride", type=float, default=0.5); ap.add_argument("--tiles", action="store_true")
    ap.add_argument("--tag", default=""); ap.add_argument("--imgsz", type=int, default=640)
    a = ap.parse_args()
    model = (RTDETR if "rtdetr" in a.model.lower() else YOLO)(a.model); IMGSZ = a.imgsz
    vids = sorted(Path(a.videos).glob("*.mp4"))
    per = {}
    for v in vids:
        per[v.stem] = (dump(model, v, a.stride, a.tiles), gt_start(Path(a.gt)/(v.stem+".xml")))
        print(f"  덤프 {v.stem}", flush=True)
    rules = {
        "기본 f+s0.6 4/6": dict(kind="both", conf=0.6, window=6, hits=4),
        "fire만 0.4 4/6":  dict(kind="fire_only", fire=0.4, window=6, hits=4),
        "결합 f0.4/s0.6 4/6": dict(kind="combined", fire=0.4, smoke=0.6, window=6, hits=4),
        "결합+타일가정 3/5": dict(kind="combined", fire=0.4, smoke=0.6, window=5, hits=3),
    }
    print(f"\n=== {a.tag or a.model} (tiles={a.tiles}) ===")
    best = None
    for name, rule in rules.items():
        res = f1([(gt, [onset(rows, rule)+DELAY] if onset(rows, rule) is not None else []) for rows, gt in per.values()])
        print(f"  {name:22s} → {res['score']:6.2f}  (정검 {res['tp']} 미검 {res['fn']} 오검 {res['fp']})")
        if best is None or res["score"] > best[2]:
            best = (name, rule, res["score"])
    # 클립별 판정(최고 규칙) — 어떤 클립을 늘 놓치는지 보려고. 대시보드 결과탭 히트맵이 이 줄을 읽는다
    if best:
        bn, br, _ = best
        print(f"\n=== 클립별 ({bn}) ===")
        for stem, (rows, gt) in per.items():
            o = onset(rows, br); sa = [o + DELAY] if o is not None else []
            if gt is None:
                v = f"오검{len(sa)}" if sa else "무GT"
            else:
                ok = any(gt - BEFORE <= x <= gt + AFTER for x in sa); extra = (len(sa) - 1) if ok else len(sa)
                v = ("정검" if ok else "미검") + (f"+오검{extra}" if extra > 0 else "")
            print(f"  클립 {stem}: {v} (gt={gt} sa={[round(x, 1) for x in sa]})")

if __name__ == "__main__":
    main()
