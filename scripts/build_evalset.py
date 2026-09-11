# -*- coding: utf-8 -*-
"""검증셋 빌더: 채점 전용 카테고리(use: eval)에서 사람이 대시보드로 친 손라벨(eval 표시 행)만 모아 mAP 검증셋을 만든다.
학습셋 빌더(build_trainset.py)는 이 행들을 항상 제외하므로 학습과 겹치지 않는다. 학습에 절대 넣지 않는다(검증 전용).
  입력  data/학습데이터/손라벨/{fire,person}_labels.json 의 eval: true 행 (cls -1 = 검토완료 → 박스 없는 배경 프레임으로 포함)
  출력  data/학습데이터/evalset_<mode>/{images,labels}/ + val.txt + meta.json
  사용  python scripts/build_evalset.py fire|person [--name evalset_fire]
러너(exp_queue.py)는 defaults.val_set 에 이 val.txt 경로를 주면 val_small 대신 이걸 검증셋으로 쓴다."""
import sys, io, json, argparse, collections, time
from pathlib import Path
import cv2
V = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(V / "dash_v2")); import gt_adapters as GTA
ap = argparse.ArgumentParser(); ap.add_argument("mode", choices=["fire", "person"]); ap.add_argument("--name", default=None); a = ap.parse_args()
RAW = V / "data/원본데이터"; D = GTA.Datasets(V / "configs/datasets.yaml", RAW)
NAME = a.name or f"evalset_{a.mode}"; OUT = V / "data/학습데이터" / NAME
NAMES = ["fire", "smoke"] if a.mode == "fire" else ["person"]
rows = json.load(io.open(V / f"data/학습데이터/손라벨/{a.mode}_labels.json", encoding="utf-8"))
frames = collections.defaultdict(list); stats = collections.Counter()
for r in rows:
    if not r.get("eval"): continue
    key = (r["clip"], round(float(r["t"]) * 2) / 2)
    if int(r.get("cls", -1)) >= 0: frames[key].append((int(r["cls"]), [r["x"], r["y"], r["w"], r["h"]]))
    else: frames.setdefault(key, [])                       # 검토완료 = 배경 프레임(박스 0) → 오탐을 재는 데 필요하다
def clip_full(stem):
    return next(RAW.rglob(stem + ".mp4"), None)
(OUT / "images").mkdir(parents=True, exist_ok=True); (OUT / "labels").mkdir(parents=True, exist_ok=True)
lst = []; caps = {}; vid = {}
for (stem, t), boxes in sorted(frames.items()):
    mp4 = vid.get(stem)
    if mp4 is None: mp4 = clip_full(stem); vid[stem] = mp4 or False
    if not mp4: stats["영상 없음"] += 1; continue
    cat = mp4.relative_to(RAW).parts[0]
    if D.get(cat).get("use") != "eval": stats[f"제외:use!=eval({cat})"] += 1; continue   # 채점 전용 카테고리 밖의 eval 표시는 안 쓴다
    jp = OUT / "images" / f"{stem}_{t:g}.jpg"
    if not jp.exists():
        cap = caps.get(mp4) or caps.setdefault(mp4, cv2.VideoCapture(str(mp4)))
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        cap.set(cv2.CAP_PROP_POS_FRAMES, max(int(round(t * fps)), 0)); ok, fr = cap.read()
        if not ok: stats["프레임 읽기 실패"] += 1; continue
        cv2.imwrite(str(jp), fr, [int(cv2.IMWRITE_JPEG_QUALITY), 95])
    (OUT / "labels" / f"{jp.stem}.txt").write_text("".join("%d %.6f %.6f %.6f %.6f\n" % (c, b[0] + b[2] / 2, b[1] + b[3] / 2, b[2], b[3]) for c, b in boxes))
    lst.append(str(jp)); stats["배경" if not boxes else "박스 프레임"] += 1
for c in caps.values(): c.release()
(OUT / "val.txt").write_text("\n".join(lst) + "\n")
meta = {"name": NAME, "mode": a.mode, "built": time.strftime("%F %T"), "frames": len(lst), "clips": len({Path(p).stem.rsplit("_", 1)[0] for p in lst}),
        "boxes": sum(len(b) for b in frames.values()), "source": "손라벨 eval 행(채점 전용 카테고리)", "use": "검증 전용. 학습 금지", "stats": dict(stats)}
(OUT / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
print(f"완료 → {OUT}  프레임 {len(lst)} (박스 {stats['박스 프레임']} · 배경 {stats['배경']}) · 클립 {meta['clips']} · 박스 {meta['boxes']}  {dict(stats)}")
