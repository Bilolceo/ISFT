/* =====================================================================
   «Konstruktor» — A versiya (taqqoslash uchun): Articulate Rise'dan o'tgan bo'lim xodimi uchun bitta oqim, uch qadam:
     1) Materiallar — fayllarni bitta joyga tashlash (video / YouTube, ma'ruza Word yoki skaner PDF, taqdimot .ppt/.pptx/.pdf, ✅ belgili test Word);
        har biri o'z joyiga tushadi, holati kartochkalarda.
     2) Tahrirlash — dars bloklarga yig'iladi (paket → muharrir) va Rise ko'rinishidagi muharrir ochiladi (kurs.js, .ku-rise).
     3) Nashr — eksport (NEXTID — xAPI) va ko'rib chiqishga yuborish / tasdiqlash (muharrirdagi qadamlar tasmasidan).
   B versiya — avvalgi «Avtomatik yig'ish (shablon)» + «Muharrirda tahrirlash». Tanlov: fan sahifasidagi «Ko'rinish: A / B» (localStorage «dsVer»).
   Server — mavjud API: /api/paket/courses/{cid}/topics/{key}[/upload|/video|/title], /api/dars/subjects/{cid}/lessons/{key}/convert|resync.
   ===================================================================== */
const KX = {cid: 0, key: 0, box: null, d: null, busy: false};
function dsVer() { try { return localStorage.getItem("dsVer") === "b" ? "b" : "a"; } catch (e) { return "a"; } }
function dsVerSet(v) { try { localStorage.setItem("dsVer", v); } catch (e) { /* jim */ } }

async function kxOpen(box, cid, key) {
  Object.assign(KX, {box, cid: +cid, key: +key});
  const [d, subj] = await Promise.all([pkApi(`/api/paket/courses/${cid}/topics/${key}`), (DS.data && DS.data.course && DS.cid === +cid ? DS.data : pkApi(`/api/dars/subjects/${cid}`))]);
  KX.d = d; KX.subj = subj;
  kxRender();
  window.scrollTo(0, 0);   /* fan ro'yxatidagi siljish saqlanib, «Namuna» tasmasi sarlavha ostida qirqilib qolmasin */
}
function kxSteps(cur) {
  const S = [["Materiallar", "Fayllarni tashlang"], ["Tahrirlash", "Rise kabi bloklar"], ["Nashr", "NEXTID uchun fayl"]];
  return `<ol class="kx-steps" aria-label="Qadamlar">${S.map(([t, s], i) => `<li class="${i + 1 < cur ? "done" : i + 1 === cur ? "on" : ""}" ${i + 1 === cur ? 'aria-current="step"' : ""}>
    <span class="n">${i + 1 < cur ? "✓" : i + 1}</span><span><b>${t}</b><small>${s}</small></span></li>`).join("")}</ol>`;
}
function kxCard(id, icon, title, ok, status, hint, body, more) {
  return `<section class="kx-card ${ok ? "ok" : ""}" data-slot="${id}"><div class="kx-card-h"><span class="kx-ic">${ico(icon, 20)}</span><b>${title}</b></div>
    <div class="kx-meta"><span class="kx-st ${ok ? "ok" : ""}">${ok ? "✓ Tayyor" : "Bo'sh"}</span></div>
    <p class="kx-stat">${status}</p>${hint ? `<p class="kx-hint">${hint}</p>` : ""}${more ? `<details class="kx-more"><summary>Batafsil</summary>${more}</details>` : ""}
    <div class="kx-body">${body}</div><p class="kx-prog" aria-live="polite"></p></section>`;
}
/* video fayli bor bo'lsa: mavjud subtitrlar (chip). «Avtomatik subtitr (AI)» tugmasi yashirilgan (ISFT darslari YouTube havolasi bilan; kerak bo'lsa true qiling) */
const KX_AUTO_CAPS = false;
function kxCaps(vd) {
  const caps = vd.captions || [];
  return `<div class="kx-cap"><div class="kx-cap-h"><b>Subtitr</b>${caps.length ? caps.map(c => `<span class="kx-chip" title="${esc(c.label || c.lang || "")}${c.cues ? ` · ${c.cues} qator` : ""}">${esc(c.label || c.lang || "uz")}${c.lang && c.label && c.label !== c.lang ? ` · ${esc(c.lang)}` : ""}</span>`).join("") : `<span class="kx-hint">hali yo'q</span>`}</div>
    ${KX_AUTO_CAPS ? `    <button type="button" class="btn sm ghost" id="kxAuto" aria-describedby="kxAutoMsg" title="Video ovozidan o'zbekcha subtitr (AI) — navbatga qo'yiladi">${ico("spark", 15)} Avtomatik subtitr (AI)</button>
    <p class="kx-cap-msg" id="kxAutoMsg" role="status" aria-live="polite">${esc(KX.capMsg || "")}</p>` : ""}</div>`;
}
function kxRender() {
  const d = KX.d, R = d.ready, L = d.lesson || {}, c = KX.subj.course || {}, box = KX.box;
  const tx = R.text || {}, sl = R.slides || {}, vd = R.video || {}, qz = R.quiz || {}, as = R.assignment || {}, ex = R.exercises || {};
  const tools = (PK.meta && PK.meta.tools) || {};
  const up = (as_, accept, label) => `<label class="btn sm pk-file">${ico("upload", 15)} ${label}<input type="file" hidden accept="${accept}" data-kx-up="${as_}"></label>`;
  box.innerHTML = `<div class="card pk-card kx">
    <div class="kx-top"><button type="button" class="btn sm ghost" id="kxBack">← ${esc(c.subject || "Fan")}</button>
      <span class="kx-code">${esc(L.code || "")}</span>${(L.full_code || (c.code && L.code ? `${c.code}_${L.code}` : "")) ? `<code class="kx-fcode" title="Darsning unikal kodi">${esc(L.full_code || `${c.code}_${L.code}`)}</code>` : ""}<input class="kx-title" id="kxT" value="${esc(L.untitled ? "" : (L.title || ""))}" placeholder="Dars mavzusi (Word'dagi «Mavzu:» qatoridan o'zi olinadi)" maxlength="300" aria-label="Dars mavzusi">
      <span class="kx-ver">A versiya · Konstruktor</span></div>
    ${kxSteps(1)}
    <div class="kx-drop" id="kxDrop" tabindex="0" role="button" aria-label="Fayllarni yuklash">
      <span class="kx-drop-ic">${ico("upload", 30)}</span>
      <div><b>Barcha fayllarni shu yerga tashlang</b>
        <span>Ma'ruza (Word${tools.ocr ? ", skaner PDF" : ""}), taqdimot (PowerPoint${tools.office ? " — .ppt ham" : ""}, PDF), test (Word), video (.mp4). Har biri o'z joyiga o'zi tushadi — Rise'dagidek copy-paste kerak emas.</span></div>
      <label class="btn primary pk-file">${ico("upload", 16)} Fayl tanlash<input type="file" id="kxAny" multiple hidden accept=".docx,.doc,.pdf,.pptx,.ppt,.txt,.mp4,.webm"></label></div>
    <div class="kx-grid">
      ${kxCard("video", "video", "1. Videodars", vd.ok, vd.ok ? (vd.provider === "youtube" ? `YouTube: <code>${esc(vd.video_id || "")}</code>` : `Fayl: ${esc(vd.file?.name || "video")}`) : "Video hali yo'q",
        "YouTube havolasi (tavsiya) yoki video fayl.",
        `<label class="kx-lbl" for="kxYt">YouTube havolasi</label>
         <input class="kx-in" id="kxYt" type="url" placeholder="https://youtu.be/…" value="${esc(vd.provider === "youtube" ? vd.url || "" : "")}">
         <div class="kx-acts"><button type="button" class="btn sm" id="kxYtS">Saqlash</button>${up("video", ".mp4,.webm,video/mp4,video/webm", vd.file ? "Videoni almashtirish" : "Video fayl")}</div>
         ${vd.file ? kxCaps(vd) : ""}`)}
      ${kxCard("text", "file", "2. Ma'ruza matni", tx.ok, tx.ok ? `${esc(tx.name || "")} · ${(tx.chars || 0).toLocaleString("ru-RU")} belgi${tx.ocr ? " · skaner (OCR) — sahifalar rasm bo'lib chiqadi" : ""}${R.plan?.n ? ` · reja: ${R.plan.n} band` : ""}${R.images?.n ? ` · ${R.images.n} rasm` : ""}` : "Ma'ruza hali yo'q",
        "Word fayl — mavzu, reja, matn, rasm va jadvallar o'zi ajratiladi (formulalar ham).", `<div class="kx-acts">${up("matn", ".docx,.doc,.pdf,.txt", tx.ok ? "Almashtirish" : "Word yuklash")}</div>`)}
      ${kxCard("slides", "slides", "3. Taqdimot", sl.ok, sl.ok ? `${sl.n || 0} slayd${sl.display === "images" ? " · asl ko'rinishda" : " · matn ko'rinishida"}${sl.file ? " · .pptx" : ""}${sl.pdf ? " · .pdf" : ""}` : "Taqdimot hali yo'q",
        tools.office ? "PowerPoint (.pptx yoki eski .ppt) — slaydlar o'zi rasmga aylanadi." : "PowerPoint (.pptx) yoki PDF.", `<div class="kx-acts">${up("taqdimot", ".pptx,.ppt,.pdf", sl.ok ? "Almashtirish" : "Taqdimot yuklash")}</div>`)}
      ${kxCard("test", "checkc", "4. Mashq va topshiriqlar", qz.ok || as.ok || ex.ok,
        [qz.approved ? `${qz.approved} ta test savoli` : "", ex.n ? `${ex.n} ta moslashtirish` : "", as.n ? `${as.n} ta ochiq savol` : "",
          qz.pending ? `<b class="kx-warn" data-pending="${qz.pending}">${qz.pending} ta savol javobsiz</b>` : ""].filter(Boolean).join(" · ") || "Test hali yo'q",
        "Test savollari Word faylda; to'g'ri javob belgilanadi.", `<div class="kx-acts">${up("test", ".docx,.txt", "Test (Word) yuklash")}${qz.pending ? `<button type="button" class="btn sm primary" id="kxTa">To'g'ri javobni tanlang (${qz.pending})</button>` : ""}</div>`,
        `<ul><li>To'g'ri javob oxiriga «✅» qo'yiladi: «1. Savol? A) … B) … ✅».</li><li>«Glossariy» bo'limi — moslashtirish mashqiga aylanadi.</li><li>«Savollar» bo'limi — PDF topshiriqqa aylanadi.</li></ul>`)}
    </div>
    <div class="kx-foot"><span class="kx-note">${tx.ok || sl.ok || vd.ok ? "Materiallar yetarli bo'lsa — darsni yig'ing. Keyin istalgan vaqtda qaytib, fayl qo'shishingiz mumkin." : "Kamida bitta material yuklang."}</span>
      <button type="button" class="btn primary kx-next" id="kxNext" ${tx.ok || sl.ok || vd.ok ? "" : "disabled"}>Darsni yig'ish va tahrirlash →</button></div></div>`;
  kxBind();
}
function kxBind() {
  const box = KX.box, base = `/api/paket/courses/${KX.cid}/topics/${KX.key}`;
  box.querySelector("#kxBack").onclick = () => { KX.cid = 0; dsSubject(box); };
  const t = box.querySelector("#kxT");
  t.onchange = async () => { const r = await pkApi(`${base}/title`, {title: t.value.trim()}); if (r) toast("Mavzu saqlandi"); };
  box.querySelector("#kxYtS").onclick = async () => {
    const u = box.querySelector("#kxYt").value.trim();
    const r = await pkApi(`${base}/video`, {url: u}); if (!r) return;
    toast(u ? "YouTube havolasi saqlandi" : "Havola olib tashlandi"); kxReload();
  };
  box.querySelector("#kxAuto")?.addEventListener("click", async e => {
    const btn = e.currentTarget, msg = box.querySelector("#kxAutoMsg"); btn.disabled = true; msg.textContent = "So'rov yuborilmoqda…"; KX.capMsg = "";
    let text = "", reload = false;
    try {
      const r = await fetch(`${base}/captions/auto`, {method: "POST", credentials: "same-origin", headers: {"Content-Type": "application/json"}, body: JSON.stringify({lang: "uz"})});
      if (r.status === 401) { showLogin(); return; }
      const d = await r.json().catch(() => ({}));
      if (r.status === 404 && (!d.detail || d.detail === "Not Found")) text = "Hozircha mavjud emas";
      else if (!r.ok) text = pkErrMsg(d);
      else {
        const st = {queued: "Navbatga qo'yildi — tayyor bo'lgach subtitr shu yerda ko'rinadi", exists: "Subtitr allaqachon bor", unavailable: "Hozircha mavjud emas"}[d.state] || "";
        text = d.message || st || "So'rov qabul qilindi"; reload = d.state === "exists";
      }
    } catch (err) { text = "Tarmoq xatosi — qayta urinib ko'ring"; }
    finally { if (btn.isConnected) btn.disabled = false; }
    if (reload) { KX.capMsg = text; return kxReload(); }
    if (msg.isConnected) msg.textContent = text;
  });
  const send = async (files, as_) => {
    files = [...files]; if (!files.length || KX.busy) return;
    KX.busy = true; let okN = 0; const needA = [];
    try {
      for (const f of files) {
        const slot = as_ ? {matn: "text", taqdimot: "slides", video: "video", test: "test"}[as_] : null;
        const prog = (slot ? box.querySelector(`[data-slot="${slot}"] .kx-prog`) : null) || box.querySelector("#kxDrop");
        const say = m => { if (prog.classList.contains("kx-prog")) prog.textContent = m; else toast(m); };
        say(`«${f.name}» yuklanmoqda…`);
        const r = await pkSend(`${base}/upload?name=${encodeURIComponent(f.name)}${as_ ? "&as=" + as_ : ""}`, f, p => say(`«${f.name}» — ${Math.round(p * 100)}%`));
        if (r.status === 401) { showLogin(); return; }
        if (r.ok) {
          okN++; say(`✓ «${f.name}» — ${r.data.label || "yuklandi"}`);
          if (r.data.needs_answer?.length) needA.push({upload_id: r.data.upload_id, needs_answer: r.data.needs_answer, saved: r.data.saved});
        }
        else { say(""); toast(`«${f.name}»: ${pkErrMsg(r.data)}`); }
      }
    } finally { KX.busy = false; }
    if (okN) await kxReload();
    if (needA.length && await pkAskAnswers(base, needA)) kxReload();      /* javobi (✅) topilmagan savollar — «To'g'ri javobni tanlang» */
  };
  box.querySelector("#kxTa")?.addEventListener("click", async () => {
    const p = await pkApi(`${base}/test/pending`).catch(() => null);
    if (p && p.needs_answer?.length) { if (await pkAnswerModal(base, p)) kxReload(); }
    else { toast("Javobi belgilanmagan savol qolmagan"); kxReload(); }
  });
  box.querySelector("#kxAny").onchange = e => { const fs = [...e.target.files]; e.target.value = ""; send(fs, ""); };
  box.querySelectorAll("[data-kx-up]").forEach(i => i.onchange = () => { const fs = [...i.files]; i.value = ""; send(fs, i.dataset.kxUp); });
  const dz = box.querySelector("#kxDrop");
  const stop = e => { e.preventDefault(); e.stopPropagation(); };
  box.ondragover = stop; box.ondrop = stop;
  dz.ondragenter = dz.ondragover = e => { stop(e); dz.classList.add("over"); };
  dz.ondragleave = e => { if (!dz.contains(e.relatedTarget)) dz.classList.remove("over"); };
  dz.ondrop = e => { stop(e); dz.classList.remove("over"); send(e.dataTransfer?.files || [], ""); };
  dz.onkeydown = e => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); box.querySelector("#kxAny").click(); } };
  box.querySelector("#kxNext").onclick = async e => {
    const b = e.currentTarget; b.disabled = true; b.textContent = "Dars yig'ilmoqda…";
    const lessons = (KX.subj.lessons || []), l = lessons.find(x => x.key === KX.key);
    let kcid = l && l.kurs ? l.kurs.id : 0;
    if (kcid) {   /* avval o'tkazilgan — yangi fayllar bo'lsa muharrirga qo'shiladi (muallif bloklari tegilmaydi) */
      const rs = await pkApi(`/api/dars/subjects/${KX.cid}/lessons/${KX.key}/resync`).catch(() => null);
      if (rs && rs.pending) await pkApi(`/api/dars/subjects/${KX.cid}/lessons/${KX.key}/resync`, {preview: false});
    } else {
      const r = await pkApi(`/api/dars/subjects/${KX.cid}/lessons/${KX.key}/convert`, {});
      if (!r) { b.disabled = false; b.textContent = "Darsni yig'ish va tahrirlash →"; return; }
      kcid = r.ku_course_id;
    }
    if (typeof kuUiSet === "function") kuUiSet("rise");
    go("kurs", {cid: kcid, wiz: {cid: KX.cid, key: KX.key, code: (KX.d.lesson || {}).code || ""}});
  };
}
async function kxReload() { KX.d = await pkApi(`/api/paket/courses/${KX.cid}/topics/${KX.key}`); KX.subj = await pkApi(`/api/dars/subjects/${KX.cid}`); kxRender(); }
/* muharrirdan «← Materiallar»: fan sahifasi chizilgach (dsSubject oxirida) konstruktor ochiladi */
function kxBack(cid, key) { KX.pending = {cid: +cid, key: +key}; DS.cid = +cid; DS.data = null; go("paket", {tab: "fanlar"}); }

/* =====================================================================
   «Ko'p faylni yuklash» (fan sahifasi): ko'p fayl (masalan 15 ta Word) → fayl nomidagi raqam bo'yicha darsga moslanadi → ko'rib chiqish jadvali
   (dars va tur o'zgartiriladi yoki fayl o'tkaziladi) → birma-bir yuklash (jarayon, har fayl natijasi) → xulosa + «Konstruktorda ochish».
   Moslashtirish — sof funksiyalar (kxbParse, kxbMatch): DOM'siz, tools/bulk_upload_check.js node'da sinaydi.
   Server: har fayl alohida — POST /api/paket/courses/{cid}/topics/{key}/upload?name=…&as=… (mavjud nuqta; ruxsat va hajm — serverda).
   ===================================================================== */
const KXB_KINDS = {matn: "Ma'ruza matni", taqdimot: "Taqdimot", video: "Video", test: "Test (Word)", subs: "Subtitr", fayl: "Qo'shimcha fayl"};
const KXB_EXT = {docx: "matn", doc: "matn", txt: "matn", pptx: "taqdimot", ppt: "taqdimot", pdf: "taqdimot", mp4: "video", webm: "video",
                 srt: "subs", vtt: "subs", xlsx: "fayl"};
const KXB_WORD = "ma'?ruza|lektsiya|lekciya|lecture|mavzu|dars|amaliyot|amaliy|practice|seminar|laboratoriya|laboratory|lab|mustaqil|mt";
const KXB_KIND_OF = w => /^(ma'?ruza|lektsiya|lekciya|lecture|mavzu|dars|l)$/.test(w) ? "maruza" : /^(amaliy|amaliyot|practice|a)$/.test(w) ? "amaliy"
  : /^(seminar|s)$/.test(w) ? "seminar" : /^(laboratoriya|laboratory|lab)$/.test(w) ? "laboratoriya" : /^(mustaqil|mt)$/.test(w) ? "mustaqil" : "maruza";
/* fayl nomi → {ext, kind (yuklash turi yoki ""), test, lk (dars turi), num (dars raqami yoki 0), how ("aniq" | "raqam" | "taxminiy" | "")} */
function kxbParse(name) {
  const full = String(name || "").trim(), m = /\.([A-Za-z0-9]{1,5})$/.exec(full), ext = m ? m[1].toLowerCase() : "";
  const s = (m ? full.slice(0, m.index) : full).toLowerCase().replace(/[’ʻʼ`´‘]/g, "'");
  const test = /(?<![a-z])test/.test(s);
  let kind = KXB_EXT[ext] || "";
  if (test && ["matn", "taqdimot"].includes(kind) && ["docx", "doc", "txt", "pdf"].includes(ext)) kind = "test";
  const out = {ext, kind, test, lk: "", num: 0, how: ""};
  let r;
  if ((r = new RegExp(`(?<![a-z\\d])0*(\\d{1,3})\\s*(?:[-_.]\\s*)?(?:-?(?:chi|inchi)\\s*)?(${KXB_WORD})(?![a-z])`).exec(s))) { out.num = +r[1]; out.lk = KXB_KIND_OF(r[2]); out.how = "aniq"; }
  else if ((r = new RegExp(`(?<![a-z])(${KXB_WORD}|l|a|s)\\s*[-_.№#:]*\\s*0*(\\d{1,3})(?!\\d)`).exec(s))) { out.num = +r[2]; out.lk = KXB_KIND_OF(r[1]); out.how = "aniq"; }
  else if ((r = /^[^a-z\d]*0*(\d{1,3})(?![\d])/.exec(s))) { out.num = +r[1]; out.lk = "maruza"; out.how = "raqam"; }
  else if ((r = /(?<![a-z\d]|\d[.])0*(\d{1,3})(?![a-z\d]|[.]\d)/.exec(s))) { out.num = +r[1]; out.lk = "maruza"; out.how = "taxminiy"; }
  if (!out.num) { out.num = 0; out.lk = ""; out.how = ""; }
  return out;
}
/* fayllar [{name, size}] × darslar [{key, kind, no, code}] → qatorlar: {i, name, size, ext, kind, lkey, code, how, skip, note} (skip — moslanmagan yoki turi noma'lum) */
function kxbMatch(files, lessons) {
  return (files || []).map((f, i) => {
    const p = kxbParse(f.name), L = p.num ? (lessons || []).find(l => l.kind === p.lk && l.no === p.num) : null;
    const junk = /^(~\$|\.)/.test(f.name) || /^(thumbs\.db|desktop\.ini)$/i.test(f.name);
    let note = "";
    if (junk) note = "Vaqtinchalik / tizim fayli";
    else if (!p.kind) note = p.ext === "mov" ? "«.mov» qabul qilinmaydi — videoni .mp4 qilib saqlang" : `«.${p.ext || "?"}» turi qo'llab-quvvatlanmaydi`;
    else if (!p.num) note = "Nomida dars raqami topilmadi — darsni tanlang";
    else if (!L) note = `${{maruza: "L", amaliy: "A", seminar: "S", laboratoriya: "Lab", mustaqil: "MT"}[p.lk]}${p.num} dars yo'q — darsni tanlang`;
    return {i, name: f.name, size: f.size || 0, ext: p.ext, kind: p.kind, lkey: L ? L.key : 0, code: L ? L.code : "", how: L ? p.how : "", skip: junk || !p.kind || !L, note};
  });
}
/* bir darsga bir turdagi bir nechta fayl — oxirgisi oldingisini almashtiradi: {qator indeksi: sabab} */
function kxbDups(rows) {
  const seen = {}, d = {};
  rows.filter(r => !r.skip && r.lkey).forEach(r => { const k = r.lkey + "|" + (r.kind === "test" ? "test" : r.kind); if (seen[k] != null) d[r.i] = seen[k]; seen[k] = r.i; });
  return d;
}
function kxbErr(res, size) {
  const d = res.data || {}, m = typeof pkErrMsg === "function" ? pkErrMsg(d) : (d.message || "Xatolik");
  if (res.status === 0) return m;
  if (res.status === 413) return /MB/.test(m) ? m : `Fayl juda katta${size ? ` (${(size / 1048576).toFixed(1)} MB)` : ""} — hajm chegarasidan oshdi`;
  if (res.status === 429) return "Juda ko'p so'rov — biroz kutib, qayta urinib ko'ring";
  if (res.status === 403) return "Bu darsga fayl yuklashga ruxsat yo'q";
  if (res.status >= 500 && m === "Xatolik yuz berdi") return `Server xatosi (${res.status}) — keyinroq qayta urinib ko'ring`;
  return m;
}

const KXB = {box: null, rows: [], files: [], phase: "pick", stop: false};
function kxbOpen(box) {
  box.querySelector("#kxbPanel")?.remove();
  Object.assign(KXB, {box, rows: [], files: [], phase: "pick", stop: false});
  const el = document.createElement("section"); el.className = "card pk-card kxb"; el.id = "kxbPanel"; el.setAttribute("aria-label", "Ko'p faylni yuklash");
  (box.querySelector(".ds-head") || box.firstElementChild).after(el);
  kxbRender(); el.scrollIntoView({block: "start", behavior: "smooth"}); el.querySelector("h3")?.focus({preventScroll: true});
}
function kxbClose() {
  if (KXB.phase === "run") return;
  const box = KXB.box, refresh = KXB.dirty; KXB.dirty = false; document.getElementById("kxbPanel")?.remove();
  if (refresh && box && box.isConnected) dsSubject(box);
}
const kxbLessonOpts = sel => (DS.data.lessons || []).map(l => `<option value="${l.key}" ${l.key === sel ? "selected" : ""}>${esc(l.code)} — ${l.untitled ? "nomi yo'q" : esc(String(l.title).slice(0, 48))}</option>`).join("");
function kxbRender() {
  const el = document.getElementById("kxbPanel"); if (!el) return;
  const ph = KXB.phase, rows = KXB.rows, use = rows.filter(r => !r.skip), dup = kxbDups(rows);
  const head = `<div class="kxb-h"><h3 tabindex="-1">${ico("upload", 18)} Ko'p faylni yuklash</h3><button type="button" class="btn sm ghost" data-kxb="close" ${ph === "run" ? "disabled" : ""} aria-label="Yopish (Esc)">${ico("x", 15)} Yopish</button></div>`;
  const pick = `<p class="kxb-note">Fayllarni tanlang yoki shu yerga tashlang (masalan, 15 ta Word). Har fayl <b>nomidagi raqam</b> bo'yicha darsga moslanadi:
      «1-ma'ruza.docx», «L3.pptx», «3-mavzu.docx», «maruza_07.docx», «07.docx»; nomida «test» bo'lsa — test, <code>.pptx/.ppt/.pdf</code> — taqdimot, <code>.mp4</code> — video.
      Yuklashdan oldin jadvalda tekshirib, o'zgartirishingiz mumkin.</p>
    <div class="kx-drop kxb-drop" id="kxbDrop" tabindex="0" role="button" aria-label="Fayllarni tanlash yoki tashlash"><span class="kx-drop-ic">${ico("upload", 26)}</span>
      <div><b>${rows.length ? "Yana fayl qo'shish" : "Fayllarni shu yerga tashlang"}</b><span>Word, PowerPoint, PDF, video (.mp4), test — birdaniga ko'p fayl</span></div>
      <label class="btn ${rows.length ? "" : "primary"} pk-file">${ico("upload", 16)} Fayllarni tanlash<input type="file" id="kxbIn" multiple hidden accept=".docx,.doc,.txt,.pdf,.pptx,.ppt,.mp4,.mov,.webm,.srt,.vtt,.xlsx"></label></div>`;
  let body = "";
  if (ph === "pick" && !rows.length) body = pick;
  else {
    const bad = rows.filter(r => r.res === "bad").length, stp = rows.filter(r => r.res === "stop").length;
    const unm = rows.filter(r => r.skip).length;
    const sum = ph === "pick" ? `<p class="kxb-sum" role="status"><b>${rows.length}</b> ta fayl: <b>${use.length}</b> ta darsga moslandi${unm ? `, <b class="kxb-bad">${unm}</b> ta o'tkazib yuboriladi (darsini tanlang)` : ""}${Object.keys(dup).length ? `, <b class="kxb-warn">${Object.keys(dup).length}</b> ta takror` : ""}.</p>`
      : `<div class="kxb-pg" role="progressbar" aria-valuemin="0" aria-valuemax="100" aria-valuenow="0" aria-label="Yuklash jarayoni"><i style="width:0%"></i></div><p class="kxb-sum" id="kxbSum" role="status" aria-live="polite"></p>`;
    const li = r => {
      const lk = r.lkey ? "" : "need";
      return `<li class="kxb-r ${r.skip ? "skip" : ""} ${lk}" data-i="${r.i}">
        <label class="kxb-use"><input type="checkbox" data-kxb-use="${r.i}" ${r.skip ? "" : "checked"} ${r.lkey && r.kind && ph === "pick" ? "" : "disabled"} aria-label="«${esc(r.name)}» yuklansin"></label>
        <span class="kxb-f"><b title="${esc(r.name)}">${esc(r.name)}</b><small>${pkSize(r.size)}${r.how === "taxminiy" ? " · raqam taxminiy" : ""}</small></span>
        <select data-kxb-l="${r.i}" ${ph === "pick" ? "" : "disabled"} aria-label="«${esc(r.name)}» — dars"><option value="0">— dars tanlang —</option>${kxbLessonOpts(r.lkey)}</select>
        <select data-kxb-k="${r.i}" ${ph === "pick" ? "" : "disabled"} aria-label="«${esc(r.name)}» — turi"><option value="">— turi —</option>${Object.entries(KXB_KINDS).map(([k, v]) => `<option value="${k}" ${k === r.kind ? "selected" : ""}>${esc(v)}</option>`).join("")}</select>
        <span class="kxb-s" data-st="${r.i}">${kxbStat(r, dup)}</span></li>`;
    };
    const acts = ph === "pick" ? `<div class="kxb-acts"><button type="button" class="btn primary" data-kxb="go" ${use.length ? "" : "disabled"}>${ico("upload", 16)} Yuklashni boshlash (${use.length} ta)</button>
        <label class="btn ghost pk-file">${ico("plus", 15)} Yana fayl<input type="file" id="kxbIn" multiple hidden accept=".docx,.doc,.txt,.pdf,.pptx,.ppt,.mp4,.mov,.webm,.srt,.vtt,.xlsx"></label>
        <button type="button" class="btn ghost" data-kxb="clear">Tozalash</button></div>`
      : ph === "run" ? `<div class="kxb-acts"><button type="button" class="btn" data-kxb="stop">To'xtatish</button><span class="kxb-hint">Sahifani yopmang — fayllar birma-bir yuklanmoqda.</span></div>`
      : `<div class="kxb-acts"><button type="button" class="btn primary" data-kxb="close">Tayyor</button>${bad + stp ? `<button type="button" class="btn" data-kxb="retry">Yuklanmaganlarni qayta yuklash (${bad + stp})</button>` : ""}</div>`;
    body = `${sum}<ul class="kxb-rows" aria-label="Fayllar">${rows.map(li).join("")}</ul>${acts}`;
  }
  el.innerHTML = head + body; kxbBind(el);
  if (ph !== "pick") kxbProgress();
}
function kxbStat(r, dup) {
  if (r.res === "ok") return `<span class="kxb-ok">✓ ${esc(r.label || "yuklandi")}</span> <button type="button" class="btn sm ghost" data-kxb-open="${r.lkey}">Konstruktorda ochish</button>`;
  if (r.res === "bad") return `<span class="kxb-bad" role="alert">✗ ${esc(r.err || "xato")}</span>`;
  if (r.res === "run") return `<span class="kxb-run">Yuklanmoqda… ${r.pct != null ? Math.round(r.pct * 100) + "%" : ""}</span>`;
  if (r.res === "stop") return `<span class="muted">To'xtatildi</span>`;
  if (r.skip) return `<span class="kxb-bad">${esc(r.note || "o'tkazib yuboriladi")}</span>`;
  const bits = [r.code ? `<b>${esc(r.code)}</b>` : "", dup && dup[r.i] != null ? `<span class="kxb-warn">takror — oldingisini almashtiradi</span>` : "", r.how === "taxminiy" ? `<span class="kxb-warn">taxminiy</span>` : ""].filter(Boolean);
  return bits.join(" · ") || `<span class="muted">kutmoqda</span>`;
}
function kxbProgress() {
  const el = document.getElementById("kxbPanel"); if (!el) return;
  const use = KXB.rows.filter(r => r.inq), done = use.filter(r => r.res === "ok" || r.res === "bad" || r.res === "stop").length;
  const cur = use.find(r => r.res === "run"), part = cur && cur.pct ? cur.pct : 0, tot = use.length || 1, pct = Math.min(100, Math.round((done + part) / tot * 100));
  const pg = el.querySelector(".kxb-pg"); if (pg) { pg.setAttribute("aria-valuenow", pct); pg.firstElementChild.style.width = pct + "%"; }
  const ok = use.filter(r => r.res === "ok").length, bad = use.filter(r => r.res === "bad").length, sm = el.querySelector("#kxbSum");
  if (sm) sm.innerHTML = KXB.phase === "run" ? `${done} / ${use.length} fayl · hozir: <b>${esc(cur ? cur.name : "—")}</b> · muvaffaqiyatli ${ok} · xato ${bad}`
    : `<b>Tugadi:</b> ${ok} ta yuklandi${bad ? `, <b class="kxb-bad">${bad} ta xato</b>` : ""}${use.length > done ? `, ${use.length - done} ta to'xtatildi` : ""}.`;
}
function kxbSetRow(r) { const c = document.querySelector(`#kxbPanel [data-st="${r.i}"]`); if (c) { c.innerHTML = kxbStat(r); } kxbProgress(); }
function kxbAdd(list) {
  const fs = [...list]; if (!fs.length || KXB.phase !== "pick") return;
  const lessons = DS.data.lessons || [], base = KXB.rows.length;
  fs.forEach(f => KXB.files.push(f));
  const rows = kxbMatch(fs.map(f => ({name: f.name, size: f.size})), lessons).map((r, j) => ({...r, i: base + j}));
  KXB.rows.push(...rows); kxbRender();
}
function kxbBind(el) {
  const inp = el.querySelector("#kxbIn"); if (inp) inp.onchange = () => { const fs = [...inp.files]; inp.value = ""; kxbAdd(fs); };
  const stop = e => { e.preventDefault(); e.stopPropagation(); };
  el.ondragover = e => { stop(e); el.classList.add("over"); }; el.ondragleave = e => { if (!el.contains(e.relatedTarget)) el.classList.remove("over"); };
  el.ondrop = e => { stop(e); el.classList.remove("over"); kxbAdd(e.dataTransfer?.files || []); };
  const dz = el.querySelector("#kxbDrop"); if (dz) dz.onkeydown = e => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); (el.querySelector("#kxbIn") || {}).click?.(); } };
  el.onkeydown = e => { if (e.key === "Escape" && KXB.phase !== "run") { e.stopPropagation(); kxbClose(); } };
  el.onclick = e => {
    const b = e.target.closest("[data-kxb]"), o = e.target.closest("[data-kxb-open]");
    if (o) { const k = +o.dataset.kxbOpen, box = KXB.box; DS.data = null; document.getElementById("kxbPanel")?.remove(); return kxOpen(box, DS.cid, k); }
    if (!b) return;
    const a = b.dataset.kxb;
    if (a === "close") kxbClose();
    else if (a === "clear") { KXB.rows = []; KXB.files = []; kxbRender(); }
    else if (a === "go") kxbRun();
    else if (a === "stop") { KXB.stop = true; b.disabled = true; b.textContent = "To'xtatilmoqda…"; }
    else if (a === "retry") { KXB.rows.forEach(r => { if (r.res === "bad" || r.res === "stop") { r.res = ""; r.err = ""; } else r.inq = false; }); kxbRun(true); }
  };
  el.querySelectorAll("[data-kxb-use]").forEach(c => c.onchange = () => { const r = KXB.rows[+c.dataset.kxbUse]; r.skip = !c.checked; r.note = r.skip ? "O'tkazib yuboriladi" : ""; kxbRender(); });
  const refit = r => { const L = (DS.data.lessons || []).find(l => l.key === r.lkey); r.code = L ? L.code : ""; r.how = L ? (r.how || "aniq") : "";
    r.skip = !(r.lkey && r.kind); r.note = r.skip ? (!r.lkey ? "Darsni tanlang" : "Turini tanlang") : ""; kxbRender(); };
  el.querySelectorAll("[data-kxb-l]").forEach(s => s.onchange = () => { const r = KXB.rows[+s.dataset.kxbL]; r.lkey = +s.value; if (r.lkey) r.how = "qo'lda"; refit(r); });
  el.querySelectorAll("[data-kxb-k]").forEach(s => s.onchange = () => { const r = KXB.rows[+s.dataset.kxbK]; r.kind = s.value; refit(r); });
}
async function kxbRun(retry) {
  const lim = (PK.meta && PK.meta.limits) || {};
  KXB.rows.forEach(r => { r.inq = retry ? r.inq !== false && !r.skip && r.res !== "ok" : !r.skip; if (r.inq) { r.res = ""; } });
  KXB.phase = "run"; KXB.stop = false; kxbRender();
  const todo = KXB.rows.filter(r => r.inq);
  for (const r of todo) {
    if (KXB.stop) { r.res = "stop"; kxbSetRow(r); continue; }
    const mb = r.kind === "video" ? lim.video_mb : r.kind === "subs" ? lim.subs_mb : lim.asset_mb;
    if (mb && r.size > mb * 1048576) { r.res = "bad"; r.err = `Fayl katta: ${(r.size / 1048576).toFixed(1)} MB (chegara — ${mb} MB)`; kxbSetRow(r); continue; }
    r.res = "run"; r.pct = 0; kxbSetRow(r);
    const res = await pkSend(`/api/paket/courses/${DS.cid}/topics/${r.lkey}/upload?name=${encodeURIComponent(r.name)}&as=${r.kind}`, KXB.files[r.i],
      p => { r.pct = p; const c = document.querySelector(`#kxbPanel [data-st="${r.i}"] .kxb-run`); if (c) c.textContent = `Yuklanmoqda… ${Math.round(p * 100)}%`; kxbProgress(); });
    if (res.status === 401) { KXB.stop = true; r.res = "stop"; showLogin(); kxbSetRow(r); continue; }
    if (res.ok) {
      r.res = "ok"; r.label = (res.data && res.data.label) || "yuklandi"; KXB.dirty = true;
      const na = res.data && res.data.needs_answer && res.data.needs_answer.length;
      if (na) r.label += ` · ${na} ta savol javobsiz — darsni ochib «To'g'ri javobni tanlang»`;
    }
    else { r.res = "bad"; r.err = kxbErr(res, r.size); }
    kxbSetRow(r);
  }
  KXB.phase = "done"; kxbRender();
}
