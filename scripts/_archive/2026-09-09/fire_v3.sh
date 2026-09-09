#!/bin/bash
# fire_v3: pose_v1 종료 대기 → IR 약라벨 → 24k+IR(5배 오버샘플) 학습 → KISA 채점
set -e
W=/NHNHOME/WORKSPACE/26mss002_E3
G=$W/vms
PY=$W/vms/.venv/bin/python
log(){ echo "[$(date +%H:%M)] $*"; }

log "pose_v1 종료 대기..."
while tmux has-session -t pose_v1 2>/dev/null; do sleep 300; done
log "GPU 확보. IR 약라벨 생성"
$PY $G/scripts/pl_ir_fire.py

N=$(ls $G/datasets/ir_fire_pl/labels/*.txt 2>/dev/null | grep -cv _bg || true)
log "IR 라벨 프레임: $N"
if [ "$N" -lt 10 ]; then log "라벨 부족 - 중단"; exit 0; fi

log "fire_v3 데이터셋 = 24k + IR×5"
DS=$G/datasets/fire_v3
mkdir -p $DS/images/train $DS/labels/train
cp -al $W/datasets/dataset_24k/images/train/. $DS/images/train/
cp -al $W/datasets/dataset_24k/labels/train/. $DS/labels/train/
for i in 1 2 3 4 5; do
  for f in $G/datasets/ir_fire_pl/images/*.jpg; do
    b=$(basename "$f" .jpg)
    ln -f "$f" "$DS/images/train/${b}_x$i.jpg"
    ln -f "$G/datasets/ir_fire_pl/labels/$b.txt" "$DS/labels/train/${b}_x$i.txt"
  done
done
ln -sfn $W/datasets/dataset_24k/images/val $DS/images/val
ln -sfn $W/datasets/dataset_24k/labels/val $DS/labels/val
printf "path: %s\ntrain: images/train\nval: images/val\nnc: 2\nnames: ['fire', 'smoke']\n" $DS > $DS/data.yaml

log "학습"
cd $W/vms
$PY model.py train --models yolo11s --data $DS/data.yaml --project $G/runs \
  --device 0 --batch 128 --epochs 100 --imgsz 640 --multi-scale --no-export
mv $G/runs/yolo11s $G/runs/fire_v3

log "KISA 채점"
{
  $PY $W/vms/score_kisa.py $G/runs/fire_v3/weights/best.pt --videos $W/vms/data/원본데이터/kisa_배포_방화채점셋/videos --gt $W/vms/data/원본데이터/kisa_배포_방화채점셋/gt --stride 0.5 --tag "fire_v3 전체"
  $PY $W/vms/score_kisa.py $G/runs/fire_v3/weights/best.pt --videos $W/vms/data/원본데이터/kisa_배포_방화채점셋/videos --gt $W/vms/data/원본데이터/kisa_배포_방화채점셋/gt --stride 0.5 --tiles --tag "fire_v3 타일"
} > $G/FIRE_V3_SCORES.txt 2>&1
log "전체 완료"
