# AI Hikvision kameralar — modul qo'llanmasi (v0.2, 2026-11-09)

> Hamma narsa **metama'lumot** asosida: vaqt, kamera, voqea turi, son, holat. Video, kadr, yuz tasviri **olinmaydi va saqlanmaydi**.

## 1. Tamoyillar

- **Privacy-by-design.** Bazaga faqat voqea metama'lumoti yoziladi (vaqt, kamera, tur, son, holat). alertStream'dagi JPEG qismlar
  xotirada o'qiladi-yu, diskka yozilmasdan tashlab yuboriladi (`AlertStreamParser.dropped_bytes`).
- **Shaxs bog'lanmaydi.** Kamera voqeasi hech qaysi talaba yoki xodim ismiga bog'lanmaydi. Hisobotlar faqat xona / bino / qavat
  kesimida va jamlangan holda chiqadi.
- **Biometrika o'chiq.** Yuz aniqlash O'RQ-547 «Shaxsga doir ma'lumotlar to'g'risida» qonuniga ko'ra alohida yozma rozilik va
  huquqiy asos talab qiladi. Kod `ISFT_CORE_FEATURE_FACE=0` bayrog'i ortida; ANPR (davlat raqami) — `ISFT_CORE_FEATURE_ANPR=0`,
  faqat xodimlar avtomobillari ro'yxati uchun. Seed/demo'da ikkalasi ham **o'chiq**. Bayroq o'chiq bo'lsa, bu voqealar qayta ishlanmaydi.
- **Boshqaruv huquqi.** Kamera qo'shish, sozlash, parol kiritish — faqat `rektor` va `xojalik` (Xo'jalik va texnik bo'lim) rollari.
  Har bir amal audit jurnaliga yoziladi.
- **Server vaqti.** Voqea vaqti kamera soati bo'yicha emas, **server vaqti** bo'yicha qo'yiladi (`ISFT_CORE_TZ`, standart
  `Asia/Tashkent`). Kamera soati serverdan 60 s dan ko'p farq qilsa — ogohlantirish (NTP tekshirilsin).
- **Bulut ≠ LAN.** Railway (bulut) institut lokal tarmog'iga ulana olmaydi. Ulagich (connector) institut ichidagi serverda ishlaydi;
  bulutdagi nusxa faqat demo/seed rejimida.

## 2. Modul funksiyalari

**A) Bandlik va oqim.** Odamlar soni (kirdi − chiqdi yoki hudud bo'yicha sanash) va xona sig'imiga nisbatan %.
Belgilar: «dars bor — xona bo'sh» va «dars yo'q — 20+ kishi». Sig'im > 110% → xo'jalikka ogohlantirish (`sigim_oshdi`).
Soatlik/haftalik grafiklar; bo'sh turgan xonalarni optimallashtirish tavsiyasi.

**B) Xavfsizlik voqealari.** Hikvision `eventType` → normallashtirilgan tur + ustuvorlik P1–P4 (3-bo'lim jadvali).
Takrorlarni birlashtirish oynasi **5 daqiqa** (`ISFT_CORE_CAM_DEDUP_SEC=300`): oyna ichidagi bir xil voqealar bitta yozuvga
birlashadi, soni `dup` maydonida. Mas'ul xodim voqeani **«noto'g'ri signal»** deb belgilashi mumkin — statistikada alohida
hisoblanadi (kamera/zona sozlamasini yaxshilash uchun). Voqeadan bir tugma bilan **ariza (ticket)** ochiladi.

**C) Navbat va olomon.** Qabul, Kassa, Oshxona: navbat uzunligi va kutish vaqti. Chegara oshsa → mas'ul bo'limga xabar
(Qabul → qabul komissiyasi, Kassa → buxgalteriya, Oshxona → xo'jalik) va rektor KPI'siga. Tadbir zali: kamera bo'yicha to'lish
vs `event_checkin` (ro'yxatdan o'tganlar) solishtiriladi.

**D) Kameralar salomatligi.** Onlayn/oflayn, oxirgi yurak urishi, proshivka yoshi, soat farqi. 10 daqiqa javob yo'q → **bitta**
avtomatik nosozlik arizasi («Murojaatlar va nosozliklar»), kamera qaytganda avtomatik yopiladi. «Kameralar holati» sahifasi:
bino/qavat bo'yicha yashil (onlayn) / sariq (ogohlantirish: soat farqi, eski proshivka, bloklangan) / qizil (oflayn).

**E) Hisobot va AI.** Haftalik xavfsizlik hisoboti `.docx` (QR-kod bilan tekshiriladi). Chatdagi AI javoblari faqat bazadagi
faktlardan (taxmin qilmaydi). Rektor bosh sahifasida bitta KPI kartasi (ochiq P1/P2, oflayn kameralar, navbat).

**F) Ixtiyoriy bayroqlar.** `ISFT_CORE_FEATURE_FACE`, `ISFT_CORE_FEATURE_ANPR` — standart `0` (o'chiq). Yoqishdan oldin yurist
xulosasi, yozma rozilik va AT/xavfsizlik bo'limi qarori kerak.

## 3. Voqealar xaritasi

«Tun» = `ISFT_CORE_WORK_HOURS` (standart `07:30-20:00`) dan tashqari yoki yakshanba.
Qo'riqlanadigan zonalar: serverxona, texnik xona, tom (xonada `guard=1`).

| Hikvision `eventType` | ISFT Core turi | Kun / Tun | Kimga |
|---|---|---|---|
| `fireDetection` | `yongin` | P1 / P1 | rektor + xojalik |
| `smokeDetection` | `tutun` | P1 / P1 | rektor + xojalik |
| `TMA` / `TMPA` / temperature | `harorat` | P1 / P1 | rektor + xojalik |
| `fielddetection`, `regionEntrance` | `hududga_kirish` | P3 / P2 (qo'riqlanadigan zona); qo'riqlanmaydigan xonada bir daraja past | xojalik |
| `linedetection` | `chiziq_kesish` | P4 / P2 (qo'riqlanadigan) | xojalik |
| `regionExiting` | `hududdan_chiqish` | P4 / P3 | xojalik |
| `loitering` | `uzoq_turish` | P3 / P2 | xojalik |
| `peopleGathering` | `toplanish` | P3 / P2 | xojalik, yoshlar prorektori |
| `running` | `yugurish` | P4 / P3 | xojalik |
| `unattendedBaggage` | `qarovsiz_buyum` | P2 / P2 | xojalik + rektor |
| `attendedBaggage`, `objectRemoval` | `buyum_olindi` | P3 / P2 | xojalik |
| `shelteralarm`, `tamperdetection` | `kamera_yopildi` | P2 (ariza ochiladi) | xojalik |
| `videoloss` (active) | `video_yoqoldi` | P3 | xojalik |
| `videoloss` (inactive) | — yurak urishi, saqlanmaydi | — | — |
| `defocus`, `scenechangedetection` | `kamera_siljidi` | P3 | xojalik |
| `VMD` | `harakat` | P4 / P3 — faqat qo'riqlanadigan zonada saqlanadi, boshqa joyda shovqin sifatida tashlanadi | xojalik |
| `personQueueDetection`, `queueManagement` | `navbat` | P3 | zona bo'yicha: Qabul → qabul komissiyasi, Kassa → buxgalteriya, Oshxona → xo'jalik |
| (ichki) xona > 110% sig'im | `sigim_oshdi` | P3 | xojalik |
| `regionPeopleCounting`, `peopleCounting` | `odam_soni` | — (faqat son) | bandlik hisobi |
| yuz / ANPR voqealari | — | tashlanadi (bayroq yoqilmagan bo'lsa) | — |
| noma'lum tur | `boshqa:<tur>` | P4 | yo'qolmaydi, tahlil uchun saqlanadi |

## 4. Qaysi funksiya qaysi kamera modelida ishlaydi

> **Taxminiy** — har model datasheet'i va proshivkasi bo'yicha AT bo'limi tasdiqlashi kerak.
> Emulyatordagi `/ISAPI/Event/triggers` ro'yxati shu jadvalga mos (`FAKE_HIK_MODEL`).

| Funksiya | DS-2CD3D46G2T (oddiy) | DS-2CD2346G2-ISU/SL (AcuSense) | iDS-2CD7A46G0 (DeepinView) | DS-2TD2617 (termal bi-spektr) |
|---|---|---|---|---|
| Harakat (VMD), videoloss, kamera yopildi | ✓ | ✓ | ✓ | ✓ |
| Chiziq kesish, hududga kirish | ✓ | ✓ | ✓ | ✓ |
| Hududga kirish/chiqish (`regionEntrance`, `regionExiting`) | — | ✓ | ✓ | — |
| Fokus/sahna o'zgarishi | — | ✓ | ✓ | — |
| Uzoq turish, to'planish, yugurish | — | — | ✓ | — |
| Qarovsiz buyum / buyum olindi | — | — | ✓ | — |
| Navbat (uzunlik, kutish vaqti) | — | — | ✓ | — |
| Odam sanash (kirdi/chiqdi, hudud) | — | ≈ (chiziq kesishdan taxminiy) | ✓ | — |
| Yong'in, tutun, harorat (TMA) | — | — | — | ✓ |

- Navbat, qarovsiz buyum, yugurish, odam sanash — asosan DeepinView (qisman AcuSense) modellarida. Oddiy kameralar faqat harakat va
  chiziq kesishni beradi.
- Sanashsiz AcuSense'da bandlik faqat chiziq kesish voqealaridan **taxminiy** hisoblanadi (aniqligi past — UI'da shunday belgilanadi).

## 5. Kod

| Fayl | Vazifasi |
|---|---|
| `app/hikvision.py` | ISAPI mijozi: Digest, HTTPS, imkoniyatlarni aniqlash (probe), soat farqi, odam sanash, voqealar oqimi parseri, normallashtirish, ogohlantirishlar |
| `app/camsec.py` | Xavfsizlik voqealari: ustuvorlik P1–P4, takrorlarni birlashtirish, «noto'g'ri signal», navbat, salomatlik, haftalik hisobot, AI suhbat uchun faktlar |
| `app/secret_store.py` | Kamera parollari bazadan alohida (Fernet — `cryptography` o'rnatilsa; aks holda 0600 fayl) |
| `app/occupancy.py` | So'rovchi, ketma-ket xato → nosozlik arizasi (tiklanganda avtomatik yopiladi), voqealar tinglovchilari (backoff bilan qayta ulanish) |
| `tools/fake_hikvision.py` | ISAPI emulyatori (ishlab chiqish va test uchun) |
| `tests/test_hikvision.py` | Parser, Digest, xatolar, probe, sanash, oqim, migratsiya, arizalar, voqealar, tinglovchi |

## 6. Haqiqiy kamerani ulash

1. AT bo'limidan 7-bo'limdagi ma'lumotlarni olish.
2. Institut ichidagi serverda ulagichni ishga tushirish (bulut LAN'ga yeta olmaydi).
3. **Xo'jalik va texnik bo'lim** (yoki rektor) akkaunti → Auditoriyalar → «+ Hikvision kamerani ulash»: xona, IP, port, foydalanuvchi,
   parol; kerak bo'lsa «Voqealar oqimi» va «Ish vaqtidan tashqari kirishni kuzatish». Amal audit jurnaliga yoziladi.
4. Saqlash bilan birga **probe**: model, proshivka, odam sanash bormi, voqealar bormi, soat farqi. Ogohlantirishlar ro'yxatda ko'rinadi.
5. Pilot: 2–3 xonada kamera soni bilan qo'lda sanashni solishtirish (maqsad: ±2 kishi); 1 hafta voqealarni «noto'g'ri signal» bo'yicha ko'rib chiqish.

## 7. AT bo'limidan nima so'rash kerak

- [ ] Kameralar ro'yxati: model, proshivka versiyasi, IP, bino / qavat / xona (yoki zona: Qabul, Kassa, Oshxona, serverxona…).
- [ ] NVR modeli (kameralar NVR orqali ulanganmi — kanal raqamlari).
- [ ] VLAN va firewall qoidasi: ISFT Core serveri → kameralar, port 80/443 (faqat shu yo'nalish).
- [ ] Har kamerada alohida faqat o'qish uchun **«Operator»** ISAPI foydalanuvchisi (admin emas).
- [ ] NTP server manzili (kamera soatlari bir xil bo'lishi uchun).
- [ ] Qaysi aqlli voqealar litsenziyalangan va yoqilgan (chiziq, hudud, navbat, sanash, qarovsiz buyum…).
- [ ] alertStream (`/ISAPI/Event/notification/alertStream`) ochiqmi, HTTP host/notification sozlamasi.
- [ ] Termal kameralar bormi (yong'in/tutun/harorat) va qayerda.
- [ ] LAN ichida ulagich uchun server (Linux, Python 3.11+, doimiy ishlaydi, zaxira nusxa).

## 8. Seed / demo ma'lumotlari

Bulut (Railway) va demo rejimida — **sintetik** ma'lumot. Kameralar ulanganda haqiqiy voqealar ularni almashtiradi.

- ~193 kamera: 180 ta auditoriyada + yo'laklar va xizmat zonalari (Qabul, Kassa, Oshxona, serverxona, kirish).
- Holat: ~93% onlayn, ~4% oflayn, ~2% bloklangan, 1–2 tasida soat farqi.
- 30 kunlik voqealar tarixi. FACE/ANPR o'chiq.
- 5 ta demo «hikoya»:
  1. C-binodagi ikki auditoriya 2 hafta davomida jadvalda dars bo'lsa ham deyarli bo'sh.
  2. Qabulda har dushanba 10:00–12:00 navbat 25+ kishi.
  3. Serverxona yonida tungi kirishlar — ikkitasi «noto'g'ri signal» deb belgilangan, bittasidan ariza ochilgan.
  4. Bitta kamera 3 kundan beri oflayn, ariza ochiq va muddati o'tgan.
  5. Oshxonada tushlik paytida ~120% sig'im.

## 9. Sozlamalar (muhit o'zgaruvchilari)

| O'zgaruvchi | Standart | Ma'nosi |
|---|---|---|
| `ISFT_CORE_CAM_POLL` | `60` | So'rov oralig'i, s |
| `ISFT_CORE_CAM_OFFLINE_FAILS` | `3` | Ketma-ket xato soni → oflayn / ariza |
| `ISFT_CORE_WORK_HOURS` | `07:30-20:00` | Ish vaqti; tashqarisi va yakshanba — «tun» |
| `ISFT_CORE_CAM_OCC_PATH` | bo'sh | Hudud bo'yicha sanash endpointi (modelga bog'liq), masalan `/ISAPI/Intelligent/channels/{ch}/regionPeopleCounting` |
| `ISFT_CORE_CAM_QUEUE_PATH` | `/ISAPI/Intelligent/channels/{ch}/queueManagement/status` | Navbat holati endpointi |
| `ISFT_CORE_CAM_DEDUP_SEC` | `300` | Takrorlarni birlashtirish oynasi, s |
| `ISFT_CORE_TZ` | `Asia/Tashkent` | Voqealar vaqt zonasi (server vaqti) |
| `ISFT_CORE_FEATURE_FACE` | `0` | Yuz aniqlash (O'RQ-547 — rozilik va huquqiy asossiz yoqilmaydi) |
| `ISFT_CORE_FEATURE_ANPR` | `0` | Davlat raqami aniqlash (faqat xodimlar avtomobillari) |
| `ISFT_CORE_SECRET_KEY` / `data/secrets/master.key` | — | Kamera parollarini shifrlash kaliti |

Emulyator (`tools/fake_hikvision.py`):

| O'zgaruvchi | Standart | Ma'nosi |
|---|---|---|
| `FAKE_HIK_USER` / `FAKE_HIK_PASS` | `jarvis` / `Test-Pass-123` | Digest login |
| `FAKE_HIK_MODEL` | `DS-2CD2346G2-ISU/SL` | Model; `/ISAPI/Event/triggers` ro'yxati model oilasiga bog'liq (`iDS-2CD7…` DeepinView, `DS-2TD…` termal, `DS-2CD2346G2`/`G2-I` AcuSense, qolgani oddiy) |
| `FAKE_HIK_SKEW` | `0` | Soat farqi, s |
| `FAKE_HIK_COUNTING` | `1` | Odam sanash bormi (0 → 404) |
| `FAKE_HIK_FW_DATE` | `build 230815` | Proshivka sanasi |
| `FAKE_HIK_EVENT_SEC` | `2` | alertStream voqealari oralig'i, s |
| `FAKE_HIK_STREAM_LIMIT` | `0` | N ta XML qismdan keyin oqim tugaydi (JPEG hisoblanmaydi); 0 — cheksiz |
| `FAKE_HIK_EVENTS` | bo'sh | Vergul bilan ro'yxat; berilsa aylanish aynan shu. Sintaksis: `tur[:holat][+jpeg][=qiymat]`, masalan `videoloss:inactive,fielddetection+jpeg,TMA=80.5,personQueueDetection=30,regionPeopleCounting=45` |
| `FAKE_HIK_THERMAL` | `0` | 1 — standart aylanishga `fireDetection`, `smokeDetection`, `TMA` qo'shiladi |
| `FAKE_HIK_QUEUE` | `1` | `queueManagement/status` bormi (0 → 404) |
| `FAKE_HIK_QUEUE_LEN` | bo'sh | Navbat uzunligini qat'iy belgilash; bo'sh — vaqtga qarab (dushanba 10–12 → 25+, 12–14 → 8–18) |

Standart alertStream aylanishi: avval eski 7 ta (`videoloss:inactive`, `linedetection`, `videoloss:inactive`, `fielddetection+jpeg`,
`VMD`, `shelteralarm`, `videoloss:inactive`), keyin `regionEntrance`, `regionExiting`, `loitering`, `peopleGathering`, `running`,
`unattendedBaggage`, `attendedBaggage`, `objectRemoval`, `defocus`, `scenechangedetection`, `personQueueDetection`, `regionPeopleCounting`
(oralarida yurak urishi).

## 10. Emulyator bilan sinash

```bash
.venv/bin/python -m uvicorn tools.fake_hikvision:app --host 127.0.0.1 --port 18090   # login: jarvis / Test-Pass-123
.venv/bin/python tests/test_hikvision.py                                             # jonli bazaga tegmaydi (18090/18091 portlar)
FAKE_HIK_MODEL=DS-2TD2617-10/QA FAKE_HIK_THERMAL=1 .venv/bin/python -m uvicorn tools.fake_hikvision:app --port 18095
```

## 11. Haqiqiy kamerada qayta sinash kerak

Emulyator Hikvision ISAPI hujjatiga **yaqin**, lekin teg nomlari va yo'llar model/proshivkaga qarab farq qiladi:

- [ ] `counting/capabilities` va `counting/search` javob tuzilmasi aniq modelda.
- [ ] Hudud bo'yicha sanash endpointi (`ISFT_CORE_CAM_OCC_PATH`) va `regionPeopleNum` tegi.
- [ ] Navbat endpointi (`ISFT_CORE_CAM_QUEUE_PATH`), `queueLength` / `waitingTime` teglari va birliklari (soniya?).
- [ ] alertStream'dagi aniq `eventType` nomlari: `regionEntrance`/`regionExiting`, `loitering`, `peopleGathering`, `running`,
      `unattendedBaggage`, `attendedBaggage`, `objectRemoval`, `personQueueDetection`, `fireDetection`, `smokeDetection`, `TMA`/`TMPA`,
      olomon zichligi voqeasi nomi.
- [ ] Termal voqeada harorat tegi (`maxTemperature`) va u qaysi blok ichida kelishi.
- [ ] `/ISAPI/Event/triggers` haqiqatan yoqilgan/litsenziyalangan voqealarni ko'rsatadimi (imkoniyatlar uchun
      `/ISAPI/Event/capabilities` ham kerak bo'lishi mumkin).
- [ ] alertStream'da JPEG qismlar qaysi voqealarda keladi va parser ularni to'liq tashlaydimi.
- [ ] Yurak urishi oralig'i (`videoloss inactive`, ~10 s) va 10 daqiqalik oflayn chegarasi to'g'riligi.
- [ ] Kamera soati vs server vaqti: NTP bilan farq < 60 s.
- [ ] NVR orqali ulanganda kanal raqamlari (`channelID` / `dynChannelID`).
- [ ] HikCentral Professional OpenAPI ulagichi — hali yozilmagan (institutda HikCentral borligi aniqlangach).

## 12. Xavfsizlik ro'yxati

- [ ] `.venv/bin/pip install cryptography` — parollar shifrlanadi (aks holda bazadan ajratilgan 0600 fayl, lekin shifrlanmagan).
- [ ] `data/secrets/` zaxira nusxalarga bazadan alohida, cheklangan kirish bilan.
- [ ] Kameralar proshivkasi 2021-09 dan yangi (CVE-2021-36260); Hik-Connect bulut o'chiq; internetga port ochilmagan.
- [ ] Kamera akkaunti — faqat o'qish uchun «Operator», admin emas.
- [ ] Yuz aniqlash va ANPR o'chiq (`ISFT_CORE_FEATURE_FACE=0`, `ISFT_CORE_FEATURE_ANPR=0`); yoqish — faqat yurist xulosasi va O'RQ-547
      bo'yicha yozma rozilik bilan.
- [ ] Rasm/kadr diskka yozilmasligi tekshirilgan (testda `*.jpg` yo'qligi).
