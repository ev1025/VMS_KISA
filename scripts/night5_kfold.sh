#!/bin/bash
# FASDD 5-fold: night4 매트릭스가 끝난 뒤 실행 (GPU 경합 방지)
W=/NHNHOME/WORKSPACE/26mss002_E3; G=$W/vms; PY=$W/vms/.venv/bin/python
export OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=1
while pgrep -f "night4_fasdd.sh|night3_snowfog.sh" >/dev/null; do sleep 180; done
echo "[$(date +%m-%d\ %H:%M)] FASDD 5-fold 시작"
$PY $G/scripts/fasdd_kfold.py 50 > $G/results/par/KFOLD_FASDD.txt 2>&1
echo "[$(date +%m-%d\ %H:%M)] 완료"; tail -12 $G/results/par/KFOLD_FASDD.txt
