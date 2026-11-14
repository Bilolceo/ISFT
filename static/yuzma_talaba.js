/* Talaba kabineti: «Yuzma-yuz» (app/yuzma_yuz.py → /api/talaba/yuzma) — faqat masofaviy talaba, faqat o'qish uchun.
   1) Bosh sahifada banner: semestr oldidan yuzma-yuz ro'yxatdan o'tish (muddat o'tgan — qizil, kutilmoqda — sariq) va keyingi sessiya.
   2) «Yuzma-yuz» sahifasi (TK.addPage): holat, muddat, keyingi sessiya, barcha tayinlangan tadbirlar (ro'yxat, imtihon, attestatsiya, himoya).
   talaba.js ga tegilmaydi: bosh sahifa chizilganini #tk-main kuzatuvchisi (MutationObserver) aniqlaydi. */
(function () {
  if (!window.TK) return;
  const { api, esc, dmy, head } = window.TK;
  const ST = { otgan: "ok", tayinlangan: "info", kutilmoqda: "warn", muddati_otgan: "bad", ozod: "", tatil: "" };
  const AS = { tayinlangan: "info", keldi: "ok", shubhali: "warn", kelmadi: "bad" };
  let card = null, at = 0, added = false, pending = null;
  async function load(force) {
    if (!force && card && Date.now() - at < 60000) return card;
    if (pending) return pending;
    pending = api("/api/talaba/yuzma").then((d) => { card = d; at = Date.now(); return d; }).finally(() => { pending = null; });
    return pending;
  }
  const when = (n) => `${dmy(n.date)}, ${esc(n.start_time)}–${esc(n.end_time)} · ${esc(n.room)}`;
  function bannerHtml(d) {
    const b = d.banner; if (!b) return "";
    return `<div class="tk-card yy-tk-banner"><a class="tk-warn ${esc(b.level)}" href="#yuzma"><div><b>${esc(b.title)}</b><span>${esc(b.text)}</span></div><span class="tk-go">›</span></a></div>`;
  }
  async function page(m) {
    const d = await load(true);
    if (!d.applies) { m.innerHTML = head("Yuzma-yuz", "") + `<div class="tk-card"><div class="tk-empty">Bu bo'lim masofaviy ta'lim talabalari uchun.</div></div>`; return; }
    const n = d.next;
    m.innerHTML = head("Yuzma-yuz tadbirlar", `${esc(d.term_label)}. Masofaviy ta'lim talabasi semestr oldidan LMS'da yuzma-yuz ro'yxatdan o'tadi; yakuniy nazorat, attestatsiya va himoya ham yuzma-yuz.`) +
      bannerHtml(d) +
      `<div class="tk-card yy-tk"><h3>Holatim</h3><div class="tk-pills"><span class="tk-pill ${ST[d.state] || ""}">${esc(d.state_label)}</span>
         ${d.foreign ? "" : `<span class="tk-pill">Muddat: ${dmy(d.deadline)}</span>`}</div>
         ${d.foreign ? `<p class="tk-small tk-muted" style="margin-top:8px">Xorijiy fuqarolar yuzma-yuz ro'yxatdan o'tishdan ozod.</p>` : ""}
         ${n ? `<div class="tk-row" style="margin-top:10px"><div class="tk-date"><b>${esc(n.date.slice(8, 10))}</b><small>${esc(n.date.slice(5, 7))}</small></div>
           <div class="tk-main-c"><div class="tk-t">${esc(n.title)}</div><div class="tk-d">${when(n)}</div><div class="tk-d">${esc(n.kind_label)}</div></div></div>` : ""}
         <p class="tk-small tk-muted" style="margin-top:8px">${esc(d.bring)}</p></div>
       <div class="tk-card"><h3>Mening tadbirlarim</h3>${d.items.length ? `<div class="tk-list">${d.items.map((x) => `<div class="tk-row"><div class="tk-main-c">
           <div class="tk-t">${esc(x.title)}</div><div class="tk-d">${esc(x.kind_label)} · ${when(x)}</div></div>
           <div class="tk-r"><span class="tk-pill ${AS[x.status] || ""}">${esc(x.status_label)}</span></div></div>`).join("")}</div>`
         : `<div class="tk-empty">Sizga hali tadbir tayinlanmagan.</div>`}</div>`;
  }
  function ensurePage(d) {
    if (added || !d || !d.applies) return;
    added = true;
    window.TK.addPage({ k: "yuzma", t: "Yuzma-yuz tadbirlar", s: "Yuzma-yuz", i: "yuzma",
      path: "M3 5h18v14H3zM8 12a2.5 2.5 0 1 0 0-.01M13 10h5M13 14h3", f: page });
  }
  async function onHome(m) {
    if (m.querySelector(".yy-tk-banner") || !m.querySelector(".tk-hero")) return;
    let d; try { d = await load(false); } catch (e) { return; }
    ensurePage(d);
    if (!d.applies || !d.banner || m.querySelector(".yy-tk-banner") || !m.querySelector(".tk-hero")) return;
    m.querySelector(".tk-hero").insertAdjacentHTML("afterend", bannerHtml(d));
  }
  const main = document.getElementById("tk-main");
  if (main) new MutationObserver(() => { const k = (location.hash || "#bosh").slice(1); if (k === "bosh") onHome(main); }).observe(main, { childList: true });
})();
