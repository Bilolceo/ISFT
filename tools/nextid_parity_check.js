#!/usr/bin/env node
/* NEXTID.LMS (my.isft.uz) bilan simdagi moslik sinovi: bizning xAPI paket Articulate Rise 360 paketi kabi so'rov yuboradimi.
 *
 * Ishga tushirish (odatda tests/test_paket_player.py «7-bo'lim» chaqiradi — paketni app.paket.build_zip bilan yig'ib, ochib beradi):
 *   PW=/path/node_modules/playwright-core CHROME=/path/to/chrome PKG_DIR=/ochilgan/xapi/paket QUIZ='<test bloki JSON>' node tools/nextid_parity_check.js
 *
 * Nima qiladi: paketni bitta portda (A), «NEXTID» sahifasi va soxta LRS'ni boshqa portda (B — boshqa domen, CORS) beradi. NEXTID kabi iframe:
 *   A/scormdriver/indexAPI.html?endpoint=B/uz/articulate&auth=Bearer%20testtok&actor={"name":9424693}
 * Barcha qadamlar ko'riladi, test to'g'ri yechiladi, sahifa yopiladi; keyin qayta ochiladi (resume, cumulative_time). LRS so'rovlari Rise yozuvi
 * (docs/paket.md «Kuzatuv», docs/nextid_xapi_sorov.md) bilan solishtiriladi: X-Experience-API-Version 1.0.2, Bearer, actor o'zgarishsiz
 * ({"objectType":"Agent","name":9424693}), attempted/progressed — PUT statements?statementId=, passed/answered — POST massiv, state hujjatlari
 * suspend_data / bookmark / cumulative_time / language_preference, yopilishda — muqobil sintaksis (POST ?method=…, forma).
 * Natija: "  ✓ …" / "  ✗ …", ma'lumot qatorlari "  » …"; xato bo'lsa chiqish kodi 1.
 */
'use strict';
const http = require('http'), fs = require('fs'), path = require('path');
const { chromium } = require(process.env.PW || 'playwright-core');
const PKG_DIR = process.env.PKG_DIR, QUIZ = JSON.parse(process.env.QUIZ || 'null');
if (!PKG_DIR || !fs.existsSync(path.join(PKG_DIR, 'scormdriver', 'indexAPI.html'))) { console.error('PKG_DIR (ochilgan xAPI paket) kerak'); process.exit(2); }
const ACTOR_IN = '{"name":9424693}', ACTOR_OUT = '{"objectType":"Agent","name":9424693}', TOKEN = 'Bearer testtok';
const VERB = 'http://adlnet.gov/expapi/verbs/', PROG = 'https://w3id.org/xapi/cmi5/result/extensions/progress';
const WEIGHT = 'http://id.tincanapi.com/extension/cmi-interaction-weighting';
const sleep = ms => new Promise(r => setTimeout(r, ms));
const fails = [];
function ok(c, m) { console.log((c ? '  ✓ ' : '  ✗ ') + m); if (!c) fails.push(m); }
const info = m => console.log('  » ' + m);

// ---------------------------------------------------------------- A: paket fayllari
const CT = { html: 'text/html; charset=utf-8', js: 'application/javascript', css: 'text/css', json: 'application/json', png: 'image/png', jpg: 'image/jpeg',
  svg: 'image/svg+xml', woff2: 'font/woff2', mp4: 'video/mp4', vtt: 'text/vtt', pdf: 'application/pdf', mp3: 'audio/mpeg' };
const pkg = http.createServer((req, res) => {
  const rel = decodeURIComponent(new URL(req.url, 'http://x').pathname).replace(/^\/+/, '') || 'index.html';
  const f = path.join(PKG_DIR, rel);
  if (rel.split('/').includes('..') || !fs.existsSync(f) || !fs.statSync(f).isFile()) { res.writeHead(404); res.end(); return; }
  res.writeHead(200, { 'Content-Type': CT[path.extname(f).slice(1)] || 'application/octet-stream' }); res.end(fs.readFileSync(f));
});
// ---------------------------------------------------------------- B: «NEXTID» sahifasi + soxta LRS (/uz/articulate/…)
const LOG = [], STATE = {};
let LAUNCH = '';
const cors = { 'Access-Control-Allow-Origin': '*', 'Access-Control-Allow-Methods': 'GET,PUT,POST,DELETE,OPTIONS',
  'Access-Control-Allow-Headers': 'Authorization,Content-Type,X-Experience-API-Version,If-Match,If-None-Match', 'Access-Control-Expose-Headers': 'ETag,X-Experience-API-Version',
  'X-Experience-API-Version': '1.0.3' };
const lrs = http.createServer((req, res) => {
  let body = ''; req.on('data', c => body += c);
  req.on('end', () => {
    const u = new URL(req.url, 'http://x');
    if (u.pathname === '/host.html' || u.pathname === '/bye.html') {
      res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' });
      res.end(u.pathname === '/bye.html' ? '<!doctype html><title>NEXTID</title><p>chiqildi</p>'
        : `<!doctype html><title>NEXTID</title><style>body{margin:0}iframe{border:0;width:100%;height:100vh}</style><iframe id="f" src="${LAUNCH.replace(/"/g, '&quot;')}" allowfullscreen></iframe>`);
      return;
    }
    if (req.method === 'OPTIONS') { res.writeHead(204, cors); res.end(); return; }
    if (!u.pathname.startsWith('/uz/articulate/')) { res.writeHead(404, cors); res.end(); return; }
    const q = Object.fromEntries(u.searchParams), ct = (req.headers['content-type'] || '').split(';')[0];
    const form = ct === 'application/x-www-form-urlencoded' ? Object.fromEntries(new URLSearchParams(body)) : null;
    const eff = (q.method || req.method).toUpperCase(), P = form ? Object.assign({}, q, form) : q;
    const content = form ? form.content : body;
    const rec = { m: req.method, eff, path: u.pathname.slice('/uz/articulate/'.length), q, form, alt: !!q.method, ct,
      ver: req.headers['x-experience-api-version'] || (form && form['X-Experience-API-Version']), auth: req.headers.authorization || (form && form.Authorization),
      dct: form ? form['Content-Type'] : ct, sid: P.stateId, agent: P.agent, act: P.activityId, stmtId: P.statementId, raw: content };
    try { rec.body = content ? JSON.parse(content) : null; } catch (e) { rec.body = null; }
    LOG.push(rec);
    if (rec.path === 'activities/state') {
      const key = [P.activityId, P.agent, P.stateId].join('|');
      if (eff === 'GET') { if (key in STATE) { res.writeHead(200, Object.assign({ 'Content-Type': 'application/octet-stream' }, cors)); res.end(STATE[key]); } else { res.writeHead(404, cors); res.end(); } return; }
      if (eff === 'PUT' || eff === 'POST') { STATE[key] = content; res.writeHead(204, cors); res.end(); return; }
    }
    if (rec.path === 'statements') {
      if (eff === 'PUT') { res.writeHead(204, cors); res.end(); return; }
      if (eff === 'POST') { const a = Array.isArray(rec.body) ? rec.body : [rec.body]; res.writeHead(200, Object.assign({ 'Content-Type': 'application/json' }, cors)); res.end(JSON.stringify(a.map(s => s && s.id))); return; }
    }
    res.writeHead(400, cors); res.end();
  });
});
const listen = s => new Promise(r => s.listen(0, '127.0.0.1', () => r(s.address().port)));

// ---------------------------------------------------------------- yordamchilar
const stmts = recs => recs.filter(r => r.path === 'statements').flatMap(r => (Array.isArray(r.body) ? r.body : [r.body]).map(s => ({ s, r })));
const verb = s => s && s.verb && s.verb.id.slice(VERB.length);
const short = r => r.path === 'statements' ? `${r.alt ? 'POST?method=' : ''}${r.eff} statements[${stmts([r]).map(x => verb(x.s)).join(',')}]`
  : `${r.alt ? 'POST?method=' : ''}${r.eff} state:${r.sid}`;
async function frameOf(page) {
  for (let i = 0; i < 100; i++) {
    const f = page.frames().find(x => x !== page.mainFrame() && /\/index\.html\?/.test(x.url()));
    if (f) { try { await f.waitForFunction(() => window.ISFTPaket && window.ISFTPaket.ready, null, { timeout: 15000 }); return f; } catch (e) { /* qayta */ } }
    await sleep(100);
  }
  throw new Error('pleyer freymi topilmadi');
}
async function session(br, B, walk) {
  const ctx = await br.newContext({ viewport: { width: 1280, height: 860 } }), page = await ctx.newPage(), errs = [];
  page.on('pageerror', e => errs.push(e.message));
  const n0 = LOG.length;
  await page.goto(B + '/host.html');
  const fr = await frameOf(page);
  const res = await walk(fr);
  await sleep(1200);                                   // state yozuvlari (800 ms kechiktirish)
  const mid = LOG.length;
  await page.goto(B + '/bye.html'); await sleep(1500);   // NEXTID'da boshqa sahifaga o'tish → pagehide (about:blank keepalive'ni uzadi)
  await ctx.close();
  return Object.assign({ all: LOG.slice(n0), live: LOG.slice(n0, mid), exit: LOG.slice(mid), errs, url: fr.url() }, res);
}

(async () => {
  const pA = await listen(pkg), pB = await listen(lrs), A = 'http://127.0.0.1:' + pA, B = 'http://127.0.0.1:' + pB;
  LAUNCH = `${A}/scormdriver/indexAPI.html?endpoint=${B}/uz/articulate&auth=Bearer%20testtok&actor=${ACTOR_IN}`;   // NEXTID kabi (actor kodlanmagan)
  const br = await chromium.launch({ executablePath: process.env.CHROME, headless: true });
  try {
    console.log('== 1-sessiya: ochish → barcha qadamlar → test → yopish');
    const s1 = await session(br, B, async fr => {
      const mode = await fr.evaluate(() => window.ISFTPaket.mode);
      const rise = await fr.evaluate(() => document.documentElement.classList.contains('rise'));
      // rise (NEXTID ko'rinishi): ↓ → har tasma: «davom etish» bosiladi, rasm sahifalari varaqlanadi, blok oxirigacha aylantiriladi (ko'rildi); steps: qadamlar ro'yxati
      const nav = rise
        ? await fr.evaluate(() => [...document.querySelectorAll('.r-band[data-i]')].map(e => ({ i: +e.dataset.i, t: e.querySelector('.r-continue') ? 'section' : (e.className.match(/\bt-(\w+)/) || [])[1] })))
        : await fr.evaluate(() => [...document.querySelectorAll('.nav-i')].map(e => ({ i: +e.dataset.i, t: e.dataset.type })));
      if (rise) await fr.click('.r-go', { force: true });
      const visit = i => rise
        ? fr.evaluate(i => { const b = document.querySelector('.r-band[data-i="' + i + '"]'), g = b.querySelector('.r-continue');
            if (g && !b.classList.contains('open')) { g.click(); return; }
            const nx = b.querySelector('.nav-a.r'); for (let k = 0; nx && !nx.disabled && k < 200; k++) nx.click();   // rasm sahifalari — hammasi varaqlanadi
            b.scrollIntoView({ block: 'end' }); window.dispatchEvent(new Event('scroll')); }, i)
        : fr.evaluate(i => document.querySelector('.nav-i[data-i="' + i + '"]').click(), i);
      for (const n of nav) { if (n.t === 'quiz') continue; await visit(n.i); await sleep(150); }
      await sleep(1300);
      const beforeQuiz = LOG.length;
      const qn = nav.find(n => n.t === 'quiz');
      if (qn && QUIZ) {
        if (rise) await fr.evaluate(i => { document.querySelector('.r-band[data-i="' + i + '"]').scrollIntoView({ block: 'start' }); window.dispatchEvent(new Event('scroll')); }, qn.i);
        else await fr.evaluate(i => document.querySelector('.nav-i[data-i="' + i + '"]').click(), qn.i);
        await sleep(200);
        await fr.click('[data-act="start"]'); await fr.waitForSelector('form.qform');
        for (const q of QUIZ.questions) {
          const sel = `fieldset[data-qid="${q.id}"]`;
          if (q.type === 'fill') await fr.fill(sel + ' input', String(q.answers[0]));
          else for (const i of q.correct) await fr.check(`${sel} input[value="${i}"]`);
        }
        await fr.click('form.qform [data-act="submit"]'); await sleep(600);
      }
      return { mode, nav, beforeQuiz, step: await fr.evaluate(() => window.ISFTPaket.debug.steps()[window.ISFTPaket.debug.step()].key) };
    });
    const L1 = s1.all.filter(r => r.m !== 'OPTIONS'), S1 = stmts(L1), actId = (S1[0] && S1[0].s.object.id) || '';
    info('1-sessiya: ' + L1.map(short).join(' → '));
    ok(/\/index\.html\?endpoint=/.test(s1.url) && new URL(s1.url).searchParams.get('auth') === TOKEN && new URL(s1.url).searchParams.get('actor') === ACTOR_IN,
      'scormdriver/indexAPI.html → ../index.html, so\'rov qatori (endpoint, auth, actor) saqlandi');
    ok(s1.mode === 'xapi', `NEXTID launch'i (faqat nomli raqamli actor) → xAPI rejimi (${s1.mode})`);
    ok(L1.every(r => r.ver === '1.0.2'), 'Hamma so\'rovda X-Experience-API-Version: 1.0.2 (sarlavha yoki forma maydoni)');
    ok(L1.every(r => r.auth === TOKEN), 'Authorization — launch\'dagi «Bearer …» aynan (sarlavha yoki forma maydoni)');
    ok(S1.length > 0 && S1.every(x => JSON.stringify(x.s.actor) === ACTOR_OUT), `actor — ${ACTOR_OUT} (raqamli nom saqlandi, mbox/account yo'q)`);
    const st1 = L1.filter(r => r.path === 'activities/state');
    ok(st1.every(r => r.agent === ACTOR_OUT && r.act === actId), 'State so\'rovlari: agent = actor JSON, activityId = kurs faoliyati');
    // ochilish ketma-ketligi
    const first = L1.slice(0, 5).map(short), firstStmt = L1.find(r => r.path === 'statements');
    ok(['GET state:language_preference', 'GET state:cumulative_time', 'GET state:suspend_data', 'GET state:bookmark'].every(x => first.includes(x))
       && firstStmt && firstStmt.eff === 'PUT' && verb(firstStmt.body) === 'attempted'
       && L1.indexOf(firstStmt) > L1.findIndex(r => r.sid === 'cumulative_time'),
      'Ochilish: GET language_preference, cumulative_time → PUT attempted → GET suspend_data, bookmark (' + first.join(', ') + ')');
    const att = firstStmt && firstStmt.body, d = att && att.object && att.object.definition;
    ok(att && firstStmt.stmtId === att.id && !att.result && !att.context && att.object.objectType === 'Activity' && /^https?:\/\//.test(att.object.id)
       && d.type === 'http://adlnet.gov/expapi/activities/course' && typeof d.name.en === 'string' && d.name.en && d.description.en === '',
      'attempted: PUT ?statementId=<id>, obyekt — kurs (type course, name.en, description.en), result/context yo\'q');
    // progress
    const prog = S1.filter(x => verb(x.s) === 'progressed'), pv = prog.map(x => x.s.result.extensions[PROG]);
    ok(prog.length > 0 && prog.every(x => x.r.eff === 'PUT' && !x.r.alt && x.r.stmtId === x.s.id && x.s.object.id === actId)
       && pv.every((v, i) => Number.isInteger(v) && v > 0 && v <= 100 && (i === 0 || v > pv[i - 1])) && pv[pv.length - 1] === 100,
      `progressed: har biri PUT, cmi5 progress butun son, o'sib boradi, oxiri 100 (${pv.join(',')})`);
    // yakunlanish
    const pas = S1.filter(x => verb(x.s) === 'passed' && x.s.object.id === actId), p0 = pas[0];
    ok(p0 && p0.r.eff === 'POST' && Array.isArray(p0.r.body) && p0.s.result.success === true && p0.s.result.completion === true && !p0.s.result.score
       && /^PT(\d+H)?(\d+M)?\d+(\.\d+)?S$/.test(p0.s.result.duration) && !p0.s.context,
      `passed (kurs): POST massiv, {success:true, duration:${p0 && p0.s.result.duration}, completion:true} — Rise «passed/incomplete» kabi`);
    ok(p0 && L1.indexOf(prog[prog.length - 1].r) < L1.indexOf(p0.r), 'progressed 100 → keyin passed');
    const sus = st1.filter(r => r.eff === 'PUT' && r.sid === 'suspend_data'), bm = st1.filter(r => r.eff === 'PUT' && r.sid === 'bookmark');
    ok(sus.length > 0 && sus.every(r => r.dct === 'application/octet-stream') && bm.length > 0 && bm[bm.length - 1].raw === s1.step,
      `State: PUT suspend_data (octet-stream, ${sus.length} marta), bookmark = joriy qadam («${bm.length ? bm[bm.length - 1].raw : '-'}»)`);
    // test
    const ans = S1.filter(x => verb(x.s) === 'answered');
    ok(!QUIZ || (ans.length === QUIZ.questions.length && ans.every(x => x.r.eff === 'POST' && Array.isArray(x.r.body) && x.s.context.contextActivities.parent[0].id === actId
       && typeof x.s.result.success === 'boolean' && typeof x.s.result.response === 'string' && x.s.result.extensions[WEIGHT] === 1 && x.s.object.id.startsWith(actId + '/'))),
      `answered: POST massiv, ota — kurs, result {success, response, cmi-interaction-weighting:1} (${ans.length} ta)`);
    ok(!QUIZ || pas.some(x => x.s.result.score && x.s.result.score.raw === 100 && x.s.result.score.scaled === 1 && x.s.result.score.min === 0 && x.s.result.score.max === 100),
      'Test hal qildi → kurs passed ball bilan (score scaled/raw/min/max)');
    const extra = S1.filter(x => x.s.object.id !== actId && verb(x.s) !== 'answered');
    info('Rise\'da yo\'q qo\'shimcha (bizning LRS analitikasi uchun): ' + (extra.map(x => verb(x.s) + ' ' + x.s.object.id.slice(actId.length)).join(', ') || 'yo\'q'));
    ok(!S1.some(x => /^(initialized|terminated|suspended|resumed|completed)$/.test(verb(x.s))) && !S1.some(x => verb(x.s) === 'experienced'),
      "Rise'da yo'q fe'llar yuborilmadi (initialized/terminated/suspended/resumed/completed; bitta darsli paketda blok experienced yo'q)");
    // yopilish
    const ex = s1.exit, exS = stmts(ex).filter(x => verb(x.s) === 'attempted'), ct1 = ex.find(r => r.sid === 'cumulative_time');
    info('Yopilish: ' + ex.map(short).join(' → '));
    ok(exS.length === 1 && exS[0].r.alt && exS[0].r.m === 'POST' && exS[0].r.eff === 'POST' && exS[0].r.ct === 'application/x-www-form-urlencoded'
       && exS[0].r.form['Content-Type'] === 'application/json' && Array.isArray(exS[0].r.body) && /^PT/.test(exS[0].s.result.duration) && Object.keys(exS[0].s.result).length === 1,
      `Yopilish: POST statements?method=POST (forma), [attempted {duration:${exS[0] && exS[0].s.result.duration}}]`);
    ok(ct1 && ct1.alt && ct1.m === 'POST' && ct1.eff === 'PUT' && ct1.ct === 'application/x-www-form-urlencoded' && ct1.form['Content-Type'] === 'application/octet-stream'
       && ct1.agent === ACTOR_OUT && ct1.act === actId && /^\d+$/.test(ct1.raw) && +ct1.raw > 1000
       && ['stateId', 'activityId', 'agent', 'Authorization', 'X-Experience-API-Version', 'Content-Type', 'content'].every(k => k in ct1.form),
      `Yopilish: POST activities/state?method=PUT, cumulative_time = ${ct1 && ct1.raw} ms (forma maydonlari Rise tartibida)`);
    ok(!s1.errs.length, 'Pleyerda JS xatosi yo\'q' + (s1.errs.length ? ': ' + s1.errs.slice(0, 2).join(' | ') : ''));

    console.log('== 2-sessiya: qayta ochish (resume, cumulative_time)');
    const s2 = await session(br, B, async fr => ({ step: await fr.evaluate(() => window.ISFTPaket.debug.steps()[window.ISFTPaket.debug.step()].key) }));
    const L2 = s2.all.filter(r => r.m !== 'OPTIONS'), S2 = stmts(L2);
    info('2-sessiya: ' + L2.map(short).join(' → '));
    ok(!L2.some(r => r.sid === 'isft-state') && L2.some(r => r.sid === 'suspend_data' && r.eff === 'GET'), 'suspend_data bor — eski isft-state so\'ralmaydi');
    ok(s2.step === s1.step, `Resume: bookmark bo'yicha oxirgi qadam («${s2.step}»)`);
    ok(S2.filter(x => x.s.object.id === actId).map(x => verb(x.s)).join() === 'attempted,attempted', 'Qayta ochishda progressed/passed takrorlanmaydi — faqat attempted (ochish va yopish)');
    const ct2 = s2.exit.find(r => r.sid === 'cumulative_time');
    ok(ct1 && ct2 && +ct2.raw > +ct1.raw, `cumulative_time sessiyalar bo'yicha jamlanadi (${ct1 && ct1.raw} → ${ct2 && ct2.raw} ms)`);
  } catch (e) {
    ok(false, 'Istisno: ' + (e && e.stack || e));
  } finally {
    await br.close(); pkg.close(); lrs.close();
  }
  console.log(fails.length ? `XATO: ${fails.length} ta` : 'Hammasi o\'tdi');
  process.exit(fails.length ? 1 : 0);
})();
