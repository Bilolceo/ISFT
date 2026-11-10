/* =====================================================================
   «Ilmiy faoliyat» — Ilmiy bo'lim va Magistratura ish jarayoni (app/ilmiy.py, /api/ilmiy).
     Umumiy:        kafedralar kesimida nashrlar va reja bajarilishi, grantlar voronkasi, dissertatsiya bosqichlari.
     Nashrlar:      ariza → kafedra tekshiruvi → Ilmiy bo'lim tasdig'i → reyestr; qaytarilgani tuzatiladi.
     Grantlar:      loyiha → prorektor imzosi → yuborildi → yutildi (hisobotlar) / rad → yakunlandi.
     Dissertatsiya: mavzu va ilmiy rahbar → 1-bob → 2-bob → seminar → dastlabki himoya → himoya; muddatlar va ogohlantirishlar.
   Ruxsat va ko'lam serverda. Global: renderIlmiy() — app.js go() chaqiradi.
   ===================================================================== */
const IL = {meta: null, tab: null, pubView: "navbat", pubQ: "", reg: {page: 1, q: "", kind: "", year: ""}, gSt: "faol", gQ: "",
  d: {course: "", flag: "", q: "", page: 1}};
if (!document.querySelector('link[href="ilmiy.css"]')) document.head.insertAdjacentHTML("beforeend", '<link rel="stylesheet" href="ilmiy.css">');
if (typeof ICONS === "object" && !ICONS.flask) {
  ICONS.flask = '<path d="M9 3h6M10 3v6L4.5 18.5A2 2 0 0 0 6.2 21h11.6a2 2 0 0 0 1.7-2.5L14 9V3"/><path d="M7 15h10"/>';
  try { const s = document.querySelector('#nav a[data-v="ilmiy"] svg'); if (s && !s.innerHTML.trim()) { s.remove(); hydrateIcons(); } } catch (e) {}
}
const IL_TABS = {umumiy: ["Umumiy", "chart"], nashrlar: ["Nashrlar", "book"], grantlar: ["Grantlar va loyihalar", "money"], dissertatsiya: ["Dissertatsiyalar", "cap"]};
const ilSum = n => n == null ? "—" : (n >= 1e9 ? (n / 1e9).toFixed(2) + " mlrd" : (n / 1e6).toFixed(1) + " mln") + " so'm";
const ilD = d => d ? dmy(String(d).slice(0, 10)) : "—";
const ilCls = st => ({tasdiqlangan: "ok", "o'tdi": "ok", "qabul qilindi": "ok", bajarilmoqda: "ok", yakunlangan: "ok", qaytarildi: "bad", "rad etilgan": "bad",
  qayta: "bad", kafedra: "warn", ilmiy: "warn", imzoda: "warn", topshirildi: "info", "ariza berilgan": "info", imzolandi: "info"})[st] || "";
async function ilApi(url, body) {
  const r = await fetch(url, {method: body === undefined ? "GET" : "POST", credentials: "same-origin", headers: {"Content-Type": "application/json"},
                              body: body === undefined ? undefined : JSON.stringify(body)});
  if (r.status === 401) { showLogin(); throw new Error("auth"); }
  const d = await r.json().catch(() => ({}));
  if (!r.ok) { const m = d.message || (typeof d.detail === "string" ? d.detail : "") || "Xatolik yuz berdi"; if (body !== undefined) { toast(m); return null; }
    const e = new Error(r.status === 403 ? "denied" : "api"); e.msg = m; throw e; }
  return d;
}
const ilQs = o => new URLSearchParams(Object.entries(o).filter(([, v]) => v !== "" && v != null)).toString();
function ilModal(title, html, onOk, okText = "Saqlash") {
  const bg = document.createElement("div"); bg.className = "il-modal-bg";
  bg.innerHTML = `<div class="il-modal" role="dialog" aria-modal="true" aria-label="${esc(title)}"><div class="il-mh"><h3>${esc(title)}</h3>
    <button type="button" class="icon-btn" data-x aria-label="Yopish">✕</button></div><div class="il-mb">${html}</div>
    <div class="il-acts"><button type="button" class="btn ghost" data-x>${onOk ? "Bekor qilish" : "Yopish"}</button>${onOk ? `<button type="button" class="btn primary" data-ok>${esc(okText)}</button>` : ""}</div></div>`;
  document.body.appendChild(bg);
  const close = () => bg.remove(); bg.close = close;
  bg.addEventListener("click", e => { if (e.target === bg || e.target.closest("[data-x]")) close(); });
  bg.addEventListener("keydown", e => { if (e.key === "Escape") close(); });
  const ok = bg.querySelector("[data-ok]");
  if (ok) ok.onclick = async () => { ok.disabled = true; try { if (await onOk(bg)) close(); } finally { ok.disabled = false; } };
  setTimeout(() => bg.querySelector("input,select,textarea,button")?.focus(), 30);
  return bg;
}
function ilPicker(root, inp, list, onPick) {
  const I = root.querySelector(inp), L = root.querySelector(list); let t = null;
  I.addEventListener("input", () => { clearTimeout(t); t = setTimeout(async () => {
    const q = I.value.trim(); if (q.length < 2) { L.innerHTML = ""; return; }
    const rs = await ilApi("/api/ilmiy/teachers?" + ilQs({q})).catch(() => []);
    L.innerHTML = rs.map((r, i) => `<button type="button" data-i="${i}">${esc(r.full_name)} <small>${esc(r.degree || "—")} · ${esc(r.kafedra || "")} · rahbarlikda ${r.load}</small></button>`).join("") || `<small class="muted">Topilmadi</small>`;
    L.querySelectorAll("button").forEach(b => b.onclick = () => { L.querySelectorAll("button").forEach(x => x.classList.remove("on")); b.classList.add("on"); onPick(rs[+b.dataset.i]); });
  }, 250); });
}
const ilLog = log => log?.length ? `<details class="il-log"><summary>Tarix (${log.length})</summary><ul>${log.map(l => `<li><b>${esc(l.action)}</b>${l.note ? ` — ${esc(l.note)}` : ""}<small>${ilD(l.at)} ${esc((l.at || "").slice(11, 16))} · ${esc(l.user_name || "")}</small></li>`).join("")}</ul></details>` : "";

/* ---------- asosiy ko'rinish ---------- */
async function renderIlmiy() {
  const el = $("#v-ilmiy");
  if (!el.innerHTML) el.innerHTML = `<p class="muted">Yuklanmoqda…</p>`;
  try { IL.meta = await ilApi("/api/ilmiy/meta"); } catch (e) { el.innerHTML = e.message === "denied" ? `<div class="card locked">${esc(e.msg)}</div>` : errCard("ilmiy"); return; }
  const M = IL.meta;
  if (!M.tabs.includes(IL.tab)) IL.tab = M.tabs[0];
  el.innerHTML = `<div class="il-head"><div><h2>Ilmiy faoliyat</h2><span class="muted">${esc(M.note)}</span></div></div>
    ${M.alerts.length ? `<div class="il-alerts">${M.alerts.map((a, i) => `<button type="button" class="il-al ${a.kind}" data-al="${i}">${ico("alert", 15)}${esc(a.text)}</button>`).join("")}</div>` : ""}
    <div class="pn-tabs il-tabs" role="tablist">${M.tabs.map(k => `<button class="pn-tab${IL.tab === k ? " on" : ""}" role="tab" aria-selected="${IL.tab === k}" data-ilt="${k}">${ico(IL_TABS[k][1], 16)}${IL_TABS[k][0]}</button>`).join("")}</div>
    <div id="ilBody"></div>`;
  const setTab = k => { IL.tab = k; el.querySelectorAll("[data-ilt]").forEach(x => { x.classList.toggle("on", x.dataset.ilt === k); x.setAttribute("aria-selected", x.dataset.ilt === k); }); ilTab(); };
  el.querySelectorAll("[data-ilt]").forEach(b => b.onclick = () => setTab(b.dataset.ilt));
  IL.setTab = setTab;
  ilBindAlerts(el);
  ilTab();
}
async function ilTab() {
  const box = $("#ilBody"); if (!box) return;
  box.innerHTML = `<p class="muted">Yuklanmoqda…</p>`;
  try { await ({umumiy: ilOverview, nashrlar: ilPubs, grantlar: ilGrants, dissertatsiya: ilDiss})[IL.tab](box); }
  catch (e) { if (e.message === "denied") box.innerHTML = `<div class="card locked">${esc(e.msg)}</div>`; else if (e.message !== "auth") box.innerHTML = errCard("ilmiy"); }
}

/* ---------- Umumiy ---------- */
async function ilOverview(box) {
  const o = await ilApi("/api/ilmiy/overview"), M = IL.meta;
  let h = "";
  if (o.depts) {
    const T = k => o.depts.reduce((a, d) => a + (d[k] || 0), 0);
    const g = o.grants || {}, gn = k => g[k]?.n || 0;
    const won = (g.bajarilmoqda?.won || 0) + (g.yakunlangan?.won || 0);
    const pp = o.pubs_pending || {};
    h += `<div class="il-kpis">
      <div class="il-kpi"><span>Scopus / WoS, ${o.year}</span><b>${fmt(T("indexed"))}</b><small>reja: ${fmt(T("plan_scopus"))}</small></div>
      <div class="il-kpi"><span>OAK jurnallari, ${o.year}</span><b>${fmt(T("oak"))}</b><small>reja: ${fmt(T("plan_oak"))}</small></div>
      <div class="il-kpi ${(pp.kafedra || 0) + (pp.ilmiy || 0) ? "warn" : ""}"><span>Tekshiruvdagi arizalar</span><b>${fmt((pp.kafedra || 0) + (pp.ilmiy || 0))}</b><small>kafedrada ${pp.kafedra || 0} · Ilmiy bo'limda ${pp.ilmiy || 0}</small></div>
      <div class="il-kpi"><span>Faol grantlar</span><b>${fmt(gn("bajarilmoqda"))}</b><small>${ilSum(won)} yutilgan</small></div>
      <div class="il-kpi"><span>Arizalar bosqichida</span><b>${fmt(gn("loyiha") + gn("imzoda") + gn("imzolandi") + gn("ariza berilgan"))}</b><small>imzoda ${gn("imzoda")} · yuborilgan ${gn("ariza berilgan")}</small></div>
      <div class="il-kpi ${o.reports_overdue ? "bad" : "ok"}"><span>Muddati o'tgan grant hisobotlari</span><b>${fmt(o.reports_overdue)}</b><small>bajarilayotgan loyihalar bo'yicha</small></div></div>
    <div class="card il-card"><div class="il-ch"><div><h3>Kafedralar kesimida — ${o.year}</h3><p class="muted">Tasdiqlangan nashrlar (reyestr). Reja — Ilmiy bo'lim belgilaydi; «nashrsiz» — ${o.year - 1}–${o.year} yillarda birorta nashri yo'q o'qituvchilar.</p></div></div>
      <div class="tbl-wrap"><table class="il-t"><thead><tr><th>Kafedra</th><th class="num">O'qituvchi</th><th class="num">Ilmiy daraja</th><th class="num">Scopus/WoS</th><th class="num">OAK</th><th class="num">Jami</th><th class="num">1 o'qituvchiga</th><th class="num">Nashrsiz</th><th class="num">Tekshiruvda</th>${M.can.plan ? "<th></th>" : ""}</tr></thead>
      <tbody>${o.depts.map(d => `<tr><td><b>${esc(d.kafedra)}</b></td><td class="num">${d.teachers}</td><td class="num">${d.degree_pct}%</td>
        <td class="num">${d.indexed}${d.plan_scopus ? ` <small class="${d.plan_scopus_pct >= 100 ? "ok" : d.plan_scopus_pct < 50 ? "bad" : ""}">/ ${d.plan_scopus} · ${d.plan_scopus_pct}%</small>` : ""}</td>
        <td class="num">${d.oak}${d.plan_oak ? ` <small class="${d.plan_oak_pct >= 100 ? "ok" : d.plan_oak_pct < 50 ? "bad" : ""}">/ ${d.plan_oak} · ${d.plan_oak_pct}%</small>` : ""}</td>
        <td class="num">${d.total}</td><td class="num">${d.per_teacher}</td><td class="num ${d.zero_teachers ? "warn" : ""}">${d.zero_teachers}</td><td class="num">${d.pending}</td>
        ${M.can.plan ? `<td><button class="btn sm ghost" data-plan="${d.dept_id}">Reja</button></td>` : ""}</tr>`).join("")}</tbody></table></div></div>`;
  }
  if (o.diss) {
    const D = o.diss;
    h += `<div class="card il-card"><h3>Magistrlik dissertatsiyalari</h3><p class="muted">Bosqichdan o'tganlar soni (kurs bo'yicha). Muddat — qabul yilidan hisoblanadi.</p>
      <div class="tbl-wrap"><table class="il-t"><thead><tr><th>Kurs</th><th class="num">Magistrant</th>${D.stages.map(s => `<th class="num">${esc(s.name)}</th>`).join("")}<th class="num">Muddati o'tgan</th></tr></thead>
      <tbody>${D.by_course.map(c => `<tr><td><b>${c.course}-kurs</b></td><td class="num">${c.n}</td>${D.stages.map(s => `<td class="num">${c.passed[s.key]}${c.n ? ` <small>${Math.round(100 * c.passed[s.key] / c.n)}%</small>` : ""}</td>`).join("")}
        <td class="num ${c.overdue ? "bad" : ""}">${c.overdue}</td></tr>`).join("")}</tbody></table></div>
      ${Object.keys(D.overdue_by_stage).length ? `<p class="il-note">${ico("alert", 14)} Muddati o'tgan bosqichlar: ${D.stages.filter(s => D.overdue_by_stage[s.key]).map(s => `${esc(s.name)} — <b>${D.overdue_by_stage[s.key]}</b>`).join(" · ")}</p>` : ""}
      ${D.supervisors.length ? `<p class="muted il-sup">Eng ko'p rahbarlik qilayotganlar (chegara ${D.sup_max}): ${D.supervisors.map(s => `${esc(s.full_name)} (${esc(s.degree || "—")}) — ${s.n}`).join(" · ")}</p>` : ""}</div>`;
  }
  box.innerHTML = h || `<p class="muted">Ma'lumot yo'q</p>`;
  box.querySelectorAll("[data-plan]").forEach(b => b.onclick = () => {
    const d = o.depts.find(x => x.dept_id === +b.dataset.plan);
    ilModal(`Ilmiy reja — ${d.kafedra}`, `<div class="row2"><label>Yil<select id="p0"><option>${o.year}</option><option>${o.year + 1}</option></select></label><span></span>
      <label>Scopus / WoS maqolalari<input id="p1" type="number" min="0" value="${d.plan_scopus ?? ""}"></label><label>OAK jurnallari<input id="p2" type="number" min="0" value="${d.plan_oak ?? ""}"></label></div>
      <p class="muted">Kafedrada ${d.teachers} o'qituvchi, ${d.degree_pct}% ilmiy darajali.</p>`, async m => {
      const r = await ilApi("/api/ilmiy/plans", {dept_id: d.dept_id, year: +m.querySelector("#p0").value, scopus: +m.querySelector("#p1").value || 0, oak: +m.querySelector("#p2").value || 0});
      if (r) { toast("Reja saqlandi"); ilTab(); } return !!r; });
  });
}

/* ---------- Nashrlar ---------- */
async function ilPubs(box) {
  const M = IL.meta, reviewer = ["kafedra", "ilmiy"].includes(M.mode);
  const views = [...(reviewer ? [["navbat", "Mening navbatim"]] : []), ["", "Barcha arizalar"], ["qaytarildi", "Qaytarilgan"], ["reestr", "Reyestr"]];
  if (!views.some(v => v[0] === IL.pubView)) IL.pubView = views[0][0];
  box.innerHTML = `<div class="il-bar"><div class="il-seg" role="group">${views.map(([k, l]) => `<button type="button" data-pv="${k}" class="${IL.pubView === k ? "on" : ""}">${l}</button>`).join("")}</div>
    <input type="search" id="ilPq" placeholder="Sarlavha, muallif yoki jurnal" value="${esc(IL.pubView === "reestr" ? IL.reg.q : IL.pubQ)}">
    ${M.can.pub_create ? `<button class="btn primary sm" id="ilPn">${ico("pen", 15)}Yangi nashr</button>` : ""}</div><div id="ilPl"></div>`;
  box.querySelectorAll("[data-pv]").forEach(b => b.onclick = () => { IL.pubView = b.dataset.pv; ilPubs(box); });
  let t; $("#ilPq").oninput = e => { clearTimeout(t); t = setTimeout(() => { if (IL.pubView === "reestr") { IL.reg.q = e.target.value; IL.reg.page = 1; } else IL.pubQ = e.target.value; ilPubList(); }, 300); };
  if ($("#ilPn")) $("#ilPn").onclick = () => ilPubForm();
  ilPubList();
}
async function ilPubList() {
  const L = $("#ilPl"); if (!L) return;
  if (IL.pubView === "reestr") {
    const d = await ilApi("/api/ilmiy/registry?" + ilQs(IL.reg));
    L.innerHTML = `<div class="il-bar"><select id="ilRk"><option value="">Barcha turlar</option>${IL.meta.kinds.map(k => `<option ${IL.reg.kind === k ? "selected" : ""}>${esc(k)}</option>`).join("")}</select>
      <select id="ilRy"><option value="">Barcha yillar</option>${[0, 1, 2, 3].map(i => IL.meta.year - i).map(y => `<option ${+IL.reg.year === y ? "selected" : ""}>${y}</option>`).join("")}</select>
      <span class="muted">${fmt(d.total)} ta nashr</span></div>
      <div class="tbl-wrap"><table class="il-t"><thead><tr><th>Nashr</th><th>Muallif</th><th>Turi</th><th class="num">Yil</th><th class="num">Iqtibos</th></tr></thead><tbody>
      ${d.rows.map(r => `<tr><td><b>${esc(r.title)}</b><small>${esc(r.journal || "")}${r.doi ? ` · DOI ${esc(r.doi)}` : ""}</small></td><td>${esc(r.author)}<small>${esc(r.kafedra || "")}</small></td>
        <td>${esc(r.kind)}${r.quartile ? ` <span class="il-chip info">${r.quartile}</span>` : ""}</td><td class="num">${r.year}</td><td class="num">${r.citations ?? 0}</td></tr>`).join("") || `<tr><td colspan="5" class="muted">Topilmadi</td></tr>`}</tbody></table></div>
      ${d.pages > 1 ? `<div class="il-pg"><button class="btn sm ghost" id="ilR1" ${d.page <= 1 ? "disabled" : ""}>‹ Oldingi</button><span>${d.page} / ${d.pages}</span><button class="btn sm ghost" id="ilR2" ${d.page >= d.pages ? "disabled" : ""}>Keyingi ›</button></div>` : ""}`;
    $("#ilRk").onchange = e => { IL.reg.kind = e.target.value; IL.reg.page = 1; ilPubList(); };
    $("#ilRy").onchange = e => { IL.reg.year = e.target.value; IL.reg.page = 1; ilPubList(); };
    if ($("#ilR1")) { $("#ilR1").onclick = () => { IL.reg.page--; ilPubList(); }; $("#ilR2").onclick = () => { IL.reg.page++; ilPubList(); }; }
    return;
  }
  const d = await ilApi("/api/ilmiy/pubs?" + ilQs({status: IL.pubView, q: IL.pubQ}));
  const rows = d.rows;
  L.innerHTML = `<p class="muted il-cnt">Kafedrada: ${d.counts.kafedra || 0} · Ilmiy bo'limda: ${d.counts.ilmiy || 0} · qaytarilgan: ${d.counts.qaytarildi || 0} · tasdiqlangan: ${d.counts.tasdiqlangan || 0}</p>
    <div class="tbl-wrap"><table class="il-t il-click"><thead><tr><th>Nashr</th><th>Muallif</th><th>Turi</th><th>Holati</th><th>Yuborilgan</th></tr></thead><tbody>
    ${rows.map(r => `<tr tabindex="0" data-ps="${r.id}"><td><b>${esc(r.title)}</b><small>${esc(r.journal || "")} · ${r.year}${r.doi ? ` · DOI ${esc(r.doi)}` : ""}</small>${r.note && r.status === "qaytarildi" ? `<small class="bad">${esc(r.note)}</small>` : ""}</td>
      <td>${esc(r.author)}<small>${esc(r.kafedra || "")}</small></td><td>${esc(r.kind)}${r.quartile ? ` <span class="il-chip info">${r.quartile}</span>` : ""}</td>
      <td><span class="il-chip ${ilCls(r.status)}">${esc(r.status_name)}</span>${r.can_review ? `<small class="warn">Sizning qaroringiz kutilmoqda</small>` : ""}</td><td>${ilD(r.created_at)}</td></tr>`).join("")
      || `<tr><td colspan="5" class="muted">${IL.pubView === "navbat" ? "Navbatingiz bo'sh — barcha arizalar ko'rib chiqilgan" : "Arizalar yo'q"}</td></tr>`}</tbody></table></div>`;
  L.querySelectorAll("[data-ps]").forEach(tr => { tr.onclick = () => ilPubOpen(+tr.dataset.ps); tr.onkeydown = e => { if (e.key === "Enter") ilPubOpen(+tr.dataset.ps); }; });
}
function ilPubFields(p = {}) {
  const M = IL.meta;
  return `${["kafedra", "ilmiy"].includes(M.mode) && !p.id ? `<label>Muallif (o'qituvchi)<input id="f0" placeholder="F.I.Sh. (kamida 2 harf)" autocomplete="off"><div class="il-pick" id="f0l"></div></label>` : ""}
    <label>Sarlavha<textarea id="f1" rows="2">${esc(p.title || "")}</textarea></label>
    <div class="row2"><label>Turi<select id="f2">${M.kinds.map(k => `<option ${p.kind === k ? "selected" : ""}>${esc(k)}</option>`).join("")}</select></label>
      <label>Yil<input id="f3" type="number" value="${p.year || M.year}"></label></div>
    <label>Jurnal / nashriyot<input id="f4" value="${esc(p.journal || "")}"></label>
    <div class="row2"><label>DOI<input id="f5" placeholder="10.xxxx/…" value="${esc(p.doi || "")}"></label><label>Kvartil (Scopus/WoS)<select id="f6"><option value="">—</option>${M.quartiles.map(q => `<option ${p.quartile === q ? "selected" : ""}>${q}</option>`).join("")}</select></label></div>
    <div class="row2"><label>Havola (bazadagi sahifa)<input id="f7" placeholder="https://…" value="${esc(p.url || "")}"></label><label>ISSN<input id="f8" value="${esc(p.issn || "")}"></label></div>
    <label>Hammualliflar<input id="f9" value="${esc(p.coauthors || "")}"></label>
    <p class="muted">Scopus / Web of Science uchun DOI yoki bazadagi havola majburiy. ${M.mode === "oqituvchi" ? "Ariza avval kafedra mudiriga, so'ng Ilmiy bo'limga boradi." : "Ariza Ilmiy bo'lim tekshiruviga yuboriladi."}</p>`;
}
const ilPubBody = m => ({title: m.querySelector("#f1").value, kind: m.querySelector("#f2").value, year: +m.querySelector("#f3").value, journal: m.querySelector("#f4").value,
  doi: m.querySelector("#f5").value, quartile: m.querySelector("#f6").value, url: m.querySelector("#f7").value, issn: m.querySelector("#f8").value, coauthors: m.querySelector("#f9").value});
function ilPubForm(p) {
  let tid = null;
  const m = ilModal(p ? "Arizani tuzatish" : "Yangi nashr arizasi", ilPubFields(p), async m => {
    const b = ilPubBody(m);
    if (!p && ["kafedra", "ilmiy"].includes(IL.meta.mode)) { if (!tid) { toast("Muallifni tanlang"); return false; } b.teacher_id = tid; }
    const r = await ilApi(p ? `/api/ilmiy/pubs/${p.id}/edit` : "/api/ilmiy/pubs", b);
    if (r) { toast(p ? "Tuzatildi va qayta yuborildi" : "Ariza yuborildi: " + r.status_name); ilPubList(); renderIlmiyAlerts(); } return !!r;
  }, p ? "Qayta yuborish" : "Yuborish");
  if (m.querySelector("#f0")) ilPicker(m, "#f0", "#f0l", t => { tid = t.id; });
}
async function ilPubOpen(id) {
  const p = await ilApi("/api/ilmiy/pubs/" + id), M = IL.meta;
  const isIdx = M.indexed.includes(p.kind);
  const m = ilModal("Nashr arizasi", `<p class="il-ttl">${esc(p.title)}</p>
    <dl class="il-dl"><dt>Muallif</dt><dd>${esc(p.author)} · ${esc(p.kafedra || "")}</dd><dt>Turi</dt><dd>${esc(p.kind)}${p.quartile ? ` · ${p.quartile}` : ""}</dd>
      <dt>Jurnal</dt><dd>${esc(p.journal || "—")}, ${p.year}${p.issn ? ` · ISSN ${esc(p.issn)}` : ""}</dd>
      <dt>DOI</dt><dd>${p.doi ? `<a href="https://doi.org/${esc(p.doi)}" target="_blank" rel="noopener">${esc(p.doi)}</a>` : "—"}</dd>
      ${p.url ? `<dt>Havola</dt><dd><a href="${esc(p.url)}" target="_blank" rel="noopener noreferrer">${esc(p.url.slice(0, 60))}…</a></dd>` : ""}
      ${p.coauthors ? `<dt>Hammualliflar</dt><dd>${esc(p.coauthors)}</dd>` : ""}
      <dt>Holati</dt><dd><span class="il-chip ${ilCls(p.status)}">${esc(p.status_name)}</span>${p.note ? `<small class="bad">${esc(p.note)}</small>` : ""}</dd></dl>
    ${p.can_review ? `<div class="il-rev"><b>${p.status === "kafedra" ? "Kafedra tekshiruvi" : "Ilmiy bo'lim tasdig'i"}</b>
      ${p.status === "ilmiy" && isIdx ? `<label class="il-chk"><input type="checkbox" id="r1"> Nashr ${esc(p.kind)} bazasida indekslanganini tekshirdim (DOI / havola)</label>
        <label>Kvartil<select id="r2"><option value="">—</option>${M.quartiles.map(q => `<option ${p.quartile === q ? "selected" : ""}>${q}</option>`).join("")}</select></label>` : ""}
      <label>Izoh (qaytarishda majburiy)<textarea id="r3" rows="2"></textarea></label>
      <div class="il-btns"><button class="btn primary sm" id="rOk">${ico("check", 15)}${p.status === "kafedra" ? "Tasdiqlash → Ilmiy bo'limga" : "Tasdiqlash → reyestrga"}</button><button class="btn sm ghost" id="rNo">Qaytarish</button></div></div>` : ""}
    <div class="il-btns">${p.can_edit ? `<button class="btn sm" id="pEd">Tuzatish</button>` : ""}${p.can_withdraw ? `<button class="btn sm ghost" id="pWd">Qaytarib olish</button>` : ""}</div>
    ${ilLog(p.log)}`);
  const rev = async (decision, btn) => busy(btn, async () => {
    const r = await ilApi(`/api/ilmiy/pubs/${id}/review`, {decision, note: m.querySelector("#r3").value, indexed: !!m.querySelector("#r1")?.checked, quartile: m.querySelector("#r2")?.value || ""});
    if (r) { m.close(); toast(r.status_name); ilPubList(); renderIlmiyAlerts(); } });
  if (m.querySelector("#rOk")) { m.querySelector("#rOk").onclick = e => rev("tasdiq", e.currentTarget); m.querySelector("#rNo").onclick = e => rev("qaytarish", e.currentTarget); }
  if (m.querySelector("#pEd")) m.querySelector("#pEd").onclick = () => { m.close(); ilPubForm(p); };
  if (m.querySelector("#pWd")) m.querySelector("#pWd").onclick = e => { const b = e.currentTarget; if (!arm(b, "Ha, qaytarib olish")) return;
    m.close(); undoToast("Ariza qaytarib olinadi", async () => { const r = await ilApi(`/api/ilmiy/pubs/${id}/withdraw`, {}); if (r) ilPubList(); }); };
}

/* ---------- Grantlar ---------- */
const IL_GACT = {imzoga: ["Prorektor imzosiga yuborish", "primary"], imzo: ["Imzolash", "primary"], qaytarish: ["Qaytarish", "ghost"], yuborish: ["Moliyalashtiruvchiga yuborildi", "primary"],
  yutildi: ["Yutildi", "primary"], rad: ["Rad etildi", "ghost"], yakunlash: ["Loyihani yakunlash", "primary"]};
async function ilGrants(box) {
  const M = IL.meta;
  const views = [["faol", "Faol"], ["imzoda", "Imzoda"], ["ariza berilgan", "Ko'rib chiqilmoqda"], ["bajarilmoqda", "Bajarilmoqda"], ["", "Barchasi"]];
  box.innerHTML = `<div class="il-bar"><div class="il-seg">${views.map(([k, l]) => `<button type="button" data-gv="${k}" class="${IL.gSt === k ? "on" : ""}">${l}</button>`).join("")}</div>
    <input type="search" id="ilGq" placeholder="Loyiha, rahbar yoki moliyalashtiruvchi" value="${esc(IL.gQ)}">
    ${M.can.grant_create ? `<button class="btn primary sm" id="ilGn">${ico("pen", 15)}Yangi loyiha</button>` : ""}</div><div id="ilGl"></div>`;
  box.querySelectorAll("[data-gv]").forEach(b => b.onclick = () => { IL.gSt = b.dataset.gv; ilGrants(box); });
  let t; $("#ilGq").oninput = e => { clearTimeout(t); t = setTimeout(() => { IL.gQ = e.target.value; ilGList(); }, 300); };
  if ($("#ilGn")) $("#ilGn").onclick = ilGrantForm;
  ilGList();
}
async function ilGList() {
  const L = $("#ilGl"); if (!L) return;
  const d = await ilApi("/api/ilmiy/grants?" + ilQs({status: IL.gSt, q: IL.gQ}));
  L.innerHTML = `<div class="tbl-wrap"><table class="il-t il-click"><thead><tr><th>Loyiha</th><th>Rahbar</th><th>Moliyalashtiruvchi</th><th class="num">Summa</th><th>Holati</th><th>Muddat</th></tr></thead><tbody>
    ${d.rows.map(g => `<tr tabindex="0" data-g="${g.id}"><td><b>${esc(g.title)}</b>${g.program ? `<small>${esc(g.program)}</small>` : ""}</td><td>${esc(g.leader)}<small>${esc(g.kafedra || "")}</small></td>
      <td>${esc(g.funder)}</td><td class="num">${ilSum(g.amount_won || g.amount)}</td>
      <td><span class="il-chip ${ilCls(g.status)}">${esc(g.status_name)}</span>${g.acts.length ? `<small class="warn">Sizdan amal kutilmoqda</small>` : ""}${g.overdue_reports ? `<small class="bad">${g.overdue_reports} ta hisobot muddati o'tgan</small>` : ""}</td>
      <td>${g.status === "bajarilmoqda" ? `${ilD(g.start)} – ${ilD(g.end_date)}` : g.deadline ? `ariza: ${ilD(g.deadline)}${g.deadline_passed ? ` <small class="bad">o'tgan</small>` : ""}` : "—"}</td></tr>`).join("")
      || `<tr><td colspan="6" class="muted">Loyihalar yo'q</td></tr>`}</tbody></table></div>`;
  L.querySelectorAll("[data-g]").forEach(tr => { tr.onclick = () => ilGrantOpen(+tr.dataset.g); tr.onkeydown = e => { if (e.key === "Enter") ilGrantOpen(+tr.dataset.g); }; });
}
function ilGrantForm() {
  const M = IL.meta; let lid = null;
  const m = ilModal("Yangi grant loyihasi", `${M.mode !== "oqituvchi" ? `<label>Loyiha rahbari<input id="g0" placeholder="F.I.Sh." autocomplete="off"><div class="il-pick" id="g0l"></div></label>` : ""}
    <label>Loyiha nomi<textarea id="g1" rows="2"></textarea></label>
    <div class="row2"><label>Moliyalashtiruvchi<select id="g2">${M.funders.map(f => `<option>${esc(f)}</option>`).join("")}</select></label><label>Tanlov / dastur<input id="g3"></label></div>
    <div class="row2"><label>So'ralgan summa (so'm)<input id="g4" type="number" min="1000000" step="1000000"></label><label>Davomiyligi (oy)<input id="g5" type="number" value="24" min="3" max="60"></label></div>
    <label>Ariza topshirish muddati<input id="g6" type="date" min="${M.today}"></label><label>Izoh<textarea id="g7" rows="2"></textarea></label>
    <p class="muted">Loyiha → prorektor (ilmiy ishlar) imzosi → Ilmiy bo'lim moliyalashtiruvchiga yuboradi → natija. Yutilsa — har 6 oyda oraliq va yakuniy hisobot.</p>`, async m => {
    const b = {title: m.querySelector("#g1").value, funder: m.querySelector("#g2").value, program: m.querySelector("#g3").value, amount: +m.querySelector("#g4").value || 0,
      months: +m.querySelector("#g5").value || 12, deadline: m.querySelector("#g6").value, note: m.querySelector("#g7").value};
    if (M.mode !== "oqituvchi") { if (!lid) { toast("Loyiha rahbarini tanlang"); return false; } b.leader_id = lid; }
    const r = await ilApi("/api/ilmiy/grants", b); if (r) { toast("Loyiha yaratildi"); IL.gSt = "faol"; ilGrants($("#ilBody")); } return !!r; }, "Yaratish");
  if (m.querySelector("#g0")) ilPicker(m, "#g0", "#g0l", t => { lid = t.id; });
}
async function ilGrantOpen(id) {
  const g = await ilApi("/api/ilmiy/grants/" + id);
  const m = ilModal("Grant loyihasi", `<p class="il-ttl">${esc(g.title)}</p>
    <dl class="il-dl"><dt>Rahbar</dt><dd>${esc(g.leader)} · ${esc(g.kafedra || "")}</dd><dt>Moliyalashtiruvchi</dt><dd>${esc(g.funder)}${g.program ? ` · ${esc(g.program)}` : ""}</dd>
      <dt>Summa</dt><dd>${g.amount_won ? `${ilSum(g.amount_won)} ajratilgan` : `${ilSum(g.amount)} so'ralgan`}</dd>
      <dt>Holati</dt><dd><span class="il-chip ${ilCls(g.status)}">${esc(g.status_name)}</span>${g.note ? `<small>${esc(g.note)}</small>` : ""}</dd>
      ${g.deadline ? `<dt>Ariza muddati</dt><dd>${ilD(g.deadline)}</dd>` : ""}${g.start ? `<dt>Bajarilish</dt><dd>${ilD(g.start)} – ${ilD(g.end_date)} (${g.months} oy)</dd>` : ""}</dl>
    ${g.acts.length ? `<div class="il-rev">${g.acts.includes("yutildi") ? `<div class="row2"><label>Ajratilgan summa<input id="a1" type="number" value="${g.amount}"></label><label>Boshlanish<input id="a2" type="date" value="${IL.meta.today}"></label></div>
      <label>Davomiyligi (oy)<input id="a3" type="number" value="${g.months || 24}"></label>` : ""}
      <label>Izoh${g.acts.some(a => ["qaytarish", "rad"].includes(a)) ? " (qaytarish / rad etishda — sabab)" : ""}<textarea id="a4" rows="2"></textarea></label>
      <div class="il-btns">${g.acts.map(a => `<button class="btn sm ${IL_GACT[a][1]}" data-ga="${a}">${esc(IL_GACT[a][0])}</button>`).join("")}</div></div>` : ""}
    ${g.reports.length ? `<h4>Hisobotlar</h4><div class="il-reps">${g.reports.map(r => `<div class="il-rep ${r.overdue ? "od" : ""}"><div><b>${esc(r.title)}</b>
        <small>muddat ${ilD(r.due)}${r.overdue ? " · muddati o'tgan" : ""}${r.submitted_at ? ` · topshirildi ${ilD(r.submitted_at)}` : ""}</small>${r.note ? `<small>${esc(r.note)}</small>` : ""}${r.review_note ? `<small class="bad">${esc(r.review_note)}</small>` : ""}</div>
        <span class="il-chip ${ilCls(r.status)}">${esc(r.status_name)}</span>
        ${r.acts.length ? `<div class="il-btns">${r.acts.map(a => `<button class="btn sm ${a === "qaytarish" ? "ghost" : ""}" data-ra="${r.id}:${a}">${{topshirish: "Topshirish", qabul: "Qabul qilish", qaytarish: "Qaytarish"}[a]}</button>`).join("")}</div>` : ""}</div>`).join("")}</div>` : ""}
    ${ilLog(g.log)}`);
  m.querySelectorAll("[data-ga]").forEach(b => b.onclick = () => {
    const a = b.dataset.ga;
    if (["rad", "yakunlash"].includes(a) && !arm(b, "Tasdiqlaysizmi?")) return;
    busy(b, async () => {
      const r = await ilApi(`/api/ilmiy/grants/${id}/act`, {action: a, note: m.querySelector("#a4").value, amount_won: +m.querySelector("#a1")?.value || null,
        start: m.querySelector("#a2")?.value || "", months: +m.querySelector("#a3")?.value || null});
      if (r) { m.close(); toast(r.status_name); ilGList(); renderIlmiyAlerts(); } }); });
  m.querySelectorAll("[data-ra]").forEach(b => b.onclick = () => {
    const [rid, a] = b.dataset.ra.split(":");
    const go = async note => { const r = await ilApi(`/api/ilmiy/grants/${id}/reports/${rid}`, {action: a, note}); if (r) { m.close(); toast("Hisobot: " + ({topshirish: "topshirildi", qabul: "qabul qilindi", qaytarish: "qaytarildi"})[a]); ilGList(); renderIlmiyAlerts(); } return !!r; };
    if (a === "qabul") return busy(b, () => go(""));
    ilModal(a === "topshirish" ? "Hisobotni topshirish" : "Hisobotni qaytarish", `<label>${a === "topshirish" ? "Bajarilgan ishlar va natijalar" : "Qaytarish sababi"}<textarea id="n1" rows="4"></textarea></label>`,
      mm => go(mm.querySelector("#n1").value), a === "topshirish" ? "Topshirish" : "Qaytarish");
  });
}

/* ---------- Dissertatsiyalar ---------- */
async function ilDiss(box) {
  const F = IL.d;
  box.innerHTML = `<div class="il-bar"><div class="il-seg" id="ilDf"></div>
    <select id="ilDc"><option value="">Barcha kurslar</option><option value="1" ${F.course === "1" ? "selected" : ""}>1-kurs</option><option value="2" ${F.course === "2" ? "selected" : ""}>2-kurs</option></select>
    <input type="search" id="ilDq" placeholder="Magistrant, mavzu yoki ilmiy rahbar" value="${esc(F.q)}"></div><div id="ilDl"></div>`;
  $("#ilDc").onchange = e => { F.course = e.target.value; F.page = 1; ilDList(); };
  let t; $("#ilDq").oninput = e => { clearTimeout(t); t = setTimeout(() => { F.q = e.target.value; F.page = 1; ilDList(); }, 300); };
  ilDList();
}
async function ilDList() {
  const L = $("#ilDl"), F = IL.d; if (!L) return;
  const d = await ilApi("/api/ilmiy/diss?" + ilQs(F));
  const flags = [["", "Barchasi", d.counts.all], ["overdue", "Muddati o'tgan", d.counts.overdue], ["soon", `${14} kun ichida`, d.counts.soon], ["topshirildi", "Ko'rib chiqish kutilmoqda", d.counts.topshirildi], ["no_sup", "Rahbarsiz", d.counts.no_sup]];
  $("#ilDf").innerHTML = flags.map(([k, l, n]) => `<button type="button" data-df="${k}" class="${F.flag === k ? "on" : ""}">${l} <em>${n}</em></button>`).join("");
  $("#ilDf").querySelectorAll("[data-df]").forEach(b => b.onclick = () => { F.flag = b.dataset.df; F.page = 1; ilDList(); });
  L.innerHTML = `<div class="tbl-wrap"><table class="il-t il-click"><thead><tr><th>Magistrant</th><th>Mavzu</th><th>Ilmiy rahbar</th><th>Joriy bosqich</th><th class="num">Bosqichlar</th></tr></thead><tbody>
    ${d.rows.map(r => `<tr tabindex="0" data-m="${r.id}" class="${r.overdue ? "il-od" : ""}"><td><b>${esc(r.student)}</b><small>${esc(r.grp || "")} · ${r.course}-kurs${r.st_status !== "faol" ? ` · ${esc(r.st_status)}` : ""}</small></td>
      <td>${r.topic ? esc(r.topic) : `<span class="muted">belgilanmagan</span>`}</td><td>${r.supervisor ? `${esc(r.supervisor)}<small>${esc(r.sup_degree || "")}</small>` : `<span class="il-chip warn">yo'q</span>`}</td>
      <td>${r.current ? `${esc(r.current.name)}<small class="${r.current.overdue ? "bad" : r.current.soon ? "warn" : ""}">muddat ${ilD(r.current.due)}${r.current.overdue ? " · o'tgan" : ""}${r.current.status === "topshirildi" ? " · material topshirildi" : r.current.status === "qayta" ? " · qayta topshirish" : ""}</small>` : `<span class="il-chip ok">Himoya qilindi</span>`}</td>
      <td class="num"><span class="il-prog" title="${r.done} / 6"><i style="width:${Math.round(100 * r.done / 6)}%"></i></span> ${r.done}/6</td></tr>`).join("")
      || `<tr><td colspan="5" class="muted">Magistrantlar topilmadi</td></tr>`}</tbody></table></div>
    ${d.pages > 1 ? `<div class="il-pg"><button class="btn sm ghost" id="ilD1" ${d.page <= 1 ? "disabled" : ""}>‹ Oldingi</button><span>${d.page} / ${d.pages} · ${fmt(d.total)} ta</span><button class="btn sm ghost" id="ilD2" ${d.page >= d.pages ? "disabled" : ""}>Keyingi ›</button></div>` : `<p class="muted">${fmt(d.total)} ta magistrant</p>`}`;
  if ($("#ilD1")) { $("#ilD1").onclick = () => { F.page--; ilDList(); }; $("#ilD2").onclick = () => { F.page++; ilDList(); }; }
  L.querySelectorAll("[data-m]").forEach(tr => { tr.onclick = () => ilDOpen(+tr.dataset.m); tr.onkeydown = e => { if (e.key === "Enter") ilDOpen(+tr.dataset.m); }; });
}
const IL_SACT = {topshirildi: "Material topshirildi", otdi: "O'tdi", qayta: "Qayta topshirish", muddat: "Muddatni o'zgartirish"};
async function ilDOpen(id, keep) {
  const r = await ilApi("/api/ilmiy/diss/" + id), M = IL.meta;
  keep?.close();
  const m = ilModal("Magistrlik dissertatsiyasi", `<p class="il-ttl">${esc(r.student)} <small class="muted">${esc(r.grp || "")} · ${r.course}-kurs · ${esc(r.direction || "")}</small></p>
    <dl class="il-dl"><dt>Mavzu</dt><dd>${r.topic ? esc(r.topic) : `<span class="muted">belgilanmagan</span>`}</dd>
      <dt>Ilmiy rahbar</dt><dd>${r.supervisor ? `${esc(r.supervisor)} · ${esc(r.sup_degree || "darajasiz")}` : `<span class="il-chip warn">belgilanmagan</span>`}</dd><dt>Kafedra</dt><dd>${esc(r.kafedra || "—")}</dd></dl>
    ${r.can_assign ? `<button class="btn sm" id="dAs">${r.topic ? "Mavzu / rahbarni o'zgartirish" : "Mavzu va rahbarni belgilash"}</button>` : ""}
    <ol class="il-steps">${r.stages.map(s => `<li class="${s.status === "o'tdi" ? "done" : s.overdue ? "od" : s.status === "topshirildi" ? "sub" : ""}">
      <div class="il-sh"><b>${esc(s.name)}</b><span class="il-chip ${ilCls(s.status)}">${esc(s.status_name)}</span></div>
      <small>${s.status === "o'tdi" ? `o'tdi ${ilD(s.done_at)}${s.protocol ? ` · bayonnoma ${esc(s.protocol)}` : ""}${s.score != null ? ` · ${s.score} ball` : ""}` : `muddat ${ilD(s.due)}${s.overdue ? " · muddati o'tgan" : s.soon ? " · yaqinlashmoqda" : ""}${s.submitted_at ? ` · material ${ilD(s.submitted_at)}` : ""}`}</small>
      ${s.note ? `<small class="${s.status === "qayta" ? "bad" : ""}">${esc(s.note)}</small>` : ""}
      ${s.acts.length ? `<div class="il-btns">${s.acts.map(a => `<button class="btn sm ${a === "otdi" ? "primary" : "ghost"}" data-sa="${s.stage}:${a}">${IL_SACT[a]}</button>`).join("")}</div>` : ""}</li>`).join("")}</ol>
    ${ilLog(r.log)}`);
  if (m.querySelector("#dAs")) m.querySelector("#dAs").onclick = () => {
    let sid = r.supervisor_id;
    const approved = r.stages[0].status === "o'tdi";
    const pm = ilModal("Mavzu va ilmiy rahbar", `<label>Dissertatsiya mavzusi<textarea id="t1" rows="3">${esc(r.topic || "")}</textarea></label>
      <label>Ilmiy rahbar${r.supervisor ? ` (hozir: ${esc(r.supervisor)})` : ""}<input id="t2" placeholder="F.I.Sh. — o'zgartirish uchun qidiring" autocomplete="off"><div class="il-pick" id="t2l"></div></label>
      ${approved ? `<label>O'zgartirish sababi (bayonnoma)<input id="t3"></label>` : ""}
      <p class="muted">Ilmiy rahbar — PhD yoki DSc darajali, ko'pi bilan ${M.sup_max} ta magistrant. ${M.mode === "kafedra" ? "Kafedra taklif qiladi, tasdiqni Magistratura bo'limi qayd etadi." : ""}</p>`, async mm => {
      if (!sid) { toast("Ilmiy rahbarni tanlang"); return false; }
      const x = await ilApi(`/api/ilmiy/diss/${id}/assign`, {topic: mm.querySelector("#t1").value, supervisor_id: sid, reason: mm.querySelector("#t3")?.value || ""});
      if (x) { toast("Saqlandi"); ilDOpen(id, m); ilDList(); } return !!x; });
    ilPicker(pm, "#t2", "#t2l", t => { sid = t.id; });
  };
  m.querySelectorAll("[data-sa]").forEach(b => b.onclick = () => {
    const [st, a] = b.dataset.sa.split(":"), S = r.stages.find(x => x.stage === st), proto = M.stages.find(x => x.key === st).protocol;
    const html = a === "topshirildi" ? `<label>Izoh (ixtiyoriy)<textarea id="s1" rows="2"></textarea></label>`
      : a === "otdi" ? `${proto ? `<label>Bayonnoma (raqami va sanasi)<input id="s2" placeholder="№3, ${dmy(M.today)}"></label>` : ""}${st === "himoya" ? `<label>Himoya bahosi (0–100, o'tish ${M.defense_pass})<input id="s3" type="number" min="0" max="100"></label>` : ""}<label>Izoh<textarea id="s1" rows="2"></textarea></label>`
      : a === "qayta" ? `<label>Kamchiliklar<textarea id="s1" rows="3"></textarea></label>${proto ? `<label>Bayonnoma<input id="s2"></label>` : ""}<p class="muted">Yangi muddat — 30 kundan keyin.</p>`
      : `<label>Yangi muddat<input id="s4" type="date" min="${M.today}" value="${S.due}"></label><label>Sabab<textarea id="s1" rows="2"></textarea></label>`;
    ilModal(`${S.name}: ${IL_SACT[a]}`, html, async mm => {
      const x = await ilApi(`/api/ilmiy/diss/${id}/stage`, {stage: st, action: a, note: mm.querySelector("#s1")?.value || "", protocol: mm.querySelector("#s2")?.value || "",
        score: mm.querySelector("#s3") ? +mm.querySelector("#s3").value : null, due: mm.querySelector("#s4")?.value || ""});
      if (x) { toast(`${S.name}: ${IL_SACT[a].toLowerCase()}`); ilDOpen(id, m); ilDList(); renderIlmiyAlerts(); } return !!x; }, IL_SACT[a]);
  });
}
function ilBindAlerts(root) {
  root.querySelectorAll("[data-al]").forEach(b => b.onclick = () => { const a = IL.meta.alerts[+b.dataset.al];
    if (a.tab === "dissertatsiya") { IL.d.flag = a.flag || ""; IL.d.page = 1; }
    if (a.tab === "nashrlar") IL.pubView = ["kafedra", "ilmiy"].includes(IL.meta.mode) ? "navbat" : "qaytarildi";
    if (a.tab === "grantlar") IL.gSt = "faol";
    IL.setTab(a.tab); });
}
async function renderIlmiyAlerts() {
  try { const M = await ilApi("/api/ilmiy/meta"); IL.meta = M;
    let el = document.querySelector("#v-ilmiy .il-alerts");
    if (!el) { const t = document.querySelector("#v-ilmiy .il-tabs"); if (!t || !M.alerts.length) return; t.insertAdjacentHTML("beforebegin", `<div class="il-alerts"></div>`); el = document.querySelector("#v-ilmiy .il-alerts"); }
    el.innerHTML = M.alerts.map((a, i) => `<button type="button" class="il-al ${a.kind}" data-al="${i}">${ico("alert", 15)}${esc(a.text)}</button>`).join("");
    el.hidden = !M.alerts.length; ilBindAlerts(el);
  } catch (e) {}
}
