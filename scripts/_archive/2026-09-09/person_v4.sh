#!/bin/bash
set -e
W=/NHNHOME/WORKSPACE/26mss002_E3; G=$W/vms; PY=$W/vms/.venv/bin/python
log(){ echo "[$(date +%H:%M)] $*"; }
# 방화 그리드 뒤 (GPU 독점 피함)
while tmux has-session -t firegrid 2>/dev/null; do sleep 300; done

log "1) AI허브 침입 국내 의사라벨 (x교사, GT창만)"
$PY $G/scripts/pl_person.py --videos $G/datasets/aihub/침입 --out $G/datasets/aihub_int_pl --sample-s 5 --cap 30

N=$(ls $G/datasets/aihub_int_pl/images/train 2>/dev/null | wc -l)
log "국내 침입 라벨 $N 장"
if [ "$N" -lt 100 ]; then log "라벨 부족 - 중단"; exit 0; fi

log "2) person_v4 = person_v2 + 국내 침입"
DS=$G/datasets/person_v4
mkdir -p $DS/images/train $DS/labels/train
cp -al $G/datasets/person_v2/images/train/. $DS/images/train/ 2>/dev/null || cp -rl $G/datasets/person_v2/images/train/. $DS/images/train/
cp -al $G/datasets/person_v2/labels/train/. $DS/labels/train/ 2>/dev/null || cp -rl $G/datasets/person_v2/labels/train/. $DS/labels/train/
cp -al $G/datasets/aihub_int_pl/images/train/. $DS/images/train/ 2>/dev/null || true
cp -al $G/datasets/aihub_int_pl/labels/train/. $DS/labels/train/ 2>/dev/null || true
ln -sfn $G/datasets/person_pl/images/val $DS/images/val
ln -sfn $G/datasets/person_pl/labels/val $DS/labels/val
printf "path: %s\ntrain: images/train\nval: images/val\nnc: 1\nnames: ['person']\n" $DS > $DS/data.yaml
echo "train: $(ls $DS/images/train | wc -l)장"

log "3) yolo11s 학습"
cd $W/vms
$PY model.py train --models yolo11s --data $DS/data.yaml --project $G/runs \
  --device 0 --batch 128 --epochs 60 --imgsz 640 --multi-scale --no-export --force
mv $G/runs/yolo11s $G/runs/person_v4

log "4) 침입/배회 덤프 (v4)"
M=$G/runs/person_v4/weights/best.pt
$PY $G/scripts/server_pdump.py --videos "$G/datasets/deploy_val/침입(30개)/배포" --model $M --out $G/dumps/intrusion_v4
$PY $G/scripts/server_pdump.py --videos "$G/datasets/deploy_val/배회(30개)/배포" --model $M --out $G/dumps/loiter_v4
log "전체 완료"
