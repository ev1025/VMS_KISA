#!/bin/bash
# pose v1 체인: 키포인트 의사라벨 → 11s-pose 학습 → 쓰러짐 kpt 덤프 + 침입/배회 박스 덤프
set -e
W=/NHNHOME/WORKSPACE/26mss002_E3
G=$W/vms
PY=$W/vms/.venv/bin/python
log(){ echo "[$(date +%H:%M)] $*"; }

log "1) 키포인트 의사라벨 (교사 yolo11x-pose)"
$PY $G/scripts/pl_pose.py --src $G/datasets/person_pl --out $G/datasets/person_pose

log "2) yolo11s-pose 학습"
cd $W/vms
$PY model.py train --models yolo11s-pose --data $G/datasets/person_pose/data.yaml --project $G/runs \
  --device 0 --batch 128 --epochs 60 --imgsz 640 --multi-scale --no-export
mv $G/runs/yolo11s-pose $G/runs/pose_v1

log "3) 쓰러짐 10편 키포인트 덤프"
M=$G/runs/pose_v1/weights/best.pt
$PY $G/scripts/server_kptdump.py --videos "$G/datasets/deploy_val/쓰러짐(10개)/배포" --model $M --out $G/dumps/fall_pose_v1

log "4) 침입·배회 박스 덤프 (pose 모델 단일 서빙 검증)"
$PY $G/scripts/server_pdump.py --videos "$G/datasets/deploy_val/침입(30개)/배포" --model $M --out $G/dumps/intrusion_pose
$PY $G/scripts/server_pdump.py --videos "$G/datasets/deploy_val/배회(30개)/배포" --model $M --out $G/dumps/loiter_pose
log "전체 완료"
