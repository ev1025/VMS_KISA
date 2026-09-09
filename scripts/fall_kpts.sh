#!/bin/bash
set -e
W=/NHNHOME/WORKSPACE/26mss002_E3; G=/NHNHOME/WORKSPACE/26mss002_E3/vms; PY=/NHNHOME/WORKSPACE/26mss002_E3/vms/.venv/bin/python
while tmux has-session -t rtdetr 2>/dev/null; do sleep 300; done   # RT-DETR 뒤
FALLDIR=$(ls -d $G/datasets/rnd_person/*쓰러짐* 2>/dev/null | head -1)
DEPLOY=$(ls -d $G/datasets/deploy_val/*쓰러짐* 2>/dev/null | head -1)
echo "[$(date +%H:%M)] 쓰러짐 원시 키포인트 추출: $FALLDIR + $DEPLOY"
$PY $G/scripts/fall_kpts.py --videos "$FALLDIR" "$DEPLOY" --out $G/feats/fall_kpts --stride 0.1 --maxp 5
echo "[$(date +%H:%M)] 완료 → $(ls $G/feats/fall_kpts | wc -l) npz"
