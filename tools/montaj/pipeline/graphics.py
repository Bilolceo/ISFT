"""Grafika (Pillow): fon/kanvas, intro/outro kartalari, lower-third, bob banneri, suv belgisi, miniatyura.

Dizayn tamoyili: sokin, universitet ma'ruzasi — oq-pushti fon (PAPER), ISFT bordo urg'u,
Arial tipografiyasi, yumshoq soyalar, keskin effektlarsiz.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from .common import (W, H, MAROON, MAROON_DARK, MAROON_SOFT, INK, MUTED, PAPER, find_font, uz_typography,
                     DEFAULT_LOGO)


@lru_cache(maxsize=64)
def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(find_font(bold), size)


def text_w(s: str, f) -> int:
    return int(f.getlength(s))


def wrap_px(text: str, f, max_w: int, max_lines: int = 3) -> list[str]:
    words = text.split()
    lines, cur = [], ""
    for w in words:
        t = f"{cur} {w}".strip()
        if text_w(t, f) <= max_w or not cur:
            cur = t
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        while lines[-1] and text_w(lines[-1] + "…", f) > max_w:
            lines[-1] = lines[-1][:-1].rstrip()
        lines[-1] += "…"
    return lines


def fit_font(text: str, max_w: int, sizes: list[int], bold: bool, max_lines: int):
    """Matn `max_lines` qatorga sig'adigan eng katta shrift."""
    for s in sizes:
        f = font(s, bold)
        if len(wrap_px(text, f, max_w, 99)) <= max_lines:
            return f, wrap_px(text, f, max_w, max_lines)
    f = font(sizes[-1], bold)
    return f, wrap_px(text, f, max_w, max_lines)


def spaced(draw, xy, text, f, fill, spacing=2):
    """Harflar orasi kengaytirilgan matn (kichik sarlavhalar uchun)."""
    x, y = xy
    for ch in text:
        draw.text((x, y), ch, font=f, fill=fill)
        x += f.getlength(ch) + spacing
    return x


def rounded_mask(size: tuple[int, int], r: int) -> Image.Image:
    m = Image.new("L", (size[0] * 2, size[1] * 2), 0)
    ImageDraw.Draw(m).rounded_rectangle((0, 0, size[0] * 2 - 1, size[1] * 2 - 1), r * 2, fill=255)
    return m.resize(size, Image.LANCZOS)


def shadow(canvas: Image.Image, box, r=18, blur=18, alpha=46, offset=(0, 8)):
    x0, y0, x1, y1 = box
    pad = blur * 3
    sh = Image.new("L", (x1 - x0 + pad * 2, y1 - y0 + pad * 2), 0)
    ImageDraw.Draw(sh).rounded_rectangle((pad, pad, pad + x1 - x0, pad + y1 - y0), r, fill=alpha)
    sh = sh.filter(ImageFilter.GaussianBlur(blur))
    col = Image.new("RGBA", sh.size, (40, 10, 22, 255))
    col.putalpha(sh)
    canvas.alpha_composite(col, (x0 - pad + offset[0], y0 - pad + offset[1])) if canvas.mode == "RGBA" else \
        canvas.paste(col, (x0 - pad + offset[0], y0 - pad + offset[1]), col)


def vgradient(size, top, bottom) -> Image.Image:
    w, h = size
    g = Image.new("RGB", (1, h))
    for y in range(h):
        k = y / max(1, h - 1)
        g.putpixel((0, y), tuple(int(top[i] + (bottom[i] - top[i]) * k) for i in range(3)))
    return g.resize((w, h))


def dgradient(size, a, b) -> Image.Image:
    """Diagonal gradient (yuqori-chap a → past-o'ng b)."""
    w, h = size
    small = Image.new("RGB", (64, 64))
    for y in range(64):
        for x in range(64):
            k = (x + y) / 126
            small.putpixel((x, y), tuple(int(a[i] + (b[i] - a[i]) * k) for i in range(3)))
    return small.resize((w, h), Image.BICUBIC)


def load_logo(path: Path | None, height: int) -> Image.Image:
    p = Path(path) if path and Path(path).exists() else DEFAULT_LOGO
    lg = Image.open(p).convert("RGBA")
    w = int(lg.width * height / lg.height)
    return lg.resize((w, height), Image.LANCZOS)


@dataclass
class Lesson:
    subject: str = ""
    code: str = ""
    title: str = ""
    teacher: str = ""
    plan: tuple = ()
    kind: str = ""

    def norm(self) -> "Lesson":
        return Lesson(uz_typography(self.subject), self.code.strip(), uz_typography(self.title),
                      uz_typography(self.teacher), tuple(uz_typography(p) for p in self.plan), self.kind)

    @property
    def code_title(self) -> str:
        return f"{self.code} · {self.title}" if self.code else self.title


# ---------------------------------------------------------------- shablon geometriyasi
class Geo:
    # maruza_slayd
    HY = 154                                          # sarlavha qatori markazi
    SLIDE = (64, 226, 64 + 1280, 226 + 720)          # 16:9 slayd kartasi (sarlavha ostida, vertikal markazda)
    TEACH = (1384, 226, 1856, 226 + 720)             # o'qituvchi ramkasi (slayd bilan bir balandlikda)
    TEACH_R = 22
    SLIDE_R = 14
    BAR_H = 8                                         # pastki bordo chiziq
    # ekran: PiP
    PIP = (W - 44 - 400, H - 44 - 8 - 300, W - 44, H - 44 - 8)
    PIP_R = 18
    WATERMARK_H = 66


def slide_canvas(lesson: Lesson, logo_path=None) -> Image.Image:
    """maruza_slayd uchun statik fon: sarlavha, slayd soyasi, o'qituvchi ramkasi, ism-familiya."""
    L = lesson
    c = vgradient((W, H), PAPER, (0xF3, 0xEC, 0xEF)).convert("RGBA")
    d = ImageDraw.Draw(c)
    # sarlavha qatori
    x = Geo.SLIDE[0]
    HY = Geo.HY
    if L.code:
        f = font(26, True)
        tw = text_w(L.code, f)
        d.rounded_rectangle((x, HY - 22, x + tw + 28, HY + 22), 10, fill=MAROON)
        d.text((x + 14, HY), L.code, font=f, fill="white", anchor="lm")
        x += tw + 28 + 18
    title_f = font(32, True)
    max_title = Geo.TEACH[2] - 260 - x
    t = wrap_px(L.title, title_f, max_title, 1)[0] if L.title else ""
    d.text((x, HY), t, font=title_f, fill=INK, anchor="lm")
    if L.subject:
        sx = x + text_w(t, title_f) + 22
        sub = wrap_px(L.subject, font(26), max(0, Geo.TEACH[2] - 200 - sx), 1)[0]
        if sx + 80 < Geo.TEACH[2] - 200:
            d.text((sx, HY + 1), "·  " + sub, font=font(26), fill=MUTED, anchor="lm")
    # slayd kartasi soyasi + oq karta
    shadow(c, Geo.SLIDE, r=Geo.SLIDE_R, blur=16, alpha=50)
    d.rounded_rectangle(Geo.SLIDE, Geo.SLIDE_R, fill="white")
    # o'qituvchi ramkasi: soya + oq chegara (video ichkarida 6 px)
    tb = Geo.TEACH
    shadow(c, tb, r=Geo.TEACH_R, blur=16, alpha=50)
    d.rounded_rectangle(tb, Geo.TEACH_R, fill="white")
    # pastki bordo chiziq
    d.rectangle((0, H - Geo.BAR_H, W, H), fill=MAROON)
    return c.convert("RGB")


def slide_card(page_img: Image.Image | None, canvas: Image.Image) -> Image.Image:
    """Slayd kartasi: kanvasning SLIDE qismi + yumaloq oq karta + sahifa rasmi (markazda)."""
    x0, y0, x1, y1 = Geo.SLIDE
    w, h = x1 - x0, y1 - y0
    base = canvas.crop((x0, y0, x1, y1)).convert("RGBA")
    card = Image.new("RGBA", (w, h), (255, 255, 255, 255))
    if page_img is not None:
        pi = page_img.copy()
        pi.thumbnail((w, h), Image.LANCZOS)
        card.paste(pi.convert("RGB"), ((w - pi.width) // 2, (h - pi.height) // 2))
    base.paste(card, (0, 0), rounded_mask((w, h), Geo.SLIDE_R))
    # nozik chegara
    ImageDraw.Draw(base).rounded_rectangle((0, 0, w - 1, h - 1), Geo.SLIDE_R, outline=(0xE6, 0xDA, 0xDF), width=1)
    return base.convert("RGB")


def teacher_label(lesson: Lesson) -> Image.Image:
    """O'qituvchi ramkasi ichida, pastda: oq yorliq (bordo chiziq, ism, fan). RGBA."""
    x0, y0, x1, y1 = Geo.TEACH
    w = x1 - x0 - 6 * 2 - 20 * 2
    nf, nl = fit_font(lesson.teacher, w - 40, [24, 22, 20], True, 2)
    sub = wrap_px(lesson.subject, font(19), w - 40, 1)[0] if lesson.subject else ""
    h = 16 + len(nl) * int(nf.size * 1.2) + (28 if sub else 0) + 12
    pad = 40
    img = Image.new("RGBA", (w + 2 * pad, h + 2 * pad), (0, 0, 0, 0))
    shadow(img, (pad, pad, pad + w, pad + h), r=12, blur=12, alpha=70, offset=(0, 4))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((pad, pad, pad + w, pad + h), 12, fill=(255, 255, 255, 244))
    d.rounded_rectangle((pad, pad, pad + 8, pad + h), 4, fill=MAROON)
    d.rectangle((pad + 4, pad, pad + 8, pad + h), fill=MAROON)
    y = pad + 14
    for line in nl:
        d.text((pad + 26, y), line, font=nf, fill=INK)
        y += int(nf.size * 1.2)
    if sub:
        d.text((pad + 26, y + 4), sub, font=font(19), fill=MAROON)
    return img


def teacher_mask() -> Image.Image:
    x0, y0, x1, y1 = Geo.TEACH
    return rounded_mask((x1 - x0 - 12, y1 - y0 - 12), Geo.TEACH_R - 5)


def pip_frame() -> Image.Image:
    """ekran shabloni: PiP uchun oq ramka + soya (RGBA, to'liq kadr o'lchamida emas — faqat atrofi)."""
    x0, y0, x1, y1 = Geo.PIP
    pad = 60
    img = Image.new("RGBA", (x1 - x0 + 2 * pad, y1 - y0 + 2 * pad), (0, 0, 0, 0))
    shadow(img, (pad, pad, pad + x1 - x0, pad + y1 - y0), r=Geo.PIP_R, blur=18, alpha=90, offset=(0, 6))
    ImageDraw.Draw(img).rounded_rectangle((pad, pad, pad + x1 - x0 - 1, pad + y1 - y0 - 1), Geo.PIP_R, fill="white")
    return img


def pip_mask() -> Image.Image:
    x0, y0, x1, y1 = Geo.PIP
    return rounded_mask((x1 - x0 - 10, y1 - y0 - 10), Geo.PIP_R - 4)


def bottom_bar() -> Image.Image:
    return Image.new("RGB", (W, Geo.BAR_H), MAROON)


WM_MARGIN = 48       # suv belgisi kadr chetidan
WM_GAP = 24          # suv belgisi va o'qituvchi (kamera) sohasi orasidagi eng kam masofa


def camera_rects(template: str, slide_on: bool = False) -> list[tuple[int, int, int, int]]:
    """Kadrdagi o'qituvchi (kamera) sohalari — suv belgisi ularni HECH QACHON yopmasligi kerak.
    ekran: PiP (alohida veb-kamera bo'lsa ham, kamera ekran yozuviga «pishirilgan» bo'lsa ham — o'qituvchi shu burchakda)."""
    if template == "ekran":
        return [Geo.PIP]
    if template == "maruza_slayd" and slide_on:
        return [Geo.TEACH]
    return []


def rects_overlap(a, b, gap: int = 0) -> bool:
    return a[0] < b[2] + gap and b[0] < a[2] + gap and a[1] < b[3] + gap and b[1] < a[3] + gap


def watermark_xy(template: str, size: tuple[int, int], slide_on: bool = False) -> tuple[int, int]:
    """Suv belgisi (logo) joyi. maruza_slayd + slayd: sarlavha qatorida, o'qituvchi ramkasi ustida (ramkaga kirmaydi).
    ekran: PiP ga diagonal qarama-qarshi burchak (yuqori chap) — o'qituvchi yuzini yopmaydi. Qolganlari: yuqori o'ng.
    Har qanday nomzod kamera sohasi bilan kesishsa — keyingi burchak olinadi."""
    w, h = size
    tl, tr = (WM_MARGIN, 34), (W - WM_MARGIN - w, 34)
    bl, br = (WM_MARGIN, H - Geo.BAR_H - 34 - h), (W - WM_MARGIN - w, H - Geo.BAR_H - 34 - h)
    cams = camera_rects(template, slide_on)
    if template == "maruza_slayd" and slide_on:
        cands = [(Geo.TEACH[2] - w, Geo.HY - h // 2), tr, tl]
    elif template == "ekran":
        # PiP qaysi burchakda bo'lsa, unga eng uzoq burchak birinchi
        px, py = (Geo.PIP[0] + Geo.PIP[2]) / 2, (Geo.PIP[1] + Geo.PIP[3]) / 2
        cands = sorted([tl, tr, bl, br], key=lambda p: -((p[0] + w / 2 - px) ** 2 + (p[1] + h / 2 - py) ** 2))
    else:
        cands = [tr, tl]
    for x, y in cands:
        if not any(rects_overlap((x, y, x + w, y + h), c, WM_GAP) for c in cams):
            return x, y
    return cands[-1]


def watermark(logo_path=None, opacity: float = 0.6) -> Image.Image:
    lg = load_logo(logo_path, Geo.WATERMARK_H)
    a = lg.getchannel("A").point(lambda v: int(v * opacity))
    lg.putalpha(a)
    return lg


# ---------------------------------------------------------------- intro / outro
def intro_layers(lesson: Lesson, logo_path=None) -> tuple[Image.Image, Image.Image]:
    """(fon, matn qatlami RGBA). Fon: chapda och panel + logo, o'ngda bordo gradient panel."""
    L = lesson
    split = 720
    bg = Image.new("RGB", (W, H), PAPER)
    bg.paste(dgradient((W - split, H), MAROON, MAROON_DARK), (split, 0))
    d = ImageDraw.Draw(bg)
    # nozik bezak: bordo panelda katta, juda och aylana yoylari
    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    od = ImageDraw.Draw(ov)
    for r, a in ((520, 16), (640, 10), (760, 6)):
        od.ellipse((W - 140 - r, H + 60 - r, W - 140 + r, H + 60 + r), outline=(255, 255, 255, a), width=2)
    bg = Image.alpha_composite(bg.convert("RGBA"), ov)
    lg = load_logo(logo_path, 330)
    bg.alpha_composite(lg, ((split - lg.width) // 2, (H - lg.height) // 2 - 30))
    d = ImageDraw.Draw(bg)
    t = uz_typography("ISFT · Masofaviy ta'lim")
    d.text((split // 2, (H + lg.height) // 2 + 40), t, font=font(26, True), fill=MAROON, anchor="mm")

    fg = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    fd = ImageDraw.Draw(fg)
    x, maxw = split + 110, W - split - 220
    title_f, title_lines = fit_font(L.code_title, maxw, [76, 68, 60, 54, 48], True, 3)
    lh = int(title_f.size * 1.18)
    block_h = 34 + 26 + 8 + 34 + len(title_lines) * lh + 34 + 40
    y = (H - block_h) // 2
    if L.subject:
        spaced(fd, (x, y), L.subject.upper()[:60], font(26, True), (0xF2, 0xC9, 0xDA, 255), spacing=3)
    y += 34 + 26
    fd.rectangle((x, y, x + 72, y + 6), fill=(255, 255, 255, 235))
    y += 8 + 34
    for line in title_lines:
        fd.text((x, y), line, font=title_f, fill=(255, 255, 255, 255))
        y += lh
    y += 34
    if L.teacher:
        fd.text((x, y), L.teacher, font=font(34), fill=(0xF6, 0xE6, 0xED, 255))
    return bg.convert("RGB"), fg


def outro_layers(lesson: Lesson, logo_path=None) -> tuple[Image.Image, Image.Image]:
    L = lesson
    bg = vgradient((W, H), PAPER, (0xF3, 0xEC, 0xEF)).convert("RGBA")
    d = ImageDraw.Draw(bg)
    d.rectangle((0, H - Geo.BAR_H, W, H), fill=MAROON)
    fg = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    lg = load_logo(logo_path, 360)
    fg.alpha_composite(lg, ((W - lg.width) // 2, 230))
    fd = ImageDraw.Draw(fg)
    fd.text((W // 2, 680), uz_typography("ISFT · Masofaviy ta'lim"), font=font(46, True), fill=INK, anchor="mm")
    sub = " · ".join(x for x in (L.subject, L.code) if x)
    if sub:
        fd.text((W // 2, 745), sub, font=font(30), fill=MUTED, anchor="mm")
    if L.teacher:
        fd.text((W // 2, 795), L.teacher, font=font(28), fill=MUTED, anchor="mm")
    return bg.convert("RGB"), fg


# ---------------------------------------------------------------- lower-third / bob banneri
def lower_third(name: str, sub: str) -> Image.Image:
    """Oq karta, chapda bordo chiziq; ism (qalin) + fan. RGBA, soya bilan."""
    nf, sf = font(40, True), font(28)
    name = wrap_px(name, nf, 900, 1)[0]
    sub = wrap_px(sub, sf, 900, 1)[0] if sub else ""
    w = max(text_w(name, nf), text_w(sub, sf)) + 40 + 56
    h = 128 if sub else 92
    pad = 50
    img = Image.new("RGBA", (w + 2 * pad, h + 2 * pad), (0, 0, 0, 0))
    shadow(img, (pad, pad, pad + w, pad + h), r=12, blur=16, alpha=70, offset=(0, 6))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((pad, pad, pad + w, pad + h), 12, fill=(255, 255, 255, 250))
    d.rounded_rectangle((pad, pad, pad + 12, pad + h), 6, fill=MAROON)
    d.rectangle((pad + 6, pad, pad + 12, pad + h), fill=MAROON)
    d.text((pad + 40, pad + 22), name, font=nf, fill=INK)
    if sub:
        d.text((pad + 40, pad + 76), sub, font=sf, fill=MAROON)
    return img


def chapter_banner(index: int, title: str) -> Image.Image:
    """Bordo karta: kichik "2-BO'LIM" yorlig'i + bob nomi (oq)."""
    lf, tf = font(22, True), font(38, True)
    label = uz_typography(f"{index}-BO'LIM")
    title = wrap_px(title, tf, 1000, 1)[0]
    w = max(text_w(title, tf), text_w(label, lf) + 30) + 72
    h = 116
    pad = 50
    img = Image.new("RGBA", (w + 2 * pad, h + 2 * pad), (0, 0, 0, 0))
    shadow(img, (pad, pad, pad + w, pad + h), r=12, blur=16, alpha=80, offset=(0, 6))
    card = dgradient((w, h), MAROON, MAROON_DARK).convert("RGBA")
    img.paste(card, (pad, pad), rounded_mask((w, h), 12))
    d = ImageDraw.Draw(img)
    spaced(d, (pad + 36, pad + 20), label, lf, (0xF2, 0xC9, 0xDA, 255), spacing=2)
    d.text((pad + 36, pad + 54), title, font=tf, fill=(255, 255, 255, 255))
    return img


OVERLAY_PAD = 50  # lower_third/chapter_banner rasmidagi soya maydoni


# ---------------------------------------------------------------- miniatyura
def thumbnail(frame: Image.Image, lesson: Lesson, logo_path=None) -> Image.Image:
    L = lesson
    tw, th = 1280, 720
    img = frame.convert("RGB").resize((tw, th), Image.LANCZOS).convert("RGBA")
    # chapdan o'ngga shaffoflashadigan bordo panel
    grad = Image.new("L", (tw, 1))
    for x in range(tw):
        k = x / tw
        a = 255 if k < 0.5 else max(0, int(255 * (1 - ((k - 0.5) / 0.16) ** 1.5))) if k < 0.66 else 0
        grad.putpixel((x, 0), a)
    grad = grad.resize((tw, th))
    panel = dgradient((tw, th), MAROON, MAROON_DARK).convert("RGBA")
    panel.putalpha(grad)
    img = Image.alpha_composite(img, panel)
    d = ImageDraw.Draw(img)
    # logo — oq yumaloq plitkada
    lg = load_logo(logo_path, 92)
    tile = (56, 48, 56 + lg.width + 28, 48 + lg.height + 20)
    d.rounded_rectangle(tile, 16, fill=(255, 255, 255, 240))
    img.alpha_composite(lg, (tile[0] + 14, tile[1] + 10))
    x, maxw = 64, 640
    y = 250
    if L.code:
        f = font(30, True)
        cw = text_w(L.code, f)
        d.rounded_rectangle((x, y, x + cw + 32, y + 50), 12, outline=(255, 255, 255, 230), width=3)
        d.text((x + 16, y + 25), L.code, font=f, fill="white", anchor="lm")
        y += 78
    tf, lines = fit_font(L.title, maxw, [62, 56, 50, 44], True, 3)
    for line in lines:
        d.text((x, y), line, font=tf, fill="white")
        y += int(tf.size * 1.16)
    y += 18
    meta = " · ".join(v for v in (L.subject, L.teacher) if v)
    for line in wrap_px(meta, font(28), maxw, 2):
        d.text((x, y), line, font=font(28), fill=(0xF6, 0xE6, 0xED))
        y += 36
    return img.convert("RGB")
