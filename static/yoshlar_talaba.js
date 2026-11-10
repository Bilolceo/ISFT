/* Talaba kabineti kengaytmasi: «Turar joy» (yotoqxonaga ariza, holat, to'lovlar) va «Tadbirlar» (yozilish) — /api/talaba/turarjoy, /api/talaba/tadbirlar
   (app/yoshlar.py). talaba.js dan keyin yuklanadi, TK.addPage orqali qo'shiladi. */
(function () {
  "use strict";
  if (!window.TK) return;
  const { api, esc, toast, dmy, head } = window.TK;
  const money = (n) => String(Math.round(+n || 0)).replace(/\B(?=(\d{3})+(?!\d))/g, " ") + " so'm";
  const ST = { tolangan: ["ok", "To'langan"], qarz: ["bad", "Qarz"], kutilmoqda: ["info", "Kutilmoqda"] };
  const AST = { yangi: "warn", navbatda: "info", joy_berildi: "ok", rad: "bad", bekor: "" };

  async function pDorm(m) {
    const d = await api("/api/talaba/turarjoy");
    const a = d.application, r = d.resident;
    let html = head("Turar joy", `Institutning o'z yotoqxonasi yo'q — talabalar hamkor yotoqxonalarga shartnoma asosida joylashtiriladi. Mas'ul: ${esc(d.office)}.`);
    if (r) {
      html += `<div class="tk-card"><h3>Mening joyim</h3><dl class="tk-kv"><dt>Yotoqxona</dt><dd>${esc(r.building)}</dd><dt>Manzil</dt><dd>${esc(r.address || "—")}</dd>
          <dt>Xona</dt><dd>${esc(r.room)}-xona, ${esc(r.bed_no)}-o'rin (${esc(r.floor)}-qavat)</dd><dt>Holat</dt><dd><span class="tk-pill ${r.status === "yashaydi" ? "ok" : "warn"}">${esc(r.status_l)}</span></dd>
          <dt>Oylik to'lov</dt><dd>${money(r.fee_month)} — har oyning ${esc(d.rules.due_day)}-sanasigacha</dd></dl>
          ${r.status === "band" ? `<p class="tk-small" style="margin-top:8px">Joy siz uchun bron qilingan. ${esc(d.rules.reserve_days)} kun ichida komendantga pasport bilan kelib joylashing, aks holda bron navbatdagi talabaga beriladi.</p>` : ""}</div>`;
      html += `<div class="tk-card"><h3>To'lovlar${d.debt ? ` · <span style="color:var(--bad)">qarz ${money(d.debt)}</span>` : ""}</h3><div class="tk-list">${d.charges.length ? d.charges.map((c) => `<div class="tk-row"><div class="tk-main-c">
          <div class="tk-t">${esc(c.period)} — ${money(c.amount)}</div><div class="tk-d">${dmy(c.due)} gacha${c.paid ? ` · to'langan ${money(c.paid)}${c.receipt ? " (" + esc(c.receipt) + ")" : ""}` : ""}</div></div>
          <div class="tk-r"><span class="tk-pill ${ST[c.state][0]}">${ST[c.state][1]}</span></div></div>`).join("") : '<div class="tk-empty">Hali hisob yo\'q.</div>'}</div>
          <p class="tk-small tk-muted" style="margin-top:8px">To'lov kassa yoki bank orqali; kvitansiyani komendantga ko'rsating — shu yerda belgilanadi.</p></div>`;
      if (d.violations.length) html += `<div class="tk-card"><h3>Tartib qaydlari</h3><div class="tk-list">${d.violations.map((v) => `<div class="tk-row"><div class="tk-main-c"><div class="tk-t">${esc(v.kind)}</div><div class="tk-d">${dmy(v.date)}</div></div><div class="tk-r"><span class="tk-pill warn">${esc(v.measure_l)}</span></div></div>`).join("")}</div></div>`;
      m.innerHTML = html; return;
    }
    if (a && ["yangi", "navbatda", "joy_berildi", "rad"].includes(a.status)) {
      html += `<div class="tk-card"><h3>Arizam</h3><dl class="tk-kv"><dt>Holat</dt><dd><span class="tk-pill ${AST[a.status] || ""}">${esc(a.status_l)}</span></dd>
          <dt>Topshirilgan</dt><dd>${dmy(a.submitted_at)}</dd><dt>Imtiyoz bali</dt><dd>${esc(a.score)}</dd>
          ${a.position ? `<dt>Navbatdagi o'rni</dt><dd><b>${esc(a.position)}</b></dd>` : ""}
          ${[...a.cats_l, ...a.auto_l].length ? `<dt>Hisobga olingan</dt><dd>${[...a.cats_l, ...a.auto_l].map(esc).join("; ")}</dd>` : ""}
          ${a.reason ? `<dt>Sabab</dt><dd>${esc(a.reason)}</dd>` : ""}</dl>
          ${a.status === "yangi" ? `<p class="tk-small" style="margin-top:8px">Imtiyozni tasdiqlovchi hujjatlar nusxasini ${esc(d.office)}ga olib keling — tekshirilgach ariza navbatga qo'yiladi.</p>` : ""}
          ${["yangi", "navbatda"].includes(a.status) ? `<div class="tk-actions" style="margin-top:10px"><button class="btn sm" type="button" id="yj-cancel">Arizani qaytarib olish</button></div>` : ""}</div>`;
    }
    const open = !a || ["rad", "bekor"].includes(a.status);
    if (open) {
      html += `<div class="tk-card"><h3>Yotoqxonaga ariza</h3>${d.eligible ? `<form class="tk-form" id="yj-form">
          ${d.near ? `<p class="tk-small">Toshkent shahrida yashovchilarga joy faqat imtiyozli toifa bo'yicha beriladi.</p>` : ""}
          <div class="tk-field"><span>Imtiyozli toifa (hujjat bilan tasdiqlanadi)</span>${Object.entries(d.cats).map(([k, v]) => `<label style="display:flex;gap:8px;align-items:center;font-weight:500"><input type="checkbox" name="cat" value="${esc(k)}" style="width:auto"> ${esc(v)}</label>`).join("")}</div>
          ${d.auto.length ? `<p class="tk-small tk-muted">Avtomatik hisobga olinadi: ${d.auto.map(esc).join("; ")}.</p>` : ""}
          <label class="tk-field"><span>Izoh (ixtiyoriy)</span><textarea name="note" maxlength="500" placeholder="Masalan: oilaviy sharoit"></textarea></label>
          <div class="tk-err"></div><div class="tk-actions"><button class="btn primary" type="submit">Ariza yuborish</button></div></form>`
        : `<p class="tk-small">${esc(d.why_not || "Ariza berib bo'lmaydi")}.</p>`}</div>`;
    }
    m.innerHTML = html;
    const f = m.querySelector("#yj-form");
    if (f) f.addEventListener("submit", async (ev) => {
      ev.preventDefault();
      const err = f.querySelector(".tk-err"); err.textContent = "";
      try {
        const cats = Array.from(f.querySelectorAll("input[name=cat]:checked")).map((x) => x.value);
        const r = await api("/api/talaba/turarjoy", { method: "POST", body: { cats, note: f.note.value } });
        toast(r.status === "yangi" ? "Ariza qabul qilindi — imtiyoz hujjatlarini olib keling" : "Ariza navbatga qo'yildi"); pDorm(m);
      } catch (e) { err.textContent = e.message; }
    });
    const c = m.querySelector("#yj-cancel");
    if (c) c.addEventListener("click", async () => {
      if (!c.dataset.armed) { c.dataset.armed = 1; c.textContent = "Ha, qaytarib olaman"; return; }
      try { await api("/api/talaba/turarjoy/cancel", { method: "POST" }); toast("Ariza qaytarib olindi"); pDorm(m); } catch (e) { toast(e.message, true); }
    });
  }

  async function pEvents(m) {
    const d = await api("/api/talaba/tadbirlar");
    m.innerHTML = head("Tadbirlar", "Institut tadbirlari: tasdiqlangan tadbirlarga oldindan yoziling, tadbirda QR orqali qatnashuvingiz belgilanadi.") + `
      <div class="tk-card"><h3>Kelgusi tadbirlar</h3><div class="tk-list">${d.upcoming.length ? d.upcoming.map((e) => `<div class="tk-row">
        <div class="tk-date"><b>${esc(e.date.slice(8, 10))}</b><small>${esc(e.date.slice(5, 7))}.${esc(e.date.slice(2, 4))}</small></div>
        <div class="tk-main-c"><div class="tk-t">${esc(e.title)}</div><div class="tk-d">${esc(e.start_time || "")}${e.venue ? " · " + esc(e.venue) : ""} · ${esc(e.kind_l || "")}${e.capacity ? ` · ${esc(e.reg)}/${esc(e.capacity)} joy` : ""}</div></div>
        <div class="tk-r">${e.mine ? '<span class="tk-pill ok">Yozilgansiz</span>' : (e.capacity && e.reg >= e.capacity ? '<span class="tk-pill">Joy yo\'q</span>' : `<button class="btn sm primary" type="button" data-reg="${e.id}">Yozilish</button>`)}</div></div>`).join("")
        : '<div class="tk-empty">Hozircha e\'lon qilingan tadbir yo\'q.</div>'}</div></div>
      <div class="tk-card"><h3>Qatnashgan tadbirlarim</h3><div class="tk-list">${d.attended.length ? d.attended.map((e) => `<div class="tk-row"><div class="tk-main-c"><div class="tk-t">${esc(e.title)}</div><div class="tk-d">${dmy(e.date)} · ${esc(e.kind_l || "")}</div></div></div>`).join("")
        : '<div class="tk-empty">Hali qayd yo\'q.</div>'}</div></div>`;
    m.querySelectorAll("[data-reg]").forEach((b) => b.addEventListener("click", async () => {
      b.disabled = true;
      try { await api(`/api/talaba/tadbirlar/${b.dataset.reg}/register`, { method: "POST" }); toast("Tadbirga yozildingiz"); pEvents(m); }
      catch (e) { toast(e.message, true); b.disabled = false; }
    }));
  }

  TK.addPage({ k: "turarjoy", t: "Turar joy", s: "Turar joy", i: "dorm", path: "M3 21V9l9-6 9 6v12M3 21h18M8 21v-6h8v6M8 11h2M14 11h2", f: pDorm });
  TK.addPage({ k: "tadbirlar", t: "Tadbirlar", s: "Tadbirlar", i: "event", path: "M8 2v4M16 2v4M3 9h18M5 5h14a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2zM12 12l1.2 2.4 2.6.4-1.9 1.8.5 2.6-2.4-1.3-2.4 1.3.5-2.6-1.9-1.8 2.6-.4z", f: pEvents });
})();
