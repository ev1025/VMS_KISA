#!/bin/bash
set -e
W=/NHNHOME/WORKSPACE/26mss002_E3
G=$W/vms
PY=$W/vms/.venv/bin/python
M=$G/runs/person_v1/weights/best.pt
$PY $G/scripts/server_pdump.py --videos "$G/datasets/deploy_val/배회(30개)/배포" --model $M --out $G/dumps/loiter_v1
$PY $G/scripts/server_pdump.py --videos "$G/datasets/deploy_val/쓰러짐(10개)/배포" --model $M --out $G/dumps/fall_v1
echo "덤프 완료"
