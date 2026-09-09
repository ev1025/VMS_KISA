#!/bin/bash
set -e
W=/NHNHOME/WORKSPACE/26mss002_E3; G=$W/vms; PY=$W/vms/.venv/bin/python
while tmux has-session -t fireseq 2>/dev/null; do sleep 120; done
$PY $G/scripts/server_tdump.py --videos "$G/datasets/deploy_val/침입(30개)/배포" --model $G/model/person_v2.pt --out $G/dumps/intrusion_v2_tile --stride 0.5 --conf 0.20 --tiles
echo "타일 덤프 완료"
