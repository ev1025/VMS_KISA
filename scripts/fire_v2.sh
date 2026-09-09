#!/bin/bash
# 방화 v2 체인: 의사라벨(방화75) → 24k+75 데이터셋 → 학습 → KISA 채점. tmux 안에서 실행
set -e
W=/NHNHOME/WORKSPACE/26mss002_E3
G=$W/vms
PY=$W/vms/.venv/bin/python
log(){ echo "[$(date +%H:%M)] $*"; }

log "1) 방화75 의사라벨 (base+타일, GPU)"
$PY $G/scripts/pl_fire75.py --videos $G/datasets/fire75_raw \
  --model $W/vms/runs/kisa/base/weights/best.pt --out $G/datasets/fire75_pl

log "2) fire_v2 데이터셋 = dataset_24k + fire75_pl"
DS=$G/datasets/fire_v2
mkdir -p $DS/images/train $DS/labels/train
cp -al $W/datasets/dataset_24k/images/train/. $DS/images/train/
cp -al $W/datasets/dataset_24k/labels/train/. $DS/labels/train/
cp -al $G/datasets/fire75_pl/images/. $DS/images/train/
cp -al $G/datasets/fire75_pl/labels/. $DS/labels/train/
ln -sfn $W/datasets/dataset_24k/images/val $DS/images/val
ln -sfn $W/datasets/dataset_24k/labels/val $DS/labels/val
printf "path: %s\ntrain: images/train\nval: images/val\nnc: 2\nnames: ['fire', 'smoke']\n" $DS > $DS/data.yaml
echo "train 장수: $(ls $DS/images/train | wc -l)"

log "3) 학습 yolo11s (base 와 같은 레시피)"
cd $W/vms
$PY model.py train --models yolo11s --data $DS/data.yaml --project $G/runs \
  --device 0 --batch 128 --epochs 100 --imgsz 640 --multi-scale --no-export
mv $G/runs/yolo11s $G/runs/fire_v2

log "4) KISA 10편 채점 (전체 / 타일)"
$PY $W/vms/score_kisa.py $G/runs/fire_v2/weights/best.pt \
  --videos $W/vms/data/원본데이터/kisa_배포_방화채점셋/videos --gt $W/vms/data/원본데이터/kisa_배포_방화채점셋/gt --stride 0.5 --tag "fire_v2 전체" > $G/FIRE_V2_SCORES.txt 2>&1
$PY $W/vms/score_kisa.py $G/runs/fire_v2/weights/best.pt \
  --videos $W/vms/data/원본데이터/kisa_배포_방화채점셋/videos --gt $W/vms/data/원본데이터/kisa_배포_방화채점셋/gt --stride 0.5 --tiles --tag "fire_v2 타일" >> $G/FIRE_V2_SCORES.txt 2>&1
log "완료" >> $G/FIRE_V2_SCORES.txt
log "전체 완료"
