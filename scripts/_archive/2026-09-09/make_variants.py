# -*- coding: utf-8 -*-
"""24k 변형 데이터셋 생성 (방화 A/B): 장소균등 축소 / fire편향 재균형 / 클립당 1프레임.

파일명 0001_SM_GAH_00001.jpg → 클립 0001, 태그 SM, 장소 GAH.
변형:
  half_loc  : 장소별 균등하게 절반 (편중 완화)
  clip1     : 클립당 1프레임만 (중복 제거, 다양성↑, 크기 대폭↓)
  firebal   : smoke 과다 완화 - smoke만 있는 프레임을 절반 버림
val 은 원본 공유(심링크).
"""
import argparse
import os
import random
import shutil
from collections import defaultdict
from pathlib import Path

SRC = Path("/NHNHOME/WORKSPACE/26mss002_E3/datasets/dataset_24k")


def link(a, b):
    try:
        os.link(a, b)
    except OSError:
        shutil.copy2(a, b)


def parts(stem):
    p = stem.split("_")
    return (p[0], p[1], p[2]) if len(p) >= 3 else ("?", "?", "?")


def has_class(lb, cls):
    if not lb.exists():
        return False
    return any(line.startswith(cls + " ") for line in lb.read_text().splitlines())


def build(names, out):
    out = Path(out)
    for s in ("images/train", "labels/train"):
        (out / s).mkdir(parents=True, exist_ok=True)
    for stem in names:
        link(SRC / "images/train" / (stem + ".jpg"), out / "images/train" / (stem + ".jpg"))
        lb = SRC / "labels/train" / (stem + ".txt")
        if lb.exists():
            link(lb, out / "labels/train" / (stem + ".txt"))
    for s in ("images/val", "labels/val"):
        d = out / s
        if not d.exists():
            os.symlink((SRC / s).resolve(), d)
    (out / "data.yaml").write_text(
        f"path: {out.resolve()}\ntrain: images/train\nval: images/val\nnc: 2\nnames: ['fire', 'smoke']\n")
    print(f"{out.name}: {len(names)}장")


def main():
    random.seed(0)
    ap = argparse.ArgumentParser()
    ap.add_argument("--which", required=True, choices=["half_loc", "clip1", "firebal"])
    ap.add_argument("--out", required=True)
    a = ap.parse_args()

    stems = [p.stem for p in (SRC / "images/train").glob("*.jpg")]

    if a.which == "half_loc":
        by_loc = defaultdict(list)
        for s in stems:
            by_loc[parts(s)[2]].append(s)
        keep = []
        for loc, lst in by_loc.items():
            random.shuffle(lst)
            keep += lst[:len(lst) // 2]
        build(keep, a.out)

    elif a.which == "clip1":
        by_clip = defaultdict(list)
        for s in stems:
            by_clip[parts(s)[0] + parts(s)[2]].append(s)   # 클립+장소
        keep = [random.choice(lst) for lst in by_clip.values()]
        build(keep, a.out)

    elif a.which == "firebal":
        keep = []
        for s in stems:
            lb = SRC / "labels/train" / (s + ".txt")
            fire = has_class(lb, "0")
            smoke = has_class(lb, "1")
            if smoke and not fire and random.random() < 0.5:
                continue          # smoke만 프레임 절반 버림
            keep.append(s)
        build(keep, a.out)


if __name__ == "__main__":
    main()
