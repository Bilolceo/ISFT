/* =====================================================================
   Umumiy «dars tanlagich»: kurs (1–4) → ta'lim yo'nalishi → fan → dars (L1, A1 …). Qo'lda yozish yo'q — faqat tanlash.
   Ikki joyda ishlatiladi: «Taqdimot» (taqdimot.js — o'qituvchining O'Z fanlari, /api/taqdimot/lessons) va «Dars tayyorlash» → «Fanlar» daraxti (dars.js dsSubjects —
   kurs / yo'nalish bosqichlarini lpLevels hisoblaydi). Qatorlar /api/paket/courses bilan bir xil: {id, subject, direction, dir_code, code, course, dept, teacher, lessons[]}.
   Unikal kod: fan — «<kurs>_<YO'NALISH>_<fan>» (2_ATT_dasturiyinjiniring), dars — fan kodi + «_L2» (serverdan: full_code).
   Global: lpLevels(all, st), lpPicker(box, {courses, value, onChange, disabled}). app.js yordamchilari: esc.
   ===================================================================== */
if (!document.querySelector('link[href="lesson_picker.css"]')) document.head.insertAdjacentHTML("beforeend", '<link rel="stylesheet" href="lesson_picker.css">');

/* kurs → yo'nalish → fan bosqichlari: st = {kurs, dir} joyida to'g'rilanadi (bitta kurs / bitta yo'nalish — bosqich o'tkaziladi, yaroqsiz tanlov tozalanadi) */
function lpLevels(all, st) {
  const kurslar = [...new Set(all.map(r => r.course))].sort((a, b) => a - b);
  if (kurslar.length === 1) st.kurs = kurslar[0];
  if (st.kurs && !kurslar.includes(st.kurs)) st.kurs = 0;
  const inK = st.kurs ? all.filter(r => r.course === st.kurs) : [];
  const dirs = [...new Set(inK.map(r => r.direction))].sort((a, b) => a.localeCompare(b, "uz"));
  if (st.kurs && dirs.length === 1) st.dir = dirs[0];
  if (st.dir && !dirs.includes(st.dir)) st.dir = "";
  const rs = st.dir ? inK.filter(r => r.direction === st.dir).sort((a, b) => (a.subject || "").localeCompare(b.subject || "", "uz")) : [];
  return {kurslar, inK, dirs, rs};
}

function lpPicker(box, o) {
  const all = o.courses || [], st = {kurs: 0, dir: "", cid: 0, lkey: 0};
  const v0 = o.value && all.find(r => r.id === o.value.cid);
  if (v0) Object.assign(st, {kurs: v0.course, dir: v0.direction, cid: v0.id, lkey: o.value.lkey || 0});
  const uid = "lp" + Math.random().toString(36).slice(2, 7);
  const sel = () => {
    const co = all.find(r => r.id === st.cid), l = co && (co.lessons || []).find(x => x.key === st.lkey);
    return co && l ? {cid: co.id, lkey: l.key, course: co, lesson: l} : null;
  };
  const ctl = {get: sel, el: box};
  const opt = (v, t, cur) => `<option value="${esc(String(v))}" title="${esc(t)}" ${String(v) === String(cur) ? "selected" : ""}>${esc(t)}</option>`;
  const dis = () => o.disabled ? "disabled" : "";
  /* DOM BIR MARTA quriladi (select'lar va aria-live bloki qayta yaratilmaydi — fokus, klaviatura strelkalari va ekran o'qigich buzilmaydi); keyin faqat bog'liq ro'yxatlar yangilanadi */
  box.innerHTML = `<div class="lp" data-lp="${uid}">
      <div class="lp-grid">
        <label><span>1. Kurs</span><select data-lp-k aria-label="Kurs"></select></label>
        <label><span>2. Ta'lim yo'nalishi</span><select data-lp-d aria-label="Ta'lim yo'nalishi"></select></label>
        <label><span>3. Fan</span><select data-lp-f aria-label="Fan"></select></label>
        <label><span>4. Dars</span><select data-lp-l aria-label="Dars"></select></label>
      </div>
      ${!all.length ? `<p class="lp-empty">${esc(o.empty || "Sizning yuklamangizda fan yo'q.")}</p>` : ""}
      <div class="lp-live" aria-live="polite" data-lp-live></div></div>`;
  const q = s => box.querySelector(s), sk = q("[data-lp-k]"), sd = q("[data-lp-d]"), sf = q("[data-lp-f]"), sl = q("[data-lp-l]");
  const cache = new Map();
  const setOpts = (el, html, value) => {            /* ro'yxat o'zgarmagan bo'lsa tegilmaydi (foydalanuvchi ishlatayotgan select ochiq qoladi) */
    if (cache.get(el) !== html) { cache.set(el, html); el.innerHTML = html; }
    if (el.value !== String(value || "")) el.value = String(value || "");
    const o2 = el.selectedOptions[0]; el.title = o2 && o2.value ? o2.textContent : "";   /* uzun matn qirqilganda — to'liq matn tooltip'da */
  };
  function update() {
    const lv = lpLevels(all, st);
    if (st.cid && !lv.rs.some(r => r.id === st.cid)) { st.cid = 0; st.lkey = 0; }
    if (!st.cid && st.dir && lv.rs.length === 1) st.cid = lv.rs[0].id;            /* bitta fan — o'zi tanlanadi */
    const co = all.find(r => r.id === st.cid), ls = co ? co.lessons || [] : [];
    if (st.lkey && !ls.some(l => l.key === st.lkey)) st.lkey = 0;
    const grp = ls.reduce((a, l) => { (a[l.kind] = a[l.kind] || []).push(l); return a; }, {});
    const lessonOpts = Object.entries(grp).map(([k, xs]) => `<optgroup label="${k === "amaliy" ? "Amaliy mashg'ulotlar (A)" : "Ma'ruzalar (L)"}">${xs.map(l =>
      opt(l.key, `${l.code} — ${l.untitled ? "mavzu nomi kiritilmagan" : l.title}${l.sent_version ? ` · v${l.sent_version} yuborilgan` : ""}`, st.lkey)).join("")}</optgroup>`).join("");
    const lesson = co && ls.find(l => l.key === st.lkey), none = `<option value="">Tanlang…</option>`;
    setOpts(sk, none + lv.kurslar.map(k => opt(k, `${k}-kurs`, st.kurs)).join(""), st.kurs);
    setOpts(sd, none + lv.dirs.map(d => opt(d, `${d} (${(lv.inK.find(r => r.direction === d) || {}).dir_code || ""})`, st.dir)).join(""), st.dir);
    setOpts(sf, none + lv.rs.map(r => opt(r.id, `${r.subject} (${r.code || ""})`, st.cid)).join(""), st.cid);
    setOpts(sl, none + lessonOpts, st.lkey);
    sk.disabled = !!o.disabled; sd.disabled = !(st.kurs && !o.disabled); sf.disabled = !(st.dir && !o.disabled); sl.disabled = !(st.cid && !o.disabled);
    const live = q("[data-lp-live]");
    live.innerHTML = co && lesson ? `<div class="lp-info"><code title="Darsning unikal kodi">${esc(lesson.full_code)}</code>
        <span><small>Kafedra</small>${esc(co.dept || "—")}</span><span><small>O'qituvchi</small>${esc(co.teacher || "—")}</span><span><small>Fan</small>${esc(co.subject)}</span><span><small>Dars</small>${esc(lesson.code)}</span></div>` : "";
  }
  /* Fokus keyingi tanlovga FAQAT sichqoncha/sensor bilan tanlanganda o'tadi; klaviatura (strelkalar — Windows/Linux'da har bosish `change` beradi) tanlovni buzmaydi */
  let lastKey = 0;                                  /* oxirgi tugma vaqti (klaviatura/type-ahead oynasi ~1 s) */
  box.addEventListener("keydown", e => { if (e.target.tagName === "SELECT" && e.key !== "Tab" && !e.altKey && !e.ctrlKey && !e.metaKey) lastKey = Date.now(); }, true);
  box.addEventListener("pointerdown", () => { lastKey = 0; }, true);
  const chg = (el, apply, next) => el.onchange = e => {
    const adv = Date.now() - lastKey > 1200; lastKey = 0;
    apply(e.target.value); update(); emit();
    if (adv && next) { const n = next(); if (n && !n.disabled) n.focus(); }
  };
  chg(sk, v => { st.kurs = +v || 0; st.dir = ""; st.cid = 0; st.lkey = 0; }, () => sd);
  chg(sd, v => { st.dir = v; st.cid = 0; st.lkey = 0; }, () => sf);
  chg(sf, v => { st.cid = +v || 0; st.lkey = 0; }, () => sl);
  chg(sl, v => { st.lkey = +v || 0; }, null);
  const emit = () => o.onChange && o.onChange(sel());
  ctl.set = v => { const co = v && all.find(r => r.id === v.cid); if (co) Object.assign(st, {kurs: co.course, dir: co.direction, cid: co.id, lkey: v.lkey || 0}); update(); emit(); };
  ctl.disable = on => { o.disabled = !!on; update(); };
  update(); emit();
  return ctl;
}
