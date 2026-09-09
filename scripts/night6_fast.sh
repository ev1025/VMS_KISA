#!/bin/bash
# 960 리사이즈 사본 + RAM 캐시로 FASDD 8종을 빠르게. 추가로 원본 1280 학습 2종.
#
# 왜 이렇게 바꾸나:
#   컨테이너 App Memory 가 150GB 인데 원본(1920px)을 --cache ram 하면 24k+FASDD 만으로
#   프로세스당 80GB, 3개 동시면 240GB 라 OOM 이 났다. 원본은 어차피 학습 때 640 으로
#   줄어드므로, 미리 긴 변 960 으로 줄인 사본을 쓰면 캐시가 ~20GB 로 줄어 다 들어간다.
#   디코딩 크기도 작아 CPU 병목(이 컨테이너의 진짜 병목)도 완화된다.
W=/NHNHOME/WORKSPACE/26mss002_E3; G=$W/vms; PY=$W/vms/.venv/bin/python
export OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=1
MAXJ=2
log(){ echo "[$(date +%m-%d\ %H:%M)] $*"; }

# 리사이즈 완료 대기
while ! grep -q "완료" $G/logs/make_960.log 2>/dev/null; do sleep 30; done
log "리사이즈 완료 확인"

# 기존 목록의 경로를 960 사본 경로로 바꿔 새 데이터셋을 만든다
to960(){ sed 's#/data/학습데이터/#/data/fire960/#g'; }
mk960(){ # 이름  (기존 _par 데이터셋 이름에서 목록 재활용)
  local N=$1; local SRC=$G/data/학습데이터/_par/$N/train.txt DS=$G/data/학습데이터/_par/${N}_960
  rm -rf $DS; mkdir -p $DS
  to960 < $SRC | grep -v '^$' > $DS/train.txt
  printf "path: %s\ntrain: train.txt\nval: %s\nnc: 2\nnames: ['fire','smoke']\n" $DS \
    "$(echo $G/data/학습데이터/_par/val_small.txt)" > $DS/data.yaml
  log "  ${N}_960: $(wc -l < $DS/train.txt)장"
}
for N in fa_small hard_fa fa_fire fa_neg fa_mix hard_mix fa_only fa_mix2; do mk960 $N; done

run(){ # 이름 데이터yaml epochs imgsz batch [cache]
  local N=$1
  log "학습 $N (imgsz $4)"
  ( cd $W/vms && $PY model.py train --models yolo11s --data $2 \
      --project $G/runs/par/$N --device 0 --batch $5 --epochs $3 --imgsz $4 --no-export --force \
      --cache ${6:-disk} --workers 16 --extra multi_scale=0.5 ) > $G/logs/par_$N.log 2>&1
  [ -f $G/runs/par/$N/yolo11s/weights/best.pt ] || { log "$N 실패"; return; }
  $PY $G/scripts/fire_detail.py $G/runs/par/$N/yolo11s/weights/best.pt --tag $N --tiles > $G/results/par/DETAIL_$N.txt 2>&1
  $PY $G/scripts/fire_rule2.py $N 2>&1 | sed -n '/규칙 스윕/,$p' > $G/results/par/RULE2_$N.txt
  log "$N → $(sed -n 2p $G/results/par/RULE2_$N.txt)"
}

gate(){ while true; do
    NJ=$(ps -eo cmd | grep '[m]odel.py train' | grep -oE '_par/[a-z0-9_]+' | sort -u | wc -l)
    VR=$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits)
    FR=$(free -g | awk '/^Mem:/{print $7}')
    [ "$NJ" -lt $MAXJ ] && [ "$VR" -lt 150000 ] && [ "$FR" -gt 60 ] && break
    sleep 30
  done; }

# 640 학습 8종 (960 사본, RAM 캐시)
for N in fa_small hard_fa fa_fire hard_mix fa_neg fa_mix fa_only fa_mix2; do
  gate; run ${N}960 $G/data/학습데이터/_par/${N}_960/data.yaml 30 640 128 disk &
  sleep 60
done
wait; log "640 8종 완료"

# 1280 학습 2종 (원본, 배포가 1280x720 이고 불이 작아 검증 가치가 있다. disk 캐시로 RAM 회피)
for N in fa_small hard_fa; do
  gate; run ${N}_1280 $G/data/학습데이터/_par/$N/data.yaml 30 1280 32 disk &
  sleep 120
done
wait; log "1280 2종 완료"
log "night6 전체 완료"
