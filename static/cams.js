/* =====================================================================
   Kameralar va xavfsizlik (Hikvision) — kamera holati, voqealar, navbat va olomon.
   Backend: app/camsec.py (/api/cams/*). Kameralar faqat raqam va voqea turini uzatadi — rasm, video, yuz yo'q.
   app.js yordamchilaridan foydalanadi: $, J, esc, fmt, toast, go, busy, ico, ICONS, hydrateIcons, tbl, bars, locked, errCard,
   pgSrc, whenTxt, dmy, ME, showLogin.
   Global: renderCams(), camsNav(), spcExtraHtml(o) (Auditoriyalar sahifasi uchun qo'shimcha kartalar), CM.
   Uslublar: cams.css
   ===================================================================== */
const CM = {tab: "holat", days: 7, prio: 3, status: "", group: "", show: 25, h: null, e: null, q: null, err: {}};
try { const t = localStorage.getItem("jarvis.camsTab"); if (["holat", "voqealar", "navbat", "face"].includes(t)) CM.tab = t; } catch (e) {}
const CM_QUEUE_ROLES = ["qabul", "buxgalteriya"];   /* backend: QUEUE_ZONES[*].role — faqat o'z navbatini ko'radi */

if (typeof ICONS === "object") {
  Object.assign(ICONS, {
    cctv: '<path d="M16.75 12h3.63a1 1 0 0 1 .9 1.45l-2.04 4.07a1 1 0 0 1-1.7.13l-2.13-2.97"/><path d="M17.1 9.05a1 1 0 0 1 .45 1.34l-3.1 6.21a1 1 0 0 1-1.35.45L3.6 12.3a2.92 2.92 0 0 1-1.3-3.9L3.7 5.6a2.92 2.92 0 0 1 3.9-1.3z"/><path d="M2 19h3.76a2 2 0 0 0 1.8-1.1L9 15"/><path d="M2 21v-4"/><path d="M7 9h.01"/>',
    wifioff: '<path d="M12 20h.01"/><path d="M8.5 16.4a5 5 0 0 1 7 0"/><path d="M2 8.8a15 15 0 0 1 4.2-2.6"/><path d="M5 12.9a10 10 0 0 1 5.2-2.7"/><path d="M19 12.9a10 10 0 0 0-2.4-1.7"/><path d="M22 8.8a15 15 0 0 0-11.3-3.8"/><path d="m2 2 20 20"/>',
    eyeoff: '<path d="M9.9 4.2A10 10 0 0 1 12 4c6.5 0 10 8 10 8a17 17 0 0 1-2.2 3.2"/><path d="M6.6 6.6A17 17 0 0 0 2 12s3.5 8 10 8a9.7 9.7 0 0 0 5.4-1.6"/><path d="M9.9 9.9a3 3 0 0 0 4.2 4.2"/><path d="m2 2 20 20"/>',
    cpu: '<rect x="5" y="5" width="14" height="14" rx="2"/><rect x="9" y="9" width="6" height="6" rx="1"/><path d="M9 2v3M15 2v3M9 19v3M15 19v3M2 9h3M2 15h3M19 9h3M19 15h3"/>',
    utensils: '<path d="M3 2v7c0 1.1.9 2 2 2h4a2 2 0 0 0 2-2V2"/><path d="M7 2v20"/><path d="M21 15V2a5 5 0 0 0-5 5v6c0 1.1.9 2 2 2h3zm0 0v7"/>',
    hall: '<path d="M3 21h18M5 21V8l7-5 7 5v13"/><path d="M9 21v-6h6v6"/>',
    route: '<circle cx="6" cy="19" r="3"/><path d="M9 19h8.5a3.5 3.5 0 0 0 0-7h-11a3.5 3.5 0 0 1 0-7H15"/><circle cx="18" cy="5" r="3"/>',
    building: '<rect x="4" y="2" width="16" height="20" rx="2"/><path d="M9 22v-4h6v4M8 6h.01M16 6h.01M12 6h.01M12 10h.01M12 14h.01M16 10h.01M16 14h.01M8 10h.01M8 14h.01"/>',
  });
  try { const s = document.querySelector('#nav a[data-v="cams"] svg'); if (s && !s.innerHTML.trim()) { s.remove(); hydrateIcons(); } } catch (e) {}
}

/* ---------- kichik yordamchilar ---------- */
const cmMsg = m => String(m || "").replace(/^[\s⛔️]+/u, "").trim();
const cmAge = s => s == null ? "—" : s < 60 ? `${s} s oldin` : s < 3600 ? `${Math.round(s / 60)} daq. oldin` : s < 86400 ? `${Math.round(s / 3600)} soat oldin` : `${Math.round(s / 86400)} kun oldin`;
const cmDay2 = d => ({Dushanba: "Du", Seshanba: "Se", Chorshanba: "Ch", Payshanba: "Pa", Juma: "Ju", Shanba: "Sh", Yakshanba: "Ya"})[d] || String(d).slice(0, 2);
const cmWd = iso => ["Ya", "Du", "Se", "Ch", "Pa", "Ju", "Sh"][new Date(iso + "T12:00:00").getDay()];
const cmDM = iso => `${iso.slice(8, 10)}.${iso.slice(5, 7)}`;
const CM_PRIO_CLS = {1: "p1", 2: "p2", 3: "p3", 4: "p4"};
const cmPrio = (p, lbl) => `<span class="cm-p ${CM_PRIO_CLS[p] || "p4"}" title="${esc(lbl || "P" + p)}">P${p}</span>`;
const CM_ST_CLS = {yangi: "new", korildi: "seen", tiket: "tk", notogri: "false", yopildi: "done", qayd: "done"};
const CM_ACT = {korildi: ["Ko'rildi", "eye"], notogri: ["Noto'g'ri signal", "x"], tiket: ["Tiket", "wrench"], yopildi: ["Yopish", "check"]};
const CM_NEXT = {yangi: ["korildi", "notogri", "tiket", "yopildi"], korildi: ["notogri", "tiket", "yopildi"], tiket: ["yopildi"]};
const CM_LV = {yashil: ["g", "Ishlayapti", ""], sariq: ["y", "E'tibor kerak", "!"], qizil: ["r", "Nosoz", "×"]};
const cmCanReport = () => ME && (["rektor", "xojalik"].includes(ME.role_key) || ME.allow.includes("reports"));

/* menyu: navbat zonasi mas'ullari (qabul, kassa) bo'limni ko'radi — faqat o'z navbati (boot() chaqiradi) */
function camsNav() {
  const a = document.querySelector('#nav a[data-v="cams"]');
  if (a && ME && !ME.allow.includes("spaces") && CM_QUEUE_ROLES.includes(ME.role_key)) a.classList.remove("hidden");
  if (a && typeof fcRole === "function" && fcRole()) a.classList.remove("hidden");   /* facecam.js: Kirish (Face ID) — kadrlar, tyutor ham */
}

async function cmLoadEv() {
  return J(`/api/cams/events?days=${CM.days}&prio=${CM.prio}&status=${encodeURIComponent(CM.status)}&group=${encodeURIComponent(CM.group)}`);
}

/* =====================================================================
   Asosiy ko'rinish
   ===================================================================== */
async function renderCams(keep) {
  const el = $("#v-cams"), full = ME.allow.includes("spaces");
  const fc = typeof fcRole === "function" && fcRole(), qOnly = !full && CM_QUEUE_ROLES.includes(ME.role_key);   /* fc — Kirish (Face ID) yorlig'i: facecam.js */
  if (!full) CM.tab = fc && !qOnly ? "face" : "navbat";
  if (CM.tab === "face" && !fc) CM.tab = "holat";
  if (!keep || !el.querySelector(".cm-tabs, #cmBody")) el.innerHTML = `<p class="muted">Yuklanmoqda…</p>`;
  const safe = p => Promise.resolve(p).then(x => x, e => { if (e?.message === "auth") throw e; return {__err: e?.message || "xato"}; });
  const [h, e, q] = await Promise.all([full ? safe(J("/api/cams/health")) : null, full ? safe(cmLoadEv()) : null, full || qOnly ? safe(J("/api/cams/queues")) : null]);
  CM.err = {};
  for (const [k, v] of [["h", h], ["e", e], ["q", q]]) { if (v && v.__err) { CM.err[k] = v.__err; CM[k] = null; } else CM[k] = v; }
  if (!full && !CM.q && !fc) {
    el.innerHTML = `<div class="head"><div><h2>Kameralar va xavfsizlik</h2></div></div>` + locked("Kameralar va xavfsizlik — rektor, prorektorlar va xo'jalik bo'limi uchun");
    return;
  }
  const now = CM.h?.now || CM.q?.now || "";
  const tabs = full ? [["holat", "Holat", "cctv"], ["voqealar", "Voqealar", "bolt"], ["navbat", `<span class="cm-tl">Navbat va olomon</span><span class="cm-ts">Navbat</span>`, "users"]] : [];
  if (fc) tabs.push(["face", `<span class="cm-tl">Kirish (Face ID)</span><span class="cm-ts">Face ID</span>`, "scanface"]);
  const flags = CM.h?.flags || {face: false, anpr: false};
  el.innerHTML = `<div class="head cm-head"><div><h2>Kameralar va xavfsizlik</h2>
      <span class="muted">${fc || flags.face ? "Auditoriya kameralari odamni emas, xonani sanaydi; yuzni tanish — faqat bino kirishlarida va faqat yozma roziligi bor shaxslar uchun" : "Kameralar odamni emas, xonani sanaydi: rasm va video saqlanmaydi, yuzni tanish o'chirilgan"}</span>
      ${now ? pgSrc(`Manba: Hikvision kameralari (demo: simulyator) · faqat metama'lumot · oxirgi yangilanish: <b>${whenTxt(now)}</b>`, "clock") : ""}</div>
    <div class="row-actions cm-hact"><span class="tag low" id="cmAnon" title="Voqealar shaxsga bog'lanmaydi — xona, bino va qavat kesimida">${ico("lock", 14)}Shaxssiz ma'lumot</span>
      <button class="btn sm ghost" id="cmRefresh" aria-label="Ma'lumotni yangilash">${ico("refresh", 16)}<span class="cm-hide-sm">Yangilash</span></button>
      ${full && cmCanReport() ? `<button class="btn sm" id="cmReport">${ico("download", 16)}Haftalik hisobot (.docx)</button>` : ""}</div></div>
    ${tabs.length ? `<div class="pn-tabs cm-tabs" role="tablist" aria-label="Kameralar bo'limlari">${tabs.map(([k, l, i]) => `<button class="pn-tab${CM.tab === k ? " on" : ""}" role="tab" id="cmt-${k}" aria-controls="cmBody" aria-selected="${CM.tab === k}" tabindex="${CM.tab === k ? 0 : -1}" data-cmt="${k}">${ico(i, 16)}<span>${l}</span><em hidden></em></button>`).join("")}</div>` : ""}
    <div id="cmBody" ${tabs.length ? `role="tabpanel" aria-labelledby="cmt-${CM.tab}"` : ""}></div>
    <p class="cm-flags">${ico("shield", 14)}<span>Yuzni tanish: <b>${flags.face || fc ? "yoqilgan — faqat kirishlarda, yozma rozilik bilan" : "o'chiq"}</b> (ZRU-547) · Avtoraqam: <b>${flags.anpr ? "yoqilgan" : "o'chiq"}</b> · ${flags.face || fc ? "kirish kadri ko'pi bilan 7 kun saqlanadi, video olinmaydi" : "kadr va video serverga olinmaydi"} · har bir ko'rish audit jurnaliga yoziladi</span></p>`;
  el.querySelectorAll("[data-cmt]").forEach(b => {
    b.onclick = () => cmSetTab(b.dataset.cmt);
    b.onkeydown = ev => {
      if (!["ArrowRight", "ArrowLeft"].includes(ev.key)) return;
      const bs = [...el.querySelectorAll("[data-cmt]")], i = bs.indexOf(b), n = bs[(i + (ev.key === "ArrowRight" ? 1 : bs.length - 1)) % bs.length];
      ev.preventDefault(); cmSetTab(n.dataset.cmt); n.focus();
    };
  });
  $("#cmRefresh").onclick = () => busy($("#cmRefresh"), () => renderCams(true), ico("refresh", 16));
  const rep = $("#cmReport");
  if (rep) rep.onclick = () => busy(rep, async () => {
    const r = await J("/api/cams/report", {method: "POST"});
    if (!r?.file) return toast("Hisobotni tayyorlab bo'lmadi");
    const a = document.createElement("a"); a.href = `/api/docs/file/${encodeURIComponent(r.file)}`; a.download = r.file; document.body.appendChild(a); a.click(); a.remove();
    toast(`Hisobot tayyor: ${r.file} — Hujjatlar markazida ham saqlandi`);
  }, "Tayyorlanmoqda…");
  cmCounts(); cmBody();
}
function cmSetTab(k) {
  CM.tab = k; try { localStorage.setItem("jarvis.camsTab", k); } catch (e) {}
  document.querySelectorAll("#v-cams [data-cmt]").forEach(b => { const on = b.dataset.cmt === k; b.classList.toggle("on", on); b.setAttribute("aria-selected", on); b.tabIndex = on ? 0 : -1; });
  $("#cmBody")?.setAttribute("aria-labelledby", "cmt-" + k);
  cmBody();
}
function cmCounts() {
  const set = (k, n, bad) => { const em = document.querySelector(`#v-cams [data-cmt="${k}"] em`); if (!em) return; em.textContent = n; em.hidden = !n; em.classList.toggle("bad", !!bad); };
  if (CM.h) set("holat", CM.h.levels.qizil, true);
  if (CM.e) set("voqealar", CM.e.stats.open, CM.e.stats.by_priority[1] + CM.e.stats.by_priority[2] > 0);
  if (CM.q) set("navbat", CM.q.zones.filter(z => z.now && z.now.n > z.limit).length, true);
}
function cmBody() {
  const b = $("#cmBody"); if (!b) return;
  const an = $("#cmAnon"); if (an) an.hidden = CM.tab === "face";
  if (CM.tab === "face" && typeof renderFace === "function") { renderFace(b); return; }   /* facecam.js */
  const fn = {holat: cmHolat, voqealar: cmVoqealar, navbat: cmNavbat}[CM.tab] || cmNavbat;
  const key = {holat: "h", voqealar: "e", navbat: "q"}[CM.tab] || "q";
  if (!CM[key]) { b.innerHTML = CM.err[key] === "denied" ? locked("Bu bo'lim") : errCard("cams"); return; }
  try { fn(b); } catch (err) { console.error(err); b.innerHTML = errCard("cams"); }
}

/* =====================================================================
   a) Holat — kameralar salomatligi
   ===================================================================== */
function cmDot(c) {
  const [cls, txt, glyph] = CM_LV[c.level] || CM_LV.yashil;
  const t = `${c.room} · ${c.model || "model noma'lum"} · ${c.reasons.length ? c.reasons.join("; ") : "ishlayapti"}`;
  return c.level === "yashil" ? `<i class="cm-dot g" title="${esc(t)}" aria-hidden="true"></i>`
    : `<button type="button" class="cm-dot ${cls}" data-cam="${c.id}" title="${esc(t)}" aria-label="${esc(txt + ": " + t)}">${glyph}</button>`;
}
function cmHolat(b) {
  const h = CM.h, L = h.levels;
  const kp = [["Onlayn", `${h.online_pct}%`, `${fmt(h.online)} / ${fmt(h.total)} kamera ishlayapti`, h.online_pct >= 98 ? "good" : h.online_pct < 90 ? "bad" : "warn", "cctv"],
    ["Oflayn", h.offline, `${h.offline_after_min} daqiqadan ortiq javob yo'q`, h.offline ? "bad" : "", "wifioff"],
    ["To'sib qo'yilgan", h.blocked, "obyektiv yopilgan yoki tasvir yo'q", h.blocked ? "bad" : "", "eyeoff"],
    ["Soat farqi", h.skew, "60 s dan ortiq — NTP sozlansin", h.skew ? "warn" : "", "clock"],
    ["Eski proshivka", h.old_fw, "2021-sentabrdan eski (CVE-2021-36260)", h.old_fw ? "warn" : "", "cpu"]];
  let s = `<div class="cm-kpis">${kp.map(([l, v, sub, c, i]) => `<div class="card kpi cm-kpi ${c}"><div class="l">${ico(i, 16)}<span>${l}</span></div><div class="v">${v}</div><div class="s">${sub}</div></div>`).join("")}</div>`;
  /* bino × qavat xaritasi */
  const lg = Object.entries(CM_LV).map(([k, [c, t, g]]) => `<span><i class="cm-dot ${c}" aria-hidden="true">${g}</i>${t} <b>${fmt(L[k] || 0)}</b></span>`).join("");
  s += `<div class="card cm-map"><div class="head cm-ch"><h3>${ico("building", 18)}Binolar va qavatlar bo'yicha</h3><div class="cm-lg">${lg}</div></div>
    <div class="cm-lv" role="img" aria-label="Kameralar: ${L.yashil} ishlayapti, ${L.sariq} e'tibor kerak, ${L.qizil} nosoz">${["yashil", "sariq", "qizil"].map(k => L[k] ? `<i class="${CM_LV[k][0]}" style="flex:${L[k]}"></i>` : "").join("")}</div>
    <div class="cm-blds">${h.buildings.map(bd => {
      const n = bd.floors.reduce((a, f) => a + f.cams.length, 0), bl = bd.levels;
      return `<section class="cm-b" aria-label="${esc(bd.building)}"><div class="cm-bh"><b>${esc(bd.building)}</b><span>${n} kamera${bl.qizil ? ` · <em class="r">${bl.qizil} nosoz</em>` : ""}${bl.sariq ? ` · <em class="y">${bl.sariq} e'tibor</em>` : ""}</span></div>
        ${[...bd.floors].reverse().map(f => { const fl = f.levels || {};
          return `<div class="cm-fl" role="group" aria-label="${esc(bd.building)}, ${esc(f.label)}: ${f.cams.length} kamera${fl.qizil ? `, ${fl.qizil} nosoz` : ""}${fl.sariq ? `, ${fl.sariq} e'tibor kerak` : ""}"><span class="cm-fll">${esc(f.label)}</span><div class="cm-dots">${f.cams.map(cmDot).join("")}</div></div>`; }).join("")}</section>`;
    }).join("")}</div>
    <p class="tiny muted cm-note">Rangli nuqta — bitta kamera. Sariq yoki qizil nuqtani bosing: muammo jadvalda ajratiladi. Kamera ${h.offline_after_min} daqiqa javob bermasa — nosozlik tiketi avtomatik ochiladi.</p></div>`;
  /* muammolar jadvali */
  const pr = h.problems;
  s += `<div class="card cm-prob"><div class="head cm-ch"><h3>${ico("alert", 18)}Muammoli kameralar <span class="cm-cnt">${pr.length}</span></h3><span class="tiny muted">avval nosozlari, keyin e'tibor talab qiladiganlari</span></div>`;
  s += pr.length ? `<div class="tw"><table class="cm-ptbl"><thead><tr><th><span class="sr">Daraja</span></th><th>Joy</th><th>Muammo</th><th>Model · proshivka</th><th>Oxirgi signal</th><th>Tiket</th></tr></thead><tbody>${pr.map(c => {
      const [cls, txt, g] = CM_LV[c.level] || CM_LV.sariq, off = c.reasons.some(r => r.startsWith("Javob bermayapti"));
      return `<tr id="cmp-${c.id}" class="lv-${cls}"><td><span class="cm-dot ${cls}" aria-hidden="true">${g}</span><span class="sr">${txt}</span></td>
        <td><b class="nowrap">${esc(c.room)}</b><br><span class="tiny muted nowrap">${c.zone ? "" : `${esc(c.building)}, ${c.floor}-qavat · `}${esc(c.ip || "")}</span></td>
        <td>${c.reasons.map((r, i) => `<div class="${i === 0 ? (cls === "r" ? "bad" : "warn-t") : "tiny"}">${esc(r)}</div>`).join("")}</td>
        <td><span class="nowrap">${esc(c.model || "—")}</span><br><span class="tiny muted">${esc(c.family || "")}${c.fw ? ` · ${esc(c.fw)}` : ""}${c.fw_age != null ? ` (${c.fw_age} yil)` : ""}${c.thermal ? " · termal" : ""}</span></td>
        <td class="nowrap ${off ? "bad" : ""}">${c.heartbeat ? cmAge(c.age_s) : `<span class="muted">hali yo'q</span>`}</td>
        <td class="nowrap">${c.ticket ? `<b>#${c.ticket.id}</b> <span class="tiny muted">${esc(c.ticket.status)}</span>${c.ticket.overdue ? `<br><span class="tag high">${ico("clock", 13)}muddati o'tgan</span>` : ""}` : `<span class="muted">—</span>`}</td></tr>`;
    }).join("")}</tbody></table></div>`
    : `<div class="cm-empty">${ico("checkc", 26)}<b>Barcha kameralar ishlayapti</b><span>Nosoz yoki e'tibor talab qiladigan kamera yo'q.</span></div>`;
  s += `</div>`;
  /* modellar va imkoniyatlar */
  s += `<div class="card cm-models"><div class="head cm-ch"><h3>${ico("cpu", 18)}Modellar va imkoniyatlar</h3></div>
    ${tbl(["Model", "Turi", "#Soni", "Odam sanash", "Imkoniyatlar"], h.models.map(m => [`<b class="nowrap">${esc(m.model)}</b>`, esc(m.family || "—"), fmt(m.n),
      `<span class="${/^yo'q/.test(m.counting) ? "muted" : ""}">${esc(m.counting || "—")}</span>`,
      `<div class="cm-caps">${[...new Set(m.caps || [])].map(c => `<span>${esc(c)}</span>`).join("")}</div>`]))}
    <p class="tiny muted cm-note">${ico("info", 14)} Imkoniyatlar taxminiy — AT bo'limi model ro'yxati bilan tasdiqlaydi. Odam sanash — faqat raqam; shaxs aniqlanmaydi.</p></div>`;
  b.innerHTML = s;
  b.querySelectorAll("button[data-cam]").forEach(x => x.onclick = () => {
    const r = document.getElementById("cmp-" + x.dataset.cam); if (!r) return;
    b.querySelectorAll("tr.flash").forEach(t => t.classList.remove("flash"));
    r.classList.add("flash"); r.scrollIntoView({behavior: "smooth", block: "center"});
    setTimeout(() => r.classList.remove("flash"), 2600);
  });
}

/* =====================================================================
   b) Voqealar — ustuvorlik, marshrut, takrorlarni birlashtirish, belgilash
   ===================================================================== */
function cmVoqealar(b) {
  const E = CM.e, st = E.stats, bp = st.by_priority, PL = E.prio_label || {}, SL = E.status_label || {}, GL = E.group_label || {};
  const pl = p => String(PL[p] || "P" + p).replace(/^P\d\s*—\s*/, "");
  let s = `<div class="cm-stats" aria-label="Voqealar statistikasi">${[1, 2, 3, 4].map(p => `<span class="cm-stat ${CM_PRIO_CLS[p]}">${cmPrio(p, PL[p])}<b>${fmt(bp[p] || 0)}</b><small>${esc(pl(p))}</small></span>`).join("")}
    <span class="cm-stat${st.open ? " warn" : ""}"><b>${fmt(st.open)}</b><small>ochiq</small></span>
    <span class="cm-stat" title="P1–P3 dan ko'rib chiqilganlari ichida"><b>${st.false_rate}%</b><small>noto'g'ri signal (${st.false})</small></span>
    <span class="cm-stat"><b>${fmt(st.tickets)}</b><small>tiketga aylangan</small></span>
    <span class="cm-stat" title="${Math.round((E.dedup_sec || 300) / 60)} daqiqa ichidagi bir xil signallar bitta voqeaga birlashtirildi"><b>${fmt(st.merged)}</b><small>birlashtirilgan takror</small></span>
    <span class="cm-stat"><b>${fmt(st.night)}</b><small>tunda</small></span></div>`;
  const seg = (name, cur, opts) => `<div class="cm-seg" role="group" aria-label="${name}">${opts.map(([v, l]) => `<button type="button" data-f="${name}" data-v="${v}" aria-pressed="${String(cur) === String(v)}" class="${String(cur) === String(v) ? "on" : ""}">${l}</button>`).join("")}</div>`;
  s += `<div class="card cm-fbar"><div class="cm-fg"><span class="cm-fl2">Davr</span>${seg("days", CM.days, [[1, "1 kun"], [7, "7 kun"], [30, "30 kun"]])}</div>
    <div class="cm-fg"><span class="cm-fl2">Ustuvorlik</span>${seg("prio", CM.prio, [[1, "P1"], [2, "P1–P2"], [3, "P1–P3"], [0, "Hammasi"]])}</div>
    <div class="cm-fg cm-fsel"><label><span class="cm-fl2">Holat</span><select id="cmSt" aria-label="Holat bo'yicha saralash"><option value="">Barcha holatlar</option>${Object.entries(SL).map(([k, v]) => `<option value="${esc(k)}"${CM.status === k ? " selected" : ""}>${esc(v)}</option>`).join("")}</select></label>
      <label><span class="cm-fl2">Guruh</span><select id="cmGr" aria-label="Guruh bo'yicha saralash"><option value="">Barcha guruhlar</option>${Object.entries(GL).map(([k, v]) => `<option value="${esc(k)}"${CM.group === k ? " selected" : ""}>${esc(v)}</option>`).join("")}</select></label></div></div>`;
  const evs = E.events, shown = evs.slice(0, CM.show);
  const list = evs.length ? shown.map(e => cmEv(e, E)).join("") + (evs.length > CM.show ? `<button class="btn ghost sm cm-more" id="cmMore">Yana ${Math.min(25, evs.length - CM.show)} ta ko'rsatish <span class="muted">(${evs.length - CM.show} qoldi)</span></button>` : "")
    : `<div class="cm-empty">${ico("checkc", 26)}<b>Voqea yo'q</b><span>Tanlangan davr va filtr bo'yicha voqea topilmadi.</span>${CM.status || CM.group || CM.prio !== 3 || CM.days !== 7 ? `<button class="btn sm" id="cmReset">Filtrni tiklash</button>` : ""}</div>`;
  const byB = Object.entries(st.by_building || {}).sort((a, b) => b[1] - a[1]);
  s += `<div class="cm-evwrap"><section class="card cm-evlist" aria-label="Voqealar ro'yxati"><div class="head cm-ch"><h3>${ico("bolt", 18)}Voqealar <span class="cm-cnt">${evs.length}</span></h3>
      <span class="tiny muted">${E.manage_groups ? "Siz kamera texnik holati voqealarini (to'sish, tasvir yo'qolishi, siljish) belgilaysiz; xavfsizlik voqealari — xo'jalik bo'limi va rektor" : E.can_manage ? "Belgilash statistikani aniqlashtiradi: noto'g'ri signallar ulushi kuzatiladi" : "Faqat ko'rish — belgilashni xo'jalik bo'limi va rektor bajaradi"}</span></div>
      <div class="cm-evs" id="cmEvs">${list}</div></section>
    <aside class="card cm-evside"><h3>${ico("chart", 18)}Turlar bo'yicha</h3>${st.by_kind.length ? bars(st.by_kind, {label: r => r.label, value: r => r.n, top: 6}) : `<p class="muted tiny">Ma'lumot yo'q</p>`}
      <h3 class="cm-h2">${ico("building", 18)}Binolar bo'yicha <span class="tiny muted">P1–P3</span></h3>${byB.length ? bars(byB, {label: r => r[0], value: r => r[1], alt: true}) : `<p class="muted tiny">Ma'lumot yo'q</p>`}
      <p class="tiny muted cm-note">${ico("info", 14)} Bir xil voqea ${Math.round((E.dedup_sec || 300) / 60)} daqiqa ichida takrorlansa — bitta yozuvga birlashtiriladi. Voqea kimga yuborilishi uning turi va vaqtiga (kun / tun) qarab avtomatik belgilanadi.</p></aside></div>`;
  b.innerHTML = s;
  b.querySelectorAll("[data-f]").forEach(x => x.onclick = () => cmFilter(x.dataset.f, +x.dataset.v));
  $("#cmSt").onchange = ev => cmFilter("status", ev.target.value);
  $("#cmGr").onchange = ev => cmFilter("group", ev.target.value);
  const more = $("#cmMore"); if (more) more.onclick = () => { CM.show += 25; cmBody(); };
  const rs = $("#cmReset"); if (rs) rs.onclick = () => { Object.assign(CM, {days: 7, prio: 3, status: "", group: ""}); cmFilter(); };
  b.querySelectorAll("[data-ea]").forEach(x => x.onclick = () => cmAct(x));
}
function cmEv(e, E) {
  const SL = E.status_label || {}, closed = ["yopildi", "notogri", "qayd"].includes(e.status);
  const day = e.ts.slice(0, 10), t2 = e.last_ts && e.last_ts !== e.ts ? (e.last_ts.slice(0, 10) === day ? e.last_ts.slice(11, 16) : whenTxt(e.last_ts)) : "";
  const acts = E.can_manage && (!E.manage_groups || E.manage_groups.includes(e.group)) ? (CM_NEXT[e.status] || []) : [];   /* AT bo'limi — faqat kamera texnik holati */
  return `<article class="cm-ev ${CM_PRIO_CLS[e.priority] || "p4"}${closed ? " done" : ""}" id="cme-${e.id}" tabindex="-1">
    ${cmPrio(e.priority, (E.prio_label || {})[e.priority])}
    <div class="cm-ev-b">
      <div class="cm-ev-t"><b>${esc(e.label)}</b>${e.dup ? `<span class="cm-dup" title="${Math.round((E.dedup_sec || 300) / 60)} daqiqa ichidagi ${e.dup} ta takror signal birlashtirildi">×${e.dup} takror</span>` : ""}${e.night ? `<span class="cm-night">${ico("moon", 12)}tun</span>` : ""}</div>
      ${e.note && e.note !== e.label ? `<p class="cm-ev-n">${esc(e.note)}</p>` : ""}
      <div class="cm-ev-m"><span>${ico("pin", 13)}${esc(e.room)}${e.zone || !e.building ? "" : `, ${esc(e.building)}`}</span><span>${ico("clock", 13)}<time datetime="${esc(e.ts)}">${whenTxt(e.ts)}${t2 ? `–${t2}` : ""}</time></span>
        ${e.route_titles?.length ? `<span>${ico("route", 13)}Kimga: ${e.route_titles.map(esc).join(", ")}</span>` : ""}${e.ticket_id ? `<span>${ico("wrench", 13)}Tiket #${e.ticket_id}</span>` : ""}
        ${e.handled_by && e.status !== "yangi" ? `<span>${ico("checkc", 13)}${esc(e.handled_by)} · ${whenTxt(e.handled_at)}</span>` : ""}</div>
      ${acts.length ? `<div class="cm-acts">${acts.map(a => `<button type="button" class="btn sm ${a === "yopildi" ? "" : "ghost"}" data-ea="${a}" data-eid="${e.id}" aria-label="${esc(CM_ACT[a][0])}: ${esc(e.label)}, ${esc(e.room)}">${ico(CM_ACT[a][1], 14)}${CM_ACT[a][0]}</button>`).join("")}</div>` : ""}
    </div>
    <span class="cm-s ${CM_ST_CLS[e.status] || ""}">${esc(SL[e.status] || e.status)}</span>
  </article>`;
}
async function cmFilter(k, v) {
  if (k) CM[k] = v;
  CM.show = 25;
  const evs = $("#cmEvs"); if (evs) evs.setAttribute("aria-busy", "true"), evs.style.opacity = ".55";
  try { CM.e = await cmLoadEv(); CM.err.e = null; } catch (e) { if (e?.message === "auth") return; CM.e = null; CM.err.e = e?.message; }
  cmCounts(); cmBody();
  const f = k && document.querySelector(`#v-cams [data-f="${k}"][data-v="${v}"]`) || (k === "status" ? $("#cmSt") : k === "group" ? $("#cmGr") : null);
  f?.focus({preventScroll: true});
}
async function cmAct(btn) {
  const id = btn.dataset.eid, a = btn.dataset.ea, row = btn.closest(".cm-ev");
  if (!row || row.getAttribute("aria-busy") === "true") return;
  const btns = [...row.querySelectorAll("button")], old = btn.innerHTML;
  const restore = () => { row.removeAttribute("aria-busy"); btns.forEach(x => x.disabled = false); btn.innerHTML = old; };
  row.setAttribute("aria-busy", "true"); btns.forEach(x => x.disabled = true); btn.innerHTML = "…";
  try {
    const r = await fetch(`/api/cams/events/${id}/${a}`, {method: "POST", credentials: "same-origin", headers: {"Content-Type": "application/json"}, body: JSON.stringify({note: ""})});
    if (r.status === 401) { showLogin(); return; }
    const j = await r.json().catch(() => ({}));
    if (r.status === 403) { restore(); return toast(cmMsg(j.message) || "Bu amal uchun ruxsat yo'q"); }
    if (!r.ok) throw new Error("http");
    toast({korildi: "Ko'rildi deb belgilandi", notogri: "Noto'g'ri signal deb belgilandi — statistika yangilandi", tiket: `Tiket #${j.ticket_id || ""} ochildi — xo'jalik bo'limiga`, yopildi: "Voqea yopildi"}[a]);
    CM.e = await cmLoadEv(); cmCounts(); cmBody();
    (document.getElementById("cme-" + id) || $("#cmEvs"))?.focus({preventScroll: true});
  } catch (e) { if (e?.message !== "auth") { restore(); toast("Xatolik yuz berdi — qayta urinib ko'ring"); } }
}

/* =====================================================================
   c) Navbat va olomon
   ===================================================================== */
const CM_ZICO = {qabul: "users", kassa: "money", oshxona: "utensils"};
function cmToday(z) {
  const S = z.today || [];
  if (!S.length) return `<p class="tiny muted cm-nodata">Bugun hali o'lchov yo'q (ish vaqti 09:00 dan).</p>`;
  const W = 360, H = 76, t0 = 9 * 60, t1 = 18 * 60, mx = Math.max(z.limit * 1.25, ...S.map(s => s.n), 1), bw = W / ((t1 - t0) / 15) - 2;
  const y = v => H - (v / mx) * (H - 4), ly = y(z.limit).toFixed(1), peak = Math.max(...S.map(s => s.n));
  const bs = S.map(s => { const m = +s.ts.slice(11, 13) * 60 + +s.ts.slice(14, 16), x = (m - t0) / (t1 - t0) * W, hh = H - y(s.n);
    return `<rect x="${(x + 1).toFixed(1)}" y="${y(s.n).toFixed(1)}" width="${bw.toFixed(1)}" height="${Math.max(1, hh).toFixed(1)}" rx="1.5" class="${s.n > z.limit ? "over" : ""}"><title>${s.ts.slice(11, 16)} — ${s.n} kishi, ~${Math.round(s.wait || 0)} daq.</title></rect>`; }).join("");
  return `<div class="cm-today"><div class="cm-sub">Bugun, har 15 daqiqada <span class="muted">· eng ko'p ${peak} kishi</span></div>
    <svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" role="img" aria-label="Bugungi navbat: eng ko'p ${peak} kishi, chegara ${z.limit}">${bs}<line x1="0" x2="${W}" y1="${ly}" y2="${ly}" class="lim"/></svg>
    <div class="cm-ax"><span>09:00</span><span>12:00</span><span>15:00</span><span>18:00</span></div>
    <div class="cm-axl"><i class="lim"></i>chegara ${z.limit} kishi</div></div>`;
}
function cmHeat(z) {
  const all = z.heat.flat().filter(v => v != null), mx = Math.max(z.limit * 1.4, ...all, 1);
  const cell = v => { if (v == null) return `<td class="na">—</td>`; const a = Math.round(12 + 70 * Math.min(1, v / mx)), over = v > z.limit;
    return `<td class="${over ? "over" : ""}${a >= 50 ? " hi" : ""}" style="--a:${a}%" title="${Math.round(v * 10) / 10} kishi${over ? " — chegaradan oshgan" : ""}">${Math.round(v)}</td>`; };
  return `<div class="cm-sub">O'rtacha navbat: hafta kuni × soat <span class="muted">· 4 hafta</span></div>
    <div class="tw cm-heatw"><table class="cm-heat"><thead><tr><th><span class="sr">Kun</span></th>${z.hours.map(hh => `<th>${hh}</th>`).join("")}</tr></thead>
    <tbody>${z.heat.map((row, i) => `<tr><th title="${esc(z.days[i])}">${cmDay2(z.days[i])}</th>${row.map(cell).join("")}</tr>`).join("")}</tbody></table></div>`;
}
function cmZone(z) {
  const n = z.now?.n, over = n != null && n > z.limit, w = z.now?.wait;
  return `<section class="card cm-zone${over ? " over" : ""}" aria-label="${esc(z.name)} navbati">
    <div class="cm-zh"><span class="cm-zic">${ico(CM_ZICO[z.zone] || "users", 18)}</span><div><h3>${esc(z.name)}</h3><span class="tiny muted">${esc(z.room)}</span></div>
      <span class="tag ${over ? "high" : n == null ? "gray" : "low"}">${over ? "Chegaradan oshgan" : n == null ? "Ma'lumot yo'q" : "Me'yorda"}</span></div>
    <div class="cm-znow"><div><b class="${over ? "bad" : ""}">${n ?? "—"}</b><span>kishi navbatda</span></div><div><b class="${over ? "bad" : ""}">${w != null ? "~" + Math.round(w) : "—"}</b><span>daqiqa kutish</span></div>
      <div class="cm-zlim"><span>chegara <b>${z.limit}</b> kishi</span>${z.now ? `<span class="tiny muted">${whenTxt(z.now.ts)}</span>` : ""}</div></div>
    ${cmToday(z)}${cmHeat(z)}
    ${z.pattern.length ? `<ul class="cm-pat" aria-label="Takrorlanadigan holatlar">${z.pattern.map(p => `<li>${ico("alert", 14)}<span><b>${esc(p.day)} ${esc(p.from)}–${esc(p.to)}</b> — o'rtacha ${p.avg} kishi <span class="muted">(chegara ${z.limit})</span></span></li>`).join("")}</ul>`
      : `<p class="cm-pat ok">${ico("checkc", 14)}<span>Muntazam chegaradan oshish kuzatilmadi</span></p>`}
    <p class="tiny muted cm-zf">4 haftada chegaradan oshgan kunlar: <b>${z.breach_days}</b> · eng ko'p: <b>${z.peak}</b> kishi · mas'ul: ${esc(z.unit)}</p></section>`;
}
function cmCrowd(c) {
  const top = Math.max(130, c.max_pct + 8), y = p => (100 * p / top).toFixed(1);
  const cols = c.days.map(d => `<div class="cm-cc" title="${dmy(d.date)}: ${d.peak} kishi / ${c.capacity} o'rin (${d.pct}%)"><span class="cm-cv ${d.pct > 110 ? "bad" : ""}">${d.pct}%</span>
    <div class="cm-cb"><i class="${d.pct > 110 ? "bad" : d.pct > 100 ? "warn" : ""}" style="height:${y(d.pct)}%"></i></div><span class="cm-cl">${d.date.slice(8, 10)}<span class="cm-mo">.${d.date.slice(5, 7)}</span><small>${cmWd(d.date)}</small></span></div>`).join("");
  return `<section class="card cm-crowd"><div class="head cm-ch"><h3>${ico("utensils", 18)}Oshxona: tushlikdagi olomon</h3><span class="tiny muted">${esc(c.room)} · sig'im ${c.capacity} · 12:50–13:30 eng ko'p</span></div>
    <p class="cm-ctext ${c.over_days ? "bad" : "good"}">${ico(c.over_days ? "alert" : "checkc", 16)}<span>${esc(c.text)}</span></p>
    ${c.days.length ? `<div class="cm-cchart" role="img" aria-label="${esc(c.text)}"><div class="cm-cgrid"><i class="l110" style="bottom:${y(110)}%"><span>110%</span></i><i class="l100" style="bottom:${y(100)}%"></i></div>${cols}</div><div class="cm-clg"><span><i class="l100"></i>100% — sig'im</span><span><i class="l110"></i>110% — chegara (olomon)</span></div>` : `<p class="muted tiny">Ma'lumot yo'q</p>`}
    <p class="tiny muted cm-note">Tavsiya: tushlik vaqtini kurslar bo'yicha 15–20 daqiqaga surish yoki qo'shimcha tarqatish nuqtasi ochish.</p></section>`;
}
function cmHall(hl) {
  const rows = hl.events.map(e => [`<span class="cm-tt">${esc(e.title)}</span><span class="cm-dm">${dmy(e.date)}</span>`, `<span class="nowrap">${dmy(e.date)}</span>`, e.checkin ? fmt(e.checkin) : `<span class="muted">0</span>`,
    e.camera_peak != null ? fmt(e.camera_peak) : `<span class="muted" title="Shu kuni zal kamerasidan o'lchov yo'q">—</span>`,
    e.fill_pct != null ? `<span class="nowrap"><span class="cm-fill"><i style="width:${Math.min(100, e.fill_pct)}%" class="${e.fill_pct > 100 ? "bad" : ""}"></i></span><span class="nowrap ${e.fill_pct > 100 ? "bad" : ""}">${e.fill_pct}%</span></span>` : `<span class="muted">—</span>`,
    e.gap != null ? `<span class="${e.gap > 20 ? "warn-t" : e.gap < -20 ? "bad" : ""}" title="${e.gap > 0 ? "ro'yxatdan o'tmay kelganlar" : "ro'yxatdan o'tib kelmaganlar"}">${e.gap > 0 ? "+" : ""}${e.gap}</span>` : `<span class="muted">—</span>`]);
  return `<section class="card cm-hall"><div class="head cm-ch"><h3>${ico("hall", 18)}Tadbirlar zali: ro'yxat va kamera</h3><span class="tiny muted">${esc(hl.room)} · sig'im ${fmt(hl.capacity)} · 45 kun</span></div>
    ${tbl(["Tadbir", "Sana", "#Ro'yxatdan o'tgan", "#Kamera: eng ko'p", "#Zal to'lishi", "#Farq"], rows, {top: 8})}
    <p class="tiny muted cm-note">Farq = kamera sanagan eng ko'p odam − ro'yxatdan o'tganlar. Katta musbat farq — ko'pchilik ro'yxatdan o'tmay kelgan; manfiy — ro'yxatdan o'tib kelmaganlar.</p></section>`;
}
function cmNavbat(b) {
  const q = CM.q, full = ME.allow.includes("spaces");
  let s = !full ? `<p class="cm-scope">${ico("info", 15)}<span>Siz faqat o'z bo'limingiz navbatini ko'rasiz. Kamera faqat navbatdagi odamlar sonini sanaydi — kim turgani aniqlanmaydi.</span></p>` : "";
  s += q.zones.length ? `<div class="cm-zones">${q.zones.map(cmZone).join("")}</div>` : `<div class="card cm-empty">${ico("users", 26)}<b>Navbat zonasi yo'q</b><span>Lavozimingizga biriktirilgan navbat zonasi topilmadi.</span></div>`;
  if (q.crowd || q.hall) s += `<div class="cm-cw">${q.crowd ? cmCrowd(q.crowd) : ""}${q.hall ? cmHall(q.hall) : ""}</div>`;
  b.innerHTML = s;
}

/* =====================================================================
   Auditoriyalar bandligi sahifasi uchun qo'shimcha kartalar (app.js renderSpaces chaqiradi)
   ===================================================================== */
function spcExtraHtml(o) {
  if (!o || !o.hourly) return "";
  const idle = o.idle_rooms || [], un = o.unsched || [], peaks = new Set((o.peak_hours || []).map(p => p.hour));
  const idleH = idle.length ? `<ul class="cm-idle">${idle.map(r => `<li><div class="cm-idle-h"><a href="#" data-room="${r.id}"><b>${esc(r.name)}</b></a><span class="tiny muted">${esc(r.building)} · ${r.capacity} o'rin</span>
      <span class="tag high">${r.empty}/${r.scheduled} para bo'sh</span></div><p>${esc(r.advice)}</p></li>`).join("")}</ul>`
    : `<div class="cm-empty sm">${ico("checkc", 22)}<b>Optimallashtirish kerak emas</b><span>Jadvaldagi barcha xonalarda darslar o'tmoqda.</span></div>`;
  const unH = un.length ? tbl(["Sana", "Para", "Xona", "#Kishi / sig'im"], un.map(u => [`${cmDM(u.date)} <span class="tiny muted">${esc(cmDay2(u.day))}</span>`, `${u.slot}-para`, `<b class="nowrap">${esc(u.room)}</b>`, `<span class="nowrap"><b class="${u.avg > u.capacity ? "bad" : ""}">${u.avg}</b> <span class="muted">/ ${u.capacity}</span></span>`]), {top: 8})
      + `<p class="tiny muted">Jadvalda dars yo'q, lekin xonada o'rtacha ${o.unsched_min || 20}+ kishi: qo'shimcha mashg'ulot, to'garak yoki jadvalga kiritilmagan dars. Akademik faoliyatni boshqarish bo'limi jadvalni tekshiradi.</p>`
    : `<p class="muted">Holat yo'q</p>`;
  const hmx = Math.max(...o.hourly.map(x => x.pct), 1);
  const hourly = `<div class="cm-hcols" role="img" aria-label="Soatlar bo'yicha o'rtacha bandlik; eng band: ${[...peaks].join(", ")}">${o.hourly.map(x => `<div class="cm-hc${peaks.has(x.hour) ? " pk" : ""}" title="${x.hour}: o'rtacha ${fmt(x.people)} kishi (${x.pct}% sig'im)">
      <span class="cm-hv">${Math.round(x.pct)}%</span><div class="cm-hb"><i style="height:${(100 * x.pct / hmx).toFixed(1)}%"></i></div><span class="cm-hl">${x.hour.slice(0, 2)}</span></div>`).join("")}</div>
    <p class="tiny muted">Ustun — barcha xonalardagi o'rtacha odamlar soni ÷ umumiy sig'im, so'nggi 4 hafta. To'q rang — eng band soatlar: ${(o.peak_hours || []).map(p => `<b>${esc(p.hour)}</b>`).join(", ")}.</p>`;
  const wk = bars(o.weekday || [], {label: r => r.day, value: r => r.pct, max: Math.max(...(o.weekday || []).map(r => r.pct), 1), fmtv: (v, r) => `${v}%`});
  const bn = bars(o.buildings_now || [], {label: r => r.building, value: r => r.pct, max: 100, alt: true, fmtv: (v, r) => `<span title="${fmt(r.people)} kishi / ${fmt(r.capacity)} o'rin">${v}%</span>`});
  return `<div class="grid g2" style="margin-top:14px">
      ${card(`${ico("refresh", 18)}Xonalarni optimallashtirish <span class="muted tiny">— 2 hafta: jadvalda dars bor, kamera xonani deyarli bo'sh ko'rgan</span>`, idleH)}
      ${card(`<span class="warn-t ic-t">${ico("users", 18)}</span>Dars yo'q — xonada ${o.unsched_min || 20}+ kishi <span class="muted tiny">— so'nggi 2 hafta</span>`, unH)}</div>
    <div class="grid cm-prof" style="margin-top:14px">
      ${card(`${ico("clock", 18)}Eng band soatlar`, hourly)}
      ${card(`${ico("calendar", 18)}Hafta kunlari`, wk + `<p class="tiny muted">O'rtacha to'lish, dars vaqtida.</p>`)}
      ${card(`${ico("building", 18)}Binolar hozir`, bn + `<p class="tiny muted">Hozirgi odamlar soni ÷ binodagi auditoriyalar sig'imi.</p>`)}</div>`;
}
