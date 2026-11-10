# Moliya: Buxgalteriya va Moliya-iqtisod prorektori

Modul: `app/moliya.py`, moslashtirish dvigateli: `app/moliya_match.py`, interfeys: `static/moliya.js`, `static/moliya.css`, testlar: `tests/test_moliya.py`.
1C va bank API ulanmagan. Hamma ma'lumot qo'lda kiritiladi yoki buxgalter qo'lidagi ko'chirma faylidan (CSV) yuklanadi.

## Kim nima qiladi

| Lavozim | Imkoniyatlar |
|---|---|
| Buxgalteriya | To'lov kiritish va storno qilish (ochiq kunda), bank ko'chirmasini yuklash, aniqlanmagan to'lovlarni biriktirish yoki belgilash, kunni solishtirib yopish, xarajat kiritish, xaridni moliyalashtirish, hisobotlar |
| Moliya-iqtisod prorektori | Hammasini ko'rish, xarajatni tasdiqlash yoki rad etish, yillik rejani o'zgartirish, yopilgan kunni qayta ochish, yopilgan kun to'lovini storno qilish, hisobotlar |
| Rektor, Kuzatuv kengashi | Faqat jamlangan ko'rsatkichlar va byudjet ijrosi, ism-shariflarsiz |
| Registrator ofisi | Talabaning to'lov holati va to'lovlar tarixi, faqat o'qish |
| Call-markaz | O'zgarish yo'q: qarzni Talabalar markazi orqali ko'radi |

Har bir ko'rish, o'zgartirish va rad etilgan urinish audit jurnaliga yoziladi. Resurslar: `contracts`, `finance`.

## To'lovlar reyestri

- Kiritiladigan maydonlar: kvitansiya raqami, sana, summa, usul (bank, Click, Payme, Uzum, kassa), to'lovchi va izoh.
- Kvitansiya raqami faol yozuvlar orasida yagona bo'lishi kerak. Takrorlansa, mavjud yozuv ko'rsatiladi (409). Raqam harf registri va bo'shliqlarni hisobga olmasdan solishtiriladi.
- Rad etiladigan to'lovlar:
  - qarzdan oshgan summa;
  - kelajakdagi sana;
  - 60 kundan eski sana;
  - kontraktsiz (grant) talaba uchun to'lov;
  - yopilgan kun uchun to'lov.
- To'lov **`students.paid_amount`** ga qo'shiladi. Talabalar markazi (kontrakt qoidasi, call-markaz navbati), Talaba kabineti, Registrator va panel aynan shu yagona manbani o'qiydi.
- Storno sabab bilan qilinadi. Summa `paid_amount` dan ayiriladi.
- Shartnoma raqami `26-SSSSS-K` ko'rinishida yoziladi: o'quv yili, talaba raqami va Luhn nazorat raqami.

## Aniqlanmagan to'lovlar (bank ko'chirmasi)

**Yuklash.** Ko'chirma CSV fayl, nusxalangan matn yoki bitta qator sifatida kiritiladi:

```
sana;summa;to'lovchi;maqsad;hujjat
10.11.2026;2 500 000;Karimov Odil;O'g'lim Nodirbek uchun kontrakt;PP-1201
```

- Ajratuvchi `;`, `,` yoki tab bo'lishi mumkin. Sarlavha qatori ixtiyoriy.
- Sana `YYYY-MM-DD` yoki `DD.MM.YYYY` formatida yoziladi.
- Bir xil qatorni ikkinchi marta yuklab bo'lmaydi. Takrorlik sana, summa, hujjat, maqsad va to'lovchi xeshi bo'yicha aniqlanadi.

**Avtomatik biriktirish** quyidagi holatlarda bajariladi:
- shartnoma raqami aniq mos keladi;
- HEMIS ID aniq mos keladi;
- otasining ismi bilan birga to'liq F.I.Sh. va guruh aniq mos keladi.

Har uch holatda ham shart bor: summa qarzdan oshmasligi kerak. Matnda boshqa odamning F.I.Sh. yozilgan bo'lsa, avtomatik biriktirilmaydi.

**Nomzodlar.** Qolgan qatorlar «Aniqlanmagan» navbatiga tushadi. Har bir qatorga 5 tagacha nomzod chiqadi, har birining bali (%) va sabablari ko'rsatiladi. Sabablar quyidagi qoidalardan olinadi:
- Kirill yozuvi lotinga o'giriladi. `oʻ/gʻ` va apostrof turlari, registr va tinish belgilari bir xillashtiriladi.
- Shartnoma raqami va HEMIS ID dagi bitta belgi xatosi, tushib qolgan yoki ortiqcha raqam, qo'shni raqamlarning o'rni almashishi hisobga olinadi («symmetric delete» indeksi).
- F.I.Sh. tokenlar bo'yicha solishtiriladi: so'zlar tartibi ahamiyatsiz, familiya ildizi (-ov/-ova) hisobga olinadi, o'xshashlik `difflib` bilan o'lchanadi.
- Ota-onani aniqlash: to'lovchining familiyasi talabanikiga mos kelsa, ismi talabaning otasining ismiga teng bo'lsa va maqsadda «o'g'lim/qizim» so'zlari bo'lsa, to'lovchi ota-ona deb hisoblanadi.
- Summa qarzga yoki navbatdagi bosqichga teng bo'lsa, ball oshadi. Qarzdan katta bo'lsa, ball kamayadi.

**Buxgalterning amallari:**
- taklifni tasdiqlash;
- qidiruv orqali boshqa talabani tanlash;
- «Shartnoma to'lovi emas» yoki «Qaytarish» deb belgilash (sabab majburiy).

Qo'lda biriktirilgan qatorlarda `match_kind='qo'lda'`, kim va qachon biriktirgani saqlanadi.

**Ikki marta o'tkazishga qarshi himoya:**
- bitta qator faqat bitta to'lovga aylanadi;
- ikkinchi tasdiq 409 qaytaradi;
- holat sharti tranzaksiya ichida tekshiriladi;
- hujjat raqami takrorlansa, avtomatik o'tkazilmaydi.

Bank qatoridan o'tgan to'lov storno qilinsa, qator yana navbatga qaytadi.

**Ogohlantirishlar.** Aniqlanmagan qatorlar soni va summasi «Umumiy» bo'limida va menyu nishonida ko'rinadi. Qator 3 kundan ortiq tursa (`UNMATCHED_ALERT_DAYS`), qizil ogohlantirish chiqadi.

## Kunlik solishtirish

- Har kun bo'yicha tizimdagi summa usullar kesimida bank yoki kassa ko'chirmasi bilan solishtiriladi.
- Farq bo'lsa, izoh majburiy. Bunday kun «farq bilan yopildi» holatini oladi.
- Yopilgan kunga to'lov kiritilmaydi.
- Yopilgan kun to'lovini faqat prorektor storno qiladi. Shunda kun summasi va farq qayta hisoblanadi.
- Kunni qayta ochish faqat prorektor ishi va sabab bilan amalga oshiriladi.

## Byudjet ijrosi va xarajatlar

- Yillik reja `fin_budget_lines` jadvalida saqlanadi. Demo uchun u `budget` jadvalining oylik rejalaridan hisoblangan.
- Fakt `budget.actual` ustunidagi qiymatlar yig'indisiga teng. Panel va hisobotlar ham shu jadvalni o'qiydi.
- Xarajat kiritilganda:
  - summa 50 mln so'mdan kichik bo'lsa va modda rejasidan oshmasa, xarajat darhol o'tkaziladi;
  - aks holda u moliya prorektori tasdig'iga tushadi.
- Tasdiqlangan xarajat `budget(month, category).actual` ga qo'shiladi.
- Modda holatlari: me'yorda / chegaraga yaqin (≥90%) / oshib ketgan (>100%) / tasdiqlansa oshadi.

## Xarid so'rovlari

Xarid bo'limi «buyurtma berildi» yoki «yetkazildi» holatiga o'tkazgan so'rovni buxgalteriya moliyalashtiradi:
- bog'langan xarajat yaratiladi (`procurements.fin_expense_id`);
- xarajat tasdiqlangach, xarid izohiga «to'langan» yoziladi.

## Hisobotlar

Oylik hisobotlar `.xlsx` (imzo qatorlari bilan) va `.csv` (UTF-8 BOM, `;`) formatlarida tayyorlanadi:
- to'lovlar reyestri;
- kunlik solishtirish;
- byudjet ijrosi.

## API (`/api/moliya`)

`GET meta, overview, students?q=, student/{id}, payments, recon?month=, budget?year=, expenses, procurements, bank?status=&q=, export?kind=&month=&fmt=`
`POST payments, payments/{id}/storno, recon/{day}/close, recon/{day}/reopen, budget/plan, expenses, expenses/{id}/decide, expenses/{id}/cancel,
procurements/{id}/fund, bank/import, bank/{id}/confirm, bank/{id}/dismiss`

## Taxminlar (tasdiqlanmagan)

Quyidagi qiymatlar va formatlar taxminiy:
- tasdiq chegarasi 50 mln so'm;
- eski to'lov chegarasi 60 kun;
- aniqlanmagan qator uchun ogohlantirish muddati 3 kun;
- shartnoma raqami formati.

Bularning hammasi `app/moliya.py` boshida yoki `moliya_match.contract_no` funksiyasida o'zgartiriladi. Demo ma'lumotlar sintetik.
