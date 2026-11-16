"""Word formulalari (OMML, «m:oMath» / «m:oMathPara») → MathML Core (Chrome 109+, Firefox, Safari brauzerning o'zi chizadi — JS kutubxonasiz).

  omml_to_mathml(el, display=None) -> str     — «<math …>…</math>» (alttext — chiziqli matn, ekran o'quvchi uchun)
  omml_to_text(el) -> str                     — chiziqli matn: «a_{ij} = (x^2)/(2)», «∑_{i=1}^{n} x_i», «√(x)» (AI, qidiruv, reja)
  convert(el, display=None) -> (mathml, text)

Ma'ruza matni (docx_lecture → pk_assets.meta.text → structure_text) orqali formula BELGI sifatida o'tadi — alohida jadvalsiz (matn bilan
birga saqlanadi, chaqiruvchilar o'zgarmaydi):  «⟦m:<base64url(zlib(MathML))>|<chiziqli matn>⟧»
  marker(mathml, text)  — belgi;  linearize(s) — belgilar → chiziqli matn;  marker_html(m) — belgi → MathML (yoki zaxira: matn)
Xavfsizlik: belgidan olingan MathML ishonchsiz — chaqiruvchi (structure_text) natijani paket.sanitize() dan o'tkazadi (oq ro'yxat).

Qo'llab-quvvatlanadi: m:r/m:t (mi/mn/mo; m:sty, m:scr, m:nor), m:f (kasr; lin/skw — «a/b», noBar), m:sSub, m:sSup, m:sSubSup, m:sPre,
m:rad (daraja bilan/siz), m:nary (∑ ∫ ∏ …, chegaralar, subHide/supHide, limLoc), m:d (begChr/endChr/sepChr), m:m (matritsa → mtable),
m:eqArr, m:func, m:limLow/m:limUpp, m:acc, m:bar, m:groupChr, m:box/m:borderBox, m:phant. Noma'lum element — matni <mtext> ichida.
"""
from __future__ import annotations
import base64, html, re, zlib

M_NS = "http://schemas.openxmlformats.org/officeDocument/2006/math"
W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
MATHML_NS = "http://www.w3.org/1998/Math/MathML"
_MAX_DEPTH = 60

FUNCS = {"sin", "cos", "tan", "tg", "ctg", "cot", "cotg", "sec", "csc", "cosec", "arcsin", "arccos", "arctan", "arctg", "arcctg", "arccot",
         "sinh", "cosh", "tanh", "coth", "sh", "ch", "th", "cth", "ln", "lg", "log", "exp", "lim", "max", "min", "sup", "inf", "det", "dim",
         "mod", "gcd", "lcm", "deg", "arg", "ker", "Re", "Im", "sgn", "rank", "tr", "var", "cov", "corr", "argmax", "argmin", "liminf", "limsup"}
# «sinx», «lnx», «tgx» — nomdan keyin harf kelsa ham funksiya (Word'da m:func'siz yozilgan); qisqa/noaniq nomlar (sh, tr, Re …) — faqat alohida so'z
_FUNC_STRONG = {"sin", "cos", "tan", "tg", "ctg", "cot", "arcsin", "arccos", "arctan", "arctg", "arcctg", "sinh", "cosh", "tanh", "ln", "lg", "log", "exp", "lim"}
_FUNC_RX = re.compile(r"(?:" + "|".join(sorted(FUNCS, key=len, reverse=True)) + r")(?![^\W\d_])|(?:" + "|".join(sorted(_FUNC_STRONG, key=len, reverse=True)) + ")")
_MI_SYMS = set("∞∅ℏℓℵ∂∇")
# birikuvchi (combining) urg'u belgilari → alohida (spacing) belgi: MathML <mover> ichida
_ACC = {"̀": "`", "́": "´", "̂": "^", "̃": "~", "̄": "¯", "̅": "¯", "̆": "˘", "̇": "˙", "̈": "¨",
        "̊": "˚", "̌": "ˇ", "⃖": "←", "⃗": "→", "⃡": "↔", "⃐": "↼", "⃑": "⇀", "̲": "_"}
_ACC_NAME = {"^": "hat", "~": "tilde", "¯": "bar", "˙": "dot", "¨": "ddot", "→": "vec", "ˇ": "check", "˘": "breve"}


def _ln(el) -> str:
    t = el.tag
    if not isinstance(t, str): return ""
    return t.rsplit("}", 1)[-1]

def _ns(el) -> str:
    t = el.tag
    return t[1:].split("}", 1)[0] if isinstance(t, str) and t.startswith("{") else ""

def _m(name: str) -> str: return f"{{{M_NS}}}{name}"

def _val(parent, name: str, default=None):
    """<m:xxxPr><m:name m:val="…"/></m:xxxPr> qiymati (element bor, val yo'q — «on» belgisi uchun «1»)."""
    if parent is None: return default
    e = parent.find(_m(name))
    if e is None: return default
    v = e.get(_m("val"))
    return "1" if v is None else v

def _on(v) -> bool: return str(v or "").strip().lower() in ("1", "on", "true")

def _esc(s: str) -> str: return html.escape(s, quote=False)

def _attr(s: str) -> str: return html.escape(s, quote=True)

def _row(parts: list[str]) -> str:
    parts = [p for p in parts if p]
    if len(parts) == 1: return parts[0]
    return "<mrow>" + "".join(parts) + "</mrow>"

def _grp(t: str) -> str:
    """Daraja/indeks uchun chiziqli matn: bitta belgi/so'z — o'zi, aks holda {…}."""
    t = t.strip()
    return t if len(t) == 1 else "{" + t + "}"

def _par(t: str) -> str:
    """Kasr surat/maxraji: oddiy (so'z, son) — o'zi, aks holda (…)."""
    t = t.strip()
    return t if re.fullmatch(r"\d+(?:[.,]\d+)?|[^\W\d_]|[^\W\d_]{2,}", t) or (t[:1] + t[-1:] == "()" and t.count("(") == 1) else "(" + t + ")"


class _Conv:
    def __init__(self):
        self.depth = 0

    # ---------------------------------------------------------------- yordamchilar
    def kids(self, el, fname=False) -> tuple[str, str]:
        """Element bolalari ketma-ketligi → (mrow, matn)."""
        if el is None: return "", ""
        ml, tx = [], []
        for c in el:
            a, b = self.node(c, fname)
            if isinstance(a, list): ml.extend(a)          # m:r — belgilar ota qatoriga qo'shiladi (mo shakli — prefix/infix — to'g'ri aniqlansin)
            elif a: ml.append(a)
            tx.append(b)
        return _row(ml), "".join(tx)

    def arg(self, el, name: str, fname=False) -> tuple[str, str]:
        """Majburiy argument (m:e, m:num …): bo'sh bo'lsa ham MathML elementi kerak (<mrow></mrow>)."""
        a, b = self.kids(el.find(_m(name)) if el is not None else None, fname)
        return (a or "<mrow></mrow>"), b

    # ---------------------------------------------------------------- matn (m:r)
    def run(self, r, fname=False) -> tuple[str, str]:
        rpr = r.find(_m("rPr"))
        sty = _val(rpr, "sty")                    # p (oddiy) / b / i / bi
        scr = _val(rpr, "scr")                    # roman, script, fraktur, double-struck, sans-serif, monospace
        nor = _on(_val(rpr, "nor", "0"))          # oddiy matn (matematik emas)
        text = "".join((t.text or "") for t in r if _ln(t) == "t")
        if not text: return [], ""
        if nor: return [f"<mtext>{_esc(text)}</mtext>"], text
        variant = {"double-struck": "double-struck", "script": "script", "fraktur": "fraktur", "sans-serif": "sans-serif", "monospace": "monospace"}.get(scr or "")
        if sty == "b": variant = "bold" if not variant else variant
        elif sty == "bi": variant = "bold-italic"
        plain = sty == "p" or fname
        return self.tokens(text, variant, plain), text

    def tokens(self, text: str, variant: str | None, plain: bool) -> list[str]:
        out, i, n = [], 0, len(text)
        def mi(s, normal=False):
            v = variant or ("normal" if normal and len(s) == 1 else None)
            if v == "italic" and len(s) == 1: v = None
            return f'<mi mathvariant="{v}">{_esc(s)}</mi>' if v else f"<mi>{_esc(s)}</mi>"
        while i < n:
            ch = text[i]
            if ch.isspace(): i += 1; continue
            if ch.isdigit():
                m = re.match(r"\d+(?:[.,]\d+)*", text[i:])
                tok = m.group(0)
                out.append(f'<mn mathvariant="{variant}">{_esc(tok)}</mn>' if variant in ("bold", "double-struck") else f"<mn>{_esc(tok)}</mn>")
                i += len(tok); continue
            if ch.isalpha():
                m = re.match(r"[^\W\d_]+", text[i:])
                word = m.group(0)
                if plain:                                      # oddiy matn uslubi / funksiya nomi: so'z — bitta <mi> (tik)
                    out.append(mi(word, normal=True)); i += len(word); continue
                f = _FUNC_RX.match(text, i)
                if f and (i == 0 or not text[i - 1].isalpha()):
                    out.append(mi(f.group(0), normal=True)); i = f.end(); continue
                out.append(mi(ch)); i += 1; continue
            if ch in _MI_SYMS: out.append(mi(ch)); i += 1; continue
            if ch == "'": ch = "′"
            out.append(f"<mo>{_esc(ch)}</mo>"); i += 1
        return out

    # ---------------------------------------------------------------- tuzilmalar
    def node(self, el, fname=False) -> tuple[str, str]:
        if not isinstance(el.tag, str): return "", ""
        name, ns = _ln(el), _ns(el)
        if name.endswith("Pr") or name in ("ctrlPr", "argPr"): return "", ""
        if ns == W_NS:
            if name in ("del", "moveFrom", "rPr", "pPr", "bookmarkStart", "bookmarkEnd", "proofErr"): return "", ""
            if name == "r":
                t = "".join(x.text or "" for x in el.iter(f"{{{W_NS}}}t"))
                return (f"<mtext>{_esc(t)}</mtext>", t) if t.strip() else ("", t)
            return self.kids(el, fname)                           # w:ins, w:smartTag … — ichidagisi
        if ns != M_NS: return self.fallback(el)
        self.depth += 1
        try:
            if self.depth > _MAX_DEPTH: return self.fallback(el)
            fn = getattr(self, "m_" + name, None)
            return fn(el, fname) if fn else self.fallback(el)
        finally:
            self.depth -= 1

    def fallback(self, el) -> tuple[str, str]:
        t = re.sub(r"\s+", " ", "".join(x.text or "" for x in el.iter() if _ln(x) == "t")).strip()
        return (f"<mtext>{_esc(t)}</mtext>", t) if t else ("", "")

    def m_r(self, el, fname=False): return self.run(el, fname)
    def m_t(self, el, fname=False):
        t = el.text or ""
        return self.tokens(t, None, fname), t
    def m_oMath(self, el, fname=False): return self.kids(el, fname)
    def m_e(self, el, fname=False): return self.kids(el, fname)
    m_box = m_borderBox = m_oMath

    def m_phant(self, el, fname=False):
        a, b = self.arg(el, "e")
        show = _val(el.find(_m("phantPr")), "show", "1")
        return (f"<mphantom>{a}</mphantom>", "") if not _on(show) else (a, b)

    def m_f(self, el, fname=False):
        typ = _val(el.find(_m("fPr")), "type", "bar")
        na, nb = self.arg(el, "num"); da, db = self.arg(el, "den")
        tx = f"{_par(nb)}/{_par(db)}"
        if typ in ("lin", "skw"): return _row([na, "<mo>/</mo>", da]), tx
        lt = ' linethickness="0"' if typ == "noBar" else ""
        return f"<mfrac{lt}>{na}{da}</mfrac>", tx

    def m_sSub(self, el, fname=False):
        ea, eb = self.arg(el, "e", fname); sa, sb = self.arg(el, "sub")
        return f"<msub>{ea}{sa}</msub>", f"{eb}_{_grp(sb)}"

    def m_sSup(self, el, fname=False):
        ea, eb = self.arg(el, "e", fname); pa, pb = self.arg(el, "sup")
        return f"<msup>{ea}{pa}</msup>", f"{eb}^{_grp(pb)}"

    def m_sSubSup(self, el, fname=False):
        ea, eb = self.arg(el, "e", fname); sa, sb = self.arg(el, "sub"); pa, pb = self.arg(el, "sup")
        return f"<msubsup>{ea}{sa}{pa}</msubsup>", f"{eb}_{_grp(sb)}^{_grp(pb)}"

    def m_sPre(self, el, fname=False):
        ea, eb = self.arg(el, "e"); sa, sb = self.arg(el, "sub"); pa, pb = self.arg(el, "sup")
        return f"<mmultiscripts>{ea}<mprescripts></mprescripts>{sa}{pa}</mmultiscripts>", f"{{}}_{_grp(sb)}^{_grp(pb)}{eb}"

    def m_rad(self, el, fname=False):
        hide = _on(_val(el.find(_m("radPr")), "degHide", "0"))
        ea, eb = self.arg(el, "e")
        da, db = self.kids(el.find(_m("deg")))
        if hide or not db.strip(): return f"<msqrt>{ea}</msqrt>", f"√({eb})"
        return f"<mroot>{ea}{da}</mroot>", f"root({db}, {eb})"

    def m_nary(self, el, fname=False):
        pr = el.find(_m("naryPr"))
        ch = _val(pr, "chr", "∫") or "∫"
        loc = _val(pr, "limLoc") or ("subSup" if ch in "∫∬∭∮∯∰∱∲∳" else "undOvr")
        sub_hide, sup_hide = _on(_val(pr, "subHide", "0")), _on(_val(pr, "supHide", "0"))
        sa, sb = self.kids(el.find(_m("sub"))); pa, pb = self.kids(el.find(_m("sup")))
        ea, eb = self.arg(el, "e")
        lo = None if sub_hide or not sb.strip() else (sa or "<mrow></mrow>")
        hi = None if sup_hide or not pb.strip() else (pa or "<mrow></mrow>")
        op = f"<mo>{_esc(ch)}</mo>"
        if lo and hi: big = f"<munderover>{op}{lo}{hi}</munderover>" if loc == "undOvr" else f"<msubsup>{op}{lo}{hi}</msubsup>"
        elif lo: big = f"<munder>{op}{lo}</munder>" if loc == "undOvr" else f"<msub>{op}{lo}</msub>"
        elif hi: big = f"<mover>{op}{hi}</mover>" if loc == "undOvr" else f"<msup>{op}{hi}</msup>"
        else: big = op
        tx = ch + (f"_{_grp(sb)}" if lo else "") + (f"^{_grp(pb)}" if hi else "") + " " + eb
        return f"<mrow>{big}{ea}</mrow>", tx

    def m_d(self, el, fname=False):
        pr = el.find(_m("dPr"))
        beg, end, sep = _val(pr, "begChr", "("), _val(pr, "endChr", ")"), _val(pr, "sepChr", "|")
        beg, end, sep = (beg if beg is not None else ""), (end if end is not None else ""), (sep if sep is not None else "")
        parts, texts = [], []
        for k, e in enumerate(el.findall(_m("e"))):
            a, b = self.kids(e)
            if k: parts.append(f'<mo separator="true">{_esc(sep)}</mo>' if sep else ""); texts.append(sep + " " if sep else " ")
            parts.append(a); texts.append(b)
        mo = lambda c, f: f'<mo fence="true" form="{f}" stretchy="true">{_esc(c)}</mo>' if c else ""
        return "<mrow>" + mo(beg, "prefix") + "".join(parts) + mo(end, "postfix") + "</mrow>", beg + "".join(texts) + end

    def m_m(self, el, fname=False):
        rows, trows = [], []
        for mr in el.findall(_m("mr")):
            cells = [self.kids(e) for e in mr.findall(_m("e"))]
            rows.append("<mtr>" + "".join(f"<mtd>{a}</mtd>" for a, _ in cells) + "</mtr>")
            trows.append("[" + ", ".join(b for _, b in cells) + "]")
        return "<mtable>" + "".join(rows) + "</mtable>", "; ".join(trows)

    def m_eqArr(self, el, fname=False):
        rows, texts = [], []
        for e in el.findall(_m("e")):
            a, b = self.kids(e)
            rows.append(f"<mtr><mtd>{a}</mtd></mtr>"); texts.append(b)
        return '<mtable columnalign="left">' + "".join(rows) + "</mtable>", "; ".join(texts)

    def m_func(self, el, fname=False):
        fa, fb = self.arg(el, "fName", True); ea, eb = self.arg(el, "e")
        sp = "" if eb.lstrip().startswith(("(", "[", "{", "|")) else ' rspace="0.1667em"'      # «sin x» — ingichka bo'shliq; «f(x)» — yo'q
        return f"<mrow>{fa}<mo{sp}>\u2061</mo>{ea}</mrow>", f"{fb} {eb}" if not eb.startswith("(") else fb + eb

    def m_fName(self, el, fname=False): return self.kids(el, True)

    def m_limLow(self, el, fname=False):
        ea, eb = self.arg(el, "e", fname); la, lb = self.arg(el, "lim")
        return f"<munder>{ea}{la}</munder>", f"{eb}_{_grp(lb)}"

    def m_limUpp(self, el, fname=False):
        ea, eb = self.arg(el, "e", fname); la, lb = self.arg(el, "lim")
        return f"<mover>{ea}{la}</mover>", f"{eb}^{_grp(lb)}"

    def m_acc(self, el, fname=False):
        ch = _val(el.find(_m("accPr")), "chr", "̂") or "̂"
        ch = _ACC.get(ch, ch)
        ea, eb = self.arg(el, "e")
        nm = _ACC_NAME.get(ch)
        return f'<mover accent="true">{ea}<mo>{_esc(ch)}</mo></mover>', (f"{nm}({eb})" if nm else eb + ch)

    def m_bar(self, el, fname=False):
        pos = _val(el.find(_m("barPr")), "pos", "bot")
        ea, eb = self.arg(el, "e")
        if pos == "top": return f'<mover accent="true">{ea}<mo stretchy="true">¯</mo></mover>', f"overline({eb})"
        return f'<munder accentunder="true">{ea}<mo stretchy="true">_</mo></munder>', f"underline({eb})"

    def m_groupChr(self, el, fname=False):
        pr = el.find(_m("groupChrPr"))
        ch = _val(pr, "chr", "⏟") or "⏟"
        pos = _val(pr, "pos", "bot")
        ea, eb = self.arg(el, "e")
        mo = f'<mo stretchy="true">{_esc(ch)}</mo>'
        return (f"<mover>{ea}{mo}</mover>" if pos == "top" else f"<munder>{ea}{mo}</munder>"), eb

    def m_oMathPara(self, el, fname=False):
        maths = [x for x in el if _ln(x) == "oMath"]
        if len(maths) == 1: return self.kids(maths[0])
        rows = [self.kids(x) for x in maths]
        return "<mtable>" + "".join(f"<mtr><mtd>{a}</mtd></mtr>" for a, _ in rows) + "</mtable>", "; ".join(b for _, b in rows)


def _clean_text(t: str) -> str:
    return re.sub(r"\s+", " ", t.replace("⁡", "")).strip()

def convert(el, display: bool | None = None) -> tuple[str, str]:
    """OMML element (m:oMath yoki m:oMathPara) → (MathML, chiziqli matn). display=None — m:oMathPara bo'lsa blok, aks holda qator ichida."""
    if display is None: display = _ln(el) == "oMathPara"
    c = _Conv()
    body, text = c.node(el)
    if isinstance(body, list): body = _row(body)
    text = _clean_text(text)
    disp = ' display="block"' if display else ""
    alt = f' alttext="{_attr(text[:500])}"' if text else ""
    return f'<math{disp}{alt}>{body or "<mrow></mrow>"}</math>', text

def omml_to_mathml(el, display: bool | None = None) -> str:
    return convert(el, display)[0]

def omml_to_text(el) -> str:
    return convert(el)[1]


# =============================================================================================
# Matn ichidagi belgi: «⟦m:<base64url(zlib(MathML))>|<chiziqli matn>⟧»
# =============================================================================================
MARKER_RX = re.compile(r"⟦m:([A-Za-z0-9_\-]{4,40000})\|([^⟧\n]{0,2000})⟧")
MARKER_LINE_RX = re.compile(r"^(?:⟦m:[A-Za-z0-9_\-]{4,40000}\|[^⟧\n]{0,2000}⟧\s*)+$")
_MAX_ML = 200_000

def marker(mathml: str, text: str) -> str:
    b = base64.urlsafe_b64encode(zlib.compress(mathml.encode("utf-8"), 9)).decode("ascii").rstrip("=")
    t = re.sub(r"\s+", " ", text.replace("⟦", "[").replace("⟧", "]")).strip()[:2000]
    return f"⟦m:{b}|{t}⟧"

def decode(b64: str) -> str | None:
    """Belgidagi MathML (ishonchsiz — keyin sanitize). Buzilgan / juda katta — None."""
    try:
        raw = base64.urlsafe_b64decode(b64 + "=" * (-len(b64) % 4))
        d = zlib.decompressobj()
        out = d.decompress(raw, _MAX_ML)
        if d.unconsumed_tail: return None
        s = out.decode("utf-8")
    except Exception:
        return None
    return s if s.lstrip().startswith("<math") else None

def marker_html(m: re.Match) -> str:
    """Belgi → MathML; o'qib bo'lmasa — chiziqli matn (escape qilingan)."""
    ml = decode(m.group(1))
    return ml if ml is not None else _esc(m.group(2))

def linearize(s: str) -> str:
    """Matndagi formula belgilari → chiziqli matn (AI, iqtibos tekshiruvi, reja/sarlavha, qidiruv)."""
    s = str(s or "")
    return MARKER_RX.sub(lambda m: m.group(2), s) if "⟦m:" in s else s

def is_math_line(line: str) -> bool:
    """Qator faqat formula(lar)dan iborat (alohida qatordagi formula — blok)."""
    return "⟦m:" in line and bool(MARKER_LINE_RX.match(line.strip()))
