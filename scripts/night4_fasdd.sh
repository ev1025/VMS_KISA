#!/bin/bash
# FASDD 적극 활용 + 어려운 배경 보강. 학습마다 새 규칙(긴 창 + 연기 기준선 대비 상승량)으로 바로 채점한다.
#
# 왜 지금 다시 FASDD 인가:
#   과거 FASDD 실험은 (1) multi_scale 이 0~1280px 로 잘못 돌던 시기 (2) 옛 채점 규칙(66.7 천장) 에서 나온 결과다.
#   게다가 FASDD 는 박스 면적 중앙값 0.035 로 24k(0.190)보다 5배 작아, 배포 영상의 작은 불에 훨씬 가깝다.
#   정상 이미지 26,133장(빈 라벨)도 있어 오탐 억제용 하드네거티브로 쓸 수 있다.
W=/NHNHOME/WORKSPACE/26mss002_E3; G=$W/vms; PY=$W/vms/.venv/bin/python
export OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=1
H=$G/data/학습데이터/_hard; F24=$G/data/학습데이터/dataset_24k; HF=$G/data/학습데이터/human_fire
R=$G/results/par; mkdir -p $R $G/logs
MAXJ=3      # 설경 학습(night3)이 아직 돌 수 있으므로 여유를 둔다
log(){ echo "[$(date +%m-%d\ %H:%M)] $*"; }

# 목록 txt 를 이어붙여 학습셋 구성. 같은 줄을 여러 번 넣으면 그대로 오버샘플이 된다.
mk(){ # 이름  "목록:배수 목록:배수 ..."
  local DS=$G/data/학습데이터/_par/$1; shift
  rm -rf $DS; mkdir -p $DS/images/train $DS/labels/train
  local f0=$(ls $HF/images/train | head -1)
  ln -sf $HF/images/train/$f0 $DS/images/train/000.jpg
  ln -sf $HF/labels/train/${f0%.jpg}.txt $DS/labels/train/000.txt
  { echo $DS/images/train/000.jpg
    for spec in "$@"; do
      local name=${spec%%:*} mult=${spec##*:}
      local src
      case $name in
        k24)   src=$(ls $F24/images/train | sed "s|^|$F24/images/train/|") ;;
        human) src=$(ls $HF/images/train | sed "s|^|$HF/images/train/|") ;;
        *)     src=$(cat $H/$name.txt) ;;
      esac
      for k in $(seq 1 $mult); do echo "$src"; done
    done
  } | grep -v '^$' > $DS/train.txt
  printf "path: %s\ntrain: train.txt\nval: %s\nnc: 2\nnames: ['fire','smoke']\n" $DS $G/data/학습데이터/_par/val_small.txt > $DS/data.yaml
  log "  $(basename $DS): $(wc -l < $DS/train.txt)장"
}

run(){ # 이름 epochs batch
  local N=$1
  log "학습 $N"
  ( cd $W/vms && $PY model.py train --models yolo11s --data $G/data/학습데이터/_par/$N/data.yaml \
      --project $G/runs/par/$N --device 0 --batch ${3:-96} --epochs ${2:-60} --imgsz 640 --no-export --force \
      --workers 16 --extra multi_scale=0.5 ) > $G/logs/par_$N.log 2>&1
  [ -f $G/runs/par/$N/yolo11s/weights/best.pt ] || { log "$N 학습 실패"; return; }
  log "시계열 $N"
  $PY $G/scripts/fire_detail.py $G/runs/par/$N/yolo11s/weights/best.pt --tag $N --tiles > $R/DETAIL_$N.txt 2>&1
  $PY $G/scripts/fire_rule2.py $N 2>&1 | sed -n '/규칙 스윕/,$p' > $R/RULE2_$N.txt
  log "$N → $(sed -n 2p $R/RULE2_$N.txt)"
}

# ---------- 1. 데이터셋 조립 ----------
log "데이터셋 조립"
#mk fa_mix      k24:1 human:5 fasdd_all:1                       # FASDD 전체 1배
#mk fa_mix2     k24:1 human:5 fasdd_all:2                       # FASDD 전체 2배 (FASDD 우세)
#mk fa_fire     k24:1 human:5 fasdd_fire:2 fasdd_neg:1          # 불 있는 것 위주 + 정상 일부
#mk fa_small    k24:1 human:5 fasdd_smallfire:4 fasdd_neg:1     # 작은 불만 강조 (배포 도메인에 가까움)
#mk fa_only     human:5 fasdd_all:1                             # 24k 빼고 FASDD 만 (24k 의존도 확인)
#mk hard_mix    k24:1 human:5 white_smoke:8 beach_sand:8 snow_fasdd:8 haze24k:8   # 어려운 배경 3종 보강
#mk hard_fa     k24:1 human:5 fasdd_all:1 white_smoke:8 beach_sand:8 snow_fasdd:8 haze24k:8
#mk fa_neg      k24:1 human:5 fasdd_neg:2                       # 정상만 추가 (오탐 억제 효과만 분리)

# ---------- 2. 학습·채점 (동시 MAXJ 개) ----------
for N in fa_small hard_fa fa_fire hard_mix; do   # 나머지 4종 제거: 방화 LOOCV상 안개·설경 2편이 천장이라 설경 보강만 의미
  # 실제 학습 프로세스 수로 센다. 스크립트 실행 시 job control 이 꺼져 있어 jobs 는 신뢰할 수 없다.
  # RAM 캐시는 안 쓰지만(24k 111GB + FASDD 120GB 로 컨테이너 한도 초과) 잡당 90GB 는 쓰므로 여유도 본다.
  while true; do
    # 서로 다른 데이터셋 이름의 개수 = 실제 잡 수 (워커까지 세면 과대평가된다)
    NJ=$(ps -eo cmd | grep '[m]odel.py train' | grep -oE '_par/[a-z0-9_]+' | sort -u | wc -l)
    VR=$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits)
    FR=$(free -g | awk '/^Mem:/{print $7}')
    [ "$NJ" -lt $MAXJ ] && [ "$VR" -lt 110000 ] && [ "$FR" -gt 300 ] && break
    sleep 60
  done
  run $N 40 96 &
  sleep 90
done
wait
log "FASDD 매트릭스 완료"

# ---------- 3. 요약 ----------
{ echo "=== FASDD·어려운배경 실험 요약 $(date +'%m-%d %H:%M') ==="
  printf "%-12s %-8s %s\n" 실험 최고F1 "정검/미검/오검 · 규칙"
  for f in $R/RULE2_*.txt; do
    n=$(basename $f .txt | sed 's/^RULE2_//')
    printf "%-12s %s\n" "$n" "$(sed -n 2p $f)"
  done
} > $G/FASDD_SUMMARY.txt 2>&1
log "요약 → $G/FASDD_SUMMARY.txt"
cat $G/FASDD_SUMMARY.txt
