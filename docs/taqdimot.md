# Taqdimot tayyorlash (o'qituvchi)

O'qituvchi ma'ruza materialini yuklaydi. Tizim **ISFT rasmiy shablonida** taqdimot rejasini tuzadi. O'qituvchi rejani tahrirlaydi va tayyor **.pptx** faylini yuklab oladi.

Kod joylashuvi:
- `app/taqdimot.py`: API, AI, dars bilan bog'lash va yuborish (versiyalar).
- `app/taqdimot_extract.py`: materialni o'qish.
- `app/taqdimot_render.py`: .pptx yaratish.
- `app/assets/taqdimot_shablon.pptx`: shablon.
- `static/taqdimot.js`, `static/taqdimot.css`: sahifa.
- `static/lesson_picker.js`, `static/lesson_picker.css`: umumiy dars tanlagich (kurs → yo'nalish → fan → dars); «Dars tayyorlash → Fanlar» daraxti (`static/dars.js`) ham shu `lpLevels` dan foydalanadi.
- `app/lesson_card.py`, `static/dars_card.js`: dars kartochkasi (`docs/studio.md`).

## Kim foydalanadi

| Lavozim | Imkoniyat |
|---|---|
| O'qituvchi | O'z taqdimotlarini yaratadi, tahrirlaydi, yuklab oladi va o'chiradi |
| Kafedra mudiri | O'z taqdimotlari bilan xuddi o'qituvchi kabi ishlaydi. «Kafedra taqdimotlari» bo'limida o'z kafedrasi o'qituvchilarining taqdimotlarini ko'radi va yuklab oladi, lekin tahrirlay olmaydi |
| Boshqa lavozimlar | 403 qaytadi, so'rov audit jurnaliga yoziladi |

Yuborish va dars bilan bog'lash — faqat o'z yuklamasidagi fan darsiga (`dl_courses.teacher_id`); yangi ruxsat darajasi qo'shilmagan (resurs `presentations`, studiya uchun `studio`, kartochka uchun `paket`).

Har bir amal audit jurnaliga `presentations` resursi bilan yoziladi: yuklash, reja tuzish, tahrir, pptx yaratish, yuklab olish, o'chirish va rad etilgan urinishlar.

## Ish tartibi

0. **Dars tanlash** (yangi, qo'lda yozilmaydi — `## Dars kodi va yuborish` bo'limiga qarang).
1. **Material.**
   - Qabul qilinadigan turlar: Word (.docx), PDF (rasmlari bilan) yoki matn (.txt). Matnni sahifaga to'g'ridan-to'g'ri yozish ham mumkin.
   - Hajm 20 MB gacha.
   - Fayl turi kengaytmasiga qarab emas, fayl ichidagi belgilar (sehrli baytlar) bo'yicha tekshiriladi.
   - Word fayldan sarlavhalar, xatboshilar, ro'yxatlar, jadvallar, rasmlar va formulalar (OMML) o'qiladi. Formulalar chiziqli matnga aylantiriladi.
   - PDF fayldan sahifa matni va rasmlar olinadi.
   - Ixtiyoriy maydonlar: mavzu nomi, taxminiy slaydlar soni va izoh (auditoriya, urg'u). Fan va mavzu raqami endi qo'lda emas — tanlangan darsdan olinadi.
2. **Reja.**
   - AI ulangan bo'lsa, rejani Claude tuzadi.
   - AI ulanmagan bo'lsa, reja hujjat tuzilmasidan tuziladi: har bir sarlavha alohida slayd bo'ladi, xatboshilardan bandlar olinadi, rasmlar alohida rasm slaydiga qo'yiladi. «Nazorat savollari», «Adabiyotlar», «Topshiriqlar» va «Xulosa» bo'limlari nomidan taniladi.
3. **Tahrir.**
   - Slaydni yuqoriga yoki pastga surish, turini o'zgartirish, sarlavha va matnni tahrirlash mumkin.
   - Rasmni almashtirish, slayd qo'shish va o'chirish mumkin. O'chirilgan slaydni «Bekor qilish» tugmasi bilan qaytarsa bo'ladi.
   - Har bir slaydga ma'ruzachi izohi yoziladi. U .pptx faylidagi izohlar maydoniga tushadi.
4. **PPTX.** «PPTX yaratish» tugmasi faylni tayyorlaydi, keyin «Yuklab olish» tugmasi chiqadi. Barcha taqdimotlar «Mening taqdimotlarim» bo'limida saqlanadi.
5. **Yuborish.** Taqdimotni ko'rib chiqqach — BITTA tugma: **«Studiyaga va masofaviy bo'limga yuborish»**.

Slayd turlari: reja, ta'rif, nazariya, ikki ustun, qadamlar, ishlangan misol (shart, yechim, javob, tekshiruv), rasm, topshiriqlar, nazorat savollari, xulosa (2×3 kartochka), adabiyotlar.

## Dizayn qoidalari (ISFT shabloni)

- **Slaydlar tartibi:** birinchisi titul (fan nomi katta harflar bilan, «N-mavzu:», mavzu nomi va qo'shimcha satr), ikkinchisi «REJA:». Oxirgi slayd doim «E'TIBORINGIZ UCHUN RAHMAT!».
- **Shriftlar:** asosiy matn Times New Roman, formulalar Cambria Math. Matnda `**qalin**` yozuvi qalin chiqadi; `$x^{2}$` va `$a_{1}$` daraja va indeks bo'lib chiqadi.
- **Sarlavha:** qizil panel ustida, oq rangda, 26 pt.
- **Joylashuv:** kontent faqat o'ng qismda (x = 285…920 pt) joylashadi, chap tomon logotip uchun bo'sh qoladi. Pastki chegara 520 pt.
- **Ranglar:** aksent #B00000, kartochka foni #FBEAEA, kulrang blok #F2F2F2.
- **Shrift o'lchami:** matn 14 pt dan kichik bo'lmaydi. Kontent sig'masa, slayd bo'linadi va keyingisining sarlavhasiga «(davomi)» qo'shiladi. Slaydlar soni kontentga qarab o'zgaradi.

## AI (Claude API)

- **Kalit:** faqat **muhit o'zgaruvchisidan** olinadi: `ANTHROPIC_API_KEY`. Kalitni kodga, faylga yoki chatga yozmang.
- **Model:** standart `claude-opus-5-5`. Boshqasini `ISFT_CORE_PRES_MODEL` orqali tanlash mumkin, masalan `claude-sonnet-5-5` (arzonroq) yoki `claude-haiku-5-5` (eng arzon).
- **Claude'ga yuboriladigan ma'lumot:** faqat yuklangan material, ya'ni matn (60 000 belgigacha) va 8 tagacha rasm. Talabalar ma'lumoti yuborilmaydi.
- **Javob shakli:** qat'iy JSON sxema (structured outputs). Model rad etsa, Anthropic tavsiya qilgan zaxira model avtomatik ishlaydi (`fallbacks: "default"`).
- **Xatolar:** kalit noto'g'ri bo'lsa, so'rovlar cheklovi oshsa, internet bo'lmasa, javob kechiksa yoki material juda katta bo'lsa, foydalanuvchiga tushunarli o'zbekcha xabar chiqadi.
- **Holat ko'rsatkichi:** sahifada va `/api/status` javobida (`taqdimot.engine` va `taqdimot.label`) qaysi rejim ishlayotgani ko'rinadi: «AI: Claude» yoki «AI siz (shablon)».

### Railway'da kalitni o'rnatish

1. Railway loyihasini oching, `ISFT` servisini tanlang va **Variables** bo'limiga o'ting.
2. **New Variable** tugmasini bosing. Nomi: `ANTHROPIC_API_KEY`. Qiymati: console.anthropic.com saytida yaratilgan API kalit (`sk-ant-api…` bilan boshlanadi).
3. Ixtiyoriy: `ISFT_CORE_PRES_MODEL` (model) va `ISFT_CORE_PRES_DAILY` (kunlik cheklov, standart qiymati 20).
4. Saqlang. Railway servisni qayta ishga tushiradi va sahifada «AI: Claude» belgisi paydo bo'ladi.

Kalit qo'shilmasa ham bo'lim ishlaydi, faqat reja AI siz tuziladi.

## Cheklovlar

- Fayl hajmi 20 MB gacha. Faqat .docx, .pdf va .txt qabul qilinadi.
- Har bir foydalanuvchi kuniga 20 ta reja tuzishi mumkin (`ISFT_CORE_PRES_DAILY`). Rejani qayta tuzish ham shu songa kiradi, PPTX yaratish esa kirmaydi.
- Fayllar `db.DATA_DIR/taqdimot/<id>/` papkasida saqlanadi: manba fayl, material.json, rasmlar (`img/`) va `taqdimot.pptx`.
- Skaner qilingan PDF'da matn bo'lmaydi. Bunday hollarda faqat rasmlar slaydga tushadi, shuning uchun matnli variantini yuklash tavsiya etiladi.

## Dars kodi va yuborish (Taqdimot → Studiya → Masofaviy bo'lim)

Zanjirning yagona kaliti — darsning **unikal kodi**: `paket.lesson_unique_code` → `2_ATT_dasturiyinjiniring_L2` (fan kodi `<kurs>_<YO'NALISH>_<fan>` + `_L2` / `_A1`).
Yangi parallel identifikator yo'q: kod darsning (course_id, lkey) bog'lanishidan hisoblanadi — studiya bandi (`st_bookings`), paket (`pk_*`) va taqdimot shu juftlik bilan bog'lanadi.

**1. Dars tanlash.** «Yangi taqdimot» sahifasida fan va mavzu raqami matn maydoni emas: **kurs (1–4) → ta'lim yo'nalishi → fan → dars (L1, A1 …)** tanlanadi.
Faqat o'qituvchining **O'Z yuklamasidagi** fanlar chiqadi (`dl_courses.teacher_id`, `paket.scope` bilan bir xil ko'lam), faqat L va A darslari (studiya shularni tayyorlaydi).
Tanlangach kod, kafedra, o'qituvchi, fan va dars ko'rinadi. Bitta kurs / yo'nalish / fan bo'lsa — bosqich o'zi tanlanadi. Tanlagich `static/lesson_picker.js` (umumiy: `lpLevels`, `lpPicker`);
«Dars tayyorlash → Fanlar» daraxti ham `lpLevels` ni ishlatadi (mantiq nusxalanmagan). «Darsni keyinroq belgilayman» belgisi (yoki o'qituvchi yuklamasida fan bo'lmaganda, masalan kafedra mudiri)
— taqdimot darssiz yaratiladi.

**2. Bog'lanmagan eski taqdimotlar buzilmaydi.** `pres_decks` ga `course_id`, `lkey`, `lesson_code`, `sent_version`, `sent_at` ustunlari `ALTER` bilan qo'shiladi (`init` takror ishlaydi, eski ma'lumot saqlanadi,
`course_id = NULL` — bog'lanmagan). Muharrirda «Darsni belgilash» (`POST /decks/{id}/lesson`) fan va mavzu raqamini darsdan o'rnatadi (titul o'zgargani uchun PPTX qayta yaratiladi).
Yuborilgan taqdimotning darsi o'zgartirilmaydi (409).

**3. Yuborish** (`POST /decks/{id}/send {note?}`) — shartlar: dars belgilangan, PPTX yaratilgan (tahrirdan keyin qayta yaratilmaguncha yuborilmaydi — eskirgan fayl ketmasin), fan o'qituvchining o'ziniki
(boshqa fan — **403 + audit** `taqdimot: begona fan`; kafedra mudiri va boshqa rollar — 403). Bitta amalda:
- yangi **versiya** (`pres_sends`, `UNIQUE(course_id, lkey, version)`): dars kodi o'zgarmaydi, v1 → v2; pptx (va serverda LibreOffice bo'lsa PDF) `db.DATA_DIR/taqdimot/sends/<kurs>_<dars>/vN/` ga saqlanadi,
  **eski versiyalar fayli bilan tarixda qoladi** (taqdimot o'chirilsa ham);
- taqdimot darsning paketiga qo'yiladi (`paket.upload_slides` — ilgak, qayta yozilmagan; `pk_topics.deck_id` bog'lanadi): montajda slaydlar PDF'dan, «Dars yaratish»da taqdimot slaydlari paketdan olinadi.
  Paketga qo'yish xato bersa yuborish bekor bo'lmaydi (`paket_error`);
- studiya: kurs ishlab chiqarish rejasiga qo'shiladi (`st_plan`; rejadan olingan bo'lsa qaytarilmaydi), `st_log` ga «taqdimot yuborildi» yoziladi (`studio.on_presentation`);
- **bildirishnoma ikkala tomonga** (mavjud «Mening vazifalarim» / qo'ng'iroqcha mexanizmi — `studio.mywork_items`; yangi xabar shinasi yo'q): operatorga «Yangi taqdimot: <kod> · v2», masofaviy bo'limga
  «Taqdimot yuborildi: <kod> · v2». Har tomonning o'z «ko'rildi» belgisi bor (`studio_ack_at`, `dept_ack_at`): operator studiya tafsilotini, bo'lim dars kartochkasini ochgach xabar o'chadi;
  yangi versiya — yana yangi xabar (faqat oxirgi versiya uchun);
- audit: `taqdimot: studiyaga va bo'limga yuborildi`.

**4. Versiyalar.** Muharrirda «Yuborilgan versiyalar» oynasi: v2, v1 … (sana, slayd, yuborgan, izoh, studiya / bo'lim ko'rdimi, .pptx va .pdf yuklab olish). Studiya va masofaviy bo'lim doim eng yangisini ko'radi.

**Cheklovlar (zanjir).** Taqdimot faqat L va A darslariga bog'lanadi (studiya darslari). Kafedra mudiri (o'z yuklamasi bo'lmasa) taqdimotni darssiz yaratadi, yubora olmaydi. PDF nusxa faqat serverda LibreOffice
bo'lsa saqlanadi (aks holda faqat .pptx; PDF so'ralsa 404). Xabarlar «Mening vazifalarim» (pull) orqali — Telegram'ga alohida push yo'q. Yuborish fon hisobida kunlik AI cheklovga kirmaydi.

## Tuzatish bosqichi: xavfsizlik, versiyalar, kod barqarorligi

- **Ko'p oqimlilik.** Har modulning yozish qulfi (`db.TxLock`) blokdan istisno bilan chiqsa avtomatik rollback qiladi — oqim ulanishida yozish tranzaksiyasi ochiq
  qolib butun serverda «database is locked» bo'lmaydi. `send`, `regenerate`, `build`, `text` endpointlari sinxron `def` (oqimlar havzasida); `/decks` (yuklash) tana
  o'qilishidan oldin ruxsatni oqimda tekshiradi.
- **Yuborish (`send`).** DARS (course_id, lkey) bo'yicha qulf butun jarayonni o'raydi (versiya hisobi, fayl, paketga qo'yish, eskisini almashtirish): parallel yuborishda
  paketda taqdimot yo'qolmaydi. Bir xil fayl (sha256) va bir xil foydalanuvchi <30 s ichida takror bosilsa — yangi versiya yo'q: `{unchanged: true, version: n}`; >30 s keyin
  ataylab qayta yuborilsa versiya oshadi. Javob: `version`, `unchanged`, `paket_error`. Versiya DARS bo'yicha hisoblanadi (boshqa taqdimot orqali yuborilsa ham davom etadi).
- **Maydonlar.** `GET /lessons` qatorida `lesson_sent_version/_deck_id/_deck_title/_at`, `decks`; `GET /decks/{id}`: `lesson` ichida shu maydonlar, `changed_since_send`,
  `last_send{version,at,size,filename,sha256_short}`, `doc_topic_no` (hujjatdagi «N-MAVZU»), `pptx{filename,size,built_at}`. Titul sarlavhasidan «7-MAVZU:» prefiksi olinadi.
- **Sarlavha.** «Mavzu nomi» bo'sh: matnning birinchi sarlavhasi → dars nomi → «<N>-mavzu — nomsiz»; hech qachon fayl nomi. Bir darsga ikkinchi taqdimot — javobda
  `existing:[{id,title}]` (bloklanmaydi). Darsga bog'langan taqdimotda fan nomi va mavzu raqami reja saqlanganda ham SERVER tomonida darsdan majburlanadi.
- **IDOR.** `GET /decks/{id}/sends/{ver}/{kind}`: chaqiruvchi darsning HOZIRGI kursiga ega (yoki kafedra ko'lamida) bo'lishi va versiya shu taqdimotniki (yoki shu muallifning
  boshqa taqdimotidan) bo'lishi shart. Kurs boshqaga o'tsa eski o'qituvchi yangisining versiyalari/izohi/ismini ko'rmaydi (`lesson.moved`), yuklay olmaydi (403, audit allowed=0).
- **Yuklash.** Content-Length oldindan tekshiriladi (20 MB → 413), oqim bilan o'qiladi va chegarada to'xtaydi. Xatolar: «Faqat .docx, .pdf yoki .txt yuklash mumkin»,
  «Fayl buzilgan yoki Word (.docx) emas. Wordda qayta saqlab ko'ring», «PDF ochilmadi — faylni qayta yuklab oling yoki Word variantini yuklang»; tur sehrli baytlar bo'yicha,
  ikkilik fayl (PNG, JPEG, eski .doc …) «matn» bo'lmaydi.
- **Muddat.** «Mening vazifalarim»dagi yangi taqdimot / video xabarlarida `due=null`, `fresh:true` («Yangi» belgisi); yuborilgan vaqt endi muddat emas.
- **Audit.** Ko'lam rad etilganda (begona kurs/taqdimot/versiya) so'rov boshidagi allowed=1 yozuv allowed=0 ga yangilanadi (`rbac.audit_deny`) — bitta so'rovga bitta yozuv.
- **Reja nusxasi.** `pres_sends.outline` — yuborilgan paytdagi reja (JSON); `pres_sends.course_code` — yuborilgan paytdagi fan kodi.


## API (`/api/taqdimot`)

| So'rov | Vazifa |
|---|---|
| `GET /meta` | Rejim, AI holati, kunlik hisob, slayd turlari (`teacher` — yuklamasi bor; `can_send`) |
| `GET /lessons` | **Dars tanlash:** o'qituvchining O'Z fanlari va L/A darslari: `{items: [{id, subject, direction, dir_code, course, code, dept, teacher, lessons: [{key, code, kind, title, full_code, sent_version}]}]}` |
| `POST /decks?name=&title=&slides=&audience=&course_id=&lkey=` | Fayl yuklash (so'rov tanasida fayl baytlari) va reja tuzish. `course_id`+`lkey` — dars bilan (eski `subject`, `topic_no` ham qabul qilinadi — darssiz) |
| `POST /decks/text` | Matndan reja tuzish (JSON: `text`, `course_id`, `lkey`, `title`, `slides`, `audience`; darssiz — `subject`, `topic_no`) |
| `POST /decks/{id}/lesson` `{course_id, lkey}` | **Darsni belgilash** (bog'lanmagan taqdimotni darsga bog'lash) |
| `POST /decks/{id}/send` `{note?}` | **Studiyaga va masofaviy bo'limga yuborish** → yangi versiya (`send`: version, code …), `sends` — tarix |
| `GET /decks/{id}/sends/{ver}/{pptx\|pdf}` | Yuborilgan versiyani yuklab olish (egasi, o'z kafedra mudiri) |
| `GET /decks?scope=mine\|dept` | Mening taqdimotlarim yoki kafedra taqdimotlari (har birida `lesson_code`, `sent_version`) |
| `GET /decks/{id}` | Taqdimot va uning rejasi; `lesson` (kod, kafedra, o'qituvchi …), `sent_version`, `sends` (versiyalar) |
| `POST /decks/{id}/outline` | Tahrirlangan rejani saqlash |
| `POST /decks/{id}/regenerate` | Rejani qayta tuzish (kunlik cheklovga kiradi) |
| `POST /decks/{id}/build` | .pptx yaratish |
| `GET /decks/{id}/download` | .pptx yuklab olish |
| `GET /decks/{id}/img/{n}` | Materialdagi rasm (tahrir sahifasi uchun) |
| `POST /decks/{id}/delete` | O'chirish |

## Testlar

`tests/test_zanjir.py` (+ `tools/zanjir_check.js`, brauzer: 1440 va 390 px) — Taqdimot → Studiya → Masofaviy bo'lim zanjiri: migratsiya, dars tanlash, versiyalar (v1 → v2 → v3), studiya va bo'lim ko'rishi,
bildirishnomalar, masofaviy bo'limga yuborish, dars kartochkasi, «Dars yaratish», ZIP, ruxsatlar va audit (`python tests/run_all.py --only zanjir`).

`tests/test_taqdimot.py` ikki qismdan iborat:
- **Serversiz qism:** soxta AI va qoidaviy reja asosida haqiqiy .pptx yaratiladi.
- **HTTP qism:** server AI siz rejimda ishlaydi. Ruxsatlar, fayl turlari, cheklovlar, kafedra ko'rishi va audit tekshiriladi.

`tests/run_all.py` serverni `ANTHROPIC_API_KEY` siz ishga tushiradi, shuning uchun testlar pul sarflamaydi. `ISFT_CORE_PRES_FAKE=1` qiymati soxta AI rejimini yoqadi (tarmoqqa chiqmaydi).
