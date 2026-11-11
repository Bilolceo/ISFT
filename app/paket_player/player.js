/* ISFT Core — o'quv paket pleyeri (Articulate o'rnini bosuvchi).
 * Bitta fayl, tashqi kutubxonasiz. Kontent: window.PAKET (content.js). Global nom: faqat window.ISFTPaket.
 * Kuzatuv rejimlari: SCORM 1.2 (window.API), SCORM 2004 4-nashr (window.API_1484_11), xAPI (TinCan launch parametrlari),
 * ko'rish rejimi (LMS yo'q yoki tracking.mode = "none" — holat localStorage'da).
 * Ball siyosati: LMS'ga OXIRGI urinish natijasi yuboriladi (eng yaxshisi faqat pleyer ichida ko'rsatiladi);
 * test o'tilgandan keyin qayta urinish berilmaydi (o'tgan natija tasodifan pasaymasin) va LMS'dagi «passed» holati
 * (SCORM 1.2 lesson_status, SCORM 2004 success_status, xAPI kurs natijasi) hech qachon «failed»/boshqasiga tushirilmaydi.
 */
(function (W, D) {
  'use strict';
  var NS = W.ISFTPaket = { version: '1.0.0', ready: false, mode: null, log: [] };
  var RAW = W.PAKET;

  // ------------------------------------------------------------------ yordamchilar
  function note(msg) { NS.log.push(new Date().toISOString().slice(11, 19) + ' ' + msg); if (NS.log.length > 200) NS.log.shift(); }
  function str(v, d) { return v == null ? (d || '') : String(v); }
  function arr(v) { return Array.isArray(v) ? v : []; }
  function num(v, d) { var n = Number(v); return isFinite(n) ? n : d; }
  function clamp(n, a, b) { return Math.max(a, Math.min(b, n)); }
  function pad(n, w) { n = String(n); while (n.length < w) n = '0' + n; return n; }
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
  function icon(name) {   // statik SVG (kontentdan emas)
    var s = el('span', { cls: 'ic', 'aria-hidden': 'true' });
    s.innerHTML = '<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">' + (ICONS[name] || '') + '</svg>';
    return s;
  }
  var ICONS = {
    plan: '<path d="M9 6h11M9 12h11M9 18h11"/><path d="M4 6h.01M4 12h.01M4 18h.01"/>',
    text: '<path d="M4 4h12l4 4v12H4z"/><path d="M8 11h8M8 15h8M8 7h5"/>',
    slides: '<rect x="3" y="4" width="18" height="12" rx="2"/><path d="M12 16v4M8 20h8"/>',
    video: '<rect x="3" y="5" width="18" height="14" rx="3"/><path d="M10 9l5 3-5 3z"/>',
    file: '<path d="M14 3H6v18h12V7z"/><path d="M14 3v4h4M12 11v6M9 14l3 3 3-3"/>',
    quiz: '<circle cx="12" cy="12" r="9"/><path d="M9.5 9.5a2.5 2.5 0 1 1 3.5 2.3c-.6.3-1 .9-1 1.6v.6M12 17h.01"/>',
    check: '<path d="M5 12l5 5 9-10"/>', x: '<path d="M6 6l12 12M18 6L6 18"/>',
    left: '<path d="M15 6l-6 6 6 6"/>', right: '<path d="M9 6l6 6-6 6"/>', menu: '<path d="M4 7h16M4 12h16M4 17h16"/>',
    ext: '<path d="M14 4h6v6M20 4l-9 9M18 14v6H4V6h6"/>', down: '<path d="M12 4v12M7 11l5 5 5-5M5 20h14"/>',
    print: '<path d="M7 9V3h10v6M7 18H4v-8h16v8h-3"/><path d="M7 14h10v7H7z"/>', notes: '<path d="M5 4h14v16H5z"/><path d="M9 9h6M9 13h6"/>'
  };
  var TYPE_LABEL = { plan: 'Reja', text: "Ma'ruza", slides: 'Taqdimot', video: 'Video', file: 'Fayl', quiz: 'Test' };
  var KNOWN = { plan: 1, text: 1, slides: 1, video: 1, file: 1, quiz: 1 };

  // Nisbiy, xavfsiz manzil (paket ichidagi fayl): boshqaruv belgilari olib tashlanadi («java\tscript:» kabi aylanib o'tishlar),
  // keyin faqat oq ro'yxat belgilari — sxema (":"), "/" bilan boshlanish, "\\", ".." yo'q
  function assetUrl(p) {
    p = str(p).replace(/[\x00-\x20\x7f]/g, '');
    return p && /^(?!\/)(?!.*\.\.)[A-Za-z0-9_\-.\/%]+$/.test(p) ? p : null;
  }
  function httpUrl(u) { u = str(u).replace(/^[\x00-\x20\x7f]+|[\x00-\x20\x7f]+$/g, ''); return /^https?:\/\/[^\s"'<>\\]+$/i.test(u) ? u : null; }
  function norm(s) {   // fill-in va reja sarlavhalarini taqqoslash: katta-kichik harf, bo'shliq, apostrof variantlari
    return str(s).replace(/[‘’ʻʼ`´′]/g, "'").replace(/\s+/g, ' ').trim().toLocaleLowerCase('uz').replace(/[.!?;:,]+$/, '');
  }
  function hash(s) { var h = 2166136261; s = str(s); for (var i = 0; i < s.length; i++) { h ^= s.charCodeAt(i); h = Math.imul(h, 16777619); } return h >>> 0; }
  function rng(seed) { var a = seed >>> 0; return function () { a = (a + 0x6D2B79F5) >>> 0; var t = a; t = Math.imul(t ^ (t >>> 15), t | 1); t ^= t + Math.imul(t ^ (t >>> 7), t | 61); return ((t ^ (t >>> 14)) >>> 0) / 4294967296; }; }
  function shuffled(n, rand) { var a = [], i, j, t; for (i = 0; i < n; i++) a.push(i); for (i = n - 1; i > 0; i--) { j = Math.floor(rand() * (i + 1)); t = a[i]; a[i] = a[j]; a[j] = t; } return a; }
  function uuid() {
    var b = new Uint8Array(16); (W.crypto && W.crypto.getRandomValues) ? W.crypto.getRandomValues(b) : b.forEach(function (_, i) { b[i] = Math.random() * 256; });
    b[6] = (b[6] & 15) | 64; b[8] = (b[8] & 63) | 128;
    var h = Array.prototype.map.call(b, function (x) { return pad(x.toString(16), 2); }).join('');
    return h.slice(0, 8) + '-' + h.slice(8, 12) + '-' + h.slice(12, 16) + '-' + h.slice(16, 20) + '-' + h.slice(20);
  }
  function fmtSize(n) { n = num(n, 0); if (!n) return ''; return n < 1024 ? n + ' B' : n < 1048576 ? Math.round(n / 1024) + ' KB' : (n / 1048576).toFixed(1) + ' MB'; }
  function cmiId(s) { return str(s).replace(/[^A-Za-z0-9_\-.]/g, '_').slice(0, 250) || 'x'; }
  function letter(i) { return 'abcdefghijklmnopqrstuvwxyz'.charAt(i) || String(i); }

  // Vaqt formatlari
  function time12(ms) {   // CMITimespan: HHHH:MM:SS.SS (soat 2–4 xona)
    var cs = Math.max(0, Math.round(ms / 10)), h = Math.min(9999, Math.floor(cs / 360000)), m = Math.floor(cs / 6000) % 60, s = Math.floor(cs / 100) % 60;
    return pad(h, 2) + ':' + pad(m, 2) + ':' + pad(s, 2) + '.' + pad(cs % 100, 2);
  }
  function iso8601(ms) {  // PT#H#M#S
    var cs = Math.max(0, Math.round(ms / 10)), h = Math.floor(cs / 360000), m = Math.floor(cs / 6000) % 60, s = (cs % 6000) / 100;
    return 'PT' + h + 'H' + m + 'M' + (Math.round(s * 100) / 100) + 'S';
  }
  function clock12(d) { return pad(d.getHours(), 2) + ':' + pad(d.getMinutes(), 2) + ':' + pad(d.getSeconds(), 2); }
  function stamp2004(d) { return d.toISOString().slice(0, 22) + 'Z'; }  // YYYY-MM-DDThh:mm:ss.ssZ

  // ------------------------------------------------------------------ HTML sanitizer (server tozalaganidan keyin ikkinchi qatlam)
  var ALLOW = {
    p: [], br: [], hr: [], h2: [], h3: [], h4: [], h5: [], h6: [], ul: [], ol: ['start'], li: [], strong: [], b: [], em: [], i: [], u: [], s: [],
    sub: [], sup: [], mark: [], small: [], blockquote: [], pre: [], code: [], span: [], div: [], figure: [], figcaption: [],
    table: [], caption: [], thead: [], tbody: [], tfoot: [], tr: [], th: ['colspan', 'rowspan', 'scope'], td: ['colspan', 'rowspan'],
    a: ['href', 'title'], img: ['src', 'alt', 'width', 'height', 'title'], dl: [], dt: [], dd: []
  };
  var DROP = { script: 1, style: 1, iframe: 1, object: 1, embed: 1, noscript: 1, template: 1, svg: 1, math: 1, form: 1, input: 1, button: 1, select: 1, textarea: 1, link: 1, meta: 1, base: 1, frame: 1, frameset: 1, audio: 1, video: 1, source: 1, canvas: 1, title: 1, head: 1 };
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
        if (!ALLOW[tag]) { walk(n, dst); return; }          // noma'lum teg — ochiladi, matni qoladi
        var out = D.createElement(tag);
        ALLOW[tag].forEach(function (a) {
          var v = n.getAttribute(a); if (v == null) return;
          if (a === 'href') {
            var u = httpUrl(v); if (!u) return;
            out.setAttribute('href', u); out.setAttribute('target', '_blank'); out.setAttribute('rel', 'noopener noreferrer');
          } else if (a === 'src') { var s = assetUrl(v); if (s) out.setAttribute('src', s); }
          else if (/^(colspan|rowspan|start|width|height)$/.test(a)) { if (/^\d{1,4}$/.test(v)) out.setAttribute(a, v); }
          else if (a === 'scope') { if (/^(row|col|rowgroup|colgroup)$/.test(v)) out.setAttribute(a, v); }
          else out.setAttribute(a, v.slice(0, 300));
        });
        if (tag === 'a' && !out.getAttribute('href')) { walk(n, dst); return; }   // xavfli/bo'sh havola — faqat matni qoladi
        if (tag === 'img') { if (!out.getAttribute('src')) return; if (!out.hasAttribute('alt')) out.setAttribute('alt', ''); out.setAttribute('loading', 'lazy'); }
        if (tag === 'table') { var wrap = D.createElement('div'); wrap.className = 'tbl'; wrap.appendChild(out); dst.appendChild(wrap); }
        else dst.appendChild(out);
        walk(n, out);
      });
    })(doc.body, frag);
    return frag;
  }

  // ------------------------------------------------------------------ kontentni normallashtirish
  function normalize(p) {
    var c = p && typeof p === 'object' ? p : null; if (!c) return null;
    var seen = {}, blocks = [];
    arr(c.blocks).forEach(function (b, i) {
      if (!b || typeof b !== 'object' || !KNOWN[b.type]) return;   // noma'lum blok turi — e'tiborsiz
      var x = {}; for (var k in b) x[k] = b[k];
      var id = cmiId(b.id || ('b' + (i + 1))); while (seen[id]) id += '_'; seen[id] = 1; x.id = id;
      x.title = str(b.title) || TYPE_LABEL[b.type];
      if (b.type === 'quiz') {
        var qs = {};
        x.questions = arr(b.questions).filter(function (q) {
          if (!q || !q.stem) return false;
          var t = q.type === 'tf' || q.type === 'fill' ? q.type : 'mcq';
          if (t === 'fill') return arr(q.answers).length > 0;
          if (t === 'tf' && !arr(q.options).length) return arr(q.correct).length > 0;
          return arr(q.options).length > 1 && arr(q.correct).length > 0;
        }).map(function (q, j) {
          var t = q.type === 'tf' || q.type === 'fill' ? q.type : 'mcq', id2 = cmiId(q.id || ('q' + (j + 1)));
          while (qs[id2]) id2 += '_'; qs[id2] = 1;
          var opts = t === 'tf' && !arr(q.options).length ? ["To'g'ri", "Noto'g'ri"] : arr(q.options).map(str);
          return { id: id2, type: t, stem: str(q.stem), options: t === 'fill' ? [] : opts, explanation: str(q.explanation),
            correct: arr(q.correct).map(Number).filter(function (n) { return n >= 0 && n < opts.length; }).sort(), answers: arr(q.answers).map(str) };
        });
        if (!x.questions.length) return;
        x.pass_pct = clamp(num(b.pass_pct, num(c.tracking && c.tracking.mastery, 60)), 0, 100);
        x.attempts = Math.max(0, Math.floor(num(b.attempts, 0)));
        x.shuffle = b.shuffle !== false; x.show_feedback = b.show_feedback !== false;
      }
      if (b.type === 'slides') x.slides = arr(b.slides).filter(function (s) { return s && typeof s === 'object'; });
      blocks.push(x);
    });
    var tr = c.tracking || {};
    return {
      id: str(c.id, 'isft-paket'), title: str(c.title) || str(c.topic && c.topic.title) || "O'quv paketi", lang: str(c.lang, 'uz'),
      course: c.course || {}, topic: c.topic || {}, brand: c.brand || {}, blocks: blocks,
      tracking: { mode: str(tr.mode, 'none'), completion: /^(view_all|quiz_pass|view_and_quiz)$/.test(tr.completion) ? tr.completion : 'view_all',
        mastery: num(tr.mastery, 60), activity_id: str(tr.activity_id) }
    };
  }

  // ------------------------------------------------------------------ holat (resume) — ixcham kodlash
  // {h: paket id xeshi, v: "0101..", c: joriy blok indeksi, q: {blokId: {n, s, b, p, sd, a:[...]}}, cs: completed yuborilgan (xAPI),
  //  xr: oxirgi yuborilgan kurs natijasi kaliti (xAPI passed/failed + ball)}
  function encodeState(st, limit) {
    var s = JSON.stringify(st);
    if (s.length <= limit) return s;
    var c = JSON.parse(s), k;
    for (k in c.q) delete c.q[k].a;                         // 1) oxirgi javoblar tashlanadi
    s = JSON.stringify(c); if (s.length <= limit) return s;
    for (k in c.q) c.q[k] = { n: c.q[k].n, s: c.q[k].s, p: c.q[k].p }; // 2) faqat natija
    s = JSON.stringify(c); return s.length <= limit ? s : JSON.stringify({ h: c.h, c: c.c, v: c.v });
  }
  function decodeState(s) { try { var o = JSON.parse(s); return o && typeof o === 'object' ? o : null; } catch (e) { return null; } }

  // ------------------------------------------------------------------ LMS adapterlari
  function findAPI(name) {
    function scan(w) {
      var n = 0;
      try {
        while (w && !w[name] && w.parent && w.parent !== w && n < 7) { n++; w = w.parent; }
        return w && w[name] ? w[name] : null;
      } catch (e) { return null; }   // boshqa domen ramkasi — kirish taqiqlangan
    }
    var api = scan(W);
    if (!api) { try { if (W.opener) api = scan(W.opener); } catch (e) { api = null; } }
    if (!api) { try { if (W.top && W.top.opener) api = scan(W.top.opener); } catch (e) { api = null; } }
    return api;
  }

  function Scorm12(api) {
    var dead = false, review = false, startStatus = '', iCount = -1, wasPassed = false;
    function err() { try { return str(api.LMSGetLastError()); } catch (e) { return '101'; } }
    function get(k) { try { var v = api.LMSGetValue(k); return v == null ? '' : String(v); } catch (e) { return ''; } }
    function set(k, v) {
      if (dead) return false;
      try { var r = String(api.LMSSetValue(k, String(v))); if (r !== 'true') note('LMSSetValue ' + k + ' xato ' + err()); return r === 'true'; }
      catch (e) { note('LMSSetValue ' + k + ' istisno'); return false; }
    }
    return {
      kind: 'scorm12', label: 'SCORM 1.2', limit: 4096,
      init: function () {
        var r; try { r = String(api.LMSInitialize('')); } catch (e) { r = 'false'; }
        if (r !== 'true' && err() !== '101') { note('LMSInitialize xato ' + err()); return null; }
        review = get('cmi.core.lesson_mode') === 'review';
        startStatus = get('cmi.core.lesson_status'); wasPassed = startStatus === 'passed';
        if (!review && (!startStatus || startStatus === 'not attempted')) set('cmi.core.lesson_status', 'incomplete');
        var ms = get('cmi.student_data.mastery_score'), name = get('cmi.core.student_name');
        if (name.indexOf(',') > 0) name = name.split(',').slice(1).join(',').trim() + ' ' + name.split(',')[0].trim();
        return { state: get('cmi.suspend_data'), location: get('cmi.core.lesson_location'), learner: name.trim(),
          mastery: ms !== '' && isFinite(+ms) ? +ms : null, review: review };
      },
      save: function (s, loc) { if (review) return; set('cmi.suspend_data', s); set('cmi.core.lesson_location', str(loc).slice(0, 255)); },
      report: function (r) {
        if (review) return;
        var st = r.success === 'passed' && r.complete ? 'passed' : r.success === 'failed' ? 'failed' : r.complete ? 'completed' : 'incomplete';
        if (wasPassed && st !== 'passed') return;   // «passed» (LMS'da yoki shu sessiyada) pasaytirilmaydi — ball ham o'sha natijada qoladi
        if (r.score != null) { set('cmi.core.score.min', 0); set('cmi.core.score.max', 100); set('cmi.core.score.raw', r.score); }
        if (st === 'incomplete' && /^(passed|completed)$/.test(startStatus)) return;   // LMS'dagi yakunlangan holat pasaytirilmaydi
        if (set('cmi.core.lesson_status', st) && st === 'passed') wasPassed = true;
      },
      interaction: function (it) {
        if (review) return;
        if (iCount < 0) { var c = get('cmi.interactions._count'); iCount = /^\d+$/.test(c) ? +c : 0; }
        var p = 'cmi.interactions.' + iCount + '.';
        if (!set(p + 'id', cmiId(it.id))) return;
        iCount++;
        set(p + 'type', it.type);
        set(p + 'student_response', it.r12.slice(0, 255));
        arr(it.c12).forEach(function (c, m) { set(p + 'correct_responses.' + m + '.pattern', str(c).slice(0, 255)); });   // har muqobil javob — alohida pattern
        set(p + 'result', it.ok ? 'correct' : 'wrong');
        set(p + 'time', clock12(it.when));
      },
      commit: function () { if (dead) return; try { if (String(api.LMSCommit('')) !== 'true') note('LMSCommit xato ' + err()); } catch (e) { /* jim */ } },
      finish: function (ms, r) {
        if (dead) return; set('cmi.core.session_time', time12(ms));
        set('cmi.core.exit', r.complete ? '' : 'suspend');
        this.commit(); try { api.LMSFinish(''); } catch (e) { /* jim */ } dead = true;
      }
    };
  }

  function Scorm2004(api) {
    var dead = false, review = false, startCompl = '', iCount = -1, wasPassed = false;
    function err() { try { return str(api.GetLastError()); } catch (e) { return '101'; } }
    function get(k) { try { var v = api.GetValue(k); return v == null ? '' : String(v); } catch (e) { return ''; } }
    function set(k, v) {
      if (dead) return false;
      try { var r = String(api.SetValue(k, String(v))); if (r !== 'true') note('SetValue ' + k + ' xato ' + err()); return r === 'true'; }
      catch (e) { note('SetValue ' + k + ' istisno'); return false; }
    }
    return {
      kind: 'scorm2004', label: 'SCORM 2004', limit: 64000,
      init: function () {
        var r; try { r = String(api.Initialize('')); } catch (e) { r = 'false'; }
        if (r !== 'true' && err() !== '103') { note('Initialize xato ' + err()); return null; }
        review = get('cmi.mode') === 'review';
        startCompl = get('cmi.completion_status'); wasPassed = get('cmi.success_status') === 'passed';
        if (!review && (!startCompl || startCompl === 'not attempted' || startCompl === 'unknown')) set('cmi.completion_status', 'incomplete');
        var sp = get('cmi.scaled_passing_score');
        return { state: get('cmi.suspend_data'), location: get('cmi.location'), learner: (function (n) { return n.indexOf(',') > 0 ? n.split(',').slice(1).join(',').trim() + ' ' + n.split(',')[0].trim() : n; })(get('cmi.learner_name')),
          mastery: sp !== '' && isFinite(+sp) ? Math.round(+sp * 100) : null, review: review };
      },
      save: function (s, loc) { if (review) return; set('cmi.suspend_data', s); set('cmi.location', str(loc).slice(0, 1000)); },
      report: function (r) {
        if (review) return;
        var keep = wasPassed && r.success !== 'passed';   // «passed» pasaytirilmaydi (eng yaxshi muvaffaqiyat saqlanadi) — ball ham
        if (r.score != null && !keep) {
          set('cmi.score.min', 0); set('cmi.score.max', 100); set('cmi.score.raw', r.score);
          set('cmi.score.scaled', (Math.round(r.score * 100) / 10000).toString());
        }
        set('cmi.progress_measure', (Math.round(r.progress * 1000) / 1000).toString());
        if (r.complete || startCompl !== 'completed') set('cmi.completion_status', r.complete ? 'completed' : 'incomplete');
        if (!keep && set('cmi.success_status', r.success) && r.success === 'passed') wasPassed = true;
      },
      interaction: function (it) {
        if (review) return;
        if (iCount < 0) { var c = get('cmi.interactions._count'); iCount = /^\d+$/.test(c) ? +c : 0; }
        var p = 'cmi.interactions.' + iCount + '.';
        if (!set(p + 'id', cmiId(it.id))) return;
        iCount++;
        set(p + 'type', it.type);
        set(p + 'description', it.desc.slice(0, 250));
        arr(it.c04).forEach(function (c, m) { set(p + 'correct_responses.' + m + '.pattern', str(c).slice(0, 4000)); });
        set(p + 'learner_response', it.r04.slice(0, 4000));
        set(p + 'result', it.ok ? 'correct' : 'incorrect');
        set(p + 'timestamp', stamp2004(it.when));
      },
      commit: function () { if (dead) return; try { if (String(api.Commit('')) !== 'true') note('Commit xato ' + err()); } catch (e) { /* jim */ } },
      finish: function (ms, r) {
        if (dead) return; set('cmi.session_time', iso8601(ms));
        set('cmi.exit', r.complete ? 'normal' : 'suspend');
        this.commit(); try { api.Terminate(''); } catch (e) { /* jim */ } dead = true;
      }
    };
  }

  var VERB = 'http://adlnet.gov/expapi/verbs/', ACT = 'http://adlnet.gov/expapi/activities/';
  function parseActor(s) {
    var a; try { a = JSON.parse(s); } catch (e) { return null; }
    if (Array.isArray(a)) a = a[0];
    if (!a || typeof a !== 'object') return null;
    function one(v) { return Array.isArray(v) ? v[0] : v; }
    var o = { objectType: 'Agent' }, name = one(a.name);
    if (name) o.name = str(name);
    if (one(a.mbox)) { var m = str(one(a.mbox)); o.mbox = /^mailto:/i.test(m) ? m : 'mailto:' + m; }
    else if (one(a.mbox_sha1sum)) o.mbox_sha1sum = str(one(a.mbox_sha1sum));
    else if (one(a.openid)) o.openid = str(one(a.openid));
    else if (one(a.account)) {
      var ac = one(a.account) || {};
      o.account = { homePage: str(ac.homePage || ac.accountServiceHomePage), name: str(ac.name || ac.accountName) };
      if (!o.account.homePage || !o.account.name) return null;
    } else return null;
    return o;
  }
  function launchParams() {
    var q; try { q = new URLSearchParams(W.location.search); } catch (e) { return null; }
    var ep = q.get('endpoint'), actor = q.get('actor');
    if (!ep || !actor || !httpUrl(ep)) return null;
    return { endpoint: ep.replace(/\/?$/, '/'), auth: q.get('auth') || '', actor: parseActor(actor), registration: q.get('registration') || '',
      activity_id: q.get('activity_id') || '' };
  }

  function Xapi(lp, C) {
    var actId = httpUrl(lp.activity_id) || httpUrl(C.tracking.activity_id) || ('urn:isft:paket:' + C.id);
    var reg = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(lp.registration) ? lp.registration : null;
    var queue = [], busy = false, inflight = 0, retryMs = 0, retryT = 0, dead = false, putT = 0, lastState = null, lang = C.lang || 'uz';
    function headers(json) {
      var h = { 'X-Experience-API-Version': '1.0.3' };
      if (lp.auth) h.Authorization = lp.auth;
      if (json) h['Content-Type'] = 'application/json';
      return h;
    }
    function lm(t) { var o = {}; o[lang] = t; return o; }
    var course = { objectType: 'Activity', id: actId, definition: { type: ACT + 'course', name: lm(C.title) } };
    function ctx(parent) {
      var c = { platform: 'ISFT Core', language: lang, contextActivities: {} };
      if (reg) c.registration = reg;
      if (parent) c.contextActivities.parent = [{ objectType: 'Activity', id: actId }];
      else delete c.contextActivities;
      return c;
    }
    function stmt(verb, en, obj, result, parent) {
      var s = { id: uuid(), actor: lp.actor, verb: { id: VERB + verb, display: { 'en-US': en } }, object: obj, timestamp: new Date().toISOString(), context: ctx(parent) };
      if (result) s.result = result;
      return s;
    }
    function send(s) { queue.push(s); flush(false); }
    function post(batch, keep) {
      return fetch(lp.endpoint + 'statements', { method: 'POST', headers: headers(true), body: JSON.stringify(batch), keepalive: !!keep, credentials: 'omit', mode: 'cors' });
    }
    function flushAll() {   // sahifa yopilmoqda: navbatdagi (yuborilayotganlardan tashqari) hamma statement keepalive bilan, 64 KB dan kichik bo'laklarda
      var rest = queue.slice(busy ? inflight : 0), part = [];
      rest.forEach(function (s) {
        part.push(s);
        if (JSON.stringify(part).length > 50000 && part.length > 1) { var last = part.pop(); try { post(part, true).catch(function () {}); } catch (e) { /* jim */ } part = [last]; }
      });
      if (part.length) try { post(part, true).catch(function () {}); } catch (e) { /* jim */ }
      queue.length = busy ? inflight : 0;
    }
    function flush(keep) {
      if (keep) return flushAll();
      if (busy || !queue.length || dead) return;
      var batch = queue.slice(0, 50);
      busy = true; inflight = batch.length;
      var done = function (okk, code) {
        busy = false; inflight = 0;
        if (okk || (code >= 400 && code < 500 && code !== 401 && code !== 403 && code !== 408 && code !== 429)) {
          if (!okk) note('LRS ' + code + ': statementlar rad etildi');
          queue.splice(0, batch.length); retryMs = 0;
          if (queue.length) flush(false);
        } else {
          retryMs = Math.min(30000, retryMs ? retryMs * 2 : 2000);
          clearTimeout(retryT); retryT = setTimeout(function () { flush(false); }, retryMs);
        }
      };
      try {
        post(batch, false).then(function (r) { done(r.ok, r.status); }, function () { done(false, 0); });
      } catch (e) { done(false, 0); }
    }
    function stateUrl() {
      var u = lp.endpoint + 'activities/state?activityId=' + encodeURIComponent(actId) + '&agent=' + encodeURIComponent(JSON.stringify(lp.actor)) + '&stateId=isft-state';
      return reg ? u + '&registration=' + reg : u;
    }
    function putState(keep) {
      if (lastState == null) return;
      var body = lastState;
      try { fetch(stateUrl(), { method: 'PUT', headers: headers(true), body: body, keepalive: !!keep && body.length < 60000, credentials: 'omit', mode: 'cors' }).then(function () {}, function () { note('State PUT xato'); }); } catch (e) { /* jim */ }
    }
    var seenBlocks = {};
    return {
      kind: 'xapi', label: 'xAPI', limit: 60000, actId: actId,
      init: function () {
        var ctl = W.AbortController ? new AbortController() : null, t = setTimeout(function () { if (ctl) ctl.abort(); }, 5000);
        var self = this;
        return fetch(stateUrl(), { headers: headers(false), credentials: 'omit', mode: 'cors', signal: ctl ? ctl.signal : undefined })
          .then(function (r) { return r.status === 200 ? r.text() : ''; }, function () { return ''; })
          .then(function (txt) {
            clearTimeout(t);
            send(stmt('initialized', 'initialized', course, null, false));
            var st = decodeState(txt);
            return { state: txt || '', location: st ? str(st.c) : '', learner: lp.actor.name || '', mastery: null, review: false, xapi: self };
          });
      },
      save: function (s) { lastState = s; clearTimeout(putT); putT = setTimeout(function () { putState(false); }, 800); },
      visit: function (b) {
        if (seenBlocks[b.id]) return; seenBlocks[b.id] = 1;
        send(stmt('experienced', 'experienced', { objectType: 'Activity', id: actId + '/block/' + b.id,
          definition: { type: ACT + (b.type === 'quiz' ? 'assessment' : b.type === 'video' ? 'media' : 'module'), name: lm(b.title) } }, null, true));
      },
      interaction: function (it) {
        var def = { type: ACT + 'cmi.interaction', name: lm(it.title), description: lm(it.desc), interactionType: it.type === 'true-false' ? 'true-false' : it.type };
        if (it.type === 'choice') def.choices = it.choices.map(function (c, i) { return { id: letter(i), description: lm(c) }; });
        if (arr(it.cX).length) def.correctResponsesPattern = arr(it.cX).map(str);   // har muqobil javob — alohida element
        send(stmt('answered', 'answered', { objectType: 'Activity', id: actId + '/block/' + it.block + '/q/' + encodeURIComponent(it.qid), definition: def },
          { success: it.ok, response: it.rX }, true));
      },
      quizResult: function (b, res) {
        send(stmt(res.passed ? 'passed' : 'failed', res.passed ? 'passed' : 'failed',
          { objectType: 'Activity', id: actId + '/block/' + b.id, definition: { type: ACT + 'assessment', name: lm(b.title) } },
          { score: { scaled: Math.round(res.pct * 100) / 10000, raw: res.pct, min: 0, max: 100 }, success: res.passed, completion: true }, true));
      },
      report: function (r, st) {
        // kurs darajasidagi natija (passed/failed + ball) — o'zgargan har safar; «passed» dan keyin «failed» yuborilmaydi
        if (r.success !== 'unknown' && !(/^p/.test(str(st.xr)) && r.success !== 'passed')) {
          var key = r.success.charAt(0) + (r.score == null ? '' : r.score) + (r.complete ? 'c' : '');
          if (st.xr !== key) {
            st.xr = key;
            var rr = { success: r.success === 'passed', completion: !!r.complete };
            if (r.score != null) rr.score = { scaled: Math.round(r.score * 100) / 10000, raw: r.score, min: 0, max: 100 };
            send(stmt(r.success, r.success, course, rr, false));
          }
        }
        if (r.complete && !st.cs) {
          st.cs = 1;
          var res = { completion: true }; if (r.score != null) res.score = { scaled: Math.round(r.score * 100) / 10000, raw: r.score, min: 0, max: 100 };
          if (r.success !== 'unknown') res.success = r.success === 'passed';
          send(stmt('completed', 'completed', course, res, false));
        }
      },
      commit: function () { putState(false); },
      flush: function () { flush(true); putState(true); },
      finish: function (ms, r) {
        if (dead) return;
        var res = { duration: iso8601(ms), completion: !!r.complete };
        queue.push(stmt('terminated', 'terminated', course, res, false));
        clearTimeout(putT); clearTimeout(retryT); putState(true); dead = true; flushAll();
      }
    };
  }

  function Preview(C) {
    var key = 'isft-paket:' + C.id;
    return {
      kind: 'preview', label: "Ko'rish rejimi", limit: 64000, preview: true,
      init: function () { var s = ''; try { s = W.localStorage.getItem(key) || ''; } catch (e) { /* xotira yopiq */ } var st = decodeState(s); return { state: s, location: st ? str(st.c) : '', learner: '', mastery: null }; },
      save: function (s) { try { W.localStorage.setItem(key, s); } catch (e) { /* jim */ } },
      report: function () {}, interaction: function () {}, commit: function () {}, finish: function () {}
    };
  }

  // ------------------------------------------------------------------ ilova
  try {   // shrift: sandbox/file:// (origin "null") da CORS xatosi chiqmasin — faqat oddiy origin'da ulanadi, aks holda tizim shrifti
    var org = typeof W.origin === 'string' ? W.origin : W.location.origin;   // self.origin — sandbox'da "null"
    if (org && org !== 'null') D.head.appendChild(el('link', { rel: 'stylesheet', href: 'fonts/fonts.css' }));
  } catch (e) { /* jim */ }
  var C = normalize(RAW), app = D.getElementById('app');
  if (!C || !C.blocks.length) {
    app.removeAttribute('aria-busy');
    app.textContent = '';
    app.appendChild(el('main', { cls: 'fatal' }, [el('h1', { text: 'Paket tarkibi topilmadi' }), el('p', { text: "content.js fayli yo'q yoki bloklar bo'sh. Paketni qayta yig'ing." })]));
    return;
  }
  var brand = /^#[0-9a-f]{6}$/i.test(str(C.brand.color)) ? C.brand.color : '#8B0033';
  D.documentElement.style.setProperty('--brand', brand);
  D.documentElement.style.setProperty('--brand-ink', shade(brand, -0.25));
  D.documentElement.style.setProperty('--brand-soft', shade(brand, 0.9));
  D.documentElement.style.setProperty('--brand-lite', shade(brand, 0.45));
  D.documentElement.lang = /^[a-z]{2}(-[A-Za-z]{2,4})?$/.test(C.lang) ? C.lang : 'uz';
  D.title = C.title + ' — ' + (str(C.brand.name) || 'ISFT');
  function shade(hex, t) {
    var n = parseInt(hex.slice(1), 16), r = n >> 16, g = (n >> 8) & 255, b = n & 255;
    function f(c) { return Math.round(t < 0 ? c * (1 + t) : c + (255 - c) * t); }
    return '#' + [f(r), f(g), f(b)].map(function (c) { return pad(c.toString(16), 2); }).join('');
  }

  var B = C.blocks, quizzes = B.filter(function (b) { return b.type === 'quiz'; }), content = B.filter(function (b) { return b.type !== 'quiz'; });
  var S = { h: hash(C.id), v: '', c: 0, q: {} };   // saqlanadigan holat
  var visited = {}, cur = -1, tracker = null, t0 = Date.now(), finished = false, lmsMastery = null, lastCompl = null, rendered = {}, saveT = 0;
  var R = {};   // DOM havolalari

  function passPct(b) { return lmsMastery != null ? clamp(lmsMastery, 0, 100) : b.pass_pct; }
  function qs(b) { var q = S.q[b.id]; if (!q) q = S.q[b.id] = { n: 0, s: null, b: null, p: 0 }; return q; }
  function status() {
    var seen = content.filter(function (b) { return visited[b.id]; }).length, allSeen = seen === content.length;
    var tried = quizzes.filter(function (b) { return qs(b).s != null; }), passed = quizzes.length > 0 && quizzes.every(function (b) { return qs(b).p; });
    var score = tried.length ? Math.round(tried.reduce(function (a, b) { return a + qs(b).s; }, 0) / tried.length) : null;
    var success = !tried.length ? 'unknown' : (tried.length === quizzes.length && passed ? 'passed' : tried.some(function (b) { return !qs(b).p; }) ? 'failed' : 'unknown');
    var mode = C.tracking.completion;
    if (!quizzes.length) mode = 'view_all';
    var complete = mode === 'view_all' ? allSeen : mode === 'quiz_pass' ? passed : allSeen && passed;
    var units = content.length + quizzes.length, done = seen + quizzes.filter(function (b) { return qs(b).p; }).length;
    return { complete: complete, success: success, score: score, progress: units ? done / units : 1, seen: seen, total: content.length };
  }
  function stateString() {
    S.v = B.map(function (b) { return visited[b.id] ? '1' : '0'; }).join(''); S.c = cur;
    return encodeState(S, tracker.limit);
  }
  function save(commit) {
    if (!tracker) return;
    tracker.save(stateString(), B[cur] ? B[cur].id : '');
    if (commit) tracker.commit();
  }
  function saveSoon() { clearTimeout(saveT); saveT = setTimeout(function () { save(false); }, 400); }
  function report(commit) {
    var r = status();
    tracker.report(r, S);
    renderProgress(r);
    if (r.complete && lastCompl === false) announce('Tabriklaymiz! Mavzu yakunlandi.');
    lastCompl = r.complete;
    save(commit);
    return r;
  }
  function announce(t) { if (!R.live) return; R.live.textContent = ''; setTimeout(function () { R.live.textContent = t; }, 30); }

  // ------------------------------------------------------------------ layout
  function build(info) {
    app.textContent = '';
    app.removeAttribute('aria-busy');
    var logo = assetUrl(C.brand.logo);
    var crs = C.course, meta = [str(crs.subject), crs.course ? crs.course + '-kurs' : '', str(crs.kafedra)].filter(Boolean).join(' · ');
    var topicNo = C.topic && C.topic.no ? C.topic.no + '-mavzu' : '';
    R.skip = el('a', { cls: 'skip', href: '#main', text: "Asosiy mazmunga o'tish", onclick: function (e) { e.preventDefault(); R.main.focus(); } });
    if (tracker.preview) R.banner = el('div', { cls: 'banner', role: 'note' }, [el('strong', { text: "Ko'rish rejimi" }), " — natija LMS'ga yuborilmaydi"]);
    R.menuBtn = el('button', { cls: 'btn icon only-m', type: 'button', 'aria-label': 'Mundarijani ochish', 'aria-controls': 'toc', 'aria-expanded': 'false', onclick: function () { toggleToc(); } }, [icon('menu')]);
    R.chip = el('span', { cls: 'chip' });
    R.bar = el('div', { cls: 'bar', role: 'progressbar', 'aria-label': "O'zlashtirish", 'aria-valuemin': '0', 'aria-valuemax': '100' }, [el('span')]);
    var header = el('header', { cls: 'top' }, [
      el('div', { cls: 'top-in' }, [
        R.menuBtn,
        logo ? el('img', { cls: 'logo', src: logo, alt: (str(C.brand.name) || 'ISFT') + ' logotipi', width: '44', height: '44' }) : el('span', { cls: 'logo txt', 'aria-hidden': 'true', text: str(C.brand.name, 'ISFT').slice(0, 4) }),
        el('div', { cls: 'ttl' }, [
          el('div', { cls: 'eyebrow', text: [str(C.brand.name, 'ISFT'), meta].filter(Boolean).join(' — ') }),
          el('div', { cls: 'h' }, [topicNo ? el('span', { cls: 'tno', text: topicNo }) : null, el('span', { text: C.title })])
        ]),
        el('div', { cls: 'top-r' }, [info.learner ? el('span', { cls: 'who', text: info.learner }) : null, R.chip])
      ]),
      R.bar
    ]);
    R.toc = el('nav', { cls: 'toc', id: 'toc', 'aria-label': 'Mundarija' });
    R.tocList = el('ol', { cls: 'toc-l' });
    B.forEach(function (b, i) {
      var a = el('button', { type: 'button', cls: 'toc-i', 'data-i': String(i), 'data-type': b.type, onclick: function () { go(i, true); closeToc(); } }, [
        el('span', { cls: 'tick' }, [icon(b.type)]),
        el('span', { cls: 'toc-t' }, [el('span', { cls: 'toc-k', text: TYPE_LABEL[b.type] }), el('span', { cls: 'toc-n', text: b.title })]),
        el('span', { cls: 'vis sr', text: '' })
      ]);
      R.tocList.appendChild(el('li', null, [a]));
    });
    R.tocHead = el('div', { cls: 'toc-h' }, [el('span', { text: 'Mundarija' }), R.tocCount = el('span', { cls: 'muted' }),
      el('button', { cls: 'btn icon only-m', type: 'button', 'aria-label': 'Mundarijani yopish', onclick: function () { closeToc(); } }, [icon('x')])]);
    R.toc.appendChild(R.tocHead); R.toc.appendChild(R.tocList);
    R.toc.appendChild(el('div', { cls: 'toc-f' }, [el('span', { text: str(C.brand.full) }), el('span', { cls: 'muted', text: tracker.label })]));
    R.scrim = el('div', { cls: 'scrim', onclick: function () { closeToc(); } });
    R.main = el('main', { id: 'main', cls: 'main', tabindex: '-1' });
    R.prev = el('button', { type: 'button', cls: 'btn ghost', onclick: function () { go(cur - 1, true); } }, [icon('left'), el('span', { text: 'Oldingi' })]);
    R.next = el('button', { type: 'button', cls: 'btn primary', onclick: function () { go(cur + 1, true); } }, [el('span', { text: 'Keyingi' }), icon('right')]);
    R.pos = el('span', { cls: 'pos muted' });
    R.pager = el('div', { cls: 'pager' }, [R.prev, R.pos, R.next]);
    R.live = el('div', { cls: 'sr', 'aria-live': 'polite', role: 'status' });
    R.wrap = el('div', { cls: 'wrap' }, [R.toc, R.scrim, el('div', { cls: 'col' }, [R.main, R.pager])]);
    [R.skip, R.banner, header, R.wrap, R.live].forEach(function (n) { if (n) app.appendChild(n); });
    D.addEventListener('keydown', function (e) {
      if (e.key === 'Escape' && app.classList.contains('toc-open')) { closeToc(); R.menuBtn.focus(); }
    });
  }
  function toggleToc() { if (app.classList.contains('toc-open')) closeToc(); else { app.classList.add('toc-open'); R.menuBtn.setAttribute('aria-expanded', 'true'); var c = R.tocList.querySelector('[aria-current]'); (c || R.tocList.querySelector('button')).focus(); } }
  function closeToc() { app.classList.remove('toc-open'); if (R.menuBtn) R.menuBtn.setAttribute('aria-expanded', 'false'); }
  function renderProgress(r) {
    var pct = Math.round(r.progress * 100);
    R.bar.firstChild.style.width = pct + '%'; R.bar.setAttribute('aria-valuenow', String(pct)); R.bar.setAttribute('aria-valuetext', pct + '%');
    var label = r.success === 'failed' ? "O'tmadi" : r.complete ? (r.success === 'passed' ? "O'tdi" : 'Yakunlandi') : 'Jarayonda';
    R.chip.textContent = label + ' · ' + pct + '%';
    R.chip.className = 'chip ' + (r.success === 'failed' ? 'bad' : r.complete ? 'good' : '');
    R.tocCount.textContent = r.seen + ' / ' + r.total;
    Array.prototype.forEach.call(R.tocList.querySelectorAll('.toc-i'), function (a) {
      var b = B[+a.getAttribute('data-i')], done = b.type === 'quiz' ? qs(b).p : visited[b.id];
      a.classList.toggle('done', !!done);
      a.classList.toggle('failed', b.type === 'quiz' && qs(b).s != null && !qs(b).p);
      a.querySelector('.vis').textContent = done ? ' — bajarildi' : visited[b.id] ? " — ko'rildi" : '';
      var t = a.querySelector('.tick'); t.textContent = ''; t.appendChild(icon(done ? 'check' : b.type));
    });
  }

  function go(i, focus) {
    if (i < 0 || i >= B.length) return;
    var prev = cur; cur = i;
    var b = B[i];
    Array.prototype.forEach.call(R.tocList.querySelectorAll('.toc-i'), function (a) { if (+a.getAttribute('data-i') === i) a.setAttribute('aria-current', 'step'); else a.removeAttribute('aria-current'); });
    R.main.textContent = '';
    var head = el('div', { cls: 'bh' }, [el('div', { cls: 'kicker' }, [icon(b.type), el('span', { text: TYPE_LABEL[b.type] + ' · ' + (i + 1) + ' / ' + B.length })]), el('h1', { id: 'bt-' + b.id, text: b.title })]);
    var card = el('section', { cls: 'card t-' + b.type, 'aria-labelledby': 'bt-' + b.id, 'data-block': b.id }, [head]);
    R.main.appendChild(card);
    (RENDER[b.type])(b, card);
    R.prev.disabled = i === 0; R.next.disabled = i === B.length - 1;
    R.pos.textContent = (i + 1) + ' / ' + B.length;
    markVisited(b);
    if (focus) { R.main.focus({ preventScroll: true }); try { W.scrollTo({ top: 0, behavior: 'auto' }); } catch (e) { W.scrollTo(0, 0); } }
    if (prev !== i) saveSoon();
  }
  function markVisited(b) {
    var isNew = !visited[b.id];
    visited[b.id] = 1;
    if (tracker.visit) tracker.visit(b);
    if (isNew) report(true); else renderProgress(status());
  }

  // ------------------------------------------------------------------ bloklar
  var RENDER = {
    plan: function (b, card) {
      var heads = textHeadings();
      var ol = el('ol', { cls: 'plan' });
      arr(b.items).forEach(function (it, k) {
        var t = str(it), h = heads[norm(t)];
        var inner = h ? el('button', { type: 'button', cls: 'link', onclick: function () { go(h.block, true); setTimeout(function () { var x = D.getElementById(h.id); if (x) { x.scrollIntoView({ block: 'start' }); x.focus({ preventScroll: true }); } }, 0); } }, [t]) : el('span', { text: t });
        ol.appendChild(el('li', null, [el('span', { cls: 'n', 'aria-hidden': 'true', text: String(k + 1) }), inner]));
      });
      card.appendChild(ol);
    },
    text: function (b, card) {
      var body = el('div', { cls: 'prose' });
      body.appendChild(sanitize(b.html));
      Array.prototype.forEach.call(body.querySelectorAll('h2,h3,h4'), function (h, k) { h.id = b.id + '-h' + k; h.setAttribute('tabindex', '-1'); });
      card.appendChild(body);
      card.appendChild(el('div', { cls: 'tools no-print' }, [el('button', { type: 'button', cls: 'btn ghost sm', onclick: function () { W.print(); } }, [icon('print'), el('span', { text: 'Chop etish' })])]));
    },
    slides: function (b, card) {
      var sl = b.slides, k = 0;
      if (!sl.length) { card.appendChild(el('p', { cls: 'muted', text: "Slaydlar yo'q." })); }
      else {
        var stage = el('div', { cls: 'stage' }), counter = el('span', { cls: 'counter', 'aria-live': 'polite' });
        var notesBox = el('div', { cls: 'notes', id: b.id + '-notes', hidden: true });
        var notesBtn = el('button', { type: 'button', cls: 'btn ghost sm', 'aria-expanded': 'false', 'aria-controls': b.id + '-notes',
          onclick: function () { var o = notesBox.hidden; notesBox.hidden = !o; notesBtn.setAttribute('aria-expanded', String(o)); } }, [icon('notes'), el('span', { text: 'Izohlar' })]);
        var prevB = el('button', { type: 'button', cls: 'nav-a l', 'aria-label': 'Oldingi slayd', onclick: function () { show(k - 1); } }, [icon('left')]);
        var nextB = el('button', { type: 'button', cls: 'nav-a r', 'aria-label': 'Keyingi slayd', onclick: function () { show(k + 1); } }, [icon('right')]);
        var dots = el('div', { cls: 'dots', role: 'group', 'aria-label': 'Slaydlar' });
        sl.forEach(function (_, j) { dots.appendChild(el('button', { type: 'button', 'aria-label': (j + 1) + '-slayd', onclick: function () { show(j); } })); });
        var deck = el('div', { cls: 'deck', tabindex: '0', role: 'region', 'aria-roledescription': 'karusel', 'aria-label': b.title + ' (← → tugmalari bilan almashtiring)' }, [stage, prevB, nextB]);
        var show = function (j) {
          k = clamp(j, 0, sl.length - 1);
          var s = sl[k], img = assetUrl(s.image);
          stage.textContent = '';
          var slide = img ? el('figure', { cls: 'slide img' }, [el('img', { src: img, alt: str(s.title) || ((k + 1) + '-slayd'), draggable: 'false' })])
            : el('div', { cls: 'slide gen' + (k === 0 ? ' cover' : '') }, [
              el('div', { cls: 's-bar' }, [el('span', { text: str(s.title) || ((k + 1) + '-slayd') })]),
              el('ul', { cls: 's-body' }, arr(s.bullets).map(function (x) { return el('li', { text: str(x) }); })),
              el('div', { cls: 's-foot' }, [el('span', { text: str(C.brand.name, 'ISFT') }), el('span', { text: String(k + 1) })])
            ]);
          slide.setAttribute('aria-label', (k + 1) + ' / ' + sl.length + (s.title ? ': ' + s.title : ''));
          slide.setAttribute('role', 'group'); slide.setAttribute('aria-roledescription', 'slayd');
          stage.appendChild(slide);
          counter.textContent = (k + 1) + ' / ' + sl.length;
          prevB.disabled = k === 0; nextB.disabled = k === sl.length - 1;
          Array.prototype.forEach.call(dots.children, function (d, j2) { if (j2 === k) d.setAttribute('aria-current', 'true'); else d.removeAttribute('aria-current'); });
          notesBox.textContent = str(s.notes) || "Bu slayd uchun izoh yo'q.";
        };
        deck.addEventListener('keydown', function (e) {
          if (e.key === 'ArrowLeft') { e.preventDefault(); show(k - 1); } else if (e.key === 'ArrowRight') { e.preventDefault(); show(k + 1); }
          else if (e.key === 'Home') { e.preventDefault(); show(0); } else if (e.key === 'End') { e.preventDefault(); show(sl.length - 1); }
        });
        var x0 = null, y0 = 0;
        deck.addEventListener('pointerdown', function (e) { x0 = e.clientX; y0 = e.clientY; });
        deck.addEventListener('pointerup', function (e) {
          if (x0 == null) return; var dx = e.clientX - x0, dy = e.clientY - y0; x0 = null;
          if (Math.abs(dx) > 40 && Math.abs(dx) > Math.abs(dy)) show(k + (dx < 0 ? 1 : -1));
        });
        card.appendChild(deck);
        card.appendChild(el('div', { cls: 'deck-bar' }, [counter, dots, notesBtn]));
        card.appendChild(notesBox);
        show(0);
      }
      var links = [], f = assetUrl(b.file), pdf = assetUrl(b.pdf);
      if (pdf) links.push(el('a', { cls: 'btn ghost sm', href: pdf, target: '_blank', rel: 'noopener' }, [icon('ext'), el('span', { text: "PDF ko'rinishida ochish" })]));
      if (f) links.push(el('a', { cls: 'btn ghost sm', href: f, download: '' }, [icon('down'), el('span', { text: 'Taqdimotni yuklab olish' })]));
      if (links.length) card.appendChild(el('div', { cls: 'tools' }, links));
    },
    video: function (b, card) {
      var id = /^[A-Za-z0-9_-]{6,20}$/.test(str(b.video_id)) ? b.video_id : null, start = Math.max(0, Math.floor(num(b.start, 0)));
      var watch = id ? 'https://www.youtube.com/watch?v=' + id + (start ? '&t=' + start + 's' : '') : (/^https:\/\/(www\.)?(youtube\.com|youtu\.be)\//.test(str(b.url)) ? b.url : null);
      if (id) {
        card.appendChild(el('div', { cls: 'video' }, [el('iframe', {
          src: 'https://www.youtube-nocookie.com/embed/' + id + '?rel=0&modestbranding=1' + (start ? '&start=' + start : ''),
          title: b.title + ' (YouTube video)', loading: 'lazy', allowfullscreen: true, referrerpolicy: 'strict-origin-when-cross-origin',
          allow: 'accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share'
        })]));
      } else card.appendChild(el('p', { cls: 'muted', text: 'Video manzili topilmadi.' }));
      if (watch) card.appendChild(el('p', { cls: 'tools' }, [el('a', { cls: 'btn ghost sm', href: watch, target: '_blank', rel: 'noopener noreferrer' }, [icon('ext'), el('span', { text: "YouTube'da ochish" })]),
        el('span', { cls: 'muted sm', text: "Video ko'rinmasa — tarmoq YouTube'ni to'sib qo'ygan bo'lishi mumkin." })]));
    },
    file: function (b, card) {
      var h = assetUrl(b.href);
      if (!h) { card.appendChild(el('p', { cls: 'muted', text: 'Fayl topilmadi.' })); return; }
      var name = h.split('/').pop(), ext = (name.split('.').pop() || '').toUpperCase();
      card.appendChild(el('div', { cls: 'filecard' }, [
        el('span', { cls: 'fext', 'aria-hidden': 'true', text: ext.slice(0, 4) }),
        el('div', { cls: 'fmeta' }, [el('strong', { text: name }), el('span', { cls: 'muted', text: [ext, fmtSize(b.size)].filter(Boolean).join(' · ') })]),
        el('div', { cls: 'fact' }, [
          /\.pdf$/i.test(h) ? el('a', { cls: 'btn ghost sm', href: h, target: '_blank', rel: 'noopener' }, [icon('ext'), el('span', { text: 'Ochish' })]) : null,
          el('a', { cls: 'btn primary sm', href: h, download: '' }, [icon('down'), el('span', { text: 'Yuklab olish' })])])
      ]));
    },
    quiz: function (b, card) { card.appendChild(el('div', { cls: 'quiz' })); quizView(b, card.lastChild); }
  };
  function textHeadings() {
    var map = {};
    B.forEach(function (b, bi) {
      if (b.type !== 'text') return;
      var tmp = el('div'); tmp.appendChild(sanitize(b.html));
      Array.prototype.forEach.call(tmp.querySelectorAll('h2,h3,h4'), function (h, k) { var n = norm(h.textContent); if (n && !map[n]) map[n] = { block: bi, id: b.id + '-h' + k }; });
    });
    return map;
  }

  // ------------------------------------------------------------------ test
  function qOrder(b, seed) {
    var r = rng(seed), order = b.shuffle ? shuffled(b.questions.length, r) : b.questions.map(function (_, i) { return i; });
    var opt = {};
    b.questions.forEach(function (q, i) { opt[q.id] = b.shuffle && q.type === 'mcq' ? shuffled(q.options.length, r) : q.options.map(function (_, j) { return j; }); });
    return { order: order, opt: opt };
  }
  function isTrue(q, i) { return /^(to'g'ri|togri|ha|true|rost|t)$/.test(norm(q.options[i])) || (i === 0 && !/^(noto'g'ri|yo'q|false|yolg'on)$/.test(norm(q.options[0]))); }
  function grade(q, ans) {   // ans: mcq/tf — tanlangan asl indekslar massivi; fill — matn
    if (q.type === 'fill') { var n = norm(ans); return !!n && q.answers.some(function (a) { return norm(a) === n; }); }
    var a = arr(ans).slice().sort(); return a.length === q.correct.length && a.every(function (x, i) { return x === q.correct[i]; });
  }
  function quizView(b, box) {
    var st = qs(b), left = b.attempts ? b.attempts - st.n : Infinity;
    box.textContent = '';
    if (st.ip && st.sd != null && left > 0 && !st.p) return renderAttempt(b, box);   // tugallanmagan urinish — o'sha tartibda davom
    if (st.s != null && (st.a || st.p)) return quizResult(b, box);   // o'tgan (javoblar suspend_data'dan tushib qolgan bo'lsa ham) — natija, qayta urinishsiz
    var rows = [el('li', null, [el('strong', { text: String(b.questions.length) }), ' ta savol']),
      el('li', null, ["O'tish bali: ", el('strong', { text: passPct(b) + '%' })]),
      el('li', null, ['Urinishlar: ', el('strong', { text: b.attempts ? st.n + ' / ' + b.attempts : st.n + " (cheklanmagan)" })])];
    if (st.s != null) rows.push(el('li', null, ['Oxirgi natija: ', el('strong', { text: st.s + '%' }), st.b != null ? ' · eng yaxshisi: ' + st.b + '%' : '']));
    box.appendChild(el('div', { cls: 'q-intro' }, [el('ul', { cls: 'facts' }, rows),
      left > 0 && !st.p ? el('button', { type: 'button', cls: 'btn primary', 'data-act': 'start', onclick: function () { startAttempt(b, box); } }, [el('span', { text: st.n ? 'Qayta urinish' : 'Testni boshlash' })])
        : el('p', { cls: 'alert bad', text: 'Urinishlar tugagan.' })]));
  }
  function startAttempt(b, box) {
    var st = qs(b);
    st.sd = (Math.random() * 4294967296) >>> 0; delete st.a; st.ip = 1;
    saveSoon(); renderAttempt(b, box);
  }
  function renderAttempt(b, box) {
    var st = qs(b), o = qOrder(b, st.sd);
    box.textContent = '';
    var form = el('form', { cls: 'qform', novalidate: true });
    o.order.forEach(function (qi, pos) {
      var q = b.questions[qi], name = b.id + '-' + q.id, fs = el('fieldset', { cls: 'q', 'data-qid': q.id });
      fs.appendChild(el('legend', null, [el('span', { cls: 'qn', text: (pos + 1) + '.' }), el('span', { text: q.stem })]));
      if (q.type === 'fill') {
        fs.appendChild(el('label', { cls: 'fill' }, [el('span', { cls: 'sr', text: 'Javobingiz' }), el('input', { type: 'text', name: name, autocomplete: 'off', spellcheck: 'false', placeholder: 'Javobni yozing', maxlength: '200' })]));
      } else {
        var multi = q.type === 'mcq' && q.correct.length > 1;
        if (multi) fs.appendChild(el('p', { cls: 'hint muted', text: 'Bir nechta javob to\'g\'ri bo\'lishi mumkin.' }));
        o.opt[q.id].forEach(function (oi) {
          fs.appendChild(el('label', { cls: 'opt' }, [el('input', { type: multi ? 'checkbox' : 'radio', name: name, value: String(oi) }), el('span', { text: q.options[oi] })]));
        });
      }
      form.appendChild(fs);
    });
    var msg = el('p', { cls: 'q-msg', role: 'status', 'aria-live': 'polite' }), confirmEmpty = false;
    var submit = el('button', { type: 'submit', cls: 'btn primary', 'data-act': 'submit' }, [el('span', { text: 'Javoblarni yuborish' })]);
    form.appendChild(el('div', { cls: 'q-foot' }, [msg, submit]));
    form.addEventListener('change', function () { confirmEmpty = false; submit.firstChild.textContent = 'Javoblarni yuborish'; msg.textContent = ''; });
    form.addEventListener('submit', function (e) {
      e.preventDefault();
      var answers = collect(b, form), empty = answers.filter(function (a, i) { var q = b.questions[i]; return q.type === 'fill' ? !norm(a) : !a.length; }).length;
      if (empty && !confirmEmpty) {
        confirmEmpty = true; msg.textContent = empty + " ta savol javobsiz qoldi. Baribir yuborilsinmi?"; submit.firstChild.textContent = 'Baribir yuborish'; return;
      }
      finishAttempt(b, answers, box);
    });
    box.appendChild(form);
    var first = form.querySelector('input'); if (first) first.focus({ preventScroll: true });
  }
  function collect(b, form) {
    return b.questions.map(function (q) {
      var name = b.id + '-' + q.id;
      if (q.type === 'fill') { var i = form.querySelector('input[name="' + name + '"]'); return i ? i.value.slice(0, 200) : ''; }
      return Array.prototype.filter.call(form.querySelectorAll('input[name="' + name + '"]'), function (x) { return x.checked; }).map(function (x) { return +x.value; });
    });
  }
  function finishAttempt(b, answers, box) {
    var st = qs(b), now = new Date(), right = 0;
    b.questions.forEach(function (q, i) {
      var ok = grade(q, answers[i]); if (ok) right++;
      var a = answers[i], it = { id: b.id + '_' + q.id, block: b.id, qid: q.id, ok: ok, when: now, title: q.stem.slice(0, 120), desc: q.stem, choices: q.options };
      if (q.type === 'fill') {
        it.type = 'fill-in'; it.r12 = it.r04 = it.rX = str(a).replace(/\[,\]/g, ', ');
        // har to'g'ri variant — alohida correct_responses.n (SCORM 2004'da «[,]» bitta javob ichidagi qismlarni ajratadi, muqobillarni emas)
        var alts = q.answers.map(function (x) { return str(x).replace(/\[[,.:]\]/g, ' '); }).filter(Boolean).slice(0, 10);
        it.c12 = alts; it.c04 = alts.map(function (x) { return '{case_matters=false}' + x; }); it.cX = alts;
      } else if (q.type === 'tf') {
        var tv = a.length ? isTrue(q, a[0]) : null, cv = isTrue(q, q.correct[0]);
        it.type = 'true-false'; it.r12 = tv == null ? '' : tv ? 't' : 'f'; it.r04 = it.rX = tv == null ? '' : String(tv);
        it.c12 = [cv ? 't' : 'f']; it.c04 = it.cX = [String(cv)];
      } else {
        it.type = 'choice'; it.r12 = a.map(letter).join(','); it.r04 = it.rX = a.map(letter).join('[,]');
        it.c12 = [q.correct.map(letter).join(',')]; it.c04 = it.cX = [q.correct.map(letter).join('[,]')];
      }
      tracker.interaction(it);
    });
    var pct = Math.round(right / b.questions.length * 100), passed = pct >= passPct(b);
    st.n++; st.s = pct; st.b = st.b == null ? pct : Math.max(st.b, pct); st.p = passed ? 1 : 0; delete st.ip;
    st.a = answers.map(function (a, i) { return b.questions[i].type === 'fill' ? str(a).slice(0, 60) : a; });
    if (tracker.quizResult) tracker.quizResult(b, { pct: pct, passed: passed });
    report(true);
    quizResult(b, box, true);
  }
  function quizResult(b, box, fresh) {
    var st = qs(b), passed = !!st.p, left = b.attempts ? b.attempts - st.n : Infinity;
    box.textContent = '';
    var right = 0, list = el('ol', { cls: 'fb-list' }), hasA = Array.isArray(st.a), fbOn = b.show_feedback && hasA;   // javoblar yo'q (ixcham holat) — faqat ball
    b.questions.forEach(function (q, i) {
      var a = hasA ? st.a[i] : null, ok = a != null && grade(q, a); if (ok) right++;
      if (!fbOn) return;
      var yours = a == null ? '—' : q.type === 'fill' ? (str(a) || '—') : (arr(a).length ? arr(a).map(function (x) { return q.options[x]; }).join('; ') : '—');
      var corr = q.type === 'fill' ? q.answers[0] : q.correct.map(function (x) { return q.options[x]; }).join('; ');
      list.appendChild(el('li', { cls: 'fb ' + (ok ? 'ok' : 'no'), 'data-qid': q.id }, [
        el('div', { cls: 'fb-h' }, [icon(ok ? 'check' : 'x'), el('span', { cls: 'sr', text: ok ? "To'g'ri: " : "Noto'g'ri: " }), el('span', { text: q.stem })]),
        el('div', { cls: 'fb-a' }, ['Sizning javobingiz: ', el('strong', { text: yours })]),
        ok ? null : el('div', { cls: 'fb-a' }, ["To'g'ri javob: ", el('strong', { text: corr })]),
        q.explanation ? el('div', { cls: 'fb-e', text: q.explanation }) : null
      ]));
    });
    var head = el('div', { cls: 'score ' + (passed ? 'good' : 'bad'), role: 'status', 'aria-live': 'polite', tabindex: '-1' }, [
      el('div', { cls: 'ring', style: '--p:' + (st.s || 0) }, [el('span', { text: (st.s || 0) + '%' })]),
      el('div', null, [el('h2', { text: passed ? 'Tabriklaymiz, test topshirildi!' : 'Test topshirilmadi' }),
        el('p', { text: (hasA ? right + ' / ' + b.questions.length + " to'g'ri javob · " : '') + "o'tish bali " + passPct(b) + '%' + (st.b != null && st.n > 1 ? ' · eng yaxshi natija ' + st.b + '%' : '') }),
        el('p', { cls: 'muted sm', text: "LMS'ga oxirgi urinish natijasi yuboriladi." })])
    ]);
    box.appendChild(head);
    if (fbOn) box.appendChild(list);
    var acts = el('div', { cls: 'q-foot' });
    if (!passed && left > 0) acts.appendChild(el('button', { type: 'button', cls: 'btn primary', 'data-act': 'retry', onclick: function () { startAttempt(b, box); } }, [el('span', { text: 'Qayta urinish' + (isFinite(left) ? ' (qoldi: ' + left + ')' : '') })]));
    else if (!passed) acts.appendChild(el('p', { cls: 'alert bad', text: 'Urinishlar tugagan.' }));
    if (acts.childNodes.length) box.appendChild(acts);
    if (fresh) { head.focus({ preventScroll: false }); announce((passed ? "Test topshirildi. " : "Test topshirilmadi. ") + 'Natija ' + st.s + '%'); }
  }

  // ------------------------------------------------------------------ ishga tushirish
  function pickTracker() {
    var m = C.tracking.mode;
    if (m === 'none') return Preview(C);
    var lp = launchParams();
    var a12 = function () { var a = findAPI('API'); return a ? Scorm12(a) : null; };
    var a04 = function () { var a = findAPI('API_1484_11'); return a ? Scorm2004(a) : null; };
    var ax = function () { return lp && lp.actor ? Xapi(lp, C) : null; };
    var order = m === 'scorm2004' ? [a04, a12, ax] : m === 'xapi' ? [ax, a04, a12] : [a12, a04, ax];
    if (lp && lp.actor) order = [ax].concat(order);   // launch parametrlari bo'lsa — xAPI
    for (var i = 0; i < order.length; i++) { var t = order[i](); if (t) return t; }
    return Preview(C);
  }
  function exit() {
    if (finished || !tracker) return;
    finished = true;
    save(false);
    tracker.finish(Date.now() - t0, status());
  }
  function start() {
    tracker = pickTracker();
    Promise.resolve(tracker.init()).then(function (info) {
      if (!info) { tracker = Preview(C); info = tracker.init(); }
      NS.mode = tracker.kind;
      lmsMastery = info.mastery;
      var st = decodeState(info.state);
      if (st && st.h === S.h) {
        S = st; S.q = S.q && typeof S.q === 'object' ? S.q : {};
        str(S.v).split('').forEach(function (c, i) { if (c === '1' && B[i]) visited[B[i].id] = 1; });
      }
      var start = 0, loc = str(info.location);
      B.forEach(function (b, i) { if (b.id === loc || String(i) === loc) start = i; });
      if (!loc && st && st.h === S.h && B[S.c]) start = S.c;
      build(info);
      lastCompl = status().complete;
      report(false);
      go(start, false);
      if (start > 0) announce('Oxirgi joydan davom ettirildi.');
      W.addEventListener('pagehide', exit);
      W.addEventListener('beforeunload', exit);
      D.addEventListener('visibilitychange', function () { if (D.visibilityState === 'hidden' && !finished) { save(true); if (tracker.flush) tracker.flush(); } });
      NS.ready = true;
      try { W.dispatchEvent(new CustomEvent('isftpaket:ready')); } catch (e) { /* eski brauzer */ }
    }).catch(function (e) { note('init xato: ' + (e && e.message)); });
  }
  NS.debug = { encodeState: encodeState, norm: norm, assetUrl: assetUrl, sanitize: function (h) { var d = el('div'); d.appendChild(sanitize(h)); return d.innerHTML; },
    status: function () { return status(); }, state: function () { return S; }, time12: time12, iso8601: iso8601 };
  NS.exit = exit;
  start();
})(window, document);
