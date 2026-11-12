/* =====================================================================
   Kirish sahifasi · 2-variant "Kiosk"
   Ikki qadamli, sensorli ekran va proyektor uchun:
     1) "Kim sifatida kirasiz?" — lavozimlar katta plitkalar to'rida;
     2) Parol — tanlangan shaxs kartasi va katta, sensorga qulay parol maydoni.
   app.js'dagi tanlash/kirish mantiqi o'zgarmaydi: drawRoles/doLogin/showLogin
   faqat o'raladi (LOGIN_AFTER ichida).
   ===================================================================== */
window.LOGIN_HTML = `
<header class="k-top">
  <div class="k-brand">
    <span class="k-logo"><img src="/brand/logo-sm.png" alt="ISFT instituti logotipi" width="34" height="26"></span>
    <div class="k-bt"><span class="k-wm"><b>ISFT</b> <span>Core</span></span><small>Institut boshqaruv tizimi</small></div>
  </div>
  <ol class="k-steps" aria-label="Kirish bosqichlari">
    <li class="k-st" data-s="1" aria-current="step"><button type="button" id="lv2Step1" tabindex="-1"><i><b>1</b><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M20 6 9 17l-5-5"/></svg></i><span>Lavozim</span></button></li>
    <li class="k-st" data-s="2"><span class="k-stb"><i><b>2</b></i><span>Parol</span></span></li>
  </ol>
  <div class="k-when" aria-label="Bugungi sana"><b id="lv2Time"></b><span id="lv2Date"></span></div>
</header>

<div class="k-stage">
  <!-- 1-qadam: lavozim -->
  <section class="k-step k-s1" id="lv2S1" aria-labelledby="lv2H1">
    <div class="k-head">
      <h1 id="lv2H1">Kim sifatida kirasiz?</h1>
      <p>Lavozimingizni tanlang — keyingi qadamda parol so'raladi.</p>
    </div>
    <div class="k-controls">
      <div class="k-seg" id="lvlTabs" role="tablist" aria-label="Lavozim guruhi"></div>
      <label class="k-search"><span data-ico="search"></span>
        <input id="roleSearch" type="search" placeholder="Lavozim yoki ism bo'yicha qidirish" aria-label="Lavozim yoki ism bo'yicha qidirish" autocomplete="off" enterkeyhint="search">
        <kbd class="k-kbd" aria-hidden="true">/</kbd></label>
    </div>
    <div id="roleList" class="k-grid" role="listbox" aria-label="Lavozimlar" style="--cols:3">
      <div class="k-skel" aria-hidden="true"></div><div class="k-skel" aria-hidden="true"></div><div class="k-skel" aria-hidden="true"></div>
    </div>
  </section>

  <!-- 2-qadam: parol -->
  <section class="k-step k-s2" id="lv2S2" aria-labelledby="lv2H2" tabindex="-1" hidden>
    <form class="k-card" id="loginForm" onsubmit="event.preventDefault()">
      <div class="k-who">
        <button type="button" class="k-back" id="lv2Back"><span data-ico="arrow"></span>Boshqa lavozim</button>
        <div class="k-id">
          <span class="k-av" id="lv2Av" aria-hidden="true"></span>
          <div class="k-idt">
            <span class="k-lvl" id="lv2Lvl"></span>
            <h2 id="lv2Role"></h2>
            <p id="lv2Name"></p>
          </div>
        </div>
        <p class="k-note"><span data-ico="lock"></span><span>Haqiqiy tizimda kirish OneID yoki HEMIS akkaunti orqali · ma'lumotlar sun'iy (demo)</span></p>
      </div>

      <div class="k-pad">
        <div class="k-pw">
          <span class="k-pwbadge" aria-hidden="true"><span data-ico="lock"></span></span>
          <h3 id="lv2H2"><label for="password">Parolni kiriting</label></h3>
          <p class="k-pwsub">Tanlangan lavozim uchun shaxsiy parolingiz</p>
          <!-- parol menejerlari uchun: qaysi akkaunt (ko'rinmaydi) -->
          <input class="k-sr" id="lv2User" type="text" autocomplete="username" tabindex="-1" aria-hidden="true" readonly>
          <div class="k-field" id="pwWrap">
            <span class="k-fico" data-ico="lock"></span>
            <input id="password" type="password" autocomplete="current-password" placeholder="Parolingizni kiriting"
              autocapitalize="off" autocorrect="off" spellcheck="false" enterkeyhint="go" aria-describedby="lv2Msg">
            <button type="button" class="k-eye" id="pwEye" aria-label="Parolni ko'rsatish" aria-pressed="false" title="Parolni ko'rsatish / yashirish"><span data-ico="eye"></span></button>
          </div>
          <p class="k-msg" id="lv2Msg" role="status" aria-live="polite"><span data-ico="info"></span><span id="lv2MsgT">${window.ISFT_HIDE_DEMO_HINT || !(window.ISFT_FLAGS && ISFT_FLAGS.demo_pw) ? "Parol katta-kichik harfni farqlaydi" : "Sinov rejimi: parol " + ISFT_FLAGS.demo_pw}</span></p>
          <button id="loginBtn" type="button" class="btn primary block k-go" disabled><span id="loginTxt">Kirish</span> <span data-ico="arrow"></span></button>
        </div>
      </div>
    </form>
  </section>
</div>`;

window.LOGIN_AFTER = function () {
  const L = document.getElementById("login");
  if (!L || !L.classList.contains("lv2")) return;
  const q = s => L.querySelector(s);
  const S1 = q("#lv2S1"), S2 = q("#lv2S2"), LIST = q("#roleList"), PW = q("#password"), WRAP = q("#pwWrap"), EYE = q("#pwEye");
  const DEMO = typeof DEMO_PW === "string" ? DEMO_PW : "";
  const reduced = () => window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const coarse = () => window.matchMedia("(pointer: coarse)").matches;
  let STEP = 1, msgT = 0, lastEmpty = false;
  const busy = () => !!$("#loginBtn").dataset.busy;

  /* ---- sana va soat (ochiq ma'lumot) ---- */
  const MO = ["yanvar", "fevral", "mart", "aprel", "may", "iyun", "iyul", "avgust", "sentabr", "oktabr", "noyabr", "dekabr"];
  const WD = ["yakshanba", "dushanba", "seshanba", "chorshanba", "payshanba", "juma", "shanba"];
  const tick = () => {
    const d = new Date();
    q("#lv2Time").textContent = String(d.getHours()).padStart(2, "0") + ":" + String(d.getMinutes()).padStart(2, "0");
    q("#lv2Date").textContent = `${d.getDate()}-${MO[d.getMonth()]}, ${WD[d.getDay()]}`;
  };
  tick(); clearInterval(window.__lv2clock); window.__lv2clock = setInterval(tick, 15000);

  /* ---- plitkalar to'rini muvozanatlash: qatorlar teng bo'lsin (15 → 5+5+5, 6 → 3+3).
     Past ekranda (1280×720) to'r pastki panel ostiga tushsa — avval plitkalar ixchamlashadi, kerak bo'lsa qatorlar kamayadi. ---- */
  function balance() {
    const W = S1.clientWidth; if (!W) return;
    const cs = getComputedStyle(LIST), num = v => parseFloat(cs.getPropertyValue(v));
    const gap = parseFloat(cs.columnGap) || 14, min = num("--tile-min") || 220, dmin = num("--tile-dense") || 150;
    const n = LIST.querySelectorAll(".role-row").length;
    const fit = w => Math.floor((W + gap) / (w + gap));
    const max = Math.max(2, Math.min(5, fit(min))), hard = Math.max(max, Math.min(8, fit(dmin)));
    let rows = Math.max(1, Math.ceil(n / max));
    const set = () => LIST.style.setProperty("--cols", n ? Math.ceil(n / rows) : Math.min(max, 3));
    LIST.classList.remove("k-dense");
    LIST.classList.toggle("k-few", n > 0 && rows === 1 && max > 2);
    set();
    if (STEP !== 1 || innerWidth <= 720) return;
    const bottom = parseFloat(getComputedStyle(L).paddingBottom) || 0;
    const over = () => LIST.getBoundingClientRect().bottom + scrollY + 8 > innerHeight - bottom;
    if (!over()) return;
    LIST.classList.remove("k-few"); LIST.classList.add("k-dense");          /* 1) ixchamroq plitkalar */
    while (rows > 1 && over() && Math.ceil(n / (rows - 1)) <= hard) { rows--; set(); }   /* 2) kamroq qator */
  }
  addEventListener("resize", () => { if (STEP === 1) balance(); });

  /* ---- qadamlar orasida o'tish (slayd + so'nish) ---- */
  function goStep(n, instant) {
    const from = n === 2 ? S1 : S2, to = n === 2 ? S2 : S1;
    [S1, S2].forEach(s => s.getAnimations().forEach(a => a.cancel()));
    L.dataset.step = n;
    q("#lv2Step1").tabIndex = n === 2 ? 0 : -1;
    q('.k-st[data-s="1"]').setAttribute("aria-current", n === 1 ? "step" : "false");
    q('.k-st[data-s="2"]').setAttribute("aria-current", n === 2 ? "step" : "false");
    if (n === 1) mask();
    if (STEP === n) { to.hidden = false; to.inert = false; from.hidden = true; if (n === 1) balance(); return; }
    STEP = n;
    to.hidden = false; to.inert = false; from.inert = true;
    if (n === 1) balance();
    if (scrollY > 0) scrollTo({top: 0, behavior: instant || reduced() ? "auto" : "smooth"});
    if (instant || reduced() || !to.animate) { from.hidden = true; return; }
    const dx = n === 2 ? 56 : -56, ease = "cubic-bezier(.2,.8,.2,1)";
    const out = from.animate([{opacity: 1, transform: "none"}, {opacity: 0, transform: `translateX(${-dx}px)`}], {duration: 170, easing: "cubic-bezier(.4,0,1,1)", fill: "forwards"});
    out.onfinish = () => { if (STEP === n) { from.hidden = true; out.cancel(); } };
    to.animate([{opacity: 0, transform: `translateX(${dx}px)`}, {opacity: 1, transform: "none"}], {duration: 360, delay: 140, easing: ease, fill: "backwards"});
  }

  /* parol ko'rinib qolmasin: qadamdan chiqishda yana yashiriladi */
  function mask() {
    if (PW.type === "password") return;
    PW.type = "password";
    EYE.classList.remove("on"); EYE.setAttribute("aria-pressed", "false"); EYE.setAttribute("aria-label", "Parolni ko'rsatish");
  }
  function focusPw() {
    /* sensorli ekranda tizim klaviaturasi o'z-o'zidan ochilmasin — maydon bosilganda ochiladi */
    if (coarse()) { $("#loginBtn").focus({preventScroll: true}); return; }
    PW.focus({preventScroll: true});
    PW.select();   /* sinov paroli oldindan to'ldirilgan: Enter — kirish, yozishni boshlash — almashtiradi */
  }

  function toPw() {
    const u = USERS.find(x => x.id === selUser); if (!u) return;
    const av = q("#lv2Av"); setAv(av, u, "k-av");
    q("#lv2Lvl").textContent = LVL_TABS[u.level] || "";
    q("#lv2Role").textContent = u.role;
    q("#lv2Name").textContent = personOf(u);
    q("#lv2User").value = u.role;
    if (!PW.value) PW.value = DEMO;
    msg();
    $("#loginBtn").disabled = false;
    goStep(2);
    focusPw();
  }
  function back() {
    if (STEP !== 2 || busy()) return;
    goStep(1);
    const t = LIST.querySelector(".role-row.sel") || LIST.querySelector(".role-row");
    t && t.focus({preventScroll: true});
    t && t.scrollIntoView({block: "nearest"});
  }
  q("#lv2Back").onclick = back;
  q("#lv2Step1").onclick = back;

  /* ---- drawRoles: app.js chizgandan keyin plitka bosilsa — 2-qadamga o'tish ---- */
  const origDraw = window.drawRoles;
  window.drawRoles = function () {
    const r = origDraw.apply(this, arguments);
    LIST.classList.remove("fade");
    LIST.querySelectorAll(".role-row").forEach(row => {
      const o = row.onclick;
      row.onclick = e => { if (o) o.call(row, e); toPw(); };
      /* app.js Enter'da #password'ga fokus beradi — toPw o'zi fokuslaydi (sensorli ekranda klaviaturasiz) */
      row.onkeydown = e => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); row.click(); } };
    });
    balance();
    return r;
  };
  /* tizimdan chiqilganda yoki sessiya tugaganda — doim 1-qadamdan */
  const origShow = window.showLogin;
  window.showLogin = function () { goStep(1, true); msg(); return origShow.apply(this, arguments); };
  /* kirish: xato turini eslab qolish; muvaffaqiyatli kirishdan keyin parol maydonda qolmasin */
  const origLogin = window.doLogin;
  window.doLogin = async function () {
    lastEmpty = !PW.value;
    const r = await origLogin.apply(this, arguments);
    if (!$("#app").classList.contains("hidden")) { PW.value = ""; mask(); msg(); }
    return r;
  };

  /* LOGIN_AFTER kech qolgan bo'lsa (ro'yxat allaqachon chizilgan) — qayta chizib, ilgaklarni ulash */
  if (LIST.querySelector(".role-row, .role-empty")) drawRoles();

  /* ---- plitkalar orasida strelkalar bilan yurish ---- */
  LIST.addEventListener("keydown", e => {
    const tiles = [...LIST.querySelectorAll(".role-row")], i = tiles.indexOf(document.activeElement);
    if (i < 0) return;
    const cols = parseInt(LIST.style.getPropertyValue("--cols")) || 1;
    let j = {ArrowRight: i + 1, ArrowLeft: i - 1, ArrowDown: i + cols, ArrowUp: i - cols, Home: 0, End: tiles.length - 1}[e.key];
    if (j == null) return;
    e.preventDefault();
    j = Math.max(0, Math.min(tiles.length - 1, j));
    tiles[j].focus();
  });

  /* ---- parol: izoh satri (sinov rejimi / xato / Caps Lock) ---- */
  function msg(kind, text) {
    clearTimeout(msgT);
    const m = q("#lv2Msg");
    m.classList.toggle("bad", kind === "bad");
    m.classList.toggle("warn", kind === "warn");
    q("#lv2MsgT").textContent = text || (window.ISFT_HIDE_DEMO_HINT || !DEMO ? "Parol katta-kichik harfni farqlaydi" : `Sinov rejimi: parol ${DEMO}`);
    if (kind === "bad") msgT = setTimeout(() => msg(), 3200);
  }
  const caps = e => {
    if (!e.getModifierState) return;
    const on = e.getModifierState("CapsLock"), m = q("#lv2Msg");
    if (on && !m.classList.contains("bad")) msg("warn", "Caps Lock yoqilgan");
    else if (!on && m.classList.contains("warn")) msg();
  };
  PW.addEventListener("keydown", caps);
  PW.addEventListener("keyup", caps);
  PW.addEventListener("blur", () => { if (q("#lv2Msg").classList.contains("warn")) msg(); });
  PW.addEventListener("input", () => { if (q("#lv2Msg").classList.contains("bad")) msg(); });

  /* app.js xato bo'lsa #pwWrap ga .err qo'yadi — matnli izoh */
  new MutationObserver(() => {
    if (!WRAP.classList.contains("err")) return;
    msg("bad", lastEmpty ? "Parolni kiriting" : "Parol noto'g'ri — qayta kiriting");
    try { navigator.vibrate && navigator.vibrate([40, 40, 40]); } catch (err) {}
  }).observe(WRAP, {attributes: true, attributeFilter: ["class"]});

  /* ---- klaviatura ---- */
  document.addEventListener("keydown", e => {
    if (L.classList.contains("hidden") || e.ctrlKey || e.metaKey || e.altKey) return;
    const t = e.target instanceof Element ? e.target : document.body;
    if (STEP === 2) {
      if (e.key === "Escape") { e.preventDefault(); back(); }
      else if (t === PW) return;                                  /* Enter — app.js o'zi yuboradi */
      else if (e.key === "Enter" && !t.closest("button, a, input")) { e.preventDefault(); doLogin(); }
      else if (e.key.length === 1 && e.key !== " " && !t.closest("input, textarea")) { PW.focus(); PW.select(); }   /* yozishni boshlash — parolga */
    } else if (!t.closest("input, textarea, select, [contenteditable]")) {
      /* 1-qadam: yozishni boshlash — qidiruvga o'tadi; "/" — qidiruv */
      if (e.key === "/") { e.preventDefault(); $("#roleSearch").focus(); }
      else if (e.key.length === 1 && e.key !== " ") $("#roleSearch").focus();
    }
  }, true);

  goStep(1, true);
};
