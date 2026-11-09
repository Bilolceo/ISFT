# Talabalar bilan ishlash markazi — dizayn hujjati (v0.1, 2026-11-06)

Manba: Samarqand tajribasi asosidagi og'zaki talablar (ovozli xabar xulosasi). Bu hujjat — qurilgan narsaning chegarasi,
qoidalari va ochiq savollari. **Qoidalardagi raqamlar institut tomonidan tasdiqlanmagan** — tizimda "tasdiqlanmagan" belgisi bilan ko'rinadi.

## Maqsad
Registrator departamenti, tyutorlar va call-markaz uchun yagona ish navbati: tizim talabalar holatini har kuni o'zi tekshiradi,
muammo topsa — mas'ulga aniq topshiriq (kimga, nima, qachongacha, nima deyish) beradi va natijani kuzatadi.
Qaror va imzo — har doim odamda.

## Doira
| Faza | Tarkib | Holat |
|---|---|---|
| 1 | Xavf registri (kontrakt, davomat, akademik, kasallik/komandirovka hujjati, akademik ta'til muddati), call-markaz navbati, va'da → qayta qo'ng'iroq, ogohlantirish zinapoyasi, ogohlantirish xati / hayfsan loyihasi | ✅ qurildi |
| 2 | Otrabotka: varaqa (QR, ro'yxat raqami) → muddat → yuklash → baho yonma-yon → tasdiqlash → baho o'tadi | ✅ qurildi |
| 3 | Arizadan buyruq loyihasi, Excel ro'yxat versiyalari (kim/nima o'zgardi), shaxsiy grafik QR | keyingi |
| 4 | Muammoli talabalar: ikki marta buyruqda, eski guruhda qolgan, hech bir buyruqda yo'q (HEMIS/buyruqlar bazasi kerak) | keyingi |

## Tamoyillar
1. **Deterministik qoidalar.** Signal va topshiriqlar kod bilan hisoblanadi (SQL + Python), AI emas. Har bir topshiriqda "nega" (fakt) ko'rinadi.
2. **Idempotentlik.** Bitta talaba + bitta qoida = bitta ochiq holat (`ops_cases.key` UNIQUE). Dvigatel necha marta ishlasa ham dublikat yo'q.
   Daraja oshsa — yangi topshiriq; shart yo'qolsa (masalan, to'lov qilindi) — holat avtomatik yopiladi va sababi yoziladi.
3. **Me'yoriy havolalar o'ylab topilmaydi.** Suhbat skriptidagi huquqiy asos faqat institut kiritgan ro'yxatdan; bo'sh bo'lsa — "kiritilmagan" deb ko'rsatiladi.
4. **OCR/imzo tekshiruvi va'da qilinmaydi.** Otrabotka varaqasi tizimda QR bilan chiqariladi; yuklangan skan yonida baho qo'lda kiritiladi va tasdiqlanadi.
   Lokal OCR — keyingi bosqich (serverda o'rnatilmagan).
5. **Shaxsiy ma'lumot minimal.** Rektor — faqat jamlangan raqamlar; call-markaz — faqat o'z navbatidagi talaba, telefon va skript; tyutor/dekan — o'z fakulteti.
6. **"Tizim o'zi o'rganadi" emas.** Yaxshilanish — qoidalar va shablonlarni foydalanuvchi fikri asosida sozlash orqali.

## Qoidalar (standart qiymatlar — TASDIQLANMAGAN)
| Kalit | Qiymat | Ma'nosi |
|---|---|---|
| `contract_critical_days` | 3 | Navbatdagi to'lov muddatiga ≤3 kun qolgan va yetarli to'lanmagan → kritik |
| `att_call_hours` | 30 | Sababsiz qoldirilgan soat ≥30 → call-markaz qo'ng'irog'i |
| `att_letter_hours` | 48 | ≥48 → ogohlantirish xati (registrator) |
| `att_reprimand_hours` | 72 | ≥72 → hayfsan buyrug'i loyihasi + tyutor suhbati |
| `pass_score` | 40 | Fan bo'yicha o'tish bali (100 ballik, «3») — institut qoidasi (akademik qoidalar taqdimoti), tasdiqlangan |
| `gpa_min` | 3.0 | JPA minimal (5 ballik) |
| `fails_warn` | 2 | Shuncha fandan o'tmasa — JPA yetarli bo'lsa ham ogohlantirish |
| `medical_doc_days` | 3 | Kasallikdan keyin hujjat topshirish muddati (kun) |
| `leave_warn_days` | 30 | Akademik ta'til tugashiga shuncha kun qolganda ogohlantirish |
| `retake_days` | 3 | Otrabotka varaqasini qaytarish muddati (kun) |
| `call_max_attempts` | 3 | Javob bermasa — shuncha urinishdan keyin tyutorga o'tadi |
| `call_daily_capacity` | 60 | Bir operatorning kunlik qo'ng'iroqlari: bugungi ro'yxat = operatorlar × 60; qolganlari jiddiylik tartibida keyingi ish kunlariga rejalashtiriladi (`ops_tasks.planned_on`), hech biri o'chirilmaydi |

Sababli dars qoldirish (kasallik — tasdiqlangan hujjat bilan, komandirovka, mehnat ta'tili) zinapoyaga qo'shilmaydi;
hujjati yo'q bo'lsa — alohida "hujjat so'rash" topshirig'i.

## Rollar
| Rol | Ko'radi | Qiladi |
|---|---|---|
| Registrator ofisi (Akademik faoliyatni boshqarish bo'limi — ko'rish) | Barcha holatlar | Xat/hayfsan loyihasi, otrabotka tasdiqlash, topshiriqni qayta yo'naltirish |
| Call-markaz operatori | O'z navbatidagi qo'ng'iroqlar | Natija: gaplashildi / va'da (sana) / javob bermadi / noto'g'ri raqam |
| Tyutor (fakultet) | O'z fakulteti | Suhbat, hujjat so'rash, otrabotka varaqasi berish |
| Dekan | O'z fakulteti (o'qish) | — |
| O'quv ishlari bo'yicha prorektor | Barchasi (o'qish) | — |
| Rektor | Faqat jamlangan raqamlar | — |

## Ochiq savollar (institutga)
1. Davomat chegaralari: "50%" va "30 soat" nimani anglatadi; har bosqichning rasmiy chegarasi va asos hujjati.
2. JPA shkalasi (5 yoki 4 ballik), kreditlar, ogohlantirish qoidasi.
3. Kontrakt to'lov jadvali (bo'lib to'lash sanalari va foizlari).
4. Call-markaz bormi yoki bu vazifani tyutorlar bajaradimi.
5. Buyruq/xat shablonlari va tayaniladigan me'yoriy hujjatlar ro'yxati.
6. Komandirovka/mehnat ta'tili — sirtqi talabalar uchunmi.

## Amalga oshirish
- Kod: `app/student_ops.py` (sxema, dvigatel, API `/api/ops/*`), shablonlar `app/documents.py` (`warn_letter`, `reprimand`, `retake_sheet`), UI `static/app.js` (`renderOps`).
- Dvigatel: server ishga tushganda va har 10 daqiqada (`poller`), har natija kiritilganda; qo'lda — "Hozir tekshirish".
- Testlar: `tests/test_talabalar_markazi.py` — ruxsatlar, idempotentlik, va'da → qayta qo'ng'iroq, 3 urinish → tyutor, hujjat → holat yopilishi,
  to'lov → holat yopilishi, xat/hayfsan hujjatlari, otrabotka (fayl tekshiruvi, rol cheklovlari, baho o'zgarishi, audit).
- Demo akkauntlar (parol Isft2026): call-markaz operatori (23), tyutorlar (24–26, har fakultetga bittadan); registrator — "Registrator ofisi" (17); "Akademik faoliyatni boshqarish bo'limi" (18) — ko'rish.
