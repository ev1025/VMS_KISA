// dash_v2/js/data.js — 데이터 확인 탭(원본/학습 데이터 브라우징·이미지·영상). app.js 에서 분리(2026-09-09). 로드 순서: core → review → data → editor → main (dashboard.html)
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
  const cb = el("button", null, "\u21bb"); cb.title = "서버 폴더 캐시 새로고침(데이터 폴더를 옮기거나 이름 바꾼 뒤)";
  cb.style.cssText = "flex:0 0 30px;border-radius:6px;padding:5px 0;cursor:pointer;font-size:12px;background:var(--panel);color:var(--mut);border:1px solid var(--line)";
  cb.onclick = async () => { cb.textContent = "\u2026"; try { await fetch("/api/refresh_cache", { method: "POST" }); } catch (e) {} SOURCES = null; DSMETA = null; buildDatasetSrc(); };
  kb.appendChild(cb);
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
  // 요약 패널: 총수·표본 라벨률·클래스 분포·규약 경고 (/api/clipstat 는 목록 표본만 읽어 빠르다)
  const sum = el("div"); sum.style.cssText = "margin:0 0 6px;padding:8px 10px;border:1px solid var(--line);border-radius:8px;background:var(--panel);font-size:11px;line-height:1.6;color:var(--mut)";
  sum.innerHTML = `이미지 <b style="color:var(--tx)">${r.img_total.toLocaleString()}</b> · 영상 <b style="color:var(--tx)">${r.vid_total}</b>${shownImg}`;
  box.appendChild(sum);
  fetch("/api/clipstat?src=" + encodeURIComponent(cat)).then(x => x.json()).then(st => {
    const cls = Object.entries(st.classes || {}).sort().map(([k, v]) => `${k}:${v}`).join(" ");
    sum.innerHTML += `<br>표본 ${st.sample}장 중 라벨 <b style="color:var(--tx)">${st.labeled}</b> · 박스 ${st.boxes}` + (cls ? ` · 클래스 <span style="font-family:ui-monospace,Menlo,monospace">${cls}</span>` : "") +
      (st.note ? `<br><span style="color:#d29922;font-weight:700">⚠ ${st.note}</span>` : "");
  }).catch(() => {});
  // 검색 필터(파일명 부분일치, 클라이언트)
  const fi = el("input"); fi.type = "search"; fi.placeholder = "파일명 검색…";
  fi.style.cssText = "width:100%;box-sizing:border-box;margin:0 0 6px;padding:5px 8px;border-radius:6px;background:var(--panel);color:var(--tx);border:1px solid var(--line);font-size:11px";
  fi.oninput = () => { const k = fi.value.trim().toLowerCase(); box.querySelectorAll(".item").forEach(it => { const nm = it.querySelector(".nm"); it.hidden = !!k && !((nm && (nm.title || nm.textContent) || "").toLowerCase().includes(k)); }); };
  box.appendChild(fi);
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

