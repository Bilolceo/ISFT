#!/usr/bin/env node
/* Kontent paketlari: HAQIQIY yig'ilgan paket (app/paket.py + app/paket_player) brauzerda — uchidan-uchigacha integratsiya sinovi.
 *
 * Ishga tushirish (odatda tests/test_paket.py chaqiradi, PW va CHROME berilganda):
 *   PW=/path/node_modules/playwright-core CHROME=/path/to/chrome node tools/paket_build_check.js <katalog>
 *   <katalog>/scorm12, <katalog>/scorm2004, <katalog>/xapi — ochilgan paketlar (namuna: «Mikroiqtisodiyot» 1-mavzu).
 * Nima qiladi: mock LMS sahifasi (window.API / window.API_1484_11) ichida paketni iframe'da ochadi, 1366 va 390 px kenglikda barcha
 * qadamlarni (bo'lim, video, reja, matn — rasm/jadval, taqdimot, test, o'z-o'zini baholash) ko'radi, testga to'g'ri javob beradi va LMS'ga
 * yozilgan holat/ballni, konsol xatolarini, gorizontal aylantirishni tekshiradi. xAPI — launch parametrlarisiz (NEXTID iframe'i kabi):
 * ota oynaga postMessage({source:"isft-paket", event:"passed", …}) keladi va «Ko'rish rejimi» banneri chiqmaydi. Natija: "  ✓ ..." / "  ✗ ..." qatorlari; xato bo'lsa chiqish kodi 1.
 * Rise 360 (kontrakt v3): muqova qadami (fon rasmi, dars kodi, muallif), video FAYL — <video src> + <track> (subtitr) + poster elementlari borligi
 * (namunadagi .mp4 haqiqiy video emas — ffmpeg yo'q; ijro emas, elementlar tekshiriladi), slayd izohi va audiosi, kartochkalar (aylantirish),
 * test ichida moslashtirish va saralash (to'g'ri javob → 100 ball), topshiriq (matn, imzo, o'qituvchi rasmi, savollar ro'yxati).
 * layout "rise" (NEXTID ko'rinishi, standart): bitta sahifa — muqova (.r-cover, ↓), har blok .r-band[data-i]; bo'lim — «davom etish» tugmasi
 * (.r-continue): bosilmaguncha keyingi bloklar yashirin, bosilgach ochiladi; tekshiruvlar blok ichida (root) bajariladi; qorong'i OS rejimida ham yorug'.
 */
const http = require('http'), fs = require('fs'), path = require('path');
const { chromium } = require(process.env.PW);
const W = process.argv[2];
const MIME = {'.html':'text/html; charset=utf-8','.js':'text/javascript; charset=utf-8','.css':'text/css','.json':'application/json','.png':'image/png','.jpg':'image/jpeg','.woff2':'font/woff2','.pptx':'application/octet-stream',
  '.mp4':'video/mp4','.webm':'video/webm','.vtt':'text/vtt; charset=utf-8','.mp3':'audio/mpeg','.m4a':'audio/mp4','.ogg':'audio/ogg','.wav':'audio/wav'};
const LMS = `<!doctype html><html><body style="margin:0"><iframe id="sco" style="border:0;width:100%;height:100vh"></iframe><script>
window.V = {}; window.CALLS = []; window.MSGS = [];
window.addEventListener('message', e => { if (e.data && e.data.source === 'isft-paket') MSGS.push(e.data); });
const mk = (pre) => ({ [pre+'Initialize']: () => 'true', [pre+'Finish']: () => { CALLS.push('finish'); return 'true'; }, [pre+'Terminate']: () => { CALLS.push('terminate'); return 'true'; },
  [pre+'GetValue']: k => V[k] ?? '', [pre+'SetValue']: (k, v) => { V[k] = String(v); return 'true'; }, [pre+'Commit']: () => 'true',
  [pre+'GetLastError']: () => '0', [pre+'GetErrorString']: () => '', [pre+'GetDiagnostic']: () => '' });
const mode = new URLSearchParams(location.search).get('m');
if (mode === 'scorm12') { window.API = mk('LMS'); V['cmi.core.student_name'] = 'Valiyev, Ali'; V['cmi.core.lesson_status'] = 'not attempted'; V['cmi.core.entry'] = 'ab-initio'; }
if (mode === 'scorm2004') { const a = mk(''); window.API_1484_11 = a; V['cmi.learner_name'] = 'Ali Valiyev'; V['cmi.completion_status'] = 'unknown'; V['cmi.entry'] = 'ab-initio'; }
document.getElementById('sco').src = '/pkg/index.html';
</script></body></html>`;
let cur = null;
const srv = http.createServer((req, res) => {
  const u = new URL(req.url, 'http://x');
  if (u.pathname === '/favicon.ico') { res.writeHead(204); res.end(); return; }
  if (u.pathname === '/lms.html') { res.writeHead(200, {'Content-Type': 'text/html'}); res.end(LMS); return; }
  const rel = decodeURIComponent(u.pathname.replace(/^\/pkg\//, ''));
  const f = path.join(W, cur, rel);
  fs.readFile(f, (e, b) => { if (e) { res.writeHead(404); res.end(); return; } res.writeHead(200, {'Content-Type': MIME[path.extname(f)] || 'application/octet-stream'}); res.end(b); });
});
const fails = []; const ok = (c, m) => { console.log((c ? '  ✓ ' : '  ✗ ') + m); if (!c) fails.push(m); };
(async () => {
  await new Promise(r => srv.listen(0, r)); const port = srv.address().port;
  const br = await chromium.launch({executablePath: process.env.CHROME});
  for (const mode of ['scorm12', 'scorm2004', 'xapi']) {
    cur = mode; console.log('== ' + mode);
    const C = JSON.parse(fs.readFileSync(path.join(W, mode, 'content.json')));
    for (const width of [1366, 390]) {
      const p = await br.newPage({viewport: {width, height: 900}, colorScheme: C.layout === 'rise' ? 'dark' : 'light'}); const errs = [];   // rise — qorong'i OS rejimida ham yorug' bo'lishi tekshiriladi
      p.on('console', m => { if (m.type() === 'error') errs.push(m.text()); }); p.on('pageerror', e => errs.push(String(e)));
      p.on('response', r => { if (r.status() >= 400) errs.push('HTTP ' + r.status() + ' ' + r.url()); });
      p.on('requestfailed', r => { if (!/youtube|ytimg|google/.test(r.url()) && !/\.(mp4|webm|mp3|m4a|ogg|wav)$/.test(r.url())) errs.push('reqfail ' + r.url()); });   // namuna media haqiqiy emas — brauzer yuklashni to'xtatadi
      await p.goto(`http://127.0.0.1:${port}/lms.html?m=${mode}`);
      const fr = await (await p.waitForSelector('#sco')).contentFrame();
      await fr.waitForFunction(() => window.ISFTPaket && window.ISFTPaket.ready, null, {timeout: 15000});
      const RISE = C.layout === 'rise';
      const NAV = RISE ? '.r-band[data-i]' : '.nav-i';
      const n = await fr.evaluate(s => document.querySelectorAll(s).length, NAV);
      const seen = await fr.evaluate(s => [...new Set([...document.querySelectorAll(s)].map(b => b.dataset.block || b.dataset.i))].length, NAV);
      // steps rejimida uzun matn bir nechta qadamga bo'linishi mumkin — har blok kamida bitta qadamda bo'lishi kerak; rise — har blok bitta tasma, muqova alohida
      const want_n = C.blocks.length + (C.cover && !RISE ? 1 : 0);   // muqova (content.cover) — steps'da alohida birinchi qadam
      ok(n >= want_n && (seen === want_n || n === want_n), `${width}px: ${n} ta ${RISE ? 'blok tasmasi' : 'qadam'}, ${C.blocks.length} ta blok${C.cover ? ' + muqova' : ''} (${C.blocks.map(b => b.type).join(',')}) · layout=${C.layout || '—'}`);
      const did = {};
      const agg = {h2: 0, table: 0, fig: 0};
      if (RISE) {
        const r = await fr.evaluate(() => { const h = document.querySelector('.r-cover'), bg = h && h.querySelector('img.r-cover-bg');
          return h ? {text: h.textContent, bg: bg ? bg.complete && bg.naturalWidth > 0 : null, go: !!h.querySelector('[data-act="begin"]'), h1: !!h.querySelector('h1'),
            dark: getComputedStyle(document.body).backgroundColor} : null; });
        ok(r && r.h1 && r.text.includes(C.lesson.code) && r.text.includes(C.lesson.title) && (!C.cover || !C.cover.author || r.text.includes(C.cover.author)) && (C.cover && C.cover.image ? r.bg === true : true) && r.go,
           `${width}px: rise muqovasi — «${C.lesson.code}-${C.lesson.title}», muallif, ↓ tugmasi${C.cover && C.cover.image ? ', fon rasmi yuklangan' : ''}`);
        ok(r && !/rgb\((\d{1,2}), (\d{1,2}), (\d{1,2})\)/.test(r.dark), `${width}px: qorong'i OS rejimida ham yorug' fon (${r && r.dark})`);
        if (C.cover) did.cover = 1;
        await fr.click('.r-go', {force: true}); await p.waitForTimeout(200);
      }
      for (let i = 0; i < n; i++) {
        const t = RISE
          ? await fr.evaluate(i => { const b = document.querySelector('.r-band[data-i="' + i + '"]'); const g = b.querySelector('.r-continue');
              if (g && !b.classList.contains('open')) g.click(); b.scrollIntoView({block: 'start'}); return g ? 'section' : (b.className.match(/\bt-(\w+)/) || [])[1]; }, i)
          : await fr.evaluate(i => { const b = document.querySelector('.nav-i[data-i="' + i + '"]'); b.click(); return b.dataset.type; }, i);
        await p.waitForTimeout(150);
        did[t] = (did[t] || 0) + 1;
        if (RISE && t === 'section') ok(await fr.evaluate(i => { const b = document.querySelector('.r-band[data-i="' + i + '"]'), ch = b.parentNode.nextElementSibling;
          return b.classList.contains('open') && (!ch || !ch.hidden); }, i), `${width}px: «davom etish» (${i}) bosildi — keyingi bo'lim ochildi`);
        if (t === 'cover') {
          const r = await fr.evaluate(() => { const h = document.querySelector('.hero'), bg = h && h.querySelector('.hero-bg');
            return h ? {text: h.textContent, bg: bg ? bg.complete && bg.naturalWidth > 0 : null, go: !!h.querySelector('[data-act="begin"]'), h1: !!h.querySelector('h1')} : null; });
          ok(r && r.h1 && new RegExp(C.lesson.code + '(-\\d+-dars)?:').test(r.text) && r.text.includes(C.lesson.title) && (!C.cover.author || r.text.includes(C.cover.author)) && (C.cover.image ? r.bg === true : r.bg === null) && r.go,
             `${width}px: muqova — «${C.lesson.code}-…-dars: …», muallif «${C.cover.author}»${C.cover.image ? ', fon rasmi yuklangan' : ''}, «Boshlash»`);
        }
        if (t === 'flashcards') {
          const fb = C.blocks.find(b => b.type === 'flashcards');
          const r = await fr.evaluate(() => { const c = [...document.querySelectorAll('.fc[data-k]')]; if (!c.length) return null; c[0].click();
            return {n: c.length, pressed: c[0].getAttribute('aria-pressed'), front: c[0].querySelector('.fc-f .fc-x')?.textContent, back: c[0].querySelector('.fc-b .fc-x')?.textContent, shown: c[0].querySelector('.fc-b')?.getAttribute('aria-hidden')}; });
          ok(r && r.n === fb.cards.length && r.pressed === 'true' && r.front === fb.cards[0].front && r.back === fb.cards[0].back && r.shown === 'false',
             `${width}px: kartochkalar — ${fb.cards.length} ta, bosilganda orqa tomoni ochiladi («${fb.cards[0].front}» → «${fb.cards[0].back}»)`);
        }
        if (t === 'assignment') {
          const ab = C.blocks.find(b => b.type === 'assignment');
          const r = await fr.evaluate(() => { const a = document.querySelector('.asg'), av = a && a.querySelector('img.asg-av');
            return a ? {text: a.innerText.replace(/\u02bb/g, "'"), li: [...a.querySelectorAll('.asg-list li')].map(x => x.innerText.replace(/\u02bb/g, "'").replace(/^\d+\s*/, '').trim()), img: av ? av.complete && av.naturalWidth > 0 : null, svg: !!a.querySelector('svg.asg-av')} : null; });
          ok(r && r.text.includes(ab.text) && r.text.includes(ab.author) && r.li.length === ab.questions.length && ab.questions.every((x, k) => r.li[k].endsWith(x)) && (ab.avatar ? r.img === true : r.svg),
             `${width}px: topshiriq — matn, imzo, ${ab.questions.length} ta savol, ${ab.avatar ? "o'qituvchi rasmi yuklangan" : 'pleyer chizgan belgi'}`);
        }
        if (t === 'slides') {
          const sb = C.blocks.find(b => b.type === 'slides');
          const s0 = sb.slides[0] || {};
          if (s0.caption || s0.audio) {
            const r = await fr.evaluate(() => ({cap: document.querySelector('.s-cap:not([hidden])')?.textContent || '', aud: document.querySelector('.s-aud:not([hidden]) audio')?.getAttribute('src') || ''}));
            ok((!s0.caption || r.cap.includes(s0.caption)) && (!s0.audio || r.aud === s0.audio), `${width}px: 1-slayd izohi${s0.audio ? ' va audiosi (<audio src="' + r.aud + '">)' : ''}`);
          }
          const s = await fr.evaluate(() => ({c: document.querySelector('.counter')?.textContent, dl: !!document.querySelector('a[href="assets/taqdimot.pptx"]')}));
          ok(s.c && (s.dl || !sb.file), `${width}px: slaydlar ko'rsatildi (${s.c}, display=${sb.display || '—'})${sb.file ? ', .pptx yuklab olish havolasi' : ''}`);
          for (let k = 0; k < 5; k++) { await fr.press('.deck', 'ArrowRight').catch(() => {}); await p.waitForTimeout(60); }
        }
        if (t === 'text') {
          const r = await fr.evaluate(() => ({h2: document.querySelectorAll('.prose h2').length, table: document.querySelectorAll('.prose table').length,
                                              fig: [...document.querySelectorAll('.prose figure img')].filter(i => i.complete && i.naturalWidth > 0).length}));
          agg.h2 += r.h2; agg.table += r.table; agg.fig += r.fig;
        }
        if (t === 'plan') {
          const pb = C.blocks.find(b => b.type === 'plan');
          ok(await fr.evaluate(() => document.querySelectorAll('.plan li').length) === pb.items.length, `${width}px: reja ${pb.items.length} band${pb.heading ? ' (' + pb.heading.slice(0, 30) + '…)' : ''}`);
        }
        if (t === 'video') {
          const vb = C.blocks.find(b => b.type === 'video');
          if (vb.provider === 'file') {     // namuna fayl haqiqiy video emas — ijro emas, <video> / <track> / poster elementlari tekshiriladi
            const r = await fr.evaluate(() => { const v = document.querySelector('video');
              return v ? {src: v.getAttribute('src'), poster: v.getAttribute('poster'), controls: v.controls, tracks: [...v.querySelectorAll('track')].map(x => [x.getAttribute('srclang'), x.getAttribute('src'), x.getAttribute('label'), x.getAttribute('kind')])} : null; });
            ok(r && r.src === vb.src && r.controls && (!vb.poster || r.poster === vb.poster) && r.tracks.length === vb.captions.length &&
               vb.captions.every((c, k) => r.tracks[k][0] === c.lang && r.tracks[k][1] === c.src && r.tracks[k][2] === c.label && /subtitles|captions/.test(r.tracks[k][3])),
               `${width}px: video fayl — <video src="${vb.src}" controls>${vb.poster ? ' + poster' : ''} + ${vb.captions.length} ta <track> (${vb.captions.map(c => c.lang).join(', ')})`);
            if (vb.captions.length) ok(await fr.evaluate(async u => (await (await fetch(u)).text()).startsWith('WEBVTT'), vb.captions[0].src), `${width}px: subtitr fayli — WebVTT (${vb.captions[0].src})`);
          } else ok(await fr.evaluate(() => !!document.querySelector('iframe[src*="youtube-nocookie.com/embed/ISFTdemo001"], [data-video], .video')), `${width}px: video bloki`);
        }
        if (t === 'section' && !RISE) ok(await fr.evaluate(() => /\S/.test(document.body.innerText)), `${width}px: bo'lim sarlavhasi`);
        if (t === 'reflect') {
          const rb = C.blocks.find(b => b.type === 'reflect');
          const fbk = await fr.evaluate(() => { const b = document.querySelector('.choice[data-k="0"]'); if (!b) return null; b.click(); return true; });
          await p.waitForTimeout(150);
          ok(fbk && await fr.evaluate(t => document.body.innerText.replace(/\u02bb/g, "'").includes(t), rb.options[0].feedback), `${width}px: o'z-o'zini baholash — javob va izoh`);
        }
      }
      const tb = C.blocks.find(b => b.type === 'text' && b.title === "Ma'ruza matni");
      if (tb) {
        const want = {h2: (tb.html.match(/<h2>/g) || []).length, table: (tb.html.match(/<table>/g) || []).length, fig: (tb.html.match(/<img /g) || []).length};
        ok(agg.h2 >= want.h2 && agg.table >= want.table && agg.fig >= want.fig, `${width}px: ma'ruza matni (h2 ${agg.h2}/${want.h2}, jadval ${agg.table}/${want.table}, rasm ${agg.fig}/${want.fig})`);
      }
      for (const b of C.blocks) if (['flashcards', 'assignment', 'video'].includes(b.type)) ok(did[b.type] >= 1, `${width}px: «${b.type}» bloki qadamlar ro'yxatida (data-type)`);
      if (C.cover) ok(did.cover === 1, `${width}px: muqova — ${RISE ? 'sahifa boshida' : 'birinchi qadam (data-type="cover")'}`);
      const q = C.blocks.find(b => b.type === 'quiz');
      if (RISE) await fr.evaluate(() => document.querySelector('.r-band.t-quiz').scrollIntoView({block: 'start'}));
      else {
        const qi = await fr.evaluate(() => +document.querySelector('.nav-i[data-type="quiz"]').dataset.i);
        await fr.evaluate(i => document.querySelector('.nav-i[data-i="' + i + '"]').click(), qi);
      }
      await p.waitForTimeout(150); if (await fr.$('[data-act="start"]')) await fr.click('[data-act="start"]');
      await fr.waitForSelector('form.qform');
      for (const x of q.questions) {
        const sel = `fieldset[data-qid="${x.id}"]`;
        if (x.type === 'fill') await fr.fill(sel + ' input', x.answers[0]);
        else if (x.type === 'match') {      // har chap band katagi → o'z juftining javobi (bosib tanlash; sensor va klaviaturada ham shu yo'l)
          for (let i = 0; i < x.pairs.length; i++) { await fr.click(`${sel} .m-slot[data-l="${i}"]`); await fr.click(`${sel} .m-bank .m-tile[data-r="${i}"]`); }
          const got = await fr.evaluate(s => [...document.querySelectorAll(s + ' .m-slot')].map(b => b.textContent.trim()), sel);
          ok(got.length === x.pairs.length && x.pairs.every((p, i) => got[i] === p.right), `${width}px: moslashtirish — ${x.pairs.length} juft joylashtirildi`);
        } else if (x.type === 'sort') {     // kartochka → o'z toifasi
          let k = 0;
          for (let c = 0; c < x.categories.length; c++) for (const _ of x.categories[c].items) { await fr.click(`${sel} .s-card[data-k="${k}"]`); await fr.click(`${sel} .s-cat[data-c="${c}"] .s-drop`); k++; }
          const got = await fr.evaluate(s => [...document.querySelectorAll(s + ' .s-cat')].map(c => [...c.querySelectorAll('.s-list .s-card')].map(b => b.textContent.trim()).sort()), sel);
          ok(x.categories.every((c, i) => JSON.stringify(got[i]) === JSON.stringify(c.items.slice().sort())) && !(await fr.$(`${sel} .s-deck .s-card`)), `${width}px: saralash — ${k} ta kartochka ${x.categories.length} toifaga ajratildi`);
        }
        else for (const i of x.correct) await fr.check(`${sel} input[value="${i}"]`);
      }
      await fr.click('form.qform [data-act="submit"]'); await p.waitForTimeout(500);
      const hs = await fr.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
      ok(hs <= 0, `${width}px: gorizontal aylantirish yo'q (${hs})`);
      const V = await p.evaluate(() => window.V);
      if (mode === 'scorm12') ok(V['cmi.core.lesson_status'] === 'passed' && V['cmi.core.score.raw'] === '100', `${width}px: SCORM 1.2 — ${V['cmi.core.lesson_status']}, ball ${V['cmi.core.score.raw']}`);
      if (mode === 'scorm2004') ok(V['cmi.completion_status'] === 'completed' && V['cmi.success_status'] === 'passed' && V['cmi.score.raw'] === '100', `${width}px: SCORM 2004 — ${V['cmi.completion_status']}/${V['cmi.success_status']}, ball ${V['cmi.score.raw']}`);
      if (mode === 'xapi') {
        ok(await fr.evaluate(() => /(100|passed|o'tdi|o‘tdi)/i.test(document.body.innerText)), `${width}px: xAPI (launch parametrlarisiz, NEXTID iframe kabi) — natija ko'rsatildi`);
        const M = await p.evaluate(() => window.MSGS);
        const pas = M.find(m => m.event === 'passed');
        ok(pas && pas.v === 1 && pas.id === C.id && pas.score && pas.score.raw === 100, `${width}px: postMessage — {source:"isft-paket", event:"passed", score.raw:100} (${M.length} ta xabar)`);
        ok(!(await fr.evaluate(() => /Ko'rish rejimi/.test(document.body.innerText))), `${width}px: ?preview=1 siz — «Ko'rish rejimi» banneri yo'q`);
      }
      ok(!errs.length, `${width}px: konsol xatolari yo'q ${errs.slice(0, 3).join(' | ')}`);
      if (width === 390) await p.screenshot({path: path.join(W, `shot_${mode}_390.png`)});
      await p.close();
    }
  }
  await br.close(); srv.close();
  console.log(fails.length ? `XATO: ${fails.length}` : 'Hammasi o\'tdi'); process.exit(fails.length ? 1 : 0);
})().catch(e => { console.error(e); process.exit(2); });
