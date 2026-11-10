"""Bank ko'chirmasi qatorini talabaga moslashtirish (faqat stdlib: difflib + o'z Levenshtein/«symmetric delete» indeksi).

Kirish: to'lov maqsadi (purpose), to'lovchi (payer), hujjat raqami (doc_no), summa.
Chiqish: nomzod talabalar (ball 0..100, sabablar ro'yxati) va avto-moslash mumkinmi.

Normallashtirish: kirill → lotin (o'zbek), oʻ/gʻ/apostrof turlari olib tashlanadi, katta-kichik harf, tinish belgilari, kh→x.
Raqamlar: matndagi barcha raqam ketma-ketliklari (ajratuvchi «-», «/», bo'shliq bilan bo'lingan bo'lsa ham birlashtiriladi).
  * shartnoma raqami (CONTRACT_NO: «26-0XXXX», talaba id dan) va HEMIS ID — aniq mos → avto; 1 belgi farq (almashtirish, tushib
    qolish, ortiqcha, qo'shni raqamlar o'rni almashgan) → «symmetric delete» indeksi orqali, sabab bilan.
F.I.Sh.: tokenlar bo'yicha (tartib ahamiyatsiz, bosh harflar), familiya ildizi (-ov/-ova/-ev/-eva) bo'yicha bloklash, difflib nisbati.
Ota-ona: to'lovchi familiyasi ildizi talabaniki bilan bir xil va to'lovchi ismi talabaning otasining ismi (patronim) bilan mos.
Summa: qarzga teng / muddati o'tgan qismga teng / navbatdagi bosqichga teng → qo'shimcha ball; qarzdan katta → jarima.
"""
import difflib, re, threading

CYR = {"а": "a", "б": "b", "в": "v", "г": "g", "ғ": "g", "д": "d", "е": "e", "ё": "yo", "ж": "j", "з": "z", "и": "i", "й": "y", "к": "k", "қ": "q",
       "л": "l", "м": "m", "н": "n", "о": "o", "ў": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u", "ф": "f", "х": "x", "ҳ": "h", "ц": "ts",
       "ч": "ch", "ш": "sh", "щ": "sh", "ъ": "", "ы": "i", "ь": "", "э": "e", "ю": "yu", "я": "ya"}
APOS = "'`ʻʼ‘’´ʹ"
STOP = {"uchun", "kontrakt", "shartnoma", "tolov", "toʻlov", "oqish", "talaba", "talabasi", "isft", "instituti", "institut", "yil", "yili", "oquv",
        "summa", "som", "dan", "va", "boyicha", "pul", "qizi", "ogli", "ogl", "qiz", "gr", "guruh", "guruhi", "hemis", "id", "raqam", "raqami", "n",
        "kontrakti", "kontrakta", "oplata", "za", "obuchenie", "dogovor", "po", "ot", "student", "contract", "payment", "for", "the", "mening", "ogim",
        "ogilim", "qizim", "oglim", "farzandim", "bolam", "sem", "semestr", "kurs", "bosqich", "toʻlovi", "tolovi", "qismi", "badali"}
KIN = {"oglim", "qizim", "farzandim", "bolam", "ukam", "singlim", "nevaram", "oglimga", "qizimga", "oglim uchun", "sinim", "doch", "syn", "docheri", "syna"}
SUFFIXES = ("ovna", "evna", "ova", "eva", "ov", "ev", "iy", "aya", "ich")

def luhn(body: str) -> int:
    t = 0
    for i, ch in enumerate(reversed(body)):
        d = int(ch) * (2 if i % 2 == 0 else 1)
        t += d - 9 if d > 9 else d
    return (10 - t % 10) % 10

# Shartnoma raqami: «26-SSSSS-K» — o'quv yili, talaba raqami va nazorat raqami (Luhn). Nazorat raqami tufayli bitta raqam xatosi yoki
# qo'shni raqamlar o'rni almashishi boshqa haqiqiy shartnoma raqamiga to'g'ri kelmaydi (zich raqamlar maydonida noto'g'ri avto-moslashning oldi olinadi).
def _contract_body(sid: int) -> str: return f"26{sid:05d}"
def _contract_digits(sid: int) -> str: b = _contract_body(sid); return b + str(luhn(b))
def contract_no(sid: int) -> str: d = _contract_digits(sid); return f"{d[:2]}-{d[2:7]}-{d[7]}"

def norm(s: str) -> str:
    s = (s or "").lower()
    s = "".join(CYR.get(ch, ch) for ch in s)
    for a in APOS: s = s.replace(a, "")
    s = s.replace("kh", "x")
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()

def tokens(s: str) -> list[str]: return [t for t in norm(s).split() if not t.isdigit()]

def root(tok: str) -> str:
    for suf in SUFFIXES:
        if tok.endswith(suf) and len(tok) - len(suf) >= 3: return tok[: -len(suf)]
    return tok

def digit_seqs(*texts) -> set[str]:
    out = set()
    for t in texts:
        t = "".join(CYR.get(ch, ch) for ch in (t or "").lower())
        for m in re.finditer(r"\d[\d\s\-/\.№]*\d|\d", t):
            raw = m.group(0)
            out.add(re.sub(r"\D", "", raw))
            out.update(re.sub(r"\D", "", ch) for ch in raw.split())        # bo'shliq bilan ajratilgan bo'laklar («26-03077 2 500 000»)
            out.update(p for p in re.split(r"\D+", raw) if p)
    return {d for d in out if len(d) >= 5}

def lev(a: str, b: str, cap: int = 3) -> int:
    if abs(len(a) - len(b)) > cap: return cap + 1
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i] + [0] * len(b)
        for j, cb in enumerate(b, 1):
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb))
        prev = cur
    return prev[-1]

def is_swap(a: str, b: str) -> bool:
    if len(a) != len(b): return False
    d = [i for i in range(len(a)) if a[i] != b[i]]
    return len(d) == 2 and d[1] == d[0] + 1 and a[d[0]] == b[d[1]] and a[d[1]] == b[d[0]]

def _dels(s: str) -> set[str]: return {s} | {s[:i] + s[i + 1:] for i in range(len(s))}

def ratio(a: str, b: str) -> float: return difflib.SequenceMatcher(None, a, b).ratio()

# ---------------------------------------------------------------------------------------------
# Indeks (talabalar ro'yxati o'zgarganda qayta quriladi)
# ---------------------------------------------------------------------------------------------
_lock = threading.Lock()
_IDX = {"key": None}

def _index(con):
    key = con.execute("SELECT COUNT(*), MAX(id), SUM(paid_amount) FROM students WHERE payment_type='kontrakt'").fetchone()
    with _lock:
        if _IDX["key"] and _IDX["key"][:2] == key[:2]:
            if _IDX["key"][2] != key[2]: _refresh_debts(con)
            _IDX["key"] = key
            return _IDX
        rows = con.execute("""SELECT s.id, s.full_name, s.hemis_id, s.contract_amount, s.paid_amount, s.status, g.name FROM students s
                              LEFT JOIN groups_ g ON g.id=s.group_id WHERE s.payment_type='kontrakt' AND s.contract_amount>0""").fetchall()
        S, by_hemis, by_contract, del_h, del_c, by_root, by_body = {}, {}, {}, {}, {}, {}, {}
        for sid, fn, hid, amt, paid, st, grp in rows:
            tk = tokens(fn)
            S[sid] = {"id": sid, "full_name": fn, "hemis_id": hid or "", "amount": amt or 0, "paid": paid or 0, "status": st, "grp": grp or "",
                      "tok": tk, "sur": tk[0] if tk else "", "giv": tk[1] if len(tk) > 1 else "", "pat": tk[2] if len(tk) > 2 else "",
                      "grpn": norm(grp or "").replace(" ", "")}
            if hid:
                by_hemis[hid] = sid
                for d in _dels(hid): del_h.setdefault(d, set()).add(sid)
            cd = _contract_digits(sid); by_contract[cd] = sid; by_body[cd[:7]] = sid
            for d in _dels(cd): del_c.setdefault(d, set()).add(sid)
            if tk: by_root.setdefault(root(tk[0]), set()).add(sid)
        _IDX.update(key=key, S=S, by_hemis=by_hemis, by_contract=by_contract, del_h=del_h, del_c=del_c, by_root=by_root, roots=list(by_root), by_body=by_body)
        return _IDX

def _refresh_debts(con):
    for sid, paid in con.execute("SELECT id, paid_amount FROM students WHERE payment_type='kontrakt' AND contract_amount>0"):
        if sid in _IDX["S"]: _IDX["S"][sid]["paid"] = paid or 0

def invalidate(): _IDX["key"] = None

def _fuzzy_ids(seq: str, exact: dict, dels: dict) -> list[tuple[int, str, int]]:
    """[(sid, matched_value, distance)] — aniq (0) yoki 1 tahrir/qo'shni almashinuv (symmetric delete)."""
    out = {}
    if seq in exact: out[exact[seq]] = 0
    for d in _dels(seq):
        for sid in dels.get(d, ()):
            out.setdefault(sid, 1)
    return [(sid, None, dist) for sid, dist in out.items()]

# ---------------------------------------------------------------------------------------------
# Moslashtirish
# ---------------------------------------------------------------------------------------------
def match(con, purpose: str, payer: str, doc_no: str, amount: int, plan: list[dict], limit: int = 5) -> dict:
    I = _index(con); S = I["S"]
    cand: dict[int, dict] = {}
    def add(sid, pts, why, kind=None):
        c = cand.setdefault(sid, {"id": sid, "score": 0, "reasons": [], "kinds": set()})
        c["score"] += pts; c["reasons"].append(why)
        if kind: c["kinds"].add(kind)
    seqs = digit_seqs(purpose, doc_no) - {str(amount or "")}
    for sq in seqs:
        if 7 <= len(sq) <= 9:
            for sid, _, dist in _fuzzy_ids(sq, I["by_contract"], I["del_c"]):
                cd = _contract_digits(sid)
                if dist == 0: add(sid, 100, f"shartnoma raqami {contract_no(sid)} aniq mos", "exact_contract")
                else:
                    why = "shartnoma raqamida qo'shni raqamlar o'rni almashgan" if is_swap(sq, cd) else "shartnoma raqami 1 belgi farq qiladi"
                    add(sid, 55, f"{why} ({sq} ↔ {contract_no(sid)})", "fuzzy_contract")
            if len(sq) == 7 and sq in I["by_body"] and sq not in I["by_contract"]:
                add(I["by_body"][sq], 60, f"shartnoma raqami nazorat raqamisiz yozilgan ({contract_no(I['by_body'][sq])})", "body_contract")
        if 11 <= len(sq) <= 15:
            for sid, _, dist in _fuzzy_ids(sq, I["by_hemis"], I["del_h"]):
                if dist == 0: add(sid, 100, "HEMIS ID aniq mos", "exact_hemis")
                else:
                    hid = S[sid]["hemis_id"]
                    why = "HEMIS ID da qo'shni raqamlar o'rni almashgan" if is_swap(sq, hid) else "HEMIS ID 1 belgi farq qiladi"
                    add(sid, 55, why, "fuzzy_hemis")
    # F.I.Sh. — maqsad matni va to'lovchi
    ptoks = [t for t in tokens(purpose) if t not in STOP and len(t) >= 3]
    ytoks = [t for t in tokens(payer) if t not in STOP and len(t) >= 3]
    text_groups = {re.sub(r"\s+", "", g) for g in re.findall(r"\b[a-z]{2,4}\s?\d{2}[a-z]?\d{2}\b", norm(purpose + " " + payer))}
    kin = any(t in KIN for t in tokens(purpose))     # «o'g'lim/qizim uchun» — to'lovchi ota-ona, talabaning o'zi emas
    pool = set()
    for t in set(ptoks + ytoks):
        r = root(t)
        if len(r) < 3: continue
        for rr in ([r] if r in I["by_root"] else []) + difflib.get_close_matches(r, I["roots"], n=4, cutoff=0.8):
            pool |= I["by_root"].get(rr, set())
    if len(pool) > 4000: pool = set()   # juda umumiy familiya va boshqa ma'lumot yo'q — raqamlarga tayaniladi
    for sid in pool | set(cand):
        s = S[sid]
        if not s["sur"]: continue
        def best(tok, toks): return max((ratio(tok, x) for x in toks), default=0.0)
        def best_root(tok, toks): return max((ratio(root(tok), root(x)) for x in toks), default=0.0)
        # talabaning o'zi maqsadda/to'lovchida
        for src, toks, lbl in (("p", ptoks, "maqsadda"), ("y", ytoks, "to'lovchi")):
            if not toks: continue
            sur, giv = best_root(s["sur"], toks), best(s["giv"], toks) if s["giv"] else 0
            if sur >= 0.8 and giv >= 0.8:
                sim = round(100 * (sur + giv) / 2)
                pat = best(s["pat"], toks) if s["pat"] else 0
                pts = 30 + (sim - 80) * 0.75 + (8 if pat >= 0.85 else 0)
                add(sid, pts, f"F.I.Sh. {lbl} o'xshash {sim}%" + (" (otasining ismi ham)" if pat >= 0.85 else ""), "name" if src == "p" else "payer_self")
                break
        else:
            if sid in cand and max(best_root(s["sur"], ptoks), best_root(s["sur"], ytoks[:1]) if ytoks else 0) >= 0.85:
                add(sid, 15, f"familiya mos ({s['sur'].capitalize()})", "surname")
        # ota-ona: to'lovchi familiyasi talabaniki bilan bir xil, ismi — talabaning otasining ismi
        if ytoks and s["pat"]:
            ysur = max((ratio(root(s["sur"]), root(x)) for x in ytoks[:1]), default=0)
            ysur = 1.0 if ytoks and root(s["sur"]) == root(ytoks[0]) else ysur
            if ysur >= 0.85 and "payer_self" not in cand.get(sid, {}).get("kinds", set()):
                fat = best(s["pat"], ytoks[1:])
                if fat >= 0.8:
                    q_ = min(ysur, fat)      # aniq mos kelganlar o'xshashlaridan yuqori turadi
                    add(sid, (28 + (10 if kin else 0)) * q_, "to'lovchi familiyasi talabaniki bilan bir xil, ismi — talabaning otasi ismi (ota-ona)", "parent")
                    gv = best(s["giv"], ptoks) if s["giv"] else 0
                    if gv >= 0.8: add(sid, 18 * gv, f"maqsadda talabaning ismi ({s['giv'].capitalize()})", "given")
        if text_groups and s["grpn"] and s["grpn"] in text_groups: add(sid, 12, f"guruh {s['grp']} mos", "group")
    if kin:
        for c in cand.values():
            if "payer_self" in c["kinds"]: c["score"] -= 20; c["reasons"].append("maqsadda «o'g'lim/qizim» — to'lovchi talabaning o'zi emas")
    # matnda ism-familiyaga o'xshash so'z bormi (talabalar familiyalari ildizlari bilan solishtiriladi)
    has_name_words = any(difflib.get_close_matches(root(t), I["roots"], n=1, cutoff=0.8) for t in set(ptoks + ytoks))
    # summa
    out = []
    for sid, c in cand.items():
        s = S[sid]
        if c["score"] < 25: continue
        debt = max(0, s["amount"] - s["paid"])
        if amount and debt and amount == debt: c["score"] += 12; c["reasons"].append("summa qarzga teng")
        elif amount and debt:
            for p in plan:
                need = s["amount"] * p["cum_pct"] // 100 - s["paid"]
                if need > 0 and amount == need: c["score"] += 10; c["reasons"].append(f"summa {p['label']}gacha yetishmaganiga teng"); break
                if amount == s["amount"] * 25 // 100: c["score"] += 6; c["reasons"].append("summa bitta bosqich (25%) ga teng"); break
        if amount and amount > debt: c["score"] -= 25; c["reasons"].append(f"summa qarzdan katta (qarz {debt:,} so'm)".replace(",", " "))
        if s["status"] != "faol": c["score"] -= 10; c["reasons"].append(f"talaba holati: {s['status']}")
        exact = bool(c["kinds"] & {"exact_contract", "exact_hemis"})
        if (ptoks or ytoks) and has_name_words and not c["kinds"] & {"name", "payer_self", "parent", "surname", "given"} \
                and c["kinds"] & {"exact_contract", "exact_hemis", "fuzzy_contract", "fuzzy_hemis", "body_contract"}:
            c["score"] -= 35; c["reasons"].append("matndagi F.I.Sh. bu talabaga mos emas"); exact = False
        sc = max(1, min(100 if exact else 97, round(c["score"])))
        out.append({"student_id": sid, "full_name": s["full_name"], "hemis_id": s["hemis_id"], "grp": s["grp"], "contract_no": contract_no(sid),
                    "debt": debt, "score": sc, "reasons": c["reasons"], "kinds": sorted(c["kinds"]), "exact": exact})
    out.sort(key=lambda x: (-x["score"], x["full_name"]))
    out = out[:limit]
    auto = None
    if out:
        top = out[0]; second = out[1]["score"] if len(out) > 1 else 0
        fits = amount and amount <= top["debt"]
        if top["exact"] and fits and not (len(out) > 1 and out[1]["exact"]):
            auto = top
        elif {"name", "group"} <= set(top["kinds"]) and fits and top["score"] - second >= 15 and \
                any("100% (otasining ismi ham)" in r for r in top["reasons"]):
            auto = top     # aniq to'liq F.I.Sh. (otasining ismi bilan) + guruh
    return {"candidates": out, "auto": auto}
