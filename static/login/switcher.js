/* Dizayn variantlarini almashtirish paneli — faqat kirish sahifasida ko'rinadi (#login ichida). */
(function () {
  const L = document.getElementById("login"); if (!L) return;
  const V = [["1", "Markaziy"], ["2", "Kiosk"], ["3", "Ko'rinish"]];
  const el = document.createElement("div");
  el.className = "lv-switch"; el.setAttribute("role", "group"); el.setAttribute("aria-label", "Kirish sahifasi dizayn varianti");
  el.innerHTML = `<span class="lv-sw-t">Dizayn</span>` + V.map(([k, t]) =>
    `<a href="?login=${k}" class="${window.LV === k ? "on" : ""}" aria-current="${window.LV === k}"><b>${k}</b><span>${t}</span></a>`).join("");
  L.appendChild(el);
})();
