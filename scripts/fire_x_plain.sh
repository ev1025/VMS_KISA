#!/bin/bash
set -e
W=/NHNHOME/WORKSPACE/26mss002_E3
G=$W/vms
PY=$W/vms/.venv/bin/python
log(){ echo "[$(date +%H:%M)] $*"; }
log "g20fall 종료 대기"
while tmux has-session -t g20fall 2>/dev/null; do sleep 300; done
log "yolo11x 순수 24k 학습 (FDA 효과 분리용 대조군)"
cd $W/vms
$PY model.py train --models yolo11x --data $W/datasets/data_24k.yaml --project $G/runs \
  --device 0 --batch 64 --epochs 60 --imgsz 640 --multi-scale --no-export --force
mv $G/runs/yolo11x $G/runs/fire_x_plain
{
  $PY $W/vms/score_kisa.py $G/runs/fire_x_plain/weights/best.pt --videos $W/vms/data/원본데이터/kisa_배포_방화채점셋/videos --gt $W/vms/data/원본데이터/kisa_배포_방화채점셋/gt --stride 0.5 --tag "x_plain 전체"
  $PY $W/vms/score_kisa.py $G/runs/fire_x_plain/weights/best.pt --videos $W/vms/data/원본데이터/kisa_배포_방화채점셋/videos --gt $W/vms/data/원본데이터/kisa_배포_방화채점셋/gt --stride 0.5 --tiles --tag "x_plain 타일"
} > $G/FIRE_XPLAIN_SCORES.txt 2>&1
log "전체 완료"
