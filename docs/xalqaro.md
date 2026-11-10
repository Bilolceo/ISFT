# Xalqaro hamkorlik — ish jarayonlari

Modul: `app/xalqaro.py` (API `/api/xalqaro`), interfeys: `static/xalqaro.js` / `xalqaro.css`. Talaba kabineti sahifasi: `static/xalqaro_talaba.js`.
Test: `tests/test_xalqaro.py`. Audit resursi: `international`.

## 1. Hamkorlik shartnomasi hayotiy sikli

```
qoralama ──► yuridik ko'rik ──► rektor imzosida ──► amalda ──► (90 / 30 kun ogohlantirish) ──► uzaytirildi | muddati tugagan
    ▲             │ e'tiroz             │ qaytarish
    └─ qaytarildi ◄┘─────────────────────┘
```

| Bosqich | Kim | Amal |
|---|---|---|
| Qoralama | Xalqaro hamkorlik bo'limi | Hamkor, davlat, turi, muddat, KPI rejasi (almashinuv, qo'shma dastur) |
| Yuridik ko'rik | Yuridik bo'lim | «Mos» → rektor imzosiga; «E'tiroz» (izoh majburiy) → qaytariladi |
| Imzo | Rektor | Imzolash yoki qaytarish (sabab majburiy); amaldagini muddatidan oldin bekor qilish |
| Amalda | — | Imzolangan shartnoma hamkorlar reyestriga (`partners`) avtomatik yoziladi: panel, agentlar, Portal ma'lumotlari shu yerdan |
| Tugamoqda | — | 90 kun qolganda — sariq, 30 kun qolganda — qizil belgi; uzaytirish boshlanmagan bo'lsa panelda ogohlantirish |
| Uzaytirish | Xalqaro bo'lim | Yangi qoralama eski shartnomaga bog'lanadi, xuddi shu yo'ldan o'tadi; imzolangach eskisi «uzaytirildi», hamkor yozuvi bitta qoladi |
| Muddati tugagan | tizim | Tugash sanasi o'tgach avtomatik; reyestrda «muddati tugagan» |

Har shartnomada **tadbirlar** (almashinuv, qo'shma dasturga qabul, ilmiy loyiha, tashrif) qayd etiladi — KPI fakti shulardan hisoblanadi.
Tarix jurnali har bir o'tishni (kim, qachon, izoh) saqlaydi.

## 2. Akademik mobillik (almashinuv)

1. **Tanlov e'loni** (Xalqaro bo'lim, faqat amaldagi shartnoma asosida): o'rinlar, minimal GPA, til bali (IELTS shkalasida), minimal kurs,
   akademik qarzsizlik, ariza muddati, mobillik sanalari.
2. **Arizalar**: xodim HEMIS ID bo'yicha kiritadi yoki talaba o'zi kabinetdan («Xalqaro almashinuv» sahifasi) beradi.
3. **Avtomatik tekshiruv**: GPA — oxirgi yakunlangan semestr, reyting tizimi bilan bir xil (`rating_cache`); akademik qarz —
   `academic_rules.debt_where`; faol talaba, kurs va til bali. Mos kelmasa sababi yoziladi.
4. **Komissiya** (Xalqaro bo'lim va ilmiy ishlar prorektori): qabul yopiladi, har muvofiq arizaga suhbat bali (0–15).
   Jami = GPA/5 × 60 + til bali/9 × 25 + suhbat.
5. **Saralash**: o'rinlar soni — «saralandi», keyingi 3 tasi — «zaxira». Saralangan voz kechsa birinchi zaxiradagi avtomatik o'tadi.
6. **Jo'nash → qaytish**: qaytishda olingan kredit va transkript izohi kiritiladi; ariza **Akademik bo'lim** navbatiga tushadi.
7. **Kredit tan olish** (Akademik bo'lim): to'liq, qisman (farq fanlari izohi bilan) yoki tan olinmadi.

## 3. Xorijiy talabalar

Viza turi va raqami, viza va ro'yxatga olish muddatlari. 60 kun qolganda — sariq, 30 kun yoki o'tib ketganda — qizil.
Pasport raqamidan faqat oxirgi 4 belgi saqlanadi. Ro'yxat (ism-shariflar) — Xalqaro bo'lim va kurator; rektor va kengashga — faqat soni.

## 4. Delegatsiyalar

Tashkilot, davlat, rahbar, kishi soni, sanalar, maqsad, mezbon, bog'liq shartnoma. Tashrifdan keyin natija (kelishuvlar, keyingi qadamlar)
majburiy yoziladi; hali bo'lmagan tashrif «o'tkazildi» deb belgilanmaydi.

## Ruxsatlar

| Lavozim | Ko'radi | Qiladi |
|---|---|---|
| Xalqaro hamkorlik bo'limi | hammasi | qoralama, yuborish, uzaytirish, tadbir, tanlov, ariza, saralash, jo'nash/qaytish, xorijiy talabalar, delegatsiyalar |
| Yuridik bo'lim | shartnomalar, umumiy | yuridik xulosa (mos / e'tiroz) |
| Rektor | umumiy, shartnomalar, mobillik (jamlangan, ismlarsiz), delegatsiyalar | imzolash, qaytarish, amaldagini bekor qilish |
| Ilmiy ishlar prorektori (kurator) | umumiy, shartnomalar, mobillik (ismlar bilan), xorijiy talabalar, delegatsiyalar | komissiya bali |
| Kuzatuv kengashi | faqat umumiy (jamlangan) | — |
| Akademik bo'lim | faqat kredit tan olish navbati | kredit qarori |
| Talaba | ochiq tanlovlar, o'z arizalari | ariza berish (faqat faol, muddat ichida) |

Boshqa lavozimlar — 403 (audit jurnaliga yoziladi).

## Demo ma'lumot

Bo'sh bazada (`intl_agreements` jadvali bo'sh bo'lsa) ishga tushganda yaratiladi: `partners` reyestridagi shartnomalar (muddati o'tganlari —
«muddati tugagan»), navbatdagi uchta shartnoma (qoralama, yuridik ko'rikda, uzaytirish — rektor imzosida), uchta tanlov (ochiq; mobillikda;
qaytgan, kredit tan olish kutilmoqda), 10 ta sintetik xorijiy talaba («namuna»), 4 ta delegatsiya. Talabalar — mavjud sintetik bazadan.
