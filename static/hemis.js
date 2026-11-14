/* =====================================================================
   «HEMIS almashinuvi» (app/hemis.py, /api/hemis; docs/hemis.md) — ISFT Core ↔ HEMIS: fayl orqali import (dry-run → qo'llash),
   Farqlar navbati, eksport (.xlsx + SHA-256), ma'lumot sifati, API ulagichi skeleti (TASDIQLANMAGAN).
   Rektor — faqat jamlangan sonlar. Ruxsat serverda. Yordamchilar: app.js ($, esc, fmt, toast, locked, errCard, ico, ME, go) va
   masofaviy.js (dlApi, dlTable, dlModal, dlKpi, dlChip, dlD, dlDT, dlPager). Menyu bandi shu faylda qo'shiladi.
   ===================================================================== */
if (!document.querySelector('link[href="masofaviy.css"]')) document.head.insertAdjacentHTML("beforeend", '<link rel="stylesheet" href="masofaviy.css">');
if (!document.querySelector('link[href="hemis.css"]')) document.head.insertAdjacentHTML("beforeend", '<link rel="stylesheet" href="hemis.css">');
if (typeof ICONS === "object" && !ICONS.sync) ICONS.sync = '<path d="M21 12a9 9 0 0 1-15.5 6.2L3 16"/><path d="M3 12a9 9 0 0 1 15.5-6.2L21 8"/><path d="M21 3v5h-5M3 21v-5h5"/>';
const HM_ROLES = ["talabalar", "registrator_xodim", "masofaviy", "rektor"];
const HM_TABS = {umumiy: "Umumiy", import: "Import", farqlar: "Farqlar navbati", eksport: "Eksport", sifat: "Ma'lumot sifati", sozlama: "API va sozlamalar"};
const HM = {meta: null, who: null, tab: "umumiy", ent: "students", scope: "qisman", prev: null, pcat: "conflict",
            df: {status: "ochiq", entity: "", field: "", q: "", offset: 0}, sel: new Set()};
const hmLvl = {bad: "bad", warn: "warn", info: "info"};

(function () {
  const nav = document.getElementById("nav"), main = document.querySelector("#app main");
  if (!nav || !main) return;
  if (!nav.querySelector('a[data-v="hemis"]')) {
    const a = document.createElement("a"); a.href = "#"; a.dataset.v = "hemis"; a.dataset.i = "sync"; a.className = "hidden";
    a.innerHTML = `${ico("sync")}HEMIS almashinuvi`;
    a.onclick = e => { e.preventDefault(); go("hemis"); };
    const after = nav.querySelector('a[data-v="yuzma"]') || nav.querySelector('a[data-v="ops"]');
    after ? after.after(a) : nav.appendChild(a);
  }
  if (!document.getElementById("v-hemis")) { const s = document.createElement("section"); s.id = "v-hemis"; s.className = "view hidden"; main.appendChild(s); }
})();
function hmNav() {
  const a = document.querySelector('#nav a[data-v="hemis"]');
  if (!a || typeof ME === "undefined" || !ME) return;
  a.classList.toggle("hidden", !HM_ROLES.includes(ME.role_key));
}
(function () {
  if (typeof navApply === "function" && !navApply._hm) {
    const prev = navApply;
    navApply = function (...a) { const r = prev.apply(this, a); hmNav(); if (typeof navGroup === "function" && typeof ME !== "undefined" && ME) navGroup(ME.role_key); return r; };
    navApply._hm = true;
  }
  if (typeof go === "function" && !go._hm) {
    const prev = go;
    go = function (v, opts) {
      const r = prev(v, opts);
      if (v === "hemis") Promise.resolve().then(() => renderHemis(opts && opts.tab)).catch(e => { if (e?.message === "auth") return; $("#v-hemis").innerHTML = e?.message === "denied" ? locked("HEMIS almashinuvi") : errCard("hemis"); });
      return r;
    };
    go._hm = true; ["_nz", "_yy", "_dl"].forEach(k => { if (prev[k]) go[k] = true; });
  }
  if (typeof XT !== "undefined" && XT.openLink && !XT.openLink._hm) {
    const prev = XT.openLink;
    XT.openLink = function (l) { if (l && l.view === "hemis") HM.tab = l.tab || HM.tab; return prev.call(this, l); };
    XT.openLink._hm = true;
  }
  if (typeof showLogin === "function" && !showLogin._hm) {
    const prev = showLogin;
    showLogin = function (...a) { HM.meta = null; HM.who = null; HM.prev = null; HM.sel = new Set(); return prev.apply(this, a); };
    showLogin._hm = true;
  }
  if (typeof ME !== "undefined" && ME) hmNav();
})();

async function renderHemis(tab) {
  const v = $("#v-hemis");
  const who = typeof ME !== "undefined" ? ME : null;
  if (HM.who !== who) { HM.meta = null; HM.who = who; HM.prev = null; HM.sel = new Set(); }
  if (!HM.meta) { const m = await dlApi("/api/hemis/meta"); if (HM.who !== who) return; HM.meta = m; }
  const M = HM.meta, cp = M.caps;
  const tabs = Object.keys(HM_TABS).filter(t => cp.manage || ["umumiy", "sifat"].includes(t));
  if (tab && tabs.includes(tab)) HM.tab = tab;
  if (!tabs.includes(HM.tab)) HM.tab = tabs[0];
  v.innerHTML = `<div class="dl-head"><div><h2>HEMIS almashinuvi</h2><span class="muted">ISFT Core ↔ HEMIS · fayl orqali · ${dlD(M.today)}</span></div></div>
    <div class="dl-demo">${ico("info", 15)}<span><b>Huquqiy holat:</b> ${esc(M.legal_note)}</span></div>
    <div class="dl-tabs" role="tablist">${tabs.map(t => `<button type="button" role="tab" aria-selected="${t === HM.tab}" class="${t === HM.tab ? "on" : ""}" data-t="${t}">${esc(HM_TABS[t])}</button>`).join("")}</div>
    <div id="hmBox"><div class="dl-empty">Yuklanmoqda…</div></div>`;
  v.querySelectorAll(".dl-tabs [data-t]").forEach(b => b.onclick = () => { HM.tab = b.dataset.t; renderHemis(); });
  const box = $("#hmBox");
  const fn = {umumiy: hmOverview, import: hmImport, farqlar: hmDiffs, eksport: hmExport, sifat: hmQuality, sozlama: hmSettings}[HM.tab];
  try { await fn(box); }
  catch (e) { if (e?.message === "auth") return; box.innerHTML = e?.message === "denied" ? locked("HEMIS almashinuvi") : `<div class="dl-empty">${esc(e?.msg || "Xatolik")}</div>`; }
}
const hmEnt = k => (HM.meta.entities.find(e => e.key === k) || {}).title || k;

/* ---------- Umumiy ---------- */
async function hmOverview(box) {
  const s = await dlApi("/api/hemis/summary"), M = HM.meta;
  const qbad = s.quality.filter(q => q.n && q.level === "bad").reduce((a, q) => a + q.n, 0);
  box.innerHTML = `<div class="dl-kpis">
      ${dlKpi("Ochiq farqlar", fmt(s.diffs_open), `${fmt(s.diffs_overdue)} tasi ${s.overdue_days} kundan ortiq`, s.diffs_overdue ? "bad" : "", M.caps.manage ? "farqlar" : "")}
      ${dlKpi("HEMIS'da topilmadi", fmt(s.missing_open), "ko'rib chiqilmagan", s.missing_open ? "warn" : "", M.caps.manage ? "farqlar" : "")}
      ${dlKpi("Sifat muammolari", fmt(qbad), "jiddiy", qbad ? "bad" : "", "sifat")}
      ${dlKpi("HEMIS'ga tuzatishlar", fmt(s.export_pending), "eksport kutmoqda", "", M.caps.manage ? "eksport" : "")}
    </div>
    <div class="dl-grid">
      <div class="card dl-card"><h3>Oxirgi importlar</h3>${dlTable([["Tur", r => esc(hmEnt(r[0]))], ["Qo'llangan", r => r[1] ? dlDT(r[1]) : "—", "num"]],
          M.entities.map(e => [e.key, s.last_import[e.key]]))}</div>
      <div class="card dl-card"><h3>HEMIS API</h3><p>${s.api_enabled ? dlChip("Yoqilgan", "warn") : dlChip("O'chirilgan (standart)", "")} ${dlChip("TASDIQLANMAGAN", "bad")}</p>
        <p class="muted">${esc(M.api_label)}. Ma'lumot almashinuvi hozircha fayl orqali: HEMIS'dan eksport → «Import»; ISFT Core egalik qiladigan ma'lumot → «Eksport» → HEMIS'ga yuklash.</p></div>
    </div>`;
  box.querySelectorAll("[data-go]").forEach(b => b.onclick = () => { HM.tab = b.dataset.go; renderHemis(); });
}

/* ---------- Import ---------- */
async function hmImport(box) {
  const M = HM.meta, h = await dlApi("/api/hemis/imports");
  const profs = M.profiles.filter(p => p.entity === HM.ent);
  box.innerHTML = `<div class="card dl-card"><h3>HEMIS eksport faylini yuklash</h3>
      <p class="muted">.xlsx yoki .csv (HEMIS'dan qanday eksport qilingan bo'lsa shunday). Ustunlar o'zbek (lotin/kirill), rus tilidagi sarlavhalardan avtomatik taniladi.
        Avval <b>ko'rib chiqish</b> (bazaga hech narsa yozilmaydi), keyin «Qo'llash». Hech narsa o'chirilmaydi.</p>
      <div class="dl-filters"><select id="hmEnt" aria-label="Tur">${M.entities.map(e => `<option value="${e.key}" ${e.key === HM.ent ? "selected" : ""}>${esc(e.title)}</option>`).join("")}</select>
        <select id="hmScope" aria-label="Ko'lam"><option value="qisman" ${HM.scope === "qisman" ? "selected" : ""}>Ko'lam: fayldagi birliklar (qisman)</option>
          <option value="toliq" ${HM.scope === "toliq" ? "selected" : ""}>Ko'lam: butun institut (to'liq eksport)</option></select>
        <select id="hmProf" aria-label="Profil"><option value="">Ustunlar: avtomatik</option>${profs.map(p => `<option value="${p.id}">Profil: ${esc(p.name)}</option>`).join("")}</select>
        <label class="btn sm primary dl-file">${ico("upload", 15)} Fayl tanlash<input type="file" id="hmFile" accept=".xlsx,.csv,.txt" hidden></label></div>
    </div>
    <div id="hmPrev">${HM.prev ? "" : ""}</div>
    <div class="card dl-card"><h3>Importlar tarixi</h3>${dlTable([["Sana", r => dlDT(r.ts), "num"], ["Tur", r => esc(r.entity_t)], ["Fayl", r => esc(r.filename)],
        ["Holat", r => r.status === "applied" ? dlChip("Qo'llangan", "ok") : r.status === "preview" ? dlChip("Ko'rib chiqilmoqda", "info") : r.status === "bekor" ? dlChip("Bekor", "") : dlChip(r.status, "bad")],
        ["Natija", r => r.counts ? `+${fmt(r.counts.new)} · ~${fmt(r.counts.changed)} · ⚠${fmt(r.counts.conflicting)} · ?${fmt(r.counts.missing)}` : (r.error ? `<small class="dl-bad">${esc(r.error)}</small>` : "—")],
        ["Kim", r => esc(String(r.applied_name || r.user_name || "").split(":").pop().trim())],
        ["", r => r.status === "preview" ? `<button type="button" class="btn sm ghost" data-open="${r.id}">Ochish</button>` : ""]], h.items, {empty: "Hali import qilinmagan"})}</div>`;
  $("#hmEnt").onchange = e => { HM.ent = e.target.value; HM.prev = null; renderHemis(); };
  $("#hmScope").onchange = e => { HM.scope = e.target.value; };
  box.querySelectorAll("[data-open]").forEach(b => b.onclick = async () => { HM.prev = await dlApi(`/api/hemis/imports/${b.dataset.open}`); hmPreview(); });
  $("#hmFile").onchange = async e => {
    const f = e.target.files[0]; if (!f) return;
    $("#hmPrev").innerHTML = `<div class="dl-empty">Fayl o'qilmoqda va ISFT Core bilan solishtirilmoqda…</div>`;
    const pid = $("#hmProf").value;
    const r = await dlApi(`/api/hemis/import/${HM.ent}?name=${encodeURIComponent(f.name)}&scope=${HM.scope}${pid ? "&profile_id=" + pid : ""}`, f);
    e.target.value = "";
    if (!r) { $("#hmPrev").innerHTML = ""; return; }
    HM.prev = r; HM.pcat = "conflict"; hmPreview();
  };
  if (HM.prev && HM.prev.status === "preview") hmPreview();
}

function hmPreview() {
  const p = HM.prev, el = $("#hmPrev"); if (!el || !p) return;
  const c = p.counts;
  const cats = {conflict: ["Ziddiyatli", "bad"], new: ["Yangi", "ok"], changed: ["O'zgargan", "info"], missing: ["HEMIS'da topilmadi", "warn"]};
  const fieldOpts = sel => `<option value="">— e'tiborsiz —</option>` + p.fields.map(f => `<option value="${f.key}" ${f.key === sel ? "selected" : ""}>${esc(f.title)}${f.required ? " *" : ""}</option>`).join("");
  const samp = c ? (p.samples[HM.pcat] || []) : [];
  el.innerHTML = `<div class="card dl-card hm-preview"><h3>Ko'rib chiqish: ${esc(p.entity_t)} · ${esc(p.filename)}</h3>
      <p class="muted">Sarlavha — ${p.header_row}-qator · ko'lam: ${p.scope === "toliq" ? "butun institut" : "fayldagi birliklar"} · SHA-256 <span class="hm-code">${esc(p.sha256.slice(0, 16))}…</span>
        ${p.hours != null ? ` · jami ${fmt(p.hours)} soat` : ""}</p>
      ${p.warning ? `<div class="hm-warn">${esc(p.warning)}</div>` : ""}
      ${p.missing_fields.length ? `<div class="hm-warn hm-bad">Majburiy ustunlar topilmadi: <b>${p.missing_fields.map(f => esc(f.title)).join(", ")}</b> — quyida qo'lda moslang.</div>` : ""}
      ${p.ignored.length ? `<p class="muted">O'qilmaydigan (shaxsiy) ustunlar: ${p.ignored.map(esc).join(", ")}</p>` : ""}
      ${c ? `<div class="dl-kpis">${dlKpi("Yangi", fmt(c.new), "qo'shiladi", "ok")}${dlKpi("O'zgargan", fmt(c.changed), "bo'sh maydon to'ldiriladi", "")}
          ${dlKpi("Ziddiyatli", fmt(c.conflicting), `${fmt(c.diffs)} farq navbatga · ${fmt(c.errors)} xato qator`, c.conflicting ? "bad" : "")}
          ${dlKpi("HEMIS'da topilmadi", fmt(c.missing), "belgilanadi, o'chirilmaydi", c.missing ? "warn" : "")}
          ${dlKpi("O'zgarmagan", fmt(c.unchanged), c.spelling ? `${fmt(c.spelling)} tasida faqat yozuv farqi (kirill/lotin)` : "", "")}</div>
        ${p.diff_fields && p.diff_fields.length ? `<p class="muted">Farqlar maydonlar bo'yicha: ${p.diff_fields.map(d => `${esc(d.title)} — ${fmt(d.n)}`).join(" · ")}</p>` : ""}
        <div class="dl-seg" role="tablist">${Object.entries(cats).map(([k, [l]]) => `<button type="button" class="${k === HM.pcat ? "on" : ""}" data-pc="${k}">${esc(l)} (${fmt(k === "missing" ? c.missing : k === "conflict" ? c.conflicting : c[k])})</button>`).join("")}</div>
        ${dlTable([["Qator", r => r.row ?? "—", "num"], ["Kalit", r => `<span class="hm-code">${esc(r.ref || "")}</span>`], ["Nomi", r => esc(r.label || "")],
                   ["Tafsilot", r => esc(r.why || "")]], samp, {empty: "Bu toifada yozuv yo'q"})}
        ${samp.length >= 150 ? `<p class="muted">Faqat birinchi 150 tasi ko'rsatildi.</p>` : ""}` : ""}
      <details ${p.missing_fields.length ? "open" : ""}><summary>Ustunlar xaritasi (${Object.keys(p.map).length} / ${p.headers.filter(Boolean).length})</summary>
        <div class="hm-map">${p.headers.filter(Boolean).map(hd => `<label><span title="${esc(hd)}">${esc(hd)}</span><select data-h="${esc(hd)}">${fieldOpts(p.map[hd])}</select></label>`).join("")}</div>
        <div class="dl-filters"><input id="hmProfName" placeholder="Profil nomi (masalan: HEMIS talabalar 2026)" maxlength="60" aria-label="Profil nomi">
          <button type="button" class="btn sm ghost" id="hmRemap">Qayta solishtirish</button></div></details>
      <div class="dl-acts end"><button type="button" class="btn ghost" id="hmCancel">Bekor qilish</button>
        <button type="button" class="btn primary" id="hmApply" ${c && !p.missing_fields.length ? "" : "disabled"}>Qo'llash</button></div></div>`;
  el.querySelectorAll("[data-pc]").forEach(b => b.onclick = () => { HM.pcat = b.dataset.pc; hmPreview(); });
  $("#hmRemap").onclick = async () => {
    const mapping = {}; el.querySelectorAll("[data-h]").forEach(s => mapping[s.dataset.h] = s.value);
    const name = $("#hmProfName").value.trim();
    const r = await dlApi(`/api/hemis/imports/${p.id}/remap`, {mapping, save_profile: name || null});
    if (r) { HM.prev = r; if (name) { HM.meta = null; toast("Profil saqlandi"); renderHemis("import"); } else hmPreview(); }
  };
  $("#hmCancel").onclick = async () => { const r = await dlApi(`/api/hemis/imports/${p.id}/cancel`, {}); if (r) { HM.prev = null; renderHemis("import"); } };
  $("#hmApply").onclick = () => dlModal("Importni qo'llash", `<p>${fmt(c.new)} ta yangi yozuv qo'shiladi, ${fmt(c.changed)} tasida bo'sh maydon to'ldiriladi,
      ${fmt(c.diffs)} ta farq Farqlar navbatiga tushadi, ${fmt(c.missing)} tasi «HEMIS'da topilmadi» deb belgilanadi.</p>
      <p class="muted">Hammasi bitta tranzaksiyada: xato bo'lsa hech narsa o'zgarmaydi. Oldingi holat (snapshot) va audit yoziladi. Hech narsa o'chirilmaydi.</p>`,
    async () => {
      const r = await dlApi(`/api/hemis/imports/${p.id}/apply`, {});
      if (!r) return false;
      toast(`Qo'llandi: +${r.counts.new}, ~${r.counts.changed}, farq ${r.counts.diffs}`); HM.prev = null; renderHemis("import"); return true;
    }, "Qo'llash");
}

/* ---------- Farqlar navbati ---------- */
async function hmDiffs(box) {
  const f = HM.df, M = HM.meta;
  const qs = new URLSearchParams({status: f.status, entity: f.entity, field: f.field, q: f.q, offset: f.offset, limit: 50});
  const [d, m] = await Promise.all([dlApi(`/api/hemis/diffs?${qs}`), dlApi("/api/hemis/missing?limit=50")]);
  const open = f.status === "ochiq";
  box.innerHTML = `<div class="card dl-card"><h3>Farqlar navbati</h3>
      <p class="muted">Egasi — Registrator ofisi. Qaror: <b>HEMIS to'g'ri</b> (ISFT Core yangilanadi) · <b>ISFT Core to'g'ri</b> (HEMIS'ga tuzatish eksportiga) · <b>qo'lda</b>.
        Ism-sharif kirill/lotin farqi avtomatik bir xil hisoblanadi.</p>
      <div class="dl-filters"><div class="dl-seg">${[["ochiq", `Ochiq (${fmt(d.counts.diffs_open)})`], ["hal", `Hal qilingan (${fmt(d.counts.diffs_done)})`]].map(([k, l]) =>
          `<button type="button" class="${f.status === k ? "on" : ""}" data-st="${k}">${esc(l)}</button>`).join("")}</div>
        <select id="hmDE" aria-label="Tur"><option value="">Barcha turlar</option>${M.entities.filter(e => e.key !== "load").map(e => `<option value="${e.key}" ${f.entity === e.key ? "selected" : ""}>${esc(e.title)}</option>`).join("")}</select>
        <select id="hmDF" aria-label="Maydon"><option value="">Barcha maydonlar</option>${d.by_field.map(x => `<option value="${x.field}" ${f.field === x.field ? "selected" : ""}>${esc(x.title)} (${fmt(x.n)})</option>`).join("")}</select>
        <input type="search" id="hmDQ" placeholder="HEMIS ID, ism…" value="${esc(f.q)}" aria-label="Qidiruv"></div>
      ${open && HM.sel.size ? `<div class="dl-acts"><span>${HM.sel.size} ta tanlandi</span><button type="button" class="btn sm ghost" data-bulk="hemis">Hammasi: HEMIS to'g'ri</button>
          <button type="button" class="btn sm ghost" data-bulk="core">Hammasi: ISFT Core to'g'ri</button></div>` : ""}
      ${dlTable([...(open ? [["", r => `<input type="checkbox" data-sel="${r.id}" ${HM.sel.has(r.id) ? "checked" : ""} aria-label="Tanlash">`]] : []),
                 ["Tur", r => esc(r.entity_t)], ["Kalit", r => `<span class="hm-code">${esc(r.ref)}</span>`], ["Nomi", r => esc(r.label || "")],
                 ["Maydon", r => esc(r.field_t)], ["ISFT Core", r => esc(r.core_value || "—")], ["HEMIS", r => esc(r.hemis_value || "—")],
                 [open ? "Kun" : "Qaror", r => open ? `${r.age_days}${r.age_days >= 7 ? " " + dlChip("muddat", "bad") : ""}` : `${esc(r.decision_t)}<small>${esc(r.final_value || "")}</small>`, open ? "num" : ""],
                 ["", r => `<button type="button" class="btn sm ${open ? "primary" : "ghost"}" data-d="${r.id}">${open ? "Qaror" : "Tarix"}</button>`]],
                d.items, {empty: open ? "Ochiq farq yo'q" : "Hal qilingan farq yo'q"})}
      ${dlPager(d.total, d.offset, d.limit, o => { HM.df.offset = o; hmDiffs(box); })}</div>
    <div class="card dl-card"><h3>HEMIS'da topilmadi (${fmt(m.total)})</h3><p class="muted">ISFT Core'da bor, oxirgi HEMIS faylida yo'q. O'chirilmaydi: sababini aniqlab, izoh bilan yoping.</p>
      ${dlTable([["Tur", r => esc(r.entity_t)], ["Kalit", r => `<span class="hm-code">${esc(r.ref)}</span>`], ["Nomi", r => esc(r.label)], ["Qachondan", r => dlD(r.since), "num"],
                 ["", r => `<button type="button" class="btn sm ghost" data-mi="${r.id}">Ko'rib chiqildi</button>`]], m.items, {empty: "Yo'q"})}</div>`;
  box.querySelectorAll("[data-st]").forEach(b => b.onclick = () => { HM.df = {...f, status: b.dataset.st, offset: 0}; HM.sel = new Set(); hmDiffs(box); });
  $("#hmDE").onchange = e => { HM.df = {...f, entity: e.target.value, offset: 0}; hmDiffs(box); };
  $("#hmDF").onchange = e => { HM.df = {...f, field: e.target.value, offset: 0}; hmDiffs(box); };
  let t; $("#hmDQ").oninput = e => { clearTimeout(t); t = setTimeout(() => { HM.df = {...f, q: e.target.value, offset: 0}; hmDiffs(box).then(() => { const i = $("#hmDQ"); i.focus(); i.setSelectionRange(i.value.length, i.value.length); }); }, 350); };
  box.querySelectorAll("[data-sel]").forEach(c => c.onchange = () => { const id = +c.dataset.sel; c.checked ? HM.sel.add(id) : HM.sel.delete(id); hmDiffs(box); });
  box.querySelectorAll("[data-bulk]").forEach(b => b.onclick = () => dlModal(`${HM.sel.size} ta farq: ${M.decisions[b.dataset.bulk]}`,
    `<div class="hm-form"><label>Izoh${b.dataset.bulk === "core" ? " (majburiy)" : ""}<textarea id="hmBN" maxlength="500"></textarea></label></div>`, async bg => {
      const r = await dlApi("/api/hemis/diffs/bulk", {ids: [...HM.sel], decision: b.dataset.bulk, note: bg.querySelector("#hmBN").value});
      if (!r) return false;
      toast(`${r.ok} ta hal qilindi${r.errors.length ? `, ${r.errors.length} ta xato` : ""}`); HM.sel = new Set(); hmDiffs(box); return true;
    }, "Tasdiqlash"));
  box.querySelectorAll("[data-d]").forEach(b => b.onclick = () => hmDecide(+b.dataset.d, box));
  box.querySelectorAll("[data-mi]").forEach(b => b.onclick = () => dlModal("«HEMIS'da topilmadi» — ko'rib chiqildi",
    `<div class="hm-form"><label>Sabab (masalan: chetlashtirilgan, buyruq № …)<textarea id="hmMN" maxlength="500"></textarea></label></div>`, async bg => {
      const r = await dlApi(`/api/hemis/missing/${b.dataset.mi}/review`, {note: bg.querySelector("#hmMN").value});
      if (!r) return false; toast("Belgilandi"); hmDiffs(box); return true;
    }));
}

async function hmDecide(id, box) {
  const d = await dlApi(`/api/hemis/diffs/${id}`), M = HM.meta, open = d.status === "ochiq";
  const log = `<ul class="hm-log">${d.log.map(l => `<li>${dlDT(l.ts)} · ${esc(l.action)}${l.user_name ? " · " + esc(String(l.user_name).split(":").pop().trim()) : ""}${l.detail ? " — " + esc(l.detail) : ""}</li>`).join("")}</ul>`;
  dlModal(`${d.field_t}: ${d.label || d.ref}`, `<p class="muted">${esc(d.entity_t)} · <span class="hm-code">${esc(d.ref)}</span> · ${d.age_days} kun</p>
      <div class="hm-vals"><span>ISFT Core: <b>${esc(d.core_value || "—")}</b></span><span>HEMIS: <b>${esc(d.hemis_value || "—")}</b></span></div>
      ${open ? `<div class="hm-dec">${Object.entries({hemis: "HEMIS to'g'ri — ISFT Core yangilanadi", core: "ISFT Core to'g'ri — HEMIS'ga tuzatish (eksport)", qolda: "Qo'lda: to'g'ri qiymatni kiritaman"})
          .map(([k, l], i) => `<label><input type="radio" name="hmDec" value="${k}" ${i ? "" : "checked"}> ${esc(l)}</label>`).join("")}</div>
        <div class="hm-form"><label>To'g'ri qiymat (qo'lda)<input id="hmDV" maxlength="200" value="${esc(d.hemis_value || "")}"></label>
          <label>Izoh (ISFT Core / qo'lda — majburiy)<textarea id="hmDN" maxlength="500"></textarea></label></div>`
             : `<p>Qaror: <b>${esc(d.decision_t)}</b> — ${esc(d.final_value || "")}${d.note ? `<br><span class="muted">${esc(d.note)}</span>` : ""}</p>`}
      <h4>Jurnal</h4>${log}`,
    open ? async bg => {
      const decision = bg.querySelector('input[name="hmDec"]:checked').value;
      const r = await dlApi(`/api/hemis/diffs/${id}/resolve`, {decision, value: decision === "qolda" ? bg.querySelector("#hmDV").value : "", note: bg.querySelector("#hmDN").value});
      if (!r) return false; toast(`Hal qilindi: ${r.decision_t}`); HM.sel.delete(id); hmDiffs(box); return true;
    } : null, "Saqlash", true);
}

/* ---------- Eksport ---------- */
async function hmExport(box) {
  const M = HM.meta, h = await dlApi("/api/hemis/exports");
  box.innerHTML = `<div class="dl-grid">${M.exports.map(x => `<div class="card dl-card"><h3>${esc(x.title)}</h3>
        ${x.unverified ? `<div class="hm-warn">${esc(x.unverified)}</div>` : ""}
        <p class="muted">Ustunlar: ${x.columns.map(c => esc(c[1])).join(" · ")}</p>
        <div class="dl-filters">${x.key === "tuzatishlar" ? `<label class="hm-form chk"><input type="checkbox" data-inc="${x.key}"> avval eksport qilinganlar ham</label>`
            : `<input data-grp="${x.key}" placeholder="Guruh (ixtiyoriy)" maxlength="40" aria-label="Guruh">`}
          ${x.key === "davomat" ? `<input type="number" data-wk="${x.key}" min="1" max="26" value="${M.rules.att_rule.weeks}" aria-label="Haftalar" style="width:90px">` : ""}
          <button type="button" class="btn sm primary" data-x="${x.key}">${ico("download", 15)} .xlsx tayyorlash</button></div><div id="hmXr-${x.key}"></div></div>`).join("")}</div>
    <div class="card dl-card"><h3>Eksport jurnali</h3>${dlTable([["Sana", r => dlDT(r.ts), "num"], ["Tur", r => esc(r.kind_t)], ["Qatorlar", r => fmt(r.rows), "num"],
        ["SHA-256", r => `<span class="hm-code" title="${esc(r.sha256)}">${esc(r.sha256.slice(0, 16))}…</span>`], ["Kim", r => esc(String(r.user_name || "").split(":").pop().trim())],
        ["", r => `<a class="btn sm ghost" href="${esc(r.url)}">${ico("download", 15)} Yuklab olish</a>`]], h.items, {empty: "Hali eksport qilinmagan"})}</div>`;
  box.querySelectorAll("[data-x]").forEach(b => b.onclick = async () => {
    const k = b.dataset.x, body = {};
    const g = box.querySelector(`[data-grp="${k}"]`); if (g && g.value.trim()) body.group = g.value.trim();
    const w = box.querySelector(`[data-wk="${k}"]`); if (w) body.weeks = +w.value;
    const inc = box.querySelector(`[data-inc="${k}"]`); if (inc) body.include_exported = inc.checked;
    b.disabled = true; const r = await dlApi(`/api/hemis/export/${k}`, body); b.disabled = false;
    if (!r) return;
    toast(`Tayyor: ${r.rows} qator`); hmExport(box).then(() => { const el = $(`#hmXr-${k}`);
      if (el) el.innerHTML = `<p class="dl-note">${fmt(r.rows)} qator · SHA-256 <span class="hm-code">${esc(r.sha256)}</span> · <a href="${esc(r.url)}">yuklab olish</a></p>`; });
  });
}

/* ---------- Ma'lumot sifati ---------- */
async function hmQuality(box) {
  const q = await dlApi("/api/hemis/quality");
  box.innerHTML = `<div class="dl-grid">${q.items.map(i => `<div class="card dl-card"><div class="hm-q"><div><h3>${esc(i.title)}</h3>
        ${i.hint ? `<p class="muted">${esc(i.hint)}</p>` : ""}</div><b class="${i.n ? (i.level === "bad" ? "dl-bad" : "") : ""}">${fmt(i.n)}</b></div>
      ${i.n ? dlChip(i.level === "bad" ? "Jiddiy" : "Ogohlantirish", hmLvl[i.level]) : dlChip("Muammo yo'q", "ok")}
      ${i.sample.length ? `<ul class="hm-sample">${i.sample.map(s => `<li>${esc(s)}</li>`).join("")}</ul>` : ""}</div>`).join("")}</div>`;
}

/* ---------- API va sozlamalar ---------- */
async function hmSettings(box) {
  const s = await dlApi("/api/hemis/settings"), ed = s.can_edit, dis = ed ? "" : "disabled";
  box.innerHTML = `<div class="card dl-card"><h3>HEMIS API ulagichi ${dlChip("TASDIQLANMAGAN", "bad")}</h3>
      <div class="hm-warn hm-bad">${esc(s.label)}. Ulagich standart holatda o'chiq; «Ulanishni tekshirish» faqat bitta zararsiz GET yuboradi va javob tanasini saqlamaydi.</div>
      <div class="hm-form"><label>Bazaviy manzil (https://…)<input id="hmUrl" value="${esc(s.api_base_url)}" ${dis} maxlength="200"></label>
        <label>Tekshirish yo'li (ixtiyoriy)<input id="hmPath" value="${esc(s.api_probe_path)}" ${dis} maxlength="100"></label>
        <label>Avtorizatsiya sxemasi<select id="hmSch" ${dis}>${["Bearer", "Token", "Basic"].map(x => `<option ${x === s.api_auth_scheme ? "selected" : ""}>${x}</option>`).join("")}</select></label>
        <label class="chk"><input type="checkbox" id="hmEn" ${s.api_enabled ? "checked" : ""} ${dis}> Ulagich yoqilgan</label>
        <label class="chk"><input type="checkbox" id="hmPA" ${s.api_probe_auth ? "checked" : ""} ${dis}> Tekshirishda tokenni yuborish (faqat https)</label></div>
      <p class="muted">Token: ${s.token_set ? dlChip("o'rnatilgan", "ok") : dlChip("yo'q", "")} — faqat maxfiy omborda (${esc(s.secret_mode)}), bazada saqlanmaydi.</p>
      ${ed ? `<div class="hm-form"><label>Yangi token<input type="password" id="hmTok" autocomplete="off" maxlength="2000"></label></div>
      <div class="dl-acts"><button type="button" class="btn sm ghost" id="hmTokSet">Tokenni saqlash</button>${s.token_set ? `<button type="button" class="btn sm ghost" id="hmTokDel">Tokenni o'chirish</button>` : ""}
        <button type="button" class="btn sm primary" id="hmSave">Saqlash</button><button type="button" class="btn sm ghost" id="hmProbe">Ulanishni tekshirish</button></div>` : ""}
      <div id="hmProbeR"></div></div>
    <div class="card dl-card"><h3>Qoidalar</h3>
      <div class="hm-warn">Davomat qoidasi (masofaviy, LRS faolligidan) — TASDIQLANMAGAN, vazirlik talabi aniqlanguncha sozlanadi.</div>
      <div class="hm-form"><label>Davomat: haftada kamida daqiqa<input type="number" id="hmAm" value="${s.att_rule.min_minutes}" ${dis}></label>
        <label>yoki kamida LRS yozuvi<input type="number" id="hmAs" value="${s.att_rule.min_statements}" ${dis}></label>
        <label>Standart davr (hafta)<input type="number" id="hmAw" value="${s.att_rule.weeks}" ${dis}></label>
        <label>Oraliq ball maksimumi<input type="number" id="hmGm" value="${s.grade_rule.scale_max}" ${dis}></label>
        <label>Kamida baholangan dars<input type="number" id="hmGl" value="${s.grade_rule.min_lessons}" ${dis}></label>
        <label class="chk"><input type="checkbox" id="hmGe" ${s.grade_rule.enabled ? "checked" : ""} ${dis}> Baholar eksportiga ruxsat (siyosat)</label>
        <label>HEMIS ID formati (regex)<input id="hmRx" value="${esc(s.hemis_id_regex)}" ${dis} maxlength="80"></label></div></div>`;
  if (!ed) return;
  const save = async vals => { const r = await dlApi("/api/hemis/settings", {values: vals}); if (r) { toast("Saqlandi"); HM.meta = null; } return r; };
  $("#hmSave").onclick = async () => {
    const r = await save({api_base_url: $("#hmUrl").value, api_probe_path: $("#hmPath").value, api_auth_scheme: $("#hmSch").value, api_enabled: $("#hmEn").checked,
                          api_probe_auth: $("#hmPA").checked, hemis_id_regex: $("#hmRx").value,
                          att_rule: {min_minutes: +$("#hmAm").value, min_statements: +$("#hmAs").value, weeks: +$("#hmAw").value},
                          grade_rule: {enabled: $("#hmGe").checked, scale_max: +$("#hmGm").value, min_lessons: +$("#hmGl").value, label: s.grade_rule.label}});
    if (r) hmSettings(box);
  };
  $("#hmTokSet").onclick = async () => { const v = $("#hmTok").value.trim(); if (!v) return toast("Token kiriting"); if (await dlApi("/api/hemis/api/token", {token: v})) { toast("Token maxfiy omborga saqlandi"); hmSettings(box); } };
  const del = $("#hmTokDel"); if (del) del.onclick = async () => { if (await dlApi("/api/hemis/api/token", {token: null})) hmSettings(box); };
  $("#hmProbe").onclick = async () => {
    $("#hmProbeR").innerHTML = `<div class="dl-empty">Tekshirilmoqda…</div>`;
    const r = await dlApi("/api/hemis/api/probe", {});
    if (!r) { $("#hmProbeR").innerHTML = ""; return; }
    $("#hmProbeR").innerHTML = `<div class="hm-warn ${r.ok ? "" : "hm-bad"}"><b>${esc(r.result)}</b>${r.status ? ` · HTTP ${r.status}` : ""}${r.ms != null ? ` · ${r.ms} ms` : ""}
      ${r.sent ? "" : " · so'rov yuborilmadi"}<br>${esc(r.message)}</div>`;
  };
}
