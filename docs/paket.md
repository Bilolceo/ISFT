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

Institut LMS'i — **NEXTID.LMS** (my.isft.uz, NextBrain; Moodle emas). Har fanda «Articulate» yorlig'i: darslar «L1-1-dars: …» (ma'ruza) va
«A1- AMALIY MASHG'ULOT: …» (amaliy) nomi bilan, har biri Articulate Rise 360 xAPI eksporti (zip ildizi: `index.html`, `tincan.xml`, …), iframe'da
**launch parametrlarisiz** ochiladi. Shuning uchun standart tur — **xAPI** (NEXTID); boshqa LMS uchun **SCORM 1.2**, **SCORM 2004 4-nashr** va
oddiy HTML (LMS'siz) ham qoladi. Kafedra shabloni (Rise «qadamlar» rejimi): VIDEODARS → MA'RUZA MATNI («1-MAVZU: …» + Reja, matn, rasmlar
«1.1-rasm. …», jadvallar, adabiyotlar) → DARS TAQDIMOTI (slayd rasmlari galereyasi) → «Darsni to'liq o'zlashtirdingizmi?».

**Rise 360 (kontrakt v3).** Bo'lim darsni Rise 360'da qo'lda qanday yig'ishini (video yozuvi) ko'rib, quyidagilar qo'shildi: **muqova** (fon rasmi +
ISFT logotipi + «L1-1-dars: …» + muallif), **video fayl** (.mp4 / .webm) subtitr va poster bilan, slayd **izohi va audiosi**, bo'lim
**«MASHQ VA TOPSHIRIQLAR»** — kartochkalar, test ichida moslashtirish va saralash, **topshiriq** (o'qituvchi rasmi + «Quyidagi topshiriqni bajarib PDF
shaklda LMS platformasiga joylang» + Word'dagi «Savollar» ro'yxati). Tafsilotlar — «Rise 360 (v3)» va «Rise 360 bilan taqqoslash» bo'limlarida.

## Kim nimani ko'radi

| Lavozim | Ko'rinish | Amallar |
|---|---|---|
| Masofaviy ta'lim bo'limi boshlig'i (`masofaviy`) | Barcha kurslar | Manbalar, yig'ish, ko'rish, yuklab olish, tasdiqlash / qaytarish, umumiy sozlamalar, avtomatik joylash |
| Bo'lim xodimi (`masofaviy_xodim`) | Barcha kurslar | Boshliq bilan bir xil |
| O'qituvchi | O'z kurslari (`dl_courses.teacher_id`) | Manba yuklash, video, mavzu sozlamasi, yig'ish, ko'rish, yuklab olish, kurs paketi; mashqlar, topshiriq, muqova, slayd audiosi |
| Kafedra mudiri | O'z kafedrasi kurslari | Ko'rish va yuklab olish (mashqlarni ham faqat ko'radi) |
| Rektor, o'quv ishlari prorektori | Faqat jamlangan qamrov (jumladan «mashqli darslar» soni) | — (matn, mashqlar, paket mazmuni va yuklab olish yo'q) |

Boshqa lavozimlar — 403. Begona kursga murojaat ham 403 va audit jurnaliga yoziladi.

## Kurslar, mavzular va darslar (L / A)

Kurs ro'yxati qurilmadi: Masofaviy ta'lim modulidagi `dl_courses` va `dl_items` (mavzu nomlari) **faqat o'qiladi** — Test bank bilan bir xil.

**Darslar.** Kursda standart **L1..Ln** (ma'ruza; n — kurs mavzulari soni, nomi `dl_items`'dan). Bo'lim/o'qituvchi «Darslar ro'yxati (NEXTID)»
orqali NEXTID nomlarini joylashtiradi (har qatorda bitta; avval «Tekshirish», keyin «Saqlash»):

| Qator | Dars | Ichki kalit |
|---|---|---|
| `L1-1-dars: AXBOROT TEXNOLOGIYALARI` | ma'ruza L1 (nomi almashtiriladi) | 1 |
| `A1- AMALIY MASHG'ULOT: Excel bilan ishlash (2-mavzu)` | amaliy A1, 2-mavzuga bog'langan | 1001 |
| `A2- Amaliy: Word hujjatlari` | amaliy A2 | 1002 |
| `S1 …`, `Lab1 …`, `MT1 …` | seminar, laboratoriya ishi, mustaqil ta'lim | 2001, 3001, 4001 |

Mavzu bog'lanishi (ixtiyoriy) — oxirida `(3-mavzu)`, `[3]`, ` | 3` yoki ` # 3`. Bir kod ikki marta — oxirgisi olinadi; `#` va bo'sh qatorlar e'tiborsiz.
**Ichki kalit** (`pk_*.topic_no` ustuni, API'dagi `/topics/{no}`) = asos + raqam: L — 0, A — 1000, S — 2000, Lab — 3000, MT — 4000. Shuning uchun
eski mavzu paketlari o'zgarishsiz L darslar (kalit = mavzu raqami, `activity_id` ham o'sha). Qo'shilgan dars o'chirilsa (standart L emas) —
ro'yxatdan yashiriladi, manba va paketlari qoladi. Test bank (matn, test) va kontent monitoringi videosi — faqat L darslar uchun zaxira manba.
UI darslarni turi bo'yicha guruhlaydi (Ma'ruzalar, Amaliy mashg'ulotlar, …).

## Manbalar va ustuvorlik

| Blok | Manba (ustuvorlik tartibida) |
|---|---|
| Ma'ruza matni | 1) shu yerda yuklangan `.docx` (matn + rasmlar izohi bilan + jadvallar) / `.pdf` / `.txt` (faqat matn) yoki joylashtirilgan matn (`pk_assets`, `purpose='matn'`); 2) darsning **manba mavzusi** bo'yicha — Test bankdagi mavzu matni (`tb_sources`, oxirgisi). Manba mavzusi (`source_topic()`): darsga mavzu bog'langan bo'lsa (`topic_ref`, masalan «A1 … (2-mavzu)») — o'sha mavzu; aks holda L dars — o'z raqami; bog'lanmagan A/S/Lab/MT — zaxira manba yo'q (video va test uchun ham shu qoida). Asl `.docx`/`.pdf` — «Fayl» bloki sifatida ham qo'shiladi |
| Rasmlar | Word ichidagi rasmlar (hujjat tartibida) va qo'lda yuklangan rasmlar (`purpose='rasm'`, nomi `<sha256[:20]>.png/jpg`, ≤ 1600 px) — matnda `<figure>` |
| Adabiyotlar | matndagi «Foydalanilgan adabiyotlar (ro'yxati)» / «Adabiyotlar» / «Asosiy adabiyotlar» / «Литература» bo'limi → `refs` bloki (matndan olinadi). «Reja:» ro'yxati ichidagi band (masalan «3. Foydalanilgan adabiyotlar») — reja bandi, adabiyotlar sarlavhasi emas. Ro'yxat tugaydi: sarlavha, rasm/jadval, ma'lum bo'lim («Nazorat savollari», «Savollar», «Topshiriqlar», «Glossariy», «Mustaqil ish» …), sarlavhasimon qisqa «…:» qatori yoki raqamli ro'yxatdan keyin bo'sh qator + oddiy matn; qolgani matnga (asosiy matndan keyin) qaytadi. «Qo'shimcha adabiyotlar» — o'sha ro'yxat davomi |
| Asosiy xulosalar | o'qituvchi yozgan yoki «AI: asosiy xulosalar» qoralamasidan **tasdiqlangan** bandlar (`pk_topics.keypoints`) |
| Reja | Matndagi «Reja:» / «Режа:» / «План:» bo'limi (raqamli, belgili yoki oddiy qatorlar; bir qatorda «Reja: 1. … 2. …»); bo'lmasa — 1-darajali sarlavhalar (kamida 2 ta) |
| Taqdimot | 1) yuklangan `.pdf` — har sahifa pypdfium2 bilan ~1600 px JPEG'ga chiziladi (`assets/slides/pN.jpg`, ≤ 120 sahifa) → `display:"images"` (aniq ko'rinish); 2) `.pptx` (python-pptx: sarlavha, bandlar, jadval qatorlari, izohlar, har slayddagi eng katta rasm → `assets/slides/sN.png`); 3) «Taqdimot» modulidagi deck (`pres_decks`); 4) PNG/JPG slayd rasmlari to'plami (nom bo'yicha tartib). `.pptx` va PDF ikkalasi bo'lsa — **eng oxirgi yuklangani hal qiladi**: PDF `.pptx` dan keyin yuklangan bo'lsa — PDF rasmlari (slaydlar soni teng bo'lsa sarlavha/izohlar `.pptx` dan), asl `.pptx` yuklab olish uchun (`file`), PDF — `pdf`; `.pptx` PDF'dan keyin yuklangan bo'lsa — PDF eskirgan hisoblanadi va paketga kirmaydi (`.pptx` matni/rasmlari). Yangi taqdimot yuklanganda shu darsning o'sha turdagi eski taqdimotlari «almashtirildi» (`pk_assets.deleted=2`, ro'yxatda ko'rinmaydi, fayli diskda qoladi). `display` — hamma slaydda rasm bo'lsa `images`, aks holda `text`. Eski `.ppt` qabul qilinmaydi. **O'qituvchilarga:** PowerPoint'da «Fayl → Saqlash → PDF» qilib PDF'ni ham yuklang — `.pptx` dan **keyin** |
| Video | 1) shu yerda kiritilgan havola (`pk_topics.video_url`, «Avtomatik joylash» ham shu yerga yozadi); 2) darsning manba mavzusi bo'yicha — kontent monitoringidagi videodars havolasi (`dl_items`, `kind='video'`). YouTube → video bloki; boshqa http(s) havola → «Videodars» matn bloki (havola bilan) |
| Test | darsning manba mavzusi bo'yicha — Test bankdagi **tasdiqlangan** savollar (`tb_questions`). Hammasi yoki N ta (tanlov deterministik: manba o'zgarmasa — o'sha savollar). To'g'ri/noto'g'ri savol har doim `["To'g'ri","Noto'g'ri"]`, `[0]` — to'g'ri (bazada qanday saqlangan bo'lmasin) |
| Qo'shimcha fayllar | `.pdf`, `.docx`, `.pptx`, `.xlsx`, `.png`, `.jpg` (`purpose='fayl'`) |
| Video fayl (v3) | `.mp4` / `.webm` (`purpose='video'`), subtitrlar `.vtt` / `.srt` (`subs`), poster (`poster`). Fayl ham, YouTube havola ham bo'lsa — sozlama `video_source` (standart: fayl) |
| Muqova (v3) | rasm: dars (`purpose='muqova'`, `topic_no` = dars) > kurs (`topic_no=0`) > bo'lim standarti (`course_id=0`); muallif — kurs o'qituvchisi F.I.Sh. yoki dars bo'yicha tahrirlangani |
| Mashqlar (v3) | `pk_exercises` — o'qituvchi/bo'lim qo'lda yoki «AI: mashqlar» qoralamasidan; faqat `status='faol'` |
| Topshiriq (v3) | savollar: qo'lda kiritilgan (`pk_topics.extra.questions`) > ma'ruza matnidagi «Savollar» bo'limi; matn/imzo — sozlamadan; o'qituvchi rasmi — kurs (`purpose='avatar'`) |

**Tayyorgarlik** (UI'dagi M / T / V / S belgilar): matn, taqdimot, video (havola **yoki fayl**), test (Test bank savollari **yoki** moslashtirish /
saralash mashqi). Paket **«tayyor»** — sozlamada yoqilgan shu to'rt blokning hammasi bor bo'lsa; aks holda **«qoralama»**. Muqova, mashqlar va
topshiriq «tayyor» uchun shart emas. Matn manbasi **faqat topshiriqlar ro'yxatidan** iborat bo'lsa (amaliy mashg'ulot: Word'da faqat «Topshiriqlar»)
ro'yxat topshiriq blokiga o'tadi, matn bloki chiqmaydi — bu «matn bor» deb hisoblanadi (`ready.text.only_assignment`). Yig'ish uchun kamida bitta
kontent bloki (matn, taqdimot, video, fayl, topshiriq, test yoki kartochkalar) kerak. Dars panelidagi ro'yxat:
video, matn, reja («1-MAVZU: …» sarlavhasi bilan), rasmlar va jadvallar soni, adabiyotlar, asosiy xulosalar (tasdiqlangan / qoralama), taqdimot
(manba, slaydlar soni, galereya yoki matnli; slayd izohlari va audio), test, mashqlar, topshiriq, o'z-o'zini baholash; birinchi qatorda — muqova.

### Word (.docx) → matn, rasmlar, jadvallar

`docx_lecture()` (lxml, `word/document.xml`): paragraflar (sarlavha uslubi / qalin qisqa qator → sarlavha — `<w:b w:val="0|false|off"/>` qalin emas, belgi uslubi (`rStyle`, `basedOn` zanjiri) qalinligi hisobga olinadi; ro'yxat), formulalar (OMML → matn),
**jadvallar** (`<table>`, birinchi qator — `thead`; bitta katakli jadval — oddiy paragraf), **rasmlar** hujjat tartibida (≤ 80 ta; < 48 px ikonkalar
tashlanadi; `_norm_image` — dekodlashdan oldin o'lcham tekshiruvi, ≤ 1600 px, metama'lumotsiz). Rasm izohi — rasmdan keyingi, bo'lmasa oldingi
paragraf, agar u `^\d+(\.\d+)*\s*-?\s*rasm` / «Rasm 2.» / «Рисунок 2.» ga mos kelsa (izoh paragrafi matndan olinadi). Saqlangan matnda belgilar:
`[RASM:<fayl>]`, `[JADVAL:N]` (meta: `images`, `tables`) — joylashtirilgan matnda ham ishlatish mumkin (qo'lda yuklangan rasm uchun UI
belgini ko'rsatadi; belgisiz qo'lda yuklangan rasm matn oxirida chiqadi). Zip/rasm bombasi tekshiruvlari (`_zip_guard`, `_ooxml_image_guard`) — tahlildan oldin.
Sarlavha darajalari: mavzu nomi olib tashlangach eng yuqori daraja `h2` bo'ladi (pleyer «qadamlar»ni `h2` bo'yicha bo'ladi). PDF ma'ruza matni — faqat matn.

### Matn → HTML

Server tomonda: sarlavhalar («1.» — yolg'iz turgan qisqa qator, «1.1.» / «1.1.1.», «#», KATTA HARFLI qisqa qator), ro'yxatlar («-», «•», «1)»,
ketma-ket «1. 2.»), « | » bilan ajratilgan qatorlar → jadval, uzilgan qatorlar → paragraf, `**qalin**`, qisqa «…:» qatori → qalin izoh.
Mavzu nomi qatori («5-MAVZU: …») olib tashlanadi. Natija oq ro'yxat bo'yicha **tozalanadi** (`sanitize`): `h2 h3 h4 p ul ol li strong em b i u
blockquote table thead tbody tr th td br sup sub code pre a` (`a` — faqat http(s) `href`, `rel="noopener noreferrer"`); script, style, iframe, svg,
`on*` atributlari, `javascript:` / `data:` havolalar olib tashlanadi. Rasmlar: `figure`, `figcaption`, `img` — faqat `src` (nisbiy `assets/…`,
`[A-Za-z0-9_\-./]`, `..`/`//`/`/` bilan boshlanish yo'q; http(s), `data:`, `javascript:` — rad) va `alt`; `html_unsafe()` aynan shuni qabul qiladi. script/style/iframe/object/svg/math/textarea/title kabi teglar
mazmuni bilan tashlanadi; bo'sh teglar (embed, frame, param …) — «tashlash» rejimiga kirmasdan; button/form/select — faqat teg (matni qoladi);
yopilmagan textarea/title — hujjat oxirida matni (escape qilingan) qaytariladi.

## Rise 360 (v3): yangi imkoniyatlar

### Video fayl, subtitr, poster

- **Yuklash** — `POST …/video/file`: `.mp4` yoki `.webm`. Tana **diskka oqim bilan** yoziladi (`_stream_upload` → `<store>/tmp/up_*.part` → `os.replace`),
  xotiraga yig'ilmaydi; hajm yo'l-yo'lakay sanaladi (chegaradan oshgan zahoti 413 — `Content-Length`siz/chunked bo'lsa ham), sha256 ham.
  Tur **birinchi 64 baytdan** aniqlanadi (`ftyp` — mp4, EBML + `webm` — WebM); `.mkv`, M4A audio, boshqa fayl — 415 va qolgan tana o'qilmaydi.
  Ruxsat va kurs ko'lami tana o'qilishidan **oldin** tekshiriladi. Darsda bitta video fayl: yangisi eskisini almashtiradi (eskisi diskdan o'chiriladi).
- **Chegaralar:** video ≤ `ISFT_CORE_PK_VIDEO_MB` (standart **200**); video fayl kirgan paket ≤ `ISFT_CORE_PK_PACKAGE_MB` (standart **500**, 200 dan kam bo'lmaydi);
  videosiz paket — avvalgidek 200 MB.
- **Zip:** `assets/video/video.mp4|webm` — **ZIP_STORED** (qayta siqilmaydi). Yig'ishda video xotiraga o'qilmaydi: zip diskdagi vaqtinchalik
  faylga oqim bilan yoziladi (`zip_write`, `BigFile`), `validate_zip` va sha256 ham diskdan; barmoq izi — yuklashda hisoblangan sha256. Natija deterministik
  (xotirada va diskka yozilgan zip bir xil). Boshqa manba fayllar ham (slaydlar, audio, .pptx/.pdf, rasmlar) xotiraga o'qilmaydi: zipga `Path` sifatida
  uzatiladi va oqim bilan ko'chiriladi, barmoq izi uchun oqim bilan xeshlanadi (`_file_sha`); tayyor zip har doim paket katalogidagi `build_*.tmp` ga yoziladi va
  `os.replace` bilan joyiga ko'chiriladi (xotirada `BytesIO` nusxasi yo'q), sha256 bir marta hisoblanadi. **Hajm oldindan tekshiriladi** (`_size_guard`): siqilmay
  yoziladigan fayllar yig'indisi paket chegarasidan oshsa — zip yozilmasdan 413. Kurs paketida 8 MB dan katta siqilmagan ichki fayllar dars zipidan oqim bilan ko'chiriladi (`ZipMember`).
- **Subtitr** — `POST …/video/captions?lang=uz&label=`: `.vtt` yoki `.srt` (≤ 2 MB, ≤ 5000 yozuv) → me'yorlangan **WebVTT** (`to_vtt`). Kodlash: UTF-8 (BOM bilan ham) →
  UTF-16 (BOM) → cp1251 (zaxira). Har yozuv tekshiriladi (vaqt qatori, daqiqa/soniya < 60, tugash > boshlanish) — xatoda 400 **qator raqami bilan** (audit jurnalida).
  SRT raqamlari, VTT sarlavhasi / NOTE / STYLE / REGION / joylashuv sozlamalari tashlanadi; matnda faqat `<i> <b> <u>`; yozuvlar vaqt bo'yicha tartiblanadi.
  VTT sarlavhasi qat'iy o'qiladi: `WEBVTT` qatori (ixtiyoriy nom bilan) + sarlavha qatorlari **birinchi bo'sh qator yoki birinchi vaqt qatorigacha** — sarlavhadan keyin
  bo'sh qatorsiz kelgan birinchi yozuv yo'qolmaydi. Faqat haqiqiy teglar olinadi (`</?[A-Za-z][^<>]*>` — `<v Ali>`, `<c.sariq>`, `<font …>` — va vaqt tegi `<00:00:01.000>`);
  matndagi yolg'iz «<» / «>» («a < b va c > d») saqlanadi va WebVTT qoidasi bo'yicha `&lt;` / `&gt;` qilib yoziladi.
  Har til uchun bitta fayl (`uz`, `ru`, `en` …); paketda `assets/video/video.<til>.vtt`. Subtitr faqat video **fayl** bilan ishlatiladi.
- **Poster** — `POST …/video/poster` (.png/.jpg → JPEG ≤ 1920 px) → `assets/video/video.jpg`.

### Muqova

`content.cover = {image, author}` (blok emas — pleyer qadamlar rejimida birinchi qadam qilib chizadi). Rasm: dars → kurs → bo'lim standarti
(Sozlamalar); hech biri bo'lmasa `image: null` (pleyer brend rangida chizadi). Rasm ≤ 1920 px JPEG'ga keltiriladi (metama'lumotsiz; mavjud rasm
himoyalari: tur baytlardan, ≤ 40 Mpx dekodlashdan oldin). Muallif — standart holda kurs o'qituvchisining F.I.Sh.; dars bo'yicha tahrirlanadi
(`pk_topics.extra.author`; bo'sh satr — **muallifsiz**: pleyer muallif qatorini chizmaydi, `course.teacher`ga qaytmaydi). «Bloklar → Muqova» o'chirilsa `cover` kaliti chiqmaydi.

### Mashqlar (`pk_exercises`)

| Tur | Tekshiruv | Paketda |
|---|---|---|
| Moslashtirish (`match`) | 2–8 juft; chap tomonlar ham, o'ng tomonlar ham takrorlanmaydi; tomon ≤ 200 belgi | test blokida savol `{"type":"match"}` — Test bank savollaridan keyin |
| Saralash (`sort`) | 2–4 toifa (nomi ≤ 80, takrorlanmaydi), har birida 1–8 element (≤ 120); element butun mashqda bir marta | test blokida savol `{"type":"sort"}` |
| Kartochkalar (`flashcards`) | 1–40 kartochka; old ≤ 200, orqa ≤ 500, ikkalasi bo'sh emas | alohida `flashcards` bloki (har to'plam — bitta blok), baholanmaydi |

Savol/sarlavha ≤ 300, izoh ≤ 500; bo'sh qatorlar tashlanadi; bitta darsda ≤ 30 mashq (qo'lda qo'shishda ham, «AI: mashqlar»da ham — 400). Holat: `faol` (paketga kiradi) / `qoralama` (AI qoralamasi —
kirmaydi). Tasdiqlash bosqichi yo'q (o'qituvchiniki); bo'lim istalgan kursda tahrirlaydi; kafedra — faqat ko'radi; rektor — faqat jamlangan son.
Test bloki Test bank savollari **yoki** moslashtirish/saralash mashqi bo'lsa chiqadi; `quiz_n` (N ta savol) faqat Test bank savollariga tegishli.
UI: dars panelida «Mashqlar» — «+ Moslashtirish / + Saralash / + Kartochkalar» oddiy formalari (juftlar qatorlari, toifa + elementlar, old/orqa).

**AI: mashqlar** — «AI: asosiy xulosalar» bilan bir xil tartib: faqat dars matni (belgilarsiz, ≤ 60 000 belgi) `claude_client.call_json` ga qat'iy sxema
(`{pairs:[{left,right,quote}], cards:[{front,back,quote}], categories:[{title, items:[{text,quote}]}]}`, `additionalProperties:false`) bilan yuboriladi;
har juft / kartochka / element **matndan aynan iqtibos** bilan keladi va `testbank._quote_in` bilan tekshiriladi — matnda topilmagani, takror va bo'shlari
tashlanadi. Natija — **qoralama** mashqlar (oldingi AI qoralamalari almashtiriladi); o'qituvchi muharrirda ko'rib «Saqlash» bosgach `faol` bo'ladi.
Saralash — ixtiyoriy (`{sort:true}`). Mashqlar chegarasi (`MAX_EXERCISES` = 30) AI uchun ham amal qiladi: AI chaqirilishidan oldin tekshiriladi
(oldingi AI qoralamalari hisobga kirmaydi — ular almashtiriladi; 2 ta, saralash bilan 3 ta bo'sh joy kerak) — joy yo'q bo'lsa 400, AI chaqirilmaydi, kunlik cheklov sarflanmaydi. Model `ISFT_CORE_PK_MODEL`, kunlik cheklov `ISFT_CORE_PK_DAILY` (xulosalar bilan umumiy), kalitsiz — 503, AI xatosi — 502.

### Topshiriq

Blok: `text` va `author` — sozlamadagi shablon (standart: «Quyidagi topshiriqni bajarib PDF shaklda LMS platformasiga joylang» — «Sizning
professor-o'qituvchingiz»), `avatar` — kurs bo'yicha yuklangan o'qituvchi rasmi (≤ 512 px JPEG; yo'q bo'lsa `null` — pleyer o'zi belgi chizadi), `questions`:

1. dars panelida **qo'lda** kiritilgan ro'yxat (bo'sh ro'yxat — blok chiqmaydi; ≤ 60 ta, har biri ≤ 500 belgi — uzuni kesilmaydi, 400), bo'lmasa
2. ma'ruza matnidagi **«Savollar» / «Nazorat savollari» / «Nazorat uchun savollar» / «Topshiriqlar» / «Mustaqil ish (uchun) topshiriqlari» /
   «Savol va topshiriqlar» / «Takrorlash uchun savollar»** (kirill va ruscha variantlari ham) sarlavhasidan keyingi ro'yxat — raqamli/belgili bandlar
   (uzilgan qator — bandning davomi) yoki «?» bilan tugaydigan qatorlar; «Savollar: 1. … 2. …» bir qatorda ham. Ro'yxat — faqat **ketma-ket** bandlar: sarlavha,
   adabiyotlar, rasm/jadval yoki oddiy matnda tugaydi; bandlar orasida bitta bo'sh qator faqat keyingi qator raqamlashni davom ettirsa («3.» → «4.») ruxsat etiladi —
   bo'sh qatordan keyingi «1.2. …» (bo'lim raqami), belgili band, qayta «1.» dan boshlangan ro'yxat yoki paragraf ma'ruza matnining davomi hisoblanadi; sarlavhadan
   keyin bo'sh qator bilan kelgan raqamli ro'yxat «1.» dan boshlanishi kerak. Ko'pi bilan **60 ta** (`ASSIGN_MAX`), band ≤ 500 belgi. **Hech narsa jimgina tashlanmaydi:**
   60 tadan ortig'i yoki 500 belgidan uzun banddan boshlab ro'yxat ma'ruza matnida qoladi va tayyorgarlik panelida ogohlantirish chiqadi (`ready.assignment.warnings`).
   Topilgan ro'yxat (sarlavhasi bilan) **matn blokidan olinadi**. «Reja» ichidagi «2. Savollar» bandi — reja bandi.

Ro'yxat matndan **faqat topshiriq blokida aynan shu (matndan olingan) ro'yxat ko'rsatilganda** olinadi. Qo'lda ro'yxat saqlangan (bo'sh ham), topshiriq bloki
o'chirilgan yoki savol topilmagan bo'lsa — «Savollar» bo'limi ma'ruza matnida qoladi. Javobni talaba LMS'ning o'ziga yuklaydi — paket fayl qabul qilmaydi.

### Slayd izohi va audiosi

«Taqdimot → Slayd izohlari va audio»: har slaydga izoh (≤ 300 belgi, `pk_topics.extra.slides`) va audio (`.mp3 / .m4a / .ogg / .wav` — tur baytlardan,
≤ 20 MB, bitta dars bo'yicha jami ≤ 150 MB — `MAX_AUDIO_TOTAL`, oshsa 413; `purpose='audio'`, `meta.slide`). Paketda `slides[].caption` va `slides[].audio = "assets/audio/s<N>.<kengaytma>"` (ZIP_STORED). Bog'lanish —
slayd **tartib raqami** bo'yicha: taqdimot almashtirilsa izoh/audio o'sha raqamda qoladi. Oynada audio yuklash/olib tashlash yozilgan, hali saqlanmagan izohlarni yo'qotmaydi.

## Rise 360 bilan taqqoslash

| Rise 360'da (qo'lda) | ISFT Core | Holat |
|---|---|---|
| Dars muqovasi: rasm, logotip, «L1-1-dars: …», muallif | `cover` — rasm (dars/kurs/bo'lim standarti), logotip, dars kodi va nomi, muallif avtomatik | bor, avtomatik |
| Video blok: mp4 yuklash | video fayl (.mp4 / .webm ≤ 200 MB) yoki YouTube havola | bor |
| Video subtitrlari (Rise'da qo'lda yoki AI) | tayyor `.vtt` / `.srt` fayl yuklanadi (SRT → WebVTT) | bor — **AI subtitr yo'q** |
| Matn bloklari (Word'dan nusxalab) | Word (.docx) bir marta yuklanadi → reja, sarlavhalar, rasmlar izohi bilan, jadvallar, adabiyotlar avtomatik | bor, avtomatik |
| Rasm karuseli: izoh va audio | taqdimot galereyasi (PDF/PPTX/rasmlar) + slayd izohi + slayd audiosi | bor — audio tayyor fayl; **AI ovoz yo'q** |
| Knowledge check: bitta/bir nechta tanlov, to'g'ri/noto'g'ri, bo'sh joy | Test bankdagi tasdiqlangan savollar | bor, avtomatik |
| Knowledge check: Matching | moslashtirish mashqi (2–8 juft) | bor (qo'lda yoki AI qoralamasi) |
| Sorting (kartochkalarni toifalarga) | saralash mashqi (2–4 toifa) | bor |
| Flashcards | kartochkalar (1–40) | bor |
| Topshiriq: o'qituvchi rasmi + iqtibos + «Savollar» ro'yxati | `assignment` — shablon matni, rasm, savollar Word'dagi «Savollar» bo'limidan avtomatik | bor, avtomatik |
| «Continue» tugmalari, qadamlar | `layout: steps` | bor |
| Bloklarni sichqoncha bilan erkin joylashtirish, istalgan tartib | tartib — kafedra shabloni (qat'iy); bloklar yoqiladi/o'chiriladi, bo'lim nomlari o'zgaradi | **yo'q** (erkin drag-drop muharrir qurilmagan) |
| AI: subtitr yaratish, matndan ovoz (text-to-speech) | — | **yo'q** — nutq xizmati (STT/TTS) kerak, ulanmagan |
| Boshqa Rise bloklari: accordion, tabs, timeline, labeled graphic, scenario, process, chart, embed | — | **yo'q** |
| Rasm/video tahriri (kesish, filtr), stok rasmlar kutubxonasi | — | **yo'q** (rasm faqat o'lchamga keltiriladi) |
| Hamkorlikda tahrir, sharh (Review 360) | bo'lim tasdiqlashi / qaytarishi (izoh bilan) | qisman |
| Natijani LMS'ga yozish | SCORM 1.2 / 2004 / xAPI; NEXTID'da — faqat `postMessage` | Rise bilan bir xil cheklov (NEXTID launch parametrlarisiz) |

Haqiqiy `.mp4` ijrosi lokal sinovda tekshirilmagan (ffmpeg yo'q — testlarda faqat sarlavhasi to'g'ri namuna fayl): `<video>`, `<track>`, Range javoblari
tekshiriladi, kodek mosligi (H.264/AAC tavsiya etiladi) — foydalanuvchi zimmasida.

## Ma'lumotlar

| Jadval | Mazmuni |
|---|---|
| `pk_packages` | Paket versiyasi: kurs, mavzu (0 — kurs paketi), versiya, tur, holat (`qoralama` / `tayyor` / `tasdiqlandi`), sozlama, manba barmoq izi, yig'ilgan vaqt va kim, fayl, hajm, sha256, tekshiruv natijasi, tayyorgarlik, tasdiqlagan, qaytarish izohi |
| `pk_assets` | Yuklangan fayllar: maqsad (`matn` / `taqdimot` / `slayd` / `fayl` / `rasm`; v3: `video`, `subs`, `poster`, `muqova`, `avatar`, `audio`), tur (pptx/pdf/docx/png/jpg/mp4/webm/vtt/mp3/…), nom, yo'l, hajm, sha256, meta (matn, reja, PPTX slaydlari; subtitr tili; slayd raqami). Kurs darajasidagi fayllar — `topic_no=0`, bo'lim standarti — `course_id=0`; `deleted=2` — «almashtirildi» |
| `pk_topics` | Dars: video havola, biriktirilgan deck, dars sozlamasi (standartdan farqi), `keypoints` (JSON: `draft` — AI/qo'lda qoralama iqtiboslar bilan, `approved` — paketga kiradigani), `extra` (JSON, v3: `author` — muqova muallifi, `questions` — qo'lda topshiriq savollari, `slides` — `{"N": izoh}`) |
| `pk_exercises` | Mashqlar (v3): kurs, dars kaliti, tur (`match` / `sort` / `flashcards`), sarlavha, `data` (JSON: `pairs` / `categories` / `cards`, AI qoralamasida `quotes`), izoh, holat (`faol` / `qoralama`), `src` (`ai`), tartib, muallif, `deleted` |
| `pk_lessons` | Darslar ro'yxati: kurs, kalit (`lkey`), tur, raqam, nom, bog'langan mavzu (`topic_ref`), o'chirilgan |
| `pk_ai` | AI so'rovlari jurnali (kunlik cheklov uchun): foydalanuvchi, kun, model, natija, tokenlar, tashlangan bandlar |
| `pk_log` | Tarix: yuklash, video, sozlama, yig'ish, tasdiqlash, qaytarish |
| `pk_meta` | `defaults` (standart sozlamalar), `seed_v1`, `seed_lessons_v1`, `demo_pkg`, `nextid_v1` (migratsiya), `pv_key` |

**Migratsiya** (`migrate()`, har `init()` da, idempotent): `pk_lessons`/`pk_ai`/`pk_exercises` jadvallari; `pk_topics.keypoints`, `pk_topics.extra` va `pk_packages.lesson` ustunlari
(yo'q bo'lsa); bo'sh `pk_packages.lesson` → `L<N>` (kurs paketi — `kurs`); standart sozlama hech o'zgartirilmagan bo'lsa (eski standart bilan
bir xil) — tur xAPI, bir marta (`nextid_v1`). Qayta chaqirish hech narsani o'zgartirmaydi. Paket `pk_packages.topic_no` — dars kaliti.

Fayllar: `<DATA_DIR>/paket/assets/<kurs>/<mavzu>/…` (kurs darajasi — `<kurs>/0/`, bo'lim standarti — `0/0/`), vaqtinchalik yuklashlar — `<DATA_DIR>/paket/tmp/` (`up_*.part`; yig'ishda — paket katalogida `build_*.tmp`; uzilib qolgan, 6 soatdan eski vaqtinchalik fayllarni `init()` dagi `sweep_tmp()` o'chiradi) va `<DATA_DIR>/paket/packages/<kurs>/<mavzu>/v<N>_<tur>.zip` (doimiy disk — `ISFT_CORE_DATA_DIR`).
Mavzu boshiga **har bir paket turi (SCORM 1.2 / SCORM 2004 / xAPI / oddiy) bo'yicha oxirgi 3 versiya** va tasdiqlangani saqlanadi; eskilari fayli bilan o'chiriladi. «O'zgarish yo'q» tekshiruvi ham tur bo'yicha: boshqa turni yig'ish keyingi qayta yig'ishni yangi versiyaga aylantirmaydi. Video faylli darsda har versiya videoning nusxasini saqlaydi (disk: tur boshiga 3 versiya × video hajmi).

## Sozlamalar

Standart (bo'lim): tur (`xapi` — standart, NEXTID / `scorm12` / `scorm2004` / `none`), yakunlash (`view_all` / `quiz_pass` / `view_and_quiz`),
o'tish foizi (mastery), savollar soni (0 — hammasi), aralashtirish, urinishlar (0 — cheksiz), javobdan keyin izoh, bloklar (bo'lim sarlavhalari,
muqova, video, reja, matn, asosiy xulosalar, adabiyotlar, taqdimot, fayllar, kartochkalar, test, topshiriq, o'z-o'zini baholash — yoqish/o'chirish) va **kafedra shabloni**:
`layout` (`steps` — standart, Rise kabi qadamlar / `scroll`), `sections` (`video`: «VIDEODARS», `text`: «MA'RUZA MATNI», `slides`: «DARS TAQDIMOTI»,
`practice`: «MASHQ VA TOPSHIRIQLAR»), `assignment` (`title`, `text`, `author` — topshiriq shabloni), `video_source` (`file` — standart / `youtube`: ikkalasi bo'lsa qaysi biri),
`reflect` (`title`, `question`: «Darsni to'liq o'zlashtirdingizmi?», `options` 2–4 ta `{text, feedback}`; 2 tadan kam — e'tiborsiz). Dars uchun
alohida o'zgartirish mumkin (o'qituvchi — o'z kursida; UI'da layout va bloklar). Testsiz paketda yakunlash avtomatik `view_all`.
Adabiyotlar bloki o'chirilsa ham adabiyotlar ro'yxati matnga qaytmaydi.

## AI: asosiy xulosalar

«AI: asosiy xulosalar» — faqat dars matni (belgilarsiz; talaba ma'lumoti yo'q, ≤ 60 000 belgi) `claude_client.call_json` ga qat'iy JSON sxema bilan
(`{"points":[{"text","quote"}]}`, `additionalProperties:false`) yuboriladi → 4–7 xulosa (o'zbek lotin), har birida matndan aynan iqtibos.
Iqtibosi matnda topilmagan (Test bankdagi `_quote_in` bilan) yoki bo'sh band tashlanadi, ko'pi bilan 7 ta. Natija — **qoralama**; o'qituvchi tahrirlab
«Tasdiqlash» bosmaguncha paketga kirmaydi. Model — `ISFT_CORE_PK_MODEL` (standart `claude-opus-5-5`); kalit yo'q — 503 (o'zbekcha xabar, qo'lda
yozish mumkin); kunlik cheklov — `ISFT_CORE_PK_DAILY` (standart 30 so'rov / foydalanuvchi). Testlarda `call_json` jarayon ichida almashtiriladi
(serverda soxta AI rejimi yo'q).

## Paket kontrakti (pleyer bilan umumiy)

Zip ildizi: pleyer fayllari (`app/paket_player/*`, `index.html` — ishga tushirish fayli), `content.js` (`window.PAKET = {...};`, UTF-8),
`content.json` (o'sha JSON), `assets/…` (`logo.png`, `img/<hash>.png|jpg`, `slides/sN.png`, `slides/pN.jpg`, `taqdimot.pptx`, `taqdimot.pdf`, `files/*`;
v3: `cover.jpg`, `video/video.mp4|webm`, `video/video.jpg`, `video/video.<til>.vtt`, `audio/sN.<kengaytma>`, `img/avatar.jpg`) va manifest.

```
{"v":1,"id":"isft-<kurs>-<dars kaliti>-v<versiya>","title":"…","lang":"uz","layout":"steps"|"scroll",
 "course":{"subject","direction","course","kafedra","teacher"}, "topic":{"no","title"},
 "lesson":{"code":"L1"|"A1"|…,"kind":"maruza|amaliy|seminar|laboratoriya|mustaqil","no":1,"title":"…"},
 "brand":{"name":"ISFT","full":"International School of Finance and Technology","color":"#8B0033","logo":"assets/logo.png"},
 "built":"<ISO>", "blocks":[section | video | plan | text | keypoints | refs | slides | file | flashcards | quiz | assignment | reflect …],
 "tracking":{"mode","completion","mastery","activity_id":"https://isft.uz/xapi/paket/<kurs>/<N>" (L) | ".../<kurs>/A1" (boshqalar)}}
```

Kontrakt v2 — qo'shimcha (v = 1 qoladi; pleyer noma'lum maydonlarni e'tiborsiz qoldiradi). `topic` moslik uchun: `{"no": dars raqami, "title"}`.
Yangi/o'zgargan bloklar:
- `{"type":"section","title":"VIDEODARS"}` — bo'lim sarlavhasi (alohida qadam);
- `plan` — `"heading":"1-MAVZU: <NOM>"` (L) / `"1-AMALIY MASHG'ULOT: <nom>"` (A …) + `items`;
- `text.html` — `<figure><img src="assets/img/<fayl>" alt="…"><figcaption>1.1-rasm. …</figcaption></figure>`, `<img src="assets/img/…" alt="…">`, `<table>`;
- `slides` — `"display":"images"|"text"` (qolgan maydonlar o'zgarmagan);
- `{"type":"refs","title":"Foydalanilgan adabiyotlar","items":["…"]}`, `{"type":"keypoints","title":"Asosiy xulosalar","items":["…"]}`;
- `{"type":"reflect","title":"O'z-o'zini baholash","question":"Darsni to'liq o'zlashtirdingizmi?","options":[{"text","feedback"}, …]}` — baholanmaydi.

### Kontrakt v3 (Rise 360) — qo'shimcha, `v` = 1 qoladi

```
"cover": {"image": "assets/cover.jpg" | null, "author": "F.I.Sh." | ""}                      — yuqori daraja, ixtiyoriy («course»dan oldin)
{"type":"video","title","provider":"file","src":"assets/video/video.mp4|webm","poster":"assets/video/video.jpg"|null,
 "captions":[{"lang":"uz","label":"O'zbekcha","src":"assets/video/video.uz.vtt"}, …]}        — YouTube varianti o'zgarmagan
slides[]: + "caption":"…", "audio":"assets/audio/s<N>.mp3|m4a|ogg|wav"                        — faqat bor bo'lsa (kalit yo'q = yo'q)
quiz.questions[]: {"id":"x<pk_exercises.id>","type":"match","stem","pairs":[{"left","right"}],"explanation"}
                  {"id":"x<id>","type":"sort","stem","categories":[{"title","items":["…"]}],"explanation"}    — baholanadi: hammasi to'g'ri = 1, aks holda 0
{"type":"flashcards","title":"Kartochkalar","cards":[{"front","back"}]}                        — baholanmaydi
{"type":"assignment","title":"Topshiriq","text":"…","author":"…","avatar":"assets/img/avatar.jpg"|null,"questions":["…"]}   — baholanmaydi
```

Pleyer tomoni (app/paket_player, v3): `cover` — qadamlar rejimida **sun'iy birinchi qadam** (`.nav-i[data-type="cover"]`, `data-i="0"`; blok emas, qolgan
qadamlar indeksi bittaga suriladi; scroll rejimida — birinchi sahifa ustida); `cover.author` berilmagan (`null` / kalit yo'q) bo'lsa `course.teacher`, bo'sh satr (`""`) —
muallifsiz (muqovada ham, chop etishda ham). Fayl-video `<video>` ga `crossorigin="anonymous"` faqat sandboxed ko'rishda (sahifa http(s) orqali berilgan, origin «opaque» — `<track>`
shusiz yuklanmaydi) qo'yiladi; `file://` va oddiy same-origin xizmatda (LMS) — qo'yilmaydi. Global ←/→/PageUp/PageDown (qadam almashtirish) test formasi (`form.qform`,
`fieldset.q`), moslashtirish/saralash vidjetlari va kartochkalar (`.fc-grid`) ichida fokus turganda ishlamaydi. Pleyer qabul qiladigan qiymatlar
(boshqasi jimgina tashlanadi): `cover.image`, video `src` / `poster` / `captions[].src`, `slides[].audio`, `assignment.avatar` — faqat nisbiy `assets/…`;
fayl video uchun `provider:"file"` aniq yozilishi shart; match — 2–20 to'liq juft; sort — ≥ 2 toifa va ≥ 1 element (≤ 8 toifa, ≤ 30 element);
flashcards — ikkala tomoni bo'sh emas, ≤ 60. Paket yig'uvchi bundan torroq chegaralarda yozadi (2–8 juft, 2–4 toifa × 1–8, ≤ 40 kartochka).
LMS'ga yoziladigan javob formati: SCORM 1.2 «matching» — bir belgili identifikatorlar (`1.b,2.a`); SCORM 2004 va xAPI — match `l1[.]r2[,]…`, sort `i1[.]c2[,]…`.
Subtitrlar standart holda o'chiq — talaba pleyerda CC ni yoqadi. Sinov selektorlari: `.card.t-cover .hero`, `h1.hero-t`, `[data-act="begin"]`;
`.video.file video[data-block]`, `track[kind="subtitles"]`, `.v-speed button[data-rate]`; `.s-cap`, `.s-aud audio`; `fieldset.q[data-kind="match"]`
(`button.m-slot[data-l=i]` → `button.m-tile[data-r=i]`), `fieldset.q[data-kind="sort"]` (`button.s-card[data-k=k]` → `button.s-drop[data-c=c]`, k — toifalar
bo'yicha yoyilgan element indeksi); `.fc-grid button.fc[data-k][aria-pressed]`; `.asg`, `ol.asg-list li`, `.asg-note`; `[data-act="start|submit|retry"]`.

Bloklar tartibi (kafedra shabloni, v3): [muqova — `cover`] → section «VIDEODARS» → video → section «MA'RUZA MATNI» → reja → matn → asosiy xulosalar →
adabiyotlar → section «DARS TAQDIMOTI» → taqdimot → qo'shimcha fayllar → section «MASHQ VA TOPSHIRIQLAR» (nomi sozlanadi) → kartochkalar → test
(Test bank savollari, keyin moslashtirish/saralash) → topshiriq → o'z-o'zini baholash. Manbasi yo'q blok tushadi, bo'sh guruhning bo'limi ham
chiqmaydi; reflect — kamida bitta kontent bloki bo'lsa. `id` — `b1`, `b2`, … (ketma-ket, turidan qat'i nazar); savol `id` — `q<tb_questions.id>`,
mashq savoli — `x<pk_exercises.id>`.

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

**Kurs paketi:** bitta manifestda har dars alohida SCO, o'z papkasida (L — `t01/index.html`, A — `a01/`, S — `s01/`, Lab — `lab01/`, MT — `mt01/`;
tartib L, A, S, Lab, MT; SCO nomi «L1. …»); har dars — oxirgi tasdiqlangan (yoki «faqat tasdiqlangan» belgilanmasa — oxirgi) dars paketidan, `content.js` dagi `tracking.mode` kurs paketi turiga qayta yoziladi.
SCORM 1.2, SCORM 2004 va xAPI (bir nechta activity).

**Deterministik zip:** yozuvlar alfavit tartibida, vaqt 1980-01-01, atributlar qotirilgan → bir xil kirish = bir xil sha256.
Manba, sozlama va pleyer fayllari o'zgarmasa, qayta yig'ish yangi versiya yaratmaydi (barmoq izi); «majburan» (`force`) — yangi versiya.

**Tekshiruv (`validate_zip`)** har yig'ishdan keyin: manifest o'qiladi va nomlar fazosi/`schemaversion` mos, identifikatorlar yagona va to'g'ri,
`item → resource` bog'langan, har bir `href`/`file` zip ichida va har bir fayl manifestda, ishga tushirish fayli bor, `content.js` shakli va JSON,
bloklar turi/`id` (section, refs/keypoints `items`, reflect savol + ≥ 2 javob, `slides.display`, `layout`), asset yo'llari zip ichida (matndagi
har bir `<img src="assets/img/…">` ham), matn blokida xavfli HTML yo'q, xAPI `activity id` = `tracking.activity_id`, `tracking.mode` = paket turi,
mutlaq / `..` / `\` yo'llar yo'q, HTML'da YouTube'dan boshqa tashqi skript yo'q. v3: `cover` shakli va rasmi, fayl video `src` (`assets/video/*.mp4|webm`),
poster, har subtitr (`lang`, `label`, `.vtt`) va slayd audiosi zip ichida; video `provider` — `youtube` yoki `file`; match (≥ 2 to'liq juft), sort (≥ 2 toifa,
har birida element), flashcards (`cards`), assignment (matn + savollar, `avatar` zip ichida). Xato bo'lsa paket saqlanmaydi (422, sababi bilan).

**Cheklovlar:** bitta fayl ≤ 50 MB (tana oqim bilan sanaladi — `Content-Length`siz/chunked yuklash ham chegarada 413), paket ≤ 200 MB
(video fayl bilan ≤ 500 MB — `ISFT_CORE_PK_PACKAGE_MB`; yig'ishda zip yozilishidan oldin tekshiriladi — 413), video fayl ≤ 200 MB (`ISFT_CORE_PK_VIDEO_MB`), slayd audiosi ≤ 20 MB
(dars bo'yicha jami ≤ 150 MB), subtitr ≤ 2 MB,
PPTX ≤ 200 slayd, matn ≤ 200 000 belgi; fayl nomlari zip ichida ASCII. **Zip/rasm bombalari:** .pptx/.docx/.xlsx tahlildan oldin markaziy katalog
bo'yicha tekshiriladi — ochilgan umumiy hajm ≤ 300 MB, bitta ichki fayl ≤ 150 MB, ≤ 5000 ichki fayl, 5 MB dan katta ichki fayl uchun siqish
nisbati ≤ 100:1 (aks holda 413). Rasm o'lchami dekodlashdan oldin (sarlavhadan) tekshiriladi: ≤ 40 Mpx — slayd rasmi va .docx ichidagi rasm
kattaroq bo'lsa 413, .pptx ichidagi katta rasm o'tkazib yuboriladi (slayd matn sifatida chiziladi). .pptx bir marta tahlil qilinadi.
Yuklab olish nomi: `ISFT_<fan>_<dars kodi>_<tur>.zip` — `L01`, `A01`, `S01`, `Lab01`, `MT01` (masalan `ISFT_Informatika_L01_xapi.zip`; kurs paketi —
`ISFT_<fan>_kurs_<tur>.zip`; kirill va o'zbek apostrofi transliteratsiya qilinadi). **PDF → rasm:** ≤ 120 sahifa, sahifa ≤ 40 Mpx, jami ≤ 250 Mpx
(oshsa qolgan sahifalar chizilmaydi); buzilgan/parolli PDF yoki sahifani o'lchash/chizishdagi har qanday pdfium xatosi — 415 (audit jurnalida). PDFium thread-safe emas: pypdfium2 bilan butun ish (ochish, chizish, yopish) modul darajasidagi `_PDFIUM_LOCK` ostida.

## Ko'rish (preview)

`GET /api/paket/packages/{id}/preview/<yo'l>` — saqlangan zip ichidan (ochilmaydi), faqat ko'lamdagi foydalanuvchiga. Yo'l tekshiriladi
(`..`, `/` bilan boshlanish, `\`, disk harfi, `%` — 400; zip'da yo'q — 404).
**Media va HTTP Range:** video/audio (va 8 MB dan katta boshqa siqilmagan a'zolar) zip **ochilmasdan**, a'zoning fayldagi oralig'idan (lokal sarlavha →
ofset; ZIP_STORED) 256 KB bo'laklar bilan oqimda beriladi — xotiraga to'liq o'qilmaydi. `Accept-Ranges: bytes`; `Range: bytes=a-b` / `a-` / `-n` → **206** +
`Content-Range: bytes a-b/N`; noto'g'ri yozilgan, bir nechta oraliqli yoki qondirib bo'lmaydigan Range → **416** + `Content-Range: bytes */N`. Media va `.vtt`
javoblarida `Access-Control-Allow-Origin: *` (sandbox — «null» origin; yo'l baribir imzolangan token bilan himoyalangan). Javobda qat'iy CSP: `default-src 'none'; script-src 'self';
style-src 'self' 'unsafe-inline'; img-src 'self' data: https://i.ytimg.com; font-src 'self' data:; media-src 'self'; connect-src 'none';
frame-src https://www.youtube-nocookie.com; object-src 'none'; base-uri 'none'; form-action 'none'; frame-ancestors 'self';
sandbox allow-scripts allow-popups allow-popups-to-escape-sandbox allow-forms`, `X-Content-Type-Options: nosniff`.
**Imzolangan yo'l:** sandbox'dagi hujjat opaque origin'da bo'lgani uchun uning ichki so'rovlari (content.js, player.js, rasmlar)
SameSite sessiya cookie'sini yubormaydi. Shuning uchun `/packages/{id}/preview/<yo'l>` cookie bilan tekshiriladi (ruxsat, ko'lam, audit, yo'l) va
`302` bilan `/api/paket/pv/<pid.uid.muddat.imzo>/<yo'l>` ga yo'naltiradi: HMAC-SHA256 (kalit `pk_meta.pv_key`), 2 soat, faqat shu paket va
foydalanuvchi uchun; har so'rovda foydalanuvchi faolligi, lavozimi va kurs ko'lami qayta tekshiriladi (soxta/muddati o'tgan — 403).
**Izolyatsiya:** `sandbox` da `allow-same-origin` yo'q — paket kontenti opaque origin («null») da ishlaydi: ilova cookie'si, `/api` va ota sahifa
DOM'iga kira olmaydi. UI modal ichidagi iframe'ga ham xuddi shu `sandbox` atributini qo'yadi; «Yangi oynada ochish» — server CSP'si orqali ham
sandbox'da. UI ko'rish havolalari (`iframe` va «Yangi oynada ochish») `?preview=1` bilan; `/packages/{id}/preview/…` → `/pv/<token>/…` 302'da so'rov
qatori saqlanadi (faqat `kalit=qiymat` ko'rinishidagi xavfsiz parametrlar). Pleyer LMS API topilmasa **jim mustaqil rejimda** ishlaydi (NEXTID
iframe'i shunday — xAPI / `none` paketlar bannersiz); «Ko'rish rejimi» banneri **faqat `?preview=1`** bo'lsa chiqadi. Istisno: `tracking.mode`
`scorm12` / `scorm2004` bo'lib SCORM API topilmasa (`?preview=1` siz) — qizil ogohlantirish banneri «LMS bilan aloqa topilmadi — natija saqlanmaydi.
O'qituvchiga xabar bering.» (`role="alert"`; SCORM paket LMS'siz ochilgan — natija hech qayerga yozilmaydi) (shriftlar «null» origin'da ulanmaydi — tizim shrifti; localStorage
yopiq bo'lsa holat saqlanmaydi, xato chiqmaydi).

### postMessage (ota oynaga xabarlar)

Pleyer har doim (LMS bo'lsa ham, bo'lmasa ham; iframe ichida bo'lsa) ota oynaga yuboradi:

```
parent.postMessage({source:"isft-paket", v:1, id, event, progress /* 0..1 */, score /* {raw, min:0, max:100, scaled} | null */,
                    step /* 1..steps */, steps, complete, success, [block, response]}, "*")
```

Hodisalar: `progress` — o'zgarganda va yuklanganda bir marta; `completed` — sessiyada bir marta (yuklanganda allaqachon tugallangan bo'lsa ham);
`passed` / `failed` — test topshirilganda (`block` bilan); `answered` — o'z-o'zini baholash tanlovi (`block` va `response` — 1 dan boshlanadigan
variant raqami). Fayl video ≥ 90% ko'rilganda `progress` xabarida `video:{block, watched}` keladi.
NEXTID natijani hozircha qabul qilmaydi — kelajakda integratsiya uchun.

## NEXTID'ga yuklash (my.isft.uz)

1. Paket turi — **xAPI (Tin Can) — NEXTID** (standart). Darsni yig'ing, tasdiqlang, «Yuklab olish» — nomi dars kodi bilan: `ISFT_<fan>_L01_xapi.zip`, `…_A01_xapi.zip`.
2. NEXTID.LMS → fan → **Articulate** yorlig'i → yangi dars.
3. Dars nomi NEXTID uslubida, kodi paketdagi bilan bir xil: «L1-1-dars: MAVZU NOMI», «A1- AMALIY MASHG'ULOT: NOM».
4. Zip'ni **ochmasdan** yuklang (ildizida `index.html` va `tincan.xml`), saqlang va darsni ochib tekshiring.
5. Taqdimot aniq ko'rinishi uchun PowerPoint'da «Fayl → Saqlash → PDF» va PDF'ni ham yuklang (sahifalar rasm bo'lib galereyada chiqadi).
6. Video fayl paket ichida ketadi — zip hajmi oshadi: NEXTID'ning yuklash chegarasini oldindan tekshiring; katta video uchun YouTube havolasi qulayroq.
7. Topshiriq javobini talaba PDF qilib NEXTID'ning o'ziga yuklaydi (paket fayl qabul qilmaydi); kartochkalar va topshiriq baholanmaydi.

Bir xil nomlash uchun ISFT Core'dagi darslar ro'yxatiga NEXTID'dagi nomlarni joylashtiring («Mavzular» → «Darslar ro'yxati (NEXTID)»).
UI'da ham «Sozlamalar → LMS'ga yuklash» panelida shu yo'riqnoma bor.

## Moodle'ga yuklash

1. Kursda tahrirlash rejimini yoqing → kerakli bo'limda «Faoliyat yoki resurs qo'shish» → **SCORM paketi**.
2. Nom yozing, paket faylini (.zip, ochmasdan) yuklang.
3. «Baholash»: «Eng yuqori urinish»; «Faoliyat yakunlanishi»: «Talab qilingan holat — o'tdi / tugallandi».
4. Saqlang va «Ko'rish» orqali tekshiring.

SCORM 2004 ni Moodle qisman qo'llaydi — LMS aniq talab qilmasa SCORM 1.2 tanlang. Moodle'da **xAPI** uchun LRS yoki plagin kerak.

## Avtomatik joylash

- **Video havolalar:** har qatorda bitta havola — L1 dan ketma-ket; «N: havola» / «N. havola» / «N) havola» — aniq L darsga (keyingilari N+1 dan davom etadi);
  «A3: havola», «L2: havola», «Lab1: havola» — dars kodi bilan (ro'yxatda bo'lmagan dars — xato).
  `#` bilan boshlangan va bo'sh qatorlar e'tiborsiz. Avval «Tekshirish» (saqlanmaydi), keyin «Saqlash». Bir mavzuga ikki havola — oxirgisi olinadi.
- **Ommaviy yig'ish:** kursning manbasi bor barcha darslari (L, A, …; ixtiyoriy — faqat to'liqlari), tanlangan yoki dars sozlamasidagi tur bo'yicha.

## Qamrov

Kafedra / o'qituvchi / kurs kesimida — **darslar** bo'yicha (L + qo'shilgan A/S/Lab/MT; javobdagi `topics` — darslar soni, `by_kind` — tur bo'yicha): darslar, paketi yig'ilgan va tasdiqlangan darslar, tasdiq kutayotganlar, manbasi to'liq mavzular
va har bir manba bo'yicha (matn, taqdimot, yaroqli video, tasdiqlangan test) soni. O'qituvchi — o'z kurslari, kafedra — o'z kafedrasi.

## «Mening vazifalarim»

`pending()` (app/pending.py → `paket` manbasi): bo'limga — «tasdiqni kutayotgan paketlar» (oxirgi versiyasi «tayyor» mavzular),
o'qituvchiga — «qaytarilgan paketlar» (oxirgi versiya qaytarish izohi bilan).

## Namuna ma'lumot

`init()` bir marta (`pk_meta.seed_v1`): «Mikroiqtisodiyot» 1-mavzu — sun'iy ma'ruza matni (reja, sarlavhalar, ro'yxat, jadval bilan) va
python-pptx bilan yaratilgan 4 slaydli taqdimot (izohlar va bitta rasm); 1–2-mavzular — namuna YouTube havolasi (`ISFTdemo001` — format to'g'ri,
video mavjud emas). Test — Test bank namunasidagi tasdiqlangan savollar. Darslar ro'yxati namunasi (`seed_lessons_v1`): A1, A2 (amaliy, 1–2-mavzuga bog'langan). Pleyer mavjud bo'lsa 1-mavzu SCORM 1.2 paketi bir marta yig'iladi
(`pk_meta.demo_pkg`). UI'da «Namuna» bannerida aniq belgilangan. `SEED_VERSION` o'zgartirilmagan.

## API

| Usul | Yo'l | Kim |
|---|---|---|
| GET | `/meta`, `/coverage` | hamma (ruxsatlilar) |
| GET | `/courses?q=&department_id=&teacher_id=&only=started\|waiting\|empty&offset=&limit=` | bo'lim, kafedra, o'qituvchi (ko'lam bo'yicha) |
| GET | `/courses/{cid}`, `/courses/{cid}/topics/{no}` (`no` — dars kaliti: L1 = 1, A1 = 1001 …), `/courses/{cid}/lessons`, `/courses/{cid}/topics/{no}/img/{fayl}` | bo'lim, kafedra, o'qituvchi |
| POST | `/courses/{cid}/lessons` `{text, apply}` (NEXTID nomlari), `/courses/{cid}/lessons/{no}/delete` | bo'lim, o'qituvchi |
| POST | `/courses/{cid}/topics/{no}/images` (rasm tanasi, `?name=&caption=`) | bo'lim, o'qituvchi |
| POST | `/courses/{cid}/topics/{no}/keypoints/ai`, `/keypoints` `{items, approve, clear}` | bo'lim, o'qituvchi |
| POST | `/courses/{cid}/topics/{no}/text` (fayl tanasi, `?name=`), `/text/paste` `{text}` | bo'lim, o'qituvchi |
| POST | `/courses/{cid}/topics/{no}/slides` (pptx/pdf/png/jpg), `/files` (qo'shimcha fayl) | bo'lim, o'qituvchi |
| POST | `/courses/{cid}/topics/{no}/video` `{url}` (bo'sh — olib tashlash), `/deck` `{deck_id}` | bo'lim, o'qituvchi |
| POST | `/courses/{cid}/topics/{no}/settings` `{layout, sections, reflect, assignment, video_source, mode, completion, mastery, quiz_n, shuffle, attempts, show_feedback, blocks, reset}` | bo'lim, o'qituvchi |
| POST | `/courses/{cid}/topics/{no}/video/file` (mp4/webm tanasi, oqim; `?name=`), `/video/captions` (`?name=&lang=&label=`), `/video/poster` | bo'lim, o'qituvchi |
| POST | `/courses/{cid}/topics/{no}/cover` (rasm), `/cover/meta` `{author \| null}`; `/courses/{cid}/cover`, `/courses/{cid}/avatar` (rasm) | bo'lim, o'qituvchi |
| POST | `/settings/cover` (bo'lim standart muqovasi) | bo'lim |
| POST | `/courses/{cid}/topics/{no}/slides/{n}/audio` (audio tanasi), `/slides/meta` `{captions: {"N": matn}}` | bo'lim, o'qituvchi |
| POST | `/courses/{cid}/topics/{no}/assignment` `{questions: [...] \| null}` (`null` — matndan avtomatik) | bo'lim, o'qituvchi |
| GET | `/courses/{cid}/topics/{no}/exercises` | bo'lim, kafedra, o'qituvchi |
| POST | `/courses/{cid}/topics/{no}/exercises` `{kind, stem \| title, pairs \| categories \| cards, explanation, status}`, `/exercises/ai` `{sort}`; `/exercises/{eid}` (tahrirlash), `/exercises/{eid}/delete` | bo'lim, o'qituvchi |
| POST | `/courses/{cid}/topics/{no}/build` `{mode?, force?}` | bo'lim, o'qituvchi |
| POST | `/courses/{cid}/bulk/videos` `{text, apply}`, `/courses/{cid}/bulk/build` `{topics?, mode?, only_complete}` (`topics` yo'q, `null` yoki `[]` — barcha darslar) | bo'lim, o'qituvchi |
| POST | `/courses/{cid}/course-package` `{mode, only_approved}` | bo'lim, o'qituvchi |
| GET | `/assets/{aid}` (asl fayl), POST `/assets/{aid}/delete` | ko'rish — bo'lim, kafedra, o'qituvchi; o'chirish — bo'lim, o'qituvchi |
| GET | `/packages/{pid}`, `/packages/{pid}/download`, `/packages/{pid}/preview/{yo'l}` (→ 302 imzolangan yo'lga) | bo'lim, kafedra, o'qituvchi |
| GET | `/pv/{token}/{yo'l}` (cookie'siz, imzolangan; ko'lam qayta tekshiriladi) | token egasi |
| POST | `/packages/{pid}/action` `{action: approve\|reject, note}` | bo'lim |
| POST | `/settings` (standart sozlamalar) | bo'lim |

## Testlar

`tests/test_paket.py`: har lavozim ruxsati va ko'lami (audit bilan); NEXTID darslar ro'yxati tahlili (jadval), dars kodi ↔ kalit, migratsiya
idempotentligi (3-bosqich sxemasidan ham); Word: 2 rasm + izohlar (keyin/oldin), ikonka tashlanishi, jadval, adabiyotlar → HTML/figure/refs va
zip ichida rasmlar; figure/img tozalash va `html_unsafe` (http, `data:`, `javascript:`, `/`, `..` — rad); PDF → 3 slayd rasmi (testda PIL bilan
yaratilgan PDF, pypdfium2), .pptx + PDF ustuvorligi; shablon bloklari tartibi va bo'lim sarlavhalari, layout, reflect; AI xulosalar (soxta
`call_json`: iqtibosi matnda yo'q band tashlanadi, sxema, faqat matn yuboriladi, 503/502/429, tasdiqsiz paketga kirmaydi); har tur uchun
`validate_zip` (A dars), dars bo'yicha fayl nomlari, kurs paketi papkalari (t01, t02, a01), `?preview=1` saqlanishi; YouTube havolalari jadvali (watch, youtu.be, shorts, embed, live, nocookie,
`t=`/`start=`, noto'g'ri ID, pleylist, `javascript:`), ommaviy ro'yxat; HTML tozalash; matn → reja va HTML (Reja bo'limi, raqamli sarlavhalar,
ro'yxat, jadval, kirill); PPTX tahlili (testda yaratilgan, rasm va jadval bilan); HTTP orqali manbalar (matn, .docx, .pptx, noto'g'ri fayl,
video, avtomatik joylash, mavzu sozlamasi); bazaning nusxasida soxta pleyer bilan har bir turni yig'ish + `validate_zip` + manifestlar
(ElementTree), kontrakt maydonlari, deterministik zip, o'zgarishsiz qayta yig'ish, versiyalarni kesish, kurs paketi, validator salbiy holatlari,
XML qochirish, preview yo'li va CSP, yuklab olish nomi, tf me'yorlash; regressiyalar: reja bandi «3. Foydalanilgan adabiyotlar», adabiyotlar
«Nazorat savollari»da tugashi, `<w:b w:val="0"/>`/qalin `rStyle`, PDF chizish xatosi → 415 + audit va `_PDFIUM_LOCK` (4 oqim), taqdimot
yuklash tartibi (pdf→pptx / pptx→pdf, eskisi `deleted=2`), `topic_ref` zaxira manbalari (A7 → 2-mavzu testi/videosi/matni; o'zi ustun),
`bulk_build` (`topics` None/[] — hammasi; `lessons()` bir marta), `lesson_info` to'g'ridan-to'g'ri so'rov; haqiqiy pleyer bilan yig'ilgan paket — brauzerda mock LMS ichida
(`tools/paket_build_check.js`: steps layout'dagi barcha qadamlar `.nav-i[data-i][data-type][data-block]` — bo'lim, video, reja, matn (rasmlar
yuklangan, jadval), xulosalar, adabiyotlar, PDF galereyasi, o'z-o'zini baholash `.choice[data-k]` + izoh; testga to'g'ri javob → SCORM 1.2
`passed`/100, SCORM 2004 `completed`/`passed`/100, xAPI launch parametrlarisiz — `postMessage` `passed`/100 va bannersiz; 1366 va 390 px;
konsol xatosiz; gorizontal aylantirishsiz); server orqali yig'ish, yuklab olish, preview, tasdiqlash/qaytarish,
«Mening vazifalarim»; qamrov — SQL bilan solishtirish.

Rise 360 (v3): `sniff_media`, SRT → WebVTT jadvali (UTF-8 / BOM / UTF-16 LE-BE / cp1251, tartibsiz yozuvlar, VTT sarlavha-NOTE-STYLE-sozlamalar; xato
yozuvlar qator raqami bilan), `parse_range` jadvali, `clean_exercise` (chegaralar va 19 ta rad holati), «Savollar» bo'limi (14 sarlavha varianti, reja bandi,
raqamsiz ro'yxat, ro'yxat chegarasi — bo'sh qator + «1.2. …» / paragraf, 60 ta chegara va ogohlantirish); HTTP: video fayl (chunked, tur baytlardan, 415/400/403, chegarada 413, vaqtinchalik fayl qolmasligi), subtitr (srt/cp1251/almashtirish/400+audit/413),
poster, muqova (dars/kurs/standart ustuvorligi, JPEG ≤ 1920, muallif), o'qituvchi rasmi, mashqlar CRUD + tekshiruv + ruxsatlar (o'qituvchi faqat o'z kursi, kafedra
— o'qish, rektor — faqat jamlangan son, bo'lim tahrirlaydi), topshiriq (Word'dagi «Savollar», qo'lda, avtomatikka qaytish), slayd audiosi/izohi, bloklar tartibi va
bo'sh guruh, sozlamalar; jarayon ichida: `_stream_upload` diskka bo'laklab yozishi, AI mashqlar (soxta Claude: iqtibos filtri, sxema, model, qoralama → faol, 503/502/429),
kontrakt v3 maydonlari, har turda yig'ish, ZIP_STORED, xotira va disk zipining bir xil sha256'i, Range (206/416, tana), `ZipFile.read` chaqirilmasligi, validator
(yo'q video/subtitr/poster/audio/muqova/avatar va 14 ta kontent xatosi), paket chegaralari, kurs paketida oqimli ko'chirish; server orqali yig'ish + imzolangan yo'lda Range;
brauzer (`tools/paket_build_check.js`): muqova qadami, `<video>` + `<track>` + poster, slayd izohi/audiosi, kartochka aylanishi, moslashtirish va saralashga to'g'ri javob → 100 ball, topshiriq.

## Ma'lum cheklovlar

- Rise 360 (v3): bloklar tartibi qat'iy (erkin drag-drop muharrir yo'q); AI subtitr va AI ovoz yo'q (nutq xizmati ulanmagan) — subtitr va audio tayyor fayl
  sifatida yuklanadi; video qayta kodlanmaydi (kodek/bitreyt tekshirilmaydi — H.264/AAC `.mp4` tavsiya etiladi), haqiqiy ijro lokal sinovda tekshirilmagan (ffmpeg yo'q);
  subtitrlar standart holda o'chiq (talaba CC ni yoqadi); video faylli paket versiyalari diskda ko'p joy oladi; slayd izohi/audiosi slayd tartib raqamiga bog'langan;
  «Savollar» bo'limi faqat ma'lum sarlavhalar bo'yicha aniqlanadi (boshqacha nomlangan bo'lsa — savollarni qo'lda kiriting); ko'rishda (sandbox) subtitr yuklanishi
  uchun pleyer `<video crossorigin>` qo'yishi kerak (server CORS sarlavhasini beradi).

- PPTX slaydlari rasmga aylantirilmaydi (LibreOffice yo'q): faqat .pptx bo'lsa pleyer slaydni sarlavha + bandlar + eng katta rasm sifatida chizadi;
  aniq ko'rinish uchun PDF'ni ham yuklang (sahifalar rasmga chiziladi). «Bir xil taqdimot»ni server tekshirmaydi — eng oxirgi yuklangan
  taqdimot hal qiladi: PDF `.pptx` dan keyin yuklangan bo'lsa PDF rasmlari, aks holda `.pptx` (PDF'ni `.pptx` dan oldin yuklasangiz, PDF'ni qayta yuklang). Animatsiya, SmartArt, diagrammalar `.pptx` matniga to'liq o'tmaydi.
- Word: formulalar oddiy matn; jadval ichidagi rasmlar va birlashtirilgan kataklar (colspan) saqlanmaydi; EMF/WMF rasmlar o'tkaziladi; izohni
  faqat qo'shni paragrafdan aniqlaydi. PDF ma'ruza matnidan rasm olinmaydi.
- NEXTID rejimida (launch parametrlarisiz) davom ettirish holati brauzerning localStorage'ida: bir laboratoriya kompyuteri va brauzer profilidan
  foydalanadigan talabalar bir-birining holatini ko'radi. Natija NEXTID'ga yozilmaydi (faqat `postMessage`).
- Skaner qilingan PDF (matnsiz) ma'ruza matni sifatida rad etiladi.
- Video faqat havola (YouTube'da qoladi); YouTube bloklangan tarmoqda ko'rinmaydi. Video mavjudligi (private/o'chirilgan) tekshirilmaydi — faqat ID formati.
- SCORM XSD fayllari paketga qo'shilmaydi (Moodle talab qilmaydi); qat'iy XSD tekshiruvi qiladigan LMS uchun qo'shish kerak bo'lishi mumkin.
- xAPI paket LRS manzilini LMS'dan (launch parametrlari) oladi; LRS'siz LMS'da (NEXTID) natija LRS'ga yuborilmaydi.
- Moodle'ga to'g'ridan-to'g'ri yuklash (API) yo'q — fayl eksporti; LMS'dagi natijalar ISFT Core'ga qaytib kelmaydi.
- Yig'ish sinxron (katta PPTX bilan bir necha soniya); ommaviy yig'ish uchun fon navbati keyinroq.
