/* =====================================================================
   «Kurs muharriri» (app/kurs.py, /api/kurs) — bloklardan kurs (Articulate Rise 360 o'rniga), docs/kurs.md.
     Kurslar:   ro'yxat (holat, qidiruv), «Yangi kurs», «Rise'dan import» (.zip → hisobot + sifat hisoboti).
     Kurs:      chapda darslar (sudrab tartiblash, dars / test qo'shish), markazda dars (bloklar, «+» — blok kutubxonasi, joyida tahrirlash,
                yuqoriga/pastga/sudrash, nusxa, o'chirish va «Bekor qilish»), o'ngda tanlangan blok sozlamalari. Avtosaqlash (rev — ziddiyat 409),
                ko'rish (kompyuter / planshet / telefon), kurs sozlamalari, versiyalar, sifat hisoboti, eksport (xAPI / SCORM / HTML),
                ko'rib chiqishga yuborish / tasdiqlash / qaytarish.
     Rahbariyat: faqat jamlangan sonlar.
   Ruxsat va ko'lam — serverda. Global: renderKurs(). app.js yordamchilari: $, esc, toast, locked, errCard, showLogin, ico, ICONS, ME, go, arm.
   ===================================================================== */
const KU = {meta: null, who: null, view: "list", cid: 0, course: null, lid: 0, lesson: null, blocks: [], title: "", quiz: null, rev: 0,
            dirty: false, saving: false, again: false, saveT: 0, sel: -1, state: "", conflict: null, list: {q: "", status: "", fan: 0}, trash: null, pv: null,
            cm: null, cmOpen: false, cmBlock: null, cmAll: false, cmDone: false};
function kuReset() { clearTimeout(KU.saveT); Object.assign(KU, {meta: null, who: null, view: "list", cid: 0, course: null, lid: 0, lesson: null, blocks: [], title: "", quiz: null, rev: 0,
  dirty: false, saving: false, again: false, sel: -1, state: "", conflict: null, list: {q: "", status: "", fan: 0}, trash: null, pv: null,
  cm: null, cmOpen: false, cmBlock: null, cmAll: false, cmDone: false}); }
if (typeof ICONS === "object") {
  const I = {plus: '<path d="M12 5v14M5 12h14"/>', trash: '<path d="M4 7h16M10 11v6M14 11v6M6 7l1 12a2 2 0 0 0 2 2h6a2 2 0 0 0 2-2l1-12M9 7V4h6v3"/>',
    copy: '<rect x="9" y="9" width="12" height="12" rx="2"/><path d="M5 15V5a2 2 0 0 1 2-2h10"/>', up: '<path d="m6 15 6-6 6 6"/>', down: '<path d="m6 9 6 6 6-6"/>',
    grip: '<circle cx="9" cy="6" r="1.2"/><circle cx="15" cy="6" r="1.2"/><circle cx="9" cy="12" r="1.2"/><circle cx="15" cy="12" r="1.2"/><circle cx="9" cy="18" r="1.2"/><circle cx="15" cy="18" r="1.2"/>',
    gear: '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 0 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 0 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 0 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 0 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z"/>',
    image: '<rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="9" cy="9" r="2"/><path d="m21 15-5-5L5 21"/>', upload: '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><path d="m17 8-5-5-5 5"/><path d="M12 3v12"/>',
    download: '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><path d="m7 10 5 5 5-5"/><path d="M12 15V3"/>', layers: '<path d="m12 2 10 5-10 5L2 7z"/><path d="m2 17 10 5 10-5"/><path d="m2 12 10 5 10-5"/>',
    quiz: '<circle cx="12" cy="12" r="10"/><path d="M9.1 9a3 3 0 0 1 5.8 1c0 2-3 3-3 3"/><path d="M12 17h.01"/>', undo: '<path d="M9 14 4 9l5-5"/><path d="M4 9h10.5a5.5 5.5 0 0 1 0 11H11"/>',
    tablet: '<rect x="4" y="2" width="16" height="20" rx="2"/><path d="M12 18h.01"/>', phone2: '<rect x="7" y="2" width="10" height="20" rx="2"/><path d="M12 18h.01"/>',
    bold: '<path d="M6 4h8a4 4 0 0 1 0 8H6zM6 12h9a4 4 0 0 1 0 8H6z"/>', italic: '<path d="M19 4h-9M14 20H5M15 4 9 20"/>', underline: '<path d="M6 4v6a6 6 0 0 0 12 0V4M4 20h16"/>',
    link: '<path d="M10 13a5 5 0 0 0 7.5.5l3-3a5 5 0 0 0-7-7l-1.7 1.7"/><path d="M14 11a5 5 0 0 0-7.5-.5l-3 3a5 5 0 0 0 7 7l1.7-1.7"/>', ul: '<path d="M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01"/>',
    eraser: '<path d="m7 21-4-4L14 6l7 7-8 8z"/><path d="M22 21H7"/>', back: '<path d="m15 18-6-6 6-6"/>', history: '<path d="M3 12a9 9 0 1 0 3-6.7L3 8"/><path d="M3 3v5h5M12 7v5l4 2"/>',
    more: '<circle cx="5" cy="12" r="1.4"/><circle cx="12" cy="12" r="1.4"/><circle cx="19" cy="12" r="1.4"/>', list2: '<path d="M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01"/>',
    text: '<path d="M4 7V5h16v2M9 19h6M12 5v14"/>', video2: '<rect x="2" y="5" width="15" height="14" rx="2"/><path d="m17 10 5-3v10l-5-3"/>', gallery: '<rect x="3" y="5" width="13" height="13" rx="2"/><path d="M20 8v11a2 2 0 0 1-2 2H7"/>',
    cont: '<rect x="3" y="9" width="18" height="6" rx="1"/>', cards: '<rect x="3" y="7" width="13" height="13" rx="2"/><path d="M8 7V5a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2h-3"/>',
    match: '<path d="M4 7h6M4 17h6M14 7h6M14 17h6M10 7l4 10M10 17l4-10"/>', blocks: '<rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/>',
    panel: '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M9 4v16"/>'};
  Object.entries(I).forEach(([k, v]) => { if (!ICONS["ku_" + k]) ICONS["ku_" + k] = v; });
}
if (!document.querySelector('link[href="kurs.css"]')) document.head.insertAdjacentHTML("beforeend", '<link rel="stylesheet" href="kurs.css">');
const kuI = (n, s = 16) => ico("ku_" + n, s);
/* Ko'rinish: «rise» — Articulate Rise kabi (dars natijadagidek: muqova, binafsha «davom etish», oq kartochkalar; asboblar blok ustida, darslar va
   blok sozlamalari yon panelda) / «classic» — uch ustunli. Tanlov brauzerda saqlanadi (localStorage), standart — «rise». */
function kuUi() { try { return localStorage.getItem("kuUi") === "classic" ? "classic" : "rise"; } catch (e) { return "rise"; } }
function kuUiSet(v) { try { localStorage.setItem("kuUi", v); } catch (e) { /* jim */ } }
const kuRise = () => KU.view === "course" && kuUi() === "rise";
const KU_ST = {qoralama: "", korib_chiqishda: "info", tasdiqlangan: "ok"};
const KU_MODE = {xapi: "NEXTID uchun — xAPI (standart)", scorm12: "Boshqa LMS — SCORM 1.2", scorm2004: "Boshqa LMS — SCORM 2004 (4-nashr)", none: "LMS'siz — oddiy veb-sahifa"};
const kuChip = (t, cls = "") => `<span class="ku-chip ${cls}">${esc(t)}</span>`;
const kuD = s => { s = String(s || ""); return s.length >= 10 ? `${s.slice(8, 10)}.${s.slice(5, 7)}.${s.slice(0, 4)}${s.length >= 16 ? " " + s.slice(11, 16) : ""}` : "—"; };
const kuSize = b => b >= 1048576 ? `${(b / 1048576).toFixed(1).replace(".", ",")} MB` : `${Math.max(1, Math.round((b || 0) / 1024))} KB`;
const kuUid = () => "b" + Array.from(crypto.getRandomValues(new Uint8Array(5)), x => x.toString(16).padStart(2, "0")).join("");
const kuClone = o => JSON.parse(JSON.stringify(o));
const kuErr = d => { const det = d && d.detail; return (typeof det === "string" ? det : det?.message) || (Array.isArray(det) ? "Maydonlarni tekshiring" : "") || "Xatolik yuz berdi"; };

async function kuFetch(url, body, method) {
  const r = await fetch(url, {method: method || (body === undefined ? "GET" : "POST"), credentials: "same-origin",
    headers: body === undefined || body instanceof Blob ? {} : {"Content-Type": "application/json"}, body: body === undefined ? undefined : body instanceof Blob ? body : JSON.stringify(body)});
  if (r.status === 401) { showLogin(); throw new Error("auth"); }
  const data = await r.json().catch(() => ({}));
  return {ok: r.ok, status: r.status, data};
}
/* GET — xato bo'lsa istisno (sahifa xato kartasi); POST — xato bo'lsa toast va null */
async function kuApi(url, body, method) {
  const r = await kuFetch(url, body, method);
  if (!r.ok) {
    if (body === undefined && !method) { const e = new Error(r.status === 403 ? "denied" : "api"); e.msg = kuErr(r.data); throw e; }
    const det = r.data?.detail;
    toast(kuErr(r.data) + (det?.errors?.length ? ` (${det.errors.slice(0, 2).join("; ")}${det.errors.length > 2 ? " …" : ""})` : ""));
    return null;
  }
  return r.data;
}
function kuModal(title, html, {onOk = null, okText = "Saqlash", wide = false, onClose = null, cls = ""} = {}) {
  const bg = document.createElement("div"); bg.className = "ku-modal-bg";
  if (typeof kuRise === "function" && kuRise()) bg.classList.add("rz");   /* Rise ko'rinishi: modallar ham binafsha palitrada (body'ga qo'shiladi) */
  bg.innerHTML = `<div class="ku-modal ${wide ? "wide" : ""} ${cls}" role="dialog" aria-modal="true" aria-label="${esc(title)}"><div class="ku-modal-h"><h3>${esc(title)}</h3>
    <button type="button" class="ku-ib" data-x aria-label="Yopish">${ico("x", 18)}</button></div><div class="ku-modal-b">${html}</div>
    ${onOk ? `<div class="ku-acts end"><button type="button" class="btn ghost" data-x>Bekor qilish</button><button type="button" class="btn primary" data-ok>${esc(okText)}</button></div>` : ""}</div>`;
  document.body.appendChild(bg);
  const opener = document.activeElement;
  const close = () => { bg.remove(); opener?.focus?.({preventScroll: true}); onClose?.(); };
  bg._close = close;
  bg.addEventListener("mousedown", e => { if (e.target === bg) close(); });
  bg.addEventListener("click", e => { if (e.target.closest("[data-x]")) close(); });
  bg.addEventListener("keydown", e => { if (e.key === "Escape") { e.stopPropagation(); close(); } });
  const ok = bg.querySelector("[data-ok]");
  if (ok) ok.onclick = async () => { ok.disabled = true; try { if (await onOk(bg)) close(); } finally { if (ok.isConnected) ok.disabled = false; } };
  setTimeout(() => (bg.querySelector("[autofocus]") || bg.querySelector(".ku-modal-b input, .ku-modal-b select, .ku-modal-b textarea, .ku-modal-b button") || bg.querySelector("[data-x]"))?.focus(), 30);
  return bg;
}
/* fayl yuklash (XHR — jarayon foizi ko'rinadi). → asset qatori yoki null */
function kuUpload(kind, file, extra = "") {
  const M = KU.meta, lim = {image: M.limits.image_mb, video: M.limits.video_mb, audio: M.limits.audio_mb, vtt: M.limits.vtt_mb, file: M.limits.file_mb}[kind] || 50;
  if (file.size > lim * 1048576) { toast(`«${file.name}» — fayl ${lim} MB dan katta`); return Promise.resolve(null); }
  return kuXhr(`/api/kurs/courses/${KU.cid}/assets?kind=${kind}&name=${encodeURIComponent(file.name)}${extra}`, file, `«${file.name}» yuklanmoqda`);
}
function kuXhr(url, file, label) {
  return new Promise(res => {
    const x = new XMLHttpRequest(), st = kuProgress(label);
    x.open("POST", url); x.withCredentials = true;
    x.upload.onprogress = e => { if (e.lengthComputable) st.set(Math.round(100 * e.loaded / e.total)); };
    x.onload = () => {
      st.done(); let d = {}; try { d = JSON.parse(x.responseText || "{}"); } catch (e) {}
      if (x.status === 401) { showLogin(); return res(null); }
      if (x.status >= 400) { toast(kuErr(d)); return res(null); }
      res(d);
    };
    x.onerror = () => { st.done(); toast("Yuklab bo'lmadi — aloqani tekshiring"); res(null); };
    x.send(file);
  });
}
function kuProgress(label) {
  let box = document.getElementById("kuProg");
  if (!box) { box = document.createElement("div"); box.id = "kuProg"; box.className = "ku-prog"; box.setAttribute("role", "status"); document.body.appendChild(box); }
  const row = document.createElement("div"); row.innerHTML = `<span>${esc(label)}</span><b>0%</b><i><s style="width:0"></s></i>`; box.appendChild(row);
  return {set: p => { row.querySelector("b").textContent = p + "%"; row.querySelector("s").style.width = p + "%"; }, done: () => { row.remove(); if (!box.children.length) box.remove(); }};
}
function kuPickFile(accept, multiple = false) {
  return new Promise(res => {
    const i = document.createElement("input"); i.type = "file"; i.accept = accept; i.multiple = multiple; i.hidden = true;
    i.onchange = () => { res([...i.files]); i.remove(); };
    document.body.appendChild(i); i.click();
    setTimeout(() => { if (i.isConnected && !i.files.length) { /* bekor qilindi — onchange chaqirilmaydi */ } }, 60000);
  });
}

/* ---------- kirish nuqtasi ---------- */
async function renderKurs() {
  const v = $("#v-kurs"), who = typeof ME !== "undefined" ? ME : null;
  if (KU.who !== who) {        /* birinchi kirish — tashqi havola (go("kurs", {cid}), «Dars tayyorlash» → «Muharrirda tahrirlash») qo'ygan kurs saqlanadi */
    const keep = (KU.who === null || KU.who === undefined) && KU.view === "course" ? KU.cid : 0;
    kuReset(); KU.who = who;
    if (keep) { KU.view = "course"; KU.cid = keep; }
  }
  if (!KU.meta) { const m = await kuApi("/api/kurs/meta"); if (KU.who !== who) return; KU.meta = m; }
  if (KU.meta.caps.summary_only) return kuSummary(v);
  if (KU.view === "course" && KU.cid) return kuOpen(KU.cid, KU.lid);
  return kuList(v);
}

async function kuSummary(v) {
  const s = await kuApi("/api/kurs/summary");
  const k = (l, n, sub = "", cls = "") => `<div class="ku-kpi ${cls}"><span>${esc(l)}</span><b>${n}</b>${sub ? `<small>${esc(sub)}</small>` : ""}</div>`;
  v.innerHTML = `<div class="ku-head"><div><h2>Kurs muharriri</h2><span class="muted">Jamlangan ko'rsatkichlar · kurslar tarkibi va tahrirlash — Masofaviy ta'lim bo'limida</span></div></div>
    <div class="ku-kpis">${k("Kurslar", s.courses, `${s.authors} ta muallif`)}${k("Tasdiqlangan", s.by_status.tasdiqlangan, "", "ok")}${k("Ko'rib chiqishda", s.by_status.korib_chiqishda, "", "info")}
    ${k("Qoralama", s.by_status.qoralama)}${k("Darslar", s.lessons, `${s.blocks} ta blok`)}${k("Rise'dan import", s.imported, `${s.exports} ta eksport`)}</div>`;
}

/* ---------- kurslar ro'yxati ---------- */
async function kuList(v) {
  KU.view = "list"; KU.cid = 0; KU.course = null;
  v = v || $("#v-kurs"); v.classList.remove("ku-rise");
  const M = KU.meta, L = KU.list;
  const d = await kuApi(`/api/kurs/courses?q=${encodeURIComponent(L.q)}&status=${L.status}&fan=${+L.fan || 0}`);
  const all = d.counts, tot = Object.values(all).reduce((a, b) => a + b, 0);
  const st = (k, t) => `<button type="button" class="${L.status === k ? "on" : ""}" data-st="${k}">${esc(t)} <small>${k ? all[k] : tot}</small></button>`;
  const fans = d.fans || [], groups = d.groups || [];
  if (L.fan && !fans.some(f => f.dl_course_id === +L.fan)) L.fan = 0;
  v.innerHTML = `<div class="ku-head"><div><h2>Kurs muharriri</h2><span class="muted">${esc(M.scope)} · bloklardan kurs yig'ing va NEXTID uchun xAPI paket oling</span></div>
      <div class="ku-acts">${M.caps.approve ? `<button type="button" class="btn ghost" id="kuReady" title="Masofaviy ta'limga kirish kursi: platforma, muddatlar, yordam, akademik halollik, AI, o'qish odatlari — bilimni tekshirish va nishon bilan">${kuI("plus")} «ISFT Ready» shabloni</button>` : ""}
        <button type="button" class="btn ghost" id="kuImp">${kuI("upload")} Rise'dan import</button><button type="button" class="btn primary" id="kuNew">${kuI("plus")} Yangi kurs</button></div></div>
    ${!M.player ? `<div class="ku-warn">${ico("alert", 15)}<span>Kurs pleyeri o'rnatilmagan — ko'rish va eksport vaqtincha ishlamaydi. Kursni tahrirlash mumkin.</span></div>` : ""}
    <div class="ku-bar"><div class="ku-seg" role="group" aria-label="Holat bo'yicha">${st("", "Hammasi")}${Object.entries(M.status).map(([k, t]) => st(k, t)).join("")}</div>
      <div class="ku-filt">${fans.length ? `<select class="ku-in" id="kuFan" aria-label="Fan bo'yicha"><option value="0">Barcha fanlar</option>${fans.map(f => `<option value="${f.dl_course_id}" ${+L.fan === f.dl_course_id ? "selected" : ""}>${esc(f.subject)}${f.direction ? " · " + esc(f.direction) : ""} (${f.n})</option>`).join("")}</select>` : ""}
      <label class="ku-search">${ico("search", 16)}<input type="search" id="kuQ" placeholder="Kurs, fan yoki muallif" value="${esc(L.q)}" aria-label="Qidirish"></label></div></div>
    ${d.items.length ? kuGroupsHtml(d) : `<div class="ku-empty"><b>Kurs yo'q</b><span>${L.q || L.fan || L.status ? "Filtr bo'yicha kurs topilmadi." : "«Yangi kurs» bilan boshlang yoki Rise 360 eksportini import qiling."}</span></div>`}`;
  v.querySelectorAll("[data-st]").forEach(b => b.onclick = () => { L.status = b.dataset.st; kuList(v); });
  const fs = $("#kuFan"); if (fs) fs.onchange = () => { L.fan = +fs.value || 0; kuList(v); };
  v.querySelectorAll("[data-grp]").forEach(b => b.onclick = () => {
    const k = b.dataset.grp, open = b.getAttribute("aria-expanded") !== "true";
    b.setAttribute("aria-expanded", open); b.closest(".ku-grp").classList.toggle("open", open); kuGrpSave(k, open);
  });
  let t = 0; $("#kuQ").oninput = e => { clearTimeout(t); t = setTimeout(() => { L.q = e.target.value; kuList(v).then(() => { const q = $("#kuQ"); q.focus(); q.setSelectionRange(q.value.length, q.value.length); }); }, 300); };
  v.querySelectorAll("[data-open]").forEach(b => b.onclick = () => kuOpen(+b.dataset.open));
  $("#kuNew").onclick = kuNewCourse;
  $("#kuImp").onclick = kuImport;
  /* «ISFT Ready» (app/isft_ready.py): mavjud bo'lsa — o'sha kurs ochiladi, aks holda qoralama yaratiladi (tasdiqlash va eksport — odatdagidek) */
  $("#kuReady")?.addEventListener("click", async () => {
    const r = await kuApi("/api/kurs/isft-ready", {});
    if (!r) return;
    toast(r.created ? "«ISFT Ready» qoralamasi yaratildi — ko'rib chiqing, tasdiqlang va xAPI eksport qiling" : "«ISFT Ready» kursi allaqachon bor — ochildi");
    kuOpen(r.id);
  });
}
function kuCourseCard(c) {
  return `<button type="button" class="ku-card" data-open="${c.id}" style="--acc:${esc(c.accent)}">
    <div class="ku-card-img">${c.cover ? `<img src="${esc(c.cover)}" alt="" loading="lazy">` : `<span>${kuI("layers", 28)}</span>`}</div>
    <div class="ku-card-b"><b>${esc(c.title)}</b><small class="muted">${esc(c.author_name || "")}${c.dl_subject ? " · " + esc(c.dl_subject) : ""}</small>
    <div class="ku-card-f">${kuChip(c.status_label, KU_ST[c.status])}${c.src === "rise" ? kuChip("Rise'dan") : c.src === "demo" ? kuChip("Namuna") : ""}<span class="muted">${c.lessons} ta dars · ${kuD(c.updated_at)}</span></div></div></button>`;
}
/* «Dars tayyorlash» bilan bog'langan kurslar — fan bo'yicha yig'iladigan guruhlar (holat — har foydalanuvchi uchun localStorage'da), qolganlari — «Mustaqil kurslar» */
const kuGrpKey = () => "jarvis.kuGroups." + String((KU.who && (KU.who.id ?? KU.who.user_id)) ?? KU.who ?? "");
function kuGrpState() { try { const v = JSON.parse(localStorage.getItem(kuGrpKey()) || "{}"); return v && typeof v === "object" ? v : {}; } catch (e) { return {}; } }
function kuGrpSave(k, open) { try { const s = kuGrpState(); s[k] = open ? 1 : 0; localStorage.setItem(kuGrpKey(), JSON.stringify(s)); } catch (e) {} }
function kuGroupsHtml(d) {
  const L = KU.list, by = Object.fromEntries(d.items.map(c => [c.id, c])), saved = kuGrpState(), M = KU.meta;
  const filtered = !!(L.q || L.fan), groups = d.groups || [], solo = (d.standalone || []).map(i => by[i]).filter(Boolean);
  const isOpen = (k, dflt) => filtered ? true : (k in saved ? !!saved[k] : dflt);
  const grp = (k, title, sub, n, counts, body, dflt) => {
    const open = isOpen(k, dflt), cnt = counts ? Object.entries(counts).filter(([, x]) => x).map(([s, x]) => kuChip(`${(M.status || {})[s] || s} ${x}`, KU_ST[s])).join("") : "";
    return `<section class="ku-grp ${open ? "open" : ""}"><button type="button" class="ku-grp-h" data-grp="${esc(k)}" aria-expanded="${open}">
      <span class="ku-grp-c" aria-hidden="true">${kuI("down", 16)}</span><span class="ku-grp-t"><b>${esc(title)}</b>${sub ? `<small class="muted">${esc(sub)}</small>` : ""}</span>
      <span class="ku-grp-n">${cnt}<span class="ku-chip">${n} ta kurs</span></span></button><div class="ku-grp-b">${body}</div></section>`;
  };
  const rows = ids => `<div class="ku-rows">${ids.map(i => by[i]).filter(Boolean).map(kuCourseRow).join("")}</div>`;
  return `<div class="ku-grps">${groups.length ? `<h3 class="ku-grps-h">Fanlar bo'yicha <small class="muted">${groups.length} ta fan · ${groups.reduce((a, g) => a + g.n, 0)} ta kurs</small></h3>` : ""}
    ${groups.map(g => grp("f" + g.dl_course_id, g.subject, [g.direction, g.course ? `${g.course}-kurs` : ""].filter(Boolean).join(" · "), g.n, g.counts, rows(g.ids), groups.length === 1)).join("")}
    ${solo.length ? (groups.length ? grp("solo", "Mustaqil kurslar", "Dars tayyorlash bilan bog'lanmagan", solo.length, null, `<div class="ku-cards">${solo.map(kuCourseCard).join("")}</div>`, true)
                                   : `<div class="ku-cards">${solo.map(kuCourseCard).join("")}</div>`) : ""}</div>`;
}
function kuCourseRow(c) {
  const ds = c.dars || {};
  return `<button type="button" class="ku-row-c" data-open="${c.id}" style="--acc:${esc(c.accent)}"><span class="ku-row-code">${esc(ds.code || "—")}</span>
    <span class="ku-row-t"><b>${esc(c.title)}</b><small class="muted">${esc(c.author_name || "")} · ${c.lessons} ta dars · ${kuD(c.updated_at)}${ds.authority === "kurs" ? " · eksport: muharrir" : ""}</small></span>
    ${kuChip(c.status_label, KU_ST[c.status])}</button>`;
}
function kuNewCourse() {
  const M = KU.meta;
  kuModal("Yangi kurs", `<label class="ku-f"><span>Kurs nomi</span><input id="kuNt" maxlength="200" autofocus placeholder="Masalan: Mikroiqtisodiyot asoslari"></label>
    <label class="ku-f"><span>Masofaviy kurs (ixtiyoriy)</span><select id="kuNd"><option value="">— bog'lanmagan —</option>${(M.dl_courses || []).map(d => `<option value="${d.id}">${esc(d.subject)}${d.direction ? " · " + esc(d.direction) : ""}${d.course ? ` · ${d.course}-kurs` : ""}</option>`).join("")}</select></label>`,
    {okText: "Yaratish", onOk: async bg => {
      const title = bg.querySelector("#kuNt").value.trim();
      if (!title) { toast("Kurs nomini yozing"); return false; }
      const r = await kuApi("/api/kurs/courses", {title, dl_course_id: +bg.querySelector("#kuNd").value || null});
      if (r) { setTimeout(() => kuOpen(r.id), 0); return true; }
      return false;
    }});
}

/* ---------- Rise importi ---------- */
async function kuImport() {
  const [f] = await kuPickFile(".zip,application/zip");
  if (!f) return;
  if (f.size > KU.meta.limits.import_mb * 1048576) { toast(`Arxiv ${KU.meta.limits.import_mb} MB dan katta`); return; }
  const r = await kuXhr(`/api/kurs/import/rise?name=${encodeURIComponent(f.name)}`, f, `«${f.name}» import qilinmoqda`);
  if (!r) return;
  kuImportReport(r);
  if (KU.view === "list") kuList();
}
function kuImportReport(r) {
  const R = r.report, Mb = KU.meta.blocks;
  const rows = Object.entries(R.by_type).map(([t, n]) => `<tr><td>${esc(Mb[t]?.label || t)}</td><td class="n">${n}</td></tr>`).join("");
  const un = Object.entries(R.unmapped || {});
  kuModal("Rise importi natijasi", `<p class="ku-lead"><b>${esc(R.title)}</b> — qoralama kurs yaratildi (${esc(R.format)} eksporti).</p>
    <div class="ku-kpis sm">${[["Darslar", R.lessons], ["Testlar", R.quiz_lessons], ["Savollar", R.questions], ["Bloklar", R.blocks], ["Rasmlar", R.images.imported], ["Import qilinmadi", R.unmapped_total]]
      .map(([l, n], i) => `<div class="ku-kpi ${i === 5 && n ? "warn" : ""}"><span>${l}</span><b>${n}</b></div>`).join("")}</div>
    <div class="ku-2col"><div><h4>Bloklar turlari bo'yicha</h4><table class="ku-t"><tbody>${rows}</tbody></table></div>
      <div><h4>Import qilinmagan</h4>${un.length ? `<table class="ku-t"><tbody>${un.map(([k, n]) => `<tr><td><code>${esc(k)}</code></td><td class="n">${n}</td></tr>`).join("")}</tbody></table>
        <p class="ku-note">Bunday bloklar o'rnida «import qilinmadi: …» izohli matn bloki qo'yildi — qo'lda almashtiring.</p>` : `<p class="ku-note ok">Hamma bloklar import qilindi.</p>`}
        ${R.images.missing || R.images.failed ? `<p class="ku-note">Rasm topilmadi: ${R.images.missing}, o'qilmadi: ${R.images.failed}.</p>` : ""}</div></div>
    <h4>Sifat hisoboti</h4><div id="kuImpQ"></div>`, {wide: true});
  const bg = document.querySelector(".ku-modal-bg:last-child");
  bg.querySelector(".ku-modal-b").insertAdjacentHTML("beforeend", `<div class="ku-acts end"><button type="button" class="btn primary" id="kuImpOpen">Kursni ochish</button></div>`);
  bg.querySelector("#kuImpOpen").onclick = () => { bg._close(); kuOpen(r.course_id); };
  kuQualityMount(bg.querySelector("#kuImpQ"), r.course_id, r.quality);
}

/* ---------- kurs ekrani: chapda darslar, markazda dars, o'ngda blok sozlamalari ---------- */
async function kuOpen(cid, lid) {
  await kuFlush();
  const v = $("#v-kurs");
  const [co, as] = await Promise.all([kuApi(`/api/kurs/courses/${cid}`), kuApi(`/api/kurs/courses/${cid}/assets`).catch(() => ({items: []}))]);
  Object.assign(KU, {view: "course", cid, course: co, conflict: null, assets: Object.fromEntries(as.items.map(a => [a.id, a]))});
  const ls = co.lessons_list;
  lid = ls.some(l => l.id === lid) ? lid : (ls[0]?.id || 0);
  v.classList.toggle("ku-rise", kuUi() === "rise");
  v.innerHTML = `<div class="ku-top" style="--acc:${esc(co.accent)}"><button type="button" class="ku-ib" id="kuBack" aria-label="Kurslar ro'yxatiga qaytish" title="Kurslar">${kuI("back", 18)}</button>
      <button type="button" class="ku-ib only-rise" id="kuSideT" aria-controls="kuSide" aria-expanded="false" title="Darslar ro'yxati">${kuI("panel", 18)}</button>
      <div class="ku-top-t"><button type="button" class="ku-ct" id="kuCt" title="Kurs sozlamalari">${esc(co.title)}</button>
        <div class="ku-top-s"><span id="kuStChip">${kuChip(co.status_label, KU_ST[co.status])}</span><span class="ku-save" id="kuSave" role="status" aria-live="polite"></span>
          <span id="kuLive" aria-live="polite" aria-atomic="true" style="position:absolute;width:1px;height:1px;margin:-1px;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap"></span></div></div>
      <div class="ku-top-a" id="kuTopA"></div></div>
    <div id="kuNote"></div>
    <div class="ku-ed" style="--acc:${esc(co.accent)}"><aside class="ku-side" id="kuSide" aria-label="Darslar"></aside><section class="ku-canvas" id="kuCanvas" aria-label="Dars"></section>
      <aside class="ku-panel" id="kuPanel" aria-label="Blok sozlamalari"></aside></div>
    <aside class="ku-cm" id="kuCm" aria-label="Izohlar" ${KU.cmOpen ? "" : "hidden"}></aside>`;
  $("#kuBack").onclick = async () => { await kuFlush(); if (KU.course?.dars?.linked && typeof dsOpenSubject === "function") return dsOpenSubject(KU.course.dars.dl_course_id); kuList(); };
  KU.cm = null; kuCmLoad(); KU.capJobs = {}; kuCapLoad();
  $("#kuCt").onclick = kuSettings;
  $("#kuSideT").onclick = () => { const s = $("#kuSide"), o = !s.classList.contains("open"); s.classList.toggle("open", o); $("#kuSideT").setAttribute("aria-expanded", String(o)); };
  kuTop(); kuNote(); kuRenderSide();
  kuBindCanvas(); kuBindPanel();
  if (lid) await kuLoadLesson(lid, true);
  else { KU.lid = 0; $("#kuCanvas").innerHTML = `<div class="ku-empty"><b>Kursda dars yo'q</b><span>Chapdagi «+ Dars» tugmasi bilan qo'shing.</span></div>`; kuRenderPanel(); }
}
function kuTop() {
  const co = KU.course, c = co.caps, a = $("#kuTopA"); if (!a) return;
  if (kuRise()) return kuTopRise(co, c, a);
  a.innerHTML = `<button type="button" class="btn sm ghost" id="kuUiT" title="Articulate Rise kabi ko'rinish">${kuI("layers", 15)} Rise ko'rinishi</button><button type="button" class="btn sm ghost" id="kuPv">${ico("eye", 15)} Ko'rish</button>
    <button type="button" class="btn sm ghost" id="kuQl">${ico("checkc", 15)} Sifat</button>
    ${c.write ? `<button type="button" class="btn sm ghost" id="kuVr">${kuI("history", 15)} Versiyalar</button>
    <button type="button" class="btn sm ghost" id="kuSt">${kuI("gear", 15)} Sozlamalar</button>
    <button type="button" class="btn sm ghost" id="kuEx">${kuI("download", 15)} Eksport</button>` : ""}
    <button type="button" class="btn sm ghost" id="kuCmBtn" aria-controls="kuCm">${ico("chat", 15)} Izohlar</button>
    ${c.write ? `<button type="button" class="btn sm ghost" id="kuAq" title="Har bloklar darsidan keyin 3–5 savollik past xavfli test — Test bankdagi tasdiqlangan savollardan (takrorsiz)">${kuI("quiz", 15)} Dars oxiri testlari</button>` : ""}
    ${KU.meta.caps.ai && c.write ? `<button type="button" class="btn sm ghost" id="kuAi" title="Ma'ruza hujjatidan (Word / PDF) bloklar, kartochkalar va test — AI">${ico("spark", 15)} AI: hujjatdan dars</button>` : ""}
    ${c.submit ? `<button type="button" class="btn sm primary" id="kuSub">Ko'rib chiqishga yuborish</button>` : ""}
    ${c.approve && co.status !== "tasdiqlangan" ? `<button type="button" class="btn sm primary" id="kuApp">Tasdiqlash</button>` : ""}
    ${c.approve && co.status !== "qoralama" ? `<button type="button" class="btn sm ghost" id="kuRet">Qaytarish</button>` : ""}`;
  kuTopBind(c);
}
/* Konstruktor (A versiya) qadamlar tasmasi shu kursda faolmi */
const kuCanDone = c => !!(c.write || c.submit || c.approve);
const kuWiz = () => { const co = KU.course; return KU.wiz && co && co.dars && co.dars.linked && co.dars.dl_course_id === KU.wiz.cid ? KU.wiz : null; };
/* Rise ko'rinishidagi yuqori panel: bitta asosiy tugma — «Tayyor» (nashr qadamlari oynasi); Ko'rish, Izohlar va «Yana» menyusi (sifat, eksport, versiyalar,
   sozlamalar, yuborish / tasdiqlash…). Telefonda — bir qatorli ixcham panel (faqat belgilar). Konstruktor qadamlar tasmasi bor bo'lsa «Tayyor» o'sha tasmada. */
function kuTopRise(co, c, a) {
  const mi = (id, ic, t, tip = "") => `<button type="button" class="ku-mi" id="${id}" role="menuitem" ${tip ? `title="${esc(tip)}"` : ""}>${ic}<span>${t}</span></button>`;
  const ib = (id, ic, t, ex = "") => `<button type="button" class="btn sm ghost ku-tb" id="${id}" aria-label="${esc(t)}" title="${esc(t)}" ${ex}>${ic}<span class="lb">${esc(t)}</span></button>`;
  a.innerHTML = `${ib("kuPv", ico("eye", 17), "Ko'rish")}${ib("kuCmBtn", ico("chat", 17), "Izohlar", 'aria-controls="kuCm"')}
    <details class="ku-more"><summary class="btn sm ghost ku-tb" aria-label="Yana" title="Yana">${kuI("more", 18)}<span class="lb">Yana</span></summary><div class="ku-menu" role="menu">
      ${mi("kuQl", ico("checkc", 15), "Sifat tekshiruvi")}
      ${c.write ? mi("kuEx", kuI("download", 15), "Eksport (NEXTID uchun xAPI)") : ""}
      ${c.write ? mi("kuVr", kuI("history", 15), "Versiyalar") + mi("kuSt", kuI("gear", 15), "Kurs sozlamalari") : ""}
      ${c.write ? mi("kuAq", kuI("quiz", 15), "Dars oxiri testlari", "Har bloklar darsidan keyin 3–5 savollik past xavfli test — Test bankdagi tasdiqlangan savollardan") : ""}
      ${KU.meta.caps.ai && c.write ? mi("kuAi", ico("spark", 15), "AI: hujjatdan dars", "Ma'ruza hujjatidan (Word / PDF) bloklar, kartochkalar va test — AI") : ""}
      ${c.submit ? mi("kuSub", ico("send", 15), "Ko'rib chiqishga yuborish") : ""}
      ${c.approve && co.status !== "tasdiqlangan" ? mi("kuApp", ico("check", 15), "Tasdiqlash") : ""}
      ${c.approve && co.status !== "qoralama" ? mi("kuRet", ico("x", 15), "Muallifga qaytarish") : ""}
      ${mi("kuUiT", kuI("panel", 15), "Klassik ko'rinish (3 ustun)")}</div></details>
    ${kuWiz() || !kuCanDone(c) ? "" : `<button type="button" class="btn sm primary ku-done" id="kuDone" title="Tekshirish, eksport va ko'rib chiqishga yuborish">Tayyor</button>`}`;
  a.querySelectorAll(".ku-menu .ku-mi:not(#kuAq):not(#kuSub):not(#kuApp)").forEach(b => b.addEventListener("click", () => { const d = b.closest("details"); if (d) d.open = false; }));
  if (!window._kuMoreBound) {
    window._kuMoreBound = true;
    document.addEventListener("click", e => { const d = document.querySelector("#kuTopA .ku-more"); if (d && d.open && !d.contains(e.target)) d.open = false; });
    document.addEventListener("keydown", e => { if (e.key !== "Escape") return; const d = document.querySelector("#kuTopA .ku-more"); if (d && d.open) { d.open = false; d.querySelector("summary")?.focus(); } });
  }
  $("#kuDone") && ($("#kuDone").onclick = () => kuPublish());
  kuTopBind(c);
}
function kuTopBind(c) {
  const co = KU.course;
  $("#kuUiT") && ($("#kuUiT").onclick = async () => { await kuFlush(); kuUiSet(kuRise() ? "classic" : "rise"); kuOpen(KU.cid, KU.lid); });
  $("#kuPv").onclick = kuPreview; $("#kuQl").onclick = kuQuality; if (c.write) { $("#kuVr").onclick = kuVersions; $("#kuSt").onclick = kuSettings; $("#kuEx").onclick = kuExport; }
  $("#kuCmBtn").onclick = () => KU.cmOpen ? kuCmClose() : kuCmOpen(null); kuCmCount();
  $("#kuAi") && ($("#kuAi").onclick = kuAiLesson);
  /* dars oxiri testlari (app/dars_testi.py): bir bosishda — natija modalda (qo'shilgan / o'tkazib yuborilgan sabablari bilan) */
  $("#kuAq") && ($("#kuAq").onclick = e => { if (arm(e.currentTarget, "Qo'shilsinmi?")) (async () => {
    await kuFlush();
    const r = await kuFetch(`/api/kurs/courses/${KU.cid}/dars-testlari`, {});
    if (!r.ok) { toast(kuErr(r.data)); return; }
    const d = r.data; KU.course = d.course; kuRenderSide(); kuTop(); kuStatusChip();
    kuModal("Dars oxiri testlari", `<p>${d.added.length ? `Qo'shildi: <b>${d.added.length}</b> ta test (${d.added.reduce((a, x) => a + x.questions, 0)} savol) — Test bankdagi tasdiqlangan savollardan, takrorsiz, aralashtirilgan; urinishlar cheklanmagan, o'tish bali 60 %.` : "Yangi test qo'shilmadi."}
      ${d.already ? ` Avval qo'shilgan: ${d.already}.` : ""}</p>
      ${d.skipped.length ? `<p class="muted">O'tkazib yuborildi:</p><ul>${d.skipped.map(s => `<li>${esc(s.lesson || "#" + s.lesson_id)} — ${esc(s.reason)}</li>`).join("")}</ul>` : ""}
      <p class="muted">Avvalgi holat versiyalarda saqlandi (Versiyalar → tiklash).</p>`, {okText: "Yopish", onOk: () => true});
  })(); });
  /* to'xtatuvchi izohlar ochiq bo'lsa server 409 qaytaradi — sabab yozib aylanib o'tish mumkin (audit jurnaliga yoziladi) */
  const act = async (action, note = "", override = "") => {
    await kuFlush();
    const r = await kuFetch(`/api/kurs/courses/${KU.cid}/action`, {action, note, override});
    if (r.status === 409 && r.data?.detail?.gate) return kuGate(r.data.detail, ov => act(action, note, ov));
    if (!r.ok) { const det = r.data?.detail; toast(kuErr(r.data) + (det?.errors?.length ? ` (${det.errors.slice(0, 2).join("; ")})` : "")); return false; }
    KU.course = r.data.course; kuTop(); kuNote(); kuStatusChip(); toast({submit: "Ko'rib chiqishga yuborildi", approve: "Kurs tasdiqlandi", return: "Kurs muallifga qaytarildi"}[action]); return true;
  };
  KU.act = act;
  $("#kuSub") && ($("#kuSub").onclick = e => { if (arm(e.currentTarget, "Yuborilsinmi?")) act("submit"); });
  $("#kuApp") && ($("#kuApp").onclick = e => { if (arm(e.currentTarget, "Tasdiqlansinmi?")) act("approve"); });
  $("#kuRet") && ($("#kuRet").onclick = () => kuModal("Kursni qaytarish", `<label class="ku-f"><span>Sabab (muallif ko'radi)</span><textarea id="kuRn" rows="3" maxlength="500" autofocus></textarea></label>`,
    {okText: "Qaytarish", onOk: async bg => { const n = bg.querySelector("#kuRn").value.trim(); if (!n) { toast("Sababni yozing"); return false; } return act("return", n); }}));
}
function kuStatusChip() { const co = KU.course, el = $("#kuStChip"); if (el) el.innerHTML = kuChip(co.status_label || KU.meta.status[co.status], KU_ST[co.status]); }
function kuNote() {
  const el = $("#kuNote"), co = KU.course; if (!el) return;
  if (KU.conflict) {
    el.innerHTML = `<div class="ku-warn bad" role="alert">${ico("alert", 16)}<span>${esc(KU.conflict.message || "Ziddiyat")}</span>
      <span class="ku-acts"><button type="button" class="btn sm ghost" id="kuCfL">Oxirgi holatni yuklash</button><button type="button" class="btn sm primary" id="kuCfS">Mening nusxamni saqlash</button></span></div>`;
    $("#kuCfL").onclick = () => { KU.dirty = false; KU.conflict = null; kuNote(); kuLoadLesson(KU.lid, true); };
    $("#kuCfS").onclick = () => { KU.conflict = null; kuNote(); kuSave(true); };
    return;
  }
  /* Konstruktor (A versiya): qadamlar tasmasi — 1 Materiallar (qaytish) · 2 Tahrirlash (shu yer) · 3 Nashr */
  const W = kuWiz();
  if (W) {
    el.innerHTML = `<div class="kx-bar"><ol class="kx-steps sm"><li class="done"><span class="n">✓</span><button type="button" class="pk-link" id="kxM"><b>Materiallar</b></button></li>
        <li class="on" aria-current="step"><span class="n">2</span><b>Tahrirlash</b></li><li><span class="n">3</span><b>Tayyor</b></li></ol>
      <span class="kx-bar-t">${esc(co.dars.code || W.code)} · blokni bosib tahrirlang, «+» — blok qo'shish, o'zgarishlar o'zi saqlanadi</span>
      ${kuCanDone(co.caps) ? `<button type="button" class="btn sm primary ku-done" id="kxPub" title="Tekshirish, eksport va ko'rib chiqishga yuborish">Tayyor</button>` : ""}</div>` + (co.status_note && co.status === "qoralama" ? `<div class="ku-warn">${ico("info", 15)}<span><b>Izoh:</b> ${esc(co.status_note)}</span></div>` : "");
    el.querySelector("#kxM").onclick = async () => { await kuFlush(); kxBack(W.cid, W.key); };
    el.querySelector("#kxPub")?.addEventListener("click", () => kuPublish());
    return;
  }
  const ln = co.dars && co.dars.linked ? `<div class="ku-link">${ico("package", 15)}<span><b>Dars tayyorlash:</b> ${esc(co.dars.subject || "")} · <b>${esc(co.dars.code)}</b> ·
      eksport uchun ustun manba — <b>${co.dars.authority === "kurs" ? "shu muharrir" : "shablon bo'yicha yig'ilgan paket"}</b></span>
      <button type="button" class="btn sm ghost" id="kuToDs">Fanga qaytish</button></div>` : "";
  const ro = !co.caps.write ? `<div class="ku-warn info">${ico("eye", 15)}<span>Faqat ko'rish va izoh: blokni tanlab «Izohlar» orqali fikr qoldiring.</span></div>` : "";
  el.innerHTML = ln + ro + (co.status_note && co.status === "qoralama" ? `<div class="ku-warn">${ico("info", 15)}<span><b>Izoh:</b> ${esc(co.status_note)}</span></div>`
    : co.status === "korib_chiqishda" ? `<div class="ku-warn info">${ico("info", 15)}<span>Kurs ko'rib chiqishda (${kuD(co.submitted_at)}). ${co.caps.approve ? "Tekshirib, tasdiqlang yoki izoh bilan qaytaring." : "O'zgartirsangiz, kurs qoralamaga qaytadi va qayta yuborish kerak bo'ladi."}</span></div>`
    : co.status === "tasdiqlangan" ? `<div class="ku-warn ok">${ico("check", 15)}<span>Tasdiqlangan: ${esc(co.approved_name || "")}, ${kuD(co.approved_at)}. O'zgartirish kursni qoralamaga qaytaradi (tasdiqlangan versiya «Versiyalar»da saqlanadi).</span></div>` : "");
  el.querySelector("#kuToDs")?.addEventListener("click", async () => { await kuFlush(); if (typeof dsOpenSubject === "function") dsOpenSubject(co.dars.dl_course_id); });
}
function kuState(s, msg = "") {
  KU.state = s;
  const el = $("#kuSave"); if (!el) return;
  const t = new Date();
  el.className = "ku-save " + s;
  el.textContent = s === "saving" ? "Saqlanmoqda…" : s === "dirty" ? "O'zgarishlar bor" : s === "conflict" ? "Ziddiyat — saqlanmadi" : s === "error" ? `Saqlanmadi${msg ? ": " + msg : ""} — qayta urinilmoqda`
    : `Saqlandi ${String(t.getHours()).padStart(2, "0")}:${String(t.getMinutes()).padStart(2, "0")}`;
}

/* ---------- darslar ro'yxati (chap) ---------- */
function kuRenderSide() {
  const co = KU.course, el = $("#kuSide"); if (!el) return;
  const ls = co.lessons_list;
  el.innerHTML = `<div class="ku-side-h"><b>Darslar</b><span class="muted">${ls.length}</span><button type="button" class="ku-ib only-rise" data-sclose aria-label="Darslar panelini yopish" title="Yopish">${ico("x", 16)}</button></div>
    <ol class="ku-ls" id="kuLs">${ls.map((l, i) => `<li draggable="true" data-lid="${l.id}" class="${l.id === KU.lid ? "on" : ""}">
      <span class="ku-grip" aria-hidden="true">${kuI("grip", 14)}</span>
      <button type="button" class="ku-l" data-go="${l.id}" aria-current="${l.id === KU.lid ? "page" : "false"}" aria-keyshortcuts="Alt+ArrowUp Alt+ArrowDown" aria-describedby="kuLsHint"><span class="no">${l.type === "quiz" ? kuI("quiz", 15) : i + 1}</span>
        <span class="t">${esc(l.id === KU.lid && KU.title ? KU.title : l.title)}</span><small>${l.type === "quiz" ? `Test · ${l.blocks} savol` : `${l.blocks} blok`}</small></button></li>`).join("")}</ol>
    <div class="ku-side-a"><button type="button" class="btn sm ghost" data-add="blocks">${kuI("plus", 14)} Dars</button><button type="button" class="btn sm ghost" data-add="quiz">${kuI("plus", 14)} Test</button></div>
    <p class="ku-note" id="kuLsHint">Tartibni o'zgartirish uchun darsni sudrang, dars sarlavhasi yonidagi ↑ ↓ ni bosing yoki darsni tanlab Alt + ↑ / ↓.</p>`;
  el.querySelectorAll("[data-go]").forEach(b => b.onclick = () => { if (+b.dataset.go !== KU.lid) kuLoadLesson(+b.dataset.go); });
  /* klaviatura: fokusdagi dars — Alt+↑ / Alt+↓ bilan ko'chiriladi; fokus o'sha darsda qoladi, yangi o'rni ekran o'quvchisiga aytiladi */
  el.querySelectorAll("[data-go]").forEach(b => b.onkeydown = e => {
    if (!e.altKey || (e.key !== "ArrowUp" && e.key !== "ArrowDown")) return;
    e.preventDefault();
    const ids = co.lessons_list.map(l => l.id), lid = +b.dataset.go, i = ids.indexOf(lid), j = i + (e.key === "ArrowUp" ? -1 : 1);
    if (j < 0 || j >= ids.length) { kuSay(j < 0 ? "Dars allaqachon birinchi o'rinda" : "Dars allaqachon oxirgi o'rinda"); return; }
    [ids[i], ids[j]] = [ids[j], ids[i]];
    kuOrder(ids, lid);
  });
  el.querySelectorAll("[data-add]").forEach(b => b.onclick = () => kuAddLesson(b.dataset.add));
  el.querySelector("[data-sclose]")?.addEventListener("click", () => { el.classList.remove("open"); $("#kuSideT")?.setAttribute("aria-expanded", "false"); $("#kuSideT")?.focus(); });
  let drag = null;
  el.querySelectorAll("#kuLs li").forEach(li => {
    li.ondragstart = e => { drag = li; li.classList.add("drag"); e.dataTransfer.effectAllowed = "move"; e.dataTransfer.setData("text/plain", li.dataset.lid); };
    li.ondragend = () => { li.classList.remove("drag"); el.querySelectorAll(".over-t,.over-b").forEach(x => x.classList.remove("over-t", "over-b")); };
    li.ondragover = e => { if (!drag || drag === li) return; e.preventDefault(); const r = li.getBoundingClientRect(), top = e.clientY < r.top + r.height / 2; li.classList.toggle("over-t", top); li.classList.toggle("over-b", !top); };
    li.ondragleave = () => li.classList.remove("over-t", "over-b");
    li.ondrop = e => { e.preventDefault(); if (!drag || drag === li) return; const top = li.classList.contains("over-t"); li.classList.remove("over-t", "over-b");
      const ids = co.lessons_list.map(l => l.id), from = +drag.dataset.lid; ids.splice(ids.indexOf(from), 1); ids.splice(ids.indexOf(+li.dataset.lid) + (top ? 0 : 1), 0, from); kuOrder(ids); };
  });
}
/* ekran o'quvchisi uchun qisqa xabar (ko'rinmas aria-live maydon) */
function kuSay(t) { const el = $("#kuLive"); if (!el) return; el.textContent = ""; setTimeout(() => { el.textContent = t; }, 30); }
async function kuOrder(ids, focusLid = null) {
  await kuFlush();
  const r = await kuFetch(`/api/kurs/courses/${KU.cid}/order`, {order: ids, rev: KU.course.rev});
  if (r.status === 409) { toast("Kurs boshqa joyda o'zgargan — yangilandi"); return kuOpen(KU.cid, KU.lid); }
  if (!r.ok) { toast(kuErr(r.data)); return; }
  KU.course = r.data; kuRenderSide(); kuLessonHead();
  const ml = focusLid ?? null, ls = KU.course.lessons_list, k = ml != null ? ls.findIndex(l => l.id === ml) : -1;
  if (k >= 0) { document.querySelector(`#kuLs [data-go="${ml}"]`)?.focus(); kuSay(`Dars «${ls[k].title}» ${k + 1}-o'ringa ko'chirildi (jami ${ls.length} ta)`); }
}
async function kuAddLesson(type) {
  await kuFlush();
  const r = await kuApi(`/api/kurs/courses/${KU.cid}/lessons`, {type, after: KU.lid || null});
  if (!r) return;
  KU.course = r.course; kuRenderSide(); kuLoadLesson(r.id, true);
}
async function kuLoadLesson(lid, skipFlush = false) {
  if (!skipFlush) await kuFlush();
  const l = await kuApi(`/api/kurs/lessons/${lid}`).catch(e => { toast(e.msg || "Darsni ochib bo'lmadi"); return null; });
  if (!l) return;
  Object.assign(KU, {lid, lesson: l, blocks: l.blocks.map(b => ({id: b.id, type: b.type, data: b.data, issues: b.issues})), title: l.title, quiz: l.quiz, rev: l.rev,
    sel: -1, conflict: null, dirty: false});
  KU.course.status = l.status; kuStatusChip();
  kuRenderSide(); kuRenderCanvas(); kuRenderPanel(); kuNote(); kuState("saved");
  if (KU.pv) kuPvLoad();
  if (KU.focus) { const i = KU.blocks.findIndex(b => b.id === KU.focus); KU.focus = null; if (i >= 0) kuSelect(i); }
}

/* ---------- dars (markaz) ---------- */
function kuLessonHead() {
  const el = $("#kuLh"); if (!el) return;
  const ls = KU.course.lessons_list, i = ls.findIndex(l => l.id === KU.lid);
  el.querySelector("[data-lmv='-1']").disabled = i <= 0; el.querySelector("[data-lmv='1']").disabled = i < 0 || i >= ls.length - 1;
}
function kuRenderCanvas() {
  const el = $("#kuCanvas"); if (!el) return;
  const quiz = KU.lesson.type === "quiz", rise = kuRise(), co = KU.course;
  /* Rise: dars boshida muqova (kurs muqovasi + dars nomi joyida tahrirlanadi), pastda — tez qo'shish paneli */
  const cover = rise && co.cover_asset ? `style="--cov:url('${kuAsset(co.cover_asset)}')"` : "";
  el.innerHTML = `<div class="ku-lh ${rise ? "ku-hero" + (co.cover_asset ? " img" : "") : ""}" id="kuLh" ${cover}>${rise ? `<span class="ku-hero-k">${esc(quiz ? "Test" : co.title || "")}</span>` : ""}${rise ? `<textarea class="ku-ltitle" id="kuLt" rows="1" data-grow data-one maxlength="200" aria-label="Dars nomi" placeholder="Dars nomi">${esc(KU.title)}</textarea>` : `<input class="ku-ltitle" id="kuLt" value="${esc(KU.title)}" maxlength="200" aria-label="Dars nomi" placeholder="Dars nomi">`}
      <div class="ku-lh-a"><span class="ku-chip">${quiz ? "Test" : "Dars"}</span>
        <button type="button" class="ku-ib" data-lmv="-1" title="Darsni yuqoriga" aria-label="Darsni yuqoriga">${kuI("up")}</button>
        <button type="button" class="ku-ib" data-lmv="1" title="Darsni pastga" aria-label="Darsni pastga">${kuI("down")}</button>
        <button type="button" class="ku-ib" data-ldup title="Darsdan nusxa" aria-label="Darsdan nusxa">${kuI("copy")}</button>
        <button type="button" class="ku-ib danger" data-ldel title="Darsni o'chirish" aria-label="Darsni o'chirish">${kuI("trash")}</button></div></div>
    ${quiz ? kuQuizHead() : ""}
    <div class="ku-blocks" id="kuBlocks">${kuBlocksHtml()}</div>
    ${rise && !quiz && co.caps.write ? kuQuickBar() : ""}
    ${quiz ? `<div class="ku-acts center"><button type="button" class="btn ghost" data-act="ins" data-at="${KU.blocks.length}">${kuI("plus", 15)} Savol qo'shish</button>
      <button type="button" class="btn ghost" data-act="tb">${ico("checkc", 15)} Test bankdan</button>${KU.meta.caps.ai && co.caps.write ? `<button type="button" class="btn ghost" data-act="qai" data-at="${KU.blocks.length}">${ico("spark", 15)} AI bilan savol</button>` : ""}</div>` : ""}`;
  kuLessonHead(); kuGrow(el);
  $("#kuLt").oninput = e => { kuOne(e.target); KU.title = e.target.value; const s = document.querySelector(`#kuLs li[data-lid="${KU.lid}"] .t`); if (s) s.textContent = KU.title; kuDirty(); };
  el.querySelectorAll("[data-lmv]").forEach(b => b.onclick = () => { const ids = KU.course.lessons_list.map(l => l.id), i = ids.indexOf(KU.lid), j = i + +b.dataset.lmv;
    if (j < 0 || j >= ids.length) return; [ids[i], ids[j]] = [ids[j], ids[i]]; kuOrder(ids, KU.lid).then(() => b.isConnected && b.focus()); });
  el.querySelector("[data-ldup]").onclick = async () => { await kuFlush(); const r = await kuApi(`/api/kurs/lessons/${KU.lid}/duplicate`, {}); if (r) { KU.course = r.course; kuLoadLesson(r.id, true); toast("Darsdan nusxa olindi"); } };
  el.querySelector("[data-ldel]").onclick = async e => {
    if (!arm(e.currentTarget, "O'chirilsinmi?")) return;
    await kuFlush(); const r = await kuApi(`/api/kurs/lessons/${KU.lid}/delete`, {});
    if (r) { KU.course = r; toast("Dars o'chirildi — «Versiyalar»dan tiklash mumkin"); const nx = r.lessons_list[0]?.id; KU.lid = 0; kuRenderSide(); if (nx) kuLoadLesson(nx, true); else kuOpen(KU.cid); }
  };
}
function kuBlocksHtml() {
  const quiz = KU.lesson.type === "quiz";
  if (!KU.blocks.length) return quiz ? `<div class="ku-empty"><b>Savollar yo'q</b><span>«Savol qo'shish» yoki «Test bankdan» bilan qo'shing.</span></div>`
    : `<div class="ku-empty"><b>Dars bo'sh</b><span>Birinchi blokni qo'shing.</span><button type="button" class="btn primary" data-act="ins" data-at="0">${kuI("plus", 15)} Blok qo'shish</button></div>`;
  return (quiz ? "" : kuIns(0)) + KU.blocks.map((b, i) => kuCard(b, i) + (quiz ? "" : kuIns(i + 1))).join("");
}
/* Rise'dagi pastki tez qo'shish paneli: blok kutubxonasi + eng ko'p ishlatiladigan bloklar (tanlangan blokdan keyin, aks holda oxiriga) */
const KU_QUICK = [["paragraph", "text", "Matn"], ["list", "list2", "Ro'yxat"], ["image", "image", "Rasm"], ["gallery", "gallery", "Galereya"], ["video", "video2", "Video"],
  ["knowledge", "quiz", "Test savoli"], ["matching", "match", "Moslashtirish"], ["flashcards", "cards", "Kartochkalar"], ["continue", "cont", "Davom etish"]];
function kuQuickBar() {
  return `<div class="ku-qbar" role="toolbar" aria-label="Blok qo'shish"><button type="button" class="ku-qb lib" data-act="qlib">${kuI("blocks", 18)}<span>Blok<br>kutubxonasi</span></button>
    ${KU_QUICK.filter(([t]) => KU.meta.blocks[t]).map(([t, ic, l]) => `<button type="button" class="ku-qb" data-act="qins" data-t="${t}">${kuI(ic, 18)}<span>${esc(l)}</span></button>`
      + (t === "knowledge" && KU.meta.caps.ai ? `<button type="button" class="ku-qb ai" data-act="qai">${ico("spark", 18)}<span>AI bilan<br>savol</span></button>` : "")).join("")}</div>`;
}
const kuIns = at => `<div class="ku-ins"><button type="button" data-act="ins" data-at="${at}" aria-label="Shu joyga blok qo'shish" title="Blok qo'shish">${kuI("plus", 16)}</button></div>`;
function kuIssues(iss) {
  if (!iss || !iss.length) return "";
  const bad = iss.some(x => x.level === "xato");
  return `<span class="ku-iss ${bad ? "bad" : "warn"}" title="${esc(iss.map(x => x.msg).join("\n"))}" tabindex="0" aria-label="${esc(iss.map(x => x.msg).join(". "))}">${ico("alert", 13)} ${iss.length}</span>`;
}
function kuCard(b, i) {
  const M = KU.meta.blocks, n = KU.blocks.length;
  if (kuDupHero(b, i)) return `<section class="ku-blk ku-dup ${i === KU.sel ? "sel" : ""}" data-bi="${i}" data-t="${esc(b.type)}" id="kb-${b.id}" aria-label="Sarlavha (dars nomi bilan bir xil)">
    <div class="ku-dup-n">${ico("eye", 14)}<span>Birinchi sarlavha («${esc(String(b.data.text || "").slice(0, 80))}») dars nomi bilan bir xil — takrorlanmasin deb yig'ildi.</span>
    <button type="button" class="btn sm ghost" data-act="dup-show">Ko'rsatish</button></div></section>`;
  return `<section class="ku-blk ${i === KU.sel ? "sel" : ""}" data-bi="${i}" data-t="${esc(b.type)}" id="kb-${b.id}" aria-label="${esc(M[b.type]?.label || b.type)}">
    <div class="ku-blk-h"><span class="ku-grip" draggable="true" tabindex="0" role="button" title="Sudrab yoki Alt + ↑ / ↓ bilan ko'chirish" aria-label="Blokni ko'chirish (${i + 1}/${n}): Alt + ↑ yoki Alt + ↓" aria-keyshortcuts="Alt+ArrowUp Alt+ArrowDown">${kuI("grip", 14)}</span><b>${KU.lesson.type === "quiz" ? `${i + 1}-savol` : esc(M[b.type]?.label || b.type)}</b>
      <span class="ku-iss-w">${kuIssues(b.issues)}</span>${kuCmBadge(b)}
      <span class="ku-tools"><button type="button" class="ku-ib" data-act="up" ${i === 0 ? "disabled" : ""} aria-label="Yuqoriga" title="Yuqoriga">${kuI("up", 15)}</button>
        <button type="button" class="ku-ib" data-act="down" ${i === n - 1 ? "disabled" : ""} aria-label="Pastga" title="Pastga">${kuI("down", 15)}</button>
        ${kuAiOk(b) ? `<button type="button" class="ku-ib ku-ai-b" data-act="ai" aria-label="AI bilan tahrirlash" title="AI bilan tahrirlash">${ico("spark", 15)}</button>` : ""}
        <button type="button" class="ku-ib" data-act="gear" aria-label="Sozlamalar" title="Sozlamalar">${kuI("gear", 15)}</button>
        <button type="button" class="ku-ib" data-act="dup" aria-label="Nusxa" title="Nusxa">${kuI("copy", 15)}</button>
        <button type="button" class="ku-ib danger" data-act="del" aria-label="O'chirish" title="O'chirish">${kuI("trash", 15)}</button></span></div>
    <div class="ku-blk-b">${kuAiInline(b)}${kuAiNote(b)}${kuEd(b, i)}</div></section>`;
}
function kuReblock(i) {
  const b = KU.blocks[i], el = document.querySelector(`#kuBlocks [data-bi="${i}"]`);
  if (!b || !el) return kuRenderBlocks();
  el.outerHTML = kuCard(b, i);
  kuGrow(document.querySelector(`#kuBlocks [data-bi="${i}"]`));
}
function kuRenderBlocks() { const el = $("#kuBlocks"); if (el) { el.innerHTML = kuBlocksHtml(); kuGrow(el); } }
/* ko'p qatorli sarlavhalar: <textarea data-grow> balandligi matnga qarab o'sadi; data-one — bir qatorli matn (Enter va yangi qator olib tashlanadi) */
function kuGrow(root) { (root || document).querySelectorAll?.("textarea[data-grow]").forEach(t => { t.style.height = "auto"; t.style.height = (t.scrollHeight + 2) + "px"; }); if (root?.matches?.("textarea[data-grow]")) { root.style.height = "auto"; root.style.height = (root.scrollHeight + 2) + "px"; } }
function kuOne(t) { if (t.matches?.("[data-one]") && /[\r\n]/.test(t.value)) { const p = t.selectionStart; t.value = t.value.replace(/\s*[\r\n]+\s*/g, " "); try { t.setSelectionRange(p, p); } catch (e) { /* jim */ } } }
/* Rise: birinchi sarlavha dars nomini (muqovadagi) takrorlasa — muharrirda yig'iladi (ma'lumot o'chirilmaydi, o'quvchi pleyeriga ta'sir qilmaydi) */
function kuDupHero(b, i) {
  if (!kuRise() || i !== 0 || b.type !== "heading" || KU.lesson?.type === "quiz" || KU.dupShow?.[b.id]) return false;
  const n = x => String(x || "").replace(/<[^>]*>/g, "").toLowerCase().replace(/[\s:.\-–—«»"'’ʻ`]+/g, " ").trim();
  const h = n(b.data.text), t = n(KU.title);
  return h.length >= 3 && t.length >= 3 && (h.includes(t) || t.includes(h));
}

/* ---------- blok muharrirlari (joyida tahrirlash) ---------- */
const kuIn = (k, v, ph = "", cls = "", max = 300) => `<input class="ku-in ${cls}" data-k="${k}" value="${esc(v ?? "")}" placeholder="${esc(ph)}" maxlength="${max}" aria-label="${esc(ph)}">`;
const kuHd = (k, v, ph, cls) => `<textarea class="ku-in ${cls} grow" data-k="${k}" data-grow data-one rows="1" placeholder="${esc(ph)}" maxlength="300" aria-label="${esc(ph)}">${esc(v ?? "")}</textarea>`;
const kuTa = (k, v, ph = "", rows = 2, cls = "", max = 2000) => `<textarea class="ku-in ${cls}" data-k="${k}" rows="${rows}" placeholder="${esc(ph)}" maxlength="${max}" aria-label="${esc(ph)}">${esc(v ?? "")}</textarea>`;
const kuRich = (k, h, ph = "Matn yozing…", cls = "") => `<div class="ku-rich ${cls}" contenteditable="true" role="textbox" aria-multiline="true" data-k="${k}" data-rich data-ph="${esc(ph)}" aria-label="${esc(ph)}">${h || ""}</div>`;
const kuAsset = id => id ? `/api/kurs/assets/${id}` : "";
const kuBtn = (act, label, extra = "", cls = "ghost") => `<button type="button" class="btn sm ${cls}" data-act="${act}" ${extra}>${label}</button>`;
const kuX = (act, i, lbl = "O'chirish") => `<button type="button" class="ku-ib sm danger" data-act="${act}" data-i="${i}" aria-label="${esc(lbl)}" title="${esc(lbl)}">${ico("x", 14)}</button>`;
function kuImg(k, id, alt = "") {
  return id ? `<div class="ku-imgw"><img src="${kuAsset(id)}" alt="${esc(alt)}"><div class="ku-img-a">${kuBtn("img", `${kuI("image", 14)} Almashtirish`, `data-k="${k}"`)}${kuBtn("img-x", "Olib tashlash", `data-k="${k}"`)}</div></div>`
    : `<div class="ku-drop" data-act="img" data-k="${k}" role="button" tabindex="0">${kuI("image", 26)}<b>Rasm qo'shish</b><span>Yuklang yoki kurs kutubxonasidan tanlang (.png, .jpg)</span></div>`;
}
const kuAlt = (k, v) => `<label class="ku-alt ${v ? "" : "warn"}"><span>${v ? "Muqobil matn (alt)" : `${ico("alert", 13)} Muqobil matn yozilmagan`}</span>${kuIn(k, v, "Rasmda nima tasvirlangan? (ko'zi ojiz talabalar uchun)", "", 300)}</label>`;
function kuItems(d, opts) {   /* akkordeon, yorliqlar, jarayon, vaqt chizig'i: [{title, html}] (+ sana) */
  return `<div class="ku-items">${d.items.map((x, i) => `<div class="ku-item"><div class="ku-item-h"><span class="ku-num">${i + 1}</span>
      ${opts.date ? kuIn(`items.${i}.date`, x.date, "Sana / davr", "date", 60) : ""}${kuIn(`items.${i}.title`, x.title, opts.ph || "Sarlavha", "strong", 200)}
      <button type="button" class="ku-ib sm" data-act="it-up" data-i="${i}" ${i ? "" : "disabled"} aria-label="Yuqoriga">${kuI("up", 13)}</button>
      <button type="button" class="ku-ib sm" data-act="it-down" data-i="${i}" ${i < d.items.length - 1 ? "" : "disabled"} aria-label="Pastga">${kuI("down", 13)}</button>${kuX("it-del", i)}</div>
      ${kuRich(`items.${i}.html`, x.html, "Matn…")}</div>`).join("")}</div>${kuBtn("it-add", `${kuI("plus", 14)} ${opts.add || "Band qo'shish"}`)}`;
}
function kuQEd(d) {   /* bilimni tekshirish / test savoli */
  const K = KU.meta.q_kinds;
  const kinds = `<div class="ku-seg sm" role="group" aria-label="Savol turi">${Object.entries(K).map(([k, t]) => `<button type="button" class="${d.kind === k ? "on" : ""}" data-act="qkind" data-v="${k}">${esc(t)}</button>`).join("")}</div>`;
  let body;
  if (d.kind === "fill") {
    body = `<div class="ku-sub">To'g'ri javob(lar) — har biri alohida (katta-kichik harf va apostrof farqi hisobga olinmaydi)</div>
      ${d.accept.map((a, i) => `<div class="ku-row">${kuIn(`accept.${i}`, a, "To'g'ri javob", "", 200)}${kuX("acc-del", i)}</div>`).join("")}${kuBtn("acc-add", `${kuI("plus", 14)} Javob varianti`)}`;
  } else {
    const multi = d.kind === "multiple", tf = d.kind === "truefalse";
    body = `<div class="ku-sub">${multi ? "Bir nechta to'g'ri javobni belgilang" : "To'g'ri javobni belgilang"} · har variantga izoh yozish mumkin</div>
      <div class="ku-answers">${d.answers.map((a, i) => `<div class="ku-ans ${a.correct ? "ok" : ""}"><label class="ku-corr" title="To'g'ri javob"><input type="${multi ? "checkbox" : "radio"}" name="c-${KU.lid}-${esc(d._bid || "")}" data-act="corr" data-i="${i}" ${a.correct ? "checked" : ""} aria-label="${i + 1}-variant to'g'ri"></label>
        <div class="ku-ans-b">${tf ? `<b class="ku-tf">${esc(a.text)}</b>` : kuIn(`answers.${i}.text`, a.text, `${String.fromCharCode(65 + i)} variant`, "", 500)}
        ${kuIn(`answers.${i}.feedback`, a.feedback, "Izoh (shu variant tanlanganda ko'rinadi)", "fb", 1000)}</div>${tf ? "" : kuX("ans-del", i)}</div>`).join("")}</div>
      ${tf ? "" : kuBtn("ans-add", `${kuI("plus", 14)} Variant qo'shish`)}`;
  }
  return `${kinds}${kuTa("question", d.question, "Savol matni", 2, "q", 1000)}${body}
    <details class="ku-det"><summary>Umumiy izoh (to'g'ri / noto'g'ri javobda)</summary>${kuIn("feedback_correct", d.feedback_correct, "To'g'ri javobda", "", 1000)}${kuIn("feedback_wrong", d.feedback_wrong, "Noto'g'ri javobda", "", 1000)}</details>`;
}
function kuYt(u) {
  u = String(u || "").trim();
  const m = u.match(/(?:youtu\.be\/|youtube(?:-nocookie)?\.com\/(?:watch\?(?:.*&)?v=|embed\/|shorts\/|live\/))([A-Za-z0-9_-]{11})/) || u.match(/^([A-Za-z0-9_-]{11})$/);
  const t = u.match(/[?&](?:t|start)=(\d+)/);
  return m ? {id: m[1], start: t ? +t[1] : 0} : null;
}
function kuEd(b, bi) {
  const d = b.data, t = b.type;
  d._bid = b.id;
  switch (t) {
    case "heading": return kuHd("text", d.text, "Sarlavha", `h${d.level}`);
    case "paragraph": return kuRich("html", d.html);
    case "heading_paragraph": return kuHd("heading", d.heading, "Sarlavha", "h3") + kuRich("html", d.html);
    case "quote": return `<div class="ku-quote ${d.style}">${kuTa("text", d.text, d.style === "impact" ? "Asosiy fikr" : "Iqtibos", 2, "", 1000)}${d.style === "quote" ? kuIn("cite", d.cite, "Muallif (ixtiyoriy)", "cite", 200) : ""}</div>`;
    case "list": return `<div class="ku-list ${d.style}">${d.items.map((h, i) => `<div class="ku-li"><span class="ku-mark">${d.style === "numbered" ? i + 1 + "." : d.style === "checkbox" ? "☐" : "•"}</span>${kuRich(`items.${i}`, h, "Band", "line")}${kuX("li-del", i)}</div>`).join("")}</div>${kuBtn("li-add", `${kuI("plus", 14)} Band qo'shish`)}`;
    case "table": {
      const w = d.rows[0]?.length || 0;
      return `<div class="ku-tbl-w"><table class="ku-tbl ${d.header ? "hdr" : ""}"><tbody>${d.rows.map((r, ri) => `<tr>${r.map((c, ci) => `<td>${kuIn(`rows.${ri}.${ci}`, c, ri === 0 && d.header ? "Ustun" : "", "", 500)}</td>`).join("")}<td class="x">${kuX("row-del", ri, "Qatorni o'chirish")}</td></tr>`).join("")}
        <tr class="x">${Array.from({length: w}, (_, ci) => `<td>${kuX("col-del", ci, "Ustunni o'chirish")}</td>`).join("")}<td></td></tr></tbody></table></div>
        <div class="ku-acts">${kuBtn("row-add", `${kuI("plus", 14)} Qator`)}${w < 8 ? kuBtn("col-add", `${kuI("plus", 14)} Ustun`) : ""}</div>${kuIn("caption", d.caption, "Jadval izohi (ixtiyoriy)", "cap", 300)}`;
    }
    case "image": return `<div class="ku-img ${d.layout}">${kuImg("asset", d.asset, d.alt)}</div>${d.asset ? kuAlt("alt", d.alt) : ""}${kuIn("caption", d.caption, "Rasm osti yozuvi (ixtiyoriy)", "cap", 500)}`;
    case "image_text": return `<div class="ku-it ${d.side}"><div>${kuImg("asset", d.asset, d.alt)}${d.asset ? kuAlt("alt", d.alt) : ""}</div><div>${kuRich("html", d.html)}</div></div>`;
    case "gallery": return `<div class="ku-gal">${d.items.map((x, i) => `<div class="ku-gi ${x.alt ? "" : "noalt"}" tabindex="0" aria-label="${i + 1}-rasm">${x.asset ? `<img src="${kuAsset(x.asset)}" alt="${esc(x.alt)}">` : `<div class="ku-drop sm">${kuI("image", 20)}</div>`}
        ${kuIn(`items.${i}.alt`, x.alt, "Muqobil matn (alt)", x.alt ? "" : "warn", 300)}${kuIn(`items.${i}.caption`, x.caption, "Izoh", "", 300)}<div class="ku-acts tight">
        <button type="button" class="ku-ib sm" data-act="it-up" data-i="${i}" ${i ? "" : "disabled"} aria-label="Chapga">${kuI("up", 13)}</button>${kuX("it-del", i)}</div></div>`).join("")}</div>
        <div class="ku-acts">${kuBtn("gal-up", `${kuI("upload", 14)} Rasmlar yuklash`)}${kuBtn("gal-lib", `${kuI("image", 14)} Kutubxonadan`)}</div>`;
    case "video": {
      const src = `<div class="ku-seg sm" role="group" aria-label="Video manbai"><button type="button" class="${d.source === "file" ? "on" : ""}" data-act="vsrc" data-v="file">Video fayl</button><button type="button" class="${d.source === "youtube" ? "on" : ""}" data-act="vsrc" data-v="youtube">YouTube</button></div>`;
      const body = d.source === "youtube"
        ? `${kuIn("youtube", d.youtube ?? (d.yt_id ? `https://youtu.be/${d.yt_id}${d.yt_start ? "?t=" + d.yt_start : ""}` : ""), "YouTube havolasi (https://youtu.be/…)", "", 500)}
           <p class="ku-note ${d.yt_id ? "ok" : ""}">${d.yt_id ? `Video ID: <code>${esc(d.yt_id)}</code>${d.yt_start ? ` · ${d.yt_start}-soniyadan` : ""} — talabaga youtube-nocookie orqali ko'rsatiladi` : "Havolani kiriting — watch, youtu.be, shorts, embed ko'rinishlari qabul qilinadi"}</p>`
        : d.asset ? `<video class="ku-vid" src="${kuAsset(d.asset)}" ${d.poster ? `poster="${kuAsset(d.poster)}"` : ""} controls preload="metadata"></video>
           <div class="ku-acts">${kuBtn("vid-up", `${kuI("upload", 14)} Videoni almashtirish`)}${kuBtn("img", d.poster ? "Posterni almashtirish" : "Poster rasmi", `data-k="poster"`)}${d.poster ? kuBtn("img-x", "Posterni olib tashlash", `data-k="poster"`) : ""}</div>
           <div class="ku-sub">Subtitrlar (.vtt / .srt)</div>${d.captions.map((c, i) => `<div class="ku-row"><span class="ku-chip">${esc(c.lang)}</span>${kuIn(`captions.${i}.label`, c.label, "Nomi", "", 40)}${kuBtn("cap-edit", "Tahrirlash", `data-i="${i}" aria-label="${esc(c.label || c.lang)} subtitrini tahrirlash"`)}${kuX("cap-del", i)}</div>`).join("") || `<p class="ku-note">Subtitr yo'q — eshitish qobiliyati cheklangan talabalar uchun qo'shing.</p>`}
           <div class="ku-acts"><select class="ku-in sm" id="kuCapL-${esc(b.id)}" aria-label="Subtitr tili">${Object.entries(KU.meta.sub_langs).map(([k, t]) => `<option value="${k}">${esc(t)}</option>`).join("")}</select>${kuBtn("cap-up", `${kuI("upload", 14)} Subtitr yuklash`)}${KU.meta.caps.approve ? kuBtn("cap-auto", "Subtitr yaratish (Whisper)") : ""}</div>
           <p class="ku-note ku-capjob" data-cap-asset="${d.asset}" aria-live="polite">${esc(kuCapJobText(d.asset))}</p>`
        : `<div class="ku-drop" data-act="vid-up" role="button" tabindex="0">${ico("video", 26)}<b>Video yuklash</b><span>.mp4 yoki .webm, ${KU.meta.limits.video_mb} MB gacha</span></div>`;
      return `${src}${body}${kuIn("caption", d.caption, "Video tavsifi (ixtiyoriy)", "cap", 500)}`;
    }
    case "audio": return (d.asset ? `<audio class="ku-aud" src="${kuAsset(d.asset)}" controls preload="metadata"></audio><div class="ku-acts">${kuBtn("aud-up", "Audioni almashtirish")}</div>`
        : `<div class="ku-drop" data-act="aud-up" role="button" tabindex="0">${kuI("upload", 24)}<b>Audio yuklash</b><span>.mp3, .m4a, .ogg, .wav</span></div>`) +
      kuIn("title", d.title, "Sarlavha", "", 200) + kuTa("transcript", d.transcript, "Matni (transkript) — eshitish qobiliyati cheklangan talabalar uchun", 3, "", 20000);
    case "attachment": {
      const a = KU.assets?.[d.asset];
      return (d.asset ? `<div class="ku-file">${ico("file", 22)}<div><b>${esc(a?.name || "Fayl")}</b><small class="muted">${a ? kuSize(a.size) : ""}</small></div>${kuBtn("file-up", "Almashtirish")}</div>`
        : `<div class="ku-drop" data-act="file-up" role="button" tabindex="0">${ico("file", 24)}<b>Fayl yuklash</b><span>PDF, Word, PowerPoint, Excel, ${KU.meta.limits.file_mb} MB gacha</span></div>`) +
        kuIn("title", d.title, "Fayl nomi (talabaga ko'rinadi)", "", 200) + kuTa("desc", d.desc, "Qisqa tavsif", 2, "", 500);
    }
    case "labeled_graphic": return d.asset ? `<p class="ku-note">Rasm ustiga bosing — yangi belgi qo'shiladi. Belgini ko'chirish: ro'yxatdagi «Joyini o'zgartirish», so'ng rasmga bosing.</p>
        <div class="ku-lg" data-act="lg-click"><img src="${kuAsset(d.asset)}" alt="${esc(d.alt)}">${d.markers.map((m, i) => `<span class="ku-mk ${KU.lgMove === i ? "mv" : ""}" style="left:${m.x}%;top:${m.y}%">${i + 1}</span>`).join("")}</div>
        ${kuAlt("alt", d.alt)}<div class="ku-acts">${kuBtn("img", "Rasmni almashtirish", `data-k="asset"`)}</div>
        <div class="ku-items">${d.markers.map((m, i) => `<div class="ku-item"><div class="ku-item-h"><span class="ku-num">${i + 1}</span>${kuIn(`markers.${i}.title`, m.title, "Belgi sarlavhasi", "strong", 200)}
          ${kuBtn("lg-move", KU.lgMove === i ? "Rasmga bosing…" : "Joyini o'zgartirish", `data-i="${i}"`)}${kuX("lg-del", i)}</div>${kuRich(`markers.${i}.html`, m.html, "Tavsif…")}</div>`).join("")}</div>`
      : kuImg("asset", null);
    case "accordion": return kuItems(d, {add: "Bo'lim qo'shish"});
    case "tabs": return kuItems(d, {add: "Yorliq qo'shish", ph: "Yorliq nomi"});
    case "process": return kuItems(d, {add: "Qadam qo'shish", ph: "Qadam nomi"});
    case "timeline": return kuItems(d, {add: "Voqea qo'shish", date: true});
    case "flashcards": return `<div class="ku-fc">${d.cards.map((c, i) => `<div class="ku-fcc"><span class="ku-num">${i + 1}</span>${kuTa(`cards.${i}.front`, c.front, "Old tomoni", 2, "", 600)}${kuTa(`cards.${i}.back`, c.back, "Orqa tomoni", 3, "", 1200)}${kuX("fc-del", i)}</div>`).join("")}</div>${kuBtn("fc-add", `${kuI("plus", 14)} Kartochka`)}`;
    case "sorting": return `${kuIn("title", d.title, "Topshiriq matni", "strong", 300)}<div class="ku-sub">Toifalar (2–6)</div>
        <div class="ku-cats">${d.categories.map((c, i) => `<div class="ku-row">${kuIn(`categories.${i}`, c, `${i + 1}-toifa`, "", 120)}${d.categories.length > 2 ? kuX("cat-del", i) : ""}</div>`).join("")}</div>
        ${d.categories.length < 6 ? kuBtn("cat-add", `${kuI("plus", 14)} Toifa`) : ""}<div class="ku-sub">Elementlar va to'g'ri toifasi</div>
        ${d.items.map((x, i) => `<div class="ku-row">${kuIn(`items.${i}.text`, x.text, "Element", "", 200)}<select class="ku-in sm" data-k="items.${i}.cat" data-num aria-label="Toifa">${d.categories.map((c, ci) => `<option value="${ci}" ${x.cat === ci ? "selected" : ""}>${esc(c || ci + 1 + "-toifa")}</option>`).join("")}</select>${kuX("srt-del", i)}</div>`).join("")}
        ${kuBtn("srt-add", `${kuI("plus", 14)} Element`)}`;
    case "matching": return `${kuIn("title", d.title, "Topshiriq matni", "strong", 300)}${d.pairs.map((p, i) => `<div class="ku-row pair">${kuIn(`pairs.${i}.left`, p.left, "Chap", "", 200)}<span aria-hidden="true">↔</span>${kuIn(`pairs.${i}.right`, p.right, "O'ng (mos)", "", 200)}${kuX("pr-del", i)}</div>`).join("")}
        ${d.pairs.length < 12 ? kuBtn("pr-add", `${kuI("plus", 14)} Juft`) : ""}`;
    case "knowledge": case "question": return kuQEd(d);
    case "divider": return `<div class="ku-divp ${d.style}" role="separator"></div>`;
    case "continue": if (kuRise()) return `<div class="ku-cont"><span class="ku-cont-btn" style="--acc:${esc(KU.course.accent)}">${kuIn("label", d.label, "Tugma yozuvi (masalan: Davom etish)", "", 60)}</span></div>`;
      return `<div class="ku-cont"><span class="ku-cont-btn" style="--acc:${esc(KU.course.accent)}">${kuIn("label", d.label, "Davom etish", "", 60)}</span>
        <label class="ku-f inline"><span>Talab</span><select class="ku-in sm" data-k="require"><option value="none" ${d.require === "none" ? "selected" : ""}>Faqat bosish</option><option value="interactions" ${d.require === "interactions" ? "selected" : ""}>Yuqoridagi mashqlar bajarilsin</option></select></label></div>
        <p class="ku-note">Talaba tugmani bosmaguncha darsning qolgan qismi ko'rinmaydi.</p>`;
    case "button": return `<div class="ku-btnb">${kuTa("text", d.text, "Tugma oldidagi matn (ixtiyoriy)", 2, "", 500)}<div class="ku-row">${kuIn("label", d.label, "Tugma yozuvi", "", 80)}${kuIn("url", d.url, "https://…", "", 1000)}</div></div>`;
  }
  return `<p class="ku-note">Bu blok turi muharrirda ko'rsatilmaydi.</p>`;
}

/* ---------- ma'lumot bog'lash: data-k (blok ichidagi yo'l), data-q (test sozlamasi) ---------- */
function kuSet(o, path, v) {
  const p = path.split("."); let x = o;
  for (let i = 0; i < p.length - 1; i++) { const k = /^\d+$/.test(p[i]) ? +p[i] : p[i]; if (x[k] == null) x[k] = /^\d+$/.test(p[i + 1]) ? [] : {}; x = x[k]; }
  x[/^\d+$/.test(p[p.length - 1]) ? +p[p.length - 1] : p[p.length - 1]] = v;
}
function kuVal(el) {
  if (el.dataset.rich !== undefined) return el.innerHTML;
  if (el.type === "checkbox") return el.checked;
  if (el.dataset.num !== undefined || el.type === "number") return +el.value;
  return el.value;
}
function kuBindCanvas() {
  const cv = $("#kuCanvas");
  const onField = e => {
    if (e.target.matches?.("[data-grow]")) { kuOne(e.target); kuGrow(e.target); }
    const el = e.target.closest("[data-k]"), card = e.target.closest("[data-bi]");
    if (el && card && !el.closest("[data-q]")) {
      const bi = +card.dataset.bi, b = KU.blocks[bi]; if (!b) return;
      const k = el.dataset.k, v = kuVal(el);
      kuSet(b.data, k, v);
      if (b.type === "video" && k === "youtube") { const y = kuYt(v); b.data.yt_id = y ? y.id : null; b.data.yt_start = y ? y.start : 0;
        const n = card.querySelector(".ku-note"); if (n) { n.classList.toggle("ok", !!y); n.innerHTML = y ? `Video ID: <code>${esc(y.id)}</code>${y.start ? ` · ${y.start}-soniyadan` : ""}` : "Havolani kiriting — watch, youtu.be, shorts, embed ko'rinishlari qabul qilinadi"; } }
      if (k === "alt" || /\.alt$/.test(k)) {   /* alt ogohlantirishi joyida yangilanadi (blok qayta chizilmaydi — fokus yo'qolmasin) */
        const lab = el.closest(".ku-alt"); el.classList.toggle("warn", !v && !lab);
        if (lab) { lab.classList.toggle("warn", !v); lab.querySelector("span").innerHTML = v ? "Muqobil matn (alt)" : `${ico("alert", 13)} Muqobil matn yozilmagan`; }
      }
      kuDirty();
      return;
    }
    const q = e.target.closest("[data-q]");
    if (q && KU.quiz) { KU.quiz[q.dataset.q] = kuVal(q); kuDirty(); }
  };
  cv.addEventListener("input", onField);
  cv.addEventListener("change", e => { if (e.target.matches("select, input[type=checkbox], [data-q]")) onField(e); });
  cv.addEventListener("focusin", e => { const card = e.target.closest("[data-bi]"); if (card && +card.dataset.bi !== KU.sel) kuSelect(+card.dataset.bi, false); if (e.target.matches("[data-rich]")) kuRtShow(e.target); });
  cv.addEventListener("focusout", e => { if (e.target.matches("[data-rich]")) setTimeout(() => { if (!document.activeElement?.closest?.(".ku-rt")) kuRtHide(); }, 120); });
  cv.addEventListener("paste", e => {   /* rich maydon: tashqi formatlash emas — oddiy matn (server baribir tozalaydi) */
    if (!e.target.closest("[data-rich]")) return;
    e.preventDefault(); document.execCommand("insertText", false, (e.clipboardData || window.clipboardData).getData("text/plain"));
  });
  cv.addEventListener("click", e => {
    const a = e.target.closest("[data-act]");
    const card = e.target.closest("[data-bi]");
    if (card && +card.dataset.bi !== KU.sel && !a) kuSelect(+card.dataset.bi, false);
    if (!a) return;
    kuAct(a, card ? +card.dataset.bi : -1, e);
  });
  cv.addEventListener("keydown", e => {
    if ((e.key === "Enter" || e.key === " ") && e.target.matches(".ku-drop[data-act]")) { e.preventDefault(); e.target.click(); }
    if (e.key === "Enter" && e.target.matches?.("[data-one]")) e.preventDefault();   /* sarlavha bir qatorli (ko'rinishda qatorga o'raladi) */
  });
  if (!window._kuGrowBound) { window._kuGrowBound = true; let rt = 0; window.addEventListener("resize", () => { clearTimeout(rt); rt = setTimeout(() => kuGrow($("#kuCanvas")), 120); }); }
  /* klaviatura bilan ko'chirish: blok (tutqich, asboblar paneli yoki blokning o'zi) fokusda — Alt+↑ / Alt+↓. Matn maydonlarida Alt+strelka
     tizimning o'z vazifasini bajaradi (kursorni ko'chirish), shuning uchun u yerda ushlanmaydi. Yangi o'rin aria-live orqali aytiladi. */
  cv.addEventListener("keydown", e => {
    if (!e.altKey || (e.key !== "ArrowUp" && e.key !== "ArrowDown")) return;
    const card = e.target.closest("[data-bi]");
    if (!card || e.target.closest("input, textarea, select, [contenteditable='true'], [data-rich]")) return;
    e.preventDefault();
    kuMoveBlock(+card.dataset.bi, e.key === "ArrowUp" ? -1 : 1, ".ku-grip");
  });
  /* bloklarni sudrab ko'chirish (sichqoncha); klaviatura — ↑ ↓ tugmalari yoki Alt+↑ / Alt+↓ */
  let drag = -1;
  cv.addEventListener("dragstart", e => { const g = e.target.closest(".ku-grip"), card = g && g.closest("[data-bi]"); if (!card) return; drag = +card.dataset.bi; card.classList.add("drag"); e.dataTransfer.effectAllowed = "move"; e.dataTransfer.setData("text/plain", String(drag)); e.dataTransfer.setDragImage(card, 20, 20); });
  cv.addEventListener("dragend", () => { drag = -1; cv.querySelectorAll(".drag,.over-t,.over-b").forEach(x => x.classList.remove("drag", "over-t", "over-b")); });
  cv.addEventListener("dragover", e => { const card = e.target.closest("[data-bi]"); if (drag < 0 || !card) return; e.preventDefault(); const r = card.getBoundingClientRect(), top = e.clientY < r.top + r.height / 2;
    cv.querySelectorAll(".over-t,.over-b").forEach(x => x.classList.remove("over-t", "over-b")); card.classList.add(top ? "over-t" : "over-b"); });
  const dropAt = (from, card, top) => {
    let to = +card.dataset.bi + (top ? 0 : 1); const [b] = KU.blocks.splice(from, 1); if (to > from) to--; KU.blocks.splice(to, 0, b);
    KU.sel = to; kuRenderBlocks(); kuRenderPanel(); kuDirty(); kuSay(`Blok ${to + 1}-o'ringa ko'chirildi (jami ${KU.blocks.length} ta)`);
  };
  cv.addEventListener("drop", e => { const card = e.target.closest("[data-bi]"); if (drag < 0 || !card) return; e.preventDefault(); const from = drag; drag = -1; dropAt(from, card, card.classList.contains("over-t")); });
  /* sensorli ekran: tutqichni uzoq bosib (~0,35 s) sudrash (pointer hodisalari). Ishonchli yo'l — blok asboblaridagi ↑ ↓ tugmalari */
  let lp = null;
  const lpClear = () => { if (lp) { clearTimeout(lp.t); lp.card.classList.remove("drag"); cv.querySelectorAll(".over-t,.over-b").forEach(x => x.classList.remove("over-t", "over-b")); lp.g.draggable = true; lp = null; } };
  const lpTarget = e => { const el = document.elementFromPoint(e.clientX, e.clientY)?.closest?.("#kuBlocks [data-bi]"); return el && el !== lp.card ? el : null; };
  cv.addEventListener("pointerdown", e => {
    const g = e.pointerType !== "mouse" && e.target.closest(".ku-grip"), card = g && g.closest("[data-bi]"); if (!card) return;
    lpClear(); g.draggable = false;
    lp = {from: +card.dataset.bi, card, g, x: e.clientX, y: e.clientY, on: false, pid: e.pointerId};
    lp.t = setTimeout(() => { if (!lp) return; lp.on = true; card.classList.add("drag"); try { g.setPointerCapture(lp.pid); } catch (x) { /* jim */ } try { navigator.vibrate?.(15); } catch (x) { /* jim */ } kuSay("Sudrash rejimi: barmoqni yuqori yoki pastga siljiting"); }, 350);
  });
  cv.addEventListener("pointermove", e => {
    if (!lp || e.pointerId !== lp.pid) return;
    if (!lp.on) { if (Math.hypot(e.clientX - lp.x, e.clientY - lp.y) > 12) lpClear(); return; }
    e.preventDefault();
    cv.querySelectorAll(".over-t,.over-b").forEach(x => x.classList.remove("over-t", "over-b"));
    const t = lpTarget(e); if (t) { const r = t.getBoundingClientRect(); t.classList.add(e.clientY < r.top + r.height / 2 ? "over-t" : "over-b"); }
    if (e.clientY < 90) window.scrollBy(0, -14); else if (e.clientY > innerHeight - 90) window.scrollBy(0, 14);
  });
  const lpEnd = e => {
    if (!lp || e.pointerId !== lp.pid) return;
    const was = lp, t = was.on && e.type === "pointerup" ? lpTarget(e) : null, top = t && e.clientY < t.getBoundingClientRect().top + t.getBoundingClientRect().height / 2;
    lpClear(); if (t) dropAt(was.from, t, top);
  };
  cv.addEventListener("pointerup", lpEnd); cv.addEventListener("pointercancel", lpEnd);
  cv.addEventListener("contextmenu", e => { if (e.target.closest(".ku-grip")) e.preventDefault(); });
}
function kuSelect(i, scroll = true) {
  const prev = document.querySelector("#kuBlocks .ku-blk.sel"); if (prev) prev.classList.remove("sel");
  KU.sel = i;
  const el = document.querySelector(`#kuBlocks [data-bi="${i}"]`); if (el) { el.classList.add("sel"); if (scroll) el.scrollIntoView({block: "nearest", behavior: "smooth"}); }
  kuRenderPanel();
}
const kuMove = (arr, i, j) => { if (j < 0 || j >= arr.length) return false; const [x] = arr.splice(i, 1); arr.splice(j, 0, x); return true; };
/* blokni bir qadam ko'chirish (↑ ↓ tugmalari va Alt+strelka): fokus ko'chgan blokning shu elementida qoladi, yangi o'rni aytiladi */
function kuMoveBlock(bi, step, focusSel) {
  const j = bi + step, n = KU.blocks.length, what = KU.lesson.type === "quiz" ? "Savol" : "Blok";
  if (!kuMove(KU.blocks, bi, j)) { kuSay(`${what} allaqachon ${step < 0 ? "birinchi" : "oxirgi"} o'rinda`); return false; }
  KU.sel = j; kuRenderBlocks(); kuRenderPanel(); kuDirty();
  const card = document.querySelector(`#kuBlocks [data-bi="${j}"]`);
  (card?.querySelector(focusSel) || card?.querySelector(".ku-grip"))?.focus();
  kuSay(`${what} ${j + 1}-o'ringa ko'chirildi (jami ${n} ta)`);
  return true;
}
async function kuAct(a, bi, e) {
  const act = a.dataset.act, b = KU.blocks[bi], d = b?.data, i = +a.dataset.i;
  const re = () => { kuReblock(bi); kuDirty(); };
  switch (act) {
    case "ins": return KU.lesson.type === "quiz" ? kuInsert("question", +a.dataset.at) : kuLibrary(+a.dataset.at);
    case "qins": case "qlib": { const at = KU.sel >= 0 ? KU.sel + 1 : KU.blocks.length; return act === "qlib" ? kuLibrary(at) : kuInsert(a.dataset.t, at); }
    case "tb": return kuTestbank();
    case "ai": return kuAiOpen({bi});
    case "qai": return kuAiOpen({at: a.dataset.at != null ? +a.dataset.at : KU.sel >= 0 ? KU.sel + 1 : KU.blocks.length});
    case "ai-x": delete KU.aiMark?.[b.id]; return kuReblock(bi);
    case "ai-undo": { const m = KU.aiMark?.[b.id]; if (m?.prev) { b.data = m.prev; delete KU.aiMark[b.id]; re(); kuSay("AI o'zgartirishi bekor qilindi"); } return; }
    case "dup-show": KU.dupShow = KU.dupShow || {}; KU.dupShow[b.id] = true; kuSelect(bi, false); kuReblock(bi); document.querySelector(`#kuBlocks [data-bi="${bi}"] textarea`)?.focus(); return;
    case "up": case "down": kuMoveBlock(bi, act === "up" ? -1 : 1, `[data-act="${act}"]:not([disabled])`); return;
    case "dup": { const c = kuClone({type: b.type, data: b.data}); KU.blocks.splice(bi + 1, 0, {id: kuUid(), ...c, issues: b.issues}); KU.sel = bi + 1; kuRenderBlocks(); kuRenderPanel(); kuDirty(); toast("Blokdan nusxa olindi"); return; }
    case "del": return kuDelete(bi);
    case "cm": kuSelect(bi, false); return kuCmOpen(b.id);
    case "gear": kuSelect(bi, false); $("#kuPanel").classList.add("open"); $("#kuPanel").querySelector("select, input, button")?.focus(); return;
    case "qkind": {
      const k = a.dataset.v; if (k === d.kind) return;
      if (k === "truefalse") d.answers = [{text: "To'g'ri", correct: true, feedback: ""}, {text: "Noto'g'ri", correct: false, feedback: ""}];
      else if (d.kind === "truefalse" || !d.answers?.length) d.answers = [{text: "", correct: true, feedback: ""}, {text: "", correct: false, feedback: ""}, {text: "", correct: false, feedback: ""}];
      if (k === "single") { let f = false; d.answers.forEach(x => { x.correct = x.correct && !f; if (x.correct) f = true; }); if (!f && d.answers[0]) d.answers[0].correct = true; }
      if (k === "fill" && !d.accept?.length) d.accept = [""];
      d.kind = k; return re();
    }
    case "corr": {
      delete KU.aiMark?.[b.id];
      if (d.kind === "multiple") d.answers[i].correct = a.checked;
      else d.answers.forEach((x, j) => x.correct = j === i);
      return re();
    }
    case "ans-add": if (d.answers.length < 10) d.answers.push({text: "", correct: false, feedback: ""}); return re();
    case "ans-del": d.answers.splice(i, 1); if (d.kind !== "multiple" && d.answers.length && !d.answers.some(x => x.correct)) d.answers[0].correct = true; return re();
    case "acc-add": d.accept.push(""); return re();
    case "acc-del": d.accept.splice(i, 1); return re();
    case "it-add": d.items.push(b.type === "timeline" ? {date: "", title: "", html: ""} : {title: "", html: ""}); return re();
    case "it-del": d.items.splice(i, 1); return re();
    case "it-up": kuMove(d.items, i, i - 1); return re();
    case "it-down": kuMove(d.items, i, i + 1); return re();
    case "li-add": d.items.push(""); return re();
    case "li-del": d.items.splice(i, 1); return re();
    case "row-add": d.rows.push(Array(d.rows[0]?.length || 2).fill("")); return re();
    case "row-del": d.rows.splice(i, 1); return re();
    case "col-add": d.rows.forEach(r => r.push("")); if (!d.rows.length) d.rows.push([""]); return re();
    case "col-del": d.rows.forEach(r => r.splice(i, 1)); return re();
    case "fc-add": d.cards.push({front: "", back: ""}); return re();
    case "fc-del": d.cards.splice(i, 1); return re();
    case "cat-add": d.categories.push(""); return re();
    case "cat-del": d.categories.splice(i, 1); d.items.forEach(x => { if (x.cat >= i) x.cat = Math.max(0, x.cat - 1); }); return re();
    case "srt-add": d.items.push({text: "", cat: 0}); return re();
    case "srt-del": d.items.splice(i, 1); return re();
    case "pr-add": d.pairs.push({left: "", right: ""}); return re();
    case "pr-del": d.pairs.splice(i, 1); return re();
    case "cap-del": d.captions.splice(i, 1); return re();
    case "cap-edit": return kuCueEditor(d.captions[i], aid => { d.captions[i].asset = aid; re(); });
    case "cap-auto": { const lang = $(`#kuCapL-${b.id}`)?.value || "uz"; return kuCapRequest(d.asset, lang); }
    case "vsrc": d.source = a.dataset.v; return re();
    case "img": { const id = await kuPickImage(); if (id) { kuSet(d, a.dataset.k, id); re(); } return; }
    case "img-x": kuSet(d, a.dataset.k, null); return re();
    case "gal-up": { const fs = await kuPickFile("image/png,image/jpeg,image/gif,image/webp", true); for (const f of fs) { const r = await kuUpload("image", f); if (r) { kuAssetAdd(r); d.items.push({asset: r.id, alt: "", caption: ""}); } } return re(); }
    case "gal-lib": { const id = await kuPickImage(); if (id) { d.items.push({asset: id, alt: "", caption: ""}); re(); } return; }
    case "vid-up": { const [f] = await kuPickFile("video/mp4,video/webm"); if (!f) return; const r = await kuUpload("video", f); if (r) { kuAssetAdd(r); d.asset = r.id; d.source = "file"; re(); } return; }
    case "cap-up": { const lang = $(`#kuCapL-${b.id}`)?.value || "uz"; const [f] = await kuPickFile(".vtt,.srt,text/vtt"); if (!f) return;
      const r = await kuUpload("vtt", f, `&lang=${lang}`); if (r) { kuAssetAdd(r); d.captions.push({asset: r.id, lang, label: KU.meta.sub_langs[lang] || lang}); re(); } return; }
    case "aud-up": { const [f] = await kuPickFile("audio/*,.mp3,.m4a,.ogg,.wav"); if (!f) return; const r = await kuUpload("audio", f); if (r) { kuAssetAdd(r); d.asset = r.id; re(); } return; }
    case "file-up": { const [f] = await kuPickFile(".pdf,.docx,.pptx,.xlsx,.png,.jpg"); if (!f) return; const r = await kuUpload("file", f); if (r) { kuAssetAdd(r); d.asset = r.id; if (!d.title) d.title = f.name.replace(/\.[^.]+$/, ""); re(); } return; }
    case "lg-move": KU.lgMove = KU.lgMove === i ? null : i; return kuReblock(bi);
    case "lg-del": d.markers.splice(i, 1); KU.lgMove = null; return re();
    case "lg-click": {
      if (e.target.closest(".ku-mk") && KU.lgMove == null) return;
      const img = a.querySelector("img"), r = img.getBoundingClientRect();
      const x = Math.round(1000 * (e.clientX - r.left) / r.width) / 10, y = Math.round(1000 * (e.clientY - r.top) / r.height) / 10;
      if (x < 0 || y < 0 || x > 100 || y > 100) return;
      if (KU.lgMove != null && d.markers[KU.lgMove]) { Object.assign(d.markers[KU.lgMove], {x, y}); KU.lgMove = null; }
      else if (d.markers.length < 20) d.markers.push({x, y, title: "", html: ""});
      return re();
    }
  }
}
function kuAssetAdd(r) { KU.assets = KU.assets || {}; KU.assets[r.id] = r; }

/* ---------- subtitrlar: avtomatik (Whisper navbati) va yozuvlar muharriri ---------- */
function kuCapJobText(asset) {
  const j = (KU.capJobs || {})[asset];
  if (!j) return "";
  const when = kuD(j.updated_at);
  return j.status === "tayyor" ? `Whisper subtitri tayyor (${j.cues} yozuv, ${when}) — tekshirib, kerak bo'lsa «Tahrirlash».`
    : j.status === "xato" ? `Whisper subtitri: xato — ${j.error || "noma'lum"}`
    : j.status === "bekor" ? "" : `Whisper subtitri: ${j.status_label.toLowerCase()}${j.pct ? ` (${Math.round(j.pct)}%)` : ""}${KU.capWorker === false ? " — montaj ishchisi o'chiq" : ""}`;
}
async function kuCapLoad() {
  if (!KU.cid) return;
  const r = await kuFetch(`/api/kurs/courses/${KU.cid}/captions`);
  if (!r.ok) return;
  KU.capWorker = r.data.worker; KU.capManual = r.data.manual; KU.capJobs = {};
  r.data.items.slice().reverse().forEach(j => { KU.capJobs[j.asset] = j; });
  document.querySelectorAll(".ku-capjob[data-cap-asset]").forEach(p => { p.textContent = kuCapJobText(+p.dataset.capAsset); });
  clearTimeout(KU.capT);
  if (r.data.items.some(j => j.status === "navbatda" || j.status === "ishlanmoqda")) KU.capT = setTimeout(() => { if (KU.view === "course") kuCapLoad(); }, 15000);
  else if (r.data.items.some(j => j.status === "tayyor" && !KU.capSeen?.[j.id])) {   // yangi tayyor subtitr bloklarga server tomonda qo'shilgan — darsni yangilash
    KU.capSeen = KU.capSeen || {}; const fresh = r.data.items.filter(j => j.status === "tayyor" && !KU.capSeen[j.id]);
    fresh.forEach(j => KU.capSeen[j.id] = 1);
    if (KU.capLoaded && KU.lid && !KU.dirty) kuLoadLesson(KU.lid, true);
  }
  KU.capLoaded = true;
}
async function kuCapRequest(asset, lang) {
  if (!asset) { toast("Avval video faylni yuklang"); return; }
  await kuFlush();
  const r = await kuApi(`/api/kurs/courses/${KU.cid}/captions`, {asset, lang});
  if (!r) return;
  toast(r.existing ? "Bu video uchun subtitr allaqachon navbatda" : r.worker ? "Subtitr navbatga qo'yildi — montaj ishchisi Whisper bilan tayyorlaydi" : `Navbatga qo'yildi, lekin montaj ishchisi o'chiq. ${KU.capManual || ""}`);
  kuCapLoad();
}
const kuTc = s => { s = Math.max(0, +s || 0); const h = Math.floor(s / 3600), m = Math.floor(s / 60) % 60, x = (s % 60).toFixed(3).padStart(6, "0"); return `${h ? String(h).padStart(2, "0") + ":" : ""}${String(m).padStart(2, "0")}:${x}`; };
const kuTcParse = t => { const p = String(t || "").trim().replace(",", ".").split(":").map(Number); if (!p.length || p.some(x => !isFinite(x))) return NaN; return p.reduce((a, x) => a * 60 + x, 0); };
async function kuCueEditor(cap, onSaved) {
  if (!cap?.asset) return;
  await kuFlush();
  const d = await kuApi(`/api/kurs/assets/${cap.asset}/cues`).catch(e => { toast(e.msg || "Subtitr o'qilmadi"); return null; });
  if (!d) return;
  let cues = d.cues.map(c => ({...c}));
  const ro = !KU.course?.caps?.write;
  const bg = kuModal(`Subtitr: ${cap.label || d.lang}`, `<p class="ku-note">${d.auto ? "Whisper avtomatik yaratgan — nomlar, atamalar va tinish belgilarini tekshiring. " : ""}Vaqt: daqiqa:soniya.ms (masalan 01:05.500). Saqlanganda yangi fayl yaratiladi — eski holat versiyalarda qoladi.</p>
    <div class="ku-cues" id="kuCues" role="list" aria-label="Subtitr yozuvlari"></div>
    ${ro ? "" : `<div class="ku-acts"><button type="button" class="btn sm ghost" id="kuCueAdd">${kuI("plus", 14)} Yozuv qo'shish</button></div>`}`,
    {wide: true, okText: "Saqlash", onOk: ro ? null : async bg => {
      const out = [];
      for (const [k, c] of cues.entries()) {
        const s = kuTcParse(c.startT ?? kuTc(c.start)), e = kuTcParse(c.endT ?? kuTc(c.end));
        if (!(s >= 0) || !(e > s)) { toast(`${k + 1}-yozuv: vaqt noto'g'ri (tugash boshlanishdan keyin bo'lsin)`); return false; }
        if (!String(c.text || "").trim()) { toast(`${k + 1}-yozuv: matn bo'sh`); return false; }
        out.push({start: s, end: e, text: c.text});
      }
      const r = await kuApi(`/api/kurs/courses/${KU.cid}/vtt`, {asset: cap.asset, lang: d.lang, cues: out});
      if (!r) return false;
      kuAssetAdd(r); onSaved(r.id); toast(`Subtitr saqlandi (${out.length} yozuv)`); return true;
    }});
  const box = bg.querySelector("#kuCues");
  const paint = () => {
    box.innerHTML = cues.map((c, k) => `<div class="ku-cue" role="listitem" data-k="${k}"><span class="ku-cue-n">${k + 1}</span>
      <input class="ku-in sm" data-f="startT" value="${esc(c.startT ?? kuTc(c.start))}" aria-label="${k + 1}-yozuv boshlanishi" ${ro ? "readonly" : ""} inputmode="decimal">
      <input class="ku-in sm" data-f="endT" value="${esc(c.endT ?? kuTc(c.end))}" aria-label="${k + 1}-yozuv tugashi" ${ro ? "readonly" : ""} inputmode="decimal">
      <textarea class="ku-in sm" data-f="text" rows="2" maxlength="500" aria-label="${k + 1}-yozuv matni" ${ro ? "readonly" : ""}>${esc(c.text)}</textarea>
      ${ro ? "" : `<button type="button" class="ku-ib sm" data-del="${k}" aria-label="${k + 1}-yozuvni o'chirish">${ico("x", 14)}</button>`}</div>`).join("") || `<p class="ku-note">Yozuv yo'q.</p>`;
  };
  box.addEventListener("input", e => { const row = e.target.closest("[data-k]"); if (row && e.target.dataset.f) cues[+row.dataset.k][e.target.dataset.f] = e.target.value; });
  box.addEventListener("click", e => { const x = e.target.closest("[data-del]"); if (x) { cues.splice(+x.dataset.del, 1); paint(); box.querySelector(`[data-k="${Math.min(+x.dataset.del, cues.length - 1)}"] textarea`)?.focus(); } });
  bg.querySelector("#kuCueAdd")?.addEventListener("click", () => {
    const last = cues[cues.length - 1], s = last ? (kuTcParse(last.endT ?? kuTc(last.end)) || 0) + 0.2 : 0;
    cues.push({start: s, end: s + 3, text: ""}); paint(); box.querySelector(`[data-k="${cues.length - 1}"] textarea`)?.focus();
  });
  paint();
}
function kuInsert(type, at) {
  const def = kuClone(KU.meta.blocks[type].default);
  KU.blocks.splice(at, 0, {id: kuUid(), type, data: def, issues: []});
  KU.sel = at; kuRenderBlocks(); kuRenderPanel(); kuDirty();
  const el = document.querySelector(`#kuBlocks [data-bi="${at}"]`);
  if (el) { el.scrollIntoView({block: "center", behavior: "smooth"}); setTimeout(() => el.querySelector("input, textarea, [data-rich], .ku-drop")?.focus({preventScroll: true}), 250); }
}
function kuDelete(bi) {
  const [b] = KU.blocks.splice(bi, 1);
  KU.trash = {lid: KU.lid, bi, b}; KU.sel = -1;
  kuRenderBlocks(); kuRenderPanel(); kuDirty();
  let u = document.getElementById("kuUndo");
  if (!u) { u = document.createElement("div"); u.id = "kuUndo"; u.className = "ku-undo"; u.setAttribute("role", "status"); document.body.appendChild(u); }
  u.innerHTML = `<span>«${esc(KU.meta.blocks[b.type]?.label || b.type)}» bloki o'chirildi</span><button type="button" class="btn sm">${kuI("undo", 14)} Bekor qilish</button>`;
  clearTimeout(u._t); u._t = setTimeout(() => u.remove(), 10000);
  u.querySelector("button").onclick = () => {
    const t = KU.trash; u.remove(); if (!t || t.lid !== KU.lid) { toast("Blok boshqa darsda edi"); return; }
    KU.blocks.splice(Math.min(t.bi, KU.blocks.length), 0, t.b); KU.trash = null; KU.sel = t.bi; kuRenderBlocks(); kuRenderPanel(); kuDirty(); toast("Blok qaytarildi");
  };
}

/* ---------- «AI bilan tahrirlash»: savol bloklari (Rise'dagi «Edit with AI» kabi) ---------- */
/* Word'dan nusxa (✅ — to'g'ri javob) → server avval ✅ ni o'zi tahlil qiladi, so'ng AI tozalaydi, har variantga izoh yozadi (app/kurs_ai.py).
   Natija bazaga yozilmaydi — avval ko'rsatiladi; «Bloknu almashtirish» bosilgandagina blok o'zgaradi (keyin oddiy avtosaqlash). */
const kuAiOk = b => !!(KU.meta?.caps?.ai && KU.course?.caps?.write && (b.type === "knowledge" || b.type === "question"));
/* telefonda blok asboblari qatori to'lib ketadi — shu yerda AI tugmasi blok ichida (CSS: faqat ≤ 520 px) */
const kuAiInline = b => kuAiOk(b) ? `<div class="ku-ai-inl"><button type="button" class="btn sm ghost" data-act="ai">${ico("spark", 15)} AI bilan tahrirlash</button></div>` : "";
function kuAiNote(b) {
  const m = KU.aiMark?.[b.id]; if (!m) return "";
  const why = !m.ai ? "✅ belgilaridan tuzildi, izohlarsiz." : m.guessed ? "Savolda ✅ yo'q edi — AI to'g'ri javobni o'zi tanladi." : "";
  return `<div class="ku-ainote ${m.guessed || !m.ai ? "warn" : ""}" role="status">${ico("spark", 14)}<span><b>AI tuzdi — to'g'ri javobni tekshiring.</b>${why ? ` ${esc(why)}` : ""} Kerak bo'lsa belgini boshqa variantga o'tkazing.</span>
    ${m.prev ? `<button type="button" class="btn sm ghost" data-act="ai-undo">Avvalgisini qaytarish</button>` : ""}<button type="button" class="ku-ib sm" data-act="ai-x" aria-label="Eslatmani yopish" title="Yopish">${ico("x", 14)}</button></div>`;
}
function kuAiSeed(b) {
  const d = b?.data || {};
  if (d.kind === "fill") return (d.question || (d.accept || []).some(Boolean)) ? `${d.question || ""}\nJavob: ${(d.accept || []).filter(Boolean).join(" / ")}`.trim() : "";
  if (!d.question && !(d.answers || []).some(a => a.text)) return "";
  return [d.question || "", ...(d.answers || []).map((a, i) => `${String.fromCharCode(65 + i)}) ${a.text || ""}${a.correct ? " ✅" : ""}`)].join("\n");
}
function kuAiPreview(r) {
  const d = r.block.data, L = i => String.fromCharCode(65 + i), K = KU.meta.q_kinds || {};
  const notes = [];
  if (r.detail) notes.push(["bad", r.detail]);
  if (r.ai && r.answer_guessed) notes.push(["warn", "Savolda ✅ yo'q edi — AI to'g'ri javobni o'zi tanladi. Almashtirishdan oldin tekshiring."]);
  if (r.answer_missing) notes.push(["warn", "To'g'ri javob aniqlanmadi — almashtirgandan keyin blokda belgilang."]);
  (r.warnings || []).forEach(w => notes.push(["warn", w]));
  const body = d.kind === "fill"
    ? `<div class="ku-aip-acc">${(d.accept || []).map(a => `<span class="ku-chip ok">${ico("check", 12)} ${esc(a)}</span>`).join("")}</div>`
    : `<ol class="ku-aip-opts">${(d.answers || []).map((a, i) => `<li class="${a.correct ? "ok" : ""}"><span class="l" aria-hidden="true">${L(i)}</span><div><b>${esc(a.text)}</b>${a.correct ? `<span class="ku-chip ok">${ico("check", 12)} To'g'ri javob</span>` : ""}
      ${a.feedback ? `<p>${esc(a.feedback)}</p>` : ""}</div></li>`).join("")}</ol>`;
  return `${notes.map(([c, t]) => `<div class="ku-aip-n ${c}" role="${c === "bad" ? "alert" : "status"}">${ico(c === "bad" ? "alert" : "spark", 14)}<span>${esc(t)}</span></div>`).join("")}
    <div class="ku-aip"><div class="ku-aip-h"><span class="ku-chip info">${esc(K[d.kind] || d.kind)}</span>${r.ai ? "" : `<span class="ku-chip">AI'siz (✅ dan)</span>`}</div>
    <p class="ku-aip-q">${esc(d.question)}</p>${body}
    ${d.feedback_correct || d.feedback_wrong ? `<div class="ku-aip-fb">${d.feedback_correct ? `<p><b>To'g'ri javobda:</b> ${esc(d.feedback_correct)}</p>` : ""}${d.feedback_wrong ? `<p><b>Noto'g'ri javobda:</b> ${esc(d.feedback_wrong)}</p>` : ""}</div>` : ""}</div>`;
}
function kuAiOpen({bi = -1, at = -1}) {
  const old = bi >= 0 ? KU.blocks[bi] : null, quiz = KU.lesson.type === "quiz", btype = old ? old.type : quiz ? "question" : "knowledge", oldId = old?.id;
  if (!KU.meta.blocks[btype]) return;
  const st = {res: null, busy: false, seq: 0}, kinds = {auto: "Avto (AI o'zi aniqlaydi)", single: "Bitta javob", multi: "Bir nechta javob", tf: "To'g'ri / noto'g'ri", fill: "Bo'sh joyni to'ldirish"};
  const bg = kuModal(old ? "AI bilan tahrirlash" : "AI bilan savol", `<div class="ku-ai">
    <div class="ku-ai-in"><label class="ku-f"><span>Savolni shu yerga qo'ying (Word'dan nusxa — ✅ to'g'ri javobni bildiradi) yoki AI'ga ko'rsatma yozing</span>
      <textarea class="ku-in" id="kuAiT" rows="8" maxlength="6000" autofocus placeholder="1. Startap qanday kompaniya?&#10;A) Davlat korxonasi&#10;B) Tez o'sishga yo'naltirilgan yangi kompaniya ✅&#10;C) Xolding bo'linmasi">${esc(old ? kuAiSeed(old) : "")}</textarea></label>
      <div class="ku-ai-opts"><label class="ku-f"><span>Savol turi</span><select class="ku-in" id="kuAiK">${Object.entries(kinds).map(([k, t]) => `<option value="${k}">${esc(t)}</option>`).join("")}</select></label>
        <label class="ku-f"><span>Ko'rsatma (ixtiyoriy)</span><input class="ku-in" id="kuAiH" maxlength="500" placeholder="Masalan: savolni soddaroq yoz"></label></div>
      <div class="ku-acts"><button type="button" class="btn primary" id="kuAiGo">${ico("spark", 15)} AI bilan tuzish</button><button type="button" class="btn ghost" id="kuAiRe" hidden>Qayta urinish</button></div>
      <p class="ku-note">AI savol va variantlarni tozalaydi, har variantga izoh yozadi. ✅ bilan belgilangan to'g'ri javobni o'zgartirmaydi. Matndagi fakt AI tomonidan o'ylab topilmaydi — baribir tekshirib chiqing.</p></div>
    <div class="ku-ai-out" id="kuAiPv" aria-live="polite"><p class="ku-note">Natija shu yerda ko'rinadi.</p></div></div>`,
    {wide: true, cls: "ai", okText: old ? "Bloknu almashtirish" : "Blokni qo'shish", onOk: () => {
      if (!st.res?.block) return false;
      const data = kuClone(st.res.block.data), prev = old ? KU.blocks.findIndex(x => x.id === oldId) : -1;
      if (old && prev < 0) { toast("Blok topilmadi (o'chirilgan bo'lishi mumkin)"); return true; }
      const mark = {guessed: !!st.res.answer_guessed || !!st.res.answer_missing, ai: !!st.res.ai};
      if (old) {
        const b = KU.blocks[prev]; if (b.type === "knowledge") data.retry = b.data.retry !== false;
        mark.prev = kuClone(b.data); b.data = data; KU.aiMark = KU.aiMark || {}; KU.aiMark[b.id] = mark;
        KU.sel = prev; kuReblock(prev); kuRenderPanel(); kuDirty();
        document.querySelector(`#kuBlocks [data-bi="${prev}"] .ku-ainote`)?.scrollIntoView({block: "center", behavior: "smooth"});
      } else {
        const id = kuUid(), pos = Math.max(0, Math.min(at < 0 ? KU.blocks.length : at, KU.blocks.length));
        if (btype === "knowledge") data.retry = true;
        KU.blocks.splice(pos, 0, {id, type: btype, data, issues: []}); KU.aiMark = KU.aiMark || {}; KU.aiMark[id] = mark;
        KU.sel = pos; kuRenderBlocks(); kuRenderPanel(); kuDirty();
        document.querySelector(`#kuBlocks [data-bi="${pos}"] .ku-ainote`)?.scrollIntoView({block: "center", behavior: "smooth"});
      }
      kuSay("AI savolni tuzdi — to'g'ri javobni tekshiring");
      toast("Blok AI tuzgan savol bilan almashtirildi — to'g'ri javobni tekshiring");
      return true;
    }});
  const ok = bg.querySelector("[data-ok]"), go = bg.querySelector("#kuAiGo"), re = bg.querySelector("#kuAiRe"), pv = bg.querySelector("#kuAiPv"), T = bg.querySelector("#kuAiT");
  ok.disabled = true;
  const run = async () => {
    const text = T.value.trim(), hint = bg.querySelector("#kuAiH").value.trim(), qtype = bg.querySelector("#kuAiK").value;
    if (text.length < 5 && !hint) { pv.innerHTML = `<div class="ku-aip-n bad" role="alert">${ico("alert", 14)}<span>Savol matnini yoki AI uchun ko'rsatmani kiriting.</span></div>`; T.focus(); return; }
    const my = ++st.seq; st.busy = true; st.res = null; go.disabled = re.disabled = ok.disabled = true;
    pv.innerHTML = `<p class="ku-note ku-ai-wait"><span class="ku-spin" aria-hidden="true"></span> AI savolni tuzmoqda…</p>`;
    let r = null;
    try { r = await kuFetch(`/api/kurs/lessons/${KU.lid}/ai-question`, {text, hint, qtype, btype}); } catch (e) { r = null; }
    if (my !== st.seq || !bg.isConnected) return;
    st.busy = false; go.disabled = re.disabled = false; re.hidden = false; go.focus({preventScroll: true});   /* fokus oynada qolsin (Esc ishlaydi) */
    if (!r) { pv.innerHTML = `<div class="ku-aip-n bad" role="alert">${ico("alert", 14)}<span>Aloqa xatosi — qayta urinib ko'ring.</span></div>`; return; }
    if (r.data?.block) { st.res = {...r.data, detail: r.ok ? "" : r.data.detail}; pv.innerHTML = kuAiPreview(st.res); ok.disabled = false; ok.focus({preventScroll: true});
      if (innerWidth <= 820) pv.scrollIntoView({block: "start", behavior: "smooth"}); return; }
    pv.innerHTML = `<div class="ku-aip-n bad" role="alert">${ico("alert", 14)}<span>${esc(kuErr(r.data))}</span></div>`;
  };
  go.onclick = run; re.onclick = run;
  T.addEventListener("keydown", e => { if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) { e.preventDefault(); run(); } });
}

/* ---------- blok kutubxonasi ---------- */
/* Blok eskizlari: oddiy sxematik chizmalar (inline SVG, tashqi fayl yo'q); binafsha — urg'u, kulrang — matn chiziqlari */
const kuSvg = body => `<svg viewBox="0 0 96 60" aria-hidden="true" focusable="false">${body}</svg>`;
const kuR = (x, y, w, h, c = "l", rx = 2) => `<rect class="${c}" x="${x}" y="${y}" width="${w}" height="${h}" rx="${rx}"/>`;
const kuLn = (x, y, w, n = 3, g = 7, c = "l") => Array.from({length: n}, (_, i) => kuR(x, y + i * g, i === n - 1 ? Math.round(w * .6) : w, 3, c, 1.5)).join("");
const kuCr = (cx, cy, r, c = "a") => `<circle class="${c}" cx="${cx}" cy="${cy}" r="${r}"/>`;
const kuMtn = (x, y, w, h) => `${kuR(x, y, w, h, "p", 3)}<path class="l" d="M${x} ${y + h - 3}l${w * .28} -${h * .42}l${w * .2} ${h * .22}l${w * .22} -${h * .34}l${w * .3} ${h * .54}z"/>${kuCr(x + w * .78, y + h * .26, 3.2)}`;
const KU_THUMB = {
  heading: () => kuR(10, 16, 58, 9, "a", 2) + kuLn(10, 33, 76, 2, 7),
  paragraph: () => kuLn(10, 12, 76, 5, 8),
  heading_paragraph: () => kuR(10, 11, 42, 7, "a", 2) + kuLn(10, 26, 76, 4, 8),
  quote: () => kuR(10, 12, 3, 36, "a", 1.5) + `<text class="at" x="18" y="30" font-size="26" font-weight="800">“</text>` + kuLn(34, 22, 52, 3, 8),
  list: () => [0, 1, 2].map(i => kuCr(14, 16 + i * 14, 3) + kuR(24, 14.5 + i * 14, i === 1 ? 50 : 62, 3, "l", 1.5)).join(""),
  table: () => kuR(10, 10, 76, 9, "a", 2) + [0, 1, 2].map(r => [0, 1, 2].map(c => kuR(10 + c * 26, 21 + r * 11, 24, 9, "p", 1.5)).join("")).join(""),
  image: () => kuMtn(14, 8, 68, 44),
  image_text: () => kuMtn(8, 10, 38, 40) + kuLn(52, 14, 36, 4, 8),
  gallery: () => kuMtn(10, 8, 36, 20) + kuMtn(50, 8, 36, 20) + kuMtn(10, 32, 36, 20) + kuMtn(50, 32, 36, 20),
  video: () => kuR(10, 8, 76, 44, "p", 4) + kuCr(48, 30, 11) + `<path class="w" d="M44 24l11 6-11 6z"/>`,
  audio: () => [8, 16, 26, 14, 30, 20, 10, 24, 16, 8].map((h, i) => kuR(14 + i * 7.4, 30 - h / 2, 4, h, i % 3 ? "l" : "a", 2)).join(""),
  attachment: () => `<path class="p" d="M30 8h24l12 12v32H30z"/><path class="l" d="M54 8v12h12z"/>` + kuLn(36, 28, 24, 2, 7) + kuCr(70, 44, 8) + `<path class="w" d="M70 39v8m-3.5-3.5L70 47l3.5-3.5" fill="none" stroke="#fff" stroke-width="1.8" stroke-linecap="round"/>`,
  labeled_graphic: () => kuMtn(12, 8, 72, 44) + kuCr(34, 28, 6) + kuCr(60, 22, 6) + kuCr(70, 40, 6) + `<text class="wt" x="34" y="31" font-size="8" text-anchor="middle" font-weight="800">1</text><text class="wt" x="60" y="25" font-size="8" text-anchor="middle" font-weight="800">2</text><text class="wt" x="70" y="43" font-size="8" text-anchor="middle" font-weight="800">3</text>`,
  accordion: () => kuR(10, 8, 76, 10, "a", 2) + kuLn(14, 22, 68, 2, 6) + kuR(10, 36, 76, 8, "p", 2) + kuR(10, 47, 76, 8, "p", 2),
  tabs: () => kuR(10, 8, 24, 9, "a", 3) + kuR(36, 8, 24, 9, "p", 3) + kuR(62, 8, 24, 9, "p", 3) + kuR(10, 20, 76, 32, "p", 3) + kuLn(16, 27, 64, 3, 8),
  flashcards: () => kuR(24, 8, 60, 38, "p", 4) + kuR(12, 15, 60, 38, "a", 4) + kuR(22, 28, 36, 3, "w", 1.5) + kuR(22, 36, 24, 3, "w", 1.5),
  process: () => `<path class="l" d="M20 30h56" stroke="#cfc4d9" stroke-width="3"/>` + [20, 48, 76].map((x, i) => kuCr(x, 30, 9) + `<text class="wt" x="${x}" y="34" font-size="10" text-anchor="middle" font-weight="800">${i + 1}</text>`).join(""),
  timeline: () => kuR(26, 8, 2.5, 44, "l", 1) + [0, 1, 2].map(i => kuCr(27, 14 + i * 16, 4) + kuR(36, 12 + i * 16, 40, 3, "l", 1.5) + kuR(36, 18 + i * 16, 26, 3, "p", 1.5) + kuR(8, 12.5 + i * 16, 12, 3, "p", 1.5)).join(""),
  sorting: () => kuR(8, 8, 38, 10, "a", 2) + kuR(50, 8, 38, 10, "a", 2) + kuR(8, 22, 38, 30, "p", 3) + kuR(50, 22, 38, 30, "p", 3) + kuR(12, 27, 30, 6, "l", 3) + kuR(12, 37, 22, 6, "l", 3) + kuR(54, 27, 30, 6, "l", 3),
  matching: () => [0, 1, 2].map(i => kuR(8, 9 + i * 15, 30, 10, "p", 2) + kuR(58, 9 + i * 15, 30, 10, "p", 2)).join("") + `<path d="M38 14L58 29M38 29L58 44M38 44L58 14" stroke="#7837a8" stroke-width="1.8" fill="none"/>`,
  knowledge: () => kuR(10, 8, 60, 4, "l", 2) + [0, 1, 2].map(i => kuCr(15, 22 + i * 12, 3.5, i === 1 ? "a" : "l") + kuR(24, 20.5 + i * 12, i === 1 ? 52 : 44, 3, i === 1 ? "p" : "l", 1.5)).join(""),
  divider: () => kuR(10, 29, 76, 2.5, "l", 1) + kuCr(48, 30, 3.5),
  continue: () => kuR(8, 21, 80, 18, "a", 2) + kuR(30, 28.5, 36, 3, "w", 1.5),
  button: () => kuR(22, 20, 52, 20, "a", 10) + kuR(34, 28.5, 28, 3, "w", 1.5),
};
KU_THUMB.question = KU_THUMB.knowledge;
const KU_LIB_GROUPS = [["Matn", ["heading", "paragraph", "heading_paragraph", "quote", "list", "table"]],
  ["Rasm va video", ["image", "image_text", "gallery", "video", "audio", "attachment", "labeled_graphic"]],
  ["Mashq va interaktiv", ["knowledge", "matching", "sorting", "flashcards", "accordion", "tabs", "process", "timeline"]],
  ["Boshqaruv", ["continue", "divider", "button"]]];
function kuLibrary(at) {
  const M = KU.meta, avail = M.lesson_blocks.filter(t => M.blocks[t]);
  const tile = t => `<button type="button" class="ku-tile" data-t="${t}"><span class="th" aria-hidden="true">${KU_THUMB[t] ? kuSvg(KU_THUMB[t]()) : ""}</span><b>${esc(M.blocks[t].label)}</b><small>${esc(M.blocks[t].desc)}</small></button>`;
  const used = new Set(KU_LIB_GROUPS.flatMap(([, l]) => l)), rest = avail.filter(t => !used.has(t));
  const groups = KU_LIB_GROUPS.map(([n, l]) => [n, l.filter(t => avail.includes(t))]).concat(rest.length ? [["Boshqa", rest]] : []).filter(([, l]) => l.length);
  const bg = kuModal("Blok qo'shish", `<label class="ku-search wide">${ico("search", 16)}<input type="search" id="kuLibQ" placeholder="Blok nomi" aria-label="Blok qidirish" autofocus></label>
    <div id="kuLib">${groups.map(([n, l]) => `<section data-cat="${esc(n)}"><h4>${esc(n)}</h4><div class="ku-tiles">${l.map(tile).join("")}</div></section>`).join("")}</div>`, {wide: true, cls: "lib"});
  bg.querySelector("#kuLibQ").oninput = e => { const q = e.target.value.toLowerCase().trim();
    bg.querySelectorAll(".ku-tile").forEach(t => t.hidden = !!q && !(t.textContent.toLowerCase().includes(q)));
    bg.querySelectorAll("#kuLib section").forEach(s => s.hidden = ![...s.querySelectorAll(".ku-tile")].some(t => !t.hidden)); };
  if (M.caps.ai && M.blocks.knowledge) {
    const g = bg.querySelector('#kuLib section[data-cat="Mashq va interaktiv"] .ku-tiles');
    g?.insertAdjacentHTML("afterbegin", `<button type="button" class="ku-tile ai" data-ai="1"><span class="th" aria-hidden="true">${kuSvg(KU_THUMB.knowledge())}</span><b>${ico("spark", 14)} AI bilan savol</b><small>Word'dan nusxa — AI savol va izohlarni tuzadi</small></button>`);
  }
  bg.querySelectorAll(".ku-tile").forEach(t => t.onclick = () => { bg._close(); t.dataset.ai ? kuAiOpen({at}) : kuInsert(t.dataset.t, at); });
}

/* ---------- rasm tanlash: kurs kutubxonasi + yuklash ---------- */
function kuPickImage() {
  return new Promise(async res => {
    let done = false;
    const fin = v => { if (!done) { done = true; res(v); } };
    const d = await kuApi(`/api/kurs/courses/${KU.cid}/assets`).catch(() => ({items: []}));
    const imgs = d.items.filter(a => a.kind === "image");
    const bg = kuModal("Rasm tanlash", `<div class="ku-acts">${`<button type="button" class="btn primary" id="kuImgUp">${kuI("upload", 15)} Kompyuterdan yuklash</button>`}<span class="ku-note">.png, .jpg, .gif, .webp · ${KU.meta.limits.image_mb} MB gacha · 1600 px gacha kichraytiriladi</span></div>
      ${imgs.length ? `<div class="ku-lib-imgs">${imgs.map(a => `<button type="button" class="ku-lib-img" data-id="${a.id}" title="${esc(a.name)}"><img src="${esc(a.url)}" alt="${esc(a.name)}" loading="lazy"><small>${esc(a.name)}</small></button>`).join("")}</div>` : `<p class="ku-note">Kursda hali rasm yo'q.</p>`}`,
      {wide: true, onClose: () => fin(null)});
    bg.querySelectorAll("[data-id]").forEach(b => b.onclick = () => { fin(+b.dataset.id); bg._close(); });
    bg.querySelector("#kuImgUp").onclick = async () => { const [f] = await kuPickFile("image/png,image/jpeg,image/gif,image/webp"); if (!f) return; const r = await kuUpload("image", f); if (r) { kuAssetAdd(r); fin(r.id); bg._close(); } };
  });
}

/* ---------- test darsi: sozlamalar ---------- */
function kuQuizHead() {
  const q = KU.quiz, M = KU.meta;
  return `<div class="ku-qset"><div class="ku-qgrid">
      <label class="ku-f"><span>O'tish bali, %</span><input class="ku-in" type="number" min="0" max="100" data-q="pass_pct" value="${q.pass_pct}"></label>
      <label class="ku-f"><span>Urinishlar (0 — cheksiz)</span><input class="ku-in" type="number" min="0" max="20" data-q="attempts" value="${q.attempts}"></label>
      <label class="ku-f"><span>Har urinishda savollar (0 — hammasi)</span><input class="ku-in" type="number" min="0" max="200" data-q="draw" value="${q.draw}"></label>
      <label class="ku-f"><span>To'g'ri javoblarni ko'rsatish</span><select class="ku-in" data-q="reveal">${Object.entries(M.reveal).map(([k, t]) => `<option value="${k}" ${q.reveal === k ? "selected" : ""}>${esc(t)}</option>`).join("")}</select></label></div>
    <div class="ku-acts"><label class="ku-chk"><input type="checkbox" data-q="shuffle" ${q.shuffle ? "checked" : ""}> Javoblarni aralashtirish</label>
      <label class="ku-chk"><input type="checkbox" data-q="randomize" ${q.randomize ? "checked" : ""}> Savollar tartibini aralashtirish</label></div>
    <label class="ku-f"><span>Kirish matni (ixtiyoriy)</span><textarea class="ku-in" rows="2" maxlength="1000" data-q="intro">${esc(q.intro || "")}</textarea></label></div>`;
}

/* ---------- Test bankdan savollar ---------- */
async function kuTestbank() {
  const d = await kuApi("/api/kurs/testbank").catch(() => ({items: [], courses: []}));
  const bg = kuModal("Test bankdan savollar", `<p class="ku-note">Faqat tasdiqlangan savollar. ${KU.lesson.type === "quiz" ? "Testga savol sifatida" : "Darsga «Bilimni tekshirish» bloki sifatida"} qo'shiladi.</p>
    <div class="ku-row"><select class="ku-in" id="kuTbC" aria-label="Fan"><option value="0">Barcha fanlar</option>${d.courses.map(c => `<option value="${c.id}">${esc(c.subject)} (${c.n})</option>`).join("")}</select>
      <input class="ku-in" type="search" id="kuTbQ" placeholder="Savol matni" aria-label="Qidirish"></div><div id="kuTbL" class="ku-tbl-list"></div>`,
    {wide: true, okText: "Qo'shish", onOk: async bg => {
      const ids = [...bg.querySelectorAll("#kuTbL input:checked")].map(x => +x.value);
      if (!ids.length) { toast("Savollarni belgilang"); return false; }
      const r = await kuApi("/api/kurs/testbank/convert", {ids}); if (!r) return false;
      const quiz = KU.lesson.type === "quiz";
      r.questions.forEach(q => KU.blocks.push({id: kuUid(), type: quiz ? "question" : "knowledge", data: quiz ? q.data : {...q.data, retry: true}, issues: []}));
      kuRenderBlocks(); kuDirty(); toast(`${r.questions.length} ta savol qo'shildi`); return true;
    }});
  const paint = rows => { bg.querySelector("#kuTbL").innerHTML = rows.length ? rows.map(q => `<label class="ku-tbq"><input type="checkbox" value="${q.id}"><span><b>${esc(q.stem)}</b><small class="muted">${esc(q.subject)} · ${q.topic_no}-mavzu · ${({mcq: "test", tf: "to'g'ri/noto'g'ri", fill: "bo'sh joy"})[q.qtype] || q.qtype}</small></span></label>`).join("") : `<p class="ku-note">Savol topilmadi.</p>`; };
  paint(d.items);
  let t = 0; const reload = () => { clearTimeout(t); t = setTimeout(async () => { const x = await kuApi(`/api/kurs/testbank?course_id=${bg.querySelector("#kuTbC").value}&q=${encodeURIComponent(bg.querySelector("#kuTbQ").value)}`).catch(() => null); if (x) paint(x.items); }, 250); };
  bg.querySelector("#kuTbC").onchange = reload; bg.querySelector("#kuTbQ").oninput = reload;
}

/* ---------- o'ng panel: tanlangan blok sozlamalari ---------- */
const kuSel = (k, v, opts, lbl) => `<label class="ku-f"><span>${esc(lbl)}</span><select class="ku-in" data-k="${k}">${Object.entries(opts).map(([o, t]) => `<option value="${o}" ${String(v) === o ? "selected" : ""}>${esc(t)}</option>`).join("")}</select></label>`;
const kuChk = (k, v, lbl) => `<label class="ku-chk"><input type="checkbox" data-k="${k}" ${v ? "checked" : ""}> ${esc(lbl)}</label>`;
function kuPanelFields(t, d) {
  switch (t) {
    case "heading": return kuSel("level", d.level, {2: "Katta (H2)", 3: "O'rta (H3)"}, "Sarlavha darajasi");
    case "quote": return kuSel("style", d.style, {quote: "Iqtibos (muallif bilan)", impact: "Urg'u — katta matn"}, "Ko'rinish");
    case "list": return kuSel("style", d.style, {bulleted: "Belgili", numbered: "Raqamli", checkbox: "Belgilash (☐)"}, "Ro'yxat turi");
    case "table": return kuChk("header", d.header, "Birinchi qator — sarlavha");
    case "image": return kuSel("layout", d.layout, {centered: "Markazda", full: "To'liq kenglik", hero: "Katta (sahifa kengligida)", banner: "Tasma (past, keng)"}, "Joylashuv");
    case "image_text": return kuSel("side", d.side, {left: "Rasm chapda", right: "Rasm o'ngda"}, "Rasm joyi");
    case "gallery": return kuSel("style", d.style, {grid: "To'r", carousel: "Karusel"}, "Ko'rinish");
    case "video": return kuSel("source", d.source, {file: "Video fayl", youtube: "YouTube"}, "Manba") + `<label class="ku-f"><span>Sarlavha</span>${kuIn("title", d.title, "Video sarlavhasi", "", 200)}</label>`;
    case "flashcards": return kuSel("style", d.style, {grid: "To'r (hammasi birdan)", stack: "Dasta (birma-bir)"}, "Ko'rinish");
    case "knowledge": return kuSel("kind", d.kind, KU.meta.q_kinds, "Savol turi") + kuChk("retry", d.retry, "Qayta urinishga ruxsat");
    case "question": return kuSel("kind", d.kind, KU.meta.q_kinds, "Savol turi");
    case "divider": return kuSel("style", d.style, {line: "Chiziq", dots: "Nuqtalar", space: "Bo'sh joy"}, "Ko'rinish");
    case "continue": return kuSel("require", d.require, {none: "Tugmani bosish kifoya", interactions: "Avval yuqoridagi mashqlar bajarilsin"}, "Tugma qachon ochiladi") +
      `<p class="ku-note">Tugmani bosmaguncha keyingi qism yopiq turadi.</p><label class="ku-f"><span>Eslatma (tugma bloklanganda)</span>${kuIn("hint", d.hint, KU.meta.labels.complete_hint, "", 200)}</label>`;
  }
  return "";
}
function kuRenderPanel() {
  const el = $("#kuPanel"); if (!el) return;
  const b = KU.blocks[KU.sel];
  if (!KU.lid) { el.innerHTML = ""; return; }
  if (!b) {
    const iss = KU.blocks.flatMap((x, i) => (x.issues || []).map(m => ({i, ...m})));
    el.innerHTML = `<div class="ku-ph"><b>${KU.lesson.type === "quiz" ? "Test" : "Dars"}</b><button type="button" class="ku-ib only-n" data-pclose aria-label="Yopish">${ico("x", 16)}</button></div>
      <p class="ku-note">${KU.blocks.length} ta ${KU.lesson.type === "quiz" ? "savol" : "blok"}. Blokni tanlang — sozlamalari shu yerda chiqadi.</p>
      ${iss.length ? `<h4>Tekshiruv (${iss.length})</h4><ul class="ku-isslist">${iss.slice(0, 40).map(x => `<li class="${x.level === "xato" ? "bad" : "warn"}"><button type="button" class="pk-link" data-goto="${x.i}">${x.i + 1}-blok</button> ${esc(x.msg)}</li>`).join("")}</ul>`
        : `<p class="ku-note ok">${ico("check", 14)} Bloklarda muammo yo'q.</p>`}
      <div class="ku-tip"><b>Maslahat</b><span>«+» — blok qo'shish · blokni sudrab yoki ↑ ↓ bilan ko'chiring · o'zgarishlar o'zi saqlanadi.</span></div>`;
  } else {
    const f = kuPanelFields(b.type, b.data);
    el.innerHTML = `<div class="ku-ph"><b>${esc(KU.meta.blocks[b.type]?.label || b.type)}</b><button type="button" class="ku-ib only-n" data-pclose aria-label="Yopish">${ico("x", 16)}</button></div>
      <div data-pbi="${KU.sel}">${f || `<p class="ku-note">Bu blokda qo'shimcha sozlama yo'q — hammasi blokning o'zida tahrirlanadi.</p>`}</div>
      ${(b.issues || []).length ? `<h4>Tekshiruv</h4><ul class="ku-isslist">${b.issues.map(x => `<li class="${x.level === "xato" ? "bad" : "warn"}">${esc(x.msg)}</li>`).join("")}</ul>` : ""}
      <div class="ku-acts"><button type="button" class="btn sm ghost" data-pact="dup">${kuI("copy", 14)} Nusxa</button><button type="button" class="btn sm ghost danger" data-pact="del">${kuI("trash", 14)} O'chirish</button></div>
      <p class="ku-note">Blok kodi: <code>${esc(b.id)}</code></p>`;
  }
}
function kuBindPanel() {
  const el = $("#kuPanel");
  const on = e => {
    const f = e.target.closest("[data-k]"), w = e.target.closest("[data-pbi]"); if (!f || !w) return;
    const bi = +w.dataset.pbi, b = KU.blocks[bi]; if (!b) return;
    const k = f.dataset.k, v = kuVal(f);
    if (k === "kind") { const fake = {dataset: {act: "qkind", v}}; return kuAct(fake, bi); }
    kuSet(b.data, k, k === "level" ? +v : v);
    if (e.type === "change") kuReblock(bi);
    kuDirty();
  };
  el.addEventListener("change", on);
  el.addEventListener("input", e => { if (e.target.matches("input[type=text], input:not([type]), textarea")) on(e); });
  el.addEventListener("click", e => {
    if (e.target.closest("[data-pclose]")) { el.classList.remove("open"); return; }
    const g = e.target.closest("[data-goto]"); if (g) { kuSelect(+g.dataset.goto); return; }
    const a = e.target.closest("[data-pact]"); if (!a || KU.sel < 0) return;
    if (a.dataset.pact === "del") kuDelete(KU.sel); else kuAct({dataset: {act: "dup"}}, KU.sel);
  });
}

/* ---------- avtosaqlash (rev — ziddiyat 409) ---------- */
function kuDirty() {
  if (KU.course && KU.course.caps && !KU.course.caps.write) { kuState("saved"); return; }   /* faqat ko'rish (kafedra): server baribir rad etadi */
  KU.dirty = true; if (KU.state !== "conflict") kuState("dirty");
  clearTimeout(KU.saveT); if (!KU.conflict) KU.saveT = setTimeout(() => kuSave(), 1200);
}
const kuSleep = ms => new Promise(r => setTimeout(r, ms));
async function kuSave(force = false) {
  clearTimeout(KU.saveT);
  if (!KU.lid || (!KU.dirty && !force)) return true;
  if (KU.saving) { KU.again = true; return false; }
  KU.saving = true; KU.dirty = false; kuState("saving");
  const lid = KU.lid, sent = KU.blocks.length;
  const body = {rev: KU.rev, title: KU.title, blocks: KU.blocks.map(b => ({id: b.id, type: b.type, data: b.data}))};
  if (KU.quiz) body.quiz = KU.quiz;
  if (force) body.force = true;
  let r;
  try { r = await kuFetch(`/api/kurs/lessons/${lid}`, body); } catch (e) { r = {ok: false, status: 0, data: {}}; }
  KU.saving = false;
  if (lid !== KU.lid) return r.ok;
  if (r.ok) {
    const L = r.data; KU.rev = L.rev; KU.lesson = {...KU.lesson, ...L, blocks: undefined};
    L.blocks.forEach((sb, i) => { const lb = KU.blocks[i]; if (lb && lb.id === sb.id) { lb.issues = sb.issues; const w = document.querySelector(`#kb-${sb.id} .ku-iss-w`); if (w) w.innerHTML = kuIssues(sb.issues); } });
    const li = KU.course.lessons_list.find(l => l.id === lid); if (li) { li.blocks = sent; li.title = L.title; }
    KU.course.rev = L.course_rev;
    if (KU.course.status !== L.status) { KU.course.status = L.status; KU.course.status_label = KU.meta.status[L.status]; KU.course.caps.submit = L.status === "qoralama"; kuStatusChip(); kuTop(); kuNote(); }
    const sm = document.querySelector(`#kuLs li[data-lid="${lid}"] small`); if (sm) sm.textContent = KU.lesson.type === "quiz" ? `Test · ${sent} savol` : `${sent} blok`;
    if (KU.sel < 0) kuRenderPanel();
    kuState(KU.dirty ? "dirty" : "saved");
    if (KU.pv) kuPvReload();
    if (KU.again || KU.dirty) { KU.again = false; if (KU.dirty) return kuSave(); }
    return true;
  }
  KU.dirty = true;
  if (r.status === 409) { KU.conflict = r.data.detail || {message: "Ziddiyat"}; kuState("conflict"); kuNote(); return false; }
  kuState("error", r.status === 400 ? kuErr(r.data) : "");
  if (r.status === 400) { toast(kuErr(r.data)); return false; }
  KU.saveT = setTimeout(() => kuSave(), 5000);
  return false;
}
async function kuFlush() {
  for (let i = 0; i < 100 && KU.saving; i++) await kuSleep(100);
  if (KU.dirty && !KU.conflict && KU.lid) await kuSave();
}
window.addEventListener("beforeunload", e => { if ((KU.dirty || KU.saving) && KU.view === "course") { e.preventDefault(); e.returnValue = ""; } });

/* ---------- ko'rish (kompyuter / planshet / telefon) ---------- */
async function kuPreview() {
  await kuFlush();
  const DEV = [["desktop", "1280px", ico("monitor", 15), "Kompyuter", "1280"], ["tablet", "768px", kuI("tablet", 15), "Planshet", "768"], ["phone", "390px", kuI("phone2", 15), "Telefon", "390"]];
  const bg = kuModal("Ko'rish", `<div class="ku-pvbar"><div class="ku-seg sm" role="group" aria-label="Qurilma: ekran kengligi">
      ${DEV.map(([k, w, ic, t, px], i) => `<button type="button" class="${i ? "" : "on"}" data-dev="${k}" data-w="${w}" aria-pressed="${i ? "false" : "true"}">${ic} ${t} <small>${px}</small></button>`).join("")}</div>
      <span class="ku-note" style="margin:0">Joriy (saqlangan) holat · o'zgarishlar avtomatik yangilanadi · natija saqlanmaydi</span>
      <button type="button" class="btn sm ghost" id="kuPvR">${ico("refresh", 15)} Yangilash</button><a class="btn sm ghost" id="kuPvO" target="_blank" rel="noopener">Yangi oynada</a></div>
    <div class="ku-pvw" data-dev="desktop"><div class="ku-dev"><iframe id="kuPvF" title="Kursni ko'rish" sandbox="allow-scripts allow-popups allow-popups-to-escape-sandbox allow-forms" referrerpolicy="no-referrer"
      allow="fullscreen; encrypted-media; picture-in-picture" allowfullscreen style="width:1280px"></iframe></div></div>`, {wide: true, cls: "kupv", onClose: () => { KU.pv = null; }});
  KU.pv = {bg, url: null};
  bg.querySelectorAll("[data-w]").forEach(b => b.onclick = () => {
    bg.querySelectorAll("[data-w]").forEach(x => { x.classList.toggle("on", x === b); x.setAttribute("aria-pressed", String(x === b)); });
    bg.querySelector(".ku-pvw").dataset.dev = b.dataset.dev; bg.querySelector("#kuPvF").style.width = b.dataset.w;
  });
  bg.querySelector("#kuPvR").onclick = () => kuPvLoad();
  kuPvLoad();
}
async function kuPvLoad() {
  if (!KU.pv) return;
  if (!KU.pv.url) { const r = await kuApi(`/api/kurs/courses/${KU.cid}/preview-url`).catch(e => { toast(e.msg || "Ko'rish ochilmadi"); return null; }); if (!r || !KU.pv) return; KU.pv.url = r.url; }
  const les = KU.course.lessons_list.find(l => l.id === KU.lid), blk = KU.blocks[KU.sel];
  const u = KU.pv.url + (les ? `#lesson=${les.uid}${blk && KU.lesson.type !== "quiz" ? "&block=" + blk.id : ""}` : "");
  const f = KU.pv.bg.querySelector("#kuPvF"); f.src = "about:blank"; setTimeout(() => { f.src = u; }, 30);
  KU.pv.bg.querySelector("#kuPvO").href = u;
}
function kuPvReload() { clearTimeout(KU.pvT); KU.pvT = setTimeout(kuPvLoad, 600); }

/* ---------- kurs sozlamalari ---------- */
async function kuSettings() {
  await kuFlush();
  const co = KU.course, M = KU.meta, S = co.settings, Lb = co.labels;
  const desc = (co.description || "").replace(/<\/p>\s*<p>/g, "\n\n").replace(/<br>/g, "\n").replace(/<[^>]+>/g, "").replace(/&amp;/g, "&").replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/&quot;/g, '"').replace(/&#x27;|&#39;/g, "'");
  let cover = co.cover_asset;
  const bg = kuModal("Kurs sozlamalari", `<div class="ku-2col"><div>
      <label class="ku-f"><span>Kurs nomi</span><input class="ku-in" id="kuSt_t" maxlength="200" value="${esc(co.title)}"></label>
      <label class="ku-f"><span>Tavsif (muqovada)</span><textarea class="ku-in" id="kuSt_d" rows="4" maxlength="3000">${esc(desc)}</textarea></label>
      <div class="ku-f"><span>Muqova rasmi</span><div id="kuStCv"></div></div>
      <label class="ku-f"><span>Muqova uchun muqobil matn (alt)</span><input class="ku-in" id="kuSt_ca" maxlength="300" value="${esc(co.cover_alt || "")}"></label>
      <div class="ku-f"><span>Urg'u rangi</span><div class="ku-pal" role="radiogroup" aria-label="Urg'u rangi">${Object.entries(M.palette).map(([h, n]) => `<label title="${esc(n)}"><input type="radio" name="kuAcc" value="${h}" ${co.accent === h ? "checked" : ""}><span style="background:${h}"></span><small>${esc(n)}</small></label>`).join("")}</div></div>
      <label class="ku-f"><span>Masofaviy kurs</span><select class="ku-in" id="kuSt_dl"><option value="">— bog'lanmagan —</option>${(M.dl_courses || []).map(d => `<option value="${d.id}" ${co.dl_course_id === d.id ? "selected" : ""}>${esc(d.subject)}${d.direction ? " · " + esc(d.direction) : ""}</option>`).join("")}</select></label>
    </div><div>
      <h4>Dizayn (talaba ko'radigan dars sahifasi)</h4>
      <div class="ku-dz" role="radiogroup" aria-label="Pleyer dizayni">${[["", co.dars?.linked ? "Fan / dars sozlamasidan" : "Standart", `hozir: ${(M.designs || {})[co.design] || co.design}`], ...Object.entries(M.designs || {}).map(([k, t]) => [k, t, k === "yangi" ? "Bosh sahifada bo'limlar kartochkalari, ichida 1 → N qadamlar" : "NEXTID'dagi Rise darslari kabi: muqova va bitta sahifa"])]
        .map(([k, t, h]) => `<label class="ku-dz-o"><input type="radio" name="kuDz" value="${k}" ${(S.design || "") === k ? "checked" : ""}><span><b>${esc(t)}</b><small>${esc(h)}</small></span></label>`).join("")}</div>
      <h4>Navigatsiya</h4>
      <label class="ku-chk"><input type="checkbox" id="kuSt_sb" ${S.sidebar ? "checked" : ""}> Yon menyu (darslar ro'yxati)</label>
      <label class="ku-chk"><input type="checkbox" id="kuSt_lc" ${S.lesson_count ? "checked" : ""}> Dars raqami va soni («3 / 12»)</label>
      <label class="ku-chk"><input type="checkbox" id="kuSt_sq" ${S.sequential ? "checked" : ""}> Ketma-ket o'tish (oldingi dars tugamaguncha keyingisi yopiq)</label>
      <label class="ku-chk"><input type="checkbox" id="kuSt_sr" ${S.search ? "checked" : ""}> Kurs bo'yicha qidiruv</label>
      <label class="ku-chk"><input type="checkbox" id="kuSt_kh" ${S.kbd_hints ? "checked" : ""}> Interaktiv bloklarda klaviatura ko'rsatmasi (qulaylik)</label>
      <h4>Yakunlash (LMS'ga «completed»)</h4>
      <label class="ku-f"><span>Qoida</span><select class="ku-in" id="kuSt_cm">${Object.entries(M.completion).map(([k, t]) => `<option value="${k}" ${S.completion === k ? "selected" : ""}>${esc(t)}</option>`).join("")}</select></label>
      <label class="ku-f"><span>Ko'rilgan darslar ulushi, %</span><input class="ku-in" type="number" min="10" max="100" id="kuSt_vp" value="${S.view_pct}"></label>
      <label class="ku-f"><span>Standart eksport turi</span><select class="ku-in" id="kuSt_md">${Object.entries(KU_MODE).map(([k, t]) => `<option value="${k}" ${S.mode === k ? "selected" : ""}>${esc(t)}</option>`).join("")}</select></label>
      <details class="ku-det"><summary>Pleyer yorliqlari (o'zbekcha)</summary><div class="ku-lbls">${Object.entries(M.labels).map(([k, t]) => `<label class="ku-f"><span>${esc(t)}</span><input class="ku-in" data-lbl="${k}" maxlength="80" value="${esc(Lb[k] || "")}" placeholder="${esc(t)}"></label>`).join("")}</div></details>
    </div></div>`, {wide: true, okText: "Saqlash", onOk: async bg => {
      const g = id => bg.querySelector(id);
      const labels = {}; bg.querySelectorAll("[data-lbl]").forEach(i => { if (i.value.trim()) labels[i.dataset.lbl] = i.value.trim(); });
      const descHtml = g("#kuSt_d").value.trim().split(/\n{2,}/).map(p => `<p>${esc(p).replace(/\n/g, "<br>")}</p>`).join("");
      const r = await kuFetch(`/api/kurs/courses/${KU.cid}/settings`, {rev: co.rev, title: g("#kuSt_t").value, description: descHtml, cover_asset: cover, cover_alt: g("#kuSt_ca").value,
        accent: bg.querySelector("[name=kuAcc]:checked")?.value, dl_course_id: +g("#kuSt_dl").value || null, labels,
        settings: {sidebar: g("#kuSt_sb").checked, lesson_count: g("#kuSt_lc").checked, sequential: g("#kuSt_sq").checked, search: g("#kuSt_sr").checked, kbd_hints: g("#kuSt_kh").checked, design: bg.querySelector("[name=kuDz]:checked")?.value ?? "",
                   completion: g("#kuSt_cm").value, view_pct: +g("#kuSt_vp").value, mode: g("#kuSt_md").value}});
      if (r.status === 409) { toast("Sozlamalar boshqa joyda o'zgargan — oyna yangilandi, qayta kiriting"); KU.course = (await kuApi(`/api/kurs/courses/${KU.cid}`)); return true; }
      if (!r.ok) { toast(kuErr(r.data)); return false; }
      KU.course = r.data; $("#kuCt").textContent = r.data.title; $(".ku-top").style.setProperty("--acc", r.data.accent); kuStatusChip(); kuTop(); kuNote(); toast("Sozlamalar saqlandi"); if (KU.pv) kuPvReload();
      return true;
    }});
  if (co.caps.delete) {   /* muallif (qoralama) yoki bo'lim — kursni o'chirish (ikki bosqichli tasdiq) */
    bg.querySelector(".ku-modal-b").insertAdjacentHTML("beforeend", `<div class="ku-acts"><button type="button" class="btn sm ghost danger" id="kuDelC">${kuI("trash", 14)} Kursni o'chirish</button></div>`);
    bg.querySelector("#kuDelC").onclick = async e => { if (!arm(e.currentTarget, "O'chirilsinmi?")) return; const r = await kuApi(`/api/kurs/courses/${KU.cid}/delete`, {}); if (r) { bg._close(); KU.dirty = false; toast("Kurs o'chirildi"); kuList(); } };
  }
  const paintCover = () => {
    bg.querySelector("#kuStCv").innerHTML = cover ? `<div class="ku-cvw"><img src="${kuAsset(cover)}" alt=""><span class="ku-acts tight"><button type="button" class="btn sm ghost" data-cv="pick">Almashtirish</button><button type="button" class="btn sm ghost" data-cv="x">Olib tashlash</button></span></div>`
      : `<button type="button" class="btn sm ghost" data-cv="pick">${kuI("image", 14)} Rasm tanlash</button>`;
    bg.querySelectorAll("[data-cv]").forEach(b => b.onclick = async () => { if (b.dataset.cv === "x") cover = null; else { const id = await kuPickImage(); if (id) cover = id; } paintCover(); });
  };
  paintCover();
}

/* ---------- versiyalar ---------- */
async function kuVersions() {
  await kuFlush();
  const d = await kuApi(`/api/kurs/courses/${KU.cid}/versions`);
  const K = {auto: "Avtomatik", "qo'lda": "Qo'lda", tasdiq: "Tasdiqlangan", import: "Import"};
  const bg = kuModal("Versiyalar", `<div class="ku-row"><input class="ku-in" id="kuVn" maxlength="200" placeholder="Izoh (masalan: 3-dars tayyor)" aria-label="Versiya izohi"><button type="button" class="btn primary" id="kuVs">Hozirgi holatni saqlash</button></div>
    <p class="ku-note">Oxirgi ${d.keep} ta versiya va tasdiqlangan versiyalar saqlanadi. Tiklashdan oldin joriy holat ham versiya sifatida saqlanadi.</p>
    <div class="ku-vers">${d.items.map(v => `<div class="ku-ver"><div><b>v${v.no}</b> ${kuChip(K[v.kind] || v.kind, v.kind === "tasdiq" ? "ok" : "")}${v.approved ? kuChip("Tasdiqlangan versiya", "ok") : ""}
      <div class="muted">${kuD(v.ts)} · ${esc(v.user_name || "")} · ${v.lessons} dars, ${v.blocks} blok</div>${v.note ? `<div>${esc(v.note)}</div>` : ""}</div>
      <button type="button" class="btn sm ghost" data-rv="${v.id}">Tiklash</button></div>`).join("") || `<p class="ku-note">Versiya yo'q.</p>`}</div>`, {wide: true});
  bg.querySelector("#kuVs").onclick = async () => { const r = await kuApi(`/api/kurs/courses/${KU.cid}/versions`, {note: bg.querySelector("#kuVn").value}); if (r) { toast("Versiya saqlandi"); bg._close(); kuVersions(); } };
  bg.querySelectorAll("[data-rv]").forEach(b => b.onclick = async e => {
    if (!arm(e.currentTarget, "Tiklansinmi?")) return;
    const r = await kuApi(`/api/kurs/courses/${KU.cid}/versions/${b.dataset.rv}/restore`, {});
    if (r) { bg._close(); toast("Versiya tiklandi"); KU.dirty = false; kuOpen(KU.cid); }
  });
}

/* ---------- sifat hisoboti ---------- */
const KU_FIX = {shuffle: "Javoblarni aralashtirish", labels: "Yorliqlarni tarjima qilish", mr_single: "«Bitta javob»ga o'tkazish",
  headings: "Sarlavha darajalarini tuzatish", table_header: "Sarlavha qatorini yoqish", kbd_hints: "Ko'rsatmalarni yoqish", accent: "Standart rangga o'tkazish"};
function kuQualityHtml(q, compact = false) {
  const pos = st => st.total ? `<div class="ku-pos" role="img" aria-label="To'g'ri javob o'rinlari">${["A", "B", "C", "D", "E"].filter(k => st.positions[k] || k < "E").map(k => {
    const n = st.positions[k] || 0, p = Math.round(100 * n / st.total);
    return `<div><span>${k}</span><i><s style="width:${p}%"></s></i><b>${n}</b></div>`; }).join("")}</div>` : `<p class="ku-note">Savol yo'q</p>`;
  const lv = {bad: "bad", warn: "warn", ok: "ok"};
  return `<div class="ku-kpis sm">
      <div class="ku-kpi ${q.knowledge.flag_pos ? "bad" : ""}"><span>Bilimni tekshirish</span><b>${q.knowledge.total ? `${q.knowledge.top_n}/${q.knowledge.total}` : "—"}</b><small>${q.knowledge.total ? `to'g'ri javob «${q.knowledge.top_pos}» o'rnida` : "savol yo'q"}</small></div>
      <div class="ku-kpi ${q.knowledge.flag_long ? "warn" : ""}"><span>Eng uzun variant</span><b>${q.knowledge.total ? `${q.knowledge.longest}/${q.knowledge.total}` : "—"}</b><small>to'g'ri javob eng uzun</small></div>
      <div class="ku-kpi ${q.images.missing_alt ? "bad" : ""}"><span>Alt matnsiz rasmlar</span><b>${q.images.missing_alt}/${q.images.total}</b></div>
      <div class="ku-kpi ${q.english_count ? "bad" : ""}"><span>Inglizcha yorliqlar</span><b>${q.english_count}</b></div>
      <div class="ku-kpi ${q.coverage.uncovered.length && q.coverage.quiz_questions ? "warn" : ""}"><span>Test qamrovi</span><b>${q.coverage.quiz_questions ? q.coverage.covered : "—"}</b><small>${q.coverage.quiz_questions ? `${q.coverage.quiz_questions} savol · darslar` : "test yo'q"}</small></div>
      <div class="ku-kpi ${q.mr_single ? "warn" : ""}"><span>«Bir nechta javob» — 1 ta to'g'ri</span><b>${q.mr_single}</b></div>
      ${q.a11y ? `<div class="ku-kpi ${q.a11y.rules.some(r => r.level === "bad") ? "bad" : q.a11y.passed < q.a11y.total ? "warn" : ""}" data-a11y-kpi><span>Qulaylik (a11y)</span><b>${q.a11y.passed}/${q.a11y.total}</b><small>qoida bajarildi</small></div>` : ""}</div>
    <ul class="ku-qis">${q.issues.map(i => `<li class="${lv[i.level]}" ${i.key ? `data-a11y="${esc(i.key)}"` : ""}><div><b>${esc(i.title)}</b><span>${esc(i.detail)}</span></div>${i.fix ? `<button type="button" class="btn sm primary" data-fix="${i.fix}">${KU_FIX[i.fix] || "Tuzatish"}</button>` : ""}${i.action === "captions" && KU.meta.caps.approve ? `<button type="button" class="btn sm primary" data-capall>Subtitr yaratish (Whisper)</button>` : ""}</li>`).join("")}</ul>
    ${!compact && q.a11y ? `<h4>Qulaylik tekshiruvi (WCAG 2.1 AA asosida)</h4><table class="ku-t ku-a11y"><thead><tr><th scope="col">Qoida</th><th scope="col">Holat</th><th scope="col">Qanday tuzatiladi</th></tr></thead><tbody>${q.a11y.rules.map(r => `<tr data-rule="${esc(r.key)}"><td><b>${esc(r.title)}</b>${r.count ? `<details><summary>${r.count} ta joy</summary><ul class="ku-isslist">${r.where.slice(0, 30).map(w => `<li class="warn">${esc(w)}</li>`).join("")}</ul></details>` : ""}</td><td>${r.level === "ok" ? kuChip("bajarildi", "ok") : kuChip(r.level === "bad" ? "muammo" : "tavsiya", r.level === "bad" ? "bad" : "warn")}</td><td class="sm">${esc(r.hint)}${r.key === "contrast" ? ` <span class="muted">(eng past: ${r.contrast.min}:1)</span>` : ""}</td></tr>`).join("")}</tbody></table>` : ""}
    ${compact ? "" : `<div class="ku-2col"><div><h4>To'g'ri javob o'rni — bilimni tekshirish</h4>${pos(q.knowledge)}</div><div><h4>To'g'ri javob o'rni — yakuniy test</h4>${pos(q.quiz)}</div></div>
      ${q.coverage.quiz_questions ? `<h4>Test savollari darslar bo'yicha (taxminiy — matn o'xshashligi)</h4><table class="ku-t"><tbody>${q.coverage.lessons.map(l => `<tr class="${l.questions ? "" : "muted"}"><td>${l.no}. ${esc(l.title)}</td><td class="n">${l.questions || "—"}</td></tr>`).join("")}</tbody></table>` : ""}
      ${q.english.length ? `<h4>Inglizcha matnlar</h4><ul class="ku-isslist">${q.english.slice(0, 40).map(x => `<li class="warn"><b>${esc(x.where)}:</b> ${esc(x.text)}</li>`).join("")}</ul>` : ""}
      ${q.images.where.length ? `<h4>Alt matnsiz rasmlar</h4><ul class="ku-isslist">${q.images.where.slice(0, 40).map(x => `<li class="warn">${esc(x)}</li>`).join("")}</ul>` : ""}`}`;
}
function kuQualityMount(box, cid, q, compact = true) {
  box.innerHTML = kuQualityHtml(q, compact);
  box.querySelectorAll("[data-fix]").forEach(b => b.onclick = async () => {
    b.disabled = true;
    if (KU.cid === cid) await kuFlush();
    const r = await kuApi(`/api/kurs/courses/${cid}/fix`, {fix: b.dataset.fix});
    if (!r) { b.disabled = false; return; }
    toast(`Tuzatildi: ${r.changed} ta o'zgarish (oldingi holat «Versiyalar»da)`);
    kuQualityMount(box, cid, r.quality, compact);
    if (KU.cid === cid && KU.view === "course") { KU.course = r.course; KU.dirty = false; if (KU.lid) kuLoadLesson(KU.lid, true); }
  });
  box.querySelectorAll("[data-capall]").forEach(b => b.onclick = async () => {   /* subtitrsiz barcha videolar — Whisper navbatiga */
    const items = (q.a11y?.rules.find(r => r.key === "captions")?.items || []), seen = new Set();
    b.disabled = true; let n = 0, worker = true;
    for (const it of items) {
      if (!it.asset || seen.has(it.asset)) continue; seen.add(it.asset);
      const r = await kuApi(`/api/kurs/courses/${cid}/captions`, {asset: it.asset, lang: "uz"});
      if (r) { n++; worker = r.worker; }
    }
    toast(`${n} ta video subtitr navbatiga qo'yildi${worker ? "" : " — montaj ishchisi o'chiq: qo'lda yo'l docs/kurs.md da"}`);
    if (KU.cid === cid) kuCapLoad();
  });
}
async function kuQuality() {
  await kuFlush();
  const q = await kuApi(`/api/kurs/courses/${KU.cid}/quality`);
  const bg = kuModal("Sifat hisoboti", `<div id="kuQb"></div>`, {wide: true});
  kuQualityMount(bg.querySelector("#kuQb"), KU.cid, q, false);
}

/* ---------- eksport ---------- */
/* «Tayyor» (Rise ko'rinishidagi yagona asosiy tugma): qadamlar ketma-ket raqamlanadi — tekshiruv → NEXTID uchun eksport → ko'rib chiqishga yuborish /
   tasdiqlash (rolga qarab bittasi yoki ikkalasi) */
async function kuPublish() {
  await kuFlush();
  const iss = KU.blocks.flatMap(b => b.issues || []), bad = iss.filter(x => x.level === "xato").length, warn = iss.length - bad;
  const co = KU.course, c = co.caps;
  let n = 0;
  const step = (cls, title, sub, btn) => `<li class="${cls}"><b>${++n}. ${title}</b><span>${sub}</span>${btn}</li>`;
  const bg = kuModal("Tayyor — keyingi qadamlar", `<ol class="kx-pub">
      ${step(bad ? "bad" : "ok", "Tekshiruv", `${bad ? `${bad} ta blokda xato — avval tuzating (blokdagi qizil belgi)` : "Bloklarda xato yo'q"}${warn ? ` · ${warn} ta ogohlantirish` : ""}`,
        `<button type="button" class="btn sm ghost" data-p="ql">Sifat hisoboti</button>`)}
      ${step("", "NEXTID uchun fayl", "xAPI .zip → my.isft.uz → fan → «Articulate» → yangi dars", `<button type="button" class="btn sm primary" data-p="ex">${kuI("download", 15)} Eksport</button>`)}
      ${c.submit ? step("", "Ko'rib chiqishga yuborish", "Bo'lim tekshirib tasdiqlaydi", `<button type="button" class="btn sm" data-p="sub">Yuborish</button>`) : ""}
      ${c.approve && co.status !== "tasdiqlangan" ? step("", "Tasdiqlash", "Tasdiqlangan versiya «Versiyalar»da saqlanadi", `<button type="button" class="btn sm" data-p="app">Tasdiqlash</button>`) : ""}</ol>`);
  bg.querySelectorAll("[data-p]").forEach(b => b.onclick = () => { const p = b.dataset.p; bg._close();
    if (p === "ql") kuQuality(); else if (p === "ex") kuExport(); else if (p === "sub") KU.act?.("submit"); else if (p === "app") KU.act?.("approve"); });
}
async function kuExport() {
  await kuFlush();
  const co = KU.course, iss = await kuApi(`/api/kurs/courses/${KU.cid}/issues`);
  const bg = kuModal("Eksport", `${iss.errors.length ? `<div class="ku-warn bad">${ico("alert", 15)}<div><b>Eksportdan oldin ${iss.errors.length} ta xatoni tuzating:</b><ul>${iss.errors.slice(0, 12).map(x => `<li>${esc(x)}</li>`).join("")}</ul></div></div>` : ""}
    <p class="ku-note">Format: <b>NEXTID uchun — xAPI</b> (my.isft.uz → «Articulate»).</p>
    ${iss.warnings.length ? `<details class="ku-det"><summary>${iss.warnings.length} ta ogohlantirish (eksportga to'sqinlik qilmaydi)</summary><ul class="ku-isslist">${iss.warnings.slice(0, 50).map(x => `<li class="warn">${esc(x)}</li>`).join("")}</ul></details>` : ""}
    <div id="kuExR" style="min-height:76px"></div>   <!-- natija chiqqanda modal sakramasin: tugma o'rnida qoladi -->
    ${co.exports.length ? `<h4>Oxirgi eksportlar</h4><div class="ku-vers">${co.exports.map(e => `<div class="ku-ver"><div><b>${esc(KU_MODE[e.mode] || e.mode)}</b> ${e.validation.ok ? kuChip("tekshiruvdan o'tdi", "ok") : kuChip("xato", "bad")}<div class="muted">${kuD(e.ts)} · ${esc(e.user_name || "")} · ${kuSize(e.size)}</div></div>
      <a class="btn sm ghost" href="/api/kurs/exports/${e.id}/download">${kuI("download", 14)} Yuklab olish</a></div>`).join("")}</div>` : ""}
    <ol class="ku-steps"><li>NEXTID (my.isft.uz) → fan → <b>«Articulate»</b> yorlig'i → yangi dars → yuklab olingan .zip faylni tanlang.</li><li>Faylni ochmang va ichini o'zgartirmang.</li></ol>`,
    {wide: true, okText: "Eksport qilish", onOk: async bg => {
      const mode = "xapi";
      const out = bg.querySelector("#kuExR"); out.innerHTML = `<p class="ku-note">Paket yig'ilmoqda…</p>`;
      const r = await kuApi(`/api/kurs/courses/${KU.cid}/export`, {mode});
      if (!r) { out.innerHTML = ""; return false; }
      out.innerHTML = `<div class="ku-warn ${r.validation.ok ? "ok" : "bad"}">${ico(r.validation.ok ? "check" : "alert", 15)}<div><b>${r.validation.ok ? "Paket tayyor va tekshiruvdan o'tdi" : "Paket tekshiruvdan o'tmadi"}</b>
        <div class="muted">${esc(r.filename)} · ${kuSize(r.size)} · ${r.validation.files} ta fayl</div>${r.validation.errors.length ? `<ul>${r.validation.errors.slice(0, 8).map(x => `<li>${esc(x)}</li>`).join("")}</ul>` : ""}</div>
        </div>`;
      KU.course = await kuApi(`/api/kurs/courses/${KU.cid}`);
      const okB = bg.querySelector("[data-ok]");
      if (okB && r.validation.ok) {   // «Eksport qilish» tugmasi o'sha joyning o'zida «Yuklab olish» ga aylanadi
        const dl = document.createElement("a"); dl.className = "btn primary"; dl.id = "kuDl"; dl.href = r.download; dl.setAttribute("download", r.filename || "");
        dl.innerHTML = `${kuI("download", 15)} Yuklab olish (.zip)`;
        okB.replaceWith(dl); const cb = bg.querySelector(".ku-acts [data-x]"); if (cb) cb.textContent = "Yopish"; dl.focus();
      }
      return false;
    }});
  if (iss.errors.length) bg.querySelector("[data-ok]").disabled = true;
}

/* ---------- navigatsiya: go("kurs") (app.js go() xaritasiga tegmasdan); boshqa bo'limga o'tishda — saqlash ---------- */
(function () {
  if (typeof go !== "function" || go._ku) return;
  const prev = go;
  go = function (v, opts) {
    if (v !== "kurs" && KU.dirty) kuSave();
    prev(v, opts);
    if (v !== "kurs") { $("#kuPanel")?.classList.remove("open"); return; }
    if (opts && typeof opts === "object" && opts.cid) {
      const who = typeof ME !== "undefined" ? ME : null; if (KU.who !== who) { kuReset(); KU.who = who; }   /* birinchi kirish — havola holati tozalanib ketmasin */
      KU.view = "course"; KU.cid = +opts.cid; KU.lid = +opts.lid || 0; KU.focus = opts.block || null; KU.wiz = opts.wiz || null;   /* wiz — Konstruktor (A versiya) qadamlari */   /* ortda.js savollar tahlili: dars + blok */
    }
    Promise.resolve().then(() => renderKurs()).catch(e => { if (e?.message === "auth") return; $("#v-kurs").innerHTML = e?.message === "denied" ? locked("Bu bo'lim") : errCard("kurs"); });
  };
  go._ku = true;
})();
(function () {
  if (typeof showLogin !== "function" || showLogin._ku) return;
  const prev = showLogin;
  showLogin = function (...a) { kuReset(); return prev.apply(this, a); };
  showLogin._ku = true;
})();
/* boy matn (rich) maydoni uchun kichik formatlash paneli: qalin, kursiv, tagiga chizilgan, havola, ro'yxat, tozalash */
function kuRtShow(el) {
  let t = document.getElementById("kuRt");
  if (!t) {
    t = document.createElement("div"); t.id = "kuRt"; t.className = "ku-rt"; t.setAttribute("role", "toolbar"); t.setAttribute("aria-label", "Matn formati");
    t.innerHTML = [["bold", "bold", "Qalin (Ctrl+B)"], ["italic", "italic", "Kursiv (Ctrl+I)"], ["underline", "underline", "Tagiga chizilgan"], ["link", "link", "Havola"], ["ul", "insertUnorderedList", "Ro'yxat"], ["eraser", "removeFormat", "Formatni tozalash"]]
      .map(([i, c, l]) => `<button type="button" data-c="${c}" title="${l}" aria-label="${l}">${kuI(i, 15)}</button>`).join("");
    t.addEventListener("mousedown", e => e.preventDefault());
    t.addEventListener("click", e => {
      const b = e.target.closest("[data-c]"); if (!b) return;
      if (b.dataset.c === "link") { const u = prompt("Havola (https://…)", "https://"); if (u && /^https?:\/\/\S+$/i.test(u.trim())) document.execCommand("createLink", false, u.trim()); else if (u) toast("Faqat http(s) havolalar"); }
      else if (b.dataset.c === "removeFormat") { document.execCommand("removeFormat"); document.execCommand("unlink"); }
      else document.execCommand(b.dataset.c);
      const ed = t._el; if (ed) ed.dispatchEvent(new Event("input", {bubbles: true}));
    });
    document.body.appendChild(t);
  }
  t._el = el; t.hidden = false;
  const r = el.getBoundingClientRect();
  t.style.top = `${window.scrollY + r.top - 40}px`; t.style.left = `${window.scrollX + Math.max(8, r.left)}px`;
}
function kuRtHide() { const t = document.getElementById("kuRt"); if (t) t.hidden = true; }

/* ---------- izohlar (ko'rib chiqish): blokka biriktirilgan, tarmoqli; to'xtatuvchi izoh tasdiqni to'xtatadi — app/dars.py ---------- */
async function kuCmLoad() {
  const cid = KU.cid;
  const r = await kuFetch(`/api/dars/kurs/${cid}/comments`).catch(() => null);
  if (!r || !r.ok || cid !== KU.cid) return;
  KU.cm = r.data; kuCmBadges(); kuCmCount(); if (KU.cmOpen) kuCmRender();
}
function kuCmBadge(b) {
  const T = (KU.cm?.items || []).filter(t => t.block_uid === b.id && t.status === "ochiq"), n = T.length, bad = T.some(t => t.blocking);
  return `<button type="button" class="ku-cmb ${n ? "on" : ""} ${bad ? "bad" : ""}" data-act="cm" aria-label="Blok izohlari: ${n} ta ochiq${bad ? ", to'xtatuvchi bor" : ""}" title="Izohlar">${ico("chat", 14)}${n ? `<b>${n}</b>` : ""}</button>`;
}
function kuCmBadges() { document.querySelectorAll("#kuBlocks .ku-blk").forEach(el => { const b = KU.blocks[+el.dataset.bi], w = el.querySelector(".ku-cmb"); if (b && w) w.outerHTML = kuCmBadge(b); }); }
function kuCmCount() {
  const el = $("#kuCmBtn"); if (!el) return;
  const c = KU.cm, n = c && c.open, rise = el.classList.contains("ku-tb");
  el.innerHTML = rise ? `${ico("chat", 17)}<span class="lb">Izohlar</span>${n ? `<b class="ku-cmn ${c.blocking ? "bad" : ""}">${n}</b>` : ""}` : `${ico("chat", 15)} Izohlar${n ? ` <b class="ku-cmn ${c.blocking ? "bad" : ""}">${n}</b>` : ""}`;
  el.setAttribute("aria-label", `Izohlar${n ? ` (${n} ta ochiq)` : ""}`);
  el.setAttribute("aria-expanded", KU.cmOpen ? "true" : "false");
}
function kuCmClose() { KU.cmOpen = false; KU.cmBlock = null; const p = $("#kuCm"); if (p) p.hidden = true; kuCmCount(); }
async function kuCmOpen(uid) {
  KU.cmOpen = true; KU.cmBlock = uid || null;
  if (uid && KU.dirty) await kuFlush();          /* izoh saqlangan blokka biriktiriladi */
  if (!KU.cm) await kuCmLoad();
  const p = $("#kuCm"); if (p) p.hidden = false;
  kuCmRender(); kuCmCount();
  (p?.querySelector("#kuCmT") || p?.querySelector("button"))?.focus();
}
function kuCmWhere(t) {
  const i = KU.blocks.findIndex(b => b.id === t.block_uid);
  if (t.lesson_id === KU.lid && i >= 0) return `<button type="button" class="ku-cm-go" data-cmgo="${esc(t.block_uid)}">${i + 1}-blok · ${esc(KU.meta.blocks[KU.blocks[i].type]?.label || KU.blocks[i].type)}</button>`;
  const l = KU.course.lessons_list.find(x => x.id === t.lesson_id);
  return `<button type="button" class="ku-cm-go" data-cml="${t.lesson_id}" data-cmb="${esc(t.block_uid)}">${esc(l ? l.title : "Dars")}${t.block_uid ? " · blok" : ""}</button>`;
}
function kuCmRender() {
  const p = $("#kuCm"), c = KU.cm; if (!p) return;
  if (!c) { p.innerHTML = `<div class="ku-cm-h"><b>Izohlar</b><button type="button" class="ku-ib" data-cmx aria-label="Yopish">${ico("x", 16)}</button></div><p class="ku-note">Yuklanmoqda…</p>`; p.querySelector("[data-cmx]").onclick = kuCmClose; return; }
  const items = c.items.filter(t => (KU.cmAll || t.lesson_id === KU.lid) && (KU.cmDone || t.status === "ochiq"));
  const bi = KU.cmBlock ? KU.blocks.findIndex(b => b.id === KU.cmBlock) : -1;
  const form = c.can.comment ? `<div class="ku-cm-new"><label class="ku-f"><span>${bi >= 0 ? `${bi + 1}-blokka izoh (${esc(KU.meta.blocks[KU.blocks[bi].type]?.label || "")})` : "Darsga umumiy izoh"}</span>
      <textarea id="kuCmT" rows="3" maxlength="2000" placeholder="${bi >= 0 ? "Bu blok bo'yicha fikringiz…" : "Blokni tanlab izoh qoldirish uchun blok sarlavhasidagi belgini bosing"}"></textarea></label>
      <div class="ku-cm-o">${c.can.blocking ? `<label class="cb"><input type="checkbox" id="kuCmB"> To'xtatuvchi (tasdiqdan oldin hal qilinishi shart)</label>
        <label class="cb"><input type="checkbox" id="kuCmM" checked> Muallifni eslatish</label>` : ""}
        <button type="button" class="btn sm primary" id="kuCmS">Izoh qoldirish</button></div></div>` : "";
  const th = t => `<li class="ku-cm-t ${t.status !== "ochiq" ? "done" : ""} ${t.blocking ? "blk" : ""}" data-cid="${t.id}">
      <div class="ku-cm-m">${kuCmWhere(t)}${t.blocking ? kuChip("to'xtatuvchi", "bad") : ""}${t.status !== "ochiq" ? kuChip("hal qilingan", "ok") : ""}${t.mention_author ? kuChip("muallifga") : ""}</div>
      <p><b>${esc(t.user)}</b> <small class="muted">${kuD(t.ts)}</small><br>${esc(t.text)}</p>
      ${t.replies.map(r => `<p class="ku-cm-r"><b>${esc(r.user)}</b> <small class="muted">${kuD(r.ts)}</small><br>${esc(r.text)}</p>`).join("")}
      ${t.status !== "ochiq" && t.resolved_by ? `<small class="muted">Hal qildi: ${esc(t.resolved_by)}, ${kuD(t.resolved_at)}</small>` : ""}
      <div class="ku-cm-a">${c.can.comment ? `<input type="text" maxlength="2000" placeholder="Javob…" aria-label="Javob" data-rp="${t.id}"><button type="button" class="btn sm ghost" data-rps="${t.id}">Javob</button>` : ""}
        ${(!t.blocking || c.can.resolve_blocking) ? (t.status === "ochiq" ? `<button type="button" class="btn sm" data-res="${t.id}">Hal qilindi</button>` : `<button type="button" class="btn sm ghost" data-reo="${t.id}">Qayta ochish</button>`) : ""}</div></li>`;
  p.innerHTML = `<div class="ku-cm-h"><b>Izohlar</b><span class="muted">${c.open} ochiq${c.blocking ? ` · <span class="ku-bad">${c.blocking} to'xtatuvchi</span>` : ""}</span>
      <button type="button" class="ku-ib" data-cmx aria-label="Izohlar panelini yopish">${ico("x", 16)}</button></div>
    ${form}
    <div class="ku-cm-f"><label class="cb"><input type="checkbox" id="kuCmAll" ${KU.cmAll ? "checked" : ""}> Barcha darslar</label><label class="cb"><input type="checkbox" id="kuCmDone" ${KU.cmDone ? "checked" : ""}> Hal qilinganlar ham</label></div>
    <ul class="ku-cm-l">${items.map(th).join("") || `<li class="ku-note">Izoh yo'q</li>`}</ul>`;
  p.querySelector("[data-cmx]").onclick = kuCmClose;
  p.querySelector("#kuCmAll").onchange = e => { KU.cmAll = e.target.checked; kuCmRender(); };
  p.querySelector("#kuCmDone").onchange = e => { KU.cmDone = e.target.checked; kuCmRender(); };
  const post = async body => { const r = await kuFetch(`/api/dars/kurs/${KU.cid}/comments`, body); if (!r.ok) { toast(kuErr(r.data)); return false; } KU.cm = r.data; kuCmBadges(); kuCmCount(); kuCmRender(); return true; };
  p.querySelector("#kuCmS")?.addEventListener("click", async () => {
    const text = p.querySelector("#kuCmT").value.trim(); if (text.length < 2) { toast("Izoh matnini yozing"); return; }
    await kuFlush();
    if (await post({lesson_id: KU.lid, block_uid: bi >= 0 ? KU.cmBlock : "", text, blocking: !!p.querySelector("#kuCmB")?.checked, mention_author: !!p.querySelector("#kuCmM")?.checked})) toast("Izoh qoldirildi");
  });
  p.querySelectorAll("[data-rps]").forEach(b => b.onclick = async () => { const i = p.querySelector(`[data-rp="${b.dataset.rps}"]`), text = i.value.trim(); if (text.length < 2) return; await post({parent_id: +b.dataset.rps, text}); });
  p.querySelectorAll("[data-rp]").forEach(i => i.onkeydown = e => { if (e.key === "Enter") p.querySelector(`[data-rps="${i.dataset.rp}"]`).click(); });
  const st = async (id, act) => { const r = await kuFetch(`/api/dars/comments/${id}/${act}`, {}); if (!r.ok) { toast(kuErr(r.data)); return; } KU.cm = r.data; kuCmBadges(); kuCmCount(); kuCmRender(); };
  p.querySelectorAll("[data-res]").forEach(b => b.onclick = () => st(b.dataset.res, "resolve"));
  p.querySelectorAll("[data-reo]").forEach(b => b.onclick = () => st(b.dataset.reo, "reopen"));
  p.querySelectorAll("[data-cmgo]").forEach(b => b.onclick = () => { const i = KU.blocks.findIndex(x => x.id === b.dataset.cmgo); if (i >= 0) { kuSelect(i, true); KU.cmBlock = b.dataset.cmgo; kuCmRender(); } });
  p.querySelectorAll("[data-cml]").forEach(b => b.onclick = async () => { await kuLoadLesson(+b.dataset.cml); const i = KU.blocks.findIndex(x => x.id === b.dataset.cmb); if (i >= 0) kuSelect(i, true); KU.cmBlock = b.dataset.cmb || null; kuCmRender(); });
}
/* to'xtatuvchi izohlar to'sig'i: izohlarni ochish yoki sabab bilan aylanib o'tish (sabab audit jurnaliga yoziladi) */
function kuGate(det, retry) {
  kuModal("Ochiq to'xtatuvchi izohlar", `<p class="ku-lead">${esc(det.message || "")}</p>
    <label class="ku-f"><span>Aylanib o'tish sababi (kamida 10 belgi; audit jurnaliga yoziladi)</span><textarea id="kuGr" rows="3" maxlength="500"></textarea></label>
    <div class="ku-acts"><button type="button" class="btn sm ghost" id="kuGc">Izohlarni ko'rish</button></div>`,
    {okText: "Sabab bilan davom etish", onOk: async bg => { const v = bg.querySelector("#kuGr").value.trim(); if (v.length < 10) { toast("Sababni batafsilroq yozing (kamida 10 belgi)"); return false; } return retry(v); }});
  const bg = document.querySelector(".ku-modal-bg:last-child");
  bg.querySelector("#kuGc").onclick = () => { bg._close(); KU.cmAll = true; kuCmOpen(null); };
  return false;
}
/* ---------- AI: hujjatdan dars (Word / PDF → bloklar, kartochkalar, bilimni tekshirish, yakuniy test) ---------- */
async function kuAiLesson() {
  const [f] = await kuPickFile(".docx,.pdf,.txt");
  if (!f) return;
  await kuFlush();
  const r = await kuXhr(`/api/dars/kurs/${KU.cid}/ai-lesson?name=${encodeURIComponent(f.name)}`, f, `«${f.name}» — AI dars tuzmoqda (1–3 daqiqa)`);
  if (!r) return;
  const R = r.report, pos = Object.entries(R.positions || {}).map(([k, v]) => `${k}: ${v}`).join(" · ");
  KU.course = r.course; kuRenderSide(); await kuLoadLesson(r.lesson_id, true);
  kuModal("AI: hujjatdan dars — natija", `<p class="ku-lead">Yangi dars qo'shildi: ${r.blocks} blok${r.quiz_lesson_id ? `, yakuniy test — ${R.questions} savol` : ""}. Ko'rib chiqing va tahrirlang.</p>
    <div class="ku-kpis sm">${[["Bo'limlar", R.sections], ["Paragraflar", R.paragraphs], ["Savollar", R.questions + R.checks], ["Kartochkalar", R.flashcards],
      ["Tashlangan (manbasiz)", R.p_uncited + R.q_uncited], ["Kirill → lotin", R.cyrillic]].map(([l, n]) => `<div class="ku-kpi"><span>${l}</span><b>${n}</b></div>`).join("")}</div>
    <ul class="ku-ul"><li>To'g'ri javob o'rinlari: ${esc(pos || "—")}</li>
      <li>«To'g'ri javob eng uzun» belgisi: ${R.longest_flagged} ta${R.distractors_regenerated ? ` → chalg'ituvchilar qayta tuzildi (${R.distractors_regenerated})` : ""}; qolgani — ${R.longest_after}</li>
      <li>Har bir bo'lim kamida bitta savol bilan qamralgan${R.coverage_retry ? " (qo'shimcha savollar so'raldi)" : ""}</li>
      <li>Inglizcha qoldiqlar tashlandi: ${R.english} · AI so'rovlari: ${R.calls} · tokenlar: ${r.tokens.in} / ${r.tokens.out}</li></ul>
    ${r.flagged.length ? `<p class="ku-note">Javobi eng uzun bo'lib qolgan savollar (qo'lda tekshiring): ${r.flagged.slice(0, 5).map(esc).join("; ")}</p>` : ""}`, {wide: true});
}
