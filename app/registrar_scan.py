"""Otrabotka varaqasi skanini o'qish (Registrator ofisi) va demo skan generatori.

O'qish tartibi (hech biri bo'lmasa — registrator qo'lda kiritadi, tizim buni ochiq aytadi):
  1. PDF matn qatlami (skaner OCR qilgan «qidiriladigan PDF») — pypdf; so'zlar koordinatasi bilan.
  2. Tesseract OCR (agar serverda o'rnatilgan bo'lsa: `tesseract` buyrug'i) — rasm yoki PDF ichidagi rasm.
     Railway'da tesseract yo'q — u yerda faqat 1-usul ishlaydi, ball qo'lda kiritiladi.
  3. Topilgan ustun sarlavhalari («Ball (100 ballik)», «O'qituvchi imzosi») bo'yicha katakchalar kesiladi:
     imzo katagidagi siyoh ulushi → imzo bor/yo'q; ball katagi → OCR (faqat raqamlar) yoki «to'ldirilgan» belgisi.
  4. Ro'yxat raqami (OV-26/0001) → otrabotka bilan moslashtiriladi. QR kodni dekodlash uchun kutubxona (zbar/opencv)
     o'rnatilmagan — QR varaqada haqiqiylikni tekshirish uchun turadi, moslashtirish ro'yxat raqami bo'yicha.
Demo generator: «to'ldirilgan va imzolangan» yoki «imzosiz» skan (PNG yoki matn qatlamli PDF) — faqat namoyish uchun.
"""
import datetime as dt, io, random, re, shutil, subprocess, tempfile, zlib
from pathlib import Path
from PIL import Image, ImageDraw, ImageFilter, ImageFont

W, H = 1240, 1754          # A4, 150 dpi
DPI = 150
REG_RE = re.compile(r"[O0Q]V\s?[-–—]\s?(\d{2})\s?/\s?(\d{4})")

# ---------------------------------------------------------------------------------------------
# Shriftlar (macOS / Linux; topilmasa — PIL standart shrifti)
# ---------------------------------------------------------------------------------------------
_PRINT = ["/System/Library/Fonts/Supplemental/Arial.ttf", "/System/Library/Fonts/Helvetica.ttc",
          "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/usr/share/fonts/dejavu/DejaVuSans.ttf",
          "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"]
_BOLD = ["/System/Library/Fonts/Supplemental/Arial Bold.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
         "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf", "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"]
_HAND = ["/System/Library/Fonts/Supplemental/Chalkboard.ttc", "/System/Library/Fonts/Noteworthy.ttc",
         "/System/Library/Fonts/Supplemental/Bradley Hand Bold.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Oblique.ttf"]

def _font(cands, size):
    for p in cands:
        if Path(p).exists():
            try: return ImageFont.truetype(p, size)
            except OSError: continue
    try: return ImageFont.load_default(size=size)
    except TypeError: return ImageFont.load_default()

def tesseract_bin():
    return shutil.which("tesseract") or next((p for p in ("/opt/homebrew/bin/tesseract", "/usr/local/bin/tesseract", "/usr/bin/tesseract") if Path(p).exists()), None)

# ---------------------------------------------------------------------------------------------
# Demo skan generatori
# ---------------------------------------------------------------------------------------------
def make_sheet(info: dict, variant: str = "signed", fmt: str = "png", seed=None):
    """info: reg_no, code, url, student, hemis, faculty, grp, subject, teacher, score_old, due.
    variant: 'signed' — ball, sana va o'qituvchi imzosi bor; 'unsigned' — ball bor, imzo yo'q (tizim belgilashi kerak).
    Qaytaradi: (bytes, '.png'|'.pdf', {'score': chizilgan ball, 'signed': bool})."""
    R = random.Random(seed if seed is not None else info.get("reg_no"))
    im = Image.new("RGB", (W, H), "white"); d = ImageDraw.Draw(im)
    segs = []    # PDF matn qatlami uchun: (matn, x, y_yuqori, o'lcham)
    def text(xy, s, size, bold=False, fill=(20, 20, 20), layer=True):
        f = _font(_BOLD if bold else _PRINT, size); d.text(xy, s, font=f, fill=fill)
        if layer: segs.append((s, xy[0], xy[1], size))
    d.rectangle([0, 70, W, 190], fill=(135, 0, 55))
    text((120, 92), "ISFT INSTITUTI", 40, True, (255, 255, 255))
    text((120, 146), "Registrator ofisi", 24, False, (255, 230, 236))
    text((120, 240), "OTRABOTKA (QAYTA TOPSHIRISH) VARAQASI", 34, True)
    text((120, 300), f"Ro'yxat raqami: {info['reg_no']}", 28, True)
    text((800, 304), f"Berilgan: {info.get('issued', dt.date.today().strftime('%d.%m.%Y'))}", 22)
    rows = [("Talaba", info["student"]), ("HEMIS ID", info.get("hemis") or "—"), ("Fakultet / guruh", f"{info.get('faculty', '')} · {info.get('grp', '')}"),
            ("Fan", info["subject"]), ("O'qituvchi", info.get("teacher") or "—"),
            ("Avvalgi ball", str(info.get("score_old") if info.get("score_old") is not None else "—")), ("Topshirish muddati", info.get("due") or "—")]
    y = 370
    for lab, val in rows:
        d.rectangle([120, y, 1120, y + 56], outline=(120, 120, 120), width=2); d.line([480, y, 480, y + 56], fill=(120, 120, 120), width=2)
        text((136, y + 14), lab, 22); text((496, y + 14), str(val)[:60], 22, True)
        y += 56
    text((120, y + 30), "Varaqani o'qituvchi to'ldiradi va muddatida Registrator ofisiga qaytariladi.", 21)
    text((120, y + 62), "Muddat o'tsa, tyutorga ogohlantirish topshirig'i yuboriladi.", 21)
    ty = y + 130                                   # to'ldiriladigan jadval
    cols = [120, 460, 800, 1120]
    d.rectangle([cols[0], ty, cols[3], ty + 60], fill=(243, 236, 239))
    for x0, x1 in zip(cols, cols[1:]):
        d.rectangle([x0, ty, x1, ty + 60], outline=(90, 90, 90), width=2); d.rectangle([x0, ty + 60, x1, ty + 200], outline=(90, 90, 90), width=2)
    for x0, lab in zip(cols, ["Topshirilgan sana", "Ball (100 ballik)", "O'qituvchi imzosi"]):
        text((x0 + 18, ty + 17), lab, 22, True)
    score = R.randint(52, 88)
    hand = _font(_HAND, 56)
    ink = (22, 38, 120)
    d.text((cols[0] + 26, ty + 105), dt.date.today().strftime("%d.%m.%y"), font=_font(_HAND, 38), fill=ink)
    d.text((cols[1] + 110, ty + 80), str(score), font=hand, fill=ink)
    if variant == "signed":
        # imzo: tasodifiy tayanch nuqtalar orqali silliq (Catmull-Rom) egri chiziq + pastki «dum»
        cps = [(cols[2] + 45, ty + 150)]
        for i in range(9):
            cps.append((cps[-1][0] + R.randint(18, 34), ty + 130 + R.choice([-1, 1]) * R.randint(8, 42)))
        cps.append((cps[-1][0] + 40, ty + 170)); cps.append((cols[2] + 70, ty + 175))
        pts = []
        for i in range(1, len(cps) - 2):
            p0, p1, p2, p3 = cps[i - 1], cps[i], cps[i + 1], cps[i + 2]
            for k in range(12):
                t = k / 12; t2, t3 = t * t, t * t * t
                pts.append(tuple(0.5 * ((2 * p1[j]) + (-p0[j] + p2[j]) * t + (2 * p0[j] - 5 * p1[j] + 4 * p2[j] - p3[j]) * t2
                                        + (-p0[j] + 3 * p1[j] - 3 * p2[j] + p3[j]) * t3) for j in (0, 1)))
        d.line(pts, fill=ink, width=3, joint="curve")
    text((120, ty + 250), "Registrator ofisi: ____________________", 22)
    try:
        import qrcode
        q = qrcode.QRCode(border=1, box_size=6); q.add_data(info.get("url") or info["reg_no"]); q.make(fit=True)
        qi = q.make_image(fill_color="black", back_color="white").convert("RGB").resize((200, 200))
        im.paste(qi, (120, ty + 320))
    except Exception:
        pass
    text((350, ty + 340), f"Tekshirish kodi: {info.get('code', '')}", 20, True)
    text((350, ty + 372), "Haqiqiyligini QR orqali tekshiring.", 18)
    text((120, H - 90), "DEMO: sun'iy skan — ISFT Core namoyishi uchun yaratilgan", 18, False, (150, 150, 150))
    # skaner effekti: qog'oz rangi, ozgina qiyshayish va xiralik
    im = im.rotate(R.uniform(-0.35, 0.35), resample=Image.BICUBIC, fillcolor=(255, 255, 255))
    im = Image.blend(im, Image.new("RGB", im.size, (246, 243, 236)), 0.12).filter(ImageFilter.GaussianBlur(0.5))
    meta = {"score": score, "signed": variant == "signed"}
    if fmt == "pdf":
        return _searchable_pdf(im, segs), ".pdf", meta
    buf = io.BytesIO(); im.save(buf, "PNG", optimize=True)
    return buf.getvalue(), ".png", meta

def _pdf_str(s: str) -> bytes:
    s = s.encode("latin-1", "replace").decode("latin-1")
    return ("(" + s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)") + ")").encode("latin-1")

def _searchable_pdf(im: Image.Image, segs) -> bytes:
    """Skaner chiqaradigan «qidiriladigan PDF»: sahifa = rasm + ko'rinmas matn qatlami (faqat bosma matn; qo'lyozma yo'q)."""
    jb = io.BytesIO(); im.convert("RGB").save(jb, "JPEG", quality=82); jpg = jb.getvalue()
    pw, ph = W * 72 / DPI, H * 72 / DPI
    k = 72 / DPI
    parts = [f"q {pw:.2f} 0 0 {ph:.2f} 0 0 cm /Im0 Do Q".encode(), b"BT 3 Tr"]
    for s, x, y, size in segs:
        fs = size * k * 0.92
        parts.append(f"/F1 {fs:.2f} Tf 1 0 0 1 {x * k:.2f} {ph - (y + size * 0.8) * k:.2f} Tm ".encode() + _pdf_str(s) + b" Tj")
    parts.append(b"ET")
    content = zlib.compress(b"\n".join(parts))
    objs = [b"<< /Type /Catalog /Pages 2 0 R >>",
            b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {pw:.2f} {ph:.2f}] /Resources << /XObject << /Im0 4 0 R >> /Font << /F1 5 0 R >> >> /Contents 6 0 R >>".encode(),
            f"<< /Type /XObject /Subtype /Image /Width {im.width} /Height {im.height} /ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /DCTDecode /Length {len(jpg)} >>\nstream\n".encode() + jpg + b"\nendstream",
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
            f"<< /Length {len(content)} /Filter /FlateDecode >>\nstream\n".encode() + content + b"\nendstream"]
    out = io.BytesIO(); out.write(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n"); offs = []
    for i, o in enumerate(objs, 1):
        offs.append(out.tell()); out.write(f"{i} 0 obj\n".encode() + o + b"\nendobj\n")
    xref = out.tell()
    out.write(f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode() + b"".join(f"{o:010d} 00000 n \n".encode() for o in offs))
    out.write(f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode())
    return out.getvalue()

# ---------------------------------------------------------------------------------------------
# O'qish
# ---------------------------------------------------------------------------------------------
def page_image(raw: bytes, ext: str):
    """Skan sahifasi rasmi (PDF bo'lsa — ichidagi birinchi rasm). Topilmasa None."""
    if ext == ".pdf":
        try:
            from pypdf import PdfReader
            pg = PdfReader(io.BytesIO(raw)).pages[0]
            imgs = list(pg.images)
            return imgs[0].image.convert("RGB") if imgs else None
        except Exception:
            return None
    try:
        return Image.open(io.BytesIO(raw)).convert("RGB")
    except Exception:
        return None

def _pdf_words(raw: bytes, img_size):
    """PDF matn qatlami: [(matn, x0, y0, x1, y1)] — rasm piksellarida."""
    try:
        from pypdf import PdfReader
        pg = PdfReader(io.BytesIO(raw)).pages[0]
    except Exception:
        return "", []
    box = pg.mediabox; pw, ph = float(box.width), float(box.height)
    iw, ih = img_size if img_size else (W, H)
    sx, sy = iw / pw, ih / ph
    words, texts = [], []
    # Matn operatorlarini o'zimiz kuzatamiz (Tm/Td/Tf/Tj/TJ): pypdf extract_text bir qatordagi segmentlarni
    # birlashtirib yuboradi va har segmentning x koordinatasi yo'qoladi.
    try:
        from pypdf.generic import ContentStream
        ops = ContentStream(pg.get_contents(), pg.pdf).operations
    except Exception:
        return "", []
    x = y = lx = ly = 0.0; fs = 10.0
    for operands, op in ops:
        try:
            if op == b"BT": x = y = lx = ly = 0.0
            elif op == b"Tf": fs = float(operands[1])
            elif op == b"Tm": x = lx = float(operands[4]); y = ly = float(operands[5])
            elif op in (b"Td", b"TD"): lx += float(operands[0]); ly += float(operands[1]); x, y = lx, ly
            elif op in (b"Tj", b"TJ", b"'", b'"'):
                arr = operands[-1] if op != b"TJ" else operands[0]
                s = "".join(str(a) for a in arr if isinstance(a, str)) if op == b"TJ" else str(arr)
                texts.append(s)
                cx = x
                for w in s.split(" "):         # so'zlar kengligi taxminan (Helvetica ~0.52 em)
                    ww = len(w) * fs * 0.52
                    if w: words.append((w, cx * sx, (ph - y - fs * 0.8) * sy, (cx + ww) * sx, (ph - y + fs * 0.2) * sy))
                    cx += ww + fs * 0.28
                x = cx
        except (ValueError, IndexError, TypeError):
            continue
    return "\n".join(texts), words

def _tess(img: Image.Image, args: list, timeout=25):
    exe = tesseract_bin()
    if not exe: return None
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "in.png"; img.save(p)
        try:
            r = subprocess.run([exe, str(p), "stdout", *args], capture_output=True, text=True, timeout=timeout)
        except (OSError, subprocess.TimeoutExpired):
            return None
        return r.stdout if r.returncode == 0 else None

def _ocr_words(img: Image.Image):
    out = _tess(img, ["--psm", "3", "tsv"])
    if out is None: return None, []
    words, lines = [], []
    for ln in out.splitlines()[1:]:
        p = ln.split("\t")
        if len(p) < 12 or not p[11].strip(): continue
        try: x, y, w, h = map(int, p[6:10])
        except ValueError: continue
        words.append((p[11].strip(), x, y, x + w, y + h)); lines.append(p[11].strip())
    return " ".join(lines), words

def _ink(img: Image.Image, box, thr=125):
    x0, y0, x1, y1 = [int(v) for v in box]
    x0, y0 = max(0, x0), max(0, y0); x1, y1 = min(img.width, x1), min(img.height, y1)
    if x1 - x0 < 10 or y1 - y0 < 10: return 0.0
    g = img.crop((x0, y0, x1, y1)).convert("L")
    hist = g.histogram()
    return sum(hist[:thr]) / max(1, (x1 - x0) * (y1 - y0))

def _cells(words):
    """Ustun sarlavhalaridan ball va imzo katakchalarini topadi: {'score': box, 'sign': box} yoki None."""
    ball = [w for w in words if w[0].startswith("Ball")]
    if not ball: return None
    b = max(ball, key=lambda w: w[2])                          # pastki jadval sarlavhasi
    line = [w for w in words if abs((w[2] + w[4]) / 2 - (b[2] + b[4]) / 2) < (b[4] - b[2]) * 0.9]
    right = sorted([w for w in line if w[1] > b[3] + 60], key=lambda w: w[1])
    if not right: return None
    third = right[0]
    # «Ball (100 ballik)» oxiri bilan uchinchi sarlavha orasidagi bo'shliq — ustun chegarasi
    cw = (third[1] - b[1])
    c2 = b[1] - 0.05 * cw; c3 = third[1] - 0.05 * cw; c4 = c3 + cw
    hb = max(w[4] for w in line) + 0.06 * cw
    rh = 0.38 * cw
    pad = 0.04 * cw
    return {"score": (c2 + pad, hb + pad, c3 - pad, hb + rh - pad), "sign": (c3 + pad, hb + pad, c4 - pad, hb + rh - pad)}

def _read_digits(crop: Image.Image):
    """Ball katagidan raqamni o'qiydi: siyoh chegarasi bo'yicha kesish + ikki xil masshtabda OCR (ovoz berish)."""
    from PIL import ImageOps
    bb = ImageOps.invert(crop).point(lambda v: 255 if v > 60 else 0).getbbox()
    if bb: crop = crop.crop(bb)
    votes = []
    for k, thr in ((1.0, None), (0.8, None), (0.6, None), (0.8, 150), (1.0, 150)):
        im = crop.resize((max(8, int(crop.width * k)), max(8, int(crop.height * k))))
        if thr: im = im.point(lambda v: 0 if v < thr else 255)
        out = _tess(ImageOps.expand(im, 20, 255), ["--psm", "7", "-c", "tessedit_char_whitelist=0123456789"]) or ""
        d = re.findall(r"\d{1,3}", out)
        if d and 0 <= int(d[0]) <= 100: votes.append(int(d[0]))
    if not votes: return None, False
    best = max(sorted(set(votes)), key=votes.count)
    return best, votes.count(best) >= 3

def read_scan(raw: bytes, ext: str) -> dict:
    """Skanni o'qiydi. Natija: method, reg_no, signed, score, score_filled, ocr, warnings."""
    meta = {"method": [], "reg_no": None, "signed": None, "score": None, "score_filled": None,
            "ocr": bool(tesseract_bin()), "warnings": [], "read_at": dt.datetime.now().isoformat(timespec="seconds")}
    img = page_image(raw, ext)
    text, words = "", []
    if ext == ".pdf":
        text, words = _pdf_words(raw, img.size if img else None)
        if words: meta["method"].append("PDF matn qatlami")
    if img is not None and (not words or not REG_RE.search(text)) and meta["ocr"]:
        t2, w2 = _ocr_words(img)
        if t2:
            meta["method"].append("OCR (tesseract)"); text += "\n" + t2
            if not _cells(words): words = w2
    m = REG_RE.search(text or "")
    if m: meta["reg_no"] = f"OV-{m.group(1)}/{m.group(2)}"
    else: meta["warnings"].append("Ro'yxat raqami o'qilmadi")
    cells = _cells(words) if img is not None else None
    if cells:
        si, sc = _ink(img, cells["sign"]), _ink(img, cells["score"])
        meta["ink"] = {"sign": round(si, 4), "score": round(sc, 4)}
        meta["signed"] = si > 0.006
        meta["score_filled"] = sc > 0.004
        if meta["score_filled"] and meta["ocr"]:
            score, agree = _read_digits(img.crop(tuple(int(v) for v in cells["score"])).convert("L"))
            if score is not None:
                meta["score"] = score; meta["score_conf"] = "yuqori" if agree else "past"
                if not agree: meta["warnings"].append("Ball ishonchsiz o'qildi — skan bilan solishtiring")
            else: meta["warnings"].append("Ball yozuvi o'qilmadi — qo'lda kiriting")
        elif meta["score_filled"]:
            meta["warnings"].append("Serverda OCR yo'q — ballni skanga qarab qo'lda kiriting")
        if meta["signed"] is False: meta["warnings"].append("O'qituvchi imzosi aniqlanmadi")
        if meta["score_filled"] is False: meta["warnings"].append("Ball katagi bo'sh")
    else:
        meta["warnings"].append("Varaqa katakchalari aniqlanmadi — imzo va ballni ko'z bilan tekshiring"
                                + ("" if meta["ocr"] or ext == ".pdf" else " (serverda OCR yo'q)"))
    meta["method"] = " + ".join(meta["method"]) or "qo'lda"
    return meta

def preview_png(raw: bytes, ext: str, max_w=1400) -> bytes | None:
    img = page_image(raw, ext)
    if img is None: return None
    if img.width > max_w: img = img.resize((max_w, int(img.height * max_w / img.width)))
    buf = io.BytesIO(); img.save(buf, "PNG", optimize=True); return buf.getvalue()
