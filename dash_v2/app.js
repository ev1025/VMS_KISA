"use strict";
const $ = s => document.querySelector(s);
const el = (t, c, h) => { const e = document.createElement(t); if (c) e.className = c; if (h != null) e.innerHTML = h; return e; };
const fmt = s => s == null ? "-" : `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, "0")}`;
const BEFORE = 2, AFTER = 10;

let META = null, LABELS = null, PLABELS = null;
let CUR = { item: "fire", name: null, mode: "data" };   // 첫 화면 = 데이터 확인
let FILT = "all", VID = null;

// ---------- 예측 알람 시각 (대시보드는 대표 규칙 하나로 표시) ----------
function fireAlarm(row) {
  const rows = row.signal || []; if (!rows.length) return null;
  const head = rows.filter(r => r[0] <= 60).map(r => r[2]).sort((a, b) => a - b);
  const base = head.length ? head[Math.min(Math.floor(head.length * 0.8), head.length - 1)] : 0;
  // 서버 실측 최적 (전수 88.9): 불임계 0.12, 창 20표본, 12회 충족, 연기 기준선+0.15
  const win = [], W = 20, HIT = 12, FTH = 0.12, RISE = 0.15;
  for (const [t, fire, smoke] of rows) {
    const hit = fire >= FTH || (smoke >= base + RISE && smoke >= 0.3);
    win.push([t, hit]); if (win.length > W) win.shift();
    if (win.filter(x => x[1]).length >= HIT) return win.find(x => x[1])[0] + 10;
  }
  return null;
}
// 점이 다각형 안인지 (구역 판정의 바탕)
function inPoly(x, y, poly) {
  if (!poly || poly.length < 3) return false;
  let on = false;
  for (let i = 0, n = poly.length; i < n; i++) {
    const [x1, y1] = poly[i], [x2, y2] = poly[(i + 1) % n];
    if ((y1 > y) !== (y2 > y) && x < x1 + (y - y1) * (x2 - x1) / (y2 - y1)) on = !on;
  }
  return on;
}
// 사람이 구역에 들어왔나. corners 0=발끝만(배회), 3=몸전체(침입)
function entered(box, poly, corners) {
  const [x1, y1, x2, y2] = box;
  if (!inPoly((x1 + x2) / 2, y2, poly)) return false;
  if (corners <= 0) return true;
  const c = [[x1, y1], [x2, y1], [x1, y2], [x2, y2]];
  return c.filter(([a, b]) => inPoly(a, b, poly)).length >= corners;
}
// 침입: 트랙별 몸전체 진입 → 마지막 사람 진입시각 (서버 실측 규칙)
function intrusionAlarm(row) {
  const poly = row.zone; if (!poly || !poly.length || !row.tracks) return null;
  const CONF = 0.45, CORNERS = 3, HOLD = 2, SETTLE = 24;
  const streak = {}, entry = {}; let latest = null, lastNew = null;
  for (const r of row.tracks) {
    const seen = new Set();
    for (const b of r.boxes) {
      if (b[1] < CONF || !entered(b.slice(2, 6), poly, CORNERS)) continue;
      seen.add(b[0]); streak[b[0]] = (streak[b[0]] || 0) + 1;
      if (streak[b[0]] === HOLD && !(b[0] in entry)) {
        entry[b[0]] = r.t; latest = latest == null ? r.t : Math.max(latest, r.t); lastNew = r.t;
      }
    }
    for (const k in streak) if (!seen.has(+k)) streak[k] = 0;
    if (latest != null && r.t - lastNew >= SETTLE) return latest;
  }
  return latest;
}
// 배회: 트랙별 체류 dwell초 → 마지막 배회자 진입 + delay
function loiterAlarm(row) {
  const poly = row.zone; if (!poly || !poly.length || !row.tracks) return null;
  const CONF = 0.4, CORNERS = 0, DWELL = 6, DELAY = 10, SETTLE = 5, GAP = 6, STEP = 0.5;
  const dwell = {}, miss = {}, entry = {}, loit = {}; let latest = null, lastNew = null;
  for (const r of row.tracks) {
    const seen = new Set();
    for (const b of r.boxes) {
      if (b[1] < CONF || !entered(b.slice(2, 6), poly, CORNERS)) continue;
      seen.add(b[0]);
      if (!(dwell[b[0]] > 0)) entry[b[0]] = r.t;
      dwell[b[0]] = (dwell[b[0]] || 0) + STEP; miss[b[0]] = 0;
      if (dwell[b[0]] >= DWELL && !(b[0] in loit)) {
        loit[b[0]] = entry[b[0]];
        latest = latest == null ? entry[b[0]] : Math.max(latest, entry[b[0]]); lastNew = r.t;
      }
    }
    for (const k in dwell) if (!seen.has(+k)) { miss[k] = (miss[k] || 0) + 1; if (miss[k] > GAP) dwell[k] = 0; }
    if (latest != null && r.t - lastNew >= SETTLE) return latest + DELAY;
  }
  return latest == null ? null : latest + DELAY;
}
function personAlarm(row, item) {
  return item === "loiter" ? loiterAlarm(row) : intrusionAlarm(row);
}
function fallAlarm(row) {
  // 서버 실측 최적 (전수 88.9): 로짓 임계 -1.0 = sigmoid 0.269, 연속 4창. 트랙별 최초 돌파 중 가장 이른 것 (처음 쓰러진 사람)
  const TH = 0.269, NEED = 4;
  let best = null;
  for (const c of (row.curves || [])) {
    let run = 0;
    for (let i = 0; i < c.length; i++) {
      run = c[i][1] >= TH ? run + 1 : 0;
      if (run >= NEED) { const t = c[i - NEED + 1][0]; best = best == null ? t : Math.min(best, t); break; }
    }
  }
  return best;
}
function alarmOf(row, item) {
  if (item === "fire") return fireAlarm(row);
  if (item === "fall") return fallAlarm(row);
  return personAlarm(row, item);
}
function verdict(row, item) {
  if (item === "labelset") return row.box_count > 0 ? "라벨" : "빈프레임";  // 손라벨은 판정 대상 아님
  const gt = row.gt, sa = alarmOf(row, item);
  if (gt == null) return sa == null ? "정상" : "오탐";
  if (sa == null) return "미검";
  return (gt - BEFORE <= sa && sa <= gt + AFTER) ? "정검" : "오검";
}
const vClass = v => ({ "정검": "ok", "오검": "bad", "오탐": "bad", "미검": "miss", "정상": "none", "라벨": "ok", "빈프레임": "none" }[v] || "none");

// ---------- 좌: 원본 + 목록 ----------
// 영상 검수 = KISA 배포 4항목만 (손라벨 labelset 은 데이터 확인 탭으로)
const REVIEW_ITEMS = ["fire", "intrusion", "loiter", "fall"];
function buildSrc() {
  const sel = $("#srcSel"); sel.innerHTML = "";
  $(".srcbox label").textContent = "검수 항목";
  $("#filtBox").hidden = false;
  for (const k of REVIEW_ITEMS) {
    const v = META.items[k]; if (!v) continue;
    const o = el("option"); o.value = k; o.textContent = `${v.title} (${v.rows.length}편)`; sel.appendChild(o);
  }
  if (!REVIEW_ITEMS.includes(CUR.item)) CUR.item = "fire";
  sel.value = CUR.item;
  sel.onchange = () => {
    CUR.item = sel.value; CUR.name = null; renderList();
    $("#center").innerHTML = '<div class="empty">영상을 선택하세요</div>';
    $("#right").innerHTML = '<div class="empty">—</div>';
  };
}
function buildFilt() {
  const box = $("#filtBox"); box.innerHTML = "";
  [["all", "전체"], ["정검", "정검"], ["미검", "미검"], ["오검", "오검"]].forEach(([k, label]) => {
    const b = el("button", k === FILT ? "on" : "", label);
    b.onclick = () => { FILT = k; buildFilt(); renderList(); };
    box.appendChild(b);
  });
}
function renderList() {
  const box = $("#list"); box.innerHTML = "";
  const rows = META.items[CUR.item].rows;
  if (CUR.item === "labelset") {
    const clips = rows.length, boxes = rows.reduce((s, r) => s + (r.box_count || 0), 0);
    const frames = rows.reduce((s, r) => s + (r.frame_count || 0), 0);
  } else {
    // KISA 집계: 창 밖 알람(오검)은 오검+미검 이중 감점. 오검이면 fp 와 fn 을 모두 올린다.
    let tp = 0, fn = 0, fp = 0;
    rows.forEach(r => {
      const v = verdict(r, CUR.item);
      if (v === "정검") tp++;
      else if (v === "미검") fn++;
      else if (v === "오검") { fp++; fn++; }
      else if (v === "오탐") fp++;   // GT 없는 정상 영상에서의 헛알람은 fp 만
    });
    const rc = tp + fn ? tp / (tp + fn) : 0, pr = tp + fp ? tp / (tp + fp) : 0;
    const f1 = rc + pr ? 2 * rc * pr / (rc + pr) * 100 : 0;
  }
  rows.forEach(r => {
    const v = verdict(r, CUR.item);
    if (FILT !== "all" && v !== FILT) return;
    const it = el("div", "item" + (r.name === CUR.name ? " on" : ""));
    const vc = vClass(v);
    const col = { ok: "#3fb950", bad: "#f85149", miss: "#d29922", none: "#8b949e" }[vc] || "#8b949e";
    const vb = el("span", null, v);
    vb.style.cssText = `flex:0 0 auto;display:inline-flex;align-items:center;justify-content:center;min-width:42px;height:20px;padding:0 8px;border-radius:6px;font:700 11px/1 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;letter-spacing:.02em;color:${col};background:${col}22;border:1px solid ${col}55`;
    it.appendChild(vb);
    it.appendChild(el("span", "nm", r.name));
    it.onclick = () => {
      CUR.name = r.name; renderList();
      if (CUR.item === "labelset") renderLabelset(r); else { renderCenter(r); renderRight(r); }
    };
    box.appendChild(it);
  });
}

// ---------- 손라벨 프레임 뷰어 (중앙에 큰 이미지 + 박스, 우측에 썸네일) ----------
let LB_FRAME = 0;
function renderLabelset(row) {
  LB_FRAME = 0;
  const c = $("#center"); c.innerHTML = "";
  const r = $("#right"); r.innerHTML = "";
  if (!row.frames || !row.frames.length) { c.innerHTML = '<div class="empty">프레임 없음</div>'; return; }
  const wrap = el("div", "lblframe"); wrap.style.cssText = "margin:16px;max-width:900px";
  const img = el("img"); img.style.cssText = "width:100%;border-radius:8px;display:block";
  const ov = el("div"); ov.style.cssText = "position:absolute;inset:0";
  wrap.appendChild(img); wrap.appendChild(ov); c.appendChild(wrap);
  const cap = el("div"); cap.style.cssText = "margin:0 16px;color:var(--mut)"; c.appendChild(cap);
  const show = i => {
    const f = row.frames[i]; LB_FRAME = i;
    img.dataset.file = f.file; img.src = "/frame/" + encodeURIComponent(f.file);
    const drawBoxes = () => {
      let s = `<svg viewBox="0 0 ${f.W} ${f.H}" style="position:absolute;inset:0;width:100%;height:100%">`;
      (f.boxes || []).forEach(b => {
        // 손라벨 툴은 x,y 를 박스 좌상단으로 저장한다 (중앙 아님)
        const x = b[1] * f.W, y = b[2] * f.H;
        s += `<rect x="${x}" y="${y}" width="${b[3] * f.W}" height="${b[4] * f.H}" fill="none" stroke="${b[0] ? "#a371f7" : "#f85149"}" stroke-width="3"/>`;
      });
      s += "</svg>"; ov.innerHTML = s;
    };
    img.onload = drawBoxes; if (img.complete) drawBoxes();
    cap.innerHTML = `프레임 <b>${i + 1}/${row.frames.length}</b> · ${f.file} · 박스 ${(f.boxes || []).length}개` + (f.gt != null ? ` · GT ${fmt(f.gt)}` : "");
    $("#right").querySelectorAll(".tw").forEach((z, j) => z.classList.toggle("on", j === i));
  };
  // 우측: 썸네일 격자
  r.appendChild(el("div", "rtitle", `${row.name} <span class="tag">${row.frames.length}프레임 ${row.box_count}박스</span>`));
  const th = el("div", "thumbs");
  row.frames.forEach((f, i) => {
    const tw = el("div", "tw" + (i === 0 ? " on" : "")); const ti = el("img"); ti.src = "/frame/" + encodeURIComponent(f.file); tw.appendChild(ti);
    if ((f.boxes || []).length) { const badge = el("span"); badge.style.cssText = "position:absolute;top:2px;right:4px;font-size:10px;color:#f85149;font-weight:700"; badge.textContent = f.boxes.length; tw.appendChild(badge); }
    tw.onclick = () => show(i);
    th.appendChild(tw);
  });
  r.appendChild(th);
  r.appendChild(el("div", "leg", '<span><i style="background:#f85149"></i>불</span><span><i style="background:#a371f7"></i>연기</span>'));
  show(0);
}

// ---------- 중: 플레이어 + 재생바 ----------
function estDur(row) {
  const arr = row.signal_type === "fall" ? (row.curves[0] || []) : (row.signal || []);
  return arr.length ? arr[arr.length - 1][0] : 300;
}
function renderCenter(row) {
  const c = $("#center"); c.innerHTML = "";
  const gt = row.gt, sa = ("sa" in row) ? row.sa : alarmOf(row, CUR.item), gdur = row.gt_dur || 0;
  const stage = el("div", "stage");
  const v = el("video"); v.controls = false; v.preload = "metadata";
  v.src = "/vid/" + row.video.replace(/\\/g, "/").split("/").map(encodeURIComponent).join("/");
  const zoneov = el("div", "zoneov");
  v.onerror = () => { stage.innerHTML = '<div class="novid">⚠ 영상을 불러올 수 없습니다<br><small>' + row.video + "</small></div>"; };
  stage.appendChild(v); stage.appendChild(zoneov); c.appendChild(stage); VID = v;

  const ctrl = el("div", "ctrl");
  const pp = el("button", "", "▶"); pp.onclick = () => v.paused ? v.play() : v.pause();
  v.onplay = () => pp.textContent = "❚❚"; v.onpause = () => pp.textContent = "▶";
  const now = el("span", "now", "0:00");
  ctrl.appendChild(pp); ctrl.appendChild(now);
  if (gt != null) { const j = el("button", "jmp gt", "GT " + fmt(gt)); j.onclick = () => v.currentTime = Math.max(0, gt - 3); ctrl.appendChild(j); }
  if (sa != null) { const j = el("button", "jmp sa", "예측 " + fmt(sa)); j.onclick = () => v.currentTime = Math.max(0, sa - 3); ctrl.appendChild(j); }
  const rate = el("div", "rate");
  let wantRate = 1;
  [1, 2, 4, 8].forEach(x => {
    const b = el("button", x === 1 ? "on" : "", x + "x");
    b.onclick = () => {
      wantRate = x; v.playbackRate = x;
      rate.querySelectorAll("button").forEach(z => z.classList.remove("on")); b.classList.add("on");
    };
    rate.appendChild(b);
  });
  // 브라우저가 seek·로드 후 배속을 1로 되돌리는 경우가 있어, 선택한 배속을 다시 강제한다
  v.addEventListener("ratechange", () => { if (Math.abs(v.playbackRate - wantRate) > 0.01) v.playbackRate = wantRate; });
  v.addEventListener("play", () => { v.playbackRate = wantRate; });
  ctrl.appendChild(rate); c.appendChild(ctrl);

  const tl = el("div", "tl");
  const bar = el("div", "tlbar"); tl.appendChild(bar);
  const leg = el("div", "leg");
  leg.innerHTML = row.signal_type === "raw"
    ? '<span><i style="background:#3fb95055"></i>정답 유효창</span>'
    : row.signal_type === "fire_smoke"
    ? '<span><i style="background:var(--fire)"></i>불</span><span><i style="background:var(--smoke)"></i>연기</span><span><i style="background:#3fb95055"></i>GT 유효창</span><span><i style="background:var(--fire)"></i>예측알람</span>'
    : '<span><i style="background:var(--blue)"></i>신호</span><span><i style="background:#3fb95055"></i>GT 유효창</span><span><i style="background:var(--fire)"></i>예측알람</span>';
  tl.appendChild(leg); c.appendChild(tl);
  // 정답/예측/판정/시간대/날씨는 우측 정보창(renderRight)에 있으므로 중앙 하단 중복 표시는 제거

  let total = estDur(row);
  v.onloadedmetadata = () => { total = v.duration || total; drawBar(bar, row, gt, sa, total, 0); };
  v.ontimeupdate = () => { now.textContent = fmt(v.currentTime); drawBar(bar, row, gt, sa, total || v.duration, v.currentTime); drawZone(zoneov, row, v.currentTime); };
  bar.onclick = e => { const r = bar.getBoundingClientRect(); const t = (e.clientX - r.left) / r.width * (total || v.duration || 1); if (v.duration) v.currentTime = t; };
  drawBar(bar, row, gt, sa, total, 0);
}
function drawBar(bar, row, gt, sa, total, cur) {
  total = total || estDur(row) || 300;
  const W = 1000, H = 64, px = t => t / total * W;
  let s = `<svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none">`;
  if (gt != null) {
    const x0 = px(Math.max(0, gt - BEFORE)), x1 = px(Math.min(total, gt + AFTER));
    s += `<rect x="${x0}" y="0" width="${x1 - x0}" height="${H}" fill="#3fb95033"/>`;
    s += `<line x1="${px(gt)}" y1="0" x2="${px(gt)}" y2="${H}" stroke="#3fb950" stroke-width="2"/>`;
  }
  // 값이 거의 0 인 구간은 선을 그리지 않는다 (하단에 빨간 직선이 쭉 깔리는 것 방지).
  // 0 이하 점은 건너뛰고, 신호가 살아있는 구간만 이어 그린다.
  const plot = (pts, idx, color) => {
    if (!pts || !pts.length) return "";
    const MIN = 0.02;
    let d = "", pen = false;
    pts.forEach(p => {
      const v = p[idx];
      if (v < MIN) { pen = false; return; }               // 신호 없음 → 선 끊기
      const x = px(p[0]), y = H - Math.min(1, v) * (H - 6) - 3;
      d += (pen ? "L" : "M") + x.toFixed(1) + " " + y.toFixed(1) + " ";
      pen = true;
    });
    return d ? `<path d="${d}" fill="none" stroke="${color}" stroke-width="1.4"/>` : "";
  };
  if (row.signal_type === "fire_smoke") { s += plot(row.signal, 1, "#f85149"); s += plot(row.signal, 2, "#a371f7"); }
  else if (row.signal_type === "fall") { (row.curves || []).forEach(c => s += plot(c, 1, "#58a6ff99")); }
  else { s += plot(row.signal, 1, "#58a6ff"); }
  if (sa != null) s += `<line x1="${px(sa)}" y1="0" x2="${px(sa)}" y2="${H}" stroke="#f85149" stroke-width="2" stroke-dasharray="4 3"/>`;
  if (cur) s += `<line x1="${px(cur)}" y1="0" x2="${px(cur)}" y2="${H}" stroke="#58a6ff" stroke-width="1.5"/>`;
  s += "</svg>";
  bar.innerHTML = s;
}
// 박스 겹침 정도(IoU). 박스는 [식별, conf, x1,y1,x2,y2].
function iouBox(a, b) {
  const x1 = Math.max(a[2], b[2]), y1 = Math.max(a[3], b[3]), x2 = Math.min(a[4], b[4]), y2 = Math.min(a[5], b[5]);
  const inter = Math.max(0, x2 - x1) * Math.max(0, y2 - y1);
  const A = (a[4] - a[2]) * (a[5] - a[3]), B = (b[4] - b[2]) * (b[5] - b[3]);
  return inter / (A + B - inter + 1e-6);
}
// 타일 추론이 같은 대상을 풀프레임+타일에서 여러 번 잡아 박스가 겹쳐 보이는 것 제거.
function nmsBoxes(boxes, iouTh) {
  const keep = [];
  for (const b of boxes.slice().sort((p, q) => q[1] - p[1])) {
    if (!keep.some(k => iouBox(b, k) > iouTh)) keep.push(b);
  }
  return keep;
}
function drawZone(ov, row, t) {
  const hasZone = row.zone && row.zone.length, hasTracks = row.tracks && row.tracks.length;
  if (!hasZone && !hasTracks) { ov.innerHTML = ""; return; }
  const W = row.framew || 1280, He = row.frameh || 720;
  let s = `<svg viewBox="0 0 ${W} ${He}" preserveAspectRatio="none" style="width:100%;height:100%">`;
  if (hasZone) s += `<polygon points="${row.zone.map(p => p.join(",")).join(" ")}" fill="#3fb95022" stroke="#3fb950" stroke-width="3"/>`;
  if (hasTracks) {
    let near = null, best = 1e9;
    for (const r of row.tracks) { const d = Math.abs(r.t - t); if (d < best) { best = d; near = r; } }
    if (near && best < 1) {
      const fire = row.signal_type === "fire_smoke";   // 방화면 클래스별 색(불=빨강, 연기=보라)
      for (const b of nmsBoxes(near.boxes.filter(x => x[1] >= 0.25), 0.5)) {
        const col = fire ? (b[0] ? "#a371f7" : "#f85149") : "#f85149";
        s += `<rect x="${b[2]}" y="${b[3]}" width="${b[4] - b[2]}" height="${b[5] - b[3]}" fill="none" stroke="${col}" stroke-width="2"/>`;
      }
    }
  }
  s += "</svg>"; ov.innerHTML = s;
}

// ---------- 우: 맵 / 손라벨 ----------
function renderRight(row) {
  const r = $("#right"); r.innerHTML = "";
  r.appendChild(el("div", "rtitle", "영상 정보"));
  const KV = (k, val) => { const d = el("div", "kv"); d.appendChild(el("span", "", k)); d.appendChild(el("b", "", val)); return d; };
  r.appendChild(KV("이름", row.name));
  r.appendChild(KV("정답 GT", fmt(row.gt)));
  r.appendChild(KV("예측 알람", fmt(alarmOf(row, CUR.item))));
  r.appendChild(KV("판정", verdict(row, CUR.item)));
  r.appendChild(KV("시간대", row.tod || "-"));
  if ((row.weather || []).length) {
    const d = el("div", "kv"); d.appendChild(el("span", "", "특이날씨"));
    const b = el("b"); row.weather.forEach(w => b.appendChild(el("span", "tag warn", w))); d.appendChild(b); r.appendChild(d);
  }
  if (row.zone && row.zone.length) {
    r.appendChild(el("div", "rtitle", `구역맵 <span class="tag">${row.zone_tag}</span>`));
    const wrap = el("div", "zonewrap");
    const W = row.framew || 1280, He = row.frameh || 720;
    let s = `<svg viewBox="0 0 ${W} ${He}">`;
    if (row.detect && row.detect.length) s += `<polygon points="${row.detect.map(p => p.join(",")).join(" ")}" fill="none" stroke="#8b949e" stroke-width="2" stroke-dasharray="6 4"/>`;
    s += `<polygon points="${row.zone.map(p => p.join(",")).join(" ")}" fill="#3fb95022" stroke="#3fb950" stroke-width="3"/></svg>`;
    wrap.innerHTML = s; r.appendChild(wrap);
    r.appendChild(el("div", "leg", '<span><i style="background:#3fb950"></i>탐지구역</span><span><i style="background:#8b949e"></i>전체영역</span>'));
  }
  if (CUR.item === "fire") renderLabels(r, row);
}
function renderLabels(r, row) {
  if (!LABELS) return;
  const mine = LABELS.filter(l => l.clip === row.name);
  if (!mine.length) return;   // 손라벨(사람이 그린 정답)이 없으면 섹션 자체를 숨김 — 배포 영상은 원래 없음
  r.appendChild(el("div", "rtitle", `손라벨(사람 정답) <span class="tag">${mine.length}박스</span>`));
  const frames = [...new Set(mine.map(l => l.file))];
  const wrap = el("div", "lblframe");
  const img = el("img"); const ov = el("div"); ov.style.cssText = "position:absolute;inset:0";
  wrap.appendChild(img); wrap.appendChild(ov); r.appendChild(wrap);
  const draw = file => {
    const bx = mine.filter(l => l.file === file);
    let s = `<svg viewBox="0 0 ${bx[0].W} ${bx[0].H}" style="position:absolute;inset:0;width:100%;height:100%">`;
    bx.forEach(l => {
      const x = l.x * l.W, y = l.y * l.H;   // 손라벨 x,y = 좌상단
      s += `<rect x="${x}" y="${y}" width="${l.w * l.W}" height="${l.h * l.H}" fill="none" stroke="${l.cls ? "#a371f7" : "#f85149"}" stroke-width="3"/>`;
    });
    s += "</svg>"; ov.innerHTML = s;
  };
  img.onload = () => draw(img.dataset.file);
  img.dataset.file = frames[0]; img.src = "/frame/" + encodeURIComponent(frames[0]);
  if (frames.length > 1) {
    const th = el("div", "thumbs");
    frames.slice(0, 12).forEach((f, i) => {
      const tw = el("div", "tw" + (i === 0 ? " on" : "")); const ti = el("img"); ti.src = "/frame/" + encodeURIComponent(f); tw.appendChild(ti);
      tw.onclick = () => { img.dataset.file = f; img.src = "/frame/" + encodeURIComponent(f); th.querySelectorAll(".tw").forEach(z => z.classList.remove("on")); tw.classList.add("on"); };
      th.appendChild(tw);
    });
    r.appendChild(th);
  }
}

// ---------- 데이터 확인 탭 ----------
let DSMETA = null, DS_CUR = null, DS_ONLY_LABELED = false, DS_SEL = null, DS_KIND = "raw", DS_EDIT = false;   // raw=원본, ds=학습
async function buildDatasetSrc() {
  if (!DSMETA) DSMETA = await (await fetch("/api/dataset")).json();
  if (!SOURCES) { try { SOURCES = await (await fetch("/api/sources")).json(); } catch (e) { SOURCES = []; } }
  const sel = $("#srcSel"); sel.innerHTML = "";
  $("#filtBox").hidden = true;
  // 드롭다운 위: 원본 데이터 / 학습 데이터 고르는 버튼
  let kb = $("#dsKind");
  if (!kb) { kb = el("div"); kb.id = "dsKind"; $(".srcbox").insertBefore(kb, sel); }
  kb.hidden = false;
  kb.style.cssText = "display:flex;gap:4px;margin-bottom:6px";
  kb.innerHTML = "";
  [["raw", "원본 데이터"], ["ds", "학습 데이터"]].forEach(([k, label]) => {
    const b = el("button", null, label);
    const on = DS_KIND === k;
    b.style.cssText = "flex:1;border-radius:6px;padding:5px;cursor:pointer;font-size:11px;font-weight:700;" +
      (on ? "background:var(--blue);color:#06090f;border:1px solid var(--blue)"
          : "background:var(--panel);color:var(--mut);border:1px solid var(--line)");
    b.onclick = () => { if (DS_KIND === k) return; DS_KIND = k; DS_SEL = null; buildDatasetSrc(); };
    kb.appendChild(b);
  });
  // 드롭다운은 고른 쪽만
  if (DS_KIND === "raw") {
    $(".srcbox label").textContent = "원본 카테고리";
    SOURCES.forEach(x => {
      const o = el("option"); o.value = "raw:" + x.key;
      o.textContent = x.count ? `${x.key} (영상 ${x.count}편)` : x.key;
      sel.appendChild(o);
    });
  } else {
    $(".srcbox label").textContent = "학습 데이터셋";
    DSMETA.datasets.forEach(d => {
      const o = el("option"); o.value = "ds:" + d.key;
      o.textContent = `${d.title} (${d.total.toLocaleString()}장)`; sel.appendChild(o);
    });
  }
  if (!DS_SEL || ![...sel.options].some(o => o.value === DS_SEL)) DS_SEL = (sel.options[0] || {}).value;
  if (!DS_SEL) { $("#list").innerHTML = '<div class="empty">보여줄 데이터가 없습니다</div>'; return; }
  sel.value = DS_SEL;
  sel.onchange = () => pickDataSrc(sel.value);
  pickDataSrc(DS_SEL);
}

function pickDataSrc(v) {
  DS_SEL = v;
  if (v.startsWith("ds:")) { DS_CUR = DSMETA.datasets.find(d => d.key === v.slice(3)); renderDatasetList(); }
  else renderRawList(v.slice(4));
}

// ---------- 원본데이터 둘러보기 (이미지·영상 원재료) ----------
async function renderRawList(cat) {
  DS_EDIT = true;   // 카테고리 새로 고르면 편집가능 항목은 라벨편집부터(catMode 가 none 이면 자동으로 재생)
  const box = $("#list"); box.innerHTML = '<div class="empty">불러오는 중…</div>';
  $("#center").innerHTML = '<div class="empty">항목을 선택하세요</div>';
  $("#right").innerHTML = '<div class="empty">—</div>';
  let r;
  try { r = await (await fetch("/api/raw?src=" + encodeURIComponent(cat))).json(); }
  catch (e) { box.innerHTML = '<div class="empty">이 카테고리를 못 읽었습니다</div>'; return; }
  const shownImg = r.img_total > r.images.length ? ` (표시 ${r.images.length})` : "";
  box.innerHTML = "";
  if (!r.images.length && !r.videos.length) {
    box.innerHTML = '<div class="empty">이 폴더엔 이미지·영상이 없습니다<br><small>압축 상태이거나 라벨 파일만 있는 폴더</small></div>';
    return;
  }
  if (r.images.length) {
    r.images.forEach(rel => {
      const it = el("div", "item");
      const nm = el("span", "nm", rel.split("/").pop()); nm.title = rel; nm.style.userSelect = "text"; nm.style.cursor = "text";
      it.appendChild(nm);
      it.onclick = () => { if (window.getSelection && String(window.getSelection())) return; showRawImage(rel); };
      box.appendChild(it);
    });
    showRawImage(r.images[0]);
  }
  if (r.videos.length) {
    r.videos.forEach(rel => {
      const it = el("div", "item");
      const _vn = labeledCount(rel.split("/").pop().replace(/\.mp4$/, ""));   // 손라벨 있으면 개수 뱃지
      if (_vn) { const _vb = el("span", null, String(_vn)); _vb.style.cssText = "flex:0 0 auto;display:inline-flex;align-items:center;justify-content:center;min-width:26px;height:18px;padding:0 6px;border-radius:6px;font:700 11px/1 ui-monospace,Menlo,monospace;color:#cfe4ff;background:#58a6ff22;border:1px solid #58a6ff55;margin-right:6px"; it.appendChild(_vb); }
      const nm = el("span", "nm", rel.split("/").pop()); nm.title = rel; nm.style.userSelect = "text"; nm.style.cursor = "text";
      it.appendChild(nm);
      it.onclick = () => { if (window.getSelection && String(window.getSelection())) return; openClip(rel); };
      box.appendChild(it);
    });
    if (!r.images.length) openClip(r.videos[0]);
  }
}

// 원본 이미지 한 장. 같은 이름 YOLO txt 가 있으면 박스도 그린다.
async function showRawImage(rel) {
  const c = $("#center"); c.innerHTML = "";
  const enc = rel.split("/").map(encodeURIComponent).join("/");
  const wrap = el("div", "lblframe");
  wrap.style.cssText = "position:relative;display:inline-block;align-self:center;margin:auto;max-width:calc(100% - 32px)";
  const img = el("img");
  img.style.cssText = "display:block;max-width:100%;max-height:calc(100vh - 150px);width:auto;height:auto;border-radius:8px";
  const ov = el("div"); ov.style.cssText = "position:absolute;inset:0";
  img.src = "/dsimg/" + enc;
  wrap.appendChild(img); wrap.appendChild(ov); c.appendChild(wrap);
  let boxes = [];
  try {
    const txt = await (await fetch("/api/rawlabel?rel=" + encodeURIComponent(rel))).text();
    boxes = txt.trim().split("\n").filter(Boolean).map(l => l.split(/\s+/).map(Number)).filter(b => b.length >= 5);
  } catch (e) {}
  const draw = () => {
    const W = img.naturalWidth || 1280, H = img.naturalHeight || 720;
    let g = `<svg viewBox="0 0 ${W} ${H}" style="position:absolute;inset:0;width:100%;height:100%">`;
    boxes.forEach(b => {
      const x = (b[1] - b[3] / 2) * W, y = (b[2] - b[4] / 2) * H;
      g += `<rect x="${x}" y="${y}" width="${b[3] * W}" height="${b[4] * H}" fill="none" stroke="${b[0] ? "#a371f7" : "#f85149"}" stroke-width="3"/>`;   // 불=빨강, 연기=보라
    });
    ov.innerHTML = g + "</svg>";
  };
  img.onload = draw; if (img.complete) draw();
  const r = $("#right"); r.innerHTML = "";
  r.appendChild(el("div", "rtitle", "이미지 정보"));
  const KV = (k, val) => { const dv = el("div", "kv"); dv.appendChild(el("span", "", k)); dv.appendChild(el("b", "", val)); return dv; };
  // 긴 파일명·경로는 한 줄에 안 들어간다 → 제목 아래에 쌓아서 줄바꿈으로 보여준다
  const KVstack = (k, val) => {
    const d = el("div"); d.style.cssText = "padding:6px 0;border-bottom:1px solid var(--line)";
    const t = el("div", "", k); t.style.cssText = "color:var(--mut);font-size:11px;margin-bottom:2px";
    const v = el("div", "", val);
    v.style.cssText = "font-family:ui-monospace,Menlo,monospace;font-size:11px;word-break:break-all;line-height:1.45";
    d.appendChild(t); d.appendChild(v); return d;
  };
  r.appendChild(KVstack("파일", rel.split("/").pop()));
  r.appendChild(KVstack("경로", rel.replace(/\/[^/]+$/, "")));
  r.appendChild(KV("라벨(기존 GT)", boxes.length ? boxes.length + "박스" : "없음"));
}

// 카테고리로 편집 모드 판정: fire / person / none
function catMode(rel) {
  const cat = (rel || "").split("/")[2] || "";
  if (/검증|채점|배포/.test(cat)) return "none";
  if (/방화|산불/.test(cat)) return "fire";
  if (/사람|침입|쓰러짐|배회|스토킹/.test(cat)) return "person";
  return "none";
}
// 라벨편집 진입: 에디터 열고 우측을 '영상 보기' 버튼으로
function openEditorFor(rel) {
  const clip = rel.replace("data/원본데이터/", "").replace(".mp4", "");
  const mode = catMode(rel);
  DS_EDIT = true;
  openFrameAt(clip, null, mode);
  const r = $("#right"); r.innerHTML = "";
  r.appendChild(el("div", "rtitle", mode === "person" ? "사람 라벨 편집" : "라벨 편집"));
  const vb = el("button", null, "\u25B6 영상 보기");
  vb.style.cssText = "width:100%;margin-bottom:10px;padding:8px;border-radius:6px;cursor:pointer;font-weight:700;font-size:12px;background:var(--panel2);color:var(--tx);border:1px solid var(--blue)";
  vb.onclick = () => { DS_EDIT = false; showRawVideo(rel); };
  r.appendChild(vb);
  const KVs = (k, val) => { const d = el("div"); d.style.cssText = "padding:6px 0;border-bottom:1px solid var(--line)"; const t = el("div", "", k); t.style.cssText = "color:var(--mut);font-size:11px;margin-bottom:2px"; const vv = el("div", "", val); vv.style.cssText = "font-family:ui-monospace,Menlo,monospace;font-size:11px;word-break:break-all;line-height:1.45"; d.appendChild(t); d.appendChild(vv); return d; };
  r.appendChild(KVs("파일", rel.split("/").pop()));
}
// 좌측 영상 클릭: 편집 중이면 그 영상 편집 유지, 아니면 재생
function openClip(rel) {
  showRawVideo(rel);   // showRawVideo 가 DS_EDIT 를 보고 에디터/영상 결정
}
// 원본 영상 한 편. XML 정답(이벤트 시각)이 있으면 같이 보여준다.
async function showRawVideo(rel) {
  const clip = rel.replace(/^data\/원본데이터\//, "").replace(/\.mp4$/, "");
  let events = [], dur = 0, ci = null;
  try { ci = await (await fetch("/api/clipinfo?clip=" + encodeURIComponent(clip))).json(); dur = ci.dur || 0; events = ci.fire || []; } catch (e) {}
  const first = events[0] || {};
  document.onkeydown = null;
  const _mode0 = catMode(rel);
  const _editing = DS_EDIT && _mode0 !== "none";
  if (_editing) {
    openFrameAt(clip, first.start != null ? first.start : null, _mode0);   // 편집 중 = 중앙은 에디터
  } else {
    ED = null;   // 영상 볼 땐 에디터 재사용상태 초기화(다음 라벨편집이 새로 그리게)
    renderCenter({ video: rel, name: rel.split("/").pop(), signal_type: "raw", signal: [], zone: [], tracks: null,
                   weather: [], tod: null, gt: (first.start != null ? first.start : null), gt_dur: first.dur || 0, sa: null });
  }
  // 우측 정보(파일/경로/정답)
  const r = $("#right"); r.innerHTML = "";
  r.appendChild(el("div", "rtitle", "영상 정보"));
  const KV = (k, val) => { const dv = el("div", "kv"); dv.appendChild(el("span", "", k)); dv.appendChild(el("b", "", val)); return dv; };
  const KVstack = (k, val) => {
    const d = el("div"); d.style.cssText = "padding:6px 0;border-bottom:1px solid var(--line)";
    const t = el("div", "", k); t.style.cssText = "color:var(--mut);font-size:11px;margin-bottom:2px";
    const vv = el("div", "", val); vv.style.cssText = "font-family:ui-monospace,Menlo,monospace;font-size:11px;word-break:break-all;line-height:1.45";
    d.appendChild(t); d.appendChild(vv); return d;
  };
  r.appendChild(KVstack("파일", rel.split("/").pop()));
  r.appendChild(KVstack("경로", rel.replace(/\/[^/]+$/, "")));
  if (ci) {
    r.appendChild(KV("길이", `${Math.floor(dur)}초`));
    r.appendChild(KV("해상도", `${ci.W}x${ci.H} · ${ci.fps}fps`));
    events.forEach((fs, i) => r.appendChild(KV(events.length > 1 ? `정답 ${i + 1}` : "정답", `${fmt(fs.start)} · ${fs.dur}초간`)));
    if (!events.length) r.appendChild(KV("정답", "XML 없음"));
  } else r.appendChild(KV("정답", "정보 없음"));
  // 라벨 대상 클립이면 버튼: 편집중=영상보기 / 아니면 라벨편집 (영상정보는 그대로)
  const _stem = stemOf(clip);
  if (_mode0 !== "none") {
    { const _n = labeledCount(_stem); r.appendChild(KV("손라벨", _n ? _n + "프레임" : "없음")); }   // fire·person 둘 다
    const _eb = el("button", null, _editing ? "\u25B6 영상 보기" : "라벨 편집");
    _eb.style.cssText = "width:100%;margin-top:10px;padding:8px;border-radius:6px;cursor:pointer;font-weight:700;font-size:12px;" +
      (_editing ? "background:var(--panel2);color:var(--tx);border:1px solid var(--blue)" : "background:var(--blue);color:#06090f;border:1px solid var(--blue)");
    _eb.onclick = () => { DS_EDIT = !_editing; showRawVideo(rel); };
    r.appendChild(_eb);
  }
}
function renderDatasetList() {
  const box = $("#list"); box.innerHTML = "";
  const d = DS_CUR;
  const shown = d.total > d.shown ? `표시 ${d.shown} / ${d.total.toLocaleString()}장` : `${d.total.toLocaleString()}장`;
  // 필터 대신 라벨만 보기 토글
  const bar = el("div"); bar.style.cssText = "padding:6px 3px;display:flex;gap:6px";
  const tog = el("button", DS_ONLY_LABELED ? "on" : "", "라벨 있는 것만");
  tog.style.cssText = "flex:1;background:var(--panel);color:" + (DS_ONLY_LABELED ? "var(--tx)" : "var(--mut)") + ";border:1px solid " + (DS_ONLY_LABELED ? "var(--blue)" : "var(--line)") + ";border-radius:6px;padding:5px;cursor:pointer;font-size:11px";
  tog.onclick = () => { DS_ONLY_LABELED = !DS_ONLY_LABELED; renderDatasetList(); };
  bar.appendChild(tog); box.appendChild(bar);
  // 좌측은 이미지가 많아 격자 썸네일로
  const grid = el("div"); grid.style.cssText = "display:grid;grid-template-columns:1fr 1fr;gap:4px";
  let imgs = d.images; if (DS_ONLY_LABELED) imgs = imgs.filter(x => x.labeled);
  imgs.slice(0, 300).forEach(im => {
    const tw = el("div"); tw.style.cssText = "position:relative;cursor:pointer;border-radius:5px;overflow:hidden;border:1px solid var(--line);aspect-ratio:16/10;background:#000";
    const t = el("img"); t.loading = "lazy"; t.style.cssText = "width:100%;height:100%;object-fit:cover"; t.src = "/dsimg/" + (im.rel || d.rel) + "/images/train/" + encodeURIComponent(im.file);
    tw.appendChild(t);
    if (im.labeled) { const dot = el("span"); dot.style.cssText = "position:absolute;top:3px;right:3px;width:7px;height:7px;border-radius:50%;background:#3fb950"; tw.appendChild(dot); }
    tw.onclick = () => { box.querySelectorAll(".dson").forEach(z => z.classList.remove("dson")); tw.classList.add("dson"); tw.style.outline = "2px solid var(--blue)"; showDatasetImage(d, im); };
    grid.appendChild(tw);
  });
  box.appendChild(grid);
  if (imgs.length) showDatasetImage(d, imgs[0]);
}
async function showDatasetImage(d, im) {
  const c = $("#center"); c.innerHTML = "";
  const wrap = el("div", "lblframe");
  wrap.style.cssText = "position:relative;display:inline-block;align-self:center;margin:auto;max-width:calc(100% - 32px)";
  const img = el("img");
  img.style.cssText = "display:block;max-width:100%;max-height:calc(100vh - 150px);width:auto;height:auto;border-radius:8px";
  const ov = el("div"); ov.style.cssText = "position:absolute;inset:0";
  img.src = "/dsimg/" + (im.rel || d.rel) + "/images/train/" + encodeURIComponent(im.file);
  wrap.appendChild(img); wrap.appendChild(ov); c.appendChild(wrap);
  // 라벨(YOLO txt) 로드 → 박스
  let boxes = [];
  if (im.labeled) {
    try {
      const txt = await (await fetch("/dslabel/" + (im.rel || d.rel) + "/labels/train/" + encodeURIComponent(im.stem) + ".txt")).text();
      boxes = txt.trim().split("\n").filter(Boolean).map(l => l.split(/\s+/).map(Number));
    } catch (e) {}
  }
  const COL = ["#f85149", "#a371f7", "#58a6ff", "#3fb950", "#d29922"];
  const drawBoxes = () => {
    const W = img.naturalWidth || 1280, H = img.naturalHeight || 720;
    let s = `<svg viewBox="0 0 ${W} ${H}" style="position:absolute;inset:0;width:100%;height:100%">`;
    boxes.forEach(b => {
      // YOLO: cls cx cy w h (중앙 정규화)
      const x = (b[1] - b[3] / 2) * W, y = (b[2] - b[4] / 2) * H;
      s += `<rect x="${x}" y="${y}" width="${b[3] * W}" height="${b[4] * H}" fill="none" stroke="${COL[b[0]] || "#f85149"}" stroke-width="3"/>`;
    });
    s += "</svg>"; ov.innerHTML = s;
  };
  img.onload = drawBoxes; if (img.complete) drawBoxes();
  // 우측: 파일 정보 + 클래스별 박스 수 + 원시 라벨
  const r = $("#right"); r.innerHTML = "";
  r.appendChild(el("div", "rtitle", "데이터 정보"));
  const KV = (k, val) => { const dv = el("div", "kv"); dv.appendChild(el("span", "", k)); dv.appendChild(el("b", "", val)); return dv; };
  r.appendChild(KV("데이터셋", d.title));
  r.appendChild(KV("파일", im.file));
  r.appendChild(KV("YOLO 라벨", boxes.length ? boxes.length + "박스" : "없음 (정상 이미지)"));
  const cnt = {};
  boxes.forEach(b => cnt[b[0]] = (cnt[b[0]] || 0) + 1);
  d.classes.forEach((cl, i) => r.appendChild(KV(cl, String(cnt[i] || 0) + "박스")));
  if (boxes.length) {
    r.appendChild(el("div", "rtitle", "YOLO 라벨 (원문)"));
    const pre = el("div"); pre.style.cssText = "font-family:ui-monospace,monospace;font-size:11px;color:var(--mut);white-space:pre-wrap;word-break:break-all";
    pre.textContent = boxes.map(b => b.map((x, i) => i ? x.toFixed(4) : d.classes[x] || x).join(" ")).join("\n");
    r.appendChild(pre);
  }
}

// ---------- 모드 ----------
function buildMode() {
  const box = $("#modeBox"); box.innerHTML = "";
  [["data", "데이터 확인"], ["review", "영상 검수"], ["results", "결과"]].forEach(([k, label]) => {
    const b = el("button", k === CUR.mode ? "on" : "", label);
    b.onclick = () => { if (CUR.mode === k) return; CUR.mode = k; buildMode(); applyMode(); };
    box.appendChild(b);
  });
}
function applyMode() {
  document.onkeydown = null;   // 편집기 밖에선 단축키 끄기
  $("#right").hidden = (CUR.mode === "label" || CUR.mode === "results");   // 라벨 생성·결과는 우측 없이
  $(".srcbox").hidden = (CUR.mode === "results");   // 결과 탭은 소스 드롭다운 숨김
  const kindBox = $("#dsKind"); if (kindBox) kindBox.style.display = (CUR.mode === "data") ? "flex" : "none";   // 원본/학습 버튼은 데이터 확인에서만
  const emptyMsg = { data: "데이터셋과 이미지를 선택하세요", review: "영상을 선택하세요", label: "프레임을 선택하세요" }[CUR.mode];
  $("#center").innerHTML = '<div class="empty">' + emptyMsg + '</div>';
  $("#right").innerHTML = '<div class="empty">—</div>';
  if (CUR.mode === "data") {
    buildDatasetSrc();
  } else if (CUR.mode === "label") {
    buildLabelSrc();
    labelEmptyCenter();
  } else if (CUR.mode === "results") {
    $("#list").innerHTML = ""; buildResults();
  } else {
    buildSrc(); buildFilt(); renderList();
    // 첫 진입 시 첫 영상 자동 열기(현재 선택이 목록에 있으면 유지)
    const _rows = META.items[CUR.item].rows.filter(r => FILT === "all" || verdict(r, CUR.item) === FILT);
    const _cur = _rows.find(r => r.name === CUR.name) || _rows[0];
    if (_cur) { CUR.name = _cur.name; renderList(); renderCenter(_cur); renderRight(_cur); }
  }
}
// ---------- 손라벨 편집기 (클립의 1초 간격 프레임에 박스 그려 저장) ----------
// 좌측 목록 = 데이터 원본(클립) 목록. 클립을 고르면 1초 간격으로 프레임을 넘기며 박스를 그린다.
// 라벨은 초당 1장 기준(30fps 전부는 이웃 프레임이 사실상 같은 그림이라 낭비).
// 그린 박스는 /api/savelabel → fire_labels.json 에 들어가고 다음 학습에 자동 포함된다.
let CLIPS = null, SOURCES = null, LB = { cat: null, clip: null, sec: 0, boxes: [], file: null };
const stemOf = pathStr => String(pathStr).split("/").pop();   // 라벨은 파일 이름(stem)으로 묶인다

// 현재 편집 모드의 라벨 저장소(person 이면 PLABELS, 아니면 LABELS)
function _labelStore() { return (LB.mode === "person") ? PLABELS : LABELS; }
// 이미 손라벨된 프레임의 박스(프리필용). 같은 clip + 같은 초를 찾는다.
function existingBoxes(clip, t) {
  const S = _labelStore(); if (!S) return null;
  const rs = S.filter(r => r.clip === clip && Math.abs(Number(r.t) - t) < 0.25);   // 0.5초(2FPS) 프레임을 정수반올림하면 63.5/64.0 이 충돌 → 허용오차로 정확히 매칭
  if (!rs.length) return null;                                          // 저장 기록 자체가 없음 → 의사라벨 프리필 대상
  return rs.filter(r => r.cls >= 0).map(r => [r.cls, r.x, r.y, r.w, r.h]);   // 기록은 있는데 박스 0개(cls -1 마커)=검토완료 → 빈 배열(프리필 안 함)
}
// 그 클립에서 라벨해 둔 초 목록(참조 샷).
function shotSecs(clip) {
  const S = _labelStore(); if (!S) return [];
  const by = {};
  S.filter(r => r.clip === clip && r.cls >= 0).forEach(r => { const s = Math.round(r.t); by[s] = (by[s] || 0) + 1; });
  return Object.keys(by).map(Number).sort((a, b) => a - b).map(s => [s, by[s]]);
}
// 목록 배지는 항상 화재(LABELS) 기준 — 편집모드에 안 흔들리게
function labeledCount(clip) {
  const by = {};   // fire(LABELS)·person(PLABELS) 어느 쪽 손라벨이든 그 클립의 프레임 수를 센다
  for (const S of [LABELS, PLABELS]) { if (S) S.filter(r => r.clip === clip && r.cls >= 0).forEach(r => { by[Math.round(r.t)] = 1; }); }
  return Object.keys(by).length;
}

// 클립 원본 영상 정보(fps·길이·해상도). 클립당 한 번만 조회해 캐시한다.
let ED = null;        // 지금 열려 있는 편집기(같은 클립이면 재사용해 깜빡임을 없앤다)
let loadSeq = 0;      // 프레임 요청 순번. 늦게 도착한 그림은 버린다
const CLIPINFO = {};
async function clipInfo(clip) {
  if (CLIPINFO[clip]) return CLIPINFO[clip];
  const r = await fetch("/api/clipinfo?clip=" + encodeURIComponent(clip));
  if (!r.ok) throw new Error("clipinfo " + r.status);
  CLIPINFO[clip] = await r.json();
  return CLIPINFO[clip];
}

async function buildLabelSrc() {
  $("#filtBox").hidden = true;
  $(".srcbox label").textContent = "원본 영상 카테고리";   // 아직 라벨 안 된 원재료
  const sel = $("#srcSel");
  if (!SOURCES) {
    try { SOURCES = await (await fetch("/api/sources")).json(); }
    catch (e) { $("#list").innerHTML = '<div class="empty">카테고리를 못 읽었습니다</div>'; return; }
  }
  sel.innerHTML = "";
  const vids = SOURCES.filter(x => x.count && /방화|산불/.test(x.key) && !/검증|채점|배포/.test(x.key));   // 손라벨 대상 = 방화·산불 영상(합성 산불도 실제 불이라 라벨 대상), 채점/배포 제외
  vids.forEach(x => {
    const o = el("option"); o.value = x.key; o.textContent = `${x.key} (${x.count}편)`;
    sel.appendChild(o);
  });
  if (!LB.cat || !vids.some(x => x.key === LB.cat)) LB.cat = (vids[0] || {}).key || null;
  sel.value = LB.cat;
  sel.onchange = () => { LB.cat = sel.value; LB.clip = null; ED = null; loadClips(); };
  await loadClips();
}

// 고른 카테고리의 영상 목록을 좌측에 채운다
async function loadClips() {
  $("#list").innerHTML = '<div class="empty">불러오는 중…</div>';
  try { CLIPS = await (await fetch("/api/clips?src=" + encodeURIComponent(LB.cat))).json(); }
  catch (e) { $("#list").innerHTML = '<div class="empty">영상 목록을 못 읽었습니다</div>'; return; }
  renderClipList();
  // 첫 진입 시 첫 클립 자동 열기(현재 선택이 목록에 있으면 유지)
  const _first = (CLIPS || []).find(c => c === LB.clip) || (CLIPS || [])[0];
  if (_first) { LB.clip = _first; renderClipList(); openFrameAt(_first); }
  else labelEmptyCenter();
}

// 좌측: 데이터 원본(클립) 목록. 라벨해 둔 장수를 같이 보여준다.
function renderClipList() {
  if (CUR.mode !== "label") return;   // 데이터확인 등에서 열린 편집기는 좌측 목록을 안 건드린다
  const box = $("#list"); box.innerHTML = "";
  (CLIPS || []).forEach(cl => {
    const n = labeledCount(stemOf(cl));
    const it = el("div", "item" + (cl === LB.clip ? " on" : ""));
    const shown = LB.cat && cl.startsWith(LB.cat + "/") ? cl.slice(LB.cat.length + 1) : cl;
    const badge = el("span", null, n ? String(n) : "");
    badge.style.cssText = "flex:0 0 auto;display:inline-flex;align-items:center;justify-content:center;min-width:30px;height:20px;padding:0 8px;border-radius:6px;font:700 12px/1 ui-monospace,SFMono-Regular,Menlo,monospace;font-variant-numeric:tabular-nums;letter-spacing:.02em;" + (n ? "color:#cfe4ff;background:#58a6ff22;border:1px solid #58a6ff55" : "");
    it.appendChild(badge);
    const nm = el("span", "nm", shown); nm.title = cl; nm.style.userSelect = "text"; nm.style.cursor = "text";
    it.appendChild(nm);
    const ci = CLIPINFO[cl];
    if (ci && ci.fire && ci.fire.length) it.title = `화재 발생 ${ci.fire.map(x => x.start + "s").join(", ")}`;
    it.onclick = () => { if (window.getSelection && String(window.getSelection())) return; LB.clip = cl; renderClipList(); openFrameAt(cl); };   // 초를 안 주면 화재 발생 시각부터
    box.appendChild(it);
  });
}

function labelEmptyCenter() {
  ED = null;      // 화면을 비우면 재사용할 편집기도 없다(다시 열 때 새로 만든다)
  $("#center").innerHTML = '<div class="empty">왼쪽에서 데이터 원본(클립)을 고르세요</div>';
}

// 그 초의 프레임을 편집기에 띄운다. 라벨 단위가 1초라 sec 는 정수로 맞춘다.
function _step() { return LB.mode === "person" ? 0.5 : 1; }   // person(침입쓰러짐)=0.5초(2FPS)
function _disp(sec) { return LB.mode === "person" ? Math.round(sec * 2) : sec; }   // 사람: 화면엔 정수 프레임번호(초×2)
function _undisp(v) { return LB.mode === "person" ? v / 2 : v; }
async function openFrameAt(clip, sec, mode) {
  LB.mode = mode || LB.mode || "fire";
  if (LB.mode === "person" && !PLABELS) { try { PLABELS = await (await fetch("/api/labels?kind=person")).json(); } catch (e) { PLABELS = []; } }
  let ci;
  try { ci = await clipInfo(clip); }
  catch (e) { $("#center").innerHTML = '<div class="empty">이 영상 정보를 못 읽었습니다</div>'; return; }
  const last = Math.max(Math.floor(ci.dur), 0);
  // 초를 안 주면 XML 의 화재 발생 시각으로 간다(0초부터 뒤질 일이 없다)
  if (sec == null) sec = (ci.fire && ci.fire.length) ? ci.fire[0].start : 0;
  const savedAt = s2 => existingBoxes(stemOf(clip), s2);
  const _q = LB.mode === "person" ? 2 : 1; sec = Math.min(Math.max(Math.round(sec * _q) / _q, 0), last);   // person 은 0.5초 단위로 반올림
  LB.clip = clip; LB.sec = sec;
  let saved = savedAt(sec);
  if (LB.mode === "person" && !saved) {
    try { const pj = await (await fetch("/api/pseudolabel?clip=" + encodeURIComponent(clip) + "&t=" + sec)).json(); if (pj.boxes && pj.boxes.length) saved = pj.boxes; } catch (e) {}
  }
  const url = `/frameat?clip=${encodeURIComponent(clip)}&t=${sec}`;
  if (ED && ED.clip === clip) {
    // 화면을 지우지 않는다. 새 그림을 다 받은 뒤 바꿔 끼우면 사라졌다 나타나는 깜빡임이 없다.
    const n = ++loadSeq;
    const pre = new Image();
    pre.onload = pre.onerror = () => { if (n === loadSeq) ED.applyFrame(sec, url, saved); };
    pre.src = url;
    return;
  }
  loadSeq++;
  renderEditor({
    clip, stem: stemOf(clip), src: clip + ".mp4", t: sec, last, W: ci.W, H: ci.H,
    file: `${stemOf(clip)}_${String(sec).padStart(4, "0")}.png`,   // 저장 기록용 이름(학습셋은 원본에서 다시 뽑는다)
    url,
    saved: saved,
  });
}

function rectSvg(x, y, w, h, cls, dash, on) {
  const stroke = (LB.mode === "person") ? "#3fb950" : (cls ? "#a371f7" : "#f85149");
  return `<rect x="${x}" y="${y}" width="${w}" height="${h}" fill="${on ? stroke + '22' : 'none'}" stroke="${stroke}" stroke-width="${on ? 6 : 3}" ${dash ? 'stroke-dasharray="8 5"' : ''}/>`;
}

function renderEditor(f) {
  LB.file = f.file;
  LB.boxes = f.saved ? f.saved.map(b => b.slice()) : [];
  const c = $("#center"); c.innerHTML = "";
  // 이미지 + 그리기 오버레이 (이미지 위에는 아무 글자도 얹지 않는다)
  const pane = el("div"); pane.style.cssText = `width:100%;max-width:min(${f.W}px, calc((100vh - 400px) * 16 / 9));margin:auto;padding:12px 8px 0`;
  c.appendChild(pane);
  const wrap = el("div"); wrap.style.cssText = "position:relative";
  const img = el("img"); img.src = f.url; img.style.cssText = "width:100%;display:block;border-radius:6px;-webkit-user-drag:none";
  const ov = el("div"); ov.style.cssText = "position:absolute;inset:0;cursor:crosshair";
  wrap.appendChild(img); wrap.appendChild(ov); pane.appendChild(wrap);
  // 휠 = 프레임 확대/축소(1~8x). 커서 기준, 프레임 박스 안에서만 확대(주변 레이아웃 안 밀림).
  wrap.style.overflow = "hidden";
  let _zoom = 1, _tx = 0, _ty = 0;   // origin 0 0 고정 + translate 로 커서 밑 지점을 붙잡아 누적 확대해도 안 튄다
  const _applyZoom = () => {
    const t = "translate(" + _tx + "px," + _ty + "px) scale(" + _zoom + ")";
    img.style.transformOrigin = "0 0"; img.style.transform = t;
    ov.style.transformOrigin = "0 0"; ov.style.transform = t;
  };
  ov.addEventListener("wheel", ev => {
    ev.preventDefault();
    const rc = wrap.getBoundingClientRect();
    const cx = ev.clientX - rc.left, cy = ev.clientY - rc.top, z0 = _zoom;
    _zoom = Math.min(Math.max(_zoom * (ev.deltaY < 0 ? 1.15 : 1 / 1.15), 1), 8);
    _tx = cx - (_zoom / z0) * (cx - _tx);   // 지금 커서 밑에 있는 지점이 확대 후에도 커서 아래 그대로
    _ty = cy - (_zoom / z0) * (cy - _ty);
    _tx = Math.min(0, Math.max(rc.width * (1 - _zoom), _tx));   // 박스 밖 빈공간 방지
    _ty = Math.min(0, Math.max(rc.height * (1 - _zoom), _ty));
    if (_zoom === 1) { _tx = 0; _ty = 0; }
    _applyZoom();
  }, { passive: false });

  // 재생바(1초 단위) + 그 아래 참조 샷 한 줄
  const status = el("span", "now", "");            // 저장 상태(이미지 위가 아니라 재생바 안에 쓴다)
  const bar = buildFrameBar(f, status);
  pane.appendChild(bar);
  const shots = el("div");
  pane.appendChild(shots);
  const undoBar = el("div");   // 삭제 직후 되돌리기 버튼이 잠깐 뜨는 자리
  undoBar.style.cssText = "padding:2px 2px 8px";
  pane.appendChild(undoBar);
  let undoTimer = null;
  let drawRef = () => {};      // 아래에서 draw 로 채운다(선언 순서 때문에 참조로 둔다)
  const fillShots = () => (drawTrack(bar.tk, f), renderShotRow(shots, f, {
    onDeleted: (sec, prev) => {
      if (sec === f.t) { LB.boxes = []; f.saved = null; }   // 지금 보고 있는 프레임을 지웠으면 화면 박스도 비운다
      renderClipList(); fillShots(); drawRef();
      showUndo(sec, prev);
    },
  }));
  // 삭제 되돌리기: 지운 박스를 그대로 다시 써 넣는다. 6초 뒤 버튼은 사라진다.
  const showUndo = (sec, prev) => {
    clearTimeout(undoTimer); undoBar.innerHTML = "";
    if (!prev || !prev.length) return;
    const b = el("button", null, `↺ 되돌리기`);
    b.style.cssText = "background:var(--panel2);color:var(--tx);border:1px solid var(--blue);border-radius:6px;padding:4px 10px;font-size:11px;font-weight:700;cursor:pointer";
    b.onclick = async () => {
      b.textContent = "…";
      try {
        await postLabel(f.stem, sec, f.W, f.H, prev, f.src);
        if (sec === f.t) { LB.boxes = prev.map(q => q.slice()); f.saved = prev; }
        renderClipList(); fillShots(); drawRef();
        undoBar.innerHTML = "";
      } catch (e) { b.textContent = "실패"; }
    };
    undoBar.appendChild(b);
    undoTimer = setTimeout(() => { undoBar.innerHTML = ""; }, 6000);
  };
  fillShots();

  let saveState = "";
  const draw = (drag, dcls) => {
    let s = `<svg viewBox="0 0 ${f.W} ${f.H}" style="position:absolute;inset:0;width:100%;height:100%">`;
    LB.boxes.forEach((b, i) => { s += rectSvg(b[1] * f.W, b[2] * f.H, b[3] * f.W, b[4] * f.H, b[0], false, false); });
    if (drag) s += rectSvg(drag.x, drag.y, drag.w, drag.h, dcls, true);
    ov.innerHTML = s + "</svg>";
    status.innerHTML = saveState ? `<span style="color:#f85149">${saveState}</span>` : "";   // 성공은 표시하지 않는다
  };
  const saveNow = async () => {
    try {
      const res = await postLabel(f.stem, f.t, f.W, f.H, LB.boxes, f.src);
      f.saved = LB.boxes.map(b => b.slice());
      renderClipList();          // 좌측 클립 목록의 라벨 장수 갱신
      fillShots();               // 참조 샷 줄에 이 초를 반영
      saveState = ""; draw();
    } catch (e) { saveState = "저장 실패"; draw(); }
  };
  // 드래그로 박스: 좌버튼=불(0), 우버튼=연기(1), 그리는 즉시 자동저장
  // 이미 있는 박스는 변·모서리 근처를 잡아 크기를 고친다(핸들은 그리지 않는다).
  let st = null, curCls = 0, rz = null, mv = null, sel = null, pan = null, _space = false;   // sel=Del대상, mv=이동, pan=스페이스드래그 화면이동
  const HIT = 8;                       // 화면 기준 8px 안이면 그 변을 잡은 것으로 본다
  const CURSOR = { n: "ns-resize", s: "ns-resize", w: "ew-resize", e: "ew-resize", nw: "nwse-resize", se: "nwse-resize", ne: "nesw-resize", sw: "nesw-resize" };
  const toImg = ev => { const rc = img.getBoundingClientRect(); return { x: (ev.clientX - rc.left) / rc.width * f.W, y: (ev.clientY - rc.top) / rc.height * f.H }; };
  // 마우스가 어느 박스의 어느 변에 닿았나. 위에 그린 박스(뒤 항목)부터 본다.
  const hitTest = p => {
    const rc = img.getBoundingClientRect();
    const tol = HIT * (f.W / (rc.width || f.W));       // 화면 px → 원본 px
    for (let i = LB.boxes.length - 1; i >= 0; i--) {
      const b = LB.boxes[i];
      const x1 = b[1] * f.W, y1 = b[2] * f.H, x2 = x1 + b[3] * f.W, y2 = y1 + b[4] * f.H;
      if (p.x < x1 - tol || p.x > x2 + tol || p.y < y1 - tol || p.y > y2 + tol) continue;
      let tag = "";
      if (Math.abs(p.y - y1) <= tol) tag += "n"; else if (Math.abs(p.y - y2) <= tol) tag += "s";
      if (Math.abs(p.x - x1) <= tol) tag += "w"; else if (Math.abs(p.x - x2) <= tol) tag += "e";
      if (tag) return { i, tag };
    }
    return null;
  };
  // 커서가 얹힌 박스(안쪽 포함). 위에 그린 것부터 본다.
  const boxUnder = p => {
    for (let i = LB.boxes.length - 1; i >= 0; i--) {
      const b = LB.boxes[i];
      const x1 = b[1] * f.W, y1 = b[2] * f.H, x2 = x1 + b[3] * f.W, y2 = y1 + b[4] * f.H;
      if (p.x >= x1 && p.x <= x2 && p.y >= y1 && p.y <= y2) return i;
    }
    return null;
  };
  // 잡은 자리를 유지하며 옮긴다. 이미지 밖으로는 나가지 않는다.
  const moveTo = p => {
    const b = LB.boxes[mv.i]; if (!b) return;
    const w = b[3] * f.W, h = b[4] * f.H;
    b[1] = Math.min(Math.max(p.x - mv.ox, 0), f.W - w) / f.W;
    b[2] = Math.min(Math.max(p.y - mv.oy, 0), f.H - h) / f.H;
  };
  const resizeTo = p => {
    const b = LB.boxes[rz.i]; if (!b) return;
    let x1 = b[1] * f.W, y1 = b[2] * f.H, x2 = x1 + b[3] * f.W, y2 = y1 + b[4] * f.H;
    if (rz.tag.includes("n")) y1 = p.y;
    if (rz.tag.includes("s")) y2 = p.y;
    if (rz.tag.includes("w")) x1 = p.x;
    if (rz.tag.includes("e")) x2 = p.x;
    if (x2 < x1) { const t = x1; x1 = x2; x2 = t; }    // 반대편으로 넘겨 끌면 좌우가 뒤집힌다
    if (y2 < y1) { const t = y1; y1 = y2; y2 = t; }
    x1 = Math.max(x1, 0); y1 = Math.max(y1, 0); x2 = Math.min(x2, f.W); y2 = Math.min(y2, f.H);
    b[1] = x1 / f.W; b[2] = y1 / f.H;
    b[3] = Math.max(x2 - x1, 6) / f.W; b[4] = Math.max(y2 - y1, 6) / f.H;   // 6px 아래로는 안 줄인다
  };
  ov.oncontextmenu = ev => ev.preventDefault();   // 우클릭 메뉴 차단(연기 그리기용)
  ov.onmousedown = ev => {
    ev.preventDefault();
    if (_space) { pan = { sx: ev.clientX, sy: ev.clientY, tx0: _tx, ty0: _ty }; ov.style.cursor = "grabbing"; return; }   // 스페이스+드래그 = 확대이미지 이동
    const p = toImg(ev);
    const h = ev.button === 2 || ev.shiftKey ? null : hitTest(p);   // 우클릭·Shift 는 언제나 새 박스
    if (h) { rz = h; sel = h.i; return; }
    if (ev.button !== 2 && !ev.shiftKey) {
      const u = boxUnder(p);                        // 박스 안쪽을 잡았으면 위치 이동
      if (u !== null) {
        const b = LB.boxes[u];
        mv = { i: u, ox: p.x - b[1] * f.W, oy: p.y - b[2] * f.H };
        sel = u; return;
      }
    }
    curCls = (LB.mode === "person") ? 0 : (ev.button === 2 ? 1 : 0); st = p;
  };
  ov.onmousemove = ev => {
    if (pan) {
      const rc = wrap.getBoundingClientRect();
      _tx = Math.min(0, Math.max(rc.width * (1 - _zoom), pan.tx0 + (ev.clientX - pan.sx)));
      _ty = Math.min(0, Math.max(rc.height * (1 - _zoom), pan.ty0 + (ev.clientY - pan.sy)));
      _applyZoom(); return;
    }
    const p = toImg(ev);
    if (rz) { resizeTo(p); draw(); return; }
    if (mv) { moveTo(p); draw(); return; }
    if (st) { draw({ x: Math.min(st.x, p.x), y: Math.min(st.y, p.y), w: Math.abs(p.x - st.x), h: Math.abs(p.y - st.y) }, curCls); return; }
    const h = hitTest(p);
    ov.style.cursor = h ? (CURSOR[h.tag] || "crosshair") : "crosshair";
    const u = h ? h.i : boxUnder(p);
    if (!h && u !== null) ov.style.cursor = "move";
    // 호버로는 sel 을 바꾸지 않는다 — 클릭으로 잡은 Del 대상이 마우스 이동에 풀리면 안 됨
  };
  const finish = ev => {
    if (pan) { pan = null; ov.style.cursor = _space ? "grab" : "crosshair"; return; }   // 이동 끝
    if (rz) { rz = null; draw(); saveNow(); return; }      // 크기조절 끝 → 그 자리에서 저장
    if (mv) { mv = null; draw(); saveNow(); return; }      // 이동 끝 → 그 자리에서 저장
    if (!st) return; const p = toImg(ev);
    const x = Math.min(st.x, p.x), y = Math.min(st.y, p.y), w = Math.abs(p.x - st.x), h = Math.abs(p.y - st.y); st = null;
    if (w > 4 && h > 4) { LB.boxes.push([curCls, x / f.W, y / f.H, w / f.W, h / f.H]); draw(); saveNow(); }
    else { draw(); saveNow(); }   // 박스 안 쳐도 프레임 안쪽 클릭이면 현재 상태 저장(빈 라벨=검토완료)
  };
  ov.onmouseup = finish;
  ov.onmouseleave = ev => { finish(ev); };   // sel 유지 → 박스 클릭 후 마우스 나가도 Del 됨
  drawRef = draw;
  img.onload = () => draw(); if (img.complete) draw();
  // 같은 클립의 다른 초로 넘어갈 때는 이 함수만 부른다(DOM 을 다시 만들지 않는다)
  ED = {
    clip: f.clip,
    applyFrame: (sec, url, saved) => {
      f.t = sec; f.url = url; f.saved = saved;
      f.file = `${f.stem}_${String(sec).padStart(4, "0")}.png`;
      LB.file = f.file; LB.sec = sec;
      LB.boxes = saved ? saved.map(b => b.slice()) : [];
      sel = null; st = null; rz = null; mv = null;
      img.src = url;                     // 미리 받아둔 그림이라 즉시 바뀐다
      bar.sl.value = _disp(sec); bar.num.value = _disp(sec);
      fillShots(); draw();
    },
  };
  // 키보드: Ctrl+Z 취소 · ←/→ 또는 W/E 1초 · Shift+←/→ 10초
  document.onkeyup = ev => { if (ev.code === "Space") { _space = false; if (!pan) ov.style.cursor = "crosshair"; } };
  document.onkeydown = ev => {
    if (ev.code === "Space") { ev.preventDefault(); _space = true; if (!pan) ov.style.cursor = "grab"; return; }   // 스페이스=이동 모드(드래그로 확대이미지 이동)
    if ((ev.ctrlKey || ev.metaKey) && (ev.key === "z" || ev.key === "Z")) { ev.preventDefault(); if (LB.boxes.length) { LB.boxes.pop(); draw(); saveNow(); } return; }
    if (ev.key === "Delete" || ev.key === "Backspace") {
      ev.preventDefault();
      if (sel !== null && LB.boxes[sel]) { LB.boxes.splice(sel, 1); sel = null; draw(); saveNow(); }
      return;
    }
    if (ev.key === "ArrowLeft" || ev.key === "ArrowRight") {
      ev.preventDefault();
      openFrameAt(f.clip, f.t + (ev.key === "ArrowLeft" ? -1 : 1) * (ev.shiftKey ? 10 : _step()), LB.mode);
    }
    if (ev.key === "w" || ev.key === "W" || ev.key === "e" || ev.key === "E") {   // W=이전 · E=다음 프레임
      ev.preventDefault();
      openFrameAt(f.clip, f.t + ((ev.key === "e" || ev.key === "E") ? 1 : -1) * _step(), LB.mode);
    }
  };
}

// 재생바: 1초 · 10초 단위 이동 + 슬라이더 + 초 직접 입력 + 저장 상태
function buildFrameBar(f, status) {
  const bar = el("div", "ctrl");
  bar.style.cssText = "margin-top:8px;border:1px solid var(--line);border-radius:8px";
  const btn = (txt, d, title) => {
    const b = el("button", null, txt);
    b.title = title; b.style.width = "auto"; b.style.padding = "0 9px";
    b.onclick = () => openFrameAt(f.clip, f.t + (Math.abs(d) === 1 ? d * _step() : d));   // ±1 버튼은 모드 스텝(person 0.5)
    return b;
  };
  bar.appendChild(btn("◀◀10", -10, "10초 뒤로"));
  bar.appendChild(btn("◀", -1, "1초 뒤로"));
  const num = el("input");
  // type=number 는 브라우저가 위아래 화살표를 붙인다 → text + 숫자 키패드로 바꿔 화살표를 없앤다
  num.type = "text"; num.inputMode = "numeric"; num.value = _disp(f.t);
  num.style.cssText = "width:56px;align-self:stretch;box-sizing:border-box;background:var(--panel);color:var(--tx);border:1px solid var(--line);border-radius:6px;padding:2px 8px;font-size:15px;font-weight:400;line-height:1;font-variant-numeric:tabular-nums;text-align:center";
  num.onchange = () => openFrameAt(f.clip, _undisp(+num.value));   // 사람은 정수 프레임번호 입력 → 초로 환산
  const slWrap = el("div", "frbar");
  const tk = el("div", "tk");          // 정답 구간·라벨 눈금이 그려지는 슬라이더 트랙
  const sl = el("input");
  sl.type = "range"; sl.min = 0; sl.max = _disp(f.last); sl.step = 1; sl.value = _disp(f.t);
  sl.oninput = () => { num.value = sl.value; };          // 끄는 동안은 숫자만 따라간다
  sl.onchange = () => openFrameAt(f.clip, _undisp(+sl.value));    // 놓을 때 그 프레임을 뽑는다
  const fire = (CLIPINFO[f.clip] && CLIPINFO[f.clip].fire) || [];
  sl.title = fire.length ? `정답 화재 발생 ${fire.map(x => x.start + "s").join(", ")} · 경보 인정 ${fire[0].dur}초` : "정답 시각 없는 클립";
  slWrap.appendChild(tk); slWrap.appendChild(sl);
  bar.appendChild(slWrap);
  bar.appendChild(num);
  bar.appendChild(el("span", "now", `/ ${_disp(f.last)}`));
  bar.appendChild(btn("▶", 1, "1초 앞으로"));
  bar.appendChild(btn("10▶▶", 10, "10초 앞으로"));
  bar.appendChild(status);
  bar.sl = sl; bar.num = num; bar.tk = tk;   // 프레임만 바꿀 때 값·그림을 고쳐 쓰려고 들고 있는다
  return bar;
}

// 그 초의 박스를 서버에 쓴다. boxes 가 빈 배열이면 그 프레임 라벨을 지우는 것과 같다.
async function postLabel(clip, t, W, H, boxes, src) {
  const kind = (LB.mode === "person") ? "person" : "fire";
  const res = await (await fetch("/api/savelabel", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ clip, t, src, file: `${clip}_${String(t).padStart(4, "0")}.png`, W, H, boxes, kind }),
  })).json();
  if (kind === "person") PLABELS = res.labels || PLABELS; else LABELS = res.labels || LABELS;
  return res;
}

// 정답(GT) 표기 타임라인. 영상 검수 화면과 같은 규칙으로 그린다.
//   초록 선  = 화재 발생 시각(클립 XML StartTime)
//   초록 띠  = 경보 인정 구간(AlarmDuration)
//   흰 눈금  = 이미 라벨해 둔 초
//   파랑 선  = 지금 보고 있는 초
function drawTrack(track, f) {
  if (!track) return;
  const total = Math.max(f.last, 1), W = 1000, H = 20, px = t => t / total * W;
  const fire = (CLIPINFO[f.clip] && CLIPINFO[f.clip].fire) || [];
  let g = `<svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" style="position:absolute;inset:0;width:100%;height:100%">`;
  fire.forEach(fs => {
    const x0 = px(Math.max(0, fs.start)), x1 = px(Math.min(total, fs.start + (fs.dur || 0)));
    g += `<rect x="${x0}" y="0" width="${Math.max(x1 - x0, 1)}" height="${H}" fill="#3fb95033"/>`;
    g += `<line x1="${px(fs.start)}" y1="0" x2="${px(fs.start)}" y2="${H}" stroke="#3fb950" stroke-width="2"/>`;
  });
  shotSecs(f.stem).forEach(([sec]) => {
    g += `<line x1="${px(sec)}" y1="${H - 7}" x2="${px(sec)}" y2="${H}" stroke="#e6edf3cc" stroke-width="1.4"/>`;
  });
  track.innerHTML = g + "</svg>";
}

// 참조 샷 한 줄: 이 영상에서 라벨해 둔 초들. 눌러서 그 프레임으로 넘어간다.
function renderShotRow(row, f, hooks) {
  row.innerHTML = "";
  row.style.cssText = "display:flex;gap:8px;overflow-x:auto;padding:12px 2px;align-items:center;min-height:114px";   // 빈 상태도 높이 예약(박스 그릴 때 안 튀게)
  row.onwheel = ev => { if (ev.deltaY) { ev.preventDefault(); row.scrollLeft += ev.deltaY; } };   // 휠 상하 → 프레임줄 좌우 스크롤
  const shots = shotSecs(f.stem);
  if (!shots.length) return;
  shots.forEach(([s, n]) => {
    const on = s === f.t;
    const b = el("button");
    b.title = `${s}초 · 박스 ${n}개`;
    b.style.cssText = "position:relative;flex:0 0 auto;padding:0;line-height:0;border-radius:6px;overflow:hidden;cursor:pointer;background:var(--panel);" +
      (on ? "outline:2px solid var(--blue);border:0" : "border:1px solid var(--line)");
    const im = el("img");
    im.src = `/frameat?clip=${encodeURIComponent(f.clip)}&t=${s}&w=180`;   // 작게 줄여 받는다
    im.loading = "lazy";
    im.style.cssText = "width:160px;height:90px;object-fit:cover;display:block";
    const cap = el("span", null, `${s}s<span style="opacity:.7;font-weight:600"> ${n}</span>`);
    cap.style.cssText = "position:absolute;left:0;bottom:0;background:#0b0e13cc;color:var(--tx);font-size:10px;font-weight:700;padding:1px 5px;border-top-right-radius:5px;line-height:1.4";
    b.appendChild(im); b.appendChild(cap);
    b.onclick = () => openFrameAt(f.clip, s);
    // x = 이 참조 샷의 박스를 바로 지운다
    const x = el("span", null, "×");
    x.title = "이 초 라벨 삭제";
    x.style.cssText = "position:absolute;right:0;top:0;background:#0b0e13cc;color:var(--tx);font-size:12px;font-weight:800;line-height:1;padding:2px 5px;border-bottom-left-radius:5px;cursor:pointer";
    x.onclick = async ev => {
      ev.stopPropagation();                       // 썸네일 클릭(이동)과 겹치지 않게
      x.textContent = "…";
      const prev = existingBoxes(f.stem, s);      // 지우기 전 박스 → 되돌리기에 쓴다
      try {
        await postLabel(f.stem, s, f.W, f.H, [], f.src);
        if (hooks && hooks.onDeleted) hooks.onDeleted(s, prev);
      } catch (e) { x.textContent = "실패"; }
    };
    b.appendChild(x);
    row.appendChild(b);
  });
}

// ---------- 부트 ----------
async function buildResults() {
  const c = $("#center");
  c.innerHTML = '<div class="empty">\ubd88\ub7ec\uc624\ub294 \uc911\u2026</div>';
  let data;
  try { data = await (await fetch("/api/results")).json(); }
  catch (e) { c.innerHTML = '<div class="empty">\uacb0\uacfc\ub97c \ubabb \uc77d\uc5c8\uc2b5\ub2c8\ub2e4</div>'; return; }
  const ITEMS = ["\ubc29\ud654", "\uce68\uc785", "\ubc30\ud68c", "\uc4f0\ub7ec\uc9d0"];   // KISA 4항목 고정 순서
  const wrap = el("div"); wrap.style.cssText = "padding:18px 22px;max-width:1040px;margin:0 auto;width:100%";
  const head = el("div"); head.style.cssText = "display:flex;align-items:center;gap:10px;margin-bottom:2px";
  head.appendChild(el("div", "rtitle", `\uc2e4\ud5d8 \ucc44\uc810 \ube44\uad50 <span class="tag">${data.length}\uac74</span> <span style="color:var(--mut);font-weight:400;font-size:11px">\u00b7 KISA \uac80\uc99d\uc601\uc0c1 F1 (\ud56d\ubaa9\ubcc4)</span>`));
  const rf = el("button", null, "\u21bb \uc0c8\ub85c\uace0\uce68"); rf.style.cssText = "margin-left:auto;background:var(--panel);color:var(--tx);border:1px solid var(--line);border-radius:6px;padding:5px 12px;font-size:11px;font-weight:700;cursor:pointer"; rf.onclick = buildResults;
  head.appendChild(rf); wrap.appendChild(head);
  const col = s => s >= 90 ? "#3fb950" : s >= 70 ? "#d29922" : "#f85149";
  const HEAD = '<thead><tr style="color:var(--mut);text-align:left;font-size:11px"><th style="padding:8px 6px">\uc2e4\ud5d8</th><th>F1 \uc810\uc218</th><th>\uc815\uac80</th><th>\ubbf8\uac80</th><th>\uc624\uac80</th><th>\ucd5c\uc801 \uaddc\uce59</th><th>\uc2dc\uac01</th></tr></thead>';
  ITEMS.forEach(item => {
    const rows = data.filter(d => d.item === item).sort((a, b) => b.score - a.score);
    const sec = el("div"); sec.style.cssText = "margin-top:18px";
    const st = el("div", "rtitle", `${item} <span class="tag">${rows.length}\uac74</span>`); st.style.cssText = "font-size:14px;margin-bottom:6px";
    sec.appendChild(st);
    if (!rows.length) {
      sec.appendChild(el("div", "", '<div style="color:var(--mut);font-size:11px;padding:4px 2px">\ucc44\uc810 \uacb0\uacfc \uc5c6\uc74c (\uc2e4\ud5d8 \ub300\uae30)</div>'));
      wrap.appendChild(sec); return;
    }
    const best = Math.max.apply(null, rows.map(d => d.score));
    const tbl = el("table"); tbl.style.cssText = "width:100%;border-collapse:collapse;font-size:12px";
    tbl.innerHTML = HEAD;
    const tb = el("tbody");
    rows.forEach(d => {
      const top = d.score === best;
      const dt = new Date(d.mtime * 1000);
      const ds = `${dt.getMonth() + 1}/${dt.getDate()} ${String(dt.getHours()).padStart(2, "0")}:${String(dt.getMinutes()).padStart(2, "0")}`;
      const tr = el("tr"); tr.style.cssText = "border-top:1px solid var(--line)" + (top ? ";background:#3fb95012" : "");
      tr.innerHTML =
        `<td style="padding:9px 6px;font-weight:${top ? 800 : 600}">${top ? "\u2605 " : ""}${d.name}</td>` +
        `<td style="font-weight:800;font-size:14px;color:${col(d.score)};font-variant-numeric:tabular-nums">${d.score.toFixed(2)}</td>` +
        `<td style="color:#3fb950;font-variant-numeric:tabular-nums">${d.tp}</td>` +
        `<td style="color:#d29922;font-variant-numeric:tabular-nums">${d.fn}</td>` +
        `<td style="color:#f85149;font-variant-numeric:tabular-nums">${d.fp}</td>` +
        `<td style="color:var(--mut)">${d.rule}</td>` +
        `<td style="color:var(--mut);font-variant-numeric:tabular-nums">${ds}</td>`;
      tb.appendChild(tr);
    });
    tbl.appendChild(tb); sec.appendChild(tbl); wrap.appendChild(sec);
  });
  wrap.appendChild(el("div", "", '<div style="color:var(--mut);font-size:11px;margin-top:16px;line-height:1.7">\u00b7 \uc810\uc218 = KISA \uac80\uc99d\uc601\uc0c1 F1(\uaddc\uce59 \uc2a4\uc717 \uc911 \ucd5c\uace0). \ucd08\ub85d \u226590 \u00b7 \ub178\ub791 \u226570 \u00b7 \ube68\uac04 70\ubbf8\ub9cc<br>\u00b7 \uc2e4\ud5d8\uc774 \ub05d\ub098\uba74 \uc0c8\ub85c\uace0\uce68\uc73c\ub85c \uac31\uc2e0</div>'));
  c.innerHTML = ""; c.appendChild(wrap);
}


async function boot() {
  META = await (await fetch("/api/meta")).json();
  try { LABELS = await (await fetch("/api/labels")).json(); } catch (e) { LABELS = null; }
  try { PLABELS = await (await fetch("/api/labels?kind=person")).json(); } catch (e) { PLABELS = null; }   // person 라벨도 미리 로드(리스트 뱃지용)
  for (const [k, v] of Object.entries(META.items)) v.rows.forEach(row => row.item = k);
  buildMode(); applyMode();   // 시작 모드에 맞는 좌측/중앙 패널을 그린다(데이터 확인=데이터셋 패널)
}
boot();
