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

/* ---------- muharrir: PowerPoint uslubi — yuqorida slaydlar tasmasi, pastda bitta slayd (chapda maydonlar, o'ngda jonli ko'rinish) ---------- */
const TQ_ICO = {plan: "☰", definition: "Ⓣ", theory: "¶", two_column: "◫", steps: "①", example: "✎", image: "▣", tasks: "✓", questions: "?", summary: "∑", references: "📚"};
const TQ_BLANK = t => ({type: t, title: (TQ.meta.types || {})[t] || "", text: "", highlight: "", subheading: "", bullets: [], columns: [], steps: [], answer: "", check: [], note: "", cards: [], image: 0, caption: "", notes: ""});
const tqTyping = e => /^(INPUT|TEXTAREA|SELECT)$/.test(e.target?.tagName || "") || e.target?.isContentEditable;
/* taxminiy hajm: shablon 14pt dan kichraymaydi — ortiqcha matn «(davomi)» slaydiga bo'linadi */
function tqLoad(s) {
  const pair = a => (a || []).reduce((n, x) => n + (x.title || "").length + (x.text || "").length, 0);
  const chars = (s.text || "").length + (s.highlight || "").length + (s.answer || "").length + (s.note || "").length + (s.subheading || "").length
    + (s.bullets || []).join("").length + (s.check || []).join("").length + pair(s.steps) + pair(s.cards)
    + (s.columns || []).reduce((n, c) => n + (c.title || "").length + (c.bullets || []).join("").length, 0);
  const lines = (s.bullets || []).length + (s.check || []).length + (s.steps || []).length + (s.cards || []).length;
  return {chars, long: chars > 700 || lines > 9 || (s.cards || []).length > 6};
}
function tqRich(t) { return esc(t || "").replace(/\*\*(.+?)\*\*/g, "<b>$1</b>").replace(/\$([^$]+)\$/g, '<i class="tq-m">$1</i>'); }
function tqGrow(t) { t.style.height = "auto"; t.style.height = Math.min(t.scrollHeight + 2, 220) + "px"; }

function tqEditor() {
  const el = $("#v-taqdimot"), D = TQ.deck, O = D.outline || (D.outline = {slides: []}), ro = !D.can_edit;
  O.slides = O.slides || [];
  if (TQ.cur == null || TQ.cur >= O.slides.length) TQ.cur = 0;
  const st = TQ_ST[D.status] || [D.status, ""];
  const metaTxt = () => [O.subject, (O.topic_no ? O.topic_no + "-mavzu: " : "") + (O.title || "Mavzu nomi")].filter(Boolean).join(" · ");
  el.innerHTML = `<div class="tq-ed" id="tqEd">
    <div class="tq-bar">
      <button type="button" class="btn ghost sm" id="tqBack" title="Ro'yxatga qaytish">←</button>
      <div class="tq-meta"><button type="button" class="tq-meta-b" id="tqMetaB" ${ro ? "disabled" : ""} title="Fan, mavzu va titul satrini tahrirlash"><b id="tqMetaT">${esc(metaTxt())}</b>${ro ? "" : ico("pen", 13)}</button>
        <div class="tq-chips">${tqChip(st[0], st[1])}${tqChip(D.engine_label)}${D.truncated ? tqChip("material qisqartirildi", "warn") : ""}${D.pages ? tqChip(`≈ ${D.pages} slayd`) : ""}${ro ? tqChip("faqat ko'rish · " + (D.user_name || "").split(":").pop().trim(), "warn") : ""}</div>
        <div class="tq-pop" id="tqMetaP" hidden><div class="tq-grid">
          <label>Fan nomi<input data-o="subject" value="${esc(O.subject || "")}" maxlength="120"></label>
          <label>Mavzu raqami<input data-o="topic_no" value="${esc(O.topic_no || "")}" maxlength="20"></label>
          <label class="wide">Mavzu nomi<input data-o="title" value="${esc(O.title || "")}" maxlength="200"></label>
          <label class="wide">Qo'shimcha satr (titulda)<input data-o="subtitle" value="${esc(O.subtitle || "")}" maxlength="200"></label></div>
          <div class="tq-acts"><button type="button" class="btn sm primary" id="tqMetaOk">Tayyor</button></div></div></div>
      <div class="tq-bar-r">
        ${ro ? "" : `<button type="button" class="btn sm" id="tqSave">Saqlash<i class="tq-dirty" id="tqDirty" ${TQ.dirty ? "" : "hidden"} title="Saqlanmagan o'zgarishlar bor"></i></button>
        <button type="button" class="btn sm ghost" id="tqRegen" title="Material asosida rejani qaytadan tuzish (kunlik cheklovga kiradi)">${ico("refresh", 14)} Qayta tuzish</button>
        <button type="button" class="btn sm primary" id="tqBuild">${ico("report", 14)} PPTX yaratish</button>`}
        ${D.status === "tayyor" ? `<a class="btn sm ${ro ? "primary" : ""}" id="tqDl" href="/api/taqdimot/decks/${D.id}/download">${ico("arrow", 14)} Yuklab olish</a>` : ""}
        ${ro ? "" : `<button type="button" class="btn sm ghost" id="tqDel" title="Taqdimotni o'chirish">O'chirish</button>`}
      </div>
    </div>
    <div class="tq-strip" id="tqStrip" role="listbox" aria-label="Slaydlar"></div>
    <div class="tq-main">
      <div class="tq-form" id="tqForm"></div>
      <div class="tq-side"><div class="tq-prev" id="tqPrev"></div>
        <div class="tq-pn"><button type="button" class="btn sm ghost" id="tqPv">‹ Oldingi</button><span class="muted tiny" id="tqPos"></span><button type="button" class="btn sm ghost" id="tqNx">Keyingi ›</button></div>
        <p class="muted tiny tq-keys">←/→ yoki PgUp/PgDn — slaydlar orasida · sichqoncha bilan sudrab tartiblang · o'ng tugma — menyu</p></div>
    </div>
    <div class="tq-menu" id="tqMenu" hidden></div>
  </div>`;
  $("#tqBack").onclick = () => { if (TQ.dirty && !confirm("Saqlanmagan o'zgarishlar bor. Chiqasizmi?")) return; TQ.deck = null; TQ.cur = 0; tqShell(); };
  $("#tqPv").onclick = () => tqGo(TQ.cur - 1);
  $("#tqNx").onclick = () => tqGo(TQ.cur + 1);
  tqStrip(); tqSlide();
  if (ro) return;
  const pop = $("#tqMetaP");
  $("#tqMetaB").onclick = () => { pop.hidden = !pop.hidden; if (!pop.hidden) pop.querySelector("input")?.focus(); };
  $("#tqMetaOk").onclick = () => { pop.hidden = true; };
  el.querySelectorAll("[data-o]").forEach(i => i.oninput = () => { O[i.dataset.o] = i.value; $("#tqMetaT").textContent = metaTxt(); tqMark(); });
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
    try { TQ.deck = await tqApi(`/api/taqdimot/decks/${D.id}/regenerate`, {}); TQ.meta.used += 1; TQ.dirty = false; TQ.cur = 0; toast("Reja qayta tuzildi"); tqEditor(); }
    catch (e) { toast(e.msg || "Xatolik"); if (b.isConnected) { b.disabled = false; b.innerHTML = `${ico("refresh", 14)} Qayta tuzish`; } }
  };
  $("#tqDel").onclick = async () => {
    const b = $("#tqDel");
    if (!arm(b, "Ha, o'chirish")) return;
    try { await tqApi(`/api/taqdimot/decks/${D.id}/delete`, {}); toast("Taqdimot o'chirildi"); TQ.deck = null; TQ.tab = "mine"; tqShell(); }
    catch (e) { toast(e.msg || "Xatolik"); }
  };
}

function tqMark() { TQ.dirty = true; const d = $("#tqDirty"); if (d) d.hidden = false; }

async function tqSave(btn) {
  const D = TQ.deck;
  try {
    if (btn) btn.disabled = true;
    TQ.deck = await tqApi(`/api/taqdimot/decks/${D.id}/outline`, {outline: D.outline});
    TQ.dirty = false;
    if (btn) { toast("Reja saqlandi"); tqEditor(); } else { const d = $("#tqDirty"); if (d) d.hidden = true; }
    return true;
  } catch (e) { toast(e.msg || "Saqlab bo'lmadi"); return false; }
  finally { if (btn && btn.isConnected) btn.disabled = false; }
}

function tqGo(i) {
  const n = (TQ.deck?.outline?.slides || []).length; if (!n) return;
  TQ.cur = Math.max(0, Math.min(n - 1, i)); tqStrip(); tqSlide();
  $("#tqStrip .tq-th.on")?.scrollIntoView({block: "nearest", inline: "nearest"});
}

/* yuqoridagi tasma: raqam, tur belgisi, sarlavha; sudrab tartiblash; o'ng tugma / ⋯ — menyu; oxirida «+» */
function tqStrip() {
  const box = $("#tqStrip"); if (!box) return;
  const O = TQ.deck.outline, ro = !TQ.deck.can_edit, T = TQ.meta.types;
  box.innerHTML = O.slides.map((s, i) => { const L = tqLoad(s);
    return `<div class="tq-th ${i === TQ.cur ? "on" : ""}" data-i="${i}" role="option" aria-selected="${i === TQ.cur}" tabindex="${i === TQ.cur ? 0 : -1}" ${ro ? "" : 'draggable="true"'} title="${esc((T[s.type] || s.type) + " — " + (s.title || ""))}">
      <span class="tq-th-n">${i + 1}</span><span class="tq-th-i" aria-hidden="true">${TQ_ICO[s.type] || "¶"}</span>
      ${ro ? "" : `<button type="button" class="tq-th-m" data-m="${i}" aria-label="Slayd menyusi">⋯</button>`}
      <b>${esc(s.title || T[s.type] || "Slayd")}</b><small>${esc(T[s.type] || s.type)}</small>
      ${L.long ? `<span class="tq-th-w" title="Matn uzun — PPTX'da «(davomi)» slaydiga bo'linadi">uzun → bo'linadi</span>` : ""}</div>`; }).join("")
    + (ro ? "" : `<button type="button" class="tq-th tq-th-add" id="tqAdd" title="Slayd qo'shish">+<small>Slayd qo'shish</small></button>`)
    || `<div class="tq-empty">Rejada slayd yo'q</div>`;
  box.querySelectorAll(".tq-th[data-i]").forEach(th => {
    const i = +th.dataset.i;
    th.onclick = e => { if (e.target.closest("[data-m]")) return; tqGo(i); };
    if (ro) return;
    th.oncontextmenu = e => { e.preventDefault(); tqMenu(i, e.clientX, e.clientY); };
    th.querySelector("[data-m]").onclick = e => { e.stopPropagation(); const r = e.target.getBoundingClientRect(); tqMenu(i, r.left, r.bottom + 4); };
    th.ondragstart = e => { e.dataTransfer.setData("text/plain", String(i)); e.dataTransfer.effectAllowed = "move"; th.classList.add("drag"); };
    th.ondragend = () => th.classList.remove("drag");
    th.ondragover = e => { e.preventDefault(); th.classList.add("over"); };
    th.ondragleave = () => th.classList.remove("over");
    th.ondrop = e => {
      e.preventDefault(); th.classList.remove("over");
      const from = +e.dataTransfer.getData("text/plain"); if (Number.isNaN(from) || from === i) return;
      const sl = TQ.deck.outline.slides, [m] = sl.splice(from, 1); sl.splice(i, 0, m);
      TQ.cur = i; tqMark(); tqStrip(); tqSlide();
    };
  });
  $("#tqAdd")?.addEventListener("click", e => { const r = e.currentTarget.getBoundingClientRect(); tqMenu(-1, r.left, r.bottom + 4); });
}

/* kontekst menyu: nusxa, tur, o'chirish (i=-1 — yangi slayd turi tanlash) */
function tqMenu(i, x, y) {
  const m = $("#tqMenu"), O = TQ.deck.outline, T = TQ.meta.types;
  const types = Object.entries(T).map(([k, v]) => `<button type="button" data-t="${k}">${TQ_ICO[k] || ""} ${esc(v)}</button>`).join("");
  m.innerHTML = i < 0 ? `<div class="tq-menu-h">Yangi slayd turi</div>${types}`
    : `<button type="button" data-a="dup">Nusxa olish</button><button type="button" data-a="left" ${i ? "" : "disabled"}>← Chapga surish</button><button type="button" data-a="right" ${i < O.slides.length - 1 ? "" : "disabled"}>O'ngga surish →</button>
       <div class="tq-menu-h">Turini o'zgartirish</div>${types}<hr><button type="button" data-a="del" class="bad">O'chirish</button>`;
  m.hidden = false;
  const W = 230, H = Math.min(m.scrollHeight, window.innerHeight - 20);
  m.style.left = Math.max(8, Math.min(x, window.innerWidth - W - 8)) + "px"; m.style.top = Math.max(8, Math.min(y, window.innerHeight - H - 8)) + "px";
  const close = () => { m.hidden = true; document.removeEventListener("mousedown", out, true); };
  const out = e => { if (!m.contains(e.target)) close(); };
  setTimeout(() => document.addEventListener("mousedown", out, true));
  m.querySelectorAll("[data-t]").forEach(b => b.onclick = () => {
    close();
    if (i < 0) { O.slides.splice(TQ.cur + 1, 0, TQ_BLANK(b.dataset.t)); TQ.cur = O.slides.length > 1 ? TQ.cur + 1 : 0; }
    else O.slides[i].type = b.dataset.t;
    tqMark(); tqStrip(); tqSlide();
  });
  m.querySelectorAll("[data-a]").forEach(b => b.onclick = () => {
    close(); const a = b.dataset.a;
    if (a === "dup") { O.slides.splice(i + 1, 0, JSON.parse(JSON.stringify(O.slides[i]))); TQ.cur = i + 1; }
    if (a === "left" || a === "right") { const j = i + (a === "left" ? -1 : 1); [O.slides[i], O.slides[j]] = [O.slides[j], O.slides[i]]; TQ.cur = j; }
    if (a === "del") {
      const removed = O.slides.splice(i, 1)[0]; TQ.cur = Math.min(i, Math.max(0, O.slides.length - 1));
      undoToast(`«${removed.title || "Slayd"}» olib tashlandi`, () => {}, {onUndo: () => { O.slides.splice(i, 0, removed); TQ.cur = i; tqStrip(); tqSlide(); }});
    }
    tqMark(); tqStrip(); tqSlide();
  });
}

function tqField(s, f, ro) {
  const dis = ro ? "disabled" : "";
  const lbl = (s.type === "definition" && TQ_TEXT_FIELD[f]) || TQ_LBL[f];
  const ta = (val, attrs) => `<textarea class="tq-ag" rows="2" ${attrs} ${dis}>${esc(val)}</textarea>`;
  if (f === "notes") return `<details class="wide tq-notes" ${s.notes ? "" : ""}><summary>${esc(lbl)}${s.notes ? " ·" : ""}</summary>${ta(s.notes || "", 'data-f="notes"')}</details>`;
  if (f === "bullets" || f === "check") return `<label class="wide">${esc(lbl)}${ta(tqLines(s[f]), `data-f="${f}" data-k="lines"`)}</label>`;
  if (f === "steps" || f === "cards") return `<label class="wide">${esc(lbl)}${ta(tqPairs(s[f]), `data-f="${f}" data-k="pairs"`)}</label>`;
  if (f === "columns") {
    const c = [0, 1].map(k => (s.columns || [])[k] || {title: "", bullets: []});
    return c.map((col, k) => `<div class="tq-col"><label>${k + 1}-ustun sarlavhasi<input data-col="${k}" data-ck="title" value="${esc(col.title)}" ${dis}></label>
      <label>Bandlar<textarea class="tq-ag" rows="2" data-col="${k}" data-ck="bullets" ${dis}>${esc(tqLines(col.bullets))}</textarea></label></div>`).join("");
  }
  if (f === "image") {
    const imgs = TQ.deck.image_list || [];
    if (!imgs.length) return `<p class="muted tiny wide">Materialda rasm yo'q.</p>`;
    return `<div class="wide"><span class="tq-lbl">${esc(lbl)}</span><div class="tq-imgs">${[{n: 0}].concat(imgs).map(im =>
      `<button type="button" class="tq-img ${+s.image === im.n ? "on" : ""}" data-img="${im.n}" ${dis} title="${esc(im.ctx || "")}">${im.n ? `<img src="/api/taqdimot/decks/${TQ.deck.id}/img/${im.n}" alt="${im.n}-rasm" loading="lazy"><span>${im.n}</span>` : "<span>Rasmsiz</span>"}</button>`).join("")}</div></div>`;
  }
  if (f === "text" || f === "note") return `<label class="wide">${esc(lbl)}${ta(s[f] || "", `data-f="${f}"`)}</label>`;
  return `<label class="wide">${esc(lbl)}<input data-f="${f}" value="${esc(s[f] || "")}" ${dis}></label>`;
}

/* bitta slayd: chapda faqat shu tur maydonlari, o'ngda jonli ko'rinish */
function tqSlide() {
  const form = $("#tqForm"); if (!form) return;
  const O = TQ.deck.outline, ro = !TQ.deck.can_edit, T = TQ.meta.types, s = O.slides[TQ.cur];
  $("#tqPos").textContent = O.slides.length ? `${TQ.cur + 1} / ${O.slides.length}` : "";
  $("#tqPv").disabled = TQ.cur <= 0; $("#tqNx").disabled = TQ.cur >= O.slides.length - 1;
  if (!s) { form.innerHTML = `<div class="tq-empty">Rejada slayd yo'q${ro ? "" : " — yuqoridagi «+» bilan qo'shing"}</div>`; $("#tqPrev").innerHTML = ""; return; }
  const L = tqLoad(s);
  form.innerHTML = `<div class="tq-fh"><span class="tq-n">${TQ.cur + 1}</span>
      <select data-type ${ro ? "disabled" : ""} aria-label="Slayd turi">${Object.entries(T).map(([k, v]) => `<option value="${k}" ${s.type === k ? "selected" : ""}>${esc(v)}</option>`).join("")}</select>
      <input class="tq-stitle" data-f="title" value="${esc(s.title || "")}" placeholder="Slayd sarlavhasi" ${ro ? "disabled" : ""} aria-label="Slayd sarlavhasi"></div>
    ${L.long ? `<div class="tq-warn">${ico("info", 14)} Matn uzun (~${L.chars} belgi) — PPTX'da shrift 14pt dan kichraymaydi, davomi keyingi slaydga o'tadi. Qisqartiring yoki slaydni ikkiga bo'ling.</div>` : ""}
    <div class="tq-fields">${(TQ_FIELDS[s.type] || TQ_FIELDS.theory).map(f => tqField(s, f, ro)).join("")}</div>`;
  form.scrollTop = 0;
  form.querySelectorAll("textarea.tq-ag").forEach(tqGrow);
  form.querySelector("details.tq-notes")?.addEventListener("toggle", e => e.target.querySelectorAll("textarea").forEach(tqGrow));
  tqPreview();
  if (ro) return;
  const live = () => { tqMark(); tqPreview(); tqThumb(); };
  form.querySelector("[data-type]").onchange = e => { s.type = e.target.value; tqMark(); tqStrip(); tqSlide(); };
  form.querySelectorAll("[data-f]").forEach(inp => inp.oninput = () => {
    const f = inp.dataset.f, k = inp.dataset.k;
    s[f] = k === "lines" ? tqSplitLines(inp.value) : (k === "pairs" ? tqSplitPairs(inp.value) : inp.value);
    if (inp.tagName === "TEXTAREA") tqGrow(inp);
    live();
  });
  form.querySelectorAll("[data-col]").forEach(inp => inp.oninput = () => {
    s.columns = [0, 1].map(k => (s.columns || [])[k] || {title: "", bullets: []});
    const c = s.columns[+inp.dataset.col];
    if (inp.dataset.ck === "title") c.title = inp.value; else { c.bullets = tqSplitLines(inp.value); tqGrow(inp); }
    live();
  });
  form.querySelectorAll("[data-img]").forEach(b => b.onclick = () => { s.image = +b.dataset.img; tqMark(); tqSlide(); });
}

/* tasmadagi joriy plitkani yangilash (butun tasmani qayta chizmasdan — fokus yo'qolmasin) */
function tqThumb() {
  const s = TQ.deck.outline.slides[TQ.cur], th = $(`#tqStrip .tq-th[data-i="${TQ.cur}"]`); if (!s || !th) return;
  th.querySelector("b").textContent = s.title || TQ.meta.types[s.type] || "Slayd";
  const L = tqLoad(s), w = th.querySelector(".tq-th-w");
  if (L.long && !w) th.insertAdjacentHTML("beforeend", `<span class="tq-th-w" title="Matn uzun — PPTX'da «(davomi)» slaydiga bo'linadi">uzun → bo'linadi</span>`);
  if (!L.long && w) w.remove();
}

/* jonli ko'rinish — ISFT shabloni: qizil sarlavha paneli, chap tomon bo'sh (logotip), kontent o'ngda */
function tqPreview() {
  const box = $("#tqPrev"), s = TQ.deck.outline.slides[TQ.cur]; if (!box) return;
  if (!s) { box.innerHTML = ""; return; }
  const li = a => (a || []).filter(Boolean).slice(0, 9).map(x => `<li>${tqRich(x)}</li>`).join("");
  const pairs = (a, cls) => (a || []).slice(0, 6).map((x, k) => `<div class="${cls}"><b>${cls === "pv-step" ? `<i>${k + 1}</i>` : ""}${tqRich(x.title)}</b> ${tqRich(x.text)}</div>`).join("");
  let body = "";
  switch (s.type) {
    case "plan": case "references": body = `<ol class="pv-ol">${li(s.bullets)}</ol>`; break;
    case "questions": body = `<div class="pv-q">${(s.bullets || []).slice(0, 8).map((q, k) => `<div><i>${k + 1}</i>${tqRich(q)}</div>`).join("")}</div>`; break;
    case "two_column": body = `${s.text ? `<p>${tqRich(s.text)}</p>` : ""}<div class="pv-2">${(s.columns || []).slice(0, 2).map(c => `<div class="pv-card"><b>${tqRich(c.title)}</b><ul>${li(c.bullets)}</ul></div>`).join("")}</div>`; break;
    case "steps": body = `${s.text ? `<p>${tqRich(s.text)}</p>` : ""}${pairs(s.steps, "pv-step")}`; break;
    case "example": body = `${s.text ? `<div class="pv-card pv-def"><b>Shart.</b> ${tqRich(s.text)}</div>` : ""}<div class="pv-2"><div>${pairs(s.steps, "pv-step")}</div>
        <div>${s.answer ? `<div class="pv-hl"><b>Javob</b><br>${tqRich(s.answer)}</div>` : ""}${(s.check || []).length ? `<div class="pv-card pv-grey"><b>Tekshiruv</b><ul>${li(s.check)}</ul></div>` : ""}</div></div>
        ${s.note ? `<div class="pv-note">${tqRich(s.note)}</div>` : ""}`; break;
    case "image": { const n = +s.image;
      body = `<div class="pv-2"><div>${s.text ? `<p>${tqRich(s.text)}</p>` : ""}<ul>${li(s.bullets)}</ul></div>
        <div class="pv-img">${n ? `<img src="/api/taqdimot/decks/${TQ.deck.id}/img/${n}" alt="">` : "<span>Rasm tanlanmagan</span>"}${s.caption ? `<small>${tqRich(s.caption)}</small>` : ""}</div></div>`; break; }
    case "tasks": case "summary": body = `${s.text ? `<p>${tqRich(s.text)}</p>` : ""}<div class="pv-grid">${(s.cards || []).slice(0, 6).map(c => `<div class="pv-card"><b>${tqRich(c.title)}</b><br>${tqRich(c.text)}</div>`).join("")}</div>`; break;
    default: body = `${s.text ? `<div class="pv-card ${s.type === "definition" ? "pv-def" : ""}">${tqRich(s.text)}</div>` : ""}${s.highlight ? `<div class="pv-hl">${tqRich(s.highlight)}</div>` : ""}
        ${s.subheading ? `<div class="pv-sub">${tqRich(s.subheading)}</div>` : ""}<ul>${li(s.bullets)}</ul>`;
  }
  box.innerHTML = `<div class="pv"><div class="pv-bar">${tqRich(s.title || "")}</div><div class="pv-logo" aria-hidden="true"></div><div class="pv-body">${body}</div></div>`;
}

/* klaviatura: ←/→ (maydon tashqarisida), PgUp/PgDn (har doim) */
document.addEventListener("keydown", e => {
  const ed = $("#tqEd"); if (!ed || !ed.offsetParent || e.altKey || e.ctrlKey || e.metaKey) return;
  if (e.key === "Escape") { const m = $("#tqMenu"); if (m && !m.hidden) m.hidden = true; const p = $("#tqMetaP"); if (p && !p.hidden) p.hidden = true; return; }
  if (e.key === "PageUp" || e.key === "PageDown") { e.preventDefault(); tqGo(TQ.cur + (e.key === "PageDown" ? 1 : -1)); return; }
  if (tqTyping(e)) return;
  if (e.key === "ArrowLeft" || e.key === "ArrowRight") { e.preventDefault(); tqGo(TQ.cur + (e.key === "ArrowRight" ? 1 : -1)); $("#tqStrip .tq-th.on")?.focus(); }
});
