#!/usr/bin/env node
/* «Yuzma-yuz tadbirlar» — brauzer tekshiruvi (tests/test_yuzma_yuz.py chaqiradi).
 *   PW=/path/to/playwright-core CHROME=/path/to/chrome ISFT_TEST_URL=http://127.0.0.1:8000 YY_UID=<masofaviy xodim id> YY_PW=<parol>
 *   YY_SESS=<bugungi sessiya id> YY_HEMIS=<talaba HEMIS> YY_SPW=<talaba paroli> YY_OUT=/tmp/yy  node tools/yuzma_check.js
 * Xodim (keng ekran va telefon): menyu bandi → Umumiy → sessiya → shaxsni tekshirish oynasi → Huquqiy chegaralar → Monitoring.
 * Talaba (telefon 390×844): bosh sahifada banner, «Yuzma-yuz» sahifasi; gorizontal aylantirish yo'q. Skrinshotlar: $YY_OUT. */
'use strict';
const fs = require('fs'), path = require('path');
const { chromium } = require(process.env.PW || 'playwright-core');
const B = process.env.ISFT_TEST_URL, OUT = process.env.YY_OUT || path.join(require('os').tmpdir(), 'isft_yuzma');
fs.mkdirSync(OUT, { recursive: true });
const fails = [];
const ok = (c, m) => { console.log((c ? '  ✓ ' : '  ✗ ') + m); if (!c) fails.push(m); };
const noScroll = async p => p.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);

(async () => {
  const br = await chromium.launch({ executablePath: process.env.CHROME, headless: true });
  try {
    for (const [name, vp] of [['keng', { width: 1366, height: 900 }], ['telefon', { width: 390, height: 844 }]]) {
      const ctx = await br.newContext({ viewport: vp, deviceScaleFactor: name === 'telefon' ? 2 : 1, isMobile: name === 'telefon', hasTouch: name === 'telefon' });
      const p = await ctx.newPage();
      const errs = [];
      p.on('console', m => { if (m.type() === 'error' && !/favicon|status of 4\d\d/.test(m.text())) errs.push(m.text()); });
      p.on('pageerror', e => errs.push('pageerror: ' + e.message));
      const lg = await p.request.post(B + '/api/login', { data: { user_id: +process.env.YY_UID, password: process.env.YY_PW } });
      ok(lg.status() === 200, `[${name}] Xodim kirdi`);
      await p.goto(B + '/');
      await p.waitForFunction(() => typeof go === 'function' && typeof ME !== 'undefined' && ME && typeof renderYuzma === 'function');
      ok(await p.$('#nav a[data-v="yuzma"]:not(.hidden)') !== null, `[${name}] Menyuda «Yuzma-yuz tadbirlar» bandi`);
      await p.evaluate(() => go('yuzma'));
      await p.waitForSelector('#v-yuzma .dl-kpis', { timeout: 20000 });
      ok((await p.locator('#v-yuzma .dl-kpi').count()) >= 4, `[${name}] Umumiy: ko'rsatkichlar`);
      ok(await noScroll(p) <= 1, `[${name}] Umumiy: gorizontal aylantirish yo'q`);
      await p.screenshot({ path: path.join(OUT, `xodim_umumiy_${name}.png`), fullPage: true });
      await p.evaluate(id => yyOpen(id), +process.env.YY_SESS);
      await p.waitForSelector('#v-yuzma .yy-head', { timeout: 20000 });
      ok((await p.locator('#v-yuzma [data-chk]').count()) >= 1, `[${name}] Sessiya: «Tekshirish» tugmalari`);
      ok(await noScroll(p) <= 1, `[${name}] Sessiya: gorizontal aylantirish yo'q`);
      await p.screenshot({ path: path.join(OUT, `xodim_sessiya_${name}.png`), fullPage: true });
      await p.locator('#v-yuzma [data-chk]').first().click();
      await p.waitForSelector('.dl-modal #yyCode', { timeout: 10000 });
      ok(await p.$eval('.dl-modal #yyCode', i => i.maxLength) === 4, `[${name}] Tekshirish oynasi: faqat 4 raqam`);
      await p.screenshot({ path: path.join(OUT, `xodim_tekshirish_${name}.png`) });
      await p.click('.dl-modal [data-x]');
      await p.evaluate(() => { YY.tab = 'chegaralar'; YY.sess = 0; renderYuzma(); });
      await p.waitForSelector('#v-yuzma .dl-t', { timeout: 20000 });
      ok(await noScroll(p) <= 1, `[${name}] Huquqiy chegaralar: gorizontal aylantirish yo'q`);
      await p.screenshot({ path: path.join(OUT, `xodim_chegaralar_${name}.png`), fullPage: true });
      await p.evaluate(() => { YY.tab = 'monitoring'; renderYuzma(); });
      await p.waitForSelector('#v-yuzma .dl-seg', { timeout: 20000 });
      await p.screenshot({ path: path.join(OUT, `xodim_monitoring_${name}.png`), fullPage: true });
      const jr = p.locator('#v-yuzma [data-jr]').first();
      if (await jr.count()) {
        await jr.click(); await p.waitForSelector('.dl-modal .dl-kpis', { timeout: 10000 });
        await p.screenshot({ path: path.join(OUT, `xodim_jurnal_${name}.png`) });
        await p.click('.dl-modal [data-x]');
      }
      await p.evaluate(() => go('masofaviy'));
      await p.waitForSelector('#v-masofaviy .yy-mcard', { timeout: 20000 });
      ok(true, `[${name}] «Masofaviy ta'lim → Umumiy»: yuzma-yuz va huquqiy chegaralar kartasi`);
      await p.screenshot({ path: path.join(OUT, `masofaviy_umumiy_${name}.png`) });
      ok(!errs.length, `[${name}] Konsolda xato yo'q` + (errs.length ? ': ' + errs.slice(0, 3).join(' | ') : ''));
      await ctx.close();
    }
    // talaba — telefon
    const sc = await br.newContext({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 2, isMobile: true, hasTouch: true });
    const sp = await sc.newPage();
    const errs = [];
    sp.on('pageerror', e => errs.push('pageerror: ' + e.message));
    const sl = await sp.request.post(B + '/api/talaba/login', { data: { hemis_id: process.env.YY_HEMIS, password: process.env.YY_SPW } });
    ok(sl.status() === 200, 'Talaba kirdi');
    await sp.goto(B + '/talaba#bosh');
    await sp.waitForSelector('.yy-tk-banner', { timeout: 20000 });
    ok(true, 'Talaba bosh sahifasida yuzma-yuz banneri');
    ok(await noScroll(sp) <= 1, 'Talaba bosh sahifasi: gorizontal aylantirish yo\'q');
    await sp.screenshot({ path: path.join(OUT, 'talaba_bosh_telefon.png') });
    await sp.goto(B + '/talaba#yuzma');
    await sp.waitForSelector('.yy-tk', { timeout: 20000 });
    ok(await noScroll(sp) <= 1, 'Talaba «Yuzma-yuz» sahifasi: gorizontal aylantirish yo\'q');
    await sp.screenshot({ path: path.join(OUT, 'talaba_yuzma_telefon.png'), fullPage: true });
    ok(!errs.length, 'Talaba: konsolda xato yo\'q' + (errs.length ? ': ' + errs.slice(0, 3).join(' | ') : ''));
  } catch (e) {
    ok(false, 'Brauzer xatosi: ' + e.message);
  } finally {
    await br.close();
  }
  process.exit(fails.length ? 1 : 0);
})();
