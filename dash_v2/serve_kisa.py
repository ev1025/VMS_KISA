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
import json, os, re, urllib.parse
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


def sources():
    """카테고리(원본데이터 1단계 폴더) 목록. count = 영상 편수(0 이면 이미지만 있는 폴더)."""
    out = []
    if not RAW.is_dir():
        return out
    for d in sorted((p for p in RAW.iterdir() if p.is_dir()), key=lambda q: (1 if "flir" in q.name.lower() else 0, q.name)):
        out.append({"key": d.name, "count": len(clips_of(d.name))})
    return out


IMG_EXT = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
_RAW = {}          # 카테고리별 파일 목록 캐시(폴더를 한 번만 훑는다)


def raw_items(cat, limit=600):
    """카테고리 안의 이미지·영상 목록. 경로는 vms 기준 상대경로(=/dsimg, /vid 주소에 그대로 쓴다).
    수만 장이면 고르게 샘플만 준다(목록이 목적이 아니라 눈으로 확인하는 게 목적)."""
    if cat in _RAW:
        got = _RAW[cat]
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

    def samp(a):
        if len(a) <= limit:
            return a
        step = len(a) / limit
        return [a[int(i * step)] for i in range(limit)]

    return {"cat": cat, "img_total": len(got["images"]), "vid_total": len(got["videos"]),
            "images": samp(got["images"]), "videos": samp(got["videos"])}


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
    return buf.tobytes() if ok else None


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
    for ox, oy, rw, rh in regions:
        r = _PERSON_MODEL.predict(fr[oy:oy + rh, ox:ox + rw], conf=conf, imgsz=640,
                                  classes=[0], device=dev, verbose=False)[0]
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
        if rng:
            m = re.match(r"bytes=(\d+)-(\d*)", rng)
            start = int(m.group(1)); end = int(m.group(2)) if m.group(2) else size-1
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
        if p == "/api/savelabel":
            try:
                n = int(self.headers.get("Content-Length", 0))
                body = json.loads(self.rfile.read(n) or b"{}")
                fn = "person_labels.json" if body.get("kind") == "person" else "fire_labels.json"
                fl = data_path("data/학습데이터/손라벨/" + fn, fn)
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
                tmp = fl.with_suffix(".json.tmp")
                json.dump(rows, open(tmp, "w", encoding="utf-8"), ensure_ascii=False)
                tmp.replace(fl)
                self._bytes(json.dumps({"ok": True, "total": len(rows), "labels": rows}).encode(),
                            "application/json; charset=utf-8")
            except Exception as e:
                self._bytes(json.dumps({"ok": False, "err": str(e)}).encode(),
                            "application/json; charset=utf-8", 500)
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
            self._stream(HERE/"dash_meta.json", "application/json; charset=utf-8"); return
        if p == "/api/dataset":
            self._stream(HERE/"dataset_meta.json", "application/json; charset=utf-8"); return
        if p == "/api/labels":
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            fn = "person_labels.json" if (q.get("kind") or [""])[0] == "person" else "fire_labels.json"
            f = data_path("data/학습데이터/손라벨/" + fn, fn)
            self._stream(f, "application/json; charset=utf-8") if f.exists() else self._bytes(b"[]", "application/json; charset=utf-8")
            return
        if p == "/api/pseudolabel":
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            clip = (q.get("clip") or [""])[0]; t = float((q.get("t") or ["0"])[0])
            try: boxes = person_boxes(clip, t)
            except Exception: boxes = []
            self._bytes(json.dumps({"boxes": boxes}).encode(), "application/json; charset=utf-8")
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
            if ip.exists() and WS in ip.resolve().parents:
                ext = ip.suffix.lower()
                ct = "image/png" if ext == ".png" else "image/jpeg"
                self._stream(ip, ct); return
            self.send_error(404); return
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
                best = max(rows, key=lambda r: r["score"])
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
                            "tp": best["tp"], "fn": best["fn"], "fp": best["fp"], "item": _item,
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


if __name__ == "__main__":
    print(f"통합 대시보드: http://localhost:{PORT}/  (ssh -L {PORT}:localhost:{PORT} 로 로컬 접속)")
    ThreadingHTTPServer(("127.0.0.1", PORT), H).serve_forever()
