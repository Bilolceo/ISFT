# Bo'limlararo portal (v2)

Portal bo'limlar o'rtasidagi ichki ish yozishmasi, ish fayllari va umumiy bazalar uchun mo'ljallangan. Rasmiy hujjatlar (buyruq, ma'lumotnoma, QR) bu yerda emas, «Hujjatlar markazi»da yuritiladi.
Kod: `app/portal.py` (API va mantiq), `app/filecheck.py` (fayl mazmunini tekshirish), `app/portal_backup.py` (zaxira nusxa), `static/portal.js` va `static/portal.css` (interfeys).

## Rollar bo'yicha imkoniyatlar

| Kim | Nima qila oladi |
|---|---|
| Rektor, prorektorlar | **Rezolyutsiya** qo'yadi: «Ijro uchun: bo'lim(lar), mas'ul ijrochi, muddat, izoh». Ijrochi bo'limlar xatni o'z muddati bilan oladi, muallif esa **Nazorat** qutisida ijroni kuzatadi («Kiruvchi · Yuborilgan · Nazorat» — asosiy qutilar, muddati o'tgan nazorat bo'lsa belgi qizil). Rezolyutsiyani **tahrirlaydi** yoki **bekor qiladi** (pastga qarang). Ijro tugagach rezolyutsiyani nazoratdan yechadi. «Barchasi» qutisida barcha yozishmalar ko'rinadi (qaytarib olinganlari belgi bilan), faqat ko'rish uchun; har bir ochish audit jurnaliga yoziladi. |
| Prorektor | **Yo'nalishim** qutisida o'zi kuratorlik qiladigan bo'limlar yozishmalari ko'rinadi (`org_units.curator`, manba — tashkiliy tuzilma 04.09.2024): o'quv — Akademik bo'lim, Registrator ofisi, Ma'lumotlar bazasi, Sirtqi, Amaliyot, fakultet va kafedralar; ilmiy — Ilmiy tadqiqotlar, Magistratura, Xalqaro hamkorlik; moliya — Buxgalteriya, Xo'jalik, Marketing, Xarid. Imtihon, Kadrlar, IT, Qabul, Strategik, Yuridik, Sifatni ta'minlash va Devonxona — rektorga bevosita. Kuratorni rektor yoki IT boshlig'i o'zgartira oladi. |
| Bo'lim rahbari | Kelgan xatni bo'lim xodimiga **ijrochi** sifatida tayinlaydi yoki ijrochini o'zgartiradi. Xatni boshqa bo'limga **yo'naltiradi**: o'z holati «yo'naltirilgan» bo'ladi, yangi bo'lim xatni o'sha muddat bilan oladi. |
| Xodim (bo'lim rahbari emas) | Bo'limning butun pochtasini **ko'rmaydi** — faqat shaxsan unga tegishli yozishmalar: o'zi yuborgan, unga ijrochi sifatida biriktirilgan (hozir yoki avval) yoki o'zi javob yozgan. Masalan, Call-markaz operatori (Registrator ofisi tarkibida) va Rektorat kotibi bo'limga kelgan biriktirilmagan xatni ko'rmaydi va ocholmaydi (403) — uni bo'lim rahbari taqsimlaydi. Ro'yxat, hisoblagichlar, eslatmalar va menyu belgisi shu qoida bo'yicha (`portal.personal_sql()` — umumiy qidiruv va bildirishnomalar ham shu shartni ishlatadi). Qoralama avtomatik saqlanadi. **Shablon**dan xat yozadi yoki o'z bo'limi uchun shablon saqlaydi. |
| Yuboruvchi bo'lim, rahbariyat | Masala hal bo'lgach yozishmani **yopadi** (izoh bilan). Yopilgan yozishma Arxivga o'tadi, kerak bo'lsa **qayta ochiladi**. Javob kutilayotgan bo'limlar uchun **muddatni o'zgartiradi** (hammasi yoki tanlanganlari uchun, izoh bilan). |
| Yuboruvchi bo'lim | Hali hech kim o'qimagan xatni **qaytarib oladi** (pastga qarang). |
| Rektor, IT boshlig'i | «Bo'limlar» bo'limida bo'lim **rahbari** (bo'lim xodimlaridan) va **kuratori** (prorektorlardan yoki «Rektorga bevosita») ni o'zgartiradi. |
| Har bir ishtirokchi | Yozishmani o'zi uchun **arxivlaydi**. Yangi javob kelsa, yozishma arxivdan avtomatik qaytadi. |
| Vakolati bor rahbar (rektor, kotib — rektor nomidan, prorektor — kuratorlikdagi bo'limlarga, bo'lim rahbari — quyi bo'limlarga, masalan Akademik bo'lim → kafedralar) | Turi **«Ma'lumot so'rovi»** yoki **«Topshiriq»** bo'lgan xat vakolatdagi bo'limlarga xat sifatida emas, **topshiriq** sifatida yuboriladi (`app/directives.py`, `tasks.src = 'portal:<xat id>'` yoki `'portal'`): ijro, taqsimlash, natija va qabul / qayta ishlashga qaytarish — «Majlislar va topshiriqlar»da, «Mening vazifalarim» va bildirishnomalarda bitta joyda. Vakolatdan tashqari bo'limlarga (masalan, yonma-yon bo'lim) — oddiy xat. Yozish oynasi oldindan ko'rsatadi: «N ta bo'limga topshiriq sifatida yuboriladi». Javob `{"id": xat|null, "directives": [{id, unit, name}]}`; xatda bog'langan topshiriqlar havolasi ko'rinadi. Avvalgi «so'rov» xatlari o'zgarishsiz qoladi. |

## Asosiy tamoyillar
- **O'qilganlik har bir xodim bo'yicha** kuzatiladi (`portal_user_reads`). Bo'limdan bir kishi ochgani boshqalar uchun xatni «o'qilgan» qilib qo'ymaydi. Yozishmada har bir bo'lim bo'yicha kim va qachon o'qigani ko'rinadi. Bo'lim holati (yangi → o'qilgan) birinchi o'qigan xodim bilan qayd etiladi.
- **Muddatlar:** har bir qabul qiluvchining muddati alohida bo'lishi mumkin (rezolyutsiya yoki yo'naltirishdan keladi). Muddati o'tgan deb faqat javob kutilayotgan va ochiq yozishmalar hisoblanadi.
- **Tizim yozuvlari** («ijrochi tayinlandi», «yozishma yopildi») xat oqimida ko'rinadi, lekin «o'qilmagan» hisoblagichini oshirmaydi.
- **Bo'lim saqlanadi:** `users.unit` maydoniga foydalanuvchi birinchi marta kirganda bir marta yoziladi. Bo'limlar ro'yxati `org_units` jadvalida (nomi, guruhi, rahbari `head_user`, kuratori `curator`, `curator_manual`). Lavozim nomi o'zgarsa ham xodim boshqa bo'limga o'tib qolmaydi.

## Rezolyutsiyani tahrirlash va bekor qilish
Faqat rezolyutsiyani qo'ygan rahbariyat bo'linmasi (rektor/prorektor roli bilan) va faqat rezolyutsiya «nazoratda» bo'lsa, yozishma ochiq bo'lsa.
- **Tahrirlash** (kartadagi «Tahrirlash» — rezolyutsiya shakli oldindan to'ldirilgan holda karta o'rnida ochiladi): matn, ijrochilar, mas'ul ijrochi, muddat.
  - Qo'shilgan bo'lim qabul qiluvchi bo'ladi (`via='rezolyutsiya'`, holat «yangi», rezolyutsiya muddati bilan). Allaqachon qabul qiluvchi bo'lsa — ijro uchun qayta ochiladi.
  - Olib tashlangan bo'lim qabul qiluvchilardan **faqat** uni aynan shu rezolyutsiya qo'shgan (`portal_recipients.res_id`) va u hali javob bermagan bo'lsa o'chiriladi. Aks holda (asl qabul qiluvchi, javob bergan) yozishmada qoladi, faqat mas'ulligi va shaxsiy muddati bekor qilinadi. Bo'lim boshqa nazoratdagi rezolyutsiyada ham bo'lsa — o'sha rezolyutsiyaning muddati va mas'ulligi tiklanadi.
  - Muddat o'zgarsa, rezolyutsiyaning javob kutilayotgan ijrochilariga ham tatbiq etiladi (yangi muddat bugundan oldin bo'lmasligi kerak; o'zgarmagan muddat tekshirilmaydi).
  - Yozishmada «Rezolyutsiya o'zgartirildi: muddat 12.11 → 15.11; qo'shildi: …; olib tashlandi: …» xabari qoladi (`kind='rezolyutsiya'`, ijrochilar uchun yangi xabar).
- **Bekor qilish** (kartada tasdiqlash shakli, izoh bilan): holat `bekor`. Shu rezolyutsiya qo'shgan va javob bermagan bo'limlar qabul qiluvchilardan chiqariladi, qolganlarining rezolyutsiya muddati bekor qilinadi. Tizim yozuvi «Rezolyutsiya bekor qilindi: izoh». Karta kulrang «Bekor qilingan»; bunday rezolyutsiya Nazorat qutisi, `control`/`control_overdue` hisoblagichlari va eslatmalarga kirmaydi.

## Talabalar ro'yxati biriktirilgan xat (v2.2)
Misol (Registrator ofisi): 10 nafar talaba harbiy ta'lim fakultetiga o'tadi → Baratov ro'yxatni xatga biriktirib O'quv ishlari prorektoriga yuboradi →
Temirov rezolyutsiya bilan Akademik bo'lim (Bo'tayev X.) va Ma'lumotlar bazasi bo'limiga (Ismatov R., mas'ul) yo'naltiradi → ijrochilar har bir talaba
bo'yicha «bajarildi / bajarilmadi (izoh)» belgilaydi, muddat va nazorat odatdagidek ishlaydi.
- **Biriktirish** (yangi xat oynasidagi «Talabalar» bloki, faqat talabalar kartochkasiga to'liq ruxsati borlarga): ism / HEMIS ID / guruh bo'yicha qidiruv,
  «Butun guruh» (bir bosishda), HEMIS ID ro'yxatini qo'yish (topilmaganlar alohida ko'rsatiladi), umumiy izoh. Har bir talaba yuboruvchining ko'lamida
  (`c.student_scope`) bo'lishi shart — aks holda 400; ruxsati yo'q lavozim — 403 (auditda). Ko'pi bilan 500 ta. Qoralamada ham saqlanadi
  (`portal_drafts.students`). Yuboruvchi ochiq yozishmaga keyin ham talaba qo'sha oladi.
- **Saqlash:** `portal_thread_students(thread_id, student_id, added_by, added_at, note, exec_status, exec_note, exec_unit, exec_by, exec_by_name, exec_at)`.
- **Kim nimani ko'radi:** ishtirokchi (yoki rahbariyat) talabalar kartochkasiga to'liq ruxsat bilan — o'z ko'lamidagi talabalar ismi, HEMIS ID, guruhi va
  ijro belgisi; ko'lamidan tashqaridagilar faqat sonda («N ta talaba ko'lamingizdan tashqarida»). Ruxsati jamlangan (rektor) yoki yo'q bo'lganlar —
  faqat jami soni, guruhlar va progress. Yozishmadagi tizim yozuvlarida faqat sonlar bo'ladi (ism yo'q). CSV (`;`, UTF-8 BOM, Excel uchun) — faqat
  ko'lam ichidagilar, har bir yuklab olish auditda.
- **Ijro belgilari:** belgilaydi — nazoratdagi rezolyutsiya bo'lsa uning ijrochi bo'limlari, bo'lmasa qabul qiluvchilar (yo'naltirib yuborganlardan
  tashqari); talabalar kartochkasiga ruxsat va ko'lam shart. «Bajarilmadi» uchun izoh majburiy; «kutilmoqda» — belgini olib tashlash. Hammasi
  belgilanganda «ijro yakunlandi» yozuvi qoladi. Progress (bajarildi / bajarilmadi / jami) xatda, ro'yxatlarda va «Nazorat» qutisida ko'rinadi.
- **Buyruqlar moduli bilan bog'lanish:** «Buyruqlar» bo'limi (`#nav a[data-v="orders"]` yoki `renderOrders`) mavjud bo'lsa, ro'yxat blokida
  «Buyruq loyihasi» tugmasi chiqadi: `window.ORDERS_PREFILL` va `sessionStorage["isft.orders.prefill"]` ga
  `{action: "guruh_ozgartirish", student_ids, source: "portal", thread_id, ref_no, subject}` yoziladi va `go("orders")` chaqiriladi
  (hali bajarilmagan talabalar). Buyruqning o'zi Portalda yaratilmaydi.
- **Rezolyutsiya qo'ygan rahbar:** xat rahbarning o'ziga kelgan bo'lsa, rezolyutsiya uning ijrosi hisoblanadi — o'z holati «yo'naltirilgan»
  (`forwarded_to` — ijrochilar), u javob kutilayotganlar va muddat eslatmalaridan chiqadi.

## Javobni ko'rib chiqish: qabul qilish / qayta ishlashga qaytarish (v2.2)
Yuboruvchi bo'lim har bir qabul qiluvchining javobini, nazoratdagi rezolyutsiya muallifi esa o'z ijrochilari javobini ko'rib chiqadi
(«Ko'rib chiqish» tugmasi, «Tafsilot»dagi havola). `POST /api/portal/threads/{tid}/review {unit, decision: "accept"|"return", comment, due?}`;
Python'dan: `portal.review_answer(con, ctx, tid, ReviewIn(...))` (masalan, sillabuslar moduli kafedralar javobini shu orqali qaytaradi).
- Faqat «javob berilgan» holatdagi bo'lim (aks holda 409), yozishma ochiq bo'lishi kerak. Begona bo'lim — 403 (auditda), qabul qiluvchi emas — 404.
- **Qabul qilish:** `review='qabul'` (izoh ixtiyoriy), tizim yozuvi. Takroriy qabul — 409.
- **Qaytarish:** izoh majburiy, ixtiyoriy yangi muddat (bugundan oldin emas). Bo'lim holati «o'qilgan» (javob kutilmoqda), `review='qaytarildi'`,
  `returns` +1, `answered_at` tozalanadi. Yozishmada `kind='qaytarish'` xabari (qabul qiluvchi uchun o'qilmagan bo'ladi); u yana «Javobsiz»,
  muddat hisoblagichlari va eslatmalarga (`returned: true`, Telegram'da «qayta ishlashga qaytarilgan») tushadi; rezolyutsiya yana «nazoratda».
- Bo'lim qayta javob yozsa `review` tozalanadi (yana ko'rib chiqiladi), `returns` saqlanadi. Tarix — `portal_reviews` (detail javobida `reviews`).
- Filtrlar va hisoblagichlar: `flt=review` (Yuborilgan / Nazorat: javob kelgan, ko'rib chiqilmagan; `counts.to_review`), `flt=returned`
  (Kiruvchi: qaytarilgan va hali qayta javob berilmagan; `counts.inbox_returned`). Ro'yxat elementida `review`, `returns`, `to_review`.

## Muddatni o'zgartirish
«Muddatni o'zgartirish» (yuboruvchi bo'lim yoki rahbariyat, yozishma ochiq, javob kutilayotgan bo'lim bor): yangi sana (bugun yoki keyin), kim uchun — barcha kutilayotgan bo'limlar (yozishma muddati o'zgaradi, ularning shaxsiy muddati unga tenglashadi) yoki tanlangan bo'limlar (faqat ularning shaxsiy muddati), ixtiyoriy izoh. Tizim yozuvi: «Muddat o'zgartirildi (bo'limlar): 12.11.2026 → 15.11.2026 (izoh)».

## Xatni qaytarib olish
Yuboruvchi bo'lim (yoki xat muallifi) xatni faqat hech bir qabul qiluvchi bo'lim xodimi uni ochmagan (`portal_user_reads` yo'q, holatlar «yangi», ijrochi tayinlanmagan), javob ham, rezolyutsiya ham bo'lmagan holda qaytarib oladi. Aks holda 409: «Xat o'qilgan — qaytarib bo'lmaydi. Yozishmani yopishingiz mumkin.»
- Holat `qaytarilgan`. Shu xat ilovalari orqali yaratilgan fayl ulashmalari ham o'chiriladi. Qabul qiluvchilar yozuvlari o'chiriladi, ro'yxati va muddati `portal_threads.recalled` (JSON) da saqlanadi. Shu sababli xat qabul qiluvchilarning qutilari, hisoblagichlari, qidiruvi (FTS), umumiy qidiruv, taqvim, bildirishnoma va eslatmalarida ko'rinmaydi; ochishga urinsa — 410 «qaytarib olingan».
- Yuboruvchida xat «Arxiv»da «Qaytarib olingan» belgisi bilan turadi; «Tahrirlab qayta yuborish» tugmasi xat matni, qabul qiluvchilari, muddati va ilovalaridan qoralama yaratadi (`PUT /api/portal/drafts`) va uni tahrirlash oynasida ochadi. Qaytarilgan xatni qayta ochib, unga javob yozib yoki rezolyutsiya qo'yib bo'lmaydi.

## Bo'limlar katalogi
Portalning 4-bo'limi — «Bo'limlar» (hamma uchun): `org_units` asosida guruhlar (Rahbariyat, Bo'limlar, Fakultet tyutorlari, Kafedralar — institutda dekanat yo'q, fakultet darajasidagi vazifalar Registrator ofisida), har bir kartada bo'lim nomi, rahbari, kuratori (prorektor yoki «Rektorga bevosita»), xodimlar soni va ro'yxati, joylashuvi va vazifalari, «Xat yozish» (yangi xat shu bo'lim tanlangan holda ochiladi). Qidiruv bo'lim, rahbar va xodim ismi bo'yicha.
- Rektor va IT boshlig'i kartadagi «Tahrirlash» orqali rahbar va kuratorni o'zgartiradi (`PUT /api/portal/org/{key}`); har bir o'zgarish va rad etilgan urinish auditda.
- Qo'lda tanlangan kurator tasdiqlangan tuzilmadan (`CURATOR`) farq qilsa `org_units.curator_manual=1` bo'ladi va `sync_units()` (server starti) uni ustidan yozmaydi; standart qiymat qaytarilsa belgi olib tashlanadi. Qo'lda tayinlangan rahbar (`head_user`) ham saqlanadi; rahbar ismi tayinlangan xodimdan olinadi.
- Kuratorlik (`curator`) prorektorning «Yo'nalishim» qutisini belgilaydi — o'zgarish darhol kuchga kiradi.

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

## Fayllar: kim ko'radi, kim ulashadi
- **Ko'rish:** o'z bo'limi fayllari, o'zi yuklagan, o'z bo'limiga (yoki «hamma»ga) ulashilgan fayllar. **Rektor** — barcha fayllar. **Prorektor** — faqat kuratorligidagi bo'limlar fayllari va o'zi ishtirok etgan yozishmalar (yuboruvchi, qabul qiluvchi, kuzatuvchi yoki rezolyutsiya muallifi) ilovalari; boshqa bo'limlar fayllari 403.
- **Qayta ulashish faqat egasi bo'lim:** xatga ilova qilingan fayl qabul qiluvchilarga avtomatik ulashiladi, lekin yangi ulashmani faqat fayl egasi bo'lim (`owner_unit`) yaratadi. Boshqa bo'lim fayli ishtirokchilarda allaqachon bo'lsa, ilova qilish mumkin; yangi bo'limga ulashishga urinish — 403 «faqat egasi bo'lim ulasha oladi» (topshiriq ilovalari uchun ham — `directives._check_files`).
- **Qaytarib olish ulashmani ham qaytaradi:** ilova orqali yaratilgan ulashma qaysi xat orqali yaratilgani `portal_shares.thread_id` da saqlanadi; xat qaytarib olinsa, shu ulashmalar o'chiriladi (boshqa xatlar orqali yaratilganlari qoladi).
- Toifa «O'quv-uslubiy» → **«O'quv jarayoni»** (dars va nazorat jadvallari, o'quv rejalar); mavjud fayllar server ishga tushganda ko'chiriladi.

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
`POST …/{id}/reply|resolve|assign|forward|close|reopen|archive` · `POST …/{id}/resolutions/{rid}/close|edit|cancel` ·
`POST …/{id}/due` (`{due, units: [], note}`) · `POST …/{id}/recall` (`{note}`) · `GET /api/portal/org`, `PUT /api/portal/org/{key}` (`{head_user, curator}`) ·
`GET|PUT /api/portal/drafts`, `DELETE /api/portal/drafts/{id}` · `GET|POST /api/portal/templates`, `DELETE …/{id}`, `POST …/{id}/use` ·
`GET /api/portal/reminders` · fayllar va umumiy bazalar endpointlari o'zgarmagan.
v2.2: `POST /api/portal/threads` — `students: [id], student_note` · `POST …/{id}/students` (`{students, note}`, yuboruvchi) ·
`POST …/{id}/students/mark` (`{ids, status: bajarildi|bajarilmadi|kutilmoqda, note}`) · `GET …/{id}/students.csv` ·
`POST …/{id}/review` (`{unit, decision, comment, due}`) · `GET /api/portal/students?q=|group_id=` · `POST /api/portal/students/lookup` (`{ids, hemis}`).
Detail javobida `students` (`total, done, failed, pending, groups, can_view, hidden, scope, executors, can_mark, can_add, items[]`), `reviews`,
`recipients[].review|review_note|review_at|review_by|returns|can_review`; ro'yxatda `students`, `review`, `returns`, `to_review`.

Holatlar: yozishma — `ochiq`, `yopilgan`, `qaytarilgan`; rezolyutsiya — `nazoratda` (javoblarga qarab «bajarildi» ko'rinadi), `yechilgan`, `bekor`. Detail javobidagi `perms`: `can_reply, can_resolve, can_assign, can_take, can_forward, can_close, can_reopen, can_change_due, can_recall, can_resend, can_archive, can_review`; rezolyutsiyada `can_close, can_edit, can_cancel`.

Demo (v2.2, `seed_demo_v22()` — `init()` va to'liq seed oqimida, mavzu bo'yicha idempotent): Baratov → Temirov xati 10 ta talaba bilan
(rezolyutsiya → Akademik bo'lim + Ma'lumotlar bazasi, 6 bajarildi / 1 bajarilmadi, Akademik bo'lim javobi ko'rib chiqish kutmoqda) va
Akademik bo'lim → 4 kafedra «sillabuslarni yangilash» (biri qaytarilgan, biri qabul qilingan, biri ko'rib chiqish kutmoqda, biri javobsiz).

Testlar: `tests/test_portal.py`. U HTTP orqali, ishlab turgan server ustida bajariladi, o'zi yaratgan yozishmalarni oxirida yopadi va tashkiliy tuzilmaga kiritgan o'zgarishlarini asl holiga qaytaradi (kuratorning saqlanishini tekshirish uchun alohida jarayonda `sync_units()` chaqiriladi).
