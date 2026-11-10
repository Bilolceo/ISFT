# Talaba kabineti

Talabaning o'z-o'ziga xizmat ko'rsatish portali: **/talaba**. Xodimlar uchun murojaatlar ro'yxati: **/talaba/xodim**.
Kod: `app/student_portal.py`, `static/talaba.html|js|css`, test: `tests/test_talaba.py`.

## Kirish

- HEMIS ID va parol bilan kiriladi. Sinov rejimida har bir talabaning boshlang'ich paroli `ISFT_CORE_STUDENT_DEMO_PASSWORD`
  (standart: `Talaba2026`). Masalan: HEMIS ID `3744642506971` (Karimova Zarina, XTA-2405, 3-kurs).
- Parol xeshi (PBKDF2, `rbac.hash_password`) talaba birinchi marta to'g'ri kirganda yaratiladi (`student_auth`).
  Birinchi kirishda parolni almashtirish majburiy: almashtirilmaguncha ma'lumot endpointlari `403 {"must_change": true}` qaytaradi.
- Yangi parol talablari: kamida 8 belgi, harf va raqam bo'lishi, sinov paroliga teng bo'lmasligi, HEMIS ID ni o'z ichiga olmasligi.
- Faqat «faol» yoki «akademik ta'til» maqomidagi talaba kira oladi. Akademik ta'tildagi talaba ma'lumotlarni ko'radi, lekin
  ma'lumotnoma so'rashi, hujjat yuklashi va apellyatsiya berishi mumkin emas.
- Sessiya alohida: cookie `tsid`, jadval `student_sessions` (bazada tokenning SHA-256 xeshi saqlanadi, `pw_tag` bilan).
  Muddati 12 soat. Parol almashtirilsa, boshqa sessiyalar yopiladi.
  Xodim cookie'si (`sid`) talaba API'sida ishlamaydi va talaba tokeni xodim API'sida ishlamaydi.
- Urinishlar cheklovi (`sessions.Limiter`): bitta HEMIS ID ga 10 daqiqada 5 ta xato, bitta IP dan 20 ta xato.
  Joriy parolni almashtirishda 5 ta xato urinish ruxsat etiladi. Rad etilgan fayl yuklashlari soatiga 10 ta bilan cheklangan.
- Noma'lum HEMIS ID va noto'g'ri parol uchun xabar bir xil, tekshirish vaqti ham bir xil.
- Audit: `audit_log` jadvaliga `user_id = NULL`, `channel = 'talaba'` bilan yoziladi; talaba `detail` maydonida
  («talaba #id · HEMIS …»). Xodimlarning qarorlari `rbac.audit` orqali `resource = 'talaba'` bilan yoziladi.

## Sahifalar

| Bo'lim | Manba |
|---|---|
| Bosh sahifa | semestr holati; ogohlantirishlar: sababsiz soatlar (30 / 48, sirtqi talabalar uchun 16 / 26), akademik qarz, oraliq < 12, kontrakt muddati, otrabotka; navbatdagi imtihon |
| Baholar | joriy semestr oraliq nazorati (12 / 30 chegarasi); yakunlangan semestrlar: ball, harf, kredit, urinishlar tarixi (`grade_attempts`); semestr va kumulyativ GPA; kreditlar 240 / 120 |
| Reyting | `rating_cache`: guruh, kurs va fakultetdagi o'rin. Faqat raqam ko'rsatiladi, boshqa talabalarning ismlari chiqmaydi |
| Davomat | `absences` yozuvlari: qaysi biri sababsiz hisoblanishi Talabalar markazi qoidasi bilan bir xil. Fanlar bo'yicha taqsimot guruh dars jadvalidan olinadi (dars qoldirish fan bilan emas, kun bilan qayd etiladi). Bu yerda «Sababli hujjat yuklash» ham bor |
| Otrabotka | `retakes`: muddat va qolgan vaqt (sahifada yangilanib turadi), holat |
| Imtihonlar | ruxsatnoma (`registrar.permit_check`, sabablari bilan); guruhning e'lon qilingan sessiya jadvali va qayta topshirish muddatlari |
| Apellyatsiya | natija e'lon qilingandan keyin 3 kun ichida beriladi (`academic_flows.create_appeal`, kanal `portal`); holatini kuzatish mumkin |
| Kontrakt | summa, to'langan qism, to'rt bosqichli jadval (`contract_plan`), keyingi muddat, uzaytirish. Faqat ko'rish uchun |
| Ma'lumotnoma | o'qish joyidan ma'lumotnoma (o'zbek yoki ingliz tilida) so'rash, holatini ko'rish, tayyor bo'lgach yuklab olish |
| Profil | ma'lumotlar (telefon qisman yashirilgan), parolni almashtirish, faol sessiyalar va ularni yopish |

## Murojaatlar (`student_requests`)

Ikki turdagi murojaat bor. Kunduzgi va masofaviy talabalarniki **Registrator ofisi** navbatiga tushadi (boshliq #17, xodim #43),
sirtqi talabalarniki **Sirtqi bo'lim** navbatiga (#27; Sirtqi bo'lim faqat sirtqi talabalarni ko'radi).

1. **Sababli hujjat.** Fayl PDF yoki JPG bo'lishi kerak, hajmi 10 MB gacha. Tekshiruv Portal bilan bir xil: `portal.safe_name` va
   `filecheck.inspect` (sehrli baytlar, bajariladigan fayllar, ixtiyoriy ClamAV). Fayl `ISFT_CORE_TALABA_DIR`
   (standart: `<DATA_DIR>/talaba_files`) papkasida tasodifiy nom bilan saqlanadi. Hujjat ro'yxatdagi dars qoldirishga
   biriktiriladi yoki sanalar qo'lda kiritiladi. **Qabul qilinsa**, dars qoldirish yozuvida sabab talaba tanlagan sababga
   almashadi va `doc_status` `tasdiqlangan` bo'ladi, ya'ni soatlar sababsizlar qatoridan chiqadi.
   Talabalar markazining holatlari keyingi davriy hisobda yangilanadi. **Rad etilsa**, sabab yozilishi shart va talaba uni ko'radi.
2. **Ma'lumotnoma.** Xodim «Ma'lumotnoma berish» tugmasini bosadi va hujjat `documents.issue("study_cert")` orqali
   xodim nomidan chiqariladi (ro'yxat raqami, QR). Talaba faqat o'z murojaati orqali, faqat `berildi` holatida va hujjat
   bekor qilinmagan bo'lsa yuklab oladi.

Xodimlar sahifasi: **/talaba/xodim** (ISFT Core'ga xodim sifatida kirilgan bo'lishi kerak). `?student=<id>` parametri
ro'yxatni bitta talabaga cheklaydi. API: `GET /api/talaba/staff/requests`, `GET …/{id}/file`, `POST …/{id}/decide`
(`qabul` | `berish` | `rad`).

## Xavfsizlik

- Barcha talaba endpointlari talaba id sini faqat sessiyadan oladi. So'rovdagi `student_id` kabi parametrlar e'tiborga olinmaydi.
- Murojaat, dars qoldirish va sessiya id lari egasi bo'yicha tekshiriladi. Begona yozuvga murojaat qilinsa, 404 qaytadi va
  audit jurnaliga yoziladi.
- Sahifa `X-Frame-Options: DENY` sarlavhasi bilan beriladi. Barcha matn chiqarishdan oldin ekranlanadi (`esc`).
- Testlar: `tests/test_talaba.py` (auth, majburiy almashtirish, bazaga moslik, ikki talaba bilan IDOR, fayllar, apellyatsiya,
  ma'lumotnoma, xodimlar ko'rib chiqishi).
