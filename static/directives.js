"use strict";
/* ---------- Ierarxik topshiriqlar (majlisdan tashqari) — «Majlislar va topshiriqlar» sahifasida ----------
   Vakolat, ko'rinish va barcha tekshiruvlar serverda (app/directives.py); bu yerda faqat ko'rsatish.
   app.js: renderTasks() → dirSection() / renderDirective(); queueCard() — «Ochish» → openDirective(). */
if (!document.querySelector('link[href="directives.css"]')) document.head.insertAdjacentHTML("beforeend", '<link rel="stylesheet" href="directives.css">');

const DIR = {open: null, flt: "all", list: null, timer: null, sig: ""};
const DIR_PRIO = {oddiy: ["Oddiy", "gray"], muhim: ["Muhim", "mid"], shoshilinch: ["Shoshilinch", "high"]};
const DIR_FLT = [["all", "Hammasi"], ["open", "Ochiq"], ["overdue", "Muddati o'tgan"], ["review", "Qabulimni kutmoqda"], ["done", "Yakunlangan"]];
const dirPlus = `<svg class="i" viewBox="0 0 24 24" width="16" height="16" aria-hidden="true"><path d="M12 5v14M5 12h14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>`;

function openDirective(id) { if (typeof DEC !== "undefined") DEC.open = null; DIR.open = +id; DIR.sig = ""; go("tasks"); }
function closeDirective() { DIR.open = null; clearInterval(DIR.timer); go("tasks"); }

/* holat yorlig'i: muddati o'tgan / qabul kutilmoqda / qaytarildi / holat */
function dirTag(n) {
  if (n.status === "bajarildi" && n.review === "kutilmoqda") return `<span class="tag mid">Natija qabul kutmoqda</span>`;
  if (n.status === "bajarildi") return `<span class="tag low">Bajarildi${n.review === "qabul" ? " · qabul qilindi" : ""}</span>`;
  const t = n.overdue ? `<span class="tag high">Muddati o'tgan</span>` : `<span class="tag ${n.status === "jarayonda" ? "mid" : "gray"}">${n.status === "jarayonda" ? "Jarayonda" : "Yangi"}</span>`;
  return t + (n.review === "qaytarildi" ? ` <span class="tag high">Qayta ishlashga qaytarildi</span>` : "");
}
const dirPrio = p => p && p !== "oddiy" ? `<span class="tag ${DIR_PRIO[p][1]}">${DIR_PRIO[p][0]}</span>` : "";
const dirWho = n => n.assignee_name ? `${esc(n.unit_name || "")} → <b>${esc(n.assignee_name)}</b>` : `<b>${esc(n.unit_name || "")}</b> <span class="unsaid">xodim biriktirilmagan</span>`;
const dirProg = n => n.progress.total ? `<span class="dir-prog" title="Quyi topshiriqlar: ${n.progress.done}/${n.progress.total} bajarildi"><i style="width:${Math.round(100 * n.progress.done / n.progress.total)}%"></i></span><span class="tiny muted">${n.progress.done}/${n.progress.total} bajarildi</span>` : "";

/* --- ro'yxat kartasi: «Men bergan topshiriqlar» + «Qabulimni kutmoqda» --- */
async function dirSection() {
  let L;
  try { L = await J(`/api/dir/list?flt=${DIR.flt}`); } catch (e) { return ""; }
  DIR.list = L;
  const c = L.counts;
  if (!L.can_issue && !c.given && !c.review) return "";
  const rows = DIR.flt === "review" ? L.review : L.given;
  return `<div class="card dir-card" style="margin-top:14px">
    <div class="dir-h"><h3>${ico("tasks")} Men bergan topshiriqlar <span class="tag ${c.overdue ? "high" : "gray"}">${c.given} ta${c.overdue ? ` · ${c.overdue} muddati o'tgan` : ""}</span></h3>
      ${L.can_issue ? `<button class="btn primary sm" id="dirNew">${dirPlus} Yangi topshiriq</button>` : ""}</div>
    ${c.review ? `<button class="dir-alert" data-dflt="review">${ico("check", 16)} <span><b>${c.review} ta natija</b> qabulingizni kutmoqda — qabul qiling yoki izoh bilan qaytaring</span></button>` : ""}
    <div class="dir-flt" role="group" aria-label="Filtr">${DIR_FLT.map(([k, l]) => `<button class="chip ${DIR.flt === k ? "on" : ""}" data-dflt="${k}" aria-pressed="${DIR.flt === k}">${l}${k === "review" && c.review ? ` <b>${c.review}</b>` : ""}</button>`).join("")}</div>
    ${rows.length ? `<div class="dir-list">${rows.map(dirRow).join("")}</div>` : `<p class="muted" style="margin:6px 0 0">${DIR.flt === "all" ? "Hali topshiriq bermagansiz." : "Bu filtr bo'yicha topshiriq yo'q."}</p>`}
  </div>`;
}
function dirRow(n) {
  return `<button class="dir-row ${n.overdue ? "late" : ""}" data-dopen="${n.id}">
    <span class="dir-row-t"><b>${esc(n.title)}</b><span class="tiny muted">${dirWho(n)}${n.parent_id ? " · taqsimlangan" : ""}</span></span>
    <span class="dir-row-m">${dirPrio(n.priority)}${dirTag(n)}<span class="tiny ${n.overdue ? "bad" : "muted"}">${n.due ? "muddat " + dtm(n.due) : ""}</span>${dirProg(n)}</span></button>`;
}
function dirBind(root) {
  root.querySelectorAll("[data-dflt]").forEach(b => b.onclick = () => { DIR.flt = b.dataset.dflt; renderTasks(); });
  root.querySelectorAll("[data-dopen]").forEach(b => b.onclick = () => openDirective(+b.dataset.dopen));
  const nb = root.querySelector("#dirNew"); if (nb) nb.onclick = () => dirNewDialog();
}

/* --- oddiy modal oyna (Esc / tashqariga bosish — yopadi) --- */
function dirModal(title, html, onOpen) {
  dirClose();
  const opener = document.activeElement;
  const ov = document.createElement("div"); ov.className = "dir-ov"; ov.id = "dirOv";
  ov.innerHTML = `<div class="dir-dlg" role="dialog" aria-modal="true" aria-labelledby="dirDlgT"><div class="dir-dlg-h"><h3 id="dirDlgT">${esc(title)}</h3>
    <button class="btn ghost sm" data-dclose aria-label="Yopish">${ico("x", 16)}</button></div><div class="dir-dlg-b">${html}</div></div>`;
  document.body.appendChild(ov); document.documentElement.classList.add("dir-lock");
  ov.addEventListener("mousedown", e => { if (e.target === ov) dirClose(); });
  ov.addEventListener("keydown", e => { if (e.key === "Escape") { e.preventDefault(); dirClose(); } });
  ov.querySelectorAll("[data-dclose]").forEach(b => b.onclick = () => dirClose());
  ov._opener = opener;
  requestAnimationFrame(() => { ov.classList.add("on"); (ov.querySelector("select, input, textarea") || ov.querySelector("button")).focus(); });
  if (onOpen) onOpen(ov.querySelector(".dir-dlg"));
  return ov;
}
function dirClose() { const ov = document.getElementById("dirOv"); if (!ov) return; ov.remove(); document.documentElement.classList.remove("dir-lock"); if (ov._opener && ov._opener.isConnected) ov._opener.focus({preventScroll: true}); }

/* maqsadlar ro'yxati — FAQAT ruxsat etilganlari (server /api/dir/targets), guruhlab */
function dirTargetOpts(T, sel = "") {
  let h = `<option value="">— tanlang —</option>`;
  if (T.people.length) h += `<optgroup label="O'z xodimlarim${T.my_unit ? " (" + esc(T.my_unit) + ")" : ""}">${T.people.map(p => `<option value="u:${p.id}" ${sel === "u:" + p.id ? "selected" : ""}>${esc(p.name)} — ${esc(p.position)}</option>`).join("")}</optgroup>`;
  for (const g of T.groups) h += `<optgroup label="${esc(g.name)}">${g.units.map(u => `<option value="b:${esc(u.key)}">${esc(u.name)}${u.head ? " — " + esc(u.head) : ""}</option>`).join("")}</optgroup>`;
  return h;
}
const dirTarget = v => v.startsWith("u:") ? {user_id: +v.slice(2)} : v.startsWith("b:") ? {unit: v.slice(2)} : null;
const dirLocal = d => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}T${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;

/* Portal fayllari: ilova avval Portalga yuklanadi (o'z bo'limi), server topshiriq oluvchilarga ulashadi */
async function dirUpload(input) {
  const ids = [];
  for (const f of input.files || []) {
    const r = await fetch(`/api/portal/files?name=${encodeURIComponent(f.name)}&category=${encodeURIComponent("Topshiriq")}`, {method: "POST", credentials: "same-origin", headers: {"Content-Type": "application/octet-stream"}, body: f});
    if (!r.ok) { let m = "Fayl yuklanmadi"; try { m = (await r.json()).detail || m; } catch (e) {} throw new Error(`${f.name}: ${m}`); }
    ids.push((await r.json()).id);
  }
  return ids;
}

async function dirNewDialog() {
  const T = await J("/api/dir/targets");
  const d = new Date(); d.setDate(d.getDate() + 3); d.setHours(18, 0, 0, 0);
  dirModal("Yangi topshiriq", `
    ${T.on_behalf ? `<div class="src-note demo" style="margin-bottom:12px">${ico("info", 15)} <span>Topshiriq <b>rektor nomidan</b> beriladi va shunday belgilanadi.</span></div>` : ""}
    <div class="form-grid">
      <label class="full">Kimga<select id="dnTo">${dirTargetOpts(T)}</select><span class="tiny muted" style="font-weight:400">Faqat vakolatingizdagi bo'limlar va o'z xodimlaringiz ko'rsatilgan.</span></label>
      <label class="full">Topshiriq (qisqa nomi)<input id="dnTitle" type="text" maxlength="300" placeholder="Masalan: Yakuniy nazoratga ruxsat etilmaganlar ro'yxati"></label>
      <label class="full">Mazmuni<textarea id="dnBody" rows="4" maxlength="5000" placeholder="Nima, qanday hajmda, kim bilan kelishib bajarilsin…"></textarea></label>
      <label>Muddat<input id="dnDue" type="datetime-local" value="${dirLocal(d)}"></label>
      <label>Ustuvorlik<select id="dnPrio">${Object.entries(T.prios).map(([k, v]) => `<option value="${k}">${esc(v)}</option>`).join("")}</select></label>
      <label class="full"><span>Natija talab qilinadi <span class="tiny muted" style="font-weight:400">(ixtiyoriy)</span></span><input id="dnExpect" type="text" maxlength="1000" placeholder="Masalan: Excel ro'yxat va qisqa izoh"></label>
      <label class="full"><span>Ilovalar <span class="tiny muted" style="font-weight:400">(ixtiyoriy · Portal fayllari sifatida saqlanadi va oluvchiga ulashiladi)</span></span><input id="dnFiles" type="file" multiple></label>
    </div>
    <div class="row-actions" style="margin-top:14px"><button class="btn primary" id="dnSend">${ico("send", 15)} Topshiriqni berish</button><button class="btn ghost" data-dclose>Bekor</button></div>`, dlg => {
    dlg.querySelector("#dnSend").onclick = e => busy(e.currentTarget, async () => {
      const to = dirTarget(dlg.querySelector("#dnTo").value), title = dlg.querySelector("#dnTitle").value.trim();
      if (!to) return toast("Kimga berilishini tanlang");
      if (title.length < 3) return toast("Topshiriq nomini yozing");
      if (!dlg.querySelector("#dnDue").value) return toast("Muddatni kiriting");
      let att = [];
      try { att = await dirUpload(dlg.querySelector("#dnFiles")); } catch (er) { return toast(er.message); }
      const r = await dirPost("/api/dir", {...to, title, body: dlg.querySelector("#dnBody").value, due_at: dlg.querySelector("#dnDue").value,
        priority: dlg.querySelector("#dnPrio").value, expect: dlg.querySelector("#dnExpect").value, attachments: att});
      if (!r) return;
      dirClose(); toast("Topshiriq berildi"); badges(); openDirective(r.id);
    }, "Yuborilmoqda…");
  });
}

/* server xatosini (400/409) foydalanuvchiga tushunarli ko'rsatish */
async function dirPost(url, body, method = "POST") {
  const r = await fetch(url, {method, credentials: "same-origin", headers: {"Content-Type": "application/json"}, body: body ? JSON.stringify(body) : undefined});
  if (r.status === 401) { showLogin(); return null; }
  let j = null; try { j = await r.json(); } catch (e) {}
  if (!r.ok) {
    const m = j && (j.message || (typeof j.detail === "string" ? j.detail : Array.isArray(j.detail) ? "Maydonlar to'g'ri to'ldirilmagan" : null));
    toast(m || "Xatolik yuz berdi"); return null;
  }
  return j || {ok: true};
}

/* --- topshiriq oynasi: zanjir daraxti, harakatlar, tarix --- */
async function renderDirective(id, silent) {
  const el = $("#v-tasks");
  let d;
  try { d = await J(`/api/dir/${id}`); } catch (e) {
    if (e.message === "denied") { el.innerHTML = dirBack() + locked("Bu topshiriq"); return; }
    if (silent) return;
    el.innerHTML = dirBack() + `<div class="card"><p class="muted">Topshiriq topilmadi yoki bekor qilingan.</p></div>`; return;
  }
  const sig = JSON.stringify(d);
  if (silent && (sig === DIR.sig || [...el.querySelectorAll("textarea, input[type=text]")].some(x => x.value.trim()) || document.getElementById("dirOv"))) return;
  DIR.sig = sig;
  const scroll = silent ? window.scrollY : 0;
  el.innerHTML = dirHtml(d);
  dirBindView(d);
  hydrateIcons(el);
  if (silent) window.scrollTo({top: scroll});
  else { const f = el.querySelector(".dir-node.focus"); if (f && d.focus !== d.root) f.scrollIntoView({block: "center"}); }
  clearInterval(DIR.timer);
  DIR.timer = setInterval(() => { if (DIR.open === id && !$("#v-tasks").classList.contains("hidden")) renderDirective(id, true).catch(() => {}); else clearInterval(DIR.timer); }, 8000);
}
const dirBack = () => `<button class="btn ghost sm" onclick="closeDirective()" style="margin-bottom:10px">← Topshiriqlar</button>`;
function dirFlat(n, out = []) { out.push(n); n.children.forEach(c => dirFlat(c, out)); return out; }

function dirHtml(d) {
  const all = dirFlat(d.tree), root = d.tree, byId = Object.fromEntries(all.map(n => [n.id, n]));
  const ev = [...d.log.map(l => ({...l, k: "log"})), ...d.msgs.map(m => ({...m, k: "msg"}))].sort((a, b) => a.ts < b.ts ? -1 : a.ts > b.ts ? 1 : 0);
  const canMsg = all.length > 0;
  return dirBack() + `<div class="head"><div><h2>${esc(root.title)}</h2><span class="muted">${esc(root.issuer_label)} · ${dtm(root.created_at)}${d.parent_hidden ? " · <span class='tiny'>yuqori topshiriqning bir qismi</span>" : ""}</span></div></div>
  <div class="dec-grid dir-grid">
    <div class="dir-tree">${dirNode(d, root)}</div>
    <div class="dec-side">
      <div class="card"><h3>${ico("history")} Tarix va izohlar</h3>
        <ol class="tl dir-tl">${ev.map(x => `<li class="${x.k === "msg" ? "msg" : ""}"><span class="tl-t">${dtm(x.ts)}${all.length > 1 && byId[x.task_id] ? ` · ${esc(dirShort(byId[x.task_id]))}` : ""}</span>${x.k === "msg"
          ? `<b>${esc(x.user_short || x.user_name)}</b>: ${esc(x.text)}`
          : `<b>${esc(x.action)}</b> — ${esc(x.user_short || x.user_name)}${x.detail ? `<div class="tiny muted">${esc(x.detail.length > 160 ? x.detail.slice(0, 160) + "…" : x.detail)}</div>` : ""}`}</li>`).join("") || `<li class="muted">Yozuv yo'q</li>`}</ol>
        ${canMsg ? `<form class="chat-in" id="dirMsg"><input type="text" placeholder="Izoh yozing…" maxlength="2000" aria-label="Izoh"><button class="btn primary sm" aria-label="Yuborish">${ico("send", 15)}</button></form>` : ""}
      </div>
    </div>
  </div>`;
}
const dirShort = n => n.assignee_name || n.unit_name || "";
const dirFiles = (fs, label) => fs && fs.length ? `<div class="dir-files"><span class="tiny muted">${label}:</span> ${fs.map(f => `<a class="dir-file" href="/api/portal/files/${f.id}/download" target="_blank" rel="noopener">${ico("file", 14)} ${esc(f.name)}</a>`).join("")}</div>` : "";

function dirNode(d, n) {
  const focus = n.id === d.focus;
  const kids = n.children.length ? `<div class="dir-kids">${n.children.map(c => dirNode(d, c)).join("")}</div>` : "";
  return `<div class="dir-branch"><div class="card dir-node ${focus ? "focus" : ""} ${n.status === "bajarildi" ? "done" : ""} ${n.overdue ? "late" : ""}" data-nid="${n.id}">
    <div class="dir-node-h"><span class="dir-node-who">${dirWho(n)}</span><span class="dir-node-tags">${dirPrio(n.priority)}${dirTag(n)}</span></div>
    ${n.depth ? `<p class="dt-text">${esc(n.title)}</p>` : ""}
    ${n.body ? `<p class="dir-body">${esc(n.body)}</p>` : ""}
    <div class="kv">
      <span>Bergan</span><span>${esc(n.issuer_label)}</span>
      <span>Muddat</span><span>${n.due ? `<b class="${n.overdue ? "bad" : ""}">${dtm(n.due)}</b>${n.overdue ? ` <span class="tiny bad">muddati o'tgan</span>` : ""}` : `<span class="unsaid">belgilanmagan</span>`}</span>
      ${n.expect ? `<span>Kutilgan natija</span><span>${esc(n.expect)}</span>` : ""}
      ${n.can_assign && d.staff.length ? `<span>Ijrochi</span><span><select class="sel-sm" data-dassign="${n.id}" aria-label="Ijrochi"><option value="">— biriktirilmagan —</option>${d.staff.map(s => `<option value="${s.id}" ${s.id === n.assignee_user ? "selected" : ""}>${esc(s.name)} (${esc(s.role)})</option>`).join("")}</select></span>` : ""}
      ${n.progress.total ? `<span>Taqsimlangan</span><span class="dir-progline">${dirProg(n)}</span>` : ""}
    </div>
    ${dirFiles(n.attachments, "Ilovalar")}
    ${n.review === "qaytarildi" && n.review_note ? `<div class="res dir-ret"><div class="res-h">Qaytarildi · ${esc(n.review_by || "")} · ${dtm(n.review_at)}</div>${esc(n.review_note)}</div>` : ""}
    ${n.result ? `<div class="res"><div class="res-h">${n.status === "bajarildi" ? "Natija" : "Oraliq natija"} · ${esc(n.result_by || "")} · ${dtm(n.result_at)}</div>${esc(n.result)}${dirFiles(n.result_attachments, "Natija fayllari")}</div>` : ""}
    ${n.review === "qabul" && n.review_by ? `<p class="tiny good" style="margin:8px 0 0">${ico("check", 14)} Qabul qildi: ${esc(n.review_by)} · ${dtm(n.review_at)}${n.review_note ? " — " + esc(n.review_note) : ""}</p>` : ""}
    ${dirActs(n)}
  </div>${kids}</div>`;
}

function dirActs(n) {
  let h = "";
  if (n.can_review) h += `<div class="act dir-review"><b class="tiny">Natijani ko'rib chiqing</b>
    <textarea class="f-rnote" rows="2" maxlength="2000" placeholder="Izoh (qaytarishda majburiy): nimani to'g'rilash kerak…"></textarea>
    <div class="row-actions"><button class="btn sm primary" data-daccept="${n.id}">${ico("check", 15)} Qabul qilish</button><button class="btn sm" data-dreturn="${n.id}">${ico("refresh", 15)} Qayta ishlashga qaytarish</button></div></div>`;
  if (n.can_act) {
    const open = n.progress.total - n.progress.done;
    h += `<div class="act">
      ${n.suggest_complete ? `<div class="src-note">${ico("info", 15)} <span>Barcha quyi topshiriqlar bajarildi — yakuniy natijani yozib, topshiriqni yakunlang.</span></div>` : ""}
      <div class="row-actions">${n.status === "yangi" ? `<button class="btn sm" data-dstart="${n.id}">${ico("play", 16)} Ishni boshlash</button>` : ""}
        ${n.can_delegate ? `<button class="btn sm" data-ddel="${n.id}">${ico("users", 16)} Taqsimlash / yo'naltirish</button>` : ""}
        ${n.can_cancel && n.status !== "bajarildi" ? `<button class="btn ghost sm" data-dcancel="${n.id}">${ico("x", 15)} Bekor qilish</button>` : ""}</div>
      <textarea class="f-res" rows="3" maxlength="5000" placeholder="${n.progress.total ? "Yakuniy natija: quyi topshiriqlar natijalari jamlanmasi…" : "Natija: nima qilindi, qanday hujjat tayyorlandi…"}">${n.status === "jarayonda" && n.result && n.review !== "qaytarildi" ? esc(n.result) : ""}</textarea>
      <label class="tiny muted dir-fl">Natija fayli (ixtiyoriy): <input type="file" class="f-rfile" multiple></label>
      <div class="row-actions"><button class="btn sm" data-dsave="${n.id}">Oraliq natijani saqlash</button>
        <button class="btn sm primary" data-dfinish="${n.id}" ${open ? "disabled" : ""}>${ico("check", 15)} Bajarildi — natijani yuborish</button></div>
      ${open ? `<p class="tiny warn-t" style="margin:0">${open} ta quyi topshiriq hali bajarilmagan — yakunlash ular bajarilgach ochiladi (server ham tekshiradi).</p>` : ""}
    </div>`;
  } else if (n.can_cancel && n.status !== "bajarildi") {
    h += `<div class="row-actions" style="margin-top:12px"><button class="btn ghost sm" data-dcancel="${n.id}">${ico("x", 15)} Topshiriqni bekor qilish</button></div>`;
  }
  return h;
}

function dirBindView(d) {
  const el = $("#v-tasks"), all = dirFlat(d.tree), byId = Object.fromEntries(all.map(n => [n.id, n]));
  const re = () => { DIR.sig = ""; renderDirective(d.focus); badges(); };
  const card = b => b.closest(".dir-node");
  el.querySelectorAll("[data-dassign]").forEach(s => s.onchange = async () => {
    if (!s.value) return; s.disabled = true;
    const r = await dirPost(`/api/dir/${s.dataset.dassign}/assign`, {user_id: +s.value}); if (r) toast("Xodimga biriktirildi"); re();
  });
  el.querySelectorAll("[data-dstart]").forEach(b => b.onclick = () => busy(b, async () => { if (await dirPost(`/api/dir/${b.dataset.dstart}/status`, {status: "jarayonda"})) { toast("Holat: jarayonda"); re(); } }));
  const send = (b, status) => busy(b, async () => {
    const c = card(b), v = c.querySelector(".f-res").value.trim();
    if (!v) return toast(status === "bajarildi" ? "Yakunlash uchun natijani yozing" : "Natija matnini yozing");
    let att = []; try { att = await dirUpload(c.querySelector(".f-rfile")); } catch (er) { return toast(er.message); }
    if (await dirPost(`/api/dir/${b.dataset.dsave || b.dataset.dfinish}/status`, {status, result: v, attachments: att})) { toast(status === "bajarildi" ? "Natija yuborildi — bergan rahbar qabul qiladi" : "Oraliq natija saqlandi"); re(); }
  });
  el.querySelectorAll("[data-dsave]").forEach(b => b.onclick = () => send(b, "jarayonda"));
  el.querySelectorAll("[data-dfinish]").forEach(b => b.onclick = () => send(b, "bajarildi"));
  el.querySelectorAll("[data-daccept]").forEach(b => b.onclick = () => busy(b, async () => {
    if (await dirPost(`/api/dir/${b.dataset.daccept}/review`, {decision: "qabul", note: card(b).querySelector(".f-rnote").value})) { toast("Natija qabul qilindi"); re(); } }));
  el.querySelectorAll("[data-dreturn]").forEach(b => b.onclick = () => busy(b, async () => {
    const t = card(b).querySelector(".f-rnote"), v = t.value.trim();
    if (!v) { t.focus(); return toast("Qaytarish sababini yozing"); }
    if (await dirPost(`/api/dir/${b.dataset.dreturn}/review`, {decision: "qaytarish", note: v})) { toast("Qayta ishlashga qaytarildi"); re(); } }));
  el.querySelectorAll("[data-dcancel]").forEach(b => b.onclick = () => {
    const n = byId[+b.dataset.dcancel];
    if (!confirm(`«${n.title}» topshirig'i${n.progress.total ? " va uning barcha quyi topshiriqlari" : ""} bekor qilinsinmi?`)) return;
    busy(b, async () => { if (await dirPost(`/api/dir/${n.id}`, null, "DELETE")) { toast("Topshiriq bekor qilindi"); if (n.id === d.root) closeDirective(); else re(); } });
  });
  el.querySelectorAll("[data-ddel]").forEach(b => b.onclick = () => dirDelegateDialog(d, byId[+b.dataset.ddel]));
  const f = $("#dirMsg");
  if (f) f.onsubmit = e => {
    e.preventDefault(); const inp = f.querySelector("input"), v = inp.value.trim(); if (!v) return;
    busy(f.querySelector("button"), async () => { if (await dirPost(`/api/dir/${d.focus}/msg`, {text: v})) { inp.value = ""; re(); } });
  };
}

/* --- taqsimlash: o'z xodimlariga yoki quyi bo'limlarga (har biriga o'z muddati, asosiy muddatdan kech emas) --- */
function dirDelegateDialog(d, n) {
  const T = d.targets;
  if (!T || !T.can) return toast("Taqsimlash uchun xodim yoki quyi bo'lim yo'q");
  const max = n.due ? n.due.slice(0, 16) : "";
  const row = () => `<div class="dir-drow"><select class="dd-to" aria-label="Kimga">${dirTargetOpts(T)}</select>
    <input type="datetime-local" class="dd-due" value="${max}" ${max ? `max="${max}"` : ""} aria-label="Muddat">
    <button class="btn ghost sm dd-rm" type="button" aria-label="Qatorni olib tashlash">${ico("x", 15)}</button></div>`;
  dirModal("Topshiriqni taqsimlash", `
    <p class="tiny muted" style="margin:0 0 10px">«${esc(n.title)}»${n.due ? ` · asosiy muddat <b>${dtm(n.due)}</b>` : ""}. Har bir ijrochi uchun alohida quyi topshiriq yaratiladi; asosiy topshiriq hammasi bajarilgach, siz yakuniy natijani yuborganingizda yakunlanadi.</p>
    <div class="dir-drows">${row()}</div>
    <button class="btn ghost sm" type="button" id="ddAdd">${dirPlus} Yana ijrochi qo'shish</button>
    <div class="form-grid" style="margin-top:10px">
      <label class="full"><span>Quyi topshiriq nomi <span class="tiny muted" style="font-weight:400">(bo'sh bo'lsa — asosiy topshiriq nomi)</span></span><input type="text" id="ddTitle" maxlength="300" placeholder="${esc(n.title)}"></label>
      <label class="full"><span>Ko'rsatma <span class="tiny muted" style="font-weight:400">(ixtiyoriy)</span></span><textarea id="ddNote" rows="3" maxlength="3000" placeholder="Nimaga e'tibor berish kerak…"></textarea></label>
    </div>
    <div class="row-actions" style="margin-top:14px"><button class="btn primary" id="ddSend">${ico("send", 15)} Yo'naltirish</button><button class="btn ghost" data-dclose>Bekor</button></div>`, dlg => {
    const rows = dlg.querySelector(".dir-drows");
    const bindRm = () => rows.querySelectorAll(".dd-rm").forEach(b => b.onclick = () => { if (rows.children.length > 1) b.closest(".dir-drow").remove(); });
    bindRm();
    dlg.querySelector("#ddAdd").onclick = () => { rows.insertAdjacentHTML("beforeend", row()); hydrateIcons(rows); bindRm(); rows.lastElementChild.querySelector("select").focus(); };
    dlg.querySelector("#ddSend").onclick = e => busy(e.currentTarget, async () => {
      const title = dlg.querySelector("#ddTitle").value.trim();
      const items = [...rows.querySelectorAll(".dir-drow")].map(r => ({...dirTarget(r.querySelector(".dd-to").value) || {}, due_at: r.querySelector(".dd-due").value || null, title: title || null}));
      if (items.some(i => !i.unit && !i.user_id)) return toast("Har bir qatorda ijrochini tanlang");
      if (max && items.some(i => i.due_at && i.due_at > max)) return toast("Quyi topshiriq muddati asosiy muddatdan kech bo'lmasin");
      const r = await dirPost(`/api/dir/${n.id}/delegate`, {items, note: dlg.querySelector("#ddNote").value});
      if (!r) return;
      dirClose(); toast(`Yo'naltirildi: ${r.ids.length} ta quyi topshiriq`); DIR.sig = ""; renderDirective(d.focus); badges();
    }, "Yuborilmoqda…");
  });
}
