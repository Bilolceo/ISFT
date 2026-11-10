/* =====================================================================
   «Taqdimot» — o'qituvchi uchun ISFT shablonida taqdimot (app/taqdimot.py, /api/taqdimot).
     1) material: Word / PDF / matn → 2) reja (AI: Claude yoki AI siz) → 3) rejani tahrirlash → 4) .pptx yuklab olish.
   «Mening taqdimotlarim» — tarix; kafedra mudiri — «Kafedra taqdimotlari» (faqat ko'rish va yuklab olish).
   Global: renderTaqdimot() — app.js go() chaqiradi. app.js yordamchilari: $, esc, toast, arm, ico, dmy.
   ===================================================================== */
const TQ = {meta: null, tab: "new", deck: null, dirty: false, src: "file", file: null};
if (!document.querySelector('link[href="taqdimot.css"]')) document.head.insertAdjacentHTML("beforeend", '<link rel="stylesheet" href="taqdimot.css">');

const TQ_FIELDS = {
  plan: ["bullets"], definition: ["text", "highlight", "subheading", "bullets", "notes"], theory: ["text", "highlight", "subheading", "bullets", "notes"],
  two_column: ["text", "columns", "notes"], steps: ["text", "steps", "notes"], example: ["text", "steps", "answer", "check", "note", "notes"],
  image: ["image", "caption", "text", "bullets", "notes"], tasks: ["text", "cards", "notes"], questions: ["bullets", "notes"],
  summary: ["cards", "notes"], references: ["bullets"],
};
const TQ_LBL = {text: "Matn", highlight: "Asosiy formula / ta'kid (ramkada)", subheading: "Kichik sarlavha", bullets: "Bandlar (har qatorda bittasi)",
  columns: "Ikki ustun", steps: "Qadamlar (har qatorda: sarlavha | matn)", answer: "Javob", check: "Tekshiruv (har qatorda bittasi)", note: "Izoh (pastda)",
  cards: "Kartochkalar (har qatorda: sarlavha | matn)", image: "Rasm", caption: "Rasm izohi", notes: "Ma'ruzachi izohi (slaydda ko'rinmaydi)"};
const TQ_TEXT_FIELD = {text: "Ta'rif matni (kartochkada)"};
const TQ_ST = {yangi: ["Yangi", ""], reja: ["Reja tayyor", "info"], tayyor: ["PPTX tayyor", "ok"]};

async function tqApi(url, body, raw) {
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
const tqChip = (t, cls = "") => `<span class="tq-chip ${cls}">${esc(t)}</span>`;
const tqLines = a => (a || []).join("\n");
const tqPairs = a => (a || []).map(x => (x.title ? x.title + " | " : "") + (x.text || "")).join("\n");
const tqSplitLines = s => String(s || "").split("\n").map(x => x.trim()).filter(Boolean);
const tqSplitPairs = s => tqSplitLines(s).map(l => { const i = l.indexOf("|"); return i < 0 ? {title: "", text: l} : {title: l.slice(0, i).trim(), text: l.slice(i + 1).trim()}; });

async function renderTaqdimot() {
  const el = $("#v-taqdimot");
  if (!el.innerHTML) el.innerHTML = `<p class="muted">Yuklanmoqda…</p>`;
  try { TQ.meta = await tqApi("/api/taqdimot/meta"); }
  catch (e) { el.innerHTML = e.message === "denied" ? `<div class="card tq-empty">${esc(e.msg)}</div>` : errCard("taqdimot"); return; }
  if (TQ.deck) return tqOpen(TQ.deck.id);
  tqShell();
}

function tqHead() {
  const M = TQ.meta;
  const eng = tqChip(M.label, M.engine === "claude" ? "ok" : (M.engine === "fake" ? "warn" : ""));
  return `<div class="tq-head"><div><h2>Taqdimot tayyorlash</h2>
      <span class="muted">Ma'ruza materialini yuklang — tizim ISFT shablonida taqdimot rejasini tuzadi, siz tahrirlaysiz va .pptx yuklab olasiz.</span></div>
    <div class="tq-head-r">${eng}${tqChip(`Bugun: ${M.used} / ${M.limit}`, M.used >= M.limit ? "bad" : "")}</div></div>`;
}

function tqShell() {
  const el = $("#v-taqdimot"), M = TQ.meta;
  const tabs = [["new", "Yangi taqdimot"], ["mine", "Mening taqdimotlarim"]].concat(M.mode === "dept" ? [["dept", "Kafedra taqdimotlari"]] : []);
  el.innerHTML = tqHead() + `<div class="tq-tabs" role="tablist">${tabs.map(([k, l]) => `<button type="button" role="tab" data-t="${k}" class="${TQ.tab === k ? "on" : ""}" aria-selected="${TQ.tab === k}">${esc(l)}</button>`).join("")}</div><div id="tqBody"></div>`;
  el.querySelectorAll(".tq-tabs button").forEach(b => b.onclick = () => { TQ.tab = b.dataset.t; tqShell(); });
  if (TQ.tab === "new") tqNew(); else tqList(TQ.tab);
}

function tqNew() {
  const M = TQ.meta, box = $("#tqBody");
  const noAi = M.engine !== "claude";
  box.innerHTML = `<div class="card tq-card">
    ${noAi ? `<div class="tq-note">${ico("info", 16)}<span>${M.engine === "fake" ? "Sinov rejimi: reja soxta AI bilan tuziladi." : "AI ulanmagan — reja hujjat tuzilmasidan (sarlavhalar, xatboshilar, ro'yxatlar, rasmlar) tuziladi. Sarlavhali Word fayl eng yaxshi natija beradi."}</span></div>` : ""}
    <div class="tq-seg" role="tablist"><button type="button" data-s="file" class="${TQ.src === "file" ? "on" : ""}">Fayl yuklash</button><button type="button" data-s="text" class="${TQ.src === "text" ? "on" : ""}">Matn yozish</button></div>
    <div id="tqSrc"></div>
    <div class="tq-grid">
      <label>Fan nomi<input id="tqSubj" list="tqSubjs" maxlength="120" placeholder="masalan, Iqtisodiyot nazariyasi"><datalist id="tqSubjs">${(M.subjects || []).map(s => `<option value="${esc(s)}">`).join("")}</datalist></label>
      <label>Mavzu raqami<input id="tqNo" maxlength="20" inputmode="numeric" placeholder="masalan, 5"></label>
      <label class="wide">Mavzu nomi <small>(bo'sh qolsa — materialdan olinadi)</small><input id="tqTitle" maxlength="200"></label>
      <label>Slaydlar soni<select id="tqSlides"><option value="">Avtomatik (kontentga qarab)</option>${[8, 10, 12, 15, 18, 20, 25, 30].map(n => `<option value="${n}">~${n}</option>`).join("")}</select></label>
      <label class="wide">Izoh <small>(auditoriya, urg'u, nimalar bo'lsin)</small><textarea id="tqAud" rows="2" maxlength="500" placeholder="masalan, 2-kurs talabalari uchun, ko'proq amaliy misollar"></textarea></label>
    </div>
    <div class="tq-acts"><span class="muted tiny">Faqat siz yuklagan material ishlatiladi. Fayl: .docx, .pdf, .txt · ${M.max_mb} MB gacha.</span>
      <button type="button" class="btn primary" id="tqGo" ${M.used >= M.limit ? "disabled" : ""}>${ico("spark", 16)} Reja tuzish</button></div>
    <div id="tqProg" class="tq-prog" hidden></div>
  </div>`;
  box.querySelectorAll(".tq-seg button").forEach(b => b.onclick = () => { TQ.src = b.dataset.s; tqNew(); });
  const src = $("#tqSrc");
  if (TQ.src === "file") {
    src.innerHTML = `<label class="tq-drop" id="tqDrop" tabindex="0"><input type="file" id="tqFile" accept=".docx,.pdf,.txt,application/pdf,text/plain,application/vnd.openxmlformats-officedocument.wordprocessingml.document" hidden>
      ${ico("file", 26)}<b id="tqFname">${TQ.file ? esc(TQ.file.name) : "Faylni shu yerga tashlang yoki tanlang"}</b><span class="muted tiny">Word (.docx), PDF (rasmlari bilan) yoki matn (.txt)</span></label>`;
    const inp = $("#tqFile"), drop = $("#tqDrop");
    const setF = f => { if (!f) return; if (f.size > M.max_mb * 1048576) { toast(`Fayl hajmi ${M.max_mb} MB dan oshmasin`); return; } TQ.file = f; $("#tqFname").textContent = `${f.name} · ${(f.size / 1048576).toFixed(1)} MB`; };
    inp.onchange = () => setF(inp.files[0]);
    drop.onkeydown = e => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); inp.click(); } };
    ["dragover", "dragenter"].forEach(ev => drop.addEventListener(ev, e => { e.preventDefault(); drop.classList.add("over"); }));
    ["dragleave", "drop"].forEach(ev => drop.addEventListener(ev, e => { e.preventDefault(); drop.classList.remove("over"); }));
    drop.addEventListener("drop", e => setF(e.dataTransfer.files[0]));
  } else {
    src.innerHTML = `<textarea id="tqText" class="tq-text" rows="12" placeholder="Ma'ruza matnini shu yerga yozing yoki joylang. Sarlavhalarni # bilan, bandlarni - bilan boshlash mumkin."></textarea>`;
  }
  $("#tqGo").onclick = async () => {
    const b = $("#tqGo");
    const meta = {subject: $("#tqSubj").value.trim(), topic_no: $("#tqNo").value.trim(), title: $("#tqTitle").value.trim(), slides: $("#tqSlides").value, audience: $("#tqAud").value.trim()};
    let call;
    if (TQ.src === "file") {
      if (!TQ.file) { toast("Avval faylni tanlang"); return; }
      const q = new URLSearchParams({name: TQ.file.name, ...meta});
      const raw = await TQ.file.arrayBuffer();
      call = () => tqApi(`/api/taqdimot/decks?${q}`, null, raw);
    } else {
      const text = ($("#tqText").value || "").trim();
      if (text.length < 40) { toast("Matn juda qisqa"); return; }
      call = () => tqApi("/api/taqdimot/decks/text", {...meta, slides: meta.slides ? +meta.slides : null, text});
    }
    b.disabled = true;
    const pr = $("#tqProg"); pr.hidden = false;
    pr.innerHTML = `<span class="tq-spin"></span><span>${M.engine === "claude" ? "AI material asosida reja tuzmoqda — odatda 1–2 daqiqa…" : "Reja tuzilmoqda…"}</span>`;
    try {
      const d = await call();
      TQ.file = null; TQ.deck = d; TQ.dirty = false;
      toast("Reja tayyor — tekshirib, tahrirlang");
      TQ.meta.used += 1;
      tqEditor();
    } catch (e) {
      if (e.message !== "auth") toast(e.msg || "Xatolik yuz berdi");
      pr.hidden = true;
    } finally { if (b.isConnected) b.disabled = TQ.meta.used >= TQ.meta.limit; }
  };
}

async function tqList(scope) {
  const box = $("#tqBody");
  box.innerHTML = `<p class="muted">Yuklanmoqda…</p>`;
  let d;
  try { d = await tqApi(`/api/taqdimot/decks?scope=${scope}`); } catch (e) { box.innerHTML = `<div class="card tq-empty">${esc(e.msg || "Yuklab bo'lmadi")}</div>`; return; }
  if (!d.items.length) { box.innerHTML = `<div class="card tq-empty">${scope === "dept" ? "Kafedra o'qituvchilari hali taqdimot tayyorlamagan." : "Hali taqdimot yo'q. «Yangi taqdimot» bo'limidan boshlang."}</div>`; return; }
  box.innerHTML = `<div class="card tq-card"><div class="tw"><table class="tq-t stack"><thead><tr>${scope === "dept" ? "<th>O'qituvchi</th>" : ""}<th>Mavzu</th><th>Fan</th><th>Holat</th><th>Slayd</th><th>Usul</th><th>Sana</th></tr></thead><tbody>
    ${d.items.map((r, i) => `<tr class="tq-click" data-i="${i}" tabindex="0">${scope === "dept" ? `<td data-l="O'qituvchi">${esc((r.user_name || "").split(":").pop().trim())}</td>` : ""}
      <td data-l="Mavzu"><b>${esc((r.topic_no ? r.topic_no + "-mavzu. " : "") + (r.title || "—"))}</b><div class="muted tiny">${esc(r.source_name || "")}</div></td>
      <td data-l="Fan">${esc(r.subject || "—")}</td><td data-l="Holat">${tqChip(...(TQ_ST[r.status] || [r.status, ""]))}</td>
      <td data-l="Slayd">${r.slides || "—"}</td><td data-l="Usul">${esc(r.engine_label)}</td><td data-l="Sana">${dmy(r.updated_at || r.created_at)}</td></tr>`).join("")}</tbody></table></div></div>`;
  box.querySelectorAll("tr[data-i]").forEach(tr => {
    const open = () => tqOpen(d.items[+tr.dataset.i].id);
    tr.onclick = open; tr.onkeydown = e => { if (e.key === "Enter") open(); };
  });
}

async function tqOpen(id) {
  try { TQ.deck = await tqApi(`/api/taqdimot/decks/${id}`); TQ.dirty = false; tqEditor(); }
  catch (e) { TQ.deck = null; toast(e.msg || "Ochib bo'lmadi"); tqShell(); }
}

function tqEditor() {
  const el = $("#v-taqdimot"), D = TQ.deck, O = D.outline || {slides: []}, ro = !D.can_edit;
  const st = TQ_ST[D.status] || [D.status, ""];
  el.innerHTML = tqHead() + `<div class="card tq-card">
    <div class="tq-ed-top"><button type="button" class="btn ghost sm" id="tqBack">← Ro'yxat</button>
      <div class="tq-chips">${tqChip(st[0], st[1])}${tqChip(D.engine_label)}${D.source_name ? tqChip(D.source_name) : ""}${D.images ? tqChip(`${D.images} ta rasm`) : ""}${D.truncated ? tqChip("material qisqartirildi", "warn") : ""}${D.pages ? tqChip(`≈ ${D.pages} slayd`) : ""}${ro ? tqChip("faqat ko'rish", "warn") : ""}</div></div>
    ${ro ? `<p class="muted tiny">Muallif: ${esc((D.user_name || "").split(":").pop().trim())}</p>` : ""}
    <div class="tq-grid">
      <label>Fan nomi<input data-o="subject" value="${esc(O.subject || "")}" maxlength="120" ${ro ? "disabled" : ""}></label>
      <label>Mavzu raqami<input data-o="topic_no" value="${esc(O.topic_no || "")}" maxlength="20" ${ro ? "disabled" : ""}></label>
      <label class="wide">Mavzu nomi<input data-o="title" value="${esc(O.title || "")}" maxlength="200" ${ro ? "disabled" : ""}></label>
      <label class="wide">Qo'shimcha satr (titulda)<input data-o="subtitle" value="${esc(O.subtitle || "")}" maxlength="200" ${ro ? "disabled" : ""}></label>
    </div>
    <div class="tq-acts tq-sticky">
      ${ro ? "" : `<button type="button" class="btn" id="tqSave">Saqlash</button><button type="button" class="btn" id="tqRegen" title="Material asosida rejani qaytadan tuzish (kunlik cheklovga kiradi)">${ico("refresh", 15)} Qayta tuzish</button>
      <button type="button" class="btn primary" id="tqBuild">${ico("report", 15)} PPTX yaratish</button>`}
      ${D.status === "tayyor" ? `<a class="btn ${ro ? "primary" : ""}" id="tqDl" href="/api/taqdimot/decks/${D.id}/download">${ico("arrow", 15)} Yuklab olish (.pptx)</a>` : ""}
      ${ro ? "" : `<button type="button" class="btn ghost" id="tqDel">O'chirish</button>`}
      <span class="muted tiny" id="tqDirty"></span>
    </div>
    <div id="tqSlidesBox" class="tq-slides"></div>
    ${ro ? "" : `<div class="tq-add"><select id="tqAddType">${Object.entries(TQ.meta.types).map(([k, v]) => `<option value="${k}">${esc(v)}</option>`).join("")}</select><button type="button" class="btn sm" id="tqAdd">+ Slayd qo'shish</button></div>`}
  </div>`;
  $("#tqBack").onclick = () => { if (TQ.dirty && !confirm("Saqlanmagan o'zgarishlar bor. Chiqasizmi?")) return; TQ.deck = null; tqShell(); };
  el.querySelectorAll("[data-o]").forEach(i => i.oninput = () => { O[i.dataset.o] = i.value; tqMark(); });
  tqSlides();
  if (ro) return;
  $("#tqSave").onclick = () => tqSave($("#tqSave"));
  $("#tqBuild").onclick = async () => {
    const b = $("#tqBuild");
    if (TQ.dirty && !(await tqSave(null))) return;
    b.disabled = true; const old = b.innerHTML; b.innerHTML = "Yaratilmoqda…";
    try { TQ.deck = await tqApi(`/api/taqdimot/decks/${D.id}/build`, {}); TQ.dirty = false; toast(`Taqdimot tayyor: ${TQ.deck.slides} slayd`); tqEditor(); }
    catch (e) { toast(e.msg || "Xatolik"); if (b.isConnected) { b.disabled = false; b.innerHTML = old; } }
  };
  $("#tqRegen").onclick = async () => {
    const b = $("#tqRegen");
    if (!arm(b, TQ.dirty ? "Tahrirlar yo'qoladi — qayta tuzilsinmi?" : "Ha, qayta tuzish")) return;
    b.disabled = true; b.innerHTML = "Tuzilmoqda…";
    try { TQ.deck = await tqApi(`/api/taqdimot/decks/${D.id}/regenerate`, {}); TQ.meta.used += 1; TQ.dirty = false; toast("Reja qayta tuzildi"); tqEditor(); }
    catch (e) { toast(e.msg || "Xatolik"); if (b.isConnected) { b.disabled = false; b.innerHTML = `${ico("refresh", 15)} Qayta tuzish`; } }
  };
  $("#tqDel").onclick = async () => {
    const b = $("#tqDel");
    if (!arm(b, "Ha, o'chirish")) return;
    try { await tqApi(`/api/taqdimot/decks/${D.id}/delete`, {}); toast("Taqdimot o'chirildi"); TQ.deck = null; TQ.tab = "mine"; tqShell(); }
    catch (e) { toast(e.msg || "Xatolik"); }
  };
  $("#tqAdd").onclick = () => {
    const t = $("#tqAddType").value;
    O.slides.push({type: t, title: TQ.meta.types[t], text: "", highlight: "", subheading: "", bullets: [], columns: [], steps: [], answer: "", check: [], note: "", cards: [], image: 0, caption: "", notes: ""});
    tqMark(); tqSlides();
    $("#tqSlidesBox").lastElementChild?.scrollIntoView({behavior: "smooth", block: "center"});
  };
}

function tqMark() { TQ.dirty = true; const d = $("#tqDirty"); if (d) d.textContent = "Saqlanmagan o'zgarishlar bor"; }

async function tqSave(btn) {
  const D = TQ.deck;
  try {
    if (btn) btn.disabled = true;
    TQ.deck = await tqApi(`/api/taqdimot/decks/${D.id}/outline`, {outline: D.outline});
    TQ.dirty = false;
    if (btn) { toast("Reja saqlandi"); tqEditor(); }
    return true;
  } catch (e) { toast(e.msg || "Saqlab bo'lmadi"); return false; }
  finally { if (btn && btn.isConnected) btn.disabled = false; }
}

function tqField(s, f, i, ro) {
  const dis = ro ? "disabled" : "";
  const lbl = (s.type === "definition" && TQ_TEXT_FIELD[f]) || TQ_LBL[f];
  if (f === "bullets" || f === "check")
    return `<label class="wide">${esc(lbl)}<textarea data-f="${f}" data-k="lines" rows="${Math.min(8, Math.max(3, (s[f] || []).length + 1))}" ${dis}>${esc(tqLines(s[f]))}</textarea></label>`;
  if (f === "steps" || f === "cards")
    return `<label class="wide">${esc(lbl)}<textarea data-f="${f}" data-k="pairs" rows="${Math.min(8, Math.max(3, (s[f] || []).length + 1))}" ${dis}>${esc(tqPairs(s[f]))}</textarea></label>`;
  if (f === "columns") {
    const c = [0, 1].map(k => (s.columns || [])[k] || {title: "", bullets: []});
    return c.map((col, k) => `<div class="tq-col"><label>${k + 1}-ustun sarlavhasi<input data-col="${k}" data-ck="title" value="${esc(col.title)}" ${dis}></label>
      <label>Bandlar<textarea data-col="${k}" data-ck="bullets" rows="4" ${dis}>${esc(tqLines(col.bullets))}</textarea></label></div>`).join("");
  }
  if (f === "image") {
    const imgs = TQ.deck.image_list || [];
    if (!imgs.length) return `<p class="muted tiny wide">Materialda rasm yo'q.</p>`;
    return `<div class="wide"><span class="tq-lbl">${esc(lbl)}</span><div class="tq-imgs">${[{n: 0}].concat(imgs).map(im =>
      `<button type="button" class="tq-img ${+s.image === im.n ? "on" : ""}" data-img="${im.n}" ${dis} title="${esc(im.ctx || "")}">${im.n ? `<img src="/api/taqdimot/decks/${TQ.deck.id}/img/${im.n}" alt="${im.n}-rasm" loading="lazy"><span>${im.n}</span>` : "<span>Rasmsiz</span>"}</button>`).join("")}</div></div>`;
  }
  const big = f === "text" || f === "notes" || f === "note";
  return big ? `<label class="wide">${esc(lbl)}<textarea data-f="${f}" rows="${f === "text" ? 3 : 2}" ${dis}>${esc(s[f] || "")}</textarea></label>`
             : `<label class="wide">${esc(lbl)}<input data-f="${f}" value="${esc(s[f] || "")}" ${dis}></label>`;
}

function tqSlides() {
  const box = $("#tqSlidesBox"), O = TQ.deck.outline || {slides: []}, ro = !TQ.deck.can_edit, T = TQ.meta.types;
  box.innerHTML = O.slides.map((s, i) => `<section class="tq-slide" data-i="${i}">
    <div class="tq-sh"><span class="tq-n">${i + 1}</span>
      <select data-type ${ro ? "disabled" : ""} aria-label="Slayd turi">${Object.entries(T).map(([k, v]) => `<option value="${k}" ${s.type === k ? "selected" : ""}>${esc(v)}</option>`).join("")}</select>
      <input class="tq-stitle" data-f="title" value="${esc(s.title || "")}" placeholder="Slayd sarlavhasi" ${ro ? "disabled" : ""} aria-label="Slayd sarlavhasi">
      ${ro ? "" : `<span class="tq-sbtn"><button type="button" class="btn sm ghost" data-mv="-1" ${i ? "" : "disabled"} aria-label="Yuqoriga">↑</button><button type="button" class="btn sm ghost" data-mv="1" ${i < O.slides.length - 1 ? "" : "disabled"} aria-label="Pastga">↓</button><button type="button" class="btn sm ghost" data-del aria-label="O'chirish">✕</button></span>`}
    </div>
    <div class="tq-fields">${(TQ_FIELDS[s.type] || TQ_FIELDS.theory).map(f => tqField(s, f, i, ro)).join("")}</div>
  </section>`).join("") || `<div class="tq-empty">Rejada slayd yo'q</div>`;
  if (ro) return;
  box.querySelectorAll(".tq-slide").forEach(sec => {
    const i = +sec.dataset.i, s = O.slides[i];
    sec.querySelector("[data-type]").onchange = e => { s.type = e.target.value; tqMark(); tqSlides(); };
    sec.querySelectorAll("[data-f]").forEach(inp => inp.oninput = () => {
      const f = inp.dataset.f, k = inp.dataset.k;
      s[f] = k === "lines" ? tqSplitLines(inp.value) : (k === "pairs" ? tqSplitPairs(inp.value) : inp.value);
      tqMark();
    });
    sec.querySelectorAll("[data-col]").forEach(inp => inp.oninput = () => {
      s.columns = [0, 1].map(k => (s.columns || [])[k] || {title: "", bullets: []});
      const c = s.columns[+inp.dataset.col];
      if (inp.dataset.ck === "title") c.title = inp.value; else c.bullets = tqSplitLines(inp.value);
      tqMark();
    });
    sec.querySelectorAll("[data-img]").forEach(b => b.onclick = () => { s.image = +b.dataset.img; tqMark(); tqSlides(); });
    sec.querySelectorAll("[data-mv]").forEach(b => b.onclick = () => {
      const j = i + +b.dataset.mv; if (j < 0 || j >= O.slides.length) return;
      [O.slides[i], O.slides[j]] = [O.slides[j], O.slides[i]]; tqMark(); tqSlides();
    });
    sec.querySelector("[data-del]").onclick = () => {
      const removed = O.slides.splice(i, 1)[0]; tqMark(); tqSlides();
      undoToast(`«${removed.title || "Slayd"}» olib tashlandi`, () => {}, {onUndo: () => { O.slides.splice(i, 0, removed); tqSlides(); }});
    };
  });
}
