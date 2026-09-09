#!/bin/bash
# person v2: 자체 의사라벨 + COCO person 혼합 → 학습 → 침입 채점 → 배회/쓰러짐 덤프
set -e
W=/NHNHOME/WORKSPACE/26mss002_E3
G=$W/vms
PY=$W/vms/.venv/bin/python
log(){ echo "[$(date +%H:%M)] $*"; }

log "1) COCO2017 다운로드"
mkdir -p $G/datasets/coco_dl && cd $G/datasets/coco_dl
[ -f train2017.zip ] || wget -q http://images.cocodataset.org/zips/train2017.zip
[ -f coco2017labels.zip ] || wget -q https://github.com/ultralytics/assets/releases/download/v0.0.0/coco2017labels.zip
[ -d train2017 ] || unzip -q train2017.zip
[ -d coco ] || unzip -q coco2017labels.zip
log "다운로드·해제 완료"

log "2) COCO person 부분집합 (12k + 배경 2k)"
$PY $G/scripts/build_coco_person.py --images $G/datasets/coco_dl/train2017 \
  --labels $G/datasets/coco_dl/coco/labels/train2017 --out $G/datasets/coco_person

log "3) person_v2 데이터셋 조립"
DS=$G/datasets/person_v2
mkdir -p $DS/images/train $DS/labels/train
cp -al $G/datasets/person_pl/images/train/. $DS/images/train/
cp -al $G/datasets/person_pl/labels/train/. $DS/labels/train/
cp -al $G/datasets/coco_person/images/. $DS/images/train/
cp -al $G/datasets/coco_person/labels/. $DS/labels/train/
ln -sfn $G/datasets/person_pl/images/val $DS/images/val
ln -sfn $G/datasets/person_pl/labels/val $DS/labels/val
printf "path: %s\ntrain: images/train\nval: images/val\nnc: 1\nnames: ['person']\n" $DS > $DS/data.yaml
echo "train: $(ls $DS/images/train | wc -l)장"

log "4) yolo11s 학습"
cd $W/vms
$PY model.py train --models yolo11s --data $DS/data.yaml --project $G/runs \
  --device 0 --batch 128 --epochs 60 --imgsz 640 --multi-scale --no-export
mv $G/runs/yolo11s $G/runs/person_v2

log "5) 침입 30편 채점 (몸전체 규칙, v1 대조)"
VAL="$G/datasets/deploy_val/침입(30개)/배포"
{
  $PY $G/scripts/score_intrusion.py $G/runs/person_v1/weights/best.pt --videos "$VAL" --maps $G/datasets/zone_maps --conf 0.30 --tag "v1"
  $PY $G/scripts/score_intrusion.py $G/runs/person_v2/weights/best.pt --videos "$VAL" --maps $G/datasets/zone_maps --conf 0.30 --tag "v2"
} > $G/PERSON_V2_SCORES.txt 2>&1

log "6) 배회·쓰러짐 v2 덤프"
$PY $G/scripts/server_pdump.py --videos "$G/datasets/deploy_val/배회(30개)/배포" --model $G/runs/person_v2/weights/best.pt --out $G/dumps/loiter_v2
$PY $G/scripts/server_pdump.py --videos "$G/datasets/deploy_val/쓰러짐(10개)/배포" --model $G/runs/person_v2/weights/best.pt --out $G/dumps/fall_v2
log "전체 완료"
