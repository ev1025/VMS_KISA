#!/bin/bash
# fire_v4: AI산불 업로드 대기 → base+타일 의사라벨(품질필터+상한) → 24k+AI 학습 → KISA 채점
set -e
W=/NHNHOME/WORKSPACE/26mss002_E3
G=$W/vms
PY=$W/vms/.venv/bin/python
log(){ echo "[$(date +%H:%M)] $*"; }

log "AI산불 업로드 대기..."
while [ ! -f $G/datasets/ai_fire/UPLOAD_DONE ]; do sleep 600; done
log "도착. 의사라벨 생성 (몇 시간 소요)"
IMGROOT=$(find $G/datasets/ai_fire -type d -name 'KISA_image_9500' | head -1)
$PY $G/scripts/pl_ai_fire.py --images "$IMGROOT" \
  --model $W/vms/runs/kisa/base/weights/best.pt --out $G/datasets/ai_fire_pl

N=$(ls $G/datasets/ai_fire_pl/labels/*.txt 2>/dev/null | wc -l)
log "라벨 $N 장"
if [ "$N" -lt 300 ]; then log "라벨 부족 - 중단"; exit 0; fi

log "미리보기 몽타주 생성 (육안 게이트용)"
$PY - <<'PYEOF'
import cv2, random, numpy as np
from pathlib import Path
random.seed(1)
src = Path("/NHNHOME/WORKSPACE/26mss002_E3/vms/datasets/ai_fire_pl")
picks = random.sample(sorted(src.glob("labels/*.txt")), 8)
tiles = []
for lb in picks:
    img = cv2.imread(str(src / "images" / (lb.stem + ".jpg")))
    h, w = img.shape[:2]
    for line in lb.read_text().splitlines():
        c, cx, cy, bw, bh = map(float, line.split())
        cv2.rectangle(img, (int((cx-bw/2)*w), int((cy-bh/2)*h)), (int((cx+bw/2)*w), int((cy+bh/2)*h)),
                      (0,0,255) if c==0 else (255,200,0), 3)
    tiles.append(cv2.resize(img, (640, 400)))
rows = [np.hstack(tiles[i:i+2]) for i in range(0, 8, 2)]
cv2.imwrite("/tmp/ai_pl_preview.jpg", np.vstack(rows), [cv2.IMWRITE_JPEG_QUALITY, 85])
print("미리보기 저장")
PYEOF

log "fire_v4 데이터셋 = 24k + AI산불 라벨"
DS=$G/datasets/fire_v4
mkdir -p $DS/images/train $DS/labels/train
cp -al $W/datasets/dataset_24k/images/train/. $DS/images/train/
cp -al $W/datasets/dataset_24k/labels/train/. $DS/labels/train/
cp -al $G/datasets/ai_fire_pl/images/. $DS/images/train/
cp -al $G/datasets/ai_fire_pl/labels/. $DS/labels/train/
ln -sfn $W/datasets/dataset_24k/images/val $DS/images/val
ln -sfn $W/datasets/dataset_24k/labels/val $DS/labels/val
printf "path: %s\ntrain: images/train\nval: images/val\nnc: 2\nnames: ['fire', 'smoke']\n" $DS > $DS/data.yaml

log "학습"
cd $W/vms
$PY model.py train --models yolo11s --data $DS/data.yaml --project $G/runs \
  --device 0 --batch 128 --epochs 100 --imgsz 640 --multi-scale --no-export
mv $G/runs/yolo11s $G/runs/fire_v4

log "KISA 채점"
{
  $PY $W/vms/score_kisa.py $G/runs/fire_v4/weights/best.pt --videos $W/vms/data/원본데이터/kisa_배포_방화채점셋/videos --gt $W/vms/data/원본데이터/kisa_배포_방화채점셋/gt --stride 0.5 --tag "fire_v4 전체"
  $PY $W/vms/score_kisa.py $G/runs/fire_v4/weights/best.pt --videos $W/vms/data/원본데이터/kisa_배포_방화채점셋/videos --gt $W/vms/data/원본데이터/kisa_배포_방화채점셋/gt --stride 0.5 --tiles --tag "fire_v4 타일"
} > $G/FIRE_V4_SCORES.txt 2>&1
log "전체 완료"
