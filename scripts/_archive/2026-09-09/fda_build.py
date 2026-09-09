# -*- coding: utf-8 -*-
"""FDA 48k 데이터셋 생성: 24k 원본 + 24k FDA 사본 (mix λ0.6, b 0.02~0.03, 육안게이트 통과 설정).

타겟 스타일 풀 = 방화75 야간 9편에서 뽑은 프레임들 (점화 전 = 순수 야간 스타일).
라벨은 원본 그대로 복사 (FDA 는 기하 불변).
"""
import random
import xml.etree.ElementTree as ET
from pathlib import Path

import cv2
import numpy as np

SRC = Path("/NHNHOME/WORKSPACE/26mss002_E3/datasets/dataset_24k")
FIRE75 = Path("/NHNHOME/WORKSPACE/26mss002_E3/vms/datasets/fire75_raw")
OUT = Path("/NHNHOME/WORKSPACE/26mss002_E3/vms/datasets/fire_fda48k")
LAM = 0.6


def hms(t):
    h, m, s = (t or "0:0:0").split(":")
    return int(h) * 3600 + int(m) * 60 + int(s)


def fda(src, tgt, beta):
    tgt = cv2.resize(tgt, (src.shape[1], src.shape[0]))
    s = src.astype(np.float32)
    t = tgt.astype(np.float32)
    fs = np.fft.fft2(s, axes=(0, 1))
    ft = np.fft.fft2(t, axes=(0, 1))
    amp_s, pha_s = np.abs(fs), np.angle(fs)
    amp_t = np.abs(ft)
    amp_s = np.fft.fftshift(amp_s, axes=(0, 1))
    amp_t = np.fft.fftshift(amp_t, axes=(0, 1))
    h, w = s.shape[:2]
    b = max(1, int(min(h, w) * beta))
    ch, cw = h // 2, w // 2
    amp_s[ch - b:ch + b, cw - b:cw + b] = ((1 - LAM) * amp_s[ch - b:ch + b, cw - b:cw + b]
                                           + LAM * amp_t[ch - b:ch + b, cw - b:cw + b])
    amp_s = np.fft.ifftshift(amp_s, axes=(0, 1))
    out = np.real(np.fft.ifft2(amp_s * np.exp(1j * pha_s), axes=(0, 1)))
    return np.clip(out, 0, 255).astype(np.uint8)


def night_pool():
    pool = []
    for x in sorted(FIRE75.glob("*.xml")):
        r = ET.parse(x).getroot()
        if not (r.findtext(".//TimeOfDay") or "").lower().startswith("night"):
            continue
        start = hms(r.findtext(".//Alarm/StartTime"))
        cap = cv2.VideoCapture(str(FIRE75 / (x.stem + ".mp4")))
        fps = cap.get(cv2.CAP_PROP_FPS) or 30
        for dt in (30, 60, 90):
            cap.set(cv2.CAP_PROP_POS_FRAMES, int(max(2, start - dt) * fps))
            ok, fr = cap.read()
            if ok:
                pool.append(cv2.resize(fr, (640, 384)))
        cap.release()
    return pool


def main():
    random.seed(0)
    import os, shutil

    def link(a, b):
        try:
            os.link(a, b)
        except OSError:
            shutil.copy2(a, b)

    for sub in ("images/train", "labels/train"):
        (OUT / sub).mkdir(parents=True, exist_ok=True)
    pool = night_pool()
    print(f"야간 스타일 풀 {len(pool)}장")
    imgs = sorted((SRC / "images/train").glob("*.jpg"))
    done = 0
    for i, p in enumerate(imgs, 1):
        # 원본 하드링크
        link(p, OUT / "images/train" / p.name)
        lb = SRC / "labels/train" / (p.stem + ".txt")
        if lb.exists():
            link(lb, OUT / "labels/train" / lb.name)
        # FDA 사본
        img = cv2.imread(str(p))
        if img is None:
            continue
        out = fda(img, random.choice(pool), random.uniform(0.02, 0.03))
        cv2.imwrite(str(OUT / "images/train" / (p.stem + "__fda.jpg")), out,
                    [cv2.IMWRITE_JPEG_QUALITY, 92])
        if lb.exists():
            link(lb, OUT / "labels/train" / (p.stem + "__fda.txt"))
        done += 1
        if i % 2000 == 0:
            print(f"{i}/{len(imgs)}", flush=True)
    import os as _os
    _os.symlink(str((SRC / "images/val").resolve()), OUT / "images/val")
    _os.symlink(str((SRC / "labels/val").resolve()), OUT / "labels/val")
    (OUT / "data.yaml").write_text(
        f"path: {OUT.resolve()}\ntrain: images/train\nval: images/val\nnc: 2\nnames: ['fire', 'smoke']\n")
    print(f"완료: FDA 사본 {done}장 (+원본 {len(imgs)})")


if __name__ == "__main__":
    main()
