#!/bin/bash
# person v1 체인: 825편 의사라벨(x+타일 교사) → yolo11s 파인튜닝 → 침입30 채점
set -e
W=/NHNHOME/WORKSPACE/26mss002_E3
G=$W/vms
PY=$W/vms/.venv/bin/python
VAL="$G/datasets/deploy_val/침입(30개)/배포"
log(){ echo "[$(date +%H:%M)] $*"; }

log "1) 의사라벨 825편 (교사 yolo11x+타일)"
$PY $G/scripts/pl_person.py --videos $G/datasets/rnd_person --out $G/datasets/person_pl
echo "train: $(ls $G/datasets/person_pl/images/train | wc -l) · val: $(ls $G/datasets/person_pl/images/val | wc -l)"

log "2) yolo11s 파인튜닝 (nc=1 person)"
cd $W/vms
$PY model.py train --models yolo11s --data $G/datasets/person_pl/data.yaml --project $G/runs \
  --device 0 --batch 128 --epochs 60 --imgsz 640 --multi-scale --no-export
mv $G/runs/yolo11s $G/runs/person_v1

log "3) 침입 30편 채점 (기준선 m 포함, 전체/타일)"
{
  echo "== 기준선 yolo11m 타일 (로컬 52.63 재현 확인용) =="
  $PY $G/scripts/score_intrusion.py yolo11m.pt --videos "$VAL" --maps $G/datasets/zone_maps --conf 0.35 --tiles --tag "m+타일"
  echo "== person_v1 전체 =="
  $PY $G/scripts/score_intrusion.py $G/runs/person_v1/weights/best.pt --videos "$VAL" --maps $G/datasets/zone_maps --conf 0.40 --tag "v1 전체"
  echo "== person_v1 타일 =="
  $PY $G/scripts/score_intrusion.py $G/runs/person_v1/weights/best.pt --videos "$VAL" --maps $G/datasets/zone_maps --conf 0.40 --tiles --tag "v1 타일"
} > $G/PERSON_V1_SCORES.txt 2>&1
log "완료"
