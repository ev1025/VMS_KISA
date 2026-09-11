# -*- coding: utf-8 -*-
"""데이터 규격 계층: 원본 정답(형식이 데이터셋마다 다르다) → 우리 정답 복사본(한 가지 틀).

기준 파일 data/학습데이터/datasets.yaml 이 카테고리마다 mode/media/gt/classes/use 를 정한다. 코드는 형식(gt)별 어댑터 하나씩만 갖고,
새 데이터셋은 yaml 에 한 줄 추가로 끝난다. 원본 파일은 읽기만 한다.

우리 클래스 규약: fire 모드 0 불 · 1 연기 / person 모드 0 사람.
정답 복사본 틀(영상·이미지 공통):
  {"frames": {"<t>": {"<obj>": [x, y, w, h]}}, "cls": {"<obj>": c}, "points": {"<t>": {"<obj>": [x, y]}}, "events": [...], "actions": {...}, "src": <형식>, "src_file": <상대경로>}
  좌표는 정규화 [x, y, w, h](왼위 기준). 이미지는 t = "0.0" 한 프레임.
"""
import json, re, os
from pathlib import Path

CLASS_WORDS = {  # 이름으로 자동 매핑(classes 가 없을 때)
    "fire": (("fire", "flame", "화염", "불"), 0),
    "smoke": (("smoke", "연기"), 1),
    "person": (("person", "human", "pedestrian", "people", "사람"), 0),
}


class Datasets:
    """datasets.yaml 읽기/쓰기. 없는 카테고리는 파일을 훑어 기본값을 만든다(mode 는 이름으로 짐작)."""

    def __init__(self, path, raw_root):
        self.path = Path(path); self.raw = Path(raw_root); self._d = None; self._m = 0

    def all(self):
        try:
            m = self.path.stat().st_mtime
        except FileNotFoundError:
            m = 0
        if self._d is None or m != self._m:
            import yaml
            self._d = (yaml.safe_load(self.path.read_text(encoding="utf-8")) or {}) if self.path.exists() else {}
            self._m = m
        return self._d

    def get(self, cat):
        d = dict(self.all().get(cat) or {})
        d.setdefault("mode", guess_mode(cat)); d.setdefault("use", "train")
        if "media" not in d or "gt" not in d:
            media, gt = probe(self.raw / cat)
            d.setdefault("media", media); d.setdefault("gt", gt)
        return d

    def set(self, cat, **fields):
        import yaml
        d = dict(self.all()); cur = dict(d.get(cat) or {})
        for k, v in fields.items():
            if v is None:
                cur.pop(k, None)
            else:
                cur[k] = v
        d[cat] = cur
        tmp = self.path.with_suffix(".yaml.tmp")
        tmp.write_text(yaml.safe_dump(d, allow_unicode=True, sort_keys=True, default_flow_style=None), encoding="utf-8"); tmp.replace(self.path)
        self._d = None
        return cur


def guess_mode(cat):
    if re.search(r"사람|침입|쓰러짐|배회|스토킹|이상행동|다각도|person|human|llvip|flir", cat, re.I):
        return "person"
    return "fire"


def probe(root):
    """카테고리 폴더를 훑어 (media, gt) 를 짐작한다. yaml 에 적혀 있으면 안 부른다."""
    root = Path(root)
    if not root.is_dir():
        return "video", "none"
    has_mp4 = any(root.rglob("*.mp4"))
    media = "video" if has_mp4 else "image"
    xml = next(root.rglob("*.xml"), None)
    if xml is not None:
        try:
            head = xml.read_text(encoding="utf-8", errors="ignore")[:4000]
        except Exception:
            head = ""
        if "<keypoint>" in head or "<objectname>" in head:
            return media, "aihub171_xml"
        if "<Alarm" in head or "StartTime" in head:
            return media, "kisa_xml"
        if "<annotation>" in head and "<object>" in head:
            return media, "voc_xml"
    js = next(root.rglob("*.json"), None)
    if js is not None:
        try:
            d = json.loads(js.read_text(encoding="utf-8"))
        except Exception:
            d = {}
        if isinstance(d.get("videos"), list) and "annotations" in d:
            return media, "aihub71953_json"
        if isinstance(d.get("annotations"), dict) and "event_frame" in d["annotations"]:
            return media, "aihub_json"
        if isinstance(d.get("annotations"), list) and "images" in d:
            return media, "coco_json"
    if next(root.rglob("*.txt"), None) is not None:
        return media, "yolo_txt"
    return media, "none"


# ---------- 클래스 매핑 ----------
def map_class(cfg, key, name=None):
    """원본 클래스(id 또는 이름) → 우리 클래스. None = 버린다."""
    m = cfg.get("classes") or {}
    for k in (key, str(key), name, (name or "").lower()):
        if k is not None and k in m:
            v = m[k]
            return None if str(v).lower() == "drop" else int(v)
    txt = f"{name or ''} {key}".lower()
    mode = cfg.get("mode", "fire")
    for grp, (words, c) in CLASS_WORDS.items():
        if any(w in txt for w in words):
            if mode == "person" and grp != "person":
                continue
            if mode == "fire" and grp == "person":
                continue
            return c
    if m:                                             # classes 가 있는데 없는 키 → 버린다
        return None
    return 0 if mode == "person" else None            # 사람 모드는 이름 몰라도 사람 하나뿐. 화재는 이름 없이는 못 정한다


def _empty(src=None, src_file=None):
    return {"frames": {}, "cls": {}, "points": {}, "events": [], "actions": {}, "src": src, "src_file": src_file}


def _put_box(d, t, box, c):
    fr = d["frames"].setdefault(t, {})
    oid = str(len(fr) + 1)
    fr[oid] = [round(float(v), 5) for v in box]
    d["cls"][oid] = int(c)


# ---------- 형식별 어댑터(이미지: rel 은 vms 기준 이미지 상대경로 · 영상: mp4 Path) ----------
def yolo_txt_image(cfg, G, rel):
    """이미지 옆 또는 images/→labels/ 트리의 YOLO txt (cls cx cy w h, 정규화)."""
    p = G / rel
    cands = [p.with_suffix(".txt")]
    s = str(rel).replace("\\", "/")
    if "/images/" in s:
        cands.append(G / (s.rsplit("/images/", 1)[0] + "/labels/" + s.rsplit("/images/", 1)[1]).replace(Path(s).suffix, ".txt"))
        cands.append(G / (s.rsplit("/images/", 1)[0] + "/labels/" + Path(s).stem + ".txt"))
    lp = next((c for c in cands if c.is_file()), None)
    if lp is None:                                    # 다른 트리(labels/<상위>/<이름>.txt 등)를 깊이 3까지
        parts = s.split("/")
        if len(parts) >= 4:
            root = G / parts[0] / parts[1] / parts[2]
            for pat in (f"labels/{parts[-2]}/{Path(s).stem}.txt", f"*/labels/{parts[-2]}/{Path(s).stem}.txt", f"*/*/labels/{parts[-2]}/{Path(s).stem}.txt", f"labels/{Path(s).stem}.txt", f"*/labels/{Path(s).stem}.txt"):
                lp = next(root.glob(pat), None)
                if lp is not None and lp.is_file():
                    break
    d = _empty("yolo_txt", str(lp.relative_to(G)) if lp else None)
    if lp is None:
        return None
    for ln in lp.read_text(errors="ignore").splitlines():
        ps = ln.split()
        if len(ps) < 5:
            continue
        c = map_class(cfg, int(float(ps[0])))
        if c is None:
            continue
        cx, cy, w, h = map(float, ps[1:5])
        _put_box(d, "0.0", [cx - w / 2, cy - h / 2, w, h], c)
    return d


_COCO_CACHE = {}


def coco_json_image(cfg, G, rel):
    """.../images/<split>/<파일> ↔ .../annotations/<split>.json (COCO). 카테고리 이름으로 클래스 매핑."""
    s = str(rel).replace("\\", "/")
    m = re.match(r"(.*)/images/([^/]+)/([^/]+)$", s)
    if not m:
        return None
    base, split, fname = m.groups()
    jp = G / base / "annotations" / (split + ".json")
    if not jp.exists():
        return None
    key = str(jp)
    if key not in _COCO_CACHE:
        try:
            dj = json.loads(jp.read_text(encoding="utf-8"))
        except Exception:
            _COCO_CACHE[key] = ({}, {}); return None
        cats = {c["id"]: c.get("name", str(c["id"])) for c in dj.get("categories", [])}
        info = {im["id"]: (im["file_name"], im["width"], im["height"]) for im in dj.get("images", [])}
        by = {}
        for a in dj.get("annotations", []):
            it = info.get(a["image_id"])
            if it:
                by.setdefault(Path(it[0]).name, []).append((a["category_id"], a["bbox"], it[1], it[2]))
        _COCO_CACHE[key] = (by, cats)
    by, cats = _COCO_CACHE[key]
    d = _empty("coco_json", str(jp.relative_to(G)))
    for cid, (x, y, w, h), W, H in by.get(fname, []):
        c = map_class(cfg, cid, cats.get(cid))
        if c is None or not W or not H:
            continue
        _put_box(d, "0.0", [x / W, y / H, w / W, h / H], c)
    return d


def voc_xml_image(cfg, G, rel):
    """VOC xml: 같은 이름 xml 을 옆 또는 Annotations/ 트리에서 찾는다. <object><name> 으로 클래스 매핑."""
    import xml.etree.ElementTree as ET
    p = G / rel
    parts = str(rel).replace("\\", "/").split("/")
    root = G / parts[0] / parts[1] / parts[2] if len(parts) >= 3 else p.parent
    cands = [p.with_suffix(".xml")] + list(root.rglob(p.stem + ".xml"))
    xp = next((c for c in cands if c.is_file()), None)
    if xp is None:
        return None
    try:
        r = ET.parse(xp).getroot()
    except Exception:
        return None
    W = float(r.findtext("size/width") or 0); H = float(r.findtext("size/height") or 0)
    d = _empty("voc_xml", str(xp.relative_to(G)))
    if not W or not H:
        return d
    for ob in r.findall("object"):
        c = map_class(cfg, None, ob.findtext("name") or "")
        b = ob.find("bndbox")
        if c is None or b is None:
            continue
        x1, y1, x2, y2 = (float(b.findtext(k) or 0) for k in ("xmin", "ymin", "xmax", "ymax"))
        _put_box(d, "0.0", [x1 / W, y1 / H, (x2 - x1) / W, (y2 - y1) / H], c)
    return d


IMAGE_ADAPTERS = {"yolo_txt": yolo_txt_image, "coco_json": coco_json_image, "voc_xml": voc_xml_image}


def image_gt(cfg, G, rel):
    """이미지 한 장의 원본 정답 → 복사본 틀. 형식은 cfg["gt"]. none 이면 None."""
    fn = IMAGE_ADAPTERS.get(cfg.get("gt") or "none")
    return fn(cfg, G, rel) if fn else None


def to_yolo_lines(d):
    """복사본 → YOLO txt 줄(cls cx cy w h). 대시보드 /api/rawlabel 이 이걸 준다(우리 클래스 규약으로 통일된 값)."""
    out = []
    for oid, (x, y, w, h) in ((d.get("frames") or {}).get("0.0") or {}).items():
        out.append("%d %.6f %.6f %.6f %.6f" % (int(d["cls"].get(oid, 0)), x + w / 2, y + h / 2, w, h))
    return "\n".join(out)
