/* ISFT Core — LMS ish vaqti adapterlari (paket pleyeri va kurs pleyeri uchun UMUMIY). Global nom: faqat window.ISFTLms.
 * SCORM 1.2 (window.API), SCORM 2004 4-nashr (window.API_1484_11), xAPI (TinCan launch parametrlari: endpoint, auth, actor, registration,
 * activity_id), ko'rish / mustaqil rejim (localStorage). Holat kodlash — encodeState (LMS uzunlik chegarasiga sig'diriladi).
 * Ichki faoliyatlar yo'li: Xapi(lp, C, {unit}) — paket: «<kurs>/block/<id>», kurs muharriri: «<kurs>/lesson/<uid>» (+ «/q/<savol>»).
 * Preview(C, {prefix}) — localStorage kaliti prefiksi (standart «isft-paket:»).
 * xAPI — Articulate Rise 360 bilan simdagi moslik (NEXTID.LMS: launch «scormdriver/indexAPI.html?endpoint=…&auth=Bearer …&actor={"name":…}»):
 * X-Experience-API-Version 1.0.2, state hujjatlari suspend_data / bookmark / cumulative_time (+ language_preference — o'qiladi), attempted /
 * progressed / experienced — «PUT statements?statementId=», answered / passed / failed / yopilishdagi attempted — «POST statements» (massiv);
 * faqat nomli actor (raqamli ham) o'zgarishsiz uzatiladi. Batafsil — Xapi() izohi va docs/paket.md «Kuzatuv».
 * xAPI oflayn navbati: tasdiqlanmagan statementlar localStorage'da («isft-xapi-q:<kalit>», try/catch — sandbox'da faqat xotirada) saqlanadi,
 * keyingi ishga tushirishda yoki tarmoq tiklanganda (online) qayta yuboriladi; id o'zgarmaydi — LRS dublikatni o'tkazib yuboradi (idempotent).
 * Launch parametrlari bo'lmasa (endpoint/actor yo'q) — Xapi ishlatilmaydi (mustaqil rejim).
 */
(function (W) {
  'use strict';
  var log = function () {};
  function note(msg) { try { log(msg); } catch (e) { /* jim */ } }
  function str(v, d) { return v == null ? (d || '') : String(v); }
  function arr(v) { return Array.isArray(v) ? v : []; }
  function pad(n, w) { n = String(n); while (n.length < w) n = '0' + n; return n; }
  function httpUrl(u) { u = str(u).replace(/^[\x00-\x20\x7f]+|[\x00-\x20\x7f]+$/g, ''); return /^https?:\/\/[^\s"'<>\\]+$/i.test(u) ? u : null; }
  function uuid() {
    var b = new Uint8Array(16); (W.crypto && W.crypto.getRandomValues) ? W.crypto.getRandomValues(b) : b.forEach(function (_, i) { b[i] = Math.random() * 256; });
    b[6] = (b[6] & 15) | 64; b[8] = (b[8] & 63) | 128;
    var h = Array.prototype.map.call(b, function (x) { return pad(x.toString(16), 2); }).join('');
    return h.slice(0, 8) + '-' + h.slice(8, 12) + '-' + h.slice(12, 16) + '-' + h.slice(16, 20) + '-' + h.slice(20);
  }
  function cmiId(s) { return str(s).replace(/[^A-Za-z0-9_\-.]/g, '_').slice(0, 250) || 'x'; }
  function letter(i) { return 'abcdefghijklmnopqrstuvwxyz'.charAt(i) || String(i); }
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

  // ------------------------------------------------------------------ holat (resume) — ixcham kodlash
  // {h: paket id xeshi, v: "0101..", c: joriy blok indeksi, q: {blokId: {n, s, b, p, sd, ip, a:[...], d:[...]}}, cs: completed yuborilgan (xAPI),
  //  xr: oxirgi yuborilgan kurs natijasi kaliti (xAPI passed/failed + ball), r: {blokId: reflect tanlovi}, m: {blokId: {t: soniya, b: 20 bitli ko'rilgan qismlar}}}
  //  a — oxirgi topshirilgan javoblar, d — tugallanmagan urinish qoralamasi. Javob shakli: mcq/tf — [indeks…], fill — matn,
  //  match — [har chap band uchun o'ng band indeksi | -1], sort — [har kartochka uchun toifa indeksi | -1]
  function encodeState(st, limit) {
    var s = JSON.stringify(st);
    if (s.length <= limit) return s;
    var c = JSON.parse(s), k;
    for (k in c.q) delete c.q[k].a;                         // 1) oxirgi javoblar tashlanadi
    s = JSON.stringify(c); if (s.length <= limit) return s;
    for (k in c.q) delete c.q[k].d;                         // 2) tugallanmagan urinish qoralamasi
    s = JSON.stringify(c); if (s.length <= limit) return s;
    for (k in c.q) c.q[k] = { n: c.q[k].n, s: c.q[k].s, p: c.q[k].p }; // 3) faqat natija
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
        set(p + 'result', it.neutral ? 'neutral' : it.ok ? 'correct' : 'wrong');
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
        set(p + 'result', it.neutral ? 'neutral' : it.ok ? 'correct' : 'incorrect');
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
  var PROGRESS_EXT = 'https://w3id.org/xapi/cmi5/result/extensions/progress', WEIGHT_EXT = 'http://id.tincanapi.com/extension/cmi-interaction-weighting';
  var XAPI_VER = '1.0.2';   // Articulate Rise (scormdriver) bilan bir xil — NEXTID shuni kutadi; bizning LRS 1.0.x ni qabul qiladi
  // State API hujjatlari (Rise nomlari): suspend_data — kodlangan holat, bookmark — joriy qadam kaliti, cumulative_time — jami ms (sessiyalar bo'yicha),
  // language_preference — faqat o'qiladi; isft-state — eski paketlar holati (faqat o'qiladi: eski sessiya davom ettirilsin)
  var ST_SUSPEND = 'suspend_data', ST_BOOKMARK = 'bookmark', ST_TIME = 'cumulative_time', ST_LANG = 'language_preference', ST_LEGACY = 'isft-state';
  function hash36(t) { var h = 5381; t = str(t); for (var i = 0; i < t.length; i++) h = ((h << 5) + h + t.charCodeAt(i)) | 0; return (h >>> 0).toString(36); }
  function xdur(ms) {     // Rise ko'rinishi: PT12.98S, PT1M11.22S, PT1H2M3S (nol qismlarsiz)
    var cs = Math.max(0, Math.round(ms / 10)), h = Math.floor(cs / 360000), m = Math.floor(cs / 6000) % 60, s = (cs % 6000) / 100;
    return 'PT' + (h ? h + 'H' : '') + (m ? m + 'M' : '') + (Math.round(s * 100) / 100) + 'S';
  }
  function sameOrigin(u) { try { return new URL(u, W.location.href).origin === W.location.origin; } catch (e) { return false; } }
  // Tasdiqlanmagan statementlar ombori (localStorage; mavjud bo'lmasa — faqat xotira). Hajm chegarasi: 300 ta / ~400 KB (eskilari tashlanadi).
  // Yozuv: {id, s: statement, put: true — «PUT statements?statementId=» (alohida), false — «POST statements» (massiv)}; eski yozuvlar (faqat statement) — POST.
  function Outbox(key) {
    var list = [];
    try { var raw = W.localStorage.getItem(key); var a = raw ? JSON.parse(raw) : []; if (Array.isArray(a)) list = a.filter(function (x) { return x && x.id; }); } catch (e) { list = []; }
    list = list.map(function (x) { return x.s && x.s.id === x.id ? x : { id: x.id, s: x, put: false }; });
    function save() {
      while (list.length > 300) list.shift();
      try {
        var t = JSON.stringify(list);
        while (t.length > 400000 && list.length > 1) { list.shift(); t = JSON.stringify(list); }
        if (list.length) W.localStorage.setItem(key, t); else W.localStorage.removeItem(key);
      } catch (e) { /* xotira yopiq yoki to'la — navbat faqat sessiya davomida */ }
    }
    return {
      pending: function () { return list.slice(); },
      add: function (s) { list.push(s); save(); },
      ack: function (ids) { var m = {}; ids.forEach(function (i) { m[i] = 1; }); var n = list.length; list = list.filter(function (x) { return !m[x.id]; }); if (list.length !== n) save(); }
    };
  }
  // Launch actor: mbox / mbox_sha1sum / openid / account — xAPI shakliga keltiriladi (TinCan massiv va accountServiceHomePage ham);
  // identifikatorsiz, faqat «name» (NEXTID: {"name":9424693}) — o'zgartirilmay uzatiladi (objectType qo'shiladi, raqamli nom raqamligicha qoladi)
  function parseActor(s) {
    var a; try { a = JSON.parse(s); } catch (e) { return null; }
    if (Array.isArray(a)) a = a[0];
    if (!a || typeof a !== 'object') return null;
    function one(v) { return Array.isArray(v) ? v[0] : v; }
    var o = { objectType: 'Agent' }, name = one(a.name);
    if (one(a.mbox)) { if (name != null && name !== '') o.name = str(name); var m = str(one(a.mbox)); o.mbox = /^mailto:/i.test(m) ? m : 'mailto:' + m; }
    else if (one(a.mbox_sha1sum)) { if (name) o.name = str(name); o.mbox_sha1sum = str(one(a.mbox_sha1sum)); }
    else if (one(a.openid)) { if (name) o.name = str(name); o.openid = str(one(a.openid)); }
    else if (one(a.account)) {
      if (name) o.name = str(name);
      var ac = one(a.account) || {};
      o.account = { homePage: str(ac.homePage || ac.accountServiceHomePage), name: str(ac.name || ac.accountName) };
      if (!o.account.homePage || !o.account.name) return null;
    } else if ((typeof a.name === 'number' && isFinite(a.name)) || (typeof a.name === 'string' && a.name.trim())) {
      o.name = a.name;   // NEXTID: faqat nom — aynan shunday (Rise ham shunday yuboradi)
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

  // xAPI — Articulate Rise 360 (scormdriver) bilan simdagi moslik (NEXTID.LMS shu ketma-ketlikni kutadi; docs/paket.md «Kuzatuv»):
  //  ochilganda: GET state language_preference, cumulative_time → PUT attempted → GET suspend_data, bookmark (yo'q bo'lsa — eski isft-state);
  //  jarayonda: PUT state suspend_data / bookmark (o'zgarganda), PUT progressed (cmi5 progress, butun foiz oshganda), POST answered (savol);
  //  yakunlanganda / test hal qilganda: POST passed | failed {success, duration, completion, score?}; yopilganda: POST attempted {duration} va
  //  cumulative_time. Boshqa domendagi LRS'ga yopilish so'rovlari — xAPI 1.0.x muqobil sintaksisi (POST ?method=…, forma: CORS-oddiy so'rov,
  //  preflight kerak emas — sahifa yopilganda ham yetib boradi); bir domendagi (bizning LRS) — keepalive fetch, oddiy sarlavhalar bilan.
  //  Bizning analitika uchun qo'shimcha (Rise'da yo'q): test bloki natijasi (passed/failed …/block/<id>), kurs muharriri: dars experienced/completed.
  function Xapi(lp, C, opts) {
    var unit = (opts && opts.unit) || 'block', seg = '/' + unit + '/';   // ichki faoliyat yo'li: paket — /block/<id>, kurs — /lesson/<uid>
    var actId = httpUrl(lp.activity_id) || httpUrl(C.tracking.activity_id) || ('urn:isft:paket:' + C.id);
    var reg = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(lp.registration) ? lp.registration : null;
    var cross = !sameOrigin(lp.endpoint), agentJson = JSON.stringify(lp.actor), lang = C.lang || 'uz', t0 = Date.now(), cum0 = 0;
    var queue = [], busy = false, inflight = 0, retryMs = 0, retryT = 0, dead = false, putT = 0;
    var want = {}, sent = {}, stBusy = {}, seen = {}, rdFail = {}, stWait = 0, stT = 0;   // state hujjatlari: yoziladigan qiymat, LRS'da borligi ma'lum qiymat, yozilmoqda
    var box = Outbox('isft-xapi-q:' + hash36(lp.endpoint + '|' + actId + '|' + agentJson));
    box.pending().forEach(function (x) { queue.push(x); });   // oldingi sessiyadan yuborilmay qolganlar (id o'sha — LRS takrorni o'tkazib yuboradi)
    function ids(b) { return b.map(function (x) { return x.id; }); }
    function final(okk, code) { return okk || (code >= 400 && code < 500 && code !== 401 && code !== 403 && code !== 408 && code !== 429); }
    function enc(v) { return encodeURIComponent(v); }
    function qs(p) { var k, out = []; for (k in p) if (p[k] != null) out.push(enc(k) + '=' + enc(p[k])); return out.length ? '?' + out.join('&') : ''; }
    function stateParams(id) { var p = { stateId: id, activityId: actId, agent: agentJson }; if (reg) p.registration = reg; return p; }
    // bitta so'rov: oddiy (sarlavhalar bilan) yoki sahifa yopilayotganda boshqa domenga — muqobil sintaksis (forma maydonlari Rise tartibida)
    function call(method, path, params, body, ctype, keep) {
      if (keep && cross && method !== 'GET') {
        var f = new URLSearchParams(), k;
        for (k in params) if (params[k] != null) f.append(k, params[k]);
        if (lp.auth) f.append('Authorization', lp.auth);
        f.append('X-Experience-API-Version', XAPI_VER);
        if (ctype) f.append('Content-Type', ctype);
        if (body != null) f.append('content', body);
        var fb = f.toString();
        return fetch(lp.endpoint + path + '?method=' + method, { method: 'POST', headers: { 'Content-Type': 'application/x-www-form-urlencoded' }, body: fb,
          keepalive: fb.length < 60000, credentials: 'omit', mode: 'cors' });
      }
      var h = { 'X-Experience-API-Version': XAPI_VER };
      if (lp.auth) h.Authorization = lp.auth;
      if (ctype) h['Content-Type'] = ctype;
      var o = { method: method, headers: h, credentials: 'omit', mode: 'cors' };
      if (body != null) { o.body = body; o.keepalive = !!keep && body.length < 60000; }
      return fetch(lp.endpoint + path + qs(params), o);
    }
    function lm(t) { var o = {}; o[lang] = str(t); return o; }
    var course = { id: actId, objectType: 'Activity', definition: { type: ACT + 'course', name: { en: str(C.title) }, description: { en: '' } } };
    function stmt(verb, obj, result, parent) {
      var s = { id: uuid(), timestamp: new Date().toISOString(), actor: lp.actor, verb: { id: VERB + verb, display: { 'en-US': verb } } };
      if (result) s.result = result;
      s.object = obj;
      var c = {};
      if (parent) c.contextActivities = { parent: [course] };
      if (reg) c.registration = reg;
      if (parent || reg) s.context = c;
      return s;
    }
    function send(s, put) { var x = { id: s.id, s: s, put: !!put }; queue.push(x); box.add(x); pump(); }
    function req(b, keep) {
      if (b[0].put) return call('PUT', 'statements', { statementId: b[0].id }, JSON.stringify(b[0].s), 'application/json', keep);
      return call('POST', 'statements', {}, JSON.stringify(b.map(function (x) { return x.s; })), 'application/json', keep);
    }
    function head(list, max) {   // navbat boshidan bitta so'rov: PUT — bitta statement, POST — ketma-ket POST statementlar massivi
      if (list[0].put) return [list[0]];
      var b = [];
      for (var i = 0; i < list.length && !list[i].put && b.length < 50; i++) {
        b.push(list[i]);
        if (b.length > 1 && JSON.stringify(b).length > max) { b.pop(); break; }
      }
      return b;
    }
    function keepSend(b) {   // keepalive: javob kelsa (sahifa hali tirik) — omborda tasdiqlanadi, aks holda keyingi sessiyada qayta yuboriladi
      try { req(b, true).then(function (r) { if (final(r.ok, r.status)) box.ack(ids(b)); }, function () {}); } catch (e) { /* jim */ }
    }
    function flushAll() {   // sahifa yopilmoqda: navbatdagi (yuborilayotganlardan tashqari) hamma statement keepalive bilan, 64 KB dan kichik bo'laklarda
      var rest = queue.slice(busy ? inflight : 0), max = cross ? 25000 : 50000;   // muqobil sintaksisda mazmun URL-kodlanadi (~1.5 baravar)
      while (rest.length) { var b = head(rest, max); rest = rest.slice(b.length); keepSend(b); }
      queue.length = busy ? inflight : 0;
    }
    function pump() {
      if (busy || !queue.length || dead) return;
      var batch = head(queue, 500000);
      busy = true; inflight = batch.length;
      var done = function (okk, code) {
        busy = false; inflight = 0;
        if (final(okk, code)) {
          if (!okk) note('LRS ' + code + ': statementlar rad etildi');
          queue.splice(0, batch.length); retryMs = 0; box.ack(ids(batch));
          if (queue.length) pump();
        } else {
          retryMs = Math.min(30000, retryMs ? retryMs * 2 : 2000);
          clearTimeout(retryT); retryT = setTimeout(pump, retryMs);
        }
      };
      try { req(batch, false).then(function (r) { done(r.ok, r.status); }, function () { done(false, 0); }); }
      catch (e) { done(false, 0); }
    }
    function writeState(id, keep) {   // o'zgargan hujjat — PUT (application/octet-stream, Rise kabi); bittasi yozilayotgan bo'lsa — keyin navbat bilan
      var v = want[id];
      if (v == null || v === sent[id] || rdFail[id] || (stBusy[id] && !keep)) return;   // rdFail: o'qish muvaffaqiyatsiz — LRS'dagi hujjatni ustiga yozmaymiz
      stBusy[id] = 1;
      // xato bo'lsa darhol qayta urinilmaydi (aks holda 429/5xx/oflayn — cheksiz tez so'rovlar): 2 s dan 60 s gacha kutish, keyin yana
      var fin = function (okk) {
        stBusy[id] = 0;
        if (okk) { sent[id] = v; stWait = 0; } else { note('State ' + id + ' yozilmadi'); stWait = Math.min(60000, stWait ? stWait * 2 : 2000); }
        if (keep || dead || want[id] === sent[id]) return;
        if (okk) writeState(id, false);
        else { clearTimeout(stT); stT = setTimeout(function () { stT = 0; writeDocs(false); }, stWait); }
      };
      try { call('PUT', 'activities/state', stateParams(id), v, 'application/octet-stream', keep).then(function (r) { fin(r.ok); }, function () { fin(false); }); }
      catch (e) { fin(false); }
    }
    function writeDocs(keep) { clearTimeout(putT); if (!keep && stWait && stT) return; writeState(ST_BOOKMARK, keep); writeState(ST_SUSPEND, keep); }
    try { W.addEventListener('online', function () { retryMs = 0; pump(); stWait = 0; clearTimeout(stT); stT = 0; writeDocs(false); }); } catch (e) { /* jim */ }
    function score(p) { return { scaled: Math.round(p * 100) / 10000, raw: p, min: 0, max: 100 }; }
    return {
      kind: 'xapi', label: 'xAPI', limit: 60000, actId: actId,
      init: function () {
        var self = this;
        // har so'rovga o'z muddati (ketma-ket 3 bosqich bitta 5 s ga sig'maydi); o'qish XATOsi (404 emas) bo'lsa — shu hujjat ustiga yozilmaydi (saqlangan progress yo'qolmasin)
        function get(id) {
          var ctl = W.AbortController ? new AbortController() : null, t = setTimeout(function () { if (ctl) ctl.abort(); }, 8000);
          return fetch(lp.endpoint + 'activities/state' + qs(stateParams(id)), { headers: (function () { var h = { 'X-Experience-API-Version': XAPI_VER }; if (lp.auth) h.Authorization = lp.auth; return h; })(),
            credentials: 'omit', mode: 'cors', signal: ctl ? ctl.signal : undefined }).then(function (r) {
            clearTimeout(t);
            if (r.status === 200) return r.text();
            if (r.status !== 404 && r.status !== 204) rdFail[id] = 1;
            return null;
          }, function () { clearTimeout(t); rdFail[id] = 1; return null; });
        }
        // Rise tartibi: avval language_preference va cumulative_time javobi, keyin «attempted», so'ng suspend_data va bookmark
        var pLang = get(ST_LANG), pTime = get(ST_TIME);
        var pHead = Promise.all([pLang, pTime]).then(function () { send(stmt('attempted', course), true); });
        var pSusp = pHead.then(function () { return get(ST_SUSPEND); }), pBook = pHead.then(function () { return get(ST_BOOKMARK); });
        return Promise.all([pLang, pTime, pSusp, pBook]).then(function (v) {
          cum0 = /^\d{1,15}$/.test(str(v[1]).trim()) ? +str(v[1]).trim() : 0;
          if (v[2] != null) sent[ST_SUSPEND] = v[2];
          if (v[3] != null) sent[ST_BOOKMARK] = v[3];
          return v[2] ? [v[2], v[3]] : get(ST_LEGACY).then(function (old) { return [old || '', v[3]]; });
        }).then(function (x) {
          var st = decodeState(x[0]), nm = lp.actor.name;
          return { state: x[0] || '', location: x[1] ? str(x[1]) : st ? str(st.c) : '', learner: nm == null || /^\d+$/.test(str(nm)) ? '' : str(nm),
            mastery: null, review: false, xapi: self };
        });
      },
      save: function (s, loc) {
        if (dead) return;
        want[ST_SUSPEND] = s; if (loc) want[ST_BOOKMARK] = str(loc).slice(0, 1000);
        clearTimeout(putT); putT = setTimeout(function () { writeDocs(false); }, 800);
      },
      visit: function (b) {   // Rise: ko'p darsli kursda har dars — PUT experienced (ota — kurs); bitta darsli paket bloklari uchun yuborilmaydi
        if (unit === 'block' || !b || seen[b.id]) return; seen[b.id] = 1;
        send(stmt('experienced', { id: actId + seg + b.id, objectType: 'Activity',
          definition: { type: ACT + (b.type === 'quiz' ? 'assessment' : 'module'), name: lm(b.title) } }, null, true), true);
      },
      interaction: function (it) {
        var def = { type: ACT + 'cmi.interaction', name: lm(it.title), description: lm(it.desc), interactionType: it.type === 'true-false' ? 'true-false' : it.type };
        if (it.type === 'choice') def.choices = it.choices.map(function (c, i) { return { id: letter(i), description: lm(c) }; });
        if (it.type === 'matching') ['source', 'target'].forEach(function (k) { def[k] = arr(it[k]).map(function (x) { return { id: x.id, description: lm(x.text) }; }); });
        if (arr(it.cX).length) def.correctResponsesPattern = arr(it.cX).map(str);   // har muqobil javob — alohida element
        if (it.neutral) {   // mulohaza (reflect): baholanmaydi — «responded», success yo'q
          send(stmt('responded', { id: actId + seg + it.block, objectType: 'Activity', definition: def }, { response: it.rX }, true), false);
          return;
        }
        var ex = {}; ex[WEIGHT_EXT] = 1;
        send(stmt('answered', { id: actId + seg + it.block + '/q/' + encodeURIComponent(it.qid), objectType: 'Activity', definition: def },
          { success: !!it.ok, response: it.rX, extensions: ex }, true), false);
      },
      done: function (b) {   // ichki faoliyat (kurs muharriri: dars) yakunlandi — sessiyada bir marta (bizning LRS dars bo'yicha holat hisoblaydi)
        if (seen['done:' + b.id]) return; seen['done:' + b.id] = 1;
        send(stmt('completed', { id: actId + seg + b.id, objectType: 'Activity',
          definition: { type: ACT + (b.type === 'quiz' ? 'assessment' : 'module'), name: lm(b.title) } }, { completion: true }, true), false);
      },
      quizResult: function (b, res) {   // test bloki natijasi (bizning LRS: urinishlar, «testdan o'tolmaslik»)
        send(stmt(res.passed ? 'passed' : 'failed', { id: actId + seg + b.id, objectType: 'Activity', definition: { type: ACT + 'assessment', name: lm(b.title) } },
          { score: score(res.pct), success: !!res.passed, completion: true }, true), false);
      },
      report: function (r, st) {
        // progress: har 25% da (25, 50, 75) va yakunda 100 — PUT progressed (cmi5 progress kengaytmasi). Rise bitta darsda faqat 100 yuboradi;
        // oraliq qiymatlar NEXTID'da jarayonni ko'rsatish uchun, lekin so'rovlar soni oz (har foizda emas). Takror yo'q (holat: xp)
        var pp = r.complete ? 100 : Math.floor(Math.max(0, Math.min(1, +r.progress || 0)) * 4 + 1e-9) * 25;
        if (pp >= 100 && !r.complete) pp = 75;
        if (pp > 0 && pp > (+st.xp || 0)) { st.xp = pp; var ex = {}; ex[PROGRESS_EXT] = pp; send(stmt('progressed', course, { extensions: ex }), true); }
        // kurs natijasi: dars yakunlansa — passed (Rise «passed/incomplete»), test yiqilsa — failed; o'zgargan har safar, «passed» dan keyin «failed» yo'q
        var verb = r.success === 'failed' ? 'failed' : r.complete ? 'passed' : null;
        if (verb && !(/^p/.test(str(st.xr)) && verb !== 'passed')) {
          var key = verb.charAt(0) + (r.score == null ? '' : r.score) + (r.complete ? 'c' : '');
          if (st.xr !== key) {
            st.xr = key;
            var rr = { success: verb === 'passed', duration: xdur(Date.now() - t0), completion: !!r.complete };
            if (r.score != null) rr.score = score(r.score);
            send(stmt(verb, course, rr), false);
          }
        }
      },
      commit: function () { writeDocs(false); },
      flush: function () { flushAll(); writeDocs(true); },
      finish: function (ms, r) {
        if (dead) return;
        clearTimeout(retryT);
        var x = stmt('attempted', course, { duration: xdur(ms) }), it = { id: x.id, s: x, put: false };
        queue.push(it); box.add(it);
        dead = true; flushAll();
        want[ST_TIME] = String(cum0 + Math.max(0, Math.round(ms)));
        writeState(ST_TIME, true); writeDocs(true);
      }
    };
  }

  // LMS API'siz rejim: ?preview=1 — «Ko'rish rejimi» banneri bilan; aks holda jim «mustaqil» rejim (NEXTID.LMS iframe'i va h.k.)
  function previewParam() { try { return new URLSearchParams(W.location.search).get('preview') === '1'; } catch (e) { return false; } }
  // SCORM paketi (tracking.mode scorm12/scorm2004) LMS API'sini topmasa — natija saqlanmaydi: ogohlantirish banneri (?preview=1 bo'lmasa).
  // xAPI / none — NEXTID kabi jim (banner yo'q).
  function Preview(C, opts) {
    var key = ((opts && opts.prefix) || 'isft-paket:') + C.id, pv = previewParam(), m = C.tracking.mode;
    return {
      kind: pv ? 'preview' : 'standalone', label: pv ? "Ko'rish rejimi" : 'Mustaqil rejim', limit: 64000, preview: pv,
      nolms: !pv && (m === 'scorm12' || m === 'scorm2004'),
      init: function () { var s = ''; try { s = W.localStorage.getItem(key) || ''; } catch (e) { /* xotira yopiq */ } var st = decodeState(s); return { state: s, location: st ? str(st.c) : '', learner: '', mastery: null }; },
      save: function (s) { try { W.localStorage.setItem(key, s); } catch (e) { /* jim */ } },
      report: function () {}, interaction: function () {}, commit: function () {}, finish: function () {}
    };
  }


  W.ISFTLms = { version: '1.1.0', setLog: function (fn) { if (typeof fn === 'function') log = fn; },
    encodeState: encodeState, decodeState: decodeState, findAPI: findAPI, Scorm12: Scorm12, Scorm2004: Scorm2004, parseActor: parseActor,
    launchParams: launchParams, previewParam: previewParam, Xapi: Xapi, Preview: Preview,
    util: { uuid: uuid, cmiId: cmiId, letter: letter, time12: time12, iso8601: iso8601, xdur: xdur, clock12: clock12, stamp2004: stamp2004, httpUrl: httpUrl } };
})(window);
