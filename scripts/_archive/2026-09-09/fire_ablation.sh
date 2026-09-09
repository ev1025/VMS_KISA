#!/bin/bash
# 방화 24k 축소 A/B: half_loc / clip1 / firebal 3변형 각각 학습 → KISA 채점, base(66.7) 대비
set -e
W=/NHNHOME/WORKSPACE/26mss002_E3; G=$W/vms; PY=$W/vms/.venv/bin/python
log(){ echo "[$(date +%H:%M)] $*"; }
# GPU 순차: inttile/fireseq 끝나면 시작
while tmux has-session -t fireseq 2>/dev/null || tmux has-session -t inttile 2>/dev/null; do sleep 120; done

score(){  # $1=런이름
  $PY $W/vms/score_kisa.py $G/runs/$1/weights/best.pt --videos $W/vms/data/원본데이터/kisa_배포_방화채점셋/videos --gt $W/vms/data/원본데이터/kisa_배포_방화채점셋/gt --stride 0.5 --tag "$1 전체"
  $PY $W/vms/score_kisa.py $G/runs/$1/weights/best.pt --videos $W/vms/data/원본데이터/kisa_배포_방화채점셋/videos --gt $W/vms/data/원본데이터/kisa_배포_방화채점셋/gt --stride 0.5 --tiles --tag "$1 타일"
}
: > $G/FIRE_ABLATION_SCORES.txt
for V in half_loc clip1 firebal; do
  log "변형 $V 생성"
  rm -rf $G/datasets/fire_$V
  $PY $G/scripts/make_variants.py --which $V --out $G/datasets/fire_$V
  log "$V 학습 (yolo11s)"
  cd $W/vms
  $PY model.py train --models yolo11s --data $G/datasets/fire_$V/data.yaml --project $G/runs \
    --device 0 --batch 128 --epochs 100 --imgsz 640 --multi-scale --no-export --force
  mv $G/runs/yolo11s $G/runs/fire_$V
  { echo "=== $V ==="; score fire_$V; } >> $G/FIRE_ABLATION_SCORES.txt 2>&1
done
log "전체 완료"
