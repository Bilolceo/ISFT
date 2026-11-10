/* Talaba kabineti (/talaba) va «Talaba murojaatlari» (/talaba/xodim). Ma'lumot — /api/talaba/* (app/student_portal.py).
   Hamma matn esc() orqali chiqariladi; sahifalar hash (#baholar ...) bo'yicha. */
(function () {
  "use strict";
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));
  const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const num = (n) => (n == null || n === "" ? "—" : String(Math.round(+n)).replace(/\B(?=(\d{3})+(?!\d))/g, " "));
  const money = (n) => num(n) + " so'm";
  const MON = ["yan", "fev", "mar", "apr", "may", "iyn", "iyl", "avg", "sen", "okt", "noy", "dek"];
  const WD = ["Yakshanba", "Dushanba", "Seshanba", "Chorshanba", "Payshanba", "Juma", "Shanba"];
  const dmy = (d) => (d && d.length >= 10 ? `${d.slice(8, 10)}.${d.slice(5, 7)}.${d.slice(0, 4)}` : d || "—");
  const dmyhm = (d) => (d ? dmy(d) + (d.length > 11 ? " " + d.slice(11, 16) : "") : "—");
  const fix2 = (x) => (x == null ? "—" : (+x).toFixed(2));
  const plural = (n, w) => `${n} ${w}`;
  const STAFF = location.pathname.replace(/\/+$/, "") === "/talaba/xodim";

  // ---------------------------------------------------------------- tarmoq
  async function api(path, opts = {}) {
    const o = { credentials: "same-origin", headers: {}, ...opts };
    if (o.body && typeof o.body !== "string") { o.body = JSON.stringify(o.body); o.headers["Content-Type"] = "application/json"; }
    const r = await fetch(path, o);
    let d = null;
    try { d = await r.json(); } catch (e) { d = null; }
    if (!r.ok) {
      const det = d && d.detail;
      const m = typeof det === "string" ? det : det && det.message ? det.message : (d && d.message) || `Xato (${r.status})`;
      const err = new Error(m); err.status = r.status; err.data = det || d; throw err;
    }
    return d;
  }
  let toastT = 0;
  function toast(m, bad) {
    const t = $("#tk-toast"); t.textContent = m; t.className = "tk-toast" + (bad ? " bad" : "");
    clearTimeout(toastT); toastT = setTimeout(() => t.classList.add("hidden"), 4200);
  }
  function show(id) { ["tk-login", "tk-force", "tk-app", "tk-staff"].forEach((x) => $("#" + x).classList.toggle("hidden", x !== id)); }

  // ---------------------------------------------------------------- mavzu
  const THEMES = ["light", "dark", "auto"];
  const THEME_N = { light: "Yorug'", dark: "Qorong'i", auto: "Tizim" };
  function themeLabel() { $$(".tk-theme-l").forEach((e) => (e.textContent = "Mavzu: " + THEME_N[document.documentElement.dataset.theme || "light"])); }
  function cycleTheme() {
    const cur = document.documentElement.dataset.theme || "light";
    const t = THEMES[(THEMES.indexOf(cur) + 1) % THEMES.length];
    document.documentElement.dataset.theme = t;
    try { localStorage.setItem("jarvis-theme", t); } catch (e) {}
    themeLabel(); toast("Mavzu: " + THEME_N[t]);
  }

  // ---------------------------------------------------------------- ikonkalar
  const P = {
    home: "M3 11l9-8 9 8v9a1 1 0 0 1-1 1h-5v-6H9v6H4a1 1 0 0 1-1-1z",
    grades: "M4 19V5M4 19h16M8 16v-5M12 16V8M16 16v-3",
    rating: "M8 21h8M12 17v4M7 4h10v5a5 5 0 0 1-10 0zM17 6h3v2a3 3 0 0 1-3 3M7 6H4v2a3 3 0 0 0 3 3",
    att: "M8 2v4M16 2v4M3 9h18M5 5h14a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2zM9 15l2 2 4-4",
    retake: "M3 12a9 9 0 1 0 3-6.7M3 4v5h5M12 7v5l3 2",
    exam: "M9 4h6a1 1 0 0 1 1 1v1H8V5a1 1 0 0 1 1-1zM6 6h12v15H6zM9 12h6M9 16h4",
    appeal: "M12 3v18M5 7h14M5 7l-3 7a4 4 0 0 0 6 0zM19 7l-3 7a4 4 0 0 0 6 0z",
    contract: "M3 6h18v12H3zM3 10h18M7 15h3",
    cert: "M7 3h7l5 5v13H7zM14 3v5h5M10 13h6M10 17h6",
    profile: "M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8zM4 21a8 8 0 0 1 16 0",
    menu: "M4 6h16M4 12h16M4 18h16",
  };
  const ico = (k) => `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="${P[k]}"/></svg>`;
  const PAGES = [
    { k: "bosh", t: "Bosh sahifa", s: "Bosh", i: "home", f: pHome },
    { k: "baholar", t: "Baholar", s: "Baholar", i: "grades", f: pGrades },
    { k: "reyting", t: "Reyting", s: "Reyting", i: "rating", f: pRating },
    { k: "davomat", t: "Davomat", s: "Davomat", i: "att", f: pAttendance },
    { k: "otrabotka", t: "Otrabotka", s: "Otrabotka", i: "retake", f: pRetakes },
    { k: "imtihonlar", t: "Imtihonlar", s: "Imtihon", i: "exam", f: pExams },
    { k: "apellyatsiya", t: "Apellyatsiya", s: "Apellyatsiya", i: "appeal", f: pAppeals },
    { k: "kontrakt", t: "Kontrakt", s: "Kontrakt", i: "contract", f: pContract },
    { k: "malumotnoma", t: "Ma'lumotnoma so'rash", s: "Ma'lumotnoma", i: "cert", f: pCert },
    { k: "profil", t: "Profil", s: "Profil", i: "profile", f: pProfile },
  ];
  const BOTTOM = ["bosh", "baholar", "davomat", "imtihonlar"];
  let ME = null, timers = [];

  // ---------------------------------------------------------------- kirish
  async function boot() {
    themeLabel();
    document.addEventListener("click", onClick);
    if (STAFF) return staffBoot();
    api("/api/talaba/config").then((c) => {
      const h = $("#tk-demo-hint");
      if (!c.demo_hint) h.classList.add("hidden");
      else h.innerHTML = `Sinov rejimi: birinchi kirishda boshlang'ich parol — <code>${esc(c.demo_password)}</code>. Keyin uni almashtirasiz.`;
    }).catch(() => {});
    $("#tk-login-form").addEventListener("submit", doLogin);
    $("#tk-force-form").addEventListener("submit", doForce);
    window.addEventListener("hashchange", route);
    await loadMe();
  }
  async function loadMe() {
    let ss = null;
    try { ss = await api("/api/talaba/session"); } catch (e) { ss = null; }
    if (!ss || !ss.auth) { ME = null; show("tk-login"); setTimeout(() => $("#tk-hemis").focus(), 50); return; }
    try { ME = await api("/api/talaba/me"); }
    catch (e) { ME = null; show("tk-login"); return; }
    if (ME.must_change) {
      show("tk-force");
      $("#tk-force-who").textContent = `${ME.name} · HEMIS ID ${ME.hemis_id}`;
      setTimeout(() => $("#tk-f-cur").focus(), 50);
      return;
    }
    renderShell(); show("tk-app"); route();
  }
  async function doLogin(ev) {
    ev.preventDefault();
    const err = $("#tk-login-err"), btn = $("#tk-login-btn");
    err.textContent = "";
    const h = $("#tk-hemis").value.trim(), p = $("#tk-pass").value;
    if (!h || !p) { err.textContent = "HEMIS ID va parolni kiriting"; return; }
    btn.disabled = true; btn.textContent = "Tekshirilmoqda…";
    try {
      await api("/api/talaba/login", { method: "POST", body: { hemis_id: h, password: p } });
      $("#tk-pass").value = "";
      await loadMe();
    } catch (e) { err.textContent = e.message; }
    finally { btn.disabled = false; btn.textContent = "Kirish"; }
  }
  async function doForce(ev) {
    ev.preventDefault();
    const err = $("#tk-force-err"); err.textContent = "";
    const cur = $("#tk-f-cur").value, n1 = $("#tk-f-new").value, n2 = $("#tk-f-new2").value;
    if (n1 !== n2) { err.textContent = "Yangi parollar bir xil emas"; return; }
    try {
      await api("/api/talaba/password", { method: "POST", body: { current: cur, new: n1 } });
      ["#tk-f-cur", "#tk-f-new", "#tk-f-new2"].forEach((s) => ($(s).value = ""));
      toast("Parol saqlandi");
      await loadMe();
    } catch (e) { err.textContent = e.message; }
  }
  async function logout() {
    try { await api(STAFF ? "/api/logout" : "/api/talaba/logout", { method: "POST" }); } catch (e) {}
    if (STAFF) { location.href = "/"; return; }
    ME = null; location.hash = ""; show("tk-login");
  }

  // ---------------------------------------------------------------- qobiq va marshrut
  function renderShell() {
    $("#tk-who").innerHTML = `${esc(ME.name)}<small>${esc(ME.group)} · ${esc(ME.course)}-kurs · HEMIS ${esc(ME.hemis_id)}</small>`;
    $("#tk-side-sub").textContent = ME.group + " · " + ME.course + "-kurs";
    /* menyu guruhlari: O'qish · Hujjat va to'lov · Hayot · Profil (kengaytma sahifalar ham k bo'yicha joylashadi) */
    const GRP = [["", ["bosh"]], ["O'qish", ["baholar", "reyting", "davomat", "otrabotka", "imtihonlar", "apellyatsiya"]],
                 ["Hujjat va to'lov", ["malumotnoma", "kontrakt"]], ["Hayot", ["turarjoy", "tadbirlar", "amaliyot", "xalqaro"]], ["Profil", ["profil"]]];
    const known = new Set(GRP.flatMap((g) => g[1]));
    const link = (p) => `<a href="#${p.k}" data-p="${p.k}">${ico(p.i)}<span>${esc(p.t)}</span></a>`;
    $("#tk-nav").innerHTML = GRP.map(([name, ks], gi) => {
      const ps = ks.map((k) => PAGES.find((x) => x.k === k)).filter(Boolean)
        .concat(gi === 3 ? PAGES.filter((x) => !known.has(x.k)) : []);
      return ps.length ? (name ? `<div class="tk-nav-h">${esc(name)}</div>` : "") + ps.map(link).join("") : "";
    }).join("");
    $("#tk-bottom").innerHTML = BOTTOM.map((k) => { const p = PAGES.find((x) => x.k === k); return `<a href="#${p.k}" data-p="${p.k}">${ico(p.i)}<span>${esc(p.s)}</span></a>`; }).join("")
      + `<a href="#" data-act="sheet" data-p="_more">${ico("menu")}<span>Menyu</span></a>`;
    $("#tk-sheet-list").innerHTML = PAGES.map((p) => `<a href="#${p.k}" data-p="${p.k}">${ico(p.i)}<span>${esc(p.s)}</span></a>`).join("");
  }
  function route() {
    if (!ME || ME.must_change) return;
    const k = (location.hash || "#bosh").slice(1);
    const p = PAGES.find((x) => x.k === k) || PAGES[0];
    timers.forEach(clearInterval); timers = [];
    $$("#tk-nav a, #tk-bottom a, #tk-sheet-list a").forEach((a) => a.classList.toggle("on", a.dataset.p === p.k));
    if (!BOTTOM.includes(p.k)) $('#tk-bottom a[data-p="_more"]').classList.add("on");
    $("#tk-sheet").classList.add("hidden");
    $("#tk-top-title").textContent = p.t;
    document.title = p.t + " — Talaba kabineti";
    const m = $("#tk-main");
    m.innerHTML = `<div class="tk-empty">Yuklanmoqda…</div>`;
    window.scrollTo(0, 0);
    p.f(m).catch((e) => {
      if (e.status === 401) { ME = null; show("tk-login"); return; }
      if (e.status === 403 && e.data && e.data.must_change) { loadMe(); return; }
      m.innerHTML = `<div class="tk-card"><div class="tk-err">${esc(e.message)}</div></div>`;
    });
  }
  function onClick(ev) {
    const a = ev.target.closest("[data-act]");
    if (!a) return;
    const act = a.dataset.act;
    if (act === "theme") { ev.preventDefault(); cycleTheme(); }
    else if (act === "logout") { ev.preventDefault(); logout(); }
    else if (act === "sheet") { ev.preventDefault(); $("#tk-sheet").classList.remove("hidden"); }
    else if (act === "sheet-close") { ev.preventDefault(); $("#tk-sheet").classList.add("hidden"); }
  }
  const head = (t, sub, right = "") => `<div class="tk-head"><div><h2>${esc(t)}</h2>${sub ? `<p>${sub}</p>` : ""}</div>${right}</div>`;
  const meter = (val, max, marks, cls) => {
    const pct = (v) => Math.max(0, Math.min(100, (v / max) * 100));
    return `<div class="tk-meter"><i class="${cls || ""}" style="width:${pct(val)}%"></i>${(marks || []).map((m) => `<b style="left:${pct(m[0])}%"></b><em style="left:${pct(m[0])}%">${esc(m[1])}</em>`).join("")}</div>`;
  };
  const lvlCls = (h, L) => (h > L.reprimand ? "bad" : h >= L.call ? "warn" : "ok");
  function countdown(hours) {
    if (hours == null) return "";
    if (hours < 0) return `Muddat ${Math.ceil(-hours / 24) > 1 ? Math.floor(-hours / 24) + " kun" : Math.ceil(-hours) + " soat"} oldin o'tgan`;
    const d = Math.floor(hours / 24), h = Math.floor(hours % 24), m = Math.floor((hours * 60) % 60);
    return d ? `${d} kun ${h} soat qoldi` : `${h} soat ${m} daqiqa qoldi`;
  }

  // ================================================================ BOSH SAHIFA
  async function pHome(m) {
    const d = await api("/api/talaba/home");
    const S = d.semester, A = d.attendance, L = A.limits;
    const warns = d.warnings.length
      ? `<div class="tk-warns">${d.warnings.map((w) => `<a class="tk-warn ${esc(w.level)}" ${w.page ? `href="#${esc(w.page)}"` : ""}><div><b>${esc(w.title)}</b><span>${esc(w.text)}</span></div>${w.page ? '<span class="tk-go">›</span>' : ""}</a>`).join("")}</div>`
      : `<div class="tk-ok-line">✓ Hozircha ogohlantirish yo'q — davomat, baholar va kontrakt bo'yicha hammasi joyida.</div>`;
    const ex = d.next_exam;
    const exHtml = ex ? `<div class="tk-row"><div class="tk-date"><b>${esc(ex.exam_date.slice(8, 10))}</b><small>${esc(MON[+ex.exam_date.slice(5, 7) - 1])}</small></div>
        <div class="tk-main-c"><div class="tk-t">${esc(ex.subject)}</div><div class="tk-d">${esc(WD[new Date(ex.exam_date + "T00:00").getDay()])}, ${esc(ex.start_time)}–${esc(ex.end_time)}${ex.room ? " · " + esc(ex.room) : ""}</div>
        <div class="tk-d">${esc(ex.session)}</div></div><div class="tk-r"><span class="tk-pill ${ex.days <= 3 ? "warn" : "info"}">${ex.days === 0 ? "Bugun" : esc(ex.days) + " kun"}</span></div></div>
        <p class="tk-small tk-muted" style="margin-top:8px">Sessiyada jami ${esc(d.exams_left)} ta imtihon qoldi. <a href="#imtihonlar">Jadval va ruxsatnoma →</a></p>`
      : `<div class="tk-empty">E'lon qilingan imtihon jadvali hali yo'q.</div>`;
    const k = d.contract;
    const kHtml = k.kind !== "kontrakt" ? `<div class="tk-stat ok"><span class="k">Kontrakt</span><span class="v" style="font-size:20px">ISFT granti</span><span class="s">To'lov talab qilinmaydi</span></div>`
      : k.next ? `<div class="tk-stat ${k.next.status === "muddati_otgan" ? "bad" : k.next.days <= 14 ? "warn" : ""}"><span class="k">Keyingi to'lov · ${esc(k.next.label)}</span><span class="v" style="font-size:20px">${money(k.next.short)}</span><span class="s">${dmy(k.next.due)} gacha · qolgan qarz ${money(k.debt)}</span></div>`
      : `<div class="tk-stat ok"><span class="k">Kontrakt</span><span class="v" style="font-size:20px">To'liq to'langan</span><span class="s">Qarz yo'q</span></div>`;
    m.innerHTML = `
      <div class="tk-card tk-hero"><h2>Salom, ${esc(ME.first)}!</h2>
        <div class="tk-sub">${esc(S.label)} · ${esc(S.sem_no)}-semestr (${esc(S.course)}-kurs)</div>
        <div class="tk-pills"><span class="tk-pill">${esc(ME.group)}</span><span class="tk-pill">${esc(ME.direction)}</span>
          <span class="tk-pill">${S.status === "faol" ? "Faol talaba" : esc(S.status)}</span><span class="tk-pill">${esc(S.subjects)} fan · ${esc(S.credits)} kredit</span>
          <span class="tk-pill">${dmy(S.start)} – ${dmy(S.end)}</span></div></div>
      <div class="tk-card"><h3>Diqqat talab qiladi</h3>${warns}</div>
      <div class="tk-g4">
        <div class="tk-card"><div class="tk-stat ${lvlCls(A.unexcused, L)}"><span class="k">Sababsiz qoldirilgan soat</span><span class="v">${esc(A.unexcused)}<small> / ${esc(L.reprimand)}</small></span>
          ${meter(A.unexcused, Math.max(L.reprimand + 12, A.unexcused), [[L.call, L.call], [L.reprimand, L.reprimand]], lvlCls(A.unexcused, L))}<span class="s">Sababli: ${esc(A.excused)} soat</span></div></div>
        <div class="tk-card"><div class="tk-stat ${d.gpa != null && d.gpa < 3 ? "warn" : ""}"><span class="k">GPA (kumulyativ, 5 ballik)</span><span class="v">${fix2(d.gpa)}</span><span class="s"><a href="#baholar">Baholar →</a></span></div></div>
        <div class="tk-card"><div class="tk-stat ${d.debts ? "bad" : "ok"}"><span class="k">Akademik qarz</span><span class="v">${esc(d.debts)}</span><span class="s">${d.debts ? "fan o'zlashtirilmagan" : "qarz yo'q"}</span></div></div>
        <div class="tk-card">${kHtml}</div>
      </div>
      <div class="tk-card"><h3>Navbatdagi imtihon</h3>${exHtml}</div>
      <p class="tk-small tk-muted" style="margin-top:14px">Savollar bo'yicha: ${esc(ME.office)}${ME.office_rooms ? " — " + esc(ME.office_rooms) : ""}.</p>`;
  }

  // ================================================================ BAHOLAR
  async function pGrades(m) {
    const d = await api("/api/talaba/grades");
    const C = d.current, CR = d.credits;
    const cur = C.subjects.length ? C.subjects.map((g) => `<div class="tk-row"><div class="tk-main-c"><div class="tk-t">${esc(g.subject)}</div>
        <div class="tk-d">${esc(g.credits)} kredit${g.teacher ? " · " + esc(g.teacher) : ""}</div>
        ${meter(g.oraliq || 0, C.oraliq_max, [[C.oraliq_min, C.oraliq_min]], g.admitted ? "ok" : "bad")}</div>
        <div class="tk-r"><div class="tk-score">${g.oraliq == null ? "—" : esc(g.oraliq)}<small> / ${esc(C.oraliq_max)}</small></div>
        <span class="tk-pill ${g.admitted ? "ok" : "bad"}">${g.admitted ? "Yakuniyga kiradi" : "Kiritilmaydi"}</span></div></div>`).join("")
      : `<div class="tk-empty">Joriy semestr fanlari topilmadi.</div>`;
    const progMax = CR.required;
    const sems = d.semesters.length ? d.semesters.map((s, i) => `<details class="tk-acc" ${i === 0 ? "open" : ""}><summary>
        <span class="tk-t">${esc(s.label)} <span class="tk-muted tk-small nowrap">· ${esc(s.sem_no)}-semestr</span></span>
        <span class="tk-pill brand">GPA ${fix2(s.gpa)}</span><span class="tk-pill">${esc(s.earned)} / ${esc(s.credits)} kredit</span>
        ${s.debts ? `<span class="tk-pill bad">${esc(s.debts)} ta qarz</span>` : ""}</summary><div class="tk-acc-b">
        <div class="tk-list">${s.subjects.map((g) => `<div class="tk-row"><div class="tk-main-c"><div class="tk-t">${esc(g.subject)}</div>
          <div class="tk-d">${esc(g.credits)} kredit · oraliq ${g.oraliq ?? "—"} · yakuniy ${g.yakuniy ?? "—"}${g.attempts > 1 ? ` · ${esc(g.attempts)} urinish` : ""}</div>
          ${g.history.length > 1 ? `<div class="tk-hist">${g.history.map((h) => `<div class="${h.counted ? "on" : ""}">${esc(h.attempt)}-urinish (${esc(h.kind)}${h.at ? ", " + dmy(h.at) : ""}): ${esc(h.score)} ball${h.counted ? " — hisobda" : ""}</div>`).join("")}</div>` : ""}</div>
          <div class="tk-r"><div class="tk-score">${esc(g.score)}<small> / 100</small></div><span class="tk-letter ${esc(g.letter)}">${esc(g.letter)}</span> <span class="tk-small tk-muted">«${esc(g.grade5)}»</span></div></div>`).join("")}</div></div></details>`).join("")
      : `<div class="tk-card"><div class="tk-empty">Hali yakunlangan semestr yo'q (1-kurs, birinchi semestr).</div></div>`;
    m.innerHTML = head("Baholar", `Joriy semestr — oraliq nazorat; yakunlangan semestrlar — yakuniy natijalar. O'tish bali: ${esc(d.pass)}.`) + `
      <div class="tk-g3">
        <div class="tk-card"><div class="tk-stat ${d.cum_gpa != null && d.cum_gpa < 3 ? "warn" : ""}"><span class="k">Kumulyativ GPA</span><span class="v">${fix2(d.cum_gpa)}<small> / 5</small></span><span class="s">${esc(d.gpa_formula)}</span></div></div>
        <div class="tk-card"><div class="tk-stat"><span class="k">Kreditlar (${esc(CR.level)})</span><span class="v">${esc(CR.earned)}<small> / ${esc(progMax)}</small></span>
          <div class="tk-meter thin"><i class="ok" style="width:${Math.min(100, (CR.earned / progMax) * 100)}%"></i></div>
          <span class="s">Joriy semestrda o'qilmoqda: ${esc(CR.in_progress)} kredit</span></div></div>
        <div class="tk-card"><div class="tk-stat"><span class="k">Oraliq nazorat chegarasi</span><span class="v">${esc(C.oraliq_min)}<small> / ${esc(C.oraliq_max)}</small></span><span class="s">Yakuniy nazoratga kirish uchun kamida ${esc(C.oraliq_min)} ball</span></div></div>
      </div>
      <div class="tk-card"><h3>${esc(C.label)} · ${esc(C.sem_no)}-semestr</h3><div class="tk-list">${cur}</div></div>
      <div class="tk-card"><h3>Yakunlangan semestrlar</h3>${sems}</div>
      <div class="tk-card"><h3>Baholash shkalasi</h3><div class="tk-pills">${d.scale.map((s) => `<span class="tk-pill"><span class="tk-letter ${esc(s.letter)}" style="width:22px;height:22px;border-radius:7px">${esc(s.letter)}</span> ${esc(s.lo)}–${esc(s.hi)} · «${esc(s.grade)}» ${esc(s.word)}</span>`).join("")}</div></div>`;
  }

  // ================================================================ REYTING
  async function pRating(m) {
    const d = await api("/api/talaba/rating");
    if (!d.items.length) {
      m.innerHTML = head("Reyting", "") + `<div class="tk-card"><div class="tk-empty">${d.rated ? "Reyting yakunlangan semestr natijalaridan hisoblanadi — sizda hali yakunlangan semestr yo'q." : "Reytingda faqat faol talabalar ishtirok etadi."}</div></div>`;
      return;
    }
    const r = d.items[0];
    const tile = (k, lbl) => `<div class="tk-place"><span class="k">${esc(lbl)}</span><span class="v">${num(r["r_" + k])}<small> / ${num(r["n_" + k])}</small></span>
      <span class="s">Yuqoridan ${esc(r["p_" + k])}% ichida</span></div>`;
    m.innerHTML = head("Reyting", `${esc(r.label)} · faqat o'rningiz ko'rsatiladi (boshqa talabalar ma'lumoti chiqmaydi)`) + `
      <div class="tk-card"><div class="tk-g3">${tile("group", d.levels.group)}${tile("course", d.levels.course)}${tile("faculty", d.levels.faculty)}</div>
        <div class="tk-pills" style="margin-top:12px"><span class="tk-pill brand">GPA ${fix2(r.gpa)}</span><span class="tk-pill">O'rtacha ball ${esc(r.avg_score)}</span>
        <span class="tk-pill">${esc(r.credits_ok)} / ${esc(r.credits)} kredit</span>${r.attendance != null ? `<span class="tk-pill">Davomat ${esc(r.attendance)}%</span>` : ""}
        ${r.n_f ? `<span class="tk-pill bad">${esc(r.n_f)} ta «F»</span>` : ""}</div></div>
      <div class="tk-card"><h3>Semestrlar bo'yicha</h3><div class="tk-list">
        ${d.items.map((x) => `<div class="tk-row"><div class="tk-main-c"><div class="tk-t">${esc(x.short)}</div>
          <div class="tk-d">Guruhda ${num(x.r_group)} / ${num(x.n_group)} · kursda ${num(x.r_course)} / ${num(x.n_course)} · fakultetda ${num(x.r_faculty)} / ${num(x.n_faculty)}</div></div>
          <div class="tk-r"><span class="tk-pill brand">GPA ${fix2(x.gpa)}</span></div></div>`).join("")}</div>
        <p class="tk-small tk-muted" style="margin-top:10px">${esc(d.note)}</p></div>`;
  }

  // ================================================================ DAVOMAT
  async function pAttendance(m) {
    const [d, rq] = await Promise.all([api("/api/talaba/attendance"), api("/api/talaba/requests")]);
    const L = d.limits;
    const reasons = Object.entries(d.reasons).map(([k, v]) => `<option value="${esc(k)}">${esc(v)}</option>`).join("");
    const exReq = rq.items.filter((x) => x.kind === "sababli");
    const cur = d.items.filter((a) => a.current), old = d.items.filter((a) => !a.current);
    const row = (a) => `<div class="tk-row" id="ab-${a.id}"><div class="tk-date ${a.current ? "" : "past"}"><b>${esc(a.start.slice(8, 10))}</b><small>${esc(MON[+a.start.slice(5, 7) - 1])}</small></div>
      <div class="tk-main-c"><div class="tk-t">${esc(a.hours)} soat · ${esc(a.reason_name)}</div>
        <div class="tk-d">${dmy(a.start)}${a.end && a.end !== a.start ? " – " + dmy(a.end) : ""}${a.subjects.length ? " · " + esc(a.subjects.join(", ")) : ""}</div>
        <div class="tk-pills" style="margin-top:6px">${a.current ? (a.unexcused ? '<span class="tk-pill bad">Sababsiz hisoblanadi</span>' : '<span class="tk-pill ok">Sababli</span>') : '<span class="tk-pill">O\'tgan semestr</span>'}
          ${a.doc_status === "kutilmoqda" ? '<span class="tk-pill warn">Hujjat kutilmoqda</span>' : a.doc_status === "tasdiqlangan" ? '<span class="tk-pill ok">Hujjat tasdiqlangan</span>' : a.doc_status === "yoq" ? '<span class="tk-pill bad">Hujjat yo\'q</span>' : ""}
          ${a.cleared_by ? '<span class="tk-pill info">Otrabotka bilan yopilgan</span>' : ""}
          ${a.request ? `<span class="tk-pill ${a.request.status === "rad" ? "bad" : a.request.status === "qabul" ? "ok" : "warn"}">Yuklangan hujjat: ${esc(a.request.status_name)}</span>` : ""}</div>
</div>
      ${a.can_upload && d.can_request ? `<div class="tk-r"><button class="btn sm" type="button" data-up="${a.id}">Hujjat yuklash</button></div>` : ""}<div class="tk-up" data-abs="${a.id}"></div></div>`;
    const bySub = d.by_subject.length ? `<div class="tk-list">${d.by_subject.map((x) => `<div class="tk-row"><div class="tk-main-c"><div class="tk-t">${esc(x.subject)}</div>
        <div class="tk-meter thin"><i class="${x.classes >= 4 ? "warn" : ""}" style="width:${Math.min(100, x.classes * 12)}%"></i></div></div><div class="tk-r"><b class="tk-num">${esc(x.classes)}</b> <span class="tk-small tk-muted">dars</span></div></div>`).join("")}</div>
        <p class="tk-small tk-muted">Dars qoldirish kun bo'yicha qayd etiladi; fanlar — o'sha kungi dars jadvalidan.</p>`
      : `<div class="tk-empty">${d.has_schedule ? "Joriy semestrda qoldirilgan dars yo'q." : "Guruhingiz dars jadvali tizimga kiritilmagan — fanlar bo'yicha taqsimot ko'rsatilmaydi."}</div>`;
    m.innerHTML = head("Davomat", `Joriy semestr. Chegaralar: ${esc(L.call)} soat — ogohlantirish, ${esc(L.reprimand)} soatdan oshsa — hayfsan.`) + `
      <div class="tk-g3">
        <div class="tk-card"><div class="tk-stat ${lvlCls(d.unexcused, L)}"><span class="k">Sababsiz</span><span class="v">${esc(d.unexcused)}<small> soat</small></span>
          ${meter(d.unexcused, Math.max(L.reprimand + 12, d.unexcused), [[L.call, L.call], [L.reprimand, L.reprimand]], lvlCls(d.unexcused, L))}</div></div>
        <div class="tk-card"><div class="tk-stat ok"><span class="k">Sababli</span><span class="v">${esc(d.excused)}<small> soat</small></span><span class="s">Hujjat bilan tasdiqlangan</span></div></div>
        <div class="tk-card"><div class="tk-stat"><span class="k">Jami qoldirilgan</span><span class="v">${esc(d.total)}<small> soat</small></span><span class="s">Hujjat muddati: dars qoldirilgandan keyin ${esc(d.doc_days)} kun</span></div></div>
      </div>
      <div class="tk-g2">
        <div class="tk-card"><h3>Qoldirilgan darslar (joriy semestr)</h3><div class="tk-list">${cur.length ? cur.map(row).join("") : '<div class="tk-empty">Joriy semestrda dars qoldirilmagan.</div>'}</div></div>
        <div class="tk-card"><h3>Fanlar bo'yicha</h3>${bySub}</div>
      </div>
      <div class="tk-card"><h3>Sababli hujjat yuklash</h3>
        <p class="tk-small tk-muted">PDF yoki JPG, ${esc(d.max_mb)} MB gacha. Hujjat ${esc(d.office)}ga ko'rib chiqish uchun yuboriladi. Ro'yxatda yo'q kun uchun — sanalarni kiriting.</p>
        ${d.can_request ? `<button class="btn sm" type="button" data-up="0">Boshqa sana uchun hujjat</button><div class="tk-up" data-abs="0"></div>` : '<p class="tk-small">Akademik ta\'tilda hujjat yuklanmaydi.</p>'}
        ${exReq.length ? `<h3 style="margin-top:16px">Yuborilgan hujjatlar</h3><div class="tk-list">${exReq.map(reqRow).join("")}</div>` : ""}</div>
      ${old.length ? `<div class="tk-card"><h3>O'tgan semestr</h3><div class="tk-list">${old.slice(0, 20).map(row).join("")}</div></div>` : ""}`;
    m.querySelectorAll("[data-up]").forEach((b) => b.addEventListener("click", () => {
      const id = b.dataset.up, box = m.querySelector(`.tk-up[data-abs="${id}"]`);
      if (box.innerHTML) { box.innerHTML = ""; return; }
      box.innerHTML = `<form class="tk-form tk-inline">
        ${id === "0" ? `<div class="tk-g2"><label class="tk-field"><span>Boshlanish</span><input type="date" name="start" required></label><label class="tk-field"><span>Tugash</span><input type="date" name="end"></label></div>` : ""}
        <label class="tk-field"><span>Sabab</span><select name="reason" required>${reasons}</select></label>
        <label class="tk-file"><span><b>Fayl</b> (PDF yoki JPG)</span><input type="file" name="file" accept=".pdf,.jpg,.jpeg,application/pdf,image/jpeg" required></label>
        <label class="tk-field"><span>Izoh (ixtiyoriy)</span><input name="note" maxlength="300" placeholder="Masalan, poliklinika ma'lumotnomasi"></label>
        <div class="tk-err"></div><div class="tk-actions"><button class="btn primary" type="submit">Yuborish</button><button class="btn ghost" type="button" data-cancel>Bekor qilish</button></div></form>`;
      box.querySelector("[data-cancel]").onclick = () => (box.innerHTML = "");
      box.querySelector("form").addEventListener("submit", (ev) => sendExcuse(ev, id === "0" ? null : +id, d.max_mb));
    }));
  }
  function readFile(f) {
    return new Promise((res, rej) => { const r = new FileReader(); r.onload = () => res(r.result); r.onerror = () => rej(new Error("Faylni o'qib bo'lmadi")); r.readAsDataURL(f); });
  }
  async function sendExcuse(ev, absId, maxMb) {
    ev.preventDefault();
    const f = ev.target, err = f.querySelector(".tk-err"), btn = f.querySelector("button[type=submit]");
    err.textContent = "";
    const file = f.file.files[0];
    if (!file) { err.textContent = "Faylni tanlang"; return; }
    if (!/\.(pdf|jpe?g)$/i.test(file.name)) { err.textContent = "Faqat PDF yoki JPG fayl"; return; }
    if (file.size > maxMb * 1024 * 1024) { err.textContent = `Fayl ${maxMb} MB dan katta`; return; }
    btn.disabled = true; btn.textContent = "Yuklanmoqda…";
    try {
      const data = await readFile(file);
      const body = { absence_id: absId, reason: f.reason.value, note: f.note.value, name: file.name, data };
      if (!absId) { body.start = f.start.value; body.end = f.end.value || f.start.value; }
      const r = await api("/api/talaba/requests/excuse", { method: "POST", body });
      toast(`Hujjat yuborildi — ${r.office} ko'rib chiqadi`);
      route();
    } catch (e) { err.textContent = e.message; btn.disabled = false; btn.textContent = "Yuborish"; }
  }
  function reqRow(x) {
    const cls = x.status === "rad" ? "bad" : x.status === "yangi" ? "warn" : "ok";
    const what = x.kind === "sababli" ? `${esc(x.reason_name || "")} · ${dmy(x.start)}${x.end && x.end !== x.start ? " – " + dmy(x.end) : ""}` : `${esc(x.lang_name)} · ${esc(x.purpose || "")}`;
    return `<div class="tk-row"><div class="tk-main-c"><div class="tk-t">${esc(x.kind_name)} <span class="tk-muted tk-small">#${esc(x.id)}</span></div>
      <div class="tk-d">${what} · yuborildi ${dmyhm(x.created_at)}</div>
      ${x.has_file ? `<div class="tk-d"><a href="/api/talaba/requests/${x.id}/file" target="_blank" rel="noopener">${esc(x.file_name)}</a></div>` : ""}
      ${x.review_note ? `<div class="tk-d">Izoh: ${esc(x.review_note)}</div>` : ""}
      ${x.has_doc ? `<div style="margin-top:6px"><a class="btn sm primary" href="/api/talaba/requests/${x.id}/document">Yuklab olish · ${esc(x.doc_reg)}</a></div>` : ""}</div>
      <div class="tk-r"><span class="tk-pill ${cls}">${esc(x.status_name)}</span></div></div>`;
  }

  // ================================================================ OTRABOTKA
  async function pRetakes(m) {
    const d = await api("/api/talaba/retakes");
    const base = Date.now();
    const card = (r) => `<div class="tk-card"><div class="tk-row" style="padding:0"><div class="tk-main-c">
        <div class="tk-t">${esc(r.subject)}</div><div class="tk-d">${esc(r.kind_label)} · ${esc(r.sem_label)}${r.teacher ? " · " + esc(r.teacher) : ""}</div></div>
        <div class="tk-r"><span class="tk-pill ${r.status === "berildi" ? (r.tone === "red" ? "bad" : r.tone === "amber" ? "warn" : "ok") : r.status === "tasdiqlandi" ? "ok" : "info"}">${esc(r.status_name)}</span></div></div>
      <dl class="tk-kv"><dt>Varaqa</dt><dd>${esc(r.reg_no || "—")}</dd><dt>Berilgan</dt><dd>${dmyhm(r.issued_at)}</dd><dt>Muddat</dt><dd>${dmyhm(r.due_at)}</dd>
        ${r.score_old != null && r.max_score ? `<dt>Oldingi ball</dt><dd>${esc(r.score_old)} / ${esc(r.max_score)}</dd>` : ""}
        ${r.score_new != null && r.max_score ? `<dt>Yangi ball</dt><dd><b>${esc(r.score_new)}</b> / ${esc(r.max_score)}</dd>` : ""}
        ${r.reason ? `<dt>Asos</dt><dd>${esc(r.reason)}</dd>` : ""}</dl>
      ${r.hours_left != null ? `<p style="margin:10px 0 0">⏱ <span class="tk-cd ${esc(r.tone)}" data-h="${r.hours_left}">${esc(countdown(r.hours_left))}</span></p>` : ""}</div>`;
    m.innerHTML = head("Otrabotka", `Varaqani o'qituvchiga topshirib, imzolatib, muddat ichida ${esc(d.office)}ga qaytaring.`) +
      (d.items.length ? `<div class="tk-g2">${d.items.map(card).join("")}</div>` : `<div class="tk-card"><div class="tk-empty">Sizda otrabotka varaqalari yo'q.</div></div>`);
    if (d.items.some((r) => r.hours_left != null)) timers.push(setInterval(() => {
      const el = (Date.now() - base) / 3600000;
      $$("[data-h]", m).forEach((e) => { e.textContent = countdown(+e.dataset.h - el); });
    }, 30000));
  }

  // ================================================================ IMTIHONLAR
  async function pExams(m) {
    const d = await api("/api/talaba/exams");
    const P = d.permit;
    const up = d.slots.filter((x) => !x.past), past = d.slots.filter((x) => x.past);
    const slot = (x) => `<div class="tk-row"><div class="tk-date ${x.past ? "past" : ""}"><b>${esc(x.exam_date.slice(8, 10))}</b><small>${esc(MON[+x.exam_date.slice(5, 7) - 1])}</small></div>
      <div class="tk-main-c"><div class="tk-t">${esc(x.subject)}</div><div class="tk-d">${esc(WD[new Date(x.exam_date + "T00:00").getDay()])}, ${esc(x.start_time)}–${esc(x.end_time)}${x.room ? " · " + esc(x.room) : ""}</div>
        ${x.examiner ? `<div class="tk-d">Imtihon oluvchi: ${esc(x.examiner)}</div>` : ""}</div>
      <div class="tk-r">${x.past ? '<span class="tk-pill">O\'tgan</span>' : `<span class="tk-pill ${x.days <= 3 ? "warn" : "info"}">${x.days === 0 ? "Bugun" : esc(x.days) + " kun"}</span>`}</div></div>`;
    m.innerHTML = head("Imtihonlar", "Yakuniy nazoratga ruxsatnoma va sessiya jadvali") + `
      <div class="tk-card"><div class="tk-head" style="margin-bottom:6px"><div><h3 style="margin:0">Imtihonga kirish ruxsatnomasi</h3></div>
        <span class="tk-pill ${P.eligible ? "ok" : "bad"}">${P.eligible ? "✓ Ruxsat bor" : "✗ Hozircha ruxsat yo'q"}</span></div>
        ${P.checks.map((c) => `<div class="tk-check ${c.ok ? "ok" : "no"}"><span class="ic">${c.ok ? "✓" : "✗"}</span><div><b>${esc(c.label)}</b>${c.detail ? `<span>${esc(c.detail)}</span>` : ""}</div></div>`).join("")}
        <p class="tk-small tk-muted" style="margin-top:8px">${P.eligible ? "Ruxsatnoma " + esc(d.office) + " tomonidan rasmiylashtiriladi." : "Sabablarni bartaraf etish bo'yicha " + esc(d.office) + "ga murojaat qiling."}</p></div>
      <div class="tk-card"><h3>Sessiya jadvali</h3>
        ${d.sessions.length ? `<div class="tk-pills" style="margin-bottom:8px">${d.sessions.map((s) => `<span class="tk-pill info">${esc(s.name)} · ${dmy(s.start)} – ${dmy(s.end)}</span>`).join("")}</div>` : ""}
        <div class="tk-list">${up.length ? up.map(slot).join("") : '<div class="tk-empty">Kelgusi imtihonlar jadvali hali e\'lon qilinmagan.</div>'}</div>
        ${d.windows.length ? `<h3 style="margin-top:14px">Qayta topshirish muddatlari</h3><div class="tk-pills">${d.windows.map((w) => `<span class="tk-pill">${esc(w.name)}: ${dmy(w.start)} – ${dmy(w.end)}</span>`).join("")}</div>` : ""}</div>
      ${past.length ? `<div class="tk-card"><h3>O'tgan imtihonlar</h3><div class="tk-list">${past.slice(-12).reverse().map(slot).join("")}</div></div>` : ""}`;
  }

  // ================================================================ APELLYATSIYA
  async function pAppeals(m) {
    const d = await api("/api/talaba/appeals");
    const opts = d.options;
    const form = !d.can_file ? `<p class="tk-small">Apellyatsiya faqat faol talabalardan qabul qilinadi.</p>`
      : opts.length ? `<form class="tk-form" id="ap-form"><label class="tk-field"><span>Fan va natija</span><select name="opt">${opts.map((o, i) => `<option value="${i}">${esc(o.subject)} — ${esc(o.score)} ball (${esc(o.letter)}), ${esc(o.sem_label)} · muddat ${dmy(o.deadline)}</option>`).join("")}</select></label>
          <label class="tk-field"><span>Sabab</span><textarea name="reason" maxlength="1000" placeholder="Qaysi topshiriq yoki savol noto'g'ri baholangan deb hisoblaysiz?" required></textarea></label>
          <div class="tk-err"></div><div class="tk-actions"><button class="btn primary" type="submit">Apellyatsiya berish</button></div></form>`
      : `<div class="tk-empty">Hozir apellyatsiya berish mumkin bo'lgan natija yo'q. Natija e'lon qilingandan keyin ${esc(d.days)} kun ichida beriladi.</div>`;
    const list = d.items.length ? d.items.map((a) => `<div class="tk-row"><div class="tk-main-c"><div class="tk-t">${esc(a.subject)} <span class="tk-small tk-muted">· ${esc(a.sem_label)}</span></div>
        <div class="tk-d">Berilgan: ${dmyhm(a.filed_at)} · natija ${esc(a.score_old)} ball</div>
        ${a.status === "qaror" ? `<div class="tk-d"><b>${esc(a.decision_name)}</b>${a.score_new != null ? ` — yangi natija ${esc(a.score_new)} ball` : ""}${a.decision_note ? " · " + esc(a.decision_note) : ""}</div>` : ""}</div>
        <div class="tk-r"><span class="tk-pill ${a.status === "qaror" ? (a.decision === "oshirish" ? "ok" : "info") : "warn"}">${esc(a.status_name)}</span></div></div>`).join("")
      : `<div class="tk-empty">Siz hali apellyatsiya bermagansiz.</div>`;
    m.innerHTML = head("Apellyatsiya", `Yakuniy nazorat natijasi e'lon qilingandan keyin ${esc(d.days)} kun ichida. Komissiya (kafedra, Imtihon bo'limi, Akademik bo'lim) ko'rib chiqadi.`) + `
      <div class="tk-card"><h3>Yangi apellyatsiya</h3>${form}</div>
      <div class="tk-card"><h3>Mening apellyatsiyalarim</h3><div class="tk-list">${list}</div></div>`;
    const f = $("#ap-form");
    if (f) f.addEventListener("submit", async (ev) => {
      ev.preventDefault();
      const o = opts[+f.opt.value], err = f.querySelector(".tk-err"); err.textContent = "";
      if (f.reason.value.trim().length < 5) { err.textContent = "Sababni batafsilroq yozing (kamida 5 belgi)"; return; }
      try {
        await api("/api/talaba/appeals", { method: "POST", body: { subject: o.subject, semester: o.semester, reason: f.reason.value } });
        toast("Apellyatsiya qabul qilindi"); route();
      } catch (e) { err.textContent = e.message; }
    });
  }

  // ================================================================ KONTRAKT
  async function pContract(m) {
    const d = await api("/api/talaba/contract");
    if (d.kind !== "kontrakt") {
      m.innerHTML = head("Kontrakt", "") + `<div class="tk-card"><div class="tk-stat ok"><span class="k">Ta'lim asosi</span><span class="v">${esc(d.basis)}</span><span class="s">Kontrakt to'lovi talab qilinmaydi.</span></div></div>`;
      return;
    }
    const ST = { tolangan: ["ok", "To'langan"], kutilmoqda: ["info", "Kutilmoqda"], muddati_otgan: ["bad", "Muddati o'tgan"] };
    m.innerHTML = head("Kontrakt", "Faqat ko'rish uchun — to'lovlar bu yerda qabul qilinmaydi.") + `
      <div class="tk-g3">
        <div class="tk-card"><div class="tk-stat"><span class="k">Yillik kontrakt summasi</span><span class="v" style="font-size:22px">${money(d.amount)}</span></div></div>
        <div class="tk-card"><div class="tk-stat ok"><span class="k">To'langan</span><span class="v" style="font-size:22px">${money(d.paid)}</span>
          <div class="tk-meter thin"><i class="ok" style="width:${Math.min(100, d.pct_paid)}%"></i></div><span class="s">${esc(d.pct_paid)}%</span></div></div>
        <div class="tk-card"><div class="tk-stat ${d.overdue ? "bad" : d.debt ? "" : "ok"}"><span class="k">Qolgan summa</span><span class="v" style="font-size:22px">${money(d.debt)}</span>
          ${d.next ? `<span class="s">Keyingi: ${esc(d.next.label)} — ${dmy(d.next.due)} gacha ${money(d.next.short)}</span>` : '<span class="s">To\'liq to\'langan</span>'}</div></div>
      </div>
      ${d.deferment ? `<div class="tk-card"><div class="tk-ok-line">To'lov muddati ${dmy(d.deferment.until)} gacha uzaytirilgan (Registrator ofisi qarori).</div></div>` : ""}
      <div class="tk-card"><h3>To'lov jadvali</h3><div class="tk-list">${d.plan.map((p) => `<div class="tk-row"><div class="tk-date ${p.status === "tolangan" ? "past" : ""}"><b>${esc(p.due.slice(8, 10))}</b><small>${esc(MON[+p.due.slice(5, 7) - 1])}</small></div>
        <div class="tk-main-c"><div class="tk-t">${esc(p.label)} — ${esc(p.pct)}%</div><div class="tk-d">${dmy(p.due)} gacha jami ${money(p.need)}${p.short ? ` · yetishmaydi ${money(p.short)}` : ""}</div></div>
        <div class="tk-r"><span class="tk-pill ${ST[p.status][0]}">${ST[p.status][1]}</span>${p.status === "kutilmoqda" ? `<div class="tk-small tk-muted">${esc(p.days)} kun</div>` : ""}</div></div>`).join("")}</div>
        <p class="tk-small tk-muted" style="margin-top:8px">To'lov qilgandan keyin ma'lumot Buxgalteriya tomonidan yangilanadi. Savollar bo'yicha — Buxgalteriya yoki ${esc(ME.office)}.</p></div>`;
  }

  // ================================================================ MA'LUMOTNOMA
  async function pCert(m) {
    const d = await api("/api/talaba/requests");
    const certs = d.items.filter((x) => x.kind === "malumotnoma");
    m.innerHTML = head("Ma'lumotnoma so'rash", `O'qish joyidan ma'lumotnoma — ${esc(d.office)} tayyorlaydi; tayyor bo'lgach shu yerdan yuklab olasiz.`) + `
      <div class="tk-card"><h3>Yangi so'rov</h3>${d.can_request ? `<form class="tk-form" id="ct-form">
        <div class="tk-field"><span>Til</span><div class="tk-seg">${Object.entries(d.langs).map(([k, v], i) => `<label><input type="radio" name="lang" value="${esc(k)}" ${i ? "" : "checked"}><span>${esc(v)}</span></label>`).join("")}</div></div>
        <label class="tk-field"><span>Qayerga taqdim etish uchun</span><select name="purpose">${d.purposes.map((p) => `<option>${esc(p)}</option>`).join("")}</select></label>
        <label class="tk-field"><span>Izoh (ixtiyoriy)</span><input name="note" maxlength="300" placeholder="Masalan, 2 nusxada kerak"></label>
        <div class="tk-err"></div><div class="tk-actions"><button class="btn primary" type="submit">So'rov yuborish</button></div></form>`
        : `<p class="tk-small">Ma'lumotnoma faqat faol talabalarga beriladi. ${esc(d.office)}ga murojaat qiling.</p>`}</div>
      <div class="tk-card"><h3>Mening so'rovlarim</h3><div class="tk-list">${certs.length ? certs.map(reqRow).join("") : '<div class="tk-empty">Hali so\'rov yuborilmagan.</div>'}</div></div>`;
    const f = $("#ct-form");
    if (f) f.addEventListener("submit", async (ev) => {
      ev.preventDefault();
      const err = f.querySelector(".tk-err"); err.textContent = "";
      try {
        const r = await api("/api/talaba/requests/certificate", { method: "POST", body: { lang: f.lang.value, purpose: f.purpose.value, note: f.note.value } });
        toast(`So'rov yuborildi — ${r.office}`); route();
      } catch (e) { err.textContent = e.message; }
    });
  }

  // ================================================================ PROFIL
  async function pProfile(m) {
    const d = await api("/api/talaba/profile");
    const kv = [["F.I.Sh.", d.name], ["HEMIS ID", d.hemis_id], ["Fakultet", d.faculty], ["Yo'nalish", d.direction], ["Guruh", `${d.group} · ${d.course}-kurs`],
      ["Ta'lim shakli", `${d.study_form || "kunduzgi"} · ${d.level}`], ["Ta'lim asosi", d.basis], ["Telefon", d.phone || "—"], ["Hudud", d.region || "—"], ["Maqom", d.status]];
    m.innerHTML = head("Profil", esc(d.contact_note)) + `
      <div class="tk-g2">
        <div class="tk-card"><h3>Shaxsiy ma'lumotlar</h3><dl class="tk-kv">${kv.map(([k, v]) => `<dt>${esc(k)}</dt><dd>${esc(v)}</dd>`).join("")}</dl>
          <p class="tk-small tk-muted" style="margin-top:10px">Aloqa ma'lumotlari qisman yashirilgan.</p></div>
        <div class="tk-card"><h3>Parolni almashtirish</h3><form class="tk-form" id="pw-form">
          <label class="tk-field"><span>Joriy parol</span><input type="password" name="cur" autocomplete="current-password" maxlength="128"></label>
          <label class="tk-field"><span>Yangi parol</span><input type="password" name="n1" autocomplete="new-password" maxlength="128"></label>
          <label class="tk-field"><span>Takrorlang</span><input type="password" name="n2" autocomplete="new-password" maxlength="128"></label>
          <div class="tk-err"></div><div class="tk-actions"><button class="btn primary" type="submit">Saqlash</button></div>
          <p class="tk-small tk-muted">Oxirgi o'zgartirish: ${d.password_changed ? dmyhm(d.password_changed) : "—"}. Parol almashtirilsa, boshqa qurilmalardagi sessiyalar yopiladi.</p></form></div>
      </div>
      <div class="tk-card"><div class="tk-head" style="margin-bottom:4px"><div><h3 style="margin:0">Faol sessiyalar</h3></div>
        ${d.sessions.length > 1 ? '<button class="btn sm" type="button" id="ss-others">Boshqalarini yopish</button>' : ""}</div>
        <div class="tk-list">${d.sessions.map((s) => `<div class="tk-row"><div class="tk-main-c"><div class="tk-t">${esc(s.device)} ${s.current ? '<span class="tk-pill ok">Shu qurilma</span>' : ""}</div>
          <div class="tk-d">IP ${esc(s.ip)} · kirgan ${dmyhm(s.created)} · oxirgi faollik ${dmyhm(s.last_seen)}</div></div>
          ${s.current ? "" : `<div class="tk-r"><button class="btn sm" type="button" data-rv="${s.id}">Yopish</button></div>`}</div>`).join("")}</div></div>`;
    const f = $("#pw-form");
    f.addEventListener("submit", async (ev) => {
      ev.preventDefault();
      const err = f.querySelector(".tk-err"); err.textContent = "";
      if (f.n1.value !== f.n2.value) { err.textContent = "Yangi parollar bir xil emas"; return; }
      try {
        const r = await api("/api/talaba/password", { method: "POST", body: { current: f.cur.value, new: f.n1.value } });
        toast("Parol almashtirildi" + (r.closed ? ` · ${r.closed} ta sessiya yopildi` : "")); route();
      } catch (e) { err.textContent = e.message; }
    });
    $$("[data-rv]", m).forEach((b) => b.addEventListener("click", async () => {
      try { await api(`/api/talaba/sessions/${b.dataset.rv}/revoke`, { method: "POST" }); toast("Sessiya yopildi"); route(); } catch (e) { toast(e.message, true); }
    }));
    const o = $("#ss-others");
    if (o) o.addEventListener("click", async () => {
      try { const r = await api("/api/talaba/sessions/revoke-others", { method: "POST" }); toast(`${r.closed} ta sessiya yopildi`); route(); } catch (e) { toast(e.message, true); }
    });
  }

  // ================================================================ XODIMLAR: TALABA MUROJAATLARI
  const SF = { status: "ochiq", kind: "", q: "", student_id: +(new URLSearchParams(location.search).get("student") || 0) };
  async function staffBoot() {
    show("tk-staff");
    document.title = "Talaba murojaatlari — ISFT Core";
    await staffLoad();
  }
  async function staffLoad() {
    const m = $("#tk-staff-main");
    const qs = new URLSearchParams({ status: SF.status, kind: SF.kind, q: SF.q, student_id: SF.student_id || 0 });
    let d;
    try { d = await api("/api/talaba/staff/requests?" + qs); }
    catch (e) {
      m.innerHTML = `<div class="tk-card"><h2>Talaba murojaatlari</h2><p class="tk-err">${esc(e.message)}</p>
        <p>${e.status === 401 ? 'Avval <a href="/">ISFT Core</a> tizimiga xodim sifatida kiring, so\'ng bu sahifani qayta oching.' : "Bu ro'yxat Registrator ofisi va Sirtqi bo'lim uchun."}</p></div>`;
      return;
    }
    $("#tk-staff-who").innerHTML = `${esc(d.unit_name)}<small>${esc(d.who)}</small>`;
    const c = d.counts, all = Object.values(c).reduce((a, b) => a + b, 0);
    const chip = (k, t, n) => `<button class="tk-chip ${SF.status === k ? "on" : ""}" data-st="${k}" type="button">${esc(t)} <i>${esc(n ?? 0)}</i></button>`;
    m.innerHTML = head("Talaba murojaatlari", `${esc(d.unit_name)} navbati: Talaba kabinetidan kelgan sababli hujjatlar va ma'lumotnoma so'rovlari.`) + `
      <div class="tk-filters">${chip("ochiq", "Ko'rib chiqilmoqda", c.yangi)}${chip("qabul", "Qabul qilingan", c.qabul)}${chip("berildi", "Berilgan", c.berildi)}${chip("rad", "Rad etilgan", c.rad)}${chip("all", "Hammasi", all)}
        <select class="tk-in" id="sf-kind" aria-label="Tur"><option value="">Barcha turlar</option><option value="sababli" ${SF.kind === "sababli" ? "selected" : ""}>Sababli hujjat</option><option value="malumotnoma" ${SF.kind === "malumotnoma" ? "selected" : ""}>Ma'lumotnoma</option></select>
        <input class="tk-in" id="sf-q" type="search" placeholder="Talaba, HEMIS ID yoki guruh" value="${esc(SF.q)}" aria-label="Qidirish">
        ${SF.student_id ? `<button class="tk-chip on" type="button" id="sf-clear">Faqat talaba #${esc(SF.student_id)} ✕</button>` : ""}</div>
      ${d.items.length ? `<div class="tk-g2">${d.items.map(staffCard).join("")}</div>` : `<div class="tk-card"><div class="tk-empty">Bu filtr bo'yicha murojaat yo'q.</div></div>`}`;
    $$("[data-st]", m).forEach((b) => b.addEventListener("click", () => { SF.status = b.dataset.st; staffLoad(); }));
    $("#sf-kind").addEventListener("change", (e) => { SF.kind = e.target.value; staffLoad(); });
    let qt = 0; $("#sf-q").addEventListener("input", (e) => { clearTimeout(qt); qt = setTimeout(() => { SF.q = e.target.value; staffLoad().then(() => { const i = $("#sf-q"); i.focus(); i.setSelectionRange(i.value.length, i.value.length); }); }, 350); });
    const cl = $("#sf-clear"); if (cl) cl.addEventListener("click", () => { SF.student_id = 0; history.replaceState(null, "", "/talaba/xodim"); staffLoad(); });
    $$("[data-dec]", m).forEach((b) => b.addEventListener("click", () => staffDecide(+b.dataset.id, b.dataset.dec)));
  }
  function staffCard(x) {
    const cls = x.status === "rad" ? "bad" : x.status === "yangi" ? "warn" : "ok";
    const ab = x.absence;
    const rows = x.kind === "sababli"
      ? [["Sabab", x.reason_name], ["Sanalar", `${dmy(x.start)}${x.end && x.end !== x.start ? " – " + dmy(x.end) : ""}`],
         ab ? ["Dars qoldirish", `${ab.hours} soat · hozir: ${ab.reason}${ab.doc_status ? " / " + ab.doc_status : ""}`] : ["Dars qoldirish", "ro'yxatda tanlanmagan (sanalar bo'yicha)"],
         ["Fayl", `<a href="/api/talaba/staff/requests/${x.id}/file" target="_blank" rel="noopener">${esc(x.file_name)}</a> · ${Math.max(1, Math.round((x.file_size || 0) / 1024))} KB · ${esc(x.file_scan || "")}`]]
      : [["Til", x.lang_name], ["Maqsad", x.purpose]];
    if (x.note) rows.push(["Talaba izohi", x.note]);
    if (x.reviewed_at) rows.push(["Ko'rib chiqdi", `${x.reviewed_by || ""} · ${dmyhm(x.reviewed_at)}${x.review_note ? " · " + x.review_note : ""}`]);
    if (x.doc_reg) rows.push(["Hujjat", x.doc_reg]);
    const raw = new Set(["Fayl"]);
    const acts = x.status !== "yangi" ? "" : `<div class="tk-req-act"><input class="tk-in" id="note-${x.id}" maxlength="300" placeholder="Izoh (rad etishda majburiy)">
      ${x.kind === "sababli" ? `<button class="btn sm primary" type="button" data-dec="qabul" data-id="${x.id}">Qabul qilish</button>` : `<button class="btn sm primary" type="button" data-dec="berish" data-id="${x.id}">Ma'lumotnoma berish</button>`}
      <button class="btn sm" type="button" data-dec="rad" data-id="${x.id}">Rad etish</button></div>`;
    return `<div class="tk-card tk-req"><div class="tk-req-h"><b>${esc(x.full_name)}</b><span class="tk-pill ${cls}">${esc(x.status_name.replace("Tayyor — yuklab olish mumkin", "Berildi"))}</span></div>
      <div class="tk-small tk-muted">${esc(x.kind_name)} #${esc(x.id)} · HEMIS ${esc(x.hemis_id)} · ${esc(x.grp)} · ${esc(x.course)}-kurs · ${esc(x.study_form)} · ${dmyhm(x.created_at)}</div>
      <dl class="tk-kv">${rows.map(([k, v]) => `<dt>${esc(k)}</dt><dd>${raw.has(k) ? v : esc(v)}</dd>`).join("")}</dl>${acts}</div>`;
  }
  async function staffDecide(id, action) {
    const note = ($("#note-" + id) || {}).value || "";
    if (action === "rad" && note.trim().length < 3) { toast("Rad etish sababini izohga yozing", true); $("#note-" + id).focus(); return; }
    try {
      const r = await api(`/api/talaba/staff/requests/${id}/decide`, { method: "POST", body: { action, note } });
      toast(r.status === "berildi" ? `Ma'lumotnoma berildi: ${r.doc_reg}` : r.status === "qabul" ? "Hujjat qabul qilindi — dars qoldirish sababli deb belgilandi" : "Rad etildi");
      staffLoad();
    } catch (e) { toast(e.message, true); }
  }

  /* Kengaytma sahifalar (boshqa modullar, masalan /amaliyot_talaba.js — talaba.js dan keyin yuklanadi):
     TK.addPage({k, t, s, i, path, f: async (m) => …}) — «Profil»dan oldin qo'shiladi; yordamchilar: api, esc, toast, dmy, head. */
  window.TK = { api, esc, toast, dmy, head,
    addPage(p) {
      if (PAGES.some((x) => x.k === p.k)) return;
      if (p.path) P[p.i = p.i || p.k] = p.path;
      PAGES.splice(PAGES.length - 1, 0, p);
      if (ME && !ME.must_change && !STAFF) { renderShell(); route(); }
    } };

  boot();
})();
