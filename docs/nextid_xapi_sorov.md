# NextBrain'ga texnik so'rov: NEXTID.LMS da xAPI natijalarini saqlash

**Kimga:** NextBrain MChJ, NEXTID.LMS ishlab chiquvchilar jamoasi
**Kimdan:** ISFT instituti, Masofaviy ta'lim bo'limi (texnik aloqa — ISFT Core jamoasi)
**Mavzu:** my.isft.uz da xAPI (Tin Can) paketlarni launch parametrlari bilan ishga tushirish yoki natijalarni bizga uzatish

> Matndagi `core.isft.uz` — ISFT Core manzili uchun misol; haqiqiy manzil joylashtirilgandan keyin yuboriladi.

---

Hurmatli hamkasblar!

Institut masofaviy ta'lim darslarini NEXTID.LMS (my.isft.uz) ga xAPI paket (`tincan.xml` bilan .zip) sifatida yuklaydi —
Articulate Rise 360 eksportlari va o'zimizning paketlar («ISFT Core»). Tahlil natijasida quyidagi muammo aniqlandi.

## 1. Muammo

1. **Paket launch parametrlarisiz ochilmoqda.** NEXTID paketni `index.html` ni iframe'da ochadi, lekin so'rov qatorida xAPI launch
   parametrlari (`endpoint`, `auth`, `actor`, `registration`, `activity_id`) yo'q. Natijada paket ichidagi pleyer statementlarni hech qayerga
   yubora olmaydi: savollarga javoblar, test bali, urinishlar soni, sarflangan vaqt **saqlanmaydi**.
2. **Faqat foiz ko'rinadi.** NEXTID har dars bo'yicha bitta progress foizini ko'rsatadi. Qaysi savolda xato qilingani, testdan necha marta
   o'tolmagani, oxirgi marta qachon kirgani ma'lum emas.
3. **Ortda qolganlar ko'rinmaydi.** Misol (bitta talaba, haqiqiy kuzatuv): «Iqtisodiyot nazariyasi 1» fanida 45 ta dars (L1–L15 ma'ruza,
   A1–A30 amaliy). Semestrning ~11-haftasida talaba 6/45 darsni 100 % qilgan, qolganlari 0 %. Bu holatni hech kim o'z vaqtida ko'rmagan.

## 2. So'raladigan imkoniyatlar (ustuvorlik tartibida)

### A variant (afzal): xAPI launch parametrlari

Paketni ochishda Rustici «xAPI Launch» (Tin Can launch) qoidasi bo'yicha so'rov qatoriga quyidagilarni qo'shish:

| Parametr | Qiymat | Izoh |
|---|---|---|
| `endpoint` | LRS manzili, `/` bilan tugaydi | NEXTID ichidagi LRS **yoki** bizning LRS: `https://core.isft.uz/xapi/` |
| `auth` | `Basic <base64>` | har ishga tushirish uchun alohida, muddatli token (umumiy parol emas) |
| `actor` | JSON, `account` shaklida | **barqaror talaba identifikatori** — HEMIS ID yoki NEXTID foydalanuvchi ID; ism va email shart emas |
| `registration` | UUID | talaba × kurs (yoki urinish) bo'yicha barqaror |
| `activity_id` | `tincan.xml` dagi launch faoliyati | masalan `https://isft.uz/xapi/paket/121/3` |

Actor namunasi:

```json
{"objectType": "Agent", "account": {"homePage": "https://my.isft.uz", "name": "3663373573636"}}
```

Agar statementlar NEXTID ichidagi LRS'ga yozilsa, ularni bizga o'qish uchun xAPI `GET /statements` (filtrlar: `activity`, `since`,
`related_activities=true`) va o'qish huquqli alohida kalit kerak bo'ladi.

### B variant: cmi5

NEXTID cmi5 (xAPI profili) ni qo'llab-quvvatlasa, paketlarni cmi5 ko'rinishida (`cmi5.xml`) eksport qilishga tayyormiz. cmi5 da launch
parametrlari (`endpoint`, `fetch`, `actor`, `registration`, `activityId`) majburiy — muammo o'z-o'zidan hal bo'ladi.

### C variant: dars bo'yicha progress API yoki webhook

Kamida quyidagi ma'lumotni beradigan API (yoki har o'zgarishda webhook):

`talaba ID (HEMIS) · kurs ID · dars kodi (L3 / A12) · holat (boshlanmagan / jarayonda / yakunlandi / o'tdi / o'tmadi) · foiz · ball ·
urinishlar soni · oxirgi faollik vaqti · sarflangan vaqt`

Format — JSON, sahifalash va `updated_since` filtri bilan; kirish — server-server token.

## 3. Muqobil taklif (NEXTID tomonida minimal o'zgarish)

Agar yuqoridagilar tez amalga oshmasa, ikki oddiy yo'l bor — ikkalasi uchun ham ISFT Core tomoni tayyor:

1. **NEXTID bizning launch havolamizni ochadi.** Darsga «tashqi havola» sifatida ISFT Core havolasi qo'yiladi; NEXTID uni talabaning
   barqaror ID'si va imzo bilan ochadi. Biz paketni o'zimizda xAPI launch parametrlari bilan ishga tushiramiz va natijani o'zimizning
   LRS'da saqlaymiz. Havola formati (taklif):

   ```
   https://core.isft.uz/xapi/nextid/launch?course=dl:121&lesson=L3&student=<HEMIS ID>&ts=<unix vaqt>&sig=<HMAC-SHA256>
   ```

   `sig = HMAC_SHA256(umumiy_kalit, "dl:121|L3|<HEMIS ID>|<ts>")`, havola 5 daqiqa amal qiladi. Kalit faqat NEXTID serverida turadi —
   paket ichiga yoki brauzerga tushmaydi. (Hozir ISFT Core'da talabaning shaxsiy havolasi ishlaydi: `https://core.isft.uz/xapi/l/<kod>` —
   NEXTID imzosini qabul qiluvchi kirish nuqtasi kelishuvdan keyin qo'shiladi.)

2. **NEXTID statementlarni bizga uzatadi.** NEXTID o'z LRS'iga kelgan (yoki o'zi yaratgan) statementlarni bizning LRS'ga POST qiladi:

   ```
   POST https://core.isft.uz/xapi/statements
   Authorization: Basic <nextid:server_kaliti>          (server-server, IP cheklovi bilan)
   X-Experience-API-Version: 1.0.3
   Content-Type: application/json
   ```

   Actor — `{"account": {"homePage": "https://my.isft.uz", "name": "<HEMIS ID>"}}`; faoliyatlar — paketdagi `tincan.xml` identifikatorlari.
   Bitta so'rovda ≤ 100 statement, statement id (UUID) takrorlansa — qayta yozilmaydi (xavfsiz qayta urinish).

## 4. Namuna statement (talaba testdagi savolga javob berdi)

```json
{
  "id": "6a1f7b8e-2c3d-4e5f-8a9b-0c1d2e3f4a5b",
  "actor": {"objectType": "Agent", "account": {"homePage": "https://my.isft.uz", "name": "3663373573636"}},
  "verb": {"id": "http://adlnet.gov/expapi/verbs/answered", "display": {"en-US": "answered"}},
  "object": {
    "objectType": "Activity",
    "id": "https://isft.uz/xapi/paket/121/A2/block/b9/q/tb121023",
    "definition": {
      "type": "http://adlnet.gov/expapi/activities/cmi.interaction",
      "name": {"uz": "A2 — 3-savol"},
      "interactionType": "choice",
      "choices": [{"id": "a", "description": {"uz": "Talab kamayadi"}}, {"id": "b", "description": {"uz": "Talab oshadi"}}],
      "correctResponsesPattern": ["a"]
    }
  },
  "result": {"success": false, "response": "b"},
  "context": {
    "registration": "0f8b1c2d-3e4f-5a6b-7c8d-9e0f1a2b3c4d",
    "contextActivities": {"parent": [{"objectType": "Activity", "id": "https://isft.uz/xapi/paket/121/A2"}]},
    "platform": "ISFT Core", "language": "uz"
  },
  "timestamp": "2026-11-14T09:41:27.120Z"
}
```

Paketlarimiz shuningdek `initialized`, `progressed` (cmi5 progress kengaytmasi), `experienced`, `passed` / `failed` (ball bilan),
`completed`, `suspended`, `resumed`, `terminated` (sarflangan vaqt bilan) statementlarini yuboradi.

## 5. Xavfsizlik va shaxsiy ma'lumot

- Launch URL'da talabaning ismi va emaili bo'lmasligi kerak — faqat barqaror ID (HEMIS yoki NEXTID ichki ID).
- `auth` — har ishga tushirish uchun alohida, muddati cheklangan, faqat shu talaba va shu dars faoliyatlariga yozish huquqi bilan.
- Server-server kalitlari — faqat serverlarda, kalitni almashtirish tartibi kelishiladi.

## 6. Kutilayotgan javob

Iltimos, quyidagilarni ma'lum qiling:

1. A, B yoki C variantlardan qaysi biri qachon amalga oshirilishi mumkin;
2. NEXTID ichida LRS bormi va unga tashqi o'qish kirishi beriladimi;
3. talabaning barqaror identifikatori sifatida nima beriladi (HEMIS ID yoki NEXTID ID) va moslash jadvali qanday olinadi;
4. muqobil taklif (3-bo'lim) bo'yicha texnik uchrashuv uchun qulay vaqt.

Texnik savollar uchun ISFT Core jamoasi bilan bevosita bog'lanishingiz mumkin. Hamkorligingiz uchun oldindan rahmat.

Hurmat bilan,
Masofaviy ta'lim bo'limi, ISFT instituti
