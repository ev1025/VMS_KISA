// dash_v2/js/main.js — 모드 전환·결과 탭·boot(). app.js 에서 분리(2026-09-09). 로드 순서: core → review → data → editor → main (dashboard.html)
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
  $("#right").hidden = (CUR.mode === "results");   // 결과 탭은 우측 없이
  $(".srcbox").hidden = (CUR.mode === "results");   // 결과 탭은 소스 드롭다운 숨김
  const kindBox = $("#dsKind"); if (kindBox) kindBox.style.display = (CUR.mode === "data") ? "flex" : "none";   // 원본/학습 버튼은 데이터 확인에서만
  const emptyMsg = { data: "데이터셋과 이미지를 선택하세요", review: "영상을 선택하세요" }[CUR.mode];
  $("#center").innerHTML = '<div class="empty">' + emptyMsg + '</div>';
  $("#right").innerHTML = '<div class="empty">—</div>';
  if (CUR.mode === "data") {
    buildDatasetSrc();
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
// ---------- 부트 ----------
async function buildResults() {
  const c = $("#center");
  c.innerHTML = '<div class="empty">불러오는 중…</div>';
  let data, q = { running: [], log: [] };
  try { data = await (await fetch("/api/results")).json(); } catch (e) { c.innerHTML = '<div class="empty">결과를 못 읽었습니다</div>'; return; }
  try { q = await (await fetch("/api/queue")).json(); } catch (e) {}
  const ITEMS = ["방화", "침입", "배회", "쓰러짐"];
  const wrap = el("div"); wrap.style.cssText = "padding:18px 22px;max-width:1180px;margin:0 auto;width:100%";
  const head = el("div"); head.style.cssText = "display:flex;align-items:center;gap:10px;margin-bottom:2px";
  head.appendChild(el("div", "rtitle", `실험 채점 비교 <span class="tag">${data.length}건</span> <span style="color:var(--mut);font-weight:400;font-size:11px">· KISA 검증영상 F1 (항목별)</span>`));
  const rf = el("button", null, "↻ 새로고침"); rf.style.cssText = "margin-left:auto;background:var(--panel);color:var(--tx);border:1px solid var(--line);border-radius:6px;padding:5px 12px;font-size:11px;font-weight:700;cursor:pointer"; rf.onclick = buildResults;
  head.appendChild(rf); wrap.appendChild(head);

  // ---- 큐 상태 (exp_queue.py): 실행 중 실험 + 러너 로그 끝 ----
  const qb = el("div"); qb.style.cssText = "margin-top:10px;padding:10px 12px;border:1px solid var(--line);border-radius:8px;background:var(--panel);font-size:11px;line-height:1.7";
  const lastLog = (q.log || []).slice(-6).map(l => `<div style="color:var(--mut);font-family:ui-monospace,Menlo,monospace;white-space:pre-wrap">${l.replace(/</g, "&lt;")}</div>`).join("");
  qb.innerHTML = `<div style="font-weight:800">큐 <span style="color:${q.running.length ? "#3fb950" : "var(--mut)"}">${q.running.length ? "실행 중 " + q.running.length + "잡" : "대기/없음"}</span>` +
    (q.running.length ? ` <span style="color:var(--tx);font-weight:600">${q.running.join(" · ")}</span>` : "") + `</div>` +
    `<details><summary style="cursor:pointer;color:var(--mut)">러너 로그</summary>${lastLog || '<div style="color:var(--mut)">로그 없음</div>'}</details>`;
  wrap.appendChild(qb);

  const col = s => s >= 90 ? "#3fb950" : s >= 70 ? "#d29922" : "#f85149";
  const fmtT = m => { const d = new Date(m * 1000); return `${d.getMonth() + 1}/${d.getDate()} ${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`; };
  const shortBase = b => (b || "").replace(/^aihub71751_/, "");
  const HEAD = '<thead><tr style="color:var(--mut);text-align:left;font-size:11px"><th style="padding:8px 6px">실험</th><th>모델</th><th>베이스</th><th>추가셋</th><th>F1 최고</th><th title="구 규칙 4개만의 최고. 신규칙(fire_rule2 스윕)과 비교용">F1 구규칙</th><th>정검</th><th>미검</th><th>오검</th><th>최적 규칙</th><th>시각</th><th></th></tr></thead>';
  const VC = { "정검": "#3fb950", "미검": "#f85149", "오검": "#d29922", "무GT": "#484f58" };

  ITEMS.forEach(item => {
    const rows = data.filter(d => d.item === item).sort((a, b) => b.score - a.score);
    const sec = el("div"); sec.style.cssText = "margin-top:18px";
    const st = el("div", "rtitle", `${item} <span class="tag">${rows.length}건</span>`); st.style.cssText = "font-size:14px;margin-bottom:6px";
    sec.appendChild(st);
    if (!rows.length) { sec.appendChild(el("div", "", '<div style="color:var(--mut);font-size:11px;padding:4px 2px">채점 결과 없음 (실험 대기)</div>')); wrap.appendChild(sec); return; }
    const best = Math.max.apply(null, rows.map(d => d.score));
    const tbl = el("table"); tbl.style.cssText = "width:100%;border-collapse:collapse;font-size:12px"; tbl.innerHTML = HEAD;
    const tb = el("tbody");
    rows.forEach(d => {
      const top = d.score === best, m = d.meta || {};
      const tr = el("tr"); tr.style.cssText = "border-top:1px solid var(--line)" + (top ? ";background:#3fb95012" : "");
      const extras = (m.extras || []).map(x => x.replace(/_yolo$/, "")).join(", ") + (m.extra && Object.keys(m.extra).length ? ` <span style="color:#d29922">${Object.entries(m.extra).map(([k, v]) => k + "=" + v).join(" ")}</span>` : "");
      tr.innerHTML =
        `<td style="padding:9px 6px;font-weight:${top ? 800 : 600}">${top ? "★ " : ""}${d.name}</td>` +
        `<td style="color:var(--mut)">${m.model || ""}</td><td style="color:var(--mut)">${shortBase(m.base)}</td><td style="color:var(--mut);font-size:11px">${extras}</td>` +
        `<td style="font-weight:800;font-size:14px;color:${col(d.score)};font-variant-numeric:tabular-nums">${d.score.toFixed(2)}${d.rule && d.rule.startsWith("신규칙") ? '<span style="font-size:9px;color:var(--mut);margin-left:3px">신</span>' : ""}</td>` +
        `<td style="font-weight:700;color:${d.score_old == null ? "var(--mut)" : col(d.score_old)};font-variant-numeric:tabular-nums">${d.score_old == null ? "–" : d.score_old.toFixed(2)}</td>` +
        `<td style="color:#3fb950;font-variant-numeric:tabular-nums">${d.tp}</td><td style="color:#d29922;font-variant-numeric:tabular-nums">${d.fn}</td><td style="color:#f85149;font-variant-numeric:tabular-nums">${d.fp}</td>` +
        `<td style="color:var(--mut)">${d.rule}</td><td style="color:var(--mut);font-variant-numeric:tabular-nums">${fmtT(d.mtime)}</td>` +
        `<td style="color:var(--mut);cursor:pointer;user-select:none" title="규칙 스윕 전체">▸</td>`;
      tb.appendChild(tr);
      const sub = el("tr"); sub.hidden = true;   // 규칙 스윕 전체(펼치기)
      sub.innerHTML = `<td colspan="12" style="padding:4px 14px 10px;font-size:11px;color:var(--mut)">` +
        (d.rules || []).map(r => `<div><span style="display:inline-block;min-width:170px">${r.rule}</span> → <b style="color:${col(r.score)}">${r.score.toFixed(2)}</b> (정검 ${r.tp} 미검 ${r.fn} 오검 ${r.fp})</div>`).join("") + `</td>`;
      tb.appendChild(sub);
      tr.lastElementChild.onclick = () => { sub.hidden = !sub.hidden; tr.lastElementChild.textContent = sub.hidden ? "▸" : "▾"; };
    });
    tbl.appendChild(tb); sec.appendChild(tbl);

    // ---- 클립 × 실험 히트맵: 어떤 클립을 늘 놓치는지 (score_kisa 클립별 판정이 있는 실험만) ----
    const withClips = rows.filter(d => d.clips && Object.keys(d.clips).length);
    if (withClips.length) {
      const clips = [...new Set(withClips.flatMap(d => Object.keys(d.clips)))].sort();
      const hm = el("table"); hm.style.cssText = "border-collapse:collapse;font-size:11px;margin-top:10px";
      hm.innerHTML = `<thead><tr style="color:var(--mut)"><th style="text-align:left;padding:4px 6px">클립별 판정(최고 규칙)</th>${clips.map(cn => `<th style="padding:4px 5px;font-weight:600;writing-mode:vertical-rl;transform:rotate(180deg);white-space:nowrap">${cn.replace(/^C00_/, "")}</th>`).join("")}<th style="padding:4px 6px;color:var(--mut)">미검</th></tr></thead>`;
      const hb = el("tbody");
      withClips.forEach(d => {
        const tr = el("tr"); tr.style.cssText = "border-top:1px solid var(--line)";
        let miss = 0;
        tr.innerHTML = `<td style="padding:4px 6px;font-weight:600;white-space:nowrap">${d.name.replace(/_\d{8}$/, "")}</td>` + clips.map(cn => {
          const v = d.clips[cn] || ""; const k = v.startsWith("정검") ? "정검" : v.startsWith("미검") ? "미검" : v.startsWith("오검") ? "오검" : v ? "무GT" : "";
          if (k === "미검") miss++;
          return `<td title="${cn}: ${v || "없음"}" style="width:22px;height:20px;text-align:center;background:${k ? VC[k] + (k === "무GT" ? "" : "cc") : "transparent"};color:#06090f;font-weight:800;font-size:10px">${k === "정검" ? "○" : k === "미검" ? "✕" : k === "오검" ? "!" : k ? "·" : ""}</td>`;
        }).join("") + `<td style="padding:4px 6px;color:#f85149;font-weight:800">${miss}</td>`;
        hb.appendChild(tr);
      });
      hm.appendChild(hb);
      const hw = el("div"); hw.style.cssText = "overflow-x:auto"; hw.appendChild(hm); sec.appendChild(hw);
      sec.appendChild(el("div", "", '<div style="color:var(--mut);font-size:10px;margin-top:4px">○ 정검 · ✕ 미검 · ! 오검(GT 없는 클립) · 열 전체가 ✕인 클립 = 데이터/규칙으로 풀어야 할 병목</div>'));
    }
    wrap.appendChild(sec);
  });
  wrap.appendChild(el("div", "", '<div style="color:var(--mut);font-size:11px;margin-top:16px;line-height:1.7">· 점수 = KISA 검증영상 F1(규칙 스윕 중 최고). 초록 ≥90 · 노랑 ≥70 · 빨강 70미만 · ▸ 누르면 규칙 4개 전부<br>· 클립별 판정은 새 러너(exp_queue.py)로 채점된 실험부터 표시</div>'));
  c.innerHTML = ""; c.appendChild(wrap);
}


// 전파 작업 전역 표시(헤더). 서버 큐를 2초마다 조회
let _JOBS_T = null;
async function pollJobs() {
  const box = $("#jobStat"); if (!box) return;
  let jobs = [];
  try { jobs = await (await fetch("/api/sam2_jobs")).json(); } catch (e) { jobs = []; }
  const run = jobs.filter(j => j.state === "running"), q = jobs.filter(j => j.state === "queued");
  try {                                                // 지금 열린 편집기 클립에 작업이 있으면 편집기도 진행률을 보이게(다른 곳에서 시작된 작업 포함)
    if (typeof ED !== "undefined" && ED && ED.watch && [...run, ...q].some(j => j.clip === ED.clip.split("/").pop())) ED.watch();
  } catch (e) {}
  if (!run.length && !q.length) { box.hidden = true; box.innerHTML = ""; return; }
  const spin = '<span style="display:inline-block;width:11px;height:11px;border:2px solid #58a6ff55;border-top-color:#58a6ff;border-radius:50%;animation:ed_sp .8s linear infinite"></span>';
  if (!document.getElementById("ed_sp")) { const st = document.createElement("style"); st.id = "ed_sp"; st.textContent = "@keyframes ed_sp{to{transform:rotate(360deg)}}"; document.head.appendChild(st); }
  const parts = run.map(j => `<b>${j.clip}</b> ${j.total ? Math.min(99, Math.round(j.done / j.total * 100)) : 0}%`);
  if (q.length) parts.push(`<span style="color:var(--mut)">대기 ${q.length}</span>`);
  box.innerHTML = spin + `<span>전파 ${parts.join(" · ")}</span>`;
  box.hidden = false;
  box.onclick = () => {                              // 진행 중 클립으로 이동(원본 데이터 목록에 있을 때)
    const j = run[0] || q[0]; if (!j) return;
    const it = [...document.querySelectorAll("#list .item")].find(e => (e.dataset.rel || "").split("/").pop().replace(/\.mp4$/, "") === j.clip);
    if (it) it.click();
  };
}
function startJobPoll() { if (_JOBS_T) return; pollJobs(); _JOBS_T = setInterval(pollJobs, 2000); }
async function boot() {
  startJobPoll();
  META = await (await fetch("/api/meta")).json();
  try { LABELS = await (await fetch("/api/labels")).json(); } catch (e) { LABELS = null; }
  try { PLABELS = await (await fetch("/api/labels?kind=person")).json(); } catch (e) { PLABELS = null; }
  try { IMGLABELS = await (await fetch("/api/labels?kind=image")).json(); } catch (e) { IMGLABELS = []; }
  try { SAMFR = await (await fetch("/api/sam2frames")).json(); } catch (e) { SAMFR = {}; }   // SAM 전파 프레임(목록 배지 합산용)
  try { DATASETS = await (await fetch("/api/datasets")).json(); } catch (e) { DATASETS = {}; }   // 데이터 규격(카테고리별 mode·gt·use)
  for (const [k, v] of Object.entries(META.items)) v.rows.forEach(row => row.item = k);
  const last = (typeof loadSession === "function") ? loadSession() : {};
  if (last.mode === "data" || last.mode === "review" || last.mode === "results") CUR.mode = last.mode;
  DS_KIND = "raw";                                  // 학습 데이터 탭은 없다
  if (last.dsSel && String(last.dsSel).startsWith("raw:")) DS_SEL = last.dsSel;
  buildMode(); applyMode();   // 시작 모드에 맞는 좌측/중앙 패널을 그린다(데이터 확인=데이터셋 패널)
  restoreLast(last);
}

// 새로고침 전에 보던 영상·프레임으로 되돌린다. 목록이 그려질 때까지만 기다리고, 없으면 조용히 포기.
async function restoreLast(last) {
  if (!last || CUR.mode !== "data") return;
  if (last.img && !last.rel) {                          // 이미지 편집 중이었으면 그 이미지로
    for (let i = 0; i < 40; i++) { await new Promise(r => setTimeout(r, 150)); if (document.querySelector("#list .item")) break; }
    try { openImage(last.img); } catch (e) {}
    return;
  }
  if (!last.rel) return;
  for (let i = 0; i < 40; i++) {
    await new Promise(r => setTimeout(r, 150));
    if (document.querySelector("#list .item")) break;
  }
  try {
    DS_EDIT = true;
    await showRawVideo(last.rel);                         // 편집기 열기(시작 프레임까지 열고 돌아온다)
    const mode = last.lmode || catMode(last.rel);        // 모드는 저장값, 없으면 카테고리로(방화 클립이 사람 모드로 열리지 않게)
    if (last.sec != null && LB.clip && mode !== "none") await openFrameAt(LB.clip, last.sec, mode);
  } catch (e) {}
}
boot();
