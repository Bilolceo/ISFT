# Taqdimot tayyorlash (o'qituvchi)

O'qituvchi ma'ruza materialini yuklaydi. Tizim **ISFT rasmiy shablonida** taqdimot rejasini tuzadi. O'qituvchi rejani tahrirlaydi va tayyor **.pptx** faylini yuklab oladi.

Kod joylashuvi:
- `app/taqdimot.py`: API va AI.
- `app/taqdimot_extract.py`: materialni o'qish.
- `app/taqdimot_render.py`: .pptx yaratish.
- `app/assets/taqdimot_shablon.pptx`: shablon.
- `static/taqdimot.js`, `static/taqdimot.css`: sahifa.

## Kim foydalanadi

| Lavozim | Imkoniyat |
|---|---|
| O'qituvchi | O'z taqdimotlarini yaratadi, tahrirlaydi, yuklab oladi va o'chiradi |
| Kafedra mudiri | O'z taqdimotlari bilan xuddi o'qituvchi kabi ishlaydi. «Kafedra taqdimotlari» bo'limida o'z kafedrasi o'qituvchilarining taqdimotlarini ko'radi va yuklab oladi, lekin tahrirlay olmaydi |
| Boshqa lavozimlar | 403 qaytadi, so'rov audit jurnaliga yoziladi |

Har bir amal audit jurnaliga `presentations` resursi bilan yoziladi: yuklash, reja tuzish, tahrir, pptx yaratish, yuklab olish, o'chirish va rad etilgan urinishlar.

## Ish tartibi

1. **Material.**
   - Qabul qilinadigan turlar: Word (.docx), PDF (rasmlari bilan) yoki matn (.txt). Matnni sahifaga to'g'ridan-to'g'ri yozish ham mumkin.
   - Hajm 20 MB gacha.
   - Fayl turi kengaytmasiga qarab emas, fayl ichidagi belgilar (sehrli baytlar) bo'yicha tekshiriladi.
   - Word fayldan sarlavhalar, xatboshilar, ro'yxatlar, jadvallar, rasmlar va formulalar (OMML) o'qiladi. Formulalar chiziqli matnga aylantiriladi.
   - PDF fayldan sahifa matni va rasmlar olinadi.
   - Ixtiyoriy maydonlar: fan nomi (o'qituvchining fanlari ro'yxatidan tanlash mumkin), mavzu raqami, mavzu nomi, taxminiy slaydlar soni va izoh (auditoriya, urg'u).
2. **Reja.**
   - AI ulangan bo'lsa, rejani Claude tuzadi.
   - AI ulanmagan bo'lsa, reja hujjat tuzilmasidan tuziladi: har bir sarlavha alohida slayd bo'ladi, xatboshilardan bandlar olinadi, rasmlar alohida rasm slaydiga qo'yiladi. «Nazorat savollari», «Adabiyotlar», «Topshiriqlar» va «Xulosa» bo'limlari nomidan taniladi.
3. **Tahrir.**
   - Slaydni yuqoriga yoki pastga surish, turini o'zgartirish, sarlavha va matnni tahrirlash mumkin.
   - Rasmni almashtirish, slayd qo'shish va o'chirish mumkin. O'chirilgan slaydni «Bekor qilish» tugmasi bilan qaytarsa bo'ladi.
   - Har bir slaydga ma'ruzachi izohi yoziladi. U .pptx faylidagi izohlar maydoniga tushadi.
4. **PPTX.** «PPTX yaratish» tugmasi faylni tayyorlaydi, keyin «Yuklab olish» tugmasi chiqadi. Barcha taqdimotlar «Mening taqdimotlarim» bo'limida saqlanadi.

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

## API (`/api/taqdimot`)

| So'rov | Vazifa |
|---|---|
| `GET /meta` | Rejim, AI holati, kunlik hisob, o'qituvchi fanlari, slayd turlari |
| `POST /decks?name=&subject=&topic_no=&title=&slides=&audience=` | Fayl yuklash (so'rov tanasida fayl baytlari) va reja tuzish |
| `POST /decks/text` | Matndan reja tuzish (JSON: `text`, `subject`, …) |
| `GET /decks?scope=mine\|dept` | Mening taqdimotlarim yoki kafedra taqdimotlari |
| `GET /decks/{id}` | Taqdimot va uning rejasi |
| `POST /decks/{id}/outline` | Tahrirlangan rejani saqlash |
| `POST /decks/{id}/regenerate` | Rejani qayta tuzish (kunlik cheklovga kiradi) |
| `POST /decks/{id}/build` | .pptx yaratish |
| `GET /decks/{id}/download` | .pptx yuklab olish |
| `GET /decks/{id}/img/{n}` | Materialdagi rasm (tahrir sahifasi uchun) |
| `POST /decks/{id}/delete` | O'chirish |

## Testlar

`tests/test_taqdimot.py` ikki qismdan iborat:
- **Serversiz qism:** soxta AI va qoidaviy reja asosida haqiqiy .pptx yaratiladi.
- **HTTP qism:** server AI siz rejimda ishlaydi. Ruxsatlar, fayl turlari, cheklovlar, kafedra ko'rishi va audit tekshiriladi.

`tests/run_all.py` serverni `ANTHROPIC_API_KEY` siz ishga tushiradi, shuning uchun testlar pul sarflamaydi. `ISFT_CORE_PRES_FAKE=1` qiymati soxta AI rejimini yoqadi (tarmoqqa chiqmaydi).
