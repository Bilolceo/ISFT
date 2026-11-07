#!/bin/sh
# Bulutda (Railway) ishga tushirish: baza yo'q bo'lsa demo ma'lumotlar yaratiladi (~2–3 daqiqa), so'ng server.
# Lokal AI (Ollama) bulutda yo'q — chat va bayonnoma tahlili qoidaga asoslangan zaxira rejimda ishlaydi.
set -e
cd "$(dirname "$0")"
mkdir -p data
if [ ! -f data/jarvis.db ]; then echo "Baza yo'q — demo ma'lumotlar yaratilmoqda..."; python -m app.seed; fi
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}" --proxy-headers --forwarded-allow-ips='*'
