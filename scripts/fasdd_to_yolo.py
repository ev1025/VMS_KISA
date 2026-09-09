# -*- coding: utf-8 -*-
"""FASDD COCO JSON → YOLO 라벨. 클래스 그대로(0 fire,1 smoke). 이미지는 심링크."""
import json, os, sys
from pathlib import Path

F = Path("/NHNHOME/WORKSPACE/26mss002_E3/vms/datasets/ext/fasdd")
OUT = Path("/NHNHOME/WORKSPACE/26mss002_E3/vms/datasets/fasdd_yolo")


def conv(split):
    d = json.load(open(F / "annotations" / f"{split}.json"))
    imgs = {im["id"]: im for im in d["images"]}
    anns = {}
    for a in d["annotations"]:
        anns.setdefault(a["image_id"], []).append(a)
    idir = OUT / "images" / split
    ldir = OUT / "labels" / split
    idir.mkdir(parents=True, exist_ok=True)
    ldir.mkdir(parents=True, exist_ok=True)
    src_split = "train" if split == "train" else split
    n = 0
    for iid, im in imgs.items():
        fn = os.path.basename(im["file_name"])
        src = F / "images" / src_split / fn
        if not src.exists():
            # 일부는 다른 split 폴더에 있을 수 있음
            cand = list(F.glob(f"images/*/{fn}"))
            if not cand:
                continue
            src = cand[0]
        w, h = im["width"], im["height"]
        lines = []
        for a in anns.get(iid, []):
            x, y, bw, bh = a["bbox"]
            cx, cy = (x + bw / 2) / w, (y + bh / 2) / h
            lines.append(f"{a['category_id']} {cx:.6f} {cy:.6f} {bw/w:.6f} {bh/h:.6f}")
        dst_i = idir / fn
        if not dst_i.exists():
            try:
                os.symlink(src.resolve(), dst_i)
            except OSError:
                pass
        (ldir / (Path(fn).stem + ".txt")).write_text("\n".join(lines))
        n += 1
    print(f"{split}: {n}장")


if __name__ == "__main__":
    for s in ("train", "val"):
        conv(s)
    (OUT / "data.yaml").write_text(
        f"path: {OUT}\ntrain: images/train\nval: images/val\nnc: 2\nnames: ['fire', 'smoke']\n")
    print("data.yaml 작성")
