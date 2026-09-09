#!/bin/bash
# 방화 해상도×버전 그리드: {11n,11s,11m,11l}×{640,960} on 24k, 각 whole/tiles 채점
set -e
W=/NHNHOME/WORKSPACE/26mss002_E3; G=$W/vms; PY=$W/vms/.venv/bin/python
log(){ echo "[$(date +%H:%M)] $*"; }
while tmux has-session -t ablation 2>/dev/null; do sleep 180; done   # ablation 뒤

: > $G/FIRE_GRID_SCORES.txt
cd $W/vms
for M in yolo11n yolo11s yolo11m yolo11l; do
  for SZ in 640 960; do
    NAME=grid_${M}_${SZ}
    [ -f $G/runs/$NAME/weights/best.pt ] && { log "$NAME 있음, 건너뜀"; continue; }
    B=128; [ $SZ -ge 960 ] && B=64
    [ "$M" = "yolo11l" ] && [ $SZ -ge 960 ] && B=48
    log "$NAME 학습 (batch $B)"
    $PY model.py train --models $M --data $W/datasets/data_24k.yaml --project $G/runs \
      --device 0 --batch $B --epochs 100 --imgsz $SZ --multi-scale --no-export --force
    mv $G/runs/$M $G/runs/$NAME
    {
      echo "=== $NAME ==="
      $PY $W/vms/score_kisa.py $G/runs/$NAME/weights/best.pt --videos $W/vms/data/원본데이터/kisa_배포_방화채점셋/videos --gt $W/vms/data/원본데이터/kisa_배포_방화채점셋/gt --stride 0.5 --imgsz $SZ --tag "$NAME 전체"
      $PY $W/vms/score_kisa.py $G/runs/$NAME/weights/best.pt --videos $W/vms/data/원본데이터/kisa_배포_방화채점셋/videos --gt $W/vms/data/원본데이터/kisa_배포_방화채점셋/gt --stride 0.5 --imgsz $SZ --tiles --tag "$NAME 타일"
    } >> $G/FIRE_GRID_SCORES.txt 2>&1
    log "$NAME 채점 완료"
  done
done
log "그리드 전체 완료"
