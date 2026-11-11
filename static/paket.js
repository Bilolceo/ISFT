/* =====================================================================
   «Kontent paketlari» (app/paket.py, /api/paket) — mavzu bo'yicha SCORM 1.2 / SCORM 2004 / xAPI paket (Articulate o'rniga).
     Qamrov:           kafedra / o'qituvchi / kurs kesimida — paketi yig'ilgan va tasdiqlangan mavzular, manbalar tayyorligi.
     Mavzular:         mavzu manbalari (ma'ruza matni + reja, taqdimot, YouTube video, Test bankdagi tasdiqlangan test),
                       sozlamalar, yig'ish, ko'rish (pleyer), yuklab olish, tasdiqlash / qaytarish (bo'lim); kurs paketi.
     Avtomatik joylash: YouTube havolalar ro'yxati → 1..n mavzular; tayyor mavzularni ommaviy yig'ish.
     Sozlamalar:       standart paket turi, yakunlash qoidasi, o'tish foizi; Moodle'ga yuklash yo'riqnomasi.
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
async function pkUpload(url, file) {
  const M = PK.meta;
  if (file.size > M.limits.asset_mb * 1048576) { toast(`Fayl ${M.limits.asset_mb} MB dan katta`); return null; }
  toast("Yuklanmoqda…");
  return pkApi(`${url}?name=${encodeURIComponent(file.name)}`, file);
}
const pkPrevUrl = id => `/api/paket/packages/${id}/preview/index.html`;
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
  v.innerHTML = `<div class="pk-head"><div><h2>Kontent paketlari</h2><span class="muted">${esc(M.scope)} · mavzu bo'yicha SCORM / xAPI paket: ma'ruza matni va reja, taqdimot, video, test</span></div>
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
      ${pkKpi("Video / test", `${fmt(t.video)} / ${fmt(t.quiz)}`, "yaroqli havola · tasdiqlangan savollar")}
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
  el.innerHTML = `<div class="card pk-card"><div class="pk-item-h"><div><h3>${esc(c.subject)}</h3>
      <p class="muted">${esc(c.direction)} · ${c.course}-kurs · ${esc(c.dept || "—")} · mas'ul: ${esc(c.teacher || "—")} · belgilar: M — matn, T — taqdimot, V — video, S — test</p></div></div>
    <div class="pk-topics" role="list">${d.topics.map(t => `<button type="button" role="listitem" class="pk-topic ${t.no === PK.topic ? "on" : ""}" data-no="${t.no}" aria-pressed="${t.no === PK.topic}">
        <span class="no">${t.no}</span><span class="tt">${esc(t.title)}</span>${pkRd(t)}
        <span class="st">${t.approved ? `<span class="ok">tasdiqlangan</span>` : t.last ? (t.last.status === "tayyor" ? `<span class="info">tasdiq kutilmoqda</span>` : "qoralama") : "paket yo'q"}${t.last ? ` · v${t.last.version}` : ""}</span></button>`).join("")}</div>
    ${d.can.write ? `<details class="pk-det" style="margin-top:12px"><summary><b>Kurs paketi</b><span class="muted">bitta manifestda barcha mavzular (har biri alohida SCO)${last ? ` · oxirgisi v${last.version}, ${pkD(last.built_at)}` : ""}</span></summary>
      <div class="pk-form"><label>Turi<select id="pkKm">${["scorm12", "scorm2004", "xapi"].map(m => `<option value="${m}">${esc(M.modes[m])}</option>`).join("")}</select></label>
        <label class="cb"><input type="checkbox" id="pkKa"> Faqat tasdiqlangan mavzular</label>
        <div class="pk-acts"><button type="button" class="btn sm primary" id="pkKb" ${M.player ? "" : "disabled"}>${ico("package", 15)} Kurs paketini yig'ish</button></div></div>
      ${d.course_packages.length ? pkTable([["Versiya", p => `v${p.version} · ${esc(p.mode_label)}<small>${pkD(p.built_at)} · ${esc(p.by || "")}</small>`],
        ["Mavzular", p => `${(p.settings.topics || []).length} ta`, "num"], ["Hajm", p => pkSize(p.size), "num"],
        ["", p => `<a class="btn sm ghost" href="/api/paket/packages/${p.id}/download">${ico("download", 15)} Yuklab olish</a>`]], d.course_packages) : ""}</details>` : ""}</div>
    <div id="pkTp"></div>`;
  el.querySelectorAll(".pk-topic").forEach(b => b.onclick = () => { PK.topic = +b.dataset.no; pkCourse(el); });
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
  const tx = R.text, sl = R.slides, vd = R.video, qz = R.quiz;
  const assets = d.assets;
  const aList = kinds => assets.filter(a => kinds.includes(a.purpose));
  const aRow = a => `${esc(a.name)} <small>${esc(a.kind)} · ${pkSize(a.size)} · ${pkD(a.ts)}${a.demo ? " · namuna" : ""}</small>`;
  el.innerHTML = `<div class="pk-grid">
    <div class="card pk-card"><h3>${d.topic.no}-mavzu: ${esc(d.topic.title)}</h3><p class="muted">Tayyorgarlik — paket «tayyor» bo'lishi uchun sozlamada yoqilgan bloklarning manbasi kerak</p>
      <ul class="pk-check">
        ${li(tx.ok, "Ma'ruza matni", tx.ok ? `${esc(tx.name)} · ${fmt(tx.chars)} belgi · ${tx.src === "paket" ? "shu yerda yuklangan" : "Test bankdan"}${tx.demo ? " · namuna" : ""}` : "Yo'q — .docx / .pdf / .txt yuklang yoki Test bankdagi mavzu matni ishlatiladi",
          can.write ? `<div class="pk-acts"><label class="btn sm pk-file">${ico("upload", 15)} Fayl (.docx, .pdf, .txt)<input type="file" accept=".docx,.pdf,.txt" hidden id="pkTf"></label><button type="button" class="btn sm ghost" id="pkTt">Matn joylashtirish</button></div>` : "")}
        ${li(R.plan.ok, "Reja", R.plan.ok ? `${R.plan.n} band · ${R.plan.explicit ? "matndagi «Reja» bo'limidan" : "sarlavhalardan"}` : "Matnda «Reja:» bo'limi yoki sarlavhalar topilmadi — reja bloki bo'lmaydi")}
        ${li(sl.ok, "Taqdimot", sl.ok ? `${{pptx: "PowerPoint (.pptx)", deck: `«Taqdimot» modulidan: ${esc(sl.deck_title || "")}`, images: "slayd rasmlari", pdf: "PDF"}[sl.src] || ""} · ${sl.n} slayd${sl.images ? `, ${sl.images} rasm` : ""}${sl.file ? " · .pptx yuklab olinadi" : ""}${sl.pdf ? " · PDF brauzerda" : ""}` : "Yo'q — .pptx (tavsiya), .pdf yoki slayd rasmlarini (.png, .jpg) yuklang",
          can.write ? `<div class="pk-acts"><label class="btn sm pk-file">${ico("upload", 15)} .pptx / .pdf / rasm<input type="file" accept=".pptx,.pdf,.png,.jpg,.jpeg" multiple hidden id="pkSf"></label>
            ${d.decks.length ? `<select id="pkDk" aria-label="Taqdimot modulidan" style="height:32px;border-radius:10px;max-width:100%"><option value="0">«Taqdimot» modulidan…</option>${d.decks.map(x => `<option value="${x.id}" ${x.id === sl.deck_id ? "selected" : ""}>${esc(x.title || "Taqdimot #" + x.id)}${x.slides ? ` (${x.slides} slayd)` : ""}</option>`).join("")}</select>` : ""}</div>` : "")}
        ${li(vd.ok, "Video", vd.ok ? `${vd.provider === "youtube" ? `YouTube · <span class="pk-mono">${esc(vd.video_id)}</span>` : "Tashqi havola"} · ${vd.src === "paket" ? "shu yerda kiritilgan" : "kontent monitoringidan"}${vd.demo ? " · namuna" : ""}` :
          vd.error ? `<span class="pk-bad">${esc(vd.error)}</span> · <span class="pk-mono">${esc(vd.url || "")}</span>` : "Yo'q — YouTube havolasini kiriting",
          can.write ? `<form class="pk-inline" id="pkVf"><label class="pk-sr" for="pkVu">YouTube havola</label><input type="url" id="pkVu" placeholder="https://youtu.be/…" value="${esc(vd.src === "paket" ? vd.url || "" : "")}"><button class="btn sm">Saqlash</button></form>` : "")}
        ${li(qz.ok, "Test", qz.ok ? `Test bankda ${qz.approved} ta tasdiqlangan savol · paketga ${qz.used} ta` : "Test bankda bu mavzu bo'yicha tasdiqlangan savol yo'q",
          typeof renderTestbank === "function" && can.write ? `<div class="pk-acts"><button type="button" class="btn sm ghost" id="pkTb">${ico("checkc", 15)} Test bankda ochish</button></div>` : "")}
      </ul>
      ${aList(["matn", "taqdimot", "slayd", "fayl"]).length ? `<h4>Yuklangan fayllar</h4>${pkTable([["Fayl", aRow], ["Turi", a => esc({matn: "Ma'ruza matni", taqdimot: "Taqdimot", slayd: "Slayd rasmi", fayl: "Qo'shimcha"}[a.purpose] || a.purpose)],
         ["", a => `<a class="btn sm ghost" href="/api/paket/assets/${a.id}">${ico("download", 15)}</a>${can.write ? ` <button type="button" class="btn sm ghost" data-del="${a.id}" aria-label="O'chirish">${ico("x", 15)}</button>` : ""}`]], assets)}` : ""}
      ${can.write ? `<div class="pk-acts"><label class="btn sm ghost pk-file">${ico("upload", 15)} Qo'shimcha fayl (.pdf, .docx, .xlsx…)<input type="file" accept=".pdf,.docx,.pptx,.xlsx,.png,.jpg,.jpeg" hidden id="pkFf"></label></div>` : ""}
      <p class="pk-note">Bitta fayl ≤ ${M.limits.asset_mb} MB · paket ≤ ${M.limits.package_mb} MB · video YouTube'da qoladi (paketga faqat havola kiradi)</p>
    </div>
    <div class="card pk-card"><h3>Paket</h3><p class="muted">Bloklar: ${d.blocks.map(b => esc(b.title)).join(" → ") || "—"}</p>
      <form id="pkSet"><div class="pk-form">
        <label>Turi (LMS)<select name="mode" ${can.write ? "" : "disabled"}>${Object.entries(M.modes).map(([k, l]) => `<option value="${k}" ${k === S.mode ? "selected" : ""}>${esc(l)}</option>`).join("")}</select></label>
        <label>Yakunlash<select name="completion" ${can.write ? "" : "disabled"}>${Object.entries(M.completion).map(([k, l]) => `<option value="${k}" ${k === S.completion ? "selected" : ""}>${esc(l)}</option>`).join("")}</select></label>
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
        ${R.plan.ok ? `<h4>Reja</h4><ol class="pk-plan">${d.plan.map(x => `<li>${esc(x)}</li>`).join("")}</ol>` : ""}
        ${d.text_html ? `<h4>Matn</h4><div class="pk-html">${d.text_html}</div>` : `<div class="pk-empty">Matn yo'q</div>`}</details>
      <details class="card pk-card pk-det" ${sl.ok ? "open" : ""}><summary><h3>Slaydlar</h3><span class="muted">${d.slides.length} ta</span></summary>
        ${d.slides.length ? `<div class="pk-slides">${d.slides.map((s, i) => `<div class="pk-slide"><b>${i + 1}. ${esc(s.title || "Slayd")}</b>${s.bullets.length ? `<ul>${s.bullets.slice(0, 4).map(b => `<li>${esc(b)}</li>`).join("")}</ul>` : ""}<small>${s.image ? "rasm · " : ""}${s.notes ? "izoh" : ""}</small></div>`).join("")}</div>` :
          `<div class="pk-empty">${sl.pdf ? "PDF taqdimot — pleyerda sahifalab ko'rsatiladi" : "Slayd yo'q"}</div>`}
        ${d.quiz_preview.length ? `<h4>Test (${d.quiz_preview.length} ta savol)</h4><ol class="pk-plan">${d.quiz_preview.slice(0, 10).map(q => `<li>${esc(q.stem)}</li>`).join("")}</ol>${d.quiz_preview.length > 10 ? `<p class="pk-note">… yana ${d.quiz_preview.length - 10} ta</p>` : ""}` : ""}
      </details></div>`;
  const tf = el.querySelector("#pkTf");
  if (tf) tf.onchange = async () => { const f = tf.files[0]; if (!f) return; const r = await pkUpload(`${base}/text`, f); if (r) { toast(`Matn saqlandi: ${fmt(r.chars)} belgi, reja: ${r.plan.length} band`); reload(); } };
  el.querySelector("#pkTt")?.addEventListener("click", () => pkModal(`${d.topic.no}-mavzu: ma'ruza matni`, `<label>Matn («Reja:» bo'limi va raqamli sarlavhalar avtomatik aniqlanadi)<textarea id="pkTx" rows="14"></textarea></label>`, async m => {
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
  el.querySelectorAll("[data-del]").forEach(b => b.onclick = async () => {
    if (!confirm("Fayl o'chirilsinmi?")) return;
    const r = await pkApi(`/api/paket/assets/${b.dataset.del}/delete`, {}); if (r) { toast("O'chirildi"); reload(); }
  });
  el.querySelector("#pkSet")?.addEventListener("submit", async e => {
    e.preventDefault(); if (!can.write) return;
    const f = e.currentTarget, blocks = {};
    Object.keys(M.blocks).forEach(k => blocks[k] = f.elements["b_" + k].checked);
    const r = await pkApi(`${base}/settings`, {mode: f.elements.mode.value, completion: f.elements.completion.value, mastery: +f.elements.mastery.value,
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

/* ---------- Avtomatik joylash ---------- */
async function pkBulk(box) {
  const M = PK.meta;
  box.innerHTML = `<div id="pkPk"></div><div class="pk-grid">
    <div class="card pk-card"><h3>Video havolalarni joylash</h3>
      <p class="muted">Har qatorda bitta YouTube havola — 1-mavzudan boshlab ketma-ket joylanadi. Aniq mavzuga: «5: https://youtu.be/…». watch, youtu.be, shorts, embed va t= (boshlanish vaqti) qo'llab-quvvatlanadi.</p>
      <label class="pk-sr" for="pkBt">Havolalar</label><textarea id="pkBt" class="pk-ta" placeholder="https://www.youtube.com/watch?v=…&#10;https://youtu.be/…&#10;7: https://youtu.be/…"></textarea>
      <div class="pk-acts"><button type="button" class="btn sm" id="pkBc">Tekshirish</button><button type="button" class="btn sm primary" id="pkBs">Saqlash</button></div>
      <div id="pkBr"></div></div>
    <div class="card pk-card"><h3>Ommaviy yig'ish</h3>
      <p class="muted">Kursning manbasi bor barcha mavzulari uchun paket yig'iladi. Manba o'zgarmagan mavzu qayta yig'ilmaydi.</p>
      <div class="pk-form"><label>Turi<select id="pkGm"><option value="">Mavzu sozlamasi bo'yicha</option>${Object.entries(M.modes).map(([k, l]) => `<option value="${k}">${esc(l)}</option>`).join("")}</select></label>
        <label class="cb"><input type="checkbox" id="pkGc" checked> Faqat manbasi to'liq mavzular</label></div>
      <div class="pk-acts"><button type="button" class="btn primary" id="pkGo" ${M.player ? "" : "disabled"}>${ico("package", 15)} Hammasini yig'ish</button></div>
      <div id="pkGr"></div></div></div>`;
  const run = async apply => {
    if (!PK.cid) { toast("Kurs tanlang"); return; }
    const text = box.querySelector("#pkBt").value;
    if (!text.trim()) { toast("Havolalarni kiriting"); return; }
    const r = await pkApi(`/api/paket/courses/${PK.cid}/bulk/videos`, {text, apply});
    if (!r) return;
    if (apply) toast(`Saqlandi: ${r.assigned} ta mavzu${r.errors ? `, xato: ${r.errors}` : ""}`);
    box.querySelector("#pkBr").innerHTML = pkTable([["Qator", x => x.line, "num"], ["Mavzu", x => `${x.topic_no}. ${esc(x.title || "")}`],
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
        pkTable([["Mavzu", x => x.no, "num"], ["Natija", x => x.ok ? (x.unchanged ? `o'zgarmagan · v${x.version}` : `yig'ildi · v${x.version} · ${esc((PK_ST[x.status] || [x.status])[0])}`) : `<span class="${x.skipped ? "" : "pk-bad"}">${esc(x.error)}</span>`]], r.results);
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
      ${ed ? `<div class="pk-acts"><button class="btn sm primary">Saqlash</button></div>` : `<p class="pk-note">O'zgartirish — Masofaviy ta'lim bo'limida.</p>`}</form></div>
    <div class="card pk-card"><h3>LMS'ga yuklash</h3>
      <h4>Moodle (SCORM 1.2 — eng universal)</h4>
      <ol class="pk-steps"><li>Kursda tahrirlash rejimini yoqing → kerakli bo'limda «Faoliyat yoki resurs qo'shish» → <b>SCORM paketi</b>.</li>
        <li>Nom yozing va paket faylini (.zip, ochmasdan) yuklang.</li><li>«Baholash»: baholash usuli — «Eng yuqori urinish»; «Yakunlash»: «Talab qilingan holat — o'tdi / tugallandi».</li>
        <li>Saqlang va «Ko'rish» orqali tekshiring.</li></ol>
      <h4>SCORM 2004</h4><p class="pk-note">Moodle SCORM 2004 ni qisman qo'llaydi; LMS aniq 2004 talab qilsa ishlating, aks holda 1.2 ni tanlang.</p>
      <h4>xAPI (Tin Can)</h4><p class="pk-note">LRS (Learning Record Store) yoki LMS plagini kerak (Moodle'da — masalan, «Logstore xAPI» / tashqi LRS). LMS turi aniq bo'lmaguncha SCORM 1.2 tavsiya etiladi.</p>
      <h4>Kurs paketi</h4><p class="pk-note">Mavzular → «Kurs paketi»: bitta zip'da barcha mavzular (har biri alohida SCO, o'z papkasida).</p>
      <h4>Cheklovlar</h4><p class="pk-note">Fayl ≤ ${M.limits.asset_mb} MB, paket ≤ ${M.limits.package_mb} MB. Video YouTube'da qoladi (paketga havola kiradi). Eski .ppt qabul qilinmaydi — .pptx qilib saqlang.</p></div></div>`;
  box.querySelector("#pkDf").onsubmit = async e => {
    e.preventDefault(); if (!ed) return;
    const f = e.currentTarget, blocks = {};
    Object.keys(M.blocks).forEach(k => blocks[k] = f.elements["b_" + k].checked);
    const r = await pkApi("/api/paket/settings", {mode: f.elements.mode.value, completion: f.elements.completion.value, mastery: +f.elements.mastery.value,
      quiz_n: +f.elements.quiz_n.value, attempts: +f.elements.attempts.value, shuffle: f.elements.shuffle.checked, show_feedback: f.elements.show_feedback.checked, blocks});
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
