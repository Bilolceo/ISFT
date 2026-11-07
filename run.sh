#!/bin/zsh
# JARVIS MVP ishga tushirish
cd "$(dirname "$0")"
[ -d .venv ] || { python3 -m venv .venv && .venv/bin/pip install -q -r requirements.txt; }
[ -f data/jarvis.db ] || .venv/bin/python -m app.seed
pgrep -x ollama >/dev/null || (ollama serve >/dev/null 2>&1 &)
if [ -n "$TELEGRAM_BOT_TOKEN" ]; then .venv/bin/python -m app.bot & fi
echo "JARVIS: http://localhost:8000"
exec .venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
