# AI tutor (pilot)

Kursga bog'langan yordamchi: talaba dars pleyeri ichida savol beradi, javob **faqat tasdiqlangan kurs materialidan** va manba (dars, bo'lim) bilan.
Kod: `app/tutor.py` (pilot, kirish, savol → javob, pleyer API), `app/tutor_index.py` (indeks, BM25), `app/tutor_text.py` (tekshiruv),
`app/tutor_llm.py` (provayderlar), `app/tutor_admin.py` (xodimlar API), `app/tutor_player/` (panel), `static/tutor_admin.js` («Ortda qolganlar» → «AI tutor»).

## Nima uchun shunday

| Dalil | Qaror |
|---|---|
| Amaliyotga o'rnatilgan, cheklangan tutor — katta foyda (Harvard RCT, 0,63 SD) | Panel dars pleyerida, «Yordam» bilimni tekshirish yonida |
| Cheklovsiz GPT — imtihonda −17 % (Bastani, PNAS 2025) | Test savollariga faqat maslahat; javob harfi/matni filtr bilan to'siladi |
| Ixtiyoriy chat — foydalanilmaydi, ta'sir nol (Khanmigo) | Pilot — 1–2 kurs, tajriba rejimi bilan o'lchanadi |
| Jill Watson — faqat kurs materialidan | Indeks faqat tasdiqlangan eksportdan; har jumla manba bilan tekshiriladi |

## Sozlash

| O'zgaruvchi | Qiymat |
|---|---|
| `ISFT_CORE_TUTOR_PROVIDER` | `off` (standart) · `ollama` (institut serveri, `ISFT_CORE_LLM_URL`) · `claude` (`ANTHROPIC_API_KEY`) |
| `ISFT_CORE_TUTOR_MODEL` | ixtiyoriy; standart — `ISFT_CORE_MODEL` (ollama) yoki `claude-opus-5-5` (effort «low») |

Pilot: «Ortda qolganlar» → «AI tutor» → kurs tanlash → rejim (**hammaga** yoki **tajriba** — guruhlarning tasodifiy yarmi, `tajriba.arm`) →
kunlik cheklov (standart 20 savol). Faqat Masofaviy ta'lim bo'limi boshlig'i.

## Xulq

1. **Indeks** — pilot kursning tasdiqlangan paket darslari va `ds_links` orqali bog'langan, muharrirda tasdiqlangan kurslar (talabaga ochiladigan
   eksport bilan bir xil). Ma'ruza matni sarlavhalar bo'yicha bo'limlarga, ~110 so'zli parchalarga; slaydlar, subtitrlar (WebVTT), kartochkalar.
   Test / bilimni tekshirish / saralash bloklari indeksga **kirmaydi** — ular faqat maslahat rejimini aniqlash uchun (`tu_items`, Test bank ham).
   Imzo = manba paketlari id'lari: tasdiq, qaytarish yoki yangi versiyada keyingi savolda indeks qayta quriladi.
2. **Javob** — model JSON qaytaradi: jumla + manba parcha id'lari. Har faktik jumla iqtibos qilingan parcha bilan kesishishi (o'zaklarning ≥ 60 %,
   sonlar parchada) shart, aks holda olib tashlanadi; hech narsa qolmasa — «Bu savolga kurs materialida javob topilmadi» + o'qituvchiga yuborish.
3. **Maslahat** — «Yordam» tugmasi yoki savol test/Test bank savoliga mos (o'zaklarning ≥ 60 %) yoki javob so'ralsa: yo'naltiruvchi savollar;
   «to'g'ri javob», variant harfi, javob yoki variant matnini takrorlovchi jumlalar o'chiriladi.
4. **Rad** — savol kurs lug'atiga mos kelmasa (qamrov < 40 %) — model chaqirilmaydi.
5. **Xavfsizlik** — tizim ko'rsatmasi o'zgarmas; parcha va savol `<material>` / `<savol>` ichida ma'lumot (teg belgilari almashtiriladi);
   kurs matnidagi buyruqqa o'xshash jumlalar indeksga kirmaydi; savoldagi in'ektsiya jumlasi olib tashlanadi va jurnalda belgilanadi;
   savoldan ism, telefon, email, uzun raqamlar tozalanadi; chiqish — oddiy matn, kirill → lotin, inglizcha/havola/HTML jumlalar o'chiriladi.
6. **Cheklovlar** — talaba: kuniga N savol (pilot sozlamasi), daqiqada 5 ta; IP cheklovi LRS bilan umumiy.

## Pleyer va eksport

Launch (`/xapi/l/…` → `/xapi/pkg/…/index.html`) paytida, provayder yoqilgan va talaba pilot/qo'lga mos bo'lsa, `lrs.x_pkg` index.html ga
`/xapi/tutor/tutor.js` qo'shadi; API — `/xapi/tutor/{status,ask,flag,teacher}`, launch tokeni (Basic) bilan, CSP `connect-src /xapi/` ichida.
Eksport zip'lar (SCORM/xAPI) **o'zgarmaydi**. Ixtiyoriy «xAPI + tutor» eksporti (bo'lim) — skript `endpoint` + `auth` launch parametrlari
bo'lsagina ishlaydi va o'sha ISFT Core'ga murojaat qiladi.

## Ko'rish huquqi

| Rol | Ko'radi |
|---|---|
| masofaviy | hammasi + pilot sozlamasi |
| masofaviy_xodim | statistika, jurnal, savollar, indeks, eksport |
| oqituvchi | faqat o'z kursi: statistika, jurnal, savollarga javob |
| rektor, prorektor_oquv | faqat jamlangan sonlar va tajriba taqqoslash |

Jurnalda talaba ismi yo'q (taxallus `T-xxxxxx`). «Eng ko'p so'ralgan savollar» — kamida 2 xil talaba so'ragan guruhlar.
Taqqoslash: qo'llar bo'yicha testdan o'tganlar ulushi, yakunlangan darslar, o'rtacha ball (`tajriba.compare`, guruhlar darajasida 95 % oraliq).
