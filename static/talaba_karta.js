/* =====================================================================
   Talaba kartasi (360°) — openKarta(studentId)
   Bitta oynada: Umumiy | O'qish | Harakatlar | Hujjatlar | Moliya | Amaliyot·Turar joy·Xalqaro | Murojaatlar | Tarix
   «Nima qilmoqchisiz?» — har bir amal o'z modulidagi asl oqimni ochadi (bir amal — bitta joy).
   API: GET /api/karta/{id} (app/talaba_karta.py). app.js yordamchilaridan foydalanadi: J, esc, ico, tbl, dmy, dtm, som, go, toast.
   ===================================================================== */
(function () {
  const GLOSS = {
    otrabotka: "Otrabotka — joriy semestrdagi qarzni (past oraliq ball yoki qoldirilgan dars) o'qituvchiga qayta topshirish; varaqa 3 kunga beriladi.",
    qayta: "Qayta o'qish — yakunlangan semestrda o'tmagan fanni keyingi semestrda pullik (kredit bo'yicha) qayta o'qish.",
    topshirish: "Qayta topshirish — sessiya davomida belgilangan qayta topshirish oynasi (yakuniy nazoratni qayta topshirish).",
  };
  const ACT = {
    ruxsatnoma: ["Imtihonga ruxsatnoma", "file", sid => kOps(sid)],
    otrabotka: ["Otrabotka varaqasi", "file", sid => kOps(sid), "otrabotka"],
    malumotnoma: ["Ma'lumotnoma / transkript", "folder", () => go("documents")],
    buyruq: ["Buyruq loyihasi (ta'til, qaytish, chetlash, ko'chirish)", "scroll", () => go("orders")],
    qayta_oqish: ["Qayta o'qish", "cap", () => kFlows("qayta"), "qayta"],
    apellyatsiya: ["Apellyatsiya", "cap", () => kFlows("apellyatsiya")],
  };
  function kOps(sid) { kClose(); if (typeof OPSV !== "undefined") OPSV.student = sid; go("ops"); }
  function kFlows(tab) { kClose(); if (typeof FL !== "undefined") { FL.tab = tab; FL.sess = null; } go("flows"); }
  let KS = {sid: null, tab: "umumiy", d: null};
  const gl = k => `<span class="tk-gl" tabindex="0" data-tip="${esc(GLOSS[k])}">?</span>`;
  const empty = t => `<p class="muted tk-empty">${t || "Ma'lumot yo'q"}</p>`;
  const T = (h, rows) => rows && rows.length ? tbl(h, rows) : empty();
  const tag = (t, c) => `<span class="tag ${c || "gray"}">${esc(t ?? "—")}</span>`;

  function kClose() { document.getElementById("tkOv")?.remove(); document.removeEventListener("keydown", kKey); }
  function kKey(e) { if (e.key === "Escape") kClose(); }

  window.openKarta = async function (sid) {
    KS = {sid: +sid, tab: "umumiy", d: null};
    kClose();
    const ov = document.createElement("div"); ov.id = "tkOv"; ov.className = "tk-ov";
    ov.innerHTML = `<div class="tk-pane" role="dialog" aria-modal="true" aria-label="Talaba kartasi"><div class="tk-load muted">Yuklanmoqda…</div></div>`;
    ov.onclick = e => { if (e.target === ov) kClose(); };
    document.body.appendChild(ov); document.addEventListener("keydown", kKey);
    try { KS.d = await J(`/api/karta/${KS.sid}`); } catch (e) { ov.querySelector(".tk-pane").innerHTML = `<div class="tk-load">${esc(e.message || "Xato")}</div>`; return; }
    draw();
  };

  function tabs(d) {
    if (d.limited) return [["umumiy", "Umumiy"]];
    const t = [["umumiy", "Umumiy"]];
    if (d.role !== "buxgalteriya") t.push(["oqish", "O'qish"], ["harakat", "Harakatlar"], ["hujjat", "Hujjatlar"]);
    if (d.payments) t.push(["moliya", "Moliya"]);
    if (d.role !== "buxgalteriya") t.push(["boshqa", "Amaliyot · Turar joy · Xalqaro"], ["murojaat", "Murojaatlar"]);
    t.push(["tarix", "Tarix"]);
    return t;
  }

  function draw() {
    const d = KS.d, b = d.base, s = b.student, f = b.facts || {};
    const pane = document.querySelector("#tkOv .tk-pane"); if (!pane) return;
    const open = (b.cases || []).filter(c => c.status === "ochiq");
    const chips = [];
    if (s.status && s.status !== "faol") chips.push(tag(s.status, "mid"));
    if (f.fails && f.fails.length) chips.push(tag(`${f.fails.length} ta akademik qarz`, "high"));
    if (f.unexcused >= 30) chips.push(tag(`${f.unexcused} soat sababsiz`, "high"));
    if (b.debt > 0) chips.push(tag(`kontrakt qarzi ${som(b.debt)}`, "mid"));
    if (open.length) chips.push(tag(`${open.length} ta ochiq holat`, "mid"));
    const acts = (d.actions || []).map(a => `<button type="button" data-act="${a}">${ico(ACT[a][1], 15)}<span>${esc(ACT[a][0])}</span>${ACT[a][3] ? gl(ACT[a][3]) : ""}</button>`).join("");
    const T_ = tabs(d); if (!T_.some(t => t[0] === KS.tab)) KS.tab = "umumiy";
    pane.innerHTML = `<header class="tk-head">
        <div class="tk-id"><span class="avatar">${esc((s.full_name || "?").split(/\s+/).slice(0, 2).map(w => w[0]).join(""))}</span>
          <div><h2>${esc(s.full_name)}</h2><div class="muted tiny">${[s.grp, s.course ? s.course + "-kurs" : "", s.faculty, s.hemis_id ? "HEMIS " + s.hemis_id : "", d.study_form, s.phone].filter(Boolean).map(esc).join(" · ")}</div>
          <div class="tk-chips">${chips.join("") || tag("muammo yo'q", "low")}</div></div></div>
        <div class="tk-hact">${acts ? `<div class="tk-menu"><button type="button" class="btn primary sm" id="tkAct" aria-expanded="false">Nima qilmoqchisiz? ${ico("chev", 14)}</button><div class="tk-dd" hidden>${acts}</div></div>` : ""}
          <button type="button" class="btn ghost sm" id="tkX" aria-label="Yopish">${ico("x", 16)}</button></div></header>
      <nav class="tk-tabs" role="tablist">${T_.map(([k, l]) => `<button role="tab" data-t="${k}" class="${KS.tab === k ? "on" : ""}">${esc(l)}</button>`).join("")}</nav>
      <div class="tk-body">${body(d)}</div>`;
    pane.querySelector("#tkX").onclick = kClose;
    pane.querySelectorAll("[data-t]").forEach(x => x.onclick = () => { KS.tab = x.dataset.t; draw(); });
    const ab = pane.querySelector("#tkAct");
    if (ab) { const dd = pane.querySelector(".tk-dd"); ab.onclick = e => { e.stopPropagation(); dd.hidden = !dd.hidden; ab.setAttribute("aria-expanded", String(!dd.hidden)); }; }
    pane.querySelectorAll("[data-act]").forEach(x => x.onclick = e => { if (e.target.classList.contains("tk-gl")) return; ACT[x.dataset.act][2](KS.sid); });
    pane.querySelectorAll("[data-ops]").forEach(x => x.onclick = () => kOps(KS.sid));
    if (typeof hydrateIcons === "function") hydrateIcons(pane);
  }

  function body(d) {
    const b = d.base, s = b.student, f = b.facts || {};
    if (d.limited) return `<div class="card">${empty("Call-markaz uchun faqat qo'ng'iroq topshiriqlari ko'rinadi.")}
      ${T(["Topshiriq", "Holat", "Muddat"], (b.tasks || []).map(t => [esc(t.title), tag(t.status), dtm(t.due_at)]))}</div>`;
    const r = d.rating;
    switch (KS.tab) {
      case "umumiy": {
        const open = (b.cases || []).filter(c => c.status === "ochiq");
        const tasks = (b.tasks || []).filter(t => t.status === "yangi");
        return `<div class="tk-kpis">
            <div><span>GPA (5)</span><b class="${f.gpa5 != null && f.gpa5 < 3 ? "bad" : ""}">${f.gpa5 ?? "—"}</b></div>
            <div><span>Akademik qarz</span><b class="${(f.fails || []).length ? "bad" : ""}">${(f.fails || []).length}</b></div>
            <div><span>Sababsiz / sababli</span><b>${f.unexcused ?? "—"} / ${f.excused ?? "—"} soat</b></div>
            ${b.debt !== undefined && b.debt !== null ? `<div><span>Kontrakt qarzi</span><b class="${b.debt > 0 ? "bad" : ""}">${s.payment_type === "kontrakt" ? som(b.debt) : "grant"}</b></div>` : ""}
            ${r ? `<div><span>Reyting (guruhda)</span><b>${r.r_group ?? "—"} / ${r.n_group ?? "—"}</b></div>` : ""}</div>
          <div class="tk-2">
            <div class="card"><h3>Ochiq holatlar</h3>${open.length ? open.map(c => `<div class="tk-row"><b>${esc((typeof OPS_RULES !== "undefined" ? OPS_RULES : {})[c.rule] || c.rule)}</b><span class="tiny muted">${dtm(c.opened_at)}</span></div>`).join("") : empty("Ochiq holat yo'q")}</div>
            <div class="card"><h3>Ochiq topshiriqlar</h3>${tasks.length ? tasks.map(t => `<div class="tk-row"><span>${esc(t.title)}</span><span class="tiny muted">${dtm(t.due_at)}</span></div>`).join("") + `<button class="btn sm" data-ops>Talabalar markazida ishlash →</button>` : empty("Ochiq topshiriq yo'q")}</div>
          </div>`;
      }
      case "oqish":
        return `<div class="card"><h3>Joriy semestr (oraliq nazorat)</h3>${T(["Fan", "Oraliq", "Kredit"], (d.current || []).map(g => [esc(g.subject), g.oraliq ?? "—", g.credits ?? "—"]))}</div>
          <div class="card"><h3>Akademik qarzlar</h3>${T(["Fan", "Natija"], (f.grades || []).filter(g => g.fail ?? g.score < 40).map(g => [esc(g.subject), `<b class="bad">${esc(String(g.shown ?? g.score))}</b>`]))}</div>
          <div class="card"><h3>Otrabotka ${gl("otrabotka")}</h3>${T(["Fan", "Holat", "Varaqa", "Muddat"], (b.retakes || []).map(x => [esc(x.subject), tag(x.status), esc(x.reg_no || "—"), dtm(x.due_at)]))}</div>
          <div class="card"><h3>Qayta o'qish ${gl("qayta")}</h3>${T(["Fan", "Kredit", "Qaror", "Summa", "To'langan"], (d.restudy || []).map(x => [esc(x.subject), x.credits, tag(x.decision), som(x.amount || 0), x.paid ? "ha" : "yo'q"]))}</div>
          <div class="card"><h3>Apellyatsiyalar</h3>${T(["Fan", "Holat", "Berilgan", "Ball"], (d.appeals || []).map(x => [esc(x.subject), tag(x.status), dmy(x.filed_at), `${x.score_old ?? "—"} → ${x.score_new ?? "—"}`]))}</div>
          <div class="card"><h3>Dars qoldirishlar</h3>${T(["Sana", "Soat", "Sabab"], (b.absences || []).slice(0, 40).map(a => [`${dmy(a.start)}${a.end !== a.start ? "–" + dmy(a.end) : ""}`, a.hours, esc(a.reason || "")]))}</div>
          <details class="card"><summary><b>Urinishlar tarixi (barcha semestrlar)</b></summary>${T(["Semestr", "Fan", "Urinish", "Ball"], (b.attempts || []).map(h => [esc(h.sem_label || h.semester), esc(h.subject), h.attempt, h.score ?? "—"]))}</details>`;
      case "harakat":
        return `<div class="card"><h3>Buyruqlar</h3>${T(["Buyruq", "Holat", "Raqam", "Sana"], (d.orders || []).map(o => [esc(o.title || o.kind), tag(o.status), esc(o.reg_no || "—"), dmy(o.order_date)]))}</div>
          <div class="card"><h3>Ko'chirish / tiklash</h3>${T(["Tur", "Holat", "Sabab", "Sana"], (d.transfers || []).map(x => [esc(x.kind), tag(x.status), esc(x.reason || ""), dmy(x.created_at)]))}</div>
          <div class="card"><h3>Ta'tillar</h3>${T(["Tur", "Boshlanish", "Tugash", "Buyruq"], (b.leaves || []).map(x => [esc(x.kind), dmy(x.start), dmy(x.end), esc(x.order_no || "—")]))}</div>
          <div class="card"><h3>Ma'lumot o'zgarishlari</h3>${T(["Sana", "Maydon", "Eski → yangi", "Asos"], (d.changes || []).map(x => [dtm(x.ts), esc(x.field), `${esc(x.old || "—")} → ${esc(x.new || "—")}`, esc(x.reg_no || "")]))}</div>
          <div class="card"><h3>Intizom</h3>${T(["Tur", "Sabab", "Holat"], (b.discipline || []).map(x => [esc(x.kind), esc(x.reason || ""), tag(x.status)]))}</div>`;
      case "hujjat":
        return `<div class="card"><h3>Berilgan hujjatlar</h3>${T(["Raqam", "Hujjat", "Sana", "Holat"], (d.docs || []).map(x => [esc(x.reg_no), esc(x.title || x.kind), dmy(x.created_at), tag(x.status)]))}</div>`;
      case "moliya":
        return `<div class="tk-kpis"><div><span>Kontrakt</span><b>${s.contract_amount != null ? som(s.contract_amount) : "—"}</b></div><div><span>To'langan</span><b>${s.paid_amount != null ? som(s.paid_amount) : "—"}</b></div>
            <div><span>Qarz</span><b class="${b.debt > 0 ? "bad" : ""}">${b.debt != null ? som(b.debt) : "—"}</b></div></div>
          <div class="card"><h3>To'lovlar</h3>${T(["Sana", "Summa", "Kvitansiya", "Usul", "Holat"], (d.payments || []).map(p => [dmy(p.paid_on), som(p.amount), esc(p.receipt_no || ""), esc(p.method || ""), tag(p.status)]))}</div>
          ${(d.deferments || []).length ? `<div class="card"><h3>Muddat uzaytirilgan</h3>${T(["Muddat", "Izoh"], d.deferments.map(x => [dmy(x.until), esc(x.note || "")]))}</div>` : ""}`;
      case "boshqa": {
        const dm = d.dorm || {};
        return `<div class="card"><h3>Amaliyot</h3>${T(["Davr", "Baza", "Holat", "Hisobot", "Baho"], (d.practice || []).map(x => [esc(x.period || ""), esc(x.base || "—"), tag(x.status), dmy(x.report_at), x.score ?? "—"]))}</div>
          <div class="card"><h3>Turar joy</h3>${T(["Bino", "Xona", "Holat", "Kirgan", "Chiqqan"], (dm.residents || []).map(x => [esc(x.building || ""), esc(x.room || ""), tag(x.status), dmy(x.check_in), dmy(x.check_out)]))}
            ${(dm.applications || []).length ? `<p class="tiny muted">Ariza: ${dm.applications.map(a => `${esc(a.status)} (${a.score} ball)`).join(", ")}</p>` : ""}
            ${(dm.rental || []).length ? `<p class="tiny muted">Ijarada: ${esc(dm.rental[0].district || "")} · oxirgi tashrif ${dmy(dm.rental[0].last_visit)}</p>` : ""}</div>
          <div class="card"><h3>Xalqaro almashinuv</h3>${T(["Holat", "Ball", "O'rin", "Ariza", "Kredit"], (d.intl || []).map(x => [tag(x.status), x.total ?? "—", x.rank ?? "—", dmy(x.created_at), esc(x.credit_status || "—")]))}</div>`;
      }
      case "murojaat":
        return `<div class="card"><h3>Talaba kabinetidan so'rovlar</h3>${T(["So'rov", "Holat", "Sana", "Izoh"], (d.requests || []).map(x => [esc(x.kind), tag(x.status), dtm(x.created_at), esc(x.review_note || x.doc_reg || "")]))}
            <a class="btn sm" href="/talaba/xodim" target="_blank" rel="noopener">Talaba murojaatlari sahifasi →</a></div>
          <div class="card"><h3>Holatlar (Talabalar markazi)</h3>${T(["Qoida", "Holat", "Ochilgan"], (b.cases || []).map(c => [esc((typeof OPS_RULES !== "undefined" ? OPS_RULES : {})[c.rule] || c.rule), tag(c.status), dtm(c.opened_at)]))}</div>`;
      case "tarix":
        return `<div class="card"><ol class="tl">${(b.log || []).map(l => `<li><span class="tl-t">${dtm(l.ts)}</span><b>${esc(l.action)}</b> — ${esc(l.user_short || l.user_name || "")}${l.detail ? `<div class="tiny muted">${esc(l.detail)}</div>` : ""}</li>`).join("") || `<li class="muted">—</li>`}</ol></div>`;
    }
    return "";
  }
  document.addEventListener("click", e => { const dd = document.querySelector("#tkOv .tk-dd"); if (dd && !dd.hidden && !e.target.closest(".tk-menu")) dd.hidden = true; });
})();
