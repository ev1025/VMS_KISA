#!/bin/bash
# 방화 손라벨(225장 전체) 실험 병렬 런처. B200 1장(183GB)·72코어 → 동시 4잡, RAM 캐시로 Lustre 소파일 I/O 병목 회피.
W=/NHNHOME/WORKSPACE/26mss002_E3; G=$W/vms; PY=$W/vms/.venv/bin/python
MAXJ=3; WK=8   # CPU 가 병목(PSI 95%, 코어당 3~4배 느림): 잡 3개·워커 8
log(){ echo "[$(date +%m-%d\ %H:%M)] $*"; }

# ---- 0. 데이터셋 = 이미지 목록 txt (Lustre 심링크 37개/s 한계 회피. ultralytics 는 목록 중복을 제거하지 않아 반복=오버샘플) ----
# human_fire(1045장)·human_synth(299장)는 이미 재생성됨. 재생성 필요시: build_humanset.py / fire_synth.py
F24=$G/data/학습데이터/dataset_24k; HF=$G/data/학습데이터/human_fire; HS=$G/data/학습데이터/human_synth
mkds(){ # 이름 손라벨배수 합성포함(0/1)
  local DS=$G/data/학습데이터/_par/$1 OV=$2 SY=$3
  rm -rf $DS; mkdir -p $DS/images/train $DS/labels/train
  # 정렬상 맨 앞 파일 1개를 데이터셋 전용 폴더에 두어 labels.cache 경로를 잡별로 분리
  local f0=$(ls $HF/images/train | head -1)
  ln -sf $HF/images/train/$f0 $DS/images/train/000.jpg; ln -sf $HF/labels/train/${f0%.jpg}.txt $DS/labels/train/000.txt
  { echo $DS/images/train/000.jpg
    ls $F24/images/train | sed "s|^|$F24/images/train/|"
    for k in $(seq 1 $OV); do ls $HF/images/train | sed "s|^|$HF/images/train/|"; done
    if [ "$SY" = 1 ]; then ls $HS/images/train | sed "s|^|$HS/images/train/|"; fi
  } > $DS/train.txt
  printf "path: %s
train: train.txt
val: %s
nc: 2
names: ['fire','smoke']
" $DS $G/data/학습데이터/_par/val_small.txt > $DS/data.yaml   # val 600장: 에폭당 NMS 3분→25초
  log "  $1: $(wc -l < $DS/train.txt)장"
}
mkds mix_human_full 5 0; mkds mix_synth 1 1; mkds ov3 3 0; mkds ov10 10 0; mkds ov20 20 0

# ---- 1. 잡 정의 ----
score(){ # 이름 가중치 imgsz
  { echo "=== $1 타일 ==="; $PY $W/vms/score_kisa.py $2 --videos $W/vms/data/원본데이터/kisa_배포_방화채점셋/videos --gt $W/vms/data/원본데이터/kisa_배포_방화채점셋/gt --stride 0.5 --imgsz $3 --tiles --tag "$1"; } > $G/results/par/EXP_$1.txt 2>&1
}
train(){ # 이름 data.yaml epochs imgsz batch
  local N=$1; log "시작 $N"
  ( cd $W/vms && OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=1 $PY model.py train --models yolo11s --data $2 --project $G/runs/par/$N --device 0 --batch $5 --epochs $3 --imgsz $4 --multi-scale --no-export --force --cache ram --workers $WK --extra multi_scale=0.5 )   # 8.4: bool True=배율1.0=0~1280px → VRAM 120GB. 0.5=320~960 > $G/logs/par_$N.log 2>&1
  score $N $G/runs/par/$N/yolo11s/weights/best.pt $4; log "완료 $N → $(grep -E 'F1' $G/results/par/EXP_$N.txt | tail -1)"
}
driver(){ log "시작 driver $1"; case $1 in
  kfold) $PY $G/scripts/fire_kfold.py human mix24k > $G/results/par/FIRE_KFOLD.txt 2>&1 ;;
  ratio_loo) $PY $G/scripts/fire_matrix2.py ratio > $G/results/par/FIRE_RATIO.txt 2>&1; $PY $G/scripts/fire_matrix2.py loo > $G/results/par/FIRE_LOO.txt 2>&1 ;;
  esac; log "완료 driver $1"; }

JOBS=(
  "train human_full $G/data/학습데이터/_par/mix_human_full/data.yaml 80 640 128"
  "train synth_mix $G/data/학습데이터/_par/mix_synth/data.yaml 70 640 64"
  "train human960 $G/data/학습데이터/_par/mix_human_full/data.yaml 60 960 64"
  "train ov3 $G/data/학습데이터/_par/ov3/data.yaml 60 640 64"
  "train ov10 $G/data/학습데이터/_par/ov10/data.yaml 60 640 64"
  "train ov20 $G/data/학습데이터/_par/ov20/data.yaml 60 640 64"
)
for j in "${JOBS[@]}"; do
  while [ "$(jobs -rp | wc -l)" -ge $MAXJ ] || [ "$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits)" -gt 120000 ]; do sleep 30; done   # 잡 수 + VRAM 여유 60GB 게이트
  eval "$j" &
  sleep 90   # 캐시 적재·GPU 초기화 시차
done
wait; log "전체 완료"
