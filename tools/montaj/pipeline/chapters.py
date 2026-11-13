"""Boblar (chapters): reja bandlari chegaralari.

1) Reja bandiga mos sarlavhali slayd birinchi marta ko'rsatilgan vaqt;
2) aks holda — transkriptda reja bandi so'zlari eng ko'p uchragan gap (monoton);
3) topilmasa — qo'shni ma'lum chegaralar orasida teng taqsimlanadi.
Barcha vaqtlar asosiy qism (main) vaqtida; YouTube talabi: birinchisi 00:00, oraliq ≥ 10 s.
"""
from __future__ import annotations

import re

from .slides import content_tokens, page_heading

MIN_GAP = 10.0


def clean_plan_item(s: str) -> str:
    return re.sub(r"^\s*(\d+[\.\)]|[-•*])\s*", "", s).strip()


def _coverage(item_toks: list[str], toks: list[str]) -> float:
    if not item_toks:
        return 0.0
    st = set(toks)
    return sum(1 for t in set(item_toks) if t in st) / len(set(item_toks))


def find_chapter_times(plan: list[str], main_duration: float, units: list[dict] | None = None,
                       slide_spans: list[tuple[float, float, int]] | None = None,
                       page_texts: list[str] | None = None) -> list[float | None]:
    """Har reja bandi uchun boshlanish vaqti (main vaqtida). units: [{start,end,text}] (main vaqtida)."""
    items = [content_tokens(clean_plan_item(p)) for p in plan]
    times: list[float | None] = [None] * len(plan)
    last = -1.0
    for k, it in enumerate(items):
        t_found = None
        # 1) slayd sarlavhasi orqali
        if slide_spans and page_texts:
            for a, _, s in slide_spans:
                if s < 0 or a <= last:
                    continue
                head = content_tokens(page_heading(page_texts[s]))
                cov_h = _coverage(it, head)
                cov_p = _coverage(it, content_tokens(page_texts[s]))
                if cov_h >= 0.6 or (cov_p >= 0.8 and len(it) >= 2):
                    t_found = a
                    break
        # 2) transkript orqali: gapning o'zi band so'zlarini qamrashi kerak; boshqa bandlarni ham
        #    qamragan "reja e'loni" gaplari jarimalanadi
        if t_found is None and units:
            best, best_t = 0.0, None
            for i, u in enumerate(units):
                if u["start"] <= last:
                    continue
                own = content_tokens(u["text"])
                cov = _coverage(it, own)
                if cov < 0.5:
                    continue
                win = _coverage(it, content_tokens(" ".join(x["text"] for x in units[i:i + 2])))
                other = max((_coverage(o, own) for j, o in enumerate(items) if j != k and o), default=0.0)
                score = cov + 0.25 * win - 0.6 * other
                if score > best + 1e-9:
                    best, best_t = score, u["start"]
            if best >= 0.5:
                t_found = best_t
        if t_found is not None:
            times[k] = t_found
            last = t_found
    # 3) topilmaganlarni interpolyatsiya
    n = len(times)
    for k in range(n):
        if times[k] is not None:
            continue
        lo_k = max((j for j in range(k) if times[j] is not None), default=None)
        hi_k = min((j for j in range(k + 1, n) if times[j] is not None), default=None)
        lo_t = times[lo_k] if lo_k is not None else 0.0
        hi_t = times[hi_k] if hi_k is not None else main_duration
        lo_i = lo_k if lo_k is not None else -1
        hi_i = hi_k if hi_k is not None else n
        times[k] = lo_t + (hi_t - lo_t) * (k - lo_i) / (hi_i - lo_i)
    return times


def build_chapters(plan: list[str], times: list[float], main_offset: float, main_duration: float,
                   intro_title: str = "Kirish") -> list[dict]:
    """Chiqish vaqtidagi boblar: [{"start","title"}], birinchisi 0 da, oraliq ≥ 10 s."""
    ch = [{"start": 0.0, "title": intro_title}]
    for p, t in zip(plan, times):
        title = clean_plan_item(p)
        if not title:
            continue
        st = round(main_offset + max(0.0, t), 2)
        if st < MIN_GAP:  # birinchi band boshida — "Kirish" o'rniga
            if len(ch) == 1 and ch[0]["title"] == intro_title:
                ch[0] = {"start": 0.0, "title": title}
                continue
        if st - ch[-1]["start"] < MIN_GAP:
            st = ch[-1]["start"] + MIN_GAP
        if st > main_offset + main_duration - 5:
            break  # video oxiriga juda yaqin — bobni tashlaymiz
        ch.append({"start": round(st, 2), "title": title})
    return ch
