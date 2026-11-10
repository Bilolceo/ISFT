"use strict";
/* ---------- Registrator ofisi: ish stoli, imtihonga ruxsatnoma, shaxsiy grafik, otrabotka skanini tekshirish ----------
   Server: app/registrar.py va app/student_ops.py. Bu fayl app.js dagi Talabalar markazi (renderOps / opsStudent / opsRetakes) ichidan chaqiriladi.
   Sirtqi bo'lim xuddi shu ekranlarni ko'radi — faqat sirtqi ta'lim talabalari (ko'lamni server belgilaydi). */
(function () {
  const REG = () => ["talabalar", "sirtqi"].includes(ME.role_key);
  const TONE = {green: ["low", "Yashil"], amber: ["mid", "Sariq"], red: ["high", "Qizil"]};

  /* otrabotka muddati: yashil → 2 kun qolganda sariq → 1 kun va kam / o'tgan — qizil */
  function cd(r) {
    if (r.status !== "berildi" || r.hours_left == null) return "";
    const h = r.hours_left, a = Math.abs(h), d = Math.floor(a / 24), hh = Math.round(a % 24);
    const t = (d ? `${d} kun ` : "") + `${hh} soat`;
    return `<span class="tag ${(TONE[r.tone] || ["gray"])[0]} rg-cd" title="Muddat: ${esc(dtm(r.due_at))}">${ico("clock", 13)} ${h < 0 ? `${t} o'tdi` : `${t} qoldi`}</span>`;
  }

  /* ===================== Ish stoli ===================== */
  async function desk() {
    const b = $("#opsBody"); b.innerHTML = `<p class="muted">Yuklanmoqda…</p>`;
    const d = await J("/api/registrar/desk");
    const S = Object.fromEntries(d.stages.map(s => [s.key, s])), P = d.policy, ver = new Set(d.verified);
    const step = (k, arrow = true) => { const s = S[k]; if (!s) return "";
      const tone = !s.n ? "good" : k === "chetlashtirish" || k.endsWith("otgan") || k === "davomat_hayfsan" ? "bad" : "warn";
      return `<button class="rg-step ${tone}" data-stage="${k}" type="button"><span class="rg-n">${fmt(s.n)}</span><b>${esc(s.title)}</b>
        <span class="tiny muted">${esc(s.who)}${s.open_tasks ? ` · ${fmt(s.open_tasks)} ta ochiq ish` : ""}</span></button>${arrow ? `<span class="rg-arr" aria-hidden="true">→</span>` : ""}`; };
    const rt = d.retakes;
    const pv = k => ver.has(k) ? `<span class="tag low">institut me'yori</span>` : `<span class="tag mid">tasdiqlanmagan</span>`;
    b.innerHTML = `<div class="src-note" style="margin-bottom:12px">${ico("info", 15)}<span><b>Registrator ish stoli</b> · ${esc(d.scope)}. Zinapoya: kontrakt muddatiga ≤${P.contract_critical_days} kun → kritik ro'yxat;
        joriy semestrda ${P.att_call_hours} soat sababsiz → call-markaz va ogohlantirish xati ${pv("att_call_hours")}; ${P.att_reprimand_hours} soatdan oshsa → hayfsan (taqdimnoma, rektor imzosi) ${pv("att_reprimand_hours")};
        hayfsan e'lon qilingan va ${P.att_expel_hours} soatga yetgan yoki kontrakt ${P.contract_expel_days} kun o'tib xat yuborilgan → «chetlashtirishga tayyor» ${pv("att_expel_hours")}. ${d.sirtqi_limits ? `Sirtqi talabalar uchun (96 soatlik sessiya, mutanosib): ${d.sirtqi_limits.call} / ${d.sirtqi_limits.reprimand} / ${d.sirtqi_limits.expel} soat <span class="tag mid">tasdiqlanmagan</span>. ` : ""}Bosqichni bosing — ro'yxat, nima deyish va asos.</span></div>
      <div class="rg-chains">
        <div class="card"><h3>${ico("money", 18)} Kontrakt</h3><div class="rg-steps">${step("kontrakt_kritik")}${step("kontrakt_otgan", false)}</div></div>
        <div class="card"><h3>${ico("clock", 18)} Davomat (sababsiz soatlar)</h3><div class="rg-steps">${step("davomat_30")}${step("davomat_hayfsan", false)}</div></div>
        <div class="card rg-final"><h3>${ico("alert", 18)} Zinapoya oxiri</h3><div class="rg-steps">${step("chetlashtirish", false)}</div></div>
      </div>
      <div class="rg-chains" style="margin-top:12px">
        <div class="card"><h3>${ico("file", 18)} Otrabotka varaqalari</h3><div class="rg-tones">
          <button class="rg-tone low" data-go="otrabotka" type="button"><b>${rt.green}</b><span>yashil</span></button>
          <button class="rg-tone mid" data-go="otrabotka" type="button"><b>${rt.amber}</b><span>sariq (≤2 kun)</span></button>
          <button class="rg-tone high" data-go="otrabotka" type="button"><b>${rt.red}</b><span>qizil (≤1 kun)</span></button>
          <button class="rg-tone high" data-go="otrabotka" type="button"><b>${rt.overdue}</b><span>muddati o'tgan</span></button>
          <button class="rg-tone gray" data-go="otrabotka" type="button"><b>${rt.review}</b><span>tekshiruvda${rt.flagged ? ` · <span class="bad">${rt.flagged} belgilangan</span>` : ""}</span></button></div>
          <p class="tiny muted" style="margin:8px 0 0">Varaqa ${P.retake_days} kunga beriladi. Muddat o'tsa — tyutor va call-markazga avtomatik topshiriq.</p></div>
        <div class="card"><h3>${ico("cap", 18)} O'zlashtirish (akademik qarz, oraliq nazorat)</h3><div class="rg-steps">${step("akademik_diqqat", false)}${step("akademik_jpa_ok", false)}${step("akademik_jpa_past", false)}</div></div>
        <div class="card"><h3>${ico("calendar", 18)} Akademik ta'til</h3><div class="rg-steps">${step("tatil_oldin")}${step("tatil_qaytish", false)}</div></div>
      </div><div id="rgList" style="margin-top:14px"></div>`;
    b.querySelectorAll("[data-stage]").forEach(x => x.onclick = () => stage(x.dataset.stage));
    b.querySelectorAll("[data-go]").forEach(x => x.onclick = () => { OPSV.tab = x.dataset.go; renderOps(); });
    hydrateIcons(b);
  }

  async function stage(key, q = "") {
    const box = $("#rgList"); if (!box) return;
    box.innerHTML = `<p class="muted">Yuklanmoqda…</p>`;
    const d = await J(`/api/registrar/stage/${encodeURIComponent(key)}?` + new URLSearchParams({q}));
    const s = d.stage;
    box.innerHTML = `<div class="card"><div class="head" style="margin-bottom:6px"><div><h3 style="margin:0">${esc(s.title)}</h3><span class="tiny muted">Mas'ul: ${esc(s.who)} · ${d.rows.length}${d.rows.length >= 300 ? "+" : ""} nafar</span></div>
        <input id="rgQ" type="text" placeholder="Ism, guruh yoki HEMIS ID" value="${esc(q)}" aria-label="Qidiruv" style="max-width:260px"></div>
      <div class="grid g2 rg-talk"><div><b class="tiny">Nima deyish kerak</b><ol class="tiny">${s.say.map(x => `<li>${esc(x)}</li>`).join("")}</ol></div>
        <div><b class="tiny">Asos</b><ul class="tiny muted">${s.basis.map(x => `<li>${esc(x)}</li>`).join("")}</ul></div></div>
      ${tbl(["Talaba", "Holat", "Fakt", "#Ochiq ish", ""], d.rows.map(r => [`<b>${esc(r.full_name)}</b><div class="tiny muted">${esc(r.grp)} · ${esc(r.faculty)}${r.study_form === "sirtqi" ? " · sirtqi" : ""}</div>`,
        `${OPS_RULES[r.rule]} ${lvlTag(r.level)}`, `<span class="tiny">${factText(r.rule, r.facts)}</span>`, r.open_tasks, `<button class="btn sm" data-st="${r.student_id}">Karta</button>`]), {top: 30})}</div>`;
    let tm; $("#rgQ").oninput = e => { clearTimeout(tm); tm = setTimeout(() => stage(key, e.target.value).then(() => { const i = $("#rgQ"); i.focus(); i.setSelectionRange(i.value.length, i.value.length); }), 350); };
    box.querySelectorAll("[data-st]").forEach(x => x.onclick = () => { OPSV.student = +x.dataset.st; opsStudent(OPSV.student); });
    box.scrollIntoView({behavior: "smooth", block: "start"});
  }

  /* ===================== Imtihonga ruxsatnoma (guruh) ===================== */
  const PV = {group: null, subject: ""};
  async function permits() {
    const b = $("#opsBody");
    b.innerHTML = `<div class="card"><h3>${ico("checkc", 18)} Imtihonga kirish ruxsatnomasi</h3>
      <p class="tiny muted" style="margin:0 0 10px">Qishki sessiya uchun. Tekshiruv faktlardan: maqom, ochiq otrabotka, yakunlangan semestrlardagi akademik qarz, joriy semestr oraliq nazorati (≥ 12 / 30 — tanlangan fan yoki barcha fanlar), joriy semestrdagi sababsiz soatlar, kontrakt jadvali yoki uzaytirilgan muddat. Ruxsatnoma faqat talablarga javob berganlarga chiqadi (QR bilan).</p>
      <div class="ops-filters"><input id="pgQ" type="text" placeholder="Guruh nomi (masalan, IQT-25)" aria-label="Guruh qidiruvi"><select id="pgSel" aria-label="Guruh"><option value="">— guruhni tanlang —</option></select>
      <select id="pgSub" aria-label="Fan"><option value="">Barcha fanlar (sessiya)</option></select></div><div id="pgOut" style="margin-top:12px"></div></div>`;
    const load = async q => { const rows = await J(`/api/docs/lookup/group?` + new URLSearchParams({q})); const sel = $("#pgSel"); if (!sel) return;
      const f = q ? rows.filter(r => r.label.toLowerCase().includes(q.toLowerCase())) : rows;
      sel.innerHTML = `<option value="">— guruhni tanlang (${f.length}) —</option>` + f.slice(0, 300).map(r => `<option value="${r.id}" ${+r.id === PV.group ? "selected" : ""}>${esc(r.label)}</option>`).join(""); };
    let tm; $("#pgQ").oninput = e => { clearTimeout(tm); tm = setTimeout(() => load(e.target.value), 250); };
    $("#pgSel").onchange = e => { PV.group = +e.target.value || null; PV.subject = ""; check(); };
    $("#pgSub").onchange = e => { PV.subject = e.target.value; check(); };
    await load("");
    if (PV.group) check();
    hydrateIcons(b);
  }
  async function check() {
    const out = $("#pgOut"); if (!PV.group) { out.innerHTML = ""; return; }
    out.innerHTML = `<p class="muted">Tekshirilmoqda…</p>`;
    const d = await J(`/api/registrar/permits?` + new URLSearchParams({group: PV.group, subject: PV.subject}));
    $("#pgSub").innerHTML = `<option value="">Barcha fanlar (sessiya)</option>` + d.subjects.map(s => `<option ${s === d.subject ? "selected" : ""}>${esc(s)}</option>`).join("");
    const no = d.rows.length - d.eligible;
    out.innerHTML = `<div class="rg-sum"><span class="chip-s">${esc(d.group.name)} · ${d.group.course}-kurs</span><span class="chip-s good">Ruxsat: <b>${d.eligible}</b></span><span class="chip-s ${no ? "bad" : ""}">Ruxsat yo'q: <b>${no}</b></span>
      ${d.eligible ? `<button class="btn primary sm" id="pgGo">${ico("file", 15)} Ruxsatnoma chiqarish — ${d.eligible} ta</button>` : ""}<span id="pgRes" class="tiny"></span></div>
      ${tbl(["Talaba", "Holat", "Sabab / izoh", ""], d.rows.map(r => [`<b>${esc(r.full_name)}</b>`,
        r.eligible ? `<span class="tag low">Ruxsat</span>` : `<span class="tag high">Ruxsat yo'q</span>`,
        `<span class="tiny">${r.eligible ? (r.checks.filter(c => c.detail && c.key === "kontrakt").map(c => esc(c.detail)).join("") || "—") : r.reasons.map(esc).join("<br>")}</span>`,
        `<button class="btn sm" data-st="${r.student_id}">Karta</button>`]))}`;
    out.querySelectorAll("[data-st]").forEach(x => x.onclick = () => { OPSV.student = +x.dataset.st; opsStudent(OPSV.student); });
    if ($("#pgGo")) $("#pgGo").onclick = () => busy($("#pgGo"), async () => {
      const r = await J("/api/docs/issue", {method: "POST", body: JSON.stringify({key: "exam_permit", params: {target: `g:${PV.group}`, subject_name: PV.subject}})});
      $("#pgRes").innerHTML = `${esc(r.regs[0])}${r.count > 1 ? ` … (${r.count} ta)` : ""} · <a href="/api/docs/file/${encodeURIComponent(r.file)}">${ico("download", 14)} .docx</a>`;
      hydrateIcons($("#pgRes")); toast(`Ruxsatnoma: ${r.count} ta`);
    }, "Tayyorlanmoqda…");
  }

  /* ===================== Talaba kartasi: Registrator amallari ===================== */
  const DISC = {loyiha: ["mid", "taqdimnoma rektorda"], amalda: ["high", "e'lon qilingan"], bekor: ["gray", "bekor qilingan"]};
  /* akademik tarix: hayfsanlar (discipline) va baholar urinishlari (asl + qayta topshirish, qaysi biri hisobda) */
  function history(root, d) {
    const host = root.querySelector(".dec-tasks"); if (!host) return;
    const disc = d.discipline || [], att = d.attempts || [];
    if (!disc.length && !att.length) return;
    const grp = {}; att.forEach(a => (grp[a.semester + "|" + a.subject] ||= []).push(a));
    host.insertAdjacentHTML("beforeend", `<div class="card rg-hist"><h3>${ico("history", 18)} Intizom va baholar tarixi</h3>
      ${disc.length ? `<div class="rg-disc">${disc.map(x => `<div class="dec-line"><span class="dl-unit">Hayfsan</span><span class="tag ${(DISC[x.status] || ["gray"])[0]}">${esc((DISC[x.status] || [x.status, x.status])[1])}</span>
        <span class="tiny muted">${esc(dtm(x.signed_at || x.created_at))}${x.doc_reg ? " · " + esc(x.doc_reg) : ""}</span><span class="dl-res tiny">${esc(x.reason || "")}${x.note ? ` <span class="muted">(${esc(x.note)})</span>` : ""}</span></div>`).join("")}</div>` : ""}
      ${att.length ? tbl(["Fan", "Semestr", "Urinishlar (hisobdagi — qalin)"], Object.values(grp).map(a => [esc(a[0].subject), esc(a[0].sem_label || ""),
        a.map(x => `<span class="${x.counted ? "rg-cnt" : "muted"}" title="${esc(x.kind)}${x.at ? " · " + esc(String(x.at).slice(0, 10)) : ""}">${x.counted ? "<b>" : ""}${x.attempt}) ${x.score ?? (x.oraliq != null ? "oraliq " + x.oraliq : "—")}${x.counted ? "</b>" : ""}</span>`).join(" → ")])) : ""}</div>`);
    hydrateIcons(host);
  }

  function cardExtras(root, d, sid) {
    history(root, d);
    if (!d.can_permit && !d.retakes?.length) return;
    const open = (d.retakes || []).filter(r => ["berildi", "topshirildi"].includes(r.status));
    const in21 = new Date(Date.now() + 21 * 864e5).toISOString().slice(0, 10);
    const html = `<div class="card rg-card"><h3>${ico("users", 18)} Registrator amallari</h3>
      ${open.length ? `<div class="rg-rt">${open.map(r => `<div class="dec-line"><span class="dl-unit">${esc(r.subject)}</span><span class="tiny muted">${esc(r.kind_label || "")} · ${esc(r.reg_no || "")}</span>
        <span>${r.status === "berildi" ? cd(r) : `<span class="tag gray">tekshiruvda</span>`}</span></div>`).join("")}</div>` : ""}
      ${d.can_permit ? `<div class="rg-acts"><button class="btn sm" id="rgPermit">${ico("checkc", 15)} Imtihonga ruxsatnoma</button>
        <span class="rg-inl"><input type="date" id="rgDl" value="${in21}" aria-label="Grafik yakuniy muddati"><button class="btn sm" id="rgSched">${ico("calendar", 15)} Shaxsiy grafik</button></span></div>
        ${d.can_defer && d.debt > 0 ? `<details class="rg-defer"><summary class="tiny">Kontrakt muddatini uzaytirish (buxgalteriya bilan kelishilgan)</summary>
          <div class="rg-inl"><input type="date" id="rgDu" aria-label="Uzaytirilgan muddat"><input type="text" id="rgDn" placeholder="Asos (masalan: ariza, buxgalteriya kelishuvi)" maxlength="300" aria-label="Asos"><button class="btn sm" id="rgDef">Saqlash</button></div></details>` : ""}
        <div id="rgOut" class="tiny" style="margin-top:8px"></div>` : ""}</div>`;
    const host = root.querySelector(".dec-tasks"); if (!host) return;
    host.insertAdjacentHTML("afterbegin", html); hydrateIcons(host);
    const out = () => $("#rgOut");
    if ($("#rgPermit")) $("#rgPermit").onclick = () => busy($("#rgPermit"), async () => {
      const r = await J(`/api/registrar/permit/${sid}`);
      out().innerHTML = `<ul class="rg-checks">${r.checks.map(c => `<li class="${c.ok ? "good" : "bad"}">${c.ok ? "✓" : "✗"} ${esc(c.label)}${c.detail ? ` <span class="muted">— ${esc(c.detail)}</span>` : ""}</li>`).join("")}</ul>` +
        (r.eligible ? `<button class="btn sm primary" id="rgPermitGo">${ico("file", 15)} Ruxsatnomani chiqarish</button>` : `<b class="bad">Ruxsatnoma berilmaydi.</b> Avval yuqoridagi sabablarni bartaraf eting yoki shaxsiy grafik tuzing.`);
      hydrateIcons(out());
      if ($("#rgPermitGo")) $("#rgPermitGo").onclick = () => busy($("#rgPermitGo"), async () => issue("exam_permit", {target: `s:${sid}`}));
    });
    if ($("#rgSched")) $("#rgSched").onclick = () => busy($("#rgSched"), async () => issue("personal_schedule", {target: `s:${sid}`, deadline: $("#rgDl").value}));
    if ($("#rgDef")) $("#rgDef").onclick = () => busy($("#rgDef"), async () => {
      const until = $("#rgDu").value, note = $("#rgDn").value.trim(); if (!until || note.length < 3) return toast("Sana va asosni kiriting");
      await J("/api/registrar/deferment", {method: "POST", body: JSON.stringify({student_id: sid, until, note})}); toast(`Kontrakt muddati ${dmy(until)}gacha uzaytirildi`); opsStudent(sid);
    });
    async function issue(key, params) {
      try {
        const r = await J("/api/docs/issue", {method: "POST", body: JSON.stringify({key, params})});
        out().insertAdjacentHTML("beforeend", `<div class="res" style="margin-top:8px"><b>${key === "exam_permit" ? "Ruxsatnoma" : "Shaxsiy grafik"}</b> · ${esc(r.regs[0])} · <a href="/api/docs/file/${encodeURIComponent(r.file)}">${ico("download", 14)} .docx</a> <span class="muted">· QR orqali kim, qachon bergani tekshiriladi</span></div>`);
        hydrateIcons(out()); toast(`Tayyor: ${r.regs[0]}`);
      } catch (e) { const m = String(e.message || ""); const j = (() => { try { return JSON.parse(m); } catch (_) { return null; } })(); if (j?.detail) { out().insertAdjacentHTML("beforeend", `<div class="bad" style="margin-top:6px">${esc(j.detail)}</div>`); } else throw e; }
    }
  }

  /* ===================== Otrabotka: demo skan, avtomatik moslashtirish, tekshiruv ===================== */
  function retakeTools(r) {
    if (r.status !== "berildi" || !["talabalar", "registrator_xodim", "tyutor", "sirtqi"].includes(ME.role_key)) return "";
    return `<span class="rg-demo"><button class="btn sm ghost" data-demo="${r.id}" data-v="signed" title="DEMO: o'qituvchi to'ldirgan va imzolagan varaqaning sun'iy skani">Demo: imzoli</button><button class="btn sm ghost" data-demo="${r.id}" data-v="unsigned" title="DEMO: ball yozilgan, imzo yo'q — tizim belgilashi kerak">Demo: imzosiz</button></span>`;
  }
  function bindRetakes(root, after) {
    root.querySelectorAll("[data-demo]").forEach(x => x.onclick = () => busy(x, async () => {
      const r = await J(`/api/registrar/retakes/${x.dataset.demo}/demo-scan`, {method: "POST", body: JSON.stringify({variant: x.dataset.v, fmt: "pdf"})});
      toast(scanToast(r.scan)); after();
    }, "…"));
    const inp = root.querySelector("#rgAuto");
    if (inp) inp.onchange = async () => {
      const file = inp.files[0]; if (!file) return; if (file.size > 10e6) return toast("Fayl 10 MB dan katta");
      const data = await new Promise((ok, no) => { const fr = new FileReader(); fr.onload = () => ok(fr.result); fr.onerror = no; fr.readAsDataURL(file); });
      try { const r = await J("/api/registrar/scan", {method: "POST", body: JSON.stringify({data_url: data})}); toast(`${r.reg_no}: ${scanToast(r.scan)}`); after(); }
      catch (e) { toast(/422|404/.test(e.message) ? "Varaqa raqami o'qilmadi — otrabotkani ro'yxatdan tanlab yuklang" : "Yuklab bo'lmadi"); }
      inp.value = "";
    };
  }
  const scanToast = m => !m ? "Skan yuklandi" : m.signed === false ? "Skan yuklandi — IMZO ANIQLANMADI, tekshiring" : m.match === false ? "Skan yuklandi — varaqa raqami mos emas" :
    m.score != null ? `Skan o'qildi: ball ${m.score}${m.signed ? ", imzo bor" : ""}` : "Skan yuklandi — ballni qo'lda kiriting";
  function scanFlags(r) {
    const m = r.scan; if (!m) return "";
    if (m.signed === false || m.match === false) return `<div class="tiny bad">${ico("alert", 13)} ${m.signed === false ? "imzo yo'q" : "raqam mos emas"}</div>`;
    return m.score != null ? `<div class="tiny muted">skandan: ${m.score} ball</div>` : "";
  }

  function review(r, after) {
    const box = $("#rtReview"), m = r.scan || {}, canApprove = REG(), kind = r.kind || "qarz", max = kind === "oraliq" ? 30 : 100;
    const yes = (v, t, f) => v === true ? `<span class="good">${ico("checkc", 14)} ${t}</span>` : v === false ? `<b class="bad">${ico("alert", 14)} ${f}</b>` : `<span class="muted">aniqlanmadi</span>`;
    const flagged = m.signed === false || m.match === false;
    box.innerHTML = `<div class="card review" style="margin-top:14px"><h3>Tekshirish: ${esc(r.full_name)} · ${esc(r.subject)} · ${esc(r.reg_no || "")}</h3>
      <p class="tiny muted" style="margin:-4px 0 8px">${esc(r.kind_label || "")}${r.sem_label ? " · " + esc(r.sem_label) : ""}${kind === "dars" ? " — tasdiqlansa qoldirilgan dars yopiladi, baho o'zgarmaydi" : " — natija avvalgi bahodan past bo'lsa, avvalgi baho saqlanadi (tarixda ikkala urinish)"}</p>
      ${flagged ? `<div class="src-note rg-flag">${ico("alert", 15)}<span><b>Diqqat:</b> ${m.signed === false ? "skanda o'qituvchi imzosi aniqlanmadi" : ""}${m.signed === false && m.match === false ? "; " : ""}${m.match === false ? `varaqa raqami ${esc(m.reg_no)} — bu otrabotkaga tegishli emas` : ""}. Varaqani qaytarish tavsiya etiladi.</span></div>` : ""}
      <div class="rv-grid"><div class="rv-scan"><img src="/api/registrar/retakes/${r.id}/preview" alt="Yuklangan varaqa skani"></div>
      <div class="rv-form"><div class="kv rg-kv">
        <span>Ro'yxat raqami</span><span>${m.reg_no ? `${esc(m.reg_no)} ${yes(m.match, "mos", "mos emas")}` : `<span class="muted">o'qilmadi</span>`}</span>
        <span>O'qituvchi imzosi</span><span>${yes(m.signed, "bor", "yo'q")}</span>
        <span>Ball (skandan)</span><span>${m.score != null ? `<b>${m.score}</b>${m.score_conf === "past" ? ` <span class="tag mid">ishonchsiz</span>` : ""}` : m.score_filled ? "yozilgan — qo'lda kiriting" : `<span class="muted">o'qilmadi</span>`}</span>
        <span>${kind === "oraliq" ? "HEMIS: oraliq (30)" : kind === "dars" ? "Qoldirilgan dars" : "HEMIS: hisobdagi ball"}</span><span>${kind === "dars" ? `${r.hours ?? "—"} soat` : `<b class="${(kind === "oraliq" ? (r.hemis_score ?? 0) < 12 : r.hemis_score < 40) ? "bad" : ""}">${r.hemis_score ?? "—"}</b> <span class="tiny muted">(varaqa berilganda: ${r.score_old ?? "—"})</span>`}</span>
        <span>O'qituvchi</span><span>${esc(r.teacher || "—")}</span><span>Yuklangan</span><span>${dtm(r.submitted_at)}</span>
        <span>O'qish usuli</span><span class="tiny">${esc(m.method || "—")}${m.ocr === false ? " · serverda OCR yo'q" : ""}</span></div>
        ${(m.warnings || []).length ? `<ul class="tiny rg-warn">${m.warnings.map(w => `<li>${esc(w)}</li>`).join("")}</ul>` : ""}
        <a class="tiny" href="/api/ops/retakes/${r.id}/file" target="_blank" rel="noopener">${ico("file", 13)} Asl faylni ochish</a>
        ${canApprove ? (kind === "dars" ? `<p class="tiny" style="margin-top:12px">O'qituvchi mashg'ulot qayta ishlanganini imzosi bilan tasdiqlagan bo'lsa — tasdiqlang.</p><input id="rvScore" type="hidden" value="">`
          : `<label class="tiny" style="display:block;margin-top:12px">Varaqadagi ${kind === "oraliq" ? "oraliq ball (0–30)" : "ball (0–100)"} — HEMIS'ga o'tadi<input id="rvScore" type="number" min="0" max="${max}" value="${m.score != null && m.score <= max ? m.score : ""}" style="width:100%;margin-top:4px"></label>`) + `
          ${flagged ? `<label class="tiny rg-force"><input type="checkbox" id="rvForce"> Imzo/raqamni asl varaqada ko'z bilan tekshirdim — izoh bilan tasdiqlayman</label>` : ""}
          <input id="rvNote" type="text" placeholder="${flagged ? "Izoh (qo'lda tasdiqlash yoki qaytarish sababi)" : "Qaytarish sababi (masalan: imzo yo'q)"}" style="width:100%;margin-top:10px" aria-label="Izoh">
          <div class="row-actions" style="margin-top:8px"><button class="btn ${flagged ? "" : "primary"}" id="rvOk">${ico("check", 16)} ${kind === "dars" ? "Tasdiqlash — dars yopiladi" : "Tasdiqlash — baho o'tadi"}</button><button class="btn ${flagged ? "primary" : ""}" id="rvBack">Qaytarish</button></div>`
        : `<p class="tiny muted">Bahoni Registrator ofisi (sirtqi talabalarniki — Sirtqi bo'lim) tasdiqlaydi.</p>`}</div></div></div>`;
    hydrateIcons(box); box.scrollIntoView({behavior: "smooth", block: "start"});
    if (!canApprove) return;
    $("#rvOk").onclick = () => busy($("#rvOk"), async () => {
      const v = $("#rvScore").value, force = !!$("#rvForce")?.checked, note = $("#rvNote").value.trim();
      if (kind !== "dars" && (v === "" || +v < 0 || +v > max)) return toast(`Ballni 0–${max} oralig'ida kiriting`);
      if (flagged && !force) return toast("Imzo aniqlanmagan: qaytaring yoki «ko'z bilan tekshirdim» belgisini qo'yib izoh yozing");
      if (force && note.length < 3) return toast("Qo'lda tasdiqlash sababini yozing");
      const res = await J(`/api/ops/retakes/${r.id}/approve`, {method: "POST", body: JSON.stringify({score: kind === "dars" ? null : +v, note, force})});
      const x = res.result || {};
      toast(kind === "dars" ? `Tasdiqlandi: ${r.subject} — qoldirilgan dars yopildi` : x.counted === false ? `Natija ${v} hisobga olinmadi — avvalgi ${x.old} yuqori (baho pasaytirilmaydi)` : `Tasdiqlandi: ${r.subject} ${x.old ?? r.score_old ?? "—"} → ${v}`); after();
    });
    $("#rvBack").onclick = () => busy($("#rvBack"), async () => {
      const n = $("#rvNote").value.trim(); if (n.length < 3) return toast("Qaytarish sababini yozing");
      await J(`/api/ops/retakes/${r.id}/return`, {method: "POST", body: JSON.stringify({note: n})}); toast("Varaqa qaytarildi — yangi muddat berildi"); after();
    });
  }

  window.RG = {cd, desk, stage, permits, cardExtras, retakeTools, bindRetakes, scanFlags, review};
})();
