# Reyting — talabalar o'zlashtirish ko'rsatkichlarini reyting baholash tizimi

To'liq nomi: **«Oliy ta'lim muassasasi talabalarining o'zlashtirish ko'rsatkichlarini reyting baholash avtomatlashtirilgan tizimi»**.
Menyu: **Ish jarayonlari → Reyting**. Kod: `app/reyting.py`, `static/reyting.js`, `static/reyting.css`; qoidalar — `app/academic_rules.py`;
testlar — `tests/test_reyting.py`.

## Nima qiladi

| Bo'lim | Mazmuni |
|---|---|
| Umumiy | Reytingdagi talabalar soni, o'rtacha GPA (o'tgan semestrga nisbatan), akademik qarzdorlar va a'lochilar ulushi, GPA taqsimoti; fakultet, daraja/kurs va ta'lim shakli bo'yicha jadval |
| Reyting ro'yxati | O'rin (guruh / kurs / yo'nalish / fakultet / institut darajasida) «37 / 1 240» va «yuqori 3%»; filtrlar: semestr, fakultet, kurs, guruh, ta'lim shakli, «faqat qarzdorlar», «faqat a'lochilar»; qidiruv (F.I.Sh., HEMIS ID, guruh); saralash; sahifalash. Ustunlar: o'rin, talaba, guruh, GPA, o'rtacha ball, davomat, kredit (o'zlashtirilgan / jami), «F» soni, o'tgan semestrga nisbatan o'rin o'zgarishi (▲/▼) |
| Talaba kartasi | Har bir yakunlangan semestr fanlari: ball, oraliq/yakuniy (bazada saqlangan), harf, 5 ballik baho, o'quv rejasi krediti, o'qituvchi, urinishlar; semestr va kumulyativ GPA (5); kreditlar dastur hajmiga nisbatan (240 / 120); joriy semestr — faqat oraliq nazorat (yakuniyga kirish); besh darajadagi o'rin va o'zgarishi; barcha semestrlar bo'yicha trend |
| Qaydnoma | Guruh × fanlar jadvali: ballar, GPA, o'rtacha ball, «F», guruh va kurs o'rni; fan bo'yicha o'rtacha va o'tish foizi. Eksport: **.xlsx** va **.docx** (ISFT blanki, albom yo'nalishi, «Registrator ofisi boshlig'i» va «Akademik faoliyatni boshqarish bo'limi boshlig'i» imzo qatorlari — ismlar `org_units`dan) |
| Dinamika | Oxirgidan oldingi yakunlangan semestrdan oxirgisiga (2025-26 kuzgi → 2025-26 bahorgi): eng ko'p ko'tarilgan va tushgan talabalar (tanlangan daraja o'rni bo'yicha), o'rtacha GPA o'sgan/pasaygan guruhlar |
| A'lochilar | Mukofot uchun ro'yxat: kurs bo'yicha eng yaxshi N% (standart 10%), «F» ≤ chegara (standart 0), davomat ≥ chegara (standart 85%). Eksport: **.xlsx** |
| Bo'linmalar | Guruhlar, kafedralar, o'qituvchilar — o'zlariga tegishli baholarning o'tish foizi va o'rtacha bali bo'yicha; kichik namunalar reytingga kirmaydi |
| Metodika | Formula, teng kelganda tartib, chegaralar va izohlar — barchasi `academic_rules.py` dan olinadi (kodda bitta joyda) |

## Metodika

**Manba.** Reyting `grades` jadvalidagi YAKUNLANGAN semestrlarning hisobdagi 100 ballik ballaridan hisoblanadi (qayta topshirilgan bo'lsa —
hisobdagi urinish; tarix `grade_attempts` da). Semestr kodi: `0` — 2025-2026 bahorgi (standart), `-1` — 2025-2026 kuzgi, … `-5` — 2023-2024
kuzgi (hozirgi 4-kursning 1-semestri). Joriy semestr (`1`, 2026-2027 kuzgi) reytingga kirmaydi: noyabrda faqat oraliq nazorat (30 ball)
o'tkazilgan, yakuniy nazorat — qishki sessiyada; joriy oraliq natijalari talaba kartasida alohida, ruxsatnoma va Talabalar markazida ishlatiladi.
1-kurs talabalarining yakunlangan semestri hali yo'q — ular reytingda ko'rinmaydi (kartasida joriy semestr bor).

**GPA (5 ballik, kredit bilan tortilgan).** `GPA = Σ(kredit × baho) / Σ kredit`. Baho — institut shkalasi bo'yicha:
65–100 → «5» (A), 60–64 → «4» (B), 50–59 → «4» (C), 45–49 → «3» (D), 40–44 → «3» (E), 0–39 → «2» (F). Natija 2 xonagacha,
aniq «yarimdan yuqoriga» yaxlitlanadi (`academic_rules.ratio2`): butun sonlardan hisoblangani uchun SQL kesh, talaba kartasi va
transkript bir xil raqam ko'rsatadi (4.625 → 4.63).

**Kredit manbai — o'quv rejasi.** `curriculum` jadvali: har yo'nalish × daraja × dastur semestri uchun turli fanlar va kreditlar
(har semestr 30 kredit; bakalavriat 8 × 30 = 240, magistratura 4 × 30 = 120; demo TAXMIN — institutning haqiqiy o'quv rejasi kiritilganda
almashtiriladi). Kredit baho qatorida ham (`grades.credits`) — reyting, transkript va Talabalar markazidagi kumulyativ GPA bir xil qiymatni
oladi. O'quv rejasida yo'q fan uchun (eski baza) — standart 6 kredit, kartada «*» bilan.

**Yagona ta'riflar (`academic_rules`).** *O'rtacha ball (100)* — fanlar bo'yicha 100 ballik ballarning oddiy o'rtachasi; *GPA (5)* — kredit
bilan tortilgan 5 ballik baho. `students.gpa` / `gpa_prev` — HISOBLANGAN qiymat: oxirgi va undan oldingi yakunlangan semestrning o'rtacha
bali (100), reyting keshidagi `avg_score` bilan bir xil formula (`ratio2`); otrabotka tasdiqlansa qayta hisoblanadi. Shuning uchun boshqaruv
panelidagi «O'rtacha ball (100)» = Reyting → Umumiy → «O'rtacha ball (100)». *Akademik qarzdor* — barcha yakunlangan semestrlar bo'yicha
kamida bitta o'zlashtirilmagan fani bor faol talaba (Umumiy ko'rinishdagi asosiy son, Talabalar markazi bilan bir xil); jadvaldagi
«Qarzdor (sem.)» — faqat shu semestrdan qolgan qarz.

**Tartib (teng kelganda).** 1) semestr GPA (2 xona) ↓; 2) o'rtacha ball (100 ballik, fanlar bo'yicha oddiy o'rtacha, 2 xona) ↓;
3) davomat, % ↓ (qayd etilmagan — masofaviy ta'lim — oxirida). Hammasi ko'rsatilgan (yaxlitlangan) qiymatlar bo'yicha — foydalanuvchi
ko'rgan raqamlardan tartibni tekshira oladi. Barcha mezonlari to'liq teng talabalar bir xil o'rinni oladi, keyingisi o'tkazib
yuboriladi (`RANK()`: 1, 2, 2, 4). Davomat: oxirgi yakunlangan semestr reytingida — joriy davomat; undan oldingi semestrlar davomati
bazada saqlanmagan — u yerda faqat GPA va o'rtacha ball.

**Darajalar.** Guruh; kurs (daraja + kurs, butun institut — bakalavr va magistr alohida); yo'nalish (daraja + yo'nalish, barcha
kurslar); fakultet; institut. Foiz — «yuqoridan necha foiz ichida» = o'rin / jami × 100, yuqoriga yaxlitlanadi.

**Kim reytingda.** Faqat `status='faol'` talabalar (akademik ta'tildagilar kartasida baholari ko'rinadi, o'rni yo'q). Kamida bitta
«F» (40 balldan past) bo'lgan talaba reytingda qoladi va **«akademik qarzdor»** deb belgilanadi. **A'lochi** — semestrdagi barcha
fanlardan kamida 65 ball («5»).

**A'lochilar ro'yxati.** Kurs (daraja + kurs) reytingida o'rni ≤ ⌈N% × kursdagi talabalar⌉, «F» soni ≤ chegara, davomat ≥ chegara
(masofaviy talabaga davomat sharti qo'llanmaydi; oxirgi yakunlangan semestrdan oldingilar uchun davomat sharti qo'llanmaydi). Ro'yxat foydalanuvchi ko'lamida.

**Bo'linmalar.** Guruh — guruh talabalarining baholari; kafedra — kafedra o'qituvchilari qo'ygan baholar (shuning uchun guruhi
yo'q «Fundamental iqtisodiy fanlar» kafedrasi ham reytingda); o'qituvchi — o'zi qo'ygan baholar. Tartib: o'tish foizi (≥ 40) ↓,
o'rtacha ball ↓. Minimal namuna: guruh ≥ 10 talaba, kafedra ≥ 150 baho, o'qituvchi ≥ 30 baho — kichiklari «kam namuna» bilan
alohida ko'rsatiladi va o'rin olmaydi. O'rin har doim butun institut bo'yicha.

**Oraliq / yakuniy.** Bazada alohida saqlanadi: `grades.oraliq` (0–30), `grades.yakuniy` (0–70), `grades.score` — hisobdagi jami.
Oraliq < 12 bo'lsa talaba yakuniyga kiritilmagan (`yakuniy` bo'sh). Qayta topshirish urinishlari `grade_attempts` da (asl urinish ham),
hisobdagi — eng yuqorisi: o'tgan baho pasaytirilmaydi.

## Kesh va tezlik

- `rating_cache` — har talaba × yakunlangan semestr uchun GPA, o'rtacha ball, kreditlar, «F», besh darajadagi o'rin va jami. Bitta SQL so'rov
  (`RANK() OVER (PARTITION BY …)`) bilan ~2 soniyada quriladi (~79 ming qator: 6 ta yakunlangan semestr, ~390 ming baho).
  `rating_credits` — fan krediti ma'lumotnomasi (metodika uchun), `rating_meta` — barmoq izi, vaqt, sabab.
- Server ishga tushganda kesh yo'q bo'lsa yoki manba (baholar va kreditlar, talaba holati/guruhi/davomati, guruh kursi, o'quv rejasi,
  shuningdek kesh formulasi versiyasi va baholash qoidalari) o'zgargan bo'lsa — avtomatik qayta quriladi. Ish paytida 30 soniyada bir marta
  tekshiriladi (masalan, otrabotka bahosi tasdiqlansa). Kesh formulasi o'zgarsa `CACHE_VERSION` oshiriladi (hozir 3).
- Qo'lda: «Qayta hisoblash» tugmasi (`POST /api/reyting/recompute`) — Registrator ofisi (boshliq va xodim) va Akademik bo'lim.
- Qo'shimcha indekslar: `grades(student_id, semester)`, `grades(teacher_id)`.

## Ruxsatlar (serverda tekshiriladi, audit — resurs `rating`)

| Lavozim | Ko'radi |
|---|---|
| Registrator ofisi (boshliq #17, xodim #43), Akademik bo'lim (#18), Rektor (#2), O'quv prorektori (#3), Imtihon bo'limi, Ma'lumotlar bazasi bo'limi | Butun institut, barcha bo'limlar |
| Sirtqi bo'lim (#27) | Faqat sirtqi ta'lim talabalari (`study_form='sirtqi'`) |
| Kafedra mudiri (masalan, #31) | O'z kafedrasi guruhlari; bo'linmalar — o'z kafedrasi va uning o'qituvchilari |
| Tyutor | O'ziga biriktirilgan guruhlar (`tutor_groups`, ~10 kunduzgi guruh) |
| O'qituvchi (#15) | Faqat o'zi baho qo'ygan talabalar; o'qituvchilar reytingida — faqat o'zi |
| Kuzatuv kengashi (#1), ilmiy / moliya / yoshlar prorektorlari, Sifatni ta'minlash boshqarmasi | Faqat jamlangan: taqsimot, o'rtacha qiymatlar, guruhlar dinamikasi. Ism-sharif va HEMIS ID umuman yuborilmaydi; ro'yxat, karta, qaydnoma, a'lochilar, o'qituvchilar — 403 |
| Qolganlar (masalan, Buxgalteriya #11) | 403; menyuda ko'rinmaydi |

Har bir murojaat (ruxsat etilgan va rad etilgan) audit jurnaliga yoziladi: `reyting: …` amallari, resurs `rating`.

## API

`GET /api/reyting/meta` · `overview?sem=` · `list?sem&level&faculty&course&group&form&flag&q&sort&dir&page&per` · `student/{id}` ·
`qaydnoma/{guruh}?sem=` · `qaydnoma/{guruh}/export?sem&fmt=xlsx|docx` · `dynamics?level&limit` · `top?sem&pct&min_att&max_f` ·
`top/export` · `units?kind=group|kafedra|teacher&sem` · `methodology` · `POST /api/reyting/recompute`.

## Cheklovlar (demo)

- O'quv rejasi va fanlar — demo (TAXMIN); institutning haqiqiy rejasi `curriculum` jadvaliga kiritilganda kesh o'zi qayta quriladi.
- O'tgan semestrlar davomati saqlanmagan.
- Talabalar markazidagi «O'zlashtirish» qoidasi kumulyativ GPA (5) ni xuddi shu kreditlar bilan hisoblaydi (`academic_rules.akademik_level`).
