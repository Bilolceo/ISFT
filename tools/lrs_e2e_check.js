#!/usr/bin/env node
/* ISFT LRS — uchidan-uchigacha brauzer sinovi (tests/test_lrs.py chaqiradi; docs/lrs.md).
 *
 * Ishga tushirish:
 *   PW=/path/to/playwright-core CHROME=/path/to/chrome B=http://127.0.0.1:8000 LAUNCH=/xapi/l/<kod> COURSE=ku:<id> STUDENT="<ism>"
 *   ADMIN_UID=<masofaviy user id> ADMIN_PW=<parol> OUT=/tmp/lrs node tools/lrs_e2e_check.js
 *
 * Oqim: (1) bo'lim xodimi «Ortda qolganlar» ekranida talabani ko'radi («umuman boshlamagan»); (2) talaba (cookie'siz, alohida kontekst) shaxsiy
 * havolani ochadi → ISFT Core paketni xAPI launch parametrlari bilan ochadi → testdagi savolga (ataylab noto'g'ri) javob beradi; pleyer statementlarni
 * /xapi ga yuboradi; (3) ekran yangilanadi: talaba ro'yxatdan chiqadi (endi faol), talaba darslari va savollar tahlilida natija, «Muharrirda ochish» —
 * Kurs muharririda o'sha blok tanlangan. Qo'shimcha skrinshotlar: namuna kursning ro'yxati, voronkasi, savollar tahlili, telefon kengligi.
 * Natija: "  ✓ …" / "  ✗ …", xato bo'lsa chiqish kodi 1. Skrinshotlar: $OUT.
 */
'use strict';
const fs = require('fs'), path = require('path');
const { chromium } = require(process.env.PW || 'playwright-core');
const B = process.env.B, OUT = process.env.OUT || path.join(require('os').tmpdir(), 'isft_lrs_e2e');
const COURSE = process.env.COURSE, STUDENT = process.env.STUDENT;
fs.mkdirSync(OUT, { recursive: true });
const fails = [];
const ok = (c, m) => { console.log((c ? '  ✓ ' : '  ✗ ') + m); if (!c) fails.push(m); };
const sleep = ms => new Promise(r => setTimeout(r, ms));
const shot = (p, n) => p.screenshot({ path: path.join(OUT, n), fullPage: false });

(async () => {
  const br = await chromium.launch({ executablePath: process.env.CHROME, headless: true });
  try {
    // ---------------- (1) bo'lim xodimi: oldingi holat ----------------
    const actx = await br.newContext({ viewport: { width: 1440, height: 950 } });
    const ap = await actx.newPage();
    const aerr = [];
    ap.on('console', m => { if (m.type() === 'error' && !/favicon|status of 4\d\d/.test(m.text())) aerr.push(m.text()); });
    ap.on('pageerror', e => aerr.push('pageerror: ' + e.message));
    const lg = await ap.request.post(B + '/api/login', { data: { user_id: +process.env.ADMIN_UID, password: process.env.ADMIN_PW } });
    ok(lg.status() === 200, "Kirish (Masofaviy ta'lim bo'limi)");
    await ap.goto(B + '/');
    await ap.waitForFunction(() => typeof go === 'function' && typeof ME !== 'undefined' && ME && typeof renderOrtda === 'function');
    ok(await ap.isVisible('#nav a[data-v="ortda"]'), 'Menyuda «Ortda qolganlar» bandi');
    const api = async u => (await ap.request.get(B + u)).json();
    const list0 = await api(`/api/ortda/list?course=${encodeURIComponent(COURSE)}&only_risk=false&limit=500&q=${encodeURIComponent(STUDENT)}`);
    const sid = (list0.items[0] || {}).student_id;
    ok(!!sid, `Talaba sinov kursi ro'yxatida (#${sid})`);
    // namuna kurs (45 dars) — umumiy ko'rinish skrinshotlari
    await ap.evaluate(() => go('ortda'));
    await ap.waitForSelector('#orBox .dl-t tbody tr', { timeout: 20000 });
    ok((await ap.$$('#orBox .dl-t tbody tr')).length > 5, 'Ro\'yxat: ortda qolgan talabalar (namuna ma\'lumot)');
    ok(await ap.isVisible('.dl-demo'), "«Namuna ma'lumot» ogohlantirishi ko'rinadi");
    await shot(ap, 'ortda-talabalar.png');
    await ap.click('#orBox .dl-t tbody tr:first-child [data-st]');
    await ap.waitForSelector('.dl-modal .or-grid .or-cell');
    ok((await ap.$$('.dl-modal .or-grid .or-cell')).length >= 15, 'Talaba darslari: darslar xaritasi (holat bo\'yicha rang)');
    await shot(ap, 'ortda-talaba-darslari.png');
    await ap.click('.dl-modal [data-x]');
    await ap.evaluate(() => renderOrtda('kurslar'));
    await ap.waitForSelector('.or-funnel .or-fr:not(.or-fh)', { timeout: 15000 });
    await shot(ap, 'ortda-kurslar-voronka.png');
    await ap.evaluate(() => renderOrtda('savollar'));
    await ap.waitForSelector('#orBox .dl-t tbody tr', { timeout: 15000 });
    ok(/xato topyapti/.test(await ap.textContent('#orBox')), "Savollar tahlili: «bu savolni N% xato topyapti»");
    await shot(ap, 'ortda-savollar.png');
    // sinov kursi: oldin
    await ap.evaluate(([c, s]) => { OQ.f = { ...OQ0, course: c, q: s }; renderOrtda('talabalar'); }, [COURSE, STUDENT]);
    await ap.waitForSelector('#orBox .dl-t tbody tr', { timeout: 15000 });
    const before = await ap.textContent('#orBox .dl-t tbody');
    ok(/umuman boshlamagan/.test(before), "Oldin: talaba «Kursni umuman boshlamagan» sababi bilan ro'yxatda");
    await shot(ap, 'e2e-1-ortda-oldin.png');

    // ---------------- (2) talaba: shaxsiy havola → paket → savolga javob ----------------
    const sctx = await br.newContext({ viewport: { width: 1280, height: 860 } });
    const sp = await sctx.newPage();
    const serr = [], posts = [];
    sp.on('console', m => { if (m.type() === 'error' && !/favicon|status of 404/.test(m.text())) serr.push(m.text()); });
    sp.on('pageerror', e => serr.push('pageerror: ' + e.message));
    sp.on('response', r => { if (/\/xapi\/statements$/.test(r.url()) && r.request().method() === 'POST') posts.push(r.status()); });
    await sp.goto(B + process.env.LAUNCH);
    await sp.waitForFunction(() => window.ISFTKurs && window.ISFTKurs.ready, null, { timeout: 20000 });
    const u = new URL(sp.url());
    ok(/\/xapi\/pkg\//.test(u.pathname) && u.searchParams.get('endpoint').endsWith('/xapi/') && /^Basic /.test(u.searchParams.get('auth')), 'Havola → paket launch parametrlari bilan ochildi');
    ok((await sp.evaluate(() => window.ISFTKurs.mode)) === 'xapi', 'Pleyer xAPI rejimida (NEXTID iframe\'idagi jim rejim emas)');
    await shot(sp, 'e2e-2-paket-muqova.png');
    const quiz = await sp.evaluate(() => { const l = window.KURS.lessons.find(x => x.type === 'quiz'); return { id: l.id, q: l.questions.map(q => ({ question: q.question, answers: q.answers.map(a => !!a.correct) })) }; });
    await sp.click('#startBtn');
    await sleep(300);
    await sp.click(`.les-b[data-lesson="${quiz.id}"]`);
    await sp.waitForSelector('.qz-start .btn.primary');
    await sp.click('.qz-start .btn.primary');
    for (let n = 0; n < 40; n++) {
      await sleep(120);
      if (await sp.$('.qz-res')) break;
      const leg = await sp.$eval('.qz legend', e => e.textContent.trim()).catch(() => '');
      const qq = quiz.q.find(x => x.question === leg);
      if (qq && await sp.$('.qz .opt input:not(:checked)') && !(await sp.$('.qz .fb .ok, .qz .fb .bad'))) {
        const wrong = qq.answers.findIndex(a => !a);
        await sp.check(`.qz .opt[data-ai="${wrong}"] input`).catch(() => {});
        if (n === 0) await shot(sp, 'e2e-3-savol.png');
      }
      if (await sp.$('.qz .acts .btn.primary')) await sp.click('.qz .acts .btn.primary');
    }
    ok(!!(await sp.$('.qz-res')), 'Test yakunlandi (natija ekrani)');
    await shot(sp, 'e2e-4-test-natijasi.png');
    // statementlar yetib borishini kutish
    let row = null;
    for (let k = 0; k < 40 && !(row && row.last); k++) {
      await sleep(250);
      const l = await api(`/api/ortda/list?course=${encodeURIComponent(COURSE)}&only_risk=false&limit=500&q=${encodeURIComponent(STUDENT)}`);
      row = l.items.find(x => x.student_id === sid);
    }
    ok(posts.length > 0 && posts.every(s => s === 200), `Pleyer /xapi/statements ga yubordi (POST: ${posts.join(',')})`);
    ok(row && row.last && row.days_inactive === 0, 'LRS: talaba faolligi bugun qayd etildi');
    await sp.close();   // pagehide → terminated / suspended
    await sleep(800);
    ok(!serr.length, 'Talaba sahifasida konsol xatolari yo\'q' + (serr.length ? ': ' + serr.slice(0, 3).join(' | ') : ''));

    // ---------------- (3) ekran yangilandi ----------------
    await ap.evaluate(() => renderOrtda('talabalar'));
    await ap.waitForSelector('#orBox .dl-t, #orBox .dl-empty', { timeout: 15000 });
    await sleep(300);
    const after = await ap.textContent('#orBox');
    ok(!/umuman boshlamagan/.test(after), "Keyin: «umuman boshlamagan» sababi yo'qoldi (talaba endi ortda qolganlar ro'yxatida emas)");
    await shot(ap, 'e2e-5-ortda-keyin.png');
    await ap.evaluate(([s, c]) => orStudent(s, c), [sid, COURSE]);
    await ap.waitForSelector('.dl-modal .or-grid');
    const md = await ap.textContent('.dl-modal');
    ok(/Yakuniy test/.test(md) && /(Testdan o'tmadi|O'tdi)/.test(md), 'Talaba darslari: «Yakuniy test» — natija va urinish');
    await shot(ap, 'e2e-6-talaba-darslari.png');
    await ap.click('.dl-modal [data-x]');
    await ap.evaluate(c => { OQ.qcourse = c; OQ.qlesson = ''; renderOrtda('savollar'); }, COURSE);
    await ap.waitForSelector('#orBox .dl-t tbody tr', { timeout: 15000 });
    ok(/Narx oshsa talab/.test(await ap.textContent('#orBox')), 'Savollar tahlili: sinov kursidagi savol (javoblar soni bilan)');
    await shot(ap, 'e2e-7-savollar.png');
    await ap.click('#orBox [data-ed]');
    await ap.waitForSelector('#kuBlocks .ku-blk.sel', { timeout: 15000 });
    ok(/Narx oshsa talab/.test(await ap.textContent('#kuBlocks .ku-blk.sel')), "«Muharrirda ochish» → Kurs muharririda o'sha savol bloki tanlangan");
    await sleep(600);
    await shot(ap, 'e2e-8-muharrir-blok.png');
    // telefon kengligi
    await ap.setViewportSize({ width: 390, height: 844 });
    await ap.evaluate(() => { OQ.f = { ...OQ0 }; go('ortda'); });
    await ap.waitForSelector('#orBox .dl-t tbody tr', { timeout: 15000 });
    const sw = await ap.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1);
    ok(sw, 'Telefon kengligida (390 px) gorizontal aylantirish yo\'q');
    await shot(ap, 'ortda-telefon.png');
    ok(!aerr.length, 'Xodim sahifasida konsol xatolari yo\'q' + (aerr.length ? ': ' + aerr.slice(0, 3).join(' | ') : ''));
  } catch (e) {
    ok(false, 'Istisno: ' + (e && e.stack || e).toString().split('\n').slice(0, 4).join(' | '));
  } finally {
    await br.close();
  }
  console.log(fails.length ? `XATO: ${fails.length}` : 'Hammasi o\'tdi');
  process.exit(fails.length ? 1 : 0);
})();
