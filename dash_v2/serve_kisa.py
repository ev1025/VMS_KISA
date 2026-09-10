# -*- coding: utf-8 -*-
"""통합 KISA 검수 대시보드 서버 (서버에서 실행, ssh -L 로 로컬 브라우저 접속).

한 서버에서 네 가지를 다 제공한다.
  - /              : 대시보드 HTML
  - /api/meta      : 4항목 영상별 GT·신호·맵·트랙 (dash_meta.json)
  - /vid/<경로>    : 배포 영상 스트리밍 (Range 지원, 브라우저 seek)
  - /frame/<파일>  : 기존 손라벨 프레임 PNG (labelfull)
  - /newframe/<파일>: 새 손라벨 대상 하드 프레임 PNG (labelfull_new)
  - /api/newframes : 하드 프레임 목록 (labelfull_new/meta.json)
  - /api/savelabel : (POST) 손라벨 박스를 fire_labels.json 에 저장
  - /api/clipinfo  : 클립 원본 mp4 의 fps·프레임수·해상도 (임의 프레임 고르기용)
  - /api/sources   : 원본데이터 카테고리 목록(폴더별 영상 수)
  - /api/raw       : 한 카테고리 안의 이미지·영상 목록 (데이터 확인용)
  - /api/clips     : 한 카테고리의 영상 목록 (원본데이터 기준 상대경로, 확장자 없음)
                     (clipinfo 는 같은 이름 XML 의 화재 발생 시각도 함께 준다)
  - /frameat       : 클립의 그 초(t) 프레임 한 장을 JPEG 로 (라벨 생성에서 프레임 선택)
"""
import json, os, re, shutil, threading, time, urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).parent
# 데이터 루트 = 이 파일의 상위 폴더(= .../vms). 전에는 general_yolo 심링크를 하드코딩했는데
# 그 심링크가 지워지자 라벨·영상·프레임이 전부 404 가 됐다. 자기 위치 기준으로 잡으면 그런 일이 없다.
G = HERE.parent
WS = Path("/NHNHOME/WORKSPACE/26mss002_E3")  # 심링크가 vms/data 로 나가도 허용
RAW = G / "data/원본데이터"        # 라벨 대상 영상이 카테고리 폴더로 들어 있는 곳
PORT = 8890

_CI = {}          # 클립별 fps·프레임수 캐시. 영상을 열어봐야 아는 값이라 한 번만 읽는다
_SAVE_LOCK = threading.Lock()   # savelabel 은 read-modify-write. ThreadingHTTPServer 라 동시 저장 시 한쪽이 사라지는 걸 막는다


def _backup_labels(fl):
    """그날 첫 저장 전에 손라벨 JSON 스냅샷을 _backup/<이름>.<YYYYMMDD>.json 으로 남긴다(실수 복구용)."""
    try:
        if not fl.exists():
            return
        b = fl.parent / "_backup" / f"{fl.stem}.{time.strftime('%Y%m%d')}.json"
        if not b.exists():
            b.parent.mkdir(exist_ok=True); shutil.copyfile(fl, b)
    except Exception:
        pass
_CLIPS = {}       # 카테고리별 영상 목록 캐시


def data_path(*cands):
    """후보 경로 중 실제로 있는 것을 쓴다. 폴더 재구성(labelfull → data/학습데이터/손라벨/full,
    fire_labels.json → data/학습데이터/손라벨/fire_labels.json)에도 안 깨지게 하려는 것."""
    for c in cands:
        q = G / c
        if q.exists():
            return q
    return G / cands[0]


_COCO = {}   # annotations json 경로 -> {파일명: YOLO 라벨 문자열}. 한 번만 파싱해 캐시


def raw_sibling_label(rel):
    """이미지와 라벨이 다른 트리에 있는 원본에서 YOLO txt 를 찾는다.
    예: open_coco/train2017/x.jpg -> open_coco/coco/labels/train2017/x.txt
    카테고리 루트 아래 labels/<이미지 상위폴더>/<같은 이름>.txt 를 깊이 3까지 본다(glob 이라 훑지 않는다)."""
    _r = str(rel).replace("\\", "/")
    if "/images/" in _r:   # YOLO 표준: .../images/x.jpg <-> .../labels/x.txt (같은 레벨)
        cand = G / (_r.rsplit("/images/", 1)[0] + "/labels/" + Path(_r).stem + ".txt")
        if cand.is_file():
            return cand
    parts = _r.split("/")
    if len(parts) < 4 or parts[0] != "data" or parts[1] != "원본데이터":
        return None
    root = G / parts[0] / parts[1] / parts[2]
    stem, parent = Path(rel).stem, parts[-2]
    for pat in (f"labels/{parent}/{stem}.txt", f"*/labels/{parent}/{stem}.txt",
                f"*/*/labels/{parent}/{stem}.txt", f"labels/{stem}.txt", f"*/labels/{stem}.txt"):
        for q in root.glob(pat):
            if q.is_file():
                return q
    return None


def coco_labels(rel):
    """원본 COCO annotations(images/<split>/ + annotations/<split>.json)에서 그 이미지의 박스를
       YOLO(cls cx cy w h, 정규화) 문자열로 돌려준다. fasdd 등 test 스플릿까지 표시하려는 것."""
    m = re.match(r"(.*)/images/(train|val|test)/([^/]+)$", rel)
    if not m:
        return None
    base, split, fname = m.groups()
    jp = G / base / "annotations" / (split + ".json")
    if not jp.exists():
        return None
    key = str(jp)
    if key not in _COCO:
        idx = {}
        try:
            import json as _json
            d = _json.load(open(jp, encoding="utf-8"))
            info = {im["id"]: (im["file_name"], im["width"], im["height"]) for im in d.get("images", [])}
            lines = {}
            for a in d.get("annotations", []):
                it = info.get(a["image_id"])
                if not it:
                    continue
                fn, W, Hh = it
                x, y, w, h = a["bbox"]
                lines.setdefault(fn, []).append(
                    "%d %.6f %.6f %.6f %.6f" % (a["category_id"], (x + w / 2) / W, (y + h / 2) / Hh, w / W, h / Hh))
            idx = {fn: chr(10).join(v) for fn, v in lines.items()}
        except Exception:
            idx = {}
        _COCO[key] = idx
    return _COCO[key].get(fname, "")


def under_raw(rel, ext=""):
    """원본데이터 기준 상대경로를 안전하게 실경로로. 폴더 밖을 가리키면 None."""
    if not rel:
        return None
    rel = str(rel).replace("\\", "/")
    if ".." in rel.split("/"):
        return None
    p = RAW / (rel + ext)
    try:
        root, rp = RAW.resolve(), p.resolve()
    except OSError:
        return None
    return p if root == rp or root in rp.parents else None


def clips_of(cat):
    """카테고리 폴더 아래 mp4 전부(하위 폴더 포함). 원본데이터 기준 상대경로, 확장자 없음."""
    if cat in _CLIPS:
        return _CLIPS[cat]
    base = under_raw(cat)
    if base is None or not base.is_dir():
        return []
    rels = sorted(str(p.relative_to(RAW).with_suffix("")).replace("\\", "/")
                  for p in base.rglob("*.mp4"))
    _CLIPS[cat] = rels
    return rels


CACHE_DIR = HERE / "_cache"        # 폴더 스캔 결과를 디스크에 둔다(재시작해도 16초 스캔을 다시 안 함)
_SOURCES = None


def _cache_read(key):
    f = CACHE_DIR / (key + ".json")
    try:
        return json.loads(f.read_text(encoding="utf-8")) if f.exists() else None
    except Exception:
        return None


def _cache_write(key, obj):
    try:
        CACHE_DIR.mkdir(exist_ok=True)
        tmp = CACHE_DIR / (key + ".json.tmp")
        tmp.write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8"); tmp.replace(CACHE_DIR / (key + ".json"))
    except Exception:
        pass


def clear_caches():
    """데이터 폴더를 옮기거나 이름을 바꾼 뒤 호출(대시보드 '캐시 새로고침' 버튼). 재시작 불필요."""
    global _SOURCES
    _SOURCES = None; _RAW.clear(); _CLIPS.clear(); _CI.clear()
    shutil.rmtree(CACHE_DIR, ignore_errors=True)


def sources():
    """카테고리(원본데이터 1단계 폴더) 목록. count = 영상 편수(0 이면 이미지만 있는 폴더).
    첫 계산이 16초(전 카테고리 os.walk)라 메모리+디스크에 캐시한다."""
    global _SOURCES
    if _SOURCES is not None:
        return _SOURCES
    disk = _cache_read("sources")
    if disk is not None:
        _SOURCES = disk; return _SOURCES
    out = []
    if not RAW.is_dir():
        return out
    for d in sorted((p for p in RAW.iterdir() if p.is_dir()), key=lambda q: (1 if "flir" in q.name.lower() else 0, q.name)):
        out.append({"key": d.name, "count": len(clips_of(d.name))})
    _SOURCES = out; _cache_write("sources", out)
    return out


IMG_EXT = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
# 원본 클래스 규약이 우리(0=불,1=연기)와 다른 세트. 데이터확인 요약에 경고로 띄운다(학습셋은 리매핑돼 있음)
RAW_CLASS_NOTE = {
    "open_azimjaan_fire": "원본 3클래스 0=구름·1=불·2=연기 (대시보드 색은 우리 규약이라 뒤바뀌어 보임. 학습셋 azimjaan_yolo 는 리매핑)",
    "open_dfire": "원본 0=smoke·1=fire (학습셋 dfire_yolo 에서 스왑)",
}
_RAW = {}          # 카테고리별 파일 목록 캐시(폴더를 한 번만 훑는다)


def raw_items(cat, limit=600):
    """카테고리 안의 이미지·영상 목록. 경로는 vms 기준 상대경로(=/dsimg, /vid 주소에 그대로 쓴다).
    수만 장이면 고르게 샘플만 준다(목록이 목적이 아니라 눈으로 확인하는 게 목적)."""
    if cat in _RAW:
        got = _RAW[cat]
    elif _cache_read("raw_" + cat) is not None:
        got = _RAW[cat] = _cache_read("raw_" + cat)
    else:
        base = under_raw(cat)
        if base is None or not base.is_dir():
            return None
        imgs, vids = [], []
        root_len = len(str(G)) + 1
        for dirpath, _dirs, files in os.walk(base):
            for fn in files:
                ext = os.path.splitext(fn)[1].lower()
                if ext in IMG_EXT:
                    _rel = os.path.join(dirpath, fn)[root_len:].replace("\\", "/")
                    if "infrared" in _rel.lower() or "thermal" in _rel.lower():
                        continue   # 적외선/열화상은 데이터확인 브라우징에서 제외(가시광/RGB만)
                    imgs.append(_rel)
                elif ext == ".mp4":
                    vids.append(os.path.join(dirpath, fn)[root_len:].replace("\\", "/"))
        imgs.sort(); vids.sort()
        got = _RAW[cat] = {"images": imgs, "videos": vids}
        _cache_write("raw_" + cat, got)

    def samp(a):
        if len(a) <= limit:
            return a
        step = len(a) / limit
        return [a[int(i * step)] for i in range(limit)]

    # 영상은 자르지 않는다: 조건 필터(야간·설경)로 골라 라벨하는데 잘리면 대상이 사라진다
    return {"cat": cat, "img_total": len(got["images"]), "vid_total": len(got["videos"]),
            "images": samp(got["images"]), "videos": got["videos"]}


def fire_spans(clip, fps=30.0):
    """클립 옆 정답 파일에서 이벤트 구간을 읽는다. [{"start": 초, "dur": 초, "kind": 종류}, ...]
    - KISA XML: StartTime(발생 시각) + AlarmDuration(경보 인정 구간)
    - AI허브 JSON: annotations.event_frame[[시작프레임, 끝프레임]] → fps 로 초 변환
    라벨할 초를 여기서 찾는다."""
    xml = under_raw(clip, ".xml")
    if xml is None or not xml.exists():
        return json_spans(clip, fps)      # XML 이 없으면 AI허브 JSON 을 본다
    def secs(txt):
        parts = [int(x) for x in str(txt).strip().split(":")]
        while len(parts) < 3:
            parts.insert(0, 0)
        return parts[0] * 3600 + parts[1] * 60 + parts[2]
    import xml.etree.ElementTree as ET
    out = []
    try:
        for al in ET.parse(xml).getroot().iter("Alarm"):
            st = al.findtext("StartTime")
            if not st:
                continue
            out.append({"start": secs(st), "dur": secs(al.findtext("AlarmDuration") or "0:0:0"),
                        "kind": (al.findtext("AlarmDescription") or "").strip()})
    except Exception:
        return []      # XML 이 깨져도 라벨 화면은 돌아야 한다
    return out


def json_spans(clip, fps=30.0):
    """AI허브 라벨(JSON) 의 이벤트 구간. 침입·쓰러짐 영상이 이 형식이다."""
    js = under_raw(clip, ".json")
    if js is None or not js.exists():
        return []
    try:
        d = json.load(open(js, encoding="utf-8"))
        a = d.get("annotations") or {}
        f = float(fps) or 30.0
        out = []
        for fr in (a.get("event_frame") or []):
            if not isinstance(fr, (list, tuple)) or not fr:
                continue
            s0 = float(fr[0]) / f
            e0 = float(fr[1]) / f if len(fr) > 1 else s0
            out.append({"start": int(round(s0)), "dur": max(int(round(e0 - s0)), 0),
                        "kind": a.get("event_class") or "event",
                        "note": a.get("event_caption") or ""})
        return out
    except Exception:
        return []      # 라벨이 깨져도 라벨 생성 화면은 돌아야 한다


def clip_info(clip):
    """클립 mp4 의 fps·총프레임·해상도 + XML 의 화재 발생 구간. 없으면 None."""
    if clip in _CI:
        return _CI[clip]
    mp4 = under_raw(clip, ".mp4")
    if mp4 is None or not mp4.exists():
        return None
    import cv2
    cap = cv2.VideoCapture(str(mp4))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 1280)
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 720)
    cap.release()
    _CI[clip] = {"clip": clip, "fps": round(fps, 4), "frames": n,
                 "dur": round(n / fps, 2) if fps else 0, "W": w, "H": h,
                 "fire": fire_spans(clip, fps)}
    return _CI[clip]


def read_frame(clip, sec, w=0):
    _c = frame_cache_path(clip, sec, w)                    # 이미 뽑아 둔 게 있으면 바로 준다
    try:
        if _c.exists():
            return _c.read_bytes()
    except Exception:
        pass
    """그 시각(초)의 프레임 한 장을 JPEG 바이트로. 없으면 None.
    라벨은 초당 1장 기준이라 프레임 번호가 아니라 초로 받는다.
    w 를 주면 그 가로 픽셀로 줄여 보낸다(참조 샷 썸네일)."""
    mp4 = under_raw(clip, ".mp4")
    if mp4 is None or not mp4.exists():
        return None
    import cv2
    # ponytail: 요청마다 열고 seek 한다(초당 몇 장이면 충분). 느려지면 최근 캡처 하나만 재사용하도록 고친다.
    cap = cv2.VideoCapture(str(mp4))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    cap.set(cv2.CAP_PROP_POS_FRAMES, max(int(round(float(sec) * fps)), 0))
    ok, fr = cap.read()
    cap.release()
    if not ok:
        return None
    q = 92
    if w and 0 < int(w) < fr.shape[1]:      # 썸네일은 작게·가볍게
        wh = int(round(fr.shape[0] * int(w) / fr.shape[1]))
        fr = cv2.resize(fr, (int(w), wh), interpolation=cv2.INTER_AREA)
        q = 78
    ok, buf = cv2.imencode(".jpg", fr, [int(cv2.IMWRITE_JPEG_QUALITY), q])
    if not ok:
        return None
    data = buf.tobytes()
    try:                                                   # 다음 요청은 디코딩 없이
        _c.parent.mkdir(parents=True, exist_ok=True)
        _t = _c.with_suffix(f".tmp{os.getpid()}")
        _t.write_bytes(data); _t.replace(_c)
    except Exception:
        pass
    return data


_PERSON_MODEL = None
def person_boxes(clip, sec, conf=0.3):
    """그 프레임에서 person 박스(YOLO 정규화 [0,cx,cy,w,h])를 person_v3(CPU)로 뽑는다. 의사라벨 프리필용."""
    global _PERSON_MODEL
    mp4 = under_raw(clip, ".mp4")
    if mp4 is None or not mp4.exists():
        return []
    import cv2
    cap = cv2.VideoCapture(str(mp4)); fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    cap.set(cv2.CAP_PROP_POS_FRAMES, max(int(round(float(sec) * fps)), 0))
    ok, fr = cap.read(); cap.release()
    if not ok:
        return []
    h0, w0 = fr.shape[:2]
    if _PERSON_MODEL is None:
        from ultralytics import YOLO
        import torch
        _PERSON_MODEL = YOLO(str(G / "model" / "person_v3.pt"))
        person_boxes._dev = 0 if torch.cuda.is_available() else "cpu"
    dev = getattr(person_boxes, "_dev", "cpu")
    # 타일: 전체 + 4분할 + 중앙 → 멀리/작은 사람도 잡는다
    regions = [(0, 0, w0, h0)] + [(x, y, w0 // 2, h0 // 2) for x, y in
               ((0, 0), (w0 // 2, 0), (0, h0 // 2), (w0 // 2, h0 // 2), (w0 // 4, h0 // 4))]
    dets = []
    crops = [fr[oy:oy + rh, ox:ox + rw] for ox, oy, rw, rh in regions]
    rs = _PERSON_MODEL.predict(crops, conf=conf, imgsz=640, classes=[0], device=dev, verbose=False)
    for (ox, oy, rw, rh), r in zip(regions, rs):        # 6번 나눠 부르지 않고 한 번에(대시보드 응답이 그만큼 빨라진다)
        for bb in r.boxes:
            x1, y1, x2, y2 = (float(v) for v in bb.xyxy[0])
            dets.append((float(bb.conf), x1 + ox, y1 + oy, x2 + ox, y2 + oy))
    # NMS(IoU 0.5) 로 타일 중복 제거
    def _iou(a, b):
        ix1 = max(a[0], b[0]); iy1 = max(a[1], b[1]); ix2 = min(a[2], b[2]); iy2 = min(a[3], b[3])
        iw = max(0.0, ix2 - ix1); ih = max(0.0, iy2 - iy1); inter = iw * ih
        ua = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
        return inter / ua if ua > 0 else 0.0
    dets.sort(key=lambda d: d[0], reverse=True)
    keep = []
    for d in dets:
        if all(_iou(d[1:], k[1:]) < 0.5 for k in keep):
            keep.append(d)
    out = [[0, round(x1 / w0, 5), round(y1 / h0, 5),
            round((x2 - x1) / w0, 5), round((y2 - y1) / h0, 5)] for _, x1, y1, x2, y2 in keep]
    return out


_GDINO = None
GDINO_PROMPT = "a person. a pedestrian. a human. a man walking. a person with an umbrella."


def gdino_boxes(clip, sec, th=0.30):
    """Grounding DINO(zero-shot)로 그 프레임의 사람 박스 → YOLO 정규화 [0, x, y, w, h].
    person_v3 가 놓치는 야간 IR·설경·원거리를 잡으라고 붙였다. 오프라인 라벨 생성 전용이고
    배포 추론에는 안 쓴다(퀄컴 NPU). 임계 0.30 은 빈 프레임 60장에서 헛박스 0개인 값."""
    global _GDINO
    mp4 = under_raw(clip, ".mp4")
    if mp4 is None or not mp4.exists():
        return []
    import cv2
    cap = cv2.VideoCapture(str(mp4)); fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    cap.set(cv2.CAP_PROP_POS_FRAMES, max(int(round(float(sec) * fps)), 0))
    ok, fr = cap.read(); cap.release()
    if not ok:
        return []
    h0, w0 = fr.shape[:2]
    import torch
    if _GDINO is None:                       # 첫 호출에만 로드(대시보드 기동을 무겁게 하지 않는다)
        from transformers import AutoProcessor, AutoModelForZeroShotObjectDetection
        mid = "IDEA-Research/grounding-dino-base"
        dev = "cuda" if torch.cuda.is_available() else "cpu"
        _GDINO = (AutoProcessor.from_pretrained(mid),
                  AutoModelForZeroShotObjectDetection.from_pretrained(mid).to(dev).eval(), dev)
    proc, model, dev = _GDINO
    rgb = cv2.cvtColor(fr, cv2.COLOR_BGR2RGB)
    with torch.no_grad():
        inp = proc(images=rgb, text=GDINO_PROMPT, return_tensors="pt").to(dev)
        r = proc.post_process_grounded_object_detection(
            model(**inp), inp.input_ids, threshold=float(th), text_threshold=float(th),
            target_sizes=[(h0, w0)])[0]
    dets = [(float(sc), *[float(v) for v in b]) for sc, b in zip(r["scores"], r["boxes"])]

    def _ov(a, b):                           # 겹침(IoU)과 포함(양방향) 을 같이 본다.
        ix1 = max(a[0], b[0]); iy1 = max(a[1], b[1]); ix2 = min(a[2], b[2]); iy2 = min(a[3], b[3])
        inter = max(0.0, ix2 - ix1) * max(0.0, iy2 - iy1)
        sa = (a[2] - a[0]) * (a[3] - a[1]); sb = (b[2] - b[0]) * (b[3] - b[1])
        ua = sa + sb - inter
        return (inter / ua if ua > 0 else 0.0,
                max(inter / sa if sa > 0 else 0.0, inter / sb if sb > 0 else 0.0))
    dets.sort(key=lambda d: d[0], reverse=True)
    keep = []
    for d in dets:
        if all((lambda v: v[0] < 0.4 and v[1] < 0.9)(_ov(d[1:], k[1:])) for k in keep):
            keep.append(d)
    return [[0, round(x1 / w0, 5), round(y1 / h0, 5),
             round((x2 - x1) / w0, 5), round((y2 - y1) / h0, 5)] for _, x1, y1, x2, y2 in keep]


AUTOLABEL_DIR = G / "data/학습데이터/자동라벨/dino"
_SAM2 = None
SAM2_ID = "facebook/sam2.1-hiera-small"
SAM2_MIN_SCORE = 0.60          # 이보다 낮으면 마스크가 화면 전체로 번지는 실패 사례가 나온다


_AUTOL = {}


def autolabel_of(clip):
    """배치로 미리 떠 둔 DINO 자동라벨. {"frames": {"200.0": [[0,x,y,w,h,score], ...]}}"""
    f = AUTOLABEL_DIR / (Path(clip).stem + ".json")
    if not f.exists():
        return None
    k = str(f)
    hit = _AUTOL.get(k)
    if hit is not None and hit[0] == f.stat().st_mtime:
        return hit[1]
    try:
        d = json.loads(f.read_text(encoding="utf-8"))
    except Exception:
        return None
    _AUTOL[k] = (f.stat().st_mtime, d)
    return d


def sam2_box(clip, sec, px, py):
    """정규화 좌표 (px,py) 한 점을 프롬프트로 SAM2 마스크 → 타이트 박스 + 외곽선.
    반환 [0, x, y, w, h] 와 폴리곤(정규화). 점수가 낮으면 None."""
    global _SAM2
    mp4 = under_raw(clip, ".mp4")
    if mp4 is None or not mp4.exists():
        return None, None, 0.0
    import cv2, numpy as np, torch
    cap = cv2.VideoCapture(str(mp4)); fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    cap.set(cv2.CAP_PROP_POS_FRAMES, max(int(round(float(sec) * fps)), 0))
    ok, fr = cap.read(); cap.release()
    if not ok:
        return None, None, 0.0
    h0, w0 = fr.shape[:2]
    if _SAM2 is None:
        from transformers.models.sam2.processing_sam2 import Sam2Processor
        from transformers.models.sam2.modeling_sam2 import Sam2Model
        dev = "cuda" if torch.cuda.is_available() else "cpu"
        _SAM2 = (Sam2Processor.from_pretrained(SAM2_ID),
                 Sam2Model.from_pretrained(SAM2_ID).to(dev).eval(), dev)
    proc, model, dev = _SAM2
    pt = [float(px) * w0, float(py) * h0]
    rgb = cv2.cvtColor(fr, cv2.COLOR_BGR2RGB)
    with torch.no_grad():
        inp = proc(images=rgb, input_points=[[[pt]]], input_labels=[[[1]]], return_tensors="pt").to(dev)
        out = model(**inp, multimask_output=True)
        masks = proc.post_process_masks(out.pred_masks.cpu(), inp["original_sizes"])[0][0]
        scores = out.iou_scores[0][0].cpu().numpy()
    best = int(np.argmax(scores)); score = float(scores[best])
    if score < SAM2_MIN_SCORE:
        return None, None, score
    m = masks[best].numpy().astype("uint8")
    ys, xs = m.nonzero()
    if len(xs) == 0:
        return None, None, score
    x1, y1, x2, y2 = float(xs.min()), float(ys.min()), float(xs.max()), float(ys.max())
    if (x2 - x1) < 3 or (y2 - y1) < 3 or (x2 - x1) * (y2 - y1) > 0.5 * w0 * h0:
        return None, None, score          # 너무 작거나 화면 절반을 덮으면 실패로 본다
    box = [0, round(x1 / w0, 5), round(y1 / h0, 5), round((x2 - x1) / w0, 5), round((y2 - y1) / h0, 5)]
    cs, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    poly = []
    if cs:
        c = max(cs, key=cv2.contourArea)
        c = cv2.approxPolyDP(c, 0.004 * cv2.arcLength(c, True), True)
        poly = [[round(float(q[0][0]) / w0, 4), round(float(q[0][1]) / h0, 4)] for q in c]
    return box, poly, score


_CONDS = {}


def clip_conds(cat):
    """카테고리 안 클립들의 촬영 조건. {stem: {"tod","snow","rain","fog","loc","gt"}}
    같은 이름 XML 에서 읽는다(KISA 배포·연구개발 영상 공통 형식). 없으면 빈 dict."""
    if cat in _CONDS:
        return _CONDS[cat]
    import xml.etree.ElementTree as ET
    base = under_raw(cat)
    out = {}
    if base is not None and base.is_dir():
        for x in base.rglob("*.xml"):
            try:
                r = ET.parse(x).getroot()
            except Exception:
                continue
            tod = (r.findtext(".//TimeOfDay") or "").strip()
            if not tod and r.find(".//Alarm") is None:
                continue
            gt = None
            al = r.find(".//Alarm")
            if al is not None and al.findtext("StartTime"):
                try:
                    h, m, sec = al.findtext("StartTime").split(":")
                    gt = int(h) * 3600 + int(m) * 60 + int(sec)
                except Exception:
                    gt = None
            out[x.stem] = {"tod": tod, "gt": gt,
                           "snow": (r.findtext(".//Snow") or "").strip(),
                           "rain": (r.findtext(".//Rain") or "").strip(),
                           "fog": (r.findtext(".//Fog") or "").strip(),
                           "loc": (r.findtext(".//Location") or "").strip()}
    _CONDS[cat] = out
    return out


FRAME_CACHE = CACHE_DIR / "frames"


def frame_cache_path(clip, sec, w):
    import hashlib
    key = f"{clip}|{float(sec):.2f}|{int(w or 0)}"
    h = hashlib.md5(key.encode("utf-8")).hexdigest()
    return FRAME_CACHE / h[:2] / (h + ".jpg")


def _encode(fr, w):
    import cv2
    q = 92
    if w and 0 < int(w) < fr.shape[1]:
        wh = int(round(fr.shape[0] * int(w) / fr.shape[1]))
        fr = cv2.resize(fr, (int(w), wh), interpolation=cv2.INTER_AREA)
        q = 78
    ok, buf = cv2.imencode(".jpg", fr, [int(cv2.IMWRITE_JPEG_QUALITY), q])
    return buf.tobytes() if ok else None


def warm_frames(clip, ts, w=0):
    """영상을 한 번만 순차로 훑으며 ts(초 목록) 프레임을 전부 캐시에 채운다.
    프레임마다 seek 하는 것보다 훨씬 빠르다(격자 81장 기준)."""
    mp4 = under_raw(clip, ".mp4")
    if mp4 is None or not mp4.exists():
        return 0
    want = {}
    for t in ts:
        pth = frame_cache_path(clip, t, w)
        if not pth.exists():
            want[round(float(t), 2)] = pth
    if not want:
        return 0
    import cv2
    cap = cv2.VideoCapture(str(mp4))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    idx_of = {int(round(t * fps)): pth for t, pth in want.items()}
    if not idx_of:
        cap.release(); return 0
    start = min(idx_of); end = max(idx_of)
    cap.set(cv2.CAP_PROP_POS_FRAMES, max(start, 0))       # 시작 지점으로 한 번만 탐색
    i = start; n = 0
    while i <= end:
        ok = cap.grab()                                    # 필요 없는 프레임은 디코딩하지 않는다
        if not ok:
            break
        if i in idx_of:
            ok2, fr = cap.retrieve()
            if ok2:
                data = _encode(fr, w)
                if data:
                    pth = idx_of[i]
                    pth.parent.mkdir(parents=True, exist_ok=True)
                    tmp = pth.with_suffix(f".tmp{os.getpid()}")
                    tmp.write_bytes(data); tmp.replace(pth); n += 1
        i += 1
    cap.release()
    return n


_SAM2V = None
SAM2V_ID = "facebook/sam2.1-hiera-small"


def _read_frames(clip, t0, t1, step):
    """[t0, t1] 구간을 step 간격으로 읽어 RGB 목록과 시각 목록을 낸다. 순차 훑기라 탐색이 한 번뿐이다."""
    import cv2
    mp4 = under_raw(clip, ".mp4")
    if mp4 is None or not mp4.exists():
        return [], [], 0, 0
    cap = cv2.VideoCapture(str(mp4))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    want = {}
    t = t0
    while t <= t1 + 1e-6:
        want[int(round(t * fps))] = round(t, 2)
        t = round(t + step, 3)
    if not want:
        cap.release(); return [], [], 0, 0
    lo, hi = min(want), max(want)
    cap.set(cv2.CAP_PROP_POS_FRAMES, max(lo, 0))
    frames, times = [], []
    i = lo
    while i <= hi:
        if not cap.grab():
            break
        if i in want:
            ok, fr = cap.retrieve()
            if ok:
                frames.append(cv2.cvtColor(fr, cv2.COLOR_BGR2RGB)); times.append(want[i])
        i += 1
    H, W = (frames[0].shape[0], frames[0].shape[1]) if frames else (0, 0)
    cap.release()
    return frames, times, W, H


def sam2_propagate(clip, t_seed, box=None, point=None, back=15.0, fwd=15.0, step=0.5):
    """씨앗 프레임의 박스(또는 점) 하나를 앞뒤로 전파한다. 반환 {시각: [x,y,w,h] 정규화}"""
    global _SAM2V
    import numpy as np, torch, time
    t0 = max(0.0, float(t_seed) - float(back))
    t1 = float(t_seed) + float(fwd)
    frames, times, W, H = _read_frames(clip, t0, t1, float(step))
    if not frames:
        return {}, 0, "프레임 없음"
    # 씨앗 프레임의 위치(가장 가까운 것)
    si = min(range(len(times)), key=lambda i: abs(times[i] - float(t_seed)))
    if _SAM2V is None:
        from transformers.models.sam2_video.processing_sam2_video import Sam2VideoProcessor
        from transformers.models.sam2_video.modeling_sam2_video import Sam2VideoModel
        dev = "cuda" if torch.cuda.is_available() else "cpu"
        _SAM2V = (Sam2VideoProcessor.from_pretrained(SAM2V_ID),
                  Sam2VideoModel.from_pretrained(SAM2V_ID).to(dev).eval(), dev)
    proc, model, dev = _SAM2V
    tic = time.time()
    sess = proc.init_video_session(video=frames, inference_device=dev, dtype=torch.float32)
    if box:                                    # 정규화 [x,y,w,h] → 픽셀 [x1,y1,x2,y2]
        bx = [[float(box[0]) * W, float(box[1]) * H,
               (float(box[0]) + float(box[2])) * W, (float(box[1]) + float(box[3])) * H]]
        proc.add_inputs_to_inference_session(sess, frame_idx=si, obj_ids=[1],
                                             input_boxes=[bx], original_size=(H, W))
    else:
        pt = [[[float(point[0]) * W, float(point[1]) * H]]]
        proc.add_inputs_to_inference_session(sess, frame_idx=si, obj_ids=[1],
                                             input_points=[pt], input_labels=[[[1]]], original_size=(H, W))
    out = {}

    def collect(rev):
        # 씨앗 프레임에서 시작해 한 방향으로 전파한다(뒤쪽은 reverse=True 로 다시 한 번).
        for r in model.propagate_in_video_iterator(sess, start_frame_idx=si, reverse=rev):
            i = int(r.frame_idx)
            m = proc.post_process_masks(r.pred_masks.unsqueeze(0).cpu().float(), [(H, W)], binarize=True)[0]
            arr = np.asarray(m.numpy() if hasattr(m, "numpy") else m)
            a = arr
            while a.ndim > 2:                   # (1,1,H,W) · (1,H,W) 어느 쪽이든 2차원으로
                a = a[0]
            ys, xs = np.nonzero(a > 0)
            if len(xs) < 20:
                continue
            x1, y1, x2, y2 = float(xs.min()), float(ys.min()), float(xs.max()), float(ys.max())
            if (x2 - x1) * (y2 - y1) > 0.5 * W * H:
                continue                        # 화면 절반을 넘게 덮으면 실패로 본다
            out[f"{times[i]:.1f}"] = [round(x1 / W, 5), round(y1 / H, 5),
                                      round((x2 - x1) / W, 5), round((y2 - y1) / H, 5)]

    with torch.no_grad():
        collect(False)
        collect(True)
    return out, round(time.time() - tic, 1), None


_EMB_CACHE = {}                 # (clip, 초) → SAM2 이미지 임베딩
_FRAME_PREP = {}                # (clip, 초) → dict(w0, h0, rgb, orig, resh). 프레임 디코딩·전처리 결과


def _prep_frame(clip, sec):
    """프레임을 한 번만 읽고 전처리해 둔다. 같은 프레임에서 여러 번 클릭할 때 1.4초+0.9초를 아낀다."""
    import cv2, numpy as np
    key = (clip, round(float(sec), 2))
    hit = _FRAME_PREP.get(key)
    if hit is not None:
        return hit
    fr = None
    _c = frame_cache_path(clip, sec, 0)
    if _c.exists():
        fr = cv2.imdecode(np.frombuffer(_c.read_bytes(), np.uint8), cv2.IMREAD_COLOR)
    if fr is None:
        mp4 = under_raw(clip, ".mp4")
        if mp4 is None or not mp4.exists():
            return None
        cap = cv2.VideoCapture(str(mp4)); fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        cap.set(cv2.CAP_PROP_POS_FRAMES, max(int(round(float(sec) * fps)), 0))
        ok, fr = cap.read(); cap.release()
        if not ok:
            return None
    h0, w0 = fr.shape[:2]
    rgb = cv2.cvtColor(fr, cv2.COLOR_BGR2RGB)
    proc, model, dev = _SAM2
    import torch
    with torch.no_grad():
        inp = proc(images=rgb, return_tensors="pt").to(dev)
        emb = model.get_image_embeddings(inp["pixel_values"])
    resh = inp["reshaped_input_sizes"][0].tolist() if "reshaped_input_sizes" in inp else [1024, 1024]
    out = dict(w0=w0, h0=h0, orig=inp["original_sizes"], resh=resh, emb=emb)
    if len(_FRAME_PREP) >= 24:
        _FRAME_PREP.pop(next(iter(_FRAME_PREP)))
    _FRAME_PREP[key] = out
    return out


def _mask_bbox(m, min_frac=0.05, min_px=20):
    """이진 마스크의 박스. 잡티 제외: 연결 성분 중 가장 큰 성분 넓이의 min_frac 이상인 것만 모아 박스를 잡는다.
    반환 (x1, y1, x2, y2) 픽셀, 없으면 None."""
    import cv2, numpy as np
    m8 = (m > 0).astype("uint8")
    n, lab, stats, _ = cv2.connectedComponentsWithStats(m8, connectivity=8)
    if n <= 1:
        return None
    areas = stats[1:, cv2.CC_STAT_AREA]
    big = int(areas.max())
    if big < min_px:
        return None
    keep = [i + 1 for i, a in enumerate(areas) if a >= max(min_px, big * min_frac)]
    sel = np.isin(lab, keep)
    ys, xs = np.nonzero(sel)
    return float(xs.min()), float(ys.min()), float(xs.max()), float(ys.max())


def sam2_mask_pts(clip, sec, pts, box=None):
    """포함/제외 점 여러 개(또는 박스 하나)로 마스크.
    pts = [[x, y, label], ...] (정규화, label 1=포함 0=제외) · box = [x, y, w, h] 정규화
    반환 (박스[정규화 x,y,w,h], 외곽선, 점수)"""
    global _SAM2
    import cv2, numpy as np, torch
    if not pts and not box:
        return None, None, 0.0
    if _SAM2 is None:
        from transformers.models.sam2.processing_sam2 import Sam2Processor
        from transformers.models.sam2.modeling_sam2 import Sam2Model
        dev = "cuda" if torch.cuda.is_available() else "cpu"
        _SAM2 = (Sam2Processor.from_pretrained(SAM2_ID),
                 Sam2Model.from_pretrained(SAM2_ID).to(dev).eval(), dev)
    proc, model, dev = _SAM2
    P = _prep_frame(clip, sec)
    if P is None:
        return None, None, 0.0
    w0, h0 = P["w0"], P["h0"]
    sx, sy = P["resh"][1] / w0, P["resh"][0] / h0        # 전처리가 하는 좌표 스케일(리사이즈 입력 기준)
    kw = {}
    if pts:
        kw["input_points"] = torch.tensor([[[[float(q[0]) * w0 * sx, float(q[1]) * h0 * sy] for q in pts]]], device=dev)
        kw["input_labels"] = torch.tensor([[[int(q[2]) for q in pts]]], device=dev)
    if box:
        kw["input_boxes"] = torch.tensor([[[float(box[0]) * w0 * sx, float(box[1]) * h0 * sy,
                                           (float(box[0]) + float(box[2])) * w0 * sx,
                                           (float(box[1]) + float(box[3])) * h0 * sy]]], device=dev)
    with torch.no_grad():
        out = model(image_embeddings=P["emb"], multimask_output=True, **kw)
        scores = out.iou_scores[0][0].float().cpu().numpy()
        best = int(np.argmax(scores)); score = float(scores[best])
        one = out.pred_masks[:, :, best:best + 1]              # 최고 마스크 1장만 업샘플(3장 → 1장)
        masks = proc.post_process_masks(one.cpu(), P["orig"])[0][0]
    m = masks[0].numpy().astype("uint8")
    bb = _mask_bbox(m)                                    # 잡티를 뺀 박스(윤곽선과 맞게)
    if bb is None:
        return None, None, score
    x1, y1, x2, y2 = bb
    bx = [round(x1 / w0, 5), round(y1 / h0, 5), round((x2 - x1) / w0, 5), round((y2 - y1) / h0, 5)]
    cs, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    poly = []
    if cs:
        c = max(cs, key=cv2.contourArea)
        c = cv2.approxPolyDP(c, 0.003 * cv2.arcLength(c, True), True)
        poly = [[round(float(q[0][0]) / w0, 4), round(float(q[0][1]) / h0, 4)] for q in c]
    return bx, poly, score


def sam2_propagate_multi(clip, seeds, back=10.0, fwd=10.0, step=0.5):
    """참조샷 여러 개로 한 객체를 전파한다.
    seeds = [{"t": 초, "box": [x,y,w,h] 정규화}] · 반환 ({시각: [x,y,w,h]}, 걸린초, 오류)"""
    global _SAM2V
    import numpy as np, torch, time
    if not seeds:
        return {}, 0, "참조샷 없음"
    ts = [float(x["t"]) for x in seeds]
    t0 = max(0.0, min(ts) - float(back)); t1 = max(ts) + float(fwd)
    frames, times, W, H = _read_frames(clip, t0, t1, float(step))
    if not frames:
        return {}, 0, "프레임 없음"
    if _SAM2V is None:
        from transformers.models.sam2_video.processing_sam2_video import Sam2VideoProcessor
        from transformers.models.sam2_video.modeling_sam2_video import Sam2VideoModel
        dev = "cuda" if torch.cuda.is_available() else "cpu"
        _SAM2V = (Sam2VideoProcessor.from_pretrained(SAM2V_ID),
                  Sam2VideoModel.from_pretrained(SAM2V_ID).to(dev).eval(), dev)
    proc, model, dev = _SAM2V
    tic = time.time()
    sess = proc.init_video_session(video=frames, inference_device=dev, dtype=torch.float32)
    idxs = []
    for sd in seeds:                          # 참조샷마다 그 프레임에 박스를 넣는다(같은 객체 id 1)
        si = min(range(len(times)), key=lambda i: abs(times[i] - float(sd["t"])))
        b = sd["box"]
        bx = [[float(b[0]) * W, float(b[1]) * H, (float(b[0]) + float(b[2])) * W, (float(b[1]) + float(b[3])) * H]]
        proc.add_inputs_to_inference_session(sess, frame_idx=si, obj_ids=[1],
                                             input_boxes=[bx], original_size=(H, W))   # 프레임별 입력은 따로 저장된다
        idxs.append(si)
    out = {}

    def collect(start, rev):
        for r in model.propagate_in_video_iterator(sess, start_frame_idx=start, reverse=rev):
            i = int(r.frame_idx)
            m = proc.post_process_masks(r.pred_masks.unsqueeze(0).cpu().float(), [(H, W)], binarize=True)[0]
            a = np.asarray(m.numpy() if hasattr(m, "numpy") else m)
            while a.ndim > 2:
                a = a[0]
            ys, xs = np.nonzero(a > 0)
            if len(xs) < 20:
                continue
            x1, y1, x2, y2 = float(xs.min()), float(ys.min()), float(xs.max()), float(ys.max())
            if (x2 - x1) * (y2 - y1) > 0.5 * W * H:
                continue
            out[f"{times[i]:.1f}"] = [round(x1 / W, 5), round(y1 / H, 5),
                                      round((x2 - x1) / W, 5), round((y2 - y1) / H, 5)]

    with torch.no_grad():
        collect(min(idxs), False)             # 첫 참조샷에서 앞으로
        collect(min(idxs), True)              # 첫 참조샷에서 뒤로
    return out, round(time.time() - tic, 1), None


def sam2_propagate_objs(clip, seeds, back=5.0, fwd=10.0, step=0.5, progress=None):
    """여러 객체를 한 세션에서 전파. seeds = [{"t": 초, "box": [x,y,w,h], "obj": 번호}]
    반환 ({시각: {obj: [x,y,w,h]}}, 걸린초, 오류)"""
    global _SAM2V
    import numpy as np, torch, time
    if not seeds:
        return {}, 0, "참조샷 없음"
    ts = [float(x["t"]) for x in seeds]
    t0 = max(0.0, min(ts) - float(back)); t1 = max(ts) + float(fwd)
    frames, times, W, H = _read_frames(clip, t0, t1, float(step))
    if not frames:
        return {}, 0, "프레임 없음"
    if _SAM2V is None:
        from transformers.models.sam2_video.processing_sam2_video import Sam2VideoProcessor
        from transformers.models.sam2_video.modeling_sam2_video import Sam2VideoModel
        dev = "cuda" if torch.cuda.is_available() else "cpu"
        _SAM2V = (Sam2VideoProcessor.from_pretrained(SAM2V_ID),
                  Sam2VideoModel.from_pretrained(SAM2V_ID).to(dev).eval(), dev)
    proc, model, dev = _SAM2V
    tic = time.time()
    # 참조샷 사이 구간 단위 전파: 각 구간은 그 구간 시작 참조 박스 하나만 조건으로 두고 새 세션에서 돈다.
    # (transformers SAM2 비디오는 시작 프레임 이후에 넣어 둔 참조 박스를 실제로 쓰지 않아, 참조샷이 여러 장이어도 첫 장만 효과가 있었다)
    def fidx(t):
        return min(range(len(times)), key=lambda k: abs(times[k] - float(t)))
    by_obj = {}
    for sd in seeds:
        by_obj.setdefault(int(sd.get("obj", 1)), []).append(sd)
    out = {}
    if progress is not None:
        progress["total"] = len(frames) * len(by_obj); progress["done"] = 0

    def to_px(b):
        return [float(b[0]) * W, float(b[1]) * H, (float(b[0]) + float(b[2])) * W, (float(b[1]) + float(b[3])) * H]

    def area_at(prof, tsec):
        """참조샷 (시각, 넓이) 목록에서 tsec 의 기준 넓이(선형 보간, 밖은 가장 가까운 값)."""
        if not prof:
            return None
        if tsec <= prof[0][0]:
            return prof[0][1]
        if tsec >= prof[-1][0]:
            return prof[-1][1]
        for (t0, a0), (t1, a1) in zip(prof, prof[1:]):
            if t0 <= tsec <= t1:
                w = (tsec - t0) / (t1 - t0) if t1 > t0 else 0.0
                return a0 + (a1 - a0) * w
        return prof[-1][1]

    def run_segment(oid, i0, i1, seed_i, box, prof, rev):
        """frames[i0..i1] 구간을 seed_i(구간 안 인덱스) 의 박스 하나로 조건 걸고 rev 방향으로 전파."""
        if i1 < i0:
            return
        sub = frames[i0:i1 + 1]
        sess = proc.init_video_session(video=sub, inference_device=dev, dtype=torch.float32)
        proc.add_inputs_to_inference_session(sess, frame_idx=seed_i - i0, obj_ids=[oid], input_boxes=[[to_px(box)]], original_size=(H, W))
        for r in model.propagate_in_video_iterator(sess, start_frame_idx=seed_i - i0, reverse=rev):
            gi = i0 + int(r.frame_idx)
            if progress is not None:
                if progress.get("cancel"):
                    raise RuntimeError("cancelled")
                progress["done"] = min(progress.get("done", 0) + 1, progress["total"])
            sc = r.object_score_logits
            if sc is not None and float(sc.detach().flatten()[0]) <= 0:      # 대상 없음(가림·이탈)
                continue
            m = proc.post_process_masks(r.pred_masks.unsqueeze(0).cpu().float(), [(H, W)], binarize=True)[0]
            arr = np.asarray(m.numpy() if hasattr(m, "numpy") else m)
            while arr.ndim > 2:
                arr = arr[0]
            bb = _mask_bbox(arr)
            if bb is None:
                continue
            x1, y1, x2, y2 = bb
            area = (x2 - x1) * (y2 - y1)
            sa = area_at(prof, times[gi]) or area
            if area > 0.5 * W * H or area > 3.0 * sa or area < sa / 3.0:     # 근처 참조 박스 대비 3배 넘게 커지거나 1/3 아래 = 흘러감
                continue
            out.setdefault(f"{times[gi]:.1f}", {})[str(oid)] = [round(x1 / W, 5), round(y1 / H, 5),
                                                                 round((x2 - x1) / W, 5), round((y2 - y1) / H, 5)]
        del sess
        torch.cuda.empty_cache()

    with torch.no_grad():
        for oid in sorted(by_obj):
            sds = sorted(by_obj[oid], key=lambda sd: float(sd["t"]))
            prof = [(float(sd["t"]), float(sd["box"][2]) * W * float(sd["box"][3]) * H) for sd in sds]
            idxs = [fidx(sd["t"]) for sd in sds]
            # 1) 구간 시작 → 첫 참조 (역방향)
            run_segment(oid, 0, idxs[0], idxs[0], sds[0]["box"], prof, True)
            # 2) 참조 k → 참조 k+1 직전 (정방향), 마지막 참조 → 끝
            for k, sd in enumerate(sds):
                i0 = idxs[k]
                i1 = (idxs[k + 1] - 1) if k + 1 < len(sds) else (len(frames) - 1)
                if k + 1 < len(sds) and idxs[k + 1] == i0:    # 같은 프레임에 참조가 둘이면 뒤 것만
                    continue
                run_segment(oid, i0, max(i0, i1), i0, sd["box"], prof, False)
    return out, round(time.time() - tic, 1), None


_BG_DINO = {}                   # clip → {"done": n, "total": n, "running": bool}
_BG_LOCK = threading.Lock()


def gdino_boxes_bgr(fr, th=0.25):
    """프레임(BGR 배열) 한 장의 DINO 사람 박스 → [[0,x,y,w,h,score]] (배치 스크립트와 같은 NMS)."""
    global _GDINO
    import cv2, torch
    h0, w0 = fr.shape[:2]
    if _GDINO is None:
        from transformers import AutoProcessor, AutoModelForZeroShotObjectDetection
        mid = "IDEA-Research/grounding-dino-base"
        dev = "cuda" if torch.cuda.is_available() else "cpu"
        _GDINO = (AutoProcessor.from_pretrained(mid), AutoModelForZeroShotObjectDetection.from_pretrained(mid).to(dev).eval(), dev)
    proc, model, dev = _GDINO
    rgb = cv2.cvtColor(fr, cv2.COLOR_BGR2RGB)
    with torch.no_grad():
        inp = proc(images=rgb, text=GDINO_PROMPT, return_tensors="pt").to(dev)
        r = proc.post_process_grounded_object_detection(model(**inp), inp.input_ids, threshold=float(th),
                                                         text_threshold=float(th), target_sizes=[(h0, w0)])[0]
    dets = sorted([(float(sc), *[float(v) for v in b]) for sc, b in zip(r["scores"], r["boxes"])], key=lambda x: -x[0])

    def _ov(a, b):
        ix1 = max(a[0], b[0]); iy1 = max(a[1], b[1]); ix2 = min(a[2], b[2]); iy2 = min(a[3], b[3])
        inter = max(0.0, ix2 - ix1) * max(0.0, iy2 - iy1)
        sa = (a[2]-a[0])*(a[3]-a[1]); sb = (b[2]-b[0])*(b[3]-b[1]); ua = sa + sb - inter
        return (inter/ua if ua > 0 else 0.0, max(inter/sa if sa > 0 else 0.0, inter/sb if sb > 0 else 0.0))
    keep = []
    for d in dets:
        if all((lambda v: v[0] < 0.4 and v[1] < 0.9)(_ov(d[1:], k[1:])) for k in keep):
            keep.append(d)
    return [[0, round(x1/w0, 5), round(y1/h0, 5), round((x2-x1)/w0, 5), round((y2-y1)/h0, 5), round(sc, 3)]
            for sc, x1, y1, x2, y2 in keep]


def bg_dino_start(clip, t_center, span=30.0, step=0.5):
    """현재 프레임 앞뒤 span 초를 DINO 로 훑어 자동라벨 파일에 채운다(백그라운드). 이미 있는 시각은 건너뛴다."""
    with _BG_LOCK:
        st = _BG_DINO.get(clip)
        if st and st.get("running"):
            return st
        st = _BG_DINO[clip] = {"done": 0, "total": 0, "running": True}

    def work():
        try:
            import cv2
            mp4 = under_raw(clip, ".mp4")
            if mp4 is None or not mp4.exists():
                return
            f = AUTOLABEL_DIR / (Path(clip).stem + ".json")
            d = autolabel_of(clip) or {"clip": Path(clip).stem, "frames": {}, "th": 0.25, "step": step,
                                        "model": "grounding-dino-base"}
            cap = cv2.VideoCapture(str(mp4)); fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
            W = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 1280); H = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 720)
            dur = (cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0) / fps
            d.setdefault("W", W); d.setdefault("H", H)
            t0 = max(0.0, float(t_center) - span); t1 = min(dur, float(t_center) + span)
            ts = []
            t = t0
            while t <= t1 + 1e-6:
                if f"{t:.1f}" not in d["frames"]:
                    ts.append(round(t, 2))
                t = round(t + step, 3)
            st["total"] = len(ts)
            for n, t in enumerate(ts, 1):
                cap.set(cv2.CAP_PROP_POS_FRAMES, max(int(round(t * fps)), 0))
                ok, fr = cap.read()
                if ok:
                    try:
                        boxes = gdino_boxes_bgr(fr, 0.25)
                    except Exception:
                        boxes = []
                    d["frames"][f"{t:.1f}"] = boxes
                st["done"] = n
                if n % 10 == 0 or n == len(ts):                     # 10장마다 저장 → 페이지가 중간 결과를 본다
                    AUTOLABEL_DIR.mkdir(parents=True, exist_ok=True)
                    tmp = f.with_suffix(f".json.tmp{os.getpid()}")
                    tmp.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8"); tmp.replace(f)
                    _AUTOL.pop(str(f), None)
            cap.release()
        finally:
            st["running"] = False

    threading.Thread(target=work, daemon=True).start()
    return st


_PROP_JOBS = {}                  # id → {"done","total","running","result","err","sec"}
_PROP_SEQ = [0]
SAM2_DIR = G / "data/학습데이터/자동라벨/sam2"
GT_DIR = G / "data/학습데이터/정답라벨"       # 데이터셋이 제공한 정답(박스·점). 사람이 고치면 손라벨로 승격


_PROP_Q = []                     # 대기 중인 job id (순서대로)
_PROP_LOCK = threading.Lock()
_PROP_WORKER = [None]            # 워커 스레드 하나 (GPU 공유·메모리 때문에 전파는 한 번에 하나)


def _prop_worker():
    import time as _t
    while True:
        with _PROP_LOCK:
            if not _PROP_Q:
                _PROP_WORKER[0] = None
                return
            jid = _PROP_Q.pop(0)
        st = _PROP_JOBS[jid]
        if st.get("cancel"):
            st["state"] = "done"; st["running"] = False; st["err"] = "cancelled"; continue
        st["state"] = "running"; st["running"] = True; st["started"] = _t.time()
        try:
            frames, sec, err = sam2_propagate_objs(st["clip_full"], st["seeds"], back=st["back"], fwd=st["fwd"], step=st["step"], progress=st)
            st["result"] = frames; st["err"] = err; st["sec"] = sec
            if frames and not err:                       # 서버가 바로 저장 → 브라우저가 떠나 있어도 결과가 남는다
                sam2_store_write(st["clip_full"], frames, [{"t": q["t"], "obj": q.get("obj", 1), "box": q["box"]} for q in st["seeds"]])
                st["saved"] = True
        except Exception as e:
            st["err"] = str(e)
        finally:
            st["running"] = False; st["state"] = "done"; st["ended"] = _t.time()


def prop_job_start(clip, seeds, back, fwd, step):
    with _PROP_LOCK:
        for jid0, st0 in _PROP_JOBS.items():      # 같은 클립이 대기·진행 중이면 그 작업을 그대로 돌려준다(중복 실행 방지)
            if st0.get("clip") == Path(clip).stem and st0.get("state") in ("queued", "running"):
                return jid0
        _PROP_SEQ[0] += 1
        jid = str(_PROP_SEQ[0])
        st = _PROP_JOBS[jid] = {"id": jid, "clip": Path(clip).stem, "clip_full": clip, "seeds": seeds, "back": back, "fwd": fwd, "step": step,
                                "done": 0, "total": 0, "running": True, "state": "queued", "result": None, "err": None, "sec": 0, "saved": False}
        _PROP_Q.append(jid)
        if _PROP_WORKER[0] is None or not _PROP_WORKER[0].is_alive():
            _PROP_WORKER[0] = threading.Thread(target=_prop_worker, daemon=True)
            _PROP_WORKER[0].start()
    return jid


def prop_jobs_view(stem=None):
    """클립(또는 전체) 전파 작업 목록: 대기 순번·진행률·오류. 결과 본문은 뺀다."""
    out = []
    with _PROP_LOCK:
        q = list(_PROP_Q); items = list(_PROP_JOBS.items())   # 스냅샷 뒤 순회(순회 중 삽입 방지)
    for jid, st in items:
        if stem and st.get("clip") != stem:
            continue
        out.append({"id": jid, "clip": st.get("clip"), "state": st.get("state", "done" if not st.get("running") else "running"),
                    "pos": (q.index(jid) + 1) if jid in q else 0, "done": st.get("done", 0), "total": st.get("total", 0),
                    "err": st.get("err"), "saved": st.get("saved", False), "sec": st.get("sec", 0),
                    "nframes": len(st["result"]) if st.get("result") else 0})
    return out


def sam2_store_clear(clip):
    f = SAM2_DIR / (Path(clip).stem + ".json")
    if not f.exists():
        return 0
    d = json.loads(f.read_text(encoding="utf-8"))
    n = len(d.get("frames") or {})
    d["frames"] = {}; d["seeds"] = []
    tmp = f.with_suffix(f".json.tmp{os.getpid()}")
    tmp.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8"); tmp.replace(f)
    return n


def sam2_store_write(clip, frames, seeds):
    """전파 결과를 자동라벨/sam2/<클립>.json 에 합친다(같은 시각은 덮어쓴다). 씨앗 프레임도 기록."""
    SAM2_DIR.mkdir(parents=True, exist_ok=True)
    f = SAM2_DIR / (Path(clip).stem + ".json")
    d = {"clip": Path(clip).stem, "frames": {}, "seeds": []}
    if f.exists():
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            pass
    d.setdefault("frames", {}); d.setdefault("seeds", [])
    hand = _hand_box_frames(clip)                     # 손라벨 박스가 있는 프레임은 손라벨만(SAM 결과는 버린다)
    for t, objs in (frames or {}).items():
        k = f"{float(t):.1f}"; cur = d["frames"].get(k)
        if k in hand:
            continue
        d["frames"][k] = {**cur, **objs} if isinstance(cur, dict) and isinstance(objs, dict) else objs   # 같은 시각: 객체 단위 병합
    have = {(round(float(x.get("t", 0)), 2), int(x.get("obj", 1))) for x in d["seeds"]}
    for sd in seeds or []:
        k = (round(float(sd.get("t", 0)), 2), int(sd.get("obj", 1)))
        if k not in have:
            d["seeds"].append({"t": sd.get("t"), "obj": sd.get("obj", 1), "box": sd.get("box")}); have.add(k)
    d["updated"] = time.strftime("%Y-%m-%d %H:%M:%S")
    tmp = f.with_suffix(f".json.tmp{os.getpid()}")
    tmp.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8"); tmp.replace(f)
    return len(d["frames"])


def _hand_box_frames(clip):
    """그 클립에서 손라벨 박스(cls>=0)가 있는 프레임 키("190.5") 집합. 사람·화재 손라벨 파일 둘 다 본다."""
    stem = Path(clip).stem; out = set()
    for fn in ("person_labels.json", "fire_labels.json"):
        fl = data_path("data/학습데이터/손라벨/" + fn, fn)
        try:
            rows = json.loads(fl.read_text(encoding="utf-8")) if fl.exists() else []
        except Exception:
            rows = []
        for r in rows:
            if Path(str(r.get("clip", ""))).stem == stem and int(r.get("cls", -1)) >= 0:
                out.add(f"{round(float(r.get('t', 0)) * 2) / 2:.1f}")
    return out


def sam2_store_drop(clip, t):
    f = SAM2_DIR / (Path(clip).stem + ".json")
    if not f.exists():
        return 0
    d = json.loads(f.read_text(encoding="utf-8"))
    k = f"{float(t):.1f}"
    n = 1 if k in (d.get("frames") or {}) else 0
    d["frames"].pop(k, None)
    tmp = f.with_suffix(f".json.tmp{os.getpid()}")
    tmp.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8"); tmp.replace(f)
    return n


def _locked_store(fn):
    """sam2 저장소는 read-modify-write. 전파 워커·검수 ×·일괄 삭제가 겹쳐도 한쪽이 사라지지 않게 savelabel 과 같은 락을 쓴다."""
    def w(*a, **k):
        with _SAVE_LOCK:
            return fn(*a, **k)
    w.__name__ = fn.__name__
    return w


sam2_store_write = _locked_store(sam2_store_write)
_sam2_store_drop_raw = sam2_store_drop            # savelabel 은 이미 _SAVE_LOCK 안 → 락 없는 원본으로
sam2_store_drop = _locked_store(sam2_store_drop)
sam2_store_clear = _locked_store(sam2_store_clear)


class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def handle_one_request(self):
        try:
            super().handle_one_request()
        except (ConnectionError, OSError):
            self.close_connection = True

    def _bytes(self, data, ctype, code=200):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        try: self.wfile.write(data)
        except OSError: pass

    def _stream(self, path, ctype):
        size = path.stat().st_size
        rng = self.headers.get("Range")
        m = re.match(r"bytes=(\d+)-(\d*)", rng) if rng else None
        if rng and not m:
            rng = None                                   # 접미 범위(bytes=-N) 등은 지원 안 함 → 전체 전송
        if rng:
            start = int(m.group(1)); end = int(m.group(2)) if m.group(2) else size-1
            if start >= size:
                self.send_error(416); return
            end = min(end, size-1); length = end-start+1
            self.send_response(206)
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        else:
            start, length = 0, size
            self.send_response(200)
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Content-Length", str(length))
        self.send_header("Content-Type", ctype)
        self.end_headers()
        with open(path, "rb") as f:
            f.seek(start); left = length
            while left > 0:
                chunk = f.read(min(1 << 20, left))
                if not chunk: break
                try: self.wfile.write(chunk)
                except OSError: return
                left -= len(chunk)

    def do_POST(self):
        p = urllib.parse.urlparse(self.path).path
        if p == "/api/refresh_cache":            # 데이터 폴더 바뀐 뒤 서버 재시작 대신 이걸 누른다
            clear_caches(); sources()
            self._bytes(json.dumps({"ok": True, "sources": len(sources())}).encode(), "application/json; charset=utf-8"); return
        if p == "/api/sam2_mask":            # 포함/제외 점들로 마스크+박스(실험실 탭 조작)
            try:
                n = int(self.headers.get("Content-Length", 0))
                b = json.loads(self.rfile.read(n) or b"{}")
                box, poly, sc = sam2_mask_pts(b["clip"], float(b["t"]), b.get("pts") or [], b.get("box"))
                self._bytes(json.dumps({"box": box, "poly": poly, "score": round(sc, 3)}).encode(),
                            "application/json; charset=utf-8")
            except Exception as e:
                self._bytes(json.dumps({"box": None, "poly": None, "score": 0, "err": str(e)}).encode(),
                            "application/json; charset=utf-8", 500)
            return
        if p == "/api/sam2_propagate_start":  # 전파를 백그라운드로 시작 → 작업 id. 진행률은 GET /api/sam2_progress?id=
            try:
                n = int(self.headers.get("Content-Length", 0))
                b = json.loads(self.rfile.read(n) or b"{}")
                jid = prop_job_start(b["clip"], b.get("seeds") or [], float(b.get("back", 5)), float(b.get("fwd", 10)), float(b.get("step", 0.5)))
                self._bytes(json.dumps({"id": jid}).encode(), "application/json; charset=utf-8")
            except Exception as e:
                self._bytes(json.dumps({"err": str(e)}).encode(), "application/json; charset=utf-8", 500)
            return
        if p == "/api/sam2_save":             # 전파 결과 → 자동라벨/sam2 (손라벨과 별도)
            try:
                n = int(self.headers.get("Content-Length", 0))
                b = json.loads(self.rfile.read(n) or b"{}")
                cnt = sam2_store_write(b["clip"], b.get("frames") or {}, b.get("seeds") or [])
                self._bytes(json.dumps({"ok": True, "frames": cnt}).encode(), "application/json; charset=utf-8")
            except Exception as e:
                self._bytes(json.dumps({"ok": False, "err": str(e)}).encode(), "application/json; charset=utf-8", 500)
            return
        if p == "/api/sam2_cancel":           # 이 클립의 대기·진행 중 전파 취소
            try:
                n = int(self.headers.get("Content-Length", 0))
                b = json.loads(self.rfile.read(n) or b"{}")
                stem = Path(b["clip"]).stem; cnt = 0
                with _PROP_LOCK:
                    for jid0, st0 in _PROP_JOBS.items():
                        if st0.get("clip") == stem and st0.get("state") in ("queued", "running"):
                            st0["cancel"] = True; cnt += 1
                            if jid0 in _PROP_Q:
                                _PROP_Q.remove(jid0); st0["state"] = "done"; st0["running"] = False; st0["err"] = "cancelled"
                self._bytes(json.dumps({"ok": True, "cancelled": cnt}).encode(), "application/json; charset=utf-8")
            except Exception as e:
                self._bytes(json.dumps({"ok": False, "err": str(e)}).encode(), "application/json; charset=utf-8", 500)
            return
        if p == "/api/sam2_clear":            # 전파 토글 해제: 그 클립의 SAM 결과(프레임·씨앗) 전부 제거
            try:
                n = int(self.headers.get("Content-Length", 0))
                b = json.loads(self.rfile.read(n) or b"{}")
                cnt = sam2_store_clear(b["clip"])
                self._bytes(json.dumps({"ok": True, "dropped": cnt}).encode(), "application/json; charset=utf-8")
            except Exception as e:
                self._bytes(json.dumps({"ok": False, "err": str(e)}).encode(), "application/json; charset=utf-8", 500)
            return
        if p == "/api/sam2_drop":             # 검수 × : 그 프레임을 sam2 저장소에서 뺀다
            try:
                n = int(self.headers.get("Content-Length", 0))
                b = json.loads(self.rfile.read(n) or b"{}")
                cnt = sam2_store_drop(b["clip"], float(b["t"]))
                self._bytes(json.dumps({"ok": True, "dropped": cnt}).encode(), "application/json; charset=utf-8")
            except Exception as e:
                self._bytes(json.dumps({"ok": False, "err": str(e)}).encode(), "application/json; charset=utf-8", 500)
            return
        if p == "/api/sam2_propagate":       # 고른 객체 하나를 앞뒤로 전파(실험용, 저장 안 함)
            try:
                n = int(self.headers.get("Content-Length", 0))
                b = json.loads(self.rfile.read(n) or b"{}")
                if b.get("seeds") and any("obj" in sd for sd in b["seeds"]):
                    frames, ms, err = sam2_propagate_objs(b["clip"], b["seeds"],
                                                          back=float(b.get("back", 5)), fwd=float(b.get("fwd", 10)),
                                                          step=float(b.get("step", 0.5)))
                elif b.get("seeds"):
                    frames, ms, err = sam2_propagate_multi(b["clip"], b["seeds"],
                                                           back=float(b.get("back", 10)), fwd=float(b.get("fwd", 10)),
                                                           step=float(b.get("step", 0.5)))
                else:
                    frames, ms, err = sam2_propagate(b["clip"], float(b["t"]), box=b.get("box"), point=b.get("point"),
                                                     back=float(b.get("back", 15)), fwd=float(b.get("fwd", 15)),
                                                     step=float(b.get("step", 0.5)))
                self._bytes(json.dumps({"frames": frames, "sec": ms, "err": err}).encode(),
                            "application/json; charset=utf-8")
            except Exception as e:
                self._bytes(json.dumps({"frames": {}, "err": str(e)}).encode(),
                            "application/json; charset=utf-8", 500)
            return
        if p == "/api/autolabel_drop_obj":   # 그 위치의 객체를 클립 전체에서 제거(정지 오탐용)
            _SAVE_LOCK.acquire()
            try:
                n = int(self.headers.get("Content-Length", 0))
                body = json.loads(self.rfile.read(n) or b"{}")
                stem = Path(body["clip"]).stem
                bx = [float(v) for v in body["box"]]          # [x, y, w, h] 정규화
                thr = float(body.get("iou", 0.5))

                def hit(b):
                    ax1, ay1, ax2, ay2 = bx[0], bx[1], bx[0] + bx[2], bx[1] + bx[3]
                    bx1, by1, bx2, by2 = b[1], b[2], b[1] + b[3], b[2] + b[4]
                    inter = max(0.0, min(ax2, bx2) - max(ax1, bx1)) * max(0.0, min(ay2, by2) - max(ay1, by1))
                    ua = bx[2] * bx[3] + b[3] * b[4] - inter
                    return (inter / ua if ua > 0 else 0.0) >= thr

                gone_auto = 0
                f = AUTOLABEL_DIR / (stem + ".json")
                if f.exists():
                    d = json.loads(f.read_text(encoding="utf-8"))
                    for t, arr in (d.get("frames") or {}).items():
                        keep = [b for b in arr if not hit(b)]
                        gone_auto += len(arr) - len(keep)
                        d["frames"][t] = keep
                    tmp = f.with_suffix(f".json.tmp{os.getpid()}")
                    tmp.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
                    tmp.replace(f); _AUTOL.pop(str(f), None)

                gone_hand = 0                                  # 손라벨로 이미 병합된 자동 행도 같이 뺀다
                fl = data_path("data/학습데이터/손라벨/person_labels.json", "person_labels.json")
                if fl.exists():
                    rows = json.loads(fl.read_text(encoding="utf-8"))
                    keep = []
                    for r in rows:
                        if r.get("clip") == stem and hit([r.get("cls", 0), r.get("x", 0), r.get("y", 0), r.get("w", 0), r.get("h", 0)]):
                            gone_hand += 1; continue
                        keep.append(r)
                    if gone_hand:
                        _backup_labels(fl)
                        tmp = fl.with_suffix(f".json.tmp{os.getpid()}")
                        tmp.write_text(json.dumps(keep, ensure_ascii=False), encoding="utf-8")
                        tmp.replace(fl)
                self._bytes(json.dumps({"ok": True, "auto": gone_auto, "hand": gone_hand}).encode(),
                            "application/json; charset=utf-8")
            except Exception as e:
                self._bytes(json.dumps({"ok": False, "err": str(e)}).encode(),
                            "application/json; charset=utf-8", 500)
            finally:
                _SAVE_LOCK.release()
            return
        if p == "/api/autolabel_drop":       # 자동라벨에서 그 프레임을 뺀다(검수 화면의 ×). 손라벨과 무관.
            try:
                n = int(self.headers.get("Content-Length", 0))
                body = json.loads(self.rfile.read(n) or b"{}")
                f = AUTOLABEL_DIR / (Path(body["clip"]).stem + ".json")
                d = json.loads(f.read_text(encoding="utf-8"))
                t = f"{float(body['t']):.1f}"
                if t in (d.get("frames") or {}):
                    d["frames"][t] = []          # 지우지 않고 '검출 없음'으로 둔다(다시 프리필되지 않게)
                    tmp = f.with_suffix(f".json.tmp{os.getpid()}")
                    tmp.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
                    tmp.replace(f)
                    _AUTOL.pop(str(f), None)
                self._bytes(json.dumps({"ok": True}).encode(), "application/json; charset=utf-8")
            except Exception as e:
                self._bytes(json.dumps({"ok": False, "err": str(e)}).encode(),
                            "application/json; charset=utf-8", 500)
            return
        if p == "/api/clearlabels":           # 학습 프레임 초기화: 클립의 손라벨 전부 삭제(백업) + SAM 저장소 비움
            try:
                n = int(self.headers.get("Content-Length", 0))
                body = json.loads(self.rfile.read(n) or b"{}")
                clip = Path(body["clip"]).stem
                fn = "person_labels.json" if body.get("kind") == "person" else "fire_labels.json"
                fl = data_path("data/학습데이터/손라벨/" + fn, fn)
                with _SAVE_LOCK:
                    if fl.exists():                       # 초기화 직전 상태를 시각 붙여 따로 남긴다(복구용)
                        bdir = fl.parent / "_backup"; bdir.mkdir(exist_ok=True)
                        shutil.copyfile(fl, bdir / f"{fl.stem}.{time.strftime('%Y%m%d_%H%M%S')}.reset_{clip}.json")
                    rows = json.load(open(fl, encoding="utf-8")) if fl.exists() else []
                    keep = [r for r in rows if r.get("clip") != clip]
                    removed = len(rows) - len(keep)
                    tmp = fl.with_suffix(f".json.tmp{os.getpid()}")
                    tmp.write_text(json.dumps(keep, ensure_ascii=False, indent=1), encoding="utf-8"); tmp.replace(fl)
                sam_n = sam2_store_clear(body["clip"])
                self._bytes(json.dumps({"ok": True, "hand_rows": removed, "sam_frames": sam_n}).encode(), "application/json; charset=utf-8")
            except Exception as e:
                self._bytes(json.dumps({"ok": False, "err": str(e)}).encode(), "application/json; charset=utf-8", 500)
            return
        if p == "/api/savelabel":
            _SAVE_LOCK.acquire()
            try:
                n = int(self.headers.get("Content-Length", 0))
                body = json.loads(self.rfile.read(n) or b"{}")
                fn = "person_labels.json" if body.get("kind") == "person" else "fire_labels.json"
                fl = data_path("data/학습데이터/손라벨/" + fn, fn)
                _backup_labels(fl)
                rows = json.load(open(fl, encoding="utf-8")) if fl.exists() else []
                clip = body["clip"]
                # t 는 초. 프레임 단위로 고른 것은 소수가 된다(30fps 면 0.03 초 간격).
                # 정수 초면 정수로 남겨 기존 라벨과 같은 모양을 유지한다.
                t = round(float(body["t"]), 2)
                t = int(t) if t == int(t) else t
                # 같은 프레임(clip,t) 기존 박스는 덮어쓴다 (재저장 = 갱신)
                rows = [r for r in rows
                        if not (r.get("clip") == clip and abs(float(r.get("t", -999)) - t) < 0.01)]
                W = int(body.get("W", 1280)); Hh = int(body.get("H", 720))
                file = body.get("file", f"{clip}_{t}.png")
                src = str(body.get("src") or "").replace("\\", "/") or None
                for b in body.get("boxes", []):
                    cls, x, y, w, h = b
                    rows.append({"file": file, "clip": clip, "src": src, "t": t, "cls": int(cls),
                                 "x": round(float(x), 5), "y": round(float(y), 5),
                                 "w": round(float(w), 5), "h": round(float(h), 5),
                                 "W": W, "H": Hh, "crop": [0, 0, W, Hh]})
                if not body.get("boxes") and body.get("kind") == "person":
                    # 박스 0개로 저장(사람이 다 지움) = '검토했고 객체 없음' 마커. 이래야 다시 의사라벨 프리필 안 된다
                    rows.append({"file": file, "clip": clip, "src": src, "t": t, "cls": -1,
                                 "x": 0, "y": 0, "w": 0, "h": 0, "W": W, "H": Hh, "crop": [0, 0, W, Hh]})
                tmp = fl.with_suffix(f".json.tmp{os.getpid()}")   # 다른 프로세스가 같은 임시이름을 쓰면 내용이 섞인다
                json.dump(rows, open(tmp, "w", encoding="utf-8"), ensure_ascii=False)
                tmp.replace(fl)
                try:
                    _sam2_store_drop_raw(clip, t)                 # 손라벨이 SAM 을 대신: 이 프레임의 전파 결과는 저장소에서 뺀다
                except Exception:
                    pass
                self._bytes(json.dumps({"ok": True, "total": len(rows), "labels": rows}).encode(),
                            "application/json; charset=utf-8")
            except Exception as e:
                self._bytes(json.dumps({"ok": False, "err": str(e)}).encode(),
                            "application/json; charset=utf-8", 500)
            finally:
                _SAVE_LOCK.release()
            return
        self.send_error(404)

    def do_GET(self):
        p = urllib.parse.urlparse(self.path).path
        if p in ("/", "/index.html"):
            self._stream(HERE/"dashboard.html", "text/html; charset=utf-8"); return
        if p == "/app.js":
            self._stream(HERE/"app.js", "application/javascript; charset=utf-8"); return
        if p.startswith("/js/") and p.endswith(".js") and "/" not in p[4:] and ".." not in p:   # 분리된 대시보드 모듈
            self._stream(HERE/"js"/p[4:], "application/javascript; charset=utf-8"); return
        if p == "/api/meta":
            f = HERE/"dash_meta.json"
            self._stream(f, "application/json; charset=utf-8") if f.exists() else self.send_error(404, "dash_meta.json 없음"); return
        if p == "/api/dataset":
            f = HERE/"dataset_meta.json"
            self._stream(f, "application/json; charset=utf-8") if f.exists() else self.send_error(404, "dataset_meta.json 없음"); return
        if p == "/api/labels":
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            fn = "person_labels.json" if (q.get("kind") or [""])[0] == "person" else "fire_labels.json"
            f = data_path("data/학습데이터/손라벨/" + fn, fn)
            self._stream(f, "application/json; charset=utf-8") if f.exists() else self._bytes(b"[]", "application/json; charset=utf-8")
            return
        if p == "/api/sam2_jobs":            # 전파 작업 상태(클립별 또는 전체)
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            stem = Path((q.get("clip") or [""])[0]).stem or None
            self._bytes(json.dumps(prop_jobs_view(stem)).encode(), "application/json; charset=utf-8")
            return
        if p == "/api/gtlabel":              # 정답라벨 저장소(클립) {frames, points, events, actions}
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            f = GT_DIR / (Path((q.get("clip") or [""])[0]).stem + ".json")
            d = {"frames": {}, "points": {}, "events": [], "actions": {}}
            if f.exists():
                try: d = json.loads(f.read_text(encoding="utf-8"))
                except Exception: pass
            self._bytes(json.dumps(d, ensure_ascii=False).encode(), "application/json; charset=utf-8")
            return
        if p == "/api/gtframes":             # 정답 박스가 있는 프레임 시각 {stem: [t,...]}
            out = {}
            if GT_DIR.exists():
                for fj in GT_DIR.glob("*.json"):
                    try:
                        fr = json.loads(fj.read_text(encoding="utf-8")).get("frames") or {}
                        ts = sorted(float(k) for k, v in fr.items() if v)
                        if ts:
                            out[fj.stem] = ts
                    except Exception:
                        pass
            self._bytes(json.dumps(out).encode(), "application/json; charset=utf-8")
            return
        if p == "/api/sam2frames":           # 모든 클립의 SAM 전파 프레임 시각 목록 {stem: [t,...]} (목록 배지용)
            out = {}
            if SAM2_DIR.exists():
                for fj in SAM2_DIR.glob("*.json"):
                    try:
                        fr = json.loads(fj.read_text(encoding="utf-8")).get("frames") or {}
                        ts = sorted(float(k) for k, v in fr.items() if v)
                        if ts:
                            out[fj.stem] = ts
                    except Exception:
                        pass
            self._bytes(json.dumps(out).encode(), "application/json; charset=utf-8")
            return
        if p == "/api/sam2label":            # SAM 전파 결과 저장소(클립 전체) {frames: {t: {obj: [x,y,w,h]}}, seeds}
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            f = SAM2_DIR / (Path((q.get("clip") or [""])[0]).stem + ".json")
            d = {"frames": {}, "seeds": []}
            if f.exists():
                try: d = json.loads(f.read_text(encoding="utf-8"))
                except Exception: pass
            self._bytes(json.dumps(d, ensure_ascii=False).encode(), "application/json; charset=utf-8")
            return
        if p == "/api/autolabel":            # 미리 떠 둔 DINO 자동라벨(클립 전체)
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            d = autolabel_of((q.get("clip") or [""])[0])
            self._bytes(json.dumps(d or {"frames": {}, "missing": True}, ensure_ascii=False).encode(),
                        "application/json; charset=utf-8")
            return
        if p == "/api/sam2_progress":         # 전파 진행률/결과
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            st = _PROP_JOBS.get((q.get("id") or [""])[0]) or {"err": "no job", "running": False}
            self._bytes(json.dumps(st).encode(), "application/json; charset=utf-8")
            return
        if p == "/api/autolabel_bg":         # 현재 프레임 앞뒤 30초를 백그라운드 DINO 로 (없는 시각만)
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            clip = (q.get("clip") or [""])[0]; t = float((q.get("t") or ["0"])[0])
            st = bg_dino_start(clip, t) if q.get("start") else (_BG_DINO.get(clip) or {"done": 0, "total": 0, "running": False})
            self._bytes(json.dumps(st).encode(), "application/json; charset=utf-8")
            return
        if p == "/api/sam2_candidates":      # 그 프레임의 후보 객체(미리 뽑은 DINO → 없으면 즉석)
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            clip = (q.get("clip") or [""])[0]; t = float((q.get("t") or ["0"])[0])
            boxes = []; src = "none"
            pre = autolabel_of(clip)
            if pre:
                fr = (pre.get("frames") or {})
                hit = fr.get(f"{t:.1f}")
                if hit is None:
                    near = min(fr.keys(), key=lambda k: abs(float(k) - t), default=None)
                    if near is not None and abs(float(near) - t) <= 0.25:
                        hit = fr[near]
                if hit is not None:
                    boxes = [b[:5] for b in hit]; src = "dino_pre"
            if not boxes:
                try:
                    boxes = gdino_boxes(clip, t, 0.25); src = "dino_live"
                except Exception as e:
                    src = "err:" + str(e)
            self._bytes(json.dumps({"boxes": boxes, "src": src}).encode(), "application/json; charset=utf-8")
            return
        if p == "/api/sam2":                 # 점 하나 → SAM2 마스크의 타이트 박스
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            try:
                box, poly, sc = sam2_box((q.get("clip") or [""])[0], float((q.get("t") or ["0"])[0]),
                                         float((q.get("x") or ["0"])[0]), float((q.get("y") or ["0"])[0]))
                self._bytes(json.dumps({"box": box, "poly": poly, "score": round(sc, 3)}).encode(),
                            "application/json; charset=utf-8")
            except Exception as e:
                self._bytes(json.dumps({"box": None, "poly": None, "score": 0, "err": str(e)}).encode(),
                            "application/json; charset=utf-8")
            return
        if p == "/api/pseudolabel":
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            clip = (q.get("clip") or [""])[0]; t = float((q.get("t") or ["0"])[0])
            which = (q.get("model") or ["auto"])[0]   # auto=미리뽑은DINO→없으면person_v3 · gdino=지금 추론 · person=person_v3
            err = None; used = which
            try:
                if which == "gdino":
                    boxes = gdino_boxes(clip, t, float((q.get("th") or ["0.30"])[0]))
                else:
                    boxes = None
                    if which != "person":
                        pre = autolabel_of(clip)          # 배치로 미리 뽑아 둔 DINO 결과(파일 읽기라 즉시)
                        if pre:
                            fr = pre.get("frames") or {}
                            hit = fr.get(f"{float(t):.1f}")
                            if hit is None:               # 0.5초 격자에서 살짝 어긋난 요청도 가장 가까운 것으로
                                near = min(fr.keys(), key=lambda k: abs(float(k) - float(t)), default=None)
                                if near is not None and abs(float(near) - float(t)) <= 0.25:
                                    hit = fr[near]
                            if hit is not None:
                                boxes = [b[:5] for b in hit]      # [cls,x,y,w,h] 만 (뒤의 점수는 뺀다)
                                used = "dino_pre"
                    if boxes is None:
                        boxes = person_boxes(clip, t); used = "person_v3"
            except Exception as e:
                boxes = []; err = str(e)
            self._bytes(json.dumps({"boxes": boxes, "model": used, "err": err}).encode(),
                        "application/json; charset=utf-8")
            return
        if p == "/api/labelmeta":
            f = data_path("data/학습데이터/손라벨/full/meta.json", "labelfull/meta.json")
            self._stream(f, "application/json; charset=utf-8") if f.exists() else self.send_error(404)
            return
        if p == "/api/sources":
            self._bytes(json.dumps(sources(), ensure_ascii=False).encode(),
                        "application/json; charset=utf-8"); return
        if p == "/api/raw":
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            try: lim = max(min(int((q.get("limit") or ["600"])[0]), 3000), 1)
            except ValueError: lim = 600
            got = raw_items((q.get("src") or [""])[0], lim)
            if got is None:
                self.send_error(404, "category not found"); return
            self._bytes(json.dumps(got, ensure_ascii=False).encode(),
                        "application/json; charset=utf-8"); return
        if p == "/api/clipconds":            # 클립별 촬영 조건(야간·눈·비·안개) — 목록 필터용
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            self._bytes(json.dumps(clip_conds((q.get("src") or [""])[0]), ensure_ascii=False).encode(),
                        "application/json; charset=utf-8")
            return
        if p == "/api/clips":
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            clips = clips_of((q.get("src") or [""])[0])
            self._bytes(json.dumps(clips, ensure_ascii=False).encode(),
                        "application/json; charset=utf-8"); return
        if p == "/api/clipinfo":
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            info = clip_info((q.get("clip") or [""])[0])
            if not info:
                self.send_error(404, "clip not found"); return
            self._bytes(json.dumps(info).encode(), "application/json; charset=utf-8"); return
        if p == "/api/warmframes":           # 격자를 열기 전에 필요한 프레임을 한 번에 캐시로
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            clip = (q.get("clip") or [""])[0]
            w = int((q.get("w") or ["0"])[0])
            try:
                ts = [float(x) for x in (q.get("ts") or [""])[0].split(",") if x]
            except Exception:
                ts = []
            n = 0
            try:
                n = warm_frames(clip, ts, w)
            except Exception:
                pass
            self._bytes(json.dumps({"warmed": n, "total": len(ts)}).encode(),
                        "application/json; charset=utf-8")
            return
        if p == "/frameat":
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            try: sec = float((q.get("t") or ["0"])[0])
            except ValueError: sec = 0.0
            try: w = int(float((q.get("w") or ["0"])[0]))
            except ValueError: w = 0
            data = read_frame((q.get("clip") or [""])[0], sec, max(min(w, 4096), 0))
            if data is None:
                self.send_error(404, "frame not found"); return
            self._bytes(data, "image/jpeg"); return
        if p == "/api/newframes":
            f = data_path("data/학습데이터/손라벨/new/meta.json", "labelfull_new/meta.json")
            self._stream(f, "application/json; charset=utf-8") if f.exists() else self.send_error(404)
            return
        m = re.match(r"/dsimg/(.+)$", p)
        if m:
            ip = G/urllib.parse.unquote(m.group(1))
            if not ip.exists() and "/images/train/" in ip.as_posix():
                ip = Path(ip.as_posix().replace("/images/train/", "/images/"))   # train 하위 폴더 없이 images/ 에 바로 있는 세트
            if ip.exists() and WS in ip.resolve().parents:
                ext = ip.suffix.lower()
                ct = "image/png" if ext == ".png" else "image/jpeg"
                self._stream(ip, ct); return
            self.send_error(404); return
        if p == "/api/queue":                    # 실험 러너 상태(결과탭 상단). 실행중 = 실제 학습 프로세스(exp_queue.py _one <큐> <이름>), 로그=runner.log 끝
            running = []
            try:
                import subprocess as _sp
                ps = _sp.run(["pgrep", "-af", "exp_queue.py _one"], capture_output=True, text=True, timeout=5).stdout
                for line in ps.splitlines():
                    parts = line.split()
                    if len(parts) >= 2 and parts[-1] != "_one" and "pgrep" not in line:
                        running.append(parts[-1])          # 마지막 인자 = 실험 이름
            except Exception:
                pass
            q = {"running": sorted(set(running)), "log": []}
            try:
                q["log"] = (G / "logs/queue/runner.log").read_text(encoding="utf-8", errors="ignore").splitlines()[-25:]
            except Exception:
                pass
            self._bytes(json.dumps(q, ensure_ascii=False).encode(), "application/json; charset=utf-8"); return
        if p == "/api/clipstat":                 # 데이터확인 요약: 총수 + 표본(목록에 보이는 이미지) 라벨률·클래스 분포
            qs = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            got = raw_items((qs.get("src") or [""])[0], 600)
            if got is None:
                self.send_error(404, "category not found"); return
            lab = 0; cls = {}; boxes = 0
            for rel in got["images"]:
                lp = (G / rel).with_suffix(".txt")            # 1) 이미지 옆 YOLO txt (산불 frames 등)
                if not lp.is_file():
                    lp = raw_sibling_label(rel)                # 2) 다른 트리(labels/) 에 있는 경우
                if lp is None or not lp.is_file():
                    continue
                lab += 1
                for ln in lp.read_text(errors="ignore").splitlines():
                    ps = ln.split()
                    if len(ps) >= 5:
                        cls[ps[0]] = cls.get(ps[0], 0) + 1; boxes += 1
            note = RAW_CLASS_NOTE.get(got["cat"], "")
            self._bytes(json.dumps({"cat": got["cat"], "img_total": got["img_total"], "vid_total": got["vid_total"],
                                    "sample": len(got["images"]), "labeled": lab, "boxes": boxes, "classes": cls,
                                    "note": note}, ensure_ascii=False).encode(), "application/json; charset=utf-8"); return
        if p == "/api/results":
            out = []
            rdir = G / "results"
            pat = re.compile(r"^\s*(.+?)\s+→\s+([0-9.]+)\s+\(정검 (\d+) 미검 (\d+) 오검 (\d+)\)", re.M)
            files = sorted(rdir.glob("*.txt")) + sorted(rdir.glob("*/score.txt"))   # 구(평면 txt) + 신(results/<exp>/score.txt)
            for f in files:
                try:
                    txt = f.read_text(errors="ignore")
                except Exception:
                    continue
                _meta = {}
                if f.name == "score.txt":                       # 새 레이아웃: 실험명=폴더명, item 은 meta.json
                    try: _meta = json.loads((f.parent / "meta.json").read_text(encoding="utf-8"))
                    except Exception: _meta = {}
                rows = []
                for m in pat.finditer(txt):
                    rows.append({"rule": m.group(1).strip(), "score": float(m.group(2)),
                                 "tp": int(m.group(3)), "fn": int(m.group(4)), "fp": int(m.group(5))})
                if not rows:
                    continue
                _clips = {m.group(1): m.group(2) for m in re.finditer(r"^\s*클립 (\S+): (\S+)", txt, re.M)}   # score_kisa 클립별 판정
                best = max(rows, key=lambda r: r["score"])
                _oldrows = [r for r in rows if not r["rule"].startswith("신규칙")]   # 구 규칙만의 최고(신규칙과 나란히)
                _score_old = max(_oldrows, key=lambda r: r["score"])["score"] if _oldrows else None
                _stem = f.parent.name if f.name == "score.txt" else f.stem
                _s = _stem.lower()
                if _meta.get("item"):
                    _item = _meta["item"]
                elif "intrusion" in _s or "\uce68\uc785" in _s:      # 침입
                    _item = "\uce68\uc785"
                elif "loiter" in _s or "roam" in _s or "\ubc30\ud68c" in _s:   # 배회
                    _item = "\ubc30\ud68c"
                elif "fall" in _s or "faint" in _s or "collapse" in _s or "\uc4f0\ub7ec" in _s:  # 쓰러짐
                    _item = "\uc4f0\ub7ec\uc9d0"
                else:
                    _item = "\ubc29\ud654"                       # 방화(기본)
                out.append({"name": _stem, "score": best["score"], "rule": best["rule"],
                            "tp": best["tp"], "fn": best["fn"], "fp": best["fp"], "item": _item, "score_old": _score_old,
                            "meta": {k: _meta.get(k) for k in ("model", "base", "extras", "extra", "status", "n_train")}, "clips": _clips,
                            "n": len(rows), "mtime": int(f.stat().st_mtime), "rules": rows})
            out.sort(key=lambda r: -r["score"])
            self._bytes(json.dumps(out).encode("utf-8"), "application/json; charset=utf-8"); return
        if p == "/api/rawlabel":
            qs = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            rel = qs.get("rel", [""])[0]
            sib = (G/rel).with_suffix(".txt")               # 1) 원본 옆 YOLO txt
            try:
                if sib.exists() and WS in sib.resolve().parents:
                    self._stream(sib, "text/plain; charset=utf-8"); return
            except Exception:
                pass
            cl = coco_labels(rel)                            # 2) 원본 COCO annotations(train/val/test 전부)
            if cl:
                self._bytes(cl.encode("utf-8"), "text/plain; charset=utf-8"); return
            lp = raw_sibling_label(rel)                      # 2.5) 라벨이 다른 트리에 있는 원본(open_coco 등)
            if lp is not None:
                self._stream(lp, "text/plain; charset=utf-8"); return
            stem = Path(rel).stem                            # 3) 변환된 학습 라벨(파일명 매칭)
            for sp in ("train", "val"):
                for cp in (G/"data/학습데이터").glob("*/labels/" + sp + "/" + stem + ".txt"):
                    try:
                        if cp.exists() and WS in cp.resolve().parents:
                            self._stream(cp, "text/plain; charset=utf-8"); return
                    except Exception:
                        pass
            self._bytes(b"", "text/plain"); return
        m = re.match(r"/dslabel/(.+\.txt)$", p)
        if m:
            lp = G/urllib.parse.unquote(m.group(1))
            if not lp.exists() and "/labels/train/" in lp.as_posix():
                lp = Path(lp.as_posix().replace("/labels/train/", "/labels/"))
            if lp.exists() and WS in lp.resolve().parents:
                self._stream(lp, "text/plain; charset=utf-8"); return
            self._bytes(b"", "text/plain"); return
        m = re.match(r"/vid/(.+\.mp4)$", p)
        if m:
            vp = G/urllib.parse.unquote(m.group(1))
            if vp.exists() and WS in vp.resolve().parents: self._stream(vp, "video/mp4")
            else: self.send_error(404, "video not found")
            return
        m = re.match(r"/newframe/(.+\.png)$", p)
        if m:
            fp = data_path("data/학습데이터/손라벨/new", "labelfull_new")/urllib.parse.unquote(m.group(1))
            if fp.exists(): self._stream(fp, "image/png")
            else: self.send_error(404)
            return
        m = re.match(r"/frame/(.+\.png)$", p)
        if m:
            fp = data_path("data/학습데이터/손라벨/full", "labelfull")/urllib.parse.unquote(m.group(1))
            if fp.exists(): self._stream(fp, "image/png")
            else: self.send_error(404)
            return
        self.send_error(404)



def _warmup_models():
    """SAM2 이미지·비디오 모델을 미리 GPU 에 올린다(첫 요청 지연 제거). 실패해도 서버는 뜬다."""
    try:
        import torch
        from transformers.models.sam2.processing_sam2 import Sam2Processor
        from transformers.models.sam2.modeling_sam2 import Sam2Model
        global _SAM2
        if _SAM2 is None:
            dev = "cuda" if torch.cuda.is_available() else "cpu"
            _SAM2 = (Sam2Processor.from_pretrained(SAM2_ID), Sam2Model.from_pretrained(SAM2_ID).to(dev).eval(), dev)
    except Exception as e:
        print("[warmup] sam2 image:", e, flush=True)
    try:
        from transformers.models.sam2_video.processing_sam2_video import Sam2VideoProcessor
        from transformers.models.sam2_video.modeling_sam2_video import Sam2VideoModel
        global _SAM2V
        if _SAM2V is None:
            dev = "cuda" if torch.cuda.is_available() else "cpu"
            _SAM2V = (Sam2VideoProcessor.from_pretrained(SAM2V_ID), Sam2VideoModel.from_pretrained(SAM2V_ID).to(dev).eval(), dev)
    except Exception as e:
        print("[warmup] sam2 video:", e, flush=True)
    print("[warmup] done", flush=True)

if __name__ == "__main__":
    threading.Thread(target=_warmup_models, daemon=True).start()
    print(f"통합 대시보드: http://localhost:{PORT}/  (ssh -L {PORT}:localhost:{PORT} 로 로컬 접속)")
    ThreadingHTTPServer(("127.0.0.1", PORT), H).serve_forever()
