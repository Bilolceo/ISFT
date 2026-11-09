/* =====================================================================
   Kirish nazorati (Face ID) — Kameralar sahifasidagi "Kirish (Face ID)" yorlig'i.
   Backend: app/facecam.py (/api/face/*). Ko'lam serverda: rektor/xo'jalik — hammasi; kadrlar — o'qituvchi va xodimlar;
   fakultet tyutori — o'z fakulteti talabalari (institutda dekan lavozimi yo'q); AT boshlig'i — faqat kamera va kutubxona holati (sonlar).
   app.js / nav.js yordamchilari: $, J, esc, fmt, toast, busy, ico, ICONS, locked, errCard, pgSrc, whenTxt, dmy, ME.
   Global: fcRole(), renderFace(el) — cams.js chaqiradi. Uslublar: facecam.css
   ===================================================================== */
const FC = {date: "", cam: 0, kind: "", q: "", off: 0, lim: 24, s: null, list: [], total: 0, rep: null, seq: 0};
const FC_ROLES = ["rektor", "xojalik", "kadrlar", "tyutor", "it_head"];
const FC_KIND = {talaba: "Talaba", oqituvchi: "O'qituvchi", xodim: "Xodim"};
const FC_ST = {tanildi: "Tanildi", notanish: "Notanish shaxs", rozilik_yoq: "Aniqlanmadi (rozilik yo'q)", past_ishonch: "Past ishonch"};
function fcRole() { return !!ME && FC_ROLES.includes(ME.role_key); }

if (typeof ICONS === "object") Object.assign(ICONS, {
  scanface: '<path d="M3 7V5a2 2 0 0 1 2-2h2"/><path d="M17 3h2a2 2 0 0 1 2 2v2"/><path d="M21 17v2a2 2 0 0 1-2 2h-2"/><path d="M7 21H5a2 2 0 0 1-2-2v-2"/><path d="M8 14s1.5 2 4 2 4-2 4-2"/><path d="M9 9h.01"/><path d="M15 9h.01"/>',
  arrowin: '<path d="M12 19V5"/><path d="m5 12 7-7 7 7"/>',
  arrowout: '<path d="M12 5v14"/><path d="m19 12-7 7-7-7"/>',
  briefcase: '<rect x="2" y="7" width="20" height="14" rx="2"/><path d="M16 21V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v16"/>',
  chevl: '<path d="m15 18-6-6 6-6"/>',
});

/* ---------- yordamchilar ---------- */
const fcT = iso => (iso || "").slice(11, 19);
const fcHM = iso => (iso || "").slice(11, 16);
const fcCls = f => f.visible ? (f.status === "tanildi" ? `k-${f.kind}` : f.status === "past_ishonch" ? "k-past" : "k-unk") : "k-hid";
const fcShort = n => { const p = String(n || "").split(" "); return p.length > 1 ? `${p[0]} ${p[1][0]}.` : (n || ""); };
function fcChip(f) {
  if (!f.visible) return `<span class="fc-chip k-hid" title="Ko'lamingizdan tashqari — yuz yashirilgan">${ico("eyeoff", 12)}yashirin</span>`;
  if (f.status === "tanildi") return `<span class="fc-chip ${fcCls(f)}" title="${esc(FC_KIND[f.kind])} · ${esc(f.name)} · ${esc(f.sub || "")} · ${f.similarity}%"><i></i>${esc(fcShort(f.name))}<small>${esc(f.sub || "")}</small></span>`;
  if (f.status === "past_ishonch") return `<span class="fc-chip k-past" title="O'xshashlik ${f.similarity}% — chegaradan past, tasdiqlanmagan"><i></i>Past ishonch ${f.similarity ?? ""}%</span>`;
  return `<span class="fc-chip k-unk"><i></i>${f.status === "rozilik_yoq" ? "Aniqlanmadi (rozilik yo'q)" : "Notanish"}</span>`;
}
const fcDir = d => d === "kirish" ? `<span class="fc-dir in">${ico("arrowin", 12)}kirish</span>` : `<span class="fc-dir out">${ico("arrowout", 12)}chiqish</span>`;
const fcBanner = s => `<div class="fc-banner" role="note">${ico("shield", 18)}<div><b>${esc(s.banner)}</b>
  <span>Yuzni kameraning o'zi solishtiradi (yuz kutubxonasi, FPID); serverda faqat metama'lumot. Ko'lamingiz: <b>${esc(s.scope_label)}</b>. Har bir ko'rish audit jurnaliga yoziladi.</span></div></div>`;

/* =====================================================================
   Asosiy ko'rinish
   ===================================================================== */
async function renderFace(el) {
  el.innerHTML = `<p class="muted">Yuklanmoqda…</p>`;
  try { document.getElementById("cmt-face")?.scrollIntoView({block: "nearest", inline: "nearest"}); } catch (e) {}   /* telefonda yorliq ko'rinsin */
  let s;
  try { s = await J(`/api/face/summary?date=${encodeURIComponent(FC.date)}`); }
  catch (e) { el.innerHTML = e?.message === "denied" ? locked("Kirish nazorati (Face ID)") : errCard("cams"); return; }
  FC.s = s; if (!FC.date) FC.date = s.date;
  if (s.mode === "health") return fcHealth(el, s);
  const k = s.kpi || {}, can = s.can;
  const tiles = [["talaba", "Talabalar kirdi", k.talaba, "aniqlangan, noyob", "users", "k-talaba"], ["oqituvchi", "O'qituvchilar kirdi", k.oqituvchi, "aniqlangan, noyob", "cap", "k-oqituvchi"],
    ["xodim", "Xodimlar kirdi", k.xodim, "aniqlangan, noyob", "briefcase", "k-xodim"], ["notanish", "Notanish / rozilik yo'q", k.notanish, "ismsiz qayd etilgan", "alert", "k-unk"],
    ["late", "Kechikkan o'qituvchilar", k.late_teachers, "birinchi para boshlangach kirgan", "clock", k.late_teachers ? "bad" : ""]].filter(t => t[2] != null);
  const isToday = FC.date === s.today;
  el.innerHTML = `${fcBanner(s)}
    <div class="fc-kpis">${tiles.map(([key, l, v, sub, i, c]) => `<button type="button" class="card kpi fc-kpi ${c}" data-fk="${key}" title="Kadrlarni shu tur bo'yicha saralash"><div class="l">${ico(i, 16)}<span>${l}</span></div><div class="v">${fmt(v)}</div><div class="s">${sub}${isToday ? "" : ` · ${dmy(FC.date)}`}</div></button>`).join("")}</div>
    <div class="card fc-bar" role="search">
      <label class="fc-f"><span>Sana</span><input type="date" id="fcDate" value="${esc(FC.date)}" max="${esc(s.today)}" min="${esc(fcAddDays(s.today, -13))}"></label>
      <label class="fc-f"><span>Kamera</span><select id="fcCam"><option value="0">Barcha kirishlar</option>${s.cameras.map(c => `<option value="${c.id}"${+FC.cam === c.id ? " selected" : ""}>${esc(c.name)}</option>`).join("")}</select></label>
      <div class="fc-f"><span>Tur</span><div class="fc-seg" role="group" aria-label="Tur bo'yicha">${[["", "Hammasi"], ...can.kinds.map(x => [x, FC_KIND[x]]), ...(can.unknown ? [["notanish", "Notanish"], ["past_ishonch", "Past ishonch"]] : [])].map(([v, l]) => `<button type="button" data-kind="${v}" aria-pressed="${FC.kind === v}" class="${FC.kind === v ? "on" : ""}">${l}</button>`).join("")}</div></div>
      <label class="fc-f fc-q"><span>Qidiruv</span><input type="search" id="fcQ" placeholder="${can.kinds.includes("talaba") ? "Ism yoki guruh (masalan, BHM-2404)" : "Ism, kafedra yoki bo'lim"}" value="${esc(FC.q)}" autocomplete="off"></label>
    </div>
    <div class="fc-wrap">
      <section class="fc-main" aria-label="Kirish kadrlari">
        <div class="head fc-h"><h3>${ico("scanface", 18)}Kirish kadrlari <span class="cm-cnt" id="fcCnt">…</span></h3><span class="tiny muted">Kadrni bosing — katta ko'rinish va shaxslar ro'yxati</span></div>
        <div class="fc-grid" id="fcGrid" aria-live="polite"></div>
        <div class="fc-more" id="fcMore"></div>
      </section>
      <aside class="fc-side">
        <section class="card fc-rep" id="fcRep" aria-label="AI hisobot"><div class="head fc-h"><h3>${ico("spark", 18)}AI hisobot</h3></div><p class="muted tiny">Tayyorlanmoqda…</p></section>
        <section class="card fc-legend"><h4>Ramka ranglari</h4>${Object.entries(s.legend).filter(([x]) => can.kinds.includes(x) || (can.unknown && ["notanish", "past_ishonch"].includes(x))).map(([x, l]) => `<span class="fc-chip k-${x === "notanish" ? "unk" : x === "past_ishonch" ? "past" : x}"><i></i>${esc(l)}</span>`).join("")}
          <span class="fc-chip k-hid">${ico("eyeoff", 12)}Ko'lamdan tashqari (yuz yashirilgan)</span>
          <p class="tiny muted">${ico("info", 13)} Kamera faqat yozma roziligi bor shaxslarni taniydi (${s.library ? `${fmt(s.library.consented_total)} / ${fmt(s.library.total)} kishi` : "rozilik reyestri"}). O'xshashlik ${s.legend.past_ishonch.match(/\d+/)?.[0] || 75}% dan past bo'lsa — tasdiqlanmagan.</p>
          ${can.manage.length || ME.role_key === "tyutor" ? `<button class="btn sm" id="fcReg">${ico("lock", 15)}Rozilik reyestri</button>` : ""}</section>
      </aside>
    </div>
    <dialog class="fc-dlg" id="fcDlg" aria-label="Kadr"></dialog>`;
  el.querySelectorAll("[data-kind]").forEach(b => b.onclick = () => { FC.kind = b.dataset.kind; el.querySelectorAll("[data-kind]").forEach(x => { const on = x.dataset.kind === FC.kind; x.classList.toggle("on", on); x.setAttribute("aria-pressed", on); }); fcLoad(); });
  el.querySelectorAll("[data-fk]").forEach(b => b.onclick = () => {
    const v = b.dataset.fk === "late" ? "oqituvchi" : b.dataset.fk;
    const x = el.querySelector(`[data-kind="${v}"]`); if (x) x.click();
    if (b.dataset.fk === "late") $("#fcRep")?.scrollIntoView({behavior: "smooth", block: "start"});
  });
  $("#fcDate").onchange = e => { if (!e.target.value) return; FC.date = e.target.value; FC.rep = null; renderFace(el); };
  $("#fcCam").onchange = e => { FC.cam = +e.target.value; fcLoad(); };
  let tq; $("#fcQ").oninput = e => { clearTimeout(tq); tq = setTimeout(() => { FC.q = e.target.value.trim(); fcLoad(); }, 320); };
  const reg = $("#fcReg"); if (reg) reg.onclick = () => fcRegistry();
  fcLoad(); fcReport();
}
function fcAddDays(iso, n) { const d = new Date(iso + "T12:00:00"); d.setDate(d.getDate() + n); return d.toISOString().slice(0, 10); }

async function fcLoad(more) {
  const g = $("#fcGrid"); if (!g) return;
  const seq = ++FC.seq;
  if (!more) { FC.off = 0; g.setAttribute("aria-busy", "true"); g.style.opacity = ".6"; }
  let r;
  try { r = await J(`/api/face/frames?date=${encodeURIComponent(FC.date)}&camera=${FC.cam}&kind=${encodeURIComponent(FC.kind)}&q=${encodeURIComponent(FC.q)}&offset=${FC.off}&limit=${FC.lim}`); }
  catch (e) { if (seq === FC.seq) { g.innerHTML = e?.message === "denied" ? locked("Kirish kadrlari") : errCard("cams"); g.style.opacity = ""; } return; }
  if (seq !== FC.seq) return;
  FC.list = more ? FC.list.concat(r.frames) : r.frames; FC.total = r.total;
  g.removeAttribute("aria-busy"); g.style.opacity = "";
  $("#fcCnt").textContent = fmt(r.total);
  g.innerHTML = FC.list.length ? FC.list.map(fcCard).join("") : `<div class="cm-empty fc-empty">${ico("scanface", 26)}<b>Kadr topilmadi</b><span>Tanlangan sana va filtr bo'yicha kirish qayd etilmagan.</span>${FC.kind || FC.q || FC.cam ? `<button class="btn sm" id="fcReset">Filtrni tiklash</button>` : ""}</div>`;
  g.querySelectorAll("[data-fid]").forEach(b => b.onclick = () => fcOpen(+b.dataset.fid));
  const rs = $("#fcReset"); if (rs) rs.onclick = () => { FC.kind = ""; FC.q = ""; FC.cam = 0; renderFace($("#cmBody")); };
  const left = r.total - FC.list.length, m = $("#fcMore");
  m.innerHTML = left > 0 ? `<button class="btn ghost sm">Yana ${Math.min(FC.lim, left)} ta ko'rsatish <span class="muted">(${left} qoldi)</span></button>` : "";
  if (left > 0) m.querySelector("button").onclick = () => { FC.off += FC.lim; fcLoad(true); };
}

function fcCard(f) {
  const vis = f.faces.filter(x => x.visible), hid = f.faces.length - vis.length;
  const alt = `${fcT(f.ts)}, ${f.camera}, ${f.direction}: ` + vis.map(x => x.status === "tanildi" ? `${FC_KIND[x.kind]} ${x.name}` : FC_ST[x.status]).join("; ");
  return `<button type="button" class="fc-card${f.night ? " night" : ""}" data-fid="${f.id}" aria-label="${esc(alt)}">
    <span class="fc-img"><img src="${f.img}?w=480" alt="" loading="lazy" decoding="async" width="480" height="270">${f.night ? `<em class="fc-nt">${ico("moon", 12)}tun</em>` : ""}</span>
    <span class="fc-cm"><time datetime="${esc(f.ts)}">${fcT(f.ts)}</time>${fcDir(f.direction)}<span class="fc-cam">${esc(f.camera)}</span></span>
    <span class="fc-chips">${vis.map(fcChip).join("")}${hid ? `<span class="fc-chip k-hid" title="Ko'lamingizdan tashqari">${ico("eyeoff", 12)}+${hid}</span>` : ""}</span></button>`;
}

/* ---------- katta ko'rinish ---------- */
function fcDlg(html) {
  const d = $("#fcDlg"); if (!d) return null;
  d.innerHTML = `<div class="fc-dh"><span id="fcDT"></span><button class="btn ghost sm" data-close aria-label="Yopish">${ico("x", 18)}</button></div><div class="fc-db">${html}</div>`;
  d.querySelector("[data-close]").onclick = () => d.close();
  if (!d.open) { d.showModal(); d.onclick = e => { if (e.target === d) d.close(); }; }
  return d;
}
async function fcOpen(fid) {
  const d = fcDlg(`<p class="muted">Yuklanmoqda…</p>`); if (!d) return;
  let r; try { r = await J(`/api/face/frames/${fid}`); } catch (e) { d.close(); return; }
  $("#fcDT").innerHTML = `<b>${esc(r.camera)}</b> · ${dmy(r.ts)} ${fcT(r.ts)} ${fcDir(r.direction)}`;
  d.querySelector(".fc-db").innerHTML = `<div class="fc-view"><figure><img src="${r.img}" alt="Kirish kadri: ${esc(r.camera)}, ${fcT(r.ts)}" width="1280" height="720"><figcaption class="tiny muted">${ico("info", 13)} ${esc(r.note)}</figcaption></figure>
    <div class="fc-plist"><h4>Kadrdagi shaxslar (${r.faces.length})</h4>${r.faces.map(f => `<div class="fc-p ${fcCls(f)}"><i></i><div>
      ${f.visible && f.name ? `<b>${f.candidate ? `<span class="fc-cand">Ehtimol:</span> ` : ""}${esc(f.name)}</b><span>${esc(f.kind_label)} · ${esc(f.sub || "")}</span>` : `<b>${f.visible ? esc(f.status_label) : "Ko'lamingizdan tashqari"}</b><span>${f.visible ? (f.status === "rozilik_yoq" ? "Yozma rozilik yo'q — shaxs aniqlanmaydi va saqlanmaydi" : f.status === "past_ishonch" ? "O'xshashlik chegaradan past — tasdiqlanmagan" : "Yuz kutubxonasida yo'q (mehmon yoki ro'yxatdan o'tmagan)") : "Yuz rasmda yashirilgan"}</span>`}
      ${f.visible && f.name ? `<small>${esc(f.status_label)}${f.similarity != null ? ` · o'xshashlik ${f.similarity}%` : ""}${f.candidate ? " — tasdiqlanmagan, hisobotlarda hisobga olinmaydi" : ""}</small>` : ""}
      ${f.visible && f.person_id && f.status === "tanildi" ? `<button class="btn sm ghost" data-tl="${f.person_id}">${ico("calendar", 14)}14 kunlik tarix</button>` : ""}</div></div>`).join("")}</div></div>`;
  d.querySelectorAll("[data-tl]").forEach(b => b.onclick = () => fcTimeline(+b.dataset.tl, fid));
}

/* ---------- shaxs tarixi (14 kun) ---------- */
async function fcTimeline(pid, back) {
  const d = fcDlg(`<p class="muted">Yuklanmoqda…</p>`); if (!d) return;
  let r; try { r = await J(`/api/face/persons/${pid}/timeline?days=14`); } catch (e) { d.close(); return; }
  const p = r.person;
  $("#fcDT").innerHTML = `${back ? `<button class="btn ghost sm" id="fcBack">${ico("chevl", 16)}Kadrga qaytish</button>` : ""}<b>${esc(p.name)}</b> <span class="muted">· ${esc(p.kind_label)} · ${esc(p.sub || "")}</span>`;
  const isT = p.kind !== "xodim", rows = r.days.map(x => {
    const fs = x.first_slot;
    return `<tr class="${x.late_min ? "late" : ""}${x.first_in ? "" : " abs"}"><td class="nowrap"><b>${x.date.slice(8, 10)}.${x.date.slice(5, 7)}</b> <span class="muted">${x.weekday}</span></td>
      <td class="nowrap">${fs ? `${fs.slot ? fs.slot + "-para · " : ""}${fs.start}` : `<span class="muted">${isT ? "dars yo'q" : "—"}</span>`}</td>
      <td class="nowrap">${x.first_in ? `<b>${fcHM(x.first_in)}</b>` : `<span class="muted">—</span>`}${x.late_min ? ` <span class="tag high">+${x.late_min} daq.</span>` : ""}</td>
      <td class="nowrap">${x.last_out ? fcHM(x.last_out) : `<span class="muted">—</span>`}</td>
      <td><div class="fc-evs">${x.events.map(e => `<button type="button" class="fc-ev ${e.direction === "kirish" ? "in" : "out"}${e.status !== "tanildi" ? " low" : ""}" data-fr="${e.frame_id}" title="${esc(e.camera)} · ${e.similarity ?? "—"}% · ${esc(FC_ST[e.status] || e.status)}">${ico(e.direction === "kirish" ? "arrowin" : "arrowout", 11)}${fcHM(e.ts)}</button>`).join("")}</div></td></tr>`;
  }).join("");
  d.querySelector(".fc-db").innerHTML = `<div class="fc-tl">
    <div class="fc-tls"><span><b>${r.present_days}</b> kun kelgan</span><span class="${r.late_days ? "bad" : ""}"><b>${r.late_days}</b> kun kechikkan</span>
      <span class="muted">${p.consent ? `${ico("check", 13)}Yozma rozilik: ${esc(p.consent_doc || "")} (${esc(p.consent_at || "")})` : "Rozilik yo'q"}</span></div>
    <div class="tw"><table class="fc-tlt"><thead><tr><th>Sana</th><th>${isT ? "Birinchi para" : "Ish boshlanishi"}</th><th>Kirdi</th><th>Chiqdi</th><th>Kirish/chiqish (kadrni ochish)</th></tr></thead><tbody>${rows}</tbody></table></div>
    <p class="tiny muted">${ico("info", 13)} Kechikish: ${isT ? "dars jadvalidagi birinchi para boshlanishidan keyin" : "09:00 dan keyin"} birinchi kirish. Faqat tasdiqlangan (o'xshashlik chegaradan yuqori) aniqlashlar hisoblanadi. Ko'rish audit jurnaliga yozildi.</p></div>`;
  d.querySelectorAll("[data-fr]").forEach(b => b.onclick = () => fcOpen(+b.dataset.fr));
  const bk = $("#fcBack"); if (bk) bk.onclick = () => fcOpen(back);
}

/* ---------- AI hisobot ---------- */
async function fcReport() {
  const box = $("#fcRep"); if (!box) return;
  let r; try { r = await J(`/api/face/report?date=${encodeURIComponent(FC.date)}`); } catch (e) { box.innerHTML = `<p class="muted tiny">Hisobot uchun ruxsat yo'q</p>`; return; }
  const f = r.facts, v = r.verify || {};
  const lt = f.late_teachers || [], sa = f.staff_after || [];
  box.innerHTML = `<div class="head fc-h"><h3>${ico("spark", 18)}AI hisobot <span class="tiny muted">${dmy(f.date)}</span></h3>
      <span class="tag ${r.narrative_mode === "ai" ? "low" : "gray"}" title="${r.narrative_mode === "ai" ? "Mahalliy til modeli faktlardan yozdi; raqamlar tekshirildi" : "Mahalliy til modeli ulanmagan — matnni kod shablon asosida tuzdi"}">${r.narrative_mode === "ai" ? "AI (mahalliy)" : "Kod shabloni"}</span></div>
    <p class="fc-nar">${esc(r.narrative)}</p>
    <p class="tiny fc-ver ${v.bad?.length ? "bad" : ""}">${ico(v.bad?.length ? "alert" : "checkc", 13)}Matndagi ${v.n ?? 0} ta raqam bazadagi faktlar bilan solishtirildi: ${v.ok ?? 0} tasi mos${v.bad?.length ? ` · mos emas: ${v.bad.map(esc).join(", ")}` : ""}</p>
    ${lt.length ? `<h4>Kechikkan o'qituvchilar <span class="muted">(${f.late_teachers_n})</span></h4><div class="tw"><table class="fc-t"><thead><tr><th>O'qituvchi</th><th>Para</th><th>Kirdi</th><th class="n">Daq.</th></tr></thead><tbody>${lt.slice(0, 8).map(x => `<tr><td><a href="#" data-tl="${x.person_id}">${esc(fcShort(x.name))}</a><br><span class="tiny muted">${esc(x.kafedra)}</span></td><td class="nowrap">${x.slot}-para ${x.first_para}</td><td class="nowrap">${x.arrival}</td><td class="n bad">+${x.minutes}</td></tr>`).join("")}</tbody></table></div>` : f.late_teachers_n === 0 && FC.s.can.kinds.includes("oqituvchi") ? `<p class="tiny fc-ok">${ico("checkc", 13)}Birinchi darsiga kechikkan o'qituvchi yo'q</p>` : ""}
    ${f.late_groups?.length ? `<h4>Birinchi paraga kech kirgan talabalar <span class="muted">(${f.late_students_n})</span></h4><div class="fc-groups">${f.late_groups.map(g => `<span><b>${esc(g.group)}</b> ${g.n}</span>`).join("")}</div>` : ""}
    ${sa.length ? `<h4>${esc(f.rules.staff_late)}: xodimlar <span class="muted">(${f.staff_after_n})</span></h4><ul class="fc-ul">${sa.slice(0, 6).map(x => `<li><b>${esc(fcShort(x.name))}</b> <span class="muted">${esc(x.unit)}</span> — ${x.arrival} <span class="bad">+${x.minutes}</span></li>`).join("")}</ul>` : ""}
    ${FC.s.can.unknown ? `<h4>Xavfsizlik</h4><div class="fc-sec"><span><b>${f.unknown}</b> notanish</span><span><b>${f.no_consent}</b> rozilik yo'q</span><span class="${f.night_entries ? "bad" : ""}"><b>${f.night_entries}</b> tungi kirish</span><span><b>${f.low_conf_pct}%</b> past ishonch</span></div>${f.night.length ? `<ul class="fc-ul">${f.night.map(x => `<li>${ico("moon", 13)} ${esc(x.ts)} — ${esc(x.camera)} · ${esc(x.status)}</li>`).join("")}</ul>` : ""}` : ""}
    ${f.prev7?.entries_avg ? `<p class="tiny muted">Oldingi ${f.prev7.days} ish kuni o'rtachasi: ${f.prev7.entries_avg} kirish (bugun ${f.entries}, ${f.prev7.entries_delta_pct > 0 ? "+" : ""}${f.prev7.entries_delta_pct}%).</p>` : ""}
    <button class="btn sm" id="fcDocx">${ico("download", 15)}Word yuklab olish</button>`;
  box.querySelectorAll("[data-tl]").forEach(a => a.onclick = e => { e.preventDefault(); fcTimeline(+a.dataset.tl); });
  $("#fcDocx").onclick = () => busy($("#fcDocx"), async () => {
    const j = await J("/api/face/report/docx", {method: "POST", body: JSON.stringify({date: FC.date})});
    if (!j?.file) return toast("Hisobotni tayyorlab bo'lmadi");
    const a = document.createElement("a"); a.href = `/api/docs/file/${encodeURIComponent(j.file)}`; a.download = j.file; document.body.appendChild(a); a.click(); a.remove();
    toast(`Hisobot tayyor: ${j.file} — Hujjatlar markazida ham saqlandi`);
  }, "Tayyorlanmoqda…");
}

/* ---------- rozilik reyestri ---------- */
async function fcRegistry(q = "", kind = "") {
  const d = fcDlg(`<p class="muted">Yuklanmoqda…</p>`); if (!d) return;
  let r; try { r = await J(`/api/face/persons?q=${encodeURIComponent(q)}&kind=${encodeURIComponent(kind)}`); } catch (e) { d.close(); return; }
  $("#fcDT").innerHTML = `<b>Rozilik reyestri</b> <span class="muted">· ${r.counts.consented} / ${r.counts.total} kishi yozma rozilik bergan</span>`;
  d.querySelector(".fc-db").innerHTML = `<div class="fc-reg"><p class="tiny muted">${ico("info", 13)} ZRU-547: biometrik ma'lumot faqat shaxsning yozma roziligi bilan. Rozilik qaytarib olinsa — FPID va kameradagi yuz yozuvi o'chiriladi, o'tgan kirishlar shaxssizlantiriladi.</p>
    <div class="fc-rbar"><input type="search" id="fcRq" placeholder="Ism, guruh yoki bo'lim" value="${esc(q)}"><select id="fcRk"><option value="">Barcha turlar</option>${Object.entries(FC_KIND).map(([k, l]) => `<option value="${k}"${kind === k ? " selected" : ""}>${l}</option>`).join("")}</select></div>
    <div class="tw"><table class="fc-t"><thead><tr><th>Shaxs</th><th>Holat</th><th></th></tr></thead><tbody>${r.persons.slice(0, 150).map(p => `<tr data-pid="${p.id}"><td><b>${esc(p.name)}</b><br><span class="tiny muted">${esc(p.kind_label)} · ${esc(p.sub || "")}</span></td>
      <td>${p.consent ? `<span class="tag low">${ico("check", 12)}Rozilik bor</span><br><span class="tiny muted">${esc(p.consent_doc || "")} · ${esc(p.consent_at || "")}</span>` : p.revoked_at ? `<span class="tag high">Qaytarib olingan</span><br><span class="tiny muted">${esc(p.revoked_at.slice(0, 10))}</span>` : `<span class="tag gray">Rozilik yo'q</span>`}</td>
      <td class="fc-ra">${p.can_manage ? (p.consent ? `<button class="btn sm ghost" data-rv="${p.id}">Qaytarib olish</button>` : `<span class="fc-gr"><input placeholder="RZ-2026/…" aria-label="Rozilik hujjati raqami" maxlength="60"><button class="btn sm" data-gr="${p.id}">Rozilik qo'shish</button></span>`) : ""}</td></tr>`).join("")}</tbody></table></div></div>`;
  let t; $("#fcRq").oninput = e => { clearTimeout(t); t = setTimeout(() => fcRegistry(e.target.value.trim(), $("#fcRk").value), 350); };
  $("#fcRk").onchange = e => fcRegistry($("#fcRq").value.trim(), e.target.value);
  d.querySelectorAll("[data-rv]").forEach(b => b.onclick = () => {
    if (!confirm("Rozilik qaytarib olinsinmi? FPID o'chiriladi va o'tgan kirishlar shaxssizlantiriladi (qaytarib bo'lmaydi).")) return;
    busy(b, async () => { const j = await J(`/api/face/persons/${b.dataset.rv}/consent`, {method: "POST", body: JSON.stringify({action: "revoke"})}); toast(j.note || "Rozilik qaytarib olindi"); fcRegistry($("#fcRq").value.trim(), $("#fcRk").value); });
  });
  d.querySelectorAll("[data-gr]").forEach(b => b.onclick = () => {
    const doc = b.previousElementSibling.value.trim();
    if (doc.length < 3) { b.previousElementSibling.focus(); return toast("Yozma rozilik hujjati raqamini kiriting"); }
    busy(b, async () => { const j = await J(`/api/face/persons/${b.dataset.gr}/consent`, {method: "POST", body: JSON.stringify({action: "grant", doc})}); toast(j.note || "Rozilik qo'shildi"); fcRegistry($("#fcRq").value.trim(), $("#fcRk").value); });
  });
}

/* ---------- AT bo'limi: faqat texnik holat ---------- */
function fcHealth(el, s) {
  const h = s.health || {}, L = s.library || {};
  el.innerHTML = `${fcBanner(s)}
    <div class="fc-kpis">${[["Bugun aniqlashlar", fmt(h.detections ?? 0), "barcha kirish kameralari", "scanface", ""], ["Tanilgan ulush", `${h.matched_pct ?? 0}%`, "kutubxona bilan mos kelgan", "checkc", ""],
      ["Past ishonch", `${h.low_conf_pct ?? 0}%`, `o'xshashlik < ${L.match_min || 75}%`, "alert", (h.low_conf_pct || 0) > 5 ? "warn" : ""],
      ["Yuz kutubxonasi", `${fmt(L.consented_total ?? 0)}`, `rozilik bergan / ${fmt(L.total ?? 0)} ro'yxatda`, "lock", ""], ["Sinxron navbati", fmt(L.sync_pending ?? 0), "kameraga yuborilmagan amallar", "refresh", L.sync_pending ? "warn" : ""]]
      .map(([l, v, sub, i, c]) => `<div class="card kpi fc-kpi ${c}"><div class="l">${ico(i, 16)}<span>${l}</span></div><div class="v">${v}</div><div class="s">${sub}</div></div>`).join("")}</div>
    <div class="card"><div class="head fc-h"><h3>${ico("cctv", 18)}Kirish kameralari</h3><button class="btn sm" id="fcSync">${ico("refresh", 15)}Kutubxonani kameralarga sinxronlash</button></div>
      ${tbl(["Kamera", "Model", "Holat", "Yuzni solishtirish", "#Bugun"], s.cameras.map(c => [`<b>${esc(c.name)}</b>`, esc(c.model || "—"), c.status === "onlayn" ? `<span class="tag low">onlayn</span>` : `<span class="tag high">${esc(c.status || "—")}</span>`, c.face_capable ? "bor (FDLib)" : `<span class="muted">yo'q</span>`, fmt(c.detections)]))}
      <p class="tiny muted">${ico("info", 13)} AT bo'limi uchun: faqat texnik holat va sonlar. Shaxslar, ismlar va kadrlar ko'rsatilmaydi (xo'jalik bo'limi va rektor). Oxirgi voqea: ${h.last_event ? whenTxt(h.last_event) : "—"} · rasm ${L.keep_days} kun, metama'lumot ${L.events_days} kun saqlanadi.</p></div>`;
  $("#fcSync").onclick = () => busy($("#fcSync"), async () => { const j = await J("/api/face/sync", {method: "POST"}); toast(j.note || (j.ok ? `Sinxronlandi: ${j.done} ta amal` : `Xato: ${(j.errors || []).join("; ")}`)); });
}
