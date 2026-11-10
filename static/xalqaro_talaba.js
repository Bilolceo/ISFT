/* Talaba kabineti: «Xalqaro almashinuv» sahifasi (app/xalqaro.py — /api/talaba/xalqaro). talaba.js dagi TK.addPage orqali qo'shiladi.
   Ochiq mobillik tanlovlari, mezonlar bo'yicha oldindan tekshiruv (GPA, akademik qarz), ariza va «Mening arizalarim». */
(function () {
  if (!window.TK) return;
  const { api, esc, toast, dmy, head } = window.TK;
  const pill = (t, c = "") => `<span class="tk-pill ${c}">${esc(t)}</span>`;
  const CLS = { saralandi: "ok", ketdi: "info", qaytdi: "ok", zaxira: "warn", mos_emas: "bad" };
  async function page(m) {
    const d = await api("/api/talaba/xalqaro");
    const calls = d.calls.length ? d.calls.map((c) => `<div class="tk-card"><h3>${esc(c.title)}</h3>
        <div class="tk-d">${c.host && c.host !== "—" ? esc(c.host) + " · " : ""}${esc(c.country)} · ${esc(c.seats)} o'rin · mobillik ${dmy(c.mob_start)} — ${dmy(c.mob_end)}</div>
        <div class="tk-d">Mezonlar: GPA ≥ ${esc(c.min_gpa)} · ${esc(c.lang_req)} · ${esc(c.min_course)}-kursdan${c.no_debts ? " · akademik qarzsiz" : ""} · ariza muddati <b>${dmy(c.deadline)}</b></div>
        <div class="tk-d">Sizning ko'rsatkichingiz: GPA ${c.preview.gpa != null ? Number(c.preview.gpa).toFixed(2) : "—"}, akademik qarz ${esc(c.preview.debts)} ·
          ${c.preview.ok ? pill("mezonlarga mos (til bali — sertifikatingiz bo'yicha)", "ok") : pill(c.preview.note, "warn")}</div>
        ${c.applied ? `<p class="tk-small">${pill("Ariza berilgan", "info")}</p>` : `<form class="tk-form" data-call="${c.id}">
          <div class="tk-g2"><label class="tk-field"><span>Til sertifikati</span><input name="cert" value="IELTS Academic" maxlength="120"></label>
          <label class="tk-field"><span>Bali (IELTS shkalasi, 0–9)</span><input name="score" type="number" step="0.5" min="0" max="9" required></label></div>
          <label class="tk-field"><span>Motivatsiya (kamida 20 belgi)</span><textarea name="mot" maxlength="2000" required></textarea></label>
          <div class="tk-err"></div><div class="tk-actions"><button class="btn primary" type="submit">Ariza berish</button></div></form>`}</div>`).join("")
      : `<div class="tk-card"><div class="tk-empty">Hozir ochiq tanlov yo'q. E'lonlar shu yerda chiqadi.</div></div>`;
    const mine = d.mine.length ? d.mine.map((a) => `<div class="tk-row"><div class="tk-main-c"><div class="tk-t">${esc(a.title)}</div>
        <div class="tk-d">${a.host && a.host !== "—" ? esc(a.host) + " · " : ""}${esc(a.country)} · ariza ${dmy(a.created_at)}${a.rank ? ` · saralash o'rni: ${esc(a.rank)} (${esc(a.seats)} ta o'rin)` : ""}</div>
        ${!a.eligible ? `<div class="tk-d">${esc(a.elig_note)}</div>` : ""}${a.credit_label ? `<div class="tk-d">Kreditlar: ${esc(a.credit_label)}</div>` : ""}</div>
        <div class="tk-r">${pill(a.status_label, CLS[a.status] || "")}</div></div>`).join("")
      : `<div class="tk-empty">Siz hali ariza bermagansiz.</div>`;
    m.innerHTML = head("Xalqaro almashinuv", `Hamkor OTMlarda bir semestr o'qish. Saralash: ${esc(d.score_rule)}. Natijani Xalqaro hamkorlik bo'limi e'lon qiladi.`) +
      calls + `<div class="tk-card"><h3>Mening arizalarim</h3><div class="tk-list">${mine}</div></div>`;
    m.querySelectorAll("form[data-call]").forEach((f) => f.addEventListener("submit", async (ev) => {
      ev.preventDefault();
      const err = f.querySelector(".tk-err"); err.textContent = "";
      if (f.mot.value.trim().length < 20) { err.textContent = "Motivatsiyani batafsilroq yozing (kamida 20 belgi)"; return; }
      try {
        const r = await api(`/api/talaba/xalqaro/${f.dataset.call}`, { method: "POST", body: { lang_cert: f.cert.value, lang_score: +f.score.value, motivation: f.mot.value } });
        toast(r.eligible ? "Ariza qabul qilindi — mezonlarga mos" : "Ariza qabul qilindi, lekin mezonga mos emas: " + r.note);
        page(m);
      } catch (e) { err.textContent = e.message; }
    }));
  }
  window.TK.addPage({ k: "xalqaro", t: "Xalqaro almashinuv", s: "Xalqaro", i: "globe",
    path: "M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20zM2 12h20M12 2a15 15 0 0 1 0 20M12 2a15 15 0 0 0 0 20", f: page });
})();
