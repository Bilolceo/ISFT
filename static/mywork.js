/* =====================================================================
   «Mening vazifalarim» — xodim shaxsan bajarishi kerak bo'lgan hamma ish bitta ro'yxatda (app/mywork.py, GET /api/mywork):
     majlis topshiriqlari, portal xatlari va rezolyutsiyalari, Talabalar markazi navbati, imzo kutayotgan hujjatlar, AI agent takliflari.
   Global: renderMywork(), myworkBadge(set) — app.js badges() chaqiradi (portalBadge bilan bir xil naqsh).
   Havola ochish — extras.js XT.openLink (bildirishnomalar markazi bilan bir xil); Talabalar markazi navbati uchun avval OPSV tab/turi qo'yiladi.
   app.js yordamchilaridan foydalanadi: $, J, esc, ico, ICONS, go, dmy, fmt, ME, hydrateIcons, errCard.
   Uslublar: mywork.css (shu fayldan ulanadi; faqat umumiy tokenlar — qorong'i rejim avtomatik).
   ===================================================================== */
const MW = {flt: "all", data: null, busy: false};
if (!document.querySelector('link[href="mywork.css"]')) document.head.insertAdjacentHTML("beforeend", '<link rel="stylesheet" href="mywork.css">');
if (typeof ICONS === "object") {
  Object.assign(ICONS, Object.fromEntries(Object.entries({
    mywork: '<rect x="3" y="4" width="18" height="17" rx="3"/><path d="M8 2v4M16 2v4"/><path d="m8.5 13.5 2.5 2.5 4.5-5"/>',
    inbox: '<path d="M22 12h-6l-2 3h-4l-2-3H2"/><path d="M5.45 5.11 2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.45-6.89A2 2 0 0 0 16.76 4H7.24a2 2 0 0 0-1.79 1.11z"/>',
    pen: '<path d="M12 20h9"/><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4z"/>',
    chevR: '<path d="m9 18 6-6-6-6"/>',
  }).filter(([k]) => !ICONS[k])));
  /* app.js menyu ikonkalarini bu fayl yuklanishidan oldin chizgan — bo'sh qolgan ikonka qayta chiziladi */
  try { const s = document.querySelector('#nav a[data-v="mywork"] svg'); if (s && !s.innerHTML.trim()) { s.remove(); hydrateIcons(); } } catch (e) {}
}

const MW_SRC = {
  majlis: {label: "Majlis", icon: "tasks"},
  portal: {label: "Portal", icon: "mail"},
  markaz: {label: "Markaz", icon: "users", long: "Talabalar markazi"},
  buyruq: {label: "Buyruqlar", icon: "file"},
  murojaat: {label: "Murojaatlar", icon: "mail", long: "Murojaatlar va nosozliklar"},
  xodim: {label: "Xodimlar ta'tili", icon: "users"},
  agent: {label: "AI agentlar", icon: "spark"},
  sillabus: {label: "O'quv dasturlari", icon: "book"},
};
const MW_GROUPS = [
  ["overdue", "Muddati o'tgan", "alert"],
  ["today", "Bugun", "clock"],
  ["week", "Shu hafta", "calendar", "keyingi 7 kun"],
  ["later", "Keyinroq", "calendar"],
  ["none", "Muddatsiz", "list"],
];
const MW_WHO = {menga: "Sizga", bolimga: "Bo'limga", nazorat: "Nazoratda", yuborgan: "Javob kutilmoqda"};

/* muddat yorlig'i: "3 kun o'tdi" · "Bugun 17:25" · "Ertaga" · "12.11 · Pa" */
const MW_WD = ["Ya", "Du", "Se", "Ch", "Pa", "Ju", "Sh"];
function mwDue(it) {
  if (!it.due) return "";
  const s = String(it.due), tm = s.length > 10 ? s.slice(11, 16) : "", d = new Date(s.slice(0, 10) + "T00:00:00"), n = it.days;
  if (it.overdue) return n < 0 ? `${-n} kun o'tdi` : `Muddati o'tdi${tm ? " · " + tm : ""}`;
  if (n === 0) return `Bugun${tm ? " " + tm : ""}`;
  if (n === 1) return `Ertaga${tm ? " " + tm : ""}`;
  return `${String(d.getDate()).padStart(2, "0")}.${String(d.getMonth() + 1).padStart(2, "0")} · ${MW_WD[d.getDay()]}`;
}

function mwOpen(link) {
  if (!link || !link.view) return;
  /* Talabalar markazi: o'z navbatim, kerakli tur bilan (XT.openLink faqat talaba kartasini biladi) */
  if (link.view === "ops" && link.tab && typeof OPSV !== "undefined") { OPSV.tab = link.tab; OPSV.kind = link.kind || ""; OPSV.rule = ""; OPSV.level = 0; OPSV.page = 30; }
  if (typeof XT !== "undefined" && XT.openLink) XT.openLink(link); else go(link.view);
}

function mwRow(it, i) {
  const src = MW_SRC[it.source] || {label: it.source, icon: "list"};
  const due = mwDue(it);
  const dueCls = it.overdue ? "bad" : it.bucket === "today" ? "warn" : "";
  const meta = [MW_WHO[it.who] || ""].filter(Boolean);
  return `<li><a href="#" class="mw-row pr-${esc(it.priority)}${it.overdue ? " mw-over" : ""}" data-i="${i}">
    <span class="mw-ic s-${esc(it.source)}">${ico(it.icon || src.icon, 17)}</span>
    <span class="mw-b"><b>${esc(it.title)}</b>${it.sub ? `<small>${esc(it.sub)}</small>` : ""}
      <span class="mw-meta"><span class="mw-src s-${esc(it.source)}">${esc(src.label)}</span>${meta.map(m => `<span class="mw-who">${esc(m)}</span>`).join("")}${it.count > 1 ? `<span class="mw-cnt">${fmt(it.count)} ta</span>` : ""}</span></span>
    <span class="mw-r">${due ? `<span class="mw-due ${dueCls}">${it.overdue ? ico("alert", 13) : ico("clock", 13)}${esc(due)}</span>` : `<span class="mw-due none">muddatsiz</span>`}${ico("chevR", 16)}</span>
  </a></li>`;
}

function mwBody() {
  const d = MW.data, items = d.items.filter(it => MW.flt === "all" || it.source === MW.flt);
  if (!d.items.length) return `<div class="card mw-empty">${ico("checkc", 30)}<b>Hammasi joyida</b><span class="muted">Hozircha sizdan kutilayotgan ish yo'q: majlis topshiriqlari, portal xatlari, imzo va tasdiqlar — barchasi bajarilgan.</span>
      <div class="mw-empty-acts"><button class="btn sm" type="button" data-go="tasks">${ico("tasks", 15)} Majlislar</button><button class="btn sm" type="button" data-go="portal">${ico("mail", 15)} Portal</button></div></div>`;
  if (!items.length) return `<div class="card mw-empty">${ico("checkc", 26)}<b>Bu manbada ish yo'q</b><span class="muted">Boshqa manbalarni ko'rish uchun «Hammasi»ni tanlang.</span></div>`;
  const idx = new Map(d.items.map((it, i) => [it, i]));
  return MW_GROUPS.map(([k, title, icon, hint]) => {
    const g = items.filter(it => it.bucket === k);
    if (!g.length) return "";
    return `<section class="mw-grp g-${k}" aria-label="${esc(title)}"><h3 class="mw-gh">${ico(icon, 16)}<span>${esc(title)}</span><em>${g.length}</em>${hint ? `<span class="muted tiny">${esc(hint)}</span>` : ""}</h3>
      <ul class="mw-list">${g.map(it => mwRow(it, idx.get(it))).join("")}</ul></section>`;
  }).join("");
}

function mwDraw() {
  const el = $("#v-mywork"), d = MW.data, c = d.counts;
  const srcs = Object.keys(MW_SRC).filter(s => c.by_source[s]);
  if (MW.flt !== "all" && !srcs.includes(MW.flt)) MW.flt = "all";
  const tile = (k, label, n, cls, icon) => `<div class="mw-st ${cls}${n ? "" : " zero"}"><span class="mw-st-ic">${ico(icon, 16)}</span><b>${fmt(n)}</b><span>${label}</span></div>`;
  const who = (typeof ME !== "undefined" && ME) ? [ME.role, ME.scope && ME.scope !== "Butun institut" ? ME.scope : ""].filter(Boolean).join(" · ") : "";
  el.innerHTML = `<div class="head"><div><h2>Mening vazifalarim</h2><span class="muted">Sizdan kutilayotgan hamma ish bitta joyda: topshiriqlar, portal xatlari va rezolyutsiyalar, Talabalar markazi navbati, buyruqlar (imzo, kelishuv, qaytarilgan), murojaatlar, xodimlar ta'tili, o'quv dasturlari va AI takliflari.${who ? ` <b class="mw-whoami">${esc(who)}</b>` : ""}</span></div>
      <div class="row-actions"><button class="btn sm" type="button" id="mwRefresh">${ico("refresh", 15)} Yangilash</button></div></div>
    <div class="mw-stats">${tile("overdue", "Muddati o'tgan", c.overdue, "bad", "alert")}${tile("today", "Bugun", c.today, "warn", "clock")}${tile("week", "Shu hafta", c.week, "", "calendar")}${tile("total", "Jami ish", c.total, "tot", "list")}</div>
    ${srcs.length > 1 ? `<div class="pn-tabs mw-tabs" role="tablist" aria-label="Manba bo'yicha saralash">
      <button type="button" role="tab" class="pn-tab${MW.flt === "all" ? " on" : ""}" aria-selected="${MW.flt === "all"}" data-f="all">Hammasi <em>${c.total}</em></button>
      ${srcs.map(s => `<button type="button" role="tab" class="pn-tab${MW.flt === s ? " on" : ""}" aria-selected="${MW.flt === s}" data-f="${s}">${ico(MW_SRC[s].icon, 15)}${esc(MW_SRC[s].label)} <em>${c.by_source[s]}</em></button>`).join("")}</div>` : ""}
    ${d.partial && d.partial.length ? `<div class="src-note" style="margin-bottom:12px">${ico("info", 15)}<span>Ayrim manbalarni yuklab bo'lmadi: ${esc(d.partial.map(s => (MW_SRC[s] || {}).label || s).join(", "))}. Keyinroq yangilang.</span></div>` : ""}
    <div id="mwBody">${mwBody()}</div>`;
  hydrateIcons(el);
  el.querySelectorAll("[data-f]").forEach(b => b.onclick = () => { MW.flt = b.dataset.f; try { localStorage.setItem("isft.mwFlt", MW.flt); } catch (e) {} mwDraw(); });
  el.querySelectorAll("[data-go]").forEach(b => b.onclick = () => go(b.dataset.go));
  el.querySelectorAll(".mw-row").forEach(a => a.onclick = e => { e.preventDefault(); mwOpen(MW.data.items[+a.dataset.i]?.link); });
  const rb = $("#mwRefresh"); if (rb) rb.onclick = () => busy(rb, async () => { await renderMywork(); if (typeof badges === "function") badges(); });
}

async function renderMywork() {
  const el = $("#v-mywork");
  try { MW.flt = localStorage.getItem("isft.mwFlt") || "all"; } catch (e) {}
  if (!MW.data) el.innerHTML = `<p class="muted">Yuklanmoqda…</p>`;
  MW.data = await J("/api/mywork");
  mwDraw();
}

/* menyudagi raqam = sahifadagi «Jami ish» (yagona qoida: sizdan harakat kutayotgan ishlar); izohda — kechikkan va bugungilar */
async function myworkBadge(set) {
  try {
    const d = await J("/api/mywork"), c = d.counts; MW.data = d;
    set("mywork", c.badge ?? c.total, `Sizdan kutilayotgan ishlar: ${c.total} ta` + (c.overdue || c.today ? ` (kechikkan ${c.overdue}, bugun ${c.today})` : ""));
  } catch (e) {}
}
