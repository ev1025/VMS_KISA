# -*- coding: utf-8 -*-
"""실험 큐 러너 (단일 진입점). docs/EXPERIMENTS.md §0 인프라 규약을 코드로 고정한다.

  python scripts/exp_queue.py run configs/queue_fire.yaml [--jobs 3] [--wait-tmux fresh] [--rebuild-human]
  python scripts/exp_queue.py status configs/queue_fire.yaml

큐 파일(yaml) 한 줄 = 실험 하나. 스크립트를 편집하지 않고 실험을 추가한다.
규약: train.txt 목록(심링크 폴더 X) · val_small 600장 · multi_scale=0.5 · --cache ram --workers 8
      오버샘플 = 목록에 경로 반복 · 잡별 000.jpg 로 labels.cache 분리 · 동시 잡 N + VRAM 게이트
산출: runs/<exp>/<model>/weights/best.pt · results/<exp>/{meta.json,score.txt} · logs/queue/<exp>.log
재실행 안전: best.pt 있으면 학습 생략, score.txt 있으면 전부 생략(idempotent).
"""
import argparse, json, os, random, shutil, subprocess, sys, time
from pathlib import Path

import yaml

V = Path(os.environ.get("VMS_ROOT", "/NHNHOME/WORKSPACE/26mss002_E3/vms"))
PY = V / ".venv/bin/python"
TRAIN_DS = V / "data/학습데이터"
RAW_DS = V / "data/원본데이터"
EXP_DIR = V / "_exp"            # 잡별 목록 파일·캐시 (재생성 가능한 임시물)
LOG_DIR = V / "logs/queue"
SCORE_VIDEOS = {"방화": V / "data/원본데이터/kisa_배포_검증영상/deploy_val/방화(10개)/배포"}
IMG_EXT = (".jpg", ".jpeg", ".png")


def _kst(fmt):
    """서버 시계는 UTC. 사람이 읽는 시각은 전부 한국 시간(KST = UTC+9)으로 쓴다."""
    return time.strftime(fmt, time.gmtime(time.time() + 9 * 3600))


def log(msg):
    line = f"[{_kst('%m-%d %H:%M')} KST] {msg}"
    print(line, flush=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    with open(LOG_DIR / "runner.log", "a", encoding="utf-8") as f:
        f.write(line + "\n")


# 데이터셋 탐색 우선순위: 960 사본 > NVMe 미러 > 원본(Lustre)
# 병목은 저장소가 아니라 JPEG 디코딩이다(실측 8워커: 원본 1920 = 261장/초, 960 사본 = 727장/초, 읽기만 하면 1,500장/초).
# 960 = 지금 레시피의 multi_scale 상한(imgsz 640 × 1.5)이라 학습이 쓰는 어떤 크기에서도 화질 손실이 없다.
R960 = Path("/NHNHOME/vms_r960")          # _kisa_port/make_r960.py
MIRROR = Path("/NHNHOME/vms_mirror")      # _kisa_port/mirror_to_nvme.py (읽기 속도는 Lustre 와 거의 같다. 보험용)


def find_dataset(name):
    for root in (TRAIN_DS, RAW_DS):
        for base, mark in ((R960, ".r960_ok"), (MIRROR, ".mirror_ok")):
            d = base / "data" / root.name / name
            if (d / mark).is_file():                    # 변환·복사가 끝난 것만 쓴다
                return d
        d = root / name
        if d.is_dir():
            return d
    raise FileNotFoundError(f"데이터셋 없음: {name}")


def list_images(ds_dir):
    """images/train/*.jpg 또는 images/*.jpg (48k 평면풀). 라벨은 ultralytics 가 /images/→/labels/ 치환으로 찾는다."""
    for sub in ("images/train", "images"):
        d = ds_dir / sub
        if d.is_dir():
            files = sorted(str(p) for p in d.iterdir() if p.suffix.lower() in IMG_EXT)
            if files:
                return files
    raise FileNotFoundError(f"이미지 없음: {ds_dir}")


def build_lists(exp, defaults):
    """train.txt(오버샘플=반복) · val_small.txt · 000.jpg(캐시 분리) · data.yaml 을 _exp/<name>/ 에 만든다."""
    name = exp["name"]
    d = EXP_DIR / name
    d.mkdir(parents=True, exist_ok=True)
    base = find_dataset(exp.get("base", defaults.get("base", "aihub71751_48k")))
    lines = list_images(base)
    oversample = dict(defaults.get("oversample", {}), **exp.get("oversample", {}))
    for ds, k in oversample.items():                       # 예: human_fire: 5 → 같은 경로 5번
        imgs = list_images(find_dataset(ds))
        lines += imgs * int(k)
    for ds in exp.get("extras", []):
        lines += list_images(find_dataset(ds))
    # labels.cache 잡별 분리: 잡 폴더의 000.jpg(빈 라벨)를 목록 맨 앞에 → 캐시가 _exp/<name>.cache 로 떨어진다
    dummy = d / "000.jpg"
    if not dummy.exists():
        shutil.copyfile(lines[0], dummy)
        (d / "000.txt").write_text("")
    lines = [str(dummy)] + lines
    (d / "train.txt").write_text("\n".join(lines) + "\n")
    rnd = random.Random(0)
    val = rnd.sample(lines[1:], min(int(defaults.get("val_small", 600)), len(lines) - 1))
    (d / "val_small.txt").write_text("\n".join([str(dummy)] + val) + "\n")
    val_path = d / "val_small.txt"                         # 기본: 학습 목록에서 뽑은 600장(학습과 겹친다 → 외운 정도만 보인다)
    vs = exp.get("val_set", defaults.get("val_set"))       # 권장: build_evalset.py 가 만든 검증 전용 val.txt(채점 전용 영상의 손라벨). 학습과 겹치지 않는다
    if vs and Path(vs).is_file():
        val_path = Path(vs)
    (d / "data.yaml").write_text(
        f"path: {d}\ntrain: {d/'train.txt'}\nval: {val_path}\nnc: 2\nnames: ['fire','smoke']\n")
    return d, len(lines) - 1


def best_pt(exp):
    """새 레이아웃 → 구 레이아웃(runs/<name>/weights) 순으로 best.pt 를 찾는다."""
    cands = [V / "runs" / exp["name"] / exp["model"] / "weights/best.pt",
             V / "runs" / exp["name"] / "weights/best.pt"]
    return next((p for p in cands if p.is_file()), None)


def _pdeathsig():
    """자식이 이 함수를 실행한 뒤 exec 한다. 부모가 죽는 순간 커널이 자식에게 SIGTERM 을 보낸다(PR_SET_PDEATHSIG).
    러너가 OOM 킬러에 -9 로 즉사해도 학습 프로세스가 고아로 남아 RAM·GPU 를 쥐고 있는 일을 막는다."""
    try:
        import ctypes
        ctypes.CDLL("libc.so.6").prctl(1, 15)      # PR_SET_PDEATHSIG=1, SIGTERM=15
    except Exception:
        pass


def kill_orphan_trainers():
    """부모가 없는(PPID 1) 학습 프로세스를 정리한다. 러너가 죽고 자식만 남은 경우가 여기 걸린다.
    부모가 살아 있는(다른 러너가 돌리는) 프로세스는 건드리지 않는다."""
    killed = []
    try:
        out = subprocess.run(["ps", "-eo", "pid,ppid,args"], capture_output=True, text=True, timeout=20).stdout
    except Exception:
        return killed
    for line in out.splitlines()[1:]:
        f = line.split(None, 2)
        if len(f) < 3 or "model.py train" not in f[2] and "resume_train.py" not in f[2]:
            continue
        if f[1] != "1":                            # 부모가 살아 있으면 정상 잡
            continue
        try:
            os.kill(int(f[0]), 9); killed.append(f[0])
        except Exception:
            pass
    if killed:
        log(f"고아 학습 프로세스 {len(killed)}개 정리(PID {' '.join(killed)})")
        time.sleep(5)
    return killed


def free_gb():
    try:
        import psutil
        return psutil.virtual_memory().available / 2 ** 30
    except Exception:
        return 1e9                                  # psutil 이 없으면 게이트를 걸지 않는다


def is_done(exp):
    return (V / "results" / exp["name"] / "score.txt").is_file() or (V / "results" / f"{exp['name']}.txt").is_file()


def gpu_used_mib():
    try:
        out = subprocess.run(["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
                             capture_output=True, text=True, timeout=20).stdout
        return int(out.strip().splitlines()[0])
    except Exception:
        return 0


def train_cmd(exp, defaults, data_yaml, n_train=0):
    a = dict(defaults.get("train", {}), **exp.get("train", {}))
    # ram 캐시는 이미지 1장≈0.7MB → 14만장이면 잡당 100GB, 3잡 동시면 OOM(rc=-9). 큰 목록은 캐시 없이 읽는다
    cache = a.get("cache", "ram")
    if cache == "ram" and n_train > int(defaults.get("ram_cache_max", 60000)):
        cache = False
    cmd = [str(PY), "model.py", "train", "--models", exp["model"], "--data", str(data_yaml),
           "--project", str(V / "runs" / exp["name"]), "--device", "0",
           "--batch", str(a.get("batch", 128)), "--epochs", str(a.get("epochs", 80)),
           "--imgsz", str(a.get("imgsz", 640)), "--multi-scale", "--no-export", "--force",
           "--cache", str(cache), "--workers", str(a.get("workers", 8)),
           "--extra", f"multi_scale={a.get('multi_scale', 0.5)}"]
    extra = dict(defaults.get("extra", {}), **exp.get("extra", {}))   # 예: scale: 0.9
    cmd += [f"{k}={v}" for k, v in extra.items()]
    return cmd


def score(exp, pt):
    item = exp.get("item", "방화")
    vids = SCORE_VIDEOS.get(item)
    rdir = V / "results" / exp["name"]; rdir.mkdir(parents=True, exist_ok=True)
    if vids is None:
        (rdir / "score.txt").write_text(f"=== {exp['name']} ===\n(항목 {item} 채점기 미연결)\n")
        return None
    cmd = [str(PY), str(V / "score_kisa.py"), str(pt), "--videos", str(vids), "--gt", str(vids),
           "--stride", "0.5", "--imgsz", "640", "--tiles", "--tag", exp["name"]]
    out = subprocess.run(cmd, capture_output=True, text=True, cwd=V).stdout
    (rdir / "score.txt").write_text(f"=== {exp['name']} 타일 ===\n" + out)
    try:                                                    # 채점 전용 검증셋 mAP(학습에 안 들어간 배포 검증영상 라벨) → results/<exp>/eval_map.json
        mode = "fire" if item == "방화" else "person"
        subprocess.run([str(PY), str(V / "scripts/build_evalset.py"), mode], capture_output=True, text=True, cwd=V, timeout=600)   # 채점 영상에 새로 친 라벨까지 검증셋에 반영(매번 다시 빌드, 수 초)
        if (V / "data/학습데이터" / f"evalset_{mode}" / "data.yaml").exists():
            subprocess.run([str(PY), str(V / "scripts/eval_map.py"), mode, "--exp", exp["name"], "--pt", str(pt)], capture_output=True, text=True, cwd=V, timeout=1800)
    except Exception as e:
        log(f"{exp['name']} eval_map 실패: {e}")
    return out


def write_meta(exp, defaults, n_train, pt, started, status):
    rdir = V / "results" / exp["name"]; rdir.mkdir(parents=True, exist_ok=True)
    meta = {"name": exp["name"], "item": exp.get("item", "방화"), "model": exp["model"],
            "base": exp.get("base", defaults.get("base")), "extras": exp.get("extras", []),
            "oversample": dict(defaults.get("oversample", {}), **exp.get("oversample", {})),
            "train": dict(defaults.get("train", {}), **exp.get("train", {})),
            "extra": dict(defaults.get("extra", {}), **exp.get("extra", {})),
            "n_train": n_train, "best_pt": str(pt) if pt else None,
            "started": started, "ended": _kst("%Y-%m-%d %H:%M:%S"), "status": status}
    (rdir / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1))


def run_one(exp, defaults):
    """한 실험 전체(목록→학습→채점→meta). 실패해도 예외를 밖으로 던지지 않는다."""
    name = exp["name"]; started = _kst("%Y-%m-%d %H:%M:%S")
    try:
        pt = best_pt(exp)
        n_train = None
        last_pt = V / "runs" / name / exp["model"] / "weights" / "last.pt"
        unfinished = False
        if last_pt.is_file() and (EXP_DIR / name / "data.yaml").is_file():
            try:                                          # 마지막 에폭 < 목표 에폭 = 중단된 학습(끝난 학습은 epoch=-1 로 저장됨)
                import torch
                ck = torch.load(str(last_pt), map_location="cpu", weights_only=False)
                ep = int(ck.get("epoch", -1)); tgt = int((ck.get("train_args") or {}).get("epochs", 0))
                unfinished = ep >= 0 and ep + 1 < tgt
                del ck
            except Exception as e:
                log(f"{name} last.pt 확인 실패: {e!r}")
        if unfinished:
            pt = None                                     # 중간 best.pt 로 완료 처리하지 않는다
        if pt is None and last_pt.is_file() and unfinished:
            # 중단된 학습 → last.pt 에서 이어간다(에폭 유지). 캐시/워커는 큐 설정을 따른다
            a_ = dict(defaults.get("train", {}), **exp.get("train", {}))
            cache = a_.get("cache", "ram")
            n_lines = sum(1 for _ in open(EXP_DIR / name / "train.txt", encoding="utf-8")) if (EXP_DIR / name / "train.txt").is_file() else 0
            if cache == "ram" and n_lines > int(defaults.get("ram_cache_max", 60000)):
                cache = False
            log(f"{name} 이어서 학습(last.pt, {n_lines}장, cache={cache}, workers={a_.get('workers', 8)}, batch={a_.get('batch', 128)})")
            LOG_DIR.mkdir(parents=True, exist_ok=True)
            with open(LOG_DIR / f"{name}.log", "a", encoding="utf-8") as lf:
                rc = subprocess.run([str(PY), str(V / "scripts/resume_train.py"), str(last_pt), "--cache", str(cache), "--workers", str(a_.get("workers", 8)), "--batch", str(a_.get("batch", 128))],
                                    cwd=V, stdout=lf, stderr=subprocess.STDOUT, preexec_fn=_pdeathsig, env=dict(os.environ, CUDA_VISIBLE_DEVICES="0")).returncode
            pt = best_pt(exp)
            if rc != 0 or pt is None:
                log(f"{name} 이어서 학습 실패 rc={rc}{' (SIGKILL: OOM 의심 → 캐시/동시잡 확인)' if rc == -9 else ''} (logs/queue/{name}.log)")
                write_meta(exp, defaults, n_lines, pt, started, "train_failed"); return
        elif pt is None:
            d, n_train = build_lists(exp, defaults)
            log(f"{name} 학습 시작 ({exp['model']}, {n_train}장, +{exp.get('extras', [])}, extra={exp.get('extra', {})})")
            LOG_DIR.mkdir(parents=True, exist_ok=True)
            with open(LOG_DIR / f"{name}.log", "a", encoding="utf-8") as lf:
                rc = subprocess.run(train_cmd(exp, defaults, d / "data.yaml", n_train), cwd=V, stdout=lf, stderr=subprocess.STDOUT, preexec_fn=_pdeathsig,
                                    env=dict(os.environ, CUDA_VISIBLE_DEVICES="0")).returncode
            pt = best_pt(exp)
            if rc != 0 or pt is None:
                log(f"{name} 학습 실패 rc={rc}{' (SIGKILL: OOM 의심 → 캐시/동시잡 확인)' if rc == -9 else ''} (logs/queue/{name}.log). 러너 재실행 시 자동 재시도")
                write_meta(exp, defaults, n_train, pt, started, "train_failed"); return
        else:
            log(f"{name} best.pt 있음 → 학습 생략, 채점만")
        log(f"{name} 채점")
        score(exp, pt)
        write_meta(exp, defaults, n_train, pt, started, "done")
        shutil.rmtree(EXP_DIR / name, ignore_errors=True)
        log(f"{name} 완료 → results/{name}/score.txt")
    except Exception as e:
        log(f"{name} 예외: {e!r}")
        write_meta(exp, defaults, None, None, started, f"error: {e!r}")


def wait_tmux_gone(session):
    while subprocess.run(["tmux", "has-session", "-t", session], capture_output=True).returncode == 0:
        time.sleep(120)


def wait_no_train_procs():
    while subprocess.run(["pgrep", "-f", "model.py train"], capture_output=True).returncode == 0:
        time.sleep(60)


def cmd_run(a):
    q = yaml.safe_load(open(a.queue, encoding="utf-8"))
    defaults = q.get("defaults", {}); exps = q["experiments"]
    if a.wait_tmux:
        log(f"tmux 세션 '{a.wait_tmux}' 종료 대기"); wait_tmux_gone(a.wait_tmux)
        log("기존 학습 프로세스 종료 대기"); wait_no_train_procs()
    if a.rebuild_human:
        log("human_fire 재빌드(손라벨 최신화)")
        subprocess.run([str(PY), str(V / "scripts/build_humanset.py")], cwd=V)
    kill_orphan_trainers()             # 지난 러너가 SIGKILL 로 죽어 남은 학습 프로세스부터 치운다
    todo = [e for e in exps if not is_done(e)]
    log(f"큐 {a.queue}: 총 {len(exps)}개, 남은 {len(todo)}개, 동시 {a.jobs}잡")
    running = []                       # (proc, exp)
    vram_gate = int(defaults.get("vram_gate_mib", 120000))
    min_free = float(defaults.get("min_free_gb", 300))   # 컨테이너 메모리 한도를 안에서 못 읽으니 가용 RAM 으로 대신 막는다
    warned = 0
    while todo or running:
        running = [(p, e) for p, e in running if p.poll() is None]
        gb = free_gb()
        if todo and len(running) < a.jobs and gpu_used_mib() < vram_gate and gb >= min_free:
            e = todo.pop(0)
            p = subprocess.Popen([sys.executable, __file__, "_one", a.queue, e["name"]], cwd=V, preexec_fn=_pdeathsig)
            running.append((p, e)); time.sleep(int(defaults.get("stagger_sec", 90)))
        else:
            if todo and len(running) < a.jobs and gb < min_free and time.time() - warned > 600:
                warned = time.time(); log(f"가용 RAM {gb:.0f}GB < {min_free:.0f}GB → 새 잡 대기")
            time.sleep(30)
    log("QUEUE DONE")


def cmd_one(a):
    q = yaml.safe_load(open(a.queue, encoding="utf-8"))
    exp = next(e for e in q["experiments"] if e["name"] == a.name)
    run_one(exp, q.get("defaults", {}))


def cmd_status(a):
    q = yaml.safe_load(open(a.queue, encoding="utf-8"))
    for e in q["experiments"]:
        st = "완료" if is_done(e) else ("학습됨(채점X)" if best_pt(e) else "대기")
        print(f"  {st:10s} {e['name']:32s} {e['model']:8s} {e.get('item','방화')}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); sp = ap.add_subparsers(dest="cmd", required=True)
    r = sp.add_parser("run"); r.add_argument("queue"); r.add_argument("--jobs", type=int, default=3)
    r.add_argument("--wait-tmux", default=None); r.add_argument("--rebuild-human", action="store_true"); r.set_defaults(f=cmd_run)
    o = sp.add_parser("_one"); o.add_argument("queue"); o.add_argument("name"); o.set_defaults(f=cmd_one)
    s = sp.add_parser("status"); s.add_argument("queue"); s.set_defaults(f=cmd_status)
    a = ap.parse_args(); a.f(a)
