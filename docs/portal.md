# Bo'limlararo portal (v2)

Portal bo'limlar o'rtasidagi ichki ish yozishmasi, ish fayllari va umumiy bazalar uchun mo'ljallangan. Rasmiy hujjatlar (buyruq, ma'lumotnoma, QR) bu yerda emas, «Hujjatlar markazi»da yuritiladi.
Kod: `app/portal.py` (API va mantiq), `app/filecheck.py` (fayl mazmunini tekshirish), `app/portal_backup.py` (zaxira nusxa), `static/portal.js` va `static/portal.css` (interfeys).

## Rollar bo'yicha imkoniyatlar

| Kim | Nima qila oladi |
|---|---|
| Rektor, prorektorlar | **Rezolyutsiya** qo'yadi: «Ijro uchun: bo'lim(lar), mas'ul ijrochi, muddat, izoh». Ijrochi bo'limlar xatni o'z muddati bilan oladi, muallif esa **Nazorat** qutisida ijroni kuzatadi. Ijro tugagach rezolyutsiyani nazoratdan yechadi. «Barchasi» qutisida barcha yozishmalar ko'rinadi, faqat ko'rish uchun; har bir ochish audit jurnaliga yoziladi. |
| Prorektor | **Yo'nalishim** qutisida o'zi kuratorlik qiladigan bo'limlar yozishmalari ko'rinadi (`org_units.curator`, manba — tashkiliy tuzilma 04.09.2024): o'quv — Akademik bo'lim, Registrator ofisi, Ma'lumotlar bazasi, Sirtqi, Amaliyot, fakultet va kafedralar; ilmiy — Ilmiy tadqiqotlar, Magistratura, Xalqaro hamkorlik; moliya — Buxgalteriya, Xo'jalik. Imtihon, Kadrlar, IT va Qabul — rektorga bevosita. |
| Bo'lim rahbari | Kelgan xatni bo'lim xodimiga **ijrochi** sifatida tayinlaydi yoki ijrochini o'zgartiradi. Xatni boshqa bo'limga **yo'naltiradi**: o'z holati «yo'naltirilgan» bo'ladi, yangi bo'lim xatni o'sha muddat bilan oladi. |
| Xodim | Biriktirilmagan xatni **o'z ijrosiga oladi**. «Menga biriktirilgan» filtridan foydalanadi. Qoralama avtomatik saqlanadi. **Shablon**dan xat yozadi yoki o'z bo'limi uchun shablon saqlaydi. |
| Yuboruvchi bo'lim, rahbariyat | Masala hal bo'lgach yozishmani **yopadi** (izoh bilan). Yopilgan yozishma Arxivga o'tadi, kerak bo'lsa **qayta ochiladi**. |
| Har bir ishtirokchi | Yozishmani o'zi uchun **arxivlaydi**. Yangi javob kelsa, yozishma arxivdan avtomatik qaytadi. |

## Asosiy tamoyillar
- **O'qilganlik har bir xodim bo'yicha** kuzatiladi (`portal_user_reads`). Bo'limdan bir kishi ochgani boshqalar uchun xatni «o'qilgan» qilib qo'ymaydi. Yozishmada har bir bo'lim bo'yicha kim va qachon o'qigani ko'rinadi. Bo'lim holati (yangi → o'qilgan) birinchi o'qigan xodim bilan qayd etiladi.
- **Muddatlar:** har bir qabul qiluvchining muddati alohida bo'lishi mumkin (rezolyutsiya yoki yo'naltirishdan keladi). Muddati o'tgan deb faqat javob kutilayotgan va ochiq yozishmalar hisoblanadi.
- **Tizim yozuvlari** («ijrochi tayinlandi», «yozishma yopildi») xat oqimida ko'rinadi, lekin «o'qilmagan» hisoblagichini oshirmaydi.
- **Bo'lim saqlanadi:** `users.unit` maydoniga foydalanuvchi birinchi marta kirganda bir marta yoziladi. Bo'limlar ro'yxati `org_units` jadvalida (nomi, guruhi, rahbari `head_user`, kuratori `curator`). Lavozim nomi o'zgarsa ham xodim boshqa bo'limga o'tib qolmaydi.

## Eslatmalar
- **Veb:** qo'ng'iroqcha bildirishnomalarida o'qilmagan xatlar, rezolyutsiyalar va muddat eslatmalari bor. Eslatma ijrochi xodimga boradi; ijrochi tayinlanmagan bo'lsa, bo'lim rahbariga. Muddatida javob olmagan yuboruvchi va ijrosi kechikkan rezolyutsiya muallifi ham eslatma oladi. Barcha eslatmalar `reminders_for()` dan olinadi.
- **Telegram:** bot ish kunlari soat 09:00 da (`ISFT_CORE_PORTAL_REMIND`) shu eslatmalarni yuboradi. Bir xil eslatma kuniga bir marta keladi; muddati o'tgan xat haqida eslatma har 3 kunda takrorlanadi (`portal_reminders` jurnali). `/xatlar` buyrug'i 7 kun ichidagi muddatlarni ko'rsatadi.

## Qidiruv, sahifalash, hisoblagichlar
- Ro'yxatlar to'liq SQL ichida filtrlanadi va sahifalanadi: `offset`/`limit`, ko'pi bilan 100, standart 50. `total` har doim aniq son.
- Qidiruv SQLite FTS5 (`portal_fts`, `unicode61 remove_diacritics 2`) orqali ishlaydi:
  - Apostrof variantlari (ʻ ʼ ‘ ’) bitta ko'rinishga keltiriladi.
  - Har bir so'z prefiks bilan qidiriladi.
  - Ro'yxat raqami va bo'lim nomi ham qidiruvga kiradi.
  - FTS5 bo'lmagan SQLite'da avtomatik ravishda LIKE ishlatiladi.
- Hisoblagichlar bitta so'rovda olinadi va 30 soniya keshlanadi. Har bir yozuvdan keyin kesh tozalanadi.

## Fayllar xavfsizligi
- **Kengaytmaga ishonilmaydi:** har bir fayl turi uchun "sehrli baytlar" va ichki tuzilma tekshiriladi. Quyidagilar rad etiladi, HTTP 415, sababi o'zbekcha matnda:
  - nomi o'zgartirilgan exe, ELF yoki skript;
  - makrosli Office va ODF hujjatlar;
  - ichida OLE obyekti bor RTF;
  - xavfli arxiv: `..` yo'l, exe, parolli, zip-bomba;
  - ikkilik baytli matn fayli.
- **Antivirus (ixtiyoriy):** `ISFT_CORE_CLAMD=host:3310` yoki unix soket yo'li berilsa, fayl ClamAV bilan tekshiriladi.
  - `ISFT_CORE_CLAMD_REQUIRED=1` bo'lsa va antivirus ishlamasa, fayl qabul qilinmaydi.
  - Antivirus bo'lmasa, `scan` maydoniga «tekshirilmadi» yoziladi.
- Har bir faylning `sha256` qiymati saqlanadi. Yuklab olishda `X-Content-Type-Options: nosniff` va `no-store` sarlavhalari qo'yiladi.

## Saqlash va zaxira nusxa (Railway)
- **Standart joy:** fayllar `data/portal_files/` papkasida saqlanadi. Railway'da `/app/data` papkasiga volume ulangan bo'lsa (README'dagi kabi), fayllar qayta joylashda saqlanib qoladi.
- **Volume ulanmagan bo'lsa:** konteyner diski har safar qayta joylanganda tozalanadi.
- **Boshqa joy:** fayllarni boshqa papkada saqlash uchun `ISFT_CORE_FILES_DIR=/data/portal_files` o'zgaruvchisini qo'ying. Demo seed tashqi papkada faqat portal fayl nomlarini (`<uuid>.<ext>`) o'chiradi.
- **Zaxira nusxa olish:** `.venv/bin/python -m app.portal_backup backup portal_YYYYMMDD.zip`. Arxivga bazadagi portal jadvallari va barcha fayllar sha256 bilan yoziladi.
- **Tiklash:** `restore portal_YYYYMMDD.zip --force`.
- **Tekshirish:** `verify` yo'qolgan, buzilgan va ortiqcha fayllarni topadi. `verify --fix` bo'sh sha256 qiymatlarini to'ldiradi.
- **Muhim:** `SEED_VERSION` o'zgarsa, demo baza va demo fayllar qayta yaratiladi. Haqiqiy foydalanishda seed ishlatilmaydi, zaxira nusxa esa muntazam olinadi.

Agar fayl diskda bo'lmasa, yuklab olishda «Fayl serverda topilmadi — zaxira nusxadan tiklash kerak» degan xabar chiqadi.

## API (qisqacha)
`GET /api/portal/threads?box=inbox|sent|control|area|all|archive&flt=all|unread|pending|overdue|mine&q=&offset=&limit=` ·
`GET /api/portal/threads/{id}` (`perms`, `resolutions`, `recipients[].readers`) ·
`POST …/{id}/reply|resolve|assign|forward|close|reopen|archive` · `POST …/{id}/resolutions/{rid}/close` ·
`GET|PUT /api/portal/drafts`, `DELETE /api/portal/drafts/{id}` · `GET|POST /api/portal/templates`, `DELETE …/{id}`, `POST …/{id}/use` ·
`GET /api/portal/reminders` · fayllar va umumiy bazalar endpointlari o'zgarmagan.

Testlar: `tests/test_portal.py`. U HTTP orqali, ishlab turgan server ustida bajariladi va o'zi yaratgan yozishmalarni oxirida yopadi.
