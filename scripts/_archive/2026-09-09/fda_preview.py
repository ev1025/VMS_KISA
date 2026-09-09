# -*- coding: utf-8 -*-
"""FDA(푸리에 도메인 적응) 미리보기: 주간 화재 이미지에 야간/IR 저주파 스타일 이식.

학습 투입 전 육안 게이트용. 소스=자체 24k 주간 화재, 타겟 스타일=방화75 야간 프레임.
beta(저주파 교체 반경 비율) 3종 비교 몽타주 생성.
"""
import xml.etree.ElementTree as ET
from pathlib import Path

import cv2
import numpy as np

SRC24K = Path("/NHNHOME/WORKSPACE/26mss002_E3/datasets/dataset_24k/images/train")
FIRE75 = Path("/NHNHOME/WORKSPACE/26mss002_E3/vms/datasets/fire75_raw")
NIGHT_STEMS = ["C051105_001", "C054105_002", "C055105_001"]   # IR흑백 / 컬러야간 2종


def hms(t):
    h, m, s = (t or "0:0:0").split(":")
    return int(h) * 3600 + int(m) * 60 + int(s)


def fda(src, tgt, beta):
    """src 의 저주파 진폭을 tgt 것으로 교체 (채널별 2D FFT)."""
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
    lam = 0.6                                             # 통째 교체 대신 혼합 (아티팩트 억제)
    amp_s[ch - b:ch + b, cw - b:cw + b] = ((1 - lam) * amp_s[ch - b:ch + b, cw - b:cw + b]
                                           + lam * amp_t[ch - b:ch + b, cw - b:cw + b])
    amp_s = np.fft.ifftshift(amp_s, axes=(0, 1))
    out = np.real(np.fft.ifft2(amp_s * np.exp(1j * pha_s), axes=(0, 1)))
    return np.clip(out, 0, 255).astype(np.uint8)


def grab_frame(stem):
    xml = FIRE75 / (stem + ".xml")
    start = hms(ET.parse(xml).getroot().findtext(".//Alarm/StartTime"))
    cap = cv2.VideoCapture(str(FIRE75 / (stem + ".mp4")))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30
    cap.set(cv2.CAP_PROP_POS_FRAMES, int((start - 30) * fps))   # 점화 전 = 순수 야간 스타일
    ok, fr = cap.read()
    cap.release()
    return fr if ok else None


def main():
    srcs = sorted(SRC24K.glob("*FL*.jpg"))[:200:66]    # 주간 화염 3장
    tgts = [(s, grab_frame(s)) for s in NIGHT_STEMS]
    rows = []
    for sp in srcs[:3]:
        src = cv2.imread(str(sp))
        src = cv2.resize(src, (640, 360))
        row = [src.copy()]
        cv2.putText(row[0], "src", (8, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 255, 0), 2)
        for stem, tgt in tgts:
            if tgt is None:
                continue
            out = fda(src, tgt, 0.02)
            cv2.putText(out, f"{stem[:7]} b.02", (8, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
            row.append(out)
        # beta 비교 (첫 타겟)
        for beta in (0.02, 0.03):
            out = fda(src, tgts[0][1], beta)
            cv2.putText(out, f"b{beta}", (8, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 255, 0), 2)
            row.append(out)
        rows.append(np.hstack(row))
    cv2.imwrite("/tmp/fda_preview2.jpg", np.vstack(rows), [cv2.IMWRITE_JPEG_QUALITY, 85])
    print("저장 /tmp/fda_preview.jpg")


if __name__ == "__main__":
    main()
