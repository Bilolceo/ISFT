#!/usr/bin/env node
/* Eski «Dars tayyorlash» ekrani (static/paket.js, tab «mavzular»): Word testi yuklanganda javobi (✅) topilmagan savollar uchun
   «Javobi belgilanmagan savollar» oynasi. tests/test_import.py chaqiradi: B, KX_UID, KX_PW, KX_CID (dl kurs), KX_KEY (dars kaliti), KX_TEST (test.docx),
   OUT (skrinshotlar). 1440 va 390 px: oyna ochiladi, tekshiruv (javobsiz saqlanmaydi), bir nechta javob, o'tkazib yuborish, Esc, dars panelidagi tugma. */
const { chromium } = require(process.env.PW || 'playwright-core');
const fs = require('fs');
const B = process.env.B, OUT = process.env.OUT || '/tmp/pk_answers';
fs.mkdirSync(OUT, { recursive: true });
let bad = 0;
const ok = (c, m) => { console.log((c ? '✓ ' : '✗ ') + m); if (!c) bad++; };
const sleep = ms => new Promise(r => setTimeout(r, ms));
(async () => {
  const b = await chromium.launch({ executablePath: process.env.CHROME, headless: true });
  try {
    for (const [W, H, tag] of [[1440, 900, 'd'], [390, 844, 'm']]) {
      const ctx = await b.newContext({ viewport: { width: W, height: H } });
      const page = await ctx.newPage();
      const errs = []; page.on('pageerror', e => errs.push(String(e)));
      const lg = await page.request.post(B + '/api/login', { data: { user_id: +process.env.KX_UID, password: process.env.KX_PW } });
      if (!lg.ok()) throw new Error('login ' + lg.status());
      await page.goto(B + '/'); await sleep(1200);
      const open = async () => {
        await page.evaluate(([cid, key]) => { PK.cid = cid; PK.topic = key; PK.ups = null; go('paket', { tab: 'mavzular' }); }, [+process.env.KX_CID, +process.env.KX_KEY]);
        await page.waitForSelector('#pkAny', { state: 'attached', timeout: 20000 }); await sleep(500);
      };
      const quizN = () => page.evaluate(async ([cid, key]) => (await (await fetch(`/api/paket/courses/${cid}/topics/${key}`, { credentials: 'same-origin' })).json()).ready.quiz, [+process.env.KX_CID, +process.env.KX_KEY]);
      await open();
      await page.setInputFiles('#pkAny', process.env.KX_TEST);
      await page.waitForSelector('.ta-bg .ta-q', { timeout: 30000 }); await sleep(250);
      ok(await page.$eval('.ta-bg .pk-modal', e => e.getAttribute('role') === 'dialog' && e.getAttribute('aria-modal') === 'true' && /Javobi belgilanmagan savollar \(1 ta\)/.test(e.querySelector('h3').textContent)),
        `[${tag}] eski ekran: test yuklangach «Javobi belgilanmagan savollar (1 ta)» oynasi ochildi`);
      ok(/4 ta savol qo'shildi, 1 tasi javobsiz — hozir tanlang/.test(await page.textContent('.ta-sum')), `[${tag}] hisob: «4 ta savol qo'shildi, 1 tasi javobsiz — hozir tanlang»`);
      await page.screenshot({ path: `${OUT}/${tag}_pk_javob_oynasi.png` });
      await page.click('.pk-modal [data-ok]'); await sleep(150);
      ok(await page.isVisible('.ta-bg') && (await page.textContent('.ta-q .ta-err')).includes("To'g'ri javobni belgilang"), `[${tag}] javobsiz saqlab bo'lmaydi — savol ostida xato`);
      await page.keyboard.press('Escape'); await sleep(150);
      ok(!(await page.$('.ta-bg')), `[${tag}] Esc — oyna yopildi`);
      await page.waitForSelector('#pkTaOpen', { timeout: 15000 });
      ok(/To'g'ri javobni tanlang \(1\)/.test(await page.textContent('#pkTaOpen')) && /1 ta import qilingan savolning/.test(await page.textContent('[data-tile="quiz"]')),
        `[${tag}] «Test va mashqlar» kartasida: 1 ta savol javobsiz + «To'g'ri javobni tanlang (1)» tugmasi`);
      await page.screenshot({ path: `${OUT}/${tag}_pk_tile.png`, fullPage: true });
      await page.click('#pkTaOpen'); await page.waitForSelector('.ta-bg .ta-q');
      await page.check('.ta-q .ta-opts label:nth-child(2) input');
      await page.click('.pk-modal [data-ok]');
      await page.waitForFunction(() => !document.querySelector('.ta-bg'), null, { timeout: 15000 }); await sleep(600);
      const q1 = await quizN();
      ok(q1.pending === 0 && q1.approved === 5 && !(await page.$('#pkTaOpen')), `[${tag}] bitta javob saqlandi: 5 ta savol, kutayotgani yo'q (approved=${q1.approved}, pending=${q1.pending})`);
      // qayta yuklash → o'tkazib yuborish
      await page.setInputFiles('#pkAny', process.env.KX_TEST);
      await page.waitForSelector('.ta-bg .ta-q', { timeout: 30000 });
      await page.click('.ta-q [data-skip]');
      ok(await page.$eval('.ta-q', e => e.classList.contains('skip')), `[${tag}] «O'tkazib yuborish» ishlaydi`);
      await page.click('.pk-modal [data-ok]');
      await page.waitForFunction(() => !document.querySelector('.ta-bg'), null, { timeout: 15000 }); await sleep(600);
      const q2 = await quizN();
      ok(q2.pending === 0 && q2.approved === 4, `[${tag}] o'tkazib yuborilgan savol javobsiz qoralama bo'ldi — testda 4 ta (approved=${q2.approved})`);
      ok(errs.length === 0, `[${tag}] konsolda xato yo'q ${errs.slice(0, 2).join(' | ')}`);
      await ctx.close();
    }
  } catch (e) { console.log('✗ ' + (e.stack || e)); bad++; }
  await b.close();
  process.exit(bad ? 1 : 0);
})();
