/* =====================================================================
   «Xodimlar ta'tili» — xizmat safari, mehnat ta'tili, kasallik varaqasi, o'quv ta'tili (app/staff_absence.py, /api/staffabs).
     kadrlar:           ro'yxatga olish, tahrir, bekor qilish, asos hujjat, mehnat ta'tili buyrug'i (Hujjatlar markazi).
     kafedra mudiri:    o'z kafedrasi — ta'sir va o'rinbosar tayinlash.
     akademik:          barcha ta'sir va jadval o'zgarishlari (ko'rish). rektor, o'quv prorektori: ro'yxat va tahlil.
     o'qituvchi:        o'z yo'qliklari va o'zi o'rinbosar bo'lgan darslar.
   Ruxsatlar serverda tekshiriladi — bu yerda faqat tugmalar ko'rsatiladi/yashiriladi. Tasdiqlashlar sahifa ichida (confirm ishlatilmaydi).
   Global: renderStaffabs() — app.js go() chaqiradi.
   app.js yordamchilaridan foydalanadi: $, esc, J, toast, busy, ico, ICONS, hydrateIcons, dmy, ME, errCard, locked, showLogin.
   ===================================================================== */
const SA = {meta: null, tab: "list", period: "active", kind: "", dept: 0, q: "", list: null, open: null, d: null, form: null, needs: null, days: 14, sug: null, edit: false, cancel: false};
if (!document.querySelector('link[href="staffabs.css"]')) document.head.insertAdjacentHTML("beforeend", '<link rel="stylesheet" href="staffabs.css">');
if (typeof ICONS === "object") {
  Object.assign(ICONS, Object.fromEntries(Object.entries({
    plane: '<path d="M17.8 19.2 16 11l3.5-3.5C21 6 21.5 4 21 3c-1-.5-3 0-4.5 1.5L13 8 4.8 6.2c-.5-.1-.9.1-1.1.5l-.3.5c-.2.5-.1 1 .3 1.3L9 12l-2 3H4l-1 1 3 2 2 3 1-1v-3l3-2 3.5 5.3c.3.4.8.5 1.3.3l.5-.2c.4-.3.6-.7.5-1.2z"/>',
    plus: '<path d="M12 5v14M5 12h14"/>',
    upload: '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><path d="m17 8-5-5-5 5"/><path d="M12 3v12"/>',
    download: '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><path d="m7 10 5 5 5-5"/><path d="M12 15V3"/>',
    back: '<path d="m15 18-6-6 6-6"/>',
    pen: '<path d="M12 20h9"/><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4z"/>',
    swap: '<path d="M16 3h5v5"/><path d="M21 3 14 10"/><path d="M8 21H3v-5"/><path d="m3 21 7-7"/>',
  }).filter(([k]) => !ICONS[k])));
  try { const s = document.querySelector('#nav a[data-v="staffabs"] svg'); if (s && !s.innerHTML.trim()) { s.remove(); hydrateIcons(); } } catch (e) {}
}
const SA_KIND_CLS = {safar: "k-safar", mehnat: "k-mehnat", kasallik: "k-kasal", oquv: "k-oquv", boshqa: "k-boshqa"};
const SA_PHASE = {joriy: ["Hozir yo'q", "now"], kelgusi: ["Kelgusi", "next"], otgan: ["Tugagan", "past"], bekor: ["Bekor qilingan", "off"]};
const saDm = s => s ? `${s.slice(8, 10)}.${s.slice(5, 7)}` : "";
const saRange = (a, b) => a === b ? dmy(a) : `${saDm(a)}–${dmy(b)}`;
const saKind = (k, n) => `<span class="sa-kind ${SA_KIND_CLS[k] || ""}">${esc(n || (SA.meta?.kinds || {})[k] || k)}</span>`;
const saQs = () => new URLSearchParams(Object.entries({period: SA.period, kind: SA.kind, dept: SA.dept || "", q: SA.q}).filter(([, v]) => v !== ""));
const saShort = n => { const w = String(n || "").split(/\s+/); return w.length > 1 ? `${w[0]} ${w[1][0]}.` : w[0] || ""; };
async function saApi(url, body, method) {
  const r = await fetch(url, {method: method || (body === undefined ? "GET" : "POST"), credentials: "same-origin", headers: {"Content-Type": "application/json"},
                              body: body === undefined ? undefined : JSON.stringify(body)});
  if (r.status === 401) { showLogin(); throw new Error("auth"); }
  const d = await r.json().catch(() => ({}));
  if (!r.ok) { const m = d.message || (typeof d.detail === "string" ? d.detail : "") || "Xatolik yuz berdi"; if (body !== undefined || method) { toast(m); return null; } const e = new Error(r.status === 403 ? "denied" : "api"); e.msg = m; throw e; }
  return d;
}

/* ---------- asosiy ko'rinish ---------- */
async function renderStaffabs() {
  const el = $("#v-staffabs");
  if (!el.innerHTML) el.innerHTML = `<p class="muted">Yuklanmoqda…</p>`;
  SA.meta = await saApi("/api/staffabs/meta");
  const M = SA.meta, own = M.mode === "own";
  const tabs = own ? [["list", "Mening yo'qliklarim", "calendar"], ["changes", "O'rinbosarligim", "swap"]]
    : [["list", "Ro'yxat", "calendar"], ["needs", "O'rinbosar kerak", "users"], ["changes", "Jadval o'zgarishlari", "swap"], ["analytics", "Tahlil", "chart"]];
  if (!tabs.some(t => t[0] === SA.tab)) SA.tab = "list";
  const sub = {full: "Kadrlar bo'limi: safar, ta'til va kasallik varaqalarini ro'yxatga olish; dars jadvaliga ta'siri va o'rinbosarlar.",
    all: "Xodimlar va o'qituvchilar yo'qligi, dars jadvaliga ta'siri va o'rinbosarlar (ko'rish).",
    kaf: `${M.kafedra || ""} kafedrasi: yo'qliklar va darslarga o'rinbosar tayinlash.`, own: "Sizning safar, ta'til va kasallik yozuvlaringiz hamda siz o'rinbosar bo'lgan darslar."}[M.mode];
  el.innerHTML = `<div class="head sa-head"><div><h2>Xodimlar ta'tili va safarlari</h2><span class="muted">${esc(sub)}</span></div>
      ${M.can_edit ? `<div class="row-actions"><button class="btn primary" id="saNew">${ico("plus", 16)}Yangi yozuv</button></div>` : ""}</div>
    <div class="pn-tabs sa-tabs" role="tablist">${tabs.map(([k, l, i]) => `<button class="pn-tab${SA.tab === k ? " on" : ""}" role="tab" aria-selected="${SA.tab === k}" data-sat="${k}">${ico(i, 16)}${l}<em class="sa-tc" data-tc="${k}" hidden></em></button>`).join("")}</div>
    <div id="saBody"></div>`;
  el.querySelectorAll("[data-sat]").forEach(b => b.onclick = () => { SA.tab = b.dataset.sat; el.querySelectorAll("[data-sat]").forEach(x => { x.classList.toggle("on", x === b); x.setAttribute("aria-selected", x === b); }); saTab(); });
  if ($("#saNew")) $("#saNew").onclick = () => { SA.tab = "list"; SA.form = {}; SA.open = null; renderStaffabs(); };
  await saTab();
}
async function saTab() {
  const body = $("#saBody");
  try { await ({list: saList, needs: saNeeds, changes: saChanges, analytics: saAnalytics}[SA.tab] || saList)(); }
  catch (e) { if (e?.message === "auth") return; body.innerHTML = e?.message === "denied" ? locked("Bu bo'lim") : errCard("staffabs"); }
}

/* ---------- 1) ro'yxat + tafsilot ---------- */
async function saList() {
  const M = SA.meta, qs = saQs();
  const [L, A] = await Promise.all([saApi(`/api/staffabs?${qs}`), M.analytics ? saApi("/api/staffabs/analytics").catch(() => null) : null]);
  SA.list = L;
  const K = A?.kpi, kinds = Object.entries(M.kinds);
  const kpi = K ? `<div class="sa-kpis">
      <div class="sa-kpi"><b>${K.absent_now}</b><span>hozir yo'q</span><small>${kinds.filter(([k]) => K.by_kind_now[k]).map(([k, n]) => `${esc(n.split(" (")[0].toLowerCase())}: ${K.by_kind_now[k]}`).join(" · ") || "—"}</small></div>
      <div class="sa-kpi"><b>${K.teachers_now}</b><span>o'qituvchi hozir yo'q</span><small>darslariga o'rinbosar kerak</small></div>
      <div class="sa-kpi"><b>${K.upcoming_14}</b><span>14 kun ichida boshlanadi</span><small>rejadagi safar va ta'tillar</small></div>
      <div class="sa-kpi${A.overlaps.length ? " warn" : ""}"><b>${A.overlaps.length}</b><span>bir vaqtdagi yo'qlik</span><small>bir kafedra/bo'limda kesishgan</small></div></div>` : "";
  const per = [["active", "Joriy va kelgusi"], ["current", "Hozir"], ["upcoming", "Kelgusi"], ["past", "O'tgan"], ["all", "Hammasi"]];
  $("#saBody").innerHTML = `${kpi}<div class="sa-wrap${SA.open || SA.form ? " has-open" : ""}">
    <aside class="card sa-list">
      <div class="sa-flt">${per.map(([k, l]) => `<button class="${SA.period === k ? "on" : ""}" data-per="${k}">${l}</button>`).join("")}</div>
      <div class="sa-flt2"><select id="saKind" aria-label="Turi"><option value="">Barcha turlar</option>${kinds.map(([k, n]) => `<option value="${k}" ${SA.kind === k ? "selected" : ""}>${esc(n)}</option>`).join("")}</select>
        ${M.departments.length > 1 ? `<select id="saDept" aria-label="Kafedra"><option value="">Barcha kafedra va bo'limlar</option>${M.departments.map(d => `<option value="${d.id}" ${+SA.dept === d.id ? "selected" : ""}>${esc(d.name)}</option>`).join("")}</select>` : ""}
        <label class="sa-search">${ico("search", 15)}<input id="saQ" type="search" placeholder="F.I.Sh. yoki bo'lim" value="${esc(SA.q)}" aria-label="Qidirish"></label></div>
      <div class="sa-items" id="saItems">${L.items.length ? L.items.map(saItem).join("") : `<div class="sa-empty">${ico("calendar", 22)}<b>Yozuv yo'q</b><span class="muted">${M.mode === "own" ? "Sizda ro'yxatga olingan safar yoki ta'til yo'q." : "Bu filtr bo'yicha yozuv topilmadi."}</span></div>`}</div>
    </aside>
    <section class="card sa-read" id="saRead">${SA.form ? "" : SA.open ? `<p class="muted">Yuklanmoqda…</p>` : saEmpty(L)}</section></div>`;
  const b = $("#saBody");
  b.querySelectorAll("[data-per]").forEach(x => x.onclick = () => { SA.period = x.dataset.per; saList(); });
  $("#saKind").onchange = e => { SA.kind = e.target.value; saList(); };
  if ($("#saDept")) $("#saDept").onchange = e => { SA.dept = +e.target.value || 0; saList(); };
  let t; $("#saQ").oninput = e => { clearTimeout(t); t = setTimeout(async () => { SA.q = e.target.value.trim(); await saList(); const q = $("#saQ"); q.focus(); q.setSelectionRange(q.value.length, q.value.length); }, 300); };
  b.querySelectorAll("[data-sa]").forEach(x => x.onclick = () => { SA.form = null; SA.edit = false; SA.cancel = false; saOpen(+x.dataset.sa); });
  if (SA.form) saForm(); else if (SA.open) await saOpen(SA.open, true);
}
function saEmpty(L) {
  const n = L.items.filter(x => x.phase === "joriy").length, u = L.items.reduce((s, x) => s + (x.uncovered_future || 0), 0);
  return `<div class="sa-empty sa-empty-r">${ico("plane", 26)}<b>Yozuvni tanlang</b><span class="muted">Ro'yxatda: <b>${L.items.length}</b> ta${n ? ` · hozir yo'q: <b>${n}</b>` : ""}${u ? ` · o'rinbosarsiz darslar: <b class="bad">${u}</b>` : ""}</span>
    ${SA.meta.can_edit ? `<button class="btn primary" onclick="SA.form={};saList()">${ico("plus", 16)}Yangi yozuv</button>` : ""}</div>`;
}
function saItem(x) {
  const P = SA_PHASE[x.phase] || [x.phase, ""];
  return `<button class="sa-it${SA.open === x.id ? " on" : ""}${x.status === "bekor" ? " off" : ""}" data-sa="${x.id}">
    <span class="sa-it-top"><b>${esc(x.name)}</b><span class="sa-ph ${P[1]}">${P[0]}</span></span>
    <span class="sa-it-sub">${esc(x.position || "")}${x.unit ? ` · ${esc(x.unit)}` : ""}</span>
    <span class="sa-it-meta">${saKind(x.kind, x.kind_name)}<span class="sa-dt">${ico("calendar", 13)}${saRange(x.start, x.end)} · ${x.days} kun</span>
      ${x.teacher && x.status === "faol" && x.lessons_future ? `<span class="sa-les${x.uncovered_future ? " bad" : " ok"}" title="Kelgusi darslar: o'rinbosar tayinlangan / jami">${ico("users", 13)}${x.covered_future}/${x.lessons_future} o'rinbosar</span>` : ""}
      ${x.order ? `<span class="sa-tag">${ico("file", 13)}${esc(x.order.reg_no)}</span>` : ""}${x.files ? `<span class="sa-tag">${ico("clip", 13)}${x.files}</span>` : ""}</span>
  </button>`;
}
async function saOpen(id, keep) {
  SA.open = id;
  document.querySelectorAll("#saItems .sa-it").forEach(x => x.classList.toggle("on", +x.dataset.sa === id));
  document.querySelector(".sa-wrap")?.classList.add("has-open");
  const r = $("#saRead"); if (!keep) r.innerHTML = `<p class="muted">Yuklanmoqda…</p>`;
  let d; try { d = await saApi(`/api/staffabs/${id}`); } catch (e) { r.innerHTML = e?.message === "denied" ? locked("Bu yozuv") : errCard("staffabs"); return; }
  if (SA.open !== id) return;
  SA.d = d;
  const P = SA_PHASE[d.phase] || [d.phase, ""], L = d.lesson_list || [], fut = L.filter(x => !x.past);
  const byDate = {}; L.forEach(x => (byDate[x.date] = byDate[x.date] || []).push(x));
  const showPast = SA.showPast, dates = Object.keys(byDate).filter(k => showPast || byDate[k].some(x => !x.past));
  const pastN = Object.keys(byDate).length - Object.keys(byDate).filter(k => byDate[k].some(x => !x.past)).length;
  r.innerHTML = `<div class="sa-d">
    <div class="sa-d-h"><button class="btn sm ghost sa-back" id="saBack">${ico("back", 16)}Ro'yxat</button>
      <div class="sa-d-meta">${saKind(d.kind, d.kind_name)}<span class="sa-ph ${P[1]}">${P[0]}</span>${d.own ? `<span class="sa-tag">Siz</span>` : ""}</div>
      <h3>${esc(d.name)}</h3><div class="muted sa-d-sub">${esc(d.position || "")}${d.unit ? ` · ${esc(d.unit)}` : ""}</div>
      <div class="sa-d-dates"><span>${ico("calendar", 15)}<b>${dmy(d.start)} — ${dmy(d.end)}</b> · ${d.days} kalendar kun</span>${d.created_by ? `<span class="muted tiny">Kiritdi: ${esc(d.created_by)} · ${dmy(d.created_at.slice(0, 10))}</span>` : ""}</div>
      ${d.note ? `<div class="sa-note">${esc(d.note)}</div>` : ""}${d.status === "bekor" ? `<div class="sa-note off">${ico("x", 14)}Bekor qilingan${d.cancel_note ? `: ${esc(d.cancel_note)}` : ""}</div>` : ""}
      ${d.can_edit ? `<div class="sa-acts"><button class="btn sm" id="saEdit">${ico("pen", 15)}Tahrirlash</button><button class="btn sm ghost" id="saCancel">${ico("x", 15)}Bekor qilish</button></div>` : ""}
      <div id="saAct"></div></div>
    ${d.can_edit || d.file_list?.length || d.order ? `<div class="sa-blocks">
      ${d.can_edit || d.file_list?.length ? `<div class="sa-blk"><div class="sa-blk-h">${ico("clip", 14)}Asos hujjat</div>
        ${(d.file_list || []).map(f => `<a class="sa-file" href="/api/staffabs/files/${f.id}" download><span class="sa-ext">${esc(String(f.ext).toUpperCase())}</span><span><b>${esc(f.name)}</b><small>${Math.max(1, Math.round(f.size / 1024))} KB · ${esc(f.by)} · ${dmy(f.at.slice(0, 10))}</small></span>${ico("download", 15)}</a>`).join("") || `<span class="muted tiny">Hali yuklanmagan (kasallik varaqasi, buyruq, xizmat topshirig'i).</span>`}
        ${d.can_edit ? `<label class="btn sm ghost sa-up">${ico("upload", 15)}Fayl yuklash<input type="file" id="saFile" accept=".pdf,.jpg,.jpeg,.png,.doc,.docx" hidden></label>` : ""}</div>` : ""}
      ${d.kind === "mehnat" && (d.order || d.can_edit) ? `<div class="sa-blk"><div class="sa-blk-h">${ico("file", 14)}Mehnat ta'tili buyrug'i</div>
        ${d.order ? `<div class="sa-ord"><b>${esc(d.order.reg_no)}</b>${d.order.status ? `<span class="sa-tag">${d.order.status === "imzolangan" ? "imzolangan" : d.order.status === "loyiha" ? "loyiha — rektor imzosida" : esc(d.order.status)}</span>` : ""}${d.order.file ? `<a class="btn sm ghost" href="/api/docs/file/${encodeURIComponent(d.order.file)}" download>${ico("download", 14)}DOCX</a>` : ""}</div>`
          : `<div class="sa-ord-f"><button class="btn sm" id="saOrdNew">${ico("plus", 14)}Buyruq loyihasini yaratish</button><span class="muted tiny">yoki</span><input id="saOrdReg" placeholder="ShT-26/0001" aria-label="Buyruq raqami"><button class="btn sm ghost" id="saOrdLink">Bog'lash</button></div>`}</div>` : ""}
    </div>` : ""}
    ${d.teacher ? `<div class="sa-les-h"><b>${ico("users", 15)}Dars jadvaliga ta'siri</b><span class="muted tiny">${L.length ? `${L.length} ta dars · kelgusi ${fut.length}, o'rinbosar tayinlangan ${fut.filter(x => x.sub).length}` : "Bu davrda darsi yo'q"}</span>
      ${pastN ? `<button class="pt-q sa-q" id="saPast">${showPast ? "O'tgan kunlarni yashirish" : `O'tgan kunlar (${pastN})`}</button>` : ""}</div>
      <div class="sa-days">${dates.map(k => `<div class="sa-day${byDate[k][0].past ? " past" : ""}"><div class="sa-day-h">${esc(byDate[k][0].weekday)}, ${dmy(k)}</div>${byDate[k].map(x => saLesson(x, d)).join("")}</div>`).join("") || (L.length ? `<p class="muted tiny">Kelgusi darslar yo'q.</p>` : "")}</div>`
      : `<div class="sa-les-h"><span class="muted tiny">${ico("info", 14)}Bu xodim dars o'tmaydi — jadvalga ta'siri yo'q. Vazifalari bo'lim rahbari tomonidan taqsimlanadi.</span></div>`}
  </div>`;
  saBindDetail(d);
}
function saLesson(x, d) {
  const key = `${x.sched_id}|${x.date}`;
  return `<div class="sa-l${x.sub ? " cov" : x.past ? "" : " open"}" data-l="${key}">
    <span class="sa-l-t"><b>${x.slot}-para</b><small>${esc(x.time)}</small></span>
    <span class="sa-l-s"><b>${esc(x.subject)}</b><small>${esc(x.group || "")}${x.room ? ` · ${esc(x.room)}` : ""}</small></span>
    <span class="sa-l-sub">${x.sub ? `<span class="sa-sub">${ico("check", 13)}${esc(saShort(x.sub.name))}</span>${d.can_assign && !x.past ? `<button class="sa-x" data-unsub="${x.sub.id}" title="O'rinbosarni olib tashlash" aria-label="O'rinbosarni olib tashlash">${ico("x", 14)}</button>` : ""}`
      : x.past ? `<span class="muted tiny">o'tgan</span>` : d.can_assign ? `<button class="btn sm" data-sug="${key}">${ico("users", 14)}O'rinbosar</button>` : `<span class="sa-need">${ico("alert", 13)}o'rinbosar yo'q</span>`}</span>
    <div class="sa-sugw" data-sugw="${key}" hidden></div></div>`;
}
function saBindDetail(d) {
  $("#saBack").onclick = () => { SA.open = null; document.querySelector(".sa-wrap")?.classList.remove("has-open"); document.querySelectorAll("#saItems .sa-it").forEach(x => x.classList.remove("on")); $("#saRead").innerHTML = saEmpty(SA.list); };
  if ($("#saPast")) $("#saPast").onclick = () => { SA.showPast = !SA.showPast; saOpen(d.id, true); };
  if ($("#saEdit")) $("#saEdit").onclick = () => saEditForm(d);
  if ($("#saCancel")) $("#saCancel").onclick = () => {
    $("#saAct").innerHTML = `<div class="sa-cf" role="alertdialog" aria-label="Yozuvni bekor qilish"><div class="sa-warn">${ico("alert", 15)}<span><b>Yozuv bekor qilinsinmi?</b> Kelgusi sanalardagi o'rinbosarliklar o'chiriladi; yozuv tarixda «Bekor qilingan» bo'lib qoladi.</span></div>
      <input id="saCnNote" maxlength="300" placeholder="Sabab (ixtiyoriy): masalan, safar qoldirildi"><div class="row-actions"><button class="btn sm ghost" id="saCnNo">Yo'q</button><button class="btn sm danger" id="saCnYes">${ico("x", 14)}Bekor qilish</button></div></div>`;
    $("#saCnNote").focus(); $("#saCnNo").onclick = () => { $("#saAct").innerHTML = ""; };
    $("#saCnYes").onclick = () => busy($("#saCnYes"), async () => { if (await saApi(`/api/staffabs/${d.id}/cancel`, {note: $("#saCnNote").value.trim()})) { toast("Yozuv bekor qilindi"); await saList(); } }, "…");
  };
  const f = $("#saFile"); if (f) f.onchange = async () => {
    const file = f.files[0]; f.value = ""; if (!file) return;
    if (file.size > 10 * 1048576) return toast("Fayl hajmi 10 MB dan oshmasligi kerak");
    const r = await fetch(`/api/staffabs/${d.id}/files?name=${encodeURIComponent(file.name)}`, {method: "POST", credentials: "same-origin", headers: {"Content-Type": "application/octet-stream"}, body: file});
    const j = await r.json().catch(() => ({}));
    if (!r.ok) return toast(j.detail || j.message || "Fayl yuklanmadi");
    toast(`Yuklandi: ${j.name}`); saOpen(d.id, true); saRefreshItem();
  };
  if ($("#saOrdNew")) $("#saOrdNew").onclick = () => busy($("#saOrdNew"), async () => { const r = await saApi(`/api/staffabs/${d.id}/order`, {}); if (r) { toast(`Buyruq loyihasi: ${r.reg_no} — rektor imzosiga`); saOpen(d.id, true); saRefreshItem(); } }, "…");
  if ($("#saOrdLink")) $("#saOrdLink").onclick = () => busy($("#saOrdLink"), async () => { const v = $("#saOrdReg").value.trim(); if (!v) { $("#saOrdReg").focus(); return toast("Buyruq raqamini kiriting"); } const r = await saApi(`/api/staffabs/${d.id}/order`, {reg_no: v}); if (r) { toast(`Bog'landi: ${r.reg_no}`); saOpen(d.id, true); saRefreshItem(); } }, "…");
  saBindLessons($("#saRead"), d.id, () => { saOpen(d.id, true); saRefreshItem(); });
}
async function saRefreshItem() { try { const qs = saQs(); SA.list = await saApi(`/api/staffabs?${qs}`); const el = $("#saItems"); if (el) { el.innerHTML = SA.list.items.map(saItem).join(""); el.querySelectorAll("[data-sa]").forEach(x => x.onclick = () => { SA.form = null; saOpen(+x.dataset.sa); }); } } catch (e) {} }
/* o'rinbosar tavsiyasi va tayinlash (tafsilot va «O'rinbosar kerak» uchun umumiy) */
function saBindLessons(root, aidDefault, after) {
  root.querySelectorAll("[data-unsub]").forEach(b => b.onclick = () => busy(b, async () => {
    const aid = +(b.closest("[data-aid]")?.dataset.aid || aidDefault);
    if (await saApi(`/api/staffabs/${aid}/subs/${b.dataset.unsub}`, undefined, "DELETE")) { toast("O'rinbosar olib tashlandi"); after(); }
  }, "…"));
  root.querySelectorAll("[data-sug]").forEach(b => b.onclick = async () => {
    const [sid, date] = b.dataset.sug.split("|"), aid = +(b.closest("[data-aid]")?.dataset.aid || aidDefault);
    const w = b.closest(".sa-l").querySelector("[data-sugw]");
    if (!w.hidden) { w.hidden = true; b.setAttribute("aria-expanded", "false"); return; }
    root.querySelectorAll("[data-sugw]").forEach(x => { x.hidden = true; }); w.hidden = false; b.setAttribute("aria-expanded", "true");
    w.innerHTML = `<p class="muted tiny">Tavsiyalar yuklanmoqda…</p>`;
    const r = await saApi(`/api/staffabs/${aid}/suggest?sched_id=${sid}&date=${date}`).catch(() => null);
    if (!r) { w.innerHTML = `<p class="muted tiny">Tavsiyalarni yuklab bo'lmadi</p>`; return; }
    w.innerHTML = r.items.length ? `<div class="sa-sug-h"><span class="muted tiny">Shu parada bo'sh, shu kuni ishda bo'lgan o'qituvchilar (avval — shu fanni o'qitadiganlar):</span>
        <label class="sa-all"><input type="checkbox" data-alld> Shu darsning yo'qlikdagi barcha sanalariga</label></div>
      ${r.items.map(x => `<div class="sa-sug"><span><b>${esc(x.name)}</b><small>${esc(x.position || "")}${x.other_kafedra ? ` · <span class="sa-oth">${esc(x.kafedra)} kafedrasi</span>` : ""} · ${esc(x.why.join(", "))}</small></span>
        <button class="btn sm${x.same_subject ? " primary" : ""}" data-pick="${x.teacher_id}">Tayinlash</button></div>`).join("")}`
      : `<p class="muted tiny">Shu parada bo'sh o'qituvchi topilmadi — darsni boshqa kunga ko'chirish Akademik bo'lim bilan kelishiladi.</p>`;
    w.querySelectorAll("[data-pick]").forEach(p => p.onclick = () => busy(p, async () => {
      const res = await saApi(`/api/staffabs/${aid}/subs`, {sched_id: +sid, date, teacher_id: +p.dataset.pick, all_dates: !!w.querySelector("[data-alld]")?.checked});
      if (res) { toast(`O'rinbosar: ${saShort(res.teacher)} · ${res.assigned.length} ta dars${res.skipped.length ? ` (${res.skipped.length} ta sanada band — o'tkazib yuborildi)` : ""}`); after(); }
    }, "…"));
  });
}
function saEditForm(d) {
  const K = SA.meta.kinds;
  $("#saAct").innerHTML = `<div class="sa-cf"><div class="sa-fg">
      <label>Turi<select id="saEK">${Object.entries(K).map(([k, n]) => `<option value="${k}" ${d.kind === k ? "selected" : ""}>${esc(n)}</option>`).join("")}</select></label>
      <label>Boshlanishi<input type="date" id="saES" value="${esc(d.start)}"></label><label>Tugashi<input type="date" id="saEE" value="${esc(d.end)}"></label>
      <label class="full">Izoh<input id="saEN" maxlength="500" value="${esc(d.note || "")}"></label></div>
    <div class="row-actions"><button class="btn sm ghost" id="saENo">Bekor qilish</button><button class="btn sm primary" id="saEGo">${ico("check", 14)}Saqlash</button></div></div>`;
  $("#saENo").onclick = () => { $("#saAct").innerHTML = ""; };
  $("#saEGo").onclick = () => busy($("#saEGo"), async () => {
    const r = await saApi(`/api/staffabs/${d.id}`, {kind: $("#saEK").value, start: $("#saES").value, end: $("#saEE").value, note: $("#saEN").value}, "PUT");
    if (r) { toast(`Saqlandi${r.dropped_subs ? ` · oraliqdan chiqqan ${r.dropped_subs} ta o'rinbosarlik o'chirildi` : ""}`); saOpen(d.id, true); saRefreshItem(); }
  }, "…");
}
/* yangi yozuv (kadrlar) */
function saForm() {
  const K = SA.meta.kinds, f = SA.form;
  document.querySelector(".sa-wrap")?.classList.add("has-open");
  $("#saRead").innerHTML = `<form class="sa-new" id="saNewF" onsubmit="event.preventDefault()">
    <div class="sa-d-h"><button type="button" class="btn sm ghost sa-back" id="saFBack">${ico("back", 16)}Ro'yxat</button><h3>${ico("plus", 18)}Yangi yozuv</h3></div>
    <label class="sa-lbl">Xodim yoki o'qituvchi<label class="sa-search">${ico("search", 15)}<input id="saStQ" type="search" placeholder="F.I.Sh. yoki bo'lim (kamida 2 harf)" autocomplete="off" aria-label="Xodim qidirish"></label></label>
    <div id="saStL" class="sa-stl"></div><div id="saStSel"></div>
    <div class="sa-fg"><label>Turi<select id="saK">${Object.entries(K).map(([k, n]) => `<option value="${k}">${esc(n)}</option>`).join("")}</select></label>
      <label>Boshlanishi<input type="date" id="saS" value="${esc(ME.today)}"></label><label>Tugashi<input type="date" id="saE" value="${esc(ME.today)}"></label>
      <label class="full">Izoh<input id="saN" maxlength="500" placeholder="Masalan: kasallik varaqasi № …, safar joyi, buyruq raqami"></label></div>
    <div class="sa-f-f"><span class="muted tiny">${ico("shield", 13)}Izoh va asos hujjat faqat Kadrlar bo'limi va xodimning o'ziga ko'rinadi. Saqlangach asos hujjatni yuklang.</span>
      <div class="row-actions"><button type="button" class="btn ghost" id="saFNo">Bekor qilish</button><button class="btn primary" id="saFGo">${ico("check", 16)}Saqlash</button></div></div></form>`;
  const back = () => { SA.form = null; document.querySelector(".sa-wrap")?.classList.remove("has-open"); $("#saRead").innerHTML = saEmpty(SA.list); };
  $("#saFBack").onclick = back; $("#saFNo").onclick = back;
  const drawSel = () => { $("#saStSel").innerHTML = f.staff ? `<div class="sa-stsel">${ico("user", 15)}<span><b>${esc(f.staff.name)}</b><small>${esc(f.staff.position)} · ${esc(f.staff.unit)}${f.staff.teacher_id ? ` · haftada ${f.staff.lessons_week} ta dars` : " · dars o'tmaydi"}</small></span><button type="button" class="sa-x" id="saStX" aria-label="Boshqa xodim">${ico("x", 14)}</button></div>` : "";
    if ($("#saStX")) $("#saStX").onclick = () => { f.staff = null; drawSel(); $("#saStQ").focus(); }; };
  let t; $("#saStQ").oninput = e => { clearTimeout(t); t = setTimeout(async () => {
    const v = e.target.value.trim(); if (v.length < 2) { $("#saStL").innerHTML = ""; return; }
    const L = await saApi(`/api/staffabs/staff?q=${encodeURIComponent(v)}`).catch(() => []);
    $("#saStL").innerHTML = L.map(x => `<button type="button" data-st="${x.id}"><b>${esc(x.name)}</b><small>${esc(x.position)} · ${esc(x.unit)}</small></button>`).join("") || `<p class="muted tiny">Topilmadi</p>`;
    $("#saStL").querySelectorAll("[data-st]").forEach(b => b.onclick = () => { f.staff = L.find(x => x.id === +b.dataset.st); $("#saStL").innerHTML = ""; $("#saStQ").value = ""; drawSel(); });
  }, 250); };
  drawSel(); setTimeout(() => $("#saStQ")?.focus({preventScroll: true}), 30);
  $("#saFGo").onclick = () => busy($("#saFGo"), async () => {
    if (!f.staff) { $("#saStQ").focus(); return toast("Xodimni tanlang"); }
    const r = await saApi("/api/staffabs", {staff_id: f.staff.id, kind: $("#saK").value, start: $("#saS").value, end: $("#saE").value, note: $("#saN").value.trim()});
    if (!r) return;
    toast(`Ro'yxatga olindi${r.lessons ? ` · ${r.lessons} ta darsga o'rinbosar kerak` : ""}`);
    SA.form = null; SA.open = r.id; SA.period = "all"; await saList();
  }, "…");
}

/* ---------- 2) o'rinbosar kerak ---------- */
async function saNeeds() {
  const n = await saApi(`/api/staffabs/needs?days=${SA.days}`); SA.needs = n;
  const tc = document.querySelector('[data-tc="needs"]'); if (tc) { tc.textContent = n.open; tc.hidden = !n.open; }
  $("#saBody").innerHTML = `<div class="sa-bar"><span>${ico("calendar", 15)}${dmy(n.from)} — ${dmy(n.to)}</span>
      <div class="sa-flt">${[7, 14, 28].map(k => `<button class="${SA.days === k ? "on" : ""}" data-days="${k}">${k} kun</button>`).join("")}</div>
      <span class="muted tiny">O'rinbosarsiz: <b class="${n.open ? "bad" : ""}">${n.open}</b> · tayinlangan: <b>${n.covered}</b></span></div>
    ${n.groups.length ? n.groups.map(g => `<section class="card sa-kaf"><div class="sa-kaf-h"><h3>${esc(g.kafedra)}${g.department_id ? " kafedrasi" : ""}</h3>
        <span class="sa-les${g.open ? " bad" : " ok"}">${g.open ? `${g.open} ta dars o'rinbosarsiz` : "hammasiga o'rinbosar bor"}</span><span class="muted tiny">tayinlangan: ${g.covered}</span></div>
      <div class="sa-nl">${g.items.map(x => `<div class="sa-l${x.sub ? " cov" : " open"}" data-aid="${x.absence_id}" data-l="${x.sched_id}|${x.date}">
        <span class="sa-l-d"><b>${esc(x.weekday.slice(0, 3))}, ${saDm(x.date)}</b><small>${x.slot}-para · ${esc(x.time)}</small></span>
        <span class="sa-l-s"><b>${esc(x.subject)}</b><small>${esc(x.group || "")}${x.room ? ` · ${esc(x.room)}` : ""}</small></span>
        <span class="sa-l-w"><b>${esc(saShort(x.teacher))}</b><small>${esc(x.kind_name || "")}</small></span>
        <span class="sa-l-sub">${x.sub ? `<span class="sa-sub">${ico("check", 13)}${esc(saShort(x.sub.name))}</span>${x.can_assign ? `<button class="sa-x" data-unsub="${x.sub.id}" title="Olib tashlash" aria-label="O'rinbosarni olib tashlash">${ico("x", 14)}</button>` : ""}`
          : x.can_assign ? `<button class="btn sm" data-sug="${x.sched_id}|${x.date}">${ico("users", 14)}O'rinbosar</button>` : `<span class="sa-need">${ico("alert", 13)}o'rinbosar yo'q</span>`}</span>
        <div class="sa-sugw" data-sugw="${x.sched_id}|${x.date}" hidden></div></div>`).join("")}</div></section>`).join("")
      : `<div class="card sa-empty">${ico("check", 22)}<b>Bu davrda o'rinbosar kerak bo'lgan dars yo'q</b><span class="muted">Yo'qlikdagi o'qituvchilarning darslari shu yerda chiqadi.</span></div>`}
    <p class="muted tiny sa-foot">${ico("info", 13)}Tavsiya: o'sha kafedra, o'sha para bo'sh, o'sha kuni ta'tilda/safarda emas, boshqa darsga o'rinbosar emas; shu fanni o'qitadiganlar birinchi. ${SA.meta.can_assign ? "Tayinlash — kafedra mudiri." : "Tayinlashni kafedra mudiri qiladi."}</p>`;
  $("#saBody").querySelectorAll("[data-days]").forEach(b => b.onclick = () => { SA.days = +b.dataset.days; saNeeds(); });
  saBindLessons($("#saBody"), 0, () => saNeeds());
}

/* ---------- 3) jadval o'zgarishlari ---------- */
async function saChanges() {
  const c = await saApi(`/api/staffabs/changes?days=${SA.days}`), own = SA.meta.mode === "own";
  const head = `<div class="sa-bar"><span>${ico("calendar", 15)}${dmy(c.from)} — ${dmy(c.to)}</span><div class="sa-flt">${[7, 14, 28].map(k => `<button class="${SA.days === k ? "on" : ""}" data-days="${k}">${k} kun</button>`).join("")}</div></div>`;
  const rows = own ? c.mine : c.items;
  $("#saBody").innerHTML = head + (rows.length ? `<div class="card sa-tbl-w"><table class="sa-tbl"><thead><tr><th>Sana</th><th>Para</th><th>Guruh · fan</th><th>Xona</th>${own ? "<th>Kim o'rniga</th>" : "<th>O'qituvchi (yo'q)</th><th>O'rinbosar</th>"}</tr></thead><tbody>
      ${rows.map(x => `<tr class="${!own && !x.sub ? "open" : ""}"><td data-l="Sana"><b>${esc(x.weekday.slice(0, 3))}, ${saDm(x.date)}</b></td><td data-l="Para">${x.slot}-para <small class="muted">${esc(x.time)}</small></td>
        <td data-l="Guruh · fan"><b>${esc(x.group || "")}</b> · ${esc(x.subject)}</td><td data-l="Xona">${esc(x.room || "—")}</td>
        ${own ? `<td data-l="Kim o'rniga">${esc(x.absent)} <small class="muted">${esc(x.kind_name || "")}</small></td>` : `<td data-l="O'qituvchi">${esc(saShort(x.teacher))} <small class="muted">${esc(x.kafedra || "")} · ${esc(x.kind_name || "")}</small></td>
        <td data-l="O'rinbosar">${x.sub ? `<span class="sa-sub">${ico("check", 13)}${esc(saShort(x.sub.name))}</span>` : `<span class="sa-need">${ico("alert", 13)}tayinlanmagan</span>`}</td>`}</tr>`).join("")}</tbody></table></div>`
    : `<div class="card sa-empty">${ico("swap", 22)}<b>${own ? "Bu davrda siz o'rinbosar bo'lgan dars yo'q" : "Bu davrda jadval o'zgarishi yo'q"}</b></div>`);
  $("#saBody").querySelectorAll("[data-days]").forEach(b => b.onclick = () => { SA.days = +b.dataset.days; saChanges(); });
}

/* ---------- 4) tahlil ---------- */
async function saAnalytics() {
  const A = await saApi("/api/staffabs/analytics");
  const mx = Math.max(1, ...A.by_unit.flatMap(u => u.months));
  const shade = v => v ? `style="--a:${(0.12 + 0.75 * v / mx).toFixed(2)}"` : "";
  $("#saBody").innerHTML = `<section class="card sa-an"><h3>Yo'qlik kunlari: kafedra va bo'limlar kesimida</h3><p class="muted tiny">Kalendar kunlar; bekor qilinganlar hisobga olinmaydi. Joriy oy ajratilgan.</p>
      ${A.by_unit.length ? `<div class="sa-hm-w"><table class="sa-hm"><thead><tr><th>Kafedra / bo'lim</th>${A.months.map((m, i) => `<th class="${i === A.current_month ? "cur" : ""}">${esc(m)}</th>`).join("")}<th>Jami</th></tr></thead><tbody>
        ${A.by_unit.map(u => `<tr><th title="${esc(Object.entries(u.by_kind).map(([k, v]) => `${SA.meta.kinds[k]}: ${v} kun`).join(" · "))}">${esc(u.unit)}</th>${u.months.map((v, i) => `<td class="${v ? "on" : ""}${i === A.current_month ? " cur" : ""}" ${shade(v)}>${v || ""}</td>`).join("")}<td class="tot">${u.months.reduce((a, b) => a + b, 0)}</td></tr>`).join("")}</tbody></table></div>`
        : `<p class="muted">Ma'lumot yo'q</p>`}</section>
    <div class="sa-an2">
      <section class="card sa-an"><h3>Tez-tez kasallik varaqasi</h3><p class="muted tiny">Oxirgi 180 kunda 2 va undan ko'p marta yoki jami 10 kundan ortiq.</p>
        ${A.frequent_sick.length ? `<div class="sa-rl">${A.frequent_sick.map(x => `<div class="sa-r"><span><b>${esc(x.name)}</b><small>${esc(x.unit)} · oxirgisi ${dmy(x.last)}</small></span><span class="sa-les bad">${x.count} marta · ${x.days} kun</span></div>`).join("")}</div>` : `<p class="muted tiny">Yo'q</p>`}</section>
      <section class="card sa-an"><h3>Bir vaqtdagi yo'qliklar</h3><p class="muted tiny">Bir kafedra yoki bo'limda kesishgan yo'qliklar (bugundan boshlab) — darslar va ish yuklamasi uchun xavf.</p>
        ${A.overlaps.length ? `<div class="sa-rl">${A.overlaps.map(o => `<div class="sa-r"><span><b>${esc(o.unit)}</b><small>${o.people.map(p => `${esc(saShort(p.name))} (${esc((p.kind_name || "").split(" (")[0].toLowerCase())})`).join(" + ")}${o.staff_total ? ` · kafedrada ${o.staff_total} o'qituvchi` : ""}</small></span><span class="sa-les warn">${saRange(o.from, o.to)} · ${o.days} kun</span></div>`).join("")}</div>` : `<p class="muted tiny">Kesishgan yo'qlik yo'q</p>`}</section>
    </div>`;
}
