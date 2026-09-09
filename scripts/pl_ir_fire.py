# -*- coding: utf-8 -*-
"""base 가 못 보는 야간(IR) 방화 영상에 점화 전후 차분으로 fire 약라벨 생성.

원리: 화염 = 점화 후 '새로 생긴' 포화 밝은 블롭. 점화 전 기준 프레임(중앙값)과
비교하면 원래 있던 가로등·조명은 자동 배제된다. YOLO-World(개념 실패)·base(순환)와
달리 물리 프라이어라 base 가 눈먼 도메인에 새 정보를 준다.

1) 야간 9편 중 base+타일이 이벤트 구간에서 fire<0.3 인 '눈먼' 영상만 선별
2) 기준 = 점화 60/40/20초 전 3프레임 중앙값(그레이)
3) 이벤트 프레임: (gray>240) & (ref<200) 블롭 → fire 박스 (상위 2개, 20% 팽창)
4) 라벨 저장 + 미리보기 몽타주 (학습 전 육안 게이트)
"""
import xml.etree.ElementTree as ET
from pathlib import Path

import cv2
import numpy as np
from ultralytics import YOLO

SRC = Path("/NHNHOME/WORKSPACE/26mss002_E3/vms/datasets/fire75_raw")
OUT = Path("/NHNHOME/WORKSPACE/26mss002_E3/vms/datasets/ir_fire_pl")
BASE = "/NHNHOME/WORKSPACE/26mss002_E3/vms/runs/kisa/base/weights/best.pt"


def hms(t):
    h, m, s = (t or "0:0:0").split(":")
    return int(h) * 3600 + int(m) * 60 + int(s)


def read_at(cap, fps, t):
    cap.set(cv2.CAP_PROP_POS_FRAMES, int(t * fps))
    ok, fr = cap.read()
    return fr if ok else None


def base_blind(model, cap, fps, start):
    """이벤트 구간 8프레임 × (전체+중앙타일) 에서 base 최대 fire conf < 0.3 이면 눈먼 영상."""
    best = 0.0
    for dt in range(4, 36, 4):
        fr = read_at(cap, fps, start + dt)
        if fr is None:
            continue
        h, w = fr.shape[:2]
        for crop in (fr, fr[h // 4:3 * h // 4, w // 4:3 * w // 4]):
            r = model.predict(crop, conf=0.10, imgsz=640, verbose=False)[0]
            for b in r.boxes:
                if r.names[int(b.cls)] == "fire":
                    best = max(best, float(b.conf))
    return best < 0.30, best


def new_blobs(gray, ref):
    """새로 생긴 밝은 블롭 (완화판: 미리보기 육안검증 통과 설정)."""
    diff = cv2.absdiff(gray, ref)
    mask = ((gray > 190) & (diff > 60)).astype(np.uint8) * 255
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8))
    n, _, stats, _ = cv2.connectedComponentsWithStats(mask)
    cands = [(s[4], s[0], s[1], s[2], s[3]) for s in stats[1:] if 25 <= s[4] <= 120000]
    boxes = [(x, y, x + w, y + h) for _, x, y, w, h in sorted(cands, reverse=True)[:3]]
    # 가까운 파편 병합 (간격 60px 이내면 합침)
    merged = []
    for b_ in boxes:
        for i, m in enumerate(merged):
            if not (b_[2] + 60 < m[0] or m[2] + 60 < b_[0] or b_[3] + 60 < m[1] or m[3] + 60 < b_[1]):
                merged[i] = (min(m[0], b_[0]), min(m[1], b_[1]), max(m[2], b_[2]), max(m[3], b_[3]))
                break
        else:
            merged.append(b_)
    out = []
    for x1, y1, x2, y2 in merged[:2]:
        dx, dy = int((x2 - x1) * 0.15), int((y2 - y1) * 0.15)
        out.append((max(0, x1 - dx), max(0, y1 - dy), x2 + dx, y2 + dy))
    return out


def main():
    (OUT / "images").mkdir(parents=True, exist_ok=True)
    (OUT / "labels").mkdir(parents=True, exist_ok=True)
    model = YOLO(BASE)
    nights = []
    for x in sorted(SRC.glob("*.xml")):
        r = ET.parse(x).getroot()
        if (r.findtext(".//TimeOfDay") or "").lower().startswith("night"):
            nights.append((x.stem, hms(r.findtext(".//Alarm/StartTime"))))
    print(f"야간 {len(nights)}편")

    tiles = []
    total = 0
    for stem, start in nights:
        cap = cv2.VideoCapture(str(SRC / (stem + ".mp4")))
        fps = cap.get(cv2.CAP_PROP_FPS) or 30
        blind, conf = base_blind(model, cap, fps, start)
        if not blind:
            print(f"  {stem}: base 가 봄(fire {conf:.2f}) → 제외")
            cap.release()
            continue
        refs = [read_at(cap, fps, max(2, start - d)) for d in (60, 40, 20)]
        refs = [cv2.cvtColor(f, cv2.COLOR_BGR2GRAY) for f in refs if f is not None]
        if not refs:
            cap.release()
            continue
        ref = np.median(np.stack(refs), axis=0).astype(np.uint8)
        made = 0
        for dt in range(2, 26, 2):   # 점화 직후만(불이 금방 사그라듦)
            fr = read_at(cap, fps, start + dt)
            if fr is None:
                continue
            boxes = new_blobs(cv2.cvtColor(fr, cv2.COLOR_BGR2GRAY), ref)
            if not boxes:
                continue
            h, w = fr.shape[:2]
            name = f"{stem}_ir{int(start)+dt}"
            cv2.imwrite(str(OUT / "images" / (name + ".jpg")), fr, [cv2.IMWRITE_JPEG_QUALITY, 92])
            (OUT / "labels" / (name + ".txt")).write_text("\n".join(
                f"0 {(x1+x2)/2/w:.6f} {(y1+y2)/2/h:.6f} {(x2-x1)/w:.6f} {(y2-y1)/h:.6f}"
                for x1, y1, x2, y2 in boxes))
            made += 1
            if made in (1, 10, 25):
                vis = fr.copy()
                for x1, y1, x2, y2 in boxes:
                    cv2.rectangle(vis, (x1, y1), (x2, y2), (0, 0, 255), 3)
                cv2.putText(vis, name, (10, 40), cv2.FONT_HERSHEY_SIMPLEX, 1.1, (0, 255, 0), 3)
                tiles.append(cv2.resize(vis, (640, 360)))
        # 배경 네거티브 3장 (점화 전)
        for dt in (10, 40, 70):
            fr = read_at(cap, fps, max(2, start - dt))
            if fr is not None:
                name = f"{stem}_bg{dt}"
                cv2.imwrite(str(OUT / "images" / (name + ".jpg")), fr, [cv2.IMWRITE_JPEG_QUALITY, 92])
                (OUT / "labels" / (name + ".txt")).write_text("")
        cap.release()
        total += made
        print(f"  {stem}: 라벨 {made}장 (base blind)", flush=True)
    if tiles:
        rows = [np.hstack(tiles[i:i + 2]) for i in range(0, len(tiles) - 1, 2)] or [np.hstack(tiles + tiles)]
        cv2.imwrite("/tmp/ir_pl_preview.jpg", np.vstack(rows), [cv2.IMWRITE_JPEG_QUALITY, 85])
    print(f"합계 {total}장, 미리보기 /tmp/ir_pl_preview.jpg")


if __name__ == "__main__":
    main()
