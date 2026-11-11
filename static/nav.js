/* =====================================================================
   Yon menyu: guruhlar va ixcham rejim (IA)
   - "Sozlamalar va xavfsizlik" guruhi yig'iladi (standart: yig'ilgan), holati localStorage'da.
   - Ayrim lavozimlar uchun guruhdagi kundalik bo'lim yuqoriga chiqariladi (masalan, xo'jalik → Auditoriyalar).
   - Ixcham rejim (faqat ikonkalar, ~76px): brend qatoridagi ☰ tugma yoki "[" tugmasi; holati localStorage'da.
     Saqlangan tanlov bo'lmasa, 981–1200px kenglikda avtomatik ixcham. 980px dan tor ekranda — eski mobil menyu.
   app.js yordamchilaridan foydalanadi: $, ico, ICONS, ME.
   ===================================================================== */
(function () {
  const nav = document.getElementById("nav"), app = document.getElementById("app"), cfg = document.getElementById("navCfg"), menuBtn = document.getElementById("menuBtn");
  if (!nav || !app) return;
  const store = {
    get(k) { try { return localStorage.getItem(k); } catch (e) { return null; } },
    set(k, v) { try { localStorage.setItem(k, v); } catch (e) {} },
  };
  if (!ICONS.gear) ICONS.gear = '<path d="M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z"/><circle cx="12" cy="12" r="3"/>';
  if (!ICONS.chev) ICONS.chev = '<path d="m6 9 6 6 6-6"/>';
  /* «Ilm va xalqaro» guruhi ikonkasi: ilmiy.js keyinroq yuklanadi, boot() esa undan oldin navGroup() ni chaqirishi mumkin */
  if (!ICONS.flask) ICONS.flask = '<path d="M9 3h6M10 3v6L4.5 18.5A2 2 0 0 0 6.2 21h11.6a2 2 0 0 0 1.7-2.5L14 9V3"/><path d="M7 15h10"/>';

  /* ---------- 1–2) Guruhlar, tezkor (sevimlilar) va lavozimga ko'ra yorliqlar ----------
     Menyu bandlari ma'noli guruhlarga bo'linadi. 12 tadan ko'p band ko'radigan lavozimlarda guruhlar yig'iladi
     (holati localStorage'da; joriy sahifa guruhi doim ochiq), kamroq bandda — tekis ro'yxat (sarlavhasiz).
     «Tezkor» — foydalanuvchi pin bilan yuqoriga chiqargan bandlar (localStorage). boot() oxirida navGroup() chaqiriladi. */
  if (cfg) cfg.remove();
  nav.querySelectorAll(".nav-h").forEach(h => h.remove());
  nav.querySelectorAll("a[data-g]").forEach(a => a.removeAttribute("data-g"));
  if (!ICONS.pin2) ICONS.pin2 = '<path d="M12 17v5"/><path d="M9 10.76a2 2 0 0 1-1.11 1.79l-1.78.9A2 2 0 0 0 5 15.24V16a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1v-.76a2 2 0 0 0-1.11-1.79l-1.78-.9A2 2 0 0 1 15 10.76V7a1 1 0 0 1 1-1 2 2 0 0 0 0-4H8a2 2 0 0 0 0 4 1 1 0 0 1 1 1z"/>';
  const GROUPS = [["tez", "Tezkor", "pin2"], ["ish", "Ish stoli", "dashboard"], ["talaba", "Talabalar va o'quv", "cap"], ["ilm", "Ilm va xalqaro", "flask"],
                  ["moliya", "Moliya va xodimlar", "money"], ["kampus", "Kampus", "wrench"], ["hujjat", "Hujjatlar", "folder"], ["tizim", "Tizim", "gear"]];
  const VG = {panel: "ish", mywork: "ish", chat: "ish", agents: "ish", tasks: "ish",
              ops: "talaba", flows: "talaba", masofaviy: "talaba", testbank: "talaba", paket: "talaba", reyting: "talaba", syllabus: "talaba", amaliyot: "talaba", taqdimot: "talaba", tekshiruv: "talaba",
              ilmiy: "ilm", xalqaro: "ilm", moliya: "moliya", kadrlar: "moliya", staffabs: "moliya",
              yoshlar: "kampus", service: "kampus", spaces: "kampus", cams: "kampus",
              kiruvchi: "hujjat", qabul: "talaba", rejalar: "ish", portal: "hujjat", documents: "hujjat", orders: "hujjat", reports: "hujjat", docs: "hujjat", rbac: "tizim", audit: "tizim", accounts: "tizim"};
  /* lavozimga xos nom: bitta sahifa turli lavozimda turli ish (xarid — so'rovlar, xo'jalik — nosozliklar, yoshlar — murojaatlar) */
  const LBL = {service: {xarid: "Xarid so'rovlari", xojalik: "Nosozliklar", it_head: "Nosozliklar", it_staff: "Nosozliklar", manaviyat: "Murojaatlar", komendant: "Murojaatlar"}};
  const PIN_KEY = "isft-nav-pins", G_KEY = "isft-nav-groups";
  const jget = (k, d) => { try { return JSON.parse(store.get(k) || "") || d; } catch (e) { return d; } };
  const label = a => { if (!a.dataset.lbl0) a.dataset.lbl0 = [...a.childNodes].filter(n => n.nodeType === 3).map(n => n.textContent).join("").trim(); return a.dataset.lbl0; };
  function setLabel(a, t) {
    const tn = [...a.childNodes].filter(n => n.nodeType === 3);
    tn.forEach((n, i) => { n.textContent = i ? "" : t; });
    if (!tn.length) a.insertBefore(document.createTextNode(t), a.querySelector(".nb, .nav-pin"));
    a.dataset.lbl = t;
  }
  let ROLE = "", OPEN = {};
  function groupOf(a) { return a.dataset.pinned ? "tez" : (VG[a.dataset.v] || "ish"); }
  function applyOpen() {
    const many = nav.classList.contains("nav-many");
    nav.querySelectorAll("a[data-v]").forEach(a => a.classList.toggle("g-closed", many && OPEN[a.dataset.grp] === false));
    nav.querySelectorAll(".nav-g").forEach(h => {
      const k = h.dataset.g, open = !many || OPEN[k] !== false;
      h.setAttribute("aria-expanded", String(open)); h.classList.toggle("closed", !open);
      const dot = [...nav.querySelectorAll(`a[data-grp="${k}"]:not(.hidden) .nb`)].length;
      h.classList.toggle("has-nb", !open && dot > 0);
    });
  }
  window.navGroup = function (role) {
    ROLE = role || ROLE;
    const anchors = [...nav.querySelectorAll("a[data-v]")];
    const pins = jget(PIN_KEY, []);
    anchors.forEach(a => {
      label(a);
      /* ikonkasi keyin yuklangan modulda aniqlangan band (app.js hydrateIcons vaqtida ICONS[...] hali yo'q edi) — bo'sh svg to'ldiriladi */
      const sv = a.querySelector(":scope > svg"); if (sv && !sv.innerHTML.trim() && ICONS[a.dataset.i]) sv.innerHTML = ICONS[a.dataset.i];
      const t = (LBL[a.dataset.v] || {})[ROLE]; setLabel(a, t || a.dataset.lbl0);
      if (!a.querySelector(".nav-pin")) {
        const p = document.createElement("span"); p.className = "nav-pin"; p.setAttribute("role", "button"); p.tabIndex = -1;
        p.innerHTML = ico("pin2", 13);
        p.addEventListener("click", e => {
          e.preventDefault(); e.stopPropagation();
          const v = a.dataset.v, cur = jget(PIN_KEY, []);
          store.set(PIN_KEY, JSON.stringify(cur.includes(v) ? cur.filter(x => x !== v) : [...cur, v]));
          navGroup(ROLE);
        });
        a.appendChild(p);
      }
      const pinned = pins.includes(a.dataset.v) && !a.classList.contains("hidden");
      a.toggleAttribute("data-pinned", pinned);
      a.querySelector(".nav-pin").title = pinned ? "Tezkordan olib tashlash" : "Tezkor bo'limga qo'shish (yuqoriga)";
      a.dataset.grp = groupOf(a);
    });
    nav.querySelectorAll(".nav-g").forEach(h => h.remove());
    const vis = anchors.filter(a => !a.classList.contains("hidden"));
    const many = vis.length > 12;
    nav.classList.toggle("nav-many", many);
    const saved = jget(G_KEY, {})[ROLE] || {};
    /* standart: Tezkor, Ish stoli va lavozimning eng ko'p bandli (asosiy) guruhi ochiq, qolganlari yig'iq */
    const cnt = {}; vis.forEach(a => { if (!["tez", "ish"].includes(a.dataset.grp)) cnt[a.dataset.grp] = (cnt[a.dataset.grp] || 0) + 1; });
    const PRI = ["oquv", "talaba", "talabalar"];   /* teng bo'lsa — talabalar/o'quv guruhi ustun */
    const main = Object.entries(cnt).sort((x, y) => (y[1] - x[1]) || (PRI.some(p => y[0].includes(p)) - PRI.some(p => x[0].includes(p))))[0]?.[0];
    OPEN = {};
    GROUPS.forEach(([k]) => { OPEN[k] = k in saved ? saved[k] : (["tez", "ish", main].includes(k)); });
    const cur = nav.querySelector("a.on"); if (cur) OPEN[cur.dataset.grp] = true;
    GROUPS.forEach(([k, name, ic]) => {
      const items = anchors.filter(a => a.dataset.grp === k);
      const shown = items.filter(a => !a.classList.contains("hidden"));
      let h = null;
      if (shown.length && (many || (k === "tez") || (pins.length && k === "ish" && vis.some(a => a.dataset.pinned)))) {
        if (many && k !== "tez") {
          h = document.createElement("button"); h.type = "button"; h.className = "nav-h nav-tg nav-g"; h.dataset.g = k; h.dataset.tip = name;
          h.innerHTML = `${ico(ic, 15)}<span class="nav-tg-l">${name}</span><span class="nav-gn">${shown.length}</span><span class="nav-chev">${ico("chev", 14)}</span>`;
          h.onclick = () => {
            OPEN[k] = !(OPEN[k] !== false);
            const all = jget(G_KEY, {}); all[ROLE] = {...(all[ROLE] || {}), [k]: OPEN[k]}; store.set(G_KEY, JSON.stringify(all));
            applyOpen();
          };
        } else {
          h = document.createElement("div"); h.className = "nav-h nav-g nav-g-flat"; h.dataset.g = k;
          h.textContent = k === "tez" ? name : (many ? name : "Bo'limlar");
        }
        nav.appendChild(h);
      }
      items.forEach(a => nav.appendChild(a));
    });
    applyOpen();
  };
  /* joriy sahifa guruhi doim ochiq (saqlanmaydi) */
  window.navOpenFor = function (v) {
    const a = nav.querySelector(`a[data-v="${v}"]`); if (!a || !nav.classList.contains("nav-many")) return;
    if (OPEN[a.dataset.grp] === false) { OPEN[a.dataset.grp] = true; applyOpen(); }
  };
  /* yig'iq guruhdagi bandga raqamli belgi qo'shilsa — sarlavhada nuqta */
  let nbT; new MutationObserver(() => { clearTimeout(nbT); nbT = setTimeout(applyOpen, 80); }).observe(nav, {childList: true, subtree: true});
  /* eski chaqiruv (boot() boshida) — endi tartibni navGroup() quradi */
  window.navLayout = function (role) { ROLE = role; };

  /* ---------- 3) ixcham rejim (faqat ikonkalar) ----------
     #menuBtn — yon menyuning brend qatorida ("ISFT Core" yonida): kompyuterda menyuni yig'adi/yoyadi,
     mobil tortma menyuda uni yopadi. #menuOpen — yuqori paneldagi ochuvchi, faqat mobil ekranda ko'rinadi. */
  const RAIL_KEY = "isft-nav-rail", MOBILE = 980, menuOpen = document.getElementById("menuOpen");
  const isMobile = () => window.innerWidth <= MOBILE;
  let lastIco = "";
  function railSync() {
    if (!menuBtn) return;
    const mob = isMobile(), open = app.classList.contains("nav-open"), rail = app.classList.contains("rail");
    const t = mob ? "Menyuni yopish" : rail ? "Menyuni yoyish" : "Menyuni yig'ish";
    menuBtn.setAttribute("aria-label", t);
    /* ixcham rejimda nom menyuning o'z ko'rsatkichida (title bilan ikki marta chiqmasin) */
    if (rail && !mob) { menuBtn.removeAttribute("title"); menuBtn.dataset.tip = `${t} ( [ )`; }
    else { menuBtn.title = mob ? t : `${t} ( [ )`; delete menuBtn.dataset.tip; }
    menuBtn.setAttribute("aria-expanded", String(mob ? open : !rail));
    const ic = mob ? "x" : "menu";
    if (ic !== lastIco) { menuBtn.innerHTML = ico(ic, 18); lastIco = ic; }
    if (menuOpen) menuOpen.setAttribute("aria-expanded", String(mob && open));
  }
  function railAuto() {
    const saved = store.get(RAIL_KEY);
    const rail = saved === "1" || (saved === null && window.innerWidth > MOBILE && window.innerWidth <= 1200);
    app.classList.toggle("rail", rail);
    if (!isMobile()) app.classList.remove("nav-open");
    railSync();
  }
  let railT;
  const RAIL_MS = 200;   /* style.css: #app grid-template-columns o'tishi (.18s) bilan mos */
  function railToggle() {
    const rail = !app.classList.contains("rail") && !app.classList.contains("rail-closing");
    store.set(RAIL_KEY, rail ? "1" : "0"); tipHide(); clearTimeout(railT);
    /* Animatsiya paytida tarkib qayta joylashmaydi (aks holda yozuvlar "bijirlab" sinadi):
       • yig'ish: avval kenglik 72px gacha kichrayadi, to'liq menyu chetda kesiladi (rail-closing), keyin rels ko'rinishi yoqiladi;
       • yoyish: rels ko'rinishi darhol o'chadi, to'liq menyu kenglik bilan birga chetdan ochiladi.
       Ikkala holatda ham yozuvlar bir qatorda qoladi (rail-anim: nowrap) — ikonkalar chap chetda deyarli bir joyda turadi. */
    app.classList.add("rail-anim");
    if (rail) {
      app.classList.add("rail-closing");
      railT = setTimeout(() => { app.classList.remove("rail-closing", "rail-anim"); app.classList.add("rail"); railSync(); }, RAIL_MS);
    } else {
      app.classList.remove("rail", "rail-closing"); railSync();
      railT = setTimeout(() => app.classList.remove("rail-anim"), RAIL_MS + 60);
    }
  }
  function drawer(open) {
    app.classList.toggle("nav-open", open); railSync();
    if (open && menuBtn) menuBtn.focus({preventScroll: true});
  }
  railAuto();
  let rz; window.addEventListener("resize", () => { clearTimeout(rz); rz = setTimeout(railAuto, 120); });
  if (menuBtn) menuBtn.onclick = () => { if (isMobile()) drawer(false); else railToggle(); };
  if (menuOpen) menuOpen.onclick = () => drawer(!app.classList.contains("nav-open"));
  /* tortma menyu boshqa joydan yopilganda ham (fon, bo'lim tanlash) aria-expanded to'g'ri qolsin */
  let wasOpen = app.classList.contains("nav-open");
  new MutationObserver(() => {
    const open = app.classList.contains("nav-open");
    /* yopilganda fokus ekrandan tashqaridagi menyuda qolib ketmasin */
    if (wasOpen && !open && menuOpen && isMobile() && document.activeElement && document.getElementById("side").contains(document.activeElement)) menuOpen.focus({preventScroll: true});
    wasOpen = open; railSync();
  }).observe(app, {attributes: true, attributeFilter: ["class"]});
  document.addEventListener("keydown", e => {
    if (e.key === "Escape" && isMobile() && app.classList.contains("nav-open")) { drawer(false); return; }
    if (e.key !== "[" || e.ctrlKey || e.metaKey || e.altKey || isMobile() || app.classList.contains("hidden")) return;
    const t = e.target; if (t && (t.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName))) return;
    e.preventDefault(); railToggle();
  });

  /* ---------- 4) ixcham rejimda nom ko'rsatkichi (tooltip) ---------- */
  const tip = document.createElement("div");
  tip.className = "nav-tip"; tip.id = "navTip"; tip.setAttribute("role", "tooltip"); document.body.appendChild(tip);
  const TIP_SEL = "#nav a, #nav .nav-g, #menuBtn, .side-foot .me";
  function tipText(el) {
    if (el.dataset.tip) return el.dataset.tip;
    if (el.classList.contains("me")) { const n = el.querySelector("b"), s = el.querySelector("small"); return [n && n.textContent, s && s.textContent].filter(Boolean).join(" · "); }
    const c = el.cloneNode(true); c.querySelectorAll(".nb, svg, .nav-pin, .nav-gn").forEach(x => x.remove());
    const n = el.querySelector(".nb");
    return c.textContent.trim() + (n ? ` · ${n.textContent}` : "");
  }
  function tipShow(el) {
    if (!app.classList.contains("rail") || isMobile()) return;
    const t = tipText(el); if (!t) return;
    tip.textContent = t;
    const r = el.getBoundingClientRect();
    tip.style.left = `${Math.round(r.right + 10)}px`; tip.style.top = `${Math.round(r.top + r.height / 2)}px`;
    tip.classList.add("on");
  }
  function tipHide() { tip.classList.remove("on"); }
  const side = document.getElementById("side");
  side.addEventListener("mouseover", e => { const el = e.target.closest(TIP_SEL); if (el) tipShow(el); });
  side.addEventListener("mouseout", e => { const el = e.target.closest(TIP_SEL); if (el && !el.contains(e.relatedTarget)) tipHide(); });
  side.addEventListener("focusin", e => { const el = e.target.closest(TIP_SEL); if (el) tipShow(el); });
  side.addEventListener("focusout", tipHide);
  side.addEventListener("click", tipHide);
  nav.addEventListener("scroll", tipHide, {passive: true});
})();

/* =====================================================================
   Sahifa sarlavhasi ostidagi "manba va yangilanish" qatori (IA).
   Faqat backend bergan qiymatlar ishlatiladi; demo bazadagi ma'lumot — "sinov ma'lumotlari".
   ===================================================================== */
/* ISO vaqt → "bugun 08:00" / "kecha 08:00" / "05.11.2026 08:00" (ME.today ga nisbatan) */
function whenTxt(iso) {
  if (!iso) return "";
  const d = String(iso).slice(0, 10), t = String(iso).slice(11, 16);
  const today = (typeof ME !== "undefined" && ME && ME.today) || new Date().toISOString().slice(0, 10);
  const y = new Date(new Date(today + "T12:00:00") - 864e5).toISOString().slice(0, 10);
  const day = d === today ? "bugun" : d === y ? "kecha" : d.split("-").reverse().join(".");
  return t ? `${day} ${t}` : day;
}
const pgSrc = (html, icon = "server") => `<span class="pg-src">${ico(icon, 14)}<span>${html}</span></span>`;
/* HEMIS/buxgalteriya sinxronlash vaqti — /api/dashboard KPI'laridagi "updated" (backend: services._sync_at) */
let SYNC_INFO = null;
async function syncInfo() {
  if (SYNC_INFO) return SYNC_INFO;
  const d = (typeof DASH !== "undefined" && DASH && DASH.kpis) ? DASH : await J("/api/dashboard");
  const ks = (d.kpis || []).filter(k => k.updated && /^(HEMIS|Buxgalteriya)/i.test(k.source || ""));
  const upd = ks.map(k => k.updated).sort().pop() || null;
  return (SYNC_INFO = {updated: upd});
}

/* =====================================================================
   Ilova qobig'i (app shell): ilova ochiq bo'lganda hujjat aylanmaydi, faqat #app > .shell aylanadi
   (style.css). Eski kod window.scrollTo / scrollY bilan ishlaydi (app.js go(), qaror sahifasini
   jim yangilash, portal.js "orqaga") — ularni shu konteynerga yo'naltiramiz. Kirish sahifasida
   (#app yashirin) brauzerning asl xatti-harakati saqlanadi.
   ===================================================================== */
(function () {
  const app = document.getElementById("app"), shell = app && app.querySelector(":scope > .shell");
  if (!shell || window.__shellScroll) return;
  window.__shellScroll = shell;
  const on = () => !app.classList.contains("hidden") && getComputedStyle(shell).overflowY !== "visible";
  const nativeTo = window.scrollTo.bind(window), nativeBy = window.scrollBy.bind(window);
  window.scrollTo = window.scroll = function (...a) { return on() ? shell.scrollTo(...a) : nativeTo(...a); };
  window.scrollBy = function (...a) { return on() ? shell.scrollBy(...a) : nativeBy(...a); };
  const desc = k => { for (let o = window; o; o = Object.getPrototypeOf(o)) { const d = Object.getOwnPropertyDescriptor(o, k); if (d) return d; } return null; };
  ["scrollY", "pageYOffset"].forEach(k => {
    const d = desc(k); if (!d || !d.get || d.configurable === false) return;
    try { Object.defineProperty(window, k, {configurable: true, enumerable: d.enumerable, get() { return on() ? shell.scrollTop : d.get.call(window); }}); } catch (e) {}
  });
})();
