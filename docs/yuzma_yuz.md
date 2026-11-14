# Yuzma-yuz tadbirlar va masofaviy ta'limning huquqiy chegaralari

**Kod:** `app/yuzma_yuz.py`, `static/yuzma.js`, `static/yuzma.css`, `static/yuzma_talaba.js` (talaba kabineti),
`app/nazorat.py` (oxirgi bo'lim — «Yuzma-yuz tadbirlar va huquqiy chegaralar»)
**Testlar:** `tests/test_yuzma_yuz.py`, brauzer — `tools/yuzma_check.js`
**API:** `/api/yuzma/*` (xodimlar), `/api/talaba/yuzma` (talaba)
**Audit resursi:** `yuzma`

> **⚠ YURIST TASDIQLASHI KERAK.** Quyidagi me'yoriy talablar ikkilamchi manbalar (sharhlar, yangiliklar) asosida kodlangan.
> Asl matnlar — Vazirlar Mahkamasining 03.10.2022 yildagi 559-son qarori bilan tasdiqlangan «Masofaviy ta'lim to'g'risidagi nizom»
> va Prezidentning PF-73 (2025) farmoni — institut yuristi tomonidan solishtirilishi, raqamlar va talqinlar tasdiqlanishi shart.
> Shu tasdiqlanmaguncha tizim ko'rsatadigan qizil/sariq belgilar — **ogohlantirish**, rasmiy xulosa emas.

## Me'yoriy asos (ikkilamchi manbalar bo'yicha)

| Talab | Tizimda | Sozlanadi |
|---|---|---|
| O'zbekiston fuqarosi bo'lgan masofaviy talaba har semestr oldidan **LMS'da yuzma-yuz ro'yxatdan o'tadi** | «Ro'yxatdan o'tish» sessiyalari, muddat, talaba kabinetida banner, Nazorat markazida istisno | Muddat — bo'lim boshlig'i |
| Yakuniy nazorat, yakuniy davlat attestatsiyasi, bitiruv ishi himoyasi — **yuzma-yuz** | «Imtihon», «Attestatsiya», «Himoya» sessiyalari, qaydnoma | — |
| Xorijiy fuqarolar yuzma-yuz ro'yxatdan o'tishdan **ozod** | `students.citizenship` ≠ UZ → «ozod», tayinlanmaydi | Fuqarolik — Registrator ofisi |
| LMS'da **avtomatik monitoring va identifikatsiya** | Kirish jurnali (xeshlar), umumiy akkaunt alomatlari, yuzma-yuz shaxsni tekshirish | — |
| Bakalavriat yo'nalishida ≤ **300** masofaviy talaba | Nazorat markazi: ≥ 90 % sariq, ≥ 100 % qizil | Rektor: `dl_quota_bachelor` |
| Magistratura mutaxassisligida ≤ **30** | xuddi shunday | Rektor: `dl_quota_master` |
| Bitta o'qituvchiga ≤ **50** masofaviy talaba | > 50 qizil, ≥ 45 (90 %) sariq | Rektor: `dl_per_teacher` |
| Masofaviy shakl faqat **kunduzgi shakli mavjud** yo'nalishda | Kunduzgi talabasi yo'q masofaviy yo'nalish — qizil | — |
| **Pedagogika** yo'nalishlarida masofaviy ta'lim taqiqlangan (PF-73, 2025) | Pedagogik yo'nalishda masofaviy talaba — qizil | Yo'nalish turi — bo'lim boshlig'i / rektor |
| Kvotalarni buzish litsenziyani bekor qilishgacha olib kelishi mumkin | Kvota ≥ 100 % — eskalatsiyasiz darhol rektorga | Ogohlantirish foizi: `dl_quota_warn_pct` |

**Talqinlar (yurist bilan aniqlashtirish kerak):**

- *Kvota «to'lgan» (aynan 300) holati* qizil ko'rsatiladi: qonuniy (≤ 300), lekin yangi qabul mumkin emas. Oshgan (301+) — «OSHGAN».
- *O'qituvchiga 50 talaba* — tizim o'qituvchi dars beradigan masofaviy guruhlardagi takrorlanmagan talabalarni sanaydi (`teacher_groups`).
  Agar me'yor umumiy nisbatni (masofaviy talabalar / masofaviy ta'limda ishlaydigan o'qituvchilar) nazarda tutsa, bu nisbat ham
  «Huquqiy chegaralar» sahifasida ko'rsatiladi (namuna ma'lumotda ≈ 17,8). Namuna ma'lumotda per-o'qituvchi hisob ko'p qizil beradi.
- *Pedagogik yo'nalish* — avtomatik nomi bo'yicha (`pedagog`, `ta'lim`, `o'qitish`), masalan «Filologiya va tillarni o'qitish»
  ham pedagogik hisoblanadi. Klassifikator kodi bazada yo'q — «Huquqiy chegaralar» sahifasida qo'lda tuzatiladi (`yy_programs`).
- Kontingent: «faol» va «akademik ta'til» maqomidagi talabalar.

## Kim nimani ko'radi

| Lavozim | Ko'radi | Amallar |
|---|---|---|
| Masofaviy ta'lim bo'limi boshlig'i (`masofaviy`) | Hammasi | Sessiya, tayinlash, shaxsni tekshirish, **qaydnomani imzolash**, muddat, yo'nalish turi, HEMIS ma'lumotnomasi, fuqarolik, alomatlarni ko'rib chiqish |
| Bo'lim xodimi (`masofaviy_xodim`) | Hammasi | Sessiya, tayinlash, shaxsni tekshirish, alomatlarni ko'rib chiqish (imzo, muddat — yo'q) |
| Registrator ofisi boshlig'i (`talabalar`) | Sessiyalar, talabalar, chegaralar | Boshliq kabi; kirish jurnali va alomatlar — **yo'q** |
| Registrator xodimi (`registrator_xodim`) | Sessiyalar, talabalar | Sessiya, tayinlash, tekshirish, fuqarolik, HEMIS ma'lumotnomasi |
| Tyutor | Faqat o'z guruhlari talabalari va ular tayinlangan sessiyalar | — (faqat o'qish) |
| Rektor, o'quv ishlari prorektori | Jamlangan sonlar, sessiyalar (ismsiz), huquqiy chegaralar, qaydnoma fayllari | Chegara raqamlari — rektor (Nazorat markazi → Qoidalar) |
| Talaba | Faqat o'z holati va tadbirlari (`/api/talaba/yuzma`) | — |

Kirish jurnali va umumiy akkaunt alomatlari — **faqat Masofaviy ta'lim bo'limi**. Har bir so'rov (rad etilganlari ham) audit jurnalida.

## 1. Tadbirlar va qaydnoma

1. **Sessiya:** tur, sana (o'tgan sanaga emas), vaqt, xona (shu xonada vaqti kesishgan sessiya — 409), sig'im, ixtiyoriy yo'nalish.
2. **Tayinlash:** talaba ID lari, guruh yoki «hali ro'yxatdan o'tmaganlar» (bo'sh joygacha). Sig'imdan oshsa — **409, hech kim yozilmaydi**.
   O'tkazib yuboriladi: xorijiy fuqaro (ozod), faol emas, masofaviy emas, allaqachon o'tgan, boshqa sessiyaga tayinlangan.
   Har bir talabaga xabar Talabalar markazi navbatiga (`ops_notices`) yoziladi; kabinetda Telegram ulangan bo'lsa — darhol yuboriladi.
3. **Shaxsni tekshirish** (sessiya kuni): xodim hujjatni ko'zdan kechiradi va rasmni yuz bilan solishtiradi.
   - Pasport / ID karta: **faqat oxirgi 4 raqam** kiritiladi (4 tadan ortiq raqam — 400). HEMIS'dan olingan ma'lumotnoma bo'lsa
     (`yy_idref` — oxirgi 4 raqamning HMAC-xeshi), tizim solishtiradi; bo'lmasa — xodim «hujjat shu talabaniki» deb ko'zdan tasdiqlaydi.
   - Talaba guvohnomasi: HEMIS ID kiritiladi va bazadagi bilan solishtiriladi.
   - **Saqlanadi:** usul, raqam mosligi (1/0), moslik manbai (tizim/xodim), rasm mosligi (1/0), kim va qachon. **Saqlanmaydi:** kiritilgan
     raqamlar. Izohdagi 5+ raqamli ketma-ketliklar yashiriladi. Ikkalasi mos — «Keldi», aks holda — «Keldi — shaxsi tasdiqlanmagan»
     (ro'yxatdan o'tgan hisoblanmaydi).
4. **Qaydnoma** — faqat bo'lim boshlig'i (masofaviy yoki Registrator ofisi), sessiya o'tgandan keyin: belgilanmaganlar «Kelmadi», sessiya
   yopiladi, ro'yxat raqami `YQ-26/NNNN`, tekshirish kodi Hujjatlar reyestriga (`documents`, tur `yy_qaydnoma`) — `/verify/KOD`.
   Mazmunning SHA-256 xeshi saqlanadi va hujjatda chop etiladi. `.docx` (ISFT blanki, QR) va `.pdf` har safar bazadan quriladi.
   Imzodan keyin davomat o'zgarmaydi (409).
5. **Muddat** — standart: semestr boshidan 30 kun (kuzgi — 1 oktabr). Semestr kaliti: sentabr–yanvar — kuzgi, fevral–iyun — bahorgi,
   iyul–avgust — kelayotgan kuzgi (ro'yxatdan o'tish semestr oldidan).

**Talaba holatlari:** o'tgan · sessiyaga tayinlangan · kutilmoqda · muddat o'tgan · ozod (xorijiy) · akademik ta'tilda.
Talaba kabinetida bosh sahifada banner (muddat o'tgan — qizil, kutilmoqda — sariq, keyingi sessiya bilan) va «Yuzma-yuz» sahifasi.

## 2. Identifikatsiya va monitoring

- **Kirish jurnali** (`yy_access`): talaba kabinetiga har bir muvaffaqiyatli kirish (`student_portal.api_login` → `yuzma_yuz.on_login`).
  IP, tarmoq (IPv4 /24, IPv6 /48) va User-Agent — **faqat HMAC-xesh** (tuz `yy_meta.salt`), ko'rsatish uchun qurilma nomi («Chrome, Android»).
  Jurnal sahifasida tarmoqlar va qurilmalar shu talaba doirasida `T1, T2…`, `Q1, Q2…` deb raqamlanadi.
- Jurnalda yana: LRS launch'lari (`lrs_tokens`), kunlik xAPI statementlar soni, yuzma-yuz tadbirlar natijasi.
- **Umumiy akkaunt alomatlari** (oxirgi 7 kun, `yy_flags`):
  | Alomat | Qoida |
  |---|---|
  | Bir vaqtda turli tarmoqlardan | Kirish paytida shu talabaning boshqa tarmoqdan ochilgan, oxirgi 30 daqiqada faol sessiyasi bor |
  | Imkonsiz tez almashish | 15 daqiqa ichida tarmoq **va** qurilma birga almashgan (faqat tarmoq — Wi-Fi → mobil — alomat emas) |
  | Sutkada ko'p tarmoq | Bir kunda 4 va undan ko'p turli tarmoq |
- **Avtomatik bloklash yo'q.** Bo'lim izoh bilan «tasdiqlandi» yoki «asossiz» deb yopadi; ko'rib chiqilgandan keyin yangi dalil bo'lsa —
  yangi belgi. Nazorat markazida — jamlangan istisno.
- Cheklov: kabinet `request.client.host` ni oladi; proksi ortida haqiqiy IP to'g'ri uzatilishi kerak (`--forwarded-allow-ips`).

## 3. Nazorat markazi

`app/nazorat.py` oxiridagi alohida bo'lim: `RULES` ga 4 ta qoida qo'shiladi (rektor «Qoidalar» oynasida o'zgartiradi) va 2 ta detektor.

| Kalit | Soha | Holat |
|---|---|---|
| `yy:kvota:<daraja>:<yo'nalish>` | O'quv jarayoni | ≥ 90 % — sariq (egasida); ≥ 100 % — qizil, darhol rektorda |
| `yy:kunduzgi:…`, `yy:ped`, `yy:oqit` | O'quv jarayoni | qizil, darhol rektorda |
| `yy:oqit90` | O'quv jarayoni | sariq |
| `yy:royxat` | Talabalar | muddatdan keyingi kundan boshlab odatiy eskalatsiya |
| `yy:umumiy` | Talabalar | birinchi ko'rib chiqilmagan alomatdan boshlab odatiy eskalatsiya |

Egasi — Masofaviy ta'lim bo'limi boshlig'i. Istisnolarda ism va HEMIS ID yo'q (faqat sonlar). «Masofaviy ta'lim → Umumiy» sahifasining
boshida ham xulosa kartasi bor (bo'lim, rektor, prorektor).

## Ma'lumotlar

| Jadval | Mazmuni |
|---|---|
| `yy_sessions` | Sessiyalar: tur, semestr, sana, vaqt, xona, sig'im, holat (`rejada` / `yopilgan` / `bekor`) |
| `yy_assign` | Talaba × sessiya: holat, tekshirish natijasi (usul, `doc_match`, `match_src`, `photo_ok`, kim, qachon), xabar id |
| `yy_protocols` | Qaydnoma: ro'yxat raqami, tekshirish kodi, kim imzolagan, SHA-256, statistika |
| `yy_idref` | HEMIS ma'lumotnomasi: oxirgi 4 raqamning HMAC-xeshi |
| `yy_access`, `yy_flags` | Kirish jurnali (xeshlar) va alomatlar |
| `yy_programs` | Yo'nalish turi (pedagogik) — qo'lda tuzatishlar |
| `yy_meta` | Tuz, muddatlar (`deadline:<semestr>`), demo belgisi |
| `students.citizenship` | Yangi ustun (ISO kod; bo'sh — O'zbekiston) |

## Demo ma'lumot (sun'iy)

`yuzma_yuz.seed()` bir marta (`yy_meta.seed_v1`): ~1,2 % masofaviy talaba xorijiy fuqaro; semestr boshida 8 ta o'tgan ro'yxat sessiyasi
(~96 % keldi, qolganlari kelmadi/shaxsi tasdiqlanmagan) va imzolangan qaydnomalar; ~3,5 % talaba umuman kelmagan (muddat o'tgan);
6 kundan keyin «Qo'shimcha ro'yxatdan o'tish» (50 talaba) va semestr oxirida bitta yakuniy nazorat; oxirgi 21 kunlik kirish jurnali va
3 ta ataylab qo'yilgan umumiy akkaunt holati. Sahifada «Namuna ma'lumot» belgisi.

## API (qisqacha)

`GET meta | overview | sessions | sessions/{id} | students | journal/{sid} | flags | limits`,
`POST sessions | sessions/{id}/assign | …/unassign/{sid} | …/check | …/absent/{sid} | …/sign | …/cancel | students/{id}/citizenship | idref | deadline |
flags/{id}/review | programs`, `GET sessions/{id}/protocol.docx | protocol.pdf`; talaba: `GET /api/talaba/yuzma`.
