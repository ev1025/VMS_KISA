#!/bin/bash
W=/NHNHOME/WORKSPACE/26mss002_E3; G=$W/vms; PY=$W/vms/.venv/bin/python
log(){ echo "[$(date +%H:%M)] $*"; }
# 24k + 사람라벨 혼합 데이터셋
DS=$G/data/학습데이터/mix_human
rm -rf $DS; mkdir -p $DS/images/train $DS/labels/train
cp -asn $G/data/학습데이터/dataset_24k/images/train/. $DS/images/train/ 2>/dev/null || true
cp -asn $G/data/학습데이터/dataset_24k/labels/train/. $DS/labels/train/ 2>/dev/null || true
# 사람라벨은 5배 오버샘플(수가 적으므로 가중)
for k in 1 2 3 4 5; do
  for f in $G/data/학습데이터/human_fire/images/train/*.jpg; do
    b=$(basename $f .jpg); ln -sf "$f" "$DS/images/train/H${k}_$b.jpg" 2>/dev/null
    ln -sf "$G/data/학습데이터/human_fire/labels/train/$b.txt" "$DS/labels/train/H${k}_$b.txt" 2>/dev/null
  done
done
ln -sfn $G/data/학습데이터/dataset_24k/images/val $DS/images/val
ln -sfn $G/data/학습데이터/dataset_24k/labels/val $DS/labels/val
printf "path: %s\ntrain: images/train\nval: images/val\nnc: 2\nnames: ['fire','smoke']\n" $DS > $DS/data.yaml
log "혼합 학습셋: $(ls $DS/images/train | wc -l)장"
cd $W/vms
$PY model.py train --models yolo11s --data $DS/data.yaml --project $G/runs \
  --device 0 --batch 128 --epochs 60 --imgsz 640 --multi-scale --no-export --force
mv $G/runs/yolo11s $G/runs/fire_human_pilot 2>/dev/null
log "채점"
: > $G/FIRE_HUMAN_PILOT.txt
{ echo "=== 전체 ==="; $PY $W/vms/score_kisa.py $G/runs/fire_human_pilot/weights/best.pt \
    --videos $W/vms/data/원본데이터/kisa_배포_방화채점셋/videos --gt $W/vms/data/원본데이터/kisa_배포_방화채점셋/gt --stride 0.5 --imgsz 640 --tag "human 전체"
  echo "=== 타일 ==="; $PY $W/vms/score_kisa.py $G/runs/fire_human_pilot/weights/best.pt \
    --videos $W/vms/data/원본데이터/kisa_배포_방화채점셋/videos --gt $W/vms/data/원본데이터/kisa_배포_방화채점셋/gt --stride 0.5 --imgsz 640 --tiles --tag "human 타일"
} >> $G/FIRE_HUMAN_PILOT.txt 2>&1
log "완료"
