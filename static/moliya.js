/* =====================================================================
   «Moliya» — Buxgalteriya va Moliya-iqtisod prorektori (app/moliya.py, /api/moliya).
     Umumiy:      kontrakt tushumi, bugungi/haftalik to'lovlar, byudjet ijrosi, ogohlantirishlar (rektor/kengash — faqat shu va byudjet).
     To'lovlar:   reyestr (qidiruv, kun/oy, usul), qo'lda kiritish (kvitansiya, sana, summa, usul), storno (sabab bilan).
     Solishtirish: kun bo'yicha tizim ↔ bank/kassa ko'chirmasi, kunni yopish; moliya prorektori — qayta ochish.
     Byudjet:     moddalar bo'yicha reja/fakt/tasdiq kutmoqda, ijro %, oylik jadval; prorektor — yillik rejani o'zgartiradi.
     Xarajatlar:  kiritish (limitdan katta yoki moddadan oshsa — prorektor tasdig'i), tasdiqlash/rad etish.
     Xaridlar:    Xarid bo'limi buyurtma bergan so'rovlarni moliyalashtirish.
     Hisobotlar:  oylik .xlsx / .csv.
     Talaba:      Registrator ofisi — talabaning to'lov holati va tarixi (faqat o'qish).
   Ruxsat serverda tekshiriladi. Global: renderMoliya() — app.js go() chaqiradi.
   ===================================================================== */
const ML = {bank: {status: "aniqlanmagan", q: ""}, meta: null, tab: null, pay: {q: "", day: "", method: "", status: "", page: 1}, month: null, year: null, exp: "", stu: null};
if (!document.querySelector('link[href="moliya.css"]')) document.head.insertAdjacentHTML("beforeend", '<link rel="stylesheet" href="moliya.css">');
if (typeof ICONS === "object" && !ICONS.plus) ICONS.plus = '<path d="M12 5v14M5 12h14"/>';
const ML_TABS = {overview: "Umumiy", bank: "Aniqlanmagan to'lovlar", payments: "To'lovlar", recon: "Kunlik solishtirish", budget: "Byudjet ijrosi", expenses: "Xarajatlar",
  procurement: "Xaridlar", reports: "Hisobotlar", student: "Talaba to'lovlari"};
const mlS = n => n == null ? "—" : fmt(Math.round(n)) + " so'm";
const mlN = n => n == null ? "—" : fmt(n);
const mlD = s => { s = String(s || "").slice(0, 10); return s.length === 10 ? `${s.slice(8, 10)}.${s.slice(5, 7)}.${s.slice(0, 4)}` : "—"; };
const mlChip = (t, cls = "") => `<span class="ml-chip ${cls}">${esc(t)}</span>`;
const mlKpi = (label, val, sub = "", cls = "") => `<div class="ml-kpi ${cls}"><span>${esc(label)}</span><b>${val}</b>${sub ? `<small>${sub}</small>` : ""}</div>`;
const mlStCls = s => ({"faol": "ok", "storno": "bad", "yopildi": "ok", "farq bilan yopildi": "warn", "ochiq": "", "qayta ochildi": "warn", "kutilmoqda": "warn",
  "tasdiqlandi": "ok", "rad etildi": "bad", "bekor qilindi": "", "me'yorda": "ok", "chegaraga yaqin": "warn", "oshib ketgan": "bad", "tasdiqlansa oshadi": "warn",
  "to'langan": "ok", "tasdiq kutmoqda": "warn", "moliyalashtirilmagan": "info"})[s] || "";
const mlProg = pct => `<div class="ml-prog ${pct > 100 ? "bad" : pct >= (ML.meta?.warn_pct || 90) ? "warn" : ""}" title="${pct ?? "—"}%"><i style="width:${Math.min(100, pct || 0)}%"></i></div>`;
async function mlApi(url, body) {
  const r = await fetch(url, {method: body === undefined ? "GET" : "POST", credentials: "same-origin", headers: {"Content-Type": "application/json"},
                              body: body === undefined ? undefined : JSON.stringify(body)});
  if (r.status === 401) { showLogin(); throw new Error("auth"); }
  const d = await r.json().catch(() => ({}));
  if (!r.ok) {
    const det = d.detail; const m = d.message || (typeof det === "string" ? det : Array.isArray(det) ? "Maydonlar to'liq emas yoki noto'g'ri" : "") || "Xatolik yuz berdi";
    if (body !== undefined) { toast(m); return null; }
    const e = new Error(r.status === 403 ? "denied" : "api"); e.msg = m; throw e;
  }
  return d;
}
const mlQs = o => new URLSearchParams(Object.entries(o).filter(([, v]) => v !== "" && v != null)).toString();
function mlTable(cols, rows, {rowCls = () => "", empty = "Ma'lumot yo'q"} = {}) {
  if (!rows.length) return `<div class="ml-empty">${esc(empty)}</div>`;
  return `<div class="tw"><table class="ml-t stack"><thead><tr>${cols.map(c => `<th>${esc(c[0])}</th>`).join("")}</tr></thead><tbody>` +
    rows.map((r, i) => `<tr class="${rowCls(r)}" data-i="${i}">${cols.map(c => `<td data-l="${esc(c[0])}" class="${c[2] || ""}"><div class="ml-c">${c[1](r) ?? ""}</div></td>`).join("")}</tr>`).join("") + `</tbody></table></div>`;
}
function mlModal(title, html, onOk, okText = "Saqlash") {
  const bg = document.createElement("div"); bg.className = "ml-modal-bg";
  bg.innerHTML = `<div class="ml-modal" role="dialog" aria-modal="true" aria-label="${esc(title)}"><h3>${esc(title)}</h3>${html}
    <div class="ml-acts"><button type="button" class="btn ghost" data-x>Bekor qilish</button>${onOk ? `<button type="button" class="btn primary" data-ok>${esc(okText)}</button>` : ""}</div></div>`;
  document.body.appendChild(bg);
  const close = () => bg.remove();
  bg.addEventListener("click", e => { if (e.target === bg || e.target.closest("[data-x]")) close(); });
  bg.addEventListener("keydown", e => { if (e.key === "Escape") close(); });
  const ok = bg.querySelector("[data-ok]");
  if (ok) ok.onclick = async () => { ok.disabled = true; try { if (await onOk(bg)) close(); } finally { ok.disabled = false; } };
  setTimeout(() => bg.querySelector("input,select,textarea,button")?.focus(), 30);
  return bg;
}
const mlMoney = v => parseInt(String(v || "").replace(/[^\d]/g, ""), 10) || 0;

async function renderMoliya() {
  const el = $("#v-moliya");
  if (!el.innerHTML) el.innerHTML = `<p class="muted">Yuklanmoqda…</p>`;
  ML.meta = await mlApi("/api/moliya/meta");
  ML.month ||= ML.meta.today.slice(0, 7); ML.year ||= ML.meta.year;
  if (!ML.tab || !ML.meta.tabs.includes(ML.tab)) ML.tab = ML.meta.tabs[0];
  const note = {enter: "Buxgalteriya: to'lovlar va xarajatlar qo'lda kiritiladi (1C/bank importi ulanmagan). Kiritilgan to'lov darhol talabaning kontrakt holatiga, Talabalar markazi va Talaba kabinetiga ta'sir qiladi.",
    approve: `Moliya-iqtisod prorektori: ${fmt(ML.meta.limit)} so'mdan katta yoki moddadan oshadigan xarajatlar tasdig'i, yillik reja, yopilgan kunlar.`,
    agg: "Rahbariyat uchun jamlangan ko'rinish: talabalar ism-shariflari ko'rsatilmaydi.",
    student: "Registrator ofisi: talabaning kontrakt to'lovi holati va tarixi (faqat o'qish). To'lovni buxgalteriya kiritadi."}[ML.meta.mode];
  el.innerHTML = `<div class="ml-head"><div><h2>Moliya</h2><span class="muted">${esc(note)}</span></div></div>
    ${ML.meta.tabs.length > 1 ? `<div class="ml-tabs" role="tablist">${ML.meta.tabs.map(t => `<button type="button" role="tab" data-tab="${t}" class="${t === ML.tab ? "on" : ""}" aria-selected="${t === ML.tab}">${esc(ML_TABS[t])}${t === "bank" && ML.meta.bank?.n ? ` <span class="n">${fmt(ML.meta.bank.n)}</span>` : ""}</button>`).join("")}</div>` : ""}
    <div id="mlBody"><p class="muted">Yuklanmoqda…</p></div>`;
  el.querySelectorAll("[data-tab]").forEach(b => b.onclick = () => { ML.tab = b.dataset.tab; renderMoliya(); });
  await mlTab();
}
async function mlTab() {
  const box = $("#mlBody");
  try { await ({overview: mlOverview, bank: mlBank, payments: mlPayments, recon: mlRecon, budget: mlBudget, expenses: mlExpenses, procurement: mlProc, reports: mlReports, student: mlStudentTab})[ML.tab](box); }
  catch (e) { if (e?.message === "auth") return; box.innerHTML = e?.message === "denied" ? locked("Bu bo'lim") : `<div class="card ml-card"><p>${esc(e?.msg || "Ma'lumotni yuklab bo'lmadi")}</p></div>`; }
}

/* ---------- Umumiy ---------- */
async function mlOverview(box) {
  const d = await mlApi("/api/moliya/overview"), C = d.contracts, B = d.budget;
  const mx = Math.max(1, ...d.days.map(x => x.s));
  box.innerHTML = `<div class="ml-kpis">
      ${mlKpi("Kontrakt tushumi", `${C.pct ?? "—"}%`, `${mln(C.paid)} / ${mln(C.total)} so'm`)}
      ${mlKpi("Qoldiq qarz", mln(C.debt), `${fmt(C.debtors)} ta talaba qarzdor`, C.debt ? "warn" : "ok")}
      ${mlKpi("Bugun kiritildi", mlS(d.today.sum), `${fmt(d.today.n)} ta to'lov`)}
      ${mlKpi("Oxirgi 7 kun", mln(d.week.sum), `${fmt(d.week.n)} ta to'lov`)}
      ${mlKpi(`Byudjet ijrosi ${B.year}`, `${B.pct ?? "—"}%`, `${mln(B.fact)} / ${mln(B.plan)} so'm`)}
      ${d.bank ? mlKpi("Aniqlanmagan to'lovlar", fmt(d.bank.n), d.bank.n ? `${mlS(d.bank.sum)}${d.bank.stale ? ` · ${d.bank.stale} tasi ${ML.meta.alert_days} kundan eski` : ""}` : "navbat bo'sh", d.bank.stale ? "bad" : d.bank.n ? "warn" : "ok") : ""}
      ${mlKpi("Tasdiq kutmoqda", fmt(d.pending.n), d.pending.n ? mlS(d.pending.s) : "xarajat yo'q", d.pending.n ? "warn" : "")}
    </div>
    ${d.alerts.length ? `<div class="ml-alerts">${d.alerts.map(a => `<div class="ml-alert ${a.level}">${esc(a.text)}</div>`).join("")}</div>` : ""}
    <div class="ml-grid2">
      <div class="card ml-card"><h3>Kunlik tushum (ISFT Core'da kiritilgan)</h3><p class="muted">Oxirgi 3 hafta · ustun ustiga olib boring</p>
        ${d.days.length ? `<div class="ml-days">${d.days.map(x => `<div class="${x.day === ML.meta.today ? "today" : ""}" style="height:${Math.round(100 * x.s / mx)}%" title="${mlD(x.day)}: ${mlS(x.s)} · ${x.n} ta"></div>`).join("")}</div>
        <div class="ml-dl">${d.days.map(x => `<span>${x.day.slice(8, 10)}</span>`).join("")}</div>` : `<div class="ml-empty">To'lov yo'q</div>`}</div>
      <div class="card ml-card"><h3>Byudjet moddalari</h3><p class="muted">Reja / fakt · ${B.year}</p>
        ${mlTable([["Modda", l => esc(l.category)], ["Ijro", l => `${mlProg(l.pct)}<small>${l.pct ?? "—"}% · ${mln(l.fact)}</small>`], ["Holat", l => mlChip(l.status, mlStCls(l.status))]], B.lines)}</div>
    </div>`;
}

/* ---------- To'lovlar ---------- */
async function mlPayments(box) {
  const P = ML.pay, d = await mlApi("/api/moliya/payments?" + mlQs({q: P.q, day: P.day, method: P.method, status: P.status, page: P.page}));
  const can = ML.meta.can;
  box.innerHTML = `<div class="card ml-card">
    <div class="ml-bar"><input type="search" id="mlQ" placeholder="Talaba, HEMIS ID yoki kvitansiya raqami" value="${esc(P.q)}">
      <input type="date" class="ml-in" id="mlDay" value="${esc(P.day)}" max="${ML.meta.today}" title="Kun">
      <select class="ml-in" id="mlMeth"><option value="">Barcha usullar</option>${Object.entries(ML.meta.methods).map(([k, v]) => `<option value="${k}" ${P.method === k ? "selected" : ""}>${esc(v)}</option>`).join("")}</select>
      <select class="ml-in" id="mlSt"><option value="">Barcha holatlar</option><option value="faol" ${P.status === "faol" ? "selected" : ""}>Faol</option><option value="storno" ${P.status === "storno" ? "selected" : ""}>Storno</option></select>
      ${can.enter ? `<button type="button" class="btn primary" id="mlNew">${ico("plus", 15)} To'lov kiritish</button>` : ""}</div>
    <p class="muted">${fmt(d.total)} ta yozuv · faol summasi ${mlS(d.sum)}</p>
    ${mlTable([["Sana", r => `${mlD(r.paid_on)}${r.day_closed ? `<small>kun yopilgan</small>` : ""}`], ["Kvitansiya", r => `<b>${esc(r.receipt_no)}</b><small>${esc(r.method_label)}${r.kind && r.kind !== "kontrakt" ? ` · ${esc(r.kind_label)}` : ""}</small>`],
      ["Talaba", r => `${esc(r.full_name)}<small>${esc(r.grp || "")} · ${esc(r.hemis_id || "")}</small>`], ["Summa", r => `<span class="ml-sum">${mlS(r.amount)}</span>`, "num"],
      ["Holat", r => mlChip(r.status, mlStCls(r.status)) + (r.storno_reason ? `<small>${esc(r.storno_reason)}</small>` : "")],
      ["", r => r.status === "faol" && (can.enter && !r.day_closed || can.approve) ? `<button type="button" class="btn sm ghost" data-storno="${r.id}">Storno</button>` : ""]],
      d.items, {rowCls: r => r.status === "storno" ? "ml-bad" : "", empty: "To'lov topilmadi"})}
    ${d.pages > 1 ? `<div class="ml-pager"><button type="button" class="btn sm ghost" id="mlPrev" ${P.page <= 1 ? "disabled" : ""}>‹</button>${P.page} / ${d.pages}<button type="button" class="btn sm ghost" id="mlNext" ${P.page >= d.pages ? "disabled" : ""}>›</button></div>` : ""}</div>`;
  let t; $("#mlQ").oninput = e => { clearTimeout(t); t = setTimeout(() => { P.q = e.target.value; P.page = 1; mlTab(); }, 350); };
  $("#mlDay").onchange = e => { P.day = e.target.value; P.page = 1; mlTab(); };
  $("#mlMeth").onchange = e => { P.method = e.target.value; P.page = 1; mlTab(); };
  $("#mlSt").onchange = e => { P.status = e.target.value; P.page = 1; mlTab(); };
  $("#mlPrev") && ($("#mlPrev").onclick = () => { P.page--; mlTab(); }); $("#mlNext") && ($("#mlNext").onclick = () => { P.page++; mlTab(); });
  $("#mlNew") && ($("#mlNew").onclick = () => mlPayForm());
  box.querySelectorAll("[data-storno]").forEach(b => b.onclick = () => {
    const r = d.items.find(x => x.id === +b.dataset.storno);
    mlModal(`Storno: ${r.receipt_no}`, `<p class="ml-note">${esc(r.full_name)} · ${mlS(r.amount)} · ${mlD(r.paid_on)}. Summa talabaning «to'langan» summasidan ayiriladi.</p>
      <label>Sabab (majburiy)<textarea id="mlWhy" maxlength="300" placeholder="Masalan: noto'g'ri talabaga kiritilgan; bank qaytargan"></textarea></label>`, async m => {
      const reason = m.querySelector("#mlWhy").value.trim(); if (reason.length < 5) { toast("Sababni yozing (kamida 5 belgi)"); return false; }
      const res = await mlApi(`/api/moliya/payments/${r.id}/storno`, {reason}); if (!res) return false;
      toast("Storno qilindi"); mlTab(); return true; }, "Storno qilish");
  });
}
function mlPayForm() {
  let pick = null;
  const m = mlModal("To'lov kiritish", `
    <label>Talaba (F.I.Sh. yoki HEMIS ID)<input id="mlSq" autocomplete="off" placeholder="Kamida 2 belgi"></label><div class="ml-pick" id="mlSl"></div><div id="mlSi"></div>
    <label>To'lov turi<select id="mlKind"><option value="kontrakt|">Kontrakt</option></select></label>
    <div class="row2"><label>Kvitansiya / to'lov hujjati raqami<input id="mlRec" maxlength="40" placeholder="TP-261110-0001"></label>
      <label>To'lov sanasi<input type="date" id="mlDt" value="${ML.meta.today}" max="${ML.meta.today}"></label></div>
    <div class="row2"><label>Summa (so'm)<input id="mlAmt" inputmode="numeric" placeholder="2 500 000"></label>
      <label>Usul<select id="mlMt">${Object.entries(ML.meta.methods).map(([k, v]) => `<option value="${k}">${esc(v)}</option>`).join("")}</select></label></div>
    <label>To'lovchi<input id="mlPayer" maxlength="120" placeholder="Talabaning o'zi / ota-onasi / tashkilot"></label>
    <label>Izoh<input id="mlNote" maxlength="300"></label>`, async m => {
      if (!pick) { toast("Talabani tanlang"); return false; }
      const body = {student_id: pick.id, receipt_no: m.querySelector("#mlRec").value.trim(), paid_on: m.querySelector("#mlDt").value, amount: mlMoney(m.querySelector("#mlAmt").value),
        method: m.querySelector("#mlMt").value, payer: m.querySelector("#mlPayer").value.trim(), note: m.querySelector("#mlNote").value.trim()};
      const [pk, pref] = m.querySelector("#mlKind").value.split("|"); body.kind = pk; body.ref_id = pref ? +pref : null;
      if (body.receipt_no.length < 3) { toast("Kvitansiya raqamini kiriting"); return false; }
      if (!body.amount) { toast("Summani kiriting"); return false; }
      const r = await mlApi("/api/moliya/payments", body); if (!r) return false;
      toast(`To'lov kiritildi: ${r.receipt_no}${r.label ? ` (${r.label})` : ""} · qoldiq ${mlS(r.left)}`); ML.pay.page = 1; mlTab(); return true; }, "Kiritish");
  const inp = m.querySelector("#mlSq"), list = m.querySelector("#mlSl"); let t;
  inp.addEventListener("input", () => { clearTimeout(t); t = setTimeout(async () => {
    const q = inp.value.trim(); if (q.length < 2) { list.innerHTML = ""; return; }
    const rs = (await mlApi("/api/moliya/students?q=" + encodeURIComponent(q)).catch(() => ({items: []}))).items;
    list.innerHTML = rs.map((s, i) => `<button type="button" data-i="${i}">${esc(s.full_name)} <small class="muted">${esc(s.grp || "")} · ${esc(s.hemis_id || "")} · ${s.payment_type === "kontrakt" ? "qarz " + mlS(s.debt) : esc(s.payment_type)}</small></button>`).join("") || `<small class="muted">Topilmadi</small>`;
    list.querySelectorAll("button[data-i]").forEach(b => b.onclick = async () => {
      list.querySelectorAll("button").forEach(x => x.classList.remove("on")); b.classList.add("on"); pick = rs[+b.dataset.i];
      const s = await mlApi(`/api/moliya/student/${pick.id}`); m.querySelector("#mlSi").innerHTML = mlStuBox(s, true);
      const amt = m.querySelector("#mlAmt"); if (!amt.value && s.contract?.overdue) amt.value = fmt(s.contract.overdue.short);
      const ob = (await mlApi(`/api/moliya/obligations/${pick.id}`).catch(() => ({items: []}))).items;   /* qayta o'qish / turar joy hisoblari */
      m.querySelector("#mlKind").innerHTML = (s.contract ? `<option value="kontrakt|">Kontrakt — qarz ${mlS(s.contract.debt)}</option>` : "") +
        ob.map(o => `<option value="${o.kind}|${o.ref_id}">${esc(o.label)} — qoldiq ${mlS(o.left)}</option>`).join("") || `<option value="kontrakt|">Ochiq hisob yo'q</option>`;
    });
  }, 250); });
}
function mlStuBox(s, compact = false) {
  const k = s.contract, st = s.student;
  if (!k) return `<div class="ml-stu"><b>${esc(st.full_name)}</b> — ${esc(st.payment_type || "")} asosida o'qiydi, kontrakt yo'q.</div>`;
  return `<div class="ml-stu"><b>${esc(st.full_name)}</b> <small class="muted">${esc(st.grp || "")} · ${esc(st.hemis_id || "")} · ${esc(st.status || "")}</small>
    <div>Shartnoma ${esc(s.contract_no || "")} · ${mlS(k.amount)} · to'langan ${mlS(k.paid)} (${k.pct ?? 0}%) · <b>qarz ${mlS(k.debt)}</b></div>
    ${k.overdue ? `<div>${mlChip(`${k.overdue.label} muddati o'tgan (${mlD(k.overdue.due)}): ${mlS(k.overdue.short)} yetishmaydi`, "bad")}</div>` : k.next ? `<div>${mlChip(`Keyingi: ${k.next.label} — ${mlD(k.next.due)} gacha ${mlS(k.next.need)}`, "info")}</div>` : `<div>${mlChip("Jadval bo'yicha qarz yo'q", "ok")}</div>`}
    ${compact ? "" : `<div class="ml-plan">${k.plan.map(p => mlChip(`${p.label} · ${mlD(p.due)} · ${p.pct}%`, p.met ? "ok" : p.due < ML.meta.today ? "bad" : "")).join("")}</div>`}</div>`;
}

/* ---------- Talaba (Registrator ofisi — o'qish) ---------- */
async function mlStudentTab(box) {
  box.innerHTML = `<div class="card ml-card"><h3>Talabaning to'lov holati</h3><p class="muted">Qidiring: F.I.Sh. yoki HEMIS ID</p>
    <div class="ml-bar"><input type="search" id="mlSq2" placeholder="Kamida 2 belgi" autocomplete="off"></div><div class="ml-pick" id="mlSl2"></div><div id="mlSi2"></div></div>`;
  const inp = $("#mlSq2"), list = $("#mlSl2"); let t;
  inp.addEventListener("input", () => { clearTimeout(t); t = setTimeout(async () => {
    const q = inp.value.trim(); if (q.length < 2) { list.innerHTML = ""; return; }
    const rs = (await mlApi("/api/moliya/students?q=" + encodeURIComponent(q)).catch(() => ({items: []}))).items;
    list.innerHTML = rs.map((s, i) => `<button type="button" data-i="${i}">${esc(s.full_name)} <small class="muted">${esc(s.grp || "")} · ${esc(s.hemis_id || "")}</small></button>`).join("") || `<small class="muted">Topilmadi</small>`;
    list.querySelectorAll("button[data-i]").forEach(b => b.onclick = async () => {
      const s = await mlApi(`/api/moliya/student/${rs[+b.dataset.i].id}`);
      $("#mlSi2").innerHTML = mlStuBox(s) + `<h3 style="margin-top:12px">To'lovlar tarixi</h3>` + mlTable([["Sana", p => mlD(p.paid_on)], ["Kvitansiya", p => `${esc(p.receipt_no)}<small>${esc(p.method_label)}</small>`],
        ["Summa", p => mlS(p.amount), "num"], ["Holat", p => mlChip(p.status, mlStCls(p.status)) + (p.storno_reason ? `<small>${esc(p.storno_reason)}</small>` : "")]], s.payments, {empty: "ISFT Core'da kiritilgan to'lov yo'q"}) + `<p class="ml-note">${esc(s.note)}</p>`;
    });
  }, 250); });
}

/* ---------- Kunlik solishtirish ---------- */
async function mlRecon(box) {
  const d = await mlApi("/api/moliya/recon?month=" + ML.month), can = ML.meta.can;
  box.innerHTML = `<div class="card ml-card"><div class="ml-bar"><h3 class="grow" style="margin:0">Kunlik solishtirish</h3><input type="month" class="ml-in" id="mlMon" value="${ML.month}"></div>
    <p class="muted">Har kuni tizimdagi to'lovlar bank/kassa ko'chirmasi bilan solishtiriladi. Yopilgan kunga to'lov kiritilmaydi; farq bo'lsa izoh majburiy.</p>
    ${mlTable([["Kun", x => `<b>${mlD(x.day)}</b>${x.stale ? `<small>solishtirilmagan</small>` : ""}`], ["To'lovlar", x => `${fmt(x.n)} ta`], ["Tizim", x => mlS(x.system), "num"],
      ["Ko'chirma", x => x.bank == null ? "—" : mlS(x.bank), "num"], ["Farq", x => x.diff ? `<b style="color:var(--bad)">${mlS(x.diff)}</b>` : x.bank == null ? "—" : "0", "num"],
      ["Holat", x => mlChip(x.status, mlStCls(x.status)) + (x.note ? `<small>${esc(x.note)}</small>` : "") + (x.reopen_reason ? `<small>Qayta ochildi: ${esc(x.reopen_reason)}</small>` : "")],
      ["", x => (["ochiq", "qayta ochildi"].includes(x.status) && can.enter ? `<button type="button" class="btn sm primary" data-close="${x.day}">Solishtirish va yopish</button>` : "")
              + (["yopildi", "farq bilan yopildi"].includes(x.status) && can.approve ? `<button type="button" class="btn sm ghost" data-reopen="${x.day}">Qayta ochish</button>` : "")]],
      d.days, {rowCls: x => x.stale ? "ml-bad" : "", empty: "Bu oyda to'lov yo'q"})}</div>`;
  $("#mlMon").onchange = e => { ML.month = e.target.value || ML.month; mlTab(); };
  box.querySelectorAll("[data-close]").forEach(b => b.onclick = () => {
    const x = d.days.find(y => y.day === b.dataset.close);
    const m = mlModal(`Solishtirish: ${mlD(x.day)}`, `<p class="ml-note">Bank/kassa ko'chirmasidagi summalarni usullar bo'yicha kiriting. Tizimdagi summa avtomatik qo'yilgan — farq bo'lsa o'zgartiring.</p>
      ${Object.entries(x.methods).map(([k, v]) => `<div class="row2"><label>${esc(v.label)} — tizimda (${v.n} ta)<input disabled value="${fmt(v.system)}"></label>
        <label>Ko'chirmada<input data-bank="${k}" inputmode="numeric" value="${fmt(v.system)}"></label></div>`).join("")}
      <p class="ml-note" id="mlDiff">Farq: 0 so'm</p><label>Izoh (farq bo'lsa majburiy)<textarea id="mlRn" maxlength="400"></textarea></label>`, async m => {
        const bank = Object.fromEntries([...m.querySelectorAll("[data-bank]")].map(i => [i.dataset.bank, mlMoney(i.value)]));
        const r = await mlApi(`/api/moliya/recon/${x.day}/close`, {bank, note: m.querySelector("#mlRn").value.trim()}); if (!r) return false;
        toast(r.diff ? `Kun farq bilan yopildi: ${mlS(r.diff)}` : "Kun yopildi — farq yo'q"); mlTab(); return true; }, "Kunni yopish");
    const upd = () => { const s = [...m.querySelectorAll("[data-bank]")].reduce((a, i) => a + mlMoney(i.value), 0) - x.system; m.querySelector("#mlDiff").textContent = `Farq: ${fmt(s)} so'm`; };
    m.querySelectorAll("[data-bank]").forEach(i => i.oninput = upd);
  });
  box.querySelectorAll("[data-reopen]").forEach(b => b.onclick = () => mlModal(`Qayta ochish: ${mlD(b.dataset.reopen)}`,
    `<p class="ml-note">Qayta ochilgan kunga buxgalteriya to'lov kiritishi/storno qilishi mumkin; keyin yana solishtirib yopiladi.</p><label>Sabab<textarea id="mlRr" maxlength="300"></textarea></label>`, async m => {
      const reason = m.querySelector("#mlRr").value.trim(); if (reason.length < 5) { toast("Sababni yozing"); return false; }
      const r = await mlApi(`/api/moliya/recon/${b.dataset.reopen}/reopen`, {reason}); if (!r) return false; toast("Kun qayta ochildi"); mlTab(); return true; }, "Qayta ochish"));
}

/* ---------- Byudjet ---------- */
async function mlBudget(box) {
  const d = await mlApi("/api/moliya/budget?year=" + ML.year), can = ML.meta.can;
  const cell = (m, c) => d.cells.find(x => x.month === m && x.category === c);
  box.innerHTML = `<div class="ml-kpis">${mlKpi("Yillik reja", mln(d.total.plan))}${mlKpi("Fakt", mln(d.total.fact), `${d.total.plan ? (100 * d.total.fact / d.total.plan).toFixed(1) : "—"}%`)}
      ${mlKpi("Tasdiq kutmoqda", mln(d.total.pending), "", d.total.pending ? "warn" : "")}${mlKpi("Oylik oshib ketish", fmt(d.monthly_over.length), "oy × modda", d.monthly_over.length ? "warn" : "ok")}</div>
    <div class="card ml-card"><div class="ml-bar"><h3 class="grow" style="margin:0">Byudjet moddalari — ${d.year}</h3>
      ${d.years.length > 1 ? `<select class="ml-in" id="mlYr">${d.years.map(y => `<option ${y === d.year ? "selected" : ""}>${y}</option>`).join("")}</select>` : ""}</div>
      <p class="muted">Fakt — tasdiqlangan xarajatlar (panel va hisobotlar shu jadvalni o'qiydi). Ijro ≥ ${ML.meta.warn_pct}% — chegaraga yaqin.</p>
      ${mlTable([["Modda", l => `<b>${esc(l.category)}</b>`], ["Reja", l => mlS(l.plan), "num"], ["Fakt", l => mlS(l.fact), "num"], ["Tasdiq kutmoqda", l => l.pending ? mlS(l.pending) : "—", "num"],
        ["Qoldiq", l => mlS(l.left), "num"], ["Ijro", l => `${mlProg(l.pct)}<small>${l.pct ?? "—"}%${l.pending ? ` · prognoz ${l.forecast_pct}%` : ""}</small>`],
        ["Holat", l => mlChip(l.status, mlStCls(l.status))], ["", l => can.approve ? `<button type="button" class="btn sm ghost" data-plan="${esc(l.category)}">Rejani o'zgartirish</button>` : ""]],
        d.lines, {rowCls: l => l.status === "oshib ketgan" ? "ml-bad" : ""})}</div>
    <div class="card ml-card"><h3>Oylar kesimida</h3><p class="muted">Fakt / oylik reja; qizil — oylik rejadan oshgan</p>
      <div class="tw"><table class="ml-t"><thead><tr><th>Modda</th>${d.months.map(m => `<th>${monOf(m)}</th>`).join("")}</tr></thead><tbody>
      ${d.lines.map(l => `<tr><td>${esc(l.category)}</td>${d.months.map(m => { const c = cell(m, l.category); return `<td class="num" ${c && c.planned && c.actual > c.planned ? 'style="color:var(--bad);font-weight:700"' : ""} title="${c ? `reja ${mlS(c.planned)}` : ""}">${c ? mln(c.actual) : "—"}</td>`; }).join("")}</tr>`).join("")}
      </tbody></table></div></div>`;
  $("#mlYr") && ($("#mlYr").onchange = e => { ML.year = +e.target.value; mlTab(); });
  box.querySelectorAll("[data-plan]").forEach(b => b.onclick = () => {
    const l = d.lines.find(x => x.category === b.dataset.plan);
    mlModal(`Yillik reja: ${l.category}`, `<p class="ml-note">Hozirgi reja ${mlS(l.plan)} · fakt ${mlS(l.fact)}</p><label>Yangi yillik reja (so'm)<input id="mlPl" inputmode="numeric" value="${fmt(l.plan)}"></label>`, async m => {
      const r = await mlApi("/api/moliya/budget/plan", {year: d.year, category: l.category, plan: mlMoney(m.querySelector("#mlPl").value)}); if (!r) return false;
      toast("Reja saqlandi"); mlTab(); return true; });
  });
}

/* ---------- Xarajatlar ---------- */
async function mlExpenses(box) {
  const d = await mlApi("/api/moliya/expenses?" + mlQs({status: ML.exp, year: ML.year})), can = ML.meta.can;
  box.innerHTML = `<div class="card ml-card"><div class="ml-bar"><h3 class="grow" style="margin:0">Xarajatlar</h3>
      <select class="ml-in" id="mlEs"><option value="">Barchasi</option>${d.statuses.map(s => `<option ${ML.exp === s ? "selected" : ""}>${s}</option>`).join("")}</select>
      ${can.enter ? `<button type="button" class="btn primary" id="mlEn">${ico("plus", 15)} Xarajat kiritish</button>` : ""}</div>
    <p class="muted">${fmt(d.limit)} so'mdan kichik va moddadan oshmaydigan xarajat darhol o'tkaziladi; aks holda moliya prorektori tasdig'iga tushadi.</p>
    ${mlTable([["№ / sana", e => `<b>${e.number}</b><small>${mlD(e.spent_on)}</small>`], ["Modda", e => esc(e.category)], ["Oluvchi va maqsad", e => `${esc(e.payee)}<small>${esc(e.purpose)}${e.doc_no ? ` · ${esc(e.doc_no)}` : ""}</small>`],
      ["Summa", e => mlS(e.amount), "num"], ["Holat", e => mlChip(e.status, mlStCls(e.status)) + (e.reason_route && e.status === "kutilmoqda" ? `<small>${esc(e.reason_route)}</small>` : "")
        + (e.decide_note ? `<small>${esc(e.decide_note)}</small>` : "") + (e.decided_by ? `<small>${esc(e.decided_by)}</small>` : "")],
      ["", e => e.status !== "kutilmoqda" ? "" : can.approve ? `<button type="button" class="btn sm primary" data-ok="${e.id}">Tasdiqlash</button> <button type="button" class="btn sm ghost" data-no="${e.id}">Rad etish</button>`
        : can.enter ? `<button type="button" class="btn sm ghost" data-cancel="${e.id}">Bekor qilish</button>` : ""]], d.items, {empty: "Xarajat yo'q"})}</div>`;
  $("#mlEs").onchange = e => { ML.exp = e.target.value; mlTab(); };
  $("#mlEn") && ($("#mlEn").onclick = () => mlModal("Xarajat kiritish", `
    <div class="row2"><label>Byudjet moddasi<select id="mlEc">${ML.meta.categories.map(c => `<option>${esc(c)}</option>`).join("")}</select></label>
      <label>Sana<input type="date" id="mlEd" value="${ML.meta.today}" max="${ML.meta.today}"></label></div>
    <div class="row2"><label>Summa (so'm)<input id="mlEa" inputmode="numeric"></label><label>Hujjat (shartnoma/hisob-faktura) №<input id="mlEdn" maxlength="60"></label></div>
    <label>Oluvchi<input id="mlEp" maxlength="160"></label><label>Maqsad<textarea id="mlEpu" maxlength="400"></textarea></label>`, async m => {
      const r = await mlApi("/api/moliya/expenses", {category: m.querySelector("#mlEc").value, spent_on: m.querySelector("#mlEd").value, amount: mlMoney(m.querySelector("#mlEa").value),
        doc_no: m.querySelector("#mlEdn").value.trim(), payee: m.querySelector("#mlEp").value.trim(), purpose: m.querySelector("#mlEpu").value.trim()}); if (!r) return false;
      toast(r.status === "tasdiqlandi" ? `${r.number} o'tkazildi` : `${r.number} — moliya prorektori tasdig'iga yuborildi`); mlTab(); return true; }, "Kiritish"));
  box.querySelectorAll("[data-ok]").forEach(b => b.onclick = () => { if (!arm(b, "Ha, tasdiqlash")) return;
    busy(b, async () => { const r = await mlApi(`/api/moliya/expenses/${b.dataset.ok}/decide`, {decision: "tasdiqlandi"}); if (r) { toast("Tasdiqlandi — byudjetga o'tkazildi"); mlTab(); } }); });
  box.querySelectorAll("[data-no]").forEach(b => b.onclick = () => mlModal("Rad etish", `<label>Sabab (majburiy)<textarea id="mlNo" maxlength="300"></textarea></label>`, async m => {
    const r = await mlApi(`/api/moliya/expenses/${b.dataset.no}/decide`, {decision: "rad etildi", note: m.querySelector("#mlNo").value.trim()}); if (!r) return false; toast("Rad etildi"); mlTab(); return true; }, "Rad etish"));
  box.querySelectorAll("[data-cancel]").forEach(b => b.onclick = () => { if (!arm(b, "Ha, bekor qilish")) return;
    busy(b, async () => { const r = await mlApi(`/api/moliya/expenses/${b.dataset.cancel}/cancel`, {}); if (r) { toast("Bekor qilindi"); mlTab(); } }); });
}

/* ---------- Xaridlar ---------- */
async function mlProc(box) {
  const d = await mlApi("/api/moliya/procurements"), can = ML.meta.can;
  box.innerHTML = `<div class="card ml-card"><h3>Xarid so'rovlari</h3><p class="muted">Xarid bo'limi «${d.fundable_statuses.join("» yoki «")}» holatiga o'tkazgan so'rovlar moliyalashtiriladi — bog'langan xarajat yaratiladi.</p>
    ${mlTable([["№", p => `<b>${p.number}</b><small>${mlD(p.created_at)}</small>`], ["Joy va buyum", p => `${esc(p.item)} × ${p.qty}<small>${esc(p.room || "")}</small>`],
      ["Taxminiy narx", p => p.est_cost ? mlS(p.est_cost) : "—", "num"], ["Xarid holati", p => mlChip(p.status)],
      ["Moliya", p => mlChip(p.fin, mlStCls(p.fin)) + (p.fin_amount ? `<small>${mlS(p.fin_amount)} · ${esc(p.fin_category || "")}</small>` : "")],
      ["", p => p.fundable && can.enter ? `<button type="button" class="btn sm primary" data-fund="${p.id}">Moliyalashtirish</button>` : ""]], d.items, {empty: "Xarid so'rovi yo'q"})}</div>`;
  box.querySelectorAll("[data-fund]").forEach(b => b.onclick = () => {
    const p = d.items.find(x => x.id === +b.dataset.fund);
    const guess = /proyektor|kompyuter|printer|monitor|router/i.test(p.item) ? "IT va uskunalar" : "Xo'jalik va ta'mir";
    mlModal(`Moliyalashtirish: ${p.number}`, `<p class="ml-note">${esc(p.item)} × ${p.qty} · ${esc(p.room || "")}</p>
      <div class="row2"><label>Byudjet moddasi<select id="mlFc">${ML.meta.categories.map(c => `<option ${c === guess ? "selected" : ""}>${esc(c)}</option>`).join("")}</select></label>
        <label>Summa (so'm)<input id="mlFa" inputmode="numeric" value="${p.est_cost ? fmt(p.est_cost) : ""}"></label></div>
      <div class="row2"><label>Yetkazib beruvchi<input id="mlFp" maxlength="160"></label><label>Hisob-faktura №<input id="mlFd" maxlength="60"></label></div>`, async m => {
        const r = await mlApi(`/api/moliya/procurements/${p.id}/fund`, {category: m.querySelector("#mlFc").value, amount: mlMoney(m.querySelector("#mlFa").value) || null,
          payee: m.querySelector("#mlFp").value.trim(), doc_no: m.querySelector("#mlFd").value.trim()}); if (!r) return false;
        toast(r.status === "tasdiqlandi" ? `${r.number}: to'landi` : `${r.number}: moliya prorektori tasdig'iga yuborildi`); mlTab(); return true; }, "Moliyalashtirish");
  });
}

/* ---------- Hisobotlar ---------- */
async function mlReports(box) {
  const R = [["payments", "To'lovlar reyestri", "Oy davomida kiritilgan barcha to'lovlar (storno bilan), jami"], ["recon", "Kunlik solishtirish", "Kunlar bo'yicha tizim ↔ ko'chirma, farqlar va izohlar"],
    ["budget", "Byudjet ijrosi", "Moddalar: yillik reja, fakt, oy fakti, tasdiq kutmoqda, qoldiq"]];
  box.innerHTML = `<div class="card ml-card"><div class="ml-bar"><h3 class="grow" style="margin:0">Oylik hisobotlar</h3><input type="month" class="ml-in" id="mlRm" value="${ML.month}"></div>
    <p class="muted">Imzo qatorlari bilan: bosh buxgalter va moliya-iqtisod prorektori.</p>
    <div class="ml-list">${R.map(([k, t, s]) => `<div class="ml-item"><div class="ml-item-h"><div><b>${esc(t)}</b><p>${esc(s)}</p></div>
      <div class="ml-acts" style="margin:0"><a class="btn sm primary" href="/api/moliya/export?kind=${k}&month=${ML.month}&fmt=xlsx">${ico("file", 15)} .xlsx</a>
      <a class="btn sm ghost" href="/api/moliya/export?kind=${k}&month=${ML.month}&fmt=csv">.csv</a></div></div></div>`).join("")}</div></div>`;
  $("#mlRm").onchange = e => { ML.month = e.target.value || ML.month; mlTab(); };
}


/* ---------- Aniqlanmagan to'lovlar (bank ko'chirmasi → talaba; app/moliya_match.py) ---------- */
const ML_BANK_ST = {aniqlanmagan: "Aniqlanmagan", avto: "Avtomatik", "qo'lda": "Qo'lda biriktirilgan", "shartnoma emas": "Shartnoma emas", qaytarish: "Qaytariladi", "": "Barchasi"};
const mlScoreCls = s => s >= 80 ? "ok" : s >= 50 ? "info" : "warn";
async function mlBank(box) {
  const B = ML.bank, d = await mlApi("/api/moliya/bank?" + mlQs({status: B.status, q: B.q})), st = d.stats, can = ML.meta.can;
  ML.meta.bank = st;
  box.innerHTML = `<div class="ml-kpis">${mlKpi("Aniqlanmagan", fmt(st.n), mlS(st.sum), st.n ? "warn" : "ok")}
      ${mlKpi(`${d.alert_days} kundan eski`, fmt(st.stale), st.stale ? mlS(st.stale_sum) : "yo'q", st.stale ? "bad" : "ok")}
      ${mlKpi("Avtomatik biriktirilgan", fmt(st.by_status.avto || 0), "shartnoma raqami / HEMIS ID / F.I.Sh.+guruh aniq")}
      ${mlKpi("Qo'lda biriktirilgan", fmt(st.by_status["qo'lda"] || 0), "buxgalter tasdig'i bilan")}</div>
    ${can.enter ? `<details class="card ml-card" ${st.n ? "" : "open"}><summary><b>Bank ko'chirmasini yuklash</b> <span class="muted">— CSV fayl yoki matn: sana; summa; to'lovchi; maqsad; hujjat №</span></summary>
      <p class="muted">Bank tizimidan olingan ko'chirma fayli (1C/bank API ulanmagan). Bir xil qator ikkinchi marta qo'shilmaydi. Shartnoma raqami, HEMIS ID yoki aniq F.I.Sh.+guruh bo'lsa — darhol biriktiriladi.</p>
      <div class="ml-bar"><input type="file" id="mlBf" accept=".csv,.txt,text/csv" class="ml-in"></div>
      <textarea id="mlBt" class="ml-in" style="width:100%;height:110px;padding:8px 10px" placeholder="sana;summa;to'lovchi;maqsad;hujjat
${ML.meta.today};2500000;Karimov Odil;O'g'lim Nodirbek uchun kontrakt;PP-1201"></textarea>
      <div class="ml-acts"><button type="button" class="btn primary" id="mlBi">Yuklash va moslashtirish</button><button type="button" class="btn ghost" id="mlB1">Bitta qator qo'lda</button></div></details>` : ""}
    <div class="card ml-card"><div class="ml-bar"><select class="ml-in" id="mlBs">${Object.entries(ML_BANK_ST).map(([k, v]) => `<option value="${esc(k)}" ${B.status === k ? "selected" : ""}>${esc(v)}</option>`).join("")}</select>
      <input type="search" id="mlBq" placeholder="To'lovchi, maqsad yoki hujjat №" value="${esc(B.q)}"></div>
      <div class="ml-list">${d.items.map(mlBankItem).join("") || `<div class="ml-empty">${B.status === "aniqlanmagan" ? "Aniqlanmagan to'lov yo'q — hammasi biriktirilgan" : "Qator yo'q"}</div>`}</div></div>`;
  $("#mlBs").onchange = e => { B.status = e.target.value; mlTab(); };
  let t; $("#mlBq").oninput = e => { clearTimeout(t); t = setTimeout(() => { B.q = e.target.value; mlTab(); }, 350); };
  if ($("#mlBf")) $("#mlBf").onchange = async e => { const f = e.target.files[0]; if (f) $("#mlBt").value = await f.text(); };
  $("#mlBi") && ($("#mlBi").onclick = () => busy($("#mlBi"), async () => {
    const r = await mlApi("/api/moliya/bank/import", {csv: $("#mlBt").value}); if (!r) return;
    toast(`Qo'shildi: ${r.added} · avtomatik: ${r.auto} · aniqlanmagan: ${r.unmatched}${r.duplicates ? ` · takroriy: ${r.duplicates}` : ""}${r.errors.length ? ` · xato: ${r.errors.length}` : ""}`);
    if (r.errors.length) mlModal("Yuklashda xatolar", `<div class="ml-list">${r.errors.map(x => `<div class="ml-alert warn">${esc(x)}</div>`).join("")}</div>`, null);
    renderMoliya(); }));
  $("#mlB1") && ($("#mlB1").onclick = () => mlModal("Ko'chirma qatori", `<div class="row2"><label>Sana<input type="date" id="b1d" value="${ML.meta.today}" max="${ML.meta.today}"></label>
      <label>Summa (so'm)<input id="b1a" inputmode="numeric"></label></div><label>To'lovchi<input id="b1p" maxlength="200"></label>
      <label>To'lov maqsadi (bankdagi matn aynan)<textarea id="b1u" maxlength="500"></textarea></label><label>Hujjat №<input id="b1n" maxlength="60"></label>`, async m => {
      const r = await mlApi("/api/moliya/bank/import", {lines: [{date: m.querySelector("#b1d").value, amount: m.querySelector("#b1a").value, payer: m.querySelector("#b1p").value,
        purpose: m.querySelector("#b1u").value, doc_no: m.querySelector("#b1n").value}]}); if (!r) return false;
      toast(r.auto ? "Avtomatik biriktirildi" : r.duplicates ? "Bu qator allaqachon bor" : r.errors.length ? r.errors[0] : "Aniqlanmagan navbatiga qo'shildi"); renderMoliya(); return true; }, "Qo'shish"));
  box.querySelectorAll("[data-bok]").forEach(b => b.onclick = () => { if (!arm(b, "Ha, biriktirish")) return;
    busy(b, async () => { const r = await mlApi(`/api/moliya/bank/${b.dataset.line}/confirm`, {student_id: +b.dataset.bok, pay_kind: b.dataset.pk || "kontrakt", ref_id: b.dataset.ref ? +b.dataset.ref : null});
      if (r) { toast(`Biriktirildi${r.label ? ` (${r.label})` : ""} — qoldiq ${mlS(r.left)}`); renderMoliya(); } }); });
  box.querySelectorAll("[data-bother]").forEach(b => b.onclick = () => mlBankOther(+b.dataset.bother));
  box.querySelectorAll("[data-bdis]").forEach(b => b.onclick = () => mlModal(b.dataset.kind === "qaytarish" ? "Qaytarishga belgilash" : "Shartnoma to'lovi emas",
    `<p class="ml-note">${b.dataset.kind === "qaytarish" ? "To'lovchiga qaytariladi (masalan, talaba topilmadi yoki ortiqcha to'lov)." : "Boshqa daromad (ijara, xizmat va h.k.) — talaba kontraktiga o'tkazilmaydi."}</p>
     <label>Sabab<textarea id="mlBd" maxlength="300"></textarea></label>`, async m => {
      const reason = m.querySelector("#mlBd").value.trim(); if (reason.length < 5) { toast("Sababni yozing"); return false; }
      const r = await mlApi(`/api/moliya/bank/${b.dataset.bdis}/dismiss`, {kind: b.dataset.kind, reason}); if (!r) return false; toast("Belgilandi"); renderMoliya(); return true; }, "Saqlash"));
}
function mlBankItem(L) {
  const can = ML.meta.can.enter && L.status === "aniqlanmagan";
  const head = `<div class="ml-item-h"><div><b>${mlS(L.amount)}</b> · ${mlD(L.line_date)}${L.doc_no ? ` · ${esc(L.doc_no)}` : ""}
      <p><span class="muted">To'lovchi:</span> ${esc(L.payer || "—")}<br><span class="muted">Maqsad:</span> ${esc(L.purpose || "—")}</p></div>
    <div>${mlChip(L.status_label, L.status === "aniqlanmagan" ? (L.stale ? "bad" : "warn") : L.status === "avto" || L.status === "qo'lda" ? "ok" : "")}${L.stale ? `<small class="muted">${L.age_days} kun turibdi</small>` : ""}</div></div>`;
  if (L.status !== "aniqlanmagan") {
    return `<div class="ml-item">${head}${L.full_name ? `<p>→ <b>${esc(L.full_name)}</b> <small class="muted">${esc(L.grp || "")} · ${esc(L.hemis_id || "")}</small></p>` : ""}
      ${L.match_reasons.length ? `<div class="ml-plan">${L.match_reasons.map(r => mlChip(r, "info")).join("")}</div>` : ""}
      <p class="ml-note">${esc(L.match_kind === "avto" ? "Avtomatik" : "Qo'lda")}${L.resolved_by ? ` · ${esc(L.resolved_by)}` : ""}${L.resolved_at ? ` · ${mlD(L.resolved_at)} ${String(L.resolved_at).slice(11, 16)}` : ""}${L.resolve_note ? ` · ${esc(L.resolve_note)}` : ""}</p></div>`;
  }
  return `<div class="ml-item">${head}${L.resolve_note ? `<div class="ml-alert warn" style="margin-top:8px">${esc(L.resolve_note)}</div>` : ""}
    <div class="ml-list" style="margin-top:10px">${L.candidates.map((c, i) => `<div class="ml-stu" style="margin:0">
      <div class="ml-item-h"><div>${mlChip(`${c.score}%`, mlScoreCls(c.score))} ${mlChip(c.ref_label || "Kontrakt", c.pay_kind && c.pay_kind !== "kontrakt" ? "warn" : "")} <b>${esc(c.full_name)}</b> <small class="muted">${esc(c.grp)} · HEMIS ${esc(c.hemis_id)}${c.contract_no ? ` · shartnoma ${esc(c.contract_no)}` : ""} · ${c.pay_kind && c.pay_kind !== "kontrakt" ? "qoldiq" : "qarz"} ${mlS(c.debt)}</small></div>
      ${can ? `<button type="button" class="btn sm ${i === 0 ? "primary" : "ghost"}" data-line="${L.id}" data-bok="${c.student_id}" data-pk="${esc(c.pay_kind || "kontrakt")}" data-ref="${c.ref_id ?? ""}">Tasdiqlash</button>` : ""}</div>
      <div class="ml-plan">${c.reasons.map(r => mlChip(r, /mos emas|katta|holati/.test(r) ? "bad" : "")).join("")}</div></div>`).join("") || `<div class="ml-empty">Mos talaba topilmadi — qidiruv orqali tanlang yoki shartnoma to'lovi emas deb belgilang</div>`}</div>
    ${can ? `<div class="ml-acts"><button type="button" class="btn sm ghost" data-bother="${L.id}">Boshqa talabani tanlash</button>
      <button type="button" class="btn sm ghost" data-bdis="${L.id}" data-kind="shartnoma emas">Shartnoma to'lovi emas</button>
      <button type="button" class="btn sm ghost" data-bdis="${L.id}" data-kind="qaytarish">Qaytarish</button></div>` : ""}</div>`;
}
function mlBankOther(lid) {
  let pick = null;
  const m = mlModal("Boshqa talabani tanlash", `<label>Talaba (F.I.Sh. yoki HEMIS ID)<input id="mlOq" autocomplete="off"></label><div class="ml-pick" id="mlOl"></div><div id="mlOi"></div>
    <label>Izoh (nega boshqa talaba)<input id="mlOn" maxlength="300"></label>`, async m => {
      if (!pick) { toast("Talabani tanlang"); return false; }
      const r = await mlApi(`/api/moliya/bank/${lid}/confirm`, {student_id: pick.id, note: m.querySelector("#mlOn").value.trim()}); if (!r) return false;
      toast(`Biriktirildi — qoldiq qarz ${mlS(r.left)}`); renderMoliya(); return true; }, "Biriktirish");
  const inp = m.querySelector("#mlOq"), list = m.querySelector("#mlOl"); let t;
  inp.addEventListener("input", () => { clearTimeout(t); t = setTimeout(async () => {
    const q = inp.value.trim(); if (q.length < 2) { list.innerHTML = ""; return; }
    const rs = (await mlApi("/api/moliya/students?q=" + encodeURIComponent(q)).catch(() => ({items: []}))).items;
    list.innerHTML = rs.map((s, i) => `<button type="button" data-i="${i}" ${s.payment_type !== "kontrakt" ? "disabled" : ""}>${esc(s.full_name)} <small class="muted">${esc(s.grp || "")} · ${esc(s.hemis_id || "")} · qarz ${mlS(s.debt)}</small></button>`).join("") || `<small class="muted">Topilmadi</small>`;
    list.querySelectorAll("button[data-i]").forEach(b => b.onclick = async () => { list.querySelectorAll("button").forEach(x => x.classList.remove("on")); b.classList.add("on"); pick = rs[+b.dataset.i];
      m.querySelector("#mlOi").innerHTML = mlStuBox(await mlApi(`/api/moliya/student/${pick.id}`), true); });
  }, 250); });
}

/* menyu nishoni (app.js badges() chaqiradi): buxgalteriya — aniqlanmagan to'lovlar; moliya prorektori — tasdiq kutayotgan xarajatlar */
async function moliyaBadge(set) {
  if (!["buxgalteriya", "prorektor_moliya"].includes(ME?.role_key)) return;
  try {
    const m = await mlApi("/api/moliya/meta");
    if (ME.role_key === "buxgalteriya") set("moliya", m.bank?.n || 0, `Aniqlanmagan to'lovlar: ${m.bank?.n || 0} ta${m.bank?.stale ? ` (${m.bank.stale} tasi ${m.alert_days} kundan eski)` : ""}`);
    else { const e = await mlApi("/api/moliya/expenses?status=kutilmoqda"); set("moliya", e.items.length, `Tasdig'ingizni kutayotgan xarajatlar: ${e.items.length} ta`); }
  } catch (e) {}
}
