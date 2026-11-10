# Kadrlar bo'limi

Kod: `app/kadrlar.py` (API `/api/hr/*`), `static/kadrlar.js`, `static/kadrlar.css`, test: `tests/test_kadrlar.py`.

Ta'til, xizmat safari va kasallik varaqasi bu modulda yo'q. Ular «Xodimlar ta'tili» bo'limida yuritiladi (`app/staff_absence.py`). Shaxsiy ish kartasida faqat ularga havola bor.

## Nimalar bor

| Jarayon | Qanday ishlaydi |
|---|---|
| Shaxsiy ish | Lavozim, bo'linma, stavka, ma'lumoti, mutaxassisligi, ilmiy daraja va unvon, mehnat shartnomasi (turi, raqami, muddati), oxirgi attestatsiya va malaka oshirish sanasi. Shartnoma va attestatsiya tarixi ham saqlanadi. |
| Mehnat shartnomasi | Ogohlantirish beriladi: muddat 30 yoki 60 kun ichida tugasa, yoki o'tib ketgan bo'lsa. Uzaytirish tarixga yoziladi. Muddatli shartnoma 5 yildan oshmaydi. |
| Attestatsiya va malaka oshirish | Har 5 yilda o'tkaziladi. Belgilar: «muddati o'tgan», «qayd yo'q», «90 kun ichida». Malaka oshirish o'qituvchilar uchun yuritiladi. |
| Shtat jadvali | Har bir bo'linma va lavozim uchun reja stavkalar beriladi. Amaldagi son faol xodimlar stavkalarining yig'indisi. Ikkalasining farqi bo'sh va ortiqcha stavkalarni ko'rsatadi. |
| Ishga qabul | Vakansiya → rektor tasdig'i → nomzodlar (ariza → suhbat → tanlandi) → rektor tasdig'i → «Buyruqlar»da `xodim_qabul` loyihasi → rektor imzosi → xodim bazaga qo'shiladi (`staff`; kafedra uchun `teachers`) → Portal orqali AT bo'limiga akkaunt so'rovi. |
| Ishdan bo'shatish | Ariza → topshirish varaqasi → «Buyruqlar»da `xodim_boshatish` loyihasi → rektor imzosi → shaxsiy ish «bo'shatilgan» holatiga o'tadi. Varaqa bandlari: akkauntlar bloklandi, moddiy boyliklar, kutubxona, ish hujjatlari, hisob-kitob. Buyruq faqat varaqa to'liq bo'lsa tuziladi. AT bo'limiga bloklash so'rovini istalgan bosqichda yuborish mumkin. |

Buyruq loyihasi «Buyruqlar» bo'limidan o'chirilsa, nomzod yoki bo'shatish jarayoni avvalgi bosqichiga qaytadi.

Imzolangan buyruq har safar ma'lumot o'qilganda shaxsiy ishga avtomatik ta'sir qiladi (`_sync_orders`). Qayta ishlash xavfsiz: bir buyruq ikki marta ta'sir qilmaydi.

## Kim nima qiladi

| Rol | Imkoniyat |
|---|---|
| Kadrlar bo'limi (`kadrlar`) | Hammasi: shaxsiy ishlar, uzaytirish, attestatsiya, shtat jadvali, vakansiya, nomzodlar, buyruq loyihalari, AT so'rovlari, bo'shatish varaqasi. |
| Rektor | Jamlangan ko'rsatkichlar va bo'linmalar kesimi; xodimlarning ismi va shaxsiy ma'lumoti ko'rinmaydi. Vakansiya va nomzodni tasdiqlaydi yoki sabab yozib rad etadi. Buyruqni «Buyruqlar»da imzolaydi. |
| Bo'lim rahbari / kafedra mudiri | Faqat o'z bo'limi: xodimning ismi, lavozimi, stavkasi va muddat belgilari (sanalar va shaxsiy ma'lumotlarsiz). Shtat jadvalini ko'radi, vakansiya taklif qiladi. |
| Qolgan xodimlar | O'z shaxsiy ishini «Shaxsiy ma'lumotlar» oynasida ko'radi, faqat o'qish uchun (`/api/hr/me`). |

Qo'shimcha cheklovlar:

- Telegram kanali orqali hech qanday kadrlar ma'lumoti berilmaydi (`rbac.TELEGRAM_BLOCKED`).
- Har bir ko'rish, o'zgartirish va rad etilgan urinish audit jurnaliga `hr` resursi bilan yoziladi.

## API qisqacha

- **Umumiy:**
  - `GET meta`
  - `GET summary`
  - `GET alerts`
- **Xodimlar:**
  - `GET staff?q=&unit=&flag=contract:d30|expired`
  - `GET staff/{id}`, `POST staff/{id}`
  - `POST staff/{id}/renew`
  - `POST staff/{id}/training`
  - `GET me`
- **Shtat jadvali:** `GET staffing`, `POST staffing`
- **Vakansiyalar:**
  - `GET vacancies`, `POST vacancies`
  - `POST vacancies/{id}/submit | decide | close | candidates`
- **Nomzodlar:** `POST candidates/{id}/stage | decide | order | it-request`
- **Bo'shatish:**
  - `GET dismissals`, `POST dismissals`
  - `POST dismissals/{id}/check | it-request | order | cancel`

## Demo ma'lumotlar

Barcha demo ma'lumotlar sintetik. Ular faqat jadvallar bo'sh bo'lganda yaratiladi.

- Mavjud `staff` ro'yxatidagi har bir xodim uchun shaxsiy ish yaratiladi. Qiymatlar deterministik.
- Shtat jadvali amaldagi stavkalar asosida tuziladi, ayrim lavozimlarda bo'sh stavka qoldiriladi.
- 4 ta vakansiya: 2 tasi ochiq, 1 tasi rektor tasdig'ida, 1 tasi bo'lim taklifi.
- Nomzodlar «Nomzod A. (sintetik)» kabi nomlangan.
- 1 ta bo'shatish jarayoni (topshirish varaqasi bosqichida).
