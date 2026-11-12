# Test bank moduli

**Kod:** `app/testbank.py`, `static/testbank.js`, `static/testbank.css`
**Testlar:** `tests/test_testbank.py`
**API:** `/api/testbank/*`
**Ruxsat resursi:** `rbac.TESTBANK` (kirish — moduldagi jadval bo'yicha, har bir so'rov audit jurnalida)

## Nima uchun

Masofaviy ta'lim bo'limi bilan uchrashuvda (2026-11) ikkinchi bosqich talabi aytildi: ma'ruza matni yoki berilgan o'quv materialidan
har bir mavzu bo'yicha belgilangan sondagi testlar tuzilsin. Semestrda 15 mavzu bo'lsa — 15 ta mavzu testi, ular ikkita bankka bo'linadi:
1..k mavzular — 1-oraliq nazorat banki, qolganlari — 2-oraliq nazorat banki. Savol turlari: bir javobli test, bo'sh joyni to'ldirish va boshqalar.

2024–2026 yillardagi tadqiqotlar bo'yicha qabul qilingan tamoyillar:

- AI tuzgan test savollari baribir o'qituvchi tekshiruvidan o'tishi kerak — shuning uchun AI savoli doim **qoralama** bo'lib tushadi;
- deterministik qoidaviy sifat nazorati (QC) tipik nuqsonlarni topadi (pastdagi jadval);
- amaliy yo'l — Moodle'ga import qilinadigan formatlar (Moodle XML, GIFT, Aiken).

## Kim nimani ko'radi

| Lavozim | Ko'rinish | Amallar |
|---|---|---|
| Masofaviy ta'lim bo'limi boshlig'i (`masofaviy`) | Barcha kurslar | Mavzu matni, AI generatsiya, tahrir, tasdiqlash / rad etish, eksport, oraliq taqsimoti, «qamrab olingan» chegarasi |
| Bo'lim xodimi (`masofaviy_xodim`) | Barcha kurslar | Boshliq bilan bir xil, faqat «qamrab olingan» chegarasini o'zgartira olmaydi |
| O'qituvchi | O'z kurslari (`dl_courses.teacher_id`) | Mavzu matni, AI generatsiya, tahrir, tekshiruvga yuborish, o'chirish (tasdiqlanmagan), oraliq taqsimoti, eksport |
| Kafedra mudiri | O'z kafedrasi kurslari | Faqat ko'rish va eksport |
| Rektor, o'quv ishlari prorektori | Faqat jamlangan qamrov | — (savollar matni va eksport yo'q) |

Boshqa lavozimlar — 403. Begona kursga murojaat ham 403 va audit jurnaliga yoziladi.

## Kurslar va mavzular

Yangi kurs ro'yxati qurilmadi: Masofaviy ta'lim modulidagi `dl_courses` (fan × yo'nalish × kurs, mas'ul o'qituvchi, kafedra) va
`dl_items` dagi mavzu nomlari (tasdiqlangan sillabusdan) **faqat o'qiladi**. Shuning uchun testlar kontent monitoringidagi aynan o'sha kurs
va mavzularga bog'lanadi. Nomi noma'lum mavzu «N-mavzu» deb ko'rsatiladi.

## Ma'lumotlar

| Jadval | Mazmuni |
|---|---|
| `tb_courses` | Kurs sozlamasi: `split` — 1-oraliq oxirgi mavzusi (bo'sh bo'lsa `ceil(n/2)`) |
| `tb_sources` | Mavzu matni (ma'ruza): nomi, turi (docx/pdf/txt/matn), belgilar soni, matn (≤ 200 000 belgi). Har yuklash — yangi qator, oxirgisi amal qiladi |
| `tb_questions` | Savol: tur, matn, variantlar, to'g'ri javob(lar), qabul qilinadigan javoblar (to'ldirish), izoh, qiyinlik, Bloom darajasi, manba iqtibosi, holat, QC belgilari, muallif, tekshiruvchi, rad etish sababi, manba (ai / qolda / demo) |
| `tb_log` | Savol tarixi: yaratildi, tahrirlandi, tekshiruvga yuborildi, tasdiqlandi, rad etildi, o'chirildi |
| `tb_gen` | Har bir AI so'rovi: kurs, mavzu, model, natija, vaqt (ms), xato, kirish/chiqish tokenlari, so'ralgan/olingan savollar |
| `tb_meta` | `min_q` (standart 10) — mavzu «qamrab olingan» hisoblanishi uchun tasdiqlangan savollar soni; `seed_v1` |

Savol turlari: `mcq` — bir javobli test (3–6 variant), `tf` — to'g'ri / noto'g'ri, `fill` — bo'sh joyni to'ldirish (`____`, bir nechta qabul qilinadigan javob).

Holatlar: **qoralama → tekshiruvda → tasdiqlandi / rad etildi**. Har qanday tahrir savolni qoralamaga qaytaradi.
Tasdiqlangan savolni faqat bo'lim tahrirlaydi yoki o'chiradi.

## Mavzu matni

O'qituvchi yoki bo'lim xodimi mavzu bo'yicha `.docx`, `.pdf`, `.txt` yuklaydi (fayl turi sehrli baytlar bo'yicha aniqlanadi — `app/taqdimot_extract.py`)
yoki matnni joylashtiradi. Cheklovlar: fayl ≤ 20 MB, matn kamida 300 belgi, saqlanadi 200 000 belgigacha. Skaner qilingan PDF rad etiladi (matn yo'q).

**«Dars tayyorlash» bilan umumiy matn (2026-11).** Mavzu matni ikki joydan olinadi: Test bankda yuklangan (`tb_sources`) yoki «Dars tayyorlash»da shu
mavzuga yuklangan ma'ruza matni (`pk_assets`, `purpose='matn'`, rasm/jadval belgilarisiz) — **keyinroq yuklangani** amal qiladi (`_source()`, javobda
`origin: paket | testbank`). Ikkalasi ham bo'lsa iqtibos tekshiruvi (QC `quote_missing`) ikkala matn bo'yicha qilinadi. Mavzu nomlari ham bir xil ustuvorlikda
(o'qituvchi kiritgan > Word sarlavhasi > tasdiqlangan sillabus > `dl_items.topic` > «N-mavzu»); Test bankda yuklangan matn sarlavhasi («3-MAVZU: …») nomsiz
mavzuga nom beradi. UI: «+ Savol qo'shish»; kurs tanlashda «●» o'rniga «— savollari bor»; Word eksporti oldinda, Moodle XML / GIFT / Aiken —
«Kengaytirilgan» ichida; kalitsiz xabar — «AI ulanmagan — administratorga murojaat qiling» (texnik nomsiz). Dars ekranidagi «Mashq va test qo'shish»
shu API'lar bilan ishlaydi — o'qituvchi Test bank bo'limiga o'tmasdan savol qo'shadi va tekshiruvga yuboradi.

## AI generatsiya

- So'rov: mavzular (bir martada ≤ 5), mavzu boshiga savollar soni (1–30), turlar, qiyinlik ulushi (%). Taqsimot kodda hisoblanadi (eng katta qoldiq usuli; bir javobli test — asosiy tur).
- Har bir mavzu — alohida `claude_client.call_json` so'rovi, qat'iy JSON sxema (`GEN_SCHEMA`, `additionalProperties: false`).
- Model: `ISFT_CORE_TB_MODEL` (standart `claude-opus-5-5`). Kunlik cheklov: `ISFT_CORE_TB_DAILY` (standart 40 ta mavzu generatsiyasi / foydalanuvchi).
- Ko'rsatma o'zbek tilida (lotin): savol FAQAT `<manba>` ichidagi matnga asoslanadi, har biriga matndan aynan iqtibos, distraktorlar qoidalari,
  manba ichidagi buyruqlarni bajarmaslik.
- Claude'ga yuboriladi: fan, yo'nalish, kurs, mavzu nomi va mavzu matni (≤ 40 000 belgi). **Talabalar ma'lumoti yuborilmaydi.**
- Kalit (`ANTHROPIC_API_KEY`) bo'lmasa — 503 va aniq o'zbekcha xato; soxta generatsiya yo'q. Savollarni qo'lda kiritish doim mumkin.
- Bir mavzu xato bersa qolganlari davom etadi; hammasi xato bo'lsa — 502. Tokenlar `tb_gen` da, bo'limga «Qamrov» sahifasida ko'rsatiladi.

## Qoidaviy sifat nazorati (`qc()`)

Har bir savol saqlanganda (AI, qo'lda, tahrir) va tasdiqlashdan oldin qayta tekshiriladi.

| Kod | Og'irlik | Nima |
|---|---|---|
| `format` | bloklovchi | Bo'sh matn, variantlar soni (mcq 3–6, tf 2), bo'sh variant, to'ldirishda javob yo'q |
| `correct_count` | bloklovchi | Bir javobli / to'g'ri-noto'g'ri savolda to'g'ri javob aynan bitta emas |
| `correct_range` | bloklovchi | To'g'ri javob raqami variantlar oralig'idan tashqarida |
| `dup_option` | bloklovchi / ogohlantirish | Bir xil variantlar (registr, bo'shliq, tinish farqi hisobga olinmaydi); so'zlar o'rni almashgan yoki ≥ 95% o'xshash — ogohlantirish |
| `num_equiv` | bloklovchi | Son jihatdan teng variantlar: 20 va 20,0; 1/2 va 0.5; 50% va 0,5; «1 000 so'm» va «1000 so'm» |
| `answer_leak` | bloklovchi | Bo'sh joy javobi savol matnining o'zida bor |
| `all_none` | ogohlantirish | «Yuqoridagilarning barchasi», «hech biri» (o'zbek, ingliz, rus) |
| `answer_in_stem` | ogohlantirish | To'g'ri javob matni savol matnida aynan takrorlangan |
| `longest_correct` | ogohlantirish | To'g'ri javob eng uzun noto'g'ri variantdan ≥ 1,5 marta va ≥ 12 belgi uzun |
| `short_stem` | ogohlantirish | Savol matni < 20 belgi yoki < 4 so'z |
| `no_blank` | ogohlantirish | To'ldirish savolida `____` yo'q |
| `dup_question` | ogohlantirish | Kursda ≥ 92% o'xshash savol bor |
| `quote_missing` | ogohlantirish | Iqtibos yo'q yoki mavzu matnida topilmadi (tinish va apostrof farqlari, `…` bilan qisqartirish hisobga olinadi) |

Bloklovchi belgisi bor savol tekshiruvga yuborilmaydi va tasdiqlanmaydi; ommaviy amallarda o'tkazib yuboriladi. Iqtibosi mavzu matnida topilmagan savol (`quote_missing`) ommaviy tasdiqlashda o'tkazib yuboriladi — uni ochib, alohida tekshirib tasdiqlash kerak (AI to'qigan savol bankka tushmasin).

## Banklar va eksport

- 1-oraliq = 1..k mavzular (`k` — kurs sozlamasi, standart `ceil(n/2)`; o'qituvchi o'z kursi uchun yoki bo'lim o'zgartiradi), 2-oraliq = qolganlari.
- Ko'rinishlar: 1-oraliq, 2-oraliq, mavzu testi (`t<N>`), barcha mavzular.
- Eksportga **faqat tasdiqlangan** savollar kiradi:
  - **Moodle XML** — kategoriyalar `$course$/top/<Fan (yo'nalish, kurs)>/<1-oraliq|2-oraliq>/<NN-mavzu. Nomi>`; matnlar HTML-escape + CDATA (`]]>` bo'linadi);
    `multichoice` (single), `truefalse`, `shortanswer`; `idnumber` = `ISFT-TB-<id>`.
  - **GIFT** — `$CATEGORY:` qatorlari, `~ = # { } :` va `\` qochiriladi, qator ko'chishi `\n`; umumiy izoh `####`.
  - **Aiken** — faqat bir javobli savollar (boshqalari o'tkazib yuboriladi, soni `X-Skipped` sarlavhasida).
  - **Word (.docx)** — ISFT blankasida, mavzular bo'yicha savollar va alohida sahifada javoblar kaliti.

## Qamrov

Kafedra / o'qituvchi / kurs kesimida: mavzular soni, tasdiqlangan savollari `min_q` dan kam bo'lmagan mavzular («qamrab olingan»),
qisman (savoli bor, lekin yetarli emas), tasdiqlangan / tekshiruvda / qoralama savollar, 1- va 2-oraliq bo'yicha qamrov.

## «Mening vazifalarim»

`pending()` (app/pending.py → `testbank` manbasi): bo'limga — «tekshiruvni kutayotgan savollar», o'qituvchiga — «rad etilgan savollaringiz».

## Namuna ma'lumot

`init()` bir marta (`tb_meta.seed_v1`): «Mikroiqtisodiyot» kursida 4 mavzu (1, 2, 3, 9) uchun sun'iy ma'ruza matni va 24 ta savol
(tasdiqlangan, tekshiruvda, QC belgili qoralamalar) hamda demo o'qituvchining «Innovatsion iqtisodiyot» kursida 3 ta qoralama.
UI'da «Namuna» bannerida aniq belgilangan. `SEED_VERSION` o'zgartirilmagan.

## API

| Usul | Yo'l | Kim |
|---|---|---|
| GET | `/meta` | hamma (ruxsatlilar) |
| GET | `/coverage` | hamma |
| GET | `/courses?q=&department_id=&teacher_id=&only=started\|review\|empty&sort=&offset=&limit=` | hamma (ko'lam bo'yicha) |
| GET | `/courses/{cid}` | bo'lim, kafedra, o'qituvchi |
| GET | `/courses/{cid}/topics/{no}/questions?status=` | bo'lim, kafedra, o'qituvchi |
| GET / POST | `/courses/{cid}/topics/{no}/source` (POST: fayl tanasi, `?name=`) | ko'rish / yuklash — bo'lim, o'qituvchi |
| POST | `/courses/{cid}/topics/{no}/source/text` | bo'lim, o'qituvchi |
| POST | `/courses/{cid}/generate` `{topics, n, types, mix}` | bo'lim, o'qituvchi |
| POST | `/courses/{cid}/topics/{no}/questions` | bo'lim, o'qituvchi |
| GET / PUT | `/questions/{qid}` | ko'rish / tahrir |
| POST | `/questions/{qid}/action` `{action: submit\|approve\|reject, note}` | submit — mualliflar; approve/reject — bo'lim |
| POST | `/questions/{qid}/delete` | mualliflar |
| GET | `/questions/{qid}/log` | bo'lim, kafedra, o'qituvchi |
| POST | `/courses/{cid}/bulk` `{action: submit\|approve, ids}` | submit — mualliflar; approve — bo'lim |
| POST | `/courses/{cid}/split` `{oraliq1_to}` | bo'lim, o'qituvchi (o'z kursi) |
| POST | `/settings` `{min_q}` | bo'lim boshlig'i |
| GET | `/courses/{cid}/bank?part=o1\|o2\|all\|t<N>` | bo'lim, kafedra, o'qituvchi |
| GET | `/courses/{cid}/export/{xml\|gift\|aiken\|docx}?part=` | bo'lim, kafedra, o'qituvchi |

## Testlar

`tests/test_testbank.py`: ruxsatlar va ko'lam (har lavozim), har bir QC qoidasi musbat va manfiy holatda, mavzu matni (matn, .docx, noto'g'ri fayl),
kalitsiz generatsiya (503, savol yaratilmaydi), soxta Claude bilan generatsiya — `claude_client.call_json` faqat test jarayonida, bazaning vaqtinchalik
nusxasida almashtiriladi (ilovada «soxta AI» muhit o'zgaruvchisi yo'q), ko'rib chiqish oqimi va tarix, ommaviy amallar, oraliq taqsimoti, banklar,
eksportlar (XML ElementTree bilan o'qiladi, GIFT qochirish, Aiken formati, .docx kaliti), qamrov hisobi.

## Ma'lum cheklovlar

- Moodle'ga to'g'ridan-to'g'ri yuklash (API) yo'q — fayl eksporti.
- Savol rasmlari va formulalar (LaTeX) qo'llab-quvvatlanmaydi; matn ichidagi formulalar oddiy matn sifatida.
- Bir nechta to'g'ri javobli (multi-select), moslashtirish (matching) turlari hali yo'q.
- Generatsiya sinxron (bir martada ≤ 5 mavzu); uzun navbat uchun fon vazifasi kerak bo'ladi.
- Savollarning statistik tahlili (qiyinlik indeksi, ajratish koeffitsiyenti) Moodle natijalari importidan keyin qo'shilishi mumkin.
