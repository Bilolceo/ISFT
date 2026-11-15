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

Kurslar ro'yxati (holat bo'yicha, qidiruv — kurs, muallif yoki fan nomi; fan tanlash) — «Dars tayyorlash» bilan bog'langan kurslar (`ds_links`: fan skeleti,
paketdan o'tkazish) **fan bo'yicha yig'iladigan guruhlarda** (sarlavhada kurslar soni va holatlar bo'yicha sonlar; ichida dars kodi tartibida — L1..Ln, A1..),
bog'lanmaganlari — **«Mustaqil kurslar»** bo'limida; guruh ochiq/yopiqligi har foydalanuvchi uchun brauzerda (`localStorage`) eslab qolinadi, filtr
qo'llanganda guruhlar ochiladi (`GET /courses?q&status&fan` → `items`, `groups`, `standalone`, `fans`; ko'lam o'zgarmagan) → kurs: chapda darslar (sudrab yoki ↑ ↓ bilan tartiblash, «+ Dars», «+ Test»), markazda dars — bloklar
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
telefon birinchi; klaviatura, alt matn, fokus belgisi, `prefers-reduced-motion`, qorong'i rejim, qulaylik paneli va «Tinglash» (pastda «Qulaylik»); barcha yorliqlar — `content.labels` (o'zbekcha,
kurs sozlamasida o'zgartiriladi). `#lesson=<uid>&block=<id>` — muharrir ko'rish oynasi shu dars/blokni ochadi; `?preview=1` — «Ko'rish rejimi» banneri.

LMS: `lms.js` (paket pleyeri bilan umumiy) — SCORM 1.2, SCORM 2004 4-nashr, xAPI (launch parametrlari; dars faoliyatlari
`<kurs>/lesson/<uid>`, savollar `<kurs>/lesson/<uid>/q/<id>`), LMS'siz rejim (localStorage). Yakunlash qoidasi: darslar ko'rilganda (≥ N %),
test topshirilganda, ikkalasi yoki biri. Baholash qoidasi serverdagi `grade()` / `norm_answer()` bilan bir xil (bo'sh joy: katta-kichik harf, apostrof
variantlari, chetdagi tinish belgilari).

ISFT Core'ning o'z LRS'i va NEXTID'ga bog'liq bo'lmagan ishga tushirish yo'li (talabaning shaxsiy havolasi → eksport qilingan kurs xAPI launch
parametrlari bilan), shuningdek savollar tahlilidan «Muharrirda ochish» (dars + blok) — `docs/lrs.md`.

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

## Qulaylik (accessibility) — sifat hisobotida, pleyerda, subtitrlar

Tadqiqot tavsiyasi №11 (UNED: ReadSpeaker / Brickfield). Uch qism: muallif uchun tekshiruv, talaba uchun pleyer imkoniyatlari, subtitrlar.

**1. Sifat hisobotidagi «Qulaylik» qoidalari** (`a11y_from`, `GET /courses/{id}/quality` → `a11y: {rules, passed, total, contrast, youtube}`;
muammolar `issues` ro'yxatida ham — `group: "a11y"`, `key`). Har qoida: qayerda (`where`, «2. Dars · 5-blok (Jadval)»), qanday tuzatiladi (`hint`),
xavfsiz bo'lsa — bir bosishli tuzatish (`fix`, avval versiya saqlanadi):

| Qoida (`key`) | Nima tekshiriladi | Tuzatish |
|---|---|---|
| `alt` | rasm, rasm+matn, galereya, belgili rasm va muqovada alt matn | qo'lda |
| `contrast` | urg'u rangi: oq matn (tugma), havola oq/kulrang fonda, qorong'i rejim havolasi (#171a21) — WCAG ≥ 4,5:1 | `accent` → standart rang |
| `headings` | sarlavha darajasi sakramaydi (dars nomi — h1; H2'siz H3; HTML ichidagi h2–h4 ham) | `headings` — sakragan sarlavha bloki bir pog'ona yuqoriga |
| `links` | havola matni: «bu yerga bosing», «batafsil», «здесь», yalang'och URL; tugma yorlig'i | qo'lda |
| `tables` | jadval blokida sarlavha qatori; matn ichidagi `<table>` da `<th>` | `table_header` — birinchi qator sarlavha |
| `captions` | fayl-videoda subtitr (VTT) | «Subtitr yaratish (Whisper)» — bo'lim xodimi (pastda) yoki .vtt yuklash |
| `transcript` | audio blokida matn (transkript) | qo'lda |
| `long_text` | ketma-ket matn bloklari sarlavhasiz > 300 so'z (`A11Y_LONG_WORDS`) | qo'lda (H2/H3 yoki akkordeon) |
| `kbd` | interaktiv bloklar bor, lekin pleyerda klaviatura ko'rsatmasi o'chiq | `kbd_hints` — kurs sozlamasi yoqiladi |
| `pdf` | PDF ilovada matn qatlami (pypdf; skaner — faqat rasm) — natija fayl meta'sida keshlanadi | qo'lda (OCR qilingan / asl fayl) |

Palitradagi barcha urg'u ranglari kontrastdan o'tadi (test bilan qotirilgan); `contrast` qoidasi palitradan tashqari rang (eski baza, qo'lda
o'zgartirish) uchun himoya. Muharrirda: «Qulaylik (a11y) N/10» ko'rsatkichi, qoidalar jadvali (holat, joylar, izoh), tuzatish tugmalari.

**2. Pleyer** (`app/kurs_player`, `app/paket_player`): umumiy modul `app/paket_player/a11y.js` (`window.ISFTA11y`; kurs eksportiga `lms.js` kabi
qo'shiladi; tashqi so'rov va tashqi shrift yo'q):

- **«Aa» qulaylik paneli** (yuqori panelda): matn o'lchami A− / A+ (90–160 %, `<html>` font-size — barcha `rem` o'lchamlar bilan), **yuqori
  kontrast** (oq/qora, qorong'i rejimda qora/sariq; havolalar tagiga chiziq, qalin chegaralar, qalin fokus), **o'qish uchun qulay shrift**
  (tizim shriftlari Verdana/Tahoma…, keng harf va so'z oralig'i, kursivsiz), **harakatni kamaytirish** (`prefers-reduced-motion` bilan birga).
  Sozlamalar `localStorage['isft-a11y']` da — har murojaat try/catch: ko'rish oynasi (sandbox) va maxfiy oynada ishlaydi, faqat eslab qolinmaydi
  (panelda izoh). Esc — panel yopiladi, fokus «Aa» ga qaytadi.
- **«Tinglash»** (matn, sarlavha+matn, iqtibos, ro'yxat, rasm+matn, vaqt chizig'i bloklari; paket pleyerida — matn qadamlari): brauzerning
  Web Speech API'si (`speechSynthesis`), tashqi xizmatsiz. Ovoz: uz-UZ → uz-* → ru-RU → ru-* → standart (xabarda qaysi ovoz); API yo'q
  bo'lsa yoki qurilmada ovoz yo'q bo'lsa — tushunarli xabar. O'qilayotgan blok ajratiladi (`.reading`), qayta bosish — to'xtatish; matn
  gaplarga bo'lib o'qiladi; dars almashganda o'qish to'xtaydi.
- **Klaviatura va ARIA** (barcha blok turlari): skip-link («Asosiy mazmunga o'tish»), akkordeon (`aria-expanded`, panel `role=region` +
  `aria-labelledby`), yorliqlar (← → Home End, roving tabindex), kartochkalar (Enter/Bo'sh joy, orqa tomon `aria-hidden` almashadi),
  saralash (faqat klaviatura bilan: element → ««Toifa» toifasiga joylash»; qayta chizilganda fokus yo'qolmaydi), moslashtirish (`<label for>`),
  jarayon (oxirgi qadamda fokus blok ichida qoladi), belgili rasm (`aria-controls` panelga), test (fieldset/legend, label). **Sarlavhalar
  ierarxiyasi**: bloklar ichidagi sarlavhalar (akkordeon bandi, jarayon qadami, video nomi…) oldingi muallif sarlavhasidan bir daraja pastda
  (h1 → h3 sakrashi yo'q). `kbd_hints` yoqilsa — interaktiv blok boshida qisqa klaviatura ko'rsatmasi.

**3. Subtitrlar**

- **Yozuvlar muharriri**: video blokida har subtitr yonida «Tahrirlash» → yozuvlar ro'yxati (boshlanish, tugash — `daqiqa:soniya.ms`, matn;
  qo'shish/o'chirish). `GET /assets/{id}/cues` → `[{start, end, text}]`; `POST /courses/{id}/vtt {asset?, lang, cues}` → `paket.to_vtt` bilan
  tekshiriladi va **yangi** «vtt» fayl (eski fayl o'zgarmaydi — versiyalar unga ishora qiladi); muharrir blokdagi havolani almashtiradi.
- **«Subtitr yaratish (Whisper)»** — faqat `masofaviy`, `masofaviy_xodim` (`POST /courses/{id}/captions {asset, lang}`; bir video + til uchun
  bitta faol vazifa; `GET /courses/{id}/captions` — holat, `POST /captions/{id}/cancel`). Navbat `ku_caption_jobs`. Bajaruvchi — **studiyaning
  montaj ishchisi** (`tools/montaj`, o'sha `ISFT_CORE_WORKER_TOKEN`, `X-Worker-Token`): montaj navbati bo'sh bo'lganda
  `POST /api/montaj/kurs-captions/claim` → `{job_id, lease, lang, media_url}` | 204; `GET …/{id}/media` (token, Range);
  `POST …/{id}/progress {stage, pct}` (lease uzayadi, `X-Worker-Lease`); `POST …/{id}/result` (tana — WebVTT) | `…/fail {error}`.
  Ishchi: video → 16 kHz WAV (ffmpeg) → faster-whisper (so'z vaqtlari) → 2 qator × 42 belgi bo'laklar → WebVTT. Server natijani tekshiradi,
  «vtt» fayl (`meta.auto = "whisper"`) sifatida saqlaydi va shu videoni ishlatgan barcha bloklarga (shu tilda subtitr bo'lmasa) «O'zbekcha
  (avto)» sifatida ulaydi; dars `rev` oshadi (ochiq muharrir ziddiyatni ko'radi). Lease muddati 2 soat, 3 urinish. Eski server (404) —
  ishchi subtitr navbatini so'ramaydi. Muallif avtomatik subtitrni «Tahrirlash» orqali tekshiradi.
- **Qo'lda yo'l** (ishchi o'chiq — `ISFT_CORE_WORKER_TOKEN` yo'q, claim 503): videoni montaj kompyuterida `tools/montaj` (yoki istalgan Whisper
  vositasi, masalan `whisper video.mp4 --language uz --output_format vtt`) bilan .vtt ga aylantiring → video blokida «Subtitr yuklash» →
  «Tahrirlash» bilan tekshiring. Navbatdagi vazifa ishchi yoqilganda bajariladi yoki «bekor» qilinadi.

Testlar: `tests/test_kurs.py` 13a–13d (har qoida uchun muammoli va to'g'ri fixture, tuzatishlar, VTT muharriri, navbat ruxsatlari, ishchi
API — bazaning nusxasida token bilan), `tools/kurs_player_check.js` «Qulaylik» bo'limlari (axe uslubidagi tekshiruvlar: nomlar, ARIA
havolalari, id takrori, sarlavhalar, Tab bilan har elementga yetish, har blok turi klaviaturada, panel va localStorage, sandbox,
reduced-motion, TTS — API yo'q / uz / ru / standart / ovoz yo'q), `tools/kurs_editor_check.js` (qulaylik jadvali, yozuvlar muharriri),
`tools/paket_player_check.js` (panel, TTS), `tools/montaj/tests/test_captions_worker.py` (ishchi tomoni, Whisper o'rniga soxta natija).

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
| GET / POST | `/assets/{id}/cues`, `/courses/{id}/vtt` | o'qish — kurs ko'ruvchilari; yozish — mualliflar |
| GET / POST | `/courses/{id}/captions`, `/captions/{id}/cancel` | ro'yxat — kurs ko'ruvchilari; navbatga qo'yish / bekor — `masofaviy`, `masofaviy_xodim` |
| POST/GET | `/api/montaj/kurs-captions/claim`, `/{id}/media`, `/{id}/progress`, `/{id}/result`, `/{id}/fail` | montaj ishchisi (`X-Worker-Token`) |

## Cheklovlar

- Sudrab tashlash — sichqoncha bilan; klaviaturada ↑ ↓ tugmalari. Boy matn — `document.execCommand` (oddiy formatlash yetarli).
- Belgili rasm belgilari muharrirda rasmga bosib qo'yiladi/ko'chiriladi (sudrash yo'q).
- Rise'dagi «scenario», «chart», «code», «storyline» bloklari import qilinmaydi (izohli matn bloki qo'yiladi); Rise kurs bo'limlari (section) — o'tkaziladi.
- Test qamrovi — matn o'xshashligiga asoslangan taxmin.
