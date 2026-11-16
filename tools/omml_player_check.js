#!/usr/bin/env node
/* Formulalar (MathML Core) — paket pleyeri va kurs pleyerida brauzer sinovi (tests/test_omml.py chaqiradi).
 *
 *   PW=/path/node_modules/playwright-core CHROME=/path/to/chrome OUT=/tmp/omml node tools/omml_player_check.js <html.json>
 *
 * <html.json>: {"html": structure_text natijasi}. Pleyer nusxasi vaqtinchalik papkaga ko'chiriladi, content.js — bitta «text» bloki bilan;
 * file:// orqali ochiladi. Tekshiradi: <math> MathML nomlar fazosida, blok formula .mth qutisida, kasr/ildiz/matritsa chiziladi (balandlik > 0),
 * ikkala pleyer sanitizeri xavfli MathML'ni (on*, href, style, maction, annotation-xml ichidagi skript, xlink) tozalaydi; 1280px va 390px skrinshot.
 */
'use strict';
const fs = require('fs'), path = require('path'), os = require('os');
const { chromium } = require(process.env.PW || 'playwright-core');
const ROOT = path.resolve(__dirname, '..');
const OUT = process.env.OUT || path.join(os.tmpdir(), 'isft_omml');
const SRC = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
fs.mkdirSync(OUT, { recursive: true });
let fails = 0;
const ok = (c, m) => { console.log((c ? '  ✓ ' : '  ✗ ') + m); if (!c) fails++; };

function copyDir(a, b) {
  fs.mkdirSync(b, { recursive: true });
  for (const f of fs.readdirSync(a)) { const s = path.join(a, f), d = path.join(b, f); fs.statSync(s).isDirectory() ? copyDir(s, d) : fs.copyFileSync(s, d); }
}
const EVIL = '<math><mi onclick="window.__x=1" href="javascript:alert(1)" style="color:red" xlink:href="javascript:1">x</mi>' +
  '<maction actiontype="toggle"><mi>a</mi><mi>b</mi></maction><semantics><mi>y</mi><annotation-xml encoding="text/html"><img src=x onerror="window.__x=2"></annotation-xml></semantics>' +
  '<mtext><img src=x onerror="window.__x=3"><b>t</b></mtext><mi mathvariant="url(javascript:1)">z</mi></math><mi>stray</mi>';

(async () => {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'omml-'));
  const pk = path.join(tmp, 'paket'), ku = path.join(tmp, 'kurs');
  copyDir(path.join(ROOT, 'app', 'paket_player'), pk);
  copyDir(path.join(ROOT, 'app', 'kurs_player'), ku);
  fs.copyFileSync(path.join(ROOT, 'app', 'paket_player', 'lms.js'), path.join(ku, 'lms.js'));
  fs.copyFileSync(path.join(ROOT, 'app', 'paket_player', 'a11y.js'), path.join(ku, 'a11y.js'));
  const content = { v: 1, id: 'omml-test', title: 'Formulalar', lang: 'uz', lesson: { code: 'L7', kind: 'maruza', no: 7, title: 'Ishlab chiqarish funksiyasi' },
    blocks: [{ id: 'b1', type: 'text', title: "Ma'ruza matni", html: SRC.html }] };
  fs.writeFileSync(path.join(pk, 'content.js'), 'window.PAKET = ' + JSON.stringify(content) + ';');
  fs.writeFileSync(path.join(ku, 'content.js'), 'window.KURS = ' + JSON.stringify({ kind: 'kurs', v: 1, id: 'k', title: 'Formulalar', lang: 'uz',
    lessons: [{ id: 'l1', type: 'blocks', title: 'Formulalar', blocks: [{ id: 'b1', type: 'paragraph', html: SRC.html }] }] }) + ';');
  const browser = await chromium.launch({ executablePath: process.env.CHROME, headless: true });
  try {
    for (const [w, h, tag] of [[1280, 900, 'desktop'], [390, 844, 'mobil']]) {
      const page = await browser.newPage({ viewport: { width: w, height: h } });
      const errs = []; page.on('pageerror', e => errs.push(String(e)));
      await page.goto('file://' + path.join(pk, 'index.html'));
      await page.waitForFunction(() => window.ISFTPaket && window.ISFTPaket.ready, null, { timeout: 15000 }).catch(() => {});
      // muqova/boshlash tugmasi bo'lsa — matn blokiga o'tish
      for (let i = 0; i < 4 && !(await page.$('math')); i++) {
        const b = await page.$('button.start, .cover button, button.r-start, button.r-go, .r-next, button[data-act="next"]');
        if (!b) break; await b.click().catch(() => {}); await page.waitForTimeout(300);
      }
      const r = await page.evaluate(() => {
        const ms = Array.from(document.querySelectorAll('math'));
        const NS = 'http://www.w3.org/1998/Math/MathML';
        const box = s => { const e = document.querySelector(s); return e ? e.getBoundingClientRect().height : 0; };
        return { n: ms.length, ns: ms.every(m => m.namespaceURI === NS), block: document.querySelectorAll('.mth > math[display="block"]').length,
          frac: box('mfrac'), root: box('mroot'), table: box('mtable'), alt: ms.filter(m => m.getAttribute('alttext')).length,
          overflow: document.documentElement.scrollWidth - window.innerWidth };
      });
      ok(r.n >= 10 && r.ns, `${tag}: ${r.n} ta <math> MathML nomlar fazosida`);
      ok(r.block >= 6, `${tag}: blok formulalar .mth qutisida (${r.block})`);
      ok(r.frac > 10 && r.root > 5 && r.table > 20, `${tag}: kasr / ildiz / matritsa chizildi (balandlik ${r.frac.toFixed(0)} / ${r.root.toFixed(0)} / ${r.table.toFixed(0)} px)`);
      ok(r.alt === r.n, `${tag}: har bir formulada alttext (${r.alt}/${r.n})`);
      ok(r.overflow <= 1, `${tag}: sahifa gorizontal aylanmaydi (${r.overflow}px)`);
      ok(!errs.length, `${tag}: JS xatosi yo'q ${errs.join('; ')}`);
      const first = await page.$('.mth');
      if (first) await first.scrollIntoViewIfNeeded();
      await page.screenshot({ path: path.join(OUT, `paket_${tag}.png`), fullPage: true });
      if (tag === 'desktop') {
        const s = await page.evaluate(evil => { window.__x = 0; return window.ISFTPaket.debug.sanitize(evil); }, EVIL);
        ok(/<math/.test(s) && !/onclick|href|style=|javascript|maction|annotation|onerror|<img|url\(|<mi>stray/.test(s) && /<mi>a<\/mi><mi>b<\/mi>/.test(s),
           'paket sanitizer: on*/href/style/xlink, maction (mazmuni qoladi), annotation-xml, mtext ichidagi img, url() — tozalandi: ' + s.slice(0, 200));
        await page.waitForTimeout(200);
        ok(await page.evaluate(() => !window.__x), 'paket sanitizer: hech qanday hodisa ishlamadi');
      }
      await page.close();
    }
    const page = await browser.newPage();
    const kerrs = []; page.on('pageerror', e => kerrs.push(String(e)));
    await page.goto('file://' + path.join(ku, 'index.html'));
    await page.waitForFunction(() => window.ISFTKurs && window.ISFTKurs.debug, null, { timeout: 15000 }).catch(() => {});
    ok(await page.evaluate(() => !!(window.ISFTKurs && window.ISFTKurs.debug)), 'kurs pleyeri yuklandi ' + kerrs.join('; '));
    const k = await page.evaluate(([evil, good]) => { window.__x = 0; return [window.ISFTKurs.debug.sanitize(evil), window.ISFTKurs.debug.sanitize(good)]; }, [EVIL, SRC.html]);
    ok(/<math/.test(k[0]) && !/onclick|href|style=|javascript|maction|annotation|onerror|<img|url\(|<mi>stray/.test(k[0]), 'kurs sanitizer: xavfli MathML tozalandi');
    await page.waitForTimeout(300);
    for (let i = 0; i < 3 && !(await page.$('math')); i++) {   // muqova → birinchi dars
      const b = await page.$('button.start, .cover button, .cv button, button[data-go], .btn-start'); if (!b) break; await b.click().catch(() => {}); await page.waitForTimeout(400);
    }
    if (await page.$('math')) { await (await page.$('.mth')).scrollIntoViewIfNeeded().catch(() => {}); await page.screenshot({ path: path.join(OUT, 'kurs_desktop.png') }); }
    ok((k[1].match(/<math/g) || []).length >= 10 && /<mfrac>/.test(k[1]) && /<mtable>/.test(k[1]) && /class="mth"/.test(k[1]), 'kurs sanitizer: formulalar (mfrac, mtable, blok qutisi) saqlanadi');
    await page.close();
  } finally {
    await browser.close();
    fs.rmSync(tmp, { recursive: true, force: true });
  }
  console.log(fails ? `\n${fails} ta xato` : '\nHammasi o\'tdi'); process.exit(fails ? 1 : 0);
})().catch(e => { console.error(e); process.exit(1); });
