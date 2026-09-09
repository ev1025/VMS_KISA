#!/bin/bash
# par_fire.sh(직접 학습 6종) 종료 후 드라이버 실험(K-fold·비율·장소홀드아웃) 순차 실행
W=/NHNHOME/WORKSPACE/26mss002_E3; G=$W/vms; PY=$W/vms/.venv/bin/python
export OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=1
log(){ echo "[$(date +%m-%d\ %H:%M)] $*"; }
while pgrep -f "par_fire.sh" >/dev/null; do sleep 120; done
log "human_only best/last 채점(학습 중 런처 재시작으로 채점 누락 + 24k val 기준 best 는 도메인 무관)"
{ echo "=== human_only 타일 ==="; $PY $W/vms/score_kisa.py $G/runs/par/human_only/yolo11s/weights/best.pt --videos $W/vms/data/원본데이터/kisa_배포_방화채점셋/videos --gt $W/vms/data/원본데이터/kisa_배포_방화채점셋/gt --stride 0.5 --imgsz 640 --tiles --tag human_only; } > $G/results/par/EXP_human_only.txt 2>&1
{ echo "=== human_only_last 타일 ==="; $PY $W/vms/score_kisa.py $G/runs/par/human_only/yolo11s/weights/last.pt --videos $W/vms/data/원본데이터/kisa_배포_방화채점셋/videos --gt $W/vms/data/원본데이터/kisa_배포_방화채점셋/gt --stride 0.5 --imgsz 640 --tiles --tag human_only_last; } > $G/results/par/EXP_human_only_last.txt 2>&1
log "A: K-fold"; $PY $G/scripts/fire_kfold.py human mix24k > $G/results/par/FIRE_KFOLD.txt 2>&1
log "D: 비율 스윕"; $PY $G/scripts/fire_matrix2.py ratio > $G/results/par/FIRE_RATIO.txt 2>&1
log "E: 장소 홀드아웃"; $PY $G/scripts/fire_matrix2.py loo > $G/results/par/FIRE_LOO.txt 2>&1
log "드라이버 전체 완료"
