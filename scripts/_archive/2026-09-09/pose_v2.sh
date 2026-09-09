#!/bin/bash
# pose_v2: person_pose(자체 kpt 의사라벨) + COCO-pose 혼합 → 11s-pose → 쓰러짐 kpt + 침입/배회 박스 덤프
set -e
W=/NHNHOME/WORKSPACE/26mss002_E3
G=$W/vms
PY=$W/vms/.venv/bin/python
log(){ echo "[$(date +%H:%M)] $*"; }

log "1) COCO-pose 라벨"
cd $G/datasets/coco_dl
[ -f coco2017labels-pose.zip ] || wget -q https://github.com/ultralytics/assets/releases/download/v0.0.0/coco2017labels-pose.zip
[ -d coco-pose ] || { mkdir -p coco-pose && unzip -q coco2017labels-pose.zip -d coco-pose; }
PL=$(find $G/datasets/coco_dl/coco-pose -type d -name train2017 -path '*labels*' | head -1)
echo "pose 라벨 폴더: $PL ($(ls $PL | wc -l)개)"

log "2) COCO-pose 부분집합 12k + person_pose 합체"
DS=$G/datasets/pose_v2
mkdir -p $DS/images/train $DS/labels/train
cp -al $G/datasets/person_pose/images/train/. $DS/images/train/
cp -al $G/datasets/person_pose/labels/train/. $DS/labels/train/
$PY - <<PYEOF
import os, random, shutil
from pathlib import Path
random.seed(0)
img_dir = Path("$G/datasets/coco_dl/train2017")
lb_dir = Path("$PL")
ds = Path("$DS")
labels = [p for p in lb_dir.glob("*.txt")]
random.shuffle(labels)
n = 0
for lb in labels:
    if n >= 12000: break
    img = img_dir / (lb.stem + ".jpg")
    if not img.exists(): continue
    try: os.link(img, ds/"images"/"train"/("coco_"+img.name))
    except OSError: shutil.copy2(img, ds/"images"/"train"/("coco_"+img.name))
    shutil.copy2(lb, ds/"labels"/"train"/("coco_"+lb.name))
    n += 1
print("coco-pose", n, "장 합류")
PYEOF
ln -sfn $G/datasets/person_pose/images/val $DS/images/val
ln -sfn $G/datasets/person_pose/labels/val $DS/labels/val
printf "path: %s\ntrain: images/train\nval: images/val\nkpt_shape: [17, 3]\nflip_idx: [0, 2, 1, 4, 3, 6, 5, 8, 7, 10, 9, 12, 11, 14, 13, 16, 15]\nnc: 1\nnames: ['person']\n" $DS > $DS/data.yaml
echo "train: $(ls $DS/images/train | wc -l)장"

log "3) yolo11s-pose 학습"
cd $W/vms
$PY model.py train --models yolo11s-pose --data $DS/data.yaml --project $G/runs \
  --device 0 --batch 128 --epochs 60 --imgsz 640 --multi-scale --no-export
mv $G/runs/yolo11s-pose $G/runs/pose_v2

log "4) 덤프: 쓰러짐 kpt + 침입/배회 박스"
M=$G/runs/pose_v2/weights/best.pt
$PY $G/scripts/server_kptdump.py --videos "$G/datasets/deploy_val/쓰러짐(10개)/배포" --model $M --out $G/dumps/fall_pose2
$PY $G/scripts/server_pdump.py --videos "$G/datasets/deploy_val/침입(30개)/배포" --model $M --out $G/dumps/intrusion_pose2
$PY $G/scripts/server_pdump.py --videos "$G/datasets/deploy_val/배회(30개)/배포" --model $M --out $G/dumps/loiter_pose2
log "전체 완료"
