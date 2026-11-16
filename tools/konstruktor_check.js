#!/usr/bin/env node
/* Konstruktor (A versiya, static/konstruktor.js) va muharrirning «Rise ko'rinishi» (static/kurs.js .ku-rise) — brauzer tekshiruvi.
   tests/test_konstruktor.py chaqiradi: B (server), KX_UID, KX_PW, KX_CID (dl kurs), KX_KEY (dars kaliti), KX_TEST (✅ test .docx yo'li), OUT (skrinshotlar).
   Oqim: fan → «A — Konstruktor» → dars → materiallar (kartochkalar, test yuklash) → «Darsni yig'ish» → Rise muharriri (qadamlar tasmasi, muqova,
   tez qo'shish paneli, blok asboblari, sozlamalar paneli, yagona «Tayyor» tugmasi va uning oynasi, ko'rish — qurilma almashtirgichi, eskizli blok kutubxonasi,
   ixcham telefon paneli, ↑ ↓ bilan ko'chirish) → «Materiallar»ga qaytish; 390 px — gorizontal siljish yo'q. */
const { chromium } = require(process.env.PW || 'playwright-core');
const fs = require('fs');
const path = require('path');
const B = process.env.B, OUT = process.env.OUT || '/tmp/kx';
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
      await page.addInitScript(() => { try { localStorage.setItem('dsVer', 'a'); localStorage.removeItem('kuUi'); } catch (e) {} });
      const lg = await page.request.post(B + '/api/login', { data: { user_id: +process.env.KX_UID, password: process.env.KX_PW } });
      if (!lg.ok()) throw new Error('login ' + lg.status());
      await page.goto(B + '/'); await sleep(1200);
      await page.evaluate(cid => { DS.cid = cid; DS.data = null; go('paket', {tab: 'fanlar'}); }, +process.env.KX_CID);
      await page.waitForSelector('[data-kx]', { timeout: 20000 });
      if (tag === 'd') {
        ok(await page.isVisible('.ds-ver button[data-ver="a"].on'), "Fan sahifasi: «Ko'rinish: A — Konstruktor» tanlangan, B versiya tugmasi bor");
        ok(!(await page.$('[data-build]')) && (await page.$$('[data-kx]')).length > 0, "A versiyada har darsda bitta tugma (avtomatik yig'ish / muharrir tugmalari yo'q)");
      }
      await sleep(600); await require('./kx_materials_assert').subject(page, ok, tag);   /* fan sahifasi: rang, 3 qadamli tayyorlik, nomi yo'q darslar */
      await page.evaluate(() => window.scrollTo(0, 700)); await sleep(200);   /* «Namuna» tasmasi qirqilmasligini tekshirish uchun: ro'yxat pastda turganda ochiladi */
      await page.click(`[data-kx="${process.env.KX_KEY}"]`);
      await page.waitForSelector('.kx-grid', { timeout: 20000 });
      const cards = await page.$$eval('.kx-card', e => e.map(x => x.dataset.slot));
      ok(JSON.stringify(cards) === JSON.stringify(['video', 'text', 'slides', 'test']), `Materiallar: 4 kartochka — video, ma'ruza, taqdimot, test (${cards})`);
      ok(await page.isVisible('.kx-steps li.on') && (await page.textContent('.kx-steps li.on')).includes('Materiallar'), "Qadamlar: 1 — Materiallar (joriy)");
      ok(await page.isVisible('#kxDrop'), "Umumiy tashlash maydoni bor");
      await require('./kx_materials_assert').materials(page, ok, tag, B, process.env);   /* rang, «Namuna» tasmasi, kartochkalar, avtomatik subtitr */
      const hs = () => page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1);
      if (tag === 'm') ok(!(await hs()), "390 px: materiallar sahifasida gorizontal siljish yo'q");
      if (process.env.KX_TEST) {   /* ---- «To'g'ri javobni tanlang» (javobi ✅ topilmagan savollar): oyna, tekshiruv, bir nechta javob, o'tkazib yuborish */
        const quizN = () => page.evaluate(async ([cid, key]) => { const d = await (await fetch(`/api/paket/courses/${cid}/topics/${key}`, { credentials: 'same-origin' })).json(); return d.ready.quiz; }, [+process.env.KX_CID, +process.env.KX_KEY]);
        const modal = () => page.$('.pk-modal-bg.ta-bg');
        const inModal = () => page.evaluate(() => !!document.activeElement && !!document.activeElement.closest('.ta-bg'));
        if (tag === 'd') {
          await page.setInputFiles('[data-kx-up="test"]', process.env.KX_TEST);
          await page.waitForSelector('.ta-bg .ta-q', { timeout: 30000 }); await sleep(200);
          ok(await page.$eval('.ta-bg .pk-modal', e => e.getAttribute('role') === 'dialog' && e.getAttribute('aria-modal') === 'true' && /Javobi belgilanmagan savollar \(1 ta\)/.test(e.querySelector('h3').textContent)),
            "Test yuklandi — «Javobi belgilanmagan savollar (1 ta)» oynasi ochildi (role=dialog, aria-modal)");
          ok(/4 ta savol qo'shildi, 1 tasi javobsiz — hozir tanlang/.test(await page.textContent('.ta-sum')), "Sarlavha ostida aniq hisob: «4 ta savol qo'shildi, 1 tasi javobsiz — hozir tanlang»");
          ok((await page.$$('.ta-q')).length === 1 && (await page.$$('.ta-q input[type=radio]')).length === 4 && await inModal(), "Savol 4 ta variant (radio) bilan; fokus oyna ichida");
          ok(await page.$eval('.ta-q .ta-stem', e => /^4\.\s/.test(e.textContent.trim())) && await page.isVisible('.ta-q [data-skip]') && await page.isVisible('.ta-q [data-multi]'), "Savol raqami (4.), «O'tkazib yuborish» va «Bir nechta javob» bor");
          await page.keyboard.press('Escape'); await sleep(150);
          ok(!(await modal()), "Esc — oyna yopildi (savollar serverda kutib turadi)");
          const q1 = await quizN();
          ok(q1.pending === 1 && q1.approved === 4, `Test bankda 4 ta savol, 1 tasi kutmoqda (pending=${q1.pending}, approved=${q1.approved})`);
          ok(/1 ta savol javobsiz/.test(await page.textContent('[data-slot="test"] .kx-warn')) && await page.isVisible('#kxTa'), "Kartochkada «1 ta savol javobsiz» va «To'g'ri javobni tanlang (1)» tugmasi");
          await page.screenshot({ path: `${OUT}/${tag}_3a_test_kartochka.png` });
          await page.click('#kxTa'); await page.waitForSelector('.ta-bg .ta-q');
          await page.click('.pk-modal [data-ok]'); await sleep(150);
          ok(await page.isVisible('.ta-bg') && (await page.textContent('.ta-q .ta-err')).includes("To'g'ri javobni belgilang"), "Javob tanlanmasdan «Hammasini saqlash» — oyna ochiq qoladi, savol ostida xato matni");
          await page.check('.ta-q [data-multi]');
          ok(await page.$$eval('.ta-q .ta-opts input', e => e.every(x => x.type === 'checkbox')), "«Bir nechta javob» — variantlar belgilash katakchasiga aylandi");
          await page.check('.ta-q .ta-opts label:nth-child(1) input'); await page.check('.ta-q .ta-opts label:nth-child(3) input');
          ok(/1 ta savolga javob tanlandi/.test(await page.textContent('#taSt')), "Holat qatori (aria-live): «1 ta savolga javob tanlandi…»");
          await page.screenshot({ path: `${OUT}/${tag}_3_javob_oynasi.png` });
          await page.click('.pk-modal [data-ok]');
          await page.waitForFunction(() => !document.querySelector('.ta-bg'), null, { timeout: 15000 }); await sleep(600);
          const q2 = await quizN();
          ok(q2.pending === 0 && q2.approved === 5, `Saqlandi: 5 ta savol (ko'p javobli ham), pending yo'q (approved=${q2.approved})`);
          ok(!(await page.$('#kxTa')) && /5 ta test savoli/.test(await page.textContent('[data-slot="test"] .kx-stat')), "Kartochka yangilandi: «5 ta test savoli», tugma yo'q");
        } else {
          await page.setInputFiles('[data-kx-up="test"]', path.join(__dirname, '..', 'tests', 'fixtures', 'test_import', 'test_javobsiz.docx'));
          await page.waitForSelector('.ta-bg .ta-q', { timeout: 30000 }); await sleep(250);
          ok((await page.$$('.ta-q')).length === 3 && /2 ta savol qo'shildi, 3 tasi javobsiz/.test(await page.textContent('.ta-sum')), "390 px: 3 ta javobsiz savol, «2 ta savol qo'shildi, 3 tasi javobsiz» hisobi");
          const geo = await page.evaluate(() => { const m = document.querySelector('.ta-bg .pk-modal'); const r = m.getBoundingClientRect();
            return { over: m.scrollWidth > m.clientWidth + 1, doc: document.documentElement.scrollWidth > innerWidth + 1, right: Math.round(r.right), minOpt: Math.min(...[...m.querySelectorAll('.ta-opt')].map(x => x.getBoundingClientRect().height)),
              minBtn: Math.min(...[...m.querySelectorAll('.ta-bar .btn')].map(x => x.getBoundingClientRect().height)) }; });
          ok(!geo.over && !geo.doc && geo.right <= 390 && geo.minOpt >= 43 && geo.minBtn >= 43, `390 px: gorizontal siljish yo'q, variant va tugmalar ≥ 44 px (variant ${Math.round(geo.minOpt)}, tugma ${Math.round(geo.minBtn)}, o'ng chet ${geo.right})`);
          await page.screenshot({ path: `${OUT}/${tag}_3_javob_oynasi.png` });
          await page.click('.ta-q:nth-of-type(1) [data-skip]');
          ok(await page.$eval('.ta-q:nth-of-type(1)', e => e.classList.contains('skip') && e.querySelector('[data-skip]').getAttribute('aria-pressed') === 'true' && [...e.querySelectorAll('.ta-opts input')].every(x => x.disabled)), "«O'tkazib yuborish» — savol o'chirilgan ko'rinishda, variantlar bloklandi (aria-pressed)");
          await page.check('.ta-q:nth-of-type(2) .ta-opts label:nth-child(2) input');
          await page.click('.pk-modal [data-ok]'); await sleep(150);
          ok(await page.isVisible('.ta-bg') && (await page.textContent('.ta-q:nth-of-type(3) .ta-err')).length > 5 && !(await page.textContent('.ta-q:nth-of-type(2) .ta-err')), "Uchinchi savolga javob yo'q (o'tkazilmagan) — saqlanmaydi, xato faqat shu savol ostida");
          await page.keyboard.press('Tab'); ok(await inModal(), "Tab — fokus oynadan chiqib ketmaydi");
          await page.check('.ta-q:nth-of-type(3) .ta-opts label:nth-child(2) input');
          await page.screenshot({ path: `${OUT}/${tag}_3b_javob_oynasi_pastda.png` });
          await page.click('.pk-modal [data-ok]');
          await page.waitForFunction(() => !document.querySelector('.ta-bg'), null, { timeout: 15000 }); await sleep(600);
          const q3 = await quizN();
          ok(q3.pending === 0 && q3.approved === 4, `Saqlandi: 2 + 2 ta tasdiqlangan savol, 1 tasi o'tkazib yuborilgan (javobsiz qoralama) — approved=${q3.approved}, pending=${q3.pending}`);
        }
      }
      await page.screenshot({ path: `${OUT}/${tag}_1_materiallar.png`, fullPage: true });
      await page.click('#kxNext');
      await page.waitForSelector('#v-kurs.ku-rise .ku-blk', { timeout: 30000 }); await sleep(800);
      ok(await page.isVisible('.kx-bar') && (await page.textContent('.kx-bar .kx-steps li.on')).includes('Tahrirlash'), "Muharrir: qadamlar tasmasi (2 — Tahrirlash) va «Tayyor» tugmasi");
      ok(await page.isVisible('.ku-hero #kuLt'), "Rise ko'rinishi: muqova ichida dars nomi joyida tahrirlanadi");
      ok(!(await page.isVisible('#kuSide')) && !(await page.isVisible('#kuPanel')), "Darslar ro'yxati va blok sozlamalari yashirin (kerak bo'lganda ochiladi)");
      ok(await page.$$eval('.ku-blk[data-t="continue"] .ku-cont-btn', e => e.length) >= 1, "Bo'limlar — «davom etish» tasmasi (NEXTID kabi)");
      if (tag === 'm') ok(!(await hs()), "390 px: muharrirda gorizontal siljish yo'q");
      /* yagona asosiy tugma «Tayyor»: yuqori panel va qadamlar tasmasida boshqa asosiy (to'ldirilgan) tugma yo'q */
      const prim = await page.$$eval('#kuTopA .btn.primary, #kuNote .btn.primary', e => e.filter(x => x.offsetParent).map(x => x.textContent.trim()));
      ok(prim.length === 1 && prim[0] === 'Tayyor', `Yagona asosiy tugma — «Tayyor» (ko'rinadiganlar: ${prim.join(' | ')})`);
      ok(!(await page.$('#kuSub:not(.ku-mi), #kuApp:not(.ku-mi)')), "«Ko'rib chiqishga yuborish» / «Tasdiqlash» yuqori panelda alohida tugma emas (Yana menyusida va «Tayyor» oynasida)");
      ok(await page.$eval('#kxPub', e => getComputedStyle(e).backgroundColor === 'rgb(120, 55, 168)'), "Rise ko'rinishi: asosiy tugma binafsha (#7837a8) — ilova qizili emas");
      const heroH = await page.$eval('.ku-hero', e => Math.round(e.getBoundingClientRect().height));
      ok(heroH <= (tag === 'm' ? 175 : 200), `Muqova ixcham (${heroH}px)`);
      ok((await page.$$('.ku-blk.ku-dup')).length === 1 && !(await page.$('.ku-blk.ku-dup textarea')), "Birinchi sarlavha dars nomini takrorlasa — yig'ilgan (izoh bilan), ma'lumot o'chirilmagan");
      ok(await page.$eval('.ku-blk[data-t="continue"] .ku-cont-btn input', e => !!e.value) && !(await page.$('.ku-blk[data-t="continue"] select')) && !(await page.$('.ku-blk[data-t="continue"] .ku-note')), "«Davom etish» bloki: faqat tahrirlanadigan tasma (select va izoh yo'q)");
      if (tag === 'm') {
        const tb = await page.$eval('#v-kurs .ku-top', e => { const r = e.getBoundingClientRect(); return [Math.round(r.height), Math.round(r.right)]; });
        ok(tb[0] <= 76 && tb[1] <= 390, `390 px: yuqori panel bir qatorli va ixcham (${tb[0]}px)`);
      }
      await page.screenshot({ path: `${OUT}/${tag}_2_muharrir.png` });
      {   /* kontrast: lavanda tuvalda kulrang matn va placeholder'lar ≥ 4,5:1 (gradientli muqova hisobga olinmaydi) */
        const bad = await page.evaluate(() => {
          const parse = c => { const sr = c.match(/color\(srgb ([^)]+)\)/); if (sr) { const q = sr[1].split(/[ \/]+/).filter(Boolean).map(Number); return {r: q[0] * 255, g: q[1] * 255, b: q[2] * 255, a: q.length > 3 ? q[3] : 1}; }
            const m = c.match(/rgba?\(([^)]+)\)/); if (!m) return {r: 255, g: 255, b: 255, a: 0}; const p = m[1].split(/[ ,\/]+/).filter(Boolean).map(Number); return {r: p[0], g: p[1], b: p[2], a: p.length > 3 ? p[3] : 1}; };
          const lum = c => { const f = v => { v /= 255; return v <= .03928 ? v / 12.92 : Math.pow((v + .055) / 1.055, 2.4); }; return .2126 * f(c.r) + .7152 * f(c.g) + .0722 * f(c.b); };
          const blend = (f, b) => ({r: f.r * f.a + b.r * (1 - f.a), g: f.g * f.a + b.g * (1 - f.a), b: f.b * f.a + b.b * (1 - f.a), a: 1});
          const bgOf = el => { const st = []; let e = el; while (e && e.nodeType === 1) { const c = parse(getComputedStyle(e).backgroundColor); if (c.a > 0) { st.push(c); if (c.a >= .99) break; } e = e.parentElement; } let base = {r: 255, g: 255, b: 255, a: 1}; for (let i = st.length - 1; i >= 0; i--) base = blend(st[i], base); return base; };
          const out = [];
          document.querySelectorAll('#kuBlocks *, #kuPanel *').forEach(el => {
            const cs = getComputedStyle(el), r = el.getBoundingClientRect(); if (cs.visibility === 'hidden' || cs.display === 'none' || +cs.opacity === 0 || !r.width || !r.height || el.closest('.ku-blk-h')) return;
            let txt = ''; for (const n of el.childNodes) if (n.nodeType === 3) txt += n.textContent; txt = txt.trim();
            let col = parse(cs.color);
            if (el.matches('input,textarea')) { if (el.value) txt = el.value; else if (el.placeholder) { txt = el.placeholder; col = parse(getComputedStyle(el, '::placeholder').color); } }
            if (!txt) return;
            const bg = bgOf(el), fg = col.a < 1 ? blend(col, bg) : col, a = lum(fg), b = lum(bg), cr = (Math.max(a, b) + .05) / (Math.min(a, b) + .05);
            if (cr < 4.5) out.push(cr.toFixed(2) + ' ' + el.className + ' ' + txt.slice(0, 24));
          });
          return out;
        });
        ok(bad.length === 0, `Kontrast: tuval va panelda matn ≥ 4,5:1${bad.length ? ' — ' + bad.slice(0, 3).join(' | ') : ''}`);
      }
      if (tag === 'd') {
        const n0 = await page.$$eval('.ku-blk', e => e.length);
        await page.click('.ku-qbar [data-t="paragraph"]'); await sleep(500);
        ok((await page.$$eval('.ku-blk', e => e.length)) === n0 + 1, "Pastki tez qo'shish paneli: «Matn» bloki qo'shildi");
        const blk = page.locator('.ku-blk').nth(2); await blk.hover(); await sleep(300);
        ok(await blk.locator('.ku-tools').evaluate(e => getComputedStyle(e).opacity === '1'), "Blok ustiga kelganda asboblar ko'rinadi (yuqoriga/pastga, sozlamalar, nusxa, o'chirish)");
        await blk.locator('[data-act="gear"]').click(); await sleep(400);
        ok(await page.isVisible('#kuPanel.open'), "⚙ — blok sozlamalari o'ng paneli ochildi");
        await page.click('#kuPanel [data-pclose]'); await sleep(300);
        await page.click('#kuSideT'); await sleep(300);
        ok(await page.isVisible('#kuSide.open'), "Darslar paneli tugma bilan ochiladi");
        await page.click('#kuSide [data-sclose]'); await sleep(300);
        ok(!(await page.isVisible('#kuSide')), "Darslar paneli ichidagi «×» bilan yopiladi");
        await page.click('#kxPub'); await sleep(600);
        const steps = await page.$$eval('.kx-pub li > b', e => e.map(x => x.textContent.trim()));
        ok(steps.length >= 3 && steps.every((t, i) => t.startsWith(`${i + 1}. `)), `«Tayyor» oynasi: tekshiruv, eksport (NEXTID), yuborish / tasdiqlash — ketma-ket raqamlangan (${steps.join(' · ')})`);
        await page.screenshot({ path: `${OUT}/${tag}_3_nashr.png` });
        await page.keyboard.press('Escape'); await sleep(300);
        ok(!(await page.$('.ku-modal-bg')), "Esc «Tayyor» oynasini yopadi");
        await page.click('.ku-more summary'); await sleep(150);
        ok(await page.isVisible('#kuSub') && await page.isVisible('#kuApp') && await page.isVisible('#kuEx'), "«Yana» menyusi: yuborish, tasdiqlash va eksport shu yerda");
        await page.keyboard.press('Escape'); await sleep(150);
        ok(!(await page.isVisible('#kuEx')), "Esc «Yana» menyusini yopadi");
        /* «Tayyor» — konstruktor tasmasi yo'q bo'lsa yuqori panelda (yagona asosiy tugma) */
        await page.evaluate(() => { window._w = KU.wiz; KU.wiz = null; kuTop(); kuNote(); });
        ok(await page.isVisible('#kuTopA #kuDone') && !(await page.$('#kxPub')) && (await page.$$eval('#kuTopA .btn.primary, #kuNote .btn.primary', e => e.filter(x => x.offsetParent).length)) === 1, "Tasma yo'q bo'lsa «Tayyor» yuqori panelda — yana bitta asosiy tugma");
        await page.evaluate(() => { KU.wiz = window._w; kuTop(); kuNote(); });
        await page.waitForSelector('#kxPub');
        // blok kutubxonasi: eskizlar, guruhlar
        await page.click('.ku-qb.lib'); await page.waitForSelector('.ku-tile');
        const th = await page.$$eval('.ku-tile', e => e.map(t => !!t.querySelector('.th svg rect, .th svg path, .th svg circle')));
        const grp = await page.$$eval('#kuLib h4', e => e.map(x => x.textContent));
        ok(th.length >= 23 && th.every(Boolean) && grp.length >= 4 && grp.includes('Matn') && grp.includes('Rasm va video') && grp.includes('Boshqaruv'), `Blok kutubxonasi: ${th.length} ta eskiz, guruhlar: ${grp.join(' / ')}`);
        await page.screenshot({ path: `${OUT}/${tag}_4_kutubxona.png` });
        await page.keyboard.press('Escape'); await sleep(200);
        // eksport: bitta format (xAPI); «Eksport qilish» tugmasi o'sha joyda «Yuklab olish» ga aylanadi
        await page.evaluate(() => kuExport()); await page.waitForSelector('.ku-modal [data-ok]');
        ok((await page.$$('.ku-modal input[type=radio]')).length === 0 && /xAPI/.test(await page.textContent('.ku-modal')) && !/SCORM/.test(await page.textContent('.ku-modal')), "Eksport: format tanlovi yo'q — faqat NEXTID uchun xAPI");
        const bt0 = await (await page.$('.ku-modal .ku-acts [data-ok]')).boundingBox();
        await page.click('.ku-modal [data-ok]'); await page.waitForSelector('#kuDl', { timeout: 60000 });
        const bt1 = await (await page.$('.ku-acts #kuDl')).boundingBox();
        ok(!(await page.$('.ku-modal [data-ok]')) && /Yuklab olish/.test(await page.textContent('#kuDl')) && (await page.$$eval('#kuExR a', e => e.length)) === 0 && Math.abs(bt1.y - bt0.y) < 4 && bt1.x + bt1.width > bt0.x, `Eksport: «Eksport qilish» o'sha joyning o'zida «Yuklab olish» ga aylandi (y: ${Math.round(bt0.y)} → ${Math.round(bt1.y)}), natija qutisida ikkinchi tugma yo'q`);
        await page.keyboard.press('Escape'); await sleep(200);
        // ko'rish: qurilma almashtirgichi
        await page.click('#kuPv'); await page.waitForSelector('#kuPvF');
        const fw = async () => Math.round((await (await page.$('#kuPvF')).boundingBox()).width);
        const w0 = await fw(); await page.click('.ku-pvbar [data-dev="tablet"]'); await sleep(450); const w1 = await fw();
        await page.click('.ku-pvbar [data-dev="phone"]'); await sleep(450); const w2 = await fw();
        ok(w1 === 768 && w2 === 390 && w0 > 1000 && await page.$eval('.ku-pvw', e => e.dataset.dev === 'phone'), `Ko'rish: Kompyuter / Planshet / Telefon almashtirgichi (kenglik ${w0} → ${w1} → ${w2})`);
        await page.screenshot({ path: `${OUT}/${tag}_5_korish.png` });
        await page.keyboard.press('Escape'); await sleep(250);
        await require('./kurs_ai_check').run(page, ok, tag, OUT);   /* «AI bilan tahrirlash»: Rise ko'rinishi, 1440 px */
        // zamonaviy select (o'ng panel)
        await page.locator('.ku-blk[data-t="continue"]').first().locator('.ku-cont-btn').click({ position: { x: 4, y: 4 } });
        await page.locator('.ku-blk[data-t="continue"].sel [data-act="gear"]').first().click(); await sleep(450);
        ok(await page.$eval('#kuPanel select[data-k="require"]', e => { const c = getComputedStyle(e); return c.appearance === 'none' && /svg/.test(c.backgroundImage) && c.borderRadius !== '0px'; }), "Panel: select zamonaviy ko'rinishda (maxsus strelka, yumaloq)");
        ok(await page.$eval('#kuPanel', e => /Tugmani bosmaguncha keyingi qism yopiq/.test(e.textContent)), "Davom etish sozlamasi — «Tugmani bosmaguncha keyingi qism yopiq» (panelda)");
        await page.click('#kuPanel [data-pclose]'); await sleep(300);
        await page.click('#kxM'); await page.waitForSelector('.kx-grid', { timeout: 20000 });
        ok(await page.isVisible('.kx-grid'), "«← Materiallar» — konstruktorning 1-qadamiga qaytdi");
      }
      if (tag === 'm') {
        const order = () => page.$$eval('#kuBlocks .ku-blk', e => e.map(x => x.dataset.t).join(','));
        const o0 = await order();
        /* ketma-ket ikki bir xil turdagi blok (masalan ikkita «continue») almashsa tartib o'zgarmaydi — turi har xil bo'lgan juftlikni olamiz */
        const types = o0.split(','); let pi = 2; for (let i = 1; i < types.length - 1; i++) if (types[i] !== types[i + 1]) { pi = i; break; }
        await page.locator('#kuBlocks .ku-blk').nth(pi).locator('.ku-blk-b').first().click({ position: { x: 4, y: 4 } }); await sleep(300);
        const bb = await page.locator('#kuBlocks .ku-blk.sel [data-act="down"]').boundingBox(), tb = await page.locator('#kuBlocks .ku-blk.sel .ku-tools').boundingBox();
        ok(bb.width >= 44 && bb.height >= 44 && tb.x >= 0 && tb.x + tb.width <= 390, `390 px: blok asboblari ekran ichida, ↑ ↓ tugmalari ${Math.round(bb.width)}×${Math.round(bb.height)} px`);
        const waitOrder = async eq => { for (let n = 0; n < 40; n++) { const cur = await order(); if (eq ? cur === o0 : cur !== o0) return cur; await sleep(100); } return order(); };
        await page.locator('#kuBlocks .ku-blk.sel [data-act="down"]').click(); const o1 = await waitOrder(false);
        await page.locator('#kuBlocks .ku-blk.sel [data-act="up"]').click(); const o2 = await waitOrder(true);
        ok(o1 !== o0 && o2 === o0, "390 px: ↓ va ↑ tugmalari bilan blok ko'chadi va joyiga qaytadi" + (o1 !== o0 && o2 === o0 ? "" : ` [o0=${o0} | o1=${o1} | o2=${o2}]`));
        ok(!(await hs()), "390 px: blok tanlanganda ham gorizontal siljish yo'q");
        await page.screenshot({ path: `${OUT}/${tag}_6_blok_asboblari.png` });
        await require('./kurs_ai_check').run(page, ok, tag, OUT);   /* «AI bilan tahrirlash»: Rise ko'rinishi, 390 px */
      }
      ok(!errs.length, `JS xatosi yo'q (${tag})${errs.length ? ': ' + errs[0].slice(0, 160) : ''}`);
      await ctx.close();
    }
  } catch (e) { ok(false, 'Istisno: ' + String(e && e.message || e).split('\n')[0]); }
  await b.close();
  process.exit(bad ? 1 : 0);
})();
