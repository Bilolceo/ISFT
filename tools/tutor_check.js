#!/usr/bin/env node
/* AI tutor (pilot) — brauzer tekshiruvi (tests/test_tutor.py chaqiradi).
 *   PW=/path/to/playwright-core CHROME=/path/to/chrome ISFT_TEST_URL=<server> TU_LAUNCH=<launch havola> TU_STAFF=<xodim id> TU_PW=<parol> TU_OUT=/tmp/tu
 * Telefon kengligi (390×844): launch → kurs pleyeri → «Savol berish» → javob va manba → manba havolasi darsning bo'limiga olib boradi →
 * bilimni tekshirish yonida «Yordam» → maslahat; gorizontal aylantirish yo'q, konsol xatosiz. Keyin keng ekranda «Ortda qolganlar» → «AI tutor». */
'use strict';
const fs = require('fs'), path = require('path');
const { chromium } = require(process.env.PW || 'playwright-core');
const B = process.env.ISFT_TEST_URL, OUT = process.env.TU_OUT || path.join(require('os').tmpdir(), 'isft_tutor');
fs.mkdirSync(OUT, { recursive: true });
const fails = [];
const ok = (c, m) => { console.log((c ? '  ✓ ' : '  ✗ ') + m); if (!c) fails.push(m); };
const shot = (p, n, full) => p.screenshot({ path: path.join(OUT, n), fullPage: !!full });

(async () => {
  const br = await chromium.launch({ executablePath: process.env.CHROME, headless: true });
  try {
    const ctx = await br.newContext({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 2, isMobile: true, hasTouch: true });
    const p = await ctx.newPage();
    const errs = [];
    p.on('console', m => { if (m.type() === 'error' && !/favicon|status of 4\d\d|youtube|ytimg/.test(m.text())) errs.push(m.text()); });
    p.on('pageerror', e => errs.push('pageerror: ' + e.message));
    p.on('dialog', d => d.accept("Javob to'liq emas"));
    await p.goto(process.env.TU_LAUNCH);
    await p.waitForSelector('.itu-fab', { timeout: 30000 });
    await p.waitForFunction(() => window.ISFTKurs && window.ISFTKurs.ready && window.ISFTTutor && window.ISFTTutor.ready, null, { timeout: 30000 });
    ok(await p.isVisible('.itu-fab'), "Pleyerda «Savol berish» tugmasi");
    await shot(p, 'tutor_pleyer_telefon.png');
    await p.click('.itu-fab');
    await p.waitForSelector('.itu-panel:not([hidden])', { timeout: 10000 });
    const box = await p.locator('.itu-panel').boundingBox();
    ok(box && box.width <= 390 && box.x >= 0, `Panel ekran kengligida (${box && Math.round(box.width)}px)`);
    await p.fill('.itu-f textarea', 'Inflyatsiya nima?');
    await p.click('.itu-send');
    await p.waitForSelector('.itu-javob .itu-cite', { timeout: 30000 });
    const ans = await p.textContent('.itu-javob p');
    ok(/narx/i.test(ans), `Javob: ${ans.slice(0, 70)}`);
    ok((await p.locator('.itu-javob .itu-cite').count()) >= 1, 'Manba havolasi (bo\'lim yorlig\'i)');
    ok(/Bugun qolgan savollar: \d+/.test(await p.textContent('.itu-q')), 'Kunlik qolgan savollar ko\'rsatiladi');
    const sw = await p.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    ok(sw <= 1, `Gorizontal aylantirish yo'q (${sw}px)`);
    await shot(p, 'tutor_javob_telefon.png');
    await p.click('[data-flag]');
    await p.waitForFunction(() => /Qabul qilindi/.test((document.querySelector('[data-flag]') || {}).textContent || ''), null, { timeout: 10000 });
    ok(true, 'Shikoyat tugmasi ishlaydi');
    await p.click('.itu-javob .itu-cite');
    await p.waitForFunction(() => /lesson=.+block=/.test(location.hash), null, { timeout: 10000 });
    ok(await p.isHidden('.itu-panel'), 'Manba bosilganda (telefon) panel yopiladi va dars bo\'limi ochiladi');
    await p.waitForTimeout(400);
    await shot(p, 'tutor_manba_bolim_telefon.png');
    // «Yordam» — bilimni tekshirish yonida
    await p.waitForSelector('.itu-help', { timeout: 15000 });
    await p.locator('.itu-help').first().scrollIntoViewIfNeeded();
    await shot(p, 'tutor_yordam_tugma_telefon.png');
    await p.locator('.itu-help').first().click();
    await p.waitForSelector('.itu-maslahat', { timeout: 30000 });
    const hint = await p.textContent('.itu-maslahat');
    ok(/Maslahat/.test(hint) && !/Narxlar umumiy darajasining barqaror oshishi/i.test(hint) && !/to'g'ri javob/i.test(hint), `«Yordam» → maslahat, javob aytilmadi: ${hint.slice(0, 80)}`);
    await shot(p, 'tutor_maslahat_telefon.png');
    ok(errs.length === 0, `Konsol xatosiz${errs.length ? ': ' + errs.slice(0, 3).join(' | ') : ''}`);
    await ctx.close();

    // Keng ekran: xodim — «Ortda qolganlar» → «AI tutor»
    const c2 = await br.newContext({ viewport: { width: 1366, height: 900 } });
    const s = await c2.newPage();
    const e2 = [];
    s.on('pageerror', e => e2.push('pageerror: ' + e.message));
    const lg = await s.request.post(B + '/api/login', { data: { user_id: +process.env.TU_STAFF, password: process.env.TU_PW } });
    ok(lg.status() === 200, 'Bo\'lim boshlig\'i kirdi');
    await s.goto(B + '/');
    await s.waitForFunction(() => typeof go === 'function' && typeof ME !== 'undefined' && ME, null, { timeout: 30000 });
    await s.evaluate(() => go('ortda', { tab: 'tutor' }));
    await s.waitForSelector('#tuBody .dl-kpis', { timeout: 30000 });
    ok(await s.isVisible('.dl-tabs [data-t="tutor"][aria-selected="true"]'), "«Ortda qolganlar» → «AI tutor» yorlig'i");
    ok((await s.locator('#orBox table').count()) >= 3, 'Pilotlar, taqqoslash, savollar va jurnal jadvallari');
    await shot(s, 'tutor_xodim_yorliq.png', true);
    ok(e2.length === 0, `Xodim sahifasi xatosiz${e2.length ? ': ' + e2.join(' | ') : ''}`);
    await c2.close();
  } catch (e) {
    ok(false, 'Istisno: ' + (e && e.message));
  } finally {
    await br.close();
  }
  process.exit(fails.length ? 1 : 0);
})();
