#!/bin/bash
# 24k_v2(클립당 12프레임, val 없음) A/B. queue4 끝나면 실행.
# 6프레임 24k 대비 프레임 2배가 방화 리콜(미검)을 줄이는지 검증.
V=/NHNHOME/WORKSPACE/26mss002_E3/vms; PY=$V/.venv/bin/python
BASE=$V/data/학습데이터/aihub71751_48k          # AI-Hub71751 12프레임 이미지+라벨 평면풀
BAE="$V/data/원본데이터/kisa_배포_검증영상/deploy_val/방화(10개)/배포"
log(){ echo "[$(date +%m-%d\ %H:%M)] $*"; }
log "queue4(3항목) 종료 대기"
while tmux has-session -t queue4 2>/dev/null; do sleep 120; done
# 인자: NAME MODEL [추가데이터...]
run_exp(){
  local NAME=$1 MODEL=$2; shift 2; local EXTRA=("$@")
  [ -s "$V/results/$NAME.txt" ] && { log "$NAME 존재, 건너뜀"; return; }
  local DS=$V/data/학습데이터/mix_$NAME
  rm -rf "$DS"; mkdir -p "$DS/images/train" "$DS/labels/train"
  # 24k_v2 는 이미지+라벨 풀(평면). images/train 하위가 있으면 그걸, 없으면 평면 images/ 를 쓴다.
  SI=$([ -d "$BASE/images/train" ] && echo "$BASE/images/train" || echo "$BASE/images")
  SL=$([ -d "$BASE/labels/train" ] && echo "$BASE/labels/train" || echo "$BASE/labels")
  cp -asn "$SI/." "$DS/images/train/" 2>/dev/null||true
  cp -asn "$SL/." "$DS/labels/train/" 2>/dev/null||true
  for k in 1 2 3 4 5; do for f in $V/data/학습데이터/human_fire/images/train/*.jpg; do b=$(basename "$f" .jpg); ln -sf "$f" "$DS/images/train/H${k}_$b.jpg"; ln -sf "$V/data/학습데이터/human_fire/labels/train/$b.txt" "$DS/labels/train/H${k}_$b.txt"; done; done
  for d in "${EXTRA[@]}"; do pre=$(echo "$d"|tr -cd "A-Za-z0-9"|cut -c1-5); for f in $V/data/학습데이터/$d/images/train/*.jpg; do b=$(basename "$f" .jpg); ln -sf "$f" "$DS/images/train/${pre}_$b.jpg"; if [ -f "$V/data/학습데이터/$d/labels/train/$b.txt" ]; then ln -sf "$V/data/학습데이터/$d/labels/train/$b.txt" "$DS/labels/train/${pre}_$b.txt"; else : > "$DS/labels/train/${pre}_$b.txt"; fi; done; done
  # 24k_v2 는 val 이 없다 → 누수 방지 위해 기존 24k val 을 쓰지 않고 train 을 가리킨다(모니터용, 실평가는 KISA 채점셋).
  ln -sfn "$DS/images/train" "$DS/images/val"; ln -sfn "$DS/labels/train" "$DS/labels/val"
  printf "path: %s\ntrain: images/train\nval: images/val\nnc: 2\nnames: ['fire','smoke']\n" "$DS" > "$DS/data.yaml"
  log "$NAME 학습($MODEL, $(ls $DS/images/train|wc -l)장, +[${EXTRA[*]}])"
  cd $V; CUDA_VISIBLE_DEVICES=0 $PY model.py train --models $MODEL --data "$DS/data.yaml" --project $V/runs --device 0 --batch 128 --epochs 80 --imgsz 640 --multi-scale --no-export --force >/dev/null 2>&1
  mv $V/runs/$MODEL $V/runs/$NAME 2>/dev/null
  log "$NAME 채점"
  { echo "=== $NAME 타일 ==="; $PY $V/score_kisa.py $V/runs/$NAME/weights/best.pt --videos "$BAE" --gt "$BAE" --stride 0.5 --imgsz 640 --tiles --tag "$NAME"; } > $V/results/$NAME.txt 2>&1
  rm -rf "$DS"; log "$NAME 완료"
}
T=$(date +%Y%m%d)
run_exp fire_v2_base_$T       yolo11s                         # vs fire_base(6f)=66.67
run_exp fire_v2_snowfull_$T   yolo11s fasdd_snowfog fasdd_yolo # vs fire_snowfull(6f)=82.35 (현재 최고)
log "QUEUE5(24k_v2 A/B) DONE"
