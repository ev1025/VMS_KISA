#!/bin/bash
W=/NHNHOME/WORKSPACE/26mss002_E3; G=$W/vms; PY=$W/vms/.venv/bin/python
log(){ echo "[$(date +%H:%M)] $*"; }
log "침입 트랙덤프 (person_v3, ID 포함)"
$PY $G/scripts/server_tdump.py --videos "$G/data/원본데이터/kisa_배포_검증영상/deploy_val/침입(30개)/배포" \
    --model $G/model/person_v3.pt --out $G/dumps/intrusion_trk_id --stride 0.5 --conf 0.20
log "배회 트랙덤프 (person_v2)"
$PY $G/scripts/server_tdump.py --videos "$G/data/원본데이터/kisa_배포_검증영상/deploy_val/배회(30개)/배포" \
    --model $G/model/person_v2.pt --out $G/dumps/loiter_trk_id --stride 0.5 --conf 0.20
log "완료"
