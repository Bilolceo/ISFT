# Amaliyot — talabalar amaliyoti

Modul: `app/amaliyot.py`. API manzili: `/api/practice`. Xodimlar sahifasi: menyuda «Amaliyot» (`static/amaliyot.js`). Talaba uchun: kabinetdagi «Amaliyot» sahifasi (`static/amaliyot_talaba.js`).
Ruxsatni modul o'zi tekshiradi (lavozimlar jadvali quyida). Har bir murojaat audit jurnaliga `resource=practice` bilan yoziladi.

## Ish jarayoni

1. **Amaliyot bazalari reyestri.** Har bir baza uchun quyidagilar yuritiladi:
   - tashkilot va uning turi, manzil, mas'ul shaxs;
   - hamkorlik shartnomasi: raqami, imzolangan sanasi, amal qilish muddati;
   - har bir yo'nalish bo'yicha **sig'im**, ya'ni bir vaqtda nechta talaba qabul qilinishi.

   Shartnoma holati 4 xil bo'ladi: «amalda», «tugayapti» (30 kundan kam qolgan), «muddati o'tgan» va «to'xtatilgan».
2. **Amaliyot davrlari.** Davr har bir guruh uchun alohida ochiladi. Ikki yo'l bor:
   - **o'quv reja bo'yicha.** `curriculum` jadvalida joyda o'tadigan amaliyot fani bor guruhlar tanlanadi («Malakaviy amaliyot», «…pedagogik amaliyot»). Bu ish joriy yoki keyingi semestr uchun bajariladi. «Nutq amaliyoti» kabi auditoriya fanlari bu ro'yxatga kirmaydi;
   - **alohida jadval bo'yicha.** Turi, sanasi va krediti qo'lda kiritiladi.

   Bitta guruhda bir vaqtning o'zida ikkita davr bo'lishi mumkin emas. Hisobot muddati bo'sh qoldirilsa, u amaliyot tugaganidan keyin 7-kun bo'ladi.
3. **Talabalarni biriktirish.** Butun guruh bo'yicha («barcha biriktirilmaganlar») yoki tanlangan talabalar bazaga biriktiriladi. Tizim quyidagilarni tekshiradi:
   - **sig'im.** Shu yo'nalish bo'yicha, muddati kesishgan barcha davrlar hisobga olinadi;
   - **shartnoma muddati.** Shartnoma amaliyot tugaguncha amal qilishi kerak;
   - **kafedradan amaliyot rahbari.** U faqat guruh kafedrasining o'qituvchisi bo'la oladi.

   Tashkilot tomonidan rahbarning ismi va telefoni ham yoziladi.
4. **Yo'llanma.** Hujjatlar markazidagi «Amaliyot yo'llanmasi» shabloni (`practice`) ishlatiladi. Har bir talabaga ro'yxatga olingan raqam beriladi (AY-…) va u biriktirish yozuviga saqlanadi.
5. **Kuzatuv.** Holatlar ketma-ketligi: biriktirildi → amaliyotda → hisobot topshirildi → baholandi. Hisobot sabab ko'rsatilib qaytarilishi mumkin; shunda holat «hisobot qaytarildi» bo'ladi.
   - **Kundalik.** Talaba kabinetda yozadi, rahbar izoh qoldiradi.
   - **Hisobot.** Talaba kabinetda topshiradi (kamida 200 belgi) yoki rahbar qog'ozdagi hisobotni qabul qilib, tizimda qayd etadi.
   - **Baho.** Bahoni **faqat kafedra rahbari** qo'yadi: biriktirilgan o'qituvchi yoki kafedra mudiri. Shkala 0–100, o'tish bali 40, harf — `academic_rules`. Qo'yilgan bahoni o'zgartirish uchun sabab yozish majburiy.
6. **Ogohlantirishlar:**
   - hisobot muddati o'tgan;
   - amaliyot boshlanganiga 3 kun bo'lgan, lekin «amaliyotga chiqdi» belgilanmagan;
   - hisobot 7 kundan ortiq baholanmagan;
   - talaba biriktirilmagan;
   - shartnoma muddati tugayapti yoki o'tgan.
7. **Statistika** amaliyot turi, baza va guruh kesimida: qamrov, hisobot, baholar, o'rtacha ball va o'tmaganlar.

## Lavozimlar

| Lavozim | Rejim | Nima qila oladi |
|---|---|---|
| Amaliyot bo'limi | full | Bazalar, davrlar (jadval va o'quv reja), biriktirish, yo'llanma, holatlar, kundalikka izoh. Baho qo'ymaydi |
| Kafedra mudiri | kafedra | O'z kafedrasi guruhlari: amaliyot rahbarini tayinlash, hisobotni qabul qilish yoki qaytarish, baholash, o'quv rejani ko'rish |
| O'qituvchi | oqituvchi | Faqat o'zi rahbarlik qilayotgan talabalar: kundalik, hisobot, baho |
| Tyutor | tyutor | O'z guruhlari, faqat ko'rish |
| Registrator ofisi va uning xodimi | reg | Barcha davrlar, faqat ko'rish |
| Sirtqi bo'lim | reg | Faqat sirtqi guruhlar, faqat ko'rish |
| Rektor, o'quv prorektori | lead | Statistika va bazalar, ism-shariflarsiz |
| Talaba (kabinet) | — | O'z amaliyoti, kundalik yozish, hisobot topshirish, bahoni ko'rish |

## Demo ma'lumot

Jadvallar bo'sh bo'lsa, server ishga tushganda demo ma'lumot avtomatik yaratiladi:
- 13 ta shartli (sintetik) tashkilot. Ulardan bittasining shartnomasi tugayapti, yana bittasiniki tugagan;
- 3 ta amaliyot turi: davom etayotgan ishlab chiqarish amaliyoti, tugagan va muddati o'tgan hisobotlari bor o'quv-tanishuv amaliyoti, hisobot topshirish bosqichidagi pedagogik amaliyot.

Talabalar va o'qituvchilar bazadagi mavjud yozuvlardan olinadi.

## Sozlanadigan qoidalar (`RULES`)

| Kalit | Ma'nosi | Qiymat |
|---|---|---|
| `start_grace_days` | Amaliyotga chiqish belgilanishi kerak bo'lgan muddat | 3 kun |
| `report_after_days` | Standart hisobot muddati (amaliyot tugaganidan keyin) | 7 kun |
| `grade_days` | Hisobotni baholash muddati | 7 kun |
| `agreement_warn_days` | Shartnoma tugashi haqida oldindan ogohlantirish | 30 kun |
| `report_min_chars` | Hisobot matnining eng kam uzunligi | 200 belgi |

## Cheklovlar

- Amaliyot bahosi `grades` jadvaliga (HEMIS) yozilmaydi. U amaliyot jurnalida saqlanadi, chunki HEMIS integratsiyasi bu ish doirasiga kirmaydi.
- Tashkilot tavsifnomasi va imzolangan kundalik qog'ozda topshiriladi. Fayl yuklash keyingi bosqichda qo'shiladi.

## Test

`tests/test_amaliyot.py` — 95 ta tekshiruv. `tests/run_all.py` uni avtomatik topadi.
