#!/usr/bin/env node
/* «Ko'p faylni yuklash» (static/konstruktor.js: kxbParse / kxbMatch / kxbErr, fan sahifasidagi #dsBulkUp) tekshiruvi.
   1) Sof funksiyalar — node'da (brauzersiz): ~20 xil fayl nomi → dars turi / raqami / yuklash turi.
   2) Brauzer (PW + CHROME berilganda): 3 ta Word + test + moslanmaydigan + buzuq fayl → jadval → qo'lda tanlash → yuklash → xulosa → «Konstruktorda ochish».
   tests/test_konstruktor.py chaqiradi: B, KX_UID, KX_PW, KX_CID, BK_DIR (fayllar katalogi), OUT. */
const fs = require('fs'), vm = require('vm'), path = require('path');
let bad = 0;
const ok = (c, m) => { console.log((c ? '✓ ' : '✗ ') + m); if (!c) bad++; };
const sleep = ms => new Promise(r => setTimeout(r, ms));

/* ---- 1. sof funksiyalar ---- */
const ctx = vm.createContext({console, pkErrMsg: d => (d && d.message) || (d && typeof d.detail === 'string' && d.detail) || 'Xatolik yuz berdi'});
vm.runInContext(fs.readFileSync(path.join(__dirname, '..', 'static', 'konstruktor.js'), 'utf8'), ctx);
const parse = vm.runInContext('kxbParse', ctx), match = vm.runInContext('kxbMatch', ctx), dups = vm.runInContext('kxbDups', ctx), errf = vm.runInContext('kxbErr', ctx);
const lessons = [];
const KD = [['maruza', 'L', 15], ['amaliy', 'A', 30], ['seminar', 'S', 3], ['laboratoriya', 'Lab', 4], ['mustaqil', 'MT', 3]];
let key = 0; KD.forEach(([k, p, n]) => { for (let i = 1; i <= n; i++) lessons.push({key: ++key, kind: k, no: i, code: p + i}); });
const code = name => { const r = match([{name, size: 10}], lessons)[0]; return r.skip ? 'SKIP' : `${r.code}/${r.kind}`; };
const CASES = [
  ["1-ma'ruza.docx", 'L1/matn'], ['L3.pptx', 'L3/taqdimot'], ['3-mavzu.docx', 'L3/matn'], ['maruza_07.docx', 'L7/matn'], ['07.docx', 'L7/matn'],
  ['12 Mikroiqtisodiyot.pdf', 'L12/taqdimot'], ['Mikroiqtisodiyot_L01_xapi.docx', 'L1/matn'], ['Ma’ruza 5 (yangi).DOCX', 'L5/matn'],
  ['5-mavzu test.docx', 'L5/test'], ['test_09.docx', 'L9/test'], ['A5.docx', 'A5/matn'], ['3-amaliy.pptx', 'A3/taqdimot'], ['dars3_video.mp4', 'L3/video'],
  ['Lab4.docx', 'Lab4/matn'], ['Seminar-2.pdf', 'S2/taqdimot'], ['mt_2.docx', 'MT2/matn'], ['1-ma\'ruza.MP4', 'L1/video'],
  ['final_v2.docx', 'SKIP'], ['2024-yil hisobot.docx', 'SKIP'], ['L99.docx', 'SKIP'], ['~$ma\'ruza1.docx', 'SKIP'], ['rasm_3.jpg', 'SKIP'], ['izoh.docx', 'SKIP'], ['latest_notes.docx', 'SKIP'],
];
for (const [n, want] of CASES) { const got = code(n); ok(got === want, `moslashtirish: «${n}» → ${got}${got === want ? '' : ` (kutilgan: ${want})`}`); }
ok(parse('test_09.docx').how === 'taxminiy' && parse('07.docx').how === 'raqam' && parse('L3.pptx').how === 'aniq', 'ishonch darajasi: aniq / raqam bo\'yicha / taxminiy');
const dp = dups(match([{name: '3-mavzu.docx', size: 1}, {name: 'L3.docx', size: 1}, {name: 'L3.pptx', size: 1}], lessons));
ok(Object.keys(dp).length === 1 && dp[1] === 0, 'takror: bir darsga ikkita «Ma\'ruza matni» — oxirgisi almashtiradi, taqdimot — takror emas');
ok(/MB/.test(errf({status: 413, data: {detail: 'Fayl hajmi 50 MB dan oshmasin'}}, 1)) && /juda katta/.test(errf({status: 413, data: {}}, 3e7)), 'xato matni: 413 (hajm) o\'qiladigan');
ok(/Juda ko'p so'rov/.test(errf({status: 429, data: {}})) && /Server xatosi \(502\)/.test(errf({status: 502, data: {}})) && /ruxsat yo'q/.test(errf({status: 403, data: {}})), 'xato matni: 429 / 5xx / 403');

/* ---- 2. brauzer ---- */
(async () => {
  if (!process.env.PW || !process.env.CHROME || !process.env.B || !process.env.BK_DIR) { console.log('– PW/CHROME/B/BK_DIR berilmagan — brauzer qismi o\'tkazib yuborildi'); process.exit(bad ? 1 : 0); }
  const {chromium} = require(process.env.PW);
  const B = process.env.B, OUT = process.env.OUT || '/tmp/bk', D = process.env.BK_DIR, cid = +process.env.KX_CID;
  fs.mkdirSync(OUT, {recursive: true});
  const f = n => path.join(D, n);
  const b = await chromium.launch({executablePath: process.env.CHROME, headless: true});
  try {
    for (const [W, H, tag] of [[1440, 900, 'd'], [390, 844, 'm']]) {
      const c = await b.newContext({viewport: {width: W, height: H}}), page = await c.newPage();
      const errs = []; page.on('pageerror', e => errs.push(String(e)));
      await page.addInitScript(() => { try { localStorage.setItem('dsVer', 'a'); } catch (e) {} });
      const lg = await page.request.post(B + '/api/login', {data: {user_id: +process.env.KX_UID, password: process.env.KX_PW}});
      if (!lg.ok()) throw new Error('login ' + lg.status());
      await page.goto(B + '/'); await sleep(1200);
      await page.evaluate(id => { DS.cid = id; DS.data = null; go('paket', {tab: 'fanlar'}); }, cid);
      await page.waitForSelector('#dsBulkUp', {timeout: 20000}); await sleep(700);
      ok(await page.isVisible('#dsBulkUp'), `[${tag}] fan sahifasida «Ko'p faylni yuklash» tugmasi bor`);
      await page.click('#dsBulkUp'); await page.waitForSelector('#kxbPanel #kxbIn', {state: 'attached'});
      ok(await page.isVisible('#kxbDrop'), `[${tag}] panel ochildi: tashlash maydoni`);
      // tag bo'yicha boshqa darslar (m — d dan keyin ham ishlashi uchun bir xil fayllar, qayta yuklash bu yerda ham o'tadi)
      await page.setInputFiles('#kxbIn', ["1-ma'ruza.docx", 'L3.docx', 'maruza_08.docx', 'L2 test.docx', 'izoh.docx', 'L9.pptx'].map(f));
      await page.waitForSelector('.kxb-r'); await sleep(300);
      const rows = await page.$$eval('.kxb-r', es => es.map(e => ({name: e.querySelector('.kxb-f b').textContent, lesson: e.querySelector('[data-kxb-l]').value, kind: e.querySelector('[data-kxb-k]').value, skip: e.classList.contains('skip')})));
      const byName = Object.fromEntries(rows.map(r => [r.name, r]));
      ok(rows.length === 6, `[${tag}] jadvalda 6 ta fayl`);
      ok(['1-ma\'ruza.docx', 'L3.docx', 'maruza_08.docx', 'L2 test.docx'].every(n => byName[n] && +byName[n].lesson > 0 && !byName[n].skip), `[${tag}] 4 ta fayl nomidagi raqam bo'yicha moslandi`);
      ok(byName['L2 test.docx'].kind === 'test' && byName['L9.pptx'].kind === 'taqdimot' && byName['L3.docx'].kind === 'matn', `[${tag}] turi taxmin qilindi: test / taqdimot / matn`);
      ok(byName['izoh.docx'].skip && byName['izoh.docx'].lesson === '0', `[${tag}] moslanmagan fayl (izoh.docx) alohida ajratilgan — darsi tanlanmagan`);
      ok(await page.isDisabled('[data-kxb="go"]') === false && /5 ta/.test(await page.textContent('[data-kxb="go"]')), `[${tag}] «Yuklashni boshlash (5 ta)» — moslanmagan izoh.docx hisobga olinmaydi`);
      if (tag === 'm') ok(!(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1)), '[m] 390 px: ko\'rib chiqish jadvalida gorizontal siljish yo\'q');
      // qo'lda tanlash: izoh.docx → L5 (dars select'idan, 5-dars kaliti = 5)
      await page.selectOption('[data-kxb-l="4"]', '5'); await sleep(200);
      ok(!(await page.$eval('.kxb-r[data-i="4"]', e => e.classList.contains('skip'))), `[${tag}] izoh.docx darsi qo'lda tanlandi (L5) — endi yuklanadi`);
      await page.screenshot({path: `${OUT}/${tag}_bulk_1_preview.png`, fullPage: true});
      await page.click('[data-kxb="go"]');
      await page.waitForFunction(() => document.querySelector('#kxbSum')?.textContent.includes('Tugadi'), null, {timeout: 120000});
      const st = await page.$$eval('.kxb-r', es => es.map(e => ({name: e.querySelector('.kxb-f b').textContent, text: e.querySelector('.kxb-s').textContent.trim()})));
      const S = Object.fromEntries(st.map(r => [r.name, r.text]));
      ok(['1-ma\'ruza.docx', 'L3.docx', 'maruza_08.docx', 'izoh.docx'].every(n => /^✓/.test(S[n])), `[${tag}] 3 ta Word + qo'lda tanlangan fayl yuklandi (✓)`);
      ok(/^✓.*Test/.test(S['L2 test.docx']), `[${tag}] «test» fayli test sifatida yuklandi: ${S['L2 test.docx']}`);
      ok(/^✗/.test(S['L9.pptx']) && S['L9.pptx'].length > 12, `[${tag}] buzuq fayl — o'qiladigan xato bilan: ${S['L9.pptx'].slice(0, 90)}`);
      const sm = await page.textContent('#kxbSum');
      ok(/5 ta yuklandi/.test(sm) && /1 ta xato/.test(sm), `[${tag}] yakuniy xulosa: ${sm.trim().slice(0, 80)}`);
      ok((await page.$$('[data-kxb-open]')).length === 5, `[${tag}] har yuklangan faylda «Konstruktorda ochish» havolasi`);
      ok(await page.isVisible('[data-kxb="retry"]'), `[${tag}] «Yuklanmaganlarni qayta yuklash» tugmasi`);
      await page.screenshot({path: `${OUT}/${tag}_bulk_2_done.png`, fullPage: true});
      // server tomonida haqiqatan tushganini tekshirish
      const t3 = await (await page.request.get(`${B}/api/paket/courses/${cid}/topics/3`)).json();
      ok(t3.ready && t3.ready.text && t3.ready.text.ok, `[${tag}] L3 ma'ruza matni serverda bor`);
      // hajm chegarasi — mijoz tomonida o'qiladigan xabar
      await page.click('[data-kxb="close"]'); await page.waitForSelector('#dsBulkUp'); await sleep(500);
      await page.click('#dsBulkUp'); await page.waitForSelector('#kxbIn', {state: 'attached'});
      const lim0 = await page.evaluate(() => { const o = PK.meta.limits.asset_mb; PK.meta.limits.asset_mb = 0.0001; return o; });
      await page.setInputFiles('#kxbIn', [f('L3.docx')]); await page.waitForSelector('.kxb-r');
      await page.click('[data-kxb="go"]'); await page.waitForFunction(() => document.querySelector('#kxbSum')?.textContent.includes('Tugadi'), null, {timeout: 30000});
      ok(/Fayl katta/.test(await page.textContent('.kxb-s')), `[${tag}] hajm chegarasidan oshgan fayl — «Fayl katta: … MB (chegara …)» xabari`);
      await page.evaluate(v => { PK.meta.limits.asset_mb = v; }, lim0);
      // Esc — panelni yopadi
      await page.click('[data-kxb="close"]'); await page.waitForSelector('#dsBulkUp'); await sleep(500);
      await page.click('#dsBulkUp'); await page.waitForSelector('#kxbPanel');
      await page.keyboard.press('Escape'); await sleep(300);
      ok(!(await page.$('#kxbPanel')), `[${tag}] Esc — panel yopiladi`);
      // «Konstruktorda ochish»
      await page.click('#dsBulkUp'); await page.waitForSelector('#kxbIn', {state: 'attached'});
      await page.setInputFiles('#kxbIn', [f('L3.docx')]); await page.waitForSelector('.kxb-r');
      await page.click('[data-kxb="go"]'); await page.waitForFunction(() => document.querySelector('#kxbSum')?.textContent.includes('Tugadi'), null, {timeout: 60000});
      await page.click('[data-kxb-open]'); await page.waitForSelector('.kx-grid', {timeout: 20000});
      ok((await page.textContent('.kx-code')).trim() === 'L3', `[${tag}] «Konstruktorda ochish» — L3 dars materiallari ochildi`);
      ok(!errs.length, `[${tag}] JS xatosi yo'q${errs.length ? ': ' + errs[0].slice(0, 160) : ''}`);
      await c.close();
    }
  } catch (e) { try { const pg = b.contexts()[0].pages()[0]; await pg.screenshot({path: (process.env.OUT || '/tmp/bk') + '/fail.png'}); } catch (_) {} ok(false, 'Istisno: ' + String(e && e.message || e).split('\n')[0]); }
  await b.close();
  process.exit(bad ? 1 : 0);
})();
