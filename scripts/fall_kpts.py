# -*- coding: utf-8 -*-
"""PoseC3D 용 조밀 다인 원시 키포인트 추출. 기존 59차원(top-1 정규화)과 달리
   stride 0.1s, 최대 5인, 절대 픽셀 좌표 저장 → 폐색·원거리에서 저신뢰 인물도 보존."""
import argparse, xml.etree.ElementTree as ET
from pathlib import Path
import cv2, numpy as np
from ultralytics import YOLO


def hms(t):
    h, m, s = (t or "0:0:0").split(":"); return int(h) * 3600 + int(m) * 60 + int(s)


def gt_info(xml):
    try:
        al = ET.parse(xml).getroot().find(".//Alarm")
        return (hms(al.findtext("StartTime")), hms(al.findtext("AlarmDuration")) or 10) if al is not None else (None, None)
    except Exception:
        return None, None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--videos", required=True, nargs="+")
    ap.add_argument("--out", required=True)
    ap.add_argument("--stride", type=float, default=0.1)   # 10fps
    ap.add_argument("--maxp", type=int, default=5)
    a = ap.parse_args()
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    model = YOLO("yolo11x-pose.pt")
    vids = []
    for d in a.videos:
        vids += sorted(Path(d).rglob("*.mp4"))
    for order, mp4 in enumerate(vids, 1):
        dst = out / (mp4.stem + ".npz")
        if dst.exists():
            continue
        start, dur = gt_info(mp4.with_suffix(".xml"))
        cap = cv2.VideoCapture(str(mp4)); fps = cap.get(cv2.CAP_PROP_FPS) or 30
        step = max(1, round(fps * a.stride)); i = 0; ts = []; kseq = []; WH = None
        while True:
            if not cap.grab(): break
            if i % step == 0:
                ok, fr = cap.retrieve()
                if ok:
                    if WH is None: WH = (fr.shape[1], fr.shape[0])
                    r = model.predict(fr, conf=0.10, imgsz=640, verbose=False)[0]
                    fr_k = np.zeros((a.maxp, 17, 3), np.float32)
                    if r.keypoints is not None and len(r.boxes):
                        confs = [float(b.conf) for b in r.boxes]
                        idx = np.argsort(confs)[::-1][:a.maxp]        # 신뢰도 상위 maxp
                        kp = r.keypoints.data.cpu().numpy()           # (n,17,3) 절대px
                        for j, id_ in enumerate(idx):
                            fr_k[j] = kp[id_]
                    ts.append(i / fps); kseq.append(fr_k)
            i += 1
        cap.release()
        np.savez_compressed(dst, t=np.array(ts, np.float32),
                            kpts=np.stack(kseq) if kseq else np.zeros((0, a.maxp, 17, 3), np.float32),
                            wh=np.array(WH or (0, 0), np.int32),
                            gt_start=-1.0 if start is None else float(start),
                            gt_dur=0.0 if dur is None else float(dur))
        if order % 20 == 0 or order == len(vids):
            print(f"[{order}/{len(vids)}] {mp4.stem} 표본 {len(ts)}", flush=True)
    print("완료")


if __name__ == "__main__":
    main()
