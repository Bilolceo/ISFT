/* =====================================================================
   «Yuzma-yuz tadbirlar» (app/yuzma_yuz.py, /api/yuzma; docs/yuzma_yuz.md) — masofaviy talabalarning yuzma-yuz ishlari va huquqiy chegaralar.
     Umumiy:      semestr ro'yxatidan o'tish holati, muddat, rejadagi sessiyalar, huquqiy chegaralar xulosasi.
     Sessiyalar:  ro'yxatdan o'tish / yakuniy nazorat / attestatsiya / himoya — sana, xona, sig'im, talabalarni tayinlash (xabar),
                  shaxsni tekshirish (hujjat oxirgi 4 raqami yoki HEMIS ID + rasm; raqamlar saqlanmaydi), qaydnoma (.docx/.pdf, imzo).
     Talabalar:   holatlar (o'tgan, muddat o'tgan, ozod — xorijiy fuqaro), fuqarolik.
     Monitoring:  umumiy akkaunt belgilari (ko'rib chiqish), talaba kirish jurnali — faqat Masofaviy ta'lim bo'limi.
     Chegaralar:  yo'nalish kvotalari (300 / 30), o'qituvchiga 50 talaba, kunduzgi shakli yo'q yo'nalish, pedagogik yo'nalishlar.
   Ruxsat va ko'lam serverda. Yordamchilar: app.js ($, esc, fmt, toast, locked, errCard, ico, ME, go) va masofaviy.js (dlApi, dlTable,
   dlModal, dlKpi, dlChip, dlD, dlDT, dlPager, dlBar). Menyu bandi va «Masofaviy ta'lim → Umumiy»dagi karta shu faylda qo'shiladi.
   ===================================================================== */
if (!document.querySelector('link[href="masofaviy.css"]')) document.head.insertAdjacentHTML("beforeend", '<link rel="stylesheet" href="masofaviy.css">');
if (!document.querySelector('link[href="yuzma.css"]')) document.head.insertAdjacentHTML("beforeend", '<link rel="stylesheet" href="yuzma.css">');
if (typeof ICONS === "object" && !ICONS.idcheck) ICONS.idcheck = '<rect x="2" y="5" width="20" height="14" rx="2"/><circle cx="8" cy="12" r="2.5"/><path d="M13 10h5M13 14h3"/><path d="m15.5 17 1.5 1.5 3-3"/>';
const YY_ROLES = ["masofaviy", "masofaviy_xodim", "talabalar", "registrator_xodim", "tyutor", "rektor", "prorektor_oquv"];
const YY_TABS = {umumiy: "Umumiy", sessiyalar: "Sessiyalar", talabalar: "Talabalar", monitoring: "Monitoring", chegaralar: "Huquqiy chegaralar"};
const YY = {meta: null, who: null, tab: "umumiy", sess: 0, st: {state: "", q: "", offset: 0}, flag: "yangi"};
const yyCls = {red: "bad", amber: "warn", ok: "ok"};
const yyA = {tayinlangan: "", keldi: "ok", shubhali: "warn", kelmadi: "bad"};

/* ---------- menyu bandi va bo'lim (bir marta) ---------- */
(function () {
  const nav = document.getElementById("nav"), main = document.querySelector("#app main");
  if (!nav || !main) return;
  if (!nav.querySelector('a[data-v="yuzma"]')) {
    const a = document.createElement("a"); a.href = "#"; a.dataset.v = "yuzma"; a.dataset.i = "idcheck"; a.className = "hidden";
    a.innerHTML = `${ico("idcheck")}Yuzma-yuz tadbirlar`;
    a.onclick = e => { e.preventDefault(); go("yuzma"); };
    const after = nav.querySelector('a[data-v="ortda"]');
    after ? after.after(a) : nav.appendChild(a);
  }
  if (!document.getElementById("v-yuzma")) { const s = document.createElement("section"); s.id = "v-yuzma"; s.className = "view hidden"; main.appendChild(s); }
})();
function yyNav() {
  const a = document.querySelector('#nav a[data-v="yuzma"]');
  if (!a || typeof ME === "undefined" || !ME) return;
  a.classList.toggle("hidden", !YY_ROLES.includes(ME.role_key) || (typeof modOn === "function" && !modOn("masofaviy")));
}
(function () {
  if (typeof navApply === "function" && !navApply._yy) {
    const prev = navApply;
    navApply = function (...a) { const r = prev.apply(this, a); yyNav(); if (typeof navGroup === "function" && typeof ME !== "undefined" && ME) navGroup(ME.role_key); return r; };
    navApply._yy = true;
  }
  if (typeof go === "function" && !go._yy) {
    const prev = go;
    go = function (v, opts) {
      const r = prev(v, opts);
      if (v === "yuzma") Promise.resolve().then(() => renderYuzma(opts && opts.tab)).catch(e => { if (e?.message === "auth") return; $("#v-yuzma").innerHTML = e?.message === "denied" ? locked("Yuzma-yuz tadbirlar") : errCard("yuzma"); });
      return r;
    };
    go._yy = true; if (prev._nz) go._nz = true;
  }
  if (typeof XT !== "undefined" && XT.openLink && !XT.openLink._yy) {   /* Nazorat markazi → «Ochish» ({view: "yuzma", tab}) */
    const prev = XT.openLink;
    XT.openLink = function (l) { if (l && l.view === "yuzma") { YY.tab = l.tab || YY.tab; YY.sess = 0; } return prev.call(this, l); };
    XT.openLink._yy = true;
  }
  if (typeof ME !== "undefined" && ME) yyNav();
})();

/* ---------- asosiy ko'rinish ---------- */
async function renderYuzma(tab) {
  const v = $("#v-yuzma");
  const who = typeof ME !== "undefined" ? ME : null;
  if (YY.who !== who) { YY.meta = null; YY.who = who; YY.sess = 0; YY.st = {state: "", q: "", offset: 0}; }
  if (!YY.meta) { const m = await dlApi("/api/yuzma/meta"); if (YY.who !== who) return; YY.meta = m; }
  const M = YY.meta, cp = M.caps;
  const tabs = Object.keys(YY_TABS).filter(t => (t !== "talabalar" || cp.names) && (t !== "monitoring" || cp.journal) && (t !== "chegaralar" || cp.limits));
  if (tab && tabs.includes(tab)) { YY.tab = tab; if (tab !== "sessiyalar") YY.sess = 0; }
  if (!tabs.includes(YY.tab)) YY.tab = tabs[0];
  v.innerHTML = `<div class="dl-head"><div><h2>Yuzma-yuz tadbirlar</h2><span class="muted">${esc(M.scope)} · ${esc(M.term_label)} · ${dlD(M.today)}</span></div>
      <div class="dl-acts">${!document.querySelector('#nav a[data-v="masofaviy"]')?.classList.contains("hidden") ? `<button type="button" class="btn sm ghost" data-dl>${ico("monitor", 15)} Masofaviy ta'lim</button>` : ""}</div></div>
    ${`<div class="dl-demo">${ico("info", 15)}<span>${esc(M.legal_note)}</span></div>`}
    <div class="dl-tabs" role="tablist">${tabs.map(t => `<button type="button" role="tab" aria-selected="${t === YY.tab}" class="${t === YY.tab ? "on" : ""}" data-t="${t}">${esc(YY_TABS[t])}</button>`).join("")}</div>
    <div id="yyBox"><div class="dl-empty">Yuklanmoqda…</div></div>`;
  v.querySelectorAll(".dl-tabs [data-t]").forEach(b => b.onclick = () => { YY.tab = b.dataset.t; YY.sess = 0; renderYuzma(); });
  v.querySelector("[data-dl]")?.addEventListener("click", () => go("masofaviy"));
  const box = $("#yyBox");
  try {
    if (YY.tab === "sessiyalar" && YY.sess) await yySession(box, YY.sess);
    else await ({umumiy: yyOverview, sessiyalar: yySessions, talabalar: yyStudents, monitoring: yyMonitoring, chegaralar: yyLimits})[YY.tab](box);
  } catch (e) {
    if (e?.message === "auth") return;
    box.innerHTML = e?.message === "denied" ? locked("Bu bo'lim") : `<div class="card dl-card"><p>${esc(e?.msg || "Ma'lumotni yuklab bo'lmadi")}</p></div>`;
  }
}
const yyOpen = id => { YY.tab = "sessiyalar"; YY.sess = id; renderYuzma(); };
const yySessRow = x => `<button type="button" class="yy-sess" data-sess="${x.id}">
    <span class="yy-date"><b>${esc(x.date.slice(8, 10))}.${esc(x.date.slice(5, 7))}</b><small>${esc(x.start_time)}</small></span>
    <span class="yy-sm"><b>${esc(x.title)}</b><small>${esc(x.kind_label)} · ${esc(x.room)}</small></span>
    <span class="yy-sr">${dlChip(`${fmt(x.assigned)} / ${fmt(x.capacity)}`, x.free ? "" : "warn")}${x.status !== "rejada" ? dlChip(x.status === "yopilgan" ? "Qaydnoma" : "Bekor", x.status === "yopilgan" ? "ok" : "") : x.today ? dlChip("Bugun", "info") : ""}</span></button>`;

/* ---------- Umumiy ---------- */
async function yyOverview(box) {
  const d = await dlApi("/api/yuzma/overview"), c = d.counts, M = YY.meta, L = d.limits;
  const nm = M.caps.names;
  box.innerHTML = `
    <h3 class="dl-sec">Semestr oldidan ro'yxatdan o'tish <span class="muted">· muddat ${dlD(d.deadline)}${d.deadline_passed ? " (o'tdi)" : ""}</span>
      ${M.caps.deadline ? `<button type="button" class="btn sm ghost" id="yyDl">${ico("calendar", 14)} Muddatni o'zgartirish</button>` : ""}</h3>
    <div class="dl-kpis">
      ${dlKpi("Majburiy (O'zbekiston fuqarolari)", fmt(c.majburiy), "faol masofaviy talabalar")}
      ${dlKpi("Ro'yxatdan o'tgan", fmt(c.otgan), `${c.majburiy ? (100 * c.otgan / c.majburiy).toFixed(1).replace(".", ",") : 0}% · shaxsi tasdiqlangan`, "ok", nm ? "otgan" : "")}
      ${dlKpi(d.deadline_passed ? "Muddat o'tgan" : "Kutilmoqda", fmt(d.deadline_passed ? c.muddati_otgan : c.kutilmoqda + c.tayinlangan),
              d.deadline_passed ? "kabinetda qizil banner" : `shundan tayinlangan: ${fmt(c.tayinlangan)}`, (d.deadline_passed ? c.muddati_otgan : 0) ? "bad" : "warn", nm ? (d.deadline_passed ? "muddati_otgan" : "kutilmoqda") : "")}
      ${dlKpi("Ozod (xorijiy fuqarolar)", fmt(c.ozod), "yuzma-yuz talab qilinmaydi", "", nm ? "ozod" : "")}
      ${dlKpi("Akademik ta'tilda", fmt(c.tatil), "hisobga olinmaydi")}
      ${d.flags_open != null ? dlKpi("Umumiy akkaunt alomati", fmt(d.flags_open), "ko'rib chiqilmagan", d.flags_open ? "warn" : "ok") : ""}
    </div>
    <div class="dl-grid yy-grid">
      <div class="card dl-card"><h3>Rejadagi sessiyalar</h3>
        ${d.upcoming.length ? `<div class="yy-list">${d.upcoming.map(yySessRow).join("")}</div>` : `<div class="dl-empty">Rejadagi sessiya yo'q.</div>`}
        ${M.caps.manage ? `<div class="dl-acts"><button type="button" class="btn sm primary" id="yyNew">${ico("checkc", 14)} Yangi sessiya</button></div>` : ""}</div>
      ${L ? `<div class="card dl-card"><h3>Huquqiy chegaralar</h3>${yyLimitSummary(L)}
        <div class="dl-acts"><button type="button" class="btn sm ghost" data-tab="chegaralar">Batafsil →</button></div></div>` : ""}
    </div>`;
  box.querySelectorAll("[data-sess]").forEach(b => b.onclick = () => yyOpen(+b.dataset.sess));
  box.querySelectorAll("[data-go]").forEach(b => b.onclick = () => { YY.st = {state: b.dataset.go, q: "", offset: 0}; YY.tab = "talabalar"; renderYuzma(); });
  box.querySelectorAll("[data-tab]").forEach(b => b.onclick = () => { YY.tab = b.dataset.tab; renderYuzma(); });
  $("#yyNew")?.addEventListener("click", yyNewSession);
  $("#yyDl")?.addEventListener("click", () => dlModal("Ro'yxatdan o'tish muddati", `<p class="muted">${esc(M.term_label)}. Muddatdan keyin o'tmagan talabalar kabinetida qizil banner chiqadi va Nazorat markaziga istisno tushadi.</p>
      <label>Muddat<input type="date" id="yyDlD" value="${esc(d.deadline)}"></label>`, async bg => {
        const r = await dlApi("/api/yuzma/deadline", {date: bg.querySelector("#yyDlD").value}); if (!r) return false;
        toast("Muddat saqlandi"); YY.meta = null; renderYuzma(); return true; }));
}
function yyLimitSummary(L) {
  const row = (cls, t, s) => `<div class="yy-lim ${cls}"><b>${t}</b><span>${s}</span></div>`;
  return `<div class="yy-lims">
    ${row(L.programs_red ? "bad" : L.programs_amber ? "warn" : "ok", `${L.programs_red} / ${L.programs_amber}`, "yo'nalish: kvota to'lgan / 90 %+")}
    ${row(L.teachers_red ? "bad" : L.teachers_amber ? "warn" : "ok", `${fmt(L.teachers_red)}`, `o'qituvchida chegaradan ortiq talaba (${fmt(L.teachers_total)} tadan)`)}
    ${row(L.pedagogical ? "bad" : "ok", `${L.pedagogical}`, "pedagogik yo'nalishda masofaviy talaba")}
    ${row(L.no_full_time ? "bad" : "ok", `${L.no_full_time}`, "kunduzgi shakli yo'q masofaviy yo'nalish")}</div>`;
}

/* ---------- Sessiyalar ---------- */
async function yySessions(box) {
  const d = await dlApi("/api/yuzma/sessions"), M = YY.meta;
  const by = {rejada: d.items.filter(x => x.status === "rejada").sort((a, b) => (a.date + a.start_time).localeCompare(b.date + b.start_time)),
              boshqa: d.items.filter(x => x.status !== "rejada")};
  box.innerHTML = `<div class="dl-acts">${M.caps.manage ? `<button type="button" class="btn sm primary" id="yyNew">${ico("checkc", 14)} Yangi sessiya</button>` : ""}</div>
    <div class="card dl-card"><h3>Rejada</h3>${by.rejada.length ? `<div class="yy-list">${by.rejada.map(yySessRow).join("")}</div>` : `<div class="dl-empty">Rejadagi sessiya yo'q.</div>`}</div>
    <div class="card dl-card"><h3>O'tkazilgan va bekor qilingan</h3>${by.boshqa.length ? `<div class="yy-list">${by.boshqa.map(yySessRow).join("")}</div>` : `<div class="dl-empty">Hali yo'q.</div>`}</div>`;
  box.querySelectorAll("[data-sess]").forEach(b => b.onclick = () => yyOpen(+b.dataset.sess));
  $("#yyNew")?.addEventListener("click", yyNewSession);
}
function yyNewSession() {
  const M = YY.meta, t = new Date(M.today + "T12:00:00"); t.setDate(t.getDate() + 7);
  dlModal("Yangi yuzma-yuz sessiya", `
    <label>Tadbir turi<select id="yyK">${Object.entries(M.kinds).map(([k, l]) => `<option value="${k}">${esc(l)}</option>`).join("")}</select></label>
    <label>Nomi (ixtiyoriy)<input id="yyT" maxlength="200" placeholder="Masalan: Qo'shimcha ro'yxatdan o'tish"></label>
    <div class="yy-g2"><label>Sana<input type="date" id="yyD" min="${esc(M.today)}" value="${t.toISOString().slice(0, 10)}"></label>
      <label>Sig'im (o'rin)<input type="number" id="yyC" min="1" max="2000" value="60"></label></div>
    <div class="yy-g2"><label>Boshlanish<input type="time" id="yyS" value="09:00"></label><label>Tugash<input type="time" id="yyE" value="13:00"></label></div>
    <label>Xona<input id="yyR" list="yyRooms" maxlength="120" value="${esc(M.rooms[0])}"><datalist id="yyRooms">${M.rooms.map(r => `<option value="${esc(r)}">`).join("")}</datalist></label>
    <label>Izoh<input id="yyN" maxlength="500"></label>`, async bg => {
      const q = s => bg.querySelector(s).value;
      const r = await dlApi("/api/yuzma/sessions", {kind: q("#yyK"), title: q("#yyT"), date: q("#yyD"), start_time: q("#yyS"), end_time: q("#yyE"), room: q("#yyR"), capacity: +q("#yyC"), note: q("#yyN")});
      if (!r) return false; toast("Sessiya yaratildi"); yyOpen(r.session.id); return true;
    }, "Yaratish");
}
async function yySession(box, id) {
  const d = await dlApi(`/api/yuzma/sessions/${id}`), s = d.session, cp = d.caps, M = YY.meta;
  const pr = d.protocol;
  box.innerHTML = `<div class="dl-acts"><button type="button" class="btn sm ghost" id="yyBack">← Sessiyalar</button></div>
    <div class="card dl-card yy-head"><div><h3>${esc(s.title)}</h3>
      <div class="muted">${esc(s.kind_label)} · ${dlD(s.date)}, ${esc(s.start_time)}–${esc(s.end_time)} · ${esc(s.room)}${s.direction ? " · " + esc(s.direction) : ""}</div>
      <div class="dl-chips">${dlChip(s.status_label, s.status === "yopilgan" ? "ok" : s.status === "bekor" ? "" : "info")} ${dlChip(`Tayinlangan ${fmt(s.assigned)} / ${fmt(s.capacity)}`)}
        ${dlChip(`Keldi ${fmt(s.came)}`, "ok")} ${s.doubt ? dlChip(`Shaxsi tasdiqlanmagan ${fmt(s.doubt)}`, "warn") : ""} ${s.absent ? dlChip(`Kelmadi ${fmt(s.absent)}`, "bad") : ""}</div></div>
      <div class="dl-acts">
        ${cp.manage ? `<button type="button" class="btn sm" id="yyAdd">${ico("checkc", 14)} Talaba qo'shish</button>` : ""}
        ${cp.sign ? `<button type="button" class="btn sm primary" id="yySign">${ico("check", 14)} Qaydnomani imzolash</button>` : ""}
        ${pr ? `<a class="btn sm" href="/api/yuzma/sessions/${s.id}/protocol.docx">${ico("report", 14)} Qaydnoma .docx</a><a class="btn sm" href="/api/yuzma/sessions/${s.id}/protocol.pdf">${ico("report", 14)} .pdf</a>` : ""}
        ${M.caps.sign && s.status === "rejada" && !s.came && !s.doubt && !s.absent ? `<button type="button" class="btn sm ghost" id="yyCancel">Bekor qilish</button>` : ""}</div></div>
    ${pr ? `<div class="dl-note yy-pr">${ico("check", 14)} Qaydnoma ${esc(pr.reg_no)} — ${esc(pr.signed_role || "")}: ${esc((pr.signed_name || "").split(":").pop().trim())}, ${dlDT(pr.signed_at)} · tekshirish kodi ${esc(pr.verify_code)}${pr.sha256 ? ` · SHA-256 ${esc(pr.sha256.slice(0, 16))}…` : ""}</div>` : ""}
    ${!cp.check && s.status === "rejada" && !s.past && !s.today && M.caps.manage ? `<p class="muted tiny">Davomat va shaxsni tekshirish sessiya kuni ochiladi.</p>` : ""}
    <div class="card dl-card">${d.names ? dlTable([
      ["Talaba", r => `<b>${esc(r.full_name)}</b><small>${esc(r.grp)} · HEMIS ${esc(r.hemis_id)}</small>`],
      ["Holat", r => dlChip(r.status_label, yyA[r.status])],
      ["Shaxsni tekshirish", r => r.method ? `${esc(r.method_label)}<small>raqam ${r.doc_match ? "mos" : "<b class='dl-bad'>mos emas</b>"} (${r.match_src === "tizim" ? "tizim" : "xodim"}) · rasm ${r.photo_ok ? "mos" : "<b class='dl-bad'>mos emas</b>"}</small>` : (r.status === "kelmadi" ? "—" : `<small>${r.has_ref ? "HEMIS ma'lumotnomasi bor" : "ma'lumotnoma yo'q — ko'zdan"}</small>`)],
      ["Tekshirgan", r => r.checked_name ? `${esc(r.checked_name)}<small>${dlDT(r.checked_at)}</small>` : "—"],
      ...(cp.check ? [["", r => `<div class="yy-ra"><button type="button" class="btn sm" data-chk="${r.student_id}">${ico("idcheck", 14)} Tekshirish</button>${r.status !== "kelmadi" ? `<button type="button" class="btn sm ghost" data-abs="${r.student_id}">Kelmadi</button>` : ""}</div>`, "yy-act"]] : []),
      ...(cp.manage && !cp.check ? [["", r => r.status === "tayinlangan" ? `<button type="button" class="btn sm ghost" data-rm="${r.student_id}">Olib tashlash</button>` : "", "yy-act"]] : [])],
      d.roster, {empty: "Hali hech kim tayinlanmagan", rowCls: r => r.status === "shubhali" || r.status === "kelmadi" ? "dl-row-bad" : ""})
      : `<p class="muted">Ro'yxat ismlarsiz: jamlangan sonlar yuqorida.</p>`}</div>`;
  $("#yyBack").onclick = () => { YY.sess = 0; renderYuzma(); };
  $("#yyAdd")?.addEventListener("click", () => yyAssign(s));
  $("#yySign")?.addEventListener("click", () => dlModal("Qaydnomani imzolash", `<p>Sessiya yopiladi: belgilanmagan ${fmt(s.assigned - s.came - s.doubt - s.absent)} nafar talaba «Kelmadi» deb yoziladi.
      Qaydnoma ro'yxat raqami va tekshirish kodi bilan Hujjatlar reyestriga yoziladi. Imzodan keyin davomat o'zgarmaydi.</p>`, async () => {
        const r = await dlApi(`/api/yuzma/sessions/${s.id}/sign`, {}); if (!r) return false;
        toast(`Qaydnoma imzolandi: ${r.reg_no}`); renderYuzma(); return true; }, "Imzolash"));
  $("#yyCancel")?.addEventListener("click", () => dlModal("Sessiyani bekor qilish", `<label>Sabab<input id="yyCn" maxlength="300"></label>`, async bg => {
        const r = await dlApi(`/api/yuzma/sessions/${s.id}/cancel`, {note: bg.querySelector("#yyCn").value}); if (!r) return false;
        toast("Bekor qilindi"); YY.sess = 0; renderYuzma(); return true; }, "Bekor qilish"));
  box.querySelectorAll("[data-chk]").forEach(b => b.onclick = () => yyCheck(s, d.roster.find(r => r.student_id === +b.dataset.chk)));
  box.querySelectorAll("[data-abs]").forEach(b => b.onclick = async () => { const r = await dlApi(`/api/yuzma/sessions/${s.id}/absent/${b.dataset.abs}`, {}); if (r) { toast("Kelmadi"); renderYuzma(); } });
  box.querySelectorAll("[data-rm]").forEach(b => b.onclick = async () => { const r = await dlApi(`/api/yuzma/sessions/${s.id}/unassign/${b.dataset.rm}`, {}); if (r) renderYuzma(); });
}
function yyAssign(s) {
  dlModal("Talabalarni tayinlash", `<p class="muted">Bo'sh joy: <b>${fmt(s.free)}</b>. Xorijiy fuqarolar (ozod), faol bo'lmagan va ${s.kind === "royxat" ? "allaqachon ro'yxatdan o'tgan" : "boshqa sessiyaga tayinlangan"} talabalar o'tkazib yuboriladi.
      Har bir talabaga xabar yuboriladi (Telegram — kabinetda ulangan bo'lsa).</p>
    ${s.kind === "royxat" ? `<label class="yy-chk"><input type="checkbox" id="yyP" checked> Hali ro'yxatdan o'tmagan va tayinlanmagan talabalar (bo'sh joygacha)</label>` : ""}
    <label>Yoki talaba ID lari (vergul bilan)<input id="yyIds" placeholder="masalan: 1201, 1202"></label>
    <label>Yoki guruh ID<input id="yyG" type="number" min="0" value=""></label>`, async bg => {
      const p = bg.querySelector("#yyP")?.checked, ids = bg.querySelector("#yyIds").value.split(/[\s,;]+/).filter(Boolean).map(Number).filter(Boolean), g = +bg.querySelector("#yyG").value || 0;
      const body = ids.length ? {student_ids: ids} : g ? {group_id: g} : {pending: !!p};
      const r = await dlApi(`/api/yuzma/sessions/${s.id}/assign`, body); if (!r) return false;
      toast(`Tayinlandi: ${r.assigned} ta${r.skipped_n ? ` · o'tkazib yuborildi: ${r.skipped_n}` : ""}`); renderYuzma(); return true;
    }, "Tayinlash");
}
function yyCheck(s, r) {
  const M = YY.meta;
  const bg = dlModal(`Shaxsni tekshirish — ${r.full_name}`, `
    <p class="muted">${esc(r.grp)} · HEMIS ${esc(r.hemis_id)}. Hujjatni ko'zdan kechiring va rasmni yuz bilan solishtiring. <b>Kiritilgan raqamlar saqlanmaydi</b> — faqat natija.</p>
    <label>Hujjat<select id="yyM">${Object.entries(M.methods).map(([k, l]) => `<option value="${k}">${esc(l)}</option>`).join("")}</select></label>
    <label id="yyCodeL">Hujjatning oxirgi 4 raqami<input id="yyCode" inputmode="numeric" maxlength="4" autocomplete="off" placeholder="••••"></label>
    ${r.has_ref ? `<p class="tiny muted">HEMIS ma'lumotnomasi bor — raqam tizimda (xesh bilan) solishtiriladi.</p>` : `<label class="yy-chk" id="yyDocL"><input type="checkbox" id="yyDoc"> Hujjat shu talabaga tegishli (HEMIS kartochkasi bilan ko'zdan solishtirildi)</label>`}
    <label class="yy-chk"><input type="checkbox" id="yyPh"> Hujjatdagi rasm yuz bilan mos</label>
    <label>Izoh (ixtiyoriy)<input id="yyNt" maxlength="300"></label>`, async b => {
      const m = b.querySelector("#yyM").value;
      const res = await dlApi(`/api/yuzma/sessions/${s.id}/check`, {student_id: r.student_id, method: m, code: b.querySelector("#yyCode").value,
        doc_ok: !!b.querySelector("#yyDoc")?.checked, photo_ok: b.querySelector("#yyPh").checked, note: b.querySelector("#yyNt").value});
      if (!res) return false;
      toast(res.status === "keldi" ? "Shaxsi tasdiqlandi — keldi" : "Shaxsi tasdiqlanmadi — «shubhali» deb yozildi"); renderYuzma(); return true;
    }, "Saqlash");
  const sel = bg.querySelector("#yyM"), code = bg.querySelector("#yyCode"), lab = bg.querySelector("#yyCodeL");
  sel.onchange = () => {
    const h = sel.value === "hemis";
    lab.firstChild.textContent = h ? "Guvohnomadagi HEMIS ID" : "Hujjatning oxirgi 4 raqami";
    code.maxLength = h ? 20 : 4; code.placeholder = h ? "HEMIS ID" : "••••"; code.value = "";
    const dl = bg.querySelector("#yyDocL"); if (dl) dl.hidden = h;
  };
}

/* ---------- Talabalar ---------- */
async function yyStudents(box) {
  const F = YY.st, M = YY.meta;
  const d = await dlApi("/api/yuzma/students?" + new URLSearchParams({state: F.state, q: F.q, offset: F.offset, limit: 50}));
  const SC = {otgan: "ok", tayinlangan: "info", kutilmoqda: "warn", muddati_otgan: "bad", ozod: "", tatil: ""};
  box.innerHTML = `<div class="dl-filters"><select id="yyS" aria-label="Holat"><option value="">Barcha holatlar</option>${Object.entries(M.states).map(([k, l]) => `<option value="${k}" ${F.state === k ? "selected" : ""}>${esc(l)}</option>`).join("")}</select>
      <input id="yyQ" type="search" placeholder="Ism, guruh yoki HEMIS ID" value="${esc(F.q)}" aria-label="Qidiruv"></div>
    <div class="card dl-card">${dlTable([
      ["Talaba", r => `<b>${esc(r.full_name)}</b><small>${esc(r.grp)} · HEMIS ${esc(r.hemis_id)}</small>`],
      ["Yo'nalish", r => `${esc(r.direction)}<small>${esc(r.course)}-kurs · ${esc(r.level)}</small>`],
      ["Fuqarolik", r => `${esc(r.country)}${M.caps.citizenship ? ` <button type="button" class="dl-link" data-cit="${r.id}" data-cc="${esc(r.citizenship || "UZ")}">o'zgartirish</button>` : ""}`],
      ["Holat", r => `${dlChip(r.state_label, SC[r.state])}${r.next ? `<small>${dlD(r.next.date)} ${esc(r.next.start_time)} · ${esc(r.next.room)}</small>` : ""}`],
      ...(M.caps.journal ? [["", r => `<button type="button" class="btn sm ghost" data-jr="${r.id}">Kirish jurnali</button>`, "yy-act"]] : [])],
      d.items, {empty: "Mos talaba yo'q", rowCls: r => r.state === "muddati_otgan" ? "dl-row-bad" : ""})}
      ${dlPager(d.total, F.offset, 50, o => { F.offset = o; renderYuzma(); })}</div>`;
  const re = () => { F.offset = 0; renderYuzma(); };
  $("#yyS").onchange = e => { F.state = e.target.value; re(); };
  let t; $("#yyQ").oninput = e => { clearTimeout(t); t = setTimeout(() => { F.q = e.target.value.trim(); re(); }, 350); };
  box.querySelectorAll("[data-jr]").forEach(b => b.onclick = () => yyJournal(+b.dataset.jr));
  box.querySelectorAll("[data-cit]").forEach(b => b.onclick = () => dlModal("Fuqarolik", `<p class="muted">Xorijiy fuqarolar yuzma-yuz ro'yxatdan o'tishdan ozod. Mamlakat kodi (ISO): UZ, KZ, TJ, TM, KG, AF, TR …</p>
      <label>Kod<input id="yyCc" maxlength="3" value="${esc(b.dataset.cc)}"></label>`, async bg => {
        const r = await dlApi(`/api/yuzma/students/${b.dataset.cit}/citizenship`, {citizenship: bg.querySelector("#yyCc").value.trim()}); if (!r) return false;
        toast(`Saqlandi: ${r.country}`); renderYuzma(); return true; }));
}

/* ---------- Monitoring ---------- */
async function yyMonitoring(box) {
  const d = await dlApi("/api/yuzma/flags?status=" + encodeURIComponent(YY.flag));
  box.innerHTML = `<div class="card dl-card"><h3>Umumiy akkaunt alomatlari</h3>
      <p class="muted">Talaba kabinetiga kirishlar bo'yicha: bir vaqtda turli tarmoqlardan faol sessiyalar (oxirgi ${d.rules.parallel_idle_min} daqiqa), ${d.rules.switch_min} daqiqa ichida tarmoq va qurilma almashishi,
        sutkada ${d.rules.many_nets}+ tarmoq. <b>Avtomatik bloklanmaydi</b> — bo'lim tekshiradi (talaba bilan bog'lanish, keyingi yuzma-yuz tadbirda shaxsni tekshirish).
        IP va qurilma ma'lumoti faqat xesh ko'rinishida saqlanadi.</p>
      <div class="dl-seg" role="tablist">${Object.entries({yangi: "Ko'rib chiqilmagan", tasdiqlandi: "Tasdiqlangan", asossiz: "Asossiz", all: "Hammasi"}).map(([k, l]) =>
        `<button type="button" class="${YY.flag === k ? "on" : ""}" data-fl="${k}">${esc(l)}${d.counts[k] != null ? ` (${d.counts[k]})` : ""}</button>`).join("")}</div>
      ${dlTable([
        ["Talaba", r => `<button type="button" class="dl-link" data-jr="${r.student_id}">${esc(r.full_name)}</button><small>${esc(r.grp)} · HEMIS ${esc(r.hemis_id)}</small>`],
        ["Alomat", r => `<b>${esc(r.kind_label)}</b><small>${esc(r.detail)}</small>`],
        ["Qachon", r => `${dlDT(r.ts_last)}<small>${r.n > 1 ? `${r.n} marta · birinchi ${dlDT(r.ts_first)}` : ""}</small>`],
        ["Holat", r => `${dlChip(r.status_label, r.status === "yangi" ? "warn" : r.status === "tasdiqlandi" ? "bad" : "ok")}${r.review_note ? `<small>${esc(r.reviewed_name || "")}: ${esc(r.review_note)}</small>` : ""}`],
        ["", r => r.status === "yangi" ? `<div class="yy-ra"><button type="button" class="btn sm" data-rv="${r.id}" data-d="tasdiqlandi">Tasdiqlash</button><button type="button" class="btn sm ghost" data-rv="${r.id}" data-d="asossiz">Asossiz</button></div>` : "", "yy-act"]],
        d.items, {empty: "Belgi yo'q"})}</div>`;
  box.querySelectorAll("[data-fl]").forEach(b => b.onclick = () => { YY.flag = b.dataset.fl; renderYuzma(); });
  box.querySelectorAll("[data-jr]").forEach(b => b.onclick = () => yyJournal(+b.dataset.jr));
  box.querySelectorAll("[data-rv]").forEach(b => b.onclick = () => dlModal(b.dataset.d === "tasdiqlandi" ? "Alomatni tasdiqlash" : "Asossiz deb yopish",
      `<label>Izoh (nima tekshirildi)<textarea id="yyRn" maxlength="500" placeholder="Masalan: talaba bilan bog'lanildi — ota-onasi telefonidan kirgan"></textarea></label>`, async bg => {
        const r = await dlApi(`/api/yuzma/flags/${b.dataset.rv}/review`, {decision: b.dataset.d, note: bg.querySelector("#yyRn").value}); if (!r) return false;
        toast("Saqlandi"); renderYuzma(); return true; }));
}
async function yyJournal(sid) {
  const d = await dlApi(`/api/yuzma/journal/${sid}`); const s = d.student, T = d.totals;
  dlModal(`Kirish jurnali — ${s.full_name}`, `<p class="muted">${esc(s.grp)} · HEMIS ${esc(s.hemis_id)} · ${esc(s.country)} · oxirgi 30 kun</p>
    <div class="dl-kpis">${dlKpi("Kirishlar", fmt(T.logins))}${dlKpi("Tarmoqlar", fmt(T.networks), "", T.networks >= 4 ? "warn" : "")}${dlKpi("Qurilmalar", fmt(T.devices), "", T.devices >= 3 ? "warn" : "")}
      ${dlKpi("Dars ochilgan", fmt(T.launches))}${dlKpi("xAPI statementlar", fmt(T.statements))}</div>
    ${d.flags.length ? `<h4>Alomatlar</h4>${d.flags.map(f => `<div class="yy-fl">${dlChip(f.status_label, f.status === "yangi" ? "warn" : f.status === "tasdiqlandi" ? "bad" : "ok")} <b>${esc(f.kind_label)}</b> · ${dlDT(f.ts_last)}<small>${esc(f.detail)}</small></div>`).join("")}` : ""}
    <h4>Kirishlar</h4>${dlTable([["Vaqt", r => dlDT(r.ts)], ["Tarmoq", r => `<b>${esc(r.net)}</b>`], ["Qurilma", r => `${esc(r.dev)} · ${esc(r.device)}`],
      ["", r => r.parallel ? dlChip("bir vaqtda", "warn") : ""]], d.logins.slice(0, 60), {empty: "Kirish yo'q"})}
    <h4>Kunlar bo'yicha</h4>${dlTable([["Kun", r => dlD(r.d)], ["Kirish", r => fmt(r.logins), "num"], ["Dars ochilgan", r => fmt(r.launches), "num"], ["Statementlar", r => fmt(r.statements), "num"]], d.days.slice(0, 30), {empty: "Faollik yo'q"})}
    ${d.inperson.length ? `<h4>Yuzma-yuz tadbirlar</h4>${d.inperson.map(x => `<div class="yy-fl">${dlChip(x.status_label, yyA[x.status])} ${esc(x.title)} · ${dlD(x.date)}</div>`).join("")}` : ""}
    <p class="tiny muted">${esc(d.note)}</p>`, null, "", true);
}

/* ---------- Huquqiy chegaralar ---------- */
async function yyLimits(box) {
  const d = await dlApi("/api/yuzma/limits"), R = d.rules;
  const flag = (p) => p.level_flag === "red" ? dlChip(p.over ? "Oshgan" : "To'lgan", "bad") : p.level_flag === "amber" ? dlChip(`${R.warn_pct}%+`, "warn") : dlChip("Me'yorda", "ok");
  box.innerHTML = `<div class="dl-note">${ico("info", 14)} ${esc(d.legal_note)} Chegaralarni rektor «Nazorat markazi → Qoidalar»da o'zgartiradi: bakalavr ${R.bakalavr}, magistratura ${R.magistr}, o'qituvchiga ${R.teacher}, ogohlantirish ${R.warn_pct}%.</div>
    <div class="dl-kpis">${dlKpi("Masofaviy talabalar", fmt(d.summary.students))}${dlKpi("Kvota to'lgan / oshgan", fmt(d.summary.programs_red), `${fmt(d.summary.programs_amber)} ta — ${R.warn_pct}%+`, d.summary.programs_red ? "bad" : d.summary.programs_amber ? "warn" : "ok")}
      ${dlKpi("Pedagogik yo'nalishlar", fmt(d.summary.pedagogical), "masofaviy talabasi bor", d.summary.pedagogical ? "bad" : "ok")}${dlKpi("Kunduzgisiz", fmt(d.summary.no_full_time), "masofaviy yo'nalish", d.summary.no_full_time ? "bad" : "ok")}
      ${dlKpi(`O'qituvchida > ${R.teacher}`, fmt(d.summary.teachers_red), `${fmt(d.summary.teachers_total)} o'qituvchidan · o'rtacha ${String(d.summary.ratio ?? "—").replace(".", ",")} talaba`, d.summary.teachers_red ? "bad" : "ok")}</div>
    <div class="card dl-card"><h3>Yo'nalishlar</h3>${dlTable([
      ["Yo'nalish", p => `<b>${esc(p.direction)}</b><small>${p.level === "magistr" ? "magistratura" : "bakalavr"} · kunduzgi ${fmt(p.full_time)}</small>`],
      ["Masofaviy", p => `${dlBar(Math.min(100, p.pct), yyCls[p.level_flag])}<small><b>${fmt(p.distance)}</b> / ${fmt(p.limit)} · ${String(p.pct).replace(".", ",")}%</small>`],
      ["Kvota", p => flag(p)],
      ["Boshqa", p => `${p.no_full_time ? dlChip("Kunduzgi shakl yo'q", "bad") : ""} ${p.pedagogical ? dlChip("Pedagogik — masofaviy taqiqlangan", "bad") : ""}
        ${d.can_programs ? `<button type="button" class="dl-link" data-ped="${esc(p.direction)}" data-lv="${esc(p.level)}" data-v="${p.pedagogical ? 0 : 1}">${p.pedagogical ? "pedagogik emas" : "pedagogik deb belgilash"}</button>` : ""}<small>${p.ped_src === "qo'lda" ? "qo'lda belgilangan" : "nomi bo'yicha avtomatik"}</small>`]],
      d.programs, {rowCls: p => p.level_flag === "red" || p.pedagogical || p.no_full_time ? "dl-row-bad" : ""})}</div>
    <div class="card dl-card"><h3>O'qituvchiga to'g'ri keladigan masofaviy talabalar</h3><p class="muted">${esc(d.basis)}</p>${dlTable([
      ["O'qituvchi", t => `<b>${esc(t.name)}</b><small>${esc(t.dept || "")}</small>`],
      ["Talabalar", t => `${dlBar(Math.min(100, 100 * t.n / t.limit), yyCls[t.level_flag])}<small><b>${fmt(t.n)}</b> / ${fmt(t.limit)}</small>`],
      ["", t => t.level_flag === "red" ? dlChip("Oshgan", "bad") : t.level_flag === "amber" ? dlChip("Yaqin", "warn") : ""]],
      d.teachers.filter(t => t.level_flag !== "ok").slice(0, 60), {empty: "Hamma o'qituvchida chegaradan kam"})}</div>`;
  box.querySelectorAll("[data-ped]").forEach(b => b.onclick = async () => {
    const r = await dlApi("/api/yuzma/programs", {direction: b.dataset.ped, level: b.dataset.lv, pedagogik: b.dataset.v === "1"});
    if (r) { toast("Saqlandi"); renderYuzma(); }
  });
}

/* ---------- «Masofaviy ta'lim → Umumiy» sahifasiga karta ---------- */
(function () {
  if (typeof dlOverview !== "function" || dlOverview._yy) return;
  const prev = dlOverview;
  dlOverview = async function (box) {
    await prev(box);
    if (typeof ME === "undefined" || !ME || !["masofaviy", "masofaviy_xodim", "rektor", "prorektor_oquv"].includes(ME.role_key)) return;
    let d; try { const r = await fetch("/api/yuzma/overview", {credentials: "same-origin"}); if (!r.ok) return; d = await r.json(); } catch (e) { return; }
    const c = d.counts;
    box.insertAdjacentHTML("afterbegin", `<div class="card dl-card yy-mcard"><div class="yy-mh"><h3>${ico("idcheck", 17)} Yuzma-yuz va huquqiy chegaralar</h3>
        <button type="button" class="btn sm ghost" data-yy>Ochish →</button></div>
      <div class="yy-mrow"><span>${dlChip(`Ro'yxatdan o'tgan ${fmt(c.otgan)} / ${fmt(c.majburiy)}`, "ok")}</span>
        ${c.muddati_otgan ? dlChip(`Muddat o'tgan: ${fmt(c.muddati_otgan)}`, "bad") : ""} ${dlChip(`Ozod (xorijiy): ${fmt(c.ozod)}`)}
        ${d.flags_open ? dlChip(`Umumiy akkaunt alomati: ${fmt(d.flags_open)}`, "warn") : ""}</div>
      ${d.limits ? yyLimitSummary(d.limits) : ""}</div>`);
    box.querySelector("[data-yy]")?.addEventListener("click", () => go("yuzma"));
  };
  dlOverview._yy = true;
})();
