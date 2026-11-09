# Reyting — talabalar o'zlashtirish ko'rsatkichlarini reyting baholash tizimi

To'liq nomi: **«Oliy ta'lim muassasasi talabalarining o'zlashtirish ko'rsatkichlarini reyting baholash avtomatlashtirilgan tizimi»**.
Menyu: **Ish jarayonlari → Reyting**. Kod: `app/reyting.py`, `static/reyting.js`, `static/reyting.css`; qoidalar — `app/academic_rules.py`;
testlar — `tests/test_reyting.py`.

## Nima qiladi

| Bo'lim | Mazmuni |
|---|---|
| Umumiy | Reytingdagi talabalar soni, o'rtacha GPA (o'tgan semestrga nisbatan), akademik qarzdorlar va a'lochilar ulushi, GPA taqsimoti; fakultet, daraja/kurs va ta'lim shakli bo'yicha jadval |
| Reyting ro'yxati | O'rin (guruh / kurs / yo'nalish / fakultet / institut darajasida) «37 / 1 240» va «yuqori 3%»; filtrlar: semestr, fakultet, kurs, guruh, ta'lim shakli, «faqat qarzdorlar», «faqat a'lochilar»; qidiruv (F.I.Sh., HEMIS ID, guruh); saralash; sahifalash. Ustunlar: o'rin, talaba, guruh, GPA, o'rtacha ball, davomat, kredit (o'zlashtirilgan / jami), «F» soni, o'tgan semestrga nisbatan o'rin o'zgarishi (▲/▼) |
| Talaba kartasi | Har bir fan: ball, oraliq/yakuniy, harf, 5 ballik baho, kredit (manbasi bilan), o'qituvchi; semestr va kumulyativ GPA; besh darajadagi o'rin va o'zgarishi; semestrlar bo'yicha trend |
| Qaydnoma | Guruh × fanlar jadvali: ballar, GPA, o'rtacha ball, «F», guruh va kurs o'rni; fan bo'yicha o'rtacha va o'tish foizi. Eksport: **.xlsx** va **.docx** (ISFT blanki, albom yo'nalishi, «Registrator ofisi boshlig'i» va «Akademik faoliyatni boshqarish bo'limi boshlig'i» imzo qatorlari — ismlar `org_units`dan) |
| Dinamika | O'tgan semestrdan joriy semestrga: eng ko'p ko'tarilgan va tushgan talabalar (tanlangan daraja o'rni bo'yicha), o'rtacha GPA o'sgan/pasaygan guruhlar |
| A'lochilar | Mukofot uchun ro'yxat: kurs bo'yicha eng yaxshi N% (standart 10%), «F» ≤ chegara (standart 0), davomat ≥ chegara (standart 85%). Eksport: **.xlsx** |
| Bo'linmalar | Guruhlar, kafedralar, o'qituvchilar — o'zlariga tegishli baholarning o'tish foizi va o'rtacha bali bo'yicha; kichik namunalar reytingga kirmaydi |
| Metodika | Formula, teng kelganda tartib, chegaralar va izohlar — barchasi `academic_rules.py` dan olinadi (kodda bitta joyda) |

## Metodika

**Manba.** Reyting `grades` jadvalidagi yakuniy 100 ballik ballardan hisoblanadi (`semester=0` — yakunlangan 2025-2026 bahorgi semestr,
`semester=1` — joriy 2026-2027 kuzgi semestr; transkript bilan bir xil).

**GPA (5 ballik, kredit bilan tortilgan).** `GPA = Σ(kredit × baho) / Σ kredit`. Baho — institut shkalasi bo'yicha:
65–100 → «5» (A), 60–64 → «4» (B), 50–59 → «4» (C), 45–49 → «3» (D), 40–44 → «3» (E), 0–39 → «2» (F). Natija 2 xonagacha,
aniq «yarimdan yuqoriga» yaxlitlanadi (`academic_rules.ratio2`): butun sonlardan hisoblangani uchun SQL kesh, talaba kartasi va
transkript bir xil raqam ko'rsatadi (4.625 → 4.63).

**Kredit manbai.** Bazada fan krediti alohida ustunda yo'q. Mavjud yagona manba — «O'quv dasturlari» modulidagi `syl_items.credits`
(72 fandan 36 tasi uchun: iqtisodiy fanlar 6, til va gumanitar fanlar 4 kredit). Fan o'quv dasturida bo'lsa — o'sha kredit
(bir nechta kafedra dasturi bo'lsa — eng ko'p uchragan qiymat), bo'lmasa **standart 6 kredit** (`academic_rules.CREDIT_DEFAULT`;
taqdimotdagi GPA misolida ham fan 6 kredit). Talaba kartasida standart kredit «*» bilan belgilanadi. Transkript (Hujjatlar markazi)
ham endi xuddi shu manbadan oladi — reyting va transkript GPA bir xil.

**`students.gpa` haqida.** `students.gpa` va `students.gpa_prev` — 100 ballik o'rtacha ball (HEMIS'dan olingan surat; boshqa
modullarda «o'rtacha ball» sifatida ishlatiladi), 5 ballik GPA emas va baholar jadvali bilan aynan mos kelmaydi (demo ma'lumotda baholar
shu qiymat atrofida tasodifiy chiqarilgan). **Reyting bu ustunlardan foydalanmaydi** — har doim baholardan qayta hisoblaydi.

**Tartib (teng kelganda).** 1) semestr GPA (2 xona) ↓; 2) o'rtacha ball (100 ballik, fanlar bo'yicha oddiy o'rtacha, 2 xona) ↓;
3) davomat, % ↓ (qayd etilmagan — masofaviy ta'lim — oxirida). Hammasi ko'rsatilgan (yaxlitlangan) qiymatlar bo'yicha — foydalanuvchi
ko'rgan raqamlardan tartibni tekshira oladi. Barcha mezonlari to'liq teng talabalar bir xil o'rinni oladi, keyingisi o'tkazib
yuboriladi (`RANK()`: 1, 2, 2, 4). O'tgan semestr davomati bazada saqlanmagan — o'tgan semestr reytingida faqat GPA va o'rtacha ball.

**Darajalar.** Guruh; kurs (daraja + kurs, butun institut — bakalavr va magistr alohida); yo'nalish (daraja + yo'nalish, barcha
kurslar); fakultet; institut. Foiz — «yuqoridan necha foiz ichida» = o'rin / jami × 100, yuqoriga yaxlitlanadi.

**Kim reytingda.** Faqat `status='faol'` talabalar (akademik ta'tildagilar kartasida baholari ko'rinadi, o'rni yo'q). Kamida bitta
«F» (40 balldan past) bo'lgan talaba reytingda qoladi va **«akademik qarzdor»** deb belgilanadi. **A'lochi** — semestrdagi barcha
fanlardan kamida 65 ball («5»).

**A'lochilar ro'yxati.** Kurs (daraja + kurs) reytingida o'rni ≤ ⌈N% × kursdagi talabalar⌉, «F» soni ≤ chegara, davomat ≥ chegara
(masofaviy talabaga davomat sharti qo'llanmaydi; o'tgan semestr uchun davomat sharti qo'llanmaydi). Ro'yxat foydalanuvchi ko'lamida.

**Bo'linmalar.** Guruh — guruh talabalarining baholari; kafedra — kafedra o'qituvchilari qo'ygan baholar (shuning uchun guruhi
yo'q «Fundamental iqtisodiy fanlar» kafedrasi ham reytingda); o'qituvchi — o'zi qo'ygan baholar. Tartib: o'tish foizi (≥ 40) ↓,
o'rtacha ball ↓. Minimal namuna: guruh ≥ 10 talaba, kafedra ≥ 150 baho, o'qituvchi ≥ 30 baho — kichiklari «kam namuna» bilan
alohida ko'rsatiladi va o'rin olmaydi. O'rin har doim butun institut bo'yicha.

**Oraliq / yakuniy.** Bazada faqat yakuniy ball saqlanadi; qaydnoma va kartadagi ajratma `academic_rules.split_score` bilan
deterministik (yakuniy nazorat qaydnomasi bilan bir xil kalit — HEMIS ID va fan).

## Kesh va tezlik

- `rating_cache` — har talaba × semestr uchun GPA, o'rtacha ball, kreditlar, «F», besh darajadagi o'rin va jami. Bitta SQL so'rov
  (`RANK() OVER (PARTITION BY …)`) bilan ~1 soniyada quriladi (29 ming talaba × 2 semestr). `rating_credits` — fan krediti va manbasi,
  `rating_meta` — barmoq izi, vaqt, sabab.
- Server ishga tushganda kesh yo'q bo'lsa yoki manba (baholar, talaba holati/guruhi/davomati, guruh kursi, o'quv dasturi kreditlari,
  shuningdek kesh formulasi versiyasi va baholash qoidalari) o'zgargan bo'lsa — avtomatik qayta quriladi. Ish paytida 30 soniyada bir marta
  tekshiriladi (masalan, otrabotka bahosi tasdiqlansa). **Qayta seed shart emas**, `SEED_VERSION` o'zgarmaydi.
- Qo'lda: «Qayta hisoblash» tugmasi (`POST /api/reyting/recompute`) — Registrator ofisi (boshliq va xodim) va Akademik bo'lim.
- Qo'shimcha indekslar: `grades(student_id, semester)`, `grades(teacher_id)`.

## Ruxsatlar (serverda tekshiriladi, audit — resurs `rating`)

| Lavozim | Ko'radi |
|---|---|
| Registrator ofisi (boshliq #17, xodim #43), Akademik bo'lim (#18), Rektor (#2), O'quv prorektori (#3), Imtihon bo'limi, Ma'lumotlar bazasi bo'limi | Butun institut, barcha bo'limlar |
| Sirtqi bo'lim (#27) | Faqat sirtqi ta'lim talabalari (`study_form='sirtqi'`) |
| Kafedra mudiri (masalan, #31) | O'z kafedrasi guruhlari; bo'linmalar — o'z kafedrasi va uning o'qituvchilari |
| Tyutor | O'z fakulteti |
| O'qituvchi (#15) | Faqat o'zi baho qo'ygan talabalar; o'qituvchilar reytingida — faqat o'zi |
| Kuzatuv kengashi (#1), ilmiy / moliya / yoshlar prorektorlari, Sifatni ta'minlash boshqarmasi | Faqat jamlangan: taqsimot, o'rtacha qiymatlar, guruhlar dinamikasi. Ism-sharif va HEMIS ID umuman yuborilmaydi; ro'yxat, karta, qaydnoma, a'lochilar, o'qituvchilar — 403 |
| Qolganlar (masalan, Buxgalteriya #11) | 403; menyuda ko'rinmaydi |

Har bir murojaat (ruxsat etilgan va rad etilgan) audit jurnaliga yoziladi: `reyting: …` amallari, resurs `rating`.

## API

`GET /api/reyting/meta` · `overview?sem=` · `list?sem&level&faculty&course&group&form&flag&q&sort&dir&page&per` · `student/{id}` ·
`qaydnoma/{guruh}?sem=` · `qaydnoma/{guruh}/export?sem&fmt=xlsx|docx` · `dynamics?level&limit` · `top?sem&pct&min_att&max_f` ·
`top/export` · `units?kind=group|kafedra|teacher&sem` · `methodology` · `POST /api/reyting/recompute`.

## Cheklovlar (demo)

- Bazada ikki semestr bor — trend ikki nuqtadan iborat.
- Kredit 36 fan uchun o'quv dasturidan, qolganlari standart 6; institut fanlar katalogi (kreditlari bilan) olinganda `syl_items` yoki
  alohida jadval orqali almashtiriladi — kesh o'zi qayta quriladi.
- Talabalar markazidagi xavf qoidasi (`student_ops`, «JPA») avvalgidek kreditsiz o'rtacha 5 ballik bahodan foydalanadi — u reyting emas,
  ogohlantirish mezoni.
