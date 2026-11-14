#!/usr/bin/env node
/* Talaba kabineti «Mening darslarim» — brauzer tekshiruvi (tests/test_talaba_darslar.py chaqiradi).
 *   PW=/path/to/playwright-core CHROME=/path/to/chrome ISFT_TEST_URL=http://127.0.0.1:8000 TD_HEMIS=<HEMIS ID> TD_PASS=<parol> TD_OUT=/tmp/td
 *   node tools/talaba_darslar_check.js
 * Telefon kengligi (390×844): kirish → «Mening darslarim» → kurs, darslar, holat belgilari; gorizontal aylantirish yo'q; «Ochish» — pleyer yangi
 * oynada (xAPI launch); Telegram ulash kodi. Keyin keng ekran. Skrinshotlar: $TD_OUT. Natija «  ✓/✗ …», xato bo'lsa chiqish kodi 1. */
'use strict';
const fs = require('fs'), path = require('path');
const { chromium } = require(process.env.PW || 'playwright-core');
const B = process.env.ISFT_TEST_URL, OUT = process.env.TD_OUT || path.join(require('os').tmpdir(), 'isft_talaba_darslar');
fs.mkdirSync(OUT, { recursive: true });
const fails = [];
const ok = (c, m) => { console.log((c ? '  ✓ ' : '  ✗ ') + m); if (!c) fails.push(m); };

(async () => {
  const br = await chromium.launch({ executablePath: process.env.CHROME, headless: true });
  try {
    const ctx = await br.newContext({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 2, isMobile: true, hasTouch: true });
    const p = await ctx.newPage();
    const errs = [];
    p.on('console', m => { if (m.type() === 'error' && !/favicon|status of 4\d\d/.test(m.text())) errs.push(m.text()); });
    p.on('pageerror', e => errs.push('pageerror: ' + e.message));
    const lg = await p.request.post(B + '/api/talaba/login', { data: { hemis_id: process.env.TD_HEMIS, password: process.env.TD_PASS } });
    ok(lg.status() === 200, 'Talaba kirdi');
    await p.goto(B + '/talaba#darslarim');
    await p.waitForSelector('.tkd-c', { timeout: 20000 });
    ok(await p.isVisible('#tk-bottom a[data-p="darslarim"]'), "Pastki menyuda «Darslar» (masofaviy talaba)");
    ok((await p.locator('.tkd-c').count()) >= 1 && (await p.locator('.tkd-l').count()) >= 1, 'Kurslar va darslar ro\'yxati');
    const sw = await p.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    ok(sw <= 1, `Gorizontal aylantirish yo'q (${sw}px)`);
    await p.screenshot({ path: path.join(OUT, 'darslarim_telefon.png'), fullPage: false });
    await p.screenshot({ path: path.join(OUT, 'darslarim_telefon_full.png'), fullPage: true });
    // Telegram ulash kodi
    const tg = p.locator('[data-tg="code"]');
    if (await tg.count()) {
      await tg.click();
      await p.waitForSelector('.tkd-otp', { timeout: 10000 });
      ok(/^[A-Z2-9]{8}$/.test((await p.textContent('.tkd-otp')).trim()), 'Telegram: bir martalik kod ko\'rsatildi');
      await p.locator('.tkd-otp').scrollIntoViewIfNeeded();
      await p.screenshot({ path: path.join(OUT, 'darslarim_telegram_kod.png'), fullPage: false });
    }
    // Ochish → pleyer yangi oynada
    const btn = p.locator('[data-open]').first();
    if (await btn.count()) {
      const [pop] = await Promise.all([ctx.waitForEvent('page', { timeout: 15000 }), btn.click()]);
      await pop.waitForURL(/\/xapi\/pkg\/.+index\.html\?endpoint=/, { timeout: 20000 });
      ok(/auth=Basic/.test(pop.url()) && /registration=/.test(pop.url()), 'Ochish: pleyer xAPI launch parametrlari bilan ochildi');
      await pop.waitForTimeout(1500);
      await pop.screenshot({ path: path.join(OUT, 'darslarim_pleyer_telefon.png'), fullPage: false });
      await pop.close();
    }
    ok(!errs.length, 'Konsolda xato yo\'q' + (errs.length ? ': ' + errs.slice(0, 3).join(' | ') : ''));
    // keng ekran
    const d = await br.newContext({ viewport: { width: 1366, height: 900 } });
    const dp = await d.newPage();
    await dp.request.post(B + '/api/talaba/login', { data: { hemis_id: process.env.TD_HEMIS, password: process.env.TD_PASS } });
    await dp.goto(B + '/talaba#darslarim');
    await dp.waitForSelector('.tkd-c', { timeout: 20000 });
    await dp.screenshot({ path: path.join(OUT, 'darslarim_keng.png'), fullPage: false });
  } catch (e) {
    ok(false, 'Istisno: ' + e.message);
  } finally {
    await br.close();
  }
  console.log(`Skrinshotlar: ${OUT}`);
  process.exit(fails.length ? 1 : 0);
})();
