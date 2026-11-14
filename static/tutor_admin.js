/* =====================================================================
   «Ortda qolganlar» → «AI tutor» yorlig'i (app/tutor_admin.py, /api/tutor): pilot kurslar (yoqish, rejim — hammaga / tajriba, kunlik cheklov),
   statistika (savollar, topilmadi ulushi, token va narx, shikoyatlar), tajriba qo'llari taqqoslash (test natijasi va yakunlangan darslar),
   «Eng ko'p so'ralgan savollar» (anonim, ≥ 2 talaba), o'qituvchiga savollar (javob yozish), savol-javob jurnali (taxallus bilan).
   Ruxsat serverda; bu fayl faqat ko'rsatadi. Yordamchilar: ortda.js (OQ, renderOrtda, OR_TABS, OR_TAB_CAP, OR_EXT), masofaviy.js (dl*).
   ===================================================================== */
(function () {
  "use strict";
  if (typeof window.OR_EXT !== "object" || typeof OR_TABS !== "object") return;
  OR_TABS.tutor = "AI tutor";
  OR_TAB_CAP.tutor = "tutor";
  const TS = {ref: "", flagged: false};
  const num = v => v == null ? "—" : String(v).replace(".", ",");
  const MODE_L = {javob: "Javob", maslahat: "Maslahat", topilmadi: "Topilmadi", rad: "Rad (mavzudan tashqari)", xato: "Xato", off: "O'chiq"};
  const ARM_L = {tajriba: "Tajriba (tutor bor)", nazorat: "Nazorat (tutorsiz)", hammasi: "Hammasi"};

  async function render(box) {
    const d = await dlApi("/api/tutor/meta");
    if (!TS.ref || !d.pilots.some(p => p.ref === TS.ref)) TS.ref = d.pilots[0]?.ref || "";
    const pv = d.available ? dlChip(`${d.provider_label} · ${d.model}`, "ok") : dlChip(`O'chiq: ${d.reason}`, "warn");
    box.innerHTML = `<div class="card dl-card"><div class="dl-item-h"><div><h3>AI tutor (pilot)</h3>
        <p class="muted">Faqat tasdiqlangan kurs materialidan javob beradi, manbani ko'rsatadi; test savollariga — faqat maslahat. Pilot kurslarda dars pleyerida
        «Savol berish» paneli va bilimni tekshirish yonida «Yordam» tugmasi chiqadi. Tajriba rejimida guruhlarning yarmi — taqqoslash uchun.</p></div>
        <div>${pv}</div></div></div>
      <div class="card dl-card"><h3>Pilot kurslar</h3>
        ${dlTable([["Kurs", p => `${esc(p.title)}<small>${esc(p.sub)}</small>`], ["Holat", p => p.enabled ? dlChip("Yoqilgan", "ok") : dlChip("O'chiq")],
          ["Rejim", p => `${esc(d.modes[p.mode] || p.mode)}${p.mode === "tajriba" ? `<small>guruhlar: tajriba ${p.groups.tajriba}, nazorat ${p.groups.nazorat}</small>` : ""}`],
          ["Kunlik cheklov", p => fmt(p.daily_limit), "num"], ["Indeks", p => p.index.n_chunks != null ? `${fmt(p.index.n_chunks)} parcha · ${fmt(p.index.n_lessons)} dars<small>${p.index.n_suspicious ? `${p.index.n_suspicious} shubhali jumla olib tashlandi · ` : ""}${dlDT(p.index.built_at)}</small>` : "—"],
          ["Savollar", p => `${fmt(p.questions)}<small>${fmt(p.students)} talaba</small>`, "num"],
          ["", p => `${d.caps.edit ? `<button type="button" class="btn sm ghost" data-edit="${esc(p.ref)}">Sozlash</button>` : ""}${d.caps.reindex ? `<button type="button" class="btn sm ghost" data-rx="${esc(p.ref)}">Indeks</button>` : ""}${d.caps.export ? `<a class="btn sm ghost" href="/api/tutor/pilots/export?ref=${encodeURIComponent(p.ref)}">xAPI + tutor</a>` : ""}`]],
          d.pilots, {empty: "Hali pilot kurs yo'q"})}
        ${d.caps.edit ? `<form id="tuNew" class="dl-filters"><select name="ref" aria-label="Kurs"><option value="">Kurs tanlang…</option>${d.candidates.filter(x => !d.pilots.some(p => p.ref === x.ref)).map(x => `<option value="${esc(x.ref)}">${esc(x.title)} — ${esc(x.sub)}</option>`).join("")}</select>
          <select name="mode" aria-label="Rejim">${Object.entries(d.modes).map(([k, t]) => `<option value="${k}">${esc(t)}</option>`).join("")}</select>
          <input name="limit" type="number" min="1" max="200" value="${d.default_limit}" aria-label="Kunlik cheklov" style="max-width:110px">
          <button class="btn primary sm" type="submit">Pilotni yoqish</button></form>` : ""}
      </div>
      ${d.pilots.length ? `<div class="dl-filters"><select id="tuRef" aria-label="Pilot kurs">${d.pilots.map(p => `<option value="${esc(p.ref)}" ${p.ref === TS.ref ? "selected" : ""}>${esc(p.title)} — ${esc(p.sub)}</option>`).join("")}</select></div>
        <div id="tuBody"><div class="dl-empty">Yuklanmoqda…</div></div>` : ""}`;
    box.querySelector("#tuNew")?.addEventListener("submit", async e => {
      e.preventDefault(); const f = e.target;
      if (!f.ref.value) return toast("Kursni tanlang");
      const r = await dlApi("/api/tutor/pilots", {course_ref: f.ref.value, enabled: true, mode: f.mode.value, daily_limit: +f.limit.value});
      if (r) { TS.ref = f.ref.value; toast(`Pilot yoqildi · indeks: ${r.index?.chunks ?? 0} parcha`); render(box); }
    });
    box.querySelectorAll("[data-rx]").forEach(b => b.onclick = async () => { const r = await dlApi(`/api/tutor/pilots/reindex?ref=${encodeURIComponent(b.dataset.rx)}`, {}); if (r) { toast(`Indeks: ${r.index.chunks} parcha`); render(box); } });
    box.querySelectorAll("[data-edit]").forEach(b => b.onclick = () => edit(d, d.pilots.find(p => p.ref === b.dataset.edit), box));
    const sel = box.querySelector("#tuRef");
    if (sel) { sel.onchange = () => { TS.ref = sel.value; body(d, box.querySelector("#tuBody")); }; body(d, box.querySelector("#tuBody")); }
  }

  function edit(d, p, box) {
    dlModal(`AI tutor: ${p.title}`, `<form class="dl-pol" id="tuEd"><label>Holat<select name="en"><option value="1" ${p.enabled ? "selected" : ""}>Yoqilgan</option><option value="0" ${p.enabled ? "" : "selected"}>O'chiq</option></select></label>
        <label>Rejim<select name="mode">${Object.entries(d.modes).map(([k, t]) => `<option value="${k}" ${p.mode === k ? "selected" : ""}>${esc(t)}</option>`).join("")}</select></label>
        <label>Kunlik cheklov (talaba)<input name="limit" type="number" min="1" max="200" value="${p.daily_limit}"></label>
        <p class="tiny muted">Rejim o'zgarsa — yangi tajriba boshlanadi (guruhlar qayta taqsimlanadi).</p></form>`, async () => {
      const f = document.getElementById("tuEd");
      const r = await dlApi("/api/tutor/pilots", {course_ref: p.ref, enabled: f.en.value === "1", mode: f.mode.value, daily_limit: +f.limit.value});
      if (r) { toast("Saqlandi"); render(box); }
      return !!r;
    });
  }

  async function body(d, el) {
    if (!el || !TS.ref) return;
    const ref = encodeURIComponent(TS.ref);
    const s = await dlApi(`/api/tutor/stats?ref=${ref}`);
    const S = s.stats, R = s.compare.result, A = R.arms.tajriba || {}, B = R.arms.nazorat || {};
    let html = `<div class="dl-kpis or-kpis">${dlKpi("Savollar", fmt(S.questions), `${fmt(S.students)} talaba · ${fmt(S.days)} kun`)}
        ${dlKpi("Topilmadi", dlPct(S.not_found_pct), "materialda javob yo'q", S.not_found_pct > 30 ? "warn" : "")}
        ${dlKpi("Maslahat", fmt(S.by_mode.maslahat || 0), "test/mashq savollari")}
        ${dlKpi("Rad etildi", fmt(S.by_mode.rad || 0), "mavzudan tashqari")}
        ${dlKpi("Shikoyat", fmt(S.flagged), `${fmt(S.dropped)} tasdiqlanmagan jumla olib tashlandi`, S.flagged ? "warn" : "")}
        ${dlKpi("Token / narx", `${fmt(S.tokens_in + S.tokens_out)}`, `$${num(S.cost_usd)}`)}</div>
      <div class="card dl-card"><h3>Tajriba taqqoslash</h3>
        ${dlTable([["Qo'l", r => esc(ARM_L[r.k] || r.k)], ["Talaba", r => fmt(r.n), "num"], ["Guruh", r => fmt(r.groups), "num"], ["Testdan o'tgan", r => dlPct(r.rate), "num"],
          ["Yakunlangan dars (o'rt.)", r => num(r.lessons), "num"], ["O'rtacha ball", r => num(s.compare.score[r.k]), "num"], ["Tutor savoli / talaba", r => num((s.compare.usage[r.k] || {}).per_student), "num"]],
          [{k: "tajriba", ...A}, {k: "nazorat", ...B}].filter(r => r.n))}
        <p>${R.diff == null ? "Farq: —" : `Farq (tajriba − nazorat): <b>${num(R.diff)} f.p.</b>${R.ci ? ` · 95% oraliq [${num(R.ci[0])}; ${num(R.ci[1])}]` : " · oraliq hisoblanmadi"}`}</p>
        <ul class="ks-cav">${R.caveats.map(c => `<li>${esc(c)}</li>`).join("")}</ul></div>`;
    if (s.top) html += `<div class="card dl-card"><h3>Eng ko'p so'ralgan savollar</h3><p class="tiny muted">O'xshash savollar guruhlangan; faqat kamida 2 xil talaba so'ragan savollar (anonim). «Topilmadi» ko'p bo'lsa — materialni to'ldirish kerak.</p>
        ${dlTable([["Savol", x => esc(x.question)], ["Marta", x => fmt(x.count), "num"], ["Talaba", x => fmt(x.students), "num"], ["Topilmadi", x => x.not_found ? dlChip(fmt(x.not_found), "warn") : "0", "num"], ["Dars", x => esc(x.lessons.join(", "))]],
          s.top, {empty: "Hali takrorlangan savollar yo'q"})}</div>`;
    if (d.caps.logs) {
      const [qq, lg] = await Promise.all([dlApi(`/api/tutor/questions?ref=${ref}&status=hammasi`), dlApi(`/api/tutor/log?ref=${ref}&flagged=${TS.flagged}&limit=100`)]);
      html += `<div class="card dl-card"><h3>O'qituvchiga savollar</h3>${dlTable([["Vaqt", x => dlDT(x.ts)], ["Talaba", x => esc(x.student)], ["Savol", x => `${esc(x.question)}${x.answer ? `<small>AI: ${esc(x.answer)}</small>` : ""}`],
          ["Javob", x => x.reply ? `${esc(x.reply)}<small>${esc(x.reply_by || "")}</small>` : `<button type="button" class="btn sm" data-reply="${x.id}">Javob yozish</button>`]], qq.items, {empty: "Savol yo'q"})}</div>
        <div class="card dl-card"><div class="dl-item-h"><h3>Savol-javob jurnali</h3><label class="tiny"><input type="checkbox" id="tuFl" ${TS.flagged ? "checked" : ""}> Faqat shikoyatlar</label></div>
        ${dlTable([["Vaqt", x => dlDT(x.ts)], ["Talaba", x => `${esc(x.student)}<small>${esc(ARM_L[x.arm] || x.arm || "")}</small>`], ["Dars", x => esc(x.lesson_ref || "—")],
          ["Rejim", x => dlChip(MODE_L[x.mode] || x.mode, x.mode === "javob" ? "ok" : x.mode === "maslahat" ? "" : "warn") + (x.injection ? dlChip("in'ektsiya urinishi", "bad") : "") + (x.flagged ? dlChip("shikoyat", "bad") : "")],
          ["Savol", x => esc(x.question)], ["Javob", x => `${esc(x.answer)}${x.cites.length ? `<small>Manba: ${esc(x.cites.join("; "))}</small>` : ""}${x.flag_note ? `<small>Shikoyat: ${esc(x.flag_note)}</small>` : ""}`],
          ["Token", x => `${fmt(x.tok_in + x.tok_out)}<small>${x.dropped ? `${x.dropped} jumla olib tashlandi` : ""}</small>`, "num"]], lg.items, {empty: "Jurnal bo'sh"})}</div>`;
    }
    el.innerHTML = html;
    el.querySelector("#tuFl")?.addEventListener("change", e => { TS.flagged = e.target.checked; body(d, el); });
    el.querySelectorAll("[data-reply]").forEach(b => b.onclick = () => dlModal("Talabaga javob", `<textarea id="tuRp" rows="5" style="width:100%" maxlength="2000"></textarea>`, async () => {
      const r = await dlApi(`/api/tutor/questions/${b.dataset.reply}/reply`, {reply: document.getElementById("tuRp").value});
      if (r) { toast("Javob yuborildi"); body(d, el); }
      return !!r;
    }));
  }

  window.OR_EXT.tutor = render;
})();
