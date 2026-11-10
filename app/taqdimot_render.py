"""Taqdimot rejasini (outline) ISFT shablonida .pptx ga aylantirish (app/taqdimot.py).

Shablon (app/assets/taqdimot_shablon.pptx): 1 — titul (guruh ichida fan/mavzu matni), 2 — «REJA:», 3 — bo'sh kontent slaydi
(qizil sarlavha paneli, logotip, burchak bezaklari), 4 — «E'TIBORINGIZ UCHUN RAHMAT!». Kontent slaydlari 3-slayd nusxasidan
olinadi (kerakli soncha), rahmat slaydi doim oxirida qoladi.
Dizayn qoidalari (ISFT taqdimot ko'nikmasi): Times New Roman, formulalar Cambria Math; sarlavha 150,18 · 802×44 pt, oq, qalin, 26 pt;
kontent faqat x=285…920 pt (chap tomon bo'sh), pastki chegara 520 pt; aksent #B00000, och fon #FBEAEA, kulrang #F2F2F2,
izoh #595959; matn 14 pt dan kichik emas — sig'masa, slayd bo'linadi («(davomi)»).
"""
from __future__ import annotations
import copy, re
from pathlib import Path
from lxml import etree
from pptx import Presentation
from pptx.util import Pt, Emu
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR, MSO_AUTO_SIZE
from pptx.oxml.ns import qn

TEMPLATE = Path(__file__).resolve().parent / "assets" / "taqdimot_shablon.pptx"

ACCENT, CARD, GREY, NOTE, BLACK, WHITE = "B00000", "FBEAEA", "F2F2F2", "595959", "000000", "FFFFFF"
FONT, MATH = "Times New Roman", "Cambria Math"
X0, X1, Y0, Y1 = 285.0, 920.0, 86.0, 520.0
CW = X1 - X0
MIN_PT = 14
TYPES = ("title", "plan", "definition", "theory", "two_column", "steps", "example", "image", "tasks", "questions", "summary", "references")
R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"


# =============================================================================================
# Matn o'lchami (taxminiy): Times New Roman o'rtacha belgi kengligi ≈ 0.47 em (qalin ≈ 0.51 em)
# =============================================================================================
def n_lines(text: str, size: float, width: float, bold=False) -> int:
    width = max(width, 20)
    per = max(4, int(width / (size * (0.51 if bold else 0.47))))
    lines = 0
    for chunk in (text or "").split("\n"):
        cur = 0
        lines += 1
        for w in re.sub(r"\*\*|\$", "", chunk).split(" "):
            L = len(w)
            if cur == 0:
                cur = L
                while cur > per:
                    lines += 1; cur -= per
            elif cur + 1 + L <= per:
                cur += 1 + L
            else:
                lines += 1; cur = L
                while cur > per:
                    lines += 1; cur -= per
    return lines


def text_h(text: str, size: float, width: float, bold=False, indent=0.0) -> float:
    return n_lines(text, size, width - indent - 12, bold) * size * 1.2


# =============================================================================================
# Run tokenizatsiyasi: **qalin**, $formula$ (Cambria Math), formulada ^{..} / _{..} — daraja / indeks
# =============================================================================================
def runs_of(text: str):
    out = []
    bold = False
    for part in re.split(r"(\*\*)", text or ""):
        if part == "**":
            bold = not bold; continue
        segs = re.split(r"(\$[^$]+\$)", part)
        for s in segs:
            if not s:
                continue
            if s.startswith("$") and s.endswith("$") and len(s) > 2:
                out += _math_runs(s[1:-1], bold)
            else:
                out.append((s, {"b": bold}))
    return out


def _math_runs(s: str, bold: bool):
    out, i, buf = [], 0, ""
    while i < len(s):
        ch = s[i]
        if ch in "^_" and i + 1 < len(s):
            if buf: out.append((buf, {"b": bold, "m": True})); buf = ""
            j = i + 1
            if s[j] in "{(":
                close = "}" if s[j] == "{" else ")"
                depth, k = 0, j
                while k < len(s):
                    if s[k] == s[j]: depth += 1
                    elif s[k] == close:
                        depth -= 1
                        if depth == 0: break
                    k += 1
                inner = s[j + 1:k] if s[j] == "{" else s[j:k + 1]
                i = k + 1
            else:
                k = j
                while k < len(s) and (s[k].isalnum() or s[k] in "′'+-−"):
                    k += 1
                    if not s[j].isdigit() or (k < len(s) and not s[k].isdigit()): break
                inner, i = s[j:k] or s[j], max(k, j + 1)
            out.append((inner, {"b": bold, "m": True, "base": 30000 if ch == "^" else -25000}))
            continue
        buf += ch
        i += 1
    if buf:
        out.append((buf, {"b": bold, "m": True}))
    return out


# =============================================================================================
# Shakl quruvchilar
# =============================================================================================
def _rgb(h): return RGBColor.from_string(h)


def _set_ppr(p, align="l", bullet=None, spc_before=0.0, line=1.0):
    pPr = p._p.get_or_add_pPr()
    for ch in list(pPr):
        pPr.remove(ch)
    pPr.set("algn", align)
    if bullet:
        pPr.set("marL", "342900"); pPr.set("indent", "-342900")
    else:
        pPr.set("marL", "0"); pPr.set("indent", "0")
    ln = etree.SubElement(pPr, qn("a:lnSpc")); etree.SubElement(ln, qn("a:spcPct")).set("val", str(int(line * 100000)))
    sb = etree.SubElement(pPr, qn("a:spcBef")); etree.SubElement(sb, qn("a:spcPts")).set("val", str(int(spc_before * 100)))
    if bullet == "dot":
        bc = etree.SubElement(pPr, qn("a:buClr")); etree.SubElement(bc, qn("a:srgbClr")).set("val", ACCENT)
        etree.SubElement(pPr, qn("a:buFont")).set("typeface", "Arial")
        etree.SubElement(pPr, qn("a:buChar")).set("char", "•")
    else:
        etree.SubElement(pPr, qn("a:buNone"))


def _run(p, text, size, color=BLACK, bold=False, math=False, base=0, italic=False):
    r = p.add_run()
    r.text = text
    f = r.font
    f.size = Pt(size); f.bold = bool(bold); f.italic = bool(italic)
    f.color.rgb = _rgb(color)
    f.name = MATH if math else FONT
    rPr = r._r.get_or_add_rPr()
    rPr.set("lang", "uz-Latn-UZ")
    if base:
        rPr.set("baseline", str(base))
    cs = etree.SubElement(rPr, qn("a:cs")); cs.set("typeface", MATH if math else FONT)
    return r


def para(text, size, color=BLACK, bold=False, align="l", bullet=None, num=None, space=0.0, italic=False):
    return {"t": text, "size": size, "color": color, "bold": bold, "align": align, "bullet": bullet, "num": num, "space": space, "italic": italic}


def box(slide, x, y, w, h, paras, fill=None, line=None, line_w=1.0, anchor="t", inset=6, shape=MSO_SHAPE.RECTANGLE):
    if fill or line or shape != MSO_SHAPE.RECTANGLE:
        sh = slide.shapes.add_shape(shape, Pt(x), Pt(y), Pt(w), Pt(h))
        sh.shadow.inherit = False
        if fill: sh.fill.solid(); sh.fill.fore_color.rgb = _rgb(fill)
        else: sh.fill.background()
        if line: sh.line.color.rgb = _rgb(line); sh.line.width = Pt(line_w)
        else: sh.line.fill.background()
    else:
        sh = slide.shapes.add_textbox(Pt(x), Pt(y), Pt(w), Pt(h))
    tf = sh.text_frame
    tf.word_wrap = True
    tf.auto_size = MSO_AUTO_SIZE.NONE
    tf.margin_left = tf.margin_right = Pt(inset)
    tf.margin_top = tf.margin_bottom = Pt(max(2, inset * 0.6))
    tf.vertical_anchor = {"t": MSO_ANCHOR.TOP, "ctr": MSO_ANCHOR.MIDDLE, "b": MSO_ANCHOR.BOTTOM}[anchor]
    first = True
    for pd in paras:
        p = tf.paragraphs[0] if first else tf.add_paragraph()
        first = False
        _set_ppr(p, pd["align"], "dot" if pd["bullet"] == "dot" else ("num" if pd["num"] else None), pd["space"])
        if pd["num"]:
            _run(p, f"{pd['num']}.\t", pd["size"], ACCENT, True)
        for txt, st in runs_of(pd["t"]):
            _run(p, txt, pd["size"], pd["color"], pd["bold"] or st.get("b"), st.get("m"), st.get("base", 0), pd.get("italic"))
    return sh


def title_box(slide, text):
    t = (text or "").strip() or " "
    size = 26
    while size > 18 and n_lines(t, size, 790, True) > 1:
        size -= 1
    box(slide, 150, 18, 802, 44, [para(t, size, WHITE, True, "ctr")], anchor="ctr", inset=4)


# =============================================================================================
# Vertikal oqim: bloklar (matn, kartochka, formula, kichik sarlavha, ro'yxat) — o'lcham tanlanadi, sig'masa bo'linadi
# =============================================================================================
def _blocks_of(s: dict) -> list[dict]:
    b = []
    t = s.get("type")
    if s.get("text"):
        b.append({"k": "card" if t == "definition" else "text", "t": s["text"]})
    if s.get("highlight"):
        b.append({"k": "formula", "t": s["highlight"]})
    if s.get("subheading"):
        b.append({"k": "sub", "t": s["subheading"]})
    if s.get("bullets"):
        b.append({"k": "list", "items": list(s["bullets"]), "num": t in ("references",)})
    if s.get("steps"):
        b.append({"k": "list", "items": [(f"**{x.get('title')}** " if x.get("title") else "") + (x.get("text") or "") for x in s["steps"]], "num": True})
    if s.get("note"):
        b.append({"k": "note", "t": s["note"]})
    return b


def _bh(bl, size):
    """Blok balandligi (pt) berilgan asosiy shriftda."""
    if bl["k"] == "text":
        return text_h(bl["t"], size, CW) + 8
    if bl["k"] == "card":
        return text_h(bl["t"], size, CW - 20) + 22
    if bl["k"] == "formula":
        fs = max(MIN_PT + 2, size + 4)
        return text_h(bl["t"], fs, CW * 0.84 - 24) + 30
    if bl["k"] == "sub":
        return text_h(bl["t"], size + 1, CW, True) + 6
    if bl["k"] == "note":
        return text_h(bl["t"], max(MIN_PT, size - 2), CW - 20) + 18
    if bl["k"] == "list":
        return sum(text_h(x, size, CW, indent=27) + size * 0.4 for x in bl["items"]) + 6
    return 0


def _stack_fits(blocks, size):
    return sum(_bh(b, size) for b in blocks) + 6 * max(0, len(blocks) - 1) <= (Y1 - Y0)


def paginate_stack(s: dict) -> list[dict]:
    """Bloklarni sahifalarga bo'lish (14 pt da ham sig'masa). Har sahifa: {"title", "blocks", "notes"}."""
    blocks = _blocks_of(s)
    pages, cur = [], []
    avail = Y1 - Y0

    def used(bs):
        return sum(_bh(b, MIN_PT) for b in bs) + 6 * max(0, len(bs) - 1)

    queue = list(blocks)
    while queue:
        b = queue.pop(0)
        if used(cur + [b]) <= avail:
            cur.append(b); continue
        if b["k"] == "list" and len(b["items"]) > 1:
            take = []
            for it in b["items"]:
                if used(cur + [{**b, "items": take + [it]}]) <= avail:
                    take.append(it)
                else:
                    break
            if take:
                cur.append({**b, "items": take})
                rest = b["items"][len(take):]
                pages.append(cur); cur = []
                queue.insert(0, {**b, "items": rest, "start": b.get("start", 1) + len(take)})
                continue
        if b["k"] in ("text", "card") and len(b["t"]) > 300 and not cur:
            # bitta juda uzun matn — gaplar bo'yicha bo'linadi
            sents = re.split(r"(?<=[.!?])\s+", b["t"])
            half, acc = [], ""
            for sn in sents:
                if used([{**b, "t": (acc + " " + sn).strip()}]) <= avail: acc = (acc + " " + sn).strip()
                else: break
            if acc and acc != b["t"]:
                pages.append([{**b, "t": acc}])
                queue.insert(0, {**b, "t": b["t"][len(acc):].strip()})
                continue
        if cur:
            pages.append(cur); cur = []
            queue.insert(0, b)
        else:   # sig'maydigan yagona blok — qisqartiriladi
            cut = {**b}
            if "t" in b:
                t = b["t"]
                while len(t) > 40 and used([{**b, "t": t}]) > avail:
                    t = t[: int(len(t) * 0.85)].rsplit(" ", 1)[0] + "…"
                cut["t"] = t
            pages.append([cut])
    if cur:
        pages.append(cur)
    return [{"title": s.get("title", "") + (" (davomi)" if i else ""), "blocks": pg, "notes": s.get("notes", "") if i == 0 else ""}
            for i, pg in enumerate(pages)] or [{"title": s.get("title", ""), "blocks": [], "notes": s.get("notes", "")}]


def draw_stack(slide, blocks):
    size = 20
    while size > MIN_PT and not _stack_fits(blocks, size):
        size -= 1
    y = Y0
    for b in blocks:
        h = _bh(b, size)
        if b["k"] == "text":
            box(slide, X0, y, CW, h, [para(b["t"], size)])
        elif b["k"] == "card":
            box(slide, X0, y, CW, h, [para(b["t"], size)], fill=CARD, inset=10)
        elif b["k"] == "formula":
            fs = max(MIN_PT + 2, size + 4)
            w = CW * 0.84
            box(slide, X0 + (CW - w) / 2, y + 2, w, h - 4, [para(f"${b['t']}$" if "$" not in b["t"] else b["t"], fs, BLACK, False, "ctr")],
                fill=CARD, line=ACCENT, line_w=1.5, anchor="ctr", inset=10)
        elif b["k"] == "sub":
            box(slide, X0, y, CW, h, [para(b["t"], size + 1, ACCENT, True)])
        elif b["k"] == "note":
            box(slide, X0, y, CW, h, [para(b["t"], max(MIN_PT, size - 2), NOTE, italic=True)], line=ACCENT, line_w=0.75, inset=10)
        elif b["k"] == "list":
            st = b.get("start", 1)
            ps = [para(it, size, num=(st + i) if b.get("num") else None, bullet=None if b.get("num") else "dot", space=size * 0.4) for i, it in enumerate(b["items"])]
            box(slide, X0, y, CW, h, ps)
        y += h + 6


# =============================================================================================
# Maxsus maketlar
# =============================================================================================
def _chunks(items, fits):
    """items ni ketma-ket bo'laklarga ajratish: fits(list) True bo'lguncha qo'shiladi."""
    pages, cur = [], []
    for it in items:
        if cur and not fits(cur + [it]):
            pages.append(cur); cur = []
        cur.append(it)
    if cur: pages.append(cur)
    if len(pages) > 1:   # yetim sahifa bo'lmasin — teng taqsimlash (sig'sa)
        k, n = len(pages), len(items)
        sizes = [n // k + (1 if i < n % k else 0) for i in range(k)]
        even, i = [], 0
        for sz in sizes:
            even.append(items[i:i + sz]); i += sz
        if all(fits(p) for p in even):
            return even
    return pages


def paginate(s: dict) -> list[dict]:
    """Bitta reja slaydi → bir yoki bir nechta chizish sahifasi {"kind", "title", ...}."""
    t = s.get("type") or "theory"
    title = s.get("title") or ""
    notes = s.get("notes") or ""
    cont = lambda i: title + (" (davomi)" if i else "")
    if t == "two_column" and s.get("columns"):
        cols = [c for c in s["columns"][:2] if c]
        def fits(c):
            return text_h(c.get("title", ""), 17, 306, True) + sum(text_h(x, MIN_PT, 306, indent=27) + 6 for x in c.get("bullets", [])) <= (Y1 - Y0 - (text_h(s.get("text", ""), 16, CW) + 10 if s.get("text") else 0))
        if all(fits(c) for c in cols):
            return [{"kind": "two_column", "title": title, "text": s.get("text", ""), "columns": cols, "notes": notes}]
        # sig'maydi — oddiy ro'yxatga aylanadi
        bl = []
        for c in cols:
            bl += [f"**{c.get('title', '')}:** {x}" for x in c.get("bullets", [])]
        return [{"kind": "stack", **p} for p in paginate_stack({"type": "theory", "title": title, "text": s.get("text", ""), "bullets": bl, "notes": notes})]
    if t == "example":
        steps = [(f"**{x.get('title')}** " if x.get("title") else "") + (x.get("text") or "") for x in (s.get("steps") or [])]
        top = text_h(s.get("text", ""), MIN_PT, CW - 20) + 22 if s.get("text") else 0
        note_h = text_h(s.get("note", ""), MIN_PT, CW - 20) + 18 if s.get("note") else 0
        avail = Y1 - Y0 - top - note_h - 16
        fits = lambda st: sum(text_h(x, MIN_PT, 418, indent=27) + 6 for x in st) <= avail
        parts = _chunks(steps, fits) or [[]]
        out = []
        for i, st in enumerate(parts):
            last = i == len(parts) - 1
            out.append({"kind": "example", "title": cont(i), "text": s.get("text", "") if i == 0 else "", "steps": st,
                        "start": 1 + sum(len(p) for p in parts[:i]), "answer": s.get("answer", "") if last else "",
                        "check": (s.get("check") or []) if last else [], "note": s.get("note", "") if last else "", "notes": notes if i == 0 else ""})
        return out
    if t == "image":
        return [{"kind": "image", "title": title, "image": s.get("image") or 0, "caption": s.get("caption", ""),
                 "bullets": (s.get("bullets") or [])[:5], "text": s.get("text", ""), "notes": notes}]
    if t == "tasks" and s.get("cards"):
        cards = s["cards"]
        intro_h = text_h(s.get("text", ""), MIN_PT, CW) + 10 if s.get("text") else 0
        fits = lambda cs: len(cs) <= 3 and sum(text_h(c.get("title", ""), 16, CW - 20, True) + text_h(c.get("text", ""), MIN_PT, CW - 20) + 24 for c in cs) + 10 * len(cs) <= Y1 - Y0 - intro_h
        return [{"kind": "tasks", "title": cont(i), "text": s.get("text", "") if i == 0 else "", "cards": cs, "notes": notes if i == 0 else ""}
                for i, cs in enumerate(_chunks(cards, fits))]
    if t == "questions" and (s.get("bullets") or s.get("cards")):
        qs = s.get("bullets") or [c.get("text") or c.get("title") for c in s["cards"]]
        rowh = lambda q: max(60, text_h(q, 18, 562) + 14)
        fits = lambda xs: len(xs) <= 6 and sum(rowh(q) for q in xs) <= Y1 - Y0 - 10
        parts = _chunks(qs, fits)
        return [{"kind": "questions", "title": cont(i), "items": p, "start": 1 + sum(len(x) for x in parts[:i]), "notes": notes if i == 0 else ""}
                for i, p in enumerate(parts)]
    if t == "summary" and s.get("cards"):
        cards = s["cards"]
        def fits(cs):
            if len(cs) > 6: return False
            rows = [cs[i:i + 2] for i in range(0, len(cs), 2)]
            return sum(max(text_h(c.get("title", ""), 16, 290, True) + text_h(c.get("text", ""), MIN_PT, 290) + 22 for c in r) for r in rows) + 12 * len(rows) <= Y1 - Y0
        return [{"kind": "summary", "title": cont(i), "cards": cs, "notes": notes if i == 0 else ""} for i, cs in enumerate(_chunks(cards, fits))]
    if t in ("tasks", "summary") and not s.get("cards") and s.get("bullets"):
        s = {**s, "type": "theory"}
    return [{"kind": "stack", **p} for p in paginate_stack(s)]


def draw(slide, pg: dict, images_dir: Path | None):
    title_box(slide, pg.get("title"))
    k = pg["kind"]
    if k == "stack":
        draw_stack(slide, pg["blocks"])
    elif k == "two_column":
        y = Y0
        if pg.get("text"):
            h = text_h(pg["text"], 16, CW) + 10
            box(slide, X0, y, CW, h, [para(pg["text"], 16)]); y += h
        size = 18
        def colh(c, sz): return text_h(c.get("title", ""), sz + 1, 306, True) + sum(text_h(x, sz, 306, indent=27) + sz * 0.4 for x in c.get("bullets", [])) + 8
        while size > MIN_PT and max(colh(c, size) for c in pg["columns"]) > Y1 - y:
            size -= 1
        for i, c in enumerate(pg["columns"]):
            x = X0 + i * 328
            th = text_h(c.get("title", ""), size + 1, 306, True) + 4
            box(slide, x, y, 306, th, [para(c.get("title", ""), size + 1, ACCENT, True)])
            bh = Y1 - y - th
            box(slide, x, y + th, 306, bh, [para(b, size, bullet="dot", space=size * 0.4) for b in c.get("bullets", [])])
    elif k == "example":
        y = Y0
        if pg.get("text"):
            h = text_h(pg["text"], MIN_PT + 1, CW - 20) + 22
            box(slide, X0, y, CW, h, [para("**Shart.** " + pg["text"], MIN_PT + 1)], fill=CARD, inset=10); y += h + 10
        note_h = text_h(pg.get("note", ""), MIN_PT, CW - 20) + 18 if pg.get("note") else 0
        bottom = Y1 - (note_h + 8 if note_h else 0)
        size = 17
        hs = lambda sz: sum(text_h(x, sz, 418, indent=27) + sz * 0.4 for x in pg["steps"])
        while size > MIN_PT and hs(size) > bottom - y:
            size -= 1
        if pg["steps"]:
            box(slide, X0, y, 418, bottom - y, [para(x, size, num=pg["start"] + i, space=size * 0.4) for i, x in enumerate(pg["steps"])])
        ry = y
        if pg.get("answer"):
            ans = pg["answer"]
            ah = text_h(ans, 18, 180) + 46
            box(slide, 717, ry, 202, ah, [para("Javob", 16, ACCENT, True, "ctr"), para(ans if "$" in ans else f"${ans}$", 18, align="ctr", space=4)],
                line=ACCENT, line_w=2, anchor="ctr", inset=8)
            ry += ah + 12
        if pg.get("check"):
            ch = [para("Tekshiruv", 15, ACCENT, True)] + [para(c, MIN_PT, bullet="dot", space=3) for c in pg["check"][:4]]
            chh = min(bottom - ry, text_h("Tekshiruv", 15, 180, True) + sum(text_h(c, MIN_PT, 180, indent=27) + 5 for c in pg["check"][:4]) + 20)
            if chh > 40:
                box(slide, 717, ry, 202, chh, ch, fill=GREY, inset=8)
        if note_h:
            box(slide, X0, Y1 - note_h, CW, note_h, [para(pg["note"], MIN_PT, NOTE, italic=True)], line=ACCENT, line_w=0.75, inset=10)
    elif k == "image":
        _draw_image(slide, pg, images_dir)
    elif k == "tasks":
        y = Y0
        if pg.get("text"):
            h = text_h(pg["text"], MIN_PT + 1, CW) + 10
            box(slide, X0, y, CW, h, [para(pg["text"], MIN_PT + 1, NOTE)]); y += h
        for c in pg["cards"]:
            h = text_h(c.get("title", ""), 16, CW - 20, True) + text_h(c.get("text", ""), MIN_PT + 1, CW - 20) + 26
            box(slide, X0, y, CW, h, [para(c.get("title", ""), 16, ACCENT, True), para(c.get("text", ""), MIN_PT + 1, space=4)], fill=CARD, inset=10)
            y += h + 10
    elif k == "questions":
        items = pg["items"]
        size = 20
        rowh = lambda q, sz: max(58, text_h(q, sz, 562) + 14)
        while size > MIN_PT and sum(rowh(q, size) for q in items) > Y1 - Y0 - 10:
            size -= 1
        y = Y0 + 8
        for i, q in enumerate(items):
            h = rowh(q, size)
            box(slide, 299, y + (h - 46) / 2, 46, 46, [para(str(pg["start"] + i), 18, WHITE, True, "ctr")], fill=ACCENT, anchor="ctr", inset=2, shape=MSO_SHAPE.OVAL)
            box(slide, 357, y, 562, h, [para(q, size)], anchor="ctr")
            y += h
    elif k == "summary":
        cards = pg["cards"]
        rows = [cards[i:i + 2] for i in range(0, len(cards), 2)]
        size = 16
        ch = lambda c, sz: text_h(c.get("title", ""), sz + 1, 290, True) + text_h(c.get("text", ""), sz, 290) + 22
        while size > MIN_PT and sum(max(ch(c, size) for c in r) for r in rows) + 12 * len(rows) > Y1 - Y0:
            size -= 1
        y = Y0 + 4
        for r in rows:
            h = max(ch(c, size) for c in r)
            for j, c in enumerate(r):
                box(slide, X0 + j * 324, y, 310, h, [para(c.get("title", ""), size + 1, ACCENT, True), para(c.get("text", ""), size, space=3)], fill=CARD, inset=10)
            y += h + 12
    if pg.get("notes"):
        try:
            slide.notes_slide.notes_text_frame.text = pg["notes"][:4000]
        except Exception:
            pass


def _draw_image(slide, pg, images_dir):
    from PIL import Image
    n = int(pg.get("image") or 0)
    path = None
    if images_dir is not None and n:
        for ext in ("png", "jpg"):
            p = images_dir / f"img{n}.{ext}"
            if p.exists(): path = p; break
    bullets = pg.get("bullets") or []
    cap = pg.get("caption") or ""
    cap_h = text_h(cap, MIN_PT, CW) + 8 if cap else 0
    if not path:
        draw_stack(slide, _blocks_of({"type": "theory", "text": pg.get("text") or cap, "bullets": bullets}))
        return
    iw, ih = Image.open(path).size
    ratio = iw / max(ih, 1)
    if bullets or pg.get("text"):
        side = ratio < 1.35
        if side:   # rasm o'ngda, matn chapda
            bw = 300
            box_w, box_h = CW - bw - 18, Y1 - Y0 - cap_h
            w = min(box_w, box_h * ratio); h = w / ratio
            x = X0 + bw + 18 + (box_w - w) / 2
            slide.shapes.add_picture(str(path), Pt(x), Pt(Y0), Pt(w), Pt(h))
            if cap: box(slide, X0 + bw + 18, Y0 + h + 4, box_w, cap_h, [para(cap, MIN_PT, NOTE, align="ctr", italic=True)])
            blocks = _blocks_of({"type": "theory", "text": pg.get("text", ""), "bullets": bullets})
            size = 18
            hh = lambda sz: sum(text_h(b, sz, bw, indent=27) + sz * 0.4 for b in bullets) + (text_h(pg.get("text", ""), sz, bw) + 8 if pg.get("text") else 0)
            while size > MIN_PT and hh(size) > Y1 - Y0:
                size -= 1
            ps = ([para(pg["text"], size)] if pg.get("text") else []) + [para(b, size, bullet="dot", space=size * 0.4) for b in bullets]
            box(slide, X0, Y0, bw, Y1 - Y0, ps)
            return
        # keng rasm — tepada, matn pastda
        tb = ([pg["text"]] if pg.get("text") else []) + bullets
        th = sum(text_h(b, MIN_PT + 1, CW, indent=27) + 6 for b in tb) + 6
        box_h = max(150, Y1 - Y0 - th - cap_h - 6)
        w = min(CW, box_h * ratio); h = w / ratio
        slide.shapes.add_picture(str(path), Pt(X0 + (CW - w) / 2), Pt(Y0), Pt(w), Pt(h))
        y = Y0 + h + 4
        if cap: box(slide, X0, y, CW, cap_h, [para(cap, MIN_PT, NOTE, align="ctr", italic=True)]); y += cap_h
        ps = ([para(pg["text"], MIN_PT + 1)] if pg.get("text") else []) + [para(b, MIN_PT + 1, bullet="dot", space=4) for b in bullets]
        box(slide, X0, y, CW, max(30, Y1 - y), ps)
        return
    box_h = Y1 - Y0 - cap_h
    w = min(CW, box_h * ratio); h = w / ratio
    slide.shapes.add_picture(str(path), Pt(X0 + (CW - w) / 2), Pt(Y0 + (box_h - h) / 2), Pt(w), Pt(h))
    if cap:
        box(slide, X0, Y0 + (box_h + h) / 2 + 4, CW, cap_h, [para(cap, MIN_PT, NOTE, align="ctr", italic=True)])


# =============================================================================================
# Slaydlarni nusxalash / o'chirish
# =============================================================================================
def _duplicate(prs, src):
    new = prs.slides.add_slide(src.slide_layout)
    for shp in list(new.shapes):
        shp._element.getparent().remove(shp._element)
    rmap = {}
    for rid, rel in src.part.rels.items():
        if rel.reltype.endswith("/notesSlide") or rel.reltype.endswith("/slideLayout"):
            continue
        rmap[rid] = new.part.relate_to(rel._target, rel.reltype) if not rel.is_external else new.part.relate_to(rel.target_ref, rel.reltype, is_external=True)
    tree = new.shapes._spTree
    for el in src.shapes._spTree:
        if etree.QName(el).localname in ("sp", "pic", "grpSp", "cxnSp", "graphicFrame"):
            c = copy.deepcopy(el)
            for node in c.iter():
                for att, val in list(node.attrib.items()):
                    if att.startswith("{%s}" % R_NS) and val in rmap:
                        node.set(att, rmap[val])
            tree.append(c)
    return new


def _delete(prs, idx):
    lst = prs.slides._sldIdLst
    sid = list(lst)[idx]
    prs.part.drop_rel(sid.rId)
    lst.remove(sid)


# =============================================================================================
# Asosiy funksiya
# =============================================================================================
def plan_pages(outline: dict) -> list[dict]:
    pages = []
    for s in outline.get("slides") or []:
        if (s.get("type") or "") in ("title", "plan"):
            continue
        pages += paginate(s)
    return pages


def plan_items(outline: dict) -> list[str]:
    for s in outline.get("slides") or []:
        if s.get("type") == "plan" and s.get("bullets"):
            return [b for b in s["bullets"] if b][:9]
    return [s.get("title") for s in outline.get("slides") or [] if s.get("type") not in ("title", "plan", "references") and s.get("title")][:7]


def _fill_title(prs, outline):
    sl = prs.slides[0]
    target = None
    for sh in sl.shapes:
        if sh.shape_type == 6:
            for g in sh.shapes:
                if g.has_text_frame and "mavzu" in g.text_frame.text.lower():
                    target = g
    if target is None:
        return
    tf = target.text_frame
    txBody = tf._txBody
    for p in list(txBody.findall(qn("a:p"))):
        txBody.remove(p)
    subj = (outline.get("subject") or "").strip().upper()
    topic = (outline.get("title") or "").strip()
    no = str(outline.get("topic_no") or "").strip()
    sub = (outline.get("subtitle") or "").strip()
    lines = []
    if subj:
        lines.append((subj, 40 if len(subj) <= 22 else (32 if len(subj) <= 40 else 26), "FF0000", True))
    if no:
        lines.append((f"{no}-mavzu:" if not no.lower().endswith("mavzu") else no + ":", 34, BLACK, True))
    if topic:
        lines.append((topic, 30 if len(topic) <= 40 else (26 if len(topic) <= 80 else 22), BLACK, True))
    if sub:
        lines.append((sub, 22 if len(sub) <= 70 else 18, "404040", False))
    for txt, size, color, bold in lines or [(" ", 30, BLACK, True)]:
        p = etree.SubElement(txBody, qn("a:p"))
        pPr = etree.SubElement(p, qn("a:pPr")); pPr.set("algn", "ctr")
        from pptx.text.text import _Paragraph
        par = _Paragraph(p, tf)
        _run(par, txt, size, color, bold)


def _fill_plan(prs, items):
    sl = prs.slides[1]
    items = [re.sub(r"^\s*\d{1,2}\s*[.)]\s*", "", x) for x in items]     # «1. Bo'lim» → «Bo'lim» (raqam rejada o'zi qo'yiladi)
    size = 22
    hh = lambda sz: sum(text_h(x, sz, CW, indent=27) + sz * 0.5 for x in items)
    while size > MIN_PT and hh(size) > 400:
        size -= 1
    while items and hh(size) > 400:
        items = items[:-1]
    box(sl, X0, 100, CW, 400, [para(x, size, num=i + 1, space=size * 0.5) for i, x in enumerate(items)])


def render(outline: dict, out_path: Path, images_dir: Path | None = None) -> dict:
    prs = Presentation(str(TEMPLATE))
    pages = plan_pages(outline)
    _fill_title(prs, outline)
    items = plan_items(outline)
    _fill_plan(prs, items)
    proto = prs.slides[2]
    if not pages:
        _delete(prs, 2)
    else:
        slides = [proto]
        for _ in range(len(pages) - 1):
            ns = _duplicate(prs, proto)
            lst = prs.slides._sldIdLst
            me = list(lst)[-1]
            lst.remove(me)
            lst.insert(len(list(lst)) - 1, me)
            slides.append(ns)
        for sl, pg in zip(slides, pages):
            draw(sl, pg, images_dir)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    prs.save(str(out_path))
    return {"slides": len(prs.slides), "content": len(pages)}
