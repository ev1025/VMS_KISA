# -*- coding: utf-8 -*-
"""사람 라벨 → YOLO 학습셋. 라벨된 프레임을 원본에서 다시 뽑고,
   불은 제자리에 머무는 성질을 이용해 앞뒤로 시간 전파(±N초)해 표본을 불린다."""
import cv2, json, xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path

G = Path("/NHNHOME/WORKSPACE/26mss002_E3/vms")
SRC = G/"data/원본데이터/kisa_연구개발_방화영상"
RAW = G/"data/원본데이터"          # 라벨에 src(상대경로)가 있으면 이 기준으로 찾는다
OUT = G/"data/학습데이터/human_fire"
PROP = [-2.0, -1.0, 0.0, 1.0, 2.0]      # 라벨 시각 기준 전파 오프셋(초)

for s in ("images/train", "labels/train"):
    (OUT/s).mkdir(parents=True, exist_ok=True)

rows = json.load(open(G/"data/학습데이터/손라벨/fire_labels.json", encoding="utf-8"))
by_frame = defaultdict(list)
for r in rows:
    by_frame[(r["clip"], r["t"])].append(r)

n_img = n_box = 0
for (clip, t), rs in sorted(by_frame.items()):
    # 라벨 생성 화면이 남긴 src(원본데이터 기준 경로)가 있으면 그 영상에서 뽑는다.
    # 없으면 예전처럼 방화영상 폴더에서 찾는다(하위호환).
    src = next((r.get("src") for r in rs if r.get("src")), None)
    mp4 = (RAW/src) if src else SRC/(clip+".mp4")
    if not mp4.exists():
        continue
    cap = cv2.VideoCapture(str(mp4)); fps = cap.get(cv2.CAP_PROP_FPS) or 30
    for off in PROP:
        tt = t + off
        if tt < 0: continue
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(tt*fps))
        ok, fr = cap.read()
        if not ok: continue
        # t 는 초. 프레임 단위로 고른 라벨은 소수라 같은 초에 두 장이 나올 수 있다 → 소수까지 이름에 넣는다
        ts = f"{float(t):.2f}".rstrip("0").rstrip(".").replace(".", "p")
        stem = f"{clip}_{ts}_{off:+.0f}".replace("+", "p").replace("-", "m")
        cv2.imwrite(str(OUT/"images/train"/(stem+".jpg")), fr, [cv2.IMWRITE_JPEG_QUALITY, 92])
        lines = []
        for r in rs:
            cx = r["x"] + r["w"]/2; cy = r["y"] + r["h"]/2
            if not (0 < cx < 1 and 0 < cy < 1): continue
            lines.append(f"{r['cls']} {cx:.6f} {cy:.6f} {r['w']:.6f} {r['h']:.6f}")
            n_box += 1
        (OUT/"labels/train"/(stem+".txt")).write_text("\n".join(lines))
        n_img += 1
    cap.release()

# val 은 기존 24k val 공유
import os
for s in ("images/val", "labels/val"):
    d = OUT/s
    if not d.exists():
        os.symlink((G/"data/학습데이터/dataset_24k"/s).resolve(), d)
(OUT/"data.yaml").write_text(
    f"path: {OUT}\ntrain: images/train\nval: images/val\nnc: 2\nnames: ['fire','smoke']\n")
print(f"사람라벨 학습셋: 이미지 {n_img} · 박스 {n_box}")
