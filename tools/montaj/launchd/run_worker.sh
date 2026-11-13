#!/bin/sh
# ISFT montaj worker'ini ishga tushiruvchi (launchd shu skriptni chaqiradi).
# Sozlamalar: ~/.config/isft-montaj/worker.env (chmod 600), masalan:
#   ISFT_CORE_API=https://core.example.uz
#   ISFT_CORE_WORKER_TOKEN=...
#   MONTAJ_VENV=$HOME/.local/montaj-venv          (ixtiyoriy)
#   MONTAJ_FFMPEG=$HOME/.local/bin/ffmpeg         (ixtiyoriy; yo'q bo'lsa imageio-ffmpeg)
#   MONTAJ_WORK_DIR=$HOME/Library/Caches/isft-montaj (ixtiyoriy)
set -e
ENV_FILE="${MONTAJ_ENV_FILE:-$HOME/.config/isft-montaj/worker.env}"
if [ -f "$ENV_FILE" ]; then
    set -a
    . "$ENV_FILE"
    set +a
fi
: "${ISFT_CORE_API:?ISFT_CORE_API berilmagan ($ENV_FILE)}"
: "${ISFT_CORE_WORKER_TOKEN:?ISFT_CORE_WORKER_TOKEN berilmagan ($ENV_FILE)}"
VENV="${MONTAJ_VENV:-$HOME/.local/montaj-venv}"
WORK="${MONTAJ_WORK_DIR:-$HOME/Library/Caches/isft-montaj}"
HERE="$(cd "$(dirname "$0")/.." && pwd)"
export HF_HUB_OFFLINE="${HF_HUB_OFFLINE:-1}"   # whisper modeli lokal keshdan
exec "$VENV/bin/python" -u "$HERE/montaj.py" --worker --api "$ISFT_CORE_API" --work-dir "$WORK"
