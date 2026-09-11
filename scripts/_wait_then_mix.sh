#!/bin/bash
# 방화 큐 러너(queue_fire_20260909)가 끝날 때까지 기다린 뒤 혼합 큐를 동시 2잡으로 시작한다.
cd /NHNHOME/WORKSPACE/26mss002_E3/vms
while pgrep -f '[e]xp_queue.py run configs/queue_fire' >/dev/null; do sleep 300; done
echo "[$(TZ=Asia/Seoul date '+%m-%d %H:%M KST')] 방화 큐 종료 확인 → 혼합 큐 시작" >> logs/queue/runner_mix.log
exec .venv/bin/python scripts/exp_queue.py run configs/queue_mix_20260911.yaml --jobs 2 >> logs/queue/runner_mix.log 2>&1
