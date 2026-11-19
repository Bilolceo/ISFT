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

## Muharrir ko'rinishi: «Rise» (standart) va «Klassik»

**Rise ko'rinishi** (`.ku-rise`, `localStorage.kuUi`, standart): dars natijadagidek — muqova (kurs muqovasi + dars nomi joyida tahrirlanadi), och binafsha fon,
media va mashqlar oq kartochkada, «Davom etish» — urg'u rangidagi tasma; blok asboblari (ko'chirish, ⚙ sozlamalar, nusxa, o'chirish, izoh) blok ustida
sichqoncha olib borilganda; darslar ro'yxati (chap) va blok sozlamalari (o'ng) — yon panellar; pastda **tez qo'shish paneli** (Blok kutubxonasi, Matn, Ro'yxat,
Rasm, Galereya, Video, Test savoli, Moslashtirish, Kartochkalar, Davom etish — tanlangan blokdan keyin). **Klassik** — avvalgi uch ustun («Yana» → «Klassik ko'rinish»).

**Yuqori panel va «Tayyor».** Rise ko'rinishida bitta asosiy (to'ldirilgan) tugma bor — **«Tayyor»**: Konstruktor qadamlar tasmasida (`#kxPub`), tasma bo'lmasa —
yuqori panelda (`#kuDone`). U `kuPublish()` oynasini ochadi: 1) Tekshiruv (sifat hisoboti) → 2) NEXTID uchun eksport (xAPI) → 3) ko'rib chiqishga yuborish va/yoki
4) tasdiqlash (rolga qarab bittasi yoki ikkalasi; qadamlar ketma-ket raqamlanadi). Yuqori panelda faqat ikkinchi darajali tugmalar: Ko'rish, Izohlar, «Yana»
(sifat, eksport, versiyalar, sozlamalar, dars oxiri testlari, AI, **yuborish / tasdiqlash / qaytarish**, klassik ko'rinish). Telefonda (≤ 700 px) panel bir qatorli —
faqat belgilar (`aria-label` bilan), sarlavha uzun bo'lsa «…».

**Palitra.** `.ku-rise` (va Rise ko'rinishidagi modallar — `.ku-modal-bg.rz`) ichida ilova chrome'ining qizili o'rniga yagona binafsha (`--rz-acc` #7837a8): asosiy
tugmalar, havolalar, fokus halqasi, qadamlar tasmasi, «Tayyor» oynasi. Boshqa ekranlar qizil bo'lib qoladi. Kontrast: tuvaldagi yordamchi matn va placeholder —
`--rz-muted` #595959 (lavanda #f2ebf6 ustida 6,0:1); `tools/konstruktor_check.js` tuvaldagi barcha matnni ≥ 4,5:1 ga tekshiradi (gradientli muqovadan tashqari).
`select` — `appearance:none`, maxsus strelka (SVG), yumaloq, binafsha fokus; sensorli ekranda 44 px.

**Muqova va takrorlanuvchi sarlavha.** Muqova ixcham (≈ 180 px, telefonda ≈ 150 px). Dars birinchi bloki sarlavha bo'lib, matni dars nomini (katta-kichik harfsiz
o'zaro o'z ichiga olish bilan) takrorlasa, muharrirda yig'iladi («Ko'rsatish» tugmali izoh) — ma'lumot o'chirilmaydi, talaba pleyeri o'zgarmaydi. Sarlavhalar
`<textarea data-grow>` (qatorga o'raladi, gorizontal qirqilmaydi; Enter — yangi qator emas).

**«Davom etish» bloki.** Tuvalda faqat tahrirlanadigan binafsha tasma; «Tugma qachon ochiladi» (Tugmani bosish kifoya / Avval yuqoridagi mashqlar bajarilsin) va eslatma —
⚙ panelida («Tugmani bosmaguncha keyingi qism yopiq turadi»).

**Blok kutubxonasi** («Blok kutubxonasi» / «+»): har tur uchun inline-SVG eskiz (`KU_THUMB`, tashqi fayl yo'q) va bir qatorli tavsif; guruhlar — Matn, Rasm va video,
Mashq va interaktiv, Boshqaruv; qidiruv saqlangan.

**Sensorli ekran (≤ 860 px yoki `pointer:coarse`).** Blok asboblari (tutqich, izoh, ↑ ↓, ⚙, nusxa, o'chirish) tanlangan blok ustida, ekran ichida, tugmalar ≥ 44 px;
tanlanmagan blokning asboblari bosilmaydi. Tartib: ↑ ↓ tugmalari (asosiy yo'l) yoki tutqichni ~0,35 s bosib turib sudrash (pointer hodisalari, chetga yaqinlashganda
sahifa aylanadi); klaviatura — Alt+↑/↓.

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

Tozalash qoidalari: HTML maydonlari (`html`, ro'yxat bandlari, belgilar tavsifi) — `paket.sanitize` oq ro'yxati (MathML formulalari ham — docs/paket.md «Formulalar») + rasm teglari olib tashlanadi;
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
Yuqorida: **Ko'rish** (segmentli almashtirgich: Kompyuter 1280 / Planshet 768 / Telefon 390 px — planshet va telefon qurilma ramkasida; saqlashdan keyin avtomatik yangilanadi), **Sifat**, **Versiyalar**, **Sozlamalar**,
**Eksport**, ko'rib chiqish tugmalari.

**Avtosaqlash va ziddiyat.** Har o'zgarishdan 1,2 s keyin dars to'liq saqlanadi (`POST /lessons/{id}` — `rev`). Server joriy `rev` bilan solishtiradi:
mos kelmasa **409** (kim, qachon) — muharrir ogohlantirish chiqaradi: «Oxirgi holatni yuklash» yoki «Mening nusxamni saqlash» (`force` — eski holat
avval versiyaga yoziladi). Kurs sozlamalari va darslar tartibi — kursning o'z `rev` raqami bilan.

**Holat.** O'qituvchi «Ko'rib chiqishga yuborish» (xatolar bo'lsa — 400 ro'yxat bilan) → bo'lim «Tasdiqlash» (tasdiqlangan versiya surati saqlanadi) yoki
«Qaytarish» (sabab majburiy). Tasdiqlangan kurs o'zgartirilsa — qoralamaga qaytadi; ko'rib chiqishdagi kursni o'qituvchi o'zgartirsa ham.

## Pleyer (`app/kurs_player/`)

O'zimizniki (Articulate kodi yo'q), tashqi skriptsiz (faqat YouTube nocookie iframe), oflayn ishlaydi. Muqova → yon menyu (darslar, bajarilganlik) →
dars sahifasi; «Davom etish» bosqichlari; ketma-ket o'tish; test (savollar banki, aralashtirish, urinishlar, o'tish bali, natija); kurs bo'yicha qidiruv;
telefon birinchi; klaviatura, alt matn, fokus belgisi, `prefers-reduced-motion`, qulaylik paneli (pastda «Qulaylik»; ovozli «Tinglash» olib tashlangan); barcha yorliqlar — `content.labels` (o'zbekcha,
kurs sozlamasida o'zgartiriladi). `#lesson=<uid>&block=<id>` — muharrir ko'rish oynasi shu dars/blokni ochadi; `?preview=1` — «Ko'rish rejimi» banneri.

**Ko'rinish — Rise 360 «classic» bilan 1:1** (NEXTID.LMS'da talabalar Rise kurslarini ko'radi; bizning eksport ulardan farq qilmasligi kerak):
Lato (sarlavha, interfeys) + Merriweather (matn) — `app/paket_player/fonts/` (OFL, `OFL.txt`; eksportga `fonts/` bilan tushadi), **faqat yorug'**
(`color-scheme: light` — OS qorong'i rejimida ham oq fon, Rise kabi). Muqova — chapda urg'u rangli panel (muallif, nom, qora «KURSNI BOSHLASH» pill),
o'ngda muqova rasmi, pastda tavsif va darslar ro'yxati (telefonda — rasm ustida qoraytirilgan qatlam, oq pill). Dars — chapda 280px yon panel
(urg'u rangli sarlavha: kurs nomi → muqova, progress chizig'i va «N% BAJARILDI», qidiruv, darslar: belgi, nom, holat halqasi — boshlangan darsda yoy,
yakunlanganda to'la doira), o'ngda: ☰ (kompyuterda yon panelni yig'adi, telefonda chiqaradi) va «Aa», dars sarlavhasi («Dars 1 / 14» kursivda, nom,
muallif, urg'u chiziqcha), bloklar 728px ustunda 30px oraliq bilan: raqamli ro'yxat — urg'u doiralar, akkordeon — ramka, + / −, ochiq bandda urg'u
chiziq; yorliqlar — kulrang sarlavhalar, tanlangani oq + urg'u; kartochkalar — 252px kvadrat, tepada urg'u chiziq; jarayon va vaqt chizig'i —
kulrang tasmada oq kartochkalar; bilimni tekshirish — oq kartochka, radio qatorlar, pill tugma, kulrang izoh paneli (doira ichida ✓/✕); «Davom etish» —
ustun kengligidagi urg'u tugma; dars oxiri — butun kenglikdagi kulrang tasma (keyingi dars nomi). Test darsi — kulrang fonda oq «varaq», «01/08»
hisoblagich. Rise kamchiliklari tuzatilgan: urg'u fonida matn oq (palitra — kontrast ≥ 4,5; Rise'da ko'pincha qora/past kontrast), telefonda yorliqlar
kesilmaydi (gorizontal aylanadi), qidiruv doim ko'rinadi, holat halqasidan tashqari ekran o'quvchisi uchun matn. Ko'rish oynasi (sandbox, opaque
origin) shriftlarni yuklamaydi — tizim shriftlari (Helvetica/Arial, Georgia) bilan ko'rinadi.

**Dizayn: 1 — eski (yuqoridagi Rise ko'rinishi) yoki 2 — yangi** (`content.settings.design`: `classic` | `yangi`). Masofaviy bo'lim tanlaydi:
kurs sozlamasida («Dizayn» — standart / 1 / 2), «Dars tayyorlash»da esa umumiy sozlamada (standart) yoki dars sozlamasida (`app/paket.py` `design`).
Kurs sozlamasi bo'sh bo'lsa — bog'langan darsning (fan/dars) sozlamasi, u ham bo'lmasa 1-dizayn (`kurs.design_of`). 2-dizayn: **bosh sahifa** —
urg'u rangli muqova (rasm bo'lsa — xira fon), umumiy foiz halqasi, «Kursni boshlash / Davom ettirish», bo'limlar kartochkalari (turi bo'yicha
rasm/ikonka: video, matn, taqdimot, mashq, test; holati: Boshlanmagan / Davom etmoqda / Bajarildi / Yopiq; qisqa tarkib: «20 ta slayd · 3 ta fayl»);
**ichki sahifa** — yuqorida «Bosh sahifa», kurs nomi va foiz, 1→N qadamlar chizig'i (telefonda — bo'laklar va «2 / 5»), oq varaqda bo'lim
mazmuni, pastda «Orqaga» va «Keyingi qadam: …» (oxirida «Yakunlash»). Qadamlar: bitta blokli darsda (Dars tayyorlash paketi) — «Davom etish»
tasmalari orasidagi bo'laklar (nomi — tasma yozuvi, «VIDEODARS» → «Videodars»; muqova sarlavhasi/rasmi bosh sahifada), ko'p darsli kursda — har
dars bitta qadam; test darsi — alohida qadam. «Davom etish» `require: interactions` — «Keyingi qadam» mashqlar bajarilguncha faol emas. Qadam
pastki qismi ko'ringanda yoki «Keyingi» bosilganda bajarilgan (`S.d`), darsning hamma qadamlari bajarilsa — dars yakunlandi (LMS kuzatuvi va
baholash 1-dizayn bilan bir xil). Shrift — Manrope. «Davom etish» tasmalari 1-dizayndagi kabi: dars ichidagi keyingi bo'lim oldingisi ko'rilmaguncha
(`require: interactions` bo'lsa — mashqlar bajarilmaguncha) «Navbatda». «Dars tayyorlash» ommaviy eksportida 2-dizayn tanlangan, muharrirga
o'tkazilmagan dars o'tkaziladi va muharrir pleyeri bilan eksport qilinadi — shablonning to'ldirilmagan bandlari paket yo'lidagi kabi tashlab
ketiladi (`export_course(..., omit=)`); bog'langan, manbasi «paket» dars — muharrir nusxasi o'zgartirilmaydi, paket pleyeri bilan eksport
qilinadi va «2-dizayn qo'llanmadi» ogohlantirishi qaytadi. Paket pleyeri (`app/paket_player`, «Avtomatik yig'ish») 2-dizaynni qo'llamaydi.

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

**NEXTID tuzilmasi (xAPI).** NEXTID.LMS yuklangan zipni ochib Rise eksporti tuzilmasini kutadi; tekis tuzilma (`index.html` ildizda) «Index.html fayli
mazmunini o'zgartirishda xatolik» bilan rad etilgan, Rise tuzilmasi esa qabul qilingan va kurs ochilgan (2026-11-17, haqiqiy NEXTID'da).
Shuning uchun `xapi` eksport: kurs (pleyer, `content.*`, `assets/`, `fonts/`) → `scormcontent/`; ildizda — Rise qobig'i (`scormdriver/`, `tc-config.js`)
va `tincan.xml` (launch `scormdriver/indexAPI.html`). Qobiq `app/nextid_shell/rise_shell.zip` dan olinadi (Articulate Rise eksportidagi
`scormdriver/` — uchinchi tomon kodi, Rise litsenziyasi bo'yicha); kurs nomi, id va versiya har eksportda almashtiriladi. `ISFT_CORE_KURS_SHELL=<zip>` —
boshqa qobiq, `off` — o'chirish (tekis tuzilma + eksport ogohlantirishi; testlar shunday ishlaydi). Rise `scormdriver` kursni parametrsiz
(`../scormcontent/index.html#/preview`) ochgani uchun `lms.js` xAPI launch parametrlarini (`endpoint`, `auth`, `actor`) ota kadrlardan (bir domen) ham o'qiydi;
`scrolling="no"` kadrda pleyer aylantirishni `#app` ichida bajaradi (`html.in-frame`). Haqiqiy NEXTID'da `tincan.xml` (bizniki) hali alohida tekshirilmagan.

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
  kontrast** (oq/qora — kurs pleyerida doim, chunki u faqat yorug'; paket pleyerining qorong'i rejimida qora/sariq; havolalar tagiga chiziq, qalin chegaralar, qalin fokus), **o'qish uchun qulay shrift**
  (tizim shriftlari Verdana/Tahoma…, keng harf va so'z oralig'i, kursivsiz), **harakatni kamaytirish** (`prefers-reduced-motion` bilan birga).
  Sozlamalar `localStorage['isft-a11y']` da — har murojaat try/catch: ko'rish oynasi (sandbox) va maxfiy oynada ishlaydi, faqat eslab qolinmaydi
  (panelda izoh). Esc — panel yopiladi, fokus «Aa» ga qaytadi.
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

## «AI bilan tahrirlash» — savol bloklari (`app/kurs_ai.py`)

Rise'dagi «Edit with AI» o'rnida (o'quv videosi: o'qituvchi Word'dan savolni nusxalaydi, ✅ — to'g'ri javob, AI toza «Bilimni tekshirish» savolini tuzadi, o'qituvchi to'g'ri javobni tekshiradi).

**Oqim.** Savol blokida (bilimni tekshirish / test savoli) asboblar qatoridagi ✨ «AI bilan tahrirlash» (telefonda — blok ichidagi tugma) → oyna: chapda matn maydoni (blokning hozirgi savoli `A) … ✅` ko'rinishida to'ldirilgan; Word'dan yopishtiriladi yoki AI'ga ko'rsatma yoziladi), savol turi (avto / bitta / bir nechta / to'g'ri-noto'g'ri / bo'sh joy) va ko'rsatma; o'ngda natija: savol, variantlar (to'g'ri javob ajratilgan), HAR variant izohi, umumiy izohlar. «AI bilan tuzish» / «Qayta urinish» → «Bloknu almashtirish» (yoki «Bekor qilish»). Almashtirgandan keyin blokda eslatma: «AI tuzdi — to'g'ri javobni tekshiring» (✅ siz savolda AI o'zi tanlagani ham aytiladi) va «Avvalgisini qaytarish»; to'g'ri javobni boshqa variantga o'tkazish eslatmani yopadi. Yangi blok: tez qo'shish panelida va blok kutubxonasida «AI bilan savol» (test darsida — «Savol qo'shish» yonida).

**Endpoint.** `POST /api/kurs/lessons/{id}/ai-question` — `{text, hint?, qtype?: auto|single|multi|tf|fill, btype?: knowledge|question}` (mualliflar; boshqa kurs — 403; text ≤ 6000 belgi). Javob: `{block: {type, data}, issues, ai, parsed, answer_guessed, answer_missing?, warnings, more, model, quota}`. Blok bazaga YOZILMAYDI (muharrir uni oddiy avtosaqlash orqali saqlaydi).
1. Deterministik: `test_import.parse_test_text` (✅, «Javob: B», qalin/rangli variant) — kalitsiz ham tuzilma tayyor.
2. AI (`claude_client.call_json`, qat'iy JSON sxema, model `ISFT_CORE_KURS_AI_MODEL`, standart claude-opus-5-5): savol/variantlarni tozalaydi, har variantga izoh va umumiy izoh yozadi, ✅ yo'q bo'lsa to'g'ri javobni tanlaydi (`answer_guessed=true`); yopishtirilgan matn «ma'lumot» sifatida beriladi, fakt o'ylab topilmaydi.
3. Qat'iy tekshiruv: variantlar 2–8, takrorsiz, to'g'ri javob(lar) to'g'ri indeksda (bitta javobli — aynan bitta), To'g'ri/Noto'g'ri tartibi, bo'sh joy javoblari 1–5, ✅ dan kelgan variantlar soni o'zgarmagan; ✅ bilan belgilangan javobni AI o'zgartirsa — o'qituvchi belgisi tiklanadi (ogohlantirish bilan). Yaroqsiz javob — 502 (✅ dan tuzilma bilan).
4. Kalit yo'q → 503 va baribir `block` (`ai=false`, izohsiz); AI xatosi → 502 va `block` (bo'lsa). Kunlik cheklov: `ISFT_CORE_KURS_AI_DAILY` (standart 100, faqat AI chaqirilganda) → 429. Har so'rov `ku_ai` jadvalida (token, xato, taxmin) va audit jurnalida («kurs: AI savol»).

**Ma'lumot modeli.** Yangi maydon yo'q: har variant izohi (`answers[i].feedback`) va umumiy izohlar (`feedback_correct/_wrong`) avvaldan bor edi (muharrir va pleyer — tanlangan variant izohi). «AI tuzdi» eslatmasi — muharrir sessiyasida (saqlanmaydi). Sinov: `tests/test_kurs_ai.py` (soxta Claude), brauzer — `tools/kurs_ai_check.js`.

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
| POST | `/lessons/{id}/ai-question` | mualliflar (AI bilan savol tuzish; bazaga yozmaydi) |
| GET / POST | `/assets/{id}/cues`, `/courses/{id}/vtt` | o'qish — kurs ko'ruvchilari; yozish — mualliflar |
| GET / POST | `/courses/{id}/captions`, `/captions/{id}/cancel` | ro'yxat — kurs ko'ruvchilari; navbatga qo'yish / bekor — `masofaviy`, `masofaviy_xodim` |
| POST/GET | `/api/montaj/kurs-captions/claim`, `/{id}/media`, `/{id}/progress`, `/{id}/result`, `/{id}/fail` | montaj ishchisi (`X-Worker-Token`) |

## Cheklovlar

- Sudrab tashlash — sichqoncha bilan; klaviaturada ↑ ↓ tugmalari. Boy matn — `document.execCommand` (oddiy formatlash yetarli).
- Belgili rasm belgilari muharrirda rasmga bosib qo'yiladi/ko'chiriladi (sudrash yo'q).
- Rise'dagi «scenario», «chart», «code», «storyline» bloklari import qilinmaydi (izohli matn bloki qo'yiladi); Rise kurs bo'limlari (section) — o'tkaziladi.
- Test qamrovi — matn o'xshashligiga asoslangan taxmin.
