#!/usr/bin/env node
/* «Taqdimot → Studiya → Masofaviy bo'lim» zanjiri — brauzer tekshiruvi (1440 va 390 px, gorizontal siljish yo'q).
   tests/test_zanjir.py chaqiradi: B (server), PW_ (parol), T_UID (o'qituvchi), H_UID (bo'lim boshlig'i), O_UID (operator), KURS, DIRN (yo'nalish nomi),
   CID (kurs id), LKEY (dars kaliti), CODE (kutilgan unikal kod), JID (tasdiqlangan montaj vazifasi), OUT (skrinshotlar).
   Oqim: o'qituvchi — «Taqdimot» → dars tanlash (kurs → yo'nalish → fan → dars; qo'lda yozish yo'q) → matndan reja → PPTX → «Studiyaga va masofaviy bo'limga yuborish» (v1, v2)
   → versiyalar oynasi; bog'lanmagan eski taqdimot — «Darsni belgilash». Operator — studiya dars tafsiloti (kod, taqdimot v2), «Mening vazifalarim» xabari,
   montajdan keyin «Masofaviy bo'limga yuborish» (avtomatik ma'lumot). Bo'lim — dars kartochkasi (kod, taqdimot, video, matn, jurnal), «Dars yaratish» → Konstruktor, ZIP. */
const { chromium } = require(process.env.PW || 'playwright-core');
const fs = require('fs');
const E = process.env, B = E.B, OUT = E.OUT || '/tmp/zanjir';
fs.mkdirSync(OUT, { recursive: true });
let bad = 0;
const ok = (c, m) => { console.log((c ? '✓ ' : '✗ ') + m); if (!c) bad++; };
const sleep = ms => new Promise(r => setTimeout(r, ms));
const TEXT = "Bozor iqtisodiyotida narx talab va taklif muvozanati orqali shakllanadi. ".repeat(3) +
  "\n## Talab qonuni\n- Narx oshsa talab kamayadi\n- Daromad ta'siri\n## Taklif qonuni\n- Narx oshsa taklif ortadi\n- Xarajatlar\n## Nazorat savollari\n- Talab qonuni nima?\n- Muvozanat narxi nima?\n";
async function login(ctx, uid) {
  const r = await ctx.request.post(B + '/api/login', { data: { user_id: +uid, password: E.PW_ } });
  if (!r.ok()) throw new Error('login ' + uid + ' ' + r.status());
}
const hs = page => page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1);
const modalFits = page => page.evaluate(() => { const m = document.querySelector('.pk-modal, .st-modal'); return !m || m.scrollWidth <= m.clientWidth + 1; });
(async () => {
  const b = await chromium.launch({ executablePath: E.CHROME, headless: true });
  let deckId = 0;
  try {
    for (const [W, H, tag] of [[1440, 900, 'd'], [390, 844, 'm']]) {
      /* ================= O'qituvchi ================= */
      const tctx = await b.newContext({ viewport: { width: W, height: H } });
      const tp = await tctx.newPage(); const errs = []; tp.on('pageerror', e => errs.push(String(e)));
      await login(tctx, E.T_UID);
      await tp.goto(B + '/'); await sleep(1200);
      await tp.evaluate(() => go('taqdimot')); await tp.waitForSelector('.lp', { timeout: 20000 });
      if (tag === 'd') {
        ok(!(await tp.$('#tqSubj')) && !(await tp.$('#tqNo')), "Taqdimot: «Fan nomi» va «Mavzu raqami» matn maydonlari yo'q — dars tanlanadi");
        ok((await tp.$$('.lp select')).length === 4, "Dars tanlagich: kurs → yo'nalish → fan → dars (4 ta tanlov)");
        ok(await tp.evaluate(() => { const g = s => document.querySelector(s); return g('[data-lp-d]').disabled === !g('[data-lp-k]').value && g('[data-lp-f]').disabled === !g('[data-lp-d]').value && g('[data-lp-l]').disabled === !g('[data-lp-f]').value; }),
           "Tanlagich: har bosqich oldingisi tanlanmaguncha o'chiq (bitta kurs / yo'nalish / fan bo'lsa — bosqich o'zi tanlanadi)");
        await tp.screenshot({ path: `${OUT}/${tag}_1_tanlagich_bosh.png` });
        /* darsni tanlamasdan yaratib bo'lmaydi */
        await tp.click('#tqSrcText, .tq-seg button[data-s="text"]'); await tp.fill('#tqText', TEXT);
        await tp.click('#tqGo'); await sleep(300);
        ok(await tp.isVisible('.lp') && !(await tp.$('#tqEd')), "Dars tanlanmasa — reja tuzilmaydi (ogohlantirish)");
        await tp.selectOption('[data-lp-k]', E.KURS);
        await tp.selectOption('[data-lp-d]', E.DIRN);
        await tp.selectOption('[data-lp-f]', E.CID);
        await tp.selectOption('[data-lp-l]', E.LKEY);
        await sleep(200);
        ok((await tp.textContent('.lp-info code')).trim() === E.CODE, `Tanlangan dars kodi: ${E.CODE}`);
        const info = await tp.textContent('.lp-info');
        ok(/Kafedra/.test(info) && /O'qituvchi/.test(info), "Kafedra va o'qituvchi avtomatik ko'rinadi");
        await tp.screenshot({ path: `${OUT}/${tag}_2_tanlagich.png` });
        await tp.click('#tqGo'); await tp.waitForSelector('#tqEd', { timeout: 30000 });
        ok((await tp.textContent('#tqLes .tq-code')).trim() === E.CODE, "Muharrir: dars qatorida unikal kod");
        ok(await tp.$eval('[data-o="subject"]', e => e.readOnly), "Fan nomi darsdan olingan (faqat o'qish)");
        ok(await tp.$eval('#tqSend', e => e.getAttribute('aria-disabled') === 'true') && /PPTX yaratish/.test(await tp.textContent('#tqSendHint')), "PPTX yaratilmaguncha «Yuborish» o'chiq, sababi yozilgan");
        await tp.click('#tqBuild'); await tp.waitForFunction(() => document.querySelector('#tqSend')?.getAttribute('aria-disabled') === 'false', null, { timeout: 60000 });
        ok(!(await tp.$eval('#tqSend', e => e.getAttribute('aria-disabled') === 'true')),"PPTX yaratildi — «Studiyaga va masofaviy bo'limga yuborish» yoqildi");
        ok(/Studiyaga va masofaviy bo'limga yuborish/.test(await tp.textContent('#tqSend')), "Tugma matni: «Studiyaga va masofaviy bo'limga yuborish» (bitta tugma, ikkala tomonga)");
        await tp.screenshot({ path: `${OUT}/${tag}_3_muharrir_yuborishga_tayyor.png` });
        await tp.click('#tqSend'); await tp.waitForSelector('.pk-modal #tqSendNote');
        ok(/v1/.test(await tp.textContent('.pk-modal')) && (await tp.textContent('.pk-modal .lp-info code')).trim() === E.CODE, "Yuborish oynasi: kod, kafedra, o'qituvchi, versiya v1");
        await tp.screenshot({ path: `${OUT}/${tag}_4_yuborish_oynasi.png` });
        await tp.fill('#tqSendNote', 'Birinchi variant'); await tp.click('.pk-modal [data-ok]');
        await tp.waitForSelector('#tqLes .tq-chip', { timeout: 60000 }); await sleep(300);
        ok(/v1 yuborilgan/.test(await tp.textContent('#tqLes')), "Yuborildi: «v1 yuborilgan»");
        ok(/\(v2\)/.test(await tp.textContent('#tqSend')), "Tugma endi «(v2)» — qayta yuborilsa versiya oshadi");
        // bir xil fayl <30 s ichida takror yuborilsa yangi versiya yaratilmaydi (A: unchanged) — haqiqiy qayta yuborish uchun avval tahrir + PPTX qayta yaratiladi
        await tp.evaluate(async () => {
          const id = TQ.deck.id, d = await tqApi(`/api/taqdimot/decks/${id}`), o = d.outline;
          o.slides.push({ type: 'summary', title: 'Xulosa', cards: [{ title: 'Talab', text: 'Narx bilan teskari' }] });
          await tqApi(`/api/taqdimot/decks/${id}/outline`, { outline: o }); await tqApi(`/api/taqdimot/decks/${id}/build`, {});
        });
        await tp.evaluate(id => tqOpen(id), await tp.evaluate(() => TQ.deck.id)); await tp.waitForSelector('#tqLes .tq-code', { timeout: 20000 });
        await tp.click('#tqSend'); await tp.waitForSelector('.pk-modal #tqSendNote');
        ok(/v2/.test(await tp.textContent('.pk-modal')) && /v1 tarixda qoladi/.test(await tp.textContent('.pk-modal')), "Qayta yuborish oynasi: v2, «v1 tarixda qoladi»");
        await tp.click('.pk-modal [data-ok]'); await tp.waitForFunction(() => /v2 yuborilgan/.test(document.querySelector('#tqLes')?.textContent || ''), null, { timeout: 60000 });
        ok((await tp.textContent('#tqLes .tq-code')).trim() === E.CODE, "v2 yuborildi — dars kodi o'zgarmadi");
        deckId = await tp.evaluate(() => TQ.deck.id);
      } else {
        await tp.evaluate(id => tqOpen(id), deckId); await tp.waitForSelector('#tqLes .tq-code', { timeout: 20000 });
        await tp.screenshot({ path: `${OUT}/${tag}_3_muharrir.png` });
        ok(!(await hs(tp)), "390 px: taqdimot muharririda gorizontal siljish yo'q");
        await tp.evaluate(() => { TQ.deck = null; TQ.tab = 'new'; tqShell(); }); await tp.waitForSelector('.lp');
        await tp.selectOption('[data-lp-k]', E.KURS); await tp.selectOption('[data-lp-d]', E.DIRN); await tp.selectOption('[data-lp-f]', E.CID); await tp.selectOption('[data-lp-l]', E.LKEY);
        await sleep(200); await tp.screenshot({ path: `${OUT}/${tag}_2_tanlagich.png` });
        ok(!(await hs(tp)), "390 px: dars tanlagichda gorizontal siljish yo'q");
      }
      await tp.evaluate(id => { if (!document.querySelector('#tqEd')) return tqOpen(id); }, deckId); await tp.waitForSelector('#tqHist', { timeout: 20000 });
      await tp.click('#tqHist'); await tp.waitForSelector('.pk-modal table.tq-t');
      const vr = await tp.$$eval('.pk-modal table.tq-t tbody tr', rs => rs.map(r => r.cells[0].textContent.trim()));
      ok(vr[0] === 'v2' && vr.includes('v1'), `Yuborilgan versiyalar oynasi: ${vr.join(', ')} (eski versiya qoldi)`);
      ok(await modalFits(tp), 'Versiyalar oynasi sig\'adi');
      await tp.screenshot({ path: `${OUT}/${tag}_5_versiyalar.png` });
      await tp.keyboard.press('Escape'); await tp.evaluate(() => document.querySelector('.pk-modal-bg')?.remove());
      /* bog'lanmagan eski taqdimot: «Darsni belgilash» */
      if (tag === 'd') {
        const old = await tp.evaluate(async () => { const r = await fetch('/api/taqdimot/decks/text', { method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ text: "Eski usulda yaratilgan taqdimot matni. ".repeat(6), subject: 'Eski fan', topic_no: '1' }) }); return (await r.json()).id; });
        await tp.evaluate(id => tqOpen(id), old); await tp.waitForSelector('#tqSetLes');
        ok(/bog'lanmagan/.test(await tp.textContent('#tqLes')) && await tp.$eval('#tqSend', e => e.getAttribute('aria-disabled') === 'true'), "Eski (bog'lanmagan) taqdimot: «Darsga bog'lanmagan», yuborish o'chiq");
        await tp.click('#tqSetLes'); await tp.waitForSelector('.pk-modal .lp');
        await tp.selectOption('.pk-modal [data-lp-k]', E.KURS); await tp.selectOption('.pk-modal [data-lp-d]', E.DIRN); await tp.selectOption('.pk-modal [data-lp-f]', E.CID); await tp.selectOption('.pk-modal [data-lp-l]', E.LKEY2);
        await sleep(200); await tp.screenshot({ path: `${OUT}/${tag}_6_darsni_belgilash.png` });
        await tp.click('.pk-modal [data-ok]'); await tp.waitForFunction(() => document.querySelector('#tqLes .tq-code'), null, { timeout: 20000 });
        ok(/\S/.test(await tp.textContent('#tqLes .tq-code')) && !(await tp.$('#tqSetLes')), "«Darsni belgilash»: kod o'rnatildi");
        await tp.evaluate(async id => { await fetch(`/api/taqdimot/decks/${id}/delete`, { method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json' }, body: '{}' }); }, old);
        /* ro'yxatda dars kodi ustuni */
        await tp.evaluate(() => { TQ.deck = null; TQ.tab = 'mine'; tqShell(); }); await tp.waitForSelector('.tq-t');
        ok(await tp.$$eval('.tq-t tbody tr .tq-code', e => e.length) >= 1 && /Dars kodi/.test(await tp.textContent('.tq-t thead')), "«Mening taqdimotlarim»: «Dars kodi» ustuni");
      }
      ok(errs.length === 0, 'O\'qituvchi: sahifa xatosi yo\'q' + (errs.length ? ' — ' + errs[0] : ''));
      if (E.BK_DAY) {
        await tp.evaluate(() => { stReset(); go('studio'); }); await tp.waitForSelector('#stBox .st-li', { timeout: 20000 }); await sleep(400);
        const mt = await tp.textContent('#stBox');
        ok(mt.includes(E.BK_CODE) && /taqdimot v\d/.test(mt), "O'qituvchi «Mening darslarim»: unikal kod va «taqdimot vN studiyaga yuborilgan»");
        await tp.screenshot({ path: `${OUT}/${tag}_6b_mening_darslarim.png` });
        if (tag === 'm') ok(!(await hs(tp)), "390 px: «Mening darslarim»da gorizontal siljish yo'q");
      }
      await tctx.close();

      /* ================= Operator (studiya) ================= */
      const octx = await b.newContext({ viewport: { width: W, height: H } });
      const op = await octx.newPage(); const oerr = []; op.on('pageerror', e => oerr.push(String(e)));
      await login(octx, E.O_UID);
      await op.goto(B + '/'); await sleep(1200);
      await op.evaluate(() => go('mywork')); await op.waitForSelector('.mw-row, .mw-empty', { timeout: 20000 });
      if (tag === 'd') {
        ok(await op.$$eval('.mw-row', (rs, code) => rs.some(r => /Yangi taqdimot: .*v2/.test(r.textContent) && r.textContent.includes(code)), E.CODE), "Operator «Mening vazifalarim»: «Yangi taqdimot: <kod> · v2»");
        await op.screenshot({ path: `${OUT}/${tag}_7_operator_vazifalar.png` });
      }
      await op.evaluate(() => go('studio')); await op.waitForSelector('#stBox', { timeout: 20000 }); await sleep(500);
      await op.evaluate(([c, l]) => stLesson(+c, +l), [E.CID, E.LKEY]); await op.waitForSelector('.st-modal');
      const mt = await op.textContent('.st-modal');
      ok(mt.includes(E.CODE) && /Taqdimot/.test(mt) && /v2/.test(mt), "Studiya dars tafsiloti: unikal kod va taqdimot v2 (oxirgi versiya)");
      ok(await op.isVisible('.st-modal a[href$="/taqdimot/2/pptx"]'), "Taqdimot v2 ni yuklab olish havolasi (operator syomkada ochadi)");
      ok(await modalFits(op), "Studiya oynasi gorizontal sig'adi");
      await op.screenshot({ path: `${OUT}/${tag}_8_studiya_tafsilot.png` });
      if (tag === 'd') {
        const dwBtn = await op.$('.st-modal [data-dw]');
        ok(!!dwBtn, "Tasdiqlangan montaj yonida «masofaviy bo'limga yuborish»");
        await dwBtn.click(); await op.waitForSelector('.st-modal .st-dl');
        const dl = await op.textContent('.st-modal .st-dl');
        ok(dl.includes(E.CODE) && /Kafedra/.test(dl) && /O'qituvchi/.test(dl) && /Fan/.test(dl) && /v2/.test(dl), "Yuborish oynasi AVTOMATIK to'ldirilgan: kod, kafedra, o'qituvchi, fan, dars, taqdimot v2");
        await op.screenshot({ path: `${OUT}/${tag}_9_bolimga_yuborish.png` });
        await op.click('.st-modal [data-ok]'); await sleep(900);
        const done = await op.evaluate(async j => (await (await fetch(`/api/studio/jobs/${j}`, { credentials: 'same-origin' })).json()).dept, E.JID);
        ok(done && done.code === E.CODE, "Operator tasdiqladi — masofaviy bo'limga yuborildi (st_dept)");
        await op.evaluate(() => { document.querySelectorAll('.st-modal-bg').forEach(x => x.remove()); stReset(); renderStudio('montaj'); }); await sleep(800);
        ok(!(await op.$('[data-dw]')), "Montaj bo'limida «yuborilmagan» ro'yxatidan chiqdi");
      }
      /* Kun rejasi: syomka bandida unikal kod va «Taqdimot vN» tugmasi (st_bookings orqali) */
      if (E.BK_DAY) {
        await op.evaluate(() => document.querySelectorAll('.st-modal-bg').forEach(x => x.remove()));
        await op.evaluate(day => { STD.day = day; renderStudio('kun'); }, E.BK_DAY); await op.waitForSelector(`.st-slot.busy [data-pres="${E.BK_KEY}"]`, { timeout: 20000 });
        const slot = await op.textContent(`.st-slot.busy:has([data-pres="${E.BK_KEY}"])`);
        ok(slot.includes(E.BK_CODE) && /Taqdimot v\d/.test(slot), "Kun rejasi: syomka bandida unikal kod va «Taqdimot vN»");
        await op.screenshot({ path: `${OUT}/${tag}_8b_kun_rejasi.png` });
        if (tag === 'm') ok(!(await hs(op)), "390 px: kun rejasida gorizontal siljish yo'q");
        await op.click(`.st-slot.busy [data-pres="${E.BK_KEY}"]`); await op.waitForSelector('.st-modal a[href*="/taqdimot/"]');
        ok(await op.isVisible('.st-modal a[href$="/pptx"]'), "«Taqdimot» tugmasi: oxirgi versiyani ochish/yuklab olish");
        await op.keyboard.press('Escape'); await op.evaluate(() => document.querySelectorAll('.st-modal-bg').forEach(x => x.remove()));
      }
      ok(oerr.length === 0, "Operator: sahifa xatosi yo'q" + (oerr.length ? ' — ' + oerr[0] : ''));
      await octx.close();

      /* ================= Masofaviy bo'lim: dars kartochkasi ================= */
      const hctx = await b.newContext({ viewport: { width: W, height: H } });
      const hp = await hctx.newPage(); const herr = []; hp.on('pageerror', e => herr.push(String(e)));
      await login(hctx, E.H_UID);
      await hp.goto(B + '/'); await sleep(1200);
      if (tag === 'd') {
        await hp.evaluate(() => go('mywork')); await hp.waitForSelector('.mw-row', { timeout: 20000 });
        const rows = await hp.$$eval('.mw-row', rs => rs.map(r => r.textContent));
        ok(rows.some(t => /Taqdimot yuborildi: .*v2/.test(t) && t.includes(E.CODE)) && rows.some(t => /Montajlangan video keldi/.test(t)), "Bo'lim «Mening vazifalarim»: «Taqdimot yuborildi · v2» va «Montajlangan video keldi»");
        await hp.screenshot({ path: `${OUT}/${tag}_10_bolim_vazifalar.png` });
      }
      await hp.evaluate(([c, l]) => { DS.cid = +c; DS.data = null; go('paket'); }, [E.CID, E.LKEY]); await hp.waitForSelector('[data-card]', { timeout: 30000 });
      await hp.click(`[data-card="${E.LKEY}"]`); await hp.waitForSelector('.lc .lc-code', { timeout: 20000 });
      ok((await hp.textContent('.lc .lc-code')).trim() === E.CODE, "Dars kartochkasi: unikal kod");
      const lt = await hp.textContent('.lc');
      ok(/Kafedra/.test(lt) && /O'qituvchi/.test(lt) && /Taqdimot/.test(lt) && /v2/.test(lt) && /Video/.test(lt) && /Ma'ruza matni/.test(lt) && /Jurnal/.test(lt), "Kartochka: kafedra, o'qituvchi, taqdimot (v2 + tarix), video holati, matn, jurnal");
      ok(await hp.isVisible('#lcCreate') && await hp.isVisible('#lcZip'), "«Dars yaratish» va «Hammasini ZIP qilib yuklab olish» tugmalari");
      ok(await modalFits(hp), "Kartochka oynasi gorizontal sig'adi");
      await hp.screenshot({ path: `${OUT}/${tag}_11_dars_kartochkasi.png` });
      if (tag === 'm') ok(!(await hs(hp)), "390 px: kartochka ochiqligida sahifa gorizontal siljimaydi");
      const zr = await hp.evaluate(async h => { const r = await fetch(h, { credentials: 'same-origin' }); const b = await r.arrayBuffer(); return [r.status, b.byteLength, r.headers.get('content-type')]; }, await hp.getAttribute('#lcZip', 'href'));
      ok(zr[0] === 200 && zr[1] > 100 && /zip/.test(zr[2]), 'ZIP yuklab olinadi');
      if (tag === 'd') {
        await hp.click('#lcCreate');
        const bo = hp.getByRole('button', { name: 'Baribir ochish' });   // yetishmaydigan ma'lumot bo'lsa — tasdiq so'raladi
        if (await bo.waitFor({ timeout: 3000 }).then(() => true).catch(() => false)) await bo.click();
        await hp.waitForSelector('.kx', { timeout: 40000 });
        ok(/Materiallar/.test(await hp.textContent('.kx-steps')), "«Dars yaratish» → Konstruktor ochildi (1 — Materiallar)");
        await hp.screenshot({ path: `${OUT}/${tag}_12_konstruktor.png` });
      }
      ok(herr.length === 0, "Bo'lim: sahifa xatosi yo'q" + (herr.length ? ' — ' + herr[0] : ''));
      await hctx.close();
    }
  } catch (e) { console.log('✗ Brauzer xatosi: ' + (e && e.stack || e)); bad++; }
  await b.close();
  process.exit(bad ? 1 : 0);
})();
