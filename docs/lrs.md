# LRS va «Ortda qolganlar»

**Kod:** `app/lrs.py` (LRS, tokenlar, ishga tushirish), `app/lrs_analytics.py` (sof hisob funksiyalari), `app/ortda.py` (ekran API'si),
`static/ortda.js`, `static/ortda.css`, `app/paket_player/lms.js` (pleyer tomoni — xAPI adapteri)
**Testlar:** `tests/test_lrs.py`; brauzer — `tools/lrs_e2e_check.js` (PW va CHROME berilganda test o'zi chaqiradi)
**API:** `/xapi/*` (xAPI 1.0.3 kichik to'plami), `/api/lrs/*`, `/api/ortda/*`
**Ruxsat resursi (audit):** `lrs`
**NEXTID'ga so'rov:** `docs/nextid_xapi_sorov.md`

## Nima uchun

NEXTID.LMS (my.isft.uz) xAPI paketlarni launch parametrlarisiz (`endpoint`, `auth`, `actor`) ochadi. Pleyer natijani yubora olmaydi —
savollarga javoblar, ball, urinishlar va vaqt yo'qoladi. NEXTID faqat dars bo'yicha foizni ko'rsatadi, kim ortda qolayotganini hech kim
ko'rmaydi. Masalan, bitta talaba: «Iqtisodiyot nazariyasi 1» — 45 dars (L1–L15, A1–A30), semestrning ~11-haftasida 6/45 dars 100 %,
qolganlari 0 %.

Yechim uch qismdan iborat:

1. **ISFT Core LRS** — statementlarni qabul qiladi va saqlaydi.
2. **To'g'ridan-to'g'ri ishga tushirish** — talabaning shaxsiy havolasi paketni xAPI launch parametrlari bilan ochadi (NEXTID'ga bog'liq emas).
3. **«Ortda qolganlar» ekrani** — taqvim bo'yicha kutilgan progress, testdan o'tolmaslik va faolsizlik; amallar: tyutorga biriktirish, eslatma,
   «bog'lanildi». Savollar tahlili — kurs mualliflari uchun.

## LRS (`/xapi`)

| Metod | Yo'l | Izoh |
|---|---|---|
| GET | `/xapi/about` | `{"version": ["1.0.3"]}` — kirishsiz |
| POST | `/xapi/statements` | bitta yoki massiv (≤ 100); javob — id'lar |
| PUT | `/xapi/statements?statementId=` | bitta statement, 204 |
| GET | `/xapi/statements` | `statementId`, `voidedStatementId`, `agent`, `verb`, `activity`, `registration`, `since`, `until`, `limit`, `ascending` — faqat token egasining o'z kursi/darsi doirasida |
| GET/PUT/POST/DELETE | `/xapi/activities/state` | resume holati (`stateId=isft-state`); POST — JSON birlashtiriladi |
| OPTIONS | `/xapi/*` | CORS (cookie ishlatilmaydi — `Access-Control-Allow-Origin: *`) |

Barcha so'rovlarda (about'dan tashqari) `X-Experience-API-Version: 1.0.x` sarlavhasi majburiy (yo'q bo'lsa — 400). Javobda `1.0.3`.

**Tekshiruv.** Actor — Agent, aniq bitta identifikator (Group yo'q). `verb.id` — IRI. Obyekt — Activity (`id` — IRI) yoki StatementRef
(faqat `voided` bilan). Result: score (`scaled` −1..1, `raw` min..max), `success`/`completion` — mantiqiy, `response` ≤ 4000 belgi,
`duration` — ISO 8601. `context.registration` — UUID. Noma'lum maydon va `attachments` — 400.

**Idempotentlik.** Bir xil id va bir xil mazmun — qayta yozilmaydi (200 / 204). Bir xil id, boshqa mazmun — 409. Pleyer oflayn navbatidan
qayta yuborilgan statementlar shu tufayli xavfsiz. Massiv atomik — bittasi xato bo'lsa, hech biri yozilmaydi.

**Bekor qilish.** `voided` → nishon statement `voided=1` bo'ladi va hisobdan chiqadi (progress qayta hisoblanadi). Shartlar:

- `GET ?statementId=` — 404, `?voidedStatementId=` — 200;
- `voided` statementni bekor qilib bo'lmaydi;
- boshqa talabaning statementi — 403.

**Cheklovlar.** So'rov ≤ 512 KB, statement ≤ 32 KB, holat hujjati ≤ 64 KB (413). Token bo'yicha daqiqasiga 120 so'rov va soatiga 3000
statement; IP bo'yicha daqiqasiga 600 so'rov (429 + `Retry-After`). Cheklovlar jarayon xotirasida.

## Kirish: token, taxallus, ko'lam

- **Launch tokeni** (Basic auth): login — `jti`, parol — imzolangan yuk `{l: taxallus, c: kurs, s: dars, e: muddat, r: registration}`.
  HMAC-SHA256 kaliti `ISFT_CORE_LRS_KEY` (yoki bazada bir marta yaratiladi, `lrs_meta.key`). Paket ichiga hech qanday sir yozilmaydi —
  token har ochilishda yangi beriladi (24 soat). `lrs_tokens` jadvalida (bekor qilish — `revoked=1`).
- **Ko'lam:**
  - paket — bitta dars (`…/paket/<kurs>/<no|kod>` va uning bloklari/savollari);
  - kurs muharriri — butun kurs (`…/kurs/<id>`, darslari va savollari).
  - Boshqa dars, boshqa kurs, boshqa talaba nomidan (actor), boshqa registration — 403. Muddati o'tgan, imzosi buzilgan yoki bekor qilingan
    token — 401.
- **Taxallus (learner id):** `s` + HMAC(talaba id) — URL va actor'da ism, HEMIS ID va email yo'q. Moslash — `lrs_learners`.
- **Hamkor (NEXTID) kirishi** (ixtiyoriy): `ISFT_CORE_LRS_PARTNER="login:parol"` (parol ≥ 16 belgi). Actor —
  `{"account": {"homePage": "https://my.isft.uz", "name": "<HEMIS ID>"}}` (`ISFT_CORE_LRS_PARTNER_HOME`). Faqat ISFT faoliyatlari nomlar
  fazosiga yozadi, o'qiy olmaydi.

Rad etilgan yozish urinishlari (401/403/409) audit jurnaliga yoziladi (`resource='lrs'`).

## To'g'ridan-to'g'ri ishga tushirish

1. Bo'lim (`masofaviy`, `masofaviy_xodim`) talaba uchun havola oladi: `POST /api/lrs/launch-link {student_id, course_ref, lesson_ref}`
   («Ortda qolganlar» → talaba darslari → «Havola»).
   - Paket uchun — `course_ref="dl:<masofaviy kurs id>"`, `lesson_ref="L3"` / `"A12"`.
   - Kurs muharriri uchun — `course_ref="ku:<id>"`, dars ko'rsatilmaydi.
2. Havola `/xapi/l/<kod>` — imzolangan, 150 kun. Ichida faqat taxallus va kurs bor. Eslatma xabarida keyingi darsga havola shu formatda.
3. Ochilganda — yangi token va 302:
   `/xapi/pkg/<kod>/index.html?endpoint=<server>/xapi/&auth=Basic…&actor={account}&registration=<uuid5>&activity_id=<IRI>`.
4. Fayllar eksport zip'i ichidan beriladi:
   - paket — o'sha dars uchun eng so'nggi paket (tasdiqlangani ustun);
   - kurs muharriri — oxirgi eksport (xAPI ustun);
   - oddiy HTML eksport ishga tushirilmaydi.
   - CSP: `default-src 'none'; script-src 'self'; connect-src <server>/xapi/` — paket skripti `/api` ga so'rov yubora olmaydi.
   - `frame-ancestors 'self' https://my.isft.uz` (`ISFT_CORE_LRS_FRAME_ANCESTORS`) — NEXTID iframe'ida ochish mumkin.
   - Media — HTTP Range bilan.
5. `registration` — talaba × kurs bo'yicha barqaror (UUID5): resume holati sessiyalar orasida saqlanadi.

## Pleyer (`lms.js`, ikkala pleyer uchun umumiy)

Launch parametrlari bo'lsa — xAPI adapteri. Yuboriladigan statementlar:

| Fe'l | Qachon |
|---|---|
| `initialized` | sessiya boshida |
| `resumed` | saqlangan holatdan davom etilganda |
| `experienced` | har blok / dars ko'rilganda |
| `progressed` | har 10 %; cmi5 `…/result/extensions/progress` kengaytmasi bilan |
| `answered` | har savolga: `response` va `success`, interaction ta'rifi — variantlar va to'g'ri javob |
| `responded` | mulohaza savollari |
| `passed` / `failed` | test natijasi, ball bilan |
| `completed` | dars yoki kurs yakunlanganda |
| `suspended` | tugallanmagan sessiya yopilganda, `duration` bilan |
| `terminated` | sessiya oxirida, `duration` bilan |

**Oflayn navbat.** Tasdiqlanmagan statementlar `localStorage` («isft-xapi-q:…») da saqlanadi va qayta yuboriladi:

- tarmoq tiklanganda (`online` hodisasi);
- keyingi ochilishda;
- 2 s → 30 s oraliqda qayta urinib.

Chegara: 300 ta / ~400 KB. `localStorage` yopiq bo'lsa (sandbox) — navbat faqat xotirada. Launch parametrlari yo'q bo'lsa (bugungi NEXTID
iframe'i) — avvalgidek jim mustaqil rejim, hech narsa yuborilmaydi.

## Ma'lumot modeli

| Jadval | Mazmuni |
|---|---|
| `lrs_statements` | id (UUID), stored, ts (Toshkent vaqti), talaba, taxallus, fe'l, faoliyat, kurs / dars / element (`parse_activity`), registration, success, completion, ball (%), javob, davomiylik, progress, `voided`, mazmun xeshi (idempotentlik), token, manba (`lrs` / `demo`), to'liq JSON. Indekslar: talaba+vaqt, faoliyat+vaqt, fe'l+vaqt, kurs+dars+talaba, stored |
| `lrs_progress` | talaba × kurs × dars jamlanmasi (har statementdan keyin qayta hisoblanadi): holat (boshlanmagan / jarayonda / testdan o'tmadi / yakunlandi / o'tdi), foiz, oxirgi va eng yaxshi ball, urinishlar, muvaffaqiyatsiz urinishlar, vaqt, birinchi/oxirgi faollik |
| `lrs_activities` | savol ta'riflari (nom, matn, tur, variantlar, to'g'ri javob) — savollar tahlili uchun |
| `lrs_state` | State API hujjatlari |
| `lrs_learners`, `lrs_tokens` | taxallus ↔ talaba; berilgan tokenlar (muddat, bekor qilish, statementlar soni) |
| `lrs_plan` | kurs darslari taqvim tartibida (ixtiyoriy; yo'q bo'lsa — «Dars tayyorlash» / Kurs muharriri darslari) |
| `lrs_policy` | chegaralar |
| `lrs_actions` | amallar jurnali: tyutorga biriktirish (topshiriq id), eslatma (xabar id), «bog'lanildi» |

Kurs identifikatori:

- `dl:<id>` — «Dars tayyorlash» paketlari, masofaviy kurs (`dl_courses`), har dars alohida paket;
- `ku:<id>` — Kurs muharriri kursi.

## Analitika (`app/lrs_analytics.py`)

**Talaba × dars.**

- Urinish — test natijasi (`passed` / `failed`). Paket natijani blok va dars darajasida ikki marta yuboradi — blok darajasidagi bo'lsa,
  faqat o'shalar sanaladi.
- Yiqilgan test — «testdan o'tmadi», dars «completed» bo'lsa ham bajarilgan hisoblanmaydi.

**Savollar** (klassik test nazariyasi, har talabaning birinchi urinishi bo'yicha):

| Ko'rsatkich | Ma'nosi |
|---|---|
| qiyinlik `p` | to'g'ri javob ulushi |
| farqlash `D` | o'sha testdagi boshqa savollar natijasi bo'yicha yuqori va quyi 27 % guruhlardagi `p` farqi |
| `r_pb` | point-biserial korrelyatsiya |
| eng ko'p tanlangan noto'g'ri javob | va uning noto'g'ri javoblar ichidagi ulushi |

`D` va `r_pb` faqat ≥ 10 javobda hisoblanadi. Belgilar:

- «juda qiyin» — p < 0,3;
- «juda oson» — p > 0,95;
- «farqlamaydi» — D < 0,2;
- «salbiy farqlash» — D < 0;
- «kuchli chalg'ituvchi» — noto'g'rilarning ≥ 60 % bitta variant.

**Kurs voronkasi.** Har dars bo'yicha boshlagan / yakunlagan / o'tganlar, o'rtacha ball, muvaffaqiyatsiz urinishlar, o'rtacha vaqt.

**Taqvim bo'yicha kutilgan progress.**

- Darslar `weeks` (15) haftaga teng taqsimlanadi va har hafta boshida chiqariladi. Semestr boshi — `academic_rules.term_dates`.
- Kutilgan = `grace_weeks` (1) hafta oldin chiqarilganlar. Joriy hafta darslari hali talab qilinmaydi.
- Misol: 45 dars, 11-hafta — 33 tasi chiqarilgan, 30 tasi kutilgan.

## «Ortda qolganlar» qoidalari

| Sabab | Shart (standart) | Og'irlik |
|---|---|---|
| Taqvimdan ortda | kutilgan − bajarilgan ≥ `lag_lessons` (3) | 2 (ikki baravar — 3) |
| Testdan qayta-qayta o'tolmayapti | hali o'tilmagan bitta testda ≥ `fail_attempts` (3) muvaffaqiyatsiz urinish | 2 (ikki baravar — 3) |
| Faolsiz | oxirgi faollikdan ≥ `inactive_days` (7) kun | 2 (ikki baravar — 3) |
| Umuman boshlamagan | hech qanday statement yo'q, kutilgan > 0 | 3 |

Og'irliklar yig'indisi ≥ 4 — yuqori xavf, 2–3 — o'rta. Chegaralarni bo'lim boshlig'i «Qoidalar» yorlig'ida o'zgartiradi (audit bilan).
Qo'shimcha chegaralar:

- eslatma — bitta talabaga `remind_cooldown_days` (3) kunda bir marta;
- bitta xodim — kuniga `remind_daily_max` (200) ta.

Kursdagi talabalar — masofaviy guruhlar (yo'nalish × kurs, faol). Kurs muharriri kursi masofaviy kursga bog'lanmagan bo'lsa — statement
yuborganlar.

## Kim nimani ko'radi

| Lavozim | Ko'rinish | Amallar |
|---|---|---|
| `masofaviy`, `masofaviy_xodim` | barcha masofaviy talabalar: ism, guruh, HEMIS ID; talaba darslari; kurslar va savollar | tyutorga biriktirish, eslatma, «bog'lanildi», ishga tushirish havolasi; chegaralar — faqat boshliq |
| `tyutor` | o'z guruhlari (`rbac.student_scope`) + unga biriktirilgan talabalar; HEMIS ID'siz | eslatma, «bog'lanildi» (biriktirmani yopadi) |
| `oqituvchi` | o'z kurslari (mas'ul o'qituvchi yoki kurs muallifi); ro'yxatda faqat o'z guruhlari talabalari ismi, kontakt va HEMIS ID'siz; savollar tahlili | — |
| `kafedra` | o'z kafedrasi kurslari: jamlangan sonlar, voronka, savollar tahlili | — |
| `rektor`, `prorektor_oquv` | faqat jamlangan sonlar (ism, HEMIS, talaba id'si yo'q) | — |

Har so'rov audit jurnaliga yoziladi (`resource='lrs'`), rad etilganlari ham.

**Amallar.**

- **Tyutorga biriktirish.** «Topshiriqlar» tizimida (`app/directives.py`, `src='lrs:<amal id>'`) tyutorga vazifa yaratiladi: muddat — 3 ish
  kuni, yuqori xavfda «muhim». Vazifa tyutorning «Mening vazifalarim»ida chiqadi, kartasi `/api/dir/<id>`.
- **Eslatma.** Talabalar markazining chiqish navbatiga (`ops_notices`, «navbatda») yoziladi. SMS / Telegram shlyuzi ulanganda yuboriladi.
  Matnda — kechikish va (paket bo'lsa) keyingi darsga shaxsiy havola.
- Hammasi `lrs_actions` va audit jurnalida.

**Savollar tahlili.** «bu savolni N% xato topyapti» — eng qiyin savollar yuqorida. Havolalar:

- kurs muharriri savoli — «Muharrirda ochish»: `go("kurs", {cid, lid, block})` o'sha darsni ochadi va blokni tanlaydi;
- paket savoli — «Dars tayyorlash»dagi dars.

## Demo ma'lumot (sun'iy)

`lrs.seed()` bir marta ishlaydi (`lrs_meta.seed_v1`). Sun'iy statementlar (`src='demo'`) uch masofaviy kurs uchun yaratiladi:

- «Iqtisodiyot nazariyasi» (Iqtisodiyot, 1-kurs) — 45 darslik reja L1–L15 + A1–A30 (`lrs_plan`, `src='demo'`). Hikoya: bir talaba
  6/45 dars bajargan;
- demo o'qituvchining kursi;
- yana bitta kurs.

Talaba profillari: a'lochi, o'rtacha, sust, to'xtagan, boshlamagan. Har dars testida 4 savol, ulardan biri ataylab qiyin — ko'pchilik
bir xil noto'g'ri variantni tanlaydi.

`redate()` statementlar sanasini butun haftalarga suradi (masofaviy demo kabi). Sahifada «Namuna ma'lumot» ogohlantirishi ko'rinadi:

- faqat sun'iy statementlar bo'lsa — doim;
- haqiqiy statementlar bilan aralash bo'lsa — izoh bilan.

## Ma'lum cheklovlar

- NEXTID launch parametrlarini bermaguncha, NEXTID ichida ochilgan darslar natijasi kelmaydi — so'rov yuborilishi kerak
  (`docs/nextid_xapi_sorov.md`).
- Talaba kabinetida (`/talaba`) havolalar ro'yxati hali yo'q — havolani bo'lim beradi yoki eslatma xabarida keladi.
- Statement oqimi: `more` (sahifalash) yo'q — `limit` ≤ 500.
- Agent profili va Activity profili API'lari yo'q.
- Cheklovlar jarayon xotirasida — bir nechta server nusxasida umumiy emas.
- Eslatma — navbatga yoziladi, haqiqiy SMS/Telegram yuborish shlyuz ulanganda.
- Tyutorlar hozir faqat kunduzgi guruhlarga biriktirilgan (`tutor_groups`). Masofaviy talabalar tyutorga bo'lim biriktirgandan keyin ko'rinadi.
