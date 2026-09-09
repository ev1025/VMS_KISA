# -*- coding: utf-8 -*-
"""FASDD 5-fold 학습 → 매번 배포 10편으로 채점. FASDD 가 운으로 도운 건지 실제로 도운 건지 가른다.

기존 K-fold 는 홀드아웃의 mAP 를 봤는데, 오늘 확인된 대로 24k·FASDD 검증 mAP 와 배포 F1 은 역상관이라
mAP 로는 판단할 수 없다. 그래서 fold 마다 배포 10편을 실제 채점(새 규칙)해서 F1 의 평균과 분산을 본다.
  - fold k: FASDD 를 5등분해 k 번째를 빼고 나머지 4/5 만 학습에 사용 (24k·손라벨은 항상 전량)
  - 5개 fold 의 배포 F1 이 고르게 높으면 FASDD 효과가 실재, 들쭉날쭉하면 우연
"""
import json
import random
import subprocess
import sys
from pathlib import Path

W = Path("/NHNHOME/WORKSPACE/26mss002_E3")
G = W / "vms"
PY = str(W / "vms/.venv/bin/python")
HARD = G / "data/학습데이터/_hard"
WORK = G / "data/학습데이터/_kf"
RUNS = G / "runs/kf"
RES = G / "results/par"
K = 5
NL = chr(10)


def lines(p):
    return [l for l in Path(p).read_text().splitlines() if l.strip()]


def build(fold):
    """fold 번째 조각을 뺀 FASDD + 24k 전량 + 손라벨 x5"""
    fa = lines(HARD / "fasdd_all.txt")
    random.Random(0).shuffle(fa)
    held = set(fa[fold::K])
    use = [p for p in fa if p not in held]

    k24 = sorted((G / "data/학습데이터/dataset_24k/images/train").glob("*.jpg"))
    hf = sorted((G / "data/학습데이터/human_fire/images/train").glob("*.jpg"))

    ds = WORK / f"f{fold}"
    if ds.exists():
        import shutil; shutil.rmtree(ds)
    (ds / "images/train").mkdir(parents=True, exist_ok=True)
    (ds / "labels/train").mkdir(parents=True, exist_ok=True)
    # labels.cache 를 fold 별로 분리하려고 선두 파일 1개만 자기 폴더에 둔다
    import os
    os.symlink(hf[0], ds / "images/train/000.jpg")
    os.symlink(G / "data/학습데이터/human_fire/labels/train" / (hf[0].stem + ".txt"), ds / "labels/train/000.txt")

    tr = [str(ds / "images/train/000.jpg")]
    tr += [str(p) for p in k24]
    for _ in range(5):
        tr += [str(p) for p in hf]
    tr += use
    (ds / "train.txt").write_text(NL.join(tr) + NL)
    (ds / "data.yaml").write_text(NL.join([
        f"path: {ds}", "train: train.txt",
        f"val: {G}/data/학습데이터/_par/val_small.txt", "nc: 2", "names: ['fire','smoke']"]) + NL)
    return ds, len(tr), len(held)


def train(ds, name, epochs):
    subprocess.run([PY, "model.py", "train", "--models", "yolo11s", "--data", str(ds / "data.yaml"),
                    "--project", str(RUNS / name), "--device", "0", "--batch", "96",
                    "--epochs", str(epochs), "--imgsz", "640", "--no-export", "--force",
                    "--cache", "ram", "--workers", "8", "--extra", "multi_scale=0.5"],
                   cwd=str(W / "vms"), capture_output=True)
    return RUNS / name / "yolo11s/weights/best.pt"


def score(weights, name):
    """배포 10편 신호 시계열 저장 → 새 규칙 스윕. 최고 F1 과 그 설정을 돌려준다."""
    subprocess.run([PY, str(G / "scripts/fire_detail.py"), str(weights), "--tag", name, "--tiles"],
                   capture_output=True)
    out = subprocess.run([PY, str(G / "scripts/fire_rule2.py"), name],
                         capture_output=True, text=True).stdout
    best = None
    for ln in out.splitlines():
        s = ln.strip()
        if s and s[0].isdigit() and "정검" in s:
            best = s
            break
    return best, out


def main():
    epochs = int(sys.argv[1]) if len(sys.argv) > 1 else 50
    WORK.mkdir(parents=True, exist_ok=True)
    RUNS.mkdir(parents=True, exist_ok=True)
    rows = []
    for fold in range(K):
        ds, ntr, nheld = build(fold)
        print(f"[fold{fold}] 학습 {ntr}장 (FASDD 제외 {nheld}장)", flush=True)
        w = train(ds, f"fold{fold}", epochs)
        if not w.exists():
            print(f"  fold{fold} 학습 실패", flush=True); continue
        best, full = score(w, f"kf{fold}")
        print(f"  fold{fold} 배포 최고: {best}", flush=True)
        rows.append((fold, best))
        (RES / f"KFOLD_FASDD_f{fold}.txt").write_text(full, encoding="utf-8")
    print("\n===== FASDD 5-fold 배포 채점 =====", flush=True)
    vals = []
    for fold, best in rows:
        print(f"  fold{fold}: {best}", flush=True)
        try:
            vals.append(float(best.split()[0]))
        except Exception:
            pass
    if vals:
        m = sum(vals) / len(vals)
        var = (sum((v - m) ** 2 for v in vals) / len(vals)) ** 0.5
        print(f"\n  평균 {m:.2f} · 표준편차 {var:.2f} · 최소 {min(vals):.2f} 최대 {max(vals):.2f}", flush=True)
        print("  표준편차가 작으면 FASDD 효과가 실재, 크면 우연", flush=True)


if __name__ == "__main__":
    main()
