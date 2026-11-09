"use strict";
/* =====================================================================
   «O'quv dasturlari» — Akademik faoliyatni boshqarish bo'limi vositalari (app/syllabus.py, /api/syllabus/*).
     1) Holat taxtasi va sillabus oqimi: so'rash → o'qituvchi biriktirish → tuzish / DOCX·PDF yuklash → tekshiruv
        (mavzular mosligi, tayanch OTM qamrovi, soatlar) → qaytarish yoki kelishuv (kafedra → Akademik bo'lim → prorektor).
     2) O'quv yuklama kalkulyatori: potok / guruh / kichik guruh bo'yicha soatlar, stavka, XLSX va Hujjatlar markazi (DOCX).
     3) Kafedra so'rovlari: yuborish, javob (matn/fayl), qabul yoki qayta ishlashga qaytarish.
   Ruxsatlar serverda; bu yerda faqat server qaytargan `actions` bo'yicha tugmalar ko'rsatiladi.
   Global: renderSyllabus() — app.js go(); sylLink(link) — extras.js openLink() (bildirishnoma / «Mening vazifalarim»).
   app.js yordamchilaridan foydalanadi: $, esc, fmt, ico, dmy, toast, showLogin, ME.
   ===================================================================== */
const SYL = {tab: "board", meta: null, board: null, flt: {dept: 0, status: "", q: ""}, open: null, d: null, edit: null, dirty: false, ver: null,
             req: false, cat: null, load: null, ldept: 0, lset: {}, lrows: {}, ltimer: null, tasks: null, task: null, tnew: false, chk: null, chkNote: ""};
if (!document.querySelector('link[href="syllabus.css"]')) document.head.insertAdjacentHTML("beforeend", '<link rel="stylesheet" href="syllabus.css">');
if (typeof ICONS === "object") {
  Object.assign(ICONS, Object.fromEntries(Object.entries({
    plus: '<path d="M12 5v14M5 12h14"/>',
    upload: '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><path d="m17 8-5-5-5 5"/><path d="M12 3v12"/>',
    download: '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><path d="m7 10 5 5 5-5"/><path d="M12 15V3"/>',
    trash: '<path d="M3 6h18"/><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/><path d="M10 11v6M14 11v6"/><path d="M9 6V4h6v2"/>',
    back: '<path d="m15 18-6-6 6-6"/>',
    inbox: '<path d="M22 12h-6l-2 3h-4l-2-3H2"/><path d="M5.45 5.11 2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.45-6.89A2 2 0 0 0 16.76 4H7.24a2 2 0 0 0-1.79 1.11z"/>',
    calc: '<rect x="4" y="2" width="16" height="20" rx="2"/><path d="M8 6h8M8 10h.01M12 10h.01M16 10h.01M8 14h.01M12 14h.01M16 14h.01M8 18h.01M12 18h4"/>',
    pen: '<path d="M12 20h9"/><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4z"/>',
    bell: '<path d="M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9"/><path d="M10.3 21a1.94 1.94 0 0 0 3.4 0"/>',
  }).filter(([k]) => !ICONS[k])));
  try { const s = document.querySelector('#nav a[data-v="syllabus"] svg'); if (s && !s.innerHTML.trim()) { s.remove(); hydrateIcons(); } } catch (e) {}
}

/* ---------- server ---------- */
async function sylApi(path, body, method) {
  const m = method || (body === undefined ? "GET" : "POST");
  const r = await fetch(path, {method: m, credentials: "same-origin", headers: {"Content-Type": "application/json"}, body: body === undefined ? undefined : JSON.stringify(body)});
  if (r.status === 401) { showLogin(); throw new Error("auth"); }
  const d = await r.json().catch(() => ({}));
  if (!r.ok) { const e = new Error(r.status === 403 && m === "GET" ? "denied" : "api"); e.msg = d.message || (typeof d.detail === "string" ? d.detail : "Xatolik yuz berdi"); throw e; }
  return d;
}
async function sylRaw(path, file) {
  const r = await fetch(path, {method: "POST", credentials: "same-origin", body: file, headers: {"Content-Type": "application/octet-stream"}});
  if (r.status === 401) { showLogin(); throw new Error("auth"); }
  const d = await r.json().catch(() => ({}));
  if (!r.ok) { const e = new Error("api"); e.msg = d.message || (typeof d.detail === "string" ? d.detail : "Faylni yuklab bo'lmadi"); throw e; }
  return d;
}
const sylErr = e => { if (!["auth"].includes(e?.message)) toast(e?.msg || "Xatolik yuz berdi — qayta urinib ko'ring"); };
async function sylBusy(btn, fn) {
  if (btn && btn.disabled) return;
  const old = btn ? btn.innerHTML : ""; if (btn) { btn.disabled = true; btn.setAttribute("aria-busy", "true"); }
  try { return await fn(); } catch (e) { sylErr(e); } finally { if (btn && btn.isConnected) { btn.disabled = false; btn.removeAttribute("aria-busy"); btn.innerHTML = old; } }
}

/* ---------- yordamchilar ---------- */
const SY_ST = {soralgan: "gray", jarayonda: "mid", qaytarilgan: "high", tekshiruvda: "rev", kelishuvda: "agr", tasdiqlangan: "low"};
const SY_TILES = [["soralgan", "So'ralgan", "inbox"], ["jarayonda", "Tayyorlanmoqda", "pen"], ["qaytarilgan", "Qaytarilgan", "back"],
                  ["tekshiruvda", "Tekshiruvda", "search"], ["kelishuvda", "Kelishuvda", "users"], ["tasdiqlangan", "Tasdiqlangan", "checkc"], ["overdue", "Muddati o'tgan", "alert"]];
const SY_H = [["lecture", "Ma'ruza"], ["practice", "Amaliy"], ["seminar", "Seminar"], ["lab", "Lab."], ["self", "Mustaqil"]];
const fh = v => { const n = Math.round((+v || 0) * 10) / 10; return fmt(n); };
const SY_STG = {kafedra: "Kafedra", akademik: "Akademik bo'lim", prorektor: "Prorektor"};
const syTag = it => `<span class="sy-st ${SY_ST[it.status]}"${it.stage_label ? ` title="${esc(it.stage_label)}"` : ""}>${esc(it.status_label)}${it.stage ? ` · ${esc(SY_STG[it.stage] || it.stage_label)}` : ""}</span>`;
function syDue(it) {
  if (!it.due) return "—";
  const tail = it.overdue ? `<small class="bad">${-it.days} kun o'tdi</small>` : (it.days != null && it.days >= 0 && it.days <= 7 && ["soralgan", "jarayonda", "qaytarilgan"].includes(it.status)) ? `<small>${it.days === 0 ? "bugun" : it.days + " kun qoldi"}</small>` : "";
  return `<span class="sy-due${it.overdue ? " over" : ""}">${dmy(it.due)}${tail}</span>`;
}
const syWhen = ts => ts ? `${dmy(ts.slice(0, 10))}${ts.length > 10 ? " " + ts.slice(11, 16) : ""}` : "";
function syLevel(l) { return l === "ok" ? `<span class="sy-lv ok">${ico("checkc", 14)}Mos</span>` : l === "warn" ? `<span class="sy-lv warn">${ico("info", 14)}E'tibor</span>` : l === "bad" ? `<span class="sy-lv bad">${ico("alert", 14)}Kamchilik</span>` : `<span class="muted">—</span>`; }
const syMeter = (p, cls = "") => `<span class="sy-meter ${cls}" role="img" aria-label="${p}%"><i style="width:${Math.max(0, Math.min(100, p))}%"></i></span>`;

/* bildirishnoma / «Mening vazifalarim» havolasi */
function sylLink(l) {
  if (!l) return;
  if (l.item) { SYL.tab = "item"; SYL.open = +l.item; SYL.ver = null; SYL.edit = null; SYL.chk = null; }
  else if (l.tab === "tasks") { SYL.tab = "tasks"; SYL.task = l.task ? +l.task : null; SYL.tnew = false; }
  else { SYL.tab = "board"; SYL.open = null; SYL.flt = {dept: 0, status: l.status || "", q: ""}; }
}

/* ---------- asosiy ---------- */
async function renderSyllabus() {
  const el = $("#v-syllabus");
  if (!SYL.meta) SYL.meta = await sylApi("/api/syllabus/meta");
  const m = SYL.meta;
  if (SYL.tab === "load" && !m.can.load) SYL.tab = "board";
  if (SYL.tab === "tasks" && !m.can.tasks) SYL.tab = "board";
  const tabs = [["board", "Holat taxtasi", "list"]].concat(m.can.load ? [["load", "Yuklama kalkulyatori", "calc"]] : []).concat(m.can.tasks ? [["tasks", "Kafedra so'rovlari", "inbox"]] : []);
  const cur = SYL.tab === "item" ? "board" : SYL.tab;
  el.innerHTML = `<div class="head"><div><h2>O'quv dasturlari</h2><span class="muted">${esc(m.semester)} · ${esc(m.scope)}. Sillabuslar, o'quv yuklama va kafedralar bilan ish — har bir amal audit jurnaliga yoziladi.</span></div></div>
    ${tabs.length > 1 ? `<div class="sy-tabs" role="tablist" aria-label="O'quv dasturlari bo'limlari">${tabs.map(([k, l, i]) => `<button type="button" role="tab" class="sy-tab${cur === k ? " on" : ""}" aria-selected="${cur === k}" data-t="${k}">${ico(i, 16)}${l}</button>`).join("")}</div>` : ""}
    <div id="syBody" aria-live="polite"><div class="card sy-loading muted">Yuklanmoqda…</div></div>`;
  el.querySelectorAll(".sy-tab").forEach(b => b.onclick = () => { if (SYL.dirty && !sylLeave()) return; SYL.tab = b.dataset.t; SYL.open = null; SYL.task = null; renderSyllabus().catch(sylErr); });
  const body = $("#syBody");
  try {
    if (SYL.tab === "item" && SYL.open) await sylItem(body);
    else if (SYL.tab === "load") await sylLoad(body);
    else if (SYL.tab === "tasks") await sylTasks(body);
    else await sylBoard(body);
  } catch (e) {
    if (e?.message === "auth") return;
    body.innerHTML = `<div class="card locked"><div class="lk-ic">${ico(e?.message === "denied" ? "lock" : "alert", 22)}</div><b>${e?.message === "denied" ? "Ruxsat yo'q" : "Ma'lumotni yuklab bo'lmadi"}</b><span class="tiny">${esc(e?.msg || "")}</span></div>`;
  }
}
function sylLeave() { const ok = !SYL.dirty || SYL._leaveOk; if (!ok) { SYL._leaveOk = true; toast("Saqlanmagan o'zgarishlar bor — chiqish uchun yana bir marta bosing"); setTimeout(() => SYL._leaveOk = false, 4000); return false; } SYL.dirty = false; SYL._leaveOk = false; return true; }

/* =====================================================================
   1. Holat taxtasi
   ===================================================================== */
async function sylBoard(body) {
  const f = SYL.flt, m = SYL.meta;
  const qs = new URLSearchParams({dept: f.dept || 0, status: f.status || "", q: f.q || ""});
  const d = SYL.board = await sylApi(`/api/syllabus/board?${qs}`);
  const c = d.counts, all = m.role !== "kafedra" && m.role !== "oqituvchi";
  const tiles = SY_TILES.map(([k, l, i]) => `<button type="button" class="sy-tile ${k}${f.status === k ? " on" : ""}${c[k] ? "" : " zero"}" data-st="${k}" aria-pressed="${f.status === k}">
      <span class="sy-tile-ic">${ico(i, 17)}</span><b>${c[k] || 0}</b><span>${l}</span></button>`).join("");
  const deps = all ? `<div class="card sy-deps"><h3>${ico("chart")} Kafedralar kesimida <span class="muted tiny">tasdiqlangan / jami · bosib saralang</span></h3>
      <div class="sy-deplist">${d.by_dept.map(b => {
        const seg = ["tasdiqlangan", "kelishuvda", "tekshiruvda", "jarayonda", "qaytarilgan", "soralgan"].map(k => b[k] ? `<i class="${SY_ST[k]}" style="flex:${b[k]}" title="${esc(m.statuses[k])}: ${b[k]}"></i>` : "").join("");
        return `<button type="button" class="sy-dep${+f.dept === b.id ? " on" : ""}" data-dept="${b.id}" aria-pressed="${+f.dept === b.id}"><span class="sy-dep-n">${esc(b.name)}</span>
          <span class="sy-stack" aria-hidden="true">${seg}</span><span class="sy-dep-v"><b>${b.tasdiqlangan}</b>/${b.total}${b.overdue ? ` <em class="bad">${b.overdue} kech</em>` : ""}</span></button>`;
      }).join("") || `<p class="muted">Hali so'rov yo'q.</p>`}</div>
      <div class="sy-legend">${["tasdiqlangan", "kelishuvda", "tekshiruvda", "jarayonda", "qaytarilgan", "soralgan"].map(k => `<span><i class="${SY_ST[k]}"></i>${esc(m.statuses[k])}</span>`).join("")}</div></div>` : "";
  const reqBanner = m.can.request ? `<div class="sy-req">${ico("plus", 16)}<span>${d.unrequested ? `<b>${d.unrequested} ta</b> fan × kafedra uchun bu semestr sillabusi hali so'ralmagan.` : "Barcha fanlar uchun sillabus so'ralgan."}</span>
      ${d.unrequested ? `<button type="button" class="btn primary sm" id="syReqBtn" aria-expanded="${SYL.req}">Sillabus so'rash</button>` : ""}</div><div id="syReqForm"></div>` : "";
  const depSel = m.departments.length > 1 ? `<select id="syDept" aria-label="Kafedra"><option value="0">Barcha kafedralar</option>${m.departments.map(x => `<option value="${x.id}"${+f.dept === x.id ? " selected" : ""}>${esc(x.name)}</option>`).join("")}</select>` : "";
  const rows = d.items;
  body.innerHTML = `<div class="sy-tiles">${tiles}</div>${reqBanner}${deps}
    <div class="card sy-list">
      <div class="sy-filters"><label class="sy-search">${ico("search", 16)}<input id="syQ" type="search" placeholder="Fan, kafedra yoki o'qituvchi" value="${esc(f.q)}" aria-label="Qidirish"></label>${depSel}
        <button type="button" class="chip${f.status === "action" ? " on" : ""}" id="syMine" aria-pressed="${f.status === "action"}">${ico("bell", 14)} Mendan amal kutilmoqda</button>
        ${f.status || f.dept || f.q ? `<button type="button" class="btn ghost sm" id="syClr">${ico("x", 14)} Tozalash</button>` : ""}</div>
      <p class="muted tiny sy-cnt">${rows.length} ta sillabus${f.status && f.status !== "action" ? ` · ${esc(f.status === "overdue" ? "muddati o'tgan" : m.statuses[f.status].toLowerCase())}` : ""}</p>
      ${rows.length ? `<div class="sy-rows" role="list">${rows.map(sylRow).join("")}</div>` : `<div class="sy-empty">${ico("checkc", 26)}<b>Bu filtr bo'yicha sillabus yo'q</b></div>`}
    </div>`;
  body.querySelectorAll(".sy-tile").forEach(b => b.onclick = () => { f.status = f.status === b.dataset.st ? "" : b.dataset.st; renderSyllabus().catch(sylErr); });
  body.querySelectorAll(".sy-dep").forEach(b => b.onclick = () => { f.dept = +f.dept === +b.dataset.dept ? 0 : +b.dataset.dept; renderSyllabus().catch(sylErr); });
  body.querySelectorAll(".sy-row").forEach(a => a.onclick = e => { e.preventDefault(); SYL.tab = "item"; SYL.open = +a.dataset.id; SYL.ver = null; SYL.edit = null; SYL.chk = null; renderSyllabus().catch(sylErr); });
  const q = $("#syQ"); let t; q.oninput = () => { clearTimeout(t); t = setTimeout(() => { f.q = q.value; sylBoard(body).then(() => { const n = $("#syQ"); n.focus(); n.setSelectionRange(n.value.length, n.value.length); }).catch(sylErr); }, 300); };
  if ($("#syDept")) $("#syDept").onchange = e => { f.dept = +e.target.value; renderSyllabus().catch(sylErr); };
  $("#syMine").onclick = () => { f.status = f.status === "action" ? "" : "action"; renderSyllabus().catch(sylErr); };
  if ($("#syClr")) $("#syClr").onclick = () => { SYL.flt = {dept: 0, status: "", q: ""}; renderSyllabus().catch(sylErr); };
  if ($("#syReqBtn")) { $("#syReqBtn").onclick = () => { SYL.req = !SYL.req; sylReqForm().catch(sylErr); }; if (SYL.req) sylReqForm().catch(sylErr); }
}
function sylRow(r) {
  const ch = r.check || {};
  const chk = r.version ? `<span class="sy-rchk">${syLevel(ch.level)}${ch.coverage != null ? `<small>Qamrov ${ch.coverage}%</small>` : ""}</span>` : `<span class="muted tiny">topshirilmagan</span>`;
  return `<a href="#" class="sy-row" role="listitem" data-id="${r.id}">
    <span class="sy-r-main"><b>${esc(r.subject)}</b><small>${esc(r.department)} · ${r.credits} kredit${r.version ? ` · v${r.version}` : ""}</small></span>
    <span class="sy-r-t">${r.teacher ? esc(r.teacher) : `<span class="muted">o'qituvchi biriktirilmagan</span>`}</span>
    <span class="sy-r-d">${syDue(r)}</span><span class="sy-r-s">${syTag(r)}</span><span class="sy-r-c">${chk}</span><span class="sy-r-go">${ico("chevR", 16)}</span></a>`;
}
if (typeof ICONS === "object" && !ICONS.chevR) ICONS.chevR = '<path d="m9 18 6-6-6-6"/>';

async function sylReqForm() {
  const box = $("#syReqForm"); if (!box) return;
  $("#syReqBtn")?.setAttribute("aria-expanded", SYL.req);
  if (!SYL.req) { box.innerHTML = ""; return; }
  const d = SYL.cat = await sylApi(`/api/syllabus/catalog`);
  const by = {}; d.pairs.forEach((p, i) => (by[p.department] ||= []).push([p, i]));
  box.innerHTML = `<form class="card sy-reqf" id="syReqF"><h3>${ico("plus")} Sillabus so'rash <span class="muted tiny">Fanlar o'qituvchi-guruh bog'lanishlari va dars jadvalidan olinadi; so'rov kafedra mudiriga tushadi, u o'qituvchini biriktiradi.</span></h3>
    <div class="sy-reqgrid">${Object.entries(by).map(([dn, ps]) => `<fieldset class="sy-fs"><legend><label><input type="checkbox" data-all="${esc(dn)}"> ${esc(dn)} <span class="muted">(${ps.length})</span></label></legend>
      ${ps.map(([p, i]) => `<label class="sy-ck"><input type="checkbox" name="pair" value="${i}" data-dn="${esc(dn)}"> <span>${esc(p.subject)}</span> <small class="muted">${p.ng} guruh · ${p.credits} kr.</small></label>`).join("")}</fieldset>`).join("")}</div>
    <div class="form-grid sy-reqbot"><label>Muddat<input type="date" id="syReqDue" value="${d.default_due}" min="${SYL.meta.today}" required></label>
      <label>Izoh (ixtiyoriy)<input type="text" id="syReqNote" maxlength="500" placeholder="Masalan: yangi o'quv reja asosida"></label></div>
    <div class="row-actions"><button type="submit" class="btn primary" id="syReqGo">So'rov yuborish</button><button type="button" class="btn ghost" id="syReqX">Bekor qilish</button><span class="muted tiny" id="syReqN">0 ta tanlandi</span></div></form>`;
  const f = $("#syReqF"), cnt = () => $("#syReqN").textContent = `${f.querySelectorAll('input[name="pair"]:checked').length} ta tanlandi`;
  f.querySelectorAll("[data-all]").forEach(a => a.onchange = () => { f.querySelectorAll(`input[name="pair"]`).forEach(x => { if (x.dataset.dn === a.dataset.all) x.checked = a.checked; }); cnt(); });
  f.querySelectorAll('input[name="pair"]').forEach(x => x.onchange = cnt);
  $("#syReqX").onclick = () => { SYL.req = false; sylReqForm(); };
  f.onsubmit = e => { e.preventDefault(); sylBusy($("#syReqGo"), async () => {
    const pairs = [...f.querySelectorAll('input[name="pair"]:checked')].map(x => SYL.cat.pairs[+x.value]).map(p => ({subject: p.subject, department_id: p.department_id}));
    if (!pairs.length) return toast("Kamida bitta fanni belgilang");
    const r = await sylApi("/api/syllabus/request", {pairs, due: $("#syReqDue").value, note: $("#syReqNote").value});
    toast(`${r.created.length} ta fan bo'yicha sillabus so'raldi — kafedralarga yuborildi`); SYL.req = false; SYL.flt.status = "soralgan"; renderSyllabus();
  }); };
}

/* =====================================================================
   1b. Sillabus kartasi
   ===================================================================== */
const SY_STEPS = [["req", "So'raldi"], ["prep", "Tayyorlash"], ["rev", "Tekshiruv"], ["kafedra", "Kafedra"], ["akademik", "Akademik bo'lim"], ["prorektor", "Prorektor"], ["ok", "Tasdiqlandi"]];
function syStep(it) {
  const pos = {soralgan: 0, jarayonda: 1, qaytarilgan: 1, tekshiruvda: 2, tasdiqlangan: 6}[it.status] ?? {kafedra: 3, akademik: 4, prorektor: 5}[it.stage] ?? 0;
  return `<ol class="sy-steps" aria-label="Bosqichlar">${SY_STEPS.map(([k, l], i) => `<li class="${i < pos ? "done" : i === pos ? (it.status === "qaytarilgan" ? "cur ret" : it.status === "tasdiqlangan" ? "done" : "cur") : ""}"${i === pos ? ' aria-current="step"' : ""}><i>${i < pos || it.status === "tasdiqlangan" ? ico("check", 12) : i + 1}</i><span>${l}${i === pos && it.status === "qaytarilgan" ? " · qaytarilgan" : ""}</span></li>`).join("")}</ol>`;
}
async function sylItem(body) {
  const d = SYL.d = await sylApi(`/api/syllabus/items/${SYL.open}`);
  const it = d.item, A = new Set(d.actions), canEdit = A.has("edit");
  if (canEdit && !SYL.edit) { SYL.edit = JSON.parse(JSON.stringify(d.content)); SYL.dirty = false; }
  if (!canEdit) SYL.edit = null;
  let content = canEdit ? SYL.edit : d.content, chk = SYL.chk || d.check, verLbl = "";
  if (SYL.ver && !canEdit) { const v = await sylApi(`/api/syllabus/items/${it.id}/versions/${SYL.ver}`); content = v.content; chk = SYL.chk || v.check; verLbl = `${SYL.ver}-versiya · ${syWhen(v.created_at)} · ${esc(v.author || "")}`; }
  else if (!canEdit && it.version) verLbl = `${it.version}-versiya (oxirgi)`;
  const lastRet = d.history.find(h => /^qaytarildi/.test(h.action));
  const retBox = it.status === "qaytarilgan" && lastRet ? `<div class="sy-ret">${ico("alert", 18)}<div><b>Qaytarildi — ${esc(lastRet.user_name)}, ${syWhen(lastRet.ts)}</b><p>${esc(lastRet.comment || "")}</p></div></div>` : "";
  body.innerHTML = `<div class="sy-back"><button type="button" class="btn ghost sm" id="syBack">${ico("back", 16)} Holat taxtasiga</button></div>
    <div class="card sy-head">
      <div class="sy-head-t"><div><h3>${esc(it.subject)}</h3>
        <div class="sy-meta"><span>${ico("users", 14)}${esc(it.department)}</span><span>${it.credits} kredit · ${d.norm.total} soat</span><span>${esc(d.field_label)}</span><span>${esc(d.semester)}</span></div></div>
        <div class="sy-head-s">${syTag(it)}${it.overdue ? `<span class="tag high">Muddati o'tgan</span>` : ""}</div></div>
      <div class="sy-kv"><div><small>O'qituvchi</small><b>${it.teacher ? esc(it.teacher) : `<span class="muted">biriktirilmagan</span>`}</b></div><div><small>Muddat</small><b>${syDue(it)}</b></div>
        <div><small>Versiya</small><b>${it.version ? "v" + it.version : "—"}</b></div><div><small>So'rov izohi</small><b class="sy-note">${esc(d.note || "—")}</b></div></div>
      ${syStep(it)}${retBox}<div id="syAct">${sylActions(d)}</div></div>
    <div class="sy-split">
      <div class="sy-main">${canEdit ? sylEditor(d) : sylView(d, content, verLbl)}</div>
      <aside class="sy-side">${sylCheck(chk, canEdit, d)}${sylHist(d)}</aside>
    </div>`;
  $("#syBack").onclick = () => { if (!sylLeave()) return; SYL.tab = "board"; SYL.open = null; SYL.edit = null; SYL.chk = null; SYL.ver = null; renderSyllabus().catch(sylErr); };
  sylBindActions(d);
  if (canEdit) sylBindEditor(d);
  body.querySelectorAll("[data-ver]").forEach(b => b.onclick = () => { SYL.ver = +b.dataset.ver || null; SYL.chk = null; sylItem(body).catch(sylErr); });
  body.querySelector("#syAi")?.addEventListener("click", e => sylBusy(e.currentTarget, async () => {
    const r = await sylApi(`/api/syllabus/items/${it.id}/check`, {content: canEdit ? sylCollect() : null, ai: true});
    SYL.chk = r.check; SYL.chkNote = r.note; await sylItem($("#syBody"));
    toast(r.note || "Mahalliy AI tekshiruvi tugadi");
  }));
  body.querySelectorAll("[data-addref]").forEach(b => b.onclick = () => { sylCollect(); SYL.edit.topics.push({week: SYL.edit.topics.length + 1, title: b.dataset.addref, lecture: 0, practice: 0, seminar: 0, lab: 0, self: 0}); SYL.dirty = true; sylItem(body).catch(sylErr); });
}

function sylActions(d) {
  const it = d.item, A = new Set(d.actions), out = [];
  if (A.has("assign")) out.push(`<form class="sy-actf" id="syAssign"><b>${ico("user", 16)} O'qituvchi biriktirish</b>
      <div class="sy-inl"><select id="syTch" aria-label="O'qituvchi" required>${(d.teachers || []).map(t => `<option value="${t.id}"${t.id === it.teacher_id ? " selected" : ""}>${esc(t.full_name)} · ${esc(t.position || "")}${t.ng ? ` · ${t.ng} guruhda shu fan` : ""}</option>`).join("")}</select>
      <label class="sy-mini">Muddat<input type="date" id="syTDue" value="${it.due || ""}"></label><button class="btn primary sm" type="submit">${it.teacher_id ? "Qayta biriktirish" : "Biriktirish"}</button></div></form>`);
  if (A.has("review")) out.push(`<form class="sy-actf" id="syRev"><b>${ico("search", 16)} Tekshiruv natijasi</b>
      <textarea id="syCm" rows="3" placeholder="Izoh: nima tuzatilishi kerak (qaytarishda majburiy)"></textarea>
      <div class="row-actions"><button class="btn primary sm" type="button" data-rv="yuborish">${ico("check", 15)} Kelishuvga yuborish</button><button class="btn sm" type="button" data-rv="qaytarish">${ico("back", 15)} Izoh bilan qaytarish</button>
      <button class="btn ghost sm" type="button" id="syAuto">${ico("spark", 15)} Izohni tekshiruvdan to'ldirish</button></div></form>`);
  if (A.has("endorse")) {
    const last = it.stage === "prorektor";
    out.push(`<form class="sy-actf" id="syRev"><b>${ico("pen", 16)} ${esc(it.stage_label)} kelishuvi</b>
      <textarea id="syCm" rows="2" placeholder="Izoh (qaytarishda majburiy)"></textarea>
      <div class="row-actions"><button class="btn primary sm" type="button" data-rv="maqullash">${ico("check", 15)} ${last ? "Tasdiqlash" : "Ma'qullash"}</button><button class="btn sm" type="button" data-rv="qaytarish">${ico("back", 15)} Qaytarish</button></div></form>`);
  }
  if (A.has("due") || A.has("remind")) out.push(`<div class="sy-actf sy-ctl"><b>${ico("clock", 16)} Nazorat</b><div class="sy-inl">
      ${A.has("due") ? `<label class="sy-mini">Muddat<input type="date" id="syNewDue" value="${it.due || ""}"></label><button class="btn sm" type="button" id="syDueGo">Saqlash</button>` : ""}
      ${A.has("remind") && ["soralgan", "jarayonda", "qaytarilgan"].includes(it.status) ? `<button class="btn sm" type="button" id="syRemind">${ico("bell", 15)} Eslatma yuborish</button>` : ""}</div></div>`);
  return out.length ? `<div class="sy-acts">${out.join("")}</div>` : "";
}
function sylBindActions(d) {
  const it = d.item, reload = msg => { toast(msg); SYL.edit = null; SYL.chk = null; SYL.ver = null; SYL.chkNote = ""; renderSyllabus().catch(sylErr); if (typeof badges === "function") badges(); };
  const as = $("#syAssign");
  if (as) as.onsubmit = e => { e.preventDefault(); sylBusy(as.querySelector("button"), async () => { await sylApi(`/api/syllabus/items/${it.id}/assign`, {teacher_id: +$("#syTch").value, due: $("#syTDue").value}); reload("O'qituvchi biriktirildi"); }); };
  document.querySelectorAll("[data-rv]").forEach(b => b.onclick = () => sylBusy(b, async () => {
    const a = b.dataset.rv, cm = $("#syCm").value.trim();
    if (a === "qaytarish" && cm.length < 5) { $("#syCm").focus(); return toast("Qaytarish uchun izoh yozing"); }
    const r = await sylApi(`/api/syllabus/items/${it.id}/review`, {action: a, comment: cm});
    reload({qaytarilgan: "Sillabus izoh bilan qaytarildi", kelishuvda: a === "yuborish" ? "Kelishuvga yuborildi (kafedra mudiri)" : "Ma'qullandi — keyingi bosqichga o'tdi", tasdiqlangan: "Sillabus tasdiqlandi"}[r.status]);
  }));
  $("#syAuto")?.addEventListener("click", () => { $("#syCm").value = sylAutoComment(d.check); $("#syCm").focus(); });
  $("#syDueGo")?.addEventListener("click", e => sylBusy(e.currentTarget, async () => { await sylApi(`/api/syllabus/items/${it.id}/due`, {due: $("#syNewDue").value}); reload("Muddat o'zgartirildi"); }));
  $("#syRemind")?.addEventListener("click", e => sylBusy(e.currentTarget, async () => { await sylApi(`/api/syllabus/items/${it.id}/remind`, {comment: ""}); reload("Eslatma yuborildi — bildirishnomalarda ko'rinadi"); }));
}
function sylAutoComment(c) {
  if (!c) return "";
  const p = [];
  (c.relevance?.flagged || []).slice(0, 3).forEach(t => p.push(`«${t}» mavzusi fan mazmuniga mos emas.`));
  (c.reference?.missing || []).slice(0, 3).forEach(t => p.push(`Tayanch OTM dasturidagi «${t}» mavzusini kiritish tavsiya etiladi.`));
  (c.hours?.rows || []).filter(r => !r.ok).forEach(r => p.push(`${r.label}: ${fh(r.plan)} soat, me'yor ${r.norm} soat.`));
  if (c.assessment && !c.assessment.ok) p.push(`Baholash ulushlari yig'indisi ${c.assessment.sum}% — 100% bo'lishi kerak.`);
  if ((c.literature || 0) < 3) p.push("Adabiyotlar ro'yxatini to'ldiring (kamida 3 ta, so'nggi nashrlar).");
  return p.join("\n") || "Kamchilik topilmadi.";
}

/* --- o'qish rejimi --- */
function sylView(d, c, verLbl) {
  const it = d.item, ts = c.topics || [], sum = k => ts.reduce((s, t) => s + (+t[k] || 0), 0);
  const vers = d.versions.length > 1 ? `<div class="sy-vers" role="group" aria-label="Versiyalar">${d.versions.map(v => `<button type="button" class="chip${(SYL.ver || it.version) === v.version ? " on" : ""}" data-ver="${v.version === it.version ? 0 : v.version}" aria-pressed="${(SYL.ver || it.version) === v.version}">v${v.version} · ${dmy(v.created_at.slice(0, 10))}</button>`).join("")}</div>` : "";
  const curV = d.versions.find(v => v.version === (SYL.ver || it.version));
  if (!ts.length) return `<div class="card"><h3>${ico("book")} Sillabus mazmuni</h3><div class="sy-empty">${ico("pen", 26)}<b>Hali topshirilmagan</b><span class="muted">${it.status === "soralgan" ? "Kafedra mudiri o'qituvchini biriktirishi kutilmoqda." : "O'qituvchi sillabusni tayyorlamoqda."}</span></div></div>`;
  return `<div class="card"><h3>${ico("book")} Sillabus mazmuni <span class="muted tiny">${verLbl}</span></h3>${vers}
    ${curV?.has_file ? `<p class="sy-file">${ico("file", 15)}<a href="/api/syllabus/items/${it.id}/file?v=${curV.version}" target="_blank" rel="noopener">${esc(curV.file_name)}</a> <span class="muted tiny">yuklangan fayl</span></p>` : ""}
    ${c.goals ? `<p class="sy-goal"><b>Maqsad:</b> ${esc(c.goals)}</p>` : ""}
    <div class="tw"><table class="sy-tt"><thead><tr><th class="n">Hafta</th><th>Mavzu</th>${SY_H.map(([, l]) => `<th class="n">${l}</th>`).join("")}</tr></thead>
      <tbody>${ts.map(t => `<tr><td class="n">${t.week}</td><td>${esc(t.title)}</td>${SY_H.map(([k]) => `<td class="n">${fh(t[k])}</td>`).join("")}</tr>`).join("")}</tbody>
      <tfoot><tr><th></th><th>Jami</th>${SY_H.map(([k]) => `<th class="n">${fh(sum(k))}<small>me'yor ${d.norm[k]}</small></th>`).join("")}</tr></tfoot></table></div>
    <div class="sy-two"><div><h4>Adabiyotlar</h4>${(c.literature || []).length ? `<ol class="sy-lit">${c.literature.map(x => `<li>${esc(x)}</li>`).join("")}</ol>` : `<p class="muted">Kiritilmagan</p>`}</div>
      <div><h4>Baholash</h4><ul class="sy-asm"><li>Joriy nazorat <b>${c.assessment?.joriy ?? 0}%</b></li><li>Oraliq nazorat <b>${c.assessment?.oraliq ?? 0}%</b></li><li>Yakuniy nazorat <b>${c.assessment?.yakuniy ?? 0}%</b></li></ul></div></div></div>`;
}

/* --- tahrirlash rejimi --- */
function sylEditor(d) {
  const c = SYL.edit, ts = c.topics || [];
  return `<div class="card sy-ed"><h3>${ico("pen")} Sillabusni tayyorlash <span class="muted tiny">Haftalik mavzular va soatlar; yoki DOCX/PDF yuklang — mavzular avtomatik ajratiladi.</span></h3>
    <div class="sy-up"><label class="btn sm" for="syFile">${ico("upload", 15)} DOCX / PDF yuklash</label><input type="file" id="syFile" accept=".docx,.pdf" class="sr">
      ${d.draft_file ? `<span class="sy-file">${ico("file", 15)}<a href="/api/syllabus/items/${d.item.id}/file" target="_blank" rel="noopener">${esc(d.draft_file)}</a></span>` : `<span class="muted tiny">Fan dasturi jadvali (Mavzu · Ma'ruza · Amaliy …) yoki «1-mavzu: …» ko'rinishidagi ro'yxat tanib olinadi.</span>`}</div>
    <label class="sy-lbl">Fanning maqsadi<textarea id="syGoal" rows="2" maxlength="3000">${esc(c.goals || "")}</textarea></label>
    <div class="tw"><table class="sy-tt sy-edt"><thead><tr><th class="n">Hafta</th><th>Mavzu</th>${SY_H.map(([, l]) => `<th class="n">${l}</th>`).join("")}<th><span class="sr">Amal</span></th></tr></thead>
      <tbody id="syTb">${ts.map((t, i) => sylEdRow(t, i)).join("")}</tbody>
      <tfoot><tr><th></th><th>Jami <small>me'yor</small></th>${SY_H.map(([k]) => `<th class="n" data-sum="${k}"></th>`).join("")}<th></th></tr></tfoot></table></div>
    <button type="button" class="btn ghost sm" id="syAddT">${ico("plus", 15)} Mavzu qo'shish</button>
    <div class="sy-two"><label class="sy-lbl">Adabiyotlar <small class="muted">har biri yangi qatorda</small><textarea id="syLit" rows="5">${esc((c.literature || []).join("\n"))}</textarea></label>
      <div class="sy-lbl"><span>Baholash, % <small class="muted" id="syAsmS"></small></span><div class="sy-asmf">${[["joriy", "Joriy"], ["oraliq", "Oraliq"], ["yakuniy", "Yakuniy"]].map(([k, l]) => `<label>${l}<input type="number" min="0" max="100" data-asm="${k}" value="${c.assessment?.[k] ?? 0}"></label>`).join("")}</div></div></div>
    <div class="row-actions sy-edbar"><button type="button" class="btn" id="sySave">${ico("check", 15)} Qoralamani saqlash va tekshirish</button>
      <button type="button" class="btn primary" id="sySubmit">${ico("send", 15)} Tekshiruvga topshirish</button><span class="muted tiny" id="syDirty"></span></div></div>`;
}
const sylEdRow = (t, i) => `<tr data-i="${i}"><td class="n"><input type="number" min="1" max="30" data-k="week" value="${t.week || i + 1}" aria-label="Hafta"></td>
  <td><input type="text" data-k="title" value="${esc(t.title)}" maxlength="200" aria-label="Mavzu nomi" placeholder="Mavzu nomi"></td>
  ${SY_H.map(([k, l]) => `<td class="n"><input type="number" min="0" max="200" step="1" data-k="${k}" value="${+t[k] || 0}" aria-label="${l}"></td>`).join("")}
  <td><button type="button" class="icon-btn sy-del" data-del="${i}" aria-label="Mavzuni o'chirish" title="O'chirish">${ico("trash", 15)}</button></td></tr>`;
function sylCollect() {
  if (!SYL.edit) return null;
  const rows = [...document.querySelectorAll("#syTb tr")].map(tr => { const o = {}; tr.querySelectorAll("[data-k]").forEach(x => o[x.dataset.k] = x.dataset.k === "title" ? x.value : +x.value || 0); return o; });
  SYL.edit.topics = rows; SYL.edit.goals = $("#syGoal")?.value || "";
  SYL.edit.literature = ($("#syLit")?.value || "").split("\n").map(s => s.trim()).filter(Boolean);
  const a = {}; document.querySelectorAll("[data-asm]").forEach(x => a[x.dataset.asm] = +x.value || 0); SYL.edit.assessment = a;
  return SYL.edit;
}
function sylSums(d) {
  const c = sylCollect(); if (!c) return;
  SY_H.forEach(([k]) => { const s = c.topics.reduce((a, t) => a + (+t[k] || 0), 0), n = d.norm[k], el = document.querySelector(`[data-sum="${k}"]`);
    if (el) { el.innerHTML = `${fh(s)}<small>${n}</small>`; el.classList.toggle("bad", Math.abs(s - n) > 2); el.classList.toggle("good", Math.abs(s - n) <= 2); } });
  const as = Object.values(c.assessment).reduce((a, b) => a + b, 0), e = $("#syAsmS"); if (e) { e.textContent = `yig'indi ${as}%`; e.className = as === 100 ? "good" : "bad"; }
  $("#syDirty").textContent = SYL.dirty ? "Saqlanmagan o'zgarishlar bor" : "";
}
function sylBindEditor(d) {
  const it = d.item, body = $("#syBody");
  const mark = () => { SYL.dirty = true; sylSums(d); };
  body.querySelector(".sy-ed").addEventListener("input", mark);
  body.querySelectorAll("[data-del]").forEach(b => b.onclick = () => { sylCollect(); SYL.edit.topics.splice(+b.dataset.del, 1); SYL.dirty = true; sylItem(body).catch(sylErr); });
  $("#syAddT").onclick = () => { sylCollect(); SYL.edit.topics.push({week: SYL.edit.topics.length + 1, title: "", lecture: 0, practice: 0, seminar: 0, lab: 0, self: 0}); SYL.dirty = true;
    sylItem(body).then(() => { const x = document.querySelectorAll('#syTb [data-k="title"]'); x[x.length - 1]?.focus(); }).catch(sylErr); };
  $("#sySave").onclick = e => sylBusy(e.currentTarget, async () => {
    const r = await sylApi(`/api/syllabus/items/${it.id}/draft`, {content: sylCollect()}, "PUT");
    SYL.edit = r.content; SYL.chk = r.check; SYL.dirty = false; await sylItem(body); toast("Qoralama saqlandi va tekshirildi");
  });
  $("#sySubmit").onclick = e => sylBusy(e.currentTarget, async () => {
    const r = await sylApi(`/api/syllabus/items/${it.id}/submit`, {content: sylCollect()});
    SYL.dirty = false; SYL.edit = null; SYL.chk = null; toast(`${r.version}-versiya tekshiruvga topshirildi`); renderSyllabus(); if (typeof badges === "function") badges();
  });
  $("#syFile").onchange = e => { const f = e.target.files[0]; if (!f) return; sylBusy($("#sySave"), async () => {
    const r = await sylRaw(`/api/syllabus/items/${it.id}/upload?name=${encodeURIComponent(f.name)}`, f);
    SYL.edit = r.content; SYL.chk = r.check; SYL.dirty = false; await sylItem(body);
    toast(r.found ? `Fayldan ${r.found} ta mavzu${r.literature ? ` va ${r.literature} ta adabiyot` : ""} ajratildi — tekshirib, soatlarni to'ldiring` : "Fayl saqlandi, lekin mavzular jadvali topilmadi — qo'lda kiriting");
  }); };
  sylSums(d);
}

/* --- tekshiruv paneli --- */
function sylCheck(c, canEdit, d) {
  if (!c) return `<div class="card sy-ck0"><h3>${ico("search")} Tekshiruv</h3><p class="muted">Mavzular kiritilgach yoki sillabus topshirilgach avtomatik tekshiriladi: mavzular fanga mosligi, tayanch OTM dasturlari bilan qamrov, soatlar me'yori.</p></div>`;
  const R = c.relevance || {}, F = c.reference || {}, H = c.hours || {};
  const relRows = (R.items || []).filter(x => !x.ok);
  const rel = `<section class="sy-cks"><h4>a) Mavzular fanga mosligi <span class="sy-pct ${R.score >= 95 ? "good" : R.score >= 80 ? "" : "bad"}">${R.score ?? 0}%</span></h4>
    <p class="muted tiny">${R.method === "ai" ? "Mahalliy AI baholadi" : "Kalit so'z o'zaklari: fan nomi, standart tavsif va tayanch dasturlar lug'ati"}${R.strong ? "" : " · bu fan uchun katalog yo'q — ishonchliligi past"}</p>
    ${relRows.length ? `<ul class="sy-bad">${relRows.map(x => `<li>${ico("alert", 14)}<span>«${esc(x.title)}»${x.reason ? ` — ${esc(x.reason)}` : " — fan mazmuni bilan umumiy kalit so'z yo'q"}</span></li>`).join("")}</ul>` : `<p class="good tiny">${ico("checkc", 14)} Barcha mavzular fan mazmuniga mos</p>`}
    <button type="button" class="btn ghost sm" id="syAi">${ico("spark", 15)} AI bilan qayta tekshirish</button>${SYL.chkNote ? `<p class="muted tiny">${esc(SYL.chkNote)}</p>` : ""}</section>`;
  const ref = F.available ? `<section class="sy-cks"><h4>b) Tayanch OTM dasturlari bilan solishtirish <span class="sy-pct ${F.coverage >= 80 ? "good" : F.coverage >= 60 ? "" : "bad"}">${F.coverage}%</span></h4>
    ${F.sample ? `<p class="sy-sample">${ico("info", 14)}<span><b>Namuna ma'lumot.</b> Tayanch OTM mavzular katalogi sinov uchun tuzilgan — rasmiy fan dasturlaridan olinmagan.</span></p>` : ""}
    <div class="sy-unis">${(F.unis || []).map(u => `<div class="sy-uni"><span>${esc(u.name)}</span>${syMeter(u.coverage, u.coverage >= 80 ? "good" : u.coverage >= 60 ? "" : "bad")}<b>${u.covered}/${u.total}</b></div>`).join("")}</div>
    ${F.missing?.length ? `<details class="sy-det" open><summary>Yetishmayotgan mavzular (${F.missing.length})</summary><ul class="sy-miss">${F.missing.map(t => `<li><span>${esc(t)}</span>${canEdit ? `<button type="button" class="btn ghost sm" data-addref="${esc(t)}" aria-label="«${esc(t)}» mavzusini qo'shish">${ico("plus", 14)} qo'shish</button>` : ""}</li>`).join("")}</ul></details>` : ""}
    ${F.extra?.length ? `<details class="sy-det"><summary>Tayanch dasturlarda yo'q mavzular (${F.extra.length})</summary><ul class="sy-miss">${F.extra.map(t => `<li><span>${esc(t)}</span></li>`).join("")}</ul></details>` : ""}</section>`
    : `<section class="sy-cks"><h4>b) Tayanch OTM dasturlari</h4><p class="muted tiny">Bu fan uchun tayanch OTM katalogi kiritilmagan.</p></section>`;
  const hrs = `<section class="sy-cks"><h4>c) Soatlar o'quv reja me'yoriga <span class="sy-pct ${H.ok ? "good" : "bad"}">${H.ok ? "mos" : "mos emas"}</span></h4>
    <p class="muted tiny">${H.credits} kredit × ${SYL.meta.h_per_credit} = ${H.total_norm} soat · ${H.topics} mavzu, ${H.weeks} hafta</p>
    <table class="sy-hrs"><thead><tr><th>Tur</th><th class="n">Me'yor</th><th class="n">Reja</th><th class="n">Farq</th></tr></thead><tbody>
    ${(H.rows || []).map(r => `<tr class="${r.ok ? "" : "bad"}"><td>${esc(r.label)}</td><td class="n">${r.norm}</td><td class="n">${fh(r.plan)}</td><td class="n">${r.diff > 0 ? "+" : ""}${fh(r.diff)}</td></tr>`).join("")}
    <tr class="sy-tot${Math.abs(H.total_plan - H.total_norm) > 2 ? " bad" : ""}"><td>Jami</td><td class="n">${H.total_norm}</td><td class="n">${fh(H.total_plan)}</td><td class="n">${fh(H.total_plan - H.total_norm)}</td></tr></tbody></table>
    <p class="tiny ${c.assessment?.ok ? "good" : "bad"}">Baholash yig'indisi: ${c.assessment?.sum ?? 0}% · Adabiyotlar: ${c.literature ?? 0} ta</p></section>`;
  return `<div class="card sy-chk"><h3>${ico("search")} Tekshiruv ${syLevel(c.summary?.level)}</h3>
    ${c.summary?.notes?.length ? `<p class="muted tiny">${c.summary.notes.map(esc).join(" · ")}</p>` : ""}${rel}${ref}${hrs}</div>`;
}
function sylHist(d) {
  return `<div class="card sy-hist"><h3>${ico("history")} Tarix</h3><ol class="sy-tl">${d.history.map(h => `<li class="${/^qaytarildi/.test(h.action) ? "ret" : h.to_status === "tasdiqlangan" ? "ok" : ""}">
    <b>${esc(h.action)}${h.version ? ` <span class="muted">· v${h.version}</span>` : ""}</b><small>${esc(h.user_name || "")}${h.role ? ` · ${esc(h.role)}` : ""} · ${syWhen(h.ts)}</small>
    ${h.comment ? `<p>${esc(h.comment)}</p>` : ""}</li>`).join("")}</ol></div>`;
}

/* =====================================================================
   2. Yuklama kalkulyatori
   ===================================================================== */
async function sylLoad(body) {
  const m = SYL.meta;
  if (!SYL.ldept) SYL.ldept = m.role === "kafedra" ? m.departments[0]?.id : 4;
  const d = SYL.load = await sylApi(`/api/syllabus/load?dept=${SYL.ldept}`);
  SYL.lset = {...d.settings}; SYL.lrows = JSON.parse(JSON.stringify(d.overrides || {}));
  const S = d.settings;
  body.innerHTML = `<div class="card sy-lc">
    <div class="sy-lhead"><div><h3>${ico("calc")} O'quv yuklama kalkulyatori</h3><p class="muted tiny">Ma'ruza — potokka, amaliy va seminar — guruhga, laboratoriya — kichik guruhga. Soatlar o'quv reja me'yoridan (kredit × ${m.h_per_credit}); qatorda o'zgartirish mumkin. 1 stavka = ${d.load_norm} soat.</p></div>
      ${d.saved ? `<span class="muted tiny">Saqlangan: ${syWhen(d.saved.at)}${d.saved.by ? ` · ${esc(d.saved.by)}` : ""}</span>` : ""}</div>
    <div class="sy-lset">
      ${m.departments.length > 1 ? `<label>Kafedra<select id="syLD">${m.departments.map(x => `<option value="${x.id}"${x.id === SYL.ldept ? " selected" : ""}>${esc(x.name)}</option>`).join("")}</select></label>` : `<label>Kafedra<input type="text" value="${esc(d.department)}" readonly></label>`}
      <label>Potokda ko'pi bilan<input type="number" min="1" max="10" data-set="potok_max" value="${S.potok_max}"></label>
      <label>Kichik guruhlar (lab.)<input type="number" min="1" max="6" data-set="subgroups" value="${S.subgroups}"></label>
      <label>Sirtqi koeff.<input type="number" min="0" max="2" step="0.05" data-set="k_sirtqi" value="${S.k_sirtqi}"></label>
      <label>Masofaviy koeff.<input type="number" min="0" max="2" step="0.05" data-set="k_masofaviy" value="${S.k_masofaviy}"></label></div>
    <div class="row-actions sy-lbar">${m.can.load_save ? `<button type="button" class="btn primary sm" id="syLSave">${ico("check", 15)} Rejani saqlash</button>` : ""}
      <button type="button" class="btn sm" id="syLX">${ico("download", 15)} XLSX</button>
      ${m.can.load_docx ? `<button type="button" class="btn sm" id="syLW">${ico("file", 15)} DOCX · Hujjatlar markazi</button>` : ""}
      <button type="button" class="btn ghost sm" id="syLR">${ico("refresh", 15)} Me'yorga qaytarish</button></div></div>
    <div id="syLOut"></div>`;
  sylLoadOut(d, true);
  if ($("#syLD")) $("#syLD").onchange = e => { SYL.ldept = +e.target.value; renderSyllabus().catch(sylErr); };
  body.querySelectorAll("[data-set]").forEach(x => x.oninput = () => { SYL.lset[x.dataset.set] = x.value; sylLoadCalc(); });
  $("#syLR").onclick = () => { SYL.lset = {...d.defaults}; SYL.lrows = {}; body.querySelectorAll("[data-set]").forEach(x => x.value = SYL.lset[x.dataset.set]); sylLoadCalc(true); };
  $("#syLSave")?.addEventListener("click", e => sylBusy(e.currentTarget, async () => { await sylApi("/api/syllabus/load/save", {department_id: SYL.ldept, settings: SYL.lset, rows: SYL.lrows}); toast("Yuklama rejasi saqlandi"); }));
  $("#syLX").onclick = e => sylBusy(e.currentTarget, async () => {
    const r = await fetch("/api/syllabus/load/export", {method: "POST", credentials: "same-origin", headers: {"Content-Type": "application/json"}, body: JSON.stringify({department_id: SYL.ldept, settings: SYL.lset, rows: SYL.lrows, fmt: "xlsx"})});
    if (!r.ok) { const j = await r.json().catch(() => ({})); throw Object.assign(new Error("api"), {msg: j.message || j.detail}); }
    const b = await r.blob(), a = document.createElement("a"); a.href = URL.createObjectURL(b);
    a.download = (r.headers.get("Content-Disposition") || "").match(/filename="([^"]+)"/)?.[1] || "yuklama.xlsx"; document.body.appendChild(a); a.click(); a.remove(); setTimeout(() => URL.revokeObjectURL(a.href), 2000);
  });
  $("#syLW")?.addEventListener("click", e => sylBusy(e.currentTarget, async () => {
    const r = await sylApi("/api/syllabus/load/export", {department_id: SYL.ldept, settings: SYL.lset, rows: SYL.lrows, fmt: "docx"});
    toast(`Hujjat ${r.regs[0]} ro'yxatga olindi (Hujjatlar markazi → reyestr)`);
    const a = document.createElement("a"); a.href = `/api/docs/file/${encodeURIComponent(r.file)}`; a.download = r.file; document.body.appendChild(a); a.click(); a.remove();
  }));
}
function sylLoadCalc(full) {
  clearTimeout(SYL.ltimer);
  SYL.ltimer = setTimeout(async () => {
    try { const d = await sylApi("/api/syllabus/load/calc", {department_id: SYL.ldept, settings: SYL.lset, rows: SYL.lrows}); SYL.load = {...SYL.load, ...d}; sylLoadOut(SYL.load, full); }
    catch (e) { sylErr(e); }
  }, 300);
}
function sylLoadOut(d, full) {
  const s = d.summary, out = $("#syLOut"); if (!out) return;
  const kpi = `<div class="sy-kpis">
    <div class="card kpi"><div class="l">Hisoblangan yuklama</div><div class="v">${fh(s.total)}</div><div class="s">soat · ${s.stavka} stavka</div></div>
    <div class="card kpi"><div class="l">Joriy taqsimot</div><div class="v">${fmt(s.current)}</div><div class="s">teachers.load_hours · ${s.current_stavka} stavka</div></div>
    <div class="card kpi ${s.diff < 0 ? "warn" : ""}"><div class="l">Farq</div><div class="v">${s.diff > 0 ? "+" : ""}${fh(s.diff)}</div><div class="s">soat (hisob − joriy)</div></div>
    <div class="card kpi"><div class="l">O'qituvchilar</div><div class="v">${s.staff}</div><div class="s">${s.over} ortiqcha · ${s.under} kam yuklama</div></div></div>`;
  if (full || !$("#syLSubj")) {
    out.innerHTML = kpi + `<div class="card"><h3>${ico("book")} Fanlar <span class="muted tiny">${s.subjects} fan · ${s.groups} guruh · o'zgartirilgan katak bo'yalgan</span></h3>
      <div class="tw"><table class="sy-lt" id="syLSubj"><thead><tr><th>Fan</th><th class="n">Guruh</th><th class="n">Potok</th><th class="n">Kichik guruh</th><th class="n">Ma'ruza<small>1 potok</small></th><th class="n">Amaliy<small>1 guruh</small></th><th class="n">Seminar<small>1 guruh</small></th><th class="n">Lab.<small>1 kichik guruh</small></th><th class="n">Jami soat</th></tr></thead>
      <tbody>${d.rows.map((r, i) => `<tr data-s="${esc(r.subject)}"><td><b>${esc(r.subject)}</b><small class="muted sy-forms">${Object.entries(r.forms).map(([k, v]) => `${k} ${v}`).join(" · ")}</small></td><td class="n">${r.groups}</td>
        ${[["streams", r.streams], ["subgroups", r.subgroups], ["lecture", r.hours.lecture], ["practice", r.hours.practice], ["seminar", r.hours.seminar], ["lab", r.hours.lab]].map(([k, v]) =>
          `<td class="n"><input type="number" min="${k === "streams" || k === "subgroups" ? 1 : 0}" max="${k === "streams" ? r.groups : k === "subgroups" ? 6 : 400}" data-ov="${k}" data-i="${i}" value="${v}" class="${r.overridden.includes(k) ? "ov" : ""}" aria-label="${esc(r.subject)}: ${k}"></td>`).join("")}
        <td class="n"><b data-tot="${i}">${fh(r.total)}</b></td></tr>`).join("")}</tbody>
      <tfoot><tr><th>Jami</th><th class="n">${s.groups}</th><th colspan="6" class="n muted">ma'ruza ${fh(s.by_type.lecture)} · amaliy ${fh(s.by_type.practice)} · seminar ${fh(s.by_type.seminar)} · lab. ${fh(s.by_type.lab)}</th><th class="n" id="syLTot">${fh(s.total)}</th></tr></tfoot></table></div></div>
      <div class="card" id="syLT"></div>`;
    out.querySelectorAll("[data-ov]").forEach(x => x.oninput = () => {
      const r = d.rows[+x.dataset.i], k = x.dataset.ov; (SYL.lrows[r.subject] ||= {})[k] = x.value === "" ? null : +x.value; x.classList.add("ov"); sylLoadCalc(false);
    });
  } else {
    out.querySelector(".sy-kpis").outerHTML = kpi;
    d.rows.forEach(r => { const tr = out.querySelector(`tr[data-s="${CSS.escape(r.subject)}"]`); if (!tr) return;
      const i = tr.querySelector("[data-tot]"); i.textContent = fh(r.total);
      const st = tr.querySelector('[data-ov="streams"]'); if (st && document.activeElement !== st && !r.overridden.includes("streams")) st.value = r.streams; });
    $("#syLTot").textContent = fh(s.total);
  }
  $("#syLT").innerHTML = `<h3>${ico("users")} O'qituvchilar kesimida <span class="muted tiny">stavka = hisob / ${d.load_norm}; ortiqcha > 1,5 · kam < 0,75</span></h3>
    <div class="tw"><table class="sy-lt"><thead><tr><th>F.I.Sh.</th><th class="n">Ma'ruza</th><th class="n">Amaliy</th><th class="n">Seminar</th><th class="n">Lab.</th><th class="n">Hisob</th><th>Stavka</th><th class="n">Joriy</th><th class="n">Farq</th></tr></thead>
    <tbody>${d.teachers.map(t => `<tr><td><b>${esc(t.name)}</b><small class="muted">${esc(t.position || "")} · ${t.groups} guruh</small></td><td class="n">${fh(t.lecture)}</td><td class="n">${fh(t.practice)}</td><td class="n">${fh(t.seminar)}</td><td class="n">${fh(t.lab)}</td>
      <td class="n"><b>${fh(t.total)}</b></td><td><span class="sy-stv">${syMeter(Math.min(100, t.stavka / 1.5 * 100), t.flag === "ortiqcha" ? "bad" : t.flag === "kam" ? "warn" : "good")}<span>${String(t.stavka).replace(".", ",")}</span>${t.flag !== "me'yorda" ? `<em class="${t.flag === "ortiqcha" ? "bad" : "warnc"}">${t.flag}</em>` : ""}</span></td>
      <td class="n">${fmt(t.current)}</td><td class="n ${Math.abs(t.diff) > 150 ? "bad" : ""}">${t.diff > 0 ? "+" : ""}${fh(t.diff)}</td></tr>`).join("")}</tbody></table></div>`;
}

/* =====================================================================
   3. Kafedra so'rovlari
   ===================================================================== */
async function sylTasks(body) {
  const L = SYL.tasks = await sylApi("/api/syllabus/tasks");
  if (SYL.task) return sylTask(body);
  body.innerHTML = `<div class="src-note sy-tnote">${ico("info", 15)}<span>Bu yerda — o'quv dasturi va yuklama bo'yicha so'rovlar: kafedra natijani yuboradi, Akademik bo'lim <b>qabul qiladi</b> yoki <b>izoh bilan qayta ishlashga qaytaradi</b>. Boshqa topshiriqlar — «Majlislar va topshiriqlar» bo'limida.</span></div>
    ${L.can_create ? `<div class="row-actions sy-tbar"><button type="button" class="btn primary sm" id="syTNew" aria-expanded="${SYL.tnew}">${ico("plus", 15)} Yangi so'rov</button></div><div id="syTForm"></div>` : ""}
    <div class="sy-tasks">${L.tasks.map(t => `<a href="#" class="card sy-task" data-t="${t.id}"><div class="sy-task-h"><span class="tag gray">${esc(t.kind_label)}</span>${t.status !== "ochiq" ? `<span class="tag low">Yopilgan</span>` : ""}${t.overdue ? `<span class="tag high">${t.overdue} ta kechikkan</span>` : ""}</div>
      <b>${esc(t.title)}</b><small class="muted">Muddat ${dmy(t.due)} · ${esc(t.created_name || "")}</small>
      <div class="sy-uchips">${t.units.map(u => `<span class="sy-u ${u.status}${u.overdue ? " over" : ""}" title="${esc(u.department)}: ${esc(u.status_label)}">${esc(u.department)}</span>`).join("")}</div>
      <small class="muted">${Object.entries(t.counts).filter(([, n]) => n).map(([k, n]) => `${n} ${({yangi: "kutilmoqda", topshirildi: "ko'rib chiqilmoqda", qabul: "qabul qilingan", qayta: "qaytarilgan"})[k]}`).join(" · ")}</small></a>`).join("") || `<div class="card sy-empty">${ico("inbox", 26)}<b>So'rovlar yo'q</b></div>`}</div>`;
  body.querySelectorAll(".sy-task").forEach(a => a.onclick = e => { e.preventDefault(); SYL.task = +a.dataset.t; sylTask(body).catch(sylErr); });
  if ($("#syTNew")) { $("#syTNew").onclick = () => { SYL.tnew = !SYL.tnew; sylTaskForm(L); }; if (SYL.tnew) sylTaskForm(L); }
}
function sylTaskForm(L) {
  const box = $("#syTForm"); $("#syTNew").setAttribute("aria-expanded", SYL.tnew);
  if (!SYL.tnew) { box.innerHTML = ""; return; }
  const due = new Date(Date.parse(SYL.meta.today) + 7 * 864e5).toISOString().slice(0, 10);
  box.innerHTML = `<form class="card sy-tf" id="syTF"><h3>${ico("plus")} Kafedralarga so'rov</h3><div class="form-grid">
    <label>Turi<select id="syTK">${Object.entries(L.kinds).map(([k, v]) => `<option value="${k}">${esc(v)}</option>`).join("")}</select></label>
    <label>Muddat<input type="date" id="syTD" value="${due}" min="${SYL.meta.today}" required></label>
    <label class="full">Mavzu<input type="text" id="syTT" maxlength="200" required placeholder="Masalan: Bahorgi semestr yuklama rejasini topshirish"></label>
    <label class="full">Matn<textarea id="syTB" rows="3" maxlength="4000" placeholder="Nima talab qilinadi, qaysi shaklda"></textarea></label></div>
    <fieldset class="sy-fs"><legend><label><input type="checkbox" id="syTAll"> Barcha kafedralar</label></legend>${L.departments.map(d => `<label class="sy-ck"><input type="checkbox" name="tdep" value="${d.id}"> <span>${esc(d.name)}</span></label>`).join("")}</fieldset>
    <div class="row-actions"><button type="submit" class="btn primary" id="syTGo">${ico("send", 15)} Yuborish</button><button type="button" class="btn ghost" id="syTX">Bekor qilish</button></div></form>`;
  $("#syTAll").onchange = e => document.querySelectorAll('input[name="tdep"]').forEach(x => x.checked = e.target.checked);
  $("#syTX").onclick = () => { SYL.tnew = false; sylTaskForm(L); };
  $("#syTF").onsubmit = e => { e.preventDefault(); sylBusy($("#syTGo"), async () => {
    const deps = [...document.querySelectorAll('input[name="tdep"]:checked')].map(x => +x.value);
    if (!deps.length) return toast("Kamida bitta kafedrani tanlang");
    const r = await sylApi("/api/syllabus/tasks", {kind: $("#syTK").value, title: $("#syTT").value, body: $("#syTB").value, due: $("#syTD").value, departments: deps});
    SYL.tnew = false; SYL.task = r.id; toast(`So'rov ${deps.length} ta kafedraga yuborildi`); renderSyllabus();
  }); };
}
async function sylTask(body) {
  const t = await sylApi(`/api/syllabus/tasks/${SYL.task}`), isAk = SYL.meta.role === "akademik";
  body.innerHTML = `<div class="sy-back"><button type="button" class="btn ghost sm" id="syTBack">${ico("back", 16)} So'rovlar ro'yxati</button></div>
    <div class="card sy-head"><div class="sy-head-t"><div><h3>${esc(t.title)}</h3><div class="sy-meta"><span>${esc(t.kind_label)}</span><span>Muddat ${dmy(t.due)}</span><span>${esc(t.created_name || "")} · ${syWhen(t.created_at)}</span></div></div>
      ${isAk ? `<button type="button" class="btn sm" id="syTClose">${t.status === "ochiq" ? "So'rovni yopish" : "Qayta ochish"}</button>` : ""}</div>${t.body ? `<p class="sy-tbody">${esc(t.body)}</p>` : ""}</div>
    <div class="sy-units">${t.units.map(u => `<div class="card sy-unit" data-u="${u.id}"><div class="sy-unit-h"><b>${esc(u.department)}</b><span class="sy-u ${u.status}${u.overdue ? " over" : ""}">${esc(u.status_label)}${u.overdue ? " · muddati o'tgan" : ""}</span>${u.round ? `<small class="muted">${u.round}-raund</small>` : ""}</div>
      ${u.response ? `<div class="sy-resp"><small class="muted">Javob · ${syWhen(u.submitted_at)}</small><p>${esc(u.response)}</p></div>` : ""}
      ${u.file_name ? `<p class="sy-file">${ico("file", 15)}<a href="/api/syllabus/tasks/${t.id}/units/${u.id}/file" target="_blank" rel="noopener">${esc(u.file_name)}</a></p>` : ""}
      ${u.comment && u.status === "qayta" ? `<div class="sy-ret">${ico("alert", 16)}<div><b>Qayta ishlashga qaytarildi</b><p>${esc(u.comment)}</p></div></div>` : ""}
      ${u.can_submit ? `<div class="sy-actf"><textarea rows="3" data-ans placeholder="Natija: qisqa izoh, ilova qilingan hujjat tavsifi"></textarea>
        <div class="row-actions"><button type="button" class="btn primary sm" data-sub>${ico("send", 15)} Javob yuborish</button><label class="btn sm" for="syUF${u.id}">${ico("upload", 15)} Fayl ilova qilish</label><input type="file" class="sr" id="syUF${u.id}" data-uf accept=".docx,.pdf,.xlsx"></div></div>` : ""}
      ${u.can_review ? `<div class="sy-actf"><textarea rows="2" data-rc placeholder="Izoh (qaytarishda majburiy)"></textarea>
        <div class="row-actions"><button type="button" class="btn primary sm" data-tr="qabul">${ico("check", 15)} Qabul qilish</button><button type="button" class="btn sm" data-tr="qayta">${ico("back", 15)} Qayta ishlashga qaytarish</button></div></div>` : ""}
      ${u.history.length ? `<details class="sy-det"><summary>Tarix (${u.history.length})</summary><ol class="sy-tl">${u.history.map(h => `<li class="${h.action.startsWith("qayta") ? "ret" : h.action.startsWith("qabul") ? "ok" : ""}"><b>${esc(h.action)}</b><small>${esc(h.user_name || "")} · ${syWhen(h.ts)}</small>${h.comment ? `<p>${esc(h.comment)}</p>` : ""}</li>`).join("")}</ol></details>` : ""}
    </div>`).join("")}</div>`;
  $("#syTBack").onclick = () => { SYL.task = null; sylTasks(body).catch(sylErr); };
  $("#syTClose")?.addEventListener("click", e => sylBusy(e.currentTarget, async () => { await sylApi(`/api/syllabus/tasks/${t.id}/close`, {}); toast(t.status === "ochiq" ? "So'rov yopildi" : "So'rov qayta ochildi"); sylTask(body); }));
  body.querySelectorAll(".sy-unit").forEach(card => {
    const uid = +card.dataset.u, base = `/api/syllabus/tasks/${t.id}/units/${uid}`;
    card.querySelector("[data-sub]")?.addEventListener("click", e => sylBusy(e.currentTarget, async () => { await sylApi(`${base}/submit`, {text: card.querySelector("[data-ans]").value}); toast("Javob Akademik bo'limga yuborildi"); sylTask(body); if (typeof badges === "function") badges(); }));
    card.querySelector("[data-uf]")?.addEventListener("change", e => { const f = e.target.files[0]; if (!f) return; sylBusy(card.querySelector("[data-sub]"), async () => { await sylRaw(`${base}/file?name=${encodeURIComponent(f.name)}`, f); toast("Fayl ilova qilindi — endi javobni yuboring"); const keep = card.querySelector("[data-ans]").value; await sylTask(body); const n = document.querySelector(`.sy-unit[data-u="${uid}"] [data-ans]`); if (n) n.value = keep; }); });
    card.querySelectorAll("[data-tr]").forEach(b => b.onclick = () => sylBusy(b, async () => {
      const cm = card.querySelector("[data-rc]").value.trim();
      if (b.dataset.tr === "qayta" && cm.length < 5) { card.querySelector("[data-rc]").focus(); return toast("Qaytarish uchun izoh yozing"); }
      await sylApi(`${base}/review`, {action: b.dataset.tr, comment: cm}); toast(b.dataset.tr === "qabul" ? "Javob qabul qilindi" : "Qayta ishlashga qaytarildi"); sylTask(body); if (typeof badges === "function") badges();
    }));
  });
}
