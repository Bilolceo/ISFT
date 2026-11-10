# Talaba harakati (akademik oqimlar)

Modul: `app/academic_flows.py` (API `/api/flows/...`), interfeys: `static/flows.js`, `static/flows.css` (menyuda «Talaba harakati»).
Testlar: `tests/test_flows.py`. Buyruq turlari va ularning bazaga ta'siri: `app/orders.py`.

Baholash qoidalari (o'tish bali 40, oraliq 30 / min 12, yakuniy 70, GPA formulasi, qarzdor ta'rifi) faqat
`app/academic_rules.py` dan olinadi. Bu modulning o'z qoidalari `academic_flows.RULES` lug'atida turadi.
**«*» belgisi bor qoidalar institut tasdig'ini talab qiladi.**

## Kim nimani ko'radi (serverda tekshiriladi, audit — `resource=flows`)

| Lavozim | Bo'limlar | Amallar |
|---|---|---|
| Registrator ofisi (17), xodim (43) | hammasi | apellyatsiya qabul qilish, qayta o'qish qarori, ko'chirish arizasi, grant nomzodlari, bitirish va chetlashtirish buyruq loyihalari, diplom raqamlari |
| Akademik faoliyatni boshqarish bo'limi (18) | hammasi | sessiya va jadval (tuzish, avtomatik tuzish, e'lon qilish, qayta topshirish muddati), komissiya raisi (apellyatsiya qarori), farq fani natijasi, YDA natijasi |
| Imtihon bo'limi (8) | Sessiya, Apellyatsiya | jadvalni ko'rish va eksport, komissiya ovozi |
| Kafedra mudiri (14, 30–36) | hammasi, faqat o'z kafedrasi | komissiya ovozi (faqat o'z kafedrasi fanlari), bitiruv ishi mavzusi va rahbari |
| Sirtqi bo'lim (27) | grantdan tashqari hammasi, faqat sirtqi talabalar | sirtqi sessiya jadvali, sirtqi talabalar arizalari va buyruq loyihalari |
| Buxgalteriya (11) | Qayta o'qish, Grant | faqat to'lov qatorlari (baholarsiz), grant moliyaviy ro'yxati, to'lovni qayd etish |
| Rektor (2), O'quv prorektori (3) | hammasi | ISFT granti komissiya qarori; buyruqlar «Buyruqlar» bo'limida imzolanadi |
| Boshqalar | — | 403 |

Buyruq talab qiladigan qarorlar «Buyruqlar» bo'limiga loyiha sifatida tushadi. Loyihani Registrator ofisi tuzadi,
sirtqi talabalar uchun Sirtqi bo'lim. Rektor imzolagach, ta'sir talabalar bazasiga o'tadi. Tuzatuvchi («bekor qilish»)
buyruq bilan o'zgarish qaytariladi: holat, guruh, ta'lim shakli, to'lov turi va kontrakt summasi.

## 1. Imtihon sessiyasi va jadvali
- Har bir ta'lim shakli uchun alohida sessiya bor: kunduzgi va masofaviy uchun qishki va yozgi, sirtqi uchun qishki va yozgi o'quv-imtihon sessiyasi.
- Jadval yozuvida fan, guruh, sana va vaqt, xona (`rooms`) va imtihon oluvchi (`teachers`) bor. Vaqt oraliqlari: 09:00, 11:30 va 14:30, har biri 2 soat.
- **To'qnashuv** degani bir sanada vaqt oralig'i kesishgan ikki yozuvda bir xil xona, guruh yoki imtihon oluvchi borligi. Tekshiruv barcha sessiyalar bo'yicha ishlaydi.
  To'qnashuvli yozuv qo'shilmaydi (javob 409). Majburan qo'shilgan bo'lsa, jadval e'lon qilinmaydi.
- «Avtomatik tuzish» guruhga kuniga bitta imtihon qo'yadi va imtihonlar orasida dam olish kuni qoldiradi.
  Xona guruh soniga yetadigan sig'imda tanlanadi, imtihon oluvchi esa guruhda shu fandan eng ko'p baho qo'ygan o'qituvchi bo'ladi.
- Qayta topshirish muddatlari sessiyaga bog'lanadi va faqat sessiya tugagandan keyin boshlanishi mumkin.
- Jadvalni XLSX ko'rinishida yuklab olish mumkin. To'qnashuvlar bo'lsa, ular alohida varaqda chiqadi.

## 2. Apellyatsiya
- Talaba yakuniy natijaga natija **e'lon qilingandan keyin 3 kun ichida** apellyatsiya beradi (`appeal_days`*).
  E'lon sanasi baholar tarixidagi hisobga olingan urinish sanasi. Tarix bo'lmasa, semestr oxiri olinadi.
- Kelajakdagi talaba portali uchun funksiya: `create_appeal(con, student_id, subject, semester, reason, channel)`. Xato bo'lsa `ValueError` qaytadi.
- Komissiya tarkibi: fan kafedrasining mudiri, Imtihon bo'limi va Akademik bo'lim (rais). Kamida 2 a'zo ovoz bergandan keyin rais qaror chiqaradi.
  Qaror uch xil bo'ladi: saqlash, oshirish yoki pasaytirish.
- Baho **faqat** `grade_attempts` orqali o'zgaradi. Unga «apellyatsiya» turidagi urinish yoziladi, qaror asosi `note` ga tushadi.
  Bu urinish hisobga olinadi (`counted=1`), avvalgi urinishlar tarixda qoladi. `grades` yangilanadi va talabaning o'rtacha bali qayta hisoblanadi.

## 3. Qayta o'qish, kursda qoldirish, chetlashtirish
- Talaba qayta topshirishda ham o'tmasa (tarixdagi oxirgi urinish «qayta topshirish» yoki «otrabotka» va ball 40 dan past), unga taklif yoziladi.
- Talaba quyidagilardan birini tanlaydi:
  - **To'lovli qayta o'qish.** Narx = kredit × (yillik kontrakt / 60)*. Grant talabasi uchun yo'nalish shaklining odatiy kontrakti olinadi. Summa Buxgalteriyaga qarz qatori bo'lib tushadi, to'lov muddati 30 kun*.
  - **Kursda qoldirish.** Shu yo'nalishning bir kurs pastdagi guruhiga o'tkaziladi va «Kursda qoldirish» buyruq loyihasi tuziladi.
- Qaror berish muddati 30 kun*. Muddat o'tsa, talaba rad etsa yoki qayta o'qish to'lovi muddatida to'lanmasa, talaba
  chetlashtirish nomzodiga aylanadi. Shundan keyin «Akademik qarzdorlik sababli chetlashtirish» (`akademik_qarz`) buyruq loyihasi tuziladi.

## 4. Ko'chirish va qayta tiklash
Modul quyidagi turlarni qo'llab-quvvatlaydi. Har biri o'z buyruq turi bilan yakunlanadi:

| Tur | Buyruq turi |
|---|---|
| ichki ko'chirish (yo'nalish yoki ta'lim shakli) | `ichki_kochirish` |
| boshqa OTMdan ko'chirib kelish | `kochirib_qabul` |
| boshqa OTMga ko'chib ketish | `kochirish` |
| qayta tiklash | `tiklash` |
| akademik ta'tildan qaytish | `tatildan_qaytish` |

- **Farq fanlari** maqsad guruh o'quv rejasidan olinadi (`curriculum`, yo'nalish × daraja). Hisobga shu guruh o'tib bo'lgan dastur semestrlari kiradi, ya'ni joriy semestrgacha bo'lganlari.
  Talaba o'zlashtirmagan fanlar (40+ ball yo'q) farq fani bo'ladi. Ko'chirib kelganlar uchun avvalgi OTMda o'qilgan fanlar ro'yxati hisobga olinadi.
  Fanlar nomi bo'yicha solishtiriladi*.
- Farq fanlarini topshirish muddati 120 kun* va arizadan hisoblanadi. Natijani Akademik bo'lim yoki Registrator kiritadi.
- Ichki ko'chirishda ta'lim shakli yangi guruhdan olinadi: kunduzgi guruhdan sirtqi guruhga o'tsa, talaba sirtqi bo'ladi.
  Ko'chirib kelgan shaxs buyruq imzolanguncha «qabul kutilmoqda» holatida turadi.

## 5. ISFT granti
Bu institutning o'z granti, **davlat granti emas**. Har yili 300 o'rin beriladi: 250 iqtidor va 50 ijtimoiy. Grant faqat kunduzgi bakalavr talabalariga beriladi.
- Yillik qayta reyting kurs ichida o'tkaziladi (`rank_by`*). Asos oxirgi o'quv yilining 2 semestri bo'yicha kredit bilan tortilgan GPA
  (`academic_rules.gpa` formulasi, SQL ko'rinishi `ratio2_sql` / `grade5_sql`). Teng kelsa, o'rtacha ball hal qiladi.
- Grantni saqlab qolish sharti: akademik qarz bo'lmasligi va GPA ≥ 4.0* (ijtimoiy toifada ≥ 3.0*). Shart bajarilmasa, talaba «mahrum qilish» nomzodi bo'ladi.
- Bo'shagan iqtidor o'rinlariga qarzsiz, GPA ≥ 4.0 bo'lgan kontrakt talabalari reyting tartibida tavsiya etiladi.
  Ijtimoiy o'rinlarni komissiya hujjatlar asosida to'ldiradi, tizim faqat ularning sonini ko'rsatadi.
- Jarayon: Registrator nomzodlar ro'yxatini tuzadi. Ro'yxat komissiyaga, ya'ni Rektor yoki O'quv prorektoriga boradi va ular har bir nomzodni tasdiqlaydi yoki rad etadi.
  So'ng Registrator ikki buyruq loyihasini tuzadi: `isft_granti` (to'lov turi grant, kontrakt 0) va `isft_granti_mahrum` (to'lov turi kontrakt, odatiy kontrakt summasi).
  Buxgalteriya tasdiqlangan o'zgarishlarni va ularning moliyaviy ta'sirini ko'radi.
- Iqtidor va ijtimoiy toifa `grant_holders` jadvalida saqlanadi. Demo bazada ijtimoiy toifa tasodifiy belgilangan*.

## 6. Bitiruv
- Bitirish uchun barcha shartlar bajarilishi kerak:
  - kredit yetarli: bakalavr 240, magistr 120 (`academic_rules.PROGRAM_CREDITS`);
  - akademik qarz yo'q;
  - bitiruv malakaviy ishi yoki magistrlik dissertatsiyasi himoya qilingan (40+);
  - YDA topshirilgan (40+).
- Bitiruv ishi bo'yicha mavzu, ilmiy rahbar, himoya sanasi, holat va ball yuritiladi. YDA natijasini Akademik bo'lim kiritadi.
- Diplomlar reyestri:
  - seriya `B-yy` yoki `M-yy`, raqam 6 xonali va ketma-ket*;
  - raqam faqat imzolangan «Bitirish» buyrug'idagi, holati «bitirgan» bo'lgan talabaga beriladi.
- **Imtiyozli diplom** qoidasi (institut nizomi bilan tasdiqlanadi*): fanlarning kamida 75% i «A» (65+) bo'lishi kerak,
  hech bir fan «C» dan past (50 dan kam) bo'lmasligi kerak, qayta topshirish bo'lmasligi kerak, bitiruv ishi va YDA «A» bo'lishi kerak.
  Qoida `RULES["honours"]` da turadi.
- Diplom ilovasi DOCX ko'rinishida chiqadi. Unda barcha semestrlar fanlari, kredit, ball, 5 ballik baho, harf, jami kredit, GPA, bitiruv ishi va YDA bor.
  Diplom raqami berilmagan bo'lsa, «LOYIHA» belgisi bilan chiqadi.
- «Bitirish» buyrug'i (`bitirish`) talaba holatini «bitirgan» ga o'zgartiradi.

## Demo ma'lumotlar (sun'iy)
Demo ma'lumotlar server birinchi marta ishga tushganda bir marta yoziladi (`flow_meta.seeded`). Bu `orders.bind` dan keyin, reyting keshidan oldin bo'ladi.
Toza `python -m app.seed` dan keyin server ishga tushishi bilan ular avtomatik paydo bo'ladi. Ular quyidagilarni o'z ichiga oladi:
- **Sessiyalar:** 7 ta sessiya. Kunduzgi va sirtqi qishki sessiyalarning jadvali to'liq va e'lon qilingan. Masofaviy sessiya loyiha holatida, unda 2 ta ataylab qoldirilgan to'qnashuv bor.
- **Qayta topshirishlar:** yozgi qayta topshirishda o'tmaganlar (bulardan qayta o'qish takliflari, qarorlar va to'lovlar chiqadi) va kuzgi qo'shimcha muddatdagi qayta topshirishlar (yaqinda e'lon qilingan).
- **Apellyatsiyalar:** 8 ta, turli bosqichlarda: yangi, ovoz berilmoqda, qaror chiqarilgan.
- **Chetlashtirish:** imzolangan tarixiy buyruq (2 talaba) va yangi loyiha (3 talaba). Chetlashtirilgan talabalardan biri qayta tiklash arizasini bergan.
- **Ko'chirish:** barcha turlar bo'yicha arizalar.
- **ISFT granti:** 2026-2027 raundi komissiya ko'rib chiqishida turibdi.
- **Bitiruv ishlari:** barcha bitiruvchi kurs talabalarining mavzulari va rahbarlari.
- **Magistr bitiruvchilari (2026):** uchta `MAG-*-2401` guruhida 27 bitiruvchi. Ular uchun imzolangan bitirish buyrug'i va diplomlar reyestri bor (imtiyozli diplomlar ham).
  Yana 3 ta «kechiktirilgan» bitiruvchi bor: ular sentabrda qarzini topshirgan, oktabrda qo'shimcha YDA dan o'tgan va hozir bitirish talablariga to'liq javob beradi.
