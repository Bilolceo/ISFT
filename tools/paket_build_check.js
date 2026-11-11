#!/usr/bin/env node
/* Kontent paketlari: HAQIQIY yig'ilgan paket (app/paket.py + app/paket_player) brauzerda — uchidan-uchigacha integratsiya sinovi.
 *
 * Ishga tushirish (odatda tests/test_paket.py chaqiradi, PW va CHROME berilganda):
 *   PW=/path/node_modules/playwright-core CHROME=/path/to/chrome node tools/paket_build_check.js <katalog>
 *   <katalog>/scorm12, <katalog>/scorm2004, <katalog>/xapi — ochilgan paketlar (namuna: «Mikroiqtisodiyot» 1-mavzu).
 * Nima qiladi: mock LMS sahifasi (window.API / window.API_1484_11) ichida paketni iframe'da ochadi, 1366 va 390 px kenglikda barcha
 * bloklarni (reja, matn, slaydlar, video, test) ko'radi, testga to'g'ri javob beradi va LMS'ga yozilgan holat/ballni, konsol xatolarini,
 * gorizontal aylantirishni tekshiradi. Natija: "  ✓ ..." / "  ✗ ..." qatorlari; xato bo'lsa chiqish kodi 1.
 */
const http = require('http'), fs = require('fs'), path = require('path');
const { chromium } = require(process.env.PW);
const W = process.argv[2];
const MIME = {'.html':'text/html; charset=utf-8','.js':'text/javascript; charset=utf-8','.css':'text/css','.json':'application/json','.png':'image/png','.woff2':'font/woff2','.pptx':'application/octet-stream'};
const LMS = `<!doctype html><html><body style="margin:0"><iframe id="sco" style="border:0;width:100%;height:100vh"></iframe><script>
window.V = {}; window.CALLS = [];
const mk = (pre) => ({ [pre+'Initialize']: () => 'true', [pre+'Finish']: () => { CALLS.push('finish'); return 'true'; }, [pre+'Terminate']: () => { CALLS.push('terminate'); return 'true'; },
  [pre+'GetValue']: k => V[k] ?? '', [pre+'SetValue']: (k, v) => { V[k] = String(v); return 'true'; }, [pre+'Commit']: () => 'true',
  [pre+'GetLastError']: () => '0', [pre+'GetErrorString']: () => '', [pre+'GetDiagnostic']: () => '' });
const mode = new URLSearchParams(location.search).get('m');
if (mode === 'scorm12') { window.API = mk('LMS'); V['cmi.core.student_name'] = 'Valiyev, Ali'; V['cmi.core.lesson_status'] = 'not attempted'; V['cmi.core.entry'] = 'ab-initio'; }
if (mode === 'scorm2004') { const a = mk(''); window.API_1484_11 = a; V['cmi.learner_name'] = 'Ali Valiyev'; V['cmi.completion_status'] = 'unknown'; V['cmi.entry'] = 'ab-initio'; }
document.getElementById('sco').src = '/pkg/index.html';
</script></body></html>`;
let cur = null;
const srv = http.createServer((req, res) => {
  const u = new URL(req.url, 'http://x');
  if (u.pathname === '/favicon.ico') { res.writeHead(204); res.end(); return; }
  if (u.pathname === '/lms.html') { res.writeHead(200, {'Content-Type': 'text/html'}); res.end(LMS); return; }
  const rel = decodeURIComponent(u.pathname.replace(/^\/pkg\//, ''));
  const f = path.join(W, cur, rel);
  fs.readFile(f, (e, b) => { if (e) { res.writeHead(404); res.end(); return; } res.writeHead(200, {'Content-Type': MIME[path.extname(f)] || 'application/octet-stream'}); res.end(b); });
});
const fails = []; const ok = (c, m) => { console.log((c ? '  ✓ ' : '  ✗ ') + m); if (!c) fails.push(m); };
(async () => {
  await new Promise(r => srv.listen(0, r)); const port = srv.address().port;
  const br = await chromium.launch({executablePath: process.env.CHROME});
  for (const mode of ['scorm12', 'scorm2004', 'xapi']) {
    cur = mode; console.log('== ' + mode);
    const C = JSON.parse(fs.readFileSync(path.join(W, mode, 'content.json')));
    for (const width of [1366, 390]) {
      const p = await br.newPage({viewport: {width, height: 900}}); const errs = [];
      p.on('console', m => { if (m.type() === 'error') errs.push(m.text()); }); p.on('pageerror', e => errs.push(String(e)));
      p.on('response', r => { if (r.status() >= 400) errs.push('HTTP ' + r.status() + ' ' + r.url()); }); p.on('requestfailed', r => { if (!/youtube|ytimg|google/.test(r.url())) errs.push('reqfail ' + r.url()); });
      await p.goto(`http://127.0.0.1:${port}/lms.html?m=${mode}`);
      const fr = await (await p.waitForSelector('#sco')).contentFrame();
      await fr.waitForFunction(() => window.ISFTPaket && window.ISFTPaket.ready, null, {timeout: 15000});
      const n = await fr.evaluate(() => document.querySelectorAll('.toc-i').length);
      ok(n === C.blocks.length, `${width}px: ${n} ta blok navigatsiyada (${C.blocks.map(b => b.type).join(',')})`);
      for (let i = 0; i < n; i++) {
        const t = await fr.evaluate(i => { const b = document.querySelector('.toc-i[data-i="' + i + '"]'); b.click(); return b.dataset.type; }, i);
        await p.waitForTimeout(150);
        if (t === 'slides') {
          const s = await fr.evaluate(() => ({c: document.querySelector('.counter')?.textContent, dl: !!document.querySelector('a[href="assets/taqdimot.pptx"]')}));
          ok(s.c && s.dl, `${width}px: slaydlar ko'rsatildi (${s.c}), .pptx yuklab olish havolasi`);
          for (let k = 0; k < 5; k++) { await fr.press('.deck', 'ArrowRight').catch(() => {}); await p.waitForTimeout(60); }
        }
        if (t === 'text') ok(await fr.evaluate(() => document.querySelectorAll('.prose h2').length >= 4 && !!document.querySelector('.prose table')), `${width}px: ma'ruza matni (h2, jadval)`);
        if (t === 'plan') ok(await fr.evaluate(() => document.querySelectorAll('.plan li').length) === 4, `${width}px: reja 4 band`);
        if (t === 'video') ok(await fr.evaluate(() => !!document.querySelector('iframe[src*="youtube-nocookie.com/embed/ISFTdemo001"], [data-video], .video')), `${width}px: video bloki`);
      }
      const q = C.blocks.find(b => b.type === 'quiz');
      const qi = await fr.evaluate(() => +document.querySelector('.toc-i[data-type="quiz"]').dataset.i);
      await fr.evaluate(i => document.querySelector('.toc-i[data-i="' + i + '"]').click(), qi);
      await p.waitForTimeout(150); if (await fr.$('[data-act="start"]')) await fr.click('[data-act="start"]');
      await fr.waitForSelector('form.qform');
      for (const x of q.questions) {
        const sel = `fieldset[data-qid="${x.id}"]`;
        if (x.type === 'fill') await fr.fill(sel + ' input', x.answers[0]);
        else for (const i of x.correct) await fr.check(`${sel} input[value="${i}"]`);
      }
      await fr.click('form.qform [data-act="submit"]'); await p.waitForTimeout(500);
      const hs = await fr.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
      ok(hs <= 0, `${width}px: gorizontal aylantirish yo'q (${hs})`);
      const V = await p.evaluate(() => window.V);
      if (mode === 'scorm12') ok(V['cmi.core.lesson_status'] === 'passed' && V['cmi.core.score.raw'] === '100', `${width}px: SCORM 1.2 — ${V['cmi.core.lesson_status']}, ball ${V['cmi.core.score.raw']}`);
      if (mode === 'scorm2004') ok(V['cmi.completion_status'] === 'completed' && V['cmi.success_status'] === 'passed' && V['cmi.score.raw'] === '100', `${width}px: SCORM 2004 — ${V['cmi.completion_status']}/${V['cmi.success_status']}, ball ${V['cmi.score.raw']}`);
      if (mode === 'xapi') ok(await fr.evaluate(() => /(100|passed|o'tdi|o‘tdi)/i.test(document.body.innerText)), `${width}px: LMS'siz/xAPI ko'rish rejimi — natija ko'rsatildi`);
      ok(!errs.length, `${width}px: konsol xatolari yo'q ${errs.slice(0, 3).join(' | ')}`);
      if (width === 390) await p.screenshot({path: path.join(W, `shot_${mode}_390.png`)});
      await p.close();
    }
  }
  await br.close(); srv.close();
  console.log(fails.length ? `XATO: ${fails.length}` : 'Hammasi o\'tdi'); process.exit(fails.length ? 1 : 0);
})().catch(e => { console.error(e); process.exit(2); });
