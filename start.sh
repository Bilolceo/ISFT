#!/bin/sh
set -e
cd "$(dirname "$0")"
mkdir -p data
# Baza yo'q yoki seed versiyasi o'zgargan (tuzilma/rollar yangilangan) bo'lsa — demo ma'lumotlar qayta yaratiladi.
WANT="$(cat SEED_VERSION 2>/dev/null || echo 0)"
HAVE="$(cat data/.seed_version 2>/dev/null || echo none)"
if [ ! -f data/jarvis.db ] || [ "$WANT" != "$HAVE" ]; then
  echo "Demo ma'lumotlar yaratilmoqda (seed: $HAVE -> $WANT)..."
  python -m app.seed
  echo "$WANT" > data/.seed_version
fi
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}" --proxy-headers --forwarded-allow-ips='*'
