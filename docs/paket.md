# Kontent paketlari moduli

**Kod:** `app/paket.py`, `static/paket.js`, `static/paket.css` (pleyer — `app/paket_player/`, alohida ish oqimi)
**Testlar:** `tests/test_paket.py`, brauzer integratsiyasi — `tools/paket_build_check.js` (PW va CHROME berilganda test chaqiradi)
**API:** `/api/paket/*`
**Ruxsat resursi:** `rbac.PAKET` (kirish — moduldagi jadval bo'yicha, har bir so'rov audit jurnalida)

## Nima uchun

Masofaviy ta'lim bo'limi har bir mavzu uchun Articulate'da (yiliga ≈ $2000) bitta paket yig'adi: ma'ruza matni (reja bilan) shablonga,
taqdimot alohida blokka, YouTube video havolasi va test; xAPI zip qilib LMS'ga yuklaydi. LMS hammasini saqlaydi, faqat video YouTube'da qoladi.
Bo'lim talabi: «video havolasini bersak — har mavzuga o'zi joylasin; ma'ruza matnini bersak — reja bilan chiroyli qo'ysin; taqdimot blokda,
iloji bo'lsa PPT kabi ochilsin, bo'lmasa yuklab olinadigan fayl». Bu modul (3-bosqich) o'sha ishni o'zimizda bajaradi.

LMS turi hali aniq emas (ehtimol Moodle), shuning uchun uch format: **SCORM 1.2** (eng universal), **SCORM 2004 4-nashr**, **xAPI** (tincan.xml);
qo'shimcha — oddiy HTML (LMS'siz).

## Kim nimani ko'radi

| Lavozim | Ko'rinish | Amallar |
|---|---|---|
| Masofaviy ta'lim bo'limi boshlig'i (`masofaviy`) | Barcha kurslar | Manbalar, yig'ish, ko'rish, yuklab olish, tasdiqlash / qaytarish, umumiy sozlamalar, avtomatik joylash |
| Bo'lim xodimi (`masofaviy_xodim`) | Barcha kurslar | Boshliq bilan bir xil |
| O'qituvchi | O'z kurslari (`dl_courses.teacher_id`) | Manba yuklash, video, mavzu sozlamasi, yig'ish, ko'rish, yuklab olish, kurs paketi |
| Kafedra mudiri | O'z kafedrasi kurslari | Ko'rish va yuklab olish |
| Rektor, o'quv ishlari prorektori | Faqat jamlangan qamrov | — (matn, paket mazmuni va yuklab olish yo'q) |

Boshqa lavozimlar — 403. Begona kursga murojaat ham 403 va audit jurnaliga yoziladi.

## Kurslar va mavzular

Kurs ro'yxati qurilmadi: Masofaviy ta'lim modulidagi `dl_courses` va `dl_items` (mavzu nomlari) **faqat o'qiladi** — Test bank bilan bir xil.

## Manbalar va ustuvorlik

| Blok | Manba (ustuvorlik tartibida) |
|---|---|
| Ma'ruza matni | 1) shu yerda yuklangan `.docx` / `.pdf` / `.txt` yoki joylashtirilgan matn (`pk_assets`, `purpose='matn'`); 2) Test bankdagi mavzu matni (`tb_sources`, oxirgisi). Asl `.docx`/`.pdf` — «Fayl» bloki sifatida ham qo'shiladi |
| Reja | Matndagi «Reja:» / «Режа:» / «План:» bo'limi (raqamli, belgili yoki oddiy qatorlar; bir qatorda «Reja: 1. … 2. …»); bo'lmasa — 1-darajali sarlavhalar (kamida 2 ta) |
| Taqdimot | 1) yuklangan `.pptx` (python-pptx: slayd sarlavhasi, bandlar, jadval qatorlari, izohlar, har slayddagi eng katta rasm → `assets/slides/sN.png`; asl `.pptx` — yuklab olish uchun); 2) «Taqdimot» modulidagi deck (`pres_decks`, o'qituvchining o'zi yoki kurs o'qituvchisiniki; yig'ilgan `.pptx` bo'lsa — u ham); 3) PNG/JPG slayd rasmlari to'plami (nom bo'yicha tartib). `.pdf` — `pdf` maydoni (pleyer brauzerda ochadi). Eski `.ppt` qabul qilinmaydi |
| Video | 1) shu yerda kiritilgan havola (`pk_topics.video_url`, «Avtomatik joylash» ham shu yerga yozadi); 2) kontent monitoringidagi videodars havolasi (`dl_items`, `kind='video'`). YouTube → video bloki; boshqa http(s) havola → «Videodars» matn bloki (havola bilan) |
| Test | Test bankdagi **tasdiqlangan** savollar (`tb_questions`). Hammasi yoki N ta (tanlov deterministik: manba o'zgarmasa — o'sha savollar). To'g'ri/noto'g'ri savol har doim `["To'g'ri","Noto'g'ri"]`, `[0]` — to'g'ri (bazada qanday saqlangan bo'lmasin) |
| Qo'shimcha fayllar | `.pdf`, `.docx`, `.pptx`, `.xlsx`, `.png`, `.jpg` (`purpose='fayl'`) |

**Tayyorgarlik** (UI'dagi M / T / V / S belgilar): matn, taqdimot, video, test. Paket **«tayyor»** — sozlamada yoqilgan shu to'rt blokning hammasi
bor bo'lsa; aks holda **«qoralama»**. Yig'ish uchun kamida bitta kontent bloki (matn, taqdimot, video yoki fayl) kerak.

### Matn → HTML

Server tomonda: sarlavhalar («1.» — yolg'iz turgan qisqa qator, «1.1.» / «1.1.1.», «#», KATTA HARFLI qisqa qator), ro'yxatlar («-», «•», «1)»,
ketma-ket «1. 2.»), « | » bilan ajratilgan qatorlar → jadval, uzilgan qatorlar → paragraf, `**qalin**`, qisqa «…:» qatori → qalin izoh.
Mavzu nomi qatori («5-MAVZU: …») olib tashlanadi. Natija oq ro'yxat bo'yicha **tozalanadi** (`sanitize`): `h2 h3 h4 p ul ol li strong em b i u
blockquote table thead tbody tr th td br sup sub code pre a` (`a` — faqat http(s) `href`, `rel="noopener noreferrer"`); script, style, iframe, svg,
`on*` atributlari, `javascript:` / `data:` havolalar, rasmlar olib tashlanadi. script/style/iframe/object/svg/math/textarea/title kabi teglar
mazmuni bilan tashlanadi; bo'sh teglar (embed, frame, param …) — «tashlash» rejimiga kirmasdan; button/form/select — faqat teg (matni qoladi);
yopilmagan textarea/title — hujjat oxirida matni (escape qilingan) qaytariladi.

## Ma'lumotlar

| Jadval | Mazmuni |
|---|---|
| `pk_packages` | Paket versiyasi: kurs, mavzu (0 — kurs paketi), versiya, tur, holat (`qoralama` / `tayyor` / `tasdiqlandi`), sozlama, manba barmoq izi, yig'ilgan vaqt va kim, fayl, hajm, sha256, tekshiruv natijasi, tayyorgarlik, tasdiqlagan, qaytarish izohi |
| `pk_assets` | Yuklangan fayllar: maqsad (`matn` / `taqdimot` / `slayd` / `fayl`), tur (pptx/pdf/docx/png/jpg/…), nom, yo'l, hajm, sha256, meta (matn, reja, PPTX slaydlari) |
| `pk_topics` | Mavzu: video havola, biriktirilgan deck, mavzu sozlamasi (standartdan farqi) |
| `pk_log` | Tarix: yuklash, video, sozlama, yig'ish, tasdiqlash, qaytarish |
| `pk_meta` | `defaults` (standart sozlamalar), `seed_v1`, `demo_pkg` |

Fayllar: `<DATA_DIR>/paket/assets/<kurs>/<mavzu>/…` va `<DATA_DIR>/paket/packages/<kurs>/<mavzu>/v<N>_<tur>.zip` (doimiy disk — `ISFT_CORE_DATA_DIR`).
Mavzu boshiga **har bir paket turi (SCORM 1.2 / SCORM 2004 / xAPI / oddiy) bo'yicha oxirgi 3 versiya** va tasdiqlangani saqlanadi; eskilari fayli bilan o'chiriladi. «O'zgarish yo'q» tekshiruvi ham tur bo'yicha: boshqa turni yig'ish keyingi qayta yig'ishni yangi versiyaga aylantirmaydi.

## Sozlamalar

Standart (bo'lim): tur (`scorm12` / `scorm2004` / `xapi` / `none`), yakunlash (`view_all` / `quiz_pass` / `view_and_quiz`), o'tish foizi (mastery),
savollar soni (0 — hammasi), aralashtirish, urinishlar (0 — cheksiz), javobdan keyin izoh, bloklar. Mavzu uchun alohida o'zgartirish mumkin
(o'qituvchi — o'z kursida). Testsiz paketda yakunlash avtomatik `view_all`.

## Paket kontrakti (pleyer bilan umumiy)

Zip ildizi: pleyer fayllari (`app/paket_player/*`, `index.html` — ishga tushirish fayli), `content.js` (`window.PAKET = {...};`, UTF-8),
`content.json` (o'sha JSON), `assets/…` (`logo.png`, `slides/sN.png`, `taqdimot.pptx`, `taqdimot.pdf`, `files/*`) va manifest.

```
{"v":1,"id":"isft-<kurs>-<mavzu>-v<versiya>","title":"…","lang":"uz",
 "course":{"subject","direction","course","kafedra","teacher"}, "topic":{"no","title"},
 "brand":{"name":"ISFT","full":"International School of Finance and Technology","color":"#8B0033","logo":"assets/logo.png"},
 "built":"<ISO>", "blocks":[plan | text | slides | video | file | quiz …],
 "tracking":{"mode","completion","mastery","activity_id":"https://isft.uz/xapi/paket/<kurs>/<mavzu>"}}
```

Bloklar tartibi: reja → matn → taqdimot → video → fayllar → test; `id` — `b1`, `b2`, …; savol `id` — `q<tb_questions.id>`.

## Turlar va manifestlar

| Tur | Manifest | Asosiy elementlar |
|---|---|---|
| SCORM 1.2 | `imsmanifest.xml` (`imscp_rootv1p1p2`, `adlcp_rootv1p2`) | `schemaversion 1.2`, bitta `item` → `resource adlcp:scormtype="sco" href="index.html"`, `adlcp:masteryscore` (test yakunlashga kirsa), barcha fayllar `<file>` da |
| SCORM 2004 4-nashr | `imsmanifest.xml` (`imscp_v1p1`, `adlcp_v1p3`, `imsss`, `adlseq`, `adlnav`) | `schemaversion 2004 4th Edition`, `adlcp:scormType="sco"`, `imsss:sequencing` — `primaryObjective satisfiedByMeasure="true"` + `minNormalizedMeasure` = mastery/100, `deliveryControls completionSetByContent/objectiveSetByContent`, tashkilotda `controlMode choice/flow` |
| xAPI | `tincan.xml` | `activity id` = `tracking.activity_id`, `type …/activities/course`, `name`/`description`/`launch` (`lang="uz"`) |
| Oddiy HTML | — | `index.html` (LMS'siz, ko'rish rejimi) |

**Pleyer kuzatuvi:** LMS'ga oxirgi urinish natijasi yuboriladi, lekin «passed» hech qachon pasaytirilmaydi (SCORM 1.2 `lesson_status`,
SCORM 2004 `success_status` va ball, xAPI kurs natijasi); test o'tilgandan keyin qayta urinish berilmaydi (`suspend_data` ixchamlanib javoblar
tushib qolsa ham — o'tganlik belgisi bo'yicha). Fill-in savolida har bir qabul qilinadigan javob — alohida `correct_responses.n.pattern`
(2004: `{case_matters=false}…`) / xAPI `correctResponsesPattern` elementi. xAPI: kurs activity uchun `passed`/`failed` (score scaled/raw/min/max,
success, completion) natija o'zgargan har safar, `completed` — bir marta. Asset havolalari: boshqaruv belgilari olib tashlanib, faqat nisbiy
oq ro'yxat yo'llari (`[A-Za-z0-9_\-./%]`, `/` bilan boshlanmaydi, `..` yo'q); tashqi havolalar — faqat http(s).

**Kurs paketi:** bitta manifestda har mavzu alohida SCO, o'z papkasida (`t01/index.html`, `t02/…`); har mavzu — oxirgi tasdiqlangan
(yoki «faqat tasdiqlangan» belgilanmasa — oxirgi) mavzu paketidan, `content.js` dagi `tracking.mode` kurs paketi turiga qayta yoziladi.
SCORM 1.2, SCORM 2004 va xAPI (bir nechta activity).

**Deterministik zip:** yozuvlar alfavit tartibida, vaqt 1980-01-01, atributlar qotirilgan → bir xil kirish = bir xil sha256.
Manba, sozlama va pleyer fayllari o'zgarmasa, qayta yig'ish yangi versiya yaratmaydi (barmoq izi); «majburan» (`force`) — yangi versiya.

**Tekshiruv (`validate_zip`)** har yig'ishdan keyin: manifest o'qiladi va nomlar fazosi/`schemaversion` mos, identifikatorlar yagona va to'g'ri,
`item → resource` bog'langan, har bir `href`/`file` zip ichida va har bir fayl manifestda, ishga tushirish fayli bor, `content.js` shakli va JSON,
bloklar turi/`id`, asset yo'llari zip ichida, matn blokida xavfli HTML yo'q, xAPI `activity id` = `tracking.activity_id`, `tracking.mode` = paket turi,
mutlaq / `..` / `\` yo'llar yo'q, HTML'da YouTube'dan boshqa tashqi skript yo'q. Xato bo'lsa paket saqlanmaydi (500, sababi bilan).

**Cheklovlar:** bitta fayl ≤ 50 MB (tana oqim bilan sanaladi — `Content-Length`siz/chunked yuklash ham chegarada 413), paket ≤ 200 MB,
PPTX ≤ 200 slayd, matn ≤ 200 000 belgi; fayl nomlari zip ichida ASCII. **Zip/rasm bombalari:** .pptx/.docx/.xlsx tahlildan oldin markaziy katalog
bo'yicha tekshiriladi — ochilgan umumiy hajm ≤ 300 MB, bitta ichki fayl ≤ 150 MB, ≤ 5000 ichki fayl, 5 MB dan katta ichki fayl uchun siqish
nisbati ≤ 100:1 (aks holda 413). Rasm o'lchami dekodlashdan oldin (sarlavhadan) tekshiriladi: ≤ 40 Mpx — slayd rasmi va .docx ichidagi rasm
kattaroq bo'lsa 413, .pptx ichidagi katta rasm o'tkazib yuboriladi (slayd matn sifatida chiziladi). .pptx bir marta tahlil qilinadi.
Yuklab olish nomi: `ISFT_<fan>_<NN>_<tur>.zip` (kurs paketi — `ISFT_<fan>_kurs_<tur>.zip`; kirill va o'zbek apostrofi transliteratsiya qilinadi).

## Ko'rish (preview)

`GET /api/paket/packages/{id}/preview/<yo'l>` — saqlangan zip ichidan (ochilmaydi), faqat ko'lamdagi foydalanuvchiga. Yo'l tekshiriladi
(`..`, `/` bilan boshlanish, `\`, disk harfi, `%` — 400; zip'da yo'q — 404). Javobda qat'iy CSP: `default-src 'none'; script-src 'self';
style-src 'self' 'unsafe-inline'; img-src 'self' data: https://i.ytimg.com; font-src 'self' data:; media-src 'self'; connect-src 'none';
frame-src https://www.youtube-nocookie.com; object-src 'none'; base-uri 'none'; form-action 'none'; frame-ancestors 'self';
sandbox allow-scripts allow-popups allow-popups-to-escape-sandbox allow-forms`, `X-Content-Type-Options: nosniff`.
**Imzolangan yo'l:** sandbox'dagi hujjat opaque origin'da bo'lgani uchun uning ichki so'rovlari (content.js, player.js, rasmlar)
SameSite sessiya cookie'sini yubormaydi. Shuning uchun `/packages/{id}/preview/<yo'l>` cookie bilan tekshiriladi (ruxsat, ko'lam, audit, yo'l) va
`302` bilan `/api/paket/pv/<pid.uid.muddat.imzo>/<yo'l>` ga yo'naltiradi: HMAC-SHA256 (kalit `pk_meta.pv_key`), 2 soat, faqat shu paket va
foydalanuvchi uchun; har so'rovda foydalanuvchi faolligi, lavozimi va kurs ko'lami qayta tekshiriladi (soxta/muddati o'tgan — 403).
**Izolyatsiya:** `sandbox` da `allow-same-origin` yo'q — paket kontenti opaque origin («null») da ishlaydi: ilova cookie'si, `/api` va ota sahifa
DOM'iga kira olmaydi. UI modal ichidagi iframe'ga ham xuddi shu `sandbox` atributini qo'yadi; «Yangi oynada ochish» — server CSP'si orqali ham
sandbox'da. Pleyer LMS topilmasa ko'rish rejimida ishlaydi (shriftlar «null» origin'da ulanmaydi — tizim shrifti; localStorage yopiq bo'lsa
holat saqlanmaydi, xato chiqmaydi).

## Moodle'ga yuklash

1. Kursda tahrirlash rejimini yoqing → kerakli bo'limda «Faoliyat yoki resurs qo'shish» → **SCORM paketi**.
2. Nom yozing, paket faylini (.zip, ochmasdan) yuklang.
3. «Baholash»: «Eng yuqori urinish»; «Faoliyat yakunlanishi»: «Talab qilingan holat — o'tdi / tugallandi».
4. Saqlang va «Ko'rish» orqali tekshiring.

SCORM 2004 ni Moodle qisman qo'llaydi — LMS aniq talab qilmasa SCORM 1.2 tanlang. **xAPI** uchun LRS (Learning Record Store) yoki LMS plagini
kerak (Moodle'da tashqi LRS / xAPI plagini) — LMS turi aniq bo'lmaguncha SCORM 1.2 tavsiya etiladi.

## Avtomatik joylash

- **Video havolalar:** har qatorda bitta havola — 1-mavzudan ketma-ket; «N: havola» / «N. havola» / «N) havola» — aniq mavzuga (keyingilari N+1 dan davom etadi).
  `#` bilan boshlangan va bo'sh qatorlar e'tiborsiz. Avval «Tekshirish» (saqlanmaydi), keyin «Saqlash». Bir mavzuga ikki havola — oxirgisi olinadi.
- **Ommaviy yig'ish:** kursning manbasi bor mavzulari (ixtiyoriy — faqat to'liqlari), tanlangan yoki mavzu sozlamasidagi tur bo'yicha.

## Qamrov

Kafedra / o'qituvchi / kurs kesimida: mavzular, paketi yig'ilgan va tasdiqlangan mavzular, tasdiq kutayotganlar, manbasi to'liq mavzular
va har bir manba bo'yicha (matn, taqdimot, yaroqli video, tasdiqlangan test) soni. O'qituvchi — o'z kurslari, kafedra — o'z kafedrasi.

## «Mening vazifalarim»

`pending()` (app/pending.py → `paket` manbasi): bo'limga — «tasdiqni kutayotgan paketlar» (oxirgi versiyasi «tayyor» mavzular),
o'qituvchiga — «qaytarilgan paketlar» (oxirgi versiya qaytarish izohi bilan).

## Namuna ma'lumot

`init()` bir marta (`pk_meta.seed_v1`): «Mikroiqtisodiyot» 1-mavzu — sun'iy ma'ruza matni (reja, sarlavhalar, ro'yxat, jadval bilan) va
python-pptx bilan yaratilgan 4 slaydli taqdimot (izohlar va bitta rasm); 1–2-mavzular — namuna YouTube havolasi (`ISFTdemo001` — format to'g'ri,
video mavjud emas). Test — Test bank namunasidagi tasdiqlangan savollar. Pleyer mavjud bo'lsa 1-mavzu SCORM 1.2 paketi bir marta yig'iladi
(`pk_meta.demo_pkg`). UI'da «Namuna» bannerida aniq belgilangan. `SEED_VERSION` o'zgartirilmagan.

## API

| Usul | Yo'l | Kim |
|---|---|---|
| GET | `/meta`, `/coverage` | hamma (ruxsatlilar) |
| GET | `/courses?q=&department_id=&teacher_id=&only=started\|waiting\|empty&offset=&limit=` | bo'lim, kafedra, o'qituvchi (ko'lam bo'yicha) |
| GET | `/courses/{cid}`, `/courses/{cid}/topics/{no}` | bo'lim, kafedra, o'qituvchi |
| POST | `/courses/{cid}/topics/{no}/text` (fayl tanasi, `?name=`), `/text/paste` `{text}` | bo'lim, o'qituvchi |
| POST | `/courses/{cid}/topics/{no}/slides` (pptx/pdf/png/jpg), `/files` (qo'shimcha fayl) | bo'lim, o'qituvchi |
| POST | `/courses/{cid}/topics/{no}/video` `{url}` (bo'sh — olib tashlash), `/deck` `{deck_id}` | bo'lim, o'qituvchi |
| POST | `/courses/{cid}/topics/{no}/settings` `{mode, completion, mastery, quiz_n, shuffle, attempts, show_feedback, blocks, reset}` | bo'lim, o'qituvchi |
| POST | `/courses/{cid}/topics/{no}/build` `{mode?, force?}` | bo'lim, o'qituvchi |
| POST | `/courses/{cid}/bulk/videos` `{text, apply}`, `/courses/{cid}/bulk/build` `{topics?, mode?, only_complete}` | bo'lim, o'qituvchi |
| POST | `/courses/{cid}/course-package` `{mode, only_approved}` | bo'lim, o'qituvchi |
| GET | `/assets/{aid}` (asl fayl), POST `/assets/{aid}/delete` | ko'rish — bo'lim, kafedra, o'qituvchi; o'chirish — bo'lim, o'qituvchi |
| GET | `/packages/{pid}`, `/packages/{pid}/download`, `/packages/{pid}/preview/{yo'l}` (→ 302 imzolangan yo'lga) | bo'lim, kafedra, o'qituvchi |
| GET | `/pv/{token}/{yo'l}` (cookie'siz, imzolangan; ko'lam qayta tekshiriladi) | token egasi |
| POST | `/packages/{pid}/action` `{action: approve\|reject, note}` | bo'lim |
| POST | `/settings` (standart sozlamalar) | bo'lim |

## Testlar

`tests/test_paket.py`: har lavozim ruxsati va ko'lami (audit bilan); YouTube havolalari jadvali (watch, youtu.be, shorts, embed, live, nocookie,
`t=`/`start=`, noto'g'ri ID, pleylist, `javascript:`), ommaviy ro'yxat; HTML tozalash; matn → reja va HTML (Reja bo'limi, raqamli sarlavhalar,
ro'yxat, jadval, kirill); PPTX tahlili (testda yaratilgan, rasm va jadval bilan); HTTP orqali manbalar (matn, .docx, .pptx, noto'g'ri fayl,
video, avtomatik joylash, mavzu sozlamasi); bazaning nusxasida soxta pleyer bilan har bir turni yig'ish + `validate_zip` + manifestlar
(ElementTree), kontrakt maydonlari, deterministik zip, o'zgarishsiz qayta yig'ish, versiyalarni kesish, kurs paketi, validator salbiy holatlari,
XML qochirish, preview yo'li va CSP, yuklab olish nomi, tf me'yorlash; haqiqiy pleyer bilan yig'ilgan paket — brauzerda mock LMS ichida
(`tools/paket_build_check.js`: barcha bloklar, testga to'g'ri javob → SCORM 1.2 `passed`/100, SCORM 2004 `completed`/`passed`/100, xAPI/ko'rish
rejimi; 1366 va 390 px; konsol xatosiz; gorizontal aylantirishsiz); server orqali yig'ish, yuklab olish, preview, tasdiqlash/qaytarish,
«Mening vazifalarim»; qamrov — SQL bilan solishtirish.

## Ma'lum cheklovlar

- PPTX slaydlari rasmga aylantirilmaydi (LibreOffice yo'q): pleyer slaydni sarlavha + bandlar + slayddagi eng katta rasm sifatida chizadi;
  aniq ko'rinish kerak bo'lsa — PDF yoki slayd rasmlarini yuklang, asl `.pptx` doim yuklab olinadi. Animatsiya, SmartArt, diagrammalar, formulalar
  (OMML) matnga to'liq o'tmaydi.
- Matn bloki rasmlarni qo'llamaydi (Word ichidagi rasmlar olib tashlanadi); formulalar oddiy matn.
- Skaner qilingan PDF (matnsiz) ma'ruza matni sifatida rad etiladi.
- Video faqat havola (YouTube'da qoladi); YouTube bloklangan tarmoqda ko'rinmaydi. Video mavjudligi (private/o'chirilgan) tekshirilmaydi — faqat ID formati.
- SCORM XSD fayllari paketga qo'shilmaydi (Moodle talab qilmaydi); qat'iy XSD tekshiruvi qiladigan LMS uchun qo'shish kerak bo'lishi mumkin.
- xAPI paket LRS manzilini LMS'dan (launch parametrlari) oladi; LRS'siz LMS'da natija saqlanmaydi.
- Moodle'ga to'g'ridan-to'g'ri yuklash (API) yo'q — fayl eksporti; LMS'dagi natijalar ISFT Core'ga qaytib kelmaydi.
- Yig'ish sinxron (katta PPTX bilan bir necha soniya); ommaviy yig'ish uchun fon navbati keyinroq.
