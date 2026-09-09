# -*- coding: utf-8 -*-
"""범용 시계열 창분류기 (방화/쓰러짐 공용). 연성 경계 라벨 + 창끝 로짓 + LOOCV 임계.

딥리서치 채택: 20-step 정적 입력, Conv1D+BiGRU(<1M), soft boundary(창 겹침 비율 라벨).
fall_seq_train 을 일반화: 피처차원·onset규정(fire=+10초, fall=즉시)만 인자.
사용: python seq_train.py --feats <dir> --dim 20 --deploy-prefix C00_ --sa-delay 10 --out <dir>
"""
import argparse
import random
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn


def build_net(dim):
    class SeqNet(nn.Module):
        def __init__(self):
            super().__init__()
            self.conv = nn.Sequential(
                nn.Conv1d(dim, 96, 5, padding=2), nn.ReLU(),
                nn.Conv1d(96, 96, 5, padding=2), nn.ReLU())
            self.gru = nn.GRU(96, 96, num_layers=2, batch_first=True,
                              bidirectional=True, dropout=0.3)
            self.drop = nn.Dropout(0.5)
            self.head = nn.Linear(192, 1)

        def forward(self, x):
            h = self.conv(x.transpose(1, 2)).transpose(1, 2)
            h, _ = self.gru(h)
            return self.head(self.drop(h[:, -1])).squeeze(-1)
    return SeqNet()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--feats", required=True)
    ap.add_argument("--dim", type=int, required=True)
    ap.add_argument("--win", type=int, default=20)
    ap.add_argument("--deploy-prefix", default="C00_")
    ap.add_argument("--sa-delay", type=float, default=0.0, help="onset→SA 지연(방화 10초)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--epochs", type=int, default=15)
    a = ap.parse_args()

    random.seed(0)
    torch.manual_seed(0)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    WIN = a.win

    train, deploy = [], []
    for p in sorted(Path(a.feats).glob("*.npz")):
        z = np.load(p)
        item = (p.stem, z["t"], z["x"], float(z["gt_start"]), float(z["gt_dur"]))
        (deploy if p.stem.startswith(a.deploy_prefix) else train).append(item)
    print(f"학습 {len(train)} · 배포검증 {len(deploy)}", flush=True)

    def windows(t, x, gt, dur):
        out_ = []
        for e in range(WIN, len(t)):
            seg = x[e - WIN:e]
            t0, t1 = t[e - WIN], t[e - 1]
            if gt < 0:
                out_.append((seg, 0.0)); continue
            ov = max(0.0, min(t1, gt + max(dur, 5)) - max(t0, gt))
            frac = ov / (t1 - t0 + 1e-6)
            if frac >= 0.5:
                out_.append((seg, 1.0))
            elif ov == 0:
                out_.append((seg, 0.0))
        return out_

    pos, neg = [], []
    for _, t, x, gt, dur in train:
        if len(t) < WIN + 1:
            continue
        for seg, y in windows(t, x, gt, dur):
            (pos if y else neg).append(seg)
    random.shuffle(neg)
    neg = neg[:len(pos) * 3]
    print(f"창 양성 {len(pos)} · 음성 {len(neg)}", flush=True)
    if not pos:
        print("양성 없음 - 중단"); return

    X = torch.tensor(np.stack(pos + neg), dtype=torch.float32)
    Y = torch.tensor([1.0] * len(pos) + [0.0] * len(neg))
    idx = torch.randperm(len(X)); X, Y = X[idx], Y[idx]

    dev = "cuda" if torch.cuda.is_available() else "cpu"
    net = build_net(a.dim).to(dev)
    opt = torch.optim.AdamW(net.parameters(), lr=1e-3, weight_decay=1e-2)
    lossf = nn.BCEWithLogitsLoss()
    B = 512
    for ep in range(a.epochs):
        net.train(); tot = 0.0
        for i in range(0, len(X), B):
            xb, yb = X[i:i + B].to(dev), Y[i:i + B].to(dev)
            opt.zero_grad(); loss = lossf(net(xb), yb); loss.backward(); opt.step()
            tot += float(loss) * len(xb)
        print(f"ep{ep+1}: loss {tot/len(X):.4f}", flush=True)
    torch.save(net.state_dict(), out / "seq.pt")

    net.eval()
    logits = {}
    with torch.no_grad():
        for stem, t, x, gt, dur in deploy:
            if len(t) < WIN + 1:
                continue
            segs = np.stack([x[e - WIN:e] for e in range(WIN, len(t))])
            lo = []
            for i in range(0, len(segs), B):
                lo.append(net(torch.tensor(segs[i:i+B], dtype=torch.float32).to(dev)).cpu().numpy())
            logits[stem] = (t[WIN:], np.concatenate(lo), gt)

    def score(th, names):
        tp = fn = fp = 0
        for s in names:
            t, lg, gt = logits[s]
            over = np.nonzero(lg >= th)[0]
            o = (float(t[over[0]]) + a.sa_delay) if len(over) else None
            if o is None: fn += 1
            elif gt - 2 <= o <= gt + 10: tp += 1
            else: fp += 1; fn += 1
        r = tp/(tp+fn) if tp+fn else 0; p = tp/(tp+fp) if tp+fp else 0
        return (2*r*p/(r+p)*100 if r+p else 0, tp, fn, fp)

    ths = [x * 0.5 for x in range(-2, 9)]
    print("\n== 전수 ==", flush=True)
    names = list(logits)
    for th in ths:
        f1, tp, fn, fp = score(th, names)
        print(f"  th {th:+.1f} → {f1:6.2f} (정검 {tp} 미검 {fn} 오검 {fp})", flush=True)
    from collections import Counter
    chosen = Counter(); TP=FN=FP=0
    for h in names:
        rest = [s for s in names if s != h]
        best = max(ths, key=lambda th: score(th, rest)[0])
        chosen[best] += 1
        _, tp, fn, fp = score(best, [h]); TP+=tp; FN+=fn; FP+=fp
    r = TP/(TP+FN) if TP+FN else 0; p = TP/(TP+FP) if TP+FP else 0
    print(f"\nLOOCV 종합: {2*r*p/(r+p)*100 if r+p else 0:.2f} (정검 {TP} 미검 {FN} 오검 {FP})", flush=True)
    print("임계 분포:", dict(chosen), flush=True)


if __name__ == "__main__":
    main()
