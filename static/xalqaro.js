/* =====================================================================
   «Xalqaro hamkorlik» (app/xalqaro.py, /api/xalqaro).
     Umumiy:        shartnomalar holati, tugayotganlar (90/30 kun), KPI reja/fakt, mobillik, vizalar, delegatsiyalar.
     Shartnomalar:  qoralama → yuridik ko'rik → rektor imzosi → amalda → uzaytirish; tadbirlar va KPI.
     Mobillik:      tanlov e'loni, arizalar (avtomatik mezon tekshiruvi), komissiya bali, saralash, jo'nash/qaytish.
     Xorijiy talabalar: viza va ro'yxatga olish muddatlari.   Delegatsiyalar: tashriflar jurnali.
     Kredit tan olish: Akademik bo'lim navbati.
   Ruxsat va ko'lam serverda; rektor/kengashga talaba ismlari yuborilmaydi.
   Global: renderXalqaro() — go("xalqaro") o'rami (pastda) chaqiradi. app.js yordamchilari: $, esc, fmt, toast, arm, undoToast, locked, showLogin, ME.
   ===================================================================== */
const XQ = {meta: null, tab: null, agFilter: "", call: null};
if (!document.querySelector('link[href="xalqaro.css"]')) document.head.insertAdjacentHTML("beforeend", '<link rel="stylesheet" href="xalqaro.css">');
if (typeof ICONS === "object" && !ICONS.globe) ICONS.globe = '<circle cx="12" cy="12" r="10"/><path d="M2 12h20"/><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/>';
try { const s = document.querySelector('#nav a[data-v="xalqaro"] svg'); if (s && !s.innerHTML.trim()) { s.remove(); typeof hydrateIcons === "function" && hydrateIcons(); } } catch (e) {}

const XQ_TABS = {overview: "Umumiy", agreements: "Shartnomalar", exchange: "Akademik mobillik", foreign: "Xorijiy talabalar", delegations: "Delegatsiyalar", credits: "Kredit tan olish"};
const xqD = s => { s = String(s || "").slice(0, 10); return s.length === 10 ? `${s.slice(8, 10)}.${s.slice(5, 7)}.${s.slice(0, 4)}` : "—"; };
const xqChip = (t, cls = "") => `<span class="xq-chip ${cls}">${esc(t)}</span>`;
const xqKpi = (label, val, sub = "", cls = "") => `<div class="xq-kpi ${cls}"><span>${esc(label)}</span><b>${val}</b>${sub ? `<small>${sub}</small>` : ""}</div>`;
const xqToday = () => XQ.meta?.today || new Date().toISOString().slice(0, 10);
const xqAgCls = s => ({faol: "ok", imzoda: "info", yuridik: "warn", qaytarildi: "bad", tugagan: "bad", bekor: ""})[s] || "";
const xqAppCls = s => ({saralandi: "ok", ketdi: "info", qaytdi: "ok", zaxira: "warn", mos_emas: "bad", rad: "", voz_kechdi: ""})[s] || "";
const xqDays = n => n == null ? "" : n < 0 ? `${-n} kun o'tdi` : `${n} kun qoldi`;

async function xqApi(url, body, method) {
  const r = await fetch(url, {method: method || (body === undefined ? "GET" : "POST"), credentials: "same-origin", headers: {"Content-Type": "application/json"},
                              body: body === undefined ? undefined : JSON.stringify(body)});
  if (r.status === 401) { showLogin(); throw new Error("auth"); }
  const d = await r.json().catch(() => ({}));
  if (!r.ok) {
    const det = d.detail; const m = d.message || (typeof det === "string" ? det : Array.isArray(det) ? "Maydonlarni tekshiring" : det?.message) || "Xatolik yuz berdi";
    if (body !== undefined) { toast(m); return null; }
    const e = new Error(r.status === 403 ? "denied" : "api"); e.msg = m; throw e;
  }
  return d;
}
function xqTable(cols, rows, {rowCls = () => "", empty = "Ma'lumot yo'q"} = {}) {
  if (!rows.length) return `<div class="xq-empty">${esc(empty)}</div>`;
  return `<div class="tw"><table class="xq-t"><thead><tr>${cols.map(c => `<th>${esc(c[0])}</th>`).join("")}</tr></thead><tbody>` +
    rows.map(r => `<tr class="${rowCls(r)}">${cols.map(c => `<td data-l="${esc(c[0])}" class="${c[2] || ""}"><div>${c[1](r) ?? ""}</div></td>`).join("")}</tr>`).join("") + `</tbody></table></div>`;
}
function xqModal(title, html, onOk, okText = "Saqlash") {
  const bg = document.createElement("div"); bg.className = "xq-modal-bg";
  bg.innerHTML = `<div class="xq-modal" role="dialog" aria-modal="true" aria-label="${esc(title)}"><h3>${esc(title)}</h3>${html}
    <div class="xq-acts end"><button type="button" class="btn ghost" data-x>${onOk ? "Bekor qilish" : "Yopish"}</button>${onOk ? `<button type="button" class="btn primary" data-ok>${esc(okText)}</button>` : ""}</div></div>`;
  document.body.appendChild(bg);
  const opener = document.activeElement;
  const close = () => { bg.remove(); opener?.focus?.({preventScroll: true}); };
  bg.addEventListener("mousedown", e => { if (e.target === bg) close(); });
  bg.addEventListener("click", e => { if (e.target.closest("[data-x]")) close(); });
  bg.addEventListener("keydown", e => { if (e.key === "Escape") close(); });
  const ok = bg.querySelector("[data-ok]");
  if (ok) ok.onclick = async () => { ok.disabled = true; try { if (await onOk(bg)) close(); } finally { if (ok.isConnected) ok.disabled = false; } };
  setTimeout(() => bg.querySelector("input,select,textarea,button")?.focus(), 30);
  return bg;
}
const xqV = (root, id) => root.querySelector("#" + id)?.value?.trim() ?? "";

/* ---------- asosiy ko'rinish ---------- */
async function renderXalqaro() {
  const el = $("#v-xalqaro");
  if (!el.innerHTML) el.innerHTML = `<p class="muted">Yuklanmoqda…</p>`;
  XQ.meta = await xqApi("/api/xalqaro/meta");
  if (!XQ.tab || !XQ.meta.tabs.includes(XQ.tab)) XQ.tab = XQ.meta.tabs[0];
  const sub = {xalqaro: "Shartnomalar hayotiy sikli, mobillik tanlovlari, xorijiy talabalar va delegatsiyalar.",
    yuridik: "Yuridik ko'rik navbati: xalqaro shartnomalar loyihalari bo'yicha xulosa (mos / e'tiroz).",
    rektor: "Imzo navbati va jamlangan ko'rsatkichlar. Talabalar ismlari ko'rsatilmaydi.",
    prorektor_ilmiy: "Kurator: ko'rish va mobillik komissiyasi bali.", kengash: "Jamlangan ko'rsatkichlar.",
    akademik: "Xorijda o'qib qaytgan talabalar kreditlarini tan olish navbati."}[XQ.meta.role] || "";
  el.innerHTML = `<div class="xq-head"><div><h2>Xalqaro hamkorlik</h2><span class="muted">${esc(sub)}</span></div></div>
    ${XQ.meta.tabs.length > 1 ? `<div class="xq-tabs" role="tablist">${XQ.meta.tabs.map(t => `<button type="button" role="tab" data-tab="${t}" class="${t === XQ.tab ? "on" : ""}" aria-selected="${t === XQ.tab}">${esc(XQ_TABS[t])}</button>`).join("")}</div>` : ""}
    <div id="xqBody"><p class="muted">Yuklanmoqda…</p></div>`;
  el.querySelectorAll("[data-tab]").forEach(b => b.onclick = () => { XQ.tab = b.dataset.tab; XQ.call = null; renderXalqaro(); });
  await xqTab();
}
async function xqTab() {
  const box = $("#xqBody");
  if (!box) return;   /* parallel qayta chizish — eski chaqiruv */
  try { await ({overview: xqOverview, agreements: xqAgreements, exchange: xqExchange, foreign: xqForeign, delegations: xqDelegations, credits: xqCredits})[XQ.tab](box); }
  catch (e) { if (e?.message === "auth") return; box.innerHTML = e?.message === "denied" ? locked("Bu bo'lim") : `<div class="card xq-card"><p>${esc(e?.msg || "Ma'lumotni yuklab bo'lmadi")}</p></div>`; }
}
const xqReload = () => xqTab();

/* =================== Umumiy =================== */
async function xqOverview(box) {
  const o = await xqApi("/api/xalqaro/overview"), A = o.agreements, K = o.kpi, M = o.mobility, F = o.foreign;
  const pct = (f, p) => p ? `${Math.round(100 * f / p)}%` : "—";
  box.innerHTML = `<div class="xq-kpis">
      ${xqKpi("Amaldagi shartnomalar", fmt(A.active), `${A.countries} ta davlat`)}
      ${xqKpi("Tugayotganlar (90 kun)", fmt(A.expiring.length), `${A.expiring.filter(x => x.alert === "high").length} tasi 30 kun ichida`, A.expiring.some(x => x.alert === "high" && !x.renewal) ? "bad" : A.expiring.length ? "warn" : "ok")}
      ${xqKpi("Navbatda", fmt(A.queue), "yuridik ko'rik va rektor imzosi", A.queue ? "warn" : "")}
      ${xqKpi("Almashinuv: fakt / reja", `${fmt(K.exchange_fact)} / ${fmt(K.exchange_plan)}`, `bajarilish ${pct(K.exchange_fact, K.exchange_plan)}`)}
      ${xqKpi("Qo'shma dasturlar", `${fmt(K.joint_fact)} / ${fmt(K.joint_plan)}`, `${K.no_activity} ta shartnomada faoliyat yo'q`, K.no_activity ? "warn" : "")}
      ${xqKpi("Xorijda (mobillik)", fmt(M.abroad), `${M.credit_wait} ta kredit tan olish kutilmoqda`)}
      ${xqKpi("Xorijiy talabalar", fmt(F.total), `${F.alerts} ta viza/ro'yxat muddati ≤30 kun yoki o'tgan`, F.alerts ? "bad" : "ok")}
      ${xqKpi("Delegatsiyalar", fmt(o.delegations.upcoming), `kutilmoqda · bu yil ${o.delegations.year} ta o'tkazildi`)}
    </div>
    <div class="xq-grid">
      <div class="card xq-card"><h3>Tugayotgan shartnomalar</h3><p class="muted">Ogohlantirish: ${XQ.meta.rules.warn90} va ${XQ.meta.rules.warn30} kun oldin. Uzaytirish — yangi qoralama, yuridik ko'rik va imzo orqali.</p>
        ${xqTable([["Hamkor", r => `<b>${esc(r.partner_name)}</b><small>${esc(r.country)} · ${esc(r.kind)}</small>`],
                   ["Tugaydi", r => `${xqD(r.end)}<small>${xqDays(r.days_left)}</small>`, "num"],
                   ["Uzaytirish", r => r.renewal ? xqChip(XQ.meta.labels.agreement[r.renewal.status] || r.renewal.status, "info") : xqChip("boshlanmagan", r.alert === "high" ? "bad" : "warn")]],
                  A.expiring, {empty: "90 kun ichida tugaydigan shartnoma yo'q"})}</div>
      <div class="card xq-card"><h3>Mobillik tanlovlari</h3><p class="muted">Arizalar va saralash holati (jamlangan).</p>
        ${xqTable([["Tanlov", r => `<b>${esc(r.title)}</b><small>${esc(r.country)} · ${r.seats} o'rin · muddat ${xqD(r.deadline)}</small>${xqChip(r.status_label, r.status === "ochiq" ? "info" : r.status === "komissiya" ? "warn" : "")}`],
                   ["Arizalar", r => `<b>${fmt(r.stats.jami || 0)}</b><small>${r.stats.saralandi || 0} saralandi</small><small>${r.stats.ketdi || 0} xorijda · ${r.stats.qaytdi || 0} qaytdi</small>`]],
                  M.calls, {empty: "Tanlovlar yo'q"})}</div>
      <div class="card xq-card"><h3>Shartnomalar holati</h3>
        <div class="xq-chips">${A.by_status.map(s => xqChip(`${s.label}: ${s.n}`, xqAgCls(s.status))).join(" ")}</div>
        <h3 style="margin-top:14px">Xorijiy talabalar — davlatlar</h3>
        <div class="xq-chips">${F.by_country.map(c => xqChip(`${c.country}: ${c.n}`)).join(" ") || "—"}</div></div>
    </div>`;
}

/* =================== Shartnomalar =================== */
async function xqAgreements(box) {
  const C = XQ.meta.can, L = XQ.meta.labels.agreement;
  const f = XQ.agFilter;
  const d = await xqApi("/api/xalqaro/agreements" + (f ? "?status=" + encodeURIComponent(f) : ""));
  const filters = [["", "Hammasi"], ["navbat", "Navbatda"], ["tugamoqda", "Tugamoqda"], ["faol", "Amalda"], ["tugagan", "Tugagan"]];
  const hint = C.legal ? "Sizning navbatingiz — «Yuridik ko'rikda» holatidagilar." : C.sign ? "Sizning navbatingiz — «Rektor imzosida» holatidagilar." : "";
  box.innerHTML = `<div class="xq-bar"><div class="xq-seg">${filters.map(([k, t]) => `<button type="button" data-f="${k}" class="${k === f ? "on" : ""}">${t}</button>`).join("")}</div>
      <span class="grow muted">${esc(hint)}</span>${C.edit ? `<button class="btn sm primary" type="button" id="xqNewAg">Yangi shartnoma</button>` : ""}</div>
    <div class="card xq-card">${xqTable([
      ["Hamkor", r => `<button type="button" class="xq-link" data-ag="${r.id}">${esc(r.partner_name)}</button><small>${esc(r.country)} · ${esc(r.kind)}${r.renew_of ? " · uzaytirish" : ""}</small>`],
      ["Holat", r => xqChip(r.status_label, xqAgCls(r.status)) + (r.alert ? " " + xqChip(r.alert === "high" ? "≤30 kun" : "≤90 kun", r.alert === "high" ? "bad" : "warn") : "")],
      ["Muddat", r => `${xqD(r.start)} — ${xqD(r.end)}<small>${r.status === "faol" ? xqDays(r.days_left) : ""}</small>`, "num"],
      ["KPI (fakt/reja)", r => `almashinuv ${r.kpi.exchange_fact}/${r.kpi.exchange_plan}${r.kpi.joint_plan ? `<small>qo'shma dastur ${r.kpi.joint_fact}/${r.kpi.joint_plan}</small>` : ""}`, "num"]],
      d.items, {rowCls: r => (C.legal && r.status === "yuridik") || (C.sign && r.status === "imzoda") ? "xq-mine" : "", empty: "Bu filtr bo'yicha shartnoma yo'q"})}</div>`;
  box.querySelectorAll("[data-f]").forEach(b => b.onclick = () => { XQ.agFilter = b.dataset.f; xqAgreements(box); });
  box.querySelectorAll("[data-ag]").forEach(b => b.onclick = () => xqAgDetail(+b.dataset.ag));
  const nb = $("#xqNewAg"); if (nb) nb.onclick = () => xqAgForm();
}
function xqAgForm(a) {
  const K = XQ.meta.kinds, t = xqToday();
  xqModal(a ? "Shartnomani tahrirlash" : "Yangi shartnoma (qoralama)", `
    <label>Hamkor tashkilot<input id="f1" value="${esc(a?.partner_name || "")}" maxlength="200"></label>
    <div class="row2"><label>Davlat<input id="f2" value="${esc(a?.country || "")}" maxlength="80"></label>
      <label>Turi<select id="f3">${K.map(k => `<option ${k === a?.kind ? "selected" : ""}>${esc(k)}</option>`).join("")}</select></label></div>
    <label>Sarlavha<input id="f4" value="${esc(a?.title || "")}" placeholder="Bo'sh qolsa — turi bo'yicha"></label>
    <div class="row2"><label>Boshlanish<input id="f5" type="date" value="${esc(a?.start || t)}"></label><label>Tugash<input id="f6" type="date" value="${esc(a?.end || "")}"></label></div>
    <div class="row2"><label>KPI: almashinuv (kishi)<input id="f7" type="number" min="0" value="${a?.kpi_exchange ?? 5}"></label>
      <label>KPI: qo'shma dastur (talaba)<input id="f8" type="number" min="0" value="${a?.kpi_joint ?? 0}"></label></div>
    <label>Izoh<textarea id="f9" maxlength="1000">${esc(a?.note || "")}</textarea></label>`, async m => {
      const body = {partner_name: xqV(m, "f1"), country: xqV(m, "f2"), kind: xqV(m, "f3"), title: xqV(m, "f4"), start: xqV(m, "f5"), end: xqV(m, "f6"),
                    kpi_exchange: +xqV(m, "f7") || 0, kpi_joint: +xqV(m, "f8") || 0, note: xqV(m, "f9"), partner_id: a?.partner_id || null};
      const r = await xqApi(a ? `/api/xalqaro/agreements/${a.id}` : "/api/xalqaro/agreements", body, a ? "PUT" : "POST");
      if (!r) return false;
      toast(a ? "Saqlandi" : "Qoralama yaratildi"); xqReload(); if (!a) xqAgDetail(r.id); else xqAgDetail(a.id);
      return true;
    });
}
async function xqAgDetail(id) {
  const a = await xqApi(`/api/xalqaro/agreements/${id}`), C = XQ.meta.can, st = a.status;
  const acts = [];
  if (C.edit && ["qoralama", "qaytarildi"].includes(st)) acts.push(`<button class="btn sm" data-a="edit">Tahrirlash</button>`, `<button class="btn sm primary" data-a="submit">Yuridik ko'rikka yuborish</button>`, `<button class="btn sm ghost" data-a="cancel">Bekor qilish</button>`);
  if (C.legal && st === "yuridik") acts.push(`<button class="btn sm primary" data-a="legal-ok">Xulosa: mos</button>`, `<button class="btn sm" data-a="legal-no">E'tiroz bildirish</button>`);
  if (C.sign && st === "imzoda") acts.push(`<button class="btn sm primary" data-a="sign">Imzolash</button>`, `<button class="btn sm" data-a="return">Qaytarish</button>`);
  if (C.sign && st === "faol") acts.push(`<button class="btn sm ghost" data-a="terminate">Muddatidan oldin bekor qilish</button>`);
  if (C.edit && ["faol", "tugagan"].includes(st) && !a.renewal) acts.push(`<button class="btn sm ${a.alert || st === "tugagan" ? "primary" : ""}" data-a="renew">Uzaytirish</button>`);
  if (C.edit && ["faol", "tugagan", "uzaytirildi"].includes(st)) acts.push(`<button class="btn sm" data-a="activity">Tadbir qo'shish</button>`);
  const m = xqModal(a.partner_name, `
    <div class="xq-chips">${xqChip(a.status_label, xqAgCls(st))} ${a.alert ? xqChip(xqDays(a.days_left), a.alert === "high" ? "bad" : "warn") : ""} ${a.renewal ? xqChip(`Uzaytirish #${a.renewal.id}: ${XQ.meta.labels.agreement[a.renewal.status]}`, "info") : ""}</div>
    <dl class="xq-dl"><dt>Davlat / turi</dt><dd>${esc(a.country)} · ${esc(a.kind)}</dd><dt>Sarlavha</dt><dd>${esc(a.title || "—")}</dd>
      <dt>Muddat</dt><dd>${xqD(a.start)} — ${xqD(a.end)}</dd>
      ${a.previous ? `<dt>Oldingi shartnoma</dt><dd><button type="button" class="xq-link" data-prev="${a.previous.id}">#${a.previous.id}</button> · ${xqD(a.previous.start)} — ${xqD(a.previous.end)}</dd>` : ""}
      <dt>Yuridik xulosa</dt><dd>${a.legal_by ? `${esc(a.legal_note || "")} <small class="muted">${esc(a.legal_by)} · ${xqD(a.legal_at)}</small>` : "—"}</dd>
      <dt>Imzo</dt><dd>${a.signed_by ? `${esc(a.signed_by)} · ${xqD(a.signed_at)}` : "—"}</dd>
      <dt>KPI</dt><dd>almashinuv ${a.kpi.exchange_fact} / ${a.kpi.exchange_plan} · qo'shma dastur ${a.kpi.joint_fact} / ${a.kpi.joint_plan}</dd>
      ${a.note ? `<dt>Izoh</dt><dd>${esc(a.note)}</dd>` : ""}</dl>
    ${acts.length ? `<div class="xq-acts">${acts.join("")}</div>` : ""}
    <h4>Tadbirlar</h4>${a.activities.length ? `<ul class="xq-list">${a.activities.map(x => `<li><b>${esc(x.title)}</b> <small class="muted">${esc(x.kind_label)} · ${xqD(x.date)}${x.count ? ` · ${x.count}` : ""}</small></li>`).join("")}</ul>` : `<p class="muted">Tadbir qayd etilmagan</p>`}
    <h4>Tarix</h4><ul class="xq-list">${a.log.map(l => `<li>${esc(l.action)}${l.note ? ` — ${esc(l.note)}` : ""} <small class="muted">${esc(l.user_name || "")} · ${xqD(l.at)}</small></li>`).join("")}</ul>`);
  m.querySelector(".xq-modal").classList.add("wide");
  const done = (t) => { toast(t); m.remove(); xqReload(); };
  const pv = m.querySelector("[data-prev]"); if (pv) pv.onclick = () => { m.remove(); xqAgDetail(+pv.dataset.prev); };
  m.querySelectorAll("[data-a]").forEach(b => b.onclick = async () => {
    const k = b.dataset.a, P = `/api/xalqaro/agreements/${id}`;
    if (k === "edit") { m.remove(); return xqAgForm(a); }
    if (k === "submit") { if (await xqApi(P + "/submit", {})) done("Yuridik bo'limga yuborildi"); return; }
    if (k === "legal-ok") { if (!arm(b, "Ha, mos")) return; if (await xqApi(P + "/legal", {decision: "mos", note: ""})) done("Xulosa: mos — rektor imzosiga o'tdi"); return; }
    if (k === "sign") { if (!arm(b, "Ha, imzolash")) return; if (await xqApi(P + "/sign", {})) done("Shartnoma imzolandi va hamkorlar reyestriga yozildi"); return; }
    if (k === "renew") { const r = await xqApi(P + "/renew", {}); if (r) { m.remove(); toast("Uzaytirish qoralamasi yaratildi"); xqReload(); xqAgDetail(r.id); } return; }
    if (k === "cancel") { m.remove(); undoToast("Qoralama bekor qilinmoqda…", async () => { if (await xqApi(P + "/cancel", {note: ""})) { toast("Bekor qilindi"); xqReload(); } }); return; }
    const noteAsk = {"legal-no": ["E'tiroz", "Qaysi band va nima o'zgarishi kerak", "legal", n => ({decision: "etiroz", note: n}), "Qaytarildi"],
                     "return": ["Qaytarish sababi", "Masalan: moliyaviy majburiyatlar bandi", "return", n => ({note: n}), "Qaytarildi"],
                     "terminate": ["Bekor qilish sababi", "Hamkor tashabbusi, majburiyatlar bajarilmadi…", "cancel", n => ({note: n}), "Shartnoma bekor qilindi"]}[k];
    if (noteAsk) return xqModal(noteAsk[0], `<label>${esc(noteAsk[1])}<textarea id="n1" maxlength="1000"></textarea></label>`, async mm => {
      const r = await xqApi(`${P}/${noteAsk[2]}`, noteAsk[3](xqV(mm, "n1"))); if (r) { m.remove(); toast(noteAsk[4]); xqReload(); } return !!r; }, "Yuborish");
    if (k === "activity") return xqModal("Tadbir qo'shish", `
      <label>Turi<select id="t1">${Object.entries(XQ.meta.labels.activity).map(([k2, v]) => `<option value="${k2}">${esc(v)}</option>`).join("")}</select></label>
      <label>Nomi<input id="t2" maxlength="200"></label>
      <div class="row2"><label>Sana<input id="t3" type="date" max="${xqToday()}" value="${xqToday()}"></label><label>Soni (kishi / talaba)<input id="t4" type="number" min="0" value="1"></label></div>
      <label>Izoh<input id="t5" maxlength="600"></label>`, async mm => {
        const r = await xqApi(P + "/activities", {kind: xqV(mm, "t1"), title: xqV(mm, "t2"), date: xqV(mm, "t3"), count: +xqV(mm, "t4") || 0, note: xqV(mm, "t5")});
        if (r) { m.remove(); toast("Tadbir qo'shildi — KPI yangilandi"); xqAgDetail(id); xqReload(); } return !!r; });
  });
}

/* =================== Akademik mobillik =================== */
async function xqExchange(box) {
  const C = XQ.meta.can, d = await xqApi("/api/xalqaro/calls");
  if (!XQ.call && d.items.length) XQ.call = d.items[0].id;
  box.innerHTML = `<div class="xq-bar"><span class="grow muted">Mezonlar avtomatik tekshiriladi: ${esc(XQ.meta.rules.gpa)}; akademik qarz yo'qligi; til bali. ${esc(XQ.meta.rules.score)}.</span>
      ${C.edit ? `<button class="btn sm primary" type="button" id="xqNewCall">Yangi tanlov</button>` : ""}</div>
    <div class="xq-calls">${d.items.map(c => `<button type="button" class="xq-call ${c.id === XQ.call ? "on" : ""}" data-c="${c.id}"><b>${esc(c.title)}</b>
      <small>${esc(c.host)} · ${esc(c.country)} · ${c.seats} o'rin</small><span>${xqChip(c.status_label, c.status === "ochiq" ? "info" : c.status === "komissiya" ? "warn" : "")} ${xqChip(`${c.stats.jami || 0} ariza`)}</span></button>`).join("") || `<div class="xq-empty">Tanlovlar yo'q</div>`}</div>
    <div id="xqCallBody"></div>`;
  box.querySelectorAll("[data-c]").forEach(b => b.onclick = () => { XQ.call = +b.dataset.c; xqExchange(box); });
  const nb = $("#xqNewCall"); if (nb) nb.onclick = () => xqCallForm(d.agreements);
  if (XQ.call) await xqCall($("#xqCallBody"), XQ.call);
}
function xqCallForm(ags) {
  const t = xqToday();
  xqModal("Mobillik tanlovi e'loni", `
    <label>Nomi<input id="c1" maxlength="200" placeholder="Masalan: Erasmus+ KA171 — kuzgi semestr"></label>
    <label>Shartnoma asosida<select id="c2"><option value="">—</option>${ags.map(a => `<option value="${a.id}" data-c="${esc(a.country)}">${esc(a.partner_name)}</option>`).join("")}</select></label>
    <div class="row2"><label>Davlat<input id="c3"></label><label>O'rinlar<input id="c4" type="number" min="1" value="3"></label></div>
    <div class="row2"><label>Minimal GPA (5)<input id="c5" type="number" step="0.1" min="0" max="5" value="3.5"></label><label>Minimal til bali (IELTS shkalasi)<input id="c6" type="number" step="0.5" min="0" max="9" value="5.5"></label></div>
    <label>Til talabi (matn)<input id="c7" value="IELTS 5.5 yoki ekvivalent (B2)"></label>
    <div class="row2"><label>Minimal kurs<select id="c8">${[1, 2, 3, 4].map(k => `<option ${k === 2 ? "selected" : ""}>${k}</option>`).join("")}</select></label>
      <label>Akademik qarz<select id="c9"><option value="1">Qarzsiz bo'lishi shart</option><option value="0">Talab qilinmaydi</option></select></label></div>
    <div class="row2"><label>Ariza muddati<input id="c10" type="date" min="${t}"></label><label>Mobillik boshlanishi<input id="c11" type="date"></label></div>
    <label>Mobillik tugashi<input id="c12" type="date"></label>`, async m => {
      const r = await xqApi("/api/xalqaro/calls", {title: xqV(m, "c1"), agreement_id: +xqV(m, "c2") || null, country: xqV(m, "c3"), seats: +xqV(m, "c4"), min_gpa: +xqV(m, "c5"),
        lang_min: +xqV(m, "c6"), lang_req: xqV(m, "c7"), min_course: +xqV(m, "c8"), no_debts: xqV(m, "c9") === "1", deadline: xqV(m, "c10"), mob_start: xqV(m, "c11"), mob_end: xqV(m, "c12")});
      if (r) { XQ.call = r.id; toast("Tanlov e'lon qilindi — talabalar kabinetda ko'radi"); xqReload(); } return !!r;
    }, "E'lon qilish").querySelector("#c2").onchange = e => { const o = e.target.selectedOptions[0]; const c = e.target.closest(".xq-modal").querySelector("#c3"); if (o?.dataset.c && !c.value) c.value = o.dataset.c; };
}
async function xqCall(box, id) {
  const c = await xqApi(`/api/xalqaro/calls/${id}`), C = XQ.meta.can, L = XQ.meta.labels.application, S = c.stats;
  const acts = [];
  if (C.edit && c.status === "ochiq") acts.push(`<button class="btn sm" data-k="add">Ariza kiritish</button>`, `<button class="btn sm" data-k="recheck">Mezonlarni qayta tekshirish</button>`, `<button class="btn sm primary" data-k="close">Qabulni yopish → komissiya</button>`);
  if (C.edit && c.status === "komissiya") acts.push(`<button class="btn sm primary" data-k="select">Saralash natijasini chiqarish</button>`);
  const scoring = C.commission && c.status === "komissiya";
  box.innerHTML = `<div class="card xq-card"><div class="xq-item-h"><div><h3>${esc(c.title)}</h3>
      <p class="muted">${esc(c.host)} · ${esc(c.country)} · ${c.seats} o'rin (+${XQ.meta.rules.reserve} zaxira) · ariza muddati ${xqD(c.deadline)} · mobillik ${xqD(c.mob_start)} — ${xqD(c.mob_end)}<br>
      Mezonlar: GPA ≥ ${c.min_gpa} · til ≥ ${c.lang_min} (${esc(c.lang_req)}) · ${c.min_course}-kursdan${c.no_debts ? " · akademik qarzsiz" : ""}</p></div>
      ${acts.length ? `<div class="xq-acts">${acts.join("")}</div>` : ""}</div>
    <div class="xq-chips">${Object.entries(S).filter(([k]) => k !== "jami").map(([k, n]) => xqChip(`${L[k] || k}: ${n}`, xqAppCls(k))).join(" ")} ${xqChip(`Jami: ${S.jami || 0}`)}</div>
    ${c.names ? xqTable([
      ["O'rin", r => r.rank ? `<b>${r.rank}</b>` : "—", "num"],
      ["Talaba", r => `<b>${esc(r.full_name)}</b><small>${esc(r.grp)} · ${r.course}-kurs · ${esc(r.hemis_id)} · ${r.channel === "portal" ? "kabinetdan" : "xodim kiritdi"}</small>`],
      ["GPA / til", r => `${r.gpa != null ? Number(r.gpa).toFixed(2) : "—"} / ${r.lang_score ?? "—"}<small>${esc(r.lang_cert || "")}${r.debts ? ` · ${r.debts} qarz` : ""}</small>`, "num"],
      ["Mezon", r => r.eligible ? xqChip("mos", "ok") : `${xqChip("mos emas", "bad")}<small>${esc(r.elig_note)}</small>`],
      ["Suhbat", r => scoring && r.eligible ? `<input class="xq-in sm" type="number" min="0" max="15" step="0.5" value="${r.interview ?? ""}" data-score="${r.id}" aria-label="Suhbat bali (0–15)">` : (r.interview ?? "—"), "num"],
      ["Jami", r => r.total ?? "—", "num"],
      ["Holat", r => `${xqChip(r.status_label, xqAppCls(r.status))}${r.status_note ? `<small>${esc(r.status_note)}</small>` : ""}${r.departed ? `<small>ketdi ${xqD(r.departed)}${r.returned ? ` · qaytdi ${xqD(r.returned)}` : ""}</small>` : ""}${r.credit_label ? `<small>Kredit: ${esc(r.credit_label)}${r.credits_recognized != null ? ` (${r.credits_recognized}/${r.credits_earned})` : ""}</small>` : ""}`],
      ...(C.edit ? [["", r => r.status === "saralandi" ? `<button class="btn sm" data-dep="${r.id}">Jo'nadi</button> <button class="btn sm ghost" data-wd="${r.id}">Voz kechdi</button>` : r.status === "zaxira" ? `<button class="btn sm ghost" data-wd="${r.id}">Voz kechdi</button>` : r.status === "ketdi" ? `<button class="btn sm" data-ret="${r.id}">Qaytdi</button>` : ""]] : [])],
      c.applications, {empty: "Arizalar yo'q"}) : `<p class="xq-note">Arizalar ro'yxati (ism-shariflar) Xalqaro hamkorlik bo'limi va kuratorda; sizga jamlangan ko'rsatkichlar ko'rsatiladi.</p>`}
    ${scoring ? `<p class="xq-note">Suhbat bali (0–15) kiritilgach avtomatik saqlanadi va o'rinlar qayta hisoblanadi.</p>` : ""}</div>`;
  const P = "/api/xalqaro";
  box.querySelectorAll("[data-score]").forEach(i => i.onchange = async () => { if (i.value === "") return; const r = await xqApi(`${P}/applications/${i.dataset.score}/score`, {interview: +i.value}); if (r) { toast(`Saqlandi: jami ${r.total}, o'rin ${r.rank}`); xqCall(box, id); } });
  box.querySelectorAll("[data-k]").forEach(b => b.onclick = async () => {
    const k = b.dataset.k;
    if (k === "add") return xqModal("Ariza kiritish (xodim)", `<label>Talaba HEMIS ID<input id="p1" maxlength="40"></label>
      <div class="row2"><label>Til sertifikati<input id="p2" value="IELTS Academic"></label><label>Bali (IELTS shkalasi)<input id="p3" type="number" step="0.5" min="0" max="9"></label></div>
      <label>Motivatsiya<textarea id="p4" maxlength="2000"></textarea></label>`, async m => {
        const r = await xqApi(`${P}/calls/${id}/applications`, {hemis_id: xqV(m, "p1"), lang_cert: xqV(m, "p2"), lang_score: xqV(m, "p3") === "" ? null : +xqV(m, "p3"), motivation: xqV(m, "p4")});
        if (r) { toast(`${r.student}: ${r.eligible ? "mezonlarga mos" : "mos emas — " + r.note}`); xqExchange($("#xqBody")); } return !!r; }, "Kiritish");
    if (k === "recheck") { const r = await xqApi(`${P}/calls/${id}/recheck`, {}); if (r) { toast(`${r.checked} ta ariza qayta tekshirildi`); xqCall(box, id); } return; }
    if (k === "close") { if (!arm(b, "Ha, qabulni yopish")) return; if (await xqApi(`${P}/calls/${id}/close`, {})) { toast("Qabul yopildi — komissiya ballarini kiriting"); xqExchange($("#xqBody")); } return; }
    if (k === "select") { if (!arm(b, "Ha, natijani chiqarish")) return; const r = await xqApi(`${P}/calls/${id}/select`, {}); if (r) { toast(`Saralandi: ${r.saralandi}, zaxira: ${r.zaxira}`); xqExchange($("#xqBody")); } }
  });
  box.querySelectorAll("[data-dep]").forEach(b => b.onclick = () => xqModal("Mobillikka jo'nadi", `<label>Jo'nash sanasi<input id="d1" type="date" value="${xqToday()}"></label>`, async m => {
    const r = await xqApi(`${P}/applications/${b.dataset.dep}/depart`, {date: xqV(m, "d1")}); if (r) { toast("Qayd etildi"); xqCall(box, id); } return !!r; }));
  box.querySelectorAll("[data-wd]").forEach(b => b.onclick = () => xqModal("Nomzod voz kechdi", `<label>Sabab<input id="w1" maxlength="300"></label><p class="muted">Saralangan nomzod o'rniga birinchi zaxiradagi talaba avtomatik o'tadi.</p>`, async m => {
    const r = await xqApi(`${P}/applications/${b.dataset.wd}/withdraw`, {note: xqV(m, "w1")}); if (r) { toast(r.promoted ? "Zaxiradagi nomzod saralandi" : "Qayd etildi"); xqCall(box, id); } return !!r; }));
  box.querySelectorAll("[data-ret]").forEach(b => b.onclick = () => xqModal("Mobillikdan qaytdi", `
    <div class="row2"><label>Qaytish sanasi<input id="r1" type="date" value="${xqToday()}"></label><label>Olingan kredit (ECTS)<input id="r2" type="number" min="0" max="90" value="30"></label></div>
    <label>Transkript izohi<input id="r3" maxlength="600" placeholder="Fanlar soni, baholar"></label><p class="muted">Kreditlarni tan olish uchun Akademik bo'lim navbatiga tushadi.</p>`, async m => {
    const r = await xqApi(`${P}/applications/${b.dataset.ret}/return`, {date: xqV(m, "r1"), credits_earned: +xqV(m, "r2"), transcript_note: xqV(m, "r3")});
    if (r) { toast("Qaytdi — Akademik bo'limga kredit tan olish uchun yuborildi"); xqCall(box, id); } return !!r; }));
}

/* =================== Kredit tan olish =================== */
async function xqCredits(box) {
  const d = await xqApi("/api/xalqaro/credits"), L = XQ.meta.labels.credit;
  const wait = d.items.filter(x => x.credit_status === "kutilmoqda").length;
  box.innerHTML = `<div class="xq-bar"><span class="grow muted">${d.can_decide ? `Navbatda: ${wait} ta. Xorijiy OTM transkripti asosida kreditlarni to'liq, qisman (farq fanlari bilan) yoki tan olmaslik qarori.` : "Akademik bo'lim qarorlari (faqat ko'rish)."}</span></div>
    <div class="card xq-card">${xqTable([
      ["Talaba", r => `<b>${esc(r.full_name)}</b><small>${esc(r.grp)} · ${r.course}-kurs · ${esc(r.hemis_id)}</small>`],
      ["Mobillik", r => `${esc(r.host)} (${esc(r.country)})<small>${xqD(r.departed)} — ${xqD(r.returned)} · ${esc(r.call)}</small>`],
      ["Kredit", r => `${r.credits_earned ?? "—"} ECTS<small>${esc(r.transcript_note || "")}</small>`, "num"],
      ["Qaror", r => `${xqChip(r.credit_label, r.credit_status === "kutilmoqda" ? "warn" : r.credit_status === "rad" ? "bad" : "ok")}${r.credits_recognized != null ? `<small>${r.credits_recognized} tan olindi${r.credit_note ? " · " + esc(r.credit_note) : ""}</small>` : ""}`],
      ...(d.can_decide ? [["", r => r.credit_status === "kutilmoqda" ? `<button class="btn sm primary" data-cr="${r.id}" data-e="${r.credits_earned}">Qaror</button>` : ""]] : [])],
      d.items, {rowCls: r => r.credit_status === "kutilmoqda" && d.can_decide ? "xq-mine" : "", empty: "Navbat bo'sh"})}</div>`;
  box.querySelectorAll("[data-cr]").forEach(b => b.onclick = () => xqModal("Kreditni tan olish", `
    <label>Qaror<select id="k1"><option value="tan_olindi">${esc(L.tan_olindi)} (${b.dataset.e} ECTS)</option><option value="qisman">${esc(L.qisman)}</option><option value="rad">${esc(L.rad)}</option></select></label>
    <label>Tan olingan kredit (qisman uchun)<input id="k2" type="number" min="0" max="${b.dataset.e}"></label>
    <label>Izoh (farq fanlari, sabab)<textarea id="k3" maxlength="1000"></textarea></label>`, async m => {
      const r = await xqApi(`/api/xalqaro/credits/${b.dataset.cr}`, {decision: xqV(m, "k1"), credits_recognized: +xqV(m, "k2") || 0, note: xqV(m, "k3")});
      if (r) { toast(`Qaror saqlandi: ${r.credits_recognized} ECTS`); xqCredits(box); } return !!r; }));
}

/* =================== Xorijiy talabalar =================== */
async function xqForeign(box) {
  const d = await xqApi("/api/xalqaro/foreign");
  const al = r => r.alert === "over" ? xqChip("muddati o'tgan", "bad") : r.alert === "high" ? xqChip("≤30 kun", "bad") : r.alert === "mid" ? xqChip("≤60 kun", "warn") : "";
  box.innerHTML = `<div class="xq-bar"><span class="grow muted">Viza va ro'yxatga olish muddati ${XQ.meta.rules.visa_warn} va ${XQ.meta.rules.visa_high} kun oldin ogohlantiriladi. Pasport raqami faqat oxirgi 4 belgisi bilan saqlanadi.</span>
    ${d.can_edit ? `<button class="btn sm primary" type="button" id="xqNewF">Xorijiy talaba qo'shish</button>` : ""}</div>
    <div class="card xq-card">${xqTable([
      ["Talaba", r => `<b>${esc(r.full_name)}</b><small>${esc(r.country)} · ${esc(r.program)} · ${r.course}-kurs · pasport ${esc(r.passport || "—")}</small>`],
      ["Viza", r => `${esc(r.visa_type)}<small>${esc(r.visa_no)} · ${xqD(r.visa_expires)} · ${xqDays(r.visa_days)}</small>`],
      ["Ro'yxatga olish", r => `${xqD(r.reg_expires)}<small>${xqDays(r.reg_days)}</small>`, "num"],
      ["Holat", r => `${xqChip(r.status, r.status === "o'qimoqda" ? "" : "info")} ${al(r)}`],
      ...(d.can_edit ? [["", r => `<button class="btn sm" data-fu="${r.id}">Yangilash</button>`]] : [])],
      d.items, {rowCls: r => r.alert === "over" || r.alert === "high" ? "xq-bad" : ""})}</div>`;
  const nb = $("#xqNewF"); if (nb) nb.onclick = () => xqModal("Xorijiy talaba", `
    <label>F.I.Sh.<input id="g1" maxlength="200"></label><div class="row2"><label>Davlat<input id="g2"></label><label>Kurs<input id="g3" type="number" min="1" max="6" value="1"></label></div>
    <label>Yo'nalish / dastur<input id="g4"></label><div class="row2"><label>Pasport (faqat oxirgi 4 belgi saqlanadi)<input id="g5" maxlength="20"></label><label>Viza turi<input id="g6" value="O'qish vizasi (S-3)"></label></div>
    <div class="row2"><label>Viza raqami<input id="g7"></label><label>Viza muddati<input id="g8" type="date"></label></div><label>Ro'yxatga olish muddati<input id="g9" type="date"></label>`, async m => {
      const r = await xqApi("/api/xalqaro/foreign", {full_name: xqV(m, "g1"), country: xqV(m, "g2"), course: +xqV(m, "g3") || 1, program: xqV(m, "g4"), passport: xqV(m, "g5"),
        visa_type: xqV(m, "g6"), visa_no: xqV(m, "g7"), visa_expires: xqV(m, "g8"), reg_expires: xqV(m, "g9")});
      if (r) { toast("Qo'shildi"); xqForeign(box); } return !!r; });
  box.querySelectorAll("[data-fu]").forEach(b => b.onclick = () => { const f = d.items.find(x => x.id === +b.dataset.fu);
    xqModal(f.full_name, `<div class="row2"><label>Viza muddati<input id="u1" type="date" value="${esc(f.visa_expires)}"></label><label>Ro'yxatga olish<input id="u2" type="date" value="${esc(f.reg_expires)}"></label></div>
      <div class="row2"><label>Viza raqami<input id="u3" value="${esc(f.visa_no || "")}"></label><label>Holat<select id="u4">${["o'qimoqda", "akademik ta'til", "bitirgan", "chetlashtirilgan"].map(s => `<option ${s === f.status ? "selected" : ""}>${s}</option>`).join("")}</select></label></div>
      <label>Izoh<input id="u5" value="${esc(f.note || "")}"></label>`, async m => {
        const r = await xqApi(`/api/xalqaro/foreign/${f.id}`, {visa_expires: xqV(m, "u1"), reg_expires: xqV(m, "u2"), visa_no: xqV(m, "u3"), status: xqV(m, "u4"), note: xqV(m, "u5")});
        if (r) { toast("Yangilandi"); xqForeign(box); } return !!r; }); });
}

/* =================== Delegatsiyalar =================== */
async function xqDelegations(box) {
  const d = await xqApi("/api/xalqaro/delegations");
  box.innerHTML = `<div class="xq-bar"><span class="grow muted">Kiruvchi xorijiy delegatsiyalar: maqsad, mezbon, natija.</span>
    ${d.can_edit ? `<button class="btn sm primary" type="button" id="xqNewD">Delegatsiya qayd etish</button>` : ""}</div>
    <div class="card xq-card">${xqTable([
      ["Sana", r => `${xqD(r.arrive)}<small>— ${xqD(r.depart)}</small>`, "num"],
      ["Tashkilot", r => `<b>${esc(r.org)}</b><small>${esc(r.country)} · ${esc(r.head || "")} · ${r.members} kishi</small>`],
      ["Maqsad", r => `${esc(r.purpose)}${r.agreement ? `<small>Shartnoma: ${esc(r.agreement)}</small>` : ""}${r.host ? `<small>Mezbon: ${esc(r.host)}</small>` : ""}`],
      ["Natija", r => `${xqChip(r.status, r.status === "o'tkazildi" ? "ok" : r.status === "bekor" ? "" : "info")}${r.outcome ? `<small>${esc(r.outcome)}</small>` : ""}`],
      ...(d.can_edit ? [["", r => r.status === "rejalashtirilgan" ? `<button class="btn sm" data-do="${r.id}">Natija</button>` : ""]] : [])],
      d.items, {empty: "Delegatsiyalar qayd etilmagan"})}</div>`;
  const nb = $("#xqNewD"); if (nb) nb.onclick = () => xqModal("Delegatsiya", `
    <label>Tashkilot<input id="e1" maxlength="200"></label><div class="row2"><label>Davlat<input id="e2"></label><label>Kishi soni<input id="e3" type="number" min="1" value="2"></label></div>
    <label>Rahbar (lavozimi)<input id="e4"></label><div class="row2"><label>Kelish<input id="e5" type="date"></label><label>Ketish<input id="e6" type="date"></label></div>
    <label>Maqsad<input id="e7" maxlength="500"></label><label>Mezbon (institutdan)<input id="e8"></label>`, async m => {
      const r = await xqApi("/api/xalqaro/delegations", {org: xqV(m, "e1"), country: xqV(m, "e2"), members: +xqV(m, "e3") || 1, head: xqV(m, "e4"), arrive: xqV(m, "e5"), depart: xqV(m, "e6"), purpose: xqV(m, "e7"), host: xqV(m, "e8")});
      if (r) { toast("Qayd etildi"); xqDelegations(box); } return !!r; });
  box.querySelectorAll("[data-do]").forEach(b => b.onclick = () => xqModal("Tashrif natijasi", `
    <label>Holat<select id="o1"><option value="o'tkazildi">O'tkazildi</option><option value="bekor">Bekor bo'ldi</option></select></label>
    <label>Natija (kelishuvlar, keyingi qadamlar)<textarea id="o2" maxlength="1500"></textarea></label>`, async m => {
      const r = await xqApi(`/api/xalqaro/delegations/${b.dataset.do}/outcome`, {status: xqV(m, "o1"), outcome: xqV(m, "o2")});
      if (r) { toast("Saqlandi"); xqDelegations(box); } return !!r; }));
}

/* ---------- navigatsiya: go("xalqaro") (app.js go() xaritasiga tegmasdan) ---------- */
(function () {
  if (typeof go !== "function" || go._xq) return;
  const prev = go;
  go = function (v) {
    prev(v);
    if (v !== "xalqaro") return;
    Promise.resolve().then(renderXalqaro).catch(e => { if (e?.message === "auth") return; $("#v-xalqaro").innerHTML = e?.message === "denied" ? locked("Bu bo'lim") : errCard("xalqaro"); });
  };
  go._xq = true;
})();
