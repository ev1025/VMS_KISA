# -*- coding: utf-8 -*-
"""pose 모델 키포인트 덤프: 영상 → jsonl (t, persons=[[conf,x1,y1,x2,y2, k1x,k1y,k1c, ...×17], ...])."""
import argparse
import json
import time
from pathlib import Path

import cv2
from ultralytics import YOLO


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--videos", required=True)
    ap.add_argument("--model", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--stride", type=float, default=1.0)
    ap.add_argument("--conf", type=float, default=0.10)
    a = ap.parse_args()

    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    model = YOLO(a.model)
    for order, mp4 in enumerate(sorted(Path(a.videos).glob("*.mp4")), 1):
        t0 = time.time()
        cap = cv2.VideoCapture(str(mp4))
        fps = cap.get(cv2.CAP_PROP_FPS) or 30
        step = max(1, round(fps * a.stride))
        rows = []
        i = 0
        while True:
            if not cap.grab():
                break
            if i % step == 0:
                ok, fr = cap.retrieve()
                if ok:
                    r = model.predict(fr, conf=a.conf, imgsz=640, verbose=False)[0]
                    persons = []
                    if r.keypoints is not None and len(r.boxes):
                        kdata = r.keypoints.data.cpu().numpy()
                        for b, kp in zip(r.boxes, kdata):
                            x1, y1, x2, y2 = (round(float(v)) for v in b.xyxy[0])
                            flat = [round(float(v), 1) for xyc in kp for v in xyc]
                            persons.append([round(float(b.conf), 3), x1, y1, x2, y2] + flat)
                    rows.append({"t": round(i / fps, 2), "persons": persons})
            i += 1
        cap.release()
        with open(out / (mp4.stem + ".jsonl"), "w") as f:
            for r_ in rows:
                f.write(json.dumps(r_) + "\n")
        print(f"[{order}] {mp4.stem} 표본 {len(rows)} ({time.time()-t0:.0f}초)", flush=True)


if __name__ == "__main__":
    main()
