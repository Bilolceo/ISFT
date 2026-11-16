# «Dars tayyorlash» — birlashgan bo'lim (shablon bo'yicha yig'ish + bloklar muharriri)

**Kod:** `app/dars.py` (server), `static/dars.js`, `static/dars.css` («Fanlar» yorlig'i), `static/kurs.js` (izohlar paneli, AI tugmasi, bog'lanish tasmasi),
`static/paket.js` (yorliq va dars paneli ilgaklari). Asos — `app/paket.py` (`docs/paket.md`) va `app/kurs.py` (`docs/kurs.md`).
**Testlar:** `tests/test_dars.py`, `tests/test_dars_resync.py` (qayta sinxronlash, muharrir ro'yxatidagi fan guruhlari); brauzer — `tools/dars_check.js` (PW va CHROME berilganda test o'zi chaqiradi; skrinshotlar — `DS_OUT`).
**API:** `/api/dars/*` · **Ruxsat resursi:** `rbac.PAKET` (har so'rov audit jurnalida, `dars: …`).

## Nima uchun

NEXTID'da (my.isft.uz) fan sahifasida, masalan, 45 dars: L1–L15 ma'ruza va A1–A30 amaliy (har ma'ruza mavzusiga ikkita amaliy), har biri alohida paket.
Avval «Dars tayyorlash» (shablon bo'yicha avtomatik yig'ish) va «Kurs muharriri» (Rise kabi bloklar) ikki alohida menyu bandi edi. Endi — bitta bo'lim:
fan → darslar to'ri → har darsda avtomatik yig'ish yoki muharrirda erkin tahrirlash; eksport uchun qaysi manba ustunligi aniq ko'rinadi.

## Ikki versiya (taqqoslash uchun, 2026-11-15)

Rise'dan o'tgan bo'lim xodimlari uchun ikki oqim yonma-yon — fan sahifasidagi **«Ko'rinish: A / B»** (brauzerda saqlanadi, `localStorage.dsVer`):

- **A — Konstruktor** (`static/konstruktor.js`, standart): har darsda bitta tugma → uch qadam: **1 Materiallar** (umumiy tashlash maydoni + 4 kartochka:
  videodars — YouTube havola yoki fayl; ma'ruza — Word / skaner PDF; taqdimot — .pptx / .ppt / .pdf; mashq va topshiriqlar — ✅ belgili test Word, glossariy,
  «Savollar»; har biri holati bilan) → **2 Tahrirlash** («Darsni yig'ish» — `convert`, avval o'tkazilgan bo'lsa `resync`; keyin muharrir Rise ko'rinishida,
  yuqorida qadamlar tasmasi) → **3 Nashr** (bloklardagi xatolar, eksport — NEXTID xAPI, ko'rib chiqishga yuborish / tasdiqlash). «← Materiallar» — 1-qadamga qaytadi.
- **B — Yig'ish + muharrir**: avvalgidek — «Avtomatik yig'ish (shablon)», «Muharrirda tahrirlash», «Fayllar».

Ikkala versiyada muharrir standart holda **Rise ko'rinishida** (`docs/kurs.md` — «Rise ko'rinishi»). Shablondagi bo'limlar (VIDEODARS, MA'RUZA MATNI …)
endi `continue` bloki (yozuvi — bo'lim nomi), NEXTID'dagi darslar kabi; «Dars tayyorlash»dan o'tkazilgan kurslar rangi — NEXTID binafsha `#7837A8`.
Brauzer tekshiruvi: `tools/konstruktor_check.js` + `tools/kx_materials_assert.js` (materiallar, rang, subtitr), `tools/bulk_upload_check.js` (ko'p fayl) — hammasi `tests/test_konstruktor.py`dan; `tools/dars_check.js` va `tools/kurs_editor_check.js` — B versiya va klassik muharrir.

### Konstruktor: rang, qator ko'rinishi, materiallar kartochkalari (2026-11-15)

- **Rang:** Konstruktor (`.kx`), «Ko'p faylni yuklash» paneli (`.kxb`) va A versiyadagi dars qatorlari (`.ds-grid.a`) uchun CSS o'zgaruvchisi `--brand-fill` binafsha
  (`#7837A8`) qilib qayta belgilanadi — asosiy tugmalar shu ko'rinishlarda binafsha, ilovaning boshqa joylarida va B versiyada qizil qoladi.
- **Dars qatori (fan sahifasi):** chap — dars raqami belgisi (L2); nomi yo'q dars — «Mavzu nomi kiritilmagan» (xira, qiya; «2-mavzu» o'rinbosari yo'q);
  tayyorlik — 3 ta kichik qadam **Material · Video · Paket** (✓ — bor; tooltip va `aria-label`, `role=list`), keyin «Ko'rib chiqishda» / «Tasdiqlangan» / izoh belgilari;
  bitta asosiy tugma. Atama hamma joyda «Paket» («Eksport» faqat «Eksport manbai» tanlovida qoladi).
- **«Namuna» tasmasi:** fan ro'yxatidan pastga siljib kirilganda Konstruktor sarlavha ostida qirqilib qolardi — endi `kxOpen` sahifani tepaga qaytaradi.
- **Materiallar kartochkalari:** bir xil balandlik (`grid-auto-rows:1fr`), sarlavha va «✓ Tayyor / Bo'sh» belgisi alohida qatorda (to'qnashmaydi), bir xil 20 px ikonkalar,
  YouTube maydoni — to'liq kenglik (ostida «Saqlash» va «Video fayl»), 4-kartochka — qisqa matn, belgilash qoidasi «Batafsil» ostida.
- **Avtomatik subtitr (AI):** faqat video **fayl** yuklangan bo'lsa (YouTube'da yo'q). Mavjud subtitrlar (`ready.video.captions`) chip ko'rinishida; tugma
  `POST /api/paket/courses/{cid}/topics/{key}/captions/auto {"lang":"uz"}` → `{ok, state: queued|exists|unavailable, message}`; server xabari ko'rsatiladi
  (`aria-live`), endpoint hali yo'q (404 «Not Found») — neytral «Hozircha mavjud emas», boshqa xato — serverning o'qiladigan matni.

### Ko'p faylni yuklash (fan sahifasi, `static/konstruktor.js`)

«Fan skeleti» yonidagi **«Ko'p faylni yuklash»** (`#dsBulkUp`) fan sahifasida panel ochadi (Esc — yopish). Oqim: fayllarni tanlash / tashlash → **ko'rib chiqish jadvali**
(fayl → dars, turi, holat; dars va turini o'zgartirish yoki faylni o'tkazib yuborish) → birma-bir yuklash (umumiy jarayon, har fayl foizi va natijasi) → xulosa
(muvaffaqiyatli / xato, «Konstruktorda ochish», «Yuklanmaganlarni qayta yuklash»). Har fayl — mavjud `POST /api/paket/courses/{cid}/topics/{key}/upload?name=…&as=…`
(ruxsat va hajm serverda; mijoz hajmni `PK.meta.limits` bo'yicha oldindan tekshiradi). Xatolar o'qiladigan: 413 (hajm), 403, 429, 5xx, tarmoq; boshqalari — serverning matni.

**Moslashtirish** — sof funksiyalar `kxbParse(name)` / `kxbMatch(files, lessons)` (DOM'siz; `tools/bulk_upload_check.js` node'da 24 nom bilan sinaydi):
1. «raqam + so'z»: `1-ma'ruza`, `3-mavzu`, `5 amaliy`; 2. «so'z + raqam»: `L3`, `A5`, `maruza_07`, `lab4`, `mt_2`, `dars3`; 3. nom boshidagi raqam (`07.docx`, ma'ruza deb olinadi);
4. istalgan alohida raqam («taxminiy» deb belgilanadi). So'z → dars turi: ma'ruza/mavzu/dars/L → L; amaliy/A → A; seminar/S; laboratoriya/lab; mustaqil/MT.
5. Yillar (2024) va `v2` kabi qo'shimchalar raqam hisoblanmaydi. Yuklash turi: `.docx/.doc/.txt` — matn, `.pptx/.ppt/.pdf` — taqdimot, `.mp4/.mov/.webm` — video, `.srt/.vtt` — subtitr,
`.xlsx` — qo'shimcha fayl; nomida «test» bo'lgan Word/PDF/txt — test. Moslanmagan (raqam yo'q, dars yo'q, turi noma'lum) fayllar jadvalda ajratiladi — darsni qo'lda tanlash mumkin;
bir darsga bir turdagi ikkita fayl — «takror — oldingisini almashtiradi».

### Dars kartochkasi, unikal kod va taqdimot zanjiri (2026-11-15)

Har dars qatorida **«Kartochka»** (`static/dars_card.js`, `docs/studio.md` — «Dars kartochkasi»): unikal kod (`2_ATT_dasturiyinjiniring_L2`), kafedra, o'qituvchi, taqdimot versiyalari (o'qituvchi «Taqdimot»dan yuborgan),
montajlangan video holati, matn, jurnal, **«Dars yaratish»** (Konstruktorni shu ma'lumotlar bilan to'ldirib ochadi) va **ZIP**. «Fanlar» daraxti (kurs → yo'nalish → fan) mantiqi `static/lesson_picker.js` (`lpLevels`) ga chiqarilgan —
«Taqdimot»dagi dars tanlagich ham shuni ishlatadi (`docs/taqdimot.md`).

## Menyu va yo'nalish

- Menyuda bitta «Dars tayyorlash» bandi (`data-v="paket"`). «Kurs muharriri» bandi olib tashlandi; `go("kurs", {cid})` — **taxallus**: muharrir ochiladi,
  menyuda «Dars tayyorlash» belgilanadi, sarlavha «Dars tayyorlash › Muharrir» (`app.js` `MOD_ALIAS`).
- Bo'limlar kaliti: `kurs` kaliti yo'q, `modules.ALIASES = {"kurs": "paket"}` — «Dars tayyorlash» o'chirilsa, muharrir ham o'chiq.
- «Dars tayyorlash» yorliqlari: **Fanlar** (kirish sahifasi) · Holat · Darslar · Ommaviy · Sozlamalar (bo'lim); o'qituvchi — Fanlar, Darslarim; kafedra — Fanlar, Holat, Darslar.

## Fan → NEXTID darslar to'ri (`GET /subjects/{cid}`)

Har dars (L, A, S, Lab, MT — `paket.lessons`): kod, nom, holat belgilari — **material** (matn yoki taqdimot), **video**, **paket/eksport** (oxirgi versiya yoki muharrir eksporti),
**ko'rib chiqishda**, **tasdiqlangan**, **ochiq izohlar** (to'xtatuvchilari bilan), **eksport manbai**. Ko'rib chiqish/tasdiq — ustun manba bo'yicha: `paket` — paket versiyasi
holati, `kurs` — muharrir kursi holati. Amallar: «Avtomatik yig'ish (shablon)» (`POST /api/paket/…/build`), «Muharrirda tahrirlash» (o'tkazish yoki ochish), «Fayllar» (dars paneli).

## Paket → muharrir (`POST /subjects/{cid}/lessons/{key}/convert`)

`paket.gather()` natijasi Kurs muharriri kursiga (bitta NEXTID darsi = bitta kurs: asosiy dars + yakuniy test darsi) o'tkaziladi, kafedra shabloni tartibida:

| Paket bloki | Muharrir bloklari |
|---|---|
| muqova | sarlavha (dars sarlavhasi) + rasm («hero», kurs muqovasi ham) |
| video (YouTube / fayl + subtitr + poster) | `video` (fayllar `ku_assets`ga ko'chiriladi — qattiq havola yoki nusxa) |
| reja | sarlavha + raqamli ro'yxat |
| ma'ruza matni | `h2/h3` → sarlavha; `figure` → rasm (izoh, alt); `table` → jadval (qatorlar aynan); qolgan matn → paragraf bloklari (≤ 15 000 belgi bo'laklar) |
| xulosalar, adabiyotlar | sarlavha + ro'yxat |
| taqdimot | rasmli slaydlar → galereya (karusel), matnli → akkordeon; .pptx / .pdf → fayl bloklari |
| qo'shimcha fayllar | fayl bloklari |
| kartochkalar | `flashcards` |
| test: Test bank savollari | yakuniy test darsi (`question`: bitta/bir nechta javob, to'g'ri-noto'g'ri, bo'sh joy) |
| test: moslashtirish / saralash | `matching` / `sorting` bloklari |
| topshiriq, o'z-o'zini baholash | sarlavha + matn + ro'yxat |

Bog'lanish — `ds_links(dl_course_id, lkey, ku_course_id, authority, tpl_id, src)`: muharrirda «Dars tayyorlash: fan · L3 · eksport uchun ustun manba» tasmasi
(`course.dars`), paket dars panelida — `topic_view.kurs_link` va «Muharrirda ochish». O'tkazilgandan keyin ustun manba — `kurs` (muharrir); fan to'rida
almashtiriladi (`POST …/authority`). Qayta bosish — o'sha kurs (dublikat yo'q).

## Paketdan qayta sinxronlash (`GET|POST /subjects/{cid}/lessons/{key}/resync {preview}`)

O'tkazilgandan keyin paketga yangi / o'zgargan mazmun (video havola yoki fayl, taqdimot, ma'ruza matni, reja, qo'shimcha fayllar, xulosalar,
kartochkalar, mashqlar, muqova …) qo'shilsa, paket dars panelida (muharrir tasmasi ostida) — **«Yangi fayllar bor»** (qaysi bandlar, nechta blok
qo'shiladi / yangilanadi, muallif bloklari soni) va **«Muharrirga qo'shish»** (oldin ko'rish oynasi: har band bo'yicha +/~/− va jami).

- **Kuzatuv yozuvi** — `ds_sync(dl_course_id, lkey, ku_course_id, sig, slots, synced_at, synced_by, n)`: o'tkazishda va har sinxronlashda yoziladi.
  `slots[kalit] = {fp, ed}`: `fp` — shu shablon bandining paket mazmuni barmoq izi (`blocks_from_gather` fayllarsiz: fayl o'rnida yo'l + nom/o'lcham/vaqt
  yoki sha), `ed` — muharrirdagi shu bandning shablon bloklari xeshi; `sig` — `paket.source_sig` (o'zgarmagan bo'lsa tez javob, yig'ish yo'q).
- **Har band uchun amal** (`dars.resync_actions` — sof funksiya): paket mazmuni o'zgarmagan — tegilmaydi (muallif bloklarni o'chirgan bo'lsa ham qayta
  qo'shilmaydi); bandda blok yo'q yoki bo'sh (to'ldirilmagan, skelet) — **to'ldiriladi**; muharrirda o'zgartirilmagan (`ed` mos) — **yangilanadi**;
  muallif shablon blokini o'zgartirgan — **tegilmaydi** («muharrirda o'zgartirilgan bandlar» sifatida ko'rsatiladi); kuzatuv yozuvi yo'q va mazmun
  bor (eski o'tkazishlar) — tegilmaydi, birinchi sinxronlashdan keyin kuzatiladi.
- **Yozish** (`dars.resync_apply` — sof funksiya): shablon bloklari uid'lari (`tp<kalit><nn><hex4>`) joyida yangilanadi, yetmagani bandning oxirgi blokidan
  keyin (blok bo'lmasa — shablon tartibidagi keyingi mavjud band oldiga) qo'shiladi, ortiqchasi olinadi. **Muallif bloklari (boshqa uid) hech qachon
  o'zgarmaydi va o'chmaydi**, boshqa bandlar ham. Faqat yangilanadigan bandlar fayllari `ku_assets`ga ko'chiriladi.
- `preview=false`: kurs oldin versiyaga saqlanadi («Paketdan yangilashdan oldin»), dars va kurs `rev` oshadi (ochiq muharrir 409 bilan ogohlantiradi),
  `ku_log` va audit (`dars: paketdan muharrirga qo'shildi`), `ds_sync` yangilanadi — bayroq o'chadi, keyingi o'zgarishda qaytadi. Qayta bosish — o'zgarishsiz.
- Ruxsat — o'tkazish bilan bir xil (`masofaviy`, `masofaviy_xodim`, o'qituvchi — o'z fani; kafedra va boshqalar — 403, audit).

## Fan skeleti (`POST /subjects/{cid}/skeleton {ratio, apply, with_kurs}`)

Mavzular ro'yxatidan (tasdiqlangan sillabus > kontent monitoringi, `paket._titles`) — L1..Ln (n = `dl_courses.topics`) va A1..A(ratio·n): har mavzuga `ratio` (0–4, standart 2)
amaliy, nomi — mavzu nomi «(1-qism)», «(2-qism)», bog'lanish `topic_ref`. `with_kurs` — har dars uchun muharrirda kafedra shabloni bo'yicha bloklar (to'ldirilmagan bloklar
«xato» beradi — to'ldirilmaguncha eksport bo'lmaydi). `apply=false` — ko'rish (baza o'zgarmaydi). Mavjud nomlar va bog'langan kurslar o'zgarmaydi (idempotent).
Skelet darslarining ustun manbasi — `paket` (fayllar yuklanib yig'iladi); muharrirda to'ldirilsa — «Muharrir»ga almashtiriladi.

## Kafedra shabloni (`GET/POST /templates`) va «Shablonni qo'llash»

`ds_templates(tkey, version, layout)`: `tkey` — `global` yoki `dep:<kafedra>`; har saqlash — yangi versiya (tarix saqlanadi). Tahrirlaydi — faqat `masofaviy`,
`masofaviy_xodim`. `layout = {maruza: [...], amaliy: [...]}` (S/Lab/MT — amaliy tartibi), band: `{key, kind, text?}`; turlar: muqova, bo'lim sarlavhasi, video, reja,
matn, xulosalar, adabiyotlar, taqdimot, fayllar, kartochkalar, mashqlar, topshiriq, o'z-o'zini baholash, «Davom etish», ajratgich, yakuniy test.

**Shablon bloklari va muallif bloklari.** Shablon bloki uid'i — `tp<kalit><nn><hex4>` (kurs `_UID_RX`ga mos, avtosaqlashda o'zgarmaydi); boshqa uid — muallif bloki.
`POST /subjects/{cid}/template/apply {template_id, preview}` (`dars.reapply` — sof funksiya):
- muallif bloklari o'z «langari» (oldidagi eng yaqin shablon bandi) bilan ko'chadi, mazmuni o'zgarmaydi; langari olib tashlangan bo'lsa — eng yaqin saqlangan oldingi bandga;
- qolgan band — mazmuni saqlanadi; statik band (bo'lim sarlavhasi, «Davom etish», ajratgich) — matni shablondan yangilanadi;
- yangi band — bo'sh blok; olib tashlangan band — bo'sh (o'zgartirilmagan) bo'lsa o'chadi, to'ldirilgan bo'lsa **muallif blokiga aylanadi** (yo'qolmaydi);
- yakuniy test bandi qo'shilsa — test darsi qo'shiladi; olib tashlansa — bo'sh test darsi o'chiriladi.
`preview=true` — har dars va jami farq (qo'shiladi, olib tashlanadi, yangilanadi, ko'chadi, muallif bloklari, muallifga aylanadi); qo'llashda har kurs oldin versiyaga
saqlanadi («Shablon qo'llashdan oldin»), keyin yoziladi, `rev` oshadi. Bir xil shablonni qayta qo'llash — o'zgarishsiz.

## Ommaviy yig'ish va eksport (`POST /subjects/{cid}/bulk {mode, keys}` → `GET /jobs/{id}`)

Fon ishi (thread): har dars ustun manbasidan — `kurs` → `kurs.export_course` (xatolari bo'lsa — dars «xato» bilan o'tkaziladi), `paket` → `paket.build_topic`.
Jarayon — `GET /jobs/{id}` (bajarildi / jami, joriy dars, natijalar, har dars uchun yuklab olish havolasi); natija — `GET /jobs/{id}/download`: bitta .zip ichida
har dars alohida .zip (`ISFT_<fan>_<L01>_<tur>.zip`, ZIP_STORED, oqim bilan). Ish holati xotirada, yakuni `ds_jobs`da.

## AI: hujjatdan dars (`POST /kurs/{kcid}/ai-lesson?name=…`, tana — .docx / .pdf / .txt ≤ 50 MB)

1. Kalit yo'q bo'lsa — **503** «AI ulanmagan — administratorga murojaat qiling…» (tana o'qilmaydi, hech narsa yaratilmaydi). Kunlik cheklov — `ISFT_CORE_PK_DAILY`.
2. Manba: .docx — `paket.docx_lecture` (rasmlar izohi bilan, jadvallar; zip/rasm bombasi tekshiruvi), .pdf/.txt — `taqdimot_extract`; `paket.structure_text` → bo'limlar (`h2`,
   bo'lmasa `h3`). Rasm va jadvallar AI'ga yuborilmaydi — manbadan aynan bloklarga qo'yiladi.
3. Claude (`claude_client.call_json`, qat'iy sxema `AI_SCHEMA`): har bo'lim — paragraflar (har biri `quote` bilan), ixtiyoriy akkordeon/yorliqlar, bilimni tekshirish
   savollari; kartochkalar; yakuniy test (`sid` bilan). **Faqat fan/mavzu nomi va ma'ruza matni yuboriladi** — talaba ma'lumoti yo'q.
4. Saqlashdan oldingi qat'iy tekshiruvlar (`dars.build_lesson` — sof funksiya, testda soxta `call`):
   - **o'ylab topilgan fakt yo'q:** paragraf/kartochka/akkordeon bandi iqtibosi manbada aynan bo'lishi (`testbank._quote_in`) va matnidagi har bir son manbada uchrashi shart — aks holda tashlanadi;
     savol iqtibosi ham manbada bo'lishi shart;
   - **faqat o'zbek lotin:** kirill → lotin (`dars.translit`: ш→sh, ч→ch, ғ→g', ў→o', қ→q, ҳ→h, ё/ю/я, «е» — so'z boshida/unlidan keyin «ye», ц→ts, ъ→', ь — tushadi;
     «Ш»→«Sh», «ШАҲАР»→«SHAHAR»); inglizcha qoldiq (≥ 4 so'z, ≥ 25 % inglizcha yordamchi so'zlar) — tashlanadi;
   - **qamrov:** har bo'lim kamida bitta savol bilan (bilimni tekshirish yoki yakuniy test); yetmasa — shu bo'limlar uchun bitta qo'shimcha so'rov; baribir yetmasa — **422**, saqlanmaydi;
   - **«to'g'ri javob eng uzun»:** qat'iy eng uzun bo'lsa belgilanadi va chalg'ituvchilar **bir marta** qayta so'raladi (soni o'sha, noyob, to'g'ri javobga teng emas); tuzalmaganlari
     `flag_longest` bilan natijada ko'rsatiladi;
   - **o'rinlar:** to'g'ri javob o'rinlari aylanma taqsimlanadi (k-savol → k mod n), tartib va chalg'ituvchilar seed bo'yicha deterministik aralash (A/B/C/D farqi ≤ 1).
5. Natija — kursga yangi dars (reja, bo'lim sarlavhalari, paragraflar, rasm, jadval, akkordeon/yorliqlar, bilimni tekshirish, «Davom etish», kartochkalar) va yakuniy test darsi;
   versiya surati; hisobot (bo'limlar, tashlanganlar, kirill, inglizcha, o'rinlar, belgilar, tokenlar). Tokenlar va natija — `ds_ai` (tb_gen kabi: model, ok, ms, xato, in/out tokenlar,
   so'rovlar soni, statistika). Xato: AI — 502, to'siq — 422.

## Izohlar (ko'rib chiqish) va tasdiq to'sig'i

`ds_comments`: kurs, dars, blok uid, `parent_id` (tarmoq), muallif, rol, matn, `blocking`, `mention_author`, holat `ochiq` / `hal`.
- Kim: bo'lim — istalgan kurs; kafedra — o'z kafedrasi fanlariga bog'langan kurslar (`kurs.scope` — kafedra endi bu kurslarni faqat ko'radi); o'qituvchi (kurs muallifi) — javob va
  oddiy izoh. **To'xtatuvchi** izohni faqat ko'rib chiquvchi (bo'lim, kafedra) qo'yadi va hal qiladi / qayta ochadi; oddiy izohni muallif ham hal qiladi.
- `GET /kurs/{kcid}/comments`, `POST /kurs/{kcid}/comments {lesson_id, block_uid, text, blocking, mention_author, parent_id}`, `POST /comments/{id}/resolve|reopen`.
  Blok mavjud bo'lishi (saqlangan) shart — 400. Har amal `ku_log` va audit jurnalida.
- Muharrirda: blok sarlavhasida izoh belgisi (soni; to'xtatuvchi — qizil), yuqorida «Izohlar N», o'ngda chiquvchi panel (yangi izoh, javob, hal qilish / qayta ochish,
  «barcha darslar», «hal qilinganlar ham»); telefonda — butun kenglik.
- **To'siq:** `kurs` — ko'rib chiqishga yuborish (`submit`) va tasdiqlash (`approve`); `paket` — darsning muharrir nusxasida izoh bo'lsa, paketni yuborish / tasdiqlash.
  Ochiq to'xtatuvchi izoh bo'lsa — **409** `{gate: true, blocking: N}`; `override` (sabab ≥ 10 belgi) — o'tkaziladi, `ds_overrides` va audit («izohlar to'sig'i aylanib o'tildi»).
- Bildirishnoma («Mening vazifalarim» / qo'ng'iroqcha, `paket.pending` orqali): o'qituvchiga — o'z kurslaridagi ochiq to'xtatuvchi yoki o'zini eslatgan izohlar; bo'limga —
  oxirgi javobi muallifniki bo'lgan ochiq to'xtatuvchi izohlar.

## Dars kodi: saqlanadi (`course_code_store`)

Fan kodi (`2_ATT_dasturiyinjiniring`) BIR MARTA beriladi va `course_code_store(course_id, code UNIQUE, created_at)` da saqlanadi: fan/yo'nalish nomi yoki yangi semestr
qo'shilsa ham o'zgarmaydi. Ishga tushirishda mavjud kurslarga hozirgi qoida bilan bir martalik to'ldirish (takrori hech narsani o'zgartirmaydi); keyin qo'shilgan kurs: asosiy
kod band bo'lsa `_<sem>s`, u ham band bo'lsa `_<sem>s_<kurs id>` — UNIKAL. Kirill nomlar lotinga o'giriladi (`slug_translit`), ʻ ' ‘ ’ olib tashlanadi. Kurs o'chirilsa kodi
tozalanadi va uning yuborilgan taqdimotlari «yetim» bo'ladi (id qayta ishlatilsa yangi kurs eski versiyalarni olmaydi; o'chirish keyingi kod so'rovida aniqlanadi).
`GET /subjects/{cid}` darslarida: `pres_version`, `pres_at`, `dept_sent`, `video_wait`.


## Ruxsatlar (qisqacha)

| Lavozim | Fanlar to'ri | O'tkazish, qayta sinxronlash, skelet, shablon qo'llash, ommaviy | Shablon tahriri | Izoh | To'xtatuvchi izoh / hal qilish | AI |
|---|---|---|---|---|---|---|
| `masofaviy`, `masofaviy_xodim` | hamma | ha | ha | ha | ha | ha |
| `oqituvchi` | o'z fanlari | o'z fanlari | — | o'z kurslari | — (oddiy izohni hal qiladi) | o'z kurslari |
| `kafedra` | o'z kafedrasi | — | — | o'z kafedrasi | o'z kafedrasi | — |
| rahbariyat, boshqalar | 403 | 403 | 403 | 403 | 403 | 403 |

## Cheklovlar

- Paketdan qayta sinxronlash qo'lda («Muharrirga qo'shish») — avtomatik emas. Yakuniy test darsi savollari va statik bandlar (bo'lim sarlavhasi,
  «Davom etish», ajratgich) sinxronlanmaydi; paketdan olib tashlangan mazmun muharrirdan o'chirilmaydi; muallif o'zgartirgan shablon bandi
  yangilanmaydi (qo'lda). Bu funksiyadan oldin o'tkazilgan darslarda birinchi sinxronlash faqat bo'sh / yo'q bandlarni to'ldiradi, keyin to'liq kuzatiladi.
- Ommaviy ish holati server xotirasida: server qayta ishga tushsa, tugamagan ish «uzildi» bo'ladi (yakunlangan natija `ds_jobs`da qoladi).
- Kafedra muharrirda «faqat ko'rish» rejimida: maydonlar ko'rinadi, lekin avtosaqlash o'chiq (server ham 403 qaytaradi).
- AI «eng uzun javob» belgisi — qat'iy uzunlik solishtiruvi; ma'no jihatidan chalg'ituvchilar sifati — o'qituvchi ko'rib chiqadi.
