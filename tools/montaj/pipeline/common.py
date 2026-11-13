"""Umumiy yordamchilar: ffmpeg yo'li, log, vaqt o'lchash, subprocess boshqaruvi."""
from __future__ import annotations

import json
import logging
import os
import re
import shutil
import signal
import subprocess
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path

log = logging.getLogger("montaj")

# Chiqish formati (barcha shablonlar uchun bir xil)
W, H = 1920, 1080
FPS = 30
SR = 48000  # audio namuna chastotasi
SAMPLES_PER_FRAME = SR // FPS  # 1600 — audio va video kadr chegaralari bir xil to'rda

# Brend ranglari
MAROON = (0x87, 0x00, 0x37)
MAROON_DARK = (0x6E, 0x00, 0x2D)
MAROON_SOFT = (0xF6, 0xE6, 0xED)
INK = (0x22, 0x14, 0x1A)       # asosiy matn rangi (to'q, iliq)
MUTED = (0x6B, 0x5A, 0x62)     # ikkinchi darajali matn
PAPER = (0xFA, 0xF7, 0xF8)     # fon (juda och, iliq)

TOOL_DIR = Path(__file__).resolve().parent.parent
REPO_DIR = TOOL_DIR.parent.parent
DEFAULT_LOGO = REPO_DIR / "static" / "brand" / "logo.png"
FONT_DIRS = ["/System/Library/Fonts/Supplemental", "/Library/Fonts", "/usr/share/fonts/truetype/msttcorefonts"]


class MontajError(RuntimeError):
    """Foydalanuvchiga ko'rsatiladigan xato (worker /fail ga yuboradi)."""


class Cancelled(MontajError):
    pass


def find_ffmpeg() -> str:
    cands = [os.environ.get("MONTAJ_FFMPEG"), str(Path.home() / ".local/bin/ffmpeg"), shutil.which("ffmpeg")]
    for c in cands:
        if c and Path(c).exists():
            return c
    try:  # zaxira: imageio-ffmpeg ichidagi statik binar
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception as e:  # pragma: no cover
        raise MontajError(f"ffmpeg topilmadi: {e}")


FFMPEG = find_ffmpeg()


def find_font(bold: bool = False) -> str:
    names = ["Arial Bold.ttf", "Arial-Bold.ttf", "DejaVuSans-Bold.ttf"] if bold else ["Arial.ttf", "DejaVuSans.ttf"]
    for d in FONT_DIRS:
        for n in names:
            p = Path(d) / n
            if p.exists():
                return str(p)
    raise MontajError("TTF shrift topilmadi (Arial kerak)")


# ---------------------------------------------------------------- bekor qilish
class CancelToken:
    """Worker SIGINT ni ikkinchi marta olganda ishlayotgan ffmpeg ni to'xtatadi."""

    def __init__(self):
        self._ev = threading.Event()
        self._procs: set[subprocess.Popen] = set()
        self._lock = threading.Lock()

    def cancel(self):
        self._ev.set()
        with self._lock:
            for p in list(self._procs):
                try:
                    p.send_signal(signal.SIGTERM)
                except Exception:
                    pass

    @property
    def cancelled(self) -> bool:
        return self._ev.is_set()

    def check(self):
        if self._ev.is_set():
            raise Cancelled("bekor qilindi")

    def add(self, p):
        with self._lock:
            self._procs.add(p)

    def remove(self, p):
        with self._lock:
            self._procs.discard(p)


NO_CANCEL = CancelToken()


def run_ffmpeg(args: list[str], *, cancel: CancelToken = NO_CANCEL, total: float | None = None,
               on_progress=None, desc: str = "ffmpeg") -> str:
    """ffmpeg ni ishga tushiradi; stderr ni qaytaradi; xato bo'lsa MontajError.

    total + on_progress berilsa, `-progress pipe:1` orqali foiz (0..1) uzatiladi.
    """
    cmd = [FFMPEG, "-hide_banner", "-nostdin", "-y"]
    if on_progress and total:
        cmd += ["-progress", "pipe:1", "-nostats"]
    cmd += args
    log.debug("%s: %s", desc, " ".join(cmd))
    cancel.check()
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE if (on_progress and total) else subprocess.DEVNULL,
                         stderr=subprocess.PIPE, text=True, errors="replace")
    cancel.add(p)
    err_chunks: list[str] = []

    def _drain():
        for line in p.stderr:
            err_chunks.append(line)
            if len(err_chunks) > 4000:
                del err_chunks[:2000]

    th = threading.Thread(target=_drain, daemon=True)
    th.start()
    try:
        if on_progress and total:
            last = 0.0
            for line in p.stdout:
                if line.startswith("out_time_us=") or line.startswith("out_time_ms="):
                    try:
                        us = int(line.split("=", 1)[1])
                    except ValueError:
                        continue
                    frac = max(0.0, min(1.0, us / 1e6 / total))
                    if frac - last >= 0.01:
                        last = frac
                        on_progress(frac)
        p.wait()
    finally:
        cancel.remove(p)
        th.join(timeout=5)
        for f in (p.stdout, p.stderr):
            if f:
                f.close()
    err = "".join(err_chunks)
    if cancel.cancelled:
        raise Cancelled("bekor qilindi")
    if p.returncode != 0:
        tail = "\n".join(err.strip().splitlines()[-15:])
        raise MontajError(f"{desc} xatosi (kod {p.returncode}):\n{tail}")
    return err


# ---------------------------------------------------------------- vaqt o'lchash
@dataclass
class Timings:
    data: dict = field(default_factory=dict)

    @contextmanager
    def step(self, name: str):
        t0 = time.perf_counter()
        log.info("▶ %s ...", name)
        try:
            yield
        finally:
            dt = time.perf_counter() - t0
            self.data[name] = round(self.data.get(name, 0.0) + dt, 2)
            log.info("✔ %s — %.1f s", name, dt)


def snap(t: float) -> float:
    """Vaqtni kadr to'riga (1/30 s) yaxlitlash."""
    return round(t * FPS) / FPS


def fmt_ts(t: float) -> str:
    """YouTube uslubidagi vaqt: 01:23 yoki 1:02:03."""
    t = int(max(0, t))
    h, rem = divmod(t, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def write_json(path: Path, obj):
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


_APOS_O_G = re.compile(r"(?<=[oOgG])['`‘’ʼ]")
_APOS_ANY = re.compile(r"['`ʼ‘]")


def uz_typography(s: str) -> str:
    """O'zbek apostroflarini to'g'ri belgiga almashtiradi: oʻ/gʻ → U+02BB, tutuq belgisi → ’ (U+2019)."""
    s = _APOS_O_G.sub("ʻ", s)
    s = _APOS_ANY.sub("’", s)
    return s
