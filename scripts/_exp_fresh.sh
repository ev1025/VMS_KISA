#!/bin/bash
# 처음부터 다시: 라벨 확실한 데이터만으로 방화 학습.
# base = aihub71751_48k(12프레임 YOLO 라벨, 24k 대체), + fasdd(외부)·snowfog(증강)·human_fire(손라벨)·fog음성.
# 과거 교훈: fasdd+snowfog=82 최고, 고해상도 악화, 병목=리콜. imgsz640 고정.
V=/NHNHOME/WORKSPACE/26mss002_E3/vms; PY=$V/.venv/bin/python
BASE=$V/data/원본데이터/aihub71751_48k          # 12프레임 이미지+라벨 평면풀
BAE="$V/data/원본데이터/kisa_배포_검증영상/deploy_val/방화(10개)/배포"
log(){ echo "[$(date +%m-%d\ %H:%M)] $*"; }

# 인자: NAME MODEL [추가데이터...]
run_exp(){
  local NAME=$1 MODEL=$2; shift 2; local EXTRA=("$@")
  [ -s "$V/results/$NAME.txt" ] && { log "$NAME 존재, 건너뜀"; return; }
  local DS=$V/data/학습데이터/mix_$NAME
  rm -rf "$DS"; mkdir -p "$DS/images/train" "$DS/labels/train"
  # base = 48k 평면풀
  cp -asn "$BASE/images/." "$DS/images/train/" 2>/dev/null||true
  cp -asn "$BASE/labels/." "$DS/labels/train/" 2>/dev/null||true
  # human_fire 손라벨 ×5 (방화영상 정답)
  for k in 1 2 3 4 5; do for f in $V/data/학습데이터/human_fire/images/train/*.jpg; do b=$(basename "$f" .jpg); ln -sf "$f" "$DS/images/train/H${k}_$b.jpg"; ln -sf "$V/data/학습데이터/human_fire/labels/train/$b.txt" "$DS/labels/train/H${k}_$b.txt"; done; done
  # 추가 데이터셋(fasdd_yolo·fasdd_snowfog·wildfire_fog_neg)
  for d in "${EXTRA[@]}"; do pre=$(echo "$d"|tr -cd "A-Za-z0-9"|cut -c1-5); for f in $V/data/학습데이터/$d/images/train/*.jpg; do b=$(basename "$f" .jpg); ln -sf "$f" "$DS/images/train/${pre}_$b.jpg"; if [ -f "$V/data/학습데이터/$d/labels/train/$b.txt" ]; then ln -sf "$V/data/학습데이터/$d/labels/train/$b.txt" "$DS/labels/train/${pre}_$b.txt"; else : > "$DS/labels/train/${pre}_$b.txt"; fi; done; done
  # 48k 는 val 없음 → 모니터용 self-val(실평가는 KISA 채점셋)
  ln -sfn "$DS/images/train" "$DS/images/val"; ln -sfn "$DS/labels/train" "$DS/labels/val"
  printf "path: %s\ntrain: images/train\nval: images/val\nnc: 2\nnames: ['fire','smoke']\n" "$DS" > "$DS/data.yaml"
  log "$NAME 학습($MODEL, $(ls $DS/images/train|wc -l)장, +[${EXTRA[*]}])"
  cd $V; CUDA_VISIBLE_DEVICES=0 $PY model.py train --models $MODEL --data "$DS/data.yaml" --project $V/runs --device 0 --batch 128 --epochs 80 --imgsz 640 --multi-scale --no-export --force >/dev/null 2>&1
  mv $V/runs/$MODEL $V/runs/$NAME 2>/dev/null
  log "$NAME 채점"
  { echo "=== $NAME 타일 ==="; $PY $V/score_kisa.py $V/runs/$NAME/weights/best.pt --videos "$BAE" --gt "$BAE" --stride 0.5 --imgsz 640 --tiles --tag "$NAME"; } > $V/results/$NAME.txt 2>&1
  rm -rf "$DS"; log "$NAME 완료 → results/$NAME.txt"
}
T=$(date +%Y%m%d)
run_exp fresh_48k_base_$T      yolo11s
run_exp fresh_48k_fasdd_$T     yolo11s fasdd_yolo
# ---- 이후 실험은 scripts/exp_queue.py + configs/queue_fire_20260909.yaml 로 이관(2026-09-09) ----
log "FRESH FIRE QUEUE DONE (exp_queue.py 로 인수)"
