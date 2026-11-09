/* =====================================================================
   AI agentlar markazi — ISFT Core agentlari, avtonomiya darajalari, inson tasdig'i.
   app.js yordamchilaridan foydalanadi: J, esc, toast, go, busy, dmy, ME, ask, badges, ico, ICONS.
   Global: renderAgents(), briefCardHtml()
   Uslublar: agents.css (shu fayldan ulanadi)
   ===================================================================== */
const AGS = {lvl: null, open: new Set()};
if (!document.querySelector('link[href="agents.css"]')) document.head.insertAdjacentHTML("beforeend", '<link rel="stylesheet" href="agents.css">');

/* qo'shimcha ikonkalar (app.js da bo'lmasa) */
if (typeof ICONS === "object") {
  if (!ICONS.spark) ICONS.spark = '<path d="M12 3l1.9 5.6L19.5 10.5l-5.6 1.9L12 18l-1.9-5.6L4.5 10.5l5.6-1.9z"/><path d="M19 3v4M17 5h4M5 17v4M3 19h4"/>';
  if (!ICONS.bot) ICONS.bot = '<rect x="4" y="8" width="16" height="12" rx="3"/><path d="M12 8V4M8 4h8M9 14h.01M15 14h.01M2 13v3M22 13v3"/>';
  if (!ICONS.chev) ICONS.chev = '<path d="m6 9 6 6 6-6"/>';
  /* menyudagi bo'sh ikonkani qayta chizish */
  try { const s = document.querySelector('#nav a[data-v="agents"] svg'); if (s && !s.innerHTML.trim()) { s.remove(); hydrateIcons(); } } catch (e) {}
}

const AG_ICO = {brief: "sun", ijro: "pin", talaba: "cap", moliya: "money", hujjat: "file", talaba247: "bot"};
const AG_ST = {taklif: ["Kutmoqda", "mid"], bajarildi: ["Bajarildi", "low"], rad: ["Rad etildi", "gray"]};
const AG_APPROVER = {moliya: "rektor yoki moliya prorektori", talaba: "rektor yoki o'quv prorektori", ijro: "rektor yoki kotib"};
const agIco = (k, sz = 18) => ico(AG_ICO[k] || "spark", sz);
const agTime = s => { if (!s) return ""; const d = new Date(s), t = `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`; return s.slice(0, 10) === (ME?.today || "") ? `bugun, ${t}` : `${dmy(s.slice(0, 10))}, ${t}`; };
const agMeter = l => `<span class="ag-meter" role="img" aria-label="Avtonomiya: ${l}-daraja">${[0, 1, 2, 3].map(i => `<i class="${i <= l ? "on" : ""}"></i>`).join("")}</span>`;
const agStTag = s => `<span class="ag-tag ${(AG_ST[s] || ["", "gray"])[1]}">${esc((AG_ST[s] || [s])[0])}</span>`;
const agShort = n => String(n || "").includes(":") ? String(n).split(":").slice(1).join(":").trim() : (n || "");
/* "(5 kun o'tgan)" — haqiqiy muammo, qizil bilan */
const agOverdue = t => { const s = String(t || ""), m = s.match(/\((\d+ kun o['‘’]tgan)\)/); return m ? esc(s.slice(0, m.index)) + `<span class="ag-late">${esc(m[1])}</span>` + esc(s.slice(m.index + m[0].length)) : esc(s); };

/* ---------- tasdiq kutayotgan takliflar: ixcham ro'yxat ---------- */
function agPropMeta(p) {
  if (p.effect === "task") return [p.assignee && esc(p.assignee), p.due && `muddat ${dmy(p.due)}`].filter(Boolean).join(" · ");
  const first = String(p.detail || "").split(/\.\s+Tasdiqlansa/)[0];
  return agOverdue(first);
}
function agPropMore(p) {
  const rest = p.effect === "remind" ? "" : String(p.detail || "");
  const eff = p.effect === "task" ? `«${esc(p.assignee || "ijrochi")}»ga${p.due ? ` ${dmy(p.due)} muddatli` : ""} yangi topshiriq yaratiladi.`
    : p.effect === "remind" ? "Ijrochiga rasmiy eslatma yuboriladi va topshiriq tarixiga yoziladi."
    : "Faqat qayd etiladi — boshqa amal bajarilmaydi.";
  return `<div class="ag-it-more">
      ${rest ? `<p>${agOverdue(rest)}</p>` : ""}
      <div class="ag-eff">${ico("info", 16)}<span><b>Tasdiqlansa:</b> ${eff} Rad etilsa — hech narsa o'zgarmaydi.</span></div>
      <div class="ag-facts">
        <span>${agIco(p.agent, 14)} ${esc(p.agent_name)}</span>
        <span>${agMeter(p.level)} ${p.level}-daraja</span>
        <span>${ico("clock", 14)} ${agTime(p.created_at)}</span>
      </div>
    </div>`;
}
function agPendingHtml(p) {
  const open = AGS.open.has(p.id);
  const act = p.can_approve
    ? `<button class="btn sm primary" data-ag-ok="${p.id}">${ico("check", 16)}Tasdiqlash</button><button class="btn sm ghost" data-ag-no="${p.id}">Rad etish</button>`
    : `<span class="ag-who">Tasdiqlovchi: ${esc(AG_APPROVER[p.agent] || "rektor")}</span>`;
  return `<div class="ag-it${open ? " open" : ""}" data-id="${p.id}">
    <div class="ag-it-row">
      <button class="ag-it-main" data-ag-tog="${p.id}" aria-expanded="${open}">
        <span class="ag-av">${agIco(p.agent, 18)}</span>
        <span class="ag-it-txt"><b>${esc(p.title)}</b><span class="ag-it-meta">${agPropMeta(p)}</span></span>
        <span class="ag-chev">${ico("chev", 16)}</span>
      </button>
      <div class="ag-it-act">${act}</div>
    </div>
    ${agPropMore(p)}
  </div>`;
}

/* ---------- agent kartasi ---------- */
function agCardHtml(a, L) {
  const pilot = a.status !== "faol";
  const st = pilot ? `<span class="ag-tag gray">Pilot</span>` : `<span class="ag-tag low"><i class="ag-live"></i>Faol</span>`;
  const stats = pilot ? `<div class="ag-plan">${ico("clock", 14)} Rejada · hali ishga tushirilmagan</div>`
    : `<div class="ag-nums">
        <div><b>${a.stats.today}</b><span>bugun</span></div>
        <div class="${a.stats.pending ? "warn" : ""}"><b>${a.stats.pending}</b><span>kutmoqda</span></div>
        <div><b>${a.stats.done}</b><span>bajarildi</span></div>
      </div>`;
  return `<div class="card ag-card${pilot ? " pilot" : ""}">
    <div class="ag-top"><span class="ag-ic">${agIco(a.key, 22)}</span>
      <div class="ag-name"><b>${esc(a.name)}</b><span class="ag-sees" title="Ko'radi: ${esc(a.sees)}">${ico("eye", 14)} ${esc(a.sees)}</span></div>${st}</div>
    <p class="ag-desc" title="${esc(a.desc)}">${esc(a.desc)}</p>
    <div class="ag-lvl">${agMeter(a.level)}<span><b>${a.level}-daraja</b> · ${esc(L[a.level])}</span></div>
    ${stats}
    ${!pilot && a.can_approve ? `<div class="ag-you">${ico("checkc", 14)} Takliflarini siz tasdiqlaysiz</div>` : ""}
  </div>`;
}

/* ---------- so'nggi amallar: ixcham vaqt chizig'i ---------- */
function agFeedHtml(x) {
  return `<li class="ag-ev ${x.status}">
    <span class="ag-ev-t">${agTime(x.decided_at || x.created_at)}</span>
    <span class="ag-ev-dot"></span>
    <div class="ag-ev-b">
      <div class="ag-ev-h"><span class="ag-ev-ic">${agIco(x.agent, 14)}</span><b>${esc(x.title)}</b>${agStTag(x.status)}${x.level === 3 ? `<span class="ag-tag gray">avtomatik</span>` : ""}</div>
      ${x.result ? `<div class="ag-ev-r">${esc(x.result)}</div>` : ""}
      <div class="ag-ev-m">${esc(x.agent_name)}${x.decided_by ? ` · ${esc(agShort(x.decided_by) || x.decided_by)}` : ""}</div>
    </div></li>`;
}

async function renderAgents() {
  const el = document.getElementById("v-agents"); if (!el) return;
  if (!el.innerHTML) el.innerHTML = `<p class="muted">Yuklanmoqda…</p>`;
  const d = await J("/api/agents");
  AGS.lvl = d.levels;
  const L = d.levels, ro = d.read_only, mine = d.pending.filter(p => p.can_approve);
  let h = `<div class="head"><div><h2>AI agentlar markazi</h2><span class="muted">ISFT Core ichidagi ixtisoslashgan yordamchilar · ${dmy(d.today)}</span></div>
    ${d.can_run ? `<button class="btn" id="agRun">${ico("refresh", 16)}Hozir ishga tushirish</button>` : ""}</div>
    <div class="ag-explain"><span class="ag-explain-ic">${ico("shield", 20)}</span><div>
      <b>Agentlar faqat ruxsat etilgan ma'lumotni ko'radi. Xavfli amal — faqat inson tasdig'idan keyin. Har bir amal audit jurnalida.</b>
      <div class="ag-legend">${Object.entries(L).map(([k, v]) => `<span>${agMeter(+k)}<b>${k}</b> ${esc(v)}</span>`).join("")}</div></div></div>`;

  h += `<div class="card ag-pending"><div class="ag-ph"><h3>${ico("clock", 18)} Tasdiqlash kutilmoqda <span class="ag-count">${d.pending.length}</span></h3>
      ${ro ? `<span class="ag-tag gray">Faqat ko'rish rejimi</span>` : mine.length > 1 ? `<div class="ag-bulk"><button class="btn sm ghost hidden" id="agAllNo">Bekor qilish</button><button class="btn sm" id="agAll">${ico("check", 16)}Barchasini tasdiqlash</button></div>` : ""}</div>` +
    (d.pending.length ? `<div class="ag-list">${d.pending.map(agPendingHtml).join("")}</div>`
      : `<div class="ag-empty">${ico("checkc", 18)} Hozircha tasdiq kutayotgan taklif yo'q — agentlar hammasini nazorat qilmoqda.</div>`) + `</div>`;

  h += `<h3 class="ag-h3">Agentlar</h3><div class="ag-grid">${d.agents.map(a => agCardHtml(a, L)).join("")}</div>`;
  h += `<div class="card ag-feedc"><div class="ag-ph"><h3>${ico("history", 18)} So'nggi amallar</h3><span class="ag-sub">Har bir amal audit jurnalida ham saqlanadi</span></div>
    ${d.actions.length ? `<ol class="ag-feed">${d.actions.map(agFeedHtml).join("")}</ol>` : `<p class="muted" style="margin:0">Hali amal yo'q.</p>`}</div>`;
  el.innerHTML = h;

  const after = async () => { await renderAgents(); if (typeof badges === "function") badges(); };
  const run = document.getElementById("agRun");
  if (run) run.onclick = () => busy(run, async () => { const r = await J("/api/agents/run", {method: "POST"}); toast(r.message); await after(); }, "Ishlamoqda…");

  const act = (b, ok) => busy(b, async () => {
    const id = ok ? b.dataset.agOk : b.dataset.agNo;
    const r = await J(`/api/agents/actions/${id}/${ok ? "approve" : "reject"}`, {method: "POST"});
    AGS.open.delete(+id); toast(r.result || "Bajarildi"); await after();
  });
  el.querySelectorAll("[data-ag-ok]").forEach(b => b.onclick = () => act(b, true));
  el.querySelectorAll("[data-ag-no]").forEach(b => b.onclick = () => act(b, false));
  el.querySelectorAll("[data-ag-tog]").forEach(b => b.onclick = () => {
    const it = b.closest(".ag-it"), id = +b.dataset.agTog, on = it.classList.toggle("open");
    b.setAttribute("aria-expanded", on); on ? AGS.open.add(id) : AGS.open.delete(id);
  });

  /* "Barchasini tasdiqlash" — ikki bosqichli, brauzer oynasisiz */
  const all = document.getElementById("agAll"), no = document.getElementById("agAllNo");
  if (all) {
    const idle = all.innerHTML;
    const reset = () => { clearTimeout(AGS.t); all.dataset.armed = ""; all.classList.remove("primary"); all.innerHTML = idle; no.classList.add("hidden"); };
    no.onclick = reset;
    all.onclick = () => {
      if (!all.dataset.armed) {
        all.dataset.armed = 1; all.classList.add("primary"); all.innerHTML = `${ico("check", 16)}Ha, ${mine.length} tasini tasdiqlash`;
        no.classList.remove("hidden"); clearTimeout(AGS.t); AGS.t = setTimeout(reset, 6000); return;
      }
      clearTimeout(AGS.t); no.classList.add("hidden");
      busy(all, async () => {
        let n = 0;
        for (const p of mine) { try { const r = await J(`/api/agents/actions/${p.id}/approve`, {method: "POST"}); if (r.ok !== false) n++; } catch (e) {} }
        AGS.open.clear(); toast(`${n} ta taklif tasdiqlandi${n < mine.length ? ` (${mine.length - n} tasi bajarilmadi)` : ""}`); await after();
      }, "Tasdiqlanmoqda…");
    };
  }
}

/* ---------- boshqaruv paneli: kunlik brifing (ruxsat yo'q bo'lsa — bo'sh satr) ---------- */
const AG_WD = ["yakshanba", "dushanba", "seshanba", "chorshanba", "payshanba", "juma", "shanba"];
const AG_MO = ["yanvar", "fevral", "mart", "aprel", "may", "iyun", "iyul", "avgust", "sentabr", "oktabr", "noyabr", "dekabr"];
const agDate = s => { const t = new Date(String(s).slice(0, 10) + "T00:00:00"); return isNaN(t) ? esc(s) : `${t.getDate()}-${AG_MO[t.getMonth()]}, ${AG_WD[t.getDay()]}`; };
const AG_LV = {high: "Yuqori ahamiyat", mid: "O'rta ahamiyat", low: "Past ahamiyat"};
function agAsk(q) { go("chat"); setTimeout(() => { try { ask(q); } catch (e) {} }, 60); }
async function briefCardHtml() {
  try {
    if (!ME || !(["rektor", "kengash"].includes(ME.role_key) || String(ME.role_key).startsWith("prorektor_"))) return "";
    const r = await fetch("/api/agents/brief", {credentials: "same-origin"});
    if (!r.ok) return "";
    const b = await r.json();
    briefCardHtml.last = b;
    /* tasdiq kutayotganlar soni panelning holat qatorida ko'rsatiladi — bu yerda takrorlanmaydi */
    const pend = `<button class="btn sm ghost ag-b-pend" onclick="go('agents')">AI agentlar${ico("arrow", 16)}</button>`;
    return `<section class="card ag-brief">
      <div class="ag-b-head">
        <span class="ag-b-ic">${ico("sun", 22)}</span>
        <div class="ag-b-ttl"><h3>Bugungi brifing</h3><span title="${esc(b.note || "")}">${agDate(b.date)} · ${esc(b.agent)}</span></div>
        ${pend}
      </div>
      ${b.priorities.length ? `<ol class="ag-b-list">${b.priorities.map((p, i) => `<li>
        <span class="ag-b-n">${i + 1}</span>
        <div class="ag-b-body"><div class="ag-b-t"><i class="ag-lv ${esc(p.level)}" title="${AG_LV[p.level] || ""}"></i><span><b>${esc(p.area)}.</b> ${esc(p.text)}</span></div>
          <button class="ag-b-ask" data-ag-ask="${esc(p.q)}" title="${esc(p.q)}">Batafsil so'rash${ico("arrow", 14)}</button></div></li>`).join("")}</ol>`
        : `<div class="ag-empty">${ico("checkc", 18)} Bugun alohida e'tibor talab qiladigan masala yo'q.</div>`}
      ${b.forecast ? `<div class="ag-b-fc">${ico("money", 18)}<span>${esc(b.forecast)}</span></div>` : ""}
    </section>`;
  } catch (e) { return ""; }
}
/* brifing kartasidagi savol tugmalari (karta HTML sifatida qo'yiladi — delegatsiya) */
document.addEventListener("click", e => { const b = e.target.closest?.("[data-ag-ask]"); if (b) { e.preventDefault(); agAsk(b.dataset.agAsk); } });
