#!/usr/bin/env node
/* «Taqdimot» sahifasi — o'qituvchi UX tuzatishlari regressiya tekshiruvi (1440 va 390 px, yorug' va qorong'i).
   tests/test_zanjir_ux_taqdimot.py chaqiradi. Muhit: B (server), PW_ (parol), T_UID (o'qituvchi), CID/KURS/DIRN (fan, kurs, yo'nalish nomi),
   LK0, LK1, LK2 (uch dars kaliti), OUT (skrinshotlar), PW (playwright-core yo'li), CHROME.
   Backend maydonlari (lesson_sent_version, decks, changed_since_send, doc_topic_no, pptx, last_send) bo'lmasa ham test o'tishi uchun javoblar
   page.route bilan SHARTNOMA bo'yicha to'ldiriladi — shu bilan UI mantig'i backenddan mustaqil tekshiriladi.
   Tekshiriladi: yuborish dialogi (versiya darsdan, boshqa taqdimot ogohlantirishi, eskirgan tab, «o'zgarish yo'q», fayl ma'lumoti, xato modal ichida,
   so'rov ketayotganda Esc/tashqariga bosish yopmaydi, unchanged), hujjat mavzu raqami, bir darsga ikkinchi taqdimot, mobil kartochka ro'yxat va versiyalar,
   44 px tegish maydoni, chip wrap, 320 px tugma, sticky tugmalar (390×380, 320×568), bo'sh yuklama, fayl turi xatosi (role=alert), ARIA (tablist, aria-disabled,
   h2), qorong'i mavzu kontrasti, saqlanmagan tahrir (confirm, beforeunload, yangilangandan keyin tiklash), aria-busy / ikki marta bosish. */
const { chromium } = require(process.env.PW || 'playwright-core');
const fs = require('fs');
const E = process.env, B = E.B, OUT = E.OUT || '/tmp/zanjir_ux_taqdimot';
fs.mkdirSync(OUT, { recursive: true });
let bad = 0;
const ok = (c, m) => { console.log((c ? '✓ ' : '✗ ') + m); if (!c) bad++; };
const sleep = ms => new Promise(r => setTimeout(r, ms));
const TEXT = "Bozor iqtisodiyotida narx talab va taklif muvozanati orqali shakllanadi. ".repeat(3) +
  "\n## Talab qonuni\n- Narx oshsa talab kamayadi\n- Daromad ta'siri\n## Taklif qonuni\n- Narx oshsa taklif ortadi\n- Xarajatlar\n## Nazorat savollari\n- Talab qonuni nima?\n- Muvozanat narxi nima?\n";
const DECK_RE = /\/api\/taqdimot\/decks\/\d+$/, LES_RE = /\/api\/taqdimot\/lessons$/;

async function login(ctx) {
  const r = await ctx.request.post(B + '/api/login', { data: { user_id: +E.T_UID, password: E.PW_ } });
  if (!r.ok()) throw new Error('login ' + r.status());
}
const hs = p => p.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1);
/* JSON javobini (faqat GET) o'zgartirish */
async function patchJson(p, re, fn) {
  await p.route(re, async (route, req) => {
    if (req.method() !== 'GET') return route.continue();
    const resp = await route.fetch();
    let j = null; try { j = await resp.json(); } catch (e) { /* json emas */ }
    if (j === null || resp.status() >= 400) return route.fulfill({ response: resp });
    const out = await fn(j, req);
    return route.fulfill({ response: resp, json: out === undefined ? j : out });
  });
}
const mkDeck = (p, lkey, build) => p.evaluate(async ([cid, lkey, build, text]) => {
  const post = async (u, b) => (await fetch(u, { method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(b) })).json();
  const d = await post('/api/taqdimot/decks/text', { text, course_id: +cid, lkey: +lkey, title: 'UX sinov taqdimoti' });
  if (build) await post(`/api/taqdimot/decks/${d.id}/build`, {});
  return d.id;
}, [E.CID, lkey, build, TEXT]);
const delDeck = (p, id) => p.evaluate(id => fetch(`/api/taqdimot/decks/${id}/delete`, { method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json' }, body: '{}' }), id).catch(() => {});
const openDeck = async (p, id) => { await p.evaluate(id => { TQ.deck = null; return tqOpen(id); }, id); await p.waitForSelector('#tqEd #tqLes', { timeout: 20000 }); await sleep(150); };
/* tanlagich: har bosqich o'zi tanlangan bo'lsa (bitta kurs / yo'nalish) — qayta tanlanmaydi */
async function pickLesson(p, lkey) {
  const set = async (sel, val) => { const cur = await p.$eval(sel, e => e.value).catch(() => null); if (cur === String(val)) return; await p.selectOption(sel, String(val)); await sleep(80); };
  await set('[data-lp-k]', E.KURS); await set('[data-lp-d]', E.DIRN); await set('[data-lp-f]', E.CID); await set('[data-lp-l]', lkey);
}
const dlgClose = p => p.evaluate(() => document.querySelectorAll('.pk-modal-bg').forEach(x => x.remove()));
/* kichik tegish maydonlari (≥44×44) */
const small = (p, sel) => p.evaluate(s => [...document.querySelectorAll(s)].filter(e => e.offsetParent !== null && !e.disabled).map(e => { const r = e.getBoundingClientRect(); return [(e.getAttribute('aria-label') || e.textContent || e.className).trim().slice(0, 28), Math.round(r.width), Math.round(r.height)]; })
  .filter(x => x[1] < 43.5 || x[2] < 43.5), sel);
/* kontrast (WCAG) */
const contrast = (p, sel, kind) => p.evaluate(([sel, kind]) => {
  const px = s => { const m = (s.match(/[\d.]+/g) || []).map(Number); return { r: m[0], g: m[1], b: m[2], a: m[3] === undefined ? 1 : m[3] }; };
  const lin = v => { v /= 255; return v <= .03928 ? v / 12.92 : Math.pow((v + .055) / 1.055, 2.4); };
  const Lm = c => .2126 * lin(c.r) + .7152 * lin(c.g) + .0722 * lin(c.b);
  const mix = (f, b) => ({ r: f.r * f.a + b.r * (1 - f.a), g: f.g * f.a + b.g * (1 - f.a), b: f.b * f.a + b.b * (1 - f.a), a: 1 });
  const bgOf = el => { const st = []; for (let e = el; e; e = e.parentElement) { const c = px(getComputedStyle(e).backgroundColor); if (c.a > 0) { st.push(c); if (c.a === 1) break; } }
    let base = px(getComputedStyle(document.body).backgroundColor); if (base.a < 1) base = { r: 255, g: 255, b: 255, a: 1 }; for (let i = st.length - 1; i >= 0; i--) base = mix(st[i], base); return base; };
  const el = document.querySelector(sel); if (!el) return 0;
  const cs = getComputedStyle(el), bg = kind === 'border-out' ? bgOf(el.parentElement) : bgOf(el);
  const fg = mix(px(kind === 'text' ? cs.color : cs.borderTopColor), bg);
  const a = Lm(fg), b = Lm(bg); return (Math.max(a, b) + .05) / (Math.min(a, b) + .05);
}, [sel, kind]);

async function suite(b, W, H, theme, DK) {
  const tag = `${W}_${theme}`, mob = W < 761, dark = theme === 'dark';
  console.log(`\n=== ${W}×${H} · ${theme} ===`);
  const ctx = await b.newContext({ viewport: { width: W, height: H }, colorScheme: theme });
  await login(ctx);
  const p = await ctx.newPage(); const errs = []; p.on('pageerror', e => errs.push(String(e))); p.on('console', m => { if (m.type() === 'error' && !/Failed to load resource/.test(m.text())) errs.push(m.text()); });
  await p.goto(B + '/'); await sleep(1200);
  await p.evaluate(t => { document.documentElement.dataset.theme = t; }, theme);
  const shot = n => p.screenshot({ path: `${OUT}/${tag}_${n}.png` });
  const dlgs = [];
  p.on('dialog', d => { dlgs.push(d.message()); d.dismiss(); });

  /* ---------- A. «Yangi taqdimot» sahifasi ---------- */
  await p.evaluate(() => go('taqdimot')); await p.waitForSelector('.lp', { timeout: 20000 });
  const heads = await p.$$eval('.tq-sec .tq-h', hs => hs.map(h => h.textContent.trim()));
  ok(heads.length === 3 && /^1-qadam\. .*dars/i.test(heads[0]) && /^2-qadam\. Material/.test(heads[1]) && /^3-qadam\. Sozlamalar/.test(heads[2]), `Sahifa qadamlari: ${heads.join(' → ')}`);
  const body0 = await p.textContent('#v-taqdimot');
  ok(!/dl_courses/.test(body0) && !/AI siz/.test(body0), "Texnik / tushunarsiz atamalar yo'q (dl_courses, «AI siz (shablon)»)");
  ok(/Reja Word sarlavhalaridan tuziladi\. Sarlavhali fayl eng yaxshi natija beradi/.test(body0), "AI ulanmagan izohi: «Reja Word sarlavhalaridan tuziladi…»");
  ok(await p.$eval('.tq-head-r .tq-chip[title*="limiti"]', e => /^Bugungi limit: \d+ \/ \d+/.test(e.textContent)), "Limit belgisi: «Bugungi limit: n / N» (title bilan)");
  ok(await p.$eval('.tq-seg', e => e.getAttribute('role') === 'tablist' && [...e.querySelectorAll('button')].every(x => x.getAttribute('role') === 'tab' && x.hasAttribute('aria-selected')) && e.querySelectorAll('[aria-selected="true"]').length === 1), "Fayl yuklash / Matn yozish: role=tablist/tab + aria-selected");
  ok(await p.$eval('.tq-tabs', e => e.getAttribute('role') === 'tablist' && e.querySelectorAll('[role=tab][aria-selected="true"]').length === 1), "Sahifa tablari: tablist/tab + aria-selected");
  await p.fill('#tqTitle', 'Saqlanib qolishi kerak');
  await p.focus('#tqSeg_file'); await p.keyboard.press('ArrowRight'); await sleep(100);
  ok(await p.evaluate(() => document.activeElement.id === 'tqSeg_text' && document.querySelector('#tqSeg_text').getAttribute('aria-selected') === 'true' && !!document.querySelector('#tqText')), "Strelka tugmasi: «Matn yozish»ga o'tadi (fokus va tanlov birga)");
  ok(await p.inputValue('#tqTitle') === 'Saqlanib qolishi kerak', "Manba almashganda yozilgan mavzu nomi yo'qolmaydi");
  await p.fill('#tqText', 'Yozilgan matn ' .repeat(5)); await p.click('#tqSeg_file'); await p.click('#tqSeg_text');
  ok((await p.inputValue('#tqText')).startsWith('Yozilgan matn'), "Matn manbalar orasida saqlanadi");
  await p.click('#tqSeg_file');
  await p.setInputFiles('#tqFile', { name: 'eski.doc', mimeType: 'application/msword', buffer: Buffer.from('x') });
  await sleep(150);
  const al = await p.$('#tqProg [role="alert"]');
  ok(!!al && /\.docx/.test(await al.textContent()) && await p.isVisible('#tqProg'), "Noto'g'ri fayl turi (.doc): xato #tqProg ichida role=alert bilan");
  if (!mob && !dark) { await sleep(4600); ok(await p.isVisible('#tqProg [role="alert"]'), "Toast yo'qolgandan keyin ham xato sahifada turibdi"); }
  ok(await p.$eval('#tqFname', e => !/eski\.doc/.test(e.textContent)), "Noto'g'ri fayl tanlanmadi");
  await p.setInputFiles('#tqFile', { name: 'dars.docx', mimeType: 'application/octet-stream', buffer: Buffer.from('PK') });
  await sleep(100);
  ok(await p.$eval('#tqFname', e => /dars\.docx/.test(e.textContent)) && !(await p.$('#tqProg [role="alert"]')), "To'g'ri fayl (.docx) qabul qilindi, xato tozalandi");
  await shot('1_yangi');
  if (mob) {
    const sm = await small(p, '.tq-tabs button, .tq-seg button, #tqGo, .lp select, .tq-cb, .tq-grid select, .tq-grid input');
    ok(sm.length === 0, `390 px: «Yangi taqdimot» tugma/select/tablar ≥44 px` + (sm.length ? ' — kichik: ' + JSON.stringify(sm) : ''));
    ok(!(await hs(p)), '390 px: «Yangi taqdimot»da gorizontal siljish yo\'q');
  }

  /* ---------- B. yuklamada fan yo'q ---------- */
  await patchJson(p, LES_RE, () => ({ items: [] }));
  await p.evaluate(() => go('taqdimot')); await p.waitForSelector('#tqNoLes', { timeout: 20000 });
  const nl = await p.textContent('#tqNoLes');
  ok(/Sizga hali fan biriktirilmagan/.test(nl) && /Darsni belgilash/.test(nl) && /kafedra mudiriga murojaat qiling/.test(nl), "Fan yo'q: aniq xabar (kafedra mudiriga murojaat)");
  ok((await p.$$('#v-taqdimot .lp select')).length === 0 && !(await p.$('#tqLater')) && !/dl_courses/.test(await p.textContent('#v-taqdimot')), "Fan yo'q: 4 ta o'chirilgan tanlov va «dl_courses» yo'q");
  await shot('2_fan_yoq');
  await p.unroute(LES_RE);

  /* ---------- C. bir darsga ikkinchi taqdimot ---------- */
  await patchJson(p, LES_RE, j => { const it = j.items.find(i => i.id == E.CID); const l = it.lessons.find(x => x.key == E.LK1); l.decks = [{ id: 987654, title: 'Eski taqdimot X' }]; return j; });
  await p.evaluate(() => go('taqdimot')); await p.waitForSelector('.lp');
  await pickLesson(p, E.LK1); await sleep(200);
  const dup = await p.$('#tqDup .tq-warn');
  const dt = dup ? await dup.textContent() : '';
  ok(/«Eski taqdimot X» taqdimot bor/.test(dt) && /Uni oching/.test(dt) && /baribir yangisini yarating/.test(dt) && /\bL\d+ uchun/.test(dt), "Bir darsga ikkinchi taqdimot: «L? uchun «nom» taqdimot bor. Uni oching / baribir yangisini yarating»");
  await shot('3_ikkinchi_taqdimot');
  if (mob) ok(!(await hs(p)), "390 px: ogohlantirish bilan gorizontal siljish yo'q");
  await p.check('#tqLater'); await sleep(100);
  ok(!(await p.$('#tqDup .tq-warn')), "«Keyinroq belgilayman» — ogohlantirish yo'qoladi");
  await p.uncheck('#tqLater');
  await pickLesson(p, E.LK0); await sleep(100);
  ok(!(await p.$('#tqDup .tq-warn')), "Boshqa dars — ogohlantirish yo'q");
  await p.unroute(LES_RE);
  await p.evaluate(() => { TQ.pick = null; TQ.later = false; });

  /* ---------- D. muharrir (PPTX yaratilmagan taqdimot) ---------- */
  const dNew = DK.A;
  await openDeck(p, dNew);
  ok(await p.$eval('#tqH2', e => e.tagName === 'H2' && /Taqdimot muharriri/.test(e.textContent)), "Muharrirda sahifa sarlavhasi h2 (ekran o'quvchi uchun)");
  ok(await p.$eval('#tqLes .tq-les-l', e => /Dars kodi:/.test(e.textContent)), "Dars kodi oldida «Dars kodi:» yorlig'i");
  const snd = await p.$eval('#tqSend', e => ({ dis: e.disabled, ad: e.getAttribute('aria-disabled'), db: e.getAttribute('aria-describedby'), hint: document.getElementById(e.getAttribute('aria-describedby'))?.textContent || '' }));
  ok(snd.ad === 'true' && !snd.dis && snd.db === 'tqSendHint' && /PPTX yaratish/.test(snd.hint), "Yuborish tugmasi: aria-disabled=true (disabled emas) + aria-describedby=tqSendHint, sabab ko'rinadi");
  await p.focus('#tqSend');
  ok(await p.evaluate(() => document.activeElement.id === 'tqSend'), "O'chirilgan «Yuborish» tugmasi klaviatura fokusini oladi");
  await p.click('#tqSend', { force: true }); await sleep(200);
  ok(!(await p.$('.pk-modal-bg')), "aria-disabled tugma bosilganda dialog ochilmaydi");
  const chipsInfo = await p.$eval('.tq-chips', e => ({ wrap: getComputedStyle(e).flexWrap, titles: [...e.querySelectorAll('.tq-chip')].every(c => c.title) }));
  ok(chipsInfo.wrap === 'wrap' && chipsInfo.titles, "Sarlavha chiplari: flex-wrap:wrap, har birida title");
  ok(await p.$eval('.tq-eng', e => (e.offsetParent !== null) === !(window.innerWidth < 761)), mob ? "Telefonda «Shablon asosida» belgisi yashirin" : "Kompyuterda dvijok belgisi ko'rinadi (aniq nomi)");
  ok(/Shablon asosida|AI|Sinov/.test(await p.$eval('.tq-chips', e => e.textContent)) && !/AI siz/.test(await p.textContent('#tqEd')), "Dvijok belgisi tushunarli («AI siz (shablon)» emas)");
  ok(await p.$eval('.tq-keys', e => { const v = s => e.querySelector(s).offsetParent !== null; return window.innerWidth < 761 ? (v('.tq-keys-m') && !v('.tq-keys-d')) : (v('.tq-keys-d') && !v('.tq-keys-m')); }), mob ? "Telefonda yo'riqnoma: «⋯ tugmasi — slayd menyusi»" : "Kompyuterda yo'riqnoma: klaviatura va o'ng tugma");
  if (mob) ok(/«⋯» tugmasi — slayd menyusi/.test(await p.textContent('.tq-keys-m')), "Yo'riqnoma matni: «⋯» tugmasi — slayd menyusi");
  ok(!(await hs(p)), `${W} px: muharrirda gorizontal siljish yo'q`);
  ok(await p.$eval('#tqMetaB', e => e.getBoundingClientRect().width > 60) && await p.$eval('#tqMetaT', e => e.scrollHeight <= e.clientHeight + 1 || getComputedStyle(e).webkitLineClamp === '2'), "Mavzu sarlavhasi qisqarib yo'qolmaydi (2 qatorgacha ko'rinadi)");
  await shot('4_muharrir_reja');
  if (mob) {
    const sm = await small(p, '.tq-bar .btn, .tq-bar .tq-meta-b, .tq-les .btn, .tq-th-m, .tq-pn .btn, .tq-fh select, .tq-fh input, .tq-notes summary, .tq-th-add');
    ok(sm.length === 0, '390 px: muharrirdagi tugmalar, ⋯ menyu, select ≥44×44' + (sm.length ? ' — kichik: ' + JSON.stringify(sm) : ''));
    await p.click('.tq-th-m'); await p.waitForSelector('#tqMenu:not([hidden])');
    const ms = await small(p, '#tqMenu button');
    ok(ms.length === 0, '390 px: slayd menyusi elementlari ≥44 px' + (ms.length ? ' — kichik: ' + JSON.stringify(ms) : ''));
    await shot('5_slayd_menyusi');
    await p.keyboard.press('Escape'); await sleep(100);
    ok(await p.$eval('#tqMenu', e => e.hidden), "Esc slayd menyusini yopadi");
  }
  if (dark) {
    const cn = await contrast(p, '.tq-th-n', 'text'), cb = await contrast(p, '.tq-th.on', 'border-out');
    ok(cn >= 4.5, `Qorong'i mavzu: slayd raqami kontrasti ${cn.toFixed(2)}:1 (≥4.5)`);
    ok(cb >= 3, `Qorong'i mavzu: tanlangan slayd chegarasi kontrasti ${cb.toFixed(2)}:1 (≥3)`);
  } else {
    const cn = await contrast(p, '.tq-th-n', 'text'), cb = await contrast(p, '.tq-th.on', 'border-out');
    ok(cn >= 4.5 && cb >= 3, `Yorug' mavzu: slayd raqami ${cn.toFixed(2)}:1, tanlangan chegara ${cb.toFixed(2)}:1`);
  }

  /* hujjat mavzu raqami */
  const own = await p.evaluate(() => String(TQ.deck.topic_no || TQ.deck.outline.topic_no || ''));
  await patchJson(p, DECK_RE, j => { j.doc_topic_no = 77; return j; });
  await openDeck(p, dNew);
  const tw = await p.$('#tqTopicWarn');
  ok(!!tw && /Hujjatda «77-mavzu» yozilgan, siz esa L\d+ ni tanladingiz\. To'g'rimi\?/.test(await tw.textContent()) && !!(await p.$('#tqChangeLes')), "Hujjat mavzu raqami farq qilsa: sariq izoh + «Darsni o'zgartirish»");
  await shot('6_mavzu_raqami');
  await p.click('#tqChangeLes'); await p.waitForSelector('.pk-modal .lp');
  ok((await p.textContent('.pk-modal h3')).includes('Darsni belgilash'), "«Darsni o'zgartirish» — dars tanlash oynasini ochadi");
  await dlgClose(p);
  await p.unroute(DECK_RE);
  await patchJson(p, DECK_RE, j => { j.doc_topic_no = +own || own; return j; });
  await openDeck(p, dNew);
  ok(!(await p.$('#tqTopicWarn')), "Hujjat raqami tanlangan dars bilan mos — izoh yo'q");
  await p.unroute(DECK_RE);

  /* saqlanmagan tahrir */
  await openDeck(p, dNew);
  await p.fill('#tqForm [data-f="title"]', 'Saqlanmagan sarlavha'); await sleep(100);
  ok(await p.evaluate(() => TQ.dirty === true), "Tahrir — TQ.dirty = true");
  dlgs.length = 0;
  await p.evaluate(() => go('mywork')); await sleep(300);
  ok(dlgs.length === 1 && /saqlanmagan/i.test(dlgs[0]) && await p.evaluate(() => !document.querySelector('#v-taqdimot').classList.contains('hidden') && !!document.querySelector('#tqEd')), "Menyu orqali chiqishda confirm so'raladi; «Bekor» — muharrirda qolinadi");
  ok(await p.evaluate(() => { const e = new Event('beforeunload', { cancelable: true }); window.dispatchEvent(e); return e.defaultPrevented; }), "beforeunload: saqlanmagan tahrirda brauzer ogohlantiradi");
  await p.evaluate(() => go('taqdimot')); await sleep(400);
  ok(await p.evaluate(() => TQ.dirty === true && document.querySelector('#tqForm [data-f="title"]')?.value === 'Saqlanmagan sarlavha'), "Menyudan «Taqdimot»ni qayta bosish saqlanmagan tahrirni serverdan o'qib yo'qotmaydi");
  p.removeAllListeners('dialog'); p.on('dialog', d => { dlgs.push(d.message()); d.accept(); });
  dlgs.length = 0;
  await p.evaluate(() => go('mywork')); await sleep(400);
  ok(dlgs.length === 1 && await p.evaluate(() => document.querySelector('#v-taqdimot').classList.contains('hidden') && TQ.dirty === false), "«Ha» — boshqa bo'limga o'tiladi");
  p.removeAllListeners('dialog'); p.on('dialog', d => { dlgs.push(d.message()); d.dismiss(); });
  ok(await p.evaluate(() => !location.hash.startsWith('#taqdimot')), "Boshqa bo'limga o'tilganda #taqdimot xeshi olib tashlanadi");

  /* yangilangandan keyin muharrir tiklanadi */
  await p.evaluate(() => go('taqdimot')); await p.waitForFunction(() => location.hash.startsWith('#taqdimot/'), null, { timeout: 20000 }); await sleep(200);
  ok(await p.evaluate(id => location.hash === '#taqdimot/' + id && sessionStorage.getItem('tqDeck') === String(id), dNew), "Ochiq muharrir: #taqdimot/<id> va sessionStorage");
  await p.reload(); await p.waitForSelector('#tqEd #tqLes', { timeout: 30000 });
  ok(await p.evaluate(id => TQ.deck && TQ.deck.id === id, dNew), "Sahifa yangilandi — muharrir o'sha taqdimot bilan tiklandi");
  await p.click('#tqBack'); await sleep(300);
  ok(await p.evaluate(() => !location.hash.startsWith('#taqdimot') && !sessionStorage.getItem('tqDeck')), "«←» — tiklash belgisi tozalandi");
  await p.reload(); await sleep(1500);
  ok(!(await p.$('#tqEd')), "Orqaga qaytilgandan keyin yangilansa muharrir ochilmaydi");

  /* ---------- E. yuborish dialogi ---------- */
  const dSent = DK.B;
  await p.evaluate(() => go('taqdimot')); await p.waitForSelector('.lp');
  await openDeck(p, dSent);
  ok(await p.$eval('#tqSend', e => e.getAttribute('aria-disabled') === 'false'), "PPTX tayyor — «Yuborish» yoqildi");
  /* ikki marta bosish */
  await p.route(DECK_RE, async (route, req) => { if (req.method() === 'GET') await sleep(700); await route.continue(); });
  await p.evaluate(() => { const b = document.querySelector('#tqSend'); b.click(); b.click(); });
  ok(await p.$eval('#tqSend', e => e.getAttribute('aria-busy') === 'true'), "Dialog tayyorlanayotganda tugmada aria-busy=true");
  await sleep(1800);
  ok((await p.$$('.pk-modal-bg')).length === 1, "Tez ikki marta bosish — bitta dialog ochiladi");
  ok(await p.$eval('#tqSend', e => !e.hasAttribute('aria-busy')), "Dialog ochilgach aria-busy olib tashlanadi");
  await dlgClose(p); await p.unroute(DECK_RE);

  /* boshqa taqdimot orqali yuborilgan dars (shartnoma maydonlari) */
  await patchJson(p, DECK_RE, j => {
    j.lesson = { ...j.lesson, lesson_sent_version: 5, lesson_sent_deck_id: j.id + 1000, lesson_sent_deck_title: 'Boshqa taqdimot', lesson_sent_at: '2026-11-15T14:20:00' };
    j.pptx = { filename: 'taqdimot_talab.pptx', size: 2457600, built_at: '2026-11-16T09:05:00' }; j.changed_since_send = true; return j;
  });
  await openDeck(p, dSent);
  ok(await p.$eval('#tqLes', e => /Darsga v5 yuborilgan \(boshqa taqdimot\)/.test(e.textContent)), "Lavhada: «Darsga v5 yuborilgan (boshqa taqdimot)»");
  ok(await p.$eval('#tqSend', e => /\(v6\)/.test(e.textContent)), "Tugma versiyasi DARS bo'yicha: (v6), taqdimotning o'zi bo'yicha emas");
  await p.click('#tqSend'); await p.waitForSelector('.pk-modal #tqSendNote');
  const mt = await p.textContent('.pk-modal');
  ok(/yangi versiya — v6/.test(mt) && /v5 tarixda qoladi/.test(mt), "Dialog: v6 (dars bo'yicha), «v5 tarixda qoladi»");
  ok(/Bu darsga allaqachon v5 yuborilgan \(boshqa taqdimot: «Boshqa taqdimot»\)\. Yuborsangiz v6 bo'lib, studiya va bo'lim yangisini ko'radi\. Davom etasizmi\?/.test(mt), "Boshqa taqdimot ogohlantirishi (sariq) — to'liq matn");
  ok(/taqdimot_talab\.pptx/.test(mt) && /2\.3 MB/.test(mt) && /16\.11\.2026, 09:05/.test(mt), "Fayl nomi, hajmi va PPTX yaratilgan vaqti ko'rsatiladi");
  ok(await p.$eval('[data-ok]', e => /Yuborish \(v6\)/.test(e.textContent)), "Tasdiqlash tugmasi: «Yuborish (v6)»");
  const ta = await p.$eval('#tqSendNote', e => ({ rows: e.rows, h: e.getBoundingClientRect().height, mh: parseFloat(getComputedStyle(e).minHeight) }));
  ok(ta.rows === 3 && ta.mh >= 64 && ta.h < 200, `Izoh maydoni 3 qator (min-height ${ta.mh}px, balandligi ${Math.round(ta.h)}px)`);
  ok(await p.$eval('.pk-modal [data-ok]', e => getComputedStyle(e.parentElement).position === 'sticky'), "Tugmalar paneli sticky (pastda yopishib turadi)");
  ok(await p.$eval('.pk-modal', e => e.scrollWidth <= e.clientWidth + 1) && !(await hs(p)), `${W} px: dialog gorizontal sig'adi`);
  await shot('7_yuborish_boshqa_taqdimot');
  if (mob) { const sm = await small(p, '.tq-dlg .btn, .tq-dlg textarea'); ok(sm.length === 0, '390 px: dialog tugmalari ≥44 px' + (sm.length ? ' — kichik: ' + JSON.stringify(sm) : '')); }
  await p.keyboard.press('Escape'); await sleep(150);
  ok(!(await p.$('.pk-modal-bg')), "Esc (so'rov ketmayotganda) dialogni yopadi");
  ok(await p.evaluate(() => document.activeElement && document.activeElement.id === 'tqSend'), "Dialog yopilgach fokus «Yuborish» tugmasiga qaytadi");
  await p.unroute(DECK_RE);

  /* eskirgan tab: boshqa tabda v5 yuborilgan — bu tab v6 ni ko'radi (dialog ochilganda qayta yuklanadi) */
  let n = 0;
  await patchJson(p, DECK_RE, j => { n++; j.lesson = { ...j.lesson, lesson_sent_version: n >= 2 ? 6 : 5, lesson_sent_deck_id: j.id, lesson_sent_deck_title: j.title, lesson_sent_at: '2026-11-16T10:00:00' }; j.changed_since_send = true; return j; });
  await openDeck(p, dSent);
  ok(await p.$eval('#tqLes', e => /v5 yuborilgan/.test(e.textContent)) && await p.$eval('#tqSend', e => /\(v6\)/.test(e.textContent)), "Eskirgan tab: dastlab v5 / tugma (v6)");
  await p.click('#tqSend'); await p.waitForSelector('.pk-modal #tqSendNote');
  ok(/yangi versiya — v7/.test(await p.textContent('.pk-modal')) && await p.$eval('[data-ok]', e => /Yuborish \(v7\)/.test(e.textContent)) && await p.$eval('#tqLes', e => /v6 yuborilgan/.test(e.textContent)), "Dialog ochilganda ma'lumot qayta yuklandi: v6 yuborilgan → dialogda v7");
  await dlgClose(p); await p.unroute(DECK_RE);

  /* o'zgarish yo'q */
  await patchJson(p, DECK_RE, j => {
    j.lesson = { ...j.lesson, lesson_sent_version: 3, lesson_sent_deck_id: j.id, lesson_sent_deck_title: j.title, lesson_sent_at: '2026-11-16T14:20:00' };
    j.changed_since_send = false; j.last_send = { version: 3, at: '2026-11-15T14:20:00', size: 1000, filename: 'taqdimot.pptx', sha256_short: 'abc123' }; return j;
  });
  await openDeck(p, dSent);
  ok(await p.$eval('#tqLes', e => /v3 yuborilgan · (14:20|15\.11\.2026, 14:20)/.test(e.textContent)), "Yuborilgan holat: «v3 yuborilgan · 14:20»");
  ok(await p.$eval('#tqSend', e => !e.classList.contains('primary')), "Yuborilgach asosiy tugma ikkinchi darajali (primary emas)");
  ok(await p.$eval('#tqSendHint', e => /o'zgarish yo'q/.test(e.textContent)), "Tugma ostida: «…beri o'zgarish yo'q»");
  await p.click('#tqSend'); await p.waitForSelector('.pk-modal #tqSendNote');
  ok(/Oxirgi yuborishdan \(v3, 15\.11\.2026\) beri o'zgarish yo'q — bir xil fayl yangi versiya bo'ladi\./.test(await p.textContent('.pk-modal')), "Dialog: «Oxirgi yuborishdan (v3, sana) beri o'zgarish yo'q — bir xil fayl yangi versiya bo'ladi»");
  await shot('8_yuborish_ozgarish_yoq');
  await dlgClose(p); await p.unroute(DECK_RE);

  /* xato modal ichida (role=alert) */
  await openDeck(p, dSent);
  await p.route(/\/api\/taqdimot\/decks\/\d+\/send$/, r => r.fulfill({ status: 409, contentType: 'application/json', body: JSON.stringify({ detail: "Sinov xatosi: yuborib bo'lmadi" }) }));
  await p.click('#tqSend'); await p.waitForSelector('.pk-modal #tqSendNote'); await p.click('.pk-modal [data-ok]'); await sleep(400);
  const er = await p.$('.pk-modal #tqSendErr[role="alert"]');
  ok(!!er && await er.isVisible() && /Sinov xatosi/.test(await er.textContent()) && !!(await p.$('.pk-modal')), "Yuborish xatosi modal ICHIDA role=alert blokida, dialog ochiq qoladi");
  ok(await p.$eval('.pk-modal [data-ok]', e => !e.disabled && /Yuborish \(v\d+\)/.test(e.textContent)), "Xatodan keyin tugma qayta ishlaydi (matni tiklandi)");
  await shot('9_yuborish_xato');
  await dlgClose(p); await p.unroute(/\/api\/taqdimot\/decks\/\d+\/send$/);

  /* unchanged:true */
  await openDeck(p, dSent);
  await p.route(/\/api\/taqdimot\/decks\/\d+\/send$/, async route => {
    const d = await (await route.fetch({ url: route.request().url().replace(/\/send$/, ''), method: 'GET' })).json();
    return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ ...d, unchanged: true, version: 3, send: { version: 3, code: d.lesson.full_code }, paket_error: null }) });
  });
  await p.click('#tqSend'); await p.waitForSelector('.pk-modal #tqSendNote'); await p.click('.pk-modal [data-ok]'); await sleep(500);
  ok(!(await p.$('.pk-modal')) && /Bu fayl allaqachon v3 sifatida yuborilgan/.test(await p.textContent('#toast') + await p.textContent('#tqSendHint')), "unchanged:true javobi: «Bu fayl allaqachon v3 sifatida yuborilgan» xabari");
  await p.unroute(/\/api\/taqdimot\/decks\/\d+\/send$/); await p.unroute(DECK_RE).catch(() => {});

  /* so'rov ketayotganda Esc / tashqariga bosish oynani yopmaydi; haqiqiy yuborish */
  await openDeck(p, dSent);
  await p.route(/\/api\/taqdimot\/decks\/\d+\/send$/, async route => { await sleep(1400); await route.continue(); });
  await p.click('#tqSend'); await p.waitForSelector('.pk-modal #tqSendNote'); await p.fill('#tqSendNote', 'Sinov izohi');
  await p.click('.pk-modal [data-ok]'); await sleep(250);
  ok(await p.$eval('.pk-modal [data-ok]', e => /Yuborilmoqda…/.test(e.textContent)) && await p.$eval('.pk-modal', e => e.getAttribute('aria-busy') === 'true'), "Yuborilayotganda tugma matni «Yuborilmoqda…», modal aria-busy");
  await p.keyboard.press('Escape'); await sleep(100);
  ok(!!(await p.$('.pk-modal')), "So'rov ketayotganda Esc oynani yopmaydi");
  await p.mouse.click(4, 4); await sleep(100);
  ok(!!(await p.$('.pk-modal')), "So'rov ketayotganda tashqariga bosish (mousedown) oynani yopmaydi");
  ok(await p.$eval('.pk-modal [data-x]', e => e.disabled), "So'rov ketayotganda «Bekor qilish» o'chiq");
  await p.waitForSelector('.pk-modal-bg', { state: 'detached', timeout: 20000 });
  await p.unroute(/\/api\/taqdimot\/decks\/\d+\/send$/);
  await sleep(300);
  ok(await p.evaluate(() => document.activeElement && document.activeElement.id === 'tqSend'), "Yuborilgach (muharrir qayta chizilgan) fokus yangi «Yuborish» tugmasida");
  const after =await p.evaluate(() => ({ chip: document.querySelector('#tqLes .tq-chip')?.textContent || '', prim: document.querySelector('#tqSend').classList.contains('primary'), when: !!(TQ.deck.last_send || TQ.deck.sent_at || TQ.deck.lesson.lesson_sent_at) }));
  ok(/^v\d+ yuborilgan/.test(after.chip) && (!after.when || /· (\d\d:\d\d|\d\d\.\d\d\.\d{4}, \d\d:\d\d)$/.test(after.chip)), `Yuborilgach holat: «${after.chip}»`);
  ok(!after.prim, "Yuborilgach asosiy tugma ikkinchi darajali");
  await shot('10_yuborilgan');

  /* versiyalar oynasi */
  await p.click('#tqHist'); await p.waitForSelector('.pk-modal table.tq-vt');
  ok(/Studiya ko'rmagan|Studiya ko'rdi/.test(await p.textContent('.pk-modal')) && /\.pptx yuklash/.test(await p.textContent('.pk-modal')), "Versiyalar: «Studiya ko'rmagan» va «.pptx yuklash»");
  ok(await p.$eval('.pk-modal', e => e.scrollWidth <= e.clientWidth + 1) && !(await hs(p)), `${W} px: versiyalar oynasi gorizontal sig'adi`);
  if (mob) {
    ok(await p.$eval('.tq-vt tbody tr', e => getComputedStyle(e).display === 'block') && await p.$eval('.tq-vt thead', e => getComputedStyle(e).display === 'none'), "390 px: versiyalar — har versiya alohida kartochka");
    ok(await p.$eval('.tq-vt td[data-l="Fayl"] .btn', e => { const r = e.getBoundingClientRect(); return r.height >= 43.5 && r.width > 80 && r.right <= innerWidth && e.offsetParent !== null; }), "390 px: «.pptx yuklash» tugmasi ko'rinadi va ≥44 px");
    const sm = await small(p, '.tq-dlg .btn'); ok(sm.length === 0, '390 px: versiyalar oynasidagi tugmalar ≥44 px' + (sm.length ? ' — ' + JSON.stringify(sm) : ''));
  }
  await shot('11_versiyalar');
  await dlgClose(p);

  /* ---------- F. «Mening taqdimotlarim» ro'yxati ---------- */
  await p.evaluate(() => { TQ.deck = null; TQ.tab = 'mine'; tqShell(); }); await p.waitForSelector('.tq-t tbody tr');
  const L = await p.evaluate(() => { const t = document.querySelector('.tq-t'), tr = t.querySelector('tbody tr'), g = (s, pe) => getComputedStyle(tr.querySelector(s), pe); return {
    trD: getComputedStyle(tr).display, head: getComputedStyle(t.querySelector('thead')).display, usul: g('td[data-l="Usul"]').display, slayd: g('td[data-l="Slayd"]').display,
    lbl: g('td[data-l="Dars kodi"]', '::before').content, ws: g('.tq-code').whiteSpace, rowH: tr.getBoundingClientRect().height, code: !!tr.querySelector('.tq-code'), vis: tr.querySelector('.tq-code').offsetParent !== null, labels: [...tr.querySelectorAll('td')].every(td => td.dataset.l) }; });
  ok(L.labels && L.code && L.vis, "Ro'yxat: har katakda data-l yorlig'i, dars kodi ko'rinadi");
  if (mob) {
    ok(L.trD === 'block' && L.head === 'none' && L.usul === 'none' && L.slayd === 'none' && /Dars kodi/.test(L.lbl), `390 px: ro'yxat kartochka ko'rinishida («Usul» va «Slayd» yashirin, yorliq «Dars kodi»)`);
    ok(L.rowH >= 44, `390 px: kartochka balandligi ${Math.round(L.rowH)} px`);
    ok(!(await hs(p)) && await p.$eval('.tq-t', e => e.scrollWidth <= e.parentElement.clientWidth + 1), "390 px: ro'yxatda gorizontal siljish yo'q");
  } else ok(L.ws === 'nowrap', "Kompyuterda dars kodi ro'yxatda nowrap");
  await shot('12_royxat');
  ok(await p.$$eval('.tq-t tbody tr .tq-chip.ok', e => e.some(x => /^v\d+ yuborilgan/.test(x.textContent))), "Ro'yxatda yuborilgan versiya belgisi ko'rinadi");

  /* ---------- G. yuborilgan taqdimotni o'chirish tasdig'i (faqat yorug' mavzuda — kunlik limitni tejaymiz) ---------- */
  if (!dark) {
    const dDel = await mkDeck(p, E.LK1, true);
    await openDeck(p, dDel);
    await p.click('#tqDel'); await sleep(150);
    ok(await p.$eval('#tqDelNote', e => e.textContent.trim().length > 5), "O'chirish: birinchi bosishda izoh chiqadi");
    await p.click('#tqDel'); await p.waitForSelector('.tq-tabs', { timeout: 15000 });
    await openDeck(p, dSent);
    const sentN = await p.evaluate(() => (TQ.deck.sends || []).length);
    await p.click('#tqDel'); await sleep(150);
    const dn = await p.textContent('#tqDelNote');
    ok(!sentN || /Yuborilgan versiyalar \(v1–v\d+\) studiya va bo'limda qoladi/.test(dn), `O'chirish tasdig'i (yuborilgan taqdimot): «${dn.trim().slice(0, 90)}»`);
    ok(await p.$eval('#tqDel', e => e.classList.contains('armed')), "O'chirish: ikki bosqichli tasdiq");
    await p.click('#tqBack'); await sleep(200);
  }
  ok(errs.length === 0, `${W}×${H} ${theme}: sahifa/konsol xatosi yo'q` + (errs.length ? ' — ' + errs[0] : ''));
  await ctx.close();
}

/* kichik ekranlar: yuborish dialogi tugmalari klaviatura chiqqanda ham ko'rinadi, 320 px da tugma sig'adi */
async function small_screens(b, id) {
  for (const [W, H, nm] of [[390, 380, 'klaviatura 390×380'], [320, 568, '320×568']]) {
    console.log(`\n=== ${nm} ===`);
    const ctx = await b.newContext({ viewport: { width: W, height: H } }); await login(ctx);
    const p = await ctx.newPage(); const errs = []; p.on('pageerror', e => errs.push(String(e)));
    await p.goto(B + '/'); await sleep(1200);
    await p.evaluate(() => go('taqdimot')); await p.waitForSelector('.lp');
    await openDeck(p, id);
    const sb = await p.$eval('#tqSend', e => { const r = e.getBoundingClientRect(); return { ws: getComputedStyle(e).whiteSpace, right: r.right, left: r.left, h: r.height }; });
    ok(sb.ws === 'normal' && sb.right <= W + 0.5 && sb.left >= -0.5, `${nm}: «Studiyaga va masofaviy bo'limga yuborish» tugmasi sig'adi (white-space:normal, ${Math.round(sb.left)}–${Math.round(sb.right)} px)`);
    ok(!(await hs(p)), `${nm}: muharrirda gorizontal siljish yo'q`);
    await p.screenshot({ path: `${OUT}/${W}x${H}_muharrir.png` });
    await p.evaluate(() => document.querySelector('#tqSend').scrollIntoView()); await p.click('#tqSend'); await p.waitForSelector('.pk-modal [data-ok]'); await sleep(300);
    const v = await p.evaluate(() => { const o = document.querySelector('.pk-modal [data-ok]').getBoundingClientRect(), x = document.querySelector('.pk-modal [data-x]').getBoundingClientRect(); return { okB: o.bottom, okT: o.top, xB: x.bottom, vh: innerHeight, tall: document.querySelector('.pk-modal').getBoundingClientRect().height > innerHeight }; });
    ok(v.okB <= v.vh + 0.5 && v.okT >= 0 && v.xB <= v.vh + 0.5, `${nm}: «Yuborish» va «Bekor qilish» skrollsiz ko'rinadi (pastki chegara ${Math.round(v.okB)} ≤ ${v.vh}px${v.tall ? ', dialog ekrandan baland — sticky' : ''})`);
    ok(!(await hs(p)) && await p.$eval('.pk-modal', e => e.scrollWidth <= e.clientWidth + 1), `${nm}: dialog gorizontal sig'adi`);
    await p.screenshot({ path: `${OUT}/${W}x${H}_yuborish.png` });
    ok(errs.length === 0, `${nm}: sahifa xatosi yo'q` + (errs.length ? ' — ' + errs[0] : ''));
    await ctx.close();
  }
}

(async () => {
  const b = await chromium.launch({ executablePath: E.CHROME, headless: true });
  try {
    const sctx = await b.newContext({ viewport: { width: 1440, height: 900 } }); await login(sctx);
    const sp = await sctx.newPage(); await sp.goto(B + '/'); await sleep(800);
    const DK = { A: await mkDeck(sp, E.LK2, false), B: await mkDeck(sp, E.LK1, true) };
    for (const [W, H, th] of [[1440, 900, 'light'], [1440, 900, 'dark'], [390, 844, 'light'], [390, 844, 'dark']]) await suite(b, W, H, th, DK);
    await small_screens(b, DK.B);
    await delDeck(sp, DK.A); await delDeck(sp, DK.B); await sctx.close();
  } catch (e) { console.log('✗ Brauzer xatosi: ' + (e && e.stack || e)); bad++; }
  await b.close();
  process.exit(bad ? 1 : 0);
})();
