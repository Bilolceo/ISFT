"use strict";
const $ = s => document.querySelector(s);
document.head.insertAdjacentHTML("beforeend", '<link rel="stylesheet" href="chat.css">');
document.head.insertAdjacentHTML("beforeend", '<link rel="stylesheet" href="panel.css">');
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
/* ru-RU: minglik ajratuvchi — bo'shliq, o'nlik — vergul → nuqta (avval vergul bo'shliqqa aylanib, 89,2 → «89 2» bo'lib qolardi) */
const fmt = n => typeof n === "number" ? n.toLocaleString("ru-RU").replace(/,/g, ".") : n;
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
const errCard = v => `<div class="card locked"><div class="lk-ic">${ico("alert", 22)}</div><b>Ma'lumotni yuklab bo'lmadi</b><span class="tiny">Server bilan aloqa uzildi yoki ichki xatolik</span><button class="btn sm" style="margin-top:8px" onclick="go('${v}')">${ico("refresh", 16)} Qayta urinish</button></div>`;
function toast(t) { const el = $("#toast"); el.textContent = t; el.classList.remove("hidden"); clearTimeout(toast.t); toast.t = setTimeout(() => el.classList.add("hidden"), 4200); }
/* Qaytarib bo'lmaydigan amal — ikki bosqichli tasdiq (yagona naqsh): birinchi bosishda tugma `label` holatiga o'tadi (ms davomida),
   ikkinchi bosishda asl ko'rinishi tiklanadi va true qaytadi. Ishlatish: b.onclick = () => { if (!arm(b, "Ha, imzolash")) return; busy(b, …); } */
function arm(btn, label = "Tasdiqlaysizmi?", ms = 4000) {
  if (!btn) return false;
  const reset = () => { clearTimeout(btn._armT); delete btn.dataset.armed; btn.innerHTML = btn._armOld; btn.classList.toggle("primary", !!btn._armP); btn.classList.remove("armed"); };
  if (btn.dataset.armed) { reset(); return true; }
  btn.dataset.armed = 1; btn._armOld = btn.innerHTML; btn._armP = btn.classList.contains("primary");
  btn.innerHTML = `${ico("alert", 15)}${esc(label)}`; btn.classList.add("primary", "armed"); btn.title = btn.title || "Tasdiqlash uchun yana bir marta bosing";
  btn._armT = setTimeout(() => { if (btn.isConnected && btn.dataset.armed) reset(); }, ms);
  return false;
}
/* Bekor qilish imkoniyatli bildirishnoma: `commit` ms dan keyin bajariladi; "Bekor qilish" bosilsa — bajarilmaydi (onUndo chaqiriladi) */
function undoToast(text, commit, {ms = 5000, onUndo = null} = {}) {
  let el = $("#undoToast");
  if (!el) { el = document.createElement("div"); el.id = "undoToast"; el.className = "toast undo-toast"; el.setAttribute("role", "status"); document.body.appendChild(el); }
  if (undoToast.pending) { const p = undoToast.pending; undoToast.pending = null; clearTimeout(p.t); p.commit(); }   /* oldingisi darhol bajariladi */
  const job = {commit: () => Promise.resolve().then(commit).catch(e => { if (!["auth", "denied"].includes(e?.message)) toast("Xatolik yuz berdi — qayta urinib ko'ring"); })};
  el.innerHTML = `<span>${esc(text)}</span><button class="btn sm" type="button">Bekor qilish</button>`; el.classList.remove("hidden");
  el.querySelector("button").onclick = () => { if (undoToast.pending !== job) return; clearTimeout(job.t); undoToast.pending = null; el.classList.add("hidden"); onUndo && onUndo(); };
  job.t = setTimeout(() => { if (undoToast.pending === job) { undoToast.pending = null; el.classList.add("hidden"); job.commit(); } }, ms);
  undoToast.pending = job;
}

/* ---------- ikonkalar (lucide uslubida, inline SVG) ---------- */
const ICONS = {
  /* qo'shimcha ikonkalar (emoji o'rniga) */
  spark: '<path d="M12 3l1.9 5.6L19.5 10.5l-5.6 1.9L12 18l-1.9-5.6L4.5 10.5l5.6-1.9z"/><path d="M19 3v4M17 5h4M5 17v4M3 19h4"/>',
  alert: '<path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z"/><path d="M12 9v4M12 17h.01"/>',
  bolt: '<path d="M13 2 3 14h9l-1 8 10-12h-9z"/>',
  cap: '<path d="M22 10 12 5 2 10l10 5 10-5z"/><path d="M6 12v5c3 2 9 2 12 0v-5"/>',
  money: '<rect x="2" y="6" width="20" height="12" rx="2"/><circle cx="12" cy="12" r="2.5"/><path d="M6 12h.01M18 12h.01"/>',
  pin: '<path d="M12 17v5M9 3h6l-1 6 3 3v2H7v-2l3-3z"/>',
  search: '<circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/>',
  checkc: '<circle cx="12" cy="12" r="9"/><path d="m8 12 3 3 5-6"/>',
  list: '<path d="M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01"/>',
  eye: '<path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/>',
  lock: '<rect x="4" y="11" width="16" height="10" rx="2"/><path d="M8 11V7a4 4 0 0 1 8 0v4"/>',
  unlock: '<rect x="4" y="11" width="16" height="10" rx="2"/><path d="M8 11V7a4 4 0 0 1 7.5-2"/>',
  chart: '<path d="M3 3v18h18"/><path d="m7 15 4-4 3 3 5-6"/>',
  globe: '<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3a14 14 0 0 1 0 18M12 3a14 14 0 0 0 0 18"/>',
  book: '<path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20V3H6.5A2.5 2.5 0 0 0 4 5.5z"/><path d="M4 19.5V21h16"/>',
  clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
  phone: '<path d="M22 16.9v3a2 2 0 0 1-2.2 2 19.8 19.8 0 0 1-8.6-3.1 19.5 19.5 0 0 1-6-6A19.8 19.8 0 0 1 2.1 4.2 2 2 0 0 1 4.1 2h3a2 2 0 0 1 2 1.7c.1.9.4 1.8.7 2.7a2 2 0 0 1-.5 2.1L8 9.8a16 16 0 0 0 6 6l1.3-1.3a2 2 0 0 1 2.1-.4c.9.3 1.8.6 2.7.7a2 2 0 0 1 1.7 2z"/>',
  mail: '<rect x="3" y="5" width="18" height="14" rx="2"/><path d="m3 7 9 6 9-6"/>',
  file: '<path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z"/><path d="M14 3v6h6"/>',
  user: '<circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 16 0"/>',
  users: '<circle cx="9" cy="8" r="3.5"/><path d="M2 20a7 7 0 0 1 14 0"/><path d="M16 4.5a3.5 3.5 0 0 1 0 7M22 20a7 7 0 0 0-4-6.3"/>',
  x: '<path d="M18 6 6 18M6 6l12 12"/>',
  play: '<path d="m7 4 13 8-13 8z"/>',
  refresh: '<path d="M21 12a9 9 0 1 1-3-6.7L21 8"/><path d="M21 3v5h-5"/>',
  trend_up: '<path d="m3 17 6-6 4 4 8-8"/><path d="M14 7h7v7"/>',
  trend_dn: '<path d="m3 7 6 6 4-4 8 8"/><path d="M14 17h7v-7"/>',
  qr: '<rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><path d="M14 14h3v3h-3zM20 14v.01M14 20h.01M17 20h4v-3"/>',
  flag: '<path d="M4 22V4M4 4h13l-2 4 2 4H4"/>',
  gift: '<rect x="3" y="8" width="18" height="4" rx="1"/><path d="M5 12v9h14v-9M12 8v13M12 8S10 3 7.5 4.5 9 8 12 8zm0 0s2-5 4.5-3.5S15 8 12 8z"/>',
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
  logout: '<path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><path d="m16 17 5-5-5-5"/><path d="M21 12H9"/>',
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
const LVL_TABS = {1: "Rahbariyat", 2: "Prorektorlar", 3: "Bo'limlar", 4: "Kafedralar"};
/* avatar: isft.uz'dagi rasm bo'lsa — rasm, bo'lmasa bosh harflar */
const avHtml = u => u.photo ? `<img src="${esc(u.photo)}" alt="" loading="lazy" decoding="async">` : esc(initials(u.role));
function setAv(el, u, base) { el.className = `${base} l${u.level}${u.photo ? " has-photo" : ""}`; el.innerHTML = avHtml(u); }
let USERS = [], LVL = 1;
const initials = t => { const w = String(t).replace(/[^\p{L}\s]/gu, "").split(/\s+/).filter(Boolean); return ((w[0] || "")[0] || "").toUpperCase() + ((w[1] || "")[0] || "").toUpperCase(); };
const personOf = u => u.name.includes(":") ? u.name.split(":")[1].trim() : "Demo foydalanuvchi";
async function showLogin() {
  $("#app").classList.add("hidden"); $("#login").classList.remove("hidden");
  USERS = await (await fetch("/api/users")).json();
  if (!selUser) selUser = (USERS.find(u => u.level === 1 && /^Rektor$/i.test(u.role)) || USERS[0]).id;
  LVL = (USERS.find(u => u.id === selUser) || {level: 1}).level;
  $("#lvlTabs").innerHTML = [1, 2, 3, 4].map(l => `<button type="button" role="tab" data-l="${l}">${LVL_TABS[l]}</button>`).join("");
  $("#lvlTabs").querySelectorAll("button").forEach(b => b.onclick = () => { LVL = +b.dataset.l; $("#roleSearch").value = ""; drawRoles(); $("#roleList").scrollTop = 0; });
  drawRoles(); if ($("#password") && !$("#password").value && !window.ISFT_HIDE_DEMO_HINT) $("#password").value = DEMO_PW;   /* sinov rejimi: oldindan to'ldirilgan */
  $("#loginBtn").disabled = !selUser;
}
function drawRoles() {
  $("#lvlTabs").querySelectorAll("button").forEach(b => { b.classList.toggle("on", +b.dataset.l === LVL); b.setAttribute("aria-selected", +b.dataset.l === LVL); });
  const q = ($("#roleSearch").value || "").trim().toLowerCase().replace(/[ʻʼ‘’`]/g, "'");
  if (q) $("#lvlTabs").querySelectorAll("button").forEach(b => { b.classList.remove("on"); b.setAttribute("aria-selected", false); });
  const list = USERS.filter(u => q ? (u.role + " " + personOf(u)).toLowerCase().replace(/[ʻʼ‘’`]/g, "'").includes(q) : u.level === LVL);
  const el = $("#roleList");
  el.innerHTML = list.length ? list.map(u => `<div class="role-row ${u.id === selUser ? "sel" : ""}" data-id="${u.id}" tabindex="0" role="option" aria-selected="${u.id === selUser}" title="${esc(u.role)} — ${esc(personOf(u))}">
    <span class="avatar l${u.level}${u.photo ? " has-photo" : ""}">${avHtml(u)}</span><div><b>${esc(u.role)}</b><small>${esc(personOf(u))}${q ? ` · ${LVL_TABS[u.level]}` : ""}</small></div><span class="chk">${u.id === selUser ? ico("check", 13) : ""}</span></div>`).join("")
    : `<div class="role-empty">Hech narsa topilmadi.<br>Boshqa so'z bilan qidirib ko'ring.</div>`;
  el.querySelectorAll(".role-row").forEach(r => {
    r.onclick = () => { selUser = +r.dataset.id; LVL = (USERS.find(u => u.id === selUser) || {}).level || LVL; $("#loginBtn").disabled = false; drawRoles(); };
    r.ondblclick = () => { selUser = +r.dataset.id; doLogin(); };
    r.onkeydown = e => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); r.click(); $("#password")?.focus(); } };
  });
  const fade = () => el.classList.toggle("fade", el.scrollHeight - el.scrollTop - el.clientHeight > 4);
  el.onscroll = fade; fade();
  el.querySelector(".sel")?.scrollIntoView({block: "nearest"});
}
$("#roleSearch").oninput = () => drawRoles();  /* nom orqali — variantlar drawRoles ni almashtirishi mumkin */
/* Parol: #password (type=password) · #pwEye (ko'rsatish/yashirish) · #pwWrap (xato bo'lsa .err) */
const DEMO_PW = "Isft2026";
const pwShake = () => { const w = $("#pwWrap"); if (!w) return; w.classList.remove("err"); void w.offsetWidth; w.classList.add("err"); setTimeout(() => w.classList.remove("err"), 450); };
if ($("#pwEye")) $("#pwEye").onclick = () => {
  const i = $("#password"), show = i.type === "password"; i.type = show ? "text" : "password";
  $("#pwEye").classList.toggle("on", show); $("#pwEye").setAttribute("aria-label", show ? "Parolni yashirish" : "Parolni ko'rsatish"); $("#pwEye").setAttribute("aria-pressed", show); i.focus();
};
if ($("#password")) $("#password").onkeydown = e => { if (e.key === "Enter") { e.preventDefault(); doLogin(); } };
async function doLogin() {
  if (!selUser || $("#loginBtn").dataset.busy) return;
  const password = $("#password").value;
  if (!password) { pwShake(); $("#password").focus(); return toast("Parolni kiriting"); }
  $("#loginBtn").dataset.busy = 1; $("#loginTxt").textContent = "Kirilmoqda…";
  try {
    const r = await fetch("/api/login", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({user_id: selUser, password})});
    if (!r.ok) { pwShake(); $("#password").select(); const d = await r.json().catch(() => ({})); return toast(typeof d.detail === "string" ? d.detail : "Parol noto'g'ri"); }
    await boot();
  } finally { delete $("#loginBtn").dataset.busy; $("#loginTxt").textContent = "Kirish"; }
}
$("#loginBtn").onclick = () => doLogin();
/* Chiqish — profil menyusidagi «Chiqish» (extras.js) chaqiradi */
async function doLogout() { await fetch("/api/logout", {method: "POST"}); $("#msgs").innerHTML = ""; $("#app").classList.remove("nav-open"); showLogin(); }

/* ---------- ishga tushirish ---------- */
async function boot() {
  try { ME = await J("/api/me"); } catch { return; }
  $("#login").classList.add("hidden"); $("#app").classList.remove("hidden");
  /* "Butun institut" — ortiqcha; faqat cheklangan ko'lam (fakultet, kafedra) ko'rsatiladi */
  const scopeTxt = ME.scope === "Butun institut" ? "" : ME.scope;
  $("#meName").textContent = ME.role; $("#meScope").textContent = scopeTxt; $("#meScope").hidden = !scopeTxt;
  setAv($("#meAv"), ME, "avatar");
  $("#todayChip").innerHTML = `${ico("calendar", 15)} ${dmy(ME.today)}`;
  /* ruxsati umuman yo'q bo'limlar menyuda ko'rsatilmaydi (ichkaridagi kartalar baribir 🔒 bilan himoyalangan) */
  if (typeof navLayout === "function") navLayout(ME.role_key);   /* nav.js: lavozimga ko'ra menyu tartibi */
  const NAV_HIDE_AGENTS = !(["rektor", "kengash", "kotib"].includes(ME.role_key) || ME.role_key.startsWith("prorektor_"));
  document.querySelector('#nav a[data-v="agents"]')?.classList.toggle("hidden", NAV_HIDE_AGENTS);
  const NAV_NEED = {service: ["facilities", "requests", "youth", "procurement"], spaces: ["spaces"], cams: ["spaces"], audit: ["audit"], ops: ["ops"], tasks: ["tasks"], reports: ["reports"]};
  /* tor vazifali lavozimlar uchun keraksiz bo'limlar yashiriladi (server baribir ruxsatni tekshiradi) */
  const NAV_HIDE = {call_center: ["chat", "reports", "documents", "docs", "rbac"], tyutor: ["reports", "docs"], kengash: ["cams"]};
  document.querySelectorAll("#nav a").forEach(a => { if (a.dataset.v === "agents") return; const need = NAV_NEED[a.dataset.v]; a.classList.toggle("hidden", (!!need && !need.some(x => ME.allow.includes(x))) || (NAV_HIDE[ME.role_key] || []).includes(a.dataset.v)); });
  document.querySelector('#nav a[data-v="accounts"]')?.classList.toggle("hidden", !["it_head", "rektor"].includes(ME.role_key));   /* accounts.js: AT boshlig'i (boshqaruv), rektor (ko'rish) */
  document.querySelector('#nav a[data-v="orders"]')?.classList.toggle("hidden", !["talabalar", "registrator_xodim", "sirtqi", "malumotlar_bazasi", "prorektor_oquv", "rektor", "kadrlar", "devonxona"].includes(ME.role_key));   /* orders.js: Buyruqlar — talabalar va xodimlar buyruqlari, devonxona reyestri */
  document.querySelector('#nav a[data-v="staffabs"]')?.classList.toggle("hidden", !["kadrlar", "kafedra", "akademik", "rektor", "prorektor_oquv", "oqituvchi"].includes(ME.role_key));   /* staffabs.js: xodimlar ta'tili */
  document.querySelector('#nav a[data-v="syllabus"]')?.classList.toggle("hidden", !["akademik", "kafedra", "oqituvchi", "prorektor_oquv", "rektor"].includes(ME.role_key));   /* syllabus.js: O'quv dasturlari */
  document.querySelector('#nav a[data-v="reyting"]')?.classList.toggle("hidden", !["talabalar", "registrator_xodim", "akademik", "rektor", "prorektor_oquv", "imtihon", "malumotlar_bazasi", "sirtqi", "kafedra", "tyutor", "oqituvchi", "kengash", "prorektor_ilmiy", "prorektor_moliya", "prorektor_yoshlar", "sifat"].includes(ME.role_key));   /* reyting.js: Reyting (ruxsat — app/reyting.py FULL/SCOPED/AGG) */
  document.querySelector('#nav a[data-v="flows"]')?.classList.toggle("hidden", !["talabalar", "registrator_xodim", "akademik", "imtihon", "kafedra", "sirtqi", "buxgalteriya", "rektor", "prorektor_oquv"].includes(ME.role_key));   /* flows.js: Talaba harakati (ruxsat — app/academic_flows.py TABS) */
  document.querySelector('#nav a[data-v="ilmiy"]')?.classList.toggle("hidden", !["ilmiy_bolim", "prorektor_ilmiy", "magistratura", "kafedra", "oqituvchi", "rektor", "kengash", "prorektor_oquv"].includes(ME.role_key));   /* ilmiy.js: Ilmiy faoliyat (ruxsat — app/ilmiy.py MODES) */
  document.querySelector('#nav a[data-v="xalqaro"]')?.classList.toggle("hidden", !["xalqaro", "yuridik", "rektor", "prorektor_ilmiy", "kengash", "akademik"].includes(ME.role_key));   /* xalqaro.js: Xalqaro hamkorlik (ruxsat — app/xalqaro.py TABS) */
  document.querySelector('#nav a[data-v="moliya"]')?.classList.toggle("hidden", !["buxgalteriya", "prorektor_moliya", "rektor", "kengash", "talabalar"].includes(ME.role_key));   /* moliya.js: to'lovlar, solishtirish, byudjet (ruxsat — app/moliya.py) */
  document.querySelector('#nav a[data-v="kadrlar"]')?.classList.toggle("hidden", !["kadrlar", "rektor", "kafedra"].includes(ME.role_key));   /* kadrlar.js: Kadrlar (bo'lim rahbarlari — kadrlarNav) */
  document.querySelector('#nav a[data-v="yoshlar"]')?.classList.toggle("hidden", !["prorektor_yoshlar", "manaviyat", "komendant", "tyutor", "buxgalteriya", "rektor", "talabalar"].includes(ME.role_key));   /* yoshlar.js: Yoshlar ishlari — turar joy va tadbirlar (ruxsat — app/yoshlar.py MODES) */
  if (typeof kadrlarNav === "function") kadrlarNav();
  document.querySelector('#nav a[data-v="amaliyot"]')?.classList.toggle("hidden", !["amaliyot", "kafedra", "oqituvchi", "tyutor", "talabalar", "registrator_xodim", "sirtqi", "rektor", "prorektor_oquv"].includes(ME.role_key));   /* amaliyot.js: Amaliyot (ruxsat — app/amaliyot.py mode) */
  if (typeof camsNav === "function") camsNav();   /* cams.js: navbat zonasi mas'ullari (qabul, kassa) o'z navbatini ko'radi */
  document.querySelectorAll("#nav .nav-h").forEach(h => { let n = h.nextElementSibling, any = false; while (n && n.tagName === "A") { any ||= !n.classList.contains("hidden"); n = n.nextElementSibling; } h.classList.toggle("hidden", !any); });
  status(); badges();
  go("panel");
}
/* AI holati (/api/status → ai): AIS.tools — {chat, extract, contract, translate, reply}: "ai" | "qoida" | null (mavjud emas) */
let AIS = null;
async function status() {
  const chip = $("#aiChip");
  /* «AI faol / Tahlil rejimi» belgisi — faqat tizim ma'muri (AT boshlig'i) va rektor uchun; boshqalar uchun shovqin */
  const showChip = ["it_head", "rektor"].includes(ME?.role_key);
  if (chip) chip.classList.toggle("hidden", !showChip);
  try {
    const s = await (await fetch("/api/status")).json();
    AIS = s.ai || {ai: !!s.llm, mode: s.llm ? "ai" : "tahlil", model: s.model, tools: {}};
    if (!showChip) return;
    const d = $("#llmDot"); d.className = "dot " + (AIS.ai ? "on" : "calm");
    $("#aiTxt").textContent = AIS.ai ? "AI faol" : "Tahlil rejimi";
    const tl = Object.entries(AIS.tools || {}).map(([k, v]) => `${({chat: "suhbat", extract: "bayonnoma", contract: "shartnoma", translate: "tarjima", reply: "javob xati"})[k] || k}: ${v === "ai" ? "AI" : v === "qoida" ? "qoida asosida" : "mavjud emas"}`).join(", ");
    chip.title = AIS.ai ? `AI faol: ${AIS.model || ""}${AIS.local ? " (mahalliy — ma'lumot institutdan chiqmaydi)" : ""}${tl ? ` · ${tl}` : ""}`
      : `Tahlil rejimi: til modeli ulanmagan — raqamlar va xulosalar qoidalar asosida kod bilan hisoblanadi, natijalar to'g'ri, faqat matn qisqaroq.${AIS.reason ? ` ${AIS.reason}` : ""}${tl ? ` · ${tl}` : ""}`;
    chip.setAttribute("aria-label", chip.title);
  } catch (e) {}
}
/* menyudagi raqamli belgilar — YAGONA QOIDA: «sizdan harakat kutayotgan ishlar» soni (sahifadagi soni bilan teng).
   set(view, n, tip): tip — raqam nimani sanashini tushuntiradi (sichqoncha ostida va ekran o'quvchisi uchun). */
async function badges() {
  const set = (v, n, tip = "") => {
    const a = document.querySelector(`#nav a[data-v="${v}"]`); if (!a) return; a.querySelector(".nb")?.remove();
    if (n > 0) { a.insertAdjacentHTML("beforeend", `<span class="nb" title="${esc(tip)}" aria-label="${esc(tip || n + " ta")}">${n}</span>`); }
  };
  if (ME.allow.includes("tasks")) try {
    const t = await J("/api/section/tasks"), mine = t.tasks.filter(x => x.mine && !["bajarildi", "qoralama"].includes(x.status)), late = mine.filter(x => x.overdue).length;
    set("tasks", mine.length, `Sizga yoki bo'limingizga tegishli bajarilmagan topshiriqlar: ${mine.length} ta${late ? ` (shundan ${late} tasi muddati o'tgan)` : ""}`);
  } catch (e) {}
  if (["rektor", "kotib"].includes(ME.role_key) || ME.role_key.startsWith("prorektor_")) try { const a = await J("/api/agents"), n = a.pending.filter(p => p.can_approve).length; set("agents", n, `Sizning tasdig'ingizni kutayotgan AI agent takliflari: ${n} ta`); } catch (e) {}
  /* Hujjatlar markazida imzo navbati yo'q — buyruqlar imzosi «Buyruqlar»da */
  if (typeof portalBadge === "function") portalBadge(set);   /* portal.js */
  if (typeof myworkBadge === "function") myworkBadge(set);   /* mywork.js: sahifadagi «Jami ish» */
  if (typeof moliyaBadge === "function") moliyaBadge(set);   /* moliya.js: aniqlanmagan to'lovlar / tasdiq kutayotgan xarajatlar */
  if (typeof ordersBadge === "function") ordersBadge(set);   /* orders.js: imzo / kelishuv / qaytarilgan / jurnal */
  if (ME.allow.includes("ops") && !["rektor", "kengash", "prorektor_yoshlar"].includes(ME.role_key))
    try { const o = await J("/api/ops/summary"), mine = (o.tasks.find(t => t.role === (ME.role_key === "prorektor_oquv" ? "_" : ME.role_key)) || {}); set("ops", mine.late || 0, `Talabalar markazi: navbatingizdagi kechikkan ishlar — ${mine.late || 0} ta`); } catch (e) {}
  if (ME.allow.some(a => ["facilities", "requests", "youth", "procurement"].includes(a)))
    try { const o = await J("/api/svc/overview"); set("service", o.action?.n || 0, o.action?.tip || ""); } catch (e) {}
}
document.querySelectorAll("#nav a").forEach(a => a.onclick = e => { e.preventDefault(); if (a.dataset.v === "tasks") { DEC.open = null; if (typeof DIR !== "undefined") DIR.open = null; } go(a.dataset.v); });
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
  const fn = ({panel: renderPanel, chat: renderChat, tasks: renderTasks, reports: renderReports, docs: renderDocs, documents: renderDocuments, service: renderService, ops: renderOps, spaces: renderSpaces, rbac: renderRbac, audit: renderAudit, agents: typeof renderAgents === "function" ? renderAgents : null, portal: typeof renderPortal === "function" ? renderPortal : null, cams: typeof renderCams === "function" ? renderCams : null, mywork: typeof renderMywork === "function" ? renderMywork : null, accounts: typeof renderAccounts === "function" ? renderAccounts : null, syllabus: typeof renderSyllabus === "function" ? renderSyllabus : null, staffabs: typeof renderStaffabs === "function" ? renderStaffabs : null, kadrlar: typeof renderKadrlar === "function" ? renderKadrlar : null, orders: typeof renderOrders === "function" ? renderOrders : null, reyting: typeof renderReyting === "function" ? renderReyting : null, flows: typeof renderFlows === "function" ? renderFlows : null, ilmiy: typeof renderIlmiy === "function" ? renderIlmiy : null, amaliyot: typeof renderAmaliyot === "function" ? renderAmaliyot : null, moliya: typeof renderMoliya === "function" ? renderMoliya : null, yoshlar: typeof renderYoshlar === "function" ? renderYoshlar : null})[v];
  Promise.resolve().then(fn).catch(e => { if (e?.message === "auth") return; $("#v-" + v).innerHTML = e?.message === "denied" ? locked("Bu bo'lim") : errCard(v); });
}

/* ---------- charts ---------- */
const MON = ["yan", "fev", "mar", "apr", "may", "iyn", "iyl", "avg", "sen", "okt", "noy", "dek"];
const monOf = s => MON[+String(s).slice(5, 7) - 1] || esc(s);
const sgn = (x, d = 1) => { const a = Math.abs(x).toFixed(d); return `${+a === 0 ? "" : x > 0 ? "+" : "−"}${a}`; };
/* "yana N ta" ochib-yopish: .pn-mw ichidagi .pn-x qatorlar */
function pnMore(b) {
  const xs = b.closest(".pn-mw").querySelectorAll(".pn-x"), show = xs[0]?.hidden;
  xs.forEach(x => x.hidden = !show); b.textContent = show ? "Yig'ish" : b.dataset.more;
}
const moreBtn = n => `<button class="btn ghost sm pn-more" data-more="Yana ${n} ta" onclick="pnMore(this)">Yana ${n} ta</button>`;
/* top — shuncha qatordan keyingisi "yana N ta" ortida (ixtiyoriy) */
function bars(rows, {label, value, max, fmtv = v => v, alt = false, mark = null, top = 0}) {
  const m = max ?? Math.max(...rows.map(value), 1), cut = top && rows.length > top + 1 ? top : rows.length;
  return `<div class="bars${cut < rows.length ? " pn-mw" : ""}">` + rows.map((r, i) => {
    const v = value(r), w = Math.max(0, Math.min(100, 100 * v / m));
    return `<div class="row${i >= cut ? " pn-x" : ""}"${i >= cut ? " hidden" : ""}><span title="${esc(label(r))}">${esc(label(r))}</span><div class="track"><div class="fill ${alt ? "alt" : ""}" style="width:${w}%"></div>${mark != null ? `<div class="mark" style="left:${100*mark/m}%"></div>` : ""}</div><span class="v">${fmtv(v, r)}</span></div>`;
  }).join("") + (cut < rows.length ? moreBtn(rows.length - cut) : "") + `</div>`;
}
/* 100% rejadan og'ish: chapga — tejaldi (neytral), o'ngga — oshib ketdi (qizil) */
function devBars(rows, {label, plan, actual, fmtv = mln}) {
  const d = rows.map(r => plan(r) ? 100 * (actual(r) - plan(r)) / plan(r) : 0), mx = Math.max(8, ...d.map(Math.abs));
  return `<div class="bars pn-dev">` + rows.map((r, i) => {
    const w = 50 * Math.abs(d[i]) / mx, over = d[i] > 1;
    return `<div class="row" title="${esc(label(r))}: ${fmtv(actual(r))} / reja ${fmtv(plan(r))} so'm"><span>${esc(label(r))}</span><div class="track pn-dtrack"><i class="pn-d0"></i><i class="pn-dbar${over ? " over" : ""}" style="${d[i] >= 0 ? "left" : "right"}:50%;width:${w.toFixed(1)}%"></i></div><span class="v ${over ? "bad" : "muted"}">${sgn(d[i])}%</span></div>`;
  }).join("") + `</div>`;
}
/* oylik reja va haqiqiy xarajat: ustun — rejadan og'ish (%), sichqoncha bilan — summa */
function budgetChart(months) {
  const d = months.map(m => m.planned ? 100 * (m.actual - m.planned) / m.planned : 0), mx = Math.max(6, ...d.map(Math.abs));
  return `<div class="pn-cols" role="img" aria-label="Oylik xarajatning rejadan og'ishi">` + months.map((m, i) => {
    const h = 36 * Math.abs(d[i]) / mx, over = d[i] > 1;
    return `<div class="pn-col" title="${monOf(m.month)}: ${mln(m.actual)} / reja ${mln(m.planned)} so'm (${sgn(d[i])}%)">
      <div class="pn-cbar"><i class="pn-c0"></i><i class="pn-cfill${over ? " over" : ""}" style="${d[i] >= 0 ? "bottom" : "top"}:50%;height:${h.toFixed(1)}%"></i>
      <span class="pn-cv ${over ? "bad" : ""}" style="${d[i] >= 0 ? "bottom" : "top"}:calc(50% + ${h.toFixed(1)}% + 2px)">${sgn(d[i], 0)}</span></div><span class="pn-cl">${monOf(m.month)}</span></div>`;
  }).join("") + `</div>`;
}
function spark(vals, w = 520, h = 90) {
  const mx = Math.max(...vals), mn = Math.min(...vals), dx = w / (vals.length - 1);
  const pts = vals.map((v, i) => `${(i*dx).toFixed(1)},${(h - 8 - (h - 16) * (v - mn) / ((mx - mn) || 1)).toFixed(1)}`).join(" ");
  return `<svg viewBox="0 0 ${w} ${h}" width="100%" height="${h}" preserveAspectRatio="none"><polyline fill="none" stroke="var(--bar)" stroke-width="2.5" points="${pts}"/></svg>`;
}
const card = (title, body, extra = "") => `<div class="card"><div class="head" style="margin-bottom:10px"><h3 style="margin:0">${title}</h3>${extra}</div>${body}</div>`;
const locked = (title) => `<div class="card locked"><div class="pn-lock">${ico("lock", 22)}</div><b>${esc(title)}</b><span class="tiny">Lavozimingiz uchun ruxsat yo'q</span></div>`;
/* opts.nw — qatorga bo'linmaydigan ustunlar indekslari; opts.top — shuncha qatordan keyingisi "yana N ta" ortida */
const tbl = (head, rows, {nw = [], top = 0} = {}) => {
  const cut = top && rows.length > top + 1 ? top : rows.length, cls = i => [head[i].startsWith("#") ? "n" : "", nw.includes(i) ? "nowrap" : ""].join(" ").trim();
  return `<div class="tw${cut < rows.length ? " pn-mw" : ""}"><table><thead><tr>${head.map((h, i) => `<th class="${cls(i)}">${esc(h.replace(/^#/, ""))}</th>`).join("")}</tr></thead><tbody>${rows.length ? rows.map((r, j) => `<tr${j >= cut ? ` class="pn-x" hidden` : ""}>${r.map((c, i) => `<td class="${cls(i)}">${c}</td>`).join("")}</tr>`).join("") : `<tr><td colspan="${head.length}" class="muted" style="text-align:center;padding:14px">Ma'lumot yo'q</td></tr>`}</tbody></table>${cut < rows.length ? moreBtn(rows.length - cut) : ""}</div>`;
};
const delta = d => `<span class="${d < -2 ? "bad" : d > 1 ? "good" : ""}">${d > 0 ? "+" : ""}${d}</span>`;
/* massivdagi barcha qiymatlar bir xil bo'lsa — o'sha qiymat (ustunni olib tashlash uchun) */
const same = (a, f) => a.length > 1 && a.every(x => f(x) === f(a[0])) ? f(a[0]) : null;

/* ---------- panel ---------- */
const PNL = {tab: null, kpi: false};
try { PNL.tab = localStorage.getItem("jarvis.panelTab"); } catch (e) {}
const PANEL_TABS = [["oquv", "O'quv", "cap"], ["moliya", "Moliya", "money"], ["ilmiy", "Ilmiy va xalqaro", "globe"], ["qabul", "Qabul va talabalar", "users"], ["ijro", "Ijro va kadrlar", "tasks"]];
/* asosiy qatordagi 4 ta KPI — kalit bo'yicha (yorliq o'zgarsa ham buzilmaydi); kalit bo'lmasa — yorliq bo'yicha */
const KPI_HEAD = [["talabalar", "Faol talabalar"], ["ball", "O'rtacha ball"], ["oqishda_xavf", "O'qishda xavf"], ["kontrakt", "Kontrakt tushumi"]];
function pnTab(k) {
  PNL.tab = k; try { localStorage.setItem("jarvis.panelTab", k); } catch (e) {}
  document.querySelectorAll("#v-panel .pn-tab").forEach(b => { const on = b.dataset.t === k; b.classList.toggle("on", on); b.setAttribute("aria-selected", on); if (on) b.scrollIntoView?.({block: "nearest", inline: "nearest"}); });
  document.querySelectorAll("#v-panel .pn-pane").forEach(p => p.hidden = p.dataset.t !== k);
}
function kpiState(k) {
  if (k.bad) return "bad";
  const L = String(k.label).toLowerCase(), v = parseFloat(String(k.value).replace(/\s/g, "").replace(",", ".")), pct = String(k.value).includes("%");
  if (k.trend != null && k.trend <= -2) return "bad";
  if (pct && L.includes("byudjet")) return v > 105 ? "bad" : v >= 95 && v <= 102 ? "good" : "warn";
  if (pct && L.includes("kontrakt")) return v < 70 ? "bad" : v < 85 ? "warn" : v >= 95 ? "good" : "";
  if (pct && L.includes("davomat")) return v < 80 ? "bad" : v < 85 ? "warn" : v >= 92 ? "good" : "";
  if (k.trend != null && k.trend < -0.5) return "warn";
  if (k.trend != null && k.trend > 0.5) return "good";
  return "";
}
/* ---------- KPI mini-grafiklari: qo'lda yozilgan SVG/CSS, kutubxonasiz (oflayn ishlaydi) ---------- */
const pnum = v => { const n = parseFloat(String(v ?? "").replace(/[\s ]/g, "").replace(",", ".")); return isFinite(n) ? n : null; };
const kNums = a => Array.isArray(a) ? a.map(Number).filter(isFinite) : [];
function kLine(vals) {
  const w = 120, h = 34, mx = Math.max(...vals), mn = Math.min(...vals), r = (mx - mn) || 1, dx = w / (vals.length - 1);
  const pts = vals.map((v, i) => [i * dx, h - 3 - (h - 9) * (v - mn) / r]), d = pts.map((p, i) => `${i ? "L" : "M"}${p[0].toFixed(1)} ${p[1].toFixed(1)}`).join(" ");
  return `<div class="kc-chart kc-line" aria-hidden="true"><svg viewBox="0 0 ${w} ${h}" preserveAspectRatio="none"><path class="kc-area" d="${d} L${w} ${h} L0 ${h}Z"/><path class="kc-stroke" d="${d}"/></svg><i class="kc-end" style="top:${(100 * pts[pts.length - 1][1] / h).toFixed(1)}%"></i></div>`;
}
/* ustunlar noldan boshlanadi (halol taqqoslash); hi — to'liq rangdagi ustun (-1 — hammasi bir xil) */
function kBars(vals, labels = [], hi = vals.length - 1, fmtv = v => fmt(v)) {
  const mx = Math.max(...vals, 0) || 1;
  return `<div class="kc-chart kc-bars${hi < 0 ? " flat" : ""}">${vals.map((v, i) => `<i class="${i === hi ? "on" : ""}" style="height:${Math.max(6, 100 * v / mx).toFixed(0)}%" title="${esc(labels[i] ? labels[i] + ": " : "")}${esc(fmtv(v))}"></i>`).join("")}</div>`;
}
const kRing = (pct, label) => `<div class="kc-ring" role="img" aria-label="${esc(label)}"><svg viewBox="0 0 36 36"><circle class="kc-rt" cx="18" cy="18" r="15"/><circle class="kc-rf" cx="18" cy="18" r="15" pathLength="100" stroke-dasharray="${Math.max(0, Math.min(100, pct)).toFixed(1)} 100"/></svg><b>${pct >= 10 && pct < 99.5 && Math.abs(pct - Math.round(pct)) >= .05 && pct < 20 ? pct.toFixed(1) : Math.round(pct)}%</b></div>`;
const kProg = pct => `<div class="kc-chart kc-prog" aria-hidden="true"><i style="width:${Math.max(0, Math.min(100, pct)).toFixed(1)}%"></i></div>`;
/* tarkib: "kunduzgi 8.9k · sirtqi 16.3k · masofaviy 3.7k" kabi izohdan bo'laklar */
function kParts(sub) {
  const ps = String(sub || "").split("·").map(s => s.trim().match(/^([^\d(]+?)\s+([\d.,]+)\s*(k|ming)?$/i)).filter(Boolean)
    .map(m => ({l: m[1], v: pnum(m[2]) * (m[3] ? 1000 : 1)}));
  return ps.length >= 2 ? ps : null;
}
const kStack = ps => { const t = ps.reduce((a, p) => a + p.v, 0) || 1;
  return `<div class="kc-chart kc-stack">${ps.map((p, i) => `<i class="s${i % 4}" style="flex:${(p.v / t).toFixed(3)}" title="${esc(p.l)}: ${Math.round(100 * p.v / t)}%"></i>`).join("")}</div>`; };
/* grafik: backend spark/spark_kind bersa — o'sha (ring/progress: [qism, butun]); bo'lmasa panel ma'lumotidan hosil qilinadi (raqam qo'lda yozilmaydi) */
const kTime = l => /^\d{4}(-\d{2}){0,2}$|semestr|chorak|oy$/i.test(String(l || ""));
const kLbl = l => /^\d{4}-\d{2}$/.test(l) ? monOf(l + "-01") : /^\d{4}-\d{2}-\d{2}$/.test(l) ? `${l.slice(8, 10)}.${l.slice(5, 7)}` : esc(l);
const kShare = (s, v) => s.length === 2 && s[1] ? 100 * s[0] / s[1] : v != null && v <= 100 ? v : s.length && s[s.length - 1] <= 100 ? s[s.length - 1] : null;
function kChart(k, P, K) {
  const s = kNums(k.spark), kind = k.spark_kind, v = pnum(k.value), pct = String(k.value).includes("%"), lb = Array.isArray(k.spark_labels) ? k.spark_labels : [];
  const ends = lb.length > 1 ? `<span class="kc-ends"><span>${kLbl(lb[0])}</span><span>${kLbl(lb[lb.length - 1])}</span></span>` : "";
  if (kind === "ring") { const r = kShare(s, pct ? v : null); if (r != null) return {ring: r}; }
  if (kind === "progress") { const r = kShare(s, pct ? v : null); if (r != null) return {html: kProg(r)}; }
  if (kind === "bars" && s.length > 1) {
    const time = lb.length && lb.every(kTime);
    return {html: kBars(s, lb, time ? s.length - 1 : -1) + (!time && lb.length === s.length && s.length <= 5 ? `<span class="kc-blbl">${lb.map(l => `<span>${esc(l)}</span>`).join("")}</span>` : ends)};
  }
  if (s.length > 1) return {html: kLine(s), cap: ends};
  const L = String(k.label).toLowerCase();
  if (L.includes("ball") && P.academic?.breakdown?.length > 1) {
    const b = P.academic.breakdown.slice(0, 12), g = b.map(r => r.gpa), lo = g.indexOf(Math.min(...g));
    return {html: kBars(g, b.map(r => r.name), lo), cap: `${esc(P.academic.breakdown_by)}lar kesimida · eng pasti ajratilgan`};
  }
  if (L.includes("xavf")) {
    const all = pnum(K.find(x => /faol talaba/i.test(x.label))?.value), sh = all && v != null ? 100 * v / all : pnum(String(k.sub).match(/([\d.,]+)\s*%/)?.[1]);
    if (sh != null) return {ring: sh};
  }
  if (L.includes("byudjet") && P.finance?.months?.length > 1) return {html: kLine(P.finance.months.map(m => m.actual)), cap: "oylik xarajat"};
  if (pct && v != null) return {html: kProg(v)};
  const ps = kParts(k.sub); if (ps) return {html: kStack(ps)};
  return {};
}
const kUpd = s => { if (!s) return ""; const t = String(s); if (!/^\d{4}-\d{2}-\d{2}/.test(t)) return esc(t);
  const tm = t.length > 10 ? t.slice(11, 16) : "", d = t.slice(0, 10);
  return (d === ME?.today ? "bugun" : d.slice(0, 4) === String(ME?.today || "").slice(0, 4) ? `${d.slice(8, 10)}.${d.slice(5, 7)}` : dmy(d)) + (tm ? ", " + tm : ""); };
function kpiHtml(k, P = DASH?.panels || {}, K = DASH?.kpis || []) {
  const c = kChart(k, P, K), st = kpiState(k);
  const tr = k.trend ? `<span class="trend ${k.trend < 0 ? "dn" : "up"}" title="o'tgan davrga nisbatan">${ico(k.trend < 0 ? "trend_dn" : "trend_up", 14)}${Math.abs(k.trend)}</span>` : "";
  const src = k.source || k.updated ? `<div class="kc-src" title="${esc([k.source && "Manba: " + k.source, k.updated && "yangilandi " + k.updated].filter(Boolean).join(" · "))}">${ico("server", 13)}<span>${[k.source && "Manba: " + esc(String(k.source).replace(/\s*\(.*\)\s*$/, "")), k.updated && kUpd(k.updated)].filter(Boolean).join(" · ")}</span></div>` : "";
  return `<div class="card kpi kc ${st}"${k.key ? ` data-k="${esc(k.key)}"` : ""}>
    <div class="l">${esc(k.label)}</div>
    <div class="kc-m"><div class="kc-vw"><div class="v">${esc(Number.isInteger(k.value) ? fmt(k.value) : k.value)}${tr}</div><div class="s">${esc(k.sub)}</div></div>${c.ring != null ? kRing(c.ring, `${k.label}: ulush ${Math.round(c.ring)}%`) : ""}</div>
    ${c.html ? `<div class="kc-foot">${c.html}${c.cap ? (c.cap.startsWith("<") ? c.cap : `<span class="kc-cap">${c.cap}</span>`) : ""}</div>` : ""}${src}</div>`;
}

/* ---------- panel: ISFT Core savollari + AI agent taklifi ---------- */
/* pasayish sababi bir joyda to'plangan bo'lsa — avval xulosa: "48 ta guruh — fakultet, kurs: 57.9 → 46.9" */
const pnClusters = cs => `<div class="pn-clus">${cs.slice(0, 3).map(c => `<div class="pn-cl">
  <div class="pn-cl-h"><b>${fmt(c.groups)} ta guruh</b><span>${esc(c.faculty)}${c.course ? `, ${c.course}-kurs` : ""}</span></div>
  <div class="pn-cl-v"><span class="pn-cl-n">${c.gpa_prev}</span>${ico("arrow", 14)}<span class="pn-cl-n bad">${c.gpa}</span><span class="tag high">${sgn(c.delta)}</span>${c.students ? `<span class="tiny muted">${fmt(c.students)} talaba</span>` : ""}</div>
  ${c.worst ? `<div class="tiny muted">Eng past: <b class="nowrap">${esc(c.worst.name)}</b> — ${c.worst.gpa_prev} → ${c.worst.gpa}${c.worst.attendance != null ? `, davomat ${c.worst.attendance}%` : ""}</div>` : ""}</div>`).join("")}</div>`;
function pnAsk(q) { go("chat"); setTimeout(() => { try { ask(q); } catch (e) {} }, 60); }
function pnAskHtml() {
  const qs = (SUGG[ME.role_key] || SUGG_DEF).slice(0, 4);
  return `<section class="card pn-ask" aria-label="ISFT Core'dan so'rash">
    <div class="pn-ask-h"><span class="pn-ask-av">${ico("spark", 18)}</span><div class="pn-ask-t"><b>ISFT Core</b><small>Institut ma'lumotlari bo'yicha savol bering</small></div>
      <span class="pn-ok">${ico("checkc", 14)}Raqamlar manbadan tekshiriladi</span></div>
    <button class="pn-ask-in" type="button" onclick="go('chat')">${ico("chat", 16)}<span>Savol yozing: masalan, «${esc(qs[0] || "Umumiy holat qanday?")}»</span><i>${ico("arrow", 16)}</i></button>
    <div class="pn-qs">${qs.map(q => `<button type="button" class="pn-q" data-pq="${esc(q)}">${esc(q)}</button>`).join("")}</div></section>`;
}
function pnAgentHtml(ag) {
  const ps = (ag?.pending || []), mine = ps.filter(p => p.can_approve), p = mine[0] || ps[0];
  if (!p) return "";
  const meta = typeof agPropMeta === "function" ? agPropMeta(p) : esc(p.detail || "");
  const ic = typeof agIco === "function" ? agIco(p.agent, 18) : ico("spark", 18);
  return `<section class="card pn-agent" aria-label="AI agent taklifi">
    <div class="pn-ag-h"><span class="pn-ag-ic">${ic}</span><div class="pn-ag-t"><b>AI agent · ${esc(p.agent_name)}</b><small>${p.can_approve ? "Tasdiqlashingizni kutmoqda" : "Tasdiq kutmoqda"}${typeof agTime === "function" && p.created_at ? " · " + agTime(p.created_at) : ""}</small></div>
      ${ps.length > 1 ? `<span class="pn-ag-n" title="Jami tasdiq kutayotgan takliflar">${ps.length} ta</span>` : ""}</div>
    <p class="pn-ag-title">${esc(p.title)}</p>${meta ? `<p class="pn-ag-meta">${meta}</p>` : ""}
    <div class="pn-ag-a"><button class="btn sm${p.can_approve ? " primary" : ""}" data-pag-view="${p.id}" title="Taklif tafsilotlari ochiladi — tasdiqlash o'sha oynada">${ico("eye", 16)}${p.can_approve ? "Ko'rib tasdiqlash" : "Ko'rish"}</button>
      ${ps.length > 1 ? `<button class="btn sm ghost pn-ag-all" onclick="go('agents')">Barchasi${ico("arrow", 14)}</button>` : ""}</div></section>`;
}
function pnBindHero(el) {
  el.querySelectorAll("[data-pq]").forEach(b => b.onclick = () => pnAsk(b.dataset.pq));
  /* AI taklifi paneldan to'g'ridan-to'g'ri tasdiqlanmaydi: avval AI agentlar oynasida tafsilot (preview), tasdiq — o'sha yerda ikki bosqichda */
  el.querySelectorAll("[data-pag-view]").forEach(b => b.onclick = () => {
    const id = +b.dataset.pagView;
    try { AGS.open.add(id); } catch (e) {}
    if (typeof XT !== "undefined" && XT.openLink) XT.openLink({view: "agents", action: id}); else go("agents");
  });
}
const pnH = (i, t) => `${ico(i, 16)}<span>${t}</span>`;

/* ---------- lavozim ish stollari (app/desks.py): strategik — KPI, sifat — akademik sifat, marketing — qabul, yuridik — shartnomalar ---------- */
const DESK_ICO = {strategik: "chart", sifat: "checkc", marketing: "users", yuridik: "shield"};
function deskInd(i) {
  const num = x => Number.isInteger(x) ? fmt(x) : String(x);   /* fmt ru-RU o'nlik vergulni bo'shliqqa aylantiradi — kasr sonlar o'zicha */
  const v = i.value == null ? "—" : `${typeof i.value === "number" ? num(i.value) : esc(i.value)}${i.unit && i.value != null ? i.unit : ""}`;
  const good = i.delta == null || i.delta === 0 ? "" : (i.delta > 0) === (i.good !== "down") ? "good" : "bad";
  return `<div class="card desk-i" title="${esc([i.tip, i.source && "Manba: " + i.source].filter(Boolean).join(" · "))}"><div class="l">${esc(i.label)}</div>
    <div class="v">${v}${i.delta != null && i.delta !== 0 ? `<span class="desk-d ${good}">${i.delta > 0 ? "+" : "−"}${num(Math.abs(i.delta))}</span>` : ""}</div><div class="s">${esc(i.sub || "")}</div></div>`;
}
const pctCell = (v, bad) => v == null ? "—" : `<span class="${bad ? "bad" : ""}">${v}%</span>`;
function deskHtml(d) {
  const rep = (d.reports || []).map(r => `<a class="btn sm" href="${esc(r.href)}" download>${ico("download", 15)}${esc(r.title)}</a>`).join("");
  let body = "";
  if (d.kind === "strategik") body = card("Fakultetlar kesimida", tbl(["Fakultet", "#Talaba", "#Ball", "#Davomat", "#Kontrakt", "#Ariza", "#Qabul qilindi"],
    d.by_faculty.map(f => [esc(f.name), fmt(f.n), f.gpa ?? "—", f.att == null ? "—" : f.att + "%", pctCell(f.contract, f.contract != null && f.contract < 80), fmt(f.applied ?? 0), fmt(f.enrolled ?? 0)]), {nw: [0]}));
  else if (d.kind === "sifat") {
    const row = r => [esc(r.name), fmt(r.n), r.gpa ?? "—", r.delta == null ? "—" : delta(r.delta), r.att == null ? "—" : r.att + "%", pctCell(r.below, r.below >= 5), pctCell(r.excellent)];
    const hd = x => [x, "#Talaba", "#Ball", "#O'zgarish", "#Davomat", "#O'zlashtirmagan", "#A'lochi"];
    body = `<div class="grid g2">${card("Fakultetlar kesimida", tbl(hd("Fakultet"), d.by_faculty.map(row), {nw: [0]}))}${card("Kurslar kesimida", tbl(hd("Kurs"), d.by_course.map(r => row({...r, name: r.name + "-kurs"})), {nw: [0]}))}</div>` +
      (d.syllabus?.total ? card("O'quv dasturlari (sillabuslar) holati", `<div class="ops-strip" style="margin:0">${d.syllabus.by_status.map(x => `<span class="chip-s">${esc(x.label)}: <b>${x.n}</b></span>`).join("")}${d.syllabus.overdue ? `<span class="chip-s">Muddati o'tgan: <b class="bad">${d.syllabus.overdue}</b></span>` : ""}</div>`) : "");
  } else if (d.kind === "marketing") {
    const wk = d.weekly || [];
    body = `<div class="grid g2">${card("Qabul voronkasi va haftalik dinamika", `<div class="ops-strip" style="margin:0 0 10px">${d.funnel.map(f => `<span class="chip-s">${esc(f.status)}: <b>${fmt(f.n)}</b></span>`).join("")}</div>` +
        (wk.length ? `<p class="tiny muted" style="margin:0 0 6px">Haftalik arizalar (oxirgi ${wk.length} hafta, hafta boshi)</p>` + bars(wk, {label: w => dmy(w.start), value: w => w.n, fmtv: v => fmt(v)}) : ""))}` +
      card("Yo'nalishlar: arizalar va konversiya", bars(d.by_direction, {label: r => `${r.direction} · ${r.conv ?? 0}%`, value: r => r.applied, fmtv: v => fmt(v), top: 8}) + `<p class="tiny muted">Yo'nalish · konversiya (talaba bo'lganlar ulushi) · ariza soni</p>`) + `</div>` +
      card("Fakultetlar kesimida", tbl(["Fakultet", "#Ariza", "#Talaba bo'ldi", "#Konversiya"], (d.by_faculty || []).map(f => [esc(f.name), fmt(f.applied), fmt(f.enrolled), (f.conv ?? 0) + "%"]), {nw: [0]}));
  } else if (d.kind === "yuridik") {
    const B = {otgan: ["muddati o'tgan", "gray"], "60": ["60 kun ichida", "high"], "180": ["180 kun ichida", "mid"], amalda: ["amalda", "low"]};
    const only = PNL.legalAll ? d.agreements : d.agreements.filter(a => a.need_review);
    body = card(`Shartnomalar reyestri <span class="tag ${only.length ? "mid" : "low"}">${d.agreements.filter(a => a.need_review).length} ta xulosa kutmoqda</span>`,
      `<div class="row-actions" style="margin:0 0 10px"><button class="btn sm" data-legal-all>${PNL.legalAll ? "Faqat xulosa kutayotganlar" : `Barchasi (${d.agreements.length})`}</button>
        <button class="btn sm" onclick="DOCSV.mode='contract';go('docs')">${ico("search", 15)}Shartnoma matnini tekshirish</button></div>` +
      (only.length ? `<div class="desk-legal">${only.map(a => `<div class="dl-row${a.need_review ? " need" : ""}" data-pid="${a.id}">
        <div class="dl-main"><b>${esc(a.name)}</b><span class="tiny muted">${esc(a.kind)} · imzolangan ${dmy(a.signed)} · tugaydi ${dmy(a.expires)}</span>
          <span class="tiny"><span class="tag ${B[a.bucket][1]}">${a.days_left < 0 ? B.otgan[0] : a.days_left + " kun qoldi"}</span>${a.review ? ` <span class="muted">Xulosa: ${esc(a.review.label)}${a.review.note ? ` — «${esc(a.review.note)}»` : ""} · ${dmy(a.review.at)}</span>` : ` <span class="muted">yuridik xulosa yo'q</span>`}</span></div>
        <div class="dl-act"><select class="sel-sm" aria-label="Xulosa">${Object.entries(d.statuses).map(([k, v]) => `<option value="${k}">${esc(v)}</option>`).join("")}</select>
          <input class="dl-note" maxlength="600" placeholder="Izoh (e'tiroz yoki tugatishda majburiy)" aria-label="Izoh"><button class="btn sm primary" data-legal>Saqlash</button></div></div>`).join("")}</div>`
        : `<p class="muted">${ico("checkc", 16)} Xulosa kutayotgan shartnoma yo'q</p>`));
  }
  return `<section class="desk desk-${d.kind}" aria-label="${esc(d.title)}"><div class="desk-h"><h3 class="pn-h">${pnH(DESK_ICO[d.kind] || "chart", esc(d.title))}</h3><div class="row-actions">${rep}</div></div>
    <div class="grid g3 desk-inds">${d.indicators.map(deskInd).join("")}</div>${body}
    ${d.note ? `<details class="pg-info"><summary>${ico("info", 14)}Ma'lumot manbasi va cheklovlar</summary><p class="tiny muted">${esc(d.note)}</p></details>` : ""}</section>`;
}
function deskBind(el, d) {
  el.querySelector("[data-legal-all]")?.addEventListener("click", () => { PNL.legalAll = !PNL.legalAll; renderPanel(); });
  el.querySelectorAll("[data-legal]").forEach(b => b.onclick = () => busy(b, async () => {
    const row = b.closest("[data-pid]"), st = row.querySelector("select").value, note = row.querySelector(".dl-note").value.trim();
    if (["etiroz", "tugatish"].includes(st) && note.length < 5) { toast("E'tiroz yoki tugatish uchun izoh yozing"); row.querySelector(".dl-note").focus(); return; }
    await J(`/api/desk/legal/${row.dataset.pid}`, {method: "POST", body: JSON.stringify({status: st, note})});
    toast("Yuridik xulosa saqlandi"); renderPanel();
  }));
}
/* yuklanish skeleti — «Yuklanmoqda…» o'rniga sahifa shakli (sekin so'rovlarda ham joy sakramaydi) */
const skelCard = (lines = 3, cls = "") => `<div class="card skel-card ${cls}" aria-hidden="true"><i class="skel skel-h"></i>${Array.from({length: lines}, (_, i) => `<i class="skel" style="width:${92 - i * 14}%"></i>`).join("")}</div>`;
const skelPanel = () => `<div class="head pn-head"><div><h2>Assalomu alaykum, ${esc(ME.greet || ME.role)}</h2><span class="muted">${dmy(ME.today)} · ma'lumot yuklanmoqda…</span></div></div>
  <div class="grid g4 pn-kpis" role="status" aria-label="Ko'rsatkichlar yuklanmoqda">${skelCard(2, "skel-kpi").repeat(4)}</div><div class="grid g2" style="margin-top:14px">${skelCard(4)}${skelCard(4)}</div>`;
const DESK_ROLES = ["strategik", "sifat", "marketing", "yuridik"];   /* app/desks.py — lavozim ish stoli panelda */
async function renderPanel() {
  const el = $("#v-panel"); el.innerHTML = skelPanel();
  const full = !(ME.level >= 3 || ME.role_key === "kotib"), safe = p => Promise.resolve(p).catch(() => null);
  const desk = DESK_ROLES.includes(ME.role_key);
  const [dash, briefH, decL, opsS, agD, deskD, mw] = await Promise.all([J("/api/dashboard"),
    typeof briefCardHtml === "function" ? safe(briefCardHtml()) : "",
    full && ME.level <= 2 ? safe(J("/api/dec/list")) : null,
    ME.allow.includes("ops") ? safe(J("/api/ops/summary")) : null,
    full ? safe(J("/api/agents")) : null,
    desk ? safe(J("/api/desk")) : null,
    full ? null : safe(J("/api/mywork"))]);
  DASH = dash;
  const P = DASH.panels, L = ME.labels;
  let h = `<div class="head pn-head"><div><h2>Assalomu alaykum, ${esc(ME.greet || ME.role)}</h2><span class="muted">${ME.scope === "Butun institut" ? "" : esc(ME.scope) + " · "}${dmy(ME.today)} · ma'lumot institut serveridan</span></div></div>`;

  /* --- KPI: 4 ta asosiy + qolgani yig'ilgan --- */
  const K = DASH.kpis, head = KPI_HEAD.map(([key, l]) => K.find(k => k.key === key) || K.find(k => !k.key && k.label === l)).filter(Boolean);
  K.forEach(k => { if (head.length < 4 && !head.includes(k)) head.push(k); });
  const rest = K.filter(k => !head.includes(k));
  const kh = k => kpiHtml(k, P, K);
  if (deskD && deskD.kind) h += deskHtml(deskD);
  else h += `<div class="grid g4 pn-kpis">${head.map(kh).join("")}</div>`;
  if (rest.length && !(deskD && deskD.kind)) h += `<details class="pn-kmore"${PNL.kpi ? " open" : ""} ontoggle="PNL.kpi=this.open"><summary>${ico("chart", 16)}<span>Barcha ko'rsatkichlar</span><span class="muted">+${rest.length}</span></summary><div class="grid g4 pn-kpis">${rest.map(kh).join("")}</div></details>`;

  /* --- ISFT Core savollari + eng yuqoridagi AI agent taklifi (login sahifasidagi va'da) --- */
  const agH = pnAgentHtml(agD);
  h += `<div class="pn-hero${agH ? "" : " solo"}">${pnAskHtml()}${agH}</div>`;

  /* --- ops (Talabalar markazi) va majlis qarorlari kartalari --- */
  let opsCard = "", decCard = "", crit = 0;
  if (opsS) {
    const o = opsS, by = {}; o.by_rule.forEach(r => { by[r.rule] = (by[r.rule] || 0) + r.n; });
    crit = o.by_rule.filter(r => r.level >= 2).reduce((a, r) => a + r.n, 0);
    const late = o.tasks.reduce((a, t) => a + (t.late || 0), 0), open = o.tasks.reduce((a, t) => a + t.n, 0);
    opsCard = `<div class="card"><div class="head" style="margin-bottom:8px"><h3 style="margin:0" class="pn-h">${pnH("cap", "Talabalar markazi")}</h3><button class="btn sm" onclick="OPSV.student=null;go('ops')">Ochish →</button></div>
      <div class="ops-strip" style="margin:0"><span class="chip-s" title="Ochiq holatlar: ${fmt(crit)} ta kritik/jiddiy (bitta talabada bir nechta bo'lishi mumkin)">O'qishda xavf (talaba): <b class="bad">${fmt(o.serious_students ?? crit)}</b></span>${Object.entries(OPS_RULES).map(([k, v]) => by[k] ? `<span class="chip-s">${v}: <b>${by[k]}</b></span>` : "").join("")}
      <span class="chip-s">Ochiq topshiriqlar: <b>${open}</b>${late ? ` · <span class="bad">${late} kechikkan</span>` : ""}</span><span class="chip-s">7 kunda yopildi: <b>${o.closed_7d}</b></span></div>
      ${["rektor", "kengash"].includes(ME.role_key) ? `<p class="tiny muted pn-note">${ico("shield", 14)}<span>Rahbariyat uchun faqat jamlangan raqamlar — talabalar ro'yxati registrator va tyutorlarda.</span></p>` : ""}</div>`;
  }
  if (decL && P.tasks) {
    const ds = decL.decisions.filter(d => d.status !== "qoralama").slice(0, 3);
    if (ds.length) decCard = `<div class="card"><div class="head" style="margin-bottom:6px"><h3 style="margin:0" class="pn-h">${pnH("pin", "Majlis qarorlari ijrosi")}</h3><button class="btn sm" onclick="DEC.open=null;go('tasks')">Barchasi →</button></div>
      <p class="tiny muted" style="margin:0 0 8px">Mas'ul, holat va natija — ijrochi kiritgan topshiriqning o'zidan.</p><div class="dec-list">${ds.map(decRow).join("")}</div></div>`;
  }

  /* --- asosiy amallar qatori --- */
  const brief = briefH || "", high = DASH.alerts.filter(a => a.level === "high").length;
  const pend = typeof briefCardHtml === "function" && briefCardHtml.last ? briefCardHtml.last.pending : +((brief.match(/Tasdiqlash kutilmoqda:\s*<b>(\d+)/) || [])[1] || 0);
  if (full) {
    const acts = [];
    if (pend) acts.push(`<button class="pn-act warn" onclick="go('agents')">${ico("checkc", 16)}<span>Tasdiqlash kutilmoqda</span><b>${pend}</b></button>`);
    if (P.tasks) {
      const openT = P.tasks.tasks.filter(t => t.status !== "bajarildi").length;
      acts.push(`<button class="pn-act${P.tasks.overdue ? " bad" : ""}" onclick="DEC.open=null;go('tasks')">${ico("tasks", 16)}<span>Topshiriqlar</span><b>${openT}</b>${P.tasks.overdue ? `<em>${P.tasks.overdue} muddati o'tgan</em>` : ""}</button>`);
    }
    /* Talabalar markazi: rahbar uchun signal — ijrochilar muddatida bajarmagan vazifalar (qizil faqat shunda);
       minglab "kritik" holatlar ro'yxati emas (ular tyutor va registrator ishida) */
    if (opsS) {
      const lateT = (opsS.tasks || []).reduce((a, t) => a + (t.late || 0), 0), ser = opsS.serious_students;
      acts.push(`<button class="pn-act${lateT ? " bad" : ""}" onclick="OPSV.student=null;go('ops')" title="Talabalar markazi: ijrochilar muddatida bajarmagan vazifalar. Jiddiy holatdagi talabalar bilan tyutor va Registrator ofisi ishlamoqda.">${ico("cap", 16)}<span>Talabalar markazi: kechikkan vazifalar</span><b>${lateT ? fmt(lateT) : "✓"}</b>${ser != null ? `<em class="n">o'qishda xavf: ${fmt(ser)} talaba</em>` : ""}</button>`);
    }
    const camK = ME.allow.includes("spaces") && DASH.kpis.find(k => k.key === "kameralar");   /* cams.js — Kameralar va xavfsizlik */
    if (camK) acts.push(`<button class="pn-act cm-pa${camK.bad ? " bad" : ""}" onclick="go('cams')" title="${esc(camK.sub || "")}">${ico("cctv", 16)}<span>Kameralar: P1/P2 bugun</span><b>${fmt(camK.value)}</b>${(camK.offline ?? +(String(camK.sub).match(/(\d+) kamera oflayn/) || [])[1]) ? `<em>${camK.offline ?? String(camK.sub).match(/(\d+) kamera oflayn/)[1]} kamera oflayn</em>` : ""}</button>`);
    if (DASH.alerts.length) acts.push(`<button class="pn-act${high ? " bad" : ""}" onclick="const d=document.getElementById('pnAlerts');d.open=true;d.scrollIntoView({behavior:'smooth',block:'start'})" title="Yuqori darajadagi ogohlantirishlar; jami ${DASH.alerts.length} ta">${ico("bolt", 16)}<span>${high ? "Muhim ogohlantirishlar" : "Ogohlantirishlar"}</span><b>${high || DASH.alerts.length}</b>${high ? `<em class="n">jami ${DASH.alerts.length}</em>` : ""}</button>`);
    if (acts.length) h += `<div class="pn-acts">${acts.join("")}</div>`;
  }
  h += brief;

  /* --- barcha ogohlantirishlar: yig'ilgan (brifing ularning eng muhimini ko'rsatadi) --- */
  if (DASH.alerts.length) {
    const T = {high: "Yuqori", mid: "O'rta", low: "Past"}, mid = DASH.alerts.filter(a => a.level === "mid").length;
    h += `<details class="card pn-alerts" id="pnAlerts"${brief || DASH.alerts.length > 6 ? "" : " open"}><summary>${ico("bolt", 16)}<span class="pn-st">Barcha ogohlantirishlar (${DASH.alerts.length})</span>
      <span class="pn-tags">${high ? `<span class="tag high">${high} yuqori</span>` : ""}${mid ? `<span class="tag mid">${mid} o'rta</span>` : ""}</span></summary>
      <p class="tiny muted" style="margin:0 0 10px">ISFT Core chorak yakunini kutmasdan aniqlagan holatlar.</p><div class="alerts">` +
      DASH.alerts.map(a => `<div class="alert"><span class="tag ${a.level}">${T[a.level]}</span><span><b>${esc(a.area)}:</b> ${esc(a.text)}</span></div>`).join("") + `</div></details>`;
  }

  /* --- kartalar: [tab, html] yoki [tab, null, bo'lim nomi] (yopiq) --- */
  const cards = [], add = (t, html) => cards.push({t, html}), lock = (t, name) => cards.push({t, html: locked(name), locked: name});
  if (P.mygroups) add("oquv", card("Mening guruhlarim", tbl(["Guruh", "Fan", "#Talaba", "#Oraliq (o'rt., 30)", "#Guruh o'tgan sem. (100)", "#Oraliq < 12"], P.mygroups.map(g => [esc(g.grp), esc(g.subject), g.n, g.avg_score ?? "—", g.prev_score ?? "—", g.failing ? `<span class="bad">${g.failing}</span>` : 0]), {nw: [0], top: 8})));
  if (P.academic) {
    const a = P.academic, dg = a.declining_groups, fac = same(dg, g => g.faculty), kurs = same(dg, g => g.course);
    const hd = ["Guruh", ...(fac == null ? ["Fakultet"] : []), ...(kurs == null ? ["#Kurs"] : []), "#Ball", "#O'zgarish", "#Davomat"];
    add("oquv", card(`O'zlashtirish: ${esc(a.breakdown_by)}lar kesimida`, bars(a.breakdown.length > 12 ? [...a.breakdown].sort((x, y) => x.gpa - y.gpa) : a.breakdown, {top: 10, label: r => r.name, value: r => r.gpa, max: 100, mark: 50, fmtv: (v, r) => `${v}${r.delta <= -2 ? `<span class="bad pn-dn" title="${r.delta}">${ico("trend_dn", 12)}</span>` : ""}`}) +
      (a.breakdown.length > 12 ? `<p class="tiny muted" style="margin:4px 0 0">Eng past natijali ${esc(a.breakdown_by)}lar birinchi.</p>` : "") + `<p class="tiny muted">Chiziq — «4» (yaxshi) baho chegarasi (50 ball; o'tish bali — 40). <span class="pn-dn">${ico("trend_dn", 12)}</span> — o'tgan semestrga nisbatan pasayish.</p>` +
      (dg.length ? `<h3 style="margin:14px 0 2px">Keskin pasaygan guruhlar${a.declining_count ? ` <span class="tag high">${fmt(a.declining_count)}</span>` : ""}</h3>` +
        (a.declining_clusters?.length ? pnClusters(a.declining_clusters) + (a.declining_count > dg.length ? `<p class="tiny muted" style="margin:10px 0 4px">Eng keskin pasaygan ${dg.length} tasi:</p>` : "")
          : fac != null || kurs != null ? `<p class="tiny muted" style="margin:0 0 6px">${[fac != null ? esc(fac) + " fakulteti" : "", kurs != null ? kurs + "-kurs" : ""].filter(Boolean).join(" · ")}</p>` : "") +
        tbl(hd, dg.map(g => [esc(g.name), ...(fac == null ? [esc(g.faculty)] : []), ...(kurs == null ? [g.course] : []), g.gpa, delta(g.delta), (g.attendance == null ? "—" : g.attendance + "%")]), {nw: [0]}) : "")));
  } else lock("oquv", L.academic);
  if (P.risk) {
    const r = P.risk;
    add("oquv", card(`O'qishda xavf ostidagi talabalar <span class="tag high">${fmt(r.count)}</span>`, r.students ?
      tbl(["F.I.Sh.", "Guruh", "#Ball", "#Davomat", "#Xavf", "Sabab"], r.students.slice(0, 10).map(s => [esc(s.full_name), esc(s.grp), s.gpa, (s.attendance == null ? "—" : s.attendance + "%"), `<b class="bad">${s.risk}</b>`, `<span class="tiny">${esc(s.reasons)}</span>`]), {nw: [1], top: 5}) :
      `<p class="tiny muted pn-note">${ico("shield", 14)}<span>${esc(r.note)}</span></p>` + bars(r.by_group, {label: g => g.group, value: g => g.count, fmtv: v => v + " nafar", top: 6}) +
      (ME.role_key === "rektor" ? `<div class="bg-box" id="bgBox"><button class="btn sm" onclick="this.parentNode.classList.add('open')">${ico("eye", 16)} Ro'yxatni ochish (favqulodda kirish)</button>
        <div class="bg-form"><p class="tiny muted" style="margin:6px 0">Sababini yozing — kirish audit jurnaliga «favqulodda» deb yoziladi.</p>
        <input id="bgReason" placeholder="Masalan: Kengash yig'ilishiga tayyorgarlik, 2-kurs holati" maxlength="200"><button class="btn sm primary" onclick="breakGlass(this)">Ochish</button></div><div id="bgOut"></div></div>` : "") +
      `<p class="tiny muted pn-note" style="margin:8px 0 0">${ico("info", 14)}<span>O'qishda xavf — talabalar soni (o'zlashtirish yoki davomat, kritik va undan yuqori). «Markaz: kritik holatlar» tugmasidagi raqam — barcha qoidalar bo'yicha holatlar (kontrakt, hujjat va h.k.).</span></p>`));
  } else lock("oquv", L.students);
  if (P.masters) {
    const m = P.masters;
    add("oquv", card("Magistratura", bars(m.stages, {label: s => s.stage, value: s => s.n, fmtv: v => v + " nafar"}) + tbl(["Ilmiy rahbar", "Daraja", "#Magistrant"], m.supervisors.slice(0, 5).map(s => [esc(s.full_name), esc(s.degree), s.n]))));
  }
  if (P.contracts) {
    const c = P.contracts, wg = c.worst_groups.slice(0, 5), fac = same(wg, g => g.faculty);
    add("moliya", card("Kontrakt tushumi", bars(c.by_faculty, {label: r => r.name, value: r => r.pct, max: 100, fmtv: v => v + "%"}) +
      `<p class="muted tiny">Jami: ${mln(c.total.paid)} / ${mln(c.total.total)} so'm · qarz ${mln(c.total.debt)} · ${c.total.debtors} qarzdor</p>` +
      (fac != null ? `<p class="tiny muted" style="margin:10px 0 4px">Eng past guruhlar — ${esc(fac)}</p>` : "") +
      `<p class="tiny muted" style="margin:10px 0 4px">Eng past tushumli guruhlar</p>` + tbl(["Guruh", ...(fac == null ? ["Fakultet"] : []), "#Tushum", "#Qarz"], wg.map(g => [esc(g.grp), ...(fac == null ? [`<span class="tiny">${esc(g.faculty.replace(/ va axborot texnologiyalari$/, " va AT"))}</span>`] : []), `<span class="bad">${g.pct}%</span>`, `<span class="nowrap">${mln(g.debt)}</span>`]), {nw: [0]})));
  } else lock("moliya", L.contracts);
  if (P.finance) {
    const f = P.finance, ms = f.months, per = ms.length ? `${monOf(ms[0].month)}–${monOf(ms[ms.length - 1].month)}` : "";
    const pl = same(ms, m => m.planned);
    add("moliya", card(`Byudjet ijrosi${per ? ` (${per})` : ""}`, `<p class="tiny muted" style="margin:0 0 4px">Jami ${mln(f.total.actual)} / ${mln(f.total.planned)} so'm — <b>${f.total.pct}%</b>. Moddalar bo'yicha rejadan og'ish:</p>` +
      devBars(f.categories, {label: r => r.category, plan: r => r.planned, actual: r => r.actual}) +
      `<p class="tiny muted" style="margin:14px 0 2px">Oylik xarajat: rejadan og'ish, %${pl != null ? ` (oylik reja ${mln(pl)} so'm)` : ""}</p>` + budgetChart(ms) +
      `<div class="pn-legend tiny muted"><span><i class="pn-sw"></i>rejadan kam</span><span><i class="pn-sw over"></i>rejadan oshgan</span><span>ustun ustiga olib boring — summa</span></div>`));
  } else lock("moliya", L.finance);
  if (P.payroll) add("moliya", card("Ish haqi fondi (oylik)", bars(P.payroll.by_unit, {label: u => u.unit, value: u => u.fund, fmtv: v => mln(v), top: 8}) + (P.payroll.staff ? "" : `<p class="tiny muted pn-note">${ico("shield", 14)}<span>Faqat jamlangan ko'rinish</span></p>`)));
  else if (["rektor", "prorektor_oquv"].includes(ME.role_key)) lock("moliya", L.payroll);
  if (P.science) {
    const s = P.science;
    add("ilmiy", card("Ilmiy salohiyat", bars(s.by_department, {label: d => d.name, value: d => d.scopus, fmtv: v => v + " ta", top: 8}) +
      `<p class="tiny muted">Scopus/WoS 2026 kafedralar kesimida · ilmiy darajalilik ${s.degree_pct}% · 2025 yildan beri nashrsiz: ${s.no_pubs_since_2025} o'qituvchi</p>`));
  } else lock("ilmiy", L.science);
  if (P.international) {
    const i = P.international, ps = i.partners.filter(p => p.days_left > 0), cn = same(ps, p => p.country);
    add("ilmiy", card("Xalqaro hamkorlar", tbl(["Hamkor", ...(cn == null ? ["Davlat"] : []), "Tur", "#Qoldi"], ps.map(p => [esc(p.name), ...(cn == null ? [esc(p.country)] : []), `<span class="tiny">${esc(p.kind)}</span>`, `<span class="nowrap">${p.days_left <= 60 ? `<b class="bad">${p.days_left} kun</b>` : p.days_left + " kun"}</span>`]), {top: 8})));
  } else lock("ilmiy", L.international);
  if (P.admissions) {
    const a = P.admissions;
    add("qabul", card("Qabul 2026", `<div class="ops-strip" style="margin:0 0 10px">${a.funnel.map(f => `<span class="chip-s">${esc(f.status)}: <b>${fmt(f.n)}</b></span>`).join("")}</div>` +
      bars(a.by_direction, {label: d => d.direction, value: d => d.applied, fmtv: v => fmt(v), top: 8}) +
      `<p class="tiny muted">Arizalar soni yo'nalishlar bo'yicha · jami ${fmt(a.total)}</p>`));
  } else lock("qabul", L.admissions);
  if (opsCard && full) add("qabul", opsCard);
  if (P.youth) {
    const y = P.youth;
    add("qabul", card(y.dormitory.length ? "Yotoqxona va murojaatlar" : "Talabalar murojaatlari", (y.dormitory.length ? bars(y.dormitory, {label: d => d.building, value: d => d.pct, max: 100, fmtv: v => v + "%"})
      : `<p class="tiny muted" style="margin:0 0 6px">Institutda yotoqxona yo'q (NQAAE pasporti) — talabalar ijara uylarda yashaydi.</p>`) +
      tbl(["Sana", "Yo'nalish", "Anonim murojaat", "Holat"], y.appeals.slice(0, 6).map(a => [dmy(a.date), esc(a.category), esc(a.text), `<span class="tag ${a.status === "hal qilindi" ? "low" : a.status === "yangi" ? "high" : "mid"}">${esc(a.status)}</span>`]), {nw: [0]})));
  } else lock("qabul", L.youth);
  if (decCard) add("ijro", decCard);
  if (P.hr) add("ijro", card("Kadrlar (shaxsiy ma'lumot — faqat mahalliy)", tbl(["F.I.Sh.", "Bo'linma", "Lavozim", "Pasport"], P.hr.staff.slice(0, 8).map(s => [esc(s.full_name), esc(s.unit), esc(s.position), esc(s.passport)]), {nw: [3]})));
  else if (ME.level <= 2) lock("ijro", L.hr);

  if (!full) {
    /* bo'lim/fakultet darajasi: faqat ruxsat etilgan kartalar, tablarsiz */
    if (opsCard) h += `<div style="margin-top:14px">${opsCard}</div>`;
    const shown = cards.filter(c => !c.locked).map(c => c.html);
    if (mw && mw.items) {   /* «Mening vazifalarim» sahifasidagi bilan bir xil ro'yxat (app/mywork.py) — eng yaqin muddatlilari */
      const it = mw.items.slice(0, 6), n = mw.counts?.total || 0;
      PNL.mw = it;
      shown.unshift(card(`Mening vazifalarim${n ? ` <span class="tag ${mw.counts.overdue ? "high" : "gray"}" title="Sizdan harakat kutayotgan ishlar${mw.counts.overdue ? `; ${mw.counts.overdue} tasi muddati o'tgan` : ""}">${n}</span>` : ""}`,
        it.length ? `<div class="pn-mwl">${it.map((x, i) => `<button type="button" class="pn-mwi" data-mwi="${i}"><span class="pn-mwt">${esc(x.title)}</span><span class="tiny ${x.overdue ? "bad" : "muted"}">${x.due ? (x.overdue ? "muddati o'tgan · " : "") + dtm(x.due) : esc(x.status || "")}</span></button>`).join("")}</div>`
          : `<p class="muted">Sizdan kutilayotgan ish yo'q ✓</p>`,
        `<button class="btn sm" onclick="go('mywork')">Barchasi →</button>`));
    }
    if (ME.role_key === "kotib")
      shown.unshift(card(pnH("file", "Majlis materiali"), `<p class="tiny">Majlis yozuvini ISFT Core'ga bering: bayonnoma qoralamasi va topshiriqlar tayyorlanadi, tasdiqlagach bo'limlar navbatiga tushadi.</p><button class="btn primary" onclick="DEC.open=null;go('tasks')">Boshlash →</button>`));
    if (ME.allow.some(a => ["facilities", "requests", "youth"].includes(a)))
      shown.unshift(card(pnH("wrench", "Murojaatlar va nosozliklar"), `<p class="tiny">QR nosozliklar, murojaatlar va tadbir qatnashuvi — bir joyda.</p><button class="btn primary" onclick="go('service')">Ochish →</button>`));
    if (ME.allow.includes("spaces"))
      shown.push(card(pnH("camera", "Auditoriyalar bandligi"), `<p class="tiny">Kameralardan faqat odamlar soni: hozir qaysi xona band, qaysi biri bo'sh turibdi.</p><button class="btn" onclick="go('spaces')">Ochish →</button>`));
    h += `<div class="grid g2" style="margin-top:14px">${shown.join("")}</div>`;
  } else {
    /* ruxsat yo'q kartalar umuman ko'rsatilmaydi (yopiq ro'yxat ham — shovqin); ruxsatlar «Ruxsat darajalari»da */
    const open = cards.filter(c => !c.locked), lockNote = "";
    const tabs = PANEL_TABS.filter(([k]) => open.some(c => c.t === k));
    if (open.length <= 4 || tabs.length < 2) h += `<div class="grid g2" style="margin-top:14px">${open.map(c => c.html).join("")}</div>${lockNote}`;
    else {
      if (!tabs.some(([k]) => k === PNL.tab)) PNL.tab = tabs[0][0];
      h += `<div class="pn-tabs" role="tablist" aria-label="Panel bo'limlari">${tabs.map(([k, t, i]) => `<button class="pn-tab${k === PNL.tab ? " on" : ""}" role="tab" data-t="${k}" aria-selected="${k === PNL.tab}" onclick="pnTab('${k}')">${ico(i, 16)}<span>${t}</span><em>${open.filter(c => c.t === k).length}</em></button>`).join("")}</div>`;
      h += tabs.map(([k]) => `<div class="pn-pane" role="tabpanel" data-t="${k}"${k === PNL.tab ? "" : " hidden"}><div class="grid g2">${open.filter(c => c.t === k).map(c => c.html).join("")}</div></div>`).join("") + lockNote;
    }
  }
  el.innerHTML = h;
  pnBindHero(el);
  el.querySelectorAll("[data-open]").forEach(b => b.onclick = () => openDecision(+b.dataset.open));
  el.querySelectorAll("[data-mwi]").forEach(b => b.onclick = () => { const x = (PNL.mw || [])[+b.dataset.mwi]; if (!x) return; if (typeof mwOpen === "function") mwOpen(x.link); else if (typeof XT !== "undefined") XT.openLink(x.link); });
  if (deskD && deskD.kind) deskBind(el, deskD);
}

/* ---------- chat ---------- */
/* Tayyor savollar — faqat lavozim ruxsati doirasidagi mavzular (ruxsat yo'q savol tavsiya qilinmaydi) */
const SUGG = {
  rektor: ["Qaysi yo'nalishda ortda qolyapmiz?", "O'zlashtirish nega pasaydi?", "Kontrakt tushumi yil oxiriga qancha bo'ladi?", "Kengash topshiriqlari bajarilyaptimi?", "Kommunal xarajatlar nega oshdi?"],
  kengash: ["Byudjet ijrosi qanday?", "Kontrakt tushumi qanday?", "Kengash topshiriqlari bajarilyaptimi?", "Qaysi xalqaro shartnomalar tugayapti?"],
  prorektor_oquv: ["Qaysi guruhlarda o'zlashtirish pasaygan?", "Xavf ostidagi talabalar kimlar?", "GPA qanday hisoblanadi?", "Qabul holati qanday?"],
  prorektor_ilmiy: ["Scopus maqolalar bo'yicha qaysi kafedra ortda?", "Qaysi xalqaro shartnomalar tugayapti?", "Magistratura holati qanday?"],
  ilmiy_bolim: ["Scopus maqolalar bo'yicha qaysi kafedra ortda?", "2025 yildan beri maqolasi yo'q o'qituvchilar", "Magistratura holati qanday?"],
  prorektor_moliya: ["Qaysi xarajat moddasi rejadan oshgan?", "Kontrakt tushumi qanday?", "Kommunal xarajatlar nega oshdi?"],
  prorektor_yoshlar: ["Yotoqxona holati qanday?", "Hal qilinmagan murojaatlar bormi?", "Topshiriqlar muddatida bajarilyaptimi?"],
  kafedra: ["Kafedramda ilmiy faoliyat qanday?", "Qaysi guruhlarda muammo bor?", "Xavf ostidagi talabalar kimlar?"],
  oqituvchi: ["Mening guruhlarimda kim qiynalyapti?", "Yakuniy nazoratga kim kiritiladi?", "O'tish bali necha?"],
  tyutor: ["Xavf ostidagi talabalar kimlar?", "Qaysi guruhlarda muammo bor?", "O'tish bali necha?"],
  buxgalteriya: ["Kommunal xarajatlar nega oshdi?", "Kontrakt tushumi qanday?"],
  talabalar: ["Qanday masalada registratorga murojaat qilaman?", "Xavf ostidagi talabalar kimlar?", "O'tish bali necha?"],
  registrator_xodim: ["Qanday masalada registratorga murojaat qilaman?", "Yakuniy nazoratga kim kiritiladi?", "O'tish bali necha?"],
  akademik: ["Akademik faoliyatni boshqarish bo'limi vazifalari?", "Yakuniy nazoratga kim kiritiladi?", "Qaysi guruhlarda o'zlashtirish pasaygan?"],
  imtihon: ["Yakuniy nazoratga kim kiritiladi?", "O'tish bali necha?", "Qaysi guruhlarda o'zlashtirish pasaygan?"],
  sirtqi: ["Sirtqi bo'lim nima ish qiladi?", "Kredit nima?", "Dars soat nechida boshlanadi?"],
  malumotlar_bazasi: ["Ma'lumotlar bazasi bo'limi vazifalari?", "GPA qanday hisoblanadi?", "Qaysi guruhlarda o'zlashtirish pasaygan?"],
  strategik: ["Topshiriqlar muddatida bajarilyaptimi?", "Qaysi topshiriqlar muddati o'tgan?"],
  sifat: ["Qaysi guruhlarda o'zlashtirish pasaygan?", "GPA qanday hisoblanadi?", "O'tish bali necha?"],
  marketing: ["Qabul holati qanday?", "Qaysi yo'nalishga ariza ko'p?"],
  qabul: ["Qabul holati qanday?", "Qaysi yo'nalishga ariza ko'p?"],
  yuridik: ["Qaysi xalqaro shartnomalar tugayapti?", "Menga berilgan topshiriqlar qaysilar?"],
  xalqaro: ["Qaysi xalqaro shartnomalar tugayapti?", "Xalqaro hamkorlar qaysilar?"],
  magistratura: ["Magistratura holati qanday?", "Menga berilgan topshiriqlar qaysilar?"],
  kotib: ["Topshiriqlar muddatida bajarilyaptimi?", "Qaysi topshiriqlar muddati o'tgan?"],
};
const SUGG_DEF = ["Menga berilgan topshiriqlar qaysilar?", "Muddati o'tgan topshiriqlar bormi?"];
function renderChat() {
  const s = SUGG[ME.role_key] || SUGG_DEF;
  const sg = $("#suggest");
  sg.classList.remove("open");
  sg.innerHTML = `<button class="sg-toggle" type="button" aria-expanded="false">${ico("spark", 15)}<span>Tayyor savollar</span><span class="sg-chev">${ico("arrow", 14)}</span></button>
    <div class="sg-list">${s.map(x => `<button class="sg-chip" type="button" data-q="${esc(x)}">${esc(x)}</button>`).join("")}</div>`;
  const tg = sg.querySelector(".sg-toggle");
  tg.onclick = () => tg.setAttribute("aria-expanded", sg.classList.toggle("open"));
  sg.querySelectorAll("[data-q]").forEach(b => b.onclick = () => ask(b.dataset.q));
  if (!$("#msgs").children.length) {
    const w = document.createElement("div"); w.className = "m a welcome";
    w.innerHTML = `<div class="w-head"><span class="w-ava">${ico("spark", 22)}</span><div><div class="w-title">Assalomu alaykum! Men ISFT Core</div>
        <div class="w-sub">ISFT institutining sun'iy intellektli yordamchisi · ${esc(ME.role)}${ME.scope === "Butun institut" ? "" : " · ko'lam: " + esc(ME.scope)}</div></div></div>
      <p class="w-text">Institut ma'lumotlari bo'yicha savol bering — javob faqat sizga ruxsat etilgan ma'lumot asosida tuziladi. Tavsiyani bir tugma bilan topshiriqqa aylantirish mumkin. «Nega?» deb davom ettirsangiz, oldingi mavzuni eslayman.</p>
      <div class="w-flow"><span>${ico("search", 15)} Savolni tahlil qilaman</span><span>${ico("server", 15)} Bazalarga murojaat qilaman</span><span>${ico("bolt", 15)} Sabab izlayman</span><span>${ico("checkc", 15)} Har bir raqamni manba bilan solishtiraman</span></div>
      <div class="w-sugg-h">Tayyor savollar</div>
      <div class="w-sugg">${s.map(x => `<button type="button" class="w-card" data-q="${esc(x)}"><span>${esc(x)}</span>${ico("arrow", 16)}</button>`).join("")}</div>`;
    $("#msgs").appendChild(w);
    w.querySelectorAll("[data-q]").forEach(b => b.onclick = () => ask(b.dataset.q));
  }
  $("#v-chat .chatwrap").classList.toggle("started", !!$("#msgs .m.u"));
  $("#q").focus();
}
function addMsg(who, text, cls = "") { const d = document.createElement("div"); d.className = `m ${who} ${cls}`; d.textContent = text; $("#msgs").appendChild(d); $("#msgs").scrollTop = 1e9; return d; }
function rich(t) { return esc(t).replace(/\*\*(.+?)\*\*/g, "<b>$1</b>").replace(/^(Tavsiya:)/gm, "<b>$1</b>"); }
$("#chatForm").onsubmit = e => { e.preventDefault(); const q = $("#q").value.trim(); if (q) ask(q); };
let ASKING = false;
const STEP_ICO = {run: "refresh", done: "check", denied: "lock"};
async function ask(q) {
  if (ASKING) return toast("ISFT Core oldingi savolga javob yozmoqda…");
  ASKING = true; $("#q").value = "";
  $("#v-chat .chatwrap")?.classList.add("started"); $("#suggest").classList.remove("open");
  $("#msgs").querySelectorAll(".a-fu").forEach(x => x.remove());  /* davom savollari faqat oxirgi javobda */
  const uEl = addMsg("u", q);
  const box = addMsg("a", "", "card-a pending");
  box.innerHTML = `<button type="button" class="a-run" aria-expanded="true"></button><div class="steps"></div><div class="ans"><div class="skel"><i></i><i></i><i></i></div></div>`;
  const runEl = box.querySelector(".a-run"), stepsEl = box.querySelector(".steps"), ansEl = box.querySelector(".ans"), steps = {};
  const drawSteps = () => {
    const L = Object.values(steps);
    stepsEl.innerHTML = L.map(x => `<div class="step ${x.status}"><span class="si">${ico(STEP_ICO[x.status] || "check", 14)}</span><span>${esc(x.label)}</span></div>`).join("");
    if (box.classList.contains("pending")) runEl.innerHTML = `<span class="spin">${ico("refresh", 15)}</span><span>ISFT Core ishlamoqda</span><span class="dots"><i></i><i></i><i></i></span>${L.length ? `<span class="a-run-n">${L.filter(x => x.status !== "run").length}/${L.length} qadam</span>` : ""}`;
  };
  drawSteps();
  try {
    const r = await api("/api/chat", {method: "POST", body: JSON.stringify({q})});
    const rd = r.body.getReader(), dec = new TextDecoder(); let buf = "";
    for (;;) {
      const {done, value} = await rd.read(); if (done) break;
      buf += dec.decode(value, {stream: true});
      let i;
      while ((i = buf.indexOf("\n")) >= 0) {
        const line = buf.slice(0, i); buf = buf.slice(i + 1); if (!line.trim()) continue;
        const e = JSON.parse(line);
        if (e.t === "step") { steps[e.id] = e; drawSteps(); $("#msgs").scrollTop = 1e9; }
        else if (e.t === "answer") {
          box.classList.remove("pending");
          ansEl.innerHTML = answerHtml(e); bindAnswer(box, e);
          const n = Object.keys(steps).length, v = e.verify;
          runEl.innerHTML = `<span class="a-run-ico">${ico("list", 15)}</span><span>${n ? n + " qadam · " : ""}${(e.ms / 1000).toFixed(1)} s</span>` +
            (v && v.n ? `<span class="vbadge ${v.bad.length ? "warn" : ""}" title="Javobdagi har bir raqam manba ma'lumot bilan kod orqali solishtirildi">${ico(v.bad.length ? "alert" : "checkc", 15)}${v.ok}/${v.n} raqam manbadan tekshirildi</span>` : "") +
            (n ? `<span class="chev">${ico("arrow", 14)}</span>` : "");
          box.classList.add("folded"); runEl.setAttribute("aria-expanded", "false");
          if (n) runEl.onclick = () => runEl.setAttribute("aria-expanded", !box.classList.toggle("folded")); else runEl.disabled = true;
          if (e.denied.length && !e.sources.length) box.classList.add("deny");
          if (!e.structured && !(e.denied.length && !e.sources.length)) box.classList.add("plain");
          const m = $("#msgs"); m.scrollTop = Math.max(0, uEl.offsetTop - 12);
        }
      }
    }
  } catch (e) {
    if (e.message !== "auth") { box.classList.add("folded"); runEl.remove(); ansEl.innerHTML = `<div class="a-err">${ico("alert", 16)} Javob uzildi. Qayta so'rab ko'ring.</div>`; }
  } finally { box.classList.remove("pending"); ASKING = false; }
}
const actBtn = (a, attr) => a.type === "propose" ? `<button class="btn sm primary" ${attr}>${ico("send", 14)}${esc(a.label)}</button>`
  : `<button class="btn sm ${a.type === "ask" ? "ghost" : ""}" ${attr}>${esc(a.label)}${ico(a.type === "ask" ? "chat" : "arrow", 14)}</button>`;
function answerHtml(e) {
  const c = e.structured, denyOnly = e.denied.length && !e.sources.length;
  const strip = t => String(t).replace(/^\s*⛔\s*/, "");
  let body;
  if (denyOnly) {
    body = `<div class="a-deny"><span class="a-deny-i">${ico("lock", 18)}</span><div><b>Ruxsat yo'q</b><div>${esc(strip(e.denied[0] || e.text))}</div></div></div>`;
  } else if (c) {
    body = `<div class="a-sum">${esc(c.summary)}</div>` +
      (c.facts.length ? `<ul class="a-facts">${c.facts.map(f => `<li class="${f.startsWith("  –") ? "sub" : ""}">${esc(f.replace(/^\s*–\s*/, ""))}</li>`).join("")}</ul>` : "") +
      (c.why.length ? `<section class="a-sec why"><div class="a-h">${ico("search", 16)} Nega</div><ul class="a-list">${c.why.map(f => `<li>${esc(f)}</li>`).join("")}</ul></section>` : "") +
      (c.recs.length ? `<section class="a-sec recs"><div class="a-h">${ico("checkc", 16)} Tavsiya</div><ol class="a-recs">${c.recs.map((r, i) => `<li><span class="a-rn">${i + 1}</span><div class="a-rt">${esc(r.text)}</div>${r.action ? `<div class="a-ra">${actBtn(r.action, `data-act="${i}"`)}</div>` : ""}</li>`).join("")}</ol></section>` : "");
  } else {
    body = `<div class="a-text">${rich(e.text)}</div>` + (e.actions.length ? `<div class="a-acts">${e.actions.map((a, i) => actBtn(a, `data-act2="${i}"`)).join("")}</div>` : "");
  }
  const denied = !denyOnly && e.denied.length ? `<div class="a-denied">${e.denied.map(d => `<div>${ico("lock", 14)}<span>${esc(strip(d))}</span></div>`).join("")}</div>` : "";
  const foot = (denyOnly ? "" : `<div class="a-foot">${e.sources.length ? `<span class="a-src-l">${ico("folder", 14)} Manbalar:</span>${e.sources.map(s => `<span class="a-src">${esc(s)}</span>`).join("")}` : ""}
    <span class="a-mode">${e.mode === "ai" ? "Mahalliy AI tahrir qildi" : "Raqamlar va xulosa — kod hisobi"}</span></div>`) +
    (e.followups.length ? `<div class="a-fu"><span class="a-fu-l">${ico("chat", 14)} Davom ettirish</span>${e.followups.map(f => `<button type="button" class="chip-btn" data-fu="${esc(f)}">${esc(f)}</button>`).join("")}</div>` : "");
  return body + denied + foot;
}
function bindAnswer(box, e) {
  const recs = e.structured ? e.structured.recs.map(r => r.action) : [];
  box.querySelectorAll("[data-act]").forEach(b => b.onclick = () => runAction(recs[+b.dataset.act], b));
  box.querySelectorAll("[data-act2]").forEach(b => b.onclick = () => runAction(e.actions[+b.dataset.act2], b));
  box.querySelectorAll("[data-fu]").forEach(b => b.onclick = () => ask(b.dataset.fu));
}
async function runAction(a, btn) {
  if (!a) return;
  if (a.type === "go") return go(a.view);
  if (a.type === "ask") return ask(a.q);
  if (a.type === "propose") {
    let res = null;
    await busy(btn, async () => {
      const r = await api("/api/agents/propose", {method: "POST", body: JSON.stringify({agent: a.agent, label: a.label, payload: a.payload})});
      const j = await r.json();
      if (!r.ok) return toast(j.message || j.detail || "Bajarib bo'lmadi");
      res = j;
      toast(j.status === "bajarildi" ? (j.result || "Bajarildi — audit jurnalida") : "Taklif AI agentlar markaziga tushdi — mas'ul rahbar tasdiqlaydi");
      if (typeof badges === "function") badges();
    }, `<span class="spin">${ico("refresh", 14)}</span>Yuborilmoqda…`);
    if (res && btn.isConnected) {
      const ok = res.status === "bajarildi", s = document.createElement("span");
      s.className = "a-done" + (ok ? "" : " wait");
      s.innerHTML = `${ico(ok ? "checkc" : "clock", 15)}${ok ? "Bajarildi — audit jurnalida" : "Tasdiqlashga yuborildi"}`;
      btn.replaceWith(s);
    }
  }
}
async function breakGlass(btn) {
  const reason = $("#bgReason").value.trim();
  await busy(btn, async () => {
    const r = await api("/api/students/breakglass", {method: "POST", body: JSON.stringify({reason})}); const j = await r.json();
    if (!r.ok) return toast(j.detail || j.message || "Ochib bo'lmadi");
    $("#bgOut").innerHTML = `<p class="bg-note">${ico("unlock", 15)}<span>Favqulodda kirish audit jurnaliga yozildi: «${esc(reason)}»</span></p>` +
      tbl(["F.I.Sh.", "Guruh", "#Ball", "#Davomat", "Sabab"], j.students.slice(0, 15).map(s => [esc(s.full_name), esc(s.grp), s.gpa, s.attendance == null ? "—" : s.attendance + "%", `<span class="tiny">${esc(s.reasons)}</span>`]));
    $("#bgBox .bg-form").remove(); $("#bgBox > button").remove();
  }, "…");
}

/* ---------- majlislar, qarorlar va topshiriqlar ---------- */
/* agent A: qo'shimcha ikonkalar (emoji o'rniga) */
Object.assign(ICONS, {
  mic: '<rect x="9" y="2" width="6" height="12" rx="3"/><path d="M5 10a7 7 0 0 0 14 0M12 17v4M8 21h8"/>',
  printer: '<path d="M6 9V2h12v7"/><rect x="2" y="9" width="20" height="9" rx="2"/><path d="M6 14h12v8H6z"/>',
  download: '<path d="M12 3v12M7 10l5 5 5-5"/><path d="M4 21h16"/>',
  pen: '<path d="M12 20h9"/><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4z"/>',
  scale: '<path d="M12 3v18M7 21h10M5 7h14M5 7l-3 7a3.5 3.5 0 0 0 6 0zM19 7l-3 7a3.5 3.5 0 0 0 6 0z"/>',
  smartphone: '<rect x="6" y="2" width="12" height="20" rx="2.5"/><path d="M11 18h2"/>',
});
/* Oqim: kotib material beradi → ISFT Core qoralama → kotib tahrirlab tasdiqlaydi → bo'lim navbati → ijro va chat → rektor nazorati.
   Barcha ruxsatlar serverda (app/decisions.py) tekshiriladi; bu yerda faqat ko'rsatish. */
const DEC = {open: null, timer: null, sig: "", src: "demo", cap: null};
const UNIT_ICO = {it: "server", registrator: "folder"};
const DST = {qoralama: ["Qoralama", "mid"], yangi: ["Navbatda", "gray"], jarayonda: ["Jarayonda", "mid"], bajarildi: ["Bajarildi", "low"]};
const dstTag = (t) => t.overdue ? `<span class="tag high">Muddati o'tgan</span>` : `<span class="tag ${(DST[t.status] || ["", "gray"])[1]}">${esc((DST[t.status] || [t.status])[0])}</span>`;
const dtm = s => { if (!s) return ""; if (s.length <= 10) return dmy(s); const d = new Date(s); return `${dmy(s.slice(0, 10))}, ${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`; };
const hm = s => { const d = new Date(s); return `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`; };
const dueHtml = t => t.due ? `<b class="${t.overdue ? "bad" : ""}">${dtm(t.due)}</b>${t.due_text ? `<span class="said">majlisda: «${esc(t.due_text)}»</span>` : ""}` : `<span class="unsaid">aytilmagan</span>`;
const whoHtml = t => t.assignee_name ? esc(t.assignee_name) : `<span class="unsaid">${t.status === "qoralama" ? "aytilmagan" : "biriktirilmagan"}</span>`;
/* taskId — havola aniq topshiriqqa ({view: "tasks", meeting, task}): qaror ochilgach shu karta ko'rsatiladi va belgilanadi */
function openDecision(id, taskId) { DEC.open = id; DEC.focus = taskId || null; DEC.sig = ""; if (typeof DIR !== "undefined") DIR.open = null; go("tasks"); }
function closeDecision() { DEC.open = null; DEC.focus = null; clearInterval(DEC.timer); go("tasks"); }

async function renderTasks() {
  clearInterval(DEC.timer);
  if (DEC.open) return renderDecision(DEC.open);
  if (typeof DIR !== "undefined" && DIR.open) return renderDirective(DIR.open);   /* ierarxik topshiriq (directives.js) */
  const el = $("#v-tasks"); let t, L;
  try { [t, L] = await Promise.all([J("/api/section/tasks"), J("/api/dec/list")]); }
  catch (e) { if (e.message === "denied") { el.innerHTML = locked("Majlis topshiriqlari"); return; } throw e; }
  const isKotib = ME.role_key === "kotib", lead = ["rektor", "kengash"].includes(ME.role_key);
  /* demo vositalari (qarorlarni o'chirish) — faqat server ISFT_CORE_DEMO_TOOLS=1 bilan ishga tushirilgan bo'lsa */
  if ((isKotib || ME.role_key === "rektor") && !DEC.cap) try { DEC.cap = await J("/api/dec/capabilities"); } catch (e) {}
  const demoTools = !!DEC.cap?.demo_tools && (isKotib || ME.role_key === "rektor");
  /* bo'limsiz eski topshiriqlar server ishga tushganda yagona oqimga o'tkaziladi (decisions.migrate_legacy) — bu ro'yxat odatda bo'sh;
     bir bosishli «Bajarildi» yo'q: topshiriq qaror kartasida ijrochi tomonidan natija bilan yakunlanadi, rektor qabul qiladi yoki qaytaradi */
  const old = t.tasks.filter(x => !x.decision && !x.directive);
  let h = `<div class="head"><div><h2>Majlislar va topshiriqlar</h2><span class="muted">${t.tasks.length} ta topshiriq · ${t.done} bajarilgan · ${t.overdue ? `<b class="bad">${t.overdue} muddati o'tgan</b>` : "muddati o'tgan yo'q"}</span></div>
    ${demoTools ? `<button class="btn ghost sm" id="decReset" title="Demo vositasi (ISFT_CORE_DEMO_TOOLS=1): demo ssenariysida yaratilgan qarorlarni o'chiradi va LMS hodisasi xabarini bekor qiladi">${ico("refresh", 16)} Demoni qayta boshlash</button>` : ""}</div>`;
  if (isKotib) h += await newMeetingCard();
  if (typeof dirSection === "function") h += await dirSection();   /* «Men bergan topshiriqlar» */
  if (L.queue) h += queueCard(L.queue);
  const decs = L.decisions;
  if (decs.length || isKotib || lead) h += `<div class="card" style="margin-top:14px"><h3>${ico("tasks")} Majlis qarorlari</h3>` + (decs.length ? `<div class="dec-list">${decs.map(decRow).join("")}</div>` :
    `<p class="muted">${isKotib ? "Hali qaror yo'q. Yuqorida majlis materialini ISFT Core'ga bering." : "Hali tasdiqlangan qaror yo'q. Majlis materialini rektorat kotibi kiritadi."}</p>`) + `</div>`;
  if (old.length) h += `<div class="card" style="margin-top:14px"><h3>Avvalgi majlis topshiriqlari</h3>${tbl(["Majlis", "Mas'ul", "Topshiriq", "Muddat", "Holat", ""], old.map(x => [
    `<span class="tiny">${esc(x.meeting)}<br><span class="muted">${dmy(x.meeting_date)}</span></span>`, esc(x.assignee), esc(x.text),
    !x.due ? `<span class="unsaid">aytilmagan</span>` : x.overdue ? `<b class="bad">${dmy(x.due)}<br><span class="tiny">${-x.days} kun o'tdi</span></b>` : `${dmy(x.due)}<br><span class="tiny muted">${x.status === "bajarildi" ? "" : x.days === 0 ? "bugun" : x.days + " kun qoldi"}</span>`,
    `<span class="tag ${x.status === "bajarildi" ? "low" : x.overdue ? "high" : "mid"}">${x.overdue ? "muddati o'tgan" : esc(x.status)}</span>`,
    x.meeting_id ? `<button class="btn sm" data-open="${x.meeting_id}" data-otask="${x.id}">Ochish →</button>` : ""]))}</div>`;
  el.innerHTML = h;
  el.querySelectorAll("[data-open]").forEach(b => b.onclick = () => openDecision(+b.dataset.open, +b.dataset.otask || null));
  bindAssign(el, renderTasks);
  if ($("#decReset")) $("#decReset").onclick = () => { const b = $("#decReset"); if (!arm(b, "Ha, demo qarorlarini o'chirish")) return;
    busy(b, async () => { const r = await J("/api/dec/demo-reset", {method: "POST"}); toast(`Demo qayta boshlandi (${r.removed} ta qaror o'chirildi)`); renderTasks(); badges(); }); };
  if (isKotib) bindNewMeeting();
  if (typeof dirBind === "function") dirBind(el);
}

function decRow(d) {
  const done = d.tasks.filter(t => t.status === "bajarildi").length;
  return `<div class="dec-row"><div class="dec-row-h"><div><b>${esc(d.title)}</b><span class="muted tiny"> · ${dmy(d.date)} · ${d.status === "qoralama" ? `<span class="tag mid">qoralama</span>` : `${done}/${d.tasks.length} bajarildi`}</span></div>
    <button class="btn sm ${d.status === "qoralama" ? "primary" : ""}" data-open="${d.id}">${d.status === "qoralama" ? "Tahrirlash" : "Ochish"} →</button></div>
    ${d.tasks.map(t => `<div class="dec-line"><span class="dl-unit">${esc(t.unit_name || "bo'lim aytilmagan")}</span><span class="dl-who">${whoHtml(t)}</span><span class="dl-tags">${dstTag(t)}${reviewTag(t)}</span>
      <span class="dl-res">${t.result ? esc(t.result.length > 110 ? t.result.slice(0, 110) + "…" : t.result) : t.blocked ? `<span class="muted">${esc(t.dep?.unit_name || "")} natijasi kutilmoqda</span>` : ""}</span></div>`).join("")}</div>`;
}

function queueCard(q) {
  const open = q.tasks.filter(t => t.status !== "bajarildi");
  return `<div class="card" style="margin-top:14px"><h3>${ico(UNIT_ICO[q.unit] || "tasks")} ${q.head ? `${esc(q.unit_name)} navbati` : "Menga biriktirilgan topshiriqlar"} <span class="tag ${open.length ? "mid" : "low"}">${open.length} ochiq</span></h3>
    ${q.head && q.duties && q.duties.length ? `<p class="tiny muted" style="margin:-4px 0 10px">Bo'lim vazifalari (akademik qoidalar taqdimoti): ${esc(q.duties.join("; "))}.</p>` : ""}
    ${q.tasks.length ? `<div class="dec-list">${q.tasks.map(t => `<div class="dec-row"><div class="dec-row-h"><div><b>${esc(t.text)}</b><div class="tiny muted">${esc(t.meeting)} · ${dmy(t.meeting_date)}</div></div>
      <button class="btn sm primary" ${t.directive ? `data-dopen="${t.id}"` : `data-open="${t.meeting_id}" data-otask="${t.id}"`}>Ochish →</button></div>
      <div class="kv"><span>Muddat</span><span>${dueHtml(t)}</span><span>Holat</span><span>${t.directive && typeof dirTag === "function" ? dirTag(t) + (t.progress && t.progress.total ? ` <span class="tiny muted">· taqsimlangan: ${t.progress.done}/${t.progress.total} bajarildi</span>` : "") : dstTag(t)}${t.blocked ? ` <span class="tiny muted">· ${esc(t.dep.unit_name)} natijasi kutilmoqda</span>` : ""}</span>
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
  return `<div class="card" style="margin-top:6px"><h3>${ico("chat")} Majlis materialini ISFT Core'ga berish</h3>
    <div class="src-tabs" role="tablist">
      <button class="btn sm ${DEC.src === "demo" ? "primary" : ""}" data-src="demo">Demo transkript</button>
      <button class="btn sm ${DEC.src === "manual" ? "primary" : ""}" data-src="manual">Matnni qo'lda kiritish</button>
      <button class="btn sm" disabled title="${esc(c.audio_note)}">${ico("mic", 16)} Ovozdan yozish — o'rnatilmagan</button>
    </div>
    <div class="src-note ${DEC.src === "demo" ? "demo" : ""}">${DEC.src === "demo"
      ? `<b>DEMO TRANSKRIPT.</b> Bu tayyor namunaviy matn — haqiqiy ovozdan olinmagan. Ovozdan matnga o'tkazish (lokal STT) bu serverda hali o'rnatilmagan; o'rnatilganda ham ovoz institutdan tashqariga chiqmaydi.`
      : `Majlis yozuvi yoki kotib qaydlarini shu yerga qo'ying. ISFT Core faqat matnda aytilgan bo'lim, xodim va muddatni oladi.`}</div>
    <input id="mTitle" value="Rektorat tezkor yig'ilishi" style="width:100%;margin:10px 0 8px" aria-label="Majlis nomi">
    <textarea id="mText" ${DEC.src === "demo" ? "readonly" : ""} aria-label="Majlis matni">${DEC.src === "demo" ? esc(c.sample) : ""}</textarea>
    <div class="row-actions" style="margin-top:10px"><button class="btn primary" id="mDraft">ISFT Core: bayonnoma va topshiriqlar qoralamasi</button>
    <span class="tiny muted">Qoralama tasdiqlanmaguncha hech kimga yuborilmaydi.</span></div></div>`;
}
function bindNewMeeting() {
  document.querySelectorAll("[data-src]").forEach(b => b.onclick = () => { DEC.src = b.dataset.src; renderTasks(); });
  $("#mDraft").onclick = () => busy($("#mDraft"), async () => {
    if (!$("#mText").value.trim()) return toast("Majlis matnini kiriting");
    const d = await J("/api/dec/draft", {method: "POST", body: JSON.stringify({title: $("#mTitle").value, transcript: $("#mText").value, source: DEC.src})});
    toast(`Qoralama tayyor: ${d.tasks.length} ta topshiriq`); openDecision(d.id);
  }, "ISFT Core tahlil qilmoqda… (≈15 s)");
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
  if (!silent && DEC.focus) {   /* aniq topshiriqqa havola (bildirishnoma, «Mening vazifalarim») — karta ko'rsatiladi va belgilanadi */
    const card = el.querySelector(`.dec-task[data-tid="${DEC.focus}"]`); DEC.focus = null;
    if (card) { card.scrollIntoView({block: "center", behavior: "smooth"}); card.classList.add("dec-focus"); setTimeout(() => card.classList.remove("dec-focus"), 2600); }
  }
  clearInterval(DEC.timer);
  if (!d.can_edit) DEC.timer = setInterval(() => { if (DEC.open === id && !$("#v-tasks").classList.contains("hidden")) renderDecision(id, true).catch(() => {}); }, 6000);
}
const backBtn = () => `<button class="btn ghost sm" onclick="closeDecision()" style="margin-bottom:10px">← Barcha qarorlar</button>`;
const srcBadge = d => d.source === "demo" ? `<span class="tag mid" title="Namunaviy matn, ovozdan olinmagan">Manba: demo transkript</span>`
  : d.source === "arxiv" ? `<span class="tag gray" title="Avval rol bo'yicha kiritilgan majlis topshiriqlari — bo'limlarga bog'lanib, yagona ijro oqimiga o'tkazilgan">Manba: avvalgi majlis yozuvi</span>`
  : `<span class="tag gray">Manba: qo'lda kiritilgan matn</span>`;

function draftHtml(d) {
  /* bo'limlar — Portal org_units bilan bitta reestr (server tartibida), guruhlab: Rahbariyat / Bo'limlar / Fakultet tyutorlari / Kafedralar */
  const grpd = d.units.reduce((a, u) => { const g = u.group_name || "Bo'limlar"; (a[g] = a[g] || []).push(u); return a; }, {});
  const opts = (sel) => `<option value="">— aytilmagan —</option>` + Object.entries(grpd).map(([g, us]) => `<optgroup label="${esc(g)}">` +
    us.map(u => `<option value="${esc(u.key)}" ${u.key === sel ? "selected" : ""}>${esc(u.name)}</option>`).join("") + `</optgroup>`).join("");
  return backBtn() + `<div class="head"><div><h2>${esc(d.title)}</h2><span class="muted">${dmy(d.date)} · <span class="tag mid">Qoralama — tasdiqlanmagan</span> ${srcBadge(d)}</span></div></div>
  <div class="src-note">${ico("info", 15)} <span><b>ISFT Core qoralamasi — tekshiring.</b> ${esc(d.extract_note || "")}. Majlisda aytilmagan maydonlar bo'sh qoldirildi.</span></div>
  ${d.incident ? `<div class="src-note" style="margin-top:8px">${ico("wrench", 15)} <span>Bog'liq hodisa (Murojaatlar va nosozliklar): <b>${esc(d.incident.title)}</b> · ${d.incident.n} ta murojaat${d.incident.notified_at ? "" : " · talabalarga hali xabar berilmagan"}</span></div>` : ""}
  <div class="grid g2" style="margin-top:14px">${d.tasks.map((t, i) => `<div class="card draft-task" data-tid="${t.id}">
    <div class="dt-h"><b>${i + 1}-topshiriq</b><button class="btn ghost sm" data-rm="${t.id}" title="Bu bandni olib tashlash">${ico("x", 16)} Olib tashlash</button></div>
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
  document.querySelectorAll("[data-rm]").forEach(b => b.onclick = () => { const c = b.closest(".draft-task"); c.classList.toggle("removed"); b.innerHTML = c.classList.contains("removed") ? ico("refresh", 16) + " Qaytarish" : ico("x", 16) + " Olib tashlash"; });
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
  /* qaytarib bo'lmaydi — ikki bosqichli tasdiq */
  $("#dDrop").onclick = () => { const b = $("#dDrop"); if (!arm(b, "Ha, qoralamani o'chirish")) return;
    busy(b, async () => { await J(`/api/dec/${d.id}`, {method: "DELETE"}); toast("Qoralama o'chirildi"); closeDecision(); }); };
}

function decisionHtml(d) {
  const chatTask = d.tasks.find(t => t.can_chat);
  const units = [...new Set(d.tasks.map(t => t.unit_name).filter(Boolean))].join(" ↔ ");
  const done = d.tasks.filter(t => t.status === "bajarildi").length;
  return backBtn() + `<div class="head"><div><h2>${esc(d.title)}</h2><span class="muted">${dmy(d.date)} · <span class="tag ${done === d.tasks.length ? "low" : "gray"}">Tasdiqlangan · ${done}/${d.tasks.length} bajarildi</span> ${srcBadge(d)}</span>
    <div class="tiny muted" style="margin-top:4px">${d.source === "arxiv" ? "Avvalgi majlis · ijrochi natija bilan yakunlaydi, rektor qabul qiladi yoki qaytaradi" : `Tasdiqladi: ${esc(d.confirmed_by || "")} · ${dtm(d.confirmed_at)}`}</div></div></div>
  ${d.incident ? `<div class="src-note">${ico("wrench", 15)} <span>Bog'liq hodisa (Murojaatlar va nosozliklar): <b>${esc(d.incident.title)}</b> · ${d.incident.n} ta murojaat · ${d.incident.notified_at ? `<span class="good">talabalarga xabar yuborilgan (${dtm(d.incident.notified_at)})</span>` : `<span class="bad">talabalarga hali xabar berilmagan</span>`}</span></div>` : ""}
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
    <div class="dt-h"><span class="dt-unit">${ico(UNIT_ICO[t.unit] || "tasks", 16)} ${esc(t.unit_name || "Bo'lim aytilmagan")}</span><span class="dt-tags">${dstTag(t)}${reviewTag(t)}</span></div>
    <p class="dt-text">${i + 1}. ${esc(t.text)}</p>
    <div class="kv"><span>Mas'ul</span><span>${t.can_assign ? assignSel(t, d.staff) : whoHtml(t)}</span>
      <span>Muddat</span><span>${dueHtml(t)}</span>
      ${t.dep || t.dep_text ? `<span>Bog'liqlik</span><span>${t.dep ? `${esc(t.dep.unit_name)} natijasidan keyin · ${t.dep.status === "bajarildi" ? `<span class="good">natija keldi</span>` : `<span class="warn-t">kutilmoqda</span>`}` : ""}${t.dep_text ? `<span class="said">majlisda: «${esc(t.dep_text)}»</span>` : ""}</span>` : ""}
    </div>
    ${t.dep && t.dep.result && t.can_act ? `<div class="res dep-res"><div class="res-h">${esc(t.dep.unit_name)} natijasi</div>${esc(t.dep.result)}</div>` : ""}
    ${t.result ? `<div class="res"><div class="res-h">${t.status === "bajarildi" ? "Natija" : "Oraliq natija"} · ${esc(t.result_by || "")} · ${dtm(t.result_at)}</div>${esc(t.result)}</div>` : ""}
    ${t.review === "qaytarildi" && t.status !== "bajarildi" && t.review_note ? `<div class="res ret"><div class="res-h">Qayta ishlashga qaytarildi · ${esc(t.review_by || "")} · ${dtm(t.review_at)}</div>${esc(t.review_note)}</div>` : ""}
    ${t.can_review ? `<div class="act rev"><textarea class="f-rnote" rows="2" placeholder="Izoh (qaytarishda majburiy)…" aria-label="Izoh"></textarea>
      <div class="row-actions"><button class="btn sm primary" data-accept="${t.id}">${ico("check", 15)} Natijani qabul qilish</button>
      <button class="btn sm" data-return="${t.id}">${ico("undo", 15)} Qayta ishlashga qaytarish</button></div></div>` : ""}
    ${t.can_act && t.status !== "bajarildi" ? `<div class="act">
      ${t.status === "yangi" ? `<button class="btn sm" data-start="${t.id}">${ico("play", 16)} Ishni boshlash</button>` : ""}
      <textarea class="f-res" rows="3" placeholder="${t.unit === "registrator" ? "Talabalarga xabar matni…" : "Tekshiruv natijasi: sabab, nima qilindi, holat…"}">${t.status === "jarayonda" && t.result ? esc(t.result) : ""}</textarea>
      ${t.dep && t.dep.result && t.unit === "registrator" ? `<button class="btn ghost sm" data-tpl="${t.id}">${esc(t.dep.unit_name)} natijasidan xabar loyihasi</button>` : ""}
      ${notifyBox ? `<label class="chk-line"><input type="checkbox" class="f-notify" checked> «Murojaatlar va nosozliklar» bo'limidagi «${esc(d.incident.title)}» hodisasiga murojaat qilgan ${d.incident.n} ta talabaga javob sifatida yuborish</label>` : ""}
      <div class="row-actions"><button class="btn sm" data-save="${t.id}">Oraliq natijani saqlash</button>
      <button class="btn sm primary" data-finish="${t.id}" ${t.blocked ? "disabled" : ""}>${ico("check", 15)} Natijani kiritish va yakunlash</button></div>
      ${t.blocked ? `<p class="tiny warn-t" style="margin:0">${esc(t.dep.unit_name)} natijasi kelmaguncha yakunlab bo'lmaydi (server ham tekshiradi). Chatda yozishishingiz mumkin.</p>` : ""}
    </div>` : ""}
  </div>`;
}
/* natijani qabul qilish holati (yagona yakunlash oqimi: ijrochi natija bilan yakunlaydi → rektor qabul qiladi yoki qaytaradi) */
const reviewTag = t => t.status === "bajarildi" && t.review === "kutilmoqda" ? ` <span class="tag mid" title="Ijrochi yakunladi — rektor qabul qiladi yoki qaytaradi">Qabul kutilmoqda</span>`
  : t.status === "bajarildi" && t.review === "qabul" && t.review_by ? ` <span class="tag low" title="${esc(t.review_by)} · ${esc(dtm(t.review_at))}">Qabul qilindi</span>`
  : t.review === "qaytarildi" && t.status !== "bajarildi" ? ` <span class="tag high">Qaytarildi</span>` : "";
function bindDecision(d) {
  const el = $("#v-tasks"), re = () => { DEC.sig = ""; renderDecision(d.id); badges(); };
  bindAssign(el, re);
  const review = (b, decision) => busy(b, async () => {
    const note = b.closest(".dec-task").querySelector(".f-rnote").value.trim();
    if (decision === "qaytarish" && !note) { b.closest(".dec-task").querySelector(".f-rnote").focus(); return toast("Qaytarish sababini yozing"); }
    await J(`/api/dec/task/${b.dataset.accept || b.dataset.return}/review`, {method: "POST", body: JSON.stringify({decision, note})});
    toast(decision === "qabul" ? "Natija qabul qilindi" : "Qayta ishlashga qaytarildi — ijrochiga bildirishnoma yuborildi"); re(); });
  el.querySelectorAll("[data-accept]").forEach(b => b.onclick = () => review(b, "qabul"));
  el.querySelectorAll("[data-return]").forEach(b => b.onclick = () => review(b, "qaytarish"));
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
    ta.value = `Hurmatli talabalar!\n\n${d.incident ? d.incident.title : "LMS platformasidagi muammo"} bo'yicha: ${t.dep.unit_name} tekshiruvni yakunladi. ${t.dep.result}\n\nAlohida murojaat yuborishingiz shart emas. Muammo takrorlansa, Registrator ofisiga yoki murojaat sahifasi orqali xabar bering.\n\nHurmat bilan, Registrator ofisi`;
    ta.focus(); toast("Loyiha bog'liq topshiriq natijasidan tuzildi — tekshirib, tahrir qiling");
  });
  el.querySelectorAll("[data-chat]").forEach(f => f.onsubmit = e => {
    e.preventDefault(); const inp = f.querySelector("input"), v = inp.value.trim(); if (!v) return;
    busy(f.querySelector("button"), async () => { await J(`/api/dec/task/${f.dataset.chat}/msg`, {method: "POST", body: JSON.stringify({text: v})}); inp.value = ""; re(); });
  });
}

/* ---------- Talabalar markazi ----------
   Qoidalar va ruxsatlar serverda (app/student_ops.py); bu yerda faqat ko'rsatish va natija kiritish. */
const OPSV = {page: 30, tab: null, rule: "", level: 0, q: "", kind: "", student: null, sum: null, review: null, grp: "", course: 0, late: false, role: "", sel: new Set()};
const OPS_RULES = {kontrakt: "Kontrakt", davomat: "Davomat", akademik: "O'zlashtirish", hujjat: "Hujjat", tatil: "Akademik ta'til", otrabotka: "Otrabotka"};
const OPS_LVL = {1: ["Diqqat", "mid"], 2: ["Kritik", "high"], 3: ["Jiddiy", "high"]};
const OPS_KIND = {qongiroq: "Qo'ng'iroq", suhbat: "Suhbat", hujjat: "Hujjat so'rash", xat: "Ogohlantirish xati", buyruq: "Buyruq loyihasi"};
const OPS_KIND_ICO = {qongiroq: "phone", suhbat: "chat", hujjat: "file", xat: "mail", buyruq: "report"};
const OPS_ROLE = {call_center: "Call-markaz", tyutor: "Tyutor", talabalar: "Registrator ofisi", sirtqi: "Sirtqi bo'lim", registrator_xodim: "Registrator ofisi xodimi"};
const OPS_REASON = {sababsiz: "Sababsiz", kasallik: "Kasallik", komandirovka: "Komandirovka", mehnat_tatili: "Mehnat ta'tili", oilaviy: "Oilaviy"};
const OPS_DOC = {tasdiqlangan: ["tasdiqlangan", "low"], kutilmoqda: ["kutilmoqda", "mid"], yoq: ["yo'q", "high"]};
/* navbat bilan ishlaydigan lavozimlar: sahifa navbatdan boshlanadi, tushuntirishlar bitta «Qanday ishlaydi» havolasida */
const OPS_OPER = ["call_center", "tyutor", "registrator_xodim", "talabalar", "sirtqi"];
const som = x => fmt(Math.round(x)) + " so'm";
const lvlTag = l => `<span class="tag ${OPS_LVL[l][1]}">${OPS_LVL[l][0]}</span>`;
const isAgg = () => ["rektor", "kengash", "prorektor_yoshlar"].includes(ME.role_key);
const opsOper = () => OPS_OPER.includes(ME.role_key);
function factText(rule, f) {
  if (rule === "kontrakt") return `${esc(f.installment)} (${f.pct}%): ${som(f.need_now)} yetishmaydi · ${f.days < 0 ? `<b class="bad">${-f.days} kun o'tdi</b>` : `${f.days} kun qoldi`}`;
  if (rule === "davomat") return `${f.hours} soat sababsiz${f.next ? ` · ${f.next} soatdan oshsa — hayfsan` : " · hayfsan chegarasidan oshgan"}`;
  if (rule === "akademik") return `GPA (5) ${f.gpa5 ?? "—"}${f.gpa_ok ? " (yetarli)" : ""} · ${f.fails.length} ta akademik qarz${f.fails.length ? ": " + esc(f.fails.map(x => x.subject).join(", ")) : ""}${(f.oraliq_low || []).length ? ` · oraliq < 12: ${esc(f.oraliq_low.map(x => x.subject).join(", "))}` : ""}`;
  if (rule === "hujjat") return `${f.items.length} ta sababli qoldirish hujjati kutilmoqda${f.items.some(i => i.late) ? ` · <b class="bad">muddat o'tdi</b>` : ""}`;
  if (rule === "tatil") return `Ta'til ${dmy(f.end)}da tugaydi · ${f.days < 0 ? `<b class="bad">${-f.days} kun o'tdi</b>` : f.days + " kun qoldi"}`;
  if (rule === "otrabotka") return `${esc(f.subject)}: muddat ${dtm(f.due_at)} · ${f.hours_left < 0 ? `<b class="bad">${-Math.round(f.hours_left)} soat o'tdi</b>` : `${Math.round(f.hours_left)} soat qoldi`}`;
  return "";
}

async function renderOps() {
  const el = $("#v-ops");
  el.innerHTML = `<p class="muted">Yuklanmoqda…</p>`;
  OPSV.sum = await J("/api/ops/summary");
  const op = opsOper(), RGok = !!window.RG, rk = ME.role_key;
  /* kafedra, buxgalteriya, imtihon — faqat o'qish (o'z ko'lami/qoidalari); buxgalteriyaga otrabotka yo'q.
     Navbat bilan ishlaydigan lavozimlarda birinchi tab — navbat; Registrator ofisi boshlig'ida — call-markaz navbatini boshqarish ham */
  const tabs = isAgg() ? [] : rk === "call_center" ? ["navbat"] : rk === "tyutor" ? ["navbat", "holatlar", "otrabotka", "qoidalar"]
    : rk === "buxgalteriya" ? ["holatlar", "navbat"]
    : rk === "talabalar" && RGok ? ["navbat", "calls", "stol", "holatlar", "otrabotka", "ruxsatnoma", "qoidalar"]
    : ["registrator_xodim", "sirtqi"].includes(rk) && RGok ? ["navbat", "stol", "holatlar", "otrabotka", "ruxsatnoma", "qoidalar"]
    : ["holatlar", "navbat", "otrabotka", "qoidalar"];
  if (!tabs.includes(OPSV.tab)) OPSV.tab = tabs[0] || null;
  const mine = OPSV.sum.mine;
  const T = {stol: "Ish stoli", holatlar: "Holatlar", navbat: rk === "call_center" ? "Qo'ng'iroqlar navbati" : `Mening navbatim${mine ? ` <span class="tag ${mine.late ? "high" : "gray"}">${fmt(mine.n)}</span>` : ""}`,
    calls: "Call-markaz navbati", otrabotka: "Otrabotka", ruxsatnoma: "Ruxsatnoma", qoidalar: "Qoidalar"};
  const canRun = ["talabalar", "prorektor_oquv"].includes(rk);
  const src = pgSrc(`Manba: HEMIS (baho, davomat, buyruqlar) va buxgalteriya (kontrakt) — sinov ma'lumotlari · qoidalar har 10 daqiqada tekshiriladi${OPSV.sum.last_run ? `, oxirgisi: <b>${whenTxt(OPSV.sum.last_run)}</b>` : ""}`);
  const intro = `Tizim o'zi aniqlagan xavf holatlari (davomat, baho, kontrakt, hujjat) — mas'ul bo'lim navbatiga topshiriq bo'lib tushadi. Talaba yozgan murojaatlar — «Murojaatlar va nosozliklar»da.`;
  const info = `<details class="pg-info" id="opsInfo" style="margin:4px 0 10px"><summary>${ico("info", 14)}${op ? "Qanday ishlaydi: qoidalar, manba va raqamlar" : "Me'yorlar, huquqiy asos va ma'lumot manbasi"}</summary>
      ${op ? `<p class="tiny muted">${intro}</p><div>${src}</div>` : ""}
      <p class="tiny muted">Davomat chegaralari — institut me'yori: 30 soat sababsiz → qo'ng'iroq va ogohlantirish xati, 48 soatdan oshsa → hayfsan. Qolganlari (JPA 3.0, 2 ta fan, 3 kun, call-markaz me'yori…) — <b>institut tomonidan hali tasdiqlanmagan</b> namunaviy qiymatlar. Ma'lumotlar sun'iy (sinov bazasi).</p>
      <p class="tiny muted">Har topshiriqning <b>muddati</b> — haqiqiy muddat (kontrakt eslatmasi — to'lov sanasidan oldin, davomat 30+ soat — 24 soat ichida); call-markaz rejasi uni o'zgartirmaydi. «Kechikkan» — faqat muddati haqiqatda o'tganlar; «rejaga ko'ra kechikadi» — navbat to'lgani uchun muddatdan keyinga rejalashtirilganlar.</p>
      <p class="tiny muted">Bu yerdagi raqamlar — <b>holatlar</b>; bitta talabada bir nechta holat bo'lishi mumkin. Paneldagi «O'qishda xavf» — <b>talabalar</b> soni. Ogohlantirish xati — Hujjatlar markazida (ro'yxat raqami va QR bilan), buyruq loyihasi — «Buyruqlar»da tayyorlanadi.</p>
      <div class="tiny muted" id="opsBasis"></div></details>`;
  el.innerHTML = `<div class="head"><div><h2>Talabalar markazi</h2>${op ? "" : `<span class="muted">${intro}</span>${src}`}</div>
    <div class="row-actions">${canRun ? `<button class="btn sm" id="opsRun">${ico("refresh", 16)} Hozir tekshirish</button>` : ""}${tabs.map(t => `<button class="btn ${t === OPSV.tab ? "primary" : ""}" data-ot="${t}">${T[t]}</button>`).join("")}</div></div>
    ${info}${op ? `<div id="opsBody"></div><div style="margin-top:14px">${opsSummary(OPSV.sum, true)}</div>` : `${opsSummary(OPSV.sum)}<div id="opsBody" style="margin-top:14px"></div>`}`;
  el.querySelectorAll("[data-ot]").forEach(b => b.onclick = () => { OPSV.tab = b.dataset.ot; OPSV.student = null; OPSV.page = 30; renderOps(); });
  bindOpsSummary(el);
  if ($("#opsRun")) $("#opsRun").onclick = () => busy($("#opsRun"), async () => { const r = await J("/api/ops/evaluate", {method: "POST"}); toast(`Tekshirildi: ${r.opened} yangi holat, ${r.closed} yopildi, ${r.tasks + r.followups} topshiriq`); renderOps(); });
  hydrateIcons(el);
  if (!OPSV.tab) { const openT = (OPSV.sum.tasks || []).reduce((a, t) => a + (t.n || 0), 0), lateT = (OPSV.sum.tasks || []).reduce((a, t) => a + (t.late || 0), 0);
    $("#opsBody").innerHTML = `<div class="card"><h3 style="margin-bottom:8px">${ico("info", 18)} Raqamlarni qanday o'qish kerak</h3>
      <p style="margin:0 0 8px;font-size:14px;color:var(--ink-2)">Holatlar qoidalar dvigateli tomonidan avtomatik ochiladi va mas'ul bo'limlar navbatiga topshiriq bo'lib tushadi. Hozir ochiq topshiriqlar: <b>${fmt(openT)}</b>${lateT ? `, shundan muddati o'tgan: <b>${fmt(lateT)}</b>` : ""}; 7 kunda yopilgan holatlar: <b>${fmt(OPSV.sum.closed_7d || 0)}</b>.</p>
      ${OPSV.sum.calls?.total ? `<p style="margin:0 0 8px;font-size:14px;color:var(--ink-2)">Call-markaz: ${esc(OPSV.sum.calls.text)}</p>` : ""}
      <p style="margin:0 0 8px;font-size:14px;color:var(--ink-2)">Bu yerdagi raqamlar — <b>holatlar</b> (kontrakt, davomat, o'zlashtirish, hujjat, ta'til, otrabotka); bitta talabada bir nechta holat bo'lishi mumkin. Paneldagi «O'qishda xavf» esa <b>talabalar</b> soni: faqat o'zlashtirish va davomat bo'yicha kritik/jiddiy holati borlar.</p>
      <p style="margin:0 0 8px;font-size:14px;color:var(--ink-2)">Rang: <b class="bad">qizil</b> — jiddiy holatlar bor, <b class="warn-t">sariq</b> — kritik, <b>qora</b> — faqat «diqqat» darajasi, <b class="good">yashil</b> — ochiq holat yo'q.</p>
      <p class="tiny muted" style="margin:0">${ico("shield", 14)} Rahbariyat uchun faqat jamlangan raqamlar. Talabalar ro'yxati, telefonlar va suhbat skriptlari — Registrator ofisi, tyutorlar va call-markazda. Har bir harakat audit jurnalida.</p></div>`; return; }
  if (OPSV.student) return opsStudent(OPSV.student);
  ({stol: () => RG.desk(), holatlar: opsCases, navbat: opsTasks, calls: opsCalls, otrabotka: opsRetakes, ruxsatnoma: () => RG.permits(), qoidalar: opsPolicy})[OPSV.tab]();
}
/* qoidalar kesimi: faqat lavozim ishlaydigan qoidalar (ko'lamdan tashqari qoida «0, yashil» bo'lib chiqmaydi) */
function opsSummary(s, compact = false) {
  const by = {}; s.by_rule.forEach(r => { (by[r.rule] ||= {1: 0, 2: 0, 3: 0, n: 0}); by[r.rule][r.level] = r.n; by[r.rule].n += r.n; });
  const keys = Object.keys(OPS_RULES).filter(k => !s.rule_scope || s.rule_scope.includes(k));
  const sub = v => [v[3] && `${fmt(v[3])} jiddiy`, v[2] && `${fmt(v[2])} kritik`, v[1] && `${fmt(v[1])} diqqat`].filter(Boolean).join(" · ") || "ochiq holat yo'q";
  const cs = s.calls;
  const tk = s.tasks.map(t => t.role === "call_center" && cs ? `<span class="chip-s" title="${esc(cs.text || "")}">Call-markaz: <b>${fmt(cs.total)}</b>${cs.late ? ` · <span class="bad">${fmt(cs.late)} kechikkan</span>` : ""}${cs.projected_late ? ` · ${fmt(cs.projected_late)} rejaga ko'ra kechikadi` : ""}</span>`
    : `<span class="chip-s">${OPS_ROLE[t.role] || esc(t.role)}: <b>${fmt(t.n)}</b>${t.late ? ` · <span class="bad">${fmt(t.late)} kechikkan</span>` : ""}</span>`).join("");
  const tail = s.done_today !== undefined ? `<span class="chip-s">Bugun bajarganim: <b>${s.done_today}</b></span>` : `<span class="chip-s">7 kunda yopilgan holatlar: <b>${s.closed_7d}</b></span>`;
  if (compact) {
    const chips = keys.map(k => { const v = by[k] || {1: 0, 2: 0, 3: 0, n: 0}; const tone = v[3] ? "bad" : v[2] ? "warn-t" : "";
      return `<button class="chip-s" type="button" data-sr="${k}" title="${esc(sub(v))}">${OPS_RULES[k]}: <b class="${tone}">${fmt(v.n)}</b></button>`; }).join("");
    return `<div id="opsSum"><div class="tiny muted" style="margin-bottom:6px">Holatlar (qoida bo'yicha) va navbatlar</div><div class="ops-strip" style="margin-top:0">${chips}${tk}${tail}</div></div>`;
  }
  const cards = keys.map(k => { const v = by[k] || {1: 0, 2: 0, 3: 0, n: 0};
    const tone = v[3] ? "bad" : v[2] ? "warn" : v.n ? "" : "good";
    return `<div class="card kpi ${isAgg() ? "" : "ops-k"} ${tone}" ${isAgg() ? "" : `data-sr="${k}" role="button" tabindex="0"`}><div class="l">${OPS_RULES[k]}</div><div class="v">${fmt(v.n)}</div><div class="s">${sub(v)}</div></div>`; }).join("");
  return `<div id="opsSum"><div class="grid g6">${cards}</div><div class="ops-strip">${tk}${tail}</div></div>`;
}
function bindOpsSummary(root) {
  root.querySelectorAll("[data-sr]").forEach(b => b.onclick = () => { if (isAgg()) return; OPSV.rule = b.dataset.sr; OPSV.level = 0;
    OPSV.tab = ["call_center", "tyutor", "registrator_xodim", "talabalar", "sirtqi"].includes(ME.role_key) && OPSV.tab !== "holatlar" ? "navbat" : "holatlar"; OPSV.student = null; OPSV.page = 30; renderOps(); });
}

/* --- holatlar --- */
async function opsCases() {
  const b = $("#opsBody");
  const qs = new URLSearchParams({rule: OPSV.rule, level: OPSV.level || 0, q: OPSV.q, course: OPSV.course || 0, grp: OPSV.grp || ""});
  const rows = await J("/api/ops/cases?" + qs);
  const rules = Object.entries(OPS_RULES).filter(([k]) => !OPSV.sum?.rule_scope || OPSV.sum.rule_scope.includes(k));
  b.innerHTML = `<div class="card"><div class="ops-filters">
      <select id="ofRule" aria-label="Qoida"><option value="">Barcha qoidalar</option>${rules.map(([k, v]) => `<option value="${k}" ${k === OPSV.rule ? "selected" : ""}>${v}</option>`).join("")}</select>
      <select id="ofLvl" aria-label="Daraja"><option value="0">Barcha darajalar</option><option value="2" ${OPSV.level == 2 ? "selected" : ""}>Kritik va jiddiy</option><option value="3" ${OPSV.level == 3 ? "selected" : ""}>Faqat jiddiy</option></select>
      <select id="ofCourse" aria-label="Kurs"><option value="0">Barcha kurslar</option>${[1, 2, 3, 4, 5].map(k => `<option value="${k}" ${+OPSV.course === k ? "selected" : ""}>${k}-kurs</option>`).join("")}</select>
      <input id="ofQ" type="text" placeholder="Ism, guruh yoki HEMIS ID" value="${esc(OPSV.q)}" aria-label="Qidiruv"></div>
    <p class="tiny muted" style="margin:8px 0">${rows.length}${rows.length >= 300 ? "+" : ""} ta ochiq holat · daraja bo'yicha tartiblangan${OPSV.grp ? ` · guruh: <b>${esc(OPSV.grp)}</b> <a href="#" id="ofGrpX">(olib tashlash)</a>` : ""}</p>
    ${tbl(["Talaba", "Qoida", "Daraja", "Fakt", "#Ochiq ish", ""], rows.map(r => [`<b>${esc(r.full_name)}</b><div class="tiny muted">${esc(r.grp)} · ${r.course}-kurs · ${esc(r.faculty)}</div>`,
      OPS_RULES[r.rule], lvlTag(r.level), `<span class="tiny">${factText(r.rule, r.facts)}</span>`, r.open_tasks, `<button class="btn sm" data-st="${r.student_id}">Karta</button>`]))}</div>`;
  $("#ofRule").onchange = e => { OPSV.rule = e.target.value; opsCases(); };
  $("#ofLvl").onchange = e => { OPSV.level = +e.target.value; opsCases(); };
  $("#ofCourse").onchange = e => { OPSV.course = +e.target.value; opsCases(); };
  if ($("#ofGrpX")) $("#ofGrpX").onclick = e => { e.preventDefault(); OPSV.grp = ""; opsCases(); };
  let tmr; $("#ofQ").oninput = e => { clearTimeout(tmr); tmr = setTimeout(() => { OPSV.q = e.target.value; opsCases().then(() => { const i = $("#ofQ"); i.focus(); i.setSelectionRange(i.value.length, i.value.length); }); }, 350); };
  b.querySelectorAll("[data-st]").forEach(x => x.onclick = () => { OPSV.student = +x.dataset.st; opsStudent(OPSV.student); });
}

/* --- navbat (topshiriqlar): filtrlar (qoida, tur, kurs, guruh, kechikkan, mas'ul), ommaviy amallar, belgilash --- */
function opsQS(extra = {}) {
  return new URLSearchParams({rule: OPSV.rule, kind: OPSV.kind, grp: OPSV.grp || "", course: OPSV.course || 0, late: OPSV.late ? 1 : 0, role: OPSV.role || "", ...extra});
}
async function opsTasks() {
  const b = $("#opsBody"), rk = ME.role_key, cc = rk === "call_center";
  b.innerHTML = `<p class="muted">Yuklanmoqda…</p>`;
  const [rows, F] = await Promise.all([J("/api/ops/tasks?" + opsQS()), J("/api/ops/tasks/facets?" + opsQS())]);
  OPSV.sel = new Set([...OPSV.sel].filter(id => rows.some(t => t.id === id)));
  const rules = Object.entries(OPS_RULES).filter(([k]) => !OPSV.sum?.rule_scope || OPSV.sum.rule_scope.includes(k));
  const kinds = cc ? [] : Object.entries(OPS_KIND);
  const kn = Object.fromEntries((F.kinds || []).map(k => [k.kind, k.n]));
  const cs = OPSV.sum?.calls;
  /* call-markaz imkoniyati — yashirmasdan: bugun nechta qilinishi kerak, nechta kechikadi */
  const capBar = (cc || rk === "talabalar") && cs?.total ? `<div class="src-note" style="margin-bottom:10px;${cs.shortfall_today || cs.late ? "border-color:color-mix(in srgb,var(--bad) 40%,transparent)" : ""}">${ico("phone", 15)}<span><b>Call-markaz:</b> ${esc(cs.text)}
      ${rk === "talabalar" ? ` <a href="#" id="otCalls">Navbatni boshqarish (SMS, taqsimlash, operatorlar) →</a>` : cs.shortfall_today ? " Registrator ofisi kechikadiganlar uchun SMS eslatma yoki tyutorlarga taqsimlashni tanlaydi." : ""}</span></div>` : "";
  const roleSel = F.roles?.length ? `<select id="otRole" aria-label="Mas'ul"><option value="">Mening navbatim (${rk === "sirtqi" ? "Sirtqi bo'lim" : "Registrator ofisi"})</option><option value="all" ${OPSV.role === "all" ? "selected" : ""}>Barcha mas'ullar</option>
      ${F.roles.map(r => `<option value="${r.role}" ${OPSV.role === r.role ? "selected" : ""}>${OPS_ROLE[r.role] || esc(r.role)} (${fmt(r.n)})</option>`).join("")}</select>` : "";
  const canXat = ["talabalar", "registrator_xodim", "sirtqi"].includes(rk) && (kn.xat || 0) > 0, canBuy = rk === "talabalar" && (kn.buyruq || 0) > 0 && !["call_center", "tyutor", "sirtqi"].includes(OPSV.role);
  const page = rows.slice(0, OPSV.page), selectable = page.filter(t => t.can_act && t.kind !== "hujjat");
  b.innerHTML = `${capBar}<div class="ops-filters" style="margin-bottom:8px">
      ${roleSel}
      <select id="otRule" aria-label="Qoida"><option value="">Barcha qoidalar</option>${rules.map(([k, v]) => `<option value="${k}" ${k === OPSV.rule ? "selected" : ""}>${v}</option>`).join("")}</select>
      ${kinds.length ? `<select id="otKind" aria-label="Tur"><option value="">Barcha turlar</option>${kinds.map(([k, v]) => `<option value="${k}" ${k === OPSV.kind ? "selected" : ""}>${v}${kn[k] ? ` (${fmt(kn[k])})` : ""}</option>`).join("")}</select>` : ""}
      <select id="otCourse" aria-label="Kurs"><option value="0">Barcha kurslar</option>${(F.courses || []).map(c => `<option value="${c.course}" ${+OPSV.course === c.course ? "selected" : ""}>${c.course}-kurs (${fmt(c.n)})</option>`).join("")}</select>
      <select id="otGrp" aria-label="Guruh"><option value="">Barcha guruhlar (${(F.groups || []).length})</option>${(F.groups || []).map(g => `<option value="${esc(g.name)}" ${OPSV.grp === g.name ? "selected" : ""}>${esc(g.name)} (${g.n})</option>`).join("")}</select>
      <label class="tiny" style="display:inline-flex;gap:6px;align-items:center"><input type="checkbox" id="otLate" ${OPSV.late ? "checked" : ""}> faqat kechikkan</label></div>
    <p class="tiny muted" style="margin:0 0 10px"><b>${fmt(F.n)}</b> ta ochiq topshiriq${F.late ? ` · <span class="bad">${fmt(F.late)} tasining muddati o'tgan</span>` : " · muddati o'tgani yo'q"}${F.later ? ` · ${fmt(F.later)} tasi keyingi kunlarga rejalashtirilgan` : ""} · muddat va jiddiylik bo'yicha tartiblangan</p>
    ${canXat || canBuy ? `<div class="row-actions" style="margin-bottom:10px">${canXat ? `<button class="btn sm" data-bulk="xat">${ico("mail", 15)} ${fmt(kn.xat)} ta ogohlantirish xati — ommaviy tayyorlash</button>` : ""}
      ${canBuy ? `<button class="btn sm" data-bulk="buyruq">${ico("report", 15)} ${fmt(kn.buyruq)} ta buyruq loyihasi — Buyruqlarga</button>` : ""}</div><div id="opsBulk"></div>` : ""}
    ${selectable.length ? `<div class="card" id="otSelBar" style="padding:10px 14px;margin-bottom:10px;display:flex;flex-wrap:wrap;gap:8px;align-items:center">
      <label class="tiny" style="display:inline-flex;gap:6px;align-items:center"><input type="checkbox" id="otAll"> Ko'rinayotganlarni belgilash</label>
      <span class="tiny muted" id="otSelN">Tanlangan: 0</span>
      <input type="text" id="otSelNote" placeholder="Natija izohi (majburiy)" maxlength="1000" aria-label="Natija izohi" style="flex:1 1 200px;min-width:0;padding:8px 10px;border:1px solid var(--line-2);border-radius:10px;background:var(--surface)">
      <button class="btn sm primary" id="otSelDo" disabled>Tanlanganlarni bajarildi deb belgilash</button></div>` : ""}
    <div class="ops-tasks">${rows.length ? page.map((t, i) => opsTaskCard(t, i === 0)).join("") : `<div class="card"><p class="muted">${ico("checkc", 16)} Navbat bo'sh</p></div>`}</div>
    ${rows.length > OPSV.page ? `<div style="text-align:center;margin-top:12px"><button class="btn" id="otMore">Yana ko'rsatish (${Math.min(30, rows.length - OPSV.page)} ta)</button></div>` : ""}
    ${F.n > rows.length ? `<p class="tiny muted" style="text-align:center">Ro'yxatda birinchi ${rows.length} ta; qolganlarini filtr bilan toping.</p>` : ""}`;
  /* huquqiy asos — har kartada takrorlanmaydi: sahifaning yagona «Qanday ishlaydi» ma'lumotida */
  const basis = [...new Set(rows.flatMap(t => t.script?.basis || []))], bx = $("#opsBasis");
  if (bx) bx.innerHTML = basis.length ? `<b>Asos (navbatdagi ishlar bo'yicha):</b><ul style="margin:4px 0 0;padding-left:18px">${basis.map(x => `<li>${esc(x)}</li>`).join("")}</ul>` : "";
  const re = () => { OPSV.page = 30; opsTasks(); };
  if ($("#otMore")) $("#otMore").onclick = () => { OPSV.page += 30; opsTasks(); };
  if ($("#otCalls")) $("#otCalls").onclick = e => { e.preventDefault(); OPSV.tab = "calls"; renderOps(); };
  $("#otRule").onchange = e => { OPSV.rule = e.target.value; re(); };
  if ($("#otKind")) $("#otKind").onchange = e => { OPSV.kind = e.target.value; re(); };
  if ($("#otRole")) $("#otRole").onchange = e => { OPSV.role = e.target.value; OPSV.grp = ""; re(); };
  $("#otCourse").onchange = e => { OPSV.course = +e.target.value; OPSV.grp = ""; re(); };
  $("#otGrp").onchange = e => { OPSV.grp = e.target.value; re(); };
  $("#otLate").onchange = e => { OPSV.late = e.target.checked; re(); };
  b.querySelectorAll("[data-bulk]").forEach(x => x.onclick = () => opsBulk(x.dataset.bulk));
  const syncSel = () => { const n = OPSV.sel.size; if ($("#otSelN")) $("#otSelN").textContent = `Tanlangan: ${n}`; if ($("#otSelDo")) $("#otSelDo").disabled = !n; };
  b.querySelectorAll(".ot-sel").forEach(x => { x.checked = OPSV.sel.has(+x.dataset.id); x.onchange = () => { x.checked ? OPSV.sel.add(+x.dataset.id) : OPSV.sel.delete(+x.dataset.id); syncSel(); }; });
  if ($("#otAll")) $("#otAll").onchange = e => { b.querySelectorAll(".ot-sel").forEach(x => { x.checked = e.target.checked; e.target.checked ? OPSV.sel.add(+x.dataset.id) : OPSV.sel.delete(+x.dataset.id); }); syncSel(); };
  if ($("#otSelDo")) $("#otSelDo").onclick = () => busy($("#otSelDo"), async () => {
    const note = $("#otSelNote").value.trim(); if (note.length < 3) { $("#otSelNote").focus(); return toast("Natija izohini yozing (kamida 3 belgi)"); }
    const r = await J("/api/ops/tasks/bulk-outcome", {method: "POST", body: JSON.stringify({ids: [...OPSV.sel], note})});
    toast(`${r.done} ta topshiriq bajarildi deb belgilandi${r.skipped.length ? ` · ${r.skipped.length} tasi o'tkazib yuborildi (${esc(r.skipped[0].why)})` : ""}`);
    OPSV.sel.clear(); opsTasks(); refreshOpsSummary();
  });
  syncSel();
  bindTaskActions(b, () => { opsTasks(); refreshOpsSummary(); });
  hydrateIcons(b);
}
/* ommaviy xatlar (bitta DOCX paket / ZIP, hujjatlar reyestrida) va buyruq loyihalari (Buyruqlar moduli) — avval ko'rib chiqish */
async function opsBulk(kind) {
  const box = $("#opsBulk"); if (!box) return;
  const body = {kind, rule: OPSV.rule, grp: OPSV.grp || "", course: +OPSV.course || 0};
  box.innerHTML = `<div class="card"><p class="muted">Ko'rib chiqish tayyorlanmoqda…</p></div>`;
  const p = await J("/api/ops/bulk/preview", {method: "POST", body: JSON.stringify(body)});
  if (!p.n) { box.innerHTML = `<div class="card"><p class="muted">Bu filtr bo'yicha bajarishingiz mumkin bo'lgan topshiriq yo'q.</p></div>`; return; }
  box.innerHTML = `<div class="card" style="margin-bottom:12px"><div class="head" style="margin-bottom:6px"><div><h3 style="margin:0">${kind === "xat" ? "Ogohlantirish xatlari — ommaviy" : "Buyruq loyihalari — ommaviy"}: ${fmt(p.n)} ta</h3>
      <span class="tiny muted">${kind === "xat" ? "Har bir xat hujjatlar reyestrida o'z ro'yxat raqami va QR bilan; shablon bo'yicha bitta birlashtirilgan DOCX" + (p.zip ? ", hammasi — ZIP" : "") : "Har tur bo'yicha BITTA buyruq loyihasi talabalar ro'yxati bilan — Buyruqlar bo'limida rektor imzosiga yuboriladi"}</span></div>
      <button class="btn ghost sm" id="bkX">Yopish</button></div>
    ${tbl(["Hujjat", "#Soni", "Qanday"], p.packets.map(x => [esc(x.title), fmt(x.n), `<span class="tiny">${esc(x.how)}</span>`]))}
    ${p.sample ? `<p class="tiny" style="margin:8px 0 4px"><b>Namuna:</b> ${esc(p.sample.student)} (${esc(p.sample.grp)}) — ${esc(p.sample.title)}: ${esc(p.sample.facts)}</p>` : ""}
    <details><summary class="tiny muted">Birinchi ${p.students.length} ta talaba</summary><ul class="tiny" style="margin:4px 0 0;padding-left:18px">${p.students.map(s => `<li>${esc(s.name)} · ${esc(s.grp)} · ${esc(s.title)}</li>`).join("")}</ul></details>
    ${p.cant ? `<p class="tiny muted">${fmt(p.cant)} tasi sizning vakolatingizda emas — kiritilmaydi.</p>` : ""}
    <div class="row-actions" style="margin-top:10px"><button class="btn primary" id="bkGo">${kind === "xat" ? `${fmt(p.n)} ta xatni tayyorlash` : `${p.packets.length} ta buyruq loyihasini yaratish`}</button></div><div id="bkRes"></div></div>`;
  $("#bkX").onclick = () => { box.innerHTML = ""; };
  $("#bkGo").onclick = () => busy($("#bkGo"), async () => {
    const r = await J("/api/ops/bulk/run", {method: "POST", body: JSON.stringify(body)});
    $("#bkRes").innerHTML = `<div class="res" style="margin-top:10px"><b>Tayyor: ${fmt(r.n)} ta</b>${r.skipped?.length ? ` · ${r.skipped.length} tasi o'tkazib yuborildi` : ""}<br>
      ${r.files.map(f => `<a href="/api/docs/file/${encodeURIComponent(f.file)}">${ico("download", 15)} ${esc(f.title)} — ${fmt(f.n)} ta (${esc(f.first)} … ${esc(f.last)}), .docx</a>`).join("<br>")}
      ${r.zip ? `<br><a href="/api/ops/bulk/${r.batch}/zip">${ico("download", 15)} Hammasi bitta ZIP (${esc(r.zip)})</a>` : ""}
      ${r.orders.map(o => `<a href="#" onclick="go('orders');return false">${esc(o.title)}: loyiha #${o.order_id} (${fmt(o.n)} ta talaba) — Buyruqlar bo'limida ochish</a>`).join("<br>")}</div>`;
    $("#bkGo").disabled = true; hydrateIcons(box); toast(`Ommaviy: ${fmt(r.n)} ta tayyorlandi`); refreshOpsSummary();
  }, "Tayyorlanmoqda…");
  hydrateIcons(box);
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
      <div class="row-actions"><button class="btn sm primary" data-docgen>${ico("folder", 15)} ${t.kind === "buyruq" ? "Buyruq loyihasini tayyorlash" : "Xatni tayyorlash"}</button></div></div>`
    : `<div class="ops-out"><input type="text" class="f-note" placeholder="Suhbat natijasi" maxlength="1000" aria-label="Izoh"><div class="row-actions"><button class="btn sm primary" data-out="bajarildi">Bajarildi</button></div></div>`;
  /* faqat muddati haqiqatda o'tgan topshiriq «kechikdi» (qizil); rejaga ko'ra kechikadigani — alohida, kulrang izoh */
  const when = `muddat ${dtm(t.due_at)}${t.scheduled ? ` · reja: ${dmy(t.planned_on)}` : ""}`;
  const sel = t.can_act && t.kind !== "hujjat" && OPSV.tab === "navbat" && !OPSV.student;
  return `<div class="card ops-task ${t.late ? "late" : ""}" data-tid="${t.id}">
    <div class="ot-h">${sel ? `<input type="checkbox" class="ot-sel" data-id="${t.id}" aria-label="Belgilash">` : ""}<span class="ot-kind ic-t">${ico(OPS_KIND_ICO[t.kind] || "file", 16)}${OPS_KIND[t.kind] || esc(t.kind)}</span>${lvlTag(t.level)}
      <span class="tiny ${t.late ? "bad" : "muted"}">${when}${t.late ? " · muddati o'tdi" : t.will_be_late ? " · rejaga ko'ra kechikadi" : ""}</span></div>
    <div class="ot-title"><b>${esc(t.title)}</b>${t.assignee_role && t.assignee_role !== ME.role_key && OPS_ROLE[t.assignee_role] && ME.role_key !== "call_center" ? ` <span class="tag gray">${OPS_ROLE[t.assignee_role]}</span>` : ""}</div>
    <div class="ot-st"><a href="#" data-st="${t.student_id}">${esc(t.full_name)}</a> · ${esc(t.grp)}${t.course ? ` · ${t.course}-kurs` : ""} · ${esc(t.faculty)}${t.study_form && t.study_form !== "kunduzgi" ? ` · ${esc(t.study_form)}` : ""}${t.phone ? ` · <span class="phone">${esc(t.phone)}</span>` : ""}</div>
    <div class="tiny" style="margin-top:4px">${factText(t.rule, t.facts)}</div>
    ${sc.say ? `<details class="script" ${openScript ? "open" : ""}><summary>${t.kind === "qongiroq" ? "Nima deyish kerak" : t.kind === "suhbat" ? "Suhbat rejasi" : "Yo'riqnoma"}</summary><ol>${sc.say.map(x => `<li>${esc(x)}</li>`).join("")}</ol>
      ${sc.tone?.length ? `<div class="tiny muted"><b>Muomala:</b> ${esc(sc.tone.join(" "))}</div>` : ""}</details>` : ""}
    ${acts}</div>`;
}
function bindTaskActions(root, after) {
  root.querySelectorAll("[data-st]").forEach(a => a.onclick = e => { e.preventDefault(); OPSV.student = +a.dataset.st; OPSV.tab = OPSV.tab || "holatlar"; opsStudent(OPSV.student); });
  root.querySelectorAll(".ops-task [data-out]").forEach(btn => btn.onclick = () => busy(btn, async () => {
    const card = btn.closest(".ops-task"), out = btn.dataset.out;
    const body = {outcome: out, note: card.querySelector(".f-note")?.value || ""};
    if (out === "vada") { body.promise_date = card.querySelector(".f-pd").value; if (!body.promise_date) return toast("Va'da sanasini tanlang"); }
    const r = await J(`/api/ops/tasks/${card.dataset.tid}/outcome`, {method: "POST", body: JSON.stringify(body)});
    toast(r.rescheduled ? `Javob bermadi — ertaga qayta (${r.attempts}/3)` : r.escalated ? "3 marta javob bermadi — yuzma-yuz suhbatga topshirildi" : out === "vada" ? `Va'da qayd etildi: ${dmy(body.promise_date)} — muddat o'tsa tizim qayta eslatadi` : "Natija saqlandi");
    after();
  }));
  root.querySelectorAll(".ops-task [data-docgen]").forEach(btn => btn.onclick = () => busy(btn, async () => {
    const card = btn.closest(".ops-task");
    const r = await J(`/api/ops/tasks/${card.dataset.tid}/document`, {method: "POST", body: JSON.stringify({reason: card.querySelector(".f-reason")?.value || ""})});
    card.querySelector(".ops-out").innerHTML = `<div class="res" style="margin-top:8px"><b>${esc(r.title)}</b> · ${esc(r.reg_no)}${r.status === "loyiha" ? " · rektor imzosini kutadi" : ""}<br>
      ${r.file ? `<a href="/api/docs/file/${encodeURIComponent(r.file)}">${ico("download", 16)} .docx yuklab olish</a>` : r.order_id ? `<a href="#" onclick="go('orders');return false">Buyruqlar bo'limida ochish (#${r.order_id})</a>` : ""}</div>`;
    toast(`Tayyor: ${r.reg_no}`); refreshOpsSummary();
  }, "Tayyorlanmoqda…"));
}
async function refreshOpsSummary() {
  try { OPSV.sum = await J("/api/ops/summary"); const g = $("#opsSum");
    if (g) { const w = document.createElement("div"); w.innerHTML = opsSummary(OPSV.sum, opsOper()); g.replaceWith(w.firstElementChild); bindOpsSummary($("#v-ops")); }
    badges(); } catch (e) {}
}

/* --- Call-markaz navbatini boshqarish (Registrator ofisi boshlig'i): haqiqiy kechikish, muqobil yo'llar, operatorlar me'yori --- */
async function opsCalls() {
  const b = $("#opsBody"); b.innerHTML = `<p class="muted">Yuklanmoqda…</p>`;
  const d = await J("/api/ops/calls/plan"), s = d.summary, A = s.alternatives || {};
  b.innerHTML = `<div class="card" style="margin-bottom:12px;${s.shortfall_today || s.projected_late ? "border-color:color-mix(in srgb,var(--bad) 40%,transparent)" : ""}">
      <h3 style="margin:0 0 6px">${ico("phone", 18)} Call-markaz: imkoniyat va muddatlar</h3><p style="margin:0;font-size:14px">${esc(s.text)}</p>
      <div class="ops-strip"><span class="chip-s">Jami navbat: <b>${fmt(s.total)}</b></span><span class="chip-s">Bugungi ro'yxat: <b>${fmt(s.today)}</b></span>
        <span class="chip-s">Muddati o'tgan: <b class="${s.late ? "bad" : ""}">${fmt(s.late)}</b></span><span class="chip-s">Rejaga ko'ra kechikadi: <b class="${s.projected_late ? "bad" : ""}">${fmt(s.projected_late)}</b></span>
        <span class="chip-s">Reja ufqi: <b>${s.last_day ? dmy(s.last_day) : "—"}</b> (~${s.days} ish kuni)</span></div></div>
    <div class="grid g2" style="align-items:start">
      <div class="card"><h3>Muddat va jiddiylik bo'yicha</h3>${tbl(["Turi", "#Soni", "Muddat", "#O'tgan", "#Kechikadi"], s.groups.map(g => [esc(g.label), fmt(g.n),
          `<span class="tiny">${dtm(g.first_due)}${g.last_due !== g.first_due ? ` … ${dtm(g.last_due)}` : ""}</span>`, g.late ? `<b class="bad">${fmt(g.late)}</b>` : "0", g.proj ? `<b class="bad">${fmt(g.proj)}</b>` : "0"]))}
        <h3 style="margin-top:14px">Kunlar bo'yicha reja</h3>${tbl(["Kun", "#Qo'ng'iroq", "#Muddatidan keyin"], d.plan.map(p => [dmy(p.day), fmt(p.n), p.late ? `<span class="bad">${fmt(p.late)}</span>` : "0"]))}</div>
      <div>
        <div class="card" style="margin-bottom:12px"><h3>${ico("mail", 18)} 1. Kontrakt eslatmasi — ommaviy SMS / Telegram</h3>
          <p class="tiny muted" style="margin:0 0 8px">To'lov sanasi hali o'tmagan (past jiddiylik) <b>${fmt(A.sms || 0)}</b> ta eslatma qo'ng'irog'ini bitta xabar bilan almashtirish. To'lanmasa, sana o'tgach qo'ng'iroq qaytadan navbatga tushadi.</p>
          ${d.can_plan && A.sms ? `<div class="row-actions"><button class="btn sm" data-ntf="sms">SMS (${fmt(A.sms)} ta)</button><button class="btn sm" data-ntf="telegram">Telegram (${fmt(A.sms)} ta)</button></div>` : ""}<div id="clNtf"></div></div>
        <div class="card" style="margin-bottom:12px"><h3>${ico("users", 18)} 2. Kechikadiganlarni taqsimlash</h3>
          <p class="tiny muted" style="margin:0 0 8px">Rejaga ko'ra muddatidan keyin qilinadigan <b>${fmt(A.overflow || 0)}</b> ta qo'ng'iroq (kontrakt eslatmasidan tashqari). Tyutorga — o'z guruhi talabalari (sirtqi — Sirtqi bo'limga), har biriga kuniga ≤ ${A.tutor_capacity}; Registrator xodimiga — kuniga ≤ ${A.staff_capacity}. Muddat o'zgarmaydi.</p>
          ${d.can_plan && A.overflow ? `<div class="row-actions"><button class="btn sm" data-rd="tyutor">Tyutorlarga (${A.tutors} nafar)</button><button class="btn sm" data-rd="registrator_xodim">Registrator xodimiga (${A.staff} nafar)</button></div>` : ""}<div id="clRd"></div></div>
        <div class="card"><h3>${ico("wrench", 18)} 3. Operatorlar va kunlik me'yor</h3>
          ${tbl(["Operator", "#Kuniga", "Faol"], d.operators.map(o => [esc(o.short || o.full_name), d.can_plan ? `<input type="number" min="0" max="300" value="${o.capacity}" data-cap="${o.id}" aria-label="Kunlik me'yor" style="width:80px;padding:6px 8px;border:1px solid var(--line-2);border-radius:8px;background:var(--surface)">` : o.capacity,
            d.can_plan ? `<input type="checkbox" data-act="${o.id}" ${o.active ? "checked" : ""} aria-label="Faol">` : (o.active ? "ha" : "yo'q")]))}
          ${d.can_plan ? `<div class="row-actions" style="margin-top:8px"><button class="btn sm primary" id="clSave">Saqlash va qayta rejalashtirish</button></div>` : ""}
          <p class="tiny muted" style="margin:8px 0 0">Kunlik imkoniyat — faol operatorlar me'yorlari yig'indisi (hozir ${fmt(s.capacity)} ta). Yangi operator — «Akkauntlar» bo'limida «Call-markaz operatori» lavozimi bilan qo'shiladi; navbat operatorlarga me'yoriga mutanosib taqsimlanadi.</p></div>
      </div></div>`;
  const confirmBox = (box, html, run) => { box.innerHTML = `<div class="res" style="margin-top:8px">${html}<div class="row-actions" style="margin-top:8px"><button class="btn sm primary">Tasdiqlash</button><button class="btn sm ghost">Bekor</button></div></div>`;
    const [ok, no] = box.querySelectorAll("button"); no.onclick = () => { box.innerHTML = ""; }; ok.onclick = () => busy(ok, run); };
  b.querySelectorAll("[data-ntf]").forEach(x => x.onclick = () => busy(x, async () => {
    const ch = x.dataset.ntf, p = await J("/api/ops/calls/notify", {method: "POST", body: JSON.stringify({channel: ch, preview: true})});
    confirmBox($("#clNtf"), `<b>${fmt(p.n)} ta ${esc(p.channel)} eslatma</b>${p.no_phone ? ` (${p.no_phone} tasida telefon yo'q)` : ""}<div class="tiny" style="margin:6px 0">Namuna: «${esc(p.sample || "")}»</div><div class="tiny muted">${esc(p.gateway)} ${esc(p.effect)}</div>`,
      async () => { const r = await J("/api/ops/calls/notify", {method: "POST", body: JSON.stringify({channel: ch, preview: false})}); toast(`${fmt(r.sent)} ta ${r.channel} eslatma navbatga yozildi`); refreshOpsSummary(); opsCalls(); });
  }));
  b.querySelectorAll("[data-rd]").forEach(x => x.onclick = () => busy(x, async () => {
    const tg = x.dataset.rd, p = await J("/api/ops/calls/redistribute", {method: "POST", body: JSON.stringify({target: tg, preview: true})});
    confirmBox($("#clRd"), p.n ? `<b>${fmt(p.n)} ta qo'ng'iroq o'tkaziladi</b>: ${p.by_role.map(r => `${esc(r.label)} — ${fmt(r.n)}`).join(", ")}. Shundan keyin ham ${fmt(p.left)} tasi navbatda qoladi.` : "O'tkaziladigan qo'ng'iroq yo'q (me'yor to'lgan yoki mos talaba yo'q).",
      async () => { if (!p.n) return; const r = await J("/api/ops/calls/redistribute", {method: "POST", body: JSON.stringify({target: tg, preview: false})}); toast(`${fmt(r.moved)} ta qo'ng'iroq o'tkazildi`); refreshOpsSummary(); opsCalls(); });
  }));
  if ($("#clSave")) $("#clSave").onclick = () => busy($("#clSave"), async () => {
    const items = d.operators.map(o => ({user_id: o.id, capacity: +b.querySelector(`[data-cap="${o.id}"]`).value || 0, active: b.querySelector(`[data-act="${o.id}"]`).checked}));
    await J("/api/ops/calls/operators", {method: "POST", body: JSON.stringify({items})}); toast("Me'yor saqlandi — navbat qayta rejalashtirildi"); refreshOpsSummary(); opsCalls();
  });
  hydrateIcons(b);
}

/* --- talaba kartasi --- */
async function opsStudent(sid) {
  const b = $("#opsBody"); b.innerHTML = `<p class="muted">Yuklanmoqda…</p>`;
  const d = await J(`/api/ops/student/${sid}`);
  const s = d.student, f = d.facts;
  const back = `<button class="btn ghost sm" id="opsBack" style="margin-bottom:10px">← Ortga</button>`;
  if (d.limited) {
    b.innerHTML = back + `<div class="card"><h3>${esc(s.full_name)}</h3><p class="muted">${esc(s.grp)} · ${esc(s.faculty)} · <span class="phone">${esc(s.phone)}</span></p>
      <p class="tiny muted">Call-markaz uchun faqat qo'ng'iroq topshiriqlari ko'rinadi.</p></div><div class="ops-tasks" style="margin-top:14px">${d.tasks.map(t => opsTaskCard({...t, full_name: s.full_name, grp: s.grp, faculty: s.faculty, phone: s.phone, rule: "", facts: {}})).join("")}</div>`;
    $("#opsBack").onclick = () => { OPSV.student = null; renderOps(); }; bindTaskActions(b, () => opsStudent(sid)); return;
  }
  const open = d.cases.filter(c => c.status === "ochiq");
  b.innerHTML = back + `<div class="card ops-hero"><div><h3 style="margin:0">${esc(s.full_name)}</h3>
      <div class="muted tiny">${esc(s.grp)} · ${s.course}-kurs · ${esc(s.faculty)} · HEMIS ${esc(s.hemis_id)}${s.phone ? ` · <span class="phone">${esc(s.phone)}</span>` : ""} · holati: ${esc(s.status)}</div></div>
      <div class="ops-facts"><div><span>Sababsiz</span><b class="${f.unexcused >= 30 ? "bad" : ""}">${f.unexcused} soat</b></div><div><span>Sababli</span><b>${f.excused} soat</b></div>
      <div><span>GPA (5), kumulyativ</span><b class="${f.gpa5 != null && f.gpa5 < 3 ? "bad" : ""}">${f.gpa5 ?? "—"}</b></div><div><span>Akademik qarz</span><b class="${f.fails.length ? "bad" : ""}">${f.fails.length}</b></div>
      <div><span>Kontrakt qarzi</span><b class="${d.debt > 0 ? "bad" : ""}">${s.payment_type === "kontrakt" ? som(d.debt) : "grant"}</b></div></div></div>
    <div class="dec-grid">
      <div class="dec-tasks">
        <div class="card"><h3>Ochiq holatlar (${open.length})</h3>${open.length ? open.map(c => `<div class="dec-line"><span class="dl-unit">${OPS_RULES[c.rule]}</span><span>${lvlTag(c.level)}</span><span class="tiny muted">${dtm(c.opened_at)}</span><span class="dl-res">${factText(c.rule, c.facts)}</span></div>`).join("") : `<p class="muted"><span class="good">${ico("checkc", 16)}</span> Ochiq holat yo'q</p>`}</div>
        <div class="card"><h3>Topshiriqlar</h3><div class="ops-tasks">${d.tasks.filter(t => t.status === "yangi").map(t => opsTaskCard({...t, full_name: s.full_name, grp: s.grp, faculty: s.faculty, phone: s.phone, rule: (d.cases.find(c => c.id === t.case_id) || {}).rule, facts: (d.cases.find(c => c.id === t.case_id) || {}).facts || {}})).join("") || `<p class="muted">Ochiq topshiriq yo'q</p>`}</div>
          ${d.tasks.some(t => t.status !== "yangi") ? `<details style="margin-top:10px"><summary class="tiny muted">Yopilgan topshiriqlar (${d.tasks.filter(t => t.status !== "yangi").length})</summary>${tbl(["Topshiriq", "Natija", "Sana"], d.tasks.filter(t => t.status !== "yangi").map(t => [esc(t.title), esc((t.outcome || "") + (t.note ? " — " + t.note : "") + (t.doc_reg ? " · " + t.doc_reg : "")), dtm(t.done_at)]))}</details>` : ""}</div>
        <div class="card"><h3>O'zlashtirish: akademik qarzlar va joriy oraliq nazorat</h3>${tbl(["Fan", "Natija", ""], f.grades.map(g => [esc(g.subject), `<b class="${(g.fail ?? g.score < 40) ? "bad" : ""}">${esc(String(g.shown ?? g.score))}</b>`,
          (g.fail ?? g.score < 40) && d.can_retake && !d.retakes.some(r => r.subject === g.subject && ["berildi", "topshirildi"].includes(r.status)) ? `<button class="btn sm" data-rt="${esc(g.subject)}">Otrabotka varaqasi</button>` :
          (d.retakes.find(r => r.subject === g.subject) ? (rt => rt.status === "berildi" && window.RG ? RG.cd(rt) : `<span class="tiny muted">otrabotka: ${esc(rt.status)}</span>`)(d.retakes.find(r => r.subject === g.subject)) : "")]))}</div>
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
  if (window.RG) RG.cardExtras(b, d, sid);   /* ruxsatnoma, shaxsiy grafik, kontrakt muddatini uzaytirish, otrabotka muddatlari */
  hydrateIcons(b);
}

/* --- otrabotka --- */
async function opsRetakes() {
  const b = $("#opsBody");
  const rows = await J("/api/ops/retakes");
  const ST = {berildi: ["Varaqa berildi", "mid"], topshirildi: ["Tekshiruvda", "gray"], tasdiqlandi: ["Tasdiqlandi", "low"]};
  const up = ["talabalar", "registrator_xodim", "tyutor", "sirtqi"].includes(ME.role_key);   /* varaqa va skan: Registrator ofisi, tyutor, Sirtqi bo'lim (Imtihon bo'limi — faqat ko'radi) */
  b.innerHTML = `<div class="src-note">${ico("info", 15)}<span>Varaqa QR va ro'yxat raqami bilan 3 kunga beriladi: <span class="tag low">yashil</span> → 2 kun qolganda <span class="tag mid">sariq</span> → 1 kun qolganda va muddat o'tganda <span class="tag high">qizil</span> (tyutor va call-markazga topshiriq).
      Yuklangan skan o'qiladi: ro'yxat raqami → otrabotka, o'qituvchi imzosi, ball; registrator skan bilan <b>yonma-yon</b> tekshirib tasdiqlaydi.</span></div>
    ${up ? `<div class="rg-auto"><label class="btn sm">${ico("file", 15)} Skanni yuklash — raqam bo'yicha avtomatik<input type="file" id="rgAuto" accept="application/pdf,image/jpeg,image/png" hidden></label><span class="tiny muted">yoki ro'yxatdagi otrabotka qatoridan yuklang</span></div>` : ""}
    <div class="card" style="margin-top:12px">${tbl(["Talaba", "Fan", "Varaqa", "Muddat", "Holat", ""], rows.map(r => [`<b>${esc(r.full_name)}</b><div class="tiny muted">${esc(r.grp)}${r.study_form === "sirtqi" ? " · sirtqi" : ""}</div>`, esc(r.subject),
      esc(r.reg_no || "—"), r.status === "berildi" ? `${dtm(r.due_at)}<div>${window.RG ? RG.cd(r) : ""}</div>` : dtm(r.due_at),
      `<span class="tag ${(ST[r.status] || ["", "gray"])[1]}">${(ST[r.status] || [r.status])[0]}</span>${r.status === "tasdiqlandi" ? `<div class="tiny muted">${r.score_old} → <b>${r.score_new}</b></div>` : ""}${r.status === "topshirildi" && window.RG ? RG.scanFlags(r) : ""}`,
      r.status === "berildi" && up ? `<label class="btn sm">Skan yuklash<input type="file" accept="application/pdf,image/jpeg,image/png" data-up="${r.id}" hidden></label>${window.RG ? RG.retakeTools(r) : ""}` :
      r.status === "topshirildi" ? `<button class="btn sm primary" data-rv="${r.id}">Tekshirish</button>` : ""]))}</div><div id="rtReview"></div>`;
  b.querySelectorAll("[data-up]").forEach(inp => inp.onchange = async () => {
    const file = inp.files[0]; if (!file) return;
    if (file.size > 10e6) return toast("Fayl 10 MB dan katta");
    const data = await new Promise((ok, no) => { const fr = new FileReader(); fr.onload = () => ok(fr.result); fr.onerror = no; fr.readAsDataURL(file); });
    try { const r = await J(`/api/ops/retakes/${inp.dataset.up}/upload`, {method: "POST", body: JSON.stringify({data_url: data})}); toast(r.scan?.signed === false ? "Skan yuklandi — imzo aniqlanmadi, tekshiring" : "Skan yuklandi va o'qildi — registrator tekshiradi"); opsRetakes(); refreshOpsSummary(); } catch (e) {}
  });
  const after = () => { opsRetakes(); refreshOpsSummary(); };
  b.querySelectorAll("[data-rv]").forEach(x => x.onclick = () => RG.review(rows.find(r => r.id === +x.dataset.rv), after));
  if (window.RG) RG.bindRetakes(b, after);
  hydrateIcons(b);
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
  /* ruxsat yo'q hisobotlar ko'rsatilmaydi («Lavozimingiz uchun ruxsat yo'q» kartalari — shovqin) */
  const mine = REP.filter(([, , , res]) => ok(res));
  const desk = DESK_ROLES.includes(ME.role_key) && ME.role_key !== "yuridik" ? `<div class="card"><h3>${ico("chart", 18)} Ish stoli jadvali (CSV)</h3><p class="muted">Boshqaruv panelidagi ko'rsatkichlar va kesim jadvali — Excel uchun</p><a class="btn" href="/api/desk/export.csv" download>Yuklab olish (.csv)</a></div>` : "";
  $("#v-reports").innerHTML = `<div class="head"><div><h2>Tahliliy hisobotlar</h2><span class="muted">Word hisobotlar, bir tugmada — faqat ruxsatingiz doirasida. Rasmiy buyruqlar — «Buyruqlar»da, ma'lumotnomalar — «Hujjatlar markazi»da.</span><span id="repSrc"></span></div></div>
  <div class="grid g2">${mine.map(([k, t, d]) => `<div class="card"><h3>${ico("report", 18)} ${t}</h3><p class="muted">${d}</p><a class="btn primary" href="/api/report/${k}" download>Yuklab olish (.docx)</a></div>`).join("")}${desk}</div>
  ${!mine.length && !desk ? `<div class="card"><p class="muted">Lavozimingiz uchun tahliliy hisobot yo'q.</p></div>` : ""}`;
  syncInfo().then(s => { const e = $("#repSrc"); if (e) e.outerHTML = pgSrc(`Manba: HEMIS va buxgalteriya (sinov ma'lumotlari)${s.updated ? ` · yangilandi <b>${whenTxt(s.updated)}</b>` : ""} · hisobot yuklab olingan paytdagi holat bo'yicha tuziladi`); }).catch(() => {});
}

/* ---------- docs ---------- */
const DOCSAMPLE = {translate: `Dear Colleagues,\n\nFollowing our recent meeting, we would like to propose extending our Memorandum of Understanding for another five years and adding a joint summer school in Data Science for 20 students from each side. Please let us know if ISFT could host the first edition in July 2027.\n\nBest regards,\nInternational Office, Partner University (sample)`,
  contract: `HAMKORLIK SHARTNOMASI\n3.2. Institut har chorakda 45 000 000 so'm miqdorida litsenziya to'lovini oldindan to'laydi.\n4.1. Pudratchi shartnomani 10 kunlik ogohlantirish bilan bir tomonlama bekor qilishi mumkin.\n5.3. Loyiha davomida yaratilgan barcha dasturiy ta'minot va ma'lumotlar Pudratchining mulki hisoblanadi.\n6.1. To'lov 5 kundan ortiq kechiktirilsa, har bir kun uchun 0,5% penya undiriladi, umumiy summa cheklanmagan.\n8.2. Nizolar Pudratchi joylashgan joydagi sudda ko'riladi.`,
  reply: `Dear ISFT team,\nWe are interested in sending 6 exchange students to your Finance programme for the spring 2027 semester. Could you confirm available courses in English and accommodation options?\nKind regards, Partner University (sample)`};
const DOCSV = {mode: null};   /* boshqa sahifadan ochilganda tanlangan rejim (masalan, yuridik ish stoli → «Shartnoma») */
const DOC_SRC = {ai: "", qoida: "Qoida asosida (AI o'chiq)"};
function renderDocs() {
  const tools = AIS?.tools || {}, reason = AIS?.reason || "AI hozir mavjud emas";
  /* tool: "ai" | "qoida" | null — null bo'lsa tugma o'chiq, sababi ko'rsatiladi */
  const tb = (m, i, t) => { const st = m in tools ? tools[m] : "ai", off = st == null;
    return `<button class="btn${DOCSV.mode === m ? " primary" : ""}" data-m="${m}"${off ? ` disabled title="${esc(reason)}"` : st === "qoida" ? ` title="Qoida asosida ishlaydi (AI o'chiq)"` : ""}>${ico(i, 16)} ${t}${st === "qoida" ? ` <span class="tag gray">qoida</span>` : ""}</button>`; };
  $("#v-docs").innerHTML = `<div class="head"><div><h2>Tarjima va shartnoma yordamchisi</h2><span class="muted">Xorijiy xat tarjimasi, shartnomadagi xavfli bandlar va javob loyihasi. Matn institut serverida qayta ishlanadi — tashqariga chiqmaydi. Bo'limlararo xatlar — «Portal»da.</span><span id="docAi"></span></div></div>
  <div class="card"><div class="row-actions" style="margin-bottom:10px">
    ${tb("translate", "globe", "Tarjima qilish")}${tb("contract", "scale", "Shartnomani tekshirish")}${tb("reply", "mail", "Javob loyihasi")}
    <span class="muted tiny" style="align-self:center">Namuna: <a href="#" data-s="translate">xat</a> · <a href="#" data-s="contract">shartnoma</a> · <a href="#" data-s="reply">so'rov</a></span></div>
  <textarea id="docText">${esc(DOCSAMPLE.contract)}</textarea><div id="docRes" class="res muted">Natija shu yerda chiqadi.</div></div>`;
  const aiNote = () => { const e = $("#docAi"); if (!e || !AIS) return; const off = Object.values(AIS.tools || {}).some(v => v == null);
    e.outerHTML = pgSrc(AIS.ai ? `AI faol${AIS.local ? " (mahalliy)" : ""}: <b>${esc(AIS.model || "")}</b>` : `${esc(AIS.reason || "Tahlil rejimi")}${off ? " O'chiq tugmalar ustiga olib boring — sababi ko'rsatiladi." : ""}`, AIS.ai ? "server" : "info"); };
  if (AIS) aiNote(); else status().then(() => { if ($("#docAi")) renderDocs(); });
  document.querySelectorAll("[data-s]").forEach(a => a.onclick = e => { e.preventDefault(); $("#docText").value = DOCSAMPLE[a.dataset.s]; });
  document.querySelectorAll("[data-m]").forEach(b => b.onclick = async () => {
    const res = $("#docRes"); res.className = "res"; res.textContent = "ISFT Core tahlil qilmoqda…"; DOCSV.mode = b.dataset.m;
    try { const r = await J("/api/doc", {method: "POST", body: JSON.stringify({text: $("#docText").value, mode: b.dataset.m})});
      if (r.ai === false && !r.source) { res.className = "res muted"; res.textContent = r.reason || "Bu vosita hozir mavjud emas"; return; }
      res.innerHTML = (r.source === "qoida" ? `<span class="tag gray" style="margin-bottom:6px">${DOC_SRC.qoida}</span><br>` : "") + rich(r.result || ""); }
    catch (e) { res.textContent = e.message === "denied" ? "Ruxsat yo'q" : "Xatolik"; }
  });
}

/* ---------- rbac ---------- */
async function renderRbac() {
  const {roles, labels, full} = await J("/api/rbac");
  const keys = Object.keys(labels);
  $("#v-rbac").innerHTML = `<div class="head"><div><h2>Ruxsat darajalari (RBAC)</h2><span class="muted">Har bir so'rov bajarilishidan oldin shu jadval bo'yicha tekshiriladi. Siz: <b>${esc(ME.role)}</b>${full ? "" : " — quyida faqat sizning lavozimingiz ruxsatlari (to'liq jadval rahbariyat va tizim ma'murida)"}</span></div></div>
  <div class="card"><div class="tw"><table class="rbac"><thead><tr><th>Lavozim</th>${keys.map(k => `<th title="${esc(labels[k])}">${esc(labels[k])}</th>`).join("")}<th>Ko'lam</th></tr></thead><tbody>
  ${roles.map(r => `<tr class="${r.key === ME.role_key ? "me" : ""}"><td><b>${esc(r.title)}</b>${r.local_only ? `<br><span class="tag gray">faqat mahalliy</span>` : ""}</td>${keys.map(k =>
    r.allow.includes(k) ? (r.aggregate_only.includes(k) ? `<td class="a" title="Faqat jamlangan">Σ</td>` : `<td class="y">${ico("check", 16)}</td>`) : `<td class="x">—</td>`).join("")}<td class="tiny">${esc(r.scope)}</td></tr>`).join("")}
  </tbody></table></div><p class="tiny muted"><span class="good">${ico("check", 14)}</span> — to'liq ruxsat · Σ — faqat jamlangan (shaxsiy ma'lumotsiz) · — — ruxsat yo'q. Telegram kanalida ish haqi va kadrlar ma'lumoti hech kimga chiqmaydi.</p></div>
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
  el.innerHTML = `<div class="head"><div><h2>Audit jurnali</h2><span class="muted">Oxirgi 50 ta so'rov · rad etilganlar qizil</span></div><button class="btn" onclick="renderAudit()">${ico("refresh", 16)} Yangilash</button></div>
  <div class="card">${tbl(["Vaqt", "Foydalanuvchi", "Kanal", "Amal", "Natija", "Izoh"], rows.map(a => [`${dmy(a.ts)} ${esc(a.ts.slice(11, 16))}`, esc(a.role), esc(a.channel), esc(a.action),
    a.allowed ? `<span class="tag low">ruxsat</span>` : `<span class="tag high">rad etildi</span>`, `<span class="tiny muted">${esc(a.detail)}</span>`]))}</div>`;
}

boot().catch(() => {});

/* ---------- Hujjatlar markazi ---------- */
const DOCSTATE = {cat: null, sel: null};
const STATUS_TXT = {berilgan: "berilgan", loyiha: "imzo kutmoqda", imzolangan: "imzolangan", bekor: "bekor qilingan"};
async function renderDocuments() {
  const el = $("#v-documents");
  el.innerHTML = `<div class="head"><div><h2>Hujjatlar markazi</h2><span class="muted">Rasmiy hujjat chiqarish: ma'lumotnoma, qaydnoma va xat — bazadan to'ldiriladi, ISFT blankida, ro'yxat raqami va QR bilan. Buyruqlar (talabalar va xodimlar) — «Buyruqlar» bo'limida; tahliliy hisobotlar — «Hisobotlar»da.</span></div></div><div id="docCat"></div><div id="docForm"></div><div id="docReg"></div>`;
  DOCSTATE.cat = await J("/api/docs/catalog");
  const cats = [...new Set(DOCSTATE.cat.map(t => t.cat))];
  const mine = DOCSTATE.cat.filter(t => t.allowed).length;
  /* avval lavozimga ochiq shablonlar; boshqa bo'limlarniki — ixcham, ochiladigan ro'yxatda */
  const cardHtml = t => `<div class="doc-card${t.allowed ? "" : " off"}" data-k="${esc(t.key)}" style="${t.allowed ? "" : "opacity:.5;cursor:not-allowed"}">
      <span class="ctag">${t.allowed ? (t.sign ? "rektor imzosi bilan" : "avtomatik") : ico("lock", 12) + " boshqa bo'lim"}</span><b>${esc(t.title)}</b><p>${esc(t.desc)}</p></div>`;
  const own = cats.map(c => [c, DOCSTATE.cat.filter(t => t.cat === c && t.allowed)]).filter(([, l]) => l.length);
  const other = DOCSTATE.cat.filter(t => !t.allowed);
  $("#docCat").innerHTML = `<p class="tiny muted">Sizning lavozimingiz uchun ${mine} ta shablon. Har bir hujjat bazadan to'ldiriladi, ro'yxat raqami va QR bilan chiqadi.</p>` +
    own.map(([c, l]) => `<div class="cat">${esc(c)}</div><div class="doc-grid">${l.map(cardHtml).join("")}</div>`).join("") +
    (other.length ? `<details style="margin-top:18px"><summary class="tiny muted" style="cursor:pointer">Boshqa bo'limlar shablonlari (${other.length}) — ular o'z mas'ullariga ochiq</summary><div class="doc-grid" style="margin-top:10px">${other.map(cardHtml).join("")}</div></details>` : "");
  el.querySelectorAll(".doc-card").forEach(c => c.onclick = () => {
    const t = DOCSTATE.cat.find(x => x.key === c.dataset.k);
    if (!t.allowed) return toast(`«${t.title}» sizning lavozimingiz uchun emas`);
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
    <div style="display:flex;gap:10px;align-items:center;margin-top:14px;flex-wrap:wrap"><button class="btn primary" id="docGo">${ico("file", 16)} Hujjatni tayyorlash</button><span id="docOut" class="tiny muted"></span></div></div>`;
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
    $("#docOut").textContent = params.use_ai ? "ISFT Core matnni yozmoqda (mahalliy AI, ~20–40 soniya)..." : "Tayyorlanmoqda...";
    try {
      const r = await J("/api/docs/issue", {method: "POST", body: JSON.stringify({key: t.key, params})});
      $("#docOut").innerHTML = `<span class="good">${ico("checkc", 16)}</span> <b>${r.count}</b> ta hujjat · ${esc(r.regs.slice(0, 3).join(", "))}${r.count > 3 ? " ..." : ""} · <span class="status ${r.status}">${STATUS_TXT[r.status]}</span>
        <a class="btn sm" href="/api/docs/file/${encodeURIComponent(r.file)}">${ico("download", 16)} Yuklab olish (.docx)</a>`;
      toast(r.count > 1 ? `${r.count} ta hujjat bitta paketda tayyor` : "Hujjat tayyor va ro'yxatga olindi"); docRegistry();
    } catch (e) { $("#docOut").textContent = e.message === "denied" ? "" : "Xatolik: " + String(e.message).slice(0, 160); }
    btn.disabled = false;
  };
}

async function docRegistry() {
  const rows = await J("/api/docs/registry");
  const isR = ME.role_key === "rektor";
  /* buyruqlar imzosi — faqat «Buyruqlar» bo'limida (yagona joy); bu yerda imzo navbati yo'q */
  const wait = rows.filter(r => r.status === "loyiha").length;
  const ordNav = !document.querySelector('#nav a[data-v="orders"]')?.classList.contains("hidden");
  $("#docReg").innerHTML = `<div class="card" style="margin-top:16px"><div class="head" style="margin-bottom:10px"><div><h3 style="margin:0">Hujjatlar jurnali (reyestr)</h3>
    <span class="tiny muted">${isR ? "Institut bo'yicha barcha hujjatlar" : "Siz tayyorlagan hujjatlar"} · ${rows.length} ta${wait ? ` · ${wait} ta loyiha` : ""}</span></div>
    ${ordNav ? `<button class="btn sm" data-go-orders>${ico("file", 16)} Buyruqlar (imzo va kelishuv)</button>` : ""}</div>
    ${rows.length ? tbl(["Raqam", "Hujjat", "Kim haqida / kimga", "Muallif", "Sana", "Holat", ""], rows.map(r => [
      `<b>${esc(r.reg_no)}</b>`, esc(r.title), esc(r.holder), `<span class="tiny">${esc(r.creator_role)}</span>`, `<span class="tiny">${dmy(r.created_at)} ${esc(r.created_at.slice(11, 16))}</span>`,
      `<span class="status ${r.status}">${STATUS_TXT[r.status] || r.status}</span>`,
      `<div style="display:flex;gap:6px;flex-wrap:wrap"><a class="btn sm" title="Yuklab olish" aria-label="Yuklab olish" href="/api/docs/file/${encodeURIComponent(r.file)}">${ico("download", 16)}</a>
       <a class="btn sm" title="QR tekshiruv sahifasi" target="_blank" aria-label="QR tekshiruv" href="/verify/${encodeURIComponent(r.verify_code)}">${ico("search", 16)}</a>
       ${r.status === "loyiha" && ordNav ? `<button class="btn sm" data-go-orders title="Buyruq loyihalari «Buyruqlar» bo'limida imzolanadi">${ico("pen", 16)} Buyruqlarda</button>` : ""}
       ${r.status !== "bekor" ? `<button class="btn sm" data-cancel="${r.id}" title="Bekor qilish" aria-label="Bekor qilish">${ico("x", 16)}</button>` : ""}</div>`]))
    : `<p class="muted">Hali hujjat tayyorlanmagan. Yuqoridan shablon tanlang.</p>`}</div>`;
  document.querySelectorAll("[data-go-orders]").forEach(b => b.onclick = () => { if (typeof OR !== "undefined") { OR.id = null; OR.tab = "reg"; OR.f.status = ""; } go("orders"); });
  /* bekor qilish qaytarib bo'lmaydi — ikki bosqichli tasdiq */
  document.querySelectorAll("[data-cancel]").forEach(b => b.onclick = () => {
    if (!b.dataset.armed) { b.dataset.armed = 1; b.textContent = "Bekor qilinsinmi?"; b.classList.add("primary"); setTimeout(() => { if (b.isConnected) { delete b.dataset.armed; b.innerHTML = ico("x", 16); b.classList.remove("primary"); } }, 3500); return; }
    busy(b, async () => { await J(`/api/docs/${b.dataset.cancel}/cancel`, {method: "POST"}); toast("Hujjat bekor qilindi — QR tekshiruvda «bekor» ko'rinadi"); docRegistry(); });
  });
}


/* ---------- Murojaatlar va nosozliklar (avval «Xizmat markazi»): QR nosozliklar · murojaatlar · tadbir qatnashuvi ---------- */
/* SVC.focus — havoladan kelgan qator (rq12 / tk5 / pr3) ajratiladi; SVC.queue === "unit" — faqat mening navbatim */
const SVC = {tab: null, data: null, focus: null, queue: null};
const SVC_TABS = {facilities: "Nosozliklar (QR)", requests: "Murojaatlar va hodisalar", procurement: "Xarid so'rovlari", events: "Tadbir qatnashuvi"};
const SVC_TABS_ICO = {facilities: "wrench", requests: "mail", procurement: "file", events: "gift"};
const ago = iso => { const m = Math.max(0, Math.round((Date.now() - new Date(iso)) / 60000)); if (m < 1) return "hozir"; return m < 60 ? `${m} daq. oldin` : m < 1440 ? `${Math.round(m/60)} soat oldin` : `${Math.round(m/1440)} kun oldin`; };
const st = s => `<span class="status ${({"hal qilindi": "imzolangan", "javob berildi": "berilgan", "jarayonda": "loyiha", "ochiq": "bekor"})[s] || ""}" style="${s === "ochiq" ? "text-decoration:none" : ""}">${esc(s)}</span>`;
async function renderService() {
  const el = $("#v-service");
  el.innerHTML = `<p class="muted">Yuklanmoqda…</p>`;
  SVC.data = await J("/api/svc/overview");
  const tabs = SVC.data.tabs;
  if (!tabs.length) { el.innerHTML = `<div class="head"><div><h2>Murojaatlar va nosozliklar</h2></div></div>` + locked("Murojaatlar va nosozliklar — xo'jalik, murojaatlar va tadbirlar mas'ullari uchun"); return; }
  if (!tabs.includes(SVC.tab)) SVC.tab = tabs[0];
  const lead = ME.role_key === "it_staff" ? "AT bo'limi navbatidagi va sizga biriktirilgan murojaatlar: «Olindi» — o'zingizga olasiz, «Hal qilindi» — yopasiz."
    : ME.role_key === "xarid" ? "Xo'jalik bo'limi «Xarid kerak» deb belgilagan nosozliklar bo'yicha xarid so'rovlari."
    : "Kelib tushgan murojaatlar, xonadagi QR orqali nosozliklar va tadbir qatnashuvi. Tizim tasniflaydi va bir xillarini birlashtiradi — qarorni mas'ul xodim qabul qiladi.";
  el.innerHTML = `<div class="head"><div><h2>Murojaatlar va nosozliklar</h2><span class="muted">${lead}</span></div>
    ${tabs.length > 1 ? `<div class="row-actions">${tabs.map(t => `<button class="btn ${t === SVC.tab ? "primary" : ""}" data-t="${t}">${ico(SVC_TABS_ICO[t], 16)} ${SVC_TABS[t]}</button>`).join("")}</div>` : ""}</div><div id="svcBody"></div>`;
  el.querySelectorAll("[data-t]").forEach(b => b.onclick = () => { SVC.tab = b.dataset.t; SVC.focus = null; SVC.queue = null; renderService(); });
  ({facilities: svcFacilities, requests: svcRequests, procurement: svcProcurement, events: svcEvents})[SVC.tab](SVC.data[SVC.tab]);
}
function svcFacilities(f) {
  const canProc = ME.role_key === "xojalik" && ME.allow.includes("procurement");
  const kp =[["Ochiq nosozliklar", f.open, `${f.rooms} ta xonada QR stiker`], ["24 soatdan oshgan", f.overdue, "javobsiz qolgan", f.overdue > 0],
              ["O'rtacha hal qilish", f.avg_hours != null ? f.avg_hours + " soat" : "—", "so'nggi 60 kun"], ["Takror xabarlar birlashtirildi", f.dup_saved, "bir muammo — bitta ish"]];
  let h = `<div class="grid g4">${kp.map(k => `<div class="card kpi ${k[3] ? "bad" : ""}"><div class="l">${k[0]}</div><div class="v">${k[1]}</div><div class="s">${k[2]}</div></div>`).join("")}</div>`;
  h += `<div class="grid g2" style="margin-top:14px">`;
  h += card(`${ico("refresh", 18)}` + " Takror buzilayotgan jihozlar <span class='muted tiny'>— 60 kunda 3+ marta</span>", f.repeat.length ? tbl(["Xona", "Jihoz", "#Marta", "#Xabarlar", "Oxirgi"], f.repeat.map(r => [esc(r.room), `<b>${esc(r.item)}</b>`, `<span class="bad">${r.n}</span>`, r.reports, ago(r.last)])) + `<p class="tiny muted">Ta'mirlash o'rniga almashtirish masalasini ko'rish tavsiya etiladi.</p>` : `<p class="muted">Yo'q</p>`);
  h += card(`${ico("qr", 18)} QR qanday ishlaydi`, `<ol class="tiny" style="margin:0;padding-left:18px;line-height:1.8"><li>Har xonaga QR stiker yopishtiriladi</li><li>Talaba yoki o'qituvchi skanerlaydi → xona <b>avtomatik</b> aniqlanadi</li><li>Muammo turini tanlaydi, xohlasa rasm qo'shadi — 15 soniya</li><li>Shu muammo allaqachon yozilgan bo'lsa — yangi ish ochilmaydi, «+1 tasdiq» bo'ladi</li></ol>
    <div class="row-actions" style="margin-top:10px"><a class="btn primary" href="/svc/qr-sheet" target="_blank">${ico("printer", 16)} QR stikerlarni chop etish</a><a class="btn" href="${esc(f.tickets[0] ? "/q/" + f.tickets[0].room_code : "#")}" target="_blank">${ico("smartphone", 16)} Talaba sahifasini ko'rish</a></div>`);
  h += `</div>`;
  h += `<div class="card" style="margin-top:14px"><div class="head" style="margin-bottom:8px"><div><h3 style="margin:0">Nosozliklar navbati</h3>${(n => n ? `<span class="tiny"><b class="bad">${n} ta yangi</b> — «Olindi» kutilmoqda (menyudagi raqam)</span>` : "")(f.tickets.filter(t => t.status === "yangi").length)}</div><span class="tiny muted">${f.by_building.map(b => `${esc(b.building)}: ${b.n}`).join(" · ")}</span></div>` +
    tbl(["#", "Xona", "Jihoz / izoh", "#Xabar", "Kelgan", "Holat", "Amal"], svcPick(f.tickets, 40, t => `tk${t.id}`).map(t => [`<span data-row="tk${t.id}">${t.id}</span>`, esc(t.room),
      `<b>${esc(t.item)}</b><br><span class="tiny muted">${esc(t.text)}${t.photo ? ` · <a href="/api/svc/photo/${esc(t.photo)}" target="_blank">${ico("camera", 14)} rasm</a>` : ""}${t.procurement_id ? ` · <b>Xarid X-${String(t.procurement_id).padStart(4, "0")}</b>` : ""}</span>`,
      t.reports > 1 ? `<b>${t.reports}</b>` : 1, `<span class="${t.overdue ? "bad" : ""}">${ago(t.created_at)}</span>`, st(t.status),
      t.status === "hal qilindi" ? `<span class="tiny muted">${t.hours} soatda</span>` : `<div class="row-actions">${t.status === "yangi" ? `<button class="btn sm" data-tk="${t.id}" data-s="jarayonda">Olindi</button>` : ""}<button class="btn sm primary" data-tk="${t.id}" data-s="hal qilindi">${ico("check", 16)} Hal qilindi</button>${canProc && !t.procurement_id ? `<button class="btn sm ghost" data-proc="${t.id}" title="Ta'mirlab bo'lmaydi — Xarid bo'limiga so'rov">Xarid kerak</button>` : ""}</div>`])) + `</div>`;
  $("#svcBody").innerHTML = h;
  document.querySelectorAll("[data-tk]").forEach(b => b.onclick = () => busy(b, async () => {
    await J(`/api/svc/tickets/${b.dataset.tk}/status`, {method: "POST", body: JSON.stringify({status: b.dataset.s})}); toast("Holat yangilandi"); renderService();
  }));
  /* «Xarid kerak» — ikki bosqichli: so'rov Xarid bo'limi navbatiga tushadi */
  document.querySelectorAll("[data-proc]").forEach(b => b.onclick = () => { if (!arm(b, "Xaridga yuborilsinmi?")) return; busy(b, async () => {
    const r = await J(`/api/svc/tickets/${b.dataset.proc}/procure`, {method: "POST", body: JSON.stringify({})}); toast(`Xarid so'rovi ${r.number} Xarid bo'limiga yuborildi`); renderService();
  }); });
}
/* navbatdan birinchi n tasi + havoladan kelgan qator (ro'yxat oxirida bo'lsa ham ko'rinsin) */
function svcPick(rows, n, key) { const out = rows.slice(0, n); const f = SVC.focus && rows.find(x => key(x) === SVC.focus); if (f && !out.includes(f)) out.unshift(f); return out; }
/* Xarid so'rovlari: Xarid bo'limi holatni yuritadi, xo'jalik va moliya prorektori — ko'radi */
function svcProcurement(p) {
  const kp = [["Ochiq so'rovlar", p.open, "yetkazilmagan"], ["Yangi", p.new, "ko'rib chiqilmagan", p.new > 0], ["Buyurtma berilgan", p.ordered, "yetkazib berish kutilmoqda"],
              ["Taxminiy summa", p.sum ? mln(p.sum) + " so'm" : "—", "ochiq so'rovlar bo'yicha"]];
  let h = `<div class="grid g4">${kp.map(k => `<div class="card kpi ${k[3] ? "bad" : ""}"><div class="l">${k[0]}</div><div class="v">${k[1]}</div><div class="s">${k[2]}</div></div>`).join("")}</div>`;
  const nxt = {"yangi": "ko'rib chiqilmoqda", "ko'rib chiqilmoqda": "buyurtma berildi", "buyurtma berildi": "yetkazildi"};
  h += `<div class="card" style="margin-top:14px"><h3>Xarid so'rovlari navbati</h3>` + (p.items.length ? tbl(["№", "Xona / jihoz", "Izoh", "Soni", "Kelgan", "Holat", "Amal"], svcPick(p.items, 60, x => `pr${x.id}`).map(x => [
    `<b data-row="pr${x.id}">X-${String(x.id).padStart(4, "0")}</b>`, `${esc(x.room)}<br><span class="tiny muted">${esc(x.item)}</span>`, `<span class="tiny">${esc(x.text || "")}${x.note ? `<br><i>${esc(x.note)}</i>` : ""}</span>`,
    x.qty, `<span class="tiny">${ago(x.created_at)}<br>${esc(x.created_by_name || "")}</span>`, st(x.status),
    p.can_status && nxt[x.status] ? `<div class="row-actions"><button class="btn sm primary" data-pr="${x.id}" data-s="${esc(nxt[x.status])}">${esc(nxt[x.status][0].toUpperCase() + nxt[x.status].slice(1))}</button>${x.status !== "buyurtma berildi" ? `<button class="btn sm ghost" data-pr="${x.id}" data-s="rad etildi">Rad etish</button>` : ""}</div>` : ""]))
    : `<p class="muted">Xarid so'rovi yo'q. Xo'jalik bo'limi nosozliklar navbatida «Xarid kerak» belgilasa — shu yerga tushadi.</p>`) + `</div>`;
  $("#svcBody").innerHTML = h;
  document.querySelectorAll("[data-pr]").forEach(b => b.onclick = () => { if (b.dataset.s === "rad etildi" && !arm(b, "Rad etilsinmi?")) return; busy(b, async () => {
    await J(`/api/svc/procurement/${b.dataset.pr}/status`, {method: "POST", body: JSON.stringify({status: b.dataset.s})}); toast("Holat yangilandi"); renderService(); if (typeof badges === "function") badges();
  }); });
}
function svcRequests(r) {
  const open = r.incidents.filter(i => i.status === "ochiq");
  const kp = [["Ochiq murojaatlar", r.open_total, r.scope], ["Faol hodisalar", open.length, open.length ? "umumiy nosozlik" : "yo'q", open.length > 0],
              ["Hodisaga birlashtirildi", r.grouped, "alohida javob shart emas"], ["Yakka ochiq murojaatlar", r.open_single, "mas'ulga yo'naltirilgan"]];
  let h = `<div class="grid g4">${kp.map(k => `<div class="card kpi ${k[3] ? "bad" : ""}"><div class="l">${k[0]}</div><div class="v">${k[1]}</div><div class="s">${esc(k[2])}</div></div>`).join("")}</div>`;
  /* mening navbatim (menyu belgisi bilan bir xil): menga biriktirilgan + bo'limim navbatidagi hech kim olmaganlar */
  const Q = r.queue || {mine: [], unit: []}, qIds = new Set([...Q.mine, ...Q.unit]);
  const reqRow = x => [`<span data-row="rq${x.id}">${x.number}</span>`, esc(x.text),
    `<span class="ctag" style="font-size:10.5px;padding:2px 8px;border-radius:20px;background:var(--accent-soft);color:var(--accent)">${esc(x.category)}</span><br><span class="tiny muted">→ ${esc(x.unit)}${x.assignee_name ? ` · <b>${x.mine ? "sizda" : esc(x.assignee_name)}</b>` : ""}</span>`,
    esc(x.channel), ago(x.created_at), st(x.status),
    ["hal qilindi", "javob berildi"].includes(x.status) ? "" : `<div class="row-actions">${x.status === "yangi" ? `<button class="btn sm" data-rq="${x.id}" data-s="jarayonda">Olindi</button>` : ""}<button class="btn sm primary" data-rq="${x.id}" data-s="hal qilindi">${ico("check", 16)} Hal qilindi</button>${r.staff?.length && x.unit === "Axborot texnologiyalari bo'limi" ? `<select class="sel-sm" data-asg="${x.id}" aria-label="Muhandisga biriktirish"><option value="">Biriktirish…</option>${r.staff.map(s => `<option value="${s.id}" ${s.id === x.assignee_user ? "selected" : ""}>${esc(s.name)}</option>`).join("")}</select>` : ""}</div>`];
  if (qIds.size) {
    const mine = r.requests.filter(x => qIds.has(x.id));
    h += `<div class="card" style="margin-top:14px"><div class="head" style="margin-bottom:8px"><div><h3 style="margin:0">Mening navbatim <span class="muted">${mine.length}</span></h3><span class="tiny muted">${Q.mine.length} ta sizga biriktirilgan${Q.unit.length ? ` · ${Q.unit.length} ta ${esc(Q.unit_name || "bo'lim")} navbatida hech kim olmagan` : ""} · menyudagi raqam shu ro'yxat</span></div></div>` +
      tbl(["№", "Matn", "Toifa → mas'ul", "Kanal", "Kelgan", "Holat", "Amal"], mine.map(reqRow)) + `</div>`;
  }
  for (const i of open) {
    h += `<div class="card" style="margin-top:14px;border-color:rgba(194,65,12,.45)"><div class="head" style="margin-bottom:6px"><div><h3 style="margin:0"><span class="bad ic-t">${ico("alert", 18)}</span>${esc(i.title)}</h3>
      <span class="tiny muted">${i.n} ta murojaat birlashtirildi · boshlandi ${ago(i.opened_at)} · oxirgisi ${ago(i.last)} · ${esc(i.category)}</span></div>${st(i.status)}</div>
      ${!r.can_broadcast ? `<p class="tiny muted">Bu umumiy hodisa — talabalarga xabarni Registrator ofisi yoki AT bo'limi boshlig'i yuboradi. ${ME.role_key === "it_staff" ? "Sizning navbatingizda" : "Sizning fakultetingizdan"} ${i.n} ta murojaat.</p>` : i.notified_at ? `<p class="tiny"><span class="good">${ico("checkc", 14)}</span> Talabalarga umumiy xabar yuborilgan (${ago(i.notified_at)}): <i>${esc(i.notice)}</i></p>` :
      `<p class="tiny muted">Tizim ${i.n} ta bir xil xabarni bitta hodisa deb aniqladi. Har biriga alohida javob yozish o'rniga — bitta umumiy xabar:</p>
      <textarea id="ntc${i.id}" style="min-height:90px" placeholder="Xabar loyihasi tayyorlanmoqda…"></textarea>
      <div class="row-actions" style="margin-top:8px"><button class="btn" data-ai="${i.id}">${ico("spark", 16)} AI bilan qayta yozish</button><button class="btn primary" data-send="${i.id}" disabled>${ico("send", 16)} ${i.n} kishiga yuborish</button></div>`}
      <div class="row-actions" style="margin-top:8px">${r.can_broadcast ? `<button class="btn sm" data-res="${i.id}">${ico("check", 16)} Hodisa hal qilindi (barchasini yopish)</button>` : ""}<button class="btn sm ghost" data-show="${i.id}">Xabarlarni ko'rish</button></div>
      <div id="incList${i.id}" class="hidden" style="margin-top:8px">${tbl(["№", "Kanal", "Matn", "Vaqt"], r.requests.filter(x => x.incident_id === i.id).map(x => [x.number, esc(x.channel), esc(x.text), ago(x.created_at)]))}</div></div>`;
  }
  h += `<div class="grid g2" style="margin-top:14px">`;
  h += card("Toifalar bo'yicha (30 kun)", bars(r.by_cat, {label: x => x.category, value: x => x.n, fmtv: (v, x) => `${v}${x.open ? ` <span class="tiny bad">(${x.open})</span>` : ""}`}) + `<p class="tiny muted">Qavsda — hali yopilmaganlari. Rahbar qaysi masala ko'p qaytayotganini ko'radi.</p>`);
  const past = r.incidents.filter(i => i.status !== "ochiq");
  h += card("Yagona murojaat oynasi", `<p class="tiny">Talaba istalgan kanaldan erkin matn yozadi — tizim toifasini va mas'ul bo'limni o'zi aniqlaydi, bir xil nosozliklarni hodisaga birlashtiradi.</p>
    <div class="row-actions"><a class="btn primary" href="/m" target="_blank">${ico("mail", 16)} Murojaat sahifasi (talaba ko'rinishi)</a></div>` +
    (past.length ? `<p class="tiny muted" style="margin-top:10px">Avvalgi hodisalar: ${past.map(i => `${esc(i.title)} — ${i.n} ta murojaat, ${ago(i.opened_at)}`).join("; ")}</p>` : ""));
  h += `</div>`;
  const singles = SVC.queue === "unit" ? [] : svcPick(r.requests.filter(x => !x.incident_id && !qIds.has(x.id)), 30, x => `rq${x.id}`);
  if (singles.length) h += `<div class="card" style="margin-top:14px"><h3>${qIds.size ? "Boshqa murojaatlar" : "Murojaatlar navbati"}</h3>` + tbl(["№", "Matn", "Toifa → mas'ul", "Kanal", "Kelgan", "Holat", "Amal"], singles.map(reqRow)) +
    `<p class="tiny muted">Toifa va mas'ul — tizim taklifi; xodim o'zgartirishi mumkin.</p></div>`;
  $("#svcBody").innerHTML = h;
  document.querySelectorAll("[data-asg]").forEach(s => s.onchange = async () => { if (!s.value) return; s.disabled = true; try { await J(`/api/svc/requests/${s.dataset.asg}/assign`, {method: "POST", body: JSON.stringify({user_id: +s.value})}); toast("Murojaat biriktirildi"); renderService(); } catch (e) { s.disabled = false; } });
  if (r.can_broadcast) for (const i of open.filter(i => !i.notified_at))
    J(`/api/svc/incidents/${i.id}/draft`, {method: "POST"}).then(j => { const t = $("#ntc" + i.id); if (t) { t.value = j.text; const s = document.querySelector(`[data-send="${i.id}"]`); if (s) s.disabled = false; } }).catch(() => {});
  document.querySelectorAll("[data-ai]").forEach(b => b.onclick = () => busy(b, async () => {
    const j = await J(`/api/svc/incidents/${b.dataset.ai}/draft?ai_=1`, {method: "POST"}); const t = $("#ntc" + b.dataset.ai); if (t) t.value = j.text;
  }, ico("spark", 16) + " AI yozmoqda… (15–25 s)"));
  /* qaytarib bo'lmaydigan amallar — ikki bosqichli tasdiq (app.js arm) */
  document.querySelectorAll("[data-send]").forEach(b => b.onclick = () => {
    const text = ($("#ntc" + b.dataset.send).value || "").trim();
    if (text.length < 20) return toast("Xabar matni juda qisqa");
    if (!arm(b, `Ha, ${b.textContent.trim()}`)) return;
    busy(b, async () => {
      const j = await J(`/api/svc/incidents/${b.dataset.send}/notify`, {method: "POST", body: JSON.stringify({text})});
      toast(`Umumiy xabar ${j.answered} ta murojaatga javob sifatida yozildi`); renderService(); if (typeof badges === "function") badges();
    }, "Yuborilmoqda…");
  });
  document.querySelectorAll("[data-res]").forEach(b => b.onclick = () => { if (!arm(b, "Ha, hodisani yopish va barcha murojaatlarni hal qilish")) return; busy(b, async () => { const j = await J(`/api/svc/incidents/${b.dataset.res}/resolve`, {method: "POST"}); toast(`Hodisa yopildi, ${j.closed} ta murojaat hal qilindi`); renderService(); if (typeof badges === "function") badges(); }); });
  document.querySelectorAll("[data-show]").forEach(b => b.onclick = () => $("#incList" + b.dataset.show).classList.toggle("hidden"));
  document.querySelectorAll("[data-rq]").forEach(b => b.onclick = () => busy(b, async () => { await J(`/api/svc/requests/${b.dataset.rq}/status`, {method: "POST", body: JSON.stringify({status: b.dataset.s})}); toast(b.dataset.s === "jarayonda" ? "Olindi — murojaat sizga biriktirildi" : "Holat yangilandi"); renderService(); if (typeof badges === "function") badges(); }));
}
function svcEvents(v) {
  const kp = [["O'rtacha qatnashuv", v.avg_pct != null ? v.avg_pct + "%" : "—", "ro'yxatdan o'tganlardan"], ["Doimiy qatnashchilar", v.regulars, "3+ tadbirga kelgan"],
              ["Yetib borilmagan guruhlar", v.unreached.length, "bu semestr 0 qatnashuv", v.unreached.length > 0], ["Tadbirlar (QR bilan)", v.events.length, "hisobot avtomatik"]];
  let h = `<div class="grid g4">${kp.map(k => `<div class="card kpi ${k[3] ? "bad" : ""}"><div class="l">${k[0]}</div><div class="v">${k[1]}</div><div class="s">${k[2]}</div></div>`).join("")}</div>`;
  const live = v.events.filter(e => e.open);
  for (const e of live) h += `<div class="card" style="margin-top:14px"><div class="head" style="margin-bottom:0"><div><h3 style="margin:0"><span class="live-dot"></span>Hozir: ${esc(e.title)}</h3><span class="tiny muted">${e.reg} kishi ro'yxatdan o'tgan · ${e.came} kishi belgilandi · QR ekranga chiqariladi, talaba telefonda HEMIS ID kiritadi</span></div>
    <div class="row-actions"><a class="btn primary" href="/svc/event-screen/${e.id}" target="_blank">${ico("monitor", 16)} QR ekranni ochish</a><button class="btn" data-ev="${e.id}" data-a="close">Ro'yxatni yopish</button></div></div></div>`;
  h += `<div class="grid g2" style="margin-top:14px">`;
  h += card("Fakultetlar kesimida qamrov", bars(v.by_faculty, {label: x => x.faculty, value: x => x.pct, max: 100, fmtv: (p, x) => `${p}%`}) + `<p class="tiny muted">Kamida bitta tadbirga kelgan talabalar ulushi.</p>`);
  h += card(`<span class="warn-t ic-t">${ico("alert", 18)}</span>` + "Hali yetib borilmagan guruhlar", v.unreached.length ? tbl(["Guruh", "Fakultet", "#Talaba"], v.unreached.map(g => [`<b>${esc(g.grp)}</b>`, esc(g.faculty), g.n])) + `<p class="tiny muted">Keyingi tadbirga shu guruhlar kuratorlari orqali alohida taklif.</p>` : `<p class="muted">Barcha guruhlar qamrab olingan</p>`);
  h += `</div><div class="card" style="margin-top:14px"><h3>Tadbirlar: ro'yxat → kelganlar</h3>` + tbl(["Tadbir", "Sana", "#Ro'yxatda", "#Keldi", "#Qatnashuv", "#Ro'yxatsiz", "QR"], v.events.map(e => [esc(e.title), dmy(e.date), e.reg, e.came,
    e.pct != null ? `<span class="${e.pct < 65 ? "bad" : ""}">${e.pct}%</span>` : "—", e.walkin,
    e.open ? `<a class="btn sm" href="/svc/event-screen/${e.id}" target="_blank" aria-label="QR ekran">${ico("monitor", 16)}</a>` : `<button class="btn sm" data-ev="${e.id}" data-a="open">Ochish</button>`])) + `</div>`;
  $("#svcBody").innerHTML = h;
  document.querySelectorAll("[data-ev]").forEach(b => b.onclick = () => busy(b, async () => { await J(`/api/svc/events/${b.dataset.ev}/${b.dataset.a}`, {method: "POST"}); renderService(); }));
}


/* ---------- Auditoriyalar bandligi (kamera — faqat odamlar soni) ---------- */
const SPC = {timer: null, data: null, room: null};
const SPC_STATE = {busy: ["Band", "busy"], free: ["Bo'sh", "free"], over: ["Sig'imdan oshgan (110%+)", "over"], ghost: ["Dars bor — xona bo'sh", "ghost"], unsched: ["Dars yo'q — 20+ kishi", "unsched"], offline: ["Kamera javob bermayapti", "offline"]};
async function renderSpaces(silent) {
  const el = $("#v-spaces");
  if (!silent) el.innerHTML = `<p class="muted">Yuklanmoqda…</p>`;
  let o;
  try { o = SPC.data = await J("/api/spaces/overview"); }
  catch (e) { if (!silent) el.innerHTML = `<div class="head"><div><h2>Auditoriyalar bandligi</h2></div></div>` + locked("Auditoriyalar bandligi — rektor, o'quv prorektori va xo'jalik bo'limi uchun"); return; }
  const k = o.kpi;
  const kp = [["Hozir band xonalar", `${k.busy_now}/${k.rooms}`, o.slot_label], ["O'rtacha bandlik", k.util + "%", "so'nggi 4 hafta, dars vaqtida"],
              ["O'rindiqlar to'lishi", k.fill + "%", "band paytda, sig'imga nisbatan"], ["Tekshirish kerak", k.ghosts, "dars bor — xona bo'sh (2 hafta)", k.ghosts > 0],
              ["Sig'imdan oshgan xonalar", k.over_rooms, `4 hafta · ${o.over_pct || 110}% dan ortiq`, k.over_rooms > 0], ["Kam ishlatiladigan", k.low_rooms, "35% dan kam band"],
              ...(k.idle_rooms != null ? [["Bo'sh turgan xonalar", k.idle_rooms, "2 hafta: jadval bor, xona bo'sh", k.idle_rooms > 0], ["Dars yo'q — xonada odam", k.unsched, `${o.unsched_min || 20}+ kishi, 2 hafta`]] : [])];
  let h = `<div class="head"><div><h2>Auditoriyalar bandligi</h2><span class="muted">Kameralar faqat <b>odamlar sonini</b> uzatadi · video saqlanmaydi · yuz aniqlash o'chirilgan · ${k.online}/${k.rooms} kamera onlayn${k.real ? ` · ${k.real} ta haqiqiy Hikvision` : " · hozircha simulyator"}</span>${pgSrc(`Manba: ${k.real ? "Hikvision kameralari va simulyator" : "kamera simulyatori"} + dars jadvali (sinov ma'lumotlari) · har ${o.poll_sec} soniyada yangilanadi, oxirgisi: <b>${whenTxt(o.now)}</b>`, "clock")}</div>
    <span class="tag low" title="Shaxsga doir ma'lumot qayta ishlanmaydi">${ico("lock", 14)} Shaxssiz ma'lumot</span></div>`;
  h += `<div class="grid ${kp.length > 6 ? "g4" : "g6"}">${kp.map(x => `<div class="card kpi ${x[3] ? "bad" : ""}"><div class="l">${x[0]}</div><div class="v">${x[1]}</div><div class="s">${esc(x[2])}</div></div>`).join("")}</div>`;
  // jonli xarita
  const blds = [...new Set(o.live.map(r => r.building))].sort();
  h += `<div class="card" style="margin-top:14px"><div class="head" style="margin-bottom:10px"><h3 style="margin:0"><span class="live-dot"></span>Jonli holat · ${esc(o.slot_label)}</h3>
    <span class="tiny muted">${Object.values(SPC_STATE).map(([t, c]) => `<span class="lg ${c}"></span>${t}`).join(" &nbsp; ")} · har ${o.poll_sec} s yangilanadi</span></div>
    <div class="bmap">${blds.map(b => `<div><div class="cat" style="margin:0 0 6px">${esc(b)}</div><div class="rgrid">${o.live.filter(r => r.building === b).map(r =>
      `<button class="rtile ${r.state}" data-room="${r.id}" title="${esc((SPC_STATE[r.state] || [r.state])[0])}${r.pct != null ? ` · ${r.count}/${r.capacity} (${r.pct}%)` : ""}${r.lesson ? " · " + esc(r.lesson.group) + " · " + esc(r.lesson.subject) : ""}">
        <b>${esc(r.name)}</b><span>${r.count ?? "—"}<small>/${r.capacity}</small></span><i>${r.pct != null ? `<em>${r.pct}%</em> ` : ""}${r.lesson ? esc(r.lesson.group) : r.kind === "kompyuter sinfi" ? "kompyuter sinfi" : "&nbsp;"}</i></button>`).join("")}</div></div>`).join("")}</div></div>`;
  h += `<div id="roomDay"></div>`;
  // issiqlik xaritasi
  const cell = v => v == null ? `<td class="hm">—</td>` : `<td class="hm" style="background:rgba(135,0,55,${(0.08 + v / 100 * .85).toFixed(2)});color:${v > 55 ? "#fff" : "inherit"}">${Math.round(v)}%</td>`;
  h += `<div class="grid g2" style="margin-top:14px">` + card(`${ico("calendar", 18)}` + " Hafta × para: o'rtacha to'lish", `<div class="tw"><table class="heat"><thead><tr><th></th>${o.slots.map(s => `<th>${s}</th>`).join("")}</tr></thead><tbody>${
      o.heatmap.map((row, i) => `<tr><th>${o.days[i]}</th>${row.map(cell).join("")}</tr>`).join("")}</tbody></table></div><p class="tiny muted">Xonalardagi odamlar soni ÷ sig'im. Och kataklar — bo'sh turgan sig'im: qo'shimcha guruh yoki kurs uchun zaxira.</p>`) +
    card(`${ico("trend_dn", 18)}` + " Kam ishlatiladigan xonalar", o.low.length ? tbl(["Xona", "#Sig'im", "#Bandlik", "#Jadvalda (haftada)"], o.low.map(r => [`<a href="#" data-room="${r.id}">${esc(r.name)}</a>`, r.capacity, `<span class="bad">${r.util}%</span>`, r.scheduled_per_week])) +
      `<p class="tiny muted">Bu xonalarni boshqa maqsadga (kovorking, laboratoriya, ijara) berish yoki jadvalni zichlashtirish mumkin.</p>` : `<p class="muted">Yo'q</p>`) + `</div>`;
  h += `<div class="grid g2" style="margin-top:14px">` +
    card(`<span class="warn-t ic-t">${ico("alert", 18)}</span>` + "Dars bor — xona bo'sh <span class='muted tiny'>— so'nggi 2 hafta · o'qituvchi ismi yashirilgan, avval o'quv bo'limi sababini aniqlaydi</span>", o.ghosts.length ? tbl(["Sana", "Para", "Xona", "Guruh · fan", ...(o.show_teacher ? ["O'qituvchi"] : []), "#Kishi"], o.ghosts.slice(0, 12).map(g => [
      `${g.date.slice(5)} <span class="tiny muted">${g.day.slice(0, 3)}</span>`, g.slot, `<span class="nowrap">${esc(g.room)}</span>`, `<span class="nowrap">${esc(g.group)}</span><br><span class="tiny muted">${esc(g.subject)}</span>`,
      ...(o.show_teacher ? [`${esc(g.teacher || "")}${g.repeat >= 3 ? ` <span class="tag high">${g.repeat} marta</span>` : ""}`] : []), g.avg])) +
      `<p class="tiny muted">Bu ayblov emas — signal: dars boshqa xonaga ko'chgan, bekor qilingan yoki o'tmagan bo'lishi mumkin. Akademik faoliyatni boshqarish bo'limi tekshiradi.</p>` : `<p class="muted">Holat yo'q</p>`) +
    card(`${ico("users", 18)}` + ` Sig'imdan oshgan xonalar <span class='muted tiny'>— ${o.over_pct || 110}% dan ortiq, 4 hafta</span>`, o.over.length ? tbl(["Xona", "#Sig'im", "#Necha marta", "#Eng ko'p"], o.over.map(x => [esc(x.room), x.capacity, `<span class="bad">${x.n}</span>`, x.max])) +
      `<p class="tiny muted">Odamlar soni sig'imdan ${(o.over_pct || 110) - 100}% dan ko'p oshsa qayd etiladi. Guruhni kattaroq xonaga ko'chirish — xavfsizlik va dars sifati uchun.</p>` : `<p class="muted">Yo'q</p>`) + `</div>`;
  if (typeof spcExtraHtml === "function") h += spcExtraHtml(o);   /* cams.js: optimallashtirish, dars yo'q — 20+ kishi, soatlar va binolar */
  // kameralar
  const realCams = o.cameras.filter(c => c.mode === "isapi");
  const camRows = o.cameras.map(c => [esc(c.room) + (c.guard ? ` <span class="tag mid" title="Ish vaqtidan tashqari kirish kuzatiladi">qo'riq</span>` : ""),
    c.mode === "isapi" ? `<b>Hikvision</b> ${esc(c.model || "")}<br><span class="tiny muted">${esc(c.scheme || "http")}://${esc(c.host)}${c.port ? ":" + c.port : ""} · kanal ${c.channel}${c.events ? " · voqealar oqimi" : ""}</span>` : `<span class="muted">Simulyator</span>`,
    `<span class="status ${c.status === "onlayn" ? "imzolangan" : c.status === "xato" ? "bekor" : "loyiha"}" style="text-decoration:none">${esc(c.status)}</span>${c.last_error ? `<br><span class="tiny bad">${esc(c.last_error)}</span>` : ""}`
      + (c.ticket_id ? `<br><span class="tiny bad">Nosozlik arizasi #${c.ticket_id} ochiq</span>` : "")
      + (c.events && c.ev_status ? `<br><span class="tiny ${String(c.ev_status).startsWith("uzildi") ? "bad" : "muted"}">voqealar: ${esc(c.ev_status)}</span>` : "")
      + (c.warnings?.length ? c.warnings.map(w => `<br><span class="tiny warn-t">${ico("alert", 13)} ${esc(w)}</span>`).join("") : ""),
    c.last_seen ? ago(c.last_seen) : "—", c.last_count ?? "—", o.can_manage ? `<button class="btn sm" data-ctest="${c.id}">Tekshirish</button>` : ""]);
  const EVK = {chiziq_kesish: "↔", hududga_kirish: "⤓", hududdan_chiqish: "⤒", odam_soni: ico("users", 14), video_yoqoldi: ico("x", 14), kamera_yopildi: ico("x", 14), kamera_siljidi: ico("alert", 14), olomon: ico("users", 14)};
  const evRows = (o.events || []).map(e => [`<span class="nowrap">${dtm(e.ts)}</span>`, esc(e.room), (e.priority ? `<span class="cm-p p${e.priority}">P${e.priority}</span> ` : `${EVK[e.kind] || "•"} `) + `${esc(e.label)}${e.state === "inactive" ? " (tugadi)" : ""}${e.note ? `<br><span class="tiny muted">${esc(e.note)}</span>` : ""}`,
    e.status ? `<span class="cm-s ${({yangi: "new", korildi: "seen", tiket: "tk", notogri: "false", yopildi: "done"})[e.status] || ""}">${esc(({yangi: "Yangi", korildi: "Ko'rildi", tiket: "Tiket", notogri: "Noto'g'ri signal", yopildi: "Yopildi", qayd: "Qayd"})[e.status] || e.status)}</span>` : e.alert ? `<span class="tag high">${esc(e.note || "ogohlantirish")}</span>` : `<span class="tiny muted">qayd</span>`]);
  h += `<div class="card" style="margin-top:14px"><div class="head" style="margin-bottom:8px"><h3 style="margin:0">${ico("camera", 18)} Kameralar</h3>${o.can_manage ? `<button class="btn sm primary" id="camAddBtn">+ Hikvision kamerani ulash</button>` : ""}</div>
    <div id="camForm"></div>
    ${realCams.length ? tbl(["Xona", "Qurilma", "Holat", "Oxirgi signal", "#Son", ""], camRows.filter((_, i) => o.cameras[i].mode === "isapi")) : `<p class="tiny muted">Haqiqiy kamera hali ulanmagan — barcha xonalar simulyatorda.</p>`}
    <details style="margin-top:8px"><summary class="tiny muted" style="cursor:pointer">Barcha ${o.cameras.length} ta xona/kamera</summary>${tbl(["Xona", "Qurilma", "Holat", "Oxirgi signal", "#Son", ""], camRows)}</details>
    ${evRows.length ? `<div class="head" style="margin:14px 0 6px"><h3 style="margin:0">Kamera voqealari (7 kun)</h3><a href="#" class="cm-evlink" onclick="event.preventDefault();go('cams')">Barcha voqealar → Kameralar va xavfsizlik</a></div>${tbl(["Vaqt", "Xona", "Voqea", "Holat"], evRows, {top: 8})}` : ""}
    <p class="tiny muted" style="margin-top:8px">Faqat raqam va voqea turi olinadi — video, kadr va yuz tasvirlari saqlanmaydi. Ulanish: lokal tarmoq, HTTP Digest (ixtiyoriy HTTPS), ISAPI.
      Kamera ${o.poll_sec * 3} soniya javob bermasa — «Murojaatlar va nosozliklar»da nosozlik arizasi avtomatik ochiladi va tiklanganda yopiladi.
      Parollar: ${o.cred_store?.encrypted ? "shifrlangan omborda" : `<span class="warn-t">bazadan ajratilgan, lekin hali shifrlanmagan (cryptography o'rnatilishi kerak)</span>`}.</p></div>`;
  el.innerHTML = h;
  el.querySelectorAll("[data-room]").forEach(b => b.onclick = ev => { ev.preventDefault(); spcRoom(+b.dataset.room); });
  el.querySelectorAll("[data-ctest]").forEach(b => b.onclick = async () => {
    b.disabled = true; b.textContent = "…";
    const j = await J(`/api/spaces/cameras/${b.dataset.ctest}/test`, {method: "POST"}).catch(() => null);
    b.disabled = false; b.textContent = "Tekshirish";
    if (j) toast(j.ok ? `${j.info}${j.count != null ? " · hozir " + j.count + " kishi" : ""}${j.warnings?.length ? " · diqqat: " + j.warnings.join("; ") : ""}` : `Diqqat: ${j.error || j.info}`);
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
  $("#roomDay").innerHTML = `<div class="card" style="margin-top:14px"><div class="head" style="margin-bottom:8px"><div><h3 style="margin:0">${esc(d.room)} — bugungi kun</h3><span class="tiny muted">Sig'im ${d.capacity} · ${d.points.length} ta o'lchov · rangli fon — jadvaldagi darslar</span></div><button class="btn sm ghost" id="rdClose" aria-label="Yopish">${ico("x", 16)}</button></div>
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
    if (j) toast(j.ok ? `${j.info}${j.count != null ? " · hozir " + j.count + " kishi" : ""}${j.warnings?.length ? " · diqqat: " + j.warnings.length + " ta ogohlantirish" : ""}` : `Diqqat: ${j.error || j.info}`);
    renderSpaces();
  };
}
