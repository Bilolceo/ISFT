/* =====================================================================
   «Nazorat markazi» (app/nazorat.py, /api/nazorat) — rektor faqat nazorat qiladi: istisnolar, egalari va 4 amal.
     nazorat  — sohalar bo'yicha istisnolar (qizil — sizgacha yetib kelgan; sariq — rahbarlar darajasida; yashil — «Hammasi joyida»);
                amallar: Eslatish · Muddat berish · Qayta tayinlash / yuqoriga ko'tarish · Ko'rdim. Qoidalar (eskalatsiya kunlari) — rektor.
     imzo     — imzo navbati: rahbar qarorini kutayotgan hujjatlar, eng eskisi birinchi; buyruqni shu yerda imzolash / izoh bilan qaytarish.
     haftalik — haftalik hisobot (dushanba 08:00): 5–8 qator va kerakli 3 qaror.
     barcha   — «Barcha bo'limlar»: rektorning ixcham menyusidan olingan bandlar (bo'limlar kaliti va ruxsatlar saqlanadi).
   Menyu: rektor — 5 band (server: /api/nazorat/meta → menu); prorektor — menyusi boshiga Nazorat markazi va Imzo navbati qo'shiladi.
   index.html va app.js ga tegmaslik uchun bandlar, bo'limlar va go()/navApply()/boot()/badges() o'ramlari shu faylda.
   Yordamchilar: app.js ($, esc, J, toast, busy, arm, ico, ICONS, ME, go, dmy, locked, errCard), extras.js (XT.openLink).
   ===================================================================== */
const NZS = {meta: null, data: null, showLower: {}, focus: null, all: [], homeOnce: false, brief: null};
if (!document.querySelector('link[href="nazorat.css"]')) document.head.insertAdjacentHTML("beforeend", '<link rel="stylesheet" href="nazorat.css">');
Object.assign(ICONS, {
  radar: '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="5"/><path d="M12 12 19 5"/><circle cx="12" cy="12" r="1"/>',
  stamp: '<path d="M5 22h14"/><path d="M19.27 13.73A2.5 2.5 0 0 0 17.5 13h-11A2.5 2.5 0 0 0 4 15.5V17a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-1.5c0-.66-.26-1.3-.73-1.77Z"/><path d="M14 13V8.5C14 7 15 7 15 5a3 3 0 0 0-6 0c0 2 1 2 1 3.5V13"/>',
  week: '<rect x="3" y="4" width="18" height="18" rx="2"/><path d="M16 2v4M8 2v4M3 10h18"/><path d="M8 14h8M8 18h5"/>',
  apps: '<rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/>',
  bellr: '<path d="M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9"/><path d="M10.3 21a1.94 1.94 0 0 0 3.4 0"/>',
  up: '<path d="m18 15-6-6-6 6"/>',
  gear2: '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68 1.65 1.65 0 0 0 10 3.17V3a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 1 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/>',
});
const NZ_VIEWS = {nazorat: ["Nazorat markazi", "radar"], imzo: ["Imzo navbati", "stamp"], haftalik: ["Haftalik hisobot", "week"], barcha: ["Barcha bo'limlar", "apps"]};
const NZ_AREA_IC = {ijro: "tasks", oquv: "monitor", talabalar: "users", moliya: "money", kadrlar: "idcard", hujjat: "scroll"};
const nzApi = (p, body) => J(p, body === undefined ? {} : {method: "POST", body: JSON.stringify(body)});
const nzDays = n => n == null ? "" : n === 0 ? "bugun" : `${n} kun`;
const nzWho = p => !p ? "—" : (p.name && p.name !== p.position ? `${esc(p.position)} — <b>${esc(p.name)}</b>` : `<b>${esc(p.position || p.name)}</b>`);

/* ---------- menyu bandlari va bo'limlar (bir marta) ---------- */
(function () {
  const nav = document.getElementById("nav"), main = document.querySelector("#app main");
  if (!nav || !main) return;
  const first = nav.querySelector('a[data-v="panel"]');
  Object.entries(NZ_VIEWS).forEach(([v, [t, ic]]) => {
    if (!nav.querySelector(`a[data-v="${v}"]`)) {
      const a = document.createElement("a"); a.href = "#"; a.dataset.v = v; a.dataset.i = ic; a.className = "hidden";
      a.innerHTML = `${ico(ic)}${esc(t)}`;
      a.onclick = e => { e.preventDefault(); go(v); };
      nav.insertBefore(a, first);
    }
    if (!document.getElementById("v-" + v)) { const s = document.createElement("section"); s.id = "v-" + v; s.className = "view hidden"; main.appendChild(s); }
  });
})();

/* ---------- menyu: rektor — 5 band, prorektor — +2 band ---------- */
function nzMenuApply() {
  const M = NZS.meta && NZS.meta.menu, nav = document.getElementById("nav");
  const mine = Object.keys(NZ_VIEWS);
  mine.forEach(v => nav.querySelector(`a[data-v="${v}"]`)?.classList.add("hidden"));
  NZS.all = [];
  if (!M || !M.items || !M.items.length || (typeof modOn === "function" && !modOn("nazorat"))) return;
  if (M.lean) {
    /* ixcham menyu: ko'rinib turgan bandlar «Barcha bo'limlar» sahifasiga o'tadi (bo'limlar kaliti va ruxsat bo'yicha allaqachon filtrlangan) */
    NZS.all = [...nav.querySelectorAll("a[data-v]")].filter(a => !mine.includes(a.dataset.v) && !a.classList.contains("hidden") && !M.items.includes(a.dataset.v))
      .map(a => ({v: a.dataset.v, i: a.dataset.i, t: a.dataset.lbl0 || a.dataset.lbl || a.textContent.replace(/\d+$/, "").trim()}));
    nav.querySelectorAll("a[data-v]").forEach(a => { if (!mine.includes(a.dataset.v)) a.classList.toggle("hidden", !M.items.includes(a.dataset.v)); });
  }
  const anchor = nav.querySelector("a[data-v]:not(.hidden)") || nav.firstChild;
  M.items.forEach(v => {
    const a = nav.querySelector(`a[data-v="${v}"]`); if (!a) return;
    a.classList.remove("hidden");
  });
  /* tartib: server bergan tartibda, menyuning boshida */
  const head = [...M.items].map(v => nav.querySelector(`a[data-v="${v}"]`)).filter(Boolean);
  head.reverse().forEach(a => nav.insertBefore(a, nav.querySelector("a[data-v]")));
  void anchor;
}
async function nzLoadMeta() {
  try { const r = await fetch("/api/nazorat/meta", {credentials: "same-origin"}); NZS.meta = r.ok ? await r.json() : null; } catch (e) { NZS.meta = null; }
}
async function nzBadge() {
  const a = document.querySelector('#nav a[data-v="imzo"]');
  if (!a || a.classList.contains("hidden")) return;
  try {
    const r = await fetch("/api/nazorat/imzo", {credentials: "same-origin"}); if (!r.ok) return;
    const d = await r.json(); a.querySelector(".nb")?.remove();
    if (d.count) a.insertAdjacentHTML("beforeend", `<span class="nb" title="Qaroringizni kutayotgan hujjatlar" aria-label="${d.count} ta hujjat">${d.count}</span>`);
  } catch (e) {}
}

/* ---------- modal ---------- */
function nzModal(title, html, onOk, okText = "Saqlash") {
  const bg = document.createElement("div"); bg.className = "nz-modal-bg";
  bg.innerHTML = `<div class="nz-modal" role="dialog" aria-modal="true" aria-label="${esc(title)}"><h3>${esc(title)}</h3>${html}
    <div class="row-actions nz-macts"><button type="button" class="btn ghost" data-x>${onOk ? "Bekor qilish" : "Yopish"}</button>${onOk ? `<button type="button" class="btn primary" data-ok>${esc(okText)}</button>` : ""}</div></div>`;
  document.body.appendChild(bg);
  const opener = document.activeElement, close = () => { bg.remove(); opener?.focus?.({preventScroll: true}); };
  bg.addEventListener("mousedown", e => { if (e.target === bg) close(); });
  bg.addEventListener("click", e => { if (e.target.closest("[data-x]")) close(); });
  bg.addEventListener("keydown", e => { if (e.key === "Escape") close(); });
  const ok = bg.querySelector("[data-ok]");
  if (ok) ok.onclick = async () => { ok.disabled = true; try { if (await onOk(bg)) close(); } catch (e) { if (!["auth", "denied"].includes(e?.message)) toast(nzErr(e)); } finally { if (ok.isConnected) ok.disabled = false; } };
  setTimeout(() => bg.querySelector("input,select,textarea,button[data-ok]")?.focus(), 30);
  return bg;
}
function nzErr(e) { try { const j = JSON.parse(e.message); return typeof j.detail === "string" ? j.detail : "Xatolik"; } catch (x) { return "Xatolik yuz berdi"; } }

/* ---------- Nazorat markazi ---------- */
async function renderNazorat() {
  const v = $("#v-nazorat");
  if (!v.innerHTML.trim()) v.innerHTML = `<div class="nz-skel card">Yuklanmoqda…</div>`;
  const d = await J("/api/nazorat");
  NZS.data = d;
  const c = d.counts, rek = d.role === "rektor";
  const areas = d.areas.map(a => nzArea(a, rek)).join("");
  v.innerHTML = `<div class="head nz-head"><div><h2>Nazorat markazi</h2>
      <div class="muted">${esc(d.scope)} · faqat istisnolar — har bir qizil bandning egasi bor</div></div>
      <div class="row-actions">${d.can_rules ? `<button class="btn sm" id="nzRules">${ico("gear2", 15)}Qoidalar</button>` : ""}<button class="btn sm" id="nzRef">${ico("refresh", 15)}Yangilash</button></div></div>
    <div class="nz-sum" role="list">
      <div class="nz-s ${c.red ? "bad" : "ok"}" role="listitem"><b>${c.red}</b><span>${rek ? "Sizgacha yetib kelgan" : "Sizga yetib kelgan"}</span></div>
      <div class="nz-s ${c.lower ? "warn" : ""}" role="listitem"><b>${c.lower}</b><span>Rahbarlar hal qilmoqda</span></div>
      <button class="nz-s link" id="nzSign" role="listitem"><b>${d.sign_count}</b><span>Imzo navbatida →</span></button>
      ${c.acked || c.snoozed ? `<div class="nz-s" role="listitem"><b>${c.acked + c.snoozed}</b><span>Ko'rilgan / muddat berilgan</span></div>` : ""}
    </div>
    <div class="nz-areas">${areas || `<div class="card nz-green">${ico("check", 18)} Kuzatiladigan soha yo'q</div>`}</div>
    <p class="tiny muted nz-foot">Eskalatsiya: istisno ${d.rules.owner_days} kun egasida, ${d.rules.head_days} kun rahbarida, keyin rektorga yetadi. Topshiriq — muddatdan ${d.rules.task_overdue_days} kun o'tgach, talaba — ${d.rules.student_inactive_days} kun faolsiz bo'lsa.</p>`;
  $("#nzRef").onclick = e => busy(e.currentTarget, renderNazorat);
  $("#nzSign").onclick = () => go("imzo");
  if ($("#nzRules")) $("#nzRules").onclick = nzRulesModal;
  v.querySelectorAll("[data-lower]").forEach(b => b.onclick = () => { NZS.showLower[b.dataset.lower] = !NZS.showLower[b.dataset.lower]; renderNazorat(); });
  v.querySelectorAll("[data-act]").forEach(b => b.onclick = () => nzAct(b, b.dataset.act, b.dataset.key));
  v.querySelectorAll("[data-open]").forEach(b => b.onclick = () => { const it = nzFind(b.dataset.open); if (it && it.link && typeof XT !== "undefined") XT.openLink(it.link); });
  if (NZS.focus) {
    const el = v.querySelector(`[data-item="${CSS.escape(NZS.focus)}"]`); NZS.focus = null;
    if (el) { el.scrollIntoView({block: "center"}); el.classList.add("nz-flash"); setTimeout(() => el.classList.remove("nz-flash"), 2400); }
  }
}
function nzFind(key) { for (const a of (NZS.data?.areas || [])) for (const it of [...a.items, ...a.lower]) if (it.key === key) return it; return null; }
function nzArea(a, rek) {
  const ic = ico(NZ_AREA_IC[a.key] || a.icon, 18);
  if (a.status === "green")
    return `<div class="card nz-area nz-green" data-area="${a.key}">${ic}<b>${esc(a.title)}</b><span class="nz-ok">${ico("check", 15)}Hammasi joyida</span></div>`;
  const open = !!NZS.showLower[a.key];
  const lowerBtn = a.lower.length ? `<button class="btn sm ghost nz-lbtn" data-lower="${a.key}" aria-expanded="${open}">${open ? "Yig'ish" : `Rahbarlar hal qilmoqda: ${a.lower.length} ta`}</button>` : "";
  if (a.status === "amber" && !open)
    return `<div class="card nz-area nz-amber" data-area="${a.key}">${ic}<b>${esc(a.title)}</b><span class="nz-am">${rek ? "Sizgacha yetib kelmagan" : "Hali sizgacha yetmagan"}</span>${lowerBtn}</div>`;
  return `<div class="card nz-area nz-red${a.status === "amber" ? " nz-amber-open" : ""}" data-area="${a.key}">
    <div class="nz-ah">${ic}<b>${esc(a.title)}</b>${a.items.length ? `<span class="tag high">${a.items.length} ta qizil</span>` : ""}${lowerBtn}</div>
    ${a.items.map(it => nzRow(it, true)).join("")}
    ${open ? `<div class="nz-lower">${a.lower.map(it => nzRow(it, false)).join("")}</div>` : ""}</div>`;
}
function nzRow(it, red) {
  const st = it.stage === 2 ? "Rektorda" : it.stage === 1 ? `Rahbarida${it.head ? ": " + esc(it.head.name) : ""}` : "Egasida";
  return `<div class="nz-item ${red ? "red" : "low"}" data-item="${esc(it.key)}">
    <div class="nz-it"><b>${esc(it.title)}</b><span class="nz-why">${ico("alert", 14)}${esc(it.why)}</span></div>
    <div class="nz-meta">
      <span><i>Egasi</i>${nzWho(it.owner)}</span>
      <span><i>Qachondan</i>${it.since ? `${dmy(it.since)} · ${nzDays(it.age_days)}` : "—"}</span>
      <span><i>Muddat</i>${it.deadline ? dmy(it.deadline) : "belgilanmagan"}</span>
      <span><i>Bosqich</i><span class="nz-st s${it.stage}">${st}</span></span>
      ${it.src ? `<span><i>Manba</i>${esc(it.src)}</span>` : ""}
    </div>
    <div class="row-actions nz-acts">
      <button class="btn sm" data-act="eslatish" data-key="${esc(it.key)}">${ico("bellr", 15)}Eslatish</button>
      <button class="btn sm" data-act="muddat" data-key="${esc(it.key)}">${ico("calendar", 15)}Muddat berish</button>
      <button class="btn sm" data-act="tayinlash" data-key="${esc(it.key)}">${ico("up", 15)}Qayta tayinlash</button>
      <button class="btn sm ghost" data-act="korildi" data-key="${esc(it.key)}">${ico("eye", 15)}Ko'rdim</button>
      ${it.link ? `<button class="btn sm ghost" data-open="${esc(it.key)}">Ochish →</button>` : ""}
    </div></div>`;
}
async function nzAct(btn, act, key) {
  const it = nzFind(key); if (!it) return;
  const post = body => nzApi("/api/nazorat/act", {key, action: act, ...body});
  if (act === "korildi") return busy(btn, async () => { await post({}); toast("Ko'rildi — holati o'zgarmaguncha yashirildi"); renderNazorat(); });
  if (act === "eslatish")
    return nzModal("Egasiga eslatish", `<p class="nz-mp">${nzWho(it.owner)}<br><span class="muted tiny">${esc(it.title)}</span></p>
      <label class="nz-f">Qo'shimcha izoh (ixtiyoriy)<textarea id="nzNote" rows="3" maxlength="1000" placeholder="Masalan: juma kuni natija kerak"></textarea></label>
      <p class="tiny muted">Eslatma egasining bildirishnomalariga va topshiriq tarixiga yoziladi${it.task_id ? "" : " (topshiriq bo'lmasa — «Nazorat» topshirig'i yaratiladi)"}.</p>`,
      async bg => { const r = await post({note: bg.querySelector("#nzNote").value}); toast(`Eslatma yuborildi: ${r.to ? r.to.name : "egasiga"}`); renderNazorat(); return true; }, "Eslatish");
  if (act === "muddat") {
    const t = new Date(ME.today + "T12:00:00"); t.setDate(t.getDate() + 3);
    return nzModal("Yangi muddat berish", `<p class="nz-mp">${esc(it.title)}</p>
      <label class="nz-f">Yangi muddat<input type="date" id="nzDue" min="${ME.today}" value="${t.toISOString().slice(0, 10)}"></label>
      <label class="nz-f">Izoh (majburiy)<textarea id="nzNote" rows="3" maxlength="1000" placeholder="Nega muddat berilmoqda, nima kutilmoqda"></textarea></label>`,
      async bg => { const r = await post({due: bg.querySelector("#nzDue").value, note: bg.querySelector("#nzNote").value}); toast(`Yangi muddat: ${dmy(r.due)}`); renderNazorat(); return true; }, "Saqlash");
  }
  if (act === "tayinlash") {
    const d = await J(`/api/nazorat/item?key=${encodeURIComponent(key)}`), T = d.targets;
    const opts = T.units.map(u => `<option value="${esc(u.key)}">${esc(u.name)}</option>`).join("");
    return nzModal("Qayta tayinlash / yuqoriga ko'tarish", `<p class="nz-mp">${esc(it.title)}<br><span class="tiny muted">Hozirgi egasi: ${nzWho(it.owner)}</span></p>
      ${T.head ? `<label class="nz-r"><input type="radio" name="nzTo" value="head" checked> Rahbariga ko'tarish: ${nzWho(T.head)}</label>` : ""}
      <label class="nz-r"><input type="radio" name="nzTo" value="unit" ${T.head ? "" : "checked"}> Boshqa bo'limga:</label>
      <select id="nzUnit" class="nz-sel" aria-label="Bo'lim">${opts}</select>
      <label class="nz-f">Izoh (ixtiyoriy)<textarea id="nzNote" rows="2" maxlength="1000"></textarea></label>
      <p class="tiny muted">Topshiriq yangi mas'ulga o'tadi, eskalatsiya soati qaytadan boshlanadi.</p>`,
      async bg => {
        const head = bg.querySelector('input[name="nzTo"]:checked')?.value === "head";
        const r = await post(head ? {to_head: true, note: bg.querySelector("#nzNote").value} : {unit: bg.querySelector("#nzUnit").value, note: bg.querySelector("#nzNote").value});
        toast(`Tayinlandi: ${r.to}`); renderNazorat(); return true;
      }, "Tayinlash");
  }
}
async function nzRulesModal() {
  const d = await J("/api/nazorat/rules");
  nzModal("Eskalatsiya qoidalari", `<div class="nz-rules">${d.rules.map(r => `<label class="nz-f"><span>${esc(r.label)}</span>
      <input type="number" data-rule="${esc(r.key)}" min="${r.min}" max="${r.max}" value="${r.value}" ${d.can_edit ? "" : "disabled"}><small class="muted">standart: ${r.default}</small></label>`).join("")}</div>`,
    d.can_edit ? async bg => {
      const rules = {}; bg.querySelectorAll("[data-rule]").forEach(i => rules[i.dataset.rule] = +i.value);
      await nzApi("/api/nazorat/rules", {rules}); toast("Qoidalar saqlandi"); renderNazorat(); return true;
    } : null, "Saqlash");
}

/* ---------- Imzo navbati ---------- */
async function renderImzo() {
  const v = $("#v-imzo");
  const d = await J("/api/nazorat/imzo");
  v.innerHTML = `<div class="head"><div><h2>Imzo navbati</h2><div class="muted">Qaroringizni kutayotgan hujjatlar — eng eskisi birinchi</div></div>
      <span class="tag ${d.count ? "mid" : "low"}">${d.count} ta</span></div>
    ${d.items.length ? `<div class="card nz-sign">${d.items.map((it, i) => `<div class="nz-srow" data-row="${i}">
        <div class="nz-it"><b>${esc(it.title.replace(/^(Imzo kutilmoqda|Kelishuv kutilmoqda): /, ""))}</b><span class="muted tiny">${esc(it.sub || "")}</span></div>
        <span class="nz-age ${it.age_days >= 3 ? "old" : ""}">${it.age_days == null ? "—" : nzDays(it.age_days)}</span>
        <div class="row-actions">${it.actions.approve ? `<button class="btn sm primary" data-ok="${i}">${ico("check", 15)}${esc(it.actions.approve)}</button>` : ""}
          ${it.actions.return ? `<button class="btn sm" data-ret="${i}">Izoh bilan qaytarish</button>` : ""}
          <button class="btn sm ghost" data-go="${i}">Ochish →</button></div></div>`).join("")}</div>`
      : `<div class="card nz-green">${ico("check", 18)}<b>Imzo navbati bo'sh</b><span class="nz-ok">Hammasi joyida</span></div>`}`;
  const at = i => d.items[+i];
  v.querySelectorAll("[data-go]").forEach(b => b.onclick = () => { const it = at(b.dataset.go); if (typeof XT !== "undefined") XT.openLink(it.link); });
  v.querySelectorAll("[data-ok]").forEach(b => b.onclick = () => {
    const it = at(b.dataset.ok);
    if (!arm(b, `Ha, ${it.actions.approve.toLowerCase()}`)) return;
    busy(b, async () => {
      try { const r = await nzApi(`/api/nazorat/imzo/${it.kind}/${it.ref}`, {decision: "approve"}); toast(`Buyruq ${r.label}`); }
      catch (e) { if (!["auth", "denied"].includes(e?.message)) toast(nzErr(e)); }
      renderImzo(); nzBadge();
    });
  });
  v.querySelectorAll("[data-ret]").forEach(b => b.onclick = () => {
    const it = at(b.dataset.ret);
    nzModal("Izoh bilan qaytarish", `<p class="nz-mp">${esc(it.title)}</p><label class="nz-f">Qaytarish sababi<textarea id="nzNote" rows="3" maxlength="500"></textarea></label>`,
      async bg => { await nzApi(`/api/nazorat/imzo/${it.kind}/${it.ref}`, {decision: "return", note: bg.querySelector("#nzNote").value}); toast("Hujjat izoh bilan qaytarildi"); renderImzo(); nzBadge(); return true; }, "Qaytarish");
  });
}

/* ---------- Haftalik hisobot ---------- */
async function renderHaftalik(week) {
  const v = $("#v-haftalik");
  const d = await J("/api/nazorat/hafta");
  const b = week ? await J(`/api/nazorat/hafta/${encodeURIComponent(week)}`) : d.latest;
  const nxt = d.next ? `${dmy(d.next)} 08:00` : "dushanba 08:00";
  const tg = b && b.telegram && b.telegram.length ? b.telegram.map(t => t.ok ? "Telegram'ga yuborildi" : t.note).join(" · ")
    : d.linked ? (d.telegram ? "Telegram: yuborilmagan" : "Telegram: bot tokeni o'rnatilmagan") : "Telegram: botga ulanmagan";
  v.innerHTML = `<div class="head"><div><h2>Haftalik hisobot</h2><div class="muted">Har dushanba 08:00 · keyingisi: ${esc(nxt)}</div></div>
      <div class="row-actions"><button class="btn sm" id="nzBrief">${ico("refresh", 15)}Hozir tayyorlash</button></div></div>
    ${b ? `<div class="card nz-brief"><div class="nz-bh"><b>${esc(b.week)}</b><span class="tag ${b.source === "ai" ? "mid" : "gray"}">${b.source === "ai" ? "AI qisqartirgan (faqat jamlangan sonlar)" : "Qoidaviy matn"}</span>
        <span class="muted tiny">${esc(whenTxt ? whenTxt(b.created_at) : b.created_at)} · ${esc(tg)}</span></div>
      <ul class="nz-lines">${b.lines.map(x => `<li>${esc(x)}</li>`).join("")}</ul>
      <h3>Kerakli qarorlar</h3><ol class="nz-dec">${b.decisions.map(x => `<li>${esc(x)}</li>`).join("")}</ol></div>`
      : `<div class="card nz-green">${ico("week", 18)}<b>Hali hisobot yo'q</b><span class="muted">Birinchi hisobot ${esc(nxt)} da tayyorlanadi yoki «Hozir tayyorlash»ni bosing.</span></div>`}
    ${d.history.length > 1 ? `<div class="card nz-hist"><h3>Oldingi haftalar</h3><div class="row-actions">${d.history.map(h => `<button class="btn sm ${b && h.week === b.week ? "primary" : "ghost"}" data-week="${esc(h.week)}">${esc(h.week)}</button>`).join("")}</div></div>` : ""}`;
  $("#nzBrief").onclick = e => busy(e.currentTarget, async () => { await nzApi("/api/nazorat/hafta", {}); toast("Hisobot yangilandi"); renderHaftalik(); });
  v.querySelectorAll("[data-week]").forEach(x => x.onclick = () => renderHaftalik(x.dataset.week));
}

/* ---------- Barcha bo'limlar ---------- */
function renderBarcha() {
  const v = $("#v-barcha");
  const L = NZS.all.length ? NZS.all : [...document.querySelectorAll("#nav a[data-v]:not(.hidden)")].filter(a => !(a.dataset.v in NZ_VIEWS)).map(a => ({v: a.dataset.v, i: a.dataset.i, t: a.dataset.lbl0 || a.textContent.trim()}));
  v.innerHTML = `<div class="head"><div><h2>Barcha bo'limlar</h2><div class="muted">Kundalik ish — xodimlarda. Kerak bo'lsa, istalgan bo'limni shu yerdan oching.</div></div></div>
    <div class="nz-grid">${L.map(x => `<button class="card nz-tile" data-v="${esc(x.v)}">${ico(x.i, 20)}<span>${esc(x.t)}</span></button>`).join("")}</div>`;
  v.querySelectorAll("[data-v]").forEach(b => b.onclick = () => go(b.dataset.v));
}

/* ---------- o'ramlar: boot (meta), navApply (menyu), badges (imzo soni), go (sahifalar), XT.openLink (fokus) ---------- */
(function () {
  /* app.js boot() fayl yuklanishida chaqiriladi (bu fayldan oldin) — shuning uchun meta navApply() da (har kirishda bir marta) yuklanadi */
  if (typeof navApply === "function" && !navApply._nz) {
    const prev = navApply;
    navApply = function (...a) {
      const r = prev.apply(this, a);
      const who = typeof ME !== "undefined" && ME ? ME.id : null;
      if (NZS.metaFor !== who) {
        NZS.metaFor = who; NZS.meta = null; NZS.metaReady = false; NZS.homeOnce = true;
        NZS.metaP = nzLoadMeta().then(() => {
          NZS.metaReady = true; if (NZS.metaFor !== who) return;
          nzMenuApply(); if (typeof navGroup === "function") navGroup(ME.role_key); nzBadge();
          /* boot() bu fayl yuklanmasidan oldin panelni ochib bo'lgan bo'lsa — bosh sahifaga o'tish */
          const h = NZS.meta?.menu?.home;
          if (NZS.homeOnce && h && !document.getElementById("v-panel")?.classList.contains("hidden")) { NZS.homeOnce = false; go(h); }
        });
      } else { nzMenuApply(); if (typeof navGroup === "function" && ME) navGroup(ME.role_key); }
      return r;
    };
    navApply._nz = true;
  }
  if (typeof badges === "function" && !badges._nz) {
    const prev = badges;
    badges = async function (...a) { const r = await prev.apply(this, a); nzBadge(); return r; };
    badges._nz = true;
  }
  if (typeof go === "function" && !go._nz) {
    const prev = go;
    go = function (v, opts) {
      /* rektorning bosh sahifasi — Nazorat markazi (faqat kirgandan keyingi birinchi go("panel")) */
      if (v === "panel" && NZS.homeOnce) {
        if (!NZS.metaReady && NZS.metaP) { NZS.metaP.then(() => go(v, opts)); return; }   /* meta kelguncha panel chizilmaydi (rektor uchun keraksiz so'rovlar) */
        NZS.homeOnce = false; const h = NZS.meta?.menu?.home; if (h && (typeof modOn !== "function" || modOn("nazorat"))) v = h;
      }
      const r = prev(v, opts);
      const bar = document.querySelector('#nav a[data-v="barcha"]');
      if (bar && !bar.classList.contains("hidden") && NZS.all.some(x => x.v === v)) bar.classList.add("on");
      const fn = {nazorat: renderNazorat, imzo: renderImzo, haftalik: renderHaftalik, barcha: renderBarcha}[v];
      if (fn) Promise.resolve().then(() => fn()).catch(e => { if (e?.message === "auth") return; $("#v-" + v).innerHTML = e?.message === "denied" ? locked(NZ_VIEWS[v][0]) : errCard(v); });
      return r;
    };
    go._nz = true;
  }
  if (typeof XT !== "undefined" && XT.openLink && !XT.openLink._nz) {
    const prev = XT.openLink;
    XT.openLink = function (l) { if (l && l.view === "nazorat") NZS.focus = l.item || null; return prev.call(this, l); };
    XT.openLink._nz = true;
  }
  if (typeof showLogin === "function" && !showLogin._nz) {
    const prev = showLogin;
    showLogin = function (...a) { NZS.meta = null; NZS.metaFor = undefined; NZS.data = null; NZS.all = []; NZS.showLower = {}; return prev.apply(this, a); };
    showLogin._nz = true;
  }
})();
/* app.js boot() bu fayl yuklanguncha tugagan bo'lsa (sekin tarmoq) — menyu va bosh sahifa shu yerda qo'llanadi */
if (typeof ME !== "undefined" && ME && typeof navApply === "function" && NZS.metaFor !== ME.id) navApply();
