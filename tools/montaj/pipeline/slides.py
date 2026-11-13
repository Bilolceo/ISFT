"""5-qadam: slayd sinxronizatsiyasi.

PDF sahifalari rasmga aylantiriladi (pypdfium2), har sahifa matni olinadi; transkript gaplari
sahifalarga TF-IDF o'xshashligi bo'yicha monoton dinamik dasturlash bilan moslanadi
(indeks kamaymaydi, 1 qadam ortga qaytishga ruxsat, "slaydsiz" holat ham bor).
"""
from __future__ import annotations

import math
import re
from collections import Counter
from pathlib import Path

from .common import log
from .edl import norm_token

STOP = set("""
va bu bir ham uchun bilan deb esa yoki lekin endi biz siz ular u men sen bu shu ana mana kabi agar
qanday nima qachon qayerda yana juda eng har hech emas bor yoq edi ekan bo'ladi boladi qiladi kerak
и в во не что он на я с со как а то все она так его но да ты к у же вы за бы по только ее мне было
вот от меня еще нет о из ему теперь когда даже ну вдруг ли если уже или ни быть был него до вас это
the a an and or of to in on for is are was were be been with as at by it this that we you they from
let us our will can now so then about into than all also
""".split())


def stem(tok: str) -> str:
    return tok[:6] if len(tok) > 6 else tok


def content_tokens(text: str) -> list[str]:
    out = []
    for raw in re.split(r"\s+", text):
        t = norm_token(raw)
        if len(t) < 3 or t.isdigit() or t in STOP:
            continue
        out.append(stem(t))
    return out


# ---------------------------------------------------------------- PDF
def read_pdf(pdf: Path) -> list[str]:
    import pypdfium2 as pdfium
    doc = pdfium.PdfDocument(str(pdf))
    texts = []
    for i in range(len(doc)):
        page = doc[i]
        tp = page.get_textpage()
        texts.append(tp.get_text_range() or "")
        tp.close()
        page.close()
    doc.close()
    return texts


def render_pages(pdf: Path, out_dir: Path, box: tuple[int, int]) -> list:
    """Har sahifani `box` ichiga sig'adigan PIL rasmga aylantiradi."""
    import pypdfium2 as pdfium
    doc = pdfium.PdfDocument(str(pdf))
    imgs = []
    for i in range(len(doc)):
        page = doc[i]
        pw, ph = page.get_size()
        scale = min(box[0] / pw, box[1] / ph) * 1.0
        img = page.render(scale=scale * 2, draw_annots=True).to_pil().convert("RGB")  # 2x — keyin kichraytiriladi (tiniq)
        tw, th = max(1, int(pw * scale)), max(1, int(ph * scale))
        from PIL import Image
        imgs.append(img.resize((tw, th), Image.LANCZOS))
        page.close()
    doc.close()
    return imgs


def page_heading(text: str) -> str:
    for line in text.splitlines():
        line = line.strip()
        if len(line) >= 3:
            return line
    return ""


# ---------------------------------------------------------------- moslash
def _tfidf(docs_tokens: list[list[str]], idf: dict) -> list[dict]:
    vecs = []
    for toks in docs_tokens:
        c = Counter(toks)
        v = {t: (1 + math.log(n)) * idf.get(t, 0.0) for t, n in c.items()}
        norm = math.sqrt(sum(x * x for x in v.values())) or 1.0
        vecs.append({t: x / norm for t, x in v.items()})
    return vecs


def _cos(a: dict, b: dict) -> float:
    if len(a) > len(b):
        a, b = b, a
    return sum(x * b.get(t, 0.0) for t, x in a.items())


def similarity_matrix(unit_texts: list[str], page_texts: list[str], context: int = 1) -> list[list[float]]:
    pages_tok = [content_tokens(t) for t in page_texts]
    units_tok = [content_tokens(t) for t in unit_texts]
    n = len(pages_tok)
    df = Counter(t for toks in pages_tok for t in set(toks))
    idf = {t: math.log((n + 1) / (d + 0.5)) + 0.2 for t, d in df.items()}
    pv = _tfidf(pages_tok, idf)
    # kontekst: qo'shni gaplar ham qo'shiladi (qisqa gaplar uchun barqarorlik)
    ctx = []
    for i in range(len(units_tok)):
        toks = list(units_tok[i])
        for j in range(max(0, i - context), min(len(units_tok), i + context + 1)):
            if j != i:
                toks += units_tok[j]
        ctx.append(toks)
    uv = _tfidf(ctx, idf)
    return [[_cos(u, p) for p in pv] for u in uv]


def align(sim: list[list[float]], *, none_score: float = 0.06, fwd_pen: float = 0.04, skip_pen: float = 0.08,
          back_pen: float = 0.25, none_pen: float = 0.15) -> list[int]:
    """Viterbi: holatlar 0..N-1 (slayd) va N ("slaydsiz"). Qaytaradi: har gap uchun holat (−1 = slaydsiz)."""
    if not sim:
        return []
    n = len(sim[0])
    NONE = n
    NEG = -1e9

    def trans(a, b):
        if a == b:
            return 0.0
        if a == NONE or b == NONE:
            return -none_pen
        d = b - a
        if d == 1:
            return -fwd_pen
        if d > 1:
            return -fwd_pen - skip_pen * (d - 1)
        if d == -1:
            return -back_pen
        return NEG

    def emit(u, s):
        return none_score if s == NONE else sim[u][s]

    score = [(-0.03 * s if s != NONE else 0.0) + emit(0, s) for s in range(n + 1)]
    back = []
    for u in range(1, len(sim)):
        new, bp = [], []
        for s in range(n + 1):
            best, arg = NEG, 0
            for r in range(n + 1):
                v = score[r] + trans(r, s)
                if v > best:
                    best, arg = v, r
            new.append(best + emit(u, s))
            bp.append(arg)
        score, back = new, back + [bp]
    s = max(range(n + 1), key=lambda k: score[k])
    path = [s]
    for bp in reversed(back):
        s = bp[s]
        path.append(s)
    path.reverse()
    return [-1 if s == NONE else s for s in path]


def enforce_dwell(spans: list[tuple[float, float, int]], min_dwell: float) -> list[tuple[float, float, int]]:
    """Juda qisqa ko'rsatilgan slaydlarni qo'shnisiga qo'shib yuboradi. spans: (start, end, slayd)."""
    spans = [list(s) for s in spans]
    while len(spans) > 1:
        k = min(range(len(spans)), key=lambda i: spans[i][1] - spans[i][0])
        if spans[k][1] - spans[k][0] >= min_dwell:
            break
        if k == 0:
            spans[1][0] = spans[0][0]
            del spans[0]
        else:
            spans[k - 1][1] = spans[k][1]
            del spans[k]
        # bir xil qo'shnilarni birlashtirish
        i = 0
        while i < len(spans) - 1:
            if spans[i][2] == spans[i + 1][2]:
                spans[i][1] = spans[i + 1][1]
                del spans[i + 1]
            else:
                i += 1
    return [tuple(s) for s in spans]


def sync_slides(units: list[dict], page_texts: list[str], main_duration: float,
                min_dwell: float = 6.0) -> tuple[list[tuple[float, float, int]], list[str]]:
    """units: chiqish vaqtidagi gaplar [{start,end,text}] (asosiy qism boshi = 0).

    Qaytaradi: (spans [(start, end, slayd_indeks | -1)], ogohlantirishlar)."""
    warnings = []
    n = len(page_texts)
    if n == 0:
        return [], warnings
    has_text = sum(1 for t in page_texts if len(content_tokens(t)) >= 2)
    if has_text < max(1, n // 2) or not units:
        warnings.append("Slaydlarda matn kam — slaydlar vaqt bo'yicha teng taqsimlandi, operator tekshirsin")
        step = main_duration / n
        return [(i * step, (i + 1) * step if i < n - 1 else main_duration, i) for i in range(n)], warnings
    sim = similarity_matrix([u["text"] for u in units], page_texts)
    path = align(sim)
    spans: list[list] = []
    for u, s in zip(units, path):
        if spans and spans[-1][2] == s:
            continue
        spans.append([u["start"], None, s])
    for i in range(len(spans)):
        spans[i][1] = spans[i + 1][0] if i + 1 < len(spans) else main_duration
    spans[0][0] = 0.0
    # slayd o'zgarishi gap boshidan biroz oldin (o'qituvchi avval slaydni almashtiradi)
    for i in range(1, len(spans)):
        t = max(spans[i - 1][0] + 0.5, spans[i][0] - 0.3)
        spans[i - 1][1] = t
        spans[i][0] = t
    out = enforce_dwell([tuple(s) for s in spans], min_dwell)
    matched = sorted({s for _, _, s in out if s >= 0})
    if len(matched) < max(1, n // 2):
        warnings.append(f"Slaydlarning faqat {len(matched)}/{n} tasi nutqqa mos topildi — operator tekshirsin")
    log.info("Slaydlar: %s", ", ".join(f"{a:.1f}s→{s + 1 if s >= 0 else '—'}" for a, _, s in out))
    return out, warnings
