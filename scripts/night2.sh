#!/bin/bash
# 밤샘 2단계: 남은 모델 전부의 신호 시계열을 저장 → 새 규칙(짧은 창 2회, 낮은 임계)으로 일괄 재채점.
# 오늘 확인한 것: 규칙만 바꿔도 pilot 75.0 → 77.8. 시계열을 저장해두면 규칙 스윕은 추론 없이 즉시 반복 가능.
W=/NHNHOME/WORKSPACE/26mss002_E3; G=$W/vms; PY=$W/vms/.venv/bin/python
export OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=1
log(){ echo "[$(date +%m-%d\ %H:%M)] $*"; }
while [ ! -f $G/results/par/detail.done ]; do sleep 60; done
for n in ov3 ov20 synth_mix human_only; do
  [ -f $G/results/par/tl/$n.json ] && continue
  [ -f $G/runs/par/$n/yolo11s/weights/best.pt ] || continue
  log "시계열 $n"
  $PY $G/scripts/fire_detail.py $G/runs/par/$n/yolo11s/weights/best.pt --tag $n --tiles > $G/results/par/DETAIL_$n.txt 2>&1
done
log "전체 시계열 완료"
{ for f in $G/results/par/tl/*.json; do n=$(basename $f .json); echo "########## $n"; $PY $G/scripts/fire_rule2.py $n 2>&1 | sed -n '/규칙 스윕/,$p'; done; } > $G/results/par/RULE2_ALL.txt 2>&1
log "새 규칙 일괄 채점 완료 → results/par/RULE2_ALL.txt"
