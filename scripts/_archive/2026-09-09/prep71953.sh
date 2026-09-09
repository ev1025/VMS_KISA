#!/bin/bash
W=/NHNHOME/WORKSPACE/26mss002_E3; G=$W/vms; PY=$W/vms/.venv/bin/python
D=$G/datasets/aihub71953
log(){ echo "[$(date +%H:%M)] $*"; }
while tmux has-session -t dl71953 2>/dev/null; do sleep 300; done
log "71953 다운로드 종료, 압축해제"
cd $D
find . -name "*.zip" | while read z; do unzip -o -q "$z" -d "${z%.zip}" 2>/dev/null; done
log "압축해제 완료. 라벨 형식·야간 확인"
$PY - <<PYEOF > $G/PREP71953.txt 2>&1
import glob, json, os
from collections import Counter
D = "$D"
js = glob.glob(D + "/**/*.json", recursive=True)[:2000]
print("json 라벨 파일:", len(glob.glob(D + "/**/*.json", recursive=True)))
mp4 = glob.glob(D + "/**/*.mp4", recursive=True)
print("mp4:", len(mp4))
# 라벨 하나 구조
if js:
    d = json.load(open(js[0], encoding="utf-8"))
    print("라벨 키:", list(d)[:15] if isinstance(d, dict) else type(d))
    print(json.dumps(d, ensure_ascii=False)[:800])
PYEOF
log "완료 → PREP71953.txt"
