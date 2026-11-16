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
const DS = {cid: 0, q: "", offset: 0, data: null, meta: null, kind: "", kurs: 0, dir: ""};
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

/* ---------- Fanlar: kurs → ta'lim yo'nalishi → fan (ichma-ich); qidiruv — tekis ro'yxat ---------- */
/* Fan kodi (serverdan): «<kurs>_<YO'NALISH>_<fan>» — masalan 2_ATT_dasturiyinjiniring (unikal; dars kodi oxiriga _L2 qo'shiladi) */
const dsAgg = rows => { const n = rows.reduce((a, r) => ({lessons: a.lessons + r.lessons, built: a.built + r.built, approved: a.approved + r.approved, waiting: a.waiting + r.waiting,
    pres: a.pres + (r.pres_sent || 0), dept: a.dept + (r.dept_sent || 0), vwait: a.vwait + (r.video_wait || 0)}), {lessons: 0, built: 0, approved: 0, waiting: 0, pres: 0, dept: 0, vwait: 0});
  n.pct = n.lessons ? Math.round(100 * n.built / n.lessons) : 0; return n; };
/* taqdimot / video holati: «yangi: 1 taqdimot · 3 video» (backend: pres_sent, dept_sent, video_wait — yo'q bo'lsa ko'rinmaydi) */
const dsNewLine = (pres, dept, vwait) => {
  const parts = [pres ? `${pres} taqdimot` : "", dept ? `${dept} video` : ""].filter(Boolean);
  return parts.length || vwait ? `<span class="ds-new">${parts.length ? `<span class="ds-nw" title="Taqdimot yuborilgan darslar; video bo'limga yuborilgan darslar">yangi: ${parts.join(" · ")}</span>` : ""}${vwait ? `<span class="ds-nw wait" title="Montaj tasdiqlangan, lekin masofaviy bo'limga hali yuborilmagan">${vwait} video yuborilmagan</span>` : ""}</span>` : "";
};
const dsGroupStat = (n, unit) => `<span class="ds-sc-f">${pkBar(n.pct, pkTone(n.pct))}<small>${[unit, `${n.lessons} dars`, `tayyorlangan ${n.built}`, `tasdiqlangan ${n.approved}`, n.waiting ? `<b>kutmoqda ${n.waiting}</b>` : ""].filter(Boolean).join(" · ")}</small>${dsNewLine(n.pres, n.dept, n.vwait)}</span>`;
const dsSubjCard = r => `<button type="button" class="ds-sc" data-cid="${r.id}">
        <span class="ds-code-s">${esc(r.code || "")}</span><b>${esc(r.subject)}</b><small>${esc(r.direction)} · ${r.course}-kurs${r.teacher ? " · " + esc(r.teacher) : ""}</small>
        <span class="ds-sc-f">${pkBar(r.built_pct, pkTone(r.built_pct))}<small>${r.lessons} dars · tayyorlangan ${r.built} · tasdiqlangan ${r.approved}${r.waiting ? ` · <b>kutmoqda ${r.waiting}</b>` : ""}</small>${dsNewLine(r.pres_sent, r.dept_sent, r.video_wait)}</span></button>`;

/* Holatni tiklash: sahifa yangilanganda kurs/yo'nalish/fan — URL hash'da (#fanlar=kurs/yo'nalish/fan_id), history.pushState bilan (har daraja tarixga yoziladi — brauzer «Orqaga» tugmasi) */
function dsWho() {
  const w = typeof ME !== "undefined" ? ME : null;
  if (DS.who !== undefined && DS.who !== w) Object.assign(DS, {cid: 0, q: "", offset: 0, data: null, kind: "", kurs: 0, dir: "", single: null, restored: false, pendingCard: 0, pendingCode: ""});
  DS.who = w;
}
const dsHashStr = () => DS.cid ? `#fanlar=${DS.kurs || 0}/${encodeURIComponent(DS.dir || "")}/${DS.cid}` : DS.kurs ? `#fanlar=${DS.kurs}/${encodeURIComponent(DS.dir || "")}` : "";
function dsHashSave(replace) {
  try {
    const h = dsHashStr();
    if (location.hash === h || !(h || location.hash.startsWith("#fanlar="))) return;
    const u = location.pathname + location.search + h;
    if (replace) history.replaceState(history.state, "", u);
    else history.pushState({isftView: (history.state && history.state.isftView) || "paket"}, "", u);   /* «Orqaga» (brauzer) bir daraja qaytaradi — nav_history.js */
  } catch (e) {}
}
function dsHashLoad() {
  const m = /^#fanlar=(\d+)(?:\/([^/]*))?(?:\/(\d+))?$/.exec(location.hash || ""); if (!m) return;
  try { DS.kurs = +m[1] || 0; DS.dir = DS.kurs ? decodeURIComponent(m[2] || "") : ""; DS.cid = +m[3] || 0; DS.fromHash = !!DS.cid; } catch (e) { DS.kurs = 0; DS.dir = ""; DS.cid = 0; }
}
/* ekran o'qigichlar uchun: doimiy aria-live bloki (daraxt qayta chizilganda ham e'lon qilinadi) */
function dsAnnounce(t) {
  let el = document.getElementById("dsLive");
  if (!el) { el = document.createElement("div"); el.id = "dsLive"; el.className = "pk-sr"; el.setAttribute("role", "status"); el.setAttribute("aria-live", "polite"); document.body.appendChild(el); }
  el.textContent = ""; setTimeout(() => { el.textContent = t; }, 60);
}
/* qayta chizishdan keyin: yangi bosqich sarlavhasiga fokus (faqat foydalanuvchi harakatidan keyin) + e'lon */
function dsStage(box, o, status, always) {
  const h = box.querySelector("[data-stage]");
  if (o && o.focus && h) h.focus({preventScroll: true});
  if ((o && o.focus) || always) dsAnnounce(status);
}
const DS_SFX = /^(.+?)_((?:L|A|S|MT|LAB)\d+)$/i;      /* to'liq dars kodi: ..._L8 */
async function dsSubjects(box, o = {}) {
  dsWho();
  if (!DS.restored) { DS.restored = true; if (!DS.cid && !DS.kurs && !DS.q) dsHashLoad(); }
  try { return await dsSubjectsIn(box, o); }
  catch (e) {
    if (e?.message === "auth") return;
    if (e?.message === "denied") { box.innerHTML = locked("Bu bo'lim"); return; }
    pkFail(box, e, () => dsSubjects(box, o));
  }
}
async function dsSubjectsIn(box, o) {
  if (DS.cid) return dsSubject(box, o);
  dsHashSave();
  const head = (title, sub) => `<div class="ds-h"><div><h3 tabindex="-1" data-stage>${esc(title)}</h3><p class="muted" aria-live="polite">${sub}</p></div>
      <input type="search" id="dsQ" class="ds-q" placeholder="Fan nomi yoki kod (masalan 4_BHM_… yoki …_L8)" value="${esc(DS.q)}" aria-label="Fanni qidirish: fan nomi yoki kod" autocomplete="off"></div>`;
  const bindQ = () => { let t = 0;
    box.querySelector("#dsQ").oninput = e => { clearTimeout(t); t = setTimeout(() => { DS.q = e.target.value.trim(); DS.offset = 0; dsSubjects(box).then(() => { const q = box.querySelector("#dsQ"); q?.focus(); q?.setSelectionRange(q.value.length, q.value.length); }); }, 300); }; };
  const openSubj = () => box.querySelectorAll("[data-cid]").forEach(b => b.onclick = () => { DS.cid = +b.dataset.cid; dsSubject(box, {focus: true}); });
  if (DS.q) {   /* qidiruv — barcha fanlar bo'yicha tekis ro'yxat */
    const lim = 30, find = q => pkApi(`/api/paket/courses?limit=${lim}&offset=${DS.offset}&q=${encodeURIComponent(q)}`);
    let d = await find(DS.q), hint = d.lesson_hint ? +d.lesson_hint : 0, code = "";
    const sfx = DS_SFX.exec(DS.q);
    if (!d.items.length && sfx && !DS.offset) { const d2 = await find(sfx[1]); if (d2.items.length === 1) { d = d2; code = sfx[2].toUpperCase(); } }   /* server lesson_hint bermasa — kod oxiridagi _L8 ni o'zimiz ajratamiz */
    if (!DS.offset && d.items.length === 1 && (hint || code)) {      /* to'liq dars kodi — fan darhol ochiladi va shu dars kartochkasiga o'tadi */
      const r = d.items[0]; DS.q = ""; DS.cid = r.id; DS.kurs = r.course; DS.dir = r.direction; DS.pendingCard = hint; DS.pendingCode = code;
      return dsSubject(box, {focus: true});
    }
    const miss = `«${esc(DS.q)}» bo'yicha fan topilmadi. ${sfx ? `Kodning oxiridagi <b>_${esc(sfx[2])}</b> ni olib tashlab ko'ring.` : "Fan nomi yoki kodining bir qismini yozib ko'ring."}`;
    box.innerHTML = `<div class="card pk-card">${head("Fanlar", `«${esc(DS.q)}» bo'yicha natijalar. Qidiruvni tozalasangiz — kurs → yo'nalish → fan bo'yicha ko'rinishga qaytasiz.`)}
    <div class="ds-subj">${d.items.map(dsSubjCard).join("") || `<div class="pk-empty" role="status">${miss}</div>`}</div>
    ${d.total > lim ? `<div class="pk-pager"><button type="button" class="btn sm ghost" data-p="${Math.max(0, DS.offset - lim)}" ${DS.offset ? "" : "disabled"}>← Oldingi</button>
      <span>${fmt(DS.offset + 1)}–${fmt(Math.min(d.total, DS.offset + lim))} / ${fmt(d.total)}</span>
      <button type="button" class="btn sm ghost" data-p="${DS.offset + lim}" ${DS.offset + lim < d.total ? "" : "disabled"}>Keyingi →</button></div>` : ""}</div>`;
    bindQ(); openSubj();
    box.querySelectorAll("[data-p]").forEach(b => b.onclick = () => { DS.offset = +b.dataset.p; dsSubjects(box, {focus: true}); });
    dsStage(box, {}, d.items.length ? `${fmt(d.total)} ta natija` : `«${DS.q}» bo'yicha fan topilmadi`, true);
    return;
  }
  const dd = await pkApi(`/api/paket/courses?limit=1000`), all = dd.items;
  DS.single = all.length === 1;
  if (all.length === 1) { DS.cid = all[0].id; DS.kurs = all[0].course; DS.dir = all[0].direction; return dsSubject(box, o); }
  if (!all.length) {
    const teacher = PK.meta?.role === "oqituvchi";
    box.innerHTML = `<div class="card pk-card"><div class="ds-h"><div><h3 tabindex="-1" data-stage>Fanlar</h3></div></div>
      <div class="pk-empty" role="status">${teacher ? "Sizga fan biriktirilmagan. Kafedra mudiriga murojaat qiling." : "Fan topilmadi."}</div></div>`;
    dsStage(box, o, teacher ? "Sizga fan biriktirilmagan" : "Fan topilmadi"); return;
  }
  const {kurslar, inK, dirs} = lpLevels(all, DS);                            /* umumiy mantiq (lesson_picker.js): bitta kurs / yo'nalish — bosqich o'tkaziladi */
  dsHashSave();
  const crumbs = [`<button type="button" class="ds-cr" data-lv="0" ${DS.kurs ? "" : 'aria-current="page"'}>Barcha kurslar</button>`];
  if (DS.kurs) crumbs.push(`<button type="button" class="ds-cr" data-lv="1" ${DS.dir ? "" : 'aria-current="page"'}>${DS.kurs}-kurs</button>`);
  if (DS.dir) crumbs.push(`<span class="ds-cr" aria-current="page">${esc(DS.dir)} <small>${esc(inK.find(r => r.direction === DS.dir)?.dir_code || "")}</small></span>`);
  let body, sub, title, live;
  if (!DS.kurs) {
    title = "Fanlar"; sub = "1-qadam: kursni tanlang."; live = `Fanlar: ${kurslar.length} ta kurs. ${sub}`;
    body = `<div class="ds-subj ds-lv">${kurslar.map(k => { const rs = all.filter(r => r.course === k);
      return `<button type="button" class="ds-sc ds-big" data-kurs="${k}"><span class="ds-code-s">${k}</span><b>${k}-kurs</b>
        <small>${new Set(rs.map(r => r.direction)).size} ta yo'nalish · ${rs.length} ta fan</small>${dsGroupStat(dsAgg(rs), "")}</button>`; }).join("")}</div>`;
  } else if (!DS.dir) {
    title = `${DS.kurs}-kurs`; sub = `2-qadam: ${DS.kurs}-kurs — ta'lim yo'nalishini tanlang.`; live = `${DS.kurs}-kurs: ${dirs.length} ta ta'lim yo'nalishi. 2-qadam: yo'nalishni tanlang.`;
    body = `<div class="ds-subj ds-lv">${dirs.map(d => { const rs = inK.filter(r => r.direction === d);
      return `<button type="button" class="ds-sc ds-big" data-dir="${esc(d)}"><span class="ds-code-s">${DS.kurs}_${esc(rs[0].dir_code)}</span><b>${esc(d)}</b>
        <small>${rs.length} ta fan</small>${dsGroupStat(dsAgg(rs), "")}</button>`; }).join("")}</div>`;
  } else {
    const rs = inK.filter(r => r.direction === DS.dir).sort((a, b) => (a.subject || "").localeCompare(b.subject || "", "uz"));
    title = DS.dir; sub = `3-qadam: fanni tanlang — kod ko'rinishi: <b>kurs_YO'NALISH_fan</b>.`; live = `${DS.dir}: ${rs.length} ta fan. 3-qadam: fanni tanlang.`;
    body = `<div class="ds-subj">${rs.map(dsSubjCard).join("")}</div>`;
  }
  const warn = dd.total > all.length ? `<div class="pk-warnbox" role="status">${ico("alert", 15)}<span>Faqat birinchi ${fmt(all.length)} ta fan ko'rsatildi (jami ${fmt(dd.total)}). Qolganlarini yuqoridagi qidiruv orqali toping.</span></div>` : "";
  box.innerHTML = `<div class="card pk-card">${head(title, sub)}${warn}<nav class="ds-crumbs" aria-label="Fanlar bo'yicha yo'l">${crumbs.join('<span aria-hidden="true">›</span>')}</nav>${body}</div>`;
  bindQ(); openSubj();
  box.querySelectorAll("[data-lv]").forEach(b => b.onclick = () => { if (+b.dataset.lv === 0) { DS.kurs = 0; DS.dir = ""; } else DS.dir = ""; dsSubjects(box, {focus: true}); });
  box.querySelectorAll("[data-kurs]").forEach(b => b.onclick = () => { DS.kurs = +b.dataset.kurs; DS.dir = ""; dsSubjects(box, {focus: true}); });
  box.querySelectorAll("[data-dir]").forEach(b => b.onclick = () => { DS.dir = b.dataset.dir; dsSubjects(box, {focus: true}); });
  dsStage(box, o, live);
}

/* ---------- Fan: NEXTID darslar to'ri ---------- */
/* dars qatori: Material · Video · Paket — 3 ta kichik qadam (✓ — bor); nomi kiritilmagan dars — «Mavzu nomi kiritilmagan» (xira, qiya) */
const dsTitle = l => l.untitled ? `<b class="ds-un">Mavzu nomi kiritilmagan</b>` : `<b>${esc(l.title)}</b>`;
const dsFlags = l => `${l.pres_version ? pkChip(`Taqdimot v${l.pres_version}`, "info") : ""}${l.dept_sent ? pkChip("Video keldi", "ok") : l.video_wait ? pkChip("Video: bo'limga yuborilmagan", "warn") : ""}${l.review ? pkChip("Ko'rib chiqishda", "info") : ""}${l.approved ? pkChip("Tasdiqlangan", "ok") : ""}
      ${l.comments.open ? pkChip(`${l.comments.open} izoh${l.comments.blocking ? ` · ${l.comments.blocking} to'xtatuvchi` : ""}`, l.comments.blocking ? "bad" : "warn") : ""}`;
function dsProgress(l) {
  const pk = !!(l.package || l.export);
  const S = [["Material", "file", !!l.material, l.material ? "Material: yuklangan (Word yoki taqdimot)" : "Material: hali yuklanmagan"],
             ["Video", "video", !!l.video, l.video ? "Video: bor" : "Video: hali yo'q"],
             ["Paket", "package", pk, pk ? (l.authority === "kurs" && l.export ? "Paket: muharrirdan eksport qilingan" : "Paket: tayyor") : "Paket: hali yig'ilmagan"]];
  return `<span class="ds-prg" role="list" aria-label="Tayyorlik: ${S.map(x => x[3]).join("; ")}">${S.map(([t, ic, on, tip]) =>
    `<span class="ds-step ${on ? "on" : ""}" role="listitem" title="${esc(tip)}" aria-label="${esc(tip)}"><i>${ico(on ? "check" : ic, 12)}</i><span>${t}</span></span>`).join("")}</span>`;
}

async function dsSubject(box, o = {}) {
  dsWho();
  let d;
  try { d = await pkApi(`/api/dars/subjects/${DS.cid}`); }
  catch (e) {          /* tiklangan (hash) fan endi mavjud emas / ruxsat yo'q — ro'yxatga qaytamiz */
    if (DS.fromHash && (e?.message === "denied" || e?.status === 404 || e?.status === 403)) { DS.fromHash = false; DS.cid = 0; DS.kurs = 0; DS.dir = ""; dsHashSave(true); return dsSubjectsIn(box, o); }
    throw e;
  }
  DS.fromHash = false;
  const c = d.course, can = d.can;
  DS.data = d;
  if (DS.single == null) { try { DS.single = (await pkApi("/api/paket/courses?limit=1")).total === 1; } catch (e) { DS.single = false; } }   /* bitta fani bor o'qituvchi: «← Fanlar» yo'q */
  DS.kurs = c.course; DS.dir = c.direction; dsHashSave();
  const groups = Object.keys(DS_KIND).map(k => [k, d.lessons.filter(l => l.kind === k)]).filter(g => g[1].length);
  const st = l => `${dsYes(l.material, "Material")}${dsYes(l.video, "Video")}${dsYes(l.package || l.export, "Paket")}
      ${dsFlags(l)}`;
  const src = l => l.kurs ? `<label class="ds-src" title="Eksport (NEXTID uchun zip) qaysi manbadan olinadi">Eksport:
      <select data-auth="${l.key}" ${can.write ? "" : "disabled"} aria-label="${esc(l.code)} — eksport manbai"><option value="kurs" ${l.authority === "kurs" ? "selected" : ""}>Muharrir</option>
      <option value="paket" ${l.authority === "paket" ? "selected" : ""}>Shablon (paket)</option></select></label>` : `<span class="ds-src muted">Eksport: shablon (paket)</span>`;
  const A = typeof kxOpen === "function" && dsVer() === "a";   /* A — Konstruktor (bitta oqim), B — avtomatik yig'ish + muharrir */
  const cardBtn = l => typeof lcOpen === "function" && ["maruza", "amaliy"].includes(l.kind) ? `<button type="button" class="btn sm ghost" data-card="${l.key}" aria-label="${esc(l.code)} — kartochka" title="Dars kartochkasi: unikal kod, taqdimot versiyalari, video holati, matn, jurnal, ZIP">${ico("file", 15)} Kartochka</button>` : "";
  const rowA = l => `<li class="ds-l ${l.approved ? "ok" : l.review ? "rv" : ""}" data-key="${l.key}">
      <span class="ds-code">${esc(l.code)}</span>
      <span class="ds-t">${dsTitle(l)}<span class="ds-sts">${dsProgress(l)}${dsFlags(l)}</span></span>
      <span class="ds-a">${cardBtn(l)}${can.write ? `<button type="button" class="btn sm primary" data-kx="${l.key}" aria-label="${esc(l.code)} — Konstruktorda ochish" title="${l.kurs ? "Dars Konstruktorda yaratilgan — davom ettirish" : l.material || l.video ? "Yuklangan fayllar bilan Konstruktorda ochiladi (dars shu yerda yaratiladi)" : "Dars hali yaratilmagan — Konstruktorda ochilganda yaratiladi"}">${ico("layers", 15)} Konstruktorda ochish</button>`
        : l.kurs ? `<button type="button" class="btn sm" data-ku="${l.kurs.id}" aria-label="${esc(l.code)} — Konstruktorda ko'rish">${ico("layers", 15)} Ko'rish</button>` : ""}</span></li>`;
  const row = l => A ? rowA(l) : `<li class="ds-l ${l.approved ? "ok" : l.review ? "rv" : ""}" data-key="${l.key}">
      <span class="ds-code">${esc(l.code)}</span>
      <span class="ds-t">${dsTitle(l)}<span class="ds-sts">${st(l)}</span></span>
      <span class="ds-a">${src(l)}
        ${can.write ? `<button type="button" class="btn sm" data-build="${l.key}" aria-label="${esc(l.code)} — avtomatik yig'ish" ${PK.meta?.player === false ? "disabled" : ""} title="Yuklangan fayllardan kafedra shabloni bo'yicha paket">${ico("package", 15)} Avtomatik yig'ish (shablon)</button>` : ""}
        ${l.kurs ? `<button type="button" class="btn sm ${can.write ? "primary" : ""}" data-ku="${l.kurs.id}" aria-label="${esc(l.code)} — ${can.write ? "muharrirda tahrirlash" : "muharrirda ko'rish"}">${ico("layers", 15)} ${can.write ? "Muharrirda tahrirlash" : "Muharrirda ko'rish"}</button>`
          : can.write ? `<button type="button" class="btn sm primary" data-conv="${l.key}" aria-label="${esc(l.code)} — muharrirda tahrirlash" title="Avtomatik yig'ilgan dars bloklarga o'tkaziladi — keyin erkin tahrirlanadi">${ico("layers", 15)} Muharrirda tahrirlash</button>` : ""}
        ${cardBtn(l)}<button type="button" class="btn sm ghost" data-open="${l.key}" aria-label="${esc(l.code)} — fayllar" title="Fayllarni yuklash, ko'rish, tasdiqlash">Fayllar</button></span></li>`;
  box.innerHTML = `<div class="card pk-card ds-head"><div class="ds-h">
      <div>${DS.single ? "" : `<button type="button" class="btn sm ghost" id="dsBack">← Fanlar</button>`}
        <h3 tabindex="-1" data-stage>${esc(c.subject)}</h3>${DS.single ? `<p class="ds-path" aria-label="Fan yo'li">${esc(c.subject)} · ${c.course}-kurs · ${esc(c.direction)} (${esc(c.dir_code || "")})</p>` : ""}<p class="muted"><span class="ds-code-s" title="Fanning unikal kodi — dars kodi oxiriga _L2 kabi qo'shiladi">${esc(c.code || "")}</span> ${esc(c.direction)} · ${c.course}-kurs · ${esc(c.dept || "—")} · mas'ul: ${esc(c.teacher || "—")} ·
          shablon: <b>${esc(d.template.name)}</b> v${d.template.version}</p></div>
      <div class="ds-kpis">${[["Ma'ruza", d.counts.L], ["Amaliy", d.counts.A], ["Muharrirda", d.counts.linked], ["Ko'rib chiqishda", d.counts.review], ["Tasdiqlangan", d.counts.approved]]
        .map(([k, v]) => `<span><b>${v}</b>${esc(k)}</span>`).join("")}${d.counts.blocking ? `<span class="bad"><b>${d.counts.blocking}</b>to'xtatuvchi izoh</span>` : ""}</div></div>
    ${typeof kxOpen === "function" ? `<div class="ds-ver" role="group" aria-label="Ko'rinish versiyasi"><span>Ko'rinish:</span>
      <button type="button" class="${A ? "on" : ""}" data-ver="a" title="Bitta oqim: fayllar → Rise kabi muharrir → nashr">A — Konstruktor</button>
      <button type="button" class="${A ? "" : "on"}" data-ver="b" title="Avvalgidek: avtomatik yig'ish (shablon) va alohida muharrir">B — Yig'ish + muharrir</button></div>` : ""}
    ${can.write ? `<div class="pk-acts ds-tools"><button type="button" class="btn sm" id="dsSkel">${ico("plus", 15)} Fan skeleti (L + A)</button>
      ${typeof kxbOpen === "function" ? `<button type="button" class="btn sm" id="dsBulkUp" title="Ko'p faylni birdaniga yuklash: fayl nomidagi raqam bo'yicha darsga moslanadi">${ico("upload", 15)} Ko'p faylni yuklash</button>` : ""}
      <button type="button" class="btn sm" id="dsApply">Shablonni qo'llash</button>
      <button type="button" class="btn sm" id="dsBulk">${ico("download", 15)} Hammasini yig'ish va eksport</button>
      <button type="button" class="btn sm" id="dsAq" title="Muharrirdagi har dars oxiriga 3–5 savollik past xavfli test — Test bankdagi tasdiqlangan savollardan, fan bo'yicha takrorsiz">${ico("checkc", 15)} Har dars oxiriga test</button>
      ${can.template ? `<button type="button" class="btn sm ghost" id="dsTpl">Kafedra shablonini tahrirlash</button>` : ""}</div>` : ""}</div>
    ${groups.length ? groups.map(([k, ls]) => `<div class="card pk-card"><h3>${esc(DS_KIND[k])} <span class="muted">· ${ls.length} ta</span></h3><ol class="ds-grid ${A ? "a" : ""}">${ls.map(row).join("")}</ol></div>`).join("")
      : `<div class="card pk-card pk-empty">Darslar yo'q — «Fan skeleti» bilan yarating.</div>`}`;
  const back = box.querySelector("#dsBack"); if (back) back.onclick = () => { DS.cid = 0; DS.kurs = c.course; DS.dir = c.direction; DS.q = ""; dsSubjects(box, {focus: true}); };
  dsStage(box, o, `${c.subject}: ${d.lessons.length} ta dars`);
  box.querySelectorAll("[data-ver]").forEach(b => b.onclick = () => { dsVerSet(b.dataset.ver); dsSubject(box); });
  box.querySelectorAll("[data-kx]").forEach(b => b.onclick = () => kxOpen(box, DS.cid, +b.dataset.kx));
  box.querySelectorAll("[data-card]").forEach(b => b.onclick = () => lcOpen(DS.cid, +b.dataset.card));
  if (typeof KX === "object" && KX.pending && KX.pending.cid === DS.cid) { const k = KX.pending.key; KX.pending = null; return kxOpen(box, DS.cid, k); }
  if (DS.pendingCard || DS.pendingCode) {      /* to'liq dars kodi bilan qidirildi — shu dars kartochkasi ochiladi */
    const l = d.lessons.find(x => (DS.pendingCard && x.key === DS.pendingCard) || (DS.pendingCode && String(x.code).toUpperCase() === DS.pendingCode));
    DS.pendingCard = 0; DS.pendingCode = "";
    if (l && typeof lcOpen === "function" && ["maruza", "amaliy"].includes(l.kind)) lcOpen(DS.cid, l.key);
    else if (l) toast(`${l.code} — kartochka bu dars turi uchun yo'q`);
    else toast("Bu fanda bunday dars topilmadi");
  }
  box.querySelector("#dsSkel")?.addEventListener("click", () => dsSkeleton(box));
  box.querySelector("#dsApply")?.addEventListener("click", () => dsApply(box));
  box.querySelector("#dsBulk")?.addEventListener("click", () => dsBulk(box));
  box.querySelector("#dsBulkUp")?.addEventListener("click", () => kxbOpen(box));
  box.querySelector("#dsAq")?.addEventListener("click", e => { if (!arm(e.currentTarget, "Qo'shilsinmi?")) return; (async () => {
    const r = await pkApi(`/api/dars/subjects/${DS.cid}/dars-testlari`, {});
    if (!r) return;
    toast(`Dars oxiri testi: ${r.added.length} ta qo'shildi${r.skipped.length ? `, ${r.skipped.length} ta o'tkazildi (${r.skipped[0].reason})` : ""}${r.already ? `, avvaldan ${r.already}` : ""}`);
    dsSubject(box);
  })(); });
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
    <button type="button" class="btn sm ${k ? "" : "primary"}" id="dsTk">${k ? "Muharrirda ochish" : "Muharrirda tahrirlash"}</button></div>
    ${k && W ? `<div class="ds-bar ds-rs" id="dsRs" hidden></div>` : ""}`;
}
function dsTopicBind(el, d) {
  el.querySelector("#dsTk")?.addEventListener("click", async e => {
    const k = d.kurs_link; if (k) return go("kurs", {cid: k.id});
    e.currentTarget.disabled = true;
    const r = await pkApi(`/api/dars/subjects/${PK.cid}/lessons/${PK.topic}/convert`, {});
    if (r) go("kurs", {cid: r.ku_course_id}); else e.currentTarget && (e.currentTarget.disabled = false);
  });
  if (el.querySelector("#dsRs")) dsResyncCheck(el, PK.cid, PK.topic);
}
/* paket → muharrir qayta sinxronlash: o'tkazilgandan keyin paketga yangi / o'zgargan fayllar — «Yangi fayllar bor» → «Muharrirga qo'shish» */
async function dsResyncCheck(el, cid, key) {
  const box = el.querySelector("#dsRs"); if (!box) return;
  const url = `/api/dars/subjects/${cid}/lessons/${key}/resync`;
  const r = await pkApi(url).catch(() => null);
  if (!r || !box.isConnected || PK.cid !== cid || PK.topic !== key) return;
  if (!r.pending) { box.hidden = true; return; }
  const parts = [r.add ? `${r.add} ta blok qo'shiladi` : "", r.update ? `${r.update} ta yangilanadi` : "", r.remove ? `${r.remove} ta ortiqcha shablon bloki olinadi` : ""].filter(Boolean);
  box.innerHTML = `${ico("upload", 15)}<span><b>Yangi fayllar bor</b> — muharrirga o'tkazilgandan keyin paket o'zgargan
      (${esc(r.slots.map(s => s.label).join(", "))}): ${esc(parts.join(", "))}; muallif bloklari (${r.author} ta) tegilmaydi${r.conflict ? ` · muharrirda o'zgartirilgan bandlar ham tegilmaydi: ${esc(r.conflicts.join(", "))}` : ""}</span>
    <button type="button" class="btn sm primary" id="dsRsGo">Muharrirga qo'shish</button>`;
  box.hidden = false;
  box.querySelector("#dsRsGo").onclick = () => {
    pkModal("Muharrirga qo'shish", `<p class="pk-note" style="margin-top:0">Paketdagi yangi / o'zgargan mazmun muharrir kursidagi shablon bloklariga yoziladi. Oldin kurs versiyaga saqlanadi («Versiyalar»dan qaytarish mumkin).</p>
      <ul class="ds-rs-l">${r.slots.map(s => `<li><b>${esc(s.label)}</b> — ${[s.add ? `+${s.add} qo'shiladi` : "", s.update ? `~${s.update} yangilanadi` : "", s.remove ? `−${s.remove} olinadi` : ""].filter(Boolean).join(", ")}</li>`).join("")}</ul>
      <p class="pk-note"><b>Jami:</b> ${r.add} ta blok qo'shiladi, ${r.update} ta yangilanadi${r.remove ? `, ${r.remove} ta olinadi` : ""}. <b>Muallif bloklari (${r.author} ta) o'zgarmaydi.</b>
      ${r.conflict ? `<br>Muharrirda qo'lda o'zgartirilgan bandlar ustidan yozilmaydi: ${esc(r.conflicts.join(", "))}.` : ""}</p>`,
      async () => {
        const x = await pkApi(url, {preview: false});
        if (!x) return false;
        toast(x.applied ? `Muharrirga qo'shildi: +${x.add} ~${x.update}${x.remove ? ` −${x.remove}` : ""} · muallif bloklari tegilmadi` : "Yangilanadigan narsa yo'q");
        box.hidden = true; return true;
      }, "Muharrirga qo'shish");
  };
}
