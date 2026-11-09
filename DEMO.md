# ISFT Core — rektor uchun demo ssenariysi (12–15 daqiqa)

**Tayyorgarlik (uchrashuvdan 15 daqiqa oldin):**
```bash
cd ~/Desktop/isft/jarvis-mvp && .venv/bin/python -m app.seed && ./run.sh
```
Brauzerda http://localhost:8000 oching. **Barcha akkauntlar paroli: `Isft2026`** (kirish oynasida oldindan to'ldirilgan). Bir marta Rektor sifatida kirib, bitta savol bering — mahalliy AI xotiraga yuklanadi. Boshqa og'ir dasturlarni (Docker va h.k.) yoping.

**Kirish oynasi:** lavozim guruhlari — *Rahbariyat* · *Prorektorlar* · *Bo'limlar* · *Kafedralar* (8 ta kafedra mudiri). Ism yoki lavozim bo'yicha qidirish mumkin. Boshqa lavozimga o'tish: chap pastda **«Chiqish»** → kirish oynasida boshqa lavozimni tanlang.

**Menyu (yangi tartib):**
- *Asosiy* — Boshqaruv paneli · ISFT Core bilan suhbat · AI agentlar · Majlislar va topshiriqlar
- *Ish jarayonlari* — Portal · Hujjatlar markazi · Talabalar markazi · **Murojaatlar va nosozliklar** (avval «Xizmat markazi») · Hisobotlar
- *Sozlamalar va xavfsizlik* (yig'ilgan, bosib ochiladi) — Auditoriyalar · **Tarjima va shartnoma** (avval «Yozishma yordamchisi») · Ruxsat darajalari · Audit jurnali

Rektor menyusida 9 ta bo'lim ko'rinadi. Har bir lavozim faqat o'ziga ruxsat berilgan bo'limlarni ko'radi. Tepadagi **☰** tugmasi (yoki klaviaturada `[`) menyuni faqat ikonkalar holatiga yig'adi — proyektorda ekran kengroq bo'ladi; ikonka ustiga kelinsa nomi chiqadi.

Har bir sahifa sarlavhasi ostida: *bu sahifa nima uchun* va *ma'lumot qayerdan, qachon yangilangan* (masalan, «Manba: HEMIS va buxgalteriya (sinov ma'lumotlari) · yangilandi kecha 08:00»).

---

### 1. Muammo (1 daqiqa) — slayd yoki og'zaki
"Bugun bitta savolga javob olish uchun 3–5 bo'limdan ma'lumot so'raysiz. Muammo chorak oxirida ma'lum bo'ladi. ISFT Core buni bir necha soniyaga qisqartiradi."

### 2. Rektor paneli (2 daqiqa)
- **Rektor** sifatida kiring.
- KPI kartalari va mini-grafiklar: o'rtacha ball **56.9 ▼ 1.0** (o'tgan semestr 57.9), davomat 89.2%, kontrakt tushumi 84.7%. Har bir karta ostida manba va yangilanish vaqti: *«Manba: HEMIS · 08.11, 08:00»*. Ayting: "Raqam qayerdan kelgani har doim ko'rinadi; demo bazadagi ma'lumot sun'iy."
- Ball 100 ballik tizimda: **o'tish bali 40** («3»), 65+ — «5». (Savol tug'ilsa, Registrator ofisi suhbatida: *"O'tish bali necha?"*.)
- **Ogohlantirishlar:** *"Xalqaro iqtisodiyot va moliya, 2-kurs: 48 ta guruhda o'rtacha ball keskin pasaygan — 58.4 dan 47.4 ga (−11.0)"* (guruhlar bitta ogohlantirishga birlashtirilgan — ildiz sabab bitta). "Bu chorak yakunini kutmasdan, hozir ko'rinadi."
- Kommunal xarajatlar 3 oy ketma-ket rejadan 30.6% oshgani, 2 ta xalqaro shartnoma (23 va 47 kunda) tugayotgani.
- Panel tepasidagi **AI agent taklifi** tasmasi (masalan, Hujjat agenti: hamkor shartnomasi tugayapti) — *Tasdiqlash* / *Ko'rish* / *Barchasi*. **Oldindan bosmang:** 7 ta taklif jonli demo uchun saqlangan (3b-qadam).
- **Tezkor savollar** — ISFT Core kartasidagi tayyor savol tugmalari; bittasini bossangiz suhbat ochiladi.
- «O'qishda xavf» **3 392** — *talabalar* soni (o'zlashtirish yoki davomat bo'yicha kritik/jiddiy). Pastdagi «kritik holatlar» tugmasi (~6 470) — barcha qoidalar (kontrakt, hujjat…) bo'yicha *holatlar* soni, shuning uchun kattaroq.
- «O'quv» bo'limida xavf ostidagi talabalar **faqat guruh bo'yicha soni** bilan. "Rektorga ham shaxsiy ma'lumot xom holda chiqmaydi."

### 3. ISFT Core bilan suhbat (4 daqiqa) — eng kuchli qism
Tayyor tugmalarni bosing va **agent qadamlarini** ko'rsating (qaysi bazaga murojaat qildi, nimaga ruxsat berilmadi):
1. **"Qaysi yo'nalishda ortda qolyapmiz?"** — strategik xulosa, sabab, tavsiya. Pastda yashil belgi: *"✓ 27/27 raqam manbadan tekshirildi"* (son savolga qarab o'zgaradi). "AI raqam o'ylab topa olmaydi — har bir raqam kod bilan bazadagi qiymatga solishtiriladi."
2. **"Nega?"** — agent oldingi mavzuni eslaydi: pasaygan 48 guruhning 48 tasi bitta fakultetning 2-kursida; davomat 84.2% (qolganlarda 89.5%); kontraktning yarmidan kamini to'laganlar 21.0% (qolganlarda 8.6%); ball 15 ta fanning hammasida bir xil tushgan — muammo bitta fanda emas, kurs darajasida.
3. Tavsiya yonidagi **"Dekanga topshiriq berish →"** — bir bosishda topshiriq ketadi (rektor bosgani — tasdiq), «Majlislar va topshiriqlar»da ko'rinadi.
4. **"Kontrakt tushumi yil oxiriga qancha bo'ladi?"** — prognoz ~97.6%; 2-to'lov muddati (12.11) oldidan 2 694 talaba hali yetarli to'lamagan.
5. **"Xodimlarning pasport ma'lumotlarini ber"** — ⛔ rad etiladi. "Hatto rektor ham kadrlar shaxsiy ma'lumotini ko'ra olmaydi."

Hozir server «Tahlil rejimi»da (mahalliy AI o'chiq) — javoblar kod bilan tuziladi, raqamlar baribir to'g'ri. AI ulansa matn ravonlashadi.

### 3b. AI agentlar markazi (2 daqiqa)
Menyu → **AI agentlar** (belgida 7). 6 ta agent, har birining avtonomiya darajasi (0 — faqat o'qiydi … 3 — avtomatik). "Xavfli amalni agent o'zi qilmaydi — rahbar tasdiqlaydi; har bir amal audit jurnalida."
- **Tasdiqlash kutilmoqda: 7 ta** — masalan, ijro nazorati agentining muddati o'tgan topshiriq bo'yicha rasmiy eslatmasi → **Tasdiqlash** (bitta taklifni jonli tasdiqlang).
- Panel tepasidagi **«Bugungi brifing»** — Rektor yordamchisi agenti har kuni ertalab tuzadi (Telegram ulansa 08:00 da botga ham keladi).
- "Talabalar uchun 24/7 yordamchi" — *pilot*: keyingi bosqich.

### 3c. Favqulodda kirish (30 soniya)
Panel → «O'quv» → «O'qishda xavf ostidagi talabalar» → **Ro'yxatni ochish (favqulodda kirish)** → sabab yozing → ro'yxat ochiladi. Audit jurnalida *"FAVQULODDA KIRISH"*. "Rektor ham shaxsiy ma'lumotni faqat sababini yozib ko'radi — bu iz qoldiradi."

### 3d. Qidiruv va bildirishnomalar (30 soniya)
- **Ctrl+K** (Mac'da **⌘K**) yoki tepadagi «Qidirish» → `BHM-2404` yozing: guruh topiladi (Enter — Portaldagi «Talabalar kontingenti» shu guruh bo'yicha ochiladi). Qidiruv talabalar, xodimlar, hujjatlar, xatlar, fayllar, topshiriqlar va sahifalarni qamraydi — faqat sizning ruxsatingiz doirasida (rektorga talaba ismlari chiqmaydi).
- Tepadagi **qo'ng'iroqcha** — tasdiq kutayotgan agent takliflari, imzo kutayotgan hujjatlar, muddati o'tgan topshiriqlar; bosilsa tegishli sahifa ochiladi.

### 4. Majlis qarori → bo'limlar → rektor (4 daqiqa)
Bo'lim nomlari — ISFT rasmiy tuzilmasidan.
1. **Rektorat kotibi** (Rahbariyat) → «Majlislar va topshiriqlar» → **"ISFT Core: bayonnoma va topshiriqlar qoralamasi"** (5–15 s).
   2 ta topshiriq: Axborot texnologiyalari bo'limi — «bugun soat 15:00 gacha»; Registrator ofisi — muddat *aytilmagan*, 1-topshiriqqa bog'liq.
   "Majlisda aytilmagan xodim va muddatni ISFT Core o'ylab topmaydi." → matnni tahrirlang → **"Tasdiqlash va bo'limlarga yuborish"** (qayta bossangiz — dublikat yo'q).
2. **Axborot texnologiyalari bo'limi boshlig'i** (Bo'limlar) → navbatdagi topshiriqni muhandisga biriktiring.
3. **Registrator ofisi** → qarorni oching: "Yakunlash" yopiq (AT natijasi yo'q). Chatga yozing.
4. **Axborot texnologiyalari bo'limi muhandisi** → "Ishni boshlash" → chatga javob → natija → "Natijani kiritish va yakunlash".
5. **Registrator ofisi** → AT natijasi ko'rinadi → "…natijasidan xabar loyihasi" → yakunlash: «Murojaatlar va nosozliklar»dagi LMS hodisasi bo'yicha 16 ta murojaatga javob ketadi.
6. **Rektor** → panelda **«Majlis qarorlari ijrosi»** → "Ochish": mas'ul, holat, natija, chat, tarix. Ogohlantirishdagi "talabalarga xabar berilmagan" yo'qoladi.
7. «Majlislar va topshiriqlar» sarlavhasida **Ro'yxat | Kalendar** → oy kalendari: majlislar, topshiriq va xat muddatlari, muddati o'tganlari qizil.

Qayta ko'rsatish: kotib yoki rektor → "↺ Demoni qayta boshlash". Ovozdan matn (STT) o'rnatilmagan — "Demo transkript" deb belgilangan.

### 4b. Talabalar markazi (3 daqiqa) — call-markaz va Registrator ofisi
Sarlavha ostida: *tizim o'zi aniqlagan xavf holatlari* (davomat, baho, kontrakt, hujjat) va manba — «HEMIS va buxgalteriya (sinov ma'lumotlari) · qoidalar har 10 daqiqada tekshiriladi, oxirgisi: …».
1. **Rektor** → «Talabalar markazi»: faqat jamlangan raqamlar (shaxsiy ma'lumot yo'q).
2. **Call-markaz operatori** (Bo'limlar) → qo'ng'iroqlar navbati (bugungi ro'yxat — kunlik imkoniyat 60 ta; qolganlari keyingi ish kunlariga «rejalashtirilgan», hech biri o'chirilmaydi), telefon va "Nima deyish kerak" skripti → sanani tanlab **"Va'da berdi"** (muddat o'tsa tizim qayta qo'ng'iroq beradi).
3. **Registrator ofisi** (Bo'limlar) — tyutorlar navbatini ham ko'radi va bajaradi:
   - **Mening navbatim** → turi **"Hujjat so'rash"** → topshiriq kartasi → **"Hujjat keldi"** (holat avtomatik yopiladi).
   - **Holatlar** → qoida «O'zlashtirish» → talaba → **Karta** → 40 balldan past fan yonida **"Otrabotka varaqasi"** (OV- raqam, QR).
   - **Otrabotka** → shu varaqa → **"Skan yuklash"** (`~/Desktop/isft/demo_otrabotka_skan.png`).
4. **Registrator ofisi** → Navbat → turi **"Ogohlantirish xati"** → **"Hujjatni tayyorlash"** (OX- raqam, QR) → Otrabotka → **"Tekshirish"**: skan yonida ball → **"Tasdiqlang"** — baho bazada o'zgaradi.

"Chegaralar namunaviy — institut nizomi bilan tasdiqlanadi; me'yoriy havolalarni tizim o'ylab topmaydi." (Tyutorlar akkauntlari bazada bor, lekin demo kirish ro'yxatida emas.)

### 4c. Portal: xat, rezolyutsiya va ijro nazorati (3 daqiqa)
1. **Rektor** → «Portal» (belgida **6**: o'qilmagan xatlar) → **Kiruvchi** → *ICH-2026/0001 «Kuzgi semestr kontingenti: 1-noyabr holatiga hisobot»*. Xat Registrator ofisidan keldi, ilova faylni oching.
   "Har bir xatning ro'yxat raqami va holati bor: yangi → o'qilgan → javob berilgan. O'qilganlik har bir xodim bo'yicha alohida kuzatiladi: bo'limdan bitta kishi ochgani bilan xat boshqalar uchun 'o'qilgan' bo'lib qolmaydi."
2. **Rezolyutsiya:** xatni oching → **Rezolyutsiya** → ijrochini tanlang, masalan Registrator ofisi (mas'ul) va Akademik bo'lim → muddat → izoh → **Qo'yish**.
   Ijrochilar xatni shu muddat bilan oladi, xat esa rektorning **Nazorat** qutisiga tushadi.
3. **Yana ▾ → Nazorat:** 2 ta rezolyutsiya, 1 tasi muddatdan o'tgan.
   *«Erasmus+ KA171»*: Registrator ofisi javob bergan, O'quv ishlari prorektori (mas'ul) hali javob bermagan — qizil «Ijro kechikkan».
   Ijro tugagach **Nazoratdan yechish**. "Kechikkan rezolyutsiya haqida eslatma ertalab Telegram'ga ham keladi."
4. **Barchasi** (faqat rahbariyat): 29 ta xat, 26 tasi javob kutmoqda, 2 tasi muddatdan o'tgan. Har bir xatda «Kimdan / Kimga» to'liq ko'rinadi. Rektor xat ishtirokchisi bo'lmasa, xatni faqat ko'radi va ochgani audit jurnaliga yoziladi.
5. **Bo'lim ichida ijro:**
   - *«Chiqish» → **Registrator ofisi*** (bo'lim rahbari): xatni ochib **Ijrochi tayinlash** bilan uni xodimga topshiradi.
   - *«Sirtqi guruh talabalari uchun ish joyiga ma'lumotnoma»*: Registrator bu xatni **Sirtqi bo'limga yo'naltirgan**, Sirtqi bo'lim javob bergan.
   - *Call-markaz operatori* bilan kiring → filtr **Menga biriktirilgan** → *«Sirtqi ta'lim: qishki sessiyaga chaqiruv xatlari»*. Operatorda o'qilmagan xatlar soni boshqa, chunki o'qilganlik har bir xodimga alohida.
6. **Yangi xat → Shablondan:** «Ma'lumot so'rovi» tanlang, mavzu, matn va muddat o'zi to'ldiriladi. Yozilgan xat qoralama sifatida avtomatik saqlanadi (**Qoralamalar** qutisi). Javob olingach yozishma **Yopiladi** va Arxivga o'tadi.
7. **Umumiy bazalar** → «Talabalar kontingenti» (egasi Registrator ofisi; rektor jamlangan ko'rinishni ko'radi) → **CSV yuklab olish**. "Endi so'rov xati yozib, Excel jo'natish shart emas."

Agar so'rashsa:
- **Fayllar:** har bir fayl mazmuni tekshiriladi. Nomi o'zgartirilgan exe, makrosli Word yoki xavfli arxiv qabul qilinmaydi. Ixtiyoriy ravishda ClamAV antivirusini ulash mumkin. Fayllar sha256 bilan saqlanadi, zaxira nusxa `python -m app.portal_backup` bilan olinadi.
- **Batafsil hujjat:** docs/portal.md.

Yangi bo'limlar: **Registrator ofisi**, **Akademik faoliyatni boshqarish bo'limi**, **Sirtqi bo'lim**, **Ma'lumotlar bazasi bo'limi** — har biri kirish ro'yxatida bor; o'z suhbatida masalan *"Sirtqi bo'lim nima ish qiladi?"*, *"Ma'lumotlar bazasi bo'limi vazifalari?"* — vazifalar institut taqdimotidan.

### 5. Bir tugmada hisobot (1 daqiqa)
«Hisobotlar» (tahliliy hisobotlar) → **"Rahbariyat uchun haftalik brifing"** → Word faylni oching. Sarlavha ostida manba va yangilanish vaqti. Rasmiy hujjat (buyruq, ma'lumotnoma) esa «Hujjatlar markazi»da — farqini ayting.

### 6. Ruxsatlar va xavfsizlik (2 daqiqa) — eng kuchli qism
1. **"Chiqish"** → kirish oynasi → *Kafedralar* → **Biznes boshqaruvi kafedrasi mudiri**. Panelda faqat o'z kafedrasi: **1 602 talaba** (institutda 28 905), o'rtacha ball 54.8, «O'qishda xavf» 301. Menyuda faqat 5 ta bo'lim — moliya, hisobotlar, talabalar markazi, audit umuman ko'rinmaydi (ruxsat yo'q bo'lim menyuga chiqmaydi).
2. Suhbatda: **"Kafedra byudjetini ko'rsat"** → ⛔ *"Byudjet va xarajatlar: 'Kafedra mudiri' lavozimi uchun ruxsat yo'q. So'rov audit jurnaliga yozildi."*
3. Qayta **Rektor** → menyu → *Sozlamalar va xavfsizlik* → **Audit jurnali**: kafedra mudirining urinishi qizil — *rad etildi*.
4. **Ruxsat darajalari** jadvali — taklifnomadagi jadval bilan bir xil.
5. Yuqori o'ngdagi nuqta: "AI shu kompyuterda ishlaydi. Internetni o'chirib ko'rsatishim mumkin." (Wi-Fi'ni o'chirib, savol bering — ishlaydi.)
6. Ixtiyoriy: chap pastdagi profil → **Parolni o'zgartirish** — kuch ko'rsatkichi, o'zgarish audit jurnaliga yoziladi.

### 7. Yakun (1 daqiqa)
"Bu namuna, sun'iy ma'lumotlar bilan. Pilotda HEMIS'dagi haqiqiy ma'lumotlar ulanadi, bitta yo'nalishdan — o'quv ishlaridan boshlaymiz. 2–3 hafta ichida birinchi natija."

---

**Savol tug'ilsa:**
- *"Ma'lumot qayerda saqlanadi?"* — Institut serverida. Tashqi bulutga hech narsa ketmaydi, AI ham shu yerda ishlaydi.
- *"HEMIS bilan ishlaydimi?"* — Ha, pilotda HEMIS administratori orqali ulanadi. Demo bazasi HEMIS tuzilmasiga yaqin qilingan; sahifalardagi «sinov ma'lumotlari» belgisi shuni bildiradi.
- *"Telegram xavfsizmi?"* — Telegram'ga faqat jamlangan ko'rsatkichlar chiqadi. Ish haqi va kadrlar ma'lumoti botga umuman chiqmaydi, buxgalteriya botga ulana olmaydi.
- *"Javob nega sekin?"* — Bu noutbuk. Server uchun kuchliroq Mac mini olinadi.

## Qo'shimcha: Hujjatlar markazi (3–4 daqiqa)
Sarlavha ostida: *rasmiy hujjat chiqarish — raqam va QR bilan*; tahliliy hisobotlar — «Hisobotlar»da.
1. **Registrator ofisi** → Hujjatlar markazi → «O'qish joyidan ma'lumotnoma» → talabani qidiring → *Hujjatni tayyorlash* → .docx oching.
   "Talaba navbat kutmaydi — ma'lumotnoma 5 soniyada, raqam va QR bilan."
2. Shu yerda «Butun guruh» → guruhning barcha ma'lumotnomalari bitta paketda.
3. **Akademik faoliyatni boshqarish bo'limi** → «Yakuniy nazorat qaydnomasi» → guruh → «★ Barcha fanlar» → butun guruh qaydnomalari bir zumda (o'tish bali 40).
4. **Rektor** → Hujjatlar markazi → jurnal → «imzo kutmoqda» buyruq → **✍ Imzolash**.
5. Telefonda QR-kodni skanerlang (yoki 🔍) → "Haqiqiy · rektor imzolagan". Soxta kod → "Hujjat topilmadi".
   "Har bir hujjatni bank yoki elchixona o'zi tekshira oladi."
6. **Rektor** → «Ijro nazorati» → «★ Barchasi» → muddati o'tgan barcha topshiriqlar bo'yicha rasmiy xatlar bir tugmada.

## Murojaatlar va nosozliklar (Offers hujjati, 1-bosqich) — 3 daqiqa
(Avval «Xizmat markazi».) Sarlavha ostida: *kelib tushgan murojaatlar, xonadagi QR orqali nosozliklar va tadbir qatnashuvi*. «Talabalar markazi»dan farqi: u yerda holatni tizimning o'zi topadi, bu yerda — talaba yoki xodim yozadi.

Telefon noutbuk bilan **bitta Wi-Fi**da bo'lsin (QR'lar kompyuterning lokal IP manziliga yo'naladi). macOS "kiruvchi ulanishga ruxsat berasizmi?" deb so'rasa — **Ruxsat**.

1. **Rektor → Murojaatlar va nosozliklar → Murojaatlar va hodisalar.** "LMS platformasiga kirishda uzilish: 16 ta murojaat bitta hodisaga birlashtirildi". *"16 kishi 16 ta xabar yozdi — operator 16 marta javob yozmaydi. Tizim bitta hodisa deb aniqladi."* → **16 kishiga yuborish** → hamma murojaatga bitta javob. (4-qadamda bu javobni Registrator ofisi yuborgan bo'lsa — "talabalarga xabar yuborilgan" deb turadi.) Ixtiyoriy: *AI bilan qayta yozish* (15–25 s, mahalliy AI kerak).
2. **Nosozliklar (QR).** "B-204: Proyektor 60 kunda 4 marta buzilgan → almashtirish masalasi". **QR stikerlarni chop etish** → 185 xona uchun tayyor stiker varag'i.
   Jonli: stikerdagi QR'ni rektor telefonida skanerlatish → "Proyektor" → Yuborish → *"Bu muammo allaqachon qayd etilgan, +1 tasdiq"* (dublikat ish ochilmaydi).
3. **Tadbir qatnashuvi.** "623 ta guruh bu semestr birorta tadbirga kelmagan" — ro'yxat. **QR ekranni ochish** → proyektorga; rektor telefonida skanerlab HEMIS ID kiritadi → ekrandagi hisoblagich 3 soniyada oshadi.
   Demo HEMIS ID: `sqlite3 data/jarvis.db "select hemis_id from students limit 3"`
4. Yakun: *"Bu Offers hujjatidagi 1-bosqich — integratsiyasiz, 1–2 oyda joriy qilinadi."* Hujjat: `~/Desktop/Offers_v2.docx`.

## Auditoriyalar bandligi (kamera — faqat odamlar soni) — 2 daqiqa
Menyu → *Sozlamalar va xavfsizlik* → **Auditoriyalar**. **Muhim:** jonli xarita real vaqtga bog'langan — demo **ish kunida 08:30–17:50** orasida bo'lsa xonalarda odamlar ko'rinadi (kechqurun hammasi 0 — bu to'g'ri).
1. Yuqorida: *"Kameralar faqat odamlar sonini uzatadi · video saqlanmaydi · yuz aniqlash o'chirilgan"* — shu jumlani ovoz chiqarib o'qing. Ostida: *«Manba: kamera simulyatori + dars jadvali (sinov ma'lumotlari) · har 60 soniyada yangilanadi»*.
2. KPI: o'rtacha bandlik ~66%, 10 ta xona 35% dan kam band → *"yangi bino/ijara o'rniga avval mavjudini to'ldiramiz"*.
3. Jonli xarita → xonani bosing → bugungi grafik (fon — jadvaldagi dars, qizil chiziq — sig'im). **B-103** va **B-104** (20 o'rin) 4 haftada sig'imning 110% dan oshgan (27–28 kishi) — xo'jalik bo'limiga ogohlantirish.
4. **"Dars bor — xona bo'sh"**: bitta o'qituvchining darslarida xona 2 hafta ichida 4 marta bo'sh. *"Bu ayblov emas — signal; o'quv bo'limi tekshiradi."* (O'qituvchi ismini faqat rektor va o'quv prorektori ko'radi.)
5. **Kameralar → + Hikvision kamerani ulash**: IP + Operator login. Hozircha 180 ta xona simulyatorda; haqiqiy kamera ulansa rejim avtomatik o'zgaradi.

## Kameralar va xavfsizlik (kamera — faqat metama'lumot) — 3 daqiqa
Menyu → *Sozlamalar va xavfsizlik* → **Kameralar va xavfsizlik**. Avval ovoz chiqarib: *"Kameralar odamni emas, xonani sanaydi: rasm va video saqlanmaydi, yuzni tanish o'chirilgan (ZRU-547)."*
1. **Holat**: 193 kamera bino × qavat kesimida (yashil/sariq/qizil). **B-302** — 3 kundan beri oflayn, tiket muddati o'tgan (hikoya 4). 4 ta kamera to'sib qo'yilgan, 2 tasida soat farqi, 5 tasida eski proshivka (CVE).
2. **Voqealar**: P1–P4. **Serverxona** — tungi kirishlar: ikkitasi «noto'g'ri signal», bugungi 02:14 dagisi tiketga aylangan (hikoya 3). Takrorlar 5 daqiqa oynada birlashadi (×N). Rektor yoki xo'jalik: **Noto'g'ri signal** tugmasi → statistika yangilanadi.
3. **Navbat va olomon**: Qabul komissiyasi — *"Dushanba 10:00–12:00 — o'rtacha 28 kishi (chegara 20)"* (hikoya 2). Oshxona tushlikda sig'imning ~120–125% (hikoya 5). Majlislar zali: ro'yxatdan o'tganlar vs kamera.
4. **Auditoriyalar** sahifasida: «Xonalarni optimallashtirish» — **C-107** va **C-207** 2 hafta jadvalga qaramay bo'sh (hikoya 1); «Eng band soatlar», «Dars yo'q — 20+ kishi».
5. **Haftalik hisobot (.docx)** — rasmiy blank, QR bilan tekshiriladi. Suhbatda: *"Kecha qaysi xonalar bo'sh turdi?"*, *"Bu hafta nechta xavfsizlik voqeasi bo'ldi?"* — javob faqat bazadagi faktlardan.
Hammasi sun'iy (demo); haqiqiy kameralar ulangach haqiqiy voqealar keladi. Batafsil: `docs/hikvision.md`.

## Tarjima va shartnoma yordamchisi (ixtiyoriy, mahalliy AI kerak)
(Avval «Yozishma yordamchisi»; bo'limlararo xatlar — Portalda.) Menyu → *Sozlamalar va xavfsizlik* → **Tarjima va shartnoma**. Namuna «shartnoma» → **Shartnomani tekshirish**: xavfli bandlar va tavsiya. Sarlavha ostida AI holati ko'rinadi: AI o'chiq bo'lsa natija chiqmaydi — demo oldidan `ollama serve`.

## Demo oldidan (ertalab)
```
cd ~/Desktop/isft/jarvis-mvp && pkill -f "uvicorn app.main"; .venv/bin/python -m app.seed && ./run.sh
```
Seed vaqtlarni "hozir"ga nisbatan qo'yadi (LMS hodisasi "2 soat oldin" bo'lib turadi). Test qilib bosilgan tugmalar ham tozalanadi. Agent takliflarini (8 ta) demo oldidan tasdiqlamang.
