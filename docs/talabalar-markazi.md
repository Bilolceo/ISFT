# Talabalar bilan ishlash markazi — dizayn hujjati (v0.3, 2026-11-10)

Manba: Samarqand tajribasi asosidagi og'zaki talablar (ovozli xabar xulosasi). Bu hujjat — qurilgan narsaning chegarasi,
qoidalari va ochiq savollari. **Qoidalardagi raqamlar institut tomonidan tasdiqlanmagan** — tizimda "tasdiqlanmagan" belgisi bilan ko'rinadi.

## Maqsad
Registrator ofisi (sirtqi talabalar uchun — Sirtqi bo'lim), tyutorlar va call-markaz uchun yagona ish navbati: tizim talabalar holatini har kuni o'zi tekshiradi,
muammo topsa — mas'ulga aniq topshiriq (kimga, nima, qachongacha, nima deyish) beradi va natijani kuzatadi.
Qaror va imzo — har doim odamda.

## Doira
| Faza | Tarkib | Holat |
|---|---|---|
| 1 | Xavf registri (kontrakt, davomat, akademik, kasallik/komandirovka hujjati, akademik ta'til muddati), call-markaz navbati, va'da → qayta qo'ng'iroq, ogohlantirish zinapoyasi, ogohlantirish xati / hayfsan loyihasi | ✅ qurildi |
| 2 | Otrabotka: varaqa (QR, ro'yxat raqami) → muddat → yuklash → baho yonma-yon → tasdiqlash → natija baholar tarixiga yoziladi | ✅ qurildi |
| 2b | Akademik model (v0.2): ko'p semestrli tarix, o'quv rejasi kreditlari, joriy semestrda faqat oraliq nazorat, baholar tarixi, hayfsan yozuvi, tyutor ↔ guruh | ✅ qurildi |
| 3 | Arizadan buyruq loyihasi, Excel ro'yxat versiyalari (kim/nima o'zgardi), shaxsiy grafik QR | keyingi |
| 4 | Muammoli talabalar: ikki marta buyruqda, eski guruhda qolgan, hech bir buyruqda yo'q (HEMIS/buyruqlar bazasi kerak) | keyingi |

## Tamoyillar
1. **Deterministik qoidalar.** Signal va topshiriqlar kod bilan hisoblanadi (SQL + Python), AI emas. Har bir topshiriqda "nega" (fakt) ko'rinadi.
2. **Idempotentlik.** Bitta talaba + bitta qoida = bitta ochiq holat (`ops_cases.key` UNIQUE). Dvigatel necha marta ishlasa ham dublikat yo'q.
   Daraja oshsa — yangi topshiriq; shart yo'qolsa (masalan, to'lov qilindi) — holat avtomatik yopiladi va sababi yoziladi.
3. **Me'yoriy havolalar o'ylab topilmaydi.** Suhbat skriptidagi huquqiy asos faqat institut kiritgan ro'yxatdan; bo'sh bo'lsa — "kiritilmagan" deb ko'rsatiladi.
4. **OCR/imzo tekshiruvi va'da qilinmaydi.** Otrabotka varaqasi tizimda QR bilan chiqariladi; yuklangan skan yonida baho qo'lda kiritiladi va tasdiqlanadi.
   Skan o'qiladi (`app/registrar_scan.py`): PDF matn qatlami yoki tesseract OCR (bo'lsa) — ro'yxat raqami, imzo bor/yo'q, ball; OCR bo'lmasa ball qo'lda kiritiladi.
5. **Shaxsiy ma'lumot minimal.** Rektor — faqat jamlangan raqamlar; call-markaz — faqat o'z navbatidagi talaba, telefon va skript; tyutor — faqat o'ziga biriktirilgan guruhlar (`tutor_groups`; dekan lavozimi yo'q; fakultet darajasidagi ko'rinish — Registrator ofisida).
6. **"Tizim o'zi o'rganadi" emas.** Yaxshilanish — qoidalar va shablonlarni foydalanuvchi fikri asosida sozlash orqali.

## Akademik model (yagona manba — `app/academic_rules.py`)
- **Semestrlar.** `grades.semester` — o'quv davri kodi: `1` — joriy (2026-2027 kuzgi), `0` — 2025-2026 bahorgi, … `-5` — 2023-2024 kuzgi.
  Dastur semestri `sem_no = 2·kurs − 2 + kod`: 1-kursda o'tgan semestr yo'q, 4-kursda 6 ta yakunlangan + joriy 7-semestr.
  Guruh kodi qabul yilidan: 1-kurs `IQT-2601`, 4-kurs `IQT-2301` (ma'lumotnomadagi o'qish muddati bilan bir xil).
- **Joriy semestr** (noyabr): faqat oraliq (joriy) nazorat bali `grades.oraliq` (0–30); yakuniy nazorat — qishki sessiyada, `score` hozircha bo'sh.
  **Yakunlangan semestrlar:** `oraliq` + `yakuniy` = `score` (oraliq < 12 bo'lsa yakuniyga kiritilmagan, `yakuniy` bo'sh, `score` = oraliq).
- **O'quv rejasi** (`curriculum`): har yo'nalish × daraja × semestr uchun turli fanlar va kreditlar; har semestr 30 kredit (bakalavr 240, magistr 120).
  Kredit baho qatorida ham (`grades.credits`) — reyting, transkript, GPA shu qiymatni oladi.
- **Baholar tarixi** (`grade_attempts`): asl urinish + qayta topshirish / otrabotka urinishlari, `counted` — qaysi biri hisobda. `grades` — hisobdagi natija.
  Hisobdagi natija — eng yuqorisi: past natija bahoni **pasaytirmaydi** (urinish tarixda qoladi).
- **Akademik ta'til**: ta'til davri bilan kesishgan semestrlarda baho, davomat va dars qoldirish yo'q.
- **Yagona ta'riflar** (panel, Talabalar markazi, Reyting, hujjatlar bir xil son ko'rsatadi):
  - *O'rtacha ball (100)* — oxirgi yakunlangan semestr fanlari bo'yicha 100 ballik ballar o'rtachasi; `students.gpa` / `gpa_prev` — shu qiymat
    (oxirgi va undan oldingi semestr), baholardan hisoblanadi (`refresh_student_metrics`), otrabotka tasdiqlansa yangilanadi.
  - *GPA (5)* — Σ(kredit × 5 ballik baho) / Σ kredit; semestr va kumulyativ.
  - *Akademik qarzdor* — yakunlangan semestr(lar)dan kamida bitta fani o'zlashtirilmagan (hisobdagi ball < 40) faol talaba.
  - *O'qishda xavf* — o'zlashtirish yoki davomat bo'yicha holati «kritik»/«jiddiy» faol talaba (TALABALAR soni). Holatlar (`by_rule`) — boshqa birlik
    («holat»): bitta talabada bir nechta holat bo'lishi mumkin; call-markaz xulosasida — o'z navbatidagi holatlar.
- **«O'zlashtirish» qoidasi** (`akademik_level`): 1 — diqqat (1 ta qarz yoki 1 fandan oraliq < 12, topshiriqsiz); 2 — kritik (≥2 qarz, kumulyativ GPA < 3.0,
  ≥2 fandan past oraliq yoki qarz + past oraliq — tyutor suhbati); 3 — jiddiy (≥4 qarz — suhbat + ogohlantirish xati).

## Qoidalar (davomat va o'tish bali — institut me'yori; qolganlari TASDIQLANMAGAN)
| Kalit | Qiymat | Ma'nosi |
|---|---|---|
| `contract_critical_days` | 3 | Navbatdagi to'lov muddatiga ≤3 kun qolgan va yetarli to'lanmagan → kritik |
| `att_call_hours` | 30 | Sababsiz qoldirilgan soat ≥30 → call-markaz qo'ng'irog'i — institut me'yori (rektor qarori), tasdiqlangan |
| `att_letter_hours` | 30 | ≥30 → ogohlantirish xati (registrator; sirtqi talabaga — Sirtqi bo'lim) — tasdiqlangan |
| `att_reprimand_hours` | 48 | 48 dan OSHSA (49+) → hayfsan taqdimnomasi (rektor imzolaydi — hayfsan qayd etiladi) + tyutor suhbati — tasdiqlangan |
| `att_expel_hours` | 72 | Hayfsan **e'lon qilingan** (`discipline.status='amalda'`) va ≥72 → «chetlashtirishga tayyor» ro'yxati (ish stoli) |
| `contract_expel_days` | 30 | Kontrakt muddatidan 30+ kun o'tgan va qarzdorlik xati yuborilgan → «chetlashtirishga tayyor» |
| `hours_to_date` | 180 | Kunduzgi: joriy semestr boshidan o'tilgan auditoriya soatlari (davomat foizi shundan) |
| `session_hours` | 96 | Sirtqi: joriy semestr o'quv sessiyasi soatlari (2026-10-12 — 10-31); davomat foizi shundan |
| `sirtqi_att_*_hours` | 16 / 26 / 38 | Sirtqi: qo'ng'iroq + xat / hayfsan / chetlashtirish — kunduzgi 30/48/72 (180 soatdan) me'yoriga mutanosib |
| `permit_att_hours` | 48 | Imtihonga ruxsatnoma: sababsiz soatlar shu chegaradan oshmasin |
| `pass_score` | 40 | Fan bo'yicha o'tish bali (100 ballik, «3») — institut qoidasi (akademik qoidalar taqdimoti), tasdiqlangan |
| `gpa_min` | 3.0 | Kumulyativ GPA (5) minimal |
| `fails_warn` | 2 | Shuncha akademik qarz (yoki past oraliq) bo'lsa — GPA yetarli bo'lsa ham kritik |
| `medical_doc_days` | 3 | Kasallikdan keyin hujjat topshirish muddati (kun) |
| `leave_warn_days` | 90 | Akademik ta'til tugashiga ~3 oy qolganda call-markaz qo'ng'irog'i (≤7 kun — qaytish buyrug'i loyihasi) |
| `retake_days` | 3 | Otrabotka varaqasini qaytarish muddati (kun) |
| `call_max_attempts` | 3 | Javob bermasa — shuncha urinishdan keyin tyutorga o'tadi |
| `call_daily_capacity` | 60 | Operatorning standart kunlik me'yori; har operator uchun alohida — `call_operators` (Registrator ofisi boshlig'i sozlaydi) |
| `tutor_call_capacity` | 10 | Navbat to'lganda bitta tyutorga bir kunda o'tkaziladigan qo'ng'iroqlar |
| `staff_call_capacity` | 40 | Navbat to'lganda Registrator ofisi xodimiga bir kunda o'tkaziladigan qo'ng'iroqlar |

Davomat chegaralari — faqat **joriy semestr** dars qoldirishlari (`absences.semester`); o'tgan semestr soatlari qo'shilmaydi.
Sababli dars qoldirish zinapoyaga qo'shilmaydi: kunduzgi ta'limda — kasallik va oilaviy sabab (hujjat bilan); **xizmat safari va mehnat ta'tili —
faqat sirtqi talabalar uchun** (kunduzgi talabada bu sabab sababsiz hisoblanadi). Hujjati yo'q bo'lsa — alohida "hujjat so'rash" topshirig'i.
Otrabotka bilan qayta ishlangan dars (`absences.cleared_by`) sababsiz soatlardan chiqadi.

Kontrakt to'lov jadvali — 2026-2027 o'quv yili uchun qat'iy sanalar (TAXMIN): 01.10.2026 — 25%, 12.11.2026 — 50%, 15.02.2027 — 75%, 01.05.2027 — 100%.
Qarzdorlik xati: kunduzgi bakalavr — ota-onaga; sirtqi, masofaviy va magistratura talabasi (ishlaydigan, katta yoshli) — talabaning o'ziga.

## Otrabotka turlari
| Tur | Qachon | Tasdiqlansa |
|---|---|---|
| `qarz` | Yakunlangan semestrdagi o'zlashtirilmagan fan (har qanday semestr) | O'sha semestr yozuvi (`score`) yangilanadi — yuqorisi hisobda; tarixga yoziladi |
| `oraliq` | Joriy semestrda oraliq < 12 (yoki kiritilmagan) | Joriy `oraliq` yangilanadi (0–30) — yuqorisi hisobda |
| `dars` | Joriy semestrda sababsiz qoldirilgan mashg'ulot | Dars qoldirish yopiladi (`cleared_by`), baho o'zgarmaydi |

Imtihonga ruxsatnoma (qishki sessiya): faol maqom, ochiq otrabotka yo'q, yakunlangan semestrlardan qarz yo'q, joriy oraliq ≥ 12 (tanlangan fan yoki
barcha fanlar), joriy semestrdagi sababsiz soatlar ≤ 48 (sirtqi — 26), kontrakt jadval bo'yicha yoki muddat uzaytirilgan.

## Call-markaz navbati (v0.3)
- **Muddat va reja alohida.** `ops_tasks.due_at` — HAQIQIY muddat (SLA): davomat 30+ soat — 24 soat; kontrakt eslatmasi (to'lov sanasi hali
  o'tmagan) — sanadan oldingi ish kuni 18:00; muddati o'tgan kontrakt — 48 soat (TAXMIN); ta'til tugashi — 5 kun (TAXMIN); otrabotka — 4/8 soat;
  va'da o'tgani — 8 soat. `planned_on` — rejalashtirilgan kun, `assignee_user` — operator. Rejalashtiruvchi (`schedule_calls`) due_at'ga tegmaydi.
- **Tartib:** muddat kuni (o'tganlari — bugun) → jiddiylik → aniq muddat. Har ish kuniga faol operatorlar me'yorlari yig'indisidan ortiq qo'yilmaydi;
  bugun qilingan qo'ng'iroqlar bugungi imkoniyatdan ayriladi; «javob bermadi» bilan ertaga qoldirilgani oldinga surilmaydi.
- **Ochiq hisob** (`calls_summary.text`): «Bugun 60 ta imkoniyat, muddati ichida qilinishi kerak 993 ta — 933 tasi kechikadi» (muddati keyingi ish
  kuni 09:00 gacha tugaydiganlar); «kechikkan» — faqat muddati o'tganlar; «rejaga ko'ra kechikadi» — rejalashtirilgan kun muddatdan keyin.
- **Muqobil yo'llar** (Registrator ofisi boshlig'i, «Call-markaz navbati» tabi): (1) to'lov sanasigacha bo'lgan kontrakt eslatmalari — ommaviy
  SMS/Telegram (`ops_notices`, shlyuz ulanmagan — chiqish navbati; holat ochiq qoladi, sana o'tsa qo'ng'iroq qaytadi); (2) kechikadigan
  qo'ng'iroqlarni bir bosishda tyutorlarga (kunduzgi — guruh tyutori, sirtqi — Sirtqi bo'lim) yoki Registrator ofisi xodimiga o'tkazish (kunlik
  me'yor bilan, muddat o'zgarmaydi, skript yangi so'zlovchi nomidan qayta tuziladi); (3) operatorlar va me'yorlar.
- **Skript so'zlovchisi** (`script(..., role)`): call-markaz / tyutor / Registrator ofisi / Sirtqi bo'lim nomidan; uchrashuv — kunduzgi talabada guruh
  tyutori, sirtqida Sirtqi bo'lim, masofaviyda Registrator ofisi; sabablar va hujjat qayerga topshirilishi ta'lim shakliga qarab.

## Ommaviy amallar
- **Xatlar:** `POST /api/ops/bulk/preview` → `POST /api/ops/bulk/run` (`kind=xat`, filtrlar: qoida, guruh, kurs). Shablon bo'yicha bitta birlashtirilgan
  DOCX (har sahifa hujjatlar reyestrida o'z raqami va QR bilan), ikki shablon bo'lsa — ZIP (`/api/ops/bulk/{id}/zip`, `ops_batches`).
- **Buyruq loyihalari:** `kind=buyruq` — har tur bo'yicha BITTA buyruq talabalar ro'yxati bilan (`orders.create_order`): hayfsan, ta'tildan qaytish.
- **Belgilash:** `POST /api/ops/tasks/bulk-outcome` — tanlanganlar natija izohi bilan bajarildi (qo'ng'iroq — gaplashildi; hujjat so'rash — alohida).
- **Filtrlar:** `/api/ops/tasks?rule=&kind=&grp=&course=&late=&role=`, hisoblagichlar — `/api/ops/tasks/facets`.
- **«Mening navbatim»:** Registrator ofisi — o'z ofisi ishlari (boshqalar — «Mas'ul» filtri); xodim — call-markaz qo'ng'iroqlari va buyruq loyihalarisiz;
  Sirtqi bo'lim — o'z topshiriqlari; operator — o'ziga taqsimlanganlar. Qoida kartalari — faqat lavozim ishlaydigan qoidalar.

## Hayfsan (intizomiy chora)
Davomat 48 soatdan oshsa (sirtqi — 26) «buyruq» topshirig'i → «Buyruqlar» modulida «Hayfsan» buyrug'i loyihasi (bitta yoki ommaviy — bitta buyruq,
talabalar ro'yxati bilan) → `discipline` yozuvi «loyiha» (`doc_reg = BUYRUQ#id`); rektor buyruqni imzolasa — «amalda», o'chirilsa/bekor qilinsa —
«bekor» (`sync_discipline`, dvigatel va xulosa so'rovida). Eski `reprimand` taqdimnomalari (HB-…) uchun `discipline_on_doc` ishlashda davom etadi.
Ma'lumot boshqa modullarga ochiq: `GET /api/registrar/discipline?student_id=&status=`.

## Rollar
| Rol | Ko'radi | Qiladi |
|---|---|---|
| Registrator ofisi (Akademik faoliyatni boshqarish bo'limi — ko'rish) | Barcha holatlar | Xat/hayfsan loyihasi, otrabotka tasdiqlash, topshiriqni qayta yo'naltirish |
| Call-markaz operatori | O'z navbatidagi qo'ng'iroqlar | Natija: gaplashildi / va'da (sana) / javob bermadi / noto'g'ri raqam |
| Tyutor | O'ziga biriktirilgan ~10 kunduzgi guruh (`tutor_groups`) | Suhbat, hujjat so'rash, otrabotka varaqasi berish |
| Sirtqi bo'lim | Sirtqi talabalar | Registrator ishlari + sirtqi talabalarning tyutor ishlari (masofaviy — Registrator ofisida) |
| O'quv ishlari bo'yicha prorektor | Barchasi (o'qish) | — |
| Rektor | Faqat jamlangan raqamlar | — |

## Ochiq savollar (institutga)
1. Davomat chegaralari: "50%" va "30 soat" nimani anglatadi; har bosqichning rasmiy chegarasi va asos hujjati.
2. JPA shkalasi (5 yoki 4 ballik), kreditlar, ogohlantirish qoidasi.
3. Kontrakt to'lov jadvali (bo'lib to'lash sanalari va foizlari).
4. Call-markaz bormi yoki bu vazifani tyutorlar bajaradimi.
5. Buyruq/xat shablonlari va tayaniladigan me'yoriy hujjatlar ro'yxati.
6. ~~Komandirovka/mehnat ta'tili — sirtqi talabalar uchunmi~~ — ha, faqat sirtqi (v0.2 da cheklandi).
7. Sirtqi davomat chegaralari (hozir kunduzgi me'yorga mutanosib 16/26/38 soat) va sessiya jadvali.
8. Tyutor me'yori (hozir ~10 guruhga bitta) va haqiqiy biriktirma.

## Amalga oshirish
- Kod: `app/academic_rules.py` (taqvim, ta'riflar, darajalar), `app/student_ops.py` (sxema, dvigatel, otrabotka, tyutorlar, API `/api/ops/*`),
  `app/registrar.py` (ish stoli, ruxsatnoma, intizom), shablonlar `app/documents.py` (`warn_letter`, `reprimand`, `retake_sheet`), UI `static/app.js` (`renderOps`), `static/registrar.js`.
- Tyutor akkauntlari server ishga tushishining oxirida yaratiladi (`reyting.init` → `student_ops.ensure_tutors`) — boshqa demo akkauntlar id'si o'zgarmaydi.
- Dvigatel: server ishga tushganda va har 10 daqiqada (`poller`), har natija kiritilganda; qo'lda — "Hozir tekshirish".
- Agent «Nega?» (`app/agent.py` `academic_drivers`): fanlar har semestrda boshqa — solishtirish guruh (pasaygan ↔ qolgan), kurs, fakultet va fan turi
  (umumta'lim, til, yo'nalish tayanch, mutaxassislik, umumkasbiy) kesimida: o'rtacha ball va o'tish ulushi, ikki oxirgi yakunlangan semestr; faktlar
  manba ma'lumotiga qo'shiladi (raqamlar tekshiruvi).
- Testlar: `tests/test_talabalar_markazi.py` — navbat v2 (SLA, rejalashtirish, operatorlar, SMS, taqsimlash, ko'lam, filtrlar, ommaviy xat/buyruq,
  skript so'zlovchisi, agent), ruxsatlar, idempotentlik, va'da → qayta qo'ng'iroq, 3 urinish → tyutor, hujjat → holat yopilishi,
  to'lov → holat yopilishi, xat/hayfsan hujjatlari, hayfsan yozuvi, otrabotka (qarz/oraliq/dars, baholar tarixi, pasaytirmaslik), tyutor ko'lami,
  semestr chegaralari, akademik ta'til, sirtqi davomat.
- Demo akkauntlar (parol Isft2026): call-markaz operatori (23), tyutorlar (24–26 va 44+, jami ~37; 24 — Xalqaro iqtisodiyot va moliya 2-kurs guruhlari); registrator — "Registrator ofisi" (17); "Akademik faoliyatni boshqarish bo'limi" (18) — ko'rish.
