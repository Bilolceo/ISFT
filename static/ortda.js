/* =====================================================================
   «Ortda qolganlar» (app/ortda.py, /api/ortda; manba — LRS: app/lrs.py) — masofaviy kurslarda ortda qolayotgan talabalar.
     Talabalar: taqvim bo'yicha kutilgan darslar va bajarilgani, kechikish, testdan qayta-qayta o'tolmaslik, faolsizlik; talaba darslari;
                amallar — tyutorga biriktirish (Topshiriqlar), eslatma (xabarlar navbati), «bog'lanildi».
     Kurslar:   voronka (darslar bo'yicha boshlagan / yakunlagan), o'rtacha ball, urinishlar.
     Savollar:  qiyinlik (p), farqlash (D), eng ko'p tanlangan noto'g'ri javob — Kurs muharriridagi blokka havola.
     Qoidalar:  chegaralar (bo'lim boshlig'i o'zgartiradi).
   Ruxsat va ko'lam serverda (rahbariyat va kafedraga — faqat jamlangan sonlar). Global: renderOrtda().
   Yordamchilar: app.js ($, esc, fmt, toast, locked, errCard, ico, ME, go) va masofaviy.js (dlApi, dlTable, dlModal, dlKpi, dlChip, dlBar, dlPct, dlD).
   ===================================================================== */
const OQ0 = {course: "", reason: "", level: "", group: 0, q: "", offset: 0};
const OQ = {meta: null, who: null, tab: "talabalar", f: {...OQ0}, qcourse: "", qlesson: "", ccourse: ""};
function orReset() { Object.assign(OQ, {meta: null, who: null, tab: "talabalar", f: {...OQ0}, qcourse: "", qlesson: "", ccourse: ""}); }
if (!document.querySelector('link[href="ortda.css"]')) document.head.insertAdjacentHTML("beforeend", '<link rel="stylesheet" href="ortda.css">');
if (!document.querySelector('link[href="masofaviy.css"]')) document.head.insertAdjacentHTML("beforeend", '<link rel="stylesheet" href="masofaviy.css">');
const OR_TABS = {talabalar: "Talabalar", kurslar: "Kurslar", savollar: "Savollar tahlili", qoidalar: "Qoidalar"};
const OR_LVL = {yuqori: ["Yuqori xavf", "bad"], orta: ["O'rta xavf", "warn"], past: ["Past", ""]};
const OR_ST = {boshlanmagan: "", jarayonda: "info", otmadi: "bad", yakunlandi: "ok", otdi: "ok"};
const OR_FLAG = {qiyin: ["Juda qiyin", "bad"], oson: ["Juda oson", ""], farqlamaydi: ["Farqlamaydi", "warn"], salbiy: ["Salbiy farqlash", "bad"], chalgituvchi: ["Kuchli chalg'ituvchi", "warn"]};
const orNum = v => v == null ? "—" : String(v).replace(".", ",");
const orAgo = d => d == null ? "faollik yo'q" : d === 0 ? "bugun" : `${d} kun oldin`;

async function renderOrtda(tab) {
  const v = $("#v-ortda");
  const who = typeof ME !== "undefined" ? ME : null;
  if (OQ.who !== who) { const t = tab || OQ.tab; orReset(); OQ.who = who; tab = t; }
  if (!OQ.meta) { const m = await dlApi("/api/ortda/meta"); if (OQ.who !== who) return; OQ.meta = m; }
  const M = OQ.meta;
  const tabs = Object.keys(OR_TABS).filter(t => t !== "talabalar" || M.caps.list).filter(t => t !== "savollar" || M.caps.questions);
  OQ.tab = tab && tabs.includes(tab) ? tab : tabs.includes(OQ.tab) ? OQ.tab : tabs[0];
  const demo = M.source !== "lrs";
  v.innerHTML = `<div class="dl-head"><div><h2>Ortda qolganlar</h2><span class="muted">${esc(M.scope)} · semestrning ${M.week}-haftasi · ${dlD(M.today)}</span></div>
      <div class="dl-acts">${!document.querySelector('#nav a[data-v="masofaviy"]')?.classList.contains("hidden") ? `<button type="button" class="btn sm ghost" data-dl>${ico("monitor", 15)} Masofaviy ta'lim</button>` : ""}</div></div>
    ${demo ? `<div class="dl-demo">${ico("info", 15)}<span><b>Namuna ma'lumot.</b> Statementlar sun'iy (NEXTID hozircha xAPI natijalarini yubormaydi). Haqiqiy natijalar ISFT Core LRS orqali
      to'g'ridan-to'g'ri ishga tushirilgan darslardan keladi${M.source === "mixed" ? " — ro'yxatda namuna va haqiqiy yozuvlar aralash" : ""}.</span></div>` : ""}
    <div class="dl-tabs" role="tablist">${tabs.map(t => `<button type="button" role="tab" aria-selected="${t === OQ.tab}" class="${t === OQ.tab ? "on" : ""}" data-t="${t}">${esc(OR_TABS[t])}</button>`).join("")}</div>
    <div id="orBox"><div class="dl-empty">Yuklanmoqda…</div></div>`;
  v.querySelectorAll(".dl-tabs [data-t]").forEach(b => b.onclick = () => renderOrtda(b.dataset.t));
  v.querySelector("[data-dl]")?.addEventListener("click", () => go("masofaviy"));
  const box = $("#orBox");
  try {
    await ({talabalar: orStudents, kurslar: orCourses, savollar: orQuestions, qoidalar: orRules})[OQ.tab](box);
  } catch (e) {
    if (e?.message === "auth") return;
    box.innerHTML = e?.message === "denied" ? locked("Bu bo'lim") : `<div class="card dl-card"><p>${esc(e?.msg || "Ma'lumotni yuklab bo'lmadi")}</p></div>`;
  }
}
function orCourseOpts(sel, all = "Barcha kurslar") {
  return `<option value="">${esc(all)}</option>` + OQ.meta.courses.map(c => `<option value="${esc(c.ref)}" ${c.ref === sel ? "selected" : ""}>${esc(c.title)} — ${esc(c.sub)}</option>`).join("");
}
const orReasons = rs => rs.map(x => dlChip(x.label, x.sev >= 3 ? "bad" : "warn")).join(" ");

/* ---------- Talabalar ---------- */
async function orStudents(box) {
  const M = OQ.meta, F = OQ.f;
  const qs = new URLSearchParams({course: F.course, reason: F.reason, level: F.level, group: F.group || 0, q: F.q, offset: F.offset, limit: 50});
  const [sm, d] = await Promise.all([dlApi("/api/ortda/summary?" + new URLSearchParams({course: F.course})), dlApi("/api/ortda/list?" + qs)]);
  const rc = Object.fromEntries(sm.reasons.map(r => [r.code, r.n]));
  box.innerHTML = `<div class="dl-kpis or-kpis">
      ${dlKpi("Kuzatuvda", fmt(sm.students), "kurs × talaba (faol)")}
      ${dlKpi("Ortda qolgan", fmt(sm.at_risk), `${dlPct(sm.students ? +(100 * sm.at_risk / sm.students).toFixed(1) : 0)} · kamida bitta sabab`, sm.at_risk ? "warn" : "ok")}
      ${dlKpi("Yuqori xavf", fmt(sm.high), "bir nechta sabab yoki katta kechikish", sm.high ? "bad" : "ok")}
      ${Object.entries(M.reasons).map(([k, l]) => `<button type="button" class="dl-kpi or-rk ${F.reason === k ? "on" : ""}" data-rs="${k}"><span>${esc(l)}</span><b>${fmt(rc[k] || 0)}</b><small>${F.reason === k ? "filtr yoqilgan — bekor qilish" : "filtrlash"}</small></button>`).join("")}
    </div>
    <div class="dl-filters">
      <select id="orC" aria-label="Kurs">${orCourseOpts(F.course)}</select>
      <select id="orL" aria-label="Xavf darajasi"><option value="">Barcha darajalar</option>${Object.entries(OR_LVL).filter(([k]) => k !== "past").map(([k, [l]]) => `<option value="${k}" ${F.level === k ? "selected" : ""}>${l}</option>`).join("")}</select>
      <select id="orG" aria-label="Guruh"><option value="0">Barcha guruhlar</option>${d.groups.map(g => `<option value="${g.id}" ${+F.group === g.id ? "selected" : ""}>${esc(g.name)}</option>`).join("")}</select>
      <input id="orQ" type="search" placeholder="${M.caps.hemis ? "Ism, guruh yoki HEMIS ID" : "Ism yoki guruh"}" value="${esc(F.q)}" aria-label="Qidiruv">
    </div>
    <div class="card dl-card"><p class="muted or-note">Kutilgan — taqvim bo'yicha shu kungacha tugatilishi kerak bo'lgan darslar (semestr boshidan haftasiga chiqarilgan darslar, joriy hafta hisobga olinmaydi).
      Saralash: xavf og'irligi, keyin kechikish. ${M.caps.aggregate_only ? "" : M.role === "oqituvchi" ? "Kontakt ma'lumotlari ko'rsatilmaydi." : ""}</p>
    ${dlTable([
      ["Talaba", r => `<button type="button" class="dl-link" data-st="${r.student_id}" data-c="${esc(r.course_ref)}">${esc(r.full_name)}</button><small>${esc(r.grp || "")}${r.hemis_id ? " · " + esc(r.hemis_id) : ""}</small>`],
      ["Kurs", r => `${esc(r.course)}<small>${esc(r.course_sub)}</small>`],
      ["Darslar", r => `${dlBar(r.expected ? 100 * r.done / r.expected : 100, r.lag >= 2 * M.policy.lag_lessons ? "bad" : r.lag >= M.policy.lag_lessons ? "warn" : "ok")}<small><b>${r.done}</b> / ${r.expected} kutilgan · jami ${r.lessons}${r.lag ? ` · <b class="dl-bad">−${r.lag}</b>` : ""}</small>`],
      ["Test", r => r.max_fails ? `<b class="${r.max_fails >= M.policy.fail_attempts ? "dl-bad" : ""}">${r.max_fails}×</b><small>${esc(r.fail_lesson || "")}</small>` : "—", "num"],
      ["Oxirgi faollik", r => `${orAgo(r.days_inactive)}<small>${r.last ? dlD(r.last) : ""}${r.time_min ? ` · ${fmt(r.time_min)} daq.` : ""}</small>`],
      ["Sabablar", r => `${r.level ? dlChip(OR_LVL[r.level][0], OR_LVL[r.level][1]) : ""} ${orReasons(r.reasons)}${orActs(r.actions)}`],
      ...(M.caps.remind || M.caps.assign ? [["", r => orRowBtns(r), "or-acts"]] : [])],
      d.items, {empty: "Ortda qolgan talaba yo'q — yoki filtr juda tor", rowCls: r => r.level === "yuqori" ? "dl-row-bad" : ""})}
    ${dlPager(d.total, F.offset, 50, o => { F.offset = o; renderOrtda("talabalar"); })}</div>`;
  const re = () => { F.offset = 0; renderOrtda("talabalar"); };
  $("#orC").onchange = e => { F.course = e.target.value; F.group = 0; re(); };
  $("#orL").onchange = e => { F.level = e.target.value; re(); };
  $("#orG").onchange = e => { F.group = +e.target.value; re(); };
  let t; $("#orQ").oninput = e => { clearTimeout(t); t = setTimeout(() => { F.q = e.target.value.trim(); re(); }, 350); };
  box.querySelectorAll("[data-rs]").forEach(b => b.onclick = () => { F.reason = F.reason === b.dataset.rs ? "" : b.dataset.rs; re(); });
  box.querySelectorAll("[data-st]").forEach(b => b.onclick = () => orStudent(+b.dataset.st, b.dataset.c));
  orBindActs(box, d.items);
}
function orActs(a) {
  if (!a || !Object.keys(a).length) return "";
  const L = {tyutor: "tyutorga biriktirilgan", eslatma: "eslatma yuborilgan", boglanildi: "bog'lanildi"};
  return `<div class="or-hist">${Object.entries(a).map(([k, x]) => `<span title="${esc(x.n)} marta">${esc(L[k] || k)} ${dlD(x.ts)}</span>`).join("")}</div>`;
}
function orRowBtns(r) {
  const M = OQ.meta, k = `data-sid="${r.student_id}" data-c="${esc(r.course_ref)}" data-n="${esc(r.full_name)}"`;
  return `<div class="or-btns">${M.caps.assign ? `<button type="button" class="btn sm" data-as ${k}>Tyutorga</button>` : ""}
    ${M.caps.remind ? `<button type="button" class="btn sm ghost" data-rm ${k}>Eslatma</button>` : ""}
    ${M.caps.contacted ? `<button type="button" class="btn sm ghost" data-ct ${k}>Bog'lanildi</button>` : ""}</div>`;
}
function orBindActs(root, items, after) {
  const done = () => after ? after() : renderOrtda(OQ.tab);
  root.querySelectorAll("[data-as]").forEach(b => b.onclick = () => orAssign(+b.dataset.sid, b.dataset.c, b.dataset.n, done));
  root.querySelectorAll("[data-rm]").forEach(b => b.onclick = () => dlModal(`Eslatma: ${b.dataset.n}`, `
      <p class="muted">Xabar Talabalar markazining chiqish navbatiga yoziladi (SMS / Telegram shlyuzi ulanganda yuboriladi). Bitta talabaga ${OQ.meta.policy.remind_cooldown_days} kunda
      bir marta; xabarda keyingi darsga shaxsiy havola bo'ladi (paket eksport qilingan bo'lsa).</p>
      <label>Kanal<select id="orCh">${Object.entries(OQ.meta.channels).map(([k, l]) => `<option value="${k}">${esc(l)}</option>`).join("")}</select></label>`,
    async m => {
      const r = await dlApi("/api/ortda/remind", {student_id: +b.dataset.sid, course_ref: b.dataset.c, channel: m.querySelector("#orCh").value});
      if (!r) return false;
      toast(`Eslatma navbatga yozildi (${r.channel})`); done(); return true;
    }, "Yuborish"));
  root.querySelectorAll("[data-ct]").forEach(b => b.onclick = () => dlModal(`Bog'lanildi: ${b.dataset.n}`, `
      <label>Izoh (ixtiyoriy)<textarea id="orNt" rows="3" maxlength="500" placeholder="Masalan: telefon orqali gaplashildi, kasal bo'lgan — hafta oxirigacha yetib oladi"></textarea></label>`,
    async m => {
      const r = await dlApi("/api/ortda/contacted", {student_id: +b.dataset.sid, course_ref: b.dataset.c, note: m.querySelector("#orNt").value});
      if (!r) return false;
      toast("Belgilandi"); done(); return true;
    }));
}
async function orAssign(sid, cref, name, done) {
  const d = await dlApi(`/api/ortda/student/${sid}?course=${encodeURIComponent(cref)}`);
  const tu = d.tutors || [];
  dlModal(`Tyutorga biriktirish: ${name}`, `
      <p class="muted">Tyutorga «Topshiriqlar» tizimida vazifa yaratiladi (muddat — 3 ish kuni) va «Mening vazifalarim»da chiqadi. Talaba tyutorning
      «Ortda qolganlar» ro'yxatiga ham qo'shiladi.</p>
      ${tu.length ? `<label>Tyutor<select id="orTu">${tu.map(t => `<option value="${t.id}">${esc(t.name)}${t.group_tutor ? " — guruh tyutori" : t.same_faculty ? " — fakultet tyutori" : ""}</option>`).join("")}</select></label>`
        : `<p class="dl-bad">Faol tyutor topilmadi.</p>`}
      <label>Izoh (ixtiyoriy)<textarea id="orAn" rows="3" maxlength="500"></textarea></label>`,
    tu.length ? async m => {
      const r = await dlApi("/api/ortda/assign", {student_id: sid, course_ref: cref, tutor_id: +m.querySelector("#orTu").value, note: m.querySelector("#orAn").value});
      if (!r) return false;
      toast(`Topshiriq #${r.task_id}: ${r.tutor}, muddat ${dlD(r.due)}`); done(); return true;
    } : null, "Biriktirish");
}
async function orStudent(sid, cref) {
  const d = await dlApi(`/api/ortda/student/${sid}?course=${encodeURIComponent(cref)}`);
  const M = OQ.meta, row = d.row || {};
  const cells = d.lessons.map(l => `<span class="or-cell ${OR_ST[l.status] || ""} ${l.released ? "" : "fut"}" title="${esc(l.code)} · ${esc(l.title)} · ${esc(l.status_label)}${l.week ? ` · ${l.week}-hafta` : ""}">${esc(l.code)}</span>`).join("");
  const bg = dlModal(`${d.student.full_name} — ${d.course.title}`, `
      <p class="muted">${esc(d.student.grp || "")}${d.student.hemis_id ? " · HEMIS " + esc(d.student.hemis_id) : ""} · ${esc(d.course.sub)}</p>
      ${row.reasons ? `<p>${orReasons(row.reasons) || dlChip("Xavf yo'q", "ok")} <span class="muted">${row.done}/${row.expected} kutilgan dars · oxirgi faollik ${row.last ? dlD(row.last) : "—"}</span></p>` : ""}
      <div class="or-grid" aria-label="Darslar holati">${cells}</div>
      <p class="tiny muted or-legend">${Object.entries({otdi: "o'tdi / yakunlandi", jarayonda: "jarayonda", otmadi: "testdan o'tmadi", boshlanmagan: "boshlanmagan"}).map(([k, l]) => `<span class="or-cell ${OR_ST[k]}"></span>${l}`).join(" ")} <span class="or-cell fut"></span>hali chiqarilmagan</p>
      ${dlTable([["Dars", l => `<b>${esc(l.code)}</b> ${esc(l.title)}${l.week ? `<small>${l.week}-hafta</small>` : ""}`], ["Holat", l => dlChip(l.status_label, OR_ST[l.status])],
                 ["Foiz", l => dlPct(l.pct), "num"], ["Ball", l => l.best == null ? "—" : orNum(l.best), "num"], ["Urinish", l => l.attempts ? `${l.attempts}${l.fails ? ` (${l.fails} ✗)` : ""}` : "—", "num"],
                 ["Vaqt", l => l.time_min ? `${l.time_min} daq.` : "—", "num"], ["Oxirgi", l => l.last ? dlD(l.last) : "—"],
                 ...(M.caps.launch ? [["", l => `<button type="button" class="btn sm ghost" data-ln="${esc(l.ref)}">Havola</button>`]] : [])],
                d.lessons.filter(l => l.status !== "boshlanmagan" || l.released))}
      ${d.actions.length ? `<h4>Amallar tarixi</h4><ul class="or-log">${d.actions.map(a => `<li>${dlD(a.ts)} ${esc(String(a.ts).slice(11, 16))} — <b>${esc({tyutor: "tyutorga biriktirildi", eslatma: "eslatma", boglanildi: "bog'lanildi"}[a.kind] || a.kind)}</b>
          · ${esc(a.user_name || "")}${a.note ? ` · ${esc(a.note)}` : ""}${a.task_id ? ` · topshiriq #${a.task_id}` : ""}</li>`).join("")}</ul>` : ""}
      <div id="orLink"></div>
      ${M.caps.remind || M.caps.assign ? orRowBtns({student_id: sid, course_ref: cref, full_name: d.student.full_name}) : ""}`, null, "", true);
  orBindActs(bg, [], () => { bg.remove(); renderOrtda(OQ.tab); });
  bg.querySelectorAll("[data-ln]").forEach(b => b.onclick = async () => {
    const r = await dlApi("/api/lrs/launch-link", {student_id: sid, course_ref: cref, lesson_ref: cref.startsWith("dl:") ? b.dataset.ln : ""});
    if (!r) return;
    bg.querySelector("#orLink").innerHTML = `<div class="or-linkbox"><b>Ishga tushirish havolasi</b> (talabaga shaxsiy; NEXTID'ga bog'liq emas; har ochilishda yangi xAPI tokeni beriladi)
      <input readonly value="${esc(r.absolute)}" aria-label="Havola"> ${r.note ? `<small class="dl-bad">${esc(r.note)}</small>` : `<a class="btn sm" href="${esc(r.url)}" target="_blank" rel="noopener">Ochish</a>`}</div>`;
    bg.querySelector("#orLink input").select();
  });
}

/* ---------- Kurslar ---------- */
async function orCourses(box) {
  const sm = await dlApi("/api/ortda/summary");
  box.innerHTML = `<div class="card dl-card"><h3>Kurslar bo'yicha</h3><p class="muted">Eng ko'p ortda qolganlar yuqorida. Kursni bosing — darslar bo'yicha voronka.</p>
    ${dlTable([["Kurs", r => `<button type="button" class="dl-link" data-cv="${esc(r.ref)}">${esc(r.title)}</button><small>${esc(r.sub)}</small>`],
               ["Talaba", r => fmt(r.students), "num"],
               ["Ortda", r => `${dlBar(r.risk_pct, r.risk_pct >= 30 ? "bad" : r.risk_pct >= 15 ? "warn" : "ok")}<small>${fmt(r.at_risk)} · ${dlPct(r.risk_pct)}${r.high ? ` · yuqori ${fmt(r.high)}` : ""}</small>`],
               ["O'rtacha bajarilgan", r => `${orNum(r.avg_done)} / ${r.expected}<small>jami ${r.lessons} dars</small>`, "num"],
               ["Sabablar", r => Object.entries(r.reasons).map(([k, n]) => dlChip(`${OQ.meta.reasons[k] || k}: ${n}`, k === "boshlamagan" || k === "ortda" ? "warn" : "")).join(" ")]],
              sm.courses, {empty: "LRS ma'lumoti bor kurs yo'q"})}</div><div id="orCv"></div>`;
  box.querySelectorAll("[data-cv]").forEach(b => b.onclick = () => { OQ.ccourse = b.dataset.cv; orCourse($("#orCv")); });
  if (OQ.ccourse || sm.courses.length) { OQ.ccourse = OQ.ccourse || sm.courses[0].ref; await orCourse($("#orCv")); }
}
async function orCourse(el) {
  const d = await dlApi("/api/ortda/course?ref=" + encodeURIComponent(OQ.ccourse));
  const mx = Math.max(1, d.enrolled);
  el.innerHTML = `<div class="card dl-card"><div class="dl-item-h"><div><h3>${esc(d.course.title)} <span class="muted">· ${esc(d.course.sub)}</span></h3>
      <p class="muted">${fmt(d.enrolled)} talaba · ${d.week}-hafta / ${d.weeks} · chiqarilgan ${d.released} dars, kutilgan ${d.expected} · o'rtacha bajarilgan ${orNum(d.avg_done)}
      · ortda ${fmt(d.at_risk)}${d.plan_demo ? " · dars rejasi — namuna" : ""}</p></div>
      ${d.can_questions ? `<button type="button" class="btn sm" data-qq="${esc(d.course.ref)}">Savollar tahlili →</button>` : ""}</div>
    <div class="or-funnel" role="table" aria-label="Darslar bo'yicha voronka">
      <div class="or-fr or-fh" role="row"><span>Dars</span><span>Boshlagan / yakunlagan</span><span class="num">Ball</span><span class="num">✗ urinish</span><span class="num">Daq.</span></div>
      ${d.lessons.map((l, i) => `<div class="or-fr ${i < d.expected ? "" : i < d.released ? "cur" : "fut"}" role="row"><span title="${esc(l.title)}"><b>${esc(l.code || l.lesson)}</b> ${esc(l.title)}</span>
        <span class="or-fb"><i class="s" style="width:${100 * l.started / mx}%"></i><i class="d" style="width:${100 * l.done / mx}%"></i><small>${fmt(l.started)} / ${fmt(l.done)}${l.started_pct != null ? ` · ${dlPct(l.done_pct)}` : ""}</small></span>
        <span class="num">${orNum(l.avg_score)}</span><span class="num">${fmt(l.fail_attempts)}</span><span class="num">${orNum(l.avg_min)}</span></div>`).join("")}
    </div><p class="tiny muted">Och chiziq — boshlaganlar, to'q — yakunlagan / o'tganlar. Kulrang qatorlar — hali chiqarilmagan darslar; sariq — joriy hafta darslari.</p></div>`;
  el.querySelector("[data-qq]")?.addEventListener("click", () => { OQ.qcourse = d.course.ref; OQ.qlesson = ""; renderOrtda("savollar"); });
}

/* ---------- Savollar ---------- */
async function orQuestions(box) {
  const M = OQ.meta;
  if (!OQ.qcourse) OQ.qcourse = M.default_q || M.courses[0]?.ref || "";
  if (!OQ.qcourse) { box.innerHTML = `<div class="dl-empty">LRS ma'lumoti bor kurs yo'q</div>`; return; }
  const d = await dlApi("/api/ortda/questions?" + new URLSearchParams({ref: OQ.qcourse, lesson: OQ.qlesson}));
  const lessons = [...new Map(d.items.map(x => [x.lesson, x.lesson_code + " — " + x.lesson_title])).entries()];
  box.innerHTML = `<div class="dl-filters"><select id="orQc" aria-label="Kurs">${orCourseOpts(OQ.qcourse, "Kursni tanlang").replace('<option value="">Kursni tanlang</option>', "")}</select>
      <select id="orQl" aria-label="Dars"><option value="">Barcha darslar</option>${lessons.map(([k, t]) => `<option value="${esc(k)}" ${k === OQ.qlesson ? "selected" : ""}>${esc(t)}</option>`).join("")}</select></div>
    <div class="card dl-card"><p class="muted or-note">${esc(d.note)}</p>
    ${dlTable([["Savol", x => `<b>${esc(x.name)}</b>${x.text ? `<small>${esc(x.text.slice(0, 160))}</small>` : ""}`], ["Dars", x => esc(x.lesson_code)],
               ["Javoblar", x => fmt(x.n), "num"],
               ["Xato", x => x.wrong_pct == null ? "—" : `<b class="${x.wrong_pct >= 60 ? "dl-bad" : ""}">${orNum(x.wrong_pct)}%</b><small>${x.wrong_pct >= 60 ? `bu savolni ${Math.round(x.wrong_pct)}% xato topyapti` : `p = ${orNum(x.p)}`}</small>`],
               ["Farqlash (D)", x => x.d == null ? "—" : orNum(x.d), "num"],
               ["Eng ko'p xato javob", x => x.top_wrong ? `${esc(x.top_wrong_text || x.top_wrong)}<small>${fmt(x.top_wrong_n)} ta · noto'g'rilarning ${dlPct(Math.round(100 * (x.wrong_share || 0)))}</small>` : "—"],
               ["Belgilar", x => x.flags.map(f => dlChip(...(OR_FLAG[f] || [f, ""]))).join(" ")],
               ["", x => x.link ? `<button type="button" class="btn sm ghost" data-ed='${esc(JSON.stringify(x.link))}'>${x.link.view === "kurs" ? "Muharrirda ochish" : "Dars tayyorlash"}</button>` : ""]],
              d.items, {empty: "Bu kursda javoblar yo'q", rowCls: x => (x.flags || []).includes("qiyin") ? "dl-row-bad" : ""})}
    ${d.total > d.items.length ? `<p class="tiny muted">Ko'rsatildi: ${d.items.length} / ${d.total}</p>` : ""}</div>`;
  $("#orQc").onchange = e => { OQ.qcourse = e.target.value; OQ.qlesson = ""; renderOrtda("savollar"); };
  $("#orQl").onchange = e => { OQ.qlesson = e.target.value; renderOrtda("savollar"); };
  box.querySelectorAll("[data-ed]").forEach(b => b.onclick = () => {
    const l = JSON.parse(b.dataset.ed);
    if (l.view === "kurs") go("kurs", {cid: l.cid, lid: l.lid, block: l.block});
    else if (l.view === "paket" && typeof PK !== "undefined") { PK.cid = l.cid; PK.topic = l.no; go("paket", {tab: "mavzular"}); }
  });
}

/* ---------- Qoidalar ---------- */
async function orRules(box) {
  const M = OQ.meta, P = M.policy;
  box.innerHTML = `<div class="card dl-card"><h3>Qoidalar va chegaralar</h3>
      <p class="muted">Har bir sabab alohida ko'rsatiladi; og'irliklar yig'indisi ≥ 4 — yuqori xavf, 2–3 — o'rta. ${M.caps.policy ? "Chegaralarni siz o'zgartira olasiz (audit jurnaliga yoziladi)." : "Chegaralarni Masofaviy ta'lim bo'limi boshlig'i o'zgartiradi."}</p>
      <form id="orPol" class="dl-pol">${M.policy_meta.map(p => `<label>${esc(p.label)}<input type="number" name="${p.k}" min="${p.min}" max="${p.max}" value="${P[p.k]}" ${M.caps.policy ? "" : "disabled"}></label>`).join("")}
      ${M.caps.policy ? `<div class="dl-acts"><button class="btn primary" type="submit">Saqlash</button></div>` : ""}</form></div>
    <div class="card dl-card"><h3>Ma'lumot qayerdan keladi</h3>
      <ul class="or-log"><li><b>ISFT Core LRS</b> (/xapi) — darslar talabaga shaxsiy havola orqali ochilganda (NEXTID'ga bog'liq emas) pleyer xAPI statementlarini yuboradi:
        boshlash, progress, har bir savol javobi, test natijasi (ball), yakunlash, to'xtatish va sarflangan vaqt.</li>
        <li><b>NEXTID.LMS</b> hozircha xAPI launch parametrlarini bermaydi — natijalar yo'qoladi. NextBrain'ga so'rov: docs/nextid_xapi_sorov.md.</li>
        <li>Kutilgan progress: semestr boshidan har hafta teng miqdorda dars chiqariladi (${P.weeks} hafta), joriy ${P.grace_weeks} hafta darslari hali talab qilinmaydi.</li></ul></div>`;
  const f = $("#orPol");
  if (M.caps.policy) f.onsubmit = async e => {
    e.preventDefault();
    const body = Object.fromEntries([...f.querySelectorAll("input")].map(i => [i.name, +i.value]));
    const r = await dlApi("/api/ortda/policy", body);
    if (r) { OQ.meta.policy = r.policy; toast("Chegaralar saqlandi"); }
  };
}

/* ---------- navigatsiya: go("ortda", {course, tab}) (app.js go() xaritasiga tegmasdan) ---------- */
(function () {
  if (typeof go !== "function" || go._or) return;
  const prev = go;
  go = function (v, opts) {
    prev(v, opts);
    if (v !== "ortda") return;
    if (opts && typeof opts === "object" && opts.course) { OQ.f = {...OQ0, course: opts.course}; }
    const tab = opts && typeof opts === "object" ? opts.tab : undefined;
    Promise.resolve().then(() => renderOrtda(tab)).catch(e => { if (e?.message === "auth") return; $("#v-ortda").innerHTML = e?.message === "denied" ? locked("Bu bo'lim") : errCard("ortda"); });
  };
  go._or = true;
})();
(function () {
  if (typeof showLogin !== "function" || showLogin._or) return;
  const prev = showLogin;
  showLogin = function (...a) { orReset(); return prev.apply(this, a); };
  showLogin._or = true;
})();
