"use strict";
const $ = s => document.querySelector(s);
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const fmt = n => typeof n === "number" ? n.toLocaleString("ru-RU").replace(/,/g, " ") : n;
const mln = x => Math.abs(x) >= 1e9 ? (x/1e9).toFixed(2)+" mlrd" : (x/1e6).toFixed(1)+" mln";
let ME = null, DASH = null, selUser = null;

async function api(path, opts = {}) {
  const r = await fetch(path, {credentials: "same-origin", headers: {"Content-Type": "application/json"}, ...opts});
  if (r.status === 401) { showLogin(); throw new Error("auth"); }
  if (r.status === 403) { const j = await r.json(); toast(j.message || "Ruxsat yo'q"); throw new Error("denied"); }
  if (!r.ok) throw new Error(await r.text());
  return r;
}
const J = async (p, o) => (await api(p, o)).json();
const dmy = d => { const t = typeof d === "string" ? new Date(d.length <= 10 ? d + "T00:00:00" : d) : d; return isNaN(t) ? esc(d) : `${String(t.getDate()).padStart(2, "0")}.${String(t.getMonth() + 1).padStart(2, "0")}.${t.getFullYear()}`; };
/* tugma: bosilganda o'chadi, ish tugagach qayta yoqiladi — ikki marta yuborishning oldi olinadi */
async function busy(btn, fn, label = "…") {
  if (!btn || btn.disabled) return;
  const old = btn.innerHTML; btn.disabled = true; btn.innerHTML = label;
  try { return await fn(); } catch (e) { if (!["auth", "denied"].includes(e?.message)) toast("Xatolik yuz berdi — qayta urinib ko'ring"); } finally { if (btn.isConnected) { btn.disabled = false; btn.innerHTML = old; } }
}
const errCard = v => `<div class="card locked"><div style="font-size:22px">⚠️</div><b>Ma'lumotni yuklab bo'lmadi</b><span class="tiny">Server bilan aloqa uzildi yoki ichki xatolik</span><button class="btn sm" style="margin-top:8px" onclick="go('${v}')">↻ Qayta urinish</button></div>`;
function toast(t) { const el = $("#toast"); el.textContent = t; el.classList.remove("hidden"); clearTimeout(toast.t); toast.t = setTimeout(() => el.classList.add("hidden"), 4200); }

/* ---------- ikonkalar (lucide uslubida, inline SVG) ---------- */
const ICONS = {
  dashboard: '<rect x="3" y="3" width="7" height="9" rx="1.5"/><rect x="14" y="3" width="7" height="5" rx="1.5"/><rect x="14" y="12" width="7" height="9" rx="1.5"/><rect x="3" y="16" width="7" height="5" rx="1.5"/>',
  chat: '<path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/><path d="M8 9h8M8 13h5"/>',
  tasks: '<rect x="8" y="2" width="8" height="4" rx="1"/><path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2"/><path d="m9 14 2 2 4-4"/>',
  report: '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6"/><path d="M8 13h8M8 17h5"/>',
  folder: '<path d="M4 20h16a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.9a2 2 0 0 1-1.69-.9L9.6 3.9A2 2 0 0 0 7.93 3H4a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2z"/>',
  languages: '<path d="m5 8 6 6"/><path d="m4 14 6-6 2-3"/><path d="M2 5h12"/><path d="M7 2h1"/><path d="m22 22-5-10-5 10"/><path d="M14 18h6"/>',
  wrench: '<path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"/>',
  camera: '<path d="m22 8-6 4 6 4V8z"/><rect x="2" y="6" width="14" height="12" rx="2"/>',
  shield: '<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/><path d="m9 12 2 2 4-4"/>',
  history: '<path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/><path d="M3 3v5h5"/><path d="M12 7v5l4 2"/>',
  server: '<rect x="2" y="2" width="20" height="8" rx="2"/><rect x="2" y="14" width="20" height="8" rx="2"/><path d="M6 6h.01M6 18h.01"/>',
  arrow: '<path d="M5 12h14"/><path d="m12 5 7 7-7 7"/>',
  info: '<circle cx="12" cy="12" r="10"/><path d="M12 16v-4M12 8h.01"/>',
  switch: '<path d="m16 3 4 4-4 4"/><path d="M20 7H4"/><path d="m8 21-4-4 4-4"/><path d="M4 17h16"/>',
  menu: '<path d="M4 6h16M4 12h16M4 18h16"/>',
  sun: '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M6.34 17.66l-1.41 1.41M19.07 4.93l-1.41 1.41"/>',
  moon: '<path d="M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9z"/>',
  monitor: '<rect x="2" y="3" width="20" height="14" rx="2"/><path d="M8 21h8M12 17v4"/>',
  send: '<path d="m22 2-7 20-4-9-9-4z"/><path d="M22 2 11 13"/>',
  check: '<path d="M20 6 9 17l-5-5"/>',
  calendar: '<rect x="3" y="4" width="18" height="18" rx="2"/><path d="M16 2v4M8 2v4M3 10h18"/>',
};
ICONS.users = '<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/>';
const ico = (n, sz = 18) => `<svg class="i" viewBox="0 0 24 24" width="${sz}" height="${sz}" aria-hidden="true">${ICONS[n] || ""}</svg>`;
function hydrateIcons(root = document) {
  root.querySelectorAll("[data-ico]").forEach(el => { if (!el.dataset.done) { el.innerHTML = ico(el.dataset.ico); el.dataset.done = 1; } });
  root.querySelectorAll("#nav a[data-i]").forEach(a => { if (!a.querySelector("svg")) a.insertAdjacentHTML("afterbegin", ico(a.dataset.i)); });
}
hydrateIcons();

/* ---------- mavzu (yorug' / qorong'i / tizim) ---------- */
const THEMES = ["light", "dark", "auto"], THEME_ICO = {light: "sun", dark: "moon", auto: "monitor"}, THEME_TXT = {light: "Yorug' rejim", dark: "Qorong'i rejim", auto: "Tizim bo'yicha"};
function setTheme(t) {
  document.documentElement.dataset.theme = t;
  try { localStorage.setItem("jarvis-theme", t); } catch (e) {}
  const b = $("#themeBtn"); b.innerHTML = ico(THEME_ICO[t]); b.title = THEME_TXT[t] + " — almashtirish";
}
$("#themeBtn").onclick = () => { const t = THEMES[(THEMES.indexOf(document.documentElement.dataset.theme) + 1) % 3]; setTheme(t); toast(THEME_TXT[t]); };
setTheme(document.documentElement.dataset.theme || "light");

/* ---------- kirish ---------- */
const LVL_TABS = {1: "Rahbariyat", 2: "Prorektorlar", 3: "Bo'limlar", 4: "Fakultet"};
let USERS = [], LVL = 1;
const initials = t => { const w = String(t).replace(/[^\p{L}\s]/gu, "").split(/\s+/).filter(Boolean); return ((w[0] || "")[0] || "").toUpperCase() + ((w[1] || "")[0] || "").toUpperCase(); };
const personOf = u => u.name.includes(":") ? u.name.split(":")[1].trim() : "Demo foydalanuvchi";
async function showLogin() {
  $("#app").classList.add("hidden"); $("#login").classList.remove("hidden");
  USERS = await (await fetch("/api/users")).json();
  if (!selUser) selUser = (USERS.find(u => u.level === 1 && /^Rektor$/i.test(u.role)) || USERS[0]).id;
  LVL = (USERS.find(u => u.id === selUser) || {level: 1}).level;
  $("#lvlTabs").innerHTML = [1, 2, 3, 4].map(l => `<button type="button" role="tab" data-l="${l}">${LVL_TABS[l]}</button>`).join("");
  $("#lvlTabs").querySelectorAll("button").forEach(b => b.onclick = () => { LVL = +b.dataset.l; drawRoles(); });
  drawRoles(); setOtp($("#pin").value);
  $("#loginBtn").disabled = !selUser;
}
function drawRoles() {
  $("#lvlTabs").querySelectorAll("button").forEach(b => { b.classList.toggle("on", +b.dataset.l === LVL); b.setAttribute("aria-selected", +b.dataset.l === LVL); });
  $("#roleList").innerHTML = USERS.filter(u => u.level === LVL).map(u => `<div class="role-row ${u.id === selUser ? "sel" : ""}" data-id="${u.id}" tabindex="0" role="option" aria-selected="${u.id === selUser}">
    <span class="avatar l${u.level}">${esc(initials(u.role))}</span><div><b>${esc(u.role)}</b><small>${esc(personOf(u))}</small></div><span class="chk">${u.id === selUser ? ico("check", 13) : ""}</span></div>`).join("");
  $("#roleList").querySelectorAll(".role-row").forEach(el => {
    el.onclick = () => { selUser = +el.dataset.id; $("#loginBtn").disabled = false; drawRoles(); };
    el.ondblclick = () => { selUser = +el.dataset.id; doLogin(); };
    el.onkeydown = e => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); el.click(); $("#loginBtn").focus(); } };
  });
}
const OTP = () => [...document.querySelectorAll("#otp input")];
function setOtp(v) { OTP().forEach((x, i) => x.value = (v || "")[i] || ""); $("#pin").value = v || ""; }
OTP().forEach((inp, i, all) => {
  inp.oninput = () => {
    const d = inp.value.replace(/\D/g, "");
    if (d.length > 1) { setOtp((OTP().map(x => x.value).join("").slice(0, i) + d).slice(0, 4)); all[Math.min(3, i + d.length)].focus(); }
    else { inp.value = d; if (d && i < 3) all[i + 1].focus(); }
    $("#pin").value = OTP().map(x => x.value).join("");
  };
  inp.onkeydown = e => {
    if (e.key === "Backspace" && !inp.value && i > 0) all[i - 1].focus();
    if (e.key === "Enter") doLogin();
  };
  inp.onfocus = () => inp.select();
});
async function doLogin() {
  if (!selUser || $("#loginBtn").dataset.busy) return;
  const pin = OTP().map(x => x.value).join("");
  if (pin.length < 4) { $("#otp").classList.add("err"); setTimeout(() => $("#otp").classList.remove("err"), 400); return toast("PIN kodni to'liq kiriting"); }
  $("#loginBtn").dataset.busy = 1;
  try {
    const r = await fetch("/api/login", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({user_id: selUser, pin})});
    if (!r.ok) { $("#otp").classList.add("err"); setTimeout(() => $("#otp").classList.remove("err"), 400); setOtp(""); OTP()[0].focus(); return toast("PIN noto'g'ri"); }
    await boot();
  } finally { delete $("#loginBtn").dataset.busy; }
}
$("#loginBtn").onclick = doLogin;
$("#switchBtn").onclick = async () => { await fetch("/api/logout", {method: "POST"}); $("#msgs").innerHTML = ""; $("#app").classList.remove("nav-open"); showLogin(); };

/* ---------- ishga tushirish ---------- */
async function boot() {
  try { ME = await J("/api/me"); } catch { return; }
  $("#login").classList.add("hidden"); $("#app").classList.remove("hidden");
  $("#meName").textContent = ME.role; $("#meScope").textContent = ME.scope;
  const av = $("#meAv"); av.textContent = initials(ME.role); av.className = `avatar l${ME.level}`;
  $("#todayChip").innerHTML = `${ico("calendar", 15)} ${dmy(ME.today)}`;
  /* ruxsati umuman yo'q bo'limlar menyuda ko'rsatilmaydi (ichkaridagi kartalar baribir 🔒 bilan himoyalangan) */
  const NAV_NEED = {service: ["facilities", "requests", "youth"], spaces: ["spaces"], audit: ["audit"], ops: ["ops"], tasks: ["tasks"]};
  /* tor vazifali lavozimlar uchun keraksiz bo'limlar yashiriladi (server baribir ruxsatni tekshiradi) */
  const NAV_HIDE = {call_center: ["chat", "reports", "documents", "docs", "rbac"], tyutor: ["reports", "docs"]};
  document.querySelectorAll("#nav a").forEach(a => { const need = NAV_NEED[a.dataset.v]; a.classList.toggle("hidden", (!!need && !need.some(x => ME.allow.includes(x))) || (NAV_HIDE[ME.role_key] || []).includes(a.dataset.v)); });
  document.querySelectorAll("#nav .nav-h").forEach(h => { let n = h.nextElementSibling, any = false; while (n && n.tagName === "A") { any ||= !n.classList.contains("hidden"); n = n.nextElementSibling; } h.classList.toggle("hidden", !any); });
  status(); badges();
  go("panel");
}
async function status() {
  try {
    const s = await (await fetch("/api/status")).json();
    const d = $("#llmDot"); d.className = "dot " + (s.llm ? "on" : "off");
    $("#aiTxt").textContent = s.llm ? "AI faol" : "AI o'chiq";
    $("#aiChip").title = s.llm ? `Mahalliy AI faol: ${s.model} · ma'lumot institutdan chiqmaydi` : "Mahalliy AI o'chiq — shablon javoblar ishlaydi";
  } catch (e) {}
}
/* menyudagi raqamli belgilar: e'tibor talab qiladigan ishlar */
async function badges() {
  const set = (v, n) => { const a = document.querySelector(`#nav a[data-v="${v}"]`); if (!a) return; a.querySelector(".nb")?.remove(); if (n > 0) a.insertAdjacentHTML("beforeend", `<span class="nb">${n}</span>`); };
  if (ME.allow.includes("tasks")) try { const t = await J("/api/section/tasks"); set("tasks", t.overdue); } catch (e) {}
  try { const r = await J("/api/docs/registry"); set("documents", r.filter(x => x.status === "loyiha").length); } catch (e) {}
  if (ME.allow.includes("ops") && !["rektor", "kengash"].includes(ME.role_key))
    try { const o = await J("/api/ops/summary"), mine = (o.tasks.find(t => t.role === (ME.role_key === "dekan" || ME.role_key === "prorektor_oquv" ? "_" : ME.role_key)) || {}); set("ops", mine.late || 0); } catch (e) {}
  if (ME.allow.some(a => ["facilities", "requests", "youth"].includes(a)))
    try { const o = await J("/api/svc/overview"); set("service", (o.requests?.incidents || []).filter(i => i.status === "ochiq" && !i.notified_at).length + (o.facilities?.overdue || 0)); } catch (e) {}
}
document.querySelectorAll("#nav a").forEach(a => a.onclick = e => { e.preventDefault(); if (a.dataset.v === "tasks") DEC.open = null; go(a.dataset.v); });
$("#menuBtn").onclick = () => $("#app").classList.toggle("nav-open");
$("#scrim").onclick = () => $("#app").classList.remove("nav-open");
function go(v) {
  clearInterval(SPC.timer); if (v !== "tasks") clearInterval(DEC.timer);
  $("#app").classList.remove("nav-open");
  document.querySelectorAll("#nav a").forEach(a => a.classList.toggle("on", a.dataset.v === v));
  const a = document.querySelector(`#nav a[data-v="${v}"]`); $("#crumb").textContent = a ? a.textContent.replace(/\d+$/, "").trim() : "";
  document.querySelectorAll(".view").forEach(s => s.classList.add("hidden"));
  $("#v-" + v).classList.remove("hidden");
  window.scrollTo({top: 0});
  const fn = ({panel: renderPanel, chat: renderChat, tasks: renderTasks, reports: renderReports, docs: renderDocs, documents: renderDocuments, service: renderService, ops: renderOps, spaces: renderSpaces, rbac: renderRbac, audit: renderAudit})[v];
  Promise.resolve().then(fn).catch(e => { if (e?.message === "auth") return; $("#v-" + v).innerHTML = e?.message === "denied" ? locked("Bu bo'lim") : errCard(v); });
}

/* ---------- charts ---------- */
function bars(rows, {label, value, max, fmtv = v => v, alt = false, mark = null}) {
  const m = max ?? Math.max(...rows.map(value), 1);
  return `<div class="bars">` + rows.map(r => {
    const v = value(r), w = Math.max(0, Math.min(100, 100 * v / m));
    return `<div class="row"><span title="${esc(label(r))}">${esc(label(r))}</span><div class="track"><div class="fill ${alt ? "alt" : ""}" style="width:${w}%"></div>${mark != null ? `<div class="mark" style="left:${100*mark/m}%"></div>` : ""}</div><span class="v">${fmtv(v, r)}</span></div>`;
  }).join("") + `</div>`;
}
function spark(vals, w = 520, h = 90) {
  const mx = Math.max(...vals), mn = Math.min(...vals), dx = w / (vals.length - 1);
  const pts = vals.map((v, i) => `${(i*dx).toFixed(1)},${(h - 8 - (h - 16) * (v - mn) / ((mx - mn) || 1)).toFixed(1)}`).join(" ");
  return `<svg viewBox="0 0 ${w} ${h}" width="100%" height="${h}" preserveAspectRatio="none"><polyline fill="none" stroke="var(--bar)" stroke-width="2.5" points="${pts}"/></svg>`;
}
const card = (title, body, extra = "") => `<div class="card"><div class="head" style="margin-bottom:10px"><h3 style="margin:0">${title}</h3>${extra}</div>${body}</div>`;
const locked = (title) => `<div class="card locked"><div style="font-size:22px">🔒</div><b>${esc(title)}</b><span class="tiny">Lavozimingiz uchun ruxsat yo'q</span></div>`;
const tbl = (head, rows) => `<div class="tw"><table><thead><tr>${head.map(h => `<th class="${h.startsWith("#") ? "n" : ""}">${esc(h.replace(/^#/, ""))}</th>`).join("")}</tr></thead><tbody>${rows.length ? rows.map(r => `<tr>${r.map((c, i) => `<td class="${head[i].startsWith("#") ? "n" : ""}">${c}</td>`).join("")}</tr>`).join("") : `<tr><td colspan="${head.length}" class="muted" style="text-align:center;padding:14px">Ma'lumot yo'q</td></tr>`}</tbody></table></div>`;
const delta = d => `<span class="${d < -2 ? "bad" : d > 1 ? "good" : ""}">${d > 0 ? "+" : ""}${d}</span>`;

/* ---------- panel ---------- */
async function renderPanel() {
  const el = $("#v-panel"); el.innerHTML = `<p class="muted">Yuklanmoqda…</p>`;
  DASH = await J("/api/dashboard");
  const P = DASH.panels, L = ME.labels;
  let h = `<div class="head"><div><h2>Assalomu alaykum, ${esc(ME.role)}</h2><span class="muted">${esc(ME.scope)} · ${dmy(ME.today)} · ma'lumot institut serveridan</span></div>
    <button class="btn" onclick="go('chat')">💬 JARVIS'dan so'rash</button></div>`;
  h += `<div class="grid g4">` + DASH.kpis.map(k => `<div class="card kpi ${k.bad ? "bad" : ""}"><div class="l">${esc(k.label)}</div><div class="v">${esc(k.value)}${k.trend ? `<span class="trend ${k.trend < 0 ? "dn" : "up"}">${k.trend > 0 ? "▲" : "▼"} ${Math.abs(k.trend)}</span>` : ""}</div><div class="s">${esc(k.sub)}</div></div>`).join("") + `</div>`;
  if (ME.level <= 2 && ME.role_key !== "kotib" && DASH.panels.tasks) {
    try {
      const L = await J("/api/dec/list"), ds = L.decisions.filter(d => d.status !== "qoralama").slice(0, 3);
      if (ds.length) h += `<div class="card" style="margin-top:14px"><div class="head" style="margin-bottom:6px"><h3 style="margin:0">📌 Majlis qarorlari ijrosi</h3><button class="btn sm" onclick="DEC.open=null;go('tasks')">Barchasi →</button></div>
        <p class="tiny muted" style="margin:0 0 8px">Mas'ul, holat va natija — ijrochi kiritgan topshiriqning o'zidan.</p><div class="dec-list">${ds.map(decRow).join("")}</div></div>`;
    } catch (e) {}
  }
  if (ME.allow.includes("ops")) {
    try {
      const o = await J("/api/ops/summary"), by = {}; o.by_rule.forEach(r => { by[r.rule] = (by[r.rule] || 0) + r.n; });
      const crit = o.by_rule.filter(r => r.level >= 2).reduce((a, r) => a + r.n, 0), late = o.tasks.reduce((a, t) => a + (t.late || 0), 0), open = o.tasks.reduce((a, t) => a + t.n, 0);
      h += `<div class="card" style="margin-top:14px"><div class="head" style="margin-bottom:8px"><h3 style="margin:0">🎓 Talabalar bilan ishlash markazi</h3><button class="btn sm" onclick="OPSV.student=null;go('ops')">Ochish →</button></div>
        <div class="ops-strip" style="margin:0"><span class="chip-s">Kritik/jiddiy holatlar: <b class="bad">${crit}</b></span>${Object.entries(OPS_RULES).map(([k, v]) => by[k] ? `<span class="chip-s">${v}: <b>${by[k]}</b></span>` : "").join("")}
        <span class="chip-s">Ochiq topshiriqlar: <b>${open}</b>${late ? ` · <span class="bad">${late} kechikkan</span>` : ""}</span><span class="chip-s">7 kunda yopildi: <b>${o.closed_7d}</b></span></div>
        ${["rektor", "kengash"].includes(ME.role_key) ? `<p class="tiny muted" style="margin:8px 0 0">🛡 Rahbariyat uchun faqat jamlangan raqamlar — talabalar ro'yxati registrator va tyutorlarda.</p>` : ""}</div>`;
    } catch (e) {}
  }
  if (DASH.alerts.length) {
    const T = {high: "Yuqori", mid: "O'rta", low: "Past"};
    h += `<div class="card" style="margin-top:14px"><h3>⚡ JARVIS ogohlantirishlari <span class="muted tiny">— chorak yakunini kutmasdan</span></h3><div class="alerts">` +
      DASH.alerts.map((a, i) => `<div class="alert${i >= 6 ? " more hidden" : ""}"><span class="tag ${a.level}">${T[a.level]}</span><span><b>${esc(a.area)}:</b> ${esc(a.text)}</span></div>`).join("") +
      (DASH.alerts.length > 6 ? `<button class="btn ghost sm" style="align-self:flex-start" onclick="this.parentNode.querySelectorAll('.more').forEach(x=>x.classList.toggle('hidden'));this.textContent=this.textContent.startsWith('Barcha')?'Yig\'ish':'Barchasini ko\'rsatish (${DASH.alerts.length})'">Barchasini ko'rsatish (${DASH.alerts.length})</button>` : "") + `</div></div>`;
  }
  const cards = [];
  if (P.mygroups) cards.push(card("Mening guruhlarim", tbl(["Guruh", "Fan", "#Talaba", "#O'rt. ball", "#O'tgan sem.", "#Qarzdor (<56)"], P.mygroups.map(g => [esc(g.grp), esc(g.subject), g.n, g.avg_score, (g.prev_score - g.avg_score > 5 ? `<span class="bad">${g.prev_score}</span>` : g.prev_score), g.failing ? `<span class="bad">${g.failing}</span>` : 0]))));
  if (P.academic) {
    const a = P.academic;
    cards.push(card(`O'zlashtirish: ${a.breakdown_by}lar kesimida`, bars(a.breakdown, {label: r => r.name, value: r => r.gpa, max: 100, mark: 71, fmtv: (v, r) => `${v} ${r.delta <= -2 ? "▼" : ""}`}) +
      `<p class="tiny muted">Chiziq — "yaxshi" chegarasi (71 ball). ▼ — o'tgan semestrga nisbatan pasayish.</p>` +
      (a.declining_groups.length ? `<h3 style="margin-top:12px">Keskin pasaygan guruhlar</h3>` + tbl(["Guruh", "Fakultet", "#Kurs", "#Ball", "#O'zgarish", "#Davomat"], a.declining_groups.map(g => [esc(g.name), esc(g.faculty), g.course, g.gpa, delta(g.delta), (g.attendance == null ? "—" : g.attendance + "%")])) : "")));
  } else cards.push(locked(L.academic));
  if (P.risk) {
    const r = P.risk;
    cards.push(card(`Xavf ostidagi talabalar <span class="tag high">${r.count}</span>`, r.students ?
      tbl(["F.I.Sh.", "Guruh", "#Ball", "#Davomat", "#Xavf", "Sabab"], r.students.slice(0, 10).map(s => [esc(s.full_name), esc(s.grp), s.gpa, (s.attendance == null ? "—" : s.attendance + "%"), `<b class="bad">${s.risk}</b>`, `<span class="tiny">${esc(s.reasons)}</span>`])) :
      `<p class="tiny muted">🛡 ${esc(r.note)}</p>` + bars(r.by_group, {label: g => g.group, value: g => g.count, fmtv: v => v + " nafar"})));
  } else cards.push(locked(L.students));
  if (P.contracts) {
    const c = P.contracts;
    cards.push(card("Kontrakt tushumi", bars(c.by_faculty, {label: r => r.name, value: r => r.pct, max: 100, fmtv: v => v + "%"}) +
      `<p class="muted tiny">Jami: ${mln(c.total.paid)} / ${mln(c.total.total)} so'm · qarz ${mln(c.total.debt)} · ${c.total.debtors} qarzdor</p>` +
      tbl(["Eng past guruhlar", "Fakultet", "#Tushum", "#Qarz"], c.worst_groups.slice(0, 5).map(g => [esc(g.grp), esc(g.faculty), `<span class="bad">${g.pct}%</span>`, mln(g.debt)]))));
  } else cards.push(locked(L.contracts));
  if (P.finance) {
    const f = P.finance;
    cards.push(card("Byudjet ijrosi (yan–okt)", bars(f.categories, {label: r => r.category, value: r => r.pct, max: 130, mark: 100, fmtv: v => `<span class="${v > 105 ? "bad" : ""}">${v}%</span>`}) +
      `<p class="tiny muted">Chiziq — 100% reja. Oylik xarajat dinamikasi:</p>` + spark(f.months.map(m => m.actual))));
  } else cards.push(locked(L.finance));
  if (P.science) {
    const s = P.science;
    cards.push(card("Ilmiy salohiyat", bars(s.by_department, {label: d => d.name, value: d => d.scopus, fmtv: v => v + " ta"}) +
      `<p class="tiny muted">Scopus/WoS 2026 kafedralar kesimida · ilmiy darajalilik ${s.degree_pct}% · 2025 yildan beri nashrsiz: ${s.no_pubs_since_2025} o'qituvchi</p>`));
  } else cards.push(locked(L.science));
  if (P.international) {
    const i = P.international;
    cards.push(card("Xalqaro hamkorlar", tbl(["Hamkor", "Davlat", "Tur", "#Qoldi"], i.partners.filter(p => p.days_left > 0).slice(0, 8).map(p => [esc(p.name), esc(p.country), `<span class="tiny">${esc(p.kind)}</span>`, p.days_left <= 60 ? `<b class="bad">${p.days_left} kun</b>` : p.days_left + " kun"]))));
  } else cards.push(locked(L.international));
  if (P.admissions) {
    const a = P.admissions;
    cards.push(card("Qabul 2026", bars(a.by_direction, {label: d => d.direction, value: d => d.applied, alt: false, fmtv: (v, d) => `${v}`}) +
      `<p class="tiny muted">Arizalar soni yo'nalishlar bo'yicha · jami ${fmt(a.total)} · ${a.funnel.map(f => `${esc(f.status)}: ${f.n}`).join(" · ")}</p>`));
  } else cards.push(locked(L.admissions));
  if (P.youth) {
    const y = P.youth;
    cards.push(card(y.dormitory.length ? "Yotoqxona va murojaatlar" : "Talabalar murojaatlari", (y.dormitory.length ? bars(y.dormitory, {label: d => d.building, value: d => d.pct, max: 100, fmtv: v => v + "%"})
      : `<p class="tiny muted" style="margin:0 0 6px">Institutda yotoqxona yo'q (NQAAE pasporti) — talabalar ijara uylarda yashaydi.</p>`) +
      tbl(["Sana", "Yo'nalish", "Anonim murojaat", "Holat"], y.appeals.slice(0, 6).map(a => [dmy(a.date), esc(a.category), esc(a.text), `<span class="tag ${a.status === "hal qilindi" ? "low" : a.status === "yangi" ? "high" : "mid"}">${esc(a.status)}</span>`]))));
  } else cards.push(locked(L.youth));
  if (P.masters) {
    const m = P.masters;
    cards.push(card("Magistratura", bars(m.stages, {label: s => s.stage, value: s => s.n, fmtv: v => v + " nafar"}) + tbl(["Ilmiy rahbar", "Daraja", "#Magistrant"], m.supervisors.slice(0, 5).map(s => [esc(s.full_name), esc(s.degree), s.n]))));
  }
  if (P.payroll) cards.push(card("Ish haqi fondi (oylik)", bars(P.payroll.by_unit, {label: u => u.unit, value: u => u.fund, fmtv: v => mln(v)}) + (P.payroll.staff ? "" : `<p class="tiny muted">🛡 Faqat jamlangan ko'rinish</p>`)));
  else if (["rektor", "prorektor_oquv"].includes(ME.role_key)) cards.push(locked(L.payroll));
  if (P.hr) cards.push(card("Kadrlar (shaxsiy ma'lumot — faqat mahalliy)", tbl(["F.I.Sh.", "Bo'linma", "Lavozim", "Pasport"], P.hr.staff.slice(0, 8).map(s => [esc(s.full_name), esc(s.unit), esc(s.position), esc(s.passport)]))));
  else if (ME.level <= 2) cards.push(locked(L.hr));
  let shown = cards;
  if (ME.level >= 3 || ME.role_key === "kotib") {
    shown = cards.filter(c => !c.includes("card locked"));
    if (P.tasks) {
      const mine = P.tasks.tasks.filter(t => t.mine && t.status !== "bajarildi");
      shown.unshift(card("Mening topshiriqlarim", mine.length ? tbl(["Topshiriq", "Muddat", ""], mine.slice(0, 6).map(t => [esc(t.text),
        !t.due ? `<span class="unsaid">aytilmagan</span>` : t.overdue ? `<b class="bad">${dtm(t.due_at || t.due)}</b>` : dtm(t.due_at || t.due),
        t.decision ? `<button class="btn sm" onclick="openDecision(${t.meeting_id})">Ochish</button>` : ""])) : `<p class="muted">Ochiq topshiriq yo'q ✓</p>`,
        `<button class="btn sm" onclick="DEC.open=null;go('tasks')">Barchasi →</button>`));
    }
    if (ME.role_key === "kotib")
      shown.unshift(card("📝 Majlis materiali", `<p class="tiny">Majlis yozuvini JARVIS'ga bering: bayonnoma qoralamasi va topshiriqlar tayyorlanadi, tasdiqlagach bo'limlar navbatiga tushadi.</p><button class="btn primary" onclick="DEC.open=null;go('tasks')">Boshlash →</button>`));
    if (ME.allow.some(a => ["facilities", "requests", "youth"].includes(a)))
      shown.unshift(card("🛠 Xizmat markazi", `<p class="tiny">QR nosozliklar, murojaatlar va tadbir qatnashuvi — bir joyda.</p><button class="btn primary" onclick="go('service')">Ochish →</button>`));
    if (ME.allow.includes("spaces"))
      shown.push(card("📷 Auditoriyalar bandligi", `<p class="tiny">Kameralardan faqat odamlar soni: hozir qaysi xona band, qaysi biri bo'sh turibdi.</p><button class="btn" onclick="go('spaces')">Ochish →</button>`));
  }
  h += `<div class="grid g2" style="margin-top:14px">${shown.join("")}</div>`;
  el.innerHTML = h;
  el.querySelectorAll("[data-open]").forEach(b => b.onclick = () => openDecision(+b.dataset.open));
}

/* ---------- chat ---------- */
const SUGG = {
  rektor: ["Qaysi yo'nalishda ortda qolyapmiz?", "Moliya fakultetida o'zlashtirish nega pasaydi?", "Kontrakt qarzdorligi qanday?", "Kengash topshiriqlari bajarilyaptimi?", "Ish haqi fondi qancha?", "Xodimlarning pasport ma'lumotlarini ber"],
  kengash: ["Institutning umumiy holati qanday?", "Byudjet ijrosi qanday?", "Xavf ostidagi talabalar ro'yxatini ber"],
  prorektor_oquv: ["Qaysi guruhlarda o'zlashtirish pasaygan?", "Xavf ostidagi talabalar kimlar?", "Byudjet xarajatlari qanday?"],
  prorektor_ilmiy: ["Scopus maqolalar bo'yicha qaysi kafedra ortda?", "Qaysi xalqaro shartnomalar tugayapti?", "Talabalar baholarini ko'rsat"],
  ilmiy_bolim: ["Scopus maqolalar bo'yicha qaysi kafedra ortda?", "2025 yildan beri maqolasi yo'q o'qituvchilar", "Magistratura holati qanday?"],
  prorektor_moliya: ["Qaysi xarajat moddasi rejadan oshgan?", "Kontrakt qarzi eng ko'p guruhlar?", "Talabalar o'zlashtirishi qanday?"],
  prorektor_yoshlar: ["Yotoqxona holati qanday?", "Hal qilinmagan murojaatlar bormi?", "Byudjet qancha?"],
  dekan: ["Fakultetimda qaysi guruhlar ortda?", "Xavf ostidagi talabalar kimlar?", "Kontrakt qarzdorligi qanday?"],
  kafedra: ["Kafedramda ilmiy faoliyat qanday?", "Qaysi guruhlarda muammo bor?", "Boshqa kafedralar bilan solishtir: moliya"],
  oqituvchi: ["Mening guruhlarimda kim qiynalyapti?", "Kafedra byudjetini ko'rsat"],
  buxgalteriya: ["Kommunal xarajatlar nega oshdi?", "Kontrakt tushumi qanday?"],
};
function renderChat() {
  const s = SUGG[ME.role_key] || ["Umumiy holat qanday?", "Mening topshiriqlarim qaysilar?"];
  $("#suggest").innerHTML = s.map(x => `<button class="btn sm" type="button">${esc(x)}</button>`).join("");
  $("#suggest").querySelectorAll("button").forEach(b => b.onclick = () => ask(b.textContent));
  if (!$("#msgs").children.length) addMsg("a", `Assalomu alaykum! Men JARVIS — ISFT institutining sun'iy intellektli yordamchisiman.\nSiz ${ME.role} sifatida kirdingiz. Ko'lam: ${ME.scope}.\nInstitut ma'lumotlari bo'yicha savol bering — javoblar faqat sizga ruxsat etilgan ma'lumot asosida beriladi.`);
  $("#q").focus();
}
function addMsg(who, text, cls = "") { const d = document.createElement("div"); d.className = `m ${who} ${cls}`; d.textContent = text; $("#msgs").appendChild(d); $("#msgs").scrollTop = 1e9; return d; }
function rich(t) { return esc(t).replace(/\*\*(.+?)\*\*/g, "<b>$1</b>").replace(/^(Tavsiya:)/gm, "<b>$1</b>"); }
$("#chatForm").onsubmit = e => { e.preventDefault(); const q = $("#q").value.trim(); if (q) ask(q); };
let ASKING = false;
async function ask(q) {
  if (ASKING) return toast("JARVIS oldingi savolga javob yozmoqda…");
  ASKING = true; $("#q").value = ""; addMsg("u", q);
  const box = addMsg("a", "", "typing"); box.innerHTML = `<span class="muted">JARVIS ma'lumotni tekshirmoqda…</span>`;
  try {
    const r = await api("/api/chat", {method: "POST", body: JSON.stringify({q})});
    const rd = r.body.getReader(), dec = new TextDecoder(); let buf = "", meta = null, text = "";
    for (;;) {
      const {done, value} = await rd.read(); if (done) break;
      buf += dec.decode(value, {stream: true});
      if (!meta) { const i = buf.indexOf("\n"); if (i < 0) continue; meta = JSON.parse(buf.slice(0, i)); buf = buf.slice(i + 1); }
      text += buf; buf = "";
      const m = $("#msgs"), near = m.scrollHeight - m.scrollTop - m.clientHeight < 120;
      box.innerHTML = metaHtml(meta) + rich(text); if (near) m.scrollTop = 1e9;
    }
    box.classList.remove("typing");
    if (meta && meta.denied.length && !meta.sources.length) box.classList.add("deny");
  } catch (e) {
    box.classList.remove("typing");
    if (e.message !== "auth") box.insertAdjacentHTML("beforeend", `<div class="tiny bad" style="margin-top:6px">⚠️ Javob uzildi. Qayta so'rab ko'ring.</div>`);
    box.querySelector(".muted")?.remove();
  } finally { ASKING = false; }
}
function metaHtml(m) {
  if (!m) return "";
  return `<div class="meta">${m.sources.map(s => `<span class="tag low">📂 ${esc(s)}</span>`).join("")}${m.denied.map(() => `<span class="tag high">🔒 ruxsat yo'q</span>`).join("")}</div>`;
}

/* ---------- majlislar, qarorlar va topshiriqlar ---------- */
/* Oqim: kotib material beradi → JARVIS qoralama → kotib tahrirlab tasdiqlaydi → bo'lim navbati → ijro va chat → rektor nazorati.
   Barcha ruxsatlar serverda (app/decisions.py) tekshiriladi; bu yerda faqat ko'rsatish. */
const DEC = {open: null, timer: null, sig: "", src: "demo", cap: null};
const UNIT_ICO = {it: "server", registrator: "folder"};
const DST = {qoralama: ["Qoralama", "mid"], yangi: ["Navbatda", "gray"], jarayonda: ["Jarayonda", "mid"], bajarildi: ["Bajarildi", "low"]};
const dstTag = (t) => t.overdue ? `<span class="tag high">Muddati o'tgan</span>` : `<span class="tag ${(DST[t.status] || ["", "gray"])[1]}">${esc((DST[t.status] || [t.status])[0])}</span>`;
const dtm = s => { if (!s) return ""; if (s.length <= 10) return dmy(s); const d = new Date(s); return `${dmy(s.slice(0, 10))}, ${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`; };
const hm = s => { const d = new Date(s); return `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`; };
const dueHtml = t => t.due ? `<b class="${t.overdue ? "bad" : ""}">${dtm(t.due)}</b>${t.due_text ? `<span class="said">majlisda: «${esc(t.due_text)}»</span>` : ""}` : `<span class="unsaid">aytilmagan</span>`;
const whoHtml = t => t.assignee_name ? esc(t.assignee_name) : `<span class="unsaid">${t.status === "qoralama" ? "aytilmagan" : "biriktirilmagan"}</span>`;
function openDecision(id) { DEC.open = id; DEC.sig = ""; go("tasks"); }
function closeDecision() { DEC.open = null; clearInterval(DEC.timer); go("tasks"); }

async function renderTasks() {
  clearInterval(DEC.timer);
  if (DEC.open) return renderDecision(DEC.open);
  const el = $("#v-tasks"); let t, L;
  try { [t, L] = await Promise.all([J("/api/section/tasks"), J("/api/dec/list")]); }
  catch (e) { if (e.message === "denied") { el.innerHTML = locked("Majlis topshiriqlari"); return; } throw e; }
  const isKotib = ME.role_key === "kotib", lead = ["rektor", "kengash"].includes(ME.role_key);
  const old = t.tasks.filter(x => !x.decision);
  let h = `<div class="head"><div><h2>Majlislar va topshiriqlar</h2><span class="muted">${t.tasks.length} ta topshiriq · ${t.done} bajarilgan · ${t.overdue ? `<b class="bad">${t.overdue} muddati o'tgan</b>` : "muddati o'tgan yo'q"}</span></div>
    ${isKotib || ME.role_key === "rektor" ? `<button class="btn ghost sm" id="decReset" title="Demo ssenariysida yaratilgan qarorlarni o'chiradi va LMS hodisasi xabarini bekor qiladi">↺ Demoni qayta boshlash</button>` : ""}</div>`;
  if (isKotib) h += await newMeetingCard();
  if (L.queue) h += queueCard(L.queue);
  const decs = L.decisions;
  if (decs.length || isKotib || lead) h += `<div class="card" style="margin-top:14px"><h3>${ico("tasks")} Majlis qarorlari</h3>` + (decs.length ? `<div class="dec-list">${decs.map(decRow).join("")}</div>` :
    `<p class="muted">${isKotib ? "Hali qaror yo'q. Yuqorida majlis materialini JARVIS'ga bering." : "Hali tasdiqlangan qaror yo'q. Majlis materialini rektorat kotibi kiritadi."}</p>`) + `</div>`;
  if (old.length) h += `<div class="card" style="margin-top:14px"><h3>Avvalgi majlis topshiriqlari</h3>${tbl(["Majlis", "Mas'ul", "Topshiriq", "Muddat", "Holat", ""], old.map(x => [
    `<span class="tiny">${esc(x.meeting)}<br><span class="muted">${dmy(x.meeting_date)}</span></span>`, esc(x.assignee), esc(x.text),
    !x.due ? `<span class="unsaid">aytilmagan</span>` : x.overdue ? `<b class="bad">${dmy(x.due)}<br><span class="tiny">${-x.days} kun o'tdi</span></b>` : `${dmy(x.due)}<br><span class="tiny muted">${x.status === "bajarildi" ? "" : x.days === 0 ? "bugun" : x.days + " kun qoldi"}</span>`,
    `<span class="tag ${x.status === "bajarildi" ? "low" : x.overdue ? "high" : "mid"}">${x.overdue ? "muddati o'tgan" : esc(x.status)}</span>`,
    (lead || x.assignee_role === ME.role_key) && x.status !== "bajarildi" ? `<button class="btn sm" data-done="${x.id}">✓ Bajarildi</button>` : ""]))}</div>`;
  el.innerHTML = h;
  el.querySelectorAll("[data-done]").forEach(b => b.onclick = () => busy(b, async () => { await J(`/api/tasks/${b.dataset.done}/status`, {method: "POST", body: JSON.stringify({status: "bajarildi"})}); toast("Belgilandi"); renderTasks(); }));
  el.querySelectorAll("[data-open]").forEach(b => b.onclick = () => openDecision(+b.dataset.open));
  bindAssign(el, renderTasks);
  if ($("#decReset")) $("#decReset").onclick = () => busy($("#decReset"), async () => { const r = await J("/api/dec/demo-reset", {method: "POST"}); toast(`Demo qayta boshlandi (${r.removed} ta qaror o'chirildi)`); renderTasks(); badges(); });
  if (isKotib) bindNewMeeting();
}

function decRow(d) {
  const done = d.tasks.filter(t => t.status === "bajarildi").length;
  return `<div class="dec-row"><div class="dec-row-h"><div><b>${esc(d.title)}</b><span class="muted tiny"> · ${dmy(d.date)} · ${d.status === "qoralama" ? `<span class="tag mid">qoralama</span>` : `${done}/${d.tasks.length} bajarildi`}</span></div>
    <button class="btn sm ${d.status === "qoralama" ? "primary" : ""}" data-open="${d.id}">${d.status === "qoralama" ? "Tahrirlash" : "Ochish"} →</button></div>
    ${d.tasks.map(t => `<div class="dec-line"><span class="dl-unit">${esc(t.unit_name || "bo'lim aytilmagan")}</span><span class="dl-who">${whoHtml(t)}</span>${dstTag(t)}
      <span class="dl-res">${t.result ? esc(t.result.length > 110 ? t.result.slice(0, 110) + "…" : t.result) : t.blocked ? `<span class="muted">${esc(t.dep?.unit_name || "")} natijasi kutilmoqda</span>` : ""}</span></div>`).join("")}</div>`;
}

function queueCard(q) {
  const open = q.tasks.filter(t => t.status !== "bajarildi");
  return `<div class="card" style="margin-top:14px"><h3>${ico(UNIT_ICO[q.unit] || "tasks")} ${q.head ? `${esc(q.unit_name)} navbati` : "Menga biriktirilgan topshiriqlar"} <span class="tag ${open.length ? "mid" : "low"}">${open.length} ochiq</span></h3>
    ${q.tasks.length ? `<div class="dec-list">${q.tasks.map(t => `<div class="dec-row"><div class="dec-row-h"><div><b>${esc(t.text)}</b><div class="tiny muted">${esc(t.meeting)} · ${dmy(t.meeting_date)}</div></div>
      <button class="btn sm primary" data-open="${t.meeting_id}">Ochish →</button></div>
      <div class="kv"><span>Muddat</span><span>${dueHtml(t)}</span><span>Holat</span><span>${dstTag(t)}${t.blocked ? ` <span class="tiny muted">· ${esc(t.dep.unit_name)} natijasi kutilmoqda</span>` : ""}</span>
      <span>Ijrochi</span><span>${t.can_assign ? assignSel(t, q.staff) : whoHtml(t)}</span></div></div>`).join("")}</div>` : `<p class="muted">Navbat bo'sh.</p>`}</div>`;
}
const assignSel = (t, staff) => `<select class="sel-sm" data-assign="${t.id}"><option value="">— biriktirilmagan —</option>${staff.map(s => `<option value="${s.id}" ${s.id === t.assignee_user ? "selected" : ""}>${esc(s.name)} (${esc(s.role)})</option>`).join("")}</select>`;
function bindAssign(root, after) {
  root.querySelectorAll("[data-assign]").forEach(s => s.onchange = async () => {
    if (!s.value) return;
    s.disabled = true;
    try { await J(`/api/dec/task/${s.dataset.assign}/assign`, {method: "POST", body: JSON.stringify({user_id: +s.value})}); toast("Xodimga biriktirildi"); }
    catch (e) {} finally { after(); }
  });
}

/* --- kotib: yangi majlis materiali --- */
async function newMeetingCard() {
  if (!DEC.cap) DEC.cap = await J("/api/dec/capabilities");
  const c = DEC.cap;
  return `<div class="card" style="margin-top:6px"><h3>${ico("chat")} Majlis materialini JARVIS'ga berish</h3>
    <div class="src-tabs" role="tablist">
      <button class="btn sm ${DEC.src === "demo" ? "primary" : ""}" data-src="demo">Demo transkript</button>
      <button class="btn sm ${DEC.src === "manual" ? "primary" : ""}" data-src="manual">Matnni qo'lda kiritish</button>
      <button class="btn sm" disabled title="${esc(c.audio_note)}">🎙 Ovozdan yozish — o'rnatilmagan</button>
    </div>
    <div class="src-note ${DEC.src === "demo" ? "demo" : ""}">${DEC.src === "demo"
      ? `<b>DEMO TRANSKRIPT.</b> Bu tayyor namunaviy matn — haqiqiy ovozdan olinmagan. Ovozdan matnga o'tkazish (lokal STT) bu serverda hali o'rnatilmagan; o'rnatilganda ham ovoz institutdan tashqariga chiqmaydi.`
      : `Majlis yozuvi yoki kotib qaydlarini shu yerga qo'ying. JARVIS faqat matnda aytilgan bo'lim, xodim va muddatni oladi.`}</div>
    <input id="mTitle" value="Rektorat tezkor yig'ilishi" style="width:100%;margin:10px 0 8px" aria-label="Majlis nomi">
    <textarea id="mText" ${DEC.src === "demo" ? "readonly" : ""} aria-label="Majlis matni">${DEC.src === "demo" ? esc(c.sample) : ""}</textarea>
    <div class="row-actions" style="margin-top:10px"><button class="btn primary" id="mDraft">JARVIS: bayonnoma va topshiriqlar qoralamasi</button>
    <span class="tiny muted">Qoralama tasdiqlanmaguncha hech kimga yuborilmaydi.</span></div></div>`;
}
function bindNewMeeting() {
  document.querySelectorAll("[data-src]").forEach(b => b.onclick = () => { DEC.src = b.dataset.src; renderTasks(); });
  $("#mDraft").onclick = () => busy($("#mDraft"), async () => {
    if (!$("#mText").value.trim()) return toast("Majlis matnini kiriting");
    const d = await J("/api/dec/draft", {method: "POST", body: JSON.stringify({title: $("#mTitle").value, transcript: $("#mText").value, source: DEC.src})});
    toast(`Qoralama tayyor: ${d.tasks.length} ta topshiriq`); openDecision(d.id);
  }, "JARVIS tahlil qilmoqda… (≈15 s)");
}

/* --- qaror kartasi --- */
async function renderDecision(id, silent) {
  const el = $("#v-tasks");
  let d;
  try { d = await J(`/api/dec/${id}`); } catch (e) { if (e.message === "denied") { el.innerHTML = backBtn() + locked("Bu qaror"); return; } throw e; }
  const sig = JSON.stringify(d);
  if (silent && sig === DEC.sig) return;
  // foydalanuvchi yozayotgan bo'lsa yangilab yubormaymiz
  if (silent && [...el.querySelectorAll("textarea, input[type=text], .chat-in input")].some(x => x.value.trim() && !x.readOnly)) return;
  DEC.sig = sig;
  const scroll = silent ? window.scrollY : 0;
  el.innerHTML = d.can_edit ? draftHtml(d) : decisionHtml(d);
  if (d.can_edit) bindDraft(d); else bindDecision(d);
  hydrateIcons(el);
  if (silent) window.scrollTo({top: scroll});
  const box = el.querySelector(".chat-msgs"); if (box) box.scrollTop = 1e9;
  clearInterval(DEC.timer);
  if (!d.can_edit) DEC.timer = setInterval(() => { if (DEC.open === id && !$("#v-tasks").classList.contains("hidden")) renderDecision(id, true).catch(() => {}); }, 6000);
}
const backBtn = () => `<button class="btn ghost sm" onclick="closeDecision()" style="margin-bottom:10px">← Barcha qarorlar</button>`;
const srcBadge = d => d.source === "demo" ? `<span class="tag mid" title="Namunaviy matn, ovozdan olinmagan">Manba: demo transkript</span>` : `<span class="tag gray">Manba: qo'lda kiritilgan matn</span>`;

function draftHtml(d) {
  const opts = (sel) => `<option value="">— aytilmagan —</option>` + d.units.map(u => `<option value="${u.key}" ${u.key === sel ? "selected" : ""}>${esc(u.name)}</option>`).join("");
  return backBtn() + `<div class="head"><div><h2>${esc(d.title)}</h2><span class="muted">${dmy(d.date)} · <span class="tag mid">Qoralama — tasdiqlanmagan</span> ${srcBadge(d)}</span></div></div>
  <div class="src-note">${ico("info", 15)} <span><b>JARVIS qoralamasi — tekshiring.</b> ${esc(d.extract_note || "")}. Majlisda aytilmagan maydonlar bo'sh qoldirildi.</span></div>
  ${d.incident ? `<div class="src-note" style="margin-top:8px">${ico("wrench", 15)} <span>Bog'liq hodisa (Xizmat markazi): <b>${esc(d.incident.title)}</b> · ${d.incident.n} ta murojaat${d.incident.notified_at ? "" : " · talabalarga hali xabar berilmagan"}</span></div>` : ""}
  <div class="grid g2" style="margin-top:14px">${d.tasks.map((t, i) => `<div class="card draft-task" data-tid="${t.id}">
    <div class="dt-h"><b>${i + 1}-topshiriq</b><button class="btn ghost sm" data-rm="${t.id}" title="Bu bandni olib tashlash">✕ Olib tashlash</button></div>
    <div class="form-grid">
      <label class="full">Topshiriq<textarea class="f-text" rows="3">${esc(t.text)}</textarea></label>
      <label>Bo'lim${t.unit ? "" : ` <span class="unsaid">majlisda aytilmagan</span>`}<select class="f-unit">${opts(t.unit)}</select></label>
      <label>Mas'ul xodim<input type="text" class="f-who" value="${esc(t.assignee_stated || "")}" placeholder="Aytilmagan — bo'lim rahbari biriktiradi"></label>
      <label>Muddat ${t.due_text ? `<span class="said">majlisda: «${esc(t.due_text)}»</span>` : `<span class="unsaid">majlisda aytilmagan</span>`}<input type="datetime-local" class="f-due" value="${t.due_at ? (t.due_at.length === 10 ? t.due_at + "T18:00" : t.due_at.slice(0, 16)) : ""}"></label>
      <label>Bog'liqlik ${t.dep_text ? `<span class="said">majlisda: «${esc(t.dep_text)}»</span>` : ""}<select class="f-dep"><option value="">— yo'q —</option>${d.tasks.filter(o => o.id !== t.id).map(o => `<option value="${o.id}" ${o.id === t.depends_on ? "selected" : ""}>${d.tasks.indexOf(o) + 1}-topshiriq natijasidan keyin</option>`).join("")}</select></label>
    </div>
    ${t.evidence ? `<div class="evidence">Asos: «${esc(t.evidence)}»</div>` : ""}</div>`).join("")}</div>
  <div class="card" style="margin-top:14px"><h3>Bayonnoma qoralamasi</h3><input id="dTitle" value="${esc(d.title)}" style="width:100%;margin-bottom:8px" aria-label="Majlis nomi"><textarea id="dMin" style="min-height:260px">${esc(d.minutes || "")}</textarea>
    <details style="margin-top:10px"><summary class="tiny muted">Manba matn</summary><pre class="src-text">${esc(d.transcript || "")}</pre></details></div>
  <div class="sticky-actions"><button class="btn" id="dSave">Saqlash</button><button class="btn primary" id="dConfirm">${ico("check", 16)} Tasdiqlash va bo'limlarga yuborish</button>
    <button class="btn ghost" id="dDrop">Qoralamani o'chirish</button></div>`;
}
function collectDraft(d) {
  const rm = [...document.querySelectorAll(".draft-task.removed")].map(x => +x.dataset.tid);
  return {title: $("#dTitle").value, minutes: $("#dMin").value, remove: rm, tasks: [...document.querySelectorAll(".draft-task")].map(c => ({
    id: +c.dataset.tid, text: c.querySelector(".f-text").value, unit: c.querySelector(".f-unit").value || null, assignee: c.querySelector(".f-who").value,
    due_at: c.querySelector(".f-due").value || null, depends_on: +c.querySelector(".f-dep").value || null}))};
}
function bindDraft(d) {
  document.querySelectorAll("[data-rm]").forEach(b => b.onclick = () => { const c = b.closest(".draft-task"); c.classList.toggle("removed"); b.textContent = c.classList.contains("removed") ? "↺ Qaytarish" : "✕ Olib tashlash"; });
  const save = async () => J(`/api/dec/${d.id}`, {method: "PUT", body: JSON.stringify(collectDraft(d))});
  $("#dSave").onclick = () => busy($("#dSave"), async () => { await save(); toast("Qoralama saqlandi"); DEC.sig = ""; renderDecision(d.id); });
  $("#dConfirm").onclick = () => busy($("#dConfirm"), async () => {
    const body = collectDraft(d), live = body.tasks.filter(t => !body.remove.includes(t.id));
    if (!live.length) return toast("Kamida bitta topshiriq bo'lishi kerak");
    if (live.some(t => !t.unit)) return toast("Har bir topshiriq uchun bo'limni tanlang — aks holda u hech kimning navbatiga tushmaydi");
    await save();
    const r = await J(`/api/dec/${d.id}/confirm`, {method: "POST"});
    toast(r.already ? "Bu qaror avval tasdiqlangan — yangi topshiriq yaratilmadi" : `Tasdiqlandi: ${live.length} ta topshiriq bo'limlar navbatiga yuborildi`);
    DEC.sig = ""; renderDecision(d.id); badges();
  }, "Yuborilmoqda…");
  $("#dDrop").onclick = () => busy($("#dDrop"), async () => { await J(`/api/dec/${d.id}`, {method: "DELETE"}); toast("Qoralama o'chirildi"); closeDecision(); });
}

function decisionHtml(d) {
  const chatTask = d.tasks.find(t => t.can_chat);
  const units = [...new Set(d.tasks.map(t => t.unit_name).filter(Boolean))].join(" ↔ ");
  const done = d.tasks.filter(t => t.status === "bajarildi").length;
  return backBtn() + `<div class="head"><div><h2>${esc(d.title)}</h2><span class="muted">${dmy(d.date)} · <span class="tag ${done === d.tasks.length ? "low" : "gray"}">Tasdiqlangan · ${done}/${d.tasks.length} bajarildi</span> ${srcBadge(d)}</span>
    <div class="tiny muted" style="margin-top:4px">Tasdiqladi: ${esc(d.confirmed_by || "")} · ${dtm(d.confirmed_at)}</div></div></div>
  ${d.incident ? `<div class="src-note">${ico("wrench", 15)} <span>Bog'liq hodisa (Xizmat markazi): <b>${esc(d.incident.title)}</b> · ${d.incident.n} ta murojaat · ${d.incident.notified_at ? `<span class="good">talabalarga xabar yuborilgan (${dtm(d.incident.notified_at)})</span>` : `<span class="bad">talabalarga hali xabar berilmagan</span>`}</span></div>` : ""}
  <div class="dec-grid">
    <div class="dec-tasks">${d.tasks.map((t, i) => taskCard(d, t, i)).join("")}</div>
    <div class="dec-side">
      <div class="card chat-card"><h3>${ico("chat")} Ichki chat${units ? ` <span class="tiny muted">${esc(units)}</span>` : ""}</h3>
        <div class="chat-msgs">${d.msgs.length ? d.msgs.map(m => `<div class="cm ${m.user_id === ME.id ? "own" : ""}"><div class="cm-h"><b>${esc(m.user_short || m.user_name)}</b> <span>${esc(m.role)} · ${hm(m.ts)}</span></div><div>${esc(m.text)}</div></div>`).join("") : `<p class="tiny muted">Xabar yo'q. Bog'langan topshiriqlar ijrochilari shu yerda yozishadi.</p>`}</div>
        ${chatTask ? `<form class="chat-in" data-chat="${chatTask.id}"><input type="text" placeholder="Xabar yozing…" maxlength="2000" aria-label="Xabar"><button class="btn primary sm">${ico("send", 15)}</button></form>` : `<p class="tiny muted" style="margin:8px 0 0">${["rektor", "kengash"].includes(ME.role_key) ? "Rahbariyat chatni kuzatadi; yozishma ijrochilar o'rtasida." : ""}</p>`}
      </div>
      <div class="card" style="margin-top:14px"><h3>${ico("history")} Tarix</h3><ol class="tl">${d.log.map(l => `<li><span class="tl-t">${dtm(l.ts)}</span><b>${esc(l.action)}</b> — ${esc(l.user_short || l.user_name)}${l.detail ? `<div class="tiny muted">${esc(l.detail.length > 140 ? l.detail.slice(0, 140) + "…" : l.detail)}</div>` : ""}</li>`).join("")}</ol></div>
      ${d.minutes ? `<div class="card" style="margin-top:14px"><details><summary><b>Bayonnoma</b></summary><pre class="src-text">${esc(d.minutes)}</pre></details></div>` : ""}
    </div>
  </div>`;
}
function taskCard(d, t, i) {
  const notifyBox = d.incident && t.unit === "registrator" && !d.incident.notified_at;
  return `<div class="card dec-task ${t.status === "bajarildi" ? "done" : ""}" data-tid="${t.id}">
    <div class="dt-h"><span class="dt-unit">${ico(UNIT_ICO[t.unit] || "tasks", 16)} ${esc(t.unit_name || "Bo'lim aytilmagan")}</span>${dstTag(t)}</div>
    <p class="dt-text">${i + 1}. ${esc(t.text)}</p>
    <div class="kv"><span>Mas'ul</span><span>${t.can_assign ? assignSel(t, d.staff) : whoHtml(t)}</span>
      <span>Muddat</span><span>${dueHtml(t)}</span>
      ${t.dep || t.dep_text ? `<span>Bog'liqlik</span><span>${t.dep ? `${esc(t.dep.unit_name)} natijasidan keyin · ${t.dep.status === "bajarildi" ? `<span class="good">natija keldi</span>` : `<span class="warn-t">kutilmoqda</span>`}` : ""}${t.dep_text ? `<span class="said">majlisda: «${esc(t.dep_text)}»</span>` : ""}</span>` : ""}
    </div>
    ${t.dep && t.dep.result && t.can_act ? `<div class="res dep-res"><div class="res-h">${esc(t.dep.unit_name)} natijasi</div>${esc(t.dep.result)}</div>` : ""}
    ${t.result ? `<div class="res"><div class="res-h">${t.status === "bajarildi" ? "Natija" : "Oraliq natija"} · ${esc(t.result_by || "")} · ${dtm(t.result_at)}</div>${esc(t.result)}</div>` : ""}
    ${t.can_act && t.status !== "bajarildi" ? `<div class="act">
      ${t.status === "yangi" ? `<button class="btn sm" data-start="${t.id}">▶ Ishni boshlash</button>` : ""}
      <textarea class="f-res" rows="3" placeholder="${t.unit === "registrator" ? "Talabalarga xabar matni…" : "Tekshiruv natijasi: sabab, nima qilindi, holat…"}">${t.status === "jarayonda" && t.result ? esc(t.result) : ""}</textarea>
      ${t.dep && t.dep.result && t.unit === "registrator" ? `<button class="btn ghost sm" data-tpl="${t.id}">${esc(t.dep.unit_name)} natijasidan xabar loyihasi</button>` : ""}
      ${notifyBox ? `<label class="chk-line"><input type="checkbox" class="f-notify" checked> Xizmat markazidagi «${esc(d.incident.title)}» hodisasiga murojaat qilgan ${d.incident.n} ta talabaga javob sifatida yuborish</label>` : ""}
      <div class="row-actions"><button class="btn sm" data-save="${t.id}">Oraliq natijani saqlash</button>
      <button class="btn sm primary" data-finish="${t.id}" ${t.blocked ? "disabled" : ""}>${ico("check", 15)} Natijani kiritish va yakunlash</button></div>
      ${t.blocked ? `<p class="tiny warn-t" style="margin:0">${esc(t.dep.unit_name)} natijasi kelmaguncha yakunlab bo'lmaydi (server ham tekshiradi). Chatda yozishishingiz mumkin.</p>` : ""}
    </div>` : ""}
  </div>`;
}
function bindDecision(d) {
  const el = $("#v-tasks"), re = () => { DEC.sig = ""; renderDecision(d.id); badges(); };
  bindAssign(el, re);
  const post = (tid, body) => J(`/api/dec/task/${tid}/update`, {method: "POST", body: JSON.stringify(body)});
  el.querySelectorAll("[data-start]").forEach(b => b.onclick = () => busy(b, async () => { await post(b.dataset.start, {status: "jarayonda"}); toast("Holat: jarayonda"); re(); }));
  el.querySelectorAll("[data-save]").forEach(b => b.onclick = () => busy(b, async () => {
    const v = b.closest(".dec-task").querySelector(".f-res").value.trim(); if (!v) return toast("Natija matnini yozing");
    await post(b.dataset.save, {status: "jarayonda", result: v}); toast("Oraliq natija saqlandi"); re(); }));
  el.querySelectorAll("[data-finish]").forEach(b => b.onclick = () => busy(b, async () => {
    const c = b.closest(".dec-task"), v = c.querySelector(".f-res").value.trim(); if (!v) return toast("Yakunlash uchun natijani yozing");
    await post(b.dataset.finish, {status: "bajarildi", result: v, notify_incident: !!c.querySelector(".f-notify")?.checked});
    toast(c.querySelector(".f-notify")?.checked ? "Yakunlandi · xabar talabalarga yuborildi" : "Yakunlandi"); re(); }));
  el.querySelectorAll("[data-tpl]").forEach(b => b.onclick = () => {
    const t = d.tasks.find(x => x.id === +b.dataset.tpl), ta = b.closest(".dec-task").querySelector(".f-res");
    ta.value = `Hurmatli talabalar!\n\n${d.incident ? d.incident.title : "LMS platformasidagi muammo"} bo'yicha: ${t.dep.unit_name} tekshiruvni yakunladi. ${t.dep.result}\n\nAlohida murojaat yuborishingiz shart emas. Muammo takrorlansa, registrator departamentiga yoki Xizmat markaziga xabar bering.\n\nHurmat bilan, Akademik faoliyat va registrator departamenti`;
    ta.focus(); toast("Loyiha bog'liq topshiriq natijasidan tuzildi — tekshirib, tahrir qiling");
  });
  el.querySelectorAll("[data-chat]").forEach(f => f.onsubmit = e => {
    e.preventDefault(); const inp = f.querySelector("input"), v = inp.value.trim(); if (!v) return;
    busy(f.querySelector("button"), async () => { await J(`/api/dec/task/${f.dataset.chat}/msg`, {method: "POST", body: JSON.stringify({text: v})}); inp.value = ""; re(); });
  });
}

/* ---------- Talabalar bilan ishlash markazi ----------
   Qoidalar va ruxsatlar serverda (app/student_ops.py); bu yerda faqat ko'rsatish va natija kiritish. */
const OPSV = {page: 30, tab: null, rule: "", level: 0, q: "", kind: "", student: null, sum: null, review: null};
const OPS_RULES = {kontrakt: "Kontrakt", davomat: "Davomat", akademik: "O'zlashtirish", hujjat: "Hujjat", tatil: "Akademik ta'til", otrabotka: "Otrabotka"};
const OPS_LVL = {1: ["Diqqat", "mid"], 2: ["Kritik", "high"], 3: ["Jiddiy", "high"]};
const OPS_KIND = {qongiroq: "📞 Qo'ng'iroq", suhbat: "🗣 Suhbat", hujjat: "📄 Hujjat so'rash", xat: "✉️ Ogohlantirish xati", buyruq: "📝 Buyruq loyihasi"};
const OPS_ROLE = {call_center: "Call-markaz", tyutor: "Tyutor", talabalar: "Registrator departamenti"};
const OPS_REASON = {sababsiz: "Sababsiz", kasallik: "Kasallik", komandirovka: "Komandirovka", mehnat_tatili: "Mehnat ta'tili", oilaviy: "Oilaviy"};
const OPS_DOC = {tasdiqlangan: ["tasdiqlangan", "low"], kutilmoqda: ["kutilmoqda", "mid"], yoq: ["yo'q", "high"]};
const som = x => fmt(Math.round(x)) + " so'm";
const lvlTag = l => `<span class="tag ${OPS_LVL[l][1]}">${OPS_LVL[l][0]}</span>`;
const isAgg = () => ["rektor", "kengash"].includes(ME.role_key);
function factText(rule, f) {
  if (rule === "kontrakt") return `${esc(f.installment)} (${f.pct}%): ${som(f.need_now)} yetishmaydi · ${f.days < 0 ? `<b class="bad">${-f.days} kun o'tdi</b>` : `<b class="bad">${f.days} kun qoldi</b>`}`;
  if (rule === "davomat") return `${f.hours} soat sababsiz${f.next ? ` · keyingi bosqich ${f.next} soatda` : ""}`;
  if (rule === "akademik") return `JPA ${f.gpa5}${f.gpa_ok ? " (yetarli)" : ""} · ${f.fails.length} ta fandan o'tmagan: ${esc(f.fails.map(x => x.subject).join(", "))}`;
  if (rule === "hujjat") return `${f.items.length} ta sababli qoldirish hujjati kutilmoqda${f.items.some(i => i.late) ? ` · <b class="bad">muddat o'tdi</b>` : ""}`;
  if (rule === "tatil") return `Ta'til ${dmy(f.end)}da tugaydi · ${f.days < 0 ? `<b class="bad">${-f.days} kun o'tdi</b>` : f.days + " kun qoldi"}`;
  if (rule === "otrabotka") return `${esc(f.subject)}: muddat ${dtm(f.due_at)} · ${f.hours_left < 0 ? `<b class="bad">${-Math.round(f.hours_left)} soat o'tdi</b>` : `<b class="bad">${Math.round(f.hours_left)} soat qoldi</b>`}`;
  return "";
}

async function renderOps() {
  const el = $("#v-ops");
  el.innerHTML = `<p class="muted">Yuklanmoqda…</p>`;
  OPSV.sum = await J("/api/ops/summary");
  const tabs = isAgg() ? [] : ME.role_key === "call_center" ? ["navbat"] : ME.role_key === "tyutor" ? ["navbat", "holatlar", "otrabotka", "qoidalar"] : ["holatlar", "navbat", "otrabotka", "qoidalar"];
  if (!tabs.includes(OPSV.tab)) OPSV.tab = tabs[0] || null;
  const T = {holatlar: "Holatlar", navbat: ME.role_key === "call_center" ? "Qo'ng'iroqlar navbati" : "Mening navbatim", otrabotka: "Otrabotka", qoidalar: "Qoidalar"};
  const canRun = ["talabalar", "prorektor_oquv"].includes(ME.role_key);
  el.innerHTML = `<div class="head"><div><h2>Talabalar bilan ishlash markazi</h2><span class="muted">Qoidalar har 10 daqiqada avtomatik tekshiriladi${OPSV.sum.last_run ? ` · oxirgi: ${hm(OPSV.sum.last_run)}` : ""} · qaror va imzo — mas'ul xodimda</span></div>
    <div class="row-actions">${canRun ? `<button class="btn sm" id="opsRun">↻ Hozir tekshirish</button>` : ""}${tabs.map(t => `<button class="btn ${t === OPSV.tab ? "primary" : ""}" data-ot="${t}">${T[t]}</button>`).join("")}</div></div>
    <div class="src-note demo" style="margin-bottom:14px">${ico("info", 15)}<span>Chegaralar (30/48/72 soat, JPA 3.0, 2 ta fan, 3 kun…) — <b>institut tomonidan hali tasdiqlanmagan</b> namunaviy qiymatlar. Ma'lumotlar sun'iy.</span></div>
    ${opsSummary(OPSV.sum)}<div id="opsBody" style="margin-top:14px"></div>`;
  el.querySelectorAll("[data-ot]").forEach(b => b.onclick = () => { OPSV.tab = b.dataset.ot; OPSV.student = null; OPSV.page = 30; renderOps(); });
  el.querySelectorAll("[data-sr]").forEach(b => b.onclick = () => { if (isAgg()) return; OPSV.rule = b.dataset.sr; OPSV.level = 0; OPSV.tab = ME.role_key === "call_center" ? "navbat" : "holatlar"; OPSV.student = null; renderOps(); });
  if ($("#opsRun")) $("#opsRun").onclick = () => busy($("#opsRun"), async () => { const r = await J("/api/ops/evaluate", {method: "POST"}); toast(`Tekshirildi: ${r.opened} yangi holat, ${r.closed} yopildi, ${r.tasks + r.followups} topshiriq`); renderOps(); });
  hydrateIcons(el);
  if (!OPSV.tab) { $("#opsBody").innerHTML = `<div class="card"><p class="tiny muted" style="margin:0">🛡 Rahbariyat uchun faqat jamlangan raqamlar. Talabalar ro'yxati, telefonlar va suhbat skriptlari — registrator departamenti, tyutorlar va call-markazda. Har bir harakat audit jurnalida.</p></div>`; return; }
  if (OPSV.student) return opsStudent(OPSV.student);
  ({holatlar: opsCases, navbat: opsTasks, otrabotka: opsRetakes, qoidalar: opsPolicy})[OPSV.tab]();
}
function opsSummary(s) {
  const by = {}; s.by_rule.forEach(r => { (by[r.rule] ||= {1: 0, 2: 0, 3: 0, n: 0}); by[r.rule][r.level] = r.n; by[r.rule].n += r.n; });
  const cards = Object.keys(OPS_RULES).map(k => { const v = by[k] || {1: 0, 2: 0, 3: 0, n: 0};
    return isAgg() ? `<div class="card kpi ${v[3] || v[2] ? "bad" : ""}">` + `<div class="l">${OPS_RULES[k]}</div><div class="v">${v.n}</div><div class="s">${[v[3] && `${v[3]} jiddiy`, v[2] && `${v[2]} kritik`, v[1] && `${v[1]} diqqat`].filter(Boolean).join(" · ") || "ochiq holat yo'q"}</div></div>`
      : `<div class="card kpi ops-k ${v[3] || v[2] ? "bad" : ""}" data-sr="${k}" role="button" tabindex="0"><div class="l">${OPS_RULES[k]}</div><div class="v">${v.n}</div>
      <div class="s">${[v[3] && `${v[3]} jiddiy`, v[2] && `${v[2]} kritik`, v[1] && `${v[1]} diqqat`].filter(Boolean).join(" · ") || "ochiq holat yo'q"}</div></div>`; }).join("");
  const tk = s.tasks.map(t => `<span class="chip-s">${OPS_ROLE[t.role] || t.role}: <b>${t.n}</b>${t.late ? ` · <span class="bad">${t.late} kechikkan</span>` : ""}</span>`).join("");
  return `<div class="grid g6">${cards}</div><div class="ops-strip">${tk || ""}${s.done_today !== undefined ? `<span class="chip-s">Bugun bajarganim: <b>${s.done_today}</b></span>` : `<span class="chip-s">7 kunda yopilgan holatlar: <b>${s.closed_7d}</b></span>`}</div>`;
}

/* --- holatlar --- */
async function opsCases() {
  const b = $("#opsBody");
  const qs = new URLSearchParams({rule: OPSV.rule, level: OPSV.level || 0, q: OPSV.q});
  const rows = await J("/api/ops/cases?" + qs);
  b.innerHTML = `<div class="card"><div class="ops-filters">
      <select id="ofRule" aria-label="Qoida"><option value="">Barcha qoidalar</option>${Object.entries(OPS_RULES).map(([k, v]) => `<option value="${k}" ${k === OPSV.rule ? "selected" : ""}>${v}</option>`).join("")}</select>
      <select id="ofLvl" aria-label="Daraja"><option value="0">Barcha darajalar</option><option value="2" ${OPSV.level == 2 ? "selected" : ""}>Kritik va jiddiy</option><option value="3" ${OPSV.level == 3 ? "selected" : ""}>Faqat jiddiy</option></select>
      <input id="ofQ" type="text" placeholder="Ism, guruh yoki HEMIS ID" value="${esc(OPSV.q)}" aria-label="Qidiruv"></div>
    <p class="tiny muted" style="margin:8px 0">${rows.length}${rows.length >= 300 ? "+" : ""} ta ochiq holat · daraja bo'yicha tartiblangan</p>
    ${tbl(["Talaba", "Qoida", "Daraja", "Fakt", "#Ochiq ish", ""], rows.map(r => [`<b>${esc(r.full_name)}</b><div class="tiny muted">${esc(r.grp)} · ${esc(r.faculty)}</div>`,
      OPS_RULES[r.rule], lvlTag(r.level), `<span class="tiny">${factText(r.rule, r.facts)}</span>`, r.open_tasks, `<button class="btn sm" data-st="${r.student_id}">Karta</button>`]))}</div>`;
  $("#ofRule").onchange = e => { OPSV.rule = e.target.value; opsCases(); };
  $("#ofLvl").onchange = e => { OPSV.level = +e.target.value; opsCases(); };
  let tmr; $("#ofQ").oninput = e => { clearTimeout(tmr); tmr = setTimeout(() => { OPSV.q = e.target.value; opsCases().then(() => { const i = $("#ofQ"); i.focus(); i.setSelectionRange(i.value.length, i.value.length); }); }, 350); };
  b.querySelectorAll("[data-st]").forEach(x => x.onclick = () => { OPSV.student = +x.dataset.st; opsStudent(OPSV.student); });
}

/* --- navbat (topshiriqlar) --- */
async function opsTasks() {
  const b = $("#opsBody");
  const qs = new URLSearchParams({rule: OPSV.rule, kind: OPSV.kind});
  const rows = await J("/api/ops/tasks?" + qs);
  const kinds = ME.role_key === "call_center" ? [] : Object.entries(OPS_KIND);
  b.innerHTML = `<div class="ops-filters" style="margin-bottom:10px">
      <select id="otRule" aria-label="Qoida"><option value="">Barcha qoidalar</option>${Object.entries(OPS_RULES).map(([k, v]) => `<option value="${k}" ${k === OPSV.rule ? "selected" : ""}>${v}</option>`).join("")}</select>
      ${kinds.length ? `<select id="otKind" aria-label="Tur"><option value="">Barcha turlar</option>${kinds.map(([k, v]) => `<option value="${k}" ${k === OPSV.kind ? "selected" : ""}>${v}</option>`).join("")}</select>` : ""}
      <span class="tiny muted">${rows.length}${rows.length >= 200 ? "+" : ""} ta ochiq topshiriq · kechikkan va jiddiylari birinchi</span></div>
    <div class="ops-tasks">${rows.length ? rows.slice(0, OPSV.page).map((t, i) => opsTaskCard(t, i === 0)).join("") : `<div class="card"><p class="muted">Navbat bo'sh ✓</p></div>`}</div>
    ${rows.length > OPSV.page ? `<div style="text-align:center;margin-top:12px"><button class="btn" id="otMore">Yana ko'rsatish (${Math.min(30, rows.length - OPSV.page)} ta)</button></div>` : ""}`;
  if ($("#otMore")) $("#otMore").onclick = () => { OPSV.page += 30; opsTasks(); };
  $("#otRule").onchange = e => { OPSV.rule = e.target.value; OPSV.page = 30; opsTasks(); };
  if ($("#otKind")) $("#otKind").onchange = e => { OPSV.kind = e.target.value; OPSV.page = 30; opsTasks(); };
  bindTaskActions(b, () => { opsTasks(); refreshOpsSummary(); });
}
function opsTaskCard(t, openScript = false) {
  const sc = t.script || {};
  const minD = new Date().toISOString().slice(0, 10), maxD = new Date(Date.now() + 30 * 864e5).toISOString().slice(0, 10);
  const acts = !t.can_act ? "" : t.kind === "qongiroq" ? `
      <div class="ops-out"><input type="text" class="f-note" placeholder="Qisqa izoh (ixtiyoriy)" maxlength="1000" aria-label="Izoh">
      <div class="row-actions"><button class="btn sm primary" data-out="gaplashildi">Gaplashildi</button>
        <span class="vada"><input type="date" class="f-pd" min="${minD}" max="${maxD}" aria-label="Va'da sanasi"><button class="btn sm" data-out="vada">Va'da berdi</button></span>
        <button class="btn sm" data-out="javob_bermadi">Javob bermadi${t.attempts ? ` (${t.attempts}/3)` : ""}</button><button class="btn sm ghost" data-out="notogri_raqam">Noto'g'ri raqam</button></div></div>`
    : t.kind === "hujjat" ? `<div class="ops-out"><input type="text" class="f-note" placeholder="Izoh: qanday hujjat, raqami" maxlength="1000" aria-label="Izoh">
      <div class="row-actions"><button class="btn sm primary" data-out="hujjat_keldi">Hujjat keldi</button><button class="btn sm" data-out="hujjat_yoq">Hujjat yo'q</button></div></div>`
    : ["xat", "buyruq"].includes(t.kind) ? `<div class="ops-out">${t.kind === "buyruq" && t.rule === "davomat" ? `<input type="text" class="f-reason" placeholder="Sabab (bo'sh qolsa — sababsiz soatlar bo'yicha avtomatik)" maxlength="300" aria-label="Sabab">` : ""}
      <div class="row-actions"><button class="btn sm primary" data-docgen>${ico("folder", 15)} Hujjatni tayyorlash</button><span class="tiny muted">Hujjatlar markazida ro'yxat raqami va QR bilan</span></div></div>`
    : `<div class="ops-out"><input type="text" class="f-note" placeholder="Suhbat natijasi" maxlength="1000" aria-label="Izoh"><div class="row-actions"><button class="btn sm primary" data-out="bajarildi">Bajarildi</button></div></div>`;
  return `<div class="card ops-task ${t.late ? "late" : ""}" data-tid="${t.id}">
    <div class="ot-h"><span class="ot-kind">${OPS_KIND[t.kind]}</span>${lvlTag(t.level)}<span class="tiny ${t.late ? "bad" : "muted"}">muddat ${dtm(t.due_at)}${t.late ? " · kechikdi" : ""}</span></div>
    <div class="ot-title"><b>${esc(t.title)}</b></div>
    <div class="ot-st"><a href="#" data-st="${t.student_id}">${esc(t.full_name)}</a> · ${esc(t.grp)} · ${esc(t.faculty)}${t.phone ? ` · <span class="phone">${esc(t.phone)}</span>` : ""}</div>
    <div class="tiny" style="margin-top:4px">${factText(t.rule, t.facts)}</div>
    ${sc.say ? `<details class="script" ${openScript ? "open" : ""}><summary>Nima deyish kerak</summary><ol>${sc.say.map(x => `<li>${esc(x)}</li>`).join("")}</ol>
      ${sc.tone?.length ? `<div class="tiny muted"><b>Muomala:</b> ${esc(sc.tone.join(" "))}</div>` : ""}${sc.basis?.length ? `<div class="tiny muted"><b>Asos:</b> ${esc(sc.basis.join(" "))}</div>` : ""}</details>` : ""}
    ${acts}</div>`;
}
function bindTaskActions(root, after) {
  root.querySelectorAll("[data-st]").forEach(a => a.onclick = e => { e.preventDefault(); OPSV.student = +a.dataset.st; OPSV.tab = OPSV.tab || "holatlar"; opsStudent(OPSV.student); });
  root.querySelectorAll(".ops-task [data-out]").forEach(btn => btn.onclick = () => busy(btn, async () => {
    const card = btn.closest(".ops-task"), out = btn.dataset.out;
    const body = {outcome: out, note: card.querySelector(".f-note")?.value || ""};
    if (out === "vada") { body.promise_date = card.querySelector(".f-pd").value; if (!body.promise_date) return toast("Va'da sanasini tanlang"); }
    const r = await J(`/api/ops/tasks/${card.dataset.tid}/outcome`, {method: "POST", body: JSON.stringify(body)});
    toast(r.rescheduled ? `Javob bermadi — ertaga qayta (${r.attempts}/3)` : r.escalated ? "3 marta javob bermadi — tyutorga topshirildi" : out === "vada" ? `Va'da qayd etildi: ${dmy(body.promise_date)} — muddat o'tsa tizim qayta eslatadi` : "Natija saqlandi");
    after();
  }));
  root.querySelectorAll(".ops-task [data-docgen]").forEach(btn => btn.onclick = () => busy(btn, async () => {
    const card = btn.closest(".ops-task");
    const r = await J(`/api/ops/tasks/${card.dataset.tid}/document`, {method: "POST", body: JSON.stringify({reason: card.querySelector(".f-reason")?.value || ""})});
    card.querySelector(".ops-out").innerHTML = `<div class="res" style="margin-top:8px"><b>${esc(r.title)}</b> · ${esc(r.reg_no)}${r.status === "loyiha" ? " · rektor imzosini kutadi" : ""}<br>
      <a href="/api/docs/file/${encodeURIComponent(r.file)}">⬇ .docx yuklab olish</a></div>`;
    toast(`Tayyor: ${r.reg_no}`); refreshOpsSummary();
  }, "Tayyorlanmoqda…"));
}
async function refreshOpsSummary() { try { OPSV.sum = await J("/api/ops/summary"); const g = document.querySelector("#v-ops .grid.g6"); if (g) { const w = document.createElement("div"); w.innerHTML = opsSummary(OPSV.sum); g.nextElementSibling?.remove(); g.replaceWith(...w.children); $("#v-ops").querySelectorAll("[data-sr]").forEach(b => b.onclick = () => { OPSV.rule = b.dataset.sr; OPSV.tab = "holatlar"; OPSV.student = null; renderOps(); }); } badges(); } catch (e) {} }

/* --- talaba kartasi --- */
async function opsStudent(sid) {
  const b = $("#opsBody"); b.innerHTML = `<p class="muted">Yuklanmoqda…</p>`;
  const d = await J(`/api/ops/student/${sid}`);
  const s = d.student, f = d.facts;
  const back = `<button class="btn ghost sm" id="opsBack" style="margin-bottom:10px">← Ortga</button>`;
  if (d.limited) {
    b.innerHTML = back + `<div class="card"><h3>${esc(s.full_name)}</h3><p class="muted">${esc(s.grp)} · ${esc(s.faculty)} · <span class="phone">${esc(s.phone)}</span></p>
      <p class="tiny muted">Call-markaz uchun faqat qo'ng'iroq topshiriqlari ko'rinadi.</p></div><div class="ops-tasks" style="margin-top:14px">${d.tasks.map(t => opsTaskCard({...t, full_name: s.full_name, grp: s.grp, faculty: s.faculty, phone: s.phone, rule: "", facts: {}, late: t.due_at < new Date().toISOString()})).join("")}</div>`;
    $("#opsBack").onclick = () => { OPSV.student = null; renderOps(); }; bindTaskActions(b, () => opsStudent(sid)); return;
  }
  const open = d.cases.filter(c => c.status === "ochiq");
  b.innerHTML = back + `<div class="card ops-hero"><div><h3 style="margin:0">${esc(s.full_name)}</h3>
      <div class="muted tiny">${esc(s.grp)} · ${s.course}-kurs · ${esc(s.faculty)} · HEMIS ${esc(s.hemis_id)}${s.phone ? ` · <span class="phone">${esc(s.phone)}</span>` : ""} · holati: ${esc(s.status)}</div></div>
      <div class="ops-facts"><div><span>Sababsiz</span><b class="${f.unexcused >= 30 ? "bad" : ""}">${f.unexcused} soat</b></div><div><span>Sababli</span><b>${f.excused} soat</b></div>
      <div><span>JPA (5 ballik)</span><b class="${f.gpa5 < 3 ? "bad" : ""}">${f.gpa5 ?? "—"}</b></div><div><span>Qarzdor fan</span><b class="${f.fails.length ? "bad" : ""}">${f.fails.length}</b></div>
      <div><span>Kontrakt qarzi</span><b class="${d.debt > 0 ? "bad" : ""}">${s.payment_type === "kontrakt" ? som(d.debt) : "grant"}</b></div></div></div>
    <div class="dec-grid">
      <div class="dec-tasks">
        <div class="card"><h3>Ochiq holatlar (${open.length})</h3>${open.length ? open.map(c => `<div class="dec-line"><span class="dl-unit">${OPS_RULES[c.rule]}</span><span>${lvlTag(c.level)}</span><span class="tiny muted">${dtm(c.opened_at)}</span><span class="dl-res">${factText(c.rule, c.facts)}</span></div>`).join("") : `<p class="muted">Ochiq holat yo'q ✓</p>`}</div>
        <div class="card"><h3>Topshiriqlar</h3><div class="ops-tasks">${d.tasks.filter(t => t.status === "yangi").map(t => opsTaskCard({...t, full_name: s.full_name, grp: s.grp, faculty: s.faculty, phone: s.phone, rule: (d.cases.find(c => c.id === t.case_id) || {}).rule, facts: (d.cases.find(c => c.id === t.case_id) || {}).facts || {}, late: t.due_at < new Date().toISOString()})).join("") || `<p class="muted">Ochiq topshiriq yo'q</p>`}</div>
          ${d.tasks.some(t => t.status !== "yangi") ? `<details style="margin-top:10px"><summary class="tiny muted">Yopilgan topshiriqlar (${d.tasks.filter(t => t.status !== "yangi").length})</summary>${tbl(["Topshiriq", "Natija", "Sana"], d.tasks.filter(t => t.status !== "yangi").map(t => [esc(t.title), esc((t.outcome || "") + (t.note ? " — " + t.note : "") + (t.doc_reg ? " · " + t.doc_reg : "")), dtm(t.done_at)]))}</details>` : ""}</div>
        <div class="card"><h3>O'zlashtirish (joriy semestr)</h3>${tbl(["Fan", "#Ball", ""], f.grades.map(g => [esc(g.subject), `<b class="${g.score < 56 ? "bad" : ""}">${g.score}</b>`,
          g.score < 56 && d.can_retake && !d.retakes.some(r => r.subject === g.subject && ["berildi", "topshirildi"].includes(r.status)) ? `<button class="btn sm" data-rt="${esc(g.subject)}">Otrabotka varaqasi</button>` :
          (d.retakes.find(r => r.subject === g.subject) ? `<span class="tiny muted">otrabotka: ${esc(d.retakes.find(r => r.subject === g.subject).status)}</span>` : "")]))}</div>
        <div class="card"><h3>Dars qoldirishlar</h3>${tbl(["Sana", "#Soat", "Sabab", "Hujjat"], d.absences.map(a => [`${dmy(a.start)}${a.end !== a.start ? "–" + dmy(a.end) : ""}`, a.hours, OPS_REASON[a.reason] || a.reason,
          a.doc_status ? `<span class="tag ${OPS_DOC[a.doc_status][1]}">${OPS_DOC[a.doc_status][0]}</span>` : "—"]))}</div>
      </div>
      <div class="dec-side"><div class="card"><h3>${ico("history")} Tarix</h3><ol class="tl">${d.log.map(l => `<li><span class="tl-t">${dtm(l.ts)}</span><b>${esc(l.action)}</b> — ${esc(l.user_short || l.user_name)}${l.detail ? `<div class="tiny muted">${esc(l.detail)}</div>` : ""}</li>`).join("") || `<li class="muted">—</li>`}</ol></div></div>
    </div>`;
  $("#opsBack").onclick = () => { OPSV.student = null; renderOps(); };
  bindTaskActions(b, () => { opsStudent(sid); refreshOpsSummary(); });
  b.querySelectorAll("[data-rt]").forEach(x => x.onclick = () => busy(x, async () => {
    const r = await J("/api/ops/retakes", {method: "POST", body: JSON.stringify({student_id: sid, subject: x.dataset.rt})});
    toast(`Varaqa berildi: ${r.reg_no} · muddat ${dtm(r.due_at)}`); opsStudent(sid);
  }));
  hydrateIcons(b);
}

/* --- otrabotka --- */
async function opsRetakes() {
  const b = $("#opsBody");
  const rows = await J("/api/ops/retakes");
  const ST = {berildi: ["Varaqa berildi", "mid"], topshirildi: ["Tekshiruvda", "gray"], tasdiqlandi: ["Tasdiqlandi", "low"]};
  b.innerHTML = `<div class="src-note">${ico("info", 15)}<span>Varaqa tizimda QR va ro'yxat raqami bilan chiqadi. O'qituvchi imzolagan skan yuklanadi va registrator bahoni skan bilan <b>yonma-yon</b> tekshirib tasdiqlaydi.
      Skanni avtomatik o'qish (OCR) — keyingi bosqich: serverda lokal OCR hali o'rnatilmagan.</span></div>
    <div class="card" style="margin-top:12px">${tbl(["Talaba", "Fan", "Varaqa", "Muddat", "Holat", ""], rows.map(r => [`<b>${esc(r.full_name)}</b><div class="tiny muted">${esc(r.grp)}</div>`, esc(r.subject),
      esc(r.reg_no || "—"), r.status === "berildi" ? `${dtm(r.due_at)}<div class="tiny ${r.hours_left < 24 ? "bad" : "muted"}">${r.hours_left < 0 ? `${-Math.round(r.hours_left)} soat o'tdi` : `${Math.round(r.hours_left)} soat qoldi`}</div>` : dtm(r.due_at),
      `<span class="tag ${(ST[r.status] || ["", "gray"])[1]}">${(ST[r.status] || [r.status])[0]}</span>${r.status === "tasdiqlandi" ? `<div class="tiny muted">${r.score_old} → <b>${r.score_new}</b></div>` : ""}`,
      r.status === "berildi" && ["talabalar", "tyutor"].includes(ME.role_key) ? `<label class="btn sm">Skan yuklash<input type="file" accept="application/pdf,image/jpeg,image/png" data-up="${r.id}" hidden></label>` :
      r.status === "topshirildi" ? `<button class="btn sm primary" data-rv="${r.id}">Tekshirish</button>` : ""]))}</div><div id="rtReview"></div>`;
  b.querySelectorAll("[data-up]").forEach(inp => inp.onchange = async () => {
    const file = inp.files[0]; if (!file) return;
    if (file.size > 10e6) return toast("Fayl 10 MB dan katta");
    const data = await new Promise((ok, no) => { const fr = new FileReader(); fr.onload = () => ok(fr.result); fr.onerror = no; fr.readAsDataURL(file); });
    try { await J(`/api/ops/retakes/${inp.dataset.up}/upload`, {method: "POST", body: JSON.stringify({data_url: data})}); toast("Skan yuklandi — registrator tekshiradi"); opsRetakes(); refreshOpsSummary(); } catch (e) {}
  });
  b.querySelectorAll("[data-rv]").forEach(x => x.onclick = () => opsReview(rows.find(r => r.id === +x.dataset.rv)));
  hydrateIcons(b);
}
function opsReview(r) {
  const box = $("#rtReview"), canApprove = ME.role_key === "talabalar";
  box.innerHTML = `<div class="card review" style="margin-top:14px"><h3>Tekshirish: ${esc(r.full_name)} · ${esc(r.subject)} · ${esc(r.reg_no || "")}</h3>
    <div class="rv-grid"><div class="rv-scan">${/\.pdf$/.test(r.file) ? `<iframe src="/api/ops/retakes/${r.id}/file" title="Skan" sandbox></iframe>` : `<img src="/api/ops/retakes/${r.id}/file" alt="Yuklangan varaqa skani">`}</div>
    <div class="rv-form"><div class="kv"><span>Avvalgi ball</span><b>${r.score_old ?? "—"}</b><span>O'qituvchi</span><span>${esc(r.teacher || "—")}</span><span>Yuklangan</span><span>${dtm(r.submitted_at)}</span></div>
      ${canApprove ? `<label class="tiny" style="display:block;margin-top:12px">Varaqadagi ball (skanga qarab kiriting)<input id="rvScore" type="number" min="0" max="100" style="width:100%;margin-top:4px"></label>
      <p class="tiny muted">Tekshiring: o'qituvchi imzosi bor, ball va sana to'ldirilgan, ro'yxat raqami mos (${esc(r.reg_no || "")}).</p>
      <div class="row-actions"><button class="btn primary" id="rvOk">${ico("check", 16)} Tasdiqlang — baho o'tadi</button></div>
      <input id="rvNote" type="text" placeholder="Qaytarish sababi (masalan: imzo yo'q)" style="width:100%;margin-top:10px" aria-label="Qaytarish sababi"><button class="btn sm" id="rvBack" style="margin-top:6px">Qaytarish</button>`
      : `<p class="tiny muted">Bahoni registrator departamenti tasdiqlaydi.</p>`}</div></div></div>`;
  hydrateIcons(box); box.scrollIntoView({behavior: "smooth", block: "start"});
  if (!canApprove) return;
  $("#rvOk").onclick = () => busy($("#rvOk"), async () => {
    const v = $("#rvScore").value; if (v === "" || +v < 0 || +v > 100) return toast("Ballni 0–100 oralig'ida kiriting");
    await J(`/api/ops/retakes/${r.id}/approve`, {method: "POST", body: JSON.stringify({score: +v})}); toast(`Tasdiqlandi: ${r.subject} ${r.score_old} → ${v}`); opsRetakes(); refreshOpsSummary();
  });
  $("#rvBack").onclick = () => busy($("#rvBack"), async () => {
    const n = $("#rvNote").value.trim(); if (n.length < 3) return toast("Qaytarish sababini yozing");
    await J(`/api/ops/retakes/${r.id}/return`, {method: "POST", body: JSON.stringify({note: n})}); toast("Varaqa qaytarildi — yangi muddat berildi"); opsRetakes();
  });
}

/* --- qoidalar --- */
async function opsPolicy() {
  const p = await J("/api/ops/policy");
  $("#opsBody").innerHTML = `<div class="grid g2"><div class="card"><h3>Chegaralar</h3>${tbl(["Qoida", "#Qiymat", "Holat"], p.policy.map(x => [esc(x.label), x.value, x.verified ? `<span class="tag low">tasdiqlangan</span>` : `<span class="tag mid">tasdiqlanmagan</span>`]))}
      <p class="tiny muted">Qiymatlar institut nizomi asosida tasdiqlanishi kerak. Ochiq savollar: docs/talabalar-markazi.md.</p></div>
    <div class="card"><h3>Qoida → topshiriq</h3>${tbl(["Qoida", "Daraja", "Topshiriqlar (rol, muddat)"], p.matrix.map(m => [esc(m.rule), esc(m.level), `<span class="tiny">${m.tasks.map(esc).join("<br>")}</span>`]))}
      <h3 style="margin-top:14px">Kontrakt to'lov jadvali (namuna)</h3>${tbl(["To'lov", "Muddat", "#Jami ulush"], p.plan.map(x => [esc(x.label), dmy(x.due), x.cum_pct + "%"]))}</div></div>`;
}

/* ---------- reports ---------- */
const REP = [["brifing", "Rahbariyat uchun haftalik brifing", "KPI, ogohlantirishlar, topshiriqlar ijrosi", "reports"],
  ["akademik", "Akademik holat va xavf ostidagi talabalar", "Fakultet/guruh kesimi, pasaygan guruhlar, xavf ro'yxati", "academic"],
  ["moliya", "Moliyaviy holat va kontrakt tushumi", "Byudjet ijrosi, rejadan oshishlar, qarzdorlik", "finance"],
  ["ilmiy", "Ilmiy salohiyat hisoboti", "Nashrlar, kafedralar reytingi, grantlar", "science"]];
function renderReports() {
  const ok = k => ME.allow.includes("reports") && (k === "reports" || ME.allow.includes(k));
  $("#v-reports").innerHTML = `<div class="head"><div><h2>Avtomatik hisobotlar</h2><span class="muted">Word formatida, bir tugma bilan. Har bir hisobot faqat sizning ruxsatingiz doirasida tuziladi.</span></div></div>
  <div class="grid g2">${REP.map(([k, t, d, res]) => ok(res) ? `<div class="card"><h3>📄 ${t}</h3><p class="muted">${d}</p><a class="btn primary" href="/api/report/${k}" download>Yuklab olish (.docx)</a></div>` : locked(t)).join("")}</div>`;
}

/* ---------- docs ---------- */
const DOCSAMPLE = {translate: `Dear Colleagues,\n\nFollowing our recent meeting, we would like to propose extending our Memorandum of Understanding for another five years and adding a joint summer school in Data Science for 20 students from each side. Please let us know if ISFT could host the first edition in July 2027.\n\nBest regards,\nInternational Office, Partner University (sample)`,
  contract: `HAMKORLIK SHARTNOMASI\n3.2. Institut har chorakda 45 000 000 so'm miqdorida litsenziya to'lovini oldindan to'laydi.\n4.1. Pudratchi shartnomani 10 kunlik ogohlantirish bilan bir tomonlama bekor qilishi mumkin.\n5.3. Loyiha davomida yaratilgan barcha dasturiy ta'minot va ma'lumotlar Pudratchining mulki hisoblanadi.\n6.1. To'lov 5 kundan ortiq kechiktirilsa, har bir kun uchun 0,5% penya undiriladi, umumiy summa cheklanmagan.\n8.2. Nizolar Pudratchi joylashgan joydagi sudda ko'riladi.`,
  reply: `Dear ISFT team,\nWe are interested in sending 6 exchange students to your Finance programme for the spring 2027 semester. Could you confirm available courses in English and accommodation options?\nKind regards, Partner University (sample)`};
function renderDocs() {
  $("#v-docs").innerHTML = `<div class="head"><div><h2>Yozishma va shartnoma yordamchisi</h2><span class="muted">Matn institut serveridagi mahalliy AI modelida qayta ishlanadi — tashqariga yuborilmaydi.</span></div></div>
  <div class="card"><div class="row-actions" style="margin-bottom:10px">
    <button class="btn" data-m="translate">🌐 Tarjima qilish</button><button class="btn" data-m="contract">⚖️ Shartnomani tekshirish</button><button class="btn" data-m="reply">✉️ Javob loyihasi</button>
    <span class="muted tiny" style="align-self:center">Namuna: <a href="#" data-s="translate">xat</a> · <a href="#" data-s="contract">shartnoma</a> · <a href="#" data-s="reply">so'rov</a></span></div>
  <textarea id="docText">${esc(DOCSAMPLE.contract)}</textarea><div id="docRes" class="res muted">Natija shu yerda chiqadi.</div></div>`;
  document.querySelectorAll("[data-s]").forEach(a => a.onclick = e => { e.preventDefault(); $("#docText").value = DOCSAMPLE[a.dataset.s]; });
  document.querySelectorAll("[data-m]").forEach(b => b.onclick = async () => {
    const res = $("#docRes"); res.className = "res"; res.textContent = "JARVIS tahlil qilmoqda…";
    try { const r = await J("/api/doc", {method: "POST", body: JSON.stringify({text: $("#docText").value, mode: b.dataset.m})}); res.innerHTML = rich(r.result); }
    catch (e) { res.textContent = e.message === "denied" ? "Ruxsat yo'q" : "Xatolik"; }
  });
}

/* ---------- rbac ---------- */
async function renderRbac() {
  const {roles, labels} = await J("/api/rbac");
  const keys = Object.keys(labels);
  $("#v-rbac").innerHTML = `<div class="head"><div><h2>Ruxsat darajalari (RBAC)</h2><span class="muted">Har bir so'rov bajarilishidan oldin shu jadval bo'yicha tekshiriladi. Siz: <b>${esc(ME.role)}</b></span></div></div>
  <div class="card"><div class="tw"><table class="rbac"><thead><tr><th>Lavozim</th>${keys.map(k => `<th title="${esc(labels[k])}">${esc(labels[k])}</th>`).join("")}<th>Ko'lam</th></tr></thead><tbody>
  ${roles.map(r => `<tr class="${r.key === ME.role_key ? "me" : ""}"><td><b>${esc(r.title)}</b>${r.local_only ? `<br><span class="tag gray">faqat mahalliy</span>` : ""}</td>${keys.map(k =>
    r.allow.includes(k) ? (r.aggregate_only.includes(k) ? `<td class="a" title="Faqat jamlangan">Σ</td>` : `<td class="y">✓</td>`) : `<td class="x">—</td>`).join("")}<td class="tiny">${esc(r.scope)}</td></tr>`).join("")}
  </tbody></table></div><p class="tiny muted">✓ — to'liq ruxsat · Σ — faqat jamlangan (shaxsiy ma'lumotsiz) · — — ruxsat yo'q. Telegram kanalida ish haqi va kadrlar ma'lumoti hech kimga chiqmaydi.</p></div>
  <div class="card" style="margin-top:14px"><h3>Xavfsizlik tamoyillari</h3><ul>
  <li>Har bir so'rov audit jurnaliga yoziladi: kim, qachon, nimani so'ragani, ruxsat berildimi.</li>
  <li>AI modeli bazaga to'g'ridan-to'g'ri kirmaydi — faqat ruxsat tekshiruvidan o'tgan ma'lumotni ko'radi.</li>
  <li>Til modeli institut serverida ishlaydi — hech qanday ma'lumot tashqi bulutga yuborilmaydi.</li>
  <li>Lavozim o'zgarganda ruxsat bir joyda yangilanadi, eski ruxsat darhol yopiladi.</li></ul></div>`;
}

/* ---------- audit ---------- */
async function renderAudit() {
  const el = $("#v-audit"); let rows;
  try { rows = await J("/api/section/audit"); } catch (e) { if (e.message !== "denied") throw e; el.innerHTML = `<div class="head"><h2>Audit jurnali</h2></div>` + locked("Audit jurnali (faqat Rektor)"); return; }
  el.innerHTML = `<div class="head"><div><h2>Audit jurnali</h2><span class="muted">Oxirgi 50 ta so'rov · rad etilganlar qizil</span></div><button class="btn" onclick="renderAudit()">↻ Yangilash</button></div>
  <div class="card">${tbl(["Vaqt", "Foydalanuvchi", "Kanal", "Amal", "Natija", "Izoh"], rows.map(a => [`${dmy(a.ts)} ${esc(a.ts.slice(11, 16))}`, esc(a.role), esc(a.channel), esc(a.action),
    a.allowed ? `<span class="tag low">ruxsat</span>` : `<span class="tag high">rad etildi</span>`, `<span class="tiny muted">${esc(a.detail)}</span>`]))}</div>`;
}

boot().catch(() => {});

/* ---------- Hujjatlar markazi ---------- */
const DOCSTATE = {cat: null, sel: null};
const STATUS_TXT = {berilgan: "berilgan", loyiha: "imzo kutmoqda", imzolangan: "imzolangan", bekor: "bekor qilingan"};
async function renderDocuments() {
  const el = $("#v-documents");
  el.innerHTML = `<div class="head"><div><h2>Hujjatlar markazi</h2><span class="muted">Ma'lumotnoma, buyruq, qaydnoma va xatlar bazadan avtomatik to'ldiriladi · ISFT rasmiy blanki · ro'yxat raqami · QR orqali tekshirish</span></div></div><div id="docCat"></div><div id="docForm"></div><div id="docReg"></div>`;
  DOCSTATE.cat = await J("/api/docs/catalog");
  const cats = [...new Set(DOCSTATE.cat.map(t => t.cat))];
  const mine = DOCSTATE.cat.filter(t => t.allowed).length;
  /* avval lavozimga ochiq shablonlar; boshqa bo'limlarniki — ixcham, ochiladigan ro'yxatda */
  const cardHtml = t => `<div class="doc-card${t.allowed ? "" : " off"}" data-k="${esc(t.key)}" style="${t.allowed ? "" : "opacity:.5;cursor:not-allowed"}">
      <span class="ctag">${t.allowed ? (t.sign ? "rektor imzosi bilan" : "avtomatik") : "🔒 boshqa bo'lim"}</span><b>${esc(t.title)}</b><p>${esc(t.desc)}</p></div>`;
  const own = cats.map(c => [c, DOCSTATE.cat.filter(t => t.cat === c && t.allowed)]).filter(([, l]) => l.length);
  const other = DOCSTATE.cat.filter(t => !t.allowed);
  $("#docCat").innerHTML = `<p class="tiny muted">Sizning lavozimingiz uchun ${mine} ta shablon. Har bir hujjat bazadan to'ldiriladi, ro'yxat raqami va QR bilan chiqadi.</p>` +
    own.map(([c, l]) => `<div class="cat">${esc(c)}</div><div class="doc-grid">${l.map(cardHtml).join("")}</div>`).join("") +
    (other.length ? `<details style="margin-top:18px"><summary class="tiny muted" style="cursor:pointer">Boshqa bo'limlar shablonlari (${other.length}) — ular o'z mas'ullariga ochiq</summary><div class="doc-grid" style="margin-top:10px">${other.map(cardHtml).join("")}</div></details>` : "");
  el.querySelectorAll(".doc-card").forEach(c => c.onclick = () => {
    const t = DOCSTATE.cat.find(x => x.key === c.dataset.k);
    if (!t.allowed) return toast(`⛔ «${t.title}» sizning lavozimingiz uchun emas`);
    el.querySelectorAll(".doc-card").forEach(x => x.classList.toggle("sel", x === c)); docForm(t);
  });
  docRegistry();
}

function fieldHtml(p) {
  const id = `f_${p.name}`, lab = esc(p.label), dv = p.default ?? "";
  const [ty, opts] = p.type.split(":");
  if (ty === "select") return `<label>${lab}<select id="${id}">${opts.split("|").map(o => `<option value="${esc(o)}">${esc(({uz: "O'zbekcha", en: "English", ISFT: "ISFT qoplaydi", guest: "Mehmon o'zi qoplaydi"})[o] || o.replace(/_/g, " "))}</option>`).join("")}</select></label>`;
  if (ty === "date") return `<label>${lab}<input id="${id}" type="date" value="${esc(dv)}"></label>`;
  if (ty === "number") return `<label>${lab}<input id="${id}" type="number" min="1" placeholder="avtomatik (21 / pedagog 56)" value="${esc(dv)}"></label>`;
  if (ty === "textarea") return `<label class="full">${lab}<textarea id="${id}" placeholder="Har bir fikrni yangi qatordan yozing"></textarea></label>`;
  if (ty === "check") return `<label style="flex-direction:row;align-items:center;gap:8px"><input id="${id}" type="checkbox" style="width:auto"${p.name === "use_ai" ? " checked" : ""}> ${lab}</label>`;
  if (ty === "text") return `<label>${lab}<input id="${id}" value="${esc(dv)}"></label>`;
  if (ty.startsWith("student")) {
    const kinds = [["s", "Bitta talaba"]].concat(ty.includes("group") ? [["g", "Butun guruh"]] : [], ty.includes("faculty") ? [["f", "Butun fakultet"]] : []);
    return `<label class="full">${lab}<div style="display:flex;gap:8px;flex-wrap:wrap">${kinds.length > 1 ? `<select id="tKind" style="max-width:170px">${kinds.map(k => `<option value="${k[0]}">${k[1]}</option>`).join("")}</select>` : `<input type="hidden" id="tKind" value="s">`}
      <input id="tSearch" placeholder="F.I.Sh., HEMIS ID yoki guruh nomi..." style="flex:1;min-width:180px"></div><select id="${id}" size="5" style="margin-top:6px"></select></label>`;
  }
  return `<label${["task", "meeting"].includes(ty) ? ' class="full"' : ""}>${lab}${ty === "staff" ? `<input id="sSearch" placeholder="Xodim familiyasi...">` : ""}<select id="${id}"${ty === "staff" ? ' size="5"' : ""}></select></label>`;
}

async function fillSel(id, kind, q = "", extra = {}) {
  const qs = new URLSearchParams({q, ...extra});
  const rows = await J(`/api/docs/lookup/${kind}?${qs}`);
  const s = $("#" + id); if (!s) return;
  const all = {task: "★ Barcha muddati o'tgan topshiriqlar (paket)", subject: "★ Barcha fanlar (paket)"}[kind];
  s.innerHTML = (all ? `<option value="*">${all}</option>` : "") + rows.map(r => `<option value="${esc(r.id)}">${esc(r.label)}</option>`).join("") || `<option value="">— topilmadi —</option>`;
  if (s.size > 1 && s.options.length) s.selectedIndex = 0;
}

async function docForm(t) {
  const el = $("#docForm");
  el.innerHTML = `<div class="card" style="margin-top:16px"><div class="head" style="margin-bottom:10px"><div><h3 style="margin:0">${esc(t.title)}</h3><span class="tiny muted">${esc(t.desc)}</span></div>${t.sign ? `<span class="status loyiha">rektor imzosi talab qilinadi</span>` : ""}</div>
    <div class="form-grid">${t.params.map(fieldHtml).join("")}</div>
    <div style="display:flex;gap:10px;align-items:center;margin-top:14px;flex-wrap:wrap"><button class="btn primary" id="docGo">📄 Hujjatni tayyorlash</button><span id="docOut" class="tiny muted"></span></div></div>`;
  const tKind = $("#tKind");
  const reloadTarget = async () => {
    const k = tKind.value, q = $("#tSearch").value;
    $("#tSearch").style.display = k === "s" ? "" : "none";
    if (k === "s") await fillSel("f_target", "student", q); else await fillSel("f_target", k === "g" ? "group" : "faculty", q);
  };
  if (tKind) { tKind.onchange = reloadTarget; let tm; $("#tSearch").oninput = () => { clearTimeout(tm); tm = setTimeout(reloadTarget, 250); }; reloadTarget(); }
  for (const p of t.params) {
    if (["group", "department", "meeting", "task"].includes(p.type)) await fillSel("f_" + p.name, p.type);
    if (p.type === "staff") { let tm; $("#sSearch").oninput = () => { clearTimeout(tm); tm = setTimeout(() => fillSel("f_staff", "staff", $("#sSearch").value), 250); }; fillSel("f_staff", "staff"); }
  }
  el.scrollIntoView({behavior: "smooth", block: "start"});
  if ($("#f_group") && $("#f_subject")) { const r = () => fillSel("f_subject", "subject", "", {group_id: $("#f_group").value}); $("#f_group").onchange = r; r(); }
  $("#docGo").onclick = async () => {
    const params = {};
    for (const p of t.params) {
      const e = $("#f_" + p.name); if (!e) continue;
      let v = e.type === "checkbox" ? e.checked : e.value;
      if (p.name === "target") { if (!v) return toast("Talaba / guruhni tanlang"); v = `${tKind.value}:${v}`; }
      params[p.name] = v;
    }
    const btn = $("#docGo"); btn.disabled = true;
    $("#docOut").textContent = params.use_ai ? "JARVIS matnni yozmoqda (mahalliy AI, ~20–40 soniya)..." : "Tayyorlanmoqda...";
    try {
      const r = await J("/api/docs/issue", {method: "POST", body: JSON.stringify({key: t.key, params})});
      $("#docOut").innerHTML = `✅ <b>${r.count}</b> ta hujjat · ${esc(r.regs.slice(0, 3).join(", "))}${r.count > 3 ? " ..." : ""} · <span class="status ${r.status}">${STATUS_TXT[r.status]}</span>
        <a class="btn sm" href="/api/docs/file/${encodeURIComponent(r.file)}">⬇ Yuklab olish (.docx)</a>`;
      toast(r.count > 1 ? `${r.count} ta hujjat bitta paketda tayyor` : "Hujjat tayyor va ro'yxatga olindi"); docRegistry();
    } catch (e) { $("#docOut").textContent = e.message === "denied" ? "" : "Xatolik: " + String(e.message).slice(0, 160); }
    btn.disabled = false;
  };
}

async function docRegistry() {
  const rows = await J("/api/docs/registry");
  const isR = ME.role_key === "rektor";
  const wait = rows.filter(r => r.status === "loyiha").length;
  $("#docReg").innerHTML = `<div class="card" style="margin-top:16px"><div class="head" style="margin-bottom:10px"><div><h3 style="margin:0">Hujjatlar jurnali (reyestr)</h3>
    <span class="tiny muted">${isR ? "Institut bo'yicha barcha hujjatlar" : "Siz tayyorlagan hujjatlar"} · ${rows.length} ta${wait ? ` · <b class="bad">${wait} ta imzo kutmoqda</b>` : ""}</span></div></div>
    ${rows.length ? tbl(["Raqam", "Hujjat", "Kim haqida / kimga", "Muallif", "Sana", "Holat", ""], rows.map(r => [
      `<b>${esc(r.reg_no)}</b>`, esc(r.title), esc(r.holder), `<span class="tiny">${esc(r.creator_role)}</span>`, `<span class="tiny">${dmy(r.created_at)} ${esc(r.created_at.slice(11, 16))}</span>`,
      `<span class="status ${r.status}">${STATUS_TXT[r.status] || r.status}</span>`,
      `<div style="display:flex;gap:6px;flex-wrap:wrap"><a class="btn sm" title="Yuklab olish" href="/api/docs/file/${encodeURIComponent(r.file)}">⬇</a>
       <a class="btn sm" title="QR tekshiruv sahifasi" target="_blank" href="/verify/${encodeURIComponent(r.verify_code)}">🔍</a>
       ${isR && r.status === "loyiha" ? `<button class="btn sm primary" data-sign="${r.id}">✍ Imzolash</button>` : ""}
       ${r.status !== "bekor" ? `<button class="btn sm" data-cancel="${r.id}" title="Bekor qilish">✕</button>` : ""}</div>`]))
    : `<p class="muted">Hali hujjat tayyorlanmagan. Yuqoridan shablon tanlang.</p>`}</div>`;
  document.querySelectorAll("[data-sign]").forEach(b => b.onclick = () => busy(b, async () => { await J(`/api/docs/${b.dataset.sign}/sign`, {method: "POST"}); toast("Buyruq imzolandi — QR tekshiruvda «imzolangan» ko'rinadi"); docRegistry(); }));
  /* bekor qilish qaytarib bo'lmaydi — ikki bosqichli tasdiq */
  document.querySelectorAll("[data-cancel]").forEach(b => b.onclick = () => {
    if (!b.dataset.armed) { b.dataset.armed = 1; b.textContent = "Bekor qilinsinmi?"; b.classList.add("primary"); setTimeout(() => { if (b.isConnected) { delete b.dataset.armed; b.textContent = "✕"; b.classList.remove("primary"); } }, 3500); return; }
    busy(b, async () => { await J(`/api/docs/${b.dataset.cancel}/cancel`, {method: "POST"}); toast("Hujjat bekor qilindi — QR tekshiruvda «bekor» ko'rinadi"); docRegistry(); });
  });
}


/* ---------- Xizmat markazi: QR nosozliklar · murojaatlar · tadbir qatnashuvi ---------- */
const SVC = {tab: null, data: null};
const SVC_TABS = {facilities: "🔧 Nosozliklar (QR)", requests: "📨 Murojaatlar va hodisalar", events: "🎟 Tadbir qatnashuvi"};
const ago = iso => { const m = Math.max(0, Math.round((Date.now() - new Date(iso)) / 60000)); if (m < 1) return "hozir"; return m < 60 ? `${m} daq. oldin` : m < 1440 ? `${Math.round(m/60)} soat oldin` : `${Math.round(m/1440)} kun oldin`; };
const st = s => `<span class="status ${({"hal qilindi": "imzolangan", "javob berildi": "berilgan", "jarayonda": "loyiha", "ochiq": "bekor"})[s] || ""}" style="${s === "ochiq" ? "text-decoration:none" : ""}">${esc(s)}</span>`;
async function renderService() {
  const el = $("#v-service");
  el.innerHTML = `<p class="muted">Yuklanmoqda…</p>`;
  SVC.data = await J("/api/svc/overview");
  const tabs = SVC.data.tabs;
  if (!tabs.length) { el.innerHTML = `<div class="head"><div><h2>Xizmat markazi</h2></div></div>` + locked("Xizmat markazi — bu bo'lim xo'jalik, murojaatlar va tadbirlar mas'ullari uchun"); return; }
  if (!tabs.includes(SVC.tab)) SVC.tab = tabs[0];
  el.innerHTML = `<div class="head"><div><h2>Xizmat markazi</h2><span class="muted">Xodim qo'lda yig'adigan ishlar — QR va avtomatik tasniflash orqali · qarorni mas'ul xodim qabul qiladi</span></div>
    <div class="row-actions">${tabs.map(t => `<button class="btn ${t === SVC.tab ? "primary" : ""}" data-t="${t}">${SVC_TABS[t]}</button>`).join("")}</div></div><div id="svcBody"></div>`;
  el.querySelectorAll("[data-t]").forEach(b => b.onclick = () => { SVC.tab = b.dataset.t; renderService(); });
  ({facilities: svcFacilities, requests: svcRequests, events: svcEvents})[SVC.tab](SVC.data[SVC.tab]);
}
function svcFacilities(f) {
  const kp = [["Ochiq nosozliklar", f.open, `${f.rooms} ta xonada QR stiker`], ["24 soatdan oshgan", f.overdue, "javobsiz qolgan", f.overdue > 0],
              ["O'rtacha hal qilish", f.avg_hours != null ? f.avg_hours + " soat" : "—", "so'nggi 60 kun"], ["Takror xabarlar birlashtirildi", f.dup_saved, "bir muammo — bitta ish"]];
  let h = `<div class="grid g4">${kp.map(k => `<div class="card kpi ${k[3] ? "bad" : ""}"><div class="l">${k[0]}</div><div class="v">${k[1]}</div><div class="s">${k[2]}</div></div>`).join("")}</div>`;
  h += `<div class="grid g2" style="margin-top:14px">`;
  h += card("🔁 Takror buzilayotgan jihozlar <span class='muted tiny'>— 60 kunda 3+ marta</span>", f.repeat.length ? tbl(["Xona", "Jihoz", "#Marta", "#Xabarlar", "Oxirgi"], f.repeat.map(r => [esc(r.room), `<b>${esc(r.item)}</b>`, `<span class="bad">${r.n}</span>`, r.reports, ago(r.last)])) + `<p class="tiny muted">Ta'mirlash o'rniga almashtirish masalasini ko'rish tavsiya etiladi.</p>` : `<p class="muted">Yo'q</p>`);
  h += card("📱 QR qanday ishlaydi", `<ol class="tiny" style="margin:0;padding-left:18px;line-height:1.8"><li>Har xonaga QR stiker yopishtiriladi</li><li>Talaba yoki o'qituvchi skanerlaydi → xona <b>avtomatik</b> aniqlanadi</li><li>Muammo turini tanlaydi, xohlasa rasm qo'shadi — 15 soniya</li><li>Shu muammo allaqachon yozilgan bo'lsa — yangi ish ochilmaydi, «+1 tasdiq» bo'ladi</li></ol>
    <div class="row-actions" style="margin-top:10px"><a class="btn primary" href="/svc/qr-sheet" target="_blank">🖨 QR stikerlarni chop etish</a><a class="btn" href="${esc(f.tickets[0] ? "/q/" + f.tickets[0].room_code : "#")}" target="_blank">📱 Talaba sahifasini ko'rish</a></div>`);
  h += `</div>`;
  h += `<div class="card" style="margin-top:14px"><div class="head" style="margin-bottom:8px"><h3 style="margin:0">Nosozliklar navbati</h3><span class="tiny muted">${f.by_building.map(b => `${esc(b.building)}: ${b.n}`).join(" · ")}</span></div>` +
    tbl(["#", "Xona", "Jihoz / izoh", "#Xabar", "Kelgan", "Holat", "Amal"], f.tickets.slice(0, 40).map(t => [t.id, esc(t.room),
      `<b>${esc(t.item)}</b><br><span class="tiny muted">${esc(t.text)}${t.photo ? ` · <a href="/api/svc/photo/${esc(t.photo)}" target="_blank">📷 rasm</a>` : ""}</span>`,
      t.reports > 1 ? `<b>${t.reports}</b>` : 1, `<span class="${t.overdue ? "bad" : ""}">${ago(t.created_at)}</span>`, st(t.status),
      t.status === "hal qilindi" ? `<span class="tiny muted">${t.hours} soatda</span>` : `<div class="row-actions">${t.status === "yangi" ? `<button class="btn sm" data-tk="${t.id}" data-s="jarayonda">Olindi</button>` : ""}<button class="btn sm primary" data-tk="${t.id}" data-s="hal qilindi">✓ Hal qilindi</button></div>`])) + `</div>`;
  $("#svcBody").innerHTML = h;
  document.querySelectorAll("[data-tk]").forEach(b => b.onclick = () => busy(b, async () => {
    await J(`/api/svc/tickets/${b.dataset.tk}/status`, {method: "POST", body: JSON.stringify({status: b.dataset.s})}); toast("Holat yangilandi"); renderService();
  }));
}
function svcRequests(r) {
  const open = r.incidents.filter(i => i.status === "ochiq");
  const kp = [["Ochiq murojaatlar", r.open_total, r.scope], ["Faol hodisalar", open.length, open.length ? "umumiy nosozlik" : "yo'q", open.length > 0],
              ["Hodisaga birlashtirildi", r.grouped, "alohida javob shart emas"], ["Yakka ochiq murojaatlar", r.open_single, "mas'ulga yo'naltirilgan"]];
  let h = `<div class="grid g4">${kp.map(k => `<div class="card kpi ${k[3] ? "bad" : ""}"><div class="l">${k[0]}</div><div class="v">${k[1]}</div><div class="s">${esc(k[2])}</div></div>`).join("")}</div>`;
  for (const i of open) {
    h += `<div class="card" style="margin-top:14px;border-color:rgba(194,65,12,.45)"><div class="head" style="margin-bottom:6px"><div><h3 style="margin:0">🚨 ${esc(i.title)}</h3>
      <span class="tiny muted">${i.n} ta murojaat birlashtirildi · boshlandi ${ago(i.opened_at)} · oxirgisi ${ago(i.last)} · ${esc(i.category)}</span></div>${st(i.status)}</div>
      ${!r.can_broadcast ? `<p class="tiny muted">Bu umumiy hodisa — talabalarga xabarni talabalar bo'limi yuboradi. Sizning fakultetingizdan ${i.n} ta murojaat.</p>` : i.notified_at ? `<p class="tiny">✅ Talabalarga umumiy xabar yuborilgan (${ago(i.notified_at)}): <i>${esc(i.notice)}</i></p>` :
      `<p class="tiny muted">Tizim ${i.n} ta bir xil xabarni bitta hodisa deb aniqladi. Har biriga alohida javob yozish o'rniga — bitta umumiy xabar:</p>
      <textarea id="ntc${i.id}" style="min-height:90px" placeholder="Xabar loyihasi tayyorlanmoqda…"></textarea>
      <div class="row-actions" style="margin-top:8px"><button class="btn" data-ai="${i.id}">✨ AI bilan qayta yozish</button><button class="btn primary" data-send="${i.id}" disabled>📣 ${i.n} kishiga yuborish</button></div>`}
      <div class="row-actions" style="margin-top:8px">${r.can_broadcast ? `<button class="btn sm" data-res="${i.id}">✓ Hodisa hal qilindi (barchasini yopish)</button>` : ""}<button class="btn sm ghost" data-show="${i.id}">Xabarlarni ko'rish</button></div>
      <div id="incList${i.id}" class="hidden" style="margin-top:8px">${tbl(["№", "Kanal", "Matn", "Vaqt"], r.requests.filter(x => x.incident_id === i.id).map(x => [x.number, esc(x.channel), esc(x.text), ago(x.created_at)]))}</div></div>`;
  }
  h += `<div class="grid g2" style="margin-top:14px">`;
  h += card("Toifalar bo'yicha (30 kun)", bars(r.by_cat, {label: x => x.category, value: x => x.n, fmtv: (v, x) => `${v}${x.open ? ` <span class="tiny bad">(${x.open})</span>` : ""}`}) + `<p class="tiny muted">Qavsda — hali yopilmaganlari. Rahbar qaysi masala ko'p qaytayotganini ko'radi.</p>`);
  const past = r.incidents.filter(i => i.status !== "ochiq");
  h += card("Yagona murojaat oynasi", `<p class="tiny">Talaba istalgan kanaldan erkin matn yozadi — tizim toifasini va mas'ul bo'limni o'zi aniqlaydi, bir xil nosozliklarni hodisaga birlashtiradi.</p>
    <div class="row-actions"><a class="btn primary" href="/m" target="_blank">📨 Murojaat sahifasi (talaba ko'rinishi)</a></div>` +
    (past.length ? `<p class="tiny muted" style="margin-top:10px">Avvalgi hodisalar: ${past.map(i => `${esc(i.title)} — ${i.n} ta murojaat, ${ago(i.opened_at)}`).join("; ")}</p>` : ""));
  h += `</div>`;
  const singles = r.requests.filter(x => !x.incident_id).slice(0, 30);
  h += `<div class="card" style="margin-top:14px"><h3>Murojaatlar navbati</h3>` + tbl(["№", "Matn", "Toifa → mas'ul", "Kanal", "Kelgan", "Holat", "Amal"], singles.map(x => [x.number, esc(x.text),
    `<span class="ctag" style="font-size:10.5px;padding:2px 8px;border-radius:20px;background:var(--accent-soft);color:var(--accent)">${esc(x.category)}</span><br><span class="tiny muted">→ ${esc(x.unit)}</span>`,
    esc(x.channel), ago(x.created_at), st(x.status),
    ["hal qilindi", "javob berildi"].includes(x.status) ? "" : `<div class="row-actions">${x.status === "yangi" ? `<button class="btn sm" data-rq="${x.id}" data-s="jarayonda">Olindi</button>` : ""}<button class="btn sm primary" data-rq="${x.id}" data-s="hal qilindi">✓</button></div>`])) +
    `<p class="tiny muted">Toifa va mas'ul — tizim taklifi; xodim o'zgartirishi mumkin.</p></div>`;
  $("#svcBody").innerHTML = h;
  if (r.can_broadcast) for (const i of open.filter(i => !i.notified_at))
    J(`/api/svc/incidents/${i.id}/draft`, {method: "POST"}).then(j => { const t = $("#ntc" + i.id); if (t) { t.value = j.text; const s = document.querySelector(`[data-send="${i.id}"]`); if (s) s.disabled = false; } }).catch(() => {});
  document.querySelectorAll("[data-ai]").forEach(b => b.onclick = () => busy(b, async () => {
    const j = await J(`/api/svc/incidents/${b.dataset.ai}/draft?ai_=1`, {method: "POST"}); const t = $("#ntc" + b.dataset.ai); if (t) t.value = j.text;
  }, "✨ AI yozmoqda… (15–25 s)"));
  document.querySelectorAll("[data-send]").forEach(b => b.onclick = () => {
    const text = ($("#ntc" + b.dataset.send).value || "").trim();
    if (text.length < 20) return toast("Xabar matni juda qisqa");
    busy(b, async () => {
      const j = await J(`/api/svc/incidents/${b.dataset.send}/notify`, {method: "POST", body: JSON.stringify({text})});
      toast(`📣 Umumiy xabar ${j.answered} ta murojaatga javob sifatida yozildi`); renderService();
    }, "Yuborilmoqda…");
  });
  document.querySelectorAll("[data-res]").forEach(b => b.onclick = () => busy(b, async () => { const j = await J(`/api/svc/incidents/${b.dataset.res}/resolve`, {method: "POST"}); toast(`✓ Hodisa yopildi, ${j.closed} ta murojaat hal qilindi`); renderService(); }));
  document.querySelectorAll("[data-show]").forEach(b => b.onclick = () => $("#incList" + b.dataset.show).classList.toggle("hidden"));
  document.querySelectorAll("[data-rq]").forEach(b => b.onclick = () => busy(b, async () => { await J(`/api/svc/requests/${b.dataset.rq}/status`, {method: "POST", body: JSON.stringify({status: b.dataset.s})}); toast("Holat yangilandi"); renderService(); }));
}
function svcEvents(v) {
  const kp = [["O'rtacha qatnashuv", v.avg_pct != null ? v.avg_pct + "%" : "—", "ro'yxatdan o'tganlardan"], ["Doimiy qatnashchilar", v.regulars, "3+ tadbirga kelgan"],
              ["Yetib borilmagan guruhlar", v.unreached.length, "bu semestr 0 qatnashuv", v.unreached.length > 0], ["Tadbirlar (QR bilan)", v.events.length, "hisobot avtomatik"]];
  let h = `<div class="grid g4">${kp.map(k => `<div class="card kpi ${k[3] ? "bad" : ""}"><div class="l">${k[0]}</div><div class="v">${k[1]}</div><div class="s">${k[2]}</div></div>`).join("")}</div>`;
  const live = v.events.filter(e => e.open);
  for (const e of live) h += `<div class="card" style="margin-top:14px"><div class="head" style="margin-bottom:0"><div><h3 style="margin:0">🟢 Hozir: ${esc(e.title)}</h3><span class="tiny muted">${e.reg} kishi ro'yxatdan o'tgan · ${e.came} kishi belgilandi · QR ekranga chiqariladi, talaba telefonda HEMIS ID kiritadi</span></div>
    <div class="row-actions"><a class="btn primary" href="/svc/event-screen/${e.id}" target="_blank">📺 QR ekranni ochish</a><button class="btn" data-ev="${e.id}" data-a="close">Ro'yxatni yopish</button></div></div></div>`;
  h += `<div class="grid g2" style="margin-top:14px">`;
  h += card("Fakultetlar kesimida qamrov", bars(v.by_faculty, {label: x => x.faculty, value: x => x.pct, max: 100, fmtv: (p, x) => `${p}%`}) + `<p class="tiny muted">Kamida bitta tadbirga kelgan talabalar ulushi.</p>`);
  h += card("⚠️ Hali yetib borilmagan guruhlar", v.unreached.length ? tbl(["Guruh", "Fakultet", "#Talaba"], v.unreached.map(g => [`<b>${esc(g.grp)}</b>`, esc(g.faculty), g.n])) + `<p class="tiny muted">Keyingi tadbirga shu guruhlar kuratorlari orqali alohida taklif.</p>` : `<p class="muted">Barcha guruhlar qamrab olingan</p>`);
  h += `</div><div class="card" style="margin-top:14px"><h3>Tadbirlar: ro'yxat → kelganlar</h3>` + tbl(["Tadbir", "Sana", "#Ro'yxatda", "#Keldi", "#Qatnashuv", "#Ro'yxatsiz", "QR"], v.events.map(e => [esc(e.title), dmy(e.date), e.reg, e.came,
    e.pct != null ? `<span class="${e.pct < 65 ? "bad" : ""}">${e.pct}%</span>` : "—", e.walkin,
    e.open ? `<a class="btn sm" href="/svc/event-screen/${e.id}" target="_blank">📺</a>` : `<button class="btn sm" data-ev="${e.id}" data-a="open">Ochish</button>`])) + `</div>`;
  $("#svcBody").innerHTML = h;
  document.querySelectorAll("[data-ev]").forEach(b => b.onclick = () => busy(b, async () => { await J(`/api/svc/events/${b.dataset.ev}/${b.dataset.a}`, {method: "POST"}); renderService(); }));
}


/* ---------- Auditoriyalar bandligi (kamera — faqat odamlar soni) ---------- */
const SPC = {timer: null, data: null, room: null};
const SPC_STATE = {busy: ["Band", "busy"], free: ["Bo'sh", "free"], over: ["Sig'imdan oshgan", "over"], ghost: ["Dars bor — xona bo'sh", "ghost"], offline: ["Kamera javob bermayapti", "offline"]};
async function renderSpaces(silent) {
  const el = $("#v-spaces");
  if (!silent) el.innerHTML = `<p class="muted">Yuklanmoqda…</p>`;
  let o;
  try { o = SPC.data = await J("/api/spaces/overview"); }
  catch (e) { if (!silent) el.innerHTML = `<div class="head"><div><h2>Auditoriyalar bandligi</h2></div></div>` + locked("Auditoriyalar bandligi — rektor, o'quv prorektori va xo'jalik bo'limi uchun"); return; }
  const k = o.kpi;
  const kp = [["Hozir band xonalar", `${k.busy_now}/${k.rooms}`, o.slot_label], ["O'rtacha bandlik", k.util + "%", "so'nggi 4 hafta, dars vaqtida"],
              ["O'rindiqlar to'lishi", k.fill + "%", "band paytda, sig'imga nisbatan"], ["Tekshirish kerak", k.ghosts, "dars bor — xona bo'sh (2 hafta)", k.ghosts > 0],
              ["Sig'imdan oshgan xonalar", k.over_rooms, "4 hafta", k.over_rooms > 0], ["Kam ishlatiladigan", k.low_rooms, "35% dan kam band"]];
  let h = `<div class="head"><div><h2>Auditoriyalar bandligi</h2><span class="muted">Kameralar faqat <b>odamlar sonini</b> uzatadi · video saqlanmaydi · yuz aniqlash o'chirilgan · ${k.online}/${k.rooms} kamera onlayn${k.real ? ` · ${k.real} ta haqiqiy Hikvision` : " · hozircha simulyator"}</span></div>
    <span class="tag low" title="Shaxsga doir ma'lumot qayta ishlanmaydi">🔒 Shaxssiz ma'lumot</span></div>`;
  h += `<div class="grid g6">${kp.map(x => `<div class="card kpi ${x[3] ? "bad" : ""}"><div class="l">${x[0]}</div><div class="v">${x[1]}</div><div class="s">${esc(x[2])}</div></div>`).join("")}</div>`;
  // jonli xarita
  const blds = [...new Set(o.live.map(r => r.building))].sort();
  h += `<div class="card" style="margin-top:14px"><div class="head" style="margin-bottom:10px"><h3 style="margin:0">🟢 Jonli holat · ${esc(o.slot_label)}</h3>
    <span class="tiny muted">${Object.values(SPC_STATE).map(([t, c]) => `<span class="lg ${c}"></span>${t}`).join(" &nbsp; ")} · har ${o.poll_sec} s yangilanadi</span></div>
    <div class="bmap">${blds.map(b => `<div><div class="cat" style="margin:0 0 6px">${esc(b)}</div><div class="rgrid">${o.live.filter(r => r.building === b).map(r =>
      `<button class="rtile ${r.state}" data-room="${r.id}" title="${esc(SPC_STATE[r.state][0])}${r.lesson ? " · " + esc(r.lesson.group) + " · " + esc(r.lesson.subject) : ""}">
        <b>${esc(r.name)}</b><span>${r.count ?? "—"}<small>/${r.capacity}</small></span>${r.lesson ? `<i>${esc(r.lesson.group)}</i>` : `<i>${r.kind === "kompyuter sinfi" ? "kompyuter sinfi" : "&nbsp;"}</i>`}</button>`).join("")}</div></div>`).join("")}</div></div>`;
  h += `<div id="roomDay"></div>`;
  // issiqlik xaritasi
  const cell = v => v == null ? `<td class="hm">—</td>` : `<td class="hm" style="background:rgba(135,0,55,${(0.08 + v / 100 * .85).toFixed(2)});color:${v > 55 ? "#fff" : "inherit"}">${Math.round(v)}%</td>`;
  h += `<div class="grid g2" style="margin-top:14px">` + card("🗓 Hafta × para: o'rtacha to'lish", `<div class="tw"><table class="heat"><thead><tr><th></th>${o.slots.map(s => `<th>${s}</th>`).join("")}</tr></thead><tbody>${
      o.heatmap.map((row, i) => `<tr><th>${o.days[i]}</th>${row.map(cell).join("")}</tr>`).join("")}</tbody></table></div><p class="tiny muted">Xonalardagi odamlar soni ÷ sig'im. Och kataklar — bo'sh turgan sig'im: qo'shimcha guruh yoki kurs uchun zaxira.</p>`) +
    card("📉 Kam ishlatiladigan xonalar", o.low.length ? tbl(["Xona", "#Sig'im", "#Bandlik", "#Jadvalda (haftada)"], o.low.map(r => [`<a href="#" data-room="${r.id}">${esc(r.name)}</a>`, r.capacity, `<span class="bad">${r.util}%</span>`, r.scheduled_per_week])) +
      `<p class="tiny muted">Bu xonalarni boshqa maqsadga (kovorking, laboratoriya, ijara) berish yoki jadvalni zichlashtirish mumkin.</p>` : `<p class="muted">Yo'q</p>`) + `</div>`;
  h += `<div class="grid g2" style="margin-top:14px">` +
    card("⚠️ Dars bor — xona bo'sh <span class='muted tiny'>— so'nggi 2 hafta</span>", o.ghosts.length ? tbl(["Sana", "Para", "Xona", "Guruh · fan", ...(o.show_teacher ? ["O'qituvchi"] : []), "#Kishi"], o.ghosts.slice(0, 12).map(g => [
      `${g.date.slice(5)} <span class="tiny muted">${g.day.slice(0, 3)}</span>`, g.slot, esc(g.room), `${esc(g.group)}<br><span class="tiny muted">${esc(g.subject)}</span>`,
      ...(o.show_teacher ? [`${esc(g.teacher || "")}${g.repeat >= 3 ? ` <span class="tag high">${g.repeat} marta</span>` : ""}`] : []), g.avg])) +
      `<p class="tiny muted">Bu ayblov emas — signal: dars boshqa xonaga ko'chgan, bekor qilingan yoki o'tmagan bo'lishi mumkin. O'quv bo'limi tekshiradi.</p>` : `<p class="muted">Holat yo'q</p>`) +
    card("👥 Sig'imdan oshgan xonalar", o.over.length ? tbl(["Xona", "#Sig'im", "#Necha marta", "#Eng ko'p"], o.over.map(x => [esc(x.room), x.capacity, `<span class="bad">${x.n}</span>`, x.max])) +
      `<p class="tiny muted">Guruhni kattaroq xonaga ko'chirish — xavfsizlik va dars sifati uchun.</p>` : `<p class="muted">Yo'q</p>`) + `</div>`;
  // kameralar
  const realCams = o.cameras.filter(c => c.mode === "isapi");
  const camRows = o.cameras.map(c => [esc(c.room) + (c.guard ? ` <span class="tag mid" title="Ish vaqtidan tashqari kirish kuzatiladi">qo'riq</span>` : ""),
    c.mode === "isapi" ? `<b>Hikvision</b> ${esc(c.model || "")}<br><span class="tiny muted">${esc(c.scheme || "http")}://${esc(c.host)}${c.port ? ":" + c.port : ""} · kanal ${c.channel}${c.events ? " · voqealar oqimi" : ""}</span>` : `<span class="muted">Simulyator</span>`,
    `<span class="status ${c.status === "onlayn" ? "imzolangan" : c.status === "xato" ? "bekor" : "loyiha"}" style="text-decoration:none">${esc(c.status)}</span>${c.last_error ? `<br><span class="tiny bad">${esc(c.last_error)}</span>` : ""}`
      + (c.ticket_id ? `<br><span class="tiny bad">Nosozlik arizasi #${c.ticket_id} ochiq</span>` : "")
      + (c.events && c.ev_status ? `<br><span class="tiny ${String(c.ev_status).startsWith("uzildi") ? "bad" : "muted"}">voqealar: ${esc(c.ev_status)}</span>` : "")
      + (c.warnings?.length ? c.warnings.map(w => `<br><span class="tiny warn-t">⚠ ${esc(w)}</span>`).join("") : ""),
    c.last_seen ? ago(c.last_seen) : "—", c.last_count ?? "—", o.can_manage ? `<button class="btn sm" data-ctest="${c.id}">Tekshirish</button>` : ""]);
  const EVK = {chiziq_kesish: "↔", hududga_kirish: "⤓", hududdan_chiqish: "⤒", odam_soni: "👥", video_yoqoldi: "⛔", kamera_yopildi: "⛔", kamera_siljidi: "⚠", olomon: "👥"};
  const evRows = (o.events || []).map(e => [dtm(e.ts), esc(e.room), `${EVK[e.kind] || "•"} ${esc(e.label)}${e.state === "inactive" ? " (tugadi)" : ""}`, e.alert ? `<span class="tag high">${esc(e.note || "ogohlantirish")}</span>` : `<span class="tiny muted">qayd</span>`]);
  h += `<div class="card" style="margin-top:14px"><div class="head" style="margin-bottom:8px"><h3 style="margin:0">📷 Kameralar</h3>${o.can_manage ? `<button class="btn sm primary" id="camAddBtn">+ Hikvision kamerani ulash</button>` : ""}</div>
    <div id="camForm"></div>
    ${realCams.length ? tbl(["Xona", "Qurilma", "Holat", "Oxirgi signal", "#Son", ""], camRows.filter((_, i) => o.cameras[i].mode === "isapi")) : `<p class="tiny muted">Haqiqiy kamera hali ulanmagan — barcha xonalar simulyatorda.</p>`}
    <details style="margin-top:8px"><summary class="tiny muted" style="cursor:pointer">Barcha ${o.cameras.length} ta xona/kamera</summary>${tbl(["Xona", "Qurilma", "Holat", "Oxirgi signal", "#Son", ""], camRows)}</details>
    ${evRows.length ? `<h3 style="margin-top:14px">Kamera voqealari (7 kun)</h3>${tbl(["Vaqt", "Xona", "Voqea", ""], evRows)}` : ""}
    <p class="tiny muted" style="margin-top:8px">Faqat raqam va voqea turi olinadi — video, kadr va yuz tasvirlari saqlanmaydi. Ulanish: lokal tarmoq, HTTP Digest (ixtiyoriy HTTPS), ISAPI.
      Kamera ${o.poll_sec * 3} soniya javob bermasa — Xizmat markazida nosozlik arizasi avtomatik ochiladi va tiklanganda yopiladi.
      Parollar: ${o.cred_store?.encrypted ? "shifrlangan omborda" : `<span class="warn-t">bazadan ajratilgan, lekin hali shifrlanmagan (cryptography o'rnatilishi kerak)</span>`}.</p></div>`;
  el.innerHTML = h;
  el.querySelectorAll("[data-room]").forEach(b => b.onclick = ev => { ev.preventDefault(); spcRoom(+b.dataset.room); });
  el.querySelectorAll("[data-ctest]").forEach(b => b.onclick = async () => {
    b.disabled = true; b.textContent = "…";
    const j = await J(`/api/spaces/cameras/${b.dataset.ctest}/test`, {method: "POST"}).catch(() => null);
    b.disabled = false; b.textContent = "Tekshirish";
    if (j) toast(j.ok ? `✅ ${j.info}${j.count != null ? " · hozir " + j.count + " kishi" : ""}${j.warnings?.length ? " · ⚠ " + j.warnings.join("; ") : ""}` : `⚠️ ${j.error || j.info}`);
    renderSpaces(true);
  });
  const add = $("#camAddBtn"); if (add) add.onclick = () => camForm(o);
  if (SPC.room) spcRoom(SPC.room, true);
  clearInterval(SPC.timer); SPC.timer = setInterval(() => { if (!$("#v-spaces").classList.contains("hidden") && !$("#camForm")?.innerHTML) renderSpaces(true); }, Math.max(30, o.poll_sec) * 1000);
}
async function spcRoom(id, keep) {
  SPC.room = id;
  const d = await J(`/api/spaces/room/${id}`).catch(() => null); if (!d) return;
  const W = 760, H = 150, t0 = 8 * 60, t1 = 18.5 * 60, x = m => ((m - t0) / (t1 - t0) * W).toFixed(1), mx = Math.max(d.capacity, ...d.points.map(p => p.count), 1);
  const mm = s => { const t = new Date(s); return t.getHours() * 60 + t.getMinutes(); }, hmm = s => { const [a, b] = s.split(":"); return +a * 60 + +b; };
  const bands = d.lessons.map(l => `<rect x="${x(hmm(l.from))}" y="0" width="${(x(hmm(l.to)) - x(hmm(l.from))).toFixed(1)}" height="${H}" fill="var(--accent-soft)"/><text x="${(+x(hmm(l.from)) + 4)}" y="12" font-size="10" fill="var(--muted)">${esc(l.group)}</text>`).join("");
  const bw = Math.max(2, W / ((t1 - t0) / 15) - 2);
  const barsSvg = d.points.map(p => { const v = p.count, hh = v / mx * (H - 20); return `<rect x="${x(mm(p.ts))}" y="${(H - hh).toFixed(1)}" width="${bw.toFixed(1)}" height="${hh.toFixed(1)}" rx="2" fill="${v > d.capacity ? "var(--bad)" : "var(--bar)"}"><title>${p.ts.slice(11, 16)} — ${v} kishi</title></rect>`; }).join("");
  const capY = (H - d.capacity / mx * (H - 20)).toFixed(1);
  const ticks = [8, 10, 12, 14, 16, 18].map(hh => `<text x="${x(hh * 60)}" y="${H + 14}" font-size="10" fill="var(--muted)">${hh}:00</text>`).join("");
  $("#roomDay").innerHTML = `<div class="card" style="margin-top:14px"><div class="head" style="margin-bottom:8px"><div><h3 style="margin:0">${esc(d.room)} — bugungi kun</h3><span class="tiny muted">Sig'im ${d.capacity} · ${d.points.length} ta o'lchov · rangli fon — jadvaldagi darslar</span></div><button class="btn sm ghost" id="rdClose">✕</button></div>
    <svg viewBox="0 0 ${W} ${H + 18}" width="100%" height="190" preserveAspectRatio="none">${bands}${barsSvg}<line x1="0" x2="${W}" y1="${capY}" y2="${capY}" stroke="var(--bad)" stroke-dasharray="4 4" opacity=".6"/>${ticks}</svg>
    ${d.points.length ? "" : `<p class="tiny muted">Bugun hali o'lchov yo'q (yakshanba yoki ish vaqtidan oldin).</p>`}
    ${d.lessons.length ? `<p class="tiny">${d.lessons.map(l => `<b>${l.slot}-para</b> ${l.from}–${l.to}: ${esc(l.group)} · ${esc(l.subject)}`).join(" &nbsp;·&nbsp; ")}</p>` : `<p class="tiny muted">Bugun jadvalda dars yo'q.</p>`}</div>`;
  $("#rdClose").onclick = () => { SPC.room = null; $("#roomDay").innerHTML = ""; };
  if (!keep) $("#roomDay").scrollIntoView({behavior: "smooth", block: "nearest"});
}
function camForm(o) {
  const rooms = o.live.map(r => `<option value="${r.id}">${esc(r.name)}</option>`).join("");
  $("#camForm").innerHTML = `<div class="form-grid" style="margin-bottom:12px">
    <label>Xona<select id="cfRoom">${rooms}</select></label><label>Kamera IP manzili<input id="cfHost" placeholder="192.168.10.21"></label>
    <label>Kanal<input id="cfCh" type="number" value="1" min="1" max="64"></label><label>Foydalanuvchi (Operator huquqi)<input id="cfUser" placeholder="jarvis" autocomplete="off"></label>
    <label>Parol<input id="cfPass" type="password" autocomplete="new-password"></label>
    <label>Protokol<select id="cfScheme"><option value="http">HTTP (80)</option><option value="https">HTTPS (443)</option></select></label>
    <label>Port (ixtiyoriy)<input id="cfPort" type="number" min="1" max="65535" placeholder="standart"></label>
    <label class="chk-line"><input type="checkbox" id="cfEvents"> Voqealar oqimini tinglash (chiziq kesish, hududga kirish, kamera yopilishi)</label>
    <label class="chk-line"><input type="checkbox" id="cfGuard"> Ish vaqtidan tashqari (${esc(o.work_hours || "")}) kirishni kuzatish — server xonasi, laboratoriya</label>
    <label class="full"><span class="tiny muted">Parol brauzerga qaytarilmaydi va bazada saqlanmaydi (maxfiy ombor). Faqat o'qish huquqli alohida foydalanuvchi ishlating. Kamera alohida VLAN'da, internetga chiqmasligi kerak. Ketma-ket xato parol — kamera IP'ni vaqtincha bloklaydi.</span></label>
    <div class="full row-actions"><button class="btn primary" id="cfSave">Saqlash va tekshirish</button><button class="btn" id="cfCancel">Bekor qilish</button></div></div>`;
  $("#cfCancel").onclick = () => $("#camForm").innerHTML = "";
  $("#cfSave").onclick = async () => {
    const body = {room_id: +$("#cfRoom").value, mode: "isapi", host: $("#cfHost").value.trim(), channel: +$("#cfCh").value || 1, username: $("#cfUser").value.trim(), password: $("#cfPass").value,
      scheme: $("#cfScheme").value, port: +$("#cfPort").value || null, events: $("#cfEvents").checked, guard: $("#cfGuard").checked};
    let r; try { r = await J("/api/spaces/cameras", {method: "POST", body: JSON.stringify(body)}); } catch (e) { return toast("Saqlanmadi: IP manzil va maydonlarni tekshiring"); }
    $("#camForm").innerHTML = ""; toast("Saqlandi — imkoniyatlar tekshirilmoqda…");
    const j = await J(`/api/spaces/cameras/${r.id}/test`, {method: "POST"}).catch(() => null);
    if (j) toast(j.ok ? `✅ ${j.info}${j.count != null ? " · hozir " + j.count + " kishi" : ""}${j.warnings?.length ? " · ⚠ " + j.warnings.length + " ta ogohlantirish" : ""}` : `⚠️ ${j.error || j.info}`);
    renderSpaces();
  };
}
