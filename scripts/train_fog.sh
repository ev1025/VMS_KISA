#!/bin/bash
# 안개 오탐 억제 학습. 24k + 손라벨 + 안개/구름 하드네거티브(빈라벨).
# 목표: C00_195(안개) 같은 장면을 "연기 아님"으로 학습시켜 오탐 없이 미검을 줄인다.
W=/NHNHOME/WORKSPACE/26mss002_E3; G=$W/vms; PY=$W/vms/.venv/bin/python
export OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=1
F24=$G/data/학습데이터/dataset_24k; HF=$G/data/학습데이터/human_fire; FOG=$G/data/학습데이터/wildfire_fog_neg 2>/dev/null
FOG=$W/vms/data/학습데이터/wildfire_fog_neg
log(){ echo "[$(date +%m-%d\ %H:%M)] $*"; }
mk(){ # 이름 안개배수
  local DS=$G/data/학습데이터/_par/$1; rm -rf $DS; mkdir -p $DS/images/train $DS/labels/train
  local f0=$(ls $HF/images/train|head -1)
  ln -sf $HF/images/train/$f0 $DS/images/train/000.jpg; ln -sf $HF/labels/train/${f0%.jpg}.txt $DS/labels/train/000.txt
  { echo $DS/images/train/000.jpg
    ls $F24/images/train | sed "s|^|$F24/images/train/|"
    for k in $(seq 1 5); do ls $HF/images/train | sed "s|^|$HF/images/train/|"; done
    for k in $(seq 1 $2); do ls $FOG/images/train | sed "s|^|$FOG/images/train/|"; done
  } > $DS/train.txt
  printf "path: %s\ntrain: train.txt\nval: %s\nnc: 2\nnames: ['fire','smoke']\n" $DS $G/data/학습데이터/_par/val_small.txt > $DS/data.yaml
  log "  $1: $(wc -l < $DS/train.txt)장 (안개 x$2)"
}
run(){ local N=$1
  log "학습 $N"
  ( cd $W/vms && $PY model.py train --models yolo11s --data $G/data/학습데이터/_par/$N/data.yaml \
      --project $G/runs/par/$N --device 0 --batch 96 --epochs 60 --imgsz 640 --no-export --force \
      --workers 16 --extra multi_scale=0.5 ) > $G/logs/par_$N.log 2>&1
  [ -f $G/runs/par/$N/yolo11s/weights/best.pt ] || { log "$N 실패"; return; }
  $PY $G/scripts/fire_detail.py $G/runs/par/$N/yolo11s/weights/best.pt --tag $N --tiles > $G/results/par/DETAIL_$N.txt 2>&1
  $PY $G/scripts/fire_rule2.py $N 2>&1 | sed -n "/규칙 스윕/,\$p" > $G/results/par/RULE2_$N.txt
  log "$N → $(sed -n 2p $G/results/par/RULE2_$N.txt)"
}
mk fog_x1 1; mk fog_x3 3
run fog_x1; run fog_x3
log "안개 학습 완료"
{ echo "=== 안개 하드네거티브 학습 결과 ==="; for n in fog_x1 fog_x3; do echo "[$n]"; sed -n '2,4p' $G/results/par/RULE2_$n.txt; done; } > $G/results/FOG_SUMMARY.txt
cat $G/results/FOG_SUMMARY.txt
