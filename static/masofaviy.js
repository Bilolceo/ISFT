/* =====================================================================
   «Masofaviy ta'lim» (app/masofaviy.py, /api/masofaviy) — Masofaviy ta'lim bo'limi ish stoli.
     Umumiy:     talabalar va kontent ko'rsatkichlari, kafedralar holati, AI xulosa, hisobot (.docx).
     Talabalar:  aktiv / noaktiv / kirmagan, videokonferensiya, o'zlashtirish, buyruq holati; talaba kartasi (haftalik faollik).
     Kontent:    kafedra / o'qituvchi / yo'nalish kesimida; materiallar ro'yxati — tasdiqlash, qaytarish, «yuklandi» (o'qituvchi).
     Xavf:       talabalar (sabablar bilan) va kechikayotgan o'qituvchilar.   Hafta: muddatlar va yangi noaktivlar.
     Import:     LMS faolligi va kontent nazorat varag'i (CSV/XLSX), qoidalar.
   Ruxsat va ko'lam serverda (rahbariyatga talaba ismlari yuborilmaydi). Global: renderMasofaviy().
   app.js yordamchilari: $, esc, fmt, toast, locked, errCard, showLogin, ico, ME.
   ===================================================================== */
const DL_ST0 = {state: "", reason: "", direction: "", course: 0, q: "", sort: "risk", offset: 0};
const DL_CT0 = {view: "kafedra", due: "overdue", status: "", kind: "", q: "", department_id: 0, teacher_id: 0, direction: "", offset: 0};
/* who — meta qaysi foydalanuvchi uchun olingan (app.js ME). Boshqa foydalanuvchi kirsa (sahifa qayta yuklanmasdan) — holat tozalanadi. */
const DL = {meta: null, who: null, tab: null, st: {...DL_ST0}, ct: {...DL_CT0}};
function dlReset() { DL.meta = null; DL.who = null; DL.tab = null; DL.st = {...DL_ST0}; DL.ct = {...DL_CT0}; }
const dlSafeUrl = u => /^https?:\/\/[^\s<>"']+$/i.test(String(u || "").trim()) ? String(u).trim() : "";   /* faqat http(s) — javascript: va h.k. emas */
if (!document.querySelector('link[href="masofaviy.css"]')) document.head.insertAdjacentHTML("beforeend", '<link rel="stylesheet" href="masofaviy.css">');
if (typeof ICONS === "object" && !ICONS.upload) ICONS.upload = '<path d="M12 21V9M7 14l5-5 5 5"/><path d="M4 3h16"/>';
if (typeof ICONS === "object" && !ICONS.monitor) ICONS.monitor = '<rect x="2" y="3" width="20" height="14" rx="2"/><path d="M8 21h8"/><path d="M12 17v4"/><path d="m9 8 2 2 4-4"/>';

const DL_TABS = {umumiy: "Umumiy", talabalar: "Talabalar", kontent: "O'quv kontenti", xavf: "Xavf ostida", hafta: "Bu hafta", import: "Import va qoidalar"};
const DL_STATE = {aktiv: ["Aktiv", "ok"], noaktiv: ["Noaktiv", "warn"], kirmagan: ["Kirmagan", "bad"], tatil: ["Ta'tilda", ""]};
const DL_IST = {kutilmoqda: ["Yuklanmagan", "bad"], yuklandi: ["Tekshiruvda", "info"], tasdiqlandi: ["Tasdiqlangan", "ok"], qaytarildi: ["Qaytarilgan", "warn"]};
const dlD = s => { s = String(s || "").slice(0, 10); return s.length === 10 ? `${s.slice(8, 10)}.${s.slice(5, 7)}.${s.slice(0, 4)}` : "—"; };
const dlDT = s => s ? `${dlD(s)} ${String(s).slice(11, 16)}` : "—";
const dlChip = (t, cls = "") => `<span class="dl-chip ${cls}">${esc(t)}</span>`;
const dlPct = v => v == null ? "—" : `${String(v).replace(".", ",")}%`;
const dlKpi = (label, val, sub = "", cls = "", link = "") =>
  `<${link ? `button type="button" data-go="${esc(link)}"` : "div"} class="dl-kpi ${cls}"><span>${esc(label)}</span><b>${val}</b>${sub ? `<small>${sub}</small>` : ""}</${link ? "button" : "div"}>`;
const dlBar = (pct, cls = "") => `<div class="dl-bar ${cls}" role="img" aria-label="${dlPct(pct)}"><i style="width:${Math.max(0, Math.min(100, pct || 0))}%"></i></div>`;
const dlHealth = s => ({ok: "ok", warn: "warn", bad: "bad"})[s] || "";
const dlDays = n => n == null ? "" : n < 0 ? `${-n} kun o'tdi` : n === 0 ? "bugun" : `${n} kun qoldi`;

async function dlApi(url, body, method) {
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
function dlTable(cols, rows, {rowCls = () => "", empty = "Ma'lumot yo'q", rowAttr = () => ""} = {}) {
  if (!rows.length) return `<div class="dl-empty">${esc(empty)}</div>`;
  return `<div class="tw"><table class="dl-t"><thead><tr>${cols.map(c => `<th class="${c[2] || ""}">${esc(c[0])}</th>`).join("")}</tr></thead><tbody>` +
    rows.map(r => `<tr class="${rowCls(r)}" ${rowAttr(r)}>${cols.map(c => `<td data-l="${esc(c[0])}" class="${c[2] || ""}"><div>${c[1](r) ?? ""}</div></td>`).join("")}</tr>`).join("") +
    `</tbody></table></div>`;
}
function dlModal(title, html, onOk, okText = "Saqlash", wide = false) {
  const bg = document.createElement("div"); bg.className = "dl-modal-bg";
  bg.innerHTML = `<div class="dl-modal ${wide ? "wide" : ""}" role="dialog" aria-modal="true" aria-label="${esc(title)}"><h3>${esc(title)}</h3>${html}
    <div class="dl-acts end"><button type="button" class="btn ghost" data-x>${onOk ? "Bekor qilish" : "Yopish"}</button>${onOk ? `<button type="button" class="btn primary" data-ok>${esc(okText)}</button>` : ""}</div></div>`;
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
function dlPager(total, offset, limit, onGo) {
  if (total <= limit) return "";
  const id = "dlpg" + Math.random().toString(36).slice(2, 7);
  setTimeout(() => document.querySelectorAll(`#${id} [data-p]`).forEach(b => b.onclick = () => onGo(+b.dataset.p)), 0);
  return `<div class="dl-pager" id="${id}"><button type="button" class="btn sm ghost" data-p="${Math.max(0, offset - limit)}" ${offset ? "" : "disabled"}>← Oldingi</button>
    <span>${fmt(offset + 1)}–${fmt(Math.min(total, offset + limit))} / ${fmt(total)}</span>
    <button type="button" class="btn sm ghost" data-p="${offset + limit}" ${offset + limit < total ? "" : "disabled"}>Keyingi →</button></div>`;
}

/* ---------- asosiy ko'rinish ---------- */
async function renderMasofaviy(tab) {
  const v = $("#v-masofaviy");
  const who = typeof ME !== "undefined" ? ME : null;
  if (DL.who !== who) { const want = tab || DL.tab; dlReset(); DL.who = who; tab = want; }   /* boshqa foydalanuvchi: eski rol/yorliq/filtrlar qolmasin */
  /* havola (Mening vazifalarim, bosh sahifa) yorlig'i filtr bilan kelishi mumkin: "kontent:view=materiallar,status=yuklandi" */
  const spec = tab || DL.tab;
  if (spec && String(spec).includes(":")) tab = dlSpec(String(spec));
  if (!DL.meta) { const m = await dlApi("/api/masofaviy/meta"); if (DL.who !== who) return; DL.meta = m; }
  const M = DL.meta;
  DL.tab = tab && M.tabs.includes(tab) ? tab : (DL.tab && M.tabs.includes(DL.tab) ? DL.tab : M.tabs[0]);
  const demo = M.source === "demo";
  v.innerHTML = `<div class="dl-head"><div><h2>Masofaviy ta'lim</h2><span class="muted">${esc(M.scope)} · ${dlD(M.today)}</span></div>
      <div class="dl-acts">${typeof renderTestbank === "function" && !document.querySelector('#nav a[data-v="testbank"]')?.classList.contains("hidden") ? `<button type="button" class="btn sm ghost" data-tb>${ico("checkc", 15)} Test bank</button>` : ""}${M.caps.report ? `<a class="btn sm" href="/api/masofaviy/report.docx">${ico("report", 15)} Hisobot (.docx)</a>` : ""}</div></div>
    ${demo ? `<div class="dl-demo">${ico("info", 15)}<span><b>Namuna ma'lumot.</b> LMS faolligi va kontent holati — demo. Haqiqiy LMS va videokonferensiya eksportini «Import» bo'limidan yuklang yoki API ulanadi.</span></div>` : ""}
    <div class="dl-tabs" role="tablist">${M.tabs.map(t => `<button type="button" role="tab" aria-selected="${t === DL.tab}" class="${t === DL.tab ? "on" : ""}" data-t="${t}">${esc(DL_TABS[t])}</button>`).join("")}</div>
    <div id="dlBox"><div class="dl-empty">Yuklanmoqda…</div></div>`;
  v.querySelectorAll(".dl-tabs [data-t]").forEach(b => b.onclick = () => { DL.tab = b.dataset.t; renderMasofaviy(DL.tab); });
  v.querySelector("[data-tb]")?.addEventListener("click", () => go("testbank"));   /* Test bank — mavzu testlari va oraliq banklari (testbank.js) */
  const box = $("#dlBox");
  try {
    await ({umumiy: dlOverview, talabalar: dlStudents, kontent: dlContent, xavf: dlRisk, hafta: dlWeek, import: dlImport})[DL.tab](box);
  } catch (e) {
    if (e?.message === "auth") return;
    box.innerHTML = e?.message === "denied" ? locked("Bu bo'lim") : `<div class="card dl-card"><p>${esc(e?.msg || "Ma'lumotni yuklab bo'lmadi")}</p></div>`;
  }
  box.querySelectorAll("[data-go]").forEach(b => b.onclick = () => dlGo(b.dataset.go));
}
function dlSpec(spec) {   /* "tab" yoki "tab:kalit=qiymat,..." → filtrlar DL.st / DL.ct ga yoziladi, yorliq nomi qaytadi */
  const i = spec.indexOf(":"), tab = i < 0 ? spec : spec.slice(0, i), q = i < 0 ? "" : spec.slice(i + 1);
  const tgt = tab === "talabalar" ? DL.st : DL.ct, base = tab === "talabalar" ? DL_ST0 : DL_CT0;
  if (q) q.split(",").forEach(p => { const j = p.indexOf("="), k = p.slice(0, j); let val = p.slice(j + 1);
    try { val = decodeURIComponent(val); } catch (e) { /* noto'g'ri kodlash — matn o'zicha */ }
    if (j > 0 && k in base && k !== "offset") tgt[k] = typeof base[k] === "number" ? (+val || 0) : val; });
  tgt.offset = 0;
  return tab;
}
function dlGo(spec) { renderMasofaviy(dlSpec(spec)); }

/* ---------- Umumiy ---------- */
async function dlOverview(box) {
  const d = await dlApi("/api/masofaviy/overview");
  const s = d.students, c = d.content, t = c.total, w = d.week, M = DL.meta;
  const base = s.total - s.tatil;
  box.innerHTML = `
    <h3 class="dl-sec">Talabalar <span class="muted">· ${fmt(s.total)} nafar masofaviy ta'lim talabasi</span></h3>
    <div class="dl-kpis">
      ${dlKpi("LMS'da aktiv", fmt(s.aktiv), `${dlPct(+(100 * s.aktiv / (base || 1)).toFixed(1))} · oxirgi ${M.policy.inactive_days} kunda kirgan`, "ok", M.names ? "talabalar:state=aktiv" : "")}
      ${dlKpi("Noaktiv", fmt(s.noaktiv), `${M.policy.inactive_days} kundan ortiq kirmagan`, s.noaktiv ? "warn" : "", M.names ? "talabalar:state=noaktiv" : "")}
      ${dlKpi("LMS'ga umuman kirmagan", fmt(s.kirmagan), "login berilganmi — tekshirish kerak", s.kirmagan ? "bad" : "", M.names ? "talabalar:state=kirmagan" : "")}
      ${dlKpi("O'zlashtirmagan", fmt(s.ozlashtirmagan), `qarzdor ${fmt(s.qarzdor)} · oraliqdan past ${fmt(s.oraliq_xavf)}`, s.ozlashtirmagan ? "warn" : "", M.names ? "talabalar:reason=qarz" : "")}
      ${dlKpi("Videokonferensiya", dlPct(s.vc_pct), `qatnashish · ${M.policy.vc_min_pct}% dan past: ${fmt(s.vc_low)}`, (s.vc_pct || 0) < 70 ? "warn" : "", M.names ? "talabalar:reason=vk" : "")}
      ${dlKpi("Buyruq holati", fmt(s.buyruq_muammo + s.buyruq_jarayon), `nomuvofiq ${fmt(s.buyruq_muammo)} · imzolanmagan ${fmt(s.buyruq_jarayon)}`, s.buyruq_muammo ? "bad" : s.buyruq_jarayon ? "warn" : "ok", M.names ? "talabalar:reason=buyruq_jarayon" : "")}
    </div>
    <h3 class="dl-sec">O'quv kontenti <span class="muted">· semestr rejasi ${fmt(t.plan)} ta material, muddati kelgani ${fmt(t.due)}</span></h3>
    <div class="dl-kpis">
      ${dlKpi("Berilgan (muddati kelganlardan)", dlPct(t.pct), `${fmt(t.given)} / ${fmt(t.due)} · semestr bo'yicha ${dlPct(t.plan_pct)}`, t.pct >= 95 ? "ok" : t.pct >= 85 ? "warn" : "bad")}
      ${dlKpi("Muddati o'tgan", fmt(t.overdue), "yuklanmagan yoki qaytarilgan", t.overdue ? "bad" : "ok", "kontent:view=materiallar,due=overdue")}
      ${dlKpi("Bugun oxirgi kun", fmt(t.today), "hali yuklanmagan", t.today ? "warn" : "ok", "kontent:view=materiallar,due=today")}
      ${dlKpi(`Yaqin ${M.policy.soon_days} kunda`, fmt(t.soon), "muddati yaqinlashmoqda", "", "kontent:view=materiallar,due=soon")}
      ${dlKpi("Tekshiruvda", fmt(t.review), "o'qituvchi yukladi, tasdiq kutilmoqda", t.review ? "info" : "", "kontent:view=materiallar,due=,status=yuklandi")}
      ${dlKpi("Qaytarilgan", fmt(t.returned), "qayta yuklash kerak", t.returned ? "warn" : "", "kontent:view=materiallar,due=,status=qaytarildi")}
    </div>
    <div class="card dl-card"><div class="dl-item-h"><div><h3>Kafedralar: kontent berilishi</h3><p class="muted">Muddati kelgan materiallardan berilgani · eng ortda turganlari yuqorida${M.caps.remind ? " · «Topshiriq» — kafedra mudiriga muddati o'tgan materiallar ro'yxati" : ""}</p></div></div>
      ${dlDeptTable(c.departments)}</div>
    <div class="card dl-card" id="dlAi"></div>
    <div class="dl-grid">
      <div class="card dl-card"><h3>Yo'nalishlar: talabalar faolligi</h3><p class="muted">Eng past aktivlik yuqorida</p>
        ${dlTable([["Yo'nalish", r => esc(r.direction)], ["Talaba", r => fmt(r.n), "num"], ["Aktiv", r => `${dlBar(r.aktiv_pct, r.aktiv_pct < 85 ? "warn" : "ok")}<small>${dlPct(r.aktiv_pct)}</small>`],
                   ["Noaktiv / kirmagan", r => `${fmt(r.noaktiv)} / ${fmt(r.kirmagan)}`, "num"], ["Qarzdor", r => fmt(r.qarzdor), "num"]], s.by_direction.slice(0, 8))}</div>
      <div class="card dl-card"><h3>Bu hafta</h3><p class="muted">${dlD(w.monday)} – ${dlD(w.sunday)}</p>
        <dl class="dl-dl"><dt>Muddati shu hafta</dt><dd>${fmt(w.content.this_week)} ta material, ochiq ${fmt(w.content.open)}</dd>
          <dt>Bugun tugaydi</dt><dd>${fmt(w.content.today_open)} ta yuklanmagan</dd>
          <dt>Keyingi hafta</dt><dd>${fmt(w.content.next_week_open)} ta hali yuklanmagan</dd>
          ${w.students ? `<dt>Yangi noaktiv</dt><dd>${fmt(w.students.newly_inactive)} nafar (shu hafta ${M.policy.inactive_days} kunlik chegaradan o'tdi)</dd>
          <dt>LMS'ga kirganlar</dt><dd>${fmt(w.students.active_this_week)} nafar (o'tgan hafta ${fmt(w.students.active_prev_week)})</dd>
          <dt>Videokonferensiya</dt><dd>${dlPct(w.students.vc_pct_week)} qatnashish</dd>` : ""}</dl>
        <button type="button" class="btn sm" data-go="hafta">Haftalik ro'yxat →</button></div>
    </div>`;
  dlBindRemind(box);
  dlAiCard($("#dlAi"));
}
function dlDeptTable(rows) {
  const M = DL.meta;
  return dlTable([["Kafedra", r => `<button type="button" class="dl-link" data-go="kontent:view=materiallar,department_id=${r.department_id},due=overdue">${esc(r.name)}</button>`],
                  ["Berilgan", r => `${dlBar(r.pct, dlHealth(r.status))}<small>${dlPct(r.pct)} · ${fmt(r.given)}/${fmt(r.due)}</small>`],
                  ["Muddati o'tgan", r => r.overdue ? `<b class="dl-bad">${fmt(r.overdue)}</b><small>${fmt(r.teachers_lagging)} o'qituvchi</small>` : "0", "num"],
                  ["Bugun / yaqin", r => `${fmt(r.today)} / ${fmt(r.soon)}`, "num"],
                  ...(M.caps.remind ? [["", r => r.overdue ? `<button type="button" class="btn sm" data-remind="${r.department_id}" data-n="${esc(r.name)}">Topshiriq</button>` : ""]] : [])],
                 rows, {rowCls: r => r.status === "bad" ? "dl-row-bad" : ""});
}
function dlBindRemind(root) {
  root.querySelectorAll("[data-remind]").forEach(b => b.onclick = () => dlModal(`Kafedraga topshiriq: ${b.dataset.n}`, `
      <p class="muted">Kafedra mudiri navbatiga «Topshiriqlar» orqali muddati o'tgan barcha materiallar ro'yxati (o'qituvchilar kesimida) yuboriladi. Bir kunda bir marta.</p>
      <label>Bajarish muddati<select id="dlRd"><option value="2">2 kun</option><option value="3" selected>3 kun</option><option value="5">5 kun</option><option value="7">7 kun</option></select></label>`,
    async m => {
      const r = await dlApi("/api/masofaviy/remind", {department_id: +b.dataset.remind, days: +m.querySelector("#dlRd").value});
      if (r) toast(r.already ? "Bugun bu kafedraga topshiriq allaqachon yuborilgan" : `Topshiriq yuborildi: ${r.items} ta material, ${r.teachers} o'qituvchi · muddat ${dlD(r.due)}`);
      return !!r;
    }, "Yuborish"));
}
async function dlAiCard(el, force = false) {
  if (!el) return;
  const M = DL.meta;
  if (!M.caps.ai) { el.remove(); return; }
  el.innerHTML = `<div class="dl-item-h"><div><h3>Xulosa ${M.ai === "claude" ? dlChip("AI", "info") : dlChip("qoidaga asoslangan")}</h3>
      <p class="muted">Faqat jamlangan raqamlar asosida. ${M.ai === "claude" ? "AI matnidagi har bir raqam tizim faktlari bilan solishtiriladi." : "AI ulanmagan — xulosa qoidalar bo'yicha tuziladi."}</p></div></div>
    <div id="dlAiBody"><button type="button" class="btn primary" id="dlAiGo">${ico("spark", 15)} Xulosa tayyorlash</button></div>`;
  const run = async f => {
    const body = $("#dlAiBody"); body.innerHTML = `<div class="dl-empty">${M.ai === "claude" ? "AI xulosa tayyorlanmoqda (10–40 soniya)…" : "Tayyorlanmoqda…"}</div>`;
    const r = await dlApi("/api/masofaviy/ai/summary", {force: f});
    if (!r) { body.innerHTML = `<button type="button" class="btn primary" id="dlAiGo">Qayta urinish</button>`; $("#dlAiGo").onclick = () => run(false); return; }
    const list = (t, a) => a?.length ? `<h4>${t}</h4><ul class="dl-list">${a.map(x => `<li>${esc(x)}</li>`).join("")}</ul>` : "";
    body.innerHTML = `<p class="dl-sum">${esc(r.xulosa)}</p>${list("Asosiy faktlar", r.asosiy)}${list("Xavflar", r.xavflar)}${list("Tavsiyalar", r.tavsiyalar)}
      ${r.ai_error ? `<p class="dl-note">AI ishlamadi (${esc(r.ai_error)}) — qoidaga asoslangan xulosa ko'rsatildi.</p>` : ""}
      ${r.removed?.length ? `<p class="dl-note">${r.removed.length} ta jumla olib tashlandi: raqami tizim faktlarida yo'q.</p>` : ""}
      <p class="dl-note">${r.engine === "claude" ? "AI (Claude)" : "Qoidalar"} · ${dlDT(r.ts)}${r.cached ? " · ma'lumot o'zgarmagan, saqlangan xulosa" : ""}
        <button type="button" class="dl-link" id="dlAiRe">Qayta tayyorlash</button></p>`;
    $("#dlAiRe").onclick = () => run(true);
  };
  $("#dlAiGo").onclick = () => run(force);
}

/* ---------- Talabalar ---------- */
async function dlStudents(box) {
  const S = DL.st, M = DL.meta;
  const qs = new URLSearchParams({state: S.state, reason: S.reason, direction: S.direction, course: S.course || 0, q: S.q, sort: S.sort, offset: S.offset, limit: 50});
  const d = await dlApi("/api/masofaviy/students?" + qs);
  const reasons = {"": "Barcha sabablar", kirmagan: "LMS'ga kirmagan", noaktiv: "Noaktiv", notekis: "Notekis faollik", erta_sust: "Semestr boshida sust",
                   vk: "Videokonferensiya kam", topshiriq: "Topshiriqlar bajarilmagan",
                   oraliq: "Oraliqdan past", qarz: "Akademik qarz", buyruq: "Buyruq nomuvofiq", buyruq_jarayon: "Buyruq imzolanmagan"};
  box.innerHTML = `<div class="card dl-card">
    <div class="dl-filters">
      <div class="dl-seg" role="group" aria-label="Holat">${[["", "Barchasi"], ["aktiv", "Aktiv"], ["noaktiv", "Noaktiv"], ["kirmagan", "Kirmagan"], ["tatil", "Ta'tilda"]]
        .map(([k, l]) => `<button type="button" class="${S.state === k ? "on" : ""}" data-state="${k}">${l}</button>`).join("")}</div>
      <select id="dlR" aria-label="Sabab">${Object.entries(reasons).map(([k, l]) => `<option value="${k}" ${S.reason === k ? "selected" : ""}>${esc(l)}</option>`).join("")}</select>
      <select id="dlDir" aria-label="Yo'nalish"><option value="">Barcha yo'nalishlar</option>${d.directions.map(x => `<option ${S.direction === x ? "selected" : ""}>${esc(x)}</option>`).join("")}</select>
      <select id="dlC" aria-label="Kurs"><option value="0">Barcha kurslar</option>${[1, 2, 3, 4].map(k => `<option value="${k}" ${S.course === k ? "selected" : ""}>${k}-kurs</option>`).join("")}</select>
      <select id="dlSort" aria-label="Tartib">${[["risk", "Xavf bo'yicha"], ["days", "Uzoq kirmaganlar"], ["vc", "VK qatnashish (past)"], ["name", "F.I.Sh."]].map(([k, l]) => `<option value="${k}" ${S.sort === k ? "selected" : ""}>${l}</option>`).join("")}</select>
      <input id="dlQ" type="search" placeholder="Ism, HEMIS ID yoki guruh" value="${esc(S.q)}" aria-label="Qidiruv">
    </div>
    <p class="muted">${fmt(d.total)} nafar · qatorni bosing — talaba kartasi (haftalik faollik, baholar, buyruqlar)</p>
    ${dlTable([["Talaba", r => `<button type="button" class="dl-link" data-sid="${r.id}">${esc(r.full_name)}</button><small>${esc(r.grp)} · ${esc(r.direction)}</small>`],
               ["LMS", r => `${dlChip(DL_STATE[r.state][0], DL_STATE[r.state][1])}<small>${r.last_login ? `oxirgi: ${dlD(r.last_login)}` : "hech qachon"}</small>`],
               ["VK", r => r.vc_pct == null ? "—" : `<span class="${r.vc_pct < M.policy.vc_min_pct ? "dl-bad" : ""}">${dlPct(r.vc_pct)}</span>`, "num"],
               ["Oraliq", r => r.oraliq_avg == null ? "—" : `${String(r.oraliq_avg).replace(".", ",")}${r.oraliq_low ? `<small class="dl-bad">${r.oraliq_low} fanda past</small>` : ""}`, "num"],
               ["Qarz", r => r.debts ? `<b class="dl-bad">${r.debts}</b>` : "0", "num"],
               ["Sabablar", r => r.reasons.length ? r.reasons.map(x => dlChip(x.label, x.sev >= 3 ? "bad" : x.sev === 2 ? "warn" : "")).join(" ") : `<span class="muted">—</span>`]],
              d.items, {rowCls: r => r.risk >= 4 ? "dl-row-bad" : "", empty: "Tanlangan shart bo'yicha talaba yo'q"})}
    ${dlPager(d.total, S.offset, 50, o => { S.offset = o; renderMasofaviy("talabalar"); })}</div>`;
  const re = () => { S.offset = 0; renderMasofaviy("talabalar"); };
  box.querySelectorAll("[data-state]").forEach(b => b.onclick = () => { S.state = b.dataset.state; re(); });
  $("#dlR").onchange = e => { S.reason = e.target.value; re(); };
  $("#dlDir").onchange = e => { S.direction = e.target.value; re(); };
  $("#dlC").onchange = e => { S.course = +e.target.value; re(); };
  $("#dlSort").onchange = e => { S.sort = e.target.value; re(); };
  let tmr; $("#dlQ").oninput = e => { clearTimeout(tmr); tmr = setTimeout(() => { S.q = e.target.value.trim(); re(); }, 350); };
  if (S.q) { const q = $("#dlQ"); q.focus(); q.setSelectionRange(q.value.length, q.value.length); }
  box.querySelectorAll("[data-sid]").forEach(b => b.onclick = () => dlStudentCard(+b.dataset.sid));
}
async function dlStudentCard(sid) {
  let r; try { r = await dlApi(`/api/masofaviy/students/${sid}`); } catch (e) { toast(e?.msg || "Ochib bo'lmadi"); return; }
  const mx = Math.max(1, ...r.weeks.map(w => w.logins));
  const weeks = r.weeks.map(w => `<div class="dl-wk" title="${dlD(w.week)}: ${w.logins} kirish, VK ${w.vc_att}/${w.vc_total}, topshiriq ${w.tasks_done}/${w.tasks_total}">
      <i style="height:${Math.round(100 * w.logins / mx)}%" class="${w.logins ? "" : "zero"}"></i><span>${dlD(w.week).slice(0, 5)}</span><small>${w.vc_att}/${w.vc_total}</small></div>`).join("");
  dlModal(r.full_name, `
    <div class="dl-chips">${dlChip(DL_STATE[r.state][0], DL_STATE[r.state][1])}${dlChip(r.grp)}${dlChip(r.course + "-kurs")}${dlChip("HEMIS " + r.hemis_id)}${r.status !== "faol" ? dlChip(r.status, "warn") : ""}</div>
    <dl class="dl-dl"><dt>Yo'nalish</dt><dd>${esc(r.direction)}</dd><dt>Oxirgi kirish</dt><dd>${r.last_login ? `${dlDT(r.last_login)} (${r.days} kun oldin)` : "LMS'ga hech qachon kirmagan"}</dd>
      <dt>Videokonferensiya</dt><dd>${r.vc_pct == null ? "—" : dlPct(r.vc_pct)} (oxirgi ${DL.meta.policy.window_weeks} hafta)</dd><dt>LMS topshiriqlari</dt><dd>${r.tasks_pct == null ? "—" : dlPct(r.tasks_pct)}</dd></dl>
    <h4>Haftalik faollik <span class="muted">(ustun — kirishlar, pastda — VK qatnashgan/jami)</span></h4><div class="dl-weeks">${weeks || '<div class="dl-empty">Ma\'lumot yo\'q</div>'}</div>
    ${r.reasons.length ? `<h4>Xavf sabablari</h4><ul class="dl-list">${r.reasons.map(x => `<li>${esc(x.label)}</li>`).join("")}</ul>` : ""}
    <h4>Joriy semestr — oraliq nazorat <span class="muted">(kamida ${r.oraliq_min} / 30)</span></h4>
    ${dlTable([["Fan", g => esc(g.subject)], ["Oraliq", g => g.oraliq == null ? "—" : `<span class="${g.oraliq < r.oraliq_min ? "dl-bad" : ""}">${g.oraliq}</span>`, "num"]], r.grades, {empty: "Baho yo'q"})}
    ${r.debts.length ? `<h4>Akademik qarzlar</h4>${dlTable([["Fan", g => esc(g.subject)], ["Ball", g => g.score, "num"]], r.debts)}` : ""}
    ${r.order_issues.length || r.order_pending ? `<h4>Buyruqlar</h4><ul class="dl-list">${r.order_issues.map(x => `<li>${esc(x)}</li>`).join("")}${r.order_pending ? `<li>Imzolanmagan buyruq loyihasi: ${r.order_pending} ta (Registrator ofisi)</li>` : ""}</ul>` : ""}`,
    null, "", true);
}

/* ---------- O'quv kontenti ---------- */
async function dlContent(box) {
  const T = DL.ct, M = DL.meta;
  const views = M.role === "oqituvchi" ? [["materiallar", "Materiallarim"]] :
    [["kafedra", "Kafedralar"], ["oqituvchi", "O'qituvchilar"], ["yonalish", "Yo'nalishlar"], ["materiallar", "Materiallar"]];
  if (!views.some(v => v[0] === T.view)) T.view = views[0][0];
  const seg = `<div class="dl-seg" role="group" aria-label="Kesim">${views.map(([k, l]) => `<button type="button" class="${T.view === k ? "on" : ""}" data-view="${k}">${l}</button>`).join("")}</div>`;
  if (T.view !== "materiallar") {
    const c = await dlApi("/api/masofaviy/content");
    let body = "";
    if (T.view === "kafedra") body = dlDeptTable(c.departments);
    else if (T.view === "oqituvchi") body = dlTable([
        ["O'qituvchi", r => `<button type="button" class="dl-link" data-go="kontent:view=materiallar,teacher_id=${r.teacher_id},department_id=0,due=">${esc(r.name)}</button><small>${esc(r.dept || "")}</small>`],
        ["Berilgan", r => `${dlBar(r.pct, dlHealth(r.status))}<small>${dlPct(r.pct)} · ${fmt(r.given)}/${fmt(r.due)}</small>`],
        ["Muddati o'tgan", r => r.overdue ? `<b class="dl-bad">${fmt(r.overdue)}</b>` : "0", "num"], ["Bugun", r => fmt(r.today), "num"],
        ["Qaytarilgan", r => fmt(r.returned), "num"], ["Tekshiruvda", r => fmt(r.review), "num"]], c.teachers.slice(0, 120), {rowCls: r => r.status === "bad" ? "dl-row-bad" : ""});
    else body = dlTable([
        ["Yo'nalish", r => `<button type="button" class="dl-link" data-go="kontent:view=materiallar,direction=${esc(encodeURIComponent(r.direction || ""))},department_id=0,teacher_id=0,due=overdue">${esc(r.direction)}</button>`],
        ["LMS'ga yuklangan", r => `${dlBar(r.pct, dlHealth(r.status))}<small>${dlPct(r.pct)} · ${fmt(r.given)}/${fmt(r.due)}</small>`],
        ["Yuklanmagan (muddati o'tgan)", r => r.overdue ? `<b class="dl-bad">${fmt(r.overdue)}</b>` : "0", "num"], ["Semestr rejasi", r => fmt(r.plan), "num"]], c.directions);
    const kinds = c.kinds.map(k => `<div class="dl-kind"><span>${esc(k.label)}</span>${dlBar(k.pct, k.pct >= 95 ? "ok" : k.pct >= 85 ? "warn" : "bad")}<small>${dlPct(k.pct)} · muddati o'tgan ${fmt(k.overdue)}</small></div>`).join("");
    box.innerHTML = `<div class="card dl-card"><div class="dl-filters">${seg}</div><div class="dl-kinds">${kinds}</div>${body}</div>`;
    dlBindRemind(box);
  } else {
    const qs = new URLSearchParams({due: T.due, status: T.status, kind: T.kind, q: T.q, department_id: T.department_id || 0, teacher_id: T.teacher_id || 0,
                                   direction: T.direction, offset: T.offset, limit: 100});
    const d = await dlApi("/api/masofaviy/items?" + qs);
    const flt = [T.department_id && "kafedra tanlangan", T.teacher_id && "o'qituvchi tanlangan", T.direction && `yo'nalish: ${T.direction}`].filter(Boolean);
    box.innerHTML = `<div class="card dl-card"><div class="dl-filters">${M.role === "oqituvchi" ? "" : seg}
        <div class="dl-seg" role="group" aria-label="Muddat">${[["overdue", "Muddati o'tgan"], ["today", "Bugun"], ["soon", "Yaqin kunlarda"], ["past", "Muddati kelgan"], ["", "Barchasi"]]
          .map(([k, l]) => `<button type="button" class="${T.due === k ? "on" : ""}" data-due="${k}">${l}</button>`).join("")}</div>
        <select id="dlSt" aria-label="Holat"><option value="">Barcha holatlar</option>${Object.entries(DL_IST).map(([k, v]) => `<option value="${k}" ${T.status === k ? "selected" : ""}>${v[0]}</option>`).join("")}</select>
        <select id="dlK" aria-label="Material turi"><option value="">Barcha turlar</option>${Object.entries(M.kinds).map(([k, v]) => `<option value="${k}" ${T.kind === k ? "selected" : ""}>${esc(v)}</option>`).join("")}</select>
        <input id="dlCq" type="search" placeholder="Fan, mavzu yoki o'qituvchi" value="${esc(T.q)}" aria-label="Qidiruv"></div>
      <p class="muted">${fmt(d.total)} ta material${flt.length ? ` · ${flt.join(", ")} <button type="button" class="dl-link" id="dlClr">filtrni tozalash</button>` : ""}</p>
      ${dlTable([["Fan / mavzu", r => `<b>${esc(r.subject)}</b><small>${r.topic_no}-mavzu${r.topic ? ": " + esc(r.topic) : ""}</small><small>${esc(r.direction)}, ${r.course}-kurs</small>`],
                 ["Tur", r => esc(r.kind_label)],
                 ["O'qituvchi", r => `${esc(r.teacher)}<small>${esc(r.dept || "")}</small>`],
                 ["Muddat", r => `${dlD(r.due)}<small class="${r.days < 0 && ["kutilmoqda", "qaytarildi"].includes(r.status) ? "dl-bad" : ""}">${["kutilmoqda", "qaytarildi"].includes(r.status) ? dlDays(r.days) : ""}</small>`, "num"],
                 ["Holat", r => `${dlChip(DL_IST[r.status][0], DL_IST[r.status][1])}${r.note ? `<small>${esc(r.note)}</small>` : ""}${dlSafeUrl(r.url) ? `<small><a href="${esc(dlSafeUrl(r.url))}" target="_blank" rel="noopener noreferrer">havola</a></small>` : ""}`],
                 ["", r => dlItemActions(r)]], d.items, {empty: "Tanlangan shart bo'yicha material yo'q"})}
      ${dlPager(d.total, T.offset, 100, o => { T.offset = o; renderMasofaviy("kontent"); })}</div>`;
    const re = () => { T.offset = 0; renderMasofaviy("kontent"); };
    box.querySelectorAll("[data-due]").forEach(b => b.onclick = () => { T.due = b.dataset.due; re(); });
    $("#dlSt").onchange = e => { T.status = e.target.value; re(); };
    $("#dlK").onchange = e => { T.kind = e.target.value; re(); };
    let tmr; $("#dlCq").oninput = e => { clearTimeout(tmr); tmr = setTimeout(() => { T.q = e.target.value.trim(); re(); }, 350); };
    if (T.q) { const q = $("#dlCq"); q.focus(); q.setSelectionRange(q.value.length, q.value.length); }
    const clr = $("#dlClr"); if (clr) clr.onclick = () => { Object.assign(T, {department_id: 0, teacher_id: 0, direction: ""}); re(); };
    box.querySelectorAll("[data-rv]").forEach(b => b.onclick = () => dlReview(+b.dataset.rv, b.dataset.ok === "1"));
    box.querySelectorAll("[data-up]").forEach(b => b.onclick = () => dlUpload(+b.dataset.up));
    box.querySelectorAll("[data-lg]").forEach(b => b.onclick = () => dlItemLog(+b.dataset.lg));
  }
  box.querySelectorAll("[data-view]").forEach(b => b.onclick = () => { T.view = b.dataset.view; T.offset = 0; renderMasofaviy("kontent"); });
}
function dlItemActions(r) {
  const C = DL.meta.caps, a = [];
  if (C.review && r.status === "yuklandi") a.push(`<button type="button" class="btn sm primary" data-rv="${r.id}" data-ok="1">Tasdiqlash</button><button type="button" class="btn sm ghost" data-rv="${r.id}" data-ok="0">Qaytarish</button>`);
  if (C.upload && ["kutilmoqda", "qaytarildi"].includes(r.status)) a.push(`<button type="button" class="btn sm primary" data-up="${r.id}">Yuklandi</button>`);
  a.push(`<button type="button" class="dl-link" data-lg="${r.id}">tarix</button>`);
  return `<div class="dl-acts tight">${a.join("")}</div>`;
}
function dlReview(id, ok) {
  if (ok) { dlApi(`/api/masofaviy/items/${id}/review`, {ok: true}).then(r => { if (r) { toast("Tasdiqlandi"); renderMasofaviy("kontent"); } }); return; }
  dlModal("Materialni qaytarish", `<label>Sabab (o'qituvchiga ko'rinadi)<textarea id="dlRn" maxlength="500" placeholder="Masalan: video havolasi ochilmayapti"></textarea></label>`, async m => {
    const r = await dlApi(`/api/masofaviy/items/${id}/review`, {ok: false, note: m.querySelector("#dlRn").value.trim()});
    if (r) { toast("Qaytarildi"); renderMasofaviy("kontent"); } return !!r;
  }, "Qaytarish");
}
function dlUpload(id) {
  dlModal("LMS'ga yuklandi", `<p class="muted">Material LMS'ga yuklangach, havolasini kiriting — Masofaviy ta'lim bo'limi tekshiradi.</p>
    <label>LMS yoki YouTube havolasi<input id="dlUrl" type="url" placeholder="https://" maxlength="500"></label>
    <label>Izoh (ixtiyoriy)<input id="dlUn" maxlength="300"></label>`, async m => {
    const r = await dlApi(`/api/masofaviy/items/${id}/upload`, {url: m.querySelector("#dlUrl").value.trim(), note: m.querySelector("#dlUn").value.trim()});
    if (r) { toast("Belgilandi — tekshiruvga yuborildi"); renderMasofaviy("kontent"); } return !!r;
  }, "Yuborish");
}
async function dlItemLog(id) {
  let d; try { d = await dlApi(`/api/masofaviy/items/${id}/log`); } catch (e) { toast(e?.msg || "Ochib bo'lmadi"); return; }
  dlModal("Material tarixi", d.items.length ? `<ul class="dl-list">${d.items.map(x => `<li><b>${esc(x.action)}</b> · ${dlDT(x.ts)} · ${esc(x.user_name.split(":").pop().trim())}${x.note ? `<br><span class="muted">${esc(x.note)}</span>` : ""}</li>`).join("")}</ul>`
    : `<p class="muted">Tizimda qo'lda o'zgarish yo'q (holat import yoki demo ma'lumotdan).</p>`, null);
}

/* ---------- Xavf ostida ---------- */
async function dlRisk(box) {
  const M = DL.meta;
  const [s, c] = await Promise.all([dlApi("/api/masofaviy/risk?limit=100"), dlApi("/api/masofaviy/risk?kind=content&limit=40")]);
  box.innerHTML = `<div class="dl-grid">
    <div class="card dl-card"><h3>Talabalar: xavf sabablari</h3><p class="muted">Yuqori xavf (≥4 ball): ${fmt(s.high)} · o'rta: ${fmt(s.mid)}. Ball — sabablar og'irligi yig'indisi.</p>
      ${dlTable([["Sabab", r => M.names ? `<button type="button" class="dl-link" data-go="talabalar:reason=${r.code},state=">${esc(r.label)}</button>` : esc(r.label)], ["Talabalar", r => fmt(r.n), "num"]], s.reasons)}</div>
    <div class="card dl-card"><h3>Kechikayotgan o'qituvchilar</h3><p class="muted">Muddati o'tgan (yuklanmagan yoki qaytarilgan) materiallar soni bo'yicha</p>
      ${dlTable([["O'qituvchi", r => `${esc(r.teacher)}<small>${esc(r.dept || "")}</small>`], ["Muddati o'tgan", r => `<b class="dl-bad">${fmt(r.overdue)}</b>${r.returned ? `<small>qaytarilgan ${r.returned}</small>` : ""}`, "num"],
                 ["Eng eskisi", r => `${dlD(r.oldest)}<small>${r.days} kun</small>`, "num"], ["Fanlar", r => esc(r.subjects.join(", "))]], c.items.slice(0, 15))}</div></div>
    ${M.names ? `<div class="card dl-card"><h3>Eng yuqori xavfli talabalar</h3><p class="muted">${fmt(s.total)} nafardan birinchi 100 tasi · har bir sabab tyutor, call-markaz yoki Registrator ofisi ishiga aylanadi</p>
      ${dlTable([["Talaba", r => `<button type="button" class="dl-link" data-sid="${r.id}">${esc(r.full_name)}</button><small>${esc(r.grp)}</small>`],
                 ["Ball", r => `<b class="${r.risk >= 4 ? "dl-bad" : ""}">${r.risk}</b>`, "num"],
                 ["Sabablar", r => r.reasons.map(x => dlChip(x.label, x.sev >= 3 ? "bad" : x.sev === 2 ? "warn" : "")).join(" ")]], s.items)}</div>`
      : `<div class="card dl-card"><p class="muted">Individual ro'yxat Masofaviy ta'lim bo'limida — rahbariyatga jamlangan raqamlar ko'rsatiladi.</p></div>`}`;
  box.querySelectorAll("[data-sid]").forEach(b => b.onclick = () => dlStudentCard(+b.dataset.sid));
}

/* ---------- Bu hafta ---------- */
async function dlWeek(box) {
  const w = await dlApi("/api/masofaviy/week");
  const byDay = {};
  w.content.items.forEach(x => (byDay[x.due] = byDay[x.due] || []).push(x));
  const days = Object.keys(byDay).sort();
  box.innerHTML = `<div class="dl-kpis">
      ${dlKpi("Muddati shu hafta", fmt(w.content.this_week), `${dlD(w.monday)} – ${dlD(w.sunday)}`)}
      ${dlKpi("Hali yuklanmagan", fmt(w.content.open), `shu hafta · muddati o'tgan ${fmt(w.content.overdue_this_week)}`, w.content.open ? "warn" : "ok")}
      ${dlKpi("Bugun oxirgi kun", fmt(w.content.today_open), "yuklanmagan", w.content.today_open ? "bad" : "ok", "kontent:view=materiallar,due=today")}
      ${dlKpi("Keyingi hafta", fmt(w.content.next_week_open), "hali yuklanmagan")}
      ${w.students ? dlKpi("Yangi noaktiv talabalar", fmt(w.students.newly_inactive), "shu hafta chegaradan o'tdi", w.students.newly_inactive ? "warn" : "ok") : ""}
    </div>
    <div class="card dl-card"><h3>Shu haftadagi muddatlar — yuklanmaganlar</h3><p class="muted">Kunlar bo'yicha · ${w.content.items.length >= 200 ? "birinchi 200 tasi" : "hammasi"}</p>
      ${days.length ? days.map(dd => `<details class="dl-day" ${dd === w.today ? "open" : ""}><summary><b>${dlD(dd)}</b> ${dd === w.today ? dlChip("bugun", "warn") : dd < w.today ? dlChip("o'tdi", "bad") : ""} <span class="muted">${byDay[dd].length} ta</span></summary>
        ${dlTable([["Fan / mavzu", r => `<b>${esc(r.subject)}</b><small>${r.topic_no}-mavzu · ${esc(r.direction)}, ${r.course}-kurs</small>`], ["Tur", r => esc(r.kind_label)],
                   ["O'qituvchi", r => `${esc(r.teacher)}<small>${esc(r.dept || "")}</small>`], ["Holat", r => dlChip(DL_IST[r.status][0], DL_IST[r.status][1])]], byDay[dd])}</details>`).join("")
        : `<div class="dl-empty">Shu hafta yuklanmagan material yo'q</div>`}</div>
    ${w.students && w.students.newly_list.length ? `<div class="card dl-card"><h3>Shu hafta noaktiv bo'lgan talabalar</h3><p class="muted">Tyutor va call-markaz bilan bog'lanish tavsiya etiladi</p>
      ${dlTable([["Talaba", r => `<button type="button" class="dl-link" data-sid="${r.id}">${esc(r.full_name)}</button><small>${esc(r.grp)}</small>`],
                 ["Oxirgi kirish", r => `${dlD(r.last_login)}<small>${r.days} kun oldin</small>`, "num"], ["VK", r => dlPct(r.vc_pct), "num"]], w.students.newly_list)}</div>` : ""}`;
  box.querySelectorAll("[data-sid]").forEach(b => b.onclick = () => dlStudentCard(+b.dataset.sid));
}

/* ---------- Import va qoidalar ---------- */
async function dlImport(box) {
  const M = DL.meta, h = await dlApi("/api/masofaviy/imports");
  const card = (kind, title, desc) => `<div class="card dl-card"><h3>${esc(title)}</h3><p class="muted">${desc}</p>
      <div class="dl-acts"><a class="btn sm ghost" href="/api/masofaviy/template/${kind}.csv">${ico("download", 15)} Namuna (CSV)</a>
        <label class="btn sm primary dl-file">${ico("upload", 15)} Fayl yuklash<input type="file" accept=".csv,.xlsx" data-imp="${kind}" hidden></label></div>
      <div id="dlRes-${kind}"></div></div>`;
  box.innerHTML = `<div class="dl-grid">
    ${card("activity", "LMS va videokonferensiya faolligi", "Haftalik eksport: HEMIS ID, hafta (dushanba sanasi), kirishlar, daqiqa, ko'rilgan material, VK qatnashgan/jami, topshiriqlar, oxirgi kirish. Bir hafta qayta yuklansa — yangilanadi.")}
    ${card("content", "Kontent nazorat varag'i", "Bo'limning checklist jadvali: fan, yo'nalish, kurs, mavzu raqami, tur (ma'ruza/taqdimot/video/test), holat (yuklandi/tasdiqlandi/qaytarildi/kutilmoqda), havola, muddat.")}
    </div>
    <div class="card dl-card"><h3>Importlar tarixi</h3><p class="muted">Joriy manba: ${h.source === "demo" ? "namuna (demo) ma'lumot" : "import qilingan ma'lumot"}</p>
      ${dlTable([["Sana", r => dlDT(r.ts), "num"], ["Tur", r => r.kind === "activity" ? "LMS faolligi" : "Kontent"], ["Fayl", r => esc(r.filename)], ["Qatorlar", r => `${fmt(r.ok)} / ${fmt(r.rows)}${r.skipped ? `<small class="dl-bad">${r.skipped} o'tkazib yuborildi</small>` : ""}`, "num"],
                 ["Kim", r => esc((r.user_name || "").split(":").pop().trim())]], h.items, {empty: "Hali import qilinmagan"})}</div>
    <div class="card dl-card"><h3>Qoidalar</h3><p class="muted">${M.caps.policy ? "Chegaralarni o'zgartirish — faqat bo'lim boshlig'i; o'zgarish darhol barcha ko'rsatkichlarga ta'sir qiladi." : "Chegaralarni bo'lim boshlig'i o'zgartiradi."}</p>
      <div class="dl-pol">${Object.entries(M.policy).map(([k, v]) => `<label><span>${esc(M.policy_help[k])}</span><input type="number" data-pk="${k}" value="${v}" ${M.caps.policy ? "" : "disabled"}></label>`).join("")}</div>
      ${M.caps.policy ? `<div class="dl-acts end"><button type="button" class="btn primary" id="dlPolSave">Saqlash</button></div>` : ""}</div>`;
  box.querySelectorAll("[data-imp]").forEach(inp => inp.onchange = async () => {
    const f = inp.files[0]; if (!f) return;
    const res = $(`#dlRes-${inp.dataset.imp}`); res.innerHTML = `<div class="dl-empty">Yuklanmoqda…</div>`;
    const r = await dlApi(`/api/masofaviy/import/${inp.dataset.imp}?name=${encodeURIComponent(f.name)}`, f);
    inp.value = "";
    if (!r) { res.innerHTML = ""; return; }
    res.innerHTML = `<p class="dl-note"><b>${fmt(r.ok)}</b> / ${fmt(r.rows)} qator qabul qilindi${r.skipped ? `, ${fmt(r.skipped)} tasi o'tkazib yuborildi` : ""}.</p>
      ${r.errors.length ? `<ul class="dl-list">${r.errors.map(e => `<li>${esc(e)}</li>`).join("")}</ul>` : ""}`;
    toast("Import yakunlandi"); DL.meta = null;
  });
  const sv = $("#dlPolSave");
  if (sv) sv.onclick = async () => {
    const values = {}; box.querySelectorAll("[data-pk]").forEach(i => values[i.dataset.pk] = +i.value);
    const r = await dlApi("/api/masofaviy/policy", {values});
    if (r) { toast("Qoidalar saqlandi"); DL.meta = null; renderMasofaviy("import"); }
  };
}

/* ---------- chiqish / sessiya tugashi: app.js showLogin() — keyingi foydalanuvchiga oldingisining meta/filtrlari qolmasin ---------- */
(function () {
  if (typeof showLogin !== "function" || showLogin._dl) return;
  const prev = showLogin;
  showLogin = function (...a) { dlReset(); return prev.apply(this, a); };
  showLogin._dl = true;
})();

/* ---------- navigatsiya: go("masofaviy") (app.js go() xaritasiga tegmasdan) ---------- */
(function () {
  if (typeof go !== "function" || go._dl) return;
  const prev = go;
  go = function (v, opts) {
    prev(v, opts);
    if (v !== "masofaviy") return;
    const tab = opts && typeof opts === "object" ? opts.tab : undefined;
    Promise.resolve().then(() => renderMasofaviy(tab)).catch(e => { if (e?.message === "auth") return; $("#v-masofaviy").innerHTML = e?.message === "denied" ? locked("Bu bo'lim") : errCard("masofaviy"); });
  };
  go._dl = true;
})();
