# -*- coding: utf-8 -*-
"""방화 K-fold 실험 매트릭스.
   사람라벨(384박스/72클립)을 클립 단위 5-fold 로 나눠, 데이터 구성별 효과를 공정 비교.
   구성: 사람라벨만 / +24k / +합성증강 / 오버샘플 배수 / 해상도.
   각 fold 는 KISA 배포 10편으로 채점하지 않고(고정 소량), 홀드아웃 클립의 프레임 검출로 비교."""
import json, math, random, shutil, subprocess, sys
from collections import defaultdict
from pathlib import Path

W = Path("/NHNHOME/WORKSPACE/26mss002_E3"); G = W/"vms"
HUMAN = G/"data/학습데이터/human_fire"
WORK = G/"data/학습데이터/kfold"
RUNS = G/"runs/kfold"
PY = str(W/"vms/.venv/bin/python")
K = 5


def clips_of():
    rows = json.load(open(G/"data/학습데이터/손라벨/fire_labels.json", encoding="utf-8"))
    return sorted({r["clip"] for r in rows})


def build(fold, mode, oversample):
    """fold 홀드아웃 제외한 클립으로 학습셋 구성. 심링크 대신 이미지 목록 txt(Lustre 메타데이터 느림·중복 줄 = 오버샘플)"""
    clips = clips_of(); random.Random(0).shuffle(clips)
    test = set(clips[fold::K]); train = [c for c in clips if c not in test]
    ds = WORK/f"f{fold}_{mode}"
    if ds.exists(): shutil.rmtree(ds)
    ds.mkdir(parents=True, exist_ok=True)
    tr, va = [], []
    for img in sorted((HUMAN/"images/train").glob("*.jpg")):
        clip = "_".join(img.stem.split("_")[:2])
        if not (HUMAN/"labels/train"/(img.stem+".txt")).exists(): continue
        if clip in test: va.append(str(img))
        else: tr += [str(img)] * oversample
    n_tr, n_va = len(tr), len(va)
    if mode in ("mix24k", "mix24k_aug"):
        for img in sorted((G/"data/학습데이터/dataset_24k/images/train").glob("*.jpg")):
            if (G/"data/학습데이터/dataset_24k/labels/train"/(img.stem+".txt")).exists():
                tr.append(str(img)); n_tr += 1
    NL = chr(10)
    (ds/"train.txt").write_text(NL.join(tr)+NL); (ds/"val.txt").write_text(NL.join(va)+NL)
    (ds/"data.yaml").write_text(NL.join([f"path: {ds}", "train: train.txt", "val: val.txt", "nc: 2", "names: ['fire','smoke']"])+NL)
    return ds, n_tr, n_va, sorted(test)


def run(ds, name, imgsz, epochs, aug):
    cmd = [PY, "model.py", "train", "--models", "yolo11s", "--data", str(ds/"data.yaml"),
           "--project", str(RUNS), "--device", "0", "--batch", "64",
           "--epochs", str(epochs), "--imgsz", str(imgsz), "--no-export", "--force", "--cache", "ram", "--workers", "8"]
    if aug: cmd += ["--extra", "multi_scale=0.5"]   # 8.4: bool True=0~1280px
    subprocess.run(cmd, cwd=str(W/"vms"), capture_output=True)
    src = RUNS/"yolo11s"
    if src.exists():
        dst = RUNS/name
        if dst.exists(): shutil.rmtree(dst)
        src.rename(dst)
        return dst
    return None


def val_map(run_dir, ds):
    """홀드아웃(val) 에서 mAP50 측정"""
    out = subprocess.run([PY, "-c", f"""
from ultralytics import YOLO
m = YOLO(r'{run_dir}/weights/best.pt')
r = m.val(data=r'{ds}/data.yaml', imgsz=640, device=0, verbose=False, plots=False)
print('MAP50', float(r.box.map50), 'MAP', float(r.box.map))
try:
    print('FIRE_AP50', float(r.box.ap50[0]))
except Exception: pass
"""], capture_output=True, text=True)
    return out.stdout.strip()


def main():
    modes = sys.argv[1:] if len(sys.argv) > 1 else ["human", "mix24k"]
    for mode in modes:
        over = 5 if mode.startswith("mix") else 1
        print(f"\n########## 구성: {mode} (오버샘플 {over}) ##########", flush=True)
        for fold in range(K):
            ds, ntr, nva, test = build(fold, mode, over)
            name = f"f{fold}_{mode}"
            rd = run(ds, name, 640, 60, aug=True)
            res = val_map(rd, ds) if rd else "학습실패"
            print(f"  fold{fold}: train {ntr} · val {nva} · 홀드아웃클립 {len(test)} → {res}", flush=True)


if __name__ == "__main__":
    main()
