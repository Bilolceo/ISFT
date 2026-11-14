#!/usr/bin/env node
/* «Ortda qolganlar» keyslari, natija, eslatmalar, Nazorat kartasi va talaba kabineti «Bu hafta» — brauzer tekshiruvi (tests/test_keyslar.py chaqiradi).
 *   PW=/path/to/playwright-core CHROME=/path/to/chrome ISFT_TEST_URL=… ADMIN_UID=… REK_UID=… ADMIN_PW=… TD_HEMIS=… TD_PASS=… KS_OUT=/tmp/ks
 *   node tools/keyslar_check.js
 * Skrinshotlar: $KS_OUT. Natija «  ✓/✗ …», xato bo'lsa chiqish kodi 1. */
'use strict';
const fs = require('fs'), path = require('path');
const { chromium } = require(process.env.PW || 'playwright-core');
const B = process.env.ISFT_TEST_URL, OUT = process.env.KS_OUT || path.join(require('os').tmpdir(), 'isft_keyslar');
fs.mkdirSync(OUT, { recursive: true });
const fails = [];
const ok = (c, m) => { console.log((c ? '  ✓ ' : '  ✗ ') + m); if (!c) fails.push(m); };
const shot = async (p, n, full = false) => { await p.waitForTimeout(700); return p.screenshot({ path: path.join(OUT, n), fullPage: full }); };   // ko'rinish animatsiyasi tugasin

async function staff(br, uid, vw) {
  const ctx = await br.newContext({ viewport: vw || { width: 1440, height: 900 } });
  const p = await ctx.newPage();
  const errs = [];
  p.on('console', m => { if (m.type() === 'error' && !/favicon|status of 4\d\d/.test(m.text())) errs.push(m.text()); });
  p.on('pageerror', e => errs.push('pageerror: ' + e.message));
  const lg = await p.request.post(B + '/api/login', { data: { user_id: +uid, password: process.env.ADMIN_PW } });
  ok(lg.status() === 200, `Xodim #${uid} kirdi`);
  await p.goto(B + '/');
  await p.waitForFunction(() => typeof go === 'function' && typeof ME !== 'undefined' && ME, null, { timeout: 30000 });
  return { p, errs };
}

(async () => {
  const br = await chromium.launch({ executablePath: process.env.CHROME, headless: true });
  try {
    // 1) Bo'lim boshlig'i: Keyslar
    const { p, errs } = await staff(br, process.env.ADMIN_UID);
    await p.evaluate(() => go('ortda', { tab: 'keyslar' }));
    await p.waitForSelector('#orBox [data-ks]', { timeout: 30000 });
    ok(await p.isVisible('.dl-tabs [data-t="keyslar"][aria-selected="true"]'), 'Ortda qolganlar → «Keyslar» yorlig\'i');
    ok((await p.locator('#orBox tr').count()) > 1, 'Keyslar jadvali: talaba, nega, egasi, SLA, holat');
    await shot(p, 'keyslar_royxat.png');
    await p.locator('#orBox button[data-ks]').first().click();
    await p.waitForSelector('.dl-modal .ks-explain', { timeout: 20000 });
    ok(/qoida/.test(await p.textContent('.dl-modal .ks-explain')), 'Keys kartasi: «Nega keys ochildi» — qoida va raqamlar bilan');
    ok(await p.locator('.dl-modal select[data-k="outcome"]').count() > 0 || await p.locator('.dl-modal #ksTu').count() > 0, 'Natija (majburiy) va biriktirish shakllari');
    await p.waitForTimeout(600);
    await shot(p, 'keyslar_karta.png');
    // natijasiz yopishga urinish — ogohlantirish, keys yopilmaydi
    const cl = p.locator('.dl-modal [data-do="close"]');
    if (await cl.count()) { await cl.click(); await p.waitForTimeout(400); ok(await p.isVisible('.dl-modal'), 'Natijasiz yopish — rad etildi (oyna ochiq qoladi)'); }
    await p.keyboard.press('Escape');
    await p.evaluate(() => document.getElementById('toast')?.classList.add('hidden'));
    // Natija
    await p.evaluate(() => renderOrtda('natija'));
    await p.waitForSelector('#orBox .dl-kpi', { timeout: 20000 });
    ok(/SLA ichida/.test(await p.textContent('#orBox')), 'Natija: SLA ulushi, median bog\'lanish, qayta faollashish, tyutorlar jadvali');
    await shot(p, 'keyslar_natija.png', true);
    // Haftalik taqvim
    await p.evaluate(() => renderOrtda('taqvim'));
    await p.waitForSelector('#orBox [data-due], #orBox .dl-t', { timeout: 20000 });
    ok(/yakshanba|Muddat/.test(await p.textContent('#orBox')), 'Haftalik taqvim: chiqarilish va muddat');
    await shot(p, 'haftalik_taqvim.png');
    // Eslatmalar va tajriba
    await p.evaluate(() => renderOrtda('eslatmalar'));
    await p.waitForSelector('#orBox .ks-tr', { timeout: 20000 });
    ok((await p.locator('#orBox .ks-tr').count()) === 3, 'Eslatmalar: 3 ta to\'siq nuqtasi, rejim va taqqoslash');
    await shot(p, 'eslatmalar_tajriba.png', true);
    // telefon kengligi — keyslar
    await p.setViewportSize({ width: 390, height: 844 });
    await p.evaluate(() => renderOrtda('keyslar'));
    await p.waitForSelector('#orBox [data-ks]', { timeout: 20000 });
    const sw = await p.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    ok(sw <= 1, `Telefon kengligida gorizontal aylantirish yo'q (${sw}px)`);
    await shot(p, 'keyslar_telefon.png');
    ok(!errs.length, 'Konsolda xato yo\'q (bo\'lim)' + (errs.length ? ': ' + errs.slice(0, 3).join(' | ') : ''));
    // 2) Rektor: Nazorat markazi kartasi
    const R = await staff(br, process.env.REK_UID);
    await R.p.evaluate(() => go('nazorat'));
    await R.p.waitForSelector('.ks-nz', { timeout: 30000 });
    ok(/SLA ichida/.test(await R.p.textContent('.ks-nz')), 'Nazorat markazi: «Keyslar natijasi» kartasi');
    await shot(R.p, 'nazorat_keyslar.png');
    ok(!R.errs.length, 'Konsolda xato yo\'q (rektor)' + (R.errs.length ? ': ' + R.errs.slice(0, 3).join(' | ') : ''));
    // 3) Talaba kabineti «Bu hafta» (telefon)
    const sc = await br.newContext({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 2, isMobile: true, hasTouch: true });
    const sp = await sc.newPage();
    const serr = [];
    sp.on('pageerror', e => serr.push(e.message));
    const lg = await sp.request.post(B + '/api/talaba/login', { data: { hemis_id: process.env.TD_HEMIS, password: process.env.TD_PASS } });
    ok(lg.status() === 200, 'Talaba kirdi');
    await sp.goto(B + '/talaba#darslarim');
    await sp.waitForSelector('.tkd-c', { timeout: 30000 });
    const wk = await sp.locator('.tkd-week').count();
    ok(wk === 1 && /Muddat/.test(await sp.textContent('.tkd-week')), '«Bu hafta» bloki — darslar va muddatlar');
    const ssw = await sp.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    ok(ssw <= 1, `Kabinet: gorizontal aylantirish yo'q (${ssw}px)`);
    await shot(sp, 'kabinet_bu_hafta_telefon.png');
    await shot(sp, 'kabinet_bu_hafta_telefon_full.png', true);
    ok(!serr.length, 'Kabinet: sahifada xato yo\'q' + (serr.length ? ': ' + serr.slice(0, 2).join(' | ') : ''));
  } catch (e) {
    ok(false, 'Istisno: ' + e.message);
  } finally {
    await br.close();
  }
  console.log(`Skrinshotlar: ${OUT}`);
  process.exit(fails.length ? 1 : 0);
})();
