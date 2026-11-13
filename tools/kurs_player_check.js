#!/usr/bin/env node
/* ISFT kurs pleyeri («Kurs muharriri», app/kurs_player) — brauzerdagi muvofiqlik sinovi.
 *
 * Ishga tushirish:
 *   PW=/path/to/node_modules/playwright-core CHROME=/path/to/chrome OUT=/tmp/kurs node tools/kurs_player_check.js <katalog>
 *   <katalog> ichida eksport qilingan va ochilgan kurs zip'lari: scorm12/, scorm2004/, xapi/ (har biri — index.html, content.js, lms.js …).
 *
 * Nima qiladi: paketlarni kichik Node serverida pastki yo'ldan (/kurs/<tur>/) beradi; ota «mock LMS» sahifasi window.API / window.API_1484_11
 * ni yozib boradi (mock — tools/paket_player_check.js dagi lmsRuntime(), shu fayldan o'qiladi: bitta mock, ikki pleyer), pleyerni iframe ichida
 * ochadi va UI orqali boshqaradi; xAPI uchun alohida portda mock LRS (CORS bilan). Bloklar kontentdan turi bo'yicha topiladi (namuna kurs).
 * Natija qatorlari: "  ✓ ..." / "  ✗ ...", xato bo'lsa chiqish kodi 1. Skrinshotlar: $OUT (player-desktop.png, player-phone.png, player-quiz.png).
 */
'use strict';
const http = require('http'), fs = require('fs'), path = require('path');
const { chromium } = require(process.env.PW || 'playwright-core');
const ROOT = path.resolve(__dirname, '..');
const DIR = path.resolve(process.argv[2] || '');
const OUT = process.env.OUT || path.join(require('os').tmpdir(), 'isft_kurs_player');
fs.mkdirSync(OUT, { recursive: true });
if (!fs.existsSync(path.join(DIR, 'scorm12', 'content.json'))) { console.error('Foydalanish: node tools/kurs_player_check.js <katalog: scorm12/ scorm2004/ xapi/>'); process.exit(2); }
const CONTENT = JSON.parse(fs.readFileSync(path.join(DIR, 'scorm12', 'content.json'), 'utf8'));
const LESSONS = CONTENT.lessons, VIEW = LESSONS.filter(l => l.type === 'blocks'), QUIZ = LESSONS.find(l => l.type === 'quiz');
const ALLB = VIEW.flatMap(l => l.blocks.map(b => Object.assign({ lesson: l.id }, b)));
const sleep = ms => new Promise(r => setTimeout(r, ms));
let sect = '';
const fails = [], counts = {};
function ok(c, m) { console.log((c ? '  ✓ ' : '  ✗ ') + m); counts[sect] = counts[sect] || [0, 0]; counts[sect][c ? 0 : 1]++; if (!c) fails.push(sect + ': ' + m); }
function section(s) { sect = s; console.log('== ' + s); }

// ---------------------------------------------------------------- mock LMS (paket sinovidagi bilan bir xil)
const SRC = fs.readFileSync(path.join(ROOT, 'tools', 'paket_player_check.js'), 'utf8');
const RUNTIME = SRC.slice(SRC.indexOf('function lmsRuntime()'), SRC.indexOf('const LMS_HTML')).trim().replace(/e\.data\.source === 'isft-paket'/, "/^isft-(paket|kurs)$/.test(e.data.source)");
const LMS_HTML = `<!doctype html><html><head><meta charset="utf-8"><title>Mock LMS</title>
<style>body{margin:0;font:14px system-ui}header{background:#333;color:#fff;padding:6px 12px}iframe{border:0;width:100%;height:calc(100vh - 32px);display:block}</style></head>
<body><header>Mock LMS</header><iframe id="sco" name="sco" title="SCO"></iframe><script>(${RUNTIME})();</script></body></html>`;
const MIME = { '.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8', '.css': 'text/css', '.json': 'application/json', '.png': 'image/png', '.jpg': 'image/jpeg',
  '.mp4': 'video/mp4', '.webm': 'video/webm', '.vtt': 'text/vtt; charset=utf-8', '.mp3': 'audio/mpeg', '.pdf': 'application/pdf', '.woff2': 'font/woff2' };
// ISFT Core ko'rish oynasidagi qat'iy CSP (app/paket.py PREVIEW_CSP) — /csp/<tur>/ yo'lida shu sarlavha bilan beriladi
const PY = fs.readFileSync(path.join(ROOT, 'app', 'paket.py'), 'utf8'), CSPM = /PREVIEW_CSP = \(([\s\S]*?)\)\n/.exec(PY);
const CSP = CSPM ? (CSPM[1].match(/"([^"]*)"/g) || []).map(x => x.slice(1, -1)).join('') : '';
const srv = http.createServer((req, res) => {
  const u0 = new URL(req.url, 'http://x'), csp = /^\/csp\//.test(u0.pathname);
  const u = csp ? new URL(req.url.replace(/^\/csp\//, '/kurs/'), 'http://x') : u0;
  if (u.pathname === '/lms.html') { res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' }); res.end(LMS_HTML); return; }
  const m = /^\/kurs\/(scorm12|scorm2004|xapi)\/(.*)$/.exec(u.pathname);
  if (!m || m[2].includes('..')) { res.writeHead(404); res.end('404'); return; }
  fs.readFile(path.join(DIR, m[1], decodeURIComponent(m[2]) || 'index.html'), (e, buf) => {
    if (e) { res.writeHead(404); res.end('404'); return; }
    res.writeHead(200, Object.assign({ 'Content-Type': MIME[path.extname(m[2])] || 'application/octet-stream', 'Cache-Control': 'no-store' }, csp ? { 'Content-Security-Policy': CSP } : {})); res.end(buf);
  });
});
const LRS = { statements: [], state: {} };
const cors = { 'Access-Control-Allow-Origin': '*', 'Access-Control-Allow-Headers': 'Authorization, Content-Type, X-Experience-API-Version', 'Access-Control-Allow-Methods': 'GET, PUT, POST, OPTIONS', 'X-Experience-API-Version': '1.0.3' };
const lrs = http.createServer((req, res) => {
  const u = new URL(req.url, 'http://x'); let body = ''; req.on('data', c => body += c);
  req.on('end', () => {
    if (req.method === 'OPTIONS') { res.writeHead(204, cors); res.end(); return; }
    if (u.pathname === '/xapi/statements' && req.method === 'POST') {
      let a; try { a = JSON.parse(body); } catch (e) { res.writeHead(400, cors); res.end(); return; }
      (Array.isArray(a) ? a : [a]).forEach(s => LRS.statements.push(s));
      res.writeHead(200, Object.assign({ 'Content-Type': 'application/json' }, cors)); res.end('[]'); return;
    }
    if (u.pathname === '/xapi/activities/state') {
      const key = u.searchParams.get('activityId') + '|' + u.searchParams.get('stateId');
      if (req.method === 'GET') { if (key in LRS.state) { res.writeHead(200, cors); res.end(LRS.state[key]); } else { res.writeHead(404, cors); res.end(); } return; }
      if (req.method === 'PUT') { LRS.state[key] = body; res.writeHead(204, cors); res.end(); return; }
    }
    res.writeHead(404, cors); res.end();
  });
});
const listen = s => new Promise(r => s.listen(0, '127.0.0.1', () => r(s.address().port)));

// ---------------------------------------------------------------- yordamchilar
async function newCtx(br, opts) {
  const ctx = await br.newContext(Object.assign({ viewport: { width: 1280, height: 860 } }, opts || {}));
  const errs = [], foreign = [];
  ctx.on('response', r => { if (r.status() >= 400 && !/\/xapi\/activities\/state\?/.test(r.url())) errs.push('HTTP ' + r.status() + ' ' + r.url().slice(0, 100)); });
  await ctx.route(/youtube-nocookie\.com|youtube\.com/, r => r.fulfill({ status: 200, contentType: 'text/html', body: '<!doctype html><title>yt</title><body>YouTube</body>' }));
  ctx.on('request', rq => { const u = rq.url(); if (!/^(http:\/\/127\.0\.0\.1:|about:|data:|blob:)/.test(u) && !/youtube(-nocookie)?\.com/.test(u)) foreign.push(u); });
  const page = await ctx.newPage();
  page.on('pageerror', e => errs.push('pageerror: ' + e.message));
  // LRS State API — birinchi o'qishda 404 (xAPI qoidasi: holat hali yo'q) normal; boshqa 4xx/5xx javoblar «bad» ro'yxatida tekshiriladi
  page.on('console', m => { if (m.type() === 'error' && !/Failed to load resource: the server responded with a status of 404/.test(m.text())) errs.push('console: ' + m.text()); });
  return { ctx, page, errs, foreign };
}
const frameOf = page => page.frame({ name: 'sco' });
async function ready(fr) { await fr.waitForFunction(() => window.ISFTKurs && window.ISFTKurs.ready, null, { timeout: 15000 }); }
async function launch(page, kind, url) { await page.evaluate(([k, u]) => window.launch(k, u), [kind, url]); await sleep(300); const fr = frameOf(page); await ready(fr); return fr; }
const lessonIndex = id => LESSONS.findIndex(l => l.id === id);
async function openLesson(fr, i) { await fr.click(`.les-b[data-lesson="${LESSONS[i].id}"]`); await sleep(150); }
async function h1(fr) { return fr.$eval('main h1', e => e.textContent.trim()); }
async function hidden(fr, bid) { return fr.$eval('#b-' + bid, e => !!e.closest('[hidden]')); }
const correctIdx = q => q.answers.map((a, i) => a.correct ? i : -1).filter(i => i >= 0);

// bitta interaktiv blokni UI orqali bajarish
async function complete(fr, b, wrongFirst) {
  const S = '#b-' + b.id;
  if (b.type === 'accordion') { for (const x of await fr.$$(S + ' .acc-b[aria-expanded="false"]')) await x.click(); }
  else if (b.type === 'tabs') { for (const x of await fr.$$(S + ' [role=tab]')) await x.click(); }
  else if (b.type === 'labeled_graphic') { for (const x of await fr.$$(S + ' .lg-m')) await x.click(); }
  else if (b.type === 'flashcards') {
    if (b.style === 'stack' && b.cards.length > 1) for (let k = 0; k < b.cards.length; k++) { await fr.click(S + ' .fc'); await fr.click(S + ' [aria-label="Keyingi kartochka"]'); }
    else for (const x of await fr.$$(S + ' .fc')) await x.click();
  }
  else if (b.type === 'process') { for (let k = 1; k < b.items.length; k++) await fr.click(S + ' .proc-n .btn.primary'); }
  else if (b.type === 'sorting') {
    for (const it of b.items) {
      await fr.evaluate(([s, t]) => [...document.querySelectorAll(s + ' .sort-pool .s-card')].find(x => x.textContent.trim() === t).click(), [S, it.text]);
      await fr.evaluate(([s, c]) => document.querySelectorAll(s + ' .s-zone .btn')[c].click(), [S, it.cat]);
    }
    await fr.click(S + ' .acts .btn.primary');
  }
  else if (b.type === 'matching') {
    for (let k = 0; k < b.pairs.length; k++) await fr.selectOption(`#${b.id}-m${k}`, { label: b.pairs[k].right });
    await fr.click(S + ' .acts .btn.primary');
  }
  else if (b.type === 'knowledge') await answerQ(fr, S, b, !wrongFirst);
}
async function answerQ(fr, scope, q, right) {
  if (q.kind === 'fill') await fr.fill(scope + ' input.fill', right ? q.accept[0] : 'notogri javob');
  else {
    const want = right ? correctIdx(q) : [q.answers.findIndex(a => !a.correct)];
    for (const i of want) await fr.check(`${scope} .opt[data-ai="${i}"] input`);
  }
  await fr.click(scope + ' .acts .btn.primary');
  await sleep(60);
}
// darsni oxirigacha: har «Davom etish» oldidan interaktiv bloklar bajariladi, keyin dars oxiri ko'rinadi
async function finishLesson(fr, l) {
  for (const b of l.blocks) {
    if (await hidden(fr, b.id)) {
      const g = l.blocks.slice(0, l.blocks.indexOf(b)).reverse().find(x => x.type === 'continue');
      if (g) await fr.click(`[data-gate="${g.id}"]`);
    }
    if (b.type !== 'continue' && ['accordion', 'tabs', 'flashcards', 'process', 'sorting', 'matching', 'knowledge', 'labeled_graphic'].includes(b.type)) {
      const st = await fr.evaluate(id => !!window.ISFTKurs.state().i[id], b.id);
      if (!st) await complete(fr, b);
    }
  }
  await fr.$eval('.les-end', e => e.scrollIntoView());
  await fr.waitForFunction(id => !!window.ISFTKurs.state().v[id], l.id, { timeout: 5000 }).catch(() => {});
}
async function takeQuiz(fr, right, shot) {
  await fr.click('.qz-start .btn.primary');
  for (let n = 0; n < 200; n++) {
    await sleep(60);
    if (await fr.$('.qz-res')) break;
    const leg = await fr.$eval('.qz legend', e => e.textContent.trim());
    const q = QUIZ.questions.find(x => x.question === leg);
    await answerQ(fr, '.qz', q, right);
    if (shot && n === 0) await shot();
    if (await fr.$('.qz .acts .btn.primary')) await fr.click('.qz .acts .btn.primary');
  }
  return fr.evaluate(() => ({ pct: document.querySelector('.qz-res .ring span').textContent, pass: document.querySelector('.qz-res').classList.contains('pass') }));
}

// ---------------------------------------------------------------- sinovlar
async function runScorm12(br, base) {
  section('SCORM 1.2: muqova, navigatsiya, «Davom etish», bloklar, test');
  const { ctx, page, errs, foreign } = await newCtx(br);
  await page.goto(base + '/lms.html');
  const fr = await launch(page, 'scorm12', base + '/kurs/scorm12/index.html');
  ok(await h1(fr) === CONTENT.title && await fr.$('#startBtn'), 'Muqova: kurs nomi va «Kursni boshlash» tugmasi');
  ok(await fr.$eval('.cover', e => !!e.querySelector('img[alt]')) || !CONTENT.cover, 'Muqova rasmi alt matn bilan');
  // klaviatura: Tab bilan boshlash tugmasigacha, fokus ko'rinadi
  await fr.focus('body').catch(() => {});
  let reached = false;
  for (let k = 0; k < 25 && !reached; k++) { await page.keyboard.press('Tab'); reached = await fr.evaluate(() => document.activeElement && document.activeElement.id === 'startBtn'); }
  const outline = reached ? await fr.evaluate(() => { const e = document.activeElement; return e.matches(':focus-visible') && getComputedStyle(e).outlineStyle !== 'none'; }) : false;
  ok(reached && outline, 'Klaviatura: Tab bilan «Kursni boshlash» tugmasiga yetiladi, fokus halqasi ko\'rinadi');
  await fr.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({ path: path.join(OUT, 'player-desktop.png') });
  await fr.click('#startBtn'); await sleep(150);
  ok(await h1(fr) === LESSONS[0].title, `«Boshlash» → 1-dars (${LESSONS[0].title})`);
  ok((await fr.$$('.les-b')).length === LESSONS.length, `Yon menyu: ${LESSONS.length} ta dars`);
  // «Davom etish»: undan keyingi bloklar yashirin; require=interactions — yuqoridagilar bajarilguncha tugma faol emas
  const gl = VIEW.find(l => l.blocks.some(b => b.type === 'continue'));
  if (gl) {
    await openLesson(fr, lessonIndex(gl.id));
    const gi = gl.blocks.findIndex(b => b.type === 'continue'), g = gl.blocks[gi], after = gl.blocks[gi + 1];
    ok(after ? await hidden(fr, after.id) : true, '«Davom etish» dan keyingi bloklar yashirin');
    const inter = gl.blocks.slice(0, gi).filter(b => ['accordion', 'tabs', 'flashcards', 'process', 'sorting', 'matching', 'knowledge', 'labeled_graphic'].includes(b.type));
    if (g.require === 'interactions' && inter.length) {
      ok(await fr.$eval(`[data-gate="${g.id}"]`, e => e.disabled) && await fr.$eval(`#b-${g.id} .gate-hint`, e => !e.hidden), 'require=interactions: tugma faol emas, izoh ko\'rinadi');
      for (const b of inter) await complete(fr, b);
      ok(!(await fr.$eval(`[data-gate="${g.id}"]`, e => e.disabled)), `Yuqoridagi interaktiv bloklar (${inter.map(b => b.type).join(', ')}) bajarilgach tugma faol`);
    }
    await fr.click(`[data-gate="${g.id}"]`); await sleep(150);
    ok(after ? !(await hidden(fr, after.id)) : true, '«Davom etish» bosilgach keyingi qism ochildi');
  }
  // bilimni tekshirish: noto'g'ri → izoh, qayta urinish → to'g'ri
  const kb = ALLB.find(b => b.type === 'knowledge' && b.kind === 'single');
  if (kb) {
    await openLesson(fr, lessonIndex(kb.lesson));
    if (await hidden(fr, kb.id)) await finishLesson(fr, LESSONS[lessonIndex(kb.lesson)]);
    if (await fr.$(`#b-${kb.id} .fbx.ok`)) { await fr.click(`#b-${kb.id} .fbx .btn`); }
    await answerQ(fr, '#b-' + kb.id, kb, false);
    const bad = await fr.$(`#b-${kb.id} .fbx.bad`), afb = await fr.$(`#b-${kb.id} .afb`);
    ok(!!bad && (!kb.answers.some(a => !a.correct && a.feedback) || !!afb), "Bilimni tekshirish: noto'g'ri javob — «Noto'g'ri» va variant izohi");
    await fr.click(`#b-${kb.id} .fbx .btn`);
    await answerQ(fr, '#b-' + kb.id, kb, true);
    ok(!!(await fr.$(`#b-${kb.id} .fbx.ok`)) && !!(await fr.$(`#b-${kb.id} .opt.right`)), "Qayta urinish → to'g'ri javob, to'g'ri variant belgilangan");
  }
  // kartochka, saralash, moslashtirish
  const fb = ALLB.find(b => b.type === 'flashcards'), sb = ALLB.find(b => b.type === 'sorting'), mb = ALLB.find(b => b.type === 'matching');
  for (const b of [fb, sb, mb].filter(Boolean)) {
    const li = lessonIndex(b.lesson);
    await openLesson(fr, li);
    if (await hidden(fr, b.id)) { const l = LESSONS[li]; const g = l.blocks.slice(0, l.blocks.findIndex(x => x.id === b.id)).reverse().find(x => x.type === 'continue'); if (g) { for (const x of l.blocks.slice(0, l.blocks.indexOf(g))) if (['accordion', 'tabs', 'knowledge', 'flashcards', 'process', 'labeled_graphic'].includes(x.type)) await complete(fr, x); await fr.click(`[data-gate="${g.id}"]`); } }
    await complete(fr, b);
    const okk = b.type === 'flashcards' ? await fr.$eval(`#b-${b.id} .fc`, e => e.getAttribute('aria-pressed') === 'true') : !!(await fr.$(`#b-${b.id} .fb.ok`));
    ok(okk && await fr.evaluate(id => !!window.ISFTKurs.state().i[id], b.id), `${b.type}: bajarildi (${b.type === 'flashcards' ? 'kartochka aylandi' : 'hammasi to\'g\'ri'})`);
  }
  // hamma darslar oxirigacha
  for (const l of VIEW) { await openLesson(fr, lessonIndex(l.id)); await finishLesson(fr, l); }
  const st = await fr.evaluate(() => window.ISFTKurs.state().v);
  ok(VIEW.every(l => st[l.id]), `Barcha ${VIEW.length} ta dars yakunlandi (dars oxiri ko'rinishi bilan)`);
  ok((await fr.$$('.les-b .st.ok')).length >= VIEW.length, 'Yon menyuda yakunlangan darslar belgisi');
  if (QUIZ) {
    await openLesson(fr, lessonIndex(QUIZ.id));
    const r = await takeQuiz(fr, true, () => page.screenshot({ path: path.join(OUT, 'player-quiz.png') }));
    ok(r.pass && r.pct === '100%', `Test: hamma javob to'g'ri → ${r.pct}, topshirildi`);
    const v = await page.evaluate(() => { const s = window.LMS.sessions[window.LMS.sessions.length - 1]; return { st: s.values['cmi.core.lesson_status'], raw: s.values['cmi.core.score.raw'], n: s.inter.length, errs: s.errors }; });
    ok(v.st === 'passed' && +v.raw === 100, `LMS: lesson_status=${v.st}, score.raw=${v.raw}`);
    ok(v.n >= QUIZ.questions.length && !v.errs.length, `LMS interactions: ${v.n} ta, API xatolari: ${v.errs.length ? v.errs.slice(0, 3).join('; ') : 'yo\'q'}`);
  }
  // qidiruv
  const target = ALLB.filter(b => b.type === 'timeline' || b.type === 'process' || b.type === 'heading_paragraph').pop();
  if (target) {
    const word = (target.items ? target.items[target.items.length - 1].title : target.heading).split(/\s+/).sort((a, b) => b.length - a.length)[0];
    await openLesson(fr, 0);
    await fr.fill('.search', word); await sleep(150);
    const n = (await fr.$$('.res')).length;
    await fr.click('.res:not(:first-child) >> nth=0').catch(async () => { await fr.click('.res'); });
    await sleep(200);
    ok(n > 0 && await h1(fr) === LESSONS[lessonIndex(target.lesson)].title, `Qidiruv «${word}»: ${n} ta natija, bosilganda kerakli dars ochildi`);
  }
  ok(!errs.length, 'Konsol xatosiz' + (errs.length ? ': ' + errs.slice(0, 3).join(' | ') : ''));
  ok(!foreign.length, 'Tashqi so\'rov yo\'q' + (foreign.length ? ': ' + foreign.slice(0, 3).join(', ') : ''));
  await ctx.close();
}

async function runScorm2004(br, base) {
  section('SCORM 2004: noto\'g\'ri → topshirilmadi, qayta urinish → topshirildi');
  if (!QUIZ) { ok(true, 'Kursda test yo\'q — o\'tkazib yuborildi'); return; }
  const { ctx, page, errs } = await newCtx(br);
  await page.goto(base + '/lms.html');
  const fr = await launch(page, 'scorm2004', base + '/kurs/scorm2004/index.html');
  await fr.click('#startBtn');
  await openLesson(fr, lessonIndex(QUIZ.id));
  let r = await takeQuiz(fr, false);
  const retry = await fr.$('.qz-res .btn.primary');
  ok(!r.pass && !!retry, `Noto'g'ri javoblar → ${r.pct}, «Test topshirilmadi», «Qayta urinish» bor`);
  let v = await page.evaluate(() => window.LMS.sessions[0].values['cmi.success_status']);
  ok(v === 'failed', `LMS: success_status=${v}`);
  await retry.click(); await sleep(100);
  for (let n = 0; n < 200; n++) {   // ikkinchi urinish (boshlash ekranisiz)
    await sleep(60);
    if (await fr.$('.qz-res')) break;
    const leg = await fr.$eval('.qz legend', e => e.textContent.trim());
    await answerQ(fr, '.qz', QUIZ.questions.find(x => x.question === leg), true);
    if (await fr.$('.qz .acts .btn.primary')) await fr.click('.qz .acts .btn.primary');
  }
  r = await fr.evaluate(() => ({ pass: document.querySelector('.qz-res').classList.contains('pass'), retry: !!document.querySelector('.qz-res .btn.primary') }));
  v = await page.evaluate(() => { const s = window.LMS.sessions[0]; return { ss: s.values['cmi.success_status'], sc: s.values['cmi.score.scaled'], errs: s.errors }; });
  ok(r.pass && !r.retry && v.ss === 'passed' && +v.sc === 1, `Qayta urinish: topshirildi (success_status=${v.ss}, scaled=${v.sc}), keyin qayta urinish yo'q`);
  ok(!v.errs.length, 'SCORM 2004 API xatosiz' + (v.errs.length ? ': ' + v.errs.slice(0, 3).join('; ') : ''));
  ok(!errs.length, 'Konsol xatosiz' + (errs.length ? ': ' + errs.slice(0, 3).join(' | ') : ''));
  await ctx.close();
}

async function runXapi(br, base, lrsBase) {
  section('xAPI: darslar va savollar faoliyatlari, passed / completed');
  const { ctx, page, errs } = await newCtx(br);
  await page.goto(base + '/lms.html');
  const act = CONTENT.tracking.activity_id;
  const q = new URLSearchParams({ endpoint: lrsBase + '/xapi/', auth: 'Basic dGVzdDp0ZXN0', actor: JSON.stringify({ name: 'Ali Valiyev', mbox: 'mailto:ali@isft.uz' }),
    registration: '6f1c2c3e-1b2a-4c5d-8e9f-0a1b2c3d4e5f', activity_id: act });
  const fr = await launch(page, 'xapi', base + '/kurs/xapi/index.html?' + q);
  await fr.click('#startBtn');
  for (const l of VIEW) { await openLesson(fr, lessonIndex(l.id)); await finishLesson(fr, l); }
  if (QUIZ) { await openLesson(fr, lessonIndex(QUIZ.id)); await takeQuiz(fr, true); }
  await sleep(2500);
  const S = LRS.statements, verb = s => s.verb.id.split('/').pop();
  const exp = S.filter(s => verb(s) === 'experienced').map(s => s.object.id);
  ok(VIEW.every(l => exp.includes(act + '/lesson/' + l.id)), `experienced — har dars uchun «${act}/lesson/<uid>»`);
  ok(VIEW.every(l => S.some(s => verb(s) === 'completed' && s.object.id === act + '/lesson/' + l.id)), 'Dars yakunlanishi — completed (…/lesson/<uid>)');
  const ans = S.filter(s => verb(s) === 'answered');
  ok(ans.length >= (QUIZ ? QUIZ.questions.length : 1) && ans.every(s => s.object.id.startsWith(act + '/lesson/') && /\/q\//.test(s.object.id)), `answered: ${ans.length} ta, id «…/lesson/<uid>/q/<id>»`);
  const ch = ans.find(s => s.object.definition.interactionType === 'choice');
  ok(!ch || (ch.object.definition.choices.every((c, i) => c.id === 'abcdefghij'[i]) && ch.result.success === true), 'choice: variantlar a, b, c… (asl tartib), javob to\'g\'ri');
  if (QUIZ) ok(S.some(s => verb(s) === 'passed' && s.object.id === act + '/lesson/' + QUIZ.id && s.result.score.raw === 100), 'Test: passed (…/lesson/<test uid>, ball 100)');
  ok(S.some(s => verb(s) === 'completed' && s.object.id === act), 'Kurs: completed');
  ok(!errs.length, 'Konsol xatosiz' + (errs.length ? ': ' + errs.slice(0, 3).join(' | ') : ''));
  await ctx.close();
}

async function runPhone(br, base) {
  section('390px mobil, xesh navigatsiya, ko\'rish rejimi');
  const { ctx, page, errs } = await newCtx(br, { viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true });
  await page.goto(base + '/kurs/xapi/index.html?preview=1#lesson=' + VIEW[0].id);
  await page.waitForFunction(() => window.ISFTKurs && window.ISFTKurs.ready);
  ok(await page.$eval('main h1', e => e.textContent.trim()) === VIEW[0].title, '#lesson=<uid> — dars to\'g\'ridan-to\'g\'ri ochildi');
  ok(!!(await page.$('.banner')) && /Ko'rish rejimi/.test(await page.$eval('.banner', e => e.textContent)), '?preview=1 — «Ko\'rish rejimi» banneri');
  const wide = async () => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1);
  ok(await wide(), '390px: gorizontal aylantirish yo\'q (dars)');
  await page.screenshot({ path: path.join(OUT, 'player-phone.png'), fullPage: false });
  await page.click('.menu-btn'); await sleep(350);
  ok(await page.evaluate(() => document.getElementById('app').classList.contains('side-open') && document.getElementById('side').getBoundingClientRect().left >= -1), 'Menyu tugmasi yon panelni ochadi');
  await page.keyboard.press('Escape'); await sleep(300);
  ok(await page.evaluate(() => !document.getElementById('app').classList.contains('side-open')), 'Esc — panel yopiladi');
  for (const l of LESSONS) { await page.evaluate(id => { location.hash = 'lesson=' + id; }, l.id); await sleep(200); if (!(await wide())) { ok(false, `390px: «${l.title}» kengligi oshdi`); break; } }
  ok(true, `390px: barcha ${LESSONS.length} ta dars eni sig'adi`);
  ok(!errs.length, 'Konsol xatosiz' + (errs.length ? ': ' + errs.slice(0, 3).join(' | ') : ''));
  await ctx.close();
  section("Barcha blok turlari (namuna kursga qo'shilgan sintetik bloklar)");
  const ex = await newCtx(br);
  const img = (CONTENT.cover && CONTENT.cover.src) || (ALLB.find(b => b.src) || {}).src;
  await ex.ctx.route(/\/kurs\/xapi\/content\.js$/, async r => {
    const resp = await r.fetch(), c = JSON.parse((await resp.text()).trim().replace(/^window\.KURS = /, '').replace(/;$/, ''));
    const extra = [
      { id: 'bx0000001', type: 'heading', text: 'Qo\'shimcha bloklar', level: 2 },
      { id: 'bx0000002', type: 'quote', text: 'Iqtibos matni', cite: 'Muallif', style: 'quote' },
      { id: 'bx0000003', type: 'list', style: 'checkbox', items: ['<p>Birinchi</p>', '<p>Ikkinchi <a href="javascript:alert(1)">xavfli</a> <a href="https://isft.uz">sayt</a></p>'] },
      { id: 'bx0000004', type: 'paragraph', html: '<p onclick="alert(1)">Matn<img src=x onerror=alert(1)><script>alert(1)</script></p>' },
      { id: 'bx0000005', type: 'image', src: img, alt: 'Banner rasm', caption: '', layout: 'banner' },
      { id: 'bx0000006', type: 'image', src: img, alt: 'Katta rasm', caption: 'Izoh', layout: 'hero' },
      { id: 'bx0000007', type: 'image_text', src: img, alt: 'Yon rasm', html: '<p>Rasm yonidagi matn</p>', side: 'right' },
      { id: 'bx0000008', type: 'gallery', style: 'carousel', items: [{ src: img, alt: 'A', caption: '1' }, { src: img, alt: 'B', caption: '2' }] },
      { id: 'bx0000009', type: 'gallery', style: 'grid', items: [{ src: img, alt: 'A', caption: '' }, { src: img, alt: 'B', caption: '' }] },
      { id: 'bx0000010', type: 'video', source: 'youtube', yt_id: 'dQw4w9WgXcQ', yt_start: 5, title: 'Video', caption: 'Izoh' },
      { id: 'bx0000011', type: 'attachment', src: img, name: 'rasm.png', size: 12345, ext: 'png', title: 'Ilova', desc: 'Tavsif' },
      { id: 'bx0000012', type: 'labeled_graphic', src: img, alt: 'Belgili rasm', markers: [{ x: 20, y: 30, title: 'Birinchi', html: '<p>A</p>' }, { x: 70, y: 60, title: 'Ikkinchi', html: '<p>B</p>' }] },
      { id: 'bx0000013', type: 'flashcards', style: 'stack', cards: [{ front: 'Old', back: 'Orqa' }, { front: 'Old 2', back: 'Orqa 2' }] },
      { id: 'bx0000014', type: 'divider', style: 'dots' }, { id: 'bx0000015', type: 'divider', style: 'space' },
      { id: 'bx0000016', type: 'button', label: 'Xavfli', url: 'javascript:alert(1)', text: 'yo\'q bo\'lishi kerak' },
      { id: 'bx0000017', type: 'knowledge', kind: 'fill', question: 'Poytaxt?', answers: [], accept: ["Toshkent"], feedback_correct: 'Barakalla', feedback_wrong: 'Yana', retry: true }
    ];
    c.lessons[0].blocks = extra.concat(c.lessons[0].blocks);
    r.fulfill({ response: resp, body: 'window.KURS = ' + JSON.stringify(c) + ';' });
  });
  let dialogs = 0; ex.page.on('dialog', d => { dialogs++; d.dismiss(); });
  await ex.page.goto(base + '/kurs/xapi/index.html#lesson=' + LESSONS[0].id);
  await ex.page.waitForFunction(() => window.ISFTKurs && window.ISFTKurs.ready);
  const r = await ex.page.evaluate(() => ({
    types: ['quote', 'list', 'image', 'image_text', 'gallery', 'video', 'attachment', 'labeled_graphic', 'flashcards', 'divider'].filter(t => !document.querySelector('.b-' + t)),
    xss: !!document.querySelector('[onclick],[onerror],script:not([src]),a[href^="javascript"]') || !!document.querySelector('#b-bx0000016 a'),
    safeLink: !!document.querySelector('#b-bx0000003 a[href="https://isft.uz"][rel~="noopener"][target="_blank"]'),
    yt: (document.querySelector('#b-bx0000010 iframe') || {}).src || '', alts: [...document.querySelectorAll('main img')].every(i => i.hasAttribute('alt')),
    att: !!document.querySelector('#b-bx0000011 a[download]') }));
  ok(!r.types.length, 'Barcha blok turlari chizildi' + (r.types.length ? ' — yo\'q: ' + r.types.join(', ') : ''));
  ok(!r.xss && !dialogs && r.safeLink, 'XSS: onclick/onerror/script/javascript: havolalar olib tashlandi, https havola rel=noopener target=_blank');
  ok(/^https:\/\/www\.youtube-nocookie\.com\/embed\/dQw4w9WgXcQ\?rel=0&start=5$/.test(r.yt) && r.alts && r.att, 'YouTube — nocookie embed (start bilan), barcha rasmlarda alt, ilova — download havola');
  await ex.page.click('#b-bx0000012 .lg-m >> nth=0');
  ok(await ex.page.$eval('#b-bx0000012 .lg-panel', e => !e.hidden && /Birinchi/.test(e.textContent)), 'Belgili rasm: nuqta bosilganda izoh paneli');
  await ex.page.fill('#b-bx0000017 input.fill', '  toshkent. '); await ex.page.click('#b-bx0000017 .acts .btn');
  ok(!!(await ex.page.$('#b-bx0000017 .fbx.ok')) && await ex.page.evaluate(() => window.ISFTKurs.grade({ kind: 'fill', accept: ["O'zbekiston"] }, '  oʻzbekiston! ')), "Bo'sh joy: katta-kichik harf, apostrof varianti, chetdagi tinish belgilari e'tiborsiz");
  await ex.page.screenshot({ path: path.join(OUT, 'player-blocks.png'), fullPage: true });
  ok(!ex.errs.length, 'Konsol xatosiz' + (ex.errs.length ? ': ' + ex.errs.slice(0, 3).join(' | ') : ''));
  await ex.ctx.close();

  section("Ko'rish oynasining qat'iy CSP'si (sandbox, opaque origin)");
  const cs = await newCtx(br);
  const viol = []; cs.page.on('console', m => { if (/Content Security Policy|Refused to/.test(m.text())) viol.push(m.text().slice(0, 140)); });
  await cs.page.goto(base + '/csp/xapi/index.html?preview=1#lesson=' + VIEW[0].id);
  await cs.page.waitForFunction(() => window.ISFTKurs && window.ISFTKurs.ready, null, { timeout: 15000 }).catch(() => {});
  ok(CSP.includes("script-src 'self'") && await cs.page.evaluate(() => !!(window.ISFTKurs && window.ISFTKurs.ready) && String(window.origin) === 'null'), 'PREVIEW_CSP bilan ishga tushdi (sandbox — opaque origin)');
  ok(!viol.length && !cs.errs.length, 'CSP buzilishi va konsol xatosi yo\'q' + (viol.length || cs.errs.length ? ': ' + viol.concat(cs.errs).slice(0, 3).join(' | ') : ''));
  await cs.ctx.close();
  section("Qorong'i rejim");
  const d = await newCtx(br, { colorScheme: 'dark' });
  await d.page.goto(base + '/kurs/xapi/index.html');
  await d.page.waitForFunction(() => window.ISFTKurs && window.ISFTKurs.ready);
  const bg = await d.page.evaluate(() => getComputedStyle(document.body).backgroundColor.match(/\d+/g).slice(0, 3).map(Number));
  ok(bg.every(x => x < 60), `Fon to'q (${bg.join(',')})`);
  await d.page.screenshot({ path: path.join(OUT, 'player-dark.png') });
  ok(!d.errs.length, 'Konsol xatosiz');
  await d.ctx.close();
}

(async () => {
  const port = await listen(srv), lport = await listen(lrs);
  const base = 'http://127.0.0.1:' + port, lrsBase = 'http://127.0.0.1:' + lport;
  const br = await chromium.launch({ executablePath: process.env.CHROME, headless: true });
  try {
    await runScorm12(br, base);
    await runScorm2004(br, base);
    await runXapi(br, base, lrsBase);
    await runPhone(br, base);
  } catch (e) { ok(false, 'Kutilmagan xato: ' + (e && e.stack || e).toString().slice(0, 500)); }
  await br.close(); srv.close(); lrs.close();
  console.log('\n' + Object.entries(counts).map(([s, c]) => `${s}: ${c[0]} ✓ ${c[1]} ✗`).join('\n'));
  console.log(fails.length ? `XATO: ${fails.length} ta tekshiruv o'tmadi` : 'Hammasi o\'tdi');
  process.exit(fails.length ? 1 : 0);
})();
