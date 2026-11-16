"""LRS analitikasi — SOF funksiyalar (bazaga murojaat yo'q, birlik testlari shu yerni tekshiradi). docs/lrs.md.

Kiruvchi ma'lumot — statementlardan olingan ixcham yozuvlar (app/lrs.py `_row`):
  {"verb": "answered"|"passed"|…, "ts": "YYYY-MM-DDTHH:MM:SS", "sub": bool (obyekt dars ichidagi blok/savol), "success": 0|1|None,
   "completion": 0|1|None, "score": 0..100|None, "duration": soniya|None, "progress": 0..100|None, "item": "savol yo'li"|None, "response": str|None}

1. lesson_summary  — talaba × dars: holat, foiz, ball, urinishlar, muvaffaqiyatsiz urinishlar, vaqt, oxirgi faollik.
2. item_stats      — savol: qiyinlik (p — birinchi urinishda to'g'ri javob ulushi), farqlash indeksi (D = p_yuqori − p_quyi, 27 % guruhlar),
                     point-biserial (r_pb), eng ko'p tanlangan noto'g'ri javob.
3. funnel          — kurs: darslar bo'yicha voronka (boshlagan, yakunlagan, o'tgan).
4. expected_done   — taqvim bo'yicha kutilgan dars soni (semestr boshidan haftasiga chiqarilgan darslar, bir hafta imtiyoz bilan).
5. risk_reasons    — «Ortda qolganlar» qoidalari: kechikish (dars), testdan qayta-qayta o'tolmaslik, faolsizlik.
"""
from __future__ import annotations
import datetime as dt, math
from collections import Counter

DONE_ST = ("otdi", "yakunlandi")
STATUS = {"boshlanmagan": "Boshlanmagan", "jarayonda": "Jarayonda", "otmadi": "Testdan o'tmadi", "yakunlandi": "Yakunlandi", "otdi": "O'tdi"}
RESULT_VERBS = ("passed", "failed")


def _ts_max(a, b):
    return b if (a is None or (b is not None and b > a)) else a


# =============================================================================================
# 1. Talaba × dars
# =============================================================================================
def lesson_summary(events: list[dict]) -> dict:
    """Bitta talabaning bitta darsi bo'yicha jamlanma.

    Urinish = test natijasi (passed/failed). Paket pleyeri natijani ham test bloki (sub), ham dars (paket) darajasida yuboradi —
    ikki marta sanalmasligi uchun: blok darajasidagi natija bo'lsa faqat o'shalar, aks holda dars darajasidagilar sanaladi.
    Holat: o'tdi (passed) > testdan o'tmadi (failed, passed yo'q — dars «completed» bo'lsa ham) > yakunlandi (completed) > jarayonda > boshlanmagan.
    Ballsiz dars darajasidagi «passed» (Rise «passed/incomplete» va bizning pleyer — testsiz dars ko'rib chiqildi) — test natijasi emas,
    yakunlanish belgisi: urinish sanalmaydi, holat «yakunlandi».
    Foiz: yakunlangan/o'tgan — 100; aks holda «progressed» kengaytmasidagi eng katta qiymat (yo'q bo'lsa 0).
    Vaqt: dars darajasidagi terminated / suspended (eski pleyer) va «attempted» (Rise / yangi pleyer — yopilishda result.duration) yig'indisi."""
    ev = [e for e in events if e]
    if not ev:
        return {"status": "boshlanmagan", "pct": 0.0, "score": None, "best": None, "attempts": 0, "fails": 0, "time_s": 0.0, "first": None, "last": None}
    res_sub = [e for e in ev if e["verb"] in RESULT_VERBS and e.get("sub")]
    res = res_sub or [e for e in ev if e["verb"] in RESULT_VERBS and not e.get("sub") and not (e["verb"] == "passed" and e.get("score") is None)]
    res = sorted(res, key=lambda e: e["ts"] or "")
    passed = any(e["verb"] == "passed" or e.get("success") == 1 and e["verb"] in RESULT_VERBS for e in res)
    fails = sum(1 for e in res if e["verb"] == "failed")
    completed = any(e["verb"] == "completed" and not e.get("sub") and e.get("completion") != 0 for e in ev) or \
        any(e["verb"] in ("passed",) and not e.get("sub") for e in ev)
    scores = [e["score"] for e in res if e.get("score") is not None]
    status = "otdi" if passed else "otmadi" if fails else "yakunlandi" if completed else "jarayonda"   # yiqilgan test «yakunlandi» hisoblanmaydi
    prog = [e["progress"] for e in ev if e.get("progress") is not None]
    pct = 100.0 if status in DONE_ST else round(min(99.0, max(prog)), 1) if prog else 0.0
    time_s = sum(float(e.get("duration") or 0) for e in ev if e["verb"] in ("terminated", "suspended", "attempted") and not e.get("sub"))
    first = last = None
    for e in ev:
        t = e.get("ts")
        if t and (first is None or t < first): first = t
        last = _ts_max(last, t)
    return {"status": status, "pct": pct, "score": scores[-1] if scores else None, "best": max(scores) if scores else None,
            "attempts": len(res), "fails": fails, "time_s": round(time_s, 1), "first": first, "last": last}


# =============================================================================================
# 2. Savollar (item analysis)
# =============================================================================================
def first_attempts(answers: list[dict]) -> dict:
    """answers: [{"student", "item", "ts", "success": 0|1, "response"}] → {(talaba, savol): birinchi javob}. Klassik test nazariyasi
    birinchi urinish bo'yicha hisoblanadi (keyingi urinishlar javobni bilib olgandan keyin bo'lishi mumkin)."""
    out = {}
    for a in sorted(answers, key=lambda a: (a.get("ts") or "", a.get("seq", 0))):
        k = (a["student"], a["item"])
        if k not in out: out[k] = a
    return out


def _pb(xs: list[int], totals: list[float]) -> float | None:
    """Point-biserial korrelyatsiya (savol 0/1 va talabaning qolgan savollardagi natijasi)."""
    n = len(xs)
    if n < 3: return None
    m1 = [t for x, t in zip(xs, totals) if x]
    m0 = [t for x, t in zip(xs, totals) if not x]
    if not m1 or not m0: return None
    mean = sum(totals) / n
    sd = math.sqrt(sum((t - mean) ** 2 for t in totals) / n)
    if sd == 0: return None
    p = len(m1) / n
    return round((sum(m1) / len(m1) - sum(m0) / len(m0)) / sd * math.sqrt(p * (1 - p)), 3)


def item_stats(answers: list[dict], min_n: int = 10, group: float = 0.27) -> dict:
    """{savol: {n, correct, p, d, r_pb, top_wrong, top_wrong_n, wrong_share, flags}}.

    p — qiyinlik (to'g'ri javoblar ulushi, birinchi urinish). d — farqlash indeksi: talabalar shu to'plamdagi BOSHQA savollardagi natijasi
    (to'g'ri javoblar ulushi) bo'yicha tartiblanadi, yuqori va quyi 27 % guruhlardagi p farqi. n < min_n bo'lsa d va r_pb — None
    (kichik tanlovda ishonchsiz). top_wrong — eng ko'p tanlangan noto'g'ri javob (javob matni yoki variant harfi), wrong_share — noto'g'ri
    javob berganlar ichidagi ulushi."""
    fa = first_attempts(answers)
    by_item: dict = {}
    by_student: dict = {}
    for (s, it), a in fa.items():
        ok = 1 if a.get("success") else 0
        by_item.setdefault(it, []).append((s, ok, a.get("response")))
        by_student.setdefault(s, {})[it] = ok
    out = {}
    for it, rows in by_item.items():
        n = len(rows)
        corr = sum(r[1] for r in rows)
        p = corr / n if n else None
        rest = []
        for s, ok, _ in rows:
            other = [v for k, v in by_student[s].items() if k != it]
            rest.append(sum(other) / len(other) if other else None)
        d = rpb = None
        pairs = [(ok, r) for (_, ok, _), r in zip(rows, rest) if r is not None]
        if n >= min_n and len(pairs) >= min_n:
            srt = sorted(pairs, key=lambda x: x[1])
            g = max(1, int(round(len(srt) * group)))
            lo, hi = srt[:g], srt[-g:]
            d = round(sum(x[0] for x in hi) / g - sum(x[0] for x in lo) / g, 3)
            rpb = _pb([x[0] for x in pairs], [x[1] for x in pairs])
        wrong = Counter((r[2] or "").strip() for r in rows if not r[1] and (r[2] or "").strip())
        top, top_n = (wrong.most_common(1)[0] if wrong else (None, 0))
        nw = n - corr
        flags = []
        if p is not None and n >= min_n:
            if p < 0.3: flags.append("qiyin")
            elif p > 0.95: flags.append("oson")
        if d is not None:
            if d < 0: flags.append("salbiy")
            elif d < 0.2: flags.append("farqlamaydi")
        if nw >= 5 and top_n / nw >= 0.6: flags.append("chalgituvchi")
        out[it] = {"n": n, "correct": corr, "p": round(p, 3) if p is not None else None, "d": d, "r_pb": rpb, "top_wrong": top, "top_wrong_n": top_n,
                   "wrong_share": round(top_n / nw, 3) if nw else None, "flags": flags}
    return out


# =============================================================================================
# 3. Kurs voronkasi
# =============================================================================================
def funnel(lessons: list[str], status: dict, enrolled: int) -> list[dict]:
    """lessons — dars yo'llari (tartibda); status — {(talaba, dars): holat}; enrolled — kursdagi talabalar soni (0 — statementlardan)."""
    students = {s for (s, _) in status}
    base = max(int(enrolled or 0), len(students))
    out = []
    for l in lessons:
        st = [v for (s, ll), v in status.items() if ll == l]
        started = sum(1 for v in st if v != "boshlanmagan")
        done = sum(1 for v in st if v in DONE_ST)
        passed = sum(1 for v in st if v == "otdi")
        out.append({"lesson": l, "started": started, "done": done, "passed": passed, "failed": sum(1 for v in st if v == "otmadi"),
                    "started_pct": round(100 * started / base, 1) if base else None, "done_pct": round(100 * done / base, 1) if base else None})
    return out


# =============================================================================================
# 4. Taqvim bo'yicha kutilgan progress
# =============================================================================================
def monday(d: dt.date) -> dt.date:
    return d - dt.timedelta(days=d.weekday())


def week_no(start: dt.date, today: dt.date) -> int:
    """Semestrning joriy haftasi (1 dan). Semestr boshlanmagan bo'lsa 0."""
    if today < start: return 0
    return (monday(today) - monday(start)).days // 7 + 1


def released(n_lessons: int, start: dt.date, today: dt.date, weeks: int) -> int:
    """Shu kungacha chiqarilgan darslar: n dars `weeks` haftaga teng taqsimlanadi, har hafta boshida chiqariladi."""
    w = min(max(0, week_no(start, today)), max(1, weeks))
    return min(n_lessons, math.ceil(n_lessons * w / max(1, weeks))) if n_lessons > 0 else 0


def expected_done(n_lessons: int, start: dt.date, today: dt.date, weeks: int, grace_weeks: int = 1) -> int:
    """Kutilgan yakunlangan darslar: `grace_weeks` hafta oldin chiqarilganlar (joriy hafta darslari hali tugatilishi shart emas)."""
    return released(n_lessons, start, today - dt.timedelta(weeks=max(0, grace_weeks)), weeks)


# =============================================================================================
# 5. «Ortda qolganlar» qoidalari
# =============================================================================================
POLICY = [  # (kalit, standart, izoh, (min, max))
    ("lag_lessons", 3, "Taqvimdan shuncha va undan ko'p dars ortda — xavf", (1, 30)),
    ("fail_attempts", 3, "Bitta testdan shuncha va undan ko'p marta o'tolmagan (hali o'tmagan) — xavf", (2, 20)),
    ("inactive_days", 7, "Shuncha kun hech qanday faollik yo'q — xavf", (2, 60)),
    ("grace_weeks", 1, "Kutilgan progress: joriy haftadan shuncha hafta oldingi darslar hisobga olinadi", (0, 4)),
    ("weeks", 15, "Semestrdagi o'quv haftalari (darslar shu haftalarga teng taqsimlanadi)", (8, 24)),
    ("remind_cooldown_days", 3, "Bitta talabaga eslatma — shuncha kunda ko'pi bilan bir marta", (1, 30)),
    ("remind_daily_max", 200, "Bitta xodim bir kunda yuboradigan eslatmalar chegarasi", (1, 2000)),
]
DEFAULTS = {k: v for k, v, _, _ in POLICY}
REASONS = {"ortda": "Taqvimdan ortda", "test": "Testdan qayta-qayta o'tolmayapti", "faolsiz": "Faolsiz", "boshlamagan": "Umuman boshlamagan"}


def risk_reasons(row: dict, pol: dict | None = None) -> list[dict]:
    """row: {expected, done, max_fails (hali o'tilmagan darsdagi eng ko'p muvaffaqiyatsiz urinish), fail_lesson, days_inactive (None — faollik yo'q),
    started (bool)}. → [{code, label, sev}] (og'irlik 1–3). Bir sabab bir marta."""
    p = {**DEFAULTS, **(pol or {})}
    out = []
    lag = max(0, int(row.get("expected") or 0) - int(row.get("done") or 0))
    if lag >= p["lag_lessons"]:
        out.append({"code": "ortda", "label": f"Taqvimdan {lag} dars ortda ({row.get('done') or 0}/{row.get('expected') or 0})",
                    "sev": 3 if lag >= 2 * p["lag_lessons"] else 2})
    mf = int(row.get("max_fails") or 0)
    if mf >= p["fail_attempts"]:
        out.append({"code": "test", "label": f"Testdan {mf} marta o'tolmagan" + (f" ({row['fail_lesson']})" if row.get("fail_lesson") else ""),
                    "sev": 3 if mf >= 2 * p["fail_attempts"] else 2})
    di = row.get("days_inactive")
    if not row.get("started"):
        if int(row.get("expected") or 0) > 0:
            out.append({"code": "boshlamagan", "label": "Kursni umuman boshlamagan", "sev": 3})
    elif di is not None and di >= p["inactive_days"]:
        out.append({"code": "faolsiz", "label": f"{di} kundan beri faollik yo'q", "sev": 3 if di >= 2 * p["inactive_days"] else 2})
    return out


def risk_level(reasons: list[dict]) -> str:
    s = sum(r["sev"] for r in reasons)
    return "yuqori" if s >= 4 else "orta" if s >= 2 else "past" if s else ""


# Qoidalar FAQAT o'quv faolligiga asoslanadi. risk_reasons() faqat shu kalitlarni o'qiydi — demografik ma'lumot (jinsi, yoshi, tug'ilgan sanasi,
# millati, hududi, ijtimoiy holati, to'lov turi va h.k.) hech qachon qoida kirishi bo'lmaydi (tests/test_keyslar.py tekshiradi).
RULE_INPUTS = ("expected", "done", "max_fails", "fail_lesson", "days_inactive", "started")
REASONS["ready"] = "«ISFT Ready» tugatilmagan"


def ready_reasons(completed: bool, started: bool, today: dt.date, deadline: dt.date) -> list[dict]:
    """«ISFT Ready» kirish kursi qoidasi (erta signal): muddat (1-hafta oxiri; kurs semestr o'rtasida e'lon qilingan bo'lsa — e'londan 7 kun)
    o'tdi va kurs tugatilmagan → «boshlamagan» bayrog'i (og'irlik 2). Faqat faollik: tugatdimi, boshladimi, sana."""
    if completed or today <= deadline: return []
    d = f"{deadline.day:02d}.{deadline.month:02d}"
    return [{"code": "ready", "label": f"Boshlamagan: «ISFT Ready» kirish kursi muddati ({d}) o'tdi" if not started
             else f"«ISFT Ready» kirish kursi muddatida ({d}) tugatilmagan", "sev": 2}]


# =============================================================================================
# 6. Haftalik ritm: darslar jadvali (chiqarilish sanasi va muddati) — app/haftalik.py (kogorta taqvimi) shu funksiyalardan foydalanadi
# =============================================================================================
def release_week(i: int, n_lessons: int, weeks: int) -> int:
    """i-dars (0 dan) qaysi haftada chiqariladi: released() bilan bir xil teng taqsimot — eng kichik w, ceil(n·w/weeks) > i."""
    weeks = max(1, int(weeks))
    for w in range(1, weeks + 1):
        if math.ceil(n_lessons * w / weeks) > i: return w
    return weeks


def schedule(n_lessons: int, start: dt.date, weeks: int, due_override: dict | None = None) -> list[dict]:
    """Darslar jadvali: [{week, release, due}] (sana). Standart — dars o'z haftasining boshida (1-hafta — semestr boshlangan kuni) chiqariladi,
    muddati — o'sha haftaning oxiri (yakshanba). due_override: {i: sana} — bo'lim bitta darsning muddatini o'zgartirgan bo'lsa (chiqarilishdan
    oldin bo'lolmaydi)."""
    m0 = monday(start)
    out = []
    for i in range(max(0, n_lessons)):
        w = release_week(i, n_lessons, weeks)
        rel = max(start, m0 + dt.timedelta(weeks=w - 1))
        due = m0 + dt.timedelta(weeks=w - 1, days=6)
        ov = (due_override or {}).get(i)
        if isinstance(ov, dt.date) and ov >= rel: due = ov
        out.append({"week": w, "release": rel, "due": due})
    return out


def released_by(sched: list[dict], today: dt.date) -> int:
    """Shu kungacha chiqarilgan darslar soni (chiqarilish sanasi ≤ bugun)."""
    return sum(1 for s in sched if s["release"] <= today)


def expected_by_due(sched: list[dict], today: dt.date, grace_weeks: int = 1) -> int:
    """Kutilgan yakunlangan darslar — muddati o'tganlar. grace_weeks — muddatdan keyingi imtiyoz: 1 (standart) — muddat yakshanba, bayroq
    keyingi haftadan (standart taqvimda expected_done(…, 1) bilan aynan bir xil); 2 — yana bir hafta; 0 — chiqarilgan dars darhol kutiladi."""
    g = max(0, int(grace_weeks))
    if not g: return released_by(sched, today)
    return sum(1 for s in sched if today > s["due"] + dt.timedelta(weeks=g - 1))
