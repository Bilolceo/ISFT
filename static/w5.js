/* =====================================================================
   W5: Kiruvchi xatlar (Devonxona), Qabul (abituriyentlar), KPI maqsadlari va Sifat amallari (rejalar),
   AT bo'limi — kutilayotgan akkaunt so'rovlari (Akkauntlar sahifasiga qo'shiladi).
   API: /api/devon, /api/qabul, /api/rejalar, /api/it-requests
   ===================================================================== */
"use strict";
document.head.insertAdjacentHTML("beforeend", '<link rel="stylesheet" href="w5.css">');

async function w5(path, body, method) {
  const r = await fetch(path, {method: method || (body !== undefined ? "POST" : "GET"), credentials: "same-origin",
    headers: body instanceof Blob ? {} : {"Content-Type": "application/json"}, body: body === undefined ? undefined : body instanceof Blob ? body : JSON.stringify(body)});
  if (r.status === 401) { showLogin(); throw new Error("auth"); }
  if (!r.ok) {
    let m = "Xatolik"; try { const j = await r.json(); m = j.message || (typeof j.detail === "string" ? j.detail : (j.detail?.[0]?.msg || m)); } catch (e) {}
    toast(m); const e = new Error("denied"); e.msg = m; throw e;
  }
  return r.headers.get("content-type")?.includes("json") ? r.json() : r;
}
function w5Modal(title, html, onOk, okText = "Saqlash") {
  const bg = document.createElement("div"); bg.className = "w5-bg";
  bg.innerHTML = `<div class="w5-modal" role="dialog" aria-modal="true" aria-label="${esc(title)}"><h3>${esc(title)}</h3><div class="w5-mb">${html}</div>
    <div class="w5-acts"><button type="button" class="btn ghost" data-x>Bekor qilish</button>${onOk ? `<button type="button" class="btn primary" data-ok>${esc(okText)}</button>` : ""}</div></div>`;
  document.body.appendChild(bg);
  const close = () => bg.remove();
  bg.addEventListener("click", e => { if (e.target === bg || e.target.closest("[data-x]")) close(); });
  bg.addEventListener("keydown", e => { if (e.key === "Escape") close(); });
  const ok = bg.querySelector("[data-ok]");
  if (ok) ok.onclick = () => busy(ok, async () => { if (await onOk(bg) !== false) close(); });
  setTimeout(() => (bg.querySelector("input,select,textarea") || ok)?.focus(), 30);
  return bg;
}
const w5v = (m, id) => (m.querySelector("#" + id)?.value || "").trim();
const w5today = () => (ME && ME.today) || new Date().toISOString().slice(0, 10);
const w5plus = d => { const t = new Date(w5today() + "T00:00:00"); t.setDate(t.getDate() + d); return t.toISOString().slice(0, 10); };
const w5head = (title, sub, actions = "") => `<div class="head"><div><h2>${title}</h2>${sub ? `<span class="muted">${sub}</span>` : ""}</div><div class="row-actions">${actions}</div></div>`;
const w5seg = (items, cur, attr) => `<div class="w5-seg" role="tablist">${items.map(([k, l, n]) => `<button type="button" role="tab" data-${attr}="${k}" class="${cur === k ? "on" : ""}" aria-selected="${cur === k}">${esc(l)}${n ? ` <b>${n}</b>` : ""}</button>`).join("")}</div>`;

/* ---------------------------------------------------------------- Kiruvchi xatlar */
const DV = {st: "", q: "", meta: null};
async function renderKiruvchi() {
  const el = $("#v-kiruvchi");
  try { DV.meta = await w5("/api/devon/meta"); } catch (e) { el.innerHTML = `<div class="card">${esc(e.msg || "Ruxsat yo'q")}</div>`; return; }
  const m = DV.meta, c = m.counts || {};
  if (!DV.st && !m.can.register) DV.st = "royxatda";
  const segs = [["", "Hammasi"], ["royxatda", "Rezolyutsiya kutilmoqda", c.royxatda], ["ijroda", "Ijroda", c.ijroda], ["muddati", "Muddati o'tgan"], ["javob", "Javob berildi"], ["yopildi", "Yopildi"]];
  el.innerHTML = w5head("Kiruvchi xatlar", m.can.register ? "Tashqi tashkilotlardan kelgan xatlar: ro'yxatga olish → rezolyutsiya → ijro → javob" : "Sizga rezolyutsiya uchun yo'naltirilgan xatlar",
      m.can.register ? `<button class="btn primary sm" id="dvNew">${ico("plus", 15)} Xatni ro'yxatga olish</button>` : "") +
    `<div class="card"><div class="w5-bar">${w5seg(segs, DV.st, "st")}<label class="w5-search">${ico("search", 15)}<input id="dvQ" placeholder="Raqam, jo'natuvchi yoki mavzu" value="${esc(DV.q)}"></label></div><div id="dvList"><p class="muted">Yuklanmoqda…</p></div></div>`;
  hydrateIcons(el);
  el.querySelectorAll("[data-st]").forEach(b => b.onclick = () => { DV.st = b.dataset.st; renderKiruvchi(); });
  let t; $("#dvQ").oninput = e => { clearTimeout(t); t = setTimeout(() => { DV.q = e.target.value; dvList(); }, 250); };
  if ($("#dvNew")) $("#dvNew").onclick = dvNew;
  dvList();
}
async function dvList() {
  const d = await w5("/api/devon/letters?" + new URLSearchParams({status: DV.st, q: DV.q})), m = DV.meta, box = $("#dvList");
  if (!d.items.length) { box.innerHTML = `<p class="muted">Xat yo'q</p>`; return; }
  box.innerHTML = `<table class="tbl w5-tbl"><thead><tr><th>Kiruvchi №</th><th>Jo'natuvchi</th><th>Mavzu</th><th>Rezolyutsiya</th><th>Ijrochi · muddat</th><th>Holat</th><th></th></tr></thead><tbody>${d.items.map(x => `<tr>
      <td class="nw"><b>${esc(x.in_no)}</b><div class="tiny muted">${dmy(x.in_date)}</div></td>
      <td>${esc(x.sender)}<div class="tiny muted">${esc(x.sender_no || "")}${x.sender_date ? " · " + dmy(x.sender_date) : ""}</div></td>
      <td>${esc(x.subject)}${x.has_file ? ` <a href="/api/devon/letters/${x.id}/file" target="_blank" class="tiny">${ico("file", 13)}fayl</a>` : ""}</td>
      <td class="tiny">${x.resolution ? `«${esc(x.resolution)}»<div class="muted">${esc(x.resolved_name || "")}</div>` : `<span class="muted">${esc(x.resolver_label)} kutilmoqda</span>`}</td>
      <td class="tiny">${x.executor_name ? `${esc(x.executor_name)}<div class="${x.overdue ? "w5-bad" : "muted"}">${dmy(x.due)}</div>` : "—"}${x.thread ? `<div><a href="#" data-th="${x.thread.id}">${esc(x.thread.ref_no)}</a></div>` : ""}</td>
      <td><span class="tag ${x.status === "royxatda" ? "mid" : x.overdue ? "high" : x.status === "ijroda" ? "" : "low"}">${esc(x.overdue ? "Muddati o'tgan" : x.status_label)}</span>${x.reply ? `<div class="tiny muted">→ ${esc(x.reply.out_no)}</div>` : ""}</td>
      <td class="nw">${x.status === "royxatda" && m.can.resolve ? `<button class="btn sm primary" data-res="${x.id}">Rezolyutsiya</button>` : ""}
        ${x.status === "royxatda" && m.can.register ? `<button class="btn sm" data-file="${x.id}" title="Skan yuklash">${ico("upload", 14)}</button>` : ""}
        ${["ijroda", "javob"].includes(x.status) && m.can.register && x.status === "ijroda" ? `<button class="btn sm" data-close="${x.id}">Javob / yopish</button>` : ""}</td></tr>`).join("")}</tbody></table>`;
  hydrateIcons(box);
  box.querySelectorAll("[data-th]").forEach(a => a.onclick = e => { e.preventDefault(); if (typeof PT !== "undefined") { PT.open = +a.dataset.th; } go("portal"); });
  box.querySelectorAll("[data-res]").forEach(b => b.onclick = () => dvRes(d.items.find(x => x.id === +b.dataset.res)));
  box.querySelectorAll("[data-close]").forEach(b => b.onclick = () => dvClose(+b.dataset.close));
  box.querySelectorAll("[data-file]").forEach(b => b.onclick = () => dvFile(+b.dataset.file));
}
function dvNew() {
  const m = DV.meta;
  w5Modal("Kiruvchi xatni ro'yxatga olish", `<div class="w5-grid">
    <label>Jo'natuvchi tashkilot *<input id="f1" maxlength="200"></label>
    <label>Kiruvchi sana<input id="f2" type="date" value="${w5today()}"></label>
    <label>Jo'natuvchi raqami<input id="f3" maxlength="60"></label><label>Jo'natuvchi sanasi<input id="f4" type="date"></label>
    <label class="w5-full">Mavzu *<input id="f5" maxlength="300"></label>
    <label class="w5-full">Qisqa mazmun<textarea id="f6" rows="2" maxlength="2000"></textarea></label>
    <label class="w5-full">Rezolyutsiya uchun<select id="f7">${Object.entries(m.resolvers).map(([k, v]) => `<option value="${k}">${esc(v)}</option>`).join("")}</select></label>
    <label class="w5-full">Skan (PDF/JPG/PNG/DOCX, ixtiyoriy)<input id="f8" type="file" accept=".pdf,.jpg,.jpeg,.png,.docx"></label></div>`, async bg => {
    const r = await w5("/api/devon/letters", {sender: w5v(bg, "f1"), in_date: w5v(bg, "f2"), sender_no: w5v(bg, "f3"), sender_date: w5v(bg, "f4"),
      subject: w5v(bg, "f5"), summary: w5v(bg, "f6"), resolver_role: w5v(bg, "f7")});
    const f = bg.querySelector("#f8").files[0];
    if (f) await fetch(`/api/devon/letters/${r.id}/file`, {method: "POST", credentials: "same-origin", headers: {"x-filename": encodeURIComponent(f.name)}, body: f});
    toast(`Ro'yxatga olindi: ${r.in_no}`); renderKiruvchi();
  }, "Ro'yxatga olish");
}
function dvFile(id) {
  w5Modal("Skan yuklash", `<label>Fayl (PDF/JPG/PNG/DOCX)<input id="f1" type="file" accept=".pdf,.jpg,.jpeg,.png,.docx"></label>`, async bg => {
    const f = bg.querySelector("#f1").files[0]; if (!f) { toast("Faylni tanlang"); return false; }
    const r = await fetch(`/api/devon/letters/${id}/file`, {method: "POST", credentials: "same-origin", headers: {"x-filename": encodeURIComponent(f.name)}, body: f});
    if (!r.ok) { toast((await r.json()).detail || "Xatolik"); return false; }
    toast("Yuklandi"); dvList();
  }, "Yuklash");
}
function dvRes(x) {
  const m = DV.meta;
  w5Modal(`Rezolyutsiya: ${x.in_no}`, `<p class="tiny muted">${esc(x.sender)} — ${esc(x.subject)}</p><div class="w5-grid">
    <label class="w5-full">Rezolyutsiya matni *<textarea id="f1" rows="2" maxlength="1000">Ijro uchun. Muddatida javob loyihasi tayyorlansin.</textarea></label>
    <label>Ijrochi bo'lim *<select id="f2"><option value="">Tanlang…</option>${m.units.map(u => `<option value="${u.key}">${esc(u.name)}</option>`).join("")}</select></label>
    <label>Ijro muddati *<input id="f3" type="date" value="${w5plus(10)}" min="${w5today()}"></label></div>
    <p class="tiny muted">Ijrochi bo'limga Portal orqali topshiriq xati avtomatik yuboriladi.</p>`, async bg => {
    if (!w5v(bg, "f2")) { toast("Ijrochi bo'limni tanlang"); return false; }
    await w5(`/api/devon/letters/${x.id}/resolution`, {resolution: w5v(bg, "f1"), executor_unit: w5v(bg, "f2"), due: w5v(bg, "f3")});
    toast("Rezolyutsiya qo'yildi, ijrochiga yuborildi"); renderKiruvchi();
  }, "Rezolyutsiya berish");
}
async function dvClose(id) {
  const og = await w5("/api/devon/outgoing");
  w5Modal("Javob / yopish", `<label>Javob — chiquvchi xat<select id="f1"><option value="0">— javobsiz yopish —</option>${og.items.map(o => `<option value="${o.id}">${esc(o.out_no)} · ${esc(o.addressee)} · ${esc(o.subject).slice(0, 60)}</option>`).join("")}</select></label>
    <label>Izoh<input id="f2" maxlength="500" placeholder="Javobsiz yopishda majburiy (masalan: «ma'lumot uchun»)"></label>`, async bg => {
    await w5(`/api/devon/letters/${id}/close`, {out_id: +w5v(bg, "f1"), note: w5v(bg, "f2")}); toast("Yopildi"); renderKiruvchi();
  }, "Saqlash");
}

/* ---------------------------------------------------------------- Qabul */
const QB = {stage: "", dir: "", q: "", meta: null};
async function renderQabul() {
  const el = $("#v-qabul");
  try { QB.meta = await w5("/api/qabul/meta"); } catch (e) { el.innerHTML = `<div class="card">${esc(e.msg || "Ruxsat yo'q")}</div>`; return; }
  const m = QB.meta, s = m.by_stage;
  const order = ["ariza", "hujjat", "imtihon", "shartnoma", "buyruq", "rad"];
  el.innerHTML = w5head("Qabul", "Abituriyentlar oqimi: ariza → hujjatlar → imtihon / suhbat → shartnoma → qabul buyrug'i loyihasi",
      m.can_edit ? `<button class="btn primary sm" id="qbNew">${ico("plus", 15)} Yangi ariza</button>` : "") +
    `<div class="w5-funnel">${order.map(k => `<button type="button" class="w5-step ${QB.stage === k ? "on" : ""} ${k === "rad" ? "rad" : ""}" data-stage="${k}"><b>${fmt(s[k] || 0)}</b><span>${esc(m.stages[k])}</span></button>`).join("")}</div>
    <div class="grid g2"><div class="card"><div class="w5-bar"><select id="qbDir"><option value="">Barcha yo'nalishlar</option>${m.directions.map(d => `<option${QB.dir === d ? " selected" : ""}>${esc(d)}</option>`).join("")}</select>
      <label class="w5-search">${ico("search", 15)}<input id="qbQ" placeholder="F.I.Sh. yoki shartnoma №" value="${esc(QB.q)}"></label>${QB.stage ? `<button class="btn sm ghost" id="qbAll">Barcha bosqichlar</button>` : ""}</div><div id="qbList"></div></div>
    <div class="card"><h3 style="margin-top:0">Yo'nalishlar bo'yicha</h3>${tbl(["Yo'nalish", "#Jami", "#Ariza", "#Hujjat", "#Imtihon", "#Shartnoma", "#Buyruq", ""],
      m.by_direction.map(r => [esc(r.direction), r.n, r.ariza, r.hujjat, r.imtihon, r.shartnoma, r.buyruq, m.can_edit && r.shartnoma ? `<button class="btn sm" data-order="${esc(r.direction)}">Buyruq loyihasi</button>` : ""]), {nw: [0]})}</div></div>
    ${m.desk && m.desk.indicators && m.desk.indicators.length ? `<details class="pg-info"><summary>${ico("chart", 14)}Qabul tahlili (o'tgan kampaniya, jamlangan)</summary><div class="grid g3 desk-inds">${m.desk.indicators.map(deskInd).join("")}</div></details>` : ""}`;
  hydrateIcons(el);
  el.querySelectorAll("[data-stage]").forEach(b => b.onclick = () => { QB.stage = QB.stage === b.dataset.stage ? "" : b.dataset.stage; renderQabul(); });
  $("#qbDir").onchange = e => { QB.dir = e.target.value; qbList(); };
  let t; $("#qbQ").oninput = e => { clearTimeout(t); t = setTimeout(() => { QB.q = e.target.value; qbList(); }, 250); };
  if ($("#qbAll")) $("#qbAll").onclick = () => { QB.stage = ""; renderQabul(); };
  if ($("#qbNew")) $("#qbNew").onclick = qbNew;
  el.querySelectorAll("[data-order]").forEach(b => b.onclick = () => { if (!arm(b, "Ha, loyiha")) return; busy(b, async () => {
    const r = await w5("/api/qabul/order?" + new URLSearchParams({direction: b.dataset.order}), {});
    const bl = await r.blob(), a = document.createElement("a"); a.href = URL.createObjectURL(bl); a.download = "qabul-buyrugi-loyihasi.docx"; a.click();
    toast("Buyruq loyihasi yuklab olindi"); renderQabul(); }); });
  qbList();
}
async function qbList() {
  const d = await w5("/api/qabul/applicants?" + new URLSearchParams({stage: QB.stage, direction: QB.dir, q: QB.q})), m = QB.meta, box = $("#qbList");
  if (!d.items.length) { box.innerHTML = `<p class="muted">Abituriyent yo'q</p>`; return; }
  box.innerHTML = `<table class="tbl w5-tbl"><thead><tr><th>F.I.Sh.</th><th>Yo'nalish</th><th>Bosqich</th><th>Ball</th><th></th></tr></thead><tbody>${d.items.slice(0, 150).map(x => `<tr>
    <td>${esc(x.full_name)}<div class="tiny muted">${esc(x.study_form || "")} · ${esc(x.payment_type || "")}${x.contract_no ? " · " + esc(x.contract_no) : ""}</div></td>
    <td class="tiny">${esc(x.direction)}</td><td><span class="tag ${x.stage === "rad" ? "high" : x.stage === "buyruq" ? "low" : ""}">${esc(x.stage_label)}</span>${x.note ? `<div class="tiny muted">${esc(x.note)}</div>` : ""}</td>
    <td>${x.exam_score ?? "—"}</td>
    <td class="nw">${m.can_edit && m.next[x.stage] ? `<button class="btn sm primary" data-adv="${x.id}">${esc({ariza: "Hujjatlar tekshirildi", hujjat: "Imtihon bali", imtihon: "Shartnoma tuzildi"}[x.stage])}</button>
      <button class="btn sm ghost" data-rej="${x.id}">Rad</button>` : ""}</td></tr>`).join("")}</tbody></table>${d.items.length > 150 ? `<p class="tiny muted">Birinchi 150 ta · filtrdan foydalaning</p>` : ""}`;
  box.querySelectorAll("[data-adv]").forEach(b => b.onclick = () => {
    const x = d.items.find(i => i.id === +b.dataset.adv);
    if (x.stage === "hujjat") return w5Modal("Imtihon / suhbat bali", `<label>Ball (0–100, o'tish ${m.pass_score})<input id="f1" type="number" min="0" max="100"></label>`, async bg => {
      await w5(`/api/qabul/applicants/${x.id}/advance`, {exam_score: +w5v(bg, "f1")}); toast("Saqlandi"); renderQabul(); });
    busy(b, async () => { await w5(`/api/qabul/applicants/${x.id}/advance`, {}); toast("Keyingi bosqichga o'tdi"); renderQabul(); });
  });
  box.querySelectorAll("[data-rej]").forEach(b => b.onclick = () => w5Modal("Arizani rad etish", `<label>Sabab *<input id="f1" maxlength="300"></label>`, async bg => {
    await w5(`/api/qabul/applicants/${b.dataset.rej}/reject`, {note: w5v(bg, "f1")}); toast("Rad etildi"); renderQabul(); }, "Rad etish"));
}
function qbNew() {
  const m = QB.meta;
  w5Modal("Yangi ariza", `<div class="w5-grid"><label class="w5-full">F.I.Sh. *<input id="f1" maxlength="120"></label><label>Telefon<input id="f2" maxlength="30"></label>
    <label>Yo'nalish *<select id="f3">${m.directions.map(d => `<option>${esc(d)}</option>`).join("")}</select></label>
    <label>Ta'lim shakli<select id="f4"><option>kunduzgi</option><option>sirtqi</option></select></label><label>To'lov<select id="f5"><option>kontrakt</option><option>grant</option></select></label></div>`,
    async bg => { await w5("/api/qabul/applicants", {full_name: w5v(bg, "f1"), phone: w5v(bg, "f2"), direction: w5v(bg, "f3"), study_form: w5v(bg, "f4"), payment_type: w5v(bg, "f5")});
      toast("Ariza qabul qilindi"); renderQabul(); }, "Qabul qilish");
}

/* ---------------------------------------------------------------- KPI maqsadlari va Sifat amallari */
const RJ = {tab: null};
async function renderRejalar() {
  const el = $("#v-rejalar");
  const kpiOk = ["strategik", "rektor", "kengash", "prorektor_oquv", "prorektor_ilmiy", "prorektor_moliya", "prorektor_yoshlar"].includes(ME.role_key);
  const sifOk = ["sifat", "rektor", "prorektor_oquv"].includes(ME.role_key);
  if (!RJ.tab) RJ.tab = ME.role_key === "sifat" ? "sifat" : "kpi";
  const tabs = [...(kpiOk ? [["kpi", "KPI maqsadlari"]] : []), ...(sifOk ? [["sifat", "Sifat: topilmalar va akkreditatsiya"]] : [])];
  if (!tabs.some(t => t[0] === RJ.tab)) RJ.tab = tabs[0]?.[0];
  el.innerHTML = w5head(ME.role_key === "sifat" ? "Sifat amallari" : "KPI maqsadlari", "", "") + (tabs.length > 1 ? w5seg(tabs, RJ.tab, "rt") : "") + `<div id="rjBody"><p class="muted">Yuklanmoqda…</p></div>`;
  el.querySelectorAll("[data-rt]").forEach(b => b.onclick = () => { RJ.tab = b.dataset.rt; renderRejalar(); });
  try { RJ.tab === "sifat" ? await rjSifat() : await rjKpi(); } catch (e) { $("#rjBody").innerHTML = `<div class="card">${esc(e.msg || "Ruxsat yo'q")}</div>`; }
}
async function rjKpi() {
  const d = await w5("/api/rejalar/kpi"), box = $("#rjBody");
  const stc = {bajarildi: "low", muddati_otgan: "high", yolda: "mid"};
  box.innerHTML = `<div class="row-actions" style="margin:0 0 10px">${d.can_edit ? `<button class="btn primary sm" id="rjAdd">${ico("plus", 15)} Maqsad qo'shish</button>` : ""}
      <a class="btn sm" href="/api/rejalar/kengash.docx">${ico("download", 15)} Kengash hisoboti (chorak, DOCX)</a></div>
    <div class="card">${d.targets.length ? `<table class="tbl w5-tbl"><thead><tr><th>Ko'rsatkich</th><th>Mas'ul</th><th>Maqsad</th><th>Amalda</th><th>Muddat</th><th>Holat</th><th></th></tr></thead><tbody>${d.targets.map(t => `<tr>
      <td><b>${esc(t.title)}</b>${t.note ? `<div class="tiny muted">${esc(t.note)}</div>` : ""}</td><td class="tiny">${esc(t.owner_name)}</td>
      <td>${t.good === "down" ? "≤" : "≥"} ${fmt(t.target)}${esc(t.unit)}</td><td><b>${t.actual == null ? "—" : fmt(t.actual) + esc(t.unit)}</b></td><td class="nw">${dmy(t.deadline)}</td>
      <td><span class="tag ${stc[t.status]}">${esc(t.status_label)}</span></td>
      <td class="nw">${d.can_edit ? `<button class="btn sm ghost" data-ed="${t.id}">Tahrirlash</button><button class="btn sm ghost" data-del="${t.id}">O'chirish</button>` : ""}</td></tr>`).join("")}</tbody></table>`
      : `<p class="muted">Maqsadlar hali qo'yilmagan</p>`}<p class="tiny muted">Amaldagi qiymat avtomatik — tizimdagi ko'rsatkichdan olinadi.</p></div>`;
  hydrateIcons(box);
  const form = t => w5Modal(t ? "KPI maqsadini tahrirlash" : "Yangi KPI maqsadi", `<div class="w5-grid">
      <label class="w5-full">Ko'rsatkich *<select id="f1">${d.metrics.map(x => `<option value="${x.key}"${t && t.metric === x.key ? " selected" : ""}>${esc(x.label)} (hozir: ${x.value ?? "—"}${esc(x.unit)})</option>`).join("")}</select></label>
      <label class="w5-full">Nomi (ixtiyoriy)<input id="f2" maxlength="120" value="${esc(t?.title || "")}"></label>
      <label>Mas'ul bo'lim *<select id="f3">${d.units.map(u => `<option value="${u.key}"${t && t.owner_unit === u.key ? " selected" : ""}>${esc(u.name)}</option>`).join("")}</select></label>
      <label>Maqsad qiymat *<input id="f4" type="number" step="0.1" value="${t?.target ?? ""}"></label>
      <label>Muddat *<input id="f5" type="date" value="${t?.deadline || w5plus(90)}"></label><label>Izoh<input id="f6" maxlength="300" value="${esc(t?.note || "")}"></label></div>`,
    async bg => { await w5("/api/rejalar/kpi" + (t ? `?tid=${t.id}` : ""), {metric: w5v(bg, "f1"), title: w5v(bg, "f2"), owner_unit: w5v(bg, "f3"), target: +w5v(bg, "f4"), deadline: w5v(bg, "f5"), note: w5v(bg, "f6")});
      toast("Saqlandi"); rjKpi(); });
  if ($("#rjAdd")) $("#rjAdd").onclick = () => form(null);
  box.querySelectorAll("[data-ed]").forEach(b => b.onclick = () => form(d.targets.find(t => t.id === +b.dataset.ed)));
  box.querySelectorAll("[data-del]").forEach(b => b.onclick = () => { if (!arm(b, "Ha, o'chirish")) return; busy(b, async () => { await w5(`/api/rejalar/kpi/${b.dataset.del}/delete`, {}); rjKpi(); }); });
}
async function rjSifat() {
  const d = await w5("/api/rejalar/sifat"), box = $("#rjBody");
  const sec = [...new Set(d.akkr.map(i => i.section))];
  const done = d.akkr.filter(i => i.status === "tayyor").length;
  box.innerHTML = `<div class="grid g2"><div class="card"><div class="head" style="margin-bottom:8px"><h3 style="margin:0">Akkreditatsiya nazorat varaqasi <span class="tag ${done === d.akkr.length ? "low" : "mid"}">${done}/${d.akkr.length} tayyor</span></h3>
      ${d.can_edit ? `<button class="btn sm" id="akAdd">${ico("plus", 14)} Band</button>` : ""}</div>
      ${sec.map(s => `<div class="w5-sec">${esc(s)}</div>${d.akkr.filter(i => i.section === s).map(i => `<div class="w5-ak">
        <div><b>${esc(i.title)}</b><div class="tiny muted">${esc(i.owner_name)} · ${i.due ? dmy(i.due) : "muddatsiz"}${i.note ? " · " + esc(i.note) : ""}</div></div>
        ${d.can_edit ? `<select data-ak="${i.id}" class="sel-sm">${Object.entries(d.akkr_status).map(([k, v]) => `<option value="${k}"${i.status === k ? " selected" : ""}>${esc(v)}</option>`).join("")}</select>`
          : `<span class="tag ${i.status === "tayyor" ? "low" : i.status === "jarayonda" ? "mid" : "high"}">${esc(i.status_label)}</span>`}</div>`).join("")}`).join("")}</div>
    <div class="card"><div class="head" style="margin-bottom:8px"><h3 style="margin:0">Topilmalar → kafedraga topshiriq</h3>${d.can_edit ? `<button class="btn sm primary" id="fnAdd">${ico("send", 14)} Yangi topilma</button>` : ""}</div>
      ${d.findings.length ? d.findings.map(f => `<div class="w5-ak"><div><b>${esc(f.title)}</b><div class="tiny muted">${esc(f.unit_name)} · muddat ${dmy(f.due)} · topshiriq #${f.directive_id}</div></div>
        <span class="tag ${f.task_status === "bajarildi" ? "low" : ""}">${esc(f.task_status || "yangi")}</span></div>`).join("") : `<p class="muted">Topilma yo'q</p>`}
      <details class="pg-info"><summary>${ico("info", 14)}«${esc(d.risk.label)}» — yagona ta'rif</summary><p class="tiny muted">${esc(d.risk.def)}</p></details></div></div>`;
  hydrateIcons(box);
  box.querySelectorAll("[data-ak]").forEach(s => s.onchange = async () => { await w5(`/api/rejalar/sifat/akkr/${s.dataset.ak}`, {status: s.value}); toast("Saqlandi"); rjSifat(); });
  if ($("#fnAdd")) $("#fnAdd").onclick = () => w5Modal("Sifat topilmasi — kafedraga", `<div class="w5-grid">
      <label class="w5-full">Kafedra *<select id="f1">${d.kafedras.map(k => `<option value="${k.key}">${esc(k.name)}</option>`).join("")}</select></label>
      <label class="w5-full">Topilma (qisqa) *<input id="f2" maxlength="200" placeholder="Masalan: 3 ta fanda sillabus adabiyotlari eskirgan"></label>
      <label class="w5-full">Tafsilot va talab *<textarea id="f3" rows="3" maxlength="3000"></textarea></label><label>Muddat *<input id="f4" type="date" value="${w5plus(14)}" min="${w5today()}"></label></div>`,
    async bg => { await w5("/api/rejalar/sifat/finding", {unit: w5v(bg, "f1"), title: w5v(bg, "f2"), body: w5v(bg, "f3"), due: w5v(bg, "f4")}); toast("Kafedraga topshiriq yuborildi"); rjSifat(); }, "Yuborish");
  if ($("#akAdd")) $("#akAdd").onclick = () => w5Modal("Akkreditatsiya bandi", `<div class="w5-grid"><label>Bo'lim (mezon) *<input id="f1" list="akSec"><datalist id="akSec">${sec.map(s => `<option>${esc(s)}</option>`).join("")}</datalist></label>
      <label>Mas'ul *<select id="f3">${d.units.map(u => `<option value="${u.key}">${esc(u.name)}</option>`).join("")}</select></label>
      <label class="w5-full">Band *<input id="f2" maxlength="200"></label><label>Muddat<input id="f4" type="date"></label></div>`,
    async bg => { await w5("/api/rejalar/sifat/akkr", {section: w5v(bg, "f1"), title: w5v(bg, "f2"), owner_unit: w5v(bg, "f3"), due: w5v(bg, "f4")}); rjSifat(); }, "Qo'shish");
}

/* ---------------------------------------------------------------- AT: kutilayotgan akkaunt so'rovlari (Akkauntlar sahifasida) */
async function itReqDraw() {
  if (!ME || !["it_head", "it_staff"].includes(ME.role_key)) return;
  const host = $("#v-accounts"); if (!host) return;
  let box = $("#itReq");
  if (!box) { const anchor = $("#acStats"); if (!anchor) return; anchor.insertAdjacentHTML("beforebegin", `<div id="itReq"></div>`); box = $("#itReq"); }
  let d; try { d = await w5("/api/it-requests"); } catch (e) { return; }
  if (!d.items.length) { box.innerHTML = ""; return; }
  box.innerHTML = `<div class="card w5-itreq"><h3 style="margin:0 0 8px">${ico("ukey", 17)} Kutilayotgan akkaunt so'rovlari <span class="tag mid">${d.items.length}</span></h3>${d.items.map((x, i) => `<div class="w5-ak">
      <div><b>${esc(x.title)}</b><div class="tiny muted">${esc(x.position || "")}${x.unit_name ? " · " + esc(x.unit_name) : ""} · ${x.kind === "hire" ? "ishga kirish" : "oxirgi ish kuni"}: ${x.date ? dmy(x.date) : "—"}${x.signed ? "" : " · buyruq hali imzolanmagan"}</div></div>
      <div class="nw">${d.can_edit && x.kind === "hire" ? `<button class="btn sm primary" data-ir="${i}">Akkaunt yaratish</button>` : ""}
        ${d.can_edit && x.kind === "dismiss" ? (x.accounts.length ? `<button class="btn sm primary" data-blk="${i}">Bloklash (${x.accounts.length})</button>` : `<span class="tiny muted">faol akkaunt yo'q</span>`) : ""}
        ${d.can_edit ? `<button class="btn sm ghost" data-ok="${i}">Bajarildi</button>` : ""}</div></div>`).join("")}</div>`;
  hydrateIcons(box);
  box.querySelectorAll("[data-ir]").forEach(b => b.onclick = () => {
    const x = d.items[+b.dataset.ir];
    AC.form = true; AC.created = null; acFormDraw();
    const f = $("#acForm"); if (!f) return;
    f.querySelector("#acfPos").value = x.position || ""; f.querySelector("#acfPerson").value = (x.person || "").replace(/\s*\(namuna\)\s*$/, "");
    if (x.role) { f.querySelector("#acfRole").value = x.role; f.querySelector("#acfRole").dispatchEvent(new Event("change")); }
    if (x.unit) { const us = f.querySelector("#acfUnit"); if ([...us.options].some(o => o.value === x.unit)) us.value = x.unit; }
    f.scrollIntoView({block: "center"}); f.querySelector("#acfRole").focus();
    toast("Forma Kadrlar ma'lumotidan to'ldirildi — rolni tekshirib «Yaratish»ni bosing");
  });
  box.querySelectorAll("[data-blk]").forEach(b => b.onclick = () => { if (!arm(b, "Ha, bloklash")) return; busy(b, async () => {
    const x = d.items[+b.dataset.blk];
    for (const id of x.accounts) await w5(`/api/accounts/${id}/deactivate`, {});
    await w5(`/api/it-requests/dismiss/${x.id}/done`, {note: "akkauntlar faolsizlantirildi"});
    toast("Akkauntlar bloklandi"); typeof acReload === "function" ? acReload(true) : null; }); });
  box.querySelectorAll("[data-ok]").forEach(b => b.onclick = () => busy(b, async () => {
    const x = d.items[+b.dataset.ok]; await w5(`/api/it-requests/${x.kind}/${x.id}/done`, {}); toast("Belgilandi"); itReqDraw(); }));
}
/* Akkauntlar sahifasi chizilgach so'rovlar blokini qo'shish */
if (typeof acShell === "function") {
  const _acShell = acShell;
  acShell = function () { _acShell.apply(this, arguments); itReqDraw(); };
}
