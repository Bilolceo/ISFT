/* =====================================================================
   Bo'limlararo portal — ichki yozishmalar, ish fayllari almashinuvi, umumiy bazalar.
   app.js yordamchilaridan foydalanadi: J, api, esc, fmt, toast, go, busy, dmy, ME, badges, ico, ICONS, hydrateIcons, tbl.
   Global: renderPortal(), portalBadge(set)
   Uslublar: portal.css (shu fayldan ulanadi)
   ===================================================================== */
const PT = {tab: "mail", box: "inbox", q: "", flt: "all", open: null, compose: false, units: null, list: null, items: [], drafts: null,
            d: null, act: null, rcOpen: false, resSel: new Set(), reSel: new Set(), fwdSel: new Set(), org: null, oq: "", oedit: null, draftId: null, cdraft: null, cs: 0, dids: {}, dt: null, dsave: null, tpls: null,
            fq: "", fscope: "all", funit: "", fcat: "", upload: false, ds: null, dsq: "", dsoff: 0, att: [], to: new Set(), share: new Set(),
            stu: new Map(), stuNote: "", stuSel: new Set(), stuExp: false, stuAdd: null};
try { PT.tab = localStorage.getItem("jarvis.portalTab") || "mail"; } catch (e) {}
if (!document.querySelector('link[href="portal.css"]')) document.head.insertAdjacentHTML("beforeend", '<link rel="stylesheet" href="portal.css">');

if (typeof ICONS === "object") {
  Object.assign(ICONS, {
    portal: '<path d="M7 7h11l-3-3"/><path d="M17 17H6l3 3"/><rect x="3" y="3" width="18" height="18" rx="4" opacity=".35"/>',
    inbox: '<path d="M22 12h-6l-2 3h-4l-2-3H2"/><path d="M5.45 5.11 2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.45-6.89A2 2 0 0 0 16.76 4H7.24a2 2 0 0 0-1.79 1.11z"/>',
    clip: '<path d="m21.44 11.05-9.19 9.19a6 6 0 0 1-8.49-8.49l8.57-8.57A4 4 0 1 1 18 8.84l-8.59 8.57a2 2 0 0 1-2.83-2.83l8.49-8.48"/>',
    upload: '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><path d="m17 8-5-5-5 5"/><path d="M12 3v12"/>',
    download: '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><path d="m7 10 5 5 5-5"/><path d="M12 15V3"/>',
    db: '<ellipse cx="12" cy="5" rx="8" ry="3"/><path d="M4 5v14c0 1.7 3.6 3 8 3s8-1.3 8-3V5"/><path d="M4 12c0 1.7 3.6 3 8 3s8-1.3 8-3"/>',
    reply: '<path d="m9 17-5-5 5-5"/><path d="M20 18v-2a4 4 0 0 0-4-4H4"/>',
    pen: '<path d="M12 20h9"/><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4z"/>',
    back: '<path d="m15 18-6-6 6-6"/>',
    chev: '<path d="m6 9 6 6 6-6"/>',
    undo: '<path d="M9 14 4 9l5-5"/><path d="M4 9h10.5a5.5 5.5 0 0 1 0 11H11"/>',
    plus: '<path d="M12 5v14M5 12h14"/>',
    org: '<rect x="9" y="2.5" width="6" height="5" rx="1.2"/><rect x="2.5" y="16.5" width="6" height="5" rx="1.2"/><rect x="15.5" y="16.5" width="6" height="5" rx="1.2"/><path d="M12 7.5v4.5M5.5 16.5V12h13v4.5"/>',
  });
  try { const s = document.querySelector('#nav a[data-v="portal"] svg'); if (s && !s.innerHTML.trim()) { s.remove(); hydrateIcons(); } } catch (e) {}
}

const PT_ST = {"yangi": ["Yangi", "new"], "o'qilgan": ["O'qilgan", "read"], "javob berilgan": ["Javob berilgan", "done"], "yo'naltirilgan": ["Yo'naltirilgan", "fwd"], "qaytarilgan": ["Qaytarib olingan", "off"]};
const PT_PRIO = {muhim: ["Muhim", "mid"], shoshilinch: ["Shoshilinch", "high"]};
const PT_FSCOPE = [["all", "Barcha fayllar", "folder"], ["mine", "Mening bo'limim", "inbox"], ["shared", "Menga ulashilgan", "users"]];
const ptKind = k => (PT.units?.kinds || {})[k] || k;
const ptTime = s => {
  if (!s) return ""; const d = new Date(s), t = `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
  const day = s.slice(0, 10), today = ME?.today || "", y = new Date(new Date(today + "T00:00:00") - 864e5).toISOString().slice(0, 10);
  return day === today ? t : day === y ? `kecha, ${t}` : `${dmy(day)}`;
};
const ptFull = s => s ? `${dmy(s.slice(0, 10))}, ${s.slice(11, 16)}` : "";
const ptAgo = s => { if (!s) return "—"; const m = Math.max(0, Math.round((Date.now() - new Date(s)) / 6e4)); return m < 60 ? `${m || 1} daq. oldin` : m < 1440 ? `${Math.round(m / 60)} soat oldin` : m < 2880 ? "kecha" : `${Math.round(m / 1440)} kun oldin`; };
const ptSize = b => b < 1024 ? `${b} B` : b < 1048576 ? `${Math.round(b / 1024)} KB` : `${(b / 1048576).toFixed(1)} MB`;
const ptDue = (due, overdue, done) => {
  if (!due) return "";
  const days = Math.round((new Date(due + "T00:00:00") - new Date((ME?.today || "") + "T00:00:00")) / 864e5);
  const cls = overdue ? "bad" : done ? "" : days <= 2 ? "warn" : "";
  const txt = overdue ? `Muddat o'tgan · ${dmy(due)}` : done ? `Muddat ${dmy(due)}` : days === 0 ? "Muddat — bugun" : days === 1 ? "Muddat — ertaga" : `Muddat ${dmy(due)}`;
  return `<span class="pt-due ${cls}">${ico("clock", 13)}${txt}</span>`;
};
/* overdue=true, lekin sana hali kelmagan — demak, kimdir (ijrochi) o'z muddatini o'tkazgan */
const ptDueX = (due, overdue, done) => overdue && due && due >= (ME?.today || "") ? ptDue(due, false, done) + `<span class="pt-tag late" title="Kamida bitta ijrochining muddati o'tgan">${ico("alert", 13)}Ijro kechikkan</span>` : ptDue(due, overdue, done);
const ptStTag = s => `<span class="pt-st ${(PT_ST[s] || ["", ""])[1]}">${esc((PT_ST[s] || [s])[0])}</span>`;
const ptPrio = p => PT_PRIO[p] ? `<span class="pt-prio ${PT_PRIO[p][1]}">${PT_PRIO[p][0]}</span>` : "";
const ptWbr = n => esc(n).replace(/([_\-])/g, "$1<wbr>").replace(/\.(?=[a-z0-9]+$)/i, "<wbr>.");
const ptExt = e => `<span class="pt-ext e-${esc(e)}">${esc(String(e).toUpperCase().slice(0, 4))}</span>`;
const ptInit = n => { const w = String(n || "").replace(/[^\p{L}\s]/gu, "").split(/\s+/).filter(x => x && !/^(va|bo|bo'yicha|ishlari)$/i.test(x)); return ((w[0] || "")[0] || "").toUpperCase() + ((w[1] || "")[0] || "").toUpperCase(); };
const ptUnit = k => (PT.units?.units || []).find(u => u.key === k);
const ptShortUnit = n => String(n || "").replace(/ kafedrasi$/, " kaf.").replace(/ fakulteti$/, " fak.");

/* ---------- menyudagi belgi (app.js badges() chaqiradi) ---------- */
/* menyu belgisi — yagona qoida: «mendan harakat kutilayotgan» xatlar (menga biriktirilgan javobsiz, rahbar uchun — bo'limga kelgan
   biriktirilmagan, men ko'rib chiqishim kerak bo'lgan javob, qaytarilgan javob); o'qilmaganlar soni — sahifa ichidagi yorliqlarda */
async function portalBadge(set) {
  try {
    const s = await J("/api/portal/summary"); PT.sum = s;
    const tip = `Harakatingizni kutayotgan xatlar: ${s.action || 0}` + (s.assigned_to_me ? ` · sizga biriktirilgan: ${s.assigned_to_me}` : "")
      + (s.to_review ? ` · ko'rib chiqish: ${s.to_review}` : "") + (s.inbox_returned ? ` · qaytarilgan: ${s.inbox_returned}` : "")
      + (s.unread ? ` · o'qilmagan: ${s.unread}` : "");
    set("portal", s.action || 0, tip);
    if (document.querySelector("#v-portal:not(.hidden)")) ptTabCounts();
  } catch (e) {}
}
function ptTabCounts() {
  const em = document.querySelector('#v-portal .pn-tab[data-pt="mail"] em');
  if (em && PT.sum) { em.textContent = PT.sum.unread; em.hidden = !PT.sum.unread; }
}

/* ---------- asosiy ko'rinish ---------- */
async function renderPortal() {
  const el = $("#v-portal");
  if (!el.innerHTML) el.innerHTML = `<p class="muted">Yuklanmoqda…</p>`;
  if (!PT.units) PT.units = await J("/api/portal/units");
  const me = ptUnit(PT.units.me) || {name: ME.role};
  const tabs = [["mail", "Yozishmalar", "mail"], ["files", "Fayllar", "folder"], ["data", `<span class="pt-tl">Umumiy bazalar</span><span class="pt-ts">Bazalar</span>`, "db"], ["org", "Bo'limlar", "org"]];
  el.innerHTML = `<div class="head pt-head"><div><h2>Yozishmalar</h2><span class="muted">${esc(me.name)} · bo'limlar o'rtasida rasmiy xat, ish fayllari va umumiy bazalar. Rasmiy hujjat chiqarish — «Hujjatlar markazi»da.</span></div>
      <div class="row-actions"><button class="btn" id="ptUpBtn">${ico("upload", 16)}Fayl yuklash</button><button class="btn primary" id="ptNewBtn">${ico("pen", 16)}Yangi xat</button></div></div>
    <div class="pn-tabs pt-tabs" role="tablist">${tabs.map(([k, l, i]) => `<button class="pn-tab${PT.tab === k ? " on" : ""}" role="tab" aria-selected="${PT.tab === k}" data-pt="${k}">${ico(i, 16)}${l}${k === "mail" ? `<em ${PT.sum?.unread ? "" : "hidden"}>${PT.sum?.unread || 0}</em>` : ""}</button>`).join("")}</div>
    <div id="ptBody"></div>`;
  el.querySelectorAll("[data-pt]").forEach(b => b.onclick = () => ptSetTab(b.dataset.pt));
  $("#ptNewBtn").onclick = () => { ptNew(); ptSetTab("mail"); };
  $("#ptUpBtn").onclick = () => { PT.upload = true; PT.share = new Set(); ptSetTab("files"); };
  await ptRenderTab();
}
function ptSetTab(k) {
  PT.tab = k; try { localStorage.setItem("jarvis.portalTab", k); } catch (e) {}
  document.querySelectorAll("#v-portal .pn-tab").forEach(b => { const on = b.dataset.pt === k; b.classList.toggle("on", on); b.setAttribute("aria-selected", on); });
  ptRenderTab();
}
async function ptRenderTab() {
  const fn = {mail: ptMail, files: ptFiles, data: ptData, org: ptOrg}[PT.tab] || ptMail;
  try { await fn(); } catch (e) { if (!["auth", "denied"].includes(e?.message)) $("#ptBody").innerHTML = errCard("portal"); }
}

/* =====================================================================
   1) Yozishmalar
   ===================================================================== */
const PT_RS = {nazoratda: ["Nazoratda", "new"], bajarildi: ["Bajarildi", "done"], yechilgan: ["Yechilgan", ""], bekor: ["Bekor qilingan", "off"]};
const PT_CROSS = ["all", "area", "control"];
const ptHM = (d = new Date()) => `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
const ptISO = d => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
const ptAddDays = n => { const d = new Date((ME?.today || ptISO(new Date())) + "T00:00:00"); d.setDate(d.getDate() + (+n || 0)); return ptISO(d); };
const ptMe = () => (PT.units.members || []).find(m => m.me);
const ptPending = d => (d.recipients || []).filter(x => ["yangi", "o'qilgan"].includes(x.status));
/* API xatosi matni: {"detail": "..."} yoki oddiy matn */
const ptErr = e => { if (!e || ["auth", "denied"].includes(e.message)) return null; try { const j = JSON.parse(e.message); return typeof j.detail === "string" ? j.detail : null; } catch (x) { return null; } };
async function ptPost(url, body, method = "POST") {
  try { return await J(url, {method, body: JSON.stringify(body || {})}); }
  catch (e) { const m = ptErr(e); if (m) { toast(m); return null; } throw e; }
}
/* ochiq menyular tashqariga bosilganda yopiladi */
document.addEventListener("click", e => document.querySelectorAll("#v-portal .pt-menu:not([hidden])").forEach(m => {
  if (m.parentElement.contains(e.target)) return; m.hidden = true; m.parentElement.querySelector("[aria-expanded]")?.setAttribute("aria-expanded", "false");
}));
document.addEventListener("keydown", e => { if (e.key === "Escape") document.querySelectorAll("#v-portal .pt-menu:not([hidden])").forEach(m => { m.hidden = true; m.parentElement.querySelector("[aria-expanded]")?.focus(); }); });
function ptMenuToggle(btn, menu) { const on = menu.hidden; menu.hidden = !on; btn.setAttribute("aria-expanded", on); if (on) menu.querySelector("button")?.focus({preventScroll: true}); }

/* har bir "yangi xat" oynasi — alohida sessiya (PT.cs); qoralama id si sessiyaga bog'lanadi, kechikkan saqlash boshqa xatga yozilmaydi */
const ptSetDid = id => { PT.draftId = id; PT.dids[PT.cs] = id; };
function ptNew() { ptLeaveCompose(); PT.compose = true; PT.open = null; PT.to = new Set(); PT.att = []; PT.stu = new Map(); PT.stuNote = ""; PT.cdraft = null; PT.cs++; ptSetDid(null); }
function ptLeaveCompose() {
  if (!PT.compose) return;
  const had = PT.dt || PT.draftId;
  if (PT.dt) ptDraftSave();
  if (had && $("#ptCf")) toast("Qoralama saqlandi — «Qoralamalar»da");
  PT.compose = false; PT.cdraft = null; PT.cs++; ptSetDid(null);
}

async function ptLoadList(more, keep) {
  if (PT.box === "drafts") {
    if (!PT.list) PT.list = await J(`/api/portal/threads?box=inbox&flt=all&limit=1`);
    try { PT.drafts = await J("/api/portal/drafts"); } catch (e) { if (["auth", "denied"].includes(e?.message)) throw e; PT.drafts = []; }
    PT.list.counts.drafts = PT.drafts.length; PT.sum = {...(PT.sum || {}), ...PT.list.counts}; ptTabCounts(); return;
  }
  const off = more ? PT.items.length : 0, lim = keep ? Math.min(200, Math.max(50, PT.items.length)) : 50;
  const r = await J(`/api/portal/threads?box=${PT.box}&flt=${PT.flt}&q=${encodeURIComponent(PT.q)}&offset=${off}&limit=${lim}`);
  PT.items = more ? PT.items.concat(r.items.filter(x => !PT.items.some(y => y.id === x.id))) : r.items;
  PT.list = r; PT.sum = {...(PT.sum || {}), ...r.counts}; ptTabCounts();
}
function ptBoxes(c) {
  const U = PT.units;
  return [["inbox", "Kiruvchi", c.inbox_unread, 1, "inbox"], ["sent", "Yuborilgan", c.sent_unread, 1, "send"],
    U.can_resolve && ["control", "Nazorat", c.control, 1, "shield", c.control_overdue],
    U.curated?.length && ["area", "Yo'nalishim", c.area_pending, 0, "flag"],
    (U.leader || c.leader) && ["all", "Barchasi", c.all_pending, 0, "users", c.all_overdue],
    ["archive", "Arxiv", c.archive, 0, "folder"], ["drafts", "Qoralamalar", c.drafts, 0, "pen"]].filter(Boolean);
}
function ptLeadStrip(c) {
  const t = PT.box === "all" ? `Rahbariyat nazorati: <b>${c.all_pending || 0}</b> ta xat javob kutmoqda${c.all_overdue ? `, <b class="bad">${c.all_overdue}</b> tasi muddatdan o'tgan` : ""}`
    : PT.box === "control" ? `Rezolyutsiyangiz bilan nazoratda: <b>${c.control || 0}</b> ta xat${c.control_overdue ? `, <b class="bad">${c.control_overdue}</b> tasi muddatdan o'tgan` : ""}`
    : PT.box === "area" ? `Yo'nalishingizdagi bo'limlar: <b>${c.area_pending || 0}</b> ta xat javob kutmoqda`
    : PT.box === "archive" ? `Yopilgan, qaytarib olingan va siz arxivlagan yozishmalar` : PT.box === "drafts" ? `Yozilayotgan xatlar avtomatik saqlanadi`
    : PT.units?.member_only && ["inbox", "sent"].includes(PT.box) ? `Faqat sizga biriktirilgan, o'zingiz yuborgan yoki qatnashgan xatlar. Bo'limga kelgan boshqa xatlarni bo'lim rahbari taqsimlaydi.` : "";
  return t ? `<div class="pt-lead">${ico(PT.box === "archive" ? "folder" : PT.box === "drafts" ? "pen" : "shield", 14)}<span>${t}</span></div>` : "";
}
async function ptMail() {
  await ptLoadList(false, !!PT.open);
  const c = PT.list.counts, open = PT.open || PT.compose, B = ptBoxes(c), sec = B.filter(b => !b[3]), cur = sec.find(b => b[0] === PT.box);
  const hot = sec.some(b => b[5]);
  const fc = {inbox: {unread: c.inbox_unread, pending: c.inbox_pending, overdue: c.my_overdue, mine: c.assigned_to_me, returned: c.inbox_returned}, sent: {unread: c.sent_unread, review: c.to_review},
    all: {pending: c.all_pending, overdue: c.all_overdue}, control: {overdue: c.control_overdue, review: c.to_review}, area: {pending: c.area_pending}}[PT.box] || {};
  const flts = [["all", "Hammasi"], ["unread", "O'qilmagan"], ["pending", "Javobsiz"], ["overdue", "Muddati o'tgan"]].concat((PT.units.members || []).length > 1 ? [["mine", "Menga biriktirilgan"]] : [])
    .concat(["sent", "control"].includes(PT.box) ? [["review", "Ko'rib chiqish"]] : []).concat(PT.box === "inbox" && (c.inbox_returned || PT.flt === "returned") ? [["returned", "Qaytarilgan"]] : []);
  const prevRead = PT.open ? $("#ptRead")?.innerHTML : "", prevTop = $("#ptItems")?.scrollTop || 0;
  $("#ptBody").innerHTML = `<div class="pt-mail${open ? " has-open" : ""}">
    <aside class="card pt-list">
      <div class="pt-segw"><div class="pt-seg n${B.filter(b => b[3]).length + 1}" role="tablist">${B.filter(b => b[3]).map(([k, l, n, , , bad]) => `<button class="${PT.box === k ? "on" : ""}" role="tab" aria-selected="${PT.box === k}" data-box="${k}"${k === "control" ? ` title="Rezolyutsiyangiz bilan nazoratda: ${n || 0} ta${bad ? `, muddati o'tgan: ${bad} ta` : ""}"` : ""}><span class="pt-seg-l">${l}</span>${n ? `<em${bad ? ` class="bad"` : ""}>${n}</em>` : ""}</button>`).join("")}
        <button class="pt-more-b${cur ? " on" : ""}" id="ptMoreB" aria-haspopup="menu" aria-expanded="false">${cur ? cur[1] : "Yana"}${!cur && hot ? `<i class="pt-mdot" title="Muddati o'tgan xatlar bor"></i>` : ""}${ico("chev", 14)}</button></div>
        <div class="pt-menu pt-boxm" id="ptMoreM" role="menu" hidden>${sec.map(([k, l, n, , i, bad]) => `<button role="menuitem" class="${PT.box === k ? "on" : ""}" data-box="${k}">${ico(i, 16)}<span>${l}</span>${bad ? `<em class="bad" title="Muddati o'tgan">${bad}</em>` : ""}${n ? `<em>${n}</em>` : ""}</button>`).join("")}</div></div>
      ${PT.box === "drafts" ? "" : `<label class="pt-search">${ico("search", 16)}<input id="ptQ" type="search" placeholder="Mavzu, matn, raqam yoki bo'lim" value="${esc(PT.q)}" aria-label="Yozishmalarni qidirish"></label>
      <div class="pt-flt">${flts.map(([k, l]) => `<button class="${PT.flt === k ? "on" : ""}" data-flt="${k}">${l}${fc[k] ? `<em class="${["overdue", "returned"].includes(k) ? "bad" : ""}">${fc[k]}</em>` : ""}</button>`).join("")}</div>`}
      ${ptLeadStrip(c)}
      <div class="pt-items" id="ptItems">${ptItems()}</div>
    </aside>
    <section class="card pt-read" id="ptRead">${PT.compose ? "" : PT.open ? (prevRead || `<p class="muted pt-ld">Yuklanmoqda…</p>`) : ptReadEmpty(c)}</section>
  </div>`;
  const b = $("#ptBody");
  if (prevTop) $("#ptItems").scrollTop = prevTop;
  b.querySelectorAll("[data-box]").forEach(x => x.onclick = () => { ptLeaveCompose(); PT.box = x.dataset.box; PT.flt = "all"; PT.open = null; PT.act = null; ptMail(); });
  b.querySelectorAll("[data-flt]").forEach(x => x.onclick = () => { PT.flt = x.dataset.flt; ptMail(); });
  $("#ptMoreB").onclick = () => ptMenuToggle($("#ptMoreB"), $("#ptMoreM"));
  const q = $("#ptQ"); let t;
  if (q) q.oninput = () => { clearTimeout(t); t = setTimeout(async () => { PT.q = q.value.trim(); await ptLoadList(); ptDrawItems(); }, 250); };
  ptBindItems();
  if (PT.compose) ptCompose(); else if (PT.open) await ptOpen(PT.open, true);
}
function ptReadEmpty(c) {
  return `<div class="pt-empty-read"><span class="pt-er-ic">${ico("inbox", 26)}</span><b>Yozishmani tanlang</b>
    <span class="muted">${c.inbox_unread ? `Kiruvchi xatlarda <b>${c.inbox_unread}</b> ta o'qilmagan` : "Barcha kiruvchi xatlar o'qilgan"}${c.inbox_pending ? ` · <b>${c.inbox_pending}</b> ta javob kutmoqda` : ""}${c.my_overdue ? ` · <b class="bad">${c.my_overdue}</b> tasi muddatdan o'tgan` : ""}${c.assigned_to_me ? ` · sizga biriktirilgan: <b>${c.assigned_to_me}</b>` : ""}${PT.units.can_resolve && c.control ? ` · nazoratda <b>${c.control}</b> ta rezolyutsiya` : ""}${c.to_review ? ` · ko'rib chiqish kutilmoqda: <b>${c.to_review}</b>` : ""}${c.inbox_returned ? ` · qayta ishlashga qaytarilgan: <b class="bad">${c.inbox_returned}</b>` : ""}</span>
    <button class="btn primary" onclick="ptNew();ptMail()">${ico("pen", 16)}Yangi xat yozish</button></div>`;
}
function ptDrawItems() { const el = $("#ptItems"); if (!el) return; const top = el.scrollTop; el.innerHTML = ptItems(); el.scrollTop = top; ptBindItems(); }
function ptItems() {
  if (PT.box === "drafts") return ptDraftItems();
  const it = PT.items;
  const E = {inbox: ["Kiruvchi xatlar yo'q", "Yangi xatlar shu yerda paydo bo'ladi."], sent: ["Hali xat yubormagansiz", "Yuborgan xatlaringiz va ularga javoblar shu yerda."],
    control: ["Nazoratda xat yo'q", "Rezolyutsiya qo'ygan xatlaringiz shu yerda kuzatiladi."], area: ["Yo'nalishingizda xat yo'q", "Siz nazorat qiladigan bo'limlar yozishmalari shu yerda."],
    all: ["Xatlar yo'q", "Institutdagi barcha yozishmalar shu yerda."], archive: ["Arxiv bo'sh", "Yopilgan, qaytarib olingan va arxivlangan yozishmalar shu yerda saqlanadi."]}[PT.box] || ["Xatlar yo'q", ""];
  if (!it.length) return `<div class="pt-empty">${ico(PT.q ? "search" : PT.box === "archive" ? "folder" : "inbox", 22)}<b>${PT.q ? "Hech narsa topilmadi" : PT.flt !== "all" ? "Bu filtr bo'yicha xat yo'q" : E[0]}</b><span class="muted">${PT.q ? "Boshqa so'z bilan qidirib ko'ring." : E[1]}</span></div>`;
  const rest = Math.max(0, (PT.list.total ?? it.length) - it.length);
  return it.map(ptItem).join("") + (rest ? `<button class="btn sm pt-more-l" id="ptMoreL">${ico("chev", 15)}Yana yuklash (${rest} ta qoldi)</button>` : "");
}
function ptItem(t) {
  const R = t.recipients || [], toAll = R.map(x => x.name).join(", "), to1 = R.length ? esc(ptShortUnit(R[0].name)) : "—", plus = R.length > 1 ? `<em class="pt-plus">+${R.length - 1}</em>` : "";
  const toLine = `<span class="pt-wl">Kimga:</span><span class="pt-w1" title="${esc(toAll)}">${to1}</span>${plus}`;
  const cross = PT_CROSS.includes(PT.box) || (PT.box === "archive" && !["from", "to"].includes(t.role));
  const top = cross ? `<span class="pt-wl">Kimdan:</span><span class="pt-w1" title="${esc(t.from_unit_name)}">${esc(ptShortUnit(t.from_unit_name))}</span>`
    : PT.box === "sent" || t.role === "from" ? toLine : `<span class="pt-w1" title="${esc(t.from_unit_name)}">${esc(t.from_unit_name)}</span>`;
  const rec = t.status === "qaytarilgan", closed = t.status === "yopilgan" || rec, mine = t.role === "to" && t.my_status;
  const st = rec ? "" : mine && PT.box !== "control" ? ptStTag(t.my_status) : `<span class="pt-st ${t.pending ? "" : "done"}">${t.answered}/${t.total} javob</span>`;
  return `<button class="pt-it${t.unread ? " unread" : ""}${PT.open === t.id ? " on" : ""}${closed ? " closed" : ""}" data-t="${t.id}">
      <span class="pt-it-top"><span class="pt-it-who">${t.unread ? `<i class="pt-dot" title="O'qilmagan"></i>` : ""}${top}</span><span class="pt-it-time">${ptTime(t.last_at)}</span></span>
      ${cross ? `<span class="pt-it-to">${toLine}</span>` : ""}
      <b class="pt-it-subj">${esc(t.subject)}</b>
      <span class="pt-it-snip">${t.count > 1 ? `<span class="pt-it-last">${esc(ptShortUnit(t.last_unit_name))}:</span> ` : ""}${esc(t.snippet)}</span>
      <span class="pt-it-meta">${rec ? `<span class="pt-tag closed rec">${ico("undo", 13)}Qaytarib olingan</span>` : closed ? `<span class="pt-tag closed">${ico("lock", 13)}Yopilgan</span>` : ""}${t.resolution ? `<span class="pt-tag rz">${ico("pen", 13)}Rezolyutsiya</span>` : ""}${ptPrio(t.priority)}${st}${closed ? "" : ptDueX(t.due, t.overdue, mine ? !["yangi", "o'qilgan"].includes(t.my_status) : !t.pending)}${t.assignee_name ? `<span class="pt-tag asg${t.assigned_to_me ? " self" : ""}" title="Bo'limingizdagi ijrochi">${ico("user", 13)}${t.assigned_to_me ? "Ijrochi: siz" : `Ijrochi: ${esc(t.assignee_name)}`}</span>` : ""}${t.files ? `<span class="pt-clip">${ico("clip", 13)}${t.files}</span>` : ""}${t.count > 1 ? `<span class="pt-cnt">${ico("chat", 13)}${t.count}</span>` : ""}${ptRvTags(t)}</span>
      ${t.students ? ptStuMini(t.students) : ""}
    </button>`;
}
function ptDraftItems() {
  const L = PT.drafts || [];
  if (!L.length) return `<div class="pt-empty">${ico("pen", 22)}<b>Qoralamalar yo'q</b><span class="muted">Yangi xat yozayotganingizda u avtomatik saqlanadi va shu yerda turadi.</span></div>`;
  return L.map(x => { const to = x.to || [], n = (x.file_ids || []).length;
    return `<div class="pt-drw"><button class="pt-it pt-dr${PT.compose && PT.draftId === x.id ? " on" : ""}" data-dr="${x.id}">
      <span class="pt-it-top"><span class="pt-it-who">${to.length ? `<span class="pt-wl">Kimga:</span><span class="pt-w1">${esc(ptShortUnit(ptUnit(to[0])?.name || to[0]))}</span>${to.length > 1 ? `<em class="pt-plus">+${to.length - 1}</em>` : ""}` : `<span class="pt-w1">Qabul qiluvchi tanlanmagan</span>`}</span><span class="pt-it-time" title="${ptFull(x.updated_at)}">${ptTime(x.updated_at)}</span></span>
      <b class="pt-it-subj${x.subject ? "" : " nosubj"}">${esc(x.subject || "(mavzusiz)")}</b>
      <span class="pt-it-snip">${esc((x.body || "").slice(0, 200)) || "—"}</span>
      <span class="pt-it-meta"><span class="pt-tag draft">${ico("pen", 13)}Qoralama</span>${to.length ? `<span class="pt-cnt">${to.length} ta bo'lim</span>` : ""}${n ? `<span class="pt-clip">${ico("clip", 13)}${n}</span>` : ""}</span>
    </button><button class="pt-x pt-drx" data-drx="${x.id}" title="Qoralamani o'chirish" aria-label="Qoralamani o'chirish">${ico("x", 15)}</button></div>`; }).join("");
}
function ptBindItems() {
  document.querySelectorAll("#ptItems [data-t]").forEach(x => x.onclick = () => { ptLeaveCompose(); PT.act = null; ptOpen(+x.dataset.t); });
  document.querySelectorAll("#ptItems [data-dr]").forEach(x => x.onclick = () => ptOpenDraft(+x.dataset.dr));
  /* qoralamani o'chirish — qaytarib bo'lmaydi: darhol yashiriladi, 5 soniya ichida «Bekor qilish» mumkin (undoToast), keyin o'chiriladi */
  document.querySelectorAll("#ptItems [data-drx]").forEach(x => x.onclick = () => {
    const id = +x.dataset.drx, row = x.closest(".pt-drw"); if (row) row.hidden = true;
    const del = async () => {
      if (!(await ptPost(`/api/portal/drafts/${id}`, {}, "DELETE"))) { if (row?.isConnected) row.hidden = false; return; }
      Object.keys(PT.dids).forEach(k => { if (PT.dids[k] === id) delete PT.dids[k]; });
      if (PT.draftId === id) { clearTimeout(PT.dt); PT.dt = null; PT.draftId = null; if (PT.compose) { PT.compose = false; PT.cdraft = null; PT.cs++; document.querySelector(".pt-mail")?.classList.remove("has-open"); $("#ptRead").innerHTML = ptReadEmpty(PT.list.counts); } }
      await ptLoadList(); ptRefreshBoxCounts(); if (PT.box === "drafts") ptDrawItems();
    };
    if (typeof undoToast === "function") undoToast("Qoralama o'chirildi", del, {onUndo: () => { if (row?.isConnected) row.hidden = false; }});
    else del();
  });
  const m = $("#ptMoreL");
  if (m) m.onclick = () => busy(m, async () => { await ptLoadList(true); ptDrawItems(); }, "Yuklanmoqda…");
}
function ptRefreshBoxCounts() { const em = document.querySelector('#ptMoreM [data-box="drafts"] em'), n = PT.list?.counts?.drafts || 0; if (em) { em.textContent = n; em.hidden = !n; } }
async function ptOpenDraft(id) {
  const x = (PT.drafts || []).find(d => d.id === id); if (!x) return;
  ptLeaveCompose(); PT.cs++; PT.open = null; PT.compose = true; ptSetDid(x.id); PT.att = [];
  PT.cdraft = {...x, to: x.to || []}; PT.stu = new Map(); PT.stuNote = "";
  if ((x.students || []).length && PT.units.students) {
    try { const r = await J("/api/portal/students/lookup", {method: "POST", body: JSON.stringify({ids: x.students})}); PT.cdraft._stu = r.items.map(i => [i.id, i]); } catch (e) {}
  }
  if ((x.file_ids || []).length) {
    try { const f = await J("/api/portal/files?scope=all"); PT.cdraft._att = x.file_ids.map(i => f.items.find(y => y.id === i) || {id: i, name: `Fayl #${i}`, size: 0, ext: ""}); } catch (e) {}
  }
  document.querySelectorAll("#ptItems .pt-it").forEach(b => b.classList.toggle("on", +b.dataset.dr === id));
  document.querySelector(".pt-mail")?.classList.add("has-open");
  ptCompose();
}

/* ---------- yozishmani o'qish ---------- */
function ptRc(x, d) {
  const s = PT_ST[x.status] || [x.status, ""], ownDue = x.due && x.due !== d.due;
  const tip = [`${x.name} — ${s[0]}`, x.via === "rezolyutsiya" ? "rezolyutsiya bo'yicha" : x.via === "yonaltirish" ? "yo'naltirilgan" : "", x.lead ? "mas'ul ijrochi" : "",
    x.assignee_name ? `Ijrochi: ${x.assignee_name}` : "", ownDue ? `Muddat: ${dmy(x.due)}` : "",
    x.readers?.length ? `O'qidi: ${x.readers.map(r => `${r.name} ${ptTime(r.at)}`).join(", ")}` : x.read_at ? `O'qildi ${ptFull(x.read_at)}${x.read_by ? ` (${x.read_by})` : ""}` : "",
    x.answered_at ? `Javob ${ptFull(x.answered_at)}` : "", x.forwarded_to?.length ? `Yo'naltirildi: ${x.forwarded_to.join(", ")}` : ""].filter(Boolean).join(" · ");
  return `<span class="pt-rc ${s[1]}" title="${esc(tip)}"><i></i>${esc(ptShortUnit(x.name))}${x.lead ? `<em class="pt-lt">mas'ul</em>` : ""}<small>${esc(s[0])}</small>${x.review === "qabul" ? `<small class="pt-rc-rv ok" title="Javob qabul qilindi">${ico("check", 13)}qabul</small>` : x.review === "qaytarildi" ? `<small class="pt-rc-rv bad" title="Qayta ishlashga qaytarilgan">${ico("undo", 13)}qaytarildi</small>` : ""}${ownDue ? `<small class="pt-rc-due${x.overdue ? " bad" : ""}">${ico("clock", 13)}${dmy(x.due).slice(0, 5)}</small>` : ""}</span>`;
}
function ptRcRow(x, d) {
  const ownDue = x.due && x.due !== d.due;
  return `<div class="pt-rcd-r">
    <div class="pt-rcd-n"><i class="pt-sd ${(PT_ST[x.status] || ["", ""])[1]}"></i><b>${esc(x.name)}</b>${x.lead ? `<em class="pt-lt">mas'ul</em>` : ""}${x.via === "rezolyutsiya" ? `<em class="pt-via">rezolyutsiya</em>` : x.via === "yonaltirish" ? `<em class="pt-via">yo'naltirish</em>` : ""}</div>
    <div class="pt-rcd-m">${ptStTag(x.status)}${x.assignee_name ? `<span>${ico("user", 13)}Ijrochi: <b>${esc(x.assignee_name)}</b></span>` : ""}${ownDue ? ptDue(x.due, x.overdue, !["yangi", "o'qilgan"].includes(x.status)) : ""}
      ${x.readers?.length ? `<span>${ico("eye", 13)}O'qidi: ${x.readers.map(r => `${esc(r.name)} <time title="${ptFull(r.at)}">${ptTime(r.at)}</time>`).join(", ")}</span>` : x.read_at ? `<span>${ico("eye", 13)}O'qildi ${ptFull(x.read_at)}${x.read_by ? ` · ${esc(x.read_by)}` : ""}</span>` : ""}
      ${x.answered_at ? `<span>${ico("reply", 13)}Javob ${ptFull(x.answered_at)}</span>` : ""}${x.forwarded_to?.length ? `<span>${ico("send", 13)}Yo'naltirildi: ${esc(x.forwarded_to.join(", "))}</span>` : ""}
      ${x.review ? `<span class="pt-rv-st ${x.review === "qabul" ? "ok" : "bad"}">${ico(x.review === "qabul" ? "check" : "undo", 13)}${x.review === "qabul" ? "Javob qabul qilindi" : "Qayta ishlashga qaytarildi"}${x.review_by ? ` · ${esc(x.review_by)}` : ""}${x.review_at ? ` · ${ptFull(x.review_at)}` : ""}${x.review_note ? ` · <i>${esc(x.review_note)}</i>` : ""}</span>` : ""}${x.returns ? `<span>${ico("history", 13)}${x.returns} marta qaytarilgan</span>` : ""}${x.can_review && !x.review ? `<button type="button" class="pt-lnk" data-act="review">${ico("checkc", 13)}Ko'rib chiqish</button>` : ""}</div>
  </div>`;
}
function ptResCard(r) {
  const S = PT_RS[r.state] || [r.state, ""], off = r.state === "bekor";
  const btns = [r.can_edit && `<button class="btn sm ghost" data-redit="${r.id}">${ico("pen", 14)}Tahrirlash</button>`,
    r.can_cancel && `<button class="btn sm ghost pt-rx" data-rcancel="${r.id}">${ico("x", 14)}Bekor qilish</button>`,
    r.can_close && `<button class="btn sm" data-rclose="${r.id}">${ico("check", 14)}Nazoratdan yechish</button>`].filter(Boolean).join("");
  return `<section class="pt-res${r.state === "nazoratda" ? "" : " off"}${off ? " cancel" : ""}" data-res="${r.id}">
    <div class="pt-res-h"><span class="pt-res-l">${ico("pen", 13)}Rezolyutsiya</span><span class="pt-st ${S[1]}">${S[0]}</span>${r.edited_at && !off ? `<span class="pt-res-ed" title="O'zgartirilgan: ${ptFull(r.edited_at)}">tahrirlangan</span>` : ""}<span class="pt-res-t" title="${ptFull(r.created_at)}">${ptTime(r.created_at)}</span></div>
    <div class="pt-res-a"><b>${esc(r.author)}</b>${r.author_unit_name ? `<span>${esc(r.author_unit_name)}</span>` : ""}</div>
    <div class="pt-res-b">${esc(r.text)}</div>
    <div class="pt-res-u"><span class="pt-rcs-l">Ijrochilar:</span>${(r.units || []).map(u => { const s = off ? ["—", "off"] : PT_ST[u.status] || [u.status || "chiqarilgan", "off"];
      return `<span class="pt-rc ${s[1]}" title="${esc(u.name)} — ${esc(s[0])}${u.answered_at ? ` · javob ${ptFull(u.answered_at)}` : ""}"><i></i>${esc(ptShortUnit(u.name))}${u.lead && !off ? `<em class="pt-lt">mas'ul</em>` : ""}${off ? "" : `<small>${esc(s[0])}</small>`}</span>`; }).join("")}</div>
    ${off ? `<div class="pt-res-f pt-res-cx">${ico("x", 14)}<span>Bekor qilingan${r.closed_at ? ` · ${ptFull(r.closed_at)}` : ""}${r.note ? ` · <i>${esc(r.note)}</i>` : ""}</span></div>`
      : r.due || btns ? `<div class="pt-res-f">${r.due ? ptDue(r.due, r.overdue, r.state !== "nazoratda") : "<span></span>"}${btns ? `<div class="pt-res-btns">${btns}</div>` : ""}</div>` : ""}
  </section>`;
}
/* rezolyutsiya kartasida: bekor qilishni tasdiqlash (window.confirm o'rniga) */
function ptResCancel(sec, r) {
  const f = sec.querySelector(".pt-res-f"); if (!f) return;
  const back = f.innerHTML;
  const added = (r.units || []).filter(u => ["yangi", "o'qilgan"].includes(u.status)).length;
  f.outerHTML = `<div class="pt-res-f pt-res-cf" role="alertdialog" aria-label="Rezolyutsiyani bekor qilish">
    <div class="pt-warn">${ico("alert", 15)}<span><b>Rezolyutsiya bekor qilinsinmi?</b> U nazoratdan chiqadi. Shu rezolyutsiya bilan qo'shilgan va hali javob bermagan bo'limlar qabul qiluvchilardan olib tashlanadi${added ? "" : " (hozir bunday bo'lim yo'q)"}; qolganlarining rezolyutsiya muddati bekor bo'ladi.</span></div>
    <label class="pt-af-l">Izoh<input id="ptRcNote" maxlength="300" placeholder="Ixtiyoriy: masalan, masala boshqa tartibda hal qilinadi"></label>
    <div class="pt-af-f"><span></span><div class="row-actions"><button type="button" class="btn sm ghost" id="ptRcNo">Yo'q, qoldirish</button><button type="button" class="btn sm danger" id="ptRcYes">${ico("x", 15)}Rezolyutsiyani bekor qilish</button></div></div></div>`;
  const cf = sec.querySelector(".pt-res-cf"), th = document.querySelector("#ptRead .pt-th"), was = th?.classList.contains("acting");
  th?.classList.add("acting");
  $("#ptRcNote").focus({preventScroll: true}); cf.scrollIntoView({block: "nearest"});
  $("#ptRcNo").onclick = () => { cf.outerHTML = `<div class="pt-res-f">${back}</div>`; if (!was) th?.classList.remove("acting"); ptBindResCards(); };
  $("#ptRcYes").onclick = () => busy($("#ptRcYes"), async () => {
    if (await ptPost(`/api/portal/threads/${PT.open}/resolutions/${r.id}/cancel`, {note: $("#ptRcNote").value.trim()})) await ptAfter("Rezolyutsiya bekor qilindi");
  }, "…");
}
function ptBindResCards() {
  const id = PT.open, R = PT.d?.resolutions || [];
  document.querySelectorAll("#ptRead [data-rclose]").forEach(b => b.onclick = () => busy(b, async () => {
    if (await ptPost(`/api/portal/threads/${id}/resolutions/${b.dataset.rclose}/close`)) await ptAfter("Rezolyutsiya nazoratdan yechildi");
  }, "…"));
  document.querySelectorAll("#ptRead [data-rcancel]").forEach(b => b.onclick = () => ptResCancel(b.closest(".pt-res"), R.find(x => x.id === +b.dataset.rcancel)));
  document.querySelectorAll("#ptRead [data-redit]").forEach(b => b.onclick = () => { PT.resEdit = +b.dataset.redit; ptResEditMount(); });
}
/* rezolyutsiya kartasi o'rnida tahrirlash shakli (bir vaqtda bitta) */
function ptResEditMount() {
  const r = (PT.d?.resolutions || []).find(x => x.id === PT.resEdit && x.can_edit);
  if (!r) { PT.resEdit = null; return; }
  document.querySelectorAll("#ptRead .pt-resf").forEach(x => { x.outerHTML = ptResCard((PT.d.resolutions || []).find(z => z.id === +x.dataset.rid) || r); });
  const sec = document.querySelector(`#ptRead .pt-res[data-res="${r.id}"]`); if (!sec) return;
  const box = document.createElement("div"); box.className = "pt-resf"; box.dataset.rid = r.id; sec.replaceWith(box);
  ptResForm(box, r); ptBindResCards();
  document.querySelector("#ptRead .pt-th")?.classList.add("acting");
}
function ptMsg(m) {
  if (m.kind === "tizim") return `<div class="pt-sys"><span>${esc(m.body)}</span><time title="${ptFull(m.created_at)}${m.name ? " · " + esc(m.name) : ""}">${ptTime(m.created_at)}</time></div>`;
  const res = m.kind === "rezolyutsiya", ret = m.kind === "qaytarish";
  return `<article class="pt-msg${m.mine ? " mine" : ""}${m.new ? " new" : ""}${res ? " rz" : ""}${ret ? " rt" : ""}">
      ${res ? `<span class="pt-res-l">${ico("pen", 13)}Rezolyutsiya</span>` : ret ? `<span class="pt-res-l rt">${ico("undo", 13)}Qayta ishlashga qaytarildi</span>` : ""}
      <div class="pt-msg-h"><span class="pt-av">${esc(ptInit(m.unit_name))}</span>
        <div class="pt-msg-who"><b>${esc(m.unit_name)}</b>${m.name && m.name !== m.unit_name ? `<span>${esc(m.name)}${m.position && !m.unit_name.startsWith(m.position) ? ` · ${esc(m.position)}` : ""}</span>` : ""}</div>
        <span class="pt-msg-t" title="${ptFull(m.created_at)}">${m.new ? `<i class="pt-new">yangi</i>` : ""}${ptTime(m.created_at)}</span></div>
      <div class="pt-msg-b">${esc(m.body)}</div>
      ${(m.files || []).length ? `<div class="pt-att">${m.files.map(ptAttChip).join("")}</div>` : ""}
    </article>`;
}
async function ptOpen(id, keep) {
  if (PT.open !== id) { PT.act = null; PT.rcOpen = false; PT.resEdit = null; }
  PT.open = id; PT.att = [];
  document.querySelectorAll("#ptItems .pt-it").forEach(x => x.classList.toggle("on", +x.dataset.t === id));
  document.querySelector(".pt-mail")?.classList.add("has-open");
  const r = $("#ptRead"); if (!keep) r.innerHTML = `<p class="muted pt-ld">Yuklanmoqda…</p>`;
  let d;
  try { d = await J(`/api/portal/threads/${id}`); } catch (e) {
    if (PT.open !== id) return; const m = ptErr(e);
    r.innerHTML = e?.message === "denied" ? locked("Bu yozishma") : m ? `<div class="pt-empty-read"><span class="pt-er-ic">${ico("undo", 26)}</span><b>${esc(m)}</b><span class="muted">Yozishma ro'yxatlardan olib tashlandi.</span></div>` : errCard("portal");
    if (m) { PT.open = null; await ptLoadList(); ptDrawItems(); } return; }
  if (PT.open !== id || PT.compose) return;
  PT.d = d;
  const P = d.perms || {can_reply: d.can_reply}, rec = d.status === "qaytarilgan", closed = d.status === "yopilgan" || rec, R = d.recipients || [];
  const it = document.querySelector(`#ptItems [data-t="${id}"]`);
  if (it && it.classList.contains("unread")) { it.classList.remove("unread"); it.querySelector(".pt-dot")?.remove(); if (typeof badges === "function") badges(); }
  const mineR = R.find(x => x.unit === PT.units.me), stEl = it?.querySelector(".pt-st.new");
  if (stEl && mineR) stEl.outerHTML = ptStTag(mineR.status);
  const many = R.length > 4;
  const sumBtn = many ? `<b>${R.length} ta bo'lim</b>${["javob berilgan", "yo'naltirilgan", "o'qilgan", "yangi"].map(k => { const n = R.filter(x => x.status === k).length; return n ? `<span class="pt-rc ${PT_ST[k][1]}"><i></i>${n} · ${PT_ST[k][0].toLowerCase()}</span>` : ""; }).join("")}` : "";
  const nRv = R.filter(x => x.can_review && !x.review).length;
  const acts = [P.can_resolve && ["resolve", "pen", "Rezolyutsiya", 1], P.can_review && ["review", "checkc", `Ko'rib chiqish${nRv ? ` (${nRv})` : ""}`, nRv ? 1 : 0], P.can_assign && ["assign", "user", mineR?.assignee_name ? "Ijrochini almashtirish" : "Ijrochi tayinlash"],
    P.can_take && ["take", "check", "O'zimga olish"], P.can_forward && ["forward", "send", "Yo'naltirish"],
    P.can_change_due && ["due", "clock", "Muddatni o'zgartirish"], P.can_recall && ["recall", "undo", "Qaytarib olish"],
    P.can_close && !closed && ["close", "lock", "Yopish"], P.can_reopen && closed && ["reopen", "unlock", "Qayta ochish"],
    (P.can_archive || P.archived) && [P.archived ? "unarch" : "arch", "folder", P.archived ? "Arxivdan chiqarish" : "Arxivga"]].filter(Boolean);
  const msgs = (d.messages || []).map(ptMsg).join(""), res = (d.resolutions || []).map(ptResCard).join("");
  const W = d.watchers || [];
  r.innerHTML = `<div class="pt-th${closed ? " is-closed" : ""}">
    <div class="pt-th-head">
      <button class="btn sm ghost pt-back" id="ptBack">${ico("back", 16)}Ro'yxat</button>
      <div class="pt-th-meta"><span class="pt-ref">${esc(d.ref_no)}</span><span>${esc(ptKind(d.kind))}</span>${ptPrio(d.priority)}${rec ? `<span class="pt-tag closed rec">${ico("undo", 13)}Qaytarib olingan</span>` : closed ? `<span class="pt-tag closed">${ico("lock", 13)}Yopilgan</span>` : ptDueX(d.due, d.overdue, !d.overdue && !ptPending(d).length)}${P.archived ? `<span class="pt-tag">${ico("folder", 13)}Arxivda</span>` : ""}${d.students ? `<button type="button" class="pt-tag stu" id="ptStuJump" title="Talabalar ro'yxatiga o'tish">${ico("users", 13)}${d.students.total} ta talaba · ${d.students.done}/${d.students.total}</button>` : ""}</div>
      <h3>${esc(d.subject)}</h3>
      <div class="pt-th-sub"><b>${esc(d.from_unit_name)}</b>${d.from_name ? ` · ${esc(d.from_name)}` : ""} · ${ptFull(d.created_at)}${W.length ? `<span class="pt-watch">${ico("eye", 13)}Nazoratda: ${esc(W.map(w => ptShortUnit(w.name)).join(", "))}</span>` : ""}</div>
      <div class="pt-rcs">${rec ? `<span class="pt-rcs-l">Kimga edi:</span>${(d.recalled?.recipients || []).map(x => `<span class="pt-rc off" title="${esc(x.name)} — qaytarib olingan"><i></i>${esc(ptShortUnit(x.name))}</span>`).join("")}` : many ? `<button class="pt-rcs-sum" id="ptRcsT" aria-expanded="${PT.rcOpen}" aria-controls="ptRcd"><span class="pt-rcs-l">Kimga:</span>${sumBtn}${ico("chev", 15)}</button>`
        : `<span class="pt-rcs-l">Kimga:</span>${R.map(x => ptRc(x, d)).join("")}<button class="pt-rcs-more" id="ptRcsT" aria-expanded="${PT.rcOpen}" aria-controls="ptRcd">Tafsilot${ico("chev", 14)}</button>`}</div>
      ${(d.directives || []).length ? `<div class="pt-dirs">${ico("tasks", 14)}<span>Topshiriq sifatida:</span>${d.directives.map(x => `<button type="button" class="pt-tag" data-pdir="${x.id}" title="Topshiriqni ochish">${esc(ptShortUnit(x.name))} · ${x.status === "bajarildi" ? (x.review === "kutilmoqda" ? "natija qabul kutmoqda" : "bajarildi") : x.review === "qaytarildi" ? "qaytarildi" : x.status === "jarayonda" ? "jarayonda" : "yangi"}</button>`).join("")}</div>` : ""}
      ${acts.length ? `<div class="pt-acts" role="toolbar" aria-label="Amallar">${acts.map(([k, i, l, p]) => `<button class="btn sm${p ? " pt-act-p" : ""}${PT.act === k ? " on" : ""}" data-act="${k}">${ico(i, 15)}${l}</button>`).join("")}</div>` : ""}
    </div>
    <div class="pt-msgs" id="ptMsgs"><div id="ptActF" class="pt-actf"></div><div class="pt-rcd" id="ptRcd" ${PT.rcOpen ? "" : "hidden"}><div class="pt-rcd-h">${ico("users", 14)}Qabul qiluvchilar · ${R.length}</div>${R.map(x => ptRcRow(x, d)).join("")}</div><div id="ptStu">${ptStuBlock(d)}</div>${res}${msgs}</div>
    ${rec ? `<div class="pt-closed-b pt-rec-b">${ico("undo", 16)}<span><b>Xat qaytarib olingan</b>${d.closed_by ? ` · ${esc(d.closed_by)}` : ""}${d.closed_at ? ` · ${ptFull(d.closed_at)}` : ""}${d.close_note ? ` · <i>${esc(d.close_note)}</i>` : ""}<small>Qabul qiluvchilar uni ko'rmaydi. Matnni tuzatib, yangi xat sifatida qayta yuborishingiz mumkin.</small></span>${P.can_resend ? `<button class="btn sm primary" id="ptResend">${ico("pen", 14)}Tahrirlab qayta yuborish</button>` : ""}</div>`
      : closed ? `<div class="pt-closed-b">${ico("lock", 16)}<span><b>Yozishma yopilgan</b>${d.closed_by ? ` · ${esc(d.closed_by)}` : ""}${d.closed_at ? ` · ${ptFull(d.closed_at)}` : ""}${d.close_note ? ` · <i>${esc(d.close_note)}</i>` : ""}</span>${P.can_reopen ? `<button class="btn sm" data-act="reopen">${ico("unlock", 14)}Qayta ochish</button>` : ""}</div>`
      : P.can_reply ? `<div class="pt-reply">
        <textarea id="ptReplyTxt" rows="2" placeholder="Javob yozing…" aria-label="Javob matni"></textarea>
        <div class="pt-reply-f"><div class="pt-att" id="ptAtt"></div>
          <div class="pt-reply-a">${ptAttachBtns()}<button class="btn primary" id="ptSend">${ico("send", 16)}Javob yuborish</button></div></div>
      </div>` : `<div class="pt-observer">${ico("eye", 16)}<span>${d.role === "observer" ? "Rahbariyat nazorati: siz bu yozishma ishtirokchisi emassiz — faqat ko'rish. Ochilgani audit jurnaliga yozildi." : "Bu yozishmaga javob yozish huquqingiz yo'q — faqat ko'rish."}</span></div>`}
  </div>`;
  if ($("#ptRcsT")) $("#ptRcsT").onclick = () => { PT.rcOpen = !PT.rcOpen; $("#ptRcd").hidden = !PT.rcOpen; $("#ptRcsT").setAttribute("aria-expanded", PT.rcOpen); if (PT.rcOpen) { $("#ptMsgs").scrollTop = 0; if (window.innerWidth <= 980) $("#ptRcd").scrollIntoView({block: "nearest"}); } };
  r.querySelectorAll("[data-pdir]").forEach(b => b.onclick = () => { if (typeof openDirective === "function") openDirective(+b.dataset.pdir); });
  $("#ptBack").onclick = () => { PT.open = null; PT.act = null; document.querySelector(".pt-mail")?.classList.remove("has-open"); document.querySelectorAll("#ptItems .pt-it").forEach(x => x.classList.remove("on")); $("#ptRead").innerHTML = ptReadEmpty(PT.list.counts); window.scrollTo({top: 0}); };
  r.querySelectorAll("[data-act]").forEach(b => b.onclick = () => ptAction(b.dataset.act, b));
  ptBindResCards(); ptBindStu(d);
  if ($("#ptStuJump")) $("#ptStuJump").onclick = () => {   /* faqat xabarlar oynasi aylanadi (sahifa joyida qoladi); mobil ekranda — sahifa */
    const b = $("#ptStu"), ms = $("#ptMsgs"); if (!b) return;
    if (ms && ms.scrollHeight > ms.clientHeight + 4 && getComputedStyle(ms).overflowY !== "visible") ms.scrollBy({top: b.getBoundingClientRect().top - ms.getBoundingClientRect().top - 8, behavior: "smooth"});
    else b.scrollIntoView({block: "start", behavior: "smooth"});
  };
  if ($("#ptResend")) $("#ptResend").onclick = () => busy($("#ptResend"), () => ptResend(d), "…");
  const ms = $("#ptMsgs");
  if (PT.resEdit) ptResEditMount();
  if (PT.act) ptActForm(PT.act);
  else if (!keep) { const firstNew = ms.querySelector(".pt-msg.new"); if (firstNew && d.messages.length > 2) firstNew.scrollIntoView({block: "nearest"}); else ms.scrollTop = ms.scrollHeight; }
  if (P.can_reply && !closed) {
    ptBindAttach();
    $("#ptSend").onclick = () => busy($("#ptSend"), async () => {
      const body = $("#ptReplyTxt").value.trim(); if (!body) { $("#ptReplyTxt").focus(); return toast("Javob matnini yozing"); }
      if (!(await ptPost(`/api/portal/threads/${id}/reply`, {body, file_ids: PT.att.map(f => f.id)}))) return;
      PT.att = []; await ptAfter("Javob yuborildi", true);
    }, "Yuborilmoqda…");
  }
}
/* amal bajarilgach: ro'yxat, yozishma va menyu belgilari yangilanadi */
async function ptAfter(msg, toEnd) {
  toast(msg); PT.act = null; PT.resEdit = null;
  await ptMail();
  if (toEnd) { const ms = $("#ptMsgs"); if (ms) ms.scrollTop = ms.scrollHeight; }
  if (typeof badges === "function") badges();
}
async function ptAction(k, btn) {
  const id = PT.open;
  if (["resolve", "assign", "forward", "close", "due", "recall", "review"].includes(k)) { PT.act = PT.act === k ? null : k; return ptActForm(PT.act); }
  const me = ptMe();
  const run = {take: [`/api/portal/threads/${id}/assign`, {user_id: me?.id ?? null}, "Xat sizga biriktirildi"],
    reopen: [`/api/portal/threads/${id}/reopen`, {}, "Yozishma qayta ochildi"],
    arch: [`/api/portal/threads/${id}/archive`, {on: true}, "Arxivga o'tkazildi"], unarch: [`/api/portal/threads/${id}/archive`, {on: false}, "Arxivdan chiqarildi"]}[k];
  if (!run) return;
  await busy(btn, async () => { if (await ptPost(run[0], run[1])) await ptAfter(run[2]); }, "…");
}
function ptActForm(k) {
  const host = $("#ptActF"), d = PT.d, id = PT.open; if (!host || !d) return;
  document.querySelectorAll("#ptRead .pt-acts [data-act]").forEach(b => b.classList.toggle("on", b.dataset.act === k));
  document.querySelector("#ptRead .pt-th")?.classList.toggle("acting", !!k);
  if (!k) { host.innerHTML = ""; return; }
  const mineR = (d.recipients || []).find(x => x.unit === PT.units.me), M = PT.units.members || [];
  const head = ptAfHead, foot = ptAfFoot;
  if (k === "resolve") {
    ptResForm(host, null);
  } else if (k === "due") {
    const pend = ptPending(d), cur = [...new Set(pend.map(x => x.due || ""))];
    host.innerHTML = `<div class="pt-af">${head("clock", "Muddatni o'zgartirish")}
      <div class="pt-af-g2"><label class="pt-af-l">Yangi muddat<input type="date" id="ptDueNew" min="${esc(ME.today)}" value="${esc(cur.length === 1 && cur[0] >= ME.today ? cur[0] : "")}" required></label>
        ${pend.length > 1 ? `<label class="pt-af-l">Kim uchun<select id="ptDueScope"><option value="all">Javob kutilayotgan barcha bo'limlar (${pend.length})</option><option value="sel">Tanlangan bo'limlar</option></select></label>` : `<div class="pt-af-l">Kim uchun<span class="pt-due-one">${esc(pend[0]?.name || "")}</span></div>`}</div>
      <div class="pt-due-u" id="ptDueU" hidden>${pend.map(x => `<label class="pt-due-o"><input type="checkbox" value="${esc(x.unit)}"><span><b>${esc(x.name)}</b><small${x.overdue ? ` class="bad"` : ""}>hozir: ${x.due ? dmy(x.due) : "belgilanmagan"}${x.overdue ? " · muddati o'tgan" : ""}</small></span></label>`).join("")}</div>
      <label class="pt-af-l">Izoh<input id="ptDueNote" maxlength="300" placeholder="Ixtiyoriy: masalan, qo'shimcha ma'lumot kutilmoqda"></label>
      ${foot(`Hozirgi muddat: <b>${cur.length === 1 ? (cur[0] ? dmy(cur[0]) : "belgilanmagan") : "bo'limlar bo'yicha turlicha"}</b>. Yozishmada «Muddat o'zgartirildi» yozuvi qoladi.`, "ptDueGo", `${ico("check", 15)}Saqlash`)}</div>`;
    const sc = $("#ptDueScope"); if (sc) sc.onchange = () => { $("#ptDueU").hidden = sc.value !== "sel"; };
    $("#ptDueGo").onclick = () => busy($("#ptDueGo"), async () => {
      const due = $("#ptDueNew").value; if (!due) { $("#ptDueNew").focus(); return toast("Yangi muddatni tanlang"); }
      const units = sc?.value === "sel" ? [...host.querySelectorAll("#ptDueU input:checked")].map(i => i.value) : [];
      if (sc?.value === "sel" && !units.length) return toast("Kamida bitta bo'limni belgilang");
      if (await ptPost(`/api/portal/threads/${id}/due`, {due, units, note: $("#ptDueNote").value.trim()})) await ptAfter(`Muddat o'zgartirildi: ${dmy(due)}`);
    }, "…");
  } else if (k === "recall") {
    host.innerHTML = `<div class="pt-af">${head("undo", "Xatni qaytarib olish")}
      <div class="pt-warn">${ico("alert", 15)}<span>Xatni hali hech kim o'qimagan. Qaytarib olingach u qabul qiluvchilarning qutisi va qidiruvidan o'chadi. Sizda «Arxiv»da qoladi — matnni tuzatib, qayta yuborishingiz mumkin.</span></div>
      <label class="pt-af-l">Izoh<input id="ptRecNote" maxlength="300" placeholder="Ixtiyoriy: masalan, qabul qiluvchi noto'g'ri tanlangan"></label>
      ${foot("Qaytarib olish audit jurnaliga yoziladi.", "ptRecGo", `${ico("undo", 15)}Qaytarib olish`, "danger")}</div>`;
    $("#ptRecGo").onclick = () => busy($("#ptRecGo"), async () => {
      if (await ptPost(`/api/portal/threads/${id}/recall`, {note: $("#ptRecNote").value.trim()})) { PT.box = "archive"; PT.flt = "all"; await ptAfter("Xat qaytarib olindi — «Arxiv»da"); }
      else { PT.act = null; await ptOpen(id, true); }
    }, "…");
  } else if (k === "assign") {
    host.innerHTML = `<div class="pt-af">${head("user", "Bo'lim ichida ijrochi tayinlash")}
      <label class="pt-af-l">Xodim<select id="ptAsg">${mineR?.assignee_id ? `<option value="">— Ijrochini olib tashlash —</option>` : `<option value="" disabled selected>Xodimni tanlang</option>`}${M.map(m => `<option value="${m.id}" ${m.id === mineR?.assignee_id ? "selected" : ""}>${esc(m.name)}${m.position ? ` — ${esc(m.position)}` : ""}${m.me ? " (siz)" : ""}</option>`).join("")}</select></label>
      ${foot(mineR?.assignee_name ? `Hozirgi ijrochi: <b>${esc(mineR.assignee_name)}</b>` : "Tayinlangan xodimga bildirishnoma boradi.", "ptAsgGo", `${ico("check", 15)}Tayinlash`)}</div>`;
    $("#ptAsgGo").onclick = () => busy($("#ptAsgGo"), async () => {
      const v = $("#ptAsg").value; if (!v && !mineR?.assignee_id) return toast("Xodimni tanlang");
      if (await ptPost(`/api/portal/threads/${id}/assign`, {user_id: v ? +v : null})) await ptAfter(v ? "Ijrochi tayinlandi" : "Ijrochi olib tashlandi");
    }, "…");
  } else if (k === "forward") {
    host.innerHTML = `<div class="pt-af">${head("send", "Boshqa bo'limga yo'naltirish")}
      <div class="pt-cf-row"><span class="pt-cf-l">Kimga</span>${ptPicker("ptFwdU", PT.fwdSel)}</div>
      <label class="pt-af-l">Izoh<input id="ptFwdNote" maxlength="500" placeholder="Masalan: Bu masala Sirtqi bo'lim vakolatida"></label>
      ${foot("Bo'limingiz holati «Yo'naltirilgan» bo'ladi; yangi bo'lim qabul qiluvchi sifatida qo'shiladi.", "ptFwdGo", `${ico("send", 15)}Yo'naltirish`)}</div>`;
    ptBindPicker("ptFwdU", PT.fwdSel);
    $("#ptFwdGo").onclick = () => busy($("#ptFwdGo"), async () => {
      if (!PT.fwdSel.size) return toast("Bo'limni tanlang");
      if (await ptPost(`/api/portal/threads/${id}/forward`, {units: [...PT.fwdSel], note: $("#ptFwdNote").value.trim()})) { PT.fwdSel = new Set(); await ptAfter("Xat yo'naltirildi"); }
    }, "…");
  } else if (k === "close") {
    const pend = ptPending(d);
    host.innerHTML = `<div class="pt-af">${head("lock", "Yozishmani yopish")}
      ${pend.length ? `<div class="pt-warn">${ico("alert", 15)}<span><b>${pend.length} ta bo'lim</b> hali javob bermagan: ${esc(pend.slice(0, 4).map(x => ptShortUnit(x.name)).join(", "))}${pend.length > 4 ? ` va yana ${pend.length - 4} ta` : ""}. Yopilgandan keyin ular javob yoza olmaydi.</span></div>` : ""}
      <label class="pt-af-l">Yakuniy izoh<input id="ptCloseNote" maxlength="500" placeholder="Ixtiyoriy: masalan, Masala hal qilindi"></label>
      ${foot("Yopilgan yozishma «Arxiv»ga o'tadi; kerak bo'lsa qayta ochiladi.", "ptCloseGo", `${ico("lock", 15)}${pend.length ? "Baribir yopish" : "Yopish"}`, pend.length ? "danger" : "primary")}</div>`;
    $("#ptCloseGo").onclick = () => busy($("#ptCloseGo"), async () => {
      if (await ptPost(`/api/portal/threads/${id}/close`, {note: $("#ptCloseNote").value.trim()})) await ptAfter("Yozishma yopildi");
    }, "…");
  } else if (k === "review") {
    ptReviewForm(host, d, id);
  }
  host.querySelectorAll("[data-afx]").forEach(b => b.onclick = () => { PT.act = null; ptActForm(null); });
  const ms = $("#ptMsgs"); if (ms) ms.scrollTop = 0;
  if (window.innerWidth <= 980) host.scrollIntoView({block: "nearest"});
  setTimeout(() => host.querySelector("textarea, select, input:not([type=checkbox])")?.focus({preventScroll: true}), 30);
}
const ptAfHead = (i, t) => `<div class="pt-af-h"><b>${ico(i, 16)}${t}</b><button type="button" class="pt-x" data-afx aria-label="Yopish">${ico("x", 16)}</button></div>`;
const ptAfFoot = (hint, go, label, cls = "primary") => `<div class="pt-af-f"><span class="muted tiny">${hint}</span><div class="row-actions"><button type="button" class="btn sm ghost" data-afx>Bekor qilish</button><button type="button" class="btn sm ${cls}" id="${go}">${label}</button></div></div>`;
/* rezolyutsiya shakli: yangi (r = null, #ptActF ichida) yoki mavjudini tahrirlash (r — rezolyutsiya, karta o'rnida) */
function ptResForm(host, r) {
  const d = PT.d, id = PT.open, edit = !!r, p = edit ? "ptRe" : "ptRes", sel = edit ? (PT.reSel = new Set(r.units.map(u => u.unit))) : PT.resSel;
  const due0 = edit ? (r.due || "") : (d.due && d.due >= ME.today ? d.due : "");
  host.innerHTML = `<div class="pt-af rz">${ptAfHead("pen", edit ? "Rezolyutsiyani tahrirlash" : "Rezolyutsiya qo'yish")}
      <label class="pt-af-l">Ko'rsatma<textarea id="${p}Txt" rows="3" maxlength="2000" placeholder="Masalan: Registrator ofisi va Sirtqi bo'lim birgalikda ko'rib chiqib, 3 kun ichida javob bersin.">${edit ? esc(r.text) : ""}</textarea></label>
      <div class="pt-cf-row"><span class="pt-cf-l">Ijrochi bo'limlar</span>${ptPicker(`${p}U`, sel)}</div>
      <div class="pt-af-g"><label class="pt-af-l">Mas'ul ijrochi<select id="${p}Lead"></select></label><label class="pt-af-l">Ijro muddati<input type="date" id="${p}Due" min="${esc(due0 && due0 < ME.today ? due0 : ME.today)}" value="${esc(due0)}"></label></div>
      ${edit ? `<div class="pt-af-note muted tiny">${ico("info", 14)}<span>Olib tashlangan bo'lim, agar uni shu rezolyutsiya qo'shgan va u hali javob bermagan bo'lsa, qabul qiluvchilardan chiqariladi; aks holda yozishmada qoladi. Yangi muddat javob kutilayotgan ijrochilarga tatbiq etiladi.</span></div>` : ""}
      ${ptAfFoot(edit ? "O'zgarishlar yozishmada «Rezolyutsiya o'zgartirildi» xabari bilan ko'rsatiladi." : "Ijrochilar xatni qabul qiluvchi sifatida oladi va o'z muddati bilan nazoratga olinadi.", `${p}Go`, `${ico("check", 15)}${edit ? "O'zgarishlarni saqlash" : "Rezolyutsiya qo'yish"}`)}</div>`;
  let first = edit ? r.lead_unit : null;
  const lead = () => { const s = $(`#${p}Lead`), v = first || s.value, ks = [...sel]; first = null;
    s.innerHTML = ks.length ? `<option value="">— belgilanmagan —</option>` + ks.map(u => `<option value="${u}" ${u === v || ks.length === 1 ? "selected" : ""}>${esc(ptUnit(u)?.name || u)}</option>`).join("") : `<option value="">Avval ijrochini tanlang</option>`;
    s.disabled = !ks.length; };
  ptBindPicker(`${p}U`, sel, lead); lead();
  const close = () => { if (edit) { PT.resEdit = null; ptOpen(id, true); } else { PT.act = null; ptActForm(null); } };
  host.querySelectorAll("[data-afx]").forEach(b => b.onclick = close);
  $(`#${p}Go`).onclick = () => busy($(`#${p}Go`), async () => {
    const text = $(`#${p}Txt`).value.trim();
    if (!text) { $(`#${p}Txt`).focus(); return toast("Rezolyutsiya matnini yozing"); }
    if (!sel.size) return toast("Kamida bitta ijrochi bo'limni tanlang");
    const body = {text, units: [...sel], lead: $(`#${p}Lead`).value || null, due: $(`#${p}Due`).value || null};
    if (edit) { if (await ptPost(`/api/portal/threads/${id}/resolutions/${r.id}/edit`, body)) await ptAfter("Rezolyutsiya o'zgartirildi"); }
    else if (await ptPost(`/api/portal/threads/${id}/resolve`, body)) { PT.resSel = new Set(); await ptAfter("Rezolyutsiya qo'yildi"); }
  }, "Saqlanmoqda…");
  if (edit) { host.scrollIntoView({block: "nearest"}); setTimeout(() => $(`#${p}Txt`)?.focus({preventScroll: true}), 30); }
}
/* qaytarib olingan xatdan qoralama (mavjud qoralamalar API) va uni tahrirlash oynasida ochish */
async function ptResend(d) {
  const own = (d.messages || []).filter(m => m.kind === "xat" && m.unit === d.from_unit);
  const due = d.recalled?.due && d.recalled.due >= ME.today ? d.recalled.due : null;
  const r = await ptPost("/api/portal/drafts", {subject: d.subject, body: own.map(m => m.body).join("\n\n"), to: (d.recalled?.recipients || []).map(x => x.unit),
    kind: d.kind, priority: d.priority, due, file_ids: [...new Set(own.flatMap(m => (m.files || []).map(f => f.id)))], students: (d.students?.items || []).map(x => x.id)}, "PUT");
  if (!r) return;
  PT.box = "drafts"; PT.open = null; PT.act = null; await ptMail();
  await ptOpenDraft(r.id); toast("Qoralama tayyor — tahrirlab yuboring");
}
const ptAttChip = f => `<a class="pt-file" href="/api/portal/files/${f.id}/download" download title="Yuklab olish">${ptExt(f.ext)}<span><b>${esc(f.name)}</b><small>${ptSize(f.size)}${f.version > 1 ? ` · v${f.version}` : ""}</small></span>${ico("download", 15)}</a>`;

/* ---------- ilovalar (javob va yangi xat uchun) ---------- */
function ptAttachBtns() {
  return `<label class="btn sm ghost pt-attbtn" title="Kompyuterdan fayl (≤ 20 MB)">${ico("clip", 16)}Fayl<input type="file" id="ptAttFile" hidden></label>
    <button class="btn sm ghost" id="ptAttPick" type="button" title="Portaldagi fayllardan">${ico("folder", 16)}Portaldan</button>`;
}
function ptDrawAtt(user) {
  const el = $("#ptAtt"); if (!el) return;
  el.innerHTML = PT.att.map((f, i) => `<span class="pt-file sm">${ptExt(f.ext)}<span><b>${esc(f.name)}</b><small>${ptSize(f.size)}</small></span><button type="button" class="pt-x" data-rm="${i}" aria-label="Olib tashlash">${ico("x", 14)}</button></span>`).join("");
  el.querySelectorAll("[data-rm]").forEach(b => b.onclick = () => { PT.att.splice(+b.dataset.rm, 1); ptDrawAtt(1); });
  if (user && $("#ptCf")) ptDraftSched();
}
function ptBindAttach() {
  ptDrawAtt();
  const inp = $("#ptAttFile");
  if (inp) inp.onchange = async () => {
    const f = inp.files[0]; inp.value = ""; if (!f) return;
    const r = await ptUpload(f, "Yozishmalar ilovasi", [], "Xatga ilova");
    if (r) { PT.att.push({id: r.id, name: r.name, size: r.size, ext: r.name.split(".").pop()}); ptDrawAtt(1); }
  };
  const pk = $("#ptAttPick");
  if (pk) pk.onclick = async () => {
    const old = document.querySelector(".pt-pick"); if (old) { old.remove(); return; }
    const d = await J("/api/portal/files?scope=all");
    const box = document.createElement("div"); box.className = "pt-pick";
    const draw = q => { const l = d.items.filter(f => !q || f.name.toLowerCase().includes(q)).slice(0, 40);
      box.querySelector(".pt-pick-l").innerHTML = l.length ? l.map(f => `<button type="button" data-pf="${f.id}">${ptExt(f.ext)}<span><b>${esc(f.name)}</b><small>${esc(f.owner_unit_name)} · ${ptSize(f.size)}</small></span></button>`).join("") : `<p class="muted tiny" style="padding:8px">Fayl topilmadi</p>`;
      box.querySelectorAll("[data-pf]").forEach(b => b.onclick = () => { const f = d.items.find(x => x.id === +b.dataset.pf); if (!PT.att.some(a => a.id === f.id)) PT.att.push(f); ptDrawAtt(1); box.remove(); }); };
    box.innerHTML = `<input type="search" placeholder="Fayl nomi…" aria-label="Fayl qidirish"><div class="pt-pick-l"></div>`;
    pk.closest(".pt-reply-f, .pt-cf-att").appendChild(box); draw("");
    const i = box.querySelector("input"); i.oninput = () => draw(i.value.trim().toLowerCase()); i.focus();
  };
}
async function ptUpload(file, category, share, note) {
  const max = 20 * 1048576;
  if (file.size > max) { toast("Fayl hajmi 20 MB dan oshmasligi kerak"); return null; }
  const qs = new URLSearchParams({name: file.name, category, share: share.join(","), note: note || ""});
  const r = await fetch(`/api/portal/files?${qs}`, {method: "POST", credentials: "same-origin", headers: {"Content-Type": "application/octet-stream"}, body: file});
  if (r.status === 401) { showLogin(); return null; }
  if (!r.ok) { let m = "Fayl yuklanmadi"; try { m = (await r.json()).detail || m; } catch (e) {} toast(m); return null; }
  return r.json();
}

/* ---------- bo'lim tanlagich ---------- */
const PT_QUICK = [["rahbariyat", "Rahbariyat"], ["bolim", "Barcha bo'limlar"], ["fakultet", "Barcha fakultet tyutorlari"], ["kafedra", "Barcha kafedralar"]];
function ptPicker(id, sel, {all = false} = {}) {
  const U = PT.units.units.filter(u => u.key !== PT.units.me), G = PT.units.groups;
  return `<div class="pt-up" id="${id}">
    <div class="pt-up-sel" aria-live="polite"></div>
    <div class="pt-up-tools">${all ? `<label class="pt-up-all"><input type="checkbox" data-all ${sel.has("*") ? "checked" : ""}> Hamma bo'limlar</label>` : ""}
      ${PT_QUICK.map(([g, l]) => `<button type="button" class="pt-q" data-q="${g}">${l}</button>`).join("")}<button type="button" class="pt-q" data-q="">Tozalash</button></div>
    <label class="pt-search sm">${ico("search", 15)}<input type="search" data-uq placeholder="Bo'lim yoki rahbar ismi" aria-label="Bo'lim qidirish"></label>
    <div class="pt-up-list">${G.map(g => { const us = U.filter(u => u.group === g.key); return us.length ? `<div class="pt-up-g" data-g="${g.key}"><div class="pt-up-gh">${esc(g.name)}</div>${us.map(u => `
      <label class="pt-up-o" data-s="${esc((u.name + " " + (u.head || "")).toLowerCase())}"><input type="checkbox" value="${u.key}" ${sel.has(u.key) ? "checked" : ""}>
        <span><b>${esc(u.name)}</b><small>${esc(u.head || "")}${u.info?.place ? ` · ${esc(u.info.place)}` : ""}</small>${u.info?.does ? `<small class="pt-up-does">${esc(u.info.does.slice(0, 3).join(" · "))}${u.info.does.length > 3 ? " …" : ""}</small>` : ""}</span></label>`).join("")}</div>` : ""; }).join("")}</div>
  </div>`;
}
/* onChange — foydalanuvchi tanlovni o'zgartirganda (qoralama, mas'ul ijrochi ro'yxati uchun) */
function ptBindPicker(id, sel, onChange) {
  const root = document.getElementById(id); if (!root) return;
  const all = root.querySelector("[data-all]"), ch = () => { if (onChange) onChange(); };
  const draw = () => {
    const keys = [...sel].filter(k => k !== "*");
    root.querySelector(".pt-up-sel").innerHTML = sel.has("*") ? `<span class="pt-chip all">${ico("users", 14)}Hamma bo'limlar</span>`
      : keys.length ? keys.slice(0, 8).map(k => `<span class="pt-chip">${esc(ptShortUnit(ptUnit(k)?.name || k))}<button type="button" data-un="${k}" aria-label="Olib tashlash">${ico("x", 12)}</button></span>`).join("") + (keys.length > 8 ? `<span class="pt-chip more">+${keys.length - 8}</span>` : "")
      : `<span class="muted tiny">Hali tanlanmagan — quyidan belgilang</span>`;
    root.querySelectorAll("[data-un]").forEach(b => b.onclick = () => { sel.delete(b.dataset.un); sync(); });
    root.querySelector(".pt-up-list").classList.toggle("dim", sel.has("*"));
  };
  const sync = () => { root.querySelectorAll(".pt-up-o input").forEach(i => i.checked = sel.has(i.value)); if (all) all.checked = sel.has("*"); draw(); ch(); };
  root.querySelectorAll(".pt-up-o input").forEach(i => i.onchange = e => { e.stopPropagation(); i.checked ? sel.add(i.value) : sel.delete(i.value); sel.delete("*"); draw(); if (all) all.checked = false; ch(); });
  if (all) all.onchange = e => { e.stopPropagation(); all.checked ? sel.add("*") : sel.delete("*"); draw(); ch(); };
  root.querySelectorAll("[data-q]").forEach(b => b.onclick = () => {
    if (!b.dataset.q) { sel.clear(); return sync(); }
    sel.delete("*"); PT.units.units.filter(u => u.group === b.dataset.q && u.key !== PT.units.me).forEach(u => sel.add(u.key)); sync();
  });
  const q = root.querySelector("[data-uq]");
  q.oninput = e => { e.stopPropagation(); const v = q.value.trim().toLowerCase(); root.querySelectorAll(".pt-up-o").forEach(o => o.hidden = !!v && !o.dataset.s.includes(v));
    root.querySelectorAll(".pt-up-g").forEach(g => g.hidden = ![...g.querySelectorAll(".pt-up-o")].some(o => !o.hidden)); };
  draw();
}

/* ---------- yangi xat: qoralama, shablonlar ---------- */
function ptCollect() {
  if (!$("#ptCf")) return null;
  return {id: PT.draftId || undefined, subject: $("#ptSubj").value, body: $("#ptBody2").value, to: [...PT.to], kind: $("#ptKind").value, priority: $("#ptPrio").value,
    due: $("#ptDue").value || null, file_ids: PT.att.map(f => f.id), _att: PT.att.slice(), students: [...PT.stu.keys()], _stu: [...PT.stu.entries()]};
}
function ptDraftSt(t, cls = "") { const el = $("#ptDst"); if (el) { el.textContent = t; el.className = `pt-dst ${cls}`; } }
function ptDraftSched() {
  PT.cdraft = ptCollect(); clearTimeout(PT.dt); PT.dt = setTimeout(ptDraftSave, 1500); ptDraftSt("Saqlanmoqda…", "wait");
}
function ptDraftSave() {
  clearTimeout(PT.dt); PT.dt = null;
  const x = ptCollect(), s = PT.cs; if (!x) return PT.dsave;
  if (!PT.draftId && !x.subject.trim() && !x.body.trim() && !x.to.length && !x.file_ids.length && !x.students.length) { ptDraftSt(""); return PT.dsave; }
  const prev = PT.dsave;
  PT.dsave = (async () => {
    await prev;
    const {_att, _stu, ...body} = x; body.id = PT.dids[s] || undefined;
    try {
      const r = await J("/api/portal/drafts", {method: "PUT", body: JSON.stringify(body)});
      PT.dids[s] = r.id;
      if (s === PT.cs) { PT.draftId = r.id; ptDraftSt(`Qoralama saqlandi ${ptHM(r.updated_at ? new Date(r.updated_at) : new Date())}`, "ok"); }
      if (PT.box === "drafts" && $("#ptItems")) { await ptLoadList(); ptRefreshBoxCounts(); ptDrawItems(); }
    } catch (e) { if (s === PT.cs) ptDraftSt("Qoralama saqlanmadi", "bad"); }
  })();
  return PT.dsave;
}
function ptFillTpl(t) {
  const due = t.due_days ? ptAddDays(t.due_days) : "", me = ptUnit(PT.units.me)?.name || "";
  const sub = s => String(s || "").replaceAll("{sana}", dmy(ME.today)).replaceAll("{bolim}", me).replaceAll("{muddat}", due ? dmy(due) : "—");
  if (t.subject) $("#ptSubj").value = sub(t.subject);
  $("#ptBody2").value = sub(t.body);
  if (t.kind && $(`#ptKind option[value="${t.kind}"]`)) $("#ptKind").value = t.kind;
  if (t.priority && $(`#ptPrio option[value="${t.priority}"]`)) $("#ptPrio").value = t.priority;
  $("#ptDue").value = due;
  if ((t.to || []).length) { PT.to = new Set(t.to.filter(k => k !== PT.units.me && ptUnit(k))); $("#ptTo").outerHTML = ptPicker("ptTo", PT.to); ptBindPicker("ptTo", PT.to, ptDraftSched); }
  J(`/api/portal/templates/${t.id}/use`, {method: "POST", body: "{}"}).catch(() => {});
  ptDraftSched(); toast(`«${t.title}» shabloni qo'llandi`);
}
async function ptTplMenu() {
  const m = $("#ptTplM"), b = $("#ptTplB");
  if (!m.hidden) return ptMenuToggle(b, m);
  m.innerHTML = `<p class="muted tiny pt-tpl-e">Yuklanmoqda…</p>`; ptMenuToggle(b, m);
  try { PT.tpls = await J("/api/portal/templates"); } catch (e) { m.innerHTML = `<p class="muted tiny pt-tpl-e">Shablonlarni yuklab bo'lmadi</p>`; return; }
  const grp = [["institut", "Institut shablonlari"], ["bolim", "Bo'limim shablonlari"]];
  m.innerHTML = PT.tpls.length ? grp.map(([g, l]) => { const L = PT.tpls.filter(t => (t.scope || "bolim") === g); return L.length ? `<div class="pt-tpl-g">${l}</div>${L.map(t => `<div class="pt-tpl">
      <button type="button" role="menuitem" data-tpl="${t.id}"><b>${esc(t.title)}</b><small>${esc(ptKind(t.kind))}${t.due_days ? ` · muddat ${t.due_days} kun` : ""}${(t.to || []).length ? ` · ${t.to.length} ta bo'lim` : ""}${t.uses ? ` · ${t.uses} marta` : ""}</small></button>
      ${t.mine ? `<button type="button" class="pt-x" data-tplx="${t.id}" title="Shablonni o'chirish" aria-label="Shablonni o'chirish">${ico("x", 14)}</button>` : ""}</div>`).join("")}` : ""; }).join("")
    : `<p class="muted tiny pt-tpl-e">Hali shablon yo'q. Xat yozib, «Shablon sifatida saqlash»ni bosing.</p>`;
  m.querySelectorAll("[data-tpl]").forEach(x => x.onclick = () => { m.hidden = true; b.setAttribute("aria-expanded", "false"); ptFillTpl(PT.tpls.find(t => t.id === +x.dataset.tpl)); });
  m.querySelectorAll("[data-tplx]").forEach(x => x.onclick = async e => {
    e.stopPropagation(); if (!(await ptPost(`/api/portal/templates/${x.dataset.tplx}`, {}, "DELETE"))) return;
    toast("Shablon o'chirildi"); m.hidden = true; ptTplMenu();
  });
}
function ptTplSave() {
  const w = $("#ptTplSave");
  w.innerHTML = `<input id="ptTplName" maxlength="120" placeholder="Shablon nomi" aria-label="Shablon nomi"><button type="button" class="btn sm" id="ptTplOk">${ico("check", 14)}Saqlash</button><button type="button" class="pt-x" id="ptTplNo" aria-label="Bekor qilish">${ico("x", 14)}</button>`;
  const i = $("#ptTplName"); i.value = $("#ptSubj").value.trim().slice(0, 120); i.focus(); i.select();
  const reset = () => { w.innerHTML = `<button type="button" class="btn sm ghost" id="ptTplSv">${ico("folder", 15)}Shablon sifatida saqlash</button>`; $("#ptTplSv").onclick = ptTplSave; };
  $("#ptTplNo").onclick = reset;
  i.onkeydown = e => { if (e.key === "Enter") { e.preventDefault(); $("#ptTplOk").click(); } if (e.key === "Escape") reset(); };
  $("#ptTplOk").onclick = () => busy($("#ptTplOk"), async () => {
    const title = i.value.trim(); if (!title) { i.focus(); return toast("Shablon nomini kiriting"); }
    const subject = $("#ptSubj").value.trim(), body = $("#ptBody2").value.trim();
    if (!subject && !body) return toast("Avval mavzu yoki matn yozing");
    const due = $("#ptDue").value, due_days = due ? Math.max(0, Math.round((new Date(due + "T00:00:00") - new Date(ME.today + "T00:00:00")) / 864e5)) : null;
    if (await ptPost("/api/portal/templates", {title, subject, body, kind: $("#ptKind").value, priority: $("#ptPrio").value, due_days, to: [...PT.to]})) { PT.tpls = null; toast(`«${title}» shablon sifatida saqlandi`); reset(); }
  }, "…");
}
/* «Ma'lumot so'rovi» / «Topshiriq» turi: vakolatingizdagi bo'limlarga xat emas, TOPSHIRIQ yuboriladi (natija, qabul/qaytarish —
   «Majlislar va topshiriqlar» oqimi). Qolgan bo'limlarga — oddiy xat. Server ham shu qoidani qo'llaydi (portal.api_create). */
function ptDirHint() {
  const h = $("#ptDirHint"), k = $("#ptKind")?.value; if (!h) return;
  const du = new Set(PT.units.directive_units || []), sel = [...PT.to].filter(u => u !== "*");
  const dir = ["sorov", "topshiriq"].includes(k) ? sel.filter(u => du.has(u)) : [], rest = sel.filter(u => !dir.includes(u));
  h.hidden = !dir.length;
  if (dir.length) h.innerHTML = `${ico("tasks", 15)}<span><b>${dir.length} ta bo'limga topshiriq sifatida yuboriladi</b> (${esc(dir.map(u => ptShortUnit(ptUnit(u)?.name || u)).join(", "))}): ijro, natija, qabul yoki qaytarish — «Majlislar va topshiriqlar»da.${rest.length ? ` Qolgan ${rest.length} ta bo'limga — oddiy xat.` : ""}${PT.stu.size ? " Talabalar ro'yxati biriktirilgan bo'lsa — xat sifatida." : ""}</span>`;
}
function ptCompose() {
  const r = $("#ptRead"), K = PT.units.kinds, P = PT.units.prios, dr = PT.cdraft || {};
  if (PT.cdraft) { PT.to = new Set(dr.to || []); if (dr.id) ptSetDid(dr.id); if (dr._att) PT.att = dr._att.slice(); if (dr._stu) PT.stu = new Map(dr._stu); }
  if (PT.box !== "drafts") document.querySelectorAll("#ptItems .pt-it").forEach(x => x.classList.remove("on"));
  r.innerHTML = `<form class="pt-cf" id="ptCf" onsubmit="event.preventDefault()">
    <div class="pt-cf-h"><button type="button" class="btn sm ghost pt-back" id="ptCfBack">${ico("back", 16)}Ro'yxat</button><h3>${ico("pen", 18)}${PT.draftId ? "Qoralama" : "Yangi xat"}</h3>
      <div class="pt-tplw"><button type="button" class="btn sm" id="ptTplB" aria-haspopup="menu" aria-expanded="false">${ico("file", 15)}Shablondan${ico("chev", 14)}</button><div class="pt-menu pt-tplm" id="ptTplM" role="menu" hidden></div></div>
      <span class="muted tiny pt-cf-from">Yuboruvchi: <b>${esc(ptUnit(PT.units.me)?.name || ME.role)}</b></span></div>
    <div class="pt-cf-row"><span class="pt-cf-l">Kimga</span>${ptPicker("ptTo", PT.to)}</div>
    <div class="form-grid pt-cf-grid">
      <label class="full">Mavzu<input id="ptSubj" maxlength="200" placeholder="Masalan: Qishki sessiya jadvali bo'yicha" value="${esc(dr.subject || "")}" required></label>
      <label>Turi<select id="ptKind">${Object.entries(K).map(([k, v]) => `<option value="${k}" ${dr.kind === k ? "selected" : ""}>${esc(v)}</option>`).join("")}</select></label>
      <label>Muhimlik<select id="ptPrio">${Object.entries(P).map(([k, v]) => `<option value="${k}" ${dr.priority === k ? "selected" : ""}>${esc(v)}</option>`).join("")}</select></label>
      <label>Javob muddati<input id="ptDue" title="Ixtiyoriy" type="date" min="${esc(ME.today)}" value="${esc(dr.due || "")}"></label>
      <label class="full">Matn<textarea id="ptBody2" rows="7" placeholder="Hurmatli hamkasblar! …" required>${esc(dr.body || "")}</textarea></label>
    </div>
    <p class="pt-dirhint" id="ptDirHint" hidden></p>
    <div class="pt-cf-att"><div class="pt-att" id="ptAtt"></div><div class="pt-reply-a">${ptAttachBtns()}</div></div>
    ${PT.units.students ? `<div class="pt-cf-stu" id="ptStuC"></div>` : ""}
    <div class="pt-cf-f"><div class="pt-cf-fl"><span id="ptTplSave"><button type="button" class="btn sm ghost" id="ptTplSv">${ico("folder", 15)}Shablon sifatida saqlash</button></span><span class="pt-dst" id="ptDst" aria-live="polite"></span></div>
      <div class="row-actions"><button type="button" class="btn ghost" id="ptCancel">Bekor qilish</button><button class="btn primary" id="ptSendNew">${ico("send", 16)}Yuborish</button></div></div>
    <span class="muted tiny pt-cf-note">${ico("shield", 14)} Xatga ro'yxat raqami beriladi; ilovalar qabul qiluvchilarga avtomatik ulashiladi. Yozilgan matn qoralama sifatida avtomatik saqlanadi.</span>
  </form>`;
  ptBindPicker("ptTo", PT.to, () => { ptDraftSched(); ptDirHint(); }); ptBindAttach();
  if ($("#ptStuC")) ptStuCompose($("#ptStuC"));
  $("#ptKind").addEventListener("change", ptDirHint); ptDirHint();
  const f = $("#ptCf");
  f.addEventListener("input", e => { if (e.target.closest("#ptTplSave, .pt-pick, .pt-sp")) return; ptDraftSched(); });
  f.addEventListener("change", e => { if (e.target.matches("#ptKind, #ptPrio, #ptDue")) ptDraftSched(); });
  $("#ptTplB").onclick = ptTplMenu; $("#ptTplSv").onclick = ptTplSave;
  if (PT.draftId) ptDraftSt("Qoralamadan ochildi", "ok");
  const back = () => { ptLeaveCompose(); document.querySelector(".pt-mail")?.classList.remove("has-open"); document.querySelectorAll("#ptItems .pt-it").forEach(x => x.classList.remove("on")); r.innerHTML = ptReadEmpty(PT.list.counts); };
  $("#ptCfBack").onclick = back; $("#ptCancel").onclick = back;
  $("#ptSendNew").onclick = () => busy($("#ptSendNew"), async () => {
    const subject = $("#ptSubj").value.trim(), body = $("#ptBody2").value.trim();
    if (!PT.to.size) return toast("Qabul qiluvchi bo'limni tanlang");
    if (!subject) { $("#ptSubj").focus(); return toast("Mavzuni kiriting"); }
    if (!body) { $("#ptBody2").focus(); return toast("Xat matnini yozing"); }
    clearTimeout(PT.dt); PT.dt = null; await PT.dsave;
    const res = await ptPost("/api/portal/threads", {subject, body, to: [...PT.to], kind: $("#ptKind").value, priority: $("#ptPrio").value, due: $("#ptDue").value || null, file_ids: PT.att.map(f => f.id), draft_id: PT.draftId || null,
      students: [...PT.stu.keys()], student_note: PT.stu.size ? ($("#ptStuNote")?.value || "").trim() : ""});
    if (!res) return;
    const nd = (res.directives || []).length;
    toast(nd && !res.id ? `Topshiriq sifatida yuborildi: ${res.directives.map(x => ptShortUnit(x.name)).join(", ")} — ijro «Majlislar va topshiriqlar»da kuzatiladi`
      : `Xat yuborildi · ${res.ref_no}${PT.stu.size ? ` · ${PT.stu.size} ta talaba` : ""}${nd ? ` · ${nd} ta bo'limga topshiriq` : ""}`);
    PT.compose = false; PT.cdraft = null; PT.cs++; ptSetDid(null); PT.to = new Set(); PT.att = []; PT.stu = new Map(); PT.stuNote = "";
    if (typeof badges === "function") badges();
    if (!res.id && nd && typeof openDirective === "function") { openDirective(res.directives[0].id); return; }
    PT.box = "sent"; PT.flt = "all"; PT.q = ""; PT.open = res.id; await ptMail();
  }, "Yuborilmoqda…");
  if (!dr.subject && !(dr.to || []).length) setTimeout(() => r.querySelector(".pt-up [data-uq]")?.focus({preventScroll: true}), 30);
}

/* =====================================================================
   1b) Talabalar ro'yxati (xatga biriktiriladi) va javoblarni ko'rib chiqish
   Ro'yxat RBAC bo'yicha: talabalar kartochkasiga to'liq ruxsat bo'lsa — o'z ko'lamidagi talabalar ismi bilan; aks holda faqat soni va guruhlar.
   ===================================================================== */
const PT_SX = {kutilmoqda: ["Kutilmoqda", ""], bajarildi: ["Bajarildi", "done"], bajarilmadi: ["Bajarilmadi", "bad"]};
const ptPct = (n, t) => t ? Math.round(1000 * n / t) / 10 : 0;
function ptStuBar(s, big) {
  const lbl = `${s.done} / ${s.total} bajarildi${s.failed ? `, ${s.failed} bajarilmadi` : ""}`;
  return `<span class="pt-sbar${big ? " big" : ""}" role="img" aria-label="Talabalar ijrosi: ${lbl}" title="${lbl}"><i class="ok" style="width:${ptPct(s.done, s.total)}%"></i><i class="bad" style="width:${ptPct(s.failed, s.total)}%"></i></span>`;
}
function ptStuMini(s) {
  return `<span class="pt-it-stu">${ico("users", 13)}<span>${s.total} ta talaba</span>${ptStuBar(s)}<b>${s.done}/${s.total}</b>${s.failed ? `<em class="bad">${s.failed} bajarilmadi</em>` : ""}</span>`;
}
function ptRvTags(t) {
  return (t.review === "qaytarildi" && ["yangi", "o'qilgan"].includes(t.my_status) ? `<span class="pt-tag ret" title="Javobingiz qayta ishlashga qaytarilgan">${ico("undo", 13)}Qaytarildi</span>` : "")
    + (t.review === "qabul" ? `<span class="pt-tag acc" title="Javobingiz qabul qilindi">${ico("check", 13)}Qabul qilindi</span>` : "")
    + (t.to_review ? `<span class="pt-tag rvw" title="Javob keldi — qabul qiling yoki qaytaring">${ico("checkc", 13)}Ko'rib chiqish: ${t.to_review}</span>` : "");
}
/* «Buyruqlar» moduli (boshqa jamoa) bo'lsa — guruh o'zgartirish buyrug'i loyihasiga chuqur havola */
function ptOrdersAvail() { return !!document.querySelector('#nav a[data-v="orders"]') || typeof renderOrders === "function"; }
function ptToOrders(d, ids) {
  const pre = {action: "guruh_ozgartirish", student_ids: ids, source: "portal", thread_id: d.id, ref_no: d.ref_no, subject: d.subject};
  window.ORDERS_PREFILL = pre; try { sessionStorage.setItem("isft.orders.prefill", JSON.stringify(pre)); } catch (e) {}
  go("orders");
}
function ptStuBlock(d) {
  const s = d.students; if (!s) return "";
  const pend = s.items.filter(x => x.exec === "kutilmoqda").length, show = PT.stuExp ? s.items : s.items.slice(0, 6), more = s.items.length - show.length;
  const grp = s.groups.map(g => `<span class="pt-sg">${esc(g.name)}<em>${g.n}</em></span>`).join("");
  const tools = [s.can_view && s.items.length ? `<a class="btn sm ghost" href="/api/portal/threads/${d.id}/students.csv" download title="Ko'lamingizdagi talabalar ro'yxati (CSV, Excel'da ochiladi)">${ico("download", 15)}CSV</a>` : "",
    s.can_view && s.items.length && ptOrdersAvail() ? `<button type="button" class="btn sm ghost" id="ptStuOrd" title="Guruh o'zgartirish buyrug'i loyihasi (Buyruqlar moduli)">${ico("file", 15)}Buyruq loyihasi</button>` : "",
    s.can_add ? `<button type="button" class="btn sm ghost" id="ptStuAddB" aria-expanded="${!!PT.stuAdd}">${ico("plus", 15)}Talaba qo'shish</button>` : ""].filter(Boolean).join("");
  const rows = show.map(x => { const X = PT_SX[x.exec] || [x.exec, ""];
    return `<div class="pt-sr${s.can_mark ? " mk" : ""}">${s.can_mark ? `<input type="checkbox" class="pt-sr-c" value="${x.id}" ${PT.stuSel.has(x.id) ? "checked" : ""} aria-label="${esc(x.name)}">` : ""}
      <div class="pt-sr-n"><b>${esc(x.name)}</b><small>${esc(x.hemis || "")}${x.student_status && x.student_status !== "faol" ? ` · ${esc(x.student_status)}` : ""}</small></div>
      <div class="pt-sr-g">${esc(x.group || "—")}<small>${x.course ? `${x.course}-kurs` : ""}</small></div>
      <div class="pt-sr-x"><span class="pt-st ${X[1]}">${X[0]}</span>${x.exec_note ? `<small class="pt-sr-note" title="${esc(x.exec_note)}">${esc(x.exec_note)}</small>` : ""}${x.exec_by ? `<small>${esc(x.exec_by)} · ${ptTime(x.exec_at)}</small>` : ""}</div></div>`; }).join("");
  return `<section class="pt-stu" aria-label="Talabalar ro'yxati">
    <div class="pt-stu-h"><span class="pt-res-l">${ico("users", 13)}Talabalar ro'yxati</span><b>${s.total} ta</b>
      <span class="pt-stu-p">${ptStuBar(s, 1)}<span><b>${s.done}</b>/${s.total} bajarildi${s.failed ? ` · <b class="bad">${s.failed}</b> bajarilmadi` : ""}${s.pending ? ` · ${s.pending} kutilmoqda` : ""}</span></span>
      ${tools ? `<span class="pt-stu-t">${tools}</span>` : ""}</div>
    <div class="pt-stu-g">${grp}${s.executors.length ? `<span class="muted tiny">Ijrochi: ${esc(s.executors.map(e => ptShortUnit(e.name)).join(", "))}</span>` : ""}</div>
    ${PT.stuAdd ? `<div class="pt-stu-add" id="ptStuAdd"></div>` : ""}
    ${!s.can_view ? `<div class="pt-stu-lock">${ico("lock", 15)}<span>Talabalar ismi lavozimingiz uchun yopiq — faqat soni va guruhlar ko'rsatiladi.</span></div>`
      : `${s.hidden ? `<div class="pt-stu-lock">${ico("lock", 15)}<span>${s.hidden} ta talaba ko'lamingizdan tashqarida (${esc(s.scope || "")}) — ular faqat sonda hisoblangan.</span></div>` : ""}
      ${s.can_mark && s.items.length ? `<div class="pt-stu-mk" id="ptStuMk">
        <label class="pt-stu-all"><input type="checkbox" id="ptStuAll"> Hammasi</label><button type="button" class="pt-q" id="ptStuPend"${pend ? "" : " disabled"}>Kutilayotganlar (${pend})</button>
        <span class="pt-stu-n" id="ptStuN"></span>
        <span class="pt-stu-btns"><button type="button" class="btn sm" data-mk="bajarildi">${ico("check", 14)}Bajarildi</button><button type="button" class="btn sm ghost" data-mk="bajarilmadi">${ico("x", 14)}Bajarilmadi</button><button type="button" class="btn sm ghost" data-mk="kutilmoqda" title="Belgini olib tashlash">${ico("undo", 14)}</button></span>
        <div class="pt-stu-why" id="ptStuWhy" hidden><input id="ptStuWhyT" maxlength="300" placeholder="Bajarilmagan sababi (majburiy)" aria-label="Bajarilmagan sababi"><button type="button" class="btn sm danger" id="ptStuWhyGo">Saqlash</button><button type="button" class="pt-x" id="ptStuWhyX" aria-label="Bekor qilish">${ico("x", 14)}</button></div>
        <input class="pt-stu-ok" id="ptStuOkT" maxlength="300" placeholder="Izoh (ixtiyoriy): masalan, HT-2601 ga ko'chirildi" aria-label="Izoh"></div>` : ""}
      ${s.items.length ? `<div class="pt-srs">${rows}</div>${more > 0 || PT.stuExp && s.items.length > 6 ? `<button type="button" class="btn sm ghost pt-stu-more" id="ptStuMore">${PT.stuExp ? "Yig'ish" : `Yana ${more} ta talaba`}</button>` : ""}` : ""}`}
  </section>`;
}
function ptBindStu(d) {
  const s = d.students, box = $("#ptStu"); if (!s || !box) return;
  const id = d.id, redraw = () => { box.innerHTML = ptStuBlock(PT.d); ptBindStu(PT.d); };
  const more = $("#ptStuMore"); if (more) more.onclick = () => { PT.stuExp = !PT.stuExp; redraw(); };
  const ord = $("#ptStuOrd"); if (ord) ord.onclick = () => ptToOrders(d, s.items.filter(x => x.exec !== "bajarildi").map(x => x.id));
  const ab = $("#ptStuAddB"); if (ab) ab.onclick = () => { PT.stuAdd = PT.stuAdd ? null : new Map(); redraw(); };
  if (PT.stuAdd && $("#ptStuAdd")) {
    const host = $("#ptStuAdd");
    host.innerHTML = `<div class="pt-stu-addh"><b>${ico("plus", 14)}Ro'yxatga talaba qo'shish</b><button type="button" class="pt-x" id="ptStuAddX" aria-label="Yopish">${ico("x", 15)}</button></div><div id="ptStuAddP"></div>
      <div class="pt-af-f"><span class="muted tiny">Qo'shilgan talabalar ijrochilarga darhol ko'rinadi.</span><div class="row-actions"><button type="button" class="btn sm primary" id="ptStuAddGo">${ico("check", 15)}Qo'shish</button></div></div>`;
    ptStuPicker($("#ptStuAddP"), PT.stuAdd, () => {}, s.items.map(x => x.id));
    $("#ptStuAddX").onclick = () => { PT.stuAdd = null; redraw(); };
    $("#ptStuAddGo").onclick = () => busy($("#ptStuAddGo"), async () => {
      if (!PT.stuAdd.size) return toast("Talaba tanlanmagan");
      const r = await ptPost(`/api/portal/threads/${id}/students`, {students: [...PT.stuAdd.keys()]});
      if (r) { PT.stuAdd = null; await ptAfter(`${r.added} ta talaba qo'shildi`); }
    }, "…");
  }
  if (!s.can_mark) return;
  const cbs = [...box.querySelectorAll(".pt-sr-c")], all = $("#ptStuAll");
  const sync = () => { const n = PT.stuSel.size; $("#ptStuN").textContent = n ? `Tanlangan: ${n}` : "Talabalarni belgilang"; all.checked = n && s.items.every(x => PT.stuSel.has(x.id));
    box.querySelectorAll("[data-mk]").forEach(b => b.disabled = !n); };
  PT.stuSel = new Set([...PT.stuSel].filter(i => s.items.some(x => x.id === i)));
  cbs.forEach(c => c.onchange = () => { c.checked ? PT.stuSel.add(+c.value) : PT.stuSel.delete(+c.value); sync(); });
  all.onchange = () => { PT.stuSel = new Set(all.checked ? s.items.map(x => x.id) : []); cbs.forEach(c => c.checked = all.checked); sync(); };
  $("#ptStuPend").onclick = () => { PT.stuSel = new Set(s.items.filter(x => x.exec === "kutilmoqda").map(x => x.id)); if (!PT.stuExp && s.items.length > 6 && PT.stuSel.size) { PT.stuExp = true; return redraw(); } cbs.forEach(c => c.checked = PT.stuSel.has(+c.value)); sync(); };
  const send = async (status, note) => {
    const r = await ptPost(`/api/portal/threads/${id}/students/mark`, {ids: [...PT.stuSel], status, note});
    if (r) { PT.stuSel = new Set(); await ptAfter(status === "kutilmoqda" ? "Belgi olib tashlandi" : `${r.marked} ta talaba: ${PT_SX[status][0].toLowerCase()} · jami ${r.done}/${r.total}`); }
  };
  box.querySelectorAll("[data-mk]").forEach(b => b.onclick = () => {
    if (b.dataset.mk === "bajarilmadi") { $("#ptStuWhy").hidden = false; $("#ptStuWhyT").focus(); return; }
    busy(b, () => send(b.dataset.mk, b.dataset.mk === "bajarildi" ? $("#ptStuOkT").value.trim() : ""), "…");
  });
  $("#ptStuWhyX").onclick = () => { $("#ptStuWhy").hidden = true; };
  $("#ptStuWhyGo").onclick = () => busy($("#ptStuWhyGo"), async () => { const n = $("#ptStuWhyT").value.trim(); if (!n) { $("#ptStuWhyT").focus(); return toast("Bajarilmagan sababini yozing"); } await send("bajarilmadi", n); }, "…");
  sync();
}
/* javoblarni ko'rib chiqish shakli: har bir ko'rib chiqiladigan bo'lim — oxirgi javobi, «Qabul qilish» yoki izoh bilan «Qaytarish» */
function ptReviewForm(host, d, id) {
  const L = (d.recipients || []).filter(x => x.can_review);
  const last = u => (d.messages || []).filter(m => m.unit === u && m.kind === "xat").pop();
  host.innerHTML = `<div class="pt-af">${ptAfHead("checkc", "Javoblarni ko'rib chiqish")}
    ${L.length ? L.map(x => { const m = last(x.unit);
      return `<div class="pt-rv" data-rvu="${esc(x.unit)}">
        <div class="pt-rv-h"><b>${esc(x.name)}</b>${x.review === "qabul" ? `<span class="pt-tag acc">${ico("check", 13)}Qabul qilingan</span>` : ""}${x.returns ? `<span class="pt-tag">${x.returns} marta qaytarilgan</span>` : ""}<time>${ptFull(x.answered_at)}</time></div>
        ${m ? `<div class="pt-rv-b">${esc(m.body.length > 400 ? m.body.slice(0, 400) + "…" : m.body)}${(m.files || []).length ? `<div class="pt-att">${m.files.map(ptAttChip).join("")}</div>` : ""}</div>` : ""}
        <div class="pt-rv-a">${x.review === "qabul" ? "" : `<button type="button" class="btn sm primary" data-rva>${ico("check", 14)}Qabul qilish</button>`}<button type="button" class="btn sm ghost" data-rvr>${ico("undo", 14)}Qayta ishlashga qaytarish</button></div>
        <div class="pt-rv-f" hidden><label class="pt-af-l">Nimani tuzatish kerak<textarea rows="2" maxlength="1000" data-rvc placeholder="Masalan: baholash mezonlari 30/70 ko'rinishida emas — tuzatib qayta yuboring"></textarea></label>
          <div class="pt-rv-fg"><label class="pt-af-l">Yangi muddat<input type="date" data-rvd min="${esc(ME.today)}"></label>
          <div class="row-actions"><button type="button" class="btn sm ghost" data-rvx>Bekor qilish</button><button type="button" class="btn sm danger" data-rvgo>${ico("undo", 14)}Qaytarish</button></div></div></div>
      </div>`; }).join("") : `<p class="muted tiny">Ko'rib chiqiladigan javob yo'q.</p>`}
    <div class="pt-af-f"><span class="muted tiny">Qaytarilgan bo'lim yana «javob kutilmoqda» holatiga o'tadi va eslatma oladi; tarix yozishmada saqlanadi.</span><div class="row-actions"><button type="button" class="btn sm ghost" data-afx>Yopish</button></div></div></div>`;
  host.querySelectorAll(".pt-rv").forEach(card => {
    const unit = card.dataset.rvu, nm = L.find(x => x.unit === unit)?.name || unit, f = card.querySelector(".pt-rv-f");
    const acc = card.querySelector("[data-rva]");
    if (acc) acc.onclick = () => busy(acc, async () => { if (await ptPost(`/api/portal/threads/${id}/review`, {unit, decision: "accept"})) await ptAfter(`Javob qabul qilindi: ${ptShortUnit(nm)}`); }, "…");
    card.querySelector("[data-rvr]").onclick = () => { f.hidden = false; f.querySelector("[data-rvc]").focus(); };
    card.querySelector("[data-rvx]").onclick = () => { f.hidden = true; };
    const go_ = card.querySelector("[data-rvgo]");
    go_.onclick = () => busy(go_, async () => {
      const comment = f.querySelector("[data-rvc]").value.trim(); if (!comment) { f.querySelector("[data-rvc]").focus(); return toast("Qaytarish sababini yozing"); }
      if (await ptPost(`/api/portal/threads/${id}/review`, {unit, decision: "return", comment, due: f.querySelector("[data-rvd]").value || null})) await ptAfter(`Qayta ishlashga qaytarildi: ${ptShortUnit(nm)}`);
    }, "…");
  });
}
/* yangi xat: talabalar ro'yxati bloki (sarlavha tanlov o'zgarganda yangilanadi, tanlagich qayta chizilmaydi) */
function ptStuCompose(host) {
  host.innerHTML = `<div class="pt-cf-stuh" id="ptStuHd"></div><div id="ptStuP"${PT.stuOpen ? "" : " hidden"}></div><div id="ptStuNt"></div>
    <span class="muted tiny pt-stu-sc">${ico("shield", 13)}<span>Qabul qiluvchilar ro'yxatni faqat o'z ko'lami doirasida ko'radi; qolganlarga soni va guruhlar ko'rinadi. Ko'lamingiz: ${esc(PT.units.student_scope || "")}</span></span>`;
  const head = () => {
    const n = PT.stu.size, G = [...new Set([...PT.stu.values()].map(x => x.group))];
    $("#ptStuHd").innerHTML = `<span class="pt-cf-l">${ico("users", 15)}Talabalar</span>
      ${n ? `<b>${n} ta talaba</b><span class="muted tiny pt-stu-gs">${esc(G.slice(0, 4).join(", "))}${G.length > 4 ? " …" : ""}</span>` : `<span class="muted tiny pt-stu-gs">Xat aniq talabalar haqida bo'lsa — ro'yxatni biriktiring (ijrochi har biri bo'yicha belgilaydi)</span>`}
      <button type="button" class="btn sm${n ? " ghost" : ""}" id="ptStuT" aria-expanded="${!!PT.stuOpen}" aria-controls="ptStuP">${ico(PT.stuOpen ? "chev" : "plus", 15)}${PT.stuOpen ? "Yig'ish" : n ? "O'zgartirish" : "Ro'yxat biriktirish"}</button>`;
    $("#ptStuT").onclick = () => { PT.stuOpen = !PT.stuOpen; $("#ptStuP").hidden = !PT.stuOpen; if (PT.stuOpen && !$("#ptStuP").innerHTML) mount(); head(); };
    const nt = $("#ptStuNt");
    if (n && !$("#ptStuNote")) { nt.innerHTML = `<label class="pt-af-l pt-stu-note">Ro'yxat bo'yicha izoh<input id="ptStuNote" maxlength="300" placeholder="Masalan: yangi guruhga ko'chirish"></label>`; $("#ptStuNote").value = PT.stuNote; $("#ptStuNote").oninput = e => { PT.stuNote = e.target.value; }; }
    if (!n) nt.innerHTML = "";
  };
  const mount = () => ptStuPicker($("#ptStuP"), PT.stu, () => { head(); ptDraftSched(); });
  if (PT.stuOpen) mount();
  head();
}
/* talaba tanlagich: qidiruv (ism, HEMIS, guruh), butun guruh, HEMIS ID ro'yxati; map — tanlanganlar (id → talaba) */
function ptStuPicker(host, map, onChange, exclude = []) {
  const ex = new Set(exclude);
  host.innerHTML = `<div class="pt-sp">
    <div class="pt-sp-tools"><label class="pt-search sm">${ico("search", 15)}<input type="search" data-sq placeholder="F.I.Sh., HEMIS ID yoki guruh (IQT-2501)" aria-label="Talaba qidirish"></label>
      <button type="button" class="btn sm ghost" data-sh aria-expanded="false">${ico("list", 15)}HEMIS ID ro'yxati</button></div>
    <div class="pt-sp-hemis" hidden><textarea rows="3" data-shx placeholder="HEMIS ID larni qo'ying — har qatorda bittadan yoki bo'sh joy, vergul bilan"></textarea>
      <div class="pt-sp-hf"><span class="muted tiny" data-shm></span><button type="button" class="btn sm" data-shgo>${ico("check", 14)}Ro'yxatdan qo'shish</button></div></div>
    <div class="pt-sp-res" data-sr><p class="muted tiny pt-sp-hint">Kamida 2 ta belgi yozing. Guruh nomini yozsangiz — butun guruhni bir bosishda qo'shish mumkin.</p></div>
    <div class="pt-sp-sel"><div class="pt-sp-selh"><b data-sn></b><button type="button" class="pt-q" data-sclr>Tozalash</button></div><div class="pt-sp-chips" data-sc></div></div>
  </div>`;
  const $$ = q => host.querySelector(q);
  let exp = false;
  const add = items => { let n = 0; items.forEach(x => { if (!ex.has(x.id) && !map.has(x.id)) { map.set(x.id, x); n++; } }); return n; };
  const chips = () => {
    const L = [...map.values()], cut = exp ? L.length : 24;
    $$("[data-sn]").textContent = L.length ? `Tanlangan: ${L.length} ta talaba` : "Hali talaba tanlanmagan";
    $$("[data-sclr]").hidden = !L.length;
    $$("[data-sc]").innerHTML = L.slice(0, cut).map(x => `<span class="pt-chip">${esc(x.name.split(" ").slice(0, 2).join(" "))}<small>${esc(x.group || "")}</small><button type="button" data-rm="${x.id}" aria-label="Olib tashlash">${ico("x", 12)}</button></span>`).join("")
      + (L.length > cut ? `<button type="button" class="pt-chip more" data-exp>+${L.length - cut}</button>` : exp && L.length > 24 ? `<button type="button" class="pt-chip more" data-exp>Yig'ish</button>` : "");
    host.querySelectorAll("[data-rm]").forEach(b => b.onclick = () => { map.delete(+b.dataset.rm); chips(); marks(); onChange(); });
    const e = $$("[data-exp]"); if (e) e.onclick = () => { exp = !exp; chips(); };
  };
  const marks = () => host.querySelectorAll("[data-ss]").forEach(b => { const on = map.has(+b.dataset.ss); b.classList.toggle("on", on); b.setAttribute("aria-pressed", on); });
  let last = {items: [], groups: []};
  const results = r => {
    last = r;
    $$("[data-sr]").innerHTML = (r.groups || []).map(g => `<button type="button" class="pt-sp-g" data-sg="${g.id}">${ico("users", 15)}<span><b>Butun guruh: ${esc(g.name)}</b><small>${g.course}-kurs · ${g.n} ta talaba</small></span>${ico("plus", 15)}</button>`).join("")
      + ((r.items || []).length ? r.items.map(x => `<button type="button" class="pt-sp-o${ex.has(x.id) ? " in" : ""}" data-ss="${x.id}" aria-pressed="false" ${ex.has(x.id) ? "disabled" : ""}><span class="pt-sp-ck">${ico("check", 13)}</span><span><b>${esc(x.name)}</b><small>${esc(x.hemis)} · ${esc(x.group || "")}${x.status !== "faol" ? ` · ${esc(x.status)}` : ""}${ex.has(x.id) ? " · ro'yxatda bor" : ""}</small></span></button>`).join("")
        : (r.groups || []).length ? "" : `<p class="muted tiny pt-sp-hint">Ko'lamingizda topilmadi.</p>`);
    host.querySelectorAll("[data-ss]").forEach(b => b.onclick = () => { const id = +b.dataset.ss, x = last.items.find(i => i.id === id); map.has(id) ? map.delete(id) : add([x]); chips(); marks(); onChange(); });
    host.querySelectorAll("[data-sg]").forEach(b => b.onclick = () => busy(b, async () => {
      const g = await J(`/api/portal/students?group_id=${b.dataset.sg}`), n = add(g.items); chips(); marks(); onChange(); toast(`${n} ta talaba qo'shildi`);
    }, "…"));
    marks();
  };
  const q = $$("[data-sq]"); let t;
  q.oninput = () => { clearTimeout(t); t = setTimeout(async () => { const v = q.value.trim(); if (v.length < 2) { $$("[data-sr]").innerHTML = `<p class="muted tiny pt-sp-hint">Kamida 2 ta belgi yozing.</p>`; return; }
    try { const r = await J(`/api/portal/students?q=${encodeURIComponent(v)}`); if (q.value.trim() === v) results(r); } catch (e) {} }, 250); };
  q.onkeydown = e => { if (e.key === "Enter") e.preventDefault(); };
  const hb = $$("[data-sh]"); hb.onclick = () => { const h = $$(".pt-sp-hemis"); h.hidden = !h.hidden; hb.setAttribute("aria-expanded", !h.hidden); if (!h.hidden) $$("[data-shx]").focus(); };
  $$("[data-shgo]").onclick = () => busy($$("[data-shgo]"), async () => {
    const txt = $$("[data-shx]").value; if (!/\d{6,}/.test(txt)) return toast("HEMIS ID topilmadi");
    const r = await J("/api/portal/students/lookup", {method: "POST", body: JSON.stringify({hemis: txt})}), n = add(r.items);
    $$("[data-shm]").innerHTML = `Qo'shildi: <b>${n}</b>${r.missing.length ? ` · <span class="bad">topilmadi yoki ko'lamingizda emas: ${r.missing.length}</span> (${esc(r.missing.slice(0, 5).join(", "))}${r.missing.length > 5 ? " …" : ""})` : ""}`;
    chips(); marks(); onChange();
  }, "…");
  $$("[data-sclr]").onclick = () => { map.clear(); chips(); marks(); onChange(); };
  chips();
  setTimeout(() => q.focus({preventScroll: true}), 30);
}

/* =====================================================================
   2) Fayllar
   ===================================================================== */
async function ptFiles() {
  const qs = new URLSearchParams({q: PT.fq, unit: PT.funit, cat: PT.fcat, scope: PT.fscope});
  const d = await J(`/api/portal/files?${qs}`); PT.files = d;
  const side = `<aside class="card pt-fside">
      <div class="pt-fs-h">Ko'rinish</div>
      ${PT_FSCOPE.map(([k, l, i]) => `<button class="pt-fs${PT.fscope === k && !PT.funit ? " on" : ""}" data-fs="${k}">${ico(i, 16)}<span>${l}</span><em>${d.scopes[k]}</em></button>`).join("")}
      <div class="pt-fs-h">Bo'limlar papkalari</div>
      <div class="pt-fs-units">${d.units.map(u => `<button class="pt-fs${PT.funit === u.key ? " on" : ""}" data-fu="${u.key}" title="${esc(u.name)}">${ico("folder", 16)}<span>${esc(ptShortUnit(u.name))}</span><em>${u.n}</em></button>`).join("") || `<span class="muted tiny">Papkalar yo'q</span>`}</div>
      <select class="pt-fs-sel" id="ptFsSel" aria-label="Papka">${PT_FSCOPE.map(([k, l]) => `<option value="s:${k}" ${PT.fscope === k && !PT.funit ? "selected" : ""}>${l} (${d.scopes[k]})</option>`).join("")}
        <optgroup label="Bo'limlar papkalari">${d.units.map(u => `<option value="u:${u.key}" ${PT.funit === u.key ? "selected" : ""}>${esc(u.name)} (${u.n})</option>`).join("")}</optgroup></select>
      <p class="pt-fs-note">${ico("shield", 14)}<span>${d.leader ? "Rahbariyat sifatida barcha bo'limlar fayllari ko'rinadi." : "Siz o'z bo'limingiz, o'zingiz yuklagan va sizga ulashilgan fayllarni ko'rasiz."} Har bir yuklash va yuklab olish audit jurnalida.</span></p>
    </aside>`;
  const head = PT.funit ? (d.units.find(u => u.key === PT.funit)?.name || "") : PT_FSCOPE.find(x => x[0] === PT.fscope)[1];
  const rows = d.items.map(f => `<div class="pt-fr" data-f="${f.id}">
      ${ptExt(f.ext)}
      <div class="pt-fr-n"><b title="${esc(f.name)}">${ptWbr(f.name)}</b><span>${f.note ? esc(f.note) + " · " : ""}${esc(f.category)}</span></div>
      <div class="pt-fr-o"><b>${esc(ptShortUnit(f.owner_unit_name))}</b><span>${esc(f.uploader)}</span></div>
      <div class="pt-fr-s">${f.public ? `<span class="pt-sh all" title="Barcha bo'limlarga ochiq">${ico("users", 13)}Hamma</span>`
        : f.shares.length ? `<span class="pt-sh" title="${esc(f.shares.map(s => s.name).join(", "))}">${ico("users", 13)}${f.shares.length === 1 ? esc(ptShortUnit(f.shares[0].name)) : `${f.shares.length} bo'lim`}</span>`
        : `<span class="pt-sh priv" title="Faqat o'z bo'limi va rahbariyat">${ico("lock", 13)}Ichki</span>`}</div>
      <div class="pt-fr-d"><span title="${ptFull(f.created_at)}">${ptTime(f.created_at)}</span><span>${ptSize(f.size)}${f.versions > 1 ? ` · <button class="pt-ver" data-v="${f.id}">v${f.version}</button>` : ""}</span></div>
      <div class="pt-fr-a"><a class="btn sm pt-dl" href="/api/portal/files/${f.id}/download" download title="Yuklab olish (${f.downloads} marta yuklangan)">${ico("download", 16)}<span>Yuklab olish</span></a>${f.mine || (PT.units?.is_head && f.own_unit) ? `<button class="btn sm ghost pt-fdel" data-fdel="${f.id}" title="Faylni o'chirish" aria-label="Faylni o'chirish">${ico("x", 16)}</button>` : ""}</div>
      <div class="pt-vers" hidden></div>
    </div>`).join("");
  $("#ptBody").innerHTML = `<div class="pt-files">${side}<section class="pt-fmain">
      <div id="ptUpWrap">${PT.upload ? ptUploadForm(d) : ""}</div>
      <div class="card pt-flist">
        <div class="pt-fl-h"><h3>${esc(head)} <span class="muted">${d.items.length}</span></h3>
          <label class="pt-search">${ico("search", 16)}<input id="ptFq" type="search" placeholder="Fayl nomi, bo'lim yoki xodim" value="${esc(PT.fq)}" aria-label="Fayllarni qidirish"></label></div>
        ${d.cats.length ? `<div class="pt-flt pt-cats"><button class="${!PT.fcat ? "on" : ""}" data-fc="">Barchasi</button>${d.cats.map(c => `<button class="${PT.fcat === c.name ? "on" : ""}" data-fc="${esc(c.name)}">${esc(c.name)} <em>${c.n}</em></button>`).join("")}</div>` : ""}
        ${d.items.length ? `<div class="pt-frs">${rows}</div>` : `<div class="pt-empty">${ico(PT.fq ? "search" : "folder", 22)}<b>${PT.fq ? "Hech narsa topilmadi" : "Bu papkada fayl yo'q"}</b><span class="muted">${PT.fq ? "Boshqa so'z bilan qidirib ko'ring." : "Fayl yuklang yoki boshqa papkani tanlang."}</span>${PT.fq ? "" : `<button class="btn" onclick="PT.upload=true;PT.share=new Set();ptFiles()">${ico("upload", 16)}Fayl yuklash</button>`}</div>`}
      </div></section></div>`;
  const b = $("#ptBody");
  b.querySelectorAll("[data-fs]").forEach(x => x.onclick = () => { PT.fscope = x.dataset.fs; PT.funit = ""; PT.fcat = ""; ptFiles(); });
  b.querySelectorAll("[data-fu]").forEach(x => x.onclick = () => { PT.funit = PT.funit === x.dataset.fu ? "" : x.dataset.fu; PT.fscope = "all"; PT.fcat = ""; ptFiles(); });
  $("#ptFsSel").onchange = e => { const [t, v] = e.target.value.split(":"); if (t === "s") { PT.fscope = v; PT.funit = ""; } else { PT.funit = v; PT.fscope = "all"; } PT.fcat = ""; ptFiles(); };
  b.querySelectorAll("[data-fc]").forEach(x => x.onclick = () => { PT.fcat = x.dataset.fc; ptFiles(); });
  const q = $("#ptFq"); let t; q.oninput = () => { clearTimeout(t); t = setTimeout(async () => { PT.fq = q.value.trim(); await ptFiles(); const n = $("#ptFq"); n.focus(); n.setSelectionRange(n.value.length, n.value.length); }, 300); };
  b.querySelectorAll("[data-v]").forEach(x => x.onclick = async () => {
    const box = x.closest(".pt-fr").querySelector(".pt-vers");
    if (!box.hidden) { box.hidden = true; return; }
    const vs = await J(`/api/portal/files/${x.dataset.v}/versions`);
    box.innerHTML = `<b>Versiyalar tarixi</b>` + vs.map(v => `<div><span class="pt-vtag">v${v.version}</span><span>${ptFull(v.created_at)} · ${esc(v.uploader)} · ${ptSize(v.size)}</span><span class="muted">${esc(v.note || "")}</span><a href="/api/portal/files/${v.id}/download" download>${ico("download", 14)}Yuklab olish</a></div>`).join("");
    box.hidden = false;
  });
  b.querySelectorAll("[data-fdel]").forEach(x => x.onclick = () => {
    const f = d.items.find(i => i.id === +x.dataset.fdel); if (!f) return;
    if (!confirm(`«${f.name}» faylini o'chirasizmi?${f.versions > 1 ? ` Barcha ${f.versions} ta versiyasi o'chadi.` : ""} Bu amalni qaytarib bo'lmaydi.`)) return;
    busy(x, async () => { if (await ptPost(`/api/portal/files/${f.id}`, {}, "DELETE")) { toast(`${f.name} o'chirildi`); await ptFiles(); } }, "…");
  });
  if (PT.upload) ptBindUpload();
}
function ptUploadForm(d) {
  return `<form class="card pt-upf" id="ptUpf" onsubmit="event.preventDefault()">
    <div class="pt-upf-h"><h3>${ico("upload", 18)}Fayl yuklash</h3><button type="button" class="btn sm ghost" id="ptUpClose" aria-label="Yopish">${ico("x", 16)}</button></div>
    <label class="pt-drop" id="ptDrop"><input type="file" id="ptUpFile" hidden>
      <span class="pt-drop-ic">${ico("upload", 22)}</span><b id="ptDropTxt">Faylni shu yerga tashlang yoki tanlang</b>
      <small>PDF, Word, Excel, PowerPoint, rasm, ZIP · ${d.max_mb} MB gacha · bir xil nomli fayl yangi versiya bo'lib saqlanadi</small></label>
    <div class="form-grid">
      <label>Papka (toifa)<select id="ptUpCat">${d.categories.map(c => `<option>${esc(c)}</option>`).join("")}</select></label>
      <label>Izoh<input id="ptUpNote" maxlength="300" placeholder="Ixtiyoriy: masalan, 2-versiya, takliflar kiritildi"></label>
    </div>
    <div class="pt-cf-row"><span class="pt-cf-l">Kimga ochiq</span>${ptPicker("ptShare", PT.share, {all: true})}<span class="muted tiny">Hech narsa tanlanmasa — faqat <b>${esc(d.unit_name)}</b> va rahbariyat ko'radi.</span></div>
    <div class="pt-cf-f"><span></span><div class="row-actions"><button type="button" class="btn ghost" id="ptUpCancel">Bekor qilish</button><button class="btn primary" id="ptUpGo" disabled>${ico("upload", 16)}Yuklash</button></div></div>
  </form>`;
}
function ptBindUpload() {
  let file = null;
  const set = f => { file = f; $("#ptDropTxt").textContent = f ? `${f.name} · ${ptSize(f.size)}` : "Faylni shu yerga tashlang yoki tanlang"; $("#ptUpGo").disabled = !f; $("#ptDrop").classList.toggle("has", !!f); };
  const close = () => { PT.upload = false; $("#ptUpWrap").innerHTML = ""; };
  $("#ptUpClose").onclick = close; $("#ptUpCancel").onclick = close;
  $("#ptUpFile").onchange = e => set(e.target.files[0]);
  const dz = $("#ptDrop");
  dz.ondragover = e => { e.preventDefault(); dz.classList.add("over"); };
  dz.ondragleave = () => dz.classList.remove("over");
  dz.ondrop = e => { e.preventDefault(); dz.classList.remove("over"); if (e.dataTransfer.files[0]) set(e.dataTransfer.files[0]); };
  ptBindPicker("ptShare", PT.share);
  $("#ptUpGo").onclick = () => busy($("#ptUpGo"), async () => {
    if (!file) return;
    const r = await ptUpload(file, $("#ptUpCat").value, [...PT.share], $("#ptUpNote").value.trim());
    if (!r) return;
    toast(r.version > 1 ? `${r.name} — ${r.version}-versiya saqlandi` : `${r.name} yuklandi`);
    PT.upload = false; PT.fq = ""; PT.fcat = ""; PT.funit = ""; PT.fscope = "mine"; await ptFiles();
    document.querySelector(`.pt-fr[data-f="${r.id}"]`)?.classList.add("flash");
  }, "Yuklanmoqda…");
  $("#ptUpf").scrollIntoView({block: "nearest"});
}

/* =====================================================================
   3) Umumiy bazalar
   ===================================================================== */
const PT_MODE = {toliq: ["To'liq", "ok"], jamlangan: ["Jamlangan", "mid"], yopiq: ["Yopiq", "lock"]};
async function ptData() {
  if (PT.ds) return ptDataView();
  const d = await J("/api/portal/datasets");
  $("#ptBody").innerHTML = `<div class="pt-dsi">${ico("db", 18)}<span>Bo'limlar o'z ma'lumotlarini boshqalarga ochadi — so'rov yozish va Excel jo'natish shart emas. Ma'lumot mavjud bazadan olinadi va <b>sizning ruxsatingiz doirasida</b> ko'rsatiladi.<br><span class="muted">Manba: ISFT Core bazasi (sinov ma'lumotlari) · kartadagi ${ico("clock", 12)} — egasi bo'lim bazani oxirgi marta yangilagan vaqt.</span></span></div>
    <div class="pt-dsg">${d.items.map(x => `<button class="card pt-ds${x.mode === "yopiq" ? " locked-ds" : ""}" data-ds="${x.key}">
      <div class="pt-ds-top"><span class="pt-ds-ic">${ico(x.mode === "yopiq" ? "lock" : x.icon, 20)}</span><div class="pt-ds-t"><b>${esc(x.title)}</b><span>${esc(x.owner_name)}${x.own ? " · <i>sizning bo'limingiz</i>" : ""}</span></div>
        <span class="pt-mode ${PT_MODE[x.mode][1]}">${PT_MODE[x.mode][0]}</span></div>
      <p>${esc(x.mode === "yopiq" ? x.reason : x.desc)}</p>
      <div class="pt-ds-f">${x.mode === "yopiq" ? `<span>${ico("shield", 13)}${esc(x.access)}</span>` : `<span><b>${fmt(x.rows)}</b> qator</span><span>${ico("clock", 13)}${ptAgo(x.updated_at)}</span><span>${ico("eye", 13)}${x.views}</span>`}</div>
    </button>`).join("")}</div>`;
  $("#ptBody").querySelectorAll("[data-ds]").forEach(b => b.onclick = () => {
    const x = d.items.find(i => i.key === b.dataset.ds);
    if (x.mode === "yopiq") return toast(`${x.title}: ${x.reason}`);
    PT.ds = x.key; PT.dsq = ""; PT.dsoff = 0; ptDataView(); window.scrollTo({top: 0});
  });
}
async function ptDataView() {
  const b = $("#ptBody");
  if (!b.querySelector(".pt-dv")) b.innerHTML = `<p class="muted">Yuklanmoqda…</p>`;
  let d;
  try { d = await J(`/api/portal/datasets/${PT.ds}?q=${encodeURIComponent(PT.dsq)}&offset=${PT.dsoff}`); }
  catch (e) { if (e?.message === "denied") { PT.ds = null; return ptData(); } throw e; }
  const head = d.cols, num = head.map(h => h.startsWith("#"));
  const cell = (v, i) => v == null ? `<span class="muted">—</span>` : num[i] && typeof v === "number" ? (Number.isInteger(v) ? fmt(v) : v.toLocaleString("ru-RU", {maximumFractionDigits: 1})) : esc(v);
  const from = d.total ? d.offset + 1 : 0, to = Math.min(d.offset + d.limit, d.total);
  b.innerHTML = `<div class="pt-dv">
    <button class="btn sm ghost pt-dv-back" id="ptDsBack">${ico("back", 16)}Barcha bazalar</button>
    <div class="card">
      <div class="pt-dv-h"><div><h3>${esc(d.title)} <span class="pt-mode ${PT_MODE[d.mode][1]}">${PT_MODE[d.mode][0]}</span></h3>
        <span class="muted tiny">Egasi: <b>${esc(d.owner_name)}</b> · yangilandi ${ptAgo(d.updated_at)} · ${esc(d.access)}</span></div>
        <a class="btn" href="/api/portal/datasets/${d.key}/csv?q=${encodeURIComponent(PT.dsq)}" download>${ico("download", 16)}CSV yuklab olish</a></div>
      <div class="pt-dv-note ${d.mode}">${ico(d.mode === "toliq" ? "info" : "shield", 16)}<span>${esc(d.note)}</span></div>
      <div class="pt-dv-tools"><label class="pt-search">${ico("search", 16)}<input id="ptDsQ" type="search" placeholder="Qidirish…" value="${esc(PT.dsq)}" aria-label="Bazadan qidirish"></label>
        <span class="muted tiny">${d.total ? `${fmt(from)}–${fmt(to)} / <b>${fmt(d.total)}</b> qator` : "0 qator"}</span></div>
      ${d.total ? tbl(head, d.rows.map(r => r.map(cell))) : `<div class="pt-empty">${ico("search", 22)}<b>Hech narsa topilmadi</b><span class="muted">Boshqa so'z bilan qidirib ko'ring.</span></div>`}
      ${d.total > d.limit ? `<div class="pt-pg"><button class="btn sm" id="ptPrev" ${d.offset ? "" : "disabled"}>${ico("back", 16)}Oldingi</button><span class="muted tiny">${Math.floor(d.offset / d.limit) + 1} / ${Math.ceil(d.total / d.limit)}-sahifa</span><button class="btn sm" id="ptNext" ${to < d.total ? "" : "disabled"}>Keyingi${ico("arrow", 16)}</button></div>` : ""}
    </div></div>`;
  $("#ptDsBack").onclick = () => { PT.ds = null; ptData(); };
  const q = $("#ptDsQ"); let t; q.oninput = () => { clearTimeout(t); t = setTimeout(async () => { PT.dsq = q.value.trim(); PT.dsoff = 0; await ptDataView(); const n = $("#ptDsQ"); n.focus(); n.setSelectionRange(n.value.length, n.value.length); }, 300); };
  if ($("#ptPrev")) { $("#ptPrev").onclick = () => { PT.dsoff = Math.max(0, d.offset - d.limit); ptDataView(); }; $("#ptNext").onclick = () => { PT.dsoff = d.offset + d.limit; ptDataView(); }; }
}

/* =====================================================================
   4) Bo'limlar — tashkiliy tuzilma katalogi
   ===================================================================== */
async function ptOrg() {
  PT.org = await J("/api/portal/org");
  const d = PT.org, G = d.groups;
  $("#ptBody").innerHTML = `<div class="pt-org">
    <div class="pt-org-h"><label class="pt-search">${ico("search", 16)}<input id="ptOq" type="search" placeholder="Bo'lim, rahbar yoki xodim ismi" value="${esc(PT.oq)}" aria-label="Bo'limlarni qidirish"></label>
      <span class="muted tiny">${d.units.length} ta bo'linma · manba: tashkiliy tuzilma (04.09.2024)${d.can_edit ? " · rahbar va kuratorni tahrirlash mumkin" : ""}</span></div>
    <div id="ptOrgL">${G.map(g => { const us = d.units.filter(u => u.group === g.key); return us.length ? `<section class="pt-org-g" data-og="${g.key}">
      <h3 class="pt-org-gh">${esc(g.name)} <span class="muted">${us.length}</span></h3><div class="pt-org-grid">${us.map(ptOrgCard).join("")}</div></section>` : ""; }).join("")}
      <div class="pt-empty" id="ptOrgE" hidden>${ico("search", 22)}<b>Hech narsa topilmadi</b><span class="muted">Boshqa so'z bilan qidirib ko'ring.</span></div></div>
  </div>`;
  const q = $("#ptOq"); q.oninput = () => { PT.oq = q.value; ptOrgFilter(); };
  ptOrgBind(); ptOrgFilter();
}
function ptOrgCard(u) {
  const d = PT.org, lead = u.group === "rahbariyat";
  const cur = lead ? "" : u.curator ? `<span class="pt-org-cur" title="${esc(u.curator_name)}${u.curator_person ? ` — ${esc(u.curator_person)}` : ""}">${ico("flag", 13)}<span>${esc(u.curator_name)}</span>${u.curator_manual ? `<em class="pt-via" title="Tasdiqlangan tuzilmadan farq qiladi (qo'lda tayinlangan)">qo'lda</em>` : ""}</span>`
    : `<span class="pt-org-cur direct">${ico("shield", 13)}<span>Rektorga bevosita</span>${u.curator_manual ? `<em class="pt-via">qo'lda</em>` : ""}</span>`;
  const s = [u.name, u.head, ...(u.members || []).map(m => m.name)].join(" ").toLowerCase();
  const hm = (u.members || []).find(m => m.head);
  return `<article class="card pt-org-c${u.me ? " me" : ""}" data-ou="${esc(u.key)}" data-s="${esc(s)}">
    <div class="pt-org-ct"><span class="pt-av">${esc(ptInit(u.name))}</span><div class="pt-org-n"><b>${esc(u.name)}</b>${u.me ? `<em class="pt-lt">sizning bo'limingiz</em>` : ""}</div></div>
    <div class="pt-org-m">
      <span>${ico("user", 13)}<span>${u.head ? `<b>${esc(u.head)}</b>${hm?.position ? ` · ${esc(hm.position)}` : ""}` : hm ? `<i class="muted">rahbar F.I.Sh. kiritilmagan</i>` : `<i class="muted">rahbar ko'rsatilmagan</i>`}</span></span>
      ${cur}
      ${u.info?.place ? `<span>${ico("pin", 13)}<span>${esc(u.info.place)}</span></span>` : ""}
    </div>
    ${u.info?.does?.length ? `<ul class="pt-org-does">${u.info.does.slice(0, 4).map(x => `<li>${esc(x)}</li>`).join("")}${u.info.does.length > 4 ? `<li class="muted">va yana ${u.info.does.length - 4} ta yo'nalish</li>` : ""}</ul>` : ""}
    <div class="pt-org-f">
      ${u.members_count ? `<details class="pt-org-mem"><summary>${ico("users", 13)}${u.members_count} ta xodim${ico("chev", 13)}</summary><ul>${u.members.map(m => `<li><b>${esc(m.name)}</b>${m.position ? `<small>${esc(m.position)}</small>` : ""}${m.head ? `<em class="pt-lt">rahbar</em>` : ""}</li>`).join("")}</ul></details>` : `<span class="muted tiny pt-org-nom">${ico("users", 13)}Tizimda akkaunt yo'q</span>`}
      <div class="pt-org-a">${d.can_edit ? `<button class="btn sm ghost" data-oedit="${esc(u.key)}" aria-label="${esc(u.name)}: rahbar va kuratorni tahrirlash">${ico("pen", 14)}Tahrirlash</button>` : ""}${u.me ? "" : `<button class="btn sm" data-owrite="${esc(u.key)}">${ico("pen", 14)}Xat yozish</button>`}</div>
    </div>
    ${PT.oedit === u.key ? ptOrgForm(u) : ""}
  </article>`;
}
function ptOrgForm(u) {
  const d = PT.org, lead = u.group === "rahbariyat";
  return `<div class="pt-org-ef">
    <label class="pt-af-l">Bo'lim rahbari<select id="ptOeHead" ${u.members_count ? "" : "disabled"}>${u.members_count ? u.members.map(m => `<option value="${m.id}" ${m.id === u.head_user ? "selected" : ""}>${esc(m.name)}${m.position ? ` — ${esc(m.position)}` : ""}</option>`).join("") : `<option>Bo'limda akkaunt yo'q</option>`}</select></label>
    ${lead ? "" : `<label class="pt-af-l">Kurator<select id="ptOeCur"><option value="">Rektorga bevosita</option>${d.curators.map(c => `<option value="${c.key}" ${c.key === u.curator ? "selected" : ""}>${esc(c.name)}${c.person ? ` — ${esc(c.person)}` : ""}</option>`).join("")}</select></label>
      <span class="muted tiny">Tasdiqlangan tuzilma bo'yicha: <b>${esc(d.curators.find(c => c.key === u.curator_default)?.name || "Rektorga bevosita")}</b>. Qo'lda tanlangan kurator server qayta ishga tushganda ham saqlanadi.</span>`}
    <div class="pt-af-f"><span></span><div class="row-actions"><button type="button" class="btn sm ghost" data-oeno>Bekor qilish</button><button type="button" class="btn sm primary" data-oego="${esc(u.key)}">${ico("check", 15)}Saqlash</button></div></div>
  </div>`;
}
function ptOrgFilter() {
  const v = (PT.oq || "").trim().toLowerCase(); let any = false;
  document.querySelectorAll("#ptOrgL .pt-org-g").forEach(g => { let n = 0;
    g.querySelectorAll(".pt-org-c").forEach(c => { const on = !v || c.dataset.s.includes(v); c.hidden = !on; if (on) n++; });
    g.hidden = !n; any = any || !!n; });
  const e = $("#ptOrgE"); if (e) e.hidden = any;
}
function ptOrgBind() {
  const b = $("#ptOrgL"); if (!b) return;
  b.querySelectorAll("[data-owrite]").forEach(x => x.onclick = () => { ptNew(); PT.to = new Set([x.dataset.owrite]); PT.box = PT.box === "drafts" ? "inbox" : PT.box; ptSetTab("mail"); window.scrollTo({top: 0}); });
  const redraw = key => { const u = PT.org.units.find(z => z.key === key), el = b.querySelector(`[data-ou="${CSS.escape(key)}"]`); if (u && el) { el.outerHTML = ptOrgCard(u); ptOrgBind(); } };
  b.querySelectorAll("[data-oedit]").forEach(x => x.onclick = () => { const prev = PT.oedit; PT.oedit = prev === x.dataset.oedit ? null : x.dataset.oedit; if (prev && prev !== PT.oedit) redraw(prev); redraw(x.dataset.oedit);
    if (PT.oedit) b.querySelector(".pt-org-ef select")?.focus(); });
  b.querySelectorAll("[data-oeno]").forEach(x => x.onclick = () => { const k = PT.oedit; PT.oedit = null; redraw(k); });
  b.querySelectorAll("[data-oego]").forEach(x => x.onclick = () => busy(x, async () => {
    const key = x.dataset.oego, u = PT.org.units.find(z => z.key === key), body = {};
    const h = $("#ptOeHead"), c = $("#ptOeCur");
    if (h && !h.disabled && +h.value !== u.head_user) body.head_user = +h.value;
    if (c && (c.value || null) !== (u.curator || null)) body.curator = c.value || null;
    if (!Object.keys(body).length) { PT.oedit = null; redraw(key); return toast("O'zgarish yo'q"); }
    const r = await ptPost(`/api/portal/org/${encodeURIComponent(key)}`, body, "PUT"); if (!r) return;
    PT.oedit = null; PT.units = await J("/api/portal/units");
    toast(`${u.name}: ${r.changes.join("; ") || "saqlandi"}`); await ptOrg();
  }, "…"));
}

/* ---------- boshqaruv paneli: amallar qatoriga "Portal xatlari" (faqat rahbariyat) ---------- */
if (typeof renderPanel === "function") {
  const _ptPanel = renderPanel;
  renderPanel = async function () {
    const r = await _ptPanel.apply(this, arguments);
    try {
      if (!ME || ME.level > 2) return r;
      const s = await J("/api/portal/summary"); PT.sum = s;
      if (!s.unread && !s.all_overdue) return r;
      const html = `<button class="pn-act${s.all_overdue ? " bad" : ""} pt-pnact" onclick="PT.tab='mail';PT.box='inbox';PT.flt='all';PT.open=null;go('portal')">${ico("portal", 16)}<span>Yozishmalar: yangi xatlar</span><b>${s.unread}</b>${s.all_overdue ? `<em>${s.all_overdue} ta javobsiz, muddati o'tgan</em>` : ""}</button>`;
      const v = $("#v-panel"); if (v.querySelector(".pt-pnact")) return r;
      const acts = v.querySelector(".pn-acts");
      if (acts) acts.insertAdjacentHTML("beforeend", html);
      else (v.querySelector(".pn-kmore") || v.querySelector(".pn-kpis"))?.insertAdjacentHTML("afterend", `<div class="pn-acts">${html}</div>`);
    } catch (e) {}
    return r;
  };
}
