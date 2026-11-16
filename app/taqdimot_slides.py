"""Taqdimot rejasi (outline) → slayd rasmlari (PNG) va ko'p sahifali PDF — LibreOffice'siz, tashqi xizmatsiz, tarmoqsiz (Pillow).

Nima uchun: Railway'da LibreOffice yo'q (docs/paket.md «Tashqi vositalar»), shuning uchun .pptx ni rasmga aylantirib bo'lmaydi. BIZ yaratgan taqdimotning
tuzilmasi (outline) va ISFT shablon qoidalari ma'lum — slaydni bevosita shundan chizamiz. O'qituvchi yuklagan tayyor .pptx uchun bu modul ISHLATILMAYDI
(python-pptx bilan taxminiy render qilinmaydi).

Mantiq nusxalanmagan: bo'linish («(davomi)»), o'lcham tanlash va joylashuv — app/taqdimot_render.py dagi `plan_pages` / `draw` ning o'zi. U slaydga `box(...)` va
`_pic(...)` orqali chizadi; bu yerdagi `Canvas` shu chaqiruvlarni (`canvas_box`, `canvas_picture`) PNG ga chizadi, pptx esa python-pptx shakllariga. Shuning uchun PNG
va .pptx bir xil sahifalarga bo'linadi (PDF sahifa soni = pptx slaydlari soni).

Koordinatalar — pt (slayd 960×540 pt), PNG — W×H px (standart 1600×900; 1 pt = W/960 px). Matn 14 pt dan kichik emas (≈23 px), asosiy matn 20 pt ≈ 33 px.
Shriftlar (app/assets/fonts, OFL): Liberation Serif (Times New Roman bilan metrik mos) va formulalar uchun STIX General (Cambria Math o'rniga).
Shrift fayllari topilmasa — tizim shriftlari, u ham bo'lmasa Pillow'ning ichki shrifti (xato bermaydi, faqat ko'rinish soddaroq).
"""
from __future__ import annotations
import io, re, threading
from functools import lru_cache
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

from . import taqdimot_render as RD

ASSETS = Path(__file__).resolve().parent / "assets"
FONT_DIR = ASSETS / "fonts"
LOGO = ASSETS / "isft_logo.png"
W, H = 1600, 900                    # standart o'lcham (16:9); PT = px / pt
SLIDE_W, SLIDE_H = 960.0, 540.0
LINE = 1.2                          # qator balandligi (× shrift) — taqdimot_render.text_h bilan bir xil
MIN_FIT = 0.8                       # sig'masa shrift ko'pi bilan shu darajagacha kichraytiriladi (taqdimot_render sahifani bo'lgan bo'lishi kerak)
MAX_IMG_PX = 60_000_000             # rasm bombasidan himoya

_SYS = {
    "serif": ["/System/Library/Fonts/Supplemental/Times New Roman.ttf", "/usr/share/fonts/truetype/liberation/LiberationSerif-Regular.ttf",
              "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf", "/usr/share/fonts/dejavu/DejaVuSerif.ttf"],
    "serif_b": ["/System/Library/Fonts/Supplemental/Times New Roman Bold.ttf", "/usr/share/fonts/truetype/liberation/LiberationSerif-Bold.ttf",
                "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf", "/usr/share/fonts/dejavu/DejaVuSerif-Bold.ttf"],
    "serif_i": ["/System/Library/Fonts/Supplemental/Times New Roman Italic.ttf", "/usr/share/fonts/truetype/liberation/LiberationSerif-Italic.ttf",
                "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Italic.ttf"],
    "math": ["/System/Library/Fonts/Supplemental/STIXGeneral.otf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/usr/share/fonts/dejavu/DejaVuSans.ttf"],
}
_OWN = {"serif": "LiberationSerif-Regular.ttf", "serif_b": "LiberationSerif-Bold.ttf", "serif_i": "LiberationSerif-Italic.ttf", "math": "STIXGeneral.ttf"}
_LOCK = threading.Lock()            # FreeType shrift obyektlari ulashiladi — keshni to'ldirish bir oqimda


def _font_path(kind: str) -> str | None:
    p = FONT_DIR / _OWN[kind]
    if p.is_file():
        return str(p)
    for c in _SYS.get(kind, []):
        if Path(c).is_file():
            return c
    return None


@lru_cache(maxsize=256)
def _font(kind: str, px: int):
    path = _font_path(kind)
    try:
        if path:
            return ImageFont.truetype(path, px, layout_engine=ImageFont.Layout.BASIC)
    except Exception:
        pass
    try:
        return ImageFont.load_default(px)
    except Exception:
        return ImageFont.load_default()


@lru_cache(maxsize=4096)
def _covers(kind: str, ch: str) -> bool:
    """Shriftda belgi bor-yo'qligi: «yo'q glif» (notdef) tasviri bilan solishtiriladi."""
    if ch.isspace() or ord(ch) < 128:
        return True
    f = _font(kind, 40)
    try:
        return bytes(f.getmask(ch)) != bytes(f.getmask("￿"))
    except Exception:
        return True


def _pick(kind: str, ch: str) -> str:
    """Belgi uchun shrift: asosiysida bor bo'lsa — o'sha; yo'qsa — boshqa (formula ↔ matn); hech birida yo'q bo'lsa — asosiysi."""
    if _covers(kind, ch):
        return kind
    for alt in (("serif", "serif_b") if kind == "math" else ("math",)):
        if _covers(alt, ch):
            return alt if alt != "serif_b" or kind == "serif_b" else "serif"
    return kind


def _rgb(h: str):
    h = (h or "000000").lstrip("#")
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


# =============================================================================================
# Matn tartibi: abzats → so'zlar → qatorlar
# =============================================================================================
def _flat(runs, bold: bool, scale: float = 1.0, dy_em: float = 0.0):
    """Run'lar → (matn, uslub, masshtab, dy/em). Daraja/indeks ichidagi daraja/indeks ham (e^{x^{2}}) — pastroq o'lchamda, birin-ketin."""
    for txt, st in runs:
        base = st.get("base", 0)
        sc = scale * (0.65 if base else 1.0)
        dy = dy_em + (-0.33 * scale if base > 0 else (0.2 * scale if base < 0 else 0.0))
        if base and re.search(r"[\^_]", txt) and scale > 0.3:
            yield from _flat(RD._math_runs(txt, bool(bold or st.get("b"))), bold, sc, dy)
        else:
            yield txt, st, sc, dy


def _words(text: str, size_pt: float, color: str, bold: bool, italic: bool, k: float):
    """Abzats matni → so'zlar ro'yxati; so'z — [(matn, shrift_turi, px, rang, dy_px)], bo'shliq — None. **qalin**, $formula$, daraja/indeks (RD.runs_of)."""
    words, cur = [], []
    px_full = size_pt * k
    for txt, st, sc, dy_em in _flat(RD.runs_of(text), bold):
        isb = bool(bold or st.get("b"))
        math = bool(st.get("m"))
        px = max(6, round(px_full * sc))
        dy = dy_em * px_full
        kind = "math" if math else ("serif_b" if isb else ("serif_i" if italic else "serif"))
        for tok in re.findall(r" +|[^ ]+", txt):
            if tok[0] == " ":
                if cur:
                    words.append(cur); cur = []
                words.append(None)
                continue
            piece, pk = "", None
            for ch in tok:
                fk = _pick(kind, ch)
                if pk is not None and fk != pk:
                    cur.append((piece, pk, px, color, dy)); piece = ""
                pk = fk; piece += ch
            if piece:
                cur.append((piece, pk, px, color, dy))
    if cur:
        words.append(cur)
    return words


def _wlen(word) -> float:
    return sum(_font(fk, px).getlength(t) for t, fk, px, _c, _d in word)


def _split_long(word, avail: float):
    """Qatorga sig'maydigan uzun so'z — belgilab bo'linadi."""
    out, cur, w = [], [], 0.0
    for t, fk, px, c, d in word:
        for ch in t:
            cw = _font(fk, px).getlength(ch)
            if cur and w + cw > avail:
                out.append(cur); cur, w = [], 0.0
            cur.append((ch, fk, px, c, d)); w += cw
    if cur:
        out.append(cur)
    return out


def _wrap(words, avail: float):
    """So'zlar → qatorlar [(so'zlar ro'yxati, kenglik)]; bo'shliq kengligi — oldingi so'z shriftidan."""
    lines, cur, cw, last_sp = [], [], 0.0, 0.0
    pending_sp = 0.0
    for w in words:
        if w is None:
            pending_sp = pending_sp or last_sp or 0.0
            continue
        parts = _split_long(w, avail) if _wlen(w) > avail else [w]
        for pi, part in enumerate(parts):
            wl = _wlen(part)
            sp = pending_sp if cur and pi == 0 else 0.0
            if cur and cw + sp + wl > avail + 0.5:
                lines.append((cur, cw)); cur, cw, sp = [], 0.0, 0.0
            if cur:
                cur.append(("sp", sp)); cw += sp
            cur.append(part); cw += wl
        pending_sp = 0.0
        t, fk, px, _c, _d = parts[-1][-1]
        last_sp = _font(fk, px).getlength(" ")
    if cur or not lines:
        lines.append((cur, cw))
    return lines


def _layout(paras, inner_w: float, k: float, f: float):
    """Matn tartibi f (≤ 1) shrift koeffitsiyentida: → (elementlar, umumiy balandlik px). Element: dict(x, y (qator tepasi), h, size_px, ...)."""
    out, y = [], 0.0
    for pi, pd in enumerate(paras):
        size = pd["size"] * f
        lh = size * LINE * k
        if pi:
            y += (pd.get("space") or 0.0) * k
        ind = 27.0 * k if (pd.get("bullet") or pd.get("num")) else 0.0
        chunks = (pd["t"] or "").split("\n")
        first = True
        for ch in chunks:
            lines = _wrap(_words(ch, size, pd["color"], pd["bold"], pd.get("italic"), k), max(10.0, inner_w - ind))
            for li, (parts, w) in enumerate(lines):
                x0 = ind
                if pd["align"] == "ctr":
                    x0 = ind + (inner_w - ind - w) / 2
                elif pd["align"] == "r":
                    x0 = inner_w - w
                out.append({"x": x0, "y": y, "lh": lh, "size_px": size * k, "parts": parts,
                            "mark": (pd, size) if (first and li == 0 and (pd.get("bullet") or pd.get("num"))) else None})
                y += lh
            first = False
    return out, y


def _draw_line(d: ImageDraw.ImageDraw, x: float, base_y: float, parts):
    for part in parts:
        if part and part[0] == "sp":
            x += part[1]
            continue
        for t, fk, px, c, dy in part:
            f = _font(fk, px)
            d.text((x, base_y + dy), t, font=f, fill=_rgb(c), anchor="ls")
            x += f.getlength(t)


class Canvas:
    """Bitta slayd: taqdimot_render.draw() chaqiradigan canvas_box / canvas_picture ni PNG ga chizadi."""

    def __init__(self, width: int = W):
        self.w = int(width)
        self.h = int(round(width * SLIDE_H / SLIDE_W))
        self.k = self.w / SLIDE_W
        self.im = Image.new("RGB", (self.w, self.h), "white")
        self.d = ImageDraw.Draw(self.im)

    # --- shakllar (pt) ---
    def px(self, v: float) -> int:
        return int(round(v * self.k))

    def rect(self, x, y, w, h, fill=None, outline=None, width=1.0):
        k = self.k
        box = (round(x * k), round(y * k), round((x + w) * k) - 1, round((y + h) * k) - 1)
        self.d.rectangle(box, fill=_rgb(fill) if fill else None, outline=_rgb(outline) if outline else None,
                         width=max(1, round(width * k)) if outline else 0)

    def oval(self, x, y, w, h, fill):
        s = 4
        k = self.k * s
        pw, ph = max(1, round(w * k)), max(1, round(h * k))
        m = Image.new("L", (pw, ph), 0)
        ImageDraw.Draw(m).ellipse((0, 0, pw - 1, ph - 1), fill=255)
        m = m.resize((max(1, round(w * self.k)), max(1, round(h * self.k))), Image.LANCZOS)
        self.im.paste(Image.new("RGB", m.size, _rgb(fill)), (round(x * self.k), round(y * self.k)), m)

    # --- taqdimot_render.draw() bilan shartnoma ---
    def canvas_box(self, x, y, w, h, paras, fill=None, line=None, line_w=1.0, anchor="t", inset=6, shape="rect"):
        k = self.k
        if shape == "oval":
            if fill:
                self.oval(x, y, w, h, fill)
        elif fill or line:
            self.rect(x, y, w, h, fill=fill, outline=line, width=line_w)
        if not paras:
            return
        padx, pady = inset * k, max(2.0, inset * 0.6) * k
        inner_w, inner_h = max(10.0, w * k - 2 * padx), max(10.0, h * k - 2 * pady)
        f = 1.0
        items, th = _layout(paras, inner_w, k, f)
        while th > inner_h + 1 and f > MIN_FIT:         # sig'masa — biroz kichraytiriladi (cheklangan)
            f = round(f - 0.04, 2)
            items, th = _layout(paras, inner_w, k, f)
        oy = {"t": 0.0, "ctr": (inner_h - th) / 2, "b": inner_h - th}.get(anchor, 0.0)
        left, top = x * k + padx, y * k + pady + max(0.0, oy)
        for it in items:
            base = top + it["y"] + (it["lh"] - it["size_px"] * 1.107) / 2 + it["size_px"] * 0.891      # Liberation Serif: ko'tarilish 0,891 · tushish 0,216
            if it["mark"]:
                pd, size = it["mark"]
                px = max(6, round(size * k))
                if pd.get("bullet"):
                    self.d.text((left, base), "•", font=_font("serif", px), fill=_rgb(RD.ACCENT), anchor="ls")
                else:
                    self.d.text((left, base), f"{pd['num']}.", font=_font("serif_b", px), fill=_rgb(RD.ACCENT), anchor="ls")
            _draw_line(self.d, left + it["x"], base, it["parts"])

    def canvas_picture(self, path, x, y, w, h):
        pw, ph = max(1, round(w * self.k)), max(1, round(h * self.k))
        try:
            with Image.open(path) as im:
                if im.width * im.height > MAX_IMG_PX:
                    raise ValueError("rasm juda katta")
                im.draft("RGB", (pw * 2, ph * 2))
                im = im.convert("RGBA") if im.mode in ("RGBA", "LA", "P") else im.convert("RGB")
                im = im.resize((pw, ph), Image.LANCZOS)
                if im.mode == "RGBA":
                    self.im.paste(im, (round(x * self.k), round(y * self.k)), im.split()[3])
                else:
                    self.im.paste(im, (round(x * self.k), round(y * self.k)))
        except Exception:
            self.rect(x, y, w, h, fill="F2F2F2", outline="BFBFBF", width=1)     # rasm ochilmadi — bo'sh kulrang ramka

    # --- shablon bezaklari ---
    def _logo(self, x, y, w, h):
        try:
            with Image.open(LOGO) as lg:
                lg = lg.convert("RGBA").resize((self.px(w), self.px(h)), Image.LANCZOS)
            self.im.paste(lg, (self.px(x), self.px(y)), lg.split()[3])
        except Exception:
            pass

    def _corners(self, tl=True, bl=True):
        edge = "D6D6E0"
        if tl: self.rect(940, 0, 19.4, 11.3, outline=edge, width=1)
        if bl: self.rect(0, 530, 16, 10.3, outline=edge, width=1)

    def _band(self):
        self.rect(143.4, 18, SLIDE_W - 143.4, 52, fill=RD.ACCENT)

    def finish(self) -> Image.Image:
        return self.im


# =============================================================================================
# Slaydlar (titul / reja / kontent / rahmat)
# =============================================================================================
def _title_slide(cv: Canvas, outline: dict):
    cv.rect(0, 0, 36.1, SLIDE_H, fill=RD.ACCENT)
    cv._logo(800, 0.9, 160, 124.1)
    cv._corners()
    P = RD.para
    cv.canvas_box(237.5, 23.1, 621.0, 138.0, [P("ISFT INSTITUTI", 48, RD.BLACK, True, "ctr"), P("MASOFAVIY TA’LIM", 48, RD.BLACK, True, "ctr")], inset=4.8)
    lines = RD.title_lines(outline)
    cv.canvas_box(332.0, 149.6, 592.8, 306.9, [P(t, sz, col, b, "ctr") for t, sz, col, b in lines], anchor="ctr", inset=4.8)
    cv.canvas_box(341.3, 493.1, 592.8, 33.0, [P("ISFT – Educational content", 29.33, RD.BLACK, True, "ctr")], anchor="ctr", inset=4.8)


def _content_slide(cv: Canvas, pg: dict, images_dir):
    cv._logo(24.0, 7.4, 106.0, 82.2)
    cv._band()
    cv._corners()
    RD.draw(cv, pg, images_dir)


def _plan_slide(cv: Canvas, items):
    cv._logo(24.0, 7.4, 106.0, 82.2)
    cv._band()
    cv._corners()
    cv.canvas_box(520.9, 15.3, 116.7, 48.5, [RD.para("REJA:", 36, RD.WHITE, True, "ctr")], anchor="ctr", inset=4.8)
    RD.draw_plan(cv, items)


def _thanks_slide(cv: Canvas):
    cv._corners()
    cv.rect(360.0, 175.0, SLIDE_W - 360.0, 178.5, fill=RD.ACCENT)
    cv.canvas_box(360.0, 175.0, SLIDE_W - 360.0, 178.5, [RD.para("E’TIBORINGIZ UCHUN RAHMAT!", 44, RD.WHITE, True, "ctr")], anchor="ctr", inset=8)


def slide_count(outline: dict) -> int:
    """PNG/PDF dagi slaydlar soni = pptx dagi: titul + reja + kontent sahifalari (kontent bo'lmasa — 0) + rahmat."""
    return 3 + len(RD.plan_pages(outline))


def _safe(draw_fn, width: int) -> Image.Image:
    """Bitta slaydni chizish; kutilmagan xatoda slayd faqat shablon (sarlavha paneli) bilan qoladi — butun taqdimot to'xtamaydi."""
    cv = Canvas(width)
    try:
        draw_fn(cv)
    except Exception as e:
        print("taqdimot_slides: slayd chizilmadi:", repr(e))
        cv = Canvas(width); cv._logo(24.0, 7.4, 106.0, 82.2); cv._band()
    return cv.finish()


def render_slides(outline: dict, images_dir: Path | None = None, width: int = W):
    """Outline → slayd rasmlari (generator, PIL.Image, RGB). Slaydlar tartibi va soni taqdimot_render.render() bilan bir xil."""
    pages = RD.plan_pages(outline)
    items = RD.plan_items(outline)
    yield _safe(lambda cv: _title_slide(cv, outline), width)
    yield _safe(lambda cv: _plan_slide(cv, items), width)
    for pg in pages:
        yield _safe(lambda cv, pg=pg: _content_slide(cv, pg, images_dir), width)
    yield _safe(_thanks_slide, width)


def render_png(im: Image.Image) -> bytes:
    bio = io.BytesIO()
    im.save(bio, "PNG", optimize=False, compress_level=6)
    return bio.getvalue()


def build_pdf(images: list[Image.Image], out_path: Path | None = None) -> bytes:
    """Slayd rasmlari → ko'p sahifali PDF (sahifa 960×540 pt, har sahifa — bitta rasm; matn qatlami yo'q)."""
    if not images:
        raise ValueError("slayd yo'q")
    bio = io.BytesIO()
    first, rest = images[0], images[1:]
    dpi = first.width / (SLIDE_W / 72.0)             # 960 pt = 13.33 dyuym
    first.save(bio, "PDF", save_all=True, append_images=rest, resolution=dpi, quality=85, subsampling=0)
    raw = bio.getvalue()
    if out_path is not None:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(raw)
    return raw


def render_deck(outline: dict, images_dir: Path | None, slides_dir: Path | None = None, pdf_path: Path | None = None, width: int = W) -> dict:
    """Asosiy kirish: har slayd → slides_dir/NN.png (01.png, 02.png …), hammasidan PDF. → {"slides": n, "pdf": baytlar yoki None, "png": [yo'llar]}.
    Bitta slayddagi kutilmagan xato butun taqdimotni to'xtatmaydi: shu slayd bo'sh (faqat sarlavha paneli) qoladi."""
    ims, paths = [], []
    if slides_dir is not None:
        slides_dir.mkdir(parents=True, exist_ok=True)
    for n, im in enumerate(render_slides(outline, images_dir, width), 1):
        ims.append(im)
        if slides_dir is not None:
            p = slides_dir / f"{n:02d}.png"
            p.write_bytes(render_png(im)); paths.append(p)
    n = len(ims)
    pdf = build_pdf(ims, pdf_path) if ims else None
    return {"slides": n, "pdf": pdf, "png": paths}
