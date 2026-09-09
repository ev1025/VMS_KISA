#!/bin/bash
# NHN B200: 증강 절제 3런 (기준선 / aug20 / aug40) — tmux 안에서 실행
set -e
W=/NHNHOME/WORKSPACE/26mss002_E3
R=$W/vms
PY=$R/.venv/bin/python
DS=$R/data/학습데이터/dataset_24k

cat > $W/datasets/data_24k.yaml <<EOF
path: $DS
train: images/train
val: images/val
nc: 2
names: ['fire', 'smoke']
EOF

for ratio in 20 40; do
  if [ ! -f $W/datasets/dataset_aug$ratio/data.yaml ]; then
    echo "== 증강 dataset_aug$ratio 생성 =="
    $PY $R/scripts/data_prep/07_augment_domains.py $DS --out $W/datasets/dataset_aug$ratio --ratio 0.$ratio
  fi
done

train() {  # $1=런이름 $2=data.yaml
  echo "== 학습 $1 =="
  cd $R && $PY model.py train --models yolo11s --data "$2" --project $R/runs/kisa \
      --device 0 --batch 128 --epochs 100 --imgsz 640 --multi-scale --no-export
  mv $R/runs/kisa/yolo11s "$R/runs/kisa/$1"
}
train base  $W/datasets/data_24k.yaml
train aug20 $W/datasets/dataset_aug20/data.yaml
train aug40 $W/datasets/dataset_aug40/data.yaml
echo "== 3런 완료 =="
