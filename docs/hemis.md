# HEMIS almashinuvi

**Kod:** `app/hemis.py` (API, qo'llash, farqlar, eksport, sifat), `app/hemis_plan.py` (dry-run rejasi), `app/hemis_map.py`
(fayl o'qish, ustun xaritasi, normallashtirish, kirill/lotin), `app/hemis_api.py` (API ulagichi skeleti), `static/hemis.js`, `static/hemis.css`,
`app/nazorat.py` (oxirgi bo'lim — «HEMIS almashinuvi»)
**Testlar:** `tests/test_hemis.py`, brauzer — `tools/hemis_check.js`
**API:** `/api/hemis/*` · **Audit resursi:** `hemis`

HEMIS — vazirlikning oliy ta'lim axborot tizimi, davlat oldidagi asosiy yozuv tizimi. ISFT Core uni almashtirmaydi: bu bo'lim ikkala
tizimdagi ma'lumot bir xil bo'lishini ta'minlaydi. HEMIS API hujjatlari bizda yo'q, shuning uchun almashinuv **fayl orqali**:
HEMIS'dan eksport → ISFT Core importi; ISFT Core egalik qiladigan ma'lumot → `.xlsx` → HEMIS'ga yuklash. API ulagichi tayyor
skelet, lekin **o'chiq va tasdiqlanmagan**.

## Huquqiy holat — YURIST TASDIQLASHI KERAK

| Hujjat | Holat |
|---|---|
| VMQ 30.12.2024 № 913 — nodavlat OTM o'z axborot tizimiga ega bo'lishi va uni HEMIS bilan integratsiya qilishi shart | **03.07.2026 dan bekor qilingan** (VMQ № 353) |
| VMQ № 353 (2026) | 913-sonni bekor qilgan. O'rniga qanday talab qo'yilgani (yangi qaror, vazirlik buyrug'i yoki talab umuman yo'qligi) **noma'lum** |

Yurist aniqlashi kerak:
1. VMQ 353 asl matni: 913-son to'liq bekor qilinganmi yoki talablar boshqa hujjatga ko'chirilganmi.
2. Nodavlat OTM uchun HEMIS'ga ma'lumot kiritish (talabalar, o'qituvchilar, baholar, davomat) majburiyati qaysi hujjatda va qaysi muddatlarda.
3. Ta'lim krediti, akkreditatsiya (1.5.3 «vazirlik tizimlari bilan integratsiya», 1.5.5 «ma'lumot to'g'riligi») talablari bekor
   qilinganmi.
4. Masofaviy talabalar davomatini LMS faolligidan hisoblash qoidasi rasmiy belgilanganmi (quyida — sozlanadigan, tasdiqlanmagan qoida).

Huquqiy talab qanday bo'lmasin, amalda ISFT HEMIS va ISFT Core'ni mos holda yuritishi shart: kredit, stipendiya, buyruqlar va hisobotlar
HEMIS'dagi ma'lumotga tayanadi.

## Kim nimani ko'radi

| Lavozim | Ko'radi | Amallar |
|---|---|---|
| Registrator ofisi boshlig'i (`talabalar`) | Hammasi | Import, qo'llash, farqlar bo'yicha qaror, eksport, sozlamalar, shablonlar, API token va tekshirish |
| Masofaviy ta'lim bo'limi boshlig'i (`masofaviy`) | Hammasi | Boshliq kabi |
| Registrator ofisi xodimi (`registrator_xodim`) | Hammasi | Import, qo'llash, farqlar, eksport (sozlamalar va API — yo'q) |
| Rektor | Faqat jamlangan sonlar (ochiq farqlar, muddati o'tganlar, sifat muammolari soni) — ism va HEMIS ID yo'q | — |
| Boshqalar | — (403) | — |

Har bir so'rov (rad etilganlari ham) audit jurnalida. Qo'llash, qaror, eksport — alohida audit yozuvi (`hemis: import qo'llandi`,
`hemis: farq hal qilindi`, `hemis: eksport tayyorlandi`).

## 1. Import (fayl → dry-run → qo'llash)

Turlar: **talabalar** (HEMIS ID, F.I.Sh., guruh, yo'nalish, kurs, ta'lim shakli — masofaviy ham, holat, fuqarolik, to'lov shakli),
**guruhlar**, **o'qituvchilar va xodimlar**, **o'quv yuklamasi** (o'qituvchi — guruh — fan — soat), **baholar** (HEMIS ID — fan — semestr — ball).

**Fayl o'qish (bag'rikeng):** `.xlsx` (birinchi varaq) yoki `.csv` (`;` `,` TAB; UTF-8, UTF-8 BOM, cp1251). Sarlavha birinchi 15 qator
ichidan topiladi (tepada hisobot nomi bo'lishi mumkin). Sarlavhalar o'zbek (lotin va kirill), rus, ingliz tillarida taniladi:
`HEMIS ID / Талаба ИД / ИД студента / Student ID`, `F.I.Sh. / Ф.И.Ш. / ФИО`, `Guruh / Гуруҳ / Группа`, `Ta'lim shakli / Форма обучения` va h.k.
(to'liq ro'yxat — `hemis_map.ALIASES`). F.I.Sh. alohida ustunlarda (Familiya / Ism / Otasining ismi) bo'lsa — yig'iladi. HEMIS ID Excel'da son
yoki `3.52E12` bo'lib kelsa ham matnga keltiriladi. **JShShIR (PINFL), pasport, telefon, manzil, tug'ilgan sana ustunlari o'qilmaydi**.

**Ustun xaritasi va profillar:** tanilmagan sarlavhani foydalanuvchi qo'lda moslaydi (yoki «e'tiborsiz»), xarita **profil** sifatida
saqlanadi va keyingi yuklashda tanlanadi. Majburiy maydon moslanmaguncha «Qo'llash» o'chiq.

**Dry-run (ko'rib chiqish)** — bazaga hech narsa yozilmaydi. Har qator bitta toifada:

| Toifa | Ma'nosi | Qo'llashda |
|---|---|---|
| Yangi | HEMIS'da bor, ISFT Core'da yo'q | Qo'shiladi (talaba — guruhi ISFT Core'da bo'lsa) |
| O'zgargan | ISFT Core'da bo'sh maydon, HEMIS'da qiymat bor | Maydon to'ldiriladi |
| Ziddiyatli | Ikkalasida qiymat bor va farqli **yoki** qator xatosi (noma'lum guruh, takror ID, tanilmagan qiymat, ball 0–100 dan tashqari) | Farq — **Farqlar navbatiga**; xatoli qator — o'tkazib yuboriladi |
| HEMIS'da topilmadi | ISFT Core'da bor (faol / akademik ta'til), faylda yo'q | **O'chirilmaydi** — `hemis_missing` ga ko'rib chiqish uchun |
| O'zgarmagan | Hamma maydon mos (ism faqat kirill/lotin yozuvida farqlansa ham) | — |

**Ko'lam:** «qisman» (standart) — «topilmadi» faqat fayldagi birliklar ichida hisoblanadi (talabalar — fayldagi guruhlar; guruhlar —
fayldagi fakultetlar; xodimlar — kafedralar; yuklama — o'qituvchilar; baholar — talaba + semestr). Bitta fakultet eksporti butun
institutni «topilmadi» qilmaydi. «To'liq» — fayl butun institut eksporti bo'lsa.

**Qo'llash** — bitta tranzaksiya (`BEGIN IMMEDIATE`): reja Core'ning shu paytdagi holati bo'yicha qayta hisoblanadi, yozuvlar qo'shiladi
va yangilanadi, har biri uchun **snapshot** (`hemis_snapshots`: jadval, qator, oldingi va keyingi qiymat), farqlar va «topilmadi»
belgilari, import holati va audit yozuvi. Istalgan xato — **hammasi qaytariladi**, import «ko'rib chiqilmoqda» holatida qoladi, xato matni
saqlanadi. Bir import ikki marta qo'llanmaydi (409); shu fayl (SHA-256) avval qo'llangan bo'lsa — ogohlantirish.

**Avtomatik yozish qoidasi:** ikkalasida qiymat bor va farqli bo'lsa — HEMIS qiymati **ustiga yozilmaydi**, navbatga tushadi. Registrator
xohlasa, ayrim maydonlarni avtomatik qilishi mumkin (`auto_fields`, masalan `["payment_type"]`).

## 2. Farqlar navbati

Maydon darajasidagi farqlar: talaba — F.I.Sh., guruh, ta'lim shakli, holat, fuqarolik, to'lov shakli; guruh — kurs, yo'nalish, bosqich,
ta'lim shakli; xodim — F.I.Sh., kafedra, lavozim, ilmiy daraja; baho — ball. Egasi — **Registrator ofisi boshlig'i** (`org_units.talabalar`).

**Normallashtirish:** holat (`Обучается`, `O'qimoqda` → `faol`; `Академический отпуск` → `akademik ta'til` …), ta'lim shakli
(`Дистанционная`, `Masofaviy` → `masofaviy` …), fuqarolik (`Гражданин РУз`, `O'zbekiston Respublikasi fuqarosi` → `UZ`, davlati yozilmagan
xorijiy — `XX`; ISFT Core'da bo'sh — `UZ` hisoblanadi). **Ism-sharif** (`hemis_map.name_key`): kirill → lotin, tutuq belgilari (o‘ o' oʻ),
rus kirilidagi Х = o'zbek H, қ/к, «ye/e», «ts/s», o'g'li / угли / оглы, so'zlar tartibi — farq hisoblanmaydi (faqat «yozuv farqi» soni);
otasining ismi qo'shilgani yoki boshqa ism — haqiqiy farq.

**Qarorlar** (har biri jurnalga — `hemis_diff_log` — va auditga):

| Qaror | Natija |
|---|---|
| HEMIS to'g'ri | ISFT Core yangilanadi (snapshot bilan) |
| ISFT Core to'g'ri (izoh majburiy) | Core o'zgarmaydi; farq «HEMIS'ga tuzatishlar» eksportiga tushadi |
| Qo'lda (qiymat + izoh) | Kiritilgan qiymat Core'ga yoziladi va tuzatishlar eksportiga tushadi |
| Mos keldi (avtomatik) | Keyingi importda HEMIS va Core qiymatlari bir xil bo'lsa, farq o'zi yopiladi |

Ommaviy qaror (ko'pi bilan 500 ta): «HEMIS to'g'ri» yoki «ISFT Core to'g'ri». Bir xil (tur, kalit, maydon) uchun bitta ochiq farq —
qayta importda ikkilanmaydi, qiymati yangilanadi. «HEMIS'da topilmadi» yozuvlari izoh bilan «ko'rib chiqildi» qilinadi; keyingi importda
faylda paydo bo'lsa — «qaytdi».

**Nazorat markazi** (`app/nazorat.py`, oxirgi bo'lim; rektor qoidasi `hemis_diff_days`, standart 7 kun):
- `hemis:farq` — N kundan ortiq hal qilinmagan farqlar soni (jamlangan, ismsiz);
- `hemis:topilmadi` — N kundan ortiq ko'rib chiqilmagan «HEMIS'da topilmadi» yozuvlari;
- `hemis:sifat` — takroriy HEMIS ID, HEMIS IDsiz faol talaba, masofaviy talaba boshqa shakldagi guruhda, guruhsiz talaba.

## 3. Eksport (.xlsx)

| Tur | Manba | Izoh |
|---|---|---|
| Oraliq ballar (LRS testlari) | `lrs_progress` (NEXTID / ISFT Core darslari), `dl_courses` → fan | O'rtacha LRS ball × maksimum / 100 (standart 30), kamida N baholangan dars. Siyosat bo'yicha o'chiriladi (`grade_rule.enabled`) |
| Masofaviy talabalar davomati | `dl_activity` (daqiqa), `lrs_statements` (haftalik soni) | **QOIDA TASDIQLANMAGAN:** haftada ≥ 30 daqiqa YOKI ≥ 3 LRS yozuvi → «Qatnashdi». Sozlanadi (`att_rule`) |
| Yuzma-yuz qaydnoma natijalari | `yy_assign`, imzolangan `yy_protocols` | Faqat yopilgan (imzolangan) sessiyalar |
| HEMIS'ga tuzatishlar | Farqlar navbati («ISFT Core to'g'ri», «qo'lda») | Eksport qilingandan keyin navbatdan chiqadi (qayta olish — «avval eksport qilinganlar ham») |

Fayl: «HEMIS» varag'i (shablon ustunlari — `TEMPLATES`, ustun nomlari boshliq tomonidan o'zgartiriladi: `POST /api/hemis/templates`)
va «Ma'lumot» varag'i (tur, vaqt, kim, qatorlar, qoida, ogohlantirish, **mazmun SHA-256** — sarlavha + qatorlar JSON ko'rinishida).
Faylning o'z **SHA-256** si eksport jurnalida (`hemis_exports`) va yuklab olishda `X-Content-SHA256` sarlavhasida; fayl diskda
(`data/hemis_exports/`) o'zgartirilgan bo'lsa yuklab berilmaydi (409). HEMIS'ning rasmiy yuklash shabloni bizda yo'q — ustunlar
HEMIS shabloni olingach moslanadi.

## 4. API ulagichi — TASDIQLANMAGAN

- Standart **o'chiq** (`api_enabled = false`). Yoqilmaguncha tarmoqqa hech narsa yuborilmaydi.
- Sozlamalar: bazaviy URL (faqat `http(s)://host`, login/parol va so'rov parametrlarisiz), tekshirish yo'li, avtorizatsiya sxemasi.
- **Token faqat `secret_store`da** (`data/secrets`, `cryptography` o'rnatilgan bo'lsa Fernet bilan shifrlangan) — bazada token ham,
  xeshi ham yo'q; sozlamaga «token: …» ko'rinishidagi matn yozilmaydi (400).
- «Ulanishni tekshirish» — **bitta zararsiz GET**, 8 s, yo'naltirishga ergashmaydi, javob tanasi o'qilmaydi va saqlanmaydi; natija —
  holat kodi, kechikish, Content-Type. Token faqat «tekshirishda tokenni yuborish» yoqilgan va manzil `https` bo'lsa yuboriladi.
  «Javob bor» — API ishlashini **tasdiqlamaydi**.
- `HemisAdapter` — izolyatsiya qilingan adapter: `fetch_students/groups/teachers/load/grades`, `push_grades/attendance`. Hozir har biri
  `NotImplementedError`. Hujjat olingach: adapter `hemis_map.FIELDS` formatidagi yozuvlarni qaytaradi va **xuddi fayl importi kabi**
  dry-run → qo'llash yo'lidan o'tadi (alohida yozish yo'li yo'q). Universitet HEMIS nusxalarida uchraydigan `…/rest/v1/…` yoki `api/v1`
  ko'rinishidagi yo'llar tasdiqlanmagan — kodda «ishlaydi» deb yozilmagan.

## 5. Ma'lumot sifati

Takroriy HEMIS ID · HEMIS IDsiz faol talabalar · HEMIS ID formati shubhali (`hemis_id_regex`, standart `^\d{10,16}$` — TASDIQLANMAGAN) ·
masofaviy talaba masofaviy bo'lmagan guruhda · masofaviy guruhda boshqa shakldagi talaba · guruhsiz talaba · takroriy xodim HEMIS ID ·
ko'rib chiqilmagan «HEMIS'da topilmadi». Boshqaruvchilar namunalarni (20 tagacha) ko'radi, rektor — faqat sonlarni.

## Jadvallar

`hemis_settings` (token yo'q), `hemis_profiles`, `hemis_imports` (fayl SHA-256, xarita, xom qatorlar — qo'llangach o'chiriladi, natija),
`hemis_snapshots`, `hemis_diffs`, `hemis_diff_log`, `hemis_missing`, `hemis_exports`. Qo'shilgan ustunlar: `groups_.hemis_id`,
`teachers.hemis_id` (va `students.citizenship`, agar bo'lmasa).

## Cheklovlar (ochiq savollar)

- HEMIS eksport fayllarining aniq ustunlari va HEMIS'ga yuklash shablonlari — haqiqiy fayl namunasi bilan tekshirilmagan (sintetik
  fayllarda sinalgan). Birinchi haqiqiy eksportda profil saqlab qo'yish tavsiya etiladi.
- Qo'llangan importni bir tugma bilan qaytarish yo'q: snapshot saqlanadi (kim, nima, oldin/keyin), lekin tiklash — qo'lda.
- Davomat va baho eksporti qoidalari vazirlik bilan kelishilmagan.
- Guruh / kafedra / fakultet nomlari bo'yicha moslashtirish (HEMIS ID'lar ISFT Core'ga hali kiritilmagan).

## Vazirlikka / HEMIS qo'llab-quvvatlash xizmatiga so'rov (namuna)

> **Kimga:** O'zbekiston Respublikasi Oliy ta'lim, fan va innovatsiyalar vazirligi — HEMIS tizimi bo'yicha mas'ul bo'linma
> (Raqamli ta'lim texnologiyalari markazi / HEMIS texnik qo'llab-quvvatlash xizmati)
>
> **Mavzu:** HEMIS bilan ma'lumot almashinuvi bo'yicha texnik hujjatlar va kirish huquqini so'rash
>
> Hurmatli rahbar!
>
> [OTM to'liq nomi] (litsenziya № ___) o'quv jarayonini boshqarishda ichki axborot tizimidan foydalanadi va talabalar, o'qituvchilar,
> baholar hamda davomat ma'lumotlarini HEMIS bilan mos holda yuritishni ta'minlamoqchi. Shu maqsadda quyidagilarni so'raymiz:
>
> 1. HEMIS tashqi integratsiya API'sining rasmiy hujjatlari (endpointlar ro'yxati, ma'lumot formatlari, versiyalash, so'rovlar chegarasi),
>    test (sandbox) muhiti va OTM uchun kirish (token) berish tartibi.
> 2. HEMIS'ga ma'lumot yuklash uchun fayl shablonlari (baholar, davomat, talabalar kontingenti o'zgarishlari) va ularning joriy versiyalari.
> 3. Masofaviy ta'lim shaklidagi talabalar davomatini LMS faolligi asosida qayd etish bo'yicha amaldagi talablar (agar mavjud bo'lsa).
> 4. VMQ № 913 bekor qilinganidan (VMQ № 353, 03.07.2026) keyin nodavlat OTM'larning HEMIS bilan integratsiyasi bo'yicha amaldagi
>    normativ talablar va texnik talablar hujjati.
> 5. Shaxsga doir ma'lumotlarni himoya qilish talablari (ma'lumot uzatish kanali, shifrlash, IP cheklovlari).
>
> Texnik aloqa uchun mas'ul xodim: [F.I.Sh., lavozim, telefon, e-pochta].
>
> Hurmat bilan, [Rektor F.I.Sh.], [sana]

So'rov rasmiy xat sifatida Devonxona orqali yuboriladi; javob olingach `app/hemis_api.py` adapteri to'ldiriladi, endpointlar test muhitida
sinaladi va shundan keyingina `VERIFIED = True` qilinadi.
