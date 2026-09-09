#!/bin/bash
# 제미나이 20일 플랜 Day1~3 상당: 쓰러짐 1D 피처(340편) → 침입/배회 트랙 덤프(0.5s, botsort)
set -e
W=/NHNHOME/WORKSPACE/26mss002_E3
G=$W/vms
PY=$W/vms/.venv/bin/python
log(){ echo "[$(date +%H:%M)] $*"; }

log "1) 쓰러짐 1D 피처 추출 (해외 330 + 배포 10)"
$PY $G/scripts/fall_feats.py --videos "$G/datasets/rnd_person/4. 쓰러짐(330개)" "$G/datasets/deploy_val/쓰러짐(10개)/배포" --out $G/feats/fall_seq

log "2) 침입 트랙 덤프 (person_v3, 0.5s, botsort)"
$PY $G/scripts/server_tdump.py --videos "$G/datasets/deploy_val/침입(30개)/배포" --model $G/model/person_v3.pt --out $G/dumps/intrusion_trk --stride 0.5 --conf 0.10

log "3) 배회 트랙 덤프 (person_v2, 0.5s, botsort)"
$PY $G/scripts/server_tdump.py --videos "$G/datasets/deploy_val/배회(30개)/배포" --model $G/model/person_v2.pt --out $G/dumps/loiter_trk --stride 0.5 --conf 0.10
log "전체 완료"
