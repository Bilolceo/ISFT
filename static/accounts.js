/* =====================================================================
   «Akkauntlar» — AT bo'limi boshlig'i uchun akkauntlar boshqaruvi (app/accounts.py, /api/accounts).
     it_head: yaratish, tahrirlash, parolni tiklash (vaqtinchalik parol bir marta ko'rsatiladi), sinov paroli (faqat sinov rejimida),
              blokdan chiqarish, sessiyalarni yopish, Telegram'ni uzish, faolsizlantirish / faollashtirish.
     rektor:  faqat ko'rish. Ruxsatlar serverda tekshiriladi — bu yerda faqat tugmalar ko'rsatiladi/yashiriladi.
   Tasdiqlashlar qator ostida (window.confirm/alert ishlatilmaydi).
   Global: renderAccounts() — app.js go() chaqiradi.
   app.js yordamchilaridan foydalanadi: $, esc, fmt, ico, ICONS, hydrateIcons, toast, showLogin, ME.
   Uslublar: accounts.css (shu fayldan ulanadi; umumiy tokenlar — qorong'i rejim avtomatik).
   ===================================================================== */
const AC = {data: null, q: "", role: "", unit: "", st: "", open: null, form: false, created: null, menu: null};
if (!document.querySelector('link[href="accounts.css"]')) document.head.insertAdjacentHTML("beforeend", '<link rel="stylesheet" href="accounts.css">');
if (typeof ICONS === "object") {
  Object.assign(ICONS, Object.fromEntries(Object.entries({
    ukey: '<circle cx="9" cy="7" r="4"/><path d="M2 21v-1a7 7 0 0 1 10.5-6.06"/><circle cx="17.5" cy="15.5" r="2.5"/><path d="m19.3 13.7 2.7-2.7M21 12l1 1"/>',
    dots: '<circle cx="12" cy="5" r="1.4"/><circle cx="12" cy="12" r="1.4"/><circle cx="12" cy="19" r="1.4"/>',
    plus: '<path d="M12 5v14M5 12h14"/>',
    key: '<circle cx="7.5" cy="15.5" r="4.5"/><path d="m10.7 12.3 9.8-9.8M17 6l3 3M14.5 8.5l2 2"/>',
    copy: '<rect x="9" y="9" width="12" height="12" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>',
    tg: '<path d="m21.5 3.5-19 7.3 6.2 2.3 2.3 6.4 3.5-4.2 5 3.7z"/><path d="m8.7 13.1 8.6-6.1"/>',
    ban: '<circle cx="12" cy="12" r="9"/><path d="m5.6 5.6 12.8 12.8"/>',
    pen: '<path d="M12 20h9"/><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4z"/>',
  }).filter(([k]) => !ICONS[k])));
  /* app.js menyu ikonkalarini bu fayl yuklanishidan oldin chizgan — bo'sh qolgan ikonka qayta chiziladi */
  try { const s = document.querySelector('#nav a[data-v="accounts"] svg'); if (s && !s.innerHTML.trim()) { s.remove(); hydrateIcons(); } } catch (e) {}
}

/* ---------- server ---------- */
async function acApi(path, body) {
  const r = await fetch(path, {method: body === undefined ? "GET" : "POST", credentials: "same-origin", headers: {"Content-Type": "application/json"},
                               body: body === undefined ? undefined : JSON.stringify(body)});
  if (r.status === 401) { showLogin(); throw new Error("auth"); }
  const d = await r.json().catch(() => ({}));
  if (!r.ok) {
    const det = d.detail, msg = d.message || (typeof det === "string" ? det : det && det.message) || "Xatolik yuz berdi";
    const e = new Error(r.status === 403 && body === undefined ? "denied" : "api"); e.msg = msg; e.field = det && det.field; e.status = r.status; throw e;
  }
  return d;
}

/* ---------- yordamchilar ---------- */
const AC_ST = {all: "Hammasi", active: "Faol", inactive: "Faol emas", locked: "Bloklangan", tg: "Telegram ulangan"};
function acWhen(ts) {
  if (!ts) return {t: "Kirmagan", s: ""};
  const d = new Date(ts); if (isNaN(d)) return {t: esc(ts), s: ""};
  const p = n => String(n).padStart(2, "0"), day = new Date(d.getFullYear(), d.getMonth(), d.getDate());
  const now = new Date(), today = new Date(now.getFullYear(), now.getMonth(), now.getDate()), n = Math.round((today - day) / 864e5);
  const s = n <= 0 ? "bugun" : n === 1 ? "kecha" : n < 31 ? `${n} kun oldin` : "";
  return {t: `${p(d.getDate())}.${p(d.getMonth() + 1)}.${d.getFullYear()} ${p(d.getHours())}:${p(d.getMinutes())}`, s};
}
const acPerson = u => u.person || u.position;
const acSub = u => u.person ? u.position : "";
function acMatch(u) {
  if (AC.role && u.role !== AC.role) return false;
  if (AC.unit && u.unit !== AC.unit) return false;
  if (AC.st === "active" && !u.active) return false;
  if (AC.st === "inactive" && u.active) return false;
  if (AC.st === "locked" && !(u.locked_min > 0)) return false;
  if (AC.st === "tg" && !u.telegram) return false;
  const q = AC.q.trim().toLowerCase().replace(/[ʻʼ‘’`´]/g, "'");
  if (!q) return true;
  const hay = [u.full_name, u.role_title, u.unit_name, u.role, "#" + u.id].join(" ").toLowerCase().replace(/[ʻʼ‘’`´]/g, "'");
  return q.split(/\s+/).every(w => hay.includes(w));
}
function acStatus(u) {
  if (!u.active) return `<span class="ac-st off">${ico("ban", 13)}Faol emas</span>`;
  if (u.locked_min > 0) return `<span class="ac-st lock">${ico("lock", 13)}Bloklangan · ${u.locked_min} daq</span>`;
  return `<span class="ac-st on"><i></i>Faol</span>`;
}

/* ---------- chizish ---------- */
function acShell() {
  const d = AC.data, el = $("#v-accounts");
  const roles = d.roles.filter(r => d.items.some(u => u.role === r.key));
  const units = d.units.filter(x => d.items.some(u => u.unit === x.key));
  el.innerHTML = `<div class="head"><div><h2>Akkauntlar</h2><span class="muted">Tizim foydalanuvchilari: lavozim, bo'lim, Telegram, oxirgi kirish va holat. Har bir amal audit jurnaliga yoziladi.</span></div>
      <div class="row-actions ac-top">${d.can_edit ? `<button class="btn primary sm" type="button" id="acNew" aria-expanded="${AC.form}" aria-controls="acForm">${ico("plus", 15)} Yangi akkaunt</button>` : ""}
        <button class="btn sm" type="button" id="acRefresh">${ico("refresh", 15)} Yangilash</button></div></div>
    ${d.can_edit ? "" : `<div class="src-note ac-note">${ico("eye", 15)}<span><b>Faqat ko'rish rejimi.</b> Akkauntlarni Axborot texnologiyalari bo'limi boshlig'i boshqaradi; rahbariyat akkauntlari — faqat server administratori orqali.</span></div>`}
    <div class="ac-stats" id="acStats"></div>
    <div id="acFormBox"></div>
    <div class="card ac-card">
      <div class="ac-filters" role="search">
        <label class="ac-search">${ico("search", 16)}<input type="search" id="acQ" placeholder="Ism, lavozim yoki bo'lim…" value="${esc(AC.q)}" aria-label="Akkauntlarni qidirish" autocomplete="off"></label>
        <select id="acRole" aria-label="Rol bo'yicha"><option value="">Barcha rollar</option>${roles.map(r => `<option value="${esc(r.key)}"${AC.role === r.key ? " selected" : ""}>${esc(r.title)}</option>`).join("")}</select>
        <select id="acUnit" aria-label="Bo'lim bo'yicha"><option value="">Barcha bo'limlar</option>${units.map(x => `<option value="${esc(x.key)}"${AC.unit === x.key ? " selected" : ""}>${esc(x.name)}</option>`).join("")}</select>
        <select id="acSt" aria-label="Holat bo'yicha">${Object.entries(AC_ST).map(([k, v]) => `<option value="${k === "all" ? "" : k}"${(AC.st || "all") === k ? " selected" : ""}>${v}</option>`).join("")}</select>
      </div>
      <div id="acTable"></div>
    </div>`;
  hydrateIcons(el);
  const q = $("#acQ"); let t;
  q.oninput = () => { clearTimeout(t); t = setTimeout(() => { AC.q = q.value; acTable(); }, 120); };
  $("#acRole").onchange = e => { AC.role = e.target.value; acTable(); };
  $("#acUnit").onchange = e => { AC.unit = e.target.value; acTable(); };
  $("#acSt").onchange = e => { AC.st = e.target.value; acTable(); };
  $("#acRefresh").onclick = () => acReload(true);
  const nb = $("#acNew"); if (nb) nb.onclick = () => { AC.form = !AC.form; AC.created = null; nb.setAttribute("aria-expanded", AC.form); acFormDraw(); if (AC.form) $("#acfPos")?.focus(); };
  acStats(); acFormDraw(); acTable();
}

function acStats() {
  const c = AC.data.counts;
  const tile = (k, label, n, cls, icon) => `<button type="button" class="ac-tile ${cls}${n ? "" : " zero"}${(AC.st || "") === k ? " on" : ""}" data-st="${k}" aria-pressed="${(AC.st || "") === k}"><span class="ac-tile-ic">${ico(icon, 16)}</span><b>${fmt(n)}</b><span>${label}</span></button>`;
  $("#acStats").innerHTML = tile("", "Jami", c.total, "tot", "users") + tile("active", "Faol", c.active, "ok", "checkc") + tile("inactive", "Faol emas", c.inactive, "off", "ban")
    + tile("tg", "Telegram ulangan", c.telegram, "tg", "tg") + tile("locked", "Bloklangan", c.locked, "bad", "lock");
  $("#acStats").querySelectorAll("[data-st]").forEach(b => b.onclick = () => { AC.st = b.dataset.st; const s = $("#acSt"); if (s) s.value = AC.st; acStats(); acTable(); });
}

function acRow(u) {
  const d = AC.data, w = acWhen(u.last_login);
  const tags = (u.self ? `<span class="ac-tag me">Siz</span>` : "") + (u.protected ? `<span class="ac-tag prot" title="Rol va holat faqat server administratori (CLI) orqali o'zgaradi">${ico("shield", 12)}Himoyalangan</span>` : "");
  const open = AC.open && AC.open.id === u.id;
  return `<tr class="ac-r${u.active ? "" : " ac-off"}${open ? " ac-open" : ""}" data-id="${u.id}">
    <td class="ac-who" data-l="F.I.Sh. / lavozim"><div class="ac-whoin"><span class="ac-av l${u.level}" aria-hidden="true">${esc(acInit(u))}</span><span class="ac-nm"><b>${esc(acPerson(u))}</b>${acSub(u) ? `<small>${esc(acSub(u))}</small>` : ""}${tags ? `<span class="ac-tags">${tags}</span>` : ""}</span></div></td>
    <td data-l="Rol"><span class="ac-role">${esc(u.role_title)}</span></td>
    <td data-l="Bo'lim">${esc(u.unit_name)}</td>
    <td data-l="Telegram">${u.telegram ? `<span class="ac-tg on">${ico("tg", 13)}Ulangan</span>` : `<span class="ac-tg">—</span>`}</td>
    <td data-l="Oxirgi kirish" class="ac-when">${u.last_login ? `<span>${w.t}</span>${w.s ? `<small>${w.s}</small>` : ""}` : `<span class="muted">Kirmagan</span>`}${u.sessions ? `<small>${u.sessions} ta ochiq sessiya</small>` : ""}</td>
    <td data-l="Holat">${acStatus(u)}</td>
    ${d.can_edit ? `<td class="ac-act"><button type="button" class="icon-btn ac-more" data-menu="${u.id}" aria-haspopup="menu" aria-expanded="false" aria-label="Amallar: ${esc(acPerson(u))}" title="Amallar">${ico("dots", 18)}</button></td>` : ""}
  </tr>${open ? `<tr class="ac-x"><td colspan="${d.can_edit ? 7 : 6}"><div class="ac-xin" id="acX">${acPanel(u)}</div></td></tr>` : ""}`;
}
const acInit = u => { const w = String(acPerson(u)).replace(/[^\p{L}\s]/gu, "").split(/\s+/).filter(Boolean); return ((w[0] || "")[0] || "").toUpperCase() + ((w[1] || "")[0] || "").toUpperCase(); };

function acTable() {
  acMenuClose();
  const d = AC.data, rows = d.items.filter(acMatch), box = $("#acTable");
  if (!rows.length) { box.innerHTML = `<div class="ac-empty">${ico("search", 22)}<b>Hech narsa topilmadi</b><span class="muted">Qidiruv yoki saralash shartlarini o'zgartiring.</span></div>`; return; }
  box.innerHTML = `<p class="muted tiny ac-cnt" aria-live="polite">${rows.length === d.items.length ? `${rows.length} ta akkaunt` : `${rows.length} / ${d.items.length} ta akkaunt`}</p>
    <div class="tw ac-tw"><table class="ac-tbl"><thead><tr><th>F.I.Sh. / lavozim</th><th>Rol</th><th>Bo'lim</th><th>Telegram</th><th>Oxirgi kirish</th><th>Holat</th>${d.can_edit ? `<th class="ac-act"><span class="sr">Amallar</span></th>` : ""}</tr></thead>
    <tbody>${rows.map(acRow).join("")}</tbody></table></div>`;
  box.querySelectorAll("[data-menu]").forEach(b => b.onclick = e => { e.stopPropagation(); acMenu(b); });
  acPanelBind();
}

/* ---------- amallar menyusi ---------- */
function acItems(u) {
  const c = u.can || {}, d = AC.data, out = [];
  const why = u.self ? "O'z akkauntingiz" : u.protected ? "Faqat CLI orqali" : "";
  out.push({k: "edit", t: "Tahrirlash", i: "pen", off: !c.edit, why});
  out.push({k: "reset-password", t: "Parolni tiklash", i: "key", off: !c.reset, why: u.self ? "«Parolni o'zgartirish» oynasidan" : ""});
  if (d.demo) out.push({k: "demo-password", t: "Sinov parolini tiklash (Isft2026)", i: "refresh", off: !c.reset, why: u.self ? "O'z akkauntingiz" : ""});
  if (u.locked_min > 0) out.push({k: "unlock", t: `Blokdan chiqarish (${u.locked_min} daq)`, i: "unlock"});
  out.push({k: "revoke", t: u.sessions ? `Sessiyalarni yopish (${u.sessions})` : "Sessiyalarni yopish", i: "logout", off: !u.sessions, why: u.sessions ? "" : "Ochiq sessiya yo'q"});
  if (u.telegram) out.push({k: "unlink-telegram", t: "Telegram'ni uzish", i: "tg"});
  out.push(u.active ? {k: "deactivate", t: "Faolsizlantirish", i: "ban", danger: true, off: !c.status, why}
                    : {k: "activate", t: "Faollashtirish", i: "checkc", off: !c.status, why});
  return out;
}
function acMenu(btn) {
  const id = +btn.dataset.menu, was = AC.menu && AC.menu.id === id;
  acMenuClose(); if (was) return;
  const u = AC.data.items.find(x => x.id === id); if (!u) return;
  const m = document.createElement("div");
  m.className = "ac-menu"; m.setAttribute("role", "menu"); m.setAttribute("aria-label", "Amallar");
  m.innerHTML = acItems(u).map(it => `<button type="button" role="menuitem" class="${it.danger ? "danger" : ""}" data-k="${it.k}"${it.off ? ` disabled aria-disabled="true"` : ""}>${ico(it.i, 16)}<span>${esc(it.t)}</span>${it.off && it.why ? `<small>${esc(it.why)}</small>` : ""}</button>`).join("")
    + (u.link_code ? `<div class="ac-menu-f">Telegram kodi: <code>${esc(u.link_code)}</code></div>` : "");
  document.body.appendChild(m);
  const r = btn.getBoundingClientRect(), mw = m.offsetWidth, mh = m.offsetHeight;
  const left = Math.max(8, Math.min(window.innerWidth - mw - 8, r.right - mw));
  const top = r.bottom + 6 + mh > window.innerHeight - 8 ? Math.max(8, r.top - mh - 6) : r.bottom + 6;
  m.style.left = left + "px"; m.style.top = top + "px";
  btn.setAttribute("aria-expanded", "true");
  AC.menu = {id, el: m, btn};
  m.querySelectorAll("button[data-k]:not([disabled])").forEach(b => b.onclick = () => { acMenuClose(); acOpen(id, b.dataset.k); });
  (m.querySelector("button:not([disabled])") || m).focus?.();
  m.addEventListener("keydown", e => {
    const bs = [...m.querySelectorAll("button:not([disabled])")], i = bs.indexOf(document.activeElement);
    if (e.key === "ArrowDown") { e.preventDefault(); bs[(i + 1) % bs.length]?.focus(); }
    else if (e.key === "ArrowUp") { e.preventDefault(); bs[(i - 1 + bs.length) % bs.length]?.focus(); }
    else if (e.key === "Escape" || e.key === "Tab") { e.preventDefault(); acMenuClose(true); }
  });
}
function acMenuClose(refocus) {
  if (!AC.menu) return;
  const {el, btn} = AC.menu; AC.menu = null; el.remove();
  if (btn && btn.isConnected) { btn.setAttribute("aria-expanded", "false"); if (refocus) btn.focus(); }
}
document.addEventListener("click", e => { if (AC.menu && !AC.menu.el.contains(e.target)) acMenuClose(); });
window.addEventListener("resize", () => acMenuClose());
document.addEventListener("scroll", () => acMenuClose(), true);

/* ---------- qator ostidagi panel: tasdiqlash, natija, tahrirlash ---------- */
const AC_CONFIRM = {
  "reset-password": u => [`<b>${esc(acPerson(u))}</b> uchun yangi vaqtinchalik parol yaratiladi. Eski parol ishlamay qoladi, barcha ochiq sessiyalari yopiladi${u.telegram ? " va Telegram ulanishi uziladi" : ""}.${u.protected ? " <b>Rahbariyat akkaunti</b> — amal audit jurnaliga alohida yoziladi." : ""}`, "Parolni tiklash", ""],
  "demo-password": u => [`<b>${esc(acPerson(u))}</b> paroli sinov paroliga (<code>Isft2026</code>) qaytariladi, sessiyalari yopiladi${u.telegram ? " va Telegram ulanishi uziladi" : ""}. Faqat sinov rejimida mavjud.`, "Sinov parolini tiklash", ""],
  "unlock": u => [`<b>${esc(acPerson(u))}</b> uchun noto'g'ri urinishlar cheklovi tozalanadi — darhol qayta kira oladi.`, "Blokdan chiqarish", ""],
  "revoke": u => [`<b>${esc(acPerson(u))}</b>ning barcha qurilmalardagi ${u.sessions} ta ochiq sessiyasi yopiladi${u.self ? " (joriy brauzeringiz bundan mustasno)" : ""}. Qayta kirish uchun parol kerak bo'ladi.`, "Sessiyalarni yopish", ""],
  "unlink-telegram": u => [`<b>${esc(acPerson(u))}</b>ning Telegram ulanishi uziladi. Qayta ulash uchun xodim kod va parolni botga yuboradi.`, "Telegram'ni uzish", ""],
  "deactivate": u => [`<b>${esc(acPerson(u))}</b> faolsizlantiriladi: tizimga kira olmaydi, ochiq sessiyalari darhol ishlamay qoladi, Telegram uziladi va kirish ro'yxatida ko'rinmaydi. Ma'lumotlari va audit tarixi saqlanadi.`, "Faolsizlantirish", "danger"],
  "activate": u => [`<b>${esc(acPerson(u))}</b> qayta faollashtiriladi va eski paroli bilan kira oladi. Kerak bo'lsa, keyin parolni tiklang.`, "Faollashtirish", ""],
};
function acOpen(id, kind) { AC.open = {id, kind}; acTable(); const x = $("#acX"); if (x) { x.closest("tr").previousElementSibling?.scrollIntoView({block: "nearest"}); (x.querySelector("form input,form select,[data-cancel]") || x).focus?.(); } }   /* tasdiq panelida fokus — «Bekor qilish»da (Enter tasodifan tiklamasin) */
function acClose() { const id = AC.open && AC.open.id; AC.open = null; acTable(); const b = document.querySelector(`[data-menu="${id}"]`); if (b) b.focus(); }

function acPanel(u) {
  const o = AC.open;
  if (o.kind === "edit") return acEditForm(u);
  if (o.result) return o.result;
  const [txt, label, cls] = AC_CONFIRM[o.kind](u);
  return `<div class="ac-confirm${cls ? " " + cls : ""}" role="group" aria-label="${esc(label)}"><span class="ac-cf-ic">${ico(cls ? "alert" : "info", 18)}</span><p>${txt}</p>
    <div class="ac-cf-b"><button type="button" class="btn sm ${cls ? "ac-danger" : "primary"}" data-do="${o.kind}">${esc(label)}</button><button type="button" class="btn sm ghost" data-cancel>Bekor qilish</button></div>
    <p class="ac-err" role="alert" hidden></p></div>`;
}
function acPwBox(pw, extra = "") {
  return `<div class="ac-pw"><label>Vaqtinchalik parol<span class="ac-pw-row"><input type="text" readonly value="${esc(pw)}" class="ac-pw-in" aria-label="Vaqtinchalik parol" spellcheck="false"><button type="button" class="btn sm" data-copy>${ico("copy", 15)} Nusxa olish</button></span></label>
    <p class="muted tiny">${ico("alert", 13)} Parol <b>faqat hozir</b> ko'rsatiladi — bazada faqat uning xeshi saqlanadi. Xodimga shaxsan yoki xavfsiz kanal orqali yetkazing va kirgach almashtirishini so'rang.${extra}</p></div>`;
}
function acEditForm(u) {
  const d = AC.data;
  return `<form class="ac-form ac-edit" novalidate aria-label="Akkauntni tahrirlash">
    ${acFields({position: u.position, person: u.person, role: u.role, unit: u.unit}, "e")}
    <div class="ac-fb"><button class="btn sm primary" type="submit">${ico("check", 15)} Saqlash</button><button type="button" class="btn sm ghost" data-cancel>Bekor qilish</button>
      <span class="muted tiny">Rol o'zgarsa, xodimning ochiq sessiyalari yopiladi.</span></div>
    <p class="ac-err" role="alert" hidden></p></form>`;
}
function acFields(v, p) {
  const d = AC.data, roles = d.roles.filter(r => r.assignable || r.key === v.role);
  return `<div class="ac-grid">
    <label class="ac-f"><span>Lavozim nomi <i>*</i></span><input id="ac${p}Pos" name="position" maxlength="120" required value="${esc(v.position || "")}" placeholder="Masalan: Yuridik bo'lim yetakchi mutaxassisi" autocomplete="off"></label>
    <label class="ac-f"><span>F.I.Sh.</span><input id="ac${p}Person" name="person" maxlength="120" value="${esc(v.person || "")}" placeholder="Familiya Ism Otasining ismi" autocomplete="off"></label>
    <label class="ac-f"><span>Rol (ruxsatlar) <i>*</i></span><select name="role" id="ac${p}Role" required>${v.role ? "" : `<option value="">Tanlang…</option>`}${roles.map(r => `<option value="${esc(r.key)}"${r.key === v.role ? " selected" : ""}>${esc(r.title)}</option>`).join("")}</select></label>
    <label class="ac-f"><span>Bo'lim</span><select name="unit" id="ac${p}Unit">${acUnitOpts(v.role, v.unit)}</select></label>
  </div>`;
}
function acUnitOpts(role, cur) {
  const d = AC.data, r = d.roles.find(x => x.key === role), sc = r && r.scope;
  const groups = {rahbariyat: "Rahbariyat", bolim: "Bo'limlar", fakultet: "Fakultet tyutorlari", kafedra: "Kafedralar"};
  const ok = x => sc === "fakultet" ? x.group === "fakultet" : sc === "kafedra" ? x.group === "kafedra" : true;
  const list = d.units.filter(ok);
  const auto = r && r.default_unit && list.some(x => x.key === r.default_unit) ? r.default_unit : "";
  return (sc === "fakultet" || sc === "kafedra" ? `<option value="">${sc === "fakultet" ? "Fakultetni tanlang…" : "Kafedrani tanlang…"}</option>` : `<option value="">Rol bo'yicha${auto ? ": " + esc((list.find(x => x.key === auto) || {}).name || auto) : ""}</option>`)
    + Object.entries(groups).map(([g, gl]) => { const xs = list.filter(x => x.group === g); return xs.length ? `<optgroup label="${gl}">${xs.map(x => `<option value="${esc(x.key)}"${x.key === cur ? " selected" : ""}>${esc(x.name)}</option>`).join("")}</optgroup>` : ""; }).join("");
}
function acFormRole(form, p) {
  const rs = form.querySelector(`#ac${p}Role`), us = form.querySelector(`#ac${p}Unit`);
  if (rs && us) rs.onchange = () => { us.innerHTML = acUnitOpts(rs.value, ""); };
}
function acShowErr(box, e) {
  const p = box.querySelector(".ac-err"); if (!p) return toast(e.msg || "Xatolik");
  p.textContent = e.msg || "Xatolik yuz berdi — qayta urinib ko'ring"; p.hidden = false;
  box.querySelectorAll("[aria-invalid]").forEach(x => x.removeAttribute("aria-invalid"));
  const f = e.field && box.querySelector(`[name="${e.field}"]`); if (f) { f.setAttribute("aria-invalid", "true"); f.focus(); }
}
async function acRun(btn, fn) {
  if (!btn || btn.disabled) return;
  const old = btn.innerHTML; btn.disabled = true; btn.innerHTML = "…";
  try { await fn(); } catch (e) { if (e.message !== "auth") acShowErr(btn.closest(".ac-confirm,.ac-form,.ac-xin") || document.body, e); }
  finally { if (btn.isConnected) { btn.disabled = false; btn.innerHTML = old; } }
}
function acCopyBind(root) {
  root.querySelectorAll("[data-copy]").forEach(b => b.onclick = async () => {
    const inp = b.parentElement.querySelector("input"); inp.select();
    let ok = false;
    try { await navigator.clipboard.writeText(inp.value); ok = true; } catch (e) { try { ok = document.execCommand("copy"); } catch (e2) {} }
    b.innerHTML = ok ? `${ico("check", 15)} Nusxa olindi` : `${ico("info", 15)} Belgilandi — Ctrl+C`;
  });
}
function acPanelBind() {
  const x = $("#acX"); if (!x) return;
  const id = AC.open.id, u = AC.data.items.find(i => i.id === id);
  x.querySelectorAll("[data-cancel]").forEach(b => b.onclick = acClose);
  x.addEventListener("keydown", e => { if (e.key === "Escape") { e.preventDefault(); acClose(); } });
  acCopyBind(x);
  const doB = x.querySelector("[data-do]");
  /* qaytarib bo'lmaydigan amallar (parol tiklash, faolsizlantirish) — panel + ikki bosqichli tugma (app.js arm) */
  const AC_ARM = {"reset-password": "Ha, parolni tiklash", "demo-password": "Ha, sinov parolini tiklash", "deactivate": "Ha, faolsizlantirish", "revoke": "Ha, sessiyalarni yopish"};
  if (doB) doB.onclick = () => (AC_ARM[doB.dataset.do] && typeof arm === "function" && !arm(doB, AC_ARM[doB.dataset.do])) ? null : acRun(doB, async () => {
    const k = doB.dataset.do, r = await acApi(`/api/accounts/${id}/${k}`, {});
    if (r.password) {
      AC.open.result = `<div class="ac-done" role="status">${ico("checkc", 18)}<div><b>${esc(acPerson(u))}: yangi parol yaratildi</b>${r.revoked ? `<span class="muted tiny">${r.revoked} ta sessiya yopildi</span>` : ""}${r.telegram_unlinked ? `<span class="muted tiny">Telegram ulanishi uzildi — xodim botga kod va yangi parolni qayta yuboradi</span>` : ""}${acPwBox(r.password)}
        <button type="button" class="btn sm" data-cancel>Yopish</button></div></div>`;
      await acReload(false, true);
      return;
    }
    toast(r.message || "Bajarildi"); AC.open = null; await acReload(false);
  });
  const f = x.querySelector("form.ac-edit");
  if (f) {
    acFormRole(f, "e");
    f.onsubmit = e => { e.preventDefault(); const b = f.querySelector("[type=submit]");
      acRun(b, async () => {
        const fd = new FormData(f), body = {position: fd.get("position"), person: fd.get("person"), role: fd.get("role"), unit: fd.get("unit") || ""};
        const r = await acApi(`/api/accounts/${id}/update`, body);
        toast(r.message || "Saqlandi"); AC.open = null; await acReload(false);
      }); };
  }
}

/* ---------- yangi akkaunt ---------- */
function acFormDraw() {
  const box = $("#acFormBox"); if (!box) return;
  if (!AC.form || !AC.data.can_edit) { box.innerHTML = ""; return; }
  if (AC.created) {
    const c = AC.created;
    box.innerHTML = `<div class="card ac-new" id="acForm"><div class="ac-done" role="status">${ico("checkc", 20)}<div><b>Akkaunt yaratildi: ${esc(c.name)}</b>
      <span class="muted tiny">Kirish ro'yxatida paydo bo'ldi. Telegram ulash kodi: <code>${esc(c.link_code)}</code></span>${acPwBox(c.password)}
      <div class="ac-fb"><button type="button" class="btn sm" id="acAgain">${ico("plus", 15)} Yana yaratish</button><button type="button" class="btn sm ghost" id="acDone">Yopish</button></div></div></div></div>`;
    hydrateIcons(box); acCopyBind(box);
    $("#acAgain").onclick = () => { AC.created = null; acFormDraw(); $("#acfPos")?.focus(); };
    $("#acDone").onclick = () => { AC.created = null; AC.form = false; $("#acNew")?.setAttribute("aria-expanded", "false"); acFormDraw(); };
    return;
  }
  box.innerHTML = `<form class="card ac-new ac-form" id="acForm" novalidate aria-labelledby="acFormH">
      <h3 id="acFormH">${ico("plus", 18)} Yangi akkaunt</h3>
      <p class="muted tiny ac-hint">Vaqtinchalik parol avtomatik yaratiladi va faqat bir marta ko'rsatiladi. Rahbariyat lavozimlari (rektor, prorektorlar, kengash, kotib) va AT boshlig'i roli bu yerdan berilmaydi — faqat server administratori orqali.</p>
      ${acFields({}, "f")}
      <div class="ac-fb"><button class="btn sm primary" type="submit">${ico("check", 15)} Yaratish</button><button type="button" class="btn sm ghost" id="acCancel">Bekor qilish</button></div>
      <p class="ac-err" role="alert" hidden></p></form>`;
  hydrateIcons(box);
  const f = $("#acForm"); acFormRole(f, "f");
  $("#acCancel").onclick = () => { AC.form = false; $("#acNew")?.setAttribute("aria-expanded", "false"); acFormDraw(); $("#acNew")?.focus(); };
  f.onsubmit = e => { e.preventDefault(); const b = f.querySelector("[type=submit]");
    acRun(b, async () => {
      const fd = new FormData(f), body = {position: fd.get("position"), person: fd.get("person"), role: fd.get("role"), unit: fd.get("unit") || ""};
      const r = await acApi("/api/accounts", body);
      AC.created = {id: r.id, password: r.password, link_code: r.link_code, name: body.person || body.position};
      await acReload(false); acFormDraw();
    }); };
}

/* ---------- yuklash ---------- */
async function acReload(manual, keepOpen) {
  const open = AC.open;
  AC.data = await acApi("/api/accounts");
  if (keepOpen && open && AC.data.items.some(i => i.id === open.id)) AC.open = open; else if (!keepOpen) AC.open = null;
  if (manual) { acShell(); toast("Yangilandi"); return; }
  acStats(); acTable();
}
async function renderAccounts() {
  const el = $("#v-accounts");
  AC.open = null; AC.created = null; AC.form = false;
  if (!AC.data) el.innerHTML = `<p class="muted">Yuklanmoqda…</p>`;
  AC.data = await acApi("/api/accounts");
  acShell();
}
