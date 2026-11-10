/* =====================================================================
   Talabalar navbati — «Fokus rejimi»: bitta qo'ng'iroq, natija tugmalari, avtomatik keyingisi.
   Call-markazda standart; Registrator ofisi, tyutor, sirtqi — ixtiyoriy («Fokus rejimi» tugmasi).
   Klavishlar: 1 Gaplashildi · 2 Va'da berdi (sana) · 3 Javob bermadi · 4 Noto'g'ri raqam · → / J keyingisi · ← / K oldingisi · Esc ro'yxat.
   app.js: opsTasks() → opsFocus.want(rows) bo'lsa opsFocus(rows) chizadi. API — mavjud /api/ops/tasks/{id}/outcome.
   ===================================================================== */
(function () {
  const KEY = "isft-ops-focus";
  const OUT = [["gaplashildi", "Gaplashildi", "primary"], ["vada", "Va'da berdi", ""], ["javob_bermadi", "Javob bermadi", ""], ["notogri_raqam", "Noto'g'ri raqam", "ghost"]];
  const F = {i: 0, done: new Set(), ids: []};
  const pref = () => { try { return localStorage.getItem(KEY); } catch (e) { return null; } };
  const setPref = v => { try { localStorage.setItem(KEY, v); } catch (e) {} };
  const calls = rows => rows.filter(t => t.kind === "qongiroq" && t.can_act);

  window.opsFocus = function (rows) {
    const list = calls(rows);
    const ids = list.map(t => t.id).join(",");
    if (ids !== F.ids.join(",")) { F.ids = list.map(t => t.id); F.i = Math.min(F.i, Math.max(0, list.length - 1)); }
    draw(list);
  };
  opsFocus.on = () => { const p = pref(); return ME.role_key === "call_center" ? p !== "0" : p === "1"; };
  opsFocus.want = rows => OPSV.tab === "navbat" && !OPSV.student && opsFocus.on() && calls(rows).length > 0;
  opsFocus.toggle = v => { setPref(v ? "1" : "0"); F.i = 0; opsTasks(); };
  /* ro'yxat ko'rinishiga «Fokus rejimi» tugmasini qo'shish (opsTasks chizgandan keyin) */
  opsFocus.offer = rows => {
    if (OPSV.tab !== "navbat" || OPSV.student || !calls(rows).length || !["call_center", "talabalar", "registrator_xodim", "tyutor", "sirtqi"].includes(ME.role_key)) return;
    const b = document.getElementById("opsBody"); if (!b || b.querySelector("#ofOn")) return;
    b.insertAdjacentHTML("afterbegin", `<div class="of-offer"><button class="btn sm primary" id="ofOn">${ico("phone", 15)} Fokus rejimi — qo'ng'iroqlarni birma-bir (${calls(rows).length})</button></div>`);
    b.querySelector("#ofOn").onclick = () => opsFocus.toggle(true);
  };

  function draw(list) {
    const b = document.getElementById("opsBody"); if (!b) return;
    const left = list.filter(t => !F.done.has(t.id));
    if (!left.length) {
      b.innerHTML = `<div class="card of-done"><h3>${ico("checkc", 18)} Bugungi navbat tugadi</h3><p class="muted">Bu sessiyada ${F.done.size} ta qo'ng'iroq natijasi kiritildi.</p>
        <div class="row-actions"><button class="btn sm" id="ofList">Ro'yxat ko'rinishi</button><button class="btn sm" id="ofRe">Navbatni yangilash</button></div></div>`;
      b.querySelector("#ofList").onclick = () => opsFocus.toggle(false);
      b.querySelector("#ofRe").onclick = () => { F.done.clear(); opsTasks(); };
      return;
    }
    if (F.i >= left.length) F.i = left.length - 1;
    const t = left[F.i], sc = t.script || {};
    const minD = new Date().toISOString().slice(0, 10), maxD = new Date(Date.now() + 30 * 864e5).toISOString().slice(0, 10);
    b.innerHTML = `<div class="of-bar"><div><b>${F.i + 1}</b> / ${left.length} navbatda · bajarildi: <b>${F.done.size}</b></div>
        <div class="of-prog"><span style="width:${Math.round(100 * F.done.size / (F.done.size + left.length))}%"></span></div>
        <div class="row-actions"><button class="btn sm ghost" id="ofPrev" ${F.i ? "" : "disabled"}>← Oldingi</button><button class="btn sm ghost" id="ofNext" ${F.i < left.length - 1 ? "" : "disabled"}>O'tkazib yuborish →</button>
        <button class="btn sm" id="ofList">Ro'yxat ko'rinishi</button></div></div>
      <div class="of-grid">
        <div class="card of-left">
          <div class="ot-h"><span class="ot-kind">${esc(OPS_KIND[t.kind] || t.kind)}</span>${lvlTag(t.level)}<span class="tiny ${t.late ? "bad" : "muted"}">muddat ${dtm(t.due_at)}${t.late ? " · muddati o'tdi" : ""}</span></div>
          <h3 class="of-name"><a href="#" data-k="${t.student_id}">${esc(t.full_name)}</a></h3>
          <div class="ot-st">${esc(t.grp)}${t.course ? ` · ${t.course}-kurs` : ""} · ${esc(t.faculty)}</div>
          ${t.phone ? `<a class="of-phone" href="tel:${esc(String(t.phone).replace(/[^\d+]/g, ""))}">${ico("phone", 18)} ${esc(t.phone)}</a>` : `<p class="bad">Telefon raqami yo'q</p>`}
          <div class="tiny" style="margin:6px 0 10px"><b>${esc(t.title)}</b> — ${factText(t.rule, t.facts)}</div>
          ${sc.say ? `<div class="of-script"><b>${t.kind === "qongiroq" ? "Nima deyish kerak" : "Yo'riqnoma"}</b><ol>${sc.say.map(x => `<li>${esc(x)}</li>`).join("")}</ol>
            ${sc.tone?.length ? `<div class="tiny muted"><b>Muomala:</b> ${esc(sc.tone.join(" "))}</div>` : ""}</div>` : ""}
        </div>
        <div class="card of-right" data-tid="${t.id}">
          <h3>Qo'ng'iroq natijasi</h3>
          <input type="text" class="of-note" placeholder="Qisqa izoh (ixtiyoriy)" maxlength="1000" aria-label="Izoh">
          ${OUT.map(([k, l, cls], n) => k === "vada"
            ? `<div class="of-vada"><button class="btn ${cls}" data-o="${k}"><kbd>${n + 1}</kbd> ${l}</button><input type="date" class="of-pd" min="${minD}" max="${maxD}" aria-label="Va'da sanasi"></div>`
            : `<button class="btn ${cls}" data-o="${k}"><kbd>${n + 1}</kbd> ${l}${k === "javob_bermadi" && t.attempts ? ` (${t.attempts}/3)` : ""}</button>`).join("")}
          <p class="tiny muted">Klavishlar: 1–4 natija · → keyingisi · ← oldingisi. Natijadan keyin keyingi qo'ng'iroq avtomatik ochiladi.</p>
        </div></div>`;
    b.querySelector("#ofList").onclick = () => opsFocus.toggle(false);
    b.querySelector("#ofPrev").onclick = () => { F.i = Math.max(0, F.i - 1); draw(list); };
    b.querySelector("#ofNext").onclick = () => { F.i = Math.min(left.length - 1, F.i + 1); draw(list); };
    b.querySelector("[data-k]").onclick = e => { e.preventDefault(); window.openKarta ? openKarta(t.student_id) : (OPSV.student = t.student_id, opsStudent(t.student_id)); };
    b.querySelectorAll("[data-o]").forEach(x => x.onclick = () => submit(t, x.dataset.o, list, x));
    hydrateIcons(b);
  }

  async function submit(t, out, list, btn) {
    const box = document.querySelector(".of-right"); if (!box) return;
    const body = {outcome: out, note: box.querySelector(".of-note").value || ""};
    if (out === "vada") { body.promise_date = box.querySelector(".of-pd").value; if (!body.promise_date) { box.querySelector(".of-pd").focus(); return toast("Va'da sanasini tanlang"); } }
    box.querySelectorAll("button").forEach(x => x.disabled = true);
    try {
      const r = await J(`/api/ops/tasks/${t.id}/outcome`, {method: "POST", body: JSON.stringify(body)});
      toast(r.rescheduled ? `Javob bermadi — ertaga qayta (${r.attempts}/3)` : r.escalated ? "3 marta javob bermadi — yuzma-yuz suhbatga topshirildi" : out === "vada" ? `Va'da qayd etildi: ${dmy(body.promise_date)}` : "Natija saqlandi");
      F.done.add(t.id); draw(list);
      if (typeof refreshOpsSummary === "function") refreshOpsSummary();
    } catch (e) { box.querySelectorAll("button").forEach(x => x.disabled = false); toast(e.message || "Xato"); }
  }

  document.addEventListener("keydown", e => {
    const box = document.querySelector("#opsBody .of-right"); if (!box || document.getElementById("tkOv")) return;
    if (e.target.matches("input,textarea,select") && !(e.target.type === "date" && e.key === "Enter")) return;
    if (e.metaKey || e.ctrlKey || e.altKey) return;
    const n = {"1": 0, "2": 1, "3": 2, "4": 3}[e.key];
    if (n !== undefined) { e.preventDefault(); const k = OUT[n][0]; if (k === "vada" && !box.querySelector(".of-pd").value) { box.querySelector(".of-pd").focus(); return toast("Va'da sanasini tanlang, keyin Enter"); } box.querySelector(`[data-o="${k}"]`)?.click(); }
    else if (e.key === "ArrowRight" || e.key === "j") { e.preventDefault(); document.getElementById("ofNext")?.click(); }
    else if (e.key === "ArrowLeft" || e.key === "k") { e.preventDefault(); document.getElementById("ofPrev")?.click(); }
    else if (e.key === "Escape") { opsFocus.toggle(false); }
  });
  document.addEventListener("keydown", e => {   /* sana maydonida Enter → Va'da berdi */
    if (e.key === "Enter" && e.target.classList?.contains("of-pd") && e.target.value) { e.preventDefault(); document.querySelector('.of-right [data-o="vada"]')?.click(); }
  });
})();
