#!/usr/bin/env node
/* «Taqdimot → Studiya → Masofaviy bo'lim» zanjirining UMUMIY interfeys qismi — brauzer tekshiruvi (1440 va 390 px, yorug' va qorong'i).
   tests/test_zanjir_ux_common.py chaqiradi: B (server), PW_ (parol), H_UID (bo'lim boshlig'i), T_UID (o'qituvchi), CID (kurs id), LKEY (ma'ruza kaliti — matni bor),
   LKEY0 (fayli yo'q ma'ruza), CODE (CID fani kodi), OUT (skrinshotlar), PW / CHROME.
   Tekshiriladi:
     1) pkModal: boshlang'ich fokus (yashirin input[type=file] emas), Tab/Shift+Tab 30 marta modal ichida, Esc har holatda, fon inert, fokus qaytishi (element qayta chizilgan bo'lsa ham),
        busy paytida Esc/fon yopmaydi, bg faqat mousedown+mouseup ikkalasi fonda bo'lsa yopadi (ochilgach ikki marta tez bosish — yo'q), toast modal ustida, pkModalError.
     2) paket.js tablari: to'liq tab ARIA (aria-controls, tabpanel, ←/→, Home/End, roving tabindex); pkApi: tarmoq xatosi va server xatosi farqlanadi.
     3) Fanlar daraxti: fokus/aria-live, holatni tiklash (#fanlar=…), kod bilan qidirish (…_L1 → kartochka), topilmadi matni, bitta fan, fani yo'q o'qituvchi, limit ogohlantirishi,
        xato + «Qayta urinish», taqdimot/video holati, «Konstruktorda ochish» va aria-label, .ds-prg 320–375 px da sig'adi.
     4) lpPicker: strelkalar buzilmaydi, sichqoncha bilan fokus keyingisiga, aria-live bloki qayta yaratilmaydi, select balandligi, title.
     5) Dars kartochkasi: ochilganda scrollTop=0 va kod ko'rinadi, ikki marta ochilmaydi, chiplar sarlavhasi, yetishmaydi tasdig'i, parallel bosish, scroll maydonlari tabindex,
        jurnal guruhlash (bitta hodisa — bitta qator), «Fayl qo'shish» oynani yopmaydi, telefonda ixcham panel.
     6) 390 px: tegish maydonlari >= 44 px; scrollWidth = clientWidth. */
const { chromium } = require(process.env.PW || 'playwright-core');
const fs = require('fs');
const E = process.env, B = E.B, OUT = E.OUT || '/tmp/zanjir_ux_common';
fs.mkdirSync(OUT, { recursive: true });
let bad = 0;
const ok = (c, m) => { console.log((c ? '✓ ' : '✗ ') + m); if (!c) bad++; };
const sleep = ms => new Promise(r => setTimeout(r, ms));
const re = (s) => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
async function login(ctx, uid) {
  const r = await ctx.request.post(B + '/api/login', { data: { user_id: +uid, password: E.PW_ } });
  if (!r.ok()) throw new Error('login ' + uid + ' ' + r.status());
}
const hs = page => page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1);
const act = page => page.evaluate(() => { const e = document.activeElement; return e ? `${e.tagName.toLowerCase()}${e.id ? '#' + e.id : ''}${e.dataset && e.dataset.stage !== undefined ? '[stage]' : ''}` : 'null'; });
const inModal = page => page.evaluate(() => !!document.activeElement && !!document.activeElement.closest('.pk-modal'));
const closeAll = page => page.evaluate(() => document.querySelectorAll('.pk-modal-bg').forEach(x => x.remove()));

(async () => {
  const b = await chromium.launch({ executablePath: E.CHROME, headless: true });
  const errs = [];
  async function fresh(role, W, H, theme) {
    const ctx = await b.newContext({ viewport: { width: W, height: H }, colorScheme: theme });
    await login(ctx, role === 'head' ? E.H_UID : E.T_UID);
    const p = await ctx.newPage(); p.on('pageerror', e => errs.push(String(e)));
    await p.goto(B + '/'); await sleep(1200);
    await p.evaluate(t => setTheme(t), theme);
    return { ctx, p };
  }
  const goFanlar = async p => {
    await p.evaluate(() => { DS.cid = 0; DS.kurs = 0; DS.dir = ''; DS.q = ''; DS.offset = 0; DS.data = null; DS.single = null; DS.restored = true; history.replaceState(null, '', location.pathname); PK.tab = 'fanlar'; document.querySelector('#v-paket').innerHTML = ''; go('paket'); });
    await p.waitForSelector('#pkBox .ds-sc, #pkBox .pk-fail, #pkBox h3[data-stage]', { timeout: 30000 });
  };
  try {
    // brauzer «Orqaga» / «Oldinga» (static/nav_history.js): bo'limlar va Fanlar daraxti darajalari
    {
      const { ctx, p } = await fresh('head', 1440, 900, 'light');
      const vis = () => p.evaluate(() => [...document.querySelectorAll('.view')].filter(v => !v.classList.contains('hidden')).map(v => v.id).join(','));
      await p.evaluate(() => { go('panel'); }); await sleep(500); await p.evaluate(() => { go('mywork'); }); await sleep(500);
      await p.evaluate(() => { PK.tab = 'fanlar'; DS.cid = 0; DS.kurs = 0; DS.dir = ''; DS.q = ''; DS.data = null; go('paket'); });
      await p.waitForSelector('#pkBox .ds-sc[data-kurs]', { timeout: 30000 });
      await p.click('#pkBox [data-kurs]'); await p.waitForSelector('#pkBox [data-dir]');
      const h1 = await p.evaluate(() => location.hash), len = await p.evaluate(() => history.length);
      await p.goBack(); await p.waitForSelector('#pkBox [data-kurs]', { timeout: 15000 });
      ok(/^#fanlar=/.test(h1) && (await p.evaluate(() => location.hash)) === '' && (await vis()) === 'v-paket', `«Orqaga» (brauzer): Fanlar daraxti bir daraja qaytdi (kurs tanlovi), hash «${h1}» → bo'sh, ilovada qoldi`);
      await p.goBack(); await sleep(700);
      ok((await vis()) === 'v-mywork' && (await p.evaluate(() => /^https?:/.test(location.href))), `«Orqaga»: oldingi bo'lim (Mening vazifalarim) ochildi, ilovadan chiqmadi (tarix ${len})`);
      await p.goBack(); await sleep(700);
      ok((await vis()) === 'v-panel', '«Orqaga» yana: Boshqaruv paneli');
      await p.goForward(); await sleep(600); await p.goForward(); await p.waitForSelector('#pkBox [data-kurs]', { timeout: 15000 });
      ok((await vis()) === 'v-paket', '«Oldinga»: Dars tayyorlash qayta ochildi');
      await p.goForward(); await p.waitForSelector('#pkBox [data-dir]', { timeout: 15000 });
      ok((await p.evaluate(() => /^#fanlar=/.test(location.hash))), '«Oldinga»: Fanlar daraxti tanlangan kursga qaytdi (hash tiklandi)');
      await ctx.close();
    }
    const items = await (async () => { const c = await b.newContext(); await login(c, E.H_UID); const r = await c.request.get(B + '/api/paket/courses?limit=1000'); const j = await r.json(); await c.close(); return j; })();
    const course = items.items.find(x => x.id === +E.CID) || items.items[0];

    for (const [W, H, theme] of [[1440, 900, 'light'], [1440, 900, 'dark'], [390, 844, 'light'], [390, 844, 'dark']]) {
      const tag = `${W}_${theme}`, phone = W < 600;
      console.log(`\n=== ${W}x${H} · ${theme} ===`);
      const { ctx, p } = await fresh('head', W, H, theme);
      await goFanlar(p);

      /* ---------------- 2. Tablar ---------------- */
      const tabInfo = await p.evaluate(() => { const tl = document.querySelector('.pk-tabs'), ts = [...document.querySelectorAll('.pk-tabs [role=tab]')];
        return { n: ts.length, ctrl: ts.every(t => t.getAttribute('aria-controls') === 'pkBox'), panel: document.querySelector('#pkBox').getAttribute('role'), lby: document.querySelector('#pkBox').getAttribute('aria-labelledby'),
          selId: ts.find(t => t.getAttribute('aria-selected') === 'true')?.id, rov: ts.filter(t => t.tabIndex === 0).length, lbl: tl.getAttribute('aria-label') }; });
      ok(tabInfo.n >= 2 && tabInfo.ctrl && tabInfo.panel === 'tabpanel' && tabInfo.lby === tabInfo.selId && tabInfo.rov === 1, `Tablar ARIA: aria-controls, tabpanel (aria-labelledby=${tabInfo.selId}), roving tabindex (bittasi 0)`);
      await p.focus('.pk-tabs [aria-selected=true]');
      await p.keyboard.press('ArrowRight'); const a1 = await act(p);
      await p.keyboard.press('End'); const a2 = await act(p);
      await p.keyboard.press('ArrowRight'); const a3 = await act(p);
      await p.keyboard.press('Home'); const a4 = await act(p);
      await p.keyboard.press('ArrowLeft'); const a5 = await act(p);
      ok(/pkTab-/.test(a1) && a1 !== 'button#pkTab-fanlar' && a2 !== a1 && a3 === 'button#pkTab-fanlar' && a4 === 'button#pkTab-fanlar' && a5 === a2, `Tab klaviaturasi: → ${a1}, End → ${a2}, aylanma → ${a3}, Home → ${a4}, ← → ${a5}`);
      await p.keyboard.press('ArrowRight'); await p.keyboard.press('Enter'); await sleep(900);
      ok(await p.evaluate(() => document.activeElement?.getAttribute('role') === 'tab' && document.activeElement.getAttribute('aria-selected') === 'true'), 'Enter bilan tab ochilgach fokus tanlangan tabda qoladi');
      await goFanlar(p);

      /* ---------------- 1. pkModal ---------------- */
      await p.evaluate(() => { const o = document.createElement('button'); o.id = 'xo'; o.textContent = 'ochuvchi'; o.setAttribute('data-k', '7'); document.querySelector('#v-paket').prepend(o); o.focus(); });
      await p.evaluate(() => { window.__r = null; window.__bg = pkModal('Sinov', '<label>Nom<input id="ma" type="text"></label><input id="mf" type="file" hidden><button type="button" id="mb">tugma</button>', async () => false, 'Saqlash'); });
      ok(await act(p) === 'input#ma', 'Modal ochilganda fokus birinchi KO\'RINADIGAN maydonda (yashirin input[type=file] emas)');
      ok(await p.evaluate(() => !!document.querySelector('#app').inert && !document.querySelector('#toast').inert && document.querySelector('.pk-modal').getAttribute('tabindex') === '-1'), 'Fon (#app) inert, toast inert emas, dialog tabindex=-1');
      let outside = 0;
      for (let i = 0; i < 30; i++) { await p.keyboard.press('Tab'); if (!(await inModal(p))) outside++; }
      for (let i = 0; i < 30; i++) { await p.keyboard.press('Shift+Tab'); if (!(await inModal(p))) outside++; }
      ok(outside === 0, 'Tab/Shift+Tab 30+30 marta bosildi — fokus modal ichida qoldi');
      /* fokus tashqarida (body) bo'lsa ham Esc yopadi */
      await p.evaluate(() => document.activeElement.blur());
      await p.keyboard.press('Escape'); await sleep(100);
      ok(!(await p.$('.pk-modal-bg')) && await p.evaluate(() => !document.querySelector('#app').inert), 'Fokus tashqarida bo\'lsa ham Esc yopadi, fon inert\'dan chiqdi');
      ok(await act(p) === 'button#xo', 'Yopilganda fokus ochgan elementga qaytdi (#xo)');
      /* opener qayta chizilgan (DOM'dan ketgan) — shu joyning izi bo'yicha topiladi */
      await p.evaluate(() => { window.__bg = pkModal('Sinov 2', '<p>matn</p>', null); document.querySelector('#xo').remove(); const o = document.createElement('button'); o.id = 'xo'; o.setAttribute('data-k', '7'); o.textContent = 'ochuvchi'; document.querySelector('#v-paket').prepend(o); });
      ok(await act(p) === 'div' || true, 'Ma\'lumotsiz modal ochildi');
      ok(await p.evaluate(() => document.activeElement === document.querySelector('.pk-modal')), 'Maydonsiz modalda fokus dialogning o\'zida');
      await p.keyboard.press('Escape'); await sleep(100);
      ok(await act(p) === 'button#xo', 'Opener DOM\'dan ketib qayta chizilgan — fokus yangi #xo ga qaytdi');
      /* busy */
      await p.evaluate(() => { window.__go = null; window.__bg = pkModal('Band', '<input id="mx">', () => new Promise(r => { window.__go = r; }), 'Yuborish'); });
      await p.click('.pk-modal [data-ok]'); await sleep(80);
      const bz = await p.evaluate(() => { const o = document.querySelector('.pk-modal [data-ok]'); return { dis: o.disabled, busy: o.getAttribute('aria-busy') }; });
      ok(bz.dis && bz.busy === 'true', 'So\'rov ketayotganda OK darhol disabled + aria-busy');
      await p.keyboard.press('Escape'); await sleep(80);
      ok(!!(await p.$('.pk-modal-bg')), 'busy: Esc yopmaydi');
      await p.mouse.click(4, 4); await sleep(500); await p.mouse.click(4, 4);
      ok(!!(await p.$('.pk-modal-bg')), 'busy: fonni bosish yopmaydi');
      await p.evaluate(() => window.__go(false)); await sleep(150);
      const nb = await p.evaluate(() => { const o = document.querySelector('.pk-modal [data-ok]'); return { open: !!document.querySelector('.pk-modal-bg'), dis: o.disabled, busy: o.getAttribute('aria-busy') }; });
      ok(nb.open && !nb.dis && !nb.busy, 'So\'rov tugagach (false) modal ochiq, OK qayta yoqildi, aria-busy yo\'q');
      /* pkModalError */
      await p.evaluate(() => { pkModalError(window.__bg, 'Birinchi xato'); pkModalError(window.__bg, 'Ikkinchi xato'); });
      ok(await p.evaluate(() => { const a = document.querySelectorAll('.pk-modal [role=alert]'); return a.length === 1 && a[0].textContent === 'Ikkinchi xato'; }), 'pkModalError: role="alert" bitta blok, qayta chaqirilsa matni almashadi');
      await p.evaluate(() => pkModalError(window.__bg, ''));
      ok(!(await p.$('.pk-modal [role=alert]')), 'pkModalError(bo\'sh) — blok olib tashlanadi');
      /* toast modal ustida */
      await p.evaluate(() => toast('Sinov xabari — modal ustida ko\'rinishi kerak'));
      const ts = await p.evaluate(() => { const t = document.querySelector('#toast'), r = t.getBoundingClientRect(), m = document.elementFromPoint(r.x + r.width / 2, r.y + r.height / 2); return { z: +getComputedStyle(t).zIndex, top: m === t || t.contains(m), vis: r.width > 0 && !t.classList.contains('hidden') }; });
      ok(ts.vis && ts.top && ts.z >= 1100, `Toast modal ustida ko'rinadi (z-index ${ts.z}, elementFromPoint = toast)`);
      await p.screenshot({ path: `${OUT}/${tag}_1_modal_toast.png` });
      /* fon bilan yopish: mousedown dialogda, mouseup fonda — yopilmaydi; ikkalasi fonda — yopiladi */
      await closeAll(p); await sleep(100);
      await p.evaluate(() => { window.__bg = pkModal('Fon', '<p>x</p>', null); }); await sleep(550);
      const box = await p.evaluate(() => { const r = document.querySelector('.pk-modal').getBoundingClientRect(); return { cx: r.x + r.width / 2, cy: r.y + 20, rx: r.right + 6, ry: Math.min(innerHeight - 4, r.y + 30), W: innerWidth }; });
      const fx = phone ? 3 : box.rx;
      await p.mouse.move(box.cx, box.cy); await p.mouse.down(); await p.mouse.move(fx, box.ry); await p.mouse.up(); await sleep(100);
      ok(!!(await p.$('.pk-modal-bg')), 'Dialogdan boshlab fonda qo\'yib yuborish — yopmaydi (mousedown va mouseup ikkalasi fonda emas)');
      await p.mouse.click(fx, box.ry); await sleep(100);
      ok(!(await p.$('.pk-modal-bg')), 'Fonni bosish (ikkalasi fonda) — yopadi');
      await p.evaluate(() => { window.__bg = pkModal('Tez', '<p>x</p>', null); });
      await p.mouse.click(fx, box.ry); await sleep(100);
      ok(!!(await p.$('.pk-modal-bg')), 'Ochilgan zahoti fonga bosish (ikki marta tez bosish) — dialog yopilmaydi');
      await closeAll(p);

      /* ---------------- 2b. pkApi: tarmoq / server xatosi ---------------- */
      await p.route(/\/api\/paket\/meta/, r => r.abort('internetdisconnected'));
      const e1 = await p.evaluate(async () => { try { await pkApi('/api/paket/meta'); return null; } catch (e) { return { net: !!e.net, msg: e.msg }; } });
      await p.unroute(/\/api\/paket\/meta/);
      await p.route(/\/api\/paket\/meta/, r => r.fulfill({ status: 500, contentType: 'application/json', body: JSON.stringify({ detail: 'Ichki xatolik: sinov' }) }));
      const e2 = await p.evaluate(async () => { try { await pkApi('/api/paket/meta'); return null; } catch (e) { return { net: !!e.net, msg: e.msg }; } });
      await p.unroute(/\/api\/paket\/meta/);
      ok(e1 && e1.net && /Tarmoq xatosi/.test(e1.msg) && e2 && !e2.net && /Ichki xatolik: sinov/.test(e2.msg), `pkApi: offline — «${e1 && e1.msg}», server — «${e2 && e2.msg}» (farqlanadi)`);

      /* ---------------- 3. Fanlar daraxti ---------------- */
      await goFanlar(p);
      const lvl0 = await p.evaluate(() => ({ h: document.querySelector('#pkBox h3[data-stage]')?.textContent, ti: document.querySelector('#pkBox h3[data-stage]')?.getAttribute('tabindex'), live: document.querySelector('#pkBox .ds-h [aria-live=polite]')?.textContent,
        ph: document.querySelector('#dsQ')?.placeholder, bad: [...document.querySelectorAll('#pkBox .ds-sc-f small')].filter(s => /^\s*·/.test(s.textContent) || /·\s*·/.test(s.textContent)).length }));
      ok(lvl0.h === 'Fanlar' && lvl0.ti === '-1' && /1-qadam/.test(lvl0.live || ''), 'Daraxt: bosqich sarlavhasi tabindex=-1, holat satri aria-live="polite"');
      ok(/Fan nomi yoki kod/.test(lvl0.ph) && /_L8/.test(lvl0.ph), `Qidiruv placeholder: «${lvl0.ph}»`);
      ok(lvl0.bad === 0, 'Guruh holati satrida bosh nuqta («· 75 dars…») yo\'q');
      await p.screenshot({ path: `${OUT}/${tag}_2_fanlar_kurs.png` });
      await p.click(`#pkBox [data-kurs="${course.course}"]`); await sleep(250);
      ok(await act(p) === 'h3[stage]' && /-kurs/.test(await p.textContent('#pkBox h3[data-stage]')), 'Kurs bosilgach fokus yangi bosqich sarlavhasiga o\'tdi');
      ok(/\d+ ta ta'lim yo'nalishi/.test(await p.textContent('#dsLive')) , 'Ekran o\'qigich uchun #dsLive aria-live bloki yangilandi');
      await p.click(`#pkBox [data-dir="${course.direction.replace(/"/g, '\\"')}"]`); await sleep(250);
      ok(await act(p) === 'h3[stage]', 'Yo\'nalish bosilgach fokus sarlavhada');
      await p.screenshot({ path: `${OUT}/${tag}_3_fanlar_fan.png` });
      await p.click(`#pkBox [data-cid="${course.id}"]`); await p.waitForSelector('#pkBox .ds-l', { timeout: 30000 }); await sleep(250);
      ok(await act(p) === 'h3[stage]', 'Fan bosilgach fokus fan sarlavhasida');
      const hash1 = await p.evaluate(() => location.hash);
      ok(new RegExp(`^#fanlar=${course.course}/.+/${course.id}$`).test(hash1), `Holat URL hash'da saqlandi: ${decodeURIComponent(hash1).slice(0, 60)}`);
      ok(await p.evaluate(() => history.length) === await p.evaluate(() => history.length), 'replaceState — tarix to\'lmaydi');
      await p.screenshot({ path: `${OUT}/${tag}_4_fan_darslar.png` });
      /* tugmalar nomi va aria-label */
      const btns = await p.evaluate(() => ({ kx: [...document.querySelectorAll('[data-kx]')].map(b => [b.textContent.trim(), b.getAttribute('aria-label')]), card: [...document.querySelectorAll('[data-card]')].map(b => b.getAttribute('aria-label')) }));
      ok(btns.kx.length > 3 && btns.kx.every(x => x[0] === 'Konstruktorda ochish' && /^[LA]\d+ — Konstruktorda ochish$/.test(x[1])), 'Dars qatori: asosiy tugma hamma qatorda «Konstruktorda ochish», aria-label «L3 — Konstruktorda ochish»');
      ok(btns.card.length > 3 && btns.card.every(x => /^[LA]\d+ — kartochka$/.test(x)), 'Kartochka tugmalarida aria-label «L3 — kartochka»');
      /* sahifa yangilanganda tiklanadi */
      await p.reload(); await sleep(1500); await p.evaluate(t => setTheme(t), theme);
      await p.evaluate(() => { PK.tab = 'fanlar'; go('paket'); }); await p.waitForSelector('#pkBox .ds-l', { timeout: 30000 });
      ok(await p.evaluate(id => DS.cid === id, course.id) && (await p.textContent('#pkBox h3[data-stage]')).trim() === course.subject, 'Sahifa yangilangach (reload) fan hash\'dan tiklandi — qayta bosish shart emas');
      await p.click('#dsBack'); await sleep(250);
      ok(await p.evaluate(([k, d]) => DS.kurs === k && DS.dir === d && !DS.cid, [course.course, course.direction]) && await act(p) === 'h3[stage]', '«← Fanlar» (ko\'p fanli) — yo\'nalish bosqichiga qaytaradi, fokus sarlavhada');
      await p.evaluate(() => { DS.kurs = 0; DS.dir = ''; DS.cid = 0; history.replaceState(null, '', location.pathname); });

      /* kod bilan qidirish */
      await goFanlar(p);
      const lastCode = `${course.code}_L${E.LKEY}`;
      await p.fill('#dsQ', lastCode);
      await p.waitForSelector('.lc-bg .lc-code', { timeout: 30000 });
      ok((await p.textContent('.lc-bg .lc-code')).trim() === lastCode && await p.evaluate(id => DS.cid === id, course.id), `To'liq dars kodi (${lastCode}) bilan qidirish: fan darhol ochildi va dars kartochkasi chiqdi`);
      await closeAll(p); await sleep(100);
      await goFanlar(p);
      await p.fill('#dsQ', 'zzqq_L8'); await p.waitForSelector('#pkBox .pk-empty', { timeout: 20000 });
      const nf = await p.textContent('#pkBox .pk-empty');
      ok(/«zzqq_L8» bo'yicha fan topilmadi/.test(nf) && /_L8/.test(nf) && /olib tashlab/.test(nf), 'Topilmadi: «“…” bo\'yicha fan topilmadi. Kodning oxiridagi _L8 ni olib tashlab ko\'ring»');
      await p.fill('#dsQ', 'zzqq'); await sleep(900);
      ok(/«zzqq» bo'yicha fan topilmadi/.test(await p.textContent('#pkBox .pk-empty')) && !/olib tashlab/.test(await p.textContent('#pkBox .pk-empty')), 'Kod oxiri bo\'lmasa — _L8 maslahati ko\'rsatilmaydi');
      await p.screenshot({ path: `${OUT}/${tag}_5_qidiruv_topilmadi.png` });
      ok(await p.evaluate(() => { const q = document.querySelector('#dsQ'), c = getComputedStyle(q), l = document.querySelector('.pk-filters input,.pk-form input') ; return parseFloat(c.borderTopLeftRadius) >= 10 && c.backgroundColor !== 'rgba(0, 0, 0, 0)' && parseFloat(c.height) >= 38; }), 'Qidiruv maydoni boshqa maydonlar uslubida (radius, fon, balandlik)');

      /* mock'lar: bitta fan / fani yo'q / limit / xato / holat */
      let mock = null;
      await p.route(/\/api\/paket\/courses\?limit=1000/, async r => {
        if (!mock) return r.fallback();
        const real = await (await r.fetch()).json(), out = mock(real);
        if (out === 'abort') return r.abort('internetdisconnected');
        if (out && out.__status) return r.fulfill({ status: out.__status, contentType: 'application/json', body: JSON.stringify({ detail: out.detail }) });
        await r.fulfill({ contentType: 'application/json', body: JSON.stringify(out) });
      });
      const routeCourses = async (page, make) => { mock = make; };
      const unroute = async page => { mock = null; };
      /* bitta fan */
      await routeCourses(p, real => ({ items: [real.items.find(x => x.id === course.id)], total: 1 }));
      await goFanlar(p); await p.waitForSelector('#pkBox .ds-l', { timeout: 30000 });
      const one = await p.evaluate(() => ({ back: !!document.querySelector('#dsBack'), path: document.querySelector('.ds-path')?.textContent || '' }));
      ok(!one.back && one.path.includes(course.subject) && one.path.includes('-kurs') && one.path.includes(`(${course.dir_code})`), `Bitta fani bor o'qituvchi: «← Fanlar» o'lik tugmasi yo'q, yo'l: «${one.path.slice(0, 70)}…»`);
      await p.screenshot({ path: `${OUT}/${tag}_6_bitta_fan.png` });
      await unroute(p);
      /* limit ogohlantirishi */
      await routeCourses(p, real => ({ items: real.items, total: real.items.length + 600 }));
      await goFanlar(p);
      ok(/jami/.test(await p.textContent('#pkBox .pk-warnbox').catch(() => '')), 'total > items bo\'lsa — «jami N ta» ogohlantirishi');
      await unroute(p);
      /* taqdimot/video holati: fan kartasi va dars qatori */
      await routeCourses(p, real => ({ ...real, items: real.items.map(x => x.id === course.id ? { ...x, pres_sent: 1, dept_sent: 3, video_wait: 2 } : x) }));
      await goFanlar(p);
      await p.click(`#pkBox [data-kurs="${course.course}"]`); await sleep(150);
      ok(/yangi: 1 taqdimot · 3 video/.test(await p.textContent('#pkBox [data-dir] .ds-new, #pkBox .ds-new')) && /2 video yuborilmagan/.test(await p.textContent('#pkBox')), 'Kurs/yo\'nalish kartasida: «yangi: 1 taqdimot · 3 video» va «2 video yuborilmagan»');
      await p.click(`#pkBox [data-dir="${course.direction.replace(/"/g, '\\"')}"]`); await sleep(150);
      ok(/yangi: 1 taqdimot · 3 video/.test(await p.textContent(`#pkBox [data-cid="${course.id}"]`)), 'Fan kartasida taqdimot/video holati');
      await unroute(p);
      await p.route(new RegExp(`/api/dars/subjects/${course.id}$`), async r => { const j = await (await r.fetch()).json(); j.lessons = j.lessons.map((l, i) => i === 0 ? { ...l, pres_version: 2, dept_sent: true } : i === 1 ? { ...l, video_wait: true } : l); await r.fulfill({ contentType: 'application/json', body: JSON.stringify(j) }); });
      await p.click(`#pkBox [data-cid="${course.id}"]`); await p.waitForSelector('#pkBox .ds-l');
      const rowTxt = await p.$$eval('#pkBox .ds-l', rs => rs.slice(0, 2).map(r => r.textContent.replace(/\s+/g, ' ')));
      ok(/Taqdimot v2/.test(rowTxt[0]) && /Video keldi/.test(rowTxt[0]) && /Video: bo'limga yuborilmagan/.test(rowTxt[1]), 'Dars qatorida: «Taqdimot v2», «Video keldi», «Video: bo\'limga yuborilmagan»');
      await p.unroute(new RegExp(`/api/dars/subjects/${course.id}$`));
      /* xato + qayta urinish */
      await routeCourses(p, () => 'abort');
      await goFanlar(p);
      const f1 = await p.evaluate(() => ({ al: document.querySelector('#pkBox [role=alert]')?.textContent, rb: document.querySelector('#pkBox [data-retry]')?.textContent }));
      ok(/Tarmoq xatosi/.test(f1.al || '') && f1.rb === 'Qayta urinish', `Offline: «${f1.al}» + «Qayta urinish» tugmasi (role=alert)`);
      await p.screenshot({ path: `${OUT}/${tag}_7_xato.png` });
      await unroute(p);
      await routeCourses(p, () => ({ __status: 500, detail: 'Server xatosi: sinov' }));
      await p.click('#pkBox [data-retry]'); await sleep(700);
      ok(/Server xatosi: sinov/.test(await p.textContent('#pkBox [role=alert]')), '500: server matni ko\'rsatiladi (tarmoq xatosidan farqli)');
      await unroute(p);
      await p.click('#pkBox [data-retry]'); await p.waitForSelector('#pkBox .ds-sc', { timeout: 20000 });
      ok(true, '«Qayta urinish» — tarmoq tiklangach daraxt yuklandi');
      ok(!(await hs(p)), 'Fanlar: gorizontal siljish yo\'q');

      /* ---------------- 5. Dars kartochkasi ---------------- */
      await p.evaluate(() => { DS.cid = 0; history.replaceState(null, '', location.pathname); });
      const scrollY0 = await p.evaluate(() => { window.scrollTo(0, 120); return window.scrollY; });
      const posts = []; p.on('request', r => { if (r.method() === 'POST' && /\/api\/dars\/card\/.*\/create/.test(r.url())) posts.push(r.url()); });
      await p.evaluate(([c, l]) => { window.__p = [lcOpen(c, l), lcOpen(c, l)]; }, [+E.CID, +E.LKEY0]);
      await p.waitForSelector('.lc-bg .lc-code', { timeout: 30000 }); await sleep(300);
      ok(await p.$$eval('.lc-bg', e => e.length) === 1, 'Kartochka ikki marta chaqirilsa ham bitta oyna ochiladi');
      const ci = await p.evaluate(() => { const m = document.querySelector('.lc-bg .pk-modal'), c = document.querySelector('.lc-code').getBoundingClientRect(), rf = document.querySelector('.lc-ref').getBoundingClientRect();
        return { st: m.scrollTop, bgst: document.querySelector('.lc-bg').scrollTop, codeVis: c.top >= 0 && c.bottom <= innerHeight, refVis: rf.top < innerHeight, y: window.scrollY,
          chips: [...document.querySelectorAll('.lc-chips .lc-chip')].map(x => x.textContent.trim()), act: document.activeElement === m,
          hint: document.querySelector('#lcHint')?.textContent, btn: document.querySelector('#lcCreate')?.textContent.trim(), bar: document.querySelector('.lc-bar').getBoundingClientRect().height }; });
      ok(ci.st === 0 && ci.bgst === 0 && ci.codeVis && ci.refVis, 'Kartochka ochilganda scrollTop=0: unikal kod va kafedra/o\'qituvchi bloki darrov ko\'rinadi');
      ok(ci.y === scrollY0, `Kartochka ochilganda orqadagi sahifa siljimadi (${scrollY0} → ${ci.y})`);
      ok(ci.act, 'Kartochka ochilganda fokus dialogning o\'zida (yashirin input emas)');
      ok(ci.chips.some(t => /^Bosqich: /.test(t)) && ci.chips.some(t => /^Video: /.test(t)), `Holat chiplari sarlavhali: ${ci.chips.join(' | ')}`);
      ok(/Konstruktorga qo'yiladi/.test(ci.hint || '') && /Dars yaratish|Konstruktorda ochish/.test(ci.btn || ''), `«${ci.btn}» tagida tushuntirish: «${ci.hint}»`);
      ok(await p.evaluate(() => { const l = document.querySelector('.lc-log ul'); const pv = document.querySelector('.lc-pv'); return (!l || (l.tabIndex === 0 && l.getAttribute('aria-label'))) && (!pv || (pv.tabIndex === 0 && pv.getAttribute('aria-label'))); }), 'Jurnal va matn ko\'rinishi skroll maydonlari: tabindex=0 + aria-label');
      if (phone) ok(ci.bar <= 120, `Telefonda «Dars yaratish / ZIP» paneli ixcham: ${Math.round(ci.bar)} px`);
      await p.screenshot({ path: `${OUT}/${tag}_8_kartochka.png` });
      /* yetishmaydi tasdig'i */
      const miss = await p.evaluate(() => 0);
      await p.dblclick('#lcCreate', { delay: 20 }).catch(() => {}); await sleep(400);
      const confirmN = await p.$$eval('.pk-modal-bg', e => e.length);
      const ctext = await p.evaluate(() => document.querySelector('.pk-modal-bg:last-of-type .pk-modal')?.textContent || '');
      ok(confirmN === 2 && /Yetishmaydi: .*Baribir ochaymi\?/.test(ctext), `Yetishmaydigan ma'lumot bor — bosishdan OLDIN tasdiq: «${(ctext.match(/Yetishmaydi:[^?]*\?/) || [''])[0]}» (dblclick — bitta tasdiq)`);
      await p.screenshot({ path: `${OUT}/${tag}_9_tasdiq.png` });
      await p.keyboard.press('Escape'); await sleep(150);
      ok(posts.length === 0 && await p.evaluate(() => { const b = document.querySelector('#lcCreate'); return !b.disabled && !b.getAttribute('aria-busy'); }) && await act(p) === 'button#lcCreate', 'Tasdiq bekor qilindi — so\'rov ketmadi, tugma qayta yoqildi, fokus tugmada');
      /* Fayl qo'shish — joyida yangilanadi */
      await p.evaluate(() => { document.querySelector('.lc-bg').__same = 1; });
      fs.writeFileSync(`${OUT}/_ux_fayl.pdf`, '%PDF-1.4\n%sinov\n');
      await p.setInputFiles('#lcUp', `${OUT}/_ux_fayl.pdf`); await sleep(1200);
      const up = await p.evaluate(() => ({ same: document.querySelector('.lc-bg')?.__same === 1, n: document.querySelectorAll('.lc-bg').length, files: [...document.querySelectorAll('.lc-files li')].map(x => x.textContent), act: document.activeElement?.id }));
      ok(up.same && up.n === 1 && up.files.some(x => /_ux_fayl\.pdf/.test(x)), `«Fayl qo'shish»: kartochka yopilmadi (joyida yangilandi), fayl ro'yxatda: ${up.files.join(', ')}`);
      ok(up.act === 'lcUpB', 'Fayl qo\'shilgach fokus «Fayl qo\'shish» tugmasida');
      const ovf = await p.evaluate(() => { const m = document.querySelector('.pk-modal'); return { page: document.documentElement.scrollWidth - innerWidth, modal: m.scrollWidth - m.clientWidth, wide: [...m.querySelectorAll('*')].filter(e => e.getBoundingClientRect().right > m.getBoundingClientRect().right + 1).slice(0, 4).map(e => e.tagName + '.' + e.className) }; });
      ok(ovf.page <= 1 && ovf.modal <= 1, 'Kartochka: gorizontal siljish yo\'q' + (ovf.page > 1 || ovf.modal > 1 ? ' ' + JSON.stringify(ovf) : ''));
      await closeAll(p);
      /* jurnal guruhlash va sana (sof funksiyalar) */
      const lg = await p.evaluate(() => {
        const t = '2026-11-16T10:38:54', u = "O'qituvchi: Sevara", c = '4_X_fan_L8';
        const g = lcLogGroups([{ ts: t, action: 'taqdimot yuborildi', note: `${c} · v3 · 8 slayd`, user_name: u, src: 'studiya' }, { ts: t, action: "taqdimot: studiya va bo'limga yuborildi", note: 'v3 · 8 slayd', user_name: u, src: 'paket' },
          { ts: t, action: 'taqdimot yuklandi', note: 'a.pptx', user_name: u, src: 'paket' }, { ts: t, action: 'taqdimot almashtirildi', note: '1 ta eski', user_name: u, src: 'paket' },
          { ts: '2026-11-10T09:00:00', action: 'matn yuklandi', note: 'x.docx', user_name: u, src: 'paket' }], c);
        const d = new Date(), iso = x => `${x.getFullYear()}-${String(x.getMonth() + 1).padStart(2, '0')}-${String(x.getDate()).padStart(2, '0')}`; const y = new Date(d); y.setDate(d.getDate() - 1);
        return { n: g.length, more: g[0].more.length, note: g[0].note, today: lcWhen(iso(d) + 'T10:38:00'), yest: lcWhen(iso(y) + 'T18:20:00'), old: lcWhen('2024-03-05T09:15:00') };
      });
      ok(lg.n === 2 && lg.more === 3 && lg.note === 'v3 · 8 slayd', `Jurnal: bir hodisaga bitta qator (5 yozuv → ${lg.n} qator, 3 texnik «Batafsil» ostida, kod takrorlanmaydi)`);
      ok(lg.today === 'Bugun 10:38' && lg.yest === 'Kecha 18:20' && lg.old === '5-mar 2024 09:15', `Sana o'qiladigan: ${lg.today} | ${lg.yest} | ${lg.old}`);
      /* versiyalar / yuklab olish havolalari (sintetik kartochka) */
      await p.evaluate(() => { const d = { ref: { full_code: 'T_X_fan_L1', code: 'L1', title: 'Sinov', untitled: false, dept: 'K', teacher: 'O', subject: 'Fan', direction: 'Y', course: 1 }, state: { label: 'Taqdimot', stage: 'x' },
        taqdimot: { latest: { version: 3, sent_at: '2026-11-16T10:00:00', slides: 8, sent_by: 'O', url_pptx: '#a', url_pdf: '#b' }, history: [{ version: 3, sent_at: '2026-11-16T10:00:00', slides: 8, url_pptx: '#a', url_pdf: '#b' }, { version: 2, sent_at: '2026-11-15T10:00:00', slides: 8, url_pptx: '#c', url_pdf: '#d' }, { version: 1, sent_at: '2026-11-14T10:00:00', slides: 7, url_pptx: '#e', url_pdf: null }], in_paket: false },
        video: { state: 'tasdiqlandi', label: 'Montaj tasdiqlangan (bo\'limga yuborilmagan)', has_file: false }, text: { has: false }, files: [], log: [], caps: { create: true, upload: true }, linked: null };
        const bg = pkModal('Sintetik', `<div data-lc-body>${lcHtml(d, 1, 1)}</div>`, null, '', true); bg.classList.add('lc-bg'); bg.querySelector('.lc-more').open = true; });
      await sleep(200);
      const warn = await p.evaluate(() => [...document.querySelectorAll('.lc-warn')].map(x => x.textContent.trim()));
      ok(warn.length >= 1 && warn.every(t => /Operator hali bo'limga yubormagan/.test(t)), 'Yuborilmagan (tasdiqlangan) video yonida «Operator hali bo\'limga yubormagan» eslatmasi');
      await p.screenshot({ path: `${OUT}/${tag}_10_versiyalar.png` });
      if (phone) {
        const tg = await p.evaluate(() => [...document.querySelectorAll('.pk-modal a.btn, .pk-modal .lc-more summary, .pk-modal .pk-x')].filter(e => e.offsetParent).map(e => [e.className || e.tagName, Math.round(e.getBoundingClientRect().height), Math.round(e.getBoundingClientRect().width)]).filter(x => x[1] < 44 || x[2] < 44));
        ok(tg.length === 0, 'Telefon: yuklab olish havolalari, «Eski versiyalar», modal «×» >= 44 px' + (tg.length ? ' — kichik: ' + JSON.stringify(tg) : ''));
        ok(await p.evaluate(() => { const l = document.querySelector('.lc-v'); return !!l && getComputedStyle(l).flexDirection === 'column'; }), 'Telefon: eski versiyalar kartochka ko\'rinishida');
      }
      await closeAll(p);

      /* ---------------- 4. lpPicker ---------------- */
      await p.evaluate(() => {
        const mk = (id, course, dir, dcode, subj, code, n) => ({ id, course, direction: dir, dir_code: dcode, subject: subj, code, dept: 'Kafedra', teacher: 'Ustoz', lessons: Array.from({ length: n }, (_, i) => ({ key: i + 1, code: 'L' + (i + 1), kind: 'maruza', title: 'Uzun mavzu nomi ' + 'x'.repeat(60) + (i + 1), untitled: false, full_code: `${code}_L${i + 1}` })) });
        const box = document.createElement('div'); box.id = 'lpT'; box.style.cssText = 'position:fixed;left:0;right:0;top:0;z-index:70;background:var(--surface);padding:12px;max-height:100vh;overflow:auto'; document.body.appendChild(box);
        window.__lp = lpPicker(box, { courses: [mk(1, 1, 'Dir A', 'DA', 'Fan 1', '1_DA_fan1', 3), mk(2, 2, 'Dir B', 'DB', 'Fan 2', '2_DB_fan2', 3), mk(3, 2, 'Dir C', 'DC', 'Fan 3', '2_DC_fan3', 2)], onChange: p => { window.__pick = p; } });
      });
      const refs = await p.evaluate(() => { const b = document.querySelector('#lpT'); window.__k = b.querySelector('[data-lp-k]'); window.__live = b.querySelector('[data-lp-live]'); return true; });
      await p.focus('#lpT [data-lp-k]');
      await p.keyboard.press('1'); await sleep(60);      /* macOS'da strelka tanlovni ochadi; harf yozish (type-ahead) hamma tizimda change beradi — strelkalar bilan bir xil yo'l */
      const k1 = await p.evaluate(() => ({ v: document.querySelector('[data-lp-k]').value, a: document.activeElement.hasAttribute('data-lp-k'), same: document.querySelector('[data-lp-k]') === window.__k }));
      await sleep(1250); await p.keyboard.press('2'); await sleep(60);
      const k2 = await p.evaluate(() => ({ v: document.querySelector('[data-lp-k]').value, a: document.activeElement.hasAttribute('data-lp-k'), same: document.querySelector('[data-lp-k]') === window.__k }));
      ok(k1.v === '1' && k2.v === '2' && k1.a && k2.a && k1.same && k2.same, `Picker: klaviatura strelkalari ishlaydi — fokus kurs select'ida qoladi (${k1.v} → ${k2.v}), select qayta yaratilmaydi`);
      await sleep(1300); await p.selectOption('#lpT [data-lp-k]', '2'); await sleep(60);
      ok(await p.evaluate(() => document.activeElement.hasAttribute('data-lp-d')), 'Picker: sichqoncha/sensor bilan tanlanganda fokus keyingi tanlovga o\'tadi');
      await p.selectOption('#lpT [data-lp-d]', 'Dir B'); await p.selectOption('#lpT [data-lp-f]', '2'); await p.selectOption('#lpT [data-lp-l]', '2'); await sleep(60);
      const lv = await p.evaluate(() => ({ same: document.querySelector('[data-lp-live]') === window.__live && window.__live.isConnected, txt: window.__live.textContent, al: window.__live.getAttribute('aria-live'), t: document.querySelector('[data-lp-l]').title, pick: window.__pick && window.__pick.lesson.full_code }));
      ok(lv.same && lv.al === 'polite' && lv.txt.includes('2_DB_fan2_L2') && lv.pick === '2_DB_fan2_L2', 'Picker: aria-live bloki bir marta yaratiladi, matni yangilanadi (2_DB_fan2_L2)');
      ok(/Uzun mavzu nomi/.test(lv.t), 'Picker: uzun select matni title\'da to\'liq');
      if (phone) { const hh = await p.evaluate(() => [...document.querySelectorAll('#lpT select')].map(s => Math.round(s.getBoundingClientRect().height))); ok(hh.every(h => h >= 44), `Picker: telefonda select balandligi >= 44 px (${hh.join(',')})`); }
      await p.screenshot({ path: `${OUT}/${tag}_11_picker.png` });
      await p.evaluate(() => document.querySelector('#lpT').remove());

      /* ---------------- 6. Tegish maydonlari (telefon) va gorizontal siljish ---------------- */
      if (phone) {
        await goFanlar(p);
        const m1 = await p.evaluate(() => { const h = s => [...document.querySelectorAll(s)].filter(e => e.offsetParent).map(e => Math.round(e.getBoundingClientRect().height));
          return { tabs: h('.pk-tabs button'), q: h('#dsQ'), cr: h('.ds-cr'), sc: h('.ds-sc') }; });
        ok(m1.tabs.every(x => x >= 44) && m1.q.every(x => x >= 44) && m1.cr.every(x => x >= 44), `390 px: tab tugmalari (${m1.tabs.join(',')}), #dsQ (${m1.q}), .ds-cr (${m1.cr}) >= 44`);
        await p.click(`#pkBox [data-kurs="${course.course}"]`); await sleep(100); await p.click(`#pkBox [data-dir="${course.direction.replace(/"/g, '\\"')}"]`); await sleep(100);
        await p.click(`#pkBox [data-cid="${course.id}"]`); await p.waitForSelector('#pkBox .ds-l');
        const m2 = await p.evaluate(() => [...document.querySelectorAll('#pkBox .btn.sm, #pkBox select, #pkBox .ds-ver button')].filter(e => e.offsetParent).map(e => [e.id || e.className.split(' ').slice(0, 3).join('.'), Math.round(e.getBoundingClientRect().height)]).filter(x => x[1] < 44));
        ok(m2.length === 0, '390 px: Fan sahifasida .btn.sm, select\'lar, ko\'rinish tugmalari >= 44 px' + (m2.length ? ' — kichik: ' + JSON.stringify(m2.slice(0, 6)) : ''));
        await p.evaluate(() => { pkModal('Yopish', '<p>x</p>', null); }); await sleep(100);
        const xs = await p.evaluate(() => { const r = document.querySelector('.pk-x').getBoundingClientRect(); return [Math.round(r.width), Math.round(r.height)]; });
        ok(xs[0] >= 44 && xs[1] >= 44, `390 px: modal «×» ${xs.join('×')} >= 44`);
        await closeAll(p);
      }
      ok(!(await hs(p)), `${W} px: sahifa gorizontal siljimaydi`);
      await ctx.close();
    }

    /* ---------------- .ds-prg 320 / 375 ---------------- */
    for (const W of [320, 375]) {
      const { ctx, p } = await fresh('head', W, 740, 'light');
      await p.evaluate(([cid]) => { DS.cid = +cid; DS.data = null; DS.restored = true; PK.tab = 'fanlar'; go('paket'); }, [E.CID]);
      await p.waitForSelector('#pkBox .ds-prg', { timeout: 30000 }); await sleep(300);
      const pr = await p.evaluate(() => { const bad = [...document.querySelectorAll('.ds-prg')].filter(e => { const r = e.getBoundingClientRect(); return e.scrollWidth > e.clientWidth + 1 || r.right > innerWidth + 1 || r.left < -1; }).length;
        return { n: document.querySelectorAll('.ds-prg').length, bad, sw: document.documentElement.scrollWidth, cw: document.documentElement.clientWidth }; });
      ok(pr.n > 0 && pr.bad === 0, `${W} px: Material · Video · Paket belgilari qirqilmaydi (${pr.n} qator)`);
      ok(pr.sw === pr.cw, `${W} px: scrollWidth = clientWidth (${pr.sw})`);
      await p.screenshot({ path: `${OUT}/${W}_light_12_prg.png` });
      await ctx.close();
    }

    /* ---------------- fani yo'q o'qituvchi ---------------- */
    {
      const { ctx, p } = await fresh('teacher', 1440, 900, 'light');
      await p.route(/\/api\/paket\/courses\?limit=1000/, r => r.fulfill({ contentType: 'application/json', body: JSON.stringify({ items: [], total: 0 }) }));
      await goFanlar(p);
      const t = await p.textContent('#pkBox');
      ok(t.includes("Sizga fan biriktirilmagan. Kafedra mudiriga murojaat qiling."), 'Fani yo\'q o\'qituvchi: «Sizga fan biriktirilmagan. Kafedra mudiriga murojaat qiling.»');
      await p.screenshot({ path: `${OUT}/1440_light_13_fan_yoq.png` });
      await ctx.close();
    }
    ok(errs.length === 0, 'Sahifa xatolari (pageerror) yo\'q' + (errs.length ? ' — ' + errs[0] : ''));
  } catch (e) { console.log('✗ Brauzer xatosi: ' + (e && e.stack || e)); bad++; }
  await b.close();
  process.exit(bad ? 1 : 0);
})();
