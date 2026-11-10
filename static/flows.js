/* =====================================================================
   «Talaba harakati» — akademik oqimlar (app/academic_flows.py, /api/flows).
     Sessiya va jadval · Apellyatsiya · Qayta o'qish · Ko'chirish / tiklash · ISFT granti · Bitiruv.
   Ruxsat va ko'lam serverda tekshiriladi (lavozimga qarab bo'limlar va amallar); bu yerda faqat ko'rinish.
   Global: renderFlows() — app.js go() chaqiradi. app.js yordamchilari: $, esc, fmt, toast, locked, errCard, showLogin, ME.
   ===================================================================== */
const FL = {meta: null, tab: null, sess: null, sq: "", sdate: "", ap: "ochiq", rs: "kutilmoqda", tr: "", gr: 0, bv: "", bq: "", boff: 0, sel: new Set()};
if (!document.querySelector('link[href="flows.css"]')) document.head.insertAdjacentHTML("beforeend", '<link rel="stylesheet" href="flows.css">');
const FL_AGG = "Rahbariyat uchun jamlangan ko'rinish: ko'rsatkichlar yuqorida, talabalar ism-shariflari ko'rsatilmaydi. Tasdiqlash — ISFT granti bo'limida, buyruqlar — «Buyruqlar»da.";
const flN = n => n == null ? "—" : fmt(n);
const flSum = n => n == null ? "—" : fmt(Math.round(n)) + " so'm";
const flD = s => { s = String(s || "").slice(0, 10); return s.length === 10 ? `${s.slice(8, 10)}.${s.slice(5, 7)}.${s.slice(0, 4)}` : "—"; };
const flShort = n => { n = String(n || ""); return n.includes(":") ? n.split(":").slice(1).join(":").trim() : n; };
const flChip = (t, cls = "") => `<span class="fl-chip ${cls}">${esc(t)}</span>`;
async function flApi(url, body) {
  const r = await fetch(url, {method: body === undefined ? "GET" : "POST", credentials: "same-origin", headers: {"Content-Type": "application/json"},
                              body: body === undefined ? undefined : JSON.stringify(body)});
  if (r.status === 401) { showLogin(); throw new Error("auth"); }
  const d = await r.json().catch(() => ({}));
  if (!r.ok) {
    const det = d.detail; const m = d.message || (typeof det === "string" ? det : det?.message) || "Xatolik yuz berdi";
    if (body !== undefined) { toast(m); return null; }
    const e = new Error(r.status === 403 ? "denied" : "api"); e.msg = m; throw e;
  }
  return d;
}
const flQs = o => new URLSearchParams(Object.entries(o).filter(([, v]) => v !== "" && v != null && v !== 0)).toString();
/* jadval: telefonda (≤600px) qatorlar kartochkaga aylanadi — sahifa gorizontal aylanmaydi */
function flTable(cols, rows, {rowCls = () => "", empty = "Ma'lumot yo'q"} = {}) {
  if (!rows.length) return `<div class="fl-empty">${esc(empty)}</div>`;
  return `<div class="tw"><table class="fl-t stack"><thead><tr>${cols.map(c => `<th>${esc(c[0])}</th>`).join("")}</tr></thead><tbody>` +
    rows.map(r => `<tr class="${rowCls(r)}">${cols.map(c => `<td data-l="${esc(c[0])}" class="${c[2] || ""}"><div class="fl-c">${c[1](r) ?? ""}</div></td>`).join("")}</tr>`).join("") + `</tbody></table></div>`;
}
const flKpi = (label, val, sub = "", cls = "") => `<div class="fl-kpi ${cls}"><span>${esc(label)}</span><b>${val}</b>${sub ? `<small>${sub}</small>` : ""}</div>`;
function flSeg(opts, cur, attr) {
  return `<div class="fl-seg" role="tablist">${opts.map(([k, t]) => `<button type="button" data-${attr}="${esc(k)}" class="${k === cur ? "on" : ""}" aria-selected="${k === cur}">${esc(t)}</button>`).join("")}</div>`;
}
/* oddiy modal: html — maydonlar; onOk(root) → true bo'lsa yopiladi */
function flModal(title, html, onOk, okText = "Saqlash") {
  const bg = document.createElement("div"); bg.className = "fl-modal-bg";
  bg.innerHTML = `<div class="fl-modal" role="dialog" aria-modal="true" aria-label="${esc(title)}"><h3>${esc(title)}</h3>${html}
    <div class="fl-acts"><button type="button" class="btn ghost" data-x>Bekor qilish</button>${onOk ? `<button type="button" class="btn primary" data-ok>${esc(okText)}</button>` : ""}</div></div>`;
  document.body.appendChild(bg);
  const close = () => bg.remove();
  bg.addEventListener("click", e => { if (e.target === bg || e.target.closest("[data-x]")) close(); });
  bg.addEventListener("keydown", e => { if (e.key === "Escape") close(); });
  const ok = bg.querySelector("[data-ok]");
  if (ok) ok.onclick = async () => { ok.disabled = true; try { if (await onOk(bg)) close(); } finally { ok.disabled = false; } };
  setTimeout(() => bg.querySelector("input,select,textarea,button")?.focus(), 30);
  return bg;
}
/* qidiruv bilan tanlash (talaba / guruh / o'qituvchi) */
function flPicker(root, inputSel, listSel, url, label, onPick) {
  const inp = root.querySelector(inputSel), list = root.querySelector(listSel); let t = null;
  inp.addEventListener("input", () => { clearTimeout(t); t = setTimeout(async () => {
    const q = inp.value.trim(); if (q.length < 2) { list.innerHTML = ""; return; }
    const rs = await flApi(url(q)).catch(() => []);
    list.innerHTML = rs.map((r, i) => `<button type="button" data-i="${i}">${label(r)}</button>`).join("") || `<small class="muted">Topilmadi</small>`;
    list.querySelectorAll("button").forEach(b => b.onclick = () => { list.querySelectorAll("button").forEach(x => x.classList.remove("on")); b.classList.add("on"); onPick(rs[+b.dataset.i]); });
  }, 250); });
}
const flStudentLabel = s => `${esc(s.full_name)} <small class="muted">${esc(s.grp || "")} · ${esc(s.study_form || "")} · ${esc(s.hemis_id || "")}</small>`;

/* ---------- asosiy ko'rinish ---------- */
async function renderFlows() {
  const el = $("#v-flows");
  if (!el.innerHTML) el.innerHTML = `<p class="muted">Yuklanmoqda…</p>`;
  FL.meta = await flApi("/api/flows/meta");
  if (!FL.tab || !FL.meta.tabs.some(t => t.key === FL.tab)) FL.tab = FL.meta.tabs[0].key;
  el.innerHTML = `<div class="fl-head"><div><h2>Akademik jarayonlar</h2><span class="muted">${esc(FL.meta.mode_note)} · ${esc(FL.meta.scope)}. Buyruq talab qiladigan har bir qaror
      Registrator ofisi orqali «Buyruqlar» bo'limiga loyiha sifatida tushadi va Rektor imzosidan keyin bazaga o'tadi.</span></div></div>
    <div class="fl-tabs" role="tablist">${FL.meta.tabs.map(t => `<button type="button" role="tab" data-tab="${t.key}" class="${t.key === FL.tab ? "on" : ""}" aria-selected="${t.key === FL.tab}">${esc(t.title)}${t.count ? ` <span class="n">${fmt(t.count)}</span>` : ""}</button>`).join("")}</div>
    <div id="flBody"><p class="muted">Yuklanmoqda…</p></div>`;
  el.querySelectorAll("[data-tab]").forEach(b => b.onclick = () => { FL.tab = b.dataset.tab; FL.sess = null; renderFlows(); });
  await flTab();
}
async function flTab() {
  const box = $("#flBody");
  try { await ({sessiya: flSessions, apellyatsiya: flAppeals, qayta: flRestudy, kochirish: flTransfers, grant: flGrant, bitiruv: flGrad})[FL.tab](box); }
  catch (e) { if (e?.message === "auth") return; box.innerHTML = e?.message === "denied" ? locked("Bu bo'lim") : `<div class="card fl-card"><p>${esc(e?.msg || "Ma'lumotni yuklab bo'lmadi")}</p></div>`; }
}

/* =================== 1. Sessiya va jadval =================== */
async function flSessions(box) {
  const d = await flApi("/api/flows/sessions"), caps = FL.meta.caps;
  if (!FL.sess && d.items.length) FL.sess = (d.items.find(s => s.status === "e'lon qilingan" && s.phase !== "yakunlangan") || d.items[0]).id;
  const cur = d.items.find(s => s.id === FL.sess);
  const phase = s => s.phase === "davom etmoqda" ? flChip("davom etmoqda", "info") : s.phase === "yakunlangan" ? flChip("yakunlangan") : flChip("kutilmoqda");
  box.innerHTML = `<div class="fl-bar"><span class="grow muted">Sessiyalar ta'lim shakli bo'yicha: kunduzgi va masofaviy — qishki/yozgi, sirtqi — qishki/yozgi o'quv-imtihon sessiyalari.
      Jadvalni ${caps.session_edit ? "siz" : "Akademik faoliyatni boshqarish bo'limi (sirtqi — Sirtqi bo'lim)"} tuzadi va e'lon qiladi.</span>
      ${caps.session_edit ? `<button class="btn sm primary" id="flNewS" type="button">Yangi sessiya</button>` : ""}</div>
    <div class="fl-sessions">${d.items.map(s => `<button type="button" class="fl-sess ${s.id === FL.sess ? "on" : ""}" data-s="${s.id}">
      <b>${esc(s.name)}</b><small>${flD(s.start)} — ${flD(s.end)} · ${esc(s.form_name)}</small>
      <span class="fl-meta">${flChip(s.status_name, s.status === "e'lon qilingan" ? "ok" : s.status === "loyiha" ? "warn" : "")}${s.status === "yakunlangan" ? "" : phase(s)}
      ${s.slots ? flChip(`${fmt(s.slots)} ta imtihon · ${fmt(s.groups)} guruh`) : ""}${s.conflicts ? flChip(`${s.conflicts} ta to'qnashuv`, "bad") : ""}</span>
      ${s.windows.map(w => `<small>${esc(w.name)}: ${flD(w.start)} — ${flD(w.end)}</small>`).join("")}</button>`).join("")}</div>
    <div id="flSessBody"></div>`;
  box.querySelectorAll("[data-s]").forEach(b => b.onclick = () => { FL.sess = +b.dataset.s; FL.sq = ""; FL.sdate = ""; flSessions(box); });
  const nb = $("#flNewS"); if (nb) nb.onclick = () => flNewSession(d);
  if (cur) await flSessionDetail($("#flSessBody"), cur);
}
async function flSessionDetail(box, s) {
  const d = await flApi(`/api/flows/sessions/${s.id}?` + flQs({q: FL.sq, date: FL.sdate, limit: 300})), S = d.session, ed = S.can_edit;
  box.innerHTML = `<div class="card fl-card"><div class="fl-item-h"><div><h3>${esc(S.name)}</h3><p class="muted" style="margin:0">${fmt(d.total)} ta yozuv · ${d.days.length} kun ·
      ${S.published_at ? "e'lon qilingan " + flD(S.published_at) : "hali e'lon qilinmagan"}</p></div>
      <div class="fl-acts" style="margin:0"><a class="btn sm" href="/api/flows/sessions/${S.id}/export" download>Excel (.xlsx)</a>
      ${ed ? `<button class="btn sm" type="button" id="flGen">Avtomatik tuzish</button><button class="btn sm" type="button" id="flAdd">Yozuv qo'shish</button>
             <button class="btn sm" type="button" id="flWin">Qayta topshirish muddati</button>
             ${S.status !== "e'lon qilingan" ? `<button class="btn sm primary" type="button" id="flPub">E'lon qilish</button>` : ""}` : ""}</div></div>
    ${d.conflicts.length ? `<div class="fl-item" style="margin:12px 0;border-color:var(--bad)"><b>To'qnashuvlar: ${d.conflicts.length} ta</b>${d.conflicts.slice(0, 8).map(x => `<p>${esc(x.text)}</p>`).join("")}
      <p class="muted">Xona, guruh yoki imtihon oluvchi bir vaqtda ikki joyda — jadval e'lon qilinmaydi.</p></div>` : `<p class="fl-note">To'qnashuv tekshiruvi: xona, guruh va imtihon oluvchi bo'yicha — muammo yo'q.</p>`}
    <div class="fl-bar" style="margin-top:12px"><input type="search" id="flSq" placeholder="Guruh, fan, xona yoki imtihon oluvchi" value="${esc(FL.sq)}" aria-label="Jadvalda qidirish">
      <select class="fl-in" id="flSd" aria-label="Sana"><option value="">Barcha kunlar</option>${d.days.map(x => `<option value="${x}" ${x === FL.sdate ? "selected" : ""}>${flD(x)}</option>`).join("")}</select></div>
    ${flTable([["Sana", r => `<b>${flD(r.exam_date)}</b><small>${esc(r.start_time)}–${esc(r.end_time)}</small>`, "num"],
               ["Guruh", r => `${esc(r.grp)}<small>${fmt(r.n)} talaba</small>`], ["Fan", r => esc(r.subject)],
               ["Xona", r => `${esc(r.room || "—")}${r.capacity ? `<small>${r.capacity} o'rin</small>` : ""}`],
               ["Imtihon oluvchi", r => `${esc(flShort(r.examiner) || "—")}<small>${esc(r.kafedra || "")}</small>`],
               ...(ed ? [["", r => `<button class="btn sm ghost" type="button" data-del="${r.id}" aria-label="O'chirish">O'chirish</button>`]] : [])],
              d.items, {rowCls: r => r.conflict ? "fl-bad" : "", empty: "Jadvalda yozuv yo'q"})}
    ${d.total > d.items.length ? `<p class="fl-note">Birinchi ${d.items.length} ta ko'rsatildi — sana yoki qidiruv bilan toraytiring, to'liq jadval — Excel'da.</p>` : ""}</div>`;
  let t; $("#flSq").oninput = e => { clearTimeout(t); t = setTimeout(() => { FL.sq = e.target.value.trim(); flSessionDetail(box, s); }, 300); };
  $("#flSd").onchange = e => { FL.sdate = e.target.value; flSessionDetail(box, s); };
  box.querySelectorAll("[data-del]").forEach(b => b.onclick = async () => { if (await flApi(`/api/flows/slots/${b.dataset.del}/delete`, {})) flSessions($("#flBody")); });
  if (!ed) return;
  $("#flGen").onclick = async () => { const r = await flApi(`/api/flows/sessions/${S.id}/generate`, {}); if (r) { toast(`Jadval tuzildi: ${r.slots} ta imtihon, ${r.groups} guruh` + (r.skipped ? ` · ${r.skipped} ta joylashmadi` : "")); flSessions($("#flBody")); } };
  const pub = $("#flPub"); if (pub) pub.onclick = async () => { if (await flApi(`/api/flows/sessions/${S.id}/publish`, {})) { toast("Jadval e'lon qilindi"); flSessions($("#flBody")); } };
  $("#flWin").onclick = () => flModal("Qayta topshirish muddati", `<label>Nomi<input id="w1" value="Qayta topshirish"></label>
      <div class="row2"><label>Boshlanish<input id="w2" type="date"></label><label>Tugash<input id="w3" type="date"></label></div>`,
    async m => !!(await flApi(`/api/flows/sessions/${S.id}/windows`, {name: m.querySelector("#w1").value, start: m.querySelector("#w2").value, end: m.querySelector("#w3").value})) && (flSessions($("#flBody")), true));
  $("#flAdd").onclick = () => flAddSlot(S);
}
async function flAddSlot(S) {
  const rooms = await flApi("/api/flows/lookup/rooms"); let g = null, t = null;
  const m = flModal("Jadvalga yozuv", `<label>Guruh<input id="a1" placeholder="Guruh nomi (kamida 2 belgi)" autocomplete="off"><div class="fl-pick" id="a1l"></div></label>
    <label>Fan<input id="a2" placeholder="Fan nomi"></label>
    <div class="row2"><label>Sana<input id="a3" type="date" min="${S.start}" max="${S.end}" value="${S.start}"></label>
      <label>Vaqt<select id="a4">${[["09:00", "11:00"], ["11:30", "13:30"], ["14:30", "16:30"]].map(([a, b]) => `<option value="${a}|${b}">${a}–${b}</option>`).join("")}</select></label></div>
    <label>Xona<select id="a5"><option value="">—</option>${rooms.map(r => `<option value="${r.id}">${esc(r.name)} · ${r.capacity} o'rin</option>`).join("")}</select></label>
    <label>Imtihon oluvchi<input id="a6" placeholder="O'qituvchi F.I.Sh." autocomplete="off"><div class="fl-pick" id="a6l"></div></label>`, async m => {
      const [st, en] = m.querySelector("#a4").value.split("|");
      const r = await flApi(`/api/flows/sessions/${S.id}/slots`, {group_id: g?.id || 0, subject: m.querySelector("#a2").value, exam_date: m.querySelector("#a3").value,
        start_time: st, end_time: en, room_id: +m.querySelector("#a5").value || null, examiner_id: t?.id || null});
      if (r) { toast("Yozuv qo'shildi"); flSessions($("#flBody")); } return !!r;
    });
  flPicker(m, "#a1", "#a1l", q => `/api/flows/lookup/groups?` + flQs({q, form: S.study_form}), x => `${esc(x.name)} <small class="muted">${esc(x.direction)} · ${x.course}-kurs</small>`, x => g = x);
  flPicker(m, "#a6", "#a6l", q => `/api/flows/lookup/teachers?q=${encodeURIComponent(q)}`, x => `${esc(flShort(x.full_name))} <small class="muted">${esc(x.kafedra || "")}</small>`, x => t = x);
}
function flNewSession(d) {
  const sir = ME.role_key === "sirtqi";
  flModal("Yangi sessiya", `<label>Ta'lim shakli<select id="n1">${Object.entries(d.forms).filter(([k]) => !sir || k === "sirtqi").map(([k, v]) => `<option value="${k}">${esc(v)}</option>`).join("")}</select></label>
    <label>Turi<select id="n2">${Object.entries(d.seasons).map(([k, v]) => `<option value="${k}">${esc(v)}</option>`).join("")}</select></label>
    <div class="row2"><label>Boshlanish<input id="n3" type="date"></label><label>Tugash<input id="n4" type="date"></label></div>
    <label>Nomi (ixtiyoriy)<input id="n5" placeholder="Avtomatik: semestr, sessiya turi va shakl"></label>`, async m => {
      const r = await flApi("/api/flows/sessions", {study_form: m.querySelector("#n1").value, season: m.querySelector("#n2").value, start: m.querySelector("#n3").value,
        end: m.querySelector("#n4").value, name: m.querySelector("#n5").value});
      if (r) { FL.sess = r.id; toast("Sessiya yaratildi — jadvalni tuzing"); flSessions($("#flBody")); } return !!r;
    });
}

/* =================== 2. Apellyatsiya =================== */
const FL_AP_ST = {yangi: ["Yangi", "warn"], "ko'rib chiqilmoqda": ["Ko'rib chiqilmoqda", "info"], qaror: ["Qaror chiqarilgan", "ok"]};
async function flAppeals(box) {
  const d = await flApi("/api/flows/appeals?" + flQs({status: FL.ap === "hammasi" ? "" : FL.ap})), caps = FL.meta.caps, c = d.counts;
  box.innerHTML = `<div class="fl-kpis">${flKpi("Yangi", flN(c["yangi"] || 0), "komissiya ovozi kutilmoqda", c["yangi"] ? "warn" : "")}
      ${flKpi("Ko'rib chiqilmoqda", flN(c["ko'rib chiqilmoqda"] || 0), `rais qarori ${d.rules.quorum} ta ovozdan keyin`)}
      ${flKpi("Qaror chiqarilgan", flN(c["qaror"] || 0), Object.entries(d.decisions).map(([k, n]) => `${esc(d.decision_names[k] || k)}: ${n}`).join(" · "))}
      ${flKpi("Muddat", `${d.rules.days} kun`, "natija e'lon qilingandan keyin")}</div>
    <div class="card fl-card"><div class="fl-bar">${flSeg([["ochiq", "Ochiq"], ["qaror", "Qaror chiqarilgan"], ["hammasi", "Hammasi"]], FL.ap, "ap")}<span class="grow"></span>
      ${caps.reg ? `<button class="btn sm primary" type="button" id="flNewAp">Apellyatsiya qabul qilish</button>` : ""}</div>
      <p class="muted">Komissiya: fan kafedrasi mudiri, Imtihon bo'limi va Akademik bo'lim (rais). Baho faqat baholar tarixiga «apellyatsiya» urinishi sifatida, sabab bilan yoziladi.</p>
      <div class="fl-list">${d.items.map(a => `<div class="fl-item"><div class="fl-item-h"><div><b>${esc(a.full_name)}</b> <small class="muted">${esc(a.grp || "")} · ${esc(a.hemis_id)}</small></div>
          ${flChip(...(FL_AP_ST[a.status] || [a.status, ""]))}</div>
        <p><b>${esc(a.subject)}</b> · ${esc(a.sem_label)} · ${esc(a.kafedra || "")} · imtihon oluvchi: ${esc(flShort(a.examiner) || "—")}</p>
        <p>Natija: ${a.score_old} ball (oraliq ${a.oraliq ?? "—"} + yakuniy ${a.yakuniy_old ?? "—"}) · e'lon ${flD(a.published_at)} · ariza ${flD(a.filed_at)} (muddat ${flD(a.deadline)}) · kanal: ${esc(a.channel)}</p>
        <p class="muted">Sabab: ${esc(a.reason)}</p>
        <div class="fl-votes">${Object.entries(d.members).map(([k, t]) => { const v = a.votes.find(x => x.member === k);
          return flChip(`${t}: ${v ? (d.decision_names[v.vote] ? v.vote : v.vote) + (v.yakuniy != null ? " → " + v.yakuniy : "") : "kutilmoqda"}`, v ? "info" : ""); }).join("")}</div>
        ${a.status === "qaror" ? `<p><b>${esc(a.decision_name)}</b>${a.decision !== "saqlash" ? `: ${a.score_old} → ${a.score_new} ball` : ""} · ${flD(a.decided_at)} · ${esc(a.decision_note || "")}</p>` : ""}
        ${a.can_vote || a.can_decide ? `<div class="fl-acts">${a.can_vote ? `<button class="btn sm" type="button" data-vote="${a.id}">Ovoz berish</button>` : ""}
          ${a.can_decide ? `<button class="btn sm primary" type="button" data-dec="${a.id}">Qaror chiqarish</button>` : ""}</div>` : ""}</div>`).join("") || `<div class="fl-empty">${d.aggregate ? FL_AGG : "Apellyatsiyalar yo'q"}</div>`}</div></div>`;
  box.querySelectorAll("[data-ap]").forEach(b => b.onclick = () => { FL.ap = b.dataset.ap; flAppeals(box); });
  const decForm = (a, title, url, key) => flModal(title, `<p class="muted">${esc(a.full_name)} · ${esc(a.subject)} · hozirgi yakuniy: ${a.yakuniy_old} / 70</p>
      <label>${key === "vote" ? "Ovoz" : "Qaror"}<select id="v1">${Object.entries(d.decision_names).map(([k, t]) => `<option value="${k}">${esc(t)}</option>`).join("")}</select></label>
      <label>Yangi yakuniy ball (oshirish / pasaytirish)<input id="v2" type="number" min="0" max="70"></label><label>${key === "vote" ? "Izoh" : "Qaror asosi"}<textarea id="v3"></textarea></label>`,
    async m => { const r = await flApi(url, {[key === "vote" ? "vote" : "decision"]: m.querySelector("#v1").value, yakuniy: m.querySelector("#v2").value === "" ? null : +m.querySelector("#v2").value,
      note: m.querySelector("#v3").value}); if (r) { toast(key === "vote" ? "Ovoz qayd etildi" : "Qaror chiqarildi"); renderFlows(); } return !!r; });
  box.querySelectorAll("[data-vote]").forEach(b => b.onclick = () => { const a = d.items.find(x => x.id === +b.dataset.vote); decForm(a, "Komissiya a'zosi ovozi", `/api/flows/appeals/${a.id}/vote`, "vote"); });
  box.querySelectorAll("[data-dec]").forEach(b => b.onclick = () => { const a = d.items.find(x => x.id === +b.dataset.dec); decForm(a, "Komissiya qarori", `/api/flows/appeals/${a.id}/decide`, "decide"); });
  const nb = $("#flNewAp"); if (nb) nb.onclick = () => {
    let st = null, opt = null;
    const m = flModal("Apellyatsiya arizasi", `<label>Talaba<input id="p1" placeholder="F.I.Sh. yoki HEMIS ID" autocomplete="off"><div class="fl-pick" id="p1l"></div></label>
      <label>Baho (muddat ichida e'lon qilinganlar)<div class="fl-pick" id="p2"><small class="muted">Avval talabani tanlang</small></div></label>
      <label>Sabab<textarea id="p3" placeholder="Talaba arizasidagi asos"></textarea></label>`, async m => {
        if (!st || !opt) { toast("Talaba va bahoni tanlang"); return false; }
        const r = await flApi("/api/flows/appeals", {student_id: st.id, subject: opt.subject, semester: opt.semester, reason: m.querySelector("#p3").value});
        if (r) { toast(`Apellyatsiya qabul qilindi · komissiyaga yuborildi`); renderFlows(); } return !!r; }, "Qabul qilish");
    flPicker(m, "#p1", "#p1l", q => `/api/flows/lookup/students?q=${encodeURIComponent(q)}`, flStudentLabel, async s => {
      st = s; opt = null; const os = await flApi(`/api/flows/appeals/options/${s.id}`); const box2 = m.querySelector("#p2");
      box2.innerHTML = os.map((o, i) => `<button type="button" data-i="${i}">${esc(o.subject)} · ${o.score} ball <small class="muted">${esc(o.sem_label)} · e'lon ${flD(o.published_at)} · muddat ${flD(o.deadline)}</small></button>`).join("")
        || `<small class="muted">Apellyatsiya muddati ichidagi natija yo'q (${FL.meta.rules.appeal_days} kun)</small>`;
      box2.querySelectorAll("button").forEach(b => b.onclick = () => { box2.querySelectorAll("button").forEach(x => x.classList.remove("on")); b.classList.add("on"); opt = os[+b.dataset.i]; });
    });
  };
}

/* =================== 3. Qayta o'qish =================== */
async function flRestudy(box) {
  const caps = FL.meta.caps, bux = caps.bux;
  if (bux && !["qayta_oqish", "muddati_otgan"].includes(FL.rs)) FL.rs = "qayta_oqish";
  const d = await flApi("/api/flows/restudy?" + flQs({view: FL.rs === "hammasi" ? "" : FL.rs})), s = d.summary;
  const exp = !bux && !caps.lead ? await flApi("/api/flows/restudy/expulsion").catch(() => ({items: []})) : {items: []};
  const views = bux ? [["qayta_oqish", "To'lov qatorlari"], ["muddati_otgan", "Muddati o'tgan"]]
    : [["kutilmoqda", "Qaror kutilmoqda"], ["muddati_otgan", "Muddati o'tgan"], ["qayta_oqish", "Qayta o'qish"], ["kursda_qoldirish", "Kursda qoldirish"], ["hammasi", "Hammasi"]];
  box.innerHTML = `<div class="fl-kpis">${bux ? flKpi("Hisoblangan", flSum(s.billed), "qayta o'qish to'lovlari") + flKpi("To'langan", flSum(s.paid), "", "ok") + flKpi("Qarz", flSum((s.billed || 0) - (s.paid || 0)), "", "warn")
      : flKpi("Qarzdor talabalar", flN(s.students), `${flN(s.n)} ta fan — qayta topshirishda ham o'tmagan`) + flKpi("Qaror kutilmoqda", flN(s.pending), `${d.rules.decision_days} kun ichida`, s.pending ? "warn" : "")
        + flKpi("Qayta o'qish", flN(s.restudy), `${flSum(s.billed)} hisoblangan`) + flKpi("Kursda qoldirish", flN(s.repeat_)) + flKpi("Chetlashtirish nomzodlari", flN(s.expel), "muddat o'tgan", s.expel ? "bad" : "")}</div>
    <div class="card fl-card"><div class="fl-bar">${flSeg(views, FL.rs, "rs")}</div>
      <p class="muted">${bux ? "Buxgalteriya: faqat to'lov qatorlari (baholarsiz). Narx: 1 kredit = yillik kontrakt / " + d.rules.credits_per_year + "."
        : `Baholar tarixida qayta topshirishda ham o'tmagan fan → talabaga to'lovli qayta o'qish (kredit × narx, Buxgalteriyaga qarz qatori) yoki kursda qoldirish taklif etiladi. Qaror — ${d.rules.decision_days} kun, to'lov — ${d.rules.pay_days} kun.`}</p>
      ${flTable([["Talaba", r => `<b>${esc(r.full_name)}</b><small>${esc(r.grp || "")} · ${esc(r.study_form)} · ${esc(r.payment_type || "")}</small>`],
                 ["Fan", r => `${esc(r.subject)}<small>${esc(r.sem_label)}${bux ? "" : ` · o'tmadi ${flD(r.failed_at)}`}</small>`],
                 ["Kredit / narx", r => `${r.credits} kr.<small>${flSum(r.per_credit)} / kredit</small>`, "num"],
                 ["Qaror", r => `${flChip(r.decision_name, r.overdue ? "bad" : r.decision === "kutilmoqda" ? "warn" : r.decision === "qayta_oqish" ? "info" : "")}<small>muddat ${flD(r.decision === "qayta_oqish" ? r.pay_due : r.deadline)}</small>`
                   + (r.order_reg || r.order_status ? `<small>buyruq: ${esc(r.order_reg || r.order_status)}</small>` : "")],
                 ["To'lov", r => r.decision === "qayta_oqish" ? `${flSum(r.paid)}<small>${flSum(r.amount)} dan</small>` : `<small>taklif: ${flSum(r.quote)}</small>`, "num"],
                 ["", r => (caps.reg && r.decision === "kutilmoqda" ? `<button class="btn sm" type="button" data-rd="${r.student_id}">Qaror</button>` : "")
                   + (bux && r.decision === "qayta_oqish" && r.paid < r.amount ? `<button class="btn sm" type="button" data-pay="${r.id}">To'lov</button>` : "")]],
                d.items, {rowCls: r => r.overdue ? "fl-bad" : "", empty: d.aggregate ? FL_AGG : "Bu ro'yxatda yozuv yo'q"})}</div>
    ${!bux && !caps.lead ? `<div class="card fl-card"><h3>Akademik qarzdorlik sababli chetlashtirish nomzodlari</h3>
      <p class="muted">Qaror muddati o'tgan, rad etgan yoki qayta o'qish to'lovini muddatida to'lamagan talabalar. Loyiha «Buyruqlar» bo'limiga «${esc("Chetlashtirish (akademik qarzdorlik)")}» turi bilan tushadi.</p>
      ${flTable([["", r => caps.reg ? `<input type="checkbox" data-ex="${r.id}" aria-label="Tanlash">` : ""], ["Talaba", r => `<b>${esc(r.full_name)}</b><small>${esc(r.grp || "")} · ${esc(r.hemis_id)}</small>`],
                 ["Fanlar", r => esc(r.subjects)], ["Sabab", r => `${esc(r.why)}<small>muddat ${flD(r.deadline)}</small>`]], exp.items, {empty: "Nomzod yo'q"})}
      ${caps.reg && exp.items.length ? `<div class="fl-acts"><button class="btn sm primary" type="button" id="flExp">Tanlanganlar uchun buyruq loyihasi</button></div>` : ""}</div>` : ""}`;
  box.querySelectorAll("[data-rs]").forEach(b => b.onclick = () => { FL.rs = b.dataset.rs; flRestudy(box); });
  box.querySelectorAll("[data-rd]").forEach(b => b.onclick = () => {
    const r = d.items.find(x => x.student_id === +b.dataset.rd), all = d.items.filter(x => x.student_id === r.student_id && x.decision === "kutilmoqda");
    flModal("Talaba qarori (ariza asosida)", `<p class="muted">${esc(r.full_name)} · ${all.map(x => esc(x.subject)).join(", ")} · jami ${all.reduce((a, x) => a + x.credits, 0)} kredit,
        ${flSum(all.reduce((a, x) => a + x.quote, 0))}</p>
      <label>Qaror<select id="q1"><option value="qayta_oqish">To'lovli qayta o'qish → Buxgalteriyaga qarz qatori</option><option value="kursda_qoldirish">Kursda qoldirish → buyruq loyihasi</option>
        <option value="rad">Rad etdi (chetlashtirish nomzodi)</option></select></label><label>Izoh<textarea id="q2"></textarea></label>`,
      async m => { const x = await flApi(`/api/flows/restudy/student/${r.student_id}/decide`, {decision: m.querySelector("#q1").value, note: m.querySelector("#q2").value});
        if (x) { toast(x.order_id ? `Buyruq loyihasi tuzildi (#${x.order_id})` : "Qaror qayd etildi"); renderFlows(); } return !!x; });
  });
  box.querySelectorAll("[data-pay]").forEach(b => b.onclick = () => { const r = d.items.find(x => x.id === +b.dataset.pay);
    flModal("To'lovni qayd etish", `<p class="muted">${esc(r.full_name)} · ${esc(r.subject)} · qoldiq ${flSum(r.amount - r.paid)}</p><label>Summa (so'm)<input id="y1" type="number" min="1" value="${r.amount - r.paid}"></label>`,
      async m => { const x = await flApi(`/api/flows/restudy/${r.id}/pay`, {amount: +m.querySelector("#y1").value}); if (x) { toast("To'lov qayd etildi"); flRestudy(box); } return !!x; }); });
  const eb = $("#flExp"); if (eb) eb.onclick = async () => { const ids = [...box.querySelectorAll("[data-ex]:checked")].map(x => +x.dataset.ex);
    if (!ids.length) return toast("Talabalarni tanlang");
    const r = await flApi("/api/flows/restudy/expulsion/order", {ids}); if (r) { toast(`Buyruq loyihasi #${r.order_id} tuzildi (${r.count} ta) — «Buyruqlar» bo'limida`); flRestudy(box); } };
}

/* =================== 4. Ko'chirish / tiklash =================== */
const FL_TR_ST = {"farq fanlari": ["Farq fanlari", "warn"], tayyor: ["Buyruqqa tayyor", "info"], buyruq: ["Buyruq loyihasi", "info"], yakunlangan: ["Yakunlangan", "ok"], rad: ["Rad etilgan", "bad"]};
async function flTransfers(box) {
  const d = await flApi("/api/flows/transfers?" + flQs({kind: FL.tr})), caps = FL.meta.caps, c = d.counts, canDiff = caps.akademik || caps.reg;
  box.innerHTML = `<div class="fl-kpis">${flKpi("Farq fanlari topshirilmoqda", flN(c["farq fanlari"] || 0), `muddat — buyruqdan ${d.deadline_days} kun`)}
      ${flKpi("Buyruqqa tayyor", flN(c["tayyor"] || 0))}${flKpi("Buyruq loyihasida", flN(c["buyruq"] || 0))}${flKpi("Yakunlangan", flN(c["yakunlangan"] || 0), "", "ok")}
      ${flKpi("Muddati o'tgan farq", flN(d.overdue), "", d.overdue ? "bad" : "")}</div>
    <div class="card fl-card"><div class="fl-bar">${flSeg([["", "Hammasi"], ...Object.entries(d.kinds)], FL.tr, "tr")}<span class="grow"></span>
      ${caps.reg ? `<button class="btn sm primary" type="button" id="flNewTr">Yangi ariza</button>` : ""}</div>
      <p class="muted">Farq fanlari maqsad guruh o'quv rejasidan (yo'nalish × daraja, o'tgan semestrlar) talaba o'zlashtirmagan fanlar sifatida hisoblanadi. Har bir ariza «Buyruqlar»dagi tegishli tur bilan yakunlanadi.</p>
      <div class="fl-list">${d.items.map(t => `<div class="fl-item"><div class="fl-item-h"><div><b>${esc(t.full_name || "—")}</b> <small class="muted">${esc(t.kind_name)}</small></div>
          ${flChip(...(FL_TR_ST[t.status] || [t.status, ""]))}</div>
        <p>${esc(t.from_desc || "")} → ${t.to_grp ? `<b>${esc(t.to_grp)}</b> · ${esc(t.to_dir || "")} · ${esc(t.to_form || "")} · ${t.to_course}-kurs` : `<b>${esc(t.other_otm || "")}</b>`}
          ${t.kind === "kirish" ? ` · avvalgi OTM: ${esc(t.other_otm || "")}` : ""}</p>
        ${t.reason ? `<p class="muted">${esc(t.reason)}</p>` : ""}
        ${t.diffs.length ? `<p>Farq fanlari: ${t.diffs.length} ta (${t.diffs.reduce((a, x) => a + (x.credits || 0), 0)} kredit), qolgan ${t.open} ta · muddat ${flD(t.deadline)} ${t.overdue ? flChip("muddat o'tdi", "bad") : ""}</p>
          ${flTable([["Fan", x => `${esc(x.subject)}<small>${x.sem_no}-semestr · ${x.credits} kr.</small>`], ["Holat", x => flChip(x.status === "topshirildi" ? `topshirildi · ${x.score}` : x.score != null ? `o'tmadi · ${x.score}` : "qarz", x.status === "topshirildi" ? "ok" : "warn")],
                     ...(canDiff && t.status !== "rad" ? [["", x => x.status !== "topshirildi" ? `<button class="btn sm ghost" type="button" data-df="${x.id}">Natija</button>` : ""]] : [])], t.diffs)}`
          : `<p class="muted">Farq fanlari yo'q</p>`}
        <div class="fl-acts">${t.order ? flChip(`Buyruq: ${t.order.reg_no || "#" + t.order.id} · ${t.order.status_name}`, t.order.status === "imzolangan" ? "ok" : "info") : ""}
          ${caps.reg && !t.order && ["tayyor", "farq fanlari"].includes(t.status) ? `<button class="btn sm primary" type="button" data-to="${t.id}">Buyruq loyihasi</button>` : ""}</div></div>`).join("")
        || `<div class="fl-empty">${d.aggregate ? FL_AGG : "Arizalar yo'q"}</div>`}</div></div>`;
  box.querySelectorAll("[data-tr]").forEach(b => b.onclick = () => { FL.tr = b.dataset.tr; flTransfers(box); });
  box.querySelectorAll("[data-to]").forEach(b => b.onclick = async () => { const r = await flApi(`/api/flows/transfers/${b.dataset.to}/order`, {});
    if (r) { toast(`Buyruq loyihasi #${r.order_id} tuzildi — «Buyruqlar» bo'limida`); flTransfers(box); } });
  box.querySelectorAll("[data-df]").forEach(b => b.onclick = () => flModal("Farq fani natijasi", `<label>Ball (0–100)<input id="f1" type="number" min="0" max="100"></label>`,
    async m => { const r = await flApi(`/api/flows/transfers/diff/${b.dataset.df}`, {score: +m.querySelector("#f1").value}); if (r) { toast(r.passed ? "Topshirildi" : "O'tmadi — qarz qoladi"); flTransfers(box); } return !!r; }));
  const nb = $("#flNewTr"); if (nb) nb.onclick = () => flNewTransfer(d);
}
function flNewTransfer(d) {
  let st = null, g = null;
  const need = {ichki: "faol", chiqish: "faol", tiklash: "chetlashtirilgan", tatildan_qaytish: "akademik ta'til"};
  const m = flModal("Ko'chirish / tiklash arizasi", `<label>Turi<select id="t0">${Object.entries(d.kinds).map(([k, v]) => `<option value="${k}">${esc(v)}</option>`).join("")}</select></label>
    <div id="tS"><label>Talaba<input id="t1" placeholder="F.I.Sh. yoki HEMIS ID" autocomplete="off"><div class="fl-pick" id="t1l"></div></label></div>
    <div id="tA" hidden><label>Arizachi F.I.Sh.<input id="t2"></label></div>
    <div id="tO" hidden><label id="tOl">OTM<input id="t3"></label></div>
    <div id="tG"><label>Maqsad guruh<input id="t4" placeholder="Guruh nomi yoki yo'nalish" autocomplete="off"><div class="fl-pick" id="t4l"></div></label></div>
    <div id="tP" hidden><label>Avvalgi OTMda o'zlashtirilgan fanlar (har qatorda bitta)<textarea id="t5"></textarea></label></div>
    <label>Asos / izoh<input id="t6"></label><p class="fl-note" id="tPrev"></p>`, async m => {
      const k = m.querySelector("#t0").value;
      const r = await flApi("/api/flows/transfers", {kind: k, student_id: st?.id || null, to_group_id: g?.id || null, applicant: m.querySelector("#t2").value,
        other_otm: m.querySelector("#t3").value, prior_subjects: m.querySelector("#t5").value.split("\n").map(x => x.trim()).filter(Boolean), reason: m.querySelector("#t6").value});
      if (r) { toast(`Ariza qabul qilindi · farq fanlari: ${r.diffs} ta`); renderFlows(); } return !!r; }, "Qabul qilish");
  const sync = () => { const k = m.querySelector("#t0").value; m.querySelector("#tS").hidden = k === "kirish"; m.querySelector("#tA").hidden = k !== "kirish";
    m.querySelector("#tO").hidden = !["kirish", "chiqish"].includes(k); m.querySelector("#tOl").firstChild.textContent = k === "kirish" ? "Avvalgi OTM" : "Qabul qiluvchi OTM";
    m.querySelector("#tG").hidden = k === "chiqish"; m.querySelector("#tP").hidden = k !== "kirish"; st = null; m.querySelector("#t1l").innerHTML = ""; m.querySelector("#t1").value = ""; };
  m.querySelector("#t0").onchange = sync; sync();
  const prev = async () => { if (!g) return; const p = await flApi(`/api/flows/transfers/preview?` + flQs({student_id: st?.id || 0, group_id: g.id})).catch(() => null);
    if (p) m.querySelector("#tPrev").textContent = `Farq fanlari (oldindan hisob): ${p.diffs.length} ta, ${p.credits} kredit` + (p.diffs.length ? " — " + p.diffs.slice(0, 6).map(x => x.subject).join(", ") + (p.diffs.length > 6 ? "…" : "") : ""); };
  flPicker(m, "#t1", "#t1l", q => `/api/flows/lookup/students?` + flQs({q, status: need[m.querySelector("#t0").value] || "faol"}), flStudentLabel, s => { st = s; prev(); });
  flPicker(m, "#t4", "#t4l", q => `/api/flows/lookup/groups?q=${encodeURIComponent(q)}`, x => `${esc(x.name)} <small class="muted">${esc(x.direction)} · ${esc(x.form)} · ${x.course}-kurs</small>`, x => { g = x; prev(); });
}

/* =================== 5. ISFT granti =================== */
async function flGrant(box) {
  const d = await flApi("/api/flows/grant"), R = d.round, caps = d.caps, bux = FL.meta.caps.bux;
  const lose = d.candidates.filter(x => x.kind === "mahrum"), award = d.candidates.filter(x => x.kind === "tavsiya");
  const tot = d.holders.reduce((a, x) => a + x.n, 0), soc = d.holders.reduce((a, x) => a + (x.social || 0), 0);
  const cand = (rows, title) => `<h3 style="margin-top:14px">${esc(title)} <small class="muted">(${rows.length})</small></h3>` + flTable([
      ["Talaba", x => `<b>${esc(x.full_name)}</b><small>${esc(x.grp || "")} · ${x.course}-kurs · ${esc(x.direction)}</small>`],
      ["Yillik GPA", x => `${x.gpa != null ? Number(x.gpa).toFixed(2) : "—"}<small>o'rt. ball ${x.avg_score ?? "—"}${x.debts ? ` · qarz ${x.debts}` : ""}</small>`, "num"],
      ["Asos", x => `${esc(x.reason)}${x.category === "ijtimoiy" ? "<small>ijtimoiy toifa</small>" : ""}`],
      ["Kontrakt", x => flSum(x.contract_amount), "num"],
      ["Qaror", x => R.status === "komissiya" && caps.decide ? `<select class="fl-in" data-gd="${x.id}" aria-label="Qaror"><option value="tasdiqlandi">Tasdiqlash</option><option value="rad">Rad etish</option></select>`
        : flChip(x.decision === "tasdiqlandi" ? "tasdiqlandi" : x.decision === "rad" ? "rad etildi" : "kutilmoqda", x.decision === "tasdiqlandi" ? "ok" : x.decision === "rad" ? "bad" : "warn")]], rows, {empty: "Nomzod yo'q"});
  box.innerHTML = `<div class="fl-kpis">${flKpi("ISFT granti egalari", flN(tot), `iqtidor ${flN(tot - soc)} · ijtimoiy ${flN(soc)}`)}
      ${flKpi("Yillik kvota", flN(d.quota.merit + d.quota.social), `${d.quota.merit} iqtidor + ${d.quota.social} ijtimoiy`)}
      ${R ? flKpi("Mahrum qilishga", flN(lose.length), "qarz yoki GPA past", lose.length ? "warn" : "") + flKpi("Grantga tavsiya", flN(award.length), "bo'shagan iqtidor o'rinlariga") : ""}
      ${d.finance ? flKpi("Kontrakt tushumi (+)", flSum(d.finance.revoke_income), "mahrum qilinganlar, yiliga") + flKpi("Kontrakt kamayishi (−)", flSum(d.finance.award_loss), "grantga o'tganlar") : ""}</div>
    <div class="card fl-card"><h3>ISFT granti — institutning o'z granti (davlat granti emas)</h3>
      <p class="muted">Yillik qayta reyting: kurs ichida, oxirgi o'quv yili (2 semestr) bo'yicha kredit bilan tortilgan GPA. Saqlab qolish: akademik qarz yo'q va GPA ≥ ${d.rules.gpa_min_merit}
        (ijtimoiy toifa — ≥ ${d.rules.gpa_min_social}). Bo'shagan iqtidor o'rinlari qarzsiz kontrakt talabalari reytingi bo'yicha to'ldiriladi; ijtimoiy o'rinlar — hujjatlar asosida komissiya.</p>
      ${flTable([["Kurs", x => `${x.course}-kurs`], ["Grant egalari", x => flN(x.n), "num"], ["shundan ijtimoiy", x => flN(x.social), "num"]], d.holders)}</div>
    ${R ? `<div class="card fl-card"><div class="fl-item-h"><div><h3>${esc(R.acad_year)} o'quv yili raundi</h3><p class="muted" style="margin:0">${flChip(R.status_name, R.status === "buyruq" ? "ok" : "warn")}
        ${R.params.social_vacancies ? ` · ijtimoiy toifadagi bo'sh o'rinlar: ${R.params.social_vacancies}` : ""}</p></div>
      <div class="fl-acts" style="margin:0">${caps.create && R.status === "loyiha" ? `<button class="btn sm primary" type="button" id="flGs">Komissiyaga yuborish</button>` : ""}
        ${caps.decide && R.status === "komissiya" ? `<button class="btn sm primary" type="button" id="flGd">Komissiya qarorini tasdiqlash</button>` : ""}
        ${caps.create && R.status === "tasdiqlangan" ? `<button class="btn sm primary" type="button" id="flGo">Buyruq loyihalarini tuzish</button>` : ""}
        ${(R.orders || []).map(o => flChip(`${o.kind_name}: ${o.reg_no || "#" + o.id} · ${o.status_name}`, o.status === "imzolangan" ? "ok" : "info")).join("")}</div></div>
      ${bux ? cand(d.candidates, "Tasdiqlangan o'zgarishlar (moliyaviy ro'yxat)") : cand(lose, "Grantdan mahrum qilish") + cand(award, "Grantga tavsiya")}</div>`
      : `<div class="card fl-card"><p class="muted">Grant raundi hali tuzilmagan.</p></div>`}
    ${caps.create && (!R || R.status === "buyruq") ? `<div class="fl-acts"><button class="btn sm" type="button" id="flGn">Yangi raund (nomzodlarni hisoblash)</button></div>` : ""}`;
  const on = (id, fn) => { const b = $(id); if (b) b.onclick = fn; };
  on("#flGs", async () => { if (await flApi(`/api/flows/grant/rounds/${R.id}/submit`, {})) { toast("Komissiyaga yuborildi"); renderFlows(); } });
  on("#flGn", async () => { const r = await flApi("/api/flows/grant/rounds", {}); if (r) { toast("Nomzodlar ro'yxati tuzildi"); renderFlows(); } });
  on("#flGo", async () => { const r = await flApi(`/api/flows/grant/rounds/${R.id}/orders`, {}); if (r) { toast("Buyruq loyihalari «Buyruqlar» bo'limida"); renderFlows(); } });
  on("#flGd", () => { const dec = Object.fromEntries([...box.querySelectorAll("[data-gd]")].map(s => [s.dataset.gd, s.value]));
    const rad = Object.values(dec).filter(v => v === "rad").length;
    flModal("Komissiya qarori", `<p class="muted">Tasdiqlanadi: ${Object.keys(dec).length - rad} ta · rad etiladi: ${rad} ta.</p><label>Bayonnoma / izoh<textarea id="g1"></textarea></label>`,
      async m => { const r = await flApi(`/api/flows/grant/rounds/${R.id}/decide`, {decisions: dec, note: m.querySelector("#g1").value}); if (r) { toast("Komissiya qarori tasdiqlandi"); renderFlows(); } return !!r; }, "Tasdiqlash"); });
}

/* =================== 6. Bitiruv =================== */
async function flGrad(box) {
  const d = await flApi("/api/flows/grad?" + flQs({view: FL.bv, q: FL.bq, offset: FL.boff, limit: 50})), s = d.summary, caps = d.caps;
  const dips = FL.bv === "bitirgan" ? await flApi("/api/flows/grad/diplomas") : null;
  const chk = r => `<div class="fl-checks">${r.checks.map(x => flChip(x.text, x.ok ? "ok" : "warn")).join("")}</div>`;
  box.innerHTML = `<div class="fl-kpis">${flKpi("Bitiruvchi kurs", flN(s.total), "bakalavr 4-kurs, magistr 2-kurs")}${flKpi("Talablarga javob beradi", flN(s.eligible), "kredit, qarzsiz, bitiruv ishi, YDA", s.eligible ? "ok" : "")}
      ${flKpi("Mavzu tanlanmagan", flN(s.no_topic), "", s.no_topic ? "warn" : "")}${flKpi("Akademik qarzdor", flN(s.debts), "", s.debts ? "bad" : "")}
      ${flKpi("Diplomlar reyestri", flN(s.diplomas), `imtiyozli: ${flN(s.honours)}`)}</div>
    <div class="card fl-card"><div class="fl-bar">${flSeg([["", "Bitiruvchi kurs"], ["eligible", "Bitirishga tayyor"], ["notopic", "Mavzusiz"], ["debts", "Qarzdorlar"], ["bitirgan", "Bitirganlar va diplomlar"]], FL.bv, "bv")}
      <input type="search" id="flBq" placeholder="F.I.Sh., HEMIS ID yoki guruh" value="${esc(FL.bq)}" aria-label="Qidirish"></div>
      <p class="muted">Bitirish: kredit (bakalavr ${d.rules.credits.bakalavr}, magistr ${d.rules.credits.magistr}), akademik qarz yo'q, bitiruv ishi / magistrlik dissertatsiyasi himoya qilingan, YDA topshirilgan.
        Imtiyozli diplom: fanlarning kamida ${Math.round(d.rules.honours.min_a_share * 100)}% i «A», hech bir fan «C» dan past emas, qayta topshirishsiz, bitiruv ishi va YDA «A» — institut nizomi bilan tasdiqlanadi.</p>
      ${caps.order && FL.bv === "eligible" ? `<div class="fl-acts" style="margin:0 0 10px"><button class="btn sm primary" type="button" id="flGo2">Tanlanganlar uchun bitirish buyrug'i loyihasi</button></div>` : ""}
      ${caps.diploma && FL.bv === "bitirgan" ? `<div class="fl-acts" style="margin:0 0 10px"><button class="btn sm" type="button" id="flDip">Imzolangan buyruq bo'yicha diplom raqamlarini berish</button></div>` : ""}
      ${flTable([...(caps.order && FL.bv === "eligible" ? [["", r => r.eligible && !r.order ? `<input type="checkbox" data-gs="${r.id}" aria-label="Tanlash">` : ""]] : []),
                 ["Talaba", r => `<b>${esc(r.full_name)}</b><small>${esc(r.grp)} · ${esc(r.level)} · ${esc(r.study_form)}</small>`],
                 ["Bitiruv ishi", r => `${esc(r.topic || "—")}<small>${esc(r.t_status_name)}${r.supervisor ? " · " + esc(flShort(r.supervisor)) : ""}${r.defense_date ? " · himoya " + flD(r.defense_date) : ""}</small>`],
                 ["Talablar", r => chk(r) + (r.honours ? `<small>${r.honours.ok ? "imtiyozli diplomga mos" : "imtiyozsiz: " + esc(r.honours.why.join("; "))}</small>` : "")],
                 ["Diplom / buyruq", r => (r.number ? `<b>${esc(r.series)} № ${esc(r.number)}</b>${r.dip_honours ? flChip("imtiyozli", "ok") : ""}` : "")
                   + (r.order ? `<small>buyruq ${esc(r.order.reg_no || "#" + r.order.id)} · ${esc(r.order.status)}</small>` : "")],
                 ["", r => `<a class="btn sm ghost" href="/api/flows/grad/${r.id}/supplement" download>Ilova (.docx)</a>`
                   + (caps.thesis && r.status === "faol" ? `<button class="btn sm ghost" type="button" data-th="${r.id}">Bitiruv ishi</button>` : "")
                   + (caps.yda && r.status === "faol" ? `<button class="btn sm ghost" type="button" data-yd="${r.id}">YDA</button>` : "")]],
                d.items, {empty: d.aggregate ? FL_AGG : "Talabalar yo'q"})}
      <div class="fl-pager">${fmt(d.total)} tadan ${d.total ? FL.boff + 1 : 0}–${Math.min(FL.boff + 50, d.total)}
        <button class="btn sm" type="button" id="flPp" ${FL.boff ? "" : "disabled"}>Oldingi</button><button class="btn sm" type="button" id="flPn" ${FL.boff + 50 < d.total ? "" : "disabled"}>Keyingi</button></div></div>
    ${dips ? `<div class="card fl-card"><h3>Diplomlar reyestri</h3><p class="muted">${esc(dips.rule)}</p>
      ${flTable([["Seriya va raqam", r => `<b>${esc(r.series)} № ${esc(r.number)}</b>`, "num"], ["Bitiruvchi", r => `${esc(r.full_name)}<small>${esc(r.grp || "")} · ${esc(r.direction || "")}</small>`],
                 ["Buyruq", r => `${esc(r.reg_no || "")}<small>${flD(r.issued_at)}</small>`], ["Imtiyoz", r => r.honours ? flChip("imtiyozli", "ok") : "—"]], dips.items, {empty: dips.aggregate ? FL_AGG : "Reyestr bo'sh"})}</div>` : ""}`;
  box.querySelectorAll("[data-bv]").forEach(b => b.onclick = () => { FL.bv = b.dataset.bv; FL.boff = 0; flGrad(box); });
  let t; $("#flBq").oninput = e => { clearTimeout(t); t = setTimeout(() => { FL.bq = e.target.value.trim(); FL.boff = 0; flGrad(box); }, 350); };
  $("#flPp").onclick = () => { FL.boff = Math.max(0, FL.boff - 50); flGrad(box); };
  $("#flPn").onclick = () => { FL.boff += 50; flGrad(box); };
  const go = $("#flGo2"); if (go) go.onclick = async () => { const ids = [...box.querySelectorAll("[data-gs]:checked")].map(x => +x.dataset.gs);
    if (!ids.length) return toast("Talabalarni tanlang");
    const r = await flApi("/api/flows/grad/order", {ids}); if (r) { toast(`Bitirish buyrug'i loyihasi #${r.order_id} — «Buyruqlar» bo'limida`); flGrad(box); } };
  const dp = $("#flDip"); if (dp) dp.onclick = async () => { const r = await flApi("/api/flows/grad/diplomas", {}); if (r) { toast(`Diplom raqami berildi: ${r.registered} ta`); flGrad(box); } };
  box.querySelectorAll("[data-th]").forEach(b => b.onclick = () => { const r = d.items.find(x => x.id === +b.dataset.th); let sup = null;
    const m = flModal("Bitiruv ishi", `<label>Mavzu<textarea id="h1">${esc(r.topic || "")}</textarea></label>
      <label>Ilmiy rahbar<input id="h2" placeholder="${esc(flShort(r.supervisor) || "O'qituvchi F.I.Sh.")}" autocomplete="off"><div class="fl-pick" id="h2l"></div></label>
      <div class="row2"><label>Himoya sanasi<input id="h3" type="date" value="${esc(r.defense_date || "")}"></label>
        <label>Holat<select id="h4">${Object.entries(d.thesis_statuses).map(([k, v]) => `<option value="${k}" ${k === r.t_status ? "selected" : ""}>${esc(v)}</option>`).join("")}</select></label></div>
      <label>Himoya bali (himoya qilingan bo'lsa)<input id="h5" type="number" min="0" max="100" value="${r.t_score ?? ""}"></label>`, async m => {
        const x = await flApi(`/api/flows/grad/${r.id}/thesis`, {topic: m.querySelector("#h1").value, supervisor_id: sup?.id || null, defense_date: m.querySelector("#h3").value,
          status: m.querySelector("#h4").value, score: m.querySelector("#h5").value === "" ? null : +m.querySelector("#h5").value});
        if (x) { toast("Saqlandi"); flGrad(box); } return !!x; });
    flPicker(m, "#h2", "#h2l", q => `/api/flows/lookup/teachers?q=${encodeURIComponent(q)}`, x => `${esc(flShort(x.full_name))} <small class="muted">${esc(x.kafedra || "")}</small>`, x => sup = x); });
  box.querySelectorAll("[data-yd]").forEach(b => b.onclick = () => flModal("YDA natijasi", `<div class="row2"><label>Ball (0–100)<input id="y1" type="number" min="0" max="100"></label>
      <label>Sana<input id="y2" type="date" value="${FL.meta.today}"></label></div>`, async m => {
      const x = await flApi(`/api/flows/grad/${b.dataset.yd}/yda`, {score: +m.querySelector("#y1").value, exam_date: m.querySelector("#y2").value}); if (x) { toast("YDA natijasi saqlandi"); flGrad(box); } return !!x; }));
}
