# «Studiya» — dars ishlab chiqarish oqimi

**Kod:** `app/studio.py` (oqim, API, ishchi API), `app/studio_yt.py` (YouTube yuklovchisi), `static/studio.js`, `static/studio.css`
**Paket ilgaklari:** `app/paket.py` — «Studiya ilgaklari» bo'limi (`studio_lesson`, `studio_slides_pdf`, `studio_logo`, `studio_set_video`,
`studio_set_youtube`, `studio_build`)
**Testlar:** `tests/test_studio.py` (A — server orqali, B — jarayon ichida bazaning nusxasida; YouTube HTTP — `httpx.MockTransport`)
**API:** `/api/studio/*` (sessiya), `/api/montaj/*` (montaj ishchisi, `X-Worker-Token`)
**Ruxsat resursi:** `rbac.STUDIO` · **Bo'lim kaliti:** `studio` (standart yoqilgan, `app/modules.py`)
**Montaj ishchisi** (studiya kompyuterida, Python + ffmpeg) — alohida dastur: `tools/montaj/`, `docs/montaj.md`.

## Muammo va yechim

Masofaviy ta'lim bo'limida bugun: 1) o'qituvchi ma'ruzani tayyorlaydi → 2) institut studiyasida syomka → 3) montaj qo'lda →
4) materiallar bo'limga yuboriladi → 5) bo'lim videoni YouTube'ga yuklab, havolani ko'chiradi → 6) Articulate'da xAPI paket yig'adi.

ISFT Core'da hammasi bitta oqim:

| Qadam | Kim | Qayerda |
|---|---|---|
| Ma'ruza matni + taqdimot | O'qituvchi | «Dars tayyorlash» (paket) |
| Syomkaga yozilish (slot) | O'qituvchi (yoki operator/bo'lim) | Studiya → Mening darslarim / Kun rejasi |
| Syomka, xom videoni yuklash, shablon | Studiya operatori | Studiya → Kun rejasi |
| AI montaj | Studiya kompyuteri (`tools/montaj`) | `/api/montaj/*` |
| Ko'rib chiqish: tasdiqlash / qayta montaj | Operator | Studiya → Montaj |
| Video darsga (fayl + subtitr + poster) | Avtomatik | paket ilgagi |
| YouTube'ga «unlisted» yuklash, havola darsga | Avtomatik (sozlangan bo'lsa) | fon oqimi |
| xAPI paket | Avtomatik (matn + taqdimot bo'lsa) | `paket.build_topic` |
| Paketni tasdiqlash | Bo'lim | «Dars tayyorlash» |
| «NEXTID'ga yuklandi» belgisi | Bo'lim | Studiya → Darslar → Tafsilot |

## Bosqichlar (har bir L / A dars)

| # | Kalit | Bosqich | Egasi (harakat qiladi) | SLA (kun, standart) | Qanday aniqlanadi |
|---|---|---|---|---|---|
| 0 | `bosh` | Ma'ruza tayyorlanmoqda | O'qituvchi | 14 (reja sanasidan) | hech narsa yo'q |
| 1 | `maruza` | Ma'ruza tayyor | O'qituvchi | 5 | paketda matn **va** taqdimot bor (`readiness_map`) |
| 2 | `syomka_belgilandi` | Syomka belgilandi | Operator | 1 (syomka **oxiridan**) | faol band (`st_bookings.status='band'`) |
| 3 | `syomka_qilindi` | Syomka qilindi | Operator | 1 | «Syomka qilindi» belgisi yoki montajga yuborilmagan xom video |
| 4 | `montaj` | Montajda (AI) | Operator | 1 | vazifa `navbatda` / `ishlanmoqda` / `operator` |
| 5 | `korib` | Ko'rib chiqishda (operator) | Operator (YouTube navbatida — tizim, xatoda — bo'lim) | 2 | vazifa `tayyor`; yoki tasdiqlangan, YouTube hali tugamagan |
| 6 | `youtube` | YouTube'da | Bo'lim (matn/taqdimot yetishmasa — o'qituvchi) | 3 | darsda video bor (YouTube havola yoki fayl — YouTube ulanmagan bo'lsa tasdiqlangan fayl) |
| 7 | `paket` | Paket tayyor | Bo'lim | 3 | oxirgi paket `tayyor` (tasdiq kutilmoqda) |
| 8 | `tasdiq` | Tasdiqlandi | Bo'lim | 3 | oxirgi paket `tasdiqlandi` |
| 9 | `nextid` | NEXTID'ga yuklandi | — | — | `st_marks` (shu tasdiqlangan paketga bog'langan) |

Qoida (`studio.derive`, sof funksiya, testlangan):
1. **Faol studiya tsikli** ustun: faol band → montajga yuborilmagan xom video → montaj → ko'rik → (tasdiqlangan, YouTube yuklanmoqda) →
   «syomka qilindi» (video hali yuklanmagan). Qayta syomka (eski paket bor bo'lsa ham) shu yerda ko'rinadi.
2. Aks holda — mavjud ma'lumotdan: NEXTID > tasdiq > paket > video bor > ma'ruza tayyor > boshlanmagan.
3. Muddat: bosqichga kirgan vaqt + SLA (`syomka_belgilandi` — syomka oxiri + SLA). Ma'lumotdan hisoblangan bosqichlarda kirish vaqti
   reja sanasidan oldin bo'lmaydi.
4. **Qizil** faqat *kuzatiladigan* darslarda: kurs «ishlab chiqarish rejasi»da (`st_plan`) yoki darsda studiya yozuvi bor.
   Shuning uchun yuzlab eski darslar birdaniga qizil bo'lib ketmaydi.

SLA kunlari — Studiya → Sozlamalar (faqat bo'lim boshlig'i), `st_meta.sla`.
Tarix — `st_log` (studiya amallari) + `pk_log` (paket) birgalikda, Darslar → Tafsilot.

## Lavozimlar

| Lavozim | Ko'radi / qiladi |
|---|---|
| `montaj_operator` (yangi, demo: «Masofaviy ta'lim bo'limi — studiya operatori: Xolmatov Sardor Baxtiyor o'g'li», sinov paroli) | Kun rejasi, hamma bandlar, xom video, montaj navbati, ko'rik/tasdiq/qayta montaj, xonalar, Holat |
| `masofaviy` (boshliq) | Hammasi + ishlab chiqarish rejasi, SLA, YouTube sozlamasi, NEXTID belgisi |
| `masofaviy_xodim` | Boshliq kabi, sozlamalarsiz |
| `rektor`, `prorektor_oquv` | Faqat Holat (jamlangan) va qizil belgilar; panelda «Dars ishlab chiqarish: N ta muddati o'tgan» KPI. Video/fayl yo'q |
| `oqituvchi` | «Mening darslarim»: o'z darslari bosqichi, syomkaga yozilish, o'z bandini ko'chirish/bekor qilish |
| `it_head` | Faqat Sozlamalar → YouTube (OAuth sirlari) |
| boshqalar (kafedra, …) | 403 (audit jurnalida) |

«Mening vazifalarim» (`app/pending.py` → `studio.mywork_items`, manba `studio`): syomka eslatmalari — ertaga, bugun va **1 soat
oldin** (yuqori ustuvorlik), o'qituvchi va operatorga; «Montaj tayyor — ko'rib chiqing»; montaj/YouTube xatolari; muddati o'tgan darslar —
faqat bosqich egasiga (5 tadan ko'p bo'lsa — bitta jamlangan qator). Operator bosh sahifasi: 4 ko'rsatkich (`studio.bugun`).

## Studiya bandi

* Xonalar (`st_rooms`): standart bitta «Studiya», 09:00–18:00, slot 90 daqiqa, Du–Sh. Slot uzunligi: 30/45/60/90/120.
* Band faqat jadval slotiga (xona ochilish vaqtidan boshlab slot qadami), o'tgan vaqtga emas, 90 kundan uzoqqa emas.
* Ziddiyat — **409**: xona band; o'qituvchining o'sha vaqtda boshqa syomkasi bor; darsning allaqachon faol bandi bor.
* Ko'chirish va bekor qilish — sabab majburiy (≥ 3 belgi), tarixda. O'qituvchi faqat o'z kursi bandini o'zgartiradi.
* «Syomka qilindi» / «Kelmadi» — operator (syomka vaqtidan 12 soatdan ko'p oldin emas). Xom video yuklansa — faol band avtomatik «qilindi».

## Montaj ishchisi API (kontrakt — `tools/montaj` bilan AYNAN bir xil)

Barcha so'rovlar: `X-Worker-Token: <ISFT_CORE_WORKER_TOKEN>`. Taqqoslash — doimiy vaqtda (`hmac.compare_digest`).
Token serverda sozlanmagan — **503** `{"detail": "worker o'chiq"}`; noto'g'ri/yo'q — **401** (audit jurnalida). Sessiya cookie o'rnini bosmaydi.

### `POST /api/montaj/jobs/claim`
Tana yo'q. Javob **204** (navbat bo'sh) yoki **200**:
```json
{"job_id": 17, "template": "maruza_slayd", "lease": "9f2c4a1b7e30d685",
 "lesson": {"course_id": 94, "no": 3, "code": "L3", "kind": "maruza", "title": "Bozor muvozanati",
            "subject": "Mikroiqtisodiyot", "teacher": "Ism Familiya", "plan": ["1. …", "2. …"]},
 "raw_url": "https://core.isft.uz/api/montaj/files/17.raw.1763030000.<lease>.<imzo>",
 "raw_ext": ".mp4", "raw_name": "L3_syomka.MP4",                      // xom video turi (baytlardan aniqlangan: .mp4/.mov/.mkv/.webm) va asl nomi
 "slides_url": "https://…/api/montaj/files/17.slides.….<imzo>",   // darsning PDF taqdimoti; yo'q bo'lsa null
 "logo_url": "https://…/api/montaj/files/17.logo.….<imzo>",       // yo'q bo'lsa null
 "note": "Kirishdagi sukutni qoldiring"}                          // FAQAT «Qayta montaj» izohi bo'lsa
```
* `raw_ext` — xom video kengaytmasi (serverda baytlardan aniqlangan tur). Ishchi uni ishlatadi; imzolangan havola nomi kengaytma EMAS.
* `lesson.no` — paket dars kaliti: L*n* → *n*, A*n* → 1000+*n* (`code` — odam o'qiydigan kod).
* `template`: `maruza_slayd` («Ma'ruza: o'qituvchi + slayd»), `faqat_oqituvchi` («Faqat o'qituvchi»), `ekran` («Ekran yozuvi + o'qituvchi burchakda»).
* `lease` — shu claim'ning identifikatori (har claim'da yangi). Ishchi uni `progress` / `result` / `fail` ga **`X-Worker-Lease`** sarlavhasi
  bilan qaytaradi; joriy lease'ga mos kelmasa (lease muddati o'tib vazifa boshqa ishchiga berilgan / navbatga qaytgan) — **409** (ishchi ishni
  bekor qiladi). Sarlavhasiz so'rov (eski ishchi dasturi) qabul qilinadi — orqaga moslik. Imzolangan fayl havolalari ham lease'ni o'z ichiga
  oladi: eskirgan lease havolasi — **409**.
* Dars ma'lumoti (`lesson`, taqdimot, logo) vazifa qulflanishidan **oldin** olinadi: olib bo'lmasa — vazifa «operator kerak» (aniq xato bilan),
  urinish va lease sarflanmaydi, navbatdagi keyingi vazifa beriladi.
* Claim vazifani qulflaydi: **lease 2 soat**. Har `progress` lease'ni yana 2 soatga uzaytiradi (heartbeat) — uzun montajda kamida har
  ~30 daqiqada progress yuboring. Lease muddati o'tsa (ishchi o'chdi) — vazifa navbatga qaytadi (urinish sanaladi).
  `result` yuklanayotganda lease boshida va har 64 MB da uzaytiriladi; natijasi yuklanayotgan vazifa navbatga qaytarilmaydi
  (`/fail` ham — 409).
* Urinish claim'da sanaladi; 3 urinishdan keyin vazifa «operator kerak» holatiga o'tadi.
* Absolyut manzillar `ISFT_CORE_PUBLIC_URL` (bo'lsa) yoki so'rov manzilidan quriladi.

### `GET /api/montaj/files/{token}` (imzolangan havola, sarlavhasiz ham ishlaydi)
* HMAC-SHA256 imzo (kalit — `st_meta.url_key`, bazada). Lease'li havola **lease amal qilguncha** ishlaydi (progress uzaytiradi; lease muddati
  o'tgan — **410**), absolyut yuqori chegara — **48 soat**; lease'siz (eski) havola — 2 soat. Vazifa `ishlanmoqda` bo'lmasa — **410**;
  imzo/muddat noto'g'ri — **403**.
* **HTTP Range**: `bytes=a-b`, `bytes=a-`, `bytes=-n` → **206** + `Content-Range`; qondirib bo'lmaydigan — **416**. Fayl xotiraga o'qilmaydi.
* Content-Type: xom video — `video/mp4|quicktime|x-matroska|webm`, slaydlar — `application/pdf`, logo — `image/png|jpeg`.

### `POST /api/montaj/jobs/{id}/progress`
`{"stage": "kesish", "pct": 40, "message": "Sukutlar olib tashlanmoqda"}` → `{"ok": true, "lease_until": "…"}`.
`stage` ≤ 40 belgi, `pct` 0–100 ga keltiriladi, `message` ≤ 300. Vazifa `ishlanmoqda` bo'lmasa — **409**.

### `POST /api/montaj/jobs/{id}/result` — `multipart/form-data` (oqim bilan diskka)
| Maydon | Majburiy | Tur (baytlardan tekshiriladi) | Chegara |
|---|---|---|---|
| `video` | ha | MP4 (`ftyp`) | `ISFT_CORE_RESULT_MAX_GB` (standart = `ISFT_CORE_RAW_MAX_GB`, 8 GB) |
| `captions` | yo'q | WebVTT (yaroqsiz bo'lsa — ogohlantirish bilan tashlanadi) | 2 MB |
| `thumbnail` | ha | JPEG | 10 MB |
| `report` | ha | JSON (quyida) | 2 MB |

```json
{"duration_in": 3725.4, "duration_out": 2950.0,
 "cuts": [{"start": 0, "end": 42.5, "reason": "boshlanishdagi sukut"}],
 "chapters": [{"start": 0, "title": "Kirish"}, {"start": 300, "title": "Bozor muvozanati"}],
 "slide_changes": [{"t": 12.5, "slide": 1}],
 "warnings": ["Mikrofon 12:40 da shovqinli"]}
```
* Vaqtlar soniyada (0 … 86400). `cuts` — **asl** yozuv vaqti, `chapters` va `slide_changes` — **natija** vaqti (YouTube bo'limlari shundan).
* `slide_changes[].slide` — PDF sahifa raqami yoki `null` (slaydsiz bo'lak). Ixtiyoriy `timings` (`{bosqich: soniya}`) saqlanadi; boshqa
  noma'lum kalitlar tashlanadi. `cuts[].reason` kodlari (`silence`, `noise`, `filler`, `retake`, `retake_cue`, `tiny` — `docs/montaj.md`)
  ko'rik oynasida o'zbekcha: Sukut, Shovqin/pauza, «Ee/hmm», Qayta olingan, «Qaytadan» buyrug'i, Qisqa bo'lak.
* Noma'lum yoki takroriy maydon — 400; majburiy maydon yo'q — 400; tur noto'g'ri — 415; chegaradan oshdi — 413 (oqimda darhol).
* Muvaffaqiyat: **200** `{"ok": true, "status": "tayyor", "warnings": [...]}`; vazifa `ishlanmoqda` bo'lmasa — 409.
* Har so'rov o'z vaqtinchalik katalogida (`jobs/<id>/.incoming/<uuid>`). Shu vazifaga natija hali yuklanayotgan bo'lsa, ikkinchi so'rov —
  **409** «… hozir yuklanmoqda» (ishchi kutib qayta yuboradi). Kutilmagan ichki xato — **500** aniq o'zbekcha matn bilan.

### `POST /api/montaj/jobs/{id}/fail`
`{"error": "ffmpeg: …"}` → `{"ok": true, "status": "navbatda" | "operator", "attempts": n, "retry": bool}`.
3-urinishgacha — navbatga (keyingi claim `60 s × urinish` dan keyin), keyin — «operator kerak» (operator «Qayta urinish» bosadi).
Istisno: `{"error": "Worker to'xtatildi yoki ish bekor qilindi"}` (ishchi SIGTERM / to'xtatildi) — vazifa darhol navbatga qaytadi, urinish hisoblanmaydi.

`result` idempotent: ishchi 5xx/uzilishda 4 martagacha qayta yuboradi — vazifa «tayyor» (hali ko'rib chiqilmagan) bo'lsa ham qabul qilinadi,
fayllar almashtiriladi (200). `pct` = 100 ni server natija qabul qilinganda qo'yadi. Hajm: ≈ 37 MB/daqiqa (90 daqiqa ≈ 3,3 GB) — standart
chegara 8 GB, diskka oqim bilan.

## Operator ko'rigi

Montaj → «Ko'rib chiqish»: natija videosi (Range bilan, subtitr bilan), poster, bo'limlar (bosilsa video o'sha joyga o'tadi), kesishlar,
ogohlantirishlar, davomiylik. Ikki amal:
* **Tasdiqlash** → `paket.studio_set_video`: video darsning video FAYLI (`pk_assets.src='studio'`, qattiq havola — nusxasiz), subtitr (o'zbekcha
  WebVTT), poster (thumbnail → JPEG), `video_source = file`. YouTube sozlangan bo'lsa — `st_yt` navbatiga; aks holda — darhol avtomatik paket.
  Holat o'tishi atomar (`UPDATE … WHERE status='tayyor'`) va har qanday yon ta'sirdan oldin: parallel ikkinchi tasdiq — 409 (takroriy video /
  YouTube qatori yo'q); video darsga qo'yilmasa — vazifa yana «tayyor» (xato matni bilan; kutilmagan xato — 500).
  `studio_set_video` tranzaksiyaviy: fayllar avval paket omborida vaqtinchalik nom bilan (qattiq havola, boshqa disk — nusxa), keyin bitta
  tranzaksiyada qatorlar yakuniy yo'l bilan; eski video/subtitr/poster faqat yangilari to'liq ro'yxatga olingach o'chiriladi. Xatoda — rollback,
  yangi fayllar o'chiriladi, darsning oldingi videosi joyida.
* **Qayta urinish** (`retry`) — atomar (`… WHERE status='operator'`): parallel «bekor qilish» yutgan bo'lsa — 409.
* **Qayta montaj** (izoh majburiy, shablonni almashtirish mumkin) → eski vazifa `qayta`, yangisi navbatda (bitta tranzaksiyada, tekshiruvlardan
  keyin: xom video yo'q yoki montaj bajarilmoqda — 409, eski natija «tayyor» qoladi); ishchi izohni `note` da oladi.

### Disk tozalovi
* Bekor qilingan vazifa natijasi (`jobs/<id>/`) — darhol; «qayta» natija — shu darsning yangiroq montaji tasdiqlangach; eski tasdiqlangan
  natija — yangisi tasdiqlanib, YouTube navbati tugagach.
* Xom video — hech qaysi faol vazifa ishlatmasa va: dars videosi tasdiqlanganiga `ISFT_CORE_RAW_KEEP_DAYS` (standart 14) kun o'tgan bo'lsa
  yoki u yangiroq xom video bilan almashtirilgan (faqat bekor/qayta vazifalarda ishlatilgan) bo'lsa. Bazada `st_raw.deleted=2`, tarixda yozuv.
* Davriy tozalov — `studio.poller` ichida soatiga bir marta (`studio.sweep`). Faol paket fayllariga (pk_assets — tasdiqlangan video qattiq havola)
  bog'langan fayl (bir xil inode yoki havolalar soni > 1) hech qachon o'chirilmaydi.

## YouTube (sozlanmaguncha o'chiq)

`app/studio_yt.py`, faqat `httpx` (yangi bog'liqlik yo'q). Fon oqimi (`studio.poller`, har 30 s, «studio» bo'limi yoqiq bo'lsa):
1. Kunlik chegara (`ISFT_CORE_YT_DAILY`, standart 6) → resumable sessiya (`privacyStatus: unlisted`, toifa 27 «Ta'lim», til uz).
   Sarlavha: `{fan} · {L1}: {mavzu}` (≤ 100 belgi). Tavsif: reja + YouTube bo'limlari (`0:00 Kirish` …; kamida 3 ta, har biri ≥ 10 s bo'lsa) .
   Teglar: fan, ISFT, masofaviy ta'lim, dars kodi, kafedra.
2. Bo'laklab yuklash (`ISFT_CORE_YT_CHUNK_MB`, standart 8, 256 KiB ga karrali); har bo'lakdan keyin offset saqlanadi. Uzilsa —
   `Content-Range: bytes */N` bilan qayerdan davom etishi so'raladi.
3. Holat so'rovi (`videos.list?part=status,processingDetails`) — `processed` bo'lguncha har daqiqa.
4. Tayyor → darsga `https://youtu.be/<id>` (`video_source = youtube`, fayl zaxirada qoladi) → avtomatik paket → shundan keyin `tayyor`.
   Darsga bog'lash yiqilsa — `yuklandi_boglanmadi` (haqiqiy xato matni, `video_id` saqlanadi): qayta urinish (avtomatik, backoff bilan; yoki
   «qayta urinish») faqat havolani bog'laydi, videoni qayta yuklamaydi. Kutilmagan ichki xato yuklangan videoni `xato` bilan yopmaydi.
5. YouTube o'chirilsa (Sozlamalar → «O'chirish» yoki `ISFT_CORE_YT_OFF=1`) — yakunlanmagan navbat qatorlari `bekor`, darslar video FAYL
   bilan davom etadi (avtomatik paket) — «ko'rib chiqishda» osilib qolmaydi.
   YouTube videoni **private** qilib qo'ysa (tasdiqlanmagan ilova) — ogohlantirish, havola darsga qo'yilmaydi (talabalar ko'ra olmaydi).

Xatolar (o'zbekcha matn bilan, «Mening vazifalarim»da bo'limga):
| Holat | Natija |
|---|---|
| 5xx / 429 / tarmoq | qayta urinish, kutish `30·2^n` s (≤ 1 soat), 8 urinishdan keyin — xato |
| 403 `quotaExceeded` va h.k. | «Kvota — keyinroq», ertaga 13:05 (Tinch okeani yarim tuni ≈ Toshkent 12:00–13:00) |
| 401 | token bir marta yangilanadi, so'rov qaytariladi |
| `invalid_grant` | xato: «Refresh token yaroqsiz yoki bekor qilingan» — Sozlamalarda yangisini kiriting |
| boshqa 403 / 4xx | xato (sababi bilan) — operator/bo'lim «qayta urinish» bosadi |
| sessiya 404/410 | yangidan boshlanadi |

**Sirlar:** client id, client secret, refresh token — `app/secret_store` da (bazada emas; `cryptography` o'rnatilsa — Fernet bilan
shifrlangan, aks holda alohida 0600 fayl). Hech qaysi API ularni qaytarmaydi (faqat «saqlangan / yo'q»), audit jurnaliga faqat
o'zgargan maydon **nomi** yoziladi, logga yozilmaydi. Access token — faqat xotirada.

## Avtomatik paket

Dars «YouTube'da» bosqichiga yetganda (yoki YouTube o'chiq bo'lsa — montaj tasdiqlanganda) `paket.studio_build`: ma'ruza matni **va**
taqdimot bo'lsa — `build_topic` (tizim nomidan); natija tarixda («Paket avtomatik tayyorlandi: vN · tasdiq kutilmoqda» yoki nima
yetishmasligi). Bo'lim faqat tasdiqlaydi. Diqqat: video FAYL bilan paket ≤ `ISFT_CORE_PK_PACKAGE_MB` (standart 500 MB) — uzun ma'ruzalar
uchun YouTube'ni ulang.

## Holat paneli

Raqamlar (`board`, `kpi`, operator «Bugun», «Mening vazifalarim» qizil qatorlari) — bitta hisob, 30 s keshlanadi (studiya yozuvlari tozalaydi).
Studiya → Holat (bo'lim, operator, rahbariyat): Jarayonda / Muddati o'tgan / NEXTID'ga yuklandi; bosqichlar bo'yicha sonlar (egasi bilan);
kesim — kurs / kafedra / o'qituvchi (rangli chiziq); muddati o'tgan darslar ro'yxati (kechikish kunlari, egasi, keyingi qadam).
Rahbariyat — o'sha raqamlar, video/fayl havolalarisiz. Bosh panelda (rektor, o'quv prorektori, bo'lim yoqiq bo'lsa):
**«Dars ishlab chiqarish: N ta muddati o'tgan»** (`GET /api/studio/kpi`).

## Ilova API (sessiya)

| Usul | Yo'l | Kim |
|---|---|---|
| GET | `/api/studio/meta` | hamma studiya lavozimlari |
| GET | `/api/studio/board?group=course\|kafedra\|teacher`, `/api/studio/kpi` | bo'lim, operator, rahbariyat |
| GET | `/api/studio/lessons[?course_id=]`, `/api/studio/lessons/{cid}/{lkey}` | bo'lim, operator, o'qituvchi (o'zi) |
| POST | `/api/studio/lessons/{cid}/{lkey}/raw?name=&template=&booking_id=` (tana — fayl baytlari) | bo'lim, operator |
| POST | `/api/studio/lessons/{cid}/{lkey}/jobs` `{template, raw_id?, note?}` | bo'lim, operator |
| POST | `/api/studio/lessons/{cid}/{lkey}/nextid` `{undo?}` | bo'lim |
| GET/POST | `/api/studio/courses?q=`, `/api/studio/plan` `{course_id, on}` | bo'lim (qidiruv — operator ham) |
| GET | `/api/studio/day?date=&room_id=` | bo'lim, operator, o'qituvchi (boshqalar bandi — faqat «band») |
| POST | `/api/studio/bookings` `{course_id, lkey, room_id, start, note}` | bo'lim, operator, o'qituvchi (o'z kursi) |
| POST | `/api/studio/bookings/{id}/move` `{start, reason, room_id?}`, `/cancel` `{reason}` | ″ |
| POST | `/api/studio/bookings/{id}/done` `{status: otdi\|kelmadi, note}` | bo'lim, operator |
| GET | `/api/studio/jobs?status=faol`, `/api/studio/jobs/{id}`, `/api/studio/jobs/{id}/media/{video\|thumb\|captions}` (Range) | bo'lim, operator |
| POST | `/api/studio/jobs/{id}/approve`, `/redo` `{note, template?}`, `/retry`, `/cancel` | bo'lim, operator |
| POST | `/api/studio/youtube/{id}/retry` | bo'lim, operator |
| GET | `/api/studio/settings`; POST `/api/studio/rooms`, `/api/studio/sla` `{sla: {bosqich: kun}}` | xonalar — boshliq, operator; SLA — boshliq |
| GET/POST | `/api/studio/youtube`, `/youtube/clear`, `/youtube/test` | boshliq, AT boshlig'i |

## Sozlash

### Muhit o'zgaruvchilari
| O'zgaruvchi | Standart | Ma'nosi |
|---|---|---|
| `ISFT_CORE_WORKER_TOKEN` | — (ishchi o'chiq, 503) | montaj ishchisi tokeni |
| `ISFT_CORE_RAW_MAX_GB` | 8 | xom video chegarasi |
| `ISFT_CORE_RESULT_MAX_GB` | = RAW | montaj natijasi (video) chegarasi |
| `ISFT_CORE_PUBLIC_URL` | so'rov manzili | ishchiga beriladigan havolalar asosi (proksi ortida: `https://core.isft.uz`) |
| `ISFT_CORE_YT_DAILY` | 6 | bir kunda boshlanadigan YouTube yuklashlari |
| `ISFT_CORE_YT_CHUNK_MB` | 8 | YouTube bo'lagi |
| `ISFT_CORE_YT_PRIVACY` | unlisted | `unlisted` / `private` / `public` |
| `ISFT_CORE_YT_OFF` | — | `1` — sirlar bo'lsa ham YouTube o'chiq (navbatdagi yuklashlar bekor, fayl video bilan) |
| `ISFT_CORE_RAW_KEEP_DAYS` | 14 | dars videosi tasdiqlangandan keyin xom video necha kun saqlanadi |
| `ISFT_CORE_SECRET_KEY` | data/secrets/master.key | secret_store Fernet kaliti (`cryptography` o'rnatilganda) |

### Montaj ishchisi tokeni
1. Tasodifiy token yarating: `python3 -c "import secrets; print(secrets.token_urlsafe(32))"`.
2. Serverda (Railway → Variables): `ISFT_CORE_WORKER_TOKEN=<token>`; proksi ortida bo'lsa `ISFT_CORE_PUBLIC_URL=https://<domen>`. Serverni qayta ishga tushiring.
3. Studiya kompyuterida `tools/montaj` sozlamasiga o'sha token va server manzilini yozing (`docs/montaj.md`).
4. Studiya → Sozlamalar → «Montaj ishchisi: Token sozlangan» ko'rinadi. Tokenni almashtirish — o'zgaruvchini yangilash (eski darhol ishlamaydi).

### YouTube'ni ulash (Google Cloud Console — bir marta, kanal egasi akkaunti bilan)
1. **Loyiha:** https://console.cloud.google.com → yuqoridagi loyiha tanlagich → *New project* → nomi «ISFT Studiya» → *Create*.
2. **API:** *APIs & Services → Library* → «YouTube Data API v3» → *Enable*.
3. **OAuth roziligi:** *APIs & Services → OAuth consent screen* (yangi interfeysda *Google Auth Platform*):
   * *Branding*: ilova nomi «ISFT Studiya», support email, developer email.
   * *Audience*: **External** (kanal Google Workspace tashkilotida bo'lsa — *Internal* ham mumkin). *Test users* ga kanal egasining
     Google akkauntini qo'shing.
   * *Data access / Scopes*: `https://www.googleapis.com/auth/youtube.upload` (ixtiyoriy: `…/auth/youtube.readonly` — «Ulanishni
     tekshirish» kanal nomini ko'rsatishi uchun).
   * **Muhim:** ilova *Testing* holatida qolsa refresh token **7 kunda** eskiradi. *Audience → Publish app* («In production») qiling.
     Tasdiqlanmagan ilovada kirishda «Google hasn't verified this app» ogohlantirishi chiqadi — *Advanced → Go to … (unsafe)* bilan davom etiladi.
4. **Credentials:** *APIs & Services → Credentials → Create credentials → OAuth client ID* → turi **Web application** → *Authorized redirect
   URIs* ga `https://developers.google.com/oauthplayground` qo'shing → *Create*. **Client ID** va **Client secret** ni nusxalang.
5. **Refresh token:** https://developers.google.com/oauthplayground →
   * o'ng yuqoridagi ⚙ → *Use your own OAuth credentials* ✓ → Client ID va secret'ni kiriting; *Access type: Offline*;
   * 1-qadam: *Input your own scopes* ga `https://www.googleapis.com/auth/youtube.upload` (va xohlasangiz `https://www.googleapis.com/auth/youtube.readonly`)
     → *Authorize APIs* → institut KANALI egasi akkaunti bilan kiring (brend akkaunt bo'lsa — kerakli kanalni tanlang) → ruxsat bering;
   * 2-qadam: *Exchange authorization code for tokens* → **Refresh token** ni nusxalang.
6. **ISFT Core:** Studiya → Sozlamalar → «YouTube kanali» (bo'lim boshlig'i yoki AT boshlig'i) → Client ID, Client secret, Refresh token
   → *Saqlash* → *Ulanishni tekshirish* («Ulanish ishlaydi: «…» kanali»). Shundan keyin tasdiqlangan montajlar avtomatik yuklanadi.
7. Xavfsizlik: Playground'dagi tokenlarni o'chirish shart emas (u yerda saqlanmaydi); kirishni bekor qilish — https://myaccount.google.com/permissions.
   ISFT Core'da «O'chirish» — barcha sirlar o'chiriladi.

## Ma'lum cheklovlar
* **Kvota:** standart 10 000 birlik/kun; bitta `videos.insert` ≈ 1600 birlik → kuniga ≈ 6 video (`ISFT_CORE_YT_DAILY`). Ko'proq kerak bo'lsa —
  Google'da kvota oshirish arizasi (YouTube API Services audit).
* **Tasdiqlanmagan ilova:** 2020-07-28 dan keyin yaratilgan, Google auditidan o'tmagan API loyihalari orqali yuklangan videolar YouTube
  tomonidan **private** qilib qo'yilishi mumkin. ISFT Core buni aniqlaydi (ogohlantirish, havola darsga qo'yilmaydi, fayl qoladi).
  Yechim — Google'ning «YouTube API Services — Audit and Quota Extension» shakli orqali auditdan o'tish.
* *Testing* holatidagi ilovada refresh token 7 kunda eskiradi (`invalid_grant`) — ilovani *In production* qiling.
* Subtitrlar YouTube'ga yuklanmaydi (paketdagi fayl videoda bor); YouTube o'zi avtomatik subtitr qiladi.
* Video fayl bilan paket hajmi chegarasi (`ISFT_CORE_PK_PACKAGE_MB`, 500 MB) — uzun ma'ruza faqat YouTube bilan.
* `cryptography` o'rnatilmagan bo'lsa secret_store sirlarni shifrlamaydi (faqat bazadan ajratadi, 0600) — ishlab chiqarishda o'rnating.
* Montaj natijasini qisman qaytarish (alohida kesishni bekor qilish) yo'q — «Qayta montaj» izoh bilan.
* Eslatmalar «Mening vazifalarim» / qo'ng'iroqcha orqali (pull); Telegram'ga alohida push yo'q.
