#!/bin/bash
V=/NHNHOME/WORKSPACE/26mss002_E3/vms; PY=$V/.venv/bin/python
BAE="$V/data/원본데이터/kisa_배포_검증영상/deploy_val/방화(10개)/배포"
log(){ echo "[$(date +%m-%d\ %H:%M)] $*"; }
log "메인 큐 종료 대기"
while tmux has-session -t queue 2>/dev/null; do sleep 120; done
run_exp(){
  local NAME=$1 MODEL=$2; shift 2; local EXTRA=("$@")
  [ -s "$V/results/$NAME.txt" ] && { log "$NAME 존재, 건너뜀"; return; }
  local DS=$V/data/학습데이터/mix_$NAME
  rm -rf "$DS"; mkdir -p "$DS/images/train" "$DS/labels/train"
  cp -asn $V/data/학습데이터/dataset_24k/images/train/. "$DS/images/train/" 2>/dev/null||true
  cp -asn $V/data/학습데이터/dataset_24k/labels/train/. "$DS/labels/train/" 2>/dev/null||true
  for k in 1 2 3 4 5; do for f in $V/data/학습데이터/human_fire/images/train/*.jpg; do b=$(basename "$f" .jpg); ln -sf "$f" "$DS/images/train/H${k}_$b.jpg"; ln -sf "$V/data/학습데이터/human_fire/labels/train/$b.txt" "$DS/labels/train/H${k}_$b.txt"; done; done
  for d in "${EXTRA[@]}"; do pre=$(echo "$d"|tr -cd "A-Za-z0-9"|cut -c1-5); for f in $V/data/학습데이터/$d/images/train/*.jpg; do b=$(basename "$f" .jpg); ln -sf "$f" "$DS/images/train/${pre}_$b.jpg"; [ -f "$V/data/학습데이터/$d/labels/train/$b.txt" ] && ln -sf "$V/data/학습데이터/$d/labels/train/$b.txt" "$DS/labels/train/${pre}_$b.txt" || : > "$DS/labels/train/${pre}_$b.txt"; done; done
  ln -sfn $V/data/학습데이터/dataset_24k/images/val "$DS/images/val"; ln -sfn $V/data/학습데이터/dataset_24k/labels/val "$DS/labels/val"
  printf "path: %s\ntrain: images/train\nval: images/val\nnc: 2\nnames: ['fire','smoke']\n" "$DS" > "$DS/data.yaml"
  log "$NAME 학습($MODEL, $(ls $DS/images/train|wc -l)장, +[${EXTRA[*]}])"
  cd $V; CUDA_VISIBLE_DEVICES=0 $PY model.py train --models $MODEL --data "$DS/data.yaml" --project $V/runs --device 0 --batch 128 --epochs 80 --imgsz 640 --multi-scale --no-export --force >/dev/null 2>&1
  mv $V/runs/$MODEL $V/runs/$NAME 2>/dev/null
  { echo "=== $NAME 타일 ==="; $PY $V/score_kisa.py $V/runs/$NAME/weights/best.pt --videos "$BAE" --gt "$BAE" --stride 0.5 --imgsz 640 --tiles --tag "$NAME"; } > $V/results/$NAME.txt 2>&1
  rm -rf "$DS"; log "$NAME 완료"
}
T=$(date +%Y%m%d)
run_exp fire_fog1_$T      yolo11s wildfire_fog_neg
run_exp fire_fogsnow_$T   yolo11s wildfire_fog_neg fasdd_snowfog
log "QUEUE2(fog) DONE"
