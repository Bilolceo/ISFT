"""Taqdimot uchun manba material: .docx / .pdf / .txt dan matn bloklari va rasmlar (app/taqdimot.py).

Natija — bloklar ro'yxati: {"k": "h"|"p"|"li"|"img", "t": matn, "lvl": sarlavha darajasi, "img": rasm raqami}
va rasmlar ro'yxati: {"n", "file", "w", "h", "ctx"} (ctx — rasm atrofidagi matn, AI rasm joyini tanlashi uchun).
Formulalar (Word OMML, m:oMath) chiziqli matnga aylantiriladi: sSup → ^(..), sSub → _(..), f → (a)/(b), rad → √(..), nary → ∫_{a}^{b}.
Fayl turi kengaytma bo'yicha emas, «sehrli baytlar» bo'yicha aniqlanadi.
"""
from __future__ import annotations
import io, re, zipfile
from pathlib import Path
from lxml import etree

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
M = "http://schemas.openxmlformats.org/officeDocument/2006/math"
A = "http://schemas.openxmlformats.org/drawingml/2006/main"
R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
VML = "urn:schemas-microsoft-com:vml"
NS = {"w": W, "m": M, "a": A, "r": R, "v": VML}

MAX_IMAGES = 24
MIN_IMG_PX = 90          # kichik ikonka/chiziqlar tashlanadi
MIN_IMG_BYTES = 2500


class BadFile(ValueError):
    pass


def sniff(raw: bytes) -> str:
    """Fayl turi: 'docx' | 'pdf' | 'txt'; mos kelmasa — BadFile."""
    if raw[:5] == b"%PDF-":
        return "pdf"
    if raw[:4] == b"PK\x03\x04":
        try:
            with zipfile.ZipFile(io.BytesIO(raw)) as z:
                if "word/document.xml" in z.namelist():
                    return "docx"
        except zipfile.BadZipFile:
            pass
        raise BadFile("Faqat Word (.docx), PDF yoki matn (.txt) fayl qabul qilinadi")
    if b"\x00" in raw[:4096]:
        raise BadFile("Faqat Word (.docx), PDF yoki matn (.txt) fayl qabul qilinadi")
    decode_text(raw)
    return "txt"


def decode_text(raw: bytes) -> str:
    for enc in ("utf-8-sig", "utf-16") if raw[:2] in (b"\xff\xfe", b"\xfe\xff") else ("utf-8-sig", "cp1251"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    raise BadFile("Matn faylini o'qib bo'lmadi (UTF-8 kodlashda saqlang)")


# ---------------------------------------------------------------- OMML → chiziqli matn
def _m(tag):
    return f"{{{M}}}{tag}"


def omml(el) -> str:
    t = etree.QName(el).localname if isinstance(el.tag, str) else ""
    kids = lambda e: "".join(omml(c) for c in e) if e is not None else ""
    sub = lambda name: el.find(_m(name))
    if t == "t":
        return el.text or ""
    if t == "sSup":
        return f"{kids(sub('e'))}^({kids(sub('sup'))})"
    if t == "sSub":
        return f"{kids(sub('e'))}_({kids(sub('sub'))})"
    if t == "sSubSup":
        return f"{kids(sub('e'))}_({kids(sub('sub'))})^({kids(sub('sup'))})"
    if t == "f":
        return f"({kids(sub('num'))})/({kids(sub('den'))})"
    if t == "rad":
        deg = kids(sub("deg"))
        return (f"{deg}√" if deg else "√") + f"({kids(sub('e'))})"
    if t == "nary":
        pr = sub("naryPr")
        ch = pr.find(_m("chr")) if pr is not None else None
        sym = ch.get(_m("val")) if ch is not None else "∫"
        lo, hi = kids(sub("sub")), kids(sub("sup"))
        return sym + (f"_{{{lo}}}" if lo else "") + (f"^{{{hi}}}" if hi else "") + " " + kids(sub("e"))
    if t == "d":
        pr = sub("dPr")
        beg, end = "(", ")"
        if pr is not None:
            b, e = pr.find(_m("begChr")), pr.find(_m("endChr"))
            if b is not None: beg = b.get(_m("val")) or ""
            if e is not None: end = e.get(_m("val")) or ""
        return beg + ", ".join(kids(e) for e in el.findall(_m("e"))) + end
    if t in ("func",):
        return kids(sub("fName")) + kids(sub("e"))
    if t in ("rPr", "ctrlPr", "naryPr", "dPr", "fPr", "radPr", "sSupPr", "sSubPr", "funcPr", "deg") and t != "deg":
        return ""
    return "".join(omml(c) for c in el)


# ---------------------------------------------------------------- DOCX
def _docx(raw: bytes, out_dir: Path | None):
    z = zipfile.ZipFile(io.BytesIO(raw))
    doc = etree.fromstring(z.read("word/document.xml"))
    rels = {}
    if "word/_rels/document.xml.rels" in z.namelist():
        for r in etree.fromstring(z.read("word/_rels/document.xml.rels")):
            rels[r.get("Id")] = r.get("Target")
    styles = {}
    if "word/styles.xml" in z.namelist():
        for s in etree.fromstring(z.read("word/styles.xml")).iter(f"{{{W}}}style"):
            nm = s.find(f"{{{W}}}name")
            styles[s.get(f"{{{W}}}styleId")] = (nm.get(f"{{{W}}}val") if nm is not None else "") or ""
    blocks, images = [], []

    def add_image(rid):
        target = rels.get(rid)
        if not target or len(images) >= MAX_IMAGES:
            return None
        path = "word/" + target.lstrip("/") if not target.startswith("word/") else target
        path = path.replace("word/../", "")
        try:
            data = z.read(path)
        except KeyError:
            return None
        return _save_image(data, images, out_dir)

    def para(p):
        txt, imgs = [], []
        bold_all, any_run = True, False
        for node in p.iter():
            tag = etree.QName(node).localname if isinstance(node.tag, str) else ""
            if tag == "oMath" and node.getparent() is not None and etree.QName(node.getparent()).localname != "oMathPara":
                txt.append(" " + omml(node) + " ")
            elif tag == "oMathPara":
                txt.append(" " + " ".join(omml(x) for x in node.findall(_m("oMath"))) + " ")
            elif tag == "t" and node.getparent() is not None and etree.QName(node.getparent()).localname == "r" \
                    and node.getparent().getparent() is not None and etree.QName(node.getparent()).namespace == W:
                if any(etree.QName(a).localname == "oMath" for a in node.iterancestors()):
                    continue
                txt.append(node.text or "")
                any_run = True
                rpr = node.getparent().find(f"{{{W}}}rPr")
                if (node.text or "").strip() and (rpr is None or rpr.find(f"{{{W}}}b") is None):
                    bold_all = False
            elif tag == "tab" and etree.QName(node).namespace == W:
                txt.append(" ")
            elif tag == "blip":
                rid = node.get(f"{{{R}}}embed")
                n = add_image(rid)
                if n is not None: imgs.append(n)
            elif tag == "imagedata" and etree.QName(node).namespace == VML:
                n = add_image(node.get(f"{{{R}}}id"))
                if n is not None: imgs.append(n)
        text = re.sub(r"[ \t]+", " ", "".join(txt)).strip()
        ppr = p.find(f"{{{W}}}pPr")
        style = ""
        lvl = None
        is_list = False
        if ppr is not None:
            ps = ppr.find(f"{{{W}}}pStyle")
            if ps is not None:
                style = styles.get(ps.get(f"{{{W}}}val"), ps.get(f"{{{W}}}val") or "").lower()
            ol = ppr.find(f"{{{W}}}outlineLvl")
            if ol is not None:
                lvl = int(ol.get(f"{{{W}}}val") or 0) + 1
            is_list = ppr.find(f"{{{W}}}numPr") is not None
        mh = re.search(r"(heading|заголовок|sarlavha)\s*(\d)", style)
        if mh:
            lvl = int(mh.group(2))
        elif style in ("title", "название", "заголовок"):
            lvl = 1
        if lvl is None and text and any_run and bold_all and len(text) <= 120 and not text.endswith((".", ",", ";")):
            lvl = 2
        return text, lvl, is_list or "list" in style, imgs

    body = doc.find(f"{{{W}}}body")
    for el in body:
        tag = etree.QName(el).localname
        if tag == "p":
            text, lvl, is_list, imgs = para(el)
            if text:
                blocks.append({"k": "h" if lvl and lvl <= 3 else ("li" if is_list else "p"), "t": text, "lvl": lvl or 0})
            for n in imgs:
                blocks.append({"k": "img", "img": n, "t": ""})
        elif tag == "tbl":
            for tr in el.iter(f"{{{W}}}tr"):
                cells = []
                for tc in tr.iter(f"{{{W}}}tc"):
                    parts = [para(p)[0] for p in tc.iter(f"{{{W}}}p")]
                    cells.append(" ".join(x for x in parts if x))
                row = " | ".join(c for c in cells if c)
                if row:
                    blocks.append({"k": "li", "t": row, "lvl": 0})
    return blocks, images


# ---------------------------------------------------------------- PDF
def _pdf(raw: bytes, out_dir: Path | None):
    from pypdf import PdfReader
    try:
        rd = PdfReader(io.BytesIO(raw))
        if rd.is_encrypted:
            try:
                rd.decrypt("")
            except Exception:
                raise BadFile("PDF parol bilan himoyalangan")
    except BadFile:
        raise
    except Exception:
        raise BadFile("PDF faylni o'qib bo'lmadi")
    blocks, images = [], []
    for pi, page in enumerate(rd.pages):
        try:
            text = page.extract_text() or ""
        except Exception:
            text = ""
        for line in _paragraphs(text):
            blocks.append(line)
        if len(images) < MAX_IMAGES:
            try:
                for im in page.images:
                    n = _save_image(im.data, images, out_dir)
                    if n is not None:
                        blocks.append({"k": "img", "img": n, "t": ""})
                    if len(images) >= MAX_IMAGES:
                        break
            except Exception:
                pass
    return blocks, images


# ---------------------------------------------------------------- TXT
LIST_RX = re.compile(r"^\s*(?:[-•*–]|\d{1,2}[.)]|[a-z][.)])\s+")
HEAD_RX = re.compile(r"^\s*(?:#{1,3}\s+|\d{1,2}(?:\.\d{1,2})*\.?\s+[A-ZА-ЯЎҚҒҲO‘G‘])")


def _paragraphs(text: str) -> list[dict]:
    out, buf = [], []

    def flush():
        if buf:
            out.append({"k": "p", "t": re.sub(r"\s+", " ", " ".join(buf)).strip(), "lvl": 0})
            buf.clear()

    for raw_line in text.replace("\r", "").split("\n"):
        line = raw_line.strip()
        if not line:
            flush(); continue
        if line.startswith("#"):
            flush(); out.append({"k": "h", "t": line.lstrip("#").strip(), "lvl": min(3, len(line) - len(line.lstrip("#")))}); continue
        if LIST_RX.match(line):
            flush(); out.append({"k": "li", "t": LIST_RX.sub("", line).strip(), "lvl": 0}); continue
        short_upper = len(line) <= 80 and (line.isupper() or (HEAD_RX.match(line) and not line.endswith(".")))
        if short_upper and len(line) > 2:
            flush(); out.append({"k": "h", "t": line.strip(), "lvl": 1 if line.isupper() else 2}); continue
        buf.append(line)
        if line.endswith((".", "!", "?", ":")) and sum(len(b) for b in buf) > 400:
            flush()
    flush()
    return [b for b in out if b["t"]]


def _txt(raw: bytes):
    return _paragraphs(decode_text(raw)), []


# ---------------------------------------------------------------- rasmlar
def _save_image(data: bytes, images: list, out_dir: Path | None):
    if len(data) < MIN_IMG_BYTES:
        return None
    from PIL import Image
    try:
        im = Image.open(io.BytesIO(data))
        im.load()
    except Exception:
        return None
    w, h = im.size
    if w < MIN_IMG_PX or h < MIN_IMG_PX or w / max(h, 1) > 8 or h / max(w, 1) > 8:
        return None
    n = len(images)
    fmt = "png" if (im.mode in ("RGBA", "LA", "P") or (im.format or "").upper() == "PNG") else "jpg"
    if im.mode not in ("RGB", "RGBA", "L", "LA"):
        im = im.convert("RGBA" if fmt == "png" else "RGB")
    if fmt == "jpg" and im.mode != "RGB":
        im = im.convert("RGB")
    if max(w, h) > 1800:
        im.thumbnail((1800, 1800))
    name = f"img{n + 1}.{fmt}"
    if out_dir is not None:
        out_dir.mkdir(parents=True, exist_ok=True)
        im.save(out_dir / name, "PNG" if fmt == "png" else "JPEG", quality=88)
    images.append({"n": n + 1, "file": name, "w": im.size[0], "h": im.size[1], "ctx": ""})
    return n + 1


def extract(raw: bytes, kind: str, out_dir: Path | None = None) -> dict:
    """Material → {"kind", "blocks", "images", "chars"}. Rasmlar out_dir ga saqlanadi (img1.png ...)."""
    if kind == "docx":
        try:
            blocks, images = _docx(raw, out_dir)
        except BadFile:
            raise
        except Exception:
            raise BadFile("Word faylni o'qib bo'lmadi (fayl buzilgan yoki .docx emas)")
    elif kind == "pdf":
        blocks, images = _pdf(raw, out_dir)
    else:
        blocks, images = _txt(raw)
    # rasm konteksti: oldingi sarlavha + yaqin matn
    last_h, last_p = "", ""
    for b in blocks:
        if b["k"] == "h":
            last_h = b["t"]
        elif b["k"] in ("p", "li"):
            last_p = b["t"]
        elif b["k"] == "img":
            im = next((i for i in images if i["n"] == b["img"]), None)
            if im:
                im["ctx"] = (last_h + " — " if last_h else "") + last_p[:160]
    chars = sum(len(b.get("t") or "") for b in blocks)
    if chars < 40 and not images:
        raise BadFile("Materialda matn topilmadi (skaner qilingan PDF bo'lsa, matnli variantini yuklang)")
    return {"kind": kind, "blocks": blocks, "images": images, "chars": chars}


def as_text(blocks: list[dict], limit: int = 60000) -> tuple[str, bool]:
    """Bloklar → AI uchun belgilangan matn (# sarlavha, - band, [RASM n]). (matn, qisqartirildimi)."""
    out, n = [], 0
    for b in blocks:
        if b["k"] == "h":
            line = "#" * max(1, min(3, b.get("lvl") or 1)) + " " + b["t"]
        elif b["k"] == "li":
            line = "- " + b["t"]
        elif b["k"] == "img":
            line = f"[RASM {b['img']}]"
        else:
            line = b["t"]
        if n + len(line) > limit:
            return "\n".join(out), True
        out.append(line)
        n += len(line) + 1
    return "\n".join(out), False
