#!/usr/bin/env node
/* ISFT o'quv paket pleyeri — muvofiqlik sinovi (SCORM 1.2, SCORM 2004 4-nashr, xAPI, ko'rish rejimi).
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
const OUT = process.env.OUT || '/private/tmp/claude-501/-Users-levi-Desktop-isft/c7457261-2842-4588-b99e-aae3cce064d9/scratchpad/paketB';
const CONTENT = JSON.parse(fs.readFileSync(path.join(FIX, 'content.json'), 'utf8'));
const QUIZ = CONTENT.blocks.find(b => b.type === 'quiz');
const NBLOCKS = CONTENT.blocks.filter(b => ['plan', 'text', 'slides', 'video', 'file', 'quiz'].includes(b.type)).length;
const NCONTENT = NBLOCKS - 1;
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
  const store = { sessions: [], persist: { entry: 'ab-initio', status: '', location: '', suspend: '', raw: '', total: 0 } };
  window.LMS = store;
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
    f.src = url;
  };
  window.unload = function () { document.getElementById('sco').src = 'about:blank'; };
}
const LMS_HTML = `<!doctype html><html><head><meta charset="utf-8"><title>Mock LMS</title>
<style>body{margin:0;font:14px system-ui}header{background:#333;color:#fff;padding:6px 12px}iframe{border:0;width:100%;height:calc(100vh - 32px);display:block}</style></head>
<body><header>Mock LMS</header><iframe id="sco" name="sco" title="SCO"></iframe><script>(${lmsRuntime.toString()})();</script></body></html>`;

// ---------------------------------------------------------------- serverlar
const MIME = { '.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8', '.css': 'text/css', '.json': 'application/json', '.png': 'image/png',
  '.pdf': 'application/pdf', '.woff2': 'font/woff2', '.pptx': 'application/vnd.openxmlformats-officedocument.presentationml.presentation' };
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
async function waitReady(fr) { await fr.waitForFunction(() => window.ISFTPaket && window.ISFTPaket.ready, null, { timeout: 15000 }); }
async function clickToc(fr, i) {
  await fr.evaluate(i => { const b = document.querySelector('.toc-i[data-i="' + i + '"]'); b.click(); }, i);
  await sleep(120);
}
async function blockIndex(fr, type) { return fr.evaluate(t => +document.querySelector('.toc-i[data-type="' + t + '"]').dataset.i, type); }
async function doneCount(fr) { return fr.evaluate(() => document.querySelectorAll('.toc-i.done').length); }
async function currentType(fr) { return fr.evaluate(() => { const c = document.querySelector('.toc-i[aria-current]'); return c && c.dataset.type; }); }
async function answerQuiz(fr, right) {
  await fr.waitForSelector('form.qform');
  for (const q of QUIZ.questions) {
    const sel = `fieldset[data-qid="${q.id}"]`;
    if (q.type === 'fill') {
      await fr.fill(sel + ' input', right ? '  O‘SADI ' : 'bilmayman');   // apostrof varianti + katta harf + bo'shliq
    } else {
      const corr = q.correct, n = (q.options || ['', '']).length;
      const pick = right ? corr : [[...Array(n).keys()].find(i => !corr.includes(i))];
      for (const i of pick) await fr.check(`${sel} input[value="${i}"]`);
    }
  }
  await fr.click('form.qform [data-act="submit"]'); await sleep(250);
}
const SHOT = async (p, name, full) => { await p.screenshot({ path: path.join(OUT, name + '.png'), fullPage: !!full }); };

// ---------------------------------------------------------------- umumiy UI tekshiruvlari (iframe yoki sahifa)
async function visitAllContent(fr, page, shotPrefix) {
  const n = await fr.evaluate(() => document.querySelectorAll('.toc-i').length);
  ok(n === NBLOCKS, `Navigatsiyada ${NBLOCKS} ta blok (noma'lum «hotspot» e'tiborsiz): ${n}`);
  for (let i = 0; i < n; i++) {
    const t = await fr.evaluate(i => document.querySelector('.toc-i[data-i="' + i + '"]').dataset.type, i);
    if (t === 'quiz') continue;
    await clickToc(fr, i);
    if (shotPrefix) await SHOT(page, `${shotPrefix}_${i}_${t}`);
  }
  ok(await doneCount(fr) === NCONTENT, `Barcha kontent bloklari ✓ belgilandi (${await doneCount(fr)}/${NCONTENT})`);
}
async function checkBlocks(fr) {
  // matn: sanitizer
  await clickToc(fr, await blockIndex(fr, 'text'));
  const san = await fr.evaluate(() => {
    const p = document.querySelector('.prose');
    return { script: !!p.querySelector('script,style,iframe'), on: [...p.querySelectorAll('*')].some(e => [...e.attributes].some(a => /^on/i.test(a.name) || a.name === 'style')),
      js: !!p.querySelector('a[href^="javascript"]'), evil: !!p.querySelector('img[src*="evil"]'), xss: window.__xss,
      ext: [...p.querySelectorAll('a[href]')].map(a => [a.getAttribute('href'), a.target, a.rel]), h2: p.querySelectorAll('h2').length, tbl: !!p.querySelector('.tbl table'),
      img: !!p.querySelector('img[src="assets/slides/s2.png"][alt]') };
  });
  ok(!san.script && !san.on && !san.js && !san.evil && san.xss === undefined, "Sanitizer: script/style/iframe, on*/style atributlari, javascript: havola, tashqi rasm olib tashlandi");
  ok(san.ext.length === 1 && san.ext[0][0] === 'https://isft.uz/kutubxona' && san.ext[0][1] === '_blank' && /noopener/.test(san.ext[0][2]), "Tashqi havola: faqat https, target=_blank rel=noopener");
  ok(san.h2 === 3 && san.tbl && san.img, "Ruxsat etilgan teglar saqlandi (h2, jadval, paket ichidagi rasm alt bilan)");
  // reja → matn sarlavhasi
  await clickToc(fr, await blockIndex(fr, 'plan'));
  const links = await fr.evaluate(() => [...document.querySelectorAll('.plan li')].map(li => !!li.querySelector('button.link')));
  ok(links.join() === 'true,true,true,false', `Reja: mos sarlavhalar havola, mos kelmagani oddiy matn (${links.join()})`);
  await fr.evaluate(() => [...document.querySelectorAll('.plan button.link')].find(b => b.textContent === 'Bozor muvozanati').click()); await sleep(200);
  const foc = await fr.evaluate(() => document.activeElement && document.activeElement.tagName + ':' + document.activeElement.textContent);
  ok((await currentType(fr)) === 'text' && foc === 'H2:Bozor muvozanati', `Reja havolasi matn blokidagi sarlavhaga o'tkazdi va fokusladi (${foc})`);
  // slaydlar
  await clickToc(fr, await blockIndex(fr, 'slides'));
  await fr.focus('.deck'); await fr.press('.deck', 'ArrowRight'); await sleep(80);
  const s2 = await fr.evaluate(() => ({ c: document.querySelector('.counter').textContent, img: !!document.querySelector('.stage img[src="assets/slides/s2.png"]') }));
  await fr.press('.deck', 'ArrowRight'); await sleep(80);
  const s3 = await fr.evaluate(() => ({ c: document.querySelector('.counter').textContent, bar: document.querySelector('.slide.gen .s-bar') && document.querySelector('.slide.gen .s-bar').textContent, li: document.querySelectorAll('.slide.gen .s-body li').length }));
  ok(s2.c === '2 / 4' && s2.img && s3.c === '3 / 4' && s3.bar === 'Talab qonuni' && s3.li === 4, `Slaydlar: ← → klaviatura, rasmli va generatsiya qilingan slayd (${s2.c}, ${s3.c})`);
  await fr.click('.deck-bar [aria-controls]');
  const notes = await fr.evaluate(() => ({ h: document.querySelector('.notes').hidden, e: document.querySelector('.deck-bar [aria-controls]').getAttribute('aria-expanded') }));
  ok(!notes.h && notes.e === 'true', 'Izohlar tugmasi ochadi (aria-expanded)');
  const dl = await fr.evaluate(() => [...document.querySelectorAll('.t-slides .tools a')].map(a => a.textContent.trim() + '|' + a.getAttribute('href')));
  ok(dl.includes("PDF ko'rinishida ochish|assets/taqdimot.pdf") && dl.includes('Taqdimotni yuklab olish|assets/taqdimot.pptx'), 'PDF ochish va taqdimotni yuklab olish havolalari');
  // video
  await clickToc(fr, await blockIndex(fr, 'video'));
  const v = await fr.evaluate(() => { const f = document.querySelector('.video iframe'); return f && { src: f.src, title: f.title, allow: f.allow, fb: !!document.querySelector('a[href^="https://www.youtube.com/watch?v=dQw4w9WgXcQ"]') }; });
  ok(v && v.src.startsWith('https://www.youtube-nocookie.com/embed/dQw4w9WgXcQ?') && /start=15/.test(v.src) && /rel=0/.test(v.src) && v.title && /encrypted-media/.test(v.allow) && v.fb,
    "Video: youtube-nocookie embed (start, rel=0, title, allow) + «YouTube'da ochish»");
  await clickToc(fr, await blockIndex(fr, 'file'));
  const f = await fr.evaluate(() => [...document.querySelectorAll('.filecard a')].map(a => a.getAttribute('href')));
  ok(f.length === 2 && f.every(h => h === 'assets/qollanma.pdf'), 'Fayl bloki: ochish + yuklab olish (nisbiy havola)');
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
  await visitAllContent(fr(), page, is12 ? null : 's04');
  await checkBlocks(fr());
  s0 = await S(0);
  ok(s0.commits > 0, `Bloklarni ko'rishda Commit chaqirildi (${s0.commits})`);
  const sd0 = s0.values['cmi.suspend_data'];
  ok(sd0 && sd0.length <= (is12 ? 4096 : 64000), `suspend_data yozildi (${sd0.length} belgi)`);
  if (!is12) ok(+s0.values['cmi.progress_measure'] > 0.8 && +s0.values['cmi.progress_measure'] < 1, `progress_measure = ${s0.values['cmi.progress_measure']}`);
  // test — noto'g'ri
  const qi = await blockIndex(fr(), 'quiz');
  await clickToc(fr(), qi);
  await fr().click('[data-act="start"]');
  const ord1 = await fr().evaluate(() => [...document.querySelectorAll('fieldset.q')].map(f => f.dataset.qid).join());
  await answerQuiz(fr(), false);
  s0 = await S(0);
  const st0 = is12 ? s0.values['cmi.core.lesson_status'] : s0.values['cmi.success_status'] + '/' + s0.values['cmi.completion_status'];
  ok(is12 ? st0 === 'failed' : st0 === 'failed/incomplete', `Noto'g'ri javoblar → ${st0}`);
  const raw0 = is12 ? s0.values['cmi.core.score.raw'] : s0.values['cmi.score.raw'];
  ok(raw0 === '0' && (is12 || s0.values['cmi.score.scaled'] === '0'), `Ball 0 (raw=${raw0}${is12 ? '' : ', scaled=' + s0.values['cmi.score.scaled']}), min/max 0/100`);
  ok(s0.inter.length === QUIZ.questions.length && s0.inter.every(i => i.id && i.type && i.result === (is12 ? 'wrong' : 'incorrect') && (is12 ? i.time : i.timestamp)),
    `interactions: ${s0.inter.length} ta (id, type, javob, result, vaqt)`);
  const types = s0.inter.map(i => i.type + ':' + (is12 ? i.student_response : i.learner_response)).join(' | ');
  ok(/choice/.test(types) && /true-false:(f|false)/.test(types) && /fill-in:bilmayman/.test(types), 'interaction turlari va javob formati: ' + types);
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
  await page.evaluate(([k, u]) => window.launch(k, u), [kind, url]); await sleep(300); await waitReady(fr());
  let s1 = await S(1);
  ok(s1.values[is12 ? 'cmi.core.entry' : 'cmi.entry'] === 'resume' && s1.inits === 1, 'Ikkinchi sessiya: entry=resume');
  ok((await currentType(fr())) === 'quiz', 'Resume: location bo\'yicha test blokiga qaytdi');
  ok(await doneCount(fr()) === NCONTENT, `Resume: ko'rilgan bloklar ✓ saqlangan (${await doneCount(fr())})`);
  const res1 = await fr().evaluate(() => ({ score: document.querySelector('.ring span') && document.querySelector('.ring span').textContent, retry: !!document.querySelector('[data-act="retry"]') }));
  ok(res1.score === '0%' && res1.retry, `Resume: oxirgi test natijasi va javoblar tiklandi (${JSON.stringify(res1)})`);
  // qayta urinish — to'g'ri
  await fr().click('[data-act="retry"]');
  const ord2 = await fr().evaluate(() => [...document.querySelectorAll('fieldset.q')].map(f => f.dataset.qid).join());
  await answerQuiz(fr(), true);
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
    ok(ch.every(i => i['correct_responses.0.pattern'] && !('correct_responses.1.pattern' in i)), 'choice/true-false: bitta correct_responses.0.pattern');
  }
  ok((await fr().evaluate(() => document.querySelector('.chip').textContent)).startsWith("O'tdi") && (await doneCount(fr())) === NBLOCKS, 'UI: «O\'tdi» va barcha bloklar ✓');
  ok(ord1 !== '' && ord2 !== '' && QUIZ.questions.every(q => ord2.split(',').includes(q.id)), `Aralashtirish: urinish tartiblari (${ord1} | ${ord2})`);
  if (is12) await SHOT(page, 's12_quiz_passed', true);
  await page.evaluate(() => window.unload()); await sleep(400);
  s1 = await S(1);
  ok(s1.finishes === 1 && s1.values[is12 ? 'cmi.core.exit' : 'cmi.exit'] === (is12 ? '' : 'normal'), `Yakunlangan — exit="${s1.values[is12 ? 'cmi.core.exit' : 'cmi.exit']}", Finish bir marta`);
  // o'tgan natija: suspend_data'dan javoblar tushib qolsa ham qayta urinish berilmaydi; keyingi «muvaffaqiyatsiz» holat LMS'dagi passed'ni pasaytirmaydi
  const sdPassed = s1.values['cmi.suspend_data'];
  for (const [label, drop] of [['javoblar tushib qolgan holat', false], ["holatda p:0, s:0 (keyingi muvaffaqiyatsiz natija)", true]]) {
    const stx = JSON.parse(sdPassed); Object.values(stx.q).forEach(q => { delete q.a; if (drop) { q.p = 0; q.s = 0; } });
    await page.evaluate(([is12, sd]) => Object.assign(window.LMS.persist, { entry: 'resume', status: is12 ? 'passed' : 'completed', success: 'passed', suspend: sd, location: '', raw: '100' }), [is12, JSON.stringify(stx)]);
    await page.evaluate(([k, u]) => window.launch(k, u), [kind, url]); await sleep(300); await waitReady(fr());
    await clickToc(fr(), qi);
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
  await T.ctx.route(/content\.js$/, async r => { const resp = await r.fetch(); const b = (await resp.text()).replace('"mode": "scorm12"', '"mode": "none"'); r.fulfill({ response: resp, body: b }); });
  await page.goto(base + '/lms.html');
  await page.evaluate(u => window.launch('scorm12', u), base + PKG + 'index.html'); await sleep(200);
  const fr = page.frame({ name: 'sco' }); await waitReady(fr);
  const s = await page.evaluate(() => window.LMS.sessions[0]);
  ok((await fr.evaluate(() => window.ISFTPaket.mode)) === 'preview' && s.calls.length === 0, 'tracking.mode=none: LMS API chaqirilmaydi, ko\'rish rejimi');
  ok(/natija LMS'ga yuborilmaydi/.test(await fr.evaluate(() => document.querySelector('.banner').textContent)), 'Banner ko\'rsatildi');
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
  await visitAllContent(page, page, null);
  const qi = await blockIndex(page, 'quiz');
  await clickToc(page, qi); await page.click('[data-act="start"]'); await answerQuiz(page, false);
  await sleep(2600);   // 503 dan keyin 2 s qayta urinish
  ok(LRS.posts >= 2 && LRS.statements.some(s => s.verb.id.endsWith('/initialized')), `503 dan keyin qayta yuborildi (POST: ${LRS.posts})`);
  await page.reload(); await waitReady(page); await sleep(500);
  const vAll = LRS.statements.map(s => s.verb.id.split('/').pop()), v1 = vAll.slice(0, vAll.indexOf('terminated') + 1);
  ok(v1[0] === 'initialized' && v1.filter(x => x === 'experienced').length === NBLOCKS && v1.filter(x => x === 'answered').length === QUIZ.questions.length
     && v1.includes('failed') && v1.indexOf('terminated') > v1.indexOf('failed'), '1-sessiya fe\'llari: ' + compact(v1));
  ok((await currentType(page)) === 'quiz' && (await doneCount(page)) === NCONTENT, 'State API orqali resume: test bloki va ✓ belgilar tiklandi');
  ok(LRS.stateReq.some(r => r.m === 'PUT') && LRS.stateReq.filter(r => r.m === 'GET').length >= 2 && LRS.stateReq.every(r => r.key.endsWith('|isft-state|' + reg) && r.auth === auth && r.ver === '1.0.3'),
    `State API: GET/PUT stateId=isft-state + registration + auth (${LRS.stateReq.map(r => r.m).join(',')})`);
  await page.click('[data-act="retry"]'); await answerQuiz(page, true); await sleep(400);
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
  const child = st.filter(s => /experienced|answered|passed|failed/.test(s.verb.id) && s.object.id !== actId);   // kurs darajasidagi passed/failed — ota-activity'siz
  ok(child.every(s => s.context.contextActivities.parent[0].id === actId), 'Blok/savol statementlarida contextActivities.parent = kurs activity');
  ok(st.filter(s => s.verb.id.endsWith('/experienced')).every(s => s.object.id.startsWith(actId + '/block/')), 'experienced obyekti: activity_id + "/block/<id>"');
  const ans = st.filter(s => s.verb.id.endsWith('/answered'));
  ok(ans.every(s => typeof s.result.success === 'boolean' && typeof s.result.response === 'string' && s.object.definition.interactionType), 'answered: result.success, result.response, interactionType');
  const fq = QUIZ.questions.find(q => q.type === 'fill'), fAns = ans.filter(s => s.object.definition.interactionType === 'fill-in');
  ok(fAns.length >= 1 && fAns.every(s => JSON.stringify(s.object.definition.correctResponsesPattern) === JSON.stringify(fq.answers)),
    'fill-in: correctResponsesPattern — har muqobil javob alohida element (' + (fAns[0] ? JSON.stringify(fAns[0].object.definition.correctResponsesPattern) : '-') + ')');
  ok(ans.filter(s => s.object.definition.interactionType !== 'fill-in').every(s => s.object.definition.correctResponsesPattern.length === 1), 'choice/true-false: bitta correctResponsesPattern');
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
  await T.ctx.route(/content\.js$/, async r => { const resp = await r.fetch(); const b = (await resp.text()).replace('"completion": "view_and_quiz"', '"completion": "view_all"').replace('"id": "isft-12-5-', '"id": "isft-12-5-va-'); r.fulfill({ response: resp, body: b }); });
  const actId = 'https://isft.uz/xapi/paket/12/5/va', reg = '9b2c1d0e-1111-4222-8333-444455556666';
  const q = new URLSearchParams({ endpoint: lrsBase + '/xapi/', auth: 'Basic eDp5', actor: JSON.stringify({ mbox: 'mailto:va@isft.uz', name: 'VA' }), registration: reg, activity_id: actId });
  const n0 = LRS.statements.length;
  await page.goto(base + PKG + 'index.html?' + q.toString()); await waitReady(page);
  await visitAllContent(page, page, null); await sleep(600);
  const mine = () => LRS.statements.slice(n0).filter(s => s.context && s.context.registration === reg);
  const course = () => mine().filter(s => s.object.id === actId).map(s => s.verb.id.split('/').pop());
  ok(course().includes('completed') && !course().some(v => /passed|failed/.test(v)), "Barcha bloklar ko'rildi → kurs uchun completed (testsiz — passed/failed yo'q): " + course().join(','));
  const qi = await blockIndex(page, 'quiz');
  await clickToc(page, qi); await page.click('[data-act="start"]'); await answerQuiz(page, false); await sleep(400);
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
  await T.ctx.route(/content\.js$/, async r => {
    const resp = await r.fetch(), js = await resp.text(), c = JSON.parse(js.trim().replace(/^window\.PAKET = /, '').replace(/;$/, ''));
    c.tracking.mode = 'none'; c.id = c.id + '-bad';
    c.blocks.forEach(b => { if (b.type === 'file') b.href = 'java\tscript:window.__xss=5'; if (b.type === 'slides') { b.pdf = ' java\nscript:window.__xss=6'; b.file = '\x01javascript:window.__xss=7'; } });
    c.brand.logo = 'java\tscript:window.__xss=8';
    r.fulfill({ response: resp, body: 'window.PAKET = ' + JSON.stringify(c) + ';' });
  });
  await page.goto(base + PKG + 'index.html'); await waitReady(page);
  await clickToc(page, await blockIndex(page, 'file'));
  const f = await page.evaluate(() => ({ links: [...document.querySelectorAll('a[href],img[src]')].map(a => a.getAttribute('href') || a.getAttribute('src')).filter(h => /script/i.test(h)), msg: document.querySelector('.t-file .muted') && document.querySelector('.t-file .muted').textContent }));
  await clickToc(page, await blockIndex(page, 'slides'));
  const sl = await page.evaluate(() => [...document.querySelectorAll('.t-slides .tools a, header img')].map(a => a.getAttribute('href') || a.getAttribute('src')));
  ok(f.links.length === 0 && f.msg === 'Fayl topilmadi.', `Fayl bloki: «java\\tscript:» href zararsizlantirildi (${f.msg})`);
  ok(sl.length === 0, 'Taqdimot PDF/yuklab olish havolalari va logotip: boshqaruv belgili javascript: manzillar olib tashlandi (' + sl.join(',') + ')');
  const d = await page.evaluate(() => { const a = window.ISFTPaket.debug.assetUrl; return [a('java\tscript:x'), a('/etc/passwd'), a('assets/../x'), a('a\\b'), a('assets/files/ok_1.pdf'), a('assets/slides/s%201.png')]; });
  ok(JSON.stringify(d) === JSON.stringify([null, null, null, null, 'assets/files/ok_1.pdf', 'assets/slides/s%201.png']), 'assetUrl: oq ro\'yxat (' + JSON.stringify(d) + ')');
  ok((await page.evaluate(() => window.__xss)) === undefined && T.errs.length === 0, "XSS yo'q, konsol xatolari yo'q");
  await T.ctx.close();
}
function compact(v) { const o = []; v.forEach(x => { const l = o[o.length - 1]; if (l && l[0] === x) l[1]++; else o.push([x, 1]); }); return o.map(([x, n]) => n > 1 ? x + '×' + n : x).join(' → '); }

// ---------------------------------------------------------------- ko'rish rejimi, mobil 390px, qorong'i rejim
async function runPreview(br, base) {
  section("Ko'rish rejimi · 390px");
  const T = await newCtx(br, { viewport: { width: 390, height: 844 }, deviceScaleFactor: 2, isMobile: true, hasTouch: true }, 'mob'), page = T.page;
  await page.goto(base + PKG + 'index.html'); await waitReady(page);
  ok((await page.evaluate(() => window.ISFTPaket.mode)) === 'preview', 'LMS yo\'q → ko\'rish rejimi');
  ok((await page.textContent('.banner')).includes("Ko'rish rejimi — natija LMS'ga yuborilmaydi"), 'Banner: «Ko\'rish rejimi — natija LMS\'ga yuborilmaydi»');
  const ov = () => page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth + 1);
  const n = await page.evaluate(() => document.querySelectorAll('.toc-i').length);
  const over = [];
  for (let i = 0; i < n; i++) {
    const t = await page.evaluate(i => document.querySelector('.toc-i[data-i="' + i + '"]').dataset.type, i);
    if (await ov()) over.push(i);
    await SHOT(page, `mob_${i}_${t}`, true);
    if (i < n - 1) { await page.click('.pager .btn.primary'); await sleep(150); }
  }
  ok(over.length === 0, `390px: hech bir blokda gorizontal toshish yo'q (${over.join(',')})`);
  await page.click('[data-act="start"]'); await answerQuiz(page, true);
  ok(!(await ov()), '390px: test natijasi sahifasida toshish yo\'q');
  await SHOT(page, 'mob_quiz_result', true);
  // mundarija tortmasi
  await page.click('.top .only-m'); await sleep(350);
  const open = await page.evaluate(() => ({ o: document.getElementById('app').classList.contains('toc-open'), f: document.activeElement && document.activeElement.classList.contains('toc-i'), e: document.querySelector('.top .only-m').getAttribute('aria-expanded') }));
  ok(open.o && open.f && open.e === 'true', 'Mundarija tortmasi ochiladi, fokus ichkariga o\'tadi (aria-expanded)');
  await SHOT(page, 'mob_toc');
  await page.keyboard.press('Escape'); await sleep(300);
  ok(!(await page.evaluate(() => document.getElementById('app').classList.contains('toc-open'))), 'Esc tortmani yopadi');
  // slayd: surish (swipe)
  await page.evaluate(() => [...document.querySelectorAll('.toc-i')].find(b => b.dataset.type === 'slides').click()); await sleep(150);
  const box = await page.$eval('.deck', e => { const r = e.getBoundingClientRect(); return { x: r.x, y: r.y, w: r.width, h: r.height }; });
  await page.evaluate(b => {
    const d = document.querySelector('.deck'), y = b.y + b.h / 2;
    d.dispatchEvent(new PointerEvent('pointerdown', { clientX: b.x + b.w - 30, clientY: y, bubbles: true }));
    d.dispatchEvent(new PointerEvent('pointerup', { clientX: b.x + 30, clientY: y, bubbles: true }));
  }, box);
  ok((await page.textContent('.counter')) === '2 / 4', 'Surish (swipe) keyingi slaydga o\'tkazadi');
  // localStorage resume
  await page.reload(); await waitReady(page);
  ok((await currentType(page)) === 'slides' && (await doneCount(page)) === NBLOCKS, 'localStorage orqali resume (joriy blok, ✓ belgilar, test natijasi)');
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
  await T2.ctx.close();

  section("Ish stoli · qorong'i rejim · klaviatura");
  const D = await newCtx(br, { colorScheme: 'dark' }, 'dark'), dp = D.page;
  await dp.goto(base + PKG + 'index.html'); await waitReady(dp);
  ok(await dp.evaluate(() => matchMedia('(prefers-color-scheme: dark)').matches && getComputedStyle(document.body).backgroundColor !== 'rgb(244, 245, 247)'), "Qorong'i rejim: prefers-color-scheme ishladi");
  for (const t of ['plan', 'text', 'slides', 'video', 'file', 'quiz']) {
    await clickToc(dp, await blockIndex(dp, t)); await SHOT(dp, 'dark_' + t);
  }
  await dp.click('[data-act="start"]'); await answerQuiz(dp, false); await SHOT(dp, 'dark_quiz_failed', true);
  // klaviatura: Tab bilan skip-havola, landmarklar
  await dp.reload(); await waitReady(dp);
  await dp.keyboard.press('Tab');
  ok(await dp.evaluate(() => document.activeElement.classList.contains('skip')), 'Birinchi Tab — «Asosiy mazmunga o\'tish» havolasi');
  const lm = await dp.evaluate(() => ({ h: !!document.querySelector('header'), n: !!document.querySelector('nav[aria-label]'), m: !!document.querySelector('main#main'), live: !!document.querySelector('[aria-live]'),
    pb: document.querySelector('[role=progressbar]').getAttribute('aria-valuenow'), alt: [...document.querySelectorAll('img')].every(i => i.hasAttribute('alt')), lang: document.documentElement.lang }));
  ok(lm.h && lm.n && lm.m && lm.live && lm.pb != null && lm.alt && lm.lang === 'uz', 'Landmarklar (header/nav/main), aria-live, progressbar, img alt, lang=uz');
  ok(D.errs.length === 0, 'Konsol xatolari yo\'q' + (D.errs.length ? ': ' + D.errs.slice(0, 3).join(' | ') : ''));
  await D.ctx.close();
  const L = await newCtx(br, { viewport: { width: 1366, height: 900 } }, 'light'), lp = L.page;
  await lp.goto(base + PKG + 'index.html'); await waitReady(lp);
  for (const t of ['plan', 'text', 'slides', 'video', 'file', 'quiz']) { await clickToc(lp, await blockIndex(lp, t)); await SHOT(lp, 'desk_' + t); }
  await lp.click('[data-act="start"]'); await SHOT(lp, 'desk_quiz_form', true);
  await lp.emulateMedia({ media: 'print' }); await clickToc(lp, await blockIndex(lp, 'text')); await SHOT(lp, 'print_text', true);
  ok(await lp.evaluate(() => getComputedStyle(document.querySelector('.top')).display === 'none' && getComputedStyle(document.querySelector('.toc')).display === 'none'), 'Chop etish: sarlavha/navigatsiya yashirinadi, faqat matn');
  ok(L.errs.length === 0, 'Konsol xatolari yo\'q');
  await L.ctx.close();
}

(async () => {
  const lmsPort = await listen(lms), lrsPort = await listen(lrs);
  const base = 'http://127.0.0.1:' + lmsPort, lrsBase = 'http://127.0.0.1:' + lrsPort;
  const br = await chromium.launch({ executablePath: process.env.CHROME || undefined });
  try {
    await runScorm(br, base, 'scorm12');
    await runScorm(br, base, 'scorm2004');
    await runModeNone(br, base);
    await runXapi(br, base, lrsBase);
    await runXapiViewAll(br, base, lrsBase);
    await runBadUrls(br, base);
    await runPreview(br, base);
  } catch (e) {
    ok(false, 'Sinov to\'xtadi: ' + (e && e.stack || e).toString().split('\n').slice(0, 3).join(' '));
  } finally {
    await br.close(); lms.close(); lrs.close();
  }
  console.log('\nJamlanma:');
  Object.keys(counts).forEach(k => console.log(`  ${k}: ${counts[k][0]} o'tdi, ${counts[k][1]} xato`));
  console.log('Skrinshotlar: ' + OUT);
  process.exit(fails.length ? 1 : 0);
})();
