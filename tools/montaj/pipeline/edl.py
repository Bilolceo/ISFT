"""4-qadam: tahrir qarorlari ro'yxati (EDL).

Kesish sabablari (report.json dagi `reason` kodlari):
  silence     — uzun sukunat (tabiiy 0.3–0.5 s pauza qoldiriladi)
  noise       — so'zlar orasidagi nutqsiz tovush (whisper tanimagan "eee", yo'tal va h.k.)
  filler      — faqat to'ldiruvchi so'zlardan iborat bo'lak (ee, hmm, mmm, ну, э ...)
  retake      — takroriy dubl: o'xshash ketma-ket gaplar → oxirgisi qoladi
  retake_cue  — "qaytadan", "stop", "kesib tashlang" kabi signal → oldingi gap boshigacha kesiladi
  tiny        — kesishlar orasida qolgan juda kichik so'zsiz bo'lak

Qoida: kesish chegarasi hech qachon so'z ichiga tushmaydi.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher

from .common import FPS

REASON_PRIORITY = {"retake_cue": 5, "retake": 4, "filler": 3, "noise": 2, "silence": 1, "tiny": 0}

FILLER_RE = re.compile(
    r"^(e+h*|ee+m*|ə+|a+h+|aa+|h+m+|m+h?m*|u+[mh]+|e+r+m*|o+h+|"
    r"э+|э+м+|м+|х+м+|м+х?м*|ну+|а+|ааа*|ммм*)$"
)

RETAKE_CUES = [
    "qaytadan", "yana bir bor", "boshidan", "kesib tashlang", "kesib tashla", "qayta olamiz", "stop",
    "заново", "ещё раз", "еще раз", "стоп", "сначала",
    "start again", "let me start again", "one more time",
]

_APOS = re.compile(r"[ʻʼ’‘'`]")
_NONWORD = re.compile(r"[^\w]+", re.U)


def norm_token(w: str) -> str:
    return _NONWORD.sub("", _APOS.sub("", w.lower()))


def is_filler(word: str) -> bool:
    t = norm_token(word)
    return bool(t) and bool(FILLER_RE.match(t))


@dataclass
class EdlParams:
    max_pause: float = 1.0      # bundan uzun sukunat kesiladi
    keep_pad: float = 0.4       # kesilgan sukunat chetida qoldiriladigan tabiiy pauza
    noise_gap: float = 1.2      # so'zlar orasidagi bundan uzun nutqsiz joy (ovozli bo'lsa ham) kesiladi
    unit_gap: float = 0.7       # gaplarni ajratish uchun pauza
    retake_sim: float = 0.8     # to'liq o'xshashlik chegarasi
    prefix_sim: float = 0.85    # "noto'g'ri boshlanish" (oldingi gap keyingisining boshi)
    retake_window: float = 25.0  # ikki dubl orasidagi maksimal vaqt
    min_cut: float = 0.3
    min_keep: float = 0.6
    conservative: bool = False  # faqat sukunat kesiladi (nutq aniqligi past bo'lganda)


@dataclass
class Unit:
    i0: int
    i1: int  # inklyuziv
    start: float
    end: float
    tokens: list = field(default_factory=list)
    text: str = ""
    filler_only: bool = False


def build_units(words: list[dict], unit_gap: float = 0.7) -> list[Unit]:
    """So'zlarni gaplarga ajratadi: tinish belgisi (. ? !) yoki uzun pauza bo'yicha."""
    units: list[Unit] = []
    i0 = 0
    for i, w in enumerate(words):
        last = i == len(words) - 1
        brk = last or w["word"].rstrip().endswith((".", "?", "!", "…")) or (words[i + 1]["start"] - w["end"] >= unit_gap)
        if brk:
            ws = words[i0:i + 1]
            toks = [norm_token(x["word"]) for x in ws]
            content = [t for t, x in zip(toks, ws) if t and not is_filler(x["word"])]
            units.append(Unit(i0, i, ws[0]["start"], ws[-1]["end"], content,
                              " ".join(x["word"] for x in ws), filler_only=not content))
            i0 = i + 1
    return units


def retake_similar(a: list[str], b: list[str], p: EdlParams) -> bool:
    if len(a) < 2 or len(b) < 2:
        return False
    if SequenceMatcher(None, a, b, autojunk=False).ratio() >= p.retake_sim:
        return True
    if len(a) >= 3 and len(a) <= len(b):  # noto'g'ri boshlanish: a ≈ b ning boshi
        if SequenceMatcher(None, a, b[:len(a)], autojunk=False).ratio() >= p.prefix_sim:
            return True
    return False


_CUE_TOKS = sorted(([norm_token(x) for x in c.split()] for c in RETAKE_CUES), key=len, reverse=True)
_CUE_CONT = {"again", "yana", "qaytadan", "заново", "ещё", "еще", "раз", "boshidan", "сначала"}


def match_cue(toks: list[str], i: int) -> int:
    """toks[i:] signal ibora bilan boshlansa — ibora uzunligi, aks holda 0."""
    for c in _CUE_TOKS:
        if toks[i:i + len(c)] == c:
            return len(c)
    return 0


def find_cues(words: list[dict], units: list[Unit]) -> list[dict]:
    """Qayta yozish signallari. Signal topilsa, kesiladigan gap aniqlanadi:
      - signaldan oldin shu gapda ≥2 so'z bo'lsa — shu gap boshi (chala gap + signal kesiladi);
      - aks holda — oldingi gap boshi.
    Xavfsizlik: signal alohida turgan qisqa gap bo'lishi YOKI keyingi gap kesilayotgan gap kabi
    boshlanishi (qayta urinish) kerak — oddiy nutqdagi "stop" kesilmaydi."""
    toks = [norm_token(w["word"]) for w in words]
    unit_of = {}
    for k, u in enumerate(units):
        for i in range(u.i0, u.i1 + 1):
            unit_of[i] = k
    out, i = [], 0
    while i < len(words):
        n = match_cue(toks, i)
        if not n:
            i += 1
            continue
        j = i + n
        while j < len(words) and (toks[j] in _CUE_CONT or match_cue(toks, j)):
            j += match_cue(toks, j) or 1
        k = unit_of[i]
        u = units[k]
        prefix = [toks[x] for x in range(u.i0, i) if toks[x] and not is_filler(words[x]["word"])]
        rest_in_unit = [toks[x] for x in range(j, u.i1 + 1) if toks[x] and not is_filler(words[x]["word"])]
        after = [t for t in toks[j:j + 12] if t]
        if len(prefix) >= 2:
            start_i, sentence = u.i0, prefix
        else:
            prev = next((units[m] for m in range(k - 1, -1, -1) if not units[m].filler_only), None)
            if prev is None:
                i = j
                continue
            start_i, sentence = prev.i0, prev.tokens
        standalone = len(prefix) <= 1 and len(rest_in_unit) <= 1
        restart = bool(sentence) and bool(after) and \
            SequenceMatcher(None, sentence[:4], after[:4], autojunk=False).ratio() >= 0.5
        if standalone or restart:
            out.append({"start_i": start_i, "end_i": j})
        i = j
    return out


# ---------------------------------------------------------------- interval yordamchilari
def subtract(iv: tuple[float, float], holes: list[tuple[float, float]]) -> list[tuple[float, float]]:
    out = [iv]
    for hs, he in holes:
        nxt = []
        for s, e in out:
            if he <= s or hs >= e:
                nxt.append((s, e))
                continue
            if hs > s:
                nxt.append((s, hs))
            if he < e:
                nxt.append((he, e))
        out = nxt
    return out


def merge_cuts(cuts: list[dict], join_gap: float = 0.05) -> list[dict]:
    cuts = sorted((c for c in cuts if c["end"] - c["start"] > 1e-6), key=lambda c: c["start"])
    out: list[dict] = []
    for c in cuts:
        if out and c["start"] <= out[-1]["end"] + join_gap:
            o = out[-1]
            o["end"] = max(o["end"], c["end"])
            if REASON_PRIORITY[c["reason"]] > REASON_PRIORITY[o["reason"]]:
                o["reason"] = c["reason"]
        else:
            out.append(dict(c))
    return out


def inside_word(t: float, words: list[dict], eps: float = 1e-6) -> dict | None:
    for w in words:  # so'zlar kam emas, lekin chegaralar soni ham kam — oddiy qidiruv yetarli
        if w["start"] + eps < t < w["end"] - eps:
            return w
    return None


def _word_index(words):
    """Tez qidirish uchun boshlanish vaqtlari ro'yxati."""
    import bisect
    starts = [w["start"] for w in words]

    def find(t, eps=1e-6):
        i = bisect.bisect_right(starts, t) - 1
        for j in (i, i - 1):
            if 0 <= j < len(words) and words[j]["start"] + eps < t < words[j]["end"] - eps:
                return words[j]
        return None
    return find


def keeps_from_cuts(cuts: list[dict], duration: float) -> list[tuple[float, float]]:
    keeps, t = [], 0.0
    for c in cuts:
        if c["start"] > t:
            keeps.append((t, c["start"]))
        t = max(t, c["end"])
    if t < duration:
        keeps.append((t, duration))
    return keeps


# ---------------------------------------------------------------- asosiy funksiya
def build_edl(words: list[dict], silences: list[tuple[float, float]], duration: float,
              params: EdlParams | None = None) -> dict:
    p = params or EdlParams()
    words = sorted((w for w in words if w["end"] > w["start"] - 1e-9), key=lambda w: w["start"])
    find_in_word = _word_index(words)
    word_iv = [(w["start"], w["end"]) for w in words]
    import bisect
    starts_sorted = [w["start"] for w in words]
    ends_sorted = sorted(w["end"] for w in words)
    cuts: list[dict] = []

    # 1) Sukunatlar (audio bo'yicha) — har ikki chetida tabiiy pauza qoldiriladi
    for s, e in silences:
        if e - s < p.max_pause:
            continue
        a = 0.0 if s <= 0.05 else s + p.keep_pad
        b = duration if e >= duration - 0.05 else e - p.keep_pad
        if s <= 0.05:
            b = e - min(p.keep_pad, 0.3)
        lo = bisect.bisect_left(ends_sorted, a)
        hi = bisect.bisect_right(starts_sorted, b)
        for x, y in subtract((a, b), word_iv[max(0, lo - 2):hi + 2]):
            cuts.append({"start": x, "end": y, "reason": "silence"})

    units = build_units(words, p.unit_gap) if words else []
    if not p.conservative and words:
        sil = silences

        def silent_frac(a, b):
            tot = sum(max(0.0, min(b, e) - max(a, s)) for s, e in sil)
            return tot / max(1e-6, b - a)

        # 2) So'zlar orasidagi uzun bo'shliqlar (nutqsiz tovush yoki sukunat)
        gaps = [(0.0, words[0]["start"])] + [(words[i]["end"], words[i + 1]["start"]) for i in range(len(words) - 1)] \
            + [(words[-1]["end"], duration)]
        for gi, (s, e) in enumerate(gaps):
            if e - s < p.noise_gap:
                continue
            a = 0.0 if gi == 0 else s + p.keep_pad
            b = duration if gi == len(gaps) - 1 else e - p.keep_pad
            if b - a > 0:
                cuts.append({"start": a, "end": b, "reason": "silence" if silent_frac(s, e) >= 0.6 else "noise"})

        # 3) To'ldiruvchi so'zlar ketma-ketligi (pauzalar bilan ajralgan)
        i = 0
        while i < len(words):
            if not is_filler(words[i]["word"]):
                i += 1
                continue
            j = i
            while j + 1 < len(words) and is_filler(words[j + 1]["word"]):
                j += 1
            prev_end = words[i - 1]["end"] if i > 0 else 0.0
            next_start = words[j + 1]["start"] if j + 1 < len(words) else duration
            g1, g2 = words[i]["start"] - prev_end, next_start - words[j]["end"]
            if (g1 >= 0.12 or i == 0) and (g2 >= 0.12 or j == len(words) - 1):
                a = prev_end + min(0.25, g1 / 2) if i > 0 else 0.0
                b = next_start - min(0.25, g2 / 2) if j + 1 < len(words) else duration
                cuts.append({"start": a, "end": b, "reason": "filler"})
            i = j + 1

        # 4) Dubllar (takroriy gaplar) va qayta yozish signallari
        def before_i(i: int) -> float:
            pe = words[i - 1]["end"] if i > 0 else 0.0
            return words[i]["start"] - min(0.2, max(0.0, words[i]["start"] - pe) / 2)

        cue_words = set()
        for c in find_cues(words, units):
            a = before_i(c["start_i"])
            b = before_i(c["end_i"]) if c["end_i"] < len(words) else min(duration, words[-1]["end"] + 0.3)
            if words[c["end_i"] - 1]["end"] - words[c["start_i"]]["start"] <= p.retake_window * 2:
                cuts.append({"start": a, "end": b, "reason": "retake_cue"})
                cue_words.update(range(c["start_i"], c["end_i"]))

        content = [u for u in units if not u.filler_only]
        for k, u in enumerate(content[:-1]):
            nxt = content[k + 1]
            if u.i0 in cue_words or nxt.i0 in cue_words:
                continue
            if nxt.start - u.end < p.retake_window and retake_similar(u.tokens, nxt.tokens, p):
                cuts.append({"start": before_i(u.i0), "end": before_i(nxt.i0), "reason": "retake"})

    cuts = merge_cuts(cuts)

    # 5) Chegaralar so'z ichiga tushmasligi
    fixed = []
    for c in cuts:
        w = find_in_word(c["start"])
        if w:
            c["start"] = w["end"]
        w = find_in_word(c["end"])
        if w:
            c["end"] = w["start"]
        if c["end"] - c["start"] > 1e-3:
            fixed.append(c)
    cuts = merge_cuts(fixed)

    # 6) Kichik so'zsiz bo'laklarni yutib yuborish (bir o'tishda, bisect bilan)
    import bisect
    starts = [w["start"] for w in words]

    def has_word(a, b):
        i = bisect.bisect_left(starts, a - 1e-6)
        return i < len(words) and words[i]["start"] <= b + 1e-6 and any(
            words[j]["end"] <= b + 1e-6 for j in range(i, min(len(words), i + 3)) if words[j]["start"] >= a - 1e-6)

    merged: list[dict] = []
    for c in cuts:
        if merged:
            a, b = merged[-1]["end"], c["start"]
            if b - a < p.min_keep and not has_word(a, b):
                o = merged[-1]
                o["end"] = max(o["end"], c["end"])
                if REASON_PRIORITY[c["reason"]] > REASON_PRIORITY[o["reason"]]:
                    o["reason"] = c["reason"]
                continue
        merged.append(dict(c))
    cuts = merged
    cuts = [c for c in cuts if c["end"] - c["start"] >= p.min_cut]

    # 7) Kadr to'riga moslash (chegara so'z ichiga tushmaydigan yo'nalishda)
    snapped = []
    for c in cuts:
        s = _snap_boundary(c["start"], find_in_word, prefer="ceil")
        e = _snap_boundary(c["end"], find_in_word, prefer="floor")
        e = min(e, math.floor(duration * FPS) / FPS) if c["end"] < duration - 1e-6 else math.floor(duration * FPS) / FPS
        if e - s >= 1.0 / FPS:
            snapped.append({"start": round(s, 4), "end": round(e, 4), "reason": c["reason"]})
    cuts = merge_cuts(snapped, join_gap=0.0)
    total_frames = math.floor(duration * FPS)
    keeps = [(round(a, 4), round(b, 4)) for a, b in keeps_from_cuts(cuts, total_frames / FPS) if b - a >= 1.0 / FPS - 1e-9]
    kept = sum(b - a for a, b in keeps)
    return {"cuts": cuts, "keeps": keeps, "duration_in": round(duration, 3), "duration_kept": round(kept, 3),
            "units": [{"start": u.start, "end": u.end, "text": u.text, "filler_only": u.filler_only} for u in units],
            "conservative": p.conservative}


def _snap_boundary(t: float, find_in_word, prefer: str) -> float:
    lo, hi = math.floor(t * FPS + 1e-9) / FPS, math.ceil(t * FPS - 1e-9) / FPS
    order = [hi, lo] if prefer == "ceil" else [lo, hi]
    for c in order:
        if not find_in_word(c):
            return c
    # ikkala nuqta ham so'z ichida (so'zlar orasida bo'shliq yo'q) — asl chegaraga eng yaqini (< 1 kadr)
    return min(order, key=lambda c: abs(c - t))


def refine_words(words: list[dict], env, hop: float = 0.02, max_ext: float = 0.35) -> list[dict]:
    """Whisper so'z chegaralari ko'pincha 0.1–0.3 s noaniq. Audio energiyasi bo'yicha so'z oxirini
    (keyingi so'zgacha) ovoz davom etayotgan joygacha cho'zamiz, boshini esa ortga — shunda kesish
    so'z "dumini" qoldirmaydi. Faqat kengaytiradi (xavfsiz yo'nalish)."""
    import numpy as np
    if env is None or len(env) == 0 or not words:
        return words
    floor = float(np.percentile(env, 15))
    thr = max(floor + 10.0, -55.0)

    def voiced(t):
        i = int(t / hop)
        return 0 <= i < len(env) and env[i] > thr

    out = [dict(w) for w in words]
    for i, w in enumerate(out):
        nxt = out[i + 1]["start"] if i + 1 < len(out) else w["end"] + max_ext
        lim = min(w["end"] + max_ext, nxt - 0.02)
        e = w["end"]
        while e + hop <= lim and voiced(e):
            e += hop
        w["end"] = round(max(w["end"], e), 3)
        prv = out[i - 1]["end"] if i > 0 else max(0.0, w["start"] - max_ext)
        lim = max(w["start"] - max_ext, prv + 0.02)
        s = w["start"]
        while s - hop >= lim and voiced(s - hop):
            s -= hop
        w["start"] = round(min(w["start"], s), 3)
    return out


# ---------------------------------------------------------------- vaqt xaritasi (kirish → chiqish)
class TimeMap:
    """Kirish vaqtini (xom yozuv) chiqish vaqtiga o'tkazadi. offset — intro uzunligi (xfade hisobga olingan)."""

    def __init__(self, keeps: list[tuple[float, float]], offset: float = 0.0):
        self.keeps = keeps
        self.offset = offset
        self.out_starts = []
        acc = 0.0
        for a, b in keeps:
            self.out_starts.append(acc)
            acc += b - a
        self.main_duration = acc
        self._starts = [a for a, _ in keeps]

    def _idx(self, t: float) -> int:
        import bisect
        return bisect.bisect_right(self._starts, t + 1e-6) - 1

    def to_out(self, t: float) -> float | None:
        i = self._idx(t)
        for j in (i, i + 1):
            if 0 <= j < len(self.keeps):
                a, b = self.keeps[j]
                if a - 1e-6 <= t <= b + 1e-6:
                    return self.offset + self.out_starts[j] + (min(max(t, a), b) - a)
        return None

    def to_out_clamped(self, t: float) -> float:
        """Kesilgan joydagi vaqt → keyingi saqlangan bo'lak boshi."""
        i = max(0, self._idx(t))
        for j in range(i, len(self.keeps)):
            a, b = self.keeps[j]
            if t <= b + 1e-6:
                return self.offset + self.out_starts[j] + max(0.0, t - a)
        return self.offset + self.main_duration

    def word_kept(self, w: dict) -> bool:
        i = max(0, self._idx(w["start"]))
        return any(a - 1e-3 <= w["start"] and w["end"] <= b + 1e-3
                   for a, b in self.keeps[max(0, i - 1):i + 2])
