# -*- coding: utf-8 -*-
"""서버 GPU person 박스 덤프: 영상 폴더 → jsonl (t, [conf,x1,y1,x2,y2]...). 규칙 스윕용."""
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
    vids = sorted(Path(a.videos).glob("*.mp4"))
    for order, mp4 in enumerate(vids, 1):
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
                    boxes = []
                    for b in model.predict(fr, conf=a.conf, imgsz=640, classes=[0],
                                           verbose=False)[0].boxes:
                        x1, y1, x2, y2 = (round(float(v)) for v in b.xyxy[0])
                        boxes.append([round(float(b.conf), 3), x1, y1, x2, y2])
                    rows.append({"t": round(i / fps, 2), "boxes": boxes})
            i += 1
        cap.release()
        with open(out / (mp4.stem + ".jsonl"), "w") as f:
            for r in rows:
                f.write(json.dumps(r) + "\n")
        print(f"[{order}/{len(vids)}] {mp4.stem} 표본 {len(rows)} ({time.time()-t0:.0f}초)", flush=True)


if __name__ == "__main__":
    main()
