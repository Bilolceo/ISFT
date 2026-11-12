/* Talaba kabineti: «Amaliyot» sahifasi (app/amaliyot.py → /api/talaba/amaliyot). talaba.js dagi TK.addPage kengaytmasi orqali qo'shiladi:
   o'z amaliyoti (baza, rahbarlar, muddatlar, yo'llanma), kundalik yozish, hisobot topshirish, baho. */
(function () {
  "use strict";
  if (!window.TK) return;
  const { api, esc, toast, dmy, head } = window.TK;
  const ST_CLS = { biriktirildi: "", boshlandi: "info", hisobot: "warn", baholandi: "ok", qaytarildi: "bad" };
  const FLAG = { hisobot_kechikdi: "Hisobot muddati o'tgan", boshlanmagan: "Amaliyotga chiqish belgilanmagan" };
  async function page(m) {
    const d = await api("/api/talaba/amaliyot");
    const pend = d.pending.length ? `<div class="tk-card"><b>Rejalashtirilgan amaliyot</b><div class="tk-small tk-muted">${d.pending.map((p) => `${esc(p.title)}: ${dmy(p.start)} – ${dmy(p.end)}`).join("<br>")}
      <br>Baza hali biriktirilmagan — Amaliyot bo'limi xabar beradi.</div></div>` : "";
    if (!d.items.length) { m.innerHTML = head("Amaliyot", "Amaliyot bazasi, rahbarlar, kundalik va hisobot") + (pend || `<div class="tk-card"><div class="tk-empty">Sizga hali amaliyot biriktirilmagan</div></div>`); return; }
    m.innerHTML = head("Amaliyot", "Amaliyot bazasi, rahbarlar, kundalik va hisobot") + pend + d.items.map((a) => `
      <div class="tk-card" data-a="${a.id}">
        <div style="display:flex;justify-content:space-between;gap:8px;flex-wrap:wrap"><b>${esc(a.title)}</b><span class="tk-pill ${ST_CLS[a.status] || ""}">${esc(a.status_name)}</span></div>
        <div class="tk-small tk-muted">${dmy(a.start)} – ${dmy(a.end)} · hisobot muddati ${dmy(a.report_due)} · ${a.credits} kredit</div>
        ${a.flags.filter((f) => FLAG[f]).map((f) => `<div class="tk-err" style="margin-top:6px">${esc(FLAG[f])}</div>`).join("")}
        <dl class="tk-kv" style="margin-top:10px">
          <dt>Baza</dt><dd>${esc(a.base || "—")}${a.address ? `<br><small class="tk-muted">${esc(a.address)}</small>` : ""}</dd>
          <dt>Tashkilotdan rahbar</dt><dd>${esc(a.org_supervisor || "—")} ${esc(a.org_phone || "")}</dd>
          <dt>Kafedradan rahbar</dt><dd>${esc(a.kaf_supervisor || "—")}</dd>
          <dt>Yo'llanma</dt><dd>${a.doc_reg ? esc(a.doc_reg) + " — Amaliyot bo'limidan oling" : "hali berilmagan"}</dd>
          ${a.score != null ? `<dt>Baho</dt><dd><b>${a.score}</b> ball («${esc(a.letter)}»)</dd>` : ""}
          ${a.return_note ? `<dt>Qaytarilgan</dt><dd class="tk-err">${esc(a.return_note)}</dd>` : ""}
        </dl>
        <div style="margin-top:12px"><b>Kundalik</b> <span class="tk-small tk-muted">(${a.diary_n} ta yozuv)</span></div>
        <div class="tk-small" style="display:flex;flex-direction:column;gap:6px;margin-top:6px;max-height:260px;overflow:auto">
          ${a.diary.map((x) => `<div><b>${dmy(x.day)}</b> ${esc(x.text)} <span class="tk-muted">— ${esc(x.author_kind === "rahbar" ? "rahbar: " + x.author : "siz")}</span></div>`).join("") || `<span class="tk-muted">Hali yozuv yo'q</span>`}
        </div>
        ${a.can_diary ? `<form class="am-t-diary" style="display:flex;gap:8px;margin-top:8px;flex-wrap:wrap">${a.diary_note ? `<div class="tk-small tk-muted" style="flex-basis:100%">${esc(a.diary_note)}</div>` : ""}<input class="tk-in" name="day" type="date" value="${esc(a.diary_day || d.today)}" min="${esc(a.diary_min || "")}" max="${esc(a.diary_max || d.today)}" style="max-width:170px">
          <input class="tk-in" name="text" maxlength="2000" placeholder="${a.ended ? "Shu kuni nima qildingiz?" : "Bugun nima qildingiz?"}" style="flex:1;min-width:180px"><button class="btn sm" type="submit">Yozish</button></form>` : ""}
        ${a.can_report ? `<form class="am-t-report" style="margin-top:12px"><label class="tk-field"><span>Amaliyot hisoboti (kamida ${d.rules.report_min_chars} belgi): bajarilgan ishlar, olingan ko'nikmalar, xulosa</span>
          <textarea name="text" rows="5" maxlength="4000"></textarea></label><button class="btn sm primary" type="submit" style="margin-top:6px">Hisobotni topshirish</button>
          <div class="tk-small tk-muted">Tashkilot tavsifnomasi va imzolangan kundalik qog'ozda kafedra rahbariga topshiriladi.</div></form>` : ""}
      </div>`).join("");
    m.querySelectorAll("form.am-t-diary").forEach((f) => f.onsubmit = async (e) => {
      e.preventDefault(); const id = f.closest("[data-a]").dataset.a;
      try { await api(`/api/talaba/amaliyot/${id}/diary`, { method: "POST", body: { text: f.text.value, day: f.day.value } }); toast("Kundalikka yozildi"); page(m); }
      catch (er) { toast(er.message, true); }
    });
    m.querySelectorAll("form.am-t-report").forEach((f) => f.onsubmit = async (e) => {
      e.preventDefault(); const id = f.closest("[data-a]").dataset.a;
      try { const r = await api(`/api/talaba/amaliyot/${id}/report`, { method: "POST", body: { text: f.text.value } });
        toast(r.late ? "Hisobot topshirildi (muddatdan kech)" : "Hisobot topshirildi — kafedra rahbari baholaydi"); page(m); }
      catch (er) { toast(er.message, true); }
    });
  }
  window.TK.addPage({ k: "amaliyot", t: "Amaliyot", s: "Amaliyot", i: "practice", path: "M3 7h18v13H3zM8 7V4h8v3M3 12h18", f: page });
})();
