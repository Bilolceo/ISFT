# ISFT Core — ekspluatatsiya qo'llanmasi (runbook)

Kimlar uchun: serverni joylaydigan va kuzatadigan AT xodimi. Kod: `start.sh`, `railway.json`, `run.sh`, `app/bot.py`, `app/ai.py`.

## 1. Jarayon tuzilishi

Bitta jarayon (`uvicorn app.main:app`) ichida quyidagilar ishlaydi:

- veb-panel va API;
- fon vazifalari: kameralar so'rovi, talabalar markazi qoidalari;
- **Telegram bot** (`TELEGRAM_BOT_TOKEN` berilgan bo'lsa). Bot polling usulida ishlaydi va kunlik ikki ishni bajaradi:
  - rahbarlarga kunlik brifing — har kuni **08:00**;
  - Portal muddat eslatmalari — ish kunlari **09:00** (yakshanbadan tashqari).

  Ikkala vaqt ham **Toshkent vaqti** bo'yicha hisoblanadi (`ISFT_CORE_TZ`), server soat zonasiga bog'liq emas.

Alohida bot jarayoni kerak emas. Eski yo'l ham ishlaydi: `TELEGRAM_BOT_TOKEN=... .venv/bin/python -m app.bot`.
Bir token bilan faqat **bitta** poller ishlaydi. Buni data papkasidagi fayl qulfi (`.bot-<xesh>.lock`) ta'minlaydi:
- qulfni ikkinchi bo'lib olmoqchi bo'lgan veb-jarayon botni ishga tushirmaydi va holatda `mode: "external"` ko'rsatadi;
- qulfni ikkinchi bo'lib olmoqchi bo'lgan alohida jarayon xabar berib chiqib ketadi.

Holatni tekshirish: `GET /api/status`. Javobdagi bo'limlar:
- `bot`: `enabled`, `running`, `username`, `mode` (`web` | `standalone` | `external`), `note`, `last_error`, `error_at`, `next_brief`, `next_portal`;
- `ai`: til modeli holati (5-bo'lim).

Logda va `last_error` maydonida bot tokeni har doim `***` bilan yashiriladi.

## 2. Muhit o'zgaruvchilari

### Joylashuv va baza
| O'zgaruvchi | Standart | Ma'nosi |
|---|---|---|
| `ISFT_CORE_DATA_DIR` | `<loyiha>/data` (Railway: `/app/data`) | Barcha doimiy fayllar shu yerda: baza, portal fayllari, buyruqlar, yuklamalar, `secrets/`, `.seed_version`, bot qulfi va holati. **Volume shu papkaga ulanadi.** |
| `ISFT_CORE_DB` | `$ISFT_CORE_DATA_DIR/jarvis.db` | SQLite baza fayli. Asosan test yoki sandbox uchun alohida baza berishda ishlatiladi |
| `ISFT_CORE_FILES_DIR` | `$ISFT_CORE_DATA_DIR/portal_files` | Portal fayllari |
| `ISFT_CORE_STAFFABS_DIR` | `$ISFT_CORE_DATA_DIR/staffabs_files` | Xodimlar ta'tili hujjatlari |
| `ISFT_CORE_SECRETS_DIR` | `$ISFT_CORE_DATA_DIR/secrets` | Maxfiy ombor (kamera parollari) |
| `ISFT_CORE_SECRET_KEY` | yo'q → `secrets/master.key` | Maxfiy omborni shifrlash kaliti (Fernet). Ishlab chiqarishda bazadan alohida saqlang |
| `ISFT_CORE_RESEED` | `1` | `start.sh`: seed versiyasi o'zgarsa demo bazani qayta yaratish. `0` bo'lsa seed hech qachon avtomatik ishlamaydi (4-bo'lim) |
| `PORT` | `8000` | HTTP port. Railway o'zi beradi |
| `TZ` | `start.sh`: `Asia/Tashkent` | Jarayon soat zonasi. Tizimda zoneinfo bo'lmasa `UZT-5` (UTC+5) ishlatiladi |
| `ISFT_CORE_TZ` | `Asia/Tashkent` | Ilova ichidagi vaqt zonasi: bot jadvali, kamera voqealari |
| `ISFT_CORE_PUBLIC_URL` | avtomatik (lokal IP) | QR havolalari uchun ochiq manzil, masalan `https://isft-production.up.railway.app` |

### Kirish va demo
| O'zgaruvchi | Standart | Ma'nosi |
|---|---|---|
| `ISFT_CORE_DEMO_PASSWORD` | `Isft2026` | Demo akkauntlar paroli. Seed paytida o'qiladi |
| `ISFT_CORE_HIDE_DEMO_HINT` | bo'sh | `1`: kirish sahifasida sinov paroli izohi yashiriladi (jonli namoyish uchun) |

### Telegram bot
| O'zgaruvchi | Standart | Ma'nosi |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | yo'q | @BotFather tokeni. Bo'lmasa bot o'chiq, ilova odatdagidek ishlaydi (logda: «Telegram bot o'chiq») |
| `ISFT_CORE_BOT` | `1` | `0`: veb-jarayon ichida bot ishga tushmaydi (masalan, bot alohida `python -m app.bot` bilan yuritilsa) |
| `ISFT_CORE_BRIEF_TIME` | `08:00` | Kunlik brifing vaqti (Toshkent vaqti) |
| `ISFT_CORE_PORTAL_REMIND` | `09:00` | Portal eslatmalari vaqti (ish kunlari, Toshkent vaqti) |

### Til modeli (AI)
| O'zgaruvchi | Standart | Ma'nosi |
|---|---|---|
| `ISFT_CORE_LLM_URL` | `OLLAMA_URL` yoki `http://localhost:11434` | Til modeli serveri. **Faqat institut nazoratidagi server bo'lishi shart: shaxsiy ma'lumot O'zbekistondan tashqariga chiqmasligi kerak.** Ollama (`http://10.0.0.5:11434`) yoki OpenAI-mos API (`http://10.0.0.5:8000/v1`: vLLM, llama.cpp, Ollama `/v1`) |
| `ISFT_CORE_LLM_API` | avtomatik | `ollama` yoki `openai`. Bo'sh bo'lsa: manzil `/v1` bilan tugasa `openai`, aks holda `ollama` |
| `ISFT_CORE_LLM_KEY` | bo'sh | Ixtiyoriy Bearer kalit (institut serveri himoyalangan bo'lsa) |
| `ISFT_CORE_LLM` | `1` | `0`: til modeli butunlay o'chiriladi va tizim doim «Tahlil rejimi»da ishlaydi |
| `ISFT_CORE_MODEL` | `qwen3:8b` | Model nomi |
| `OLLAMA_URL` | `http://localhost:11434` | Eski nom. `ISFT_CORE_LLM_URL` berilmagan bo'lsa ishlatiladi |

Hech qanday bulut AI provayderi standart holatda ulanmagan va ulanmasligi kerak.

### Fayllar xavfsizligi (Portal)
| O'zgaruvchi | Standart | Ma'nosi |
|---|---|---|
| `ISFT_CORE_CLAMD` | bo'sh | ClamAV manzili: `host:3310` yoki unix soket yo'li |
| `ISFT_CORE_CLAMD_REQUIRED` | bo'sh | `1`: antivirus ishlamasa fayl qabul qilinmaydi |

### Kameralar va Kirish nazorati
Batafsil ma'lumot: `docs/hikvision.md`, 9-bo'lim.

| O'zgaruvchi | Standart |
|---|---|
| `ISFT_CORE_CAM_POLL` | `60` |
| `ISFT_CORE_CAM_OFFLINE_FAILS` | `3` |
| `ISFT_CORE_WORK_HOURS` | `07:30-20:00` |
| `ISFT_CORE_CAM_OCC_PATH` | bo'sh |
| `ISFT_CORE_CAM_QUEUE_PATH` | `/ISAPI/Intelligent/channels/{ch}/queueManagement/status` |
| `ISFT_CORE_CAM_DEDUP_SEC` | `300` |
| `ISFT_CORE_FEATURE_FACE` | `1` |
| `ISFT_CORE_FEATURE_ANPR` | `0` |
| `ISFT_CORE_FACE_MATCH_MIN` | `0.75` |
| `ISFT_CORE_FACE_KEEP_DAYS` | `7` |
| `ISFT_CORE_FACE_EVENTS_DAYS` | `90` |
| `ISFT_CORE_FACE_EXIT_CAMS` | bo'sh |
| `ISFT_CORE_STAFF_START` | `09:00` |
| `ISFT_CORE_FACE_LATE_GRACE_MIN` | `0` |

### Testlar
| O'zgaruvchi | Standart | Ma'nosi |
|---|---|---|
| `ISFT_TEST_URL` | `http://127.0.0.1:8000` | Testlar so'rov yuboradigan server |
| `ISFT_CORE_DB` / `ISFT_CORE_DATA_DIR` | yuqoridagidek | Testlar to'g'ridan-to'g'ri o'qiydigan baza va papka. Server ishlatayotgan baza bilan **bir xil** bo'lishi shart |

## 3. Railway sozlamalari

`railway.json` start buyrug'ini (`sh start.sh`), healthcheck'ni (`/healthz`, 900 soniya) va qayta ishga tushirish siyosatini belgilaydi.
Muhit o'zgaruvchilari va volume'ni esa Railway panelida qo'lda sozlash kerak.

1. **Volume.** Service → Settings → Volumes → *Add volume*, mount path: `/app/data`.
   - Boshqa yo'l tanlasangiz, masalan `/data`, `ISFT_CORE_DATA_DIR=/data` o'zgaruvchisini qo'ying.
   - Volume bo'lmasa, har bir deploy bazani, portal fayllarini va `secrets/` papkasini o'chirib yuboradi.
   - Volume ulangan servisda Railway eski va yangi deploy'ni bir vaqtda ishlatmaydi. Shu sabab deploy paytida qisqa uzilish bo'ladi.
2. **O'zgaruvchilar** (Service → Variables):
   - `TZ=Asia/Tashkent` — `start.sh` buni o'zi qo'yadi, panelda berish ixtiyoriy;
   - `ISFT_CORE_PUBLIC_URL=https://isft-production.up.railway.app` — QR havolalari to'g'ri chiqishi uchun;
   - `TELEGRAM_BOT_TOKEN=<token>` — bot kerak bo'lsa (pastga qarang);
   - ixtiyoriy: `ISFT_CORE_HIDE_DEMO_HINT=1`, `ISFT_CORE_SECRET_KEY=<Fernet kalit>`.
3. **Telegram tokeni:**
   1. Telegram'da `@BotFather` → `/newbot` → nom va `..._bot` bilan tugaydigan username bering.
   2. Berilgan tokenni (`123456789:AA...`) Railway → Variables → `TELEGRAM_BOT_TOKEN` ga qo'ying. Token maxfiy: chatga yoki git'ga yozmang.
   3. Deploy tugagach `GET /api/status` → `bot.running: true` va `bot.username` chiqishi kerak. `last_error` bo'lsa, ko'rinishiga qarab:
      - `InvalidToken` — token noto'g'ri yoki bekor qilingan. `@BotFather` → `/token` orqali yangisini oling;
      - `Conflict` — shu token bilan boshqa joyda ham bot ishlayapti, masalan noutbukda `./run.sh`. Bittasini to'xtating;
      - tarmoq xatosi — bot 30 soniyadan 10 daqiqagacha kutib, o'zi qayta urinadi.
   4. Botga yozing: `REKTOR <parol>`. Buxgalteriya va Kadrlar akkauntlari botga ulanmaydi; bu ataylab qilingan.
   5. Tokenni almashtirgandan keyin servisni qayta ishga tushiring (Redeploy/Restart).
4. **Healthcheck.**
   - `GET /healthz` faqat bazani tekshiradi (`SELECT 1`) va `{"ok": true}` (200) yoki 503 qaytaradi. Ollama va Telegram tekshirilmaydi.
   - Railway healthcheck faqat deploy paytida ishlaydi. Birinchi ishga tushishda yoki `SEED_VERSION` o'zgarganda seed port ochilishidan oldin bajariladi: lokal kompyuterda ~2 daqiqa, Railway'da 2–5 daqiqa. Shuning uchun `healthcheckTimeout` 900 soniya qilib qo'yilgan.
5. **To'xtatish.**
   - Railway SIGTERM yuboradi: uvicorn bot polling'ini, fon vazifalarini va qulfni toza yopadi.
   - `drainingSeconds: 15` — SIGKILL'dan oldingi kutish vaqti.
6. **AI.** Railway'da Ollama yo'q, shuning uchun tizim «Tahlil rejimi»da ishlaydi (5-bo'lim). Bulutdagi demo serverga institut tashqarisidagi modelni ulamang.

## 4. Seed (demo ma'lumotlar) — FAQAT DEMO UCHUN

`start.sh` qoidasi: baza fayli yo'q **yoki** `SEED_VERSION` fayli `$ISFT_CORE_DATA_DIR/.seed_version` dan farq qilsa, `python -m app.seed` ishga tushadi.

- Seed **eski bazani o'chiradi** va 2026-11-04 hikoyasi asosida yangi sun'iy ma'lumot yaratadi. Barcha o'zgarishlar yo'qoladi: portal xatlari, yaratilgan akkauntlar, parollar, Telegram ulanishlari.
- Bu qoida faqat demo deploy uchun. Haqiqiy ma'lumot bilan ishlaganda `ISFT_CORE_RESEED=0` qo'ying. Shunda seed hech qachon avtomatik ishlamaydi, versiya farqi faqat logda ogohlantirish bo'ladi.
- `SEED_VERSION` ni o'zgartirish (git'da) = keyingi deploy'da demo baza qayta yaratiladi.
- Qo'lda qayta seed qilish: `python -m app.seed`. Keyin **serverni albatta qayta ishga tushiring**. Ishlab turgan jarayon xotirasida eski holat qoladi: sessiyalar, keshlar, `services.TODAY`, reyting keshi. Railway'da bu Restart, lokalda `./run.sh` ni qayta ishga tushirish. `start.sh` orqali seed qilingan bo'lsa, `.seed_version` ham yangilanadi.
- Seed'dan keyin barcha Telegram ulanishlari uziladi (`telegram_id` yo'q). Foydalanuvchilar botga qayta `KOD parol` yuborishi kerak.

## 5. AI: «Tahlil rejimi»

Til modeliga ulanib bo'lmasa (`/api/status` → `ai.ai: false`):

- chat, ogohlantirishlar, bayonnomadan topshiriq ajratish va shartnoma tekshiruvi **qoidalar** asosida ishlaydi (`"source": "qoida"`);
- tarjima va javob loyihasi ishlamaydi. Ular `{"ai": false, "reason": "..."}` va foydalanuvchiga tushunarli xabar qaytaradi;
- `ai.tools` har bir vosita uchun `"ai"`, `"qoida"` yoki `null` qiymatini beradi. `null` — vosita o'chiq;
- holat 15–30 soniya keshlanadi: model ulanganidan keyin bir daqiqa ichida o'zi «AI faol»ga o'tadi.

## 6. Zaxira nusxa va tiklash (bugun mavjud buyruqlar)

Railway'da buyruqlar `railway ssh` orqali konteyner ichida bajariladi, lokalda esa `.venv/bin/python`. Nusxani volume ichida (`/app/data/backups/`) saqlash mumkin, lekin u server bilan birga yo'qolishi mumkin. Muntazam ravishda tashqariga ham ko'chiring.

**Butun baza** (SQLite'ning izchil nusxasi; ilova ishlab turganda ham xavfsiz):
```bash
python -c "import sqlite3,sys; s=sqlite3.connect('data/jarvis.db'); d=sqlite3.connect(sys.argv[1]); s.backup(d); d.close()" data/backups/jarvis_$(date +%Y%m%d).db
# sqlite3 CLI bo'lsa:  sqlite3 data/jarvis.db ".backup 'data/backups/jarvis_YYYYMMDD.db'"
```
Bazani tiklash:
1. Serverni to'xtating.
2. Nusxani `data/jarvis.db` o'rniga qo'ying va `jarvis.db-wal` / `jarvis.db-shm` fayllarini o'chiring.
3. `SEED_VERSION` va `data/.seed_version` bir xil bo'lishini tekshiring. Aks holda `start.sh` bazani qayta seed qiladi; buning oldini olish uchun `ISFT_CORE_RESEED=0` qo'ying.
4. Serverni ishga tushiring.

**Portal** (jadvallar + fayllar, sha256 bilan):
```bash
python -m app.portal_backup backup data/backups/portal_YYYYMMDD.zip
python -m app.portal_backup restore data/backups/portal_YYYYMMDD.zip --force
python -m app.portal_backup verify          # yo'qolgan, buzilgan yoki ortiqcha fayllar; --fix faqat bo'sh sha256 ni to'ldiradi
```
**Boshqa fayllar.** Baza nusxasidan tashqari volume'dagi quyidagi papkalarni ham saqlang:
- `secrets/` — kamera parollari kaliti. Bu papkani bazadan **alohida** saqlang;
- `orders/`, `uploads/`, `staffabs_files/`, `syllabus/`.

## 7. Testlarni sandbox serverga qarshi ishga tushirish

Testlar bazani o'zgartiradi, shuning uchun ularni ishlab turgan `:8000` yoki asosiy `data/jarvis.db` ga qarshi emas, nusxaga qarshi ishga tushiring:
```bash
SB=/tmp/isft-sb; rm -rf $SB; mkdir -p $SB
rsync -a --exclude 'jarvis.db*' data/ $SB/
sqlite3 data/jarvis.db ".backup '$SB/jarvis.db'"
ISFT_CORE_DATA_DIR=$SB ISFT_CORE_DB=$SB/jarvis.db ISFT_CORE_FILES_DIR=$SB/portal_files ISFT_CORE_STAFFABS_DIR=$SB/staffabs_files \
  .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8103 &
until curl -sf http://127.0.0.1:8103/healthz >/dev/null; do sleep 1; done

export ISFT_TEST_URL=http://127.0.0.1:8103 ISFT_CORE_DB=$SB/jarvis.db ISFT_CORE_DATA_DIR=$SB
.venv/bin/python tests/test_regressiya.py
.venv/bin/python tests/test_ruxsatlar.py
```
- Sandbox'da `TELEGRAM_BOT_TOKEN` bermang. Aks holda u ishlab turgan bot bilan `409 Conflict` beradi.
- Testlar tugagach sandbox serverni to'xtating: `kill %1` yoki `lsof -ti tcp:8103 | xargs kill`.

## 8. Tezkor tekshiruv ro'yxati

| Belgi | Tekshirish |
|---|---|
| Sayt ochilmaydi, deploy «healthcheck failed» | Deploy logida seed tugaganini tekshiring; `/healthz` 503 bo'lsa — baza fayli yoki volume |
| Brifing / eslatma kelmayapti | `/api/status` → `bot.running`, `bot.last_error`, `bot.next_brief`. Foydalanuvchi botga ulanganmi (`users.telegram_id`) |
| Vaqtlar 5 soat siljigan | `TZ` va `ISFT_CORE_TZ`. Deploy logida `start.sh` qaysi TZ qo'yganini ko'ring |
| Deploy'dan keyin ma'lumotlar yo'qoldi | Volume `/app/data` ga ulanganmi; `SEED_VERSION` o'zgarganmi (4-bo'lim) |
