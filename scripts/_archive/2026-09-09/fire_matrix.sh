#!/bin/bash
W=/NHNHOME/WORKSPACE/26mss002_E3; G=$W/vms; PY=$W/vms/.venv/bin/python
log(){ echo "[$(date +%m-%d\ %H:%M)] $*"; }
wait_gpu(){ while pgrep -f "model.py train|fall_seq_v2.py|posec3d" >/dev/null; do sleep 120; done; }

# A. K-fold 로 데이터 구성 비교 (사람라벨만 vs 24k혼합)
wait_gpu; log "A: K-fold 데이터구성 비교"
$PY $G/scripts/fire_kfold.py human mix24k > $G/FIRE_KFOLD.txt 2>&1
log "A 완료"

# B. 합성증강 포함 학습 → 배포 채점
wait_gpu; log "B: 사람라벨+합성 학습"
DS=$G/data/학습데이터/mix_synth
rm -rf $DS; mkdir -p $DS/images/train $DS/labels/train
for src in human_fire human_synth; do
  for f in $G/data/학습데이터/$src/images/train/*.jpg; do
    [ -e "$f" ] || continue
    b=$(basename $f .jpg)
    ln -sf "$f" "$DS/images/train/${src}_$b.jpg"
    ln -sf "$G/data/학습데이터/$src/labels/train/$b.txt" "$DS/labels/train/${src}_$b.txt"
  done
done
# 24k 도 섞기
cp -asn $G/data/학습데이터/dataset_24k/images/train/. $DS/images/train/ 2>/dev/null || true
cp -asn $G/data/학습데이터/dataset_24k/labels/train/. $DS/labels/train/ 2>/dev/null || true
ln -sfn $G/data/학습데이터/dataset_24k/images/val $DS/images/val
ln -sfn $G/data/학습데이터/dataset_24k/labels/val $DS/labels/val
printf "path: %s\ntrain: images/train\nval: images/val\nnc: 2\nnames: ['fire','smoke']\n" $DS > $DS/data.yaml
log "  합성포함 학습셋 $(ls $DS/images/train | wc -l)장"
cd $W/vms
$PY model.py train --models yolo11s --data $DS/data.yaml --project $G/runs \
  --device 0 --batch 64 --epochs 70 --imgsz 640 --multi-scale --no-export --force
mv $G/runs/yolo11s $G/runs/fire_synth_mix 2>/dev/null
{ echo "=== synth_mix 타일 ==="; $PY $W/vms/score_kisa.py $G/runs/fire_synth_mix/weights/best.pt \
  --videos $W/vms/data/원본데이터/kisa_배포_방화채점셋/videos --gt $W/vms/data/원본데이터/kisa_배포_방화채점셋/gt --stride 0.5 --imgsz 640 --tiles --tag "synth_mix"; } > $G/EXP3_SYNTH.txt 2>&1
log "B 완료"

# C. 오버샘플 배수 비교 (사람라벨 가중치 효과)
for OV in 3 10 20; do
  wait_gpu; log "C: 오버샘플 x$OV"
  DS=$G/data/학습데이터/ov$OV
  rm -rf $DS; mkdir -p $DS/images/train $DS/labels/train
  cp -asn $G/data/학습데이터/dataset_24k/images/train/. $DS/images/train/ 2>/dev/null || true
  cp -asn $G/data/학습데이터/dataset_24k/labels/train/. $DS/labels/train/ 2>/dev/null || true
  for k in $(seq 1 $OV); do
    for f in $G/data/학습데이터/human_fire/images/train/*.jpg; do
      b=$(basename $f .jpg); ln -sf "$f" "$DS/images/train/H${k}_$b.jpg" 2>/dev/null
      ln -sf "$G/data/학습데이터/human_fire/labels/train/$b.txt" "$DS/labels/train/H${k}_$b.txt" 2>/dev/null
    done
  done
  ln -sfn $G/data/학습데이터/dataset_24k/images/val $DS/images/val
  ln -sfn $G/data/학습데이터/dataset_24k/labels/val $DS/labels/val
  printf "path: %s\ntrain: images/train\nval: images/val\nnc: 2\nnames: ['fire','smoke']\n" $DS > $DS/data.yaml
  cd $W/vms
  $PY model.py train --models yolo11s --data $DS/data.yaml --project $G/runs \
    --device 0 --batch 64 --epochs 60 --imgsz 640 --multi-scale --no-export --force
  mv $G/runs/yolo11s $G/runs/fire_ov$OV 2>/dev/null
  { echo "=== ov$OV 타일 ==="; $PY $W/vms/score_kisa.py $G/runs/fire_ov$OV/weights/best.pt \
    --videos $W/vms/data/원본데이터/kisa_배포_방화채점셋/videos --gt $W/vms/data/원본데이터/kisa_배포_방화채점셋/gt --stride 0.5 --imgsz 640 --tiles --tag "ov$OV"; } >> $G/EXP4_OVERSAMPLE.txt 2>&1
done
log "전체 매트릭스 완료"
