/* ISFT Core — kurs pleyeri («Kurs muharriri», Articulate Rise o'rnini bosuvchi). Kontent: window.KURS (content.js, app/kurs.py build_content).
 * LMS adapterlari — lms.js (window.ISFTLms, paket pleyeri bilan umumiy). Global nom: faqat window.ISFTKurs.
 * Muqova → yon menyu (darslar, holat, qidiruv) → dars sahifasi (bloklar ketma-ket; «Davom etish» bloki qolgan qismni yashiradi,
 * require="interactions" — yuqoridagi interaktiv bloklar bajarilguncha tugma faol emas) → test darsi (savollar banki, aralashtirish,
 * o'tish foizi, urinishlar, javoblarni ko'rsatish siyosati). Ko'rish rejimi (?preview=1) va «#lesson=<uid>&block=<id>» — muharrir uchun.
 * Kuzatuv: SCORM 1.2 / SCORM 2004 / xAPI (ichki faoliyatlar «<kurs>/lesson/<uid>», savollar «…/q/<id>» — app/kurs.py tincan_xml bilan bir xil).
 * Baholash qoidasi app/kurs.py grade()/norm_answer() bilan BIR XIL (hammasi yoki hech narsa; bo'sh joy — me'yorlangan matn).
 * Ota oynaga: postMessage({source:"isft-kurs", v:1, id, event, progress, score, lesson, lessons, complete, success}, "*").
 */
(function (W, D) {
  'use strict';
  var NS = W.ISFTKurs = { version: '1.0.0', ready: false, mode: null, log: [] };
  var RAW = W.KURS, LMS = W.ISFTLms;

  // ------------------------------------------------------------------ yordamchilar
  function note(m) { NS.log.push(new Date().toISOString().slice(11, 19) + ' ' + m); if (NS.log.length > 200) NS.log.shift(); }
  function str(v, d) { return v == null ? (d || '') : String(v); }
  function arr(v) { return Array.isArray(v) ? v : []; }
  function num(v, d) { var n = Number(v); return isFinite(n) ? n : d; }
  function clamp(n, a, b) { return Math.max(a, Math.min(b, n)); }
  function el(tag, attrs, kids) {
    var e = D.createElement(tag), k;
    if (attrs) for (k in attrs) {
      var v = attrs[k];
      if (v == null || v === false) continue;
      if (k === 'text') e.textContent = v;
      else if (k === 'cls') e.className = v;
      else if (k.slice(0, 2) === 'on' && typeof v === 'function') e.addEventListener(k.slice(2), v);
      else e.setAttribute(k, v === true ? '' : v);
    }
    (Array.isArray(kids) ? kids : kids == null ? [] : [kids]).forEach(function (c) {
      if (c == null || c === false) return;
      e.appendChild(typeof c === 'string' || typeof c === 'number' ? D.createTextNode(String(c)) : c);
    });
    return e;
  }
  // Yagona innerHTML joyi: faqat shu fayldagi statik SVG ikonkalar — kontentdan hech narsa kelmaydi
  function staticSvg(cls, attrs, body) { var s = el('span', { cls: cls, 'aria-hidden': 'true' }); s.innerHTML = '<svg ' + attrs + '>' + body + '</svg>'; return s; }
  function icon(name) { return staticSvg('ic', 'viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"', ICONS[name] || ''); }
  var ICONS = {
    check: '<path d="M5 12l5 5 9-10"/>', x: '<path d="M6 6l12 12M18 6L6 18"/>', left: '<path d="M15 6l-6 6 6 6"/>', right: '<path d="M9 6l6 6-6 6"/>',
    menu: '<path d="M4 7h16M4 12h16M4 17h16"/>', lock: '<rect x="5" y="11" width="14" height="10" rx="2"/><path d="M8 11V8a4 4 0 0 1 8 0v3"/>',
    search: '<circle cx="11" cy="11" r="7"/><path d="M20 20l-3.5-3.5"/>', down: '<path d="M12 4v12M7 11l5 5 5-5M5 20h14"/>', ext: '<path d="M14 4h6v6M20 4l-9 9M18 14v6H4V6h6"/>',
    quiz: '<circle cx="12" cy="12" r="9"/><path d="M9.5 9.5a2.5 2.5 0 1 1 3.5 2.3c-.6.3-1 .9-1 1.6v.6M12 17h.01"/>', flip: '<path d="M4 9a8 8 0 0 1 14-3l2 2M20 4v4h-4M20 15a8 8 0 0 1-14 3l-2-2M4 20v-4h4"/>',
    home: '<path d="M4 11l8-7 8 7v9H4z"/><path d="M10 20v-6h4v6"/>', restart: '<path d="M4 4v6h6"/><path d="M5.5 15a7 7 0 1 0 1.6-7.3L4 10"/>', plus: '<path d="M12 5v14M5 12h14"/>',
    file: '<path d="M14 3H6v18h12V7z"/><path d="M14 3v4h4"/>', chev: '<path d="M6 9l6 6 6-6"/>'
  };
  function hash(s) { var h = 2166136261; s = str(s); for (var i = 0; i < s.length; i++) { h ^= s.charCodeAt(i); h = Math.imul(h, 16777619); } return h >>> 0; }
  function shuffled(n) { var a = [], i, j, t; for (i = 0; i < n; i++) a.push(i); for (i = n - 1; i > 0; i--) { j = Math.floor(Math.random() * (i + 1)); t = a[i]; a[i] = a[j]; a[j] = t; } return a; }
  function ident(n) { var a = []; for (var i = 0; i < n; i++) a.push(i); return a; }
  function letter(i) { return 'abcdefghijklmnopqrstuvwxyz'.charAt(i) || String(i); }
  function cmiId(s) { return str(s).replace(/[^A-Za-z0-9_\-.]/g, '_').slice(0, 250) || 'x'; }
  function fmtSize(n) { n = num(n, 0); if (!n) return ''; return n < 1024 ? n + ' B' : n < 1048576 ? Math.round(n / 1024) + ' KB' : (n / 1048576).toFixed(1).replace('.', ',') + ' MB'; }
  function assetUrl(p) { p = str(p).replace(/[\x00-\x20\x7f]/g, ''); return p && /^assets\/(?!.*\.\.)[A-Za-z0-9_\-.\/]+$/.test(p) ? p : null; }
  function httpUrl(u) { u = str(u).replace(/^[\x00-\x20\x7f]+|[\x00-\x20\x7f]+$/g, ''); return /^https?:\/\/[^\s"'<>\\]+$/i.test(u) ? u : null; }
  function opaqueHttp() { try { return String(W.origin) === 'null' && /^https?:$/.test(W.location.protocol); } catch (e) { return false; } }
  // Bo'sh joy javobi — app/kurs.py norm_answer() bilan bir xil
  function normAns(s) {
    s = str(s).replace(/[ʻʼ‘’`´]/g, "'").toLowerCase().replace(/\s+/g, ' ').trim();
    return s.replace(/^[\s.,;:!?"«»()]+|[\s.,;:!?"«»()]+$/g, '');
  }
  // Baholash — app/kurs.py grade() bilan bir xil: resp — tanlangan javoblarning ASL indekslari (yoki bo'sh joy matni)
  function grade(q, resp) {
    if (q.kind === 'fill') {
      var acc = arr(q.accept).map(normAns);
      return acc.length > 0 && acc.indexOf(normAns(resp)) >= 0;
    }
    var want = [], got = {}, n = 0, i;
    arr(q.answers).forEach(function (a, k) { if (a && a.correct) want.push(k); });
    var r = arr(resp);
    for (i = 0; i < r.length; i++) { var x = parseInt(r[i], 10); if (!isFinite(x)) return false; if (!got[x]) { got[x] = 1; n++; } }
    if ((q.kind === 'single' || q.kind === 'truefalse') && n !== 1) return false;
    return want.length > 0 && n === want.length && want.every(function (k) { return got[k]; });
  }

  // ------------------------------------------------------------------ HTML tozalash (server tozalaganidan keyin ikkinchi qatlam)
  var ALLOW = { p: [], br: [], h2: [], h3: [], h4: [], ul: [], ol: ['start'], li: [], strong: [], b: [], em: [], i: [], u: [], s: [], sub: [], sup: [],
    blockquote: [], pre: [], code: [], span: [], div: [], table: [], caption: [], thead: [], tbody: [], tr: [], th: ['colspan', 'rowspan', 'scope'], td: ['colspan', 'rowspan'], a: ['href', 'title'] };
  var DROP = { script: 1, style: 1, iframe: 1, object: 1, embed: 1, noscript: 1, template: 1, svg: 1, math: 1, form: 1, input: 1, button: 1, select: 1, textarea: 1, link: 1, meta: 1,
    base: 1, frame: 1, frameset: 1, audio: 1, video: 1, source: 1, canvas: 1, title: 1, head: 1, img: 1 };
  function sanitize(html) {
    var frag = D.createDocumentFragment(), doc;
    try { doc = new DOMParser().parseFromString('<!doctype html><body>' + str(html), 'text/html'); } catch (e) { return frag; }
    (function walk(src, dst) {
      Array.prototype.forEach.call(src.childNodes, function (n) {
        if (n.nodeType === 3) { dst.appendChild(D.createTextNode(n.nodeValue)); return; }
        if (n.nodeType !== 1) return;
        var tag = n.nodeName.toLowerCase();
        if (DROP[tag]) return;
        if (tag === 'h1') tag = 'h2';
        if (!ALLOW[tag]) { walk(n, dst); return; }
        var out = D.createElement(tag);
        ALLOW[tag].forEach(function (a) {
          var v = n.getAttribute(a); if (v == null) return;
          if (a === 'href') { var u = httpUrl(v); if (!u) return; out.setAttribute('href', u); out.setAttribute('target', '_blank'); out.setAttribute('rel', 'noopener noreferrer'); }
          else if (/^(colspan|rowspan|start)$/.test(a)) { if (/^\d{1,3}$/.test(v)) out.setAttribute(a, v); }
          else if (a === 'scope') { if (/^(row|col)$/.test(v)) out.setAttribute(a, v); }
          else out.setAttribute(a, v.slice(0, 300));
        });
        if (tag === 'a' && !out.getAttribute('href')) { walk(n, dst); return; }
        dst.appendChild(out); walk(n, out);
      });
    })(doc.body, frag);
    return frag;
  }
  function rich(html, cls) { var d = el('div', { cls: 'prose' + (cls ? ' ' + cls : '') }); d.appendChild(sanitize(html)); return d; }
  function plain(html) { var d = el('div'); d.appendChild(sanitize(html)); return d.textContent.replace(/\s+/g, ' ').trim(); }

  // ------------------------------------------------------------------ kontent
  var app = D.getElementById('app');
  function fatal(h, p) { app.removeAttribute('aria-busy'); app.textContent = ''; app.appendChild(el('main', { cls: 'fatal' }, [el('h1', { text: h }), el('p', { text: p })])); }
  if (!LMS) { fatal('Pleyer fayli yetishmaydi', "lms.js fayli topilmadi. Kursni qayta eksport qiling."); return; }
  LMS.setLog(note);
  var C = RAW && typeof RAW === 'object' && RAW.kind === 'kurs' ? RAW : null;
  var LS = C ? arr(C.lessons).filter(function (l) { return l && /^(blocks|quiz)$/.test(l.type) && l.id; }) : [];
  if (!C || !LS.length) { fatal('Kurs tarkibi topilmadi', "content.js fayli yo'q yoki darslar bo'sh. Kursni qayta eksport qiling."); return; }
  C.settings = C.settings || {}; C.tracking = C.tracking || {}; C.labels = C.labels || {};
  LS.forEach(function (l) {
    l.blocks = arr(l.blocks).filter(function (b) { return b && b.type; });
    l.questions = arr(l.questions).filter(function (q) { return q && q.kind; });
    l.quiz = l.quiz || {};
  });
  var LB = { start: 'Kursni boshlash', resume: 'Davom ettirish', continue: 'Davom etish', next_lesson: 'Keyingi dars', prev_lesson: 'Oldingi dars', lesson: 'Dars',
    lessons: 'Darslar', quiz: 'Test', quiz_start: 'Testni boshlash', submit: 'Javobni tekshirish', next_question: 'Keyingi savol', retry: 'Qayta urinish', result: 'Natija',
    search: 'Qidirish', complete_hint: 'Davom etish uchun yuqoridagi topshiriqlarni bajaring', menu: 'Mundarija', progress: 'bajarildi', passed: 'Test topshirildi',
    failed: 'Test topshirilmadi', correct: "To'g'ri", incorrect: "Noto'g'ri", finish: 'Kurs yakunlandi' };
  function T(k) { return str(C.labels[k]).trim() || LB[k] || k; }
  var ACC = /^#[0-9a-f]{6}$/i.test(str(C.accent)) ? C.accent : '#870037';
  function shade(hex, t) {
    var n = parseInt(hex.slice(1), 16), c = [n >> 16, (n >> 8) & 255, n & 255].map(function (x) { return Math.round(t < 0 ? x * (1 + t) : x + (255 - x) * t); });
    return '#' + c.map(function (x) { var s = x.toString(16); return s.length < 2 ? '0' + s : s; }).join('');
  }
  var RS = D.documentElement.style;
  RS.setProperty('--brand', ACC); RS.setProperty('--brand-ink', shade(ACC, -0.25)); RS.setProperty('--brand-soft-l', shade(ACC, 0.9)); RS.setProperty('--brand-lite', shade(ACC, 0.45));
  D.documentElement.lang = /^[a-z]{2}$/.test(str(C.lang)) ? C.lang : 'uz';
  D.title = str(C.title) + ' — ' + (str((C.brand || {}).name) || 'ISFT');
  try { var org = typeof W.origin === 'string' ? W.origin : W.location.origin; if (org && org !== 'null') D.head.appendChild(el('link', { rel: 'stylesheet', href: 'fonts/fonts.css' })); } catch (e) { /* jim */ }
  var reduced = false; try { reduced = W.matchMedia('(prefers-reduced-motion: reduce)').matches; } catch (e) { /* jim */ }
  var INTERACTIVE = { accordion: 1, tabs: 1, flashcards: 1, process: 1, sorting: 1, matching: 1, knowledge: 1, labeled_graphic: 1 };
  var QUIZZES = LS.filter(function (l) { return l.type === 'quiz'; }), VIEWS = LS.filter(function (l) { return l.type === 'blocks'; });

  // ------------------------------------------------------------------ holat: {h, c: joriy dars (-1 muqova), v: {dars: 1}, g: {dars: ochilgan bo'laklar}, i: {blok: 1},
  //   k: {blok: {a, ok}} (bilimni tekshirish), q: {dars: {n, s, b, p}} (test: urinishlar, oxirgi, eng yaxshi, o'tdi), cs/xr — xAPI}
  var S = { h: hash(C.id), c: -1, v: {}, g: {}, i: {}, k: {}, q: {} };
  var tracker = null, cur = -1, t0 = Date.now(), finished = false, lmsMastery = null, lastCompl = null, saveT = 0, R = {}, CLEAN = [], previewMode = false;
  function obj(v) { return v && typeof v === 'object' && !Array.isArray(v) ? v : {}; }
  function qst(l) { var q = S.q[l.id]; if (!q || typeof q !== 'object') q = S.q[l.id] = { n: 0, s: null, b: null, p: 0 }; return q; }
  function passPct(l) { return lmsMastery != null ? clamp(lmsMastery, 0, 100) : clamp(num(l.quiz.pass_pct, 80), 0, 100); }
  function lessonDone(l) { return !!S.v[l.id]; }
  function status() {
    var seen = VIEWS.filter(lessonDone).length, viewPct = VIEWS.length ? 100 * seen / VIEWS.length : 100;
    var tried = QUIZZES.filter(function (l) { return qst(l).n > 0; });
    var passed = QUIZZES.length > 0 && QUIZZES.every(function (l) { return qst(l).p; });
    var score = tried.length ? Math.round(tried.reduce(function (a, l) { var q = qst(l); return a + num(q.p ? q.b : q.s, 0); }, 0) / tried.length) : null;
    var success = !tried.length ? 'unknown' : passed ? 'passed' : tried.some(function (l) { return !qst(l).p; }) ? 'failed' : 'unknown';
    var mode = str(C.tracking.completion) || 'view', viewOk = viewPct + 1e-9 >= clamp(num(C.tracking.view_pct, 100), 1, 100);
    if (!QUIZZES.length) mode = 'view';
    var complete = mode === 'quiz' ? passed : mode === 'view_and_quiz' ? viewOk && passed : mode === 'view_or_quiz' ? viewOk || passed : viewOk;
    var done = LS.filter(function (l) { return l.type === 'quiz' ? qst(l).p || qst(l).n > 0 : lessonDone(l); }).length;
    return { complete: complete, success: success, score: score, progress: done / LS.length, seen: seen, total: VIEWS.length };
  }
  function stateString() { S.c = cur; return LMS.encodeState(S, tracker.limit); }
  function save(commit) { if (!tracker) return; tracker.save(stateString(), cur >= 0 ? LS[cur].id : ''); if (commit) tracker.commit(); }
  function saveSoon() { clearTimeout(saveT); saveT = setTimeout(function () { save(false); }, 400); }
  function announce(t) { if (!R.live) return; R.live.textContent = ''; setTimeout(function () { R.live.textContent = t; }, 30); }
  var pm = { key: '', completed: false };
  function emit(ev, r, extra) {
    if (W.parent === W) return;
    r = r || status();
    var m = { source: 'isft-kurs', v: 1, id: C.id, event: ev, progress: Math.round(r.progress * 1000) / 1000, score: r.score == null ? null : { raw: r.score, min: 0, max: 100, scaled: r.score / 100 },
      lesson: cur + 1, lessons: LS.length, complete: !!r.complete, success: r.success };
    if (extra) for (var k in extra) m[k] = extra[k];
    try { W.parent.postMessage(m, '*'); } catch (e) { /* jim */ }
  }
  function report(commit) {
    var r = status();
    tracker.report(r, S);
    paintProgress(r);
    if (r.complete && lastCompl === false) announce(T('finish') + '!');
    lastCompl = r.complete;
    save(commit);
    var key = Math.round(r.progress * 1000) + '|' + cur;
    if (key !== pm.key) { pm.key = key; emit('progress', r); }
    if (r.complete && !pm.completed) { pm.completed = true; emit('completed', r); }
    return r;
  }
  function locked(i) {
    if (!C.settings.sequential || previewMode) return false;
    for (var k = 0; k < i; k++) { var l = LS[k]; if (l.type === 'quiz' ? !(qst(l).p || qst(l).n > 0) : !lessonDone(l)) return true; }
    return false;
  }
  function completeLesson(l) {
    if (S.v[l.id]) return;
    S.v[l.id] = 1;
    if (tracker.done) tracker.done({ id: l.id, type: l.type, title: l.title });
    paintNav(); report(true);
    announce('«' + l.title + '» darsi yakunlandi');
  }

  // ------------------------------------------------------------------ qobiq: yuqori panel, yon menyu, qidiruv
  function build() {
    app.textContent = ''; app.removeAttribute('aria-busy');
    app.classList.toggle('no-side', !C.settings.sidebar);
    R.live = el('div', { cls: 'sr', 'aria-live': 'polite', role: 'status' });
    var skip = el('a', { cls: 'skip', href: '#main', text: "Asosiy mazmunga o'tish", onclick: function (e) { e.preventDefault(); R.main.focus(); } });
    var banner = tracker.preview ? el('div', { cls: 'banner', role: 'note' }, [el('strong', { text: "Ko'rish rejimi" }), " — natija LMS'ga yuborilmaydi"])
      : tracker.nolms ? el('div', { cls: 'banner warn', role: 'alert' }, [el('strong', { text: 'LMS bilan aloqa topilmadi' }), " — natija saqlanmaydi. O'qituvchiga xabar bering."]) : null;
    R.menuBtn = el('button', { cls: 'btn icon menu-btn', type: 'button', 'aria-label': T('menu'), 'aria-controls': 'side', 'aria-expanded': 'false', onclick: toggleSide }, [icon('menu')]);
    R.pct = el('span', { cls: 'chip' });
    R.bar = el('span');
    var logo = assetUrl((C.brand || {}).logo);
    var top = el('header', { cls: 'top' }, [el('div', { cls: 'top-in' }, [R.menuBtn,
      logo ? el('img', { cls: 'logo', src: logo, alt: str((C.brand || {}).name) || 'ISFT' }) : null,
      el('button', { cls: 'ttl', type: 'button', onclick: function () { go(-1); }, 'aria-label': 'Muqovaga qaytish: ' + C.title }, [el('span', { cls: 'h', text: C.title })]),
      R.pct]), el('div', { cls: 'bar', 'aria-hidden': 'true' }, [R.bar])]);
    R.side = el('nav', { cls: 'side', id: 'side', 'aria-label': T('lessons') });
    R.main = el('main', { cls: 'main', id: 'main', tabindex: '-1' });
    R.scrim = el('div', { cls: 'scrim', onclick: closeSide });
    app.appendChild(skip); if (banner) app.appendChild(banner); app.appendChild(top);
    app.appendChild(el('div', { cls: 'wrap' }, [R.side, R.main])); app.appendChild(R.scrim); app.appendChild(R.live);
    buildSide();
    D.addEventListener('keydown', function (e) { if (e.key === 'Escape' && app.classList.contains('side-open')) { closeSide(); R.menuBtn.focus(); } });
  }
  function toggleSide() {
    if (!C.settings.sidebar && !app.classList.contains('side-open') && W.innerWidth > 980) { go(-1); return; }
    var open = !app.classList.contains('side-open');
    app.classList.toggle('side-open', open); R.menuBtn.setAttribute('aria-expanded', String(open));
    if (open) { var f = R.side.querySelector('input,button'); if (f) f.focus(); }
  }
  function closeSide() { app.classList.remove('side-open'); R.menuBtn.setAttribute('aria-expanded', 'false'); }
  function buildSide() {
    R.side.textContent = '';
    R.sidePct = el('span', { cls: 'sm muted' });
    R.sideBar = el('span');
    R.side.appendChild(el('div', { cls: 'side-h' }, [el('div', { cls: 'side-t', text: C.title }), el('div', { cls: 'meter' }, [R.sideBar]), R.sidePct]));
    if (C.settings.search !== false) {
      R.q = el('input', { type: 'search', cls: 'search', placeholder: T('search') + '…', 'aria-label': T('search'), autocomplete: 'off', oninput: function () { runSearch(R.q.value); } });
      R.results = el('div', { cls: 'results', role: 'region', 'aria-label': 'Qidiruv natijalari', 'aria-live': 'polite' });
      R.side.appendChild(el('div', { cls: 'search-w', role: 'search' }, [icon('search'), R.q])); R.side.appendChild(R.results);
    }
    R.list = el('ol', { cls: 'les' });
    R.side.appendChild(R.list);
    paintNav();
  }
  function paintNav() {
    if (!R.list) return;
    R.list.textContent = '';
    LS.forEach(function (l, i) {
      var lk = locked(i), done = l.type === 'quiz' ? qst(l).p : lessonDone(l), failedQ = l.type === 'quiz' && !qst(l).p && qst(l).n > 0;
      var st = lk ? el('span', { cls: 'st lk', title: 'Oldingi darslarni yakunlang' }, [icon('lock')]) : done ? el('span', { cls: 'st ok' }, [icon('check')]) : el('span', { cls: 'st' + (failedQ ? ' bad' : '') });
      var b = el('button', { type: 'button', cls: 'les-b' + (i === cur ? ' on' : ''), 'aria-current': i === cur ? 'page' : null, disabled: lk, 'data-lesson': l.id,
        onclick: function () { closeSide(); go(i); } }, [
        C.settings.lesson_count !== false ? el('span', { cls: 'no', text: String(i + 1) }) : null,
        el('span', { cls: 'les-t' }, [l.type === 'quiz' ? el('span', { cls: 'tag', text: T('quiz') }) : null, l.title]),
        st, el('span', { cls: 'sr', text: lk ? ' (yopiq)' : done ? ' (yakunlangan)' : '' })]);
      R.list.appendChild(el('li', null, [b]));
    });
  }
  function paintProgress(r) {
    var p = Math.round(r.progress * 100);
    if (R.pct) { R.pct.textContent = p + '% ' + T('progress'); R.pct.className = 'chip' + (r.complete ? ' good' : ''); }
    if (R.bar) R.bar.style.width = p + '%';
    if (R.sideBar) R.sideBar.style.width = p + '%';
    if (R.sidePct) R.sidePct.textContent = p + '% ' + T('progress');
  }
  // qidiruv: darslar va bloklar matni bo'yicha
  var INDEX = null;
  function blockText(b) {
    var out = [];
    (function grab(o, d) {
      if (d > 3 || o == null) return;
      if (typeof o === 'string') { out.push(o); return; }
      if (Array.isArray(o)) { o.forEach(function (x) { grab(x, d + 1); }); return; }
      if (typeof o === 'object') for (var k in o) if (!/^(id|type|src|poster|style|layout|side|source|yt_id|url|lang|require|kind|correct|cat|ext|name|size|x|y)$/.test(k)) grab(o[k], d + 1);
    })(b, 0);
    return plain(out.join(' \n '));
  }
  function runSearch(q) {
    R.results.textContent = '';
    q = normAns(q);
    if (q.length < 2) return;
    if (!INDEX) {
      INDEX = [];
      LS.forEach(function (l, i) {
        INDEX.push({ i: i, b: null, t: l.title });
        (l.type === 'quiz' ? [] : l.blocks).forEach(function (b) { INDEX.push({ i: i, b: b.id, t: blockText(b) }); });
      });
    }
    var hits = INDEX.filter(function (x) { return normAns(x.t).indexOf(q) >= 0; }).slice(0, 30);
    if (!hits.length) { R.results.appendChild(el('p', { cls: 'sm muted', text: "Hech narsa topilmadi" })); return; }
    R.results.appendChild(el('p', { cls: 'sm muted', text: hits.length + ' ta natija' }));
    hits.forEach(function (h) {
      var t = h.t, k = normAns(t).indexOf(q), snip = (k > 40 ? '…' : '') + t.slice(Math.max(0, k - 40), k + 80) + (t.length > k + 80 ? '…' : '');
      R.results.appendChild(el('button', { type: 'button', cls: 'res', disabled: locked(h.i), onclick: function () { closeSide(); go(h.i, h.b); } },
        [el('b', { text: (h.i + 1) + '. ' + LS[h.i].title }), el('span', { text: snip })]));
    });
  }

  // ------------------------------------------------------------------ navigatsiya
  function cleanup() { var c = CLEAN; CLEAN = []; c.forEach(function (f) { try { f(); } catch (e) { /* jim */ } }); }
  function go(i, blockId, noFocus) {
    if (i >= 0 && locked(i)) { announce('Bu dars hali yopiq: oldingi darslarni yakunlang'); return; }
    cleanup();
    cur = i;
    R.main.textContent = '';
    if (i < 0) renderCover(); else if (LS[i].type === 'quiz') renderQuiz(LS[i]); else renderLesson(LS[i], blockId);
    paintNav(); report(false);
    if (i >= 0 && tracker.visit) tracker.visit({ id: LS[i].id, type: LS[i].type === 'quiz' ? 'quiz' : 'lesson', title: LS[i].title });
    if (!blockId) { try { W.scrollTo({ top: 0, behavior: 'instant' }); } catch (e) { W.scrollTo(0, 0); } }
    if (!noFocus) { var h = R.main.querySelector('h1'); if (h && !blockId) h.focus({ preventScroll: true }); }
    emit('lesson');
  }
  function lessonNav(i) {
    var prev = i > 0 ? el('button', { cls: 'btn ghost', type: 'button', onclick: function () { go(i - 1); } }, [icon('left'), T('prev_lesson')]) : el('span');
    var nx = i < LS.length - 1;
    var next = el('button', { cls: 'btn primary next-lesson', type: 'button', onclick: function () {
      if (LS[i].type === 'blocks') completeLesson(LS[i]);
      if (nx) go(i + 1); else { go(-1); announce(T('finish')); }
    } }, nx ? [T('next_lesson'), icon('right')] : status().complete ? [T('finish'), icon('check')] : [icon('home'), T('menu')]);
    return el('div', { cls: 'pager' }, [prev, next]);
  }

  // ------------------------------------------------------------------ muqova
  function renderCover() {
    var r = status(), started = S.c >= 0 || Object.keys(S.v).length > 0, cv = C.cover && assetUrl(C.cover.src);
    var first = 0; if (S.c >= 0 && S.c < LS.length && !locked(S.c)) first = S.c;
    var start = el('button', { cls: 'btn primary lg', type: 'button', id: 'startBtn', onclick: function () { go(first); } }, [started ? T('resume') : T('start'), icon('right')]);
    var hero = el('section', { cls: 'cover' + (cv ? ' has-img' : '') }, [
      cv ? el('img', { cls: 'cover-img', src: cv, alt: str(C.cover.alt) }) : null,
      el('div', { cls: 'cover-in' }, [
        el('p', { cls: 'eyebrow', text: (C.settings.lesson_count !== false ? LS.length + ' ta dars · ' : '') + (str((C.brand || {}).name) || 'ISFT') }),
        el('h1', { tabindex: '-1', text: C.title }),
        C.description ? rich(C.description, 'lead') : null,
        C.author ? el('p', { cls: 'author', text: C.author }) : null,
        el('div', { cls: 'cover-acts' }, [start, started ? el('span', { cls: 'chip' + (r.complete ? ' good' : ''), text: Math.round(r.progress * 100) + '% ' + T('progress') }) : null])])]);
    var list = el('ol', { cls: 'outline' });
    LS.forEach(function (l, i) {
      var lk = locked(i), done = l.type === 'quiz' ? qst(l).p : lessonDone(l);
      list.appendChild(el('li', null, [el('button', { type: 'button', cls: 'out-b', disabled: lk, onclick: function () { go(i); } }, [
        el('span', { cls: 'no', text: C.settings.lesson_count !== false ? String(i + 1) : '' }), el('span', { cls: 'les-t' }, [l.type === 'quiz' ? el('span', { cls: 'tag', text: T('quiz') }) : null, l.title]),
        lk ? icon('lock') : done ? el('span', { cls: 'st ok' }, [icon('check')]) : icon('right')])]));
    });
    R.main.appendChild(hero);
    R.main.appendChild(el('section', { cls: 'card outline-c', 'aria-label': T('lessons') }, [el('h2', { text: T('lessons') }), list]));
  }

  // ------------------------------------------------------------------ dars sahifasi: bloklar «Davom etish» bo'yicha bo'laklarga ajraladi
  function renderLesson(l, blockId) {
    var i = LS.indexOf(l), segs = [[]];
    l.blocks.forEach(function (b) { segs[segs.length - 1].push(b); if (b.type === 'continue') segs.push([]); });
    var open = clamp(num(S.g[l.id], 0), 0, segs.length - 1);
    var head = el('header', { cls: 'les-h' }, [
      C.settings.lesson_count !== false ? el('p', { cls: 'eyebrow', text: T('lesson') + ' ' + (i + 1) + ' / ' + LS.length }) : null,
      el('h1', { tabindex: '-1', text: l.title })]);
    R.main.appendChild(head);
    var gates = [], segEls = [];
    var endBox = el('div', { cls: 'les-end' });
    function refreshGates() {
      gates.forEach(function (g) {
        var need = g.b.require === 'interactions', pending = need ? g.above.filter(function (b) { return INTERACTIVE[b.type] && !S.i[b.id]; }) : [];
        g.btn.disabled = pending.length > 0;
        g.btn.setAttribute('aria-describedby', pending.length ? g.hintId : '');
        g.hint.hidden = !pending.length;
      });
    }
    function reveal(k, focus) {
      if (k <= open && !focus) return;
      open = Math.max(open, k); S.g[l.id] = open; saveSoon();
      segEls.forEach(function (s, j) { s.hidden = j > open; });
      gates.forEach(function (g, j) { g.wrap.hidden = j < open || j > open; });
      endBox.hidden = open < segs.length - 1;
      if (focus) { var f = segEls[k].querySelector('h2,h3,.blk'); if (f) { f.setAttribute('tabindex', '-1'); f.focus({ preventScroll: true }); try { segEls[k].scrollIntoView({ behavior: reduced ? 'auto' : 'smooth', block: 'start' }); } catch (e) { /* jim */ } } }
      watchEnd();
    }
    segs.forEach(function (seg, k) {
      var box = el('div', { cls: 'seg', 'data-seg': String(k) });
      seg.forEach(function (b) {
        if (b.type === 'continue') {
          var hid = 'h-' + b.id, hint = el('p', { cls: 'gate-hint', id: hid, text: b.hint || T('complete_hint') });
          var btn = el('button', { cls: 'btn primary lg', type: 'button', 'data-gate': b.id, onclick: function () { reveal(k + 1, true); } }, [b.label || T('continue'), icon('chev')]);
          var wrap = el('div', { cls: 'gate blk', id: 'b-' + b.id }, [btn, hint]);
          gates.push({ b: b, btn: btn, hint: hint, hintId: hid, wrap: wrap, above: l.blocks.slice(0, l.blocks.indexOf(b)) });
          box.appendChild(wrap);
        } else box.appendChild(block(b, l, refreshGates));
      });
      segEls.push(box); R.main.appendChild(box);
    });
    endBox.appendChild(lessonNav(i));
    R.main.appendChild(endBox);
    segEls.forEach(function (s, j) { s.hidden = j > open; });
    gates.forEach(function (g, j) { g.wrap.hidden = j !== open; });
    endBox.hidden = open < segs.length - 1;
    refreshGates();
    // dars oxiri ko'rinsa (barcha bo'laklar ochiq) — dars yakunlandi
    var io = null;
    function watchEnd() {
      if (open < segs.length - 1 || S.v[l.id]) return;
      if (!('IntersectionObserver' in W)) { completeLesson(l); return; }
      if (io) return;
      io = new IntersectionObserver(function (es) { if (es.some(function (e) { return e.isIntersecting; })) { completeLesson(l); io.disconnect(); } });
      io.observe(endBox);
      CLEAN.push(function () { io.disconnect(); });
    }
    watchEnd();
    if (blockId) {
      var t = D.getElementById('b-' + blockId), seg = t ? t.closest('.seg') : null;
      setTimeout(function () {
        if (t && seg && !seg.hidden) { t.setAttribute('tabindex', '-1'); t.focus({ preventScroll: true }); t.scrollIntoView({ block: 'start' }); t.classList.add('hit'); }
        else if (gates[open]) { gates[open].btn.focus(); announce("Bu qism «" + (gates[open].b.label || T('continue')) + "» tugmasidan keyin ochiladi"); }
      }, 30);
    }
  }

  // ------------------------------------------------------------------ bloklar
  function done(b, refresh) { if (S.i[b.id]) return; S.i[b.id] = 1; saveSoon(); if (refresh) refresh(); }
  function figure(src, alt, cap, cls) {
    var s = assetUrl(src);
    if (!s) return null;
    return el('figure', { cls: 'fig ' + (cls || '') }, [el('img', { src: s, alt: str(alt), loading: 'lazy' }), cap ? el('figcaption', { text: cap }) : null]);
  }
  function block(b, l, refresh) {
    var f = RENDER[b.type], inner = null;
    try { inner = f ? f(b, l, refresh) : null; } catch (e) { note('blok ' + b.type + ' xato: ' + (e && e.message)); }
    return el('div', { cls: 'blk b-' + b.type + (b.layout ? ' lay-' + b.layout : ''), id: 'b-' + b.id }, inner);
  }
  var RENDER = {
    heading: function (b) { return el(b.level === 3 ? 'h3' : 'h2', { text: b.text }); },
    paragraph: function (b) { return rich(b.html); },
    heading_paragraph: function (b) { return [b.heading ? el('h2', { text: b.heading }) : null, rich(b.html)]; },
    quote: function (b) {
      if (b.style === 'impact') return el('p', { cls: 'impact', text: b.text });
      return el('blockquote', { cls: 'quote' }, [el('p', { text: b.text }), b.cite ? el('cite', { text: '— ' + b.cite }) : null]);
    },
    list: function (b) {
      var items = arr(b.items).filter(function (x) { return plain(x); });
      if (b.style === 'checkbox') return el('ul', { cls: 'checks' }, items.map(function (h, k) {
        var id = b.id + '-c' + k; return el('li', null, [el('input', { type: 'checkbox', id: id }), el('label', { for: id }, [sanitize(h)])]);
      }));
      return el(b.style === 'numbered' ? 'ol' : 'ul', { cls: 'prose lst' }, items.map(function (h) { var li = el('li'); li.appendChild(sanitize(h)); return li; }));
    },
    table: function (b) {
      var rows = arr(b.rows), hd = b.header && rows.length > 1;
      var t = el('table', null, [b.caption ? el('caption', { text: b.caption }) : null,
        hd ? el('thead', null, [el('tr', null, arr(rows[0]).map(function (c) { return el('th', { scope: 'col', text: c }); }))]) : null,
        el('tbody', null, rows.slice(hd ? 1 : 0).map(function (r) { return el('tr', null, arr(r).map(function (c) { return el('td', { text: c }); })); }))]);
      return el('div', { cls: 'tbl', tabindex: '0', role: 'region', 'aria-label': b.caption || 'Jadval' }, [t]);
    },
    image: function (b) { return figure(b.src, b.alt, b.caption, 'lay-' + (b.layout || 'centered')); },
    image_text: function (b) { return el('div', { cls: 'imgtxt side-' + (b.side === 'right' ? 'right' : 'left') }, [figure(b.src, b.alt, ''), rich(b.html)]); },
    gallery: function (b) {
      var items = arr(b.items).filter(function (x) { return assetUrl(x.src); });
      if (b.style !== 'carousel' || items.length < 2) return el('div', { cls: 'gal' }, items.map(function (x) { return figure(x.src, x.alt, x.caption); }));
      var k = 0, stage = el('div', { cls: 'car-stage', 'aria-live': 'polite' }), cnt = el('span', { cls: 'sm muted' });
      function show() { stage.textContent = ''; stage.appendChild(figure(items[k].src, items[k].alt, items[k].caption)); cnt.textContent = (k + 1) + ' / ' + items.length; }
      show();
      return el('div', { cls: 'car', role: 'group', 'aria-roledescription': 'karusel' }, [stage, el('div', { cls: 'car-nav' }, [
        el('button', { cls: 'btn icon', type: 'button', 'aria-label': 'Oldingi rasm', onclick: function () { k = (k + items.length - 1) % items.length; show(); } }, [icon('left')]), cnt,
        el('button', { cls: 'btn icon', type: 'button', 'aria-label': 'Keyingi rasm', onclick: function () { k = (k + 1) % items.length; show(); } }, [icon('right')])])]);
    },
    video: function (b) {
      var out = [];
      if (b.title) out.push(el('h3', { text: b.title }));
      if (b.source === 'youtube') {
        if (!/^[A-Za-z0-9_-]{11}$/.test(str(b.yt_id))) return null;
        out.push(el('div', { cls: 'vid' }, [el('iframe', { src: 'https://www.youtube-nocookie.com/embed/' + b.yt_id + '?rel=0' + (num(b.yt_start, 0) > 0 ? '&start=' + Math.floor(b.yt_start) : ''),
          title: b.title || 'Video', loading: 'lazy', allow: 'accelerometer; encrypted-media; gyroscope; picture-in-picture; fullscreen', allowfullscreen: true, referrerpolicy: 'strict-origin-when-cross-origin' })]));
      } else {
        var src = assetUrl(b.src); if (!src) return null;
        var v = el('video', { controls: true, preload: 'metadata', playsinline: true, src: src, poster: assetUrl(b.poster), crossorigin: opaqueHttp() ? 'anonymous' : null, 'aria-label': b.title || 'Video' },
          arr(b.captions).filter(function (c) { return assetUrl(c.src); }).map(function (c, k) { return el('track', { kind: 'subtitles', src: assetUrl(c.src), srclang: str(c.lang) || 'uz', label: str(c.label) || 'Subtitr', default: k === 0 }); }));
        CLEAN.push(function () { try { v.pause(); } catch (e) { /* jim */ } });
        out.push(el('div', { cls: 'vid file' }, [v]));
      }
      if (b.caption) out.push(el('p', { cls: 'cap', text: b.caption }));
      return out;
    },
    audio: function (b) {
      var src = assetUrl(b.src); if (!src) return null;
      var a = el('audio', { controls: true, preload: 'metadata', src: src, 'aria-label': b.title || 'Audio' });
      CLEAN.push(function () { try { a.pause(); } catch (e) { /* jim */ } });
      return el('div', { cls: 'card aud' }, [b.title ? el('h3', { text: b.title }) : null, a,
        b.transcript ? el('details', null, [el('summary', { text: 'Audio matni' }), el('p', { cls: 'pre', text: b.transcript })]) : null]);
    },
    attachment: function (b) {
      var src = assetUrl(b.src); if (!src) return null;
      return el('a', { cls: 'card att', href: src, download: str(b.name) || true }, [icon('file'), el('span', { cls: 'att-t' }, [el('b', { text: b.title || b.name || 'Fayl' }),
        el('span', { cls: 'sm muted', text: [str(b.ext).toUpperCase(), fmtSize(b.size)].filter(Boolean).join(' · ') + (b.desc ? ' — ' + b.desc : '') })]), icon('down')]);
    },
    labeled_graphic: function (b, l, refresh) {
      var src = assetUrl(b.src); if (!src) return null;
      var ms = arr(b.markers), seen = {}, panel = el('div', { cls: 'lg-panel card', 'aria-live': 'polite', hidden: true }), btns = [];
      var stage = el('div', { cls: 'lg' }, [el('img', { src: src, alt: str(b.alt) })]);
      ms.forEach(function (m, k) {
        var bt = el('button', { type: 'button', cls: 'lg-m', style: 'left:' + clamp(num(m.x, 50), 0, 100) + '%;top:' + clamp(num(m.y, 50), 0, 100) + '%', 'aria-expanded': 'false',
          'aria-label': (k + 1) + '-belgi: ' + (m.title || ''), onclick: function () {
            btns.forEach(function (x) { x.setAttribute('aria-expanded', 'false'); x.classList.remove('on'); });
            bt.setAttribute('aria-expanded', 'true'); bt.classList.add('on');
            panel.hidden = false; panel.textContent = '';
            panel.appendChild(el('h3', { text: (k + 1) + '. ' + (m.title || '') })); panel.appendChild(rich(m.html));
            seen[k] = 1; if (Object.keys(seen).length >= ms.length) done(b, refresh);
          } }, String(k + 1));
        btns.push(bt); stage.appendChild(bt);
      });
      return [stage, panel];
    },
    accordion: function (b, l, refresh) {
      var items = arr(b.items), seen = {};
      return el('div', { cls: 'acc' }, items.map(function (x, k) {
        var pid = b.id + '-p' + k, panel = el('div', { cls: 'acc-p', id: pid, role: 'region', hidden: true }, [rich(x.html)]);
        var btn = el('button', { type: 'button', cls: 'acc-b', 'aria-expanded': 'false', 'aria-controls': pid, onclick: function () {
          var o = btn.getAttribute('aria-expanded') !== 'true'; btn.setAttribute('aria-expanded', String(o)); panel.hidden = !o;
          if (o) { seen[k] = 1; if (Object.keys(seen).length >= items.length) done(b, refresh); }
        } }, [el('span', { text: x.title || (k + 1) + '-bo\'lim' }), icon('chev')]);
        return el('div', { cls: 'acc-i' }, [el('h3', null, [btn]), panel]);
      }));
    },
    tabs: function (b, l, refresh) {
      var items = arr(b.items), seen = {}, tabs = [], panels = [];
      function sel(k, focus) {
        tabs.forEach(function (t, j) { t.setAttribute('aria-selected', String(j === k)); t.tabIndex = j === k ? 0 : -1; panels[j].hidden = j !== k; });
        if (focus) tabs[k].focus();
        seen[k] = 1; if (Object.keys(seen).length >= items.length) done(b, refresh);
      }
      var list = el('div', { cls: 'tabs-l', role: 'tablist' });
      items.forEach(function (x, k) {
        var t = el('button', { type: 'button', role: 'tab', id: b.id + '-t' + k, 'aria-controls': b.id + '-tp' + k, onclick: function () { sel(k); },
          onkeydown: function (e) {
            var n = e.key === 'ArrowRight' ? k + 1 : e.key === 'ArrowLeft' ? k - 1 : e.key === 'Home' ? 0 : e.key === 'End' ? items.length - 1 : null;
            if (n != null) { e.preventDefault(); sel((n + items.length) % items.length, true); }
          } }, x.title || (k + 1) + '-yorliq');
        tabs.push(t); list.appendChild(t);
        panels.push(el('div', { role: 'tabpanel', id: b.id + '-tp' + k, 'aria-labelledby': b.id + '-t' + k, tabindex: '0', cls: 'tab-p' }, [rich(x.html)]));
      });
      if (items.length) sel(0);
      return el('div', { cls: 'tabs' }, [list].concat(panels));
    },
    flashcards: function (b, l, refresh) {
      var cards = arr(b.cards), seen = {};
      function card(c, k) {
        var btn = el('button', { type: 'button', cls: 'fc', 'aria-pressed': 'false', onclick: function () {
          var o = btn.getAttribute('aria-pressed') !== 'true'; btn.setAttribute('aria-pressed', String(o)); btn.classList.toggle('flip', o);
          seen[k] = 1; if (Object.keys(seen).length >= cards.length) done(b, refresh);
        } }, [el('span', { cls: 'fc-in' }, [el('span', { cls: 'fc-f' }, [el('span', { text: c.front })]), el('span', { cls: 'fc-b' }, [el('span', { text: c.back })])]),
          el('span', { cls: 'sr', text: ' — kartochkani aylantirish' })]);
        return btn;
      }
      if (b.style !== 'stack' || cards.length < 2) return el('div', { cls: 'fc-grid' }, cards.map(card));
      var k = 0, stage = el('div', { cls: 'fc-stack', 'aria-live': 'polite' }), cnt = el('span', { cls: 'sm muted' });
      function show() { stage.textContent = ''; stage.appendChild(card(cards[k], k)); cnt.textContent = (k + 1) + ' / ' + cards.length; }
      show();
      return [stage, el('div', { cls: 'car-nav' }, [el('button', { cls: 'btn icon', type: 'button', 'aria-label': 'Oldingi kartochka', onclick: function () { k = (k + cards.length - 1) % cards.length; show(); } }, [icon('left')]), cnt,
        el('button', { cls: 'btn icon', type: 'button', 'aria-label': 'Keyingi kartochka', onclick: function () { k = (k + 1) % cards.length; show(); } }, [icon('right')])])];
    },
    process: function (b, l, refresh) {
      var items = arr(b.items), k = 0, body = el('div', { cls: 'proc-b', 'aria-live': 'polite' }), cnt = el('span', { cls: 'sm muted' });
      var prev = el('button', { cls: 'btn ghost', type: 'button', onclick: function () { show(k - 1); } }, [icon('left'), 'Oldingi']);
      var next = el('button', { cls: 'btn primary', type: 'button', onclick: function () { show(k + 1); } }, ['Keyingi qadam', icon('right')]);
      function show(n) {
        k = clamp(n, 0, items.length - 1); body.textContent = '';
        body.appendChild(el('p', { cls: 'eyebrow', text: 'Qadam ' + (k + 1) + ' / ' + items.length }));
        body.appendChild(el('h3', { text: items[k].title })); body.appendChild(rich(items[k].html));
        prev.disabled = k === 0; next.disabled = k >= items.length - 1; cnt.textContent = (k + 1) + ' / ' + items.length;
        if (k >= items.length - 1) done(b, refresh);
      }
      if (!items.length) return null;
      show(0);
      return el('div', { cls: 'card proc' }, [el('div', { cls: 'dots', 'aria-hidden': 'true' }, items.map(function () { return el('i'); })), body, el('div', { cls: 'proc-n' }, [prev, cnt, next])]);
    },
    timeline: function (b) {
      return el('ol', { cls: 'tl' }, arr(b.items).map(function (x) { return el('li', null, [el('span', { cls: 'tl-d', text: x.date }), el('div', { cls: 'tl-c' }, [x.title ? el('h3', { text: x.title }) : null, rich(x.html)])]); }));
    },
    sorting: function (b, l, refresh) {
      var cats = arr(b.categories), items = arr(b.items), place = items.map(function () { return -1; }), pick = -1, checked = false;
      var order = shuffled(items.length), fb = el('p', { cls: 'fb', 'aria-live': 'polite' });
      var pool = el('div', { cls: 'sort-pool', 'aria-label': 'Joylashtirilmagan elementlar' }), zones = [];
      var chk = el('button', { cls: 'btn primary', type: 'button', onclick: check }, 'Tekshirish');
      var again = el('button', { cls: 'btn ghost', type: 'button', hidden: true, onclick: function () { place = place.map(function (c, k) { return c >= 0 && items[k].cat === c ? c : -1; }); checked = false; paint(); } }, [icon('restart'), T('retry')]);
      function chip(k) {
        var ok = checked && place[k] >= 0 ? items[k].cat === place[k] : null;
        return el('button', { type: 'button', cls: 's-card' + (pick === k ? ' on' : '') + (ok === true ? ' ok' : ok === false ? ' bad' : ''), 'aria-pressed': String(pick === k), disabled: checked && ok === true,
          onclick: function () { if (place[k] >= 0 && pick !== k) { place[k] = -1; pick = k; } else pick = pick === k ? -1 : k; paint(); } },
          [items[k].text, ok === true ? icon('check') : ok === false ? icon('x') : null]);
      }
      function paint() {
        pool.textContent = '';
        order.forEach(function (k) { if (place[k] < 0) pool.appendChild(chip(k)); });
        if (!pool.childNodes.length) pool.appendChild(el('span', { cls: 'sm muted', text: 'Hamma elementlar joylashtirildi' }));
        zones.forEach(function (z, c) { z.list.textContent = ''; order.forEach(function (k) { if (place[k] === c) z.list.appendChild(chip(k)); }); z.btn.disabled = pick < 0; });
        chk.disabled = place.some(function (c) { return c < 0; }) || checked;
        again.hidden = !checked || place.every(function (c, k) { return items[k].cat === c; });
      }
      function check() {
        checked = true;
        var good = place.filter(function (c, k) { return items[k].cat === c; }).length;
        fb.textContent = good === items.length ? T('correct') + '! Hamma elementlar to\'g\'ri joylashtirildi.' : good + ' / ' + items.length + " to'g'ri. Noto'g'rilarini qayta joylashtiring.";
        fb.className = 'fb ' + (good === items.length ? 'ok' : 'bad');
        if (good === items.length) done(b, refresh);
        paint();
      }
      var grid = el('div', { cls: 'sort-z' }, cats.map(function (c, ci) {
        var list = el('div', { cls: 's-list' }), btn = el('button', { type: 'button', cls: 'btn ghost sm', onclick: function () { if (pick >= 0) { place[pick] = ci; pick = -1; checked = false; fb.textContent = ''; paint(); } } }, ['Shu yerga joylash', icon('plus')]);
        zones.push({ list: list, btn: btn });
        return el('div', { cls: 's-zone', role: 'group', 'aria-label': c }, [el('h3', { text: c }), list, btn]);
      }));
      paint();
      return el('div', { cls: 'card sort' }, [b.title ? el('h3', { text: b.title }) : null, el('p', { cls: 'sm muted', text: 'Elementni tanlang, keyin tegishli toifadagi «Shu yerga joylash» tugmasini bosing.' }),
        pool, grid, el('div', { cls: 'acts' }, [chk, again]), fb]);
    },
    matching: function (b, l, refresh) {
      var pairs = arr(b.pairs), rights = shuffled(pairs.length), sels = [], fb = el('p', { cls: 'fb', 'aria-live': 'polite' }), marks = [];
      var rows = pairs.map(function (p, k) {
        var s = el('select', { id: b.id + '-m' + k, onchange: function () { fb.textContent = ''; marks[k].textContent = ''; s.classList.remove('ok', 'bad'); } },
          [el('option', { value: '', text: '— tanlang —' })].concat(rights.map(function (r) { return el('option', { value: String(r), text: pairs[r].right }); })));
        sels.push(s); marks.push(el('span', { cls: 'mk' }));
        return el('div', { cls: 'm-row' }, [el('label', { for: s.id, text: p.left }), s, marks[k]]);
      });
      var chk = el('button', { cls: 'btn primary', type: 'button', onclick: function () {
        var good = 0;
        sels.forEach(function (s, k) {
          var v = s.value === '' ? -1 : +s.value, ok = v >= 0 && (v === k || normAns(pairs[v].right) === normAns(pairs[k].right));
          if (ok) good++;
          s.classList.toggle('ok', ok); s.classList.toggle('bad', !ok);
          marks[k].textContent = ''; marks[k].appendChild(icon(ok ? 'check' : 'x')); marks[k].appendChild(el('span', { cls: 'sr', text: ok ? T('correct') : T('incorrect') }));
        });
        fb.textContent = good === pairs.length ? T('correct') + '! Hamma juftlar mos.' : good + ' / ' + pairs.length + " to'g'ri. Noto'g'rilarini o'zgartirib qayta tekshiring.";
        fb.className = 'fb ' + (good === pairs.length ? 'ok' : 'bad');
        if (good === pairs.length) done(b, refresh);
      } }, 'Tekshirish');
      return el('div', { cls: 'card match' }, [b.title ? el('h3', { text: b.title }) : null].concat(rows, [el('div', { cls: 'acts' }, [chk]), fb]));
    },
    knowledge: function (b, l, refresh) { var box = el('div', { cls: 'card kc' }); kcView(b, l, box, refresh); return box; },
    divider: function (b) { return b.style === 'space' ? el('div', { cls: 'space' }) : b.style === 'dots' ? el('div', { cls: 'dots-d', 'aria-hidden': 'true', text: '• • •' }) : el('hr'); },
    button: function (b) {
      var u = httpUrl(b.url); if (!u) return null;
      return el('div', { cls: 'card btnb' }, [b.text ? el('p', { text: b.text }) : null,
        el('a', { cls: 'btn primary', href: u, target: '_blank', rel: 'noopener noreferrer' }, [b.label || 'Ochish', icon('ext'), el('span', { cls: 'sr', text: ' (yangi oynada)' })])]);
    }
  };

  // ------------------------------------------------------------------ savol (bilimni tekshirish va test): javob shakli — asl indekslar yoki matn
  function qForm(q, order, name, initial, onChange) {
    var fs = el('fieldset', { cls: 'q' }, [el('legend', { text: q.question })]);
    if (q.kind === 'fill') {
      var inp = el('input', { type: 'text', cls: 'fill', id: name, autocomplete: 'off', 'aria-label': 'Javobingiz', oninput: function () { onChange(inp.value); } });
      if (initial != null) inp.value = str(initial);
      fs.appendChild(inp);
      return { el: fs, value: function () { return inp.value; }, lock: function () { inp.disabled = true; } };
    }
    var multi = q.kind === 'multiple', inputs = [];
    if (multi) fs.appendChild(el('p', { cls: 'sm muted', text: "Bir nechta to'g'ri javob bo'lishi mumkin" }));
    order.forEach(function (ai) {
      var a = q.answers[ai], id = name + '-' + ai;
      var x = el('input', { type: multi ? 'checkbox' : 'radio', name: name, id: id, value: String(ai), onchange: function () { onChange(val()); } });
      if (initial && arr(initial).indexOf(ai) >= 0) x.checked = true;
      inputs.push(x);
      fs.appendChild(el('div', { cls: 'opt', 'data-ai': String(ai) }, [x, el('label', { for: id, text: a.text })]));
    });
    function val() { return inputs.filter(function (x) { return x.checked; }).map(function (x) { return +x.value; }); }
    return { el: fs, value: val, lock: function () { inputs.forEach(function (x) { x.disabled = true; }); } };
  }
  function answered(v) { return Array.isArray(v) ? v.length > 0 : str(v).trim().length > 0; }
  function markAnswers(q, form, resp, showCorrect) {   // tanlangan / to'g'ri variantlar belgisi va har javob izohi
    Array.prototype.forEach.call(form.el.querySelectorAll('.opt'), function (o) {
      var ai = +o.getAttribute('data-ai'), a = q.answers[ai], mine = arr(resp).indexOf(ai) >= 0;
      if (mine) o.classList.add(a.correct ? 'ok' : 'bad');
      if (showCorrect && a.correct) o.classList.add('right');
      if ((mine || (showCorrect && a.correct)) && !o.querySelector('.ic')) o.appendChild(icon(a.correct ? 'check' : 'x'));
      if (mine && a.feedback) o.appendChild(el('p', { cls: 'afb', text: a.feedback }));
    });
  }
  function interaction(q, resp, ok, lessonId, qid) {   // SCORM 1.2 / 2004 / xAPI interaction (choice id — ASL tartibdagi harflar)
    var it = { id: cmiId(lessonId + '_' + qid), block: lessonId, qid: qid, ok: ok, neutral: false, when: new Date(), title: str(q.question).slice(0, 120), desc: str(q.question).slice(0, 250), choices: [] };
    if (q.kind === 'fill') {
      var alts = arr(q.accept);
      it.type = 'fill-in'; it.r12 = it.r04 = it.rX = str(resp).slice(0, 250);
      it.c12 = alts; it.c04 = alts.map(function (x) { return '{case_matters=false}' + x; }); it.cX = alts;
    } else if (q.kind === 'truefalse') {
      var tv = arr(resp).length ? arr(resp)[0] === 0 : null, cv = !!(q.answers[0] && q.answers[0].correct);
      it.type = 'true-false'; it.r12 = tv == null ? '' : tv ? 't' : 'f'; it.r04 = it.rX = tv == null ? '' : String(tv); it.c12 = [cv ? 't' : 'f']; it.c04 = it.cX = [String(cv)];
    } else {
      var corr = []; q.answers.forEach(function (a, k) { if (a.correct) corr.push(k); });
      var mine = arr(resp).slice().sort(function (x, y) { return x - y; });
      it.type = 'choice'; it.choices = q.answers.map(function (a) { return a.text; });
      it.r12 = mine.map(letter).join(','); it.r04 = it.rX = mine.map(letter).join('[,]');
      it.c12 = [corr.map(letter).join(',')]; it.c04 = it.cX = [corr.map(letter).join('[,]')];
    }
    try { tracker.interaction(it); } catch (e) { note('interaction xato'); }
  }
  function kcView(b, l, box, refresh) {
    box.textContent = '';
    var st = S.k[b.id], order = b.kind === 'truefalse' || b.kind === 'fill' ? ident(arr(b.answers).length) : shuffled(arr(b.answers).length);
    box.appendChild(el('p', { cls: 'eyebrow', text: 'Bilimni tekshirish' }));
    var form = qForm(b, order, 'k' + b.id, st ? st.a : null, function (v) { sub.disabled = !answered(v); });
    var fb = el('div', { cls: 'fbx', 'aria-live': 'polite' });
    var sub = el('button', { cls: 'btn primary', type: 'button', disabled: true, onclick: function () {
      var resp = form.value(), ok = grade(b, resp);
      S.k[b.id] = { a: resp, ok: ok ? 1 : 0 };
      interaction(b, resp, ok, l.id, b.id);
      done(b, refresh); saveSoon(); result(resp, ok, true);
    } }, T('submit'));
    box.appendChild(form.el); box.appendChild(el('div', { cls: 'acts' }, [sub])); box.appendChild(fb);
    function result(resp, ok, fresh) {
      form.lock(); sub.hidden = true;
      markAnswers(b, form, resp, true);
      fb.textContent = '';
      fb.className = 'fbx ' + (ok ? 'ok' : 'bad');
      fb.appendChild(el('p', { cls: 'fb-h' }, [icon(ok ? 'check' : 'x'), ok ? T('correct') : T('incorrect')]));
      var t = ok ? b.feedback_correct : b.feedback_wrong; if (t) fb.appendChild(el('p', { text: t }));
      if (!ok && b.kind === 'fill' && arr(b.accept).length) fb.appendChild(el('p', { cls: 'sm', text: "To'g'ri javob: " + b.accept[0] }));
      if (b.retry !== false) fb.appendChild(el('button', { cls: 'btn ghost sm', type: 'button', onclick: function () { delete S.k[b.id]; saveSoon(); kcView(b, l, box, refresh); box.querySelector('input').focus(); } }, [icon('restart'), T('retry')]));
      if (fresh) announce(ok ? T('correct') : T('incorrect'));
    }
    if (st && st.a != null) result(st.a, !!st.ok, false);
  }

  // ------------------------------------------------------------------ test darsi
  function renderQuiz(l) {
    var i = LS.indexOf(l), q = qst(l), Q = l.quiz, att = clamp(num(Q.attempts, 0), 0, 99), pp = passPct(l);
    var nq = Q.draw > 0 ? Math.min(Q.draw, l.questions.length) : l.questions.length;
    var box = el('div', { cls: 'quiz' });
    R.main.appendChild(el('header', { cls: 'les-h' }, [C.settings.lesson_count !== false ? el('p', { cls: 'eyebrow', text: T('lesson') + ' ' + (i + 1) + ' / ' + LS.length }) : null,
      el('h1', { tabindex: '-1', text: l.title })]));
    R.main.appendChild(box);
    if (q.n > 0) quizResult(l, box, false); else quizStart(l, box);
    R.main.appendChild(el('div', { cls: 'les-end' }, [lessonNav(i)]));
    function quizStart() {
      box.textContent = '';
      box.appendChild(el('div', { cls: 'card qz-start' }, [el('span', { cls: 'qz-ic' }, [icon('quiz')]),
        Q.intro ? el('p', { text: Q.intro }) : null,
        el('ul', { cls: 'facts' }, [el('li', null, [el('b', { text: String(nq) }), ' ta savol']), el('li', null, ["O'tish bali: ", el('b', { text: pp + '%' })]),
          el('li', null, ['Urinishlar: ', el('b', { text: att ? String(att) : 'cheklanmagan' })])]),
        el('button', { cls: 'btn primary lg', type: 'button', disabled: !l.questions.length, onclick: function () { attempt(l, box); } }, [T('quiz_start'), icon('right')])]));
    }
  }
  function attempt(l, box) {
    var Q = l.quiz, qs = l.questions, idx = Q.randomize || Q.draw > 0 ? shuffled(qs.length) : ident(qs.length);
    if (Q.draw > 0) idx = idx.slice(0, Math.min(Q.draw, qs.length));
    if (!Q.randomize) idx.sort(function (a, b) { return a - b; });
    var resp = {}, k = 0, reveal = Q.reveal || 'always';
    function screen() {
      box.textContent = '';
      var qq = qs[idx[k]], order = qq.kind === 'truefalse' || qq.kind === 'fill' || Q.shuffle === false ? ident(arr(qq.answers).length) : shuffled(arr(qq.answers).length);
      var form = qForm(qq, order, 'q' + qq.id + '-' + k, null, function (v) { btn.disabled = !answered(v); });
      var fb = el('div', { cls: 'fbx', 'aria-live': 'polite' }), last = k === idx.length - 1, checked = false;
      var btn = el('button', { cls: 'btn primary', type: 'button', disabled: true, onclick: function () {
        if (!checked) {
          resp[qq.id] = form.value(); form.lock(); checked = true;
          if (reveal === 'always') {
            var ok = grade(qq, resp[qq.id]);
            markAnswers(qq, form, resp[qq.id], true);
            fb.className = 'fbx ' + (ok ? 'ok' : 'bad');
            fb.appendChild(el('p', { cls: 'fb-h' }, [icon(ok ? 'check' : 'x'), ok ? T('correct') : T('incorrect')]));
            var t = ok ? qq.feedback_correct : qq.feedback_wrong; if (t) fb.appendChild(el('p', { text: t }));
            announce(ok ? T('correct') : T('incorrect'));
          } else { fb.appendChild(el('p', { cls: 'sm muted', text: 'Javob qabul qilindi' })); }
          btn.textContent = last ? T('result') : T('next_question');
          btn.focus();
          if (reveal !== 'always') { btn.click(); }
          return;
        }
        if (last) finish(); else { k++; screen(); }
      } }, T('submit'));
      box.appendChild(el('div', { cls: 'card qz' }, [el('div', { cls: 'qz-top' }, [el('span', { cls: 'eyebrow', text: (k + 1) + ' / ' + idx.length }),
        el('div', { cls: 'meter' }, [el('span', { style: 'width:' + Math.round(100 * k / idx.length) + '%' })])]), form.el, fb, el('div', { cls: 'acts' }, [btn])]));
      var f = form.el.querySelector('input'); if (f) f.focus({ preventScroll: true });
    }
    function finish() {
      var picked = idx.map(function (j) { return qs[j]; }), good = 0;
      picked.forEach(function (qq) { var ok = grade(qq, resp[qq.id]); if (ok) good++; interaction(qq, resp[qq.id], ok, l.id, qq.id); });
      var pct = picked.length ? Math.round(100 * good / picked.length) : 0, passed = pct >= passPct(l), st = qst(l);
      st.n = (st.n || 0) + 1; st.s = pct; st.b = Math.max(num(st.b, 0), pct);
      if (passed) st.p = 1;
      st.a = picked.map(function (qq) { return [qq.id, resp[qq.id]]; });
      if (tracker.quizResult) tracker.quizResult({ id: l.id, title: l.title }, { pct: pct, passed: passed });
      if (tracker.done) tracker.done({ id: l.id, type: 'quiz', title: l.title });
      paintNav(); report(true);
      emit(passed ? 'passed' : 'failed', null, { lesson_id: l.id, pct: pct });
      quizResult(l, box, true);
    }
    screen();
  }
  function quizResult(l, box, fresh) {
    var st = qst(l), Q = l.quiz, att = clamp(num(Q.attempts, 0), 0, 99), pp = passPct(l), passed = !!st.p;
    var shown = passed ? num(st.b, st.s) : num(st.s, 0);
    var canRetry = !passed && (att === 0 || st.n < att), reveal = Q.reveal || 'always';
    box.textContent = '';
    var head = el('h2', { tabindex: '-1', cls: 'score-h', text: T('result') + ': ' + shown + '%' });
    var card = el('div', { cls: 'card qz-res ' + (passed ? 'pass' : 'fail') }, [
      el('div', { cls: 'ring', style: '--p:' + shown, 'aria-hidden': 'true' }, [el('span', { text: shown + '%' })]), head,
      el('p', { cls: 'res-st', text: passed ? T('passed') : T('failed') }),
      el('p', { cls: 'sm muted', text: "O'tish bali " + pp + '% · urinish: ' + st.n + (att ? ' / ' + att : '') + (st.b != null && st.b !== shown ? ' · eng yaxshi natija ' + st.b + '%' : '') })]);
    var acts = el('div', { cls: 'acts' });
    if (canRetry) acts.appendChild(el('button', { cls: 'btn primary', type: 'button', onclick: function () { attempt(l, box); } }, [icon('restart'), T('retry')]));
    if (!passed && !canRetry) acts.appendChild(el('p', { cls: 'sm muted', text: 'Urinishlar tugadi.' }));
    card.appendChild(acts);
    box.appendChild(card);
    if ((reveal === 'always' || (reveal === 'pass' && passed)) && arr(st.a).length) {
      var rv = el('ol', { cls: 'review' });
      arr(st.a).forEach(function (p) {
        var qq = l.questions.filter(function (x) { return x.id === p[0]; })[0]; if (!qq) return;
        var ok = grade(qq, p[1]), right = qq.kind === 'fill' ? arr(qq.accept).join(' / ') : qq.answers.filter(function (a) { return a.correct; }).map(function (a) { return a.text; }).join('; ');
        var mine = qq.kind === 'fill' ? str(p[1]) : arr(p[1]).map(function (ai) { return (qq.answers[ai] || {}).text; }).filter(Boolean).join('; ');
        rv.appendChild(el('li', { cls: ok ? 'ok' : 'bad' }, [el('p', { cls: 'rq' }, [icon(ok ? 'check' : 'x'), qq.question]),
          el('p', { cls: 'sm', text: 'Sizning javobingiz: ' + (mine || '—') }), ok ? null : el('p', { cls: 'sm', text: "To'g'ri javob: " + right })]));
      });
      box.appendChild(el('details', { cls: 'card' }, [el('summary', { text: 'Javoblarni ko\'rish' }), rv]));
    }
    if (fresh) { head.focus({ preventScroll: false }); announce((passed ? T('passed') : T('failed')) + '. ' + T('result') + ' ' + shown + '%'); }
  }

  // ------------------------------------------------------------------ ishga tushirish
  function pickTracker() {
    var m = C.tracking.mode, opts = { unit: 'lesson', prefix: 'isft-kurs:' };
    if (m === 'none') return LMS.Preview(C, opts);
    var lp = LMS.launchParams();
    var a12 = function () { var a = LMS.findAPI('API'); return a ? LMS.Scorm12(a) : null; };
    var a04 = function () { var a = LMS.findAPI('API_1484_11'); return a ? LMS.Scorm2004(a) : null; };
    var ax = function () { return lp && lp.actor ? LMS.Xapi(lp, C, opts) : null; };
    var order = m === 'scorm2004' ? [a04, a12, ax] : m === 'xapi' ? [ax, a04, a12] : [a12, a04, ax];
    if (lp && lp.actor) order = [ax].concat(order);
    for (var k = 0; k < order.length; k++) { var t = order[k](); if (t) return t; }
    return LMS.Preview(C, opts);
  }
  function exit() { if (finished || !tracker) return; finished = true; cleanup(); save(false); tracker.finish(Date.now() - t0, status()); }
  function fromHash() {
    var h = str(W.location.hash).replace(/^#/, ''), m = /(?:^|&)lesson=([a-z0-9]{6,24})(?:&|$)/.exec(h), bm = /(?:^|&)block=([a-z0-9]{6,24})(?:&|$)/.exec(h);
    if (!m) return null;
    for (var k = 0; k < LS.length; k++) if (LS[k].id === m[1]) return { i: k, b: bm ? bm[1] : null };
    return null;
  }
  function start() {
    tracker = pickTracker();
    Promise.resolve(tracker.init()).then(function (info) {
      if (!info) { tracker = LMS.Preview(C, { unit: 'lesson', prefix: 'isft-kurs:' }); info = tracker.init(); }
      NS.mode = tracker.kind; previewMode = !!tracker.preview;
      lmsMastery = info.mastery != null ? info.mastery : null;
      var st = LMS.decodeState(info.state);
      if (st && st.h === S.h) { S = st; ['v', 'g', 'i', 'k', 'q'].forEach(function (k) { S[k] = obj(S[k]); }); S.c = num(S.c, -1); }
      build();
      lastCompl = status().complete;
      var hv = fromHash();
      if (hv) go(hv.i, hv.b, true); else go(-1, null, true);
      W.addEventListener('hashchange', function () { var x = fromHash(); if (x) go(x.i, x.b); });
      W.addEventListener('pagehide', exit); W.addEventListener('beforeunload', exit);
      D.addEventListener('visibilitychange', function () { if (D.visibilityState === 'hidden' && !finished) { save(true); if (tracker.flush) tracker.flush(); } });
      NS.ready = true;
      try { W.dispatchEvent(new CustomEvent('isftkurs:ready')); } catch (e) { /* eski brauzer */ }
    }).catch(function (e) { note('init xato: ' + (e && e.message)); });
  }
  NS.grade = grade; NS.normAns = normAns;
  NS.state = function () { return S; }; NS.status = function () { return status(); }; NS.go = function (i, b) { go(i, b); }; NS.exit = exit;
  NS.debug = { sanitize: function (h) { var d = el('div'); d.appendChild(sanitize(h)); return d.innerHTML; }, current: function () { return cur; } };
  start();
})(window, document);
