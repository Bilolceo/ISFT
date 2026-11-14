#!/usr/bin/env node
/* ISFT «Kurs muharriri» — muharrir sinovi (static/kurs.js) jonli serverga qarshi, brauzerda.
 *
 * Ishga tushirish (tests/test_kurs.py o'zi chaqiradi):
 *   PW=/path/to/node_modules/playwright-core CHROME=/path/to/chrome B=http://127.0.0.1:8000 KU_UID=<masofaviy user id> KU_PW=<parol>
 *   KU_CID=<kurs id> [KU_QCID=<sifat hisoboti skrinshoti uchun kurs id>] OUT=/tmp/kurs node tools/kurs_editor_check.js
 *
 * Tekshiradi: kurslar ro'yxati, kurs ochilishi (darslar, bloklar), «+» → blok kutubxonasi → yangi blok, joyida yozish va avtosaqlash (server
 * holati bilan solishtiriladi), o'ng panel sozlamasi, o'chirish → «Bekor qilish», ↑ ↓ ko'chirish, klaviatura bilan ko'chirish (Alt+↑/↓ — blok va dars, aria-live), ziddiyat (boshqa joyda saqlangan rev → 409 →
 * ogohlantirish va «Oxirgi holatni yuklash»), ko'rish oynasi (pleyer iframe'da, telefon kengligi), sifat hisoboti, telefon kengligida gorizontal
 * aylantirish yo'qligi, konsol xatolari yo'qligi. Natija: "  ✓ …" / "  ✗ …"; xato bo'lsa chiqish kodi 1. Skrinshotlar: $OUT.
 */
'use strict';
const fs = require('fs'), path = require('path');
const { chromium } = require(process.env.PW || 'playwright-core');
const B = process.env.B, OUT = process.env.OUT || path.join(require('os').tmpdir(), 'isft_kurs_editor');
const CID = +process.env.KU_CID, QCID = +(process.env.KU_QCID || 0);
fs.mkdirSync(OUT, { recursive: true });
const fails = [];
const ok = (c, m) => { console.log((c ? '  ✓ ' : '  ✗ ') + m); if (!c) fails.push(m); };
const sleep = ms => new Promise(r => setTimeout(r, ms));

(async () => {
  const br = await chromium.launch({ executablePath: process.env.CHROME, headless: true });
  const ctx = await br.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await ctx.newPage();
  const errs = [];
  page.on('console', m => { if (m.type() === 'error' && !/favicon|status of 409/.test(m.text())) errs.push(m.text()); });   // 409 — ataylab chaqirilgan ziddiyat
  page.on('pageerror', e => errs.push('pageerror: ' + e.message));
  const api = async (url, body) => { const r = body === undefined ? await page.request.get(B + url) : await page.request.post(B + url, { data: body }); return { status: r.status(), data: await r.json().catch(() => ({})) }; };
  try {
    const lg = await page.request.post(B + '/api/login', { data: { user_id: +process.env.KU_UID, password: process.env.KU_PW } });
    ok(lg.status() === 200, 'Kirish (masofaviy ta\'lim bo\'limi)');
    await page.goto(B + '/');
    await page.waitForFunction(() => typeof go === 'function' && typeof ME !== 'undefined' && ME && typeof renderKurs === 'function');
    ok(await page.isVisible('#nav a[data-v="kurs"]'), 'Menyuda «Kurs muharriri» bandi');
    await page.evaluate(() => go('kurs'));
    await page.waitForSelector('.ku-cards .ku-card', { timeout: 15000 });
    ok((await page.$$('.ku-card')).length >= 1, 'Kurslar ro\'yxati (kartochkalar)');
    await page.click(`.ku-card[data-open="${CID}"]`);
    await page.waitForSelector('#kuBlocks .ku-blk', { timeout: 15000 });
    const co = (await api(`/api/kurs/courses/${CID}`)).data;
    ok((await page.$$('#kuLs li')).length === co.lessons_list.length, `Darslar ro'yxati (${co.lessons_list.length} ta)`);
    const lid = co.lessons_list[0].id;
    let L = (await api(`/api/kurs/lessons/${lid}`)).data;
    ok((await page.$$('#kuBlocks .ku-blk')).length === L.blocks.length, `Dars bloklari (${L.blocks.length} ta) va «+» tugmalari (${(await page.$$('#kuBlocks .ku-ins')).length} ta)`);
    await page.screenshot({ path: path.join(OUT, 'kurs-editor.png') });

    // blok kutubxonasi → yangi «Matn» bloki (2-o'ringa)
    await page.click('#kuBlocks .ku-ins:nth-of-type(2) button').catch(async () => { await (await page.$$('#kuBlocks .ku-ins button'))[1].click(); });
    await page.waitForSelector('.ku-tile');
    const tiles = await page.$$eval('.ku-tile', x => x.map(t => t.dataset.t));
    ok(tiles.length >= 23 && ['accordion', 'flashcards', 'knowledge', 'continue', 'labeled_graphic', 'sorting', 'matching', 'table', 'video'].every(t => tiles.includes(t)), `Blok kutubxonasi: ${tiles.length} tur, toifalar bo'yicha`);
    await page.fill('#kuLibQ', 'kartoch');
    ok((await page.$$eval('.ku-tile', x => x.filter(t => !t.hidden).map(t => t.dataset.t))).join() === 'flashcards', 'Kutubxonada qidiruv («kartoch» → Kartochkalar)');
    await page.fill('#kuLibQ', '');
    await page.screenshot({ path: path.join(OUT, 'kurs-library.png') });
    await page.click('.ku-tile[data-t="paragraph"]');
    await page.waitForSelector('#kuBlocks .ku-blk.sel [data-rich]');
    const MARK = 'Avtosaqlash sinovi ' + Date.now();
    await page.click('#kuBlocks .ku-blk.sel [data-rich]');
    await page.keyboard.type(MARK);
    await page.waitForFunction(() => /Saqlandi/.test(document.querySelector('#kuSave')?.textContent || ''), null, { timeout: 10000 });
    L = (await api(`/api/kurs/lessons/${lid}`)).data;
    const ins = L.blocks.findIndex(b => b.type === 'paragraph' && (b.data.html || '').includes(MARK));
    ok(ins >= 0, `Yangi blok joyida yozildi va avtosaqlandi (serverda ${ins + 1}-blok)`);

    // o'ng panel: rasm bloki joylashuvi
    const imgI = L.blocks.findIndex(b => b.type === 'image');
    if (imgI >= 0) {
      await page.click(`#kuBlocks [data-bi="${imgI}"] [data-act="gear"]`);
      await page.waitForSelector('#kuPanel [data-k="layout"]');
      await page.selectOption('#kuPanel [data-k="layout"]', 'full');
      await page.waitForFunction(() => /Saqlandi/.test(document.querySelector('#kuSave')?.textContent || ''), null, { timeout: 10000 });
      await sleep(200);
      const L2 = (await api(`/api/kurs/lessons/${lid}`)).data;
      ok(L2.blocks[imgI].data.layout === 'full', 'O\'ng panel: rasm joylashuvi «To\'liq kenglik» — saqlandi');
      await page.selectOption('#kuPanel [data-k="layout"]', 'centered');
      L = L2;
    }
    // ko'chirish va o'chirish → bekor qilish
    const curIns = await page.$$eval('#kuBlocks .ku-blk', (x, mark) => x.findIndex(e => [...e.querySelectorAll('[data-rich]')].some(r => r.textContent.includes(mark))), MARK);
    await page.click(`#kuBlocks [data-bi="${curIns}"] [data-act="down"]`);
    await sleep(200);
    ok(((await page.textContent(`#kuBlocks [data-bi="${curIns + 1}"]`)) || '').includes(MARK), '↓ tugmasi bilan blok pastga ko\'chdi');
    // klaviatura: blok tutqichi fokusda — Alt+↑ / Alt+↓ (fokus ko'chgan blokda qoladi, aria-live xabari)
    await page.focus(`#kuBlocks [data-bi="${curIns + 1}"] .ku-grip`);
    await page.keyboard.press('Alt+ArrowUp');
    await sleep(150);
    ok(((await page.textContent(`#kuBlocks [data-bi="${curIns}"]`)) || '').includes(MARK)
       && await page.evaluate(i => document.activeElement === document.querySelector(`#kuBlocks [data-bi="${i}"] .ku-grip`), curIns)
       && new RegExp(`${curIns + 1}-o'ringa ko'chirildi`).test(await page.textContent('#kuLive')),
       'Alt+↑ (klaviatura): blok yuqoriga ko\'chdi, fokus o\'sha blokda, ekran o\'quvchisiga yangi o\'rni aytildi');
    await page.keyboard.press('Alt+ArrowDown');
    await sleep(150);
    ok(((await page.textContent(`#kuBlocks [data-bi="${curIns + 1}"]`)) || '').includes(MARK), 'Alt+↓ (klaviatura): blok pastga qaytdi');
    const rich = `#kuBlocks [data-bi="${curIns + 1}"] [data-rich]`;
    await page.focus(rich); await page.keyboard.press('Alt+ArrowUp'); await sleep(150);
    ok(((await page.textContent(`#kuBlocks [data-bi="${curIns + 1}"]`)) || '').includes(MARK), 'Matn maydonida Alt+↑ blokni ko\'chirmaydi (kursor uchun)');
    ok(await page.$eval(`#kuBlocks [data-bi="${curIns + 1}"] .ku-grip`, g => g.tabIndex === 0 && g.getAttribute('role') === 'button' && /Alt/.test(g.getAttribute('aria-label') || '')),
       'Blok tutqichi klaviaturadan fokuslanadi (role=button, Alt + ↑/↓ izohi)');
    // darslar: fokusdagi dars Alt+↓ / Alt+↑ bilan ko'chadi (server tartibi bilan solishtiriladi)
    const ord0 = (await api(`/api/kurs/courses/${CID}`)).data.lessons_list.map(l => l.id);
    if (ord0.length >= 2) {
      await page.focus(`#kuLs [data-go="${ord0[0]}"]`);
      await page.keyboard.press('Alt+ArrowDown');
      await page.waitForFunction(id => document.querySelector('#kuLs li:nth-child(2) [data-go]')?.dataset.go === String(id), ord0[0], { timeout: 10000 });
      await sleep(150);   // aria-live matni qisqa kechikish bilan yoziladi (ekran o'quvchisi o'zgarishni sezishi uchun)
      const ord1 = (await api(`/api/kurs/courses/${CID}`)).data.lessons_list.map(l => l.id);
      ok(ord1[1] === ord0[0] && ord1[0] === ord0[1] && await page.evaluate(id => document.activeElement?.dataset.go === String(id), ord0[0])
         && /2-o'ringa ko'chirildi/.test(await page.textContent('#kuLive')), 'Alt+↓ (klaviatura): dars 2-o\'ringa ko\'chdi (serverda), fokus o\'sha darsda, aria-live xabari');
      await page.keyboard.press('Alt+ArrowUp');
      await page.waitForFunction(id => document.querySelector('#kuLs li:nth-child(1) [data-go]')?.dataset.go === String(id), ord0[0], { timeout: 10000 });
      ok(JSON.stringify((await api(`/api/kurs/courses/${CID}`)).data.lessons_list.map(l => l.id)) === JSON.stringify(ord0), 'Alt+↑ (klaviatura): dars joyiga qaytdi');
    }
    await page.click(`#kuBlocks [data-bi="${curIns + 1}"] [data-act="del"]`);
    await page.waitForSelector('#kuUndo button');
    ok(!((await page.textContent('#kuBlocks')) || '').includes(MARK), 'Blok o\'chirildi, «Bekor qilish» tugmasi chiqdi');
    await page.click('#kuUndo button');
    await sleep(300);
    ok(((await page.textContent('#kuBlocks')) || '').includes(MARK), '«Bekor qilish» — blok qaytdi');
    await page.waitForFunction(() => /Saqlandi/.test(document.querySelector('#kuSave')?.textContent || ''), null, { timeout: 10000 });

    // ziddiyat: boshqa joyda saqlash → bu oynada 409
    L = (await api(`/api/kurs/lessons/${lid}`)).data;
    const other = await api(`/api/kurs/lessons/${lid}`, { rev: L.rev, title: L.title, blocks: L.blocks.map(b => ({ id: b.id, type: b.type, data: b.data })) });
    ok(other.status === 200, 'Boshqa oynada saqlandi (rev oshdi)');
    await page.click('#kuLt'); await page.keyboard.press('End'); await page.keyboard.type(' ');
    await page.waitForSelector('#kuNote .ku-warn.bad', { timeout: 10000 });
    ok(/Ziddiyat/.test(await page.textContent('#kuSave')) && (await page.isVisible('#kuCfL')), 'Ziddiyat: ogohlantirish va «Oxirgi holatni yuklash / Mening nusxamni saqlash»');
    await page.click('#kuCfL');
    await page.waitForFunction(() => /Saqlandi/.test(document.querySelector('#kuSave')?.textContent || '') && !document.querySelector('#kuNote .ku-warn.bad'), null, { timeout: 10000 });
    ok(true, 'Oxirgi holat yuklandi — ziddiyat yopildi');
    // tozalash: sinov bloki o'chiriladi
    L = (await api(`/api/kurs/lessons/${lid}`)).data;
    await api(`/api/kurs/lessons/${lid}`, { rev: L.rev, title: L.title.trim(), blocks: L.blocks.filter(b => !(b.data.html || '').includes(MARK)).map(b => ({ id: b.id, type: b.type, data: b.data })) });
    await page.evaluate(lid => kuLoadLesson(lid, true), lid);
    await sleep(400);

    // ko'rish oynasi
    await page.click('#kuPv');
    await page.waitForSelector('#kuPvF');
    const fr = await (await page.$('#kuPvF')).contentFrame();
    await fr.waitForFunction(t => document.body && document.body.innerText.includes(t), co.title.slice(0, 20), { timeout: 20000 }).catch(() => {});
    ok((await fr.evaluate(() => document.body.innerText)).includes(co.title.slice(0, 20)), 'Ko\'rish: pleyer iframe ichida kursni ko\'rsatdi');
    await page.click('.ku-pvbar [data-w="390px"]');
    await sleep(500);
    ok(Math.round((await (await page.$('#kuPvF')).boundingBox()).width) === 390, 'Ko\'rish: telefon kengligi (390px)');
    await page.screenshot({ path: path.join(OUT, 'kurs-preview.png') });
    await page.keyboard.press('Escape');

    // sifat hisoboti
    if (QCID) { await page.evaluate(cid => kuOpen(cid), QCID); await page.waitForSelector('#kuBlocks'); }
    await page.click('#kuQl');
    await page.waitForSelector('.ku-qis li');
    ok((await page.$$('.ku-qis li')).length >= 1 && (await page.$$('.ku-kpi')).length >= 6, 'Sifat hisoboti: ko\'rsatkichlar va muammolar ro\'yxati');
    await page.screenshot({ path: path.join(OUT, 'kurs-quality.png') });
    await page.keyboard.press('Escape');

    // telefon kengligi
    await page.setViewportSize({ width: 390, height: 844 });
    await sleep(400);
    ok(await page.evaluate(() => document.documentElement.scrollWidth <= 392), 'Telefon kengligida (390px) gorizontal aylantirish yo\'q');
    await page.screenshot({ path: path.join(OUT, 'kurs-editor-phone.png') });
    ok(errs.length === 0, `Konsolda xato yo'q${errs.length ? ': ' + errs.slice(0, 3).join(' | ') : ''}`);
  } catch (e) {
    ok(false, 'Istisno: ' + (e && e.message || e).toString().split('\n')[0]);
    await page.screenshot({ path: path.join(OUT, 'kurs-editor-xato.png') }).catch(() => {});
  }
  await br.close();
  console.log(fails.length ? `\nXATO: ${fails.length}` : '\nMuharrir sinovi: hammasi o\'tdi');
  process.exit(fails.length ? 1 : 0);
})();
