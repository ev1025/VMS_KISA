#!/bin/bash
W=/NHNHOME/WORKSPACE/26mss002_E3; G=$W/vms; PY=$W/vms/.venv/bin/python
log(){ echo "[$(date +%m-%d\ %H:%M)] $*"; }
wait_gpu(){ while pgrep -f "model.py train|fall_seq_v2.py|fire_kfold.py" >/dev/null; do sleep 180; done; }

# D. 24k 혼합 비율 스윕 (0% = 손라벨만)
wait_gpu; log "D: 24k 비율 스윕"
$PY $G/scripts/fire_matrix2.py ratio > $G/FIRE_RATIO.txt 2>&1
log "D 완료"

# E. 장소 단위 홀드아웃 (Leave-One-Location-Out)
wait_gpu; log "E: 장소 홀드아웃"
$PY $G/scripts/fire_matrix2.py loo > $G/FIRE_LOO.txt 2>&1
log "E 완료"
log "확장 매트릭스 종료"
