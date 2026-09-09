# -*- coding: utf-8 -*-
"""어려운 배경 3종의 학습용 목록을 만든다: 흰연기 · 해변모래(밝은 저채도) · 설경.

왜 이 셋인가 (실측 근거):
  배포 미검 2편이 짙은 안개와 설경이었고, 둘 다 공통점이 "화면 대부분이 밝고 채도가 낮다"이다.
  이런 장면에서 모델은 배경 전체를 연기로 오인해 연기 신뢰도가 영상 내내 0.92로 고정된다.
  같은 성질의 학습 표본을 모아 오버샘플하면 이 오인을 줄일 수 있는지 본다.
  - 흰연기: 24k 실내 화재의 흰 연기 장면 (이미 라벨 있음)
  - 해변모래: 연구개발 방화 15편의 밝은 모래·흐린 하늘 배경 (손라벨 있음)
  - 설경: FASDD 에서 푸른기 조건으로 고른 눈 장면 (라벨 있음)
출력은 이미지 경로 목록 txt. 학습셋 조립은 목록을 이어붙이기만 하면 된다(심링크보다 훨씬 빠름).
"""
import collections
import glob
import json
import os
from pathlib import Path

G = Path("/NHNHOME/WORKSPACE/26mss002_E3/vms")
OUT = G / "data/학습데이터/_hard"
OUT.mkdir(parents=True, exist_ok=True)

# 밝은 모래·흐린 하늘 배경으로 확인된 연구개발 방화 클립 (HSV 통계 + 육안 확인)
BEACH = ["C052105_001", "C052105_004", "C054305_001", "C054305_003", "C054305_004",
         "C054305_005", "C055105_003", "C055205_002", "C055205_003", "C055305_002",
         "C055305_003", "C058105_001", "C058105_004", "C058205_004", "C055205_003"]


def write(name, paths):
    paths = [p for p in paths if p]
    (OUT / f"{name}.txt").write_text("\n".join(paths) + "\n")
    print(f"  {name}: {len(paths)}장")
    return len(paths)


def main():
    # 1) 흰연기: 24k 중 밝고 저채도로 걸러둔 목록 (snowfog_24k.json 의 snow 항목 = 실측상 전부 흰연기였다)
    sf = json.load(open(G / "data/학습데이터/snowfog_24k.json"))
    im24 = G / "data/학습데이터/dataset_24k/images/train"
    white = [str(im24 / n) for n in sf["snow"] if (im24 / n).exists()]
    fog24 = [str(im24 / n) for n in sf["fog"] if (im24 / n).exists()]
    write("white_smoke", white)
    write("haze24k", fog24)

    # 2) 해변모래: 손라벨에서 만든 human_fire 는 클립명이 파일명에 남아 있다
    hf = G / "data/학습데이터/human_fire/images/train"
    allf = sorted(os.listdir(hf))
    beach = [str(hf / f) for f in allf if any(f.startswith(c) for c in BEACH)]
    if not beach:
        # 파일명 규칙이 다르면 클립명이 포함되기만 해도 채택
        beach = [str(hf / f) for f in allf if any(c in f for c in BEACH)]
    write("beach_sand", beach)

    # 3) 설경: FASDD 푸른기 조건으로 고른 것
    snow = sorted(glob.glob(str(G / "data/학습데이터/fasdd_snow2/images/train/*")))
    write("snow_fasdd", snow)

    # 4) FASDD 전체 / 불있는것 / 정상(빈라벨=하드네거티브)
    fa = G / "data/학습데이터/fasdd_yolo"
    imgs = sorted(glob.glob(str(fa / "images/train/*")))
    with_fire, with_smoke, neg = [], [], []
    for p in imgs:
        lb = fa / "labels/train" / (Path(p).stem + ".txt")
        if not lb.exists():
            continue
        cls = {l.split()[0] for l in lb.read_text().splitlines() if l.strip()}
        if not cls:
            neg.append(p)
        else:
            if "0" in cls:
                with_fire.append(p)
            if "1" in cls:
                with_smoke.append(p)
    write("fasdd_all", imgs)
    write("fasdd_fire", with_fire)
    write("fasdd_smoke", with_smoke)
    write("fasdd_neg", neg)

    # 5) 작은 박스만 (배포 도메인은 불이 작다: C00_216 은 화면의 0.0012)
    small = []
    for p in with_fire:
        lb = fa / "labels/train" / (Path(p).stem + ".txt")
        a = [float(l.split()[3]) * float(l.split()[4]) for l in lb.read_text().splitlines()
             if l.strip() and l.split()[0] == "0"]
        if a and min(a) <= 0.01:
            small.append(p)
    write("fasdd_smallfire", small)

    print(f"\n목록 저장 → {OUT}")


if __name__ == "__main__":
    main()
