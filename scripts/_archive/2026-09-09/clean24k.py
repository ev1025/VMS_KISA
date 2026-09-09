# -*- coding: utf-8 -*-
"""24k 누수 제거판: 클립 단위로 train/val 분할 (같은 클립이 양쪽에 못 들어감).
   추가로 장소 비율은 유지해 공정 비교 가능하게."""
import random, shutil
from collections import defaultdict
from pathlib import Path

G = Path("/NHNHOME/WORKSPACE/26mss002_E3/vms")
SRC = G/"data/학습데이터/dataset_24k"
OUT = G/"data/학습데이터/clean24k"
random.seed(0)


def key(stem):
    p = stem.split("_")
    return (p[0] + "_" + p[2]) if len(p) >= 3 else stem


# 전체(원래 train+val) 를 모아 클립 단위로 재분할
seen = {}
dups = 0
for split in ("train", "val"):
    for img in (SRC/f"images/{split}").glob("*.jpg"):
        lb = SRC/f"labels/{split}"/(img.stem+".txt")
        if not lb.exists():
            continue
        if img.name in seen:
            dups += 1
            continue                     # 동일 파일명 = train/val 중복(누수)
        seen[img.name] = (img, lb)
print("동일 파일명 중복(누수):", dups)
pairs = list(seen.values())
byclip = defaultdict(list)
for img, lb in pairs: byclip[key(img.stem)].append((img, lb))
clips = sorted(byclip); random.shuffle(clips)
nval = max(1, int(len(clips)*0.2))
val_clips = set(clips[:nval])

if OUT.exists(): shutil.rmtree(OUT)
for s in ("images/train", "labels/train", "images/val", "labels/val"):
    (OUT/s).mkdir(parents=True, exist_ok=True)
n = {"train": 0, "val": 0}
for c in clips:
    sp = "val" if c in val_clips else "train"
    for img, lb in byclip[c]:
        (OUT/f"images/{sp}"/img.name).symlink_to(img.resolve())
        (OUT/f"labels/{sp}"/lb.name).symlink_to(lb.resolve())
        n[sp] += 1
(OUT/"data.yaml").write_text(
    f"path: {OUT}\ntrain: images/train\nval: images/val\nnc: 2\nnames: ['fire','smoke']\n")
print(f"클립 {len(clips)} (val {len(val_clips)}) · train {n['train']}장 · val {n['val']}장 · 누수 0")
