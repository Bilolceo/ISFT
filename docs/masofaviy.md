# Masofaviy ta'lim moduli

**Kod:** `app/masofaviy.py`, `static/masofaviy.js`, `static/masofaviy.css`
**Testlar:** `tests/test_masofaviy.py` (100 ta tekshiruv)
**API:** `/api/masofaviy/*`
**Ruxsat resursi:** `rbac.DISTANCE`

## Nima uchun

Masofaviy ta'lim bo'limi bilan bo'lgan uchrashuvda (2026-11) ikkita asosiy talab aytildi:

1. **Talabalar holati.** Kim aktiv, kim noaktiv, kim videokonferensiyaga kirgan, kim o'zlashtirgan, kimning buyrug'i chiqmagan — hammasi bitta joyda.
2. **O'quv kontenti monitoringi.** Bo'limning nazorat ro'yxati (checklist) bo'yicha qaysi kafedra va qaysi o'qituvchi materialni bermagan, qaysi yo'nalishga material yuklanmagan, bugun kimning muddati tugaydi.

Ularning ustiga qo'shimcha so'rovlar:

- xavf ostidagilar ro'yxati;
- haftalik ko'rinish;
- AI xulosa va hisobot;
- bo'lim xodimlariga topshiriq berish.

Bo'lim xodimlariga topshiriq berish uchun yangi narsa qurilmadi: mavjud `directives` (Topshiriqlar) moduli ishlatiladi.

## Kim nimani ko'radi

| Lavozim | Ko'rinish | Amallar |
|---|---|---|
| Masofaviy ta'lim bo'limi boshlig'i (`masofaviy`) | To'liq: talabalarning ismlari, kartalari, barcha bo'limlar | Materialni tasdiqlash yoki qaytarish, kafedraga topshiriq, import, qoidalarni o'zgartirish, AI xulosa, hisobot |
| Bo'lim xodimi (`masofaviy_xodim`) | To'liq | Materialni tasdiqlash yoki qaytarish, import, AI xulosa, hisobot. Kafedraga topshiriq bera olmaydi va qoidalarni o'zgartira olmaydi — bular boshliqda |
| Rektor, o'quv ishlari prorektori | Jamlangan ko'rinish: talabalarning ismlari va individual ro'yxati yo'q | AI xulosa, hisobot (ismlarsiz nusxa) |
| Kafedra mudiri | Faqat o'z kafedrasining materiallari | — |
| O'qituvchi | Faqat o'z materiallari | Materialni "Yuklandi" deb belgilash (LMS havolasi bilan) |

Har bir so'rov audit jurnaliga yoziladi, rad etilgan so'rovlar ham. Telegram'ga bu modul ma'lumoti chiqmaydi.

## Ma'lumotlar

| Jadval | Mazmuni |
|---|---|
| `dl_courses` | Fan × yo'nalish × kurs (masofaviy guruhlar). Mas'ul o'qituvchi — shu fandan eng ko'p guruhda dars beradigan o'qituvchi; kafedra — o'sha o'qituvchining kafedrasi. |
| `dl_items` | Har bir mavzu × material turi (ma'ruza matni, taqdimot, videodars, test) × muddat × holat. Holat: `kutilmoqda` → `yuklandi` → `tasdiqlandi` yoki `qaytarildi`. |
| `dl_activity` | Haftalik LMS faolligi: kirishlar soni, daqiqalar, ko'rilgan materiallar, videokonferensiyalar (qatnashgan/jami), topshiriqlar, oxirgi kirish. |
| `dl_policy` | Chegaralar: noaktiv deb hisoblash uchun kunlar, videokonferensiya va topshiriqlar bo'yicha minimal foiz, hisoblash oynasi (haftalar), "yaqinlashmoqda" kunlari, material qancha oldin yuklanishi kerak, notekis faollik (necha haftadan nechtasida kirgan) va semestr boshidagi minimal kirishlar. |
| `dl_log`, `dl_imports`, `dl_reminders`, `dl_ai` | Material tarixi, importlar, kafedralarga yuborilgan topshiriqlar, AI xulosalar keshi. |
| `dl_meta` | `seed_v1` (demo yaratilgan vaqt), `source` (`demo` yoki `import`), `anchor` (demo sanalari bog'langan hafta dushanbasi). |

Mavzu nomlari quyidagi tartibda olinadi:

1. tasdiqlangan sillabus;
2. tayanch katalog (namuna);
3. ikkalasi bo'lmasa — "N-mavzu".

Ko'rsatkichlar mavjud manbalardan hisoblanadi, yangi qoidalar dvigateli yozilmadi:

- **O'zlashtirish** — baholar jadvalidan (`academic_rules`):
  - joriy semestr oraliq nazoratidan `ORALIQ_MIN` (12) baldan past olgan fanlar;
  - akademik qarzlar (`debt_where`).
- **Buyruq holati** — Buyruqlar modulidan:
  - `orders.analyze` topgan nomuvofiqliklar (qabul, kursga o'tkazish yoki ta'til buyrug'i yo'q, ziddiyatli buyruqlar);
  - imzolanmagan buyruq loyihalari.

## Xavf qoidalari

Har bir sababning og'irligi bor (1–3). Talabaning ballari shu og'irliklarning yig'indisi:

- **4 va undan yuqori** — yuqori xavf;
- **2–3** — o'rta xavf.

| Sabab | Og'irlik |
|---|---|
| LMS'ga umuman kirmagan | 3 |
| N kundan beri kirmagan | 2 (N ikki baravardan oshsa — 3) |
| Videokonferensiyaga qatnashishi minimal foizdan past | 2 |
| Oraliq nazoratdan past ball | 1 (2 va undan ko'p fanda — 2) |
| Akademik qarz | 1 (2 va undan ko'p fanda — 2) |
| Buyruq nomuvofiqligi | 2 |
| Imzolanmagan buyruq | 1 |
| LMS topshiriqlari bajarilmagan (faqat aktiv talabalar uchun) | 1 |
| Notekis faollik: oxirgi `irregular_weeks` (6) ta to'liq haftadan `irregular_min_active` (3) tadan kamida kirgan (faqat aktiv talabalar uchun) | 1 |
| Semestr boshida sust: birinchi 4 haftada kirishlar `early_min_logins` (4) dan kam yoki topshiriqlar `tasks_min_pct` dan past (faqat aktiv talabalar uchun) | 1 |

Akademik ta'tildagi talabalarga faollik bo'yicha xavf qo'yilmaydi.

**Erta ogohlantirish signallari.** O'quv analitikasi tadqiqotlarida eng kuchli signallar: kirish chastotasi, topshiriqlarni o'z vaqtida topshirish, haftadan-haftaga barqarorlik va birinchi 4 haftadagi faollik. Oxirgi ikkitasi uchun:

- **Notekis faollik.** Joriy hafta hisobga olinmaydi (hali tugamagan — aks holda dushanba kuni hamma "notekis" bo'lardi). Faollik ma'lumoti butun oynani qamrasagina hisoblanadi; eksportda bo'sh hafta qatori bo'lmasa, u hafta "kirmagan" deb olinadi.
- **Semestr boshida sust.** Oyna — semestr boshi (`academic_rules.term_dates`) haftasidan 4 hafta. Faollik ma'lumoti keyinroq boshlansa (masalan, LMS eksporti semestr o'rtasidan), oyna eng birinchi faollik haftasidan boshlanadi. Oyna tugamaguncha bu sabab qo'yilmaydi.
- Ikkalasi ham faqat **aktiv** talabalarga qo'yiladi: kirmagan va noaktiv talabalar o'z sababi bilan allaqachon belgilangan, ikki marta sanalmaydi.

## AI xulosa

- **Nima yuboriladi.** Claude'ga faqat jamlangan raqamlar yuboriladi (`_facts`). Talabaning ismi, HEMIS ID va telefoni yuborilmaydi — bu test bilan tekshiriladi.
- **Raqamlar tekshiriladi.** AI matnidagi har bir raqam faktlar bilan solishtiriladi. Faktlarda yo'q raqam bo'lgan jumla olib tashlanadi va foydalanuvchiga "N ta jumla olib tashlandi" deb ko'rsatiladi.
  - xulosa, asosiy faktlar va xavflar — qat'iy: kichik son ham ("5 ta kafedra to'xtagan") faktlarda bo'lishi shart;
  - tavsiyalar — 7 gacha kichik sonlarga ruxsat ("3 kun ichida");
  - "N%" ko'rinishidagi son faqat faktlardagi foiz maydoni (kalitida "foiz") qiymatiga mos bo'lsa o'tadi: 12 soni faktlarda boshqa ma'noda bo'lsa ham, "12%" o'tmaydi;
  - sana faqat faktlardagi sana bilan aynan bir xil bo'lsa o'tadi; "2-kurs", "1-semestr" kabi yorliqlar raqam hisoblanmaydi.
- **Kalit bo'lmasa yoki AI ishlamasa.** Qoidalar asosidagi xulosa ko'rsatiladi, ish to'xtamaydi. AI javobi buzuq yoki bo'sh bo'lsa (yoki tekshiruvdan keyin hech narsa qolmasa) ham shunday.
- **Kesh.** Ma'lumot o'zgarmagan bo'lsa, saqlangan xulosa qaytariladi va qayta pul to'lanmaydi. Keshga faqat muvaffaqiyatli AI javobi yoki (kalit yo'q bo'lganda) qoidaviy xulosa yoziladi. AI xatosi keshlanmaydi — keyingi so'rovda AI qayta uriniladi. Kalit bor bo'lsa, keshdan faqat AI xulosasi olinadi.
- **Hisobot.** .docx'ga faqat joriy faktlarga mos (bir xil digest) xulosa kiritiladi. Ma'lumot o'zgargan bo'lsa, eski xulosa kiritilmaydi — uning sanasi va yangilash haqida izoh yoziladi.
- **Model.** `ISFT_CORE_DL_MODEL` o'zgaruvchisi bilan tanlanadi, standart qiymati `claude-opus-5-5`.

## Import

**LMS faolligi:** `hemis_id; hafta; kirishlar; daqiqa; korilgan_material; vk_qatnashgan; vk_jami; topshiriq_bajarilgan; topshiriq_jami; oxirgi_kirish`

- Hafta kalit hisoblanadi: bir haftani qayta yuklasangiz, eski qiymatlar yangilanadi.

**Kontent nazorat varag'i:** `fan; yonalish; kurs; mavzu_no; tur; holat; havola; muddat`

- `tur` maydonida ma'ruza, taqdimot, video yoki test yoziladi.
- `holat` maydonida yuklandi, tasdiqlandi, qaytarildi yoki kutilmoqda yoziladi.
- `havola` faqat `http://` yoki `https://` bilan boshlansa qabul qilinadi (o'qituvchi belgilashi bilan bir xil qoida); aks holda qator sababi bilan o'tkazib yuboriladi. Sahifa ham faqat http(s) havolani ko'rsatadi.

Ikkalasi uchun ham:

- CSV (`;` yoki `,` bilan ajratilgan) va XLSX formatlari qabul qilinadi, hajmi 8 MB gacha;
- namuna fayllar `/api/masofaviy/template/{activity|content}.csv` manzilida;
- topilmagan qatorlar o'tkazib yuboriladi va sababi ko'rsatiladi (birinchi 20 tasi).

- **Namuna o'zgarishsiz import qilinadi:** namuna qatorlari bazadagi haqiqiy masofaviy talaba (HEMIS ID) va kurs/material bilan, joriy qiymatlarida
  (`template_rows()`); kontent namunasi importi hech narsani o'zgartirmaydi (bir xil havola/muddat qayta yozilmaydi).

## Ommaviy tasdiqlash va «Dars tayyorlash» bilan bog'lanish

- `POST /items/bulk-review` `{ids}` (bo'lim): faqat «Yuklandi (tekshiruvda)» holatidagilari tasdiqlanadi, qolganlari o'tkazib yuboriladi
  (`approved`, `skipped`); har biri tarixga yoziladi. UI: «Materiallar» ro'yxati ustida «Ro'yxatdagi «Tekshiruvda» materiallarni tasdiqlash (N)».
- «Dars tayyorlash»da ma'ruza darsi tasdiqlansa, shu kurs/mavzuning paketda bor materiallari bu yerda «tasdiqlandi» bo'ladi (`src='paket'`,
  tarixda «Dars tayyorlash: L3 v1 tasdiqlandi») — o'qituvchidagi «Yuklanmagan, N kun o'tdi» yo'qoladi; tasdiqlangan dars qaytarilsa — shu yo'l bilan
  yopilganlari «qaytarildi» (`sync_from_package` / `unsync_from_package`, docs/paket.md).

## Demo ma'lumot (sun'iy)

`masofaviy.seed()` bir marta ishlaydi (`dl_meta.seed_v1`), `--force` bilan qayta yaratiladi.

**Demo sanalari eskirmaydi.** Demo yaratilgan kunga nisbatan quriladi. Uzoq yashaydigan bazada (Railway volume) 2 haftadan keyin hamma talaba "noaktiv"ga o'tib, muddatlar eskirib qolardi. Shuning uchun `masofaviy.redate()` ishga tushishda va kuniga bir marta (birinchi so'rovda) tekshiradi:

- manba hali `demo` bo'lsa va `dl_meta.anchor` joriy haftadan eski bo'lsa, demo qatorlar butun haftalar farqiga suriladi: `dl_activity` (hafta, oxirgi kirish) va `dl_items` (muddat; demo qatorlarda yuklangan va tekshirilgan vaqt ham);
- import qilingan qatorlarga (`src='import'`) tegilmaydi, faollik importidan keyin (`source='import'`) umuman surilmaydi;
- idempotent: langar yangilanadi, ikkinchi chaqiruv hech narsa qilmaydi.

Ma'lumotda quyidagi holatlar ataylab qo'yilgan:

1. **Ortda qolgan kafedra.** Buxgalteriya hisobi kafedrasi materiallarning taxminan 60% ini bergan. Bitta kafedra taxminan 85% da, qolganlari 92–97% da.
2. **Videodars bermagan o'qituvchi.** Bitta o'qituvchi 6-mavzudan boshlab videodarslarni yuklamagan.
3. **Muddatlar hafta bo'ylab.** Material muddatlari dars kunlariga qarab taqsimlangan, shuning uchun har kuni "bugun oxirgi kun" ro'yxati bor.
4. **Imzolanmagan buyruq.** LMS'ga kirmay qo'ygan 3 nafar talaba uchun akademik ta'til buyrug'ining loyihasi Registrator ofisida imzolanmay turibdi.
5. **Talabalar faolligi.** Taxminan 3% LMS'ga umuman kirmagan, taxminan 5% kirishni to'xtatgan, qolganlari aktiv yoki sust. Faollik oraliq nazorat ballari bilan bog'langan.

Haqiqiy LMS va videokonferensiya platformasi ulanganda yoki birinchi import qilinganda, sahifadagi "Namuna ma'lumot" ogohlantirishi yo'qoladi.

## Havolalar

"Mening vazifalarim" va bosh sahifa havolalari yorliq bilan birga filtrni ham olib yuradi: `tab: "kontent:view=materiallar,due=,status=yuklandi,..."`. `pending.py` faqat `view`/`tab`/`href`ni uzatadi, shuning uchun filtr yorliq matnida. `masofaviy.js` (`dlSpec`) uni o'qiydi. Masalan, "tekshiruvni kutayotgan materiallar" to'g'ridan-to'g'ri "Tekshiruvda" holatidagi materiallar ro'yxatini ochadi.

Sahifa holati (meta, yorliq, filtrlar) joriy foydalanuvchiga bog'langan. Chiqib, boshqa foydalanuvchi bilan kirilsa (sahifa qayta yuklanmasdan), oldingi foydalanuvchining yorliqlari, huquqlari va filtrlari qolmaydi.

## Ishlash tezligi

- `student_rows` (30 s) va `content_summary` (60 s, ko'lam bo'yicha) keshlanadi. Kontent kesimlari materiallarni bir marta aylanib chiqib hisoblanadi.
- Kesh yozuvlarda tozalanadi: yuklandi, tekshirish, import, qoidalar, demo surish.
- `orders.analyze` hamma talabalar bo'yicha ishlaydi (masofaviy filtri yo'q), natijasi 60 s keshlanadi. Masofaviy talabalarga cheklash uchun `orders.analyze`ga filtr parametri qo'shish kerak (Buyruqlar moduli).

## Keyingi bosqichlar (institut ma'lumoti kerak)

- **LMS API'ga to'g'ridan-to'g'ri ulanish.** LMS turini aniqlash kerak (Moodle yoki boshqa). Moodle bo'lsa: `core_course_get_contents` (materiallar holati) va `report_log` (talabalar kirishlari).
- **Videokonferensiya platformasi.** Platformani aniqlash kerak (Zoom, BigBlueButton yoki Meet) va undan qatnashchilar hisobotini olish.
- **Bo'limning haqiqiy checklist jadvali va xodimlar ro'yxati.**
- **Test bank (2-bosqich).** Mavzular bo'yicha testlar, oraliq 1 va oraliq 2 uchun alohida banklar.
- **Mavzu paketi (3-bosqich).** Articulate o'rniga SCORM yoki xAPI paket.
