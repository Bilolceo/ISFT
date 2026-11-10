/* =====================================================================
   «Ishlarni tekshirish» — o'qituvchi talabalardan olgan ishlarni yuklaydi, AI tekshiruv taklifi beradi (app/tekshiruv.py, /api/tekshiruv).
     1) tekshiruv: topshiriq, maksimal ball, mezonlar, namunaviy javob / test kaliti → 2) ishlarni yuklash (ko'p fayl, ZIP) →
     3) «Tekshirish» (fon jarayoni) → 4) har bir ishni ko'rib, ballni tahrirlab TASDIQLASH → 5) .xlsx / .csv / izohlar .docx.
   Kafedra mudiri — «Kafedra tekshiruvlari» (faqat ko'rish). Global: renderTekshiruv() — app.js go() chaqiradi.
   ===================================================================== */
if (!ICONS.upload) ICONS.upload = '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><path d="m17 8-5-5-5 5"/><path d="M12 3v12"/>';
const TK = {meta: null, tab: "mine", batch: null, poll: null, edit: false};
if (!document.querySelector('link[href="tekshiruv.css"]')) document.head.insertAdjacentHTML("beforeend", '<link rel="stylesheet" href="tekshiruv.css">');
const TK_ST = {yuklandi: ["Yuklandi", ""], navbatda: ["Navbatda", "info"], tekshirildi: ["AI taklifi", "info"], qolda: ["Qo'lda tekshirish", "warn"],
  tasdiqlandi: ["Tasdiqlandi", "ok"], xato: ["Xato", "bad"]};
const TK_CONF = {high: ["Ishonch: yuqori", "ok"], medium: ["Ishonch: o'rta", ""], low: ["Ishonch: past", "warn"]};

async function tkApi(url, body, raw) {
  const opt = {method: body === undefined ? "GET" : "POST", credentials: "same-origin"};
  if (raw) { opt.body = raw; opt.headers = {"Content-Type": "application/octet-stream"}; }
  else if (body !== undefined) { opt.body = JSON.stringify(body); opt.headers = {"Content-Type": "application/json"}; }
  const r = await fetch(url, opt);
  if (r.status === 401) { showLogin(); throw new Error("auth"); }
  const d = await r.json().catch(() => ({}));
  if (!r.ok) {
    const det = d.detail; const m = d.message || (typeof det === "string" ? det : det?.message) || "Xatolik yuz berdi";
    const e = new Error(r.status === 403 ? "denied" : "api"); e.msg = m; e.status = r.status; throw e;
  }
  return d;
}
const tkChip = (t, cls = "") => `<span class="tk-chip ${cls}">${esc(t)}</span>`;
const tkNum = v => v === null || v === undefined ? "—" : String(+(+v).toFixed(1));

async function renderTekshiruv() {
  const el = $("#v-tekshiruv");
  if (!el.innerHTML) el.innerHTML = `<p class="muted">Yuklanmoqda…</p>`;
  try { TK.meta = await tkApi("/api/tekshiruv/meta"); }
  catch (e) { el.innerHTML = e.message === "denied" ? `<div class="card tk-empty">${esc(e.msg)}</div>` : errCard("tekshiruv"); return; }
  if (TK.batch) return tkOpen(TK.batch.id);
  tkShell();
}

function tkHead() {
  const M = TK.meta;
  return `<div class="tk-head"><div><h2>Ishlarni tekshirish</h2>
      <span class="muted">Talabalardan olgan ishlarni (PDF, Word, PowerPoint, rasm, ZIP) yuklang — AI har bir ish bo'yicha mezonlar asosida ball va izoh taklif qiladi. Yakuniy bahoni siz tasdiqlaysiz.</span></div>
    <div class="tk-head-r">${tkChip(M.label, M.engine === "claude" ? "ok" : (M.engine === "fake" ? "warn" : "bad"))}${tkChip(`Bugun: ${M.used} / ${M.limit}`, M.used >= M.limit ? "bad" : "")}</div></div>`;
}

function tkShell() {
  tkStopPoll();
  const el = $("#v-tekshiruv"), M = TK.meta;
  const tabs = [["mine", "Mening tekshiruvlarim"], ["new", "Yangi tekshiruv"]].concat(M.mode === "dept" ? [["dept", "Kafedra tekshiruvlari"]] : []);
  el.innerHTML = tkHead() + `<div class="tk-tabs" role="tablist">${tabs.map(([k, l]) => `<button type="button" role="tab" data-t="${k}" class="${TK.tab === k ? "on" : ""}" aria-selected="${TK.tab === k}">${esc(l)}</button>`).join("")}</div><div id="tkBody"></div>`;
  el.querySelectorAll(".tk-tabs button").forEach(b => b.onclick = () => { TK.tab = b.dataset.t; tkShell(); });
  if (TK.tab === "new") tkForm(null); else tkList(TK.tab);
}

async function tkList(scope) {
  const box = $("#tkBody");
  box.innerHTML = `<p class="muted">Yuklanmoqda…</p>`;
  let d;
  try { d = await tkApi(`/api/tekshiruv/batches?scope=${scope}`); } catch (e) { box.innerHTML = `<div class="card tk-empty">${esc(e.msg || "Yuklab bo'lmadi")}</div>`; return; }
  if (!d.items.length) {
    box.innerHTML = `<div class="card tk-empty">${scope === "dept" ? "Kafedra o'qituvchilari hali tekshiruv o'tkazmagan." : `Hali tekshiruv yo'q. <button type="button" class="btn primary sm" id="tkFirst">Yangi tekshiruv</button>`}</div>`;
    $("#tkFirst")?.addEventListener("click", () => { TK.tab = "new"; tkShell(); });
    return;
  }
  box.innerHTML = `<div class="card tk-card"><div class="tw"><table class="tk-t stack"><thead><tr>${scope === "dept" ? "<th>O'qituvchi</th>" : ""}<th>Tekshiruv</th><th>Guruh</th><th>Ishlar</th><th>Tasdiqlangan</th><th>Qo'lda</th><th>O'rtacha</th><th>Sana</th></tr></thead><tbody>
    ${d.items.map((r, i) => `<tr class="tk-click" data-i="${i}" tabindex="0">${scope === "dept" ? `<td data-l="O'qituvchi">${esc(r.author)}</td>` : ""}
      <td data-l="Tekshiruv"><b>${esc(r.title)}</b><div class="muted tiny">${esc(r.kind)}${r.subject ? " · " + esc(r.subject) : ""}${r.status === "tekshirilmoqda" ? " · tekshirilmoqda…" : ""}</div></td>
      <td data-l="Guruh">${esc(r.group || "—")}</td><td data-l="Ishlar">${r.works}</td>
      <td data-l="Tasdiqlangan">${r.confirmed} / ${r.works}</td><td data-l="Qo'lda">${r.manual ? tkChip(r.manual, "warn") : "—"}</td>
      <td data-l="O'rtacha">${r.avg === null ? "—" : `${tkNum(r.avg)} / ${tkNum(r.max_score)}`}</td><td data-l="Sana">${dmy(r.updated_at)}</td></tr>`).join("")}</tbody></table></div></div>`;
  box.querySelectorAll("tr[data-i]").forEach(tr => {
    const open = () => tkOpen(d.items[+tr.dataset.i].id);
    tr.onclick = open; tr.onkeydown = e => { if (e.key === "Enter") open(); };
  });
}

/* ---------- tekshiruv sozlamalari (yangi yoki tahrir) ---------- */
function tkForm(B) {
  const M = TK.meta, box = B ? tkModal("Tekshiruv sozlamalari") : $("#tkBody");
  if (B) box.classList.add("tk-modal-wide");
  const kind = B ? B.kind : "mustaqil";
  let rubric = B ? B.rubric.map(x => ({...x})) : M.rubrics[kind].map(x => ({...x}));
  box.innerHTML = `<div class="card tk-card">
    ${M.engine !== "claude" ? `<div class="tk-note">${ico("info", 16)}<span>${M.engine === "fake" ? "Sinov rejimi: soxta AI." : "AI ulanmagan — test kaliti bo'yicha yozma javoblar baribir avtomatik baholanadi, boshqa ishlar qo'lda tekshiruvga tushadi."}</span></div>` : ""}
    <div class="tk-grid">
      <label class="wide">Tekshiruv nomi<input id="tkTitle" maxlength="200" value="${esc(B?.title || "")}" placeholder="masalan, 1-mustaqil ish: Buxgalteriya balansi"></label>
      <label>Turi<select id="tkKind">${Object.entries(M.kinds).map(([k, v]) => `<option value="${k}" ${k === kind ? "selected" : ""}>${esc(v)}</option>`).join("")}</select></label>
      <label>Maksimal ball<input id="tkMax" type="number" min="1" max="1000" step="0.5" value="${B ? tkNum(B.max_score) : 5}"></label>
      <label>Fan<input id="tkSubj" list="tkSubjs" maxlength="160" value="${esc(B?.subject || "")}"><datalist id="tkSubjs">${(M.subjects || []).map(s => `<option value="${esc(s)}">`).join("")}</datalist></label>
      <label>Guruh <small>(talabani fayl nomidan aniqlash uchun)</small><select id="tkGroup"><option value="">— tanlanmagan —</option>${(M.groups || []).map(g => `<option value="${g.id}" ${B?.group_id === g.id ? "selected" : ""}>${esc(g.name)}</option>`).join("")}</select></label>
      <label class="wide">Topshiriq matni<textarea id="tkTask" rows="4" maxlength="30000" placeholder="Talabaga berilgan topshiriq: mavzu, talablar, hajm…">${esc(B?.task_text || "")}</textarea></label>
      ${B ? `<div class="wide tk-taskfile"><label class="btn sm">${ico("upload", 14)} Topshiriq faylini qo'shish<input type="file" id="tkTaskFile" hidden accept=".pdf,.docx,.pptx,.txt,.xlsx"></label>${B.task_file ? `<span class="muted tiny">Qo'shilgan: ${esc(B.task_file)}</span>` : ""}</div>` : ""}
      <div class="wide"><span class="tk-lbl">Baholash mezonlari <small class="muted">(ball — mezon og'irligi; jami maksimal ballga moslab hisoblanadi)</small></span><div id="tkRub"></div>
        <button type="button" class="btn sm ghost" id="tkRubAdd">+ Mezon</button> <button type="button" class="btn sm ghost" id="tkRubTpl">Andozani tiklash</button></div>
      <label class="wide" id="tkRefL">Namunaviy javob / yechim <small>(ixtiyoriy)</small><textarea id="tkRef" rows="3" maxlength="30000">${esc(B?.ref_answer || "")}</textarea></label>
      <label class="wide" id="tkKeyL">Test kaliti <small>(masalan: 1-A, 2-C, 3-B …)</small><input id="tkKey" maxlength="3000" value="${esc(B?.answer_key || "")}" placeholder="1-A, 2-C, 3-B, 4-D"></label>
    </div>
    <div class="tk-acts">${B ? `<button type="button" class="btn ghost" id="tkCfgCancel">Bekor qilish</button>` : ""}<button type="button" class="btn primary" id="tkSave">${B ? "Saqlash" : "Yaratish va ishlarni yuklash"}</button></div>
  </div>`;
  const drawRub = () => {
    $("#tkRub").innerHTML = rubric.map((r, i) => `<div class="tk-rub"><input data-r="${i}" data-k="name" value="${esc(r.name)}" maxlength="120" aria-label="Mezon nomi">
      <input data-r="${i}" data-k="points" type="number" min="0.5" max="1000" step="0.5" value="${tkNum(r.points)}" aria-label="Ball"><button type="button" class="btn sm ghost" data-rd="${i}" aria-label="O'chirish">✕</button></div>`).join("");
    $("#tkRub").querySelectorAll("input").forEach(inp => inp.oninput = () => { const r = rubric[+inp.dataset.r]; r[inp.dataset.k] = inp.dataset.k === "points" ? +inp.value : inp.value; });
    $("#tkRub").querySelectorAll("[data-rd]").forEach(b => b.onclick = () => { rubric.splice(+b.dataset.rd, 1); drawRub(); });
  };
  const kindVis = () => { const k = $("#tkKind").value; $("#tkKeyL").hidden = k !== "test"; };
  drawRub(); kindVis();
  $("#tkKind").onchange = () => { if (!B) rubric = M.rubrics[$("#tkKind").value].map(x => ({...x})); drawRub(); kindVis(); };
  $("#tkRubAdd").onclick = () => { rubric.push({name: "", points: 10}); drawRub(); };
  $("#tkRubTpl").onclick = () => { rubric = M.rubrics[$("#tkKind").value].map(x => ({...x})); drawRub(); };
  $("#tkCfgCancel")?.addEventListener("click", tkModalClose);
  $("#tkTaskFile")?.addEventListener("change", async e => {
    const f = e.target.files[0]; if (!f) return;
    try { TK.batch = await tkApi(`/api/tekshiruv/batches/${B.id}/task?name=${encodeURIComponent(f.name)}`, null, await f.arrayBuffer()); toast("Topshiriq fayli qo'shildi"); tkModalClose(); tkView(); }
    catch (er) { toast(er.msg || "Xatolik"); }
  });
  $("#tkSave").onclick = async () => {
    const b = $("#tkSave");
    const body = {title: $("#tkTitle").value.trim(), kind: $("#tkKind").value, max_score: +$("#tkMax").value, subject: $("#tkSubj").value.trim(),
      group_id: $("#tkGroup").value ? +$("#tkGroup").value : null, task_text: $("#tkTask").value, rubric: rubric.filter(r => (r.name || "").trim()),
      ref_answer: $("#tkRef").value, answer_key: $("#tkKey").value};
    if (body.title.length < 3) { toast("Tekshiruv nomini kiriting"); return; }
    b.disabled = true;
    try {
      TK.batch = await tkApi(B ? `/api/tekshiruv/batches/${B.id}` : "/api/tekshiruv/batches", body);
      toast(B ? "Saqlandi" : "Tekshiruv yaratildi — endi ishlarni yuklang"); tkModalClose(); tkView(); if (!B) tkUploadDlg();
    } catch (e) { toast(e.msg || "Xatolik"); if (b.isConnected) b.disabled = false; }
  };
}

/* ---------- modal oyna (yuklash, sozlamalar) ---------- */
function tkModal(title) {
  tkModalClose();
  document.body.insertAdjacentHTML("beforeend", `<div class="tk-modal" id="tkModal" role="dialog" aria-modal="true" aria-label="${esc(title)}"><div class="tk-modal-b">
    <div class="tk-modal-h"><b>${esc(title)}</b><button type="button" class="btn sm ghost" id="tkModalX" aria-label="Yopish">✕</button></div><div id="tkModalC"></div></div></div>`);
  const m = $("#tkModal");
  m.onclick = e => { if (e.target === m) tkModalClose(); };
  $("#tkModalX").onclick = tkModalClose;
  return $("#tkModalC");
}
function tkModalClose() { $("#tkModal")?.remove(); }

/* ---------- tekshiruv sahifasi: avval jadval; yuklash — tugma/modal yoki sahifaga sudrab tashlash ---------- */
async function tkOpen(id) {
  try { TK.batch = await tkApi(`/api/tekshiruv/batches/${id}`); tkView(); }
  catch (e) { TK.batch = null; toast(e.msg || "Ochib bo'lmadi"); tkShell(); }
}

const TK_FLT = [["all", "Hammasi"], ["ai", "AI taklifi"], ["qolda", "Qo'lda"], ["ok", "Tasdiqlangan"], ["sim", "O'xshash"]];
function tkView() {
  const el = $("#v-tekshiruv"), B = TK.batch, M = TK.meta, ro = !B.can_edit, C = B.counts;
  const pending = (C.yuklandi || 0) + (C.xato || 0);
  TK.flt = TK.flt || "all"; TK.view = "batch";
  el.innerHTML = `<div class="tk-bv">
    <div class="tk-bar">
      <button type="button" class="btn ghost sm" id="tkBack" title="Ro'yxatga qaytish">←</button>
      <div class="tk-title"><h3>${esc(B.title)}</h3><div class="tk-chips">${tkChip(B.kind_label)}${B.subject ? tkChip(B.subject) : ""}${B.group_name ? tkChip(B.group_name) : ""}${tkChip(`Maks. ${tkNum(B.max_score)} ball`)}${tkChip(M.label, M.engine === "claude" ? "ok" : (M.engine === "fake" ? "warn" : "bad"))}${ro ? tkChip(`Muallif: ${B.author} · faqat ko'rish`, "warn") : ""}</div></div>
      <div class="tk-bar-r">
        ${ro ? "" : `<button type="button" class="btn sm" id="tkUpB">${ico("upload", 14)} Ish yuklash</button>
        <button type="button" class="btn sm primary" id="tkRun" ${pending && !B.progress.running ? "" : "disabled"}>${ico("spark", 14)} Tekshirish${pending ? ` (${pending})` : ""}</button>
        <button type="button" class="btn sm" id="tkAll" ${C.tekshirildi ? "" : "disabled"} title="Faqat siz ochib ko'rgan AI takliflari tasdiqlanadi">Ko'rilganlarni tasdiqlash</button>`}
        <div class="tk-dd"><button type="button" class="btn sm ghost" id="tkExpB" aria-haspopup="true">Eksport ▾</button>
          <div class="tk-ddm" id="tkExpM" hidden><a href="/api/tekshiruv/batches/${B.id}/export.xlsx">Baholar (.xlsx)</a><a href="/api/tekshiruv/batches/${B.id}/export.csv">Baholar (.csv)</a><a href="/api/tekshiruv/batches/${B.id}/export.docx">Izohlar varaqasi (.docx)</a></div></div>
        <div class="tk-dd"><button type="button" class="btn sm ghost" id="tkMoreB" aria-label="Boshqa amallar">⋯</button>
          <div class="tk-ddm" id="tkMoreM" hidden><button type="button" id="tkSim">O'xshashlikni tekshirish</button>${ro ? "" : `<button type="button" id="tkCfgBtn">Sozlamalar (topshiriq, mezonlar)</button><button type="button" id="tkDelB" class="bad">Tekshiruvni o'chirish</button>`}</div></div>
      </div>
    </div>
    <div class="tk-line">${tkChip(`${B.works.length} ish`)}${tkChip(`${C.tasdiqlandi || 0} tasdiqlangan`, C.tasdiqlandi ? "ok" : "")}${tkChip(`${C.tekshirildi || 0} AI taklifi kutmoqda`, C.tekshirildi ? "info" : "")}${tkChip(`${C.qolda || 0} qo'lda tekshirish`, C.qolda ? "warn" : "")}${pending ? tkChip(`${pending} tekshirilmagan`) : ""}${tkChip(`o'rtacha: ${B.stats.avg === null ? "—" : tkNum(B.stats.avg)}`)}
      <span class="tk-flt" role="tablist">${TK_FLT.map(([k, l]) => `<button type="button" role="tab" data-fl="${k}" class="${TK.flt === k ? "on" : ""}">${esc(l)}</button>`).join("")}</span></div>
    <div id="tkProg"></div><div id="tkUp"></div><div id="tkSimBox"></div>
    <div id="tkWorks" class="tk-wbox"></div>
    ${ro ? "" : `<div class="tk-dropov" id="tkDropOv" hidden><div>${ico("upload", 30)}<b>Ishlarni shu yerga tashlang</b><span>PDF, Word, PowerPoint, Excel, matn, JPG/PNG yoki ZIP</span></div></div>`}
  </div>`;
  $("#tkBack").onclick = () => { TK.batch = null; TK.flt = "all"; tkShell(); };
  const dd = (b, m) => { $(b).onclick = e => { e.stopPropagation(); const mm = $(m), was = mm.hidden; el.querySelectorAll(".tk-ddm").forEach(x => x.hidden = true); mm.hidden = !was; }; };
  dd("#tkExpB", "#tkExpM"); dd("#tkMoreB", "#tkMoreM");
  el.querySelector(".tk-bv").addEventListener("click", e => { if (!e.target.closest(".tk-dd")) el.querySelectorAll(".tk-ddm").forEach(x => x.hidden = true); });
  el.querySelectorAll("[data-fl]").forEach(b => b.onclick = async () => { TK.flt = b.dataset.fl; if (TK.flt === "sim" && !TK.sim) await tkSimilarity(true); el.querySelectorAll("[data-fl]").forEach(x => x.classList.toggle("on", x === b)); tkWorks(); });
  $("#tkSim").onclick = () => { $("#tkMoreM").hidden = true; tkSimilarity(); };
  TK.sim = null;
  tkWorks(); tkProgress();
  if (ro) return;
  $("#tkUpB").onclick = tkUploadDlg;
  $("#tkCfgBtn").onclick = () => { $("#tkMoreM").hidden = true; tkForm(B); };
  $("#tkRun").onclick = async () => {
    const b = $("#tkRun"); b.disabled = true;
    try { const r = await tkApi(`/api/tekshiruv/batches/${B.id}/check`, {}); if (r.note) toast(r.note); else toast(`${r.started} ta ish tekshiruvga yuborildi`); TK.batch.progress = {done: 0, total: r.started, running: true}; tkProgress(); }
    catch (e) { toast(e.msg || "Xatolik"); b.disabled = false; }
  };
  $("#tkAll").onclick = async () => {
    const b = $("#tkAll"); if (!arm(b, "Ha, ko'rilganlarni tasdiqlash")) return;
    try { const r = await tkApi(`/api/tekshiruv/batches/${B.id}/confirm-seen`, {}); toast(`${r.confirmed} ta tasdiqlandi${r.unseen ? ` · ${r.unseen} ta hali ochib ko'rilmagan` : ""}`); tkOpen(B.id); }
    catch (e) { toast(e.msg || "Xatolik"); }
  };
  $("#tkDelB").onclick = async () => {
    const b = $("#tkDelB"); if (!arm(b, "Ha, butunlay o'chirish")) return;
    try { await tkApi(`/api/tekshiruv/batches/${B.id}/delete`, {}); toast("Tekshiruv o'chirildi"); TK.batch = null; TK.tab = "mine"; tkShell(); }
    catch (e) { toast(e.msg || "Xatolik"); }
  };
  /* butun sahifaga sudrab tashlash */
  const bv = el.querySelector(".tk-bv"), ov = $("#tkDropOv"); let depth = 0;
  const hasFiles = e => [...(e.dataTransfer?.types || [])].includes("Files");
  bv.addEventListener("dragenter", e => { if (!hasFiles(e)) return; e.preventDefault(); depth++; ov.hidden = false; });
  bv.addEventListener("dragover", e => { if (hasFiles(e)) e.preventDefault(); });
  bv.addEventListener("dragleave", () => { if (--depth <= 0) { depth = 0; ov.hidden = true; } });
  bv.addEventListener("drop", e => { if (!hasFiles(e)) return; e.preventDefault(); depth = 0; ov.hidden = true; tkUpload([...e.dataTransfer.files]); });
}

function tkUploadDlg() {
  const M = TK.meta, box = tkModal("Talaba ishlarini yuklash");
  box.innerHTML = `<label class="tk-drop" id="tkDrop" tabindex="0"><input type="file" id="tkFiles" multiple hidden accept=".pdf,.docx,.pptx,.xlsx,.txt,.jpg,.jpeg,.png,.zip">
      ${ico("upload", 26)}<b>Fayllarni shu yerga tashlang yoki tanlang</b>
      <span class="muted tiny">PDF, Word, PowerPoint, Excel, matn, JPG/PNG yoki ZIP · har biri ${M.max_mb} MB gacha · tekshiruvda ${M.max_works} tagacha ish.<br>Fayl nomida talaba familiyasi bo'lsa — avtomatik taniladi. Keyingi safar fayllarni to'g'ridan-to'g'ri sahifaga ham tashlashingiz mumkin.</span></label>`;
  const inp = $("#tkFiles"), drop = $("#tkDrop");
  inp.onchange = () => { tkModalClose(); tkUpload([...inp.files]); };
  drop.onkeydown = e => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); inp.click(); } };
  ["dragover", "dragenter"].forEach(ev => drop.addEventListener(ev, e => { e.preventDefault(); drop.classList.add("over"); }));
  ["dragleave", "drop"].forEach(ev => drop.addEventListener(ev, e => { e.preventDefault(); drop.classList.remove("over"); }));
  drop.addEventListener("drop", e => { const f = [...e.dataTransfer.files]; tkModalClose(); tkUpload(f); });
  drop.focus();
}

async function tkUpload(files) {
  const B = TK.batch, M = TK.meta;
  if (!files.length) return;
  const bad = [], ok = [];
  for (const f of files) { if (f.size > M.max_mb * 1048576) bad.push(`${f.name}: ${M.max_mb} MB dan katta`); else ok.push(f); }
  let i = 0, added = 0;
  for (const f of ok) {
    i += 1; const box = $("#tkUp"); if (box) box.innerHTML = `<div class="tk-prog"><span class="tk-spin"></span>Yuklanmoqda: ${i} / ${ok.length} — ${esc(f.name)}</div>`;
    try {
      const r = await tkApi(`/api/tekshiruv/batches/${B.id}/files?name=${encodeURIComponent(f.name)}`, null, await f.arrayBuffer());
      added += r.added.length; r.skipped.forEach(s => bad.push(`${s.file}: ${s.why}`));
      r.added.filter(a => a.err).forEach(a => bad.push(`${a.file}: ${a.err} — qo'lda tekshiruvga tushdi`));
    } catch (e) { if (e.message === "auth") return; bad.push(`${f.name}: ${e.msg || "xatolik"}`); }
  }
  toast(`${added} ta ish yuklandi`);
  await tkOpen(B.id);
  if (bad.length) $("#tkUp").innerHTML = `<div class="tk-note warn">${ico("info", 16)}<div><b>Yuklanmaganlar / ogohlantirishlar:</b><ul>${bad.map(x => `<li>${esc(x)}</li>`).join("")}</ul></div><button type="button" class="btn sm ghost tk-x" onclick="this.parentElement.remove()" aria-label="Yopish">✕</button></div>`;
}

function tkFilter(w) {
  const f = TK.flt || "all";
  if (f === "ai") return w.status === "tekshirildi";
  if (f === "qolda") return w.status === "qolda" || w.status === "xato";
  if (f === "ok") return w.status === "tasdiqlandi";
  if (f === "sim") return (TK.sim || new Set()).has(w.n);
  return true;
}
function tkWorks() {
  const B = TK.batch, box = $("#tkWorks");
  if (!B.works.length) { box.innerHTML = `<div class="tk-empty">Hali ish yuklanmagan.${B.can_edit ? ` <button type="button" class="btn primary sm" id="tkUpE">${ico("upload", 14)} Ish yuklash</button><div class="muted tiny">yoki fayllarni shu sahifaga sudrab tashlang</div>` : ""}</div>`; $("#tkUpE")?.addEventListener("click", tkUploadDlg); return; }
  const rows = B.works.filter(tkFilter);
  box.innerHTML = rows.length ? `<table class="tk-t tk-compact stack"><thead><tr><th>№</th><th>Talaba</th><th>Holat</th><th class="r">Ball</th><th>Belgilar</th></tr></thead><tbody>
    ${rows.map(w => { const st = TK_ST[w.status] || [w.status, ""];
      return `<tr class="tk-click" data-w="${w.id}" tabindex="0"><td data-l="№" class="muted">${w.n}</td>
        <td data-l="Talaba"><b>${w.student ? esc(w.student) : `<span class="muted">aniqlanmagan</span>`}</b>${w.label_auto ? ` <span class="muted tiny" title="Fayl nomidan aniqlandi — tekshiring">(avto)</span>` : ""}<span class="tk-fn">${esc(w.file)}</span></td>
        <td data-l="Holat">${tkChip(st[0], st[1])}${!w.seen && w.status === "tekshirildi" ? ` <span class="tk-dot" title="Hali ochib ko'rilmagan"></span>` : ""}</td>
        <td data-l="Ball" class="r"><b>${tkNum(w.total)}</b><span class="muted tiny"> / ${tkNum(B.max_score)}</span></td>
        <td data-l="Belgilar">${(w.flags || []).map(f => tkChip(f.split(" — ")[0], "warn")).join(" ") || (w.err ? tkChip(w.err, "bad") : "")}</td></tr>`; }).join("")}</tbody></table>`
    : `<div class="tk-empty">Bu filtr bo'yicha ish yo'q.</div>`;
  box.querySelectorAll("tr[data-w]").forEach(tr => {
    const open = () => tkWork(+tr.dataset.w);
    tr.onclick = open; tr.onkeydown = e => { if (e.key === "Enter") open(); };
  });
}

function tkStopPoll() { if (TK.poll) { clearTimeout(TK.poll); TK.poll = null; } }
async function tkProgress() {
  tkStopPoll();
  const B = TK.batch, box = $("#tkProg"); if (!box) return;
  const p = B.progress;
  if (!p.running) { box.innerHTML = B.run_err ? `<div class="tk-note warn">${ico("info", 16)}<span>${esc(B.run_err)}</span></div>` : ""; return; }
  box.innerHTML = `<div class="tk-prog"><span class="tk-spin"></span><span>Tekshirilmoqda: ${p.done} / ${p.total}</span><div class="tk-bar"><i style="width:${p.total ? Math.round(100 * p.done / p.total) : 0}%"></i></div></div>`;
  TK.poll = setTimeout(async () => {
    if (!TK.batch || TK.batch.id !== B.id || !$("#tkProg")) return;
    try { const r = await tkApi(`/api/tekshiruv/batches/${B.id}/progress`); if (r.running) { TK.batch.progress = r; tkProgress(); } else { toast("Tekshiruv tugadi"); tkOpen(B.id); } }
    catch (e) { /* tarmoq uzilishi — keyingi urinish */ TK.poll = setTimeout(tkProgress, 4000); }
  }, 2000);
}

async function tkSimilarity(quiet) {
  const box = $("#tkSimBox"); if (!quiet) box.innerHTML = `<p class="muted tiny">Hisoblanmoqda…</p>`;
  try {
    const r = await tkApi(`/api/tekshiruv/batches/${TK.batch.id}/similarity`);
    TK.sim = new Set(r.pairs.flatMap(p => [p.an, p.bn]));
    if (quiet) return;
    box.innerHTML = r.pairs.length ? `<div class="tk-note">${ico("info", 16)}<div><b>O'xshash ishlar (${r.pairs.length} juft) — tekshiring:</b><ul>${r.pairs.map(p =>
      `<li>${tkChip(p.level === "yuqori" ? "o'xshashlik yuqori" : "o'xshashlik o'rta", p.level === "yuqori" ? "bad" : "warn")} Ish #${p.an} ${esc(p.al)} ↔ Ish #${p.bn} ${esc(p.bl)} — ${p.jaccard}% umumiy matn (${p.contain}% qamrov)</li>`).join("")}</ul>
      <span class="muted tiny">Bu faqat ishlar orasidagi matn o'xshashligi; ko'chirma ekanini o'qituvchi hal qiladi.</span></div><button type="button" class="btn sm ghost tk-x" onclick="this.parentElement.remove()" aria-label="Yopish">✕</button></div>`
      : `<div class="tk-note">${ico("check", 16)}<span>Ishlar orasida sezilarli o'xshashlik topilmadi.</span><button type="button" class="btn sm ghost tk-x" onclick="this.parentElement.remove()" aria-label="Yopish">✕</button></div>`;
  } catch (e) { box.innerHTML = ""; toast(e.msg || "Xatolik"); }
}

/* ---------- ko'rib chiqish rejimi: chapda ishlar navbati, o'rtada ish, o'ngda baholash ---------- */
async function tkWork(wid) {
  let W;
  try { W = await tkApi(`/api/tekshiruv/works/${wid}`); } catch (e) { toast(e.msg || "Ochib bo'lmadi"); return; }
  const B = TK.batch, ro = !W.can_edit, F = W.final, A = W.ai;
  const wi = B.works.find(x => x.id === wid); if (wi) wi.seen = true;
  const st = TK_ST[W.status] || [W.status, ""];
  const ix = B.works.findIndex(x => x.id === wid);
  const el = $("#v-tekshiruv");
  tkStopPoll(); clearTimeout(TK.autoT); TK.view = "work"; TK.wid = wid; TK.confirmNext = null;
  const dotCls = w => ({tasdiqlandi: "ok", tekshirildi: w.seen ? "info" : "new", qolda: "warn", xato: "bad"})[w.status] || "";
  const clamp = (t, n) => `<div class="tk-clamp" style="--n:${n}">${t}</div>`;
  el.innerHTML = `<div class="tk-rv" id="tkRv">
    <div class="tk-bar">
      <button type="button" class="btn ghost sm" id="tkWBack" title="Jadvalga qaytish">← ${esc(B.title)}</button>
      <div class="tk-chips">${tkChip(`Ish #${W.n}`)}${tkChip(st[0], st[1])}${W.confidence ? tkChip(...(TK_CONF[W.confidence] || [W.confidence, ""])) : ""}${W.engine ? tkChip(W.engine) : ""}</div>
      <span class="muted tiny tk-keys">J / K — keyingi / oldingi · Enter — tasdiqlash</span>
      <span class="tk-nav"><button type="button" class="btn sm ghost" id="tkPrev" ${ix > 0 ? "" : "disabled"}>‹</button><span class="muted tiny">${ix + 1} / ${B.works.length}</span><button type="button" class="btn sm ghost" id="tkNext" ${ix < B.works.length - 1 ? "" : "disabled"}>›</button></span>
    </div>
    <div class="tk-3">
      <nav class="tk-q" aria-label="Ishlar navbati">${B.works.map(w => `<button type="button" class="tk-qi ${w.id === wid ? "on" : ""}" data-w="${w.id}">
        <i class="tk-sd ${dotCls(w)}" title="${esc((TK_ST[w.status] || [w.status])[0])}"></i><span><b>${w.n}. ${esc(w.student || "aniqlanmagan")}</b><small>${esc((TK_ST[w.status] || [w.status])[0])}</small></span><em>${tkNum(w.total)}</em></button>`).join("")}</nav>
      <section class="tk-doc">
        <div class="tk-src-h"><b>${esc(W.file)}</b><a class="btn sm ghost" href="/api/tekshiruv/works/${W.id}/file">Asl fayl</a></div>
        ${(W.flags || []).length ? `<div class="tk-note warn">${ico("info", 16)}<div>${W.flags.map(f => `<div>${esc(f)}</div>`).join("")}</div></div>` : ""}
        ${W.err ? `<div class="tk-note bad">${ico("info", 16)}<span>${esc(W.err)}</span></div>` : ""}
        ${W.img_names.length ? `<div class="tk-imgs">${W.img_names.map(n => `<a href="/api/tekshiruv/works/${W.id}/img/${n}" target="_blank" rel="noopener"><img src="/api/tekshiruv/works/${W.id}/img/${n}" alt="${esc(n)}" loading="lazy"></a>`).join("")}</div>` : ""}
        <pre class="tk-text">${esc(W.text || "(matn yo'q)")}${W.text_cut ? "\n…" : ""}</pre>
      </section>
      <aside class="tk-ev">
        <div class="tk-ev-s">
          <label class="tk-stud">Talaba<input id="tkStud" list="tkStuds" value="${esc(W.student)}" ${ro ? "disabled" : ""} placeholder="Familiya bo'yicha qidiring"><datalist id="tkStuds"></datalist></label>
          ${A ? `<div class="tk-ai">${clamp(`<b>AI xulosasi.</b> ${esc(A.summary || "")}`, 3)}
            ${(A.strengths || []).length || (A.mistakes || []).length ? `<details><summary>batafsil${(A.mistakes || []).length ? ` · ${A.mistakes.length} kamchilik` : ""}</summary>
              ${(A.strengths || []).length ? `<span class="tk-lbl ok">Kuchli tomonlar</span><ul>${A.strengths.map(x => `<li>${esc(x)}</li>`).join("")}</ul>` : ""}
              ${(A.mistakes || []).length ? `<span class="tk-lbl bad">Kamchiliklar</span><ul>${A.mistakes.map(m => `<li>${m.quote ? `<q>${esc(m.quote)}</q> — ` : ""}${esc(m.issue)}</li>`).join("")}</ul>` : ""}</details>` : ""}</div>`
            : `<div class="tk-note">${ico("info", 16)}<span>AI taklifi yo'q — ballni o'zingiz qo'ying.</span></div>`}
          <div class="tk-crh"><span>Mezon</span><span>Ball</span></div>
          <div class="tk-crit">${F.criteria.map((c, i) => `<div class="tk-cr"><div class="tk-cr-h"><span class="tk-cr-n" title="${esc(c.name)}">${esc(c.name)}</span>
              <button type="button" class="tk-cmt ${c.comment ? "has" : ""}" data-ct="${i}" title="${esc(c.comment || "Izoh qo'shish")}" aria-label="Izoh">💬</button>
              <span class="tk-cr-in"><input type="number" data-c="${i}" min="0" max="${c.points}" step="0.5" value="${c.score === null || c.score === undefined ? "" : tkNum(c.score)}" ${ro ? "disabled" : ""} aria-label="${esc(c.name)} balli"><span>/ ${tkNum(c.points)}</span></span></div>
            <textarea data-cc="${i}" rows="2" ${ro ? "disabled" : ""} placeholder="Izoh" hidden>${esc(c.comment || "")}</textarea></div>`).join("")}</div>
          <label class="tk-fb">Talabaga izoh<textarea id="tkFb" rows="3" ${ro ? "disabled" : ""}>${esc(F.feedback || "")}</textarea></label>
        </div>
        <div class="tk-ev-f">
          <div class="tk-total">Jami: <b id="tkTot">${tkNum(F.total)}</b> / ${tkNum(W.max_score)} <span class="muted tiny" id="tkAuto">${W.confirmed_at ? `· tasdiqlangan ${dmy(W.confirmed_at)}` : ""}</span></div>
          ${ro ? "" : `<div class="tk-ev-a"><div class="tk-dd"><button type="button" class="btn sm ghost" id="tkWMore" aria-label="Boshqa amallar">⋯</button>
              <div class="tk-ddm up" id="tkWMoreM" hidden><a href="/api/tekshiruv/works/${W.id}/docx">Izoh varaqasi (.docx)</a><button type="button" id="tkWDel" class="bad">Ishni o'chirish</button></div></div>
            <button type="button" class="btn primary" id="tkWOk">${ico("check", 15)} ${W.status === "tasdiqlandi" ? "Qayta tasdiqlash" : "Tasdiqlash"} va keyingi →</button></div>`}
        </div>
      </aside>
    </div>
  </div>`;
  const back = () => { clearTimeout(TK.autoT); TK.view = "batch"; tkOpen(B.id); };
  $("#tkWBack").onclick = back;
  $("#tkPrev").onclick = () => tkWork(B.works[ix - 1].id);
  $("#tkNext").onclick = () => tkWork(B.works[ix + 1].id);
  el.querySelectorAll(".tk-qi").forEach(b => b.onclick = () => tkWork(+b.dataset.w));
  el.querySelector(".tk-qi.on")?.scrollIntoView({block: "nearest"});
  el.querySelectorAll("[data-ct]").forEach(b => b.onclick = () => { const t = el.querySelector(`[data-cc="${b.dataset.ct}"]`); t.hidden = !t.hidden; if (!t.hidden) t.focus(); });
  if (ro) return;
  const recalc = () => {
    const sc = F.criteria.map((c, i) => $(`[data-c="${i}"]`).value), pts = F.criteria.reduce((a, c) => a + c.points, 0) || 1;
    $("#tkTot").textContent = sc.every(v => v !== "") ? tkNum(Math.min(sc.reduce((a, v) => a + +v, 0) / pts * W.max_score, W.max_score)) : "—";
  };
  let studT, studMap = {};
  $("#tkStud").oninput = () => {
    clearTimeout(studT);
    studT = setTimeout(async () => {
      const q = $("#tkStud").value.trim(); if (q.length < 2) return;
      try { const r = await tkApi(`/api/tekshiruv/batches/${B.id}/students?q=${encodeURIComponent(q)}`); studMap = Object.fromEntries(r.items.map(s => [s.name, s.id]));
        $("#tkStuds").innerHTML = r.items.map(s => `<option value="${esc(s.name)}">`).join(""); } catch (e) { /* jim */ }
    }, 250);
  };
  const body = confirm => {
    const name = $("#tkStud").value.trim(), sid = studMap[name];
    const b = {criteria: F.criteria.map((c, i) => ({name: c.name, score: $(`[data-c="${i}"]`).value === "" ? null : +$(`[data-c="${i}"]`).value, comment: $(`[data-cc="${i}"]`).value})),
      feedback: $("#tkFb").value, confirm};
    if (name !== W.student) { if (sid) b.student_id = sid; else b.student_label = name; }
    return b;
  };
  /* avtomatik saqlash: tahrirdan 1.5 s keyin (tasdiqlamasdan) */
  let dirty = false;
  const autosave = async () => {
    if (!dirty || TK.wid !== W.id) return;
    dirty = false; const a = $("#tkAuto"); if (a) a.textContent = "· saqlanmoqda…";
    try { await tkApi(`/api/tekshiruv/works/${W.id}`, body(false)); if ($("#tkAuto")) $("#tkAuto").textContent = "· saqlandi"; W.confirmed_at = null; }
    catch (e) { if ($("#tkAuto")) $("#tkAuto").textContent = "· saqlanmadi"; toast(e.msg || "Saqlab bo'lmadi"); }
  };
  const touched = () => { dirty = true; const a = $("#tkAuto"); if (a) a.textContent = "· o'zgartirildi"; clearTimeout(TK.autoT); TK.autoT = setTimeout(autosave, 1500); };
  el.querySelectorAll("[data-c]").forEach(i => i.addEventListener("input", () => { recalc(); touched(); }));
  el.querySelectorAll("[data-cc]").forEach(t => t.addEventListener("input", () => { el.querySelector(`[data-ct="${t.dataset.cc}"]`)?.classList.toggle("has", !!t.value.trim()); touched(); }));
  $("#tkFb").addEventListener("input", touched);
  $("#tkStud").addEventListener("change", touched);
  const confirmNext = async () => {
    const btn = $("#tkWOk"); if (!btn || btn.disabled) return;
    btn.disabled = true; clearTimeout(TK.autoT); dirty = false;
    try { await tkApi(`/api/tekshiruv/works/${W.id}`, body(true)); toast("Tasdiqlandi");
      TK.batch = await tkApi(`/api/tekshiruv/batches/${B.id}`);
      const L = TK.batch.works, j = L.findIndex(x => x.id === W.id);
      const nx = L.find((x, k) => k > j && x.status !== "tasdiqlandi") || L.find(x => x.status !== "tasdiqlandi" && x.id !== W.id);
      return nx ? tkWork(nx.id) : (toast("Barcha ishlar tasdiqlandi"), tkView());
    } catch (e) { toast(e.msg || "Xatolik"); if (btn.isConnected) btn.disabled = false; }
  };
  TK.confirmNext = confirmNext;
  $("#tkWOk").onclick = confirmNext;
  $("#tkWMore").onclick = e => { e.stopPropagation(); $("#tkWMoreM").hidden = !$("#tkWMoreM").hidden; };
  el.querySelector(".tk-rv").addEventListener("click", e => { if (!e.target.closest(".tk-dd")) { const m = $("#tkWMoreM"); if (m) m.hidden = true; } });
  $("#tkWDel").onclick = async () => {
    const b = $("#tkWDel"); if (!arm(b, "Ha, o'chirish")) return;
    try { await tkApi(`/api/tekshiruv/works/${W.id}/delete`, {}); toast("Ish o'chirildi"); back(); } catch (e) { toast(e.msg || "Xatolik"); }
  };
}

/* klaviatura (ko'rib chiqish rejimi): J/K — keyingi/oldingi, Enter — tasdiqlash va keyingi */
document.addEventListener("keydown", e => {
  if (e.key === "Escape") { if ($("#tkModal")) { tkModalClose(); return; } }
  const rv = $("#tkRv"); if (!rv || !rv.offsetParent || TK.view !== "work" || e.altKey || e.ctrlKey || e.metaKey || $("#tkModal")) return;
  const tag = e.target?.tagName || "";
  if (e.key === "Enter" && tag !== "TEXTAREA" && tag !== "BUTTON" && tag !== "A" && !e.target.closest?.("summary")) {
    if (tag === "INPUT" && e.target.id === "tkStud") return;
    e.preventDefault(); TK.confirmNext?.(); return;
  }
  if (/^(INPUT|TEXTAREA|SELECT)$/.test(tag)) return;
  if (e.key === "j" || e.key === "J") { e.preventDefault(); $("#tkNext")?.click(); }
  if (e.key === "k" || e.key === "K") { e.preventDefault(); $("#tkPrev")?.click(); }
});
