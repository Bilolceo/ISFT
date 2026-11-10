# Ilmiy faoliyat: Ilmiy bo'lim va Magistratura

Modul: `app/ilmiy.py` (`/api/ilmiy`), interfeys: `static/ilmiy.js` / `ilmiy.css` (menyu: «Ilmiy faoliyat»), test: `tests/test_ilmiy.py`.

Mavjud jadvallar (`publications`, `grants`, `masters`) kengaytiriladi, ya'ni yangi ustunlar qo'shiladi. Shuning uchun Boshqaruv panelidagi
«Ilmiy salohiyat», «Magistratura» va AI hisobotlari o'zgarishsiz ishlaydi. Reyestrga faqat tasdiqlangan nashrlar tushadi.

## Lavozimlar

| Lavozim | Bo'limlar | Nima qiladi |
|---|---|---|
| Ilmiy bo'lim | Umumiy, Nashrlar, Grantlar, Dissertatsiyalar (faqat ko'rish) | Nashrni yakuniy tasdiqlaydi yoki qaytaradi. Scopus/WoS nashrida indeksatsiyani tekshiradi va kvartilni belgilaydi. Kafedra rejalarini tuzadi. Grantni moliyalashtiruvchiga yuboradi, natijasini (yutildi yoki rad) kiritadi. Hisobotlarni qabul qiladi yoki qaytaradi, loyihani yakunlaydi. |
| Ilmiy ishlar prorektori | Hammasi (ko'rish) | Grant arizasini imzolaydi yoki qaytaradi. Kafedra rejalarini tuzadi. |
| Magistratura bo'limi | Umumiy, Dissertatsiyalar | Mavzu va ilmiy rahbarni belgilaydi. Mavzu tasdig'ini (Ilmiy kengash bayonnomasi) va himoya natijasini (DAK, ball) qayd etadi. Har qanday bosqich natijasini kiritadi. Muddatni sabab bilan o'zgartiradi. |
| Kafedra mudiri | Hammasi, faqat o'z kafedrasi | Nashrning birinchi tekshiruvini o'tkazadi. O'qituvchi nomidan nashr kiritadi (to'g'ridan-to'g'ri Ilmiy bo'limga boradi). Grant loyihasini tuzadi. Mavzu va rahbarni taklif qiladi. 1-bob, 2-bob, ilmiy seminar va dastlabki himoya natijasini qayd etadi. |
| O'qituvchi | Nashrlar, Grantlar, Dissertatsiyalar (o'ziniki) | O'z nashrini yuboradi, qaytarilganini tuzatadi, qaytarib oladi. O'zi rahbar bo'lgan grant loyihasini tuzadi va hisobot topshiradi. Rahbarligidagi magistrantning 1-bob va 2-bobini qabul qiladi. |
| Rektor | Umumiy, Nashrlar, Grantlar (ko'rish) | Dissertatsiyalar bo'yicha faqat jamlangan sonlarni ko'radi, ismlar ko'rsatilmaydi. |
| Kuzatuv kengashi | Umumiy | Faqat jamlangan ko'rsatkichlar. |
| O'quv prorektori | Umumiy, Dissertatsiyalar (ko'rish) | |

Boshqa lavozimlar uchun javob 403. Har bir murojaat audit jurnaliga yoziladi: `science`, dissertatsiya bo'yicha esa `masters`.

## 1. Nashrlar

Ariza → **kafedra tekshiruvi** → **Ilmiy bo'lim tasdig'i** → reyestr (`publications`).

- **Qaytarish:** sabab ko'rsatish majburiy. Muallif arizani tuzatadi va qayta yuboradi; ariza yana kafedraga boradi. Kafedra yoki Ilmiy bo'lim tuzatgan bo'lsa, Ilmiy bo'limga boradi.
- **Tekshiruvlar:**
  - Scopus/WoS uchun DOI yoki bazadagi havola majburiy.
  - DOI formati tekshiriladi.
  - Nashr yili joriy yil va undan oldingi 3 yil ichida bo'lishi kerak.
  - Takror qabul qilinmaydi: bir xil DOI yoki bir muallifda bir xil sarlavha.
  - Scopus/WoS tasdig'ida «indekslanganini tekshirdim» belgisi majburiy.
- **Kafedra rejasi:** yil bo'yicha Scopus/WoS va OAK. Umumiy sahifa bajarilish foizini, ilmiy darajalilarni, nashrsiz o'qituvchilarni va tekshiruvdagi arizalarni ko'rsatadi.

## 2. Grantlar va loyihalar

Bosqichlar ketma-ketligi:
1. Loyiha
2. Prorektor imzosida (prorektor qaytarishi mumkin)
3. Imzolandi
4. Ariza yuborildi, ko'rib chiqilmoqda
5. Natija: **yutildi** (bajarilmoqda) yoki rad etildi
6. Yakunlandi

- Tanlov muddati o'tgan bo'lsa, loyihani imzoga yuborib bo'lmaydi.
- «Yutildi»da ajratilgan summa, boshlanish sanasi va muddat kiritiladi. Shundan avtomatik ravishda har 6 oyda **oraliq hisobot** va **yakuniy hisobot** jadvali tuziladi: hisobot muddati davr tugaganidan keyin 15 kun, yakuniy hisobot uchun 30 kun.
- Hisobot oqimi: rahbar topshiradi, Ilmiy bo'lim qabul qiladi yoki sabab bilan qaytaradi.
- Yakuniy hisobot qabul qilinmaguncha loyihani yakunlab bo'lmaydi.

## 3. Magistrlik dissertatsiyasi

Muddatlar qabul yilidan (Y) hisoblanadi. Kunlarni institut tasdiqlaydi.

| Bosqich | Muddat | Kim qayd etadi | Bayonnoma |
|---|---|---|---|
| Mavzu va ilmiy rahbar | Y-yil 15-noyabr | Magistratura | majburiy (Ilmiy kengash) |
| 1-bob | Y+1, 1-mart | Ilmiy rahbar, kafedra, magistratura | — |
| 2-bob | Y+1, 15-iyun | Ilmiy rahbar, kafedra, magistratura | — |
| Kafedra ilmiy seminari | Y+2, 15-mart | Kafedra, magistratura | majburiy |
| Dastlabki himoya | Y+2, 10-may | Kafedra, magistratura | majburiy |
| Himoya (DAK) | Y+2, 20-iyun | Magistratura | majburiy, ball 0–100 (o'tish ≥ 55) |

- **Ketma-ketlik:** oldingi bosqich o'tmaguncha keyingisini qayd etib bo'lmaydi. Rahbar yoki kafedra «material topshirildi» deb belgilaydi.
- **«Qayta»:** kamchiliklar yozilishi shart. Yangi muddat kamida 30 kundan keyin.
- **Ilmiy rahbar talablari:** PhD yoki DSc darajasi; ko'pi bilan 8 ta faol magistrant. Tasdiqlangan mavzu yoki rahbarni o'zgartirish uchun sabab (bayonnoma) talab qilinadi.
- **Bog'lanishlar:**
  - `masters.stage` oxirgi o'tilgan bosqichni ko'rsatadi.
  - Dastlabki himoyadan keyin «Talaba harakati → Bitiruv»dagi `theses` yozuvi «himoyaga tayyor» holatiga o'tadi.
  - Himoyadan keyin u «himoya qilindi» holatiga o'tadi va ball yoziladi.
- **Ogohlantirishlar:** muddati o'tgan bosqich, 14 kun ichida tugaydigan muddat, ko'rib chiqish kutayotgan material, rahbarsiz magistrant. Ular sarlavhada va filtrlarda ko'rinadi.

## Ogohlantirishlar (sarlavhada)

| Lavozim | Ogohlantirish |
|---|---|
| Kafedra, Ilmiy bo'lim | Tekshiruv navbatidagi nashrlar |
| O'qituvchi | Qaytarilgan arizalar |
| Prorektor | Imzo kutayotgan grantlar |
| Ilmiy bo'lim, kafedra, o'qituvchi, prorektor | Muddati o'tgan grant hisobotlari |
| Ilmiy bo'lim | Qabul kutayotgan hisobotlar |
| Magistratura, kafedra, rahbar | Muddati o'tgan bosqichlar va ko'rib chiqilishi kerak bo'lgan materiallar |

## Demo ma'lumot

Demo ma'lumotlar bir marta yaratiladi (`ilmiy_meta.seeded`) va hammasi sintetik. Tarkibi:
- 24 ta navbatdagi yoki qaytarilgan nashr arizasi; 2026 yilgi reyestr yozuvlari bog'langan.
- Kafedra rejalari.
- Mavjud grantlarga sanalar va hisobotlar qo'shilgan; 3 ta yangi loyiha (loyiha, imzoda, imzolandi holatlarida).
- 366 magistrant uchun bosqichlar.
  - 1-kurs: mavzu hali tasdiqlanmoqda.
  - 2-kurs: bosqichlar mavjud `masters.stage` qiymatidan tiklangan.
