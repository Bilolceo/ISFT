/* =====================================================================
   «Kadrlar» — shaxsiy ish, ishga qabul, ishdan bo'shatish, shartnoma muddatlari, attestatsiya, shtat jadvali (app/kadrlar.py, /api/hr).
     kadrlar:       to'liq — shaxsiy ishlar, uzaytirish, attestatsiya/malaka, vakansiya → nomzod → buyruq → AT so'rovi, bo'shatish varaqasi, shtat jadvali.
     rektor:        jamlangan ko'rsatkichlar (shaxsiy ma'lumotsiz), vakansiya va nomzodni tasdiqlash; buyruqni «Buyruqlar»da imzolaydi.
     bo'lim rahbari / kafedra mudiri: o'z bo'limi — ism, lavozim, stavka, muddat belgilari; vakansiya taklifi.
     boshqalar:     o'z shaxsiy ishi «Shaxsiy ma'lumotlar» oynasida (kadrlarProfile).
   Ta'til va safarlar — «Xodimlar ta'tili» (staffabs.js). Ruxsatlar serverda tekshiriladi.
   Global: renderKadrlar() — app.js go(); kadrlarNav() — bo'lim rahbarlariga menyu; kadrlarProfile(body) — extras.js profil oynasi.
   ===================================================================== */
const KD = {meta: null, tab: "", q: "", flag: "", unit: "", open: null, form: null, vacForm: false, disForm: false};
if (!document.querySelector('link[href="kadrlar.css"]')) document.head.insertAdjacentHTML("beforeend", '<link rel="stylesheet" href="kadrlar.css">');
if (typeof ICONS === "object") {
  Object.assign(ICONS, Object.fromEntries(Object.entries({
    idcard: '<rect x="3" y="4" width="18" height="16" rx="2"/><circle cx="9" cy="11" r="2.5"/><path d="M5.5 17c.6-1.8 2-2.7 3.5-2.7s2.9.9 3.5 2.7M14 9.5h4M14 13h4"/>',
    plus: '<path d="M12 5v14M5 12h14"/>',
    back: '<path d="m15 18-6-6 6-6"/>',
    check: '<path d="M20 6 9 17l-5-5"/>',
  }).filter(([k]) => !ICONS[k])));
  try { const s = document.querySelector('#nav a[data-v="kadrlar"] svg'); if (s && !s.innerHTML.trim()) { s.remove(); hydrateIcons(); } } catch (e) {}
}
async function kdApi(url, body) {
  const r = await fetch(url, {method: body === undefined ? "GET" : "POST", credentials: "same-origin", headers: {"Content-Type": "application/json"},
                              body: body === undefined ? undefined : JSON.stringify(body)});
  if (r.status === 401) { showLogin(); throw new Error("auth"); }
  const d = await r.json().catch(() => ({}));
  if (!r.ok) { const m = d.message || (typeof d.detail === "string" ? d.detail : "") || "Xatolik yuz berdi"; if (body !== undefined) { toast(m); return null; } const e = new Error(r.status === 403 ? "denied" : "api"); e.msg = m; throw e; }
  return d;
}
const kdN = x => (Math.round((x || 0) * 100) / 100).toString().replace(".", ",");
const kdLink = l => { if (typeof XT !== "undefined" && XT.openLink) XT.openLink(l); };
const KD_CON = {expired: ["Muddati o'tgan", "bad"], d30: ["30 kun ichida", "bad"], d60: ["60 kun ichida", "warn"]};
const KD_DUE = {overdue: ["Muddati o'tgan", "bad"], none: ["Qayd yo'q", "bad"], soon: ["90 kun ichida", "warn"]};
function kdFlags(f) {
  const out = [];
  if (f.contract) out.push(`<span class="kd-tag ${KD_CON[f.contract][1]}">Shartnoma: ${KD_CON[f.contract][0].toLowerCase()}${f.contract_days != null && f.contract !== "expired" ? ` (${f.contract_days} kun)` : ""}</span>`);
  if (f.attest) out.push(`<span class="kd-tag ${KD_DUE[f.attest][1]}">Attestatsiya: ${KD_DUE[f.attest][0].toLowerCase()}</span>`);
  if (f.qual) out.push(`<span class="kd-tag ${KD_DUE[f.qual][1]}">Malaka oshirish: ${KD_DUE[f.qual][0].toLowerCase()}</span>`);
  return out.join("");
}
const kdKpi = (n, l, s, cls = "") => `<div class="kd-kpi ${cls}"><b>${n}</b><span>${esc(l)}</span>${s ? `<small>${s}</small>` : ""}</div>`;
const kdEmpty = (t, s = "") => `<div class="kd-empty"><b>${esc(t)}</b>${s ? `<span>${esc(s)}</span>` : ""}</div>`;

/* menyu: bo'lim rahbarlari (kafedra mudiridan tashqari) — serverdan rejim so'raladi */
async function kadrlarNav() {
  const a = document.querySelector('#nav a[data-v="kadrlar"]');
  if (!a || !a.classList.contains("hidden")) return;
  try { const m = await kdApi("/api/hr/meta"); if (m.mode !== "own") { a.classList.remove("hidden"); const h = a.parentElement && [...a.parentElement.querySelectorAll(".nav-h")].filter(x => x.compareDocumentPosition(a) & 4).pop(); h && h.classList.remove("hidden"); } } catch (e) {}
}

/* «Shaxsiy ma'lumotlar» oynasi: o'z shaxsiy ishi (faqat o'qish) */
async function kadrlarProfile(body) {
  let d; try { d = await kdApi("/api/hr/me"); } catch (e) { return; }
  if (!d || !d.found || !body.isConnected) return;
  const row = (k, v) => v ? `<div class="xt-pf-r"><dt>${k}</dt><dd>${v}</dd></div>` : "";
  const ct = (KD.meta?.contract_types || {muddatli: "Muddatli mehnat shartnomasi", muddatsiz: "Muddatsiz mehnat shartnomasi", orindosh: "O'rindoshlik (muddatli)"})[d.contract_type] || d.contract_type;
  const sec = document.createElement("section"); sec.className = "xt-pf-sec";
  sec.innerHTML = `<h4>Kadrlar ma'lumoti</h4><dl class="xt-pf-dl">
      ${row("Lavozim va stavka", `${esc(d.position)} · ${kdN(d.rate)} stavka<small>${esc(d.unit)}</small>`)}
      ${row("Ishga qabul qilingan", d.hired ? dmy(d.hired) : "")}
      ${row("Ma'lumoti", esc([d.education, d.specialty].filter(Boolean).join(", ")))}
      ${row("Ilmiy daraja / unvon", esc([d.degree, d.academic_title].filter(x => x && x !== "—").join(", ") || "—"))}
      ${row("Mehnat shartnomasi", `${esc(ct)}${d.contract_end ? `<small>${dmy(d.contract_end)} gacha</small>` : ""}`)}
      ${row("Attestatsiya", d.last_attest ? `${dmy(d.last_attest)}<small>keyingisi: ${d.flags.attest_due ? dmy(d.flags.attest_due) : "—"}</small>` : "Qayd yo'q")}
      ${d.flags.qual !== undefined ? row("Malaka oshirish", d.last_qual ? `${dmy(d.last_qual)}<small>keyingisi: ${d.flags.qual_due ? dmy(d.flags.qual_due) : "—"}</small>` : "Qayd yo'q") : ""}
    </dl>${kdFlags(d.flags) ? `<div class="kd-tags">${kdFlags(d.flags)}</div>` : ""}
    <p class="xt-pf-note">Ma'lumotlarni Kadrlar bo'limi yuritadi. Xato bo'lsa — Portal orqali Kadrlar bo'limiga yozing. Ta'til va safarlar — «Xodimlar ta'tili» bo'limida.</p>`;
  const first = body.querySelector(".xt-pf-sec");
  first ? first.after(sec) : body.prepend(sec);
}

/* ---------- asosiy ko'rinish ---------- */
async function renderKadrlar() {
  const el = $("#v-kadrlar");
  if (!el.innerHTML) el.innerHTML = `<p class="muted">Yuklanmoqda…</p>`;
  try { KD.meta = await kdApi("/api/hr/meta"); } catch (e) { if (e?.message !== "auth") el.innerHTML = errCard("kadrlar"); return; }
  const M = KD.meta;
  if (M.mode === "own") { el.innerHTML = `<div class="head"><div><h2>Kadrlar</h2></div></div>${locked("Kadrlar bo'limi")}<p class="muted">O'z shaxsiy ishingiz — profil menyusidagi «Shaxsiy ma'lumotlar» oynasida.</p>`; return; }
  const tabs = {full: [["home", "Umumiy"], ["staff", "Xodimlar"], ["hire", "Ishga qabul"], ["dismiss", "Bo'shatish"], ["staffing", "Shtat jadvali"]],
                rektor: [["home", "Umumiy"], ["hire", "Vakansiya va nomzodlar"], ["staffing", "Shtat jadvali"]],
                head: [["home", "Bo'lim xodimlari"], ["hire", "Vakansiyalar"], ["staffing", "Shtat jadvali"]]}[M.mode];
  if (!tabs.some(t => t[0] === KD.tab)) KD.tab = "home";
  const sub = {full: "Shaxsiy ishlar, ishga qabul va bo'shatish, shartnoma muddatlari, attestatsiya va shtat jadvali. Ta'til va safarlar — «Xodimlar ta'tili».",
               rektor: "Jamlangan kadrlar ko'rsatkichlari (shaxsiy ma'lumotlarsiz), vakansiya va nomzodlarni tasdiqlash. Buyruqlar — «Buyruqlar» bo'limida imzolanadi.",
               head: `${M.unit?.name || ""}: xodimlar, muddat belgilari va vakansiya taklifi (shaxsiy ma'lumotlarsiz).`}[M.mode];
  el.innerHTML = `<div class="head kd-head"><div><h2>Kadrlar</h2><span class="muted">${esc(sub)}</span></div></div>
    <div class="pn-tabs kd-tabs" role="tablist">${tabs.map(([k, l]) => `<button class="pn-tab${KD.tab === k ? " on" : ""}" role="tab" aria-selected="${KD.tab === k}" data-kdt="${k}">${l}</button>`).join("")}</div>
    <div id="kdBody"></div>`;
  el.querySelectorAll("[data-kdt]").forEach(b => b.onclick = () => { KD.tab = b.dataset.kdt; KD.open = null; el.querySelectorAll("[data-kdt]").forEach(x => { x.classList.toggle("on", x === b); x.setAttribute("aria-selected", x === b); }); kdTab(); });
  await kdTab();
}
async function kdTab() {
  const body = $("#kdBody");
  try { await ({home: kdHome, staff: kdStaff, hire: kdHire, dismiss: kdDismiss, staffing: kdStaffing}[KD.tab] || kdHome)(); }
  catch (e) { if (e?.message === "auth") return; body.innerHTML = e?.message === "denied" ? locked("Bu bo'lim") : errCard("kadrlar"); }
}

/* ---------- 1) umumiy: KPI + ogohlantirishlar ---------- */
async function kdHome() {
  const M = KD.meta, [S, A] = await Promise.all([kdApi("/api/hr/summary"), kdApi("/api/hr/alerts")]);
  const K = S.kpi;
  let html = `<div class="kd-kpis">
    ${kdKpi(K.headcount, "faol xodim", `${kdN(K.rates_fact)} / ${kdN(K.rates_plan)} stavka band`)}
    ${kdKpi(kdN(K.vacant_rates), "bo'sh stavka", `ochiq vakansiya: ${K.vacancies_open}`, K.vacant_rates ? "warn" : "")}
    ${kdKpi(K.contract_30 + K.contract_expired, "shartnoma: 30 kun / o'tgan", `60 kun ichida yana ${K.contract_60} ta`, K.contract_30 + K.contract_expired ? "bad" : "")}
    ${kdKpi(K.attest_overdue + K.qual_overdue, "attestatsiya / malaka kechikkan", `attestatsiya ${K.attest_overdue} · malaka ${K.qual_overdue}`, K.attest_overdue + K.qual_overdue ? "warn" : "")}
    ${M.mode !== "head" ? kdKpi(K.vacancies_pending + K.candidates_pending, "rektor tasdig'ida", `vakansiya ${K.vacancies_pending} · nomzod ${K.candidates_pending}`, M.mode === "rektor" && K.vacancies_pending + K.candidates_pending ? "bad" : "") : ""}
    ${M.mode === "full" ? kdKpi(K.dismissals, "bo'shatish jarayonida", `bo'lim takliflari: ${K.vacancies_proposed}`) : ""}</div>`;
  if (A.aggregate || M.mode === "rektor") {
    html += `<div class="card kd-card"><h4>Bo'linmalar kesimida</h4>${kdUnitTable(S.by_unit)}</div>`;
  } else {
    const sec = (t, L, empty) => `<div class="card kd-card"><h4>${t} <em class="kd-cnt">${L.length}</em></h4>${L.length ? `<ul class="kd-list">${L.slice(0, 60).map(x =>
      `<li${M.mode === "full" ? ` data-sid="${x.id}" tabindex="0"` : ""}><div><b>${esc(x.name)}</b><small>${esc(x.position || "")} · ${esc(x.unit)}</small></div><div class="kd-tags">${kdFlags(x.flags)}</div></li>`).join("")}</ul>
      ${L.length > 60 ? `<p class="muted tiny">Yana ${L.length - 60} ta — «Xodimlar» bo'limida filtr bilan.</p>` : ""}` : kdEmpty(empty)}</div>`;
    html += `<div class="kd-grid">${sec("Mehnat shartnomasi muddati", A.contracts, "60 kun ichida tugaydigan shartnoma yo'q")}
      ${sec(`Attestatsiya (har ${M.years.attest} yilda)`, A.attest, "Kechikkan attestatsiya yo'q")}
      ${sec(`Malaka oshirish (har ${M.years.qual} yilda)`, A.qual, "Kechikkan malaka oshirish yo'q")}</div>`;
    if (M.mode === "head") html += `<div class="card kd-card"><h4>Bo'lim xodimlari</h4><div id="kdHeadStaff"><p class="muted">Yuklanmoqda…</p></div></div>`;
  }
  $("#kdBody").innerHTML = html;
  $("#kdBody").querySelectorAll("[data-sid]").forEach(li => { li.onclick = li.onkeydown = e => { if (e.type === "keydown" && e.key !== "Enter") return; KD.tab = "staff"; KD.open = +li.dataset.sid; renderKadrlar(); }; });
  if (M.mode === "head") {
    const L = await kdApi("/api/hr/staff");
    $("#kdHeadStaff").innerHTML = L.items.length ? `<table class="kd-tb"><thead><tr><th>F.I.Sh.</th><th>Lavozim</th><th>Stavka</th><th>Belgilar</th></tr></thead><tbody>
      ${L.items.map(x => `<tr><td>${esc(x.name)}</td><td>${esc(x.position || "")}</td><td>${kdN(x.rate)}</td><td>${kdFlags(x.flags) || `<span class="muted tiny">—</span>`}</td></tr>`).join("")}</tbody></table>` : kdEmpty("Xodimlar yo'q");
  }
}
function kdUnitTable(rows) {
  if (!rows.length) return kdEmpty("Ma'lumot yo'q");
  return `<div class="kd-scroll"><table class="kd-tb"><thead><tr><th>Bo'linma</th><th>Xodim</th><th>Stavka (amalda / reja)</th><th>Bo'sh</th><th>Shartnoma ≤60 kun</th><th>Muddati o'tgan</th><th>Attestatsiya</th><th>Malaka</th></tr></thead><tbody>
    ${rows.map(u => `<tr><td>${esc(u.name)}</td><td>${u.headcount}</td><td>${kdN(u.fact)} / ${kdN(u.plan)}</td><td class="${u.vacant ? "warn" : ""}">${kdN(u.vacant)}</td>
      <td class="${u.contract_60 ? "warn" : ""}">${u.contract_60}</td><td class="${u.contract_expired ? "bad" : ""}">${u.contract_expired}</td><td>${u.attest_overdue}</td><td>${u.qual_overdue}</td></tr>`).join("")}</tbody></table></div>`;
}

/* ---------- 2) xodimlar ro'yxati va shaxsiy ish (kadrlar) ---------- */
async function kdStaff() {
  const M = KD.meta, qs = new URLSearchParams(Object.entries({q: KD.q, flag: KD.flag, unit: KD.unit, limit: 500}).filter(([, v]) => v !== ""));
  const L = await kdApi(`/api/hr/staff?${qs}`);
  const flags = [["", "Hammasi"], ["contract", "Shartnoma ≤60 kun"], ["attest", "Attestatsiya"], ["qual", "Malaka oshirish"]];
  $("#kdBody").innerHTML = `<div class="kd-wrap${KD.open ? " has-open" : ""}"><aside class="card kd-side">
      <div class="kd-flt">${flags.map(([k, l]) => `<button class="${KD.flag === k ? "on" : ""}" data-f="${k}">${l}</button>`).join("")}</div>
      <div class="kd-row"><select id="kdUnit"><option value="">Barcha bo'linmalar</option>${M.units.map(u => `<option value="${esc(u.key)}"${KD.unit === u.key ? " selected" : ""}>${esc(u.name)}</option>`).join("")}</select>
        <input id="kdQ" type="search" placeholder="Ism yoki lavozim" value="${esc(KD.q)}"></div>
      <p class="muted tiny">${L.total} ta xodim</p>
      <div class="kd-items">${L.items.map(x => `<button class="kd-it${KD.open === x.id ? " on" : ""}" data-sid="${x.id}"><b>${esc(x.name)}</b><small>${esc(x.position || "")} · ${esc(x.unit)} · ${kdN(x.rate)} st.</small>
        <span class="kd-tags">${kdFlags(x.flags)}</span></button>`).join("") || kdEmpty("Topilmadi")}</div></aside>
    <section class="card kd-read" id="kdRead">${KD.open ? `<p class="muted">Yuklanmoqda…</p>` : kdEmpty("Xodimni tanlang", "Shaxsiy ish, shartnoma, attestatsiya va malaka oshirish tarixi")}</section></div>`;
  const B = $("#kdBody");
  B.querySelectorAll("[data-f]").forEach(b => b.onclick = () => { KD.flag = b.dataset.f; kdStaff(); });
  $("#kdUnit").onchange = e => { KD.unit = e.target.value; kdStaff(); };
  let t; $("#kdQ").oninput = e => { clearTimeout(t); t = setTimeout(() => { KD.q = e.target.value.trim(); kdStaff().then(() => { const i = $("#kdQ"); i.focus(); i.setSelectionRange(i.value.length, i.value.length); }); }, 300); };
  B.querySelectorAll("[data-sid]").forEach(b => b.onclick = () => { KD.open = +b.dataset.sid; B.querySelectorAll(".kd-it").forEach(x => x.classList.toggle("on", x === b)); B.querySelector(".kd-wrap").classList.add("has-open"); kdFile(); });
  if (KD.open) kdFile();
}
async function kdFile() {
  const M = KD.meta, R = $("#kdRead"), sid = KD.open;
  let d; try { d = await kdApi(`/api/hr/staff/${sid}`); } catch (e) { R.innerHTML = e?.message === "denied" ? locked("Shaxsiy ish") : errCard("kadrlar"); return; }
  const row = (k, v) => `<dt>${k}</dt><dd>${v || "—"}</dd>`, CT = M.contract_types;
  const ab = d.absences.length ? `<ul class="kd-mini">${d.absences.map(a => `<li>${esc(a.kind)} · ${dmy(a.start)}–${dmy(a.end)}${a.status !== "faol" ? " · bekor" : ""}</li>`).join("")}</ul>` : `<span class="muted tiny">Yozuv yo'q</span>`;
  R.innerHTML = `<button class="btn sm ghost kd-back" id="kdBack">${ico("back", 15)} Ro'yxat</button>
    <div class="kd-fh"><div><h3>${esc(d.name)}</h3><span class="muted">${esc(d.position || "")} · ${esc(d.unit)}</span></div>
      <span class="kd-st ${d.status === "faol" ? "ok" : "off"}">${d.status === "faol" ? "Faol" : "Bo'shatilgan " + (d.dismissed_on ? dmy(d.dismissed_on) : "")}</span></div>
    <div class="kd-tags">${kdFlags(d.flags)}</div>
    <dl class="kd-dl">${row("Stavka", kdN(d.rate))}${row("Ishga qabul", d.hired ? dmy(d.hired) : "")}${row("Ma'lumoti", esc([d.education, d.specialty].filter(Boolean).join(", ")))}
      ${row("Ilmiy daraja", esc(d.degree))}${row("Ilmiy unvon", esc(d.academic_title))}
      ${row("Mehnat shartnomasi", `${esc(CT[d.contract_type] || d.contract_type || "")} № ${esc(d.contract_no || "")}<br><small>${d.contract_start ? dmy(d.contract_start) : "—"} — ${d.contract_end ? dmy(d.contract_end) : "muddatsiz"}</small>`)}
      ${row("Attestatsiya", d.last_attest ? `${dmy(d.last_attest)} <small>· keyingisi ${d.flags.attest_due ? dmy(d.flags.attest_due) : "—"}</small>` : "Qayd yo'q")}
      ${d.flags.qual !== undefined ? row("Malaka oshirish", d.last_qual ? `${dmy(d.last_qual)} <small>· keyingisi ${d.flags.qual_due ? dmy(d.flags.qual_due) : "—"}</small>` : "Qayd yo'q") : ""}
      ${row("Ta'til va safarlar", ab + ` <a href="#" id="kdAbs" class="tiny">«Xodimlar ta'tili» →</a>`)}</dl>
    ${d.status === "faol" ? `<div class="kd-acts">
      <details class="kd-det"><summary>Shartnomani uzaytirish</summary><div class="kd-form">
        <label>Turi<select id="kdRT">${Object.entries(CT).map(([k, v]) => `<option value="${k}"${k === d.contract_type ? " selected" : ""}>${esc(v)}</option>`).join("")}</select></label>
        <label>Yangi tugash sanasi<input type="date" id="kdRE"></label><label>Raqami (ixtiyoriy)<input id="kdRN" placeholder="avtomatik"></label>
        <label class="kd-wide">Izoh<input id="kdRC" placeholder="masalan: tanlov natijasi asosida"></label>
        <button class="btn sm primary" id="kdRenew">${ico("check", 15)} Uzaytirish</button></div></details>
      <details class="kd-det"><summary>Attestatsiya / malaka oshirishni qayd etish</summary><div class="kd-form">
        <label>Tur<select id="kdTK">${Object.entries(M.trainings).map(([k, v]) => `<option value="${k}">${esc(v)}</option>`).join("")}</select></label>
        <label>Sana<input type="date" id="kdTD" max="${M.today}"></label><label>Natija<input id="kdTR" placeholder="masalan: lavozimga mos"></label>
        <label class="kd-wide">Izoh / sertifikat<input id="kdTN"></label>
        <button class="btn sm primary" id="kdTrain">${ico("check", 15)} Saqlash</button></div></details>
      <details class="kd-det"><summary>Ma'lumotlarni tahrirlash</summary><div class="kd-form">
        <label>Lavozim<input id="kdEP" value="${esc(d.position || "")}"></label><label>Stavka<input type="number" step="0.25" min="0.25" max="1.5" id="kdER" value="${d.rate}"></label>
        <label>Ma'lumoti<select id="kdEE">${M.education.map(e => `<option${e === d.education ? " selected" : ""}>${esc(e)}</option>`).join("")}</select></label>
        <label>Mutaxassisligi<input id="kdES" value="${esc(d.specialty || "")}"></label><label>Ilmiy daraja<input id="kdED" value="${esc(d.degree || "")}"></label>
        <label>Ilmiy unvon<input id="kdEU" value="${esc(d.academic_title || "")}"></label>
        <button class="btn sm primary" id="kdEdit">${ico("check", 15)} Saqlash</button></div></details>
      ${d.dismissal ? `<p class="kd-note">Bo'shatish jarayoni: ${esc(M.dis_status[d.dismissal.status] || d.dismissal.status)} · oxirgi ish kuni ${dmy(d.dismissal.last_day)}</p>`
        : `<button class="btn sm danger-ghost" id="kdDis">Bo'shatish arizasini qayd etish</button>`}</div>` : ""}
    <h4 class="kd-h4">Shartnoma tarixi</h4>${d.contract_log.length ? `<ul class="kd-mini">${d.contract_log.map(l => `<li>${dmy(l.ts)} · ${esc(l.action)} ${l.new_end ? "→ " + dmy(l.new_end) : ""} ${l.by_name ? `<small>${esc(l.by_name.split(":").pop())}</small>` : ""}</li>`).join("")}</ul>` : `<p class="muted tiny">Yozuv yo'q</p>`}
    <h4 class="kd-h4">Attestatsiya va malaka oshirish tarixi</h4>${d.trainings.length ? `<ul class="kd-mini">${d.trainings.map(l => `<li>${dmy(l.done_on)} · ${esc(M.trainings[l.kind] || l.kind)}${l.result ? " — " + esc(l.result) : ""}</li>`).join("")}</ul>` : `<p class="muted tiny">Yozuv yo'q</p>`}`;
  $("#kdBack").onclick = () => { KD.open = null; $("#kdBody .kd-wrap").classList.remove("has-open"); };
  $("#kdAbs").onclick = e => { e.preventDefault(); go("staffabs"); };
  const after = () => { kdFile(); };
  $("#kdRenew") && ($("#kdRenew").onclick = e => busy(e.currentTarget, async () => { if (await kdApi(`/api/hr/staff/${sid}/renew`, {contract_type: $("#kdRT").value, new_end: $("#kdRE").value || null, contract_no: $("#kdRN").value, note: $("#kdRC").value})) { toast("Shartnoma uzaytirildi"); after(); } }));
  $("#kdTrain") && ($("#kdTrain").onclick = e => busy(e.currentTarget, async () => { if (await kdApi(`/api/hr/staff/${sid}/training`, {kind: $("#kdTK").value, done_on: $("#kdTD").value, result: $("#kdTR").value, note: $("#kdTN").value})) { toast("Qayd etildi"); after(); } }));
  $("#kdEdit") && ($("#kdEdit").onclick = e => busy(e.currentTarget, async () => { if (await kdApi(`/api/hr/staff/${sid}`, {position: $("#kdEP").value, rate: +$("#kdER").value, education: $("#kdEE").value, specialty: $("#kdES").value, degree: $("#kdED").value, academic_title: $("#kdEU").value})) { toast("Saqlandi"); after(); } }));
  $("#kdDis") && ($("#kdDis").onclick = () => { KD.tab = "dismiss"; KD.disForm = {staff_id: sid, name: d.name}; renderKadrlar(); });
}

/* ---------- 3) ishga qabul: vakansiyalar va nomzodlar ---------- */
async function kdHire() {
  const M = KD.meta, V = await kdApi("/api/hr/vacancies"), full = M.mode === "full", rek = M.mode === "rektor";
  const st = s => ({tasdiqda: "warn", taklif: "info", ochiq: "ok", rad: "off", yopilgan: "off"})[s] || "";
  const cand = (v, k) => {
    let act = "";
    if (full && v.status === "ochiq") {
      if (k.stage === "ariza") act = `<button class="btn sm" data-stage="suhbat" data-k="${k.id}">Suhbatga</button><button class="btn sm ghost" data-stage="rad" data-k="${k.id}">Rad</button>`;
      else if (k.stage === "suhbat") act = `<button class="btn sm primary" data-stage="tanlandi" data-k="${k.id}">Tanlash (rektorga)</button><button class="btn sm ghost" data-stage="rad" data-k="${k.id}">Rad</button>`;
      else if (k.stage === "tasdiqlandi") act = `<span class="kd-form kd-inl"><input type="date" data-od="${k.id}" value="${M.today}" title="Ishga kirish sanasi">
          <select data-oc="${k.id}">${Object.entries(M.contract_types).map(([a, b]) => `<option value="${a}">${esc(b)}</option>`).join("")}</select>
          <input type="date" data-oe="${k.id}" title="Shartnoma tugash sanasi (bo'sh — 1 yil)"><button class="btn sm primary" data-order="${k.id}">Buyruq loyihasi</button></span>`;
    }
    if (full && k.stage === "qabul_qilindi" && !k.it) act = `<button class="btn sm primary" data-it="${k.id}">AT bo'limiga akkaunt so'rovi</button>`;
    if (rek && k.stage === "tanlandi") act = `<button class="btn sm primary" data-cd="approve" data-k="${k.id}">Tasdiqlash</button><button class="btn sm ghost" data-cd="reject" data-k="${k.id}">Rad etish</button>`;
    return `<li><div><b>${esc(k.name)}</b><small>${esc([k.education, k.degree !== "—" ? k.degree : ""].filter(Boolean).join(" · "))}${k.note ? " · " + esc(k.note) : ""}</small>
        <span class="kd-tag ${k.stage === "rad" ? "off" : k.stage === "qabul_qilindi" ? "ok" : k.stage === "tanlandi" ? "warn" : ""}">${esc(k.stage_label)}</span>
        ${k.order ? `<a href="#" class="kd-lnk" data-lnk='${esc(JSON.stringify(k.order.link))}'>Buyruq ${esc(k.order.reg_no)} · ${esc(k.order.status)}</a>` : ""}
        ${k.it ? `<a href="#" class="kd-lnk" data-lnk='${esc(JSON.stringify(k.it.link))}'>AT so'rovi ${esc(k.it.ref_no)}</a>` : ""}</div><div class="kd-act">${act}</div></li>`;
  };
  const vac = v => `<div class="card kd-vac"><div class="kd-vh"><div><b>${esc(v.position)}</b> <span class="muted">· ${esc(v.unit)} · ${kdN(v.rate)} stavka</span>
      <small>${esc(v.requirements || "")}${v.decision_note ? ` · Rektor: ${esc(v.decision_note)}` : ""}</small></div><span class="kd-tag ${st(v.status)}">${esc(v.status_label)}</span></div>
    ${v.candidates.length ? `<ul class="kd-cands">${v.candidates.map(k => cand(v, k)).join("")}</ul>` : `<p class="muted tiny">Nomzodlar yo'q</p>`}
    <div class="kd-act">${full && v.status === "taklif" ? `<button class="btn sm primary" data-vs="${v.id}">Rektorga yuborish</button>` : ""}
      ${rek && v.status === "tasdiqda" ? `<button class="btn sm primary" data-vd="approve" data-v="${v.id}">Vakansiyani tasdiqlash</button><button class="btn sm ghost" data-vd="reject" data-v="${v.id}">Rad etish</button>` : ""}
      ${full && v.status === "ochiq" ? `<button class="btn sm" data-addc="${v.id}">${ico("plus", 15)} Nomzod</button>` : ""}
      ${full && ["ochiq", "taklif", "tasdiqda"].includes(v.status) ? `<button class="btn sm ghost" data-vc="${v.id}">Yopish</button>` : ""}</div>
    <div class="kd-form" data-cf="${v.id}" hidden><label>F.I.Sh.<input data-cn></label><label>Telefon<input data-cp></label>
      <label>Ma'lumoti<select data-ce>${M.education.map(e => `<option>${esc(e)}</option>`).join("")}</select></label><label>Ilmiy daraja<input data-cg placeholder="—"></label>
      <label class="kd-wide">Izoh<input data-cx></label><button class="btn sm primary" data-cs="${v.id}">Qo'shish</button></div></div>`;
  const active = V.items.filter(v => ["taklif", "tasdiqda", "ochiq"].includes(v.status)), done = V.items.filter(v => !active.includes(v));
  const canNew = M.caps.propose;
  $("#kdBody").innerHTML = `${canNew ? `<div class="kd-bar"><button class="btn primary" id="kdVNew">${ico("plus", 16)}${full ? "Yangi vakansiya" : "Vakansiya taklif qilish"}</button>
      <span class="muted tiny">${full ? "Vakansiya rektor tasdig'idan keyin ochiladi; nomzod tanlangach — yana rektor tasdig'i, so'ng «Buyruqlar»da ishga qabul buyrug'i." : "Taklif Kadrlar bo'limiga tushadi, u rektorga yuboradi."}</span></div>
    <div class="card kd-form kd-newv" id="kdVF" ${KD.vacForm ? "" : "hidden"}>
      ${full ? `<label>Bo'linma<select id="kdVU">${M.units.map(u => `<option value="${esc(u.key)}">${esc(u.name)}</option>`).join("")}</select></label>` : ""}
      <label>Lavozim<input id="kdVP" placeholder="masalan: Katta o'qituvchi"></label><label>Stavka<input id="kdVR" type="number" step="0.25" min="0.25" max="1.5" value="1"></label>
      <label class="kd-wide">Talablar<input id="kdVQ" placeholder="ma'lumoti, staj, til bilish darajasi"></label><label class="kd-wide">Asos / izoh<input id="kdVN"></label>
      <button class="btn sm primary" id="kdVS">${full ? "Rektorga yuborish" : "Taklif yuborish"}</button></div>` : ""}
    ${active.length ? active.map(vac).join("") : kdEmpty("Faol vakansiya yo'q")}
    ${done.length ? `<details class="kd-det"><summary>Yopilgan va rad etilganlar (${done.length})</summary>${done.map(vac).join("")}</details>` : ""}`;
  const B = $("#kdBody");
  $("#kdVNew") && ($("#kdVNew").onclick = () => { KD.vacForm = !KD.vacForm; $("#kdVF").hidden = !KD.vacForm; });
  $("#kdVS") && ($("#kdVS").onclick = e => busy(e.currentTarget, async () => {
    const r = await kdApi("/api/hr/vacancies", {unit_key: $("#kdVU") ? $("#kdVU").value : "", position: $("#kdVP").value, rate: +$("#kdVR").value, requirements: $("#kdVQ").value, note: $("#kdVN").value});
    if (r) { toast(r.status === "taklif" ? "Taklif Kadrlar bo'limiga yuborildi" : "Vakansiya rektor tasdig'iga yuborildi"); KD.vacForm = false; kdHire(); } }));
  B.querySelectorAll("[data-lnk]").forEach(a => a.onclick = e => { e.preventDefault(); kdLink(JSON.parse(a.dataset.lnk)); });
  B.querySelectorAll("[data-stage]").forEach(b => b.onclick = () => busy(b, async () => { if (await kdApi(`/api/hr/candidates/${b.dataset.k}/stage`, {stage: b.dataset.stage})) kdHire(); }));
  B.querySelectorAll("[data-addc]").forEach(b => b.onclick = () => { const f = B.querySelector(`[data-cf="${b.dataset.addc}"]`); f.hidden = !f.hidden; });
  B.querySelectorAll("[data-cs]").forEach(b => b.onclick = () => busy(b, async () => { const f = b.closest(".kd-form");
    if (await kdApi(`/api/hr/vacancies/${b.dataset.cs}/candidates`, {full_name: f.querySelector("[data-cn]").value, phone: f.querySelector("[data-cp]").value, education: f.querySelector("[data-ce]").value, degree: f.querySelector("[data-cg]").value, note: f.querySelector("[data-cx]").value})) { toast("Nomzod qo'shildi"); kdHire(); } }));
  B.querySelectorAll("[data-vs]").forEach(b => b.onclick = () => busy(b, async () => { if (await kdApi(`/api/hr/vacancies/${b.dataset.vs}/submit`, {})) { toast("Rektorga yuborildi"); kdHire(); } }));
  B.querySelectorAll("[data-vc]").forEach(b => b.onclick = () => { if (!arm(b, "Ha, yopish")) return; busy(b, async () => { if (await kdApi(`/api/hr/vacancies/${b.dataset.vc}/close`, {})) kdHire(); }); });
  const decide = (url, b) => { const rej = b.dataset.vd === "reject" || b.dataset.cd === "reject";
    const send = (btn, note) => busy(btn, async () => { if (await kdApi(url, {decision: rej ? "reject" : "approve", note})) { toast(rej ? "Rad etildi" : "Tasdiqlandi"); kdHire(); } });
    if (!rej) { if (arm(b, "Ha, tasdiqlash")) send(b, ""); return; }
    if (b.nextElementSibling?.classList.contains("kd-rej")) return b.nextElementSibling.querySelector("input").focus();
    b.insertAdjacentHTML("afterend", `<span class="kd-rej"><input placeholder="Rad etish sababi" aria-label="Rad etish sababi"><button class="btn sm primary">Rad etish</button></span>`);
    const f = b.nextElementSibling, inp = f.querySelector("input"); inp.focus();
    f.querySelector("button").onclick = e => { const n = inp.value.trim(); if (!n) { inp.focus(); toast("Sababini yozing"); return; } send(e.currentTarget, n); }; };
  B.querySelectorAll("[data-vd]").forEach(b => b.onclick = () => decide(`/api/hr/vacancies/${b.dataset.v}/decide`, b));
  B.querySelectorAll("[data-cd]").forEach(b => b.onclick = () => decide(`/api/hr/candidates/${b.dataset.k}/decide`, b));
  B.querySelectorAll("[data-order]").forEach(b => b.onclick = () => busy(b, async () => { const k = b.dataset.order;
    const r = await kdApi(`/api/hr/candidates/${k}/order`, {date_from: B.querySelector(`[data-od="${k}"]`).value, contract_type: B.querySelector(`[data-oc="${k}"]`).value, contract_end: B.querySelector(`[data-oe="${k}"]`).value || null});
    if (r) { toast(`Buyruq loyihasi tuzildi — «Buyruqlar»da imzoga yuboring`); kdHire(); } }));
  B.querySelectorAll("[data-it]").forEach(b => b.onclick = () => busy(b, async () => { const r = await kdApi(`/api/hr/candidates/${b.dataset.it}/it-request`, {}); if (r) { toast(`AT bo'limiga so'rov yuborildi: ${r.thread.ref_no}`); kdHire(); } }));
}

/* ---------- 4) ishdan bo'shatish ---------- */
async function kdDismiss() {
  const M = KD.meta, D = await kdApi("/api/hr/dismissals"), F = KD.disForm;
  const item = d => `<div class="card kd-vac"><div class="kd-vh"><div><b>${esc(d.name)}</b> <span class="muted">· ${esc(d.position || "")} · ${esc(d.unit)}</span>
      <small>Asos: ${esc(d.reason)} · ariza ${dmy(d.app_date)} · oxirgi ish kuni <b>${dmy(d.last_day)}</b>${d.accounts.length ? ` · tizim akkaunti: ${d.accounts.some(a => a.active) ? "faol" : "bloklangan"}` : ""}</small></div>
      <span class="kd-tag ${d.status === "buyruq" ? "warn" : ""}">${esc(d.status_label)} · ${d.done}/${d.checklist.length}</span></div>
    <ul class="kd-check">${d.checklist.map(c => `<li><label><input type="checkbox" data-ck="${c.key}" data-d="${d.id}" ${c.done ? "checked" : ""} ${d.status === "buyruq" ? "disabled" : ""}> ${esc(c.label)}</label></li>`).join("")}</ul>
    <div class="kd-act">
      ${d.it ? `<a href="#" class="kd-lnk" data-lnk='${esc(JSON.stringify(d.it.link))}'>AT so'rovi ${esc(d.it.ref_no)}</a>` : `<button class="btn sm" data-dit="${d.id}">AT bo'limiga bloklash so'rovi</button>`}
      ${d.order ? `<a href="#" class="kd-lnk" data-lnk='${esc(JSON.stringify(d.order.link))}'>Buyruq ${esc(d.order.reg_no)} · ${esc(d.order.status)}</a>`
        : `<button class="btn sm primary" data-dord="${d.id}" ${d.done < d.checklist.length ? `disabled title="Avval topshirish varaqasini to'ldiring"` : ""}>Buyruq loyihasi</button>
           <button class="btn sm ghost" data-dcan="${d.id}">Ariza qaytarib olindi</button>`}</div></div>`;
  $("#kdBody").innerHTML = `<div class="kd-bar"><span class="muted tiny">Tartib: ariza → topshirish varaqasi (akkauntlar, moddiy boyliklar, kutubxona, hujjatlar, hisob-kitob) → «Buyruqlar»da buyruq → rektor imzosi.
      Yangi ariza — «Xodimlar» bo'limida xodim kartasidan.</span></div>
    ${F ? `<div class="card kd-form kd-newv"><b class="kd-wide">Bo'shatish arizasi: ${esc(F.name)}</b>
      <label class="kd-wide">Asos<select id="kdDR"><option>O'z xohishiga ko'ra (ariza)</option><option>Tomonlarning kelishuviga ko'ra</option><option>Mehnat shartnomasi muddati tugaganligi sababli</option><option>Pensiyaga chiqishi munosabati bilan</option></select></label>
      <label>Ariza sanasi<input type="date" id="kdDA" value="${M.today}" max="${M.today}"></label><label>Oxirgi ish kuni<input type="date" id="kdDL"></label>
      <button class="btn sm primary" id="kdDS">Qayd etish</button><button class="btn sm ghost" id="kdDX">Bekor</button></div>` : ""}
    ${D.items.length ? D.items.map(item).join("") : kdEmpty("Ochiq bo'shatish jarayoni yo'q")}`;
  const B = $("#kdBody");
  $("#kdDX") && ($("#kdDX").onclick = () => { KD.disForm = false; kdDismiss(); });
  $("#kdDS") && ($("#kdDS").onclick = e => busy(e.currentTarget, async () => { if (await kdApi("/api/hr/dismissals", {staff_id: F.staff_id, reason: $("#kdDR").value, app_date: $("#kdDA").value, last_day: $("#kdDL").value})) { toast("Ariza qayd etildi — topshirish varaqasini to'ldiring"); KD.disForm = false; kdDismiss(); } }));
  B.querySelectorAll("[data-lnk]").forEach(a => a.onclick = e => { e.preventDefault(); kdLink(JSON.parse(a.dataset.lnk)); });
  B.querySelectorAll("[data-ck]").forEach(c => c.onchange = async () => { c.disabled = true; const r = await kdApi(`/api/hr/dismissals/${c.dataset.d}/check`, {item: c.dataset.ck, done: c.checked}); if (!r) c.checked = !c.checked; kdDismiss(); });
  B.querySelectorAll("[data-dit]").forEach(b => b.onclick = () => busy(b, async () => { const r = await kdApi(`/api/hr/dismissals/${b.dataset.dit}/it-request`, {}); if (r) { toast(`AT bo'limiga yuborildi: ${r.thread.ref_no}`); kdDismiss(); } }));
  B.querySelectorAll("[data-dord]").forEach(b => b.onclick = () => { if (!arm(b, "Ha, buyruq loyihasi")) return; busy(b, async () => { if (await kdApi(`/api/hr/dismissals/${b.dataset.dord}/order`, {})) { toast("Buyruq loyihasi tuzildi — «Buyruqlar»da imzoga yuboring"); kdDismiss(); } }); });
  B.querySelectorAll("[data-dcan]").forEach(b => b.onclick = () => { const id = b.dataset.dcan; b.closest(".kd-vac").classList.add("kd-fade");
    undoToast("Bo'shatish jarayoni bekor qilinadi", async () => { await kdApi(`/api/hr/dismissals/${id}/cancel`, {}); kdDismiss(); }, {onUndo: () => b.closest(".kd-vac")?.classList.remove("kd-fade")}); });
}

/* ---------- 5) shtat jadvali ---------- */
async function kdStaffing() {
  const M = KD.meta, full = M.mode === "full";
  const S = await kdApi(`/api/hr/staffing${full && KD.unit ? "?unit=" + encodeURIComponent(KD.unit) : ""}`);
  $("#kdBody").innerHTML = `<div class="kd-kpis">${kdKpi(kdN(S.total.plan), "reja stavka", "shtat jadvali bo'yicha")}${kdKpi(kdN(S.total.fact), "amalda band", "faol shaxsiy ishlar stavkasi")}
      ${kdKpi(kdN(S.total.vacant), "bo'sh stavka", "vakansiya ochish uchun asos", S.total.vacant ? "warn" : "")}</div>
    ${M.units.length ? `<div class="kd-bar"><select id="kdSU"><option value="">Barcha bo'linmalar</option>${M.units.map(u => `<option value="${esc(u.key)}"${KD.unit === u.key ? " selected" : ""}>${esc(u.name)}</option>`).join("")}</select></div>` : ""}
    <div class="card kd-card"><div class="kd-scroll"><table class="kd-tb"><thead><tr><th>Bo'linma</th><th>Lavozim</th><th>Reja</th><th>Amalda</th><th>Xodim</th><th>Bo'sh</th>${full ? "<th></th>" : ""}</tr></thead><tbody>
    ${S.items.filter(r => !KD.unit || r.unit_key === KD.unit).map(r => `<tr><td>${esc(r.unit)}</td><td>${esc(r.position || "")}</td>
      <td>${full ? `<input type="number" class="kd-num" step="0.25" min="0" value="${r.plan}" data-u="${esc(r.unit_key)}" data-p="${esc(r.position || "")}">` : kdN(r.plan)}</td>
      <td>${kdN(r.fact)}${r.over ? ` <span class="kd-tag bad">+${kdN(r.over)} ortiq</span>` : ""}</td><td>${r.people}</td><td class="${r.vacant ? "warn" : ""}">${kdN(r.vacant)}</td>
      ${full ? `<td><button class="btn sm ghost" data-ps>Saqlash</button></td>` : ""}</tr>`).join("")}</tbody></table></div></div>`;
  $("#kdSU") && ($("#kdSU").onchange = e => { KD.unit = e.target.value; kdStaffing(); });
  $("#kdBody").querySelectorAll("[data-ps]").forEach(b => b.onclick = () => busy(b, async () => { const i = b.closest("tr").querySelector("input");
    if (await kdApi("/api/hr/staffing", {unit_key: i.dataset.u, position: i.dataset.p, plan: +i.value})) { toast("Shtat jadvali yangilandi"); kdStaffing(); } }));
}
