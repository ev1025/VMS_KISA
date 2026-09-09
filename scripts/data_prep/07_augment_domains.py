# -*- coding: utf-8 -*-
"""KISA 배포용 채점에서 확인된 도메인 구멍(야간 IR·안개·원거리 소형)을 증강으로 메운다.

배경: 배포용 방화 10편 채점(F1 25점)에서 미탐 4편의 원인이 전부 학습 분포 밖이었다.
  - 야간 IR(흑백): 색 의존 확인됨(주간 프레임 흑백 변환만으로 fire 0.78 → 소실)
  - 안개: 안개 자체를 smoke 0.5~0.63 으로 오탐
  - 설경 원거리: 작은 불꽃 미탐

세 가지 변형을 만든다. 전부 오프라인 사본이라 무엇이 들어갔는지 재현된다.
  ir    흑백 + 화염 박스 중심 포화·글로우(블루밍 모사) + 배경 저조도 + 센서 노이즈
  fog   안개 오버레이. 라벨 있는 장 = 안개 속 화재(포지티브 유지),
        라벨 빈 장 = 안개 네거티브("안개는 연기가 아니다")
  paste 화염 크롭을 라벨 빈 장에 소형으로 soft-blend 합성(경계 알파 페더링,
        지름길 학습 방지). 새 fire 라벨 생성

사용(서버):
  python scripts/data_prep/07_augment_domains.py <dataset_root> --out <새 dataset_root> --ratio 0.2
결과: 원본 train 전체(하드링크) + 증강 사본, val 은 원본 그대로, data.yaml 동봉.
"""

import argparse
import json
import os
import random
import shutil
import sys
from pathlib import Path

import cv2
import numpy as np

FIRE_CLASS_ID = 0
# 증강 종류별 비중 — ir 이 주 타깃(야간 IR 미탐 2편)이라 절반을 준다
MIX = [("ir", 0.5), ("fog", 0.3), ("paste", 0.2)]
PASTE_HEIGHT_PX = (10, 36)        # 합성 화염의 목표 높이(원거리 소형 대응)
PASTE_BAND = (0.35, 0.80)         # 합성 위치의 세로 범위(하늘·최상단 제외)


def read_label(path):
    if not path.exists():
        return []
    rows = []
    for line in path.read_text().split("\n"):
        parts = line.split()
        if len(parts) == 5:
            rows.append([int(parts[0])] + [float(v) for v in parts[1:]])
    return rows


def yolo_to_xyxy(box, w, h):
    _, cx, cy, bw, bh = box
    return (int((cx - bw / 2) * w), int((cy - bh / 2) * h),
            int((cx + bw / 2) * w), int((cy + bh / 2) * h))


def augment_ir(img, labels):
    """흑백 + 화염 포화·글로우 + 저조도 + 노이즈. 실측 IR 프레임(헤일로·백화)을 흉내낸다."""
    h, w = img.shape[:2]
    gray = cv2.cvtColor(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY), cv2.COLOR_GRAY2BGR).astype(np.float32)
    dark = gray * random.uniform(0.35, 0.55) - random.uniform(5, 15)   # 배경 저조도

    # 포화·헤일로는 도형이 아니라 "그 화염의 밝은 픽셀 모양"을 따라간다.
    # 타원을 채우면 흰 스티커가 붙은 것처럼 되어 경계 아티팩트를 학습한다.
    luma = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY).astype(np.float32)
    glow = np.zeros((h, w), np.float32)
    for box in labels:
        if box[0] != FIRE_CLASS_ID:
            continue
        x1, y1, x2, y2 = yolo_to_xyxy(box, w, h)
        x1, y1 = max(0, x1), max(0, y1)
        roi = luma[y1:y2, x1:x2]
        if roi.size == 0:
            continue
        top = np.percentile(roi, 75)                                   # 화염 안 밝은 25%가 포화 씨앗
        seed = np.clip((roi - top) / max(1.0, 255 - top), 0, 1) ** 0.7
        glow[y1:y2, x1:x2] = np.maximum(glow[y1:y2, x1:x2], seed)
    if glow.any():
        k = max(9, int(min(h, w) * 0.03) | 1)
        core = cv2.GaussianBlur(glow, (k, k), 0)                       # 포화 중심(질감 소실)
        halo = cv2.GaussianBlur(glow, (k * 5 | 1, k * 5 | 1), 0)       # 넓게 번지는 헤일로
        m = np.clip(core * 1.4 + halo * 1.2, 0, 1)[..., None]
        dark = dark * (1 - m) + 255.0 * m

    noise = np.random.normal(0, random.uniform(4, 9), dark.shape).astype(np.float32)
    return np.clip(dark + noise, 0, 255).astype(np.uint8), labels


def augment_fog(img, labels):
    """안개 오버레이. 굵은 저주파 얼룩으로 균일하지 않은 안개를 만든다."""
    h, w = img.shape[:2]
    patch = cv2.resize(np.random.rand(h // 64 + 1, w // 64 + 1).astype(np.float32), (w, h))
    alpha = np.clip(random.uniform(0.35, 0.6) + (patch - 0.5) * 0.2, 0.2, 0.75)[..., None]
    fog_color = random.uniform(195, 225)
    out = img.astype(np.float32) * (1 - alpha) + fog_color * alpha
    return out.astype(np.uint8), labels


def collect_fire_crops(dataset, sample_names, limit=400):
    """도너: 어느 정도 크기가 되는 화염 박스를 크롭으로 모아둔다."""
    crops = []
    for name in sample_names:
        img_path = dataset / "images" / "train" / name
        labels = read_label(dataset / "labels" / "train" / (Path(name).stem + ".txt"))
        boxes = [b for b in labels if b[0] == FIRE_CLASS_ID and b[3] > 0.03 and b[4] > 0.03]
        if not boxes:
            continue
        img = cv2.imread(str(img_path))
        if img is None:
            continue
        for box in boxes[:2]:
            x1, y1, x2, y2 = yolo_to_xyxy(box, img.shape[1], img.shape[0])
            if x2 - x1 < 12 or y2 - y1 < 12:
                continue
            aspect = (x2 - x1) / (y2 - y1)
            if not 0.4 <= aspect <= 2.5:                       # 가로로 눌린 조각 배제
                continue
            crop = img[max(0, y1):y2, max(0, x1):x2]
            b, g, r = crop[..., 0].astype(int), crop[..., 1].astype(int), crop[..., 2].astype(int)
            fire_like = ((r > 150) & (r >= g) & (g >= b)).mean()
            if fire_like < 0.15:                               # 불꽃색 픽셀이 적으면 배경 조각
                continue
            crops.append(crop.copy())
        if len(crops) >= limit:
            break
    return crops


def augment_paste(img, crops):
    """빈 장에 소형 화염을 soft-blend 합성. 경계를 페더링해 지름길 학습을 막는다."""
    h, w = img.shape[:2]
    out = img.copy()
    new_labels = []
    for _ in range(random.randint(1, 2)):
        crop = random.choice(crops)
        th = random.randint(*PASTE_HEIGHT_PX)
        tw = max(6, int(crop.shape[1] * th / crop.shape[0]))
        small = cv2.resize(crop, (tw, th))
        y = random.randint(int(h * PASTE_BAND[0]), int(h * PASTE_BAND[1]) - th)
        x = random.randint(8, w - tw - 8)

        # 마스크도 크롭의 밝기 모양을 따라간다(타원 채우기 = 경계 아티팩트)
        crop_luma = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY).astype(np.float32)
        mask = np.clip((crop_luma - crop_luma.mean()) / max(1.0, crop_luma.max() - crop_luma.mean()), 0, 1)
        mask = cv2.GaussianBlur(mask, (0, 0), sigmaX=max(1.5, tw * 0.12))
        # 패치 가장자리에서 0 으로 죽이는 창 — 순흑 배경에 사각 경계가 비치는 것 방지
        fy = np.minimum(np.arange(th), np.arange(th)[::-1]) / max(1, th * 0.25)
        fx = np.minimum(np.arange(tw), np.arange(tw)[::-1]) / max(1, tw * 0.25)
        mask = (mask * np.clip(np.outer(fy, fx), 0, 1))[..., None]

        roi = out[y:y + th, x:x + tw].astype(np.float32)
        blended = roi * (1 - mask) + small.astype(np.float32) * mask
        # 배경이 어두우면 불빛이 주변을 비추는 온기(warm glow)를 살짝 얹는다
        if roi.mean() < 90:
            gk = max(3, tw | 1)
            glow = cv2.GaussianBlur(mask, (gk * 2 | 1, gk * 2 | 1), 0)
            blended = np.clip(blended + glow[..., None] * np.array([15.0, 35.0, 70.0]), 0, 255)
        out[y:y + th, x:x + tw] = blended.astype(np.uint8)
        new_labels.append([FIRE_CLASS_ID, (x + tw / 2) / w, (y + th / 2) / h, tw / w, th / h])
    return out, new_labels


def hardlink_or_copy(src, dst):
    try:
        os.link(src, dst)
    except OSError:
        shutil.copy2(src, dst)


def main():
    parser = argparse.ArgumentParser(description="도메인 증강 데이터셋 생성")
    parser.add_argument("dataset", help="원본 dataset 루트(images/labels × train/val)")
    parser.add_argument("--out", required=True, help="새 dataset 루트")
    parser.add_argument("--ratio", type=float, default=0.2, help="train 대비 증강 사본 비율")
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()

    random.seed(args.seed)
    np.random.seed(args.seed)
    src = Path(args.dataset)
    out = Path(args.out)

    train_images = sorted(p.name for p in (src / "images" / "train").glob("*") if p.suffix.lower() in (".jpg", ".jpeg", ".png"))
    labeled, empty = [], []
    for name in train_images:
        rows = read_label(src / "labels" / "train" / (Path(name).stem + ".txt"))
        (labeled if rows else empty).append(name)
    print(f"train {len(train_images)}장 (라벨 있음 {len(labeled)} · 없음 {len(empty)})")

    for sub in ("images/train", "labels/train"):
        (out / sub).mkdir(parents=True, exist_ok=True)
    for split in ("images/val", "labels/val"):
        d = out / split
        if not d.exists():
            d.parent.mkdir(parents=True, exist_ok=True)
            try:
                os.symlink((src / split).resolve(), d, target_is_directory=True)
            except OSError:                      # 윈도우 로컬 테스트: 심링크 권한 없으면 복사
                shutil.copytree(src / split, d)
    for name in train_images:
        hardlink_or_copy(src / "images" / "train" / name, out / "images" / "train" / name)
        lb = src / "labels" / "train" / (Path(name).stem + ".txt")
        if lb.exists():
            hardlink_or_copy(lb, out / "labels" / "train" / lb.name)

    total_aug = int(len(train_images) * args.ratio)
    plan = [(kind, int(total_aug * weight)) for kind, weight in MIX]
    crops = collect_fire_crops(src, random.sample(labeled, min(len(labeled), 3000)))
    print(f"증강 {total_aug}장 계획 {dict(plan)} · 화염 도너 크롭 {len(crops)}개")

    made = {k: 0 for k, _ in MIX}
    for kind, count in plan:
        pool = empty if kind == "paste" else (labeled if kind == "ir" else train_images)
        for name in random.sample(pool, min(count, len(pool))):
            img = cv2.imread(str(src / "images" / "train" / name))
            if img is None:
                continue
            labels = read_label(src / "labels" / "train" / (Path(name).stem + ".txt"))
            if kind == "ir":
                aug, out_labels = augment_ir(img, labels)
            elif kind == "fog":
                aug, out_labels = augment_fog(img, labels)
            else:
                if not crops:
                    break
                aug, out_labels = augment_paste(img, crops)
            stem = f"{Path(name).stem}__aug_{kind}"
            cv2.imwrite(str(out / "images" / "train" / (stem + ".jpg")), aug,
                        [cv2.IMWRITE_JPEG_QUALITY, 92])
            (out / "labels" / "train" / (stem + ".txt")).write_text(
                "\n".join(" ".join(f"{v:.6f}" if i else str(int(v)) for i, v in enumerate(row))
                          for row in out_labels))
            made[kind] += 1

    (out / "data.yaml").write_text(
        f"path: {out.resolve()}\ntrain: images/train\nval: images/val\nnc: 2\nnames: ['fire', 'smoke']\n")
    (out / "aug_meta.json").write_text(json.dumps(
        {"source": str(src), "ratio": args.ratio, "seed": args.seed, "made": made},
        ensure_ascii=False, indent=2))
    print(f"완료: {out}  증강 {made} (+원본 {len(train_images)})")


if __name__ == "__main__":
    main()
