#!/bin/bash
# FDA 48k 생성(CPU, 즉시) → g20d1 종료 대기 → YOLO11x 학습 → KISA 채점 (교사=최종 배포, KD 생략)
set -e
W=/NHNHOME/WORKSPACE/26mss002_E3
G=$W/vms
PY=$W/vms/.venv/bin/python
log(){ echo "[$(date +%H:%M)] $*"; }

log "1) FDA 48k 생성 (CPU)"
CUDA_VISIBLE_DEVICES=-1 $PY $G/scripts/fda_build.py

log "2) GPU 대기 (g20d1 종료까지)"
while tmux has-session -t g20d1 2>/dev/null; do sleep 300; done

log "3) YOLO11x 학습 (FDA 48k, multi_scale)"
cd $W/vms
$PY model.py train --models yolo11x --data $G/datasets/fire_fda48k/data.yaml --project $G/runs \
  --device 0 --batch 64 --epochs 60 --imgsz 640 --multi-scale --no-export
mv $G/runs/yolo11x $G/runs/fire_fda_x

log "4) KISA 10편 채점 (전체/타일)"
{
  $PY $W/vms/score_kisa.py $G/runs/fire_fda_x/weights/best.pt --videos $W/vms/data/원본데이터/kisa_배포_방화채점셋/videos --gt $W/vms/data/원본데이터/kisa_배포_방화채점셋/gt --stride 0.5 --tag "fda_x 전체"
  $PY $W/vms/score_kisa.py $G/runs/fire_fda_x/weights/best.pt --videos $W/vms/data/원본데이터/kisa_배포_방화채점셋/videos --gt $W/vms/data/원본데이터/kisa_배포_방화채점셋/gt --stride 0.5 --tiles --tag "fda_x 타일"
} > $G/FIRE_FDA_SCORES.txt 2>&1
log "전체 완료"
