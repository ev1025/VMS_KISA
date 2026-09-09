// dash_v2/js/editor.js — 손라벨 편집기(프레임 뽑기·박스·저장·의사라벨·확대·단축키). app.js 에서 분리(2026-09-09). 로드 순서: core → review → data → editor → main (dashboard.html)
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

