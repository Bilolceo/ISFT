#!/usr/bin/env node
/* ISFT «Dars tayyorlash» — birlashgan ekran va izohlar paneli (static/dars.js, static/kurs.js) jonli serverga qarshi, brauzerda.
 *
 * Ishga tushirish (tests/test_dars.py o'zi chaqiradi):
 *   PW=/path/to/playwright-core CHROME=/path/to/chrome B=http://127.0.0.1:8000 DS_UID=<masofaviy> DS_PW=<parol> DS_CID=<fan id> DS_KCID=<muharrir kursi id>
 *   OUT=/tmp/dars node tools/dars_check.js
 *
 * Tekshiradi: menyuda bitta «Dars tayyorlash» bandi; «Fanlar» → fan → NEXTID darslar to'ri (L/A kodlari, holat belgilari, ikki amal);
 * telefon kengligida gorizontal aylantirish yo'q; «Muharrirda tahrirlash» → muharrir (menyuda «Dars tayyorlash» belgilangan, bog'lanish
 * tasmasi); blok sarlavhasidagi izoh belgisi → izohlar paneli → izoh qoldirish (to'xtatuvchi), javob, hal qilish; konsol xatolari yo'qligi.
 * Natija: "  ✓ …" / "  ✗ …"; xato bo'lsa chiqish kodi 1. Skrinshotlar: $OUT.
 */
'use strict';
const fs = require('fs'), path = require('path');
const { chromium } = require(process.env.PW || 'playwright-core');
const B = process.env.B, OUT = process.env.OUT || path.join(require('os').tmpdir(), 'isft_dars');
const CID = +process.env.DS_CID, KCID = +process.env.DS_KCID;
fs.mkdirSync(OUT, { recursive: true });
const fails = [];
const ok = (c, m) => { console.log((c ? '  ✓ ' : '  ✗ ') + m); if (!c) fails.push(m); };

(async () => {
  const br = await chromium.launch({ executablePath: process.env.CHROME, headless: true });
  const ctx = await br.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await ctx.newPage();
  /* bu tekshiruv klassik muharrir (3 ustun) va B versiya (avtomatik yig'ish + muharrir) oqimini tekshiradi; Rise ko'rinishi va Konstruktor (A) — tools/konstruktor_check.js */
  await page.addInitScript(() => { try { localStorage.setItem('kuUi', 'classic'); localStorage.setItem('dsVer', 'b'); } catch (e) {} });
  const errs = [];
  page.on('console', m => { if (m.type() === 'error' && !/favicon/.test(m.text())) errs.push(m.text()); });
  page.on('pageerror', e => errs.push('pageerror: ' + e.message));
  const api = async url => { const r = await page.request.get(B + url); return r.json().catch(() => ({})); };
  try {
    const lg = await page.request.post(B + '/api/login', { data: { user_id: +process.env.DS_UID, password: process.env.DS_PW } });
    ok(lg.status() === 200, 'Kirish (Masofaviy ta\'lim bo\'limi)');
    await page.goto(B + '/');
    await page.waitForFunction(() => typeof go === 'function' && typeof ME !== 'undefined' && ME && typeof dsSubjects === 'function');
    ok(await page.isVisible('#nav a[data-v="paket"]') && !(await page.$('#nav a[data-v="kurs"]')), 'Menyuda bitta «Dars tayyorlash» bandi (alohida «Kurs muharriri» yo\'q)');
    await page.evaluate(() => go('paket'));
    await page.waitForSelector('.ds-subj .ds-sc', { timeout: 20000 });
    ok(await page.$eval('.pk-tabs button.on', b => b.textContent.trim()) === 'Fanlar', 'Kirish sahifasi — «Fanlar» yorlig\'i');
    await page.screenshot({ path: path.join(OUT, 'dars-fanlar.png') });
    // Fanlar: kurs → ta'lim yo'nalishi → fan (ichma-ich); fan kodi «<kurs>_<YO'NALISH>_<fan>»
    ok(await page.$$eval('.ds-subj [data-kurs]', e => e.map(x => x.dataset.kurs).join(',')) === '1,2,3,4' && /Barcha kurslar/.test(await page.textContent('.ds-crumbs')), 'Fanlar 1-qadam: faqat kurslar (1, 2, 3, 4) tanlanadi');
    await page.click('.ds-subj [data-kurs="2"]'); await page.waitForSelector('.ds-subj [data-dir]');
    const nDir = await page.$$eval('.ds-subj [data-dir]', e => e.length);
    ok(nDir >= 2 && (await page.$$('.ds-subj [data-cid]')).length === 0 && /2-kurs/.test(await page.textContent('.ds-crumbs')), `Fanlar 2-qadam: 2-kurs — ta'lim yo'nalishlari (${nDir} ta), fanlar hali yo'q`);
    await page.screenshot({ path: path.join(OUT, 'dars-fanlar-yonalish.png') });
    await page.click('.ds-subj [data-dir]'); await page.waitForSelector('.ds-subj [data-cid]');
    const cc = await page.$$eval('.ds-subj .ds-sc .ds-code-s', e => e.map(x => x.textContent.trim()));
    ok(cc.length >= 1 && cc.every(x => /^2_[A-Z0-9]{2,6}_[a-z0-9]+$/.test(x)) && new Set(cc).size === cc.length, `Fanlar 3-qadam: fan kodlari «kurs_YO'NALISH_fan» (${cc.slice(0, 2).join(', ')}) va takrorlanmaydi`);
    await page.screenshot({ path: path.join(OUT, 'dars-fanlar-fan.png') });
    await page.click('.ds-crumbs [data-lv="1"]'); await page.waitForSelector('.ds-subj [data-dir]');
    await page.click('.ds-crumbs [data-lv="0"]'); await page.waitForSelector('.ds-subj [data-kurs]');
    ok(true, 'Fanlar: yo\'l tasmasi orqali orqaga qaytish (kurs, barcha kurslar)');
    await page.fill('#dsQ', 'ATT'); await page.waitForSelector('.ds-subj [data-cid]:not([data-kurs])', { timeout: 10000 });
    ok((await page.$$('.ds-subj [data-kurs]')).length === 0 && (await page.$$('.ds-subj [data-cid]')).length >= 1, 'Qidiruv (kod bo\'yicha): tekis natijalar ro\'yxati');
    await page.fill('#dsQ', ''); await page.waitForSelector('.ds-subj [data-kurs]', { timeout: 10000 });
    await page.evaluate(cid => dsOpenSubject(cid), CID);
    await page.waitForSelector('.ds-grid .ds-l', { timeout: 20000 });
    const codes = await page.$$eval('.ds-l .ds-code', x => x.map(e => e.textContent.trim()));
    ok(codes[0] === 'L1' && codes.length >= 2, `Fan: NEXTID darslar to'ri (${codes.length} dars: ${codes.slice(0, 4).join(', ')} …)`);
    const row = await page.$eval('.ds-l[data-key="1"]', li => ({ st: li.querySelectorAll('.ds-st').length, build: !!li.querySelector('[data-build]'), ku: !!li.querySelector('[data-ku],[data-conv]'), src: !!li.querySelector('[data-auth]') }));
    ok(row.st === 3 && row.build && row.ku && row.src, 'Har darsda holat (material, video, paket/eksport), «Avtomatik yig\'ish (shablon)», «Muharrirda tahrirlash», eksport manbai');
    const chips = await page.$$eval('.ds-l[data-key="1"] .ds-st', es => es.map(e => e.textContent.replace(/[✓–]/g, '').trim()));
    ok(chips.join('|') === 'Material|Video|Paket', `Holat belgilari bir xil atamada: Material | Video | Paket (${chips.join(' | ')})`);
    ok(await page.$$eval('.ds-grid .ds-l b.ds-un', es => es.every(e => e.textContent === 'Mavzu nomi kiritilmagan')) && await page.$eval('.ds-grid', g => !/(^|\s)\d+-mavzu(\s|$)/.test(g.textContent.replace(/Mavzu nomi kiritilmagan/g, ''))), "Nomi kiritilmagan darslar — «Mavzu nomi kiritilmagan» (o'rinbosar «2-mavzu» emas)");
    ok(await page.$eval('#dsBulkUp', b => /Ko'p faylni yuklash/.test(b.textContent)) && await page.$eval('.ds-l[data-key="1"] [data-ku],.ds-l[data-key="1"] [data-conv]', b => getComputedStyle(b).backgroundColor !== 'rgb(120, 55, 168)'), "B versiya: «Ko'p faylni yuklash» bor; asosiy tugma qizil (binafsha faqat Konstruktorda)");
    ok(await page.isVisible('#dsSkel') && await page.isVisible('#dsApply') && await page.isVisible('#dsBulk') && await page.isVisible('#dsTpl'), 'Fan asboblari: skelet, shablonni qo\'llash, ommaviy yig\'ish, kafedra shabloni');
    await page.screenshot({ path: path.join(OUT, 'dars-fan-tori.png'), fullPage: true });
    // shablonni qo'llash — oldin farq
    await page.click('#dsApply');
    await page.waitForSelector('#dsAr .ds-kpis', { timeout: 15000 });
    ok(await page.isVisible('#dsAr .ds-kpis'), '«Shablonni qo\'llash» — oldin farq va sonlar ko\'rsatiladi');
    await page.screenshot({ path: path.join(OUT, 'dars-shablon-farq.png') });
    await page.click('.pk-modal [data-x]');
    // telefon kengligi
    await page.setViewportSize({ width: 390, height: 844 });
    await page.waitForTimeout(300);
    const ov = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    ok(ov <= 1, `Telefon kengligi (390px): gorizontal aylantirish yo'q (${ov}px)`);
    await page.screenshot({ path: path.join(OUT, 'dars-fan-telefon.png'), fullPage: true });
    await page.setViewportSize({ width: 1440, height: 900 });
    // muharrir
    await page.click(`[data-ku="${KCID}"]`);
    await page.waitForSelector('#kuBlocks .ku-blk', { timeout: 20000 });
    ok(await page.$eval('#nav a[data-v="paket"]', a => a.classList.contains('on')), 'Muharrir ochildi — menyuda «Dars tayyorlash» belgilangan (taxallus)');
    const lnk = await page.$eval('.ku-link', e => e.textContent).catch(() => '');
    ok(/L1/.test(lnk) && /ustun manba/.test(lnk), 'Muharrirda bog\'lanish tasmasi: dars kodi va eksport uchun ustun manba');
    await page.waitForFunction(() => KU.cm !== null, null, { timeout: 10000 });
    const before = (await api(`/api/dars/kurs/${KCID}/comments`)).open;
    await page.click('#kuBlocks .ku-blk:nth-of-type(2) .ku-cmb').catch(async () => { await (await page.$$('#kuBlocks .ku-blk .ku-cmb'))[1].click(); });
    await page.waitForSelector('#kuCm:not([hidden]) #kuCmT', { timeout: 10000 });
    ok(await page.isVisible('#kuCm'), 'Blok izoh belgisi → izohlar paneli ochildi');
    await page.fill('#kuCmT', 'Brauzer sinovi: rasm izohini aniqlashtiring');
    await page.check('#kuCmB');
    await page.click('#kuCmS');
    await page.waitForFunction(n => KU.cm && KU.cm.open === n + 1, before, { timeout: 10000 });
    const after = await api(`/api/dars/kurs/${KCID}/comments`);
    ok(after.open === before + 1 && after.items.some(t => t.text.startsWith('Brauzer sinovi') && t.blocking), 'Izoh qoldirildi (to\'xtatuvchi) — serverda bor');
    const badge = await page.$$eval('#kuBlocks .ku-cmb.on', x => x.length);
    ok(badge >= 1 && /Izohlar\s*\d/.test(await page.$eval('#kuCmBtn', b => b.textContent)), `Blok belgilari va «Izohlar» tugmasida son (${badge} ta blokda)`);
    const tid = after.items.find(t => t.text.startsWith('Brauzer sinovi')).id;
    await page.fill(`[data-rp="${tid}"]`, 'Javob: tuzatildi');
    await page.click(`[data-rps="${tid}"]`);
    await page.waitForFunction(id => KU.cm.items.find(t => t.id === id)?.replies.length === 1, tid, { timeout: 10000 });
    ok(true, 'Tarmoqda javob yozildi');
    await page.screenshot({ path: path.join(OUT, 'dars-izohlar-panel.png') });
    await page.click(`[data-res="${tid}"]`);
    await page.waitForFunction(id => KU.cm.items.find(t => t.id === id)?.status === 'hal' || !KU.cm.items.find(t => t.id === id && t.status === 'ochiq'), tid, { timeout: 10000 });
    ok((await api(`/api/dars/kurs/${KCID}/comments`)).items.find(t => t.id === tid).status === 'hal', 'Izoh «hal qilindi» (serverda)');
    // telefon: izohlar paneli
    await page.setViewportSize({ width: 390, height: 844 });
    await page.waitForTimeout(300);
    ok(await page.evaluate(() => document.querySelector('#kuCm').getBoundingClientRect().right <= window.innerWidth + 1), 'Telefon kengligida izohlar paneli ekrandan chiqmaydi');
    await page.screenshot({ path: path.join(OUT, 'dars-izohlar-telefon.png') });
    ok(!errs.length, 'Konsolda xato yo\'q' + (errs.length ? ': ' + errs.slice(0, 3).join(' | ') : ''));
  } catch (e) {
    ok(false, 'Kutilmagan xato: ' + (e && e.message || e));
    await page.screenshot({ path: path.join(OUT, 'dars-xato.png') }).catch(() => {});
  } finally {
    await br.close();
  }
  process.exit(fails.length ? 1 : 0);
})();
