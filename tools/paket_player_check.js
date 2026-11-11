#!/usr/bin/env node
/* ISFT o'quv paket pleyeri — muvofiqlik sinovi (SCORM 1.2, SCORM 2004 4-nashr, xAPI, NEXTID/mustaqil rejim, ko'rish rejimi,
 * kontrakt v2: qadamlar rejimi, bo'limlar, rasm lightbox, galereya, mulohaza bloki, postMessage;
 * kontrakt v3: muqova, fayl-video (track, tezlik, joy/ko'rilgan ulush), slayd izohi/audio, match/sort savollari (klaviatura, bosish, sudrash,
 * «matching» interaction), kartochkalar, topshiriq).
 *
 * Ishga tushirish:
 *   PW=/path/to/node_modules/playwright-core CHROME=/path/to/chrome OUT=/tmp/paket node tools/paket_player_check.js
 *
 * Nima qiladi: app/paket_player + tests/fixtures/paket_sample ni kichik Node serverida pastki yo'ldan (/courses/12/5/pkg/) beradi,
 * ota «mock LMS» sahifasi window.API / window.API_1484_11 ni (ma'lumotlar modeli, lug'at, uzunlik cheklovlari, xato kodlari bilan)
 * yozib boradi, pleyerni iframe ichida ochadi va UI orqali boshqaradi. xAPI uchun alohida portda mock LRS (CORS bilan).
 * Natija qatorlari: "  ✓ ..." / "  ✗ ...", oxirida jamlanma; xato bo'lsa chiqish kodi 1. Skrinshotlar: $OUT.
 */
'use strict';
const http = require('http'), fs = require('fs'), path = require('path');
const { chromium } = require(process.env.PW || 'playwright-core');
const ROOT = path.resolve(__dirname, '..');
const PLAYER = path.join(ROOT, 'app', 'paket_player'), FIX = path.join(ROOT, 'tests', 'fixtures', 'paket_sample');
const OUT = process.env.OUT || path.join(require('os').tmpdir(), 'isft_paket_player');
const CONTENT = JSON.parse(fs.readFileSync(path.join(FIX, 'content.json'), 'utf8'));
const QUIZ = CONTENT.blocks.find(b => b.type === 'quiz'), REFLECT = CONTENT.blocks.find(b => b.type === 'reflect');
const TEXT = CONTENT.blocks.find(b => b.type === 'text'), SLIDES = CONTENT.blocks.find(b => b.type === 'slides');
const KNOWN = ['plan', 'text', 'slides', 'video', 'file', 'quiz', 'section', 'refs', 'keypoints', 'reflect', 'flashcards', 'assignment'];
const NBLOCKS = CONTENT.blocks.filter(b => KNOWN.includes(b.type)).length;   // noma'lum «hotspot» hisobga olinmaydi; muqova qadami — blok emas
const MATCH = QUIZ.questions.find(q => q.type === 'match'), SORT = QUIZ.questions.find(q => q.type === 'sort'), FILLQ = QUIZ.questions.find(q => q.type === 'fill');
const VFILE = CONTENT.blocks.find(b => b.type === 'video' && b.provider === 'file'), FLASH = CONTENT.blocks.find(b => b.type === 'flashcards'), ASSIGN = CONTENT.blocks.find(b => b.type === 'assignment');
const SORT_ITEMS = SORT.categories.flatMap((c, ci) => c.items.map(t => ({ text: t, c: ci })));
// kutilgan «matching» javoblari: to'g'ri — i→i, noto'g'ri — i→i+1 (aylanma); saralash: to'g'ri toifa / keyingi toifa
const letter = i => 'abcdefghijklmnopqrstuvwxyz'[i], id36 = i => '0123456789abcdefghijklmnopqrstuvwxyz'[i];
const EXP = {
  m12: right => MATCH.pairs.map((_, i) => id36(i + 1) + '.' + letter(right ? i : (i + 1) % MATCH.pairs.length)).join(','),
  m04: right => MATCH.pairs.map((_, i) => 'l' + (i + 1) + '[.]r' + ((right ? i : (i + 1) % MATCH.pairs.length) + 1)).join('[,]'),
  s12: right => SORT_ITEMS.map((it, k) => id36(k + 1) + '.' + letter(right ? it.c : (it.c + 1) % SORT.categories.length)).join(','),
  s04: right => SORT_ITEMS.map((it, k) => 'i' + (k + 1) + '[.]c' + ((right ? it.c : (it.c + 1) % SORT.categories.length) + 1)).join('[,]')
};
fs.mkdirSync(OUT, { recursive: true });

const sleep = ms => new Promise(r => setTimeout(r, ms));
let sect = '';
const fails = [], counts = {};
function ok(c, m) {
  console.log((c ? '  ✓ ' : '  ✗ ') + m);
  counts[sect] = counts[sect] || [0, 0]; counts[sect][c ? 0 : 1]++;
  if (!c) fails.push(sect + ': ' + m);
}
function section(s) { sect = s; console.log('== ' + s); }

// ---------------------------------------------------------------- mock LMS (ota sahifada ishlaydi; .toString() orqali uzatiladi)
function lmsRuntime() {
  /* global window, document */
  const store = { sessions: [], persist: { entry: 'ab-initio', status: '', location: '', suspend: '', raw: '', total: 0 }, msgs: [] };
  window.LMS = store;
  window.addEventListener('message', e => { if (e.data && e.data.source === 'isft-paket') store.msgs.push(e.data); });   // pleyer postMessage'lari
  const R12_TIME = /^\d{2,4}:\d{2}:\d{2}(\.\d{1,2})?$/, R12_CLOCK = /^\d{2}:\d{2}:\d{2}(\.\d{1,2})?$/;
  const R04_DUR = /^P(?=\d|T\d)(\d+Y)?(\d+M)?(\d+D)?(T(?=\d)(\d+H)?(\d+M)?(\d+(\.\d{1,2})?S)?)?$/;
  const R04_TIME = /^\d{4}(-\d{2}(-\d{2}(T\d{2}(:\d{2}(:\d{2}(\.\d{1,2}(Z|[+-]\d{2}(:\d{2})?)?)?)?)?)?)?)?$/;
  const dec = v => /^-?\d+(\.\d+)?$/.test(v);
  function base(kind) { const s = { kind, calls: [], inits: 0, finishes: 0, commits: 0, errors: [], values: {}, inter: [], state: 'new' }; store.sessions.push(s); return s; }
  function rec(s, fn, args, ret, err) { s.calls.push({ fn, args, ret, err, t: Date.now() }); if (err !== '0' && fn !== 'GetValue' && fn !== 'LMSGetValue') s.errors.push(fn + '(' + args.join(',') + ') => ' + err); }

  window.makeAPI12 = function () {
    const s = base('scorm12'), P = store.persist; let err = '0';
    const v = s.values;
    Object.assign(v, { 'cmi.core.student_id': 'u123', 'cmi.core.student_name': 'Valiyev, Ali', 'cmi.core.lesson_location': P.location,
      'cmi.core.credit': 'credit', 'cmi.core.lesson_status': P.status || 'not attempted', 'cmi.core.entry': P.entry, 'cmi.core.score.raw': P.raw,
      'cmi.core.score.min': '', 'cmi.core.score.max': '', 'cmi.core.total_time': '0000:00:00.00', 'cmi.core.lesson_mode': 'normal', 'cmi.suspend_data': P.suspend,
      'cmi.launch_data': '', 'cmi.student_data.mastery_score': '' });
    const RO = ['cmi.core.student_id', 'cmi.core.student_name', 'cmi.core.credit', 'cmi.core.entry', 'cmi.core.total_time', 'cmi.core.lesson_mode', 'cmi.launch_data', 'cmi.student_data.mastery_score', 'cmi.interactions._count', 'cmi.core._children', 'cmi.interactions._children'];
    const WO = ['cmi.core.exit', 'cmi.core.session_time'];
    function check(k, val) {
      const m = /^cmi\.interactions\.(\d+)\.(id|type|student_response|result|time|weighting|latency|correct_responses\.(\d+)\.pattern|objectives\.\d+\.id)$/.exec(k);
      if (m) {
        const n = +m[1]; if (n > s.inter.length) return '201';
        if (m[2] === 'id' && !/^[A-Za-z0-9_\-.]{1,255}$/.test(val)) return '405';
        if (m[2] === 'type' && !['true-false', 'choice', 'fill-in', 'matching', 'performance', 'sequencing', 'likert', 'numeric'].includes(val)) return '405';
        if (m[2] === 'result' && !['correct', 'wrong', 'unanticipated', 'neutral'].includes(val) && !dec(val)) return '405';
        if (m[2] === 'time' && !R12_CLOCK.test(val)) return '405';
        if (m[2] === 'student_response' || m[3] != null) {
          if (m[3] != null && +m[3] !== Object.keys(s.inter[n] || {}).filter(x => /^correct_responses\./.test(x)).length) return '201';   // ketma-ket
          const it = s.inter[n] || {}; if (val.length > 255) return '405';
          if (it.type === 'choice' && val !== '' && !/^[0-9a-z](,[0-9a-z])*$/.test(val)) return '405';
          if (it.type === 'true-false' && val !== '' && !/^[01tf]$/.test(val)) return '405';
          if (it.type === 'matching' && val !== '' && !/^[0-9a-z]\.[0-9a-z](,[0-9a-z]\.[0-9a-z])*$/.test(val)) return '405';   // {manba}.{nishon} juftlari, vergul bilan; bir belgili identifikatorlar
          if (it.type === 'matching' && m[3] != null && val === '') return '405';
        }
        if (n === s.inter.length) s.inter.push({});
        s.inter[n][m[2]] = val; return '0';
      }
      if (RO.includes(k)) return '403';
      switch (k) {
        case 'cmi.core.lesson_status': return ['passed', 'completed', 'failed', 'incomplete', 'browsed'].includes(val) ? '0' : '405';
        case 'cmi.core.exit': return ['time-out', 'suspend', 'logout', ''].includes(val) ? '0' : '405';
        case 'cmi.core.session_time': return R12_TIME.test(val) ? '0' : '405';
        case 'cmi.core.lesson_location': return val.length <= 255 ? '0' : '405';
        case 'cmi.suspend_data': return val.length <= 4096 ? '0' : '405';
        case 'cmi.core.score.raw': case 'cmi.core.score.min': case 'cmi.core.score.max': return val === '' || (dec(val) && +val >= 0 && +val <= 100) ? '0' : '405';
        case 'cmi.comments': return '0';
        default: return /^cmi\./.test(k) ? '401' : '201';
      }
    }
    const api = {
      LMSInitialize(a) { let r = 'true'; err = '0'; if (a !== '') { err = '201'; r = 'false'; } else if (s.state !== 'new') { err = '101'; r = 'false'; } else { s.state = 'run'; s.inits++; } rec(s, 'LMSInitialize', [a], r, err); return r; },
      LMSFinish(a) {
        let r = 'true'; err = '0';
        if (s.state !== 'run') { err = '301'; r = 'false'; } else {
          s.state = 'done'; s.finishes++;
          P.status = v['cmi.core.lesson_status']; P.location = v['cmi.core.lesson_location']; P.suspend = v['cmi.suspend_data']; P.raw = v['cmi.core.score.raw'];
          P.entry = v['cmi.core.exit'] === 'suspend' ? 'resume' : '';
        }
        rec(s, 'LMSFinish', [a], r, err); return r;
      },
      LMSGetValue(k) {
        err = '0'; let r = '';
        if (s.state !== 'run') err = '301';
        else if (WO.includes(k)) err = '404';
        else if (k === 'cmi.interactions._count') r = String(s.inter.length);
        else if (/^cmi\.interactions\.\d+\./.test(k)) err = '404';
        else if (k in v) r = v[k]; else err = '401';
        rec(s, 'LMSGetValue', [k], r, err); return r;
      },
      LMSSetValue(k, val) {
        val = String(val); let r = 'false';
        if (s.state !== 'run') err = '301'; else { err = check(k, val); if (err === '0') { if (!/^cmi\.interactions/.test(k)) v[k] = val; r = 'true'; } }
        rec(s, 'LMSSetValue', [k, val], r, err); return r;
      },
      LMSCommit(a) { let r = 'true'; err = '0'; if (s.state !== 'run') { err = '301'; r = 'false'; } else s.commits++; rec(s, 'LMSCommit', [a], r, err); return r; },
      LMSGetLastError() { return err; }, LMSGetErrorString(c) { return 'err ' + c; }, LMSGetDiagnostic(c) { return 'diag ' + c; }
    };
    return api;
  };

  window.makeAPI04 = function () {
    const s = base('scorm2004'), P = store.persist; let err = '0';
    const v = s.values;
    Object.assign(v, { 'cmi.learner_id': 'u123', 'cmi.learner_name': 'Valiyev, Ali', 'cmi.location': P.location, 'cmi.credit': 'credit',
      'cmi.completion_status': P.status || 'unknown', 'cmi.success_status': P.success || 'unknown', 'cmi.entry': P.entry, 'cmi.mode': 'normal',
      'cmi.suspend_data': P.suspend, 'cmi.launch_data': '', 'cmi.scaled_passing_score': '', 'cmi.total_time': 'PT0S', 'cmi.progress_measure': '',
      'cmi.score.scaled': '', 'cmi.score.raw': '', 'cmi.score.min': '', 'cmi.score.max': '', 'cmi.completion_threshold': '' });
    const RO = ['cmi.learner_id', 'cmi.learner_name', 'cmi.credit', 'cmi.entry', 'cmi.mode', 'cmi.launch_data', 'cmi.scaled_passing_score', 'cmi.total_time', 'cmi.completion_threshold', 'cmi.interactions._count', 'cmi._version'];
    const WO = ['cmi.exit', 'cmi.session_time'];
    function check(k, val) {
      const m = /^cmi\.interactions\.(\d+)\.(id|type|learner_response|result|timestamp|description|weighting|latency|correct_responses\.(\d+)\.pattern)$/.exec(k);
      if (m) {
        const n = +m[1]; if (n > s.inter.length) return '351';
        const it = s.inter[n];
        if (m[2] !== 'id' && !it) return '408';
        if (m[2] === 'id') { if (!/^\S{1,4000}$/.test(val)) return '406'; if (!it) s.inter.push({}); s.inter[n].id = val; return '0'; }
        if ((m[2] === 'learner_response' || m[3] != null) && !it.type) return '408';
        if (m[3] != null && +m[3] !== Object.keys(it).filter(x => /^correct_responses\./.test(x)).length) return '351';   // ketma-ket
        if (m[2] === 'type' && !['true-false', 'choice', 'fill-in', 'long-fill-in', 'likert', 'matching', 'performance', 'sequencing', 'numeric', 'other'].includes(val)) return '406';
        if (m[2] === 'result' && !['correct', 'incorrect', 'unanticipated', 'neutral'].includes(val) && !dec(val)) return '406';
        if (m[2] === 'timestamp' && !R04_TIME.test(val)) return '406';
        if (m[2] === 'learner_response' || m[3] != null) {
          if (it.type === 'true-false' && !/^(true|false)$/.test(val)) return '406';
          if (it.type === 'choice' && val !== '' && !/^[^\[\],\s]+(\[,\][^\[\],\s]+)*$/.test(val)) return '406';
          if (it.type === 'matching' && val !== '' && !/^[A-Za-z0-9_-]+\[\.\][A-Za-z0-9_-]+(\[,\][A-Za-z0-9_-]+\[\.\][A-Za-z0-9_-]+)*$/.test(val)) return '406';   // source[.]target[,]source[.]target
          if (it.type === 'matching' && m[3] != null && val === '') return '406';
          if (it.type === 'fill-in' && m[3] != null && !/^(\{case_matters=(true|false)\})?(\{order_matters=(true|false)\})?/.test(val)) return '406';
        }
        it[m[2]] = val; return '0';
      }
      if (RO.includes(k)) return '404';
      switch (k) {
        case 'cmi.completion_status': return ['completed', 'incomplete', 'not attempted', 'unknown'].includes(val) ? '0' : '406';
        case 'cmi.success_status': return ['passed', 'failed', 'unknown'].includes(val) ? '0' : '406';
        case 'cmi.exit': return ['time-out', 'suspend', 'logout', 'normal', ''].includes(val) ? '0' : '406';
        case 'cmi.session_time': return R04_DUR.test(val) ? '0' : '406';
        case 'cmi.location': return val.length <= 1000 ? '0' : '407';
        case 'cmi.suspend_data': return val.length <= 64000 ? '0' : '407';
        case 'cmi.score.scaled': return !dec(val) ? '406' : (+val < -1 || +val > 1) ? '407' : '0';
        case 'cmi.score.raw': case 'cmi.score.min': case 'cmi.score.max': return dec(val) ? '0' : '406';
        case 'cmi.progress_measure': return !dec(val) ? '406' : (+val < 0 || +val > 1) ? '407' : '0';
        default: return /^cmi\./.test(k) ? '401' : '351';
      }
    }
    const api = {
      Initialize(a) { let r = 'true'; err = '0'; if (a !== '') { err = '201'; r = 'false'; } else if (s.state === 'run') { err = '103'; r = 'false'; } else if (s.state === 'done') { err = '104'; r = 'false'; } else { s.state = 'run'; s.inits++; } rec(s, 'Initialize', [a], r, err); return r; },
      Terminate(a) {
        let r = 'true'; err = '0';
        if (s.state === 'new') { err = '112'; r = 'false'; } else if (s.state === 'done') { err = '113'; r = 'false'; } else {
          s.state = 'done'; s.finishes++;
          if (v['cmi.exit'] === 'suspend') { Object.assign(P, { entry: 'resume', status: v['cmi.completion_status'], success: v['cmi.success_status'], location: v['cmi.location'], suspend: v['cmi.suspend_data'] }); }
          else Object.assign(P, { entry: 'ab-initio', status: '', success: '', location: '', suspend: '' });   // yangi urinish
        }
        rec(s, 'Terminate', [a], r, err); return r;
      },
      GetValue(k) {
        err = '0'; let r = '';
        if (s.state === 'new') err = '122'; else if (s.state === 'done') err = '123';
        else if (WO.includes(k)) err = '405';
        else if (k === 'cmi.interactions._count') r = String(s.inter.length);
        else if (k in v) { r = v[k]; if (r === '' && !['cmi.location', 'cmi.suspend_data', 'cmi.launch_data', 'cmi.entry'].includes(k)) err = '403'; }
        else err = '401';
        rec(s, 'GetValue', [k], r, err); return r;
      },
      SetValue(k, val) {
        val = String(val); let r = 'false';
        if (s.state === 'new') err = '132'; else if (s.state === 'done') err = '133'; else { err = check(k, val); if (err === '0') { if (!/^cmi\.interactions/.test(k)) v[k] = val; r = 'true'; } }
        rec(s, 'SetValue', [k, val], r, err); return r;
      },
      Commit(a) { let r = 'true'; err = '0'; if (s.state === 'new') { err = '142'; r = 'false'; } else if (s.state === 'done') { err = '143'; r = 'false'; } else s.commits++; rec(s, 'Commit', [a], r, err); return r; },
      GetLastError() { return err; }, GetErrorString(c) { return 'err ' + c; }, GetDiagnostic(c) { return 'diag ' + c; }
    };
    return api;
  };

  // LMS «ishga tushirish»: yangi sessiya (yangi API obyekti) + iframe
  window.launch = function (kind, url) {
    const f = document.getElementById('sco');
    if (kind === 'scorm12') { window.API = window.makeAPI12(); delete window.API_1484_11; }
    else if (kind === 'scorm2004') { window.API_1484_11 = window.makeAPI04(); delete window.API; }
    else { delete window.API; delete window.API_1484_11; }   // NEXTID.LMS kabi: API yo'q, launch parametrlari yo'q
    f.src = url;
  };
  window.unload = function () { document.getElementById('sco').src = 'about:blank'; };
}
const LMS_HTML = `<!doctype html><html><head><meta charset="utf-8"><title>Mock LMS</title>
<style>body{margin:0;font:14px system-ui}header{background:#333;color:#fff;padding:6px 12px}iframe{border:0;width:100%;height:calc(100vh - 32px);display:block}</style></head>
<body><header>Mock LMS</header><iframe id="sco" name="sco" title="SCO"></iframe><script>(${lmsRuntime.toString()})();</script></body></html>`;

// ---------------------------------------------------------------- serverlar
const MIME = { '.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8', '.css': 'text/css', '.json': 'application/json', '.png': 'image/png', '.jpg': 'image/jpeg',
  '.mp4': 'video/mp4', '.vtt': 'text/vtt; charset=utf-8', '.wav': 'audio/wav', '.pdf': 'application/pdf', '.woff2': 'font/woff2', '.pptx': 'application/vnd.openxmlformats-officedocument.presentationml.presentation' };
const PKG = '/courses/12/5/pkg/';
const served = [];
function serveFile(res, file) {
  fs.readFile(file, (e, buf) => {
    if (e) { res.writeHead(404); res.end('404'); return; }
    res.writeHead(200, { 'Content-Type': MIME[path.extname(file)] || 'application/octet-stream', 'Cache-Control': 'no-store' }); res.end(buf);
  });
}
const lms = http.createServer((req, res) => {
  const u = new URL(req.url, 'http://x'); served.push(u.pathname);
  if (u.pathname === '/lms.html') { res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' }); res.end(LMS_HTML); return; }
  if (u.pathname.startsWith(PKG)) {
    const rel = decodeURIComponent(u.pathname.slice(PKG.length)) || 'index.html';
    if (rel.includes('..')) { res.writeHead(400); res.end(); return; }
    const p1 = path.join(PLAYER, rel);
    serveFile(res, fs.existsSync(p1) ? p1 : path.join(FIX, rel)); return;
  }
  res.writeHead(404); res.end('404');
});
// mock LRS
const LRS = { statements: [], heads: [], posts: 0, failFirst: 0, state: {}, stateReq: [], ids: new Set(), dup: 0 };
const cors = { 'Access-Control-Allow-Origin': '*', 'Access-Control-Allow-Headers': 'Authorization, Content-Type, X-Experience-API-Version',
  'Access-Control-Allow-Methods': 'GET, PUT, POST, OPTIONS', 'Access-Control-Expose-Headers': 'X-Experience-API-Version', 'X-Experience-API-Version': '1.0.3' };
const lrs = http.createServer((req, res) => {
  const u = new URL(req.url, 'http://x');
  let body = ''; req.on('data', c => body += c);
  req.on('end', () => {
    if (req.method === 'OPTIONS') { res.writeHead(204, cors); res.end(); return; }
    if (u.pathname === '/xapi/statements' && req.method === 'POST') {
      LRS.posts++;
      if (LRS.failFirst > 0) { LRS.failFirst--; res.writeHead(503, cors); res.end(); return; }
      LRS.heads.push({ auth: req.headers.authorization, ver: req.headers['x-experience-api-version'], ct: req.headers['content-type'] });
      let arr; try { arr = JSON.parse(body); } catch (e) { res.writeHead(400, cors); res.end(); return; }
      if (!Array.isArray(arr)) arr = [arr];
      arr.forEach(s => { if (LRS.ids.has(s.id)) { LRS.dup++; return; } LRS.ids.add(s.id); LRS.statements.push(s); });
      res.writeHead(200, Object.assign({ 'Content-Type': 'application/json' }, cors)); res.end(JSON.stringify(arr.map(s => s.id))); return;
    }
    if (u.pathname === '/xapi/activities/state') {
      const key = [u.searchParams.get('activityId'), u.searchParams.get('agent'), u.searchParams.get('stateId'), u.searchParams.get('registration')].join('|');
      LRS.stateReq.push({ m: req.method, auth: req.headers.authorization, ver: req.headers['x-experience-api-version'], key });
      if (req.method === 'GET') {
        if (key in LRS.state) { res.writeHead(200, Object.assign({ 'Content-Type': 'application/json' }, cors)); res.end(LRS.state[key]); }
        else { res.writeHead(404, cors); res.end(); }
        return;
      }
      if (req.method === 'PUT') { LRS.state[key] = body; res.writeHead(204, cors); res.end(); return; }
    }
    res.writeHead(404, cors); res.end();
  });
});
const listen = s => new Promise(r => s.listen(0, '127.0.0.1', () => r(s.address().port)));


// ---------------------------------------------------------------- yordamchi brauzer funksiyalari
async function newCtx(br, opts, tag) {
  const ctx = await br.newContext(Object.assign({ viewport: { width: 1280, height: 860 } }, opts || {}));
  const errs = [], foreign = [];
  ctx.on('page', p => wirePage(p, errs));
  await ctx.route(/youtube-nocookie\.com|youtube\.com/, r => r.fulfill({ status: 200, contentType: 'text/html', body: '<!doctype html><meta charset="utf-8"><title>yt</title><body style="background:#000;color:#fff;font:20px sans-serif;display:grid;place-items:center;height:100vh;margin:0">▶ YouTube (sinov zaglushkasi)</body>' }));
  const bad = []; ctx.on('response', r => { if (r.status() >= 400) bad.push(r.status() + ' ' + r.url().slice(0, 90)); });
  ctx.on('requestfailed', r => bad.push('FAIL ' + r.url().slice(0, 90) + ' ' + (r.failure() && r.failure().errorText)));
  ctx.on('request', rq => { const u = rq.url(); if (!/^(http:\/\/127\.0\.0\.1:|about:|data:|blob:)/.test(u) && !/youtube(-nocookie)?\.com/.test(u)) foreign.push(u); });
  const page = await ctx.newPage(); wirePage(page, errs);
  return { ctx, page, errs, foreign, tag, bad };
}
function wirePage(p, errs) {
  p.on('pageerror', e => errs.push('pageerror: ' + e.message));
  p.on('console', m => { if (m.type() === 'error') errs.push('console: ' + m.text()); });
}
// content.js ni o'zgartirib berish (layout, completion, id …)
async function patchContent(ctx, fn) {
  await ctx.route(/content\.js$/, async r => {
    const resp = await r.fetch(), c = JSON.parse((await resp.text()).trim().replace(/^window\.PAKET = /, '').replace(/;$/, ''));
    fn(c); r.fulfill({ response: resp, body: 'window.PAKET = ' + JSON.stringify(c) + ';' });
  });
}
async function waitReady(fr) { await fr.waitForFunction(() => window.ISFTPaket && window.ISFTPaket.ready, null, { timeout: 15000 }); }
const navN = fr => fr.evaluate(() => document.querySelectorAll('.nav-i').length);
async function clickStep(fr, i) { await fr.evaluate(i => document.querySelector('.nav-i[data-i="' + i + '"]').click(), i); await sleep(120); }
async function stepIndex(fr, type, nth) { return fr.evaluate(([t, n]) => +[...document.querySelectorAll('.nav-i[data-type="' + t + '"]')][n || 0].dataset.i, [type, nth]); }
async function doneCount(fr) { return fr.evaluate(() => document.querySelectorAll('.nav-i.done').length); }
async function currentType(fr) { return fr.evaluate(() => { const c = document.querySelector('.nav-i[aria-current]'); return c && c.dataset.type; }); }
const curStep = fr => fr.evaluate(() => window.ISFTPaket.debug.step());
// match: har chap katakka javob (kb — faqat klaviatura: fokus + Enter/Space; aks holda bosish). Avval to'ldirilgan kataklar bo'shatiladi.
async function answerMatch(fr, q, right, kb) {
  const sel = `fieldset[data-qid="${q.id}"]`, n = q.pairs.length;
  const act = async (s, key) => { if (kb) await fr.press(s, key || 'Enter'); else await fr.click(s); };
  for (const l of await fr.evaluate(s => [...document.querySelectorAll(s + ' .m-slot.filled')].map(e => e.dataset.l), sel)) { await act(`${sel} .m-slot[data-l="${l}"]`); await act(`${sel} .m-slot[data-l="${l}"]`); }
  for (let i = 0; i < n; i++) { await act(`${sel} .m-slot[data-l="${i}"]`); await act(`${sel} .m-tile[data-r="${right ? i : (i + 1) % n}"]`, ' '); }
}
// sort: kartochka → toifa (kb: Enter kartochkada, Space toifa sarlavhasida)
async function answerSort(fr, q, right, kb) {
  const sel = `fieldset[data-qid="${q.id}"]`;
  for (let k = 0; k < SORT_ITEMS.length; k++) {
    const c = right ? SORT_ITEMS[k].c : (SORT_ITEMS[k].c + 1) % q.categories.length;
    if (kb) { await fr.press(`${sel} .s-card[data-k="${k}"]`, 'Enter'); await fr.press(`${sel} .s-drop[data-c="${c}"]`, ' '); }
    else { await fr.click(`${sel} .s-card[data-k="${k}"]`); await fr.click(`${sel} .s-drop[data-c="${c}"]`); }
  }
}
async function answerQuiz(fr, right, kb) {
  await fr.waitForSelector('form.qform');
  for (const q of QUIZ.questions) {
    const sel = `fieldset[data-qid="${q.id}"]`;
    if (q.type === 'match') await answerMatch(fr, q, right, kb);
    else if (q.type === 'sort') await answerSort(fr, q, right, kb);
    else if (q.type === 'fill') {
      await fr.fill(sel + ' input', right ? '  O‘SADI ' : 'bilmayman');   // apostrof varianti + katta harf + bo'shliq
    } else {
      const corr = q.correct, n = (q.options || ['', '']).length;
      const pick = right ? corr : [[...Array(n).keys()].find(i => !corr.includes(i))];
      for (const i of pick) await fr.check(`${sel} input[value="${i}"]`);
    }
  }
  await fr.click('form.qform [data-act="submit"]'); await sleep(250);
}
async function answerReflect(fr, k) {
  await clickStep(fr, await stepIndex(fr, 'reflect'));
  await fr.click(`.choice[data-k="${k}"]`); await sleep(150);
  return fr.evaluate(() => ({ fb: (document.querySelector('.scn-fb') || {}).textContent, pressed: [...document.querySelectorAll('.choice')].map(b => b.getAttribute('aria-pressed')).join() }));
}
// skrinshot uchun yarim to'ldirilgan match/sort holati
async function demoFill(p) {
  const M = `fieldset[data-qid="${MATCH.id}"]`, S = `fieldset[data-qid="${SORT.id}"]`;
  for (const [a, b] of [[`${M} .m-slot[data-l="0"]`, `${M} .m-tile[data-r="0"]`], [`${M} .m-tile[data-r="2"]`, `${M} .m-slot[data-l="1"]`], [`${S} .s-card[data-k="0"]`, `${S} .s-drop[data-c="0"]`], [`${S} .s-card[data-k="4"]`, `${S} .s-drop[data-c="0"]`], [`${S} .s-card[data-k="3"]`, `${S} .s-drop[data-c="1"]`]]) { await p.click(a); await p.click(b); }
  await p.click(`${M} .m-slot[data-l="3"]`); await p.click(`${S} .s-card[data-k="1"]`); await p.mouse.move(2, 2); await sleep(300);
}
const SHOT = async (p, name, full) => { await p.screenshot({ path: path.join(OUT, name + '.png'), fullPage: !!full }); };

// ---------------------------------------------------------------- umumiy UI tekshiruvlari (iframe yoki sahifa)
async function visitAllContent(fr, page, shotPrefix) {
  const n = await navN(fr), info = await fr.evaluate(() => ({ steps: window.ISFTPaket.debug.steps().length, cover: document.querySelectorAll('.nav-i[data-type="cover"]').length,
    blocks: new Set([...document.querySelectorAll('.nav-i:not([data-type="cover"])')].map(b => b.dataset.block)).size }));
  ok(n === info.steps && info.blocks === NBLOCKS, `Navigatsiyada ${n} qadam (muqova: ${info.cover}), ${info.blocks} blok (kutilgan ${NBLOCKS}; noma'lum «hotspot» e'tiborsiz)`);
  for (let i = 0; i < n; i++) {
    const t = await fr.evaluate(i => document.querySelector('.nav-i[data-i="' + i + '"]').dataset.type, i);
    if (t === 'quiz') continue;
    await clickStep(fr, i);
    if (shotPrefix) await SHOT(page, `${shotPrefix}_${pad2(i)}_${t}`);
  }
  ok(await doneCount(fr) === n - 1, `Barcha kontent qadamlari ✓ belgilandi (${await doneCount(fr)}/${n - 1})`);
  return n;
}
const pad2 = i => String(i).padStart(2, '0');
async function checkBlocks(fr) {
  // sanitizer — fixture matnining to'liq HTML'i bo'yicha (pleyerning o'z sanitizeri)
  const san = await fr.evaluate(html => {
    const d = document.createElement('div'); d.innerHTML = window.ISFTPaket.debug.sanitize(html);
    return { script: !!d.querySelector('script,style,iframe'), on: [...d.querySelectorAll('*')].some(e => [...e.attributes].some(a => /^on/i.test(a.name) || a.name === 'style')),
      js: !!d.querySelector('a[href^="javascript"]'), imgs: [...d.querySelectorAll('img')].map(i => i.getAttribute('src')),
      ext: [...d.querySelectorAll('a[href]')].map(a => [a.getAttribute('href'), a.target, a.rel]), h2: d.querySelectorAll('h2').length, tbl: d.querySelectorAll('.tbl table').length,
      fig: d.querySelectorAll('figure > img + figcaption').length };
  }, TEXT.html);
  ok(!san.script && !san.on && !san.js && (await fr.evaluate(() => window.__xss)) === undefined, "Sanitizer: script/style/iframe, on*/style atributlari, javascript: havola olib tashlandi, XSS yo'q");
  ok(JSON.stringify(san.imgs) === JSON.stringify(['assets/img/fig1.png', 'assets/img/fig2.png']), `Rasmlar: faqat nisbiy assets/ (https/http/data/«java\\tscript:» olib tashlandi): ${san.imgs.join(', ')}`);
  ok(san.ext.length === 1 && san.ext[0][0] === 'https://isft.uz/kutubxona' && san.ext[0][1] === '_blank' && /noopener/.test(san.ext[0][2]), "Tashqi havola: faqat https, target=_blank rel=noopener");
  ok(san.h2 === 3 && san.tbl === 2 && san.fig === 2, `Ruxsat etilgan teglar saqlandi (h2: ${san.h2}, jadval: ${san.tbl}, figure+figcaption: ${san.fig})`);
  // reja → bayonot (heading) + matn sarlavhasiga havola
  await clickStep(fr, await stepIndex(fr, 'plan'));
  const st = await fr.evaluate(() => ({ h1: document.querySelector('.statement .bh h1') && document.querySelector('.statement .bh h1').textContent, reja: (document.querySelector('.reja') || {}).textContent,
    links: [...document.querySelectorAll('.plan li')].map(li => !!li.querySelector('button.link')).join() }));
  const PLAN = CONTENT.blocks.find(b => b.type === 'plan');
  ok(st.h1 === PLAN.heading && st.reja === 'Reja:', `Reja bayonot sifatida: «${st.h1}» + «${st.reja}»`);
  ok(st.links === 'true,true,true,false', `Reja: mos sarlavhalar havola, mos kelmagani oddiy matn (${st.links})`);
  await fr.evaluate(() => [...document.querySelectorAll('.plan button.link')].find(b => b.textContent === 'Bozor muvozanati').click()); await sleep(200);
  const foc = await fr.evaluate(() => document.activeElement && document.activeElement.tagName + ':' + document.activeElement.textContent);
  ok((await currentType(fr)) === 'text' && foc === 'H2:Bozor muvozanati', `Reja havolasi kerakli matn qadamidagi sarlavhaga o'tkazdi va fokusladi (${foc})`);
  // galereya (slides display=images)
  await clickStep(fr, await stepIndex(fr, 'slides'));
  const NS = SLIDES.slides.length;
  const g0 = await fr.evaluate(() => ({ c: document.querySelector('.counter').textContent, th: document.querySelectorAll('.thumbs button').length, fs: !!document.querySelector('.fs-btn') }));
  await fr.focus('.deck'); await fr.press('.deck', 'ArrowRight'); await sleep(80);
  const g1 = await fr.evaluate(() => ({ c: document.querySelector('.counter').textContent, img: (document.querySelector('.stage img') || {}).getAttribute && document.querySelector('.stage img').getAttribute('src'), step: window.ISFTPaket.debug.step() }));
  await fr.click('.thumbs button:nth-child(4)'); await sleep(60);
  const g2 = await fr.evaluate(() => document.querySelector('.counter').textContent);
  await fr.press('.deck', 'End'); await sleep(60);
  const g3 = await fr.evaluate(() => ({ c: document.querySelector('.counter').textContent, next: document.querySelector('.nav-a.r').disabled }));
  ok(g0.c === `1 / ${NS}` && g0.th === NS && g0.fs, `Galereya: hisoblagich «${g0.c}», ${g0.th} ta eskiz, «To'liq ekran» tugmasi`);
  ok(g1.c === `2 / ${NS}` && g1.img === 'assets/slides/s2.png' && g2 === `4 / ${NS}` && g3.c === `${NS} / ${NS}` && g3.next, `Galereya: → klaviatura, eskiz bosish, End (${g1.c}, ${g2}, ${g3.c}); qadam o'zgarmadi`);
  await fr.click('.deck-bar [aria-controls]');
  const notes = await fr.evaluate(() => ({ h: document.querySelector('.notes').hidden, e: document.querySelector('.deck-bar [aria-controls]').getAttribute('aria-expanded') }));
  ok(!notes.h && notes.e === 'true', 'Izohlar tugmasi ochadi (aria-expanded)');
  const dl = await fr.evaluate(() => [...document.querySelectorAll('.t-slides .tools a')].map(a => a.textContent.trim() + '|' + a.getAttribute('href')));
  ok(dl.includes("PDF ko'rinishida ochish|assets/taqdimot.pdf") && dl.includes('Taqdimotni yuklab olish|assets/taqdimot.pptx'), 'PDF ochish va taqdimotni yuklab olish havolalari');
  // video
  await clickStep(fr, await stepIndex(fr, 'video'));
  const v = await fr.evaluate(() => { const f = document.querySelector('.video iframe'); return f && { src: f.src, title: f.title, allow: f.allow, fb: !!document.querySelector('a[href^="https://www.youtube.com/watch?v=dQw4w9WgXcQ"]') }; });
  ok(v && v.src.startsWith('https://www.youtube-nocookie.com/embed/dQw4w9WgXcQ?') && /start=15/.test(v.src) && /rel=0/.test(v.src) && v.title && /encrypted-media/.test(v.allow) && v.fb,
    "Video: youtube-nocookie embed (start, rel=0, title, allow) + «YouTube'da ochish»");
  await clickStep(fr, await stepIndex(fr, 'file'));
  const f = await fr.evaluate(() => [...document.querySelectorAll('.filecard a')].map(a => a.getAttribute('href')));
  ok(f.length === 2 && f.every(h => h === 'assets/qollanma.pdf'), 'Fayl bloki: ochish + yuklab olish (nisbiy havola)');
  // adabiyotlar, xulosalar, bo'lim
  await clickStep(fr, await stepIndex(fr, 'refs'));
  const rf = await fr.evaluate(() => ({ n: document.querySelectorAll('ol.refs li').length, a: [...document.querySelectorAll('ol.refs a')].map(a => a.getAttribute('href') + '|' + a.rel) }));
  const RF = CONTENT.blocks.find(b => b.type === 'refs');
  ok(rf.n === RF.items.length && rf.a.length === 2 && rf.a.every(x => /^https:\/\/[^|]+\|noopener noreferrer$/.test(x)), `Adabiyotlar: ${rf.n} ta raqamli band, havolalar faqat https (${rf.a.map(x => x.split('|')[0]).join(', ')}); javascript: — matn`);
  await clickStep(fr, await stepIndex(fr, 'keypoints'));
  ok((await fr.evaluate(() => document.querySelectorAll('ul.kp li').length)) === CONTENT.blocks.find(b => b.type === 'keypoints').items.length, 'Asosiy xulosalar: ajratilgan kartochkalar ro\'yxati');
  await clickStep(fr, await stepIndex(fr, 'section'));
  ok((await fr.evaluate(() => document.querySelector('.t-section .band h1.pill').textContent)) === 'VIDEODARS', "Bo'lim ajratgichi: yashil «tabletka» — VIDEODARS");
}
async function checkLightbox(fr) {
  await clickStep(fr, await stepIndex(fr, 'text'));
  const z = await fr.evaluate(() => { const b = document.querySelector('.prose .zoom'); return b && { tag: b.tagName, label: b.getAttribute('aria-label'), lazy: b.querySelector('img').getAttribute('loading') }; });
  ok(z && z.tag === 'BUTTON' && /kattalashtirish/.test(z.label) && z.lazy === 'lazy', `Matndagi rasm — klaviatura bilan ochiladigan tugma, lazy-load (${z && z.label})`);
  await fr.focus('.prose .zoom'); await fr.press('.prose .zoom', 'Enter'); await sleep(120);
  const o = await fr.evaluate(() => { const lb = document.querySelector('.lb'); return lb && { vis: !lb.hidden, modal: lb.getAttribute('aria-modal'), img: lb.querySelector('img').getAttribute('src'), cap: lb.querySelector('figcaption').textContent, foc: document.activeElement.classList.contains('lb-x') }; });
  ok(o && o.vis && o.modal === 'true' && o.img === 'assets/img/fig1.png' && /^1\.1-rasm\./.test(o.cap) && o.foc, `Lightbox ochildi (aria-modal, izoh «${o && o.cap.slice(0, 20)}…», fokus «Yopish» da)`);
  const stepBefore = await curStep(fr);
  await fr.press('.lb-x', 'ArrowRight'); await sleep(60);
  ok((await curStep(fr)) === stepBefore, 'Lightbox ochiqligida ← → qadamni almashtirmaydi');
  await fr.press('.lb-x', 'Escape'); await sleep(80);
  const c = await fr.evaluate(() => ({ hid: document.querySelector('.lb').hidden, back: document.activeElement.classList.contains('zoom') }));
  ok(c.hid && c.back, 'Esc lightboxni yopadi, fokus rasmga qaytadi');
  await fr.click('.prose .zoom'); await sleep(80); await fr.click('.lb-x'); await sleep(80);
  ok(await fr.evaluate(() => document.querySelector('.lb').hidden), '«Yopish» tugmasi lightboxni yopadi');
}

// ---------------------------------------------------------------- SCORM
async function runScorm(br, base, kind) {
  section(kind === 'scorm12' ? 'SCORM 1.2' : 'SCORM 2004');
  const is12 = kind === 'scorm12';
  const T = await newCtx(br, {}, kind), page = T.page;
  await page.goto(base + '/lms.html');
  const url = base + PKG + 'index.html';
  await page.evaluate(([k, u]) => window.launch(k, u), [kind, url]);
  const fr = () => page.frame({ name: 'sco' });
  await sleep(200); await waitReady(fr());
  const S = i => page.evaluate(i => window.LMS.sessions[i], i);
  let s0 = await S(0);
  ok((await fr().evaluate(() => window.ISFTPaket.mode)) === kind, `API topildi (iframe → window.parent) — rejim ${kind}`);
  ok(s0.inits === 1 && s0.calls[0].fn === (is12 ? 'LMSInitialize' : 'Initialize'), 'Initialize bir marta, birinchi chaqiruv');
  ok(is12 ? s0.values['cmi.core.lesson_status'] === 'incomplete' : s0.values['cmi.completion_status'] === 'incomplete', 'Boshlanishda holat: incomplete');
  ok(!(await fr().$('.banner')), "Ko'rish rejimi banneri yo'q");
  ok((await fr().evaluate(() => document.querySelector('.who') && document.querySelector('.who').textContent)) === 'Ali Valiyev', 'Talaba ismi LMS dan («Familiya, Ism» → «Ism Familiya»)');
  const N = await visitAllContent(fr(), page, null);
  await checkBlocks(fr());
  s0 = await S(0);
  ok(s0.commits > 0, `Qadamlarni ko'rishda Commit chaqirildi (${s0.commits})`);
  const sd0 = s0.values['cmi.suspend_data'];
  ok(sd0 && sd0.length <= (is12 ? 4096 : 64000), `suspend_data yozildi (${sd0.length} belgi)`);
  if (!is12) ok(+s0.values['cmi.progress_measure'] > 0.8 && +s0.values['cmi.progress_measure'] < 1, `progress_measure = ${s0.values['cmi.progress_measure']}`);
  // test — noto'g'ri
  const qi = await stepIndex(fr(), 'quiz');
  await clickStep(fr(), qi);
  await fr().click('[data-act="start"]');
  const ord1 = await fr().evaluate(() => [...document.querySelectorAll('fieldset.q')].map(f => f.dataset.qid).join());
  {   // tugallanmagan javoblar (qoralama) suspend_data'ga yoziladi: match — [o'ng indeks | -1], sort — [toifa | -1]
    await fr().fill(`fieldset[data-qid="${FILLQ.id}"] input`, 'qoralama');
    await fr().click(`fieldset[data-qid="${MATCH.id}"] .m-slot[data-l="1"]`); await fr().click(`fieldset[data-qid="${MATCH.id}"] .m-tile[data-r="3"]`);
    await fr().click(`fieldset[data-qid="${SORT.id}"] .s-card[data-k="4"]`); await fr().click(`fieldset[data-qid="${SORT.id}"] .s-drop[data-c="0"]`);
    await sleep(600);
    const sd = (await S(0)).values['cmi.suspend_data'], d = (JSON.parse(sd).q[QUIZ.id] || {}).d || [], qi2 = t => QUIZ.questions.findIndex(q => q.type === t);
    ok(JSON.stringify(d[qi2('match')]) === '[-1,3,-1,-1]' && JSON.stringify(d[qi2('sort')]) === '[-1,-1,-1,-1,0,-1]' && d[qi2('fill')] === 'qoralama' && sd.length <= (is12 ? 4096 : 64000),
      `Tugallanmagan javoblar holatda (qoralama: match ${JSON.stringify(d[qi2('match')])}, sort ${JSON.stringify(d[qi2('sort')])}; ${sd.length} belgi)`);
  }
  await answerQuiz(fr(), false, is12);   // SCORM 1.2 — match/sort faqat klaviatura bilan, 2004 — bosish bilan
  s0 = await S(0);
  const st0 = is12 ? s0.values['cmi.core.lesson_status'] : s0.values['cmi.success_status'] + '/' + s0.values['cmi.completion_status'];
  ok(is12 ? st0 === 'failed' : st0 === 'failed/incomplete', `Noto'g'ri javoblar → ${st0}`);
  const raw0 = is12 ? s0.values['cmi.core.score.raw'] : s0.values['cmi.score.raw'];
  ok(raw0 === '0' && (is12 || s0.values['cmi.score.scaled'] === '0'), `Ball 0 (raw=${raw0}${is12 ? '' : ', scaled=' + s0.values['cmi.score.scaled']}), min/max 0/100`);
  ok(s0.inter.length === QUIZ.questions.length && s0.inter.every(i => i.id && i.type && i.result === (is12 ? 'wrong' : 'incorrect') && (is12 ? i.time : i.timestamp)),
    `interactions: ${s0.inter.length} ta (id, type, javob, result, vaqt)`);
  const types = s0.inter.map(i => i.type + ':' + (is12 ? i.student_response : i.learner_response)).join(' | ');
  ok(/choice/.test(types) && /true-false:(f|false)/.test(types) && /fill-in:bilmayman/.test(types), 'interaction turlari va javob formati: ' + types);
  {   // match va sort → «matching» interaction (LMS sintaksis tekshiruvidan o'tgan): javob va to'g'ri javob namunasi
    const mi = s0.inter.find(i => i.id === QUIZ.id + '_' + MATCH.id) || {}, si = s0.inter.find(i => i.id === QUIZ.id + '_' + SORT.id) || {}, rk = is12 ? 'student_response' : 'learner_response';
    ok(mi.type === 'matching' && mi[rk] === (is12 ? EXP.m12(false) : EXP.m04(false)) && mi['correct_responses.0.pattern'] === (is12 ? EXP.m12(true) : EXP.m04(true)) && mi.result === (is12 ? 'wrong' : 'incorrect'),
      `match (${is12 ? 'klaviatura' : 'bosish'} bilan, noto'g'ri): type=matching, javob «${mi[rk]}», namuna «${mi['correct_responses.0.pattern']}», result=${mi.result}`);
    ok(si.type === 'matching' && si[rk] === (is12 ? EXP.s12(false) : EXP.s04(false)) && si['correct_responses.0.pattern'] === (is12 ? EXP.s12(true) : EXP.s04(true)) && si.result === (is12 ? 'wrong' : 'incorrect'),
      `sort (${is12 ? 'klaviatura' : 'bosish'} bilan, noto'g'ri): type=matching (manba — kartochka, nishon — toifa), javob «${si[rk]}», result=${si.result}`);
    const fbp = await fr().evaluate(([m, s]) => { const f = id => document.querySelector('.fb[data-qid="' + id + '"]'); return [m, s].map(id => f(id) && { no: f(id).classList.contains('no'), mine: f(id).querySelectorAll('.fb-a:not(.fb-c) .fb-pairs li.no').length, corr: [...f(id).querySelectorAll('.fb-c .fb-pairs li')].map(li => li.textContent.replace(/\s*→\s*/, '→')) }); }, [MATCH.id, SORT.id]);
    ok(fbp[0] && fbp[0].no && fbp[0].mine === MATCH.pairs.length && JSON.stringify(fbp[0].corr) === JSON.stringify(MATCH.pairs.map(p => p.left + '→' + p.right)), `match izohi: sizning juftliklaringiz (${fbp[0] && fbp[0].mine} ta xato) va to'g'ri juftliklar ko'rsatildi`);
    ok(fbp[1] && fbp[1].no && fbp[1].mine === SORT_ITEMS.length && JSON.stringify(fbp[1].corr) === JSON.stringify(SORT_ITEMS.map(it => it.text + '→' + SORT.categories[it.c].title)), "sort izohi: har kartochkaning to'g'ri toifasi ko'rsatildi");
    const sdA = JSON.parse(s0.values['cmi.suspend_data']).q[QUIZ.id];
    ok(Array.isArray(sdA.a) && sdA.a.length === QUIZ.questions.length && !sdA.d && s0.values['cmi.suspend_data'].length <= (is12 ? 4096 : 64000), `Barcha savol turlari javoblari bilan suspend_data ${s0.values['cmi.suspend_data'].length} belgi (qoralama tozalandi)`);
  }
  const fb = await fr().evaluate(() => ({ n: document.querySelectorAll('.fb.no').length, live: document.querySelector('.score[aria-live]') !== null, retry: !!document.querySelector('[data-act="retry"]'), expl: document.querySelectorAll('.fb-e').length }));
  ok(fb.n === QUIZ.questions.length && fb.live && fb.retry && fb.expl >= 3, `Fikr-mulohaza: har savol noto'g'ri deb belgilandi + izoh, aria-live, «Qayta urinish» (${JSON.stringify(fb)})`);
  if (is12) await SHOT(page, 's12_quiz_failed', true);
  // qayta ishga tushirish (resume)
  await page.evaluate(() => window.unload()); await sleep(400);
  s0 = await S(0);
  const fin = s0.calls.filter(c => /Finish|Terminate/.test(c.fn));
  ok(s0.finishes === 1 && fin.length === 1, `pagehide → ${is12 ? 'LMSFinish' : 'Terminate'} bir marta (${fin.length})`);
  const tail = s0.calls.slice(-4).map(c => c.fn + (c.args[0] && /exit|session_time/.test(c.args[0]) ? '(' + c.args[0] + ')' : ''));
  ok(/Commit/.test(tail[tail.length - 2]) && /Finish|Terminate/.test(tail[tail.length - 1]), 'Yakunlashdan oldin Commit: ' + tail.join(' → '));
  const exit0 = s0.values[is12 ? 'cmi.core.exit' : 'cmi.exit'], stime = s0.values[is12 ? 'cmi.core.session_time' : 'cmi.session_time'];
  ok(exit0 === 'suspend', 'Tugallanmagan — exit=suspend');
  ok(is12 ? /^\d{2,4}:\d{2}:\d{2}\.\d{2}$/.test(stime) : /^PT\d+H\d+M[\d.]+S$/.test(stime), 'session_time formati: ' + stime);
  ok(s0.values[is12 ? 'cmi.core.lesson_location' : 'cmi.location'] === QUIZ.id, `location = joriy qadam kaliti (${s0.values[is12 ? 'cmi.core.lesson_location' : 'cmi.location']})`);
  await page.evaluate(([k, u]) => window.launch(k, u), [kind, url]); await sleep(300); await waitReady(fr());
  let s1 = await S(1);
  ok(s1.values[is12 ? 'cmi.core.entry' : 'cmi.entry'] === 'resume' && s1.inits === 1, 'Ikkinchi sessiya: entry=resume');
  ok((await currentType(fr())) === 'quiz', 'Resume: location bo\'yicha test qadamiga qaytdi');
  ok(await doneCount(fr()) === N - 1, `Resume: ko'rilgan qadamlar ✓ saqlangan (${await doneCount(fr())})`);
  const res1 = await fr().evaluate(() => ({ score: document.querySelector('.ring span') && document.querySelector('.ring span').textContent, retry: !!document.querySelector('[data-act="retry"]') }));
  ok(res1.score === '0%' && res1.retry, `Resume: oxirgi test natijasi va javoblar tiklandi (${JSON.stringify(res1)})`);
  // qayta urinish — to'g'ri
  await fr().click('[data-act="retry"]');
  const ord2 = await fr().evaluate(() => [...document.querySelectorAll('fieldset.q')].map(f => f.dataset.qid).join());
  await answerQuiz(fr(), true, !is12);   // SCORM 2004 — match/sort faqat klaviatura bilan
  s1 = await S(1);
  ok(is12 ? s1.values['cmi.core.lesson_status'] === 'passed' : s1.values['cmi.success_status'] === 'passed' && s1.values['cmi.completion_status'] === 'completed',
    `To'g'ri javoblar → ${is12 ? s1.values['cmi.core.lesson_status'] : s1.values['cmi.success_status'] + '/' + s1.values['cmi.completion_status']}`);
  ok((is12 ? s1.values['cmi.core.score.raw'] : s1.values['cmi.score.raw']) === '100' && (is12 || (s1.values['cmi.score.scaled'] === '1' && s1.values['cmi.progress_measure'] === '1')),
    'Ball 100' + (is12 ? '' : ', scaled=1, progress_measure=1'));
  ok(s1.inter.length === QUIZ.questions.length && s1.inter.every(i => i.result === 'correct'), "Ikkinchi urinish interactions: hammasi correct (fill-in: «  O‘SADI » ≈ «o'sadi»)");
  {   // fill-in: har bir qabul qilinadigan javob — alohida correct_responses.n.pattern
    const fq = QUIZ.questions.find(q => q.type === 'fill'), fi = s1.inter.find(i => i.type === 'fill-in');
    const pats = fi ? Object.keys(fi).filter(k => /^correct_responses\.\d+\.pattern$/.test(k)).sort().map(k => fi[k]) : [];
    const want = fq.answers.map(a => is12 ? a : '{case_matters=false}' + a);
    ok(JSON.stringify(pats) === JSON.stringify(want), `fill-in: har muqobil javob alohida pattern (${pats.join(' | ')})`);
    const ch = s1.inter.filter(i => i.type !== 'fill-in');
    ok(ch.every(i => i['correct_responses.0.pattern'] && !('correct_responses.1.pattern' in i)), 'choice/true-false/matching: bitta correct_responses.0.pattern');
    const mi = s1.inter.find(i => i.id === QUIZ.id + '_' + MATCH.id) || {}, si = s1.inter.find(i => i.id === QUIZ.id + '_' + SORT.id) || {}, rk = is12 ? 'student_response' : 'learner_response';
    ok(mi.type === 'matching' && mi[rk] === (is12 ? EXP.m12(true) : EXP.m04(true)) && mi.result === 'correct' && si.type === 'matching' && si[rk] === (is12 ? EXP.s12(true) : EXP.s04(true)) && si.result === 'correct',
      `match/sort (${is12 ? 'bosish' : 'klaviatura'} bilan, to'g'ri): «${mi[rk]}» · «${si[rk]}» → correct`);
  }
  ok((await fr().evaluate(() => document.querySelector('.chip').textContent)).startsWith("O'tdi") && (await doneCount(fr())) === N, 'UI: «O\'tdi» va barcha qadamlar ✓');
  ok(ord1 !== '' && ord2 !== '' && QUIZ.questions.every(q => ord2.split(',').includes(q.id)), `Aralashtirish: urinish tartiblari (${ord1} | ${ord2})`);
  // mulohaza (reflect) — baholanmaydigan interaction: result=neutral
  const rf = await answerReflect(fr(), 1);
  s1 = await S(1);
  const ri = s1.inter[s1.inter.length - 1] || {};
  ok(rf.fb === REFLECT.options[1].feedback && rf.pressed === 'false,true', `Mulohaza: tanlov → izoh pufakchasi (${rf.fb.slice(0, 30)}…)`);
  ok(s1.inter.length === QUIZ.questions.length + 1 && ri.id === REFLECT.id && ri.type === 'choice' && ri.result === 'neutral' && (is12 ? ri.student_response : ri.learner_response) === 'b'
     && !Object.keys(ri).some(k => /^correct_responses/.test(k)), `Mulohaza interaction: type=choice, result=neutral, javob «b», to'g'ri javob yo'q (${JSON.stringify(ri)})`);
  ok((is12 ? s1.values['cmi.core.lesson_status'] === 'passed' : s1.values['cmi.success_status'] === 'passed'), 'Mulohaza natijaga ta\'sir qilmaydi (passed qoldi)');
  if (is12) await SHOT(page, 's12_quiz_passed', true);
  await page.evaluate(() => window.unload()); await sleep(400);
  s1 = await S(1);
  ok(s1.finishes === 1 && s1.values[is12 ? 'cmi.core.exit' : 'cmi.exit'] === (is12 ? '' : 'normal'), `Yakunlangan — exit="${s1.values[is12 ? 'cmi.core.exit' : 'cmi.exit']}", Finish bir marta`);
  ok(JSON.parse(s1.values['cmi.suspend_data']).r[REFLECT.id] === 1, 'Mulohaza tanlovi holatda saqlandi (suspend_data.r)');
  // o'tgan natija: suspend_data'dan javoblar tushib qolsa ham qayta urinish berilmaydi; keyingi «muvaffaqiyatsiz» holat LMS'dagi passed'ni pasaytirmaydi
  const sdPassed = s1.values['cmi.suspend_data'];
  for (const [label, drop] of [['javoblar tushib qolgan holat', false], ["holatda p:0, s:0 (keyingi muvaffaqiyatsiz natija)", true]]) {
    const stx = JSON.parse(sdPassed); Object.values(stx.q).forEach(q => { delete q.a; if (drop) { q.p = 0; q.s = 0; } });
    await page.evaluate(([is12, sd]) => Object.assign(window.LMS.persist, { entry: 'resume', status: is12 ? 'passed' : 'completed', success: 'passed', suspend: sd, location: '', raw: '100' }), [is12, JSON.stringify(stx)]);
    await page.evaluate(([k, u]) => window.launch(k, u), [kind, url]); await sleep(300); await waitReady(fr());
    await clickStep(fr(), qi);
    const si = (await page.evaluate(() => window.LMS.sessions.length)) - 1, sx = await S(si);
    const sets = sx.calls.filter(c => /SetValue/.test(c.fn) && /lesson_status|success_status|score\.raw/.test(c.args[0])).map(c => c.args[0].split('.').pop() + '=' + c.args[1]);
    const stNow = is12 ? sx.values['cmi.core.lesson_status'] : sx.values['cmi.success_status'];
    ok(stNow === 'passed' && !sets.some(x => /=(failed|incomplete|completed|unknown)$/.test(x) && !/completion/.test(x)) && !sets.some(x => /^raw=/.test(x) && x !== 'raw=100'),
      `${label}: LMS holati passed qoldi, pasaytirilmadi (${sets.join(', ') || 'yozuv yo\'q'})`);
    if (!drop) {
      const ui = await fr().evaluate(() => ({ retry: !!document.querySelector('[data-act="retry"],[data-act="start"]'), ring: document.querySelector('.ring span') && document.querySelector('.ring span').textContent, chip: document.querySelector('.chip').textContent }));
      ok(!ui.retry && ui.ring === '100%' && ui.chip.startsWith("O'tdi"), `${label}: qayta urinish tugmasi yo'q, natija 100%, «O'tdi» (${JSON.stringify(ui)})`);
    }
    await page.evaluate(() => window.unload()); await sleep(300);
  }
  const allErr = (await page.evaluate(() => window.LMS.sessions.map(s => s.errors))).flat();
  ok(allErr.length === 0, `LMS API xato kodlari yo'q (${allErr.slice(0, 3).join('; ')})`);
  const maxSd = Math.max(...(await page.evaluate(() => window.LMS.sessions.flatMap(s => s.calls.filter(c => /SetValue/.test(c.fn) && c.args[0] === 'cmi.suspend_data').map(c => c.args[1].length)))));
  ok(maxSd <= (is12 ? 4096 : 64000), `suspend_data maksimal uzunligi ${maxSd}`);
  if (is12) {
    // 1.2: ixcham kodlash 4096 dan oshmaydi (sun'iy katta holat)
    await page.evaluate(([k, u]) => window.launch(k, u), [kind, url]); await sleep(300); await waitReady(fr());
    const L = await fr().evaluate(() => { const q = {}; for (let i = 0; i < 30; i++) q['b' + i] = { n: 3, s: 40, b: 60, p: 0, sd: 4294967295, a: Array.from({ length: 60 }, () => 'juda uzun javob matni '.repeat(3)) }; return window.ISFTPaket.debug.encodeState({ h: 1, v: '1'.repeat(60), c: 5, q }, 4096).length; });
    ok(L <= 4096, `Katta holat 4096 ga sig'diriladi (ixcham kodlash): ${L}`);
    await page.evaluate(() => window.unload()); await sleep(300);
  }
  ok(T.errs.length === 0, 'Konsol xatolari yo\'q' + (T.errs.length ? ': ' + T.errs.slice(0, 3).join(' | ') : ''));
  ok(T.foreign.length === 0, 'Tashqi tarmoq so\'rovlari yo\'q (YouTube dan tashqari)' + (T.foreign.length ? ': ' + T.foreign.slice(0, 3).join(' ') : ''));
  await T.ctx.close();
}

// ---------------------------------------------------------------- tracking.mode = none (API bo'lsa ham)
async function runModeNone(br, base) {
  section('mode=none');
  const T = await newCtx(br, {}, 'none'), page = T.page;
  await patchContent(T.ctx, c => { c.tracking.mode = 'none'; });
  await page.goto(base + '/lms.html');
  await page.evaluate(u => window.launch('scorm12', u), base + PKG + 'index.html'); await sleep(200);
  let fr = page.frame({ name: 'sco' }); await waitReady(fr);
  const s = await page.evaluate(() => window.LMS.sessions[0]);
  ok((await fr.evaluate(() => window.ISFTPaket.mode)) === 'standalone' && s.calls.length === 0, "tracking.mode=none: LMS API chaqirilmaydi, jim mustaqil rejim");
  ok(!(await fr.$('.banner')), "?preview=1 siz — banner yo'q");
  await page.evaluate(u => window.launch('scorm12', u), base + PKG + 'index.html?preview=1'); await sleep(300);
  fr = page.frame({ name: 'sco' }); await waitReady(fr);
  ok((await fr.evaluate(() => window.ISFTPaket.mode)) === 'preview' && /natija LMS'ga yuborilmaydi/.test(await fr.evaluate(() => document.querySelector('.banner').textContent)),
    "tracking.mode=none + ?preview=1 → «Ko'rish rejimi» banneri");
  ok(T.errs.length === 0, "Konsol xatolari yo'q");
  await T.ctx.close();
}

// ---------------------------------------------------------------- xAPI
async function runXapi(br, base, lrsBase) {
  section('xAPI');
  const T = await newCtx(br, {}, 'xapi'), page = T.page;
  const reg = '3f2504e0-4f89-41d3-9a0c-0305e82c3301', auth = 'Basic dGVzdDpzZWNyZXQ=';
  const actorIn = { name: ['Ali Valiyev'], account: [{ accountServiceHomePage: 'https://lms.isft.uz', accountName: 'u123' }] };
  const actId = 'https://isft.uz/xapi/paket/12/5';
  const q = new URLSearchParams({ endpoint: lrsBase + '/xapi/', auth, actor: JSON.stringify(actorIn), registration: reg, activity_id: actId });
  const url = base + PKG + 'index.html?' + q.toString();
  LRS.failFirst = 1;   // birinchi POST 503 — navbat va qayta urinish sinovi
  await page.goto(url); await waitReady(page);
  ok((await page.evaluate(() => window.ISFTPaket.mode)) === 'xapi', 'Launch parametrlari (endpoint, auth, actor, registration, activity_id) → xAPI rejimi');
  ok(!(await page.$('.banner')), "Ko'rish rejimi banneri yo'q");
  const N = await visitAllContent(page, page, null);
  const qi = await stepIndex(page, 'quiz');
  await clickStep(page, qi); await page.click('[data-act="start"]'); await answerQuiz(page, false);
  await sleep(2600);   // 503 dan keyin 2 s qayta urinish
  ok(LRS.posts >= 2 && LRS.statements.some(s => s.verb.id.endsWith('/initialized')), `503 dan keyin qayta yuborildi (POST: ${LRS.posts})`);
  await page.reload(); await waitReady(page); await sleep(500);
  const vAll = LRS.statements.map(s => s.verb.id.split('/').pop()), v1 = vAll.slice(0, vAll.indexOf('terminated') + 1);
  ok(v1[0] === 'initialized' && v1.filter(x => x === 'experienced').length === NBLOCKS && v1.filter(x => x === 'answered').length === QUIZ.questions.length
     && v1.includes('failed') && v1.indexOf('terminated') > v1.indexOf('failed'), '1-sessiya fe\'llari (experienced — har blokka bir marta): ' + compact(v1));
  ok((await currentType(page)) === 'quiz' && (await doneCount(page)) === N - 1, 'State API orqali resume: test qadami va ✓ belgilar tiklandi');
  ok(LRS.stateReq.some(r => r.m === 'PUT') && LRS.stateReq.filter(r => r.m === 'GET').length >= 2 && LRS.stateReq.every(r => r.key.endsWith('|isft-state|' + reg) && r.auth === auth && r.ver === '1.0.3'),
    `State API: GET/PUT stateId=isft-state + registration + auth (${LRS.stateReq.map(r => r.m).join(',')})`);
  await page.click('[data-act="retry"]'); await answerQuiz(page, true); await sleep(400);
  await answerReflect(page, 0); await sleep(300);
  await page.goto(base + '/lms.html'); await sleep(1200);   // talaba LMS'ga qaytdi (about:blank ga Playwright goto keepalive so'rovlarini uzadi — real yopilishga mos emas)
  const st = LRS.statements, verbs = st.map(s => s.verb.id.split('/').pop());
  const n0 = verbs.indexOf('terminated');
  const v2 = verbs.slice(n0 + 1);
  ok(v2[0] === 'initialized' && v2.filter(x => x === 'answered').length === QUIZ.questions.length && v2.indexOf('passed') < v2.indexOf('completed') && v2[v2.length - 1] === 'terminated',
    '2-sessiya fe\'llari: ' + compact(v2));
  ok(st.every(s => /^http:\/\/adlnet\.gov\/expapi\/verbs\/\w+$/.test(s.verb.id) && s.verb.display && s.verb.display['en-US']), 'Hamma fe\'llar ADL IRI + display');
  const actorOut = { objectType: 'Agent', name: 'Ali Valiyev', account: { homePage: 'https://lms.isft.uz', name: 'u123' } };
  ok(st.every(s => JSON.stringify(s.actor) === JSON.stringify(actorOut)), 'Actor normallashtirildi (massiv/TinCan account → xAPI 1.0.3 account)');
  ok(st.every(s => s.context && s.context.registration === reg), 'context.registration hamma statementda');
  const child = st.filter(s => /experienced|answered|responded|passed|failed/.test(s.verb.id) && s.object.id !== actId);   // kurs darajasidagi passed/failed — ota-activity'siz
  ok(child.every(s => s.context.contextActivities.parent[0].id === actId), 'Blok/savol statementlarida contextActivities.parent = kurs activity');
  ok(st.filter(s => s.verb.id.endsWith('/experienced')).every(s => s.object.id.startsWith(actId + '/block/')), 'experienced obyekti: activity_id + "/block/<id>"');
  const ans = st.filter(s => s.verb.id.endsWith('/answered'));
  ok(ans.every(s => typeof s.result.success === 'boolean' && typeof s.result.response === 'string' && s.object.definition.interactionType), 'answered: result.success, result.response, interactionType');
  const fq = QUIZ.questions.find(q => q.type === 'fill'), fAns = ans.filter(s => s.object.definition.interactionType === 'fill-in');
  ok(fAns.length >= 1 && fAns.every(s => JSON.stringify(s.object.definition.correctResponsesPattern) === JSON.stringify(fq.answers)),
    'fill-in: correctResponsesPattern — har muqobil javob alohida element (' + (fAns[0] ? JSON.stringify(fAns[0].object.definition.correctResponsesPattern) : '-') + ')');
  ok(ans.filter(s => s.object.definition.interactionType !== 'fill-in').every(s => s.object.definition.correctResponsesPattern.length === 1), 'choice/true-false/matching: bitta correctResponsesPattern');
  {
    const byQ = id => ans.filter(s => s.object.id === actId + '/block/' + QUIZ.id + '/q/' + id), mm = byQ(MATCH.id), ss = byQ(SORT.id);
    const defOk = (s, src, tgt, sp, tp) => { const d = s.object.definition; return d.interactionType === 'matching' && JSON.stringify(d.source.map(x => x.id)) === JSON.stringify(src.map((_, i) => sp + (i + 1)))
      && JSON.stringify(d.source.map(x => x.description.uz)) === JSON.stringify(src) && JSON.stringify(d.target.map(x => x.id)) === JSON.stringify(tgt.map((_, i) => tp + (i + 1))) && JSON.stringify(d.target.map(x => x.description.uz)) === JSON.stringify(tgt) && !d.choices; };
    ok(mm.length === 2 && mm.every(s => defOk(s, MATCH.pairs.map(p => p.left), MATCH.pairs.map(p => p.right), 'l', 'r') && s.object.definition.correctResponsesPattern[0] === EXP.m04(true))
       && mm[0].result.response === EXP.m04(false) && mm[0].result.success === false && mm[1].result.response === EXP.m04(true) && mm[1].result.success === true,
      `match → xAPI «matching»: source/target massivlari, correctResponsesPattern, javob «${mm[0] && mm[0].result.response}» → «${mm[1] && mm[1].result.response}»`);
    ok(ss.length === 2 && ss.every(s => defOk(s, SORT_ITEMS.map(i => i.text), SORT.categories.map(c => c.title), 'i', 'c') && s.object.definition.correctResponsesPattern[0] === EXP.s04(true))
       && ss[0].result.response === EXP.s04(false) && ss[0].result.success === false && ss[1].result.response === EXP.s04(true) && ss[1].result.success === true,
      `sort → xAPI «matching» (source — kartochkalar, target — toifalar): «${ss[1] && ss[1].result.response}»`);
  }
  const resp = st.filter(s => s.verb.id === 'http://adlnet.gov/expapi/verbs/responded');
  ok(resp.length === 1 && resp[0].object.id === actId + '/block/' + REFLECT.id && resp[0].result.response === 'a' && !('success' in resp[0].result) && !resp[0].result.score
     && resp[0].object.definition.interactionType === 'choice' && resp[0].object.definition.choices.length === REFLECT.options.length && !resp[0].object.definition.correctResponsesPattern,
    `Mulohaza: «responded» (result.response="a", success/score yo'q, choices ${resp[0] && resp[0].object.definition.choices.length})`);
  const crs = st.filter(s => /\/(passed|failed)$/.test(s.verb.id) && s.object.id === actId).map(s => s.verb.id.split('/').pop() + ':' + (s.result.score && s.result.score.raw));
  ok(crs.join() === 'failed:0,passed:100', 'Kurs darajasidagi natija har o\'zgarganda (failed → passed, ball bilan): ' + crs.join());
  const passed = st.find(s => s.verb.id.endsWith('/passed')), failed = st.find(s => s.verb.id.endsWith('/failed'));
  ok(passed && passed.result.success === true && passed.result.score.scaled === 1 && passed.result.score.raw === 100 && passed.result.score.min === 0 && passed.result.score.max === 100, 'passed: score.scaled/raw/min/max, success=true');
  ok(failed && failed.result.success === false && failed.result.score.scaled === 0, 'failed: success=false, scaled=0');
  const compl = st.filter(s => s.verb.id.endsWith('/completed'));
  ok(compl.length === 1 && compl[0].object.id === actId && compl[0].result.completion === true, 'completed bir marta, kurs activity uchun');
  const terms = st.filter(s => s.verb.id.endsWith('/terminated'));
  ok(terms.length === 2 && terms.every(t => /^PT\d+H\d+M[\d.]+S$/.test(t.result.duration)), 'terminated har sessiyada, result.duration ISO 8601: ' + terms.map(t => t.result.duration).join(', '));
  ok(LRS.heads.every(h => h.auth === auth && h.ver === '1.0.3' && /application\/json/.test(h.ct)), 'Sarlavhalar: Authorization, X-Experience-API-Version 1.0.3, Content-Type JSON');
  ok(new Set(st.map(s => s.id)).size === st.length && st.every(s => /^[0-9a-f-]{36}$/.test(s.id) && s.timestamp), `Statement id (UUID) noyob; qayta yuborilgan dublikatlar: ${LRS.dup}`);
  ok(T.errs.filter(e => !/status of (404|503)/.test(e)).length === 0 && T.bad.filter(b => /^404/.test(b)).every(b => /activities\/state/.test(b)),
    "Konsol xatolari yo'q (State GET 404 — spec bo'yicha «hujjat yo'q», 503 — sinovda ataylab)" + (T.errs.length ? ': ' + T.errs.slice(0, 3).join(' | ') : ''));
  ok(T.foreign.length === 0, "Tashqi tarmoq so'rovlari yo'q");
  fs.writeFileSync(path.join(OUT, 'xapi_statements.json'), JSON.stringify(st, null, 1));
  await T.ctx.close();
}
// xAPI, completion=view_all: «completed» ko'rish bilan (testsiz natija), keyin test — kurs activity uchun failed/passed ball bilan
async function runXapiViewAll(br, base, lrsBase) {
  section('xAPI · view_all');
  const T = await newCtx(br, {}, 'xapi_va'), page = T.page;
  await patchContent(T.ctx, c => { c.tracking.completion = 'view_all'; c.id = c.id.replace('isft-12-5-', 'isft-12-5-va-'); });
  const actId = 'https://isft.uz/xapi/paket/12/5/va', reg = '9b2c1d0e-1111-4222-8333-444455556666';
  const q = new URLSearchParams({ endpoint: lrsBase + '/xapi/', auth: 'Basic eDp5', actor: JSON.stringify({ mbox: 'mailto:va@isft.uz', name: 'VA' }), registration: reg, activity_id: actId });
  const n0 = LRS.statements.length;
  await page.goto(base + PKG + 'index.html?' + q.toString()); await waitReady(page);
  await visitAllContent(page, page, null); await sleep(600);
  const mine = () => LRS.statements.slice(n0).filter(s => s.context && s.context.registration === reg);
  const course = () => mine().filter(s => s.object.id === actId).map(s => s.verb.id.split('/').pop());
  ok(course().includes('completed') && !course().some(v => /passed|failed/.test(v)), "Barcha qadamlar ko'rildi → kurs uchun completed (testsiz — passed/failed yo'q): " + course().join(','));
  const qi = await stepIndex(page, 'quiz');
  await clickStep(page, qi); await page.click('[data-act="start"]'); await answerQuiz(page, false); await sleep(400);
  await page.click('[data-act="retry"]'); await answerQuiz(page, true); await sleep(600);
  const cs = mine().filter(s => s.object.id === actId && /\/(passed|failed)$/.test(s.verb.id));
  const pz = cs.find(s => s.verb.id.endsWith('/passed'));
  ok(cs.map(s => s.verb.id.split('/').pop()).join() === 'failed,passed', 'Kurs activity: failed, keyin passed (' + cs.map(s => s.verb.id.split('/').pop() + ':' + s.result.score.raw).join(',') + ')');
  ok(pz && pz.result.success === true && pz.result.completion === true && pz.result.score.scaled === 1 && pz.result.score.raw === 100 && pz.result.score.min === 0 && pz.result.score.max === 100 && !pz.context.contextActivities,
    'Kurs passed: score scaled/raw/min/max, success, completion');
  ok(mine().filter(s => s.verb.id.endsWith('/completed')).length === 1, 'completed bir marta');
  ok(!(await page.$('[data-act="retry"],[data-act="start"]')), "O'tgandan keyin qayta urinish yo'q");
  await page.reload(); await waitReady(page); await sleep(500);
  ok(mine().filter(s => s.object.id === actId && /\/(passed|failed)$/.test(s.verb.id)).length === 2, 'Qayta yuklashda kurs natijasi takror yuborilmaydi (holat: xr)');
  ok(T.errs.filter(e => !/status of 404/.test(e)).length === 0, "Konsol xatolari yo'q" + (T.errs.length ? ': ' + T.errs.slice(0, 2).join(' | ') : ''));
  await T.ctx.close();
}

// Xavfli asset manzillari («java\tscript:» — boshqaruv belgilari bilan aylanib o'tish) zararsizlantiriladi
async function runBadUrls(br, base) {
  section('Xavfli manzillar');
  const T = await newCtx(br, {}, 'badurl'), page = T.page;
  await patchContent(T.ctx, c => {
    c.tracking.mode = 'none'; c.id = c.id + '-bad';
    c.blocks.forEach(b => {
      if (b.type === 'file') b.href = 'java\tscript:window.__xss=5';
      if (b.type === 'slides') { b.pdf = ' java\nscript:window.__xss=6'; b.file = '\x01javascript:window.__xss=7'; b.slides[1].image = 'java\tscript:window.__xss=10'; }
      if (b.type === 'refs') b.items.push({ text: 'Yomon', url: 'javascript:window.__xss=11' });
      if (b.type === 'slides') { b.slides[0].caption = '<img src=x onerror="window.__xss=22">izoh'; b.slides[0].audio = 'https://evil.example/a.mp3'; b.slides[2].audio = 'java\tscript:window.__xss=23'; }
      if (b.type === 'video' && b.provider === 'file') { b.poster = 'data:image/svg+xml;base64,PHN2ZyBvbmxvYWQ9YWxlcnQoMSk+'; b.captions.push({ lang: '"><script>', label: 'x', src: 'assets/../x.vtt' }); }
      if (b.type === 'flashcards') { b.cards[0].front = 'Old <script>window.__xss=13</script>'; b.cards[0].back = '<img src=x onerror="window.__xss=14">orqa'; }
      if (b.type === 'assignment') { b.avatar = 'java\tscript:window.__xss=18'; b.text = '<script>window.__xss=15</script>Matn'; b.questions[0] = '<img src=x onerror="window.__xss=19">savol'; }
      if (b.type === 'quiz') { b.questions.find(q => q.type === 'match').pairs[0].left = '<b onmouseover="window.__xss=16">chap</b>'; b.questions.find(q => q.type === 'sort').categories[0].title = '<svg onload="window.__xss=17">toifa'; }
    });
    c.blocks.push({ id: 'bv', type: 'video', title: 'Tashqi fayl', provider: 'file', src: 'https://evil.example/v.mp4' });
    c.brand.logo = 'java\tscript:window.__xss=8';
    c.cover = { image: 'java\tscript:window.__xss=20', author: '<img src=x onerror="window.__xss=21">muallif' };
  });
  await page.goto(base + PKG + 'index.html'); await waitReady(page);
  await clickStep(page, await stepIndex(page, 'file'));
  const f = await page.evaluate(() => ({ links: [...document.querySelectorAll('a[href],img[src]')].map(a => a.getAttribute('href') || a.getAttribute('src')).filter(h => /script/i.test(h)), msg: document.querySelector('.t-file .muted') && document.querySelector('.t-file .muted').textContent }));
  await clickStep(page, await stepIndex(page, 'slides'));
  const sl = await page.evaluate(() => [...document.querySelectorAll('.t-slides .tools a, header img')].map(a => a.getAttribute('href') || a.getAttribute('src')));
  const th = await page.evaluate(() => [...document.querySelectorAll('.t-slides img')].map(i => i.getAttribute('src')).filter(s => /script/i.test(s)).length);
  await clickStep(page, await stepIndex(page, 'refs'));
  const rl = await page.evaluate(() => [...document.querySelectorAll('ol.refs a')].map(a => a.getAttribute('href')).filter(h => !/^https?:/.test(h)).length);
  ok(f.links.length === 0 && f.msg === 'Fayl topilmadi.', `Fayl bloki: «java\\tscript:» href zararsizlantirildi (${f.msg})`);
  ok(sl.length === 0 && th === 0, 'Taqdimot PDF/yuklab olish havolalari, slayd rasmi va logotip: boshqaruv belgili javascript: manzillar olib tashlandi (' + sl.join(',') + ')');
  ok(rl === 0, "Adabiyotlar: javascript: url havolaga aylanmadi");
  {   // kontrakt v3 maydonlari: matn — faqat matn (HTML emas), manzillar — faqat nisbiy assets/
    const bad = () => page.evaluate(() => document.querySelectorAll('#main img[src="x"], #main script, #main svg[onload], #main [onmouseover], #main [onerror]').length);
    let n = 0; const texts = {};
    await clickStep(page, 0);
    texts.cover = await page.evaluate(() => ({ bg: !!document.querySelector('.hero-bg'), img: document.querySelector('.hero').classList.contains('has-img'), au: document.querySelector('.hero-au').textContent })); n += await bad();
    await clickStep(page, await stepIndex(page, 'video', 1));
    texts.video = await page.evaluate(() => { const v = document.querySelector('.video.file video'); return { poster: v.getAttribute('poster'), tracks: [...v.querySelectorAll('track')].map(t => t.getAttribute('src')).join() }; }); n += await bad();
    await clickStep(page, await stepIndex(page, 'video', 2));
    texts.ext = await page.evaluate(() => ({ v: !!document.querySelector('#main video'), msg: (document.querySelector('.t-video .muted') || {}).textContent }));
    await clickStep(page, await stepIndex(page, 'slides'));
    texts.slides = await page.evaluate(() => ({ cap: document.querySelector('.s-cap').textContent, aud: document.querySelectorAll('.s-aud audio').length })); n += await bad();
    await page.focus('.deck'); await page.press('.deck', 'ArrowRight'); await page.press('.deck', 'ArrowRight');
    texts.slides.aud3 = await page.evaluate(() => document.querySelectorAll('.s-aud audio').length);
    await clickStep(page, await stepIndex(page, 'flashcards'));
    texts.fc = await page.evaluate(() => document.querySelector('.fc[data-k="0"]').textContent); n += await bad();
    await clickStep(page, await stepIndex(page, 'assignment'));
    texts.asg = await page.evaluate(() => ({ t: document.querySelector('.asg-q blockquote').textContent, q: document.querySelector('.asg-list li').textContent, img: !!document.querySelector('.asg img'), svg: !!document.querySelector('.asg-av svg') })); n += await bad();
    await clickStep(page, await stepIndex(page, 'quiz')); await page.click('[data-act="start"]');
    texts.q = await page.evaluate(() => ({ l: document.querySelector('.m-row .m-left').textContent, c: document.querySelector('.s-drop[data-c="0"] span').textContent })); n += await bad();
    ok(!texts.cover.bg && !texts.cover.img && texts.cover.au === '<img src=x onerror="window.__xss=21">muallif', 'Muqova: xavfli rasm manzili tashlandi (gradient fon), muallif — oddiy matn');
    ok(texts.video.poster === null && texts.video.tracks === 'assets/video/dars.uz.vtt' && !texts.ext.v && texts.ext.msg === 'Video fayli topilmadi.',
      `Fayl-video: data: poster va tashqi/«..»/javascript: subtitrlar tashlandi (${texts.video.tracks}); tashqi src → «${texts.ext.msg}»`);
    ok(texts.slides.cap === '<img src=x onerror="window.__xss=22">izoh' && texts.slides.aud === 0 && texts.slides.aud3 === 0, 'Slayd izohi — oddiy matn; tashqi/javascript: audio manzillari tashlandi');
    ok(/^Old <script>window\.__xss=13<\/script>/.test(texts.fc) && /<img src=x onerror=/.test(texts.fc) && texts.asg.t === '<script>window.__xss=15</script>Matn' && /^1?<img src=x/.test(texts.asg.q) && !texts.asg.img && texts.asg.svg,
      'Kartochkalar va topshiriq: HTML satrlari matn sifatida; xavfli avatar o\'rniga chizilgan personaj');
    ok(texts.q.l === '<b onmouseover="window.__xss=16">chap</b>' && texts.q.c === '<svg onload="window.__xss=17">toifa' && n === 0, `match/sort: bandlar va toifalar — oddiy matn; kontentdan element yaratilmadi (${n})`);
  }
  const d = await page.evaluate(() => { const a = window.ISFTPaket.debug.assetUrl; return [a('java\tscript:x'), a('/etc/passwd'), a('assets/../x'), a('a\\b'), a('assets/files/ok_1.pdf'), a('assets/slides/s%201.png')]; });
  ok(JSON.stringify(d) === JSON.stringify([null, null, null, null, 'assets/files/ok_1.pdf', 'assets/slides/s%201.png']), 'assetUrl: oq ro\'yxat (' + JSON.stringify(d) + ')');
  const si = await page.evaluate(() => window.ISFTPaket.debug.sanitize('<img src="logo.png"><img src=" assets/img/a.png"><img src="ASSETS/x.png"><figure><img src="assets/img/ok.png"><figcaption>c</figcaption></figure>'));
  ok(!/logo\.png|ASSETS/.test(si) && /assets\/img\/a\.png/.test(si) && /<figcaption>c<\/figcaption>/.test(si), 'Matn rasmi: faqat «assets/» bilan boshlanadigan nisbiy yo\'l (' + si.replace(/loading="lazy" /g, '') + ')');
  ok((await page.evaluate(() => window.__xss)) === undefined && T.errs.length === 0, "XSS yo'q, konsol xatolari yo'q");
  await T.ctx.close();
}
function compact(v) { const o = []; v.forEach(x => { const l = o[o.length - 1]; if (l && l[0] === x) l[1]++; else o.push([x, 1]); }); return o.map(([x, n]) => n > 1 ? x + '×' + n : x).join(' → '); }

// ---------------------------------------------------------------- qadamlar rejimi: navigatsiya, yakunlash, resume, lightbox, galereya
async function runSteps(br, base) {
  section('Qadamlar rejimi');
  const T = await newCtx(br, { viewport: { width: 1366, height: 900 } }, 'steps'), page = T.page;
  await patchContent(T.ctx, c => { c.tracking.completion = 'view_all'; c.tracking.mode = 'xapi'; });
  await page.goto(base + PKG + 'index.html'); await waitReady(page);
  const N = await navN(page);
  const ui = await page.evaluate(() => ({ rail: !!document.querySelector('nav.rail .step'), toc: !!document.querySelector('.toc'), next: document.querySelector('.pager .btn.primary').textContent,
    restart: !!document.querySelector('.top .restart'), mode: window.ISFTPaket.mode, banner: !!document.querySelector('.banner'), keys: window.ISFTPaket.debug.steps().map(s => s.key) }));
  const textKeys = ui.keys.filter(k => k.startsWith(TEXT.id));
  ok(ui.rail && !ui.toc && ui.next === 'Keyingi qadam' && ui.restart, "O'ngda raqamli qadamlar, mundarija yo'q, «Keyingi qadam» va «Boshidan boshlash» tugmalari");
  ok(textKeys.length === 3 && textKeys.join() === [1, 2, 3].map(i => TEXT.id + '.' + i).join(), `Uzun matn h2 bo'yicha qadamlarga bo'lindi (${textKeys.join(', ')}); jami ${N} qadam`);
  ok(ui.mode === 'standalone' && !ui.banner, "xAPI paket LMS'siz (parametrsiz) — jim mustaqil rejim, banner yo'q");
  const cv = await page.evaluate(() => { const h = document.querySelector('.card.t-cover .hero'), q = s => h && h.querySelector(s); return h && { h1: (q('h1.hero-t') || {}).textContent, bg: q('img.hero-bg') && q('img.hero-bg').getAttribute('src'), alt: q('img.hero-bg') && q('img.hero-bg').getAttribute('alt'),
    au: (q('.hero-au') || {}).textContent, logo: q('.hero-brand img') && q('.hero-brand img').getAttribute('src'), go: (q('[data-act="begin"]') || {}).textContent, head: !!document.querySelector('.t-cover .bh'), lab: document.querySelector('.card.t-cover').getAttribute('aria-labelledby') === (q('h1') || {}).id }; });
  ok((await curStep(page)) === 0 && (await currentType(page)) === 'cover' && cv && cv.h1 === 'L1-1-dars: ' + CONTENT.lesson.title && cv.bg === CONTENT.cover.image && cv.alt === '' && cv.au === CONTENT.cover.author && cv.logo === CONTENT.brand.logo && cv.go === 'Boshlash' && !cv.head && cv.lab,
    `1-qadam — muqova: rasm, logotip, «${cv && cv.h1}», muallif «${cv && cv.au}», «Boshlash»`);
  await page.click('[data-act="begin"]'); await sleep(150);
  ok((await curStep(page)) === 1 && (await currentType(page)) === 'section' && (await page.evaluate(() => document.activeElement.id)) === 'main', "«Boshlash» → 2-qadam (bo'lim ajratgichi), fokus asosiy mazmunda");
  await clickStep(page, 0);
  await page.click('.pager .btn.primary'); await sleep(150);
  const a1 = await curStep(page), anim = await page.evaluate(() => /in-r/.test(document.querySelector('.card').className));
  await page.click('.pager .btn.ghost'); await sleep(150);
  ok(a1 === 1 && (await curStep(page)) === 0 && anim, `«Keyingi qadam» / «Oldingi» (${a1} → ${await curStep(page)}), o'tish animatsiyasi`);
  await page.evaluate(() => document.activeElement.blur());
  const seq = [];
  for (const k of ['ArrowRight', 'ArrowRight', 'ArrowLeft', 'PageDown', 'PageUp', 'PageDown']) { await page.keyboard.press(k); await sleep(80); seq.push(await curStep(page)); }
  ok(seq.join() === '1,2,1,2,1,2', `Klaviatura: → → ← PageDown PageUp PageDown (${seq.join(',')})`);
  await page.click('.nav-i[data-i="5"]'); await sleep(120);
  const cur5 = await page.evaluate(() => ({ s: window.ISFTPaket.debug.step(), cur: document.querySelector('.nav-i[aria-current]').dataset.i, lbl: document.querySelector('.nav-i[data-i="5"]').getAttribute('aria-label') }));
  ok(cur5.s === 5 && cur5.cur === '5' && /^6-qadam: /.test(cur5.lbl), `Qadamlar ro'yxatidan bosish → 6-qadam (aria-current, «${cur5.lbl}»)`);
  await page.click('.top .restart'); await sleep(120);
  ok((await curStep(page)) === 0, '«Boshidan boshlash» → 1-qadam');
  // galereyada ← → qadamni emas, slaydni almashtiradi
  await clickStep(page, await stepIndex(page, 'slides'));
  const sIdx = await curStep(page);
  await page.focus('.deck'); await page.keyboard.press('ArrowRight'); await sleep(80);
  ok((await curStep(page)) === sIdx && (await page.textContent('.counter')) === '2 / ' + SLIDES.slides.length, 'Galereya fokusida ← → slaydni almashtiradi, qadamni emas');
  // to'liq ekran (iframe/headless'da Fullscreen API rad etilsa — oyna bo'ylab qoplama)
  await page.click('.fs-btn'); await sleep(300);
  const fs1 = await page.evaluate(() => ({ api: document.fullscreenElement === document.querySelector('.gal'), pseudo: document.querySelector('.gal').classList.contains('pseudo-fs'), pr: document.querySelector('.fs-btn').getAttribute('aria-pressed') }));
  ok((fs1.api || fs1.pseudo) && fs1.pr === 'true', `«To'liq ekran»: ${fs1.api ? 'Fullscreen API' : 'zaxira qoplama'} (aria-pressed=${fs1.pr})`);
  await SHOT(page, 'steps_gallery_fullscreen');
  if (fs1.api) await page.evaluate(() => document.exitFullscreen()); else await page.keyboard.press('Escape');
  await sleep(250);
  ok(await page.evaluate(() => !document.fullscreenElement && !document.querySelector('.gal').classList.contains('pseudo-fs')), "To'liq ekrandan chiqish (Esc)");
  await checkLightbox(page);
  // hamma qadamlar → yakunlandi (view_all)
  await clickStep(page, 0);
  for (let i = 1; i < N; i++) { await page.click('.pager .btn.primary'); await sleep(60); }
  const fin = await page.evaluate(() => ({ st: window.ISFTPaket.debug.status(), chip: document.querySelector('.chip').textContent, next: document.querySelector('.pager .btn.primary').disabled, last: window.ISFTPaket.debug.step() }));
  ok(fin.st.complete && fin.chip.startsWith('Yakunlandi') && fin.next && fin.last === N - 1, `Hamma qadamlar ko'rildi → yakunlandi (view_all; ${fin.st.seen}/${fin.st.total}, «${fin.chip}»), oxirgi qadamda «Keyingi» o'chiq`);
  // resume
  await clickStep(page, 6); await sleep(600);
  await page.reload(); await waitReady(page);
  ok((await curStep(page)) === 6 && (await doneCount(page)) >= N - 1, `Qayta yuklash → o'sha qadam (7-qadam) va ✓ belgilar (localStorage)`);
  ok(T.errs.length === 0, "Konsol xatolari yo'q" + (T.errs.length ? ': ' + T.errs.slice(0, 3).join(' | ') : ''));
  await T.ctx.close();
  // reduced-motion: animatsiyasiz
  const RM = await newCtx(br, { reducedMotion: 'reduce' }, 'rm');
  await RM.page.goto(base + PKG + 'index.html'); await waitReady(RM.page);
  await RM.page.click('.pager .btn.primary'); await sleep(100);
  ok(!(await RM.page.evaluate(() => /in-[rl]/.test(document.querySelector('.card').className))), "prefers-reduced-motion: o'tish animatsiyasi yo'q");
  await RM.ctx.close();
}

// ---------------------------------------------------------------- kontrakt v3: muqova, fayl-video, slayd izohi/audio, kartochkalar, topshiriq, match/sort (sudrash, qoralama)
async function runV3(br, base) {
  section('Kontrakt v3 bloklari');
  const T = await newCtx(br, { viewport: { width: 1366, height: 900 } }, 'v3'), page = T.page;
  await patchContent(T.ctx, c => { c.tracking.mode = 'xapi'; c.id += '-v3'; });
  await page.goto(base + '/lms.html');
  const url = base + PKG + 'index.html', KEY = 'isft-paket:' + CONTENT_ID + '-v3';
  const open = async () => { await page.evaluate(u => window.launch('none', u), url); await sleep(250); const f = page.frame({ name: 'sco' }); await waitReady(f); return f; };
  const stored = fr => fr.evaluate(k => JSON.parse(localStorage.getItem(k) || '{}'), KEY);
  let fr = await open();
  await SHOT(page, 'v3_cover');

  // ---- fayl-video
  await clickStep(fr, await stepIndex(fr, 'video', 1)); await sleep(200);
  const v0 = await fr.evaluate(() => { const v = document.querySelector('.video.file video'); return v && { controls: v.controls, inline: v.hasAttribute('playsinline'), pre: v.getAttribute('preload'), src: v.getAttribute('src'), poster: v.getAttribute('poster'), label: v.getAttribute('aria-label'),
    tracks: [...v.querySelectorAll('track')].map(t => [t.kind, t.srclang, t.label, t.getAttribute('src')].join('|')), rates: [...document.querySelectorAll('.v-speed button')].map(b => b.dataset.rate + ':' + b.getAttribute('aria-pressed')).join(),
    grp: document.querySelector('.v-speed').getAttribute('role') + '/' + document.querySelector('.v-speed').getAttribute('aria-label'), pct: document.querySelector('.v-pct').textContent, yt: !!document.querySelector('#main iframe') }; });
  ok(v0 && v0.controls && v0.inline && v0.pre === 'metadata' && v0.src === VFILE.src && v0.poster === VFILE.poster && v0.label === VFILE.title && !v0.yt,
    `Fayl-video: <video controls playsinline preload="metadata"> src=${v0 && v0.src}, poster, aria-label`);
  ok(v0 && v0.tracks.length === 1 && v0.tracks[0] === "subtitles|uz|O'zbekcha|assets/video/dars.uz.vtt", `Subtitr: bitta <track kind="subtitles"> (tashqi va javascript: manzillar tashlandi): ${v0 && v0.tracks.join(' ; ')}`);
  ok(v0 && v0.rates === '0.75:false,1:true,1.25:false,1.5:false,2:false' && v0.grp === 'group/Ijro tezligi' && v0.pct === "Ko'rildi: 0%", `Tezlik menyusi (${v0 && v0.rates}), «${v0 && v0.pct}»`);
  await fr.press('.v-speed [data-rate="1.5"]', 'Enter');
  const r15 = await fr.evaluate(() => ({ r: document.querySelector('video').playbackRate, p: document.querySelector('.v-speed [data-rate="1.5"]').getAttribute('aria-pressed'), one: document.querySelector('.v-speed [data-rate="1"]').getAttribute('aria-pressed') }));
  ok(r15.r === 1.5 && r15.p === 'true' && r15.one === 'false', `Tezlik 1.5× (klaviatura): playbackRate=${r15.r}, aria-pressed`);
  // HTMLMediaElement xususiyatlari almashtiriladi (o'rinbosar .mp4 dekodlanmaydi) — holat mantig'i hodisalar orqali tekshiriladi
  const stub = f => f.evaluate(() => {
    const v = document.querySelector('video'); let t = 0; window.__set = [];
    const def = (k, get, set) => Object.defineProperty(v, k, { configurable: true, get, set });
    def('duration', () => 100); def('paused', () => false); def('seeking', () => false); def('ended', () => false);
    def('currentTime', () => t, x => { t = x; window.__set.push(x); });
    window.__play = (a, b) => { for (let x = a; x <= b; x++) { t = x; v.dispatchEvent(new Event('timeupdate')); } };
    window.__ev = n => v.dispatchEvent(new Event(n));
  });
  const vst = f => f.evaluate(id => ({ m: (window.ISFTPaket.debug.state().m || {})[id], w: window.ISFTPaket.debug.watched(id), pct: (document.querySelector('.v-pct') || {}).textContent }), VFILE.id);
  await stub(fr);
  await fr.evaluate(() => window.__play(0, 12)); await sleep(650);
  const p1 = await vst(fr), l1 = ((await stored(fr)).m || {})[VFILE.id];
  ok(p1.m.t === 12 && p1.w === 15 && p1.pct === "Ko'rildi: 15%" && l1 && l1.t === 12, `Ijro 0→12 s: joy ${p1.m.t} s, ko'rildi ${p1.w}%; ~10 s da holat saqlandi (localStorage t=${l1 && l1.t})`);
  await fr.evaluate(() => { window.__ev('seeking'); window.__play(50, 51); window.__ev('pause'); }); await sleep(650);
  const p2 = await vst(fr), l2 = ((await stored(fr)).m || {})[VFILE.id];
  ok(p2.w === 20 && p2.m.t === 51 && l2 && l2.t === 51, `Oldinga sakrash (seek) ko'rilgan ulushga qo'shilmaydi (${p2.w}%), pauzada joy saqlandi (t=${l2 && l2.t})`);
  ok(!(await page.evaluate(() => window.LMS.msgs.some(m => m.video))), "90% dan kam — postMessage'da video maydoni yo'q");
  fr = await open(); await sleep(150);
  await stub(fr); await fr.evaluate(() => window.__ev('loadedmetadata'));
  const p3 = await fr.evaluate(() => ({ set: window.__set.join(), type: document.querySelector('.nav-i[aria-current]').dataset.type, pct: document.querySelector('.v-pct').textContent }));
  ok(p3.type === 'video' && p3.set === '51' && p3.pct === "Ko'rildi: 20%", `Qayta ochilganda video o'sha joydan davom etadi (currentTime=${p3.set}), «${p3.pct}»`);
  await fr.evaluate(() => { window.__ev('seeking'); window.__play(0, 100); window.__ev('ended'); }); await sleep(200);
  const p4 = await vst(fr), vm = (await page.evaluate(() => window.LMS.msgs)).filter(m => m.video);
  ok(p4.w === 100 && p4.m.t === 0 && (await fr.evaluate(() => document.querySelector('.v-pct').classList.contains('good'))), `To'liq ko'rildi: ${p4.w}%, tugaganda joy 0 ga qaytadi`);
  ok(vm.length === 1 && vm[0].event === 'progress' && vm[0].video.block === VFILE.id && vm[0].video.watched >= 90 && vm[0].source === 'isft-paket', `postMessage progress: video:{block:"${vm[0] && vm[0].video.block}", watched:${vm[0] && vm[0].video.watched}} (≥ 90% da bir marta)`);
  await clickStep(fr, 1); await clickStep(fr, await stepIndex(fr, 'video', 1));
  ok((await page.evaluate(() => window.LMS.msgs.filter(m => m.video).length)) === 1 && (await fr.evaluate(() => document.querySelector('.nav-i[data-type="video"].done') !== null)), "Blok ochilganda «ko'rildi» ✓; video xabari takrorlanmaydi");
  await SHOT(page, 'v3_video_file');
  // video fokusida ← → qadamni almashtirmaydi
  const vs = await curStep(fr); await fr.focus('video'); await fr.press('video', 'ArrowRight'); await sleep(60);
  ok((await curStep(fr)) === vs, 'Video fokusida ← → qadamni almashtirmaydi (pleyerning o\'z tugmalari)');
  ok((await fr.evaluate(() => document.querySelector('.video.file video').hasAttribute('crossorigin'))) === false,
    'Oddiy (same-origin, http) xizmatda <video> crossorigin atributisiz — CORS so\'rovi yuborilmaydi');

  // ---- slayd izohi va audio
  await clickStep(fr, await stepIndex(fr, 'slides'));
  const sl0 = await fr.evaluate(() => ({ cap: document.querySelector('.s-cap').hidden, aud: document.querySelector('.s-aud').hidden }));
  await fr.click('.nav-a.r'); await sleep(80);
  const sl1 = await fr.evaluate(() => { const a = document.querySelector('.s-aud audio'); window.__paused = 0; if (a) a.pause = () => { window.__paused++; };
    return { cap: document.querySelector('.s-cap').textContent, vis: !document.querySelector('.s-cap').hidden, a: a && { c: a.controls, src: a.getAttribute('src'), pre: a.getAttribute('preload'), l: a.getAttribute('aria-label') } }; });
  ok(sl0.cap && sl0.aud && sl1.vis && sl1.cap === SLIDES.slides[1].caption && sl1.a && sl1.a.c && sl1.a.src === SLIDES.slides[1].audio && sl1.a.pre === 'none' && /audio/.test(sl1.a.l),
    `Slayd izohi rasm ostida («${sl1.cap.slice(0, 28)}…») va <audio controls> (${sl1.a && sl1.a.src}); izohsiz slaydda yashirin`);
  await SHOT(page, 'v3_slide_caption_audio');
  await fr.click('.nav-a.r'); await sleep(80);
  const sl2 = await fr.evaluate(() => ({ p: window.__paused, a: document.querySelectorAll('.s-aud audio').length, cap: document.querySelector('.s-cap').hidden }));
  ok(sl2.p === 1 && sl2.a === 0 && sl2.cap, 'Slayddan chiqilganda audio to\'xtatiladi va olib tashlanadi');
  await fr.click('.nav-a.l'); await sleep(80);
  await fr.evaluate(() => { window.__paused = 0; document.querySelector('.s-aud audio').pause = () => { window.__paused++; }; });
  await fr.click('.pager .btn.primary'); await sleep(120);
  ok((await fr.evaluate(() => window.__paused)) === 1, 'Qadamdan chiqilganda ham audio to\'xtatiladi');

  // ---- kartochkalar
  await clickStep(fr, await stepIndex(fr, 'flashcards'));
  const NC = FLASH.cards.filter(c => c.front && c.back).length;
  const f0 = await fr.evaluate(() => ({ n: document.querySelectorAll('.fc-grid .fc').length, tag: document.querySelector('.fc').tagName, pr: [...document.querySelectorAll('.fc')].map(b => b.getAttribute('aria-pressed')).join(),
    front: document.querySelector('.fc[data-k="0"] .fc-f .fc-x').textContent, bh: document.querySelector('.fc[data-k="0"] .fc-b').getAttribute('aria-hidden'), done: document.querySelector('.nav-i[data-type="flashcards"]').classList.contains('done') }));
  ok(f0.n === NC && f0.tag === 'BUTTON' && f0.pr === Array(NC).fill('false').join() && f0.front === FLASH.cards[0].front && f0.bh === 'true' && f0.done, `Kartochkalar: ${f0.n} ta tugma (bo'sh kartochka tashlandi), aria-pressed=false, ochilganda «ko'rildi»`);
  await fr.click('.fc[data-k="0"]'); await sleep(650);
  const f1 = await fr.evaluate(() => { const b = document.querySelector('.fc[data-k="0"]'); return { pr: b.getAttribute('aria-pressed'), bh: b.querySelector('.fc-b').getAttribute('aria-hidden'), fh: b.querySelector('.fc-f').getAttribute('aria-hidden'), back: b.querySelector('.fc-b .fc-x').textContent, tr: getComputedStyle(b.querySelector('.fc-in')).transform }; });
  ok(f1.pr === 'true' && f1.bh === 'false' && f1.fh === 'true' && f1.back === FLASH.cards[0].back && f1.tr !== 'none', `Bosilganda aylanadi: aria-pressed=true, orqa tomon ochiq («${f1.back.slice(0, 30)}…»)`);
  await fr.press('.fc[data-k="0"]', 'Enter'); await fr.press('.fc[data-k="1"]', ' '); await sleep(100);
  {   // kartochka fokusida ← → / PageDown qadamni almashtirmaydi
    const fs0 = await curStep(fr); await fr.focus('.fc[data-k="1"]');
    for (const k of ['ArrowRight', 'ArrowLeft', 'PageDown']) { await fr.press('.fc[data-k="1"]', k); await sleep(50); }
    ok((await curStep(fr)) === fs0 && (await currentType(fr)) === 'flashcards', 'Kartochka fokusida ← → / PageDown qadamni almashtirmaydi');
  }
  const f2 = await fr.evaluate(() => [...document.querySelectorAll('.fc')].map(b => b.getAttribute('aria-pressed')).join());
  ok(f2 === ['false', 'true'].concat(Array(NC - 2).fill('false')).join() && (await curStep(fr)) === (await stepIndex(fr, 'flashcards')), `Klaviatura: Enter qaytaradi, Space aylantiradi (${f2})`);
  await sleep(600); await SHOT(page, 'v3_flashcards');

  // ---- topshiriq
  await clickStep(fr, await stepIndex(fr, 'assignment'));
  const as = await fr.evaluate(() => ({ q: document.querySelector('.asg-q blockquote p').textContent, au: document.querySelector('.asg-q figcaption').textContent, svg: !!document.querySelector('.asg-q .asg-av svg'), img: !!document.querySelector('.asg-q img'),
    li: [...document.querySelectorAll('ol.asg-list li')].map(li => li.lastChild.textContent), note: document.querySelector('.asg-note').textContent, role: document.querySelector('.asg-note').getAttribute('role'), done: document.querySelector('.nav-i[data-type="assignment"]').classList.contains('done') }));
  ok(as.q === ASSIGN.text && as.au === ASSIGN.author && as.svg && !as.img, `Topshiriq: iqtibos «${as.q.slice(0, 40)}…» — ${as.au}, chizilgan personaj (avatar berilmagan)`);
  ok(JSON.stringify(as.li) === JSON.stringify(ASSIGN.questions) && as.note === "Javobni LMS'dagi «Vazifa yuklash» orqali yuboring" && as.role === 'note' && as.done, `Topshiriq: ${as.li.length} ta raqamli savol, eslatma «${as.note}»; baholanmaydi`);
  await SHOT(page, 'v3_assignment');
  const stA = await fr.evaluate(() => window.ISFTPaket.debug.status());
  ok(stA.score === null && stA.success === 'unknown', 'Kartochkalar va topshiriq natijaga ta\'sir qilmaydi (ball yo\'q)');

  // ---- match / sort: sudrash (sichqoncha), bosish, almashtirish, bo'shatish
  const qi = await stepIndex(fr, 'quiz');
  await clickStep(fr, qi); await fr.click('[data-act="start"]'); await fr.waitForSelector('form.qform');
  const M = `fieldset[data-qid="${MATCH.id}"]`, S = `fieldset[data-qid="${SORT.id}"]`;
  const mState = () => fr.evaluate(s => ({ slots: [...document.querySelectorAll(s + ' .m-slot')].map(e => e.dataset.r || '-').join(), bank: [...document.querySelectorAll(s + ' .m-tile')].filter(e => !e.hidden).map(e => e.dataset.r).sort().join(),
    sel: [...document.querySelectorAll(s + ' [aria-pressed="true"]')].map(e => e.className.split(' ')[0] + (e.dataset.l || e.dataset.r)).join(), ghost: document.querySelectorAll('.drag-ghost').length }), M);
  const sState = () => fr.evaluate(s => ({ deck: [...document.querySelectorAll(s + ' .s-deck .s-card')].map(e => e.dataset.k).sort().join(''), cats: [...document.querySelectorAll(s + ' .s-cat')].map(c => [...c.querySelectorAll('.s-card')].map(e => e.dataset.k).sort().join('')).join('|'),
    n: [...document.querySelectorAll(s + ' .s-n')].map(e => e.textContent).join() }), S);
  const a11y = await fr.evaluate(([m, s]) => ({ slot: document.querySelector(m + ' .m-slot').tagName + ':' + document.querySelector(m + ' .m-slot[data-l="0"]').getAttribute('aria-label'), tile: document.querySelector(m + ' .m-tile').tagName, bank: document.querySelector(m + ' .m-bank').getAttribute('role'),
    card: document.querySelector(s + ' .s-card').tagName, drop: document.querySelector(s + ' .s-drop').tagName + ':' + document.querySelector(s + ' .s-drop[data-c="0"]').getAttribute('aria-label'), hints: document.querySelectorAll(m + ' .hint, ' + s + ' .hint').length,
    order: [...document.querySelectorAll(m + ' .m-tile')].map(e => e.dataset.r).join(), sub: getComputedStyle(document.querySelector('[data-act="submit"]')).backgroundColor }), [M, S]);
  ok(a11y.slot === `BUTTON:«${MATCH.pairs[0].left}» uchun javob: bo'sh` && a11y.tile === 'BUTTON' && a11y.bank === 'group' && a11y.card === 'BUTTON' && a11y.drop === `BUTTON:«${SORT.categories[0].title}» toifasiga qo'yish` && a11y.hints === 2,
    `match/sort: kataklar, javoblar, kartochkalar va toifalar — tugmalar (aria-label «${a11y.slot.slice(7)}»), yo'riqnoma matni`);
  ok(a11y.order !== MATCH.pairs.map((_, i) => i).join() && a11y.sub === 'rgb(46, 140, 86)', `O'ng bandlar aralashtirilgan (${a11y.order}); «Javoblarni yuborish» — yashil (${a11y.sub})`);
  await fr.dragAndDrop(`${M} .m-tile[data-r="2"]`, `${M} .m-slot[data-l="0"]`); await sleep(80);
  const d1 = await mState();
  await fr.dragAndDrop(`${M} .m-slot[data-l="0"]`, `${M} .m-slot[data-l="2"]`); await sleep(80);
  const d2 = await mState();
  await fr.dragAndDrop(`${M} .m-tile[data-r="0"]`, `${M} .m-slot[data-l="2"]`); await sleep(80);
  const d3 = await mState();
  ok(d1.slots === '2,-,-,-' && d1.bank === '0,1,3' && d2.slots === '-,-,2,-' && d3.slots === '-,-,0,-' && d3.bank === '1,2,3' && d3.ghost === 0, `match sudrash: javob → katak (${d1.slots}), katak → katak (${d2.slots}), band katakka yangi javob — eskisi qaytadi (${d3.slots}; bankda ${d3.bank})`);
  await fr.dragAndDrop(`${M} .m-slot[data-l="2"]`, `${M} .m-bank`); await sleep(80);
  const d4 = await mState();
  ok(d4.slots === '-,-,-,-' && d4.bank === '0,1,2,3' && d4.sel === '', `match sudrash: katakdan bankka qaytarish (${d4.slots}); sudrashdan keyin tasodifiy tanlov yo'q`);
  // bosish: javob → katak, katak ↔ katak almashtirish, qayta bosish — bo'shatish
  await fr.click(`${M} .m-tile[data-r="1"]`); const t1 = await mState(); await fr.click(`${M} .m-slot[data-l="0"]`);
  await fr.click(`${M} .m-slot[data-l="1"]`); await fr.click(`${M} .m-tile[data-r="0"]`);
  const t2 = await mState(), foc = await fr.evaluate(() => document.activeElement.className + ':' + document.activeElement.dataset.l);
  await fr.click(`${M} .m-slot[data-l="0"]`); await fr.click(`${M} .m-slot[data-l="1"]`);
  const t3 = await mState();
  await fr.click(`${M} .m-slot[data-l="1"]`); await fr.click(`${M} .m-slot[data-l="1"]`);
  const t4 = await mState();
  ok(t1.sel === 'm-tile1' && t2.slots === '1,0,-,-' && /^m-slot:2$/.test(foc) && t3.slots === '0,1,-,-' && t4.slots === '0,-,-,-' && t4.bank === '1,2,3',
    `match bosish: javob→katak va katak→javob (${t2.slots}; fokus keyingi bo'sh katakda), almashtirish (${t3.slots}), qayta bosish — bo'shatish (${t4.slots})`);
  const lbl = await fr.evaluate(m => document.querySelector(m + ' .m-slot[data-l="0"]').getAttribute('aria-label') + ' / ' + document.querySelector('[aria-live].sr').textContent, M);
  ok(lbl.startsWith(`«${MATCH.pairs[0].left}» uchun javob: «${MATCH.pairs[0].right}»`), `match: katak aria-label yangilanadi, o'zgarish aria-live orqali e'lon qilinadi (${lbl.slice(0, 70)}…)`);
  {   // global ← → / PageUp / PageDown: test ichida (moslashtirish, saralash, variantlar, «yuborish») qadam almashmaydi
    const q0 = await curStep(fr), res = [];
    const mcq = `fieldset[data-qid="${QUIZ.questions.find(q => q.type === 'mcq').id}"] input`;
    for (const [sel, key] of [[`${M} .m-tile[data-r="1"]`, 'ArrowRight'], [`${M} .m-tile[data-r="1"]`, 'PageDown'], [`${M} .m-slot[data-l="1"]`, 'ArrowLeft'], [`${S} .s-card[data-k="1"]`, 'ArrowRight'],
      [`${S} .s-drop[data-c="0"]`, 'PageUp'], [mcq, 'PageDown'], ['[data-act="submit"]', 'ArrowRight']]) {
      await fr.focus(sel); await fr.press(sel, key); await sleep(50);
      res.push((await curStep(fr)) === q0 && (await fr.evaluate(() => !!document.querySelector('form.qform'))));
    }
    ok(res.every(Boolean) && (await currentType(fr)) === 'quiz', `Test ichida fokus (match javobi/katagi, sort kartochkasi/toifasi, variant, «yuborish») — ← → / PageUp / PageDown qadamni almashtirmaydi (${res.map(x => x ? 1 : 0).join('')})`);
    const m1 = await mState();
    ok(m1.slots === '0,-,-,-', `…va vidjet holati o'zgarmaydi (${m1.slots})`);
  }
  await fr.dragAndDrop(`${S} .s-card[data-k="0"]`, `${S} .s-cat[data-c="1"] .s-list`); await sleep(80);
  const e1 = await sState();
  await fr.dragAndDrop(`${S} .s-card[data-k="0"]`, `${S} .s-cat[data-c="0"] .s-drop`); await sleep(80);
  const e2 = await sState();
  await fr.dragAndDrop(`${S} .s-card[data-k="0"]`, `${S} .s-deck`); await sleep(80);
  const e3 = await sState();
  ok(e1.cats === '|0' && e1.deck === '12345' && e1.n === '0,1' && e2.cats === '0|' && e3.cats === '|' && e3.deck === '012345', `sort sudrash: kartochka → toifa (${e1.cats}), toifadan toifaga (${e2.cats}), qaytarish (${e3.deck}); hisoblagichlar ${e1.n}`);
  await fr.click(`${S} .s-card[data-k="2"]`); await fr.click(`${S} .s-cat[data-c="1"]`, { position: { x: 20, y: 110 } });
  await fr.press(`${S} .s-card[data-k="2"]`, 'Delete');
  const e4 = await sState();
  await fr.press(`${S} .s-card[data-k="5"]`, 'Enter'); await fr.press(`${S} .s-drop[data-c="1"]`, 'Enter');
  const e5 = await sState(), foc2 = await fr.evaluate(() => document.activeElement.className);
  ok(e4.deck === '012345' && e5.cats === '|5' && foc2 === 's-card', `sort: toifa maydonini bosish, Delete — qaytarish, klaviatura (Enter → Enter) — «${e5.cats}», fokus keyingi kartochkada`);
  await SHOT(page, 'v3_quiz_match_sort', true);

  // ---- tugallanmagan javoblar: qayta ochilganda tiklanadi
  await fr.fill(`fieldset[data-qid="${FILLQ.id}"] input`, 'qoralama javob');
  await fr.check(`fieldset[data-qid="${QUIZ.questions[0].id}"] input[value="1"]`);
  const ordA = await fr.evaluate(() => [...document.querySelectorAll('fieldset.q')].map(f => f.dataset.qid).join() + '/' + [...document.querySelectorAll('.m-tile')].map(e => e.dataset.r).join());
  await sleep(650);
  fr = await open(); await sleep(150);
  const rs = await fr.evaluate(([m, s, f, q0]) => ({ type: document.querySelector('.nav-i[aria-current]').dataset.type, form: !!document.querySelector('form.qform'),
    ord: [...document.querySelectorAll('fieldset.q')].map(f => f.dataset.qid).join() + '/' + [...document.querySelectorAll('.m-tile')].map(e => e.dataset.r).join(),
    slots: [...document.querySelectorAll(m + ' .m-slot')].map(e => e.dataset.r || '-').join(), cats: [...document.querySelectorAll(s + ' .s-cat')].map(c => [...c.querySelectorAll('.s-card')].map(e => e.dataset.k).join('')).join('|'),
    fill: document.querySelector('fieldset[data-qid="' + f + '"] input').value, mcq: [...document.querySelectorAll('fieldset[data-qid="' + q0 + '"] input')].filter(i => i.checked).map(i => i.value).join() }), [M, S, FILLQ.id, QUIZ.questions[0].id]);
  ok(rs.type === 'quiz' && rs.form && rs.ord === ordA, 'Tugallanmagan urinish: qayta ochilganda o\'sha savol va javob tartibi');
  ok(rs.slots === '0,-,-,-' && rs.cats === '|5' && rs.fill === 'qoralama javob' && rs.mcq === '1', `Tugallanmagan javoblar tiklandi (match ${rs.slots}; sort ${rs.cats}; matn «${rs.fill}»; tanlov ${rs.mcq})`);
  // chala javob → tasdiq so'raladi → o'tmadi; qayta urinish (to'g'ri) → o'tdi
  await fr.click('[data-act="submit"]'); await sleep(100);
  const warn = await fr.evaluate(() => document.querySelector('.q-msg').textContent + ' | ' + document.querySelector('[data-act="submit"]').textContent);
  await fr.click('[data-act="submit"]'); await sleep(250);
  const r0 = await fr.evaluate(([m, s]) => ({ st: window.ISFTPaket.debug.status(), bad: document.querySelector('.score.bad') !== null, m: [...document.querySelectorAll('.fb[data-qid="' + m + '"] .fb-a:not(.fb-c) .fb-pairs li')].map(li => li.className).join(),
    sEmpty: [...document.querySelectorAll('.fb[data-qid="' + s + '"] .fb-a:not(.fb-c) .fb-pairs li strong')].filter(x => x.textContent === '—').length, d: window.ISFTPaket.debug.state().q }), [M.match(/"(.+)"/)[1], S.match(/"(.+)"/)[1]]);
  ok(/javobsiz yoki chala/.test(warn) && /Baribir yuborish/.test(warn) && r0.bad && r0.st.success === 'failed', `Chala javoblar: «${warn.split(' | ')[0]}» → tasdiqdan keyin «o'tmadi»`);
  ok(r0.m === 'ok,no,no,no' && r0.sEmpty === SORT_ITEMS.length - 1 && !r0.d[QUIZ.id].d && !r0.d[QUIZ.id].ip, `Izoh: match juftliklari alohida belgilangan (${r0.m}), joylanmagan kartochkalar «—»; qoralama tozalandi`);
  await SHOT(page, 'v3_quiz_failed', true);
  await fr.click('[data-act="retry"]'); await answerQuiz(fr, true); await sleep(200);
  const r1 = await fr.evaluate(() => ({ st: window.ISFTPaket.debug.status(), ok: document.querySelectorAll('.fb.ok').length, pairs: document.querySelectorAll('.fb-pairs li.no').length }));
  const ev = (await page.evaluate(() => window.LMS.msgs)).filter(m => /passed|failed/.test(m.event)).map(m => m.event + ':' + m.score.raw).join();
  ok(r1.st.success === 'passed' && r1.st.score === 100 && r1.ok === QUIZ.questions.length && r1.pairs === 0 && /^failed:\d+,passed:100$/.test(ev), `Qayta urinish (to'g'ri) → o'tdi 100% (postMessage: ${ev})`);
  await SHOT(page, 'v3_quiz_passed', true);
  ok(T.errs.length === 0, "Konsol xatolari yo'q" + (T.errs.length ? ': ' + T.errs.slice(0, 3).join(' | ') : ''));
  ok(T.foreign.length === 0, "Tashqi tarmoq so'rovlari yo'q" + (T.foreign.length ? ': ' + T.foreign.slice(0, 3).join(' ') : ''));
  await T.ctx.close();

  // muqova maydoni yo'q → avvalgi xulq (birinchi qadam — bo'lim); rasmsiz muqova — brend gradienti
  const N0 = await newCtx(br, {}, 'nocover');
  await patchContent(N0.ctx, c => { delete c.cover; c.id += '-nc'; c.tracking.mode = 'none'; });
  await N0.page.goto(base + PKG + 'index.html'); await waitReady(N0.page);
  const nc = await N0.page.evaluate(() => ({ t: window.ISFTPaket.debug.steps()[0].type, cov: document.querySelectorAll('.nav-i[data-type="cover"], .hero').length, n: new Set(window.ISFTPaket.debug.steps().map(s => s.block)).size }));
  ok(nc.t === 'section' && nc.cov === 0 && nc.n === NBLOCKS, `cover maydoni yo'q → muqovasiz, birinchi qadam — bo'lim (${nc.n} blok)`);
  await N0.ctx.close();
  const N1 = await newCtx(br, { reducedMotion: 'reduce' }, 'coverplain');
  await patchContent(N1.ctx, c => { c.cover = { image: null }; c.id += '-cp'; c.tracking.mode = 'none'; c.lesson = { code: 'A1', kind: 'amaliy', no: 1, title: 'Excel bilan ishlash' }; });
  await N1.page.goto(base + PKG + 'index.html'); await waitReady(N1.page);
  const cp = await N1.page.evaluate(() => ({ bg: !!document.querySelector('.hero-bg'), h1: document.querySelector('.hero-t').textContent, au: document.querySelector('.hero-au').textContent, grad: /gradient/.test(getComputedStyle(document.querySelector('.hero')).backgroundImage) }));
  ok(!cp.bg && cp.grad && cp.h1 === "A1 — Amaliy mashg'ulot: Excel bilan ishlash" && cp.au === CONTENT.course.teacher, `Rasmsiz muqova: brend gradienti, «${cp.h1}», muallif — kurs o'qituvchisi (${cp.au})`);
  await SHOT(N1.page, 'v3_cover_plain');
  // reduced-motion: kartochka aylanmaydi — tomonlar almashtiriladi
  await clickStep(N1.page, await stepIndex(N1.page, 'flashcards')); await N1.page.click('.fc[data-k="0"]'); await sleep(100);
  const rm = await N1.page.evaluate(() => { const b = document.querySelector('.fc[data-k="0"]'), cs = e => getComputedStyle(b.querySelector(e)); return { tr: cs('.fc-in').transform, f: cs('.fc-f').visibility, bk: cs('.fc-b').visibility, btr: cs('.fc-b').transform }; });
  ok(rm.tr === 'none' && rm.f === 'hidden' && rm.bk === 'visible' && rm.btr === 'none', `prefers-reduced-motion: kartochka aylanmasdan almashadi (transform: ${rm.tr})`);
  ok(N1.errs.length === 0, "Konsol xatolari yo'q");
  await N1.ctx.close();
  for (const [au, want, tag] of [['', null, "bo'sh satr — muallifsiz (course.teacher'ga qaytmaydi)"], [null, CONTENT.course.teacher, 'null — kurs o\'qituvchisi'], ['  Aliyev V.  ', 'Aliyev V.', 'berilgan muallif']]) {
    const N2 = await newCtx(br, {}, 'coverauthor');
    await patchContent(N2.ctx, c => { c.cover = { image: null, author: au }; c.id += '-ca'; c.tracking.mode = 'none'; });
    await N2.page.goto(base + PKG + 'index.html'); await waitReady(N2.page);
    const ca = await N2.page.evaluate(() => { window.dispatchEvent(new Event('beforeprint'));
      return { au: (document.querySelector('.hero-au') || { textContent: null }).textContent, pr: (document.querySelector('.print-all .p-cover') || {}).textContent }; });
    ok(ca.au === want && typeof ca.pr === 'string' && ca.pr.includes(CONTENT.course.teacher) === (want === CONTENT.course.teacher) && (!want || ca.pr.includes(want)),
      `Muqova muallifi: ${tag} (muqova: ${JSON.stringify(ca.au)}; chop etish: «${ca.pr}»)`);
    await N2.ctx.close();
  }
}

// ---------------------------------------------------------------- NEXTID.LMS: iframe, API ham, launch parametrlari ham yo'q
async function runNextid(br, base) {
  section('NEXTID (API\'siz iframe)');
  const T = await newCtx(br, { viewport: { width: 1366, height: 900 } }, 'nextid'), page = T.page;
  await patchContent(T.ctx, c => { c.tracking.mode = 'xapi'; });       // NEXTID standarti — xAPI
  await page.goto(base + '/lms.html');
  const url = base + PKG + 'index.html';
  await page.evaluate(u => window.launch('none', u), url); await sleep(200);
  let fr = page.frame({ name: 'sco' }); await waitReady(fr);
  const m0 = await fr.evaluate(() => ({ mode: window.ISFTPaket.mode, banner: !!document.querySelector('.banner'), q: location.search }));
  ok(m0.mode === 'standalone' && !m0.banner && m0.q === '', "API va launch parametrlarisiz iframe → jim rejim, «Ko'rish rejimi» banneri YO'Q");
  const N = await navN(fr);
  // talaba «Keyingi qadam» bilan oxirigacha boradi: test (to'g'ri) va mulohaza
  for (let i = 1; i < N; i++) {
    await fr.click('.pager .btn.primary'); await sleep(60);
    if ((await currentType(fr)) === 'quiz') { await fr.click('[data-act="start"]'); await answerQuiz(fr, true); }
  }
  await fr.click('.choice[data-k="0"]'); await sleep(200);
  const M = await page.evaluate(() => window.LMS.msgs);
  const prog = M.filter(m => m.event === 'progress').map(m => m.progress);
  const ev = M.map(m => m.event);
  ok(M.length > 0 && M.every(m => m.source === 'isft-paket' && m.v === 1 && m.id === CONTENT_ID && typeof m.progress === 'number' && m.steps === N && m.step >= 1 && m.step <= N),
    `postMessage: ${M.length} ta xabar, {source:"isft-paket", v:1, id, event, progress, score, step, steps}`);
  ok(prog.length > 3 && prog.every((p, i) => i === 0 || p >= prog[i - 1]) && prog[prog.length - 1] === 1, `progress o'sib boradi: ${prog.slice(0, 4).join(', ')} … ${prog[prog.length - 1]}`);
  const pz = M.find(m => m.event === 'passed');
  ok(pz && pz.score && pz.score.raw === 100 && pz.score.scaled === 1 && pz.score.min === 0 && pz.score.max === 100, `«passed» xabari ball bilan (${JSON.stringify(pz && pz.score)})`);
  ok(ev.filter(e => e === 'completed').length === 1 && ev.indexOf('completed') > ev.indexOf('passed'), '«completed» bir marta, test o\'tilgandan keyin');
  const an = M.find(m => m.event === 'answered');
  ok(an && an.block === REFLECT.id && an.response === 1, `«answered» (mulohaza): block=${an && an.block}, response=${an && an.response}`);
  // klaviatura iframe ichida
  await clickStep(fr, 4); await fr.evaluate(() => document.activeElement.blur());
  await fr.press('body', 'ArrowRight'); await sleep(80); const k1 = await curStep(fr);
  await fr.press('body', 'PageUp'); await sleep(80); const k2 = await curStep(fr);
  ok(k1 === 5 && k2 === 4, `Iframe ichida klaviatura: → ${k1 + 1}-qadam, PageUp ${k2 + 1}-qadam`);
  await clickStep(fr, 8); await sleep(600);
  // qayta ochish → localStorage'dan o'sha qadam
  await page.evaluate(() => window.unload()); await sleep(200);
  const before = (await page.evaluate(() => window.LMS.msgs.length));
  await page.evaluate(u => window.launch('none', u), url); await sleep(200);
  fr = page.frame({ name: 'sco' }); await waitReady(fr); await sleep(200);
  const r1 = await fr.evaluate(() => ({ s: window.ISFTPaket.debug.step(), st: window.ISFTPaket.debug.status() }));
  const M2 = (await page.evaluate(() => window.LMS.msgs)).slice(before);
  ok(r1.s === 8 && r1.st.complete && r1.st.success === 'passed', `Qayta ochilganda (localStorage) o'sha qadam (${r1.s + 1}) va natija tiklandi`);
  ok(M2.some(m => m.event === 'progress' && m.progress === 1 && m.step === 9) && M2.some(m => m.event === 'completed'), "Qayta ochilganda ota oynaga joriy holat xabari (progress=1, completed)");
  await SHOT(page, 'nextid_iframe');
  // ?preview=1 → banner
  await page.evaluate(u => window.launch('none', u), url + '?preview=1'); await sleep(200);
  fr = page.frame({ name: 'sco' }); await waitReady(fr);
  ok((await fr.evaluate(() => window.ISFTPaket.mode)) === 'preview' && (await fr.textContent('.banner')).includes("Ko'rish rejimi — natija LMS'ga yuborilmaydi"), "?preview=1 → «Ko'rish rejimi — natija LMS'ga yuborilmaydi» banneri");
  await SHOT(page, 'nextid_preview_banner');
  ok(T.errs.length === 0, "Konsol xatolari yo'q" + (T.errs.length ? ': ' + T.errs.slice(0, 3).join(' | ') : ''));
  ok(T.foreign.length === 0, "Tashqi tarmoq so'rovlari yo'q");
  await T.ctx.close();
}
const CONTENT_ID = CONTENT.id;

// ---------------------------------------------------------------- SCORM paketi, lekin LMS API yo'q → ogohlantirish banneri
async function runScormNoApi(br, base) {
  section("SCORM paketi API'siz");
  for (const kind of ['scorm12', 'scorm2004']) {
    const T = await newCtx(br, {}, 'noapi_' + kind), page = T.page;
    await patchContent(T.ctx, c => { c.tracking.mode = kind; c.id += '-noapi-' + kind; });
    await page.goto(base + '/lms.html');
    await page.evaluate(u => window.launch('none', u), base + PKG + 'index.html'); await sleep(200);
    let fr = page.frame({ name: 'sco' }); await waitReady(fr);
    const b = await fr.evaluate(() => { const e = document.querySelector('.banner'); return { mode: window.ISFTPaket.mode, txt: e && e.textContent, warn: !!(e && e.classList.contains('warn')), role: e && e.getAttribute('role') }; });
    ok(b.mode === 'standalone' && b.warn && b.role === 'alert' && b.txt === "LMS bilan aloqa topilmadi — natija saqlanmaydi. O'qituvchiga xabar bering.",
      `tracking.mode=${kind}, SCORM API yo'q → ogohlantirish banneri («${b.txt}»)`);
    if (kind === 'scorm12') await SHOT(page, 'scorm_noapi_warning');
    await page.evaluate(u => window.launch('none', u), base + PKG + 'index.html?preview=1'); await sleep(200);
    fr = page.frame({ name: 'sco' }); await waitReady(fr);
    const p = await fr.evaluate(() => { const e = document.querySelector('.banner'); return { mode: window.ISFTPaket.mode, txt: e && e.textContent, warn: !!(e && e.classList.contains('warn')), n: document.querySelectorAll('.banner').length }; });
    ok(p.mode === 'preview' && !p.warn && p.n === 1 && /Ko'rish rejimi — natija LMS'ga yuborilmaydi/.test(p.txt), `${kind} + ?preview=1 → faqat «Ko'rish rejimi» banneri`);
    ok(T.errs.length === 0, "Konsol xatolari yo'q");
    await T.ctx.close();
  }
  // xAPI paket, parametrsiz → banner yo'q (NEXTID)
  const X = await newCtx(br, {}, 'noapi_xapi');
  await patchContent(X.ctx, c => { c.tracking.mode = 'xapi'; c.id += '-noapi-x'; });
  await X.page.goto(base + '/lms.html');
  await X.page.evaluate(u => window.launch('none', u), base + PKG + 'index.html'); await sleep(200);
  const xf = X.page.frame({ name: 'sco' }); await waitReady(xf);
  ok((await xf.evaluate(() => window.ISFTPaket.mode)) === 'standalone' && !(await xf.$('.banner')), "tracking.mode=xapi, launch parametrlarisiz → banner yo'q (NEXTID)");
  await X.ctx.close();
}

// ---------------------------------------------------------------- eski «scroll» layout (layout maydoni yo'q) — orqaga moslik
async function runScrollLayout(br, base) {
  section('Scroll layout (orqaga moslik)');
  const T = await newCtx(br, { viewport: { width: 1366, height: 900 } }, 'scroll'), page = T.page;
  await patchContent(T.ctx, c => { delete c.layout; c.id += '-scroll'; c.blocks.forEach(b => { if (b.type === 'slides') { b.display = 'text'; b.slides[2].image = null; } }); });
  await page.goto(base + PKG + 'index.html?preview=1'); await waitReady(page);
  const u = await page.evaluate(() => ({ toc: !!document.querySelector('nav.toc .toc-i'), rail: !!document.querySelector('.rail'), n: document.querySelectorAll('.nav-i').length }));
  ok(u.toc && !u.rail && u.n === NBLOCKS, `layout yo'q → chapda mundarija, har blok — bitta sahifa (${u.n})`);
  const hr = await page.evaluate(() => { const h = document.querySelector('#main > .hero'); return h && { t: h.querySelector('p.hero-t').textContent, h1: document.querySelectorAll('#main h1').length, go: !!h.querySelector('[data-act="begin"]'), step: !!document.querySelector('.nav-i[data-type="cover"]') }; });
  await clickStep(page, 1);
  ok(hr && hr.t === 'L1-1-dars: ' + CONTENT.lesson.title && hr.h1 === 1 && !hr.go && !hr.step && !(await page.$('#main > .hero')), 'Scroll rejimi: muqova birinchi sahifa ustida sarlavha sifatida (alohida qadam emas, «Boshlash» yo\'q)');
  ok(!!(await page.$('.banner')), '?preview=1 → banner');
  await clickStep(page, await stepIndex(page, 'text'));
  ok((await page.evaluate(() => document.querySelectorAll('.prose h2').length)) === 3, "Matn bo'linmaydi (3 ta h2 bitta sahifada)");
  await clickStep(page, await stepIndex(page, 'slides'));
  await page.focus('.deck'); await page.press('.deck', 'ArrowRight'); await page.press('.deck', 'ArrowRight'); await sleep(80);
  const s3 = await page.evaluate(() => ({ c: document.querySelector('.counter').textContent, bar: document.querySelector('.slide.gen .s-bar') && document.querySelector('.slide.gen .s-bar').textContent, li: document.querySelectorAll('.slide.gen .s-body li').length, dots: document.querySelectorAll('.dots button').length }));
  ok(s3.c === '3 / ' + SLIDES.slides.length && s3.bar === SLIDES.slides[2].title && s3.li === SLIDES.slides[2].bullets.length && s3.dots === SLIDES.slides.length, `display=text: generatsiya qilingan slayd va nuqtalar (${s3.c}, «${s3.bar}»)`);
  await SHOT(page, 'scroll_slides_text');
  await visitAllContent(page, page, null);
  ok(T.errs.length === 0, "Konsol xatolari yo'q");
  await T.ctx.close();
}

// ---------------------------------------------------------------- mobil 390px, qorong'i rejim, ish stoli skrinshotlari, chop etish
async function runVisual(br, base) {
  section('390px mobil');
  const T = await newCtx(br, { viewport: { width: 390, height: 844 }, deviceScaleFactor: 2, isMobile: true, hasTouch: true }, 'mob'), page = T.page;
  await page.goto(base + PKG + 'index.html'); await waitReady(page);
  const ov = () => page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth + 1);
  const n = await navN(page);
  const over = [];
  for (let i = 0; i < n; i++) {
    const t = await page.evaluate(i => document.querySelector('.nav-i[data-i="' + i + '"]').dataset.type, i);
    if (t === 'flashcards') await page.click('.fc[data-k="1"]');
    if (t === 'slides') await page.click('.nav-a.r');
    await sleep(t === 'flashcards' ? 700 : 320);
    if (await ov()) over.push(i);
    await SHOT(page, `mob_${pad2(i)}_${t}`, t === 'cover' || t === 'flashcards' || t === 'assignment' || (t === 'video' && i > 2));
    if (i < n - 1) { await page.click('.pager .btn.primary'); await sleep(100); }
  }
  ok(over.length === 0, `390px: hech bir qadamda gorizontal toshish yo'q (keng jadval ham) (${over.join(',')})`);
  const tbl = await page.evaluate(() => { const ti = [...document.querySelectorAll('.nav-i[data-type="text"]')][1]; ti.click(); const w = document.querySelector('.tbl'); return w && { sw: w.scrollWidth, cw: w.clientWidth, ox: getComputedStyle(w).overflowX }; });
  ok(tbl && tbl.sw > tbl.cw && tbl.ox === 'auto', `Keng jadval karta ichida aylanadi (${tbl && tbl.sw}px > ${tbl && tbl.cw}px, overflow-x:auto)`);
  const pg = await page.evaluate(() => { const p = document.querySelector('.pager'); const r = p.getBoundingClientRect(); return { pos: getComputedStyle(p).position, bottom: Math.round(r.bottom), vh: innerHeight }; });
  ok(pg.pos === 'sticky' && pg.bottom <= pg.vh, `Mobil: pastki panel (sticky) — oldingi / «3 / N qadam» / Keyingi qadam (${pg.bottom}/${pg.vh})`);
  await clickStep(page, await stepIndex(page, 'quiz'));
  await page.click('[data-act="start"]');
  // match/sort bosh barmoq bilan: yarim to'ldirilgan holat (skrinshot), nishon o'lchamlari ≥ 44px, toshish yo'q
  const Mq = `fieldset[data-qid="${MATCH.id}"]`, Sq = `fieldset[data-qid="${SORT.id}"]`;
  await page.tap(`${Mq} .m-slot[data-l="0"]`); await page.tap(`${Mq} .m-tile[data-r="0"]`); await page.tap(`${Mq} .m-tile[data-r="2"]`); await page.tap(`${Mq} .m-slot[data-l="1"]`); await page.tap(`${Mq} .m-slot[data-l="3"]`);
  await page.tap(`${Sq} .s-card[data-k="0"]`); await page.tap(`${Sq} .s-drop[data-c="0"]`); await page.tap(`${Sq} .s-card[data-k="4"]`); await page.tap(`${Sq} .s-drop[data-c="0"]`);
  await page.tap(`${Sq} .s-card[data-k="3"]`); await page.tap(`${Sq} .s-drop[data-c="1"]`); await page.tap(`${Sq} .s-card[data-k="1"]`); await sleep(300);
  const tp = await page.evaluate(([m, s]) => ({ slots: [...document.querySelectorAll(m + ' .m-slot')].map(e => e.dataset.r || '-').join(), cats: [...document.querySelectorAll(s + ' .s-cat')].map(c => [...c.querySelectorAll('.s-card')].map(e => e.dataset.k).join('')).join('|'),
    sel: document.querySelector(s + ' .s-card[data-k="1"]').getAttribute('aria-pressed'), min: Math.min(...[...document.querySelectorAll('.m-slot,.m-tile:not([hidden]),.s-card,.s-drop')].map(e => Math.round(e.getBoundingClientRect().height))),
    wide: [...document.querySelectorAll('.m-row,.m-bank,.s-deck,.s-cats')].every(e => e.getBoundingClientRect().right <= innerWidth), cols: getComputedStyle(document.querySelector('.s-cats')).gridTemplateColumns.split(' ').length }), [Mq, Sq]);
  ok(tp.slots === '0,2,-,-' && tp.cats === '04|3' && tp.sel === 'true', `390px sensor: match (${tp.slots}) va sort (${tp.cats}) bosib tanlash bilan ishlaydi`);
  ok(tp.min >= 44 && tp.wide && !(await ov()), `390px: match/sort nishonlari ≥ 44px (eng kichigi ${tp.min}px), ${tp.cols} ustunli toifalar, gorizontal toshish yo'q`);
  await SHOT(page, 'mob_quiz_form', true);
  await answerQuiz(page, true);
  ok(!(await ov()), '390px: test natijasi sahifasida toshish yo\'q');
  await SHOT(page, 'mob_quiz_result', true);
  // qadamlar tortmasi (hisoblagich tugmasi)
  await page.click('.pager .pos'); await sleep(350);
  const open = await page.evaluate(() => ({ o: document.getElementById('app').classList.contains('toc-open'), f: document.activeElement && document.activeElement.classList.contains('nav-i'), e: document.querySelector('.pager .pos').getAttribute('aria-expanded'), lbl: getComputedStyle(document.querySelector('.step .lbl')).display }));
  ok(open.o && open.f && open.e === 'true' && open.lbl !== 'none', 'Qadamlar tortmasi ochiladi (nomlari bilan), fokus ichkariga o\'tadi (aria-expanded)');
  await SHOT(page, 'mob_steps_drawer');
  await page.keyboard.press('Escape'); await sleep(300);
  ok(!(await page.evaluate(() => document.getElementById('app').classList.contains('toc-open'))), 'Esc tortmani yopadi');
  // galereya: surish (swipe)
  await clickStep(page, await stepIndex(page, 'slides'));
  const box = await page.$eval('.deck', e => { const r = e.getBoundingClientRect(); return { x: r.x, y: r.y, w: r.width, h: r.height }; });
  await page.evaluate(b => {
    const d = document.querySelector('.deck'), y = b.y + b.h / 2;
    d.dispatchEvent(new PointerEvent('pointerdown', { clientX: b.x + b.w - 30, clientY: y, bubbles: true }));
    d.dispatchEvent(new PointerEvent('pointerup', { clientX: b.x + 30, clientY: y, bubbles: true }));
  }, box);
  ok((await page.textContent('.counter')) === '2 / ' + SLIDES.slides.length, 'Surish (swipe) keyingi slaydga o\'tkazadi');
  await answerReflect(page, 0);
  await SHOT(page, 'mob_reflect_answered');
  await clickStep(page, await stepIndex(page, 'slides')); await sleep(500);
  await page.reload(); await waitReady(page);
  ok((await currentType(page)) === 'slides' && (await doneCount(page)) === n, 'localStorage orqali resume (joriy qadam, ✓ belgilar, test natijasi)');
  ok(T.errs.length === 0, 'Konsol xatolari yo\'q' + (T.errs.length ? ': ' + T.errs.slice(0, 3).join(' | ') : ''));
  ok(T.foreign.length === 0, "Tashqi tarmoq so'rovlari yo'q");
  await T.ctx.close();
  // localStorage bloklangan (sandbox iframe opaque origin) — yiqilmasligi kerak
  const T2 = await newCtx(br, {}, 'nols');
  await T2.page.setContent(`<iframe sandbox="allow-scripts" src="${base + PKG}index.html" style="width:100%;height:600px"></iframe>`);
  await sleep(1200);
  const fr = T2.page.frames()[1];
  ok(fr && (await fr.evaluate(() => window.ISFTPaket && window.ISFTPaket.ready)), 'localStorage mavjud bo\'lmagan muhitda (sandbox) ham ishlaydi');
  ok(T2.errs.length === 0, 'Sandbox: konsol xatolari yo\'q' + (T2.errs.length ? ': ' + T2.errs.slice(0, 2).join(' | ') : ''));
  {   // <video crossorigin>: faqat sandboxed ko'rishda (opaque origin + http); file:// da — yo'q
    const vAttr = f => f.evaluate(() => { let v = null; for (const n of document.querySelectorAll('.nav-i[data-type="video"]')) { n.click(); v = document.querySelector('.video.file video'); if (v) break; }
      return { co: v ? v.getAttribute('crossorigin') : 'video yo\'q', origin: String(window.origin), proto: location.protocol, tracks: v ? v.querySelectorAll('track').length : 0 }; });
    const a1 = await vAttr(fr);
    ok(a1.origin === 'null' && a1.proto === 'http:' && a1.co === 'anonymous' && a1.tracks > 0, `Sandboxed ko'rish (origin «${a1.origin}», ${a1.proto}): <video crossorigin="anonymous"> — <track> yuklanishi uchun`);
    const dir = path.join(OUT, 'filepkg'); fs.rmSync(dir, { recursive: true, force: true });
    fs.cpSync(FIX, dir, { recursive: true }); fs.cpSync(PLAYER, dir, { recursive: true });
    const T3 = await newCtx(br, {}, 'fileurl');
    await T3.page.goto(require('url').pathToFileURL(path.join(dir, 'index.html')).href); await waitReady(T3.page);
    const a2 = await vAttr(T3.page);
    ok(a2.proto === 'file:' && a2.co === null && a2.tracks > 0, `file:// (origin «${a2.origin}»): <video> crossorigin atributisiz (${JSON.stringify(a2.co)})`);
    await T3.ctx.close();
  }
  await T2.ctx.close();

  section("Ish stoli · qorong'i rejim · klaviatura");
  const D = await newCtx(br, { colorScheme: 'dark', viewport: { width: 1366, height: 900 } }, 'dark'), dp = D.page;
  await dp.goto(base + PKG + 'index.html'); await waitReady(dp);
  ok(await dp.evaluate(() => matchMedia('(prefers-color-scheme: dark)').matches && getComputedStyle(document.body).backgroundColor !== 'rgb(244, 245, 247)'), "Qorong'i rejim: prefers-color-scheme ishladi");
  const bq = await dp.evaluate(() => { const ti = document.querySelectorAll('.nav-i[data-type="text"]')[1]; ti.click(); const b = document.querySelector('.prose blockquote'); return b && getComputedStyle(b).backgroundColor; });
  ok(bq && !/rgb\(2[0-9]{2}, 2[0-9]{2}, 2[0-9]{2}\)/.test(bq), `Qorong'i rejimda iqtibos foni to'q (${bq})`);
  const dn = await navN(dp);
  for (let i = 0; i < dn; i++) { await clickStep(dp, i); const t = await currentType(dp); if (t === 'flashcards') await dp.click('.fc[data-k="1"]'); if (t === 'slides') await dp.click('.nav-a.r'); await sleep(t === 'flashcards' ? 700 : 320); await SHOT(dp, `dark_${pad2(i)}_${t}`); }
  await clickStep(dp, await stepIndex(dp, 'quiz')); await dp.click('[data-act="start"]'); await demoFill(dp); await SHOT(dp, 'dark_quiz_form', true);
  const dk = await dp.evaluate(() => { const bg = s => getComputedStyle(document.querySelector(s)).backgroundColor; return [bg('.m-slot.filled'), bg('.m-bank'), bg('.s-cat'), bg('.s-card[aria-pressed="false"]')]; });
  ok(dk.every(c => { const m = c.match(/\d+/g).map(Number); return m[0] + m[1] + m[2] < 330; }), `Qorong'i rejim: match/sort fonlari to'q (${dk.join(' ; ')})`);
  await answerQuiz(dp, false); await SHOT(dp, 'dark_quiz_failed', true);
  // klaviatura: Tab bilan skip-havola, landmarklar
  await dp.reload(); await waitReady(dp);
  await dp.keyboard.press('Tab');
  ok(await dp.evaluate(() => document.activeElement.classList.contains('skip')), 'Birinchi Tab — «Asosiy mazmunga o\'tish» havolasi');
  const lm = await dp.evaluate(() => ({ h: !!document.querySelector('header'), n: !!document.querySelector('nav[aria-label]'), m: !!document.querySelector('main#main'), live: !!document.querySelector('[aria-live]'),
    pb: document.querySelector('[role=progressbar]').getAttribute('aria-valuenow'), alt: [...document.querySelectorAll('img')].every(i => i.hasAttribute('alt')), lang: document.documentElement.lang,
    lbl: [...document.querySelectorAll('.nav-i')].every(b => /^\d+-qadam: /.test(b.getAttribute('aria-label'))) }));
  ok(lm.h && lm.n && lm.m && lm.live && lm.pb != null && lm.alt && lm.lang === 'uz' && lm.lbl, 'Landmarklar (header/nav/main), aria-live, progressbar, img alt, lang=uz, qadam tugmalarida aria-label');
  ok(D.errs.length === 0, 'Konsol xatolari yo\'q' + (D.errs.length ? ': ' + D.errs.slice(0, 3).join(' | ') : ''));
  await D.ctx.close();

  section('Ish stoli 1366 · chop etish');
  const L = await newCtx(br, { viewport: { width: 1366, height: 900 } }, 'light'), lp = L.page;
  await lp.goto(base + PKG + 'index.html'); await waitReady(lp);
  const ln = await navN(lp);
  for (let i = 0; i < ln; i++) { await clickStep(lp, i); const t = await currentType(lp); if (t === 'flashcards') await lp.click('.fc[data-k="1"]'); if (t === 'slides') await lp.click('.nav-a.r'); await sleep(t === 'flashcards' ? 700 : 320); await SHOT(lp, `desk_${pad2(i)}_${t}`); }
  ok(!(await lp.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth + 1)), '1366px: gorizontal toshish yo\'q');
  await clickStep(lp, await stepIndex(lp, 'text')); await lp.click('.prose .zoom'); await sleep(200); await SHOT(lp, 'desk_lightbox'); await lp.keyboard.press('Escape');
  await answerReflect(lp, 1); await SHOT(lp, 'desk_reflect_answered');
  await clickStep(lp, await stepIndex(lp, 'quiz')); await lp.click('[data-act="start"]'); await demoFill(lp); await SHOT(lp, 'desk_quiz_form', true);
  await lp.emulateMedia({ media: 'print' }); await sleep(200);
  const pr = await lp.evaluate(() => { const p = document.querySelector('.print-all'); return { top: getComputedStyle(document.querySelector('.top')).display, wrap: getComputedStyle(document.querySelector('.wrap')).display,
    shown: p && getComputedStyle(p).display, vid: p ? p.querySelectorAll('.p-video img').length : 0, vt: p ? [...p.querySelectorAll('.p-blk.t-video p')].map(x => x.textContent).join(' | ') : '', fc: p ? p.querySelectorAll('.p-fc dt').length : 0,
    asg: p ? p.querySelectorAll('.p-blk.t-assignment ol li').length : 0, cap: p ? p.querySelectorAll('.p-sl figcaption').length : 0, sec: p ? p.querySelectorAll('.p-sec').length : 0, h2: p ? p.querySelectorAll('.prose h2').length : 0, fig: p ? p.querySelectorAll('.prose figure figcaption').length : 0, sl: p ? p.querySelectorAll('.p-sl').length : 0, ids: p ? p.querySelectorAll('[id]').length : -1 }; });
  ok(pr.top === 'none' && pr.wrap === 'none' && pr.shown === 'block', 'Chop etish: sarlavha/navigatsiya yashirinadi, barcha qadamlar ketma-ket');
  ok(pr.sec === 4 && pr.h2 === 3 && pr.fig === 2 && pr.sl === SLIDES.slides.length + 1 && pr.ids === 0, `Chop etish mazmuni: ${pr.sec} bo'lim, ${pr.h2} h2, ${pr.fig} rasm izohi, ${pr.sl - 1} slayd (takroriy id yo'q)`);
  ok(pr.vid === 1 && pr.vt.includes(VFILE.title) && pr.fc === FLASH.cards.filter(c => c.front && c.back).length && pr.asg === ASSIGN.questions.length && pr.cap === SLIDES.slides.filter(s => s.caption).length,
    `Chop etish (v3): fayl-video — poster + nom, ${pr.fc} kartochka (old/orqa), ${pr.asg} topshiriq savoli, ${pr.cap} slayd izohi`);
  await SHOT(lp, 'print_all', true);
  ok(L.errs.length === 0, 'Konsol xatolari yo\'q' + (L.errs.length ? ': ' + L.errs.slice(0, 3).join(' | ') : ''));
  await L.ctx.close();
}

(async () => {
  const lmsPort = await listen(lms), lrsPort = await listen(lrs);
  const base = 'http://127.0.0.1:' + lmsPort, lrsBase = 'http://127.0.0.1:' + lrsPort;
  const br = await chromium.launch({ executablePath: process.env.CHROME || undefined });
  const only = (process.env.ONLY || '').split(',').filter(Boolean);
  const run = async (name, fn) => { if (only.length && !only.includes(name)) return; try { await fn(); } catch (e) { ok(false, 'Sinov to\'xtadi: ' + (e && e.stack || e).toString().split('\n').slice(0, 3).join(' ')); } };
  try {
    await run('scorm12', () => runScorm(br, base, 'scorm12'));
    await run('scorm2004', () => runScorm(br, base, 'scorm2004'));
    await run('none', () => runModeNone(br, base));
    await run('xapi', () => runXapi(br, base, lrsBase));
    await run('xapi_va', () => runXapiViewAll(br, base, lrsBase));
    await run('bad', () => runBadUrls(br, base));
    await run('steps', () => runSteps(br, base));
    await run('v3', () => runV3(br, base));
    await run('nextid', () => runNextid(br, base));
    await run('noapi', () => runScormNoApi(br, base));
    await run('scroll', () => runScrollLayout(br, base));
    await run('visual', () => runVisual(br, base));
  } finally {
    await br.close(); lms.close(); lrs.close();
  }
  console.log('\nJamlanma:');
  Object.keys(counts).forEach(k => console.log(`  ${k}: ${counts[k][0]} o'tdi, ${counts[k][1]} xato`));
  console.log('Skrinshotlar: ' + OUT);
  process.exit(fails.length ? 1 : 0);
})();
