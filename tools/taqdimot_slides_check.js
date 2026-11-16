#!/usr/bin/env node
/* Studiya: taqdimotni o'qish rejimi — slayd RASMLARI (PNG) ko'rinishi, brauzer tekshiruvi. tests/test_taqdimot_slides.py chaqiradi (PW va CHROME berilsa).
   Muhit: B (server), PW_ (parol), O_UID (operator), CID, LK (dars), VER (versiya), OLD_VER (PNG'siz eski versiya, ixtiyoriy), OUT (skrinshotlar).
   Tekshiradi: rasm yuklanadi (1600 px), ←/→/Home/End, hisoblagich, to'liq ekran tugmasi, Esc, 390 px da gorizontal siljish yo'q va tugmalar ≥44 px,
   eski versiya (rasm yo'q) — avvalgi matnli ko'rinish. */
const { chromium } = require(process.env.PW || 'playwright-core');
const fs = require('fs');
const E = process.env, B = E.B, OUT = E.OUT || '/tmp/taqdimot_slides';
fs.mkdirSync(OUT, { recursive: true });
let bad = 0;
const ok = (c, m) => { console.log((c ? '✓ ' : '✗ ') + m); if (!c) bad++; };
const sleep = ms => new Promise(r => setTimeout(r, ms));

async function open(b, W, H, scheme) {
  const ctx = await b.newContext({ viewport: { width: W, height: H }, colorScheme: scheme });
  await ctx.addInitScript(t => { try { localStorage.setItem('jarvis-theme', t); } catch (e) {} }, scheme);
  const r = await ctx.request.post(B + '/api/login', { data: { user_id: +E.O_UID, password: E.PW_ } });
  if (!r.ok()) throw new Error('login ' + r.status());
  const p = await ctx.newPage(); p.errs = [];
  p.on('pageerror', e => p.errs.push(String(e)));
  p.on('console', m => { if (m.type() === 'error' && !/status of (404|409|403)/.test(m.text())) p.errs.push('console: ' + m.text()); });
  await p.goto(B + '/'); await sleep(1200);
  return { ctx, p };
}
const hs = p => p.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1);
const imgOk = p => p.evaluate(async () => { const i = document.querySelector('.st-rd-img'); if (!i) return null; await i.decode().catch(() => {}); return { w: i.naturalWidth, h: i.naturalHeight, alt: i.alt, vis: i.getBoundingClientRect().width }; });
async function reader(p, ver) {
  await p.evaluate(([c, l]) => stPres(c, l), [E.CID, E.LK]);
  await p.waitForSelector('.st-modal');
  await p.click(`.st-modal [data-read="${ver}"]`); await p.waitForSelector('.st-reader'); await sleep(400);
}

(async () => {
  const b = await chromium.launch({ executablePath: E.CHROME, headless: true });
  try {
    for (const [W, H, scheme] of [[1440, 900, 'light'], [390, 844, 'dark']]) {
      const T = `${W}_${scheme}`, mob = W < 500;
      const { ctx, p } = await open(b, W, H, scheme);
      await reader(p, E.VER);
      const n0 = await p.textContent('#stRdN'); const total = +n0.split('/')[1];
      ok(/^1 \/ \d+$/.test(n0) && total >= 4, `${T}: o'qish rejimi ochildi: ${n0}`);
      const im = await imgOk(p);
      ok(im && im.w === 1600 && im.h === 900 && im.alt.includes('1-slayd'), `${T}: 1-slayd RASMI yuklandi (${im && im.w}×${im && im.h}), alt: «${im && im.alt}»`);
      ok(await p.evaluate(() => !document.querySelector('.st-rd-h')), `${T}: rasm rejimida matnli sarlavha yo'q (rasm ko'rsatilgan)`);
      ok(im && im.vis >= (mob ? 340 : 700), `${T}: rasm ekranda katta (${Math.round(im.vis)} px kenglikda)`);
      ok(await p.evaluate(() => { const i = document.querySelector('.st-rd-img').getBoundingClientRect(), n = document.querySelector('.st-rd-nav').getBoundingClientRect(); return i.top >= 0 && i.bottom <= n.top + 1; }), `${T}: butun slayd rasmi ekranga sig'adi (skrollsiz, pastki panelga tegmaydi)`);
      ok(!(await hs(p)), `${T}: gorizontal siljish yo'q`);
      await p.screenshot({ path: `${OUT}/oqish_${T}_1.png` });
      await p.keyboard.press('ArrowRight'); await sleep(300);
      ok((await p.textContent('#stRdN')).startsWith('2 /') && (await imgOk(p)).w === 1600, `${T}: → 2-slayd rasmi`);
      ok(await p.evaluate(() => document.querySelectorAll('.st-rd-sr li').length >= 1), `${T}: ekran o'quvchi uchun yashirin band ro'yxati bor (REJA)`);
      await p.screenshot({ path: `${OUT}/oqish_${T}_2.png` });
      await p.keyboard.press('ArrowLeft'); ok((await p.textContent('#stRdN')).startsWith('1 /'), `${T}: ← oldingi`);
      await p.keyboard.press('End'); await sleep(300);
      ok((await p.textContent('#stRdN')) === `${total} / ${total}` && await p.evaluate(() => document.querySelector('[data-next]').disabled), `${T}: End — oxirgi slayd, «Keyingi» o'chiq`);
      await p.screenshot({ path: `${OUT}/oqish_${T}_oxirgi.png` });
      await p.keyboard.press('Home'); await sleep(200);
      ok((await p.textContent('#stRdN')).startsWith('1 /'), `${T}: Home — birinchi slayd`);
      const fs0 = await p.evaluate(() => { const f = document.querySelector('[data-fs]'); if (!f) return null; const r = f.getBoundingClientRect(); return { w: r.width, h: r.height, label: f.getAttribute('aria-label') }; });
      ok(fs0 && fs0.w >= 43.5 && fs0.h >= 43.5 && /To'liq ekran/.test(fs0.label), `${T}: «To'liq ekran» tugmasi (≥44 px, aria-label)`);
      if (mob) {
        const m = await p.evaluate(() => { const r = [...document.querySelectorAll('.st-rd-nav .btn, .st-rd-x')].map(e => e.getBoundingClientRect()); return { w: Math.min(...r.map(x => x.width)), h: Math.min(...r.map(x => x.height)) }; });
        ok(m.w >= 43.5 && m.h >= 43.5, `${T}: o'qish rejimi tugmalari ≥44 px (${m.w}×${m.h})`);
        const tx = await p.evaluate(() => { const r = document.querySelector('.st-rd-nav').getBoundingClientRect(); return r.right <= innerWidth + 1; });
        ok(tx, `${T}: pastki panel ekranga sig'adi`);
      } else {
        await p.keyboard.press('f'); await sleep(500);
        const isFs = await p.evaluate(() => document.fullscreenElement && document.fullscreenElement.classList.contains('st-reader'));
        if (isFs) {
          ok(await p.evaluate(() => document.querySelector('[data-fs]').getAttribute('aria-pressed') === 'true'), `${T}: F — to'liq ekran yoqildi (aria-pressed)`);
          await p.keyboard.press('f'); await sleep(400);
          ok(await p.evaluate(() => !document.fullscreenElement), `${T}: F — to'liq ekrandan chiqdi`);
        } else console.log(`– ${T}: headless Chrome to'liq ekranga ruxsat bermadi — o'tkazib yuborildi`);
      }
      await p.keyboard.press('Escape'); await sleep(300);
      ok(await p.evaluate(() => !document.querySelector('.st-reader') && !!document.querySelector('.st-modal')), `${T}: Esc — o'qish rejimi yopildi, oyna qoldi`);
      await p.screenshot({ path: `${OUT}/oyna_${T}.png` });
      ok(p.errs.length === 0, `${T}: konsolda xato yo'q` + (p.errs.length ? ' — ' + p.errs.join(' | ').slice(0, 300) : ''));
      await ctx.close();
    }
    if (E.OLD_VER) {      /* eski versiya: PNG yo'q → matnli zaxira */
      const { ctx, p } = await open(b, 1440, 900, 'light');
      await reader(p, E.OLD_VER);
      ok(await p.evaluate(() => !document.querySelector('.st-rd-img') && !!document.querySelector('.st-rd-h') && document.querySelectorAll('.st-rd-ul li').length >= 0), `Eski versiya (rasm yo'q): avvalgi matnli ko'rinish (.st-rd-h)`);
      await p.keyboard.press('ArrowRight'); ok((await p.textContent('#stRdN')).startsWith('2 /'), 'Eski versiya: ← / → matnli ko\'rinishda ishlaydi');
      ok(await p.evaluate(() => !document.querySelector('[data-fs]')), `Eski versiya: «To'liq ekran» tugmasi yo'q (faqat rasm rejimida)`);
      await p.screenshot({ path: `${OUT}/oqish_eski_versiya_matn.png` });
      ok(p.errs.length === 0, `Eski versiya: konsolda xato yo'q` + (p.errs.length ? ' — ' + p.errs.join(' | ').slice(0, 300) : ''));
      await ctx.close();
    }
  } finally { await b.close(); }
  console.log(bad ? `\nXATO: ${bad}` : '\nHammasi o\'tdi');
  process.exit(bad ? 1 : 0);
})().catch(e => { console.error(e); process.exit(2); });
