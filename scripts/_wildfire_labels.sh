#!/bin/bash
# TL.zip(라벨)에서 frames 매칭 json 만 추출 → YOLO txt(화염0·연기1)로 변환해 프레임 옆에 저장.
V=/NHNHOME/WORKSPACE/26mss002_E3/vms
D=$V/data/원본데이터/aihub71330_산불
TL=$D/TL.zip; F=$D/frames
log(){ echo "[$(date +%m-%d\ %H:%M)] $*"; }

log "frames 이미지 → 매칭 json 목록 생성"
find "$F" -iname "*.jpg" | sed "s#$F/##; s#\.jpg\$#.json#" > /tmp/wf_lab.txt
n=$(wc -l < /tmp/wf_lab.txt); log "대상 json $n 개"
[ "$n" -lt 100 ] && { log "목록 비정상 중단"; exit 1; }

log "TL.zip 에서 해당 json 만 추출(→ frames 안, jpg 옆)"
7z x "$TL" -o"$F" @/tmp/wf_lab.txt -y -bsp1 > "$V/logs/wf_labels_7z.log" 2>&1
got=$(find "$F" -iname "*.json" | wc -l); log "추출된 json $got 개 → 변환 시작"

$V/.venv/bin/python - <<"PY"
import json, os, pathlib
F = pathlib.Path("/NHNHOME/WORKSPACE/26mss002_E3/vms/data/원본데이터/aihub71330_산불/frames")
def cls_of(name):
    if "화염" in name: return 0
    if "구름" in name or "안개" in name: return None   # 구름·안개 = 연기 아님(하드네거)
    if "연기" in name: return 1   # 굴뚝 포함 모든 실제 연기 = smoke
    return None
made = empty = 0
for jp in F.rglob("*.json"):
    try:
        d = json.load(open(jp, encoding="utf-8"))
    except Exception:
        os.remove(jp); continue
    cats = {c["id"]: c.get("name", "") for c in d.get("categories", [])}
    W = d["images"][0]["width"]; H = d["images"][0]["height"]
    lines = []
    for a in d.get("annotations", []):
        c = cls_of(cats.get(a.get("category_id"), ""))
        if c is None: continue
        x, y, w, h = a["bbox"]
        cx = (x + w / 2) / W; cy = (y + h / 2) / H
        lines.append("%d %.6f %.6f %.6f %.6f" % (c, cx, cy, w / W, h / H))
    txt = jp.with_suffix(".txt")
    txt.write_text("\n".join(lines), encoding="utf-8")   # 음성이면 빈 파일
    if lines: made += 1
    else: empty += 1
    os.remove(jp)
print("변환 완료: 박스있는 txt %d, 빈(음성) txt %d" % (made, empty))
PY
log "WILDFIRE LABELS DONE"
