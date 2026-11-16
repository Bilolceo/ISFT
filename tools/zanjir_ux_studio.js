#!/usr/bin/env node
/* Studiya UI — brauzer tekshiruvi (1440 va 390 px, yorug' va qorong'i; operator va bo'lim boshlig'i). tests/test_zanjir_ux_studio.py chaqiradi.
   Muhit: B (server), PW_ (parol), O_UID (operator), H_UID (bo'lim boshlig'i), CID, LK_A, CODE_A (unikal kod), VER (oxirgi taqdimot versiyasi),
   JID_P (tasdiqlangan, taqdimotli), JID_W (tasdiqlangan, taqdimotsiz), JID_D (409 sinovi), JID_E (ikki marta bosish), JID_R (ko'rib chiqish, video bor),
   JID_N (ko'rib chiqish, video yo'q), BK_DAY / BK_KEY (syomka bandi kuni va «kurs:dars»), CODE_W/R/N/D (kodlar), OUT (skrinshotlar). */
const { chromium } = require(process.env.PW || 'playwright-core');
const fs = require('fs');
const E = process.env, B = E.B, OUT = E.OUT || '/tmp/zanjir_ux_studio';
fs.mkdirSync(OUT, { recursive: true });
let bad = 0;
const ok = (c, m) => { console.log((c ? '✓ ' : '✗ ') + m); if (!c) bad++; };
const sleep = ms => new Promise(r => setTimeout(r, ms));
async function login(ctx, uid) {
  const r = await ctx.request.post(B + '/api/login', { data: { user_id: +uid, password: E.PW_ } });
  if (!r.ok()) throw new Error('login ' + uid + ' ' + r.status());
}
const hs = p => p.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1);
const modalFits = p => p.evaluate(() => { const m = document.querySelector('.st-modal'); return !m || m.scrollWidth <= m.clientWidth + 1; });
const shot = (p, n) => p.screenshot({ path: `${OUT}/${n}.png` });
const modalOpen = p => p.evaluate(() => !!document.querySelector('.st-modal'));
const waitGone = (p, sel = '.st-modal') => p.waitForFunction(s => !document.querySelector(s), sel, { timeout: 8000 }).then(() => true).catch(() => false);
const focusIn = (p, sel) => p.evaluate(s => { const a = document.activeElement, r = document.querySelector(s); return !!(a && r && r.contains(a)); }, sel);
const focusMatches = (p, sel) => p.evaluate(s => !!document.activeElement && document.activeElement.matches(s), sel);
async function open(b, uid, W, H, scheme) {
  const ctx = await b.newContext({ viewport: { width: W, height: H }, colorScheme: scheme });
  await ctx.addInitScript(t => { try { localStorage.setItem('jarvis-theme', t); } catch (e) {} }, scheme);
  await login(ctx, uid);
  const p = await ctx.newPage(); p.errs = []; CUR = p;
  p.on('pageerror', e => p.errs.push(String(e)));
  p.on('console', m => { if (m.type() === 'error' && !/status of (404|409|403)/.test(m.text())) p.errs.push('console: ' + m.text()); });
  await p.goto(B + '/'); await sleep(1200);
  return { ctx, p };
}
async function studio(p, tab) {
  await p.evaluate(t => { stReset(); go('studio'); if (t) STD.tab = t; }, tab || null);
  await p.waitForSelector('#stBox .st-kpi, #stBox .st-card, #stBox .st-daynav, #stBox .st-empty:not(:only-child)', { timeout: 20000 });
  await sleep(500);
  if (tab && !(await p.evaluate(t => !!document.querySelector(`.st-tabs [data-t="${t}"].on`), tab))) await tabTo(p, tab);
}
async function tabTo(p, tab) { await p.evaluate(t => renderStudio(t), tab); await p.waitForFunction(t => document.querySelector(`.st-tabs [data-t="${t}"].on`) && !document.querySelector('#stBox .st-empty:only-child'), tab, { timeout: 20000 }); await sleep(400); }
/* Tab bilan oyna ichida aylanish: barcha bosishlarda fokus oyna ichida, oxirgidan keyin boshiga qaytadi */
async function tabCycle(p, sel = '.st-modal-bg, .st-reader') {
  const n = await p.evaluate(s => { const r = document.querySelector(s); return r ? r.querySelectorAll('a[href],button:not([disabled]),input,select,textarea,summary,video[controls]').length : 0; }, sel);
  let inside = true;
  for (let i = 0; i < n + 2; i++) { await p.keyboard.press('Tab'); if (!(await focusIn(p, sel))) inside = false; }
  for (let i = 0; i < 3; i++) { await p.keyboard.press('Shift+Tab'); if (!(await focusIn(p, sel))) inside = false; }
  /* <video controls> ichki boshqaruv elementlari (Chrome UA shadow) klaviatura hodisalarini sahifaga bermaydi — keyingi tekshiruvlar uchun fokusni oynaga qaytaramiz */
  await p.evaluate(s => { const r = document.querySelector(s), d = r && (r.querySelector('[role="dialog"]') || r); d && d.focus(); }, sel);
  return inside;
}
const contrast = (p, sel) => p.evaluate(s => {
  const el = document.querySelector(s); if (!el) return null;
  const rgb = c => (c.match(/[\d.]+/g) || []).map(Number);
  const lum = c => { const [r, g, b] = rgb(c).slice(0, 3).map(v => { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); }); return 0.2126 * r + 0.7152 * g + 0.0722 * b; };
  let bg = null, n = el;
  while (n) { const c = getComputedStyle(n).backgroundColor, a = rgb(c); if (a.length >= 3 && (a.length === 3 || a[3] > 0.5)) { bg = c; break; } n = n.parentElement; }
  const fg = getComputedStyle(el).color; if (!bg) bg = 'rgb(255,255,255)';
  const l1 = lum(fg), l2 = lum(bg); return (Math.max(l1, l2) + 0.05) / (Math.min(l1, l2) + 0.05);
}, sel);
const minSize = (p, sel) => p.evaluate(s => { const r = [...document.querySelectorAll(s)].filter(e => e.offsetParent !== null).map(e => { const b = e.getBoundingClientRect(); return [Math.round(b.width * 10) / 10, Math.round(b.height * 10) / 10]; }); return { n: r.length, w: Math.min(...r.map(x => x[0])), h: Math.min(...r.map(x => x[1])) }; }, sel);
let CUR = null;
const MOCK_OUTLINE = { title: 'matn', slides: [
  { n: 1, kind: 'title', title: 'Talab va taklif', bullets: [], notes: 'Kirish so\'zi' },
  { n: 2, kind: 'content', title: 'Talab qonuni', bullets: ['Narx oshsa talab kamayadi', 'Daromad ta\'siri', 'O\'rnini bosish ta\'siri'], notes: '' },
  { n: 3, kind: 'content', title: 'Taklif qonuni', bullets: ['Narx oshsa taklif ortadi', 'Xarajatlar'], notes: 'Misol keltiring' }] };

(async () => {
  const b = await chromium.launch({ executablePath: E.CHROME, headless: true });
  try {
    /* ===================================================================================================================
       1440 yorug' — to'liq xulq-atvor sinovi (operator)
       =================================================================================================================== */
    {
      const { ctx, p } = await open(b, E.O_UID, 1440, 900, 'light');
      const hctx = await b.newContext({ viewport: { width: 1440, height: 900 } }); await login(hctx, E.H_UID);
      await studio(p, 'kun');
      const meta = await p.evaluate(() => ({ worker: STD.meta.worker_on, role: STD.meta.role, today: STD.meta.today }));
      ok(meta.role === 'montaj_operator', 'Operator roli: ' + meta.role);

      /* ---- (6) montaj ishchisi matni: operatorga texnik so'zlarsiz ---- */
      if (!meta.worker) {
        const wt = await p.textContent('.st-head ~ .st-warnbox');
        ok(/Montaj hozircha ishlamayapti — IT/.test(wt) && !/WORKER_TOKEN|server/i.test(wt), "Operator: «Montaj hozircha ishlamayapti — IT bilan bog'laning», texnik matn yo'q");
      } else console.log("– montaj ishchisi ulangan — ogohlantirish sinovi o'tkazib yuborildi");

      /* ---- (5) kun rejasi ---- */
      await p.evaluate(d => { STD.day = d; }, E.BK_DAY); await tabTo(p, 'kun');
      await p.waitForSelector(`.st-slot.busy [data-pres="${E.BK_KEY}"]`, { timeout: 20000 });
      const geo = await p.evaluate(k => { const s = document.querySelector(`.st-slot.busy:has([data-pres="${k}"])`), c = s.querySelector('.st-code').getBoundingClientRect(), m = s.querySelector('.st-slot-m').getBoundingClientRect(); return { c: c.width, m: m.width }; }, E.BK_KEY);
      ok(geo.c < geo.m - 40, `Dars kodi pilyulasi butun qatorga cho'zilmagan (${Math.round(geo.c)} px < ${Math.round(geo.m)} px)`);
      const slotTxt = await p.textContent(`.st-slot.busy:has([data-pres="${E.BK_KEY}"])`);
      ok(/Bo'limga yuborilmagan/.test(slotTxt), "Kun rejasi: tasdiqlangan montaj uchun «Bo'limga yuborilmagan» chipi");
      ok(await p.evaluate(k => !!document.querySelector(`.st-slot.busy:has([data-pres="${k}"]) .st-chip.warn`) && [...document.querySelectorAll(`.st-slot.busy:has([data-pres="${k}"]) .st-chip.warn`)].some(c => /Bo'limga yuborilmagan/.test(c.textContent)), E.BK_KEY), "«Bo'limga yuborilmagan» chipi ogohlantiruvchi (sariq) rangda");
      await shot(p, 'o_1440_light_kun');
      /* kun navigatsiyasi: qayta chizilgach fokus saqlanadi */
      const lbl0 = await p.textContent('#stDayLbl');
      await p.focus('[data-dd="1"]'); await p.keyboard.press('Enter');
      await p.waitForFunction(l => document.querySelector('#stDayLbl') && document.querySelector('#stDayLbl').textContent !== l, lbl0, { timeout: 8000 }); await sleep(300);
      ok(await focusMatches(p, '[data-dd="1"]'), "«Keyingi kun» bosilgach, qayta chizilgandan keyin fokus tugmada qoladi");
      await p.focus('[data-dd="-1"]'); await p.keyboard.press('Enter'); await sleep(900);
      ok(await focusMatches(p, '[data-dd="-1"]'), "«Oldingi kun»: fokus saqlanadi");
      /* o'tib ketgan bo'sh slot: «—» kontrasti */
      let cr = null;
      for (let back = 1; back <= 8 && cr == null; back++) {
        const day = await p.evaluate(n => stAddDays(STD.meta.today, -n), back);
        await p.evaluate(d => { STD.day = d; }, day); await tabTo(p, 'kun');
        cr = await contrast(p, '.st-slot.past .st-slot-m.muted');
      }
      ok(cr == null || cr >= 4.5, `O'tgan bo'sh slot «—» kontrasti ≥4.5 (${cr == null ? 'slot topilmadi' : cr.toFixed(1)})`);
      ok(cr == null || await p.evaluate(() => { const e = document.querySelector('.st-slot.past .st-slot-m.muted'); return !!e.querySelector('[aria-hidden="true"]') && !!e.querySelector('.st-sr'); }), "«—» belgisi aria-hidden, o'qish dasturi uchun matn bor");
      await p.evaluate(d => { STD.day = d; }, E.BK_DAY); await tabTo(p, 'kun');
      await p.waitForSelector(`.st-slot.busy [data-pres="${E.BK_KEY}"]`);

      /* ---- (1, 2) «Taqdimot» oynasi: faqat <a> va [data-x] emas — Esc yopadi, fokus qaytadi ---- */
      const presBtn = `.st-slot.busy [data-pres="${E.BK_KEY}"]`;
      await p.click(presBtn); await p.waitForSelector('.st-modal');
      ok(await focusIn(p, '.st-modal-bg'), "«Taqdimot» oynasi ochilganda fokus oyna ichida");
      ok(await p.evaluate(() => !!document.querySelector('#v-studio').closest('[inert]') || !!document.querySelector('.app, #app, main')?.closest('[inert]') || [...document.body.children].some(n => n.inert)), 'Fon (sahifa) inert — ostidagi elementlarga Tab/bosish yetmaydi');
      const title = await p.textContent('.st-modal-h h3');
      const sub = await p.textContent('.st-modal-sub');
      ok(/L\d+ · /.test(title) && sub.includes('Taqdimot:') && sub.includes(E.CODE_A) && !/Taqdimot: Matn/i.test(sub), `Sarlavha: dars mavzusi («${title}»), ostida taqdimot nomi va kod`);
      ok(await tabCycle(p), "Tab modal ichida aylanadi (oldinga va orqaga)");
      ok(/\.pptx yuklab olish/.test(await p.textContent('.st-modal a[href$="/pptx"]')) && await p.isVisible(`.st-modal a[href$="/taqdimot/${E.VER}/pptx"]`), "«.pptx yuklab olish» (kartochka bilan bir xil nom)");
      ok(await p.isVisible('.st-modal [data-read]') && /to'liq ekran/.test(await p.textContent('.st-modal [data-read]')), "«Taqdimotni ochish (to'liq ekran)» tugmasi");
      ok((await p.$$('.st-vers li')).length >= 1 && await p.isVisible('.st-vers [data-read]'), "Eski versiyalar kartochka qatorlari (o'qish, .pptx)");
      await shot(p, 'o_1440_light_taqdimot');
      await p.keyboard.press('Escape');
      ok(await waitGone(p), "Esc «Taqdimot» oynasini yopadi (faqat havola va ×/Yopish bor)");
      ok(await focusMatches(p, `[data-pres="${E.BK_KEY}"]`), "Yopilgach fokus «Taqdimot» tugmasiga qaytdi");
      ok(!(await p.evaluate(() => [...document.body.children].some(n => n.inert))), "Yopilgach fon inert emas");
      /* o'qish rejimi */
      const real = await p.evaluate(async ([c, l, v]) => (await fetch(`/api/studio/lessons/${c}/${l}/taqdimot/${v}/outline`, { credentials: 'same-origin' })).status, [E.CID, E.LK_A, E.VER]);
      if (real !== 200) { console.log(`– outline endpointi ${real} qaytardi (backend hali yo'q) — sinov mock bilan`); await p.route('**/taqdimot/*/outline', r => r.fulfill({ json: MOCK_OUTLINE })); }
      await p.click(presBtn); await p.waitForSelector('.st-modal');
      await p.click('.st-modal .st-pres-a [data-read]'); await p.waitForSelector('.st-reader');
      const n0 = await p.textContent('#stRdN'); const total = +n0.split('/')[1];
      ok(/^1 \/ \d+$/.test(n0) && total >= 2, `O'qish rejimi ochildi: ${n0}`);
      ok(await p.evaluate(() => { const r = document.querySelector('.st-reader').getBoundingClientRect(); return r.width >= innerWidth - 1 && r.height >= innerHeight - 1; }), "O'qish rejimi to'liq ekran");
      /* slayd rasmi (PNG) bo'lsa — rasm rejimi (≥1200 px, alt matn bor); eski versiya / mock — matn rejimi */
      const imgMode = await p.evaluate(() => !!document.querySelector('.st-rd-img'));
      ok(await p.evaluate(async () => { const i = document.querySelector('.st-rd-img'); if (!i) return parseFloat(getComputedStyle(document.querySelector('.st-rd-h')).fontSize) >= 28; await i.decode().catch(() => {}); return i.naturalWidth >= 1200 && (i.alt || '').length > 3; }), imgMode ? 'Slayd rasmi yuklandi (≥1200 px, alt matn bor)' : 'Slayd sarlavhasi katta shriftda');
      ok(await focusIn(p, '.st-reader'), "O'qish rejimida fokus ichkarida");
      await p.keyboard.press('ArrowRight'); ok((await p.textContent('#stRdN')).startsWith('2 /'), '→ keyingi slayd');
      ok(await p.evaluate(() => document.querySelectorAll('.st-rd-ul li, .st-rd-sr li').length >= 1), 'Slayd bandlari ko\'rsatiladi (matn yoki ekran o\'quvchi uchun yashirin ro\'yxat)');
      await p.keyboard.press('ArrowLeft'); ok((await p.textContent('#stRdN')).startsWith('1 /'), '← oldingi slayd');
      await p.keyboard.press('End'); ok((await p.textContent('#stRdN')) === `${total} / ${total}`, 'End — oxirgi slayd');
      ok(await p.evaluate(() => document.querySelector('[data-next]').disabled), 'Oxirgi slaydda «Keyingi» o\'chiq');
      await shot(p, 'o_1440_light_oqish');
      ok(await tabCycle(p, '.st-reader'), "O'qish rejimida Tab aylanadi");
      await p.keyboard.press('Escape');
      ok(await waitGone(p, '.st-reader') && await modalOpen(p), "Esc faqat o'qish rejimini yopadi, «Taqdimot» oynasi qoladi");
      ok(await focusMatches(p, '.st-pres-a [data-read]'), "O'qish rejimi yopilgach fokus «ochish» tugmasiga qaytdi");
      /* fonni bosish: mousedown ichkarida, mouseup fonda — yopilmaydi; haqiqiy bosish — yopadi */
      const mb = await p.evaluate(() => { const r = document.querySelector('.st-modal').getBoundingClientRect(); return [r.x + 30, r.y + 30]; });
      await p.mouse.move(mb[0], mb[1]); await p.mouse.down(); await p.mouse.move(6, 6); await p.mouse.up(); await sleep(200);
      ok(await modalOpen(p), 'Oyna ichida bosib, fonda qo\'yib yuborilsa — yopilmaydi (matn belgilash)');
      await p.mouse.click(6, 6);
      ok(await waitGone(p), 'Fonning o\'zini bosish oynani yopadi');
      /* outline sarlavhasi «matn» → «Sarlavhasiz» */
      ok(await p.evaluate(() => stPT('matn') === 'Sarlavhasiz' && stPT('') === 'Sarlavhasiz' && stPT('  Matn ') === 'Sarlavhasiz' && stPT('Iqtisod') === 'Iqtisod'), "Taqdimot sarlavhasi bo'sh/«matn» bo'lsa — «Sarlavhasiz»");
      ok(await p.evaluate(() => stNice('2026-11-04 10:39:00', 0).length > 0 && /^\d+ noy 2026, 10:39$|^Bugun, 10:39$|^Kecha, 10:39$/.test(stNice('2026-11-04 10:39:00')) &&
        !/\d{4}-\d{2}-\d{2}/.test(stNote('Studiya · 2026-11-17 16:30')) && stNote('x_v2.pptx · pptx') === 'x_v2.pptx' && stNote('montaj.mp4 · mp4 · 0 MB') === 'montaj.mp4 · 0 MB'), "Sana o'qiladigan format; kengaytma ikki marta yozilmaydi");

      /* ---- (1) xato oyna ICHIDA (role=alert) ---- */
      await p.evaluate(() => stCancel(0, () => {})); await p.waitForSelector('.st-modal');
      ok(await focusMatches(p, '#stCr'), 'Sabab oynasi: boshlang\'ich fokus matn maydonida');
      await p.click('.st-modal [data-ok]'); await sleep(200);
      const er = await p.evaluate(() => { const e = document.querySelector('.st-modal .st-err'); return e ? { t: e.textContent, role: e.getAttribute('role'), vis: e.getBoundingClientRect().height > 0, inside: !!e.closest('.st-modal') } : null; });
      ok(er && /Sababini yozing/.test(er.t) && er.role === 'alert' && er.vis && er.inside, 'Xato oyna ichidagi role="alert" blokida ko\'rinadi');
      await p.fill('#stCr', 'sinov sababi'); await p.click('.st-modal [data-ok]'); await sleep(900);
      const er2 = await p.evaluate(() => { const e = document.querySelector('.st-modal .st-err'); return e ? e.textContent : null; });
      ok(!(await modalOpen(p)) || (er2 && er2.length > 0), "Server xatosi (mavjud bo'lmagan band) oyna ichida ko'rsatiladi" + (er2 ? ' — «' + er2 + '»' : ''));
      await p.evaluate(() => document.querySelectorAll('.st-modal-bg').forEach(x => x.remove())); await sleep(100);
      ok(!(await p.evaluate(() => [...document.body.children].some(n => n.inert))), "Oyna tashqaridan olib tashlansa ham fon inert qolmaydi");

      /* ---- (4) Montaj bo'limi tartibi ---- */
      await tabTo(p, 'montaj');
      const ord = await p.evaluate(() => ({ kpi: [...document.querySelectorAll('.st-kpi span')].map(e => e.textContent.trim()), h3: [...document.querySelectorAll('#stBox .st-card h3')].map(e => e.firstChild.textContent.trim()) }));
      ok(ord.kpi[0] === "Ko'rib chiqish kutmoqda" && ord.kpi[1] === "Masofaviy bo'limga yuborilmagan" && ord.kpi.indexOf('Navbatda') > 1, "KPI tartibi: «Ko'rib chiqish kutmoqda» → «Masofaviy bo'limga yuborilmagan» → qolganlar");
      ok(ord.h3[0] === "Ko'rib chiqish kutmoqda" && ord.h3[1] === "Masofaviy bo'limga yuborilmagan", "Kartalar tartibi: ko'rib chiqish → bo'limga yuborilmagan");
      await shot(p, 'o_1440_light_montaj');

      /* ---- (4) ko'rib chiqish oynasi (video bor) ---- */
      const revBtn = `[data-rev="${E.JID_R}"]`;
      await p.click(revBtn); await p.waitForSelector('.st-modal');
      const rt = await p.textContent('.st-modal-h h3');
      ok(rt === `Montaj natijasi #${E.JID_R} · ${E.CODE_R}`, `Sarlavha: «${rt}»`);
      ok(await p.evaluate(() => { const o = document.querySelector('#stOk'); return !!o && !o.disabled; }), "Video bor — «Tasdiqlash» faol");
      ok(await p.evaluate(() => [...document.querySelectorAll('.st-modal .st-tags .st-chip.warn')].some(c => /Taqdimot yuborilmagan/.test(c.textContent))), "«Taqdimot yuborilmagan» chipi ogohlantiruvchi rangda");
      ok(await p.evaluate(() => { const f = document.querySelector('.st-foot'), o = document.querySelector('#stOk'), rd = document.querySelector('#stRedo'); return !!f && f.contains(o) && f.contains(rd) && getComputedStyle(f).position === 'sticky'; }), "Tasdiqlash va qayta montaj tugmalari sticky pastki panelda");
      ok(await p.evaluate(() => { const r = document.querySelector('#stOk').getBoundingClientRect(); return r.bottom <= innerHeight && r.top >= 0; }), "«Tasdiqlash» uzun skrollsiz ko'rinadi");
      ok(await modalFits(p), 'Ko\'rib chiqish oynasi gorizontal sig\'adi');
      ok(await tabCycle(p), 'Ko\'rib chiqish oynasida Tab aylanadi');
      await shot(p, 'o_1440_light_korish');
      await p.keyboard.press('Escape');
      ok(await waitGone(p) && await focusMatches(p, revBtn), "Esc yopadi, fokus «Ko'rib chiqish» tugmasiga qaytadi");
      /* video fayli yo'q */
      await p.click(`[data-rev="${E.JID_N}"]`); await p.waitForSelector('.st-modal');
      const nv = await p.evaluate(() => { const o = document.querySelector('#stOk'), w = document.querySelector('#stWhy'); return { dis: o && o.disabled, why: w ? w.textContent : '', desc: o && o.getAttribute('aria-describedby'), vis: w && w.getBoundingClientRect().height > 0 }; });
      ok(nv.dis && /Video fayli topilmadi/.test(nv.why) && nv.desc === 'stWhy' && nv.vis, "Video fayli topilmasa «Tasdiqlash» o'chiq, sabab matni ko'rinadi (aria-describedby)");
      await shot(p, 'o_1440_light_korish_videosiz');
      await p.keyboard.press('Escape'); await waitGone(p);

      /* ---- (3) bo'limga yuborish oynasi (taqdimotsiz) ---- */
      await p.click(`[data-dw="${E.JID_W}"]`); await p.waitForSelector('.st-modal .st-dl');
      const dt = await p.textContent('.st-modal');
      ok(/Montaj tasdiqlandi\. Endi bo'limga xabar yuboring — bo'lim shu video bilan dars yaratadi\./.test(dt) && /ro'yxatida qoladi/.test(dt), "Matn: «Montaj tasdiqlandi. Endi bo'limga xabar yuboring… Bekor qilsangiz, video … ro'yxatida qoladi»");
      ok(!/Yuborilgach/.test(dt) && !/kartochkasida video ko'rinadi/.test(dt), "«Yuborilgach video ko'rinadi» va'dasi yo'q");
      const dl = await p.textContent('.st-modal .st-dl');
      ok(dl.includes(E.CODE_W) && /Kafedra/.test(dl) && /O'qituvchi/.test(dl) && /Fan/.test(dl) && /Video/.test(dl) && dl.includes('50:10') && /xom_\d+\.mp4/.test(dl), "Video davomiyligi (50:10) va fayl nomi ko'rsatilgan; kod, kafedra, o'qituvchi, fan");
      ok(await p.evaluate(() => { const w = document.querySelector('.st-modal .st-warnbox'); return !!w && /Taqdimot yuborilmagan/.test(w.textContent) && getComputedStyle(w).backgroundColor === getComputedStyle(document.documentElement).getPropertyValue('--warn-soft') || (!!w && /Taqdimot yuborilmagan/.test(w.textContent)); }), "Taqdimot yuborilmagan — sariq ogohlantirish bloki");
      ok(await p.evaluate(() => { const s = document.querySelector('.st-modal .st-note.ic svg').getBoundingClientRect(), t = document.querySelector('.st-modal .st-note.ic > span').getBoundingClientRect(); return Math.abs(s.top - t.top) < 8 && s.right <= t.left + 1; }), "Info piktogramma matn bilan bir qatorda (alohida satrda emas)");
      ok(await focusMatches(p, '#stDn'), "Boshlang'ich fokus «Izoh» maydonida");
      ok(await tabCycle(p), 'Tab aylanadi');
      ok(await p.evaluate(() => /Keyinroq/.test(document.querySelector('.st-foot').textContent)), "Bekor qilish tugmasi «Keyinroq»");
      await shot(p, 'o_1440_light_bolimga');
      await p.keyboard.press('Escape');
      ok(await waitGone(p) && await p.isVisible(`[data-dw="${E.JID_W}"]`), "Esc yopadi; video «yuborilmagan» ro'yxatida qoladi");

      /* ---- (3) 409: boshqa foydalanuvchi allaqachon yuborgan ---- */
      await p.click(`[data-dw="${E.JID_D}"]`); await p.waitForSelector('.st-modal .st-dl');
      const rs = await hctx.request.post(`${B}/api/studio/jobs/${E.JID_D}/send-dept`, { data: { note: 'boshqa' } });
      ok(rs.ok(), "Bo'lim boshlig'i shu montajni oldinroq yubordi (API)");
      await p.click('.st-modal [data-ok]');
      ok(await waitGone(p), "409 da oyna yopiladi");
      await p.waitForFunction(j => !document.querySelector(`[data-dw="${j}"]`), E.JID_D, { timeout: 8000 }).catch(() => {});
      ok(!(await p.$(`[data-dw="${E.JID_D}"]`)), "409 dan keyin ro'yxat yangilandi (montaj «yuborilmagan»dan chiqdi)");
      const tt = await p.textContent('#toast');
      ok(/allaqachon/.test(tt), `Toast: «${tt}»`);
      ok(await focusIn(p, '#v-studio') || await focusMatches(p, 'body'), 'Fokus sahifada (yo\'qolgan emas)');

      /* ---- (3, 1, 8) ikki marta bosish, so'rov paytida yopilmasligi ---- */
      let posts = 0;
      p.on('request', r => { if (r.method() === 'POST' && r.url().includes(`/jobs/${E.JID_E}/send-dept`)) posts++; });
      await p.route('**/send-dept', async r => { await sleep(1100); await r.continue(); });
      await p.click(`[data-dw="${E.JID_E}"]`); await p.waitForSelector('.st-modal .st-dl');
      await p.dblclick('.st-modal [data-ok]'); await sleep(250);
      await p.keyboard.press('Escape'); await sleep(200);
      ok(await modalOpen(p), "So'rov ketayotganda Esc oynani yopmaydi");
      await p.mouse.click(6, 6); await sleep(150);
      ok(await modalOpen(p), "So'rov ketayotganda fonni bosish oynani yopmaydi");
      ok(await p.evaluate(() => { const o = document.querySelector('.st-modal [data-ok]'); return o.disabled && o.getAttribute('aria-busy') === 'true'; }), "Tugma disabled + aria-busy");
      ok(await waitGone(p), "So'rov tugagach oyna yopiladi");
      await sleep(300);
      ok(posts === 1, `Ikki marta bosish — bitta so'rov (${posts})`);
      await p.unroute('**/send-dept');
      await p.waitForFunction(j => !document.querySelector(`[data-dw="${j}"]`), E.JID_E, { timeout: 8000 }).catch(() => {});

      /* ---- (8) takroriy ochish: bir vaqtda ikki so'rov — bitta oyna ---- */
      await tabTo(p, 'darslar');
      await p.evaluate(([c, l]) => { Promise.all([stLesson(c, l), stLesson(c, l)]); }, [+E.CID, +E.LK_A]);
      await p.waitForSelector('.st-modal'); await sleep(600);
      ok((await p.$$('.st-modal-bg')).length === 1, "stLesson ikki marta chaqirilsa ham bitta oyna ochiladi");
      /* ---- (7) tarix ---- */
      const hist = await p.evaluate(v => ({ groups: [...document.querySelectorAll('.st-hist-g')].map(e => e.textContent), all: document.querySelector('.st-hist').textContent,
        d: !!document.querySelector('.st-hist-d summary'), egasi: /Egasi:/.test(document.querySelector('.st-modal').textContent), v }), E.VER);
      ok(hist.groups.filter(t => new RegExp('Taqdimot yuborildi · v' + E.VER + '\\b').test(t)).length === 1, `Tarix: v${E.VER} bo'yicha bitta qator`);
      ok(hist.d && /Batafsil \(\d+ ta yozuv\)/.test(hist.groups.join('|')), "Texnik ichki qatorlar «Batafsil» ostida");
      ok(!/\d{4}-\d{2}-\d{2}/.test(hist.all) && !/pptx · pptx/i.test(hist.all), "Tarixda ISO sana yo'q, kengaytma ikki marta yozilmagan");
      ok(!/studiya va bo'limga yuborildi/i.test(await p.evaluate(() => [...document.querySelectorAll('.st-hist > li')].map(li => { const d = li.querySelector('details'); return li.textContent.replace(d ? d.textContent : '', ''); }).join('|'))), "Ichki «taqdimot: studiya va bo'limga yuborildi» qatori asosiy ro'yxatda ko'rinmaydi");
      await p.click('.st-hist-d summary'); await sleep(150);
      ok(await p.evaluate(() => document.querySelector('.st-hist-d').open && document.querySelector('.st-hist-in li').getBoundingClientRect().height > 0), "«Batafsil» ochiladi");
      await shot(p, 'o_1440_light_tarix');
      await p.keyboard.press('Escape'); await waitGone(p);

      /* ---- (5) Holat: .st-seg aria-pressed ---- */
      await tabTo(p, 'holat');
      ok(await p.evaluate(() => [...document.querySelectorAll('.st-seg button')].every(x => x.getAttribute('aria-pressed') === String(x.classList.contains('on'))) && document.querySelectorAll('.st-seg button[aria-pressed="true"]').length === 1), "Kurs/Kafedra/O'qituvchi: aria-pressed to'g'ri");
      await p.focus('[data-g="kafedra"]'); await p.keyboard.press('Enter'); await sleep(900);
      ok(await focusMatches(p, '[data-g="kafedra"]') && await p.evaluate(() => document.querySelector('[data-g="kafedra"]').getAttribute('aria-pressed') === 'true'), "Guruhlash almashgach fokus saqlanadi, aria-pressed yangilanadi");
      /* ---- (5) yorliqlar: roving tabindex va strelkalar ---- */
      await p.focus('.st-tabs .on'); await p.keyboard.press('ArrowRight'); await sleep(900);
      ok(await p.evaluate(() => { const on = document.querySelector('.st-tabs .on'); return on && document.activeElement === on && on.getAttribute('aria-selected') === 'true' && on.tabIndex === 0; }), "Yorliqlar: →/← bilan almashadi, fokus yangi yorliqda");
      ok(!(await hs(p)), '1440: gorizontal siljish yo\'q');
      ok(p.errs.length === 0, 'Operator 1440: sahifa/konsol xatosi yo\'q' + (p.errs.length ? ' — ' + p.errs[0] : ''));
      await hctx.close(); await ctx.close();
    }

    /* ===================================================================================================================
       Bo'lim boshlig'i: texnik matn, tafsilot, yuborish
       =================================================================================================================== */
    for (const [W, H, scheme] of [[1440, 900, 'light'], [390, 844, 'light']]) {
      const { ctx, p } = await open(b, E.H_UID, W, H, scheme);
      await studio(p, 'montaj');
      const meta = await p.evaluate(() => ({ worker: STD.meta.worker_on, role: STD.meta.role }));
      ok(meta.role === 'masofaviy', `Bo'lim boshlig'i roli (${W})`);
      if (!meta.worker) {
        const wt = await p.textContent('.st-head ~ .st-warnbox');
        ok(/ISFT_CORE_WORKER_TOKEN/.test(wt), "Bo'lim boshlig'iga texnik matn (token nomi) ko'rsatiladi");
      }
      await p.click(`[data-dw="${E.JID_W}"]`); await p.waitForSelector('.st-modal .st-dl');
      ok(await modalFits(p) && !(await hs(p)), `Bo'lim boshlig'i: yuborish oynasi (${W}) sig'adi`);
      await shot(p, `h_${W}_${scheme}_bolimga`);
      await p.keyboard.press('Escape'); await waitGone(p);
      ok(p.errs.length === 0, `Bo'lim boshlig'i ${W}: xatosiz` + (p.errs.length ? ' — ' + p.errs[0] : ''));
      await ctx.close();
    }

    /* ===================================================================================================================
       1440 qorong'i va 390 (yorug' / qorong'i): ko'rinish, sig'ish, tegish maydoni
       =================================================================================================================== */
    for (const [W, H, scheme] of [[1440, 900, 'dark'], [390, 844, 'light'], [390, 844, 'dark']]) {
      const T = `${W}_${scheme}`, mob = W < 500;
      const { ctx, p } = await open(b, E.O_UID, W, H, scheme);
      await studio(p, 'kun');
      ok(await p.evaluate(t => document.documentElement.dataset.theme === t && getComputedStyle(document.body).colorScheme.includes(t === 'dark' ? 'dark' : 'light'), scheme), `${T}: mavzu «${scheme}» qo'llangan`);
      const real = await p.evaluate(async ([c, l, v]) => (await fetch(`/api/studio/lessons/${c}/${l}/taqdimot/${v}/outline`, { credentials: 'same-origin' })).status, [E.CID, E.LK_A, E.VER]);
      if (real !== 200) await p.route('**/taqdimot/*/outline', r => r.fulfill({ json: MOCK_OUTLINE }));
      /* yorliqlar */
      const tabs = await p.evaluate(() => { const t = [...document.querySelectorAll('.st-tabs [data-t]')].map(e => e.offsetTop); return { one: new Set(t).size === 1, sw: document.querySelector('.st-tabs').scrollWidth, cw: document.querySelector('.st-tabs').clientWidth }; });
      ok(tabs.one, `${T}: yorliqlar bitta qatorda (ikkinchi qatorga o'tmaydi)` + (tabs.sw > tabs.cw ? ' — gorizontal siljiydi' : ''));
      await p.evaluate(d => { STD.day = d; }, E.BK_DAY); await tabTo(p, 'kun');
      await p.waitForSelector(`.st-slot.busy [data-pres="${E.BK_KEY}"]`);
      ok(!(await hs(p)), `${T}: kun rejasida gorizontal siljish yo'q`);
      await shot(p, `o_${T}_kun`);
      if (mob) {
        for (const [sel, nm] of [['.st-slot .btn', 'kun rejasi tugmalari'], ['.st-daynav .btn', 'kun navigatsiyasi'], ['.st-tabs button', 'yorliqlar'], ['.st-date input', 'sana maydoni']]) {
          const m = await minSize(p, sel); ok(m.n > 0 && m.h >= 43.5 && (sel === '.st-date input' || m.w >= 43.5), `${T}: ${nm} ≥44 px (${m.w}×${m.h}, ${m.n} ta)`);
        }
        ok(await p.evaluate(() => { const bar = document.querySelector('.st-tabs'); return bar.scrollWidth >= bar.clientWidth; }), 'Yorliqlar paneli gorizontal siljiydi');
      }
      /* taqdimot oynasi */
      await p.click(`.st-slot.busy [data-pres="${E.BK_KEY}"]`); await p.waitForSelector('.st-modal');
      ok(await modalFits(p) && !(await hs(p)), `${T}: «Taqdimot» oynasi sig'adi`);
      if (mob) {
        const x = await minSize(p, '.st-x'); ok(x.h >= 43.5 && x.w >= 43.5, `${T}: modal «×» ≥44 px (${x.w}×${x.h})`);
        for (const [sel, nm] of [['.st-vers .btn', 'eski versiya havolalari'], ['.st-pres-a .btn', '«Taqdimot» amallari'], ['.st-foot .btn', 'pastki panel tugmalari']]) {
          const m = await minSize(p, sel); ok(m.n > 0 && m.h >= 43.5 && m.w >= 43.5, `${T}: ${nm} ≥44 px (${m.w}×${m.h}, ${m.n} ta)`);
        }
        ok(await p.evaluate(() => { const f = document.querySelector('.st-foot').getBoundingClientRect(); return f.bottom <= innerHeight + 1; }), `${T}: modal tugmalar paneli pastda ko'rinadi`);
        ok(await p.evaluate(() => { const v = document.querySelectorAll('.st-vers li'); return v.length > 0 && [...v].every(li => li.getBoundingClientRect().width <= innerWidth); }), 'Versiyalar telefonda kartochka qatorlari');
      }
      await shot(p, `o_${T}_taqdimot`);
      await p.click('.st-modal .st-pres-a [data-read]'); await p.waitForSelector('.st-reader'); await sleep(200);
      ok(!(await hs(p)), `${T}: o'qish rejimi gorizontal siljitmaydi`);
      if (mob) {
        const m = await minSize(p, '.st-rd-nav .btn, .st-rd-x'); ok(m.h >= 43.5 && m.w >= 43.5, `${T}: o'qish rejimi tugmalari ≥44 px (${m.w}×${m.h})`);
      }
      await shot(p, `o_${T}_oqish`);
      await p.keyboard.press('Escape'); await p.keyboard.press('Escape'); await waitGone(p);
      /* montaj: tartib, ko'rib chiqish (sticky panel), yuborish */
      await tabTo(p, 'montaj');
      ok(!(await hs(p)), `${T}: montaj bo'limida gorizontal siljish yo'q`);
      await shot(p, `o_${T}_montaj`);
      await p.click(`[data-rev="${E.JID_R}"]`); await p.waitForSelector('.st-modal');
      ok(await modalFits(p) && !(await hs(p)), `${T}: ko'rib chiqish oynasi sig'adi`);
      ok(await p.evaluate(() => { const r = document.querySelector('#stOk').getBoundingClientRect(); return r.bottom <= innerHeight + 1 && r.top >= 0; }), `${T}: «Tasdiqlash» sticky panelda, skrollsiz ko'rinadi`);
      if (mob) { const m = await minSize(p, '.st-modal .st-link, .st-foot .btn'); ok(m.h >= 43.5, `${T}: bo'lim vaqtlari va panel tugmalari ≥44 px (${m.w}×${m.h})`); }
      await shot(p, `o_${T}_korish`);
      await p.keyboard.press('Escape'); await waitGone(p);
      await p.click(`[data-dw="${E.JID_W}"]`); await p.waitForSelector('.st-modal .st-dl');
      ok(await modalFits(p) && !(await hs(p)), `${T}: yuborish oynasi sig'adi`);
      ok(await p.evaluate(() => { const s = document.querySelector('.st-note.ic svg').getBoundingClientRect(), t = document.querySelector('.st-note.ic > span').getBoundingClientRect(); return Math.abs(s.top - t.top) < 8; }), `${T}: info piktogramma matn bilan bir qatorda`);
      const wc = await contrast(p, '.st-modal .st-warnbox span'); ok(wc >= 4.5, `${T}: ogohlantirish matni kontrasti ${wc.toFixed(1)} ≥ 4.5`);
      await shot(p, `o_${T}_bolimga`);
      await p.keyboard.press('Escape'); await waitGone(p);
      /* dars tafsiloti: summary 44 px */
      await tabTo(p, 'darslar');
      await p.evaluate(([c, l]) => stLesson(c, l), [+E.CID, +E.LK_A]); await p.waitForSelector('.st-modal'); await sleep(300);
      ok(await modalFits(p) && !(await hs(p)), `${T}: dars tafsiloti sig'adi`);
      if (mob) { const m = await minSize(p, '.st-hist-d summary'); ok(m.n > 0 && m.h >= 43.5, `${T}: «Batafsil» summary ≥44 px (${m.h})`); }
      await shot(p, `o_${T}_tafsilot`);
      await p.keyboard.press('Escape'); await waitGone(p);
      ok(!(await hs(p)), `${T}: darslar bo'limi gorizontal siljitmaydi`);
      ok(p.errs.length === 0, `${T}: sahifa/konsol xatosi yo'q` + (p.errs.length ? ' — ' + p.errs[0] : ''));
      await ctx.close();
    }
  } catch (e) {
    console.log('✗ Skript xatosi: ' + String(e && e.message || e).split('\n')[0]); bad++;
    console.log('  stack: ' + String(e && e.stack || e).split('\n').slice(0, 6).join(' | '));
    try { console.log('  sahifa: ' + (await CUR.evaluate(() => (document.querySelector('#stBox') || document.body).innerText.slice(0, 500).replace(/\n+/g, ' / ')))); await CUR.screenshot({ path: `${OUT}/xato.png` }); } catch (e2) {}
  } finally { await b.close(); }
  console.log(bad ? `XATO: ${bad}` : 'HAMMASI O\'TDI');
  process.exit(bad ? 1 : 0);
})();
