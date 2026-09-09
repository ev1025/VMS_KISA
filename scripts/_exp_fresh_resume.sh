#!/bin/bash
# 고아가 된 base 학습(runs/yolo11s)을 이어받는다: 끝날 때까지 대기 → 채점 → 나머지 fresh 실험 이어서.
V=/NHNHOME/WORKSPACE/26mss002_E3/vms; PY=$V/.venv/bin/python
BAE="$V/data/원본데이터/kisa_배포_검증영상/deploy_val/방화(10개)/배포"
NAME=fresh_48k_base_20260909
BASE_PID=2635714
log(){ echo "[$(date +%m-%d\ %H:%M)] $*"; }

log "고아 base 학습(PID $BASE_PID) 종료 대기"
while kill -0 "$BASE_PID" 2>/dev/null; do sleep 60; done
log "base 학습 종료 감지"

if [ -f "$V/runs/yolo11s/weights/best.pt" ] && [ ! -s "$V/results/$NAME.txt" ]; then
  [ -d "$V/runs/$NAME" ] || mv "$V/runs/yolo11s" "$V/runs/$NAME"
  log "base 채점 시작"
  { echo "=== $NAME 타일 ==="; $PY $V/score_kisa.py $V/runs/$NAME/weights/best.pt --videos "$BAE" --gt "$BAE" --stride 0.5 --imgsz 640 --tiles --tag "$NAME"; } > $V/results/$NAME.txt 2>&1
  rm -rf $V/data/학습데이터/mix_fresh_48k_base_20260909
  log "base 완료 → results/$NAME.txt"
else
  log "base best.pt 없음 또는 이미 채점됨 → 건너뜀"
fi

log "나머지 fresh 실험 이어서(_exp_fresh.sh, base 는 결과존재로 스킵)"
bash $V/scripts/_exp_fresh.sh
log "RESUME FRESH QUEUE DONE"
