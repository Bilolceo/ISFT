/* =====================================================================
   «Dars tayyorlash» — birlashgan bo'lim (app/dars.py, /api/dars): «Fanlar» yorlig'i (paket.js ichida, kirish sahifasi).
     Fanlar:   fan (kurs) ro'yxati → fan: NEXTID darslar to'ri (L/A kodlari; har darsda: material, video, paket, ko'rib chiqish, tasdiq,
               ochiq izohlar, eksport uchun ustun manba). Har darsda: «Avtomatik yig'ish (shablon)» va «Muharrirda tahrirlash»
               (paket → Kurs muharriri bloklari; kurs.js). «Fan skeleti» (L1..Ln + A1..Ak·n), «Shablonni qo'llash» (oldin farq),
               «Hammasini yig'ish / eksport» (fon ishi — jarayon ko'rsatiladi, zip ichida zip'lar), kafedra shabloni muharriri (bo'lim).
   Paket va muharrir ekranlariga yordamchilar: dsTopicBar / dsTopicBind (dars panelida muharrir bog'lanishi), dsGateFetch (to'xtatuvchi izohlar
   to'sig'i — sabab bilan aylanib o'tish), dsOpenSubject (muharrirdan fanga qaytish).
   Ruxsat va ko'lam — serverda. app.js yordamchilari: $, esc, fmt, toast, ico, ME, go; paket.js: PK, pkApi, pkModal, pkChip, pkTable, pkPreview, pkD.
   ===================================================================== */
const DS = {cid: 0, q: "", offset: 0, data: null, meta: null, kind: ""};
if (!document.querySelector('link[href="dars.css"]')) document.head.insertAdjacentHTML("beforeend", '<link rel="stylesheet" href="dars.css">');
const DS_KIND = {maruza: "Ma'ruzalar (L)", amaliy: "Amaliy mashg'ulotlar (A)", seminar: "Seminarlar (S)", laboratoriya: "Laboratoriya ishlari (Lab)", mustaqil: "Mustaqil ta'lim (MT)"};
const dsYes = (on, label, cls = "ok") => `<span class="ds-st ${on ? cls : "off"}" title="${esc(label)}: ${on ? "bor" : "yo'q"}">${on ? "✓" : "–"} ${esc(label)}</span>`;

/* muharrirdan (kurs.js) fanga qaytish */
function dsOpenSubject(cid) { DS.cid = +cid || 0; DS.data = null; go("paket", {tab: "fanlar"}); }

/* to'xtatuvchi izohlar to'sig'i: 409 {gate} → sabab so'raladi va qayta yuboriladi (audit). → javob yoki null */
async function dsGateFetch(url, body) {
  const r = await fetch(url, {method: "POST", credentials: "same-origin", headers: {"Content-Type": "application/json"}, body: JSON.stringify(body)});
  if (r.status === 401) { showLogin(); return null; }
  const d = await r.json().catch(() => ({}));
  if (r.ok) return d;
  if (r.status === 409 && d.detail && d.detail.gate) {
    return new Promise(res => {
      pkModal("Ochiq to'xtatuvchi izohlar", `<p class="pk-note" style="margin-top:0">${esc(d.detail.message)}</p>
        <label>Aylanib o'tish sababi (kamida 10 belgi — audit jurnaliga yoziladi)<textarea id="dsGr" rows="3" style="min-height:70px"></textarea></label>`,
        async m => { const v = m.querySelector("#dsGr").value.trim(); if (v.length < 10) { toast("Sababni batafsilroq yozing (kamida 10 belgi)"); return false; }
          const x = await dsGateFetch(url, {...body, override: v}); res(x); return !!x; }, "Sabab bilan davom etish", false, () => res(null));
    });
  }
  toast(pkErrMsg(d)); return null;
}

/* ---------- Fanlar ro'yxati ---------- */
async function dsSubjects(box) {
  if (DS.cid) return dsSubject(box);
  const lim = 30;
  const d = await pkApi(`/api/paket/courses?limit=${lim}&offset=${DS.offset}&q=${encodeURIComponent(DS.q)}`);
  if (d.total === 1 && !DS.q && d.items[0]) { DS.cid = d.items[0].id; return dsSubject(box); }
  box.innerHTML = `<div class="card pk-card"><div class="ds-h"><div><h3>Fanlar</h3><p class="muted">Fanni tanlang — NEXTID darslari (ma'ruza L, amaliy A) to'ri ochiladi: har dars shablon bo'yicha avtomatik yig'iladi yoki muharrirda bloklardan tahrirlanadi.</p></div>
      <input type="search" id="dsQ" placeholder="Fan, yo'nalish, o'qituvchi…" value="${esc(DS.q)}" aria-label="Fanni qidirish"></div>
    <div class="ds-subj">${d.items.map(r => `<button type="button" class="ds-sc" data-cid="${r.id}">
        <b>${esc(r.subject)}</b><small>${esc(r.direction)} · ${r.course}-kurs${r.teacher ? " · " + esc(r.teacher) : ""}</small>
        <span class="ds-sc-f">${pkBar(r.built_pct, pkTone(r.built_pct))}<small>${r.lessons} dars · tayyorlangan ${r.built} · tasdiqlangan ${r.approved}${r.waiting ? ` · <b>kutmoqda ${r.waiting}</b>` : ""}</small></span></button>`).join("")
      || `<div class="pk-empty">Fan topilmadi</div>`}</div>
    ${d.total > lim ? `<div class="pk-pager"><button type="button" class="btn sm ghost" data-p="${Math.max(0, DS.offset - lim)}" ${DS.offset ? "" : "disabled"}>← Oldingi</button>
      <span>${fmt(DS.offset + 1)}–${fmt(Math.min(d.total, DS.offset + lim))} / ${fmt(d.total)}</span>
      <button type="button" class="btn sm ghost" data-p="${DS.offset + lim}" ${DS.offset + lim < d.total ? "" : "disabled"}>Keyingi →</button></div>` : ""}</div>`;
  let t = 0;
  box.querySelector("#dsQ").oninput = e => { clearTimeout(t); t = setTimeout(() => { DS.q = e.target.value.trim(); DS.offset = 0; dsSubjects(box).then(() => { const q = box.querySelector("#dsQ"); q?.focus(); q?.setSelectionRange(q.value.length, q.value.length); }); }, 300); };
  box.querySelectorAll("[data-p]").forEach(b => b.onclick = () => { DS.offset = +b.dataset.p; dsSubjects(box); });
  box.querySelectorAll("[data-cid]").forEach(b => b.onclick = () => { DS.cid = +b.dataset.cid; dsSubject(box); });
}

/* ---------- Fan: NEXTID darslar to'ri ---------- */
async function dsSubject(box) {
  const d = await pkApi(`/api/dars/subjects/${DS.cid}`), c = d.course, can = d.can;
  DS.data = d;
  const groups = Object.keys(DS_KIND).map(k => [k, d.lessons.filter(l => l.kind === k)]).filter(g => g[1].length);
  const st = l => `${dsYes(l.material, "Material")}${dsYes(l.video, "Video")}${dsYes(l.package || l.export, l.authority === "kurs" ? "Eksport" : "Paket")}
      ${l.review ? pkChip("Ko'rib chiqishda", "info") : ""}${l.approved ? pkChip("Tasdiqlangan", "ok") : ""}
      ${l.comments.open ? pkChip(`${l.comments.open} izoh${l.comments.blocking ? ` · ${l.comments.blocking} to'xtatuvchi` : ""}`, l.comments.blocking ? "bad" : "warn") : ""}`;
  const src = l => l.kurs ? `<label class="ds-src" title="Eksport (NEXTID uchun zip) qaysi manbadan olinadi">Eksport:
      <select data-auth="${l.key}" ${can.write ? "" : "disabled"} aria-label="${esc(l.code)} — eksport manbai"><option value="kurs" ${l.authority === "kurs" ? "selected" : ""}>Muharrir</option>
      <option value="paket" ${l.authority === "paket" ? "selected" : ""}>Shablon (paket)</option></select></label>` : `<span class="ds-src muted">Eksport: shablon (paket)</span>`;
  const row = l => `<li class="ds-l ${l.approved ? "ok" : l.review ? "rv" : ""}" data-key="${l.key}">
      <span class="ds-code">${esc(l.code)}</span>
      <span class="ds-t"><b class="${l.untitled ? "muted" : ""}">${esc(l.title)}</b><span class="ds-sts">${st(l)}</span></span>
      <span class="ds-a">${src(l)}
        ${can.write ? `<button type="button" class="btn sm" data-build="${l.key}" ${PK.meta?.player === false ? "disabled" : ""} title="Yuklangan fayllardan kafedra shabloni bo'yicha paket">${ico("package", 15)} Avtomatik yig'ish (shablon)</button>` : ""}
        ${l.kurs ? `<button type="button" class="btn sm ${can.write ? "primary" : ""}" data-ku="${l.kurs.id}">${ico("layers", 15)} ${can.write ? "Muharrirda tahrirlash" : "Muharrirda ko'rish"}</button>`
          : can.write ? `<button type="button" class="btn sm primary" data-conv="${l.key}" title="Avtomatik yig'ilgan dars bloklarga o'tkaziladi — keyin erkin tahrirlanadi">${ico("layers", 15)} Muharrirda tahrirlash</button>` : ""}
        <button type="button" class="btn sm ghost" data-open="${l.key}" title="Fayllarni yuklash, ko'rish, tasdiqlash">Fayllar</button></span></li>`;
  box.innerHTML = `<div class="card pk-card ds-head"><div class="ds-h">
      <div><button type="button" class="btn sm ghost" id="dsBack">← Fanlar</button>
        <h3>${esc(c.subject)}</h3><p class="muted">${esc(c.direction)} · ${c.course}-kurs · ${esc(c.dept || "—")} · mas'ul: ${esc(c.teacher || "—")} ·
          shablon: <b>${esc(d.template.name)}</b> v${d.template.version}</p></div>
      <div class="ds-kpis">${[["Ma'ruza", d.counts.L], ["Amaliy", d.counts.A], ["Muharrirda", d.counts.linked], ["Ko'rib chiqishda", d.counts.review], ["Tasdiqlangan", d.counts.approved]]
        .map(([k, v]) => `<span><b>${v}</b>${esc(k)}</span>`).join("")}${d.counts.blocking ? `<span class="bad"><b>${d.counts.blocking}</b>to'xtatuvchi izoh</span>` : ""}</div></div>
    ${can.write ? `<div class="pk-acts ds-tools"><button type="button" class="btn sm" id="dsSkel">${ico("plus", 15)} Fan skeleti (L + A)</button>
      <button type="button" class="btn sm" id="dsApply">Shablonni qo'llash</button>
      <button type="button" class="btn sm" id="dsBulk">${ico("download", 15)} Hammasini yig'ish va eksport</button>
      ${can.template ? `<button type="button" class="btn sm ghost" id="dsTpl">Kafedra shablonini tahrirlash</button>` : ""}</div>` : ""}</div>
    ${groups.length ? groups.map(([k, ls]) => `<div class="card pk-card"><h3>${esc(DS_KIND[k])} <span class="muted">· ${ls.length} ta</span></h3><ol class="ds-grid">${ls.map(row).join("")}</ol></div>`).join("")
      : `<div class="card pk-card pk-empty">Darslar yo'q — «Fan skeleti» bilan yarating.</div>`}`;
  box.querySelector("#dsBack").onclick = () => { DS.cid = 0; dsSubjects(box); };
  box.querySelector("#dsSkel")?.addEventListener("click", () => dsSkeleton(box));
  box.querySelector("#dsApply")?.addEventListener("click", () => dsApply(box));
  box.querySelector("#dsBulk")?.addEventListener("click", () => dsBulk(box));
  box.querySelector("#dsTpl")?.addEventListener("click", () => dsTemplates(box));
  box.querySelectorAll("[data-open]").forEach(b => b.onclick = () => { PK.cid = DS.cid; PK.topic = +b.dataset.open; PK.ups = null; renderPaket("mavzular"); });
  box.querySelectorAll("[data-ku]").forEach(b => b.onclick = () => go("kurs", {cid: +b.dataset.ku}));
  box.querySelectorAll("[data-conv]").forEach(b => b.onclick = async () => {
    b.disabled = true; toast("Dars bloklarga o'tkazilmoqda…");
    const r = await pkApi(`/api/dars/subjects/${DS.cid}/lessons/${b.dataset.conv}/convert`, {});
    if (!r) { b.disabled = false; return; }
    toast(r.created ? `Muharrirga o'tkazildi: ${r.blocks} blok${r.counts?.questions ? `, ${r.counts.questions} test savoli` : ""}` : "Muharrirdagi nusxa ochildi");
    go("kurs", {cid: r.ku_course_id});
  });
  box.querySelectorAll("[data-build]").forEach(b => b.onclick = async () => {
    b.disabled = true; toast("Dars shablon bo'yicha tayyorlanmoqda…");
    const r = await pkApi(`/api/paket/courses/${DS.cid}/topics/${b.dataset.build}/build`, {});
    b.disabled = false; if (!r) return;
    toast(r.unchanged ? `O'zgarish yo'q — v${r.package.version}` : `Tayyor: v${r.package.version}`);
    await dsSubject(box);
    const l = d.lessons.find(x => x.key === +b.dataset.build); pkPreview(r.package, l ? `${l.code} — ${l.title}` : "");
  });
  box.querySelectorAll("[data-auth]").forEach(s => s.onchange = async () => {
    const r = await pkApi(`/api/dars/subjects/${DS.cid}/lessons/${s.dataset.auth}/authority`, {authority: s.value});
    if (r) { toast(s.value === "kurs" ? "Eksport — muharrirdagi nusxadan" : "Eksport — shablon bo'yicha yig'ilgan paketdan"); dsSubject(box); }
  });
}

/* ---------- Fan skeleti ---------- */
function dsSkeleton(box) {
  const c = DS.data.course;
  const bg = pkModal("Fan skeleti", `<p class="pk-note" style="margin-top:0">Mavzular ro'yxatidan (tasdiqlangan sillabus yoki kontent monitoringi) ${c.topics} ta ma'ruza (L1–L${c.topics}) va har mavzuga
      belgilangan sondagi amaliy mashg'ulot yaratiladi; har dars uchun muharrirda kafedra shabloni bo'yicha bloklar tayyorlanadi. Mavjud nomlar va darslar o'zgarmaydi.</p>
    <div class="pk-form"><label>Har mavzuga amaliy mashg'ulot<input type="number" id="dsR" min="0" max="4" value="2"></label>
      <label class="cb"><input type="checkbox" id="dsK" checked> Muharrirda shablon bloklarini yaratish</label>
      <div class="pk-acts"><button type="button" class="btn sm" id="dsPv">Ko'rish</button></div></div><div id="dsSr"></div>`,
    async m => {
      const r = await pkApi(`/api/dars/subjects/${DS.cid}/skeleton`, {ratio: +m.querySelector("#dsR").value, apply: true, with_kurs: m.querySelector("#dsK").checked});
      if (!r) return false;
      toast(`Skelet: L${r.L} + A${r.A} · muharrirda ${r.created} ta yangi dars`); dsSubject(box); return true;
    }, "Yaratish", true);
  const pv = async () => {
    const r = await pkApi(`/api/dars/subjects/${DS.cid}/skeleton`, {ratio: +bg.querySelector("#dsR").value, apply: false, with_kurs: bg.querySelector("#dsK").checked});
    if (!r) return;
    bg.querySelector("#dsSr").innerHTML = `<p class="pk-note"><b>${r.L}</b> ma'ruza + <b>${r.A}</b> amaliy · yangi darslar: ${r.new_lessons} · muharrirda yangi: ${r.new_courses}</p>` +
      pkTable([["Kod", p => `<b>${esc(p.code)}</b>`], ["Nomi", p => esc(p.title)], ["Mavzu", p => `${p.topic}`, "num"],
               ["", p => p.linked ? pkChip("bor") : p.exists ? pkChip("dars bor", "info") : pkChip("yangi", "ok")]], r.plan.slice(0, 60));
  };
  bg.querySelector("#dsPv").onclick = pv; pv();
}

/* ---------- Shablonni qo'llash: oldin farq, keyin hammasiga ---------- */
async function dsApply(box) {
  const T = await pkApi("/api/dars/templates"), dep = DS.data.course.department_id;
  const opts = T.items.filter(t => t.tkey === "global" || t.tkey === `dep:${dep}`).flatMap(t => t.versions.map(v => ({id: v.id, label: `${t.name} — v${v.version} (${pkD(v.ts)})`})));
  const bg = pkModal("Shablonni qo'llash", `<p class="pk-note" style="margin-top:0">Shablon bloklari (bo'lim sarlavhalari, video, reja, matn … tartibi) yangi shablonga moslanadi.
      <b>Muallif qo'shgan bloklar va shablon bloklaridagi mazmun saqlanadi</b>; olib tashlangan band to'ldirilgan bo'lsa — muallif blokiga aylanadi. Har dars oldin versiyaga saqlanadi.</p>
    <label>Shablon<select id="dsTs">${opts.map(o => `<option value="${o.id}" ${o.id === DS.data.template.id ? "selected" : ""}>${esc(o.label)}</option>`).join("")}</select></label>
    <div id="dsAr"><div class="pk-empty">Farq hisoblanmoqda…</div></div>`,
    async m => {
      const r = await pkApi(`/api/dars/subjects/${DS.cid}/template/apply`, {template_id: +m.querySelector("#dsTs").value, preview: false});
      if (!r) return false;
      toast(`Shablon qo'llandi: ${r.total.changed} ta dars yangilandi`); dsSubject(box); return true;
    }, "Hammasiga qo'llash", true);
  const pv = async () => {
    const r = await pkApi(`/api/dars/subjects/${DS.cid}/template/apply`, {template_id: +bg.querySelector("#dsTs").value, preview: true});
    if (!r) return;
    const t = r.total;
    bg.querySelector("#dsAr").innerHTML = `<div class="ds-kpis sm">${[["O'zgaradi", `${t.changed} / ${t.lessons}`], ["Qo'shiladi", t.added], ["Olib tashlanadi", t.removed], ["Yangilanadi", t.updated],
        ["Ko'chadi", t.moved], ["Muallif bloklari (saqlanadi)", t.author], ["Muallif blokiga aylanadi", t.detached]].map(([k, v]) => `<span><b>${v}</b>${esc(k)}</span>`).join("")}</div>` +
      (t.lessons ? pkTable([["Dars", x => `<b>${esc(x.code)}</b> ${esc(x.title)}`], ["Farq", x => x.changed ? `+${x.added} −${x.removed} ~${x.updated}${x.moved ? ` ↕${x.moved}` : ""}${x.detached ? ` · ${x.detached} muallifga` : ""}${x.quiz ? ` · test ${x.quiz === "add" ? "qo'shiladi" : "olinadi"}` : ""}` : `<span class="muted">o'zgarishsiz</span>`],
                         ["Muallif bloklari", x => `${x.author}`, "num"]], r.lessons) : `<div class="pk-empty">Muharrirda darslar yo'q — avval «Fan skeleti» yoki «Muharrirda tahrirlash».</div>`);
  };
  bg.querySelector("#dsTs").onchange = pv; pv();
}

/* ---------- Hammasini yig'ish / eksport (fon ishi, jarayon) ---------- */
function dsBulk(box) {
  const bg = pkModal("Hammasini yig'ish va eksport", `<p class="pk-note" style="margin-top:0">Har dars o'z ustun manbasidan yig'iladi: «Muharrir» — muharrirdagi bloklardan eksport, «Shablon» — yuklangan fayllardan paket.
      Natija — bitta .zip ichida har dars alohida .zip (NEXTID'ga birma-bir yuklanadi) yoki har darsni alohida yuklab olish.</p>
    <label>Turi<select id="dsBm">${Object.entries(DS.data.modes).filter(([k]) => k !== "none").map(([k, v]) => `<option value="${k}">${esc(v)}</option>`).join("")}</select></label>
    <div id="dsBp"></div>`, async m => {
      const ok = m.querySelector("[data-ok]"); ok.hidden = true;
      const r = await pkApi(`/api/dars/subjects/${DS.cid}/bulk`, {mode: m.querySelector("#dsBm").value});
      if (!r) { ok.hidden = false; return false; }
      dsJob(m.querySelector("#dsBp"), r.id, () => dsSubject(box)); return false;
    }, "Boshlash", true);
}
async function dsJob(el, id, done) {
  const j = await pkApi(`/api/dars/jobs/${id}`).catch(() => null); if (!j || !el.isConnected) return;
  el.innerHTML = `<div class="ds-prog" role="progressbar" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${j.pct}" aria-label="Jarayon"><i style="width:${j.pct}%"></i></div>
    <p class="pk-note">${j.done} / ${j.total} dars · muvaffaqiyatli ${j.ok} · xato ${j.failed}${j.current ? ` · hozir: <b>${esc(j.current)}</b>` : ""}</p>
    ${j.status === "tayyor" ? `${j.download ? `<a class="btn primary" href="${j.download}">${ico("download", 15)} Hammasini yuklab olish (.zip)</a>` : ""}
      ${pkTable([["Dars", r => `<b>${esc(r.code)}</b> ${esc(r.title || "")}<small>${r.source === "kurs" ? "muharrirdan" : "shablon (paket)"}</small>`],
                 ["Natija", r => r.ok ? pkChip(r.unchanged ? "o'zgarishsiz" : "tayyor", "ok") : `<small class="pk-bad">${esc(r.error || "xato")}</small>`],
                 ["", r => r.ok && r.download ? `<a class="btn sm ghost" href="${r.download}">${ico("download", 15)} .zip</a>` : ""]], j.results)}` : ""}`;
  if (j.status === "tayyor") { done && done(); return; }
  setTimeout(() => dsJob(el, id, done), 700);
}

/* ---------- Kafedra shabloni muharriri (bo'lim) — har saqlash yangi versiya ---------- */
async function dsTemplates(box) {
  const T = await pkApi("/api/dars/templates"), dep = DS.data.course.department_id;
  const cur = T.items.find(t => t.tkey === `dep:${dep}`) || T.items.find(t => t.tkey === "global");
  let lay = JSON.parse(JSON.stringify(cur ? cur.layout : T.default)), target = cur && cur.tkey !== "global" ? dep : 0;
  const kinds = Object.entries(T.kinds);
  const list = lt => `<ol class="ds-tl">${lay[lt].map((it, i) => `<li><select data-lt="${lt}" data-i="${i}" data-f="kind" aria-label="${i + 1}-band turi">${kinds.map(([k, v]) => `<option value="${k}" ${k === it.kind ? "selected" : ""}>${esc(v)}</option>`).join("")}</select>
      ${it.kind === "section" ? `<input data-lt="${lt}" data-i="${i}" data-f="text" value="${esc(it.text || "")}" maxlength="120" aria-label="Bo'lim sarlavhasi">` : ""}
      <button type="button" class="ku-ib sm" data-mv="-1" data-lt="${lt}" data-i="${i}" aria-label="Yuqoriga" ${i ? "" : "disabled"}>↑</button>
      <button type="button" class="ku-ib sm" data-mv="1" data-lt="${lt}" data-i="${i}" aria-label="Pastga" ${i < lay[lt].length - 1 ? "" : "disabled"}>↓</button>
      <button type="button" class="ku-ib sm danger" data-rm data-lt="${lt}" data-i="${i}" aria-label="Olib tashlash">×</button></li>`).join("")}</ol>
    <button type="button" class="btn sm ghost" data-add="${lt}">+ Band</button>`;
  const bg = pkModal("Kafedra shabloni", `<p class="pk-note" style="margin-top:0">Dars turi bo'yicha bloklar tartibi. Har saqlash — yangi versiya (oldingilari saqlanadi); fanlarga «Shablonni qo'llash» bilan o'tkaziladi.</p>
    <label>Kimga<select id="dsTd"><option value="0">Barcha kafedralar (standart)</option>${dep ? `<option value="${dep}" ${target ? "selected" : ""}>${esc(DS.data.course.dept || "Shu kafedra")}</option>` : ""}</select></label>
    <label>Nomi<input id="dsTn" maxlength="120" value="${esc(cur ? cur.name : "Kafedra shabloni")}"></label>
    <div class="ds-tg">${Object.entries(T.ltypes).map(([lt, l]) => `<div><h4>${esc(l)}</h4><div data-box="${lt}">${list(lt)}</div></div>`).join("")}</div>
    <label>O'zgarish izohi<input id="dsTc" maxlength="300" placeholder="Masalan: amaliy darsga «Davom etish» qo'shildi"></label>
    ${cur ? `<details class="pk-det pk-sub"><summary><b>Versiyalar</b><span class="muted">${cur.versions.length} ta</span></summary>${pkTable([["Versiya", v => `v${v.version}`], ["Kim", v => esc(v.by || "")], ["Qachon", v => pkD(v.ts)], ["Izoh", v => esc(v.note)]], cur.versions)}</details>` : ""}`,
    async m => {
      const r = await pkApi("/api/dars/templates", {department_id: +m.querySelector("#dsTd").value, name: m.querySelector("#dsTn").value, layout: lay, note: m.querySelector("#dsTc").value});
      if (!r) return false;
      toast(r.unchanged ? "O'zgarish yo'q" : `Saqlandi: v${r.template.version} — fanlarga «Shablonni qo'llash» bilan o'tkazing`); dsSubject(box); return true;
    }, "Yangi versiya sifatida saqlash", true);
  const redraw = lt => { bg.querySelector(`[data-box="${lt}"]`).innerHTML = list(lt); bind(); };
  const bind = () => {
    bg.querySelectorAll("[data-f]").forEach(x => x.onchange = x.oninput = () => { const it = lay[x.dataset.lt][+x.dataset.i]; it[x.dataset.f] = x.value;
      if (x.dataset.f === "kind") { it.key = ""; if (x.value === "section" && !it.text) it.text = "BO'LIM"; redraw(x.dataset.lt); } });
    bg.querySelectorAll("[data-mv]").forEach(b => b.onclick = () => { const a = lay[b.dataset.lt], i = +b.dataset.i, j = i + +b.dataset.mv; [a[i], a[j]] = [a[j], a[i]]; redraw(b.dataset.lt); });
    bg.querySelectorAll("[data-rm]").forEach(b => b.onclick = () => { lay[b.dataset.lt].splice(+b.dataset.i, 1); redraw(b.dataset.lt); });
    bg.querySelectorAll("[data-add]").forEach(b => b.onclick = () => { lay[b.dataset.add].push({kind: "section", key: "", text: "BO'LIM"}); redraw(b.dataset.add); });
  };
  bind();
}

/* ---------- dars paneli (paket.js pkTopicPanel): muharrir bilan bog'lanish ---------- */
function dsTopicBar(d, W) {
  const k = d.kurs_link;
  if (!k && !W) return "";
  return `<div class="ds-bar">${ico("layers", 15)}<span>${k ? `Muharrirda nusxasi bor (${esc(k.status === "tasdiqlangan" ? "tasdiqlangan" : k.status === "korib_chiqishda" ? "ko'rib chiqishda" : "qoralama")}) ·
      eksport uchun ustun manba — <b>${k.authority === "kurs" ? "muharrir" : "shu yerdagi shablon (paket)"}</b>${k.blocking ? ` · <b class="pk-bad">${k.blocking} ta to'xtatuvchi izoh</b>` : ""}`
      : "Darsni bloklardan erkin tahrirlash: akkordeon, kartochkalar, bilimni tekshirish — Rise kabi"}</span>
    <button type="button" class="btn sm ${k ? "" : "primary"}" id="dsTk">${k ? "Muharrirda ochish" : "Muharrirda tahrirlash"}</button></div>`;
}
function dsTopicBind(el, d) {
  el.querySelector("#dsTk")?.addEventListener("click", async e => {
    const k = d.kurs_link; if (k) return go("kurs", {cid: k.id});
    e.currentTarget.disabled = true;
    const r = await pkApi(`/api/dars/subjects/${PK.cid}/lessons/${PK.topic}/convert`, {});
    if (r) go("kurs", {cid: r.ku_course_id}); else e.currentTarget && (e.currentTarget.disabled = false);
  });
}
