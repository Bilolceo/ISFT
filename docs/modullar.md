# Bo'limlar kaliti (modullar)

ISFT Core juda kattalashib ketgan edi: rektor menyusida 32 ta band, deyarli hammasi namuna (sun'iy) ma'lumotda, bir xil narsa
3–4 joyda takrorlanardi. Qaror: **egasi (mas'ul bo'lim) va haqiqiy ma'lumot manbai yo'q bo'limlar yashiriladi — o'chirib tashlanmaydi.**
Kod, jadvallar, ma'lumot va API joyida qoladi; bo'lim bitta kalit bilan qayta yoqiladi.

Yagona manba: `app/modules.py` (reestr `MODULES`, standart qiymatlar, API). Bu hujjatdagi jadvallar o'sha reestrdan olingan.

## Bu xavfsizlik chegarasi EMAS

Kalit — **mahsulot sozlamasi**. O'chirilgan bo'lim:

- menyuda hech kimga ko'rinmaydi;
- `go('<bo'lim>')` (havola, qidiruv, eski xatcho'p) «Bu bo'lim o'chirilgan» kartasini ko'rsatadi;
- panel kartalari, KPI plitkalari, ogohlantirishlar, qo'ng'iroqcha (bildirishnomalar), «Mening vazifalarim» manbalari va Ctrl+K
  qidiruv natijalarida chiqmaydi.

Lekin **API ishlayveradi** — kim nimani ko'ra olishini avvalgidek `app/rbac.py` va har bir modulning o'z tekshiruvi belgilaydi.
Ma'lumotni yashirish kerak bo'lsa, ruxsatni (rbac) o'zgartiring, kalitni emas. Testlar ham o'chirilgan bo'limlar API'sini
to'g'ridan-to'g'ri chaqiradi.

Filtrlash brauzerda bajariladi (`static/app.js`: `modOn`, `linkOn`, `modWork`, `modGate`): `/api/me` → `modules: {kalit: true|false}`.

## Qanday yoqiladi / o'chiriladi

Ustuvorlik yuqoridan pastga:

1. **Server sozlamasi** — `ISFT_CORE_MODULES` muhit o'zgaruvchisi, vergul bilan: `+moliya,-testbank,reyting`
   (`+x` yoki belgisiz `x` — yoqish, `-y` — o'chirish; noma'lum va qulflangan nomlar e'tiborga olinmaydi). Deploy uchun (Railway
   Variables). Shu yo'l bilan belgilangan bo'lim sahifada «server sozlamasi» deb ko'rsatiladi va sahifadan o'zgartirilmaydi.
2. **«Bo'limlar» sahifasi** — menyu → Bo'limlar (faqat AT bo'limi boshlig'i va rektor). Har bir bo'lim yonida kalit, tavsif va
   o'chiq bo'lsa sababi. O'zgarish darhol hamma foydalanuvchiga ta'sir qiladi (ular sahifani yangilaganda) va audit jurnaliga
   yoziladi (`resource = modullar`). Qiymat bazada: `module_switch(key, enabled, updated_at, updated_by)` — faqat qo'lda
   o'zgartirilganlari saqlanadi.
3. **Standart** — quyidagi jadvallar.

API: `GET /api/modules` (hamma: holat; AT boshlig'i va rektor: to'liq ro'yxat), `POST /api/modules/{kalit}` `{"enabled": true|false}`.

## Yoqishdan oldin nima kerak

Har bir bo'lim uchun ikkita narsa aniq bo'lishi shart:

1. **Egasi** — bo'limni kundalik yuritadigan mas'ul bo'lim (kim ma'lumot kiritadi, kim javob beradi);
2. **Ma'lumot manbai** — raqamlar qayerdan keladi (HEMIS, NEXTID LMS, 1C, o'rnatilgan kameralar yoki bo'limning o'zi qo'lda kiritadi).

Shu ikkisi bo'lmasa bo'lim namuna ma'lumotni «jonli» qilib ko'rsatadi — rahbarni chalg'itadi.

## Asosiy bo'limlar (standart: yoqilgan)

| Kalit | Bo'lim | Nima | Egasi va ma'lumot manbai |
|---|---|---|---|
| `panel` | Boshqaruv paneli | Bosh sahifa: sizdan kutilayotgan ishlar va lavozim ko'rsatkichlari. | — |
| `mywork` | Mening vazifalarim | Barcha manbalardagi ishlar bitta ro'yxatda. | — |
| `tasks` | Majlislar va topshiriqlar | Majlis bayonnomasi, qarorlar va topshiriqlar ijrosi. | Rektorat kotibi |
| `portal` | Yozishmalar | Bo'limlararo xatlar, fayllar va umumiy bazalar. | Devonxona |
| `documents` | Hujjat chiqarish | Ma'lumotnoma va boshqa hujjatlar, reyestr, QR tekshiruv. | Registrator ofisi |
| `orders` | Buyruqlar | Arizadan buyruq, kelishuv, rektor imzosi, reyestr. | Registrator ofisi, Kadrlar, Devonxona |
| `ops` | Talabalar navbati | Talabalar markazi: qoidalar bo'yicha holatlar va ijrochilar navbati. | Registrator ofisi · manba: HEMIS (hali ulanmagan) |
| `masofaviy` | Masofaviy ta'lim | LMS faolligi va o'quv kontenti monitoringi. | Masofaviy ta'lim bo'limi · manba: NEXTID LMS |
| `testbank` | Test bank | Mavzu testlari va oraliq nazorat banklari. | Masofaviy ta'lim bo'limi |
| `paket` | Dars tayyorlash | Bir ekranda dars: mavzu manbalari, taqdimot, video va test → SCORM / xAPI paket. | Masofaviy ta'lim bo'limi |
| `kurs` | Kurs muharriri | Bloklardan kurs (Articulate Rise o'rniga): darslar, interaktiv bloklar, test → xAPI / SCORM; Rise importi. | Masofaviy ta'lim bo'limi |
| `taqdimot` | Taqdimot | O'qituvchi materialidan ISFT shablonida taqdimot. | Kafedralar |
| `service` | Nosozliklar va murojaatlar | QR orqali nosozlik arizalari va xarid so'rovlari; «Murojaatlar» yorlig'i — «Talabalar navbati», «Tadbir qatnashuvi» — «Yoshlar ishlari» yoqilganda. | Xo'jalik bo'limi, AT bo'limi, Xarid bo'limi |

## Tizim sahifalari (doim yoqilgan, menyuda faqat AT bo'limi boshlig'ida)

| Kalit | Bo'lim | Nima | Egasi va ma'lumot manbai |
|---|---|---|---|
| `accounts` | Akkauntlar | Akkaunt yaratish, parolni tiklash, faolsizlantirish. | — |
| `rbac` | Ruxsat darajalari | Lavozimlar bo'yicha ruxsatlar jadvali. | — |
| `audit` | Audit jurnali | Kim, qachon, nimani so'ragani. | — |
| `modullar` | Bo'limlar | Shu sahifa: bo'limlarni yoqish va o'chirish. | — |

## Faqat menyu bandi (standart: o'chiq)

| Kalit | Bo'lim | Nima | Egasi va ma'lumot manbai |
|---|---|---|---|
| `chat` | ISFT Core bilan suhbat | Alohida menyu bandi. Panel ichidagi savol-javob oynasi baribir ishlaydi. | Alohida band kerak emas — suhbat paneldan ochiladi |
| `kiruvchi` | Kiruvchi xatlar | Devonxona reyestri. Devonxona uchun doim ochiq; rezolyutsiya kutayotgan xat «Mening vazifalarim»dan ochiladi. | Devonxona (reyestrni yuritadi) |
| `reports` | Hisobotlar | Tahliliy Word hisobotlar sahifasi. O'chiq bo'lsa — yuklab olish tugmalari panelda. | Alohida sahifa kerak emas — tugmalar panelda |

## Egasi va haqiqiy ma'lumot manbai kutilayotgan bo'limlar (standart: o'chiq)

| Kalit | Bo'lim | Nima | Egasi va ma'lumot manbai |
|---|---|---|---|
| `moliya` | Moliya | To'lovlar reyestri, solishtirish, byudjet ijrosi. | Buxgalteriya · manba: 1C / bank ko'chirmalari |
| `kadrlar` | Kadrlar | Shaxsiy ish, ishga qabul, shtat jadvali. | Kadrlar bo'limi · manba: kadrlar bazasi |
| `staffabs` | Xodimlar ta'tili | Safar, ta'til, kasallik varaqasi va dars jadvaliga ta'siri. | Kadrlar bo'limi · manba: dars jadvali (HEMIS) |
| `yoshlar` | Yoshlar ishlari | Turar joy, ijara monitoringi, tadbirlar (shu jumladan «Tadbir qatnashuvi»). | Yoshlar ishlari bo'yicha prorektor |
| `spaces` | Auditoriyalar | Xonalar bandligi (kamera sanog'i). | Xo'jalik bo'limi · manba: o'rnatilgan Hikvision kameralari |
| `cams` | Kameralar va xavfsizlik | Xavfsizlik voqealari, kamera salomatligi, navbatlar, Face ID. | AT bo'limi · manba: o'rnatilgan Hikvision kameralari |
| `syllabus` | O'quv dasturlari | Sillabus oqimi va yuklama kalkulyatori. | Akademik faoliyat bo'limi |
| `flows` | Akademik jarayonlar | Sessiya, apellyatsiya, qayta o'qish, ko'chirish, bitiruv. | Registrator ofisi · manba: HEMIS |
| `reyting` | Reyting | Talabalar o'zlashtirish reytingi. | Registrator ofisi · manba: HEMIS baholari |
| `amaliyot` | Amaliyot | Amaliyot bazalari, biriktirish, kundalik. | Amaliyot bo'limi |
| `ilmiy` | Ilmiy faoliyat | Nashrlar, grantlar, magistrlik dissertatsiyalari. | Ilmiy bo'lim · manba: nashrlar bazasi |
| `xalqaro` | Xalqaro hamkorlik | Shartnomalar, mobillik, viza, delegatsiyalar. | Xalqaro bo'lim |
| `rejalar` | KPI maqsadlari | KPI maqsadlari va sifat amallari. | Strategik bo'lim, Sifat boshqarmasi |
| `tekshiruv` | Ishlarni tekshirish | Talaba ishlarini AI yordamida tekshirish. | Kafedralar · talaba ishlari uchun rozilik tartibi |
| `qabul` | Qabul | Abituriyentlar arizalari. | Qabul bo'limi · manba: qabul bazasi |
| `docs` | Tarjima va shartnoma | Xat tarjimasi, shartnoma bandlari tahlili. | Yuridik bo'lim, Xalqaro bo'lim |
| `agents` | AI takliflari | AI agentlar takliflari va kunlik brifing. | Rektorat · takliflarni kim tasdiqlashi belgilanmagan |

## Alohida holatlar

- **`chat`** — kalit faqat menyu bandini boshqaradi. Panel ichidagi «ISFT Core'dan so'rash» oynasi doim ishlaydi va suhbat sahifasini ochadi.
- **`kiruvchi`** — Devonxona menyusida doim bor (reyestrni u yuritadi). Rezolyutsiya kutayotgan xat rahbarga «Mening vazifalarim»da
  chiqadi va o'sha yerdan ochiladi; boshqalarga alohida menyu bandi yo'q.
- **`reports`** — o'chiq bo'lsa, hisobotlarni yuklab olish tugmalari boshqaruv paneli pastidagi «Hisobotlar» kartasida (ruxsat bo'yicha).
- **`service`** («Nosozliklar va murojaatlar») — nomi hamma lavozimda bir xil. Yorliqlar: «Nosozliklar (QR)» va «Xarid so'rovlari» doim;
  «Murojaatlar va hodisalar» — `ops` (Talabalar navbati) yoqilganda; «Tadbir qatnashuvi» — `yoshlar` yoqilganda.
- **Tizim sahifalari** (`accounts`, `rbac`, `audit`, `modullar`) o'chirilmaydi. «Akkauntlar», «Ruxsat darajalari», «Audit jurnali»
  menyuda faqat AT bo'limi boshlig'ida; «Bo'limlar» — AT boshlig'i va rektorda.
- **Ixcham menyu** (`static/app.js`, `navApply()` → `LEAN`): rektor menyusida «Test bank» va «Dars tayyorlash» yo'q (xulosasi
  «Masofaviy ta'lim»da); o'qituvchi menyusida «Majlislar va topshiriqlar», «Hujjat chiqarish» va «Masofaviy ta'lim» yo'q (ishlari
  «Mening vazifalarim»da chiqadi, sahifa havoladan ochiladi). Natija: rektor — 10 band, o'qituvchi — 6 band.

## Kameralar: simulyator standart holda o'chiq

Kamera simulyatori «jonli monitoring» bo'lib ko'rinardi. Endi:

| Holat | Fon so'rovchisi | Avtomatik nosozlik arizalari | Paneldagi «Kameralar» KPI va ogohlantirishlar |
|---|---|---|---|
| `cams` va `spaces` o'chiq (standart) | ishlamaydi | ochilmaydi | yo'q |
| bo'lim yoqilgan, `ISFT_CORE_CAM_SIM` yo'q | faqat haqiqiy (ISAPI) kameralar | faqat haqiqiy kameralar | faqat haqiqiy kamera ulangan bo'lsa |
| bo'lim yoqilgan **va** `ISFT_CORE_CAM_SIM=1` | simulyator + haqiqiy | ha | ha |

Ishga tushishda (`app/occupancy.py: cleanup`, idempotent):

- `ISFT_CORE_CAM_SIM` yo'q — simulyator ochgan **ochiq** arizalar («Kamera … javob bermayapti», kamera voqeasidan ochilgan xavfsizlik
  arizalari) o'chiriladi va `occupancy` jadvalidagi simulyator sanoqlari to'liq tozalanadi. Haqiqiy kamera xonalari, yopilgan arizalar,
  odam yozgan va xaridga bog'langan arizalarga tegilmaydi.
- `ISFT_CORE_CAM_SIM=1` — sanoqlar 7 kun saqlanadi (`ISFT_CORE_OCC_KEEP_DAYS`, kuniga bir marta tozalanadi).

## Namuna ma'lumot belgilari

HEMIS va NEXTID bilan integratsiya hali yo'q. Shuning uchun:

- ilova tepasida yupqa tasma: «Namuna ma'lumot — haqiqiy tizimlar (HEMIS, NEXTID) hali ulanmagan»;
- KPI va sahifalarda «Manba: HEMIS» o'rniga «Namuna ma'lumot (HEMIS ulanmagan)» belgisi.

Haqiqiy tizimlar ulangach: `ISFT_CORE_REAL_DATA=1` — tasma va belgilar yo'qoladi, manba nomlari o'z holicha chiqadi.

## Muhit o'zgaruvchilari (shu ish bilan qo'shilgan)

| O'zgaruvchi | Standart | Nima qiladi |
|---|---|---|
| `ISFT_CORE_MODULES` | bo'sh | Bo'limlarni yoqish/o'chirish: `+x,-y` (sahifadagi qiymatdan ustun) |
| `ISFT_CORE_CAM_SIM` | o'chiq | `1` — kamera simulyatori (yuqoridagi jadval) |
| `ISFT_CORE_OCC_KEEP_DAYS` | `7` | Simulyator yoqilganda sanoq namunalari necha kun saqlanadi |
| `ISFT_CORE_REAL_DATA` | o'chiq | `1` — «Namuna ma'lumot» tasmasi va belgilari ko'rsatilmaydi |
| `ISFT_CORE_SHOW_DEMO_PASSWORD` | o'chiq | `1` — kirish sahifasida sinov paroli va xodimlar ismi/rasmi (faqat namoyish uchun) |
| `ISFT_CORE_TRUSTED_PROXIES` | `1` | Server oldidagi ishonchli proksilar soni (Railway — 1). Mijoz IP manzili `X-Forwarded-For` ning o'ngdan shu o'rindagi qiymati; `0` — sarlavha e'tiborga olinmaydi |

## Testlar

`tests/test_modullar.py` — standartlar, muhit sintaksisi, API va ruxsatlar, kamera simulyatori, tozalash, kirish sahifasi.
`tests/run_all.py` serverni `ISFT_CORE_CAM_SIM=1` bilan ishga tushiradi (seed ma'lumoti saqlansin), lekin bo'limlar standart holatda
qoladi; kamera bo'limi kerak bo'lgan to'plamlar (`test_facecam.py`, `test_hikvision.py`) uni o'zi yoqadi.
