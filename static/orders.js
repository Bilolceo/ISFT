/* =====================================================================
   «Buyruqlar» — talabalar harakati buyruqlari (app/orders.py, /api/orders).
     Reyestr · Arizadan buyruq · Ro'yxatdan buyruq (Excel/CSV, versiyalar) · Muammoli talabalar · O'zgarishlar jurnali.
   Ruxsatlar serverda: Registrator ofisi — to'liq; Sirtqi bo'lim — sirtqi talabalar; Ma'lumotlar bazasi — o'qish + tuzatish;
   O'quv prorektori — kelishish; Rektor — imzolash/qaytarish. Bu yerda faqat tugmalar ko'rsatiladi/yashiriladi.
   Global: renderOrders() (app.js go()), ordersBadge(set) (app.js badges()).
   app.js yordamchilari: $, esc, fmt, ico, ICONS, hydrateIcons, toast, showLogin, ME, dmy.
   ===================================================================== */
const OR = {tab: null, meta: null, f: {status: "", kind: "", q: "", hist: -1}, list: [], total: 0, id: null, d: null, iq: "", ioff: 0, sel: new Set(),
            intake: null, issues: null, ifilter: "", iq2: "", fixOpen: null, fixDoc: {}, chq: "", diff: null, confirm: null, editItem: null};
if (!document.querySelector('link[href="orders.css"]')) document.head.insertAdjacentHTML("beforeend", '<link rel="stylesheet" href="orders.css">');
if (typeof ICONS === "object") {
  Object.assign(ICONS, Object.fromEntries(Object.entries({
    scroll: '<path d="M8 21h12a2 2 0 0 0 2-2v-2H10v2a2 2 0 1 1-4 0V5a2 2 0 1 0-4 0v3h4"/><path d="M19 17V5a2 2 0 0 0-2-2H4"/><path d="M15 8h-5M15 12h-5"/>',
    upload: '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><path d="m17 8-5-5-5 5"/><path d="M12 3v12"/>',
    download: '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><path d="m7 10 5 5 5-5"/><path d="M12 15V3"/>',
    back: '<path d="m15 18-6-6 6-6"/>',
    plus: '<path d="M12 5v14M5 12h14"/>',
    pen: '<path d="M12 20h9"/><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4z"/>',
    trash: '<path d="M3 6h18M8 6V4h8v2M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/>',
    layers: '<path d="m12 2 10 5-10 5L2 7z"/><path d="m2 17 10 5 10-5M2 12l10 5 10-5"/>',
    stamp: '<path d="M5 22h14M19.27 13.73A2.5 2.5 0 0 0 17.5 13h-11A2.5 2.5 0 0 0 4 15.5V17a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-1.5c0-.66-.26-1.3-.73-1.77z"/><path d="M14 13V8.5C14 7 15 7 15 5a3 3 0 0 0-6 0c0 2 1 2 1 3.5V13"/>',
    undo: '<path d="M9 14 4 9l5-5"/><path d="M4 9h10.5a5.5 5.5 0 0 1 0 11H11"/>',
  }).filter(([k]) => !ICONS[k])));
  try { const s = document.querySelector('#nav a[data-v="orders"] svg'); if (s && !s.innerHTML.trim()) { s.remove(); hydrateIcons(); } } catch (e) {}
}

/* ---------- server ---------- */
async function orApi(path, body, raw) {
  const opt = {method: body === undefined ? "GET" : "POST", credentials: "same-origin"};
  if (raw) { opt.body = body; opt.headers = {"Content-Type": "application/octet-stream"}; }
  else if (body !== undefined) { opt.body = JSON.stringify(body); opt.headers = {"Content-Type": "application/json"}; }
  const r = await fetch(path, opt);
  if (r.status === 401) { showLogin(); throw new Error("auth"); }
  const d = await r.json().catch(() => ({}));
  if (!r.ok) {
    const det = d.detail, msg = d.message || (typeof det === "string" ? det : Array.isArray(det) ? "Ma'lumot noto'g'ri" : det?.message) || "Xatolik yuz berdi";
    const e = new Error(r.status === 403 && body === undefined && !OR.meta ? "denied" : "api"); e.msg = msg; e.status = r.status; throw e;
  }
  return d;
}
async function orDo(btn, fn, okMsg) {
  if (btn?.disabled) return;
  const old = btn ? btn.innerHTML : ""; if (btn) { btn.disabled = true; btn.innerHTML = "…"; }
  try { const r = await fn(); if (okMsg) toast(okMsg); return r; }
  catch (e) { if (e.message !== "auth") toast(e.msg || "Xatolik yuz berdi — qayta urinib ko'ring"); }
  finally { if (btn && btn.isConnected) { btn.disabled = false; btn.innerHTML = old; } }
}
const orUp = (path, file) => orApi(path + (path.includes("?") ? "&" : "?") + "name=" + encodeURIComponent(file.name), file, true);

/* ---------- yordamchilar ---------- */
const OR_ST_CLS = {loyiha: "draft", yuborilgan: "wait", kelishilgan: "wait", imzolangan: "ok", bekor: "off", bekor_qilingan: "bad"};
const orSt = (s, name) => `<span class="or-st ${OR_ST_CLS[s] || ""}">${esc(name || s)}</span>`;
const orKind = k => (OR.meta?.kinds || []).find(x => x.key === k) || {short: k, title: k, fields: [], req: []};
const orLbl = f => (OR.meta?.field_labels || {})[f] || f;
const orCan = () => OR.meta?.caps || {};
const orWhen = ts => ts ? `${dmy(String(ts).slice(0, 10))}${String(ts).length > 10 ? " " + String(ts).slice(11, 16) : ""}` : "—";
const orN = n => fmt(n ?? 0);
const FIELD_NAMES = {full_name: "F.I.Sh.", status: "Holat", group_id: "Guruh", faculty_id: "Fakultet"};
function orFieldVal(f, v) { return f.startsWith("date_") && v ? dmy(v) : esc(v ?? ""); }
function orFieldsTxt(eff, kind) {
  const ks = orKind(kind).fields; if (!ks.length) return "";
  return ks.filter(f => eff?.[f]).map(f => `<span class="or-fv"><i>${esc(orLbl(f))}:</i> ${orFieldVal(f, eff[f])}</span>`).join("");
}
function orInput(f, v, id) {
  if (f.startsWith("date_")) return `<input type="date" id="${id}" value="${esc(v || "")}">`;
  if (f === "group_to") return `<input id="${id}" value="${esc(v || "")}" placeholder="Guruh nomi, masalan IQT-2402" list="orGroups" autocomplete="off">`;
  return `<input id="${id}" value="${esc(v || "")}">`;
}
let orGrpT;
function orGroupList(input) {   /* guruh nomlari uchun datalist */
  if (!document.getElementById("orGroups")) document.body.insertAdjacentHTML("beforeend", '<datalist id="orGroups"></datalist>');
  input.addEventListener("input", () => { clearTimeout(orGrpT); orGrpT = setTimeout(async () => {
    try { const g = await orApi(`/api/orders/lookup/groups?q=${encodeURIComponent(input.value)}`); document.getElementById("orGroups").innerHTML = g.map(x => `<option value="${esc(x.name)}">${x.course}-kurs · ${esc(x.form)}</option>`).join(""); } catch (e) {}
  }, 200); });
}

/* ---------- asosiy ---------- */
async function renderOrders() {
  const el = $("#v-orders");
  try { OR.meta = await orApi("/api/orders/meta"); }
  catch (e) { if (e.status === 403 || e.message === "denied") { el.innerHTML = typeof locked === "function" ? locked("Buyruqlar") : `<div class="card">${esc(e.msg || "Ruxsat yo'q")}</div>`; return; } throw e; }
  const c = orCan();
  if (!OR.tab) OR.tab = ME.role_key === "malumotlar_bazasi" ? "audit" : "reg";
  if (!OR.f.status) OR.f.status = c.sign || c.forward ? "imzo" : c.edit ? "jarayonda" : "";
  orShell();
}
function orTabs() {
  const c = orCan();
  return [["reg", "Reyestr", "scroll"], ...(c.edit ? [["intake", "Arizadan buyruq", "file"], ["bulk", "Ro'yxatdan buyruq", "layers"]] : []),
          ["audit", "Muammoli talabalar", "alert"], ["changes", "O'zgarishlar jurnali", "history"]];
}
function orShell() {
  const el = $("#v-orders"), m = OR.meta, c = orCan();
  const pend = c.sign ? m.pending.sign : c.forward ? m.pending.forward : 0;
  el.innerHTML = `<div class="head"><div><h2>Buyruqlar</h2><span class="muted">Talabalar harakati: arizadan buyruq loyihasi, katta ro'yxatlar versiyalari, rektor imzosi va bazaga avtomatik ta'sir. ${c.sirtqi ? "Ko'lam: faqat sirtqi ta'lim talabalari." : ""}</span></div></div>
    ${pend ? `<button type="button" class="or-pend" id="orPend">${ico("stamp", 18)}<span><b>${pend} ta buyruq ${c.sign ? "imzongizni" : "kelishuvingizni"} kutmoqda</b><small>Ko'rib chiqish uchun bosing</small></span>${ico("arrow", 16)}</button>` : ""}
    <div class="or-tabs" role="tablist">${orTabs().map(([k, l, i]) => `<button type="button" role="tab" data-t="${k}" aria-selected="${OR.tab === k}" class="${OR.tab === k ? "on" : ""}">${ico(i, 15)}<span>${l}</span></button>`).join("")}</div>
    <div id="orBody"></div>`;
  el.querySelectorAll(".or-tabs button").forEach(b => b.onclick = () => { OR.tab = b.dataset.t; OR.id = null; orShell(); });
  if ($("#orPend")) $("#orPend").onclick = () => { OR.tab = "reg"; OR.id = null; OR.f.status = "imzo"; orShell(); };
  if (OR.id) return orDetail(OR.id);
  ({reg: orRegistry, intake: orIntake, bulk: orBulk, audit: orAudit, changes: orChanges})[OR.tab]();
}
function orOpen(id) { OR.id = id; OR.iq = ""; OR.ioff = 0; OR.sel = new Set(); OR.diff = null; OR.confirm = null; OR.editItem = null; orShell(); window.scrollTo({top: 0}); }

/* ---------- reyestr ---------- */
async function orRegistry(more) {
  const b = $("#orBody"), m = OR.meta;
  if (!more) {
    b.innerHTML = `<div class="card or-card"><div class="or-filters">
        <label class="or-search">${ico("search", 16)}<input id="orQ" placeholder="Raqam, sarlavha, talaba F.I.Sh., HEMIS ID yoki guruh" value="${esc(OR.f.q)}" aria-label="Qidiruv"></label>
        <select id="orS" aria-label="Holat"><option value="jarayonda">Jarayonda (loyiha, imzoda)</option><option value="imzo">Imzo kutmoqda</option><option value="">Hammasi</option>
          ${Object.entries(m.statuses).map(([k, v]) => `<option value="${k}">${esc(v)}</option>`).join("")}</select>
        <select id="orK" aria-label="Turi"><option value="">Barcha turlar</option>${m.kinds.map(k => `<option value="${k.key}">${esc(k.short)}</option>`).join("")}</select>
        <select id="orH" aria-label="Manba"><option value="-1">Yangi va arxiv</option><option value="0">Tizimda tuzilgan</option><option value="1">Arxiv (import)</option></select>
      </div><div class="tiny muted or-cnt" id="orCnt"></div><div id="orList" class="or-list"></div><div id="orMore"></div></div>`;
    $("#orS").value = OR.f.status; $("#orK").value = OR.f.kind; $("#orH").value = String(OR.f.hist);
    let t; $("#orQ").oninput = () => { clearTimeout(t); t = setTimeout(() => { OR.f.q = $("#orQ").value.trim(); orRegistry(); }, 300); };
    $("#orS").onchange = () => { OR.f.status = $("#orS").value; orRegistry(); };
    $("#orK").onchange = () => { OR.f.kind = $("#orK").value; orRegistry(); };
    $("#orH").onchange = () => { OR.f.hist = +$("#orH").value; orRegistry(); };
    OR.list = [];
  }
  const qs = new URLSearchParams({status: OR.f.status, kind: OR.f.kind, q: OR.f.q, hist: OR.f.hist, offset: OR.list.length, limit: 50});
  const r = await orApi("/api/orders?" + qs);
  OR.list = OR.list.concat(r.items); OR.total = r.total;
  $("#orCnt").textContent = `${orN(r.total)} ta buyruq`;
  $("#orList").innerHTML = OR.list.length ? OR.list.map(o => `<button type="button" class="or-row" data-id="${o.id}">
      <span class="or-rno"><b>${esc(o.reg_no || "Loyiha #" + o.id)}</b><small>${o.order_date ? dmy(o.order_date) : "yaratildi " + orWhen(o.created_at)}</small></span>
      <span class="or-rt"><b>${esc(o.title)}</b><small><span class="or-kind">${esc(o.kind_name)}</span>${o.study_form ? ` · ${esc(o.study_form)}` : ""}${o.historic ? " · arxiv" : o.creator ? ` · ${esc(o.creator)}` : ""}${o.version > 1 ? ` · ${o.version}-versiya` : ""}${o.returned_note && o.status === "loyiha" ? ` · <em class="or-ret">qaytarilgan</em>` : ""}</small></span>
      <span class="or-rn"><b>${orN(o.count)}</b><small>talaba</small></span>
      <span class="or-rs">${orSt(o.status, o.status_name)}</span></button>`).join("")
    : `<div class="or-empty">${ico("scroll", 22)}<b>Buyruq topilmadi</b><span class="tiny muted">Filtrni o'zgartiring${orCan().edit ? " yoki «Arizadan buyruq» / «Ro'yxatdan buyruq» orqali yangi loyiha tuzing" : ""}.</span></div>`;
  $("#orList").querySelectorAll(".or-row").forEach(x => x.onclick = () => orOpen(+x.dataset.id));
  $("#orMore").innerHTML = OR.list.length < OR.total ? `<button type="button" class="btn sm" id="orMoreB">Yana ${Math.min(50, OR.total - OR.list.length)} ta</button>` : "";
  if ($("#orMoreB")) $("#orMoreB").onclick = e => orDo(e.target, () => orRegistry(true));
}

/* ---------- buyruq sahifasi ---------- */
async function orDetail(id, keepScroll) {
  const b = $("#orBody"), y = window.scrollY;
  const d = OR.d = await orApi(`/api/orders/${id}?` + new URLSearchParams({q: OR.iq, offset: OR.ioff, limit: 100}));
  const o = d.order, can = d.can, k = orKind(o.kind), draft = can.edit;
  const conf = OR.confirm;
  const act = [];
  if (can.submit) act.push(`<button type="button" class="btn primary sm" data-a="submit">${ico("send", 15)} Imzoga yuborish</button>`);
  if (can.forward) act.push(`<button type="button" class="btn primary sm" data-a="forward">${ico("check", 15)} Kelishish</button>`);
  if (can.sign) act.push(`<button type="button" class="btn primary sm" data-a="sign">${ico("stamp", 15)} Imzolash</button>`);
  if (can.return) act.push(`<button type="button" class="btn sm" data-a="return">${ico("undo", 15)} Qaytarish</button>`);
  if (can.annul) act.push(`<button type="button" class="btn sm" data-a="annul">${ico("x", 15)} Bekor qiluvchi buyruq</button>`);
  act.push(`<a class="btn sm" href="/api/orders/${o.id}/docx">${ico("download", 15)} DOCX</a>`, `<a class="btn sm" href="/api/orders/${o.id}/xlsx">${ico("download", 15)} Ro'yxat (XLSX)</a>`);
  if (can.delete) act.push(`<button type="button" class="btn ghost sm" data-a="delete">${ico("trash", 15)} O'chirish</button>`);
  const confHtml = conf ? `<div class="or-confirm" role="alert">${conf.note ? `<label class="or-l">${esc(conf.label)}<textarea id="orCN" rows="2" placeholder="${esc(conf.ph || "")}"></textarea></label>` : `<span>${conf.text}</span>`}
      <div class="row-actions"><button type="button" class="btn primary sm" id="orCY">${esc(conf.yes)}</button><button type="button" class="btn ghost sm" id="orCX">Bekor</button></div></div>` : "";
  const rel = d.related;
  const steps = [["loyiha", "Loyiha", o.created_at, o.creator], ["yuborilgan", "Imzoga yuborildi", o.submitted_at, ""], ["kelishilgan", "Prorektor kelishdi", o.forwarded_at, o.forwarder], ["imzolangan", "Rektor imzoladi", o.signed_at, o.signer]];
  const reached = {loyiha: 0, yuborilgan: 1, kelishilgan: 2, imzolangan: 3, bekor_qilingan: 3, bekor: 0}[o.status] ?? 0;
  b.innerHTML = `<div class="or-dhead"><button type="button" class="btn ghost sm" id="orBack">${ico("back", 15)} Reyestr</button></div>
    <div class="card or-card">
      <div class="or-top"><div class="or-ttl"><span class="or-kind">${esc(o.kind_name)}</span><h3>${esc(o.title)}</h3>
        <span class="muted tiny">${o.reg_no ? `<b>№ ${esc(o.reg_no)}</b> · ${dmy(o.order_date)}` : `Loyiha #${o.id}`} · ${orN(d.all)} ta talaba · ${o.version}-versiya${o.study_form ? " · " + esc(o.study_form) : ""}${o.historic ? " · arxivdan import" : ""}</span></div>
        <div>${orSt(o.status, o.status_name)}</div></div>
      ${o.historic ? "" : `<ol class="or-steps">${steps.map(([s, l, ts, who], i) => `<li class="${i <= reached && o.status !== "bekor" ? "done" : ""}"><i></i><b>${l}</b><small>${i <= reached && ts ? orWhen(ts) : ""}${who && i <= reached ? " · " + esc(who) : ""}</small></li>`).join("")}</ol>`}
      ${o.returned_note && o.status === "loyiha" ? `<div class="or-note warn">${ico("undo", 15)}<span><b>Qaytarilgan:</b> ${esc(o.returned_note)}</span></div>` : ""}
      ${rel.cancels ? `<div class="or-note">${ico("info", 15)}<span>Bekor qilinadigan buyruq: <a href="#" data-open="${rel.cancels.id}">${esc(rel.cancels.reg_no || "#" + rel.cancels.id)} — ${esc(rel.cancels.title)}</a>. Imzolangach talabalar ma'lumotlari avvalgi holatiga qaytariladi.</span></div>` : ""}
      ${rel.cancelled_by ? `<div class="or-note bad">${ico("x", 15)}<span>Bu buyruq <a href="#" data-open="${rel.cancelled_by.id}">${esc(rel.cancelled_by.reg_no || "#" + rel.cancelled_by.id)}</a> bilan bekor qilingan.</span></div>` : ""}
      ${rel.cancel_pending ? `<div class="or-note">${ico("info", 15)}<span>Bekor qiluvchi loyiha tayyorlanmoqda: <a href="#" data-open="${rel.cancel_pending.id}">#${rel.cancel_pending.id}</a></span></div>` : ""}
      ${d.checks.errors.map(e => `<div class="or-note bad">${ico("alert", 15)}<span>${esc(e)}</span></div>`).join("")}
      ${d.checks.warnings.map(e => `<div class="or-note warn">${ico("alert", 15)}<span>${esc(e)}</span></div>`).join("")}
      <div class="row-actions or-acts">${act.join("")}</div>${confHtml}
      ${o.status === "imzolangan" && k.effect && o.kind !== "bekor" && !o.historic ? `<div class="or-note ok">${ico("checkc", 15)}<span>Ta'sir bazaga o'tkazildi${o.applied_at ? " · " + orWhen(o.applied_at) : ""}. Ro'yxat muzlatilgan — o'zgartirish faqat tuzatuvchi buyruq orqali.</span></div>` : ""}
    </div>
    <div class="or-grid">
      <div class="or-main">${orItemsCard(d)}</div>
      <div class="or-side">${orParamsCard(d)}${orVersionsCard(d)}${orFilesCard(d)}${orLogCard(d)}</div>
    </div>`;
  orBind(d);
  if (keepScroll) window.scrollTo({top: y});
}
function orParamsCard(d) {
  const o = d.order, k = orKind(o.kind), ed = d.can.edit;
  const pf = k.fields.filter(f => !["old_surname", "new_surname", "basis"].includes(f));
  return `<div class="card or-card"><h4>Buyruq ma'lumotlari</h4>
    ${ed ? `<div class="or-form"><label class="or-l">Sarlavha<input id="orPT" value="${esc(o.title)}"></label>
      <label class="or-l">Asos (bo'sh bo'lsa — shablon)<input id="orPB" value="${esc(o.basis || "")}" placeholder="talabaning arizasi va …"></label>
      ${pf.length ? `<div class="tiny muted">Barcha talabalar uchun umumiy qiymat (talaba qatorida alohida berilsa — o'shasi olinadi):</div>` + pf.map(f => `<label class="or-l">${esc(orLbl(f))}${orInput(f, o.params[f], "orPP_" + f)}</label>`).join("") : ""}
      <label class="or-l">Izoh<textarea id="orPN" rows="2">${esc(o.note || "")}</textarea></label>
      <button type="button" class="btn sm" id="orPS">${ico("check", 15)} Saqlash</button></div>`
      : `<dl class="or-dl"><dt>Asos</dt><dd>${esc(o.basis || "shablon bo'yicha")}</dd>${pf.filter(f => o.params[f]).map(f => `<dt>${esc(orLbl(f))}</dt><dd>${orFieldVal(f, o.params[f])}</dd>`).join("")}
        ${o.note ? `<dt>Izoh</dt><dd>${esc(o.note)}</dd>` : ""}<dt>Manba</dt><dd>${esc(o.source || "—")}</dd><dt>Tuzgan</dt><dd>${esc(o.creator || "Arxiv")}</dd></dl>`}</div>`;
}
function orItemsCard(d) {
  const o = d.order, k = orKind(o.kind), ed = d.can.edit, signed = ["imzolangan", "bekor_qilingan"].includes(o.status) && !o.historic;
  const rows = d.items.map(i => {
    const editing = OR.editItem === i.id;
    const unm = !i.student_id;
    const now = i.now && (i.now.full_name !== i.full_name || i.now.grp !== i.group_name) ? `<small class="or-now">hozir: ${esc(i.now.full_name)} · ${esc(i.now.grp || "")}</small>` : "";
    const eff = signed && i.prev && i.prev.after && Object.keys(i.prev.after).length ? `<div class="or-eff">${Object.keys(i.prev.after).filter(f => f !== "faculty_id").map(f => `<span>${esc(FIELD_NAMES[f] || f)}: <s>${esc(f === "group_id" ? "" : i.prev.before[f])}</s> → <b>${esc(f === "group_id" ? (i.now?.grp || i.prev.after[f]) : i.prev.after[f])}</b></span>`).join("")}</div>` : "";
    return `<div class="or-it${unm ? " unm" : ""}${OR.sel.has(i.id) ? " sel" : ""}">
      ${ed ? `<input type="checkbox" class="or-cb" data-id="${i.id}" aria-label="Tanlash: ${esc(i.full_name)}" ${OR.sel.has(i.id) ? "checked" : ""}>` : ""}
      <div class="or-itm"><b>${esc(i.full_name)}</b><small>${esc(i.hemis_id || "HEMIS yo'q")} · ${esc(i.group_name || "—")}${i.now && i.now.status !== "faol" ? ` · <em>${esc(i.now.status)}</em>` : ""}</small>${now}
        ${unm ? `<small class="or-why">${ico("alert", 12)} ${esc(i.raw?.why || "bazada topilmadi")}${i.raw?.line ? ` (fayl qatori ${i.raw.line})` : ""}</small>` : ""}
        <div class="or-fvs">${orFieldsTxt(i.eff, o.kind)}</div>${eff}
        ${editing ? `<div class="or-iedit">${k.fields.map(f => `<label class="or-l">${esc(orLbl(f))}${k.req.includes(f) ? " *" : ""}${orInput(f, i.data[f], `orIE_${f}`)}</label>`).join("")}
          <div class="row-actions"><button type="button" class="btn primary sm" id="orIES" data-id="${i.id}">Saqlash (yangi versiya)</button><button type="button" class="btn ghost sm" id="orIEX">Bekor</button></div></div>` : ""}
      </div>
      ${ed && !unm && k.fields.length && !editing ? `<button type="button" class="icon-btn or-ib" data-edit="${i.id}" aria-label="Tahrirlash: ${esc(i.full_name)}" title="Maydonlarni tahrirlash">${ico("pen", 15)}</button>` : ""}
    </div>`;
  }).join("");
  return `<div class="card or-card"><div class="or-h"><h4>Talabalar <span class="muted">${orN(d.all)}${d.unmatched ? ` · <span class="bad">${d.unmatched} ta mos emas</span>` : ""}</span></h4>
      ${ed ? `<div class="row-actions"><button type="button" class="btn sm" id="orAdd">${ico("plus", 15)} Talaba qo'shish</button></div>` : ""}</div>
    ${ed ? `<div class="or-addbox hidden" id="orAddBox"><label class="or-search">${ico("search", 16)}<input id="orAddQ" placeholder="F.I.Sh., HEMIS ID yoki guruh (kamida 2 belgi)" aria-label="Talaba qidirish"></label><div id="orAddR" class="or-addr"></div></div>` : ""}
    <div class="or-filters"><label class="or-search">${ico("search", 16)}<input id="orIQ" placeholder="Ro'yxat ichida qidirish" value="${esc(OR.iq)}" aria-label="Ro'yxat ichida qidirish"></label>
      ${ed ? `<button type="button" class="btn sm" id="orRm" ${OR.sel.size ? "" : "disabled"}>${ico("trash", 15)} Tanlanganlarni olib tashlash${OR.sel.size ? ` (${OR.sel.size})` : ""}</button>
        ${d.unmatched ? `<button type="button" class="btn sm" id="orRmU">Mos kelmaganlarni olib tashlash (${d.unmatched})</button>` : ""}` : ""}</div>
    ${ed ? `<div class="tiny muted or-cnt">Har bir o'zgarish ro'yxatning yangi versiyasini yaratadi — eski versiyalar saqlanadi.</div>` : ""}
    <div class="or-items">${rows || `<div class="or-empty"><b>Ro'yxat bo'sh</b>${ed ? `<span class="tiny muted">Talaba qo'shing yoki Excel/CSV ro'yxat yuklang (o'ng tomonda).</span>` : ""}</div>`}</div>
    <div class="or-pager">${d.total > 100 ? `<span class="tiny muted">${orN(OR.ioff + 1)}–${orN(Math.min(OR.ioff + 100, d.total))} / ${orN(d.total)}</span>
      <button type="button" class="btn sm" id="orPrev" ${OR.ioff ? "" : "disabled"}>Oldingi</button><button type="button" class="btn sm" id="orNext" ${OR.ioff + 100 < d.total ? "" : "disabled"}>Keyingi</button>` : ""}</div></div>`;
}
function orVersionsCard(d) {
  const o = d.order, ed = d.can.edit;
  const df = OR.diff;
  return `<div class="card or-card"><div class="or-h"><h4>Ro'yxat versiyalari <span class="muted">${d.versions.length}</span></h4></div>
    ${ed && o.kind !== "bekor" ? `<label class="or-drop" id="orUpL">${ico("upload", 18)}<span><b>Yangi versiya yuklash</b><small>Excel (.xlsx) yoki CSV: HEMIS ID, F.I.Sh., Guruh ustunlari</small></span><input type="file" id="orUp" accept=".xlsx,.xlsm,.csv,.txt" hidden></label>` : ""}
    ${!ed && ["imzolangan", "bekor_qilingan"].includes(o.status) ? `<div class="tiny muted">${ico("lock", 13)} Imzolangan — ro'yxat muzlatilgan.</div>` : ""}
    <ol class="or-vers">${d.versions.map(v => `<li class="${v.no === o.version ? "cur" : ""}">
      <div class="or-vh"><b>${v.no}-versiya</b>${v.no === o.version ? `<span class="or-cur">joriy</span>` : ""}<span class="or-vd">${v.no > 1 ? `<i class="add">+${orN(v.added)}</i><i class="rem">−${orN(v.removed)}</i>` : ""}<i>${orN(v.count)} ta</i></span></div>
      <small>${esc(v.created_by_name || "")} · ${orWhen(v.created_at)}</small>
      <small>${esc(v.source || "")}${v.filename ? ` · ${esc(v.filename)}` : ""}${v.unmatched ? ` · <span class="bad">${v.unmatched} mos emas</span>` : ""}${v.restored_from ? ` · ${v.restored_from}-versiyadan` : ""}${v.note ? ` · ${esc(v.note)}` : ""}</small>
      <div class="row-actions">${v.no > 1 ? `<button type="button" class="btn ghost sm" data-diff="${v.no}" aria-expanded="${df?.no === v.no}">Farq</button>` : ""}<a class="btn ghost sm" href="/api/orders/${o.id}/xlsx?version=${v.no}">XLSX</a>
        ${ed && v.no !== o.version ? `<button type="button" class="btn ghost sm" data-restore="${v.no}">Tiklash</button>` : ""}</div>
      ${df?.no === v.no ? orDiffHtml(df) : ""}</li>`).join("") || `<li class="tiny muted">Hali versiya yo'q</li>`}</ol></div>`;
}
function orDiffHtml(df) {
  const li = (xs, cls) => xs.map(x => `<li class="${cls}">${esc(x.full_name)} <small>${esc(x.hemis_id || "")} · ${esc(x.group_name || "")}${x.matched ? "" : " · mos emas"}</small></li>`).join("");
  return `<div class="or-diff"><div class="tiny muted">${df.against}-versiya (${orN(df.count_a)}) → ${df.no}-versiya (${orN(df.count_b)})</div>
    <div class="or-dcol"><b class="add">Qo'shilgan: ${orN(df.n_added)}</b><ul>${li(df.added, "add")}${df.n_added > df.added.length ? `<li class="tiny muted">… yana ${df.n_added - df.added.length}</li>` : ""}</ul></div>
    <div class="or-dcol"><b class="rem">Olib tashlangan: ${orN(df.n_removed)}</b><ul>${li(df.removed, "rem")}${df.n_removed > df.removed.length ? `<li class="tiny muted">… yana ${df.n_removed - df.removed.length}</li>` : ""}</ul></div>
    ${df.n_changed ? `<div class="or-dcol"><b>Maydoni o'zgargan: ${orN(df.n_changed)}</b><ul>${df.changed.map(x => `<li>${esc(x.full_name)}</li>`).join("")}</ul></div>` : ""}</div>`;
}
function orFilesCard(d) {
  if (!d.files.length) return "";
  return `<div class="card or-card"><h4>Ilova fayllar <span class="muted">${d.files.length}</span></h4><ul class="or-files">${d.files.map(f => `<li><a href="/api/orders/files/${f.id}">${ico("file", 14)} ${esc(f.filename)}</a><small>${esc(f.kind)} · ${esc(f.uploaded_name || "")} · ${orWhen(f.uploaded_at)}</small></li>`).join("")}</ul></div>`;
}
function orLogCard(d) {
  return `<div class="card or-card"><h4>Jurnal</h4><ol class="or-log">${d.log.map(l => `<li><b>${esc(l.action)}</b><small>${orWhen(l.ts)} · ${esc(l.user_name || "")}</small>${l.detail ? `<span>${esc(l.detail)}</span>` : ""}</li>`).join("")}</ol></div>`;
}
function orBind(d) {
  const o = d.order, b = $("#orBody");
  $("#orBack").onclick = () => { OR.id = null; orShell(); };
  b.querySelectorAll("[data-open]").forEach(a => a.onclick = e => { e.preventDefault(); orOpen(+a.dataset.open); });
  const reload = () => orDetail(o.id, true);
  b.querySelectorAll(".or-acts [data-a]").forEach(btn => btn.onclick = () => {
    const a = btn.dataset.a;
    const big = d.all > 50 ? ` Ro'yxatda ${orN(d.all)} ta talaba.` : "";
    const C = {
      submit: {text: `Buyruq loyihasi imzoga yuboriladi.${big} Yuborilgach ro'yxatni o'zgartirib bo'lmaydi (qaytarilsa — mumkin).`, yes: "Yuborish", go: () => orApi(`/api/orders/${o.id}/submit`, {}), ok: "Imzoga yuborildi"},
      forward: {text: "Buyruq loyihasini kelishasizmi? Rektor imzosiga o'tadi.", yes: "Kelishaman", go: () => orApi(`/api/orders/${o.id}/forward`, {}), ok: "Kelishildi"},
      sign: {text: `<b>Imzolash.</b> Buyruq ro'yxatga olinadi (raqam, sana) va ta'siri talabalar bazasiga avtomatik o'tadi.${big}${d.checks.warnings.length ? " Ogohlantirishlarni ko'rib chiqing." : ""}`, yes: "Imzolayman",
             go: () => orApi(`/api/orders/${o.id}/sign`, {}), ok: null},
      delete: {text: "Loyiha o'chiriladi (versiyalar va jurnal saqlanadi).", yes: "O'chirish", go: () => orApi(`/api/orders/${o.id}/delete`, {}), ok: "Loyiha o'chirildi"},
      return: {note: true, label: "Qaytarish sababi", ph: "Masalan: 3-qatordagi talabaning sanasi noto'g'ri", yes: "Qaytarish", go: n => orApi(`/api/orders/${o.id}/return`, {note: n}), ok: "Registrator ofisiga qaytarildi"},
      annul: {note: true, label: "Bekor qilish sababi", ph: "Masalan: talaba arizasini qaytarib oldi", yes: "Loyiha tuzish", go: n => orApi(`/api/orders/${o.id}/annul`, {note: n}), ok: "Bekor qiluvchi buyruq loyihasi tuzildi"},
    }[a];
    OR.confirm = C; orDetail(o.id, true).then(() => {
      $("#orCN")?.focus();
      $("#orCX").onclick = () => { OR.confirm = null; reload(); };
      $("#orCY").onclick = e => orDo(e.target, async () => {
        const r = await C.go(C.note ? $("#orCN").value : undefined);
        OR.confirm = null;
        if (a === "sign") toast(`Imzolandi: ${r.reg_no}` + (r.changed != null ? ` · bazaga ta'sir: ${r.changed} ta talaba` : "") + (r.reverted != null ? ` · qaytarildi: ${r.reverted}` : ""));
        else toast(C.ok);
        if (a === "annul") return orOpen(r.id);
        if (a === "delete") { OR.id = null; return orShell(); }
        await reload(); if (typeof badges === "function") badges();
      });
    });
  });
  if ($("#orPS")) $("#orPS").onclick = e => orDo(e.target, async () => {
    const params = {}; orKind(o.kind).fields.forEach(f => { const x = $("#orPP_" + f); if (x) params[f] = x.value; });
    await orApi(`/api/orders/${o.id}/edit`, {title: $("#orPT").value, basis: $("#orPB").value, note: $("#orPN").value, params}); await reload();
  }, "Saqlandi");
  document.querySelectorAll('[id^="orPP_group_to"],[id^="orIE_group_to"]').forEach(orGroupList);
  /* ro'yxat */
  let t; if ($("#orIQ")) $("#orIQ").oninput = () => { clearTimeout(t); t = setTimeout(() => { OR.iq = $("#orIQ").value.trim(); OR.ioff = 0; reload().then(() => { const i = $("#orIQ"); i.focus(); i.setSelectionRange(i.value.length, i.value.length); }); }, 300); };
  if ($("#orPrev")) $("#orPrev").onclick = () => { OR.ioff = Math.max(0, OR.ioff - 100); reload(); };
  if ($("#orNext")) $("#orNext").onclick = () => { OR.ioff += 100; reload(); };
  b.querySelectorAll(".or-cb").forEach(cb => cb.onchange = () => { const id = +cb.dataset.id; cb.checked ? OR.sel.add(id) : OR.sel.delete(id); cb.closest(".or-it").classList.toggle("sel", cb.checked);
    const rm = $("#orRm"); rm.disabled = !OR.sel.size; rm.innerHTML = `${ico("trash", 15)} Tanlanganlarni olib tashlash${OR.sel.size ? ` (${OR.sel.size})` : ""}`; });
  if ($("#orRm")) $("#orRm").onclick = e => orDo(e.target, async () => { const r = await orApi(`/api/orders/${o.id}/items`, {remove: [...OR.sel]}); OR.sel = new Set(); toast(`${r.version.no}-versiya: −${r.version.removed}`); await reload(); });
  if ($("#orRmU")) $("#orRmU").onclick = e => orDo(e.target, async () => {
    const all = await orApi(`/api/orders/${o.id}?limit=500&q=`); const ids = all.items.filter(i => !i.student_id).map(i => i.id);
    let extra = []; if (all.total > 500) for (let off = 500; off < all.total; off += 500) { const p = await orApi(`/api/orders/${o.id}?limit=500&offset=${off}`); extra = extra.concat(p.items.filter(i => !i.student_id).map(i => i.id)); }
    const r = await orApi(`/api/orders/${o.id}/items`, {remove: ids.concat(extra)}); toast(`${r.version.no}-versiya: −${r.version.removed}`); await reload();
  });
  b.querySelectorAll("[data-edit]").forEach(x => x.onclick = () => { OR.editItem = +x.dataset.edit; reload(); });
  if ($("#orIEX")) $("#orIEX").onclick = () => { OR.editItem = null; reload(); };
  if ($("#orIES")) $("#orIES").onclick = e => orDo(e.target, async () => {
    const data = {}; orKind(o.kind).fields.forEach(f => { const x = $("#orIE_" + f); if (x) data[f] = x.value; });
    const r = await orApi(`/api/orders/${o.id}/items`, {update: [{id: +e.target.dataset.id, data}]}); OR.editItem = null; toast(`Saqlandi · ${r.version.no}-versiya`); await reload();
  });
  if ($("#orAdd")) $("#orAdd").onclick = () => { const bx = $("#orAddBox"); bx.classList.toggle("hidden"); if (!bx.classList.contains("hidden")) $("#orAddQ").focus(); };
  if ($("#orAddQ")) { let t2; $("#orAddQ").oninput = () => { clearTimeout(t2); t2 = setTimeout(async () => {
    const q = $("#orAddQ").value.trim(); if (q.length < 2) { $("#orAddR").innerHTML = ""; return; }
    const rs = await orApi(`/api/orders/lookup/students?q=${encodeURIComponent(q)}`);
    $("#orAddR").innerHTML = rs.map(s => `<button type="button" class="or-pick" data-sid="${s.id}"><b>${esc(s.full_name)}</b><small>${esc(s.hemis_id)} · ${esc(s.grp || "")} · ${esc(s.study_form)} · ${esc(s.status)}</small>${ico("plus", 15)}</button>`).join("") || `<div class="tiny muted">Topilmadi</div>`;
    $("#orAddR").querySelectorAll(".or-pick").forEach(p => p.onclick = () => orDo(p, async () => { const r = await orApi(`/api/orders/${o.id}/items`, {add: [{student_id: +p.dataset.sid}]}); toast(`Qo'shildi · ${r.version.no}-versiya`); await reload(); }));
  }, 250); }; }
  /* versiyalar */
  if ($("#orUp")) $("#orUp").onchange = () => { const f = $("#orUp").files[0]; if (!f) return;
    const L = $("#orUpL"); L.classList.add("busy");
    orDo(null, async () => { const r = await orUp(`/api/orders/${o.id}/upload`, f); toast(`${r.version.no}-versiya: ${orN(r.version.count)} ta (+${orN(r.version.added)} / −${orN(r.version.removed)})${r.unmatched.length ? ` · ${r.version.unmatched} ta mos emas` : ""}`); OR.diff = null; await reload(); })
      .finally(() => L.isConnected && L.classList.remove("busy")); };
  b.querySelectorAll("[data-diff]").forEach(x => x.onclick = () => orDo(x, async () => { const no = +x.dataset.diff; OR.diff = OR.diff?.no === no ? null : await orApi(`/api/orders/${o.id}/versions/${no}/diff`); await reload(); }));
  b.querySelectorAll("[data-restore]").forEach(x => x.onclick = () => orDo(x, async () => { const r = await orApi(`/api/orders/${o.id}/versions/${x.dataset.restore}/restore`, {}); toast(`${x.dataset.restore}-versiya tiklandi → ${r.version.no}-versiya`); await reload(); }));
}

/* ---------- arizadan buyruq ---------- */
function orIntake() {
  const b = $("#orBody"), m = OR.meta, smp = m.samples.filter(s => s.type === "ariza");
  b.innerHTML = `<div class="or-grid2"><div class="card or-card"><h4>1. Arizani yuklang yoki matnini kiriting</h4>
      <label class="or-drop big" id="orInL">${ico("upload", 22)}<span><b>Ariza faylini tanlang</b><small>PDF, DOCX, TXT yoki rasm (JPG/PNG). ${m.ocr ? "Skan va rasmlar OCR orqali o'qiladi." : "OCR serverda yo'q — skan/rasm uchun matnni qo'lda kiriting."}</small></span><input type="file" id="orIn" accept=".pdf,.docx,.txt,.png,.jpg,.jpeg" hidden></label>
      <div class="or-or"><span>yoki</span></div>
      <label class="or-l">Ariza matni<textarea id="orInT" rows="6" placeholder="Men, Familiya Ism Otasining ismi, … akademik ta'til berishingizni so'rayman."></textarea></label>
      <button type="button" class="btn sm" id="orInGo">${ico("search", 15)} Matnni tahlil qilish</button>
      ${smp.length ? `<h4 class="or-mt">Namuna arizalar <span class="muted tiny">(sun'iy, demo)</span></h4><ul class="or-smp">${smp.map(s => `<li><span><b>${esc(s.title)}</b><small>${esc(s.note || s.format)}</small></span>
        <span class="row-actions"><button type="button" class="btn sm" data-smp="${esc(s.file)}">Sinab ko'rish</button><a class="btn ghost sm" href="/api/orders/samples/${encodeURIComponent(s.file)}" aria-label="Yuklab olish: ${esc(s.title)}">${ico("download", 14)}</a></span></li>`).join("")}</ul>` : ""}
    </div><div class="card or-card" id="orInR">${orIntakeResult()}</div></div>`;
  $("#orIn").onchange = () => { const f = $("#orIn").files[0]; if (!f) return; const L = $("#orInL"); L.classList.add("busy");
    orDo(null, async () => { OR.intake = await orUp("/api/orders/intake", f); orIntakeDraw(); }).finally(() => L.isConnected && L.classList.remove("busy")); };
  $("#orInGo").onclick = e => orDo(e.target, async () => { OR.intake = await orApi("/api/orders/intake/text", {text: $("#orInT").value}); orIntakeDraw(); });
  b.querySelectorAll("[data-smp]").forEach(x => x.onclick = () => orDo(x, async () => { OR.intake = await orApi(`/api/orders/intake/sample/${encodeURIComponent(x.dataset.smp)}`, {}); orIntakeDraw(); }));
  orIntakeBind();
}
const OR_METHOD = {"pdf-text": "PDF matn qatlami", docx: "DOCX matni", text: "Matnli fayl", ocr: "OCR (rasm/skan)", manual: "Qo'lda kiritish kerak", "qo'lda": "Qo'lda kiritilgan"};
function orIntakeResult() {
  const r = OR.intake;
  if (!r) return `<h4>2. Natija</h4><div class="or-empty">${ico("file", 22)}<b>Ariza hali tahlil qilinmagan</b><span class="tiny muted">Tizim ariza turini (familiya, akademik ta'til, ta'tildan qaytish, chetlashtirish, ko'chirish, guruh, qayta tiklash), maydonlarni va talabani aniqlaydi. Natijani tekshirib, loyiha tuzasiz.</span></div>`;
  const kinds = OR.meta.kinds.filter(k => !["qabul", "kurs", "bekor"].includes(k.key));
  const k = orKind(r.kind || "akademik_tatil");
  return `<h4>2. Natija ${r.filename ? `<span class="muted tiny">${esc(r.filename)}</span>` : ""}</h4>
    <div class="or-badges"><span class="or-tag">${esc(OR_METHOD[r.method] || r.method)}</span>${r.kind ? `<span class="or-tag ok">${esc(r.kind_name)} · ishonch ${Math.round(r.confidence * 100)}%</span>` : `<span class="or-tag warn">Tur aniqlanmadi</span>`}</div>
    ${r.note ? `<div class="or-note warn">${ico("info", 15)}<span>${esc(r.note)}</span></div>` : ""}
    <details class="or-txt" ${r.text ? "" : "open"}><summary>Ariza matni (${orN((r.text || "").length)} belgi) — tahrirlab qayta tahlil qilish mumkin</summary><textarea id="orRT" rows="8">${esc(r.text || "")}</textarea><button type="button" class="btn ghost sm" id="orRTG">Qayta tahlil</button></details>
    <div class="or-form"><label class="or-l">Buyruq turi<select id="orRK">${kinds.map(x => `<option value="${x.key}" ${x.key === (r.kind || "") ? "selected" : ""}>${esc(x.short)}</option>`).join("")}</select></label>
      ${r.alternatives?.length ? `<div class="tiny muted">Muqobil: ${r.alternatives.map(a => esc(a.name)).join(", ")}</div>` : ""}
      <div id="orRF">${orIntakeFields(r.kind || kinds[0].key)}</div></div>
    <h4 class="or-mt">Talaba</h4>
    <div class="or-cands">${(r.candidates || []).map((c, i) => `<label class="or-cand"><input type="radio" name="orCand" value="${c.id}" ${i === 0 ? "checked" : ""}><span><b>${esc(c.full_name)}</b><small>${esc(c.hemis_id)} · ${esc(c.grp || "")} · ${esc(c.study_form)} · ${esc(c.status)}</small><small class="or-why ${c.score >= .95 ? "ok" : ""}">${esc(c.why)} · ${Math.round(c.score * 100)}%</small></span></label>`).join("") || `<div class="tiny muted">Arizadan talaba aniqlanmadi — qidiring:</div>`}</div>
    <label class="or-search">${ico("search", 16)}<input id="orRS" placeholder="Boshqa talabani qidirish: F.I.Sh. yoki HEMIS ID" aria-label="Talaba qidirish"></label><div id="orRSR" class="or-addr"></div>
    <h4 class="or-mt">3. Loyiha</h4>
    <label class="or-l">Qayerga<select id="orRD"><option value="0">Yangi buyruq loyihasi</option>${(r.drafts || []).map(x => `<option value="${x.id}">Mavjud loyihaga qo'shish: #${x.id} · ${esc(x.title)} (${x.count} ta)</option>`).join("")}</select></label>
    <button type="button" class="btn primary" id="orRGo">${ico("scroll", 16)} Buyruq loyihasini tayyorlash</button>`;
}
function orIntakeFields(kind) {
  const k = orKind(kind), f = (OR.intake?.kind === kind ? OR.intake.fields : {}) || {};
  return k.fields.map(x => `<label class="or-l">${esc(orLbl(x))}${k.req.includes(x) ? " *" : ""}${orInput(x, f[x], "orRF_" + x)}</label>`).join("") + (f._to_guess ? `<div class="tiny muted">«Sanagacha» arizada yo'q — 1 yil deb taxmin qilindi, tekshiring.</div>` : "");
}
function orIntakeDraw() { $("#orInR").innerHTML = orIntakeResult(); orIntakeBind(); $("#orInR").scrollIntoView({behavior: "smooth", block: "start"}); }
function orIntakeBind() {
  if (!OR.intake || !$("#orRK")) return;
  $("#orRK").onchange = () => { $("#orRF").innerHTML = orIntakeFields($("#orRK").value); document.querySelectorAll('[id^="orRF_group_to"]').forEach(orGroupList); };
  document.querySelectorAll('[id^="orRF_group_to"]').forEach(orGroupList);
  $("#orRTG").onclick = e => orDo(e.target, async () => { OR.intake = await orApi("/api/orders/intake/text", {text: $("#orRT").value}); orIntakeDraw(); });
  let t; $("#orRS").oninput = () => { clearTimeout(t); t = setTimeout(async () => {
    const q = $("#orRS").value.trim(); if (q.length < 2) { $("#orRSR").innerHTML = ""; return; }
    const rs = await orApi(`/api/orders/lookup/students?q=${encodeURIComponent(q)}`);
    $("#orRSR").innerHTML = rs.map(s => `<button type="button" class="or-pick" data-sid="${s.id}"><b>${esc(s.full_name)}</b><small>${esc(s.hemis_id)} · ${esc(s.grp || "")} · ${esc(s.status)}</small>${ico("check", 15)}</button>`).join("") || `<div class="tiny muted">Topilmadi</div>`;
    $("#orRSR").querySelectorAll(".or-pick").forEach(p => p.onclick = () => {
      const s = rs.find(x => x.id === +p.dataset.sid);
      OR.intake.candidates = [{...s, score: 1, why: "qo'lda tanlandi"}].concat((OR.intake.candidates || []).filter(c => c.id !== s.id));
      const kind = $("#orRK").value; OR.intake.kind = kind; orIntakeDraw();
    });
  }, 250); };
  $("#orRGo").onclick = e => orDo(e.target, async () => {
    const sid = +(document.querySelector('input[name="orCand"]:checked')?.value || 0);
    if (!sid) throw Object.assign(new Error("api"), {msg: "Talabani tanlang"});
    const kind = $("#orRK").value, fields = {}; orKind(kind).fields.forEach(f => { const x = $("#orRF_" + f); if (x && x.value) fields[f] = x.value; });
    const r = await orApi(`/api/orders/intake/${OR.intake.app_id}/order`, {kind, student_id: sid, fields, order_id: +$("#orRD").value});
    toast("Buyruq loyihasi tayyor"); OR.intake = null; OR.tab = "reg"; orOpen(r.id);
  });
}

/* ---------- ro'yxatdan buyruq ---------- */
function orBulk() {
  const b = $("#orBody"), m = OR.meta, smp = m.samples.filter(s => s.type === "royxat");
  const kinds = m.kinds.filter(k => k.key !== "bekor");
  b.innerHTML = `<div class="or-grid2"><div class="card or-card"><h4>Katta ro'yxat asosida buyruq</h4>
      <p class="tiny muted">Masalan, kontrakt qarzdorlarini chetlashtirish (minglab talaba). Excel/CSV yuklanadi → talabalar HEMIS ID (yoki F.I.Sh. + guruh) bo'yicha topiladi →
      1-versiya. Keyin to'lov qilganlarni chiqarib yangi fayl yuklasangiz — 2-versiya (eski versiya saqlanadi, kim/qachon, +/− farq ko'rinadi). Buyruq DOCX oxirgi versiyadan; imzodan keyin ro'yxat muzlatiladi.</p>
      <div class="or-form"><label class="or-l">Buyruq turi<select id="orBK">${kinds.map(k => `<option value="${k.key}" ${k.key === "chetlashtirish_tolov" ? "selected" : ""}>${esc(k.short)}</option>`).join("")}</select></label>
        <label class="or-l">Sarlavha<input id="orBT" placeholder="bo'sh qolsa — shablon"></label>
        <div id="orBP"></div>
        <label class="or-drop" id="orBL">${ico("upload", 18)}<span><b id="orBFn">Ro'yxat faylini tanlang</b><small>.xlsx yoki .csv · ustunlar: HEMIS ID, F.I.Sh., Guruh</small></span><input type="file" id="orBF" accept=".xlsx,.xlsm,.csv,.txt" hidden></label>
        <button type="button" class="btn primary" id="orBGo" disabled>${ico("layers", 16)} Loyiha va 1-versiyani yaratish</button></div></div>
    <div class="card or-card"><h4>Namuna ro'yxatlar <span class="muted tiny">(sun'iy, demo)</span></h4>
      <ul class="or-smp">${smp.map(s => `<li><span><b>${esc(s.title)}</b><small>${esc(s.format)}</small></span><a class="btn ghost sm" href="/api/orders/samples/${encodeURIComponent(s.file)}">${ico("download", 14)} Yuklab olish</a></li>`).join("") || `<li class="tiny muted">Namuna yo'q</li>`}</ul>
      <p class="tiny muted">Faylni yuklab oling, so'ng chap tomondan yuklang — yoki mavjud loyihani ochib «Yangi versiya yuklash» bilan ikkinchi faylni yuklang va «Farq»ni ko'ring.</p></div></div>`;
  const params = () => { const k = orKind($("#orBK").value); $("#orBP").innerHTML = k.fields.filter(f => f.startsWith("date_") || f === "target" || f === "reason" || f === "group_to").map(f => `<label class="or-l">${esc(orLbl(f))} (barchasi uchun)${orInput(f, f === "date_from" ? new Date(Date.now() + 864e6).toISOString().slice(0, 10) : "", "orBP_" + f)}</label>`).join("");
    document.querySelectorAll('[id^="orBP_group_to"]').forEach(orGroupList); };
  $("#orBK").onchange = params; params();
  $("#orBF").onchange = () => { const f = $("#orBF").files[0]; $("#orBFn").textContent = f ? f.name : "Ro'yxat faylini tanlang"; $("#orBGo").disabled = !f; };
  $("#orBGo").onclick = e => orDo(e.target, async () => {
    const f = $("#orBF").files[0], kind = $("#orBK").value, p = {};
    orKind(kind).fields.forEach(x => { const el = $("#orBP_" + x); if (el && el.value) p[x] = el.value; });
    const o = await orApi("/api/orders", {kind, title: $("#orBT").value || null, params: p, students: []});
    try { const r = await orUp(`/api/orders/${o.id}/upload`, f); toast(`1-versiya: ${orN(r.version.count)} ta${r.version.unmatched ? ` · ${r.version.unmatched} ta mos emas` : ""}`); }
    catch (err) { toast(err.msg || "Ro'yxatni yuklab bo'lmadi"); }
    OR.tab = "reg"; orOpen(o.id);
  });
}

/* ---------- muammoli talabalar ---------- */
async function orAudit() {
  const b = $("#orBody");
  b.innerHTML = `<div class="card or-card"><div class="or-empty">${ico("refresh", 20)}<b>Reyestr va baza solishtirilmoqda…</b></div></div>`;
  OR.issues = await orApi("/api/orders/audit/issues");
  orAuditDraw();
}
function orAuditDraw() {
  const b = $("#orBody"), r = OR.issues, c = orCan();
  const qq = OR.iq2.toLowerCase().replace(/[ʻʼ‘’`´]/g, "'");
  const list = r.items.filter(x => (!OR.ifilter || x.kind === OR.ifilter) && (!qq || `${x.student.full_name} ${x.student.hemis_id} ${x.student.grp}`.toLowerCase().replace(/[ʻʼ‘’`´]/g, "'").includes(qq)));
  b.innerHTML = `<div class="src-note or-src">${ico("info", 15)}<span>Imzolangan buyruqlar reyestri (${orN(r.orders)} ta buyruq) bilan ${orN(r.students)} ta talaba ma'lumoti solishtirildi. ${c.fix ? "Har bir holat uchun tuzatish: avval asos hujjatni tanlang (reyestrdagi buyruq yoki PDF), so'ng amalni bajaring." : "Faqat ko'rish rejimi."}${r.resolved ? ` Hal qilingan: ${r.resolved}.` : ""}</span></div>
    <div class="or-tiles">${r.summary.map(s => `<button type="button" class="or-tile${OR.ifilter === s.kind ? " on" : ""}${s.count ? "" : " zero"}" data-k="${s.kind}" title="${esc(s.desc)}" aria-pressed="${OR.ifilter === s.kind}"><b>${s.count}</b><span>${esc(s.title)}</span></button>`).join("")}</div>
    <div class="card or-card"><div class="or-filters"><label class="or-search">${ico("search", 16)}<input id="orAQ" placeholder="Talaba, HEMIS ID yoki guruh" value="${esc(OR.iq2)}" aria-label="Qidiruv"></label>
      ${OR.ifilter ? `<button type="button" class="btn ghost sm" id="orAF">${ico("x", 14)} Filtrni olib tashlash</button>` : ""}</div>
      <div class="or-issues">${list.map(orIssueHtml).join("") || `<div class="or-empty">${ico("checkc", 22)}<b>Muammo topilmadi</b><span class="tiny muted">Reyestr va baza mos.</span></div>`}</div></div>`;
  b.querySelectorAll(".or-tile").forEach(t => t.onclick = () => { OR.ifilter = OR.ifilter === t.dataset.k ? "" : t.dataset.k; orAuditDraw(); });
  if ($("#orAF")) $("#orAF").onclick = () => { OR.ifilter = ""; orAuditDraw(); };
  let tt; $("#orAQ").oninput = () => { clearTimeout(tt); tt = setTimeout(() => { OR.iq2 = $("#orAQ").value.trim(); orAuditDraw(); const i = $("#orAQ"); i.focus(); i.setSelectionRange(i.value.length, i.value.length); }, 250); };
  b.querySelectorAll("[data-open]").forEach(a => a.onclick = e => { e.preventDefault(); OR.tab = "reg"; orOpen(+a.dataset.open); });
  b.querySelectorAll("[data-fix]").forEach(x => x.onclick = () => { OR.fixOpen = OR.fixOpen === x.dataset.fix ? null : x.dataset.fix; orAuditDraw(); if (OR.fixOpen) orFixLoad(OR.fixOpen); });
  if (OR.fixOpen) orFixBind(OR.fixOpen);
}
function orIssueHtml(x) {
  const open = OR.fixOpen === x.key, s = x.student, c = orCan();
  return `<div class="or-iss${open ? " open" : ""}"><div class="or-issh"><span class="or-ik ${x.kind}">${esc(x.title)}</span>
      <div class="or-itm"><b>${esc(s.full_name)}</b><small>${esc(s.hemis_id)} · ${esc(s.grp || "")} · ${s.course || "?"}-kurs · ${esc(s.study_form)} · ${esc(s.status)}</small>
        <span class="or-idet">${esc(x.detail)}</span>
        ${x.orders.length ? `<span class="or-irefs">${x.orders.map(o => `<a href="#" data-open="${o.id}">${esc(o.reg_no)} · ${esc(o.kind_name)} · ${dmy(o.date)}</a>`).join("")}</span>` : ""}</div>
      ${c.fix ? `<button type="button" class="btn sm" data-fix="${esc(x.key)}" aria-expanded="${open}">${open ? "Yopish" : "Tuzatish"}</button>` : ""}</div>
    ${open ? `<div class="or-fix" id="orFix"><div class="tiny muted">Yuklanmoqda…</div></div>` : ""}</div>`;
}
async function orFixLoad(key) {
  const x = OR.issues.items.find(i => i.key === key); if (!x) return;
  let hist = null; try { hist = await orApi(`/api/orders/student/${x.student.id}`); } catch (e) {}
  const signed = (hist?.orders || []).filter(o => o.status === "imzolangan");
  const st = OR.fixDoc[key] || (OR.fixDoc[key] = {ref: x.orders[0]?.id || 0, file: 0, fname: ""});
  const box = $("#orFix"); if (!box) return;
  box.innerHTML = `<div class="or-fstep"><b>1. Asos hujjat</b>
      <label class="or-l">Reyestrdagi imzolangan buyruq<select id="orFR"><option value="0">— tanlanmagan —</option>${signed.map(o => `<option value="${o.id}" ${o.id === st.ref ? "selected" : ""}>${esc(o.reg_no)} · ${esc(o.kind_name)} · ${dmy(o.order_date)}${o.group_name ? " · " + esc(o.group_name) : ""}</option>`).join("")}</select></label>
      <label class="or-drop sm" id="orFUL">${ico("upload", 16)}<span><b id="orFUN">${st.file ? esc(st.fname) + " — yuklandi" : "yoki buyruq PDF/skanini yuklang"}</b><small>PDF, DOCX yoki rasm</small></span><input type="file" id="orFU" accept=".pdf,.docx,.png,.jpg,.jpeg" hidden></label></div>
    <div class="or-fstep"><b>2. Amal</b><label class="or-l">Izoh${x.actions.some(a => a.action === "izoh") ? " («Hujjat bilan izohlash» uchun majburiy)" : ""}<textarea id="orFN" rows="2" placeholder="Masalan: qog'oz arxivdagi 2023-yil 145-son buyruqda bor"></textarea></label>
      <div class="row-actions">${x.actions.map(a => `<button type="button" class="btn sm ${a.action === x.actions[0].action ? "primary" : ""}" data-act="${a.action}" ${a.allowed ? "" : "disabled"} title="${esc(a.hint)}${a.allowed ? "" : " — boshqa bo'lim vakolati"}">${esc(a.label)}</button>`).join("")}</div>
      <div class="tiny muted" id="orFH">${x.actions.some(a => a.needs_doc) ? "«Guruhga biriktirish», «Holatni …» va «Hujjat bilan izohlash» uchun avval asos hujjat tanlanadi." : ""}</div></div>`;
  orFixBind(key);
}
function orFixBind(key) {
  const x = OR.issues.items.find(i => i.key === key), st = OR.fixDoc[key]; if (!x || !st || !$("#orFR")) return;
  const sync = () => { document.querySelectorAll("#orFix [data-act]").forEach(b => { const a = x.actions.find(y => y.action === b.dataset.act); b.disabled = !a.allowed || (a.needs_doc && !st.ref && !st.file); }); };
  $("#orFR").onchange = () => { st.ref = +$("#orFR").value; sync(); };
  $("#orFU").onchange = () => { const f = $("#orFU").files[0]; if (!f) return; const L = $("#orFUL"); L.classList.add("busy");
    orDo(null, async () => { const r = await orUp(`/api/orders/files?student_id=${x.student.id}&kind=asos`, f); st.file = r.id; st.fname = f.name; $("#orFUN").textContent = f.name + " — yuklandi"; sync(); })
      .finally(() => L.isConnected && L.classList.remove("busy")); };
  document.querySelectorAll("#orFix [data-act]").forEach(b => b.onclick = () => orDo(b, async () => {
    const r = await orApi("/api/orders/audit/fix", {key, action: b.dataset.act, file_id: st.file || 0, ref_order_id: st.ref || 0, note: $("#orFN").value});
    toast(r.order_id ? "Tuzatuvchi buyruq loyihasi tuzildi" : "Tuzatildi");
    OR.fixOpen = null; delete OR.fixDoc[key];
    if (r.order_id) { OR.tab = "reg"; return orOpen(r.order_id); }
    await orAudit();
  }));
  sync();
}

/* ---------- o'zgarishlar jurnali ---------- */
async function orChanges(more) {
  const b = $("#orBody");
  if (!more) {
    b.innerHTML = `<div class="card or-card"><div class="or-filters"><label class="or-search">${ico("search", 16)}<input id="orChQ" placeholder="Talaba, HEMIS ID, buyruq raqami yoki qiymat" value="${esc(OR.chq)}" aria-label="Qidiruv"></label></div>
      <div class="tiny muted or-cnt" id="orChC"></div><div class="tw"><table class="or-tbl"><thead><tr><th>Sana</th><th>Talaba</th><th>Maydon</th><th>Eski → Yangi</th><th>Asos</th><th>Kim</th></tr></thead><tbody id="orChB"></tbody></table></div><div id="orChM"></div></div>`;
    let t; $("#orChQ").oninput = () => { clearTimeout(t); t = setTimeout(() => { OR.chq = $("#orChQ").value.trim(); orChanges(); }, 300); };
    OR.chRows = [];
  }
  const r = await orApi(`/api/orders/changes/log?` + new URLSearchParams({q: OR.chq, offset: OR.chRows.length, limit: 100}));
  OR.chRows = OR.chRows.concat(r.items);
  $("#orChC").textContent = `${orN(r.total)} ta o'zgarish · buyruq imzolanganda yoki muvofiqlik tuzatishida avtomatik yoziladi`;
  $("#orChB").innerHTML = OR.chRows.map(x => `<tr class="${x.reverted ? "or-rev" : ""}"><td class="nowrap">${orWhen(x.ts)}</td><td><b>${esc(x.cur_name)}</b><br><small class="muted">${esc(x.hemis_id)}</small></td>
    <td>${esc(FIELD_NAMES[x.field] || x.field)}</td><td><s>${esc(x.old ?? "—")}</s> → <b>${esc(x.new ?? "—")}</b>${x.reverted ? ` <span class="or-tag warn">qaytarilgan</span>` : ""}</td>
    <td>${x.order_id ? `<a href="#" data-open="${x.order_id}">${esc(x.reg_no || "#" + x.order_id)}</a>` : ""}<br><small class="muted">${esc(x.note || "")}</small></td><td>${esc(x.user_name || "")}</td></tr>`).join("")
    || `<tr><td colspan="6" class="muted">O'zgarishlar hali yo'q — buyruq imzolanganda bu yerda paydo bo'ladi.</td></tr>`;
  $("#orChB").querySelectorAll("[data-open]").forEach(a => a.onclick = e => { e.preventDefault(); OR.tab = "reg"; orOpen(+a.dataset.open); });
  $("#orChM").innerHTML = OR.chRows.length < r.total ? `<button type="button" class="btn sm" id="orChMB">Yana</button>` : "";
  if ($("#orChMB")) $("#orChMB").onclick = e => orDo(e.target, () => orChanges(true));
}

/* ---------- menyu belgisi ---------- */
async function ordersBadge(set) {
  if (!["rektor", "prorektor_oquv"].includes(ME?.role_key)) return;
  try { const m = await orApi("/api/orders/meta"); set("orders", ME.role_key === "rektor" ? m.pending.sign : m.pending.forward); } catch (e) {}
}
