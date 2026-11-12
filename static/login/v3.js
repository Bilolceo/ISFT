/* =====================================================================
   Kirish sahifasi · 3-variant "Ko'rinish"
   Chapda — oq, sokin kirish shakli; o'ngda — qirmizi panel va ISFT Core
   ilovasining CSS bilan chizilgan NAMUNA ko'rinishi (haqiqiy ma'lumot yo'q).
   ===================================================================== */
window.LOGIN_HTML = `
<section class="v3-form" aria-label="Tizimga kirish">
  <div class="v3-inner">
    <header class="v3-brand">
      <img src="/brand/logo-sm.png" alt="ISFT instituti logotipi" width="52" height="39">
      <div><b>ISFT instituti</b><small>ISFT Core · boshqaruv tizimi</small></div>
    </header>

    <div class="v3-head">
      <p class="v3-eyebrow">Xush kelibsiz</p>
      <h1><span class="v3-wm">ISFT <em>Core</em></span>'ga kirish</h1>
      <p class="v3-sub">Lavozimingizni tanlang va parolingizni kiriting.</p>
    </div>

    <form id="loginForm" class="v3-card" autocomplete="off" onsubmit="event.preventDefault()">
      <div class="v3-tabs" id="lvlTabs" role="tablist" aria-label="Lavozim guruhi"></div>
      <label class="v3-search"><span data-ico="search"></span>
        <input id="roleSearch" type="search" placeholder="Lavozim yoki ism bo'yicha qidirish" aria-label="Lavozim yoki ism bo'yicha qidirish" autocomplete="off"></label>
      <div id="roleList" class="v3-list" role="listbox" aria-label="Lavozimlar"></div>

      <div class="v3-pwrow">
        <label for="password">Parol</label>
        <span class="v3-hint"${window.ISFT_HIDE_DEMO_HINT || !(window.ISFT_FLAGS && ISFT_FLAGS.demo_pw) ? ' hidden style="display:none"' : ""}>Sinov rejimi: ${(window.ISFT_FLAGS && ISFT_FLAGS.demo_pw) || ""}</span>
      </div>
      <div class="v3-pw" id="pwWrap">
        <span class="v3-pw-ico" data-ico="lock"></span>
        <input id="password" type="password" autocomplete="current-password" placeholder="Parolingizni kiriting" spellcheck="false" autocapitalize="off">
        <button type="button" class="v3-eye" id="pwEye" aria-label="Parolni ko'rsatish" aria-pressed="false"><span data-ico="eye"></span></button>
      </div>
      <button id="loginBtn" type="button" class="v3-btn" disabled><span id="loginTxt">Kirish</span><span data-ico="arrow"></span></button>
      <p class="v3-foot"><span data-ico="lock"></span>Haqiqiy tizimda kirish OneID yoki HEMIS orqali</p>
    </form>
  </div>
</section>

<aside class="v3-show" aria-label="ISFT Core imkoniyatlari">
  <div class="v3-show-head">
    <span class="v3-pill"><span data-ico="spark"></span>Sun'iy intellekt yordamchisi</span>
    <h2>Institut bo'yicha har bir savolga — tekshirilgan javob</h2>
    <p>Raqamlar, hujjatlar va topshiriqlar bir joyda. ISFT Core har bir javobni institut manbalaridan tekshiradi.</p>
  </div>

  <div class="v3-stage" role="img" aria-label="ISFT Core ilovasining namuna ko'rinishi (haqiqiy ma'lumot emas)">
    <div class="v3-float">
      <div class="v3-mock" aria-hidden="true">
        <div class="m-win">
          <div class="m-bar"><i></i><i></i><i></i><b class="m-wm">ISFT<span>Core</span></b><span class="m-tag">Namuna ko'rinish</span></div>
          <div class="m-body">
            <nav class="m-side">
              <img src="/brand/logo-sm.png" alt="">
              <span class="on" data-ico="dashboard"></span><span data-ico="chat"></span><span data-ico="spark"></span>
              <span data-ico="tasks"></span><span data-ico="report"></span><span data-ico="folder"></span>
            </nav>
            <div class="m-main">
              <div class="m-top">
                <div><b>Boshqaruv paneli</b><i class="sk" style="--w:13em"></i></div>
                <span class="m-live"><i></i>AI faol</span>
              </div>

              <div class="m-kpis">
                <div class="m-kpi"><i class="sk" style="--w:62%"></i><i class="sk m-num" style="--w:46%"></i>
                  <svg viewBox="0 0 100 28" preserveAspectRatio="none"><path class="m-area" d="M0 22 L14 19 L28 21 L42 14 L56 16 L70 9 L84 11 L100 4 L100 28 L0 28Z"/><path class="m-line" d="M0 22 L14 19 L28 21 L42 14 L56 16 L70 9 L84 11 L100 4"/></svg></div>
                <div class="m-kpi"><i class="sk" style="--w:48%"></i><i class="sk m-num" style="--w:34%"></i>
                  <span class="m-cols"><i style="--h:45%"></i><i style="--h:60%"></i><i style="--h:52%"></i><i style="--h:74%"></i><i style="--h:66%"></i><i style="--h:88%"></i><i style="--h:80%"></i></span></div>
                <div class="m-kpi m-kpi-ring"><div><i class="sk" style="--w:80%"></i><i class="sk m-num" style="--w:62%"></i><i class="sk" style="--w:55%"></i></div>
                  <svg viewBox="0 0 36 36"><circle class="m-rt" cx="18" cy="18" r="14"/><circle class="m-rf" cx="18" cy="18" r="14" pathLength="100" stroke-dasharray="78 100"/></svg></div>
                <div class="m-kpi"><i class="sk" style="--w:56%"></i><i class="sk m-num" style="--w:50%"></i>
                  <span class="m-prog"><i style="--w:68%"></i></span><span class="m-trend"><span data-ico="trend_up"></span><i class="sk" style="--w:3.5em"></i></span></div>
              </div>

              <div class="m-grid">
                <div class="m-chat">
                  <div class="m-q">Qaysi yo'nalishda ortda qolyapmiz?</div>
                  <div class="m-a">
                    <div class="m-a-h"><span class="m-av" data-ico="spark"></span><b>ISFT Core</b><i class="sk" style="--w:5em"></i></div>
                    <i class="sk" style="--w:94%"></i><i class="sk" style="--w:72%"></i>
                    <div class="m-hb">
                      <div><i class="sk" style="--w:4.6em"></i><span><i style="--w:86%"></i></span></div>
                      <div><i class="sk" style="--w:3.8em"></i><span><i style="--w:74%"></i></span></div>
                      <div class="low"><i class="sk" style="--w:5.2em"></i><span><i style="--w:41%"></i></span></div>
                    </div>
                    <span class="m-ok"><span data-ico="check"></span>Raqamlar manbadan tekshirildi</span>
                  </div>
                </div>
                <div class="m-chart">
                  <i class="sk" style="--w:58%"></i><i class="sk m-sk-s" style="--w:38%"></i>
                  <div class="m-vb"><i style="--h:62%"></i><i style="--h:78%"></i><i class="low" style="--h:34%"></i><i style="--h:70%"></i><i style="--h:84%"></i><i style="--h:66%"></i></div>
                  <div class="m-vb-x"><i></i><i></i><i></i><i></i><i></i><i></i></div>
                </div>
              </div>
            </div>
          </div>
        </div>

        <div class="m-agent">
          <div class="m-agent-h"><span class="m-agent-ic" data-ico="spark"></span><div><b>AI agent</b><small>Hisobot loyihasi tayyor</small></div></div>
          <i class="sk" style="--w:92%"></i><i class="sk" style="--w:64%"></i>
          <div class="m-agent-a"><span class="m-btn">Tasdiqlash</span><span class="m-btn ghost">Ko'rish</span></div>
        </div>
      </div>
    </div>
  </div>

  <ul class="v3-props">
    <li><span data-ico="server"></span><b>Ma'lumot institutdan chiqmaydi</b></li>
    <li><span data-ico="shield"></span><b>Har bir lavozim o'z ko'lamida</b></li>
    <li><span data-ico="history"></span><b>Har bir so'rov audit jurnalida</b></li>
  </ul>
</aside>`;

window.LOGIN_AFTER = function () {
  const RM = matchMedia("(prefers-reduced-motion: reduce)");

  /* Ro'yxatning eng katta balandligi — ekranda qolgan joyga qarab (sahifa skrollsiz sig'adi) */
  const fit = () => {
    const el = $("#roleList"), inner = el.closest(".v3-inner"), col = el.closest(".v3-form");
    if (!inner || !col.offsetParent) return;
    const cs = getComputedStyle(col), rest = inner.offsetHeight - el.offsetHeight;
    const top = col.getBoundingClientRect().top + scrollY;  /* planshetda ustida ixcham sarlavha bor */
    const avail = innerHeight - top - rest - ["paddingTop", "paddingBottom", "borderTopWidth", "borderBottomWidth"].reduce((t, k) => t + parseFloat(cs[k]), 0);
    el.style.setProperty("--v3-max", Math.max(158, Math.min(312, Math.floor(avail))) + "px");
  };
  addEventListener("resize", fit);

  /* Ro'yxat balandligi tabiiy (3 ta lavozim — 3 qator, bo'sh joy yo'q), lekin o'zgarishi silliq:
     eski balandlikdan yangisiga CSS transition orqali o'tadi, shakl markazda sakramay suriladi. */
  const orig = window.drawRoles;
  window.drawRoles = function () {
    const el = $("#roleList");
    fit();
    const from = el.offsetHeight;
    el.style.height = "";
    orig();
    const to = el.offsetHeight;
    if (!from || RM.matches || Math.abs(to - from) < 2) return;
    el.style.height = from + "px";
    void el.offsetHeight;
    el.style.height = to + "px";
    clearTimeout(el._v3t);
    el._v3t = setTimeout(() => { el.style.height = ""; }, 320);
  };

  /* Klaviatura: ro'yxatda ↑/↓, tablarda ←/→ */
  $("#roleList").addEventListener("keydown", e => {
    if (e.key !== "ArrowDown" && e.key !== "ArrowUp") return;
    const rows = [...$("#roleList").querySelectorAll(".role-row")], i = rows.indexOf(document.activeElement);
    if (i < 0) return;
    e.preventDefault();
    rows[Math.max(0, Math.min(rows.length - 1, i + (e.key === "ArrowDown" ? 1 : -1)))].focus();
  });
  $("#lvlTabs").addEventListener("keydown", e => {
    if (e.key !== "ArrowRight" && e.key !== "ArrowLeft") return;
    const bs = [...$("#lvlTabs").querySelectorAll("button")], i = bs.indexOf(document.activeElement);
    if (i < 0) return;
    e.preventDefault();
    const n = bs[(i + (e.key === "ArrowRight" ? 1 : bs.length - 1)) % bs.length];
    n.focus(); n.click();
  });
};
