# -*- coding: utf-8 -*-
"""라벨링용 전체 프레임 (자동 발화점 탐지 없음). 원본 그대로, 사람이 보고 판단."""
import cv2, json, xml.etree.ElementTree as ET
from pathlib import Path
G = Path("/NHNHOME/WORKSPACE/26mss002_E3/vms")
SRC = G/"data/원본데이터/kisa_연구개발_방화영상"; OUT = G/"data/학습데이터/손라벨/full"; OUT.mkdir(exist_ok=True)
def hms(t):
    h, m, s = (t or "0:0:0").split(":"); return int(h)*3600+int(m)*60+int(s)
meta = []
clips = sorted(SRC.glob("*.mp4"))
for n, mp4 in enumerate(clips, 1):
    x = mp4.with_suffix(".xml")
    if not x.exists(): continue
    al = ET.parse(x).getroot().find(".//Alarm")
    if al is None: continue
    gt = hms(al.findtext("StartTime")); ign = max(0, gt-10)
    cap = cv2.VideoCapture(str(mp4)); fps = cap.get(cv2.CAP_PROP_FPS) or 30
    for tag, tt in (("a", ign+3), ("b", gt), ("c", gt+8)):
        cap.set(cv2.CAP_PROP_POS_FRAMES, max(0, int(tt*fps)))
        ok, fr = cap.read()
        if not ok: continue
        H, W = fr.shape[:2]
        cv2.imwrite(str(OUT/f"{mp4.stem}_{tag}.png"), fr)
        meta.append({"file": f"{mp4.stem}_{tag}.png", "clip": mp4.stem, "t": round(tt,1), "gt": gt,
                     "W": W, "H": H, "x0": 0, "y0": 0, "cw": W, "ch": H, "auto": False})
    cap.release()
    if n % 20 == 0: print(f"[{n}/{len(clips)}]", flush=True)
json.dump(meta, open(OUT/"meta.json","w"), ensure_ascii=False)
print("전체프레임", len(meta), "장")
