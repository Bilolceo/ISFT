/* =====================================================================
   «Studiya» (app/studio.py, /api/studio) — dars ishlab chiqarish: syomka bandi → AI montaj → operator ko'rigi → YouTube → paket → NEXTID.
     Holat:      bosqichlar bo'yicha jamlanma (kurs / kafedra / o'qituvchi), muddati o'tgan darslar (bo'lim, operator, rahbariyat — faqat jamlangan).
     Kun rejasi: studiya xonalari va slotlar; band qilish, «Syomka qilindi» / «Kelmadi», xom video yuklash, ko'chirish, bekor qilish (operator, bo'lim).
     Montaj:     AI montaj navbati; natijani ko'rish (video, bo'limlar, kesishlar) → «Tasdiqlash» yoki «Qayta montaj» (operator, bo'lim).
     Darslar:    rejadagi kurslar darslari va bosqichlari; o'qituvchida — «Mening darslarim» (o'z bandlari, syomkaga yozilish).
     Sozlamalar: xonalar, SLA muddatlari, YouTube (OAuth sirlari — faqat kiritiladi, hech qachon ko'rsatilmaydi), montaj ishchisi holati.
   Ruxsat va ko'lam serverda. Global: renderStudio(). app.js yordamchilari: $, esc, fmt, toast, locked, errCard, showLogin, ico, ME, go, dmy.
   ===================================================================== */
const STD = {meta: null, who: null, tab: null, day: null, group: "course", cid: 0, room: 0};
function stReset() { Object.assign(STD, {meta: null, who: null, tab: null, day: null, group: "course", cid: 0, room: 0}); }
if (typeof ICONS === "object") {
  if (!ICONS.video) ICONS.video = '<rect x="3" y="5" width="13" height="14" rx="2"/><path d="m16 10 5-3v10l-5-3z"/>';
  if (!ICONS.upload) ICONS.upload = '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><path d="m17 8-5-5-5 5"/><path d="M12 3v12"/>';
  if (!ICONS.chevl) ICONS.chevl = '<path d="m15 18-6-6 6-6"/>';
  if (!ICONS.chevr) ICONS.chevr = '<path d="m9 18 6-6-6-6"/>';
}
if (!document.querySelector('link[href="studio.css"]')) document.head.insertAdjacentHTML("beforeend", '<link rel="stylesheet" href="studio.css">');
/* «Mening vazifalarim» manbasi (mywork.js MW_SRC) — nom va ikonka */
if (typeof MW_SRC === "object" && MW_SRC && !MW_SRC.studio) MW_SRC.studio = {label: "Studiya", icon: "video"};

const ST_TPL_DEF = {maruza_slayd: "Ma'ruza: o'qituvchi + slayd", faqat_oqituvchi: "Faqat o'qituvchi", ekran: "Ekran yozuvi + o'qituvchi burchakda"};
const ST_JOB_TONE = {navbatda: "", ishlanmoqda: "info", tayyor: "warn", operator: "bad", tasdiqlandi: "ok", qayta: "", bekor: ""};
const ST_BK_TONE = {band: "info", otdi: "ok", kelmadi: "bad", bekor: ""};
const ST_DAYS = ["Du", "Se", "Ch", "Pa", "Ju", "Sh", "Ya"];
/* montaj ishchisi kesish sabablari (docs/montaj.md) → o'zbekcha */
const ST_CUT = {silence: "Sukut", noise: "Shovqin/pauza", filler: "«Ee/hmm»", retake: "Qayta olingan", retake_cue: "«Qaytadan» buyrug'i", tiny: "Qisqa bo'lak"};
const stChip = (t, cls = "") => `<span class="st-chip ${cls}">${esc(t)}</span>`;
const stD = s => { s = String(s || ""); return s.length >= 10 ? `${s.slice(8, 10)}.${s.slice(5, 7)}.${s.slice(0, 4)}` : "—"; };
const stDT = s => { s = String(s || ""); return s.length >= 16 ? `${stD(s)} ${s.slice(11, 16)}` : stD(s); };
const stHM = s => String(s || "").slice(11, 16);
const stSize = b => b >= 1073741824 ? `${(b / 1073741824).toFixed(2).replace(".", ",")} GB` : b >= 1048576 ? `${(b / 1048576).toFixed(1).replace(".", ",")} MB` : `${Math.max(1, Math.round((b || 0) / 1024))} KB`;
const stSec = s => { s = Math.max(0, Math.round(+s || 0)); const h = Math.floor(s / 3600), m = Math.floor(s / 60) % 60, x = s % 60; return h ? `${h}:${String(m).padStart(2, "0")}:${String(x).padStart(2, "0")}` : `${m}:${String(x).padStart(2, "0")}`; };
const stErr = d => { const det = d && d.detail; return (d && d.message) || (typeof det === "string" ? det : Array.isArray(det) ? "Maydonlarni tekshiring" : det?.message) || "Xatolik yuz berdi"; };
const stIso = d => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
const stAddDays = (iso, n) => { const d = new Date(iso + "T12:00:00"); d.setDate(d.getDate() + n); return stIso(d); };
const stWeek = iso => ST_DAYS[(new Date(iso + "T12:00:00").getDay() + 6) % 7];

const ST_MON = ["yan", "fev", "mar", "apr", "may", "iyn", "iyl", "avg", "sen", "okt", "noy", "dek"];
/* o'qiladigan sana: «Bugun, 10:39» / «Kecha, 10:39» / «12 noy 2026, 10:39» */
function stNice(s) {
  s = String(s || ""); if (s.length < 10) return "—";
  const d = s.slice(0, 10), t = s.length >= 16 ? s.slice(11, 16) : "", today = (STD.meta && STD.meta.today) || stIso(new Date());
  const lab = d === today ? "Bugun" : d === stAddDays(today, -1) ? "Kecha" : `${+d.slice(8, 10)} ${ST_MON[+d.slice(5, 7) - 1] || ""} ${d.slice(0, 4)}`;
  return t ? `${lab}, ${t}` : lab;
}
/* jurnal matnidagi ichki ko'rinish: ISO sana → o'qiladigan; «x.pptx · pptx» — kengaytma ikki marta yozilmasin */
const stNote = n => String(n || "").replace(/(\d{4})-(\d{2})-(\d{2})(?: (\d{2}:\d{2}))?/g, (m, y, mo, d, t) => stNice(`${y}-${mo}-${d}${t ? " " + t : ""}`))
  .replace(/(\.([A-Za-z0-9]{2,5}))\s·\s\2(?=\s|·|$)/gi, "$1");
/* taqdimot sarlavhasi yo'q bo'lsa «matn» (ichki joy tutuvchi) emas — «Sarlavhasiz» */
const stPT = t => { t = String(t || "").trim(); return !t || /^(matn|text|untitled)$/i.test(t) ? "Sarlavhasiz" : t; };
const stTech = () => ["masofaviy", "it_head"].includes((STD.meta || {}).role);     /* texnik matn (token, server sozlamasi) — faqat bo'lim boshlig'i va IT'ga */
const WORKER_OFF_TECH = `Montaj ishchisi ulanmagan (serverda <b>ISFT_CORE_WORKER_TOKEN</b> sozlanmagan) — vazifalar navbatda kutadi.`;
const WORKER_OFF_USER = `Montaj hozircha ishlamayapti — IT xodimlari bilan bog'laning. Yuklangan videolar navbatda kutadi.`;

/* ---------- API ---------- */
async function stApi(url, body, method) {
  const r = await fetch(url, {method: method || (body === undefined ? "GET" : "POST"), credentials: "same-origin",
                              headers: body === undefined ? {} : {"Content-Type": "application/json"}, body: body === undefined ? undefined : JSON.stringify(body)});
  if (r.status === 401) { showLogin(); throw new Error("auth"); }
  const d = await r.json().catch(() => ({}));
  if (!r.ok) {
    const m = stErr(d);
    stApi.last = {status: r.status, msg: m};
    if (body !== undefined) { stMsg(m); return null; }
    const e = new Error(r.status === 403 ? "denied" : "api"); e.msg = m; e.status = r.status; throw e;
  }
  stApi.last = null;
  return d;
}
/* xabar: ochiq oyna bo'lsa — oyna ICHIDAGI role="alert" blokida (toast oyna orqasida qolardi), bo'lmasa toast */
function stMsg(m) {
  stPrune();
  const L = ST_LAYERS[ST_LAYERS.length - 1];
  if (L && L.err) L.err(m); else toast(m);
}

/* ---------- qatlamlar (oyna, to'liq ekranli o'qish): fokus tuzog'i, Esc, fon inert, fokus qaytishi ---------- */
const ST_LAYERS = [];
let ST_N = 0, ST_PEND = null, ST_MO = null;
const stAttrSel = (n, v) => `[${n}="${String(v).replace(/["\\]/g, "\\$&")}"]`;
function stSig(el) {
  if (!el || el === document.body || !el.attributes) return "";
  if (el.id) return "#" + CSS.escape(el.id);
  for (const a of el.attributes) if (a.name.startsWith("data-") && !["data-x", "data-st-busy", "data-armed"].includes(a.name)) return stAttrSel(a.name, a.value);
  return "";
}
const stVisible = e => !!(e.offsetWidth || e.offsetHeight || e.getClientRects().length);
const stFocusables = root => [...root.querySelectorAll('a[href],button,input:not([type=hidden]),select,textarea,summary,video[controls],[tabindex]')]
  .filter(e => !e.disabled && e.tabIndex >= 0 && !e.closest("[hidden]") && stVisible(e));
function stRestore(root, sig, fb) {
  const t = (sig && root.querySelector(sig)) || (fb && root.querySelector(fb));
  if (t) { t.focus({preventScroll: true}); return true; }
  return false;
}
/* qayta chizishdan oldin fokus qayerda edi (box ichida) — chizilgach shu yerga qaytariladi */
const stKeep = box => ({sig: box && document.activeElement && document.activeElement !== box && box.contains(document.activeElement) ? stSig(document.activeElement) : ""});
function stBack(box, keep, fb) {
  const pend = ST_PEND && Date.now() - ST_PEND.t < 6000 ? ST_PEND : null;
  ST_PEND = null;
  const sig = (keep && keep.sig) || (pend && pend.sig);
  if (!sig && !pend) return;
  if (!stRestore(box, sig, fb) && (pend || keep.sig)) stRestore(document, "#v-studio .st-head h2");
}
function stPrune() { [...ST_LAYERS].forEach(L => { if (!L.el.isConnected) L.close(true); }); }
function stLayer(el, o = {}) {
  stPrune();
  let op = document.activeElement;
  if ((!op || op === document.body) && stBusy.opener && stBusy.opener.isConnected) op = stBusy.opener;
  const L = {el, busy: false, onKey: o.onKey, err: o.err, opener: op, sig: stSig(op), inerted: [], closed: false};
  [...document.body.children].forEach(n => { if (n === el || n.id === "toast" || /^(SCRIPT|STYLE|LINK|TEMPLATE)$/.test(n.tagName) || n.inert) return; n.inert = true; L.inerted.push(n); });
  document.body.appendChild(el);
  L.request = () => { if (!L.busy) L.close(); };
  L.close = silent => {
    if (L.closed) return; L.closed = true;
    const i = ST_LAYERS.indexOf(L); if (i >= 0) ST_LAYERS.splice(i, 1);
    L.inerted.forEach(n => { if (n.isConnected) n.inert = false; });
    el.remove();
    if (!silent && L.opener && L.opener.isConnected && !L.opener.closest("[inert]") && stVisible(L.opener)) L.opener.focus({preventScroll: true});
    else if (L.sig) { ST_PEND = {sig: L.sig, t: Date.now()}; if (!silent) { const r = document.querySelector("#v-studio"); r && stRestore(r, L.sig); } }
    try { o.onClose && o.onClose(); } catch (e) { console.error(e); }
  };
  ST_LAYERS.push(L);
  if (!ST_MO) { ST_MO = new MutationObserver(stPrune); ST_MO.observe(document.body, {childList: true}); }
  return L;
}
document.addEventListener("keydown", e => {
  stPrune();
  const L = ST_LAYERS[ST_LAYERS.length - 1]; if (!L) return;
  if (e.key === "Escape") { e.preventDefault(); e.stopPropagation(); L.request(); return; }
  if (e.key === "Tab") {
    const f = stFocusables(L.el), dlg = L.el.querySelector('[role="dialog"]') || L.el, a = document.activeElement;
    if (!f.length) { e.preventDefault(); dlg.focus({preventScroll: true}); return; }
    const first = f[0], last = f[f.length - 1], inside = L.el.contains(a);
    if (e.shiftKey && (!inside || a === first || a === dlg)) { e.preventDefault(); last.focus(); }
    else if (!e.shiftKey && (!inside || a === last)) { e.preventDefault(); first.focus(); }
    return;
  }
  if (L.onKey) L.onKey(e);
}, true);

/* tugma: so'rov ketayotganda disabled + aria-busy (+ aylanuvchi ko'rsatkich); ikkinchi bosish e'tiborsiz — takroriy oyna ochilmaydi */
async function stBusy(btn, fn) {
  if (btn) {
    if (btn.dataset.stBusy) return;
    btn.dataset.stBusy = "1"; btn.setAttribute("aria-busy", "true"); btn.classList.add("st-loading"); btn.disabled = true; stBusy.opener = btn;
  }
  try { return await fn(); }
  catch (e) { if (e && e.message !== "auth") toast((e && e.msg) || "Ma'lumotni yuklab bo'lmadi"); }
  finally {
    stBusy.opener = null;
    if (btn && btn.isConnected) { delete btn.dataset.stBusy; btn.removeAttribute("aria-busy"); btn.classList.remove("st-loading"); btn.disabled = false; }
  }
}
const ST_ONCE = new Set();
async function stOnce(key, fn) { if (ST_ONCE.has(key)) return; ST_ONCE.add(key); try { return await fn(); } finally { ST_ONCE.delete(key); } }

/* opts: {foot — pastki panel HTML, cancelText, sub — sarlavha ostidagi HTML, onClose}. Tugmalar paneli doim pastda (sticky). */
function stModal(title, html, onOk, okText = "Saqlash", wide = false, opts = {}) {
  const id = "stm" + (++ST_N);
  const bg = document.createElement("div"); bg.className = "st-modal-bg";
  const foot = opts.foot != null ? opts.foot : onOk ? `<button type="button" class="btn ghost" data-x>${esc(opts.cancelText || "Bekor qilish")}</button><button type="button" class="btn primary" data-ok>${esc(okText)}</button>` : `<button type="button" class="btn ghost" data-x>Yopish</button>`;
  bg.innerHTML = `<div class="st-modal ${wide ? "wide" : ""}" role="dialog" aria-modal="true" aria-labelledby="${id}" tabindex="-1"><div class="st-modal-h"><h3 id="${id}">${esc(title)}</h3>
    <button type="button" class="st-x" data-x aria-label="Yopish">×</button></div>${opts.sub ? `<div class="st-modal-sub">${opts.sub}</div>` : ""}<div class="st-modal-b">${html}</div>
    <div class="st-err" role="alert" aria-atomic="true"></div><div class="st-foot st-acts end">${foot}</div></div>`;
  const dlg = bg.firstElementChild, errEl = bg.querySelector(".st-err");
  const L = stLayer(bg, {onClose: opts.onClose, err: m => { errEl.textContent = m || ""; if (m) errEl.scrollIntoView({block: "nearest"}); }});
  bg.err = L.err; bg.close = () => L.close(); bg.layer = L;
  let down = false;                                           /* fon bosilsa yopiladi — faqat mousedown ham, mouseup ham fonda bo'lsa (matn belgilash yopib yubormasin) */
  bg.addEventListener("mousedown", e => { down = e.target === bg; });
  bg.addEventListener("mouseup", e => { if (down && e.target === bg) L.request(); down = false; });
  bg.addEventListener("click", e => { if (e.target.closest("[data-x]")) L.request(); });
  const ok = bg.querySelector("[data-ok]");
  if (ok) ok.onclick = async () => {
    if (L.busy) return;
    L.busy = true; L.err(""); ok.disabled = true; ok.setAttribute("aria-busy", "true");
    try { if (await onOk(bg)) L.close(); }
    catch (e) { if (e && e.message !== "auth") L.err((e && e.msg) || "Xatolik yuz berdi — qayta urinib ko'ring"); }
    finally { L.busy = false; if (ok.isConnected) { ok.disabled = false; ok.removeAttribute("aria-busy"); } }
  };
  const f0 = bg.querySelector(".st-modal-b textarea, .st-modal-b input:not([type=hidden]), .st-modal-b select");
  (f0 && stVisible(f0) ? f0 : dlg).focus({preventScroll: true});
  return bg;
}
const stStageChip = s => stChip(s.label, s.over ? "bad" : s.stage === "nextid" ? "ok" : s.studio ? "info" : "");

/* ---------- asosiy ---------- */
async function renderStudio(tab) {
  const v = $("#v-studio");
  const who = typeof ME !== "undefined" ? ME : null;
  if (STD.who !== who) { stReset(); STD.who = who; }
  if (!STD.meta) { const m = await stApi("/api/studio/meta"); if (STD.who !== who) return; STD.meta = m; }
  const M = STD.meta;
  STD.tab = tab && M.tabs.includes(tab) ? tab : (STD.tab && M.tabs.includes(STD.tab) ? STD.tab : M.tabs[0]);
  if (!STD.day) STD.day = M.today;
  const sub = {montaj_operator: "Syomka kun rejasi, xom video va AI montaj natijasini ko'rib chiqish", oqituvchi: "Darslaringiz qaysi bosqichda va studiyada syomkaga yozilish",
               rektor: "Dars ishlab chiqarish: bosqichlar va muddati o'tgan darslar (jamlangan)", prorektor_oquv: "Dars ishlab chiqarish: bosqichlar va muddati o'tgan darslar (jamlangan)",
               it_head: "YouTube kanaliga ulanish (OAuth) va montaj ishchisi holati"}[M.role] || "Ma'ruza → syomka → AI montaj → YouTube → paket → NEXTID: bitta oqim";
  const tabFocus = !!(document.activeElement && document.activeElement.closest && document.activeElement.closest(".st-tabs"));
  v.innerHTML = `<div class="st-head"><div><h2 tabindex="-1">Studiya</h2><span class="muted">${esc(sub)}</span></div></div>
    ${M.caps.ops && !M.worker_on ? `<div class="st-warnbox">${ico("alert", 15)}<span>${stTech() ? WORKER_OFF_TECH : WORKER_OFF_USER}</span></div>` : ""}
    ${M.tabs.length > 1 ? `<div class="st-tabs" role="tablist" aria-label="Studiya bo'limlari">${M.tabs.map(t => `<button type="button" role="tab" aria-selected="${t === STD.tab}" tabindex="${t === STD.tab ? 0 : -1}" class="${t === STD.tab ? "on" : ""}" data-t="${t}">${esc(M.tab_labels[t])}</button>`).join("")}</div>` : ""}
    <div id="stBox"><div class="st-empty">Yuklanmoqda…</div></div>`;
  const tabs = v.querySelectorAll(".st-tabs [data-t]");
  tabs.forEach(b => {
    b.onclick = () => renderStudio(b.dataset.t);
    b.onkeydown = e => {
      const i = [...tabs].indexOf(b), n = e.key === "ArrowRight" ? i + 1 : e.key === "ArrowLeft" ? i - 1 : e.key === "Home" ? 0 : e.key === "End" ? tabs.length - 1 : -1;
      if (n >= 0) { e.preventDefault(); const t = tabs[(n + tabs.length) % tabs.length]; t.focus(); renderStudio(t.dataset.t); }
    };
  });
  const onTab = v.querySelector(".st-tabs .on");
  if (onTab) { if (tabFocus) onTab.focus({preventScroll: true}); try { onTab.scrollIntoView({inline: "nearest", block: "nearest"}); } catch (e) {} }
  const box = $("#stBox");
  try {
    await ({holat: stHolat, kun: stKun, montaj: stMontaj, darslar: M.role === "oqituvchi" ? stMine : stDarslar, sozlama: stSozlama})[STD.tab](box);
  } catch (e) {
    if (e?.message === "auth") return;
    box.innerHTML = e?.message === "denied" ? locked("Bu bo'lim") : `<div class="card st-card"><p>${esc(e?.msg || "Ma'lumotni yuklab bo'lmadi")}</p></div>`;
  }
}
const stRe = () => renderStudio(STD.tab);

/* ---------- Holat (board) ---------- */
async function stHolat(box) {
  const d = await stApi(`/api/studio/board?group=${STD.group}`);
  const keep = stKeep(box);
  const inProc = d.total - d.done;
  const stages = d.stages, mx = Math.max(1, ...stages.map(s => d.totals[s.key]));
  const seg = r => `<div class="st-stack" role="img" aria-label="${esc(stages.filter(s => r.counts[s.key]).map(s => `${s.label}: ${r.counts[s.key]}`).join(", "))}">${stages.map((s, i) => r.counts[s.key] ? `<i class="st-c${i}" style="flex:${r.counts[s.key]}" title="${esc(s.label)}: ${r.counts[s.key]}"></i>` : "").join("")}</div>`;
  box.innerHTML = `<div class="st-kpis">
      <div class="st-kpi"><span>Jarayonda</span><b>${fmt(inProc)}</b><small>ta dars · jami kuzatilayotgan: ${fmt(d.total)}</small></div>
      <div class="st-kpi ${d.red_total ? "bad" : "ok"}"><span>Muddati o'tgan</span><b>${fmt(d.red_total)}</b><small>bosqich muddati (SLA) o'tgan</small></div>
      <div class="st-kpi ok"><span>NEXTID'ga yuklandi</span><b>${fmt(d.done)}</b><small>tugallangan darslar</small></div></div>
    <div class="card st-card"><div class="st-item-h"><h3>Bosqichlar</h3><span class="muted tiny">«Egasi» — kim harakat qilishi kerak</span></div>
      <div class="st-stages">${stages.map((s, i) => `<div class="st-stage"><i class="st-dot st-c${i}"></i><span class="st-sl">${esc(s.label)}<small>Egasi: ${esc(s.owner || "—")}</small></span><b>${fmt(d.totals[s.key])}</b>
        <span class="st-sbar"><i class="st-c${i}" style="width:${100 * d.totals[s.key] / mx}%"></i></span></div>`).join("")}</div></div>
    <div class="card st-card"><div class="st-item-h"><h3>Kesimda</h3>
      <div class="st-seg" role="group" aria-label="Guruhlash">${[["course", "Kurs"], ["kafedra", "Kafedra"], ["teacher", "O'qituvchi"]].map(([k, l]) => `<button type="button" class="${STD.group === k ? "on" : ""}" aria-pressed="${STD.group === k}" data-g="${k}">${l}</button>`).join("")}</div></div>
      ${d.rows.length ? `<div class="st-rows">${d.rows.map(r => `<div class="st-row"><div class="st-row-t"><b>${esc(r.name)}</b><span class="muted tiny">${fmt(r.total)} dars${r.red ? ` · <span class="st-bad">${r.red} ta muddati o'tgan</span>` : ""}</span></div>${seg(r)}</div>`).join("")}</div>`
        : `<div class="st-empty">Ishlab chiqarish rejasida kurs yo'q${STD.meta.caps.plan ? " — «Darslar» bo'limida kurs qo'shing" : ""}</div>`}</div>
    <div class="card st-card"><div class="st-item-h"><h3>Muddati o'tgan darslar <span class="st-chip ${d.red_total ? "bad" : "ok"}">${fmt(d.red_total)}</span></h3></div>
      ${d.red.length ? `<div class="st-list">${d.red.map(x => `<div class="st-li"><div class="st-li-m"><b>${esc(x.code)} · ${esc(x.title)}</b>
          <span class="muted tiny">${esc(x.subject)} · ${esc(x.teacher || "—")}</span><span class="tiny">${esc(x.next)}</span></div>
          <div class="st-li-s">${stChip(x.label, "bad")}<span class="tiny">${esc(x.owner_label)} · ${x.days_over} kun kechikdi</span></div></div>`).join("")}</div>`
        : `<div class="st-empty">Muddati o'tgan dars yo'q</div>`}
      ${d.aggregate ? `<p class="st-note ic">${ico("shield", 14)}<span>Rahbariyat uchun — faqat jamlangan raqamlar va belgilar; video va fayllar bo'lim va operatorda.</span></p>` : ""}</div>`;
  box.querySelectorAll("[data-g]").forEach(b => b.onclick = () => { STD.group = b.dataset.g; stHolat(box); });
  stBack(box, keep);
}

/* ---------- Kun rejasi ---------- */
async function stKun(box) {
  const M = STD.meta;
  const [d, jw] = await Promise.all([stApi(`/api/studio/day?date=${STD.day}`), stApi("/api/studio/jobs?status=faol").catch(e => { if (e && e.message === "auth") throw e; return null; })]);
  const wait = new Set(((jw && jw.dept_wait) || []).map(x => `${x.course_id}:${x.lkey}`));            /* tasdiqlangan, lekin bo'limga yuborilmagan darslar */
  const keep = stKeep(box);
  const nav = `<div class="st-daynav"><button type="button" class="btn sm ghost" data-dd="-1" aria-label="Oldingi kun" title="Oldingi kun">${ico("chevl", 16)}</button>
      <label class="st-date"><span class="st-sr">Sana</span><input type="date" id="stDay" value="${esc(d.date)}"></label>
      <button type="button" class="btn sm ghost" data-dd="1" aria-label="Keyingi kun" title="Keyingi kun">${ico("chevr", 16)}</button>
      ${d.date !== M.today ? `<button type="button" class="btn sm ghost" data-dd="0">Bugun</button>` : ""}<span class="muted tiny" id="stDayLbl" aria-live="polite">${stWeek(d.date)}, ${stD(d.date)}</span></div>`;
  const deptTag = (b, j) => {
    if (!j || j.status !== "tasdiqlandi") return "";
    const sent = j.dept_sent != null ? !!j.dept_sent : b.video_wait ? false : b.dept_sent != null ? !!b.dept_sent : jw ? !wait.has(`${b.course_id}:${b.lkey}`) : null;
    return sent === false ? stChip("Bo'limga yuborilmagan", "warn") : sent === true ? stChip("Bo'limga yuborilgan", "ok") : "";
  };
  const slot = (rm, s) => {
    const b = s.booking;
    if (!b) return `<div class="st-slot ${s.past ? "past" : "free"}"><span class="st-time">${stHM(s.start)}–${stHM(s.end)}</span>${s.past ? `<span class="st-slot-m muted"><span aria-hidden="true">—</span><span class="st-sr">O'tib ketgan, bo'sh vaqt</span></span>` : `<span class="st-slot-m muted">Bo'sh</span>`}
      ${s.free ? `<button type="button" class="btn sm" data-book="${esc(s.start)}" data-room="${rm.id}">Band qilish</button>` : ""}</div>`;
    const j = b.job, acts = [];
    if (b.status === "band") {
      if (b.past || s.past) acts.push(`<button type="button" class="btn sm primary" data-done="${b.id}">Syomka qilindi</button>`, `<button type="button" class="btn sm ghost" data-noshow="${b.id}">Kelmadi</button>`);
      acts.push(`<button type="button" class="btn sm ghost" data-move="${b.id}">Ko'chirish</button>`, `<button type="button" class="btn sm ghost" data-cancel="${b.id}">Bekor qilish</button>`);
    }
    if (b.status === "otdi" || (b.status === "band" && (b.past || s.past))) acts.unshift(`<button type="button" class="btn sm${b.status === "otdi" && !b.has_raw ? " primary" : ""}" data-raw="${b.course_id}:${b.lkey}">${ico("upload", 14)} Xom video</button>`);
    acts.unshift(`<button type="button" class="btn sm ${b.pres ? "" : "ghost"}" data-pres="${b.course_id}:${b.lkey}" title="O'qituvchi yuborgan taqdimot — syomkada ochiladi">${ico("file", 14)} Taqdimot${b.pres ? " v" + b.pres.version : ""}</button>`);
    return `<div class="st-slot busy"><span class="st-time">${stHM(s.start)}–${stHM(s.end)}</span><div class="st-slot-m"><b>${esc(b.code)} · ${esc(b.title)}</b> <code class="st-code" title="Darsning unikal kodi">${esc(b.full_code || "")}</code>
        <span class="muted tiny">${esc(b.subject)} (${esc(b.group)}) · ${esc(b.teacher || "—")}</span>
        <span class="st-tags">${stChip(b.status_label, ST_BK_TONE[b.status])}${b.pres ? stChip(`Taqdimot v${b.pres.version}${b.pres.studio_seen ? "" : " · yangi"}`, b.pres.studio_seen ? "ok" : "warn") : stChip("Taqdimot yuborilmagan", "")}${j ? stChip(`Montaj: ${j.status_label}${j.status === "ishlanmoqda" && j.pct != null ? ` ${j.pct}%` : ""}`, ST_JOB_TONE[j.status]) : b.has_raw ? stChip("Xom video yuklangan", "info") : ""}${deptTag(b, j)}${b.reason ? `<span class="tiny muted">«${esc(b.reason)}»</span>` : ""}</span></div>
      <div class="st-acts">${acts.join("")}</div></div>`;
  };
  box.innerHTML = nav + (d.rooms.length ? d.rooms.map(rm => `<div class="card st-card"><div class="st-item-h"><h3>${esc(rm.name)}</h3><span class="muted tiny">${esc(rm.open_from)}–${esc(rm.open_to)} · ${rm.slot_min} daqiqa</span></div>
      ${rm.works ? `<div class="st-slots">${rm.slots.map(s => slot(rm, s)).join("")}</div>` : `<div class="st-empty">Bu kuni studiya ishlamaydi</div>`}</div>`).join("") : `<div class="st-empty">Faol studiya xonasi yo'q — Sozlamalarda qo'shing</div>`);
  const go2 = n => { STD.day = n === 0 ? M.today : stAddDays(STD.day, n); return stKun(box); };
  box.querySelectorAll("[data-dd]").forEach(b => b.onclick = () => go2(+b.dataset.dd));
  box.querySelector("#stDay").onchange = e => { if (e.target.value) { STD.day = e.target.value; stKun(box); } };
  const re = () => stKun(box);
  box.querySelectorAll("[data-book]").forEach(b => b.onclick = () => stBusy(b, () => stBookFor(b.dataset.book, +b.dataset.room, re)));
  box.querySelectorAll("[data-done]").forEach(b => b.onclick = () => stBusy(b, async () => { if (await stApi(`/api/studio/bookings/${b.dataset.done}/done`, {status: "otdi"})) { toast("Syomka qilindi deb belgilandi"); await re(); } }));
  box.querySelectorAll("[data-noshow]").forEach(b => b.onclick = () => stBusy(b, async () => { if (confirm("O'qituvchi kelmadi deb belgilansinmi?") && await stApi(`/api/studio/bookings/${b.dataset.noshow}/done`, {status: "kelmadi"})) { toast("Belgilandi"); await re(); } }));
  box.querySelectorAll("[data-move]").forEach(b => b.onclick = () => stMove(d.items.find(x => x.id === +b.dataset.move), re));
  box.querySelectorAll("[data-cancel]").forEach(b => b.onclick = () => stCancel(+b.dataset.cancel, re));
  box.querySelectorAll("[data-raw]").forEach(b => b.onclick = () => { const [c, l] = b.dataset.raw.split(":"); stRaw(+c, +l, re); });
  box.querySelectorAll("[data-pres]").forEach(b => b.onclick = () => { const [c, l] = b.dataset.pres.split(":"); return stBusy(b, () => stPres(+c, +l, re)); });
  stBack(box, keep, "#stDay");
}
/* O'qituvchi yuborgan taqdimot (oxirgi versiya + tarix): operator syomkada ochadi — to'liq ekranli o'qish (slayd matni, ←/→), .pptx yoki PDF.
   Ochilganda «yangi taqdimot» xabari «ko'rildi» bo'ladi. */
function stPresHtml(L, T) {
  const p = T.latest, u = (v, k) => `${T.url}/${v}/${k}`;
  if (!p) return `<p class="muted">O'qituvchi bu dars uchun hali taqdimot yubormagan.</p>`;
  const old = (T.history || []).filter(h => h.version !== p.version);
  const sl = h => h.slides ? `${h.slides} slayd` : "slayd soni noma'lum";
  return `<div class="st-pres"><p class="st-pres-i"><b>v${p.version}</b> · ${esc(stNice(p.sent_at))} · ${sl(p)} · ${esc(p.sent_by || "")}${p.note ? ` <span class="muted">«${esc(p.note)}»</span>` : ""}</p>
      <div class="st-acts st-pres-a"><button type="button" class="btn sm primary" data-read="${p.version}">${ico("play", 14)} Taqdimotni ochish (to'liq ekran)</button>
        <a class="btn sm" href="${u(p.version, "pptx")}">${ico("download", 14)} .pptx yuklab olish</a>${p.has_pdf ? `<a class="btn sm" href="${u(p.version, "pdf")}" target="_blank" rel="noopener">${ico("file", 14)} PDF</a>` : ""}</div>
      ${old.length ? `<h4>Eski versiyalar</h4><ul class="st-vers">${old.map(h => `<li><span class="st-vers-t"><b>v${h.version}</b> · ${esc(stNice(h.sent_at))} · ${sl(h)}</span>
        <span class="st-vers-a"><button type="button" class="btn sm ghost" data-read="${h.version}">O'qish</button><a class="btn sm ghost" href="${u(h.version, "pptx")}">.pptx</a>${h.has_pdf ? `<a class="btn sm ghost" href="${u(h.version, "pdf")}" target="_blank" rel="noopener">PDF</a>` : ""}</span></li>`).join("")}</ul>` : ""}</div>`;
}
function stPresBind(m, L, T) {
  m.querySelectorAll("[data-read]").forEach(b => b.onclick = () => stBusy(b, () => stRead(m, L, T, +b.dataset.read)));
}
/* slayd rasmlari (PNG, `${T.url}/<ver>/slides/NN.png`) — outline javobida `images` > 0 bo'lsa; yo'q bo'lsa (eski versiya) — avvalgi matnli ko'rinish */
async function stRead(m, L, T, ver) {
  const fail = t => { if (m && m.err) m.err(t); else toast(t); };
  let o;
  try { o = await stApi(`${T.url}/${ver}/outline`); }
  catch (e) {
    if (e && e.message === "auth") return;
    fail(!e.msg || e.status === 404 && /not found/i.test(e.msg) ? "Bu versiyaning slayd matni topilmadi — .pptx faylini yuklab oling." : e.msg);
    return;
  }
  const sl = (o && o.slides) || [];
  const imgs = Math.max(0, +(o && o.images) || 0);
  if (!sl.length && !imgs) { fail("Bu taqdimotda o'qish uchun matn topilmadi — .pptx faylini yuklab oling."); return; }
  stReader(o, ver, L, imgs ? `${T.url}/${ver}/slides/` : "");
}
/* base — slayd rasmlari manzili (bo'sh bo'lsa matn rejimi). Rasm rejimida slayd n ning sarlavhasi/izohi outline dagi `n` bo'yicha (bo'lingan «davomi» slaydlarda — oldingi sarlavha) */
function stReader(o, ver, L, base) {
  let S = o.slides;
  if (base) {
    let last = "";
    S = Array.from({length: +o.images}, (_, k) => {
      const x = o.slides.find(y => +y.n === k + 1);
      if (x) last = x.title || "";
      return {title: x ? x.title : last ? `${last} (davomi)` : "", notes: x ? x.notes : "", img: `${base}${k + 1}.png`, bullets: x ? x.bullets : []};
    });
  }
  let i = 0, notes = true;
  const el = document.createElement("div"); el.className = "st-reader";
  const head = `${stPT(o.title)} · ${L.full_code || L.code} · v${ver}`;
  el.innerHTML = `<div class="st-reader-in" role="dialog" aria-modal="true" aria-label="Taqdimotni o'qish: ${esc(head)}" tabindex="-1">
      <div class="st-rd-top"><span class="st-rd-t">${esc(head)}</span><span class="st-rd-n" id="stRdN"></span>${base ? `<button type="button" class="st-rd-x st-rd-fs" data-fs aria-pressed="false" aria-label="To'liq ekran (F)" title="To'liq ekran (F)"><svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><path d="M4 9V4h5M20 9V4h-5M4 15v5h5M20 15v5h-5"/></svg></button>` : ""}<button type="button" class="st-rd-x" data-x aria-label="Yopish (Esc)" title="Yopish (Esc)">×</button></div>
      <div class="st-rd-bar" aria-hidden="true"><i id="stRdP"></i></div>
      <div class="st-rd-body"><div class="st-rd-slide" id="stRdS" tabindex="-1" aria-live="polite"></div></div>
      <div class="st-rd-nav"><button type="button" class="btn" data-prev>${ico("chevl", 18)} Oldingi</button><button type="button" class="btn ghost" data-notes aria-pressed="true">Izoh</button><button type="button" class="btn primary" data-next>Keyingi ${ico("chevr", 18)}</button></div></div>`;
  const q = s => el.querySelector(s);
  const draw = () => {
    const s = S[i], bl = (s.bullets || []).filter(Boolean);
    if (base) {
      const lab = `${i + 1}-slayd, jami ${S.length} ta${s.title ? ": " + s.title : ""}`;
      q("#stRdS").className = "st-rd-slide st-rd-img-w";
      q("#stRdS").innerHTML = `<img class="st-rd-img" src="${esc(s.img)}" alt="${esc(lab)}" decoding="async">
        ${bl.length ? `<ul class="st-rd-sr">${bl.map(x => `<li>${esc(x)}</li>`).join("")}</ul>` : ""}
        ${s.notes ? `<aside class="st-rd-notes" ${notes ? "" : "hidden"}><b>Izoh:</b> ${esc(s.notes)}</aside>` : ""}`;
      q(".st-rd-img").onerror = ev => { ev.target.replaceWith(Object.assign(document.createElement("p"), {className: "muted", textContent: `${s.title || i + 1 + "-slayd"} — slayd rasmi yuklanmadi. .pptx faylini yuklab oling.`})); };
      if (i + 1 < S.length) { const pre = new Image(); pre.src = S[i + 1].img; }          /* keyingi slaydni oldindan yuklash */
      q("#stRdN").textContent = `${i + 1} / ${S.length}`;
      q("#stRdP").style.width = `${100 * (i + 1) / S.length}%`;
      q("[data-prev]").disabled = i === 0; q("[data-next]").disabled = i === S.length - 1;
      q("#stRdS").scrollTop = 0;
      return;
    }
    q("#stRdS").innerHTML = `<h2 class="st-rd-h">${esc(s.title || `${i + 1}-slayd`)}</h2>${bl.length ? `<ul class="st-rd-ul">${bl.map(x => `<li>${esc(x)}</li>`).join("")}</ul>` : ""}
      ${s.notes ? `<aside class="st-rd-notes" ${notes ? "" : "hidden"}><b>Izoh:</b> ${esc(s.notes)}</aside>` : ""}`;
    q("#stRdN").textContent = `${i + 1} / ${S.length}`;
    q("#stRdP").style.width = `${100 * (i + 1) / S.length}%`;
    q("[data-prev]").disabled = i === 0; q("[data-next]").disabled = i === S.length - 1;
    q("#stRdS").scrollTop = 0;
  };
  const go = n => { n = Math.max(0, Math.min(S.length - 1, n)); if (n !== i) { i = n; draw(); } };
  const L2 = stLayer(el, {onKey: e => {
    if (e.key === "ArrowRight" || e.key === "PageDown" || e.key === " " && e.target === q("#stRdS")) { e.preventDefault(); go(i + 1); }
    else if (e.key === "ArrowLeft" || e.key === "PageUp") { e.preventDefault(); go(i - 1); }
    else if (e.key === "Home") { e.preventDefault(); go(0); }
    else if (e.key === "End") { e.preventDefault(); go(S.length - 1); }
    else if ((e.key === "f" || e.key === "F") && base) { e.preventDefault(); fs(); }
  }, onClose: () => { if (document.fullscreenElement) document.exitFullscreen().catch(() => {}); }});
  const fs = () => {                                              /* to'liq ekran (Esc — chiqish) */
    if (document.fullscreenElement) { document.exitFullscreen().catch(() => {}); return; }
    (el.requestFullscreen ? el.requestFullscreen() : Promise.reject()).catch(() => toast("Brauzer to'liq ekranga ruxsat bermadi"));
  };
  if (q("[data-fs]")) q("[data-fs]").onclick = fs;
  el.addEventListener("fullscreenchange", () => { const b = q("[data-fs]"); if (b) b.setAttribute("aria-pressed", String(document.fullscreenElement === el)); });
  q("[data-prev]").onclick = () => go(i - 1); q("[data-next]").onclick = () => go(i + 1);
  q("[data-notes]").onclick = e => { notes = !notes; e.currentTarget.setAttribute("aria-pressed", String(notes)); el.querySelectorAll(".st-rd-notes").forEach(x => { x.hidden = !notes; }); };
  q("[data-x]").onclick = () => L2.request();
  let tx = null;                                                   /* telefon: chapga / o'ngga surish */
  el.addEventListener("touchstart", e => { tx = e.touches.length === 1 ? e.touches[0].clientX : null; }, {passive: true});
  el.addEventListener("touchend", e => { if (tx == null) return; const dx = e.changedTouches[0].clientX - tx; tx = null; if (Math.abs(dx) > 60) go(i + (dx < 0 ? 1 : -1)); }, {passive: true});
  draw();
  q("#stRdS").focus({preventScroll: true});
  return el;
}
async function stPres(cid, lkey, after) {
  return stOnce(`pres:${cid}:${lkey}`, async () => {
    const d = await stApi(`/api/studio/lessons/${cid}/${lkey}`).catch(e => { if (e && e.message !== "auth") toast((e && e.msg) || "Ochib bo'lmadi"); return null; });
    if (!d) return;
    const L = d.lesson, T = d.taqdimot, p = T.latest;
    const sub = `<p class="st-pres-nm">Taqdimot: <b>${p ? esc(stPT(p.title)) : "yuborilmagan"}</b> <code class="st-code" title="Darsning unikal kodi">${esc(L.full_code || "")}</code></p>
      <p class="tiny muted">${esc(L.subject)} · ${esc(L.teacher || "")} · ${esc(L.dept || "")}</p>`;
    const m = stModal(`${L.code} · ${L.title}`, stPresHtml(L, T), null, "", false, {sub, onClose: after});
    stPresBind(m, L, T);
  });
}
/* Montajdan keyin: operator masofaviy bo'limga yuboradi. Kod, kafedra, o'qituvchi, fan, dars — montaj vazifasidan AVTOMATIK (qayta tanlanmaydi), operator faqat tasdiqlaydi. */
async function stSendDept(jid, after) {
  return stOnce(`dept:${jid}`, async () => {
    const d = await stApi(`/api/studio/jobs/${jid}`).catch(e => { if (e && e.message !== "auth") toast((e && e.msg) || "Ochib bo'lmadi"); return null; });
    if (!d) return;
    if (d.dept) { toast(`Bu montaj allaqachon masofaviy bo'limga yuborilgan (${d.dept.by || "—"}, ${stNice(d.dept.ts)})`); after && after(); return; }
    const I = d.dept_info;
    if (!I) { toast("Bu montajni hozir bo'limga yuborib bo'lmaydi"); after && after(); return; }
    const pr = I.pres, rep = d.job.report || {}, raw = d.raw || {};
    let warns = [...new Set([...(d.warnings || []), ...(I.warnings || [])].filter(Boolean).map(String))];
    if (!warns.length && !pr) warns = ["Taqdimot yuborilmagan — o'qituvchi bu dars uchun taqdimot yubormagan. Bo'lim videoni taqdimotsiz qabul qiladi."];
    const dur = rep.duration_out != null ? stSec(rep.duration_out) : "";
    stModal("Masofaviy bo'limga yuborish", `<p class="st-note ic" style="margin-top:0">${ico("info", 14)}<span>Montaj tasdiqlandi. Endi bo'limga xabar yuboring — bo'lim shu video bilan dars yaratadi. Bekor qilsangiz, video «Montaj → Masofaviy bo'limga yuborilmagan» ro'yxatida qoladi.</span></p>
    ${warns.length ? `<div class="st-warnbox" role="note">${ico("alert", 15)}<span>${warns.map(esc).join("<br>")}</span></div>` : ""}
    <dl class="st-dl"><div><dt>Dars kodi</dt><dd><code class="st-code">${esc(I.full_code)}</code></dd></div><div><dt>Kafedra</dt><dd>${esc(I.dept || "—")}</dd></div><div><dt>O'qituvchi</dt><dd>${esc(I.teacher || "—")}</dd></div>
      <div><dt>Fan</dt><dd>${esc(I.subject)}</dd></div><div><dt>Dars</dt><dd>${esc(I.code)} — ${I.untitled ? "<i>mavzu nomi kiritilmagan</i>" : esc(I.title)}</dd></div>
      <div><dt>Taqdimot</dt><dd>${pr ? `v${pr.version} · ${pr.slides ? pr.slides + " slayd" : "slayd soni noma'lum"}` : "<span class='muted'>yuborilmagan</span>"}</dd></div>
      <div><dt>Video</dt><dd>${dur ? `${esc(dur)} · ` : ""}${raw.name ? esc(raw.name) : "<span class='muted'>fayl nomi yo'q</span>"}</dd></div><div><dt>Montaj</dt><dd>#${jid} · tasdiqlangan</dd></div></dl>
    <label class="st-lbl2">Izoh (ixtiyoriy)<textarea id="stDn" rows="2" maxlength="300" placeholder="masalan, 12:40 dagi kesish qaytarilgan"></textarea></label>`,
      async m => {
        const r = await stApi(`/api/studio/jobs/${jid}/send-dept`, {note: m.querySelector("#stDn").value.trim()});
        if (!r) {
          const last = stApi.last;
          if (last && last.status === 409) { toast(last.msg || "Bu montaj allaqachon masofaviy bo'limga yuborilgan"); after && after(); return true; }   /* oyna yopiladi, ro'yxat yangilanadi */
          return false;
        }
        toast(`${r.info.full_code}: masofaviy bo'limga yuborildi`); after && after(); return true;
      }, "Tasdiqlab yuborish", false, {cancelText: "Keyinroq"});
  });
}
/* operator / bo'lim: bo'sh slotga dars tanlab band qilish */
async function stBookFor(start, room, after) {
  const L = await stApi("/api/studio/lessons");
  if (!L.courses.length) { toast("Ishlab chiqarish rejasida kurs yo'q — «Darslar» bo'limida qo'shing"); return; }
  const opts = cid => L.lessons.filter(l => l.course_id === cid && !l.booking && l.stage !== "nextid").map(l => `<option value="${l.lkey}">${esc(l.code)} · ${esc(l.title)} — ${esc(l.label)}</option>`).join("");
  const m = stModal(`Syomka: ${stD(start)} soat ${stHM(start)}`, `<div class="st-form">
      <label>Kurs<select id="stBc">${L.courses.map(c => `<option value="${c.id}">${esc(c.subject)} (${esc(c.direction || "")}, ${c.course || ""}-kurs) — ${esc(c.teacher || "")}</option>`).join("")}</select></label>
      <label>Dars<select id="stBl"></select></label><label>Izoh (ixtiyoriy)<input type="text" id="stBn" maxlength="300" placeholder="Masalan: slaydlar fleshkada"></label></div>`,
    async m => {
      const r = await stApi("/api/studio/bookings", {course_id: +m.querySelector("#stBc").value, lkey: +m.querySelector("#stBl").value, room_id: room, start, note: m.querySelector("#stBn").value});
      if (!r) return false;
      toast(r.warning || "Band qilindi"); after?.(); return true;
    }, "Band qilish");
  const fill = () => { m.querySelector("#stBl").innerHTML = opts(+m.querySelector("#stBc").value) || `<option value="">Band qilinmagan dars yo'q</option>`; };
  m.querySelector("#stBc").onchange = fill; fill();
}
/* slot tanlash (o'qituvchi: o'z darsi uchun; ko'chirish) */
function stSlotPicker(title, onPick, opts = {}) {
  const M = STD.meta;
  let day = opts.day || stAddDays(M.today, 1), room = opts.room || (M.rooms[0] || {}).id || 0;
  const m = stModal(title, `<div class="st-form"><div class="st-daynav"><button type="button" class="btn sm ghost" data-pd="-1" aria-label="Oldingi kun">${ico("chevl", 16)}</button>
      <label class="st-date"><span class="st-sr">Sana</span><input type="date" id="stPd" min="${esc(M.today)}"></label><button type="button" class="btn sm ghost" data-pd="1" aria-label="Keyingi kun">${ico("chevr", 16)}</button></div>
      ${M.rooms.length > 1 ? `<label>Xona<select id="stPr">${M.rooms.map(r => `<option value="${r.id}">${esc(r.name)}</option>`).join("")}</select></label>` : ""}
      <div id="stPs" class="st-pick"></div>${opts.reason ? `<label>Sabab<input type="text" id="stPreason" maxlength="300" placeholder="Nima uchun ko'chirilmoqda"></label>` : ""}</div>`, null);
  const load = async () => {
    m.querySelector("#stPd").value = day;
    const d = await stApi(`/api/studio/day?date=${day}`).catch(() => null);
    const rm = d && (d.rooms.find(r => r.id === room) || d.rooms[0]);
    const box = m.querySelector("#stPs");
    if (!rm || !rm.works) { box.innerHTML = `<div class="st-empty">Bu kuni studiya ishlamaydi — boshqa kunni tanlang</div>`; return; }
    const free = rm.slots.filter(s => s.free);
    box.innerHTML = `<span class="muted tiny">${stWeek(day)}, ${stD(day)} · ${esc(rm.name)}</span><div class="st-pick-g">${rm.slots.map(s => `<button type="button" class="st-pslot" ${s.free ? "" : "disabled"} data-s="${esc(s.start)}">${stHM(s.start)}<small>${s.free ? "bo'sh" : s.past ? "o'tgan" : "band"}</small></button>`).join("")}</div>
      ${free.length ? "" : `<div class="st-empty">Bo'sh slot yo'q</div>`}`;
    box.querySelectorAll("[data-s]").forEach(b => b.onclick = async () => {
      const reason = m.querySelector("#stPreason")?.value || "";
      if (opts.reason && reason.trim().length < 3) { stMsg("Ko'chirish sababini yozing"); m.querySelector("#stPreason").focus(); return; }
      if (m.layer.busy) return;
      m.layer.busy = true; m.err(""); b.disabled = true; b.setAttribute("aria-busy", "true");
      try { if (await onPick(b.dataset.s, rm.id, reason)) m.close(); else if (b.isConnected) { b.disabled = false; b.removeAttribute("aria-busy"); } }
      catch (e) { if (e && e.message !== "auth") m.err("Xatolik yuz berdi — qayta urinib ko'ring"); if (b.isConnected) { b.disabled = false; b.removeAttribute("aria-busy"); } }
      finally { m.layer.busy = false; }
    });
  };
  m.querySelectorAll("[data-pd]").forEach(b => b.onclick = () => { const n = stAddDays(day, +b.dataset.pd); if (n >= M.today) { day = n; load(); } });
  m.querySelector("#stPd").onchange = e => { if (e.target.value) { day = e.target.value; load(); } };
  const rs = m.querySelector("#stPr"); if (rs) { rs.value = room; rs.onchange = () => { room = +rs.value; load(); }; }
  load();
}
function stMove(b, after) {
  if (!b) return;
  stSlotPicker(`Ko'chirish: ${b.code} · ${b.title}`, async (start, room, reason) => {
    const r = await stApi(`/api/studio/bookings/${b.id}/move`, {start, room_id: room, reason});
    if (r) { toast("Ko'chirildi"); after?.(); }
    return !!r;
  }, {day: String(b.start).slice(0, 10) >= STD.meta.today ? String(b.start).slice(0, 10) : undefined, room: b.room_id, reason: true});
}
function stCancel(id, after) {
  stModal("Syomkani bekor qilish", `<div class="st-form"><label>Sabab<textarea id="stCr" rows="3" maxlength="300" placeholder="Masalan: o'qituvchi kasal"></textarea></label></div>`, async m => {
    const reason = m.querySelector("#stCr").value.trim();
    if (reason.length < 3) { stMsg("Sababini yozing"); m.querySelector("#stCr").focus(); return false; }
    const r = await stApi(`/api/studio/bookings/${id}/cancel`, {reason});
    if (r) { toast("Bekor qilindi"); after?.(); }
    return !!r;
  }, "Bekor qilish");
}
/* xom video: oqim bilan yuklash (XHR — jarayon foizi) */
function stRaw(cid, lkey, after) {
  const M = STD.meta, T = M.templates || ST_TPL_DEF;
  const m = stModal("Xom videoni yuklash", `<div class="st-form"><label>Video fayl (.mp4, .mov, .mkv, .webm · ≤ ${String(M.limits.raw_gb).replace(".", ",")} GB)<input type="file" id="stRf" accept="video/mp4,video/quicktime,video/x-matroska,video/webm,.mp4,.mov,.mkv,.webm"></label>
      <label>Montaj shabloni<select id="stRt">${Object.entries(T).map(([k, l]) => `<option value="${k}">${esc(l)}</option>`).join("")}</select></label>
      <div class="st-prog" hidden><div class="st-bar"><i></i></div><span class="tiny muted"></span></div>
      <p class="st-note">Fayl serverga to'g'ridan-to'g'ri yoziladi; yuklangach AI montaj navbatiga tushadi. Natijani «Montaj» bo'limida ko'rib chiqasiz.</p></div>`,
    m => new Promise(res => {
      const f = m.querySelector("#stRf").files[0];
      if (!f) { stMsg("Faylni tanlang"); m.querySelector("#stRf").focus(); return res(false); }
      if (f.size > M.limits.raw_gb * 1073741824) { stMsg(`Fayl juda katta (${stSize(f.size)})`); return res(false); }
      const pg = m.querySelector(".st-prog"), bar = pg.querySelector("i"), txt = pg.querySelector("span");
      pg.hidden = false;
      const x = new XMLHttpRequest();
      x.open("POST", `/api/studio/lessons/${cid}/${lkey}/raw?name=${encodeURIComponent(f.name)}&template=${encodeURIComponent(m.querySelector("#stRt").value)}`);
      x.upload.onprogress = e => { if (e.lengthComputable) { const p = Math.round(100 * e.loaded / e.total); bar.style.width = p + "%"; txt.textContent = `${p}% · ${stSize(e.loaded)} / ${stSize(e.total)}`; } };
      x.onload = () => {
        let d = {}; try { d = JSON.parse(x.responseText); } catch (e) {}
        if (x.status === 401) { showLogin(); return res(false); }
        if (x.status >= 400) { stMsg(stErr(d)); pg.hidden = true; return res(false); }
        toast("Xom video yuklandi — montaj navbatida"); after?.(); res(true);
      };
      x.onerror = () => { stMsg("Yuklash uzildi — qayta urinib ko'ring"); pg.hidden = true; res(false); };
      x.send(f);
    }), "Yuklash");
  return m;
}

/* ---------- Montaj ---------- */
async function stMontaj(box) {
  const d = await stApi("/api/studio/jobs?status=faol");
  const keep = stKeep(box);
  const dw = d.dept_wait || [];
  /* tartib: avval operator harakati kerak bo'lgan «Ko'rib chiqish kutmoqda», keyin «Masofaviy bo'limga yuborilmagan», qolganlari */
  const grp = [["tayyor", "Ko'rib chiqish kutmoqda"], ["dept", "Masofaviy bo'limga yuborilmagan"], ["operator", "Xatolik — operator kerak"], ["ishlanmoqda", "Montaj qilinmoqda"], ["navbatda", "Navbatda"]];
  const cnt = k => k === "dept" ? dw.length : (d.counts[k] || 0);
  const card = j => `<div class="st-li"><div class="st-li-m"><b>${esc(j.code)} · ${esc(j.title)}</b><span class="muted tiny">${esc(j.subject)} · ${esc(j.teacher || "—")} · ${esc(j.template_label)}</span>
      ${j.status === "ishlanmoqda" ? `<div class="st-bar" role="img" aria-label="${j.pct || 0}%"><i style="width:${j.pct || 0}%"></i></div><span class="tiny muted">${esc(j.stage || "")} ${j.pct || 0}%${j.message ? " · " + esc(j.message) : ""}</span>` : ""}
      ${j.error && j.status !== "tayyor" ? `<span class="tiny st-bad">${esc(j.error)}</span>` : ""}${j.note ? `<span class="tiny">Izoh: «${esc(j.note)}»</span>` : ""}</div>
    <div class="st-li-s">${stChip(j.status_label, ST_JOB_TONE[j.status])}<span class="tiny muted">${j.attempts ? `${j.attempts}-urinish · ` : ""}${esc(stNice(j.result_at || j.created_at))}</span>
      <div class="st-acts tight">${j.status === "tayyor" ? `<button type="button" class="btn sm primary" data-rev="${j.id}">Ko'rib chiqish</button>` : ""}
        ${j.status === "operator" ? `<button type="button" class="btn sm" data-retry="${j.id}">Qayta urinish</button>` : ""}
        ${["navbatda", "operator"].includes(j.status) ? `<button type="button" class="btn sm ghost" data-jc="${j.id}">Bekor qilish</button>` : ""}</div></div></div>`;
  const items = d.items;
  const sec = k => {
    if (k === "dept") return dw.length ? `<div class="card st-card"><h3>Masofaviy bo'limga yuborilmagan <span class="st-chip warn">${dw.length}</span></h3><p class="muted tiny">Tasdiqlangan montajlar — bo'limga yuboring (dars kodi avtomatik).</p><div class="st-list">${dw.map(x => `<div class="st-li"><div class="st-li-m"><b>${esc(x.code)} · ${esc(x.title)}</b> <code class="st-code">${esc(x.full_code)}</code>
        <span class="muted tiny">${esc(x.subject)} · ${esc(x.teacher || "—")}</span></div><div class="st-li-s"><div class="st-acts tight"><button type="button" class="btn sm primary" data-dw="${x.job_id}">Masofaviy bo'limga yuborish</button></div></div></div>`).join("")}</div></div>` : "";
    const xs = items.filter(j => j.status === k);
    return xs.length ? `<div class="card st-card"><h3>${esc(grp.find(g => g[0] === k)[1])}</h3><div class="st-list">${xs.map(card).join("")}</div></div>` : "";
  };
  box.innerHTML = `<div class="st-kpis">${grp.map(([k, l]) => `<div class="st-kpi ${(k === "tayyor" || k === "dept") && cnt(k) ? "warn" : k === "operator" && cnt(k) ? "bad" : ""}"><span>${esc(l)}</span><b>${fmt(cnt(k))}</b></div>`).join("")}</div>
    ${grp.map(g => sec(g[0])).join("") || `<div class="card st-card"><div class="st-empty">Faol montaj vazifasi yo'q. Xom videoni «Kun rejasi» yoki «Darslar»dan yuklang.</div></div>`}`;
  box.querySelectorAll("[data-rev]").forEach(b => b.onclick = () => stBusy(b, () => stReview(+b.dataset.rev, () => stMontaj(box))));
  box.querySelectorAll("[data-dw]").forEach(b => b.onclick = () => stBusy(b, () => stSendDept(+b.dataset.dw, () => stMontaj(box))));
  box.querySelectorAll("[data-retry]").forEach(b => b.onclick = () => stBusy(b, async () => { if (await stApi(`/api/studio/jobs/${b.dataset.retry}/retry`, {})) { toast("Qayta navbatga qo'yildi"); await stMontaj(box); } }));
  box.querySelectorAll("[data-jc]").forEach(b => b.onclick = () => stBusy(b, async () => { if (confirm("Montaj vazifasi bekor qilinsinmi?") && await stApi(`/api/studio/jobs/${b.dataset.jc}/cancel`, {})) { toast("Bekor qilindi"); await stMontaj(box); } }));
  stBack(box, keep);
}
async function stReview(jid, after) {
  return stOnce(`review:${jid}`, async () => {
  const d = await stApi(`/api/studio/jobs/${jid}`).catch(e => { if (e && e.message !== "auth") toast((e && e.msg) || "Ochib bo'lmadi"); return null; });
  if (!d) return;
  const j = d.job, r = j.report || {}, L = d.lesson, T = STD.meta.templates || ST_TPL_DEF;
  const noVideo = !j.media.video, ready = j.status === "tayyor";
  const code = (d.dept_info && d.dept_info.full_code) || L.full_code || L.code;
  const noPres = !!d.dept_info && !d.dept_info.pres;
  const html = `<div class="st-rev"><div class="st-rev-v">${j.media.video ? `<video controls preload="metadata" playsinline ${j.media.thumb ? `poster="${esc(j.media.thumb)}"` : ""} src="${esc(j.media.video)}">
        ${j.media.captions ? `<track kind="subtitles" srclang="uz" label="O'zbekcha" src="${esc(j.media.captions)}" default>` : ""}</video>` : `<div class="st-empty">Video fayli topilmadi</div>`}
      <p class="tiny muted">${esc(L.subject)} · ${esc(L.code)} «${esc(L.title)}» · ${esc(L.teacher || "")} · ${esc(j.template_label)}</p>
      <div class="st-tags">${stChip(`Asl: ${stSec(r.duration_in)}`)}${stChip(`Natija: ${stSec(r.duration_out)}`, "info")}${stChip(`Kesildi: ${stSec(r.cut_total)}`)}${j.files?.captions ? stChip("Subtitr bor", "ok") : stChip("Subtitrsiz")}${noPres ? stChip("Taqdimot yuborilmagan", "warn") : ""}</div></div>
    <div class="st-rev-s">${(r.warnings || []).length ? `<div class="st-warnbox">${ico("alert", 15)}<span>${r.warnings.map(esc).join("<br>")}</span></div>` : ""}
      <h4>Bo'limlar (${(r.chapters || []).length})</h4>${(r.chapters || []).length ? `<ol class="st-ch">${r.chapters.map(c => `<li><button type="button" class="st-link" data-t="${c.start}">${stSec(c.start)}</button> ${esc(c.title)}</li>`).join("")}</ol>` : `<p class="tiny muted">Bo'limlar yo'q</p>`}
      <h4>Kesilgan joylar (${(r.cuts || []).length})</h4>${(r.cuts || []).length ? `<ul class="st-cuts">${r.cuts.slice(0, 300).map(c => `<li><span class="st-mono">${stSec(c.start)}–${stSec(c.end)}</span> <span class="muted">${esc(ST_CUT[c.reason] || c.reason || "")}</span></li>`).join("")}</ul>` : `<p class="tiny muted">Kesish yo'q</p>`}
      <p class="st-note">Vaqtlar asl yozuv bo'yicha (kesishlar) va natija bo'yicha (bo'limlar).${d.yt_on ? " Tasdiqlansa video darsga qo'yiladi va YouTube'ga (havola orqali) yuklanadi." : " Tasdiqlansa video darsga fayl sifatida qo'yiladi (YouTube ulanmagan)."}${ready && !noVideo ? " Keyingi qadam — masofaviy bo'limga yuborish." : ""}</p>
      ${ready ? `<div class="st-form st-redo"><label>Qayta montaj uchun izoh<textarea id="stRn" rows="2" maxlength="500" placeholder="Masalan: 12:40 dagi kesishni qaytaring, kirish qisqaroq"></textarea></label>
        <label>Shablon<select id="stRt2">${Object.entries(T).map(([k, l]) => `<option value="${k}" ${k === j.template ? "selected" : ""}>${esc(l)}</option>`).join("")}</select></label></div>` : `<p>${stChip(j.status_label, ST_JOB_TONE[j.status])}</p>`}</div></div>`;
  /* tasdiqlash va qayta montaj — uzun skrolldan keyin emas, pastki (sticky) panelda */
  const foot = ready ? `${noVideo ? `<p class="st-why" id="stWhy">Video fayli topilmadi — tasdiqlab bo'lmaydi. «Qayta montaj»ni tanlang.</p>` : ""}<button type="button" class="btn ghost" data-x>Yopish</button><button type="button" class="btn" id="stRedo">Qayta montaj</button>
    <button type="button" class="btn primary" id="stOk" ${noVideo ? `disabled aria-describedby="stWhy"` : ""}>Tasdiqlash</button>` : null;
  const m = stModal(`Montaj natijasi #${j.id} · ${code}`, html, null, "", true, foot ? {foot} : {});
  const vid = m.querySelector("video");
  m.querySelectorAll("[data-t]").forEach(b => b.onclick = () => { if (vid) { vid.currentTime = +b.dataset.t; vid.play?.().catch(() => {}); } });
  const ok = m.querySelector("#stOk"), redo = m.querySelector("#stRedo");
  if (ok && !noVideo) ok.onclick = async () => {
    if (m.layer.busy) return;
    m.layer.busy = true; m.err(""); ok.disabled = true; ok.setAttribute("aria-busy", "true"); if (redo) redo.disabled = true;
    let r2 = null;
    try { r2 = await stApi(`/api/studio/jobs/${j.id}/approve`, {}); }
    finally { m.layer.busy = false; if (!r2 && ok.isConnected) { ok.disabled = false; ok.removeAttribute("aria-busy"); if (redo) redo.disabled = false; } }
    if (!r2) return;
    toast(r2.youtube ? "Tasdiqlandi — YouTube'ga yuklash navbatida" : r2.package && r2.package.ok ? "Tasdiqlandi — dars paketi tayyorlandi" : "Tasdiqlandi — video darsga qo'yildi");
    m.close(); after?.();
    stSendDept(j.id, after);                                  /* keyingi qadam: masofaviy bo'limga yuborish (ma'lumotlar avtomatik, operator faqat tasdiqlaydi) */
  };
  if (redo) redo.onclick = async () => {
    if (m.layer.busy) return;
    const note = m.querySelector("#stRn").value.trim();
    if (note.length < 3) { m.err("Qayta montaj sababini yozing"); m.querySelector("#stRn").focus(); return; }
    m.layer.busy = true; m.err(""); redo.disabled = true; redo.setAttribute("aria-busy", "true"); if (ok) ok.disabled = true;
    let r2 = null;
    try { r2 = await stApi(`/api/studio/jobs/${j.id}/redo`, {note, template: m.querySelector("#stRt2").value}); }
    finally { m.layer.busy = false; if (!r2 && redo.isConnected) { redo.disabled = false; redo.removeAttribute("aria-busy"); if (ok && !noVideo) ok.disabled = false; } }
    if (!r2) return;
    toast("Qayta montajga yuborildi"); m.close(); after?.();
  };
  });
}

/* ---------- Darslar (bo'lim, operator) ---------- */
async function stDarslar(box) {
  const M = STD.meta;
  const all = await stApi("/api/studio/lessons");
  if (STD.cid && !all.courses.some(c => c.id === STD.cid)) STD.cid = 0;
  if (!STD.cid && all.courses.length) STD.cid = all.courses[0].id;
  const L = all.lessons.filter(l => l.course_id === STD.cid);
  const keep = stKeep(box);
  box.innerHTML = `<div class="card st-card"><div class="st-pickrow">${all.courses.length ? `<label class="st-grow"><span class="st-lbl">Kurs (ishlab chiqarish rejasida)</span><select id="stCs">${all.courses.map(c => `<option value="${c.id}" ${c.id === STD.cid ? "selected" : ""}>${esc(c.subject)} (${esc(c.direction || "")}, ${c.course || ""}-kurs) — ${esc(c.teacher || "")}</option>`).join("")}</select></label>` : `<span class="muted">Rejada kurs yo'q</span>`}
      ${M.caps.plan ? `<button type="button" class="btn sm" id="stAddC">Kurs qo'shish</button>${STD.cid && all.courses.find(c => c.id === STD.cid)?.planned ? `<button type="button" class="btn sm ghost" id="stRmC">Rejadan olish</button>` : ""}` : ""}</div></div>
    <div class="card st-card">${L.length ? `<div class="st-list">${L.map(l => `<div class="st-li"><div class="st-li-m"><b>${esc(l.code)} · ${esc(l.title)}</b> <code class="st-code" title="Darsning unikal kodi">${esc(l.full_code || "")}</code>
        <span class="st-tags">${l.pres_version ? stChip(`Taqdimot v${l.pres_version}`, "ok") : ""}${l.dept_sent ? `<span class="st-chip ok" title="Video masofaviy bo'limga yuborilgan">Bo'limga yuborilgan</span>` : l.video_wait ? `<span class="st-chip warn" title="Montaj tasdiqlangan, lekin masofaviy bo'limga hali yuborilmagan">Bo'limga yuborilmagan</span>` : ""}</span><span class="tiny">${esc(l.next)}</span><span class="tiny muted">Egasi: ${esc(l.owner_label)}${l.due && l.stage !== "nextid" ? ` · muddat ${stD(l.due)}` : ""}${l.booking ? ` · syomka ${stDT(l.booking.start)}` : ""}</span></div>
      <div class="st-li-s">${stStageChip(l)}${l.over ? `<span class="tiny st-bad">${l.days_over} kun kechikdi</span>` : ""}
        <div class="st-acts tight"><button type="button" class="btn sm ghost" data-ld="${l.lkey}">Tafsilot</button>
          ${!l.booking && l.stage !== "nextid" ? `<button type="button" class="btn sm ghost" data-lb="${l.lkey}">Band qilish</button>` : ""}
          <button type="button" class="btn sm ghost" data-lr="${l.lkey}">${ico("upload", 14)} Xom video</button></div></div></div>`).join("")}</div>`
      : `<div class="st-empty">${all.courses.length ? "Darslar yo'q" : "Kurs tanlang yoki rejaga qo'shing"}</div>`}</div>`;
  const cs = box.querySelector("#stCs"); if (cs) cs.onchange = () => { STD.cid = +cs.value; stDarslar(box); };
  box.querySelector("#stAddC")?.addEventListener("click", () => stAddCourse(() => stDarslar(box)));
  box.querySelector("#stRmC")?.addEventListener("click", async () => { if (confirm("Kurs ishlab chiqarish rejasidan olinsinmi? (studiya yozuvlari saqlanadi)") && await stApi("/api/studio/plan", {course_id: STD.cid, on: false})) { STD.cid = 0; stDarslar(box); } });
  const les = k => L.find(l => l.lkey === k);
  box.querySelectorAll("[data-ld]").forEach(b => b.onclick = () => stBusy(b, () => stLesson(STD.cid, +b.dataset.ld, () => stDarslar(box))));
  box.querySelectorAll("[data-lb]").forEach(b => b.onclick = () => { const l = les(+b.dataset.lb); stSlotPicker(`Syomka: ${l.code} · ${l.title}`, async (start, room) => {
    const r = await stApi("/api/studio/bookings", {course_id: l.course_id, lkey: l.lkey, room_id: room, start}); if (r) { toast(r.warning || "Band qilindi"); stDarslar(box); } return !!r; }); });
  box.querySelectorAll("[data-lr]").forEach(b => b.onclick = () => stRaw(STD.cid, +b.dataset.lr, () => stDarslar(box)));
  stBack(box, keep);
}
function stAddCourse(after) {
  const m = stModal("Ishlab chiqarish rejasiga kurs qo'shish", `<div class="st-form"><label>Qidirish<input type="search" id="stCq" placeholder="Fan, yo'nalish yoki o'qituvchi" autocomplete="off"></label><div id="stCl" class="st-list"></div></div>`, null);
  let t = null;
  const load = async () => {
    const d = await stApi(`/api/studio/courses?q=${encodeURIComponent(m.querySelector("#stCq").value)}`).catch(() => ({items: []}));
    const el = m.querySelector("#stCl");
    el.innerHTML = d.items.length ? d.items.map(c => `<div class="st-li"><div class="st-li-m"><b>${esc(c.subject)}</b><span class="muted tiny">${esc(c.direction || "")}, ${c.course || ""}-kurs · ${esc(c.teacher || "—")}</span></div>
      <div class="st-li-s">${c.planned ? stChip("Rejada", "ok") : `<button type="button" class="btn sm" data-c="${c.id}">Qo'shish</button>`}</div></div>`).join("") : `<div class="st-empty">Topilmadi</div>`;
    el.querySelectorAll("[data-c]").forEach(b => b.onclick = async () => { if (await stApi("/api/studio/plan", {course_id: +b.dataset.c, on: true})) { STD.cid = +b.dataset.c; toast("Rejaga qo'shildi"); m.close(); after?.(); } });
  };
  m.querySelector("#stCq").oninput = () => { clearTimeout(t); t = setTimeout(load, 250); };
  load();
}
/* tarix: bir hodisaga bitta qator (taqdimot yuborish — v2 bilan bog'liq ichki yozuvlar guruhlanadi), texnik qatorlar «Batafsil» ostida */
function stHistHtml(hist) {
  const cap = t => { t = String(t || ""); return t.charAt(0).toUpperCase() + t.slice(1); };
  const verOf = h => { const m = /^taqdimot/i.test(h.action || "") && String(h.note || "").match(/(?:^|[\s_·—-])v(\d+)(?=[\s._·]|$)/i); return m ? m[1] : null; };
  const sentVers = new Set(hist.filter(h => /yuborildi/i.test(h.action || "") && verOf(h)).map(verOf));
  const rows = [], groups = new Map();
  for (const h of hist) {
    const v = verOf(h);
    if (v && sentVers.has(v)) {
      let g = groups.get(v);
      if (!g) { g = {v, items: [], ts: h.ts}; groups.set(v, g); rows.push(g); }
      g.items.push(h);
    } else rows.push({one: h});
  }
  const raw = h => `<li><span class="tiny muted">${esc(stNice(h.ts))} · ${esc(h.user_name || "")}</span> <span class="tiny">${esc(cap(h.action))}${h.note ? ` — ${esc(stNote(h.note))}` : ""}</span></li>`;
  const li = r => {
    if (r.one) { const h = r.one; return `<li><span class="tiny muted">${esc(stNice(h.ts))} · ${esc(h.user_name || "")}</span><span>${esc(cap(h.action))}${h.note ? ` — <span class="muted">${esc(stNote(h.note))}</span>` : ""}</span></li>`; }
    const sent = r.items.find(h => /^taqdimot yuborildi/i.test(h.action || "")) || r.items.find(h => /yuborildi/i.test(h.action || "")) || r.items[0];
    const sl = r.items.map(h => String(h.note || "").match(/(\d+)\s*slayd/)).find(Boolean);
    return `<li class="st-hist-g"><span class="tiny muted">${esc(stNice(r.ts))} · ${esc(sent.user_name || "")}</span><span><b>Taqdimot yuborildi</b> · v${r.v}${sl ? ` · ${sl[1]} slayd` : ""}</span>
      ${r.items.length > 1 ? `<details class="st-det st-hist-d"><summary>Batafsil (${r.items.length} ta yozuv)</summary><ul class="st-hist-in">${r.items.map(raw).join("")}</ul></details>` : ""}</li>`;
  };
  return `<h4>Tarix</h4>${hist.length ? `<ul class="st-hist">${rows.map(li).join("")}</ul>` : `<p class="tiny muted">Hali yozuv yo'q</p>`}`;
}
const stLesson = (cid, lkey, after) => stOnce(`lesson:${cid}:${lkey}`, () => stLessonOpen(cid, lkey, after));
async function stLessonOpen(cid, lkey, after) {
  const d = await stApi(`/api/studio/lessons/${cid}/${lkey}`).catch(e => { if (e && e.message !== "auth") toast((e && e.msg) || "Ochib bo'lmadi"); return null; });
  if (!d) return;
  const L = d.lesson, s = d.state, M = STD.meta;
  const myJobDept = new Set((d.dept_sends || []).map(x => x.job_id));
  const html = `<p class="tiny muted"><code class="st-code" title="Darsning unikal kodi">${esc(L.full_code || "")}</code> ${esc(L.subject)} · ${esc(L.teacher || "")} · ${esc(L.dept || "")}</p>
    <div class="st-tags">${stStageChip(s)}<span class="tiny">${esc(s.next)}</span></div>
    ${typeof lcOpen === "function" && (M.caps.ops) ? `<div class="st-acts"><button type="button" class="btn sm" id="stCard">${ico("file", 14)} Dars kartochkasi</button></div>` : ""}
    <h4>Taqdimot</h4>${stPresHtml(L, d.taqdimot)}
    <p class="tiny muted">Egasi: ${esc(s.owner_label)}${s.due && s.stage !== "nextid" ? ` · muddat ${stDT(s.due)}` : ""}${s.over ? ` · <span class="st-bad">${s.days_over} kun kechikdi</span>` : ""}</p>
    ${M.caps.nextid && ["tasdiq", "nextid"].includes(s.stage) ? `<div class="st-acts"><button type="button" class="btn sm ${s.stage === "tasdiq" ? "primary" : "ghost"}" id="stNx">${s.stage === "tasdiq" ? "NEXTID'ga yuklandi deb belgilash" : "NEXTID belgisini olib tashlash"}</button></div>` : ""}
    ${d.bookings.length ? `<h4>Syomka</h4><ul class="st-ul">${d.bookings.map(b => `<li>${stDT(b.start)} — ${stChip(b.status_label, ST_BK_TONE[b.status])}${b.reason ? ` <span class="muted tiny">«${esc(b.reason)}»</span>` : ""}</li>`).join("")}</ul>` : ""}
    ${d.jobs.length ? `<h4>Montaj</h4><ul class="st-ul">${d.jobs.map(j => `<li>#${j.id} ${stChip(j.status_label, ST_JOB_TONE[j.status])} <span class="tiny muted">${stDT(j.created_at)}</span>${j.status === "tayyor" && M.caps.review ? ` <button type="button" class="st-link" data-rv="${j.id}">ko'rib chiqish</button>` : ""}
      ${j.status === "tasdiqlandi" ? (myJobDept.has(j.id) ? stChip("Masofaviy bo'limga yuborilgan", "ok") : M.caps.review ? ` <button type="button" class="st-link" data-dw="${j.id}">masofaviy bo'limga yuborish</button>` : "") : ""}</li>`).join("")}</ul>` : ""}
    ${d.youtube.length ? `<h4>YouTube</h4><ul class="st-ul">${d.youtube.map(y => `<li>${stChip(y.status_label, y.status === "tayyor" ? "ok" : y.status === "xato" ? "bad" : "info")}${y.url ? ` <a href="${esc(y.url)}" target="_blank" rel="noopener">${esc(y.url)}</a>` : ""}${y.error ? ` <span class="tiny st-bad">${esc(y.error)}</span>` : ""}${y.warning ? ` <span class="tiny">${esc(y.warning)}</span>` : ""}
      ${y.status === "xato" && M.caps.ops ? ` <button type="button" class="st-link" data-yr="${y.id}">qayta urinish</button>` : ""}</li>`).join("")}</ul>` : ""}
    ${stHistHtml(d.history)}`;
  const m = stModal(`${L.code} · ${L.title}`, html, null, "", true);
  stPresBind(m, L, d.taqdimot);
  m.querySelector("#stNx")?.addEventListener("click", ev => stBusy(ev.currentTarget, async () => { if (await stApi(`/api/studio/lessons/${cid}/${lkey}/nextid`, {undo: s.stage === "nextid"})) { toast("Saqlandi"); m.close(); after?.(); } }));
  m.querySelectorAll("[data-rv]").forEach(b => b.onclick = () => { m.close(); stReview(+b.dataset.rv, after); });
  m.querySelectorAll("[data-dw]").forEach(b => b.onclick = () => { m.close(); stSendDept(+b.dataset.dw, after); });
  m.querySelector("#stCard")?.addEventListener("click", () => { m.close(); stOnce(`card:${cid}:${lkey}`, async () => { try { await lcOpen(cid, lkey); } catch (e) { toast("Kartochkani ochib bo'lmadi"); } }); });
  m.querySelectorAll("[data-yr]").forEach(b => b.onclick = async () => { if (await stApi(`/api/studio/youtube/${b.dataset.yr}/retry`, {})) { toast("Qayta navbatga qo'yildi"); m.close(); after?.(); } });
}

/* ---------- Mening darslarim (o'qituvchi) ---------- */
async function stMine(box) {
  const M = STD.meta;
  const [d, mt] = await Promise.all([stApi("/api/studio/lessons"), stApi("/api/studio/meta")]);
  STD.meta = mt;
  const bk = mt.my_bookings || [];
  const cs = d.courses;
  if (STD.cid && !cs.some(c => c.id === STD.cid)) STD.cid = 0;
  if (!STD.cid && cs.length) STD.cid = cs[0].id;
  const L = d.lessons.filter(l => l.course_id === STD.cid);
  box.innerHTML = `<div class="card st-card"><h3>Syomkalarim</h3>${bk.length ? `<div class="st-list">${bk.map(b => `<div class="st-li"><div class="st-li-m"><b>${stWeek(b.start.slice(0, 10))}, ${stDT(b.start)} — ${esc(b.room || "Studiya")}</b>
      <span class="tiny">${esc(b.code)} · ${esc(b.title)} <code class="st-code">${esc(b.full_code || "")}</code></span><span class="muted tiny">${esc(b.subject)} · ${b.pres ? `taqdimot v${b.pres.version} yuborilgan` : "taqdimot hali yuborilmagan"} · slayd va ma'ruza matnini olib keling</span></div>
      <div class="st-li-s"><div class="st-acts tight"><button type="button" class="btn sm ghost" data-mv="${b.id}">Ko'chirish</button><button type="button" class="btn sm ghost" data-cn="${b.id}">Bekor qilish</button></div></div></div>`).join("")}</div>`
      : `<div class="st-empty">Belgilangan syomka yo'q — quyidagi darslardan birini tanlab «Syomkaga yozilish»ni bosing</div>`}</div>
    <div class="card st-card"><div class="st-pickrow">${cs.length > 1 ? `<label class="st-grow"><span class="st-lbl">Fan</span><select id="stMc">${cs.map(c => `<option value="${c.id}" ${c.id === STD.cid ? "selected" : ""}>${esc(c.subject)} (${esc(c.direction || "")}, ${c.course || ""}-kurs)</option>`).join("")}</select></label>`
        : cs.length ? `<h3 class="st-grow">${esc(cs[0].subject)} <span class="muted tiny">${esc(cs[0].direction || "")}, ${cs[0].course || ""}-kurs</span></h3>` : `<span class="muted">Kurslar yo'q</span>`}</div>
      ${L.length ? `<div class="st-list">${L.map(l => `<div class="st-li"><div class="st-li-m"><b>${esc(l.code)} · ${esc(l.title)}</b> <code class="st-code" title="Darsning unikal kodi">${esc(l.full_code || "")}</code><span class="tiny">${esc(l.next)}</span>
        <span class="muted tiny">${["text", "slides"].map(k => `${k === "text" ? "Matn" : "Taqdimot"}: ${l.ready[k] ? "bor" : "yo'q"}`).join(" · ")}${l.pres_version ? ` · taqdimot v${l.pres_version} studiyaga yuborilgan` : " · «Taqdimot» bo'limidan studiyaga yuboring"}${l.booking ? ` · syomka ${stDT(l.booking.start)}` : ""}</span></div>
        <div class="st-li-s">${stStageChip(l)}${l.over && l.owner === "oqituvchi" ? `<span class="tiny st-bad">${l.days_over} kun kechikdi</span>` : ""}
          ${!l.booking && ["bosh", "maruza", "syomka_qilindi"].includes(l.stage) ? `<div class="st-acts tight"><button type="button" class="btn sm ${l.stage === "maruza" ? "primary" : ""}" data-bk="${l.lkey}">Syomkaga yozilish</button></div>` : ""}</div></div>`).join("")}</div>`
        : `<div class="st-empty">Darslar yo'q</div>`}
      <p class="st-note">Ma'ruza matni va taqdimotni «Dars tayyorlash» bo'limiga yuklang — syomkadan keyin video, YouTube va dars fayli avtomatik tayyorlanadi.</p></div>`;
  const mc = box.querySelector("#stMc"); if (mc) mc.onchange = () => { STD.cid = +mc.value; stMine(box); };
  box.querySelectorAll("[data-mv]").forEach(b => b.onclick = () => stMove(bk.find(x => x.id === +b.dataset.mv), () => stMine(box)));
  box.querySelectorAll("[data-cn]").forEach(b => b.onclick = () => stCancel(+b.dataset.cn, () => stMine(box)));
  box.querySelectorAll("[data-bk]").forEach(b => b.onclick = () => { const l = L.find(x => x.lkey === +b.dataset.bk); stSlotPicker(`Syomkaga yozilish: ${l.code} · ${l.title}`, async (start, room) => {
    const r = await stApi("/api/studio/bookings", {course_id: l.course_id, lkey: l.lkey, room_id: room, start}); if (r) { toast(r.warning || "Syomkaga yozildingiz"); stMine(box); } return !!r; }); });
}

/* ---------- Sozlamalar ---------- */
async function stSozlama(box) {
  const d = await stApi("/api/studio/settings");
  const ys = d.youtube;
  const room = r => `<form class="st-form st-room" data-id="${r.id || 0}"><div class="st-frow"><label class="st-grow">Nomi<input type="text" name="name" maxlength="60" value="${esc(r.name || "")}" required></label>
      <label>Ochiladi<input type="time" name="open_from" value="${esc(r.open_from || "09:00")}"></label><label>Yopiladi<input type="time" name="open_to" value="${esc(r.open_to || "18:00")}"></label>
      <label>Slot<select name="slot_min">${d.slot_choices.map(x => `<option value="${x}" ${x === (r.slot_min || 90) ? "selected" : ""}>${x} daqiqa</option>`).join("")}</select></label></div>
    <div class="st-days" role="group" aria-label="Ish kunlari">${ST_DAYS.map((n, i) => `<label class="st-day"><input type="checkbox" name="d" value="${i + 1}" ${String(r.days || "1,2,3,4,5,6").split(",").includes(String(i + 1)) ? "checked" : ""}><span>${n}</span></label>`).join("")}
      ${r.id ? `<label class="st-day"><input type="checkbox" name="active" ${r.active ? "checked" : ""}><span>Faol</span></label>` : ""}</div>
    <div class="st-acts"><button type="submit" class="btn sm ${r.id ? "" : "primary"}">${r.id ? "Saqlash" : "Xona qo'shish"}</button></div></form>`;
  const yesno = (b, t) => stChip(`${t}: ${b ? "saqlangan" : "yo'q"}`, b ? "ok" : "");
  box.innerHTML = `${d.can.rooms ? `<div class="card st-card"><h3>Studiya xonalari</h3><p class="muted tiny">Ish vaqti va slot uzunligi faqat yangi bandlarga ta'sir qiladi.</p>${d.rooms.map(room).join("")}
      <details class="st-det"><summary>Yangi xona</summary>${room({})}</details></div>` : ""}
    ${d.can.sla ? `<div class="card st-card"><h3>Bosqich muddatlari (SLA, kun)</h3><p class="muted tiny">Bosqichga kirgandan keyin shuncha kunda keyingisiga o'tmasa — dars qizil (rahbariyat KPI va egasining «Mening vazifalarim»i). «Syomka belgilandi» — syomka vaqtidan keyin.</p>
      <form class="st-form st-sla" id="stSla">${d.stages.map(s => `<label><span>${esc(s.label)}<small>${esc(s.owner)}</small></span><input type="number" min="0" max="90" name="${s.key}" value="${d.sla[s.key]}"></label>`).join("")}
      <div class="st-acts"><button type="submit" class="btn sm primary">Saqlash</button></div></form></div>` : ""}
    ${ys ? `<div class="card st-card"><h3>YouTube kanali</h3>
      <div class="st-tags">${stChip(ys.configured ? "Ulangan — videolar avtomatik yuklanadi (havola orqali)" : "Ulanmagan — videolar faqat fayl sifatida darsga qo'yiladi", ys.configured ? "ok" : "warn")}
        ${yesno(ys.client_id, "Client ID")}${yesno(ys.client_secret, "Client secret")}${yesno(ys.refresh_token, "Refresh token")}</div>
      <p class="tiny muted">Bugun yuklangan: ${fmt(ys.used_today)} / ${fmt(ys.daily_cap)} · maxfiylik: ${esc(ys.privacy)} · saqlash: ${esc(ys.store)}</p>
      ${ys.last_error ? `<div class="st-warnbox">${ico("alert", 15)}<span>${esc(ys.last_error.error)} <span class="muted">(${stDT(ys.last_error.ts)})</span></span></div>` : ""}
      <form class="st-form" id="stYt" autocomplete="off"><p class="st-note">Qiymatlar faqat kiritiladi — saqlangandan keyin hech qayerda ko'rsatilmaydi. Bo'sh maydon o'zgarmaydi.</p>
        <label>OAuth Client ID<input type="text" name="client_id" placeholder="${ys.client_id ? "saqlangan — almashtirish uchun yangisini kiriting" : "…apps.googleusercontent.com"}" spellcheck="false" autocomplete="off"></label>
        <label>Client secret<input type="password" name="client_secret" placeholder="${ys.client_secret ? "saqlangan" : ""}" autocomplete="new-password"></label>
        <label>Refresh token<input type="password" name="refresh_token" placeholder="${ys.refresh_token ? "saqlangan" : ""}" autocomplete="new-password"></label>
        <div class="st-acts"><button type="submit" class="btn sm primary">Saqlash</button>${ys.configured ? `<button type="button" class="btn sm" id="stYtT">Ulanishni tekshirish</button>` : ""}${ys.client_id || ys.client_secret || ys.refresh_token ? `<button type="button" class="btn sm ghost" id="stYtC">O'chirish</button>` : ""}</div></form>
      <p class="st-note">Google Cloud Console'da qadamma-qadam sozlash — <b>docs/studio.md</b> («YouTube'ni ulash»).</p></div>` : ""}
    <div class="card st-card"><h3>Montaj ishchisi</h3><div class="st-tags">${stChip(stTech() ? (d.worker.configured ? "Token sozlangan" : "Token sozlanmagan") : (d.worker.configured ? "Ulangan" : "Hozircha ishlamayapti"), d.worker.configured ? "ok" : "warn")}${stChip(`Xom video ≤ ${String(d.worker.raw_max_gb).replace(".", ",")} GB`)}</div>
      ${stTech() ? `<p class="st-note">Studiya kompyuteridagi dastur (tools/montaj) serverga <b>X-Worker-Token</b> sarlavhasi bilan ulanadi. Token serverda <b>ISFT_CORE_WORKER_TOKEN</b> muhit o'zgaruvchisida — sahifada ko'rsatilmaydi.</p>`
        : `<p class="st-note">${d.worker.configured ? "Montaj ishlayapti — yuklangan videolar avtomatik navbatga tushadi." : WORKER_OFF_USER}</p>`}</div>`;
  box.querySelectorAll(".st-room").forEach(f => f.onsubmit = async e => {
    e.preventDefault();
    const days = [...f.querySelectorAll('[name="d"]:checked')].map(x => +x.value);
    const body = {id: +f.dataset.id || 0, name: f.elements.name.value, open_from: f.elements.open_from.value, open_to: f.elements.open_to.value, slot_min: +f.elements.slot_min.value, days,
                  active: f.elements.active ? f.elements.active.checked : true};
    if (await stApi("/api/studio/rooms", body)) { toast("Saqlandi"); STD.meta = null; renderStudio("sozlama"); }
  });
  const sf = box.querySelector("#stSla");
  if (sf) sf.onsubmit = async e => { e.preventDefault(); const sla = {}; d.stages.forEach(s => { sla[s.key] = +sf.elements[s.key].value; }); if (await stApi("/api/studio/sla", {sla})) toast("Saqlandi"); };
  const yf = box.querySelector("#stYt");
  if (yf) {
    yf.onsubmit = async e => {
      e.preventDefault();
      const body = {client_id: yf.elements.client_id.value.trim(), client_secret: yf.elements.client_secret.value.trim(), refresh_token: yf.elements.refresh_token.value.trim()};
      if (!body.client_id && !body.client_secret && !body.refresh_token) { toast("Kamida bitta maydonni to'ldiring"); return; }
      const r = await stApi("/api/studio/youtube", body);
      yf.reset();
      if (r) { toast(`Saqlandi: ${r.changed.join(", ")}`); STD.meta = null; renderStudio("sozlama"); }
    };
    box.querySelector("#stYtT")?.addEventListener("click", async ev => {
      ev.target.disabled = true;
      const r = await stApi("/api/studio/youtube/test", {});
      ev.target.disabled = false;
      if (r) toast(r.channel ? `Ulanish ishlaydi: «${r.channel}» kanali` : r.note || "Ulanish ishlaydi");
    });
    box.querySelector("#stYtC")?.addEventListener("click", async () => { if (confirm("YouTube sozlamasi (barcha sirlar) o'chirilsinmi?") && await stApi("/api/studio/youtube/clear", {})) { toast("O'chirildi"); STD.meta = null; renderStudio("sozlama"); } });
  }
}

/* ---------- navigatsiya: go("studio") (app.js go() xaritasiga tegmasdan) ---------- */
(function () {
  if (typeof go !== "function" || go._st) return;
  const prev = go;
  go = function (v, opts) {
    prev(v, opts);
    if (v !== "studio") return;
    const tab = opts && typeof opts === "object" ? opts.tab : undefined;
    Promise.resolve().then(() => renderStudio(tab)).catch(e => { if (e?.message === "auth") return; $("#v-studio").innerHTML = e?.message === "denied" ? locked("Bu bo'lim") : errCard("studio"); });
  };
  go._st = true;
})();
(function () {
  if (typeof showLogin !== "function" || showLogin._st) return;
  const prev = showLogin;
  showLogin = function (...a) { stReset(); return prev.apply(this, a); };
  showLogin._st = true;
})();
