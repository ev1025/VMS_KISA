#!/bin/bash
set -e
V=/NHNHOME/WORKSPACE/26mss002_E3/vms; PY=$V/.venv/bin/python
NAME=fire_snowmix_20260908_1028; DS=$V/data/학습데이터/mix_$NAME
log(){ echo "[$(date +%H:%M)] $*"; }
log "혼합 학습셋 구성"
rm -rf $DS; mkdir -p $DS/images/train $DS/labels/train
cp -asn $V/data/학습데이터/dataset_24k/images/train/. $DS/images/train/ 2>/dev/null || true
cp -asn $V/data/학습데이터/dataset_24k/labels/train/. $DS/labels/train/ 2>/dev/null || true
for k in 1 2 3 4 5; do for f in $V/data/학습데이터/human_fire/images/train/*.jpg; do b=$(basename $f .jpg); ln -sf "$f" "$DS/images/train/H${k}_$b.jpg"; ln -sf "$V/data/학습데이터/human_fire/labels/train/$b.txt" "$DS/labels/train/H${k}_$b.txt"; done; done
for f in $V/data/학습데이터/fasdd_snowfog/images/train/*.jpg; do b=$(basename $f .jpg); ln -sf "$f" "$DS/images/train/SF_$b.jpg"; ln -sf "$V/data/학습데이터/fasdd_snowfog/labels/train/$b.txt" "$DS/labels/train/SF_$b.txt"; done
ln -sfn $V/data/학습데이터/dataset_24k/images/val $DS/images/val
ln -sfn $V/data/학습데이터/dataset_24k/labels/val $DS/labels/val
printf "path: %s\ntrain: images/train\nval: images/val\nnc: 2\nnames: ['fire','smoke']\n" $DS > $DS/data.yaml
log "학습셋 $(ls $DS/images/train | wc -l)장 → 학습 시작(yolo11s, 80ep, imgsz640, dev0)"
cd $V
CUDA_VISIBLE_DEVICES=0 $PY model.py train --models yolo11s --data $DS/data.yaml --project $V/runs --device 0 --batch 128 --epochs 80 --imgsz 640 --multi-scale --no-export --force
mv $V/runs/yolo11s $V/runs/$NAME 2>/dev/null
log "채점(검증영상 방화10)"
BAE="$V/data/원본데이터/kisa_배포_검증영상/deploy_val/방화(10개)/배포"
OUT=$V/results/$NAME.txt
{ echo "=== 전체 ==="; $PY $V/score_kisa.py $V/runs/$NAME/weights/best.pt --videos "$BAE" --gt "$BAE" --stride 0.5 --imgsz 640 --tag "$NAME 전체";
  echo "=== 타일 ==="; $PY $V/score_kisa.py $V/runs/$NAME/weights/best.pt --videos "$BAE" --gt "$BAE" --stride 0.5 --imgsz 640 --tiles --tag "$NAME 타일"; } > $OUT 2>&1
log "완료 → $OUT"
