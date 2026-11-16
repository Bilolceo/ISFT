/* =====================================================================
   «Taqdimot» — o'qituvchi uchun ISFT shablonida taqdimot (app/taqdimot.py, /api/taqdimot).
     1) material: Word / PDF / matn → 2) reja (AI: Claude yoki AI siz) → 3) rejani tahrirlash → 4) .pptx yuklab olish.
   «Mening taqdimotlarim» — tarix; kafedra mudiri — «Kafedra taqdimotlari» (faqat ko'rish va yuklab olish).
   DARS KODI: fan/mavzu qo'lda yozilmaydi — dars tanlanadi (kurs → yo'nalish → fan → dars; faqat o'z fanlari, lesson_picker.js). Tayyor taqdimot BITTA tugma bilan
   «Studiyaga va masofaviy bo'limga yuboriladi»: dars kodi o'zgarmaydi, versiya oshadi (v1 → v2), tarixda qoladi. Bog'lanmagan eski taqdimot — «Darsni belgilash».
   Global: renderTaqdimot() — app.js go() chaqiradi. app.js yordamchilari: $, esc, toast, arm, ico, dmy.
   ===================================================================== */
const TQ = {meta: null, tab: "new", deck: null, dirty: false, src: "file", file: null, lessons: null, pick: null, later: false, text: "", stale: false};
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
const tqChip = (t, cls = "", title = "") => `<span class="tq-chip ${cls}" title="${esc(title || t)}">${esc(t)}</span>`;
/* AI ulanmagan bo'lsa serverning texnik nomi o'qituvchiga tushunarsiz — aniq nom */
const tqEngLbl = (engine, label) => engine === "claude" ? (label || "AI") : engine === "fake" ? "Sinov rejimi" : "Shablon asosida";
const tqEngTitle = engine => engine === "claude" ? "Reja AI yordamida tuzilgan" : engine === "fake" ? "Sinov rejimi: reja soxta AI bilan tuziladi" : "AI ulanmagan: reja Word sarlavhalaridan (shablon bo'yicha) tuziladi";
const tqDT = s => { const t = String(s || "").replace(" ", "T"); return t.length >= 16 ? {d: `${t.slice(8, 10)}.${t.slice(5, 7)}.${t.slice(0, 4)}`, h: t.slice(11, 16), day: t.slice(0, 10)} : null; };
/* «14:20» (bugun) yoki «15.11.2026, 14:20» */
function tqWhen(s) { const x = tqDT(s); if (!x) return ""; const today = new Date(); const iso = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, "0")}-${String(today.getDate()).padStart(2, "0")}`; return x.day === iso ? x.h : `${x.d}, ${x.h}`; }
const tqSize = n => n >= 1048576 ? (n / 1048576).toFixed(1) + " MB" : Math.max(1, Math.round(n / 1024)) + " KB";
/* tugma band: ikki marta bosish va yuklanish holati (aria-busy) */
function tqBusy(b, on, txt) {
  if (!b) return;
  if (on) { b._tqOld = b.innerHTML; b.setAttribute("aria-busy", "true"); b.disabled = true; if (txt) b.textContent = txt; }
  else { b.removeAttribute("aria-busy"); if (b.isConnected) { b.disabled = false; if (b._tqOld != null) b.innerHTML = b._tqOld; } b._tqOld = null; }
}
/* tablist: ←/→/Home/End — fokus va tanlov birga ko'chadi */
function tqTabKeys(box) {
  box.addEventListener("keydown", e => {
    if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(e.key)) return;
    const bs = [...box.querySelectorAll('[role="tab"]')], i = bs.indexOf(document.activeElement); if (i < 0) return;
    e.preventDefault(); const j = e.key === "Home" ? 0 : e.key === "End" ? bs.length - 1 : (i + (e.key === "ArrowRight" ? 1 : -1) + bs.length) % bs.length;
    bs[j].focus(); bs[j].click();
  });
}
const tqLines = a => (a || []).join("\n");
const tqPairs = a => (a || []).map(x => (x.title ? x.title + " | " : "") + (x.text || "")).join("\n");
const tqSplitLines = s => String(s || "").split("\n").map(x => x.trim()).filter(Boolean);
const tqSplitPairs = s => tqSplitLines(s).map(l => { const i = l.indexOf("|"); return i < 0 ? {title: "", text: l} : {title: l.slice(0, i).trim(), text: l.slice(i + 1).trim()}; });

async function renderTaqdimot() {
  const el = $("#v-taqdimot");
  if (TQ.deck && TQ.dirty && $("#tqEd")) return;                 /* saqlanmagan tahrir — serverdan qayta o'qib YO'QOTMAYMIZ */
  if (!el.innerHTML) el.innerHTML = `<p class="muted">Yuklanmoqda…</p>`;
  try { TQ.meta = await tqApi("/api/taqdimot/meta"); }
  catch (e) { el.innerHTML = e.message === "denied" ? `<div class="card tq-empty">${esc(e.msg)}</div>` : errCard("taqdimot"); return; }
  TQ.lessons = null; TQ.stale = false;
  try { TQ.lessons = await tqApi("/api/taqdimot/lessons"); } catch (e) { TQ.lessons = {items: []}; }
  if (!TQ.deck) { const id = tqSavedId(); if (id) return tqOpen(id, true); }      /* sahifa yangilangan — ochiq muharrir tiklanadi */
  if (TQ.deck) return tqOpen(TQ.deck.id);
  tqShell();
}

/* ochiq muharrir (deck id) yangilashdan keyin tiklanadi: sessionStorage + #taqdimot/<id> (app.js go() birinchi chaqiruvida shu xeshni ko'radi) */
function tqSavedId() { try { return +sessionStorage.getItem("tqDeck") || 0; } catch (e) { return 0; } }
function tqRemember(id) {
  try { id ? sessionStorage.setItem("tqDeck", String(id)) : sessionStorage.removeItem("tqDeck"); } catch (e) {}
  try { history.replaceState(null, "", id ? `#taqdimot/${id}` : location.pathname + location.search); } catch (e) {}
}
/* app.js go() ilgagi: false — o'tma. Saqlanmagan tahrir bo'lsa tasdiq so'raladi (boshqa bo'limga o'tishda; «Taqdimot»ning o'ziga qayta kirish — tahrirni yo'qotmaydi) */
window.tqBeforeLeave = function (v) {
  if (v === "taqdimot" || !TQ.dirty || !$("#tqEd")) return true;
  if (!confirm("Taqdimotda saqlanmagan o'zgarishlar bor. Baribir boshqa bo'limga o'tasizmi? (o'zgarishlar yo'qoladi)")) return false;
  TQ.dirty = false; tqRemember(0); return true;
};
/* sahifa yangilandi: #taqdimot/<id> bo'lsa, kirish tayyor bo'lgach «Taqdimot» bo'limi (renderTaqdimot muharrirni tiklaydi) ochiladi */
(function tqRestoreOnLoad() {
  const m = /^#taqdimot\/(\d+)$/.exec(location.hash || "");
  if (!m || +m[1] !== tqSavedId()) return;
  let n = 0;
  const t = setInterval(() => {
    if (typeof ME !== "undefined" && ME && $("#app") && !$("#app").classList.contains("hidden")) { clearInterval(t); setTimeout(() => go("taqdimot"), 80); }
    else if (++n > 150) clearInterval(t);
  }, 100);
})();
window.addEventListener("beforeunload", e => { if (TQ.dirty && $("#tqEd")) { e.preventDefault(); e.returnValue = ""; } });

function tqHead() {
  const M = TQ.meta;
  const eng = tqChip(tqEngLbl(M.engine, M.label), M.engine === "claude" ? "ok" : (M.engine === "fake" ? "warn" : ""), tqEngTitle(M.engine));
  return `<div class="tq-head"><div><h2>Taqdimot tayyorlash</h2>
      <span class="muted">Ma'ruza materialini yuklang — tizim ISFT shablonida taqdimot rejasini tuzadi, siz tahrirlaysiz va .pptx yuklab olasiz.</span></div>
    <div class="tq-head-r"><span class="tq-eng">${eng}</span>${tqChip(`Bugungi limit: ${M.used} / ${M.limit}`, M.used >= M.limit ? "bad" : "", `Bugungi reja tuzish limiti: ${M.used} ta ishlatilgan, ${M.limit} tadan (har kuni yangilanadi)`)}</div></div>`;
}

async function tqShell() {
  const el = $("#v-taqdimot"), M = TQ.meta;
  if (TQ.stale) { TQ.stale = false; try { TQ.lessons = await tqApi("/api/taqdimot/lessons"); } catch (e) {} }     /* yuborilgan / o'chirilgan taqdimotdan keyin «bu darsga taqdimot bor» yangilansin */
  const tabs = [["new", "Yangi taqdimot"], ["mine", "Mening taqdimotlarim"]].concat(M.mode === "dept" ? [["dept", "Kafedra taqdimotlari"]] : []);
  el.innerHTML = tqHead() + `<div class="tq-tabs" role="tablist" aria-label="Taqdimot bo'limlari">${tabs.map(([k, l]) => `<button type="button" role="tab" id="tqTab_${k}" data-t="${k}" class="${TQ.tab === k ? "on" : ""}" aria-selected="${TQ.tab === k}" tabindex="${TQ.tab === k ? 0 : -1}" aria-controls="tqBody">${esc(l)}</button>`).join("")}</div><div id="tqBody" role="tabpanel" aria-labelledby="tqTab_${TQ.tab}"></div>`;
  el.querySelectorAll(".tq-tabs button").forEach(b => b.onclick = async () => { TQ.tab = b.dataset.t; await tqShell(); $(`#tqTab_${TQ.tab}`)?.focus(); });
  tqTabKeys(el.querySelector(".tq-tabs"));
  if (TQ.tab === "new") tqNew(); else tqList(TQ.tab);
}

const TQ_NO_LESSON = "Sizga hali fan biriktirilmagan. Taqdimotni hozir darssiz yaratishingiz mumkin; fan biriktirilgach «Darsni belgilash» orqali bog'laysiz. Fan biriktirish uchun kafedra mudiriga murojaat qiling.";
const TQ_EXT = /\.(docx|pdf|txt)$/i;

/* xatoni toastdan tashqari sahifada ham qoldiramiz (toast 4 soniyada yo'qoladi): #tqProg ichida role="alert" */
function tqErr(msg) {
  toast(msg);
  const pr = $("#tqProg"); if (!pr) return;
  pr.hidden = false; pr.classList.add("err");
  pr.innerHTML = `<span role="alert">${ico("alert", 16)} ${esc(msg)}</span>`;
}
const tqErrClear = () => { const pr = $("#tqProg"); if (pr) { pr.classList.remove("err"); if (!pr.querySelector(".tq-spin")) { pr.hidden = true; pr.innerHTML = ""; } } };

function tqDupHint() {
  const el = $("#tqDup"); if (!el) return;
  const p = TQ.pick, ds = (!$("#tqLater")?.checked && p?.lesson?.decks) || [];
  if (!ds.length) { el.innerHTML = ""; return; }
  const code = p.lesson.code;
  el.innerHTML = `<div class="tq-warn">${ico("info", 14)}<span>${esc(code)} uchun ${ds.slice(0, 2).map(d => `«${esc(d.title || "Nomsiz taqdimot")}»`).join(", ")}${ds.length > 2 ? ` va yana ${ds.length - 2} ta` : ""} taqdimot bor.
    <span class="tq-dup-a">${ds.slice(0, 3).map(d => `<button type="button" class="btn sm" data-open="${d.id}" title="${esc(d.title || "")}">Uni oching${ds.length > 1 ? ` (${esc((d.title || "#" + d.id).slice(0, 24))})` : ""}</button>`).join("")}</span>
    Yoki baribir yangisini yarating — pastdan davom eting.</span></div>`;
  el.querySelectorAll("[data-open]").forEach(b => b.onclick = () => tqOpen(+b.dataset.open));
}

function tqNew() {
  const M = TQ.meta, box = $("#tqBody"), items = (TQ.lessons || {}).items || [], noLes = !items.length;
  const noAi = M.engine !== "claude";
  box.innerHTML = `<div class="card tq-card">
    ${noAi ? `<div class="tq-note">${ico("info", 16)}<span>${M.engine === "fake" ? "Sinov rejimi: reja soxta AI bilan tuziladi." : "Reja Word sarlavhalaridan tuziladi. Sarlavhali fayl eng yaxshi natija beradi."}</span></div>` : ""}
    <section class="tq-sec" aria-labelledby="tqLpH"><h3 class="tq-h" id="tqLpH">1-qadam. Qaysi dars uchun?</h3>
      ${noLes ? `<div class="tq-note warn" id="tqNoLes" role="status">${ico("info", 16)}<span>${esc(TQ_NO_LESSON)}</span></div>`
        : `<p class="muted tiny">Fan, kafedra va o'qituvchi darsdan avtomatik olinadi — qo'lda yozilmaydi. Faqat o'z yuklamangizdagi fanlar chiqadi.</p>
      <div id="tqLp"></div><div id="tqDup" role="status"></div>
      <label class="tq-cb"><input type="checkbox" id="tqLater" ${TQ.later ? "checked" : ""}> Darsni keyinroq belgilayman <small>(taqdimot darssiz yaratiladi; «Darsni belgilash» tugmasi bilan keyin bog'lanadi)</small></label>`}</section>
    <section class="tq-sec" aria-labelledby="tqSrcH"><h3 class="tq-h" id="tqSrcH">2-qadam. Material</h3>
      <div class="tq-seg" role="tablist" aria-label="Material manbai"><button type="button" role="tab" id="tqSeg_file" data-s="file" class="${TQ.src === "file" ? "on" : ""}" aria-selected="${TQ.src === "file"}" tabindex="${TQ.src === "file" ? 0 : -1}" aria-controls="tqSrc">Fayl yuklash</button><button type="button" role="tab" id="tqSeg_text" data-s="text" class="${TQ.src === "text" ? "on" : ""}" aria-selected="${TQ.src === "text"}" tabindex="${TQ.src === "text" ? 0 : -1}" aria-controls="tqSrc">Matn yozish</button></div>
      <div id="tqSrc" role="tabpanel"></div></section>
    <section class="tq-sec last" aria-labelledby="tqSetH"><h3 class="tq-h" id="tqSetH">3-qadam. Sozlamalar</h3>
    <div class="tq-grid">
      <label class="wide">Mavzu nomi <small>(bo'sh qolsa — materialdan olinadi)</small><input id="tqTitle" maxlength="200" value="${esc(TQ.titleV || "")}"></label>
      <label>Slaydlar soni<select id="tqSlides"><option value="">Avtomatik (kontentga qarab)</option>${[8, 10, 12, 15, 18, 20, 25, 30].map(n => `<option value="${n}" ${String(TQ.slidesV) === String(n) ? "selected" : ""}>~${n}</option>`).join("")}</select></label>
      <label class="wide">Izoh <small>(auditoriya, urg'u, nimalar bo'lsin)</small><textarea id="tqAud" rows="2" maxlength="500" placeholder="masalan, 2-kurs talabalari uchun, ko'proq amaliy misollar">${esc(TQ.audV || "")}</textarea></label>
    </div></section>
    <div class="tq-acts"><span class="muted tiny">Faqat siz yuklagan material ishlatiladi. Fayl: .docx, .pdf, .txt · ${M.max_mb} MB gacha.</span>
      <button type="button" class="btn primary" id="tqGo" ${M.used >= M.limit ? "disabled" : ""}>${ico("spark", 16)} Reja tuzish</button></div>
    <div id="tqProg" class="tq-prog" hidden></div>
  </div>`;
  const keep = () => { TQ.titleV = $("#tqTitle").value; TQ.slidesV = $("#tqSlides").value; TQ.audV = $("#tqAud").value; };
  ["#tqTitle", "#tqSlides", "#tqAud"].forEach(q => $(q).addEventListener("input", keep));
  $("#tqSlides").addEventListener("change", keep);
  const later = $("#tqLater");
  if (!noLes) {
    const lp = lpPicker($("#tqLp"), {courses: items, value: TQ.pick && {cid: TQ.pick.cid, lkey: TQ.pick.lkey}, disabled: later.checked, onChange: p => { TQ.pick = p; tqDupHint(); }});
    later.onchange = () => { TQ.later = later.checked; lp.disable(later.checked); tqDupHint(); };
  }
  const segs = box.querySelector(".tq-seg");
  segs.querySelectorAll("button").forEach(b => b.onclick = () => {
    if (TQ.src === "text") TQ.text = $("#tqText")?.value || TQ.text;
    TQ.src = b.dataset.s;
    segs.querySelectorAll("button").forEach(x => { const on = x === b; x.classList.toggle("on", on); x.setAttribute("aria-selected", on); x.tabIndex = on ? 0 : -1; });
    $("#tqSrc").setAttribute("aria-labelledby", "tqSeg_" + TQ.src); tqErrClear(); tqSrcDraw();
  });
  tqTabKeys(segs);
  tqSrcDraw();
  $("#tqGo").onclick = async () => {
    const b = $("#tqGo");
    if (TQ.creating) return;
    tqErrClear();
    const meta = {title: $("#tqTitle").value.trim(), slides: $("#tqSlides").value, audience: $("#tqAud").value.trim()};
    if (!noLes && !later.checked) {
      if (!TQ.pick) { tqErr("Avval darsni tanlang: kurs → yo'nalish → fan → dars"); return; }
      meta.course_id = TQ.pick.cid; meta.lkey = TQ.pick.lkey;
    }
    let call;
    TQ.creating = true;
    try {
      if (TQ.src === "file") {
        if (!TQ.file) { tqErr("Avval faylni tanlang"); return; }
        const q = new URLSearchParams({name: TQ.file.name, ...meta});
        const raw = await TQ.file.arrayBuffer();
        call = () => tqApi(`/api/taqdimot/decks?${q}`, null, raw);
      } else {
        const text = ($("#tqText").value || "").trim();
        if (text.length < 40) { tqErr("Matn juda qisqa — kamida bir-ikki jumla yozing"); return; }
        call = () => tqApi("/api/taqdimot/decks/text", {...meta, slides: meta.slides ? +meta.slides : null, text});
      }
      tqBusy(b, true);
      const pr = $("#tqProg"); pr.hidden = false; pr.classList.remove("err");
      pr.innerHTML = `<span class="tq-spin"></span><span role="status">${M.engine === "claude" ? "AI material asosida reja tuzmoqda — odatda 1–2 daqiqa…" : "Reja tuzilmoqda…"}</span>`;
      try {
        const d = await call();
        TQ.file = null; TQ.text = ""; TQ.deck = d; TQ.dirty = false; TQ.stale = true; TQ.titleV = TQ.audV = "";
        toast("Reja tayyor — tekshirib, tahrirlang");
        TQ.meta.used += 1;
        tqEditor();
      } catch (e) {
        if (e.message !== "auth") tqErr(e.msg || "Xatolik yuz berdi");
        else $("#tqProg") && ($("#tqProg").hidden = true);
      } finally { if (b.isConnected) { tqBusy(b, false); b.disabled = TQ.meta.used >= TQ.meta.limit; } }
    } finally { TQ.creating = false; }
  };
}

/* material manbai: fayl yoki matn (faqat shu qism qayta chiziladi — yozilgan mavzu va izoh yo'qolmaydi) */
function tqSrcDraw() {
  const M = TQ.meta, src = $("#tqSrc"); if (!src) return;
  if (TQ.src === "file") {
    src.innerHTML = `<label class="tq-drop" id="tqDrop" tabindex="0"><input type="file" id="tqFile" accept=".docx,.pdf,.txt,application/pdf,text/plain,application/vnd.openxmlformats-officedocument.wordprocessingml.document" hidden>
      ${ico("file", 26)}<b id="tqFname">${TQ.file ? esc(TQ.file.name) + ` · ${(TQ.file.size / 1048576).toFixed(1)} MB` : "Faylni shu yerga tashlang yoki tanlang"}</b><span class="muted tiny">Word (.docx), PDF (rasmlari bilan) yoki matn (.txt)</span></label>`;
    const inp = $("#tqFile"), drop = $("#tqDrop");
    const setF = f => {
      if (!f) return;
      if (!TQ_EXT.test(f.name)) { tqErr(`«${f.name}» qabul qilinmaydi — faqat .docx, .pdf yoki .txt fayl yuklang (eski .doc faylni Word'da .docx qilib saqlang)`); return; }
      if (f.size > M.max_mb * 1048576) { tqErr(`Fayl hajmi ${M.max_mb} MB dan oshmasin`); return; }
      if (!f.size) { tqErr("Fayl bo'sh"); return; }
      tqErrClear(); TQ.file = f; $("#tqFname").textContent = `${f.name} · ${(f.size / 1048576).toFixed(1)} MB`;
    };
    inp.onchange = () => { setF(inp.files[0]); inp.value = ""; };
    drop.onkeydown = e => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); inp.click(); } };
    ["dragover", "dragenter"].forEach(ev => drop.addEventListener(ev, e => { e.preventDefault(); drop.classList.add("over"); }));
    ["dragleave", "drop"].forEach(ev => drop.addEventListener(ev, e => { e.preventDefault(); drop.classList.remove("over"); }));
    drop.addEventListener("drop", e => setF(e.dataTransfer.files[0]));
  } else {
    src.innerHTML = `<textarea id="tqText" class="tq-text" rows="12" aria-label="Ma'ruza matni" placeholder="Ma'ruza matnini shu yerga yozing yoki joylang. Sarlavhalarni # bilan, bandlarni - bilan boshlash mumkin.">${esc(TQ.text || "")}</textarea>`;
    $("#tqText").addEventListener("input", e => { TQ.text = e.target.value; });
  }
}

async function tqList(scope) {
  const box = $("#tqBody");
  box.innerHTML = `<p class="muted" role="status">Yuklanmoqda…</p>`;
  let d;
  try { d = await tqApi(`/api/taqdimot/decks?scope=${scope}`); } catch (e) { box.innerHTML = `<div class="card tq-empty">${esc(e.msg || "Yuklab bo'lmadi")}</div>`; return; }
  if (!d.items.length) { box.innerHTML = `<div class="card tq-empty">${scope === "dept" ? "Kafedra o'qituvchilari hali taqdimot tayyorlamagan." : "Hali taqdimot yo'q. «Yangi taqdimot» bo'limidan boshlang."}</div>`; return; }
  box.innerHTML = `<div class="card tq-card"><div class="tw"><table class="tq-t stack"><thead><tr>${scope === "dept" ? "<th>O'qituvchi</th>" : ""}<th>Mavzu</th><th>Fan</th><th>Dars kodi</th><th>Holat</th><th>Slayd</th><th>Usul</th><th>Sana</th></tr></thead><tbody>
    ${d.items.map((r, i) => `<tr class="tq-click" data-i="${i}" tabindex="0" aria-label="${esc((r.title || "Mavzu nomi kiritilmagan") + " — ochish")}">${scope === "dept" ? `<td data-l="O'qituvchi">${esc((r.user_name || "").split(":").pop().trim())}</td>` : ""}
      <td data-l="Mavzu"><b>${esc((r.topic_no ? r.topic_no + "-mavzu. " : "") + (r.title || "Mavzu nomi kiritilmagan"))}</b><div class="muted tiny">${esc(r.source_name || "")}</div></td>
      <td data-l="Fan">${esc(r.subject || "—")}</td><td data-l="Dars kodi">${r.lesson_code ? `<code class="tq-code">${esc(r.lesson_code)}</code>${r.sent_version ? " " + tqChip(`v${r.sent_version} yuborilgan`, "ok") : ""}` : `<span class="muted tiny">bog'lanmagan</span>`}</td><td data-l="Holat">${tqChip(...(TQ_ST[r.status] || [r.status, ""]))}</td>
      <td data-l="Slayd">${r.slides || "—"}</td><td data-l="Usul">${esc(r.engine ? tqEngLbl(r.engine, r.engine_label) : (r.engine_label || ""))}</td><td data-l="Sana">${dmy(r.updated_at || r.created_at)}</td></tr>`).join("")}</tbody></table></div></div>`;
  box.querySelectorAll("tr[data-i]").forEach(tr => {
    const open = () => tqOpen(d.items[+tr.dataset.i].id);
    tr.onclick = open; tr.onkeydown = e => { if (e.key === "Enter") open(); };
  });
}

async function tqOpen(id, restoring = false) {
  try { TQ.deck = await tqApi(`/api/taqdimot/decks/${id}`); TQ.dirty = false; tqEditor(); }
  catch (e) { TQ.deck = null; tqRemember(0); if (!restoring || e.message !== "api") toast(e.msg || "Ochib bo'lmadi"); tqShell(); }
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
  const metaTxt = () => [O.subject, (O.topic_no ? O.topic_no + "-mavzu: " : "") + (O.title || "Mavzu nomi kiritilmagan")].filter(Boolean).join(" · ");
  tqRemember(D.id);
  el.innerHTML = `<div class="tq-ed" id="tqEd">
    <h2 class="tq-sr" id="tqH2">Taqdimot muharriri: ${esc(metaTxt())}</h2>
    <div class="tq-bar">
      <button type="button" class="btn ghost sm tq-back" id="tqBack" title="Ro'yxatga qaytish" aria-label="Ro'yxatga qaytish">←</button>
      <div class="tq-meta"><button type="button" class="tq-meta-b" id="tqMetaB" ${ro ? "disabled" : ""} title="${ro ? esc(metaTxt()) : "Fan, mavzu va titul satrini tahrirlash"}" aria-label="${esc(metaTxt())}${ro ? "" : " — tahrirlash"}"><b id="tqMetaT">${esc(metaTxt())}</b>${ro ? "" : ico("pen", 13)}</button>
        <div class="tq-chips">${tqChip(st[0], st[1])}<span class="tq-eng">${tqChip(tqEngLbl(D.engine, D.engine_label), "", tqEngTitle(D.engine))}</span>${D.truncated ? tqChip("material qisqartirildi", "warn", "Material juda uzun edi — reja uning boshidan tuzildi") : ""}${D.pages ? tqChip(`≈ ${D.pages} slayd`, "", "Materialdagi taxminiy sahifalar soni") : ""}${ro ? tqChip("faqat ko'rish · " + (D.user_name || "").split(":").pop().trim(), "warn") : ""}</div>
        <div class="tq-pop" id="tqMetaP" hidden><div class="tq-grid">
          <label>Fan nomi<input data-o="subject" value="${esc(O.subject || "")}" maxlength="120" ${D.lesson ? 'readonly title="Fan darsdan olinadi"' : ""}></label>
          <label>Mavzu raqami<input data-o="topic_no" value="${esc(O.topic_no || "")}" maxlength="20" ${D.lesson ? 'readonly title="Raqam darsdan olinadi"' : ""}></label>
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
    ${tqLessonBar(D, ro)}
    <div class="tq-strip" id="tqStrip" role="listbox" aria-label="Slaydlar"></div>
    <div class="tq-main">
      <div class="tq-form" id="tqForm"></div>
      <div class="tq-side"><div class="tq-prev" id="tqPrev"></div>
        <div class="tq-pn"><button type="button" class="btn sm ghost" id="tqPv">‹ Oldingi</button><span class="muted tiny" id="tqPos"></span><button type="button" class="btn sm ghost" id="tqNx">Keyingi ›</button></div>
        <p class="muted tiny tq-keys"><span class="tq-keys-d">←/→ yoki PgUp/PgDn — slaydlar orasida · sichqoncha bilan sudrab tartiblang · o'ng tugma — menyu</span><span class="tq-keys-m">«⋯» tugmasi — slayd menyusi (nusxa, surish, turi, o'chirish)</span></p></div>
    </div>
    <div class="tq-menu" id="tqMenu" hidden></div>
  </div>`;
  $("#tqBack").onclick = () => { if (TQ.dirty && !confirm("Saqlanmagan o'zgarishlar bor. Chiqasizmi?")) return; TQ.deck = null; TQ.cur = 0; TQ.dirty = false; TQ.stale = true; tqRemember(0); tqShell(); };
  $("#tqPv").onclick = () => tqGo(TQ.cur - 1);
  $("#tqNx").onclick = () => tqGo(TQ.cur + 1);
  tqStrip(); tqSlide();
  tqLessonBind(D, ro);
  if (ro) return;
  const pop = $("#tqMetaP");
  $("#tqMetaB").onclick = () => { pop.hidden = !pop.hidden; if (!pop.hidden) pop.querySelector("input")?.focus(); };
  $("#tqMetaOk").onclick = () => { pop.hidden = true; };
  el.querySelectorAll("[data-o]").forEach(i => i.oninput = () => { O[i.dataset.o] = i.value; const t = metaTxt(); $("#tqMetaT").textContent = t; $("#tqMetaB").setAttribute("aria-label", t + " — tahrirlash"); $("#tqH2").textContent = "Taqdimot muharriri: " + t; tqMark(); });
  $("#tqSave").onclick = () => tqSave($("#tqSave"));
  $("#tqBuild").onclick = async () => {
    const b = $("#tqBuild");
    if (TQ.dirty && !(await tqSave(null))) return;
    if (b.getAttribute("aria-busy")) return;
    tqBusy(b, true, "Yaratilmoqda…");
    try { TQ.deck = await tqApi(`/api/taqdimot/decks/${D.id}/build`, {}); TQ.dirty = false; toast(`Taqdimot tayyor: ${TQ.deck.slides} slayd`); tqEditor(); }
    catch (e) { toast(e.msg || "Xatolik"); tqBusy(b, false); }
  };
  $("#tqRegen").onclick = async () => {
    const b = $("#tqRegen");
    if (!arm(b, TQ.dirty ? "Tahrirlar yo'qoladi — qayta tuzilsinmi?" : "Ha, qayta tuzish")) return;
    if (b.getAttribute("aria-busy")) return;
    tqBusy(b, true, "Tuzilmoqda…"); b._tqOld = `${ico("refresh", 14)} Qayta tuzish`;
    try { TQ.deck = await tqApi(`/api/taqdimot/decks/${D.id}/regenerate`, {}); TQ.meta.used += 1; TQ.dirty = false; TQ.cur = 0; toast("Reja qayta tuzildi"); tqEditor(); }
    catch (e) { toast(e.msg || "Xatolik"); tqBusy(b, false); }
  };
  $("#tqDel").onclick = async () => {
    const b = $("#tqDel"), n = Math.max(0, ...(D.sends || []).map(x => x.version), D.sent_version || 0), note = $("#tqDelNote");
    if (b.getAttribute("aria-busy")) return;
    const first = !b.dataset.armed;
    if (!arm(b, "Ha, o'chirish")) {
      if (first && note) { note.textContent = n ? `Yuborilgan versiyalar (v1–v${n}) studiya va bo'limda qoladi; faqat sizdagi taqdimot va reja o'chadi.` : "Taqdimot va uning rejasi o'chiriladi."; clearTimeout(note._t); note._t = setTimeout(() => { note.textContent = ""; }, 4200); }
      return;
    }
    if (note) note.textContent = "";
    tqBusy(b, true);
    try { await tqApi(`/api/taqdimot/decks/${D.id}/delete`, {}); toast("Taqdimot o'chirildi"); TQ.deck = null; TQ.dirty = false; TQ.stale = true; tqRemember(0); TQ.tab = "mine"; tqShell(); }
    catch (e) { toast(e.msg || "Xatolik"); tqBusy(b, false); }
  };
}

function tqMark() { TQ.dirty = true; const d = $("#tqDirty"); if (d) d.hidden = false; tqSendState(); }

/* ---------- dars kodi, versiyalar, «Studiyaga va masofaviy bo'limga yuborish» ---------- */
/* Versiya DARS bo'yicha hisoblanadi (lesson_sent_version): dars boshqa taqdimot orqali yuborilgan bo'lishi mumkin. Maydon yo'q (eski server) — taqdimotning o'z sent_version'i. */
function tqSentInfo(D) {
  const L = D.lesson || {}, has = L.lesson_sent_version !== undefined;
  const sentV = has ? (+L.lesson_sent_version || 0) : (+D.sent_version || 0);
  const otherId = has ? L.lesson_sent_deck_id : null;
  const other = !!(sentV && otherId && +otherId !== +D.id);
  const ls = D.last_send || null;
  const at = other || !ls ? (L.lesson_sent_at || (other ? "" : D.sent_at) || "") : (ls.at || L.lesson_sent_at || D.sent_at || "");
  return {sentV, next: sentV + 1, other, otherTitle: L.lesson_sent_deck_title || (otherId ? "#" + otherId : ""), at,
    unchanged: !other && sentV > 0 && D.changed_since_send === false, ver: ls && ls.version ? ls.version : sentV};
}
const tqLesNo = les => (les && String(les.code || "").replace(/\D/g, "")) || "";
function tqLessonBar(D, ro) {
  const les = D.lesson, I = tqSentInfo(D);
  /* hujjatdagi «N-mavzu» tanlangan dars raqamidan farq qilsa — ehtimol noto'g'ri dars tanlangan */
  const dn = D.doc_topic_no != null && D.doc_topic_no !== "" ? String(D.doc_topic_no) : "", own = String(D.topic_no || (D.outline || {}).topic_no || tqLesNo(les));
  const mism = les && dn && own && dn !== own && !les.gone;
  const canRe = !ro && !D.sent_version;
  return `<div class="tq-les" id="tqLes">
    ${les ? `<span class="tq-les-l">Dars kodi:</span><code class="tq-code" title="Darsning unikal kodi">${esc(les.full_code)}</code><span class="tq-les-m">${esc([les.dept, les.teacher, les.subject].filter(Boolean).join(" · "))}</span>`
          : `<span class="tq-les-m muted">Darsga bog'lanmagan taqdimot</span>${ro ? "" : `<button type="button" class="btn sm" id="tqSetLes">Darsni belgilash</button>`}`}
    ${I.sentV ? (I.other ? tqChip(`Darsga v${I.sentV} yuborilgan (boshqa taqdimot)`, "warn", `Bu darsga v${I.sentV} boshqa taqdimot orqali yuborilgan: «${I.otherTitle}»`)
                         : tqChip(`v${I.sentV} yuborilgan${tqWhen(I.at) ? " · " + tqWhen(I.at) : ""}`, "ok", I.unchanged ? "Oxirgi yuborilgandan beri PPTX o'zgarmagan" : "Studiya va masofaviy bo'lim shu versiyani ko'radi")) : ""}
    <span class="tq-les-r">${(D.sends || []).length ? `<button type="button" class="btn sm ghost" id="tqHist">Yuborilgan versiyalar (${D.sends.length})</button>` : ""}
      ${ro ? "" : `<button type="button" class="btn sm ${I.sentV && !I.other && D.changed_since_send !== true ? "" : "primary"}" id="tqSend" aria-describedby="tqSendHint">${ico("arrow", 14)} Studiyaga va masofaviy bo'limga yuborish${I.sentV ? ` (v${I.next})` : ""}</button>`}</span>
    ${ro ? "" : `<p class="tq-les-hint muted tiny" id="tqSendHint" role="status"></p><p class="tq-les-hint muted tiny" id="tqDelNote" role="status"></p>`}
    ${mism ? `<div class="tq-warn tq-topic-w" id="tqTopicWarn">${ico("info", 14)}<span>Hujjatda «${esc(dn)}-mavzu» yozilgan, siz esa ${esc(les.code)} ni tanladingiz. To'g'rimi?</span>${canRe ? ` <button type="button" class="btn sm" id="tqChangeLes">Darsni o'zgartirish</button>` : ""}</div>` : ""}</div>`;
}
/* yuborish uchun shartlar: dars belgilangan, PPTX yaratilgan, saqlanmagan o'zgarish yo'q (aks holda eskirgan fayl ketmasin).
   Tugma disabled EMAS (fokus olsin va sababi o'qilsin) — aria-disabled + aria-describedby="tqSendHint" */
function tqSendState() {
  const b = $("#tqSend"), h = $("#tqSendHint"), D = TQ.deck; if (!b || !D) return;
  const I = tqSentInfo(D);
  const why = !D.lesson ? "Yuborish uchun avval darsni belgilang." : TQ.dirty ? "Saqlanmagan o'zgarishlar bor — «Saqlash» va «PPTX yaratish»ni bosing." :
    D.status !== "tayyor" ? "Yuborish uchun avval «PPTX yaratish»ni bosing." : "";
  b.setAttribute("aria-disabled", why ? "true" : "false"); b.classList.toggle("is-disabled", !!why);
  if (h) { h.textContent = why || TQ.note || (I.unchanged ? `Oxirgi yuborishdan (v${I.ver}${tqWhen(I.at) ? ", " + tqWhen(I.at) : ""}) beri o'zgarish yo'q.` : ""); h.classList.toggle("why", !!why); }
  if (!why && TQ.note) TQ.note = "";
}
function tqLessonRefresh() {
  const el = $("#tqLes"), D = TQ.deck; if (!el || !D) return;
  el.outerHTML = tqLessonBar(D, !D.can_edit); tqLessonBind(D, !D.can_edit);
}
function tqVersions(D) {
  const mx = Math.max(0, ...(D.sends || []).map(x => x.version));
  const rows = (D.sends || []).map(x => `<tr><td data-l="Versiya"><b>v${x.version}</b></td><td data-l="Sana">${dmy(x.sent_at)}${tqDT(x.sent_at) ? `<span class="muted tiny"> ${tqDT(x.sent_at).h}</span>` : ""}</td><td data-l="Slayd">${x.slides || "—"}</td><td data-l="Yuborgan">${esc(x.sent_by || "")}</td>
    <td data-l="Izoh">${x.note ? esc(x.note) : "<span class='muted'>—</span>"}</td><td data-l="Holat"><span class="tq-vst">${tqChip(x.studio_seen ? "Studiya ko'rdi" : "Studiya ko'rmagan", x.studio_seen ? "ok" : "")} ${tqChip(x.dept_seen ? "Bo'lim ko'rdi" : "Bo'lim ko'rmagan", x.dept_seen ? "ok" : "")}</span></td>
    <td data-l="Fayl" class="tq-vf"><a class="btn sm ghost" href="/api/taqdimot/decks/${D.id}/sends/${x.version}/pptx" aria-label="v${x.version} faylini yuklash (.pptx)">${ico("arrow", 13)} .pptx yuklash</a>${x.has_pdf ? ` <a class="btn sm ghost" href="/api/taqdimot/decks/${D.id}/sends/${x.version}/pdf" aria-label="v${x.version} faylini yuklash (.pdf)">.pdf</a>` : ""}</td></tr>`).join("");
  const bg = pkModal(`Yuborilgan versiyalar · ${D.lesson ? D.lesson.full_code : ""}`, `<p class="pk-note" style="margin-top:0">Dars kodi o'zgarmaydi, har yuborishda versiya oshadi. Studiya va masofaviy bo'lim eng yangisini (v${mx || tqSentInfo(D).sentV}) ko'radi; eskilari shu yerda qoladi.</p>
    <div class="tw"><table class="tq-t stack tq-vt"><thead><tr><th>Versiya</th><th>Sana</th><th>Slayd</th><th>Yuborgan</th><th>Izoh</th><th>Holat</th><th>Fayl</th></tr></thead><tbody>${rows}</tbody></table></div>`, null, "", true);
  bg.querySelector(".pk-modal").classList.add("tq-dlg", "tq-vers");
}
function tqPickLesson(D) {
  let pick = null;
  const bg = pkModal("Darsni belgilash", `<p class="pk-note" style="margin-top:0">Taqdimot qaysi darsga tegishli? Fan, kafedra va o'qituvchi darsdan olinadi; titul slaydidagi fan va mavzu raqami yangilanadi (PPTX qayta yaratiladi).</p>
    ${(TQ.lessons?.items || []).length ? `<div id="tqLpM"></div>` : `<div class="tq-note warn" role="status">${ico("info", 16)}<span>${esc(TQ_NO_LESSON)}</span></div>`}
    <div class="tq-dlg-err" id="tqPickErr" role="alert" hidden></div>`,
    async m => {
      const er = m.querySelector("#tqPickErr"); er.hidden = true;
      if (!pick) { er.textContent = "Darsni to'liq tanlang: kurs → yo'nalish → fan → dars."; er.hidden = false; return false; }
      try { TQ.deck = await tqApi(`/api/taqdimot/decks/${D.id}/lesson`, {course_id: pick.cid, lkey: pick.lkey}); TQ.dirty = false; TQ.stale = true; toast(`Dars belgilandi: ${pick.lesson.full_code}`); tqEditor(); return true; }
      catch (e) { er.textContent = e.msg || "Belgilab bo'lmadi"; er.hidden = false; return false; }
    }, "Belgilash", true, () => ($("#tqSetLes") || $("#tqChangeLes") || $("#tqSend"))?.focus({preventScroll: true}));
  bg.querySelector(".pk-modal").classList.add("tq-dlg");
  const box = bg.querySelector("#tqLpM");
  if (box) lpPicker(box, {courses: (TQ.lessons || {}).items || [], value: D.lesson ? {cid: D.lesson.course_id, lkey: D.lesson.lkey} : null, onChange: p => { pick = p; }});
}

/* «Yuborish» bosilganda: avval taqdimot SERVERDAN qayta o'qiladi (ikki tab / eskirgan versiya: boshqa tabda v5 yuborilgan bo'lsa bu yerda v6 ko'rinadi) */
async function tqSendOpen() {
  const b = $("#tqSend"), D0 = TQ.deck;
  if (!b || !D0 || document.querySelector(".tq-dlg")) return;
  if (b.getAttribute("aria-disabled") === "true") { const h = $("#tqSendHint"); h?.classList.remove("flash"); void h?.offsetWidth; h?.classList.add("flash"); return; }
  if (b.getAttribute("aria-busy") === "true") return;
  b.setAttribute("aria-busy", "true");
  try {
    const fresh = await tqApi(`/api/taqdimot/decks/${D0.id}`);
    if (!TQ.dirty) {
      const key = d => [tqSentInfo(d).sentV, d.status, d.updated_at, (d.lesson || {}).full_code, d.changed_since_send, (d.lesson || {}).lesson_sent_deck_id, (d.sends || []).length].join("|");
      const diff = key(fresh) !== key(D0);
      TQ.deck = fresh;
      if (diff) { tqEditor(); $("#tqSend")?.focus(); }
    }
    if (!TQ.deck.lesson || TQ.deck.status !== "tayyor" || TQ.dirty) { tqSendState(); toast("Taqdimot holati o'zgargan — yuborishdan oldin tekshiring"); return; }
    tqSendDialog(TQ.deck);
  } catch (e) { if (e.message !== "auth") toast(e.msg || "Taqdimot holatini o'qib bo'lmadi"); }
  finally { $("#tqSend")?.removeAttribute("aria-busy"); }
}
function tqSendDialog(D) {
  const L = D.lesson, I = tqSentInfo(D), next = I.next, px = D.pptx || {};
  const warn = I.other ? `<div class="tq-warn tq-dlg-w">${ico("alert", 14)}<span>Bu darsga allaqachon <b>v${I.sentV}</b> yuborilgan (boshqa taqdimot: «${esc(I.otherTitle)}»). Yuborsangiz <b>v${next}</b> bo'lib, studiya va bo'lim yangisini ko'radi. Davom etasizmi?</span></div>`
    : I.unchanged ? `<div class="tq-warn tq-dlg-w">${ico("info", 14)}<span>Oxirgi yuborishdan (v${I.ver}${tqDT(I.at) ? ", " + tqDT(I.at).d : ""}) beri o'zgarish yo'q — bir xil fayl yangi versiya bo'ladi.</span></div>` : "";
  const file = px.filename || px.size || px.built_at ? `<p class="tq-fileinfo tiny muted">Fayl: <b>${esc(px.filename || "taqdimot.pptx")}</b>${px.size ? " · " + tqSize(px.size) : ""}${tqDT(px.built_at) ? " · PPTX yaratilgan " + tqDT(px.built_at).d + ", " + tqDT(px.built_at).h : ""}</p>` : "";
  let busy = false;
  const bg = pkModal("Studiyaga va masofaviy bo'limga yuborish", `<p class="pk-note" style="margin-top:0">Tayyor taqdimot <b>ikkala tomonga birga</b> ketadi: studiya (syomkada ochadi) va masofaviy ta'lim bo'limi. Dars kodi o'zgarmaydi,
      yangi versiya — <b>v${next}</b>${I.sentV ? `; v${I.sentV} tarixda qoladi` : ""}.</p>
    ${warn}
    <div class="lp-info"><code>${esc(L.full_code)}</code><span><small>Kafedra</small>${esc(L.dept || "—")}</span><span><small>O'qituvchi</small>${esc(L.teacher || "—")}</span><span><small>Fan</small>${esc(L.subject)}</span>
      <span><small>Dars</small>${esc(L.code)}</span><span><small>Slayd</small>${D.slides || "—"}</span></div>
    ${file}
    <label class="tq-lbl2">Izoh (ixtiyoriy — operator va bo'limga)<textarea id="tqSendNote" rows="3" maxlength="400" placeholder="masalan, 7-slaydda formulalar yangilandi"></textarea></label>
    <div class="tq-dlg-err" id="tqSendErr" role="alert" hidden></div>`,
    async m => {
      const er = m.querySelector("#tqSendErr"), ok = m.querySelector("[data-ok]"), cancel = m.querySelector("[data-x]"), md = m.querySelector(".pk-modal"), okTxt = ok.textContent;
      er.hidden = true; er.textContent = "";
      busy = true; md.setAttribute("aria-busy", "true"); ok.textContent = "Yuborilmoqda…"; cancel.disabled = true;
      try {
        const r = await tqApi(`/api/taqdimot/decks/${D.id}/send`, {note: m.querySelector("#tqSendNote").value.trim()});
        TQ.deck = r; TQ.stale = true; tqApi("/api/taqdimot/lessons").then(x => { TQ.lessons = x; TQ.stale = false; }).catch(() => {});
        const v = r.version ?? r.send?.version, code = r.send?.code || L.full_code;
        if (r.unchanged) { TQ.note = `Bu fayl allaqachon v${v} sifatida yuborilgan — yangi versiya yaratilmadi.`; toast(`Bu fayl allaqachon v${v} sifatida yuborilgan`); }
        else toast(`Yuborildi: ${code} · v${v}${r.paket_error ? " (paketga qo'yishda ogohlantirish: " + r.paket_error + ")" : ""}`);
        tqEditor(); return true;
      } catch (e) {
        if (e.message === "auth") return false;
        er.textContent = e.msg || "Yuborib bo'lmadi — qayta urinib ko'ring"; er.hidden = false; toast(er.textContent); return false;
      } finally { busy = false; md.removeAttribute("aria-busy"); if (ok.isConnected) ok.textContent = okTxt; if (cancel.isConnected) cancel.disabled = false; }
    }, `Yuborish (v${next})`, false, () => $("#tqSend")?.focus({preventScroll: true}));
  bg.querySelector(".pk-modal").classList.add("tq-dlg");
  /* so'rov ketayotganda Esc / tashqariga bosish / «Bekor qilish» oynani yopib qo'ymaydi (pkModal'ning o'z tinglovchilaridan oldin, capture) */
  const stop = e => { if (busy) { e.stopImmediatePropagation(); e.preventDefault(); } };
  bg.addEventListener("mousedown", e => { if (e.target === bg) stop(e); }, true);
  bg.addEventListener("keydown", e => { if (e.key === "Escape") stop(e); }, true);
  bg.addEventListener("click", e => { if (e.target.closest("[data-x]")) stop(e); }, true);
}
function tqLessonBind(D, ro) {
  $("#tqHist")?.addEventListener("click", () => tqVersions(D));
  if (ro) return;
  $("#tqSetLes")?.addEventListener("click", () => tqPickLesson(D));
  $("#tqChangeLes")?.addEventListener("click", () => tqPickLesson(D));
  $("#tqSend")?.addEventListener("click", () => tqSendOpen());
  tqSendState();
}

async function tqSave(btn) {
  const D = TQ.deck;
  try {
    if (btn) tqBusy(btn, true);
    TQ.deck = await tqApi(`/api/taqdimot/decks/${D.id}/outline`, {outline: D.outline});
    TQ.dirty = false;
    if (btn) { toast("Reja saqlandi"); tqEditor(); } else { const d = $("#tqDirty"); if (d) d.hidden = true; }
    return true;
  } catch (e) { toast(e.msg || "Saqlab bo'lmadi"); return false; }
  finally { if (btn && btn.isConnected) tqBusy(btn, false); }
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
      ${ro ? "" : `<button type="button" class="tq-th-m" data-m="${i}" aria-label="${i + 1}-slayd menyusi" aria-haspopup="menu">⋯</button>`}
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
