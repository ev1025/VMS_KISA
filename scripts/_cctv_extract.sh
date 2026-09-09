#!/bin/bash
V=/NHNHOME/WORKSPACE/26mss002_E3/vms; C=$V/data/원본데이터/aihub71953_다각도CCTV
LOG=$V/logs/cctv_extract.log
echo "[$(date +%H:%M)] CCTV 추출 시작" > $LOG
T=$C/원천데이터; L=$C/라벨링데이터; mkdir -p "$T" "$L"
# 라벨(작음) 먼저
find $C/dl_retry -name '*.zip' -size +0c 2>/dev/null | while read z; do
  n=$(basename "$z" .zip); echo "[$(date +%H:%M)] 라벨 $n" >> $LOG
  /usr/bin/7z x "$z" -o"$L/$n" -y >/dev/null 2>&1
done
# 원천(대용량 비디오)
find $C/dl_ts -name '*.zip' -size +0c 2>/dev/null | while read z; do
  n=$(basename "$z" .zip); echo "[$(date +%H:%M)] 원천 $n ($(du -sh "$z"|cut -f1))" >> $LOG
  /usr/bin/7z x "$z" -o"$T/$n" -y >/dev/null 2>&1
done
echo "[$(date +%H:%M)] 추출 완료. 잔재 정리" >> $LOG
rm -rf $C/dl_ts $C/dl_retry "$C/21.다각도_CCTV_생활안전_데이터" $C/dl_ts.log $C/dl.log $C/tl.log $C/done.flag 2>/dev/null
echo "[$(date +%H:%M)] 원천 mp4 $(find $T -name '*.mp4'|wc -l) · 라벨 json $(find $L -name '*.json'|wc -l)" >> $LOG
echo "CCTVX DONE" >> $LOG
