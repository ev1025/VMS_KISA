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
