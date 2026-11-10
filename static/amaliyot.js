/* =====================================================================
   «Amaliyot» — talabalar amaliyoti (app/amaliyot.py, /api/practice).
     Davrlar va biriktirish · Ogohlantirishlar · Bazalar (shartnoma, sig'im) · Statistika.
   Ruxsat va ko'lam serverda; bu yerda faqat ko'rinish. Global: renderAmaliyot() — app.js go() chaqiradi.
   app.js yordamchilari: $, esc, fmt, toast, arm, busy, locked, showLogin, ico.
   ===================================================================== */
const AM = {meta: null, tab: null, pid: null, st: "", q: ""};
if (!document.querySelector('link[href="amaliyot.css"]')) document.head.insertAdjacentHTML("beforeend", '<link rel="stylesheet" href="amaliyot.css">');
const amD = s => { s = String(s || "").slice(0, 10); return s.length === 10 ? `${s.slice(8, 10)}.${s.slice(5, 7)}.${s.slice(0, 4)}` : "—"; };
const amN = n => n == null ? "—" : fmt(n);
const amChip = (t, cls = "") => `<span class="am-chip ${cls}">${esc(t)}</span>`;
const AM_ST_CLS = {biriktirildi: "", boshlandi: "info", hisobot: "warn", baholandi: "ok", qaytarildi: "bad"};
const AM_PST_CLS = {"kutilmoqda": "", "davom etmoqda": "info", "hisobot topshirish": "warn", "yakunlangan": "ok"};
const AM_AGR_CLS = {"amalda": "ok", "tugayapti": "warn", "muddati o'tgan": "bad", "to'xtatilgan": "bad", "shartnomasiz": "bad"};
async function amApi(url, body) {
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
function amTable(cols, rows, {rowCls = () => "", empty = "Ma'lumot yo'q", click = null} = {}) {
  if (!rows.length) return `<div class="am-empty">${esc(empty)}</div>`;
  return `<div class="tw"><table class="am-t stack"><thead><tr>${cols.map(c => `<th>${esc(c[0])}</th>`).join("")}</tr></thead><tbody>` +
    rows.map((r, i) => `<tr class="${rowCls(r)}${click ? " am-click" : ""}" ${click ? `data-row="${i}" tabindex="0"` : ""}>${cols.map(c => `<td data-l="${esc(c[0])}" class="${c[2] || ""}">${c[1](r) ?? ""}</td>`).join("")}</tr>`).join("") +
    `</tbody></table></div>`;
}
function amBindRows(box, rows, fn) {
  box.querySelectorAll("tr[data-row]").forEach(tr => {
    const go_ = () => fn(rows[+tr.dataset.row]);
    tr.onclick = e => { if (!e.target.closest("button,a,input")) go_(); };
    tr.onkeydown = e => { if (e.key === "Enter") go_(); };
  });
}
const amKpi = (label, val, sub = "", cls = "") => `<div class="am-kpi ${cls}"><span>${esc(label)}</span><b>${val}</b>${sub ? `<small>${sub}</small>` : ""}</div>`;
function amModal(title, html, onOk, okText = "Saqlash", wide = false) {
  const bg = document.createElement("div"); bg.className = "am-modal-bg";
  bg.innerHTML = `<div class="am-modal${wide ? " wide" : ""}" role="dialog" aria-modal="true" aria-label="${esc(title)}"><h3>${esc(title)}</h3>${html}
    <div class="am-acts"><button type="button" class="btn ghost" data-x>${onOk ? "Bekor qilish" : "Yopish"}</button>${onOk ? `<button type="button" class="btn primary" data-ok>${esc(okText)}</button>` : ""}</div></div>`;
  document.body.appendChild(bg);
  const close = () => bg.remove();
  bg.addEventListener("click", e => { if (e.target === bg || e.target.closest("[data-x]")) close(); });
  bg.addEventListener("keydown", e => { if (e.key === "Escape") close(); });
  const ok = bg.querySelector("[data-ok]");
  if (ok) ok.onclick = async () => { ok.disabled = true; try { if (await onOk(bg)) close(); } finally { if (ok.isConnected) ok.disabled = false; } };
  setTimeout(() => bg.querySelector("input,select,textarea,button")?.focus(), 30);
  bg.close = close;
  return bg;
}
const AM_TABS = {davrlar: "Davrlar va biriktirish", ogohlantirish: "Ogohlantirishlar", bazalar: "Amaliyot bazalari", statistika: "Statistika"};

async function renderAmaliyot() {
  const el = $("#v-amaliyot");
  if (!el.innerHTML) el.innerHTML = `<p class="muted">Yuklanmoqda…</p>`;
  AM.meta = await amApi("/api/practice/meta");
  const M = AM.meta, K = M.kpi;
  if (!AM.tab || !M.tabs.includes(AM.tab)) AM.tab = M.tabs[0];
  const kp = [amKpi("Talabalar amaliyotda", amN(K.amaliyotda), `jami biriktirilgan ${amN(K.jami)}`),
              amKpi("Hisobot topshirgan", amN(K.hisobot), "baho kutilmoqda", K.hisobot ? "warn" : ""),
              amKpi("Baholangan", amN(K.baholandi)),
              amKpi("Hisobot muddati o'tgan", amN(K.kechikkan), "", K.kechikkan ? "bad" : "")];
  if (K.bazalar != null) kp.push(amKpi("Faol bazalar", amN(K.bazalar), K.shartnoma_tugayapti ? `${K.shartnoma_tugayapti} ta shartnoma muddati tugayapti/o'tgan` : "shartnomalar amalda", K.shartnoma_tugayapti ? "warn" : ""));
  el.innerHTML = `<div class="am-head"><div><h2>Amaliyot</h2><span class="muted">${esc(M.mode_note)} · ${esc(M.scope)}</span></div></div>
    <div class="am-kpis">${kp.join("")}</div>
    <div class="am-tabs" role="tablist">${M.tabs.map(t => `<button type="button" role="tab" data-tab="${t}" class="${t === AM.tab ? "on" : ""}" aria-selected="${t === AM.tab}">${esc(AM_TABS[t])}${t === "ogohlantirish" && (K.kechikkan + K.boshlanmagan + K.baholanmagan) ? ` <span class="n">${fmt(K.kechikkan + K.boshlanmagan + K.baholanmagan)}</span>` : ""}</button>`).join("")}</div>
    <div id="amBody"><p class="muted">Yuklanmoqda…</p></div>`;
  el.querySelectorAll("[data-tab]").forEach(b => b.onclick = () => { AM.tab = b.dataset.tab; AM.pid = null; renderAmaliyot(); });
  await amTab();
}
async function amTab() {
  const box = $("#amBody");
  try {
    if (AM.tab === "davrlar") await (AM.pid ? amPeriod(box, AM.pid) : amPeriods(box));
    else await ({ogohlantirish: amAlerts, bazalar: amBases, statistika: amStats})[AM.tab](box);
  } catch (e) { if (e?.message === "auth") return; box.innerHTML = e?.message === "denied" ? locked("Bu bo'lim") : `<div class="card am-card"><p>${esc(e?.msg || "Ma'lumotni yuklab bo'lmadi")}</p></div>`; }
}

/* ---------------- Davrlar ---------------- */
async function amPeriods(box) {
  const M = AM.meta;
  const rows = await amApi("/api/practice/periods?" + new URLSearchParams({status: AM.st, q: AM.q}));
  const segs = [["", "Hammasi"], ["davom etmoqda", "Davom etmoqda"], ["hisobot topshirish", "Hisobot topshirish"], ["kutilmoqda", "Kutilmoqda"], ["yakunlangan", "Yakunlangan"]];
  box.innerHTML = `<div class="card am-card"><div class="am-bar">
      <div class="am-seg">${segs.map(([k, t]) => `<button type="button" data-st="${esc(k)}" class="${k === AM.st ? "on" : ""}">${esc(t)}</button>`).join("")}</div>
      <input type="search" id="amQ" placeholder="Guruh, yo'nalish yoki amaliyot nomi" value="${esc(AM.q)}">
      ${M.caps.edit ? `<button type="button" class="btn" id="amPlan">O'quv reja bo'yicha</button><button type="button" class="btn primary" id="amNew">Yangi davr</button>` : ""}
    </div>
    ${amTable([["Guruh", r => `<b>${esc(r.grp)}</b><small>${esc(r.direction)} · ${esc(r.dept || "")}</small>`],
               ["Amaliyot", r => `${esc(r.title)}<small>${esc(M.kinds[r.kind] || r.kind)} · ${r.credits} kredit${r.source === "o'quv reja" ? " · o'quv reja" : ""}</small>`],
               ["Muddat", r => `${amD(r.start)} – ${amD(r.end)}<small>hisobot: ${amD(r.report_due)}</small>`, "num"],
               ["Holat", r => amChip(r.state, AM_PST_CLS[r.state])],
               ["Biriktirilgan", r => `${amN(r.assigned)}${r.unassigned ? ` <small class="am-bad">biriktirilmagan: ${r.unassigned}</small>` : ""}`, "num"],
               ["Hisobot / baho", r => `${amN(r.counts.hisobot + r.counts.baholandi)} / ${amN(r.counts.baholandi)}${r.avg_score != null ? `<small>o'rtacha ${r.avg_score}</small>` : ""}`, "num"],
               ["Ogohlantirish", r => r.alerts ? amChip(r.alerts + " ta", "bad") : amChip("yo'q", "ok")]],
              rows, {click: true, empty: "Amaliyot davrlari topilmadi"})}</div>`;
  box.querySelectorAll("[data-st]").forEach(b => b.onclick = () => { AM.st = b.dataset.st; amTab(); });
  const q = box.querySelector("#amQ"); let t = null;
  q.oninput = () => { clearTimeout(t); t = setTimeout(() => { AM.q = q.value.trim(); amTab().then(() => { const n = $("#amQ"); n.focus(); n.setSelectionRange(n.value.length, n.value.length); }); }, 350); };
  amBindRows(box, rows, r => { AM.pid = r.id; amTab(); });
  box.querySelector("#amNew")?.addEventListener("click", amNewPeriod);
  box.querySelector("#amPlan")?.addEventListener("click", amPlan);
}
function amNewPeriod() {
  const M = AM.meta, sel = new Map();
  const m = amModal("Yangi amaliyot davri (jadval bo'yicha)", `
    <label>Guruhlar<input type="search" id="amGq" placeholder="Guruh nomi yoki yo'nalish (kamida 2 harf)"></label>
    <div class="am-pick" id="amGl"></div><div class="am-sel" id="amGs"><small class="muted">Guruh tanlanmagan</small></div>
    <label>Turi<select id="amK">${Object.entries(M.kinds).map(([k, v]) => `<option value="${k}">${esc(v)}</option>`).join("")}</select></label>
    <label>Nomi (ixtiyoriy)<input id="amT" maxlength="160" placeholder="Masalan: Ishlab chiqarish amaliyoti"></label>
    <div class="row3"><label>Boshlanish<input type="date" id="amS"></label><label>Tugash<input type="date" id="amE"></label><label>Hisobot muddati<input type="date" id="amR"></label></div>
    <label>Kredit<input type="number" id="amC" min="1" max="30" value="6"></label>
    <p class="muted am-note">Hisobot muddati bo'sh qolsa — tugashdan keyin ${M.rules.report_after_days} kun. Shu vaqtda boshqa amaliyoti bor guruh o'tkazib yuboriladi.</p>`,
    async root => {
      const r = await amApi("/api/practice/periods", {group_ids: [...sel.keys()], kind: root.querySelector("#amK").value, title: root.querySelector("#amT").value,
        start: root.querySelector("#amS").value, end: root.querySelector("#amE").value, report_due: root.querySelector("#amR").value, credits: +root.querySelector("#amC").value});
      if (!r) return false;
      toast(`Yaratildi: ${r.created.length} ta davr${r.skipped.length ? ` · o'tkazib yuborildi: ${r.skipped.map(x => x.group).join(", ")}` : ""}`);
      renderAmaliyot(); return true;
    }, "Yaratish");
  const drawSel = () => { m.querySelector("#amGs").innerHTML = sel.size ? [...sel.values()].map(g => `<button type="button" class="am-chip info" data-rm="${g.id}">${esc(g.name)} ✕</button>`).join("") : `<small class="muted">Guruh tanlanmagan</small>`;
    m.querySelectorAll("[data-rm]").forEach(b => b.onclick = () => { sel.delete(+b.dataset.rm); drawSel(); }); };
  let t = null; const inp = m.querySelector("#amGq"), list = m.querySelector("#amGl");
  inp.oninput = () => { clearTimeout(t); t = setTimeout(async () => {
    if (inp.value.trim().length < 2) { list.innerHTML = ""; return; }
    const rs = await amApi("/api/practice/lookup/groups?q=" + encodeURIComponent(inp.value.trim())).catch(() => []);
    list.innerHTML = rs.map((g, i) => `<button type="button" data-i="${i}">${esc(g.name)} <small>${g.course}-kurs · ${esc(g.direction)} · ${esc(g.form)}</small></button>`).join("") || `<small class="muted">Topilmadi</small>`;
    list.querySelectorAll("button").forEach(b => b.onclick = () => { const g = rs[+b.dataset.i]; sel.set(g.id, g); drawSel(); });
  }, 250); };
}
async function amPlan() {
  let term = 2;
  const load = async () => amApi("/api/practice/plan?term=" + term);
  let d = await load();
  const m = amModal("O'quv reja bo'yicha amaliyot davrlari", `<div id="amPl"></div>`, async root => {
    const ids = [...root.querySelectorAll("input[data-g]:checked")].map(x => +x.dataset.g);
    if (!ids.length) { toast("Guruh tanlanmagan"); return false; }
    const r = await amApi("/api/practice/periods/from-curriculum", {term, group_ids: ids, start: root.querySelector("#amPs").value, end: root.querySelector("#amPe").value,
                                                                    report_due: root.querySelector("#amPr").value});
    if (!r) return false;
    toast(`Yaratildi: ${r.created.length} ta davr${r.skipped.length ? ` · o'tkazildi: ${r.skipped.length}` : ""}`); renderAmaliyot(); return true;
  }, "Davrlarni yaratish", true);
  const draw = () => {
    const free = d.rows.filter(r => !r.exists);
    m.querySelector("#amPl").innerHTML = `<div class="am-seg">${[[1, "Joriy semestr"], [2, "Keyingi semestr"]].map(([k, t]) => `<button type="button" data-term="${k}" class="${k === term ? "on" : ""}">${t}</button>`).join("")}</div>
      <p class="muted am-note">${d.year}-${d.year + 1} o'quv yili, ${esc(d.season)} semestr. O'quv rejasida (curriculum) joyda o'tadigan amaliyot fani bor guruhlar: ${d.rows.length} ta, shundan davri hali yaratilmagan: ${free.length} ta.</p>
      <div class="row3"><label>Boshlanish<input type="date" id="amPs" value="${d.start}"></label><label>Tugash<input type="date" id="amPe" value="${d.end}"></label><label>Hisobot muddati<input type="date" id="amPr" value="${d.report_due}"></label></div>
      <label class="am-ck"><input type="checkbox" id="amPall" ${free.length ? "checked" : "disabled"}> Hammasini tanlash</label>
      <div class="am-plan">${d.rows.map(r => `<label class="am-ck${r.exists ? " dim" : ""}"><input type="checkbox" data-g="${r.group_id}" ${r.exists ? "disabled" : "checked"}>
        <span><b>${esc(r.grp)}</b> · ${esc(r.subject)} (${r.credits} kr) <small>${esc(r.direction)} · ${r.course}-kurs · ${esc(r.form)} · ${r.sem_no}-semestr${r.exists ? " · davr bor" : ""}</small></span></label>`).join("") || `<div class="am-empty">Bu semestrda o'quv rejasida amaliyot yo'q</div>`}</div>`;
    m.querySelectorAll("[data-term]").forEach(b => b.onclick = async () => { term = +b.dataset.term; d = await load(); draw(); });
    m.querySelector("#amPall").onchange = e => m.querySelectorAll("input[data-g]:not(:disabled)").forEach(x => x.checked = e.target.checked);
  };
  draw();
}
async function amPeriod(box, pid) {
  const M = AM.meta, d = await amApi("/api/practice/periods/" + pid), p = d.period;
  const back = `<button type="button" class="btn ghost sm" id="amBack">← Davrlar</button>`;
  const act = [];
  if (M.caps.edit) {
    act.push(`<button type="button" class="btn primary" id="amAssign" ${d.unassigned.length ? "" : "disabled"}>Talabalarni biriktirish${d.unassigned.length ? ` (${d.unassigned.length})` : ""}</button>`);
    act.push(`<button type="button" class="btn" id="amRef">Yo'llanmalar</button>`);
    if (!d.rows.length) act.push(`<button type="button" class="btn ghost" id="amDel">Davrni o'chirish</button>`);
  }
  if (M.caps.supervisor && d.rows.length) act.push(`<button type="button" class="btn" id="amSup">Amaliyot rahbari</button>`);
  const fl = AM.meta.flag_titles;
  box.innerHTML = `<div class="card am-card"><div class="am-bar">${back}<div class="am-ptitle"><h3>${esc(p.grp)} · ${esc(p.title)}</h3>
      <span class="muted">${esc(p.direction)} · ${esc(p.dept || "")} · ${amD(p.start)} – ${amD(p.end)} · hisobot muddati ${amD(p.report_due)} · ${p.credits} kredit</span></div>
      ${amChip(p.state, AM_PST_CLS[p.state])}</div>
    <div class="am-acts left">${act.join("")}</div>
    ${d.unassigned.length && !M.caps.edit ? `<p class="am-note am-bad">Biriktirilmagan talabalar: ${d.unassigned.length} ta (Amaliyot bo'limi biriktiradi)</p>` : ""}
    ${amTable([["Talaba", r => `<b>${esc(r.full_name)}</b><small>${esc(r.hemis_id)}</small>`],
               ["Baza", r => `${esc(r.base || "—")}<small>${esc(r.org_supervisor || "")}${r.doc_reg ? ` · yo'llanma ${esc(r.doc_reg)}` : ""}</small>`],
               ["Kafedra rahbari", r => esc(r.kaf_supervisor || "—")],
               ["Holat", r => amChip(M.statuses[r.status] || r.status, AM_ST_CLS[r.status]) + r.flags.map(f => " " + amChip(fl[f], "bad")).join("")],
               ["Kundalik", r => amN(r.diary_n), "num"],
               ["Ball", r => r.score != null ? `<b>${r.score}</b>` : "—", "num"]],
              d.rows, {click: M.caps.names, rowCls: r => r.flags.length ? "am-badrow" : "", empty: "Bu davrda hali talaba biriktirilmagan"})}</div>`;
  box.querySelector("#amBack").onclick = () => { AM.pid = null; amTab(); };
  if (M.caps.names) amBindRows(box, d.rows, r => amAssignView(r.id));
  box.querySelector("#amAssign")?.addEventListener("click", () => amAssign(d));
  box.querySelector("#amSup")?.addEventListener("click", () => amSup(d));
  const ref = box.querySelector("#amRef");
  if (ref) ref.onclick = () => { if (!arm(ref, "Yo'llanmalarni ro'yxatga olish")) return;
    busy(ref, async () => { const r = await amApi(`/api/practice/periods/${pid}/referrals`, {}); if (r) { toast(`Yo'llanma berildi: ${r.issued} ta (Hujjatlar markazi reyestrida)${r.left ? ` · qoldi ${r.left}` : ""}`); amTab(); } }); };
  const del = box.querySelector("#amDel");
  if (del) del.onclick = () => { if (!arm(del, "Ha, o'chirish")) return; busy(del, async () => { const r = await amApi(`/api/practice/periods/${pid}/delete`, {}); if (r) { toast("Davr o'chirildi"); AM.pid = null; renderAmaliyot(); } }); };
}
function amAssign(d) {
  const p = d.period;
  const m = amModal(`Biriktirish · ${p.grp}`, `
    <label>Amaliyot bazasi<select id="amB">${d.bases.map(b => `<option value="${b.id}" ${b.ok && b.capacity - b.used > 0 ? "" : "disabled"}>${esc(b.name)} — bo'sh ${Math.max(0, b.capacity - b.used)} / ${b.capacity}${b.ok ? "" : " · shartnoma muddati yetmaydi"}</option>`).join("")}</select></label>
    <label>Kafedradan amaliyot rahbari<select id="amKs"><option value="">— keyinroq —</option>${d.teachers.map(t => `<option value="${t.id}">${esc(t.full_name)}${t.position ? " · " + esc(t.position) : ""}</option>`).join("")}</select></label>
    <div class="row2"><label>Tashkilotdan rahbar<input id="amOs" maxlength="120"></label><label>Telefon<input id="amOp" maxlength="40"></label></div>
    <label class="am-ck"><input type="checkbox" id="amAll" checked> Barcha biriktirilmagan talabalar (${d.unassigned.length} ta)</label>
    <div class="am-plan" id="amSl" hidden>${d.unassigned.map(s => `<label class="am-ck"><input type="checkbox" data-s="${s.id}"><span>${esc(s.full_name)} <small>${esc(s.hemis_id)}</small></span></label>`).join("")}</div>
    <p class="muted am-note">Sig'im shu yo'nalish bo'yicha va shu muddatda kesishgan barcha davrlar hisobidan tekshiriladi.</p>`,
    async root => {
      const all = root.querySelector("#amAll").checked;
      const r = await amApi(`/api/practice/periods/${p.id}/assign`, {base_id: +root.querySelector("#amB").value, all_unassigned: all,
        student_ids: all ? [] : [...root.querySelectorAll("input[data-s]:checked")].map(x => +x.dataset.s),
        kaf_supervisor_id: +root.querySelector("#amKs").value || null, org_supervisor: root.querySelector("#amOs").value, org_phone: root.querySelector("#amOp").value});
      if (!r) return false;
      toast(`Biriktirildi: ${r.assigned} ta · bazada bo'sh joy: ${r.free_left}`); renderAmaliyot(); return true;
    }, "Biriktirish");
  m.querySelector("#amAll").onchange = e => { m.querySelector("#amSl").hidden = e.target.checked; };
}
function amSup(d) {
  const p = d.period;
  amModal(`Amaliyot rahbari · ${p.grp}`, `
    <label>Kafedradan amaliyot rahbari (barcha talabalar uchun)<select id="amKs"><option value="">— o'zgarmaydi —</option>${d.teachers.map(t => `<option value="${t.id}">${esc(t.full_name)}</option>`).join("")}</select></label>
    <div class="row2"><label>Tashkilotdan rahbar<input id="amOs" maxlength="120" placeholder="o'zgarmaydi"></label><label>Telefon<input id="amOp" maxlength="40"></label></div>`,
    async root => {
      const r = await amApi(`/api/practice/periods/${p.id}/supervisor`, {kaf_supervisor_id: +root.querySelector("#amKs").value || null,
        org_supervisor: root.querySelector("#amOs").value, org_phone: root.querySelector("#amOp").value});
      if (!r) return false; toast(`Yangilandi: ${r.updated} ta talaba`); amTab(); return true;
    });
}
async function amAssignView(aid) {
  const M = AM.meta, a = await amApi("/api/practice/assign/" + aid);
  const acts = [];
  if (M.caps.review) {
    if (a.status === "biriktirildi") acts.push(`<button type="button" class="btn" data-a="start">Amaliyotga chiqdi</button>`);
    if (["boshlandi", "qaytarildi"].includes(a.status)) acts.push(`<button type="button" class="btn" data-a="receive">Qog'oz hisobotni qabul qilish</button>`);
    if (a.status === "hisobot") acts.push(`<button type="button" class="btn" data-a="return">Qayta ishlashga qaytarish</button>`);
  }
  if (a.can_grade && ["hisobot", "baholandi"].includes(a.status)) acts.push(`<button type="button" class="btn primary" data-a="grade">${a.status === "baholandi" ? "Bahoni o'zgartirish" : "Baholash"}</button>`);
  const fl = M.flag_titles;
  const m = amModal(`${a.full_name} · ${a.title}`, `
    <dl class="am-kv"><dt>Guruh</dt><dd>${esc(a.grp)} · HEMIS ${esc(a.hemis_id)}</dd><dt>Muddat</dt><dd>${amD(a.start)} – ${amD(a.end)} · hisobot ${amD(a.report_due)}</dd>
      <dt>Baza</dt><dd>${esc(a.base || "—")}</dd><dt>Tashkilotdan rahbar</dt><dd>${esc(a.org_supervisor || "—")} ${esc(a.org_phone || "")}</dd>
      <dt>Kafedra rahbari</dt><dd>${esc(a.kaf_supervisor || "—")}</dd><dt>Yo'llanma</dt><dd>${esc(a.doc_reg || "berilmagan")}</dd>
      <dt>Holat</dt><dd>${amChip(M.statuses[a.status], AM_ST_CLS[a.status])}${a.flags.map(f => " " + amChip(fl[f], "bad")).join("")}</dd>
      ${a.score != null ? `<dt>Baho</dt><dd><b>${a.score}</b> ball · «${esc(a.letter)}» · ${esc(a.graded_name || "")} ${amD(a.graded_at)}${a.grade_note ? ` · ${esc(a.grade_note)}` : ""}</dd>` : ""}
      ${a.return_note ? `<dt>Qaytarilgan</dt><dd class="am-bad">${esc(a.return_note)}</dd>` : ""}</dl>
    ${a.report_text ? `<h4>Hisobot (${a.report_by === "talaba" ? "talaba kabinetidan" : "qog'ozda, qabul qildi: " + esc(a.report_by)} · ${amD(a.report_at)})</h4><div class="am-report">${esc(a.report_text)}</div>` : ""}
    <h4>Kundalik (${a.diary.length})</h4><div class="am-diary">${a.diary.map(x => `<div class="${x.author_kind === "rahbar" ? "rh" : ""}"><b>${amD(x.day)}</b> ${esc(x.text)}<small>${esc(x.author)}</small></div>`).join("") || `<div class="am-empty">Yozuv yo'q</div>`}</div>
    ${M.caps.review ? `<div class="am-add"><input id="amDt" maxlength="2000" placeholder="Rahbar izohi kundalikka"><button type="button" class="btn sm" id="amDa">Qo'shish</button></div>` : ""}
    <div class="am-acts left">${acts.join("")}</div>`, null, "", true);
  const reload = () => { m.close(); amAssignView(aid); amTab(); };
  m.querySelector("#amDa")?.addEventListener("click", async () => { const r = await amApi(`/api/practice/assign/${aid}/diary`, {text: m.querySelector("#amDt").value}); if (r) reload(); });
  m.querySelectorAll("[data-a]").forEach(b => b.onclick = async () => {
    const k = b.dataset.a;
    if (k === "start") { const r = await amApi(`/api/practice/assign/${aid}/status`, {status: "start"}); if (r) { toast("Belgilandi: amaliyotda"); reload(); } }
    else if (k === "receive") amModal("Qog'oz hisobotni qabul qilish", `<label>Hisobot qisqa mazmuni<textarea id="amRt" maxlength="4000"></textarea></label>`, async r2 => {
      const r = await amApi(`/api/practice/assign/${aid}/status`, {status: "receive", report: r2.querySelector("#amRt").value}); if (r) { toast("Hisobot qabul qilindi"); reload(); } return !!r; }, "Qabul qilish");
    else if (k === "return") amModal("Hisobotni qaytarish", `<label>Sabab (talabaga ko'rinadi)<textarea id="amRn" maxlength="500"></textarea></label>`, async r2 => {
      const r = await amApi(`/api/practice/assign/${aid}/status`, {status: "return", note: r2.querySelector("#amRn").value}); if (r) { toast("Qaytarildi"); reload(); } return !!r; }, "Qaytarish");
    else if (k === "grade") amModal("Amaliyot bahosi", `<label>Ball (0–100; o'tish — 40)<input type="number" id="amSc" min="0" max="100" value="${a.score ?? ""}"></label>
        <label>Izoh${a.status === "baholandi" ? " (o'zgartirish sababi — majburiy)" : ""}<textarea id="amSn" maxlength="500"></textarea></label>`, async r2 => {
      const v = r2.querySelector("#amSc").value; if (v === "") { toast("Ballni kiriting"); return false; }
      const r = await amApi(`/api/practice/assign/${aid}/grade`, {score: +v, note: r2.querySelector("#amSn").value});
      if (r) { toast(`Baho saqlandi: «${r.letter}»${r.passed ? "" : " — o'tmadi, qayta topshirish kerak"}`); reload(); } return !!r; }, "Saqlash");
  });
}

/* ---------------- Ogohlantirishlar ---------------- */
async function amAlerts(box) {
  const M = AM.meta, d = await amApi("/api/practice/alerts"), fl = M.flag_titles;
  const sec = (k, extra) => {
    const rows = d.items[k] || [];
    return `<div class="card am-card"><h3>${esc(fl[k])} <span class="am-cnt">${fmt(d.counts[k] || 0)}</span></h3><p class="muted">${esc(extra)}</p>
      ${amTable([["Talaba", r => `<b>${esc(r.full_name)}</b><small>${esc(r.grp)}</small>`], ["Amaliyot", r => `${esc(r.title)}<small>${amD(r.start)} – ${amD(r.end)}</small>`],
                 ["Hisobot muddati", r => amD(r.report_due), "num"], ["Baza", r => esc(r.base || "—")], ["Kafedra rahbari", r => esc(r.kaf_supervisor || "—")]],
                rows.slice(0, 100), {click: M.caps.names, empty: "Yo'q"})}${rows.length > 100 ? `<p class="muted am-note">Yana ${rows.length - 100} ta</p>` : ""}</div>`;
  };
  box.innerHTML = sec("hisobot_kechikdi", "Hisobot topshirish muddati o'tgan, hisobot yo'q. Kafedra rahbari va tyutor talaba bilan bog'lanadi.") +
    sec("boshlanmagan", `Amaliyot boshlanganiga ${M.rules.start_grace_days} kundan ko'p bo'ldi, «amaliyotga chiqdi» belgilanmagan.`) +
    sec("baholanmagan", `Hisobot topshirilganiga ${M.rules.grade_days} kundan ko'p bo'ldi, baho qo'yilmagan.`) +
    (d.unassigned.length ? `<div class="card am-card"><h3>Biriktirilmagan talabalar</h3>${amTable([["Guruh", r => `<b>${esc(r.grp)}</b>`], ["Amaliyot", r => esc(r.title)], ["Boshlanish", r => amD(r.start), "num"], ["Talabalar", r => fmt(r.n), "num"]], d.unassigned)}</div>` : "") +
    (d.agreements.length ? `<div class="card am-card"><h3>Shartnoma muddati</h3>${amTable([["Baza", r => `<b>${esc(r.name)}</b><small>${esc(r.agreement_no || "")}</small>`], ["Muddat", r => amD(r.agreement_expires), "num"],
        ["Holat", r => amChip(r.agreement_state, AM_AGR_CLS[r.agreement_state])], ["Kelgusi talabalar", r => fmt(r.future_students), "num"]], d.agreements)}</div>` : "");
  box.querySelectorAll(".am-card").forEach((card, i) => {
    const k = ["hisobot_kechikdi", "boshlanmagan", "baholanmagan"][i];
    if (k && M.caps.names) amBindRows(card, (d.items[k] || []).slice(0, 100), r => amAssignView(r.id));
  });
}

/* ---------------- Bazalar ---------------- */
async function amBases(box) {
  const M = AM.meta, rows = await amApi("/api/practice/bases");
  box.innerHTML = `<div class="card am-card"><div class="am-bar"><h3>Amaliyot bazalari <span class="am-cnt">${rows.length}</span></h3>
      ${M.caps.edit ? `<button type="button" class="btn primary" id="amBn">Baza qo'shish</button>` : ""}</div>
    ${amTable([["Tashkilot", r => `<b>${esc(r.name)}</b><small>${esc(M.base_kinds[r.kind] || r.kind || "")} · ${esc(r.address || "")}</small>`],
               ["Shartnoma", r => `${esc(r.agreement_no || "—")}<small>${amD(r.agreement_date)} – ${amD(r.agreement_expires)}</small>`],
               ["Holat", r => amChip(r.agreement_state, AM_AGR_CLS[r.agreement_state])],
               ["Sig'im (yo'nalish: band / jami)", r => r.caps.map(c => `<small>${esc(c.direction)}: ${c.now} / ${c.capacity}</small>`).join("")],
               ["Bog'lanish", r => `${esc(r.contact_name || "—")}<small>${esc(r.contact_phone || "")}</small>`],
               ["Jami talabalar", r => fmt(r.students_total), "num"]],
              rows, {click: M.caps.edit, empty: "Bazalar yo'q"})}</div>`;
  box.querySelector("#amBn")?.addEventListener("click", () => amBaseForm(null));
  if (M.caps.edit) amBindRows(box, rows, r => amBaseForm(r));
}
function amBaseForm(b) {
  const M = AM.meta, caps = Object.fromEntries((b?.caps || []).map(c => [c.direction, c.capacity]));
  const m = amModal(b ? "Bazani tahrirlash" : "Yangi amaliyot bazasi", `
    <label>Tashkilot nomi<input id="bN" maxlength="200" value="${esc(b?.name || "")}"></label>
    <div class="row2"><label>Turi<select id="bK">${Object.entries(M.base_kinds).map(([k, v]) => `<option value="${k}" ${b?.kind === k ? "selected" : ""}>${esc(v)}</option>`).join("")}</select></label>
      <label>Manzil<input id="bA" maxlength="300" value="${esc(b?.address || "")}"></label></div>
    <div class="row2"><label>Mas'ul shaxs<input id="bC" maxlength="120" value="${esc(b?.contact_name || "")}"></label><label>Telefon<input id="bP" maxlength="40" value="${esc(b?.contact_phone || "")}"></label></div>
    <div class="row3"><label>Shartnoma raqami<input id="bNo" maxlength="60" value="${esc(b?.agreement_no || "")}"></label><label>Imzolangan<input type="date" id="bD" value="${esc(b?.agreement_date || "")}"></label>
      <label>Amal qiladi<input type="date" id="bE" value="${esc(b?.agreement_expires || "")}"></label></div>
    <h4>Yo'nalishlar bo'yicha sig'im (bir vaqtda)</h4>
    <div class="am-caps">${M.directions.map(d => `<label><span>${esc(d)}</span><input type="number" min="0" max="500" data-dir="${esc(d)}" value="${caps[d] || ""}" placeholder="0"></label>`).join("")}</div>
    ${b ? `<div class="am-acts left"><button type="button" class="btn ghost" id="bSt">${b.status === "faol" ? "Hamkorlikni to'xtatish" : "Qayta faollashtirish"}</button></div>` : ""}`,
    async root => {
      const caps2 = {}; root.querySelectorAll("[data-dir]").forEach(i => { if (+i.value > 0) caps2[i.dataset.dir] = +i.value; });
      const body = {name: root.querySelector("#bN").value, kind: root.querySelector("#bK").value, address: root.querySelector("#bA").value, contact_name: root.querySelector("#bC").value,
        contact_phone: root.querySelector("#bP").value, agreement_no: root.querySelector("#bNo").value, agreement_date: root.querySelector("#bD").value,
        agreement_expires: root.querySelector("#bE").value, caps: caps2};
      const r = await amApi(b ? `/api/practice/bases/${b.id}` : "/api/practice/bases", body);
      if (!r) return false; toast(b ? "Baza saqlandi" : "Baza qo'shildi"); amTab(); return true;
    }, "Saqlash", true);
  const st = m.querySelector("#bSt");
  if (st) st.onclick = () => { if (!arm(st, "Tasdiqlash")) return;
    busy(st, async () => { const r = await amApi(`/api/practice/bases/${b.id}/status`, {status: b.status === "faol" ? "to'xtatilgan" : "faol"}); if (r) { toast("Holat o'zgardi"); m.close(); amTab(); } }); };
}

/* ---------------- Statistika ---------------- */
async function amStats(box) {
  const M = AM.meta, d = await amApi("/api/practice/stats");
  box.innerHTML = `<div class="card am-card"><h3>Amaliyot turlari bo'yicha</h3>${amTable([["Turi", r => esc(r.title)], ["Talabalar", r => fmt(r.students), "num"], ["O'rtacha ball", r => r.avg_score ?? "—", "num"]], d.by_kind)}</div>
    <div class="card am-card"><h3>Bazalar bo'yicha</h3>${amTable([["Baza", r => `<b>${esc(r.name)}</b><small>${esc(M.base_kinds[r.kind] || "")}</small>`], ["Talabalar", r => fmt(r.students || 0), "num"],
      ["Baholangan", r => fmt(r.graded || 0), "num"], ["O'rtacha ball", r => r.avg_score ?? "—", "num"], ["O'tmagan (<40)", r => r.failed ? `<span class="am-bad">${r.failed}</span>` : "0", "num"]], d.by_base)}</div>
    <div class="card am-card"><h3>Guruhlar bo'yicha</h3>${amTable([["Guruh", r => `<b>${esc(r.grp)}</b><small>${esc(r.direction)}</small>`], ["Amaliyot", r => `${esc(r.title)}<small>${amD(r.start)} – ${amD(r.end)}</small>`],
      ["Qamrov", r => `${fmt(r.students || 0)} / ${fmt(r.group_size || 0)}`, "num"], ["Hisobot", r => fmt(r.reported || 0), "num"], ["Baholangan", r => fmt(r.graded || 0), "num"],
      ["O'rtacha ball", r => r.avg_score ?? "—", "num"], ["O'tmagan", r => r.failed ? `<span class="am-bad">${r.failed}</span>` : "0", "num"]], d.by_group)}</div>`;
}
