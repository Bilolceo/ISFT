/* =====================================================================
   ISFT Core — qo'shimchalar (app/extras.py bilan):
     1) Shaxsiy ma'lumotlar va parolni o'zgartirish — yon menyudagi foydalanuvchi kartasi menyusidan.
     2) Global qidiruv — Ctrl+K / ⌘K yoki tepadagi "Qidirish" tugmasi.
     3) Bildirishnomalar markazi — tepadagi qo'ng'iroqcha, har 60 soniyada (sahifa ko'rinib turganda) yangilanadi.
     4) Majlislar kalendari — "Majlislar va topshiriqlar" sarlavhasidagi "Ro'yxat | Kalendar" almashtirgichi.
   app.js yordamchilaridan foydalanadi: $, J, esc, ico, ICONS, toast, go, dmy, ME, hydrateIcons; portal.js — PT; app.js — DEC, OPSV, pnTab.
   Uslublar: extras.css (shu fayldan ulanadi; faqat umumiy tokenlar — qorong'i rejim avtomatik).
   ===================================================================== */
(function () {
  "use strict";
  if (!document.querySelector('link[href="extras.css"]')) document.head.insertAdjacentHTML("beforeend", '<link rel="stylesheet" href="extras.css">');
  Object.assign(ICONS, Object.fromEntries(Object.entries({
    bell: '<path d="M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9"/><path d="M10.3 21a1.94 1.94 0 0 0 3.4 0"/>',
    key: '<circle cx="7.5" cy="15.5" r="5.5"/><path d="m21 2-9.6 9.6M15.5 7.5l3 3L22 7l-3-3"/>',
    chevL: '<path d="m15 18-6-6 6-6"/>',
    chevR: '<path d="m9 18 6-6-6-6"/>',
    chevD: '<path d="m6 9 6 6 6-6"/>',
    eyeoff: '<path d="M9.9 4.24A9 9 0 0 1 12 4c6.5 0 10 8 10 8a17.6 17.6 0 0 1-2.16 3.19M6.6 6.6A17.4 17.4 0 0 0 2 12s3.5 8 10 8a9.7 9.7 0 0 0 5.4-1.6"/><path d="M14.12 14.12a3 3 0 1 1-4.24-4.24"/><path d="m2 2 20 20"/>',
    cmd: '<path d="M15 6v12a3 3 0 1 0 3-3H6a3 3 0 1 0 3 3V6a3 3 0 1 0-3 3h12a3 3 0 1 0-3-3"/>',
  }).filter(([k]) => !ICONS[k])));

  const IS_MAC = /Mac|iPhone|iPad/.test(navigator.platform || navigator.userAgent);
  const KBD = IS_MAC ? "⌘K" : "Ctrl K";
  const store = {
    get(k, d) { try { const v = localStorage.getItem(k); return v == null ? d : JSON.parse(v); } catch (e) { return d; } },
    set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch (e) {} },
    del(k) { try { localStorage.removeItem(k); } catch (e) {} },
  };
  const appVisible = () => { const a = document.getElementById("app"); return !!a && !a.classList.contains("hidden"); };
  const norm = s => String(s ?? "").replace(/[ʻʼ‘’`´]/g, "'").toLowerCase();
  const MONTHS = ["Yanvar", "Fevral", "Mart", "Aprel", "May", "Iyun", "Iyul", "Avgust", "Sentabr", "Oktabr", "Noyabr", "Dekabr"];
  const WD_S = ["Du", "Se", "Ch", "Pa", "Ju", "Sh", "Ya"];
  const WD_L = ["Dushanba", "Seshanba", "Chorshanba", "Payshanba", "Juma", "Shanba", "Yakshanba"];
  const pad = n => String(n).padStart(2, "0");
  const isoD = d => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
  const parseD = s => new Date(String(s).slice(0, 10) + "T00:00:00");

  /* "2 soat oldin" */
  function ago(ts) {
    const t = new Date(String(ts).length <= 10 ? ts + "T00:00:00" : ts);
    if (isNaN(t)) return "";
    const s = Math.max(0, (Date.now() - t) / 1000), m = s / 60, h = m / 60, d = Math.floor(h / 24);
    if (s < 60) return "hozirgina";
    if (m < 60) return `${Math.floor(m)} daqiqa oldin`;
    if (h < 24) return `${Math.floor(h)} soat oldin`;
    if (d === 1) return "kecha";
    if (d < 7) return `${d} kun oldin`;
    if (d < 30) return `${Math.floor(d / 7)} hafta oldin`;
    return dmy(t);
  }

  /* ---------------- fokus tuzog'i va modal oyna ---------------- */
  const FOC = 'a[href],button:not([disabled]),input:not([disabled]):not([type="hidden"]),select:not([disabled]),textarea:not([disabled]),[tabindex]:not([tabindex="-1"])';
  const focusables = root => [...root.querySelectorAll(FOC)].filter(x => x.getClientRects().length && !x.closest("[hidden]"));
  function trapTab(e, root) {
    if (e.key !== "Tab") return;
    const f = focusables(root); if (!f.length) { e.preventDefault(); return; }
    const first = f[0], last = f[f.length - 1], a = document.activeElement;
    if (!root.contains(a)) { e.preventDefault(); first.focus(); }
    else if (e.shiftKey && a === first) { e.preventDefault(); last.focus(); }
    else if (!e.shiftKey && a === last) { e.preventDefault(); first.focus(); }
  }
  let MODAL = null;
  function openModal({cls = "", label, html, onClose, labelledby}) {
    closeModal(true);
    const opener = document.activeElement;
    const ov = document.createElement("div");
    ov.className = "xt-ov " + cls;
    ov.innerHTML = `<div class="xt-dlg" role="dialog" aria-modal="true" ${labelledby ? `aria-labelledby="${labelledby}"` : `aria-label="${esc(label)}"`}>${html}</div>`;
    document.body.appendChild(ov);
    document.documentElement.classList.add("xt-lock");
    const dlg = ov.firstElementChild;
    ov.addEventListener("mousedown", e => { if (e.target === ov) closeModal(); });
    ov.addEventListener("keydown", e => {
      if (e.key === "Escape" && !e.defaultPrevented) { e.preventDefault(); e.stopPropagation(); closeModal(); return; }
      trapTab(e, dlg);
    });
    MODAL = {ov, dlg, opener, onClose};
    requestAnimationFrame(() => ov.classList.add("on"));
    return MODAL;
  }
  function closeModal(silent) {
    if (!MODAL) return;
    const m = MODAL; MODAL = null;
    m.ov.remove(); document.documentElement.classList.remove("xt-lock");
    try { m.onClose && m.onClose(); } catch (e) {}
    if (!silent && m.opener && m.opener.isConnected && typeof m.opener.focus === "function") m.opener.focus({preventScroll: true});
  }

  /* =====================================================================
     Tepadagi panel: qidiruv tugmasi va qo'ng'iroqcha
     ===================================================================== */
  const top = document.querySelector(".top-actions"), themeBtn = document.getElementById("themeBtn");
  if (top && !document.getElementById("xtSearchBtn")) {
    const html = `<button type="button" class="xt-sbtn" id="xtSearchBtn" aria-label="Qidirish (${IS_MAC ? "⌘" : "Ctrl"}+K)" aria-keyshortcuts="Control+K Meta+K" title="Qidirish (${KBD})">${ico("search", 17)}<span class="xt-sbtn-l">Qidirish…</span><kbd>${KBD}</kbd></button>
      <div class="xt-bellw"><button type="button" class="icon-btn xt-bell" id="xtBell" aria-haspopup="dialog" aria-expanded="false" aria-controls="xtNp" aria-label="Bildirishnomalar" title="Bildirishnomalar">${ico("bell")}<span class="xt-badge" id="xtBadge" hidden></span></button>
      <div class="xt-np" id="xtNp" role="dialog" aria-label="Bildirishnomalar" hidden></div></div>`;
    if (themeBtn && themeBtn.parentElement === top) themeBtn.insertAdjacentHTML("beforebegin", html); else top.insertAdjacentHTML("beforeend", html);
  }

  /* =====================================================================
     1) Profil menyusi va parolni o'zgartirish
     ===================================================================== */
  const meCard = document.querySelector(".side-foot .me");
  if (meCard && !meCard.dataset.xt) {
    meCard.dataset.xt = 1;
    meCard.classList.add("xt-me");
    meCard.setAttribute("role", "button"); meCard.tabIndex = 0;
    meCard.setAttribute("aria-haspopup", "menu"); meCard.setAttribute("aria-expanded", "false");
    meCard.setAttribute("aria-label", "Profil menyusi");
    meCard.title = "Profil: shaxsiy ma'lumotlar, parol, chiqish";
    meCard.insertAdjacentHTML("beforeend", `<span class="xt-me-chev" aria-hidden="true">${ico("chevD", 15)}</span>`);
    meCard.addEventListener("click", e => { e.stopPropagation(); toggleMenu(); });
    meCard.addEventListener("keydown", e => { if (e.key === "Enter" || e.key === " " || e.key === "ArrowUp") { e.preventDefault(); toggleMenu(true); } });
  }
  let MENU = null;
  function toggleMenu(kbd) {
    if (MENU) return closeMenu(true);
    const r = meCard.getBoundingClientRect();
    const m = document.createElement("div");
    m.className = "xt-menu"; m.setAttribute("role", "menu"); m.setAttribute("aria-label", "Profil");
    m.innerHTML = `<div class="xt-menu-h"><b>${esc(ME?.role || "")}</b><small>${esc(String(ME?.name || "").split(":").pop().trim())}</small></div>
      <button type="button" role="menuitem" data-a="profile">${ico("user", 16)}<span>Shaxsiy ma'lumotlar</span></button>
      <button type="button" role="menuitem" data-a="pw">${ico("key", 16)}<span>Parolni o'zgartirish</span></button>
      <button type="button" role="menuitem" data-a="switch">${ico("logout", 16)}<span>Chiqish</span></button>`;
    document.body.appendChild(m);
    const w = Math.max(232, Math.min(280, r.width));
    m.style.width = w + "px";
    m.style.left = Math.max(8, Math.min(r.left, innerWidth - w - 8)) + "px";
    m.style.bottom = Math.max(8, innerHeight - r.top + 6) + "px";
    MENU = m; meCard.setAttribute("aria-expanded", "true");
    const items = [...m.querySelectorAll("[role=menuitem]")];
    m.addEventListener("click", e => {
      const b = e.target.closest("[data-a]"); if (!b) return;
      closeMenu(false); document.getElementById("app")?.classList.remove("nav-open");
      if (b.dataset.a === "pw") openPassword();
      else if (b.dataset.a === "profile") openProfile();
      else doLogout();
    });
    m.addEventListener("keydown", e => {
      const i = items.indexOf(document.activeElement);
      if (e.key === "Escape") { e.preventDefault(); closeMenu(true); }
      else if (e.key === "ArrowDown") { e.preventDefault(); items[(i + 1) % items.length].focus(); }
      else if (e.key === "ArrowUp") { e.preventDefault(); items[(i - 1 + items.length) % items.length].focus(); }
      else if (e.key === "Home") { e.preventDefault(); items[0].focus(); }
      else if (e.key === "End") { e.preventDefault(); items[items.length - 1].focus(); }
      else if (e.key === "Tab") closeMenu(false);
    });
    items[0].focus({preventScroll: true});
  }
  function closeMenu(refocus) {
    if (!MENU) return;
    MENU.remove(); MENU = null; meCard?.setAttribute("aria-expanded", "false");
    if (refocus) meCard?.focus({preventScroll: true});
  }
  document.addEventListener("mousedown", e => { if (MENU && !MENU.contains(e.target) && !meCard.contains(e.target)) closeMenu(false); });

  /* shaxsiy ma'lumotlar: faqat o'zi haqida (GET /api/me/profile) — akkaunt sahifasi uslubida */
  const dmyhm = v => { const t = String(v || "").replace(" ", "T"); return t.length >= 16 ? `${t.slice(8, 10)}.${t.slice(5, 7)}.${t.slice(0, 4)}, ${t.slice(11, 16)}` : (t ? t.slice(0, 10) : "—"); };
  const PERM_GROUPS = [
    ["Ta'lim jarayoni", ["academic", "students", "ops", "rating", "masters", "admissions"]],
    ["Moliya", ["contracts", "finance", "payroll"]],
    ["Xodimlar", ["hr"]],
    ["Ilmiy va xalqaro faoliyat", ["science", "intl"]],
    ["Boshqaruv va nazorat", ["kpi", "tasks", "reports", "audit"]],
    ["Infratuzilma va xizmatlar", ["facilities", "spaces", "requests", "youth"]]];
  async function openProfile() {
    closePalette(true); closeNp(false);
    const nm = String(ME?.name || "").split(":").pop().trim();
    const ini = nm.split(/\s+/).slice(0, 2).map(w => w[0] || "").join("").toUpperCase();
    const av = ME?.photo ? `<span class="xt-pf-av has"><img src="${esc(ME.photo)}" alt=""></span>` : `<span class="xt-pf-av">${esc(ini)}</span>`;
    const M = openModal({cls: "xt-pfm", labelledby: "xtPfT", html: `
      <div class="xt-pf">
        <header class="xt-pf-hd">${av}
          <div class="xt-pf-who"><h3 id="xtPfT">${esc(nm || ME?.role || "")}</h3><p>${esc(ME?.role || "")}</p></div>
          <button type="button" class="icon-btn xt-x" data-close aria-label="Yopish">${ico("x", 18)}</button></header>
        <div id="xtPfBody" class="xt-pf-body"><p class="muted xt-pf-load">Yuklanmoqda…</p></div>
      </div>`});
    M.dlg.querySelectorAll("[data-close]").forEach(b => b.onclick = () => closeModal());
    setTimeout(() => M.dlg.querySelector(".xt-x")?.focus(), 30);
    const body = M.dlg.querySelector("#xtPfBody");
    let p;
    try {
      const r = await fetch("/api/me/profile", {credentials: "same-origin"});
      if (r.status === 401) { closeModal(); showLogin(); return; }
      if (!r.ok) throw 0;
      p = await r.json();
    } catch (e) { if (body.isConnected) body.innerHTML = `<p class="xt-form-err">Ma'lumotlarni yuklab bo'lmadi. Qayta urinib ko'ring.</p>`; return; }
    if (!body.isConnected) return;
    M.dlg.querySelector(".xt-pf-who p").textContent = `${p.position} · ${p.unit.name}`;
    const row = (k, v) => v ? `<div class="xt-pf-r"><dt>${k}</dt><dd>${v}</dd></div>` : "";
    const who = x => x ? `${esc(x.name)}<small>${esc(x.position)}</small>` : "";
    const sess = p.sessions, others = sess.filter(s => !s.current).length, SHOW = 4;
    const sessRow = s => `<li><span class="xt-pf-dev">${ico(/iPhone|Android|iPad/.test(s.device) ? "phone" : "monitor", 16)}</span>
        <div><b>${esc(s.device)}</b>${s.current ? ` <span class="xt-pf-badge">Joriy qurilma</span>` : ""}<small>IP ${esc(s.ip)} · kirgan: ${esc(dmyhm(s.created))}</small></div></li>`;
    const perms = p.allow, byKey = Object.fromEntries(perms.map(x => [x.key, x]));
    const groups = PERM_GROUPS.map(([g, ks]) => [g, ks.filter(k => byKey[k]).map(k => byKey[k])]).filter(([, xs]) => xs.length);
    const rest = perms.filter(x => !PERM_GROUPS.some(([, ks]) => ks.includes(x.key)));
    if (rest.length) groups.push(["Boshqa", rest]);
    body.innerHTML = `
      <section class="xt-pf-sec"><h4>Xizmat ma'lumotlari</h4><dl class="xt-pf-dl">
        ${row("To'liq ism", esc(p.name))}
        ${row("Lavozim", esc(p.position))}
        ${row("Bo'lim", `${esc(p.unit.name)}${p.unit.am_head ? ` <span class="xt-pf-badge">Rahbar</span>` : ""}<small>${p.unit.staff} nafar xodim</small>`)}
        ${row("Bevosita rahbar", who(p.head))}
        ${row("Kurator prorektor", who(p.curator))}
        ${row("Ma'lumot ko'lami", esc(p.scope))}
        ${p.curated.length ? row("Kuratorlikda", `${p.curated.length} ta bo'linma<small>${p.curated.slice(0, 3).map(esc).join(", ")}${p.curated.length > 3 ? ` va yana ${p.curated.length - 3} ta` : ""}</small>`) : ""}
        ${row("Akkaunt raqami", `#${p.id}`)}
      </dl></section>

      <section class="xt-pf-sec"><h4>Kirish va xavfsizlik</h4>
        <div class="xt-pf-set">
          <div><b>Parol</b><small>${p.password_changed ? `Oxirgi marta o'zgartirilgan: ${esc(dmyhm(p.password_changed))}` : `Boshlang'ich parol hali o'zgartirilmagan`}</small></div>
          <button type="button" class="btn sm" data-a="pw">O'zgartirish</button></div>
        ${p.password_changed ? "" : `<p class="xt-pf-warn">${ico("alert", 15)}<span>Xavfsizlik uchun boshlang'ich parolni almashtiring.</span></p>`}
        ${p.fails30 ? `<p class="xt-pf-warn">${ico("alert", 15)}<span>So'nggi 30 kunda ${p.fails30} ta muvaffaqiyatsiz kirish urinishi qayd etilgan.</span></p>` : ""}
        <div class="xt-pf-set xt-pf-gap">
          <div><b>Faol sessiyalar</b><small>${sess.length} ta qurilmada tizimga kirilgan</small></div>
          ${others ? `<button type="button" class="btn sm danger-ghost" id="xtPfClose">Boshqa qurilmalardan chiqish</button>` : ""}</div>
        <ul class="xt-pf-list">${sess.slice(0, SHOW).map(sessRow).join("")}</ul>
        ${sess.length > SHOW ? `<button type="button" class="xt-pf-more" id="xtPfMore">Yana ${sess.length - SHOW} ta sessiyani ko'rsatish</button>` : ""}
        ${p.logins.length ? `<details class="xt-pf-det"><summary>Kirishlar tarixi</summary>
          <table class="xt-pf-tb"><thead><tr><th>Sana</th><th>Qurilma</th><th>IP</th><th>Natija</th></tr></thead><tbody>
          ${p.logins.map(l => `<tr><td>${esc(dmyhm(l.ts))}</td><td>${esc(l.device || (l.channel === "telegram" ? "Telegram" : "—"))}</td><td>${esc(l.ip || "—")}</td>
            <td class="${l.ok ? "ok" : "bad"}">${l.ok ? "Muvaffaqiyatli" : esc(l.reason || "Rad etildi")}</td></tr>`).join("")}</tbody></table></details>` : ""}
      </section>

      <section class="xt-pf-sec"><h4>Ruxsatlar</h4>
        <p class="xt-pf-note">${perms.length} ta ma'lumot turiga ruxsat. Ruxsatlarni AT bo'limi lavozimga qarab belgilaydi.</p>
        <details class="xt-pf-det"><summary>Batafsil</summary><dl class="xt-pf-dl">
          ${groups.map(([g, xs]) => row(esc(g), xs.map(x => esc(x.label) + (x.agg ? ` <span class="xt-pf-agg" title="Faqat jamlangan ko'rinishda, shaxsiy ma'lumotlarsiz">jamlangan</span>` : "")).join("<br>"))).join("")}
        </dl></details>
      </section>

      <section class="xt-pf-sec"><h4>Telegram bildirishnomalari</h4>
        <div class="xt-pf-set">
          <div><b>${p.telegram.linked ? "Ulangan" : "Ulanmagan"}</b><small>${p.telegram.linked ? "Topshiriq va xat muddatlari, kunlik brifing Telegram'ga keladi" : "Topshiriq va xat muddatlari haqida eslatma olish uchun ulang"}</small></div>
          ${p.telegram.linked ? `<span class="xt-pf-badge ok">Faol</span>` : `<button type="button" class="btn sm" id="xtPfTg">Qanday ulanadi</button>`}</div>
        <p class="xt-pf-note" id="xtPfTgHelp" hidden>ISFT Core botini oching va bitta xabarda ulash kodingiz hamda parolingizni yuboring: <code>${esc(p.telegram.code || "KOD")} parol</code>. Parol bot tomonidan tekshiriladi va saqlanmaydi.</p>
      </section>`;
    body.querySelector("[data-a=pw]")?.addEventListener("click", () => openPassword());
    if (typeof kadrlarProfile === "function") kadrlarProfile(body);   /* kadrlar.js: o'z shaxsiy ishi (o'qish uchun) */
    body.querySelector("#xtPfTg")?.addEventListener("click", e => { body.querySelector("#xtPfTgHelp").hidden = false; e.currentTarget.remove(); });
    body.querySelector("#xtPfMore")?.addEventListener("click", e => { body.querySelector(".xt-pf-list").innerHTML = sess.map(sessRow).join(""); e.currentTarget.remove(); });
    const cb = body.querySelector("#xtPfClose");
    if (cb) cb.onclick = async () => {
      if (cb.dataset.sure !== "1") { cb.dataset.sure = "1"; cb.textContent = `${others} ta sessiyani yopishni tasdiqlang`; return; }
      cb.disabled = true;
      try {
        const r = await fetch("/api/me/sessions/close-others", {method: "POST", credentials: "same-origin"});
        const j = await r.json();
        if (!r.ok) throw 0;
        toast(`${j.closed} ta boshqa sessiya yopildi`); openProfile();
      } catch (e) { cb.disabled = false; toast("Sessiyalarni yopib bo'lmadi"); }
    };
  }

  /* parol kuchi: 0..4 */
  function pwScore(p) {
    if (!p) return 0;
    let s = 0;
    if (p.length >= 8) s++;
    if (p.length >= 12) s++;
    if (/[a-zа-я]/.test(p) && /[A-ZА-Я]/.test(p)) s++;
    if (/\d/.test(p) && /[^\p{L}\d]/u.test(p)) s++;
    else if (/\d/.test(p) && /\p{L}/u.test(p) && p.length >= 10) s++;
    if (/^(.)\1+$/.test(p) || /(1234|qwerty|parol|password|isft)/i.test(p)) s = Math.min(s, 1);
    return Math.min(4, s);
  }
  const PW_LBL = ["Juda zaif", "Zaif", "O'rtacha", "Yaxshi", "Kuchli"];
  const pwRules = p => ({len: p.length >= 8, let: /\p{L}/u.test(p), dig: /\d/.test(p)});
  const pwField = (id, label, ac, extra = "") => `<div class="xt-f" id="${id}F"><label for="${id}">${label}</label>
      <div class="xt-pw"><input id="${id}" type="password" autocomplete="${ac}" spellcheck="false" autocapitalize="off" required ${extra}>
      <button type="button" class="xt-eye" data-eye="${id}" aria-label="Parolni ko'rsatish" aria-pressed="false" aria-controls="${id}">${ico("eye", 17)}</button></div>
      <p class="xt-ferr" id="${id}E" role="alert"></p></div>`;

  function openPassword() {
    closePalette(true); closeNp(false);
    const M = openModal({cls: "xt-pwm", labelledby: "xtPwT", html: `
      <form class="xt-pwf" id="xtPwForm" novalidate>
        <div class="xt-dh"><span class="xt-dh-ic">${ico("key", 20)}</span><div><h3 id="xtPwT">Parolni o'zgartirish</h3><p class="muted">${esc(ME?.role || "")} · ${esc(String(ME?.name || "").split(":").pop().trim())}</p></div>
          <button type="button" class="icon-btn xt-x" data-close aria-label="Yopish">${ico("x", 18)}</button></div>
        <input type="text" autocomplete="username" value="${esc(ME?.name || "")}" class="xt-sr" tabindex="-1" aria-hidden="true" readonly>
        ${pwField("xtPwCur", "Joriy parol", "current-password")}
        ${pwField("xtPwNew", "Yangi parol", "new-password", 'aria-describedby="xtPwMeter xtPwRules"')}
        <div class="xt-meter" id="xtPwMeter" aria-live="polite"><div class="xt-meter-b" data-s="0"><i></i><i></i><i></i><i></i></div><span id="xtPwLbl">Parol kuchi</span></div>
        <ul class="xt-rules" id="xtPwRules"><li data-r="len">Kamida 8 ta belgi</li><li data-r="let">Kamida 1 ta harf</li><li data-r="dig">Kamida 1 ta raqam</li></ul>
        ${pwField("xtPwRep", "Yangi parolni takrorlang", "new-password")}
        <p class="xt-form-err" id="xtPwErr" role="alert" hidden></p>
        <div class="xt-acts"><button type="button" class="btn ghost" data-close>Bekor qilish</button><button type="submit" class="btn primary" id="xtPwSave">${ico("check", 16)} Saqlash</button></div>
        <p class="tiny muted xt-pw-note">${ico("shield", 13)} O'zgarish audit jurnaliga yoziladi. 10 daqiqada 5 marta noto'g'ri joriy parol kiritilsa, vaqtincha bloklanadi.</p>
      </form>`});
    const f = M.dlg, cur = f.querySelector("#xtPwCur"), nw = f.querySelector("#xtPwNew"), rep = f.querySelector("#xtPwRep");
    f.querySelectorAll("[data-close]").forEach(b => b.onclick = () => closeModal());
    f.querySelectorAll("[data-eye]").forEach(b => b.onclick = () => {
      const i = f.querySelector("#" + b.dataset.eye), show = i.type === "password";
      i.type = show ? "text" : "password"; b.setAttribute("aria-pressed", show); b.setAttribute("aria-label", show ? "Parolni yashirish" : "Parolni ko'rsatish");
      b.innerHTML = ico(show ? "eyeoff" : "eye", 17); i.focus();
    });
    const setErr = (id, msg) => { const fe = f.querySelector(`#${id}E`); fe.textContent = msg || ""; f.querySelector(`#${id}F`).classList.toggle("bad", !!msg); f.querySelector("#" + id).setAttribute("aria-invalid", msg ? "true" : "false"); };
    let touchedRep = false;
    function validate(final) {
      const p = nw.value, r = pwRules(p), s = pwScore(p);
      f.querySelectorAll("#xtPwRules li").forEach(li => li.classList.toggle("ok", r[li.dataset.r]));
      const mb = f.querySelector(".xt-meter-b"); mb.dataset.s = p ? Math.max(1, s) : 0;
      f.querySelector("#xtPwLbl").textContent = p ? PW_LBL[s] : "Parol kuchi";
      const okNew = r.len && r.let && r.dig;
      if (final || touchedRep) setErr("xtPwRep", rep.value && rep.value !== p ? "Parollar mos kelmadi" : final && !rep.value ? "Yangi parolni takrorlang" : "");
      if (final) {
        setErr("xtPwCur", cur.value ? "" : "Joriy parolni kiriting");
        setErr("xtPwNew", !p ? "Yangi parolni kiriting" : !okNew ? "Parol talablarga javob bermaydi" : p === cur.value ? "Yangi parol joriy paroldan farq qilsin" : "");
      } else if (f.querySelector("#xtPwNewF").classList.contains("bad") && okNew) setErr("xtPwNew", "");
      return cur.value && okNew && p === rep.value && p !== cur.value;
    }
    nw.oninput = () => validate(false);
    rep.oninput = () => { touchedRep = touchedRep || rep.value.length >= nw.value.length; validate(false); };
    rep.onblur = () => { if (rep.value) { touchedRep = true; validate(false); } };
    cur.oninput = () => { if (f.querySelector("#xtPwCurF").classList.contains("bad")) setErr("xtPwCur", ""); f.querySelector("#xtPwErr").hidden = true; };
    f.querySelector("#xtPwForm").onsubmit = async e => {
      e.preventDefault();
      const errBox = f.querySelector("#xtPwErr"); errBox.hidden = true;
      if (!validate(true)) { (f.querySelector(".xt-f.bad input") || cur).focus(); return; }
      const btn = f.querySelector("#xtPwSave"); if (btn.disabled) return;
      btn.disabled = true; const old = btn.innerHTML; btn.innerHTML = "Saqlanmoqda…";
      try {
        const r = await fetch("/api/me/password", {method: "POST", credentials: "same-origin", headers: {"Content-Type": "application/json"}, body: JSON.stringify({current: cur.value, new: nw.value})});
        const j = await r.json().catch(() => ({}));
        if (r.ok) { closeModal(); toast(j.message || "Parol o'zgartirildi"); return; }
        if (r.status === 401) { closeModal(); showLogin(); return; }
        const d = j.detail || {}, msg = d.message || (typeof j.detail === "string" ? j.detail : "Parolni o'zgartirib bo'lmadi");
        if (d.field === "current" && r.status !== 429) { setErr("xtPwCur", msg); cur.select(); cur.focus(); }
        else if (d.field === "new") { setErr("xtPwNew", msg); nw.focus(); }
        else { errBox.textContent = msg; errBox.hidden = false; }
      } catch (err) { errBox.textContent = "Server bilan aloqa uzildi — qayta urinib ko'ring"; errBox.hidden = false; }
      finally { if (btn.isConnected) { btn.disabled = false; btn.innerHTML = old; } }
    };
    setTimeout(() => cur.focus(), 30);
  }

  /* =====================================================================
     2) Global qidiruv (Ctrl+K / ⌘K)
     ===================================================================== */
  const RECENT_KEY = "isft-xt-recent";
  const PAL = {open: false, q: "", items: [], active: -1, ctrl: null, seq: 0, timer: 0, data: null, loading: false};
  const GROUP_IC = {talabalar: "user", guruhlar: "users", xodimlar: "shield", hujjatlar: "file", xatlar: "mail", fayllar: "folder", topshiriqlar: "tasks", sahifalar: "arrow", amallar: "bolt", recent: "history"};

  function pages() {
    const out = [];
    document.querySelectorAll("#nav a[data-v]").forEach(a => {
      if (a.classList.contains("hidden")) return;
      const c = a.cloneNode(true); c.querySelectorAll(".nb, svg").forEach(x => x.remove());
      const t = c.textContent.replace(/\s+/g, " ").trim();
      if (t) out.push({title: t, sub: "Sahifa", icon: a.dataset.i || "arrow", link: {view: a.dataset.v}});
    });
    out.push({title: "Majlislar kalendari", sub: "Sahifa · majlislar, topshiriq va xat muddatlari", icon: "calendar", link: {view: "calendar"}});
    return out;
  }
  const ACTIONS = () => [
    {title: "Parolni o'zgartirish", sub: "Amal · profil", icon: "key", action: openPassword},
    {title: "Bildirishnomalar", sub: "Amal · yangi xatlar, muddatlar, takliflar", icon: "bell", action: () => setTimeout(() => openNp(true), 30)},
    {title: "Yorug' / qorong'i rejim", sub: "Amal · mavzuni almashtirish", icon: "moon", action: () => document.getElementById("themeBtn")?.click()},
  ];

  /* belgilash: so'rov so'zlari <mark> ichida (apostrof turlari bir xil hisoblanadi) */
  function hl(text, q) {
    const s = String(text ?? ""), n = norm(s), words = norm(q).split(/\s+/).filter(w => w.length >= 1);
    if (!words.length) return esc(s);
    const mark = new Array(s.length).fill(false);
    for (const w of words) { let i = n.indexOf(w); while (i >= 0) { for (let k = i; k < i + w.length; k++) mark[k] = true; i = n.indexOf(w, i + w.length); } }
    let out = "", open = false;
    for (let i = 0; i < s.length; i++) {
      if (mark[i] && !open) { out += "<mark>"; open = true; }
      if (!mark[i] && open) { out += "</mark>"; open = false; }
      out += esc(s[i]);
    }
    return out + (open ? "</mark>" : "");
  }

  function openPalette(prefill) {
    if (!appVisible()) return;
    closeNp(false); closeMenu(false); closeCalPop();
    if (PAL.open) { PAL.input.select(); return; }
    const M = openModal({cls: "xt-palov", label: "Global qidiruv", onClose: () => { PAL.open = false; PAL.ctrl?.abort(); clearTimeout(PAL.timer); }, html: `
      <div class="xt-pal">
        <div class="xt-pal-in">${ico("search", 20)}
          <input id="xtPalQ" type="text" role="combobox" aria-expanded="true" aria-controls="xtPalList" aria-autocomplete="list" aria-activedescendant=""
            placeholder="Talaba, guruh, xodim, hujjat, xat, fayl yoki sahifa…" autocomplete="off" spellcheck="false" aria-label="Qidiruv so'rovi">
          <span class="xt-spin" id="xtPalSpin" hidden aria-hidden="true"></span>
          <button type="button" class="xt-pal-esc" data-close aria-label="Yopish"><kbd>Esc</kbd></button></div>
        <div class="xt-pal-list" id="xtPalList" role="listbox" aria-label="Qidiruv natijalari"></div>
        <div class="xt-pal-foot"><span><kbd>↑</kbd><kbd>↓</kbd> tanlash</span><span><kbd>Enter</kbd> ochish</span><span><kbd>Esc</kbd> yopish</span>
          <span class="xt-pal-ms" id="xtPalMs">${ico("shield", 13)} faqat sizga ruxsat berilgan ma'lumot</span></div>
      </div>`});
    PAL.open = true; PAL.input = M.dlg.querySelector("#xtPalQ"); PAL.list = M.dlg.querySelector("#xtPalList");
    M.dlg.querySelector("[data-close]").onclick = () => closeModal();
    PAL.input.addEventListener("input", () => { PAL.q = PAL.input.value; schedule(); });
    PAL.input.addEventListener("keydown", palKey);
    PAL.list.addEventListener("mousemove", e => { const o = e.target.closest(".xt-opt"); if (o && +o.dataset.i !== PAL.active) setActive(+o.dataset.i, false); });
    PAL.list.addEventListener("click", e => {
      const r = e.target.closest("[data-recent]"); if (r) { PAL.input.value = PAL.q = r.dataset.recent; PAL.input.focus(); schedule(0); return; }
      if (e.target.closest("[data-clear-recent]")) { store.del(RECENT_KEY); renderPal(); PAL.input.focus(); return; }
      const o = e.target.closest(".xt-opt"); if (o) choose(+o.dataset.i);
    });
    PAL.input.value = PAL.q = prefill || "";
    PAL.data = null; renderPal(); if (PAL.q) schedule(0);
    setTimeout(() => PAL.input.focus(), 20);
  }
  function closePalette(silent) { if (PAL.open) closeModal(silent); }

  function schedule(delay = 180) {
    clearTimeout(PAL.timer);
    const q = PAL.q.trim();
    if (q.length < 2) { PAL.ctrl?.abort(); PAL.data = null; spin(false); renderPal(); return; }
    renderPal();      // sahifalar darhol filtrlanadi
    PAL.timer = setTimeout(() => fetchSearch(q), delay);
  }
  const spin = on => { const s = document.getElementById("xtPalSpin"); if (s) s.hidden = !on; };
  async function fetchSearch(q) {
    PAL.ctrl?.abort(); const ctrl = PAL.ctrl = new AbortController(), my = ++PAL.seq;
    spin(true);
    try {
      const r = await fetch("/api/search?q=" + encodeURIComponent(q), {credentials: "same-origin", signal: ctrl.signal});
      if (r.status === 401) { closeModal(); showLogin(); return; }
      if (!r.ok) throw new Error(r.status);
      const j = await r.json();
      if (my !== PAL.seq || !PAL.open) return;
      PAL.data = j; renderPal();
      const ms = document.getElementById("xtPalMs"); if (ms) ms.innerHTML = `${ico("shield", 13)} faqat sizga ruxsat berilgan ma'lumot · ${j.ms} ms`;
    } catch (e) {
      if (e.name === "AbortError") return;
      if (my === PAL.seq && PAL.open) { PAL.data = {q, groups: [], error: true}; renderPal(); }
    } finally { if (my === PAL.seq) spin(false); }
  }

  function renderPal() {
    if (!PAL.list) return;
    const q = PAL.q.trim(), groups = [];
    if (!q) {
      const rec = store.get(RECENT_KEY, []);
      if (Array.isArray(rec) && rec.length) groups.push({key: "recent", title: "So'nggi qidiruvlar", recent: rec.slice(0, 6)});
      groups.push({key: "sahifalar", title: "Sahifalar", items: pages()});
      groups.push({key: "amallar", title: "Amallar", items: ACTIONS()});
    } else {
      const nq = norm(q), pg = [...pages(), ...ACTIONS()].filter(p => nq.split(/\s+/).every(w => norm(p.title).includes(w)));
      if (pg.length) groups.push({key: "sahifalar", title: "Sahifalar va amallar", items: pg.slice(0, 5)});
      if (PAL.data && PAL.data.q === q.replace(/\s+/g, " ").replace(/[ʻʼ‘’`´]/g, "'").slice(0, 60)) groups.push(...PAL.data.groups);
      else if (PAL.data) groups.push(...PAL.data.groups);   // eski natija — yangisi kelguncha
    }
    PAL.items = [];
    let html = "";
    for (const g of groups) {
      if (g.recent) {
        html += `<div class="xt-grp" role="presentation"><span>${ico("history", 13)} ${esc(g.title)}</span><button type="button" class="xt-link" data-clear-recent>Tozalash</button></div>
          <div class="xt-recent" role="presentation">${g.recent.map(r => `<button type="button" class="xt-chip" data-recent="${esc(r)}">${ico("search", 13)}${esc(r)}</button>`).join("")}</div>`;
        continue;
      }
      if (!g.items?.length) continue;
      html += `<div class="xt-grp" role="presentation" id="xtg-${esc(g.key)}"><span>${esc(g.title)}</span><em>${g.items.length}</em></div><div role="group" aria-labelledby="xtg-${esc(g.key)}">`;
      for (const it of g.items) {
        const i = PAL.items.length; PAL.items.push({...it, group: g.key});
        html += `<div class="xt-opt${it.bad ? " bad" : ""}" role="option" id="xto-${i}" data-i="${i}" aria-selected="false">
          <span class="xt-opt-ic g-${esc(g.key)}">${ico(it.icon || GROUP_IC[g.key] || "arrow", 17)}</span>
          <span class="xt-opt-b"><b>${hl(it.title, q)}</b>${it.sub ? `<small>${hl(it.sub, q)}</small>` : ""}</span>
          <span class="xt-opt-go">${esc(it.hint || (it.action ? "Bajarish" : "Ochish"))} ↵</span></div>`;
      }
      html += `</div>`;
    }
    if (q.length >= 2 && PAL.data && !PAL.items.length) {
      html = PAL.data.error ? `<div class="xt-empty">${ico("alert", 26)}<b>Qidiruvni bajarib bo'lmadi</b><span>Server bilan aloqa uzildi. Birozdan keyin qayta urinib ko'ring.</span></div>`
        : `<div class="xt-empty">${ico("search", 26)}<b>«${esc(q)}» bo'yicha hech narsa topilmadi</b><span>Ism-familiya, HEMIS ID, guruh (masalan, IQT-2501), hujjat raqami yoki xat mavzusini yozib ko'ring. Faqat lavozimingizga ruxsat berilgan ma'lumotlar qidiriladi.</span></div>`;
    } else if (q.length === 1 && !PAL.items.length) {
      html = `<div class="xt-empty sm">${ico("search", 22)}<span>Kamida 2 ta belgi yozing</span></div>`;
    } else if (q.length >= 2 && !PAL.data && !PAL.items.length) {
      html = `<div class="xt-empty sm"><span class="xt-spin"></span><span>Qidirilmoqda…</span></div>`;
    }
    if (!q) html += `<p class="xt-tip">${ico("info", 14)} Talaba (ism yoki HEMIS ID), guruh, xodim, hujjat raqami, portal xati, fayl yoki topshiriqni qidiring. Ochish uchun <kbd>Enter</kbd>.</p>`;
    PAL.list.innerHTML = html;
    PAL.active = -1; setActive(PAL.items.length ? 0 : -1, false);
  }
  function setActive(i, scroll = true) {
    PAL.list.querySelectorAll(".xt-opt.on").forEach(o => { o.classList.remove("on"); o.setAttribute("aria-selected", "false"); });
    PAL.active = i;
    const o = i >= 0 ? PAL.list.querySelector(`#xto-${i}`) : null;
    if (o) { o.classList.add("on"); o.setAttribute("aria-selected", "true"); if (scroll) o.scrollIntoView({block: "nearest"}); }
    PAL.input?.setAttribute("aria-activedescendant", o ? o.id : "");
  }
  function palKey(e) {
    const n = PAL.items.length;
    if (e.key === "ArrowDown") { e.preventDefault(); if (n) setActive((PAL.active + 1) % n); }
    else if (e.key === "ArrowUp") { e.preventDefault(); if (n) setActive((PAL.active - 1 + n) % n); }
    else if (e.key === "Home" && e.ctrlKey) { e.preventDefault(); if (n) setActive(0); }
    else if (e.key === "End" && e.ctrlKey) { e.preventDefault(); if (n) setActive(n - 1); }
    else if (e.key === "Enter") { e.preventDefault(); if (PAL.active >= 0) choose(PAL.active); else if (PAL.q.trim().length >= 2) { clearTimeout(PAL.timer); fetchSearch(PAL.q.trim()); } }
  }
  function choose(i) {
    const it = PAL.items[i]; if (!it) return;
    const q = PAL.q.trim();
    if (q.length >= 2 && !it.action) { const rec = store.get(RECENT_KEY, []); store.set(RECENT_KEY, [q, ...(Array.isArray(rec) ? rec : []).filter(r => r !== q)].slice(0, 8)); }
    closeModal(true);
    if (it.action) it.action(); else openLink(it.link);
  }

  /* ---------- havolani ochish (qidiruv, bildirishnoma, kalendar uchun umumiy) ---------- */
  function waitFor(fn, ms = 6000) {
    return new Promise(res => { const t0 = Date.now(); (function poll() { let v = null; try { v = fn(); } catch (e) {} if (v) return res(v); if (Date.now() - t0 > ms) return res(null); setTimeout(poll, 120); })(); });
  }
  const flash = el => { if (!el) return; el.scrollIntoView({block: "center", behavior: "smooth"}); el.classList.add("xt-flash"); setTimeout(() => el.classList.remove("xt-flash"), 2600); };
  function openLink(l) {
    if (!l || !l.view) return;
    const hasPT = typeof PT !== "undefined";
    switch (l.view) {
      case "ops":
        if (typeof OPSV !== "undefined") { OPSV.student = l.student; }
        go("ops"); break;
      case "portal":
        if (hasPT) {
          PT.compose = false; PT.upload = false;
          if (l.thread) { PT.tab = "mail"; PT.box = "inbox"; PT.flt = "all"; PT.q = ""; PT.open = l.thread; }
          else if (l.dataset) { PT.tab = "data"; PT.ds = l.dataset; PT.dsq = l.q || ""; PT.dsoff = 0; }
          else if (l.file) { PT.tab = "files"; PT.fq = l.file; PT.fscope = "all"; PT.funit = ""; PT.fcat = ""; }
          else if (l.compose) { PT.tab = "mail"; PT.open = null; PT.compose = true; PT.to = new Set([l.compose]); PT.att = []; }
          else if (l.flt) { PT.tab = "mail"; PT.box = "inbox"; PT.flt = l.flt; PT.q = ""; PT.open = null; }
          try { localStorage.setItem("jarvis.portalTab", PT.tab); } catch (e) {}
        }
        go("portal"); break;
      case "tasks":   /* majlis topshirig'i: {meeting, task} — qaror kartasi ochiladi va topshiriq ajratiladi */
        if (l.meeting && typeof openDecision === "function") openDecision(l.meeting, l.task);
        else if (l.directive && typeof openDirective === "function") openDirective(l.directive);   /* directives.js */
        else { if (typeof DEC !== "undefined") DEC.open = null; if (typeof DIR !== "undefined") DIR.open = null; go("tasks"); }
        break;
      case "documents":
        go("documents");
        if (l.reg) waitFor(() => [...document.querySelectorAll("#docReg tr")].find(tr => tr.textContent.includes(l.reg))).then(flash);
        break;
      case "orders":   /* Buyruqlar: {order} — buyruq sahifasi; {tab} — reyestr/chiquvchi */
        if (typeof OR !== "undefined") { OR.id = l.order || null; if (l.order || !l.tab) OR.tab = "reg"; else OR.tab = l.tab; OR.confirm = null; }
        go("orders"); break;
      case "service":  /* Murojaatlar va nosozliklar: {tab, request|ticket|procurement} — kerakli yorliq va qator ajratiladi */
        if (typeof SVC !== "undefined") { if (l.tab) SVC.tab = l.tab; SVC.focus = l.request ? `rq${l.request}` : l.ticket ? `tk${l.ticket}` : l.procurement ? `pr${l.procurement}` : null; SVC.queue = l.queue || null; }
        go("service");
        if (typeof SVC !== "undefined" && SVC.focus) { const k = SVC.focus; waitFor(() => document.querySelector(`#v-service [data-row="${k}"]`)).then(el => flash(el && (el.closest("tr") || el))); }
        break;
      case "staffabs": /* Xodimlar ta'tili: {absence} — yozuv kartasi */
        if (typeof SA !== "undefined") { SA.tab = "list"; SA.form = null; SA.open = l.absence || null; if (l.absence) SA.period = "all"; }
        go("staffabs"); break;
      case "agents":   /* AI agentlar: {action} — taklifni ko'rib chiqish oynasi */
        if (typeof AGS !== "undefined") AGS.focus = l.action || null;
        go("agents"); break;
      case "syllabus":   /* syllabus.js: sillabus / holat / so'rov */
        if (typeof sylLink === "function") sylLink(l);
        go("syllabus"); break;
      case "panel":
        go("panel");
        if (l.tab && typeof pnTab === "function") waitFor(() => document.querySelector(`#v-panel .pn-tab[data-t="${l.tab}"]`)).then(b => b && pnTab(l.tab));
        break;
      default: go(l.view);
    }
  }

  document.addEventListener("keydown", e => {
    if ((e.ctrlKey || e.metaKey) && !e.altKey && !e.shiftKey && (e.key === "k" || e.key === "K" || e.code === "KeyK")) {
      if (!appVisible()) return;
      e.preventDefault();
      if (PAL.open) closeModal(); else openPalette();
    }
  });
  document.getElementById("xtSearchBtn")?.addEventListener("click", () => openPalette());

  /* =====================================================================
     3) Bildirishnomalar markazi
     ===================================================================== */
  const NP = {data: null, open: false, timer: 0, busy: false};
  const bell = document.getElementById("xtBell"), np = document.getElementById("xtNp"), badge = document.getElementById("xtBadge");
  const N_IC = {xat: "mail", xat_muddat: "clock", topshiriq: "clock", topshiriq_muddat: "alert", agent: "spark", hujjat: "file"};
  const N_T = {xat: "Portal xati", xat_muddat: "Xat muddati", topshiriq: "Topshiriq", topshiriq_muddat: "Topshiriq muddati", agent: "AI agent", hujjat: "Hujjat"};

  async function loadNp() {
    if (!appVisible() || NP.busy) return;
    NP.busy = true;
    try {
      const r = await fetch("/api/notifications", {credentials: "same-origin"});
      if (!r.ok) return;
      NP.data = await r.json(); paintBadge(); if (NP.open) renderNp();
    } catch (e) {} finally { NP.busy = false; }
  }
  function paintBadge() {
    if (!badge || !bell) return;
    const n = NP.data?.unread || 0;
    badge.hidden = !n; badge.textContent = n > 9 ? "9+" : String(n);
    bell.setAttribute("aria-label", n ? `Bildirishnomalar: ${n} ta o'qilmagan` : "Bildirishnomalar");
    bell.classList.toggle("has", !!n);
  }
  function renderNp() {
    const d = NP.data;
    if (!d) { np.innerHTML = `<div class="xt-np-h"><b>Bildirishnomalar</b></div><div class="xt-empty sm"><span class="xt-spin"></span><span>Yuklanmoqda…</span></div>`; return; }
    const items = d.items || [];
    np.innerHTML = `<div class="xt-np-h"><div><b>Bildirishnomalar</b><small>${d.unread ? `${d.unread} ta yangi` : "Hammasi o'qilgan"}</small></div>
        <button type="button" class="xt-link" id="xtReadAll" ${d.unread ? "" : "disabled"}>${ico("check", 14)} Hammasini o'qilgan deb belgilash</button></div>
      ${items.length ? `<div class="xt-np-list" role="list">${items.map((it, i) => `<a href="#" role="listitem" class="xt-ni lv-${esc(it.level || "info")}${it.unread ? " unread" : ""}" data-i="${i}">
          <span class="xt-ni-ic" title="${esc(N_T[it.kind] || "")}">${ico(it.icon || N_IC[it.kind] || "bell", 17)}</span>
          <span class="xt-ni-b"><b>${esc(it.title)}</b>${it.sub ? `<small>${esc(it.sub)}</small>` : ""}<time datetime="${esc(it.ts)}">${esc(N_T[it.kind] || "")} · ${esc(ago(it.ts))}</time></span>
          ${it.unread ? `<i class="xt-dot" aria-label="o'qilmagan"></i>` : ""}</a>`).join("")}</div>`
      : `<div class="xt-empty">${ico("bell", 26)}<b>Yangi bildirishnoma yo'q</b><span>Yangi xatlar, muddatlar va tasdiq kutayotgan takliflar shu yerda ko'rinadi.</span></div>`}
      <div class="xt-np-f">${ico("refresh", 13)} Har daqiqada yangilanadi</div>`;
    np.querySelector("#xtReadAll")?.addEventListener("click", async e => {
      const b = e.currentTarget; b.disabled = true;
      try {
        const r = await fetch("/api/notifications/read", {method: "POST", credentials: "same-origin"});
        if (r.ok) { (NP.data.items || []).forEach(x => x.unread = false); NP.data.unread = 0; paintBadge(); renderNp(); np.querySelector(".xt-ni")?.focus(); toast("Barcha bildirishnomalar o'qilgan deb belgilandi"); }
      } catch (err) { b.disabled = false; }
    });
    np.querySelectorAll(".xt-ni").forEach(a => a.addEventListener("click", e => {
      e.preventDefault(); const it = items[+a.dataset.i]; closeNp(false); openLink(it.link);
    }));
  }
  function openNp(focus) {
    if (!np || !appVisible()) return;
    closeMenu(false); closeCalPop();
    NP.open = true; np.hidden = false; bell.setAttribute("aria-expanded", "true"); renderNp(); loadNp();
    if (focus !== false) setTimeout(() => (np.querySelector(".xt-ni") || np.querySelector("button:not([disabled])") || np).focus?.(), 30);
  }
  function closeNp(refocus) {
    if (!NP.open) return;
    NP.open = false; np.hidden = true; bell.setAttribute("aria-expanded", "false");
    if (refocus) bell.focus({preventScroll: true});
  }
  if (np) {
    np.tabIndex = -1;
    bell.addEventListener("click", e => { e.stopPropagation(); NP.open ? closeNp(false) : openNp(true); });
    np.addEventListener("keydown", e => {
      if (e.key === "Escape") { e.preventDefault(); closeNp(true); return; }
      const its = [...np.querySelectorAll(".xt-ni")], i = its.indexOf(document.activeElement);
      if (e.key === "ArrowDown" && its.length) { e.preventDefault(); its[Math.min(its.length - 1, i + 1)].focus(); }
      if (e.key === "ArrowUp" && its.length) { e.preventDefault(); its[Math.max(0, i - 1)].focus(); }
    });
    np.addEventListener("focusout", e => { if (NP.open && e.relatedTarget && !np.contains(e.relatedTarget) && e.relatedTarget !== bell) closeNp(false); });
    document.addEventListener("mousedown", e => { if (NP.open && !np.contains(e.target) && !bell.contains(e.target)) closeNp(false); });
    /* har 60 soniyada — faqat sahifa ko'rinib turganda */
    NP.timer = setInterval(() => { if (document.visibilityState === "visible") loadNp(); }, 60000);
    document.addEventListener("visibilitychange", () => { if (document.visibilityState === "visible") loadNp(); });
    /* kirish / chiqish: #app ko'rinishi o'zgarganda */
    const app = document.getElementById("app");
    if (app) new MutationObserver(() => {
      if (appVisible()) { if (!NP.data) loadNp(); }
      else { NP.data = null; paintBadge(); closeNp(false); closePalette(true); closeMenu(false); CAL.month = null; }
    }).observe(app, {attributes: true, attributeFilter: ["class"]});
    if (appVisible()) loadNp();
    setInterval(() => { if (NP.open && NP.data) np.querySelectorAll("time[datetime]").forEach(t => { const it = (NP.data.items || []).find(x => x.ts === t.getAttribute("datetime")); if (it) t.textContent = `${N_T[it.kind] || ""} · ${ago(it.ts)}`; }); }, 30000);
  }
  /* login sahifasidagi eski (0-variant) izoh ham yashirilsin */
  if (window.ISFT_HIDE_DEMO_HINT) document.querySelectorAll(".pin-demo").forEach(x => x.style.display = "none");

  /* =====================================================================
     4) Majlislar kalendari
     ===================================================================== */
  const CAL = {month: null, data: null, show: store.get("isft-xt-cal-show", {majlis: true, topshiriq: true, xat: true}), pop: null, popAnchor: null};
  const T_NAME = {majlis: "Majlis", topshiriq: "Topshiriq muddati", xat: "Xat muddati"};
  const T_IC = {majlis: "users", topshiriq: "tasks", xat: "mail"};

  function ensureSection() {
    let s = document.getElementById("v-calendar");
    if (!s) { s = document.createElement("section"); s.id = "v-calendar"; s.className = "view hidden"; (document.querySelector("#app main") || document.querySelector("main")).appendChild(s); }
    return s;
  }
  ensureSection();
  const goOrig = window.go;
  window.go = function (v) {
    closeCalPop();
    if (v !== "calendar") return goOrig.apply(this, arguments);
    const r = goOrig.call(this, "calendar");
    document.querySelectorAll("#nav a").forEach(a => a.classList.toggle("on", a.dataset.v === "tasks"));
    const cr = document.getElementById("crumb"); if (cr) cr.textContent = "Majlislar kalendari";
    renderCalendar().catch(e => { if (e?.message !== "auth") document.getElementById("v-calendar").innerHTML = typeof errCard === "function" ? errCard("calendar") : ""; });
    return r;
  };
  const segHtml = on => `<div class="xt-seg" role="group" aria-label="Ko'rinish"><button type="button" data-xv="tasks" aria-pressed="${on === "tasks"}" class="${on === "tasks" ? "on" : ""}">${ico("list", 15)}Ro'yxat</button><button type="button" data-xv="calendar" aria-pressed="${on === "calendar"}" class="${on === "calendar" ? "on" : ""}">${ico("calendar", 15)}Kalendar</button></div>`;
  function bindSeg(root) {
    root.querySelectorAll("[data-xv]").forEach(b => b.onclick = () => {
      if (b.classList.contains("on")) return;
      if (b.dataset.xv === "calendar") go("calendar"); else { if (typeof DEC !== "undefined") DEC.open = null; go("tasks"); }
    });
  }
  /* "Majlislar va topshiriqlar" sarlavhasiga almashtirgich (tasks ko'rinishi kodiga tegmasdan) */
  const vt = document.getElementById("v-tasks");
  function injectSeg() {
    if (!vt || (typeof DEC !== "undefined" && DEC.open)) return;
    const head = vt.querySelector(":scope > .head"); if (!head || head.querySelector(".xt-seg")) return;
    let acts = head.querySelector(":scope > .row-actions");
    if (!acts) {
      acts = document.createElement("div"); acts.className = "row-actions xt-acts";
      [...head.children].slice(1).forEach(ch => acts.appendChild(ch));
      head.appendChild(acts);
    }
    acts.insertAdjacentHTML("afterbegin", segHtml("tasks")); bindSeg(acts);
  }
  if (vt) new MutationObserver(injectSeg).observe(vt, {childList: true});

  async function renderCalendar(soft) {
    const el = ensureSection();
    if (!CAL.month) CAL.month = String(ME?.today || isoD(new Date())).slice(0, 7);
    if (!soft || !el.querySelector(".xt-cal")) el.innerHTML = `<div class="head"><div><h2>Majlislar kalendari</h2><span class="muted">Yuklanmoqda…</span></div><div class="row-actions">${segHtml("calendar")}</div></div><div class="card xt-cal xt-cal-load"><div class="xt-empty sm"><span class="xt-spin"></span><span>Kalendar yuklanmoqda…</span></div></div>`;
    bindSeg(el);
    const d = await J("/api/calendar?month=" + CAL.month);
    if (document.getElementById("v-calendar").classList.contains("hidden")) return;
    CAL.data = d; paintCalendar();
  }
  function shift(n) { const [y, m] = CAL.month.split("-").map(Number), d = new Date(y, m - 1 + n, 1); CAL.month = `${d.getFullYear()}-${pad(d.getMonth() + 1)}`; renderCalendar(true); }
  function evCls(e) { return `t-${e.type}${e.overdue ? " over" : ""}${e.done ? " done" : ""}`; }
  function paintCalendar() {
    const el = document.getElementById("v-calendar"), d = CAL.data;
    const [y, m] = d.month.split("-").map(Number), first = new Date(y, m - 1, 1), today = d.today;
    const evs = d.events.filter(e => CAL.show[e.type] !== false);
    const by = {}; evs.forEach((e, i) => (by[e.date] = by[e.date] || []).push(e));
    const start = new Date(first); start.setDate(1 - ((first.getDay() + 6) % 7));
    const last = new Date(y, m, 0), weeks = Math.ceil((((first.getDay() + 6) % 7) + last.getDate()) / 7);
    const inMonth = e => e.date.slice(0, 7) === d.month;
    const over = d.events.filter(e => e.overdue && inMonth(e)).length;
    const title = `${MONTHS[m - 1]} ${y}`;
    let grid = `<div class="xt-cal-wd" role="row">${WD_S.map((w, i) => `<div role="columnheader" class="${i >= 5 ? "we" : ""}" aria-label="${WD_L[i]}">${w}</div>`).join("")}</div>`;
    for (let w = 0; w < weeks; w++) {
      grid += `<div class="xt-cal-row" role="row">`;
      for (let k = 0; k < 7; k++) {
        const day = new Date(start); day.setDate(start.getDate() + w * 7 + k);
        const iso = isoD(day), list = by[iso] || [], other = day.getMonth() !== m - 1, MAX = 3;
        const lbl = `${day.getDate()}-${MONTHS[day.getMonth()].toLowerCase()}, ${WD_L[k].toLowerCase()}${list.length ? ` · ${list.length} ta voqea` : ""}${iso === today ? " · bugun" : ""}`;
        grid += `<div role="gridcell" class="xt-day${other ? " other" : ""}${iso === today ? " today" : ""}${k >= 5 ? " we" : ""}${iso < today ? " past" : ""}" aria-label="${esc(lbl)}">
          <span class="xt-dn">${day.getDate()}</span><div class="xt-evs">${list.slice(0, list.length > MAX ? MAX - 1 : MAX).map(e => `<button type="button" class="xt-ev ${evCls(e)}" data-e="${esc(e.id)}" title="${esc(T_NAME[e.type] + ": " + e.title)}"><i aria-hidden="true"></i><span>${esc(e.title)}</span></button>`).join("")}
          ${list.length > MAX ? `<button type="button" class="xt-more" data-day="${iso}">yana ${list.length - MAX + 1} ta</button>` : ""}</div></div>`;
      }
      grid += `</div>`;
    }
    /* mobil: kun tartibidagi ro'yxat */
    const days = Object.keys(by).filter(k => k.slice(0, 7) === d.month).sort();
    const agenda = days.length ? days.map(iso => { const dd = parseD(iso), k = (dd.getDay() + 6) % 7;
      return `<div class="xt-ag-day${iso === today ? " today" : ""}${iso < today ? " past" : ""}"><div class="xt-ag-d"><b>${dd.getDate()}</b><span>${iso === today ? "Bugun" : WD_S[k]}</span></div>
        <div class="xt-ag-evs">${by[iso].map(e => `<button type="button" class="xt-ag-ev ${evCls(e)}" data-e="${esc(e.id)}"><i aria-hidden="true"></i><span><b>${esc(e.title)}</b><small>${esc(T_NAME[e.type])}${e.time ? " · " + esc(e.time) : ""}${e.overdue ? " · muddati o'tgan" : e.done ? " · " + esc(e.type === "majlis" ? "o'tkazildi" : e.status) : ""}</small></span>${ico("chevR", 16)}</button>`).join("")}</div></div>`; }).join("")
      : `<div class="xt-empty">${ico("calendar", 26)}<b>Bu oyda voqea yo'q</b><span>Boshqa oyni tanlang yoki filtrlarni yoqing.</span></div>`;
    const cnt = t => d.counts?.[t] ?? 0;
    el.innerHTML = `<div class="head"><div><h2>Majlislar kalendari</h2><span class="muted">Majlislar, topshiriq muddatlari${d.has_tasks ? "" : " (ruxsat yo'q)"} va bo'limingiz xatlari muddatlari · faqat sizga ko'rinadiganlari</span></div><div class="row-actions">${segHtml("calendar")}</div></div>
      <div class="card xt-cal">
        <div class="xt-cal-bar">
          <div class="xt-cal-nav"><button type="button" class="icon-btn" id="xtCalPrev" aria-label="Oldingi oy">${ico("chevL")}</button>
            <h3 aria-live="polite">${title}</h3>
            <button type="button" class="icon-btn" id="xtCalNext" aria-label="Keyingi oy">${ico("chevR")}</button>
            <button type="button" class="btn sm" id="xtCalToday" ${d.month === today.slice(0, 7) ? "disabled" : ""}>Bugun</button></div>
          <div class="xt-legend" role="group" aria-label="Voqea turlari (filtr)">
            ${["majlis", "topshiriq", "xat"].map(t => `<button type="button" class="xt-lg t-${t}${CAL.show[t] === false ? " off" : ""}" data-t="${t}" aria-pressed="${CAL.show[t] !== false}"><i aria-hidden="true"></i>${T_NAME[t]} <em>${cnt(t)}</em></button>`).join("")}
            <span class="xt-lg static over"><i aria-hidden="true"></i>Muddati o'tgan <em>${over}</em></span>
          </div>
        </div>
        <div class="xt-cal-grid" role="grid" aria-label="${title}">${grid}</div>
        <div class="xt-agenda" aria-label="${title} — kun tartibi">${agenda}</div>
      </div>`;
    hydrateIcons?.(el); bindSeg(el);
    el.querySelector("#xtCalPrev").onclick = () => shift(-1);
    el.querySelector("#xtCalNext").onclick = () => shift(1);
    el.querySelector("#xtCalToday").onclick = () => { CAL.month = today.slice(0, 7); renderCalendar(true); };
    el.querySelectorAll(".xt-lg[data-t]").forEach(b => b.onclick = () => { CAL.show[b.dataset.t] = CAL.show[b.dataset.t] === false; store.set("isft-xt-cal-show", CAL.show); paintCalendar(); el.querySelector(`.xt-lg[data-t="${b.dataset.t}"]`)?.focus(); });
    const byId = Object.fromEntries(d.events.map(e => [e.id, e]));
    el.querySelectorAll("[data-e]").forEach(b => b.onclick = e => { e.stopPropagation(); showEvent(byId[b.dataset.e], b); });
    el.querySelectorAll("[data-day]").forEach(b => b.onclick = e => { e.stopPropagation(); showDay(b.dataset.day, by[b.dataset.day] || [], b, byId); });
  }

  function placePop(p, anchor) {
    const mobile = innerWidth <= 700;
    p.classList.toggle("sheet", mobile);
    if (mobile) { p.style.left = p.style.top = ""; return; }
    const r = anchor.getBoundingClientRect(), w = p.offsetWidth, h = p.offsetHeight;
    let left = r.left + r.width / 2 - w / 2; left = Math.max(12, Math.min(left, innerWidth - w - 12));
    let topY = r.bottom + 8; if (topY + h > innerHeight - 12) topY = Math.max(12, r.top - h - 8);
    p.style.left = left + "px"; p.style.top = topY + "px";
  }
  function openPop(html, anchor, label) {
    closeCalPop();
    const p = document.createElement("div");
    p.className = "xt-pop"; p.setAttribute("role", "dialog"); p.setAttribute("aria-label", label);
    p.innerHTML = html; document.body.appendChild(p);
    CAL.pop = p; CAL.popAnchor = anchor; placePop(p, anchor);
    p.addEventListener("keydown", e => { if (e.key === "Escape") { e.preventDefault(); closeCalPop(true); } else trapTab(e, p); });
    p.querySelector("[data-pclose]")?.addEventListener("click", () => closeCalPop(true));
    requestAnimationFrame(() => p.classList.add("on"));
    return p;
  }
  function closeCalPop(refocus) {
    if (!CAL.pop) return;
    const a = CAL.popAnchor; CAL.pop.remove(); CAL.pop = null; CAL.popAnchor = null;
    if (refocus && a?.isConnected) a.focus({preventScroll: true});
  }
  document.addEventListener("mousedown", e => { if (CAL.pop && !CAL.pop.contains(e.target)) closeCalPop(false); });
  window.addEventListener("resize", () => { if (CAL.pop && CAL.popAnchor?.isConnected) placePop(CAL.pop, CAL.popAnchor); });
  document.addEventListener("scroll", () => { if (CAL.pop && innerWidth > 700) closeCalPop(false); }, true);

  function evDate(e) { const dd = parseD(e.date); return `${dd.getDate()}-${MONTHS[dd.getMonth()].toLowerCase()} ${dd.getFullYear()}, ${WD_L[(dd.getDay() + 6) % 7].toLowerCase()}${e.time ? " · " + esc(e.time) : ""}`; }
  function evStatus(e) {
    if (e.overdue) return `<span class="xt-tag bad">${ico("alert", 13)} Muddati o'tgan</span>`;
    if (e.type === "majlis") return `<span class="xt-tag">${e.done ? "O'tkazildi" : "Rejalashtirilgan"}</span>`;
    return `<span class="xt-tag ${e.done ? "ok" : ""}">${esc(e.status)}</span>`;
  }
  function evBody(e) {
    return `<div class="xt-pop-h"><span class="xt-pop-t ${evCls(e)}"><i aria-hidden="true"></i>${T_NAME[e.type]}</span><button type="button" class="icon-btn xt-x" data-pclose aria-label="Yopish">${ico("x", 16)}</button></div>
      <b class="xt-pop-title">${esc(e.title)}</b>
      <div class="xt-pop-m">${ico("calendar", 14)}<span>${evDate(e)}</span></div>
      ${e.sub ? `<div class="xt-pop-m">${ico(T_IC[e.type], 14)}<span>${esc(e.sub)}</span></div>` : ""}
      <div class="xt-pop-f">${evStatus(e)}<button type="button" class="btn primary sm" data-open>${ico("arrow", 15)} Ochish</button></div>`;
  }
  function showEvent(e, anchor) {
    if (!e) return;
    const p = openPop(evBody(e), anchor, `${T_NAME[e.type]}: ${e.title}`);
    p.querySelector("[data-open]").onclick = () => { closeCalPop(false); openLink(e.link); };
    p.querySelector("[data-open]").focus();
  }
  function showDay(iso, list, anchor, byId) {
    const dd = parseD(iso);
    const p = openPop(`<div class="xt-pop-h"><b>${dd.getDate()}-${MONTHS[dd.getMonth()].toLowerCase()}, ${WD_L[(dd.getDay() + 6) % 7].toLowerCase()}</b><button type="button" class="icon-btn xt-x" data-pclose aria-label="Yopish">${ico("x", 16)}</button></div>
      <div class="xt-pop-list">${list.map(e => `<button type="button" class="xt-ev ${evCls(e)}" data-pe="${esc(e.id)}"><i aria-hidden="true"></i><span>${esc(e.title)}</span></button>`).join("")}</div>`, anchor, `${dd.getDate()}-${MONTHS[dd.getMonth()].toLowerCase()} voqealari`);
    p.querySelectorAll("[data-pe]").forEach(b => b.onclick = ev => { ev.stopPropagation(); showEvent(byId[b.dataset.pe], anchor); });
    p.querySelector("[data-pe]")?.focus();
  }

  window.XT = {openPalette, openPassword, openNp, loadNp, renderCalendar, openLink};
})();
