/* ISFT Core — pleyerlar uchun umumiy qulaylik moduli (kurs pleyeri app/kurs_player va «Dars tayyorlash» pleyeri app/paket_player).
 * Global nom: faqat window.ISFTA11y. Tashqi so'rov va tashqi shrift yo'q (CSP: script-src 'self'; style-src 'unsafe-inline' — uslublar shu yerda).
 *
 * 1) Qulaylik paneli («Aa» tugmasi): matn o'lchami (A− / A+, 90–160 %), yuqori kontrast, o'qish uchun qulay shrift (tizim shriftlari:
 *    Verdana / Tahoma …, keng harf va so'z oralig'i), harakatni kamaytirish (prefers-reduced-motion bilan birga). Sozlamalar brauzerda
 *    (localStorage 'isft-a11y'); har murojaat try/catch — sandbox (opaque origin) va maxfiy oynada xatosiz, faqat eslab qolinmaydi.
 *    <html> ga: --a11y-fs (1 = 100 %), klasslar a11y-hc / a11y-dys / a11y-rm.
 * 2) Ovozli o'qish («Tinglash»): brauzerning Web Speech API'si (speechSynthesis) — tashqi xizmatsiz. Ovoz: uz-UZ → uz-* → ru-RU → ru-* →
 *    standart; ovoz yoki API bo'lmasa — tushunarli xabar. O'qilayotgan blok ajratib ko'rsatiladi (.reading). Matn gaplarga bo'lib o'qiladi
 *    (Chrome uzun matnni yarmida to'xtatadi).
 */
(function (W, D) {
  'use strict';
  if (W.ISFTA11y) return;
  var KEY = 'isft-a11y', FS = [90, 100, 112, 125, 140, 160];
  var P = { fs: 100, hc: false, dys: false, rm: false };
  var CSS = [
    'html{font-size:calc(100% * var(--a11y-fs,1))}',
    '.a11y-b{display:inline-flex;align-items:center;justify-content:center;min-height:44px;min-width:44px;padding:0 10px;border:1px solid var(--line);border-radius:10px;background:var(--surface);color:var(--ink);font-weight:800;font-size:.95rem;cursor:pointer;flex:none}',
    '.a11y-b[aria-expanded="true"]{border-color:var(--brand);color:var(--brand)}',
    '.a11y-p{position:fixed;z-index:80;top:66px;right:12px;width:min(330px,calc(100vw - 24px));background:var(--surface);color:var(--ink);border:1px solid var(--line);border-radius:14px;box-shadow:0 10px 40px rgba(0,0,0,.18);padding:14px}',
    '.a11y-p h2{font-size:1rem;margin:0 0 10px}',
    '.a11y-row{display:flex;align-items:center;gap:8px;margin:0 0 10px}',
    '.a11y-row .a11y-v{min-width:56px;text-align:center;font-weight:800}',
    '.a11y-s{min-height:44px;min-width:44px;border:1px solid var(--line);border-radius:10px;background:var(--surface-2);color:var(--ink);font-weight:800;cursor:pointer}',
    '.a11y-s:disabled{opacity:.4;cursor:not-allowed}',
    '.a11y-t{display:flex;width:100%;align-items:center;justify-content:space-between;gap:10px;min-height:44px;border:1px solid var(--line);border-radius:10px;background:var(--surface);color:var(--ink);padding:8px 12px;margin:0 0 8px;cursor:pointer;text-align:left;font-weight:600}',
    '.a11y-t::after{content:"";flex:none;width:38px;height:22px;border-radius:99px;background:var(--line);box-shadow:inset -16px 0 0 2px var(--surface);transition:box-shadow .15s}',
    '.a11y-t[aria-pressed="true"]{border-color:var(--brand)}',
    '.a11y-t[aria-pressed="true"]::after{background:var(--brand);box-shadow:inset 16px 0 0 2px var(--surface)}',
    '.a11y-note{font-size:.8rem;color:var(--muted);margin:6px 0 0}',
    '.tts{display:flex;flex-wrap:wrap;align-items:center;gap:8px;margin-top:8px}',
    '.tts-b{display:inline-flex;align-items:center;gap:6px;min-height:36px;padding:4px 12px;border:1px solid var(--line);border-radius:99px;background:var(--surface);color:var(--ink-2);font-size:.82rem;font-weight:700;cursor:pointer}',
    '.tts-b:hover{border-color:var(--brand-lite);color:var(--brand)}',
    '.tts-b[aria-pressed="true"]{background:var(--brand);border-color:var(--brand);color:#fff}',
    '.tts-m{font-size:.8rem;color:var(--muted)}',
    '.reading{outline:3px solid var(--brand-lite);outline-offset:6px;border-radius:8px;background:var(--brand-soft)}',
    /* yuqori kontrast */
    'html.a11y-hc{--bg:#fff;--surface:#fff;--surface-2:#fff;--ink:#000;--ink-2:#000;--muted:#1a1a1a;--line:#000;--brand:#000;--brand-ink:#000;--brand-soft:#ffef99;--brand-soft-l:#ffef99;--brand-lite:#000;--link:#0000c8;--focus:#c80000;--good:#005a1f;--bad:#a00000;--shadow:none}',
    '@media (prefers-color-scheme:dark){html.a11y-hc{--bg:#000;--surface:#000;--surface-2:#000;--ink:#fff;--ink-2:#fff;--muted:#e6e6e6;--line:#fff;--brand:#000;--brand-ink:#000;--brand-soft:#333000;--brand-lite:#ffd400;--link:#ffd400;--focus:#ffd400;--good:#7dff9a;--bad:#ff8080}}',
    'html.a11y-hc a{text-decoration:underline!important;text-underline-offset:3px}',
    'html.a11y-hc .btn,html.a11y-hc button,html.a11y-hc .card,html.a11y-hc input,html.a11y-hc select{border-width:2px!important;border-style:solid!important;border-color:var(--ink)!important}',
    'html.a11y-hc .btn.primary,html.a11y-hc .tts-b[aria-pressed="true"]{background:#000!important;color:#fff!important}',
    'html.a11y-hc :focus-visible{outline:4px solid var(--focus)!important;outline-offset:3px}',
    'html.a11y-hc img{filter:contrast(1.1)}',
    /* o'qish uchun qulay shrift (tashqi shriftsiz — tizimdagi keng, aniq shriftlar) */
    'html.a11y-dys{--font:Verdana,Tahoma,"Trebuchet MS","Segoe UI","DejaVu Sans","Noto Sans",system-ui,sans-serif}',
    'html.a11y-dys body{letter-spacing:.035em;word-spacing:.14em;line-height:1.85}',
    'html.a11y-dys .prose,html.a11y-dys p,html.a11y-dys li{text-align:left!important;font-style:normal}',
    'html.a11y-dys em,html.a11y-dys i{font-style:normal;text-decoration:underline dotted}',
    /* harakatni kamaytirish */
    'html.a11y-rm *,html.a11y-rm *::before,html.a11y-rm *::after{animation:none!important;transition:none!important;scroll-behavior:auto!important}',
    '@media (prefers-reduced-motion:reduce){.a11y-t::after{transition:none}}',
    '@media print{.a11y-b,.a11y-p,.tts{display:none!important}}'
  ].join('\n');

  function load() {
    try {
      var v = JSON.parse(W.localStorage.getItem(KEY) || 'null');
      if (v && typeof v === 'object') {
        if (FS.indexOf(+v.fs) >= 0) P.fs = +v.fs;
        P.hc = !!v.hc; P.dys = !!v.dys; P.rm = !!v.rm;
      }
    } catch (e) { /* localStorage yo'q (sandbox / maxfiy oyna) — standart */ }
  }
  function save() { try { W.localStorage.setItem(KEY, JSON.stringify(P)); return true; } catch (e) { return false; } }
  function apply() {
    var r = D.documentElement;
    r.style.setProperty('--a11y-fs', String(P.fs / 100));
    r.classList.toggle('a11y-hc', !!P.hc); r.classList.toggle('a11y-dys', !!P.dys); r.classList.toggle('a11y-rm', !!P.rm);
  }
  function mq() { try { return W.matchMedia('(prefers-reduced-motion: reduce)').matches; } catch (e) { return false; } }
  function injectCss() {
    if (D.getElementById('isft-a11y-css')) return;
    var s = D.createElement('style'); s.id = 'isft-a11y-css'; s.textContent = CSS; (D.head || D.documentElement).appendChild(s);
  }
  function mk(tag, attrs, text) {
    var e = D.createElement(tag), k;
    for (k in attrs || {}) if (attrs[k] != null) e.setAttribute(k, attrs[k]);
    if (text != null) e.textContent = text;
    return e;
  }
  load(); injectCss(); apply();

  // ------------------------------------------------------------------ qulaylik paneli
  var uid = 0;
  function panel(opts) {
    opts = opts || {};
    var id = 'a11y-p' + (++uid), announce = opts.announce || function () {};
    var btn = mk('button', { type: 'button', 'class': 'a11y-b', 'aria-label': 'Qulaylik sozlamalari: matn o\'lchami, kontrast, shrift', 'aria-expanded': 'false', 'aria-controls': id, title: 'Qulaylik sozlamalari' }, 'Aa');
    var box = mk('div', { 'class': 'a11y-p', id: id, role: 'group', 'aria-label': 'Qulaylik sozlamalari' });
    box.hidden = true;
    box.appendChild(mk('h2', null, 'Qulaylik'));
    var row = mk('div', { 'class': 'a11y-row', role: 'group', 'aria-label': 'Matn o\'lchami' });
    var dec = mk('button', { type: 'button', 'class': 'a11y-s', 'aria-label': 'Matnni kichraytirish', 'data-a11y': 'fs-' }, 'A−');
    var val = mk('output', { 'class': 'a11y-v', 'aria-live': 'polite' });
    var inc = mk('button', { type: 'button', 'class': 'a11y-s', 'aria-label': 'Matnni kattalashtirish', 'data-a11y': 'fs+' }, 'A+');
    var rst = mk('button', { type: 'button', 'class': 'a11y-s', 'aria-label': 'Matn o\'lchamini tiklash', 'data-a11y': 'fs0' }, '100%');
    row.appendChild(dec); row.appendChild(val); row.appendChild(inc); row.appendChild(rst);
    box.appendChild(row);
    var T = [['hc', 'Yuqori kontrast'], ['dys', 'O\'qish uchun qulay shrift'], ['rm', 'Harakatni kamaytirish']].map(function (x) {
      var b = mk('button', { type: 'button', 'class': 'a11y-t', 'aria-pressed': 'false', 'data-a11y': x[0] }, x[1]);
      b.addEventListener('click', function () { P[x[0]] = !P[x[0]]; changed(x[1] + (P[x[0]] ? ' yoqildi' : ' o\'chirildi')); });
      box.appendChild(b); return b;
    });
    var note = mk('p', { 'class': 'a11y-note' }, 'Sozlamalar shu brauzerda eslab qolinadi.');
    box.appendChild(note);
    function paint() {
      var i = FS.indexOf(P.fs);
      val.textContent = P.fs + '%'; dec.disabled = i <= 0; inc.disabled = i >= FS.length - 1;
      T.forEach(function (b) { b.setAttribute('aria-pressed', String(!!P[b.getAttribute('data-a11y')])); });
    }
    function changed(msg) { apply(); var ok = save(); paint(); note.textContent = ok ? 'Sozlamalar shu brauzerda eslab qolinadi.' : 'Brauzer sozlamalarni saqlashga ruxsat bermadi — faqat shu sahifa uchun.'; if (msg) announce(msg); if (opts.onChange) opts.onChange(P); }
    function step(d) { var i = FS.indexOf(P.fs); i = Math.max(0, Math.min(FS.length - 1, (i < 0 ? 1 : i) + d)); P.fs = FS[i]; changed('Matn o\'lchami ' + P.fs + '%'); }
    dec.addEventListener('click', function () { step(-1); });
    inc.addEventListener('click', function () { step(1); });
    rst.addEventListener('click', function () { P.fs = 100; changed('Matn o\'lchami 100%'); });
    function open(o) {
      box.hidden = !o; btn.setAttribute('aria-expanded', String(o));
      if (o) { paint(); dec.disabled ? inc.focus() : dec.focus(); }
    }
    btn.addEventListener('click', function () { open(box.hidden); });
    box.addEventListener('keydown', function (e) { if (e.key === 'Escape') { e.stopPropagation(); open(false); btn.focus(); } });
    D.addEventListener('click', function (e) { if (!box.hidden && !box.contains(e.target) && e.target !== btn && !btn.contains(e.target)) open(false); });
    paint();
    return { button: btn, panel: box, open: open };
  }

  // ------------------------------------------------------------------ ovozli o'qish (Web Speech API)
  var SS = null; try { SS = W.speechSynthesis && W.SpeechSynthesisUtterance ? W.speechSynthesis : null; } catch (e) { SS = null; }
  var cur = null;   // {btn, target, msg, token}
  function voices() { try { return SS ? SS.getVoices() || [] : []; } catch (e) { return []; } }
  function pickVoice(list) {
    list = list || voices();
    var norm = function (v) { return String(v.lang || '').toLowerCase().replace('_', '-'); };
    var by = function (re) { for (var i = 0; i < list.length; i++) if (re.test(norm(list[i]))) return list[i]; return null; };
    return by(/^uz-uz/) || by(/^uz\b/) || by(/^ru-ru/) || by(/^ru\b/) || list.filter(function (v) { return v.default; })[0] || list[0] || null;
  }
  function whenVoices(cb) {
    var v = voices(), done = false;
    if (v.length) { cb(v); return; }
    function fin() { if (done) return; done = true; cb(voices()); }
    try { SS.addEventListener('voiceschanged', fin, { once: true }); } catch (e) { /* eski brauzer */ }
    setTimeout(fin, 900);
  }
  function chunks(text) {   // gaplar bo'yicha ≤ 220 belgi
    var out = [], buf = '';
    (String(text || '').replace(/\s+/g, ' ').trim().match(/[^.!?…;:]+[.!?…;:]*\s*/g) || []).forEach(function (s) {
      s = s.trim(); if (!s) return;
      while (s.length > 220) { var k = s.lastIndexOf(' ', 220); if (k < 60) k = 220; out.push(s.slice(0, k)); s = s.slice(k).trim(); }
      if ((buf + ' ' + s).trim().length > 220) { if (buf) out.push(buf); buf = s; } else buf = (buf + ' ' + s).trim();
    });
    if (buf) out.push(buf);
    return out;
  }
  function setState(c, on) {
    if (!c) return;
    c.btn.setAttribute('aria-pressed', String(on));
    c.lbl.textContent = on ? 'To\'xtatish' : 'Tinglash';
    if (c.target) c.target.classList.toggle('reading', on);
  }
  function stop() {
    var c = cur; cur = null;
    try { if (SS) SS.cancel(); } catch (e) { /* jim */ }
    setState(c, false);
  }
  function say(c, msg) { if (c.msg) c.msg.textContent = msg || ''; if (msg && c.announce) c.announce(msg); }
  function speak(c) {
    if (!SS) { say(c, 'Brauzeringiz ovozli o\'qishni qo\'llab-quvvatlamaydi — Chrome, Edge yoki Safari\'ning yangi versiyasidan foydalaning.'); return; }
    var text = String(c.getText() || '').trim();
    if (!text) { say(c, 'O\'qiladigan matn yo\'q.'); return; }
    stop();
    cur = c; c.token = {}; var tok = c.token;
    setState(c, true); say(c, 'Ovoz tayyorlanmoqda…');
    whenVoices(function (list) {
      if (cur !== c || c.token !== tok) return;
      var v = pickVoice(list);
      if (!v) { stop(); say(c, 'Qurilmada ovoz topilmadi. Tizim sozlamalarida o\'zbek yoki rus tilidagi ovozni o\'rnating.'); return; }
      var lang = String(v.lang || '').toLowerCase();
      say(c, /^uz/.test(lang) ? 'O\'qilmoqda (o\'zbekcha ovoz)' : /^ru/.test(lang) ? 'O\'zbekcha ovoz topilmadi — ruscha ovoz bilan o\'qilmoqda' : 'O\'zbekcha ovoz topilmadi — standart ovoz bilan o\'qilmoqda');
      var parts = chunks(text), i = 0;
      (function next() {
        if (cur !== c || c.token !== tok) return;
        if (i >= parts.length) { stop(); say(c, ''); return; }
        var u = new W.SpeechSynthesisUtterance(parts[i++]);
        u.voice = v; u.lang = v.lang || 'uz-UZ'; u.rate = 0.95;
        u.onend = next;
        u.onerror = function (e) { if (cur === c && c.token === tok) { stop(); if (!e || e.error !== 'canceled' && e.error !== 'interrupted') say(c, 'Ovozli o\'qish to\'xtadi (' + ((e && e.error) || 'xato') + ').'); } };
        try { SS.speak(u); } catch (e) { stop(); say(c, 'Ovozli o\'qishni boshlab bo\'lmadi.'); }
      })();
    });
  }
  // «Tinglash» tugmasi: getText() — o'qiladigan matn, target — ajratib ko'rsatiladigan blok; announce — pleyerning aria-live xabari
  function ttsButton(getText, target, opts) {
    opts = opts || {};
    var lbl = mk('span', null, 'Tinglash');
    var btn = mk('button', { type: 'button', 'class': 'tts-b', 'aria-pressed': 'false', title: opts.label || 'Matnni ovozli tinglash' });
    btn.appendChild(mk('span', { 'class': 'tts-i', 'aria-hidden': 'true' }, '▶')); btn.appendChild(lbl);
    var msg = mk('span', { 'class': 'tts-m', role: 'status' });
    var c = { btn: btn, lbl: lbl, msg: msg, target: target, getText: getText, announce: opts.announce };
    btn.addEventListener('click', function () { if (cur === c) { stop(); say(c, ''); } else speak(c); });
    var wrap = mk('div', { 'class': 'tts' }); wrap.appendChild(btn); wrap.appendChild(msg);
    return wrap;
  }

  W.ISFTA11y = {
    version: '1.0.0', prefs: function () { return { fs: P.fs, hc: P.hc, dys: P.dys, rm: P.rm }; },
    reduced: function () { return !!P.rm || mq(); },
    panel: panel, ttsButton: ttsButton, stop: stop, supported: function () { return !!SS; }, pickVoice: pickVoice
  };
  try { W.addEventListener('pagehide', stop); } catch (e) { /* jim */ }
})(window, document);
