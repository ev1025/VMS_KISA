#!/bin/bash
W=/NHNHOME/WORKSPACE/26mss002_E3; G=$W/vms; PY=$W/vms/.venv/bin/python
log(){ echo "[$(date +%m-%d\ %H:%M)] $*"; }
# 1) RT-DETR 끝날 때까지
while tmux has-session -t rtdetr 2>/dev/null; do sleep 180; done
log "RT-DETR 종료 감지, 큐 시작"

# 2) 화재 FASDD (사용자 최우선) — fire_fasdd.sh 본체를 인라인 호출(자체 rtdetr 대기 없음 버전)
log "화재 FASDD 학습 3종 시작"
bash $G/scripts/fire_fasdd_core.sh > $G/firefasdd.log 2>&1
log "화재 FASDD 완료"

# 3) 쓰러짐 원시 키포인트 추출
log "쓰러짐 키포인트 추출"
FALLDIR=$(ls -d $G/datasets/rnd_person/*쓰러짐* 2>/dev/null | head -1)
DEPLOY=$(ls -d $G/datasets/deploy_val/*쓰러짐* 2>/dev/null | head -1)
$PY $G/scripts/fall_kpts.py --videos "$FALLDIR" "$DEPLOY" --out $G/feats/fall_kpts --stride 0.1 --maxp 5 > $G/fallkpt.log 2>&1
log "키포인트 $(ls $G/feats/fall_kpts 2>/dev/null | wc -l) npz"

# 4) PoseC3D 학습·평가
log "PoseC3D 학습"
$PY $G/scripts/posec3d_train.py > $G/POSEC3D.txt 2>&1
log "PoseC3D 완료"
log "=== 전체 큐 종료 ==="
