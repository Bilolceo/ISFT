/* Konstruktor «Materiallar» qadami va fan sahifasidagi dars qatorlari — ko'rinish tekshiruvlari (tools/konstruktor_check.js chaqiradi).
   subject(page, ok, tag) — fan sahifasi; materials(page, ok, tag, B, env) — 1-qadam (kartochkalar, rang, «Namuna» tasmasi, avtomatik subtitr). */
const sleep = ms => new Promise(r => setTimeout(r, ms));
const PURPLE = 'rgb(120, 55, 168)';

async function subject(page, ok, tag) {
  const bg = sel => page.$eval(sel, e => getComputedStyle(e).backgroundColor);
  ok(await bg('.ds-grid.a .btn.primary') === PURPLE, `[${tag}] fan sahifasi: dars qatoridagi asosiy tugma binafsha (qizil emas)`);
  const steps = await page.$$eval('.ds-grid.a .ds-l:first-child .ds-step', es => es.map(e => ({t: e.textContent.trim(), tip: e.title, al: e.getAttribute('aria-label')})));
  ok(steps.length === 3 && steps.map(s => s.t).join('·') === 'Material·Video·Paket', `[${tag}] dars qatori: 3 ta qadam — Material · Video · Paket (${steps.map(s => s.t)})`);
  ok(steps.every(s => s.tip && s.al && s.tip === s.al), `[${tag}] qadamlarda tooltip va aria-label bor ("${steps[0] && steps[0].al}")`);
  ok(await page.$eval('.ds-grid.a', e => !/Eksport/.test(e.textContent)), `[${tag}] bir xil atama: «Paket» (qatorlarda «Eksport» yo'q)`);
  ok(await page.$eval('.ds-grid.a .ds-prg', e => e.getAttribute('role') === 'list' && /Tayyorlik/.test(e.getAttribute('aria-label'))), `[${tag}] tayyorlik ko'rsatkichi: role=list, aria-label`);
  const un = await page.$$eval('.ds-grid.a .ds-un', es => es.map(e => ({t: e.textContent, st: getComputedStyle(e).fontStyle})));
  ok(!un.length || (un.every(u => u.t === 'Mavzu nomi kiritilmagan' && u.st === 'italic')), `[${tag}] nomi yo'q darslar: «Mavzu nomi kiritilmagan» (qiya, xira) — ${un.length} ta`);
  ok(await page.$eval('.ds-grid.a', e => !/(^|\s)\d+-mavzu(\s|$)/.test(e.textContent.replace(/Mavzu nomi kiritilmagan/g, ''))), `[${tag}] «2-mavzu», «3-mavzu» kabi o'rinbosar nomlar ko'rinmaydi`);
  ok(await page.$eval('.ds-grid.a .ds-code', e => getComputedStyle(e).display === 'grid' && e.getBoundingClientRect().width >= 40), `[${tag}] ma'ruza raqami belgisi (L#) ko'rinadi`);
  ok(await page.isVisible('#dsBulkUp'), `[${tag}] «Ko'p faylni yuklash» tugmasi «Fan skeleti» yonida`);
}

async function materials(page, ok, tag, B, env) {
  ok(await page.$eval('.kx-next', e => getComputedStyle(e).backgroundColor) === PURPLE && await page.$eval('#kxDrop .btn.primary', e => getComputedStyle(e).backgroundColor) === PURPLE,
     `[${tag}] Konstruktor: «Fayl tanlash» va «Darsni yig'ish» tugmalari binafsha`);
  // «Namuna» tasmasi: sarlavha (74 px) ostida to'liq ko'rinadi, sahifa tepaga qaytadi
  const demo = await page.evaluate(() => { const e = document.querySelector('.pk-demo'); if (!e) return null; const r = e.getBoundingClientRect(); return {top: r.top, y: scrollY}; });
  ok(!demo || (demo.y === 0 && demo.top >= 60), `[${tag}] «Namuna» tasmasi to'liq ko'rinadi (sahifa tepada, tasma yuqorisi ${demo ? Math.round(demo.top) : '—'} px)`);
  // kartochkalar: bir xil balandlik, sarlavha va «Tayyor» belgisi to'qnashmaydi
  const hs = await page.$$eval('.kx-card', es => es.map(e => Math.round(e.getBoundingClientRect().height)));
  if (tag === 'd') ok(Math.max(...hs) - Math.min(...hs) <= 1, `[${tag}] 4 ta kartochka bir xil balandlikda (${hs})`);
  const clash = await page.$$eval('.kx-card', es => es.map(c => { const a = c.querySelector('.kx-card-h b').getBoundingClientRect(), s = c.querySelector('.kx-st').getBoundingClientRect(); return !(a.bottom <= s.top || s.bottom <= a.top || a.right <= s.left || s.right <= a.left); }));
  ok(!clash.some(Boolean), `[${tag}] sarlavha va holat belgisi (✓ Tayyor / Bo'sh) to'qnashmaydi`);
  const yt = await page.evaluate(() => { const i = document.querySelector('#kxYt').getBoundingClientRect(), c = document.querySelector('[data-slot="video"]').getBoundingClientRect(); return i.width / c.width; });
  ok(yt > 0.85, `[${tag}] YouTube maydoni kartochka kengligining ${Math.round(yt * 100)}% (to'liq kenglik)`);
  ok(await page.$eval('[data-slot="test"]', c => { const d = c.querySelector('details.kx-more'); return !!d && !d.open && !/✅/.test(c.querySelector('.kx-hint').textContent + c.querySelector('.kx-stat').textContent); }), `[${tag}] 4-kartochka: qisqa matn, tafsilot «Batafsil» ostida (yopiq), emojisiz`);
  await page.click('[data-slot="test"] .kx-more summary'); await sleep(150);
  ok(await page.$eval('[data-slot="test"] details.kx-more', d => d.open && /✅/.test(d.textContent)), `[${tag}] «Batafsil» ochiladi — belgilash qoidasi ko'rinadi`);
  const ic = await page.$$eval('.kx-ic svg', es => [...new Set(es.map(e => Math.round(e.getBoundingClientRect().width)))]);
  ok(ic.length === 1 && ic[0] === 20, `[${tag}] kartochka ikonkalari bir xil o'lchamda (${ic})`);
  ok(!(await page.$('#kxAuto')), `[${tag}] YouTube videoda «Avtomatik subtitr» tugmasi yo'q (faqat video fayl uchun)`);
  if (tag !== 'd') return;
  // video FAYL: topic javobiga soxta video qo'shiladi; subtitr endpointi — avval yo'q (404), keyin navbat, keyin xato
  const key = env.KX_KEY, cid = env.KX_CID, topicRx = new RegExp(`/api/paket/courses/${cid}/topics/${key}$`), capRx = /\/captions\/auto$/;
  await page.route(topicRx, async route => {
    const r = await route.fetch(), j = await r.json();
    j.ready.video = {...j.ready.video, ok: true, provider: 'file', file: {id: 1, name: 'dars.mp4', kind: 'mp4', size: 1000}, captions: [{id: 9, lang: 'uz', label: "O'zbekcha", cues: 12}, {id: 10, lang: 'ru', label: 'Ruscha', cues: 3}]};
    await route.fulfill({response: r, json: j});
  });
  await page.evaluate(() => kxReload()); await page.waitForSelector('.kx-cap');
  ok((await page.$$('.kx-chip')).length === 2 && /O'zbekcha/.test(await page.textContent('.kx-cap-h')), `[${tag}] video fayl: mavjud subtitrlar chip ko'rinishida (2 ta)`);
  ok(!(await page.$('#kxAuto')) && !(await page.$('#kxAutoMsg')), `[${tag}] «Avtomatik subtitr (AI)» tugmasi yashirilgan (video fayl bo'lsa ham)`);
  await page.screenshot({path: `${env.OUT || '/tmp/kx'}/${tag}_1b_video_fayl.png`, fullPage: true});
  await page.unroute(topicRx);
  await page.evaluate(() => kxReload()); await page.waitForSelector('.kx-grid'); await sleep(300);
}
module.exports = {subject, materials};
