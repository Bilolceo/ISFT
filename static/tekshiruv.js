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
  const M = TK.meta, box = B ? $("#tkCfg") : $("#tkBody");
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
  $("#tkCfgCancel")?.addEventListener("click", () => { $("#tkCfg").innerHTML = ""; });
  $("#tkTaskFile")?.addEventListener("change", async e => {
    const f = e.target.files[0]; if (!f) return;
    try { TK.batch = await tkApi(`/api/tekshiruv/batches/${B.id}/task?name=${encodeURIComponent(f.name)}`, null, await f.arrayBuffer()); toast("Topshiriq fayli qo'shildi"); tkView(); }
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
      toast(B ? "Saqlandi" : "Tekshiruv yaratildi — endi ishlarni yuklang"); tkView();
    } catch (e) { toast(e.msg || "Xatolik"); if (b.isConnected) b.disabled = false; }
  };
}

/* ---------- tekshiruv sahifasi ---------- */
async function tkOpen(id) {
  try { TK.batch = await tkApi(`/api/tekshiruv/batches/${id}`); tkView(); }
  catch (e) { TK.batch = null; toast(e.msg || "Ochib bo'lmadi"); tkShell(); }
}

function tkView() {
  const el = $("#v-tekshiruv"), B = TK.batch, M = TK.meta, ro = !B.can_edit, C = B.counts;
  const pending = (C.yuklandi || 0) + (C.xato || 0);
  el.innerHTML = tkHead() + `<div class="card tk-card">
    <div class="tk-top"><button type="button" class="btn ghost sm" id="tkBack">← Ro'yxat</button>
      <div class="tk-title"><h3>${esc(B.title)}</h3><div class="tk-chips">${tkChip(B.kind_label)}${B.subject ? tkChip(B.subject) : ""}${B.group_name ? tkChip(B.group_name) : ""}${tkChip(`Maks. ${tkNum(B.max_score)} ball`)}${ro ? tkChip(`Muallif: ${B.author} · faqat ko'rish`, "warn") : ""}</div></div></div>
    <div class="tk-stats">
      <div><b>${B.works.length}</b><span>ish</span></div><div><b>${C.tasdiqlandi || 0}</b><span>tasdiqlangan</span></div>
      <div><b>${C.tekshirildi || 0}</b><span>AI taklifi kutmoqda</span></div><div class="${C.qolda ? "warn" : ""}"><b>${C.qolda || 0}</b><span>qo'lda tekshirish</span></div>
      <div><b>${B.stats.avg === null ? "—" : tkNum(B.stats.avg)}</b><span>o'rtacha (tasdiqlangan)</span></div></div>
    <div id="tkProg"></div>
    ${ro ? "" : `<div class="tk-acts tk-left">
      <button type="button" class="btn primary" id="tkRun" ${pending && !B.progress.running ? "" : "disabled"}>${ico("spark", 15)} Tekshirish${pending ? ` (${pending})` : ""}</button>
      <button type="button" class="btn" id="tkAll" ${C.tekshirildi ? "" : "disabled"} title="Faqat siz ochib ko'rgan AI takliflari tasdiqlanadi">Ko'rilganlarni tasdiqlash</button>
      <button type="button" class="btn ghost" id="tkCfgBtn">Sozlamalar</button>
      <button type="button" class="btn ghost" id="tkDelB">O'chirish</button></div>`}
    <div id="tkCfg"></div>
    ${ro ? "" : `<label class="tk-drop" id="tkDrop" tabindex="0"><input type="file" id="tkFiles" multiple hidden accept=".pdf,.docx,.pptx,.xlsx,.txt,.jpg,.jpeg,.png,.zip">
      ${ico("upload", 24)}<b>Talaba ishlarini shu yerga tashlang yoki tanlang</b>
      <span class="muted tiny">PDF, Word, PowerPoint, Excel, matn, JPG/PNG yoki ZIP · har biri ${M.max_mb} MB gacha · tekshiruvda ${M.max_works} tagacha ish. Fayl nomida talaba familiyasi bo'lsa — avtomatik taniladi.</span></label>
      <div id="tkUp"></div>`}
    <div class="tk-acts tk-left tk-exp"><span class="muted tiny">Eksport:</span>
      <a class="btn sm" href="/api/tekshiruv/batches/${B.id}/export.xlsx">Baholar (.xlsx)</a><a class="btn sm" href="/api/tekshiruv/batches/${B.id}/export.csv">.csv</a>
      <a class="btn sm" href="/api/tekshiruv/batches/${B.id}/export.docx">Izohlar varaqasi (.docx)</a>
      <button type="button" class="btn sm ghost" id="tkSim">O'xshashlikni tekshirish</button></div>
    <div id="tkSimBox"></div>
    <div id="tkWorks"></div>
  </div>`;
  $("#tkBack").onclick = () => { TK.batch = null; tkShell(); };
  tkWorks(); tkProgress();
  $("#tkSim").onclick = tkSimilarity;
  if (ro) return;
  $("#tkCfgBtn").onclick = () => tkForm(B);
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
  const inp = $("#tkFiles"), drop = $("#tkDrop");
  inp.onchange = () => tkUpload([...inp.files]);
  drop.onkeydown = e => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); inp.click(); } };
  ["dragover", "dragenter"].forEach(ev => drop.addEventListener(ev, e => { e.preventDefault(); drop.classList.add("over"); }));
  ["dragleave", "drop"].forEach(ev => drop.addEventListener(ev, e => { e.preventDefault(); drop.classList.remove("over"); }));
  drop.addEventListener("drop", e => tkUpload([...e.dataTransfer.files]));
}

async function tkUpload(files) {
  const B = TK.batch, M = TK.meta, box = $("#tkUp");
  if (!files.length) return;
  const bad = [], ok = [];
  for (const f of files) { if (f.size > M.max_mb * 1048576) bad.push(`${f.name}: ${M.max_mb} MB dan katta`); else ok.push(f); }
  let i = 0, added = 0;
  for (const f of ok) {
    i += 1; box.innerHTML = `<div class="tk-prog"><span class="tk-spin"></span>Yuklanmoqda: ${i} / ${ok.length} — ${esc(f.name)}</div>`;
    try {
      const r = await tkApi(`/api/tekshiruv/batches/${B.id}/files?name=${encodeURIComponent(f.name)}`, null, await f.arrayBuffer());
      added += r.added.length; r.skipped.forEach(s => bad.push(`${s.file}: ${s.why}`));
      r.added.filter(a => a.err).forEach(a => bad.push(`${a.file}: ${a.err} — qo'lda tekshiruvga tushdi`));
    } catch (e) { if (e.message === "auth") return; bad.push(`${f.name}: ${e.msg || "xatolik"}`); }
  }
  toast(`${added} ta ish yuklandi`);
  await tkOpen(B.id);
  if (bad.length) $("#tkUp").innerHTML = `<div class="tk-note warn">${ico("info", 16)}<div><b>Yuklanmaganlar / ogohlantirishlar:</b><ul>${bad.map(x => `<li>${esc(x)}</li>`).join("")}</ul></div></div>`;
}

function tkWorks() {
  const B = TK.batch, box = $("#tkWorks");
  if (!B.works.length) { box.innerHTML = `<div class="tk-empty">Hali ish yuklanmagan.</div>`; return; }
  box.innerHTML = `<div class="tw"><table class="tk-t stack"><thead><tr><th>№</th><th>Talaba</th><th>Fayl</th><th>Holat</th><th>Ball</th><th>Belgilar</th></tr></thead><tbody>
    ${B.works.map(w => { const st = TK_ST[w.status] || [w.status, ""];
      return `<tr class="tk-click" data-w="${w.id}" tabindex="0"><td data-l="№">${w.n}</td>
        <td data-l="Talaba">${w.student ? esc(w.student) + (w.label_auto ? ` <span class="muted tiny" title="Fayl nomidan aniqlandi — tekshiring">(avto)</span>` : "") : `<span class="muted">aniqlanmagan</span>`}</td>
        <td data-l="Fayl"><span class="tk-file">${esc(w.file)}</span><div class="muted tiny">${esc(w.fkind)}${w.images ? ` · ${w.images} rasm` : ""}</div></td>
        <td data-l="Holat">${tkChip(st[0], st[1])}${!w.seen && w.status === "tekshirildi" ? ` <span class="tk-dot" title="Hali ochib ko'rilmagan"></span>` : ""}</td>
        <td data-l="Ball"><b>${tkNum(w.total)}</b> <span class="muted tiny">/ ${tkNum(B.max_score)}</span></td>
        <td data-l="Belgilar">${(w.flags || []).map(f => tkChip(f.split(" — ")[0], "warn")).join(" ") || (w.err ? tkChip(w.err, "bad") : "—")}</td></tr>`; }).join("")}</tbody></table></div>`;
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

async function tkSimilarity() {
  const box = $("#tkSimBox"); box.innerHTML = `<p class="muted tiny">Hisoblanmoqda…</p>`;
  try {
    const r = await tkApi(`/api/tekshiruv/batches/${TK.batch.id}/similarity`);
    box.innerHTML = r.pairs.length ? `<div class="tk-note">${ico("info", 16)}<div><b>O'xshash ishlar (${r.pairs.length} juft) — tekshiring:</b><ul>${r.pairs.map(p =>
      `<li>${tkChip(p.level === "yuqori" ? "o'xshashlik yuqori" : "o'xshashlik o'rta", p.level === "yuqori" ? "bad" : "warn")} Ish #${p.an} ${esc(p.al)} ↔ Ish #${p.bn} ${esc(p.bl)} — ${p.jaccard}% umumiy matn (${p.contain}% qamrov)</li>`).join("")}</ul>
      <span class="muted tiny">Bu faqat ishlar orasidagi matn o'xshashligi; ko'chirma ekanini o'qituvchi hal qiladi.</span></div></div>`
      : `<div class="tk-note">${ico("check", 16)}<span>Ishlar orasida sezilarli o'xshashlik topilmadi.</span></div>`;
  } catch (e) { box.innerHTML = ""; toast(e.msg || "Xatolik"); }
}

/* ---------- bitta ish: matn + AI baholash, tahrir va tasdiq ---------- */
async function tkWork(wid) {
  let W;
  try { W = await tkApi(`/api/tekshiruv/works/${wid}`); } catch (e) { toast(e.msg || "Ochib bo'lmadi"); return; }
  const B = TK.batch, ro = !W.can_edit, F = W.final, A = W.ai;
  const st = TK_ST[W.status] || [W.status, ""];
  const ix = B.works.findIndex(x => x.id === wid);
  const el = $("#v-tekshiruv");
  tkStopPoll();
  el.innerHTML = tkHead() + `<div class="card tk-card">
    <div class="tk-top"><button type="button" class="btn ghost sm" id="tkWBack">← ${esc(B.title)}</button>
      <div class="tk-chips">${tkChip(`Ish #${W.n}`)}${tkChip(st[0], st[1])}${W.confidence ? tkChip(...(TK_CONF[W.confidence] || [W.confidence, ""])) : ""}${W.engine ? tkChip(W.engine) : ""}</div>
      <span class="tk-nav"><button type="button" class="btn sm ghost" id="tkPrev" ${ix > 0 ? "" : "disabled"}>‹ Oldingi</button><button type="button" class="btn sm ghost" id="tkNext" ${ix < B.works.length - 1 ? "" : "disabled"}>Keyingi ›</button></span></div>
    ${(W.flags || []).length ? `<div class="tk-note warn">${ico("info", 16)}<div>${W.flags.map(f => `<div>${esc(f)}</div>`).join("")}</div></div>` : ""}
    ${W.err ? `<div class="tk-note bad">${ico("info", 16)}<span>${esc(W.err)}</span></div>` : ""}
    <div class="tk-split">
      <div class="tk-src">
        <div class="tk-src-h"><b>${esc(W.file)}</b><a class="btn sm ghost" href="/api/tekshiruv/works/${W.id}/file">Asl fayl</a></div>
        ${W.img_names.length ? `<div class="tk-imgs">${W.img_names.map(n => `<a href="/api/tekshiruv/works/${W.id}/img/${n}" target="_blank" rel="noopener"><img src="/api/tekshiruv/works/${W.id}/img/${n}" alt="${esc(n)}" loading="lazy"></a>`).join("")}</div>` : ""}
        <pre class="tk-text">${esc(W.text || "(matn yo'q)")}${W.text_cut ? "\n…" : ""}</pre>
      </div>
      <div class="tk-eval">
        <label class="tk-stud">Talaba<div class="tk-stud-row"><input id="tkStud" list="tkStuds" value="${esc(W.student)}" ${ro ? "disabled" : ""} placeholder="Familiya bo'yicha qidiring"><datalist id="tkStuds"></datalist></div></label>
        ${A ? `<div class="tk-ai"><span class="tk-lbl">AI xulosasi</span><p>${esc(A.summary || "")}</p>
          ${(A.strengths || []).length ? `<span class="tk-lbl ok">Kuchli tomonlar</span><ul>${A.strengths.map(x => `<li>${esc(x)}</li>`).join("")}</ul>` : ""}
          ${(A.mistakes || []).length ? `<span class="tk-lbl bad">Kamchiliklar</span><ul>${A.mistakes.map(m => `<li>${m.quote ? `<q>${esc(m.quote)}</q> — ` : ""}${esc(m.issue)}</li>`).join("")}</ul>` : ""}</div>` : `<div class="tk-note">${ico("info", 16)}<span>AI taklifi yo'q — mezonlar bo'yicha ballni o'zingiz qo'ying.</span></div>`}
        <span class="tk-lbl">Mezonlar bo'yicha ball</span>
        <div class="tk-crit">${F.criteria.map((c, i) => `<div class="tk-cr"><div class="tk-cr-h"><span>${esc(c.name)}</span><span class="tk-cr-in"><input type="number" data-c="${i}" min="0" max="${c.points}" step="0.5" value="${c.score === null || c.score === undefined ? "" : tkNum(c.score)}" ${ro ? "disabled" : ""} aria-label="${esc(c.name)} balli"> / ${tkNum(c.points)}</span></div>
          <textarea data-cc="${i}" rows="1" ${ro ? "disabled" : ""} placeholder="Izoh">${esc(c.comment || "")}</textarea></div>`).join("")}</div>
        <div class="tk-total">Jami: <b id="tkTot">${tkNum(F.total)}</b> / ${tkNum(W.max_score)}</div>
        <label class="tk-fb">Talabaga izoh<textarea id="tkFb" rows="5" ${ro ? "disabled" : ""}>${esc(F.feedback || "")}</textarea></label>
        ${ro ? "" : `<div class="tk-acts"><button type="button" class="btn ghost" id="tkWDel">O'chirish</button><a class="btn ghost" href="/api/tekshiruv/works/${W.id}/docx">Izoh (.docx)</a>
          <button type="button" class="btn" id="tkWSave">Saqlash</button><button type="button" class="btn primary" id="tkWOk">${ico("check", 15)} ${W.status === "tasdiqlandi" ? "Qayta tasdiqlash" : "Tasdiqlash"}</button></div>
          ${W.confirmed_at ? `<p class="muted tiny">Tasdiqlangan: ${dmy(W.confirmed_at)}. Tahrirlasangiz, qayta tasdiqlang.</p>` : ""}`}
      </div></div></div>`;
  const back = () => tkOpen(B.id);
  $("#tkWBack").onclick = back;
  $("#tkPrev").onclick = () => tkWork(B.works[ix - 1].id);
  $("#tkNext").onclick = () => tkWork(B.works[ix + 1].id);
  if (ro) return;
  const recalc = () => {
    const sc = F.criteria.map((c, i) => $(`[data-c="${i}"]`).value), pts = F.criteria.reduce((a, c) => a + c.points, 0) || 1;
    $("#tkTot").textContent = sc.every(v => v !== "") ? tkNum(Math.min(sc.reduce((a, v) => a + +v, 0) / pts * W.max_score, W.max_score)) : "—";
  };
  el.querySelectorAll("[data-c]").forEach(i => i.oninput = recalc);
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
  const save = async (btn, confirm) => {
    btn.disabled = true;
    try { await tkApi(`/api/tekshiruv/works/${W.id}`, body(confirm)); toast(confirm ? "Tasdiqlandi" : "Saqlandi");
      TK.batch = await tkApi(`/api/tekshiruv/batches/${B.id}`);
      if (confirm) { const nx = TK.batch.works.find((x, j) => j > ix && x.status !== "tasdiqlandi"); return nx ? tkWork(nx.id) : tkView(); }
      tkWork(W.id);
    } catch (e) { toast(e.msg || "Xatolik"); if (btn.isConnected) btn.disabled = false; }
  };
  $("#tkWSave").onclick = () => save($("#tkWSave"), false);
  $("#tkWOk").onclick = () => save($("#tkWOk"), true);
  $("#tkWDel").onclick = async () => {
    const b = $("#tkWDel"); if (!arm(b, "Ha, o'chirish")) return;
    try { await tkApi(`/api/tekshiruv/works/${W.id}/delete`, {}); toast("Ish o'chirildi"); back(); } catch (e) { toast(e.msg || "Xatolik"); }
  };
}
