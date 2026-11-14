/* =====================================================================
   «Dars tayyorlash» (app/paket.py, /api/paket) — NEXTID.LMS uchun dars fayli (Articulate Rise o'rniga): o'qituvchi fayllarni tashlaydi,
   «Tayyorlash»ni bosadi, ko'radi va .zip yuklab oladi.
     Darslar(im):  bitta ekran — dars ro'yxati (haqiqiy nomlar, sodda holat), BITTA yuklash maydoni (fayl turi o'zi aniqlanadi), to'rtta holat
                   kartasi (Matn, Taqdimot, Video, Test va mashqlar), «Mashq va test qo'shish», bitta «Tayyorlash» tugmasi, natija (Ko'rish,
                   Yuklab olish, bo'lim tasdig'i), qolgan hammasi — «Kengaytirilgan sozlamalar» ichida. Bo'lim: ko'rib chiqish navbati yuqorida.
     Holat:        kafedra / o'qituvchi / kurs kesimida — tayyorlangan va tasdiqlangan darslar (bo'lim, kafedra, rahbariyat).
     Ommaviy:      YouTube havolalar ro'yxati → L1..Ln; «Hammasini tayyorlash» (bo'lim).
     Sozlamalar:   standart sozlamalar, kafedra shabloni, NEXTID / boshqa LMS yo'riqnomasi (bo'lim).
   Ruxsat va ko'lam serverda. Global: renderPaket().  app.js yordamchilari: $, esc, fmt, toast, locked, errCard, showLogin, ico, ME.
   Texnik atamalar (SCORM, xAPI …) faqat «Kengaytirilgan sozlamalar» va «Sozlamalar»da; tafsilot — docs/paket.md.
   ===================================================================== */
const PK = {meta: null, tab: null, cid: 0, topic: 1, cov: {q: "", department_id: 0, only: "", offset: 0}, ups: null, adv: false, prac: false};
/* boshqa foydalanuvchi kirsa (sahifa qayta yuklanmasdan) — oldingisining rol/yorliq/kurs/filtrlari qolmasin (testbank.js tbReset bilan bir xil) */
function pkReset() { Object.assign(PK, {meta: null, who: null, tab: null, cid: 0, topic: 1, cov: {q: "", department_id: 0, only: "", offset: 0}, ups: null, adv: false, prac: false}); }
if (typeof ICONS === "object") {
  if (!ICONS.upload) ICONS.upload = '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><path d="m17 8-5-5-5 5"/><path d="M12 3v12"/>';
  if (!ICONS.download) ICONS.download = '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><path d="m7 10 5 5 5-5"/><path d="M12 15V3"/>';
  if (!ICONS.package) ICONS.package = '<path d="M11 21.73a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73z"/><path d="M12 22V12"/><path d="m3.3 7 8.7 5 8.7-5"/><path d="m7.5 4.27 9 5.15"/>';
  if (!ICONS.plus) ICONS.plus = '<path d="M12 5v14M5 12h14"/>';
  if (!ICONS.slides) ICONS.slides = '<rect x="3" y="4" width="18" height="12" rx="2"/><path d="M12 16v4M8 20h8"/>';
  if (!ICONS.video) ICONS.video = '<rect x="3" y="5" width="13" height="14" rx="2"/><path d="m16 10 5-3v10l-5-3z"/>';
  if (!ICONS.trash) ICONS.trash = '<path d="M4 7h16M10 11v6M14 11v6M6 7l1 12a2 2 0 0 0 2 2h6a2 2 0 0 0 2-2l1-12M9 7V4h6v3"/>';
}
if (!document.querySelector('link[href="paket.css"]')) document.head.insertAdjacentHTML("beforeend", '<link rel="stylesheet" href="paket.css">');

const PK_TABS = {fanlar: "Fanlar", qamrov: "Holat", mavzular: "Darslar", joylash: "Ommaviy", sozlama: "Sozlamalar"};
const PK_ST = {qoralama: ["Bo'limga yuborilmagan", ""], tayyor: ["Tasdiq kutilmoqda", "info"], tasdiqlandi: ["Tasdiqlangan", "ok"]};
const PK_LS = {bosh: "", tayyorlanmoqda: "warn", kutilmoqda: "info", tasdiqlangan: "ok"};      /* darsning sodda holati → rang */
const PK_NAMES = {text: "Matn", slides: "Taqdimot", video: "Video", quiz: "Test"};
/* paket turi: o'qituvchiga oddiy so'zlar bilan (texnik nomi — qavsda, faqat «Kengaytirilgan sozlamalar»da ko'rinadi) */
const PK_MODE = {xapi: "NEXTID uchun (standart)", scorm12: "Boshqa LMS uchun (SCORM 1.2)", scorm2004: "Boshqa LMS uchun (SCORM 2004)", none: "LMS'siz — oddiy veb-sahifa"};
const pkMode = m => PK_MODE[m] || m;
const pkChip = (t, cls = "") => `<span class="pk-chip ${cls}">${esc(t)}</span>`;
const pkSt = s => pkChip((PK_ST[s] || [s])[0], (PK_ST[s] || [])[1] || "");
const pkPct = v => v == null ? "—" : `${String(v).replace(".", ",")}%`;
const pkBar = (pct, cls = "") => `<div class="pk-bar ${cls}" role="img" aria-label="${pkPct(pct)}"><i style="width:${Math.max(0, Math.min(100, pct || 0))}%"></i></div>`;
const pkTone = p => p == null ? "" : p >= 80 ? "ok" : p >= 40 ? "warn" : "bad";
const pkD = s => { s = String(s || ""); return s.length >= 10 ? `${s.slice(8, 10)}.${s.slice(5, 7)}.${s.slice(0, 4)}${s.length >= 16 ? " " + s.slice(11, 16) : ""}` : "—"; };
const pkKpi = (label, val, sub = "", cls = "") => `<div class="pk-kpi ${cls}"><span>${esc(label)}</span><b>${val}</b>${sub ? `<small>${sub}</small>` : ""}</div>`;
const pkSize = b => b >= 1048576 ? `${(b / 1048576).toFixed(1).replace(".", ",")} MB` : `${Math.max(1, Math.round((b || 0) / 1024))} KB`;
const pkErrMsg = d => { const det = d && d.detail; return (d && d.message) || (typeof det === "string" ? det : Array.isArray(det) ? "Maydonlarni tekshiring" : det?.message) || "Xatolik yuz berdi"; };

async function pkApi(url, body, method) {
  const r = await fetch(url, {method: method || (body === undefined ? "GET" : "POST"), credentials: "same-origin",
                              headers: body instanceof Blob ? {} : {"Content-Type": "application/json"},
                              body: body === undefined ? undefined : body instanceof Blob ? body : JSON.stringify(body)});
  if (r.status === 401) { showLogin(); throw new Error("auth"); }
  const d = await r.json().catch(() => ({}));
  if (!r.ok) {
    const m = pkErrMsg(d);
    if (body !== undefined) { toast(m); return null; }
    const e = new Error(r.status === 403 ? "denied" : "api"); e.msg = m; throw e;
  }
  return d;
}
function pkTable(cols, rows, {empty = "Ma'lumot yo'q"} = {}) {
  if (!rows.length) return `<div class="pk-empty">${esc(empty)}</div>`;
  return `<div class="tw"><table class="pk-t"><thead><tr>${cols.map(c => `<th class="${c[2] || ""}">${esc(c[0])}</th>`).join("")}</tr></thead><tbody>` +
    rows.map(r => `<tr>${cols.map(c => `<td data-l="${esc(c[0])}" class="${c[2] || ""}"><div>${c[1](r) ?? ""}</div></td>`).join("")}</tr>`).join("") +
    `</tbody></table></div>`;
}
function pkModal(title, html, onOk, okText = "Saqlash", wide = false, onClose = null) {
  const bg = document.createElement("div"); bg.className = "pk-modal-bg";
  bg.innerHTML = `<div class="pk-modal ${wide ? "wide" : ""}" role="dialog" aria-modal="true" aria-label="${esc(title)}"><h3>${esc(title)}</h3>${html}
    <div class="pk-acts end"><button type="button" class="btn ghost" data-x>${onOk ? "Bekor qilish" : "Yopish"}</button>${onOk ? `<button type="button" class="btn primary" data-ok>${esc(okText)}</button>` : ""}</div></div>`;
  document.body.appendChild(bg);
  const opener = document.activeElement;
  const close = () => { bg.remove(); opener?.focus?.({preventScroll: true}); onClose?.(); };
  bg.addEventListener("mousedown", e => { if (e.target === bg) close(); });
  bg.addEventListener("click", e => { if (e.target.closest("[data-x]")) close(); });
  bg.addEventListener("keydown", e => { if (e.key === "Escape") close(); });
  const ok = bg.querySelector("[data-ok]");
  if (ok) ok.onclick = async () => { ok.disabled = true; try { if (await onOk(bg)) close(); } finally { if (ok.isConnected) ok.disabled = false; } };
  setTimeout(() => bg.querySelector("textarea,input,select,button")?.focus(), 30);
  return bg;
}
async function pkUpload(url, file, extra = "", mb = 0) {
  const M = PK.meta, lim = mb || M.limits.asset_mb;
  if (file.size > lim * 1048576) { toast(`«${file.name}» — fayl ${lim} MB dan katta`); return null; }
  toast(file.size > 20 * 1048576 ? `Yuklanmoqda… (${pkSize(file.size)} — biroz kuting)` : "Yuklanmoqda…");
  return pkApi(`${url}${url.includes("?") ? "&" : "?"}name=${encodeURIComponent(file.name)}${extra}`, file);
}
/* bitta fayl — jarayon ko'rsatkichi bilan (XHR): → {ok, status, data} */
function pkSend(url, file, onProgress) {
  return new Promise(res => {
    const x = new XMLHttpRequest();
    x.open("POST", url); x.withCredentials = true;
    x.upload.onprogress = e => { if (e.lengthComputable && onProgress) onProgress(e.loaded / e.total); };
    x.onload = () => { let d = {}; try { d = JSON.parse(x.responseText || "{}"); } catch (e) {} res({ok: x.status >= 200 && x.status < 300, status: x.status, data: d}); };
    x.onerror = () => res({ok: false, status: 0, data: {message: "Tarmoq xatosi — internet aloqasini tekshirib, qayta urinib ko'ring"}});
    x.send(file);
  });
}
const PK_KORD = ["maruza", "amaliy", "seminar", "laboratoriya", "mustaqil"];
/* NEXTID'dagi dars nomi (kod paketdagi bilan bir xil bo'lsin) */
const pkNextidName = L => L.kind === "maruza" ? `${L.code}-${L.no}-dars: ${L.untitled ? "MAVZU NOMI" : String(L.title).toUpperCase()}`
  : `${L.code}- ${String(L.kind_label).toUpperCase()}: ${L.untitled ? "NOM" : L.title}`;
/* «NEXTID'ga qanday yuklanadi?» — o'qituvchi uchun qisqa yo'riqnoma (dars paneli); L — dars (ixtiyoriy) */
const pkNextidHelp = (L, file) => `<ol class="pk-steps">
    <li><b>«Yuklab olish (.zip)»</b> tugmasini bosing — fayl kompyuteringizga tushadi${file ? ` (<span class="pk-mono">${esc(file)}</span>)` : ""}. Faylni <b>ochmang</b> va ichini o'zgartirmang.</li>
    <li><b>my.isft.uz</b> (NEXTID) → faningiz → <b>«Articulate»</b> yorlig'i → yangi dars qo'shish.</li>
    <li>Dars nomini yozing${L ? `: <b class="pk-copy" id="pkNn">${esc(pkNextidName(L))}</b> <button type="button" class="btn sm ghost" id="pkNc">Nusxalash</button>` : ` — «L1-1-dars: MAVZU NOMI» (ma'ruza), «A1- AMALIY MASHG'ULOT: NOM» (amaliy)`}, yuklab olingan .zip faylni tanlang va saqlang.</li>
    <li>Darsni NEXTID'da ochib, video, matn va taqdimot ko'rinishini tekshiring.</li></ol>
  <p class="pk-note">Video fayl dars ichida ketadi — fayl hajmi kattalashadi; uzun video uchun YouTube havolasi qulayroq. Topshiriq javobini talaba PDF qilib NEXTID'ning o'ziga yuklaydi.</p>`;
const pkPrevUrl = id => `/api/paket/packages/${id}/preview/index.html?preview=1`;   /* ?preview=1 — «Ko'rish rejimi» banneri chiqadi */
function pkPreview(p, title) {
  pkModal(`Ko'rish${title ? ": " + title : ""}`, `<div class="pk-acts pk-prev-h"><span class="pk-note" style="margin:0;flex:1 1 220px">Talaba darsni shunday ko'radi (v${p.version}). Bu ko'rish rejimi — natija saqlanmaydi.</span>
      <a class="btn sm ghost" href="${pkPrevUrl(p.id)}" target="_blank" rel="noopener">Yangi oynada ochish</a>
      <a class="btn sm primary" href="/api/paket/packages/${p.id}/download" data-dl>${ico("download", 15)} Yuklab olish (.zip)</a></div>
    <iframe class="pk-frame" src="${pkPrevUrl(p.id)}" title="Darsni ko'rish" sandbox="allow-scripts allow-popups allow-popups-to-escape-sandbox allow-forms"
      referrerpolicy="no-referrer" allow="fullscreen; encrypted-media; picture-in-picture" allowfullscreen></iframe>`, null, "", true);
  /* sandbox (allow-same-origin YO'Q): dars kontenti ilova origin'idan ajratilgan — sessiya cookie/API'ga kira olmaydi; yangi oynada ham server CSP sandbox qo'yadi */
}

/* ---------- asosiy ko'rinish ---------- */
async function renderPaket(tab) {
  const v = $("#v-paket");
  const who = typeof ME !== "undefined" ? ME : null;
  if (PK.who !== who) {     /* birinchi kirish (who=null) — tashqi havola qo'ygan PK.cid saqlanadi; boshqa foydalanuvchi — hammasi tozalanadi */
    const cid = PK.who === null || PK.who === undefined ? PK.cid : 0, topic = cid ? PK.topic : 1, want = tab || (cid ? PK.tab : null);
    pkReset(); PK.who = who; PK.cid = cid; PK.topic = topic; tab = want;
  }
  if (!PK.meta) { const m = await pkApi("/api/paket/meta"); if (PK.who !== who) return; PK.meta = m; }
  const M = PK.meta, TL = {...PK_TABS, ...(M.tab_labels || {})};
  /* o'qituvchi — to'g'ridan-to'g'ri o'z darslari; bo'lim — avval ko'rib chiqish navbati turgan «Darslar» */
  /* kirish sahifasi — «Fanlar» (dars.js: fan → NEXTID darslar to'ri); u bo'lmasa — avvalgidek */
  const first = M.tabs.includes("fanlar") && typeof dsSubjects === "function" ? "fanlar" : M.tabs.includes("mavzular") && (M.role === "oqituvchi" || M.caps.approve) ? "mavzular" : M.tabs.filter(t => t !== "fanlar")[0];
  PK.tab = tab && M.tabs.includes(tab) ? tab : (PK.tab && M.tabs.includes(PK.tab) ? PK.tab : first);
  const kuLink = typeof renderKurs === "function" && M.caps.write;   /* kurs.js: bloklar muharriri — barcha kurslar ro'yxati (alohida menyu bandi yo'q) */
  v.innerHTML = `<div class="pk-head"><div><h2>${esc(M.title || "Dars tayyorlash")}</h2><span class="muted">${esc(M.scope)} · fayllarni yuklang, «Tayyorlash»ni bosing — NEXTID uchun tayyor dars fayli chiqadi</span></div>
      ${kuLink ? `<button type="button" class="btn sm ghost" id="pkToKu" title="Bloklar muharriri: barcha kurslar, Rise importi — Rise 360 kabi">${ico("layers", 15)} Muharrir: barcha kurslar</button>` : ""}</div>
    ${M.demo && M.caps.approve ? `<div class="pk-demo">${ico("info", 15)}<span><b>Namuna.</b> «Mikroiqtisodiyot» 1–2-mavzulari: ma'ruza matni, taqdimot va video havola — sun'iy (demo); video mavjud emas. Haqiqiy dars uchun o'z fayllaringizni yuklang.</span></div>` : ""}
    ${!M.player && M.caps.build ? `<div class="pk-warnbox">${ico("alert", 15)}<span>Dars oynasi o'rnatilmagan — «Tayyorlash» vaqtincha ishlamaydi (administratorga murojaat qiling). Fayllarni yuklab qo'yish mumkin.</span></div>` : ""}
    ${M.tabs.length > 1 ? `<div class="pk-tabs" role="tablist">${M.tabs.map(t => `<button type="button" role="tab" aria-selected="${t === PK.tab}" class="${t === PK.tab ? "on" : ""}" data-t="${t}">${esc(TL[t])}</button>`).join("")}</div>` : ""}
    <div id="pkBox"><div class="pk-empty">Yuklanmoqda…</div></div>`;
  v.querySelectorAll(".pk-tabs [data-t]").forEach(b => b.onclick = () => renderPaket(b.dataset.t));
  v.querySelector("#pkToKu")?.addEventListener("click", () => go("kurs"));
  const box = $("#pkBox");
  try {
    await ({fanlar: typeof dsSubjects === "function" ? dsSubjects : pkTopics, qamrov: pkCoverage, mavzular: pkTopics, joylash: pkBulk, sozlama: pkSettings})[PK.tab](box);
  } catch (e) {
    if (e?.message === "auth") return;
    box.innerHTML = e?.message === "denied" ? locked("Bu bo'lim") : `<div class="card pk-card"><p>${esc(e?.msg || "Ma'lumotni yuklab bo'lmadi")}</p></div>`;
  }
}

/* ---------- Kurs tanlash (bitta kurs bo'lsa — ko'rsatilmaydi; qidiruv — faqat kurs ko'p bo'lsa) ---------- */
async function pkPicker(box, onPick) {
  const first = await pkApi("/api/paket/courses?limit=60&q=");
  if (!PK.cid) PK.cid = first.items[0]?.id || 0;
  if (first.total <= 1) { box.innerHTML = ""; return; }
  const many = first.total > 8;
  box.innerHTML = `<div class="pk-pick">${many ? `<label class="pk-sr" for="pkPq">Kursni qidirish</label>
      <input type="search" id="pkPq" placeholder="Fan, yo'nalish, o'qituvchi…" autocomplete="off">` : ""}
      <label class="pk-lbl" for="pkPs">Fan (kurs)</label><select id="pkPs"><option>Yuklanmoqda…</option></select></div>`;
  const inp = box.querySelector("#pkPq"), sel = box.querySelector("#pkPs");
  let timer = null;
  const load = async (q, d) => {
    d = d || await pkApi(`/api/paket/courses?limit=60&q=${encodeURIComponent(q || "")}`);
    const items = d.items.slice();
    if (PK.cid && !items.some(x => x.id === PK.cid) && !q) {
      try { const c = await pkApi(`/api/paket/courses/${PK.cid}`); items.unshift({id: PK.cid, subject: c.course.subject, direction: c.course.direction, course: c.course.course, built: 0}); } catch (e) {}
    }
    /* holat belgisi o'rniga tushunarli matn: nechta dars tayyorlangan / nechtasi tasdiq kutmoqda */
    sel.innerHTML = items.map(x => `<option value="${x.id}" ${x.id === PK.cid ? "selected" : ""}>${esc(x.subject)} — ${esc(x.direction)}, ${x.course}-kurs${x.built ? ` · ${x.built} ta dars tayyorlangan` : ""}${x.waiting ? ` · ${x.waiting} ta tasdiq kutmoqda` : ""}</option>`).join("")
      || `<option value="">Topilmadi</option>`;
    if (d.total > items.length) sel.insertAdjacentHTML("beforeend", `<option disabled>… yana ${fmt(d.total - items.length)} ta — qidiruvdan foydalaning</option>`);
  };
  if (inp) inp.oninput = () => { clearTimeout(timer); timer = setTimeout(() => load(inp.value.trim()), 250); };
  sel.onchange = () => { const id = +sel.value; if (id && id !== PK.cid) { PK.cid = id; PK.topic = 1; PK.ups = null; onPick(); } };
  await load("", first);
}

/* ---------- Holat (kafedra / o'qituvchi / kurs kesimida) ---------- */
async function pkCoverage(box) {
  const M = PK.meta, F = PK.cov;
  const d = await pkApi("/api/paket/coverage");
  const t = d.total;
  const srcs = r => `<small>matn ${fmt(r.text)} · taqdimot ${fmt(r.slides)} · video ${fmt(r.video)} · test ${fmt(r.quiz)}</small>`;
  box.innerHTML = `
    <div class="pk-kpis">
      ${pkKpi("Tayyorlangan darslar", pkPct(t.built_pct), `${fmt(t.built)} / ${fmt(t.topics)} dars`, pkTone(t.built_pct))}
      ${pkKpi("Tasdiqlangan", fmt(t.approved), `${pkPct(t.pct)} dars · NEXTID'ga yuklashga tayyor`, "ok")}
      ${pkKpi("Tasdiq kutilmoqda", fmt(t.waiting), "bo'lim ko'rib chiqadi", t.waiting ? "info" : "")}
      ${pkKpi("Fayllari to'liq darslar", fmt(t.full), "matn, taqdimot, video va test bor")}
      ${pkKpi("Ma'ruza matni / taqdimot", `${fmt(t.text)} / ${fmt(t.slides)}`, "dars")}
      ${pkKpi("Video / test", `${fmt(t.video)} / ${fmt(t.quiz)}`, "havola yoki fayl · savollar yoki mashqlar")}
      ${pkKpi("Mashqli darslar", fmt(t.exercises || 0), "moslashtirish, saralash, kartochkalar")}
    </div>
    <div class="card pk-card"><h3>Kafedralar</h3><p class="muted">Tayyorlangan darslar ulushi · eng ortda turganlari yuqorida${M.caps.view ? " · kafedra nomini bosing — kurslar ro'yxati filtrlanadi" : ""}</p>
      ${pkTable([["Kafedra", r => M.caps.view ? `<button type="button" class="pk-link" data-dep="${r.department_id}">${esc(r.name)}</button>` : esc(r.name)],
                 ["Darslar", r => `${pkBar(r.built_pct, pkTone(r.built_pct))}<small>${fmt(r.built)} / ${fmt(r.topics)} dars tayyorlangan · tasdiqlangan ${fmt(r.approved)}</small>`],
                 ["Fayllar", srcs],
                 ["Kurslar", r => `${fmt(r.started)} / ${fmt(r.courses)}<small>boshlangan</small>`, "num"]], d.departments)}</div>
    ${d.teachers.length ? `<details class="card pk-card pk-det"><summary><h3>O'qituvchilar</h3><span class="muted">${fmt(d.teachers.filter(x => x.started).length)} nafarida boshlangan</span></summary>
      ${pkTable([["O'qituvchi", r => `${esc(r.name)}<small>${esc(r.dept || "")}</small>`],
                 ["Darslar", r => `${pkBar(r.built_pct, pkTone(r.built_pct))}<small>${fmt(r.built)} / ${fmt(r.topics)} · tasdiqlangan ${fmt(r.approved)}</small>`],
                 ["Fayllar", srcs]],
                d.teachers.slice().sort((a, b) => (b.started - a.started) || ((a.built_pct || 0) - (b.built_pct || 0))).slice(0, 40))}</details>` : ""}
    ${M.caps.view ? `<div class="card pk-card"><h3>Kurslar</h3>
      <div class="pk-filters">
        <input type="search" id="pkCq" placeholder="Fan, yo'nalish, o'qituvchi…" value="${esc(F.q)}" aria-label="Qidirish">
        <select id="pkCo" aria-label="Holat"><option value="">Hammasi</option><option value="started" ${F.only === "started" ? "selected" : ""}>Boshlanganlar</option>
          <option value="waiting" ${F.only === "waiting" ? "selected" : ""}>Tasdiq kutayotganlar</option><option value="empty" ${F.only === "empty" ? "selected" : ""}>Hali boshlanmagan</option></select>
        <select id="pkCd" aria-label="Kafedra"><option value="0">Barcha kafedralar</option>${d.departments.map(x => `<option value="${x.department_id}" ${x.department_id === F.department_id ? "selected" : ""}>${esc(x.name)}</option>`).join("")}</select>
      </div><div id="pkCl"><div class="pk-empty">Yuklanmoqda…</div></div></div>` : `<p class="pk-note">Rahbariyat uchun jamlangan ko'rinish: dars matnlari va fayllari ko'rsatilmaydi.</p>`}`;
  if (!M.caps.view) return;
  box.querySelectorAll("[data-dep]").forEach(b => b.onclick = () => { F.department_id = +b.dataset.dep; F.offset = 0; box.querySelector("#pkCd").value = String(F.department_id); pkCourseList(box); box.querySelector("#pkCl").scrollIntoView({block: "start", behavior: "smooth"}); });
  let timer = null;
  box.querySelector("#pkCq").oninput = e => { clearTimeout(timer); timer = setTimeout(() => { F.q = e.target.value.trim(); F.offset = 0; pkCourseList(box); }, 250); };
  box.querySelector("#pkCo").onchange = e => { F.only = e.target.value; F.offset = 0; pkCourseList(box); };
  box.querySelector("#pkCd").onchange = e => { F.department_id = +e.target.value; F.offset = 0; pkCourseList(box); };
  await pkCourseList(box);
}
async function pkCourseList(box) {
  const F = PK.cov, el = box.querySelector("#pkCl"), lim = 30;
  const d = await pkApi(`/api/paket/courses?limit=${lim}&offset=${F.offset}&q=${encodeURIComponent(F.q)}&only=${F.only}&department_id=${F.department_id}`);
  el.innerHTML = pkTable([
    ["Fan", r => `<b>${esc(r.subject)}</b><small>${esc(r.direction)} · ${r.course}-kurs</small>`],
    ["Mas'ul", r => `${esc(r.teacher || "—")}<small>${esc(r.dept || "")}</small>`],
    ["Darslar", r => `${pkBar(r.built_pct, pkTone(r.built_pct))}<small>${r.built} / ${r.topics} dars tayyorlangan · tasdiqlangan ${r.approved}${r.waiting ? ` · <b>tasdiq kutmoqda ${r.waiting}</b>` : ""}</small>`],
    ["Fayllar", r => `<small>matn ${r.text} · taqdimot ${r.slides} · video ${r.video} · test ${r.quiz}</small>`],
    ["", r => `<button type="button" class="btn sm ${r.waiting ? "primary" : ""}" data-open="${r.id}" data-no="${r.waiting_no || 1}">${r.waiting ? "Ko'rib chiqish" : "Ochish"}</button>`]], d.items, {empty: "Kurs topilmadi"}) +
    (d.total > lim ? `<div class="pk-pager"><button type="button" class="btn sm ghost" data-p="${Math.max(0, F.offset - lim)}" ${F.offset ? "" : "disabled"}>← Oldingi</button>
      <span>${fmt(F.offset + 1)}–${fmt(Math.min(d.total, F.offset + lim))} / ${fmt(d.total)}</span>
      <button type="button" class="btn sm ghost" data-p="${F.offset + lim}" ${F.offset + lim < d.total ? "" : "disabled"}>Keyingi →</button></div>` : "");
  el.querySelectorAll("[data-p]").forEach(b => b.onclick = () => { F.offset = +b.dataset.p; pkCourseList(box); });
  /* «Ochish» — tasdiq kutayotgan dars bo'lsa aynan o'sha dars ochiladi (L1 emas) */
  el.querySelectorAll("[data-open]").forEach(b => b.onclick = () => { PK.cid = +b.dataset.open; PK.topic = +b.dataset.no || 1; PK.ups = null; renderPaket("mavzular"); });
}

/* ---------- Darslar: [bo'lim — ko'rib chiqish navbati] → kurs → darslar ro'yxati → dars ekrani ---------- */
const pkScroller = () => document.querySelector(".shell") || document.scrollingElement;
async function pkTopics(box) {
  box.innerHTML = `<div id="pkQu"></div><div id="pkPk"></div><div id="pkCv"></div>`;
  const cv = box.querySelector("#pkCv");
  pkQueue(box.querySelector("#pkQu")).catch(() => {});
  await pkPicker(box.querySelector("#pkPk"), () => pkCourse(cv));
  await pkCourse(cv);
}
/* bo'lim: tasdiq kutayotgan darslar (birinchi) va tasdiqlangan versiyasi eskirganlari; o'qituvchi: faqat «qayta tayyorlash kerak» */
async function pkQueue(el) {
  const M = PK.meta;
  const d = await pkApi("/api/paket/queue");
  const wait = M.caps.approve ? d.items.filter(x => x.kind === "kutilmoqda") : [], stale = d.items.filter(x => x.kind === "eskirgan");
  if (!wait.length && !stale.length) { el.innerHTML = ""; return; }
  const row = x => `<li><span class="pk-code">${esc(x.code)}</span><span class="pk-q-t"><b>${esc(x.title)}</b><small>${esc(x.subject)} — ${esc(x.direction)}, ${x.course}-kurs${M.caps.approve ? ` · ${esc(x.teacher || "—")}` : ""} · v${x.version} · ${pkD(x.built_at)}</small></span>
      <button type="button" class="btn sm ${x.kind === "kutilmoqda" ? "primary" : ""}" data-qc="${x.course_id}" data-qn="${x.no}">${x.kind === "kutilmoqda" ? "Ko'rib chiqish" : "Ochish"}</button></li>`;
  el.innerHTML = `<div class="card pk-card pk-queue">
    ${wait.length ? `<h3>Tasdiq kutayotgan darslar <span class="pk-chip info">${wait.length}</span></h3><p class="muted">O'qituvchi tayyorlab yuborgan — ko'rib, tasdiqlang yoki izoh bilan qaytaring.</p><ul class="pk-ql">${wait.map(row).join("")}</ul>` : ""}
    ${stale.length ? `<h3 ${wait.length ? 'style="margin-top:14px"' : ""}>Tasdiqlangan versiya eskirgan <span class="pk-chip warn">${stale.length}</span></h3>
      <p class="muted">Tasdiqdan keyin fayl almashtirilgan yoki yangi savol tasdiqlangan — ${M.caps.approve ? "o'qituvchi darsni qayta tayyorlashi kerak" : "darsni qayta tayyorlang"}.</p><ul class="pk-ql">${stale.map(row).join("")}</ul>` : ""}</div>`;
  el.querySelectorAll("[data-qc]").forEach(b => b.onclick = () => { PK.cid = +b.dataset.qc; PK.topic = +b.dataset.qn; PK.ups = null; renderPaket("mavzular"); });
}
async function pkCourse(el) {
  if (!PK.cid) { el.innerHTML = `<div class="card pk-card pk-empty">Sizga biriktirilgan fan (kurs) topilmadi. Masofaviy ta'lim bo'limiga murojaat qiling.</div>`; return; }
  const sc = pkScroller(), top = sc ? sc.scrollTop : 0, had = !!el.querySelector("#pkTp");
  const d = await pkApi(`/api/paket/courses/${PK.cid}`), c = d.course, M = PK.meta;
  if (!d.topics.some(t => t.no === PK.topic)) PK.topic = d.topics[0]?.no || 1;
  const last = d.course_packages[0];
  const groups = PK_KORD.map(k => [k, d.topics.filter(t => t.kind === k)]).filter(g => g[1].length);
  const stChip = t => `${pkChip(t.state_label, PK_LS[t.state])}${t.stale ? pkChip("eskirgan", "warn") : ""}${t.returned ? pkChip("qaytarilgan", "bad") : ""}`;
  const tBtn = t => `<button type="button" role="listitem" class="pk-topic st-${t.state} ${t.no === PK.topic ? "on" : ""}" data-no="${t.no}" aria-pressed="${t.no === PK.topic}">
        <span class="no">${esc(t.code)}</span><span class="tt ${t.untitled ? "un" : ""}">${esc(t.title)}</span><span class="st">${stChip(t)}</span></button>`;
  const stTxt = t => `${t.state_label}${t.stale ? " · eskirgan" : ""}${t.returned ? " · qaytarilgan" : ""}`;
  el.innerHTML = `<div class="card pk-card pk-lessons"><div class="pk-item-h"><div><h3>${esc(c.subject)}</h3>
      <p class="muted">${esc(c.direction)} · ${c.course}-kurs${M.role === "oqituvchi" ? "" : ` · ${esc(c.dept || "—")} · mas'ul: ${esc(c.teacher || "—")}`} · ${c.lessons} ta dars — darsni tanlang</p></div></div>
    <label class="pk-lsel"><span>Dars</span><select id="pkLs">${groups.map(([k, ts]) => `<optgroup label="${esc(d.kinds[k].plural)}">${ts.map(t => `<option value="${t.no}" ${t.no === PK.topic ? "selected" : ""}>${esc(t.code)} · ${esc(t.title)} — ${esc(stTxt(t))}</option>`).join("")}</optgroup>`).join("")}</select></label>
    <div class="pk-lgrid">${groups.map(([k, ts]) => `<div class="pk-kind">${groups.length > 1 ? `<h4>${esc(d.kinds[k].plural)} <span class="muted">· ${ts.length} ta</span></h4>` : ""}
      <div class="pk-topics" role="list">${ts.map(tBtn).join("")}</div></div>`).join("")}</div></div>
    <div id="pkTp"></div>
    ${d.can.write ? `<details class="card pk-card pk-det pk-adv" id="pkAdv" ${PK.adv ? "open" : ""}><summary><h3>Kengaytirilgan sozlamalar</h3><span class="muted">dars turi, o'tish bali, bloklar, muqova, subtitr, qo'shimcha fayllar, kurs sozlamalari — odatda o'zgartirish shart emas</span></summary>
      <div id="pkAdvL"></div>
      <h3 class="pk-adv-h">Butun kurs uchun</h3>
      <details class="pk-det pk-sub"><summary><b>Darslar ro'yxati (NEXTID)</b><span class="muted">amaliy, seminar, laboratoriya darslarini qo'shish yoki nomlarni NEXTID'dagidek yozish</span></summary>
        <p class="pk-note">Har qatorda bitta dars: «L1-1-dars: MAVZU NOMI», «A1- AMALIY MASHG'ULOT: NOM», «A2- Amaliy: NOM», «S1 …», «Lab1 …», «MT1 …». Mavzuga bog'lash (ixtiyoriy): oxirida «(3-mavzu)».</p>
        <label class="pk-sr" for="pkLt">Darslar ro'yxati</label><textarea id="pkLt" class="pk-ta" placeholder="L1-1-dars: AXBOROT TEXNOLOGIYALARI&#10;A1- AMALIY MASHG'ULOT: Excel bilan ishlash (1-mavzu)&#10;A2- Amaliy: Word hujjatlari"></textarea>
        <div class="pk-acts"><button type="button" class="btn sm" id="pkLc">Tekshirish</button><button type="button" class="btn sm primary" id="pkLs2">Saqlash</button></div><div id="pkLr"></div></details>
      <details class="pk-det pk-sub"><summary><b>Kurs muqovasi va o'qituvchi rasmi</b><span class="muted">kursning barcha darslari uchun${d.media.muqova ? " · muqova bor" : ""}${d.media.avatar ? " · rasm bor" : ""}</span></summary>
        <div class="pk-media">${[["muqova", "Kurs muqovasi", "cover", "Darsning birinchi sahifasidagi fon rasmi. Darsga alohida muqova yuklanmasa shu, bo'lmasa bo'lim standarti ishlatiladi."],
                                 ["avatar", "O'qituvchi rasmi", "avatar", "«Topshiriq» qismida ko'rinadi. Yuklanmasa oddiy belgi chiziladi."]].map(([k, l, u, h]) => `<div>
          ${d.media[k] ? `<img class="pk-thumb ${k}" src="/api/paket/assets/${d.media[k]}" alt="${esc(l)}">` : `<div class="pk-thumb ${k} none">yo'q</div>`}
          <div><b>${esc(l)}</b><p class="pk-note" style="margin:2px 0 6px">${esc(h)}</p><div class="pk-acts tight" style="justify-content:flex-start">
            <label class="btn sm pk-file">${ico("upload", 15)} Rasm tanlash (.png, .jpg)<input type="file" accept=".png,.jpg,.jpeg" hidden data-cm="${u}"></label>
            ${d.media[k] ? `<button type="button" class="btn sm ghost" data-cdel="${d.media[k]}">Olib tashlash</button>` : ""}</div></div></div>`).join("")}</div></details>
      <details class="pk-det pk-sub"><summary><b>Kurs paketi</b><span class="muted">Barcha darslar bitta faylda${last ? ` · oxirgisi v${last.version}, ${pkD(last.built_at)}` : ""}</span></summary>
        <div class="pk-form"><label>Turi<select id="pkKm">${["xapi", "scorm12", "scorm2004"].map(m => `<option value="${m}">${esc(pkMode(m))}</option>`).join("")}</select></label>
          <label class="cb"><input type="checkbox" id="pkKa"> Faqat tasdiqlangan darslar</label>
          <div class="pk-acts"><button type="button" class="btn sm primary" id="pkKb" ${M.player ? "" : "disabled"}>${ico("package", 15)} Kurs paketini tayyorlash</button></div></div>
        ${d.course_packages.length ? pkTable([["Versiya", p => `v${p.version} · ${esc(pkMode(p.mode))}<small>${pkD(p.built_at)} · ${esc(p.by || "")}</small>`],
          ["Darslar", p => `${(p.settings.topics || []).length} ta`, "num"], ["Hajm", p => pkSize(p.size), "num"],
          ["", p => `<a class="btn sm ghost" href="/api/paket/packages/${p.id}/download">${ico("download", 15)} Yuklab olish</a>`]], d.course_packages) : ""}</details>
    </details>` : ""}`;
  const adv = el.querySelector("#pkAdv"); if (adv) adv.ontoggle = () => { PK.adv = adv.open; };
  const lrun = async apply => {
    const text = el.querySelector("#pkLt").value;
    if (!text.trim()) { toast("Darslar ro'yxatini kiriting"); return; }
    const r = await pkApi(`/api/paket/courses/${PK.cid}/lessons`, {text, apply});
    if (!r) return;
    if (apply) { toast(`Saqlandi: ${r.saved} ta dars${r.errors ? `, xato: ${r.errors}` : ""}`); pkCourse(el); return; }
    el.querySelector("#pkLr").innerHTML = pkTable([["Qator", x => x.line, "num"], ["Dars", x => x.ok ? `<b>${esc(x.code)}</b> · ${esc(x.title)}${x.topic ? `<small>${x.topic}-mavzuga bog'langan</small>` : ""}` : `<span class="pk-mono">${esc(x.raw)}</span>`],
      ["", x => x.ok ? pkChip(x.new ? "yangi" : "yangilanadi", "ok") : `<small class="pk-bad">${esc(x.error)}</small>`]], r.rows, {empty: "Qator topilmadi"});
  };
  el.querySelector("#pkLc")?.addEventListener("click", () => lrun(false));
  el.querySelector("#pkLs2")?.addEventListener("click", () => lrun(true));
  const pick = no => { if (no === PK.topic) return; PK.topic = no; PK.ups = null; PK.prac = false; pkCourse(el); };
  el.querySelectorAll(".pk-topic").forEach(b => b.onclick = () => pick(+b.dataset.no));
  el.querySelector("#pkLs").onchange = e => pick(+e.target.value);
  el.querySelectorAll("[data-cm]").forEach(i => i.onchange = async () => { const f = i.files[0]; if (!f) return;
    const r = await pkUpload(`/api/paket/courses/${PK.cid}/${i.dataset.cm}`, f); if (r) { toast("Rasm saqlandi"); pkCourse(el); } });
  el.querySelectorAll("[data-cdel]").forEach(b => b.onclick = async () => { if (!confirm("Rasm olib tashlansinmi?")) return;
    const r = await pkApi(`/api/paket/assets/${b.dataset.cdel}/delete`, {}); if (r) { toast("Olib tashlandi"); pkCourse(el); } });
  el.querySelector("#pkKb")?.addEventListener("click", async e => {
    const btn = e.currentTarget; btn.disabled = true;   /* await'dan keyin e.currentTarget = null — havola oldindan saqlanadi */
    try {
      const r = await pkApi(`/api/paket/courses/${PK.cid}/course-package`, {mode: el.querySelector("#pkKm").value, only_approved: el.querySelector("#pkKa").checked});
      if (r) { toast(`Kurs paketi tayyor: ${r.topics.length} ta dars`); pkCourse(el); }
    } finally { if (btn.isConnected) btn.disabled = false; }
  });
  await pkTopicPanel(el.querySelector("#pkTp"));
  if (had && sc) sc.scrollTop = top;          /* qayta chizilganda sahifa joyidan siljimasin */
}

/* rasm noaniq: muqova, matn ichidagi rasm yoki slayd — bitta savol (bir nechta rasm bo'lsa hammasiga) → "muqova" | "rasm" | "slayd" | null */
function pkAskImage(files) {
  return new Promise(res => {
    let pick = null;
    const names = files.slice(0, 3).map(f => `«${esc(f.name)}»`).join(", ") + (files.length > 3 ? ` va yana ${files.length - 3} ta` : "");
    const bg = pkModal(files.length > 1 ? "Bu rasmlar nima uchun?" : "Bu rasm nima uchun?", `<p class="pk-note" style="margin:0 0 10px">${names}</p>
      <div class="pk-choice">
        <button type="button" class="btn" data-as="muqova"><b>Dars muqovasi</b><small>darsning birinchi sahifasidagi fon rasmi${files.length > 1 ? " (oxirgi rasm olinadi)" : ""}</small></button>
        <button type="button" class="btn" data-as="rasm"><b>Matn ichidagi rasm</b><small>ma'ruza matniga qo'shiladi</small></button>
        <button type="button" class="btn" data-as="slayd"><b>Taqdimot slaydi</b><small>slayd rasmlari to'plamiga qo'shiladi</small></button>
      </div>`, null, "", false, () => res(pick));
    bg.querySelectorAll("[data-as]").forEach(b => b.onclick = () => { pick = b.dataset.as; bg.querySelector("[data-x]").click(); });
  });
}
const pkUpDesc = r => ({matn: () => `Ma'ruza matni — ${(r.plan || []).length} band reja${r.images ? `, ${r.images} rasm` : ""}${r.tables ? `, ${r.tables} jadval` : ""}${r.refs ? `, ${r.refs} adabiyot` : ""}`,
  taqdimot: () => `Taqdimot — ${r.count ?? r.pages ?? 0} slayd`, slayd: () => "Taqdimot slaydi (rasm)", video: () => `Video — ${pkSize(r.size)}`, muqova: () => "Dars muqovasi",
  rasm: () => "Matn ichidagi rasm", poster: () => "Video muqovasi", subs: () => `Subtitr — ${r.cues} yozuv`, fayl: () => "Qo'shimcha fayl"}[r.as] || (() => r.label || "Yuklandi"))();

/* ---------- Dars ekrani ---------- */
async function pkTopicPanel(el) {
  const M = PK.meta, base = `/api/paket/courses/${PK.cid}/topics/${PK.topic}`, key = `${PK.cid}/${PK.topic}`;
  if (!el.firstChild) el.innerHTML = `<div class="pk-empty">Yuklanmoqda…</div>`;
  const d = await pkApi(base), R = d.ready, can = d.can, S = d.settings;
  const reload = () => pkCourse($("#pkCv"));
  const tx = R.text, sl = R.slides, vd = R.video, qz = R.quiz, L = d.lesson, KP = d.keypoints, cv = R.cover, xr = R.exercises, ag = R.assignment, EX = d.exercises;
  const exN = x => x.kind === "match" ? `${x.pairs.length} juft` : x.kind === "sort" ? `${x.categories.length} toifa, ${x.categories.reduce((a, c) => a + c.items.length, 0)} element` : `${x.cards.length} kartochka`;
  const kpItems = (KP.approved?.items || []), kpDraft = (KP.draft?.items || []);
  const assets = d.assets, p0 = d.packages[0], NX = d.nextid;
  const W = can.write;
  /* --- to'rtta holat kartasi --- */
  const tile = (k, icon, name, ok, main, subs, acts, opt) => `<div class="pk-tile ${ok ? "ok" : ""}" data-tile="${k}">
      <div class="pk-tile-h">${ico(icon, 18)}<b>${esc(name)}</b>${ok ? `<span class="pk-tick" title="Bor">${ico("checkc", 18)}<span class="pk-sr">bor</span></span>` : `<span class="pk-none">${opt ? "ixtiyoriy" : "hali yo'q"}</span>`}</div>
      <div class="pk-tile-b"><p>${main}</p>${(subs || []).filter(Boolean).map(s => `<small>${s}</small>`).join("")}</div>
      ${W && acts && acts.trim() ? `<div class="pk-tile-a">${acts}</div>` : ""}</div>`;
  const txInfo = [R.plan.ok ? `${R.plan.n} band reja` : "", R.images.n ? `${R.images.n} rasm` : "", R.images.tables ? `${R.images.tables} jadval` : "",
                  R.refs.ok ? `${R.refs.n} adabiyot` : "", ag.ok ? `${ag.n} topshiriq savoli` : "", R.keypoints.ok ? `${R.keypoints.n} xulosa` : ""].filter(Boolean).join(" · ");
  const vLink = vd.url && !vd.error ? `${vd.video_id ? "YouTube havolasi" : "Tashqi havola"}${vd.link_src === "paket" ? "" : " (kontent monitoringidan)"}${vd.demo ? " · namuna" : ""}` : "";
  const vFile = vd.file ? `${esc(vd.file.name)} · ${pkSize(vd.file.size)}` : "";
  const vErr = vd.error && vd.link_src === "paket";       /* faqat shu yerda kiritilgan havola xatosi ko'rsatiladi (monitoringdagi eski havola — yo'q hisob) */
  const slSrc = {pptx: "PowerPoint", deck: "ISFT shablonidagi taqdimot", images: "slayd rasmlari", pdf: "PDF"}[sl.src] || "";
  const nQ = qz.approved || 0, nX = xr.n || 0;
  const tiles = `<div class="pk-tiles">
    ${tile("text", "file", "Matn", tx.ok, tx.ok ? `${esc(tx.name)}${tx.src === "paket" ? "" : " <i>(Test bankda yuklangan)</i>"}` : "Word fayl (.docx) tashlang — reja, rasm va jadvallar o'zi ajratiladi",
        [txInfo, tx.ok && tx.only_assignment ? "faqat topshiriqlar ro'yxati — «Topshiriq» qismiga o'tdi" : ""],
        tx.ok ? `<label class="btn sm ghost pk-file">Almashtirish<input type="file" accept=".docx,.pdf,.txt" hidden data-up="matn"></label>${d.text_asset ? `<button type="button" class="btn sm ghost" data-rm="text">Olib tashlash</button>` : ""}` : "")}
    ${tile("slides", "slides", "Taqdimot", sl.ok, sl.ok ? `${sl.n ? `${sl.n} slayd` : "PDF taqdimot"}${slSrc ? ` · ${esc(slSrc)}` : ""}` : "PDF yoki PowerPoint (.pptx) tashlang",
        [sl.ok && sl.src === "pptx" ? "aniq ko'rinishi uchun PDF qilib ham yuklang (PowerPoint: Fayl → Saqlash → PDF)" : "", sl.captions || sl.audio ? `${sl.captions} izoh · ${sl.audio} audio` : ""],
        `${sl.ok ? `<label class="btn sm ghost pk-file">Almashtirish<input type="file" accept=".pptx,.pdf,.png,.jpg,.jpeg" multiple hidden data-up="taqdimot"></label><button type="button" class="btn sm ghost" data-rm="slides">Olib tashlash</button>` : ""}
         ${can.deck && tx.ok && sl.src !== "deck" ? `<button type="button" class="btn sm ${sl.ok ? "ghost" : ""}" id="pkDkNew" title="Yuklangan ma'ruza matnidan ISFT shablonida taqdimot tuziladi">${ico("spark", 15)} ISFT shablonida taqdimot yaratish</button>` : ""}`)}
    ${tile("video", "video", "Video", vd.ok, vd.ok ? (vd.provider === "file" ? vFile : vLink) : vErr ? `<span class="pk-bad">${esc(vd.error)}</span>` : "MP4 fayl tashlang yoki YouTube havolasini kiriting",
        [vd.both ? `yana ${vd.provider === "file" ? "YouTube havolasi" : "video fayl"} ham bor — darsga «${esc(M.video_sources[S.video_source])}» kiradi` : "",
         vd.file ? `subtitr: ${vd.captions.length ? vd.captions.map(x => esc(x.lang)).join(", ") : "yo'q"}${vd.poster ? " · muqovasi bor" : ""}` : "",
         vd.file && vd.file.studio ? "studiyada yozilgan, AI montaj qilingan" : ""],
        (vd.ok || vErr ? `<label class="btn sm ghost pk-file">Almashtirish<input type="file" accept=".mp4,.webm,video/mp4,video/webm" hidden data-up="video"></label>${vd.file || vd.link_src === "paket" ? `<button type="button" class="btn sm ghost" data-rm="video">Olib tashlash</button>` : ""}` : "")
        + (!vd.ok && typeof modOn === "function" && modOn("studio") && ["oqituvchi", "masofaviy", "masofaviy_xodim"].includes(M.role) && ["maruza", "amaliy"].includes(L.kind)
           ? `<button type="button" class="btn sm ghost" onclick="go('studio')" title="Studiyada syomka → AI montaj → video darsga o'zi qo'yiladi">${ico("video", 15)} Studiyada yozish</button>` : ""))}
    ${tile("quiz", "checkc", "Test va mashqlar", !!(nQ || nX), nQ || nX ? `${nQ} savol · ${nX} mashq` : "Test savollari va mashqlar — xohlasangiz qo'shing",
        [nQ && qz.used !== nQ ? `darsga ${qz.used} ta savol kiradi` : "", xr.draft ? `${xr.draft} ta mashq qoralamasi — ko'rib saqlang` : ""],
        `<button type="button" class="btn sm ghost" id="pkPrOpen">${ico("plus", 15)} Qo'shish</button>`, true)}
  </div>`;
  /* --- natija: oxirgi versiya holati --- */
  const miss = (R.core_missing || []).map(k => PK_NAMES[k] || M.blocks[k]);
  const flow = p0 ? (() => {
    const sent = p0.status !== "qoralama", appr = p0.status === "tasdiqlandi";
    return `<ol class="pk-flow" aria-label="Dars holati"><li class="done">Tayyorlandi</li><li class="${sent ? "done" : p0.note ? "bad" : ""}">${p0.note && !sent ? "Bo'lim qaytardi" : "Bo'limga yuborildi"}</li><li class="${appr ? "done" : ""}">Tasdiqlandi</li></ol>`; })() : "";
  const stMsg = !p0 ? "" : p0.status === "tasdiqlandi" ? `<p class="pk-msg ok">${ico("checkc", 16)} Tasdiqlandi${p0.approved_name ? ` — ${esc(p0.approved_name)}, ${pkD(p0.approved_at)}` : ""}. NEXTID'ga yuklash mumkin.</p>`
    : p0.status === "tayyor" ? `<p class="pk-msg info">${ico("clock", 16)} Bo'limga yuborildi — Masofaviy ta'lim bo'limi ko'rib, tasdiqlaydi yoki izoh bilan qaytaradi.</p>`
    : p0.note ? `<p class="pk-msg bad">${ico("alert", 16)} <span><b>Bo'lim qaytardi:</b> ${esc(p0.note)} — faylni tuzatib, «Tayyorlash»ni qayta bosing.</span></p>`
    : `<p class="pk-msg">${ico("info", 16)} <span>Hali bo'limga yuborilmadi${miss.length ? ` — yetishmaydi: <b>${esc(miss.join(", "))}</b>. Yuklab, «Tayyorlash»ni qayta bosing` : ""}.${W ? ` <button type="button" class="btn sm ghost" id="pkSubmit">Shu holicha bo'limga yuborish</button>` : ""}</span></p>`;
  const nxMsg = NX ? `<p class="pk-nx">${ico("flag", 15)} <span><b>NEXTID uchun: v${NX.version}</b> (tasdiqlangan${NX.approved_at ? ", " + pkD(NX.approved_at) : ""})${p0 && NX.id !== p0.id ? ` — yangi v${p0.version} hali tasdiqlanmagan, NEXTID'ga hozircha v${NX.version} yuklanadi. <a href="/api/paket/packages/${NX.id}/download">v${NX.version} ni yuklab olish</a>` : ""}</span></p>` : "";
  const result = p0 ? `<div class="card pk-card pk-result" id="pkRes">
      <div class="pk-item-h"><div><h3>Tayyor dars — v${p0.version}</h3><p class="muted">${pkD(p0.built_at)} · ${esc(p0.by || "")} · ${pkSize(p0.size)}${p0.valid ? " · Tekshirildi ✓" : ""}${p0.mode !== "xapi" ? ` · ${esc(pkMode(p0.mode))}` : ""}${p0.demo ? " · namuna" : ""}</p></div>${flow}</div>
      ${d.stale ? `<p class="pk-msg warn" role="status">${ico("alert", 16)} <span><b>Tasdiqlangan versiya eskirgan — qayta tayyorlang.</b> Tasdiqdan keyin fayl almashtirilgan yoki yangi savol tasdiqlangan; NEXTID'dagi dars eski holatda qoladi.</span></p>` : ""}
      ${stMsg}${nxMsg}
      <div class="pk-acts pk-big"><button type="button" class="btn pk-lg" data-prev="${p0.id}">${ico("eye", 18)} Ko'rish</button>
        <a class="btn pk-lg ${d.changed || d.stale ? "" : "primary"}" href="/api/paket/packages/${p0.id}/download" data-dl>${ico("download", 18)} Yuklab olish (.zip)</a>
        ${can.approve && p0.status === "tayyor" ? `<button type="button" class="btn pk-lg primary" data-ok="${p0.id}">${ico("check", 18)} Tasdiqlash</button>` : ""}
        ${can.approve && p0.status !== "qoralama" ? `<button type="button" class="btn pk-lg" data-rej="${p0.id}">Qaytarish</button>` : ""}</div>
      <details class="pk-det pk-sub"><summary><b>NEXTID'ga qanday yuklanadi?</b><span class="muted">4 qadam</span></summary>${pkNextidHelp(L, d.file_name)}</details>
      ${d.packages.length > 1 ? `<details class="pk-det pk-sub"><summary><b>Oldingi versiyalar</b><span class="muted">${d.packages.length - 1} ta</span></summary>
        ${pkTable([["Versiya", p => `<b>v${p.version}</b>${NX && NX.id === p.id ? " " + pkChip("NEXTID uchun", "ok") : ""}<small>${pkD(p.built_at)} · ${esc(p.by || "")} · ${pkSize(p.size)}${p.mode !== "xapi" ? ` · ${esc(pkMode(p.mode))}` : ""}</small>`],
          ["Holat", p => `${pkSt(p.status)}${p.approved_name ? `<small>${esc(p.approved_name)}, ${pkD(p.approved_at)}</small>` : ""}${p.note ? `<small class="pk-bad">Qaytarildi: ${esc(p.note)}</small>` : ""}`],
          ["", p => `<div class="pk-acts tight"><button type="button" class="btn sm ghost" data-prev="${p.id}">${ico("eye", 15)} Ko'rish</button>
             <a class="btn sm ghost" href="/api/paket/packages/${p.id}/download">${ico("download", 15)} Yuklab olish</a></div>`]], d.packages.slice(1))}
        <p class="pk-note">Oxirgi ${M.limits.keep} versiya (va tasdiqlangani) saqlanadi. Fayllar o'zgarmasa, qayta tayyorlash yangi versiya yaratmaydi.</p></details>` : ""}
    </div>` : "";
  /* --- pastki amallar paneli (telefonda ham doim ko'rinadi) --- */
  const fresh = p0 && !d.changed && !d.stale;
  const hint = !R.buildable ? "Avval kamida bitta fayl yuklang" : !p0 ? (miss.length ? `Hozircha: ${esc(miss.join(", "))} yo'q — keyin qo'shsangiz ham bo'ladi` : "Hammasi joyida — tayyorlash mumkin")
    : d.stale ? "Tasdiqlangan versiya eskirgan" : d.changed ? "Fayllar o'zgardi — qayta tayyorlang" : `v${p0.version} · ${esc(d.state_label)}`;
  const actbar = W || p0 ? `<div class="pk-actbar" id="pkAct"><span class="pk-act-i">${hint}</span>
      ${W ? `<button type="button" class="btn pk-lg ${fresh ? "" : "primary"}" id="pkBuild" ${M.player && R.buildable ? "" : "disabled"}>${ico("package", 18)} ${p0 ? "Qayta tayyorlash" : "Tayyorlash"}</button>` : ""}
      ${p0 ? `<a class="btn pk-lg ${fresh ? "primary" : ""}" href="/api/paket/packages/${p0.id}/download" data-dl>${ico("download", 18)} Yuklab olish</a>` : ""}</div>` : "";
  /* --- mashq va test (ixtiyoriy) --- */
  const practice = `<details class="card pk-card pk-det" id="pkPr" ${PK.prac ? "open" : ""}><summary><h3>Mashq va test qo'shish</h3><span class="muted">ixtiyoriy · ${nQ} savol · ${nX} mashq</span></summary>
      ${d.source_topic ? `<div id="pkTq"><p class="pk-note">Test savollari yuklanmoqda…</p></div>` : `<p class="pk-note">Test savollari ma'ruza mavzulari bo'yicha yuritiladi; bu darsga mashq qo'shishingiz mumkin (moslashtirish yoki saralash mashqi test sifatida baholanadi).</p>`}
      <h4>Mashqlar</h4><p class="pk-note" style="margin-top:0">Moslashtirish va saralash — test ichida baholanadi; kartochkalar — takrorlash uchun (baholanmaydi).</p>
      ${EX.length ? `<ul class="pk-exl">${EX.map(x => `<li><span>${pkChip(x.kind_label, x.status === "qoralama" ? "warn" : "info")} ${esc(x.title)} <small>${exN(x)}${x.status === "qoralama" ? " · qoralama" + (x.ai ? " (AI)" : "") + " — ko'rib saqlang" : ""}</small></span>
            ${W ? `<span class="pk-acts tight"><button type="button" class="btn sm ghost" data-exe="${x.id}">Tahrirlash</button><button type="button" class="btn sm ghost" data-exd="${x.id}" aria-label="Mashqni o'chirish" title="O'chirish">${ico("trash", 15)}</button></span>` : ""}</li>`).join("")}</ul>` : ""}
      ${W ? `<div class="pk-acts">${Object.entries(M.ex_kinds).map(([k, l]) => `<button type="button" class="btn sm" data-exn="${k}">${ico("plus", 15)} ${esc(l)}</button>`).join("")}
            ${M.ai ? `<button type="button" class="btn sm ghost" id="pkExAi" ${tx.ok ? "" : "disabled"} title="${tx.ok ? "Ma'ruza matnidan mashq qoralamalari" : "Avval ma'ruza matnini yuklang"}">${ico("spark", 15)} AI bilan mashq tuzish</button>` : ""}</div>` : ""}
    </details>`;
  /* --- talabaga ko'rinishi --- */
  const seen = `<details class="card pk-card pk-det"><summary><h3>Matn va slaydlar</h3><span class="muted">Talabaga shunday ko'rinadi</span></summary>
      <p class="pk-note" style="margin-top:0">Dars qismlari tartibi: ${d.blocks.map(b => b.type === "section" ? `<b>${esc(b.title)}</b>` : esc(b.title)).join(" → ") || "—"}</p>
      ${R.plan.ok ? `<h4>${esc(d.heading)}</h4><p class="pk-note" style="margin:0">Reja:</p><ol class="pk-plan">${d.plan.map(x => `<li>${esc(x)}</li>`).join("")}</ol>` : ""}
      ${d.text_html ? `<h4>Matn</h4><div class="pk-html">${d.text_html}</div>` : ""}
      ${kpItems.length ? `<h4>Asosiy xulosalar</h4><ul class="pk-plan">${kpItems.map(x => `<li>${esc(x)}</li>`).join("")}</ul>` : ""}
      ${d.refs.length ? `<h4>Foydalanilgan adabiyotlar</h4><ol class="pk-plan">${d.refs.map(x => `<li>${esc(x)}</li>`).join("")}</ol>` : ""}
      ${d.slides.length ? `<h4>Slaydlar (${d.slides.length} ta)</h4><div class="pk-slides">${d.slides.map((s, i) => `<div class="pk-slide"><b>${i + 1}. ${esc(s.title || "Slayd")}</b>${s.bullets.length ? `<ul>${s.bullets.slice(0, 4).map(b => `<li>${esc(b)}</li>`).join("")}</ul>` : ""}<small>${s.image ? "rasm · " : ""}${s.notes ? "ma'ruzachi izohi · " : ""}${s.audio ? "audio · " : ""}${s.caption ? esc(s.caption) : ""}</small></div>`).join("")}</div>` : ""}
      ${ag.ok ? `<h4>Topshiriq (${ag.n} ta savol)</h4><p class="pk-note" style="margin:0">«${esc(ag.text)}» — ${esc(ag.author)}</p><ol class="pk-plan">${ag.items.map(x => `<li>${esc(x)}</li>`).join("")}</ol>` : ""}
      ${d.quiz_preview.length ? `<h4>Test (${d.quiz_preview.length} ta savol)</h4><ol class="pk-plan">${d.quiz_preview.slice(0, 10).map(q => `<li>${esc(q.stem)}${q.type === "match" || q.type === "sort" ? ` <small style="display:inline">(${q.type === "match" ? "moslashtirish" : "saralash"})</small>` : ""}</li>`).join("")}</ol>${d.quiz_preview.length > 10 ? `<p class="pk-note">… yana ${d.quiz_preview.length - 10} ta</p>` : ""}` : ""}
    </details>`;
  el.innerHTML = `<div class="card pk-card pk-lesson">
      <div class="pk-item-h pk-lh"><h3 id="pkTh"><span class="pk-code">${esc(L.code)}</span> <span id="pkTn" class="${L.untitled ? "pk-un" : ""}">${L.untitled ? "Dars nomi kiritilmagan" : esc(d.topic.title)}</span>
          ${W ? `<button type="button" class="btn sm ghost pk-ic" id="pkTe" aria-label="Dars nomini o'zgartirish" title="Dars nomini o'zgartirish">${ico("pen", 15)}</button>` : ""}</h3>
        <span class="pk-lst">${pkChip(d.state_label, PK_LS[d.state])}${d.stale ? pkChip("eskirgan", "warn") : ""}</span></div>
      ${typeof dsTopicBar === "function" ? dsTopicBar(d, W) : ""}
      <p class="muted">${esc(L.kind_label)}${L.topic ? ` · ${L.topic}-mavzuga bog'langan` : ""}${L.untitled && W ? " · nomni qalam tugmasi bilan kiriting yoki Word yuklang — sarlavhasidan («3-MAVZU: …») o'zi olinadi" : L.title_src === "word" ? " · nom Word sarlavhasidan olindi" : ""}</p>
      ${W ? `<div class="pk-drop" id="pkDrop"><div class="pk-drop-ic">${ico("upload", 28)}</div>
          <div class="pk-drop-t"><b>Fayllarni shu yerga tashlang</b>
            <span>Word (ma'ruza), PDF yoki PPTX (taqdimot), MP4 (video), rasm (muqova), .srt/.vtt (subtitr) — bir nechtasini birga tashlash mumkin, har biri o'z joyiga o'zi tushadi</span></div>
          <label class="btn ${R.buildable ? "" : "primary"} pk-lg pk-file">${ico("upload", 18)} Fayl tanlash<input type="file" id="pkAny" multiple hidden accept=".docx,.pdf,.pptx,.txt,.mp4,.webm,.png,.jpg,.jpeg,.srt,.vtt"></label></div>
        <form class="pk-yt" id="pkVf"><label for="pkVu">YouTube havolasi <small>(video fayl o'rniga)</small></label>
          <input type="url" id="pkVu" placeholder="https://youtu.be/…" value="${esc(vd.link_src === "paket" ? vd.url || "" : "")}"><button class="btn sm">Saqlash</button></form>
        <ul class="pk-ups" id="pkUps" aria-live="polite"></ul>` : ""}
      ${tiles}
    </div>
    ${actbar}${result}${practice}${tx.ok || sl.ok ? seen : ""}`;
  /* --- kengaytirilgan sozlamalar: shu dars --- */
  const advL = $("#pkAdvL");
  if (advL) advL.innerHTML = W ? `<h3 class="pk-adv-h" style="margin-top:0">${esc(L.code)} darsi uchun</h3>
    <form id="pkSet"><div class="pk-form">
        <label>Dars turi (qaysi tizim uchun)<select name="mode">${Object.keys(M.modes).map(k => `<option value="${k}" ${k === S.mode ? "selected" : ""}>${esc(pkMode(k))}</option>`).join("")}</select></label>
        <label>Dars qachon tugallangan hisoblanadi<select name="completion">${Object.entries(M.completion).map(([k, l]) => `<option value="${k}" ${k === S.completion ? "selected" : ""}>${esc(l)}</option>`).join("")}</select></label>
        <label>O'tish bali, %<input type="number" name="mastery" min="0" max="100" value="${S.mastery}"></label>
        <label>Testdagi savollar soni (0 — hammasi)<input type="number" name="quiz_n" min="0" max="200" value="${S.quiz_n}"></label>
        <label>Urinishlar soni (0 — cheksiz)<input type="number" name="attempts" min="0" max="20" value="${S.attempts}"></label>
        <label>Ko'rinish<select name="layout">${Object.entries(M.layouts).map(([k, l]) => `<option value="${k}" ${k === S.layout ? "selected" : ""}>${esc(l)}</option>`).join("")}</select></label>
        <label>Video (fayl ham, havola ham bo'lsa)<select name="video_source">${Object.entries(M.video_sources).map(([k, l]) => `<option value="${k}" ${k === S.video_source ? "selected" : ""}>${esc(l)}</option>`).join("")}</select></label>
        <label class="cb"><input type="checkbox" name="shuffle" ${S.shuffle ? "checked" : ""}> Savollarni aralashtirish</label>
        <label class="cb"><input type="checkbox" name="show_feedback" ${S.show_feedback ? "checked" : ""}> Javobdan keyin izoh ko'rsatish</label>
      </div>
      <fieldset class="pk-fs"><legend>Dars qismlari (belgilanmagani darsga kirmaydi)</legend><div class="pk-checks">${Object.entries(M.blocks).map(([k, l]) => `<label><input type="checkbox" name="b_${k}" ${S.blocks[k] ? "checked" : ""}> ${esc(l)}</label>`).join("")}</div></fieldset>
      <div class="pk-acts"><button class="btn sm">Sozlamani saqlash</button>${Object.keys(d.override).length ? `<button type="button" class="btn sm ghost" id="pkSr">Standartga qaytarish</button>` : ""}
        <span class="pk-note" style="margin:0">${Object.keys(d.override).length ? "Bu dars uchun alohida sozlama" : "Standart sozlama"}</span></div></form>
    <div class="pk-advg">
      <div><h4>Muqova</h4><p class="pk-note" style="margin-top:0">${cv.ok ? `${cv.image ? `fon rasmi — ${{dars: "shu dars uchun yuklangan", kurs: "kurs muqovasi", standart: "bo'lim standarti"}[cv.src]}` : "rasmsiz (institut rangi)"} · muallif: ${cv.author ? esc(cv.author) : "—"}${cv.custom ? " (tahrirlangan)" : ""}` : "O'chirilgan («Dars qismlari»da yoqish mumkin)"}</p>
        <div class="pk-acts">${cv.image ? `<img class="pk-thumb muqova" src="/api/paket/assets/${cv.image}" alt="Muqova">` : ""}
          <label class="btn sm pk-file">${ico("upload", 15)} Dars muqovasi (.png, .jpg)<input type="file" accept=".png,.jpg,.jpeg" hidden id="pkCf"></label>
          ${cv.src === "dars" ? `<button type="button" class="btn sm ghost" data-del="${cv.image}">Olib tashlash</button>` : ""}</div>
        <form class="pk-inline" id="pkCa"><label class="pk-sr" for="pkCu">Muallif</label><input type="text" id="pkCu" maxlength="120" placeholder="Muallif (F.I.Sh.)" value="${esc(cv.author || "")}"><button class="btn sm">Saqlash</button>${cv.custom ? `<button type="button" class="btn sm ghost" id="pkCr">Standart</button>` : ""}</form></div>
      <div><h4>Video: muqova va subtitr</h4>${vd.file ? `<p class="pk-note" style="margin-top:0">Video muqovasi — video boshlanishidan oldin ko'rinadigan rasm. Subtitr — tayyor .srt yoki .vtt fayl.</p>
        <div class="pk-acts"><label class="btn sm pk-file">${ico("upload", 15)} Video muqovasi (.png, .jpg)<input type="file" accept=".png,.jpg,.jpeg" hidden id="pkVp"></label>
          <label class="pk-sr" for="pkVl">Subtitr tili</label><select id="pkVl" class="pk-sel">${Object.entries(M.sub_langs).map(([k, l]) => `<option value="${k}">${esc(l)}</option>`).join("")}</select>
          <label class="btn sm pk-file">${ico("upload", 15)} Subtitr (.srt, .vtt)<input type="file" accept=".vtt,.srt,text/vtt" hidden id="pkVs"></label></div>` : `<p class="pk-note" style="margin-top:0">Video muqovasi va subtitr faqat yuklangan video fayl bilan ishlaydi (YouTube'da o'zining subtitri bor).</p>`}</div>
      <div><h4>Matn</h4><div class="pk-acts"><button type="button" class="btn sm" id="pkTt">Matnni qo'lda joylashtirish</button>
          <button type="button" class="btn sm" id="pkIb">${ico("upload", 15)} Matnga rasm qo'shish</button>
          <button type="button" class="btn sm" id="pkAe">Topshiriq savollarini tahrirlash</button></div>
        <p class="pk-note">Asosiy xulosalar: ${R.keypoints.ok ? `${R.keypoints.n} ta tasdiqlangan` : kpDraft.length ? `${kpDraft.length} ta qoralama — tahrirlab tasdiqlang` : "yo'q (ixtiyoriy)"}.</p>
        <div class="pk-acts"><button type="button" class="btn sm" id="pkKpEd">Asosiy xulosalarni tahrirlash</button>${M.ai ? `<button type="button" class="btn sm ghost" id="pkKpAi" ${tx.ok ? "" : "disabled"}>${ico("spark", 15)} AI bilan xulosa tuzish</button>` : ""}</div>
        ${(ag.warnings || []).map(w => `<p class="pk-note">${esc(w)}</p>`).join("")}</div>
      <div><h4>Taqdimot</h4><div class="pk-acts">${sl.n ? `<button type="button" class="btn sm" id="pkSe">Slayd izohlari va audio${sl.captions || sl.audio ? ` (${sl.captions} izoh, ${sl.audio} audio)` : ""}</button>` : `<span class="pk-note" style="margin:0">Slayd izohi va audiosi — taqdimot yuklangach.</span>`}
          ${d.decks.length ? `<label class="pk-sr" for="pkDk">«Taqdimot» bo'limidan</label><select id="pkDk" class="pk-sel"><option value="0">«Taqdimot» bo'limidagi tayyor taqdimot…</option>${d.decks.map(x => `<option value="${x.id}" ${x.id === sl.deck_id ? "selected" : ""}>${esc(x.title || "Taqdimot #" + x.id)}${x.slides ? ` (${x.slides} slayd)` : ""}</option>`).join("")}</select>` : ""}</div></div>
    </div>
    <h4>Yuklangan fayllar</h4>
    ${assets.length ? pkTable([["Fayl", a => a.purpose === "rasm" ? `${esc(a.caption || a.name)} <small>matn ichidagi rasm · ${pkSize(a.size)}</small>` : `${esc(a.name)} <small>${esc(a.kind)} · ${pkSize(a.size)} · ${pkD(a.ts)}${a.demo ? " · namuna" : ""}</small>${a.caption ? `<small>${esc(a.caption)}</small>` : ""}`],
         ["Nima uchun", a => esc({matn: "Ma'ruza matni", taqdimot: "Taqdimot", slayd: "Slayd rasmi", fayl: "Qo'shimcha fayl", rasm: "Matn ichidagi rasm", video: "Video", subs: "Subtitr",
                            poster: "Video muqovasi", muqova: "Dars muqovasi", audio: "Slayd audiosi"}[a.purpose] || a.purpose)],
         ["", a => `<div class="pk-acts tight"><a class="btn sm ghost" href="/api/paket/assets/${a.id}" aria-label="Faylni yuklab olish" title="Yuklab olish">${ico("download", 15)}</a><button type="button" class="btn sm ghost" data-del="${a.id}" aria-label="Faylni o'chirish" title="O'chirish">${ico("trash", 15)}</button></div>`]], assets) : `<p class="pk-note">Hali fayl yuklanmagan.</p>`}
    <div class="pk-acts"><label class="btn sm pk-file">${ico("upload", 15)} Qo'shimcha fayl (talaba yuklab oladi: .pdf, .docx, .xlsx…)<input type="file" accept=".pdf,.docx,.pptx,.xlsx,.png,.jpg,.jpeg" hidden id="pkFf"></label>
      ${L.custom && !L.default ? `<button type="button" class="btn sm ghost" id="pkLd">${ico("trash", 15)} Darsni ro'yxatdan o'chirish</button>` : ""}</div>
    <p class="pk-note">Cheklovlar: bitta fayl ≤ ${M.limits.asset_mb} MB · video ≤ ${M.limits.video_mb} MB · slayd audiosi ≤ ${M.limits.audio_mb} MB · tayyor dars ≤ ${M.limits.package_mb} MB (video fayl bilan ≤ ${M.limits.package_video_mb} MB). YouTube videosi YouTube'da qoladi (darsga faqat havola kiradi). Fayl nomi: <span class="pk-mono">${esc(d.file_name)}</span></p>` : "";
  const A = advL || el;                                    /* kengaytirilgan sozlamalardagi elementlar */
  /* --- bitta yuklash maydoni: fayl turi tarkibidan aniqlanib, o'z joyiga tushadi --- */
  const ups = el.querySelector("#pkUps");
  const drawUps = () => { if (!ups) return; const U = PK.ups && PK.ups.key === key ? PK.ups.rows : [];
    ups.innerHTML = U.map(r => `<li class="${r.state}"><span class="n">${r.state === "ok" ? ico("checkc", 16) : r.state === "err" ? ico("alert", 16) : ico("file", 16)} ${esc(r.name)}</span>
      ${r.state === "up" ? `<span class="pk-bar"><i style="width:${Math.round(r.pct * 100)}%"></i></span><small>${r.pct >= 1 ? "qayta ishlanmoqda…" : Math.round(r.pct * 100) + "%"}</small>` : `<small>${r.state === "wait" ? "navbatda" : esc(r.msg)}</small>`}</li>`).join(""); };
  drawUps();
  const isImg = f => /\.(png|jpe?g)$/i.test(f.name) || /^image\/(png|jpeg)$/.test(f.type);
  const isVid = f => /\.(mp4|webm)$/i.test(f.name) || /^video\//.test(f.type);
  const handleFiles = async (list, force) => {
    let files = [...list]; if (!files.length || PK.busy) return;
    let imgAs = force || null;
    if (!force && files.some(isImg)) { imgAs = await pkAskImage(files.filter(isImg)); if (!imgAs) files = files.filter(f => !isImg(f)); }
    if (!files.length) return;
    files.sort((a, b) => isVid(a) - isVid(b));          /* video (eng kattasi) — oxirida */
    PK.busy = true;
    PK.ups = {key, rows: files.map(f => ({name: f.name, state: "wait", pct: 0, msg: ""}))}; drawUps();
    let okN = 0, title = null;
    try {
      for (let i = 0; i < files.length; i++) {
        const f = files[i], row = PK.ups.rows[i], lim = isVid(f) ? M.limits.video_mb : M.limits.asset_mb;
        if (!f.size) { row.state = "err"; row.msg = "Fayl bo'sh"; drawUps(); continue; }
        if (f.size > lim * 1048576) { row.state = "err"; row.msg = `Fayl juda katta (${pkSize(f.size)}) — chegara ${lim} MB${isVid(f) ? ". Uzun video uchun YouTube havolasidan foydalaning" : ""}`; drawUps(); continue; }
        row.state = "up"; drawUps();
        const url = as => `${base}/upload?name=${encodeURIComponent(f.name)}${as ? "&as=" + as : ""}`;
        let r = await pkSend(url(force || (isImg(f) ? imgAs : "")), f, p => { row.pct = p; drawUps(); });
        if (r.status === 409 && r.data?.detail?.ambiguous) { const ch = await pkAskImage([f]); if (ch) { row.pct = 0; r = await pkSend(url(ch), f, p => { row.pct = p; drawUps(); }); } }
        if (r.status === 401) { showLogin(); return; }
        if (r.ok) { row.state = "ok"; row.msg = pkUpDesc(r.data); okN++; if (r.data.title_set) title = r.data.title; }
        else { row.state = "err"; row.msg = pkErrMsg(r.data); }
        drawUps();
      }
    } finally { PK.busy = false; }
    const bad = files.length - okN;
    toast(title ? `Dars nomi Word sarlavhasidan olindi: «${title}»` : bad ? `Yuklandi: ${okN} ta · yuklanmadi: ${bad} ta — sababi ro'yxatda` : `Yuklandi: ${okN} ta fayl`);
    if (okN) await reload();
  };
  const any = el.querySelector("#pkAny");
  if (any) any.onchange = () => { const fs = [...any.files]; any.value = ""; handleFiles(fs); };
  const dz = el.querySelector("#pkDrop");
  if (dz) {
    const stop = e => { e.preventDefault(); e.stopPropagation(); };
    el.ondragover = stop; el.ondrop = stop;                /* maydondan tashqariga tushsa — brauzer faylni ochib yubormasin */
    dz.ondragenter = dz.ondragover = e => { stop(e); dz.classList.add("over"); };
    dz.ondragleave = e => { if (!dz.contains(e.relatedTarget)) dz.classList.remove("over"); };
    dz.ondrop = e => { stop(e); dz.classList.remove("over"); handleFiles(e.dataTransfer?.files || []); };
  }
  el.querySelectorAll("[data-up]").forEach(i => i.onchange = () => { const fs = [...i.files]; i.value = ""; handleFiles(fs, i.dataset.up); });
  el.querySelectorAll("[data-rm]").forEach(b => b.onclick = async () => {
    const k = b.dataset.rm, post = u => pkApi(u, {});
    if (!confirm({text: "Ma'ruza matni olib tashlansinmi?", slides: "Taqdimot olib tashlansinmi?", video: "Video olib tashlansinmi?"}[k])) return;
    let r = null;
    if (k === "text") r = await post(`/api/paket/assets/${d.text_asset}/delete`);
    else if (k === "slides") {
      for (const a of assets.filter(a => a.purpose === "taqdimot" || a.purpose === "slayd")) r = await post(`/api/paket/assets/${a.id}/delete`);
      if (sl.deck_id) r = await pkApi(`${base}/deck`, {deck_id: 0});
    } else {
      if (vd.file) r = await post(`/api/paket/assets/${vd.file.id}/delete`);
      if (vd.link_src === "paket") r = await pkApi(`${base}/video`, {url: ""});
    }
    if (r) { toast("Olib tashlandi"); reload(); }
  });
  el.querySelector("#pkVf")?.addEventListener("submit", async e => {
    e.preventDefault();
    const r = await pkApi(`${base}/video`, {url: el.querySelector("#pkVu").value.trim()});
    if (r) { toast(r.url ? "YouTube havolasi saqlandi" : "Havola olib tashlandi"); reload(); }
  });
  /* --- dars nomi: joyida tahrirlash --- */
  el.querySelector("#pkTe")?.addEventListener("click", () => {
    const h = el.querySelector("#pkTh");
    h.innerHTML = `<span class="pk-code">${esc(L.code)}</span><form class="pk-inline pk-tform" id="pkTfm"><label class="pk-sr" for="pkTi">Dars nomi</label>
      <input type="text" id="pkTi" maxlength="200" value="${L.untitled ? "" : esc(d.topic.title)}" placeholder="Masalan: Raqamli iqtisodiyot asoslari"><button class="btn sm primary">Saqlash</button><button type="button" class="btn sm ghost" id="pkTx0">Bekor qilish</button></form>`;
    const inp = h.querySelector("#pkTi"); inp.focus(); inp.select();
    h.querySelector("#pkTx0").onclick = () => pkTopicPanel(el);
    h.querySelector("#pkTfm").onsubmit = async e => { e.preventDefault();
      const r = await pkApi(`${base}/title`, {title: inp.value.trim()}); if (r) { toast(inp.value.trim() ? "Dars nomi saqlandi" : "Dars nomi avtomatik olinadi"); reload(); } };
  });
  /* --- «ISFT shablonida taqdimot yaratish»: yuklangan ma'ruza matnidan (qayta yuklash shart emas) --- */
  el.querySelector("#pkDkNew")?.addEventListener("click", async e => {
    const btn = e.currentTarget; btn.disabled = true; toast("Taqdimot tuzilmoqda… (ma'ruza matnidan)");
    try {
      const r = await pkApi(`${base}/deck/create`, {});
      if (r) { toast(`Taqdimot yaratildi: ${r.slides} slayd — «Taqdimot» bo'limida tahrirlash mumkin`); reload(); }
    } finally { if (btn.isConnected) btn.disabled = false; }
  });
  /* --- Tayyorlash → ko'rish oynasi --- */
  el.querySelector("#pkBuild")?.addEventListener("click", async e => {
    const btn = e.currentTarget; btn.disabled = true;
    toast("Dars tayyorlanmoqda…");
    const r = await pkApi(`${base}/build`, {});
    if (!r) { if (btn.isConnected) btn.disabled = false; return; }
    const p = r.package;
    toast(r.unchanged ? `O'zgarish yo'q — v${p.version} amalda` : `Tayyor: v${p.version} (${pkSize(p.size)})${p.status === "tayyor" ? " — bo'limga yuborildi" : ""}`);
    await reload();
    pkPreview(p, `${L.code} — ${d.topic.title}`);
  });
  const repaint = async () => { PK.meta = await pkApi("/api/paket/meta"); renderPaket("mavzular"); };
  el.querySelectorAll("[data-prev]").forEach(b => b.onclick = () => pkPreview(d.packages.find(p => p.id === +b.dataset.prev), `${L.code} — ${d.topic.title}`));
  if (typeof dsTopicBind === "function") dsTopicBind(el, d);
  const gAct = typeof dsGateFetch === "function" ? dsGateFetch : pkApi;     /* to'xtatuvchi izohlar to'sig'i (dars.js) — sabab bilan aylanib o'tish */
  el.querySelector("#pkSubmit")?.addEventListener("click", async () => { const r = await gAct(`/api/paket/packages/${p0.id}/action`, {action: "submit"}); if (r) { toast("Bo'limga yuborildi"); reload(); } });
  el.querySelectorAll("[data-ok]").forEach(b => b.onclick = async () => { b.disabled = true; const r = await gAct(`/api/paket/packages/${b.dataset.ok}/action`, {action: "approve"});
    if (r) { toast(`Tasdiqlandi${r.monitoring ? ` · kontent monitoringida ${r.monitoring} ta material yopildi` : ""}`); repaint(); } else b.disabled = false; });
  el.querySelectorAll("[data-rej]").forEach(b => b.onclick = () => pkModal("Darsni qaytarish", `<label>Sabab (o'qituvchiga ko'rinadi)<textarea id="pkRn" rows="4" style="min-height:90px" placeholder="Masalan: 3-slayddagi jadval o'qilmaydi; videoda ovoz yo'q"></textarea></label>`, async m => {
    const r = await pkApi(`/api/paket/packages/${b.dataset.rej}/action`, {action: "reject", note: m.querySelector("#pkRn").value.trim()});
    if (r) { toast("Qaytarildi"); repaint(); return true; }
  }, "Qaytarish"));
  el.querySelector("#pkNc")?.addEventListener("click", async () => { const t = el.querySelector("#pkNn").textContent;
    try { await navigator.clipboard.writeText(t); toast("Nusxalandi: " + t); } catch (e) { toast(t); } });
  /* --- mashq va test (ixtiyoriy) --- */
  const pr = el.querySelector("#pkPr");
  if (pr) pr.ontoggle = () => { PK.prac = pr.open; if (pr.open) loadQuiz(); };
  el.querySelector("#pkPrOpen")?.addEventListener("click", () => { pr.open = true; pr.scrollIntoView({block: "start", behavior: "smooth"}); });
  let quizLoaded = false;
  const loadQuiz = () => { const q = el.querySelector("#pkTq"); if (q && !quizLoaded) { quizLoaded = true; pkQuizBox(q, d, () => pkTopicPanel(el)); } };
  if (PK.prac) loadQuiz();
  el.querySelectorAll("[data-exn]").forEach(b => b.onclick = () => pkExEdit(base, {kind: b.dataset.exn}, L, () => pkTopicPanel(el)));
  el.querySelectorAll("[data-exe]").forEach(b => b.onclick = () => pkExEdit(base, EX.find(x => x.id === +b.dataset.exe), L, () => pkTopicPanel(el)));
  el.querySelectorAll("[data-exd]").forEach(b => b.onclick = async () => { if (!confirm("Mashq o'chirilsinmi?")) return;
    const r = await pkApi(`/api/paket/exercises/${b.dataset.exd}/delete`, {}); if (r) { toast("O'chirildi"); pkTopicPanel(el); } });
  el.querySelector("#pkExAi")?.addEventListener("click", async e => {
    const btn = e.currentTarget, sort = confirm("Saralash mashqi ham tayyorlansinmi?\n(OK — moslashtirish + kartochkalar + saralash; Bekor qilish — saralashsiz)");
    btn.disabled = true; toast("AI matnni o'qiyapti… (faqat dars matni yuboriladi)");
    try {
      const r = await pkApi(`${base}/exercises/ai`, {sort});
      if (r) { toast(`AI: ${r.exercises.length} ta mashq qoralamasi${r.dropped ? ` · matnga asoslanmagan ${r.dropped} ta band tashlandi` : ""} — tahrirlab saqlang`); pkTopicPanel(el); }
    } finally { if (btn.isConnected) btn.disabled = false; }
  });
  /* ================= kengaytirilgan sozlamalar (shu dars) ================= */
  A.querySelector("#pkLd")?.addEventListener("click", async () => {
    if (!confirm(`${L.code} darsi ro'yxatdan o'chirilsinmi? (Fayllar va tayyorlangan versiyalar saqlanib qoladi)`)) return;
    const r = await pkApi(`/api/paket/courses/${PK.cid}/lessons/${PK.topic}/delete`, {}); if (r) { toast("O'chirildi"); PK.topic = 1; reload(); }
  });
  A.querySelector("#pkIb")?.addEventListener("click", () => pkModal(`${L.code}: matnga rasm qo'shish`, `<label>Rasm (.png, .jpg)<input type="file" id="pkIf" accept=".png,.jpg,.jpeg"></label>
      <label>Izoh (ixtiyoriy)<input type="text" id="pkIc" maxlength="300" placeholder="1.3-rasm. …"></label>
      <p class="pk-note">Rasm ma'ruza matnining oxiriga qo'shiladi. Matn o'rtasiga qo'yish uchun rasmni Word faylning o'ziga joylab, Word'ni qayta yuklang.</p>`, async m => {
    const f = m.querySelector("#pkIf").files[0]; if (!f) { toast("Rasm tanlang"); return false; }
    const r = await pkUpload(`${base}/images`, f, `&caption=${encodeURIComponent(m.querySelector("#pkIc").value.trim())}`);
    if (r) { toast("Rasm qo'shildi"); reload(); return true; }
  }, "Yuklash"));
  const kpEdit = () => {
    const cur = (kpDraft.length ? kpDraft.map(x => x.text) : kpItems);
    const quotes = kpDraft.filter(x => x.quote).map(x => `<li>${esc(x.text)}<small>«${esc(x.quote)}»</small></li>`).join("");
    const bg = pkModal(`${L.code}: asosiy xulosalar`, `<label>Har qatorda bitta xulosa (4–7 ta tavsiya etiladi)<textarea id="pkKx" rows="9">${esc(cur.join("\n"))}</textarea></label>
      ${quotes ? `<details class="pk-det"><summary>AI qoralamasi — matndagi iqtiboslar</summary><ol class="pk-plan">${quotes}</ol></details>` : ""}
      <p class="pk-note">Faqat tasdiqlangan xulosalar darsga kiradi. <button type="button" class="btn sm ghost" data-kpd>Qoralama sifatida saqlash</button> <button type="button" class="btn sm ghost" data-kpc>Hammasini o'chirish</button></p>`, async m => {
      const items = m.querySelector("#pkKx").value.split("\n").map(x => x.trim()).filter(Boolean);
      const r = await pkApi(`${base}/keypoints`, {items, approve: true}); if (r) { toast("Xulosalar tasdiqlandi — darsga kiradi"); reload(); return true; }
    }, "Tasdiqlash", true);
    bg.querySelector("[data-kpd]").onclick = async () => { const items = bg.querySelector("#pkKx").value.split("\n").map(x => x.trim()).filter(Boolean);
      const r = await pkApi(`${base}/keypoints`, {items, approve: false}); if (r) { toast("Qoralama saqlandi"); bg.remove(); reload(); } };
    bg.querySelector("[data-kpc]").onclick = async () => { if (!confirm("Xulosalar o'chirilsinmi?")) return;
      const r = await pkApi(`${base}/keypoints`, {items: [], clear: true}); if (r) { toast("O'chirildi"); bg.remove(); reload(); } };
  };
  A.querySelector("#pkKpEd")?.addEventListener("click", kpEdit);
  A.querySelector("#pkKpAi")?.addEventListener("click", async e => {
    const btn = e.currentTarget; btn.disabled = true; toast("AI matnni o'qiyapti… (faqat dars matni yuboriladi)");
    try {
      const r = await pkApi(`${base}/keypoints/ai`, {});
      if (r) { toast(`AI: ${r.draft.items.length} ta xulosa (qoralama)${r.dropped ? ` · matnga asoslanmagan ${r.dropped} ta tashlandi` : ""}`); await reload(); $("#pkKpEd")?.click(); }
    } finally { if (btn.isConnected) btn.disabled = false; }
  });
  A.querySelector("#pkTt")?.addEventListener("click", () => pkModal(`${L.code}: ma'ruza matni`, `<label>Matn («Reja:», raqamli sarlavhalar va «Foydalanilgan adabiyotlar» bo'limi o'zi aniqlanadi)<textarea id="pkTx" rows="14"></textarea></label>`, async m => {
    const r = await pkApi(`${base}/text/paste`, {text: m.querySelector("#pkTx").value});
    if (r) { toast(r.title_set ? `Matn saqlandi · dars nomi: «${r.title}»` : `Matn saqlandi: ${fmt(r.chars)} belgi`); reload(); return true; }
  }, "Saqlash", true));
  const ff = A.querySelector("#pkFf");
  if (ff) ff.onchange = async () => { const f = ff.files[0]; if (!f) return; const r = await pkUpload(`${base}/files`, f); if (r) { toast("Fayl qo'shildi"); reload(); } };
  A.querySelector("#pkDk")?.addEventListener("change", async e => { const r = await pkApi(`${base}/deck`, {deck_id: +e.target.value}); if (r) { toast(r.deck_id ? "Taqdimot biriktirildi" : "Uzildi"); reload(); } });
  /* --- muqova, video muqovasi / subtitr, slayd izohi va audiosi, topshiriq --- */
  const upTo = (sel, url, msg, extra, mb) => { const i = A.querySelector(sel); if (i) i.onchange = async () => { const f = i.files[0]; if (!f) return;
    const r = await pkUpload(url, f, extra ? extra() : "", mb); i.value = ""; if (r) { toast(typeof msg === "function" ? msg(r) : msg); reload(); } }; };
  upTo("#pkCf", `${base}/cover`, "Muqova saqlandi");
  upTo("#pkVp", `${base}/video/poster`, "Video muqovasi saqlandi");
  upTo("#pkVs", `${base}/video/captions`, r => `Subtitr saqlandi: ${r.cues} yozuv`, () => `&lang=${encodeURIComponent(A.querySelector("#pkVl").value)}`, M.limits.subs_mb);
  A.querySelector("#pkCa")?.addEventListener("submit", async e => { e.preventDefault();
    const r = await pkApi(`${base}/cover/meta`, {author: A.querySelector("#pkCu").value.trim()}); if (r) { toast("Muallif saqlandi"); reload(); } });
  A.querySelector("#pkCr")?.addEventListener("click", async () => { const r = await pkApi(`${base}/cover/meta`, {author: null}); if (r) { toast("Standart muallif (kurs o'qituvchisi)"); reload(); } });
  A.querySelector("#pkSe")?.addEventListener("click", () => {
    // audio yuklash/olib tashlash oynani qayta chizadi — yozilgan, hali saqlanmagan izohlar yo'qolmasin: qiymatlar yangi oynaga ko'chiriladi (PK.capDraft)
    const draft = PK.capDraft && PK.capDraft.base === base ? PK.capDraft.caps : null; PK.capDraft = null;
    const capVal = (n, saved) => draft && draft[n] != null ? draft[n] : saved;
    const bg = pkModal(`${L.code}: slayd izohlari va audio`, `<p class="pk-note" style="margin-top:0">Izoh slayd ostida ko'rinadi; audio (.mp3, .m4a, .ogg, .wav ≤ ${M.limits.audio_mb} MB) — slayd bilan birga tinglanadi. Izohlar «Izohlarni saqlash» bilan, audio darhol saqlanadi (audio yuklanganda yozilgan izohlar oynada qoladi). Taqdimot almashtirilsa, izoh va audio slayd tartib raqami bo'yicha qoladi.</p>
      <div class="pk-srows">${d.slides.map((s, i) => { const a = d.slide_audio[i + 1]; return `<div class="pk-srow"><b>${i + 1}</b><div><small>${esc(s.title || "Slayd " + (i + 1))}</small>
        <input type="text" maxlength="300" data-cap="${i + 1}" value="${esc(capVal(i + 1, s.caption))}" placeholder="Izoh (ixtiyoriy)" aria-label="${i + 1}-slayd izohi">
        <span class="pk-acts tight" style="justify-content:flex-start">${a ? `<small>${ico("checkc", 13)} ${esc(a.name)}</small><button type="button" class="btn sm ghost" data-adel="${a.id}">Audioni olib tashlash</button>` : ""}
          <label class="btn sm ghost pk-file">${ico("upload", 15)} Audio<input type="file" accept=".mp3,.m4a,.ogg,.wav,audio/*" hidden data-aud="${i + 1}"></label></span></div></div>`; }).join("")}</div>`, async m => {
      const captions = {}; m.querySelectorAll("[data-cap]").forEach(i => { captions[i.dataset.cap] = i.value.trim(); });
      const r = await pkApi(`${base}/slides/meta`, {captions}); if (r) { toast(`Izohlar saqlandi: ${Object.keys(r.captions).length} ta`); reload(); return true; }
    }, "Izohlarni saqlash", true);
    const typed = () => { const o = {}; bg.querySelectorAll("[data-cap]").forEach(i => { o[i.dataset.cap] = i.value; }); return o; };
    const dirty = () => d.slides.some((s, i) => (typed()[i + 1] ?? "").trim() !== (s.caption || ""));
    const reopen = async () => { const caps = typed(); bg.remove(); await reload(); PK.capDraft = {base, caps}; $("#pkSe")?.click(); PK.capDraft = null; };
    bg.querySelectorAll("[data-aud]").forEach(i => i.onchange = async () => { const f = i.files[0]; if (!f) return;
      const r = await pkUpload(`${base}/slides/${i.dataset.aud}/audio`, f, "", M.limits.audio_mb); if (r) { toast(`${i.dataset.aud}-slaydga audio saqlandi${dirty() ? " — izohlar hali saqlanmagan" : ""}`); await reopen(); } });
    bg.querySelectorAll("[data-adel]").forEach(b => b.onclick = async () => { const r = await pkApi(`/api/paket/assets/${b.dataset.adel}/delete`, {}); if (r) { toast(`Audio olib tashlandi${dirty() ? " — izohlar hali saqlanmagan" : ""}`); await reopen(); } });
  });
  A.querySelector("#pkAe")?.addEventListener("click", () => {
    const bg = pkModal(`${L.code}: topshiriq savollari`, `<label>Har qatorda bitta savol yoki topshiriq (ko'pi bilan ${ag.max || 60} ta)<textarea id="pkAq" rows="10">${esc(ag.items.join("\n"))}</textarea></label>
      <p class="pk-note">${ag.manual ? "Hozir: qo'lda kiritilgan ro'yxat." : `Hozir: avtomatik — ma'ruza matnidagi «Savollar» / «Nazorat savollari» / «Topshiriqlar» bo'limidan (${ag.found} ta).`} Topshiriq matni («${esc(ag.text)}») va imzo — bo'lim sozlamalarida; o'qituvchi rasmi — «Butun kurs uchun» qismida.
        ${ag.manual ? `<button type="button" class="btn sm ghost" data-aauto>Matndan olish (avtomatik)</button>` : ""}</p>`, async m => {
      const r = await pkApi(`${base}/assignment`, {questions: m.querySelector("#pkAq").value.split("\n").map(x => x.trim()).filter(Boolean)});
      if (r) { toast(`Topshiriq savollari saqlandi: ${r.questions.length} ta`); reload(); return true; }
    }, "Saqlash", true);
    bg.querySelector("[data-aauto]")?.addEventListener("click", async () => { const r = await pkApi(`${base}/assignment`, {questions: null}); if (r) { toast("Savollar matndan olinadi"); bg.remove(); reload(); } });
  });
  A.querySelectorAll("[data-del]").forEach(b => b.onclick = async () => {
    if (!confirm("Fayl o'chirilsinmi?")) return;
    const r = await pkApi(`/api/paket/assets/${b.dataset.del}/delete`, {}); if (r) { toast("O'chirildi"); reload(); }
  });
  A.querySelector("#pkSet")?.addEventListener("submit", async e => {
    e.preventDefault(); if (!W) return;
    const f = e.currentTarget, blocks = {};
    Object.keys(M.blocks).forEach(k => blocks[k] = f.elements["b_" + k].checked);
    const r = await pkApi(`${base}/settings`, {layout: f.elements.layout.value, mode: f.elements.mode.value, completion: f.elements.completion.value, mastery: +f.elements.mastery.value, video_source: f.elements.video_source.value,
      quiz_n: +f.elements.quiz_n.value, attempts: +f.elements.attempts.value, shuffle: f.elements.shuffle.checked, show_feedback: f.elements.show_feedback.checked, blocks});
    if (r) { toast("Sozlama saqlandi"); reload(); }
  });
  A.querySelector("#pkSr")?.addEventListener("click", async () => { const r = await pkApi(`${base}/settings`, {reset: true}); if (r) { toast("Standart sozlama"); reload(); } });
}

/* ---------- dars ichida Test bank savollari (testbank.js funksiyalari: tbApi, tbQCard, tbEdit, tbQAction) — alohida bo'limga o'tish shart emas ---------- */
async function pkQuizBox(box, d, refresh) {
  const cid = PK.cid, tno = d.source_topic, W = d.can.write;
  if (typeof TB !== "object" || typeof tbQCard !== "function" || typeof tbApi !== "function") { box.innerHTML = ""; return; }
  let items, TM;
  try {
    if (!TB.meta) TB.meta = await tbApi("/api/testbank/meta");
    TM = TB.meta; TB.cid = cid;                                 /* tbEdit / tbQAction shu kursga yozadi */
    items = (await tbApi(`/api/testbank/courses/${cid}/topics/${tno}/questions`)).items;
  } catch (e) { if (e?.message !== "auth") box.innerHTML = `<p class="pk-note">Test savollarini yuklab bo'lmadi.</p>`; return; }
  const cnt = st => items.filter(q => q.status === st).length;
  const nA = cnt("tasdiqlandi"), nR = cnt("tekshiruvda"), nD = cnt("qoralama"), nX = cnt("rad_etildi");
  const sendable = items.filter(q => q.can?.submit).length;
  box.innerHTML = `<h4 style="margin-top:0">Test savollari <span class="muted">· ${tno}-mavzu (Test bank bilan umumiy)</span></h4>
    <p class="pk-note" style="margin-top:0">Darsga faqat <b>bo'lim tasdiqlagan</b> savollar kiradi: savol qo'shing → «Tekshiruvga yuborish» → Masofaviy ta'lim bo'limi tasdiqlaydi → «Tayyorlash»ni qayta bosing.</p>
    <div class="pk-acts">${pkChip(`Tasdiqlangan ${nA}`, nA ? "ok" : "")}${nR ? pkChip(`Tekshiruvda ${nR}`, "info") : ""}${nD ? pkChip(`Qoralama ${nD}`) : ""}${nX ? pkChip(`Rad etilgan ${nX}`, "bad") : ""}</div>
    ${W ? `<div class="pk-acts"><button type="button" class="btn sm" id="pkQa">${ico("plus", 15)} Savol qo'shish</button>
      ${TM.caps.generate && TM.ai.on ? `<button type="button" class="btn sm ghost" id="pkQg" ${d.ready.text.ok ? "" : "disabled"} title="${d.ready.text.ok ? "Ma'ruza matnidan 10 ta savol qoralamasi" : "Avval ma'ruza matnini yuklang"}">${ico("spark", 15)} AI bilan 10 ta savol tuzish</button>` : ""}
      ${sendable ? `<button type="button" class="btn sm primary" id="pkQs">Tekshiruvga yuborish (${sendable})</button>` : ""}
      ${d.can.approve && nR ? `<button type="button" class="btn sm primary" id="pkQb">Tekshiruvdagilarni tasdiqlash (${nR})</button>` : ""}</div>
      ${TM.caps.generate && !TM.ai.on ? `<p class="pk-note">AI ulanmagan — administratorga murojaat qiling. Savollarni «Savol qo'shish» orqali qo'lda kiritish mumkin.</p>` : ""}` : ""}
    <div id="pkQr"></div>
    ${items.length ? `<details class="pk-det pk-sub" ${nD || nR || nX || items.length <= 3 ? "open" : ""}><summary><b>Savollar</b><span class="muted">${items.length} ta</span></summary><div class="tb-qs">${items.map(tbQCard).join("")}</div></details>` : ""}`;
  box.querySelector("#pkQa")?.addEventListener("click", () => tbEdit(null, tno, refresh));
  box.querySelectorAll("[data-qa]").forEach(b => b.onclick = () => tbQAction(+b.dataset.id, b.dataset.qa, items, tno, refresh));
  const bulk = async (action, ids) => { const r = await tbApi(`/api/testbank/courses/${cid}/bulk`, {action, ids});
    if (r) { toast(`Bajarildi: ${r.done} ta${r.skipped.length ? ` · o'tkazib yuborildi: ${r.skipped.length} (tuzatish kerak)` : ""}`); refresh(); } };
  box.querySelector("#pkQs")?.addEventListener("click", () => bulk("submit", items.filter(q => q.can?.submit).map(q => q.id)));
  box.querySelector("#pkQb")?.addEventListener("click", () => bulk("approve", items.filter(q => q.status === "tekshiruvda").map(q => q.id)));
  box.querySelector("#pkQg")?.addEventListener("click", async e => {
    const btn = e.currentTarget; btn.disabled = true;
    box.querySelector("#pkQr").innerHTML = `<p class="pk-note">${ico("clock", 14)} AI savollar tuzmoqda — bir-ikki daqiqa davom etishi mumkin…</p>`;
    try {
      const r = await tbApi(`/api/testbank/courses/${cid}/generate`, {topics: [tno], n: 10, types: ["mcq"], mix: {oson: 30, orta: 50, qiyin: 20}});
      if (r) { TB.meta = null; toast(`Yaratildi: ${r.created} ta savol (qoralama) — ko'rib, tekshiruvga yuboring`); refresh(); } else box.querySelector("#pkQr").innerHTML = "";
    } finally { if (btn.isConnected) btn.disabled = false; }
  });
}

/* ---------- Mashq muharriri (oddiy formalar): moslashtirish — juftlar; saralash — toifalar va elementlar; kartochkalar — old/orqa ---------- */
function pkExEdit(base, x, L, done) {
  const k = x.kind, lab = PK.meta.ex_kinds[k], val = v => esc(v || "");
  const pair = (a, b, pa, pb, n) => `<div class="pk-row2"><input type="text" data-a maxlength="200" value="${val(a)}" placeholder="${pa}" aria-label="${n}: ${pa}"><input type="text" data-b maxlength="500" value="${val(b)}" placeholder="${pb}" aria-label="${n}: ${pb}"></div>`;
  const rows = k === "match" ? Array.from({length: 8}, (_, i) => x.pairs?.[i] || {}) : k === "flashcards" ? [...(x.cards || []), ...Array.from({length: Math.max(3, 6 - (x.cards || []).length)}, () => ({}))].slice(0, 40) : [];
  const body = k === "match" ? `<label>Topshiriq matni<input type="text" id="pkXs" maxlength="300" value="${val(x.title)}" placeholder="Mos juftlarni toping"></label>
      <p class="pk-note" style="margin:0 0 6px">2–8 juft: chapda atama, o'ngda ta'rifi. Bo'sh qatorlar hisobga olinmaydi; qiymatlar takrorlanmasin. Talabaga o'ng tomon aralashtirib beriladi.</p>
      <div id="pkXr">${rows.map((p, i) => pair(p.left, p.right, "Atama", "Ta'rifi / mos qiymat", i + 1)).join("")}</div>`
    : k === "sort" ? `<label>Topshiriq matni<input type="text" id="pkXs" maxlength="300" value="${val(x.title)}" placeholder="Elementlarni toifalarga ajrating"></label>
      <p class="pk-note" style="margin:0 0 6px">2–4 toifa, har birida 1–8 element (har qatorda bitta). Element faqat bitta toifada bo'lsin. Talabaga elementlar aralashtirib, kartochka sifatida beriladi.</p>
      <div class="pk-cats">${[0, 1, 2, 3].map(i => { const c = x.categories?.[i] || {}; return `<div class="pk-cat"><input type="text" data-ct maxlength="80" value="${val(c.title)}" placeholder="${i + 1}-toifa nomi${i > 1 ? " (ixtiyoriy)" : ""}" aria-label="${i + 1}-toifa nomi">
        <textarea data-ci rows="5" placeholder="Elementlar — har qatorda bitta" aria-label="${i + 1}-toifa elementlari">${val((c.items || []).join("\n"))}</textarea></div>`; }).join("")}</div>`
    : `<label>Sarlavha<input type="text" id="pkXs" maxlength="80" value="${val(x.title)}" placeholder="Kartochkalar"></label>
      <p class="pk-note" style="margin:0 0 6px">1–40 kartochka: old tomonda atama yoki savol, orqada javob. Bo'sh qatorlar hisobga olinmaydi. Baholanmaydi.</p>
      <div id="pkXr">${rows.map((c, i) => pair(c.front, c.back, "Old tomon", "Orqa tomon", i + 1)).join("")}</div>
      <div class="pk-acts"><button type="button" class="btn sm ghost" id="pkXm">+ Yana 3 qator</button></div>`;
  const quotes = (x.quotes || []).filter(q => q.quote).map(q => `<li>${esc(q.text)}<small>«${esc(q.quote)}»</small></li>`).join("");
  const bg = pkModal(`${L.code}: ${lab}${x.id ? "" : " (yangi)"}`, `${x.status === "qoralama" ? `<p class="pk-warnbox">${ico("info", 15)}<span>${x.ai ? "AI qoralamasi" : "Qoralama"} — tekshirib, kerak bo'lsa tahrirlang. «Saqlash» bosilgach darsga kiradi.</span></p>` : ""}${body}
    ${k !== "flashcards" ? `<label style="margin-top:10px">Izoh (javobdan keyin ko'rsatiladi, ixtiyoriy)<input type="text" id="pkXe" maxlength="500" value="${val(x.explanation)}"></label>` : ""}
    ${quotes ? `<details class="pk-det"><summary>AI — matndagi iqtiboslar</summary><ol class="pk-plan">${quotes}</ol></details>` : ""}`, async m => {
    const b = {kind: k, status: "faol", explanation: m.querySelector("#pkXe")?.value.trim() || ""};
    b[k === "flashcards" ? "title" : "stem"] = m.querySelector("#pkXs").value.trim();
    const two = () => [...m.querySelectorAll(".pk-row2")].map(r => [r.querySelector("[data-a]").value.trim(), r.querySelector("[data-b]").value.trim()]).filter(r => r[0] || r[1]);
    if (k === "match") b.pairs = two().map(([left, right]) => ({left, right}));
    else if (k === "flashcards") b.cards = two().map(([front, back]) => ({front, back}));
    else b.categories = [...m.querySelectorAll(".pk-cat")].map(c => ({title: c.querySelector("[data-ct]").value.trim(), items: c.querySelector("[data-ci]").value.split("\n").map(v => v.trim()).filter(Boolean)})).filter(c => c.title || c.items.length);
    const r = await pkApi(x.id ? `/api/paket/exercises/${x.id}` : `${base}/exercises`, b);
    if (r) { toast(`${lab} saqlandi — darsga kiradi`); done(); return true; }
  }, "Saqlash", true);
  bg.querySelector("#pkXm")?.addEventListener("click", () => { const box = bg.querySelector("#pkXr"), n = box.children.length;
    if (n >= 40) { toast("Ko'pi bilan 40 ta kartochka"); return; }
    box.insertAdjacentHTML("beforeend", Array.from({length: Math.min(3, 40 - n)}, (_, i) => pair("", "", "Old tomon", "Orqa tomon", n + i + 1)).join("")); });
}

/* ---------- Ommaviy: video havolalar ro'yxati va «Hammasini tayyorlash» (bo'lim) ---------- */
async function pkBulk(box) {
  const M = PK.meta;
  box.innerHTML = `<div id="pkPk"></div><div class="pk-grid">
    <div class="card pk-card"><h3>Video havolalarni joylash</h3>
      <p class="muted">Har qatorda bitta YouTube havola — L1 (1-mavzu) dan boshlab ketma-ket joylanadi. Aniq darsga: «5: https://youtu.be/…» yoki dars kodi bilan «A3: https://youtu.be/…».</p>
      <label class="pk-sr" for="pkBt">Havolalar</label><textarea id="pkBt" class="pk-ta" placeholder="https://www.youtube.com/watch?v=…&#10;https://youtu.be/…&#10;7: https://youtu.be/…"></textarea>
      <div class="pk-acts"><button type="button" class="btn sm" id="pkBc">Tekshirish</button><button type="button" class="btn sm primary" id="pkBs">Saqlash</button></div>
      <div id="pkBr"></div></div>
    <div class="card pk-card"><h3>Hammasini tayyorlash</h3>
      <p class="muted">Tanlangan kursning fayli bor barcha darslari birdan tayyorlanadi. Fayllari o'zgarmagan dars qayta tayyorlanmaydi.</p>
      <div class="pk-form"><label>Dars turi<select id="pkGm"><option value="">Har dars o'z sozlamasi bo'yicha</option>${Object.keys(M.modes).map(k => `<option value="${k}">${esc(pkMode(k))}</option>`).join("")}</select></label>
        <label class="cb"><input type="checkbox" id="pkGc" checked> Faqat fayllari to'liq darslar (matn, taqdimot, video, test)</label></div>
      <div class="pk-acts"><button type="button" class="btn primary" id="pkGo" ${M.player ? "" : "disabled"}>${ico("package", 15)} Hammasini tayyorlash</button></div>
      <div id="pkGr"></div></div></div>`;
  const run = async apply => {
    if (!PK.cid) { toast("Kurs tanlang"); return; }
    const text = box.querySelector("#pkBt").value;
    if (!text.trim()) { toast("Havolalarni kiriting"); return; }
    const r = await pkApi(`/api/paket/courses/${PK.cid}/bulk/videos`, {text, apply});
    if (!r) return;
    if (apply) toast(`Saqlandi: ${r.assigned} ta dars${r.errors ? `, xato: ${r.errors}` : ""}`);
    box.querySelector("#pkBr").innerHTML = pkTable([["Qator", x => x.line, "num"], ["Dars", x => `<b>${esc(x.code || x.topic_no)}</b> ${esc(x.title || "")}`],
      ["Havola", x => `<span class="pk-mono">${esc(x.url)}</span>${x.ok ? `<small>${x.provider === "youtube" ? "YouTube" : "tashqi havola"}</small>` : `<small class="pk-bad">${esc(x.error)}</small>`}`],
      ["", x => x.ok ? pkChip(apply ? "joylandi" : "to'g'ri", "ok") : pkChip("xato", "bad")]], r.rows, {empty: "Havola topilmadi"});
  };
  box.querySelector("#pkBc").onclick = () => run(false);
  box.querySelector("#pkBs").onclick = () => run(true);
  box.querySelector("#pkGo").onclick = async e => {
    if (!PK.cid) { toast("Kurs tanlang"); return; }
    const btn = e.currentTarget; btn.disabled = true;
    const out = box.querySelector("#pkGr");
    out.innerHTML = `<p class="pk-note">${ico("clock", 14)} Tayyorlanmoqda… Bir necha daqiqa davom etishi mumkin.</p>`;
    try {
      const r = await pkApi(`/api/paket/courses/${PK.cid}/bulk/build`, {mode: box.querySelector("#pkGm").value || null, only_complete: box.querySelector("#pkGc").checked});
      if (!r) { out.innerHTML = ""; return; }
      const sum = `Tayyorlandi: ${r.built} · o'zgarmagan: ${r.unchanged} · o'tkazib yuborildi: ${r.skipped}${r.failed ? ` · xato: ${r.failed}` : ""}`;
      toast(sum);
      out.innerHTML = `<p class="pk-note">${sum}</p>` +
        pkTable([["Dars", x => esc(x.code || x.no)], ["Natija", x => x.ok ? (x.unchanged ? `o'zgarmagan · v${x.version}` : `tayyorlandi · v${x.version} · ${esc((PK_ST[x.status] || [x.status])[0])}`) : `<span class="${x.skipped ? "" : "pk-bad"}">${esc(x.error)}</span>`]], r.results);
    } finally { if (btn.isConnected) btn.disabled = false; }
  };
  await pkPicker(box.querySelector("#pkPk"), () => { box.querySelector("#pkBr").innerHTML = ""; box.querySelector("#pkGr").innerHTML = ""; });
}

/* ---------- Sozlamalar (bo'lim) ---------- */
async function pkSettings(box) {
  const M = PK.meta, S = M.defaults, ed = M.caps.settings;
  box.innerHTML = `<div class="pk-grid">
    <div class="card pk-card"><h3>Standart sozlamalar</h3><p class="muted">Barcha darslar uchun. Alohida dars uchun: Darslar → «Kengaytirilgan sozlamalar».</p>
      <form id="pkDf"><div class="pk-form">
        <label>Dars turi (qaysi tizim uchun)<select name="mode" ${ed ? "" : "disabled"}>${Object.keys(M.modes).map(k => `<option value="${k}" ${k === S.mode ? "selected" : ""}>${esc(pkMode(k))}</option>`).join("")}</select></label>
        <label>Dars qachon tugallangan hisoblanadi<select name="completion" ${ed ? "" : "disabled"}>${Object.entries(M.completion).map(([k, l]) => `<option value="${k}" ${k === S.completion ? "selected" : ""}>${esc(l)}</option>`).join("")}</select></label>
        <label>O'tish bali, %<input type="number" name="mastery" min="0" max="100" value="${S.mastery}" ${ed ? "" : "disabled"}></label>
        <label>Testdagi savollar soni (0 — hammasi)<input type="number" name="quiz_n" min="0" max="200" value="${S.quiz_n}" ${ed ? "" : "disabled"}></label>
        <label>Urinishlar soni (0 — cheksiz)<input type="number" name="attempts" min="0" max="20" value="${S.attempts}" ${ed ? "" : "disabled"}></label>
        <label class="cb"><input type="checkbox" name="shuffle" ${S.shuffle ? "checked" : ""} ${ed ? "" : "disabled"}> Savollarni aralashtirish</label>
        <label class="cb"><input type="checkbox" name="show_feedback" ${S.show_feedback ? "checked" : ""} ${ed ? "" : "disabled"}> Javobdan keyin izoh ko'rsatish</label>
      </div>
      <fieldset class="pk-fs"><legend>Dars qismlari</legend><div class="pk-checks">${Object.entries(M.blocks).map(([k, l]) => `<label><input type="checkbox" name="b_${k}" ${S.blocks[k] ? "checked" : ""} ${ed ? "" : "disabled"}> ${esc(l)}</label>`).join("")}</div></fieldset>
      <fieldset class="pk-fs"><legend>Kafedra shabloni</legend><div class="pk-form">
        <label>Ko'rinish<select name="layout" ${ed ? "" : "disabled"}>${Object.entries(M.layouts).map(([k, l]) => `<option value="${k}" ${k === S.layout ? "selected" : ""}>${esc(l)}</option>`).join("")}</select></label>
        <label>Video (fayl ham, havola ham bo'lsa)<select name="video_source" ${ed ? "" : "disabled"}>${Object.entries(M.video_sources).map(([k, l]) => `<option value="${k}" ${k === S.video_source ? "selected" : ""}>${esc(l)}</option>`).join("")}</select></label>
        ${Object.entries({video: "Video bo'limi", text: "Matn bo'limi", slides: "Taqdimot bo'limi", practice: "Mashq va topshiriq bo'limi"}).map(([k, l]) => `<label>${esc(l)} sarlavhasi<input type="text" name="s_${k}" maxlength="80" value="${esc(S.sections[k])}" ${ed ? "" : "disabled"}></label>`).join("")}
      </div></fieldset>
      <fieldset class="pk-fs"><legend>O'z-o'zini baholash (baholanmaydi)</legend><div class="pk-form">
        <label class="pk-wide">Savol<input type="text" name="r_q" maxlength="300" value="${esc(S.reflect.question)}" ${ed ? "" : "disabled"}></label>
        ${[0, 1].map(i => `<label>${i + 1}-javob<input type="text" name="r_t${i}" maxlength="120" value="${esc(S.reflect.options[i]?.text || "")}" ${ed ? "" : "disabled"}></label>
          <label>${i + 1}-javobga izoh<input type="text" name="r_f${i}" maxlength="500" value="${esc(S.reflect.options[i]?.feedback || "")}" ${ed ? "" : "disabled"}></label>`).join("")}
      </div><p class="pk-note">Yoqish/o'chirish — «Dars qismlari»da («O'z-o'zini baholash»). Dars bo'yicha alohida o'zgartirish mumkin.</p></fieldset>
      <fieldset class="pk-fs"><legend>Topshiriq (o'qituvchi rasmi + matn + savollar)</legend><div class="pk-form">
        <label>Sarlavha<input type="text" name="a_title" maxlength="80" value="${esc(S.assignment.title)}" ${ed ? "" : "disabled"}></label>
        <label>Imzo<input type="text" name="a_author" maxlength="120" value="${esc(S.assignment.author)}" ${ed ? "" : "disabled"}></label>
        <label class="pk-wide">Matn<input type="text" name="a_text" maxlength="400" value="${esc(S.assignment.text)}" ${ed ? "" : "disabled"}></label>
      </div><p class="pk-note">Savollar — ma'ruza matnidagi «Savollar» / «Nazorat savollari» / «Topshiriqlar» bo'limidan o'zi olinadi yoki dars ekranida qo'lda kiritiladi. O'qituvchi rasmi — kurs sozlamalarida.</p></fieldset>
      ${ed ? `<div class="pk-acts"><button class="btn sm primary">Saqlash</button></div>` : `<p class="pk-note">O'zgartirish — Masofaviy ta'lim bo'limida.</p>`}</form>
      <h4>Standart muqova (bo'lim)</h4><div class="pk-media"><div>${M.default_cover ? `<img class="pk-thumb muqova" src="/api/paket/assets/${M.default_cover}" alt="Standart muqova">` : `<div class="pk-thumb muqova none">yo'q</div>`}
        <div><p class="pk-note" style="margin:0 0 6px">Dars muqovasi: fon rasmi + ISFT logotipi + «L1-1-dars: MAVZU» + muallif. Qaysi rasm olinadi: dars → kurs → shu standart; hech biri bo'lmasa — institut rangi.</p>
        ${ed ? `<div class="pk-acts tight" style="justify-content:flex-start"><label class="btn sm pk-file">${ico("upload", 15)} Rasm tanlash (.png, .jpg)<input type="file" accept=".png,.jpg,.jpeg" hidden id="pkDc"></label>
          ${M.default_cover ? `<button type="button" class="btn sm ghost" id="pkDx">Olib tashlash</button>` : ""}</div>` : ""}</div></div></div></div>
    <div class="card pk-card"><h3>Darsni LMS'ga yuklash</h3>
      <h4>NEXTID (my.isft.uz) — «Articulate» yorlig'i</h4>${pkNextidHelp(null, "")}
      <p class="pk-note">Taqdimot aniq ko'rinishi uchun o'qituvchi PowerPoint'da «Fayl → Saqlash → PDF» qilib PDF'ni ham yuklashi kerak (.pptx dan keyin) — har bir sahifa rasm sifatida ko'rsatiladi.</p>
      <h4>Moodle va boshqa LMS</h4>
      <ol class="pk-steps"><li>Dars turini «Boshqa LMS uchun (SCORM 1.2)» qilib tayyorlang.</li><li>Kursda tahrirlash rejimini yoqing → «Faoliyat yoki resurs qo'shish» → <b>SCORM paketi</b>.</li>
        <li>Nom yozing va .zip faylni (ochmasdan) yuklang; baholash usuli — «Eng yuqori urinish».</li><li>Saqlang va ochib tekshiring.</li></ol>
      <p class="pk-note">SCORM 2004 ni faqat LMS aniq talab qilsa tanlang. Texnik tafsilotlar — docs/paket.md.</p>
      <h4>Kurs paketi</h4><p class="pk-note">Darslar → «Kengaytirilgan sozlamalar» → «Kurs paketi»: barcha darslar bitta faylda.</p>
      <h4>Cheklovlar</h4><p class="pk-note">Fayl ≤ ${M.limits.asset_mb} MB, video ≤ ${M.limits.video_mb} MB (.mp4 / .webm), slayd audiosi ≤ ${M.limits.audio_mb} MB, tayyor dars ≤ ${M.limits.package_mb} MB (video fayl bilan ≤ ${M.limits.package_video_mb} MB). YouTube videosi YouTube'da qoladi. Eski .ppt / .doc qabul qilinmaydi — .pptx / .docx qilib saqlang.</p>
      <h4>Articulate Rise 360 bilan farqi</h4><p class="pk-note">O'zi bajaradi: muqova, video (fayl yoki YouTube), ma'ruza matni Word'dan (reja, rasm, jadval, adabiyotlar), taqdimot galereyasi (izoh va audio bilan), kartochkalar, test + moslashtirish / saralash, topshiriq, o'z-o'zini baholash. Yo'q: qismlarni sichqoncha bilan erkin joylashtirish (tartib — kafedra shabloni), AI subtitr va AI ovoz — subtitr va audio tayyor fayl sifatida yuklanadi.</p></div></div>`;
  const reMeta = async () => { PK.meta = await pkApi("/api/paket/meta"); pkSettings(box); };
  const dc = box.querySelector("#pkDc");
  if (dc) dc.onchange = async () => { const f = dc.files[0]; if (!f) return; const r = await pkUpload("/api/paket/settings/cover", f); if (r) { toast("Standart muqova saqlandi"); reMeta(); } };
  box.querySelector("#pkDx")?.addEventListener("click", async () => { if (!confirm("Standart muqova olib tashlansinmi?")) return;
    const r = await pkApi(`/api/paket/assets/${M.default_cover}/delete`, {}); if (r) { toast("Olib tashlandi"); reMeta(); } });
  box.querySelector("#pkDf").onsubmit = async e => {
    e.preventDefault(); if (!ed) return;
    const f = e.currentTarget, blocks = {};
    Object.keys(M.blocks).forEach(k => blocks[k] = f.elements["b_" + k].checked);
    const sections = {video: f.elements.s_video.value.trim(), text: f.elements.s_text.value.trim(), slides: f.elements.s_slides.value.trim(), practice: f.elements.s_practice.value.trim()};
    const assignment = {title: f.elements.a_title.value.trim(), text: f.elements.a_text.value.trim(), author: f.elements.a_author.value.trim()};
    const reflect = {question: f.elements.r_q.value.trim(), options: [0, 1].map(i => ({text: f.elements["r_t" + i].value.trim(), feedback: f.elements["r_f" + i].value.trim()}))};
    const r = await pkApi("/api/paket/settings", {mode: f.elements.mode.value, completion: f.elements.completion.value, mastery: +f.elements.mastery.value, layout: f.elements.layout.value,
      quiz_n: +f.elements.quiz_n.value, attempts: +f.elements.attempts.value, shuffle: f.elements.shuffle.checked, show_feedback: f.elements.show_feedback.checked, blocks, sections, reflect, assignment, video_source: f.elements.video_source.value});
    if (r) { toast("Saqlandi"); PK.meta.defaults = r.defaults; }
  };
}

/* ---------- navigatsiya: go("paket") (app.js go() xaritasiga tegmasdan) ---------- */
(function () {
  if (typeof go !== "function" || go._pk) return;
  const prev = go;
  go = function (v, opts) {
    prev(v, opts);
    if (v !== "paket") return;
    const tab = opts && typeof opts === "object" ? opts.tab : undefined;
    Promise.resolve().then(() => renderPaket(tab)).catch(e => { if (e?.message === "auth") return; $("#v-paket").innerHTML = e?.message === "denied" ? locked("Bu bo'lim") : errCard("paket"); });
  };
  go._pk = true;
})();

/* ---------- chiqish / sessiya tugashi: app.js showLogin() — keyingi foydalanuvchiga oldingisining holati qolmasin ---------- */
(function () {
  if (typeof showLogin !== "function" || showLogin._pk) return;
  const prev = showLogin;
  showLogin = function (...a) { pkReset(); return prev.apply(this, a); };
  showLogin._pk = true;
})();
