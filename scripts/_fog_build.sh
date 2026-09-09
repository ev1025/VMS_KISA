#!/bin/bash
V=/NHNHOME/WORKSPACE/26mss002_E3/vms
OUT=$V/data/원본데이터/aihub71330_산불_안개구름
NEG=$V/data/학습데이터/wildfire_fog_neg
LOG=$V/logs/fog_build.log
echo "[$(date +%H:%M)] 추출 완료 대기" > $LOG
while ! grep -q DONE $V/logs/fog_extract.log 2>/dev/null; do sleep 60; done
echo "[$(date +%H:%M)] 추출 완료, 샘플링 시작" >> $LOG
rm -rf $NEG; mkdir -p $NEG/images/train $NEG/labels/train
mapfile -t ALL < <(find $OUT -name '*.jpg' | sort)
n=${#ALL[@]}; target=12000
step=$(( n>target ? n/target : 1 )); [ $step -lt 1 ] && step=1
i=0; c=0
for f in "${ALL[@]}"; do
  if (( i % step == 0 )); then
    b=$(basename "$f" .jpg)
    ln -sf "$f" "$NEG/images/train/$b.jpg"
    : > "$NEG/labels/train/$b.txt"
    c=$((c+1))
  fi
  i=$((i+1))
done
printf "path: %s\ntrain: images/train\nval: images/train\nnc: 2\nnames: ['fire','smoke']\n" $NEG > $NEG/data.yaml
echo "[$(date +%H:%M)] wildfire_fog_neg 재생성 완료: 전체 $n 중 $c장(빈 라벨 하드네거티브)" >> $LOG
echo "FOGBUILD DONE" >> $LOG
