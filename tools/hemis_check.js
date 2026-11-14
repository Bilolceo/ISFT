#!/usr/bin/env node
/* «HEMIS almashinuvi» — brauzer tekshiruvi (tests/test_hemis.py chaqiradi).
 *   PW=/path/to/playwright-core CHROME=/path/to/chrome ISFT_TEST_URL=http://127.0.0.1:8000 HM_UID=<registrator id> HM_PW=<parol>
 *   HM_FILE=<sintetik .xlsx> HM_OUT=/tmp/hemis_shots  node tools/hemis_check.js
 * Keng ekran va telefon: menyu bandi → Import (fayl yuklash → ko'rib chiqish sonlari) → Farqlar navbati → qaror oynasi → Sifat → Sozlamalar.
 * Gorizontal aylantirish yo'q, konsolda xato yo'q. Skrinshotlar: $HM_OUT. Import QO'LLANMAYDI (ko'rib chiqish bekor qilinadi). */
'use strict';
const fs = require('fs'), path = require('path');
const { chromium } = require(process.env.PW || 'playwright-core');
const B = process.env.ISFT_TEST_URL, OUT = process.env.HM_OUT || path.join(require('os').tmpdir(), 'hemis_shots');
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
      const lg = await p.request.post(B + '/api/login', { data: { user_id: +process.env.HM_UID, password: process.env.HM_PW } });
      ok(lg.status() === 200, `[${name}] Registrator kirdi`);
      await p.goto(B + '/');
      await p.waitForFunction(() => typeof go === 'function' && typeof ME !== 'undefined' && ME && typeof renderHemis === 'function');
      ok(await p.$('#nav a[data-v="hemis"]:not(.hidden)') !== null, `[${name}] Menyuda «HEMIS almashinuvi» bandi`);
      await p.evaluate(() => go('hemis', { tab: 'umumiy' }));
      await p.waitForSelector('#v-hemis .dl-kpis', { timeout: 20000 });
      ok(await noScroll(p) <= 1, `[${name}] Umumiy: gorizontal aylantirish yo'q`);
      await p.screenshot({ path: path.join(OUT, `umumiy_${name}.png`), fullPage: true });
      await p.evaluate(() => { HM.tab = 'import'; HM.prev = null; renderHemis(); });
      await p.waitForSelector('#hmFile', { state: 'attached', timeout: 20000 });
      await p.setInputFiles('#hmFile', process.env.HM_FILE);
      await p.waitForSelector('#v-hemis .hm-preview .dl-kpis', { timeout: 60000 });
      const kp = await p.locator('#v-hemis .hm-preview .dl-kpi').count();
      ok(kp >= 5, `[${name}] Import ko'rib chiqish: ${kp} ta ko'rsatkich (yangi / o'zgargan / ziddiyatli / topilmadi / o'zgarmagan)`);
      ok(await p.locator('#v-hemis .hm-preview table.dl-t tbody tr').count() >= 1, `[${name}] Ziddiyatli qatorlar jadvali`);
      ok(await noScroll(p) <= 1, `[${name}] Import: gorizontal aylantirish yo'q`);
      await p.screenshot({ path: path.join(OUT, `import_korib_chiqish_${name}.png`), fullPage: true });
      await p.click('#hmCancel');
      await p.waitForFunction(() => !document.querySelector('#v-hemis .hm-preview') && document.querySelector('#v-hemis #hmFile') && !HM.prev, null, { timeout: 20000 });
      await p.evaluate(() => { HM.tab = 'farqlar'; HM.df = { status: 'ochiq', entity: '', field: '', q: '', offset: 0 }; renderHemis(); });
      await p.waitForSelector('#v-hemis #hmDQ', { state: 'attached', timeout: 20000 });
      const nd = await p.locator('#v-hemis [data-d]').count();
      ok(await noScroll(p) <= 1, `[${name}] Farqlar navbati (${nd} ta qator): gorizontal aylantirish yo'q`);
      await p.screenshot({ path: path.join(OUT, `farqlar_${name}.png`), fullPage: true });
      if (nd) {
        await p.locator('#v-hemis [data-d]').first().click();
        await p.waitForSelector('.dl-modal input[name="hmDec"]', { timeout: 10000 });
        ok((await p.locator('.dl-modal input[name="hmDec"]').count()) === 3, `[${name}] Qaror oynasi: 3 variant (HEMIS / ISFT Core / qo'lda)`);
        await p.screenshot({ path: path.join(OUT, `farq_qaror_${name}.png`) });
        await p.click('.dl-modal [data-x]');
      }
      await p.evaluate(() => { HM.tab = 'sifat'; renderHemis(); });
      await p.waitForSelector('#v-hemis .hm-q', { timeout: 20000 });
      ok(await noScroll(p) <= 1, `[${name}] Sifat: gorizontal aylantirish yo'q`);
      await p.screenshot({ path: path.join(OUT, `sifat_${name}.png`), fullPage: true });
      await p.evaluate(() => { HM.tab = 'sozlama'; renderHemis(); });
      await p.waitForSelector('#v-hemis #hmUrl', { timeout: 20000 });
      await p.screenshot({ path: path.join(OUT, `sozlamalar_${name}.png`), fullPage: true });
      ok(!errs.length, `[${name}] Konsolda xato yo'q` + (errs.length ? ': ' + errs.slice(0, 3).join(' | ') : ''));
      await ctx.close();
    }
  } catch (e) {
    ok(false, 'Brauzer xatosi: ' + e.message);
  } finally {
    await br.close();
  }
  process.exit(fails.length ? 1 : 0);
})();
