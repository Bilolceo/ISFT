/* «AI bilan tahrirlash» (static/kurs.js kuAiOpen, app/kurs_ai.py) — brauzer tekshiruvi. Rise ko'rinishidagi muharrir ochiq bo'lishi kerak
   (tools/konstruktor_check.js 1440 va 390 px da chaqiradi; klassik ko'rinish uchun tools/kurs_editor_check.js).
   run(page, ok, tag, OUT): tez qo'shish panelidan yangi «Bilimni tekshirish» bloki → blok asbobidagi «AI bilan tahrirlash» → Word matni (✅) →
   natija (soxta endpoint javobi: page.route) → ko'rinish (savol, variantlar, to'g'ri javob ajratilgan, har variant izohi) → «Bloknu almashtirish» →
   blok ma'lumoti o'zgardi + «AI tuzdi — to'g'ri javobni tekshiring» eslatmasi → to'g'ri javobni boshqa variantga o'tkazish → eslatma yo'qoladi →
   haqiqiy server (kalitsiz): 503 + ✅ dan tuzilma ko'rsatiladi → «AI bilan savol» (yangi blok) → 390 px da sig'ishi. Blok bazaga avtosaqlanadi. */
'use strict';
const sleep = ms => new Promise(r => setTimeout(r, ms));
const WORD = "3. Startap qanday kompaniya hisoblanadi?\nA) Davlat unitar korxonasi\nB) Tez o‘sishga yo‘naltirilgan yangi kompaniya ✅\nC) Faqat eksport bilan shug‘ullanadigan firma\nD) Yirik xolding tarkibidagi bo‘linma";
const FAKE = {
  ok: true, ai: true, parsed: true, answer_guessed: false, answer_missing: false, warnings: [], more: 0, model: "claude-opus-5-5", quota: { used: 1, limit: 100 },
  block: { type: "knowledge", data: { kind: "single", question: "Startap qanday kompaniya hisoblanadi?", accept: [], retry: true,
    answers: [
      { text: "Davlat unitar korxonasi", correct: false, feedback: "Startap davlat korxonasi emas." },
      { text: "Tez o'sishga yo'naltirilgan yangi kompaniya", correct: true, feedback: "To'g'ri: startap tez o'sishga mo'ljallangan." },
      { text: "Faqat eksport bilan shug'ullanadigan firma", correct: false, feedback: "Faoliyat eksport bilan cheklanmaydi." },
      { text: "Yirik xolding tarkibidagi bo'linma", correct: false, feedback: "Startap odatda mustaqil kompaniya." }],
    feedback_correct: "Startap — tez o'sishga yo'naltirilgan yangi kompaniya.", feedback_wrong: "Ta'rifni takrorlang." } },
  issues: [] };
exports.run = async function (page, ok, tag, OUT) {
  const mob = tag === 'm';
  const hs = () => page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1);
  const seen = [];
  await page.route('**/api/kurs/lessons/*/ai-question', async route => {
    seen.push(JSON.parse(route.request().postData() || '{}'));
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(FAKE) });
  });
  const n0 = await page.$$eval('#kuBlocks .ku-blk', e => e.length);
  const rise = !!(await page.$('.ku-qbar'));   /* klassik ko'rinishda tez qo'shish paneli yo'q — kutubxona orqali */
  if (rise) { ok(await page.isVisible('.ku-qbar [data-act="qai"]'), "Tez qo'shish paneli: «AI bilan savol» tugmasi bor"); await page.click('.ku-qbar [data-t="knowledge"]'); }
  else await page.evaluate(() => kuInsert('knowledge', KU.blocks.length));
  await sleep(500);
  const bi = await page.evaluate(() => KU.sel);
  const card = page.locator(`#kuBlocks [data-bi="${bi}"]`);
  const aiBtn = i => page.locator(`#kuBlocks [data-bi="${i}"] ${mob ? '.ku-ai-inl' : '.ku-tools'} [data-act="ai"]`);   /* telefonda — blok ichidagi tugma (asboblar qatori to'lib ketmasligi uchun) */
  const btn = aiBtn(bi);
  ok(await btn.count() === 1 && (mob ? /AI bilan tahrirlash/.test(await btn.textContent()) : await btn.getAttribute('aria-label') === 'AI bilan tahrirlash') && await btn.evaluate(e => !!e.querySelector('svg')), "Savol blokida: «AI bilan tahrirlash» (sparkle belgisi; kompyuterda asboblar qatorida aria-label bilan, telefonda blok ichida)");
  ok(await page.$$eval('#kuBlocks .ku-blk:not([data-t="knowledge"]):not([data-t="question"]) [data-act="ai"]', e => e.length) === 0, "AI tugmasi faqat savol bloklarida");
  if (mob) {
    const tl = await card.locator('.ku-tools').boundingBox(), cr = await card.boundingBox();
    ok(tl.x >= 0 && tl.x + tl.width <= 390 && (await card.locator('.ku-tools [data-act="del"]').boundingBox()).x + 44 <= 390, "390 px: blok asboblari qatori ekranga sig'adi (o'chirish tugmasi qirqilmagan)"); const bb = await btn.boundingBox(); ok(bb.width >= 44 && bb.height >= 44 && bb.x >= 0 && bb.x + bb.width <= 390, `390 px: AI tugmasi ${Math.round(bb.width)}×${Math.round(bb.height)} px, ekran ichida`); }
  await btn.click(); await page.waitForSelector('.ku-modal.ai #kuAiT');
  const dlg = page.locator('.ku-modal.ai');
  ok(await page.$eval('.ku-modal.ai', e => e.getAttribute('role') === 'dialog' && e.getAttribute('aria-modal') === 'true'), "Oyna: dialog (aria-modal), sarlavha «AI bilan tahrirlash»");
  ok(/Word'dan nusxa — ✅ to'g'ri javobni bildiradi/.test(await dlg.textContent()) && await page.$eval('#kuAiT', e => e.value === ''), "Matn maydoni: «Savolni shu yerga qo'ying (Word'dan nusxa — ✅ …)» (yangi blokda bo'sh)");
  ok(await page.$eval('.ku-modal.ai [data-ok]', e => e.disabled) && await page.isVisible('#kuAiGo') && !(await page.isVisible('#kuAiRe')), "Boshida «Bloknu almashtirish» o'chiq, «Qayta urinish» yo'q");
  await page.fill('#kuAiT', WORD); await page.click('#kuAiGo');
  await page.waitForSelector('.ku-aip .ku-aip-opts li');
  const pv = await page.$$eval('.ku-aip-opts li', e => e.map(x => ({ ok: x.classList.contains('ok'), fb: !!x.querySelector('p') })));
  ok(pv.length === 4 && pv.filter(x => x.ok).length === 1 && pv[1].ok && pv.every(x => x.fb), "Ko'rinish: 4 variant, to'g'ri javob (B) ajratilgan, har variantda izoh");
  ok(/Startap qanday kompaniya/.test(await page.textContent('.ku-aip-q')) && /To'g'ri javobda:/.test(await page.textContent('.ku-aip-fb')) && await page.isVisible('#kuAiRe'), "Ko'rinish: savol matni, umumiy izoh, «Qayta urinish»");
  ok(seen.length === 1 && seen[0].text === WORD && seen[0].qtype === 'auto' && seen[0].btype === 'knowledge', "So'rov: matn, qtype=auto, btype=knowledge yuborildi");
  ok(await page.$eval('.ku-modal.ai [data-ok]', e => !e.disabled), "Natija bor — «Bloknu almashtirish» yoqildi");
  const box = await dlg.boundingBox();
  ok(box.x >= 0 && box.x + box.width <= (mob ? 390 : 1440) + 1 && box.y >= 0 && box.y + box.height <= (mob ? 844 : 900) + 1 && !(await hs()), `Oyna ekranga sig'adi (${Math.round(box.width)}×${Math.round(box.height)}), gorizontal siljish yo'q`);
  await page.screenshot({ path: `${OUT}/${tag}_ai_1_oyna.png` });
  await page.click('.ku-modal.ai [data-ok]'); await sleep(500);
  ok(!(await page.$('.ku-modal.ai')), "«Bloknu almashtirish» oynani yopadi");
  const d = await page.evaluate(i => KU.blocks[i].data, bi);
  ok(d.question === FAKE.block.data.question && d.answers.length === 4 && d.answers[1].correct && d.answers[1].feedback.startsWith("To'g'ri:") && d.feedback_correct && d.kind === 'single' && d.retry === true, "Blok ma'lumoti AI natijasi bilan almashdi (savol, 4 variant, izohlar)");
  const note = card.locator('.ku-ainote');
  ok(await note.isVisible() && /AI tuzdi — to'g'ri javobni tekshiring/.test(await note.textContent()), "Blokda eslatma: «AI tuzdi — to'g'ri javobni tekshiring»");
  ok(await card.locator('.ku-ans').count() === 4 && await card.locator('.ku-ans.ok').count() === 1 && await card.locator('.ku-ans.ok input[data-k="answers.1.text"]').inputValue() === FAKE.block.data.answers[1].text
     && await card.locator('input[data-k="answers.1.feedback"]').inputValue() === FAKE.block.data.answers[1].feedback, "Blok muharriri: variantlar va har variant izohi maydonlarda, to'g'ri javob belgilangan");
  await page.screenshot({ path: `${OUT}/${tag}_ai_2_blok.png` });
  await page.evaluate(() => kuFlush()); await sleep(300);
  const srv = await page.evaluate(async () => { const r = await fetch(`/api/kurs/lessons/${KU.lid}`); const j = await r.json(); return j.blocks.filter(b => b.type === 'knowledge' && b.data.question.startsWith('Startap qanday')).pop(); });
  ok(srv && srv.data.answers[1].correct === true && srv.data.answers[1].feedback.startsWith("To'g'ri:") && srv.data.feedback_wrong === "Ta'rifni takrorlang.", "Almashtirilgan blok serverga avtosaqlandi (variant izohlari bilan)");
  /* to'g'ri javobni almashtirish (Rise: «agar AI adashgan bo'lsa, to'g'ri javobni shu yerda almashtirasiz») */
  await card.locator('input[data-act="corr"][data-i="0"]').click({ force: true }); await sleep(300);
  const d2 = await page.evaluate(i => KU.blocks[i].data.answers.map(a => a.correct), bi);
  ok(JSON.stringify(d2) === '[true,false,false,false]' && await page.locator(`#kuBlocks [data-bi="${bi}"] .ku-ainote`).count() === 0, "To'g'ri javobni A ga o'tkazish ishladi, eslatma yo'qoldi");
  /* qayta ochish: oldingi matn ✅ bilan to'ldiriladi; haqiqiy server (kalitsiz) — 503 + ✅ dan tuzilma */
  await page.unroute('**/api/kurs/lessons/*/ai-question');
  await page.evaluate(i => kuSelect(i, false), bi); await sleep(200);
  await aiBtn(bi).click(); await page.waitForSelector('#kuAiT');
  const seed = await page.inputValue('#kuAiT');
  ok(/^Startap qanday kompaniya hisoblanadi\?\nA\) Davlat unitar korxonasi ✅\nB\) /.test(seed), "Qayta ochilganda matn maydoni blokning hozirgi savoli bilan to'ldirilgan (✅ — to'g'ri javob)");
  await page.click('#kuAiGo'); await page.waitForSelector('.ku-aip, .ku-aip-n.bad', { timeout: 20000 });
  const real = await page.evaluate(() => ({ n: document.querySelectorAll('.ku-aip-opts li').length, ok: document.querySelectorAll('.ku-aip-opts li.ok').length, msg: document.querySelector('.ku-aip-n.bad')?.textContent || '', btn: !document.querySelector('.ku-modal.ai [data-ok]').disabled }));
  ok(real.n === 4 && real.ok === 1 && /AI ulanmagan/.test(real.msg) && real.btn, "Kalitsiz server: «AI ulanmagan» xabari + ✅ dan tuzilma ko'rsatiladi, almashtirish mumkin (AI'siz ham ishlaydi)");
  ok(await page.isVisible('#kuAiRe') && /AI'siz/.test(await page.textContent('.ku-aip-h')), "«AI'siz (✅ dan)» belgisi va «Qayta urinish»");
  await page.screenshot({ path: `${OUT}/${tag}_ai_3_kalitsiz.png` });
  await page.keyboard.press('Escape'); await sleep(250);
  ok(!(await page.$('.ku-modal.ai')) && (await page.evaluate(i => KU.blocks[i].data.answers[0].correct, bi)) === true, "«Bekor qilish» / Esc blokni o'zgartirmaydi");
  /* tez qo'shish: AI bilan yangi savol (soxta javob) */
  await page.route('**/api/kurs/lessons/*/ai-question', async route => { await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ ...FAKE, answer_guessed: true }) }); });
  const n1 = await page.$$eval('#kuBlocks .ku-blk', e => e.length);
  if (rise) await page.click('.ku-qbar [data-act="qai"]');
  else { await page.evaluate(() => kuLibrary(KU.blocks.length)); await page.waitForSelector('.ku-tile.ai'); await page.click('.ku-tile.ai'); }   /* blok kutubxonasida ham «AI bilan savol» */
  await page.waitForSelector('#kuAiT');
  ok(/AI bilan savol/.test(await page.textContent('.ku-modal.ai .ku-modal-h')) && /Blokni qo'shish/.test(await page.textContent('.ku-modal.ai [data-ok]')), "«AI bilan savol» (yangi blok): oyna va «Blokni qo'shish» tugmasi");
  await page.fill('#kuAiT', 'Startap haqida savol'); await page.click('#kuAiGo'); await page.waitForSelector('.ku-aip-opts li');
  ok(/to'g'ri javobni o'zi tanladi/.test(await page.textContent('.ku-aip-n.warn')), "Belgisiz savol: «AI to'g'ri javobni o'zi tanladi — tekshiring» ogohlantirishi");
  await page.click('.ku-modal.ai [data-ok]'); await sleep(500);
  const n2 = await page.$$eval('#kuBlocks .ku-blk', e => e.length), nb = await page.evaluate(() => KU.sel);
  ok(n2 === n1 + 1 && await page.evaluate(i => KU.blocks[i].type === 'knowledge' && KU.blocks[i].data.question.startsWith('Startap qanday'), nb)
     && await page.locator(`#kuBlocks [data-bi="${nb}"] .ku-ainote.warn`).isVisible(), "Yangi savol bloki qo'shildi, eslatma (ogohlantirish) ko'rinadi");
  ok(await page.locator(`#kuBlocks [data-bi="${nb}"] [data-act="ai-undo"]`).count() === 0, "Yangi blokda «Avvalgisini qaytarish» yo'q (qaytariladigan narsa yo'q)");
  await page.screenshot({ path: `${OUT}/${tag}_ai_4_yangi.png` });
  /* «Avvalgisini qaytarish» (almashtirilgan blok) */
  await page.evaluate(i => kuSelect(i, false), bi); await sleep(200);
  await aiBtn(bi).click(); await page.waitForSelector('#kuAiT');
  await page.fill('#kuAiT', WORD); await page.click('#kuAiGo'); await page.waitForSelector('.ku-aip-opts li'); await page.click('.ku-modal.ai [data-ok]'); await sleep(500);
  await page.locator(`#kuBlocks [data-bi="${bi}"] [data-act="ai-undo"]`).click(); await sleep(300);
  ok(await page.evaluate(i => KU.blocks[i].data.answers[0].correct === true && KU.blocks[i].data.answers[1].correct === false && !KU.aiMark[KU.blocks[i].id] && !document.querySelector(`#kuBlocks [data-bi="${i}"] .ku-ainote`), bi),
     "«Avvalgisini qaytarish» oldingi holatni tiklaydi, eslatma yo'qoladi");
  ok(!(await hs()), "AI oqimidan keyin ham gorizontal siljish yo'q");
  await page.unroute('**/api/kurs/lessons/*/ai-question');
  /* tozalash: sinov bloklari o'chiriladi */
  await page.evaluate(([a, b]) => { KU.blocks = KU.blocks.filter((_, i) => i !== a && i !== b); kuRenderBlocks(); kuRenderPanel(); kuDirty(); return kuFlush(); }, [bi, nb]);
  await sleep(300);
  ok(await page.$$eval('#kuBlocks .ku-blk', e => e.length) === n0, "Sinov bloklari o'chirildi (dars avvalgi holatda)");
};
