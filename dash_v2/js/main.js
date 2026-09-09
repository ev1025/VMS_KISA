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


async function boot() {
  META = await (await fetch("/api/meta")).json();
  try { LABELS = await (await fetch("/api/labels")).json(); } catch (e) { LABELS = null; }
  try { PLABELS = await (await fetch("/api/labels?kind=person")).json(); } catch (e) { PLABELS = null; }   // person 라벨도 미리 로드(리스트 뱃지용)
  for (const [k, v] of Object.entries(META.items)) v.rows.forEach(row => row.item = k);
  buildMode(); applyMode();   // 시작 모드에 맞는 좌측/중앙 패널을 그린다(데이터 확인=데이터셋 패널)
}
boot();
