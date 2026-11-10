/* =====================================================================
   Sahifa izohlarini ixchamlash (UX tahlili: «hammayoq bijr-bijr»):
   sarlavha (h2) ostidagi uzun izoh — bitta qisqa jumla ko'rinadi, qolgani «ⓘ Qanday ishlaydi» ortida;
   boshqa bo'limga yo'llovchi jumlalar («… «X»da») olib tashlanadi — menyu nomlari endi o'zi tushunarli.
   Faqat matnli izohlarga tegadi (ichida tugma/teg bo'lsa — o'zgartirilmaydi).
   ===================================================================== */
(function () {
  const main = document.querySelector("main"); if (!main) return;
  const SEL = "h2 + .muted:not([data-dn]), h2 + p:not([data-dn])";
  const INLINE = new Set(["B", "STRONG", "I", "EM", "BR"]);
  const XREF = /«[^»]{2,40}»\s?(da|ga|dan|ning|bo'limida|sahifasida)\b/i;
  const sentences = t => t.split(/(?<=[.!?])\s+(?=[A-ZА-ЯЎҚҒҲO'«"0-9])/u).map(x => x.trim()).filter(Boolean);
  function fix(el) {
    el.dataset.dn = "1";
    if ([...el.children].some(c => !INLINE.has(c.tagName))) return;
    const txt = el.textContent.replace(/\s+/g, " ").trim();
    let ss = sentences(txt).filter(s => !XREF.test(s));
    if (!ss.length) { el.textContent = ""; return; }
    const full = ss.join(" ");
    if (full.length <= 110 && ss.length <= 1) { if (full !== txt) el.textContent = full; return; }
    let first = ss[0], rest = ss.slice(1).join(" ");
    if (first.length > 140) {
      const cut = first.lastIndexOf(" ", 110);
      rest = (first.slice(cut + 1) + " " + rest).trim(); first = first.slice(0, cut) + " …";
    }
    if (!rest) { el.textContent = first; return; }
    el.textContent = "";
    const a = document.createElement("span"); a.textContent = first + " ";
    const m = document.createElement("span"); m.className = "dn-more"; m.textContent = rest + " ";
    const b = document.createElement("button"); b.type = "button"; b.className = "dn-tg"; b.textContent = "ⓘ Qanday ishlaydi";
    b.setAttribute("aria-expanded", "false");
    b.onclick = () => { const o = el.classList.toggle("dn-open"); b.textContent = o ? "Yig'ish" : "ⓘ Qanday ishlaydi"; b.setAttribute("aria-expanded", String(o)); };
    el.append(a, m, b);
  }
  let t;
  const run = () => main.querySelectorAll(SEL).forEach(fix);
  new MutationObserver(() => { clearTimeout(t); t = setTimeout(run, 60); }).observe(main, {childList: true, subtree: true});
  run();
})();
