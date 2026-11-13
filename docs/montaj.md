# Montaj — ISFT studiyasi uchun AI video-montaj

`tools/montaj/` — studiyada yozilgan xom ma'ruza videosini avtomatik ravishda tayyor darsga
aylantiradi: ortiqcha pauzalar, "eee/hmm" va qayta olingan dubllar kesiladi, audio tozalanadi,
slaydlar nutqqa moslab almashtiriladi, ISFT brendidagi intro/outro, lower-third, bob bannerlari,
subtitr (WebVTT), miniatyura va hisobot (report.json) yaratiladi.

Dastur ikki rejimda ishlaydi: **CLI** (operator qo'lda) va **worker** (ISFT Core navbatidan
ishlarni olib, natijani qaytaradi). Hamma narsa lokal: faster-whisper (large-v3), ffmpeg, Pillow.

> Natija har doim **operator tomonidan ko'rib chiqiladi** — ayniqsa o'zbek/rus aralash nutqda
> nutqni tanish xato qilishi mumkin. `report.json` dagi `cuts` va `warnings` shu uchun.

## Quvur (pipeline)

| # | Qadam | Modul | Nima qiladi |
|---|-------|-------|-------------|
| 1 | Tekshirish | `pipeline/probe.py` | PyAV bilan fps, o'lcham, burilish (rotation), audio; audio → 48 kHz mono WAV (audio/video boshlanish siljishi tuzatiladi) |
| 2 | Audio | `pipeline/audio.py` | `highpass=80 Hz` → `afftdn` shovqin pasaytirish → ikki bosqichli `loudnorm` (−16 LUFS, TP −1.5); `silencedetect` (−38 dB, 0.5 s) |
| 3 | Nutq | `pipeline/asr.py` | faster-whisper, so'z vaqtlari, VAD, `language=uz` (agar aniq rus/ingliz bo'lsa — avtomatik o'sha til), dars nomi/rejasi/slayd sarlavhalari `initial_prompt` sifatida; natija keshlanadi (`~/.cache/isft-montaj/asr`) |
| 4 | EDL | `pipeline/edl.py` | Kesishlar ro'yxati (pastda batafsil) |
| 5 | Slaydlar | `pipeline/slides.py` | PDF → rasmlar (pypdfium2) + sahifa matni; gaplar ↔ sahifalar TF-IDF o'xshashligi, monoton Viterbi (oldinga, 1 qadam ortga, "slaydsiz" holat), minimal ko'rsatish vaqti 6 s |
| 6 | Kompozitsiya | `pipeline/compose.py`, `graphics.py` | Bitta ffmpeg o'tishida: kesish + maket + grafika + intro/outro (xfade) + kodlash |
| 7 | Subtitr | `pipeline/captions.py` | Kesishlardan keyin qayta vaqtlangan WebVTT (2 qator × 42 belgi); `--burn-captions` bilan ASS orqali videoga yoziladi |
| 8 | Natijalar | `pipeline/run.py` | `final.mp4`, `captions.vtt`, `thumbnail.jpg`, `report.json`, `youtube_chapters.txt` (+ `transcript.json`, `edl.json`, `montaj.log`) |
| 9 | Sifat nazorati | `pipeline/run.py` | Chiqish asosiy qismi kirishning 40% idan qisqa bo'lsa — ogohlantirish; nutq ishonchi past (< 0.55) bo'lsa — faqat sukunat kesiladi + "Nutq aniqligi past — operator tekshirsin" |

Har qadamning vaqti log'ga va `report.json → timings` ga yoziladi.

### Kesish qoidalari (EDL)

`report.json → cuts[].reason` kodlari (vaqtlar **kirish** videosi bo'yicha):

| Kod | Ma'nosi |
|-----|---------|
| `silence` | 1.0 s dan uzun sukunat; ikki chetida 0.4 s tabiiy pauza qoldiriladi |
| `noise` | so'zlar orasidagi 1.2 s dan uzun nutqsiz joy (whisper tanimagan "eee", yo'tal, shovqin) |
| `filler` | faqat to'ldiruvchilardan iborat bo'lak (ee, eee, hmm, mmm, um, uh, э, ээ, ну, ммм …), ikki tomonida pauza bo'lsa |
| `retake` | ketma-ket o'xshash gaplar (token o'xshashligi ≥ 0.8 yoki oldingi gap keyingisining boshi ≥ 0.85) → **oxirgi dubl qoladi** |
| `retake_cue` | "qaytadan", "kesib tashlang", "stop", "boshidan", "заново", "ещё раз", "стоп" … → chala gap (yoki oldingi gap) + signal kesiladi |
| `tiny` | (ichki) kesishlar orasida qolgan juda qisqa so'zsiz bo'lak |

Xavfsizlik qoidalari:
- Kesish chegarasi hech qachon so'z ichiga tushmaydi (so'z chegaralari audio energiyasi bo'yicha
  aniqlashtiriladi, chegaralar 1/30 s kadr to'riga moslanadi; bo'shliqsiz yopishgan so'zlarda
  xatolik < 1 kadr).
- Signal so'zi ("stop", "yana bir bor" …) oddiy nutqda ham uchraydi, shuning uchun u faqat
  (a) alohida qisqa gap bo'lsa yoki (b) keyingi gap kesilayotgan gap kabi boshlansa (qayta urinish) qabul qilinadi.
- 0.6 s dan qisqa so'zsiz bo'laklar yutib yuboriladi, 0.3 s dan qisqa kesishlar bekor qilinadi.
- Audio va video bir xil kadr to'rida kesiladi (video 30 fps, audio 1600 namunali bo'laklar) —
  yuzlab kesishda ham sinxronlik siljimaydi.

## Shablonlar

Barchasi: 1920×1080, 30 fps, yuv420p, H.264 High (Mac'da `h264_videotoolbox`, aks holda `libx264`),
AAC 160k stereo, `+faststart`. Intro 4.5 s va outro 3.5 s (0.6 s xfade), pastda 8 px bordo chiziq,
yuqori o'ngda ISFT logosi (60% shaffof), intro'dan keyingi ilk 6 s da lower-third (ism + fan),
har bob boshida 2.4 s "N-BOʻLIM · bob nomi" banneri.

- **`maruza_slayd`** — chapda katta slayd kartasi (16:9, yumaloq burchak, yumshoq soya), o'ngda
  o'qituvchi slayd balandligidagi yumaloq ramkada (harakat xaritasi bo'yicha o'qituvchi joylashgan
  joydan kesiladi), ramka ichida pastda oq ism yorlig'i; yuqorida "L3 | Mavzu · Fan" sarlavha
  qatori va logo. Lower-third va banner slayd pastki chetiga "minib" turadi. Nutq hech bir slaydga
  mos kelmagan bo'laklarda — o'qituvchi to'liq kadrda. PDF berilmasa — `faqat_oqituvchi` ko'rinishi.
- **`faqat_oqituvchi`** — o'qituvchi to'liq kadrda (16:9 bo'lmagan yozuv xiralashtirilgan fon
  ustida to'liq ko'rsatiladi), lower-third boshida va har bob boshida banner.
- **`ekran`** — ekran yozuvi to'liq (nisbat mos kelmasa to'q fon bilan), `--webcam` berilsa
  past-o'ngda 400×300 yumaloq PiP (oq ramka, soya). Veb-kamera ekran yozuvidan kech/oldin
  boshlangan bo'lsa — `--webcam-offset SONIYA`.
- **Intro** — chapda och fonda logo va "ISFT · Masofaviy taʼlim", o'ngda bordo gradient panelda
  FAN (bosh harflar), oq chiziq, katta "L3 · Mavzu nomi", o'qituvchi ismi; matn 0.5 s dan keyin
  yumshoq paydo bo'ladi va 28 px yuqoriga siljiydi. **Outro** — och fon, markazda logo,
  "ISFT · Masofaviy taʼlim", fan · kod, o'qituvchi; oxirida qoraga so'nadi.
- **Miniatyura** (1280×720) — videodan 1-bob boshidagi kadr, chapda bordo panel, oq plitkada logo,
  "L3" belgisi, katta mavzu nomi, fan · o'qituvchi.

Tipografiya: Arial / Arial Bold (tizim TTF), o'zbek apostroflari avtomatik to'g'rilanadi:
`o'` → `oʻ` (U+02BB), tutuq belgisi → `’` (U+2019).

## CLI

```sh
~/.local/montaj-venv/bin/python tools/montaj/montaj.py \
  --input raw.mp4 --slides deck.pdf --template maruza_slayd \
  --subject "Ma'lumotlar bazasi" --code L3 --title "Relyatsion model va SQL so'rovlari" \
  --teacher "Karimova Dilnoza O'tkirovna" \
  --plan "1. Relyatsion model" --plan "2. SQL so'rovlari" --plan "3. Indekslar" \
  --out ~/Montaj/L3
```

Asosiy parametrlar:

| Parametr | Ma'nosi |
|----------|---------|
| `--template` | `maruza_slayd` (standart), `faqat_oqituvchi`, `ekran` |
| `--slides PDF`, `--webcam FAYL`, `--webcam-offset S` | qo'shimcha kirishlar |
| `--model` | faster-whisper modeli, standart `large-v3` |
| `--device` | `auto` (Apple GPU/MPS, bo'lmasa CPU int8), `mps`, `cpu` |
| `--language` | `uz` (standart; aniq rus/ingliz nutqi aniqlansa o'sha til), `ru`, `en`, `auto` |
| `--multilingual` | aralash uz/ru nutq uchun har segmentda til aniqlash (tajribaviy) |
| `--dry-run` | faqat EDL + hisobot (+ subtitr, boblar), render yo'q — tez tekshirish |
| `--no-intro`, `--no-outro`, `--burn-captions` | ko'rinish |
| `--max-pause 1.0`, `--keep-pad 0.4`, `--conservative` | kesish qattiqligi |
| `--encoder auto|h264_videotoolbox|libx264` | kodlovchi |
| `--keep-work`, `--no-cache`, `-v` | sozlash/diagnostika |

Chiqish papkasi:

```
final.mp4  captions.vtt  thumbnail.jpg  report.json  youtube_chapters.txt
transcript.json  edl.json  montaj.log
```

`report.json` aniq shu ko'rinishda:

```json
{"duration_in": 77.0, "duration_out": 63.97,
 "cuts": [{"start": 8.07, "end": 10.07, "reason": "silence"}, ...],
 "chapters": [{"start": 0.0, "title": "Kirish"}, {"start": 11.89, "title": "Relyatsion model"}, ...],
 "slide_changes": [{"t": 3.9, "slide": 1}, {"t": 11.89, "slide": 2}, ...],
 "warnings": [],
 "timings": {"1_tekshirish": 0.1, "2_audio": 1.9, "3_nutq": 21.0, "4_edl": 0.0, "5_slayd": 0.2,
             "6_render": 11.1, "8_miniatyura": 0.2, "jami": 35.0}}
```

- `cuts` — **kirish** vaqtida; `chapters`, `slide_changes` — **chiqish** videosi vaqtida (intro hisobga olingan).
- `slide_changes[].slide` — 1 dan boshlanadigan PDF sahifa raqami; `null` — slaydsiz bo'lak (o'qituvchi to'liq kadrda).
- `chapters[0]` doim `00:00` ("Kirish", yoki 1-reja bandi 10 s ichida boshlansa — o'sha band).
  Boblar orasi ≥ 10 s (YouTube talabi). Bob chegarasi: reja bandiga mos sarlavhali slayd birinchi
  ko'rsatilgan vaqt → aks holda transkriptda band so'zlari uchragan gap → aks holda teng taqsimlash.
- `youtube_chapters.txt`: `00:00 Kirish\n00:11 Relyatsion model\n…`

## Worker rejimi (ISFT Core)

```sh
ISFT_CORE_WORKER_TOKEN=... ~/.local/montaj-venv/bin/python tools/montaj/montaj.py \
  --worker --api https://core.example.uz [--work-dir DIR] [--once]
```

Shartnoma (barcha so'rovlarda `X-Worker-Token: $ISFT_CORE_WORKER_TOKEN`; token faqat `--api`
hostiga yuboriladi, boshqa hostdagi imzolangan URL'larga yuborilmaydi):

| So'rov | Tana / javob |
|--------|--------------|
| `POST /api/montaj/jobs/claim` | so'rov: `{}`; javob `200 {"job_id","template","lesson":{"course_id","no","code","kind","title","subject","teacher","plan":[...]},"raw_url","raw_ext","raw_name","slides_url"\|null,"logo_url"}` yoki `204` |
| `GET raw_url / slides_url / logo_url` | imzolangan URL (nisbiy bo'lsa `--api` ga qo'shiladi); uzilsa `Range: bytes=N-` bilan davom ettiriladi (6 urinish, eksponensial kutish) |
| `POST /api/montaj/jobs/{id}/progress` | `{"stage","pct","message"}` — kamida har 3 s da bir (bosqich almashganda darhol) |
| `POST /api/montaj/jobs/{id}/result` | `multipart/form-data`: `video` (final.mp4, video/mp4), `captions` (captions.vtt, text/vtt), `thumbnail` (thumbnail.jpg, image/jpeg), `report` (report.json, application/json); fayl xotiraga o'qilmay oqim bilan yuboriladi, `Content-Length` aniq; 5xx/uzilishda (va 409 «… yuklanmoqda») 4 urinish. Har urinishdan oldin `progress` («yuborish», 97), yuklash davomida parallel oqim har 60 s da yana `progress` (server lease'ni uzaytiradi) |
| `POST /api/montaj/jobs/{id}/fail` | `{"error": "…"}` (o'zbekcha matn, ≤ 4000 belgi) |

`stage` qiymatlari va `pct` oralig'i: `yuklash` 0–2 → `tayyorlash` 2–5 → `audio` 5–10 → `nutq` 10–45 →
`tahrir` 45–47 → `slayd` 47–50 → `render` 50–94 → `yakun` 94–97 → `yuborish` 97 (100% ni server
`result` qabul qilganda o'zi qo'yadi). `pct` monoton o'sadi.

`plan` elementlari satr yoki `{"title": …}` obyekt bo'lishi mumkin. `lesson.code` + `lesson.title`
intro/miniatyurada "L3 · Mavzu" ko'rinishida chiqadi. `logo_url` yuklanmasa standart
`static/brand/logo.png` ishlatiladi.

Xatti-harakat:
- Xom video kengaytmasi: `raw_ext` (server) → yuklab olish `Content-Type` / `Content-Disposition` → baytlar (`ftyp` — mp4/mov, EBML — mkv/webm) → `.mp4`.
  Imzolangan havola nomi (`17.raw.<muddat>.<lease>.<imzo>`) kengaytma sifatida ishlatilmaydi.
- Navbat bo'sh (`204`) yoki tarmoq xatosi — kutish 5 s dan 60 s gacha asta-sekin uzayadi.
- `progress` javobi `404/409/410` bo'lsa — server ishni bekor qilgan deb hisoblanadi, render to'xtatiladi va `/fail` yuboriladi.
- Claim javobida `lease` bo'lsa — `progress` / `result` / `fail` `X-Worker-Lease` sarlavhasi bilan yuboriladi (eskirgan lease → 409 → ish bekor); eski serverda `lease` yo'q — sarlavha yuborilmaydi.
- `SIGINT` (Ctrl+C) 1-marta — joriy ish tugagach chiqadi; 2-marta yoki `SIGTERM` (launchd) — joriy
  ish to'xtatiladi, `/fail {"error":"Worker to'xtatildi yoki ish bekor qilindi"}` yuboriladi.
- Har ish alohida vaqtinchalik papkada, oxirida o'chiriladi.

## Studiya Mac'ini sozlash

1. Python venv (Python 3.11+):
   ```sh
   python3 -m venv ~/.local/montaj-venv
   ~/.local/montaj-venv/bin/pip install faster-whisper "av<16" pypdfium2 pillow numpy imageio-ffmpeg
   ```
2. ffmpeg: to'liq build (`libx264`, `h264_videotoolbox`, `afftdn`, `loudnorm`, `subtitles`/libass,
   `xfade`) `~/.local/bin/ffmpeg` ga qo'yiladi yoki `MONTAJ_FFMPEG=/yo'l/ffmpeg`. Topilmasa
   `imageio-ffmpeg` ichidagi statik ffmpeg ishlatiladi (unda `--burn-captions` ishlamasligi mumkin).
3. Whisper modelini oldindan yuklab olish (internet bir marta kerak, ~3 GB):
   ```sh
   ~/.local/montaj-venv/bin/python -c "from faster_whisper import WhisperModel; WhisperModel('large-v3')"
   ```
4. Sozlamalar fayli `~/.config/isft-montaj/worker.env` (`chmod 600`):
   ```sh
   ISFT_CORE_API=https://core.example.uz
   ISFT_CORE_WORKER_TOKEN=...
   ```
5. launchd (foydalanuvchi kirganda avtomatik, yiqilsa qayta ko'tariladi):
   ```sh
   cd ~/isft/jarvis-mvp
   sed -e "s#__REPO__#$PWD#g" -e "s#__HOME__#$HOME#g" tools/montaj/launchd/uz.isft.montaj.worker.plist \
     > ~/Library/LaunchAgents/uz.isft.montaj.worker.plist
   launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/uz.isft.montaj.worker.plist
   tail -f ~/Library/Logs/isft-montaj-worker.log
   # to'xtatish: launchctl bootout gui/$(id -u)/uz.isft.montaj.worker
   ```
   Mac uxlab qolmasligi kerak (System Settings → Energy, yoki `caffeinate -s`).

## Sinovlar

```sh
cd ~/isft/jarvis-mvp
~/.local/montaj-venv/bin/python -m unittest discover -s tools/montaj/tests -p 'test_unit.py'    # 0.1 s
~/.local/montaj-venv/bin/python -m unittest discover -s tools/montaj/tests -p 'test_e2e.py'     # ~1–2 daq.
~/.local/montaj-venv/bin/python -m unittest discover -s tools/montaj/tests -p 'test_worker.py'  # ~25 s
```

- `test_unit.py` — to'ldiruvchilar, dubllar (to'liq, chala, zanjir, signal alohida/yopishgan,
  "stop" oddiy nutqda), sukunat/birlashtirish, 60 ta tasodifiy transkriptda chegaralar so'z
  ichida emas va kadr to'rida, slayd moslash (monoton, ortga qaytish, min. vaqt, matnsiz PDF,
  slaydsiz bo'lak), VTT qayta vaqtlash va qator chegaralari, boblar, hisobot sxemasi.
- `test_e2e.py` — `tests/fixtures.py` sintetik ma'ruza yaratadi (macOS `say`, pauzalar,
  "Ummm… ehhh…", chala va to'liq dubl, "Stop. Again." signali, pushti shovqin, 25 fps "o'qituvchi"
  videosi, 4 sahifali matnli PDF; `ekran` uchun Articulate yozuvidan bo'lak). Uchala shablon;
  tekshiruvlar: fayllar, sxema, 1920×1080@30, A/V uzunligi teng, kiritilgan nuqsonlar kesilgan va
  kerakli nutq kesilmagan, slaydlar tartibi, boblar, VTT, chiqish kadri EDL bo'yicha xom kadrga mos.
  Ko'zdan kechirish uchun kadrlar: `…/scratchpad/montaj/e2e/<shablon>/frames/`.
- `test_worker.py` — jarayon ichidagi soxta ISFT Core (http.server): claim → yuklash (aloqa
  ataylab uziladi, `Range` bilan davom) → progress → multipart natija; yo'q fayl → `/fail`;
  noto'g'ri token → kutish bilan qayta urinish.

Generatsiya qilingan media repoga qo'shilmaydi (scratch papkada).

## Ishlash tezligi (M4, 10 yadro, 16 GB)

O'lchangan (2026-11, `h264_videotoolbox`, whisper large-v3):

| Yozuv | Kirish → chiqish | Audio | Nutq (ASR) | Render | Jami | daq./daq. |
|-------|------------------|-------|------------|--------|------|-----------|
| Haqiqiy o'zbek nutqi, ekran yozuvi (`ekran`, 28.4 fps VFR) | 12:12 → 10:04, 46 kesish | 17.5 s | 234.6 s (MPS) | 81.1 s | 334 s | **0.46** |
| Sintetik ma'ruza (`maruza_slayd`, 25 fps, PDF) | 1:17 → 1:03, 8 kesish | 1.9 s | 21.0 s (MPS) | 11.1 s | 35 s | 0.45 |
| Xuddi shu, ASR CPU int8 (`--device cpu`) | — | — | 138 s | — | — | ~2.1 |

- Nutq tanish: MPS (Apple GPU, float16) ≈ 0.2–0.32× real vaqt (o'zbek nutqida temperatura
  fallback'lari tufayli sekinroq), CPU int8 ≈ 1.8× real vaqt. **90 daqiqalik ma'ruza ≈ 40–45 daqiqa**
  (MPS), CPU'da ≈ 3 soat.
- Render (bitta ffmpeg o'tishi, VideoToolbox) ≈ 0.13× real vaqt chiqish uchun; libx264 ≈ 3–4 marta sekinroq.
- Transkripsiya keshlanadi: shablon/dizaynni o'zgartirib qayta ishlash faqat render vaqtini oladi.
- 1080p30, 5 Mbit/s → ~37 MB/daqiqa (10 daqiqa = 100 MB).

## Cheklovlar

- **O'zbek nutqini tanish mukammal emas** (Whisper large-v3), ayniqsa o'zbek/rus aralash nutqda
  va atamalarda. To'ldiruvchilar ko'pincha transkriptga tushmaydi — ular `noise` (nutqsiz tovush)
  sifatida kesiladi. Dubl va signal aniqlash transkriptga tayanadi, shuning uchun ishonch past
  bo'lsa avtomatik ravishda faqat sukunat kesiladi.
- **Operator har doim ko'rib chiqadi**: `report.json → cuts` (sabab bilan), `warnings`.
- Avtomatik ko'p kamerali almashtirish yo'q (bitta o'qituvchi kamerasi + ixtiyoriy ekran/veb-kamera).
- O'qituvchini kesish yuzni aniqlash emas, harakat xaritasi bo'yicha (statik o'tirgan o'qituvchida
  markaz olinadi).
- Slayd sinxronlash sahifa matniga tayanadi; rasmli (skanerlangan) PDF'da slaydlar vaqt bo'yicha
  teng taqsimlanadi va ogohlantirish beriladi. Slayd ichidagi animatsiyalar (bosqichma-bosqich
  paydo bo'lish) hisobga olinmaydi.
- Whisper MPS (Apple GPU) backend'i ctranslate2'da "experimental"; muammo bo'lsa `--device cpu`
  (≈8 marta sekinroq).
- Kesish chegaralarida audio krossfeyd yo'q (kesishlar pauzalarda bo'lgani uchun odatda sezilmaydi).
