# -*- coding: utf-8 -*-
"""COCO2017 에서 person 만 남긴 부분집합 생성 (nc=1, 파국적 망각 방지용 혼합분).

- person(클래스 0) 라인만 유지, person 있는 이미지에서 pos 장 표본
- person 없는 이미지 neg 장 = 배경 네거티브
"""
import argparse
import os
import random
import shutil
from pathlib import Path


def link_or_copy(src, dst):
    try:
        os.link(src, dst)
    except OSError:
        shutil.copy2(src, dst)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--images", required=True, help="coco train2017 이미지 폴더")
    ap.add_argument("--labels", required=True, help="coco YOLO 라벨 폴더")
    ap.add_argument("--out", required=True)
    ap.add_argument("--pos", type=int, default=12000)
    ap.add_argument("--neg", type=int, default=2000)
    ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args()

    random.seed(a.seed)
    out = Path(a.out)
    (out / "images").mkdir(parents=True, exist_ok=True)
    (out / "labels").mkdir(parents=True, exist_ok=True)

    img_dir = Path(a.images)
    pos_pool, neg_pool = [], []
    for lb in Path(a.labels).glob("*.txt"):
        person = [ln for ln in lb.read_text().splitlines() if ln.startswith("0 ")]
        (pos_pool if person else neg_pool).append((lb, person))
    print(f"COCO: person 있는 이미지 {len(pos_pool)} · 없는 이미지 {len(neg_pool)}")

    n_pos = n_neg = 0
    for lb, person in random.sample(pos_pool, min(a.pos, len(pos_pool))):
        img = img_dir / (lb.stem + ".jpg")
        if not img.exists():
            continue
        link_or_copy(img, out / "images" / ("coco_" + img.name))
        (out / "labels" / ("coco_" + lb.name)).write_text("\n".join(person))
        n_pos += 1
    for lb, _ in random.sample(neg_pool, min(a.neg, len(neg_pool))):
        img = img_dir / (lb.stem + ".jpg")
        if not img.exists():
            continue
        link_or_copy(img, out / "images" / ("coco_" + img.name))
        (out / "labels" / ("coco_" + lb.name)).write_text("")
        n_neg += 1
    print(f"완료: person {n_pos} · 배경 {n_neg}")


if __name__ == "__main__":
    main()
