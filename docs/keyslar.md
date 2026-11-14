# Keyslar, haftalik ritm, to'siq nuqtalaridagi eslatmalar, dars oxiri testi, «ISFT Ready»

**Kod:** `app/keyslar.py` (keyslar, ko'rsatkichlar), `app/haftalik.py` (kogorta taqvimi), `app/tajriba.py` (eslatmalar va tajriba),
`app/dars_testi.py` (dars oxiri testi), `app/isft_ready.py` (kirish kursi), `app/nazorat.py` (oxirgi bo'lim — Nazorat markazi),
`static/keyslar.js`, `static/talaba_darslar.js` («Bu hafta», nishon)
**Testlar:** `tests/test_keyslar.py`; brauzer — `tools/keyslar_check.js` (PW va CHROME berilganda test o'zi chaqiradi)
**API:** `/api/ortda/keys*`, `/api/ortda/keys-qoidalar`, `/api/ortda/taqvim`, `/api/ortda/tajriba*`, `/api/kurs/courses/{id}/dars-testlari`,
`/api/dars/subjects/{id}/dars-testlari`, `/api/kurs/isft-ready`, `/api/nazorat/keyslar`
**Ruxsat resursi (audit):** `lrs` (keyslar, taqvim, tajriba), `kurs` / `paket` (testlar, kirish kursi)

## Nima uchun (dalil — `reports/Onlayn universitetlar va platformalar.md`)

| Dalil | Xulosa |
|---|---|
| InsideTrack coaching RCT (+5,2 f.p.), OU qo'ng'iroq RCT | Bayroqqa javob beradigan **odam** natija beradi |
| MAAPS RCT (11 universitet) — ta'sir yo'q | Panel va bayroqning o'zi yetarli emas — egasi, muddati, natijasi kerak |
| Oreopoulos RCT, FAFSA SMS takrorlanishi — nol | Ommaviy eslatma retention vositasi emas; faqat to'siq nuqtalarida va o'lchab |
| Bettinger (AER 2017), retrieval practice meta-tahlili | Qat'iy haftalik muddatlar va tez-tez past xavfli test |
| OU Ready | Kirish kursi va 1-hafta faolligi — eng erta signal |

## 1. Keyslar

Har bayroqli talaba («Ortda qolganlar» qoidalari) — bitta faol keys (kurslar va sabablar ichida).

- **Hayot sikli:** ochiq → jarayonda (birinchi bog'lanish qayd etildi) → yopilgan.
- **SLA:** birinchi bog'lanish `sla_days` (2) ish kuni ichida (shanba-yakshanba sanalmaydi). Har qanday qayd etilgan urinish, «javob bermadi» ham —
  bog'lanish hisoblanadi.
- **Yopish:** natija majburiy:
  - qo'ng'iroq qilindi — gaplashildi;
  - qo'ng'iroq qilindi — javob bermadi;
  - uchrashildi;
  - talaba o'qishni davom ettirmaydi;
  - boshqa (izoh majburiy).

  Keyingi qadam sanasi majburiy («davom ettirmaydi»dan tashqari) va o'tgan kun bo'lolmaydi.
- **Egasi:** guruh tyutori (yuklamasi chegaradan past bo'lsa) avtomatik, aks holda — bo'lim biriktiradi.
- **Yuklama chegarasi:** `caseload_max` (50) — 1:50 nisbat bilan mos. Oshsa 409 qaytadi va tavsiya beriladi:
  chegaradan past guruh tyutori → shu fakultetning eng kam yuklangani → qolganlarning eng kam yuklangani.
  «Baribir biriktirish» (`force`) audit jurnaliga yoziladi.
- **Qayta ochish:** yopilganiga `reopen_days` (14) kun bo'lmagan talaba bayroqli bo'lsa ham yangi keys ochilmaydi. 14 kundan keyin hali
  bayroqli bo'lsa — yangi keys (`src='qayta'`, `reopened_from`). «Davom ettirmaydi» bilan yopilgani qayta ochilmaydi (Registrator jarayoni).
- **Bayroq yo'qolsa:** hali hech kim bog'lanmagan keys tizim tomonidan yopiladi (`avto_yoqoldi`). Bu odam natijasi emas, ko'rsatkichlarda alohida.
- **Tushuntirish:** har keysda oddiy o'zbek tilida, raqam va qoida chegarasi bilan. Masalan: «taqvim bo'yicha 20 ta dars tugatilgan bo'lishi
  kerak edi, 8 tasi tugatilgan — 12 dars ortda (qoida: 3 va undan ko'p dars)».
- **Demografiya yo'q:** qoidalar faqat `LA.RULE_INPUTS` (kutilgan / bajarilgan darslar, test urinishlari, faolsiz kunlar, boshlaganmi) va
  «ISFT Ready» holatini o'qiydi. Test buni natija va kod bo'yicha tekshiradi.
- **Sinxronizatsiya:** fon jarayoni har 10 daqiqada ishlaydi; ro'yxat ochilganda — ko'pi bilan 60 soniyada bir marta; «Yangilash» tugmasi bo'limda.

### Ko'rsatkichlar (`keyslar.metrics` — sof funksiya)

| Ko'rsatkich | Ta'rif |
|---|---|
| ochilgan / yopilgan | davrda (standart — semestr boshidan); tizim yopgani alohida |
| median bog'lanish | ochilishdan birinchi bog'lanishgacha, soat |
| SLA ichida | baholanadigan keyslar (bog'lanilgan yoki SLA muddati o'tgan) ichida muddatida bog'lanilganlar. SLA'dan oldin bayroq o'zi yo'qolgani hisobga olinmaydi |
| qayta faollashish | bog'lanishdan keyin `reengage_days` (14) kun ichida LMS faolligi; oynasi tugamaganlar «kutilmoqda». Sababiy ta'sir emas |

Ko'rsatkichlar umumiy va tyutorlar bo'yicha beriladi. Tyutor — faqat o'zinikini ko'radi. Rektor va o'quv prorektori — jamlangan, talaba ismi yo'q.

**Nazorat markazi** («talabalar» sohasi):

- istisnolar:
  - «N ta keys SLA ichida bog'lanilmagan» — tyutor bo'yicha (`case_sla_min`);
  - «Tyutor yuklamasi oshgan» — egasi Masofaviy ta'lim bo'limi;
- «Keyslar natijasi» kartasi (`/api/nazorat/keyslar`).

## 2. Haftalik ritm (`app/haftalik.py`)

Taqvim manbai (ustunlik tartibida):

1. guruh sozlamasi — `lrs_cohort(kurs, guruh)`;
2. kurs sozlamasi — `lrs_cohort(kurs, 0)`;
3. `lrs_plan` yoki semestr boshi.

Darslar haftalarga teng taqsimlanadi (`lrs_analytics.schedule`): dars hafta boshida chiqadi, muddati — o'sha hafta oxiri (yakshanba).
Bo'lim alohida muddat qo'yishi mumkin, lekin dars chiqarilishidan oldin emas.

- **Kutilgan progress:** muddati o'tgan darslar, `grace_weeks` imtiyozi bilan (`expected_by_due`). Standart taqvimda avvalgi hisob bilan aynan
  bir xil (test 135 kun × 5 kursda tekshiradi). Yagona farq: semestr hafta o'rtasida boshlansa, 2-haftaning dushanbasida 1-hafta darslari
  muddati o'tgan hisoblanadi.
- **Talaba kabineti:** «Bu hafta» bloki — joriy hafta darslari va muddati o'tgan bajarilmaganlar, muddati bilan. Kurs darslarida ham muddat
  ko'rsatiladi. Belgilar: kechikkan — muddati o'tgan; bu hafta — chiqarilgan, muddati o'tmagan; keyinroq — hali chiqarilmagan.

## 3. To'siq nuqtalaridagi eslatmalar va tajriba (`app/tajriba.py`)

| Nuqta | Shart | Takrorlanmaslik |
|---|---|---|
| `t_login` | semestrning 3-kunidan: kabinetga kirmagan va LMS faolligi yo'q | semestrda bir marta; SMS navbati (telefon bo'lsa), aks holda Telegram |
| `t_due48` | dars muddatiga ≤ 48 soat qoldi, bajarilmagan | bitta muddat sanasi uchun bitta xabar (kurslar va darslar ro'yxati bilan) |
| `t_inactive7` | boshlagan talaba ≥ 7 kun faolsiz | har faolsizlik davri uchun bir marta |

- **Rejim** (faqat bo'lim boshlig'i): o'chiq (standart) | hammaga | tajriba.
- **Tajriba qo'li:** `sha256(kalit|tuz|guruh)` — barqaror; yangi tajriba — yangi tuz. Nazorat qo'lidagi mos hodisalar ham yoziladi (yuborilmaydi).
- **Cheklovlar** (`tj_limits`), har hodisa jurnalda (`tj_events` + `ops_notices` + `notice_delivery`):
  - bitta talabaga ≥ 48 soat oraliq;
  - 7 kunda ≤ 2 ta;
  - kuniga jami ≤ 500.
- **Taqqoslash:** har talabaning tajribadagi birinchi hodisasi, oynasi tugaganlar. Natijalar:
  - 7 kunda qayta faollashish;
  - 14 kunda yakunlangan darslar.

  Farqning 95 % oralig'i guruhlar darajasida hisoblanadi (Welch t). Ogohlantirishlar: guruh yoki talaba kam, oraliq 0 ni qamraydi, oynasi
  tugamagan hodisalar. Ish niyat bo'yicha (ITT): cheklov tufayli yuborilmaganlar ham tajriba qo'lida qoladi.

## 4. Dars oxiri testi (`app/dars_testi.py`)

Kurs muharriri («Dars oxiri testlari») yoki Dars tayyorlash («Har dars oxiriga test») tugmasi bilan har bloklar darsidan keyin test darsi
qo'shiladi (uid `aq…`). Test sozlamalari: 3–5 savol, urinishlar cheklanmagan, o'tish bali 60 %, savollar va javoblar aralashtiriladi.

- **Savollar:** faqat Test bankdagi tasdiqlangan savollar, darsning mavzusidan. Mavzu:
  - Dars tayyorlash darsi — `paket.source_topic`;
  - fanga bog'langan kurs — n-chi dars = n-mavzu.
- **Takrorlanmaslik:** fan bo'yicha savol takrorlanmaydi (`ku_autoquiz`). Bo'sh savollar mavzu darslariga teng bo'linadi; 3 tadan kam qolsa,
  dars sabab bilan o'tkazib yuboriladi.
- **Idempotent:** testi bor dars qayta qo'shilmaydi. O'zgarishdan oldin versiya saqlanadi.
- **Natija:** ball xAPI orqali LRS'ga (`lrs_progress`) va savollar tahliliga tushadi.

## 5. «ISFT Ready» (`app/isft_ready.py`)

Kurs muharriridagi «ISFT Ready shabloni» tugmasi (bo'lim) qoralama kurs yaratadi. Tarkibi — 6 bo'lim, har birida bilimni tekshirish savoli:

1. platforma;
2. muddatlar;
3. yordam;
4. akademik halollik;
5. sun'iy intellektdan mas'uliyatli foydalanish;
6. o'qish odatlari.

Oxirida yakuniy tekshiruv: 8 savol, 80 %, urinishlar cheklanmagan. Qonunchilik haqida yagona da'vo — yakuniy imtihonlar universitet
qoidalariga ko'ra yuzma-yuz o'tkaziladi.

- **E'lon qilish:** tasdiqlash va xAPI eksportdan keyin kurs talaba kabinetida karta bo'lib chiqadi («Boshlash»). Yakunlagan talabada —
  «ISFT Ready» nishoni.
- **Kuzatish:** «Ortda qolganlar» 1-kurs masofaviy talabalarini kuzatadi.
- **Qoida:** muddat — 1-hafta oxiri; kurs keyinroq e'lon qilinsa, e'londan 7 kun. Muddat o'tib, kurs tugatilmagan bo'lsa — «Boshlamagan»
  erta bayrog'i (og'irlik 2) va keys.

## Ma'lum cheklovlar

- Avtomatik eslatmalar standart holda o'chiq — bo'lim boshlig'i yoqadi (tavsiya: «tajriba»). Ilgari ham o'quv eslatmalari ommaviy yuborilmagan
  (faqat «Ortda qolganlar»dagi qo'lda eslatma). Talabalar markazidagi kontrakt bo'yicha ommaviy SMS/Telegram (call-markaz) bu ishga kirmaydi.
- SMS shlyuzi yo'q — SMS navbatda qoladi. Telegram — talaba ulagan bo'lsa.
- Masofaviy guruhlar soni kam (namunada 95, LRS kuzatuvidagi kurslarda 5) — tajriba natijalari keng oraliq bilan chiqadi, ekran buni ochiq aytadi.
- Namuna keyslar (`src='demo'`) sun'iy: LRS namunasi bayroqlaridan, eng kichik id'li 4 tyutor ishlatilmaydi.
