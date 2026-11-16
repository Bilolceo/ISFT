/* Brauzer «Orqaga» / «Oldinga» tugmalari butun ilova uchun (SPA tarixi). Barcha modullardan KEYIN yuklanadi (index.html oxirida).
   - go(v) har safar yangi bo'limga o'tganda history.pushState({isftView: v}) — «Orqaga» oldingi bo'limga qaytaradi (ilovadan chiqarib yubormaydi).
   - popstate: oldingi bo'lim go() orqali qayta ochiladi; «Dars tayyorlash → Fanlar» daraxti holati URL hash'dan (#fanlar=kurs/yo'nalish/fan) tiklanadi (dars.js).
   - Saqlanmagan tahrir (taqdimot.js tqBeforeLeave) bekor qilsa — tarix joyiga qaytariladi (URL va holat mos qoladi).
   - history.replaceState boshqa modullarda state=null bilan chaqirilsa ham {isftView} saqlanadi. */
(function (W, D) {
  "use strict";
  if (W.__isftNavHistory || typeof W.go !== "function" || !W.history || !W.history.pushState) return;
  W.__isftNavHistory = true;
  var cur = null, popping = false, goInner = W.go;

  // boshqa modullar replaceState(null, …) desa ham joriy yozuvning bo'lim belgisi yo'qolmasin
  var rs = W.history.replaceState.bind(W.history);
  W.history.replaceState = function (state, title, url) {
    var keep = W.history.state && W.history.state.isftView ? { isftView: W.history.state.isftView } : null;
    var st = state && typeof state === "object" ? Object.assign({}, keep || {}, state) : (keep || state);
    return url === undefined ? rs(st, title) : rs(st, title, url);
  };

  function shown(v) { var el = D.getElementById("v-" + v); return !el || !el.classList.contains("hidden"); }
  function base() { return W.location.pathname + W.location.search; }

  W.go = function (v) {
    var r = goInner.apply(this, arguments);
    try {
      if (popping || !v || !shown(v)) return r;            // bekor qilingan o'tish (tahrir tasdig'i) yoki tarixdan qaytish — yozilmaydi
      if (cur === null) { rs(Object.assign({}, W.history.state || {}, { isftView: v }), "", W.location.href); cur = v; }
      else if (v !== cur) { W.history.pushState({ isftView: v }, "", base()); cur = v; }
    } catch (e) { /* tarix mavjud emas (sandbox) — navigatsiya o'zi ishlaydi */ }
    return r;
  };

  W.addEventListener("popstate", function (e) {
    var v = e.state && e.state.isftView;
    if (!v || typeof ME === "undefined" || !ME) return;            // kirmagan yoki begona yozuv — tegmaymiz
    var prev = cur; popping = true;
    try {
      if (v === "paket" && typeof dsHashLoad === "function") {
        if (typeof DS === "object") Object.assign(DS, { cid: 0, kurs: 0, dir: "", q: "", offset: 0, data: null, fromHash: false });
        dsHashLoad();                                                // #fanlar=… bo'lsa daraxt holati tiklanadi, bo'lmasa — boshiga
      }
      W.go.call(W, v);   // eng tashqi qatlam (modGate) orqali; popping=true — qayta yozilmaydi
      if (!shown(v)) { W.history.pushState({ isftView: prev }, "", base()); return; }   // go() ruxsat bermadi (masalan, saqlanmagan tahrir) — joyiga qaytaramiz
      cur = v;
    } catch (err) { /* ruxsat yo'q va h.k. — go() o'zi xabar beradi */ }
    finally { popping = false; }
  });
})(window, document);
