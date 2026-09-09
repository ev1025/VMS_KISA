#!/bin/bash
# 설경·안개 보강 학습. 배포 미검 2편(설경 위 작은 불꽃 / 짙은 안개)이 학습 분포에 없어서 생긴 문제.
# 보강원: FASDD 중 눈 장면 351장(불 박스 44장)과 밝은 저채도 배경 3,579장. 둘 다 박스 라벨 보유.
W=/NHNHOME/WORKSPACE/26mss002_E3; G=$W/vms; PY=$W/vms/.venv/bin/python
export OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=1
log(){ echo "[$(date +%m-%d\ %H:%M)] $*"; }
while pgrep -f "person_redump.py" >/dev/null; do sleep 120; done   # 재덤프가 GPU 쓰는 중이면 대기
F24=$G/data/학습데이터/dataset_24k; HF=$G/data/학습데이터/human_fire
mk(){ # 이름 눈배수 밝은배경배수
  local DS=$G/data/학습데이터/_par/$1; rm -rf $DS; mkdir -p $DS/images/train $DS/labels/train
  local f0=$(ls $HF/images/train | head -1)
  ln -sf $HF/images/train/$f0 $DS/images/train/000.jpg; ln -sf $HF/labels/train/${f0%.jpg}.txt $DS/labels/train/000.txt
  { echo $DS/images/train/000.jpg
    ls $F24/images/train | sed "s|^|$F24/images/train/|"
    for k in $(seq 1 5); do ls $HF/images/train | sed "s|^|$HF/images/train/|"; done
    for k in $(seq 1 $2); do ls $G/data/학습데이터/fasdd_snow2/images/train | sed "s|^|$G/data/학습데이터/fasdd_snow2/images/train/|"; done
    for k in $(seq 1 $3); do ls $G/data/학습데이터/fasdd_snowfog/images/train | sed "s|^|$G/data/학습데이터/fasdd_snowfog/images/train/|"; done
  } > $DS/train.txt
  printf "path: %s\ntrain: train.txt\nval: %s\nnc: 2\nnames: ['fire','smoke']\n" $DS $G/data/학습데이터/_par/val_small.txt > $DS/data.yaml
  log "  $1: $(wc -l < $DS/train.txt)장"
}
mk snow_x10 10 2
mk snow_x30 30 5
for N in snow_x10 snow_x30; do
  log "학습 $N"
  ( cd $W/vms && $PY model.py train --models yolo11s --data $G/data/학습데이터/_par/$N/data.yaml \
      --project $G/runs/par/$N --device 0 --batch 96 --epochs 70 --imgsz 640 --no-export --force \
      --cache ram --workers 8 --extra multi_scale=0.5 ) > $G/logs/par_$N.log 2>&1
  log "시계열 $N"
  $PY $G/scripts/fire_detail.py $G/runs/par/$N/yolo11s/weights/best.pt --tag $N --tiles > $G/results/par/DETAIL_$N.txt 2>&1
  log "$N 새 규칙 채점"; $PY $G/scripts/fire_rule2.py $N 2>&1 | sed -n '/규칙 스윕/,$p' > $G/results/par/RULE2_$N.txt
  head -4 $G/results/par/RULE2_$N.txt
done
log "설경·안개 보강 완료"
