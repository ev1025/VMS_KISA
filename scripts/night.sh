#!/bin/bash
# 밤샘 마스터 큐. 이미 도는 par_fire.sh(방화 학습 6종)·par_fire_drivers.sh(K-fold·비율·장소) 와 병행.
# 이 스크립트가 하는 일: 쓰러짐 스펙규칙 재설계 실행 → 방화 모델 전수 규칙 스윕 → 최종 요약표 생성.
W=/NHNHOME/WORKSPACE/26mss002_E3; G=$W/vms; PY=$W/vms/.venv/bin/python
export OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=1
R=$G/results/par; mkdir -p $R $G/logs
log(){ echo "[$(date +%m-%d\ %H:%M)] $*"; }

# ---------- 1. 쓰러짐: 사람별 독립 판정 → 처음 쓰러진 사람 (GPU 가벼움, 방화와 병행) ----------
log "쓰러짐 스펙규칙 시작"
$PY $G/scripts/fall_track.py > $R/FALL_TRACK.txt 2>&1
log "쓰러짐 완료: $(grep -A1 '스펙 방식' $R/FALL_TRACK.txt | tail -1)"

# ---------- 2. 방화 학습 전부 끝나길 대기 ----------
while pgrep -f "par_fire.sh|par_fire_drivers.sh" >/dev/null; do sleep 300; done
log "방화 학습·드라이버 전부 종료"

# ---------- 3. 학습된 방화 모델 전수 규칙 스윕 ----------
# 각 모델의 best.pt 를 배포 10편에 대해 재채점 (score_kisa 내부 규칙 스윕이 임계·N/M 을 훑음)
for d in $G/runs/par/*/yolo11s/weights/best.pt; do
  [ -f "$d" ] || continue
  N=$(echo "$d" | sed -E 's|.*/runs/par/([^/]+)/.*|\1|')
  [ -s "$R/EXP_$N.txt" ] && continue      # 런처가 이미 채점한 건 건너뜀
  log "재채점 $N"
  { echo "=== $N 타일 ==="; $PY $W/vms/score_kisa.py "$d" \
      --videos $W/vms/data/원본데이터/kisa_배포_방화채점셋/videos --gt $W/vms/data/원본데이터/kisa_배포_방화채점셋/gt --stride 0.5 --imgsz 640 --tiles --tag "$N"; } > $R/EXP_$N.txt 2>&1
done
log "방화 재채점 완료"

# ---------- 4. 최종 요약표 ----------
S=$G/results/NIGHT_SUMMARY.txt
{
  echo "=============================================="
  echo " KISA 밤샘 실험 요약  $(date +'%Y-%m-%d %H:%M')"
  echo "=============================================="
  echo
  echo "[방화] 배포 10편 F1 (규칙 스윕 중 최고)"
  printf "  %-22s %8s  %s\n" 실험 F1 "정검/미검/오검"
  for f in $R/EXP_*.txt; do
    [ -f "$f" ] || continue
    N=$(basename "$f" .txt | sed 's/^EXP_//')
    # score_kisa 출력 줄: "  규칙이름   →   F1  (정검 n 미검 n 오검 n)"
    BEST=$(sed 's/\x1b\[[0-9;]*[mK]//g' "$f" | grep -oE '→ +[0-9]+\.[0-9]+ +\(정검 [0-9]+ 미검 [0-9]+ 오검 [0-9]+\)' \
           | sed -E 's/→ +//' | sort -k1 -g -r | head -1)
    printf "  %-22s %s\n" "$N" "${BEST:-결과없음}"
  done
  echo
  echo "[방화] K-fold / 비율 / 장소 홀드아웃"
  for f in FIRE_KFOLD FIRE_RATIO FIRE_LOO; do
    echo "--- $f"; sed 's/\x1b\[[0-9;]*[mK]//g' $R/$f.txt 2>/dev/null | grep -E "fold|홀드아웃|비율|mAP|→" | tail -12
  done
  echo
  echo "[쓰러짐] 사람별 독립 판정 → 처음 쓰러진 사람"
  sed 's/\x1b\[[0-9;]*[mK]//g' $R/FALL_TRACK.txt 2>/dev/null | sed -n '/스펙 방식/,$p' | head -25
  echo
  echo "[참고] 이번 세션 확정 (로컬 채점)"
  echo "  배회  93.1  트랙별 체류 6s → 마지막 배회자 진입 +10s (기존 71.4)"
  echo "  침입  73.5  트랙별 three_foot → 마지막 사람 진입     (기존 58.3)"
  echo "  방화  75.0  파일럿(132장 부분라벨·16에폭) 결합 f0.4/s0.6 (기존 66.7)"
  echo
  echo "[산출물]"
  echo "  방화 채점 원본 : $R/EXP_*.txt"
  echo "  드라이버 원본   : $R/FIRE_KFOLD.txt FIRE_RATIO.txt FIRE_LOO.txt"
  echo "  쓰러짐 원본     : $R/FALL_TRACK.txt  (모델 runs/fall_track/fall_track.pt)"
  echo "  학습 로그       : $G/logs/par_*.log"
} > $S 2>&1
log "요약 생성: $S"
cat $S
