"""ISFT brend elementlari: ranglar (rasmiy logodan olingan), logo, rasmiy blank (letterhead) va QR.
Rasmiy logo fayli bo'lsa static/brand/logo.png ga qo'ying — barcha hujjatlarda avtomatik o'sha ishlatiladi."""
import io
from pathlib import Path
from docx.shared import Pt, RGBColor, Cm
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml.ns import qn
from docx.oxml import OxmlElement

ROOT = Path(__file__).resolve().parent.parent
BRAND_DIR = ROOT / "static" / "brand"

# isft.uz CSS'idan: asosiy firuza va to'q firuza, urg'u — to'q qizil (bordo)
TEAL, TEAL_DARK, MAROON, GOLD = "A8161E", "7A0E14", "8A6200", "FFC22D"  # rasmiy logodan: bordo, to'q bordo, oltin
RGB_TEAL_DARK = RGBColor(0x7A, 0x0E, 0x14)
RGB_TEAL = RGBColor(0xA8, 0x16, 0x1E)
RGB_MAROON = RGBColor(0x8A, 0x62, 0x00)
RGB_GREY = RGBColor(0x55, 0x5B, 0x63)

INST = {
    "uz": "ISFT INSTITUTI",
    "en": "ISFT INSTITUTE",
    "full_en": "International School of Finance and Technology",
    "address_uz": "Toshkent viloyati, Qibray tumani, Bobur MFY, Universitet ko'chasi, 7-uy. Indeks: 111200",
    "address_en": "7 University street, Bobur MCA, Kibray district, Tashkent region, 111200, Uzbekistan",
    "phone": "+998 55 508-37-37", "email": "info@isft.uz", "web": "isft.uz",
    "rector_title_uz": "Rektor", "rector_title_en": "Rector",
}

def _font(size, bold=True):
    from PIL import ImageFont
    for p in ["/System/Library/Fonts/Supplemental/Arial Bold.ttf", "/Library/Fonts/Arial Bold.ttf",
              "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"]:
        if Path(p).exists(): return ImageFont.truetype(p, size)
    return ImageFont.load_default()

def logo_png() -> Path:
    """Rasmiy logo bo'lsa o'shani, bo'lmasa sayt uslubidagi 'ISFT' so'z-belgisini (PNG) qaytaradi."""
    official = BRAND_DIR / "logo.png"
    if official.exists(): return official
    out = BRAND_DIR / "isft-mark.png"
    if out.exists(): return out
    from PIL import Image, ImageDraw
    W = H = 512
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0)); d = ImageDraw.Draw(img)
    d.rounded_rectangle((0, 0, W, H), radius=96, fill=(0x00, 0x57, 0x5B, 255))
    d.rounded_rectangle((0, H - 150, W, H), radius=96, fill=(0x00, 0x96, 0x9D, 255))
    d.rectangle((0, H - 150, W, H - 96), fill=(0x00, 0x96, 0x9D, 255))
    f = _font(170); t = "ISFT"; bb = d.textbbox((0, 0), t, font=f)
    d.text(((W - (bb[2] - bb[0])) / 2 - bb[0], 150 - bb[1]), t, font=f, fill="white")
    d.rectangle((W / 2 - 70, 345, W / 2 + 70, 357), fill=(0xFF, 0xC2, 0x2D, 255))
    img.save(out); return out

def qr_png(url: str) -> io.BytesIO:
    import qrcode
    q = qrcode.QRCode(border=1, box_size=6, error_correction=qrcode.constants.ERROR_CORRECT_M)
    q.add_data(url); q.make(fit=True)
    buf = io.BytesIO(); q.make_image(fill_color="#5c0a0f", back_color="white").save(buf, format="PNG"); buf.seek(0)
    return buf

# ---------- docx yordamchilari ----------
def shade(cell, hex_):
    tcPr = cell._tc.get_or_add_tcPr(); sh = OxmlElement("w:shd")
    sh.set(qn("w:val"), "clear"); sh.set(qn("w:color"), "auto"); sh.set(qn("w:fill"), hex_); tcPr.append(sh)

def _border(par, side="bottom", color=TEAL_DARK, sz=18):
    pPr = par._p.get_or_add_pPr(); b = OxmlElement("w:pBdr"); e = OxmlElement(f"w:{side}")
    e.set(qn("w:val"), "single"); e.set(qn("w:sz"), str(sz)); e.set(qn("w:space"), "4"); e.set(qn("w:color"), color)
    b.append(e); pPr.append(b)

def _no_borders(table):
    b = OxmlElement("w:tblBorders")
    for s in ("top", "left", "bottom", "right", "insideH", "insideV"):
        e = OxmlElement(f"w:{s}"); e.set(qn("w:val"), "nil"); b.append(e)
    _set_tblpr(table, b)

_TBLPR_ORDER = ["tblStyle", "tblpPr", "tblOverlap", "bidiVisual", "tblStyleRowBandSize", "tblStyleColBandSize", "tblW", "jc",
                "tblCellSpacing", "tblInd", "tblBorders", "shd", "tblLayout", "tblCellMar", "tblLook"]

def _set_tblpr(table, el):
    """tblPr ichiga elementni OOXML sxemasi talab qilgan tartibda joylaydi (eski nusxasini almashtiradi)."""
    tblPr = table._tbl.tblPr; name = el.tag.split("}")[1]
    for old in tblPr.findall(qn(f"w:{name}")): tblPr.remove(old)
    idx = _TBLPR_ORDER.index(name)
    for i, ch in enumerate(list(tblPr)):
        cn = ch.tag.split("}")[1]
        if cn in _TBLPR_ORDER and _TBLPR_ORDER.index(cn) > idx:
            ch.addprevious(el); return
    tblPr.append(el)

def full_width(table, widths_cm=None):
    """Jadvalni 17 sm (sahifa matn kengligi) ga yoyadi, ustunlarni qat'iy kenglikda joylaydi."""
    n = len(table.columns); widths_cm = widths_cm or [17 / n] * n
    w = OxmlElement("w:tblW"); w.set(qn("w:w"), str(int(sum(widths_cm) * 567))); w.set(qn("w:type"), "dxa"); _set_tblpr(table, w)
    lay = OxmlElement("w:tblLayout"); lay.set(qn("w:type"), "fixed"); _set_tblpr(table, lay)
    for i, gc in enumerate(table._tbl.tblGrid.findall(qn("w:gridCol"))):
        if i < len(widths_cm): gc.set(qn("w:w"), str(int(widths_cm[i] * 567)))
    for row in table.rows:
        for i, wd in enumerate(widths_cm):
            if i < len(row.cells): row.cells[i].width = Cm(wd)

def run(par, text, size=11, bold=False, color=None, italic=False):
    r = par.add_run(text); r.font.size = Pt(size); r.bold = bold; r.italic = italic
    if color is not None: r.font.color.rgb = color
    return r

def setup(doc):
    st = doc.styles["Normal"]; st.font.name = "Times New Roman"; st.font.size = Pt(12)
    st.element.rPr.rFonts.set(qn("w:eastAsia"), "Times New Roman")
    st.paragraph_format.space_after = Pt(2)
    for s in doc.sections:
        s.top_margin = Cm(1.4); s.bottom_margin = Cm(1.6); s.left_margin = Cm(2.5); s.right_margin = Cm(1.5)

def letterhead(doc, lang="uz"):
    """Rasmiy blank: logo + nom + manzil, ostida bordo chiziq."""
    t = doc.add_table(rows=1, cols=2); _no_borders(t); t.alignment = WD_TABLE_ALIGNMENT.CENTER
    full_width(t, [2.7, 14.3])
    t.rows[0].cells[0].paragraphs[0].add_run().add_picture(str(logo_png()), width=Cm(2.2))
    c = t.rows[0].cells[1]; p = c.paragraphs[0]
    run(p, INST["en" if lang == "en" else "uz"], 17, True, RGB_TEAL_DARK)
    p = c.add_paragraph(); run(p, INST["full_en"], 10, False, RGB_TEAL, italic=True)
    p = c.add_paragraph(); run(p, INST["address_en" if lang == "en" else "address_uz"], 8.5, False, RGB_GREY)
    p = c.add_paragraph(); run(p, f"Tel: {INST['phone']}  ·  {INST['email']}  ·  {INST['web']}", 8.5, False, RGB_GREY)
    line = doc.add_paragraph(); _border(line); line.paragraph_format.space_after = Pt(6)

def regline(doc, reg_no, date_str, lang="uz"):
    t = doc.add_table(rows=1, cols=2); _no_borders(t); full_width(t, [8.5, 8.5])
    run(t.rows[0].cells[0].paragraphs[0], f"{'Ref. No' if lang == 'en' else '№'} {reg_no}", 10.5, True)
    p = t.rows[0].cells[1].paragraphs[0]; p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    run(p, date_str, 10.5, True)
    doc.add_paragraph()

def title(doc, text, sub=None):
    p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.CENTER; run(p, text, 14, True, RGB_TEAL_DARK)
    if sub:
        p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.CENTER; run(p, sub, 11.5, True)
    doc.add_paragraph()

def para(doc, text, indent=True, size=12, align=WD_ALIGN_PARAGRAPH.JUSTIFY, bold=False):
    p = doc.add_paragraph(); p.alignment = align
    if indent: p.paragraph_format.first_line_indent = Cm(1.25)
    p.paragraph_format.line_spacing = 1.15
    run(p, text, size, bold); return p

def table(doc, head, rows, widths=None, size=10):
    t = doc.add_table(rows=1, cols=len(head)); t.style = "Table Grid"; t.alignment = WD_TABLE_ALIGNMENT.CENTER
    for i, h in enumerate(head):
        c = t.rows[0].cells[i]; c.text = ""; run(c.paragraphs[0], str(h), size, True, RGBColor(255, 255, 255)); shade(c, TEAL_DARK)
    for k, row in enumerate(rows):
        cells = t.add_row().cells
        for i, v in enumerate(row):
            cells[i].text = ""; run(cells[i].paragraphs[0], str(v), size)
            if k % 2: shade(cells[i], "EEF6F6")
    if widths:
        k = 17.0 / sum(widths); full_width(t, [w * k for w in widths])
    else:
        full_width(t)
    doc.add_paragraph(); return t

def signature(doc, position, name="", lang="uz"):
    doc.add_paragraph()
    t = doc.add_table(rows=1, cols=3); _no_borders(t); full_width(t, [7, 4.5, 5.5])
    run(t.rows[0].cells[0].paragraphs[0], position, 12, True)
    p = t.rows[0].cells[1].paragraphs[0]; p.alignment = WD_ALIGN_PARAGRAPH.CENTER; run(p, "_______________", 12)
    p = t.rows[0].cells[2].paragraphs[0]; p.alignment = WD_ALIGN_PARAGRAPH.RIGHT; run(p, name, 12, True)
    p = doc.add_paragraph(); run(p, "M.O." if lang == "uz" else "Seal", 10, False, RGB_GREY)

def footer_qr(doc, url, code, note):
    """Hujjat oxirida haqiqiylikni tekshirish uchun QR va kod."""
    doc.add_paragraph()
    t = doc.add_table(rows=1, cols=2); _no_borders(t); full_width(t, [2.7, 14.3])
    t.rows[0].cells[0].paragraphs[0].add_run().add_picture(qr_png(url), width=Cm(2.3))
    c = t.rows[0].cells[1]; p = c.paragraphs[0]
    run(p, note, 8.5, False, RGB_GREY)
    p = c.add_paragraph(); run(p, f"Tekshirish kodi / Verification code: {code}", 8.5, True, RGB_TEAL_DARK)
    p = c.add_paragraph(); run(p, url, 8, False, RGB_GREY)
    p = c.add_paragraph(); run(p, "JARVIS — ISFT hujjat avtomatlashtirish tizimi", 8, False, RGB_GREY, italic=True)
