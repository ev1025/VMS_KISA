# -*- coding: utf-8 -*-
"""기존+신규 데이터 세세 분석: 규모·클래스·해상도·주야(밝기)·박스크기 분포."""
import json, os, glob, random
from collections import Counter
from pathlib import Path
import numpy as np
import cv2

G = Path("/NHNHOME/WORKSPACE/26mss002_E3/vms")
W = Path("/NHNHOME/WORKSPACE/26mss002_E3")
random.seed(0)


def sample_bright(img_paths, n=400):
    """이미지 평균 밝기 표본 → 야간(<60)/황혼(60~110)/주간(>110) 비율"""
    paths = random.sample(img_paths, min(n, len(img_paths)))
    br = []
    for p in paths:
        im = cv2.imread(str(p), cv2.IMREAD_GRAYSCALE)
        if im is not None:
            br.append(im.mean())
    br = np.array(br)
    if not len(br):
        return {}
    return {"표본": len(br), "야간<60": int((br < 60).sum()), "황혼60-110": int(((br >= 60) & (br <= 110)).sum()),
            "주간>110": int((br > 110).sum()), "평균밝기": round(float(br.mean()), 1)}


def yolo_stats(img_dir, lbl_dir, name):
    imgs = glob.glob(str(img_dir) + "/*.jpg") + glob.glob(str(img_dir) + "/*.png")
    cls = Counter(); boxsz = []; wh = Counter()
    lbls = glob.glob(str(lbl_dir) + "/*.txt")
    for lb in random.sample(lbls, min(3000, len(lbls))):
        for line in open(lb):
            p = line.split()
            if len(p) == 5:
                cls[p[0]] += 1
                boxsz.append(float(p[3]) * float(p[4]))       # 정규화 면적
    # 해상도 표본
    for p in random.sample(imgs, min(200, len(imgs))):
        im = cv2.imread(p)
        if im is not None:
            wh[f"{im.shape[1]}x{im.shape[0]}"] += 1
    bs = np.array(boxsz) if boxsz else np.array([0])
    print(f"\n### {name}")
    print(f"  이미지 {len(imgs)} · 라벨파일 {len(lbls)}")
    print(f"  박스 클래스(표본): {dict(cls)}")
    print(f"  박스 면적(정규화) 중앙값 {np.median(bs):.4f} · 소형(<0.01)비율 {(bs<0.01).mean()*100:.0f}%")
    print(f"  해상도 상위: {dict(wh.most_common(4))}")
    print(f"  밝기분포: {sample_bright(imgs)}")


print("="*60, "\n화재 데이터\n", "="*60)
yolo_stats(W/"datasets/dataset_24k/images/train", W/"datasets/dataset_24k/labels/train", "우리 24k (기존)")
if (G/"datasets/fasdd_yolo/images/train").exists():
    yolo_stats(G/"datasets/fasdd_yolo/images/train", G/"datasets/fasdd_yolo/labels/train", "FASDD (신규)")

print("\n", "="*60, "\nKISA 배포용 화재 10편 (채점 대상, 밝기만)\n", "="*60)
# 배포 화재는 영상 → 첫 프레임 밝기
for mp4 in sorted((W/"vms/data/원본데이터/kisa_배포_방화채점셋/videos").glob("*.mp4")):
    cap = cv2.VideoCapture(str(mp4)); ok, fr = cap.read(); cap.release()
    if ok:
        b = cv2.cvtColor(fr, cv2.COLOR_BGR2GRAY).mean()
        tag = "야간" if b < 60 else ("황혼" if b <= 110 else "주간")
        print(f"  {mp4.stem}: 밝기 {b:.0f} ({tag})")
