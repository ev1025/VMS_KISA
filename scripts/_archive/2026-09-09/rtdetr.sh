#!/bin/bash
# RT-DETR-L 화재 탐지기: 학습 → KISA 10편 채점(전체/타일). base 66.7 대비
set -e
W=/NHNHOME/WORKSPACE/26mss002_E3; G=$W/vms; PY=$W/vms/.venv/bin/python
log(){ echo "[$(date +%H:%M)] $*"; }
log "RT-DETR 학습 시작"
cd $G/runs && $PY $G/scripts/rtdetr_train.py $W/datasets/data_24k.yaml $G/runs fire_rtdetr_l
M=$G/runs/fire_rtdetr_l/weights/best.pt
: > $G/FIRE_RTDETR_SCORES.txt
{
  echo "=== fire_rtdetr_l 전체 ==="; $PY $W/vms/score_kisa.py $M --videos $W/vms/data/원본데이터/kisa_배포_방화채점셋/videos --gt $W/vms/data/원본데이터/kisa_배포_방화채점셋/gt --stride 0.5 --imgsz 640 --tag "rtdetr 전체"
  echo "=== fire_rtdetr_l 타일 ==="; $PY $W/vms/score_kisa.py $M --videos $W/vms/data/원본데이터/kisa_배포_방화채점셋/videos --gt $W/vms/data/원본데이터/kisa_배포_방화채점셋/gt --stride 0.5 --imgsz 640 --tiles --tag "rtdetr 타일"
} >> $G/FIRE_RTDETR_SCORES.txt 2>&1
log "완료"
