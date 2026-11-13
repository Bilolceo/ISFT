/* ISFT Core — LMS ish vaqti adapterlari (paket pleyeri va kurs pleyeri uchun UMUMIY). Global nom: faqat window.ISFTLms.
 * SCORM 1.2 (window.API), SCORM 2004 4-nashr (window.API_1484_11), xAPI (TinCan launch parametrlari: endpoint, auth, actor, registration,
 * activity_id), ko'rish / mustaqil rejim (localStorage). Holat kodlash — encodeState (LMS uzunlik chegarasiga sig'diriladi).
 * Ichki faoliyatlar yo'li: Xapi(lp, C, {unit}) — paket: «<kurs>/block/<id>», kurs muharriri: «<kurs>/lesson/<uid>» (+ «/q/<savol>»).
 * Preview(C, {prefix}) — localStorage kaliti prefiksi (standart «isft-paket:»).
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

  function Xapi(lp, C, opts) {
    var seg = '/' + ((opts && opts.unit) || 'block') + '/';   // ichki faoliyat yo'li: paket — /block/<id>, kurs — /lesson/<uid>
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
        send(stmt('experienced', 'experienced', { objectType: 'Activity', id: actId + seg + b.id,
          definition: { type: ACT + (b.type === 'quiz' ? 'assessment' : b.type === 'video' ? 'media' : 'module'), name: lm(b.title) } }, null, true));
      },
      interaction: function (it) {
        var def = { type: ACT + 'cmi.interaction', name: lm(it.title), description: lm(it.desc), interactionType: it.type === 'true-false' ? 'true-false' : it.type };
        if (it.type === 'choice') def.choices = it.choices.map(function (c, i) { return { id: letter(i), description: lm(c) }; });
        if (it.type === 'matching') ['source', 'target'].forEach(function (k) { def[k] = arr(it[k]).map(function (x) { return { id: x.id, description: lm(x.text) }; }); });
        if (arr(it.cX).length) def.correctResponsesPattern = arr(it.cX).map(str);   // har muqobil javob — alohida element
        if (it.neutral) {   // mulohaza (reflect): baholanmaydi — «responded», success yo'q
          send(stmt('responded', 'responded', { objectType: 'Activity', id: actId + seg + it.block, definition: def }, { response: it.rX }, true));
          return;
        }
        send(stmt('answered', 'answered', { objectType: 'Activity', id: actId + seg + it.block + '/q/' + encodeURIComponent(it.qid), definition: def },
          { success: it.ok, response: it.rX }, true));
      },
      done: function (b) {   // ichki faoliyat (kurs muharriri: dars) yakunlandi — sessiyada bir marta
        if (seenBlocks['done:' + b.id]) return; seenBlocks['done:' + b.id] = 1;
        send(stmt('completed', 'completed', { objectType: 'Activity', id: actId + seg + b.id,
          definition: { type: ACT + (b.type === 'quiz' ? 'assessment' : 'module'), name: lm(b.title) } }, { completion: true }, true));
      },
      quizResult: function (b, res) {
        send(stmt(res.passed ? 'passed' : 'failed', res.passed ? 'passed' : 'failed',
          { objectType: 'Activity', id: actId + seg + b.id, definition: { type: ACT + 'assessment', name: lm(b.title) } },
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


  W.ISFTLms = { version: '1.0.0', setLog: function (fn) { if (typeof fn === 'function') log = fn; },
    encodeState: encodeState, decodeState: decodeState, findAPI: findAPI, Scorm12: Scorm12, Scorm2004: Scorm2004, parseActor: parseActor,
    launchParams: launchParams, previewParam: previewParam, Xapi: Xapi, Preview: Preview,
    util: { uuid: uuid, cmiId: cmiId, letter: letter, time12: time12, iso8601: iso8601, clock12: clock12, stamp2004: stamp2004, httpUrl: httpUrl } };
})(window);
