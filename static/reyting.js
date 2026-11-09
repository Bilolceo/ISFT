/* =====================================================================
   «Reyting» — talabalar o'zlashtirish ko'rsatkichlarini reyting baholash tizimi (app/reyting.py, /api/reyting).
     Umumiy:      taqsimot, o'rtacha GPA, qarzdorlar va a'lochilar ulushi (jamlangan — barcha ruxsatli lavozimlar).
     Ro'yxat:     o'rin (guruh/kurs/yo'nalish/fakultet/institut), filtrlar, qidiruv, saralash, sahifalash → talaba kartasi.
     Qaydnoma:    guruh × fanlar jadvali, .xlsx / .docx eksport (imzo qatorlari bilan).
     Dinamika:    semestrlar orasida eng ko'p ko'tarilgan / tushgan talabalar va guruhlar.
     A'lochilar:  mukofot uchun ro'yxat (kurs bo'yicha eng yaxshi N%, qarzsiz, davomat ≥), .xlsx.
     Bo'linmalar: guruhlar, kafedralar, o'qituvchilar — o'tish foizi va o'rtacha ball, kam namuna alohida.
     Metodika:    formula, teng kelganda tartib, chegaralar — academic_rules.py dan.
   Ruxsat va ko'lam serverda tekshiriladi; jamlangan lavozimlarga ism-shariflar umuman yuborilmaydi.
   Global: renderReyting() — app.js go() chaqiradi.
   app.js yordamchilaridan foydalanadi: $, esc, fmt, ico, ICONS, hydrateIcons, toast, busy, errCard, locked, showLogin, ME.
   ===================================================================== */
const RT = {meta: null, tab: "overview", sem: null, card: null, cardFrom: null,
  L: {level: "institute", faculty: "", course: "", group: "", form: "", flag: "", q: "", sort: "place", dir: "", page: 1},
  qd: {group: "", sem: null}, dyn: {level: "course"}, top: null, un: {kind: "group", small: false}};
if (!document.querySelector('link[href="reyting.css"]')) document.head.insertAdjacentHTML("beforeend", '<link rel="stylesheet" href="reyting.css">');
if (typeof ICONS === "object") {
  Object.assign(ICONS, Object.fromEntries(Object.entries({
    trophy: '<path d="M6 9H4.5a2.5 2.5 0 0 1 0-5H6"/><path d="M18 9h1.5a2.5 2.5 0 0 0 0-5H18"/><path d="M4 22h16"/><path d="M10 14.66V17c0 .55-.47.98-.97 1.21C7.85 18.75 7 20.24 7 22"/><path d="M14 14.66V17c0 .55.47.98.97 1.21C16.15 18.75 17 20.24 17 22"/><path d="M18 2H6v7a6 6 0 0 0 12 0V2Z"/>',
    download: '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><path d="m7 10 5 5 5-5"/><path d="M12 15V3"/>',
    back: '<path d="m15 18-6-6 6-6"/>',
    list: '<path d="M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01"/>',
    grid: '<rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/>',
    trend: '<path d="m22 7-8.5 8.5-5-5L2 17"/><path d="M16 7h6v6"/>',
    layers: '<path d="m12 2 10 5-10 5L2 7z"/><path d="m2 17 10 5 10-5"/><path d="m2 12 10 5 10-5"/>',
    info: '<circle cx="12" cy="12" r="10"/><path d="M12 16v-4M12 8h.01"/>',
    search: '<circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/>',
    pie: '<path d="M21.2 15.9A10 10 0 1 1 8 2.8"/><path d="M22 12A10 10 0 0 0 12 2v10z"/>',
  }).filter(([k]) => !ICONS[k])));
  try { const s = document.querySelector('#nav a[data-v="reyting"] svg'); if (s && !s.innerHTML.trim()) { s.remove(); hydrateIcons(); } } catch (e) {}
}
const RT_TABS = {overview: ["Umumiy", "pie"], list: ["Reyting ro'yxati", "list"], qaydnoma: ["Qaydnoma", "grid"], dynamics: ["Dinamika", "trend"],
  top: ["A'lochilar", "trophy"], units: ["Bo'linmalar", "layers"], method: ["Metodika", "info"]};
const rtN = n => n == null ? "—" : fmt(n);
const rtG = x => x == null ? "—" : Number(x).toFixed(2);
const rtS = x => x == null ? "—" : Number(x).toFixed(1);
const rtPlace = p => p && p.rank ? `<b class="rt-pl">${fmt(p.rank)}</b><span class="rt-of"> / ${fmt(p.n)}</span>` : "—";
const rtPct = p => p && p.pct ? `<small class="rt-pct" title="Yuqoridan ${p.pct}% ichida">yuqori ${p.pct}%</small>` : "";
const rtDelta = d => d == null ? `<span class="rt-dl muted" title="O'tgan semestr ma'lumoti yo'q">—</span>` : d > 0 ? `<span class="rt-dl up" title="${d} o'ringa ko'tarildi">▲${fmt(d)}</span>`
  : d < 0 ? `<span class="rt-dl dn" title="${-d} o'ringa tushdi">▼${fmt(-d)}</span>` : `<span class="rt-dl muted" title="O'zgarmadi">0</span>`;
const rtTags = r => (r.debtor ? `<span class="rt-tag bad" title="Kamida bitta fandan ${RT.meta?.methodology?.pass || 40} balldan past">akademik qarzdor</span>` : "")
  + (r.excellent ? `<span class="rt-tag ok" title="Barcha fanlardan «5»">a'lochi</span>` : "");
const rtSemLabel = k => (RT.meta?.semesters || []).find(s => s.key === +k)?.short || k;
async function rtApi(url, body) {
  const r = await fetch(url, {method: body === undefined ? "GET" : "POST", credentials: "same-origin", headers: {"Content-Type": "application/json"},
                              body: body === undefined ? undefined : JSON.stringify(body)});
  if (r.status === 401) { showLogin(); throw new Error("auth"); }
  const d = await r.json().catch(() => ({}));
  if (!r.ok) { const m = d.message || (typeof d.detail === "string" ? d.detail : "") || "Xatolik yuz berdi"; if (body !== undefined) { toast(m); return null; }
    const e = new Error(r.status === 403 ? "denied" : "api"); e.msg = m; throw e; }
  return d;
}
const rtQs = o => new URLSearchParams(Object.entries(o).filter(([, v]) => v !== "" && v != null)).toString();

/* ---------- asosiy ko'rinish ---------- */
async function renderReyting() {
  const el = $("#v-reyting");
  if (!el.innerHTML) el.innerHTML = `<p class="muted">Yuklanmoqda…</p>`;
  RT.meta = await rtApi("/api/reyting/meta");
  const M = RT.meta;
  if (RT.sem == null) RT.sem = M.current;
  if (!M.tabs.includes(RT.tab)) RT.tab = M.tabs[0];
  const when = M.computed_at ? `Hisoblandi: ${esc(M.computed_at.slice(8, 10) + "." + M.computed_at.slice(5, 7) + "." + M.computed_at.slice(0, 4) + " " + M.computed_at.slice(11, 16))}` : "";
  el.innerHTML = `<div class="head rt-head"><div class="rt-ttl"><h2>Reyting</h2>
        <span class="muted">${esc(M.title)}</span>
        <div class="rt-src"><span class="rt-chip">${ico("users", 14)}${esc(M.scope)}</span>${M.mode === "aggregate" ? `<span class="rt-chip warn">${ico("lock", 14)}Faqat jamlangan ko'rsatkichlar</span>` : ""}
          <span class="rt-chip muted" title="Kesh: ${rtN(M.rows)} qator, ${esc(M.seconds || "")} s">${ico("calendar", 14)}${when}</span></div></div>
      <div class="rt-hact">
        <div class="rt-seg" role="group" aria-label="Semestr">${M.semesters.map(s => `<button type="button" data-sem="${s.key}" class="${+RT.sem === s.key ? "on" : ""}" aria-pressed="${+RT.sem === s.key}" title="${esc(s.label)}">${esc(s.short)}</button>`).join("")}</div>
        ${M.can_recompute ? `<button class="btn sm" id="rtRe" title="Reytingni baholar jadvalidan qayta hisoblash">${ico("refresh", 15)}Qayta hisoblash</button>` : ""}</div></div>
    <div class="pn-tabs rt-tabs" role="tablist">${M.tabs.map(k => `<button class="pn-tab${RT.tab === k ? " on" : ""}" role="tab" aria-selected="${RT.tab === k}" data-rtt="${k}">${ico(RT_TABS[k][1], 16)}${RT_TABS[k][0]}</button>`).join("")}</div>
    <div id="rtBody"></div>`;
  el.querySelectorAll("[data-rtt]").forEach(b => b.onclick = () => { RT.tab = b.dataset.rtt; RT.card = null;
    el.querySelectorAll("[data-rtt]").forEach(x => { x.classList.toggle("on", x === b); x.setAttribute("aria-selected", x === b); }); rtTab(); });
  el.querySelectorAll("[data-sem]").forEach(b => b.onclick = () => { RT.sem = +b.dataset.sem; RT.L.page = 1;
    el.querySelectorAll("[data-sem]").forEach(x => { x.classList.toggle("on", x === b); x.setAttribute("aria-pressed", x === b); }); rtTab(); });
  if ($("#rtRe")) $("#rtRe").onclick = e => busy(e.currentTarget, async () => {
    const r = await rtApi("/api/reyting/recompute", {}); if (r) { toast(`Reyting qayta hisoblandi: ${fmt(r.rows)} qator, ${r.seconds} s`); renderReyting(); } }, "Hisoblanmoqda…");
  await rtTab();
}
async function rtTab() {
  const body = $("#rtBody");
  try {
    if (RT.card) return await rtCard(RT.card);
    await ({overview: rtOverview, list: rtList, qaydnoma: rtQaydnoma, dynamics: rtDynamics, top: rtTop, units: rtUnits, method: rtMethod}[RT.tab] || rtOverview)();
  } catch (e) { if (e?.message === "auth") return; body.innerHTML = e?.message === "denied" ? `<div class="card locked"><div class="pn-lock">${ico("lock", 22)}</div><b>Ruxsat yo'q</b><span class="tiny">${esc(e.msg || "")}</span></div>` : errCard("reyting"); }
}

/* ---------- 1) umumiy ---------- */
async function rtOverview() {
  const O = await rtApi(`/api/reyting/overview?sem=${RT.sem}`), T = O.total || {}, P = O.prev;
  const dv = (a, b, d = 2, inv = false) => a == null || b == null ? "" : (() => { const x = +(a - b).toFixed(d); if (!x) return `<span class="trend muted">0</span>`; const good = inv ? x < 0 : x > 0; return `<span class="trend ${good ? "up" : "dn"}">${x > 0 ? "+" : "−"}${Math.abs(x).toFixed(d)}</span>`; })();
  const mx = Math.max(1, ...O.bins.map(b => b.n));
  const tbl = (rows, title) => `<div class="card rt-card"><h3>${title}</h3><div class="tw rt-tw"><table class="rt-t"><thead><tr><th>Bo'lim</th><th class="n">Talaba</th><th class="n">O'rt. GPA</th><th class="n">O'rt. ball</th><th class="n">Qarzdor</th><th class="n">A'lochi</th><th class="n">Davomat</th></tr></thead><tbody>
    ${rows.map(r => `<tr><td>${esc(r.label)}</td><td class="n">${rtN(r.n)}</td><td class="n"><b>${rtG(r.gpa)}</b></td><td class="n">${rtS(r.avg_score)}</td><td class="n">${rtS(r.debt_pct)}%</td><td class="n">${rtS(r.excellent_pct)}%</td><td class="n">${r.attendance == null ? "—" : rtS(r.attendance) + "%"}</td></tr>`).join("")}</tbody></table></div></div>`;
  $("#rtBody").innerHTML = `<div class="rt-kpis">
      <div class="rt-kpi"><span>Reytingda</span><b>${rtN(T.n)}</b><small>faol talaba · ${esc(O.scope)}</small></div>
      <div class="rt-kpi"><span>O'rtacha GPA</span><b>${rtG(T.gpa)}${P ? dv(T.gpa, P.gpa) : ""}</b><small>${P ? `o'tgan semestr: ${rtG(P.gpa)}` : "5 ballik, kredit bilan tortilgan"}</small></div>
      <div class="rt-kpi${T.debt_pct > 20 ? " warn" : ""}"><span>Akademik qarzdorlar</span><b>${rtS(T.debt_pct)}%${P ? dv(T.debt_pct, P.debt_pct, 1, true) : ""}</b><small>${rtN(T.debt)} talaba · kamida bitta «F»</small></div>
      <div class="rt-kpi"><span>A'lochilar</span><b>${rtS(T.excellent_pct)}%${P ? dv(T.excellent_pct, P.excellent_pct, 1) : ""}</b><small>${rtN(T.excellent)} talaba · barcha fanlardan «5»</small></div>
      <div class="rt-kpi"><span>O'rtacha ball</span><b>${rtS(T.avg_score)}</b><small>davomat: ${T.attendance == null ? "qayd etilmagan" : rtS(T.attendance) + "%"}</small></div></div>
    <div class="grid g2 rt-g">
      <div class="card rt-card"><h3>GPA taqsimoti <span class="muted tiny">${esc(O.label)} · talabalar soni</span></h3>
        <div class="rt-hist" role="img" aria-label="GPA bo'yicha talabalar taqsimoti">${O.bins.map(b => `<div class="rt-hb" title="GPA ${b.lo.toFixed(1)}–${b.hi.toFixed(1)}: ${fmt(b.n)} talaba"><span class="rt-hv">${fmt(b.n)}</span><i style="height:${(100 * b.n / mx).toFixed(1)}%"></i><span class="rt-hl">${b.lo.toFixed(1)}–${b.hi.toFixed(1)}</span></div>`).join("")}</div></div>
      ${tbl(O.by_faculty, "Fakultetlar bo'yicha")}
      ${tbl(O.by_course, "Daraja va kurs bo'yicha")}
      ${tbl(O.by_form, "Ta'lim shakli bo'yicha")}</div>`;
}

/* ---------- 2) reyting ro'yxati ---------- */
function rtFilters() {
  const M = RT.meta, L = RT.L;
  const grp = M.groups.filter(g => (!L.faculty || g.faculty_id === +L.faculty) && (!L.course || g.course === +L.course) && (!L.form || g.form === L.form));
  return `<div class="card rt-flt">
    <div class="rt-frow">
      <label class="rt-f"><span>Daraja (o'rin)</span><select id="rtLv">${M.levels.map(l => `<option value="${l.key}"${L.level === l.key ? " selected" : ""}>${esc(l.label)}</option>`).join("")}</select></label>
      <label class="rt-f"><span>Fakultet</span><select id="rtFac"><option value="">Barchasi</option>${M.faculties.map(f => `<option value="${f.id}"${+L.faculty === f.id ? " selected" : ""}>${esc(f.name)}</option>`).join("")}</select></label>
      <label class="rt-f sm"><span>Kurs</span><select id="rtCo"><option value="">Barchasi</option>${M.courses.map(c => `<option value="${c}"${+L.course === c ? " selected" : ""}>${c}-kurs</option>`).join("")}</select></label>
      <label class="rt-f"><span>Guruh</span><select id="rtGr"><option value="">Barchasi (${grp.length})</option>${grp.map(g => `<option value="${g.id}"${+L.group === g.id ? " selected" : ""}>${esc(g.name)}</option>`).join("")}</select></label>
      <label class="rt-f sm"><span>Ta'lim shakli</span><select id="rtFo"><option value="">Barchasi</option>${M.forms.map(f => `<option value="${f.key}"${L.form === f.key ? " selected" : ""}>${esc(f.label)}</option>`).join("")}</select></label>
    </div>
    <div class="rt-frow">
      <div class="rt-chips" role="group" aria-label="Belgi">${[["", "Hammasi"], ["qarzdor", "Faqat qarzdorlar"], ["alochi", "Faqat a'lochilar"]].map(([k, l]) => `<button type="button" data-flag="${k}" class="${L.flag === k ? "on" : ""}" aria-pressed="${L.flag === k}">${l}</button>`).join("")}</div>
      <label class="rt-search">${ico("search", 16)}<input id="rtQ" type="search" placeholder="F.I.Sh., HEMIS ID yoki guruh" value="${esc(L.q)}" aria-label="Qidiruv"></label>
    </div></div>`;
}
async function rtList() {
  const L = RT.L;
  const D = await rtApi(`/api/reyting/list?${rtQs({sem: RT.sem, level: L.level, faculty: L.faculty, course: L.course, group: L.group, form: L.form, flag: L.flag, q: L.q, sort: L.sort, dir: L.dir, page: L.page, per: 50})}`);
  const S = D.summary, from = D.total ? (D.page - 1) * D.per + 1 : 0, to = Math.min(D.total, D.page * D.per);
  const th = (k, l, cls = "n", tip = "") => `<th class="${cls}"><button type="button" class="rt-sort${L.sort === k ? " on" : ""}" data-sort="${k}" title="${esc(tip || "Saralash")}">${l}${L.sort === k ? (L.dir === "asc" || (!L.dir && ["place", "name"].includes(k)) ? " ↑" : " ↓") : ""}</button></th>`;
  $("#rtBody").innerHTML = rtFilters() + `<div class="card rt-card">
    <div class="rt-lhead"><div><b>${rtN(D.total)}</b> talaba · o'rin: <b>${esc(D.level_label.toLowerCase())}</b> darajasida · o'rtacha GPA ${rtG(S.gpa)} · qarzdor ${rtN(S.debt)} · a'lochi ${rtN(S.excellent)}</div>
      <span class="muted tiny">${from}–${to}</span></div>
    <div class="tw rt-tw"><table class="rt-t rt-list"><thead><tr>
      ${th("place", "O'rin", "", "O'rin bo'yicha")}${th("name", "Talaba", "")}<th>Guruh</th>${th("gpa", "GPA")}${th("avg", "O'rt. ball")}${th("att", "Davomat")}${th("credits", "Kredit")}${th("nf", "F")}${th("delta", "O'zgarish", "n", "O'tgan semestrga nisbatan o'rin o'zgarishi")}
    </tr></thead><tbody>${D.rows.map(r => `<tr class="rt-row" data-sid="${r.id}" tabindex="0">
      <td class="rt-plc">${rtPlace(r.place)}${rtPct(r.place)}</td>
      <td class="rt-nm"><a href="#" data-sid="${r.id}">${esc(r.name)}</a><small class="muted">${esc(r.hemis_id || "")}${rtTags(r)}</small></td>
      <td><span class="nowrap">${esc(r.group)}</span><small class="muted">${r.course}-kurs · ${esc(r.form)}</small></td>
      <td class="n"><b>${rtG(r.gpa)}</b></td><td class="n">${rtS(r.avg_score)}</td><td class="n">${r.attendance == null ? `<span class="muted" title="Davomat qayd etilmaydi">—</span>` : rtS(r.attendance) + "%"}</td>
      <td class="n">${r.credits_ok}/${r.credits}</td><td class="n">${r.n_f ? `<b class="bad">${r.n_f}</b>` : "0"}</td><td class="n">${D.has_prev ? rtDelta(r.delta) : `<span class="muted">—</span>`}</td></tr>`).join("") || `<tr><td colspan="9" class="muted">Mos talaba topilmadi</td></tr>`}</tbody></table></div>
    <div class="rt-pg"><button class="btn sm" id="rtPrev"${D.page <= 1 ? " disabled" : ""}>${ico("back", 15)}Oldingi</button><span class="muted tiny">${D.page} / ${fmt(D.pages)} sahifa</span><button class="btn sm" id="rtNext"${D.page >= D.pages ? " disabled" : ""}>Keyingi</button></div></div>`;
  const set = (k, v, reset = true) => { L[k] = v; if (reset) L.page = 1; rtList().catch(rtErr); };
  $("#rtLv").onchange = e => set("level", e.target.value);
  $("#rtFac").onchange = e => { L.group = ""; set("faculty", e.target.value); };
  $("#rtCo").onchange = e => { L.group = ""; set("course", e.target.value); };
  $("#rtFo").onchange = e => { L.group = ""; set("form", e.target.value); };
  $("#rtGr").onchange = e => { if (e.target.value && L.level === "institute") L.level = "group"; set("group", e.target.value); };
  document.querySelectorAll("#rtBody [data-flag]").forEach(b => b.onclick = () => set("flag", b.dataset.flag));
  let t; $("#rtQ").oninput = e => { clearTimeout(t); t = setTimeout(() => { L.q = e.target.value.trim(); L.page = 1; rtList().then(() => { const q = $("#rtQ"); if (q) { q.focus(); q.setSelectionRange(q.value.length, q.value.length); } }).catch(rtErr); }, 350); };
  document.querySelectorAll("#rtBody [data-sort]").forEach(b => b.onclick = () => { const k = b.dataset.sort;
    if (L.sort === k) { const def = ["place", "name"].includes(k) ? "asc" : "desc"; L.dir = (L.dir || def) === "asc" ? "desc" : "asc"; } else { L.sort = k; L.dir = ""; } L.page = 1; rtList().catch(rtErr); });
  $("#rtPrev").onclick = () => set("page", L.page - 1, false);
  $("#rtNext").onclick = () => set("page", L.page + 1, false);
  rtRowClicks("list");
}
function rtErr(e) { if (e?.message === "auth") return; $("#rtBody").innerHTML = e?.message === "denied" ? locked("Reyting") : errCard("reyting"); }
function rtRowClicks(from) {
  document.querySelectorAll("#rtBody [data-sid]").forEach(x => {
    const open = ev => { ev.preventDefault(); RT.card = +x.dataset.sid; RT.cardFrom = from; rtCard(RT.card).catch(rtErr); };
    if (x.tagName === "TR") { x.onclick = ev => { if (ev.target.closest("a")) return; open(ev); }; x.onkeydown = ev => { if (ev.key === "Enter") open(ev); }; }
    else x.onclick = open;
  });
}

/* ---------- 3) talaba kartasi ---------- */
function rtSpark(trend) {
  const pts = trend.filter(t => t.gpa != null);
  if (pts.length < 2) return `<p class="muted tiny">Trend uchun kamida ikki semestr kerak.</p>`;
  const W = 340, H = 104, lo = 2, hi = 5, x = i => 56 + i * (W - 112) / (pts.length - 1), y = v => 22 + 56 * (1 - (v - lo) / (hi - lo));
  const grid = [5, 4, 3, 2].map(v => `<line x1="24" x2="${W - 4}" y1="${y(v)}" y2="${y(v)}" class="rt-sg"/><text x="0" y="${y(v) + 3.5}" class="rt-sx">${v}.0</text>`).join("");
  return `<svg class="rt-spark" viewBox="0 0 ${W} ${H}" width="${W}" height="${H}" role="img" aria-label="Semestrlar bo'yicha GPA: ${pts.map(p => `${esc(p.short)} ${p.gpa}`).join(", ")}">${grid}
    <polyline points="${pts.map((p, i) => `${x(i)},${y(p.gpa)}`).join(" ")}" class="rt-sl"/>
    ${pts.map((p, i) => `<circle cx="${x(i)}" cy="${y(p.gpa)}" r="4" class="rt-sd"/><text x="${x(i)}" y="${y(p.gpa) - 9}" text-anchor="middle" class="rt-st">${p.gpa.toFixed(2)}</text><text x="${x(i)}" y="${H - 4}" text-anchor="middle" class="rt-sx">${esc(p.short)}</text>`).join("")}</svg>`;
}
async function rtCard(sid) {
  const C = await rtApi(`/api/reyting/student/${sid}`), s = C.student;
  const sem = C.semesters.find(x => x.sem === +RT.sem) || C.semesters[0], other = C.semesters.filter(x => x !== sem);
  const back = {list: "Reyting ro'yxatiga", qaydnoma: "Qaydnomaga", dynamics: "Dinamikaga", top: "A'lochilar ro'yxatiga"}[RT.cardFrom] || "Orqaga";
  const places = sem?.places ? C.levels.map(l => { const p = sem.places[l.key]; return `<div class="rt-plt"><span>${esc(l.label)}</span><b>${fmt(p.rank)}<small> / ${fmt(p.n)}</small></b><small>yuqori ${p.pct}% ${p.delta != null ? rtDelta(p.delta) : ""}</small></div>`; }).join("") : "";
  const stbl = x => `<div class="tw rt-tw"><table class="rt-t"><thead><tr><th>Fan</th><th class="n">Ball</th><th class="n">Oraliq</th><th class="n">Yakuniy</th><th class="n">Harf</th><th class="n">Baho</th><th class="n">Kredit</th><th>O'qituvchi</th></tr></thead><tbody>
    ${x.subjects.map(g => `<tr${g.fail ? ' class="rt-fail"' : ""}><td>${esc(g.subject)}</td><td class="n"><b>${g.score}</b></td><td class="n">${g.oraliq}</td><td class="n">${g.yakuniy}</td><td class="n"><span class="rt-ltr l-${g.letter}">${g.letter}</span></td><td class="n">${g.grade} <small class="muted">${esc(g.word)}</small></td><td class="n" title="Manba: ${esc(g.credit_source)}">${g.credits}${g.credit_source === "standart" ? "*" : ""}</td><td><span class="nowrap">${esc(g.teacher || "—")}</span></td></tr>`).join("")}</tbody></table></div>
    <p class="muted tiny rt-note">GPA ${rtG(x.gpa)} · o'rtacha ball ${rtS(x.avg_score)} · kredit ${x.credits_ok}/${x.credits}${x.n_f ? ` · <b class="bad">${x.n_f} ta fan o'zlashtirilmagan</b>` : ""}. * — kredit o'quv dasturida ko'rsatilmagan, standart ${RT.meta.methodology.credit_default} kredit.</p>`;
  $("#rtBody").innerHTML = `<button class="btn ghost sm rt-back" id="rtBack">${ico("back", 15)}${back}</button>
    <div class="card rt-card rt-sc">
      <div class="rt-sh"><div><h3 class="rt-sn">${esc(s.full_name)}</h3>
        <div class="muted tiny">HEMIS ID ${esc(s.hemis_id)} · ${esc(s.grp)} · ${s.course}-kurs · ${esc(s.direction || "")} · ${esc(s.faculty || "")} · ${esc(C.form_label)}</div>
        <div class="rt-tags">${sem && sem.n_f ? `<span class="rt-tag bad">akademik qarzdor · ${sem.n_f} ta «F»</span>` : ""}${sem && sem.subjects.every(g => g.score >= RT.meta.methodology.excellent_min) ? `<span class="rt-tag ok">a'lochi</span>` : ""}${C.ranked ? "" : `<span class="rt-tag warn">reytingda ishtirok etmaydi (${esc(s.status)})</span>`}</div></div>
      </div>
      <div class="rt-kpis rt-k4">
        <div class="rt-kpi"><span>Semestr GPA</span><b>${rtG(sem?.gpa)}</b><small>${esc(sem?.short || "")}</small></div>
        <div class="rt-kpi"><span>Kumulyativ GPA</span><b>${rtG(C.cumulative.gpa)}</b><small>barcha semestrlar · kredit ${C.cumulative.credits_ok}/${C.cumulative.credits}</small></div>
        <div class="rt-kpi"><span>O'rtacha ball</span><b>${rtS(sem?.avg_score)}</b><small>100 ballik</small></div>
        <div class="rt-kpi"><span>Davomat</span><b>${sem?.attendance == null ? "—" : rtS(sem.attendance) + "%"}</b><small>${sem?.attendance == null ? "qayd etilmagan" : "joriy semestr"}</small></div></div>
      ${places ? `<h3 class="rt-h">O'rinlar <span class="muted tiny">${esc(sem.label)}</span></h3><div class="rt-plts">${places}</div>` : ""}
      <div class="rt-two"><div><h3 class="rt-h">Semestrlar bo'yicha trend</h3>${rtSpark(C.trend)}
        <div class="rt-trl">${C.trend.map(t => `<span>${esc(t.short)}: GPA <b>${rtG(t.gpa)}</b>${t.rank ? ` · institutda ${fmt(t.rank)} / ${fmt(t.n)}` : ""}</span>`).join("")}</div></div></div>
    </div>
    ${sem ? `<div class="card rt-card"><h3>Fanlar — ${esc(sem.label)}</h3>${stbl(sem)}</div>` : ""}
    ${other.map(x => `<details class="card rt-card rt-det"><summary><b>Fanlar — ${esc(x.label)}</b> <span class="muted tiny">GPA ${rtG(x.gpa)}</span></summary>${stbl(x)}</details>`).join("")}`;
  $("#rtBack").onclick = () => { RT.card = null; rtTab(); };
  window.scrollTo({top: 0});
}

/* ---------- 4) qaydnoma ---------- */
async function rtQaydnoma() {
  const M = RT.meta, Q = RT.qd;
  if (!Q.group && M.groups.length) Q.group = String(M.groups[0].id);
  const opts = M.groups.map(g => `<option value="${g.id}"${+Q.group === g.id ? " selected" : ""}>${esc(g.name)} · ${g.course}-kurs</option>`).join("");
  const exp = f => `/api/reyting/qaydnoma/${Q.group}/export?sem=${RT.sem}&fmt=${f}`;
  $("#rtBody").innerHTML = `<div class="card rt-flt"><div class="rt-frow">
      <label class="rt-f"><span>Guruh</span><select id="rtQg">${opts || `<option value="">Guruh yo'q</option>`}</select></label>
      <div class="rt-exp">${Q.group ? `<a class="btn sm" href="${exp("xlsx")}" download>${ico("download", 15)}Excel (.xlsx)</a><a class="btn sm" href="${exp("docx")}" download>${ico("download", 15)}Word (.docx)</a>` : ""}</div></div></div>
    <div id="rtQd"><p class="muted">Yuklanmoqda…</p></div>`;
  $("#rtQg").onchange = e => { Q.group = e.target.value; rtQaydnoma().catch(rtErr); };
  if (!Q.group) { $("#rtQd").innerHTML = `<div class="card"><p class="muted">Ko'lamingizda guruh yo'q.</p></div>`; return; }
  const D = await rtApi(`/api/reyting/qaydnoma/${Q.group}?sem=${RT.sem}`), g = D.group;
  $("#rtQd").innerHTML = `<div class="card rt-card"><h3>Reyting qaydnomasi — ${esc(g.name)} <span class="muted tiny">${esc(D.sem_label)} · ${esc(g.faculty || "")} · ${esc(g.direction || "")} · ${g.course}-kurs · ${esc(D.form_label)} · kafedra: ${esc(g.kafedra || "—")}</span></h3>
    <div class="tw rt-tw rt-qtw"><table class="rt-t rt-q"><thead><tr><th class="rt-stk">O'rin</th><th class="rt-stk2">Talaba</th>${D.subjects.map((x, i) => `<th class="n" title="${esc(x.subject)} · ${x.credits} kredit · ${esc(x.teacher || "")}"><span class="rt-qs">${esc(x.subject)}</span><small>${x.credits} kr.</small></th>`).join("")}<th class="n">GPA</th><th class="n">O'rt.</th><th class="n">F</th><th class="n">Kurs</th></tr></thead>
    <tbody>${D.rows.map(r => `<tr class="rt-row" data-sid="${r.id}" tabindex="0"><td class="rt-stk">${rtPlace(r.place)}</td><td class="rt-stk2"><a href="#" data-sid="${r.id}">${esc(r.name)}</a>${rtTags({debtor: r.n_f > 0, excellent: r.excellent})}</td>
      ${r.scores.map(s => `<td class="n${s != null && s < D.pass ? " rt-bad" : ""}">${s == null ? "—" : s}</td>`).join("")}<td class="n"><b>${rtG(r.gpa)}</b></td><td class="n">${rtS(r.avg_score)}</td><td class="n">${r.n_f || ""}</td><td class="n"><small>${fmt(r.place_course.rank)}/${fmt(r.place_course.n)}</small></td></tr>`).join("")}</tbody>
    <tfoot><tr><td class="rt-stk"></td><td class="rt-stk2 muted">O'rtacha / o'tish</td>${D.subjects.map(x => `<td class="n"><b>${x.avg}</b><small class="muted">${x.pass_pct}%</small></td>`).join("")}<td class="n"><b>${rtG(D.avg_gpa)}</b></td><td colspan="3"></td></tr></tfoot></table></div>
    <p class="muted tiny rt-note">${D.rows.length} talaba${D.skipped ? ` · reytingda ishtirok etmaydi: ${D.skipped} (faol emas)` : ""}. Qizil — ${D.pass} balldan past. Eksport faylida imzo qatorlari: Registrator ofisi boshlig'i va Akademik faoliyatni boshqarish bo'limi boshlig'i.</p></div>`;
  rtRowClicks("qaydnoma");
}

/* ---------- 5) dinamika ---------- */
async function rtDynamics() {
  const M = RT.meta, D = await rtApi(`/api/reyting/dynamics?level=${RT.dyn.level}&limit=15`), S = D.summary || {};
  const st = (rows, up) => rows && rows.length ? `<div class="tw rt-tw"><table class="rt-t"><thead><tr><th>Talaba</th><th>Guruh</th><th class="n">GPA</th><th class="n">O'rin</th><th class="n">O'zgarish</th></tr></thead><tbody>
    ${rows.map(r => `<tr class="rt-row" data-sid="${r.id}" tabindex="0"><td><a href="#" data-sid="${r.id}">${esc(r.name)}</a></td><td><span class="nowrap">${esc(r.grp)}</span></td><td class="n">${rtG(r.gpa_prev)} → <b>${rtG(r.gpa)}</b></td><td class="n">${fmt(r.rank_prev)} → <b>${fmt(r.rank)}</b><small class="muted"> / ${fmt(r.n)}</small></td><td class="n">${rtDelta(r.delta)}</td></tr>`).join("")}</tbody></table></div>` : `<p class="muted">Ma'lumot yo'q</p>`;
  const gt = rows => rows.length ? `<div class="tw rt-tw"><table class="rt-t"><thead><tr><th>Guruh</th><th class="n">Talaba</th><th class="n">O'rt. GPA</th><th class="n">O'zgarish</th></tr></thead><tbody>
    ${rows.map(r => `<tr><td><span class="nowrap">${esc(r.name)}</span> <small class="muted">${r.course}-kurs</small></td><td class="n">${r.n}</td><td class="n">${rtG(r.gpa_prev)} → <b>${rtG(r.gpa)}</b></td><td class="n"><span class="rt-dl ${r.delta > 0 ? "up" : r.delta < 0 ? "dn" : "muted"}">${r.delta > 0 ? "+" : r.delta < 0 ? "−" : ""}${Math.abs(r.delta).toFixed(2)}</span></td></tr>`).join("")}</tbody></table></div>` : `<p class="muted">Ma'lumot yo'q</p>`;
  $("#rtBody").innerHTML = `<div class="card rt-flt"><div class="rt-frow">
      <label class="rt-f"><span>O'rin darajasi</span><select id="rtDl">${M.levels.map(l => `<option value="${l.key}"${RT.dyn.level === l.key ? " selected" : ""}>${esc(l.label)}</option>`).join("")}</select></label>
      <div class="rt-dsum"><span>${esc(D.from)} → ${esc(D.to)}</span><span>solishtirildi: <b>${rtN(S.n)}</b></span><span class="up">▲ ko'tarildi: <b>${rtN(S.up)}</b></span><span class="dn">▼ tushdi: <b>${rtN(S.down)}</b></span><span>o'rtacha GPA: ${rtG(S.gpa_prev)} → <b>${rtG(S.gpa)}</b></span></div></div></div>
    ${D.risers ? `<div class="grid g2 rt-g"><div class="card rt-card"><h3>Eng ko'p ko'tarilganlar <span class="muted tiny">${esc(D.level_label.toLowerCase())} darajasidagi o'rin</span></h3>${st(D.risers, true)}</div>
      <div class="card rt-card"><h3>Eng ko'p tushganlar <span class="muted tiny">${esc(D.level_label.toLowerCase())} darajasidagi o'rin</span></h3>${st(D.fallers, false)}</div></div>` : ""}
    <div class="grid g2 rt-g"><div class="card rt-card"><h3>Guruhlar: o'rtacha GPA o'sgan <span class="muted tiny">kamida ${M.methodology.unit_min.group} talaba</span></h3>${gt(D.groups_up)}</div>
      <div class="card rt-card"><h3>Guruhlar: o'rtacha GPA pasaygan <span class="muted tiny">kamida ${M.methodology.unit_min.group} talaba</span></h3>${gt(D.groups_down)}</div></div>`;
  $("#rtDl").onchange = e => { RT.dyn.level = e.target.value; rtDynamics().catch(rtErr); };
  rtRowClicks("dynamics");
}

/* ---------- 6) a'lochilar (mukofot uchun) ---------- */
async function rtTop() {
  const d = RT.meta.methodology.top_defaults;
  RT.top = RT.top || {pct: d.pct, min_att: d.min_att, max_f: d.max_f};
  const P = RT.top, qs = rtQs({sem: RT.sem, pct: P.pct, min_att: P.min_att, max_f: P.max_f});
  const T = await rtApi(`/api/reyting/top?${qs}`);
  $("#rtBody").innerHTML = `<div class="card rt-flt"><form class="rt-frow" id="rtTf">
      <label class="rt-f sm"><span>Kurs bo'yicha eng yaxshi, %</span><input type="number" id="rtTp" min="1" max="50" step="1" value="${P.pct}"></label>
      <label class="rt-f sm"><span>Davomat kamida, %</span><input type="number" id="rtTa" min="0" max="100" step="1" value="${P.min_att}"></label>
      <label class="rt-f sm"><span>«F» ko'pi bilan</span><select id="rtTx">${[0, 1, 2].map(n => `<option value="${n}"${+P.max_f === n ? " selected" : ""}>${n}</option>`).join("")}</select></label>
      <div class="rt-exp"><button class="btn sm primary" type="submit">Qo'llash</button><a class="btn sm" href="/api/reyting/top/export?${qs}" download>${ico("download", 15)}Excel (.xlsx)</a></div></form>
      <p class="muted tiny rt-note">Kurs — daraja (bakalavr/magistr) va kurs bo'yicha butun institut. Ro'yxat: kurs reytingida eng yaxshi ${T.params.pct}% ichida, «F» soni ≤ ${T.params.max_f}${T.params.att_applied ? `, davomat ≥ ${T.params.min_att}% (masofaviy — davomat qayd etilmaydi, shart qo'llanmaydi)` : " — o'tgan semestr davomati saqlanmagan, davomat sharti qo'llanmadi"}. Ko'lam: ${esc(T.scope)}. Jami: <b>${fmt(T.total)}</b>.</p></div>
    ${T.courses.map(c => `<div class="card rt-card"><h3>${esc(c.level)} · ${c.course}-kurs <span class="muted tiny">kursda ${fmt(c.n)} talaba · eng yaxshi ${T.params.pct}% = ${fmt(c.quota)} o'rin · ro'yxatda ${c.rows.length}</span></h3>
      <div class="tw rt-tw"><table class="rt-t"><thead><tr><th>O'rin</th><th>Talaba</th><th>Guruh</th><th class="n">GPA</th><th class="n">O'rt. ball</th><th class="n">Davomat</th></tr></thead><tbody>
      ${c.rows.map(r => `<tr class="rt-row" data-sid="${r.id}" tabindex="0"><td class="rt-plc"><b class="rt-pl">${fmt(r.rank)}</b><span class="rt-of"> / ${fmt(r.n)}</span><small class="rt-pct">yuqori ${r.pct}%</small></td><td class="rt-nm"><a href="#" data-sid="${r.id}">${esc(r.name)}</a>${r.excellent ? `<span class="rt-tag ok">a'lochi</span>` : ""}</td><td><span class="nowrap">${esc(r.grp)}</span><small class="muted">${esc(r.faculty || "")}</small></td><td class="n"><b>${rtG(r.gpa)}</b></td><td class="n">${rtS(r.avg_score)}</td><td class="n">${r.attendance == null ? `<span class="muted">—</span>` : rtS(r.attendance) + "%"}</td></tr>`).join("")}</tbody></table></div></div>`).join("") || `<div class="card"><p class="muted">Shartlarga mos talaba topilmadi.</p></div>`}`;
  $("#rtTf").onsubmit = e => { e.preventDefault(); RT.top = {pct: +$("#rtTp").value || d.pct, min_att: +$("#rtTa").value, max_f: +$("#rtTx").value}; rtTop().catch(rtErr); };
  rtRowClicks("top");
}

/* ---------- 7) bo'linmalar ---------- */
async function rtUnits() {
  const M = RT.meta, U = RT.un;
  if (!M.units.includes(U.kind)) U.kind = M.units[0];
  const D = await rtApi(`/api/reyting/units?kind=${U.kind}&sem=${RT.sem}`);
  const lbl = {group: "Guruhlar", kafedra: "Kafedralar", teacher: "O'qituvchilar"}, rows = D.rows.filter(r => U.small || r.eligible), nsmall = D.rows.filter(r => !r.eligible).length;
  const name = r => U.kind === "group" ? `<span class="nowrap"><b>${esc(r.name)}</b></span><small class="muted">${r.course}-kurs · ${esc(r.form)} · ${esc(r.faculty || "")}</small>`
    : U.kind === "kafedra" ? `<b>${esc(r.name)}</b><small class="muted">${r.n_teachers} o'qituvchi</small>` : `<b>${esc(r.name)}</b><small class="muted">${esc(r.position || "")} · ${esc(r.kafedra || "")} · ${r.n_groups} guruh</small>`;
  $("#rtBody").innerHTML = `<div class="card rt-flt"><div class="rt-frow">
      <div class="rt-chips" role="group" aria-label="Bo'linma turi">${M.units.map(k => `<button type="button" data-unit="${k}" class="${U.kind === k ? "on" : ""}" aria-pressed="${U.kind === k}">${lbl[k]}</button>`).join("")}</div>
      <label class="rt-chk"><input type="checkbox" id="rtSm"${U.small ? " checked" : ""}> Kam namunalilarni ham ko'rsatish (${nsmall})</label></div>
    <p class="muted tiny rt-note">Tartib: o'tish foizi (≥ ${M.methodology.pass} ball), teng bo'lsa o'rtacha ball. Reytingga kamida ${D.min} ${esc(D.min_note)}li bo'linmalar kiradi — kichik guruhlar tasodifan yuqoriga chiqmasligi uchun. Ko'lam: ${esc(D.scope)}.</p></div>
    <div class="card rt-card"><div class="tw rt-tw"><table class="rt-t"><thead><tr><th>O'rin</th><th>${lbl[U.kind].replace(/lar$/, "")}</th><th class="n">Talaba</th><th class="n">Baho</th><th class="n">O'tish</th><th class="n">O'rt. ball</th></tr></thead><tbody>
    ${rows.map(r => `<tr${r.eligible ? "" : ' class="rt-small"'}><td class="rt-plc">${r.eligible ? `<b class="rt-pl">${fmt(r.rank)}</b><span class="rt-of"> / ${fmt(r.of)}</span>` : `<span class="rt-tag gray" title="Namuna kichik: reytingga kirmaydi">kam namuna</span>`}</td><td class="rt-nm">${name(r)}</td>
      <td class="n">${fmt(r.n_students)}</td><td class="n">${fmt(r.n_grades)}</td><td class="n"><b>${rtS(r.pass_pct)}%</b><div class="rt-bar"><i style="width:${r.pass_pct}%"></i></div></td><td class="n">${rtS(r.avg)}</td></tr>`).join("") || `<tr><td colspan="6" class="muted">Ma'lumot yo'q</td></tr>`}</tbody></table></div>
    ${D.total > D.rows.length ? `<p class="muted tiny rt-note">Birinchi ${D.rows.length} ta ko'rsatildi (jami ${fmt(D.total)}).</p>` : ""}</div>`;
  document.querySelectorAll("#rtBody [data-unit]").forEach(b => b.onclick = () => { U.kind = b.dataset.unit; rtUnits().catch(rtErr); });
  $("#rtSm").onchange = e => { U.small = e.target.checked; rtUnits().catch(rtErr); };
}

/* ---------- 8) metodika ---------- */
async function rtMethod() {
  const m = RT.meta.methodology, cov = m.credits_coverage;
  $("#rtBody").innerHTML = `<div class="grid g2 rt-g">
    <div class="card rt-card"><h3>Formula</h3><p class="rt-formula">${esc(m.formula)}</p>
      <p class="tiny">Har bir fanning 100 ballik bali 5 ballik bahoga o'tkaziladi va fan krediti bilan tortiladi. Semestr GPA — shu semestr fanlari bo'yicha; kumulyativ GPA — barcha semestrlar bo'yicha.</p>
      <p class="tiny"><b>Kredit manbai:</b> o'quv dasturi (O'quv dasturlari moduli) — ${cov.from_syllabus} / ${cov.subjects} fan; qolganlari uchun standart ${m.credit_default} kredit. ${esc(m.credit_note)}.</p>
      <h3 class="rt-h">Teng kelganda tartib</h3><ol class="rt-ol">${m.order.map(o => `<li>${esc(o.label)} — ${o.digits} xonagacha yaxlitlangan qiymat bo'yicha</li>`).join("")}</ol>
      <p class="tiny muted">Reytingda faqat «${esc(m.status)}» holatidagi talabalar. «F» bo'lgan talaba reytingda qoladi va «akademik qarzdor» deb belgilanadi. A'lochi — barcha fanlardan kamida ${m.excellent_min} ball («5»).</p></div>
    <div class="card rt-card"><h3>Baholash shkalasi</h3><div class="tw rt-tw"><table class="rt-t"><thead><tr><th>Ball</th><th>Harf</th><th>Baho</th><th></th></tr></thead><tbody>
      ${m.scale.map(s => `<tr><td>${s.lo}–${s.hi}</td><td><span class="rt-ltr l-${s.letter}">${s.letter}</span></td><td>«${s.grade}»</td><td>${esc(s.word)}</td></tr>`).join("")}</tbody></table></div>
      <p class="tiny muted">O'tish bali — ${m.pass}. Oraliq nazorat ${m.oraliq[0]}–${m.oraliq[1]}, yakuniy nazorat ${m.yakuniy[0]}–${m.yakuniy[1]} ball. Manba: ${esc(m.source)}.</p></div>
    <div class="card rt-card"><h3>O'rin darajalari</h3><ul class="rt-ul">${m.levels.map(l => `<li><b>${esc(l.label)}</b> — ${esc(l.note)}</li>`).join("")}</ul>
      <p class="tiny muted">O'rin «37 / 1 240» ko'rinishida; foiz — yuqoridan necha foiz ichida (1 — eng yaxshi).</p></div>
    <div class="card rt-card"><h3>Chegaralar</h3><ul class="rt-ul">
      <li>A'lochilar ro'yxati (standart): kurs bo'yicha eng yaxshi <b>${m.top_defaults.pct}%</b>, «F» ≤ <b>${m.top_defaults.max_f}</b>, davomat ≥ <b>${m.top_defaults.min_att}%</b></li>
      <li>Bo'linmalar reytingi — minimal namuna: guruh ≥ ${m.unit_min.group} talaba, kafedra ≥ ${m.unit_min.kafedra} baho, o'qituvchi ≥ ${m.unit_min.teacher} baho</li></ul>
      <h3 class="rt-h">Izohlar</h3><ul class="rt-ul">${m.notes.map(n => `<li>${esc(n)}</li>`).join("")}</ul></div></div>`;
}
