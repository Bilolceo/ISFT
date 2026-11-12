#!/bin/sh
# Railway / server ishga tushirish. Batafsil: docs/ops.md
set -e
cd "$(dirname "$0")"
# Toshkent vaqti (TZ berilmagan bo'lsa). Tizimda zoneinfo bo'lmasa — POSIX ko'rinish (UTC+5, yozgi vaqt yo'q).
if [ -z "$TZ" ]; then
  if [ -f /usr/share/zoneinfo/Asia/Tashkent ]; then export TZ=Asia/Tashkent; else export TZ=UZT-5; fi
fi
DATA="${ISFT_CORE_DATA_DIR:-data}"
DB="${ISFT_CORE_DB:-$DATA/jarvis.db}"
mkdir -p "$DATA"
# DEMO QOIDASI: baza yo'q yoki seed versiyasi o'zgargan bo'lsa — demo ma'lumotlar QAYTA YARATILADI (eski baza o'chadi).
# Haqiqiy ma'lumot bilan ishlaganda ISFT_CORE_RESEED=0 qo'ying — seed hech qachon avtomatik ishlamaydi.
WANT="$(cat SEED_VERSION 2>/dev/null || echo 0)"
HAVE="$(cat "$DATA/.seed_version" 2>/dev/null || echo none)"
if [ ! -f "$DB" ] || [ "$WANT" != "$HAVE" ]; then
  if [ "${ISFT_CORE_RESEED:-1}" = "0" ]; then
    echo "OGOHLANTIRISH: seed versiyasi $HAVE -> $WANT, lekin ISFT_CORE_RESEED=0 — baza o'zgartirilmaydi."
  else
    echo "Demo ma'lumotlar yaratilmoqda (seed: $HAVE -> $WANT, 2-5 daqiqa)..."
    python -m app.seed
    echo "$WANT" > "$DATA/.seed_version"
  fi
fi
# Telegram bot shu jarayon ichida ishlaydi (TELEGRAM_BOT_TOKEN bo'lsa) — alohida jarayon kerak emas.
# Bo'limlar kaliti va namoyish sozlamalari (docs/modullar.md):
#   ISFT_CORE_MODULES="+moliya,-testbank"  bo'limlarni yoqish/o'chirish (sahifadagi «Bo'limlar»dan ustun)
#   ISFT_CORE_CAM_SIM=1                    kamera simulyatori (standart: o'chiq — fon so'rovchisi va avtomatik arizalar yo'q)
#   ISFT_CORE_REAL_DATA=1                  «Namuna ma'lumot» tasmasi ko'rsatilmaydi (HEMIS/NEXTID ulangach)
#   ISFT_CORE_SHOW_DEMO_PASSWORD=1         kirish sahifasida sinov paroli va ismlar (faqat namoyish)
# Proksi: --forwarded-allow-ips='*' sxema (https) uchun kerak; mijoz IP manzilini ilova o'zi X-Forwarded-For ning o'ngdan
# ISFT_CORE_TRUSTED_PROXIES-chi (standart 1 — Railway) qiymatidan oladi — urinishlar cheklovini sarlavha bilan chetlab o'tib bo'lmaydi.
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}" --proxy-headers --forwarded-allow-ips='*'
