# Rektor uchun demo ssenariysi (10–12 daqiqa)

**Tayyorgarlik (uchrashuvdan 15 daqiqa oldin):**
```bash
cd ~/Desktop/isft/jarvis-mvp && .venv/bin/python -m app.seed && ./run.sh
```
Brauzerda http://localhost:8000 oching va bir marta Rektor sifatida kirib, bitta savol bering. Bu modelni xotiraga yuklaydi va keyingi javoblar tezlashadi. Boshqa og'ir dasturlarni (Docker va h.k.) yoping.

---

### 1. Muammo (1 daqiqa) — slayd yoki og'zaki
"Bugun bitta savolga javob olish uchun 3–5 bo'limdan ma'lumot so'raysiz. Muammo chorak oxirida ma'lum bo'ladi. JARVIS buni bir necha soniyaga qisqartiradi."

### 2. Rektor paneli (2 daqiqa)
- **Rektor** sifatida kiring.
- KPI kartalarini ko'rsating: o'rtacha ball **▼ 1.6** ga tushgan.
- **Ogohlantirishlar**ga e'tibor qarating: *"Xalqaro iqtisodiyot va moliya fakulteti 2-kurs guruhlarida o'rtacha ball 11 ballga tushgan"*. Ta'kidlang: "Bu chorak yakunini kutmasdan, hozir ko'rinadi."
- Kommunal xarajatlar 3 oy ketma-ket rejadan oshgani, 2 ta xalqaro shartnoma tugayotgani.
- Pastga tushing: xavf ostidagi talabalar **faqat guruh bo'yicha soni** bilan ko'rinadi. Ayting: "Rektorga ham shaxsiy ma'lumot xom holda chiqmaydi — taklifnomadagi tamoyil."

### 3. JARVIS bilan suhbat (3 daqiqa)
Tayyor tugmalarni bosing:
1. **"Qaysi yo'nalishda ortda qolyapmiz?"** — manbalar belgisi va tavsiyaga e'tibor qarating.
2. **"Kengash topshiriqlari bajarilyaptimi?"** — 3 ta muddati o'tgan topshiriq.
3. **"Xodimlarning pasport ma'lumotlarini ber"** — ⛔ rad etiladi. "Hatto rektor ham kadrlar shaxsiy ma'lumotini ko'ra olmaydi — bu faqat kadrlar bo'limida."

### 4. Majlis qarori → bo'limlar → rektor (4 daqiqa)
Barcha akkauntlar PIN 1234. Almashtirish: chap pastda "Lavozimni almashtirish". Bo'lim nomlari — ISFT rasmiy tuzilmasidan (2024).
1. **Rektorat kotibi** (Rahbariyat) → "Majlislar va topshiriqlar" → **"JARVIS: bayonnoma va topshiriqlar qoralamasi"** (5–15 s).
   2 ta topshiriq: Axborot texnologiyalari bo'limi — «bugun soat 15:00 gacha»; Akademik faoliyat va registrator departamenti — muddat *aytilmagan*, 1-topshiriqqa bog'liq.
   Ayting: "Majlisda aytilmagan xodim va muddatni JARVIS o'ylab topmaydi." → matnni tahrirlang → **"Tasdiqlash va bo'limlarga yuborish"** (qayta bossangiz — dublikat yo'q).
2. **Axborot texnologiyalari bo'limi boshlig'i** (Bo'limlar) → navbatdagi topshiriqni muhandisga biriktiring.
3. **Akademik faoliyat va registrator departamenti** → qarorni oching: "Yakunlash" yopiq (AT natijasi yo'q). Chatga yozing.
4. **AT bo'limi muhandisi** → "Ishni boshlash" → chatga javob → natija → "Natijani kiritish va yakunlash".
5. **Registrator departamenti** → AT natijasi ko'rinadi → "…natijasidan xabar loyihasi" → yakunlash (16 ta LMS murojaatiga javob ketadi).
6. **Rektor** → panelda "📌 Majlis qarorlari ijrosi" → "Ochish": mas'ul, holat, natija, chat, tarix. Ogohlantirishdagi "talabalarga xabar berilmagan" yo'qoladi.
Qayta ko'rsatish: kotib yoki rektor → "↺ Demoni qayta boshlash". Ovozdan matn (STT) o'rnatilmagan — "Demo transkript" deb belgilangan.

### 4b. Talabalar markazi (3 daqiqa) — registrator, tyutor, call-markaz
1. **Rektor** → panelda "🎓 Talabalar bilan ishlash markazi": faqat jamlangan raqamlar (shaxsiy ma'lumot yo'q).
2. **Call-markaz operatori** (Bo'limlar) → "Talabalar markazi": qo'ng'iroqlar navbati, telefon va "Nima deyish kerak" skripti → sanani tanlab **"Va'da berdi"** (muddat o'tsa tizim qayta qo'ng'iroq beradi).
3. **Tyutor (Xalqaro iqtisodiyot va moliya)** (Fakultet) → navbat → "Hujjat so'rash" → **"Hujjat keldi"** (holat avtomatik yopiladi) → Holatlar → O'zlashtirish → talaba kartasi → **"Otrabotka varaqasi"** → Otrabotka → **Skan yuklash** (`~/Desktop/isft/demo_otrabotka_skan.png`).
4. **Akademik faoliyat va registrator departamenti** → Navbat → turi "Ogohlantirish xati" → **"Hujjatni tayyorlash"** (OX- raqam, QR) → Otrabotka → **"Tekshirish"**: skan yonida ball → **"Tasdiqlang"** — baho bazada o'zgaradi.
Ayting: "Chegaralar namunaviy — institut nizomi bilan tasdiqlanadi; me'yoriy havolalarni tizim o'ylab topmaydi."

### 5. Bir tugmada hisobot (1 daqiqa)
"Hisobotlar" → **"Rahbariyat uchun haftalik brifing"** → Word faylni oching.

### 6. Ruxsatlar va xavfsizlik (2 daqiqa) — eng kuchli qism
- **"Lavozimni almashtirish"** → **O'qituvchi**. Faqat o'z 4 ta guruhi, qolgan hammasi 🔒.
- Suhbatda: **"Kafedra byudjetini ko'rsat"** → ⛔.
- Qayta **Rektor** → **Audit jurnali**: o'qituvchining urinishi *rad etildi* deb yozilgan.
- **Ruxsat darajalari** jadvali — taklifnomadagi jadval bilan bir xil.
- Yuqori o'ngdagi yashil nuqta: "AI shu kompyuterda ishlayapti. Internetni o'chirib ko'rsatishim mumkin." (Wi-Fi'ni o'chirib, savol bering — ishlaydi.)

### 7. Yakun (1 daqiqa)
"Bu 1 kunda qurilgan namuna, sun'iy ma'lumotlar bilan. Pilotda HEMIS'dagi haqiqiy ma'lumotlar ulanadi, bitta yo'nalishdan — o'quv ishlaridan boshlaymiz. 2–3 hafta ichida birinchi natija."

---

**Savol tug'ilsa:**
- *"Ma'lumot qayerda saqlanadi?"* — Institut serverida. Tashqi bulutga hech narsa ketmaydi, AI ham shu yerda ishlaydi.
- *"HEMIS bilan ishlaydimi?"* — Ha, pilotda HEMIS administratori orqali ulanadi. Demo bazasi HEMIS tuzilmasiga yaqin qilingan.
- *"Telegram xavfsizmi?"* — Telegram'ga faqat jamlangan ko'rsatkichlar chiqadi. Ish haqi va kadrlar ma'lumoti botga umuman chiqmaydi, buxgalteriya botga ulana olmaydi.
- *"Javob nega sekin?"* — Bu noutbuk. Server uchun kuchliroq Mac mini olinadi.

## Qo'shimcha: Hujjatlar markazi (3–4 daqiqa)

1. **Dekan** → 🗂 Hujjatlar markazi → «O'qish joyidan ma'lumotnoma» → talabani qidiring → *Hujjatni tayyorlash* → .docx oching.
   Gap: "Talaba dekanatda navbat kutmaydi — ma'lumotnoma 5 soniyada, raqam va QR bilan."
2. Shu yerda «Butun guruh» → 25 ta ma'lumotnoma bitta paketda.
3. «Yakuniy nazorat qaydnomasi» → guruh → «★ Barcha fanlar» → butun guruh qaydnomalari bir zumda.
4. **Rektor** → Hujjatlar markazi → jurnal → «imzo kutmoqda» buyruq → **✍ Imzolash**.
5. Telefonda QR-kodni skanerlang (yoki 🔍) → "Haqiqiy · rektor imzolagan". Soxta kod → "Hujjat topilmadi".
   Gap: "Soxta ma'lumotnoma muammosi yo'qoladi — har bir hujjatni bank yoki elchixona o'zi tekshira oladi."
6. **Rektor** → «Ijro nazorati» → «★ Barchasi» → muddati o'tgan barcha topshiriqlar bo'yicha rasmiy xatlar bir tugmada.

## Xizmat markazi (Offers hujjati, 1-bosqich) — 3 daqiqa

Telefon noutbuk bilan **bitta Wi-Fi**da bo'lsin (QR'lar kompyuterning lokal IP manziliga yo'naladi). macOS "kiruvchi ulanishga ruxsat berasizmi?" deb so'rasa — **Ruxsat**.

1. **Rektor → 🛠 Xizmat markazi → Murojaatlar.** "LMS uzilishi: 16 ta murojaat bitta hodisaga birlashtirildi". Aytish kerak: *"20 kishi 20 ta xabar yozdi — operator 20 marta javob yozmaydi. Tizim bitta hodisa deb aniqladi."* → **📣 16 kishiga yuborish** → hamma murojaatga bitta javob. (Ixtiyoriy: ✨ AI bilan qayta yozish — 15–25 s.)
2. **Nosozliklar (QR).** "B-204: Proyektor 60 kunda 4–5 marta buzilgan → almashtirish masalasi". **🖨 QR stikerlarni chop etish** → 39 xona uchun tayyor stiker varag'i.
   Jonli: stikerdagi QR'ni rektor telefonida skanerlatish → "Proyektor" → Yuborish → *"Bu muammo allaqachon qayd etilgan, +1 tasdiq"* (dublikat ish ochilmaydi).
3. **Tadbir qatnashuvi.** "7 ta guruh bu semestr birorta tadbirga kelmagan" — ro'yxat. **📺 QR ekranni ochish** → proyektorga; rektor telefonida skanerlab HEMIS ID kiritadi → ekrandagi hisoblagich 3 soniyada oshadi.
   Demo HEMIS ID: `sqlite3 data/jarvis.db "select hemis_id from students limit 3"`
4. Yakun: *"Bu Offers hujjatidagi 1-bosqich — integratsiyasiz, 1–2 oyda joriy qilinadi."* Hujjat: `~/Desktop/Offers_v2.docx`.

## Auditoriyalar bandligi (kamera — faqat odamlar soni) — 2 daqiqa
**Muhim:** jonli xarita real vaqtga bog'langan — demo **ish kunida 08:30–17:50** orasida bo'lsa xonalarda odamlar ko'rinadi (kechqurun hammasi 0 — bu to'g'ri).
1. **Rektor → 📷 Auditoriyalar.** Yuqorida: *"Kameralar faqat odamlar sonini uzatadi · video saqlanmaydi · yuz aniqlash o'chirilgan"* — shu jumlani ovoz chiqarib o'qing (qonun va ishonch masalasi).
2. KPI: o'rtacha bandlik ~56%, 13 ta xona 35% dan kam band → *"yangi bino/ijara o'rniga avval mavjudini to'ldiramiz"*.
3. Jonli xarita → xonani bosing → bugungi grafik (fon — jadvaldagi dars, qizil chiziq — sig'im). **B-104**: 20 o'rinli xonaga 30 kishilik guruh qo'yilgan.
4. **"Dars bor — xona bo'sh"**: bitta o'qituvchining seshanba/payshanba 5-parasida xona 4 marta bo'sh. *"Bu ayblov emas — signal; o'quv bo'limi tekshiradi."* (O'qituvchi ismini faqat rektor va o'quv prorektori ko'radi.)
5. **📷 Kameralar → + Hikvision kamerani ulash**: IP + Operator login. Hozircha 36 xona simulyatorda; haqiqiy kamera ulansa rejim avtomatik o'zgaradi.

## Demo oldidan (ertalab)
```
cd ~/Desktop/isft/jarvis-mvp && pkill -f "uvicorn app.main"; .venv/bin/python -m app.seed && ./run.sh
```
Seed vaqtlarni "hozir"ga nisbatan qo'yadi (LMS hodisasi "2 soat oldin" bo'lib turadi). Test qilib bosilgan tugmalar ham tozalanadi.
