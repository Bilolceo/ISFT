/* =====================================================================
   Kirish · 1-variant "Markaziy" — brend fonida markazda bitta karta.
   Lavozim — ochiladigan tanlov (combobox): maydon tanlangan lavozimni ko'rsatadi,
   bosilganda ostida panel ochiladi (#roleSearch, #lvlTabs, #roleList — app.js to'ldiradi).
   ===================================================================== */
window.LOGIN_HTML = `
<div class="v1-wrap">
  <header class="v1-brand">
    <span class="v1-logo"><img src="/brand/logo-sm.png" alt="ISFT instituti logotipi" width="400" height="300"></span>
    <div class="v1-brand-t"><b>ISFT instituti</b><small><span class="v1-mark">ISFT <i>Core</i></span><span class="v1-dot" aria-hidden="true">·</span>Boshqaruv tizimi</small></div>
  </header>

  <form class="v1-card" id="loginForm" autocomplete="off" onsubmit="event.preventDefault()">
    <div class="v1-head">
      <h1>Tizimga kirish</h1>
      <p>Lavozimingizni tanlang va parolni kiriting</p>
    </div>

    <div class="v1-field">
      <span class="v1-label" id="v1Lbl">Lavozim</span>
      <div class="v1-combo" id="v1Combo">
        <button type="button" class="v1-pick" id="v1Pick" aria-haspopup="dialog" aria-expanded="false" aria-controls="v1Pop" aria-labelledby="v1Lbl v1PickT">
          <span class="avatar v1-av0" id="v1Av" aria-hidden="true"></span>
          <span class="v1-pick-t" id="v1PickT"><b id="v1Role">Yuklanmoqda…</b><small id="v1Person">&nbsp;</small></span>
          <span class="v1-chev" aria-hidden="true"><svg class="i" viewBox="0 0 24 24" width="18" height="18"><path d="m6 9 6 6 6-6"/></svg></span>
        </button>
        <div class="v1-pop" id="v1Pop" role="dialog" aria-label="Lavozimni tanlash">
          <label class="v1-search"><span data-ico="search"></span><input id="roleSearch" type="search" placeholder="Lavozim yoki ism bo'yicha qidirish" aria-label="Lavozim yoki ism bo'yicha qidirish" autocomplete="off" spellcheck="false"><kbd class="v1-kbd">Esc</kbd></label>
          <div class="v1-tabs" id="lvlTabs" role="tablist" aria-label="Lavozim guruhi"></div>
          <div id="roleList" class="v1-list" role="listbox" aria-label="Lavozimlar"></div>
        </div>
      </div>
    </div>

    <div class="v1-field">
      <label class="v1-label" for="password">Parol</label>
      <div class="v1-pw" id="pwWrap">
        <span class="v1-pw-ic" data-ico="lock" aria-hidden="true"></span>
        <input id="password" type="password" autocomplete="current-password" placeholder="Parolingizni kiriting" spellcheck="false" autocapitalize="off" aria-describedby="v1PwHint">
        <button type="button" class="v1-eye" id="pwEye" aria-label="Parolni ko'rsatish" aria-pressed="false" aria-controls="password"><span class="v1-eye-ic" data-ico="eye"></span></button>
      </div>
      <p class="v1-hint" id="v1PwHint"${window.ISFT_HIDE_DEMO_HINT ? ' hidden style="display:none"' : ""}><span data-ico="info"></span><span>Sinov rejimi: parol <b>Isft2026</b></span></p>
    </div>

    <button id="loginBtn" type="button" class="v1-btn" disabled><span id="loginTxt">Kirish</span><span class="v1-btn-ic" data-ico="arrow"></span></button>
  </form>

  <p class="v1-foot">Haqiqiy tizimda kirish OneID yoki HEMIS orqali · ma'lumotlar sun'iy (demo)</p>
</div>`;

window.LOGIN_AFTER = function () {
  const combo = $("#v1Combo"); if (!combo) return;
  const form = $("#loginForm"), pick = $("#v1Pick"), pop = $("#v1Pop"), list = $("#roleList"), search = $("#roleSearch"), tabs = $("#lvlTabs");
  const isOpen = () => combo.classList.contains("open");
  const refade = () => { if (typeof list.onscroll === "function") list.onscroll(); };
  const rows = () => [...list.querySelectorAll(".role-row")];
  const fine = () => window.matchMedia("(pointer:fine)").matches;

  /* maydon: tanlangan lavozim (avatar + lavozim + ism) */
  function paint() {
    const u = USERS.find(x => x.id === selUser), av = $("#v1Av");
    pick.classList.toggle("empty", !u);
    if (!u) { av.className = "avatar v1-av0"; av.innerHTML = ico("user", 18); $("#v1Role").textContent = "Lavozimni tanlang"; $("#v1Person").textContent = "Ro'yxat ochiladi"; pick.removeAttribute("title"); return; }
    setAv(av, u, "avatar");
    $("#v1Role").textContent = u.role; $("#v1Person").textContent = personOf(u);
    pick.title = u.role + " — " + personOf(u);
  }

  /* panel ekrandan (va pastki almashtirgichdan) chiqib ketmasin */
  function fit() {
    const r = pick.getBoundingClientRect(), vh = window.innerHeight;
    const below = vh - r.bottom - 8 - (vh < 560 ? 12 : 76);
    pop.style.setProperty("--v1-max", Math.max(240, Math.floor(below)) + "px");
  }

  const orig = window.drawRoles;
  window.drawRoles = function () { orig(); paint(); if (isOpen()) { fit(); refade(); } };

  function open() {
    if (isOpen()) return;
    combo.classList.add("open"); pick.setAttribute("aria-expanded", "true");
    fit();
    const s = list.querySelector(".sel");
    if (s) list.scrollTop = Math.max(0, s.offsetTop - (list.clientHeight - s.offsetHeight) / 2);
    refade();
    if (fine()) search.focus({preventScroll: true});
  }
  function close(refocus) {
    if (!isOpen()) return;
    combo.classList.remove("open"); pick.setAttribute("aria-expanded", "false");
    /* keyingi ochilishda tanlangan lavozim guruhi ko'rinsin */
    const u = USERS.find(x => x.id === selUser);
    if (search.value || (u && u.level !== LVL)) { search.value = ""; if (u) LVL = u.level; drawRoles(); }
    if (refocus) pick.focus();
  }

  pick.addEventListener("click", () => (isOpen() ? close(false) : open()));
  pick.addEventListener("keydown", e => {
    if ((e.key === "ArrowDown" || e.key === "ArrowUp") && !isOpen()) { e.preventDefault(); e.stopPropagation(); open(); }
    else if (e.key.length === 1 && e.key !== " " && !e.ctrlKey && !e.metaKey && !e.altKey) { /* yozishni boshlasa — qidiruv */
      e.preventDefault(); open(); search.focus(); search.value = e.key; drawRoles();
    }
  });

  /* qatordan tanlash → panel yopiladi (app.js qatorni avval belgilaydi). Ikki marta bosish pastdagi tugmaga tushmasin. */
  let guard = 0;
  list.addEventListener("click", e => { if (e.target.closest(".role-row")) { guard = Date.now() + 400; close(true); } });
  ["mousedown", "click", "dblclick"].forEach(t => form.addEventListener(t, e => {
    if (Date.now() < guard && !combo.contains(e.target)) { e.preventDefault(); e.stopPropagation(); }
  }, true));

  search.addEventListener("keydown", e => {
    if (e.key === "Enter") {
      e.preventDefault();
      const r = search.value.trim() && rows()[0];
      if (r) { r.click(); $("#password")?.focus(); } else close(true);
    }
  });

  combo.addEventListener("keydown", e => {
    if (!isOpen()) return;
    if (e.key === "Escape") { e.preventDefault(); e.stopPropagation(); close(true); return; }
    const rs = rows(), i = rs.indexOf(document.activeElement), inTabs = tabs.contains(document.activeElement);
    if (e.key === "ArrowDown") { e.preventDefault(); (i < 0 ? rs[0] : rs[Math.min(rs.length - 1, i + 1)])?.focus(); }
    else if (e.key === "ArrowUp" && e.target !== search) { e.preventDefault(); if (i <= 0) search.focus(); else rs[i - 1].focus(); }
    else if ((e.key === "Home" || e.key === "End") && i >= 0) { e.preventDefault(); rs[e.key === "Home" ? 0 : rs.length - 1]?.focus(); }
    else if ((e.key === "ArrowLeft" || e.key === "ArrowRight") && inTabs) {
      e.preventDefault();
      const bs = [...tabs.querySelectorAll("button")], j = bs.indexOf(document.activeElement);
      const n = bs[(j + (e.key === "ArrowRight" ? 1 : bs.length - 1)) % bs.length]; n.focus(); n.click();
    }
  });
  combo.addEventListener("focusout", e => { if (isOpen() && e.relatedTarget && !combo.contains(e.relatedTarget)) close(false); });
  document.addEventListener("pointerdown", e => { if (isOpen() && !combo.contains(e.target)) close(false); }, true);
  window.addEventListener("resize", () => { if (isOpen()) { fit(); refade(); } });

  /* parol maydoni: o'ramning bo'sh joyiga (qulf belgisi) bosilsa ham input fokus oladi */
  const pw = $("#pwWrap"), pwIn = $("#password");
  if (pw && pwIn) pw.addEventListener("mousedown", e => { if (e.target !== pwIn && !e.target.closest("#pwEye")) { e.preventDefault(); pwIn.focus(); } });
};
