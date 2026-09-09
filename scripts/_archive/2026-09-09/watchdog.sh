#!/bin/bash
# 밤샘 감시견: 5분마다 상태 기록 + 자원 도둑 정리 + 죽은 큐 재기동.
# 오늘 실제로 겪은 사고들만 막는다(추측 방어 없음):
#   - VS Code 원격 인덱서 rg 가 Lustre 전체를 몇 시간씩 크롤링해 CPU 를 먹음
#   - 학습이 죽어도 워커 프로세스가 VRAM 을 붙잡고 남음
#   - 런처가 통째로 죽으면 밤새 아무것도 안 돎
W=/NHNHOME/WORKSPACE/26mss002_E3; G=$W/vms
LOG=$G/logs/watchdog.log
while true; do
  TS=$(date +'%m-%d %H:%M')

  # 1) VS Code 인덱서 정리
  N=$(pgrep -fc "ripgrep-universal.*--files" 2>/dev/null || echo 0)
  [ "$N" -gt 0 ] && { pkill -f "ripgrep-universal.*--files"; echo "[$TS] rg 인덱서 $N개 정리" >> $LOG; }

  # 2) 고아 워커(부모 없이 VRAM 만 잡은 학습 프로세스) 정리
  for P in $(nvidia-smi --query-compute-apps=pid --format=csv,noheader 2>/dev/null); do
    [ -d /proc/$P ] || continue
    PP=$(awk '{print $4}' /proc/$P/stat 2>/dev/null)
    if [ "$PP" = "1" ] && tr '\0' ' ' < /proc/$P/cmdline 2>/dev/null | grep -q "model.py train"; then
      kill -9 $P; echo "[$TS] 고아 학습 워커 $P 정리" >> $LOG
    fi
  done

  # 3) 큐 생존 확인 (par_fire 는 잡을 다 돌리면 정상 종료하므로, 종료 표시가 없을 때만 재기동)
  if ! pgrep -f "par_fire.sh" >/dev/null && ! grep -q "전체 완료" $G/logs/par_fire.log 2>/dev/null; then
    echo "[$TS] par_fire.sh 비정상 종료 감지 → 재기동" >> $LOG
    nohup bash $G/scripts/par_fire.sh >> $G/logs/par_fire.log 2>&1 < /dev/null &
  fi
  if ! pgrep -f "night.sh" >/dev/null && [ ! -f $G/results/NIGHT_SUMMARY.txt ]; then
    echo "[$TS] night.sh 비정상 종료 감지 → 재기동" >> $LOG
    nohup bash $G/scripts/night.sh >> $G/logs/night.log 2>&1 < /dev/null &
  fi

  # 4) 결과 모으기 (흩어진 파일 -> results/ALL_RESULTS.md 한 장)
  $W/vms/.venv/bin/python $G/scripts/collect_results.py > /dev/null 2>&1

  # 5) 상태 한 줄 기록
  GPU=$(nvidia-smi --query-gpu=utilization.gpu,memory.used --format=csv,noheader | tr -d ' ')
  JOBS=$(pgrep -fc "model.py train" 2>/dev/null || echo 0)
  DONE=$(ls $G/results/par/EXP_*.txt 2>/dev/null | wc -l)
  echo "[$TS] GPU $GPU · 학습프로세스 $JOBS · 채점완료 $DONE · load $(cut -d' ' -f1 /proc/loadavg)" >> $LOG

  [ -f $G/results/NIGHT_SUMMARY.txt ] && { echo "[$TS] 요약 생성됨 → 감시 종료" >> $LOG; break; }
  sleep 300
done
