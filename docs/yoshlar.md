# Yoshlar ishlari: turar joy va tadbirlar

Modul `app/yoshlar.py` (API: `/api/yoshlar/*`), interfeys «Yoshlar ishlari» (`static/yoshlar.js`). Talaba kabinetidagi «Turar joy» va «Tadbirlar» sahifalari `static/yoshlar_talaba.js` faylida. Test: `tests/test_yoshlar.py`.

Institutning o'z yotoqxonasi yo'q (NQAAE pasporti bo'yicha). Shuning uchun turar joy ikki yo'l bilan yuritiladi:

1. **Hamkor yotoqxonalar.** Institut joylarni shartnoma asosida oladi. Tizimda shartnoma raqami va muddati, bino, xona va o'rinlar yuritiladi. Shartnoma muddati tugashiga 60 kun qolganda ogohlantirish chiqadi.
2. **Ijarada yashovchilar.** Talabaning manzili qayd etiladi, tyutor tashrifi dalolatnoma sifatida yoziladi. 90 kundan beri tashrif bo'lmagan qaydlar alohida belgilanadi.

## Yotoqxona jarayoni

1. **Ariza.** Talaba arizani kabinetdan beradi. Ma'naviyat bo'limi, komendant yoki Registrator ofisi uni talaba nomidan kirita oladi.
   - Ariza faqat faol, kunduzgi ta'lim talabalaridan qabul qilinadi.
   - Toshkent shahrida yashovchilarga joy faqat imtiyozli toifa bo'lsa beriladi.
2. **Hujjat tekshiruvi.** Talaba imtiyoz da'vo qilgan bo'lsa, ariza «Yangi» holatida qoladi. Xodim hujjatlarni ko'rib, «Hujjatlar tekshirildi» tugmasini bosadi. Shundan keyin ariza navbatga o'tadi. Imtiyoz da'vo qilinmagan ariza darhol navbatga tushadi.
3. **Navbat.** Arizalar imtiyoz bali bo'yicha kamayish tartibida turadi, ball teng bo'lsa ariza vaqti hal qiladi. Ballar:

   | Toifa | Ball |
   |---|---|
   | Chin yetim yoki ota-ona qaramog'idan mahrum | +40 |
   | Nogironligi bor | +35 |
   | Ijtimoiy himoya reyestrida (Temir, Ayollar yoki Yoshlar daftari) | +30 |
   | Ko'p bolali yoki kam ta'minlangan oila | +15 |
   | Toshkentdan tashqari hududdan (avtomatik) | +20 |
   | 1-kurs talabasi (avtomatik) | +10 |
   | A'lochi, o'rtacha ball 86 va undan yuqori (avtomatik) | +5 |

4. **Joy berish (bron).** Joy faqat talabaning jinsiga mos xonadan beriladi. Xona tanlanmasa, birinchi bo'sh o'rin olinadi. «Navbat bo'yicha joylashtirish» tugmasi bo'sh o'rinlarni navbat tartibida bir yo'la to'ldiradi (prorektor va Ma'naviyat bo'limi).
5. **Joylashish va chiqish.**
   - Talaba kelgach «Joylashdi» bosiladi. Bron 7 kundan oshib ketsa ogohlantirish chiqadi. Bron bekor qilinsa, ariza navbatga qaytadi.
   - Chiqish sabab bilan rasmiylashtiriladi.
   - Talaba faol bo'lmay qolsa (chetlashtirilgan, ta'tilda yoki bitirgan), lekin hali yashayotgan bo'lsa, «nomuvofiqlik» ogohlantirishi chiqadi.
6. **To'lov.**
   - «Oylik hisob yaratish» shu oyda yashagan har bir talabaga bino tarifi bo'yicha hisob yozadi. Qayta bosilsa, mavjud hisoblar o'zgarmaydi.
   - To'lov muddati har oyning 10-sanasigacha.
   - Pul kassa yoki bank orqali qabul qilinadi. Tizimda faqat kvitansiya raqami bilan qayd etiladi; qisman to'lov ham mumkin. Qayd etishni komendant yoki buxgalteriya bajaradi.
7. **Tartib.**
   - Qoidabuzarlik qaydiga chora tanlanadi: ogohlantirish, hayfsan yoki chiqarish.
   - 3 ta qayd to'plansa, ogohlantirish chiqadi.
   - **Chiqarish faqat prorektor qarori bilan** qo'llanadi. Bu choradan keyin yashovchi avtomatik chiqariladi.

## Tadbirlar

Tadbir quyidagi bosqichlardan o'tadi:

1. **Reja.** Ma'naviyat bo'limi yoki prorektor tuzadi: sana, vaqt, joy, tur, kimlar uchun, joylar soni va smeta.
2. **Tasdiqlashga yuborish.** Joy va vaqt ko'rsatilmagan bo'lsa, tadbirni yuborib bo'lmaydi.
3. **Prorektor qarori.** Prorektor tasdiqlaydi yoki sabab yozib rad etadi. Rad etilgan tadbirni tuzatib, qayta yuborish mumkin.
4. **Ishtirokchilar.**
   - Talabalar tasdiqlangan tadbirga kabinetdan yoziladi; joylar soni cheklangan bo'lishi mumkin.
   - Qatnashuv tadbir kuni QR orqali («Murojaatlar» → Tadbirlar) yoki qo'lda belgilanadi.
5. **O'tkazildi va hisobot.** Hisobot kamida 20 belgidan iborat bo'lishi kerak. Ishtirokchilar soni sifatida QR yoki qayd bo'yicha sanalgan son olinadi; qo'lda kiritilgan son undan kam bo'lsa, sanalgani qoladi.
   - O'tib ketgan, lekin hisobot topshirilmagan tadbirlar ogohlantirishda ko'rinadi.

Eski tadbirlar (holati bo'lmaganlari) avtomatik «O'tkazildi» deb belgilanadi.

## Rollar

| Rol | Nima qila oladi |
|---|---|
| Yoshlar masalalari birinchi prorektori | Hammasi. Tadbirni tasdiqlaydi yoki rad etadi, yotoqxonadan chiqarish qarorini qabul qiladi |
| Ma'naviyat va ma'rifat bo'limi (`manaviyat`) | Arizalar, joy berish, navbat bo'yicha joylashtirish, binolar, oylik hisob, tartib qaydlari, ijara, tadbirlarni rejalashtirish va hisobot |
| Turar joy komendanti (`komendant`, bo'limi «Talabalar turar joyi») | Hujjat tekshiruvi, joy berish, joylashtirish va chiqarish, oylik hisob, to'lovni belgilash, tartib qaydlari (chiqarish chorasisiz). Tadbirlar bo'limi yopiq |
| Buxgalteriya | Faqat «To'lovlar» bo'limi: hisob yaratish va to'lovni belgilash |
| Tyutor | O'z guruhlari talabalarini ko'radi. Ijara qaydi va tashrif yozadi |
| Rektor | Faqat ko'rish |
| Registrator ofisi | Faqat ko'rish, talaba nomidan ariza kiritish mumkin |

Ma'naviyat bo'limi va «Talabalar turar joyi» bo'limining kuratori Yoshlar prorektori (`app/portal.py` CURATOR). Shu sababli prorektor bu bo'limlarga Portal va topshiriqlar orqali ish yubora oladi.

Har bir murojaat `audit_log` jurnaliga `resource=youth` bilan yoziladi. Talaba amallari ham shu resurs bilan, «Talaba» roli ostida yoziladi.

## Sozlanadigan qiymatlar

Bu qiymatlar vaqtinchalik va institut nizomi bilan tasdiqlanishi kerak. Ular `app/yoshlar.py` faylida, `CATS`, `AUTO`, `NEAR` va `RULES` o'zgaruvchilarida turadi:

- imtiyoz ballari;
- Toshkent shahri bo'yicha cheklov;
- to'lov muddati (10-sana);
- tartib qaydlari chegarasi (3 ta);
- bron muddati (7 kun).

Demo ma'lumot to'liq sintetik. U jadvallar bo'sh bo'lganda bir marta yaratiladi: 2 ta hamkor yotoqxona (171 o'rin), taxminan 200 ariza, oylik hisoblar, tartib qaydlari, 140 ta ijara qaydi va 4 ta tadbir.
