"""7-qadam: subtitrlar — kesishlardan keyin qayta vaqtlangan WebVTT (2 qator × 42 belgi) va ASS (burn-in)."""
from __future__ import annotations

from .common import uz_typography
from .edl import TimeMap, is_filler

MAX_LINE = 42
MAX_LINES = 2
MAX_CUE_DUR = 6.0


def wrap_lines(text: str, width: int = MAX_LINE) -> list[str]:
    """Muvozanatli bo'lish: 1 qatorga sig'sa — 1 qator, aks holda o'rtaga yaqin bo'shliqdan."""
    text = " ".join(text.split())
    if len(text) <= width:
        return [text]
    words = text.split(" ")
    best, best_cost = None, None
    for i in range(1, len(words)):
        a, b = " ".join(words[:i]), " ".join(words[i:])
        if len(a) > width or len(b) > width:
            continue
        cost = abs(len(a) - len(b))
        if best_cost is None or cost < best_cost:
            best, best_cost = [a, b], cost
    if best:
        return best
    # sig'masa — ochko'z bo'lish (chaqiruvchi buni oldini oladi)
    lines, cur = [], ""
    for w in words:
        if cur and len(cur) + 1 + len(w) > width:
            lines.append(cur)
            cur = w
        else:
            cur = f"{cur} {w}".strip()
    lines.append(cur)
    return lines


def build_cues(words: list[dict], tmap: TimeMap) -> list[dict]:
    """Saqlangan so'zlardan subtitr bo'laklari: [{start,end,lines}] chiqish vaqtida."""
    kept = []
    for w in words:
        if not tmap.word_kept(w) or is_filler(w["word"]):
            continue
        a, b = tmap.to_out(w["start"]), tmap.to_out(w["end"])
        if a is None or b is None:
            continue
        kept.append({"start": a, "end": max(b, a + 0.05), "word": w["word"].strip(), "in_start": w["start"]})
    cues, cur = [], []

    def flush():
        if not cur:
            return
        text = " ".join(x["word"] for x in cur)
        cues.append({"start": cur[0]["start"], "end": cur[-1]["end"], "text": text})
        cur.clear()

    for w in kept:
        if cur:
            text = " ".join(x["word"] for x in cur + [w])
            gap = w["start"] - cur[-1]["end"]
            jumped = w["in_start"] - cur[-1]["in_start"] > (w["start"] - cur[-1]["start"]) + 0.2  # orada kesish bor
            fits = len(wrap_lines(text)) <= MAX_LINES and all(len(l) <= MAX_LINE for l in wrap_lines(text))
            if (not fits or gap > 0.8 or jumped or w["end"] - cur[0]["start"] > MAX_CUE_DUR
                    or cur[-1]["word"].endswith((".", "?", "!")) and len(" ".join(x["word"] for x in cur)) > 20):
                flush()
        cur.append(w)
    flush()
    # vaqtlarni tozalash: ustma-ust tushmasin, minimal 0.8 s ko'rinsin
    for i, c in enumerate(cues):
        nxt = cues[i + 1]["start"] if i + 1 < len(cues) else None
        end = max(c["end"] + 0.25, c["start"] + 0.8)
        if nxt is not None:
            end = min(end, nxt - 0.02)
        c["end"] = max(end, c["start"] + 0.3)
        c["lines"] = wrap_lines(uz_typography(c["text"]))
    return cues


def _ts(t: float, sep: str = ".") -> str:
    ms = int(round(t * 1000))
    h, ms = divmod(ms, 3600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d}{sep}{ms:03d}"


def to_vtt(cues: list[dict]) -> str:
    out = ["WEBVTT", ""]
    for i, c in enumerate(cues, 1):
        out += [str(i), f"{_ts(c['start'])} --> {_ts(c['end'])}", *c["lines"], ""]
    return "\n".join(out)


def to_ass(cues: list[dict], *, offset: float = 0.0, margin_l: int = 60, margin_r: int = 60, margin_v: int = 48,
           font: str = "Arial", size: int = 40) -> str:
    """Burn-in uchun ASS. offset — cue vaqtidan ayiriladi (asosiy qism vaqtiga o'tkazish)."""

    def ts(t):
        t = max(0.0, t)
        cs = int(round(t * 100))
        h, cs = divmod(cs, 360000)
        m, cs = divmod(cs, 6000)
        s, cs = divmod(cs, 100)
        return f"{h}:{m:02d}:{s:02d}.{cs:02d}"

    head = f"""[Script Info]
ScriptType: v4.00+
PlayResX: 1920
PlayResY: 1080
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{font},{size},&H00FFFFFF,&H00FFFFFF,&H6014141A,&H6014141A,0,0,0,0,100,100,0,0,3,10,0,2,{margin_l},{margin_r},{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines = []
    for c in cues:
        a, b = c["start"] - offset, c["end"] - offset
        if b <= 0:
            continue
        text = "\\N".join(l.replace("{", "(").replace("}", ")") for l in c["lines"])
        lines.append(f"Dialogue: 0,{ts(a)},{ts(b)},Default,,0,0,0,,{text}")
    return head + "\n".join(lines) + "\n"
