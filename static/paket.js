/* =====================================================================
   «Kontent paketlari» (app/paket.py, /api/paket) — dars bo'yicha xAPI (NEXTID.LMS) / SCORM 1.2 / SCORM 2004 paket (Articulate o'rniga).
     Qamrov:           kafedra / o'qituvchi / kurs kesimida — paketi yig'ilgan va tasdiqlangan darslar, manbalar tayyorligi.
     Mavzular:         darslar (L — ma'ruza, A — amaliy, S, Lab, MT; NEXTID nomlari ro'yxatidan), dars manbalari (ma'ruza matni + reja,
                       Word rasmlari va jadvallari, adabiyotlar, taqdimot — PDF sahifalari rasm sifatida, YouTube video, Test bank testi,
                       AI asosiy xulosalar), sozlamalar, yig'ish, ko'rish (pleyer), yuklab olish, tasdiqlash / qaytarish (bo'lim); kurs paketi.
     Avtomatik joylash: YouTube havolalar ro'yxati → L1..Ln (yoki «A3: havola»); tayyor darslarni ommaviy yig'ish.
     Sozlamalar:       standart paket turi, yakunlash, kafedra shabloni (bo'lim sarlavhalari, layout, o'z-o'zini baholash); NEXTID / Moodle yo'riqnomasi.
     Rise 360 (v3):    muqova (rasm + muallif), video fayl (.mp4/.webm) + subtitr (.vtt/.srt) + poster, slayd izohi va audiosi, mashqlar
                       (moslashtirish, saralash, kartochkalar — oddiy formalar; «AI: mashqlar» qoralamasi), topshiriq (o'qituvchi rasmi + savollar).
   Ruxsat va ko'lam serverda. Global: renderPaket().  app.js yordamchilari: $, esc, fmt, toast, locked, errCard, showLogin, ico, ME.
   ===================================================================== */
const PK = {meta: null, tab: null, cid: 0, topic: 1, cov: {q: "", department_id: 0, only: "", offset: 0}};
/* boshqa foydalanuvchi kirsa (sahifa qayta yuklanmasdan) — oldingisining rol/yorliq/kurs/filtrlari qolmasin (testbank.js tbReset bilan bir xil) */
function pkReset() { Object.assign(PK, {meta: null, who: null, tab: null, cid: 0, topic: 1, cov: {q: "", department_id: 0, only: "", offset: 0}}); }
if (typeof ICONS === "object") {
  if (!ICONS.upload) ICONS.upload = '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><path d="m17 8-5-5-5 5"/><path d="M12 3v12"/>';
  if (!ICONS.download) ICONS.download = '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><path d="m7 10 5 5 5-5"/><path d="M12 15V3"/>';
  if (!ICONS.package) ICONS.package = '<path d="M11 21.73a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73z"/><path d="M12 22V12"/><path d="m3.3 7 8.7 5 8.7-5"/><path d="m7.5 4.27 9 5.15"/>';
}
if (!document.querySelector('link[href="paket.css"]')) document.head.insertAdjacentHTML("beforeend", '<link rel="stylesheet" href="paket.css">');

const PK_TABS = {qamrov: "Qamrov", mavzular: "Mavzular", joylash: "Avtomatik joylash", sozlama: "Sozlamalar"};
const PK_ST = {qoralama: ["Qoralama", "warn"], tayyor: ["Tayyor · tasdiq kutilmoqda", "info"], tasdiqlandi: ["Tasdiqlangan", "ok"]};
const PK_RD = [["text", "M", "Ma'ruza matni"], ["slides", "T", "Taqdimot"], ["video", "V", "Video"], ["quiz", "S", "Test savollari"]];
const pkChip = (t, cls = "") => `<span class="pk-chip ${cls}">${esc(t)}</span>`;
const pkSt = s => pkChip((PK_ST[s] || [s])[0], (PK_ST[s] || [])[1] || "");
const pkPct = v => v == null ? "—" : `${String(v).replace(".", ",")}%`;
const pkBar = (pct, cls = "") => `<div class="pk-bar ${cls}" role="img" aria-label="${pkPct(pct)}"><i style="width:${Math.max(0, Math.min(100, pct || 0))}%"></i></div>`;
const pkTone = p => p == null ? "" : p >= 80 ? "ok" : p >= 40 ? "warn" : "bad";
const pkD = s => { s = String(s || ""); return s.length >= 10 ? `${s.slice(8, 10)}.${s.slice(5, 7)}.${s.slice(0, 4)}${s.length >= 16 ? " " + s.slice(11, 16) : ""}` : "—"; };
const pkKpi = (label, val, sub = "", cls = "") => `<div class="pk-kpi ${cls}"><span>${esc(label)}</span><b>${val}</b>${sub ? `<small>${sub}</small>` : ""}</div>`;
const pkSize = b => b >= 1048576 ? `${(b / 1048576).toFixed(1).replace(".", ",")} MB` : `${Math.max(1, Math.round((b || 0) / 1024))} KB`;
const pkRd = t => `<span class="pk-rd" aria-label="Tayyorgarlik">${PK_RD.map(([k, l, n]) => `<i class="${t[k] ? "on" : ""}" title="${esc(n)}: ${t[k] ? "bor" : "yo'q"}">${l}</i>`).join("")}</span>`;

async function pkApi(url, body, method) {
  const r = await fetch(url, {method: method || (body === undefined ? "GET" : "POST"), credentials: "same-origin",
                              headers: body instanceof Blob ? {} : {"Content-Type": "application/json"},
                              body: body === undefined ? undefined : body instanceof Blob ? body : JSON.stringify(body)});
  if (r.status === 401) { showLogin(); throw new Error("auth"); }
  const d = await r.json().catch(() => ({}));
  if (!r.ok) {
    const det = d.detail; const m = d.message || (typeof det === "string" ? det : Array.isArray(det) ? "Maydonlarni tekshiring" : det?.message) || "Xatolik yuz berdi";
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
function pkModal(title, html, onOk, okText = "Saqlash", wide = false) {
  const bg = document.createElement("div"); bg.className = "pk-modal-bg";
  bg.innerHTML = `<div class="pk-modal ${wide ? "wide" : ""}" role="dialog" aria-modal="true" aria-label="${esc(title)}"><h3>${esc(title)}</h3>${html}
    <div class="pk-acts end"><button type="button" class="btn ghost" data-x>${onOk ? "Bekor qilish" : "Yopish"}</button>${onOk ? `<button type="button" class="btn primary" data-ok>${esc(okText)}</button>` : ""}</div></div>`;
  document.body.appendChild(bg);
  const opener = document.activeElement;
  const close = () => { bg.remove(); opener?.focus?.({preventScroll: true}); };
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
  if (file.size > lim * 1048576) { toast(`Fayl ${lim} MB dan katta`); return null; }
  toast(file.size > 20 * 1048576 ? `Yuklanmoqda… (${pkSize(file.size)} — biroz kuting)` : "Yuklanmoqda…");
  return pkApi(`${url}?name=${encodeURIComponent(file.name)}${extra}`, file);
}
const PK_KORD = ["maruza", "amaliy", "seminar", "laboratoriya", "mustaqil"];
/* NEXTID'ga yuklash yo'riqnomasi (Sozlamalar va dars paneli) */
const pkNextidHelp = () => `<ol class="pk-steps">
    <li>Paket turi — <b>xAPI (Tin Can) — NEXTID</b> (standart). Darsni yig'ing va «Yuklab olish» — fayl nomi dars kodi bilan: <span class="pk-mono">ISFT_&lt;fan&gt;_L01_xapi.zip</span>, <span class="pk-mono">…_A01_xapi.zip</span>.</li>
    <li>my.isft.uz (NEXTID.LMS) → fan → <b>Articulate</b> yorlig'i → yangi dars qo'shish.</li>
    <li>Dars nomini NEXTID uslubida yozing — kod paketdagi bilan bir xil bo'lsin: «L1-1-dars: MAVZU NOMI» (ma'ruza), «A1- AMALIY MASHG'ULOT: NOM» (amaliy).</li>
    <li>Zip faylni <b>ochmasdan</b> yuklang (ildizida <span class="pk-mono">index.html</span> va <span class="pk-mono">tincan.xml</span>). Saqlang va darsni ochib tekshiring.</li>
    <li>Video: YouTube havola yoki <b>video fayl</b> (.mp4 / .webm, subtitr .vtt / .srt bilan). Fayl paket ichida ketadi — zip hajmi oshadi (NEXTID'ning yuklash chegarasini tekshiring); katta video uchun YouTube havolasi qulayroq.</li>
    <li>«MASHQ VA TOPSHIRIQLAR»: kartochkalar, test (Test bank savollari + moslashtirish / saralash) va topshiriq paket ichida. Topshiriq javobini talaba PDF qilib NEXTID'ning o'ziga yuklaydi (paket fayl qabul qilmaydi).</li>
    <li>Taqdimot aniq ko'rinishi uchun PowerPoint'da <b>«Fayl → Saqlash → PDF»</b> qiling va PDF'ni ham yuklang (.pptx dan <b>keyin</b> — eng oxirgi yuklangan taqdimot ishlatiladi) — har bir sahifa rasm sifatida ko'rsatiladi (.pptx yuklab olish uchun qoladi).</li></ol>
  <p class="pk-note">NEXTID darsni iframe'da launch parametrlarisiz ochadi: pleyer «mustaqil» rejimda ishlaydi, jarayon/natijani ota oynaga <span class="pk-mono">postMessage</span> bilan yuboradi; «Ko'rish rejimi» banneri chiqmaydi.</p>`;
const pkPrevUrl = id => `/api/paket/packages/${id}/preview/index.html?preview=1`;   /* ?preview=1 — pleyer «Ko'rish rejimi» bannerini ko'rsatadi */
function pkPreview(p) {
  pkModal(`Ko'rish: v${p.version} · ${p.mode_label}`, `<p class="pk-note">Pleyer LMS'siz rejimda ochiladi (natija saqlanmaydi). <a href="${pkPrevUrl(p.id)}" target="_blank" rel="noopener">Yangi oynada ochish</a></p>
    <iframe class="pk-frame" src="${pkPrevUrl(p.id)}" title="Paketni ko'rish" sandbox="allow-scripts allow-popups allow-popups-to-escape-sandbox allow-forms"
      referrerpolicy="no-referrer" allow="fullscreen; encrypted-media; picture-in-picture" allowfullscreen></iframe>`, null, "", true);
  /* sandbox (allow-same-origin YO'Q): paket kontenti ilova origin'idan ajratilgan — sessiya cookie/API'ga kira olmaydi; yangi oynada ham server CSP sandbox qo'yadi */
}

/* ---------- asosiy ko'rinish ---------- */
async function renderPaket(tab) {
  const v = $("#v-paket");
  const who = typeof ME !== "undefined" ? ME : null;
  if (PK.who !== who) {     /* birinchi kirish (who=null) — tashqi havola qo'ygan PK.cid saqlanadi; boshqa foydalanuvchi — hammasi tozalanadi */
    const cid = PK.who === null || PK.who === undefined ? PK.cid : 0, want = tab || (cid ? PK.tab : null);
    pkReset(); PK.who = who; PK.cid = cid; tab = want;
  }
  if (!PK.meta) { const m = await pkApi("/api/paket/meta"); if (PK.who !== who) return; PK.meta = m; }
  const M = PK.meta;
  PK.tab = tab && M.tabs.includes(tab) ? tab : (PK.tab && M.tabs.includes(PK.tab) ? PK.tab : M.tabs[0]);
  const tbOn = typeof renderTestbank === "function" && !document.querySelector('#nav a[data-v="testbank"]')?.classList.contains("hidden");
  v.innerHTML = `<div class="pk-head"><div><h2>Kontent paketlari</h2><span class="muted">${esc(M.scope)} · dars bo'yicha xAPI (NEXTID) / SCORM paket: video, ma'ruza matni (rasm, jadval, adabiyotlar), taqdimot, test</span></div>
      <div class="pk-acts tight">${tbOn ? `<button type="button" class="btn sm ghost" data-tb>${ico("checkc", 15)} Test bank</button>` : ""}</div></div>
    ${M.demo ? `<div class="pk-demo">${ico("info", 15)}<span><b>Namuna.</b> «Mikroiqtisodiyot» 1–2-mavzulari: ma'ruza matni, taqdimot (.pptx) va video havola — sun'iy (demo); video ID mavjud emas. Haqiqiy paket uchun manbalarni yuklang.</span></div>` : ""}
    ${!M.player && M.caps.build ? `<div class="pk-warnbox">${ico("alert", 15)}<span>Paket pleyeri o'rnatilmagan (app/paket_player) — yig'ish vaqtincha ishlamaydi. Manbalarni tayyorlash mumkin.</span></div>` : ""}
    <div class="pk-tabs" role="tablist">${M.tabs.map(t => `<button type="button" role="tab" aria-selected="${t === PK.tab}" class="${t === PK.tab ? "on" : ""}" data-t="${t}">${esc(PK_TABS[t])}</button>`).join("")}</div>
    <div id="pkBox"><div class="pk-empty">Yuklanmoqda…</div></div>`;
  v.querySelectorAll(".pk-tabs [data-t]").forEach(b => b.onclick = () => renderPaket(b.dataset.t));
  v.querySelector("[data-tb]")?.addEventListener("click", () => go("testbank"));
  const box = $("#pkBox");
  try {
    await ({qamrov: pkCoverage, mavzular: pkTopics, joylash: pkBulk, sozlama: pkSettings})[PK.tab](box);
  } catch (e) {
    if (e?.message === "auth") return;
    box.innerHTML = e?.message === "denied" ? locked("Bu bo'lim") : `<div class="card pk-card"><p>${esc(e?.msg || "Ma'lumotni yuklab bo'lmadi")}</p></div>`;
  }
}

/* ---------- Kurs tanlash ---------- */
async function pkPicker(box, onPick) {
  if (!PK.cid) { const d = await pkApi("/api/paket/courses?limit=1"); PK.cid = d.items[0]?.id || 0; }
  box.innerHTML = `<div class="pk-pick"><label class="pk-sr" for="pkPq">Kursni qidirish</label>
      <input type="search" id="pkPq" placeholder="Fan, yo'nalish, o'qituvchi…" autocomplete="off">
      <label class="pk-sr" for="pkPs">Kurs</label><select id="pkPs"><option>Yuklanmoqda…</option></select></div>`;
  const inp = box.querySelector("#pkPq"), sel = box.querySelector("#pkPs");
  let timer = null;
  const load = async q => {
    const d = await pkApi(`/api/paket/courses?limit=60&q=${encodeURIComponent(q || "")}`);
    const items = d.items.slice();
    if (PK.cid && !items.some(x => x.id === PK.cid) && !q) {
      try { const c = await pkApi(`/api/paket/courses/${PK.cid}`); items.unshift({id: PK.cid, subject: c.course.subject, direction: c.course.direction, course: c.course.course, started: true}); } catch (e) {}
    }
    sel.innerHTML = items.map(x => `<option value="${x.id}" ${x.id === PK.cid ? "selected" : ""}>${esc(x.subject)} — ${esc(x.direction)}, ${x.course}-kurs${x.started ? " ●" : ""}</option>`).join("")
      || `<option value="">Topilmadi</option>`;
    if (d.total > items.length) sel.insertAdjacentHTML("beforeend", `<option disabled>… yana ${fmt(d.total - items.length)} ta — qidiruvdan foydalaning</option>`);
  };
  inp.oninput = () => { clearTimeout(timer); timer = setTimeout(() => load(inp.value.trim()), 250); };
  sel.onchange = () => { const id = +sel.value; if (id && id !== PK.cid) { PK.cid = id; PK.topic = 1; onPick(); } };
  await load("");
}

/* ---------- Qamrov ---------- */
async function pkCoverage(box) {
  const M = PK.meta, F = PK.cov;
  const d = await pkApi("/api/paket/coverage");
  const t = d.total;
  box.innerHTML = `
    <div class="pk-kpis">
      ${pkKpi("Paketi yig'ilgan mavzular", pkPct(t.built_pct), `${fmt(t.built)} / ${fmt(t.topics)} mavzu`, pkTone(t.built_pct))}
      ${pkKpi("Tasdiqlangan", fmt(t.approved), `${pkPct(t.pct)} mavzu · LMS'ga yuklashga tayyor`, "ok")}
      ${pkKpi("Tasdiq kutilmoqda", fmt(t.waiting), "bo'lim ko'rib chiqadi", t.waiting ? "info" : "")}
      ${pkKpi("Manbasi to'liq mavzular", fmt(t.full), "matn, taqdimot, video va test bor")}
      ${pkKpi("Ma'ruza matni / taqdimot", `${fmt(t.text)} / ${fmt(t.slides)}`, "mavzular")}
      ${pkKpi("Video / test", `${fmt(t.video)} / ${fmt(t.quiz)}`, "havola yoki fayl · savollar yoki mashqlar")}
      ${pkKpi("Mashqli darslar", fmt(t.exercises || 0), "moslashtirish, saralash, kartochkalar")}
    </div>
    <div class="card pk-card"><h3>Kafedralar</h3><p class="muted">Paketi yig'ilgan mavzular ulushi · eng ortda turganlari yuqorida${M.caps.view ? " · kafedra nomini bosing — kurslar ro'yxati filtrlanadi" : ""}</p>
      ${pkTable([["Kafedra", r => M.caps.view ? `<button type="button" class="pk-link" data-dep="${r.department_id}">${esc(r.name)}</button>` : esc(r.name)],
                 ["Paketlar", r => `${pkBar(r.built_pct, pkTone(r.built_pct))}<small>${fmt(r.built)} / ${fmt(r.topics)} mavzu · tasdiqlangan ${fmt(r.approved)}</small>`],
                 ["Manbalar", r => `<small>matn ${fmt(r.text)} · taqdimot ${fmt(r.slides)} · video ${fmt(r.video)} · test ${fmt(r.quiz)}</small>`],
                 ["Kurslar", r => `${fmt(r.started)} / ${fmt(r.courses)}<small>boshlangan</small>`, "num"]], d.departments)}</div>
    ${d.teachers.length ? `<details class="card pk-card pk-det"><summary><h3>O'qituvchilar</h3><span class="muted">${fmt(d.teachers.filter(x => x.started).length)} nafarida boshlangan</span></summary>
      ${pkTable([["O'qituvchi", r => `${esc(r.name)}<small>${esc(r.dept || "")}</small>`],
                 ["Paketlar", r => `${pkBar(r.built_pct, pkTone(r.built_pct))}<small>${fmt(r.built)} / ${fmt(r.topics)} · tasdiqlangan ${fmt(r.approved)}</small>`],
                 ["Manbalar", r => `<small>matn ${fmt(r.text)} · taqdimot ${fmt(r.slides)} · video ${fmt(r.video)} · test ${fmt(r.quiz)}</small>`]],
                d.teachers.slice().sort((a, b) => (b.started - a.started) || ((a.built_pct || 0) - (b.built_pct || 0))).slice(0, 40))}</details>` : ""}
    ${M.caps.view ? `<div class="card pk-card"><h3>Kurslar</h3>
      <div class="pk-filters">
        <input type="search" id="pkCq" placeholder="Fan, yo'nalish, o'qituvchi…" value="${esc(F.q)}" aria-label="Qidirish">
        <select id="pkCo" aria-label="Holat"><option value="">Hammasi</option><option value="started" ${F.only === "started" ? "selected" : ""}>Boshlanganlar</option>
          <option value="waiting" ${F.only === "waiting" ? "selected" : ""}>Tasdiq kutayotganlar</option><option value="empty" ${F.only === "empty" ? "selected" : ""}>Hali boshlanmagan</option></select>
        <select id="pkCd" aria-label="Kafedra"><option value="0">Barcha kafedralar</option>${d.departments.map(x => `<option value="${x.department_id}" ${x.department_id === F.department_id ? "selected" : ""}>${esc(x.name)}</option>`).join("")}</select>
      </div><div id="pkCl"><div class="pk-empty">Yuklanmoqda…</div></div></div>` : `<p class="pk-note">Rahbariyat uchun jamlangan ko'rinish: mavzu matnlari va paketlar mazmuni ko'rsatilmaydi.</p>`}`;
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
    ["Paketlar", r => `${pkBar(r.built_pct, pkTone(r.built_pct))}<small>${r.built} / ${r.topics} mavzu · tasdiqlangan ${r.approved}${r.waiting ? ` · kutilmoqda ${r.waiting}` : ""}</small>`],
    ["Manbalar", r => `<small>M ${r.text} · T ${r.slides} · V ${r.video} · S ${r.quiz}</small>`],
    ["", r => `<button type="button" class="btn sm" data-open="${r.id}">Ochish</button>`]], d.items, {empty: "Kurs topilmadi"}) +
    (d.total > lim ? `<div class="pk-pager"><button type="button" class="btn sm ghost" data-p="${Math.max(0, F.offset - lim)}" ${F.offset ? "" : "disabled"}>← Oldingi</button>
      <span>${fmt(F.offset + 1)}–${fmt(Math.min(d.total, F.offset + lim))} / ${fmt(d.total)}</span>
      <button type="button" class="btn sm ghost" data-p="${F.offset + lim}" ${F.offset + lim < d.total ? "" : "disabled"}>Keyingi →</button></div>` : "");
  el.querySelectorAll("[data-p]").forEach(b => b.onclick = () => { F.offset = +b.dataset.p; pkCourseList(box); });
  el.querySelectorAll("[data-open]").forEach(b => b.onclick = () => { PK.cid = +b.dataset.open; PK.topic = 1; renderPaket("mavzular"); });
}

/* ---------- Mavzular ---------- */
async function pkTopics(box) {
  box.innerHTML = `<div id="pkPk"></div><div id="pkCv"></div>`;
  await pkPicker(box.querySelector("#pkPk"), () => pkCourse(box.querySelector("#pkCv")));
  await pkCourse(box.querySelector("#pkCv"));
}
async function pkCourse(el) {
  if (!PK.cid) { el.innerHTML = `<div class="pk-empty">Sizga biriktirilgan kurs topilmadi</div>`; return; }
  const d = await pkApi(`/api/paket/courses/${PK.cid}`), c = d.course, M = PK.meta;
  if (!d.topics.some(t => t.no === PK.topic)) PK.topic = 1;
  const last = d.course_packages[0];
  const groups = PK_KORD.map(k => [k, d.topics.filter(t => t.kind === k)]).filter(g => g[1].length);
  const tBtn = t => `<button type="button" role="listitem" class="pk-topic ${t.no === PK.topic ? "on" : ""}" data-no="${t.no}" aria-pressed="${t.no === PK.topic}">
        <span class="no">${esc(t.code)}</span><span class="tt">${esc(t.title)}</span>${pkRd(t)}
        <span class="st">${t.approved ? `<span class="ok">tasdiqlangan</span>` : t.last ? (t.last.status === "tayyor" ? `<span class="info">tasdiq kutilmoqda</span>` : "qoralama") : "paket yo'q"}${t.last ? ` · v${t.last.version}` : ""}</span></button>`;
  el.innerHTML = `<div class="card pk-card"><div class="pk-item-h"><div><h3>${esc(c.subject)}</h3>
      <p class="muted">${esc(c.direction)} · ${c.course}-kurs · ${esc(c.dept || "—")} · mas'ul: ${esc(c.teacher || "—")} · ${c.lessons} ta dars · belgilar: M — matn, T — taqdimot, V — video, S — test</p></div></div>
    ${groups.map(([k, ts]) => `<div class="pk-kind"><h4>${esc(d.kinds[k].plural)} <span class="muted">(${esc(d.kinds[k].prefix)}) · ${ts.length} ta</span></h4>
      <div class="pk-topics" role="list">${ts.map(tBtn).join("")}</div></div>`).join("")}
    ${d.can.write ? `<details class="pk-det" style="margin-top:12px"><summary><b>Darslar ro'yxati (NEXTID)</b><span class="muted">amaliy, seminar, laboratoriya darslarini qo'shish yoki nomlarni NEXTID'dagidek yozish</span></summary>
      <p class="pk-note">Har qatorda bitta dars: «L1-1-dars: MAVZU NOMI», «A1- AMALIY MASHG'ULOT: NOM», «A2- Amaliy: NOM», «S1 …», «Lab1 …», «MT1 …». Mavzuga bog'lash (ixtiyoriy): oxirida «(3-mavzu)».</p>
      <label class="pk-sr" for="pkLt">Darslar ro'yxati</label><textarea id="pkLt" class="pk-ta" placeholder="L1-1-dars: AXBOROT TEXNOLOGIYALARI&#10;A1- AMALIY MASHG'ULOT: Excel bilan ishlash (1-mavzu)&#10;A2- Amaliy: Word hujjatlari"></textarea>
      <div class="pk-acts"><button type="button" class="btn sm" id="pkLc">Tekshirish</button><button type="button" class="btn sm primary" id="pkLs">Saqlash</button></div><div id="pkLr"></div></details>` : ""}
    ${d.can.write ? `<details class="pk-det" style="margin-top:12px"><summary><b>Muqova va o'qituvchi rasmi</b><span class="muted">kursning barcha darslari uchun${d.media.muqova ? " · muqova bor" : ""}${d.media.avatar ? " · rasm bor" : ""}</span></summary>
      <div class="pk-media">${[["muqova", "Kurs muqovasi", "cover", "Dars muqovasidagi fon rasmi (≤ 1920 px). Darsga alohida muqova yuklanmasa shu, bo'lmasa bo'lim standarti ishlatiladi."],
                               ["avatar", "O'qituvchi rasmi", "avatar", "«Topshiriq» blokidagi rasm. Yuklanmasa pleyer o'zi belgi chizadi."]].map(([k, l, u, h]) => `<div>
        ${d.media[k] ? `<img class="pk-thumb ${k}" src="/api/paket/assets/${d.media[k]}" alt="${esc(l)}">` : `<div class="pk-thumb ${k} none">yo'q</div>`}
        <div><b>${esc(l)}</b><p class="pk-note" style="margin:2px 0 6px">${esc(h)}</p><div class="pk-acts tight" style="justify-content:flex-start">
          <label class="btn sm pk-file">${ico("upload", 15)} Rasm (.png, .jpg)<input type="file" accept=".png,.jpg,.jpeg" hidden data-cm="${u}"></label>
          ${d.media[k] ? `<button type="button" class="btn sm ghost" data-cdel="${d.media[k]}">Olib tashlash</button>` : ""}</div></div></div>`).join("")}</div></details>` : ""}
    ${d.can.write ? `<details class="pk-det" style="margin-top:12px"><summary><b>Kurs paketi</b><span class="muted">bitta manifestda barcha darslar (har biri alohida SCO)${last ? ` · oxirgisi v${last.version}, ${pkD(last.built_at)}` : ""}</span></summary>
      <div class="pk-form"><label>Turi<select id="pkKm">${["xapi", "scorm12", "scorm2004"].map(m => `<option value="${m}">${esc(M.modes[m])}</option>`).join("")}</select></label>
        <label class="cb"><input type="checkbox" id="pkKa"> Faqat tasdiqlangan darslar</label>
        <div class="pk-acts"><button type="button" class="btn sm primary" id="pkKb" ${M.player ? "" : "disabled"}>${ico("package", 15)} Kurs paketini yig'ish</button></div></div>
      ${d.course_packages.length ? pkTable([["Versiya", p => `v${p.version} · ${esc(p.mode_label)}<small>${pkD(p.built_at)} · ${esc(p.by || "")}</small>`],
        ["Darslar", p => `${(p.settings.topics || []).length} ta`, "num"], ["Hajm", p => pkSize(p.size), "num"],
        ["", p => `<a class="btn sm ghost" href="/api/paket/packages/${p.id}/download">${ico("download", 15)} Yuklab olish</a>`]], d.course_packages) : ""}</details>` : ""}</div>
    <div id="pkTp"></div>`;
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
  el.querySelector("#pkLs")?.addEventListener("click", () => lrun(true));
  el.querySelectorAll(".pk-topic").forEach(b => b.onclick = () => { PK.topic = +b.dataset.no; pkCourse(el); });
  el.querySelectorAll("[data-cm]").forEach(i => i.onchange = async () => { const f = i.files[0]; if (!f) return;
    const r = await pkUpload(`/api/paket/courses/${PK.cid}/${i.dataset.cm}`, f); if (r) { toast("Rasm saqlandi"); pkCourse(el); } });
  el.querySelectorAll("[data-cdel]").forEach(b => b.onclick = async () => { if (!confirm("Rasm olib tashlansinmi?")) return;
    const r = await pkApi(`/api/paket/assets/${b.dataset.cdel}/delete`, {}); if (r) { toast("Olib tashlandi"); pkCourse(el); } });
  el.querySelector("#pkKb")?.addEventListener("click", async e => {
    const btn = e.currentTarget; btn.disabled = true;   /* await'dan keyin e.currentTarget = null — havola oldindan saqlanadi */
    try {
      const r = await pkApi(`/api/paket/courses/${PK.cid}/course-package`, {mode: el.querySelector("#pkKm").value, only_approved: el.querySelector("#pkKa").checked});
      if (r) { toast(`Kurs paketi tayyor: ${r.topics.length} mavzu`); pkCourse(el); }
    } finally { if (btn.isConnected) btn.disabled = false; }
  });
  await pkTopicPanel(el.querySelector("#pkTp"));
}
async function pkTopicPanel(el) {
  const M = PK.meta, base = `/api/paket/courses/${PK.cid}/topics/${PK.topic}`;
  el.innerHTML = `<div class="pk-empty">Yuklanmoqda…</div>`;
  const d = await pkApi(base), R = d.ready, can = d.can, S = d.settings;
  const reload = () => pkCourse($("#pkCv"));
  const li = (ok, title, desc, extra = "") => `<li class="${ok ? "ok" : "no"}">${ico(ok ? "checkc" : "alert", 18)}<b>${esc(title)}</b><div class="d">${desc}</div>${extra}</li>`;
  const tx = R.text, sl = R.slides, vd = R.video, qz = R.quiz, L = d.lesson, KP = d.keypoints, cv = R.cover, xr = R.exercises, ag = R.assignment, EX = d.exercises;
  const vLink = vd.url && !vd.error ? `${vd.video_id ? `YouTube · <span class="pk-mono">${esc(vd.video_id)}</span>` : "Tashqi havola"} · ${vd.link_src === "paket" ? "shu yerda kiritilgan" : "kontent monitoringidan"}${vd.demo ? " · namuna" : ""}` : "";
  const vFile = vd.file ? `Video fayl · ${esc(vd.file.name)} <small style="display:inline">(${esc(vd.file.kind)}, ${pkSize(vd.file.size)})</small> · subtitr: ${vd.captions.length ? vd.captions.map(x => esc(x.lang)).join(", ") : "yo'q"}${vd.poster ? " · poster bor" : ""}` : "";
  const exN = x => x.kind === "match" ? `${x.pairs.length} juft` : x.kind === "sort" ? `${x.categories.length} toifa, ${x.categories.reduce((a, c) => a + c.items.length, 0)} element` : `${x.cards.length} kartochka`;
  const kpItems = (KP.approved?.items || []), kpDraft = (KP.draft?.items || []);
  const assets = d.assets;
  const aList = kinds => assets.filter(a => kinds.includes(a.purpose));
  const aRow = a => `${esc(a.name)} <small>${esc(a.kind)} · ${pkSize(a.size)} · ${pkD(a.ts)}${a.demo ? " · namuna" : ""}</small>`;
  el.innerHTML = `<div class="pk-grid">
    <div class="card pk-card"><div class="pk-item-h"><h3><span class="pk-code">${esc(L.code)}</span> ${esc(d.topic.title)}</h3>
        ${can.write && L.custom && !L.default ? `<button type="button" class="btn sm ghost" id="pkLd">Darsni o'chirish</button>` : ""}</div>
      <p class="muted">${esc(L.kind_label)}${L.topic ? ` · ${L.topic}-mavzuga bog'langan` : ""} · tayyorgarlik — paket «tayyor» bo'lishi uchun sozlamada yoqilgan bloklarning manbasi kerak</p>
      <ul class="pk-check">
        ${li(cv.ok, "Muqova", cv.ok ? `${cv.image ? `fon rasmi — ${{dars: "shu dars uchun yuklangan", kurs: "kurs muqovasi", standart: "bo'lim standarti"}[cv.src]}` : "rasmsiz (brend rangi)"} · logotip · «${esc(L.code)}: ${esc(d.topic.title)}» · muallif: ${cv.author ? esc(cv.author) : "—"}${cv.custom ? " (tahrirlangan)" : ""}` : "O'chirilgan (sozlamada yoqish mumkin)",
          can.write ? `<div class="pk-acts">${cv.image ? `<img class="pk-thumb muqova" src="/api/paket/assets/${cv.image}" alt="Muqova">` : ""}
            <label class="btn sm pk-file">${ico("upload", 15)} Dars muqovasi (.png, .jpg)<input type="file" accept=".png,.jpg,.jpeg" hidden id="pkCf"></label>
            ${cv.src === "dars" ? `<button type="button" class="btn sm ghost" data-del="${cv.image}">Dars muqovasini olib tashlash</button>` : ""}</div>
            <form class="pk-inline" id="pkCa"><label class="pk-sr" for="pkCu">Muallif</label><input type="text" id="pkCu" maxlength="120" placeholder="Muallif (F.I.Sh.)" value="${esc(cv.author || "")}"><button class="btn sm">Saqlash</button>${cv.custom ? `<button type="button" class="btn sm ghost" id="pkCr">Standart</button>` : ""}</form>` : "")}
        ${li(vd.ok, "Video", vd.ok ? `${vd.provider === "file" ? vFile : vLink}${vd.both ? `<br><span class="muted">Ikkalasi ham bor (${vd.provider === "file" ? vLink : vFile}) — paketga «${esc(M.video_sources[S.video_source])}» kiradi (o'zgartirish: Paket → Video manbasi)</span>` : ""}` :
          vd.error ? `<span class="pk-bad">${esc(vd.error)}</span> · <span class="pk-mono">${esc(vd.url || "")}</span>` : "Yo'q — YouTube havolasini kiriting yoki video fayl (.mp4, .webm) yuklang",
          can.write ? `<form class="pk-inline" id="pkVf"><label class="pk-sr" for="pkVu">YouTube havola</label><input type="url" id="pkVu" placeholder="https://youtu.be/…" value="${esc(vd.link_src === "paket" ? vd.url || "" : "")}"><button class="btn sm">Saqlash</button></form>
            <div class="pk-acts"><label class="btn sm pk-file">${ico("upload", 15)} Video fayl (.mp4, .webm ≤ ${M.limits.video_mb} MB)<input type="file" accept=".mp4,.webm,video/mp4,video/webm" hidden id="pkVm"></label>
              ${vd.file ? `<label class="btn sm ghost pk-file">${ico("upload", 15)} Poster (rasm)<input type="file" accept=".png,.jpg,.jpeg" hidden id="pkVp"></label>
              <select id="pkVl" aria-label="Subtitr tili" class="pk-sel">${Object.entries(M.sub_langs).map(([k, l]) => `<option value="${k}">${esc(l)}</option>`).join("")}</select>
              <label class="btn sm ghost pk-file">${ico("upload", 15)} Subtitr (.vtt, .srt)<input type="file" accept=".vtt,.srt,text/vtt" hidden id="pkVs"></label>` : ""}</div>` : "")}
        ${li(tx.ok, "Ma'ruza matni", tx.ok ? `${esc(tx.name)} · ${fmt(tx.chars)} belgi · ${tx.src === "paket" ? "shu yerda yuklangan" : "Test bankdan"}${tx.demo ? " · namuna" : ""}${tx.only_assignment ? " · matn faqat topshiriqlar ro'yxatidan iborat — «Topshiriq» blokiga o'tdi (alohida matn bloki chiqmaydi)" : ""}` : `Yo'q — Word (.docx: rasmlar va jadvallar bilan) / .pdf / .txt yuklang${L.kind === "maruza" ? " yoki Test bankdagi mavzu matni ishlatiladi" : ""}`,
          can.write ? `<div class="pk-acts"><label class="btn sm pk-file">${ico("upload", 15)} Fayl (.docx, .pdf, .txt)<input type="file" accept=".docx,.pdf,.txt" hidden id="pkTf"></label><button type="button" class="btn sm ghost" id="pkTt">Matn joylashtirish</button></div>` : "")}
        ${li(R.plan.ok, "Reja", R.plan.ok ? `«${esc(R.plan.heading)}» · ${R.plan.n} band · ${R.plan.explicit ? "matndagi «Reja» bo'limidan" : "sarlavhalardan"}` : "Matnda «Reja:» bo'limi yoki sarlavhalar topilmadi — reja bloki bo'lmaydi")}
        ${li(R.images.ok, "Rasmlar va jadvallar", `${R.images.n} ta rasm matnda${R.images.tables ? ` · ${R.images.tables} ta jadval` : ""}${R.images.manual ? ` · ${R.images.manual} ta qo'lda yuklangan` : ""} — Word'dagi rasmlar izohi («1.1-rasm. …») bilan o'z joyida`,
          can.write ? `<div class="pk-acts"><button type="button" class="btn sm ghost" id="pkIb">${ico("upload", 15)} Rasm qo'shish</button></div>` : "")}
        ${li(R.refs.ok, "Foydalanilgan adabiyotlar", R.refs.ok ? `${R.refs.n} ta manba — matndagi «Foydalanilgan adabiyotlar» bo'limidan alohida blok` : "Matnda «Foydalanilgan adabiyotlar» bo'limi topilmadi")}
        ${li(R.keypoints.ok, "Asosiy xulosalar", R.keypoints.ok ? `${R.keypoints.n} ta tasdiqlangan xulosa paketda` : kpDraft.length ? `${kpDraft.length} ta qoralama — tahrirlab tasdiqlang (tasdiqlanmagani paketga kirmaydi)` : "Ixtiyoriy — AI yordamida matndan yoki qo'lda",
          can.write ? `<div class="pk-acts">${M.ai ? `<button type="button" class="btn sm ghost" id="pkKpAi" ${tx.ok ? "" : "disabled"}>AI: asosiy xulosalar</button>` : ""}<button type="button" class="btn sm ghost" id="pkKpEd">Tahrirlash</button></div>` : "")}
        ${li(sl.ok, "Taqdimot", sl.ok ? `${{pptx: "PowerPoint (.pptx)", deck: `«Taqdimot» modulidan: ${esc(sl.deck_title || "")}`, images: "slayd rasmlari", pdf: "PDF sahifalari (rasm)"}[sl.src] || ""} · ${sl.n} slayd${sl.images ? `, ${sl.images} rasm` : ""} · ${sl.display === "images" ? "galereya (rasmlar)" : "matnli slaydlar"}${sl.file ? " · .pptx yuklab olinadi" : ""}` : "Yo'q — PDF (aniq ko'rinish, tavsiya), .pptx yoki slayd rasmlarini (.png, .jpg) yuklang",
          can.write ? `<div class="pk-acts"><label class="btn sm pk-file">${ico("upload", 15)} .pdf / .pptx / rasm<input type="file" accept=".pptx,.pdf,.png,.jpg,.jpeg" multiple hidden id="pkSf"></label>
            ${sl.n ? `<button type="button" class="btn sm ghost" id="pkSe">Slayd izohlari va audio${sl.captions || sl.audio ? ` (${sl.captions} izoh, ${sl.audio} audio)` : ""}</button>` : ""}
            ${d.decks.length ? `<select id="pkDk" aria-label="Taqdimot modulidan" style="height:32px;border-radius:10px;max-width:100%"><option value="0">«Taqdimot» modulidan…</option>${d.decks.map(x => `<option value="${x.id}" ${x.id === sl.deck_id ? "selected" : ""}>${esc(x.title || "Taqdimot #" + x.id)}${x.slides ? ` (${x.slides} slayd)` : ""}</option>`).join("")}</select>` : ""}</div>` : "")}
        ${li(qz.ok, "Test", qz.ok ? `Test bankda ${qz.approved} ta tasdiqlangan savol · paketga ${qz.used} ta${qz.exercises ? ` + ${qz.exercises} ta mashq (moslashtirish / saralash)` : ""}` : L.kind === "maruza" ? "Test bankda bu mavzu bo'yicha tasdiqlangan savol yo'q — mashq (moslashtirish / saralash) qo'shsangiz ham test bloki bo'ladi" : "Test bank — ma'ruza mavzulari bo'yicha; bu darsda mashq (moslashtirish / saralash) qo'shsangiz test bloki bo'ladi",
          typeof renderTestbank === "function" && can.write && L.kind === "maruza" ? `<div class="pk-acts"><button type="button" class="btn sm ghost" id="pkTb">${ico("checkc", 15)} Test bankda ochish</button></div>` : "")}
        ${li(xr.ok, "Mashqlar", `${xr.ok ? `${xr.match} ta moslashtirish · ${xr.sort} ta saralash (test ichida, baholanadi) · ${xr.flashcards} ta kartochkalar to'plami (baholanmaydi)` : "Ixtiyoriy — moslashtirish, saralash, kartochkalar: qo'lda yoki AI yordamida matndan"}${xr.draft ? ` · <b>${xr.draft} ta qoralama</b> — tahrirlab saqlang (qoralama paketga kirmaydi)` : ""}`,
          `${EX.length ? `<ul class="pk-exl">${EX.map(x => `<li><span>${pkChip(x.kind_label, x.status === "qoralama" ? "warn" : "info")} ${esc(x.title)} <small>${exN(x)}${x.status === "qoralama" ? " · qoralama" + (x.ai ? " (AI)" : "") : ""}</small></span>
              ${can.write ? `<span class="pk-acts tight"><button type="button" class="btn sm ghost" data-exe="${x.id}">Tahrirlash</button><button type="button" class="btn sm ghost" data-exd="${x.id}" aria-label="O'chirish">${ico("x", 15)}</button></span>` : ""}</li>`).join("")}</ul>` : ""}
           ${can.write ? `<div class="pk-acts">${Object.entries(M.ex_kinds).map(([k, l]) => `<button type="button" class="btn sm ghost" data-exn="${k}">+ ${esc(l)}</button>`).join("")}
              ${M.ai ? `<button type="button" class="btn sm ghost" id="pkExAi" ${tx.ok ? "" : "disabled"}>AI: mashqlar</button>` : ""}</div>` : ""}`)}
        ${li(ag.ok, "Topshiriq", ag.ok ? `${ag.n} ta savol — ${ag.manual ? "qo'lda kiritilgan" : "ma'ruza matnidagi «Savollar» bo'limidan (matndan olib, shu blokka ko'chirildi)"} · «${esc(ag.text)}» — ${esc(ag.author)} · o'qituvchi rasmi: ${ag.avatar ? "bor" : "yo'q (pleyer belgi chizadi)"}` :
            ag.manual ? "Savollar ro'yxati bo'sh — topshiriq bloki bo'lmaydi" : "Matnda «Savollar» / «Nazorat savollari» / «Topshiriqlar» bo'limi topilmadi — savollarni qo'lda kiriting",
          (ag.warnings || []).map(w => `<div class="pk-warnbox" role="note" style="margin:8px 0 0">${ico("alert", 14)} ${esc(w)}</div>`).join("") +
          (can.write ? `<div class="pk-acts"><button type="button" class="btn sm ghost" id="pkAe">Savollarni tahrirlash</button></div>` : ""))}
        ${li(R.reflect.ok, "O'z-o'zini baholash", R.reflect.ok ? `«${esc(R.reflect.question)}» — baholanmaydi (shablon sozlamasidan)` : "O'chirilgan (sozlamada yoqish mumkin)")}
      </ul>
      ${assets.length ? `<h4>Yuklangan fayllar</h4>${pkTable([["Fayl", a => a.purpose === "rasm" ? `${esc(a.caption || a.name)} <small>matnga qo'yish: <span class="pk-mono">${esc(a.marker)}</span> · ${pkSize(a.size)}</small>` : aRow(a) + (a.caption ? `<small>${esc(a.caption)}</small>` : "")],
         ["Turi", a => esc({matn: "Ma'ruza matni", taqdimot: "Taqdimot", slayd: "Slayd rasmi", fayl: "Qo'shimcha", rasm: "Rasm (matn uchun)", video: "Video fayl", subs: "Subtitr (WebVTT)",
                            poster: "Video posteri", muqova: "Dars muqovasi", audio: "Slayd audiosi"}[a.purpose] || a.purpose)],
         ["", a => `<a class="btn sm ghost" href="/api/paket/assets/${a.id}">${ico("download", 15)}</a>${can.write ? ` <button type="button" class="btn sm ghost" data-del="${a.id}" aria-label="O'chirish">${ico("x", 15)}</button>` : ""}`]], assets)}` : ""}
      ${can.write ? `<div class="pk-acts"><label class="btn sm ghost pk-file">${ico("upload", 15)} Qo'shimcha fayl (.pdf, .docx, .xlsx…)<input type="file" accept=".pdf,.docx,.pptx,.xlsx,.png,.jpg,.jpeg" hidden id="pkFf"></label></div>` : ""}
      <p class="pk-note">Bitta fayl ≤ ${M.limits.asset_mb} MB · video fayl ≤ ${M.limits.video_mb} MB · slayd audiosi ≤ ${M.limits.audio_mb} MB · paket ≤ ${M.limits.package_mb} MB (video fayl bilan ≤ ${M.limits.package_video_mb} MB) · YouTube videosi YouTube'da qoladi (paketga faqat havola kiradi)</p>
    </div>
    <div class="card pk-card"><h3>Paket</h3><p class="muted">Qadamlar: ${d.blocks.map(b => b.type === "section" ? `<b>${esc(b.title)}</b>` : esc(b.title)).join(" → ") || "—"}</p>
      <p class="pk-note" style="margin-top:0">Fayl nomi: <span class="pk-mono">${esc(d.file_name)}</span> — NEXTID'da «${esc(L.code)}» darsiga yuklang</p>
      <form id="pkSet"><div class="pk-form">
        <label>Ko'rinish<select name="layout" ${can.write ? "" : "disabled"}>${Object.entries(M.layouts).map(([k, l]) => `<option value="${k}" ${k === S.layout ? "selected" : ""}>${esc(l)}</option>`).join("")}</select></label>
        <label>Turi (LMS)<select name="mode" ${can.write ? "" : "disabled"}>${Object.entries(M.modes).map(([k, l]) => `<option value="${k}" ${k === S.mode ? "selected" : ""}>${esc(l)}</option>`).join("")}</select></label>
        <label>Yakunlash<select name="completion" ${can.write ? "" : "disabled"}>${Object.entries(M.completion).map(([k, l]) => `<option value="${k}" ${k === S.completion ? "selected" : ""}>${esc(l)}</option>`).join("")}</select></label>
        <label>Video manbasi (ikkalasi bo'lsa)<select name="video_source" ${can.write ? "" : "disabled"}>${Object.entries(M.video_sources).map(([k, l]) => `<option value="${k}" ${k === S.video_source ? "selected" : ""}>${esc(l)}</option>`).join("")}</select></label>
        <label>O'tish foizi<input type="number" name="mastery" min="0" max="100" value="${S.mastery}" ${can.write ? "" : "disabled"}></label>
        <label>Savollar soni (0 — hammasi)<input type="number" name="quiz_n" min="0" max="200" value="${S.quiz_n}" ${can.write ? "" : "disabled"}></label>
        <label>Urinishlar (0 — cheksiz)<input type="number" name="attempts" min="0" max="20" value="${S.attempts}" ${can.write ? "" : "disabled"}></label>
        <label class="cb"><input type="checkbox" name="shuffle" ${S.shuffle ? "checked" : ""} ${can.write ? "" : "disabled"}> Savollarni aralashtirish</label>
        <label class="cb"><input type="checkbox" name="show_feedback" ${S.show_feedback ? "checked" : ""} ${can.write ? "" : "disabled"}> Javobdan keyin izoh</label>
      </div>
      <fieldset class="pk-fs"><legend>Bloklar</legend><div class="pk-checks">${Object.entries(M.blocks).map(([k, l]) => `<label><input type="checkbox" name="b_${k}" ${S.blocks[k] ? "checked" : ""} ${can.write ? "" : "disabled"}> ${esc(l)}</label>`).join("")}</div></fieldset>
      ${can.write ? `<div class="pk-acts"><button class="btn sm">Sozlamani saqlash</button>${Object.keys(d.override).length ? `<button type="button" class="btn sm ghost" id="pkSr">Standartga qaytarish</button>` : ""}
        <span class="pk-note" style="margin:0">${Object.keys(d.override).length ? "Bu mavzu uchun alohida sozlama" : "Standart sozlama"}</span></div>` : ""}</form>
      ${can.write ? `<div class="pk-acts"><button type="button" class="btn primary" id="pkBuild" ${M.player && R.buildable ? "" : "disabled"}>${ico("package", 15)} Paketni yig'ish</button>
        ${R.complete ? pkChip("Manbalar to'liq", "ok") : pkChip("Yetishmaydi: " + R.missing.map(k => M.blocks[k]).join(", "), "warn")}</div>` : ""}
      <h4>Versiyalar</h4>
      ${pkTable([["Versiya", p => `<b>v${p.version}</b> · ${esc(p.mode_label)}<small>${pkD(p.built_at)} · ${esc(p.by || "")}${p.demo ? " · namuna" : ""}</small>`],
        ["Holat", p => `${pkSt(p.status)}${p.approved_name ? `<small>${esc(p.approved_name)}, ${pkD(p.approved_at)}</small>` : ""}${p.note ? `<small class="pk-bad">Qaytarildi: ${esc(p.note)}</small>` : ""}`],
        ["Hajm", p => `${pkSize(p.size)}<small>${p.files} fayl${p.valid ? " · tekshiruvdan o'tgan" : ""}</small>`, "num"],
        ["", p => `<div class="pk-acts tight"><button type="button" class="btn sm" data-prev="${p.id}">${ico("eye", 15)} Ko'rish</button>
           <a class="btn sm ghost" href="/api/paket/packages/${p.id}/download">${ico("download", 15)} Yuklab olish</a>
           ${can.approve && p.status === "tayyor" ? `<button type="button" class="btn sm primary" data-ok="${p.id}">Tasdiqlash</button>` : ""}
           ${can.approve && !p.note ? `<button type="button" class="btn sm ghost" data-rej="${p.id}">Qaytarish</button>` : ""}</div>`]],
        d.packages, {empty: "Hali yig'ilmagan"})}
      <p class="pk-note">Oxirgi ${M.limits.keep} versiya (va tasdiqlangani) saqlanadi. Manba o'zgarmasa, qayta yig'ish yangi versiya yaratmaydi.</p>
    </div></div>
    <div class="pk-grid">
      <details class="card pk-card pk-det" ${R.plan.ok || tx.ok ? "open" : ""}><summary><h3>Reja va ma'ruza matni</h3><span class="muted">paketda qanday ko'rinadi (tozalangan HTML)</span></summary>
        ${R.plan.ok ? `<h4>${esc(d.heading)}</h4><p class="pk-note" style="margin:0">Reja:</p><ol class="pk-plan">${d.plan.map(x => `<li>${esc(x)}</li>`).join("")}</ol>` : ""}
        ${d.text_html ? `<h4>Matn</h4><div class="pk-html">${d.text_html}</div>` : `<div class="pk-empty">Matn yo'q</div>`}
        ${kpItems.length ? `<h4>Asosiy xulosalar</h4><ul class="pk-plan">${kpItems.map(x => `<li>${esc(x)}</li>`).join("")}</ul>` : ""}
        ${d.refs.length ? `<h4>Foydalanilgan adabiyotlar</h4><ol class="pk-plan">${d.refs.map(x => `<li>${esc(x)}</li>`).join("")}</ol>` : ""}</details>
      <details class="card pk-card pk-det" ${sl.ok ? "open" : ""}><summary><h3>Slaydlar</h3><span class="muted">${d.slides.length} ta</span></summary>
        ${d.slides.length ? `<div class="pk-slides">${d.slides.map((s, i) => `<div class="pk-slide"><b>${i + 1}. ${esc(s.title || "Slayd")}</b>${s.bullets.length ? `<ul>${s.bullets.slice(0, 4).map(b => `<li>${esc(b)}</li>`).join("")}</ul>` : ""}<small>${s.image ? "rasm · " : ""}${s.notes ? "ma'ruzachi izohi · " : ""}${s.audio ? "audio · " : ""}${s.caption ? esc(s.caption) : ""}</small></div>`).join("")}</div>` :
          `<div class="pk-empty">${sl.pdf ? "PDF taqdimot — pleyerda sahifalab ko'rsatiladi" : "Slayd yo'q"}</div>`}
        ${ag.ok ? `<h4>Topshiriq (${ag.n} ta savol)</h4><p class="pk-note" style="margin:0">«${esc(ag.text)}» — ${esc(ag.author)}</p><ol class="pk-plan">${ag.items.map(x => `<li>${esc(x)}</li>`).join("")}</ol>` : ""}
        ${d.quiz_preview.length ? `<h4>Test (${d.quiz_preview.length} ta savol)</h4><ol class="pk-plan">${d.quiz_preview.slice(0, 10).map(q => `<li>${esc(q.stem)}${q.type === "match" || q.type === "sort" ? ` <small style="display:inline">(${q.type === "match" ? "moslashtirish" : "saralash"})</small>` : ""}</li>`).join("")}</ol>${d.quiz_preview.length > 10 ? `<p class="pk-note">… yana ${d.quiz_preview.length - 10} ta</p>` : ""}` : ""}
      </details></div>`;
  const tf = el.querySelector("#pkTf");
  if (tf) tf.onchange = async () => { const f = tf.files[0]; if (!f) return; const r = await pkUpload(`${base}/text`, f); if (r) { toast(`Matn saqlandi: ${fmt(r.chars)} belgi, reja: ${r.plan.length} band${r.images ? `, ${r.images} rasm` : ""}${r.tables ? `, ${r.tables} jadval` : ""}${r.refs ? `, ${r.refs} adabiyot` : ""}`); reload(); } };
  el.querySelector("#pkLd")?.addEventListener("click", async () => {
    if (!confirm(`${L.code} darsi ro'yxatdan o'chirilsinmi? (Manbalar va paketlar saqlanib qoladi)`)) return;
    const r = await pkApi(`/api/paket/courses/${PK.cid}/lessons/${PK.topic}/delete`, {}); if (r) { toast("O'chirildi"); PK.topic = 1; reload(); }
  });
  el.querySelector("#pkIb")?.addEventListener("click", () => pkModal(`${L.code}: rasm qo'shish`, `<label>Rasm (.png, .jpg)<input type="file" id="pkIf" accept=".png,.jpg,.jpeg"></label>
      <label>Izoh (ixtiyoriy)<input type="text" id="pkIc" maxlength="300" placeholder="1.3-rasm. …"></label>
      <p class="pk-note">Matnning kerakli joyiga alohida qatorda <span class="pk-mono">[RASM:fayl]</span> belgisini qo'ying (yuklangandan keyin fayllar ro'yxatida ko'rinadi); belgi qo'yilmasa — rasm matn oxirida chiqadi.</p>`, async m => {
    const f = m.querySelector("#pkIf").files[0]; if (!f) { toast("Rasm tanlang"); return false; }
    const r = await pkUpload(`${base}/images`, f, `&caption=${encodeURIComponent(m.querySelector("#pkIc").value.trim())}`);
    if (r) { toast(`Rasm qo'shildi: ${r.marker}`); reload(); return true; }
  }, "Yuklash"));
  const kpEdit = () => {
    const cur = (kpDraft.length ? kpDraft.map(x => x.text) : kpItems);
    const quotes = kpDraft.filter(x => x.quote).map(x => `<li>${esc(x.text)}<small>«${esc(x.quote)}»</small></li>`).join("");
    const bg = pkModal(`${L.code}: asosiy xulosalar`, `<label>Har qatorda bitta xulosa (4–7 ta tavsiya etiladi)<textarea id="pkKx" rows="9">${esc(cur.join("\n"))}</textarea></label>
      ${quotes ? `<details class="pk-det"><summary>AI qoralamasi — matndagi iqtiboslar</summary><ol class="pk-plan">${quotes}</ol></details>` : ""}
      <p class="pk-note">Faqat tasdiqlangan xulosalar paketga kiradi. <button type="button" class="btn sm ghost" data-kpd>Qoralama sifatida saqlash</button> <button type="button" class="btn sm ghost" data-kpc>Hammasini o'chirish</button></p>`, async m => {
      const items = m.querySelector("#pkKx").value.split("\n").map(x => x.trim()).filter(Boolean);
      const r = await pkApi(`${base}/keypoints`, {items, approve: true}); if (r) { toast("Xulosalar tasdiqlandi — paketga kiradi"); pkTopicPanel(el); return true; }
    }, "Tasdiqlash", true);
    bg.querySelector("[data-kpd]").onclick = async () => { const items = bg.querySelector("#pkKx").value.split("\n").map(x => x.trim()).filter(Boolean);
      const r = await pkApi(`${base}/keypoints`, {items, approve: false}); if (r) { toast("Qoralama saqlandi"); bg.remove(); pkTopicPanel(el); } };
    bg.querySelector("[data-kpc]").onclick = async () => { if (!confirm("Xulosalar o'chirilsinmi?")) return;
      const r = await pkApi(`${base}/keypoints`, {items: [], clear: true}); if (r) { toast("O'chirildi"); bg.remove(); pkTopicPanel(el); } };
  };
  el.querySelector("#pkKpEd")?.addEventListener("click", kpEdit);
  el.querySelector("#pkKpAi")?.addEventListener("click", async e => {
    const btn = e.currentTarget; btn.disabled = true; toast("AI matnni o'qiyapti… (faqat dars matni yuboriladi)");
    try {
      const r = await pkApi(`${base}/keypoints/ai`, {});
      if (r) { toast(`AI: ${r.draft.items.length} ta xulosa (qoralama)${r.dropped ? ` · matnga asoslanmagan ${r.dropped} ta tashlandi` : ""}`); await pkTopicPanel(el); $("#pkKpEd")?.click(); }
    } finally { if (btn.isConnected) btn.disabled = false; }
  });
  el.querySelector("#pkTt")?.addEventListener("click", () => pkModal(`${L.code}: ma'ruza matni`, `<label>Matn («Reja:», raqamli sarlavhalar, «Foydalanilgan adabiyotlar», «[RASM:fayl]» avtomatik aniqlanadi)<textarea id="pkTx" rows="14"></textarea></label>`, async m => {
    const r = await pkApi(`${base}/text/paste`, {text: m.querySelector("#pkTx").value});
    if (r) { toast(`Matn saqlandi: ${fmt(r.chars)} belgi`); reload(); return true; }
  }, "Saqlash", true));
  const sf = el.querySelector("#pkSf");
  if (sf) sf.onchange = async () => {
    let n = 0;
    for (const f of [...sf.files]) { const r = await pkUpload(`${base}/slides`, f); if (r) n++; }
    if (n) { toast(`Yuklandi: ${n} ta fayl`); reload(); }
  };
  const ff = el.querySelector("#pkFf");
  if (ff) ff.onchange = async () => { const f = ff.files[0]; if (!f) return; const r = await pkUpload(`${base}/files`, f); if (r) { toast("Fayl qo'shildi"); reload(); } };
  el.querySelector("#pkDk")?.addEventListener("change", async e => { const r = await pkApi(`${base}/deck`, {deck_id: +e.target.value}); if (r) { toast(r.deck_id ? "Taqdimot biriktirildi" : "Uzildi"); reload(); } });
  el.querySelector("#pkVf")?.addEventListener("submit", async e => {
    e.preventDefault();
    const r = await pkApi(`${base}/video`, {url: el.querySelector("#pkVu").value.trim()});
    if (r) { toast(r.url ? `Video saqlandi${r.video?.video_id ? ": " + r.video.video_id : ""}` : "Video olib tashlandi"); reload(); }
  });
  el.querySelector("#pkTb")?.addEventListener("click", () => { if (typeof TB === "object") { TB.cid = PK.cid; TB.topic = PK.topic; } go("testbank", {tab: "mavzu"}); });
  /* --- Rise 360: muqova, video fayl / subtitr / poster, slayd izohi va audiosi, mashqlar, topshiriq --- */
  const upTo = (sel, url, msg, extra, mb) => { const i = el.querySelector(sel); if (i) i.onchange = async () => { const f = i.files[0]; if (!f) return;
    const r = await pkUpload(url, f, extra ? extra() : "", mb); i.value = ""; if (r) { toast(typeof msg === "function" ? msg(r) : msg); reload(); } }; };
  upTo("#pkCf", `${base}/cover`, "Muqova saqlandi");
  upTo("#pkVm", `${base}/video/file`, r => `Video fayl saqlandi (${pkSize(r.size)})`, null, M.limits.video_mb);
  upTo("#pkVp", `${base}/video/poster`, "Poster saqlandi");
  upTo("#pkVs", `${base}/video/captions`, r => `Subtitr saqlandi: ${r.cues} yozuv${r.converted ? " (.srt → WebVTT)" : ""}`, () => `&lang=${encodeURIComponent(el.querySelector("#pkVl").value)}`, M.limits.subs_mb);
  el.querySelector("#pkCa")?.addEventListener("submit", async e => { e.preventDefault();
    const r = await pkApi(`${base}/cover/meta`, {author: el.querySelector("#pkCu").value.trim()}); if (r) { toast("Muallif saqlandi"); pkTopicPanel(el); } });
  el.querySelector("#pkCr")?.addEventListener("click", async () => { const r = await pkApi(`${base}/cover/meta`, {author: null}); if (r) { toast("Standart muallif (kurs o'qituvchisi)"); pkTopicPanel(el); } });
  el.querySelector("#pkSe")?.addEventListener("click", () => {
    // audio yuklash/olib tashlash oynani qayta chizadi — yozilgan, hali saqlanmagan izohlar yo'qolmasin: qiymatlar yangi oynaga ko'chiriladi (PK.capDraft)
    const draft = PK.capDraft && PK.capDraft.base === base ? PK.capDraft.caps : null; PK.capDraft = null;
    const capVal = (n, saved) => draft && draft[n] != null ? draft[n] : saved;
    const bg = pkModal(`${L.code}: slayd izohlari va audio`, `<p class="pk-note" style="margin-top:0">Izoh slayd ostida ko'rinadi; audio (.mp3, .m4a, .ogg, .wav ≤ ${M.limits.audio_mb} MB) — slayd bilan birga tinglanadi. Izohlar «Izohlarni saqlash» bilan, audio darhol saqlanadi (audio yuklanganda yozilgan izohlar oynada qoladi). Taqdimot almashtirilsa, izoh va audio slayd tartib raqami bo'yicha qoladi.</p>
      <div class="pk-srows">${d.slides.map((s, i) => { const a = d.slide_audio[i + 1]; return `<div class="pk-srow"><b>${i + 1}</b><div><small>${esc(s.title || "Slayd " + (i + 1))}</small>
        <input type="text" maxlength="300" data-cap="${i + 1}" value="${esc(capVal(i + 1, s.caption))}" placeholder="Izoh (ixtiyoriy)" aria-label="${i + 1}-slayd izohi">
        <span class="pk-acts tight" style="justify-content:flex-start">${a ? `<small>${ico("checkc", 13)} ${esc(a.name)}</small><button type="button" class="btn sm ghost" data-adel="${a.id}">Audioni olib tashlash</button>` : ""}
          <label class="btn sm ghost pk-file">${ico("upload", 15)} Audio<input type="file" accept=".mp3,.m4a,.ogg,.wav,audio/*" hidden data-aud="${i + 1}"></label></span></div></div>`; }).join("")}</div>`, async m => {
      const captions = {}; m.querySelectorAll("[data-cap]").forEach(i => { captions[i.dataset.cap] = i.value.trim(); });
      const r = await pkApi(`${base}/slides/meta`, {captions}); if (r) { toast(`Izohlar saqlandi: ${Object.keys(r.captions).length} ta`); pkTopicPanel(el); return true; }
    }, "Izohlarni saqlash", true);
    const typed = () => { const o = {}; bg.querySelectorAll("[data-cap]").forEach(i => { o[i.dataset.cap] = i.value; }); return o; };
    const dirty = () => d.slides.some((s, i) => (typed()[i + 1] ?? "").trim() !== (s.caption || ""));
    const reopen = async () => { const caps = typed(); bg.remove(); await pkTopicPanel(el); PK.capDraft = {base, caps}; el.querySelector("#pkSe")?.click(); PK.capDraft = null; };
    bg.querySelectorAll("[data-aud]").forEach(i => i.onchange = async () => { const f = i.files[0]; if (!f) return;
      const r = await pkUpload(`${base}/slides/${i.dataset.aud}/audio`, f, "", M.limits.audio_mb); if (r) { toast(`${i.dataset.aud}-slaydga audio saqlandi${dirty() ? " — izohlar hali saqlanmagan" : ""}`); await reopen(); } });
    bg.querySelectorAll("[data-adel]").forEach(b => b.onclick = async () => { const r = await pkApi(`/api/paket/assets/${b.dataset.adel}/delete`, {}); if (r) { toast(`Audio olib tashlandi${dirty() ? " — izohlar hali saqlanmagan" : ""}`); await reopen(); } });
  });
  el.querySelector("#pkAe")?.addEventListener("click", () => {
    const bg = pkModal(`${L.code}: topshiriq savollari`, `<label>Har qatorda bitta savol yoki topshiriq (ko'pi bilan ${ag.max || 60} ta)<textarea id="pkAq" rows="10">${esc(ag.items.join("\n"))}</textarea></label>
      <p class="pk-note">${ag.manual ? "Hozir: qo'lda kiritilgan ro'yxat." : `Hozir: avtomatik — ma'ruza matnidagi «Savollar» / «Nazorat savollari» / «Topshiriqlar» bo'limidan (${ag.found} ta).`} Blok matni («${esc(ag.text)}») va imzo — Sozlamalarda; o'qituvchi rasmi — kurs kartasida.
        ${ag.manual ? `<button type="button" class="btn sm ghost" data-aauto>Matndan olish (avtomatik)</button>` : ""}</p>`, async m => {
      const r = await pkApi(`${base}/assignment`, {questions: m.querySelector("#pkAq").value.split("\n").map(x => x.trim()).filter(Boolean)});
      if (r) { toast(`Topshiriq savollari saqlandi: ${r.questions.length} ta`); pkTopicPanel(el); return true; }
    }, "Saqlash", true);
    bg.querySelector("[data-aauto]")?.addEventListener("click", async () => { const r = await pkApi(`${base}/assignment`, {questions: null}); if (r) { toast("Savollar matndan olinadi"); bg.remove(); pkTopicPanel(el); } });
  });
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
  el.querySelectorAll("[data-del]").forEach(b => b.onclick = async () => {
    if (!confirm("Fayl o'chirilsinmi?")) return;
    const r = await pkApi(`/api/paket/assets/${b.dataset.del}/delete`, {}); if (r) { toast("O'chirildi"); reload(); }
  });
  el.querySelector("#pkSet")?.addEventListener("submit", async e => {
    e.preventDefault(); if (!can.write) return;
    const f = e.currentTarget, blocks = {};
    Object.keys(M.blocks).forEach(k => blocks[k] = f.elements["b_" + k].checked);
    const r = await pkApi(`${base}/settings`, {layout: f.elements.layout.value, mode: f.elements.mode.value, completion: f.elements.completion.value, mastery: +f.elements.mastery.value, video_source: f.elements.video_source.value,
      quiz_n: +f.elements.quiz_n.value, attempts: +f.elements.attempts.value, shuffle: f.elements.shuffle.checked, show_feedback: f.elements.show_feedback.checked, blocks});
    if (r) { toast("Sozlama saqlandi"); pkTopicPanel(el); }
  });
  el.querySelector("#pkSr")?.addEventListener("click", async () => { const r = await pkApi(`${base}/settings`, {reset: true}); if (r) { toast("Standart sozlama"); pkTopicPanel(el); } });
  el.querySelector("#pkBuild")?.addEventListener("click", async e => {
    const btn = e.currentTarget; btn.disabled = true;
    toast("Paket yig'ilmoqda…");
    const r = await pkApi(`${base}/build`, {});
    if (r) { toast(r.unchanged ? `O'zgarish yo'q — v${r.package.version} amalda` : `Yig'ildi: v${r.package.version} (${pkSize(r.package.size)})`); reload(); } else btn.disabled = false;
  });
  el.querySelectorAll("[data-prev]").forEach(b => b.onclick = () => pkPreview(d.packages.find(p => p.id === +b.dataset.prev)));
  el.querySelectorAll("[data-ok]").forEach(b => b.onclick = async () => { const r = await pkApi(`/api/paket/packages/${b.dataset.ok}/action`, {action: "approve"}); if (r) { toast("Tasdiqlandi"); PK.meta = null; PK.meta = await pkApi("/api/paket/meta"); reload(); } });
  el.querySelectorAll("[data-rej]").forEach(b => b.onclick = () => pkModal("Paketni qaytarish", `<label>Sabab (o'qituvchiga ko'rinadi)<textarea id="pkRn" rows="4" style="min-height:90px"></textarea></label>`, async m => {
    const r = await pkApi(`/api/paket/packages/${b.dataset.rej}/action`, {action: "reject", note: m.querySelector("#pkRn").value.trim()});
    if (r) { toast("Qaytarildi"); reload(); return true; }
  }, "Qaytarish"));
}

/* ---------- Mashq muharriri (oddiy formalar): moslashtirish — juftlar; saralash — toifalar va elementlar; kartochkalar — old/orqa ---------- */
function pkExEdit(base, x, L, done) {
  const k = x.kind, lab = PK.meta.ex_kinds[k], val = v => esc(v || "");
  const pair = (a, b, pa, pb, n) => `<div class="pk-row2"><input type="text" data-a maxlength="200" value="${val(a)}" placeholder="${pa}" aria-label="${n}: ${pa}"><input type="text" data-b maxlength="500" value="${val(b)}" placeholder="${pb}" aria-label="${n}: ${pb}"></div>`;
  const rows = k === "match" ? Array.from({length: 8}, (_, i) => x.pairs?.[i] || {}) : k === "flashcards" ? [...(x.cards || []), ...Array.from({length: Math.max(3, 6 - (x.cards || []).length)}, () => ({}))].slice(0, 40) : [];
  const body = k === "match" ? `<label>Topshiriq matni<input type="text" id="pkXs" maxlength="300" value="${val(x.title)}" placeholder="Mos juftlarni toping"></label>
      <p class="pk-note" style="margin:0 0 6px">2–8 juft: chapda atama, o'ngda ta'rifi. Bo'sh qatorlar hisobga olinmaydi; qiymatlar takrorlanmasin. Pleyer o'ng tomonni aralashtirib beradi.</p>
      <div id="pkXr">${rows.map((p, i) => pair(p.left, p.right, "Atama", "Ta'rifi / mos qiymat", i + 1)).join("")}</div>`
    : k === "sort" ? `<label>Topshiriq matni<input type="text" id="pkXs" maxlength="300" value="${val(x.title)}" placeholder="Elementlarni toifalarga ajrating"></label>
      <p class="pk-note" style="margin:0 0 6px">2–4 toifa, har birida 1–8 element (har qatorda bitta). Element faqat bitta toifada bo'lsin. Pleyer elementlarni aralashtirib, kartochka sifatida beradi.</p>
      <div class="pk-cats">${[0, 1, 2, 3].map(i => { const c = x.categories?.[i] || {}; return `<div class="pk-cat"><input type="text" data-ct maxlength="80" value="${val(c.title)}" placeholder="${i + 1}-toifa nomi${i > 1 ? " (ixtiyoriy)" : ""}" aria-label="${i + 1}-toifa nomi">
        <textarea data-ci rows="5" placeholder="Elementlar — har qatorda bitta" aria-label="${i + 1}-toifa elementlari">${val((c.items || []).join("\n"))}</textarea></div>`; }).join("")}</div>`
    : `<label>Sarlavha<input type="text" id="pkXs" maxlength="80" value="${val(x.title)}" placeholder="Kartochkalar"></label>
      <p class="pk-note" style="margin:0 0 6px">1–40 kartochka: old tomonda atama yoki savol, orqada javob. Bo'sh qatorlar hisobga olinmaydi. Baholanmaydi.</p>
      <div id="pkXr">${rows.map((c, i) => pair(c.front, c.back, "Old tomon", "Orqa tomon", i + 1)).join("")}</div>
      <div class="pk-acts"><button type="button" class="btn sm ghost" id="pkXm">+ Yana 3 qator</button></div>`;
  const quotes = (x.quotes || []).filter(q => q.quote).map(q => `<li>${esc(q.text)}<small>«${esc(q.quote)}»</small></li>`).join("");
  const bg = pkModal(`${L.code}: ${lab}${x.id ? "" : " (yangi)"}`, `${x.status === "qoralama" ? `<p class="pk-warnbox">${ico("info", 15)}<span>${x.ai ? "AI qoralamasi" : "Qoralama"} — tekshirib, kerak bo'lsa tahrirlang. «Saqlash» bosilgach paketga kiradi.</span></p>` : ""}${body}
    ${k !== "flashcards" ? `<label style="margin-top:10px">Izoh (javobdan keyin ko'rsatiladi, ixtiyoriy)<input type="text" id="pkXe" maxlength="500" value="${val(x.explanation)}"></label>` : ""}
    ${quotes ? `<details class="pk-det"><summary>AI — matndagi iqtiboslar</summary><ol class="pk-plan">${quotes}</ol></details>` : ""}`, async m => {
    const b = {kind: k, status: "faol", explanation: m.querySelector("#pkXe")?.value.trim() || ""};
    b[k === "flashcards" ? "title" : "stem"] = m.querySelector("#pkXs").value.trim();
    const two = () => [...m.querySelectorAll(".pk-row2")].map(r => [r.querySelector("[data-a]").value.trim(), r.querySelector("[data-b]").value.trim()]).filter(r => r[0] || r[1]);
    if (k === "match") b.pairs = two().map(([left, right]) => ({left, right}));
    else if (k === "flashcards") b.cards = two().map(([front, back]) => ({front, back}));
    else b.categories = [...m.querySelectorAll(".pk-cat")].map(c => ({title: c.querySelector("[data-ct]").value.trim(), items: c.querySelector("[data-ci]").value.split("\n").map(v => v.trim()).filter(Boolean)})).filter(c => c.title || c.items.length);
    const r = await pkApi(x.id ? `/api/paket/exercises/${x.id}` : `${base}/exercises`, b);
    if (r) { toast(`${lab} saqlandi — paketga kiradi`); done(); return true; }
  }, "Saqlash", true);
  bg.querySelector("#pkXm")?.addEventListener("click", () => { const box = bg.querySelector("#pkXr"), n = box.children.length;
    if (n >= 40) { toast("Ko'pi bilan 40 ta kartochka"); return; }
    box.insertAdjacentHTML("beforeend", Array.from({length: Math.min(3, 40 - n)}, (_, i) => pair("", "", "Old tomon", "Orqa tomon", n + i + 1)).join("")); });
}

/* ---------- Avtomatik joylash ---------- */
async function pkBulk(box) {
  const M = PK.meta;
  box.innerHTML = `<div id="pkPk"></div><div class="pk-grid">
    <div class="card pk-card"><h3>Video havolalarni joylash</h3>
      <p class="muted">Har qatorda bitta YouTube havola — L1 (1-mavzu) dan boshlab ketma-ket joylanadi. Aniq darsga: «5: https://youtu.be/…» yoki dars kodi bilan «A3: https://youtu.be/…». watch, youtu.be, shorts, embed va t= (boshlanish vaqti) qo'llab-quvvatlanadi.</p>
      <label class="pk-sr" for="pkBt">Havolalar</label><textarea id="pkBt" class="pk-ta" placeholder="https://www.youtube.com/watch?v=…&#10;https://youtu.be/…&#10;7: https://youtu.be/…"></textarea>
      <div class="pk-acts"><button type="button" class="btn sm" id="pkBc">Tekshirish</button><button type="button" class="btn sm primary" id="pkBs">Saqlash</button></div>
      <div id="pkBr"></div></div>
    <div class="card pk-card"><h3>Ommaviy yig'ish</h3>
      <p class="muted">Kursning manbasi bor barcha darslari (L, A, …) uchun paket yig'iladi. Manba o'zgarmagan dars qayta yig'ilmaydi.</p>
      <div class="pk-form"><label>Turi<select id="pkGm"><option value="">Mavzu sozlamasi bo'yicha</option>${Object.entries(M.modes).map(([k, l]) => `<option value="${k}">${esc(l)}</option>`).join("")}</select></label>
        <label class="cb"><input type="checkbox" id="pkGc" checked> Faqat manbasi to'liq darslar</label></div>
      <div class="pk-acts"><button type="button" class="btn primary" id="pkGo" ${M.player ? "" : "disabled"}>${ico("package", 15)} Hammasini yig'ish</button></div>
      <div id="pkGr"></div></div></div>`;
  const run = async apply => {
    if (!PK.cid) { toast("Kurs tanlang"); return; }
    const text = box.querySelector("#pkBt").value;
    if (!text.trim()) { toast("Havolalarni kiriting"); return; }
    const r = await pkApi(`/api/paket/courses/${PK.cid}/bulk/videos`, {text, apply});
    if (!r) return;
    if (apply) toast(`Saqlandi: ${r.assigned} ta mavzu${r.errors ? `, xato: ${r.errors}` : ""}`);
    box.querySelector("#pkBr").innerHTML = pkTable([["Qator", x => x.line, "num"], ["Dars", x => `<b>${esc(x.code || x.topic_no)}</b> ${esc(x.title || "")}`],
      ["Havola", x => `<span class="pk-mono">${esc(x.url)}</span>${x.ok ? `<small>${x.provider === "youtube" ? "YouTube · " + esc(x.video_id) : "tashqi havola"}</small>` : `<small class="pk-bad">${esc(x.error)}</small>`}`],
      ["", x => x.ok ? pkChip(apply ? "joylandi" : "to'g'ri", "ok") : pkChip("xato", "bad")]], r.rows, {empty: "Havola topilmadi"});
  };
  box.querySelector("#pkBc").onclick = () => run(false);
  box.querySelector("#pkBs").onclick = () => run(true);
  box.querySelector("#pkGo").onclick = async e => {
    if (!PK.cid) { toast("Kurs tanlang"); return; }
    const btn = e.currentTarget; btn.disabled = true;
    const out = box.querySelector("#pkGr");
    out.innerHTML = `<p class="pk-note">${ico("clock", 14)} Yig'ilmoqda… Bir necha daqiqa davom etishi mumkin.</p>`;
    try {
      const r = await pkApi(`/api/paket/courses/${PK.cid}/bulk/build`, {mode: box.querySelector("#pkGm").value || null, only_complete: box.querySelector("#pkGc").checked});
      if (!r) { out.innerHTML = ""; return; }
      toast(`Yig'ildi: ${r.built} · o'zgarmagan: ${r.unchanged} · o'tkazildi: ${r.skipped}${r.failed ? ` · xato: ${r.failed}` : ""}`);
      out.innerHTML = `<p class="pk-note">Yig'ildi: ${r.built} · o'zgarmagan: ${r.unchanged} · o'tkazildi: ${r.skipped} · xato: ${r.failed}</p>` +
        pkTable([["Dars", x => esc(x.code || x.no)], ["Natija", x => x.ok ? (x.unchanged ? `o'zgarmagan · v${x.version}` : `yig'ildi · v${x.version} · ${esc((PK_ST[x.status] || [x.status])[0])}`) : `<span class="${x.skipped ? "" : "pk-bad"}">${esc(x.error)}</span>`]], r.results);
    } finally { if (btn.isConnected) btn.disabled = false; }
  };
  await pkPicker(box.querySelector("#pkPk"), () => { box.querySelector("#pkBr").innerHTML = ""; box.querySelector("#pkGr").innerHTML = ""; });
}

/* ---------- Sozlamalar ---------- */
async function pkSettings(box) {
  const M = PK.meta, S = M.defaults, ed = M.caps.settings;
  box.innerHTML = `<div class="pk-grid">
    <div class="card pk-card"><h3>Standart sozlamalar</h3><p class="muted">Har bir mavzu uchun alohida o'zgartirish mumkin (Mavzular → Paket).</p>
      <form id="pkDf"><div class="pk-form">
        <label>Turi (LMS)<select name="mode" ${ed ? "" : "disabled"}>${Object.entries(M.modes).map(([k, l]) => `<option value="${k}" ${k === S.mode ? "selected" : ""}>${esc(l)}</option>`).join("")}</select></label>
        <label>Yakunlash<select name="completion" ${ed ? "" : "disabled"}>${Object.entries(M.completion).map(([k, l]) => `<option value="${k}" ${k === S.completion ? "selected" : ""}>${esc(l)}</option>`).join("")}</select></label>
        <label>O'tish foizi<input type="number" name="mastery" min="0" max="100" value="${S.mastery}" ${ed ? "" : "disabled"}></label>
        <label>Savollar soni (0 — hammasi)<input type="number" name="quiz_n" min="0" max="200" value="${S.quiz_n}" ${ed ? "" : "disabled"}></label>
        <label>Urinishlar (0 — cheksiz)<input type="number" name="attempts" min="0" max="20" value="${S.attempts}" ${ed ? "" : "disabled"}></label>
        <label class="cb"><input type="checkbox" name="shuffle" ${S.shuffle ? "checked" : ""} ${ed ? "" : "disabled"}> Savollarni aralashtirish</label>
        <label class="cb"><input type="checkbox" name="show_feedback" ${S.show_feedback ? "checked" : ""} ${ed ? "" : "disabled"}> Javobdan keyin izoh</label>
      </div>
      <fieldset class="pk-fs"><legend>Bloklar</legend><div class="pk-checks">${Object.entries(M.blocks).map(([k, l]) => `<label><input type="checkbox" name="b_${k}" ${S.blocks[k] ? "checked" : ""} ${ed ? "" : "disabled"}> ${esc(l)}</label>`).join("")}</div></fieldset>
      <fieldset class="pk-fs"><legend>Kafedra shabloni</legend><div class="pk-form">
        <label>Ko'rinish<select name="layout" ${ed ? "" : "disabled"}>${Object.entries(M.layouts).map(([k, l]) => `<option value="${k}" ${k === S.layout ? "selected" : ""}>${esc(l)}</option>`).join("")}</select></label>
        <label>Video manbasi (fayl va havola ikkalasi bo'lsa)<select name="video_source" ${ed ? "" : "disabled"}>${Object.entries(M.video_sources).map(([k, l]) => `<option value="${k}" ${k === S.video_source ? "selected" : ""}>${esc(l)}</option>`).join("")}</select></label>
        ${Object.entries({video: "Video bo'limi", text: "Matn bo'limi", slides: "Taqdimot bo'limi", practice: "Mashq va topshiriq bo'limi"}).map(([k, l]) => `<label>${esc(l)} sarlavhasi<input type="text" name="s_${k}" maxlength="80" value="${esc(S.sections[k])}" ${ed ? "" : "disabled"}></label>`).join("")}
      </div></fieldset>
      <fieldset class="pk-fs"><legend>O'z-o'zini baholash (baholanmaydi)</legend><div class="pk-form">
        <label class="pk-wide">Savol<input type="text" name="r_q" maxlength="300" value="${esc(S.reflect.question)}" ${ed ? "" : "disabled"}></label>
        ${[0, 1].map(i => `<label>${i + 1}-javob<input type="text" name="r_t${i}" maxlength="120" value="${esc(S.reflect.options[i]?.text || "")}" ${ed ? "" : "disabled"}></label>
          <label>${i + 1}-javobga izoh<input type="text" name="r_f${i}" maxlength="500" value="${esc(S.reflect.options[i]?.feedback || "")}" ${ed ? "" : "disabled"}></label>`).join("")}
      </div><p class="pk-note">Yoqish/o'chirish — «Bloklar»da («O'z-o'zini baholash»). Mavzu bo'yicha alohida o'zgartirish mumkin.</p></fieldset>
      <fieldset class="pk-fs"><legend>Topshiriq bloki (o'qituvchi rasmi + matn + savollar)</legend><div class="pk-form">
        <label>Sarlavha<input type="text" name="a_title" maxlength="80" value="${esc(S.assignment.title)}" ${ed ? "" : "disabled"}></label>
        <label>Imzo<input type="text" name="a_author" maxlength="120" value="${esc(S.assignment.author)}" ${ed ? "" : "disabled"}></label>
        <label class="pk-wide">Matn<input type="text" name="a_text" maxlength="400" value="${esc(S.assignment.text)}" ${ed ? "" : "disabled"}></label>
      </div><p class="pk-note">Savollar — ma'ruza matnidagi «Savollar» / «Nazorat savollari» / «Topshiriqlar» / «Mustaqil ish topshiriqlari» bo'limidan avtomatik olinadi (matndan shu blokka ko'chadi) yoki dars panelida qo'lda kiritiladi. O'qituvchi rasmi — kurs kartasida.</p></fieldset>
      ${ed ? `<div class="pk-acts"><button class="btn sm primary">Saqlash</button></div>` : `<p class="pk-note">O'zgartirish — Masofaviy ta'lim bo'limida.</p>`}</form>
      <h4>Standart muqova (bo'lim)</h4><div class="pk-media"><div>${M.default_cover ? `<img class="pk-thumb muqova" src="/api/paket/assets/${M.default_cover}" alt="Standart muqova">` : `<div class="pk-thumb muqova none">yo'q</div>`}
        <div><p class="pk-note" style="margin:0 0 6px">Dars muqovasi: fon rasmi + ISFT logotipi + «L1-1-dars: MAVZU» + muallif. Rasm ustuvorligi: dars → kurs → shu standart; hech biri bo'lmasa — brend rangi. Rasm ≤ 1920 px JPEG'ga keltiriladi.</p>
        ${ed ? `<div class="pk-acts tight" style="justify-content:flex-start"><label class="btn sm pk-file">${ico("upload", 15)} Rasm (.png, .jpg)<input type="file" accept=".png,.jpg,.jpeg" hidden id="pkDc"></label>
          ${M.default_cover ? `<button type="button" class="btn sm ghost" id="pkDx">Olib tashlash</button>` : ""}</div>` : ""}</div></div></div></div>
    <div class="card pk-card"><h3>LMS'ga yuklash</h3>
      <h4>NEXTID.LMS (my.isft.uz) — «Articulate» yorlig'i</h4>${pkNextidHelp()}
      <h4>Moodle va boshqa LMS (SCORM 1.2 — eng universal)</h4>
      <ol class="pk-steps"><li>Kursda tahrirlash rejimini yoqing → kerakli bo'limda «Faoliyat yoki resurs qo'shish» → <b>SCORM paketi</b>.</li>
        <li>Nom yozing va paket faylini (.zip, ochmasdan) yuklang.</li><li>«Baholash»: baholash usuli — «Eng yuqori urinish»; «Yakunlash»: «Talab qilingan holat — o'tdi / tugallandi».</li>
        <li>Saqlang va «Ko'rish» orqali tekshiring.</li></ol>
      <h4>SCORM 2004</h4><p class="pk-note">Moodle SCORM 2004 ni qisman qo'llaydi; LMS aniq 2004 talab qilsa ishlating, aks holda 1.2 ni tanlang.</p>
      <h4>xAPI (Tin Can)</h4><p class="pk-note">NEXTID uchun standart. Boshqa LMS'da LRS (Learning Record Store) yoki plagin kerak; launch parametrlari bo'lsa natija LRS'ga yuboriladi.</p>
      <h4>Kurs paketi</h4><p class="pk-note">Mavzular → «Kurs paketi»: bitta zip'da barcha darslar (har biri alohida SCO, o'z papkasida: t01, a01, …).</p>
      <h4>Cheklovlar</h4><p class="pk-note">Fayl ≤ ${M.limits.asset_mb} MB, video fayl ≤ ${M.limits.video_mb} MB (.mp4 / .webm), slayd audiosi ≤ ${M.limits.audio_mb} MB, paket ≤ ${M.limits.package_mb} MB (video fayl bilan ≤ ${M.limits.package_video_mb} MB). YouTube videosi YouTube'da qoladi (paketga havola kiradi). Eski .ppt qabul qilinmaydi — .pptx qilib saqlang.</p>
      <h4>Articulate Rise 360 bilan farqi</h4><p class="pk-note">Avtomatik: muqova, video (fayl yoki YouTube), ma'ruza matni Word'dan (reja, rasm, jadval, adabiyotlar), taqdimot galereyasi (izoh va audio bilan), kartochkalar, test + moslashtirish / saralash, topshiriq, o'z-o'zini baholash. Yo'q: bloklarni sichqoncha bilan erkin joylashtirish muharriri (tartib — kafedra shabloni), AI subtitr va AI ovoz (nutq xizmati kerak) — subtitr va audio tayyor fayl sifatida yuklanadi.</p></div></div>`;
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
