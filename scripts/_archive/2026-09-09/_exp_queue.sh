#!/bin/bash
V=/NHNHOME/WORKSPACE/26mss002_E3/vms; PY=$V/.venv/bin/python
BAE="$V/data/원본데이터/kisa_배포_검증영상/deploy_val/방화(10개)/배포"
log(){ echo "[$(date +%m-%d\ %H:%M)] $*"; }
# 앞 학습/채점 끝날 때까지 대기(GPU 점유 해제)
log "앞 작업(GPU) 종료 대기"
while pgrep -f "model.py train" >/dev/null || pgrep -f "score_kisa.py" >/dev/null; do sleep 60; done
run_exp(){
  local NAME=$1 MODEL=$2; shift 2; local EXTRA=("$@")
  # 이미 결과 있으면 건너뜀(중복 방지)
  [ -s "$V/results/$NAME.txt" ] && { log "$NAME 결과 존재, 건너뜀"; return; }
  local DS=$V/data/학습데이터/mix_$NAME
  rm -rf "$DS"; mkdir -p "$DS/images/train" "$DS/labels/train"
  cp -asn $V/data/학습데이터/dataset_24k/images/train/. "$DS/images/train/" 2>/dev/null||true
  cp -asn $V/data/학습데이터/dataset_24k/labels/train/. "$DS/labels/train/" 2>/dev/null||true
  for k in 1 2 3 4 5; do for f in $V/data/학습데이터/human_fire/images/train/*.jpg; do b=$(basename "$f" .jpg); ln -sf "$f" "$DS/images/train/H${k}_$b.jpg"; ln -sf "$V/data/학습데이터/human_fire/labels/train/$b.txt" "$DS/labels/train/H${k}_$b.txt"; done; done
  for d in "${EXTRA[@]}"; do pre=$(echo "$d"|tr -cd 'A-Za-z0-9'|cut -c1-4); for f in $V/data/학습데이터/$d/images/train/*.jpg; do b=$(basename "$f" .jpg); ln -sf "$f" "$DS/images/train/${pre}_$b.jpg"; ln -sf "$V/data/학습데이터/$d/labels/train/$b.txt" "$DS/labels/train/${pre}_$b.txt"; done; done
  ln -sfn $V/data/학습데이터/dataset_24k/images/val "$DS/images/val"
  ln -sfn $V/data/학습데이터/dataset_24k/labels/val "$DS/labels/val"
  printf "path: %s\ntrain: images/train\nval: images/val\nnc: 2\nnames: ['fire','smoke']\n" "$DS" > "$DS/data.yaml"
  log "$NAME 학습 시작 ($MODEL, $(ls $DS/images/train|wc -l)장, 추가=[${EXTRA[*]}])"
  cd $V
  CUDA_VISIBLE_DEVICES=0 $PY model.py train --models $MODEL --data "$DS/data.yaml" --project $V/runs --device 0 --batch 128 --epochs 80 --imgsz 640 --multi-scale --no-export --force >/dev/null 2>&1
  mv $V/runs/$MODEL $V/runs/$NAME 2>/dev/null
  log "$NAME 채점"
  { echo "=== $NAME 타일 ==="; $PY $V/score_kisa.py $V/runs/$NAME/weights/best.pt --videos "$BAE" --gt "$BAE" --stride 0.5 --imgsz 640 --tiles --tag "$NAME"; } > $V/results/$NAME.txt 2>&1
  rm -rf "$DS"
  log "$NAME 완료 → results/$NAME.txt"
}
T=$(date +%Y%m%d)
run_exp fire_base_$T        yolo11s
run_exp fire_fasdd_$T       yolo11s fasdd_yolo
run_exp fire_snow2_$T       yolo11s fasdd_snow2
run_exp fire_snowfull_$T    yolo11s fasdd_snowfog fasdd_yolo
run_exp fire_m_snowmix_$T   yolo11m fasdd_snowfog
log "QUEUE DONE (fog 실험은 TS 추출 후 추가)"
