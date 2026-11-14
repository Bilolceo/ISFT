# «Dars tayyorlash» — birlashgan bo'lim (shablon bo'yicha yig'ish + bloklar muharriri)

**Kod:** `app/dars.py` (server), `static/dars.js`, `static/dars.css` («Fanlar» yorlig'i), `static/kurs.js` (izohlar paneli, AI tugmasi, bog'lanish tasmasi),
`static/paket.js` (yorliq va dars paneli ilgaklari). Asos — `app/paket.py` (`docs/paket.md`) va `app/kurs.py` (`docs/kurs.md`).
**Testlar:** `tests/test_dars.py`; brauzer — `tools/dars_check.js` (PW va CHROME berilganda test o'zi chaqiradi; skrinshotlar — `DS_OUT`).
**API:** `/api/dars/*` · **Ruxsat resursi:** `rbac.PAKET` (har so'rov audit jurnalida, `dars: …`).

## Nima uchun

NEXTID'da (my.isft.uz) fan sahifasida, masalan, 45 dars: L1–L15 ma'ruza va A1–A30 amaliy (har ma'ruza mavzusiga ikkita amaliy), har biri alohida paket.
Avval «Dars tayyorlash» (shablon bo'yicha avtomatik yig'ish) va «Kurs muharriri» (Rise kabi bloklar) ikki alohida menyu bandi edi. Endi — bitta bo'lim:
fan → darslar to'ri → har darsda avtomatik yig'ish yoki muharrirda erkin tahrirlash; eksport uchun qaysi manba ustunligi aniq ko'rinadi.

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

## Ruxsatlar (qisqacha)

| Lavozim | Fanlar to'ri | O'tkazish, skelet, shablon qo'llash, ommaviy | Shablon tahriri | Izoh | To'xtatuvchi izoh / hal qilish | AI |
|---|---|---|---|---|---|---|
| `masofaviy`, `masofaviy_xodim` | hamma | ha | ha | ha | ha | ha |
| `oqituvchi` | o'z fanlari | o'z fanlari | — | o'z kurslari | — (oddiy izohni hal qiladi) | o'z kurslari |
| `kafedra` | o'z kafedrasi | — | — | o'z kafedrasi | o'z kafedrasi | — |
| rahbariyat, boshqalar | 403 | 403 | 403 | 403 | 403 | 403 |

## Cheklovlar

- Muharrirga o'tkazish bir martalik: keyin paketga yuklangan yangi fayllar muharrir nusxasiga o'zi qo'shilmaydi (ustun manbani «Shablon»ga qaytarish yoki qo'lda qo'shish).
- Ommaviy ish holati server xotirasida: server qayta ishga tushsa, tugamagan ish «uzildi» bo'ladi (yakunlangan natija `ds_jobs`da qoladi).
- Kafedra muharrirda «faqat ko'rish» rejimida: maydonlar ko'rinadi, lekin avtosaqlash o'chiq (server ham 403 qaytaradi).
- AI «eng uzun javob» belgisi — qat'iy uzunlik solishtiruvi; ma'no jihatidan chalg'ituvchilar sifati — o'qituvchi ko'rib chiqadi.
