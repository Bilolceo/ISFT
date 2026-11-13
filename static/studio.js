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

async function stApi(url, body, method) {
  const r = await fetch(url, {method: method || (body === undefined ? "GET" : "POST"), credentials: "same-origin",
                              headers: body === undefined ? {} : {"Content-Type": "application/json"}, body: body === undefined ? undefined : JSON.stringify(body)});
  if (r.status === 401) { showLogin(); throw new Error("auth"); }
  const d = await r.json().catch(() => ({}));
  if (!r.ok) {
    const m = stErr(d);
    if (body !== undefined) { toast(m); return null; }
    const e = new Error(r.status === 403 ? "denied" : "api"); e.msg = m; throw e;
  }
  return d;
}
function stModal(title, html, onOk, okText = "Saqlash", wide = false) {
  const bg = document.createElement("div"); bg.className = "st-modal-bg";
  bg.innerHTML = `<div class="st-modal ${wide ? "wide" : ""}" role="dialog" aria-modal="true" aria-label="${esc(title)}"><div class="st-modal-h"><h3>${esc(title)}</h3>
    <button type="button" class="st-x" data-x aria-label="Yopish">×</button></div><div class="st-modal-b">${html}</div>
    <div class="st-acts end">${onOk ? `<button type="button" class="btn ghost" data-x>Bekor qilish</button><button type="button" class="btn primary" data-ok>${esc(okText)}</button>` : `<button type="button" class="btn ghost" data-x>Yopish</button>`}</div></div>`;
  document.body.appendChild(bg);
  const opener = document.activeElement;
  const close = () => { bg.remove(); opener?.focus?.({preventScroll: true}); };
  bg.addEventListener("mousedown", e => { if (e.target === bg) close(); });
  bg.addEventListener("click", e => { if (e.target.closest("[data-x]")) close(); });
  bg.addEventListener("keydown", e => { if (e.key === "Escape") close(); });
  const ok = bg.querySelector("[data-ok]");
  if (ok) ok.onclick = async () => { ok.disabled = true; try { if (await onOk(bg)) close(); } finally { if (ok.isConnected) ok.disabled = false; } };
  setTimeout(() => bg.querySelector("textarea,input,select,button:not([data-x])")?.focus(), 30);
  bg.close = close;
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
  v.innerHTML = `<div class="st-head"><div><h2>Studiya</h2><span class="muted">${esc(sub)}</span></div></div>
    ${M.caps.ops && !M.worker_on ? `<div class="st-warnbox">${ico("alert", 15)}<span>Montaj ishchisi ulanmagan (serverda <b>ISFT_CORE_WORKER_TOKEN</b> sozlanmagan) — vazifalar navbatda kutadi.</span></div>` : ""}
    ${M.tabs.length > 1 ? `<div class="st-tabs" role="tablist">${M.tabs.map(t => `<button type="button" role="tab" aria-selected="${t === STD.tab}" class="${t === STD.tab ? "on" : ""}" data-t="${t}">${esc(M.tab_labels[t])}</button>`).join("")}</div>` : ""}
    <div id="stBox"><div class="st-empty">Yuklanmoqda…</div></div>`;
  v.querySelectorAll(".st-tabs [data-t]").forEach(b => b.onclick = () => renderStudio(b.dataset.t));
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
  const inProc = d.total - d.done;
  const stages = d.stages, mx = Math.max(1, ...stages.map(s => d.totals[s.key]));
  const seg = r => `<div class="st-stack" role="img" aria-label="${esc(stages.filter(s => r.counts[s.key]).map(s => `${s.label}: ${r.counts[s.key]}`).join(", "))}">${stages.map((s, i) => r.counts[s.key] ? `<i class="st-c${i}" style="flex:${r.counts[s.key]}" title="${esc(s.label)}: ${r.counts[s.key]}"></i>` : "").join("")}</div>`;
  box.innerHTML = `<div class="st-kpis">
      <div class="st-kpi"><span>Jarayonda</span><b>${fmt(inProc)}</b><small>ta dars · jami kuzatilayotgan: ${fmt(d.total)}</small></div>
      <div class="st-kpi ${d.red_total ? "bad" : "ok"}"><span>Muddati o'tgan</span><b>${fmt(d.red_total)}</b><small>bosqich muddati (SLA) o'tgan</small></div>
      <div class="st-kpi ok"><span>NEXTID'ga yuklandi</span><b>${fmt(d.done)}</b><small>tugallangan darslar</small></div></div>
    <div class="card st-card"><div class="st-item-h"><h3>Bosqichlar</h3><span class="muted tiny">egasi — kim harakat qilishi kerak</span></div>
      <div class="st-stages">${stages.map((s, i) => `<div class="st-stage"><i class="st-dot st-c${i}"></i><span class="st-sl">${esc(s.label)}<small>${esc(s.owner || "—")}</small></span><b>${fmt(d.totals[s.key])}</b>
        <span class="st-sbar"><i class="st-c${i}" style="width:${100 * d.totals[s.key] / mx}%"></i></span></div>`).join("")}</div></div>
    <div class="card st-card"><div class="st-item-h"><h3>Kesimda</h3>
      <div class="st-seg" role="group" aria-label="Guruhlash">${[["course", "Kurs"], ["kafedra", "Kafedra"], ["teacher", "O'qituvchi"]].map(([k, l]) => `<button type="button" class="${STD.group === k ? "on" : ""}" data-g="${k}">${l}</button>`).join("")}</div></div>
      ${d.rows.length ? `<div class="st-rows">${d.rows.map(r => `<div class="st-row"><div class="st-row-t"><b>${esc(r.name)}</b><span class="muted tiny">${fmt(r.total)} dars${r.red ? ` · <span class="st-bad">${r.red} ta muddati o'tgan</span>` : ""}</span></div>${seg(r)}</div>`).join("")}</div>`
        : `<div class="st-empty">Ishlab chiqarish rejasida kurs yo'q${STD.meta.caps.plan ? " — «Darslar» bo'limida kurs qo'shing" : ""}</div>`}</div>
    <div class="card st-card"><div class="st-item-h"><h3>Muddati o'tgan darslar <span class="st-chip ${d.red_total ? "bad" : "ok"}">${fmt(d.red_total)}</span></h3></div>
      ${d.red.length ? `<div class="st-list">${d.red.map(x => `<div class="st-li"><div class="st-li-m"><b>${esc(x.code)} · ${esc(x.title)}</b>
          <span class="muted tiny">${esc(x.subject)} · ${esc(x.teacher || "—")}</span><span class="tiny">${esc(x.next)}</span></div>
          <div class="st-li-s">${stChip(x.label, "bad")}<span class="tiny">${esc(x.owner_label)} · ${x.days_over} kun kechikdi</span></div></div>`).join("")}</div>`
        : `<div class="st-empty">Muddati o'tgan dars yo'q</div>`}
      ${d.aggregate ? `<p class="st-note">${ico("shield", 14)} Rahbariyat uchun — faqat jamlangan raqamlar va belgilar; video va fayllar bo'lim va operatorda.</p>` : ""}</div>`;
  box.querySelectorAll("[data-g]").forEach(b => b.onclick = () => { STD.group = b.dataset.g; stHolat(box); });
}

/* ---------- Kun rejasi ---------- */
async function stKun(box) {
  const M = STD.meta;
  const d = await stApi(`/api/studio/day?date=${STD.day}`);
  const nav = `<div class="st-daynav"><button type="button" class="btn sm ghost" data-dd="-1" aria-label="Oldingi kun">${ico("chevl", 16)}</button>
      <label class="st-date"><span class="st-sr">Sana</span><input type="date" id="stDay" value="${esc(d.date)}"></label>
      <button type="button" class="btn sm ghost" data-dd="1" aria-label="Keyingi kun">${ico("chevr", 16)}</button>
      ${d.date !== M.today ? `<button type="button" class="btn sm ghost" data-dd="0">Bugun</button>` : ""}<span class="muted tiny">${stWeek(d.date)}, ${stD(d.date)}</span></div>`;
  const slot = (rm, s) => {
    const b = s.booking;
    if (!b) return `<div class="st-slot ${s.past ? "past" : "free"}"><span class="st-time">${stHM(s.start)}–${stHM(s.end)}</span><span class="st-slot-m muted">${s.past ? "—" : "Bo'sh"}</span>
      ${s.free ? `<button type="button" class="btn sm" data-book="${esc(s.start)}" data-room="${rm.id}">Band qilish</button>` : ""}</div>`;
    const j = b.job, acts = [];
    if (b.status === "band") {
      if (b.past || s.past) acts.push(`<button type="button" class="btn sm primary" data-done="${b.id}">Syomka qilindi</button>`, `<button type="button" class="btn sm ghost" data-noshow="${b.id}">Kelmadi</button>`);
      acts.push(`<button type="button" class="btn sm ghost" data-move="${b.id}">Ko'chirish</button>`, `<button type="button" class="btn sm ghost" data-cancel="${b.id}">Bekor qilish</button>`);
    }
    if (b.status === "otdi" || (b.status === "band" && (b.past || s.past))) acts.unshift(`<button type="button" class="btn sm${b.status === "otdi" && !b.has_raw ? " primary" : ""}" data-raw="${b.course_id}:${b.lkey}">${ico("upload", 14)} Xom video</button>`);
    return `<div class="st-slot busy"><span class="st-time">${stHM(s.start)}–${stHM(s.end)}</span><div class="st-slot-m"><b>${esc(b.code)} · ${esc(b.title)}</b>
        <span class="muted tiny">${esc(b.subject)} (${esc(b.group)}) · ${esc(b.teacher || "—")}</span>
        <span class="st-tags">${stChip(b.status_label, ST_BK_TONE[b.status])}${j ? stChip(`Montaj: ${j.status_label}${j.status === "ishlanmoqda" && j.pct != null ? ` ${j.pct}%` : ""}`, ST_JOB_TONE[j.status]) : b.has_raw ? stChip("Xom video yuklangan", "info") : ""}${b.reason ? `<span class="tiny muted">«${esc(b.reason)}»</span>` : ""}</span></div>
      <div class="st-acts">${acts.join("")}</div></div>`;
  };
  box.innerHTML = nav + (d.rooms.length ? d.rooms.map(rm => `<div class="card st-card"><div class="st-item-h"><h3>${esc(rm.name)}</h3><span class="muted tiny">${esc(rm.open_from)}–${esc(rm.open_to)} · ${rm.slot_min} daqiqa</span></div>
      ${rm.works ? `<div class="st-slots">${rm.slots.map(s => slot(rm, s)).join("")}</div>` : `<div class="st-empty">Bu kuni studiya ishlamaydi</div>`}</div>`).join("") : `<div class="st-empty">Faol studiya xonasi yo'q — Sozlamalarda qo'shing</div>`);
  const go2 = n => { STD.day = n === 0 ? M.today : stAddDays(STD.day, n); stKun(box); };
  box.querySelectorAll("[data-dd]").forEach(b => b.onclick = () => go2(+b.dataset.dd));
  box.querySelector("#stDay").onchange = e => { if (e.target.value) { STD.day = e.target.value; stKun(box); } };
  box.querySelectorAll("[data-book]").forEach(b => b.onclick = () => stBookFor(b.dataset.book, +b.dataset.room, () => stKun(box)));
  box.querySelectorAll("[data-done]").forEach(b => b.onclick = async () => { if (await stApi(`/api/studio/bookings/${b.dataset.done}/done`, {status: "otdi"})) { toast("Syomka qilindi deb belgilandi"); stKun(box); } });
  box.querySelectorAll("[data-noshow]").forEach(b => b.onclick = async () => { if (confirm("O'qituvchi kelmadi deb belgilansinmi?") && await stApi(`/api/studio/bookings/${b.dataset.noshow}/done`, {status: "kelmadi"})) { toast("Belgilandi"); stKun(box); } });
  box.querySelectorAll("[data-move]").forEach(b => b.onclick = () => stMove(d.items.find(x => x.id === +b.dataset.move), () => stKun(box)));
  box.querySelectorAll("[data-cancel]").forEach(b => b.onclick = () => stCancel(+b.dataset.cancel, () => stKun(box)));
  box.querySelectorAll("[data-raw]").forEach(b => b.onclick = () => { const [c, l] = b.dataset.raw.split(":"); stRaw(+c, +l, () => stKun(box)); });
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
      if (opts.reason && reason.trim().length < 3) { toast("Ko'chirish sababini yozing"); m.querySelector("#stPreason").focus(); return; }
      b.disabled = true;
      if (await onPick(b.dataset.s, rm.id, reason)) m.close(); else b.disabled = false;
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
    if (reason.length < 3) { toast("Sababini yozing"); return false; }
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
      if (!f) { toast("Faylni tanlang"); return res(false); }
      if (f.size > M.limits.raw_gb * 1073741824) { toast(`Fayl juda katta (${stSize(f.size)})`); return res(false); }
      const pg = m.querySelector(".st-prog"), bar = pg.querySelector("i"), txt = pg.querySelector("span");
      pg.hidden = false;
      const x = new XMLHttpRequest();
      x.open("POST", `/api/studio/lessons/${cid}/${lkey}/raw?name=${encodeURIComponent(f.name)}&template=${encodeURIComponent(m.querySelector("#stRt").value)}`);
      x.upload.onprogress = e => { if (e.lengthComputable) { const p = Math.round(100 * e.loaded / e.total); bar.style.width = p + "%"; txt.textContent = `${p}% · ${stSize(e.loaded)} / ${stSize(e.total)}`; } };
      x.onload = () => {
        let d = {}; try { d = JSON.parse(x.responseText); } catch (e) {}
        if (x.status === 401) { showLogin(); return res(false); }
        if (x.status >= 400) { toast(stErr(d)); pg.hidden = true; return res(false); }
        toast("Xom video yuklandi — montaj navbatida"); after?.(); res(true);
      };
      x.onerror = () => { toast("Yuklash uzildi — qayta urinib ko'ring"); pg.hidden = true; res(false); };
      x.send(f);
    }), "Yuklash");
  return m;
}

/* ---------- Montaj ---------- */
async function stMontaj(box) {
  const d = await stApi("/api/studio/jobs?status=faol");
  const grp = [["tayyor", "Ko'rib chiqish kutmoqda"], ["operator", "Xatolik — operator kerak"], ["ishlanmoqda", "Montaj qilinmoqda"], ["navbatda", "Navbatda"]];
  const card = j => `<div class="st-li"><div class="st-li-m"><b>${esc(j.code)} · ${esc(j.title)}</b><span class="muted tiny">${esc(j.subject)} · ${esc(j.teacher || "—")} · ${esc(j.template_label)}</span>
      ${j.status === "ishlanmoqda" ? `<div class="st-bar" role="img" aria-label="${j.pct || 0}%"><i style="width:${j.pct || 0}%"></i></div><span class="tiny muted">${esc(j.stage || "")} ${j.pct || 0}%${j.message ? " · " + esc(j.message) : ""}</span>` : ""}
      ${j.error && j.status !== "tayyor" ? `<span class="tiny st-bad">${esc(j.error)}</span>` : ""}${j.note ? `<span class="tiny">Izoh: «${esc(j.note)}»</span>` : ""}</div>
    <div class="st-li-s">${stChip(j.status_label, ST_JOB_TONE[j.status])}<span class="tiny muted">${j.attempts ? `${j.attempts}-urinish · ` : ""}${stDT(j.result_at || j.created_at)}</span>
      <div class="st-acts tight">${j.status === "tayyor" ? `<button type="button" class="btn sm primary" data-rev="${j.id}">Ko'rib chiqish</button>` : ""}
        ${j.status === "operator" ? `<button type="button" class="btn sm" data-retry="${j.id}">Qayta urinish</button>` : ""}
        ${["navbatda", "operator"].includes(j.status) ? `<button type="button" class="btn sm ghost" data-jc="${j.id}">Bekor qilish</button>` : ""}</div></div></div>`;
  const items = d.items;
  box.innerHTML = `<div class="st-kpis">${grp.map(([k, l]) => `<div class="st-kpi ${k === "tayyor" && d.counts[k] ? "warn" : k === "operator" && d.counts[k] ? "bad" : ""}"><span>${esc(l)}</span><b>${fmt(d.counts[k] || 0)}</b></div>`).join("")}</div>
    ${!d.worker ? `<p class="st-note">${ico("info", 14)} Montaj ishchisi (studiya kompyuteridagi dastur) hali ulanmagan — tools/montaj va docs/studio.md.</p>` : ""}
    ${grp.map(([k, l]) => { const xs = items.filter(j => j.status === k); return xs.length ? `<div class="card st-card"><h3>${esc(l)}</h3><div class="st-list">${xs.map(card).join("")}</div></div>` : ""; }).join("")
      || `<div class="card st-card"><div class="st-empty">Faol montaj vazifasi yo'q. Xom videoni «Kun rejasi» yoki «Darslar»dan yuklang.</div></div>`}`;
  box.querySelectorAll("[data-rev]").forEach(b => b.onclick = () => stReview(+b.dataset.rev, () => stMontaj(box)));
  box.querySelectorAll("[data-retry]").forEach(b => b.onclick = async () => { if (await stApi(`/api/studio/jobs/${b.dataset.retry}/retry`, {})) { toast("Qayta navbatga qo'yildi"); stMontaj(box); } });
  box.querySelectorAll("[data-jc]").forEach(b => b.onclick = async () => { if (confirm("Montaj vazifasi bekor qilinsinmi?") && await stApi(`/api/studio/jobs/${b.dataset.jc}/cancel`, {})) { toast("Bekor qilindi"); stMontaj(box); } });
}
async function stReview(jid, after) {
  const d = await stApi(`/api/studio/jobs/${jid}`).catch(e => { toast(e.msg || "Ochib bo'lmadi"); return null; });
  if (!d) return;
  const j = d.job, r = j.report || {}, L = d.lesson, T = STD.meta.templates || ST_TPL_DEF;
  const html = `<div class="st-rev"><div class="st-rev-v">${j.media.video ? `<video controls preload="metadata" playsinline ${j.media.thumb ? `poster="${esc(j.media.thumb)}"` : ""} src="${esc(j.media.video)}">
        ${j.media.captions ? `<track kind="subtitles" srclang="uz" label="O'zbekcha" src="${esc(j.media.captions)}" default>` : ""}</video>` : `<div class="st-empty">Video fayli topilmadi</div>`}
      <p class="tiny muted">${esc(L.subject)} · ${esc(L.code)} «${esc(L.title)}» · ${esc(L.teacher || "")} · ${esc(j.template_label)}</p>
      <div class="st-tags">${stChip(`Asl: ${stSec(r.duration_in)}`)}${stChip(`Natija: ${stSec(r.duration_out)}`, "info")}${stChip(`Kesildi: ${stSec(r.cut_total)}`)}${j.files?.captions ? stChip("Subtitr bor", "ok") : stChip("Subtitrsiz")}</div></div>
    <div class="st-rev-s">${(r.warnings || []).length ? `<div class="st-warnbox">${ico("alert", 15)}<span>${r.warnings.map(esc).join("<br>")}</span></div>` : ""}
      <h4>Bo'limlar (${(r.chapters || []).length})</h4>${(r.chapters || []).length ? `<ol class="st-ch">${r.chapters.map(c => `<li><button type="button" class="st-link" data-t="${c.start}">${stSec(c.start)}</button> ${esc(c.title)}</li>`).join("")}</ol>` : `<p class="tiny muted">Bo'limlar yo'q</p>`}
      <h4>Kesilgan joylar (${(r.cuts || []).length})</h4>${(r.cuts || []).length ? `<ul class="st-cuts">${r.cuts.slice(0, 300).map(c => `<li><span class="st-mono">${stSec(c.start)}–${stSec(c.end)}</span> <span class="muted">${esc(ST_CUT[c.reason] || c.reason || "")}</span></li>`).join("")}</ul>` : `<p class="tiny muted">Kesish yo'q</p>`}
      <p class="st-note">Vaqtlar asl yozuv bo'yicha (kesishlar) va natija bo'yicha (bo'limlar).${d.yt_on ? " Tasdiqlansa video darsga qo'yiladi va YouTube'ga (havola orqali) yuklanadi." : " Tasdiqlansa video darsga fayl sifatida qo'yiladi (YouTube ulanmagan)."}</p>
      ${j.status === "tayyor" ? `<div class="st-form st-redo"><label>Qayta montaj uchun izoh<textarea id="stRn" rows="2" maxlength="500" placeholder="Masalan: 12:40 dagi kesishni qaytaring, kirish qisqaroq"></textarea></label>
        <label>Shablon<select id="stRt2">${Object.entries(T).map(([k, l]) => `<option value="${k}" ${k === j.template ? "selected" : ""}>${esc(l)}</option>`).join("")}</select></label>
        <div class="st-acts"><button type="button" class="btn" id="stRedo">Qayta montaj</button><button type="button" class="btn primary" id="stOk">Tasdiqlash</button></div></div>` : `<p>${stChip(j.status_label, ST_JOB_TONE[j.status])}</p>`}</div></div>`;
  const m = stModal(`Montaj natijasi #${j.id}`, html, null, "", true);
  const vid = m.querySelector("video");
  m.querySelectorAll("[data-t]").forEach(b => b.onclick = () => { if (vid) { vid.currentTime = +b.dataset.t; vid.play?.().catch(() => {}); } });
  const ok = m.querySelector("#stOk"), redo = m.querySelector("#stRedo");
  if (ok) ok.onclick = async () => {
    ok.disabled = true;
    const r2 = await stApi(`/api/studio/jobs/${j.id}/approve`, {});
    if (!r2) { ok.disabled = false; return; }
    toast(r2.youtube ? "Tasdiqlandi — YouTube'ga yuklash navbatida" : r2.package && r2.package.ok ? "Tasdiqlandi — dars paketi tayyorlandi" : "Tasdiqlandi — video darsga qo'yildi");
    m.close(); after?.();
  };
  if (redo) redo.onclick = async () => {
    const note = m.querySelector("#stRn").value.trim();
    if (note.length < 3) { toast("Qayta montaj sababini yozing"); m.querySelector("#stRn").focus(); return; }
    redo.disabled = true;
    const r2 = await stApi(`/api/studio/jobs/${j.id}/redo`, {note, template: m.querySelector("#stRt2").value});
    if (!r2) { redo.disabled = false; return; }
    toast("Qayta montajga yuborildi"); m.close(); after?.();
  };
}

/* ---------- Darslar (bo'lim, operator) ---------- */
async function stDarslar(box) {
  const M = STD.meta;
  const all = await stApi("/api/studio/lessons");
  if (STD.cid && !all.courses.some(c => c.id === STD.cid)) STD.cid = 0;
  if (!STD.cid && all.courses.length) STD.cid = all.courses[0].id;
  const L = all.lessons.filter(l => l.course_id === STD.cid);
  box.innerHTML = `<div class="card st-card"><div class="st-pickrow">${all.courses.length ? `<label class="st-grow"><span class="st-lbl">Kurs (ishlab chiqarish rejasida)</span><select id="stCs">${all.courses.map(c => `<option value="${c.id}" ${c.id === STD.cid ? "selected" : ""}>${esc(c.subject)} (${esc(c.direction || "")}, ${c.course || ""}-kurs) — ${esc(c.teacher || "")}</option>`).join("")}</select></label>` : `<span class="muted">Rejada kurs yo'q</span>`}
      ${M.caps.plan ? `<button type="button" class="btn sm" id="stAddC">Kurs qo'shish</button>${STD.cid && all.courses.find(c => c.id === STD.cid)?.planned ? `<button type="button" class="btn sm ghost" id="stRmC">Rejadan olish</button>` : ""}` : ""}</div></div>
    <div class="card st-card">${L.length ? `<div class="st-list">${L.map(l => `<div class="st-li"><div class="st-li-m"><b>${esc(l.code)} · ${esc(l.title)}</b>
        <span class="tiny">${esc(l.next)}</span><span class="tiny muted">${esc(l.owner_label)}${l.due && l.stage !== "nextid" ? ` · muddat ${stD(l.due)}` : ""}${l.booking ? ` · syomka ${stDT(l.booking.start)}` : ""}</span></div>
      <div class="st-li-s">${stStageChip(l)}${l.over ? `<span class="tiny st-bad">${l.days_over} kun kechikdi</span>` : ""}
        <div class="st-acts tight"><button type="button" class="btn sm ghost" data-ld="${l.lkey}">Tafsilot</button>
          ${!l.booking && l.stage !== "nextid" ? `<button type="button" class="btn sm ghost" data-lb="${l.lkey}">Band qilish</button>` : ""}
          <button type="button" class="btn sm ghost" data-lr="${l.lkey}">${ico("upload", 14)} Xom video</button></div></div></div>`).join("")}</div>`
      : `<div class="st-empty">${all.courses.length ? "Darslar yo'q" : "Kurs tanlang yoki rejaga qo'shing"}</div>`}</div>`;
  const cs = box.querySelector("#stCs"); if (cs) cs.onchange = () => { STD.cid = +cs.value; stDarslar(box); };
  box.querySelector("#stAddC")?.addEventListener("click", () => stAddCourse(() => stDarslar(box)));
  box.querySelector("#stRmC")?.addEventListener("click", async () => { if (confirm("Kurs ishlab chiqarish rejasidan olinsinmi? (studiya yozuvlari saqlanadi)") && await stApi("/api/studio/plan", {course_id: STD.cid, on: false})) { STD.cid = 0; stDarslar(box); } });
  const les = k => L.find(l => l.lkey === k);
  box.querySelectorAll("[data-ld]").forEach(b => b.onclick = () => stLesson(STD.cid, +b.dataset.ld, () => stDarslar(box)));
  box.querySelectorAll("[data-lb]").forEach(b => b.onclick = () => { const l = les(+b.dataset.lb); stSlotPicker(`Syomka: ${l.code} · ${l.title}`, async (start, room) => {
    const r = await stApi("/api/studio/bookings", {course_id: l.course_id, lkey: l.lkey, room_id: room, start}); if (r) { toast(r.warning || "Band qilindi"); stDarslar(box); } return !!r; }); });
  box.querySelectorAll("[data-lr]").forEach(b => b.onclick = () => stRaw(STD.cid, +b.dataset.lr, () => stDarslar(box)));
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
async function stLesson(cid, lkey, after) {
  const d = await stApi(`/api/studio/lessons/${cid}/${lkey}`).catch(e => { toast(e.msg || "Ochib bo'lmadi"); return null; });
  if (!d) return;
  const L = d.lesson, s = d.state, M = STD.meta;
  const html = `<p class="tiny muted">${esc(L.subject)} · ${esc(L.teacher || "")} · ${esc(L.dept || "")}</p>
    <div class="st-tags">${stStageChip(s)}<span class="tiny">${esc(s.next)}</span></div>
    <p class="tiny muted">Egasi: ${esc(s.owner_label)}${s.due && s.stage !== "nextid" ? ` · muddat ${stDT(s.due)}` : ""}${s.over ? ` · <span class="st-bad">${s.days_over} kun kechikdi</span>` : ""}</p>
    ${M.caps.nextid && ["tasdiq", "nextid"].includes(s.stage) ? `<div class="st-acts"><button type="button" class="btn sm ${s.stage === "tasdiq" ? "primary" : "ghost"}" id="stNx">${s.stage === "tasdiq" ? "NEXTID'ga yuklandi deb belgilash" : "NEXTID belgisini olib tashlash"}</button></div>` : ""}
    ${d.bookings.length ? `<h4>Syomka</h4><ul class="st-ul">${d.bookings.map(b => `<li>${stDT(b.start)} — ${stChip(b.status_label, ST_BK_TONE[b.status])}${b.reason ? ` <span class="muted tiny">«${esc(b.reason)}»</span>` : ""}</li>`).join("")}</ul>` : ""}
    ${d.jobs.length ? `<h4>Montaj</h4><ul class="st-ul">${d.jobs.map(j => `<li>#${j.id} ${stChip(j.status_label, ST_JOB_TONE[j.status])} <span class="tiny muted">${stDT(j.created_at)}</span>${j.status === "tayyor" && M.caps.review ? ` <button type="button" class="st-link" data-rv="${j.id}">ko'rib chiqish</button>` : ""}</li>`).join("")}</ul>` : ""}
    ${d.youtube.length ? `<h4>YouTube</h4><ul class="st-ul">${d.youtube.map(y => `<li>${stChip(y.status_label, y.status === "tayyor" ? "ok" : y.status === "xato" ? "bad" : "info")}${y.url ? ` <a href="${esc(y.url)}" target="_blank" rel="noopener">${esc(y.url)}</a>` : ""}${y.error ? ` <span class="tiny st-bad">${esc(y.error)}</span>` : ""}${y.warning ? ` <span class="tiny">${esc(y.warning)}</span>` : ""}
      ${y.status === "xato" && M.caps.ops ? ` <button type="button" class="st-link" data-yr="${y.id}">qayta urinish</button>` : ""}</li>`).join("")}</ul>` : ""}
    <h4>Tarix</h4>${d.history.length ? `<ul class="st-hist">${d.history.map(h => `<li><span class="tiny muted">${stDT(h.ts)} · ${esc(h.user_name || "")}</span><span>${esc(h.action)}${h.note ? ` — <span class="muted">${esc(h.note)}</span>` : ""}</span></li>`).join("")}</ul>` : `<p class="tiny muted">Hali yozuv yo'q</p>`}`;
  const m = stModal(`${L.code} · ${L.title}`, html, null, "", true);
  m.querySelector("#stNx")?.addEventListener("click", async () => { if (await stApi(`/api/studio/lessons/${cid}/${lkey}/nextid`, {undo: s.stage === "nextid"})) { toast("Saqlandi"); m.close(); after?.(); } });
  m.querySelectorAll("[data-rv]").forEach(b => b.onclick = () => { m.close(); stReview(+b.dataset.rv, after); });
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
      <span class="tiny">${esc(b.code)} · ${esc(b.title)}</span><span class="muted tiny">${esc(b.subject)} · slayd va ma'ruza matnini olib keling</span></div>
      <div class="st-li-s"><div class="st-acts tight"><button type="button" class="btn sm ghost" data-mv="${b.id}">Ko'chirish</button><button type="button" class="btn sm ghost" data-cn="${b.id}">Bekor qilish</button></div></div></div>`).join("")}</div>`
      : `<div class="st-empty">Belgilangan syomka yo'q — quyidagi darslardan birini tanlab «Syomkaga yozilish»ni bosing</div>`}</div>
    <div class="card st-card"><div class="st-pickrow">${cs.length > 1 ? `<label class="st-grow"><span class="st-lbl">Fan</span><select id="stMc">${cs.map(c => `<option value="${c.id}" ${c.id === STD.cid ? "selected" : ""}>${esc(c.subject)} (${esc(c.direction || "")}, ${c.course || ""}-kurs)</option>`).join("")}</select></label>`
        : cs.length ? `<h3 class="st-grow">${esc(cs[0].subject)} <span class="muted tiny">${esc(cs[0].direction || "")}, ${cs[0].course || ""}-kurs</span></h3>` : `<span class="muted">Kurslar yo'q</span>`}</div>
      ${L.length ? `<div class="st-list">${L.map(l => `<div class="st-li"><div class="st-li-m"><b>${esc(l.code)} · ${esc(l.title)}</b><span class="tiny">${esc(l.next)}</span>
        <span class="muted tiny">${["text", "slides"].map(k => `${k === "text" ? "Matn" : "Taqdimot"}: ${l.ready[k] ? "bor" : "yo'q"}`).join(" · ")}${l.booking ? ` · syomka ${stDT(l.booking.start)}` : ""}</span></div>
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
    <div class="card st-card"><h3>Montaj ishchisi</h3><div class="st-tags">${stChip(d.worker.configured ? "Token sozlangan" : "Token sozlanmagan", d.worker.configured ? "ok" : "warn")}${stChip(`Xom video ≤ ${String(d.worker.raw_max_gb).replace(".", ",")} GB`)}</div>
      <p class="st-note">Studiya kompyuteridagi dastur (tools/montaj) serverga <b>X-Worker-Token</b> sarlavhasi bilan ulanadi. Token serverda <b>ISFT_CORE_WORKER_TOKEN</b> muhit o'zgaruvchisida — sahifada ko'rsatilmaydi.</p></div>`;
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
