# AI Hikvision kameralar — modul qo'llanmasi (v0.2, 2026-11-09)

> Hamma narsa **metama'lumot** asosida: vaqt, kamera, voqea turi, son, holat. Video, kadr, yuz tasviri **olinmaydi va saqlanmaydi**.
> Yagona istisno — **Kirish nazorati (Face ID)**, 13-bo'lim: faqat bino kirishlari, faqat yozma roziligi bor shaxslar, kadr ≤ 7 kun.

## 1. Tamoyillar

- **Privacy-by-design.** Bazaga faqat voqea metama'lumoti yoziladi (vaqt, kamera, tur, son, holat). alertStream'dagi JPEG qismlar
  xotirada o'qiladi-yu, diskka yozilmasdan tashlab yuboriladi (`AlertStreamParser.dropped_bytes`).
- **Shaxs bog'lanmaydi.** Kamera voqeasi hech qaysi talaba yoki xodim ismiga bog'lanmaydi. Hisobotlar faqat xona / bino / qavat
  kesimida va jamlangan holda chiqadi.
- **Biometrika — faqat rozilik bilan.** Yuz aniqlash O'RQ-547 «Shaxsga doir ma'lumotlar to'g'risida» qonuniga ko'ra alohida yozma
  rozilik va huquqiy asos talab qiladi. Kod `ISFT_CORE_FEATURE_FACE` bayrog'i ortida (demo uchun `1`, tasvirlar sintetik — 13-bo'lim);
  ANPR (davlat raqami) — `ISFT_CORE_FEATURE_ANPR=0`, faqat xodimlar avtomobillari ro'yxati uchun. Bayroq o'chiq bo'lsa, bu voqealar
  umuman qayta ishlanmaydi. Haqiqiy kameralarda yoqishdan oldin — yurist xulosasi va yozma rozilik shakli (13.6).
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
| `ISFT_CORE_FEATURE_FACE` | `1` (demo) | Kirish nazorati (Face ID): faqat kirish kameralari va yozma rozilik reyestri (13-bo'lim). Haqiqiy tizimda yurist xulosasigacha `0` |
| `ISFT_CORE_FACE_MATCH_MIN` | `0.75` | O'xshashlik chegarasi; pastrog'i — «past ishonch» (tasdiqlanmagan, hisobotga kirmaydi) |
| `ISFT_CORE_FACE_KEEP_DAYS` | `7` | Kirish kadri (fon rasmi) saqlanish muddati, kun (`data/face_snaps/`, server startida tozalanadi) |
| `ISFT_CORE_FACE_EVENTS_DAYS` | `90` | Kirish voqeasi metama'lumoti saqlanish muddati, kun |
| `ISFT_CORE_FACE_EXIT_CAMS` | bo'sh | Chiqishga qaragan kameralar id'lari (vergul bilan); qolganlari — kirish |
| `ISFT_CORE_STAFF_START` | `09:00` | Xodimlar ish boshlanishi (kechikish hisobi) |
| `ISFT_CORE_FACE_LATE_GRACE_MIN` | `0` | O'qituvchi/talaba kechikishi uchun imtiyoz, daqiqa |
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
| `FAKE_HIK_EVENTS=alarmResult=FPID:0.93` | — | Yuz voqeasi (JSON qism, DeepinView `alarmResult`); FPID bo'sh — notanish yuz. FDLib endpointlari xotirada (13-bo'lim) |

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
- [ ] ANPR o'chiq (`ISFT_CORE_FEATURE_ANPR=0`). Yuz (Face ID) — demo'da yoqilgan (sintetik); haqiqiy kameralarda yoqish — faqat yurist
      xulosasi va O'RQ-547 bo'yicha yozma rozilik bilan (13.6).
- [ ] Rasm/kadr diskka yozilmasligi tekshirilgan (testda `*.jpg` yo'qligi). Istisno: Face ID kirish kadri — `data/face_snaps/`, ≤ 7 kun.

## 13. Kirish nazorati (Face ID) — `app/facecam.py`

Rektor topshirig'i: bino kirishlaridagi kameralar kim kirgani/chiqqanini ko'rsatsin — talaba (ism, guruh), o'qituvchi (ism, kafedra),
xodim (ism, bo'lim) yoki notanish — va qisqa AI hisobot. **Demo'da tasvirlar sintetik** (`app/facecam_render.py`, PIL bilan chiziladi,
haqiqiy surat ishlatilmaydi), voqealar `app/seed_facecam.py` (14 kun, dars jadvali asosida).

### 13.1. Haqiqiy kameralar bilan qanday ishlaydi (serverda ML model yo'q)

```
 Yozma rozilik (kadrlar / Registrator)  ISFT Core                          Hikvision DeepinView (kirish)
 ─────────────────────────────────      ─────────────────────────────      ─────────────────────────────────
 RZ-2026/1234 + yuz rasmi  ───────────► face_persons: FPID=FP7C1A…  ─────► FDLib (yuz kutubxonasi): FPID + rasm
                                        (ism faqat bazada)  face_sync        (kamerada ism YO'Q)
                                                                              │ kamera yuzni O'ZI solishtiradi
 Kameralar → «Kirish (Face ID)» ◄────── ingest(): FPID → shaxs, rozilik? ◄── alertStream: alarmResult (JSON):
   kadr + ramka + yorliq                 o'xshashlik ≥ 75%? → tanildi        FPID, similarity, faceRect (0..1), bkgUrl
```

1. **Kutubxona sinxroni** (`HikClient.fdlib_*`, faqat `mode=isapi` kameralar uchun, «Kutubxonani kameralarga sinxronlash» tugmasi):
   - `GET/POST /ISAPI/Intelligent/FDLib?format=json` — `ISFT_Kirish` kutubxonasi (FDID);
   - `POST /ISAPI/Intelligent/FDLib/FaceDataRecord?format=json` — multipart: `FaceDataRecord` (JSON: `faceLibType=blackFD`, `FDID`, `FPID`,
     `name`=FPID) + `img` (JPEG, `data/face_enroll/{FPID}.jpg` — rozilik olinganda suratga olinadi);
   - `PUT /ISAPI/Intelligent/FDLib/FDSearch/Delete?format=json&FDID=…&faceLibType=blackFD` — rozilik qaytarib olinganda.
   Navbat — `face_sync` jadvali (kamera oflayn bo'lsa, keyin yuboriladi).
2. **Voqea**: kamera `alarmResult` (JSON qism) yuboradi → `AlertStreamParser` (XML va JSON qismlar, JPEG tashlanadi) → `parse_json_alert`
   (har bir yuz — alohida voqea; eng o'xshash nomzodning `reserve_field.FPID`, `similarity`, `faceRect`, `bkgUrl`) →
   `normalize(face=True)` → `kind="yuz"` → `camsec.process_event` → `facecam.ingest`. Eski proshivkalardagi XML (`faceContrast`, `FPID`,
   `similarity` 0..100, `faceRect` 0..1000) ham o'qiladi.
3. **Qaror (ingest)**: faqat `zone='kirish'` kameralar (bino ichida shaxs kuzatilmaydi). FPID bazada va rozilik faol → o'xshashlik ≥
   `ISFT_CORE_FACE_MATCH_MIN` bo'lsa «tanildi», past bo'lsa «past ishonch» (tasdiqlanmagan, hisobotlarga kirmaydi); FPID yo'q yoki
   rozilik qaytarilgan → «notanish» (shaxs va FPID saqlanmaydi). Bir kameradan 60 s ichidagi takroriy moslik yozilmaydi.
4. **Rasm**: `bkgUrl` faqat shu kameraning o'z manzilidan olinadi (SSRF himoyasi), `data/face_snaps/{kadr}.jpg` ga ≤ `KEEP_DAYS` kun.
   Ramka va yorliq **har safar ko'ruvchining ko'lamiga qarab** chiziladi (LRU kesh); ko'lamdan tashqari yuz — piksel.
5. **Demo** (`source='sintetik'`): fon rasmi saqlanmaydi — kadr `seed` va voqea parametrlaridan (ramka, `look`) qayta chiziladi.

### 13.2. Rozilik modeli (ZRU-547)

- `face_persons(kind, ref_id, name, sub, faculty_id, fpid UNIQUE, consent, consent_doc, consent_at, revoked_at, avatar_seed)` —
  eski `face_consent` jadvalining umumlashtirilgani (talaba / o'qituvchi / xodim). FPID — tasodifiy (`FP` + 10 hex), ism emas.
- Rozilik berish/qaytarish: rektor va xo'jalik (hammasi), kadrlar bo'limi (o'qituvchi, xodim). Qaytarib olinsa: FPID o'chiriladi,
  kameradan o'chirish navbatga qo'yiladi, o'tgan voqealar **shaxssizlantiriladi** (`person_id=NULL`, holat «rozilik yo'q»).
- Rozilik bermagan shaxs kamerada «Aniqlanmadi (rozilik yo'q)» (demo) — haqiqiy kamera uni kutubxonada topmaydi va «notanish» deydi.
- Demo ro'yxati: ~60 talaba, ~25 o'qituvchi (kafedra mudirlari emas), ~15 xodim (bo'lim boshliqlari emas); ~85% rozilik bergan.
  Haqiqiy rahbarlar (foydalanuvchilar, kafedra mudirlari, `static/brand/people/index.json`) ro'yxatga olinmaydi va
  `static/brand/people/` rasmlari ishlatilmaydi.

### 13.3. Kim nimani ko'radi

| Lavozim | Ko'lam |
|---|---|
| Rektor, Xo'jalik va texnik bo'lim | Hamma: talaba, o'qituvchi, xodim, notanish, tungi kirishlar; rozilik reyestri |
| Kadrlar bo'limi | Faqat o'qituvchi va xodimlar (punktuallik); ularning roziligini boshqaradi |
| Fakultet tyutori | Faqat o'z fakulteti talabalari (institutda dekan lavozimi yo'q) |
| AT bo'limi boshlig'i | Kamera va yuz kutubxonasi holati — faqat sonlar; kadr va ism yo'q |
| Kuzatuv kengashi | Jamlangan ko'rsatkichlar va hisobot (ism, rasmsiz); menyuda «Kameralar» yashirin |
| Boshqalar | 403 (audit jurnaliga yoziladi) |

Har bir kadr/rasm (30 daqiqada bir yozuv), shaxs tarixi, rozilik o'zgarishi va rad etilgan urinish — `audit_log`, `resource='face'`.
Telegram kanalida — faqat jamlangan ko'rsatkichlar. Rasm javobi `Cache-Control: no-store` (bir kompyuterda boshqa lavozim).

### 13.4. API

| Endpoint | Ma'nosi |
|---|---|
| `GET /api/face/summary?date=` | KPI (ko'lam bo'yicha), kameralar, kutubxona holati, 14 kunlik qator |
| `GET /api/face/frames?date=&camera=&kind=&q=&offset=&limit=` | Kadrlar (yuzlar, yorliqlar ko'lam bo'yicha) |
| `GET /api/face/frames/{id}` | Kadr tafsiloti |
| `GET /api/face/events/{id}/image?w=` | Izohlangan JPEG (1280×720 yoki `w` kenglik) |
| `GET /api/face/persons/{id}/timeline?days=14` | Shaxsning 14 kunlik kirish/chiqishlari, birinchi para, kechikish |
| `GET /api/face/persons?q=&kind=` · `POST /api/face/persons` · `POST /api/face/persons/{id}/consent` | Rozilik reyestri |
| `GET /api/face/report?date=&scope=` | `{facts, narrative, narrative_mode, verify}` — faktlar koddan; matn mahalliy LLM (bo'lsa) yoki shablon |
| `POST /api/face/report/docx` | Word hisobot (blank, QR bilan tekshiriladi, Hujjatlar markazida saqlanadi) |
| `POST /api/face/sync` | FDLib navbatini haqiqiy kameralarga yuborish |

AI suhbat: «Bugun qaysi o'qituvchilar kechikdi?», «Bugun nechta talaba kirdi?» — `ai.TOOLS["facecam"]` (xuddi shu faktlar, ko'lam bo'yicha).

### 13.5. Hisobot qoidalari

- O'qituvchi kechikdi — shu kuni birinchi tasdiqlangan kirishi dars jadvalidagi **birinchi parasi** boshlanishidan keyin
  (`ISFT_CORE_FACE_LATE_GRACE_MIN`, standart 0). Talaba — guruhining birinchi parasi. Xodim — `ISFT_CORE_STAFF_START` (09:00).
- «Past ishonch» va «notanish» kechikish/kelganlar hisobiga kirmaydi. Taqqoslash — oldingi 7 ish kuni (yakshanbasiz) o'rtachasi.
- Matndagi har bir raqam faktlar bilan solishtiriladi (`verify`); mos kelmasa — AI matni o'rniga shablon.

### 13.6. AT bo'limidan nima so'rash kerak (Face ID)

- [ ] Kirish kameralari modeli **yuz kutubxonasini (Face Picture Library / FDLib) va kamerada solishtirishni** qo'llaydimi
      (DeepinView `iDS-2CD71xxG0-IZS` / `…-IZHS(Y)` yuz algoritmi bilan; AcuSense `DS-2CD2xxx` odatda faqat «face capture», solishtirmaydi).
      Muqobil: NVR (DeepinMind `iDS-96xxNXI`) yoki HikCentral Professional + Face Recognition Server.
- [ ] Proshivka versiyasi va yoqilgan algoritm (bitta DeepinView kamerada «face capture/comparison» va boshqa algoritmlar almashtiriladi).
- [ ] ISAPI foydalanuvchisi: alertStream o'qish + FDLib yozish huquqi (alohida «Operator» akkaunt; admin emas).
- [ ] alertStream'da `alarmResult` JSON keladimi yoki XML (`faceContrast`) — namuna yozib olinsin; `bkgUrl` qaysi yo'lda.
- [ ] Kamera o'rnatilishi: yuz ≥ 60–80 piksel, yorug'lik (kontr-yorug'lik yo'q), kirish va chiqish uchun alohida kamera (`ISFT_CORE_FACE_EXIT_CAMS`).
- [ ] Kamera soati NTP bilan (voqea vaqti baribir server vaqti).
- [ ] Yuridik: yozma rozilik shakli (ZRU-547), maqsad (kirish nazorati), saqlash muddatlari, rozilikni qaytarib olish tartibi,
      shaxsga doir ma'lumotlar bazasi ro'yxatdan o'tkazilishi.

### 13.7. Sinash

```bash
.venv/bin/python tests/test_facecam.py      # jonli server kerak; emulyator 18094-portda; mantiq — baza nusxasida
FAKE_HIK_MODEL=iDS-2CD7146G0-IZS FAKE_HIK_EVENTS="alarmResult=FP0123456789:0.93,alarmResult=:0" \
  .venv/bin/python -m uvicorn tools.fake_hikvision:app --port 18094
```
