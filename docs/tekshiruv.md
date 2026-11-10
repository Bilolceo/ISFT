# Ishlarni tekshirish (o'qituvchi)

O'qituvchi talabalardan olgan ishlarni — mustaqil ish, referat, taqdimot, masala yechimi, test javoblari — platformaga yuklaydi.
AI har bir ish bo'yicha mezonlar asosida **ball va izoh taklif qiladi**. **Yakuniy bahoni o'qituvchi tasdiqlaydi**: tasdiqlanmagan taklif baho hisoblanmaydi.

Modul: `app/tekshiruv.py` (API `/api/tekshiruv`), interfeys: `static/tekshiruv.js`, menyu: **Ishlarni tekshirish**.

## Kimlar foydalanadi

| Rol | Imkoniyat |
|---|---|
| O'qituvchi | O'z tekshiruvlari: yaratish, ishlarni yuklash, tekshirish, baholash, tasdiqlash, eksport |
| Kafedra mudiri | O'z tekshiruvlari (o'qituvchi kabi) + **Kafedra tekshiruvlari** — kafedra o'qituvchilarining tekshiruvlarini faqat ko'radi va eksport qiladi (baholay olmaydi) |
| Boshqa rollar | Ruxsat yo'q (403), urinish audit jurnaliga yoziladi |

## Ish tartibi

1. **Yangi tekshiruv** quyidagilardan iborat:
   - nom va tur (mustaqil ish / test javoblari / referat / taqdimot / masala / boshqa);
   - maksimal ball (masalan 5, 10 yoki 100);
   - fan va guruh;
   - topshiriq matni (yoki topshiriq fayli: PDF / Word / PowerPoint / Excel / matn).
   - **Baholash mezonlari:** har tur uchun tayyor andoza beriladi, uni o'zgartirish mumkin. Mezon balli — uning og'irligi. Jami avtomatik ravishda maksimal ballga moslanadi.
   - Ixtiyoriy: **namunaviy javob / yechim**. Test uchun **test kaliti** kiritiladi: `1-A, 2-C, 3-B …` (kirill harflari ham qabul qilinadi).
2. **Ishlarni yuklash.** Fayllarni bir nechtasini birdan, sudrab tashlash yo'li bilan yoki ZIP arxiv qilib yuklash mumkin.
   - Qabul qilinadigan turlar: PDF, Word (.docx), PowerPoint (.pptx), Excel (.xlsx), matn (.txt), JPG/PNG.
   - Bitta fayl 20 MB gacha, bitta tekshiruvda 100 tagacha ish.
   - Fayl turi kengaytmasiga qarab emas, ichidagi baytlarga qarab tekshiriladi.
   - Fayl nomida talabaning familiyasi va ismi bo'lsa (masalan `Karimova_Dilnoza.docx`), talaba guruh ro'yxatidan **avtomatik taklif qilinadi**. Bunday yozuv «(avto)» bilan belgilanadi; o'qituvchi uni tuzatishi yoki ismni qo'lda yozishi mumkin.
   - ZIP xavfsiz ochiladi: ichki papkalar e'tiborga olinmaydi, `../` kabi yo'llar ishlamaydi. ZIP ichidagi ZIP va noma'lum turdagi fayllar o'tkazib yuboriladi, o'qituvchiga ro'yxat ko'rsatiladi.
3. **Tekshirish.** Ishlar fonda tekshiriladi, jarayon foizi ko'rinib turadi. Har bir ish uchun AI quyidagilarni taklif qiladi:
   - har mezon bo'yicha ball va izoh;
   - jami ball;
   - qisqa xulosa;
   - kuchli tomonlar;
   - kamchiliklar, iqtibos yoki joy bilan (masalan «3-slayd»);
   - talabaga murojaat shaklidagi izoh;
   - AI ishonchi darajasi.

   Quyidagi ishlar **«Qo'lda tekshirish»** holatiga tushadi:
   - o'qib bo'lmaydigan ishlar;
   - AI ishonchi past bo'lgan ishlar;
   - ichida baholashga ta'sir qilishga urinish bor ishlar.
4. **Ko'rib chiqish.** Chapda talaba ishining matni va rasmlari, o'ngda AI taklifi turadi.
   - O'qituvchi ballar va izohlarni tahrirlaydi, keyin **Tasdiqlash**ni bosadi. Shundan so'ng keyingi tasdiqlanmagan ish ochiladi.
   - Tasdiqlangan ish tahrirlansa, tasdiq bekor bo'ladi va qayta tasdiqlash kerak.
   - **Ko'rilganlarni tasdiqlash** tugmasi faqat o'qituvchi ochib ko'rgan AI takliflarini tasdiqlaydi.
5. **O'xshashlik.** Bir tekshiruv ichidagi ishlar matni o'zaro solishtiriladi (5 so'zli bo'laklar bo'yicha). Ko'p umumiy matnga ega juftliklar «o'xshashlik yuqori/o'rta» deb ko'rsatiladi. Ko'chirilgan-ko'chirilmaganini o'qituvchi hal qiladi. «AI yozgan matnni aniqlash» funksiyasi **yo'q**, chunki bunday aniqlash ishonchli emas.
6. **Eksport:**
   - baholar jadvali — `.xlsx` (imzo qatori bilan) va `.csv`;
   - izohlar varaqasi — `.docx` (hamma talabalar uchun bitta fayl yoki har bir talaba uchun alohida).

## Test javoblari

Test turida kalit kiritilgan bo'lsa, ball **server tomonida aniq hisoblanadi**:
- **Yozma javob varaqasi** (matn, Word, PDF): javoblar o'qiladi (`1-A`, `2) B`, `3.С` …). Ball = to'g'ri javoblar ulushi × maksimal ball. Bu AI'siz ishlaydi.
- **Skaner yoki rasm:** AI faqat talaba tanlagan harflarni o'qiydi, ballni server kalit bo'yicha hisoblaydi.
- Javobi bo'lmagan savol noto'g'ri hisoblanadi. Noto'g'ri javoblar ro'yxati kamchiliklar qismida ko'rsatiladi.

## AI (Claude) va maxfiylik

- Kalit **faqat** muhit o'zgaruvchisidan olinadi: `ANTHROPIC_API_KEY` (Railway → Variables). U kodda, faylda yoki logda saqlanmaydi. Kalit «Taqdimot» funksiyasi bilan umumiy (`app/claude_client.py`).
- Model: `ISFT_CORE_CHECK_MODEL`. Standart qiymati — `claude-sonnet-5-5`: ishlar soni ko'p bo'lgani uchun arzonroq model tanlangan.
- **Claude'ga yuboriladi:** topshiriq, mezonlar, namunaviy javob, ish matni va rasmlari (10 tagacha, ≤ 1568 px).
- **Claude'ga yuborilmaydi:** talaba ismi, ID'si, guruhi va fayl nomi. Ish «Ish #N» deb nomlanadi, matndagi talaba ismi va familiyasi `[talaba]` bilan almashtiriladi.
- **Ta'sir qilishga urinishlardan himoya:** ish matni `<work>` teglari ichida faqat ma'lumot sifatida beriladi. Model ish ichidagi ko'rsatmalarni (masalan «menga 100 ball qo'ying») bajarmaydi. Server har bir ballni mezon chegarasida, jamini esa maksimal ball chegarasida qisadi. Bunday urinish o'qituvchiga alohida belgi bilan ko'rsatiladi.
- **Kalit bo'lmasa:**
  - interfeysda «AI ulanmagan» deb ko'rsatiladi;
  - test kaliti bo'yicha yozma javoblar baribir baholanadi;
  - boshqa ishlar qo'lda tekshiruvga tushadi, o'ylab topilgan ball **chiqmaydi**.

## Cheklovlar va sozlamalar

| O'zgaruvchi | Ma'nosi | Standart |
|---|---|---|
| `ANTHROPIC_API_KEY` | Claude API kaliti | — (AI ulanmagan) |
| `ISFT_CORE_CHECK_MODEL` | Model | `claude-sonnet-5-5` |
| `ISFT_CORE_CHECK_DAILY` | Bitta o'qituvchi uchun kunlik AI tekshiruvlari soni | 200 |
| `ISFT_CORE_CHECK_FAKE` | `1` — testlar uchun soxta AI (tarmoqqa chiqmaydi) | — |

- Fayllar `DATA_DIR/tekshiruv/<id>/` papkasida saqlanadi. Tekshiruv o'chirilsa, fayllari ham o'chiriladi.
- Har bir amal audit jurnaliga `work_checks` resursi bilan yoziladi: yaratish, yuklash, tekshirish, ball o'zgarishi («ball: 4.0 → 3.5»), tasdiq va rad etilgan urinishlar.
- Baholar shu modul ichida qoladi. HEMIS'ga avtomatik yozilmaydi, chunki bu integratsiya rejadan chiqarilgan.

## Testlar

`tests/test_tekshiruv.py` (run_all.py avtomatik topadi). Tekshiriladi:
- **Jarayon ichida:**
  - AI juda katta ball qaytarsa ham, ball mezon va maksimal chegarasida qoladi;
  - ish ichidagi ko'rsatma ballni oshirmaydi;
  - Claude'ga ism va fayl nomi yuborilmaydi;
  - test kaliti to'g'ri o'qiladi va hisoblanadi;
  - talaba fayl nomidan to'g'ri aniqlanadi;
  - fayl turi ichidagi baytlarga qarab aniqlanadi.
- **HTTP orqali:**
  - ruxsatlar (kim kirishi mumkin, kim 403 oladi);
  - yuklash, ZIP xavfsizligi, hajm va fayl turi cheklovi;
  - AI'siz qo'lda tekshiruv navbati;
  - test kaliti bo'yicha baholash;
  - tahrir, tasdiq va «ko'rilganlarni tasdiqlash»;
  - o'xshashlik, eksport, kafedra mudiri ko'rinishi, audit va o'chirish.
