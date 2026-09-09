#!/bin/bash
# 방화 시계열: 피처추출(75+10편) → seq 학습 → 배포10 채점
set -e
W=/NHNHOME/WORKSPACE/26mss002_E3
G=$W/vms
PY=$W/vms/.venv/bin/python
log(){ echo "[$(date +%H:%M)] $*"; }
log "1) 방화 시계열 피처 추출 (base 모델, 6뷰+플리커+flow)"
$PY $G/scripts/fire_feats.py --videos "$G/datasets/fire75_raw" "$W/vms/data/원본데이터/kisa_배포_방화채점셋/videos" \
  --model $W/vms/runs/kisa/base/weights/best.pt --out $G/feats/fire_seq
log "2) 시계열 창분류기 학습 + 채점 (fire: SA=onset+10초)"
$PY $G/scripts/seq_train.py --feats $G/feats/fire_seq --dim 20 --deploy-prefix C00_ \
  --sa-delay 10 --out $G/runs/fire_seq > $G/FIRE_SEQ_SCORES.txt 2>&1
cat $G/FIRE_SEQ_SCORES.txt | tail -20
log "전체 완료"
