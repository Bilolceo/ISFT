"""Tayyor testni Word'dan import (docs/paket.md — «Tayyor testni Word'dan import»).

O'qituvchilarning testlari odatda Word'da shu ko'rinishda (Articulate Rise'ga qo'lda ko'chiriladi):

    1. “O‘zbek tilining sohada qo‘llanilishi” fanining maqsadi nima?
    A) Tilning faqat shevalarini o‘rganish
    B) O‘zbek tilining turli sohalarda qo‘llanilishini o‘rgatish ✅
    C) Faqat badiiy matnlarni yozishni o‘rgatish

To'g'ri javob belgisi: ✅ (shuningdek ✔ ✓ ☑ ✔️, «(to'g'ri)», oxiridagi « *» / « +», boshidagi «*» / «+»), «Javob: B» qatori yoki
Word'da variantning qalin / rangli fon (highlight) bilan ajratilgani (faqat matnli belgi bo'lmasa). Variantlar: «A)», «A.», «a)», «(A)»,
kirillcha «А)», «Б)»; bir qatorda bir nechta variant («A) 3  B) 4  C) 5»); Word avtomatik ro'yxati (numbering.xml: 1. / A)) ham.
Savollar «1.», «1)», «1-savol.» bilan raqamlangan yoki raqamsiz («?» bilan tugaydi yoki keyingi qatori — A variant).

Shu faylning o'zida bo'lishi mumkin:
  * «Glossariy» / «Atamalar» bo'limi — «olma - meva…», «olma — …», «olma: …» qatorlari yoki 2 ustunli jadval → moslashtirish mashqi;
  * «Savollar» / «Nazorat savollari» bo'limi — ochiq savollar → darsning topshiriq savollari.

Sof funksiyalar (baza talab qilmaydi): parse_test_docx, parse_test_text, parse_test_file, looks_like_test.
Saqlash (import_upload): savollar → Test bank (tb_questions, src='import', mavzu — darsning source_topic); bo'lim (masofaviy,
masofaviy_xodim) yuklasa — tasdiqlangan (darhol paket testiga kiradi), o'qituvchi yuklasa — qoralama (bo'lim tasdiqlaydi). Javobi
belgilanmagan savol Test bankka tushmaydi: `needs_answer` + `upload_id` bilan qaytadi (pk_import_pending'da kutadi), apply_answers («To'g'ri
javobni tanlang», POST …/test/answers) uni Test bankka yozadi (2+ to'g'ri javob — qtype «multi»). Qayta yuklash — o'sha mavzuning oldingi importi almashtiriladi.
AI izoh (ixtiyoriy): Claude ulangan bo'lsa — har bir variant uchun qisqa o'zbekcha izoh (fayl boshiga bitta so'rov; faqat savol matni va
variantlar yuboriladi, talabalar ma'lumoti yo'q). Ulanmagan bo'lsa — jim o'tkaziladi (soxta matn yo'q).
"""
from __future__ import annotations
import io, json, re, time, unicodedata, zipfile

MAX_QUESTIONS = 200
MAX_GLOSSARY = 120
MAX_LINES = 20_000
MATCH_MAX = 8                        # paket.clean_exercise: moslashtirishda 2..8 juft

# ---------------------------------------------------------------------------------------------------------------- belgilar
_AP = "['\u2018\u2019\u02bb\u02bc`\u00b4]"         # apostrof turlari (o'zbek lotin: o‘, g‘, ʼ)


def _rx(pat: str, flags=re.I) -> re.Pattern:
    """Naqshdagi «'» — har qanday apostrof (matn o'zgartirilmaydi: o'qituvchining «o‘» si saqlanadi)."""
    return re.compile(pat.replace("'", _AP), flags)


_CHECKS = "\u2705\u2714\u2713\u2611"      # ✅ ✔ ✓ ☑
_VS = "\ufe0f\ufe0e"                    # emoji variant selektorlari
_MARK_TAIL = _rx(r"(?:\s*[" + _CHECKS + r"][" + _VS + r"]?)+\s*$"
                        r"|\s*[(\[]\s*(?:to'g'ri(?:\s+javob)?|тўғри(?:\s+жавоб)?|правильн\w*|верн\w*|correct|\+)\s*[)\]]\s*$"
                        r"|\s+[*+]\s*$")
_MARK_HEAD = re.compile(r"^\s*(?:[" + _CHECKS + r"][" + _VS + r"]?|[*+])\s*")
_Q_RX = re.compile(r"^\s*(?:savol\s*)?(\d{1,3})\s*(?:-\s*savol)?\s*[.)]\s*(\S.*)$", re.I)
_OPT_LETTERS = "A-Ha-hА-Еа-еЁё"
_OPT_RX = re.compile(r"^\s*\(?([" + _OPT_LETTERS + r"])\s*[).]\s*(.*)$")
_OPT_SPLIT = re.compile(r"\s+(?=\(?[B-Hb-hБ-Еб-е]\s*\)\s*\S)")
_ANS_RX = _rx(r"^\s*(?:to'g'ri\s+)?(?:javob(?:i)?|kalit|тўғри\s+жавоб|жавоб|ответ|правильный\s+ответ|answer)\s*[:\-–—]\s*"
                     r"\(?([" + _OPT_LETTERS + r"](?:\s*[,;/ ]\s*[" + _OPT_LETTERS + r"])*)\)?\s*\.?\s*$", re.I)
_EXPL_RX = re.compile(r"^\s*(?:izoh|tushuntirish|sharh|изоҳ|пояснение|объяснение|explanation)\s*[:\-–—]\s*(\S.*)$", re.I)
_H_GLOSS = _rx(r"^\s*(?:#{1,6}\s*)?(?:[ivx\d]{1,3}[.)]\s*)?(?:glossariy|glossary|глоссарий|atamalar(?:\s+lug'ati)?|lug'at|"
                      r"tayanch\s+(?:so'z|tushuncha|ibora)lar|asosiy\s+(?:tushuncha|atama)lar|атамалар|терминлар|термины|"
                      r"основные\s+(?:понятия|термины))\s*[:.]?\s*$", re.I)
_H_OPEN = _rx(r"^\s*(?:#{1,6}\s*)?(?:[ivx\d]{1,3}[.)]\s*)?(?:nazorat\s+(?:savollari|uchun\s+savollar)|savollar|"
                     r"o'z-o'zini\s+(?:tekshirish|nazorat\s+qilish)\s+(?:uchun\s+)?savollar(?:i)?|muhokama\s+(?:uchun\s+)?savollar(?:i)?|"
                     r"ochiq\s+savollar|topshiriqlar|назорат\s+саволлари|саволлар|вопросы(?:\s+для\s+самоконтроля)?|контрольные\s+вопросы)\s*[:.]?\s*$", re.I)
_H_TEST = _rx(r"^\s*(?:#{1,6}\s*)?(?:[ivx\d]{1,3}[.)]\s*)?(?:test(?:\s+savollari|\s+topshiriqlari)?|testlar|тест(?:\s+саволлари)?|"
                     r"тесты|тестовые\s+задания)\s*[:.]?\s*$", re.I)
_BULLET = re.compile(r"^\s*(?:[-•*–—▪●◦►]\s+|\d{1,3}\s*[.)]\s*)")
_GL_SEP = re.compile(r"\s+[-–—]\s+|\s*[–—]\s*|:\s+")


def _n(s: str) -> str:
    """Qator: NFC, bo'shliqlar (shu jumladan NBSP) bitta. Apostroflar o'zgartirilmaydi (naqshlar _rx bilan hammasini taniydi)."""
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", str(s or ""))).strip()


def _strip_marks(t: str) -> tuple[str, bool]:
    """Variant matnidan to'g'ri javob belgisini olib tashlash → (matn, belgi bormidi)."""
    hit = False
    while True:
        m = _MARK_TAIL.search(t)
        if not m: break
        t2 = t[:m.start()].rstrip()
        if t2 == t or not t2: break
        t, hit = t2, True
    m = _MARK_HEAD.match(t)
    if m and t[m.end():].strip():
        t, hit = t[m.end():], True
    return t.strip(), hit


def _opt_line(line: str) -> list[tuple[str, str, bool]] | None:
    """«A) matn ✅» yoki «A) 3  B) 4 ✅  C) 5» → [(harf, matn, belgi)]; variant emas — None."""
    s, lead = line, False
    m0 = _MARK_HEAD.match(s)
    if m0 and _OPT_RX.match(s[m0.end():]): s, lead = s[m0.end():], True      # «✅ B) …», «*B) …»
    m = _OPT_RX.match(s)
    if not m: return None
    parts = [s]
    if re.search(r"[)]", s[m.end(1):]) and _OPT_SPLIT.search(s):
        parts = [p for p in _OPT_SPLIT.split(s) if p.strip()]
    out = []
    for i, p in enumerate(parts):
        mm = _OPT_RX.match(p)
        if not mm: return None if i == 0 else out
        txt, hit = _strip_marks(mm.group(2))
        out.append((mm.group(1).upper(), txt, hit or (lead and i == 0)))
    return out


def _gloss_line(line: str) -> tuple[str, str] | None:
    s = _BULLET.sub("", line, count=1).strip()
    m = _GL_SEP.search(s)
    if not m or m.start() == 0: return None
    term, d = s[:m.start()].strip(" *«»\"'"), s[m.end():].strip()
    if not term or len(d) < 2 or len(term) > 80 or len(term.split()) > 8: return None
    return term, d


# ---------------------------------------------------------------------------------------------------------------- tahlil (yadro)
def _parse_lines(lines: list[tuple[str, bool]]) -> dict:
    """[(qator, ajratilgan(qalin/rangli))] → natija. Bo'lim sarlavhalari rejimni almashtiradi: test (standart), glossariy, ochiq savollar."""
    qs, gloss, openq, warns = [], [], [], []
    used = 0
    L = [(_n(t), bool(e)) for t, e in lines[:MAX_LINES]]
    L = [(t, e) for t, e in L if t]
    mode = "test"
    cur = None

    def nxt_is_opt_a(i):
        if i + 1 >= len(L): return False
        o = _opt_line(L[i + 1][0])
        return bool(o) and o[0][0] in ("A", "А")

    def close():
        nonlocal cur
        if cur is None: return
        if len(cur["options"]) >= 2:
            qs.append(cur)
        elif cur["options"]:
            warns.append(f"«{cur['stem'][:60]}» — faqat bitta variant; savol tashlandi")
        else:                                   # variantsiz savol — ochiq savol (topshiriq)
            if cur["stem"].rstrip().endswith("?"): openq.append(cur["stem"])
        cur = None

    for i, (t, emph) in enumerate(L):
        if _H_GLOSS.match(t): close(); mode = "gloss"; used += 1; continue
        if _H_OPEN.match(t): close(); mode = "open"; used += 1; continue
        if _H_TEST.match(t): close(); mode = "test"; used += 1; continue
        mq = _Q_RX.match(t)
        if mode != "test" and mq and nxt_is_opt_a(i): close(); mode = "test"      # sarlavhasiz test bo'limi
        if mode == "gloss":
            g = _gloss_line(t)
            if g: gloss.append(g); used += 1
            continue
        if mode == "open":
            if mq or _BULLET.match(t) or (t.endswith("?") and (not openq or openq[-1].endswith(("?", ".", "!")))):
                openq.append(_BULLET.sub("", t, count=1).strip()); used += 1
            elif openq: openq[-1] = (openq[-1] + " " + t).strip(); used += 1          # ko'p qatorli savol
            continue
        # --- test rejimi
        if cur is not None:
            ma = _ANS_RX.match(t)
            if ma and cur["options"]:
                cur["key"] = [x.upper() for x in re.findall(r"[" + _OPT_LETTERS + r"]", ma.group(1))]; used += 1; continue
            me = _EXPL_RX.match(t)
            if me and cur["options"]:
                cur["explanation"] = (cur["explanation"] + " " + me.group(1)).strip(); used += 1; continue
            o = _opt_line(t)
            if o:
                for letter, txt, hit in o:
                    cur["options"].append({"letter": letter, "text": txt, "mark": hit, "emph": emph and len(o) == 1})
                used += 1; continue
        if mq:
            close()
            stem, _ = _strip_marks(mq.group(2))
            cur = {"stem": stem, "options": [], "key": [], "explanation": "", "num": int(mq.group(1))}; used += 1; continue
        if cur is not None and not cur["options"]:
            cur["stem"] = (cur["stem"] + " " + t).strip(); used += 1; continue          # ko'p qatorli savol matni
        if t.endswith("?") or nxt_is_opt_a(i):
            close()
            cur = {"stem": t, "options": [], "key": [], "explanation": "", "num": None}; used += 1; continue
        # boshqa matn (sarlavha, kirish) — e'tiborsiz
    close()

    out_q = []
    for k, q in enumerate(qs[:MAX_QUESTIONS], 1):
        opts = [o["text"] for o in q["options"]]
        corr = [j for j, o in enumerate(q["options"]) if o["mark"]]
        how = "belgi"
        if not corr and q["key"]:
            letters = [o["letter"] for o in q["options"]]
            corr = sorted({letters.index(x) for x in q["key"] if x in letters}); how = "kalit"
        if not corr:
            em = [j for j, o in enumerate(q["options"]) if o["emph"]]
            if 0 < len(em) < len(opts): corr, how = em, "format"
        label = f"{k}-savol"
        if not corr:
            how = ""
            warns.append(f"{label}: to'g'ri javob belgilanmagan (✅) — «To'g'ri javobni tanlang» oynasida belgilang")
        if any(not o for o in opts): warns.append(f"{label}: bo'sh variant bor")
        out_q.append({"stem": q["stem"], "options": opts, "correct": corr, "qtype": "multi" if len(corr) > 1 else "mcq",
                      "explanation": q["explanation"], "marked_by": how})
    if len(qs) > MAX_QUESTIONS: warns.append(f"Savollar ko'p — birinchi {MAX_QUESTIONS} tasi olindi")
    seen, gl = set(), []
    for term, d in gloss:
        key = term.casefold()
        if key in seen: warns.append(f"Glossariy: «{term[:40]}» takrorlangan — birinchisi olindi"); continue
        seen.add(key); gl.append({"term": term, "def": d})
    oq, so = [], set()
    for x in openq:
        x = x.strip()
        if x and x.casefold() not in so: so.add(x.casefold()); oq.append(x)
    return {"questions": out_q, "glossary": gl[:MAX_GLOSSARY], "open_questions": oq, "warnings": warns,
            "stats": {"lines": len(L), "used": used}}


def parse_test_text(text: str) -> dict:
    """Oddiy matn (.txt, PDF matni) → {"questions", "glossary", "open_questions", "warnings", "stats"}."""
    return _parse_lines([(ln, False) for ln in str(text or "").replace("\r", "\n").split("\n")])


# ---------------------------------------------------------------------------------------------------------------- Word
_W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_LETTER_FMTS = {"upperLetter": "ABCDEFGH", "lowerLetter": "abcdefgh", "russianUpper": "АБВГДЕЖЗ", "russianLower": "абвгдежз"}


def _on(el) -> bool:
    v = (el.get(f"{{{_W}}}val") or "").strip().lower()
    return v not in ("0", "false", "off", "none")


def docx_lines(raw: bytes) -> list[tuple[str, bool]]:
    """Word → [(qator, ajratilgan)]: ajratilgan — paragrafning barcha matnli qismlari qalin yoki rangli fon (highlight / shading) bilan.
    Avtomatik ro'yxat raqami/harfi (numbering.xml) matn boshiga qo'shiladi («1. », «A) »). Jadval: 2 ustunli qator — «chap — o'ng»."""
    from lxml import etree
    W = _W
    z = zipfile.ZipFile(io.BytesIO(raw))
    names = set(z.namelist())
    parser = etree.XMLParser(resolve_entities=False, no_network=True, huge_tree=False)
    doc = etree.fromstring(z.read("word/document.xml"), parser)
    num_fmt = {}                                   # (numId, ilvl) → numFmt
    if "word/numbering.xml" in names:
        nx = etree.fromstring(z.read("word/numbering.xml"), parser)
        absf = {}
        for an in nx.findall(f"{{{W}}}abstractNum"):
            aid = an.get(f"{{{W}}}abstractNumId")
            for lv in an.findall(f"{{{W}}}lvl"):
                f = lv.find(f"{{{W}}}numFmt")
                absf[(aid, lv.get(f"{{{W}}}ilvl"))] = f.get(f"{{{W}}}val") if f is not None else "decimal"
        for nm in nx.findall(f"{{{W}}}num"):
            a = nm.find(f"{{{W}}}abstractNumId")
            if a is None: continue
            for (aid, lvl), f in absf.items():
                if aid == a.get(f"{{{W}}}val"): num_fmt[(nm.get(f"{{{W}}}numId"), lvl)] = f
    sbold, snum = {}, {}                           # uslub: qalinmi; uslubdagi avtomatik ro'yxat (List Number …) — (numId, ilvl)
    if "word/styles.xml" in names:
        for st in etree.fromstring(z.read("word/styles.xml"), parser).iter(f"{{{W}}}style"):
            b = st.find(f"{{{W}}}rPr/{{{W}}}b")
            if b is not None: sbold[st.get(f"{{{W}}}styleId")] = _on(b)
            sn = st.find(f"{{{W}}}pPr/{{{W}}}numPr")
            if sn is not None:
                ni, il = sn.find(f"{{{W}}}numId"), sn.find(f"{{{W}}}ilvl")
                if ni is not None: snum[st.get(f"{{{W}}}styleId")] = (ni.get(f"{{{W}}}val"), il.get(f"{{{W}}}val") if il is not None else "0")

    def run_emph(r, pstyle_bold):
        rpr = r.find(f"{{{W}}}rPr")
        if rpr is None: return pstyle_bold
        b = rpr.find(f"{{{W}}}b")
        hl = rpr.find(f"{{{W}}}highlight")
        if hl is not None and (hl.get(f"{{{W}}}val") or "none").lower() not in ("none", "white"): return True
        sh = rpr.find(f"{{{W}}}shd")
        if sh is not None and (sh.get(f"{{{W}}}fill") or "auto").lower() not in ("auto", "ffffff", "none", ""): return True
        if b is not None: return _on(b)
        rs = rpr.find(f"{{{W}}}rStyle")
        if rs is not None and sbold.get(rs.get(f"{{{W}}}val")): return True
        return pstyle_bold

    counters, out = {}, []

    def para(p):
        ppr = p.find(f"{{{W}}}pPr")
        pstyle_bold, prefix = False, ""
        if ppr is not None:
            ps = ppr.find(f"{{{W}}}pStyle")
            sid = ps.get(f"{{{W}}}val") if ps is not None else None
            pstyle_bold = bool(sbold.get(sid))
            npr = ppr.find(f"{{{W}}}numPr")
            nid, lvl = snum.get(sid, (None, "0"))
            if npr is not None:
                ni, il = npr.find(f"{{{W}}}numId"), npr.find(f"{{{W}}}ilvl")
                if ni is not None: nid = ni.get(f"{{{W}}}val")
                if il is not None: lvl = il.get(f"{{{W}}}val")
            if nid:
                f = num_fmt.get((nid, lvl))
                if f and nid != "0":
                    k = (nid, lvl)
                    counters[k] = counters.get(k, 0) + 1
                    for kk in [x for x in counters if x[0] == nid and int(x[1]) > int(lvl)]: counters.pop(kk)     # quyi darajalar qaytadan
                    n = counters[k]
                    if f in _LETTER_FMTS: prefix = (_LETTER_FMTS[f][n - 1] if n <= 8 else "?") + ") "
                    elif f in ("decimal", "decimalZero"): prefix = f"{n}. "
                    elif f == "bullet": prefix = "- "
        txt, emph_all, any_t = [], True, False
        for r in p.iter(f"{{{W}}}r"):
            for ch in r:
                tag = etree.QName(ch).localname if isinstance(ch.tag, str) else ""
                if tag == "t":
                    s = ch.text or ""; txt.append(s)
                    if s.strip():
                        any_t = True
                        if not run_emph(r, pstyle_bold): emph_all = False
                elif tag in ("tab", "br", "cr"): txt.append(" ")
        text = re.sub(r"\s+", " ", "".join(txt)).strip()
        if not text: return None
        if prefix and not (_OPT_RX.match(text) or _Q_RX.match(text)): text = prefix + text
        return text, any_t and emph_all

    body = doc.find(f"{{{W}}}body")

    def walk(parent):
        for el in parent:
            tag = etree.QName(el).localname if isinstance(el.tag, str) else ""
            if tag == "sdt":
                c = el.find(f"{{{W}}}sdtContent")
                if c is not None: walk(c)
            elif tag == "p":
                r = para(el)
                if r: out.append(r)
            elif tag == "tbl":
                start = len(out)
                for tr in el.iter(f"{{{W}}}tr"):
                    cells = []
                    for tc in tr.findall(f"{{{W}}}tc"):
                        ps = [para(p) for p in tc.iter(f"{{{W}}}p")]
                        cells.append([x for x in ps if x])
                    flat = [" ".join(t for t, _ in c) for c in cells]
                    if len(cells) == 2 and all(flat):
                        if _rx(r"\W*(atama|termin|tushuncha|so'z|term|термин|атама)\W*").fullmatch(_n(flat[0])): continue   # sarlavha qatori
                        out.append((f"{flat[0]} — {flat[1]}", False))
                    else:
                        for c in cells: out.extend(c)
                pairs = [ln for ln, _ in out[start:] if " — " in ln]
                if len(pairs) >= 2 and len(pairs) == len(out) - start:
                    out.insert(start, ("Glossariy", False))          # 2 ustunli jadval — glossariy (sarlavhasiz bo'lsa ham)
            if len(out) > MAX_LINES: return

    walk(body)
    return out


def parse_test_docx(raw: bytes) -> dict:
    return _parse_lines(docx_lines(raw))


def _pdf_text(raw: bytes) -> str:
    from pypdf import PdfReader
    rd = PdfReader(io.BytesIO(raw))
    if rd.is_encrypted: rd.decrypt("")
    out = []
    for pg in rd.pages[:200]:
        try: out.append(pg.extract_text() or "")
        except Exception: pass
    return "\n".join(out)


def sniff(raw: bytes) -> str | None:
    if raw[:5] == b"%PDF-": return "pdf"
    if raw[:4] == b"PK\x03\x04":
        try:
            with zipfile.ZipFile(io.BytesIO(raw)) as z:
                return "docx" if "word/document.xml" in z.namelist() else None
        except zipfile.BadZipFile:
            return None
    if b"\x00" in raw[:4096]: return None
    return "txt"


def parse_test_file(raw: bytes, kind: str | None = None) -> dict:
    """.docx / .pdf / .txt → natija (tur tarkibdan aniqlanadi). O'qib bo'lmasa — ValueError (o'zbekcha)."""
    kind = kind or sniff(raw)
    try:
        if kind == "docx": return parse_test_docx(raw)
        if kind == "pdf": return parse_test_text(_pdf_text(raw))
        if kind == "txt":
            from . import taqdimot_extract as EX
            return parse_test_text(EX.decode_text(raw))
    except ValueError:
        raise
    except Exception as e:
        raise ValueError(f"Faylni o'qib bo'lmadi ({type(e).__name__}) — Word (.docx), PDF yoki .txt bo'lsin") from e
    raise ValueError("Faqat Word (.docx), PDF yoki matn (.txt) fayl qabul qilinadi")


def is_test(res: dict) -> bool:
    """Natija «test fayli»mi: ≥ 2 ta to'g'ri javobi belgilangan savol va faylning asosiy qismi (≥ 50% qatorlar) — test/glossariy/savollar
    (ma'ruza matni oxiridagi kichik test bo'limi ma'ruzani testga aylantirmaydi)."""
    marked = sum(1 for q in res["questions"] if q["correct"] and len(q["options"]) >= 2)
    st = res.get("stats") or {}
    return marked >= 2 and st.get("used", 0) >= 0.5 * max(1, st.get("lines", 0))


def looks_like_test(raw: bytes, kind: str | None = None) -> bool:
    try: return is_test(parse_test_file(raw, kind))
    except Exception: return False


# ---------------------------------------------------------------------------------------------------------------- AI izoh (ixtiyoriy)
AI_SCHEMA = {"type": "object", "additionalProperties": False, "required": ["items"], "properties": {"items": {"type": "array", "items": {
    "type": "object", "additionalProperties": False, "required": ["n", "explanation", "option_feedback"],
    "properties": {"n": {"type": "integer"}, "explanation": {"type": "string"}, "option_feedback": {"type": "array", "items": {"type": "string"}}}}}}}
AI_SYSTEM = ("Sen oliy ta'lim muassasasi uchun test savollariga izoh yozuvchi metodistsan. Har bir savol uchun: explanation — to'g'ri javob nega "
             "to'g'ri ekanini 1–2 gapda; option_feedback — har bir variant uchun (tartibda, variantlar soniga teng) talaba shu variantni "
             "tanlaganda ko'radigan qisqa izoh (1 gap): to'g'ri bo'lsa — nega to'g'ri, noto'g'ri bo'lsa — xatosi nimada. O'zbek tilida (lotin), "
             "aniq va xushmuomala. Faqat berilgan savol va variantlar asosida; yangi fakt to'qima. To'g'ri javoblarni o'zgartirma.")
AI_MAX_Q = 60


def _L(i: int) -> str: return "ABCDEFGH"[i] if 0 <= i < 8 else str(i + 1)


def ai_feedback(questions: list[dict], subject: str = "", topic: str = "", call=None) -> tuple[dict, dict]:
    """[{stem, options, correct}] (faqat javobi belgilanganlar) → ({indeks: {"explanation", "option_feedback"}}, info).
    call — claude_client.call_json (testda almashtiriladi). Xato — claude_client.AIError."""
    from . import claude_client as CC
    from . import testbank as TB
    call = call or CC.call_json
    items = [(i, q) for i, q in enumerate(questions) if q.get("correct")][:AI_MAX_Q]
    if not items: return {}, {"in": 0, "out": 0, "model": TB.model_name()}
    body = "\n\n".join(f"{n}. {q['stem']}\n" + "\n".join(f"{_L(j)}) {o}" + (" [TO'G'RI]" if j in q["correct"] else "") for j, o in enumerate(q["options"]))
                       for n, (_, q) in enumerate(items, 1))
    prompt = (f"Fan: {subject or '—'}\nMavzu: {topic or '—'}\n"
              f"Quyidagi {len(items)} ta test savoli uchun izohlar yoz (n — savol raqami).\n<savollar>\n{body}\n</savollar>")
    data, info = call(model=TB.model_name(), system=AI_SYSTEM, content=[{"type": "text", "text": prompt}], schema=AI_SCHEMA,
                      max_tokens=min(32000, 1200 + 350 * len(items)), effort="low", timeout=240, what="test izohlari")
    out = {}
    for it in (data or {}).get("items") or []:
        try: n = int(it.get("n"))
        except (TypeError, ValueError): continue
        if not 1 <= n <= len(items): continue
        idx, q = items[n - 1]
        fb = [re.sub(r"\s+", " ", str(x or "")).strip()[:300] for x in (it.get("option_feedback") or [])]
        if len(fb) != len(q["options"]): fb = []
        ex = re.sub(r"\s+", " ", str(it.get("explanation") or "")).strip()[:600]
        if ex or fb: out[idx] = {"explanation": ex, "option_feedback": fb}
    return out, info


def _explanation(base: str, fb: dict | None, opts: list, corr: list) -> str:
    """Savol izohi: fayldagi izoh (bo'lsa) yoki AI izohi + noto'g'ri variantlar bo'yicha qisqa izohlar («B: …»)."""
    if base: return base[:2000]
    if not fb: return ""
    parts = [fb.get("explanation") or ""]
    for j, t in enumerate(fb.get("option_feedback") or []):
        if t and j not in corr: parts.append(f"{_L(j)}: {t}")
    return " ".join(p for p in parts if p)[:2000]


# ---------------------------------------------------------------------------------------------------------------- saqlash (paket → Test bank)
def _ai_explanations(c, cid: int, tno: int, co: dict, les: dict, qs: list[dict], report: dict, warns: list) -> dict:
    """Claude ulangan bo'lsa — javobi belgilangan va izohsiz savollarga izoh (bitta so'rov; tb_gen'ga yoziladi). {qs ichidagi o'rin: {...}}. Ulanmagan — {}."""
    from . import claude_client as CC, testbank as TB
    fb = {}
    if not (qs and CC.has_key() and any(q["correct"] and not q["explanation"] for q in qs)): return fb
    t0 = time.time(); info = {"in": 0, "out": 0, "model": TB.model_name()}; err = None
    try:
        fb, info = ai_feedback([q if not q["explanation"] else {**q, "correct": []} for q in qs], co.get("subject") or "", les.get("title") or "")
        report["ai"] = True
    except CC.AIError as e:
        err = str(e); warns.append(f"AI izoh yozilmadi: {e}")
    except Exception as e:
        err = type(e).__name__; warns.append("AI izoh yozilmadi (kutilmagan javob)")
    try:
        with TB._lock:
            TB._con.execute("INSERT INTO tb_gen(course_id,topic_no,user_id,day,ts,engine,model,ok,ms,err,in_tok,out_tok,n_req,n_got) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                            (cid, tno or 0, c.user["id"], TB.clock.today().isoformat(), TB._now(), "claude-izoh", info.get("model"), 0 if err else 1,
                             int((time.time() - t0) * 1000), err, info.get("in", 0), info.get("out", 0), len(qs), len(fb)))
            TB._con.commit()
    except Exception as e:
        print("test_import tb_gen:", repr(e))
    return fb


def _store_questions(c, cid: int, tno: int, qs: list[dict], fb: dict, name: str, report: dict, replace: bool) -> None:
    """Savollarni Test bankka yozish. replace — shu mavzuning oldingi importi (src='import') o'chiriladi (faqat yuklashda; javob belgilashda — yo'q).
    Bo'lim (masofaviy, masofaviy_xodim) — tasdiqlangan (blokirovkasi va javobi bor bo'lsa), o'qituvchi — qoralama. «multi» — ko'p javobli."""
    from . import testbank as TB, db
    dept = c.role.key in TB.DEPT
    with TB._lock:
        now = TB._now()
        if replace:
            old = [r["id"] for r in db.rows(TB._con, "SELECT id FROM tb_questions WHERE course_id=? AND topic_no=? AND src='import' AND deleted=0", (cid, tno))]
            for qid in old:
                TB._con.execute("UPDATE tb_questions SET deleted=1, updated_at=? WHERE id=?", (now, qid)); TB._log(qid, c, "o'chirildi", f"qayta import: {name[:80]}")
            report["replaced"] = len(old)
        others = TB._others(cid)
        for i, q in enumerate(qs):
            qt = "multi" if len(q["correct"]) > 1 else "mcq"
            rec = {"qtype": qt, "stem": q["stem"], "options": q["options"], "correct": q["correct"],
                   "explanation": _explanation(q["explanation"], fb.get(i), q["options"], q["correct"]), "difficulty": "orta", "bloom": "eslash"}
            if fb.get(i): report["explanations"] += 1
            qid = TB._insert(cid, tno, rec, c.user, status="qoralama", engine="import", src="import", source=None, others=others)
            others.append((qid, q["stem"]))
            flags = json.loads(db.one(TB._con, "SELECT flags FROM tb_questions WHERE id=?", (qid,))["flags"] or "[]")
            block = TB.blocking(flags)
            ok_ = dept and q["correct"] and not block
            if ok_:
                TB._con.execute("UPDATE tb_questions SET flags=?, blocking=0, status='tasdiqlandi', reviewer_id=?, reviewer_name=?, reviewed_at=?, review_note=? WHERE id=?",
                                (json.dumps(flags, ensure_ascii=False), c.user["id"], c.user["full_name"], now, "Word'dan import (bo'lim)", qid))
                report["approved"] += 1
            else:
                TB._con.execute("UPDATE tb_questions SET flags=?, blocking=? WHERE id=?", (json.dumps(flags, ensure_ascii=False), int(block), qid))
                report["draft"] += 1
                if not q["correct"]: report["no_answer_ids"].append(qid)
            q["qid"] = qid
            TB._log(qid, c, "yaratildi", f"Word'dan import: {name[:80]}" + (" · tasdiqlandi" if ok_ else ""))
            report["saved"] += 1
        TB._con.commit()


# --- javobi belgilanmagan savollar: Test bankka tushmaydi, serverda (pk_import_pending) «To'g'ri javobni tanlang» qadamini kutadi
def _pend_load(row: dict) -> list[dict]:
    try: return json.loads(row["items"] or "[]")
    except ValueError: return []


def _needs(items: list[dict]) -> list[dict]:
    return [{"i": it["i"], "n": it["i"] + 1, "stem": it["stem"], "options": it["options"]} for it in items if it.get("state") == "kutilmoqda"]


def pending_state(c, cid: int, no: int) -> dict:
    """Mavzuning kutayotgan (javobi belgilanmagan) savollari: {"upload_id", "file", "needs_answer": [...]} (yo'q bo'lsa — bo'sh ro'yxat)."""
    from . import paket as PK, db
    co = PK._course(c, cid, write=True); les = PK._check_topic(co, no)
    tno = PK.source_topic(les)
    r = db.one(PK._con, "SELECT * FROM pk_import_pending WHERE course_id=? AND topic_no=? AND status='kutilmoqda' ORDER BY created_at DESC, rowid DESC LIMIT 1", (cid, tno or 0))
    if not r: return {"upload_id": None, "file": None, "needs_answer": []}
    return {"upload_id": r["upload_id"], "file": r["file"], "needs_answer": _needs(_pend_load(r))}


def pending_count(cid: int, tno: int) -> int:
    from . import paket as PK, db
    try:
        r = db.one(PK._con, "SELECT items FROM pk_import_pending WHERE course_id=? AND topic_no=? AND status='kutilmoqda' ORDER BY created_at DESC, rowid DESC LIMIT 1", (cid, tno or 0))
    except Exception: return 0
    return len(_needs(_pend_load(r))) if r else 0


def _hold(c, cid: int, tno: int, name: str, unanswered: list[dict]) -> str:
    """Javobsiz savollarni ushlab turish: oldingi kutayotgan yuklash «almashtirildi» bo'ladi; yangisi — upload_id bilan."""
    import secrets
    from . import paket as PK
    uid_ = secrets.token_hex(8)
    items = [{"i": q["i"], "stem": q["stem"], "options": q["options"], "explanation": q["explanation"], "state": "kutilmoqda", "qid": None} for q in unanswered]
    with PK._lock:
        PK._con.execute("UPDATE pk_import_pending SET status='almashtirildi' WHERE course_id=? AND topic_no=? AND status='kutilmoqda'", (cid, tno))
        PK._con.execute("INSERT INTO pk_import_pending(upload_id,course_id,topic_no,user_id,file,created_at,status,items) VALUES(?,?,?,?,?,?,?,?)",
                        (uid_, cid, tno, c.user["id"], name[:160], PK._now(), "kutilmoqda", json.dumps(items, ensure_ascii=False)))
        PK._con.commit()
    return uid_


def _clear_pending(cid: int, tno: int) -> None:
    from . import paket as PK
    with PK._lock:
        PK._con.execute("UPDATE pk_import_pending SET status='almashtirildi' WHERE course_id=? AND topic_no=? AND status='kutilmoqda'", (cid, tno))
        PK._con.commit()


def import_upload(c, cid: int, no: int, raw: bytes, kind: str, name: str) -> dict:
    """«Dars tayyorlash» → yuklangan test fayli: javobi belgilangan savollar → Test bank (darsning manba mavzusi), glossariy → moslashtirish mashqi,
    ochiq savollar → topshiriq savollari. Javobi belgilanmagan savollar Test bankka TUSHMAYDI — `needs_answer` ro'yxati va `upload_id` bilan
    qaytadi (serverda ushlab turiladi); `apply_answers` (POST …/test/answers) ularni belgilangan javob bilan Test bankka qo'shadi.
    Qayta yuklash — oldingi import almashtiriladi. → hisobot (soni, ogohlantirishlar)."""
    from fastapi import HTTPException
    from . import paket as PK, testbank as TB, rbac, db
    co = PK._course(c, cid, write=True); les = PK._check_topic(co, no)
    PK._zip_guard(raw)
    try: res = parse_test_file(raw, kind)
    except ValueError as e: raise HTTPException(415, str(e))
    qs, gl, oq, warns = res["questions"], res["glossary"], res["open_questions"], list(res["warnings"])
    if not qs and not gl and not oq:
        raise HTTPException(400, "Faylda test savollari topilmadi. Namuna: «1. Savol matni?» va keyingi qatorlarda «A) …», «B) … ✅» "
                                 "(to'g'ri javob ✅ bilan belgilanadi). Ma'ruza matni bo'lsa — «Ma'ruza matni» sifatida yuklang")
    for i, q in enumerate(qs): q["i"] = i
    answered, unanswered = [q for q in qs if q["correct"]], [q for q in qs if not q["correct"]]
    tno = PK.source_topic(les)
    report = {"ok": True, "file": name[:160], "topic_no": tno, "questions": len(qs), "without_answer": len(unanswered),
              "multi": sum(1 for q in qs if q["qtype"] == "multi"), "approved": 0, "draft": 0, "replaced": 0, "saved": 0, "no_answer_ids": [],
              "upload_id": None, "needs_answer": [], "glossary": len(gl), "exercises": 0, "open_questions": len(oq), "explanations": 0, "ai": False}
    # --- savollar → Test bank (javobi belgilanganlari); javobsizlari — serverda ushlanadi
    if qs and not tno:
        warns.append("Bu dars mavzuga bog'lanmagan — test savollari Test bankka saqlanmadi (darsni mavzuga bog'lang va qayta yuklang)")
    elif qs:
        fb = _ai_explanations(c, cid, tno, co, les, answered, report, warns)
        _store_questions(c, cid, tno, answered, fb, name, report, replace=True)
        if unanswered:
            report["upload_id"] = _hold(c, cid, tno, name, unanswered)
            report["needs_answer"] = _needs([{**q, "state": "kutilmoqda"} for q in unanswered])
            warns.append(f"{len(unanswered)} ta savolning to'g'ri javobi belgilanmagan — «To'g'ri javobni tanlang» oynasida belgilang (belgilamaguningizcha Test bankka tushmaydi)")
        else:
            _clear_pending(cid, tno)
        if report["draft"] and c.role.key in TB.DEPT:
            warns.append(f"{report['draft']} ta savol qoralama qoldi (xatosi bor) — Test bankda tuzatib tasdiqlang")
        elif report["draft"]:
            warns.append("Savollar Test bankka qoralama sifatida saqlandi — Masofaviy ta'lim bo'limi tasdiqlagach testga kiradi")
    # --- glossariy → moslashtirish mashqi (8 juftdan)
    with PK._lock:
        prev = [r["id"] for r in db.rows(PK._con, "SELECT id FROM pk_exercises WHERE course_id=? AND topic_no=? AND src='import' AND deleted=0", (cid, no))]
        for eid in prev: PK._con.execute("UPDATE pk_exercises SET deleted=1, updated_at=? WHERE id=?", (PK._now(), eid))
        PK._con.commit()
    if len(gl) == 1: warns.append("Glossariyda bitta atama — moslashtirish uchun kamida 2 ta kerak")
    if len(gl) >= 2:
        chunks = [gl[k:k + MATCH_MAX] for k in range(0, len(gl), MATCH_MAX)]
        if len(chunks) > 1 and len(chunks[-1]) < 2: chunks[-2] = chunks[-2][:-1]; chunks[-1] = [gl[len(gl) - 2]] + chunks[-1]
        seen_r = set()
        for k, ch in enumerate(chunks, 1):
            pairs = []
            for g in ch:
                key = g["def"].casefold()[:200]
                if key in seen_r: continue
                seen_r.add(key); pairs.append({"left": g["term"], "right": g["def"]})
            if len(pairs) < 2: continue
            title = "Atamalarni ta'riflari bilan moslashtiring" + (f" ({k})" if len(chunks) > 1 else "")
            try:
                r = PK.save_exercise(c, cid, no, "match", {"stem": title, "pairs": pairs})
                with PK._lock:
                    PK._con.execute("UPDATE pk_exercises SET src='import' WHERE id=?", (r["exercise"]["id"],)); PK._con.commit()
                report["exercises"] += 1
            except HTTPException as e:
                warns.append(f"Glossariy mashqi saqlanmadi: {e.detail}")
    # --- ochiq savollar → topshiriq
    if oq:
        items = [x[:PK.ASSIGN_ITEM_MAX] for x in oq][:PK.ASSIGN_MAX]
        PK.set_assignment(c, cid, no, items)
        if len(oq) > PK.ASSIGN_MAX: warns.append(f"Ochiq savollar ko'p — birinchi {PK.ASSIGN_MAX} tasi topshiriqqa olindi")
    with PK._lock:
        PK._log(c, cid, no, "test import qilindi", f"{name[:80]} · {len(qs)} savol · {len(gl)} atama · {len(oq)} ochiq savol"); PK._con.commit()
    rbac.audit(PK._con, c, "paket: test import (Word)", PK.RES, True,
               f"kurs #{cid} · {les['code']} · {name[:60]} · savol {len(qs)} (tasdiq {report['approved']}, qoralama {report['draft']}, javobsiz {len(unanswered)}) · atama {len(gl)} · ochiq {len(oq)}")
    report["warnings"] = warns[:50]
    report["items"] = [{"stem": q["stem"][:200], "n_options": len(q["options"]), "correct": q["correct"], "qtype": q["qtype"], "marked_by": q["marked_by"]} for q in qs[:MAX_QUESTIONS]]
    return report


def apply_answers(c, cid: int, no: int, upload_id: str, answers) -> dict:
    """«To'g'ri javobni tanlang» natijasi → Test bank. answers: [{"i": savol indeksi, "correct": [variant indekslari]} | {"i": …, "skip": true}].
    Tekshiriladi (butun so'rov — hammasi yoki hech narsa): upload_id mavzuga tegishli va eskirmagan; i — kutayotgan savollardan, takrorlanmagan;
    correct — bo'sh emas, noyob, variantlar oralig'ida (≥ 2 tasi belgilansa — ko'p javobli «multi»; hammasi to'g'ri bo'lmaydi). Belgilangan savol —
    yuklashdagidek (bo'lim — tasdiqlangan, o'qituvchi — qoralama); «o'tkazib yuborish» — javobsiz qoralama (Test bankda keyin tanlanadi).
    Takroriy so'rov dublikat yaratmaydi: allaqachon qayta ishlangan i — `already` ga sanaladi. → hisobot."""
    from fastapi import HTTPException
    from . import paket as PK, testbank as TB, rbac, db
    co = PK._course(c, cid, write=True); les = PK._check_topic(co, no)
    tno = PK.source_topic(les)
    if not isinstance(answers, list) or not answers: raise HTTPException(400, "Javoblar ro'yxati bo'sh")
    if len(answers) > MAX_QUESTIONS: raise HTTPException(400, f"Bir martada ko'pi bilan {MAX_QUESTIONS} ta savol")
    row = db.one(PK._con, "SELECT * FROM pk_import_pending WHERE upload_id=? AND course_id=?", (str(upload_id or "")[:64], cid))
    if not row or row["topic_no"] != (tno or 0): raise HTTPException(404, "Yuklash topilmadi — faylni qayta yuklang")
    if row["status"] == "almashtirildi": raise HTTPException(409, "Bu yuklash eskirgan (shu mavzuga yangi test fayli yuklangan) — joriy savollarni oching yoki faylni qayta yuklang")
    items = _pend_load(row); by_i = {it["i"]: it for it in items}
    plan, seen = [], set()
    for k, a in enumerate(answers, 1):
        if not isinstance(a, dict) or isinstance(a.get("i"), bool) or not isinstance(a.get("i"), int) or a["i"] not in by_i:
            raise HTTPException(400, f"{k}-javob: savol indeksi noto'g'ri")
        if a["i"] in seen: raise HTTPException(400, f"{a['i'] + 1}-savol javobi takrorlangan")
        seen.add(a["i"]); it = by_i[a["i"]]
        if a.get("skip") is True: plan.append((it, None)); continue
        cr = a.get("correct")
        if not isinstance(cr, list) or not cr or any(isinstance(x, bool) or not isinstance(x, int) for x in cr):
            raise HTTPException(400, f"{a['i'] + 1}-savol: kamida bitta to'g'ri javob belgilang (yoki «O'tkazib yuborish»)")
        cr = sorted(set(cr))
        if cr[0] < 0 or cr[-1] >= len(it["options"]): raise HTTPException(400, f"{a['i'] + 1}-savol: variant raqami oralig'idan tashqarida")
        if len(cr) > 1 and len(cr) == len(it["options"]): raise HTTPException(400, f"{a['i'] + 1}-savol: hamma variant to'g'ri bo'lishi mumkin emas")
        plan.append((it, cr))
    # --- band qilish: parallel takroriy so'rov bir xil savolni ikki marta yozmasin
    todo = []
    with PK._lock:
        fresh = db.one(PK._con, "SELECT items, status FROM pk_import_pending WHERE upload_id=?", (row["upload_id"],))
        if fresh["status"] == "almashtirildi": raise HTTPException(409, "Bu yuklash eskirgan (shu mavzuga yangi test fayli yuklangan)")
        cur = {it["i"]: it for it in _pend_load(fresh)}
        for it, cr in plan:
            if cur[it["i"]]["state"] == "kutilmoqda": cur[it["i"]]["state"] = "saqlanmoqda"; todo.append((cur[it["i"]], cr))
        PK._con.execute("UPDATE pk_import_pending SET items=? WHERE upload_id=?", (json.dumps(list(cur.values()), ensure_ascii=False), row["upload_id"]))
        PK._con.commit()
    report = {"ok": True, "upload_id": row["upload_id"], "topic_no": tno, "saved": 0, "answered": sum(1 for _, cr in todo if cr), "skipped": sum(1 for _, cr in todo if not cr),
              "already": len(plan) - len(todo), "approved": 0, "draft": 0, "multi": sum(1 for _, cr in todo if cr and len(cr) > 1), "no_answer_ids": [],
              "explanations": 0, "ai": False, "replaced": 0}
    warns: list = []
    done_ids = {}
    try:
        qs = [{"stem": it["stem"], "options": it["options"], "correct": cr or [], "explanation": it["explanation"], "_it": it} for it, cr in todo]
        if qs:
            fb = _ai_explanations(c, cid, tno, co, les, qs, report, warns)
            _store_questions(c, cid, tno, qs, fb, row["file"] or "test", report, replace=False)
            done_ids = {q["_it"]["i"]: q.get("qid") for q in qs}
    except BaseException:
        with PK._lock:          # yiqilsa — band qilish qaytariladi (qayta urinish mumkin)
            cur = {it["i"]: it for it in _pend_load(db.one(PK._con, "SELECT items FROM pk_import_pending WHERE upload_id=?", (row["upload_id"],)))}
            for it, _ in todo:
                if cur.get(it["i"], {}).get("state") == "saqlanmoqda" and it["i"] not in done_ids: cur[it["i"]]["state"] = "kutilmoqda"
            PK._con.execute("UPDATE pk_import_pending SET items=? WHERE upload_id=?", (json.dumps(list(cur.values()), ensure_ascii=False), row["upload_id"]))
            PK._con.commit()
        raise
    with PK._lock:
        cur = {it["i"]: it for it in _pend_load(db.one(PK._con, "SELECT items FROM pk_import_pending WHERE upload_id=?", (row["upload_id"],)))}
        cr_of = {it["i"]: cr for it, cr in todo}
        for i, qid in done_ids.items():
            cur[i]["state"] = "saqlandi" if cr_of[i] else "otkazildi"; cur[i]["qid"] = qid
        left = [it for it in cur.values() if it["state"] == "kutilmoqda"]
        PK._con.execute("UPDATE pk_import_pending SET items=?, status=? WHERE upload_id=?",
                        (json.dumps(list(cur.values()), ensure_ascii=False), "kutilmoqda" if left else "tugadi", row["upload_id"]))
        PK._log(c, cid, no, "test javoblari belgilandi", f"{(row['file'] or '')[:60]} · belgilandi {report['answered']} · o'tkazildi {report['skipped']}"); PK._con.commit()
    rbac.audit(PK._con, c, "paket: test javoblari belgilandi", PK.RES, True,
               f"kurs #{cid} · {les['code']} · belgilandi {report['answered']} (tasdiq {report['approved']}, qoralama {report['draft'] - report['skipped']}) · "
               f"o'tkazildi {report['skipped']} · avval {report['already']} · qoldi {len(left)}")
    report["remaining"] = len(left)
    report["needs_answer"] = _needs(left)
    report["warnings"] = warns
    return report
