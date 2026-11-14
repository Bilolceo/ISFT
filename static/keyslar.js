/* =====================================================================
   «Ortda qolganlar» kengaytmasi (docs/keyslar.md):
     Keyslar    — har bayroq keys: egasi (tyutor), SLA, majburiy natija, keyingi qadam, tushunarli sabab (app/keyslar.py, /api/ortda/keys)
     Natija     — ochilgan/yopilgan, median bog'lanish vaqti, SLA ulushi, qayta faollashish — umumiy va tyutorlar bo'yicha
     Taqvim     — kogorta (guruh) bo'yicha haftalik taqvim: chiqarilish va muddat (app/haftalik.py, /api/ortda/taqvim)
     Eslatmalar — to'siq nuqtalari, rejim (o'chiq / hammaga / tajriba), qo'llar taqqoslash, cheklovlar, jurnal (app/tajriba.py)
   Nazorat markazi: «Keyslar natijasi» kartasi (rektor, o'quv prorektori — /api/nazorat/keyslar).
   Yordamchilar: ortda.js (OQ, renderOrtda, orReasons) va masofaviy.js (dlApi, dlTable, dlModal, dlKpi, dlChip, dlPct, dlD, dlDT).
   ===================================================================== */
(function () {
  "use strict";
  if (typeof window.OR_EXT !== "object") return;
  const KS = {f: {status: "faol", owner: "", q: "", offset: 0}, cal: {course: "", group: 0}};
  const SLA = {overdue: ["SLA o'tdi", "bad"], soon: ["24 soatdan kam", "warn"], ok: ["vaqt bor", ""], met: ["SLA ichida", "ok"], missed: ["SLA'dan kech", "warn"]};
  const STC = {ochiq: "warn", jarayonda: "info", yopilgan: "ok"};
  const LV = {yuqori: ["Yuqori", "bad"], orta: ["O'rta", "warn"]};
  const num = v => v == null ? "—" : String(v).replace(".", ",");
  const hrs = h => h == null ? "—" : h < 48 ? `${num(Math.round(h * 10) / 10)} soat` : `${num(Math.round(h / 2.4) / 10)} kun`;
  const today = () => new Date(Date.now() - new Date().getTimezoneOffset() * 60000).toISOString().slice(0, 10);

  /* ---------- Keyslar ---------- */
  async function orCases(box) {
    const M = OQ.meta, F = KS.f, dept = ["masofaviy", "masofaviy_xodim"].includes(M.role);
    const d = await dlApi("/api/ortda/keys?" + new URLSearchParams({status: F.status, owner: F.owner, q: F.q, offset: F.offset, limit: 50}));
    const C = d.counts;
    box.innerHTML = `<div class="dl-kpis or-kpis">
        ${dlKpi("Ochiq", fmt(C.ochiq), "hali bog'lanilmagan", C.ochiq ? "warn" : "ok")}
        ${dlKpi("Jarayonda", fmt(C.jarayonda), "bog'lanildi, yopilmagan")}
        ${dlKpi("SLA o'tgan", fmt(C.overdue), `${d.policy.sla_days} ish kunida bog'lanilmagan`, C.overdue ? "bad" : "ok")}
        ${dept ? dlKpi("Biriktirilmagan", fmt(C.unassigned), "tyutor tanlang", C.unassigned ? "warn" : "ok") : dlKpi("Mening yuklamam", `${fmt(d.my_load || 0)} / ${d.policy.caseload_max}`, "ochiq keyslar")}
      </div>
      ${d.demo ? `<div class="dl-demo">${ico("info", 15)}<span><b>Namuna keyslar.</b> Tyutor amallari va sanalar sun'iy — natija ko'rsatkichlarini ko'rsatish uchun.</span></div>` : ""}
      <div class="dl-filters">
        <select id="ksS" aria-label="Holat">${[["faol", "Faol (ochiq va jarayonda)"], ["ochiq", "Ochiq"], ["jarayonda", "Jarayonda"], ["yopilgan", "Yopilgan"], ["hammasi", "Hammasi"]]
          .map(([k, t]) => `<option value="${k}" ${F.status === k ? "selected" : ""}>${t}</option>`).join("")}</select>
        <select id="ksO" aria-label="Egasi">${(dept ? [["", "Barcha egalar"], ["men", "Menga biriktirilgan"], ["yoq", "Biriktirilmagan"]] : [["", "Menga va guruhlarimga"], ["men", "Faqat menga biriktirilgan"]])
          .map(([k, t]) => `<option value="${k}" ${F.owner === k ? "selected" : ""}>${t}</option>`).join("")}</select>
        <input id="ksQ" type="search" placeholder="Ism yoki guruh" value="${esc(F.q)}" aria-label="Qidiruv">
        ${dept ? `<button type="button" class="btn sm ghost" id="ksSync" title="Bayroqlar bilan keyslarni hozir moslashtirish (fon jarayoni har 10 daqiqada)">${ico("refresh", 15)} Yangilash</button>` : ""}
      </div>
      <div class="card dl-card"><p class="muted or-note">Har bir bayroq — keys: egasi (tyutor), birinchi bog'lanish muddati (SLA — ${d.policy.sla_days} ish kuni), yopishda natija majburiy.
        Yopilgandan ${d.policy.reopen_days} kun o'tib talaba hali ortda bo'lsa — keys avtomatik qayta ochiladi. ${esc(d.note)}</p>
      ${dlTable([
        ["Talaba", x => `<button type="button" class="dl-link" data-ks="${x.id}">${esc(x.student.name || "—")}</button><small>${esc(x.student.grp || "")} · #${x.id}${x.src === "qayta" ? " · qayta ochilgan" : ""}</small>`],
        ["Nega", x => `${x.level && LV[x.level] ? dlChip(LV[x.level][0], LV[x.level][1]) : ""} <small class="ks-why">${esc((x.explain[0] || x.reasons[0] || "").slice(0, 170))}${x.explain.length > 1 ? ` <i>+${x.explain.length - 1}</i>` : ""}</small>`],
        ["Egasi", x => x.owner ? esc(x.owner.name) : `<span class="dl-bad">biriktirilmagan</span>`],
        ["SLA", x => `${dlChip(...(SLA[x.sla] || [x.sla, ""]))}<small>${x.first_contact_at ? "bog'lanildi " + dlDT(x.first_contact_at) : "muddat " + dlDT(x.sla_due)}</small>`],
        ["Holat", x => `${dlChip(x.status_label, STC[x.status])}${x.outcome_label ? `<small>${esc(x.outcome_label)}</small>` : ""}`],
        ["Keyingi qadam", x => x.next_step ? dlD(x.next_step) : "—"],
        ["", x => `<button type="button" class="btn sm ${x.can_act ? "primary" : "ghost"}" data-ks="${x.id}">${x.can_act ? "Ochish" : "Ko'rish"}</button>`, "or-acts"]],
        d.items, {empty: F.status === "faol" ? "Faol keys yo'q" : "Keys topilmadi", rowCls: x => x.sla === "overdue" ? "dl-row-bad" : ""})}
      ${dlPager(d.total, F.offset, 50, o => { F.offset = o; renderOrtda("keyslar"); })}</div>`;
    const re = () => { F.offset = 0; renderOrtda("keyslar"); };
    $("#ksS").onchange = e => { F.status = e.target.value; re(); };
    $("#ksO").onchange = e => { F.owner = e.target.value; re(); };
    let t; $("#ksQ").oninput = e => { clearTimeout(t); t = setTimeout(() => { F.q = e.target.value.trim(); re(); }, 350); };
    $("#ksSync")?.addEventListener("click", async () => { const r = await dlApi("/api/ortda/keys/sync", {}); if (r) { toast(`Yangi: ${r.opened}, qayta ochilgan: ${r.reopened}, tizim yopgan: ${r.auto_closed}`); re(); } });
    box.querySelectorAll("[data-ks]").forEach(b => b.onclick = () => caseCard(+b.dataset.ks));
  }

  function outcomeForm(id, closing, outs) {
    return `<div class="ks-form" data-form="${id}">
      <label><span>Natija <b class="dl-bad">*</b> <span class="muted">— yopish uchun majburiy</span></span><select data-k="outcome"><option value="">— tanlang —</option>${Object.entries(outs).map(([k, t]) => `<option value="${k}">${esc(t)}</option>`).join("")}</select></label>
      <label><span>Izoh <span class="muted">(«Boshqa» uchun majburiy)</span></span><textarea data-k="note" rows="2" maxlength="500" placeholder="Masalan: ishga joylashgan, kechqurun o'qiydi — shu hafta L5 va A9 ni tugatadi"></textarea></label>
      <label><span>Keyingi qadam sanasi <span class="muted">(yopishda majburiy, «davom ettirmaydi»dan tashqari)</span></span><input type="date" data-k="next_step" min="${today()}"></label>
    </div>`;
  }
  async function caseCard(id) {
    const x = await dlApi(`/api/ortda/keys/${id}`);
    const outs = x.outcomes || {};
    const bg = dlModal(`Keys #${x.id}: ${x.student.name || ""}`, `
      <p class="muted">${esc(x.student.grp || "")}${x.student.phone ? ` · tel. <a href="tel:${esc(x.student.phone)}">${esc(x.student.phone)}</a>` : ""} · ochilgan ${dlDT(x.opened_at)} · ${esc(x.src_label)}${x.reopened_from ? ` (#${x.reopened_from} dan)` : ""}</p>
      <p>${dlChip(x.status_label, STC[x.status])} ${dlChip(...(SLA[x.sla] || [x.sla, ""]))} <span class="muted">SLA muddati: ${dlDT(x.sla_due)} · egasi: ${x.owner ? esc(x.owner.name) : "biriktirilmagan"}</span></p>
      <div class="ks-explain"><b>Nega keys ochildi</b><ul>${x.explain.map(t => `<li>${esc(t)}</li>`).join("") || "<li>Sabab saqlanmagan</li>"}</ul>
        <p class="tiny muted">${esc(x.note)}</p></div>
      ${x.outcome_label ? `<p><b>Natija:</b> ${esc(x.outcome_label)}${x.outcome_note ? ` — ${esc(x.outcome_note)}` : ""}${x.next_step ? ` · keyingi qadam ${dlD(x.next_step)}` : ""}</p>` : ""}
      ${x.course_rows?.length ? `<p class="tiny">${x.course_rows.map(c => `<button type="button" class="dl-link" data-oc="${esc(c.ref)}">${esc(c.title)}: ${c.done}/${c.expected} dars</button>`).join(" · ")}</p>` : ""}
      ${x.can_act ? `<div class="ks-acts"><h4>Bog'lanishni qayd etish yoki yopish</h4>${outcomeForm(x.id, false, outs)}
        <div class="dl-acts"><button type="button" class="btn" data-do="contact">Bog'lanishni qayd etish</button><button type="button" class="btn primary" data-do="close">Keysni yopish</button></div></div>` : ""}
      ${x.can_assign ? `<div class="ks-acts"><h4>Tyutorga biriktirish</h4><div id="ksTu" class="muted">Yuklanmoqda…</div></div>` : ""}
      ${x.log?.length ? `<h4>Tarix</h4><ul class="or-log">${x.log.map(l => `<li>${dlDT(l.ts)} — <b>${esc(l.action)}</b> · ${esc(l.user_name || "")}${l.outcome_label ? ` · ${esc(l.outcome_label)}` : ""}${l.note ? ` · ${esc(l.note)}` : ""}${l.next_step ? ` · keyingi qadam ${dlD(l.next_step)}` : ""}</li>`).join("")}</ul>` : ""}`,
      null, "", true);
    const reload = () => { bg.remove(); renderOrtda("keyslar"); };
    bg.querySelectorAll("[data-oc]").forEach(b => b.onclick = () => { bg.remove(); orStudent(x.student.id, b.dataset.oc); });
    bg.querySelectorAll("[data-do]").forEach(b => b.onclick = async () => {
      const f = bg.querySelector(`[data-form="${x.id}"]`), v = k => f.querySelector(`[data-k="${k}"]`).value;
      if (!v("outcome")) { toast("Natijani tanlang — yopish va qayd etish uchun majburiy"); return; }
      const r = await dlApi(`/api/ortda/keys/${x.id}/${b.dataset.do}`, {outcome: v("outcome"), note: v("note"), next_step: v("next_step")});
      if (r) { toast(b.dataset.do === "close" ? "Keys yopildi" : "Bog'lanish qayd etildi"); reload(); }
    });
    if (x.can_assign) {
      const cd = await dlApi(`/api/ortda/keys/${x.id}/tyutorlar`);
      const el = bg.querySelector("#ksTu");
      el.innerHTML = `<p class="tiny muted">Yuklama chegarasi — ${cd.limit} ta ochiq keys. Tavsiya: chegaradan past guruh tyutori, keyin shu fakultetning eng kam yuklangani.</p>
        <label>Tyutor<select id="ksTs">${cd.items.map(t => `<option value="${t.id}" ${t.id === (cd.current || cd.suggest) ? "selected" : ""}>${esc(t.name)} — ${t.load}/${cd.limit}${t.group_tutor ? " · guruh tyutori" : t.same_faculty ? " · fakultet" : ""}${t.id === cd.suggest ? " · tavsiya" : ""}${t.load >= cd.limit ? " · TO'LA" : ""}</option>`).join("")}</select></label>
        <div class="dl-acts"><button type="button" class="btn primary" id="ksAs">Biriktirish</button></div><div id="ksWarn"></div>`;
      const go_ = async force => {
        const r = await fetch(`/api/ortda/keys/${x.id}/assign`, {method: "POST", credentials: "same-origin", headers: {"Content-Type": "application/json"},
                                                               body: JSON.stringify({tutor_id: +el.querySelector("#ksTs").value, force})});
        const j = await r.json().catch(() => ({}));
        if (r.status === 409 && j.detail?.overload) {
          const s = j.detail.suggest;
          el.querySelector("#ksWarn").innerHTML = `<div class="ks-warn" role="alert">${ico("alert", 15)} ${esc(j.detail.message)}
            <div class="dl-acts">${s ? `<button type="button" class="btn sm primary" data-sg="${s.id}">${esc(s.name)}ga biriktirish</button>` : ""}
            <button type="button" class="btn sm ghost" data-force>Baribir biriktirish (auditga yoziladi)</button></div></div>`;
          el.querySelector("[data-sg]")?.addEventListener("click", e => { el.querySelector("#ksTs").value = e.currentTarget.dataset.sg; go_(false); });
          el.querySelector("[data-force]").onclick = () => go_(true);
          return;
        }
        if (!r.ok) { toast(typeof j.detail === "string" ? j.detail : j.detail?.message || "Xatolik"); return; }
        toast(`Biriktirildi: ${j.owner.name} (${j.load}/${j.limit})`); reload();
      };
      el.querySelector("#ksAs").onclick = () => go_(false);
    }
  }

  /* ---------- Natija ---------- */
  async function orOutcomes(box) {
    const d = await dlApi("/api/ortda/keys/metrics"), T = d.total;
    box.innerHTML = `${d.demo ? `<div class="dl-demo">${ico("info", 15)}<span><b>Namuna keyslar.</b> Ko'rsatkichlar sun'iy keyslar va namuna LRS ma'lumoti asosida.</span></div>` : ""}
      <div class="dl-kpis or-kpis">
        ${dlKpi("Ochilgan", fmt(T.opened), `${dlD(d.since)} dan beri`)}
        ${dlKpi("Yopilgan", fmt(T.closed), `${fmt(T.auto_closed)} tasi bayroq o'zi yo'qolgani uchun tizim yopgan (alohida)`)}
        ${dlKpi("Median bog'lanish", hrs(T.median_contact_h), d.definitions.median)}
        ${dlKpi("SLA ichida", dlPct(T.sla_pct), `${fmt(T.sla_ok)} / ${fmt(T.sla_n)} · ${d.definitions.sla}`, T.sla_pct == null ? "" : T.sla_pct >= 80 ? "ok" : T.sla_pct >= 60 ? "warn" : "bad")}
        ${dlKpi("Qayta faollashdi", dlPct(T.reeng_pct), `${fmt(T.reeng_ok)} / ${fmt(T.reeng_n)} · ${fmt(T.reeng_pending)} ta kutilmoqda`)}
        ${dlKpi("SLA o'tgan (hozir)", fmt(T.overdue), "ochiq, bog'lanilmagan", T.overdue ? "bad" : "ok")}
      </div>
      <div class="card dl-card"><h3>Tyutorlar bo'yicha</h3><p class="muted">${esc(d.definitions.reeng)}. Qayta faollashish — bog'lanishning sababiy ta'siri emas
        (o'zi qaytgan talabalar ham kiradi); ta'sirni baholash uchun «Eslatmalar va tajriba» yorlig'idagi guruhlararo taqqoslashdan foydalaning.</p>
      ${dlTable([["Tyutor", x => x.id ? esc(x.name) : `<span class="dl-bad">${esc(x.name)}</span>`],
                 ["Yuklama", x => x.id ? `<b class="${x.over ? "dl-bad" : ""}">${fmt(x.load)}</b> / ${d.policy.caseload_max}` : fmt(x.load), "num"],
                 ["Ochilgan", x => fmt(x.opened), "num"], ["Yopilgan", x => fmt(x.closed), "num"],
                 ["SLA o'tgan", x => x.overdue ? `<b class="dl-bad">${fmt(x.overdue)}</b>` : "0", "num"],
                 ["Median bog'lanish", x => hrs(x.median_contact_h), "num"], ["SLA ichida", x => dlPct(x.sla_pct), "num"], ["Qayta faollashdi", x => dlPct(x.reeng_pct), "num"]],
                d.tutors, {empty: "Keyslar yo'q", rowCls: x => x.over || x.overdue ? "dl-row-bad" : ""})}
      <p class="tiny muted">Natijalar: ${Object.entries(T.outcomes).map(([k, n]) => `${esc(d.outcomes[k] || k)} — ${n}`).join(" · ") || "—"}</p></div>`;
  }

  /* ---------- Haftalik taqvim ---------- */
  async function orCalendar(box) {
    const M = OQ.meta, cs = M.courses.filter(c => c.kind === "dl" || c.kind === "ku");
    if (!KS.cal.course) KS.cal.course = cs.find(c => c.kind === "dl")?.ref || cs[0]?.ref || "";
    if (!KS.cal.course) { box.innerHTML = `<div class="dl-empty">Kuzatiladigan kurs yo'q</div>`; return; }
    const d = await dlApi("/api/ortda/taqvim?" + new URLSearchParams({course: KS.cal.course, group: KS.cal.group}));
    const ed = d.can_edit, cur = d.items.filter(x => x.release <= d.today && d.today <= x.due);
    box.innerHTML = `<div class="dl-filters"><select id="kcC" aria-label="Kurs">${cs.map(c => `<option value="${esc(c.ref)}" ${c.ref === KS.cal.course ? "selected" : ""}>${esc(c.title)} — ${esc(c.sub)}</option>`).join("")}</select>
        <select id="kcG" aria-label="Guruh"><option value="0">Kurs bo'yicha (barcha guruhlar)</option>${d.groups.map(g => `<option value="${g.id}" ${+KS.cal.group === g.id ? "selected" : ""}>${esc(g.name)} (${g.n})</option>`).join("")}</select></div>
      <div class="card dl-card"><h3>Haftalik ritm <span class="muted">· ${d.week ? d.week + "-hafta" : "semestr boshlanmagan"} · manba: ${esc({guruh: "guruh taqvimi", kurs: "kurs taqvimi", reja: "standart (semestr boshidan teng)"}[d.src])}</span></h3>
        <p class="muted">Darslar har hafta chiqariladi, muddati — o'sha hafta oxiri (yakshanba). «Ortda qolganlar» kutilgan progressni shu muddatlar bo'yicha hisoblaydi
          (muddatdan keyin ${d.grace_weeks} hafta imtiyoz). Talaba kabinetidagi «Bu hafta» bloki ham shu taqvimdan.</p>
        <form id="kcF" class="dl-pol"><label>Boshlanish sanasi<input type="date" name="start" value="${d.start}" ${ed ? "" : "disabled"}></label>
          <label>Haftalar soni<input type="number" name="weeks" min="8" max="24" value="${d.weeks}" ${ed ? "" : "disabled"}></label>
          ${ed ? `<div class="dl-acts"><button class="btn primary" type="submit">Saqlash</button>${+KS.cal.group && d.src === "guruh" ? `<button class="btn ghost" type="button" id="kcR">Guruh taqvimini o'chirish</button>` : ""}</div>` : ""}</form>
        ${cur.length ? `<p><b>Bu hafta:</b> ${cur.map(x => `${esc(x.code)} (${esc(x.due_label)})`).join(", ")}</p>` : ""}
        ${dlTable([["Hafta", x => fmt(x.week), "num"], ["Dars", x => `<b>${esc(x.code)}</b> ${esc(x.title)}`], ["Chiqariladi", x => dlD(x.release)],
                   ["Muddat", x => ed ? `<input type="date" data-due="${esc(x.ref)}" value="${x.due}" min="${x.release}" aria-label="${esc(x.code)} muddati">` : `${dlD(x.due)} <small>${esc(x.due_label)}</small>`]],
                  d.items, {empty: "Darslar yo'q", rowCls: x => x.release <= d.today && d.today <= x.due ? "ks-cur" : x.release > d.today ? "ks-fut" : ""})}</div>`;
    $("#kcC").onchange = e => { KS.cal.course = e.target.value; KS.cal.group = 0; renderOrtda("taqvim"); };
    $("#kcG").onchange = e => { KS.cal.group = +e.target.value; renderOrtda("taqvim"); };
    if (!ed) return;
    const base = Object.fromEntries(d.items.map(x => [x.ref, x.due]));
    $("#kcR")?.addEventListener("click", async () => { if (await dlApi("/api/ortda/taqvim", {course: KS.cal.course, group_id: +KS.cal.group, reset: true})) { toast("Guruh taqvimi o'chirildi"); renderOrtda("taqvim"); } });
    $("#kcF").onsubmit = async e => {
      e.preventDefault();
      const f = e.target, dues = {};
      box.querySelectorAll("[data-due]").forEach(i => { if (i.value && i.value !== base[i.dataset.due]) dues[i.dataset.due] = i.value; });
      const r = await dlApi("/api/ortda/taqvim", {course: KS.cal.course, group_id: +KS.cal.group, start: f.start.value, weeks: +f.weeks.value, dues});
      if (r) { toast("Taqvim saqlandi"); renderOrtda("taqvim"); }
    };
  }

  /* ---------- Eslatmalar va tajriba ---------- */
  async function orTriggers(box) {
    const d = await dlApi("/api/ortda/tajriba");
    const res = it => {
      const R = it.result, A = R.arms.tajriba || {}, B = R.arms.nazorat || {};
      if (it.mode === "all") return `<p class="tiny muted">Hammaga rejimi: taqqoslash guruhi yo'q — ta'sirni baholab bo'lmaydi. Hodisalar: ${fmt(R.events)}, yuborilgan: ${fmt(R.sent)}.</p>`;
      if (!R.events) return `<p class="tiny muted">${it.mode === "tajriba" ? "Tajriba boshlangan, hali hodisa yo'q." : "Hodisa yo'q."}</p>`;
      return `${dlTable([["Qo'l", r => esc(d.arms[r.k])], ["Talaba", r => fmt(r.n), "num"], ["Guruh", r => fmt(r.groups), "num"],
                         [`${d.windows.reeng} kunda qaytdi`, r => dlPct(r.rate), "num"], [`${d.windows.progress} kunda dars (o'rt.)`, r => num(r.lessons), "num"]],
                        [{k: "tajriba", ...A}, {k: "nazorat", ...B}])}
        <p>${R.diff == null ? "Farq: —" : `Farq (tajriba − nazorat): <b>${num(R.diff)} f.p.</b>${R.ci ? ` · 95% oraliq [${num(R.ci[0])}; ${num(R.ci[1])}]` : " · oraliq hisoblanmadi"}
          · darslar: ${num(R.diff_lessons)}${R.ci_lessons ? ` [${num(R.ci_lessons[0])}; ${num(R.ci_lessons[1])}]` : ""}`}</p>
        <ul class="ks-cav">${R.caveats.map(c => `<li>${esc(c)}</li>`).join("")}</ul>`;
    };
    box.innerHTML = `<div class="card dl-card"><p class="muted">${esc(d.note)} Tajriba rejimida guruhlarning tasodifiy yarmi (guruh id xeshi bo'yicha, barqaror) eslatma oladi,
      qolgani — taqqoslash guruhi; ikkala qo'ldagi mos hodisalar yoziladi.</p></div>
      ${d.items.map(it => `<div class="card dl-card ks-tr"><div class="dl-item-h"><div><h3>${esc(it.title)}</h3><p class="muted">${esc(it.desc)}</p></div>
          <label class="ks-mode">Rejim<select data-mode="${it.key}" ${d.can_edit ? "" : "disabled"}>${Object.entries(d.modes).map(([k, t]) => `<option value="${k}" ${it.mode === k ? "selected" : ""}>${esc(t)}</option>`).join("")}</select></label></div>
        <p class="tiny muted">${it.started_at ? `Boshlangan: ${dlDT(it.started_at)} · ` : ""}Guruhlar: tajriba ${it.groups.tajriba}, nazorat ${it.groups.nazorat} · oxirgi 7 kun: ${Object.entries(it.week).map(([s, n]) => `${esc(s)} ${n}`).join(", ") || "hodisa yo'q"}</p>
        ${res(it)}</div>`).join("")}
      <div class="card dl-card"><h3>Cheklovlar</h3><form id="ksL" class="dl-pol">${d.limits_meta.map(p => `<label>${esc(p.label)}<input type="number" name="${p.k}" min="${p.min}" max="${p.max}" value="${d.limits[p.k]}" ${d.can_edit ? "" : "disabled"}></label>`).join("")}
        ${d.can_edit ? `<div class="dl-acts"><button class="btn primary" type="submit">Saqlash</button><button class="btn ghost" type="button" id="ksDry">Hozir tekshirish (yubormasdan)</button><button class="btn" type="button" id="ksRun">Hozir yuborish</button></div>` : ""}</form></div>
      ${d.log.length ? `<div class="card dl-card"><h3>Jurnal</h3>${dlTable([["Vaqt", x => dlDT(x.ts)], ["Nuqta", x => esc((d.items.find(i => i.key === x.key) || {}).title || x.key)], ["Guruh", x => esc(x.grp || "—")],
          ["Qo'l", x => esc(d.arms[x.arm] || x.arm)], ["Holat", x => `${esc(x.status)}${x.delivery ? `<small>${esc(x.delivery)}</small>` : ""}`]], d.log)}</div>` : ""}`;
    box.querySelectorAll("[data-mode]").forEach(s => s.onchange = async () => {
      const r = await dlApi("/api/ortda/tajriba/mode", {key: s.dataset.mode, mode: s.value});
      if (r) { toast("Rejim saqlandi"); renderOrtda("eslatmalar"); }
    });
    const f = $("#ksL");
    if (d.can_edit) {
      f.onsubmit = async e => { e.preventDefault(); const r = await dlApi("/api/ortda/tajriba/limits", Object.fromEntries([...f.querySelectorAll("input")].map(i => [i.name, +i.value]))); if (r) toast("Cheklovlar saqlandi"); };
      const run = async dry => { const r = await dlApi("/api/ortda/tajriba/run?dry=" + dry, {}); if (r) { toast(`Mos: ${r.eligible} · yuborildi: ${r.sent} · nazorat: ${r.control} · cheklov: ${r.limited}`); if (!dry) renderOrtda("eslatmalar"); } };
      $("#ksDry").onclick = () => run(true);
      $("#ksRun").onclick = () => run(false);
    }
  }

  Object.assign(window.OR_EXT, {keyslar: orCases, natija: orOutcomes, taqvim: orCalendar, eslatmalar: orTriggers});

  /* ---------- Nazorat markazi: «Keyslar natijasi» kartasi (rektor, o'quv prorektori) ---------- */
  async function nzCard() {
    const v = document.getElementById("v-nazorat");
    if (!v || v.querySelector(".ks-nz") || typeof ME === "undefined" || !["rektor", "prorektor_oquv"].includes(ME.role_key)) return;
    let d;
    try { const r = await fetch("/api/nazorat/keyslar", {credentials: "same-origin"}); if (!r.ok) return; d = await r.json(); } catch (e) { return; }
    if (!d.enabled || v.querySelector(".ks-nz")) return;
    const T = d.total, bad = d.tutors.filter(x => x.id && (x.overdue || x.over)).slice(0, 5);
    const el = document.createElement("div");
    el.className = "card ks-nz";
    el.innerHTML = `<div class="dl-item-h"><div><h3>Ortda qolganlar: keyslar natijasi${d.demo ? ` <span class="dl-chip">namuna</span>` : ""}</h3>
        <p class="muted">Bayroqlar soni emas — ularga kim, qachon javob bergani. ${dlD(d.since)} dan beri.</p></div>
        <button type="button" class="btn sm ghost" data-ks-go>Batafsil →</button></div>
      <div class="ks-nz-k"><span><b>${fmt(T.opened)}</b>ochilgan</span><span><b>${fmt(T.closed)}</b>yopilgan</span>
        <span class="${T.sla_pct != null && T.sla_pct < 80 ? "bad" : ""}"><b>${dlPct(T.sla_pct)}</b>SLA ichida bog'lanildi</span>
        <span><b>${hrs(T.median_contact_h)}</b>median bog'lanish</span><span><b>${dlPct(T.reeng_pct)}</b>qayta faollashdi (${d.policy.reengage_days} kun)</span>
        <span class="${T.overdue ? "bad" : ""}"><b>${fmt(T.overdue)}</b>SLA o'tgan (hozir)</span></div>
      ${bad.length ? `<p class="tiny">${bad.map(x => `${esc(x.name)}: ${x.overdue ? `${x.overdue} ta SLA o'tgan` : ""}${x.over ? ` · yuklama ${x.load}/${d.policy.caseload_max}` : ""}`).join(" · ")}</p>` : ""}`;
    const areas = v.querySelector(".nz-areas");
    (areas ? areas.parentNode.insertBefore(el, areas) : v.appendChild(el));
    el.querySelector("[data-ks-go]").onclick = () => go("ortda", {tab: "natija"});
  }
  if (typeof renderNazorat === "function" && !renderNazorat._ks) {
    const prev = renderNazorat;
    renderNazorat = async function (...a) { const r = await prev.apply(this, a); nzCard(); return r; };
    renderNazorat._ks = true;
  }
})();
