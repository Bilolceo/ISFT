#!/bin/zsh
# ISFT Core MVP ishga tushirish
cd "$(dirname "$0")"
[ -d .venv ] || { python3 -m venv .venv && .venv/bin/pip install -q -r requirements.txt; }
# baza yo'q yoki seed versiyasi o'zgargan bo'lsa — demo ma'lumotlar qayta yaratiladi (start.sh bilan bir xil qoida)
DATA="${ISFT_CORE_DATA_DIR:-data}"; DB="${ISFT_CORE_DB:-$DATA/jarvis.db}"
WANT="$(cat SEED_VERSION 2>/dev/null || echo 0)"; HAVE="$(cat "$DATA/.seed_version" 2>/dev/null || echo none)"
if [ ! -f "$DB" ] || [ "$WANT" != "$HAVE" ]; then .venv/bin/python -m app.seed && echo "$WANT" > "$DATA/.seed_version"; fi
pgrep -x ollama >/dev/null || (ollama serve >/dev/null 2>&1 &)
# Telegram bot: TELEGRAM_BOT_TOKEN bo'lsa veb-jarayon ichida o'zi ishga tushadi (alohida `python -m app.bot` shart emas)
echo "ISFT Core: http://localhost:8000"
exec .venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
