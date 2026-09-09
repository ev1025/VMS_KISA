# -*- coding: utf-8 -*-
"""학습 이미지를 긴 변 960 으로 줄인 사본을 만든다. 원본 1920 은 학습 때 어차피 640 으로
   줄어드므로 화질 손실이 없고, 디코딩 크기가 작아져 150GB 컨테이너에서도 RAM 캐시가 다 들어간다.
   원본 트리를 data/fire960/<원래상대경로> 로 미러링해 라벨 경로 규칙(images->labels)도 유지한다."""
import sys, os
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import cv2

G = Path("/NHNHOME/WORKSPACE/26mss002_E3/vms")
DST = G / "data/fire960"
SRC_ROOTS = [G/"data/학습데이터/dataset_24k", G/"data/학습데이터/fasdd_yolo", G/"data/학습데이터/human_fire",
             G/"data/학습데이터/human_synth", G/"data/학습데이터/fasdd_snow2", G/"data/학습데이터/fasdd_snowfog"]

def collect():
    imgs = []
    for root in SRC_ROOTS:
        for p in (root/"images").rglob("*"):
            if p.suffix.lower() in (".jpg",".jpeg",".png"):
                imgs.append(p)
    return imgs

def one(p):
    rel = p.relative_to(G/"data/fire")
    out = DST/rel
    if out.exists(): return 0
    out.parent.mkdir(parents=True, exist_ok=True)
    im = cv2.imread(str(p))
    if im is None: return 0
    h,w = im.shape[:2]
    if max(h,w) > 960:
        s = 960/max(h,w); im = cv2.resize(im,(int(w*s),int(h*s)),interpolation=cv2.INTER_AREA)
    cv2.imwrite(str(out), im, [cv2.IMWRITE_JPEG_QUALITY,90])
    # 라벨도 미러링(심링크)
    lp = Path(str(p).replace("/images/","/labels/")).with_suffix(".txt")
    if lp.exists():
        lo = Path(str(out).replace("/images/","/labels/")).with_suffix(".txt")
        lo.parent.mkdir(parents=True, exist_ok=True)
        if not lo.exists():
            try: os.symlink(lp, lo)
            except FileExistsError: pass
    return 1

if __name__ == "__main__":
    imgs = collect(); print(f"대상 {len(imgs)}장", flush=True)
    done = 0
    with ThreadPoolExecutor(48) as ex:
        for i,r in enumerate(ex.map(one, imgs),1):
            done += r
            if i%10000==0: print(f"  {i}/{len(imgs)}", flush=True)
    print(f"완료 {done}장 신규 → {DST}", flush=True)
