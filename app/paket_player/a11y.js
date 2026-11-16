/* ISFT Core — pleyerlar uchun umumiy qulaylik moduli (kurs pleyeri app/kurs_player va «Dars tayyorlash» pleyeri app/paket_player).
 * Global nom: faqat window.ISFTA11y. Tashqi so'rov va tashqi shrift yo'q (CSP: script-src 'self'; style-src 'unsafe-inline' — uslublar shu yerda).
 *
 * 1) (qulaylik paneli «Aa» olib tashlangan — foydalanuvchi talabi; brauzerning o'z sozlamalari: prefers-reduced-motion va hokazo)
 * 2) (ovozli o'qish «Tinglash» olib tashlangan)
 * 3) Imlo (faqat ko'rinish): rasmiy o'zbek lotinida o‘ va g‘ harflari ʻ (U+02BB) bilan yoziladi. Ma'lumotlarda ko'pincha oddiy ' turadi —
 *    sahifadagi MATN tugunlarida "o'zlashtir", "G'oya" → "oʻzlashtir", "Gʻoya" (harf oldidan kelganda). Tutuq belgisi (ma'ruza, a'zo) tegilmaydi.
 *    Atributlar, id, input/textarea qiymatlari, <script>/<style>, <code>/<pre>, MathML, URL/e-pochta o'xshash so'zlar va ingliz egalik shakli (dog's)
 *    o'zgarmaydi; saqlanadigan ma'lumot, xAPI matnlari va javoblarni solishtirish (norm) asl matn bilan ishlaydi. MutationObserver yangi tugunlarni ham tuzatadi.
 */
(function (W, D) {
  'use strict';
  if (W.ISFTA11y) return;
  function mq() { try { return W.matchMedia('(prefers-reduced-motion: reduce)').matches; } catch (e) { return false; } }

  // ------------------------------------------------------------------ imlo: oʻ / gʻ (faqat ko'rinadigan matn tugunlari)
  var UZ_RE = /([oOgG])'(?=\p{L})(?!s(?!\p{L}))/gu, UZ_SKIP = /:\/\/|^www\.|@|\\/, UZ_BAD = { SCRIPT: 1, STYLE: 1, TEXTAREA: 1, INPUT: 1, CODE: 1, PRE: 1, KBD: 1, SAMP: 1, NOSCRIPT: 1, TEMPLATE: 1, MATH: 1, TITLE: 1 };
  function uz(t) {   // satr: "to'liq" → "toʻliq" (so'zma-so'z; URL va e-pochta o'xshash so'zlar tegilmaydi)
    t = String(t == null ? '' : t);
    if (t.indexOf("'") < 0) return t;
    return t.replace(/\S+/g, function (w) { return UZ_SKIP.test(w) ? w : w.replace(UZ_RE, '$1\u02bb'); });
  }
  function uzSkip(n) {
    for (var p = n.parentNode; p && p.nodeType === 1; p = p.parentNode) {
      if (UZ_BAD[String(p.nodeName).toUpperCase()] || /\/Math\/MathML$/.test(p.namespaceURI || '') || p.isContentEditable === true || p.hasAttribute('data-no-uz')) return true;
    }
    return false;
  }
  function uzText(t) {
    var v = t.nodeValue;
    if (!v || v.indexOf("'") < 0 || uzSkip(t)) return;
    var n = uz(v); if (n !== v) t.nodeValue = n;
  }
  function uzWalk(root) {
    if (!root) return;
    if (root.nodeType === 3) { uzText(root); return; }
    if (root.nodeType !== 1 && root.nodeType !== 11) return;
    var w = D.createTreeWalker(root, 4), n;   // 4 = NodeFilter.SHOW_TEXT
    while ((n = w.nextNode())) uzText(n);
  }
  var uzObs = null;
  function uzStart() {
    if (uzObs || !D.body || !W.MutationObserver) return;
    try {
      uzWalk(D.body);
      uzObs = new W.MutationObserver(function (list) {
        for (var i = 0; i < list.length; i++) {
          var m = list[i];
          if (m.type === 'characterData') uzText(m.target);
          else for (var j = 0; j < m.addedNodes.length; j++) uzWalk(m.addedNodes[j]);
        }
      });
      uzObs.observe(D.body, { childList: true, subtree: true, characterData: true });
    } catch (e) { /* eski brauzer (\p{L} yo'q) — matn o'zgarishsiz qoladi */ }
  }
  if (D.body) uzStart(); else D.addEventListener('DOMContentLoaded', uzStart);

  W.ISFTA11y = {
    version: '2.0.0', prefs: function () { return { fs: 100, hc: false, dys: false, rm: false }; },
    reduced: function () { return mq(); },
    uz: uz, uzWalk: uzWalk
  };
})(window, document);
