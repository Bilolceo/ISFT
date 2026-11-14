/* Talaba kabineti: «Mening darslarim» (app/talaba_darslar.py → /api/talaba/darslar) va Telegram eslatmalarini ulash.
   talaba.js dagi TK.addPage kengaytmasi orqali qo'shiladi. Hamma matn esc() orqali; faqat o'z ma'lumoti (sessiyadan). */
(function () {
  "use strict";
  if (!window.TK) return;
  const { api, esc, toast, dmy, head } = window.TK;
  const ST = { boshlanmagan: "", jarayonda: "info", otmadi: "bad", yakunlandi: "ok", otdi: "ok" };
  const MARK = { kechikkan: ["Kechikkan", "bad"], bu_hafta: ["Bu hafta", "warn"], keyinroq: ["Keyinroq", ""] };
  const KIND = { maruza: "Ma'ruza", amaliy: "Amaliy", seminar: "Seminar", laboratoriya: "Laboratoriya", mustaqil: "Mustaqil ta'lim" };
  let open = null;            // ochiq kurs (ref)
  try { open = sessionStorage.getItem("tk-darslar-open"); } catch (e) {}

  function status(l) {
    if (l.status === "otdi") return `O'tdi${l.best != null ? ` · ${Math.round(l.best)} ball` : ""}`;
    if (l.status === "yakunlandi") return "Yakunlandi";
    if (l.status === "otmadi") return `Testdan o'tmadi${l.best != null ? ` · ${Math.round(l.best)}` : ""}`;
    if (l.status === "jarayonda") return `Jarayonda · ${l.pct}%`;
    return "Boshlanmagan";
  }
  const bar = (pct, cls) => `<div class="tk-meter" style="margin:6px 0 2px"><i class="${cls || ""}" style="width:${Math.max(0, Math.min(100, pct))}%"></i></div>`;

  function lessonRow(c, l) {
    const mk = l.mark && MARK[l.mark] ? `<span class="tk-pill ${MARK[l.mark][1]}">${MARK[l.mark][0]}</span>` : "";
    const btn = l.can_open
      ? `<button class="btn sm ${l.status === "otdi" || l.status === "yakunlandi" ? "ghost" : "primary"}" type="button" data-open="${esc(c.ref)}" data-l="${esc(l.code)}">${l.resume ? "Davom etish" : l.status === "otdi" || l.status === "yakunlandi" ? "Qayta ko'rish" : "Ochish"}</button>`
      : l.status === "otdi" || l.status === "yakunlandi" ? "" : `<span class="tk-small tk-muted">onlayn ochish hali yo'q</span>`;
    return `<li class="tkd-l"><span class="tkd-code">${esc(l.code)}</span>
      <div class="tkd-mid"><b>${esc(l.title)}</b><div class="tk-small tk-muted">${esc(KIND[l.kind] || "")}${l.last ? " · oxirgi: " + dmy(l.last) : ""}</div>
        <div class="tkd-st"><span class="tk-pill ${ST[l.status] || ""}">${esc(status(l))}</span>${mk}</div>
        ${l.status === "jarayonda" ? bar(l.pct, "") : ""}</div>
      <div class="tkd-act">${btn}</div></li>`;
  }

  async function launch(ref, code, btn) {
    // oyna sinxron ochiladi (popup bloklanmasin), keyin manzil beriladi
    let w = null;
    try { w = window.open("", "_blank"); } catch (e) { w = null; }
    const label = btn ? btn.textContent : "";
    if (btn) { btn.disabled = true; btn.textContent = "Ochilmoqda…"; }
    try {
      const r = await api("/api/talaba/darslar/launch", { method: "POST", body: { course_ref: ref, lesson: code } });
      if (w) { try { w.opener = null; } catch (e) {} w.location.href = r.url; } else location.href = r.url;
      toast("Dars yangi oynada ochildi — tugatgach shu sahifani yangilang");
    } catch (e) { if (w) w.close(); toast(e.message, true); }
    finally { if (btn) { btn.disabled = false; btn.textContent = label; } }
  }

  async function tgCard(box) {
    let d;
    try { d = await api("/api/talaba/telegram"); } catch (e) { box.innerHTML = ""; return; }
    box.innerHTML = `<div class="tk-card"><b>Telegram eslatmalari</b>
      ${d.linked ? `<p class="tk-small">✓ Ulangan (${dmy(d.since)}). Masofaviy ta'lim bo'limi va tyutoringiz eslatmalari Telegram'ga keladi.</p>
        <button class="btn sm ghost" type="button" data-tg="unlink">Uzish</button>`
      : `<p class="tk-small tk-muted">Darslar bo'yicha eslatmalarni Telegram'da olish uchun bir martalik kod oling va uni ISFT botiga yuboring.
        Kod 10 daqiqa amal qiladi va faqat bir marta ishlatiladi.${d.queued ? ` <b>Navbatda ${d.queued} ta eslatma</b> — ulanganingizda yuboriladi.` : ""}</p>
        <button class="btn sm" type="button" data-tg="code">Ulash kodini olish</button><div id="tkd-code"></div>`}</div>`;
    box.onclick = async (ev) => {
      const b = ev.target.closest("[data-tg]"); if (!b) return;
      if (b.dataset.tg === "check") return tgCard(box);
      try {
        if (b.dataset.tg === "unlink") { await api("/api/talaba/telegram/unlink", { method: "POST" }); toast("Telegram uzildi"); return tgCard(box); }
        const r = await api("/api/talaba/telegram/code", { method: "POST" });
        box.querySelector("#tkd-code").innerHTML = `<div class="tkd-code-box"><span class="tk-small tk-muted">Kod</span><b class="tkd-otp">${esc(r.code)}</b>
          ${r.deep_link ? `<a class="btn sm primary" href="${esc(r.deep_link)}" target="_blank" rel="noopener">Botni ochish</a>` : ""}
          <span class="tk-small tk-muted">${r.username ? `@${esc(r.username)} botiga «/start ${esc(r.code)}» yoki kodning o'zini yuboring.` : "ISFT botiga shu kodni yuboring."}
          ${r.bot ? "" : " (Bot hozircha ulanmagan — eslatmalar navbatda saqlanadi.)"}</span>
          <button class="btn sm ghost" type="button" data-tg="check">Tekshirish</button></div>`;
      } catch (e) { toast(e.message, true); }
    };
  }

  async function page(m) {
    const d = await api("/api/talaba/darslar");
    const T = d.total;
    if (!d.courses.length) {
      m.innerHTML = head("Mening darslarim", "Masofaviy kurslar, darslar va natijalar") +
        `<div class="tk-card"><div class="tk-empty">${d.masofaviy ? (d.pending && d.pending.length ? "Kurslaringiz darslari hali tayyorlanmoqda: " + d.pending.map(esc).join(", ") : "Guruhingiz uchun masofaviy kurslar hali biriktirilmagan.") : "Bu bo'lim masofaviy ta'lim talabalari uchun."}</div></div><div id="tkd-tg"></div>`;
      if (d.masofaviy) tgCard(m.querySelector("#tkd-tg"));
      return;
    }
    if (!open || !d.courses.some((c) => c.ref === open)) open = (d.next && d.next.course_ref) || d.courses[0].ref;
    const nx = d.next;
    m.innerHTML = head("Mening darslarim", "Masofaviy kurslar: darslar taqvim bo'yicha, holat va natijalar") + `
      <div class="tk-g3 tkd-sum">
        <div class="tk-card tk-stat ${T.lag ? "warn" : "ok"}"><span class="k">Bajarilgan</span><span class="v">${T.done}<small> / ${T.lessons}</small></span><span class="s">kutilgan: ${T.expected}</span></div>
        <div class="tk-card tk-stat ${T.lag ? "bad" : "ok"}"><span class="k">Ortda</span><span class="v">${T.lag}</span><span class="s">${T.lag ? "dars — taqvimdan" : "taqvim bo'yicha"}</span></div>
        <div class="tk-card tk-stat"><span class="k">Kurslar</span><span class="v">${T.courses}</span><span class="s">${T.late ? `${T.late} ta kechikkan dars` : "kechikkan dars yo'q"}</span></div>
      </div>
      ${nx ? `<div class="tk-card tkd-next"><div><span class="tk-small tk-muted">Keyingi tavsiya etilgan dars</span><b>${esc(nx.code)} · ${esc(nx.title)}</b>
          <span class="tk-small tk-muted">${esc(nx.course)}${nx.mark === "kechikkan" ? " · kechikkan" : nx.mark === "bu_hafta" ? " · bu hafta" : ""}</span></div>
          <button class="btn primary" type="button" data-open="${esc(nx.course_ref)}" data-l="${esc(nx.code)}">${nx.resume ? "Davom etish" : "Boshlash"}</button></div>` : ""}
      ${d.courses.map((c) => `<section class="tk-card tkd-c ${c.ref === open ? "on" : ""}">
        <button class="tkd-ch" type="button" data-c="${esc(c.ref)}" aria-expanded="${c.ref === open}">
          <span><b>${esc(c.title)}</b><span class="tk-small tk-muted">${c.done} / ${c.total} dars · ${c.week ? c.week + "-hafta" : "semestr boshlanmagan"}${c.avg_score != null ? " · o'rtacha ball " + Math.round(c.avg_score) : ""}</span></span>
          ${c.lag ? `<span class="tk-pill bad">−${c.lag}</span>` : `<span class="tk-pill ok">o'z vaqtida</span>`}</button>
        ${bar(c.pct, c.lag ? "warn" : "")}
        ${c.ref === open ? `<ul class="tkd-list">${c.lessons.map((l) => lessonRow(c, l)).join("") || `<li class="tk-empty">Tasdiqlangan dars hali yo'q</li>`}</ul>
          ${c.hidden ? `<p class="tk-small tk-muted">Yana ${c.hidden} ta dars tayyorlanmoqda — tasdiqlangach shu yerda chiqadi.</p>` : ""}` : ""}
      </section>`).join("")}
      ${d.pending && d.pending.length ? `<p class="tk-small tk-muted" style="margin:12px 4px 0">Tayyorlanmoqda (darslar tasdiqlangach chiqadi): ${d.pending.map(esc).join(", ")}</p>` : ""}
      <div id="tkd-tg"></div>`;
    m.onclick = (ev) => {
      const o = ev.target.closest("[data-open]");
      if (o) { launch(o.dataset.open, o.dataset.l, o); return; }
      const c = ev.target.closest("[data-c]");
      if (c) { open = open === c.dataset.c ? "" : c.dataset.c; try { sessionStorage.setItem("tk-darslar-open", open); } catch (e) {} page(m); }
    };
    tgCard(m.querySelector("#tkd-tg"));
  }

  window.TK.addPage({ k: "darslarim", t: "Mening darslarim", s: "Darslar", i: "lessons",
    path: "M4 5a2 2 0 0 1 2-2h12v16H6a2 2 0 0 0-2 2zM4 19V5M8 7h6M8 11h6", f: page });
})();
