/* =====================================================================
   «Yoshlar ishlari» — turar joy (hamkor yotoqxonalar, ijara) va tadbirlar (app/yoshlar.py, /api/yoshlar).
   Ruxsat va ko'lam serverda tekshiriladi (rejim — lavozimga qarab); bu yerda faqat ko'rinish.
   Global: renderYoshlar() — app.js go() chaqiradi. app.js yordamchilari: $, esc, fmt, toast, arm, locked, showLogin, ME.
   ===================================================================== */
const YJ = {meta: null, tab: null, aq: "", ast: "navbat", rq: "", rst: "faol", rb: 0, room: null, cp: "", cdebt: 0, cq: "", vq: "", xq: "", xstale: 0, est: "", ev: null};
if (!document.querySelector('link[href="yoshlar.css"]')) document.head.insertAdjacentHTML("beforeend", '<link rel="stylesheet" href="yoshlar.css">');
const yjSum = n => n == null ? "—" : fmt(Math.round(n)) + " so'm";
const yjD = s => { s = String(s || "").slice(0, 10); return s.length === 10 ? `${s.slice(8, 10)}.${s.slice(5, 7)}.${s.slice(0, 4)}` : "—"; };
const yjShort = n => { n = String(n || ""); return n.includes(":") ? n.split(":").slice(1).join(":").trim() : n; };
const yjChip = (t, cls = "") => `<span class="yj-chip ${cls}">${esc(t)}</span>`;
async function yjApi(url, body) {
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
const yjQs = o => new URLSearchParams(Object.entries(o).filter(([, v]) => v !== "" && v != null && v !== 0)).toString();
function yjTable(cols, rows, {rowCls = () => "", empty = "Ma'lumot yo'q"} = {}) {
  if (!rows.length) return `<div class="yj-empty">${esc(empty)}</div>`;
  return `<div class="tw"><table class="yj-t"><thead><tr>${cols.map(c => `<th>${esc(c[0])}</th>`).join("")}</tr></thead><tbody>` +
    rows.map(r => `<tr class="${rowCls(r)}">${cols.map(c => `<td data-l="${esc(c[0])}" class="${c[2] || ""}"><div>${c[1](r) ?? ""}</div></td>`).join("")}</tr>`).join("") + `</tbody></table></div>`;
}
const yjKpi = (label, val, sub = "", cls = "") => `<div class="yj-kpi ${cls}"><span>${esc(label)}</span><b>${val}</b>${sub ? `<small>${sub}</small>` : ""}</div>`;
const yjSeg = (opts, cur, attr) => `<div class="yj-seg" role="tablist">${opts.map(([k, t]) => `<button type="button" data-${attr}="${esc(k)}" class="${String(k) === String(cur) ? "on" : ""}" aria-selected="${String(k) === String(cur)}">${esc(t)}</button>`).join("")}</div>`;
function yjModal(title, html, onOk, okText = "Saqlash") {
  const bg = document.createElement("div"); bg.className = "yj-modal-bg";
  bg.innerHTML = `<div class="yj-modal" role="dialog" aria-modal="true" aria-label="${esc(title)}"><h3>${esc(title)}</h3>${html}
    <div class="yj-acts"><button type="button" class="btn ghost" data-x>${onOk ? "Bekor qilish" : "Yopish"}</button>${onOk ? `<button type="button" class="btn primary" data-ok>${esc(okText)}</button>` : ""}</div></div>`;
  document.body.appendChild(bg);
  const close = () => bg.remove();
  bg.addEventListener("click", e => { if (e.target === bg || e.target.closest("[data-x]")) close(); });
  bg.addEventListener("keydown", e => { if (e.key === "Escape") close(); });
  const ok = bg.querySelector("[data-ok]");
  if (ok) ok.onclick = async () => { ok.disabled = true; try { if (await onOk(bg)) close(); } finally { ok.disabled = false; } };
  setTimeout(() => bg.querySelector("input,select,textarea,button")?.focus(), 30);
  return bg;
}
/* talaba qidiruvi (o'z ko'lamida) */
function yjPicker(root, onPick) {
  const inp = root.querySelector("[data-pq]"), list = root.querySelector("[data-pl]"); let t = null;
  inp.addEventListener("input", () => { clearTimeout(t); t = setTimeout(async () => {
    const q = inp.value.trim(); if (q.length < 2) { list.innerHTML = ""; return; }
    const rs = await yjApi("/api/yoshlar/lookup/students?" + yjQs({q})).catch(() => []);
    list.innerHTML = rs.map((r, i) => `<button type="button" data-i="${i}"><b>${esc(r.full_name)}</b> <small class="muted">${esc(r.grp || "")} · ${esc(r.region || "")} · ${esc(r.gender_l)} · ${esc(r.study_form || "")}</small></button>`).join("") || `<small class="muted">Topilmadi</small>`;
    list.querySelectorAll("button").forEach(b => b.onclick = () => { list.querySelectorAll("button").forEach(x => x.classList.remove("on")); b.classList.add("on"); onPick(rs[+b.dataset.i]); });
  }, 250); });
}

async function renderYoshlar() {
  const el = $("#v-yoshlar");
  if (!el.innerHTML) el.innerHTML = `<p class="muted">Yuklanmoqda…</p>`;
  try { YJ.meta = await yjApi("/api/yoshlar/meta"); }
  catch (e) { if (e?.message !== "auth") el.innerHTML = e?.message === "denied" ? locked("Yoshlar ishlari") : `<div class="card yj-card"><p>${esc(e?.msg || "Yuklab bo'lmadi")}</p></div>`; return; }
  if (!YJ.tab || !YJ.meta.tabs.some(t => t.key === YJ.tab)) YJ.tab = YJ.meta.tabs[0].key;
  el.innerHTML = `<div class="yj-head"><div><h2>Yoshlar ishlari</h2><span class="muted">${esc(YJ.meta.mode_note)} · ${esc(YJ.meta.scope)}.
      Institutning o'z yotoqxonasi yo'q: talabalar hamkor yotoqxonalarga shartnoma asosida joylashtiriladi, ijarada yashovchilar tyutorlar nazoratida.</span></div></div>
    <div class="yj-tabs" role="tablist">${YJ.meta.tabs.map(t => `<button type="button" role="tab" data-tab="${t.key}" class="${t.key === YJ.tab ? "on" : ""}" aria-selected="${t.key === YJ.tab}">${esc(t.title)}</button>`).join("")}</div>
    <div id="yjBody"><p class="muted">Yuklanmoqda…</p></div>`;
  el.querySelectorAll("[data-tab]").forEach(b => b.onclick = () => { YJ.tab = b.dataset.tab; YJ.ev = null; renderYoshlar(); });
  await yjTab();
}
async function yjTab() {
  const box = $("#yjBody");
  try { await ({umumiy: yjOverview, arizalar: yjApps, joylar: yjDorms, tolov: yjCharges, tartib: yjViol, ijara: yjRent, tadbirlar: yjEvents})[YJ.tab](box); }
  catch (e) { if (e?.message === "auth") return; box.innerHTML = e?.message === "denied" ? locked("Bu bo'lim") : `<div class="card yj-card"><p>${esc(e?.msg || "Ma'lumotni yuklab bo'lmadi")}</p></div>`; }
}
const yjGo = tab => { YJ.tab = tab; renderYoshlar(); };

/* =================== Umumiy =================== */
async function yjOverview(box) {
  const d = await yjApi("/api/yoshlar/overview"), k = d.kpi;
  box.innerHTML = `${d.alerts.length ? `<div class="yj-alerts">${d.alerts.map(a => `<div class="yj-alert ${a.level}"><span>${esc(a.text)}</span><button class="btn sm ghost" type="button" data-go="${a.tab}">Ochish</button></div>`).join("")}</div>` : ""}
    <div class="yj-kpis">
      ${yjKpi("Yotoqxonada yashaydi", fmt(k.live), `${fmt(k.capacity)} o'rindan · bron ${fmt(k.reserved)}`)}
      ${yjKpi("Bo'sh o'rin", fmt(k.free_m + k.free_f), `yigitlar ${k.free_m} · qizlar ${k.free_f}`, k.free_m + k.free_f ? "ok" : "")}
      ${yjKpi("Navbatda", fmt(k.queue), k.unverified ? `${k.unverified} tasi hujjat tekshiruvida` : "", k.queue ? "warn" : "")}
      ${yjKpi("To'lov qarzi", yjSum(k.debt), `${fmt(k.debtors)} nafar yashovchi`, k.debt ? "bad" : "ok")}
      ${yjKpi("Tartib qaydlari (30 kun)", fmt(k.viol30))}
      ${yjKpi("Ijarada yashaydi", fmt(k.rentals), `${fmt(k.rent_stale)} tasiga 90 kundan beri tashrif yo'q`, k.rent_stale ? "warn" : "")}
      ${YJ.meta.tabs.some(t => t.key === "tadbirlar") ? yjKpi("Tadbirlar", fmt(k.ev_upcoming), `kelgusi · ${k.ev_pending} tasdiqlashda${k.ev_noreport ? ` · ${k.ev_noreport} hisobotsiz` : ""}`) : ""}
    </div>
    <div class="yj-bld">${d.buildings.map(b => `<div class="yj-bcard"><b>${esc(b.name)}</b><small>${esc(b.gender_l)} · ${fmt(b.capacity)} o'rin · band ${fmt(b.live + b.reserved)} · bo'sh ${fmt(b.free)}</small>
      <div class="yj-meter"><i style="width:${Math.min(100, b.pct)}%"></i></div><small>${b.pct}% to'lgan</small></div>`).join("") || `<div class="yj-empty">Yotoqxona qo'shilmagan</div>`}</div>`;
  box.querySelectorAll("[data-go]").forEach(b => b.onclick = () => yjGo(b.dataset.go));
}

/* =================== Arizalar va navbat =================== */
async function yjApps(box) {
  const caps = YJ.meta.caps;
  const rs = await yjApi("/api/yoshlar/applications?" + yjQs({status: YJ.ast, q: YJ.aq}));
  const stChip = r => yjChip(r.status_l, {navbatda: "info", yangi: "warn", joy_berildi: "ok", rad: "bad"}[r.status] || "");
  box.innerHTML = `<div class="card yj-card"><div class="yj-bar">
      ${yjSeg([["navbat", "Navbat"], ["joy_berildi", "Joy berilgan"], ["rad", "Rad etilgan"], ["bekor", "Bekor qilingan"]], YJ.ast, "ast")}
      <input type="search" id="yjAq" placeholder="Ism yoki HEMIS ID" value="${esc(YJ.aq)}">
      ${caps.apply ? `<button class="btn sm" type="button" id="yjAppNew">Ariza kiritish</button>` : ""}
      ${caps.bulk && YJ.ast === "navbat" ? `<button class="btn sm primary" type="button" id="yjBulk">Navbat bo'yicha joylashtirish</button>` : ""}</div>
    <p class="muted">Navbat tartibi: imtiyoz bali (kamayish), keyin ariza vaqti. Ball: ${Object.values(YJ.meta.cats).map(c => `${c.label} +${c.points}`).join("; ")};
      avtomatik: ${Object.values(YJ.meta.auto).map(c => `${c.label} +${c.points}`).join("; ")}. Faqat kunduzgi ta'lim talabalari.</p>
    ${yjTable([
      ["№", r => r.position ? `<b>${r.position}</b>` : "—", "num"],
      ["Talaba", r => `<b>${esc(r.full_name)}</b><small>${esc(r.grp || "")} · ${esc(r.region || "")} · ${esc(r.gender_l)}</small>`],
      ["Imtiyoz", r => [...r.cats_l.map(x => yjChip(x, r.verified ? "ok" : "warn")), ...r.auto_l.map(x => yjChip(x))].join(" ") || "—"],
      ["Ball", r => `<b>${r.score}</b>`, "num"],
      ["Ariza", r => `${yjD(r.submitted_at)}<small>${r.channel === "kabinet" ? "Talaba kabineti" : "Xodim kiritgan"}</small>`],
      ["Holat", r => stChip(r) + (r.building ? `<small>${esc(r.building)}, ${esc(r.room)}-xona</small>` : "") + (r.reason ? `<small>${esc(r.reason)}</small>` : "")],
      ["", r => caps.dorm && ["yangi", "navbatda"].includes(r.status) ? `<div class="yj-acts">
          ${!r.verified ? `<button class="btn sm" data-ver="${r.id}" type="button">Hujjatlar tekshirildi</button>` : `<button class="btn sm primary" data-alloc="${r.id}" type="button">Joy berish</button>`}
          <button class="btn sm ghost" data-rej="${r.id}" type="button">Rad etish</button></div>` : ""]],
      rs, {rowCls: r => r.status === "yangi" && !r.verified ? "warn" : "", empty: "Arizalar yo'q"})}</div>`;
  const q = $("#yjAq"); let t; q.oninput = () => { clearTimeout(t); t = setTimeout(() => { YJ.aq = q.value.trim(); yjApps(box).then(() => { const n = $("#yjAq"); n.focus(); n.setSelectionRange(n.value.length, n.value.length); }); }, 350); };
  box.querySelectorAll("[data-ast]").forEach(b => b.onclick = () => { YJ.ast = b.dataset.ast; yjApps(box); });
  box.querySelectorAll("[data-ver]").forEach(b => b.onclick = async () => { if (!arm(b, "Hujjatlar ko'rildi")) return; if (await yjApi(`/api/yoshlar/applications/${b.dataset.ver}/verify`, {})) { toast("Ariza navbatga qo'shildi"); yjApps(box); } });
  box.querySelectorAll("[data-alloc]").forEach(b => b.onclick = () => yjAllocModal(rs.find(r => r.id === +b.dataset.alloc), box));
  box.querySelectorAll("[data-rej]").forEach(b => b.onclick = () => yjModal("Arizani rad etish", `<label>Sabab (talabaga ko'rinadi)<textarea data-r maxlength="500"></textarea></label>`, async m => {
    const d = await yjApi(`/api/yoshlar/applications/${b.dataset.rej}/reject`, {reason: m.querySelector("[data-r]").value}); if (d) { toast("Ariza rad etildi"); yjApps(box); } return !!d; }, "Rad etish"));
  $("#yjAppNew")?.addEventListener("click", () => yjAppModal(box));
  $("#yjBulk")?.addEventListener("click", async e => { if (!arm(e.currentTarget, "Ha, joylashtirish")) return;
    const d = await yjApi("/api/yoshlar/allocate-waitlist", {}); if (d) { toast(`${d.allocated} ta talabaga joy berildi${d.left ? ` · ${d.left} tasi navbatda qoldi (mos o'rin yo'q yoki hujjat tekshirilmagan)` : ""}`); yjApps(box); } });
}
function yjAppModal(box) {
  let pick = null;
  const m = yjModal("Talaba nomidan ariza", `<label>Talaba<input data-pq placeholder="Ism yoki HEMIS ID (kamida 2 belgi)"></label><div class="yj-pick" data-pl></div>
    <div style="margin:10px 0 4px;font-size:12.5px;font-weight:600;color:var(--muted)">Imtiyozli toifa (hujjati bilan)</div>
    ${Object.entries(YJ.meta.cats).map(([k, c]) => `<label class="ck"><input type="checkbox" value="${k}"> ${esc(c.label)} (+${c.points})</label>`).join("")}
    <label>Izoh<textarea data-n maxlength="500" placeholder="Masalan: hujjatlar nusxasi ilova qilingan"></textarea></label>`, async m => {
      if (!pick) { toast("Talabani tanlang"); return false; }
      const cats = [...m.querySelectorAll("input[type=checkbox]:checked")].map(x => x.value);
      const d = await yjApi("/api/yoshlar/applications", {student_id: pick.id, cats, note: m.querySelector("[data-n]").value});
      if (d) { toast(d.status === "yangi" ? "Ariza qabul qilindi — imtiyoz hujjatlari tekshirilishi kerak" : "Ariza navbatga qo'shildi"); yjApps(box); }
      return !!d; }, "Kiritish");
  yjPicker(m, s => pick = s);
}
async function yjAllocModal(a, box) {
  const bs = await yjApi("/api/yoshlar/buildings");
  const rooms = bs.flatMap(b => b.rooms.filter(r => r.gender === a.gender && r.free > 0).map(r => ({...r, bname: b.name})));
  let room = null;
  const m = yjModal(`Joy berish: ${a.full_name}`, `<p class="muted" style="margin:0 0 10px">${esc(a.gender_l)} uchun bo'sh o'rinli xonalar: ${rooms.length}. Xona tanlanmasa — birinchi bo'sh o'rin beriladi.
      Joy «bron» holatida beriladi; talaba kelgach «Joylashdi» bosiladi (${YJ.meta.rules.reserve_days} kun ichida).</p>
    ${rooms.length ? `<div class="yj-rooms">${rooms.map(r => `<button type="button" class="yj-room free" data-room="${r.id}" title="${esc(r.bname)}"><b>${esc(r.number)}</b>${r.free}/${r.beds} bo'sh</button>`).join("")}</div>` : `<div class="yj-empty">Mos bo'sh o'rin yo'q — ariza navbatda qoladi</div>`}`,
    rooms.length ? async () => { const d = await yjApi(`/api/yoshlar/applications/${a.id}/allocate`, {room_id: room}); if (d) { toast(`${d.building}, ${d.room}-xona, ${d.bed}-o'rin — bron qilindi`); yjApps(box); } return !!d; } : null, "Joy berish");
  m.querySelectorAll("[data-room]").forEach(b => b.onclick = () => { m.querySelectorAll("[data-room]").forEach(x => x.classList.remove("on")); b.classList.add("on"); room = +b.dataset.room; });
}

/* =================== Yotoqxonalar =================== */
async function yjDorms(box) {
  const caps = YJ.meta.caps;
  const [bs, rs] = await Promise.all([yjApi("/api/yoshlar/buildings"), yjApi("/api/yoshlar/residents?" + yjQs({status: YJ.rst, q: YJ.rq, building: YJ.rb}))]);
  box.innerHTML = `<div class="yj-bld">${bs.map(b => `<div class="yj-bcard"><div class="yj-item-h"><b>${esc(b.name)}</b>${b.contract_days != null && b.contract_days < 60 ? yjChip(b.contract_days < 0 ? "Shartnoma muddati o'tgan" : `Shartnoma ${b.contract_days} kunda tugaydi`, b.contract_days < 0 ? "bad" : "warn") : ""}</div>
      <small>${esc(b.address || "")}<br>Hamkor: ${esc(b.partner || "—")} · shartnoma ${esc(b.contract_no || "—")} (${yjD(b.contract_until)} gacha)<br>${esc(b.gender_l)} · oyiga ${yjSum(b.fee_month)}</small>
      <div class="yj-meter"><i style="width:${Math.min(100, b.pct)}%"></i></div>
      <small>${fmt(b.capacity)} o'rin · yashaydi ${fmt(b.live)} · bron ${fmt(b.reserved)} · bo'sh ${fmt(b.free)}</small>
      <div class="yj-rooms">${b.rooms.map(r => `<button type="button" class="yj-room ${r.free ? "free" : "full"} ${YJ.room === r.id ? "on" : ""}" data-room="${r.id}" data-b="${b.id}" title="${r.floor}-qavat"><b>${esc(r.number)}</b>${r.beds - r.free}/${r.beds}</button>`).join("")}</div>
      ${caps.dorm ? `<div class="yj-acts"><button class="btn sm ghost" data-addroom="${b.id}" type="button">Xona qo'shish</button></div>` : ""}</div>`).join("")}
      ${caps.dorm ? `<button type="button" class="yj-bcard" id="yjAddB" style="cursor:pointer;align-items:center;justify-content:center;font:inherit;color:var(--muted)"><b>+ Hamkor yotoqxona qo'shish</b><small>Shartnoma asosida ajratilgan joylar</small></button>` : ""}</div>
    <div class="card yj-card"><div class="yj-bar">${yjSeg([["faol", "Yashovchilar va bron"], ["band", "Faqat bron"], ["chiqdi", "Chiqib ketganlar"]], YJ.rst, "rst")}
      <select id="yjRb"><option value="0">Barcha binolar</option>${bs.map(b => `<option value="${b.id}" ${YJ.rb === b.id ? "selected" : ""}>${esc(b.name)}</option>`).join("")}</select>
      <input type="search" id="yjRq" placeholder="Ism, HEMIS ID yoki xona raqami" value="${esc(YJ.rq)}">
      ${YJ.room ? `<button class="btn sm ghost" id="yjRoomX" type="button">Xona filtri: bekor</button>` : ""}</div>
    ${yjTable([
      ["Talaba", r => `<b>${esc(r.full_name)}</b><small>${esc(r.grp || "")} · ${esc(r.course || "")}-kurs</small>` + (r.mismatch ? yjChip("Faol talaba emas", "bad") : "")],
      ["Joy", r => `${esc(r.building)}<small>${esc(r.room)}-xona, ${r.bed_no}-o'rin</small>`],
      ["Holat", r => yjChip(r.status_l, r.status === "yashaydi" ? "ok" : r.status === "band" ? (r.overdue_reserve ? "bad" : "warn") : "") +
        `<small>${r.status === "band" ? "bron: " + yjD(r.reserved_at) : r.check_in ? "kelgan: " + yjD(r.check_in) : ""}${r.check_out ? " · chiqqan: " + yjD(r.check_out) : ""}${r.out_reason ? " · " + esc(r.out_reason) : ""}</small>`],
      ["Qarz", r => r.debt ? `<b style="color:var(--bad)">${yjSum(r.debt)}</b>` : "—", "num"],
      ["Qayd", r => r.viol ? yjChip(String(r.viol), r.viol >= YJ.meta.rules.violations_warn ? "bad" : "warn") : "—"],
      ["", r => caps.dorm ? `<div class="yj-acts">${r.status === "band" ? `<button class="btn sm primary" data-in="${r.id}" type="button">Joylashdi</button><button class="btn sm ghost" data-cancel="${r.id}" type="button">Bronni bekor qilish</button>` :
        r.status === "yashaydi" ? `<button class="btn sm ghost" data-out="${r.id}" type="button">Chiqish</button>` : ""}</div>` : ""]],
      YJ.room ? rs.filter(r => r.room_id === YJ.room) : rs, {rowCls: r => r.mismatch || r.overdue_reserve ? "bad" : "", empty: "Yozuv yo'q"})}</div>`;
  box.querySelectorAll("[data-rst]").forEach(b => b.onclick = () => { YJ.rst = b.dataset.rst; yjDorms(box); });
  $("#yjRb").onchange = e => { YJ.rb = +e.target.value; yjDorms(box); };
  const q = $("#yjRq"); let t; q.oninput = () => { clearTimeout(t); t = setTimeout(() => { YJ.rq = q.value.trim(); yjDorms(box).then(() => { const n = $("#yjRq"); n.focus(); n.setSelectionRange(n.value.length, n.value.length); }); }, 350); };
  box.querySelectorAll("[data-room]").forEach(b => b.onclick = () => { YJ.room = YJ.room === +b.dataset.room ? null : +b.dataset.room; yjDorms(box); });
  $("#yjRoomX")?.addEventListener("click", () => { YJ.room = null; yjDorms(box); });
  box.querySelectorAll("[data-in]").forEach(b => b.onclick = async () => { if (await yjApi(`/api/yoshlar/residents/${b.dataset.in}/checkin`, {})) { toast("Talaba joylashdi — oylik hisob shu oydan boshlanadi"); yjDorms(box); } });
  box.querySelectorAll("[data-cancel]").forEach(b => b.onclick = async () => { if (!arm(b, "Ha, bekor qilish")) return; if (await yjApi(`/api/yoshlar/residents/${b.dataset.cancel}/cancel`, {})) { toast("Bron bekor qilindi, ariza navbatga qaytdi"); yjDorms(box); } });
  box.querySelectorAll("[data-out]").forEach(b => b.onclick = () => yjModal("Yotoqxonadan chiqish", `<label>Sabab<select data-r>${YJ.meta.out_reasons.filter(x => x !== "Tartib buzilishi (chiqarish)" || YJ.meta.caps.expel).map(x => `<option>${esc(x)}</option>`).join("")}</select></label>
      <label>Sana<input type="date" data-d value="${YJ.meta.today}"></label>`, async m => {
      const d = await yjApi(`/api/yoshlar/residents/${b.dataset.out}/checkout`, {reason: m.querySelector("[data-r]").value, date: m.querySelector("[data-d]").value});
      if (d) { toast("Chiqish rasmiylashtirildi — o'rin bo'shadi"); yjDorms(box); } return !!d; }, "Rasmiylashtirish"));
  box.querySelectorAll("[data-addroom]").forEach(b => b.onclick = () => yjModal("Xona qo'shish", `<div class="row2"><label>Xona raqami<input data-n maxlength="12"></label><label>Qavat<input type="number" data-f value="1" min="0" max="30"></label></div>
      <div class="row2"><label>O'rinlar soni<input type="number" data-b value="3" min="1" max="8"></label><label>Kim uchun<select data-g><option value="M">Yigitlar</option><option value="F">Qizlar</option></select></label></div>`, async m => {
      const d = await yjApi(`/api/yoshlar/buildings/${b.dataset.addroom}/rooms`, {number: m.querySelector("[data-n]").value, floor: +m.querySelector("[data-f]").value, beds: +m.querySelector("[data-b]").value, gender: m.querySelector("[data-g]").value});
      if (d) { toast("Xona qo'shildi"); yjDorms(box); } return !!d; }));
  $("#yjAddB")?.addEventListener("click", () => yjModal("Hamkor yotoqxona", `<label>Nomi<input data-n maxlength="120"></label><label>Manzil<input data-a maxlength="200"></label>
      <div class="row2"><label>Hamkor tashkilot<input data-p maxlength="160"></label><label>Shartnoma №<input data-c maxlength="60"></label></div>
      <div class="row2"><label>Shartnoma muddati<input type="date" data-u></label><label>Oylik to'lov (so'm)<input type="number" data-fee min="0" step="10000"></label></div>
      <label>Kim uchun<select data-g><option value="">Aralash (xonalar bo'yicha)</option><option value="M">Yigitlar</option><option value="F">Qizlar</option></select></label>`, async m => {
      const v = s => m.querySelector(s).value;
      const d = await yjApi("/api/yoshlar/buildings", {name: v("[data-n]"), address: v("[data-a]"), partner: v("[data-p]"), contract_no: v("[data-c]"), contract_until: v("[data-u]"), fee_month: +v("[data-fee]") || 0, gender: v("[data-g]")});
      if (d) { toast("Yotoqxona qo'shildi — endi xonalarni kiriting"); yjDorms(box); } return !!d; }));
}

/* =================== To'lovlar =================== */
async function yjCharges(box) {
  const caps = YJ.meta.caps;
  const d = await yjApi("/api/yoshlar/charges?" + yjQs({period: YJ.cp, debt: YJ.cdebt, q: YJ.cq})), T = d.total;
  const ST = {tolangan: ["To'langan", "ok"], qarz: ["Qarz", "bad"], kutilmoqda: ["Kutilmoqda", "info"]};
  box.innerHTML = `<div class="yj-kpis">${yjKpi("Hisoblangan", yjSum(T.amt))}${yjKpi("To'langan", yjSum(T.paid), "", "ok")}${yjKpi("Muddati o'tgan qarz", yjSum(T.debt), `${fmt(T.debtors)} nafar`, T.debt ? "bad" : "ok")}</div>
    <div class="card yj-card"><div class="yj-bar">
      <select id="yjCp"><option value="">Barcha oylar</option>${d.periods.map(p => `<option ${p === YJ.cp ? "selected" : ""}>${p}</option>`).join("")}</select>
      ${yjSeg([[0, "Hammasi"], [1, "Faqat qarzlar"]], YJ.cdebt, "cdebt")}
      <input type="search" id="yjCq" placeholder="Ism yoki HEMIS ID" value="${esc(YJ.cq)}">
      ${caps.charge ? `<button class="btn sm" id="yjGen" type="button">Oylik hisob yaratish</button>` : ""}</div>
    <p class="muted">To'lov ${YJ.meta.rules.due_day}-sanagacha. Pul kassa / bank orqali qabul qilinadi; bu yerda faqat kvitansiya raqami bilan qayd etiladi.</p>
    ${yjTable([
      ["Oy", r => `<b>${esc(r.period)}</b><small>${yjD(r.due)} gacha</small>`],
      ["Talaba", r => `${esc(r.full_name)}<small>${esc(r.building)}, ${esc(r.room)}-xona</small>`],
      ["Summa", r => yjSum(r.amount), "num"],
      ["To'langan", r => yjSum(r.paid) + (r.receipt ? `<small>${esc(r.receipt)} · ${yjD(r.paid_at)}${r.by_name ? " · " + esc(r.by_name) : ""}</small>` : ""), "num"],
      ["Holat", r => yjChip(...ST[r.state])],
      ["", r => caps.pay && r.state !== "tolangan" ? `<button class="btn sm primary" data-pay="${r.id}" type="button">To'lovni belgilash</button>` : ""]],
      d.items, {rowCls: r => r.state === "qarz" ? "bad" : "", empty: "Hisob yo'q"})}</div>`;
  $("#yjCp").onchange = e => { YJ.cp = e.target.value; yjCharges(box); };
  box.querySelectorAll("[data-cdebt]").forEach(b => b.onclick = () => { YJ.cdebt = +b.dataset.cdebt; yjCharges(box); });
  const q = $("#yjCq"); let t; q.oninput = () => { clearTimeout(t); t = setTimeout(() => { YJ.cq = q.value.trim(); yjCharges(box).then(() => { const n = $("#yjCq"); n.focus(); n.setSelectionRange(n.value.length, n.value.length); }); }, 350); };
  $("#yjGen")?.addEventListener("click", () => yjModal("Oylik hisob", `<label>Oy<input type="month" data-p value="${YJ.meta.today.slice(0, 7)}"></label>
      <p class="muted">Shu oyda yashagan barcha talabalarga bino tarifi bo'yicha hisob yoziladi. Takror bosilsa — mavjud hisoblar o'zgarmaydi.</p>`, async m => {
      const r = await yjApi("/api/yoshlar/charges/generate", {period: m.querySelector("[data-p]").value}); if (r) { toast(`${r.period}: ${r.created} ta yangi hisob`); YJ.cp = r.period; yjCharges(box); } return !!r; }, "Yaratish"));
  box.querySelectorAll("[data-pay]").forEach(b => b.onclick = () => { const r = d.items.find(x => x.id === +b.dataset.pay);
    yjModal(`To'lov: ${r.full_name}, ${r.period}`, `<div class="row2"><label>Summa (qolgan ${fmt(r.amount - r.paid)})<input type="number" data-a value="${r.amount - r.paid}" min="1" max="${r.amount - r.paid}"></label>
      <label>Kvitansiya / to'lov hujjati №<input data-k maxlength="60"></label></div>`, async m => {
      const x = await yjApi(`/api/yoshlar/charges/${r.id}/pay`, {amount: +m.querySelector("[data-a]").value, receipt: m.querySelector("[data-k]").value});
      if (x) { toast(x.left ? `Qisman to'landi · qoldi ${yjSum(x.left)}` : "To'liq to'landi"); yjCharges(box); } return !!x; }, "Belgilash"); });
}

/* =================== Tartib =================== */
async function yjViol(box) {
  const caps = YJ.meta.caps;
  const rs = await yjApi("/api/yoshlar/violations?" + yjQs({q: YJ.vq}));
  box.innerHTML = `<div class="card yj-card"><div class="yj-bar"><input type="search" id="yjVq" placeholder="Ism yoki HEMIS ID" value="${esc(YJ.vq)}">
      ${caps.violation ? `<button class="btn sm primary" id="yjVNew" type="button">Qayd kiritish</button>` : ""}</div>
    <p class="muted">${YJ.meta.rules.violations_warn} ta qayd to'plangan yashovchi bo'yicha chiqarish masalasi ko'riladi. Yotoqxonadan chiqarish — faqat prorektor qarori bilan.</p>
    ${yjTable([
      ["Sana", r => yjD(r.date)],
      ["Talaba", r => `<b>${esc(r.full_name)}</b><small>${esc(r.grp || "")} · ${esc(r.building)}, ${esc(r.room)}-xona</small>`],
      ["Qoidabuzarlik", r => `${esc(r.kind)}<small>${esc(r.text)}</small>`],
      ["Chora", r => yjChip(r.measure_l, r.measure === "chiqarish" ? "bad" : r.measure === "hayfsan" ? "warn" : "")],
      ["Jami", r => yjChip(String(r.total), r.total >= YJ.meta.rules.violations_warn ? "bad" : ""), "num"],
      ["Kiritgan", r => esc(r.by_name || "—")]], rs, {empty: "Qaydlar yo'q"})}</div>`;
  const q = $("#yjVq"); let t; q.oninput = () => { clearTimeout(t); t = setTimeout(() => { YJ.vq = q.value.trim(); yjViol(box).then(() => { const n = $("#yjVq"); n.focus(); n.setSelectionRange(n.value.length, n.value.length); }); }, 350); };
  $("#yjVNew")?.addEventListener("click", async () => {
    const res = await yjApi("/api/yoshlar/residents?status=yashaydi");
    const m = yjModal("Tartib buzilishi qaydi", `<label>Yashovchi<select data-s>${res.map(r => `<option value="${r.id}">${esc(r.full_name)} — ${esc(r.room)}-xona</option>`).join("")}</select></label>
      <div class="row2"><label>Turi<select data-k>${YJ.meta.viol_kinds.map(k => `<option>${esc(k)}</option>`).join("")}</select></label><label>Sana<input type="date" data-d value="${YJ.meta.today}"></label></div>
      <label>Tavsif<textarea data-t maxlength="500" placeholder="Nima bo'ldi, kim guvoh"></textarea></label>
      <label>Chora<select data-m>${Object.entries(YJ.meta.measures).filter(([k]) => k !== "chiqarish" || caps.expel).map(([k, v]) => `<option value="${k}">${esc(v)}</option>`).join("")}</select></label>`, async m => {
      const v = s => m.querySelector(s).value;
      const d = await yjApi("/api/yoshlar/violations", {resident_id: +v("[data-s]"), kind: v("[data-k]"), text: v("[data-t]"), measure: v("[data-m]"), date: v("[data-d]")});
      if (d) { toast(d.warn ? `Qayd saqlandi — bu yashovchida ${d.count} ta qayd: chiqarish masalasini ko'ring` : "Qayd saqlandi"); yjViol(box); } return !!d; });
  });
}

/* =================== Ijara =================== */
async function yjRent(box) {
  const caps = YJ.meta.caps;
  const rs = await yjApi("/api/yoshlar/rentals?" + yjQs({q: YJ.xq, stale: YJ.xstale}));
  const C = {yaxshi: "ok", qoniqarli: "info", qoniqarsiz: "bad"};
  box.innerHTML = `<div class="card yj-card"><div class="yj-bar">${yjSeg([[0, "Hammasi"], [1, "90 kundan beri tashrifsiz"]], YJ.xstale, "xstale")}
      <input type="search" id="yjXq" placeholder="Ism, HEMIS ID yoki tuman" value="${esc(YJ.xq)}">
      ${caps.rental ? `<button class="btn sm" id="yjXNew" type="button">Ijara qaydi</button>` : ""}</div>
    <p class="muted">Ijarada yashovchi talabalar: manzil va tyutor tashrifi (dalolatnoma). Har chorakda kamida bir marta tashrif tavsiya etiladi.</p>
    ${yjTable([
      ["Talaba", r => `<b>${esc(r.full_name)}</b><small>${esc(r.grp || "")} · ${esc(r.region || "")}</small>`],
      ["Manzil", r => `${esc(r.address)}<small>${esc(r.district)} · ${yjSum(r.rent)}/oy${r.has_contract ? " · shartnoma bor" : " · shartnomasiz"}</small>`],
      ["Oxirgi tashrif", r => r.last_visit ? `${yjD(r.last_visit)} ${yjChip(r.condition || "", C[r.condition] || "")}<small>${esc(r.visit_note || "")}${r.visited_name ? " · " + esc(r.visited_name) : ""}</small>` : yjChip("Tashrif bo'lmagan", "warn")],
      ["", r => caps.rental ? `<button class="btn sm" data-visit="${r.id}" type="button">Tashrif qaydi</button>` : ""]],
      rs, {rowCls: r => r.stale ? "warn" : "", empty: "Qaydlar yo'q"})}</div>`;
  box.querySelectorAll("[data-xstale]").forEach(b => b.onclick = () => { YJ.xstale = +b.dataset.xstale; yjRent(box); });
  const q = $("#yjXq"); let t; q.oninput = () => { clearTimeout(t); t = setTimeout(() => { YJ.xq = q.value.trim(); yjRent(box).then(() => { const n = $("#yjXq"); n.focus(); n.setSelectionRange(n.value.length, n.value.length); }); }, 350); };
  box.querySelectorAll("[data-visit]").forEach(b => b.onclick = () => yjModal("Ijara tashrifi", `<div class="row2"><label>Sana<input type="date" data-d value="${YJ.meta.today}"></label>
      <label>Sharoit<select data-c><option value="yaxshi">Yaxshi</option><option value="qoniqarli">Qoniqarli</option><option value="qoniqarsiz">Qoniqarsiz</option></select></label></div>
      <label>Izoh<textarea data-n maxlength="500" placeholder="Yashash sharoiti, kim bilan yashaydi, muammolar"></textarea></label>`, async m => {
      const d = await yjApi(`/api/yoshlar/rentals/${b.dataset.visit}/visit`, {date: m.querySelector("[data-d]").value, condition: m.querySelector("[data-c]").value, note: m.querySelector("[data-n]").value});
      if (d) { toast("Tashrif qayd etildi"); yjRent(box); } return !!d; }));
  $("#yjXNew")?.addEventListener("click", () => { let pick = null;
    const m = yjModal("Ijarada yashovchi talaba", `<label>Talaba<input data-pq placeholder="Ism yoki HEMIS ID"></label><div class="yj-pick" data-pl></div>
      <label>Manzil<input data-a maxlength="200" placeholder="Ko'cha, uy, xonadon"></label>
      <div class="row2"><label>Tuman<input data-t maxlength="80"></label><label>Ijara haqi (so'm/oy)<input type="number" data-r min="0" step="50000"></label></div>
      <div class="row2"><label>Qachondan<input type="date" data-s value="${YJ.meta.today}"></label><label class="ck" style="margin-top:22px"><input type="checkbox" data-c> Uy egasi bilan shartnoma bor</label></div>`, async m => {
      if (!pick) { toast("Talabani tanlang"); return false; }
      const v = s => m.querySelector(s).value;
      const d = await yjApi("/api/yoshlar/rentals", {student_id: pick.id, address: v("[data-a]"), district: v("[data-t]"), rent: +v("[data-r]") || 0, since: v("[data-s]"), has_contract: m.querySelector("[data-c]").checked});
      if (d) { toast("Saqlandi"); yjRent(box); } return !!d; });
    yjPicker(m, s => pick = s); });
}

/* =================== Tadbirlar =================== */
async function yjEvents(box) {
  if (YJ.ev) return yjEvent(box, YJ.ev);
  const caps = YJ.meta.caps;
  const rs = await yjApi("/api/yoshlar/events?" + yjQs({status: YJ.est}));
  const ST = {reja: "", tasdiqlashda: "warn", tasdiqlangan: "info", rad: "bad", otkazildi: "ok"};
  const today = YJ.meta.today;
  box.innerHTML = `<div class="card yj-card"><div class="yj-bar">${yjSeg([["", "Hammasi"], ...Object.entries(YJ.meta.ev_st)], YJ.est, "est")}<span class="grow"></span>
      ${caps.event ? `<button class="btn sm primary" id="yjENew" type="button">Tadbir rejalashtirish</button>` : ""}</div>
    <p class="muted">Tartib: reja → tasdiqlashga yuborish → prorektor tasdig'i → o'tkazish (ishtirokchilar, QR qatnashuv) → hisobot. Tasdiqlangan tadbirga talabalar kabinetdan yoziladi.</p>
    <div class="yj-list">${rs.map(e => `<div class="yj-item"><div class="yj-item-h"><div><b>${esc(e.title)}</b><small class="muted" style="display:block">${yjD(e.date)}${e.start_time ? " · " + esc(e.start_time) : ""}${e.venue ? " · " + esc(e.venue) : ""} · ${esc(e.kind_l || "")}</small></div>
        <div class="yj-acts">${yjChip(e.status_l || "—", ST[e.status] || "")}${e.status === "tasdiqlangan" && e.date < today ? yjChip("Hisobot kutilmoqda", "warn") : ""}</div></div>
      <p>${e.status === "otkazildi" ? `Ishtirokchilar: ${fmt(e.participants || 0)}${e.came ? ` (QR/qayd: ${fmt(e.came)})` : ""}` : `Yozilgan: ${fmt(e.reg)}${e.capacity ? " / " + fmt(e.capacity) : ""}${e.budget ? " · smeta " + yjSum(e.budget) : ""}`}${e.reject_reason ? `\nRad etish sababi: ${esc(e.reject_reason)}` : ""}${e.approved_name ? ` · tasdiqladi: ${esc(e.approved_name)}` : ""}</p>
      <div class="yj-acts"><button class="btn sm ghost" data-open="${e.id}" type="button">Ochish</button>
        ${caps.event && ["reja", "rad"].includes(e.status) ? `<button class="btn sm" data-sub="${e.id}" type="button">Tasdiqlashga yuborish</button>` : ""}
        ${caps.approve && e.status === "tasdiqlashda" ? `<button class="btn sm primary" data-appr="${e.id}" type="button">Tasdiqlash</button><button class="btn sm ghost" data-erej="${e.id}" type="button">Rad etish</button>` : ""}
        ${caps.event && e.status === "tasdiqlangan" && e.date <= today ? `<button class="btn sm primary" data-hold="${e.id}" type="button">O'tkazildi — hisobot</button>` : ""}</div></div>`).join("") || `<div class="yj-empty">Tadbirlar yo'q</div>`}</div></div>`;
  box.querySelectorAll("[data-est]").forEach(b => b.onclick = () => { YJ.est = b.dataset.est; yjEvents(box); });
  box.querySelectorAll("[data-open]").forEach(b => b.onclick = () => { YJ.ev = +b.dataset.open; yjEvents(box); });
  box.querySelectorAll("[data-sub]").forEach(b => b.onclick = async () => { if (await yjApi(`/api/yoshlar/events/${b.dataset.sub}/submit`, {})) { toast("Prorektor tasdig'iga yuborildi"); yjEvents(box); } });
  box.querySelectorAll("[data-appr]").forEach(b => b.onclick = async () => { if (!arm(b, "Ha, tasdiqlash")) return; if (await yjApi(`/api/yoshlar/events/${b.dataset.appr}/approve`, {})) { toast("Tadbir tasdiqlandi — talabalar kabinetda ko'radi"); yjEvents(box); } });
  box.querySelectorAll("[data-erej]").forEach(b => b.onclick = () => yjModal("Tadbirni rad etish", `<label>Sabab (tashkilotchiga ko'rinadi)<textarea data-r maxlength="500"></textarea></label>`, async m => {
    const d = await yjApi(`/api/yoshlar/events/${b.dataset.erej}/reject`, {reason: m.querySelector("[data-r]").value}); if (d) { toast("Rad etildi"); yjEvents(box); } return !!d; }, "Rad etish"));
  box.querySelectorAll("[data-hold]").forEach(b => b.onclick = () => yjHoldModal(+b.dataset.hold, box));
  $("#yjENew")?.addEventListener("click", () => yjModal("Tadbir rejasi", `<label>Nomi<input data-t maxlength="200"></label>
      <div class="row2"><label>Sana<input type="date" data-d min="${today}"></label><label>Boshlanishi<input type="time" data-s value="14:00"></label></div>
      <div class="row2"><label>Joy<input data-v maxlength="120" placeholder="Majlislar zali"></label><label>Turi<select data-k>${Object.entries(YJ.meta.ev_kinds).map(([k, v]) => `<option value="${esc(k)}">${esc(v)}</option>`).join("")}</select></label></div>
      <div class="row2"><label>Kimlar uchun<input data-a maxlength="160" placeholder="Masalan: 1-kurs talabalari"></label><label>Joylar soni (0 — cheklanmagan)<input type="number" data-c value="0" min="0"></label></div>
      <div class="row2"><label>Smeta (so'm)<input type="number" data-b value="0" min="0" step="100000"></label><label>Mas'ul<input data-o maxlength="120" placeholder="${esc(yjShort(ME?.name || ""))}"></label></div>
      <label>Maqsad va dastur<textarea data-n maxlength="1000"></textarea></label>`, async m => {
      const v = s => m.querySelector(s).value;
      const d = await yjApi("/api/yoshlar/events", {title: v("[data-t]"), date: v("[data-d]"), start_time: v("[data-s]"), venue: v("[data-v]"), kind: v("[data-k]"), audience: v("[data-a]"),
        capacity: +v("[data-c]") || 0, budget: +v("[data-b]") || 0, organizer: v("[data-o]"), plan_note: v("[data-n]")});
      if (d) { toast("Reja saqlandi — tayyor bo'lgach tasdiqlashga yuboring"); yjEvents(box); } return !!d; }));
}
function yjHoldModal(eid, box) {
  yjModal("Tadbir hisoboti", `<label>Ishtirokchilar soni (QR / qayd bo'yicha sanalganidan kam bo'lsa — sanalgani olinadi)<input type="number" data-p min="0" value="0"></label>
    <label>Hisobot: nima qilindi, natija, muammolar<textarea data-r maxlength="3000"></textarea></label>`, async m => {
    const d = await yjApi(`/api/yoshlar/events/${eid}/hold`, {participants: +m.querySelector("[data-p]").value || 0, report: m.querySelector("[data-r]").value});
    if (d) { toast("Hisobot saqlandi"); YJ.ev = null; yjEvents(box); } return !!d; }, "Saqlash");
}
async function yjEvent(box, eid) {
  const e = await yjApi(`/api/yoshlar/events/${eid}`), caps = YJ.meta.caps, today = YJ.meta.today;
  const canPeople = caps.event && ["tasdiqlangan", "otkazildi"].includes(e.status);
  box.innerHTML = `<div class="yj-bar"><button class="btn sm ghost" id="yjEBack" type="button">← Tadbirlar</button></div>
    <div class="card yj-card"><div class="yj-item-h"><div><h3>${esc(e.title)}</h3><span class="muted">${yjD(e.date)}${e.start_time ? " · " + esc(e.start_time) : ""}${e.venue ? " · " + esc(e.venue) : ""} · ${esc(e.kind_l || "")}${e.organizer ? " · mas'ul: " + esc(e.organizer) : ""}</span></div>${yjChip(e.status_l || "—")}</div>
      ${e.plan_note ? `<p style="white-space:pre-wrap">${esc(e.plan_note)}</p>` : ""}
      ${e.report ? `<h3 style="margin-top:12px">Hisobot</h3><p style="white-space:pre-wrap">${esc(e.report)}</p><p class="muted">Ishtirokchilar: ${fmt(e.participants || 0)}</p>` : ""}
      ${e.by_faculty.length ? `<p class="muted">Fakultetlar kesimida: ${e.by_faculty.map(f => `${esc(f.name)} — ${f.n}`).join("; ")}</p>` : ""}
      ${caps.event && e.status === "tasdiqlangan" && e.date <= today ? `<div class="yj-acts"><button class="btn sm primary" id="yjEHold" type="button">O'tkazildi — hisobot</button></div>` : ""}</div>
    <div class="card yj-card"><div class="yj-bar"><b class="grow">Ishtirokchilar (${e.people.length})</b>
      ${canPeople ? `<button class="btn sm" id="yjEAdd" type="button">Talaba qo'shish</button>` : ""}</div>
      ${yjTable([["Talaba", p => `${esc(p.full_name)}<small>${esc(p.grp || "")}</small>`], ["Yozilgan", p => p.reg ? yjChip("ha", "info") : "—"],
        ["Keldi", p => p.came ? yjChip("keldi", "ok") : (canPeople && e.date <= today ? `<button class="btn sm ghost" data-came="${p.id}" type="button">Keldi</button>` : "—")]], e.people, {empty: "Hali hech kim yozilmagan"})}</div>`;
  $("#yjEBack").onclick = () => { YJ.ev = null; yjEvents(box); };
  $("#yjEHold")?.addEventListener("click", () => yjHoldModal(eid, box));
  box.querySelectorAll("[data-came]").forEach(b => b.onclick = async () => { if (await yjApi(`/api/yoshlar/events/${eid}/attend`, {student_ids: [+b.dataset.came]})) yjEvent(box, eid); });
  $("#yjEAdd")?.addEventListener("click", () => { let pick = null;
    const m = yjModal("Ishtirokchi qo'shish", `<label>Talaba<input data-pq placeholder="Ism yoki HEMIS ID"></label><div class="yj-pick" data-pl></div>
      ${e.date <= today ? `<label class="ck"><input type="checkbox" data-c checked> Tadbirda qatnashdi deb belgilash</label>` : ""}`, async m => {
      if (!pick) { toast("Talabani tanlang"); return false; }
      const att = m.querySelector("[data-c]")?.checked;
      const d = await yjApi(`/api/yoshlar/events/${eid}/${att ? "attend" : "participants"}`, {student_ids: [pick.id]});
      if (d) { toast(d.added ? "Qo'shildi" : "Allaqachon ro'yxatda"); yjEvent(box, eid); } return !!d; }, "Qo'shish");
    yjPicker(m, s => pick = s); });
}
