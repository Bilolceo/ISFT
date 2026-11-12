# Lavozimlar va ruxsatlar: 2026-yil noyabr auditi

Ruxsatlar uch joyda belgilanadi:
- `app/rbac.py` — qaysi lavozim qaysi ma'lumot turlarini ko'radi (ROLES);
- modullarning o'z qoidalari — Talabalar markazi, Hujjatlar markazi, kameralar, majlis topshiriqlari, Portal;
- menyu — ruxsat bo'lmagan bo'lim menyuda umuman ko'rinmaydi.

Server har bir so'rovda ruxsatni o'zi tekshiradi. Rad etilgan so'rovlar audit jurnaliga yoziladi.
Bu hujjatdagi qoidalarni `tests/test_ruxsatlar.py` tekshiradi.

## Audit natijasida qo'shilgan imkoniyatlar
| Lavozim | Qo'shilgan imkoniyat | Asos |
|---|---|---|
| Amaliyot bo'limi | Amaliyot yo'llanmasi | Bo'limning asosiy hujjati |
| Sirtqi bo'lim | Sirtqi ta'lim talabalari uchun registrator: otrabotka varaqasi, skan, bahoni tasdiqlash/qaytarish; o'z navbatidagi ogohlantirish xatlari; ma'lumotnoma, transkript, ogohlantirish xati, «Sessiyaga chaqiruv xati», imtihonga ruxsatnoma, shaxsiy grafik — **faqat sirtqi talabalarga** (server ko'lamni `study_form` bo'yicha tekshiradi). Kontrakt holatlari — faqat o'qish; institut kontrakt jamlanmasi yopiq; kontrakt muddatini uzaytirish va buyruq loyihalari — Registrator ofisida | Registrator ofisi boshlig'i M. Baratov: sirtqi bo'lim xuddi shu ishni faqat sirtqi talabalar uchun qiladi; sessiyaga qo'yish to'lov holatiga bog'liq |
| Imtihon bo'limi | Akademik qarzdorlar ro'yxati; Talabalar markazi — o'zlashtirish va otrabotka holatlarini **ko'radi**. Otrabotka varaqasini bermaydi, skan yuklamaydi | Otrabotka varaqasi va imtihonga ruxsatnomani Registrator ofisi beradi (M. Baratov) |
| Registrator ofisi | Ish stoli (zinapoya bosqichlari), imtihonga kirish ruxsatnomasi, shaxsiy grafik, kontrakt muddatini uzaytirishni qayd etish, otrabotka skanini o'qish va tasdiqlash | Talabaning qabuldan bitiruvgacha hamrohi |
| Akademik bo'lim | Auditoriyalar fondi; o'quv yuklama taqsimoti; qarzdorlar ro'yxati | Dars jadvalini shu bo'lim tuzadi |
| Rektorat kotibi | Majlis bayonnomasi, ijro nazorati xati | Majlis qarorlari va ijro nazorati kotibda |
| Kafedra mudiri | Talabalar markazi — faqat o'z kafedrasi, faqat o'quv holatlari (ko'rish); hisobotlar o'z kafedrasi ko'lamida | Qarzdorlik va otrabotka bilan kafedra ishlaydi |
| Buxgalteriya | Talabalar markazi — faqat kontrakt holatlari. Baho, davomat va otrabotka ko'rinmaydi | Kontrakt bo'yicha 2,6 mingdan ortiq holat |
| Moliya-iqtisod prorektori | Xo'jalik nosozliklari, auditoriyalar, qabul | Tuzilma: Xo'jalik, Xarid va Marketing bo'limlari shu prorektorga bo'ysunadi |
| Yoshlar masalalari prorektori | Auditoriyalar va kameralar (Majlislar zali signali), Talabalar markazi (jamlangan), hisobotlar | Kamera signali unga borardi, lekin uni ochib ko'ra olmasdi |
| Ilmiy ishlar prorektori | Viza uchun taklifnoma | Xalqaro hamkorlik bo'limi shu prorektorga bo'ysunadi |
| AT bo'limi boshlig'i | Kameralar salomatligi. Faqat kameraning texnik voqealarini belgilaydi: to'sish, tasvir yo'qolishi, siljish | Kamera tarmog'i va proshivkasi AT bo'limining ishi |
| AT bo'limi muhandisi (#22) | `requests` — «Murojaatlar va nosozliklar»da **faqat** AT bo'limi navbati va o'ziga biriktirilgan murojaatlar; «Olindi» (o'ziga biriktiradi) / «Hal qilindi». Umumiy hodisa xabarini yubormaydi va hodisani yopmaydi (server: `service.UNIT_ONLY`). AT boshlig'i murojaatni muhandisga biriktiradi | Muhandisning real navbati yo'q edi — faqat majlis topshiriqlari |
| Devonxona (#40) | Yangi resurs `chancery`: Buyruqlar reyestri (o'qish — talabalar va xodimlar buyruqlari), imzolangan buyruqni devonxona jurnaliga ro'yxatga olish, chiquvchi yozishmalar jurnali (raqam `Ch-YY/NNNN`, sana, qabul qiluvchi, mavzu, buyruq yoki Portal yozishmasiga havola). Loyiha tuzmaydi, imzolamaydi; talabalar muvofiqlik auditi, o'zgarishlar jurnali, talaba qidiruvi va ro'yxat XLSX — yopiq | Devonxona — buyruqlar va chiquvchi hujjatlar ro'yxatga olinadigan joy |
| Kadrlar bo'limi | Buyruqlar — **faqat xodimlar buyruqlari** (mehnat ta'tili): loyiha, imzoga yuborish, qaytarilganini tuzatish. Talabalar buyruqlari, audit va jurnal yopiq | Buyruqlar — talabalar va xodimlar buyruqlarining yagona joyi (Hujjatlar markazidagi buyruq shablonlari o'rniga) |
| Xarid bo'limi (#42) | Yangi resurs `procurement`: xarid so'rovlari navbati (xo'jalik nosozligidan), holat: yangi → ko'rib chiqilmoqda → buyurtma berildi → yetkazildi / rad etildi. Nosozliklar, murojaatlar, talabalar va kadrlar ma'lumoti — yopiq | Xo'jalik «Xarid kerak» belgilagan jihozlar shu bo'limga tushadi |
| Xo'jalik bo'limi | `procurement`: nosozlik qatorida «Xarid kerak» (ikki bosqichli tasdiq) va xarid so'rovlari holatini ko'rish | — |
| Moliya-iqtisod prorektori | `procurement` — xarid so'rovlarini ko'rish (kuratorlik) | Xarid bo'limi shu prorektorga bo'ysunadi |
| Yuridik bo'lim (#39) | `international` — xalqaro/hamkorlik shartnomalari reyestri (faqat o'qish) va «Tarjima va shartnoma» tekshiruvi (AI o'chiq bo'lsa — qoida asosida). Panelda «Shartnomalar ekspertizasi» ish stoli: 180 kun ichida tugaydigan yoki e'tirozli shartnomalar navbati va yuridik xulosa (`POST /api/desk/legal/{id}` — faqat Yuridik bo'lim; e'tiroz/tugatishda izoh majburiy) | Shartnomalar ekspertizasi yuridik bo'lim ishi |
| Strategik bo'lim (#37), Sifatni ta'minlash (#38), Marketing (#41) | Ruxsatlar o'zgarmadi — mavjud resurslar ustida ish stoli (`app/desks.py`, `GET /api/desk`, panelda): strategik — `kpi` + `reports` (10 ta institut KPI, fakultetlar kesimi, haftalik brifing DOCX, KPI jadvali CSV); sifat — `academic` (faqat jamlangan, faqat o'qish: fakultet/kurs kesimida ball, davomat, o'zlashtirmaganlar va a'lochilar ulushi, keskin pasaygan guruhlar, sillabuslar holati); marketing — `admissions` (voronka, yo'nalishlar konversiyasi, haftalik dinamika). Hech bir stol shaxsiy ma'lumot qaytarmaydi; o'qish audit jurnaliga yoziladi | Panellar bo'sh edi: ruxsat bor, lekin ko'rinish yo'q edi |
| Barcha xodimlar (call-markaz va Kuzatuv kengashidan tashqari) | Xizmat xati | — |
| Reyting (`app/reyting.py`, [reyting.md](reyting.md)) | To'liq: Registrator ofisi (#17, #43), Akademik bo'lim, rektor, o'quv prorektori, Imtihon va Ma'lumotlar bazasi bo'limlari; Sirtqi bo'lim — faqat sirtqi talabalar; kafedra mudiri — o'z kafedrasi; tyutor — o'z fakulteti; o'qituvchi — o'zi baholagan talabalar; Kuzatuv kengashi, boshqa prorektorlar, Sifat boshqarmasi — faqat jamlangan (ism-sharifsiz); qolganlar (Buxgalteriya) — 403. Qayta hisoblash — Registrator ofisi va Akademik bo'lim. Audit resursi `rating` | Reyting talaba baholarini ochadi — faqat ular bilan ishlaydigan bo'limlarga; rahbariyat kuzatuvi uchun jamlangan ko'rinish |

## Olib tashlangan ortiqcha ruxsatlar
- **Kuzatuv kengashi** kamera xavfsizlik voqealari va kameralar ro'yxatini endi ko'rmaydi. Kengash operativ ish bilan shug'ullanmaydi, unga bandlik statistikasi ochiq qoldi. Ijro nazorati xati va xizmat xati ham olib tashlandi.
- **Ruxsat jadvali** (`/api/rbac`) endi faqat tizimga kirgan foydalanuvchiga ochiladi. Avval kirishsiz ham ochilardi. To'liq jadvalni rektor, Kuzatuv kengashi va AT bo'limi boshlig'i ko'radi, qolganlar faqat o'z lavozimining ruxsatlarini ko'radi.

## Menyu belgilari — yagona qoida
Menyudagi har bir raqam — **sizdan harakat kutayotgan ishlar** soni va u bo'lim sahifasidagi son bilan teng; sichqoncha ostida izoh
(nimani sanaydi). «Mening vazifalarim» — sahifadagi «Jami ish»; «Buyruqlar» — imzo / kelishuv / qaytarilgan / jurnalga olinmagan;
«Murojaatlar va nosozliklar» — menga biriktirilgan + bo'limim navbatida hech kim olmagan murojaatlar (xo'jalik — yangi nosozliklar,
xarid — ochiq so'rovlar, AT boshlig'i va Registrator ofisi — xabar yuborilmagan hodisalar); «Majlislar» — menga/bo'limimga tegishli
bajarilmagan topshiriqlar; «AI agentlar» — mening tasdig'imni kutayotgan takliflar; «Talabalar markazi» — navbatimdagi kechikkanlar.
Hujjatlar markazida imzo navbati yo'q: buyruqlar faqat «Buyruqlar»da imzolanadi.

## Bo'limlar ro'yxati bitta joyda
- Majlis topshiriqlari, Portal va «Mening vazifalarim» bitta bo'limlar ro'yxatidan foydalanadi: `org_units` jadvali va `users.unit` maydoni.
- Topshiriqni har qanday bo'limga berish mumkin: rahbariyat, bo'limlar, fakultet tyutorlari, kafedralar.
- Topshiriq shu bo'lim xodimlariga, ijrochiga va bo'limga kuratorlik qiladigan prorektorga ko'rinadi. Prorektor uni faqat ko'radi, o'zgartira olmaydi.
- Ko'lam tekshiruvi tuzatildi: bir kafedra mudiri boshqa kafedraning topshiriqlarini endi ko'rmaydi.

## Dekan lavozimi bekor qilindi (2026-11-09)
Institutda dekan lavozimi yo'q (Yevropa modeli). Fakultet darajasidagi vazifalarni **Registrator ofisi** (boshlig'i — M. Baratov, #17)
bajaradi; fakultetlar akademik tuzilma sifatida qoladi, fakultet tyutorlari (#24–26) — o'z fakulteti talabalari bilan ishlaydi.
- `rbac.ROLES["dekan"]` — faqat eski yozuvlar (audit jurnali) to'g'ri ko'rinishi uchun saqlangan *legacy* kalit (`rbac.LEGACY_ROLES`):
  ruxsatlari bo'sh, ruxsatlar jadvalida (`/api/rbac`), akkaunt yaratishda va kirish ro'yxatida yo'q; bu lavozimni berib ham,
  shu lavozimdagi akkauntni faollashtirib ham bo'lmaydi.
- Sobiq «Dekan» demo akkaunti (#13) id'si saqlangan (keyingi id'lar o'zgarmasin), lekin faolsizlantirilgan: kirish 403, eski sessiyalar
  401, Telegram uzilgan. Yangi seed'da ham, mavjud bazada server ishga tushganda ham (`accounts.retire_legacy`, idempotent);
  eski bazalardagi dekanga yozilgan bo'limsiz majlis topshiriqlari Registrator ofisiga o'tkaziladi.
- Hujjatlar: talaba hujjatlari, qaydnoma va qarzdorlar ro'yxati — «Registrator ofisi boshlig'i» imzosi bilan (ism `org_units`dan);
  buyruq loyihalarining KELISHILDI qatorida ham dekan o'rniga Registrator ofisi boshlig'i. Yakuniy nazorat qaydnomasi va akademik
  qarzdorlar ro'yxati endi Registrator ofisida ham chiqariladi.
- Portal: «Dekanatlar» guruhi → «Fakultet tyutorlari» (`fak1..fak3` — «<fakultet> fakulteti tyutorlari»). Majlis matnidagi
  «dekan/dekanat» Registrator ofisiga yo'naltiriladi. Face ID: dekan ko'lami olib tashlandi (tyutor — o'z fakulteti talabalari).

## Xavfsizlik va izchillik tuzatishlari (2026-11-12)
Regressiya testi: `tests/test_xavfsizlik.py` (+ `tests/test_qabul.py`, `tests/test_rejalar.py`).

- **Talabalar ko'lami — yagona qoida** (`rbac.Ctx.student_scope()` / `group_scope()`): tyutor — faqat o'ziga biriktirilgan guruhlar
  (`tutor_groups`; butun fakultet emas), Sirtqi bo'lim — faqat sirtqi talabalar, Masofaviy bo'lim — faqat masofaviy, kafedra mudiri — o'z
  kafedrasi guruhlari, o'qituvchi — o'zi dars beradigan guruhlar. Talabalar markazi (`student_ops._scope_sql`), reyting (`reyting.scope_sql`),
  hujjatlar (`documents._sscope`, `_groups_sql`), buyruqlar (`orders.st_scope`), umumiy qidiruv, `/api/section/risk`, Portal «kontingent»
  bazasi va talaba qidiruvi shu funksiyadan oladi; modul faqat qo'shimcha toraytiradi (masalan, buxgalteriya — faqat kontrakt talabalari;
  reytingda o'qituvchi — o'zi baholagan talabalar).
- **Portal yozish amallari**: qaytarib olish, yopish, qayta ochish, muddat, yo'naltirish, ijrochi tayinlash / o'ziga olish, talabalar ro'yxati,
  javobni ko'rib chiqish, arxiv — hammasi `portal._need_access()` dan o'tadi: xodim ocha olmaydigan (shaxsan unga tegishli bo'lmagan) xatni
  o'zgartira ham olmaydi (403, auditga yoziladi). Biriktirilmagan kiruvchi xatni bo'lim rahbari taqsimlaydi; xodim faqat avval o'ziga
  tegishli bo'lgan xatni qayta «o'ziga oladi».
- **Murojaatlar** (`app/service.py`): murojaat faqat navbatini ocha oladigan bo'limga tushadi (`RECEIVING_UNITS` — lavozimida `requests`
  ruxsati bor bo'limlar). Buxgalteriya va Ma'naviyat bo'limiga tasniflangani Registrator ofisiga yo'naltiriladi, `requests.route_note`da asl
  mas'ul bo'lim yoziladi. Holatni faqat egasi bo'lgan bo'lim, shaxsan biriktirilgan xodim yoki rahbariyat (rektor, o'quv prorektori)
  o'zgartiradi (`can_handle`); «javob berildi» — javob matni bilan. Umumiy hodisa xabari tashqi kanalga yuborilmaydi — javob sifatida
  murojaatlarga yoziladi (`stored`, `delivered: false`). Tadbir QR ro'yxati faqat mavjud, tasdiqlangan tadbirga va faqat o'z kunida ochiladi.
- **Hayfsan**: yagona yo'l — «Buyruqlar»dagi «hayfsan» buyrug'i. Har qanday (Talabalar markazidan, bevosita Buyruqlarda tuzilgan yoki
  Hujjatlar markazidan ko'chirilgan) hayfsan buyrug'i imzolanganda `student_ops.sync_discipline()` har bir talabaga «amalda» intizomiy yozuv
  beradi (idempotent; arxiv — `historic` — buyruqlar hisobga olinmaydi). Hujjatlar markazida «reprimand» taqdimnomasi tuzilmaydi;
  «leave_order» → `orders.draft_staff_leave` (xodim buyrug'i loyihasi).
- **Parol va Telegram**: parol tiklansa, sinov paroliga qaytarilsa yoki xodim o'zi almashtirsa (`rbac.set_password`) — Telegram ulanishi
  uziladi, javobda `telegram_unlinked`. Bot ulanishni parol iziga bog'laydi (`users.tg_pin_fp`): parol boshqa yo'l bilan o'zgargan bo'lsa ham
  keyingi murojaatda qayta tasdiqlash (KOD parol) so'raladi, rejali xabarlar yuborilmaydi.
- **Xodim ↔ akkaunt** (`staff_absence.user_link`, jadval `user_staff`): «o'z» yo'qliklari va shaxsiy ishi (kadrlar) barqaror id bo'yicha.
  Ism faqat birinchi bog'lashda va faqat bir qiymatli bo'lsa ishlatiladi (bitta xodim, bitta akkaunt, yozuv band emas); adashlar va nomi
  o'zgartirilgan bog'lanmagan akkaunt — «o'z» yozuvlarisiz.
- **AI agent takliflari**: tasdiq kutadigan takliflar obyekt bo'yicha kalitlanadi (`ijro:overdue:<id>#sana` va h.k.): bitta obyektga bitta
  ochiq taklif, har kuni takrorlanmaydi, sharti yo'qolsa avtomatik yopiladi, qarordan keyin 7/14 kun (yoki yaratilgan topshiriq yopilguncha)
  qayta taklif qilinmaydi; bir xil ochiq topshiriq ikkinchi marta yaratilmaydi. Eski takrorlar server startida tozalanadi (`dedupe`).
- **Kutilayotgan ishlar — bitta yig'uvchi**: qo'ng'iroqcha (`/api/notifications`) ishlarni `mywork.collect()` dan oladi (xodim bo'yicha 75 s
  kesh — `collect_cached`), javobda `work.total` = «Mening vazifalarim»dagi son. Jonli hodisalar (o'qilmagan xat, yangi/qaytarilgan topshiriq,
  sillabus) alohida. «Yangi» belgisi — ish birinchi marta paydo bo'lgan vaqtdan (`notif_first`), muddat yaqinlashganda yana ko'tariladi.
- **Rektor — kadrlar jamlanmasi**: yangi resurs `hr_stats` (rektor, Kadrlar): suhbatda «Bugun nechta xodim ta'tilda?» — faqat sonlar
  (`staff_absence.agent_tool`, ai.py «staffabs»). `hr` (shaxsiy ma'lumot, pasport) rektorga yopiq qoladi.
- **Qabul buyrug'i**: loyiha (.docx) bosqichni o'zgartirmaydi; `qb_batches` — loyiha → kiritilgan (alohida tasdiq) → imzolangan | bekor;
  qayta yuklab olish va (imzolanguncha) qaytarish mumkin. «Buyruqlar» moduli bilan avtomatik bog'lanmaydi (abituriyent hali `students`da yo'q).
- **KPI maqsadlari**: bir ko'rsatkichga bitta maqsad (409), foizli ko'rsatkich ≤ 100, muddat o'tmishda emas va 5 yildan uzoq emas.
