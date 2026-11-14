# «Kurs muharriri» moduli

**Kod:** `app/kurs.py` (server), `static/kurs.js`, `static/kurs.css` (muharrir), `app/kurs_player/` (pleyer), `app/paket_player/lms.js` (LMS adapterlari — «Dars tayyorlash» pleyeri bilan umumiy)
**Testlar:** `tests/test_kurs.py`; brauzer — `tools/kurs_player_check.js` (pleyer, mock LMS) va `tools/kurs_editor_check.js` (muharrir), PW va CHROME berilganda test o'zi chaqiradi
**API:** `/api/kurs/*`
**Ruxsat resursi:** `rbac.KURS` (har bir so'rov audit jurnalida); bo'lim kaliti — `kurs` (`app/modules.py`, standart: yoqilgan)

## Nima uchun

Masofaviy ta'lim bo'limi darslarni Articulate Rise 360'da (yiliga ≈ $2000) bloklardan yig'adi: sarlavha, matn, rasm, akkordeon, kartochkalar,
«Continue» tugmasi, bilimni tekshirish savollari va yakuniy test → xAPI .zip → NEXTID (my.isft.uz). «Kurs muharriri» shu ishni ISFT Core ichida,
o'z uslubimizda bajaradi va Rise'da yig'ilgan kurslarni import qilib, sifatini tekshiradi. «Dars tayyorlash» (`docs/paket.md`) — shablon bo'yicha
avtomatik yig'ish (Word + taqdimot + video + Test bank); «Kurs muharriri» — erkin, blokma-blok yig'ish. Ikkalasi ham bitta manifest/zip/validator
(`app/paket.py`) va bitta LMS adapterlaridan (`lms.js`) foydalanadi.

## Kim nima qiladi

| Lavozim | Imkoniyat |
|---|---|
| `masofaviy`, `masofaviy_xodim` | barcha kurslar: yaratish, tahrirlash, import, eksport, versiyalar, **tasdiqlash / qaytarish** |
| `oqituvchi` | o'z kurslari (muallif yoki o'zi o'qitadigan masofaviy kursga bog'langan): yaratish, tahrirlash, import, eksport, **ko'rib chiqishga yuborish** |
| `rektor`, `prorektor_oquv` | faqat jamlangan sonlar (`GET /api/kurs/summary`): kurslar holati bo'yicha, darslar, bloklar, import, eksport — nomlar va tarkibsiz |
| boshqalar | 403 (audit) |

**2026-11: «Dars tayyorlash» bilan birlashdi** (`docs/dars.md`): alohida menyu bandi yo'q — muharrir «Dars tayyorlash» → «Fanlar» → dars →
«Muharrirda tahrirlash» orqali ochiladi; `go("kurs")` taxallus sifatida ishlaydi (menyuda «Dars tayyorlash» belgilanadi, sarlavha «Dars tayyorlash › Muharrir»),
bo'limlar kaliti `kurs` → `paket`. «Dars tayyorlash» sarlavhasidagi «Muharrir: barcha kurslar» — kurslar ro'yxati (Rise importi shu yerda).
Rahbariyat jamlangan sonlarni «Masofaviy ta'lim» sahifasidagi «Kurs muharriri» tugmasi orqali ko'radi.

`kafedra` — o'z kafedrasi fanlariga (`dl_courses.department_id`) bog'langan kurslarni **faqat ko'radi** (ro'yxat, kurs, dars, fayllar, ko'rish, sifat) va
blok izohlarini (to'xtatuvchi ham) qoldiradi; tahrirlash, eksport, tasdiqlash — 403. Muharrirda «Izohlar» paneli, blok sarlavhasidagi izoh belgisi,
«AI: hujjatdan dars» tugmasi va «Dars tayyorlash» bilan bog'lanish tasmasi (`course.dars` — fan, dars kodi, eksport uchun ustun manba) — `docs/dars.md`.
`POST /courses/{id}/action` — `submit` / `approve` ochiq to'xtatuvchi izohlar bo'lsa 409 (`override` — sabab bilan aylanib o'tish).

## Ma'lumot modeli (`ku_*`)

| Jadval | Mazmuni |
|---|---|
| `ku_courses` | nom, tavsif (HTML, tozalangan), muqova (`cover_asset`, `cover_alt`), urg'u rangi (xavfsiz palitradan — `PALETTE`, oq matn bilan kontrast ≥ 4,5), `settings` (yon menyu, dars soni, ketma-ket o'tish, qidiruv, yakunlash qoidasi, ko'rilgan ulush %, standart eksport turi), `labels` (pleyer yorliqlari — o'zbekcha), muallif, ixtiyoriy `dl_course_id`, holat `qoralama → korib_chiqishda → tasdiqlangan`, `rev`, tasdiq ma'lumoti, `src` (`''` / `rise` / `demo`), `import_report` |
| `ku_lessons` | tartib (`pos`), `uid` (pleyer/xAPI uchun barqaror), tur `blocks` \| `quiz`, test sozlamalari (`pass_pct`, `attempts`, `shuffle` — standart yoqilgan, `randomize`, `draw` — savollar bankidan N ta, `reveal` — always/pass/never, `intro`), o'z `rev` raqami |
| `ku_blocks` | tartib, `uid`, tur, JSON ma'lumot — **har tur serverda tozalanadi** (`clean_block`) |
| `ku_assets` | rasm (≤ 1600 px ga keltiriladi, metama'lumot tashlanadi, piksel bombasi — 413), video (.mp4/.webm, oqim bilan, `ISFT_CORE_PK_VIDEO_MB`), audio (.mp3/.m4a/.ogg/.wav, 50 MB), subtitr (.vtt/.srt → WebVTT), ilova (PDF/Word/PowerPoint/Excel/rasm, 50 MB). Tur birinchi baytlardan aniqlanadi; fayl `DATA_DIR/kurs/assets/<kurs>/<id>.<ext>` |
| `ku_versions` | kursning to'liq surati (JSON): qo'lda, avtomatik (avtosaqlashda ≤ 10 daqiqada bir marta; dars o'chirish, tiklash, tuzatish, ziddiyatda ustidan yozishdan oldin), import, tasdiq. Oxirgi 30 ta + tasdiqlanganlar saqlanadi |
| `ku_exports` | eksportlar (har tur bo'yicha oxirgi 3 ta), sha256, `validate_zip` natijasi |
| `ku_log` | kurs bo'yicha amallar jurnali (sahifada ko'rinadi); audit — `audit_log`, `resource='kurs'` |

Migratsiya — `migrate()` (idempotent, `init()` da). Namuna kurs (`src='demo'`) — barcha media bo'lmagan blok turlari bilan, bir marta yaratiladi.

## Blok turlari

| Toifa | Turlar |
|---|---|
| Matn | `heading` (H2/H3), `paragraph`, `heading_paragraph`, `quote` (iqtibos / urg'u), `list` (raqamli / belgili / belgilash), `table` |
| Media | `image` (markazda / to'liq kenglik / katta / tasma, izoh, **alt — bo'sh bo'lsa ogohlantirish**), `image_text` (chap/o'ng), `gallery` (to'r / karusel), `video` (fayl + poster + VTT subtitrlar yoki YouTube — nocookie), `audio` (+ transkript), `attachment`, `labeled_graphic` (rasm ustida belgilar) |
| Interaktiv | `accordion`, `tabs`, `flashcards` (to'r / dasta), `process`, `timeline`, `sorting` (2–6 toifa), `matching` |
| Bilimni tekshirish | `knowledge` — bitta javob, bir nechta javob (haqiqiy ko'p to'g'ri), to'g'ri/noto'g'ri, bo'sh joy; har variantga izoh, umumiy izoh, qayta urinish |
| Tuzilma | `divider` (chiziq / nuqtalar / bo'sh joy), `continue` (qolgan qismni yashiradi; talab: «faqat bosish» yoki «yuqoridagi mashqlar bajarilsin»), `button` (faqat http(s)) |
| Test darsi | `question` (bilimni tekshirish bilan bir xil sxema) — faqat `quiz` turidagi darsda |

Tozalash qoidalari: HTML maydonlari (`html`, ro'yxat bandlari, belgilar tavsifi) — `paket.sanitize` oq ro'yxati + rasm teglari olib tashlanadi;
oddiy matn maydonlari — boshqaruv belgilarisiz, uzunlik chegarasi bilan (pleyer ularni matn sifatida chiqaradi); asset havolasi — faqat shu
kursning mos turdagi fayli; noto'g'ri qiymatlar standartga keltiriladi (avtosaqlash yarim tayyor blokni ham saqlaydi). Tekshiruv (`block_issues`):
«xato» — eksport, yuborish va tasdiqlashni to'xtatadi (masalan, to'g'ri javobsiz savol, rasmsiz rasm bloki); «ogoh» — eslatma (alt yo'q, subtitr yo'q,
«bir nechta javob»da bitta to'g'ri).

## Muharrir (`static/kurs.js`)

Kurslar ro'yxati (holat bo'yicha, qidiruv) → kurs: chapda darslar (sudrab yoki ↑ ↓ bilan tartiblash, «+ Dars», «+ Test»), markazda dars — bloklar
orasidagi **«+»** → blok kutubxonasi (toifalar, qidiruv), joyida tahrirlash (boy matn paneli: qalin, kursiv, havola, ro'yxat), blok asboblari
(↑ ↓ sudrash, sozlamalar, nusxa, o'chirish → «Bekor qilish»), o'ngda tanlangan blok sozlamalari (1280 px dan tor ekranda — chiquvchi panel).
Test darsi: o'tish bali, urinishlar, savollar banki (N ta), aralashtirish, to'g'ri javobni ko'rsatish siyosati, «Test bankdan» (faqat tasdiqlangan).
Yuqorida: **Ko'rish** (kompyuter / planshet / telefon kengligi, saqlashdan keyin avtomatik yangilanadi), **Sifat**, **Versiyalar**, **Sozlamalar**,
**Eksport**, ko'rib chiqish tugmalari.

**Avtosaqlash va ziddiyat.** Har o'zgarishdan 1,2 s keyin dars to'liq saqlanadi (`POST /lessons/{id}` — `rev`). Server joriy `rev` bilan solishtiradi:
mos kelmasa **409** (kim, qachon) — muharrir ogohlantirish chiqaradi: «Oxirgi holatni yuklash» yoki «Mening nusxamni saqlash» (`force` — eski holat
avval versiyaga yoziladi). Kurs sozlamalari va darslar tartibi — kursning o'z `rev` raqami bilan.

**Holat.** O'qituvchi «Ko'rib chiqishga yuborish» (xatolar bo'lsa — 400 ro'yxat bilan) → bo'lim «Tasdiqlash» (tasdiqlangan versiya surati saqlanadi) yoki
«Qaytarish» (sabab majburiy). Tasdiqlangan kurs o'zgartirilsa — qoralamaga qaytadi; ko'rib chiqishdagi kursni o'qituvchi o'zgartirsa ham.

## Pleyer (`app/kurs_player/`)

O'zimizniki (Articulate kodi yo'q), tashqi skriptsiz (faqat YouTube nocookie iframe), oflayn ishlaydi. Muqova → yon menyu (darslar, bajarilganlik) →
dars sahifasi; «Davom etish» bosqichlari; ketma-ket o'tish; test (savollar banki, aralashtirish, urinishlar, o'tish bali, natija); kurs bo'yicha qidiruv;
telefon birinchi; klaviatura, alt matn, fokus belgisi, `prefers-reduced-motion`, qorong'i rejim; barcha yorliqlar — `content.labels` (o'zbekcha,
kurs sozlamasida o'zgartiriladi). `#lesson=<uid>&block=<id>` — muharrir ko'rish oynasi shu dars/blokni ochadi; `?preview=1` — «Ko'rish rejimi» banneri.

LMS: `lms.js` (paket pleyeri bilan umumiy) — SCORM 1.2, SCORM 2004 4-nashr, xAPI (launch parametrlari; dars faoliyatlari
`<kurs>/lesson/<uid>`, savollar `<kurs>/lesson/<uid>/q/<id>`), LMS'siz rejim (localStorage). Yakunlash qoidasi: darslar ko'rilganda (≥ N %),
test topshirilganda, ikkalasi yoki biri. Baholash qoidasi serverdagi `grade()` / `norm_answer()` bilan bir xil (bo'sh joy: katta-kichik harf, apostrof
variantlari, chetdagi tinish belgilari).

## Eksport

`POST /api/kurs/courses/{id}/export {mode}` — `xapi` (NEXTID, standart), `scorm12`, `scorm2004`, `none` (oddiy HTML). Zip: pleyer + `lms.js` + shriftlar +
`content.js` (`window.KURS = {...};`) + `content.json` + `assets/…` + manifest (`paket.manifest_scorm12/2004`; `tincan.xml` — kurs (launch), har dars
(module / assessment), har test savoli va bilimni tekshirish bloki (cmi.interaction: turi, variantlar, to'g'ri javob naqshlari)). Deterministik
(qotirilgan vaqt, tartiblangan yozuvlar — bir xil kurs → bir xil sha256). Har eksportdan keyin `paket.validate_zip` (window.KURS tekshiruvchisi
`paket.CONTENT_KINDS` ga ro'yxatdan o'tadi: xavfsiz HTML, yo'llar, fayllar mavjudligi, YouTube ID, to'g'ri javoblar; tincan.xml ichki faoliyatlari
kurs faoliyatiga tegishli bo'lishi kerak). SCORM `masteryscore` — yakunlash qoidasi testni o'z ichiga olsa, birinchi testning o'tish bali.

## Ko'rish (preview)

`GET /courses/{id}/preview-url` → `/api/kurs/pv/<kurs.foydalanuvchi.muddat.imzo>/index.html?preview=1` (HMAC, 2 soat). Kontent — joriy (avtosaqlangan)
holat, `Cache-Control: no-store`; qat'iy CSP (`paket.PREVIEW_CSP`: sandbox, `script-src 'self'`); media — HTTP Range bilan.

## Rise 360 importi

`POST /api/kurs/import/rise?name=…` (tana — .zip; xAPI / SCORM / Web eksporti). Tana diskka oqim bilan (`ISFT_CORE_KURS_IMPORT_MB`, standart 400 MB);
keyin zip markaziy katalogi tekshiriladi: fayllar soni ≤ 5000, ochilgan hajm ≤ 1 GB (bitta fayl ≤ 400 MB), siqish nisbati ≤ 100 (2 MB dan katta fayllar —
**zip bombasi**), xavfli yo'llar (mutlaq, `..`, `\`, disk harfi, boshqaruv belgilari) — 400. Kurs ma'lumoti `scormcontent/runtime-data.js`
(`__jsonp("runtime-data.js","<base64>")`; eski eksportlarda `index.html` dagi `deserialize("…")`) dan o'qiladi; arxivdan hech narsa diskka nomi bilan
chiqarilmaydi (faqat kerakli a'zolar o'qiladi).

Moslash: matn (sarlavha, paragraf, sarlavha+paragraf, impact/quote), ro'yxat, rasm (hero, banner, full, centered, text aside → `image_text`), galereya,
multimedia (video/audio fayl, YouTube embed), akkordeon, yorliqlar, kartochkalar, jarayon (intro → steps → summary), vaqt chizig'i, saralash (piles),
belgili rasm, bilimni tekshirish (MULTIPLE_CHOICE, MULTIPLE_RESPONSE, FILL_IN_THE_BLANK, MATCHING), continue / divider, tugmalar; test darsi (o'tish bali,
urinishlar = `retryCount + 1`, aralashtirish, savollar tartibi, javoblarni ko'rsatish, tavsif → kirish matni); muqova, urg'u rangi (palitradagi eng yaqin
rang), navigatsiya sozlamalari. Noma'lum blok — **«import qilinmadi: <tur/variant>»** sarlavhali matn bloki (ichidagi matnlar bilan); `section`
turidagi darslar (bo'lim sarlavhalari) o'tkaziladi. Hisobot: darslar, testlar, savollar, bloklar (bizning tur bo'yicha va Rise tur/varianti bo'yicha),
import qilinmaganlar, rasmlar (import / topilmadi / o'qilmadi).

Haqiqiy namuna («Xalqaro munosabatlar tarixi va nazariyalari», xAPI): 13 dars + 1 test (8 savol), 552 blok, 48 rasm, import qilinmagan 0, ≈ 0,5 s.

## Sifat hisoboti va tuzatishlar

`GET /courses/{id}/quality` (istalgan kurs; importdan keyin avtomatik ko'rsatiladi):

- bilimni tekshirish va test savollarida **to'g'ri javob o'rni** taqsimoti (A/B/C/D) — biri > 50 % bo'lsa xato; **to'g'ri javob eng uzun** (yoki teng eng uzun) variant — > 50 % bo'lsa ogohlantirish;
- **alt matnsiz rasmlar** (rasm, rasm+matn, galereya, belgili rasm) va muqova;
- **inglizcha qolgan yorliqlar** (Continue, Quiz, «Complete the content above…», «Expand each…», «Test your understanding…» va h.k.);
- **test qamrovi darslar bo'yicha** — savol (+ to'g'ri javob) matnining so'zlari darslar matni bilan IDF og'irligida solishtiriladi (taxminiy);
- **«bir nechta javob» savolida bitta to'g'ri javob**; testda aralashtirish o'chiq.

Bir bosishli tuzatishlar (`POST /courses/{id}/fix`, avval versiya saqlanadi): `shuffle` — to'g'ri javob o'rinlari aylanma tartibda teng taqsimlanadi
(deterministik), testlarda aralashtirish yoqiladi; `labels` — standart yorliqlar o'zbekchaga («Continue» → «Davom etish», «Quiz» → «Yakuniy test»,
eslatma, «Expand each tab…» → «Har bir yorliqni ochib…»); `mr_single` — «bir nechta javob» → «bitta javob». «Eng uzun variant» va alt matn — qo'lda.

Haqiqiy namunada: 87/104 to'g'ri javob «B» o'rnida, 88/104 eng uzun, 47/47 rasm alt'siz (+ muqova), 29 ta inglizcha yorliq, test 1–5-darslar ichida
(6–13-darslar savolsiz), 2 ta «bir nechta javob»da bitta to'g'ri. `shuffle` dan keyin — A/B/C/D: 26/26/26/26; `labels` dan keyin — 0 ta inglizcha.

## API (qisqacha)

| Metod | Yo'l | Kim |
|---|---|---|
| GET | `/meta`, `/summary` | hamma ruxsatli (rahbariyat — `summary`) |
| GET/POST | `/courses`, `/courses/{id}`, `/courses/{id}/settings`, `/courses/{id}/delete` | mualliflar |
| POST | `/courses/{id}/lessons`, `/courses/{id}/order`, `/lessons/{id}` (saqlash), `/lessons/{id}/delete`, `/lessons/{id}/duplicate` | mualliflar |
| GET/POST | `/courses/{id}/assets` (`?kind=image\|video\|audio\|vtt\|file`), `/assets/{id}` | mualliflar |
| GET/POST | `/courses/{id}/versions`, `/courses/{id}/versions/{v}/restore` | mualliflar |
| POST | `/courses/{id}/action` — `submit` (mualliflar), `approve` / `return` (bo'lim) | |
| POST/GET | `/courses/{id}/export`, `/exports/{id}/download`, `/courses/{id}/issues` | mualliflar |
| GET | `/courses/{id}/preview-url`, `/pv/{token}/{path}` | mualliflar (imzolangan yo'l) |
| GET/POST | `/courses/{id}/quality`, `/courses/{id}/fix`, `/import/rise` | mualliflar |
| GET/POST | `/testbank`, `/testbank/convert` | mualliflar (o'qituvchi — o'z fanlari) |

## Cheklovlar

- Sudrab tashlash — sichqoncha bilan; klaviaturada ↑ ↓ tugmalari. Boy matn — `document.execCommand` (oddiy formatlash yetarli).
- Belgili rasm belgilari muharrirda rasmga bosib qo'yiladi/ko'chiriladi (sudrash yo'q).
- Rise'dagi «scenario», «chart», «code», «storyline» bloklari import qilinmaydi (izohli matn bloki qo'yiladi); Rise kurs bo'limlari (section) — o'tkaziladi.
- Test qamrovi — matn o'xshashligiga asoslangan taxmin.
