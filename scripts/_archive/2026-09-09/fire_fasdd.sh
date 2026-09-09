#!/bin/bash
# 화재 2단계: FASDD 사전학습 → 24k 미세조정. + FASDD 직접혼합 대조군. 전부 KISA 10편 채점(전체/타일)
set -e
W=/NHNHOME/WORKSPACE/26mss002_E3; G=$W/vms; PY=$W/vms/.venv/bin/python
log(){ echo "[$(date +%H:%M)] $*"; }
while tmux has-session -t rtdetr 2>/dev/null; do sleep 300; done   # GPU 비면

log "FASDD → YOLO 변환"
$PY $G/scripts/fasdd_to_yolo.py

cd $W/vms
: > $G/FIRE_FASDD_SCORES.txt
score(){ # $1 런이름
  { echo "=== $1 전체 ==="; $PY $G/scripts/../..//vms/score_kisa.py $G/runs/$1/weights/best.pt --videos $W/vms/data/원본데이터/kisa_배포_방화채점셋/videos --gt $W/vms/data/원본데이터/kisa_배포_방화채점셋/gt --stride 0.5 --imgsz 640 --tag "$1 전체"
    echo "=== $1 타일 ==="; $PY $W/vms/score_kisa.py $G/runs/$1/weights/best.pt --videos $W/vms/data/원본데이터/kisa_배포_방화채점셋/videos --gt $W/vms/data/원본데이터/kisa_배포_방화채점셋/gt --stride 0.5 --imgsz 640 --tiles --tag "$1 타일"; } >> $G/FIRE_FASDD_SCORES.txt 2>&1
}

# 1) FASDD 사전학습 (11s)
log "1/3 FASDD 사전학습"
$PY model.py train --models yolo11s --data $G/datasets/fasdd_yolo/data.yaml --project $G/runs \
  --device 0 --batch 128 --epochs 60 --imgsz 640 --multi-scale --no-export --force
mv $G/runs/yolo11s $G/runs/fire_fasdd_pre
score fire_fasdd_pre

# 2) FASDD 사전학습 → 우리 24k 미세조정
log "2/3 24k 미세조정"
$PY model.py train --models yolo11s --data $W/datasets/data_24k.yaml --project $G/runs \
  --device 0 --batch 128 --epochs 60 --imgsz 640 --multi-scale --no-export --force \
  --weights $G/runs/fire_fasdd_pre/weights/best.pt 2>/dev/null || \
$PY -c "
from ultralytics import YOLO
m=YOLO('$G/runs/fire_fasdd_pre/weights/best.pt')
m.train(data='$W/datasets/data_24k.yaml', project='$G/runs', name='fire_fasdd_ft', exist_ok=True, device=0, batch=128, epochs=60, imgsz=640, multi_scale=True, plots=False)
"
[ -d $G/runs/yolo11s ] && mv $G/runs/yolo11s $G/runs/fire_fasdd_ft
score fire_fasdd_ft

# 3) 직접 혼합 대조군 (FASDD+24k 합쳐 한 번에)
log "3/3 직접혼합 대조군"
DS=$G/datasets/fire_mix; mkdir -p $DS/images/train $DS/labels/train
cp -asn $G/datasets/fasdd_yolo/images/train/. $DS/images/train/ 2>/dev/null || true
cp -asn $G/datasets/fasdd_yolo/labels/train/. $DS/labels/train/ 2>/dev/null || true
cp -asn $W/datasets/dataset_24k/images/train/. $DS/images/train/ 2>/dev/null || true
cp -asn $W/datasets/dataset_24k/labels/train/. $DS/labels/train/ 2>/dev/null || true
ln -sfn $G/datasets/fasdd_yolo/images/val $DS/images/val
ln -sfn $G/datasets/fasdd_yolo/labels/val $DS/labels/val
printf "path: %s\ntrain: images/train\nval: images/val\nnc: 2\nnames: ['fire','smoke']\n" $DS > $DS/data.yaml
$PY model.py train --models yolo11s --data $DS/data.yaml --project $G/runs \
  --device 0 --batch 128 --epochs 60 --imgsz 640 --multi-scale --no-export --force
mv $G/runs/yolo11s $G/runs/fire_mix
score fire_mix
log "완료"
