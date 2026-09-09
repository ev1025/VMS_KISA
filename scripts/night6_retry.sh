#!/bin/bash
# night6 본 큐가 끝난 뒤 놓친 fa_fire(첫에폭 3개 겹쳐 OOM사) 를 단독 재시도. 이제 .npy 대부분 있어 안전.
W=/NHNHOME/WORKSPACE/26mss002_E3; G=$W/vms; PY=$W/vms/.venv/bin/python
export OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=1
while pgrep -f "night6_fast.sh" >/dev/null; do sleep 300; done
[ -s $G/results/par/RULE2_fa_fire960.txt ] && { echo "이미 완료"; exit; }
echo "[$(date +%H:%M)] fa_fire 단독 재시도"
( cd $W/vms && $PY model.py train --models yolo11s --data $G/data/학습데이터/_par/fa_fire_960/data.yaml \
    --project $G/runs/par/fa_fire960 --device 0 --batch 128 --epochs 30 --imgsz 640 --no-export --force \
    --cache disk --workers 16 --extra multi_scale=0.5 ) > $G/logs/par_fa_fire960.log 2>&1
$PY $G/scripts/fire_detail.py $G/runs/par/fa_fire960/yolo11s/weights/best.pt --tag fa_fire960 --tiles > $G/results/par/DETAIL_fa_fire960.txt 2>&1
$PY $G/scripts/fire_rule2.py fa_fire960 2>&1 | sed -n "/규칙 스윕/,\$p" > $G/results/par/RULE2_fa_fire960.txt
echo "[$(date +%H:%M)] fa_fire 완료: $(sed -n 2p $G/results/par/RULE2_fa_fire960.txt)"
