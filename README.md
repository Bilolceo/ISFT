# ISFT Core — ISFT instituti uchun MVP

Rahbariyat uchun sun'iy intellektli boshqaruv tizimining ishlaydigan namunasi. Barcha ma'lumotlar **sun'iy (demo)**, haqiqiy shaxslarga aloqasi yo'q.

## Ishga tushirish

```bash
cd ~/Desktop/isft/jarvis-mvp
./run.sh
```
So'ng brauzerda: **http://localhost:8000**. Kirish sahifasi sinov parolini va xodimlar ismini ko'rsatmaydi; namoyish uchun: `ISFT_CORE_SHOW_DEMO_PASSWORD=1 ./run.sh` (demo parol — `ISFT_CORE_DEMO_PASSWORD`, standart `Isft2026`).

Birinchi marta ishga tushganda virtual muhit va baza avtomatik yaratiladi. To'liq AI uchun Ollama ishlab turishi va `qwen3:8b` modeli yuklangan bo'lishi kerak (`ollama pull qwen3:8b`).

Til modeli bo'lmasa, tizim **«Tahlil rejimi»**da ishlaydi:
- raqamlar, xulosalar, bayonnoma tahlili va shartnoma tekshiruvi qoidalar asosida bajariladi (`"source": "qoida"`);
- tarjima va javob loyihasi vaqtincha o'chiriladi.

Institut ichidagi boshqa serverdagi modelni ulash uchun `ISFT_CORE_LLM_URL` dan foydalaning. Bu faqat institut nazoratidagi server bo'lishi kerak: shaxsiy ma'lumot O'zbekistondan tashqariga chiqmasligi shart. Barcha sozlamalar va runbook: **`docs/ops.md`**.

| Buyruq | Vazifasi |
|---|---|
| `./run.sh` | Serverni ishga tushirish |
| `.venv/bin/python -m app.seed` | Demo ma'lumotlarni qaytadan yaratish (demo oldidan tavsiya etiladi) |
| `TELEGRAM_BOT_TOKEN=... ./run.sh` | Veb + Telegram bot (bot veb-jarayon ichida ishlaydi) |

Tarmoqdagi boshqa qurilmadan (masalan, rektorning planshetidan) kirish: `http://<kompyuter-IP>:8000`.

## Nima bor

| Modul | Taklifnomadagi funksiya | Holat |
|---|---|---|
| Boshqaruv paneli | KPI, proaktiv ogohlantirishlar, rolga mos grafiklar | ✅ |
| ISFT Core suhbat | "Qaysi yo'nalishda ortda qolyapmiz?" kabi savollar | ✅ mahalliy AI |
| Talabalar monitoringi | Xavf ostidagi talabalarni oldindan aniqlash | ✅ |
| Reyting | Talabalar o'zlashtirish reytingi: kredit bilan tortilgan GPA, guruh/kurs/yo'nalish/fakultet/institut o'rni, qaydnoma (.xlsx/.docx), dinamika, a'lochilar, bo'linmalar ([docs/reyting.md](docs/reyting.md)) | ✅ |
| Majlis nazorati | Bayonnomadan kim/nima/qachon ajratish, muddat nazorati | ✅ |
| Hisobot generatori | Word (.docx) — brifing, akademik, moliya, ilmiy | ✅ |
| Tarjima va shartnoma yordamchisi | Xorijiy xat tarjimasi, shartnoma tekshiruvi, javob loyihasi (mahalliy AI kerak) | ✅ |
| RBAC (15 lavozim) | Taklifnomaning 4-bo'limidagi jadval aynan kodlangan | ✅ |
| Audit jurnali | Har bir so'rov: kim, qachon, nima, ruxsat/rad | ✅ |
| Telegram bot | Bitta bot, ko'p rol; ish haqi/kadrlar botga chiqmaydi | ✅ token kerak |

## Menyu tuzilmasi va bo'limlar kaliti

Mahsulot soddalashtirildi: egasi (mas'ul bo'lim) va haqiqiy ma'lumot manbai yo'q bo'limlar **yashirilgan** (kod va API joyida, bitta
kalit bilan qayta yoqiladi). Yagona manba — `app/modules.py`; to'liq ro'yxat, standartlar va yoqish tartibi: **[docs/modullar.md](docs/modullar.md)**.

| Standart holat | Bo'limlar |
|---|---|
| Yoqilgan | Boshqaruv paneli · Mening vazifalarim · Majlislar va topshiriqlar · Yozishmalar · Hujjat chiqarish · Buyruqlar · Talabalar navbati · Masofaviy ta'lim · Test bank · Dars tayyorlash · Taqdimot · Nosozliklar va murojaatlar |
| Faqat AT bo'limi boshlig'i | Ruxsat darajalari · Audit jurnali · Akkauntlar · Bo'limlar (bu sahifa rektorda ham bor) |
| O'chiq | Moliya · Kadrlar · Xodimlar ta'tili · Yoshlar ishlari · Auditoriyalar · Kameralar va xavfsizlik · O'quv dasturlari · Akademik jarayonlar · Reyting · Amaliyot · Ilmiy faoliyat · Xalqaro hamkorlik · KPI maqsadlari · Ishlarni tekshirish · Qabul · Tarjima va shartnoma · AI takliflari · (menyu bandi sifatida) Suhbat, Hisobotlar, Kiruvchi xatlar |

- Yoqish/o'chirish: menyu → **Bo'limlar** (AT bo'limi boshlig'i, rektor) yoki `ISFT_CORE_MODULES="+moliya,-testbank"`. Bu mahsulot kaliti, xavfsizlik chegarasi emas — ruxsatni `app/rbac.py` tekshiradi.
- Standart holatda rektor menyusida 10 ta, o'qituvchida 6 ta band; guruhlangan (yig'iladigan) menyu faqat 12 tadan ko'p band bo'lganda yoqiladi (`static/nav.js`).
- Ilova tepasida «Namuna ma'lumot — haqiqiy tizimlar (HEMIS, NEXTID) hali ulanmagan» tasmasi; `ISFT_CORE_REAL_DATA=1` bilan o'chadi.
- Kamera simulyatori standart holda o'chiq (`ISFT_CORE_CAM_SIM=1` va «Kameralar» bo'limi yoqilgandagina ishlaydi).
- Ixcham rejim (faqat ikonkalar): tepadagi ☰ tugma yoki klaviaturada `[`. 980px dan tor ekranda — chiquvchi mobil menyu.
- Nomlar: bo'limlararo xatlar — **Yozishmalar**, rasmiy hujjatlar — **Hujjat chiqarish**, QR nosozliklar va xarid — **Nosozliklar va murojaatlar** (nom lavozimga qarab o'zgarmaydi).

## Arxitektura (taklifnomadagi 3 qatlam)

```
 Veb-panel / Telegram bot          ← 3-qatlam: interfeys
            │
   app/rbac.py  (ruxsat + audit)   ← 2-qatlam: ISFT Core yadrosi
   app/services.py (ko'lam filtri)
   app/ai.py  → Ollama (mahalliy)  ← AI faqat ruxsatdan o'tgan ma'lumotni ko'radi
            │
   data/jarvis.db (SQLite)         ← 1-qatlam: bo'lim ma'lumotlari (HEMIS formatiga yaqin)
```

**Asosiy xavfsizlik tamoyili:** til modeli bazaga hech qachon to'g'ridan-to'g'ri kirmaydi. Savol avval kalit so'zlar bo'yicha ma'lumot manbasiga yo'naltiriladi, RBAC tekshiruvidan o'tadi, kod tomonidan aniq faktlar matni tuziladi va faqat shu matn modelga beriladi. Model raqam o'ylab topa olmaydi, chunki raqamlar unga tayyor holda beriladi.

## Telegram botni ulash

1. Telegram'da @BotFather → `/newbot` → token oling.
2. `TELEGRAM_BOT_TOKEN=<token> ./run.sh`. Bot veb-server jarayoni ichida ishga tushadi. Holatini `/api/status` → `bot` bo'limida ko'rasiz.
   - Token bo'lmasa, ilova odatdagidek ishlaydi, bot esa o'chiq turadi.
   - Bir token bilan faqat bitta poller ishlaydi (data papkasidagi fayl qulfi).
   - Botni alohida jarayonda yuritish: `ISFT_CORE_BOT=0` qo'ying va `python -m app.bot` ni ishga tushiring.
3. Botga yozing: `REKTOR Isft2026` (boshqa kodlar: OQUV, ILMIY, MOLIYA, YOSHLAR, REGOFIS, KAFEDRA, USTOZ, QABUL, XALQARO…).
4. Buyruqlar: `/bugun` (kunlik brifing), `/brifing` (Word hisobot), `/topshiriqlar`, `/xatlar` (portal: muddati yaqin xatlar), `/chiqish`.
   Portal muddat eslatmalari ish kunlari **09:00** da (Toshkent vaqti, `ISFT_CORE_TZ`) keladi (`ISFT_CORE_PORTAL_REMIND`). Eslatma ijrochiga, ijrochi bo'lmasa bo'lim rahbariga, yuboruvchiga va rezolyutsiya muallifiga yuboriladi.
5. Rektor yordamchisi agenti har kuni **08:00** da ulangan rahbarlarga (rektor, kengash, prorektorlar) kunlik brifing yuboradi. Vaqtni o'zgartirish: `ISFT_CORE_BRIEF_TIME=07:30`. Savollarga javob — veb-suhbatdagi agent bilan bir xil (raqamlar tekshiriladi).

Buxgalteriya (`BUXGALTER`) va Kadrlar (`KADR`) botga ulana olmaydi — bu ataylab qilingan.

## MVP cheklovlari (rektorga ochiq aytish kerak)

- **Ma'lumotlar sun'iy.** HEMIS va 1C bilan integratsiya pilot bosqichida quriladi. HEMIS'ning ochiq API hujjati yo'q, kirish institut HEMIS administratori orqali olinadi.
- **AI tezligi.** Bu noutbukda (M4, 16 GB) javob 10–25 soniyada chiqadi. Server uchun 32–64 GB xotirali Mac mini (M4 Pro) tavsiya etiladi: kattaroq model, tezroq javob.
- **O'zbek tili.** 8B model o'zbekchada tushunarli, lekin ba'zan uslubiy xatolar qiladi. Raqamlar esa har doim to'g'ri, chunki ular koddan olinadi.
- **Kirish.** Demo'da barcha akkauntlar uchun parol `Isft2026` (bazada PBKDF2 xesh). Real tizimda har bir xodimga alohida parol yoki OneID/HEMIS + Telegram'da qo'shimcha tasdiqlash.
- **Sessiyalar.** Cookie'da tasodifiy token, bazada uning xeshi (`sessions` jadvali, 12 soat). Chiqish yoki parol o'zgarishi eski sessiyalarni darhol bekor qiladi; server qayta ishga tushganda foydalanuvchilar chiqib ketmaydi. Kirish va Telegram ulanishida 10 daqiqada 5 ta xato urinishdan keyin blok (IP bo'yicha — 20 ta).
- **Zaxira nusxa** va HTTPS hali yo'q — pilotda qo'shiladi.

## Fayllar

```
app/db.py        sxema
app/seed.py      demo ma'lumotlar (ichida rektor uchun "hikoyalar")
app/rbac.py      15 lavozim, ruxsatlar, audit
app/sessions.py  sessiyalar (bazada), xato urinishlar cheklovi
app/portal.py    bo'limlararo portal: yozishma, rezolyutsiya, ijrochi, fayllar, umumiy bazalar (docs/portal.md)
app/filecheck.py yuklanayotgan fayl mazmunini tekshirish (magic bytes, makros, arxiv, ixtiyoriy ClamAV)
app/portal_backup.py  portal zaxira nusxasi: backup / restore / verify
app/services.py  ma'lumot servislari, ogohlantirishlar, KPI
app/ai.py        mahalliy AI, faktlar, bayonnoma tahlili, tarjima va shartnoma yordamchisi
app/reports.py   Word hisobotlar
app/reyting.py   o'zlashtirish reytingi: kesh (RANK oyna funksiyalari), ro'yxat, karta, qaydnoma eksporti (docs/reyting.md)
app/main.py      veb-server (FastAPI)
app/bot.py       Telegram bot
static/          veb-interfeys (internetsiz ishlaydi, CDN yo'q); static/nav.js — yon menyu guruhlari va ixcham rejim
```

## Hujjat chiqarish (qog'ozbozlikni avtomatlashtirish)

Menyu: **Hujjat chiqarish** (rasmiy hujjat chiqarish; tahliliy hisobotlar — «Hisobotlar»da). 14 ta shablon, hammasi bazadan avtomatik to'ldiriladi:

| Bo'lim | Hujjatlar |
|---|---|
| Talabalar va Registrator ofisi | O'qish joyidan ma'lumotnoma (uz/en, guruh bo'yicha ommaviy), akademik ma'lumotnoma (transkript), kontrakt qarzdorligi bo'yicha ota-onaga xat (guruh/fakultet bo'yicha paket), amaliyot yo'llanmasi (qaytarma qismi bilan) |
| Buyruqlar | Talabalar harakati (akademik ta'til, ko'chirish, chetlashtirish, tiklash), mehnat ta'tili — **rektor imzosidan keyin kuchga kiradi** |
| O'quv jarayoni | Yakuniy nazorat qaydnomasi (fan yoki butun guruh paketi), akademik qarzdorlar ro'yxati, o'quv yuklama taqsimoti |
| Rektorat va ijro nazorati | Majlis bayonnomasi, muddati o'tgan topshiriqlar bo'yicha ijro xatlari (paket), xizmat xati (mahalliy AI matn tuzadi) |
| Kadrlar / Xalqaro | Ish joyidan ma'lumotnoma, invitation letter (viza uchun) |

Har bir hujjatda: ISFT rasmiy blanki (isft.uz ranglari), ro'yxat raqami (`MT-26/0001`), QR-kod → `/verify/KOD` sahifasi
(haqiqiy / imzolangan / bekor qilingan; shaxsiy ma'lumot qisqartirilgan). Lavozim va ko'lam bo'yicha ruxsat (tyutor — faqat o'z fakulteti,
o'qituvchi — faqat o'z fanlari), har bir amal audit jurnalida. Fayllar: `data/docs/`.

**Rasmiy logo:** `static/brand/logo.png` ga qo'yilsa, barcha hujjatlar va tekshiruv sahifasida avtomatik ishlatiladi
(hozircha sayt uslubidagi "ISFT" belgisi — `isft-mark.png`).

**Akademik qoidalar** (`app/academic_rules.py`, manba — "O'quv jarayoni va akademik qoidalar" taqdimoti): o'tish bali 40
(«3»), oraliq nazorat 30 (min. 12), yakuniy nazorat 70 (min. 28), shkala 65+ A «5» · 60–64 B «4» · 50–59 C «4» · 45–49 D «3» ·
40–44 E «3» · 0–39 F «2», GPA = Σ(kredit × baho) / Σ kredit, 1 kredit = 30 soat (12 + 18), dars vaqtlari (`app/occupancy.py` SLOTS).

**Institut tasdiqlashi kerak bo'lgan sozlamalar** (`app/documents.py` boshida): fan krediti (o'quv dasturida bo'lmasa standart 6 — `academic_rules.CREDIT_DEFAULT`; transkript va Reyting bir xil manbadan),
1 stavka yuklamasi (840 soat), pedagog xodimlar ta'tili (56 kun). Bular institut nizomi bilan solishtirilishi shart.

## Nosozliklar va murojaatlar (`app/service.py`)
| Modul | Xodim | Ommaviy sahifa (login'siz) |
|---|---|---|
| Xona QR nosozliklari | Xo'jalik va texnik bo'lim, rektor, yoshlar prorektori | `/q/<xona-kodi>` — muammo turi, izoh, rasm (EXIF tozalanadi) |
| Yagona murojaat + hodisalar | Registrator ofisi, o'quv prorektori, rektor | `/m` — erkin matn → toifa + mas'ul bo'lim avtomatik |
| Tadbir QR qatnashuvi | Yoshlar prorektori, talabalar bo'limi, rektor | `/t/<tadbir-kodi>` — HEMIS ID bilan belgilash (ro'yxat ochiq bo'lsa) |

- Tasniflash — kalit so'zlarga asoslangan qoidalar (tez, tushuntirib bo'ladigan). Bir xil tizim nosozligi bo'yicha 6 soat ichida ≥3 murojaat → bitta hodisa.
- AI faqat umumiy xabar loyihasini yozadi; yuborishni xodim tasdiqlaydi.
- Ommaviy sahifalar: IP bo'yicha so'rov cheklovi, hech qanday shaxsiy ma'lumot ko'rsatilmaydi (ism qisqartiriladi), har bir yozuv audit jurnaliga.
- QR manzil: avtomatik lokal IP. Doimiy domen bo'lsa: `ISFT_CORE_PUBLIC_URL=https://jarvis.isft.uz ./run.sh`.

## Auditoriyalar bandligi (`app/occupancy.py`)
- **Standart holatda o'chiq** (bo'lim kaliti `spaces`/`cams`; simulyator — `ISFT_CORE_CAM_SIM=1`). Batafsil: docs/modullar.md.
- Ulagichlar: `isapi` — Hikvision, lokal tarmoq, HTTP Digest, `POST /ISAPI/System/Video/inputs/channels/{ch}/counting/search` (bugungi kirdi − chiqdi = xonadagi son). Kamera "region people counting" qo'llasa: `ISFT_CORE_CAM_OCC_PATH=/ISAPI/...{ch}...` (aniq yo'l kamera modeli ISAPI hujjatidan olinadi). `sim` — jadval + davomatdan simulyator.
- Fon jarayoni har `ISFT_CORE_CAM_POLL` (60) soniyada so'raydi, 5 daqiqada bir o'lchov saqlaydi. Video/rasm hech qachon olinmaydi.
- Ruxsat: rektor, o'quv prorektori, xo'jalik, kuzatuv kengashi. O'qituvchi ismi faqat rektor va o'quv prorektoriga. Kamera sozlash — xo'jalik va rektor; parol API javobida qaytarilmaydi.
- Hikvision xavfsizligi: kameralar alohida VLAN, internetga chiqmaydi, Hik-Connect o'chiq, proshivka 2021-09 dan yangi (CVE-2021-36260), alohida Operator akkaunt (5 xato urinish — IP bloklanadi).
- ⚠️ Haqiqiy kamerada sinalmagan: XML element nomlari (`enterCount`/`exitCount`) forum va hujjat asosida; birinchi ulanishda "Tekshirish" tugmasi bilan tasdiqlang.

## Kod tekshiruvi (2026-11-05)
Backend va frontend mustaqil ko'rib chiqildi; tuzatildi: hujjat qidiruvida rol tekshiruvi yo'qligi (talaba HEMIS ID sizishi), buzuq sana butun panelni yiqitishi, "Moliya fakulteti dekani" → moliya prorektoriga ketishi (endi — Registrator ofisiga), fakultet ko'lamidagi lavozimning umumiy hodisani boshqa fakultetlar nomidan yopishi, imzolangan buyruqni muallif bekor qilishi, AI o'chiq paytda bayonnoma tahlili, ikki marta bosish, "Yuklanmoqda…" da qotib qolish, qorong'i rejim kontrasti, blur sabab sekinlik. Regressiya: `scratchpad/regress.py` — 28/28.

## Sanalar
Yagona sana manbai — `services.TODAY = date.today()`. Seed hikoyasi 2026-11-04 ga nisbatan yozilgan; `app/dateshift.py` seed oxirida barcha sanalarni (majlis matnlaridagi "13.10.2026", "15-noyabrgacha" ham) bugungi kunga suradi. Har kuni ertalab `python -m app.seed` — hikoya (3 ta muddati o'tgan topshiriq, 23/47 kunda tugaydigan shartnomalar) o'sha kunga moslashadi.

## Bulutga joylash (Railway) — faqat demo uchun
`railway.json` va `start.sh` tayyor. To'liq qo'llanma: **`docs/ops.md`** (o'zgaruvchilar, volume, Telegram tokeni, zaxira nusxa, seed qoidalari).

- **Volume:** baza uchun `/app/data` ga ulang.
- **O'zgaruvchilar:**
  - `ISFT_CORE_PUBLIC_URL=https://<domen>` — QR havolalari uchun;
  - `TELEGRAM_BOT_TOKEN` — bot kerak bo'lsa;
  - `TZ` — `start.sh` o'zi `Asia/Tashkent` qo'yadi.
- **Healthcheck:** `/healthz` (faqat baza), kutish vaqti 900 soniya.
- **Birinchi ishga tushish:** demo ma'lumotlar yaratiladi (2–5 daqiqa). `SEED_VERSION` o'zgarsa, baza qayta yaratiladi. Bu faqat demo uchun; haqiqiy ma'lumotda `ISFT_CORE_RESEED=0` qo'ying.
- **AI:** bulutda Ollama yo'q, shuning uchun tizim «Tahlil rejimi»da ishlaydi. Haqiqiy talaba ma'lumotlari bilan bulutga qo'yilmaydi: loyiha tamoyiliga ko'ra ma'lumot institut serverida saqlanadi.
