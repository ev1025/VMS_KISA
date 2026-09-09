#!/bin/bash
W=/NHNHOME/WORKSPACE/26mss002_E3
R=$W/vms
PY=$R/.venv/bin/python
V="/NHNHOME/WORKSPACE/26mss002_E3/vms/data/원본데이터/kisa_배포_검증영상/deploy_val/방화(10개)/배포"
G="/NHNHOME/WORKSPACE/26mss002_E3/vms/data/원본데이터/kisa_배포_검증영상/deploy_val/방화(10개)/배포"
OUT=$R/results/KISA_SCORES.txt
echo "채점 워처 시작 $(date)" > $OUT
for run in base aug20 aug40; do
  echo "[$(date +%H:%M)] $run best.pt 대기..." >> $OUT
  while [ ! -f $R/runs/kisa/$run/weights/best.pt ]; do sleep 120; done
  sleep 30   # 파일 쓰기 완료 여유
  echo "[$(date +%H:%M)] $run 채점 시작" >> $OUT
  $PY $R/score_kisa.py $R/runs/kisa/$run/weights/best.pt --videos "$V" --gt "$G" --stride 0.5 --tag "$run 전체" >> $OUT 2>&1
  $PY $R/score_kisa.py $R/runs/kisa/$run/weights/best.pt --videos "$V" --gt "$G" --stride 0.5 --tiles --tag "$run 타일" >> $OUT 2>&1
  echo "----" >> $OUT
done
echo "전체 채점 완료 $(date)" >> $OUT
