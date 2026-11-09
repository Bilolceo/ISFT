# Kirish sahifasi variantlari — umumiy shartnoma

Har bir variant N (1..3; 4-variant olib tashlangan) ikki fayldan iborat:
- `static/login/vN.js` — `window.LOGIN_HTML = \`...\`` (#login ichiga qo'yiladigan markup) va ixtiyoriy `window.LOGIN_AFTER = function(){...}` (app.js yuklangandan keyin chaqiriladi).
- `static/login/vN.css` — faqat `.login.lvN` ichida skoplangan uslublar (#login elementi `login lvN` klassiga ega).

Variant `?login=N` bilan ochiladi (localStorage "jarvis-login" ga yoziladi). Pastda markazda variant almashtirgich bor (fixed, bottom 16px, ~46px) — muhim tugmalarni uning ostiga qo'ymang.

## app.js kutadigan id'lar (majburiy, bitta nusxada)
- `#lvlTabs` — bo'sh konteyner; app.js 4 ta `<button data-l="1..4">` (Rahbariyat, Prorektorlar, Bo'limlar, Fakultet) qo'yadi va tanlanganiga `.on` beradi.
- `#roleSearch` — input (qidiruv); app.js `oninput` bog'laydi.
- `#roleList` — app.js to'ldiradi: `.role-row(.sel)[data-id] > span.avatar.l{1-4} + div>(b, small) + span.chk`; topilmasa `.role-empty`; skroll bo'lsa ro'yxatga `.fade` klassi.
- **PIN o'rniga PAROL** (2026-11-08 o'zgarishi):
  - `#pwWrap` — parol maydoni o'rami (input + ko'z tugmasi shu ichida); xato parolda app.js unga `.err` klassini 450ms qo'shadi (silkinish animatsiyasini variant CSS'i beradi).
  - `#password` — `<input type="password" autocomplete="current-password">`; app.js sinov rejimida uni `Isft2026` bilan oldindan to'ldiradi; Enter → kirish.
  - `#pwEye` — tugma; app.js inputni text/password qilib almashtiradi, tugmaga `.on` va `aria-pressed` beradi.
  - Sinov rejimi matni: "Sinov rejimi: parol Isft2026". `#otp`, `#pin`, `#pinEye`, `#pin1` endi YO'Q.
- `#loginBtn` (button, rol tanlanmaguncha disabled, kirish paytida `data-busy`) ichida `<span id="loginTxt">Kirish</span>`.
- `<span data-ico="nom">` — app.js SVG ikonkaga aylantiradi (ICONS: dashboard chat tasks report folder languages wrench camera shield history server arrow info switch menu sun moon monitor send check calendar spark alert bolt cap money pin search checkc list eye lock unlock chart globe book clock phone mail file user users x play refresh trend_up trend_dn qr flag gift).

## LOGIN_AFTER ichida foydalanish mumkin bo'lgan globallar
`USERS` (/api/users ro'yxati: {id,name,role,level}), `LVL`, `selUser`, `LVL_TABS`, `initials()`, `personOf()`, `esc()`, `ico()`, `drawRoles()`, `showLogin()`, `doLogin()`, `toast()`, `$()`, `DEMO_PW`.
Funksiyani almashtirish: `const orig = window.drawRoles; window.drawRoles = function(){ orig(); /* qo'shimcha */ };` (global funksiya deklaratsiyalari window xususiyati — ichki chaqiruvlar ham yangisini oladi).
`selUser`/`LVL` — `let` globallar: nomi bilan o'qish/yozish mumkin (`selUser = 5`), `window.selUser` EMAS.

## Qoidalar
- Matn — o'zbek tilida (lotin). Kirishdan oldin shaxsiy yoki ichki raqamlar ko'rsatilmaydi (faqat ochiq: institut nomi, sana/vaqt, tizim holati).
- Tashqi resurs (CDN, rasm, shrift) yo'q — hammasi lokal. Shrift: Manrope (style.css'da yuklangan), `var(--font)`.
- O'lchamlar: 1512×860 va 1280×720 da vertikal skrollsiz; 390×844 telefon; sahifa gorizontal skrollsiz.
- Qorong'i rejim (`html[data-theme="dark"]`) buzilmasin. Klaviatura va fokus holatlari ko'rinsin. `prefers-reduced-motion` hurmat qilinsin.
