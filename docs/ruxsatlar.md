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
| Strategik bo'lim, Sifatni ta'minlash, Yuridik bo'lim, Devonxona, Marketing, Xarid | Akkaunt, Portal, majlis topshiriqlari; eng kam ruxsat | 04.09.2024 tasdiqlangan tuzilma |
| Barcha xodimlar (call-markaz va Kuzatuv kengashidan tashqari) | Xizmat xati | — |
| Reyting (`app/reyting.py`, [reyting.md](reyting.md)) | To'liq: Registrator ofisi (#17, #43), Akademik bo'lim, rektor, o'quv prorektori, Imtihon va Ma'lumotlar bazasi bo'limlari; Sirtqi bo'lim — faqat sirtqi talabalar; kafedra mudiri — o'z kafedrasi; tyutor — o'z fakulteti; o'qituvchi — o'zi baholagan talabalar; Kuzatuv kengashi, boshqa prorektorlar, Sifat boshqarmasi — faqat jamlangan (ism-sharifsiz); qolganlar (Buxgalteriya) — 403. Qayta hisoblash — Registrator ofisi va Akademik bo'lim. Audit resursi `rating` | Reyting talaba baholarini ochadi — faqat ular bilan ishlaydigan bo'limlarga; rahbariyat kuzatuvi uchun jamlangan ko'rinish |

## Olib tashlangan ortiqcha ruxsatlar
- **Kuzatuv kengashi** kamera xavfsizlik voqealari va kameralar ro'yxatini endi ko'rmaydi. Kengash operativ ish bilan shug'ullanmaydi, unga bandlik statistikasi ochiq qoldi. Ijro nazorati xati va xizmat xati ham olib tashlandi.
- **Ruxsat jadvali** (`/api/rbac`) endi faqat tizimga kirgan foydalanuvchiga ochiladi. Avval kirishsiz ham ochilardi. To'liq jadvalni rektor, Kuzatuv kengashi va AT bo'limi boshlig'i ko'radi, qolganlar faqat o'z lavozimining ruxsatlarini ko'radi.

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
