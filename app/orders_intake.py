"""Buyruqlar moduli (app/orders.py) uchun kirish ma'lumotlarini o'qish: talaba arizasi va Excel/CSV ro'yxatlar.

  * extract()       — ariza faylidan matn: PDF matn qatlami (pypdf), DOCX (python-docx), TXT; matn qatlami bo'lmasa yoki rasm
                      (JPG/PNG) bo'lsa — OCR (tesseract, bo'lsa). Tesseract yo'q bo'lsa (masalan, Railway) — xato emas:
                      method="manual", foydalanuvchi matnni qo'lda kiritadi.
  * detect()        — ariza turi va maydonlari (qoidalar asosida, AI'siz — natija tekshiriladigan va takrorlanadigan):
                      familiya o'zgartirish, akademik ta'til, ta'tildan qaytish, o'z xohishi bilan chetlashtirish,
                      boshqa OTMga ko'chirish, guruh o'zgartirish, qayta tiklash.
  * match_students()— talabani HEMIS ID / F.I.Sh. / guruh bo'yicha topish (ko'lam filtri bilan).
  * parse_list()    — Excel (.xlsx, openpyxl) yoki CSV ro'yxat: HEMIS ID / F.I.Sh. / guruh ustunlari sarlavhadan yoki mazmundan aniqlanadi.
Kirill yozuvidagi arizalar lotinga o'giriladi (faqat aniqlash uchun)."""
import csv, datetime as dt, difflib, io, re, shutil, subprocess, tempfile
from pathlib import Path

# ---------------------------------------------------------------------------------------------
# Matnni normallashtirish
# ---------------------------------------------------------------------------------------------
APOS = re.compile(r"[ʻʼ‘’`´′]")
CYR = {"а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "yo", "ж": "j", "з": "z", "и": "i", "й": "y", "к": "k",
       "л": "l", "м": "m", "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u", "ф": "f", "х": "x", "ц": "ts",
       "ч": "ch", "ш": "sh", "щ": "sh", "ъ": "'", "ы": "i", "ь": "", "э": "e", "ю": "yu", "я": "ya", "ў": "o'", "қ": "q", "ғ": "g'", "ҳ": "h"}

def translit(s: str) -> str:
    out = []
    for ch in s:
        lo = ch.lower()
        if lo in CYR:
            t = CYR[lo]
            out.append(t.capitalize() if ch != lo and t else t)
        else:
            out.append(ch)
    return "".join(out)

def clean(s: str) -> str:
    """Asl ko'rinishdagi (katta-kichik harf saqlangan) lotin matn: apostroflar bir xil, ortiqcha bo'shliqlar yo'q."""
    s = APOS.sub("'", translit(s or ""))
    s = s.replace(" ", " ").replace("\r", "")
    s = re.sub(r"[ \t]+", " ", s)
    return re.sub(r"\n{3,}", "\n\n", s).strip()

def norm(s: str) -> str:
    return re.sub(r"\s+", " ", clean(s).lower()).strip()

def name_key(s: str) -> str:
    """F.I.Sh. solishtirish kaliti: kichik harf, apostrof va tirelarsiz, «o'g'li/qizi» olib tashlanadi."""
    s = norm(s)
    s = re.sub(r"\b(o'g'li|ogli|o'g'il|qizi)\b", "", s)
    s = re.sub(r"[^a-z0-9 ]", "", s.replace("'", ""))
    return re.sub(r"\s+", " ", s).strip()

# ---------------------------------------------------------------------------------------------
# Fayldan matn
# ---------------------------------------------------------------------------------------------
TEXT_EXT = {".txt"}
DOCX_EXT = {".docx"}
PDF_EXT = {".pdf"}
IMG_EXT = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp"}
ALLOWED_APP = TEXT_EXT | DOCX_EXT | PDF_EXT | IMG_EXT

_LANGS = None
def ocr_available() -> bool:
    return bool(shutil.which("tesseract"))

def _ocr_langs() -> str:
    global _LANGS
    if _LANGS is None:
        try:
            out = subprocess.run(["tesseract", "--list-langs"], capture_output=True, text=True, timeout=15).stdout.split()
        except Exception:
            out = []
        pref = [l for l in ("uzb_latn", "uzb", "rus", "eng") if l in out]
        _LANGS = "+".join(pref) or "eng"
    return _LANGS

def ocr_image(raw: bytes) -> str | None:
    """Rasmdan matn (tesseract). Tesseract yo'q yoki xato — None (chaqiruvchi qo'lda kiritishni taklif qiladi)."""
    if not ocr_available(): return None
    try:
        from PIL import Image, ImageOps
        im = Image.open(io.BytesIO(raw))
        im = ImageOps.exif_transpose(im).convert("L")
        if im.width < 1400:   # kichik skan — kattalashtirish OCR aniqligini oshiradi
            k = 1400 / max(1, im.width); im = im.resize((int(im.width * k), int(im.height * k)))
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "in.png"; im.save(p)
            r = subprocess.run(["tesseract", str(p), "stdout", "-l", _ocr_langs(), "--psm", "4"], capture_output=True, text=True, timeout=90)
        return r.stdout if r.returncode == 0 else None
    except Exception:
        return None

def extract(filename: str, raw: bytes) -> dict:
    """→ {text, method: text|docx|pdf-text|ocr|manual, note}"""
    ext = Path(filename or "").suffix.lower()
    if ext not in ALLOWED_APP:
        raise ValueError("Ariza fayli PDF, DOCX, TXT yoki rasm (JPG/PNG) bo'lishi kerak")
    if ext in TEXT_EXT:
        for enc in ("utf-8-sig", "cp1251", "latin-1"):
            try: return {"text": clean(raw.decode(enc)), "method": "text", "note": ""}
            except UnicodeDecodeError: continue
    if ext in DOCX_EXT:
        from docx import Document
        try:
            d = Document(io.BytesIO(raw))
        except Exception:
            raise ValueError("DOCX faylni ochib bo'lmadi")
        parts = [p.text for p in d.paragraphs]
        for t in d.tables:
            for row in t.rows:
                parts.append(" ".join(c.text for c in row.cells))
        return {"text": clean("\n".join(parts)), "method": "docx", "note": ""}
    if ext in PDF_EXT:
        try:
            from pypdf import PdfReader
            rd = PdfReader(io.BytesIO(raw))
            text = "\n".join((pg.extract_text() or "") for pg in rd.pages[:6])
        except Exception:
            raise ValueError("PDF faylni o'qib bo'lmadi")
        if len(re.sub(r"\s", "", text)) >= 40:
            return {"text": clean(text), "method": "pdf-text", "note": ""}
        # skanerlangan PDF: sahifadagi rasmlar → OCR
        if not ocr_available():
            return {"text": "", "method": "manual", "note": "PDF'da matn qatlami yo'q (skan), serverda OCR (tesseract) o'rnatilmagan — ariza matnini qo'lda kiriting."}
        chunks = []
        for pg in rd.pages[:4]:
            try:
                for img in pg.images[:2]:
                    t = ocr_image(img.data)
                    if t: chunks.append(t)
            except Exception:
                continue
        text = "\n".join(chunks)
        if len(re.sub(r"\s", "", text)) < 20:
            return {"text": clean(text), "method": "manual", "note": "Skanerlangan PDF'dan matn ajratib bo'lmadi — matnni qo'lda kiriting yoki tuzating."}
        return {"text": clean(text), "method": "ocr", "note": "Matn OCR orqali olindi — ism-sharif va sanalarni tekshiring."}
    # rasm
    if not ocr_available():
        return {"text": "", "method": "manual", "note": "Serverda OCR (tesseract) o'rnatilmagan — rasmdagi ariza matnini qo'lda kiriting."}
    t = ocr_image(raw)
    if not t or len(re.sub(r"\s", "", t)) < 20:
        return {"text": clean(t or ""), "method": "manual", "note": "Rasmdan matn ajratib bo'lmadi — matnni qo'lda kiriting."}
    return {"text": clean(t), "method": "ocr", "note": "Matn OCR orqali olindi — ism-sharif va sanalarni tekshiring."}

# ---------------------------------------------------------------------------------------------
# Sanalar
# ---------------------------------------------------------------------------------------------
MONTHS = {"yanvar": 1, "fevral": 2, "mart": 3, "aprel": 4, "may": 5, "iyun": 6, "iyul": 7, "avgust": 8, "sentabr": 9, "sentyabr": 9,
          "oktabr": 10, "oktyabr": 10, "noyabr": 11, "dekabr": 12}
_MON = "|".join(sorted(MONTHS, key=len, reverse=True))
DATE_RX = [
    (re.compile(r"\b(\d{1,2})[./](\d{1,2})[./](\d{4})\b"), lambda m: (int(m[3]), int(m[2]), int(m[1]))),
    (re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b"), lambda m: (int(m[1]), int(m[2]), int(m[3]))),
    (re.compile(rf"\b(\d{{4}})\s*-?\s*y(?:il|\.)?\s*(\d{{1,2}})\s*-?\s*({_MON})\w*", re.I), lambda m: (int(m[1]), MONTHS[m[3].lower()], int(m[2]))),
    (re.compile(rf"\b(\d{{1,2}})\s*-?\s*({_MON})\w*\s+(\d{{4}})", re.I), lambda m: (int(m[3]), MONTHS[m[2].lower()], int(m[1]))),
]

def find_dates(text: str, with_end=False) -> list:
    """Matndagi sanalar (pozitsiya bo'yicha). Bir-birini qoplaydigan mosliklardan birinchi (aniqroq) shablon olinadi:
    «2026-yil 16-noyabrdan 2027-yil …» dagi «16-noyabrdan 2027» noto'g'ri sana bo'lib qolmasin."""
    spans, out = [], []
    for rx, conv in DATE_RX:
        for m in rx.finditer(text):
            if any(m.start() < b and a < m.end() for a, b in spans): continue
            try:
                y, mo, d = conv(m)
                iso = dt.date(y, mo, d).isoformat()
            except (ValueError, KeyError):
                continue
            spans.append((m.start(), m.end())); out.append((m.start(), m.end(), iso))
    out.sort()
    return out if with_end else [(a, iso) for a, _, iso in out]

def from_date(text: str) -> str | None:
    """«…dan» bilan kelgan sana (masalan, «20-noyabrdan») — bo'lmasa imzo qatoridan oldingi oxirgi sana."""
    ds = find_dates(text, True)
    for a, b, iso in ds:
        tail = text[b - 3:b + 4].lower()
        if re.search(r"(?:dan|-dan|sanadan)", tail): return iso
    cut = text.lower().rfind("imzo")
    body = [iso for a, b, iso in ds if cut < 0 or a < cut]
    return (body or [iso for _, _, iso in ds] or [None])[-1]

# ---------------------------------------------------------------------------------------------
# Ariza turini aniqlash
# ---------------------------------------------------------------------------------------------
KIND_RULES = [   # (tur, [(regex, og'irlik)]) — matn norm() dan o'tgan (kichik harf, lotin, apostrof bir xil)
    ("tatildan_qaytish", [(r"ta'?tildan\s+(?:\S+\s+){0,2}?(?:qayt|chiq)", 5), (r"o'qishni\s+davom\s+ettir", 3), (r"o'qishga\s+qo'y", 3),
                          (r"ta'?tilim(?:ning)?\s+(?:muddati\s+)?tuga", 3)]),
    ("familiya", [(r"familiya\w*\s+(?:\S+\s+){0,6}?(?:o'zgartir|almashtir)", 6), (r"nikoh", 3), (r"familiyamni", 4), (r"yangi\s+familiya", 4)]),
    ("kochirish", [(r"ko'chir", 4), (r"boshqa\s+(?:oliy|otm|universitet|institut)", 3), (r"o'qishimni\s+\S*\s*(?:universitet|institut)", 2),
                   (r"(?:universiteti|instituti|akademiyasi)ga\s+(?:o'qishimni\s+)?ko'chir", 4)]),
    ("guruh", [(r"guruh\w*\s+(?:\S+\s+){0,4}?(?:o'tkaz|almashtir|o'zgartir|ko'chir)", 5), (r"boshqa\s+guruhga", 4)]),
    ("tiklash", [(r"qayta\s+tikla", 6), (r"safiga\s+(?:qayta\s+)?tikla", 5), (r"tiklashingizni", 4)]),
    ("akademik_tatil", [(r"akademik\s+ta'?til\s+(?:ber|so'ra|ol)", 6), (r"akademik\s+ta'?til", 3)]),
    ("chetlashtirish_xohish", [(r"o'z\s+xohish", 5), (r"safidan\s+chiqar", 3), (r"chetlashtir", 3), (r"o'qishni\s+tark", 3)]),
]
KIND_NAMES = {"familiya": "Familiya o'zgartirish", "akademik_tatil": "Akademik ta'til", "tatildan_qaytish": "Akademik ta'tildan qaytish",
              "chetlashtirish_xohish": "O'z xohishi bilan chetlashtirish", "kochirish": "Boshqa OTMga ko'chirish",
              "guruh": "Guruhni o'zgartirish", "tiklash": "Qayta tiklash"}

GROUP_RX = re.compile(r"\b([A-Z]{2,5}(?:-[A-Z]{2,5})?-\d{2}[A-Z]?\d{2})\b")
HEMIS_RX = re.compile(r"(?<!\d)(\d{12,14})(?!\d)")
NAME_W = r"[A-Z][a-z']+(?:-[A-Z][a-z']+)?"
NAME_RX = re.compile(rf"({NAME_W}\s+{NAME_W}(?:\s+{NAME_W})?(?:\s+(?:o'g'li|qizi))?)")

def _kind(t: str):
    scores = []
    for k, rules in KIND_RULES:
        sc, ev = 0, []
        for rx, w in rules:
            m = re.search(rx, t)
            if m: sc += w; ev.append(m.group(0))
        if sc: scores.append((sc, k, ev))
    if not scores: return None, 0.0, [], []
    # ta'tildan qaytish arizasida «akademik ta'til» ham bor; ko'chirish arizasida «safidan chiqarish» ham — ustunlik tartibi KIND_RULES da
    order = [k for k, _ in KIND_RULES]
    scores.sort(key=lambda x: (-x[0], order.index(x[1])))
    best = scores[0]
    total = sum(s for s, _, _ in scores)
    conf = round(min(0.98, 0.45 + 0.5 * best[0] / max(total, 1) + 0.03 * best[0]), 2)
    return best[1], conf, best[2], [{"kind": k, "score": s} for s, k, _ in scores[1:4]]

def _after(t_clean: str, rx: str, n=120) -> str:
    m = re.search(rx, t_clean, re.I)
    return t_clean[m.end():m.end() + n] if m else ""

def _reason(tc: str) -> str:
    m = re.search(r"([^.,;:\n]{6,90}?)\s+(?:sababli|munosabati\s+bilan|tufayli)", tc, re.I)
    if m:
        r = m.group(1).strip()
        r = re.sub(r"^(?:men|meni|mening|menga|chunki|ya'ni|hamda|va)\s+", "", r, flags=re.I)
        r = re.sub(r"^.*?\b(?:yilda|yil)\s+", "", r) if len(r) > 60 else r
        return r[:90]
    m = re.search(r"sabab[i]?\s*[:\-]\s*([^.\n]{4,90})", tc, re.I)
    return m.group(1).strip() if m else ""

def _student_hint(tc: str) -> dict:
    hint = {"hemis": None, "name": None, "group": None, "groups": []}
    m = HEMIS_RX.search(tc)
    if m: hint["hemis"] = m.group(1)
    groups = list(dict.fromkeys(GROUP_RX.findall(tc.upper().replace("–", "-"))))
    hint["groups"] = groups
    if groups: hint["group"] = groups[0]
    pats = [rf"\b(?:Men|men),?\s+({NAME_W}\s+{NAME_W}(?:\s+{NAME_W})?(?:\s+(?:o'g'li|qizi))?)",
            rf"talaba(?:si)?\s+({NAME_W}\s+{NAME_W}(?:\s+{NAME_W})?(?:\s+(?:o'g'li|qizi))?)",
            rf"F\.?\s*I\.?\s*Sh\.?\s*[:\-]\s*({NAME_W}\s+{NAME_W}(?:\s+{NAME_W})?(?:\s+(?:o'g'li|qizi))?)",
            rf"(?:^|\n)\s*({NAME_W}\s+{NAME_W}\s+{NAME_W}\s+(?:o'g'li|qizi))(?:dan)?\b"]
    for p in pats:
        m = re.search(p, tc)
        if m:
            nm = re.sub(r"(?:dan|ning)$", "", m.group(1).strip())
            if not re.match(r"(?i)(ISFT|Instituti|Rektor|Hurmatli)", nm):
                hint["name"] = nm; break
    return hint

def detect(text: str) -> dict:
    tc0 = clean(text)
    tc = re.sub(r"[ \t]*\n[ \t]*", " ", tc0)        # maydonlar uchun bitta qator (PDF qator ko'chirishi so'zni bo'lmasin)
    t = norm(text)
    kind, conf, evidence, alts = _kind(t)
    dates = find_dates(tc)
    hint = _student_hint(tc0)
    fd = from_date(tc)
    f = {}
    if kind == "familiya":
        m = (re.search(rf"familiyam(?:ni)?\s+(?:«|\")?({NAME_W})(?:»|\")?\s*(?:-?dan)\s+(?:«|\")?({NAME_W})(?:»|\")?\s*(?:-?ga)", tc)
             or re.search(rf"({NAME_W})\s+familiyasi(?:ni|dan)?\s+(?:\S+\s+){{0,3}}?({NAME_W})\s+familiyasiga", tc))
        if m:
            f["old_surname"], f["new_surname"] = re.sub(r"dan$", "", m.group(1)), re.sub(r"ga$", "", m.group(2))
        else:
            m = re.search(rf"yangi\s+familiya(?:m)?\s*[:\-]?\s*(?:«|\")?({NAME_W})", tc, re.I) or re.search(rf"({NAME_W})\s+familiyasiga", tc)
            if m: f["new_surname"] = re.sub(r"ga$", "", m.group(1))
        b = re.search(r"(nikoh\w*\s+(?:\S+\s+){0,3}?guvohnoma\w*|nikoh\s+qayd\w*\s+\S+|ajrim\w*\s+(?:\S+\s+){0,3}?guvohnoma\w*|sud\s+qarori)"
                      r"((?:[^.\n]{0,60}?)(?:№|No\.?|N)\s*[A-Z\-]{0,6}\s*\d{4,9})?", tc, re.I)
        if b:
            basis = b.group(0).strip()
            near = [d for p, d in dates if b.start() - 10 <= p <= b.end() + 60]
            f["basis"] = basis[0].upper() + basis[1:] + (f", {near[0]}" if near else "")
    elif kind == "akademik_tatil":
        m = re.search(r"(\S+\s+\S+)\s*(?:dan|-dan)\s+(\S+\s+\S+)\s*(?:gacha|-gacha)", tc)
        if len(dates) >= 2:
            f["date_from"], f["date_to"] = dates[0][1], dates[1][1]
        elif dates:
            f["date_from"] = dates[0][1]
            d0 = dt.date.fromisoformat(dates[0][1]); f["date_to"] = (d0.replace(year=d0.year + 1) - dt.timedelta(days=1)).isoformat()
            f["_to_guess"] = True
        r = _reason(tc)
        if r: f["reason"] = r
        elif "sog'lig" in t or "tibbiy" in t or "kasal" in t: f["reason"] = "sog'lig'i bo'yicha"
        elif "farzand" in t or "homilador" in t or "tug'ruq" in t: f["reason"] = "homiladorlik va tug'ish / bola parvarishi"
        elif "harbiy" in t: f["reason"] = "muddatli harbiy xizmat"
        elif "oilaviy" in t: f["reason"] = "oilaviy sharoit"
    elif kind == "tatildan_qaytish":
        if fd: f["date_from"] = fd
        g = hint["groups"]
        if len(g) >= 2: f["group_to"] = g[-1]
    elif kind == "chetlashtirish_xohish":
        if fd: f["date_from"] = fd
        r = _reason(tc)
        if r: f["reason"] = r
    elif kind == "kochirish":
        m = re.search(r"((?:[A-Z][\w'\-]*\s+){1,7}?(?:davlat\s+)?(?:\w+\s+){0,3}?(?:universiteti|instituti|akademiyasi)(?:\s+[A-Z][\w']+\s+filiali)?)\s*(?:ga|-ga)\b", tc)
        if m: f["target"] = m.group(1).strip()
        if fd: f["date_from"] = fd
    elif kind == "guruh":
        g = hint["groups"]
        if len(g) >= 2: f["group_from"], f["group_to"] = g[0], g[1]
        elif g:
            m = re.search(r"(" + GROUP_RX.pattern[2:-2] + r")\s*(?:-?)\s*guruh(?:i)?ga", tc)
            if m: f["group_to"] = m.group(1)
        r = _reason(tc)
        if r: f["reason"] = r
    elif kind == "tiklash":
        if fd: f["date_from"] = fd
        g = hint["groups"]
        if g: f["group_to"] = g[-1]
    return {"kind": kind, "kind_name": KIND_NAMES.get(kind), "confidence": conf if kind else 0.0, "evidence": evidence[:4],
            "alternatives": [dict(a, name=KIND_NAMES.get(a["kind"])) for a in alts], "fields": f, "hint": hint,
            "dates": [d for _, d in dates][:6]}

# ---------------------------------------------------------------------------------------------
# Talabani topish
# ---------------------------------------------------------------------------------------------
def match_students(con, hint: dict, scope_sql: str = "1=1", limit=5) -> list[dict]:
    from . import db
    base = f"""SELECT s.id, s.full_name, s.hemis_id, s.status, s.study_form, s.group_id, g.name grp, g.course
               FROM students s JOIN groups_ g ON g.id=s.group_id WHERE ({scope_sql})"""
    out = {}
    if hint.get("hemis"):
        for r in db.rows(con, base + " AND s.hemis_id=?", (hint["hemis"],)):
            out[r["id"]] = dict(r, score=1.0, why="HEMIS ID mos")
    nm = hint.get("name")
    if nm:
        key = name_key(nm); toks = key.split()
        if toks:
            cand = db.rows(con, base + " AND (lower(s.full_name) LIKE ? OR lower(s.full_name) LIKE ?) LIMIT 400",
                           (f"{toks[0][:5]}%", f"% {toks[1][:5]}%" if len(toks) > 1 else f"{toks[0][:5]}%"))
            for r in cand:
                sc = difflib.SequenceMatcher(None, key, name_key(r["full_name"])).ratio()
                if len(toks) > 1 and name_key(r["full_name"]).split()[:2] == toks[:2]: sc = max(sc, 0.9)
                if hint.get("groups") and r["grp"] in hint["groups"]: sc += 0.12
                if sc < 0.62: continue
                sc = round(min(sc, 0.99), 2)
                if r["id"] not in out or out[r["id"]]["score"] < sc:
                    out[r["id"]] = dict(r, score=sc, why="F.I.Sh." + (" va guruh mos" if hint.get("groups") and r["grp"] in hint["groups"] else " o'xshash"))
    return sorted(out.values(), key=lambda r: -r["score"])[:limit]

# ---------------------------------------------------------------------------------------------
# Excel / CSV ro'yxat
# ---------------------------------------------------------------------------------------------
LIST_EXT = {".xlsx", ".xlsm", ".csv", ".txt"}
HEAD = {"hemis": ("hemis", "id raqam", "talaba id", "student id", "jshshir", "pinfl"),
        "name": ("f.i.sh", "fish", "f.i.o", "fio", "familiya", "ism", "talaba", "full name", "ф.и.ш", "ф.и.о"),
        "group": ("guruh", "group", "гурух", "группа")}

def _rows_from_file(filename: str, raw: bytes) -> list[list[str]]:
    ext = Path(filename or "").suffix.lower()
    if ext not in LIST_EXT: raise ValueError("Ro'yxat Excel (.xlsx) yoki CSV formatida bo'lishi kerak")
    if ext in (".xlsx", ".xlsm"):
        try:
            from openpyxl import load_workbook
        except ImportError:
            raise ValueError("Serverda Excel o'qish kutubxonasi (openpyxl) yo'q — ro'yxatni CSV formatida yuklang")
        try:
            wb = load_workbook(io.BytesIO(raw), read_only=True, data_only=True)
        except Exception:
            raise ValueError("Excel faylni ochib bo'lmadi")
        best = []
        for ws in wb.worksheets[:5]:
            rows = [["" if v is None else (str(int(v)) if isinstance(v, float) and v.is_integer() else str(v)).strip() for v in r]
                    for r in ws.iter_rows(values_only=True)]
            rows = [r for r in rows if any(r)]
            if len(rows) > len(best): best = rows
        wb.close()
        return best
    txt = None
    for enc in ("utf-8-sig", "cp1251"):
        try: txt = raw.decode(enc); break
        except UnicodeDecodeError: continue
    if txt is None: raise ValueError("CSV fayl kodlashi aniqlanmadi (UTF-8 bo'lishi kerak)")
    sample = txt[:4000]
    delim = max([";", ",", "\t"], key=lambda d: sample.count(d))
    return [[c.strip() for c in r] for r in csv.reader(io.StringIO(txt), delimiter=delim) if any(c.strip() for c in r)]

def parse_list(filename: str, raw: bytes) -> dict:
    """→ {rows: [{hemis, name, group, line}], columns: {...}, header: bool, skipped}"""
    rows = _rows_from_file(filename, raw)
    if not rows: raise ValueError("Faylda ma'lumot topilmadi")
    cols, hdr_i = {}, None
    for i, r in enumerate(rows[:10]):
        low = [norm(c) for c in r]
        found = {}
        for key, words in HEAD.items():
            for j, c in enumerate(low):
                if j in found.values(): continue
                if any(w in c for w in words): found[key] = j; break
        if "hemis" in found or "name" in found:
            cols, hdr_i = found, i; break
    data = rows[hdr_i + 1:] if hdr_i is not None else rows
    if hdr_i is None:   # sarlavhasiz: mazmundan
        width = max(len(r) for r in data[:50])
        for j in range(width):
            vals = [r[j] for r in data[:50] if j < len(r) and r[j]]
            if not vals: continue
            if "hemis" not in cols and sum(bool(HEMIS_RX.fullmatch(v)) for v in vals) > len(vals) * 0.6: cols["hemis"] = j
            elif "group" not in cols and sum(bool(GROUP_RX.fullmatch(v.upper())) for v in vals) > len(vals) * 0.6: cols["group"] = j
            elif "name" not in cols and sum(len(v.split()) >= 2 and not any(ch.isdigit() for ch in v) for v in vals) > len(vals) * 0.6: cols["name"] = j
    if "hemis" not in cols and "name" not in cols:
        raise ValueError("Ro'yxatda HEMIS ID yoki F.I.Sh. ustuni topilmadi (sarlavha: «HEMIS ID», «F.I.Sh.», «Guruh»)")
    out, skipped = [], 0
    get = lambda r, k: (r[cols[k]].strip() if k in cols and cols[k] < len(r) else "")
    for n, r in enumerate(data, (hdr_i or -1) + 2):
        h, nm, g = get(r, "hemis"), get(r, "name"), get(r, "group").upper()
        h = re.sub(r"\D", "", h) if h else ""
        if not h and not nm: skipped += 1; continue
        if nm and norm(nm) in ("jami", "итого", "jami:"): skipped += 1; continue
        out.append({"hemis": h or None, "name": clean(nm) or None, "group": g or None, "line": n})
    return {"rows": out, "columns": {k: v + 1 for k, v in cols.items()}, "header": hdr_i is not None, "skipped": skipped}

def match_list(con, rows: list[dict], scope_sql: str = "1=1") -> tuple[list[dict], list[dict], int]:
    """Ro'yxat qatorlarini talabalarga moslash. → (mos, mos_emas, takrorlar)"""
    from . import db
    st = db.rows(con, f"""SELECT s.id, s.hemis_id, s.full_name, s.group_id, s.study_form, s.status, g.name grp, g.course
                          FROM students s JOIN groups_ g ON g.id=s.group_id WHERE ({scope_sql})""")
    by_h = {s["hemis_id"]: s for s in st}
    by_n = {}
    for s in st: by_n.setdefault(name_key(s["full_name"]), []).append(s)
    ok, bad, seen, dup = [], [], set(), 0
    for r in rows:
        s = by_h.get(r["hemis"]) if r.get("hemis") else None
        why = "HEMIS ID"
        if not s and r.get("name"):
            c = by_n.get(name_key(r["name"]), [])
            if len(c) > 1 and r.get("group"): c = [x for x in c if x["grp"] == r["group"]]
            if len(c) == 1: s, why = c[0], "F.I.Sh." + (" + guruh" if r.get("group") else "")
        if not s:
            bad.append(dict(r, why="HEMIS ID ham, F.I.Sh. ham bazadagi talabaga mos kelmadi" if r.get("hemis") else "F.I.Sh. bo'yicha aniq topilmadi (bir nechta yoki hech kim)"))
            continue
        if s["id"] in seen: dup += 1; continue
        seen.add(s["id"])
        ok.append({"student": s, "row": r, "why": why})
    return ok, bad, dup
