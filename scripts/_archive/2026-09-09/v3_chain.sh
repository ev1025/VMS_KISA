#!/bin/bash
# 통합 체인: 쓰러짐 0.5s 정밀 kpt 덤프 → 야간 트랙라벨 → person_v3 학습 → 3항목 덤프
set -e
W=/NHNHOME/WORKSPACE/26mss002_E3
G=$W/vms
PY=$W/vms/.venv/bin/python
log(){ echo "[$(date +%H:%M)] $*"; }

log "1) 쓰러짐 x-pose 0.5초 정밀 덤프"
$PY $G/scripts/server_kptdump.py --videos "$G/datasets/deploy_val/쓰러짐(10개)/배포" \
  --model yolo11x-pose.pt --out $G/dumps/fall_xpose05 --stride 0.5

log "2) 야간 트랙 검증 라벨 (rnd_person 야간분)"
$PY $G/scripts/pl_person_track.py --videos $G/datasets/rnd_person --out $G/datasets/night_track_pl

N=$(ls $G/datasets/night_track_pl/labels/*.txt 2>/dev/null | wc -l)
log "야간 트랙 라벨 $N 장"
if [ "$N" -lt 100 ]; then log "라벨 부족 - v3 학습 건너뜀"; log "전체 완료"; exit 0; fi

log "3) person_v3 = person_v2 데이터 + 야간 트랙 라벨"
DS=$G/datasets/person_v3
mkdir -p $DS/images/train $DS/labels/train
cp -al $G/datasets/person_v2/images/train/. $DS/images/train/
cp -al $G/datasets/person_v2/labels/train/. $DS/labels/train/
cp -al $G/datasets/night_track_pl/images/. $DS/images/train/
cp -al $G/datasets/night_track_pl/labels/. $DS/labels/train/
ln -sfn $G/datasets/person_pl/images/val $DS/images/val
ln -sfn $G/datasets/person_pl/labels/val $DS/labels/val
printf "path: %s\ntrain: images/train\nval: images/val\nnc: 1\nnames: ['person']\n" $DS > $DS/data.yaml
echo "train: $(ls $DS/images/train | wc -l)장"

cd $W/vms
$PY model.py train --models yolo11s --data $DS/data.yaml --project $G/runs \
  --device 0 --batch 128 --epochs 60 --imgsz 640 --multi-scale --no-export
mv $G/runs/yolo11s $G/runs/person_v3

log "4) 침입/배회 v3 덤프"
M=$G/runs/person_v3/weights/best.pt
$PY $G/scripts/server_pdump.py --videos "$G/datasets/deploy_val/침입(30개)/배포" --model $M --out $G/dumps/intrusion_v3
$PY $G/scripts/server_pdump.py --videos "$G/datasets/deploy_val/배회(30개)/배포" --model $M --out $G/dumps/loiter_v3
log "전체 완료"
