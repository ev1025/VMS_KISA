#!/bin/bash
W=/NHNHOME/WORKSPACE/26mss002_E3; G=$W/vms; PY=$W/vms/.venv/bin/python
# 신호추출 끝날 때까지 대기
while pgrep -f fire_sig.py > /dev/null; do sleep 60; done
[ -f $G/fire_sig_train.json ] || { echo "신호파일 없음, 중단"; exit 1; }
echo "[$(date +%H:%M)] 온셋 분류기 학습·평가"
$PY $G/scripts/fire_onset_ml.py > $G/FIRE_ONSET_ML.txt 2>&1
echo "[$(date +%H:%M)] 완료"
