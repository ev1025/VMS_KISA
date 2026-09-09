#!/bin/bash
# AI-Hub 265 산불 원천 TS(631G, 6볼륨 split zip) → 초당 1프레임(30fps 가정, 프레임번호%30==1)만 추출.
# 9개 카테고리(양성 불·연기 + 음성 구름/굴뚝연기/안개연무) 전부. 추출 검증되면 원본 zip 삭제.
V=/NHNHOME/WORKSPACE/26mss002_E3/vms
BASE="$V/data/원본데이터/aihub71330_산불_원천ts"
SRCDIR="$BASE/dl_ts/265.지역안전재난(산불)_방재의_고도화를_위한_대규모_인공지능_데이터베이스_구축/01-1.정식개방데이터/Training/01.원천데이터"
SRC="$SRCDIR/TS.zip"
OUT="$BASE/frames"
log(){ echo "[$(date +%m-%d\ %H:%M)] $*"; }
mkdir -p "$OUT"

log "TS 아카이브 파일목록 읽기(560k+ 항목, 수분 소요)"
7z l -slt "$SRC" 2>/dev/null | grep '^Path = ' | sed 's/^Path = //' | grep '\.jpg$' > /tmp/wf_all.txt
total=$(wc -l < /tmp/wf_all.txt)
log "전체 jpg $total 장"
if [ "$total" -lt 1000 ]; then log "목록 비정상 - 중단"; exit 1; fi

# 프레임번호(마지막 _토큰)%30==1 만 선택 = 초당 1장
awk -F'_' '{ n=$NF; sub(/\.jpg$/,"",n); if ((n+0)%30==1) print }' /tmp/wf_all.txt > /tmp/wf_pick.txt
pick=$(wc -l < /tmp/wf_pick.txt)
log "초당 1장 선택 $pick 장 → 추출 시작"

# 선택 목록만 추출(원본 zip 불변). 내부 폴더구조 유지(카테고리별)
7z x "$SRC" -o"$OUT" @/tmp/wf_pick.txt -y -bsp1 > "$V/logs/wf_7z.log" 2>&1
got=$(find "$OUT" -name '*.jpg' 2>/dev/null | wc -l)
log "추출 완료: $got 장 (목표 $pick)"
find "$OUT" -maxdepth 2 -type d 2>/dev/null | sed "s#$OUT/##" | sort -u | head -20 | while read d; do
  [ -n "$d" ] && echo "  $d : $(find "$OUT/$d" -name '*.jpg' 2>/dev/null | wc -l)장"
done

# 검증: 목표의 90% 이상 나왔으면 원본 zip(631G) 삭제
if [ "$got" -ge $((pick*9/10)) ] && [ "$got" -gt 1000 ]; then
  log "검증 통과 → 원본 TS zip(631G) 삭제"
  rm -f "$SRCDIR"/TS.zip "$SRCDIR"/TS.z0* "$SRCDIR"/TS.z[0-9]*
  # dl_ts 잔재 정리(TL.zip 라벨은 남긴다)
  rm -f "$BASE/dl_ts/ts_dl.log" "$BASE"/z01.log 2>/dev/null
  df -h "$V/data" | tail -1 | awk '{print "  삭제 후 여유 "$4}'
else
  log "검증 미달($got<$pick*0.9) → 원본 zip 보존(수동 확인 필요)"
fi
log "WILDFIRE EXTRACT DONE"
