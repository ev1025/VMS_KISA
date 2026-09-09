#!/bin/bash
W=/NHNHOME/WORKSPACE/26mss002_E3; G=$W/vms; PY=$W/vms/.venv/bin/python
log(){ echo "[$(date +%m-%d\ %H:%M)] $*"; }
wait_gpu(){ while pgrep -f "fire_human_pilot.sh|fire_human_full.sh|posec3d_v3.py|model.py train" >/dev/null; do sleep 120; done; }

# 1) 사람라벨 단독 학습 (24k 없이) — 도메인 순수 효과 측정
wait_gpu; log "실험1: 사람라벨 단독"
cd $W/vms
$PY model.py train --models yolo11s --data $G/data/학습데이터/human_fire/data.yaml --project $G/runs \
  --device 0 --batch 64 --epochs 80 --imgsz 640 --no-export --force 2>&1 | tail -3
mv $G/runs/yolo11s $G/runs/fire_human_only 2>/dev/null
{ echo "=== human_only 타일 ==="; $PY $W/vms/score_kisa.py $G/runs/fire_human_only/weights/best.pt \
  --videos $W/vms/data/원본데이터/kisa_배포_방화채점셋/videos --gt $W/vms/data/원본데이터/kisa_배포_방화채점셋/gt --stride 0.5 --imgsz 640 --tiles --tag "human_only"; } > $G/EXP1_HUMAN_ONLY.txt 2>&1
log "실험1 완료"

# 2) 사람라벨 + 고해상도(960) — 작은 불에 해상도 효과 재검증
wait_gpu; log "실험2: 사람라벨혼합 960"
$PY model.py train --models yolo11s --data $G/data/학습데이터/mix_human_full/data.yaml --project $G/runs \
  --device 0 --batch 64 --epochs 60 --imgsz 960 --multi-scale --no-export --force 2>&1 | tail -3
mv $G/runs/yolo11s $G/runs/fire_human_960 2>/dev/null
{ echo "=== human960 타일 ==="; $PY $W/vms/score_kisa.py $G/runs/fire_human_960/weights/best.pt \
  --videos $W/vms/data/원본데이터/kisa_배포_방화채점셋/videos --gt $W/vms/data/원본데이터/kisa_배포_방화채점셋/gt --stride 0.5 --imgsz 960 --tiles --tag "human960"; } > $G/EXP2_HUMAN_960.txt 2>&1
log "실험2 완료"

# 3) 배회 트랙 덤프 완료 후 스펙 규칙(마지막사람+10초) 채점용 대기
log "전체 큐 종료"
