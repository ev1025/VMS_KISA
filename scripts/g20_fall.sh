#!/bin/bash
# 큐 3번: fda_x 종료 대기 → 쓰러짐 시계열 모델 학습 + 배포 10편 로짓/임계 스윕
set -e
W=/NHNHOME/WORKSPACE/26mss002_E3
G=$W/vms
PY=$W/vms/.venv/bin/python
log(){ echo "[$(date +%H:%M)] $*"; }
log "fda_x 종료 대기"
while tmux has-session -t fda_x 2>/dev/null; do sleep 300; done
log "쓰러짐 시계열 학습 시작"
$PY $G/scripts/fall_seq_train.py > $G/FALL_SEQ_SCORES.txt 2>&1
log "전체 완료"
