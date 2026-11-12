/* =====================================================================
   «Test bank» (app/testbank.py, /api/testbank) — mavzu testlari va oraliq nazorat banklari.
     Qamrov:        kafedra / o'qituvchi / kurs kesimida — tasdiqlangan testi yetarli mavzular ulushi.
     Mavzu testlari: mavzu matni (fayl yoki matn) → AI bilan tuzish (Claude) → qoidaviy sifat belgilari → tahrir, tekshiruvga yuborish,
                     tasdiqlash / rad etish (Masofaviy ta'lim bo'limi).
     Banklar:       1-oraliq (1..k mavzular) / 2-oraliq / mavzu bo'yicha — faqat tasdiqlangan savollar; Moodle XML, GIFT, Aiken, Word.
     Sozlamalar:    kurs uchun oraliq taqsimoti, «qamrab olingan» chegarasi (bo'lim boshlig'i), AI holati, sifat qoidalari.
   Ruxsat va ko'lam serverda. Global: renderTestbank().  app.js yordamchilari: $, esc, fmt, toast, locked, errCard, showLogin, ico, ME.
   ===================================================================== */
const TB = {meta: null, tab: null, cid: 0, topic: 1, part: "o1", qst: "", cov: {q: "", department_id: 0, only: "", offset: 0}};
/* boshqa foydalanuvchi kirsa (sahifa qayta yuklanmasdan) — oldingisining rol/yorliq/kurs/filtrlari qolmasin (masofaviy.js dlReset bilan bir xil) */
function tbReset() { Object.assign(TB, {meta: null, who: null, tab: null, cid: 0, topic: 1, part: "o1", qst: "", cov: {q: "", department_id: 0, only: "", offset: 0}}); }
if (typeof ICONS === "object") {
  if (!ICONS.upload) ICONS.upload = '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><path d="m17 8-5-5-5 5"/><path d="M12 3v12"/>';
  if (!ICONS.download) ICONS.download = '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><path d="m7 10 5 5 5-5"/><path d="M12 15V3"/>';
}
if (typeof ICONS === "object" && !ICONS.plus) ICONS.plus = '<path d="M12 5v14M5 12h14"/>';
if (!document.querySelector('link[href="testbank.css"]')) document.head.insertAdjacentHTML("beforeend", '<link rel="stylesheet" href="testbank.css">');

const TB_TABS = {qamrov: "Fanlar va qamrov", mavzu: "Mavzu testlari", bank: "Banklar (oraliq 1/2)", sozlama: "Sozlamalar"};
const TB_ST = {qoralama: ["Qoralama", ""], tekshiruvda: ["Tekshiruvda", "info"], tasdiqlandi: ["Tasdiqlangan", "ok"], rad_etildi: ["Rad etilgan", "bad"]};
const TB_ENG = {claude: "AI (Claude)", qolda: "Qo'lda", demo: "Namuna"};
const tbChip = (t, cls = "") => `<span class="tb-chip ${cls}">${esc(t)}</span>`;
const tbPct = v => v == null ? "—" : `${String(v).replace(".", ",")}%`;
const tbBar = (pct, cls = "") => `<div class="tb-bar ${cls}" role="img" aria-label="${tbPct(pct)}"><i style="width:${Math.max(0, Math.min(100, pct || 0))}%"></i></div>`;
const tbTone = p => p == null ? "" : p >= 80 ? "ok" : p >= 40 ? "warn" : "bad";
const tbD = s => { s = String(s || "").slice(0, 10); return s.length === 10 ? `${s.slice(8, 10)}.${s.slice(5, 7)}.${s.slice(0, 4)}` : "—"; };
const tbL = i => "ABCDEFGHIJ"[i] || String(i + 1);
const tbKpi = (label, val, sub = "", cls = "") => `<div class="tb-kpi ${cls}"><span>${esc(label)}</span><b>${val}</b>${sub ? `<small>${sub}</small>` : ""}</div>`;

async function tbApi(url, body, method) {
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
function tbTable(cols, rows, {empty = "Ma'lumot yo'q", rowAttr = () => ""} = {}) {
  if (!rows.length) return `<div class="tb-empty">${esc(empty)}</div>`;
  return `<div class="tw"><table class="tb-t"><thead><tr>${cols.map(c => `<th class="${c[2] || ""}">${esc(c[0])}</th>`).join("")}</tr></thead><tbody>` +
    rows.map(r => `<tr ${rowAttr(r)}>${cols.map(c => `<td data-l="${esc(c[0])}" class="${c[2] || ""}"><div>${c[1](r) ?? ""}</div></td>`).join("")}</tr>`).join("") +
    `</tbody></table></div>`;
}
function tbModal(title, html, onOk, okText = "Saqlash", wide = false) {
  const bg = document.createElement("div"); bg.className = "tb-modal-bg";
  bg.innerHTML = `<div class="tb-modal ${wide ? "wide" : ""}" role="dialog" aria-modal="true" aria-label="${esc(title)}"><h3>${esc(title)}</h3>${html}
    <div class="tb-acts end"><button type="button" class="btn ghost" data-x>${onOk ? "Bekor qilish" : "Yopish"}</button>${onOk ? `<button type="button" class="btn primary" data-ok>${esc(okText)}</button>` : ""}</div></div>`;
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

/* ---------- asosiy ko'rinish ---------- */
async function renderTestbank(tab) {
  const v = $("#v-testbank");
  const who = typeof ME !== "undefined" ? ME : null;
  if (TB.who !== who) {     /* birinchi kirish (who=null) — tashqi havola qo'ygan TB.cid saqlanadi; boshqa foydalanuvchi — hammasi tozalanadi */
    const cid = TB.who === null || TB.who === undefined ? TB.cid : 0, want = tab || (cid ? TB.tab : null);
    tbReset(); TB.who = who; TB.cid = cid; tab = want;
  }
  if (!TB.meta) { const m = await tbApi("/api/testbank/meta"); if (TB.who !== who) return; TB.meta = m; }
  const M = TB.meta;
  TB.tab = tab && M.tabs.includes(tab) ? tab : (TB.tab && M.tabs.includes(TB.tab) ? TB.tab : M.tabs[0]);
  v.innerHTML = `<div class="tb-head"><div><h2>Test bank</h2><span class="muted">${esc(M.scope)} · mavzu testlari va oraliq nazorat banklari</span></div>
      <div class="tb-acts tight">${typeof renderPaket === "function" && !document.querySelector('#nav a[data-v="paket"]')?.classList.contains("hidden") ? `<button type="button" class="btn sm ghost" data-pk>${ico("package", 15)} Dars tayyorlash</button>` : ""}${M.ai.on ? tbChip("AI: " + (M.ai.model || "Claude"), "info") : tbChip("AI ulanmagan — savollar qo'lda", "warn")}</div></div>
    ${M.demo ? `<div class="tb-demo">${ico("info", 15)}<span><b>Namuna.</b> «Mikroiqtisodiyot» va bitta o'qituvchi kursidagi savollar va ma'ruza matnlari — sun'iy (demo). Haqiqiy testlar mavzu matni yuklanib, AI yoki qo'lda tuziladi.</span></div>` : ""}
    <div class="tb-tabs" role="tablist">${M.tabs.map(t => `<button type="button" role="tab" aria-selected="${t === TB.tab}" class="${t === TB.tab ? "on" : ""}" data-t="${t}">${esc(TB_TABS[t])}</button>`).join("")}</div>
    <div id="tbBox"><div class="tb-empty">Yuklanmoqda…</div></div>`;
  v.querySelectorAll(".tb-tabs [data-t]").forEach(b => b.onclick = () => renderTestbank(b.dataset.t));
  v.querySelector("[data-pk]")?.addEventListener("click", () => go("paket"));   /* Kontent paketlari (paket.js) */
  const box = $("#tbBox");
  try {
    await ({qamrov: tbCoverage, mavzu: tbTopics, bank: tbBank, sozlama: tbSettings})[TB.tab](box);
  } catch (e) {
    if (e?.message === "auth") return;
    box.innerHTML = e?.message === "denied" ? locked("Bu bo'lim") : `<div class="card tb-card"><p>${esc(e?.msg || "Ma'lumotni yuklab bo'lmadi")}</p></div>`;
  }
}

/* ---------- Kurs tanlash (Mavzu testlari, Banklar, Sozlamalar) ---------- */
async function tbPicker(box, onPick) {
  if (!TB.cid) {
    const d = await tbApi("/api/testbank/courses?limit=1");
    TB.cid = d.items[0]?.id || 0;
  }
  box.innerHTML = `<div class="tb-pick"><label class="tb-sr" for="tbPq">Kursni qidirish</label>
      <input type="search" id="tbPq" placeholder="Fan, yo'nalish, o'qituvchi…" autocomplete="off">
      <label class="tb-sr" for="tbPs">Kurs</label><select id="tbPs"><option>Yuklanmoqda…</option></select></div>`;
  const inp = box.querySelector("#tbPq"), sel = box.querySelector("#tbPs");
  let timer = null;
  const load = async q => {
    const d = await tbApi(`/api/testbank/courses?limit=60&q=${encodeURIComponent(q || "")}`);
    const items = d.items.slice();
    if (TB.cid && !items.some(x => x.id === TB.cid) && !q) {
      try { const c = await tbApi(`/api/testbank/courses/${TB.cid}`); items.unshift({id: TB.cid, subject: c.course.subject, direction: c.course.direction, course: c.course.course, started: true}); } catch (e) {}
    }
    sel.innerHTML = items.map(x => `<option value="${x.id}" ${x.id === TB.cid ? "selected" : ""}>${esc(x.subject)} — ${esc(x.direction)}, ${x.course}-kurs${x.started ? " — savollari bor" : ""}</option>`).join("")
      || `<option value="">Topilmadi</option>`;
    if (d.total > items.length) sel.insertAdjacentHTML("beforeend", `<option disabled>… yana ${fmt(d.total - items.length)} ta — qidiruvdan foydalaning</option>`);
  };
  inp.oninput = () => { clearTimeout(timer); timer = setTimeout(() => load(inp.value.trim()), 250); };
  sel.onchange = () => { const id = +sel.value; if (id && id !== TB.cid) { TB.cid = id; TB.topic = 1; onPick(); } };
  await load("");
}

/* ---------- Qamrov ---------- */
async function tbCoverage(box) {
  const M = TB.meta, F = TB.cov;
  const d = await tbApi("/api/testbank/coverage");
  const t = d.total;
  box.innerHTML = `
    <div class="tb-kpis">
      ${tbKpi("Mavzular qamrovi", tbPct(t.pct), `${fmt(t.covered)} / ${fmt(t.topics)} mavzuda ≥ ${d.min_q} ta tasdiqlangan savol`, tbTone(t.pct))}
      ${tbKpi("Qisman", fmt(t.partial), "testi bor, lekin yetarli emas", t.partial ? "warn" : "")}
      ${tbKpi("Tasdiqlangan savollar", fmt(t.approved), "banklarga kiradi", "ok")}
      ${tbKpi("Tekshiruvda", fmt(t.review), "bo'lim tasdig'ini kutmoqda", t.review ? "info" : "")}
      ${tbKpi("Qoralama", fmt(t.draft), `rad etilgan: ${fmt(t.rejected)}`)}
      ${tbKpi("Boshlangan kurslar", `${fmt(t.started)} / ${fmt(t.courses)}`, `mavzu matni yuklangan mavzular: ${fmt(t.sources)}`)}
    </div>
    ${d.ai ? `<p class="tb-note">${ico("spark", 14)} AI generatsiyalar: ${fmt(d.ai.runs)} ta (muvaffaqiyatli ${fmt(d.ai.ok)}) · tokenlar: kirish ${fmt(d.ai.tokens_in)}, chiqish ${fmt(d.ai.tokens_out)}</p>` : ""}
    <div class="card tb-card"><h3>Kafedralar</h3><p class="muted">Tasdiqlangan testi yetarli mavzular ulushi · eng ortda turganlari yuqorida${M.caps.questions ? " · kafedra nomini bosing — kurslar ro'yxati filtrlanadi" : ""}</p>
      ${tbTable([["Kafedra", r => M.caps.questions || M.role === "rektor" || M.role === "prorektor_oquv" ? `<button type="button" class="tb-link" data-dep="${r.department_id}">${esc(r.name)}</button>` : esc(r.name)],
                 ["Kurslar", r => `${fmt(r.started)} / ${fmt(r.courses)}<small>boshlangan</small>`, "num"],
                 ["Qamrov", r => `${tbBar(r.pct, tbTone(r.pct))}<small>${fmt(r.covered)} / ${fmt(r.topics)} mavzu · ${tbPct(r.pct)}</small>`],
                 ["Savollar", r => `${fmt(r.approved)} <small>tekshiruvda ${fmt(r.review)} · qoralama ${fmt(r.draft)}</small>`, "num"]], d.departments)}</div>
    ${d.teachers.length ? `<details class="card tb-card tb-det"><summary><h3>O'qituvchilar</h3><span class="muted">${fmt(d.teachers.filter(x => x.started).length)} nafarida boshlangan</span></summary>
      ${tbTable([["O'qituvchi", r => `${esc(r.name)}<small>${esc(r.dept || "")}</small>`],
                 ["Qamrov", r => `${tbBar(r.pct, tbTone(r.pct))}<small>${fmt(r.covered)} / ${fmt(r.topics)} · ${tbPct(r.pct)}</small>`],
                 ["Savollar", r => `${fmt(r.approved)} <small>tekshiruvda ${fmt(r.review)}</small>`, "num"]],
                d.teachers.slice().sort((a, b) => (b.started - a.started) || ((a.pct || 0) - (b.pct || 0))).slice(0, 40))}</details>` : ""}
    <div class="card tb-card"><h3>Kurslar</h3>
      <div class="tb-filters">
        <input type="search" id="tbCq" placeholder="Fan, yo'nalish, o'qituvchi…" value="${esc(F.q)}" aria-label="Qidirish">
        <select id="tbCo" aria-label="Holat"><option value="">Hammasi</option><option value="started" ${F.only === "started" ? "selected" : ""}>Boshlanganlar</option>
          <option value="review" ${F.only === "review" ? "selected" : ""}>Tekshiruvi borlar</option><option value="empty" ${F.only === "empty" ? "selected" : ""}>Hali boshlanmagan</option></select>
        <select id="tbCd" aria-label="Kafedra"><option value="0">Barcha kafedralar</option>${d.departments.map(x => `<option value="${x.department_id}" ${x.department_id === F.department_id ? "selected" : ""}>${esc(x.name)}</option>`).join("")}</select>
      </div><div id="tbCl"><div class="tb-empty">Yuklanmoqda…</div></div></div>`;
  box.querySelectorAll("[data-dep]").forEach(b => b.onclick = () => { F.department_id = +b.dataset.dep; F.offset = 0; box.querySelector("#tbCd").value = String(F.department_id); tbCourseList(box); box.querySelector("#tbCl").scrollIntoView({block: "start", behavior: "smooth"}); });
  let timer = null;
  box.querySelector("#tbCq").oninput = e => { clearTimeout(timer); timer = setTimeout(() => { F.q = e.target.value.trim(); F.offset = 0; tbCourseList(box); }, 250); };
  box.querySelector("#tbCo").onchange = e => { F.only = e.target.value; F.offset = 0; tbCourseList(box); };
  box.querySelector("#tbCd").onchange = e => { F.department_id = +e.target.value; F.offset = 0; tbCourseList(box); };
  await tbCourseList(box);
}
async function tbCourseList(box) {
  const F = TB.cov, M = TB.meta, el = box.querySelector("#tbCl");
  const lim = 30;
  const d = await tbApi(`/api/testbank/courses?q=${encodeURIComponent(F.q)}&only=${F.only}&department_id=${F.department_id}&offset=${F.offset}&limit=${lim}`);
  el.innerHTML = tbTable([
    ["Fan", r => `<b>${esc(r.subject)}</b><small>${esc(r.direction)} · ${r.course}-kurs</small>`],
    ["Mas'ul", r => `${esc(r.teacher || "—")}<small>${esc(r.dept || "")}</small>`],
    ["Qamrov", r => `${tbBar(r.pct, tbTone(r.pct))}<small>${r.covered} / ${r.topics} mavzu · 1-oraliq ${r.o1_covered}/${r.split}, 2-oraliq ${r.o2_covered}/${r.topics - r.split}</small>`],
    ["Savollar", r => `${fmt(r.approved)}${r.review ? " " + tbChip(r.review + " tekshiruvda", "info") : ""}${r.draft ? " " + tbChip(r.draft + " qoralama") : ""}`],
    ["", r => M.caps.questions ? `<button type="button" class="btn sm" data-open="${r.id}">Ochish</button>` : ""]], d.items, {empty: "Kurs topilmadi"}) +
    (d.total > lim ? `<div class="tb-pager"><button type="button" class="btn sm ghost" data-p="${Math.max(0, F.offset - lim)}" ${F.offset ? "" : "disabled"}>← Oldingi</button>
      <span>${fmt(F.offset + 1)}–${fmt(Math.min(d.total, F.offset + lim))} / ${fmt(d.total)}</span>
      <button type="button" class="btn sm ghost" data-p="${F.offset + lim}" ${F.offset + lim < d.total ? "" : "disabled"}>Keyingi →</button></div>` : "");
  el.querySelectorAll("[data-p]").forEach(b => b.onclick = () => { F.offset = +b.dataset.p; tbCourseList(box); });
  el.querySelectorAll("[data-open]").forEach(b => b.onclick = () => { TB.cid = +b.dataset.open; TB.topic = 1; renderTestbank("mavzu"); });
}

/* ---------- Mavzu testlari ---------- */
async function tbTopics(box) {
  box.innerHTML = `<div id="tbPk"></div><div id="tbCv"></div>`;
  await tbPicker(box.querySelector("#tbPk"), () => tbCourse(box.querySelector("#tbCv")));
  await tbCourse(box.querySelector("#tbCv"));
}
async function tbCourse(el) {
  if (!TB.cid) { el.innerHTML = `<div class="tb-empty">Sizga biriktirilgan kurs topilmadi</div>`; return; }
  const d = await tbApi(`/api/testbank/courses/${TB.cid}`);
  const c = d.course;
  if (!d.topics.some(t => t.no === TB.topic)) TB.topic = 1;
  el.innerHTML = `<div class="card tb-card"><div class="tb-item-h"><div><h3>${esc(c.subject)}</h3>
      <p class="muted">${esc(c.direction)} · ${c.course}-kurs · ${esc(c.dept || "—")} · mas'ul: ${esc(c.teacher || "—")} · 1-oraliq: 1–${c.split}-mavzular, 2-oraliq: ${c.split + 1}–${c.topics}</p></div></div>
    <div class="tb-topics" role="list">${d.topics.map(t => `<button type="button" role="listitem" class="tb-topic ${t.no === TB.topic ? "on" : ""} ${t.covered ? "cov" : ""}" data-no="${t.no}" aria-pressed="${t.no === TB.topic}">
        <span class="no">${t.no}</span><span class="tt">${esc(t.label)}</span>
        <span class="mm"><span title="tasdiqlangan / chegara">${t.approved}/${d.min_q}</span>${t.review ? `<i class="info" title="tekshiruvda">${t.review}</i>` : ""}${t.blocking ? `<i class="bad" title="bloklovchi xato">!${t.blocking}</i>` : ""}${t.source ? "" : `<i class="mut" title="mavzu matni yo'q">matn yo'q</i>`}</span>
        <span class="or">${t.oraliq}-oraliq</span></button>`).join("")}</div></div>
    <div id="tbTp"></div>`;
  el.querySelectorAll(".tb-topic").forEach(b => b.onclick = () => { TB.topic = +b.dataset.no; TB.qst = ""; tbCourse(el); });
  await tbTopicPanel(el.querySelector("#tbTp"), d);
}
async function tbTopicPanel(el, d) {
  const M = TB.meta, t = d.topics.find(x => x.no === TB.topic), can = d.can;
  const [qs, src] = await Promise.all([tbApi(`/api/testbank/courses/${TB.cid}/topics/${t.no}/questions`), tbApi(`/api/testbank/courses/${TB.cid}/topics/${t.no}/source`)]);
  const s = src.source, items = qs.items;
  const shown = TB.qst ? items.filter(q => q.status === TB.qst) : items;
  const cnt = st => items.filter(q => q.status === st).length;
  const withSrc = d.topics.filter(x => x.source);
  el.innerHTML = `<div class="tb-grid">
    <div class="card tb-card"><h3>${t.no}-mavzu: ${esc(t.label)} <span class="muted">· mavzu matni</span></h3>
      ${s ? `<p class="tb-src">${ico("file", 15)} <b>${esc(s.name)}</b> · ${fmt(s.chars)} belgi${s.truncated ? " (qisqartirilgan)" : ""} · ${esc(s.by || "")} · ${tbD(s.ts)}${s.demo ? " " + tbChip("namuna", "warn") : ""}${s.origin === "paket" ? " " + tbChip("«Dars tayyorlash»da yuklangan", "info") : ""}</p>
             <details class="tb-srctext"><summary>Matnni ko'rish</summary><pre>${esc(s.text)}${s.cut ? "\n…" : ""}</pre></details>`
          : `<p class="muted">Bu mavzu uchun ma'ruza matni yuklanmagan. Testlar faqat yuklangan matn asosida tuziladi.</p>`}
      ${can.write ? `<div class="tb-acts"><label class="btn sm tb-file">${ico("upload", 15)} Fayl yuklash (.docx, .pdf, .txt)<input type="file" accept=".docx,.pdf,.txt" hidden id="tbSf"></label>
         <button type="button" class="btn sm ghost" id="tbSt">Matn joylashtirish</button></div><p class="tb-note">≤ ${M.limits.max_mb} MB · kamida ${fmt(M.limits.min_chars)} belgi · Claude'ga faqat shu matn yuboriladi (talabalar ma'lumoti yo'q)</p>` : ""}
    </div>
    ${can.write && M.caps.generate ? `<div class="card tb-card"><h3>AI bilan test tuzish</h3>
      ${M.ai.on ? `<p class="muted">Model: ${esc(M.ai.model)} · bugun ${M.ai.used_today}/${M.ai.daily} · bir martada ${M.limits.max_topics} tagacha mavzu</p>`
                : `<p class="tb-warnbox">${ico("alert", 15)} AI ulanmagan — administratorga murojaat qiling. Savollarni «Savol qo'shish» orqali qo'lda kiritish mumkin.</p>`}
      <fieldset class="tb-fs"><legend>Mavzular</legend><div class="tb-checks">${withSrc.length ? withSrc.map(x => `<label><input type="checkbox" name="tbGt" value="${x.no}" ${x.no === t.no ? "checked" : ""}> ${x.no}. ${esc(x.label)}</label>`).join("") : `<span class="muted">Avval mavzu matnini yuklang</span>`}</div></fieldset>
      <div class="tb-form">
        <label>Mavzu boshiga savollar<input type="number" id="tbGn" min="1" max="${M.limits.max_n}" value="10"></label>
        <fieldset class="tb-fs"><legend>Turlar</legend><div class="tb-checks row">${Object.entries(M.qtypes).map(([k, v]) => `<label><input type="checkbox" name="tbGy" value="${k}" ${k === "mcq" ? "checked" : ""}> ${esc(v)}</label>`).join("")}</div></fieldset>
        <fieldset class="tb-fs"><legend>Qiyinlik ulushi, %</legend><div class="tb-mix">${[["oson", 30], ["orta", 50], ["qiyin", 20]].map(([k, v]) => `<label>${esc(M.difficulty[k])}<input type="number" min="0" max="100" value="${v}" data-mix="${k}"></label>`).join("")}</div></fieldset>
      </div>
      <div class="tb-acts"><button type="button" class="btn primary" id="tbGo" ${M.ai.on && withSrc.length ? "" : "disabled"}>${ico("spark", 15)} Savollarni tuzish</button></div>
      <div id="tbGr"></div></div>` : ""}
  </div>
  <div class="card tb-card"><div class="tb-item-h"><div><h3>Savollar <span class="muted">· ${items.length} ta</span></h3>
      <p class="muted">Qoralama → tekshiruvga yuborish (o'qituvchi) → tasdiqlash / rad etish (Masofaviy ta'lim bo'limi). Bloklovchi belgisi bor savol yuborilmaydi.</p></div>
      <div class="tb-acts tight">${can.write ? `<button type="button" class="btn sm" id="tbAdd">${ico("plus", 15)} Savol qo'shish</button>` : ""}
        ${can.write && cnt("qoralama") ? `<button type="button" class="btn sm ghost" id="tbBs">Qoralamalarni yuborish (${cnt("qoralama")})</button>` : ""}
        ${can.review && cnt("tekshiruvda") ? `<button type="button" class="btn sm primary" id="tbBa">Tekshiruvdagilarni tasdiqlash (${cnt("tekshiruvda")})</button>` : ""}</div></div>
    <div class="tb-seg" role="tablist">${[["", "Hammasi", items.length], ...Object.entries(TB_ST).map(([k, v]) => [k, v[0], cnt(k)])].map(([k, l, n]) =>
      `<button type="button" class="${TB.qst === k ? "on" : ""}" data-qs="${k}">${esc(l)} <small>${n}</small></button>`).join("")}</div>
    <div class="tb-qs">${shown.length ? shown.map(tbQCard).join("") : `<div class="tb-empty">Savol yo'q${can.write ? " — mavzu matnini yuklab, AI bilan tuzing yoki qo'lda qo'shing" : ""}</div>`}</div></div>`;
  const reload = () => tbCourse($("#tbCv"));
  el.querySelectorAll("[data-qs]").forEach(b => b.onclick = () => { TB.qst = b.dataset.qs; tbTopicPanel(el, d); });
  const sf = el.querySelector("#tbSf");
  if (sf) sf.onchange = async () => {
    const f = sf.files[0]; if (!f) return;
    if (f.size > M.limits.max_mb * 1024 * 1024) { toast(`Fayl ${M.limits.max_mb} MB dan katta`); return; }
    toast("Yuklanmoqda…");
    const r = await tbApi(`/api/testbank/courses/${TB.cid}/topics/${t.no}/source?name=${encodeURIComponent(f.name)}`, f);
    if (r) { toast(`Matn saqlandi: ${fmt(r.chars)} belgi`); reload(); }
  };
  el.querySelector("#tbSt")?.addEventListener("click", () => tbModal(`${t.no}-mavzu: ma'ruza matni`, `<label>Matn (kamida ${M.limits.min_chars} belgi)<textarea id="tbTx" rows="12"></textarea></label>`, async m => {
    const r = await tbApi(`/api/testbank/courses/${TB.cid}/topics/${t.no}/source/text`, {text: m.querySelector("#tbTx").value, name: `${t.no}-mavzu matni.txt`});
    if (r) { toast(`Matn saqlandi: ${fmt(r.chars)} belgi`); reload(); return true; }
  }, "Saqlash", true));
  el.querySelector("#tbGo")?.addEventListener("click", async e => {
    const topics = [...el.querySelectorAll('input[name="tbGt"]:checked')].map(x => +x.value);
    const types = [...el.querySelectorAll('input[name="tbGy"]:checked')].map(x => x.value);
    const mix = {}; el.querySelectorAll("[data-mix]").forEach(x => mix[x.dataset.mix] = +x.value || 0);
    const n = +el.querySelector("#tbGn").value;
    if (!topics.length) { toast("Kamida bitta mavzu tanlang"); return; }
    if (topics.length > M.limits.max_topics) { toast(`Bir martada ko'pi bilan ${M.limits.max_topics} ta mavzu`); return; }
    if (!types.length) { toast("Kamida bitta savol turini tanlang"); return; }
    const btn = e.currentTarget; btn.disabled = true;
    const gr = el.querySelector("#tbGr");
    gr.innerHTML = `<p class="tb-note">${ico("clock", 14)} AI savollar tuzmoqda: ${topics.length} mavzu × ${n} ta. Bu bir necha daqiqa davom etishi mumkin…</p>`;
    try {
      const r = await tbApi(`/api/testbank/courses/${TB.cid}/generate`, {topics, n, types, mix});
      if (!r) { gr.innerHTML = ""; return; }
      TB.meta = null;
      toast(`Yaratildi: ${r.created} ta savol (qoralama)`);
      gr.innerHTML = `<ul class="tb-list">${r.results.map(x => `<li>${x.topic_no}-mavzu: ${x.ok ? `${x.created} ta savol · bloklovchi ${x.blocking}, belgili ${x.flagged} · ${fmt(x.tokens_in)}/${fmt(x.tokens_out)} token` : `<span class="tb-bad">${esc(x.err)}</span>`}</li>`).join("")}</ul>`;
      TB.meta = await tbApi("/api/testbank/meta");
      setTimeout(reload, 1200);
    } finally { if (btn.isConnected) btn.disabled = false; }
  });
  el.querySelector("#tbAdd")?.addEventListener("click", () => tbEdit(null, t.no, reload));
  const bulk = async (action, st) => {
    const ids = items.filter(q => q.status === st).map(q => q.id);
    const r = await tbApi(`/api/testbank/courses/${TB.cid}/bulk`, {action, ids});
    if (r) { toast(`Bajarildi: ${r.done} ta${r.skipped.length ? ` · o'tkazib yuborildi: ${r.skipped.length} (bloklovchi xato)` : ""}`); reload(); }
  };
  el.querySelector("#tbBs")?.addEventListener("click", () => bulk("submit", "qoralama"));
  el.querySelector("#tbBa")?.addEventListener("click", () => bulk("approve", "tekshiruvda"));
  el.querySelectorAll("[data-qa]").forEach(b => b.onclick = () => tbQAction(+b.dataset.id, b.dataset.qa, items, t.no, reload));
}
function tbQCard(q) {
  const M = TB.meta, st = TB_ST[q.status] || [q.status, ""];
  const opts = q.qtype === "fill" ? `<p class="tb-ans">Javob: <b>${q.answers.map(esc).join(" / ") || "—"}</b></p>`
    : `<ol class="tb-opts">${q.options.map((o, i) => `<li class="${q.correct.includes(i) ? "ok" : ""}"><span class="l">${tbL(i)}</span><span>${esc(o)}</span>${q.correct.includes(i) ? `<span class="tb-sr">(to'g'ri javob)</span>${ico("check", 14)}` : ""}</li>`).join("")}</ol>`;
  const fl = q.flags.length ? `<ul class="tb-flags">${q.flags.map(f => `<li class="${f.sev}">${ico(f.sev === "block" ? "x" : "alert", 13)}<span><b>${f.sev === "block" ? "Bloklovchi" : "Ogohlantirish"}:</b> ${esc(f.msg)}</span></li>`).join("")}</ul>` : "";
  const c = q.can || {};
  return `<article class="tb-q st-${q.status}" aria-label="Savol ${q.id}">
    <div class="tb-qh">${tbChip(st[0], st[1])}${tbChip(M.qtypes[q.qtype] || q.qtype)}${tbChip(M.difficulty[q.difficulty] || "")}${tbChip(M.bloom[q.bloom] || "")}${tbChip(TB_ENG[q.engine] || q.engine, q.engine === "demo" ? "warn" : "")}<span class="tb-id">#${q.id}</span></div>
    <p class="tb-stem">${esc(q.stem)}</p>${opts}${fl}
    ${q.status === "rad_etildi" && q.review_note ? `<p class="tb-rej"><b>Rad etish sababi:</b> ${esc(q.review_note)}</p>` : ""}
    <details class="tb-more"><summary>Izoh va manba</summary>${q.explanation ? `<p><b>Izoh:</b> ${esc(q.explanation)}</p>` : ""}${q.source_quote ? `<blockquote>${esc(q.source_quote)}</blockquote>` : "<p class='muted'>Iqtibos yo'q</p>"}
      <p class="muted">Muallif: ${esc(q.author_name || "—")}${q.reviewer_name ? ` · ko'rib chiqdi: ${esc(q.reviewer_name)} (${tbD(q.reviewed_at)})` : ""}</p></details>
    <div class="tb-acts">${c.edit ? `<button type="button" class="btn sm ghost" data-qa="edit" data-id="${q.id}">Tahrirlash</button>` : ""}
      ${c.submit ? `<button type="button" class="btn sm" data-qa="submit" data-id="${q.id}">Tekshiruvga yuborish</button>` : ""}
      ${c.review ? `<button type="button" class="btn sm primary" data-qa="approve" data-id="${q.id}" ${q.blocking ? "disabled" : ""}>Tasdiqlash</button><button type="button" class="btn sm ghost" data-qa="reject" data-id="${q.id}">Rad etish</button>` : ""}
      ${c.delete ? `<button type="button" class="btn sm ghost tb-del" data-qa="delete" data-id="${q.id}">O'chirish</button>` : ""}
      <button type="button" class="btn sm ghost" data-qa="log" data-id="${q.id}">Tarix</button></div></article>`;
}
async function tbQAction(id, act, items, no, reload) {
  const q = items.find(x => x.id === id);
  if (act === "edit") return tbEdit(q, no, reload);
  if (act === "log") {
    const d = await tbApi(`/api/testbank/questions/${id}/log`).catch(e => { toast(e?.msg || "Ochib bo'lmadi"); return null; });
    if (d) tbModal(`Savol #${id}: tarix`, `<ul class="tb-list">${d.items.map(x => `<li><b>${esc(x.action)}</b> · ${esc(x.user_name || "—")} · ${esc(String(x.ts).replace("T", " ").slice(0, 16))}${x.note ? ` — ${esc(x.note)}` : ""}</li>`).join("") || "<li>Yozuv yo'q</li>"}</ul>`);
    return;
  }
  if (act === "reject") return tbModal(`Savol #${id}: rad etish`, `<label>Sabab (o'qituvchi ko'radi)<textarea id="tbRn" rows="3" placeholder="Masalan: noto'g'ri variantlar juda oson, iqtibos mavzu matniga mos emas"></textarea></label>`, async m => {
    const r = await tbApi(`/api/testbank/questions/${id}/action`, {action: "reject", note: m.querySelector("#tbRn").value.trim()});
    if (r) { toast("Rad etildi"); reload(); return true; }
  }, "Rad etish");
  if (act === "delete") return tbModal(`Savol #${id}: o'chirish`, `<p>Savol bankdan o'chiriladi (tarix saqlanadi).</p>`, async () => {
    const r = await tbApi(`/api/testbank/questions/${id}/delete`, {});
    if (r) { toast("O'chirildi"); reload(); return true; }
  }, "O'chirish");
  const r = await tbApi(`/api/testbank/questions/${id}/action`, {action: act});
  if (r) { toast(act === "approve" ? "Tasdiqlandi" : "Tekshiruvga yuborildi"); reload(); }
}
function tbEdit(q, no, reload) {
  const M = TB.meta, isNew = !q;
  q = q || {qtype: "mcq", stem: "", options: ["", "", "", ""], correct: [0], answers: [], explanation: "", difficulty: "orta", bloom: "tushunish", source_quote: ""};
  const optsHtml = (opts, corr) => opts.map((o, i) => `<div class="tb-opt"><input type="radio" name="tbEc" value="${i}" ${corr.includes(i) ? "checked" : ""} aria-label="${tbL(i)} — to'g'ri javob">
      <span class="l">${tbL(i)}</span><input type="text" data-opt="${i}" value="${esc(o)}" aria-label="${tbL(i)} variant"></div>`).join("");
  const m = tbModal(isNew ? `${no}-mavzu: yangi savol` : `Savol #${q.id}: tahrirlash`, `
    ${!isNew && q.status !== "qoralama" ? `<p class="tb-note">Saqlangach savol qoralamaga qaytadi va qayta tekshiruvga yuboriladi.</p>` : ""}
    <div class="tb-form2"><label>Turi<select id="tbEt">${Object.entries(M.qtypes).map(([k, v]) => `<option value="${k}" ${k === q.qtype ? "selected" : ""}>${esc(v)}</option>`).join("")}</select></label>
      <label>Qiyinlik<select id="tbEd">${Object.entries(M.difficulty).map(([k, v]) => `<option value="${k}" ${k === q.difficulty ? "selected" : ""}>${esc(v)}</option>`).join("")}</select></label>
      <label>Bloom darajasi<select id="tbEb">${Object.entries(M.bloom).map(([k, v]) => `<option value="${k}" ${k === q.bloom ? "selected" : ""}>${esc(v)}</option>`).join("")}</select></label></div>
    <label>Savol matni<textarea id="tbEs" rows="3" placeholder="Bo'sh joyni to'ldirish turida bo'sh joyni ____ bilan belgilang">${esc(q.stem)}</textarea></label>
    <div id="tbEo"></div>
    <label>Izoh (nega to'g'ri)<textarea id="tbEx" rows="2">${esc(q.explanation || "")}</textarea></label>
    <label>Manba iqtibosi (mavzu matnidan aynan)<textarea id="tbEq" rows="2">${esc(q.source_quote || "")}</textarea></label>`, async m2 => {
    const t = m2.querySelector("#tbEt").value;
    const body = {qtype: t, stem: m2.querySelector("#tbEs").value.trim(), explanation: m2.querySelector("#tbEx").value.trim(),
                  difficulty: m2.querySelector("#tbEd").value, bloom: m2.querySelector("#tbEb").value, source_quote: m2.querySelector("#tbEq").value.trim(),
                  options: [], correct: [], answers: []};
    if (t === "fill") body.answers = m2.querySelector("#tbEa").value.split("\n").map(s => s.trim()).filter(Boolean);
    else if (t === "tf") body.correct = [+(m2.querySelector('input[name="tbEtf"]:checked')?.value ?? 0)];
    else { body.options = [...m2.querySelectorAll("[data-opt]")].map(x => x.value.trim()); const c = m2.querySelector('input[name="tbEc"]:checked'); body.correct = c ? [+c.value] : []; }
    const r = isNew ? await tbApi(`/api/testbank/courses/${TB.cid}/topics/${no}/questions`, body) : await tbApi(`/api/testbank/questions/${q.id}`, body, "PUT");
    if (r) { toast(r.flags?.length ? `Saqlandi · sifat belgilari: ${r.flags.length}` : "Saqlandi"); reload(); return true; }
  }, "Saqlash", true);
  let opts = q.qtype === "mcq" ? q.options.slice() : ["", "", "", ""], corr = q.qtype === "mcq" ? q.correct.slice() : [0];
  const draw = () => {
    const t = m.querySelector("#tbEt").value, box = m.querySelector("#tbEo");
    if (t === "fill") box.innerHTML = `<label>Qabul qilinadigan javoblar (har biri yangi qatorda)<textarea id="tbEa" rows="3">${esc((q.qtype === "fill" ? q.answers : []).join("\n"))}</textarea></label>`;
    else if (t === "tf") box.innerHTML = `<fieldset class="tb-fs"><legend>To'g'ri javob</legend><div class="tb-checks row">${["To'g'ri", "Noto'g'ri"].map((l, i) => `<label><input type="radio" name="tbEtf" value="${i}" ${(q.qtype === "tf" ? q.correct[0] : 0) === i ? "checked" : ""}> ${l}</label>`).join("")}</div></fieldset>`;
    else {
      box.innerHTML = `<fieldset class="tb-fs"><legend>Variantlar (to'g'risini belgilang)</legend><div id="tbEol">${optsHtml(opts, corr)}</div>
        <div class="tb-acts"><button type="button" class="btn sm ghost" id="tbEp" ${opts.length >= 6 ? "disabled" : ""}>+ Variant</button><button type="button" class="btn sm ghost" id="tbEm" ${opts.length <= 3 ? "disabled" : ""}>− Variant</button></div></fieldset>`;
      const sync = () => { opts = [...box.querySelectorAll("[data-opt]")].map(x => x.value); const c = box.querySelector('input[name="tbEc"]:checked'); corr = c ? [+c.value] : []; };
      box.querySelector("#tbEp").onclick = () => { sync(); opts.push(""); draw(); };
      box.querySelector("#tbEm").onclick = () => { sync(); opts.pop(); corr = corr.filter(i => i < opts.length); draw(); };
      box.querySelectorAll("input").forEach(x => x.addEventListener("change", sync));
    }
  };
  m.querySelector("#tbEt").onchange = draw;
  draw();
}

/* ---------- Banklar ---------- */
async function tbBank(box) {
  box.innerHTML = `<div id="tbPk"></div><div id="tbBv"></div>`;
  await tbPicker(box.querySelector("#tbPk"), () => tbBankView(box.querySelector("#tbBv")));
  await tbBankView(box.querySelector("#tbBv"));
}
async function tbBankView(el) {
  if (!TB.cid) { el.innerHTML = `<div class="tb-empty">Kurs topilmadi</div>`; return; }
  const M = TB.meta;
  const cv = await tbApi(`/api/testbank/courses/${TB.cid}`);
  const c = cv.course;
  if (/^t\d+$/.test(TB.part) && +TB.part.slice(1) > c.topics) TB.part = "o1";
  const b = await tbApi(`/api/testbank/courses/${TB.cid}/bank?part=${TB.part}`);
  const isT = TB.part.startsWith("t");
  const exp = f => `/api/testbank/courses/${TB.cid}/export/${f}?part=${TB.part}`;
  const n = b.questions.length, mcq = b.by_type.mcq || 0;
  el.innerHTML = `<div class="card tb-card"><div class="tb-item-h"><div><h3>${esc(c.subject)} <span class="muted">· ${esc(c.direction)}, ${c.course}-kurs</span></h3>
      <p class="muted">Bankka faqat tasdiqlangan savollar kiradi · 1-oraliq: 1–${c.split}-mavzular, 2-oraliq: ${c.split + 1}–${c.topics}-mavzular${M.caps.write ? " (taqsimot — «Sozlamalar»da)" : ""}</p></div></div>
    <div class="tb-seg">${[["o1", `1-oraliq (1–${c.split})`], ["o2", `2-oraliq (${c.split + 1}–${c.topics})`], ["all", "Barcha mavzular"]].map(([k, l]) => `<button type="button" class="${TB.part === k ? "on" : ""}" data-part="${k}">${esc(l)}</button>`).join("")}
      <button type="button" class="${isT ? "on" : ""}" data-part="t${isT ? TB.part.slice(1) : 1}">Mavzu testi</button></div>
    ${isT ? `<div class="tb-filters"><label class="tb-sr" for="tbBt">Mavzu</label><select id="tbBt">${cv.topics.map(t => `<option value="${t.no}" ${"t" + t.no === TB.part ? "selected" : ""}>${t.no}. ${esc(t.label)} — ${t.approved} ta</option>`).join("")}</select></div>` : ""}
    <div class="tb-kpis sm">${tbKpi(b.label, fmt(n), "tasdiqlangan savol", n ? "ok" : "warn")}${Object.entries(M.qtypes).map(([k, v]) => tbKpi(v, fmt(b.by_type[k] || 0))).join("")}</div>
    <div class="tb-exp">
      <a class="btn sm ${n ? "" : "disabled"}" href="${exp("docx")}" ${n ? "" : 'aria-disabled="true" tabindex="-1"'}>${ico("download", 15)} Word (.docx) — savollar va javoblar kaliti</a></div>
    <details class="tb-more"><summary>Kengaytirilgan: boshqa LMS uchun eksport (Moodle XML, GIFT, Aiken)</summary>
      <div class="tb-exp" style="margin-top:8px">
        <a class="btn sm ghost ${n ? "" : "disabled"}" href="${exp("xml")}" ${n ? "" : 'aria-disabled="true" tabindex="-1"'}>${ico("download", 15)} Moodle XML</a>
        <a class="btn sm ghost ${n ? "" : "disabled"}" href="${exp("gift")}" ${n ? "" : 'aria-disabled="true" tabindex="-1"'}>${ico("download", 15)} GIFT</a>
        <a class="btn sm ghost ${mcq ? "" : "disabled"}" href="${exp("aiken")}" ${mcq ? "" : 'aria-disabled="true" tabindex="-1"'}>${ico("download", 15)} Aiken${n > mcq ? ` (${mcq} ta)` : ""}</a></div>
      <p class="tb-note">Moodle: Savollar banki → Import → «Moodle XML» (kategoriyalar: fan / oraliq / mavzu) yoki «GIFT». Aiken — faqat bir javobli savollar. NEXTID uchun test dars ichida ketadi («Dars tayyorlash»).</p></details>
    ${!isT ? tbTable([["Mavzu", r => `${r.no}. ${esc(r.label)}`], ["Tasdiqlangan", r => `${r.n} ${r.n >= cv.min_q ? tbChip("yetarli", "ok") : tbChip(`${cv.min_q} dan kam`, "warn")}`, "num"]], b.topics) : ""}
  </div>
  <div class="card tb-card"><h3>Savollar <span class="muted">· ${n} ta</span></h3>
    <div class="tb-qs">${n ? b.questions.slice(0, 60).map(q => tbQCard({...q, can: {}})).join("") + (n > 60 ? `<div class="tb-empty">… yana ${n - 60} ta — to'liq ro'yxat eksport faylida</div>` : "") : `<div class="tb-empty">Bu bankda hali tasdiqlangan savol yo'q</div>`}</div></div>`;
  el.querySelectorAll("[data-part]").forEach(x => x.onclick = () => { TB.part = x.dataset.part; tbBankView(el); });
  el.querySelector("#tbBt")?.addEventListener("change", e => { TB.part = "t" + e.target.value; tbBankView(el); });
  el.querySelectorAll("a.disabled").forEach(a => a.addEventListener("click", e => e.preventDefault()));
  el.querySelectorAll("[data-qa]").forEach(x => x.onclick = async () => {
    const d = await tbApi(`/api/testbank/questions/${x.dataset.id}/log`).catch(() => null);
    if (d) tbModal(`Savol #${x.dataset.id}: tarix`, `<ul class="tb-list">${d.items.map(r => `<li><b>${esc(r.action)}</b> · ${esc(r.user_name || "—")} · ${esc(String(r.ts).replace("T", " ").slice(0, 16))}${r.note ? ` — ${esc(r.note)}` : ""}</li>`).join("")}</ul>`);
  });
}

/* ---------- Sozlamalar ---------- */
async function tbSettings(box) {
  const M = TB.meta;
  box.innerHTML = `<div id="tbPk"></div><div class="tb-grid"><div id="tbSp" class="card tb-card"></div>
    <div class="card tb-card"><h3>Umumiy</h3>
      <form id="tbMq" class="tb-form"><label>«Qamrab olingan» mavzu: kamida shuncha tasdiqlangan savol<input type="number" id="tbMqv" min="1" max="100" value="${M.min_q}" ${M.caps.settings ? "" : "disabled"}></label>
        ${M.caps.settings ? `<div class="tb-acts"><button class="btn sm primary">Saqlash</button></div>` : `<p class="tb-note">O'zgartirish — Masofaviy ta'lim bo'limi boshlig'ida.</p>`}</form>
      <h4>AI</h4><p class="muted">${M.ai.on ? `Ulangan · model ${esc(M.ai.model)} · bir foydalanuvchi uchun kuniga ${M.ai.daily} ta mavzu generatsiyasi (bugun ${M.ai.used_today})` : "AI ulanmagan — administratorga murojaat qiling. Savollar hozircha qo'lda kiritiladi."}
        Claude'ga faqat fan/mavzu nomi va yuklangan mavzu matni yuboriladi.</p></div></div>
    <div class="card tb-card"><h3>Sifat nazorati qoidalari</h3><p class="muted">Har bir savol saqlanganda avtomatik tekshiriladi. Bloklovchi — tekshiruvga yuborish va tasdiqlashni to'xtatadi; ogohlantirish — tekshiruvchi e'tiboriga.</p>
      ${tbTable([["Qoida", r => esc(r[1].label)], ["Turi", r => r[1].sev === "block" ? tbChip("Bloklovchi", "bad") : tbChip("Ogohlantirish", "warn")]], Object.entries(M.rules))}</div>`;
  box.querySelector("#tbMq").onsubmit = async e => {
    e.preventDefault(); if (!M.caps.settings) return;
    const r = await tbApi("/api/testbank/settings", {min_q: +box.querySelector("#tbMqv").value});
    if (r) { toast("Saqlandi"); TB.meta = null; }
  };
  const drawSplit = async () => {
    const el = box.querySelector("#tbSp");
    if (!TB.cid) { el.innerHTML = `<div class="tb-empty">Kurs topilmadi</div>`; return; }
    const d = await tbApi(`/api/testbank/courses/${TB.cid}`), c = d.course;
    el.innerHTML = `<h3>Oraliq taqsimoti</h3><p class="muted">${esc(c.subject)} · ${esc(c.direction)}, ${c.course}-kurs · ${c.topics} mavzu</p>
      <form id="tbSf2" class="tb-form"><label>1-oraliq: 1-mavzudan shu mavzugacha<input type="number" id="tbSk" min="1" max="${c.topics - 1}" value="${c.split}" ${d.can.split ? "" : "disabled"}></label>
        <p class="tb-note" id="tbSn"></p>${d.can.split ? `<div class="tb-acts"><button class="btn sm primary">Saqlash</button><button type="button" class="btn sm ghost" id="tbSd">Standart (${c.split_default})</button></div>` : ""}</form>`;
    const k = el.querySelector("#tbSk"), note = el.querySelector("#tbSn");
    const upd = () => { const v = Math.max(1, Math.min(c.topics - 1, +k.value || 1)); note.textContent = `1-oraliq banki: 1–${v}-mavzular · 2-oraliq banki: ${v + 1}–${c.topics}-mavzular`; };
    k.oninput = upd; upd();
    el.querySelector("#tbSd")?.addEventListener("click", () => { k.value = c.split_default; upd(); });
    el.querySelector("#tbSf2").onsubmit = async e => {
      e.preventDefault();
      const r = await tbApi(`/api/testbank/courses/${TB.cid}/split`, {oraliq1_to: +k.value});
      if (r) toast(`Saqlandi: 1-oraliq — 1–${r.split}-mavzular`);
    };
  };
  await tbPicker(box.querySelector("#tbPk"), drawSplit);
  await drawSplit();
}

/* ---------- navigatsiya: go("testbank") (app.js go() xaritasiga tegmasdan) ---------- */
(function () {
  if (typeof go !== "function" || go._tb) return;
  const prev = go;
  go = function (v, opts) {
    prev(v, opts);
    if (v !== "testbank") return;
    const tab = opts && typeof opts === "object" ? opts.tab : undefined;
    Promise.resolve().then(() => renderTestbank(tab)).catch(e => { if (e?.message === "auth") return; $("#v-testbank").innerHTML = e?.message === "denied" ? locked("Bu bo'lim") : errCard("testbank"); });
  };
  go._tb = true;
})();

/* ---------- chiqish / sessiya tugashi: app.js showLogin() — keyingi foydalanuvchiga oldingisining holati qolmasin ---------- */
(function () {
  if (typeof showLogin !== "function" || showLogin._tb) return;
  const prev = showLogin;
  showLogin = function (...a) { tbReset(); return prev.apply(this, a); };
  showLogin._tb = true;
})();
