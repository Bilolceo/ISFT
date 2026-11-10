# Testlar

Testlar uchidan-uchigacha: jonli server (HTTP) + seed qilingan SQLite baza. Ko'pchiligi bazani o'zgartiradi, shuning uchun
**asosiy usul — `tests/run_all.py`**: u har safar toza vaqtinchalik muhit yaratadi va ishchi `data/` ga tegmaydi.

## Hammasini ishga tushirish (lokal)

```bash
.venv/bin/python tests/run_all.py                        # ~1.5 daqiqa: seed → server (bo'sh port) → barcha to'plamlar → jadval
.venv/bin/python tests/run_all.py --only reyting,flows   # faqat tanlanganlar (nom: test_ va .py siz)
.venv/bin/python tests/run_all.py --skip hikvision       # birortasini chiqarib tashlash
.venv/bin/python tests/run_all.py --list                 # to'plamlar va ishga tushish tartibi
.venv/bin/python tests/run_all.py --keep                 # vaqtinchalik katalog va loglar saqlansin
.venv/bin/python tests/run_all.py --data-dir /tmp/isft   # shu katalog (baza bo'lmasa seed qilinadi; --reseed — majburan)
.venv/bin/python tests/run_all.py --fake-today 2026-11-04  # «bugun»ni qotirish (ISFT_CORE_FAKE_TODAY)
```

Nima qiladi:

1. vaqtinchalik katalog yaratadi va `python -m app.seed` ni `ISFT_CORE_DATA_DIR`, `ISFT_CORE_DB`, `ISFT_CORE_FILES_DIR`,
   `ISFT_CORE_STAFFABS_DIR`, `ISFT_CORE_SECRETS_DIR` bilan ishga tushiradi;
2. `uvicorn app.main:app` ni bo'sh portda ko'taradi va `/healthz` ni kutadi;
3. `tests/test_*.py` ni tartib bilan ishga tushiradi: avval o'qiydigan/o'zini tozalaydiganlar, oxirida bazani ko'p o'zgartiradiganlar
   (`talabalar_markazi` — eng oxirida). Yangi `test_*.py` fayl avtomatik qo'shiladi (ma'lum tartibdan keyin);
4. natijalar jadvalini chiqaradi (✓/✗ soni, vaqt), serverni to'xtatadi; biror to'plam yiqilsa chiqish kodi 1.
   Xato bo'lsa loglar (`_testlogs/seed.log`, `server.log`, `test_<nom>.log`) saqlanib qoladi.

Muhit: LLM (Ollama) standart holda o'chiriladi — AI qoidaviy zaxira javob beradi, natija deterministik (CI bilan bir xil).
`--llm` bilan mavjud sozlama qoldiriladi. Telegram bot tokeni test serveriga berilmaydi.

## Bitta to'plamni mavjud serverga qarshi

Har bir test mustaqil skript; manzil va baza muhit o'zgaruvchilaridan olinadi (`:8000` / `data/jarvis.db` — faqat standart qiymat):

```bash
ISFT_TEST_URL=http://127.0.0.1:8132 ISFT_CORE_DATA_DIR=/tmp/sb ISFT_CORE_DB=/tmp/sb/jarvis.db \
ISFT_CORE_FILES_DIR=/tmp/sb/portal_files ISFT_CORE_STAFFABS_DIR=/tmp/sb/staffabs_files \
  .venv/bin/python tests/test_reyting.py
```

Ishchi (demo) serverga qarshi ishga tushirmang — testlar bazani o'zgartiradi; keyin `python -m app.seed` kerak bo'ladi.

## Vaqt

Ilova va testlar «bugun»ni `app/clock.py` dan oladi: Toshkent vaqti (`ISFT_CORE_TZ`, standart `Asia/Tashkent`), server
zonasidan qat'i nazar. `ISFT_CORE_FAKE_TODAY=YYYY-MM-DD` — sanani qotirish (soat haqiqiy); seed, server va testlarga bir xil
beriladi (`--fake-today`). Kun vaqtiga bog'liq tekshiruvlar (masalan, Face ID «bugungi kadrlar») kadrlari bor oxirgi kunga qaraydi —
yarim tundan keyin ham o'tadi.

## CI (GitHub Actions)

`.github/workflows/tests.yml`: `main` ga push, har bir pull request va qo'lda (`workflow_dispatch`). Ubuntu, Python
`.python-version` (3.13), `pip install -r requirements.txt` (kesh bilan), keyin `python tests/run_all.py`. Vaqt chegarasi 40 daqiqa.
Xato bo'lsa loglar `isft-test-logs` artefakti sifatida yuklanadi.

CI'da o'rnatilmaydigan ixtiyoriy qismlar (testlar ularsiz o'tadi):

- **Tesseract (OCR)** — skan/ariza OCR tekshiruvlari o'tkazib yuboriladi (lokal macOS'da tesseract bo'lsa, ular ham tekshiriladi);
- **ClamAV** (`ISFT_CORE_CLAMD`) — fayllar `scan: "tekshirilmadi"` bilan qabul qilinadi;
- **Ollama / LLM** — qoidaviy zaxira javoblar;
- **Telegram bot** — token berilmaydi.
