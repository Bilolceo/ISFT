/* =====================================================================
   «Dars kartochkasi» (app/lesson_card.py, /api/dars/card): har dars uchun BITTA oyna — unikal kod, kafedra, o'qituvchi, fan, dars, taqdimot (oxirgi versiya + tarix),
   montajlangan video (holati), ma'ruza matni, qo'shimcha fayllar, jurnal. «Dars yaratish» — shu ma'lumotlar bilan mavjud paket / Konstruktor oqimini to'ldirib ochadi;
   «Hammasini ZIP qilib yuklab olish» — <kod>/taqdimot_vN.pptx, video, matn, meta.json. Studiya operatori va o'qituvchi ko'radi (yaratish — faqat bo'lim).
   Global: lcOpen(cid, lkey). Chaqiriladi: dars.js (fan → dars qatori), studio.js (dars tafsiloti), extras.js openLink (xabar havolasi {card: {cid, lkey}}).
   app.js yordamchilari: $, esc, toast, ico, go, dmy; paket.js: pkModal.
   ===================================================================== */
if (!document.querySelector('link[href="dars_card.css"]')) document.head.insertAdjacentHTML("beforeend", '<link rel="stylesheet" href="dars_card.css">');

const LC_VIDEO_TONE = {dept: "ok", tasdiqlandi: "info", korib: "warn", montaj: "info", xom: "", syomka: "", bor: "ok", yoq: ""};
const lcSize = b => b >= 1073741824 ? `${(b / 1073741824).toFixed(2).replace(".", ",")} GB` : b >= 1048576 ? `${(b / 1048576).toFixed(1).replace(".", ",")} MB` : `${Math.max(1, Math.round((b || 0) / 1024))} KB`;
const lcDT = s => { s = String(s || ""); return s.length >= 16 ? `${s.slice(8, 10)}.${s.slice(5, 7)}.${s.slice(0, 4)} ${s.slice(11, 16)}` : (s ? `${s.slice(8, 10)}.${s.slice(5, 7)}.${s.slice(0, 4)}` : "—"); };
/* o'qiladigan sana: «Bugun 10:38», «Kecha 18:20», «12-noy 09:15», boshqa yil — to'liq (to'liq sana har doim title'da) */
const LC_MON = ["yan", "fev", "mar", "apr", "may", "iyn", "iyl", "avg", "sen", "okt", "noy", "dek"];
function lcWhen(ts) {
  ts = String(ts || ""); if (ts.length < 10) return "—";
  const day = ts.slice(0, 10), hm = ts.length >= 16 ? ts.slice(11, 16) : "", now = new Date(), iso = d => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
  const y = new Date(now); y.setDate(now.getDate() - 1);
  if (day === iso(now)) return `Bugun${hm ? " " + hm : ""}`;
  if (day === iso(y)) return `Kecha${hm ? " " + hm : ""}`;
  const mo = LC_MON[+day.slice(5, 7) - 1] || day.slice(5, 7);
  return day.slice(0, 4) === String(now.getFullYear()) ? `${+day.slice(8, 10)}-${mo}${hm ? " " + hm : ""}` : `${+day.slice(8, 10)}-${mo} ${day.slice(0, 4)}${hm ? " " + hm : ""}`;
}
const lcChip = (t, cls = "", title = "") => `<span class="lc-chip ${cls}"${title ? ` title="${esc(title)}"` : ""}>${esc(t)}</span>`;

async function lcApi(url, method, body) {
  let r;
  try { r = await fetch(url, {method: method || "GET", credentials: "same-origin", headers: body ? {"Content-Type": "application/octet-stream"} : {}, body}); }
  catch (err) { const e = new Error("net"); e.msg = "Tarmoq xatosi — internetni tekshiring"; throw e; }
  if (r.status === 401) { if (typeof showLogin === "function") showLogin(); throw new Error("auth"); }
  const d = await r.json().catch(() => ({}));
  if (!r.ok) { const det = d.detail; const e = new Error("api"); e.msg = d.message || (typeof det === "string" ? det : det?.message) || "Xatolik yuz berdi"; e.status = r.status; throw e; }
  return d;
}

/* ---- jurnal: bir hodisaga bitta qator; texnik qatorlar (fayl yuklandi / almashtirildi, studiya va paket jurnallarining takrori) «Batafsil» ostida ---- */
const lcSecs = ts => { const t = Date.parse(String(ts || "").replace(" ", "T")); return isNaN(t) ? 0 : t / 1000; };
const lcPrimary = a => /yuborildi|yaratish|belgilandi|yig'ildi|tasdiq|yaratildi/i.test(a || "");
const lcTech = a => /^(taqdimot yuklandi|taqdimot almashtirildi)$/i.test((a || "").trim());
function lcLogGroups(log, fullCode) {
  const rows = (log || []).map(h => ({...h, t: lcSecs(h.ts)})).sort((a, b) => b.t - a.t);
  const used = new Set(), groups = [];
  rows.forEach((h, i) => {
    if (used.has(i)) return;
    used.add(i);
    const g = {main: h, more: []};
    rows.forEach((x, j) => {
      if (used.has(j) || Math.abs(x.t - h.t) > 5 || x.user_name !== h.user_name) return;
      const dup = x.action === h.action && (x.note || "") === (h.note || "");                     /* aynan bir xil qator (ikki marta bosish) */
      const same = /taqdimot/i.test(h.action) && /taqdimot/i.test(x.action) && /yuborildi/.test(h.action) && /yuborildi/.test(x.action);   /* studiya + paket jurnali — bitta hodisa */
      if (lcPrimary(h.action) && (lcTech(x.action) || dup || same)) { used.add(j); g.more.push(x); }
    });
    groups.push(g);
  });
  const clean = (n) => { n = String(n || ""); const c = String(fullCode || ""); return c && n.startsWith(c + " · ") ? n.slice(c.length + 3) : n === c ? "" : n; };
  const act = a => { a = String(a || "").replace(/^dars kartochkasi:\s*/i, ""); return a.charAt(0).toUpperCase() + a.slice(1); };
  return groups.map(g => ({...g, text: act(g.main.action), note: clean(g.main.note), when: lcWhen(g.main.ts), full: lcDT(g.main.ts), who: String(g.main.user_name || "").split(": ").pop(), role: String(g.main.user_name || "").includes(": ") ? String(g.main.user_name).split(": ")[0] : "",
    more: g.more.map(x => ({text: act(x.action), note: clean(x.note), src: x.src}))}));
}

/* kartochka ichidagi tasdiq (window.confirm o'rniga): true / false */
function lcConfirm(title, msg, okText) {
  return new Promise(res => { let ans = false;
    pkModal(title, `<p style="margin:0 0 6px">${esc(msg)}</p>`, async () => { ans = true; return true; }, okText, false, () => res(ans)); });
}

function lcHtml(d, cid, lkey) {
  const R = d.ref, T = d.taqdimot, V = d.video, X = d.text, caps = d.caps, pres = T.latest;
  const unsent = V.state === "tasdiqlandi";                        /* montaj tasdiqlangan, lekin operator bo'limga yubormagan */
  const lg = lcLogGroups(d.log, R.full_code).slice(0, 40);
  return `<div class="lc">
    <div class="lc-head"><code class="lc-code" title="Darsning unikal kodi">${esc(R.full_code)}</code>
      <div class="lc-chips">${d.state ? lcChip(`Bosqich: ${d.state.label}`, d.state.over ? "bad" : d.state.stage === "nextid" ? "ok" : "info", "Darsning umumiy bosqichi") : ""}${lcChip(`Video: ${V.label}`, LC_VIDEO_TONE[V.state], "Video holati")}${d.linked ? lcChip("Konstruktorda", "ok", "Dars Konstruktorda yaratilgan") : ""}</div>
      ${unsent ? `<p class="lc-warn" role="note">${ico("alert", 14)} Operator hali bo'limga yubormagan</p>` : ""}</div>
    <dl class="lc-ref"><div><dt>Kafedra</dt><dd>${esc(R.dept || "—")}</dd></div><div><dt>O'qituvchi</dt><dd>${esc(R.teacher || "—")}</dd></div><div><dt>Fan</dt><dd>${esc(R.subject)}</dd></div>
      <div><dt>Yo'nalish · kurs</dt><dd>${esc(R.direction || "—")} · ${R.course || "—"}-kurs</dd></div><div><dt>Dars</dt><dd>${esc(R.code)} — ${R.untitled ? "<i>mavzu nomi kiritilmagan</i>" : esc(R.title)}</dd></div></dl>
    <div class="lc-grid">
      <section class="lc-sec"><h4>Taqdimot</h4>
        ${pres ? `<p><b>v${pres.version}</b> · <time title="${esc(lcDT(pres.sent_at))}">${esc(lcWhen(pres.sent_at))}</time> · ${pres.slides || "?"} slayd · ${esc(pres.sent_by)}${pres.note ? `<br><span class="muted">«${esc(pres.note)}»</span>` : ""}</p>
          <div class="lc-acts"><a class="btn sm primary" href="${esc(pres.url_pptx)}">${ico("arrow", 13)} .pptx</a>${pres.url_pdf ? `<a class="btn sm" href="${esc(pres.url_pdf)}" target="_blank" rel="noopener">PDF</a>` : ""}</div>
          ${T.history.length > 1 ? `<details class="lc-more"><summary>Eski versiyalar (${T.history.length - 1})</summary><ul>${T.history.slice(1).map(h => `<li class="lc-v"><span><b>v${h.version}</b> · ${esc(lcWhen(h.sent_at))} · ${h.slides || "?"} slayd</span><span class="lc-lk"><a class="btn sm ghost" href="${esc(h.url_pptx)}">.pptx</a>${h.url_pdf ? `<a class="btn sm ghost" href="${esc(h.url_pdf)}" target="_blank" rel="noopener">PDF</a>` : ""}</span></li>`).join("")}</ul></details>` : ""}
          <p class="lc-st">${T.in_paket ? lcChip("Dars paketida bor", "ok") : lcChip("Paketda yo'q", "warn")}</p>`
          : `<p class="muted">O'qituvchi hali taqdimot yubormagan (Taqdimot → «Studiyaga va masofaviy bo'limga yuborish»).</p>${T.in_paket ? `<p class="lc-st">${lcChip("Paketda qo'lda yuklangan taqdimot bor", "ok")}</p>` : ""}`}
      </section>
      <section class="lc-sec"><h4>Video</h4>
        <p>${lcChip(V.label, LC_VIDEO_TONE[V.state])}${V.duration ? ` <span class="muted">${Math.floor(V.duration / 60)}:${String(Math.round(V.duration % 60)).padStart(2, "0")}</span>` : ""}</p>
        ${unsent ? `<p class="lc-warn" role="note">${ico("alert", 14)} Operator hali bo'limga yubormagan</p>` : ""}
        ${V.dept ? `<p class="tiny muted">Bo'limga yubordi: ${esc(V.dept.by)} · ${esc(lcWhen(V.dept.ts))}${V.dept.pres_version ? ` · taqdimot v${V.dept.pres_version}` : ""}</p>` : ""}
        ${V.has_file ? `<p class="tiny">${esc(V.name || "video")} · ${lcSize(V.size)}</p>` : ""}${V.youtube ? `<p class="tiny"><a href="${esc(V.youtube)}" target="_blank" rel="noopener">YouTube havolasi</a></p>` : ""}
        <div class="lc-acts">${V.media_url ? `<button type="button" class="btn sm" data-lc-play>${ico("video", 13)} Ko'rish</button>` : ""}${V.file_url ? `<a class="btn sm" href="${esc(V.file_url)}">${ico("arrow", 13)} Yuklab olish</a>` : ""}</div>
        <div class="lc-player" id="lcPlayer" hidden></div></section>
      <section class="lc-sec"><h4>Ma'ruza matni</h4>
        ${X.has ? `<p class="tiny"><b>${esc(X.name || "matn")}</b> · ${X.chars} belgi${X.by ? ` · ${esc(X.by)}` : ""}</p><p class="lc-pv" tabindex="0" role="region" aria-label="Ma'ruza matnining boshi (aylantiriladigan)">${esc(X.preview)}${X.chars > 500 ? "…" : ""}</p>
          <div class="lc-acts"><a class="btn sm" href="${esc(X.url)}">${ico("arrow", 13)} Yuklab olish</a></div>` : `<p class="muted">Matn yuklanmagan.</p>`}</section>
      <section class="lc-sec"><h4>Qo'shimcha fayllar</h4>
        ${d.files.length ? `<ul class="lc-files">${d.files.map(f => `<li>${esc(f.name)} <span class="muted">${lcSize(f.size)}</span></li>`).join("")}</ul>` : `<p class="muted">Yo'q.</p>`}
        ${caps.upload ? `<button type="button" class="btn sm lc-up" id="lcUpB">${ico("upload", 13)} Fayl qo'shish</button><input type="file" hidden id="lcUp" accept=".pdf,.docx,.pptx,.xlsx,.png,.jpg,.jpeg">` : ""}</section>
    </div>
    <section class="lc-sec lc-log"><h4>Jurnal</h4>${lg.length ? `<ul tabindex="0" role="region" aria-label="Jurnal yozuvlari (aylantiriladigan ro'yxat)">${lg.map(g => `<li><span class="tiny muted"><time title="${esc(g.full)}">${esc(g.when)}</time> · <span title="${esc(g.role)}">${esc(g.who)}</span></span><span>${esc(g.text)}${g.note ? ` — <span class="muted">${esc(g.note)}</span>` : ""}</span>
        ${g.more.length ? `<details class="lc-tech"><summary>Batafsil (${g.more.length})</summary><ul>${g.more.map(m => `<li><span class="tiny muted">${esc(m.src || "")}</span> ${esc(m.text)}${m.note ? ` — <span class="muted">${esc(m.note)}</span>` : ""}</li>`).join("")}</ul></details>` : ""}</li>`).join("")}</ul>` : `<p class="muted">Hali yozuv yo'q.</p>`}</section>
    <div class="lc-bar">
      <p class="lc-hint" id="lcHint">${caps.create ? "Taqdimot, video, matn Konstruktorga qo'yiladi; yo'qlari keyin to'ldiriladi." : "ZIP: taqdimot, video, matn va meta.json bitta arxivda."}</p>
      <div class="lc-bar-b">${caps.create ? `<button type="button" class="btn primary" id="lcCreate" aria-describedby="lcHint" title="Mavjud taqdimot, video va matn dars paketiga qo'yiladi va Konstruktor ochiladi">${ico("layers", 15)} ${d.linked ? "Konstruktorda ochish" : "Dars yaratish"}</button>` : ""}
      <a class="btn" id="lcZip" href="/api/dars/card/${cid}/${lkey}/zip">${ico("download", 15)} Hammasini ZIP qilib yuklab olish</a></div></div></div>`;
}

let LC_BUSY = "";
async function lcOpen(cid, lkey) {
  const key = `${cid}:${lkey}`;
  const ex = document.querySelector(`.lc-bg[data-lc="${key}"]`);
  if (ex) { ex.querySelector(".pk-modal")?.focus({preventScroll: true}); return; }       /* allaqachon ochiq — takroriy oyna ochilmaydi */
  if (LC_BUSY) return;                                                                   /* ikki marta bosish: bitta so'rov */
  LC_BUSY = key;
  const btn = document.activeElement && document.activeElement.tagName === "BUTTON" && !document.activeElement.disabled ? document.activeElement : null;
  if (btn) { btn.disabled = true; btn.setAttribute("aria-busy", "true"); }
  document.body.classList.add("lc-loading");                                             /* yuklanish holati: kursor + tugma */
  let d;
  try { d = await lcApi(`/api/dars/card/${cid}/${lkey}`); }
  catch (e) { if (e.message !== "auth") toast(e.msg || "Kartochkani ochib bo'lmadi"); d = null; }
  finally {
    LC_BUSY = ""; document.body.classList.remove("lc-loading");
    if (btn) { btn.disabled = false; btn.removeAttribute("aria-busy"); if (btn.isConnected) btn.focus({preventScroll: true}); }
  }
  if (!d) return;
  const R = d.ref;
  const bg = pkModal(`${R.code} · ${R.untitled ? R.subject : R.title}`, `<div data-lc-body>${lcHtml(d, cid, lkey)}</div>`, null, "", true);
  bg.classList.add("lc-bg"); bg.dataset.lc = key;
  lcBind(bg, d, cid, lkey);
}

function lcBind(bg, d, cid, lkey) {
  const V = d.video, T = d.taqdimot, X = d.text;
  bg.querySelector("[data-lc-play]")?.addEventListener("click", e => {
    const p = bg.querySelector("#lcPlayer"); p.hidden = false; e.currentTarget.hidden = true;
    p.innerHTML = `<video controls preload="metadata" playsinline src="${esc(V.media_url)}"></video>`;
  });
  const upB = bg.querySelector("#lcUpB"), up = bg.querySelector("#lcUp");
  upB?.addEventListener("click", () => up.click());
  up?.addEventListener("change", async e => {
    const f = e.target.files[0]; if (!f) return;
    upB.disabled = true; upB.setAttribute("aria-busy", "true");
    try {
      await lcApi(`/api/paket/courses/${cid}/topics/${lkey}/upload?as=fayl&name=${encodeURIComponent(f.name)}`, "POST", await f.arrayBuffer());
      toast(`«${f.name}» qo'shildi`);
      const d2 = await lcApi(`/api/dars/card/${cid}/${lkey}`), dlg = bg.querySelector(".pk-modal"), top = dlg.scrollTop;      /* joyida yangilanadi — oyna yopilib-ochilmaydi */
      bg.querySelector("[data-lc-body]").innerHTML = lcHtml(d2, cid, lkey); lcBind(bg, d2, cid, lkey);
      dlg.scrollTop = top; bg.querySelector("#lcUpB")?.focus({preventScroll: true});
    } catch (er) { if (er.message !== "auth") { toast(er.msg || "Yuklab bo'lmadi"); pkModalError(bg, er.msg || "Yuklab bo'lmadi"); } if (upB.isConnected) { upB.disabled = false; upB.removeAttribute("aria-busy"); } }
  });
  bg.querySelector("#lcCreate")?.addEventListener("click", async e => {
    const b = e.currentTarget; if (b.dataset.busy) return; b.dataset.busy = "1";          /* parallel bosish */
    const missing = [!(T.latest || T.in_paket) && "taqdimot", !(V.has_file || V.youtube || V.media_url) && "video", !X.has && "matn"].filter(Boolean);
    if (missing.length && !(await lcConfirm("Yetishmaydigan ma'lumotlar", `Yetishmaydi: ${missing.join(", ")}. Baribir ochaymi?`, "Baribir ochish"))) { delete b.dataset.busy; b.focus({preventScroll: true}); return; }
    b.disabled = true; b.setAttribute("aria-busy", "true"); const old = b.innerHTML; b.textContent = "Tayyorlanmoqda…";
    try {
      const r = await lcApi(`/api/dars/card/${cid}/${lkey}/create`, "POST");
      toast(`${r.code}: ${r.created ? "dars yaratildi" : "dars yangilandi"}${r.missing.length ? ` · yetishmaydi: ${r.missing.map(k => ({taqdimot: "taqdimot", video: "video", matn: "matn"}[k] || k)).join(", ")}` : ""}`);
      bg.remove();
      if (typeof KX === "object") KX.pending = {cid: r.open.cid, key: r.open.lkey};
      if (typeof DS === "object") { DS.cid = r.open.cid; DS.data = null; }
      if (typeof PK === "object") PK.tab = "fanlar";
      go("paket");
    } catch (er) { if (er.message !== "auth") { toast(er.msg || "Dars yaratib bo'lmadi"); pkModalError(bg, er.msg || "Dars yaratib bo'lmadi"); } b.disabled = false; b.removeAttribute("aria-busy"); delete b.dataset.busy; b.innerHTML = old; }
  });
}
