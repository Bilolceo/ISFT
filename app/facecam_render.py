"""Kirish nazorati (Face ID) — tasvir qatlami.

1) SINTETIK kadr (demo): kirish kamerasi ko'rinishi (devor, eshik, turniket, pol perspektivasi, OSD), stilize odamlar.
   Hech qanday haqiqiy surat ishlatilmaydi — hammasi PIL primitivlari, `seed` bo'yicha deterministik.
2) IZOH qatlami (haqiqiy kamerada ham xuddi shu): yuz ramkasi (tur bo'yicha rang), yorliq, yo'nalish, pastki satr.
   Haqiqiy kamerada fon rasmi kamera yuborgan JPEG (data/face_snaps/, ISFT_CORE_FACE_KEEP_DAYS kundan ortiq saqlanmaydi).

Koordinatalar: yuz to'rtburchagi (rect) 0..1 oralig'ida [x, y, w, h] — Hikvision alarmResult `faceRect` bilan bir xil.
Sintetik kadrda odam aynan shu rect atrofida chiziladi, ya'ni ramka va odam doimo mos keladi.
"""
import io, math, random, datetime as dt
from functools import lru_cache
from pathlib import Path
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageEnhance, ImageOps

W, H = 1280, 720
SS = 2                      # supersampling: 2x chizib, keyin kichraytiramiz (silliq qirralar)

# ---------------------------------------------------------------------------------------------
# Shriftlar (macOS / Linux / Pillow ichki shrifti)
# ---------------------------------------------------------------------------------------------
_FONTS = {
    "b": ["/System/Library/Fonts/Supplemental/Arial Bold.ttf", "/Library/Fonts/Arial Bold.ttf",
          "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf"],
    "r": ["/System/Library/Fonts/Supplemental/Arial.ttf", "/Library/Fonts/Arial.ttf",
          "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/usr/share/fonts/dejavu/DejaVuSans.ttf"],
    "m": ["/System/Library/Fonts/Supplemental/Courier New Bold.ttf", "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
          "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"],
}

@lru_cache(maxsize=64)
def font(kind: str, size: int):
    for p in _FONTS.get(kind, _FONTS["r"]):
        if Path(p).exists():
            try: return ImageFont.truetype(p, size)
            except OSError: pass
    try: return ImageFont.load_default(size=size)
    except TypeError: return ImageFont.load_default()

# ---------------------------------------------------------------------------------------------
# Ranglar
# ---------------------------------------------------------------------------------------------
SKIN = [(241, 206, 177), (232, 192, 160), (222, 180, 146), (205, 160, 124), (186, 140, 104), (160, 116, 84), (238, 200, 170), (214, 170, 136)]
HAIR = [(24, 20, 18), (36, 28, 24), (52, 38, 30), (70, 50, 36), (96, 68, 44), (30, 26, 26), (128, 98, 70), (150, 146, 140)]
TOPS = [(34, 44, 72), (30, 30, 34), (104, 108, 116), (186, 168, 140), (52, 72, 58), (108, 36, 48), (226, 226, 222), (146, 176, 206),
        (70, 94, 128), (88, 60, 92), (150, 70, 52), (60, 60, 70), (176, 196, 214), (200, 90, 90), (74, 112, 92)]
BOTTOMS = [(34, 34, 40), (40, 46, 66), (58, 78, 112), (164, 146, 118), (46, 46, 52), (72, 66, 60), (28, 30, 36)]
SCARF = [(108, 36, 60), (40, 60, 96), (190, 176, 160), (60, 90, 80), (150, 120, 150), (220, 212, 200), (80, 54, 46), (170, 70, 80)]
WALLS = {"A": ((214, 204, 186), (196, 186, 168)), "B": ((196, 204, 210), (176, 186, 194)), "E": ((204, 210, 192), (186, 192, 174))}

# izoh ranglari (tur bo'yicha)
KIND_RGB = {"talaba": (37, 99, 235), "oqituvchi": (22, 163, 74), "xodim": (147, 51, 234),
            "notanish": (220, 38, 38), "rozilik_yoq": (220, 38, 38), "past_ishonch": (217, 119, 6), "yashirin": (100, 116, 139)}

def _mix(a, b, t):
    return tuple(int(round(a[i] + (b[i] - a[i]) * t)) for i in range(3))

def _dk(c, f=0.75): return tuple(max(0, int(x * f)) for x in c[:3])
def _lt(c, f=0.25): return _mix(c, (255, 255, 255), f)

# ---------------------------------------------------------------------------------------------
# Tashqi ko'rinish (yuz "look" seed'idan) — bir xil odam har kadrda bir xil ko'rinadi
# ---------------------------------------------------------------------------------------------
def look(seed: int, female: bool | None = None) -> dict:
    r = random.Random(seed * 7919 + 13)
    fem = (r.random() < .45) if female is None else bool(female)
    old = r.random() < .12
    L = {"female": fem, "skin": r.choice(SKIN), "hair_c": HAIR[7] if old and r.random() < .7 else r.choice(HAIR[:7] if r.random() < .93 else HAIR),
         "top": r.choice(TOPS), "bottom": r.choice(BOTTOMS), "glasses": r.random() < (.32 if old else .2),
         "bag": r.choice(["none", "none", "backpack", "backpack", "shoulder", "folder"]), "lean": r.uniform(-.05, .05),
         "stride": r.choice([-1, 0, 1]), "inner": r.choice([(236, 236, 232), (210, 222, 236), (240, 238, 226), (60, 60, 66)]),
         "jacket": r.random() < .55, "tie": False, "beard": False, "scarf": None, "skirt": False}
    if fem:
        if r.random() < .38: L["hair"], L["scarf"] = "scarf", r.choice(SCARF)
        else: L["hair"] = r.choice(["long", "long", "bun", "bob", "pony"])
        L["skirt"] = r.random() < .35
    else:
        L["hair"] = r.choice(["short", "short", "side", "side", "buzz", "curly", "bald" if old else "short"])
        L["beard"] = r.random() < (.35 if old else .16)
        L["tie"] = L["jacket"] and r.random() < .3
    return L

# ---------------------------------------------------------------------------------------------
# Sahna (fon)
# ---------------------------------------------------------------------------------------------
VP = (640, 250)
BACK = (300, 70, 980, 330)       # orqa devor: x0, y0, x1, y1

def _p(pts, s=SS): return [(x * s, y * s) for x, y in pts]

def _floor_x(x0, y):
    """Orqa devor chizig'idagi x0 nuqtadan VP orqali o'tgan chiziqning y balandlikdagi x qiymati."""
    return VP[0] + (x0 - VP[0]) * (y - VP[1]) / (BACK[3] - VP[1])

def _scene(d: ImageDraw.ImageDraw, r: random.Random, bld: str, direction: str, night: bool, ts: dt.datetime):
    wall, wall2 = WALLS.get(bld, WALLS["A"])
    x0, y0, x1, y1 = BACK
    ceil = (226, 226, 222)
    # shift: binoga qarab devor rangi, ichki yorug'lik
    d.polygon(_p([(0, 0), (W, 0), (x1, y0), (x0, y0)]), fill=ceil)
    for i in range(3):        # shiftdagi chiroq panellari (perspektivada)
        t0, t1 = .18 + i * .27, .3 + i * .27
        ya, yb = y0 * (1 - t0) + 0 * t0, y0 * (1 - t1)
        cx = 640
        wa, wb = 120 + 240 * (1 - ya / y0), 120 + 240 * (1 - yb / y0)
        d.polygon(_p([(cx - wb / 2, yb), (cx + wb / 2, yb), (cx + wa / 2, ya), (cx - wa / 2, ya)]), fill=(250, 250, 244))
    d.line(_p([(0, 0), (x0, y0)]), fill=_dk(ceil, .9), width=2 * SS); d.line(_p([(W, 0), (x1, y0)]), fill=_dk(ceil, .9), width=2 * SS)
    # yon devorlar
    d.polygon(_p([(0, 0), (x0, y0), (x0, y1), (0, 610)]), fill=wall2)
    d.polygon(_p([(W, 0), (x1, y0), (x1, y1), (W, 610)]), fill=_dk(wall2, .96))
    # orqa devor
    d.rectangle(_p([(x0, y0), (x1, y1)]), fill=wall)
    # pol
    fl = (172, 168, 160) if bld != "B" else (160, 164, 168)
    d.polygon(_p([(x0, y1), (x1, y1), (W, 610), (W, H), (0, H), (0, 610)]), fill=fl)
    for k in range(1, 9):     # plitka chiziqlari: gorizontal (perspektiva bilan zichlashadi)
        t = (k / 9) ** 1.8; y = y1 + (H - y1) * t
        xa = x0 - (x0 - 0) * min(1, (y - y1) / (610 - y1)) if y < 610 else 0
        xb = x1 + (W - x1) * min(1, (y - y1) / (610 - y1)) if y < 610 else W
        d.line(_p([(xa, y), (xb, y)]), fill=_dk(fl, .9), width=SS)
    for xx in range(x0, x1 + 1, 68):
        d.line(_p([(xx, y1), (_floor_x(xx, H), H)]), fill=_dk(fl, .9), width=SS)
    # plintus
    d.line(_p([(x0, y1), (x1, y1)]), fill=_dk(wall, .7), width=3 * SS)
    d.line(_p([(0, 610), (x0, y1)]), fill=_dk(wall2, .7), width=3 * SS); d.line(_p([(W, 610), (x1, y1)]), fill=_dk(wall2, .7), width=3 * SS)
    if direction == "kirish":
        _doors(d, r, night, wall)
    else:
        _interior(d, r, wall, bld)
    # o'ng devor: o't o'chirgich va eshik ramkasi; chap devor: skameyka
    d.polygon(_p([(1112, 250), (1132, 244), (1132, 300), (1112, 304)]), fill=(196, 30, 36))
    d.polygon(_p([(1040, 140), (1100, 118), (1100, 398), (1040, 372)]), outline=_dk(wall2, .62), width=3 * SS)
    d.polygon(_p([(40, 520), (190, 452), (190, 470), (40, 545)]), fill=(92, 74, 60))
    # turniketlar (faqat kirish sahnasida — kamera ko'chadan kirganlarga qaragan)
    if direction == "kirish":
        _turnstiles(d, night)
    else:
        d.rectangle(_p([(820, 238), (930, 300)]), fill=(120, 84, 56)); d.rectangle(_p([(816, 232), (934, 240)]), fill=(150, 112, 80))   # navbatchi stoli

def _doors(d, r, night, wall):
    x0, y0, x1, y1 = BACK
    sky_t, sky_b = ((18, 24, 46), (30, 36, 54)) if night else ((196, 214, 228), (226, 232, 236))
    for gx0, gx1 in ((380, 508), (520, 760), (772, 900)):
        for yy in range(118, y1, 4):        # tashqi ko'rinish gradienti
            t = (yy - 118) / (y1 - 118)
            d.rectangle(_p([(gx0, yy), (gx1, yy + 4)]), fill=_mix(sky_t, sky_b, t))
        gy = 262                            # tashqi yer
        d.rectangle(_p([(gx0, gy), (gx1, y1)]), fill=(44, 46, 54) if night else (150, 152, 150))
        if not night:
            for k in range(3):              # daraxtlar
                tx = r.randint(gx0, gx1); tr = r.randint(16, 30)
                d.ellipse(_p([(tx - tr, gy - tr * 2.2), (tx + tr, gy - tr * .2)]), fill=(84 + r.randint(-10, 10), 112, 76))
                d.rectangle(_p([(tx - 2, gy - tr * .4), (tx + 2, gy)]), fill=(80, 64, 50))
        else:
            lx = r.randint(gx0 + 10, gx1 - 10)
            d.ellipse(_p([(lx - 14, 150), (lx + 14, 178)]), fill=(120, 110, 70))
        d.rectangle(_p([(gx0, 118), (gx1, y1)]), outline=(150, 154, 160), width=5 * SS)
    d.line(_p([(640, 118), (640, y1)]), fill=(150, 154, 160), width=5 * SS)          # eshik tabaqalari
    for hx in (626, 654): d.line(_p([(hx, 200), (hx, 250)]), fill=(196, 198, 204), width=3 * SS)
    d.rectangle(_p([(560, 84), (720, 108)]), fill=(135, 0, 55))                     # "KIRISH" lavhasi
    f = font("b", 16 * SS); tw = d.textlength("KIRISH", font=f)
    d.text((640 * SS - tw / 2, 86 * SS), "KIRISH", fill=(255, 255, 255), font=f)
    if night:   # tunda — ichkarida ham yorug'lik kam
        pass

def _interior(d, r, wall, bld):
    x0, y0, x1, y1 = BACK
    # koridorga o'tish (markazda) — ichkariga perspektiva
    d.rectangle(_p([(560, 120), (720, y1)]), fill=_dk(wall, .55))
    d.polygon(_p([(560, 120), (720, 120), (690, 160), (590, 160)]), fill=_dk(wall, .7))
    d.polygon(_p([(590, 160), (690, 160), (690, 300), (590, 300)]), fill=_dk(wall, .42))
    d.polygon(_p([(560, y1), (720, y1), (690, 300), (590, 300)]), fill=_dk((170, 166, 158), .65))
    # e'lonlar taxtasi
    d.rectangle(_p([(350, 140), (500, 250)]), fill=(176, 138, 96), outline=(110, 80, 52), width=3 * SS)
    for k in range(6):
        px, py = 360 + (k % 3) * 46, 150 + (k // 3) * 48
        d.rectangle(_p([(px, py), (px + 38, py + 40)]), fill=r.choice([(244, 244, 238), (236, 232, 200), (220, 232, 244)]))
    # soat va lavha
    d.ellipse(_p([(800, 120), (840, 160)]), fill=(250, 250, 250), outline=(60, 60, 60), width=2 * SS)
    d.line(_p([(820, 140), (820, 126)]), fill=(30, 30, 30), width=2 * SS); d.line(_p([(820, 140), (831, 144)]), fill=(30, 30, 30), width=2 * SS)
    d.rectangle(_p([(580, 90), (700, 110)]), fill=(135, 0, 55))
    f = font("b", 13 * SS); t = f"{bld}-BINO"; tw = d.textlength(t, font=f)
    d.text((640 * SS - tw / 2, 92 * SS), t, fill=(255, 255, 255), font=f)
    # gul
    d.rectangle(_p([(930, 280), (960, 330)]), fill=(120, 96, 80))
    for k in range(7):
        a = -math.pi / 2 + (k - 3) * .38
        d.ellipse(_p([(945 + 34 * math.cos(a) - 14, 270 + 30 * math.sin(a) - 9), (945 + 34 * math.cos(a) + 14, 270 + 30 * math.sin(a) + 9)]), fill=(64, 112, 70))

def _turnstiles(d, night):
    y = 452
    for i, cx in enumerate((372, 528, 752, 908)):
        w, h = 40, 92
        d.rectangle(_p([(cx - w / 2, y - h), (cx + w / 2, y)]), fill=(178, 182, 188), outline=(120, 124, 130), width=2 * SS)
        d.rectangle(_p([(cx - w / 2, y - h), (cx + w / 2, y - h + 10)]), fill=(206, 210, 216))
        d.rectangle(_p([(cx - 9, y - h + 18), (cx + 9, y - h + 28)]), fill=(22, 160, 80) if i != 2 else (200, 40, 40))
        if i < 3:   # uch shoxli to'siq
            for a in (-.5, .1, .7):
                d.line(_p([(cx + w / 2, y - 58), (cx + w / 2 + 52 * math.cos(a), y - 58 + 14 * math.sin(a))]), fill=(200, 204, 210), width=4 * SS)
    d.line(_p([(300, y), (980, y)]), fill=(140, 140, 136), width=2 * SS)

# ---------------------------------------------------------------------------------------------
# Odam (oldga qarab yuryapti). cx, cy — yuz markazi, hh — bosh balandligi (px, 1280x720 bo'yicha)
# ---------------------------------------------------------------------------------------------
def _person(d: ImageDraw.ImageDraw, cx, cy, hh, L: dict):
    s = SS
    def E(x0, y0, x1, y1, **kw): d.ellipse([x0 * s, y0 * s, x1 * s, y1 * s], **kw)
    def R(x0, y0, x1, y1, rad=0, **kw): d.rounded_rectangle([x0 * s, y0 * s, x1 * s, y1 * s], radius=rad * s, **kw)
    def P(pts, **kw): d.polygon([(x * s, y * s) for x, y in pts], **kw)
    hw = hh * .76                              # bosh eni
    top, bot = cy - hh / 2, cy + hh / 2
    skin, top_c, bottom = L["skin"], L["top"], L["bottom"]
    sh_y = bot + hh * .32                      # yelka chizig'i
    sw = hh * 1.05                             # yelka yarim eni
    hip_y = sh_y + hh * 2.65
    feet_y = hip_y + hh * 3.3
    lean = L["lean"] * hh
    # --- oyoqlar
    gap = hh * .08
    for side in (-1, 1):
        fwd = (L["stride"] == side) * hh * .25
        lx0 = cx + lean + side * gap if side > 0 else cx + lean - hh * .62
        lx1 = cx + lean + hh * .62 if side > 0 else cx + lean - gap
        if L["skirt"]:
            continue
        R(lx0, hip_y - hh * .2, lx1, feet_y + fwd, rad=hh * .12, fill=bottom)
        R(lx0 - hh * .04, feet_y + fwd - hh * .12, lx1 + hh * .06, feet_y + fwd + hh * .14, rad=hh * .1, fill=(28, 26, 26))
    if L["skirt"]:
        P([(cx - sw * .78 + lean, hip_y - hh * .3), (cx + sw * .78 + lean, hip_y - hh * .3), (cx + sw * 1.0 + lean, feet_y - hh * .4), (cx - sw * 1.0 + lean, feet_y - hh * .4)], fill=bottom)
        for side in (-1, 1):
            R(cx + side * hh * .3 - hh * .18 + lean, feet_y - hh * .5, cx + side * hh * .3 + hh * .18 + lean, feet_y + hh * .05, rad=hh * .08, fill=_dk(skin, .8))
            R(cx + side * hh * .3 - hh * .24 + lean, feet_y - hh * .06, cx + side * hh * .3 + hh * .24 + lean, feet_y + hh * .14, rad=hh * .08, fill=(30, 26, 26))
    # --- qo'llar (tana ortida)
    sleeve = top_c if L["jacket"] or L["hair"] == "scarf" or (sum(top_c) < 400) else top_c
    for side in (-1, 1):
        ax = cx + side * (sw * .92) + lean
        swing = side * (L["stride"] or 1) * hh * .08
        P([(ax - hh * .26, sh_y + hh * .15), (ax + hh * .26, sh_y + hh * .15), (ax + hh * .22 + side * hh * .16 + swing, hip_y + hh * .2), (ax - hh * .2 + side * hh * .16 + swing, hip_y + hh * .2)],
          fill=_dk(sleeve, .9))
        E(ax - hh * .19 + side * hh * .16 + swing, hip_y + hh * .1, ax + hh * .19 + side * hh * .16 + swing, hip_y + hh * .52, fill=_dk(skin, .92))
    # --- tana
    torso = [(cx - sw + lean, sh_y + hh * .22), (cx - sw * .78 + lean, sh_y - hh * .02), (cx + sw * .78 + lean, sh_y - hh * .02), (cx + sw + lean, sh_y + hh * .22),
             (cx + sw * .82 + lean, hip_y + hh * .05), (cx - sw * .82 + lean, hip_y + hh * .05)]
    if L["hair"] == "scarf":   # ro'molli — uzun ko'ylak/kardigan
        torso[-2] = (cx + sw * .9 + lean, hip_y + hh * .9); torso[-1] = (cx - sw * .9 + lean, hip_y + hh * .9)
    P(torso, fill=top_c)
    for side in (-1, 1):
        E(cx + side * sw * .82 + lean - hh * .3, sh_y - hh * .04, cx + side * sw * .82 + lean + hh * .3, sh_y + hh * .5, fill=top_c if side < 0 else _dk(top_c, .86))
    P([(cx + sw * .25 + lean, sh_y), (cx + sw + lean, sh_y + hh * .22), (cx + sw * .82 + lean, hip_y + hh * .05), (cx + sw * .3 + lean, hip_y + hh * .05)], fill=_dk(top_c, .86))
    if L["jacket"]:           # ochiq kurtka: ichki ko'ylak va lattsan
        P([(cx - hh * .22 + lean, sh_y - hh * .02), (cx + hh * .22 + lean, sh_y - hh * .02), (cx + hh * .06 + lean, hip_y), (cx - hh * .06 + lean, hip_y)], fill=L["inner"])
        P([(cx - hh * .22 + lean, sh_y - hh * .02), (cx - hh * .02 + lean, sh_y + hh * .5), (cx - hh * .3 + lean, sh_y + hh * .32)], fill=_dk(top_c, .78))
        P([(cx + hh * .22 + lean, sh_y - hh * .02), (cx + hh * .02 + lean, sh_y + hh * .5), (cx + hh * .3 + lean, sh_y + hh * .32)], fill=_dk(top_c, .7))
        if L["tie"]:
            P([(cx - hh * .05 + lean, sh_y + hh * .05), (cx + hh * .05 + lean, sh_y + hh * .05), (cx + hh * .08 + lean, sh_y + hh * 1.3), (cx + lean, sh_y + hh * 1.45),
               (cx - hh * .08 + lean, sh_y + hh * 1.3)], fill=(120, 30, 40) if sum(top_c) > 200 else (60, 70, 120))
    else:
        E(cx - hh * .2 + lean, sh_y - hh * .1, cx + hh * .2 + lean, sh_y + hh * .14, fill=_dk(top_c, .8))     # yoqa
    # --- sumka
    if L["bag"] == "backpack":
        for side in (-1, 1):
            P([(cx + side * sw * .55 + lean - hh * .07, sh_y - hh * .02), (cx + side * sw * .55 + lean + hh * .07, sh_y - hh * .02),
               (cx + side * sw * .62 + lean + hh * .08, sh_y + hh * 1.6), (cx + side * sw * .62 + lean - hh * .08, sh_y + hh * 1.6)], fill=(30, 32, 38))
        R(cx + sw * .9 + lean, sh_y + hh * .3, cx + sw * 1.18 + lean, sh_y + hh * 1.9, rad=hh * .1, fill=(40, 44, 54))     # yondan ko'ringan ryukzak
    elif L["bag"] == "shoulder":
        d.line([((cx - sw * .6 + lean) * s, (sh_y) * s), ((cx + sw * .85 + lean) * s, (hip_y - hh * .1) * s)], fill=(54, 40, 32), width=max(2, int(hh * .07 * s)))
        R(cx + sw * .62 + lean, hip_y - hh * .45, cx + sw * 1.32 + lean, hip_y + hh * .45, rad=hh * .1, fill=(96, 64, 44))
    elif L["bag"] == "folder":
        R(cx - sw * 1.2 + lean, hip_y - hh * .6, cx - sw * .7 + lean, hip_y + hh * .5, rad=hh * .05, fill=(60, 90, 140))
    # --- bo'yin
    R(cx - hh * .17 + lean * .5, bot - hh * .12, cx + hh * .17 + lean * .5, sh_y + hh * .06, rad=hh * .06, fill=_dk(skin, .88))
    # --- soch (orqa qism) / ro'mol
    hc = L["hair_c"]
    if L["hair"] == "scarf":
        sc = L["scarf"]
        P([(cx - hw * .78, cy), (cx + hw * .78, cy), (cx + sw * .82, sh_y + hh * .5), (cx - sw * .82, sh_y + hh * .5)], fill=_dk(sc, .9))
        E(cx - hw * .74, top - hh * .1, cx + hw * .74, bot + hh * .22, fill=sc)
    elif L["hair"] in ("long", "pony"):
        ln = .85 if L["hair"] == "long" else .25
        for side in (-1, 1):
            P([(cx + side * hw * .2, top + hh * .05), (cx + side * hw * .66, top + hh * .3), (cx + side * hw * .72, bot + hh * ln),
               (cx + side * hw * .36, bot + hh * ln), (cx + side * hw * .3, cy)], fill=_dk(hc, .85))
    elif L["hair"] == "bob":
        R(cx - hw * .6, top + hh * .05, cx + hw * .6, bot - hh * .05, rad=hh * .3, fill=_dk(hc, .9))
    # --- bosh va quloqlar
    if L["hair"] != "scarf":
        for side in (-1, 1):
            E(cx + side * hw * .5 - hh * .08, cy - hh * .1, cx + side * hw * .5 + hh * .08, cy + hh * .14, fill=_dk(skin, .9))
    E(cx - hw / 2, top, cx + hw / 2, bot, fill=_dk(skin, .84))                                    # soya (o'ng tomon)
    E(cx - hw / 2, top + hh * .01, cx + hw * .4, bot - hh * .03, fill=skin)                     # yoritilgan qism
    E(cx - hw * .34, cy + hh * .1, cx - hw * .14, cy + hh * .24, fill=_mix(skin, (226, 120, 110), .12))   # yonoq
    E(cx + hw * .14, cy + hh * .1, cx + hw * .34, cy + hh * .24, fill=_mix(_dk(skin, .9), (226, 120, 110), .1))
    # --- yuz belgilari
    ey = cy - hh * .04
    for side in (-1, 1):
        ex = cx + side * hw * .2
        E(ex - hh * .07, ey - hh * .035, ex + hh * .07, ey + hh * .035, fill=(250, 248, 244))
        E(ex - hh * .035, ey - hh * .035, ex + hh * .035, ey + hh * .035, fill=(40, 30, 26))
        d.line([((ex - hh * .09) * s, (ey - hh * .1) * s), ((ex + hh * .08) * s, (ey - hh * .12) * s)], fill=_dk(hc, .9), width=max(2, int(hh * .035 * s)))
    P([(cx + hh * .01, ey + hh * .04), (cx + hh * .07, cy + hh * .17), (cx - hh * .01, cy + hh * .17)], fill=_dk(skin, .86))   # burun soyasi
    E(cx - hh * .07, cy + hh * .13, cx + hh * .07, cy + hh * .2, fill=_dk(skin, .8))
    mc = (150, 70, 70) if L["female"] else _dk(skin, .62)
    d.line([((cx - hh * .11) * s, (cy + hh * .3) * s), ((cx + hh * .11) * s, (cy + hh * .3) * s)], fill=mc, width=max(2, int(hh * .035 * s)))
    if L["beard"]:
        bc = _mix(hc, skin, .25)
        d.chord([(cx - hw * .48) * s, (cy - hh * .15) * s, (cx + hw * .48) * s, (bot + hh * .04) * s], 10, 170, fill=bc)
        R(cx - hh * .14, cy + hh * .22, cx + hh * .14, cy + hh * .27, rad=2, fill=bc)
        d.line([((cx - hh * .1) * s, (cy + hh * .32) * s), ((cx + hh * .1) * s, (cy + hh * .32) * s)], fill=_dk(skin, .55), width=max(2, int(hh * .03 * s)))
    # --- soch (old qism)
    hs = L["hair"]
    if hs == "scarf":
        sc = L["scarf"]
        d.chord([(cx - hw * .6) * s, (top - hh * .02) * s, (cx + hw * .6) * s, (top + hh * .5) * s], 180, 360, fill=sc)
        d.arc([(cx - hw * .56) * s, (top + hh * .02) * s, (cx + hw * .56) * s, (bot + hh * .18) * s], 200, 340, fill=_dk(sc, .8), width=max(2, int(hh * .05 * s)))
        P([(cx - hw * .5, cy + hh * .35), (cx + hw * .5, cy + hh * .35), (cx + hw * .3, bot + hh * .3), (cx - hw * .3, bot + hh * .3)], fill=sc)
    elif hs in ("short", "side", "curly", "long", "bun", "bob", "pony"):
        d.chord([(cx - hw * .56) * s, (top - hh * .08) * s, (cx + hw * .56) * s, (top + hh * (.62 if hs in ("long", "bob", "pony") else .5)) * s], 180, 360, fill=hc)
        if hs in ("short", "side", "curly"):
            for side in (-1, 1):
                R(cx + side * hw * .5 - hh * .07, top + hh * .18, cx + side * hw * .5 + hh * .07, cy - hh * .02, rad=hh * .04, fill=hc)
        if hs == "side":
            P([(cx - hw * .5, top + hh * .24), (cx + hw * .1, top + hh * .1), (cx + hw * .52, top + hh * .3), (cx + hw * .52, top + hh * .2), (cx - hw * .3, top - hh * .02)], fill=hc)
        if hs == "curly":
            for k in range(7):
                a = math.pi + k * math.pi / 6
                E(cx + hw * .5 * math.cos(a) - hh * .12, top + hh * .28 + hh * .3 * math.sin(a) - hh * .12, cx + hw * .5 * math.cos(a) + hh * .12, top + hh * .28 + hh * .3 * math.sin(a) + hh * .12, fill=hc)
        if hs == "bun":
            E(cx - hh * .2, top - hh * .26, cx + hh * .2, top + hh * .06, fill=hc)
        if hs in ("long", "bob", "pony"):
            for side in (-1, 1):
                R(cx + side * hw * .55 - hh * .06, top + hh * .2, cx + side * hw * .55 + hh * .06, cy + hh * .05, rad=hh * .05, fill=hc)
    elif hs == "buzz":
        d.chord([(cx - hw * .53) * s, (top - hh * .02) * s, (cx + hw * .53) * s, (top + hh * .44) * s], 180, 360, fill=_mix(hc, skin, .45))
    # --- ko'zoynak
    if L["glasses"]:
        lw = max(2, int(hh * .03 * s))
        for side in (-1, 1):
            ex = cx + side * hw * .2
            d.rounded_rectangle([(ex - hh * .11) * s, (ey - hh * .07) * s, (ex + hh * .11) * s, (ey + hh * .07) * s], radius=hh * .03 * s, outline=(30, 30, 34), width=lw)
        d.line([((cx - hw * .2 + hh * .11) * s, ey * s), ((cx + hw * .2 - hh * .11) * s, ey * s)], fill=(30, 30, 34), width=lw)

def _bystander(d, r, night):
    """Kichik (uzoqdagi) odam — yuzi juda kichik, kamera aniqlamaydi (izohsiz)."""
    hh = r.uniform(17, 24)
    cx = r.choice([r.uniform(330, 520), r.uniform(760, 950)])
    cy = 300 + (hh - 17) * 2
    _person(d, cx, cy, hh, look(r.randint(1, 10 ** 6)))

def rect_geom(rect):
    """rect (0..1) → (cx, cy, hh) piksel (1280x720). Bosh balandligi rect balandligining 1/1.1 qismi."""
    x, y, w, h = rect
    return (x + w / 2) * W, (y + h * .52) * H, h * H / 1.1

def make_rect(cx, cy, hh):
    w, h = hh * .84 / W, hh * 1.1 / H
    return [round(cx / W - w / 2, 4), round(cy / H - h * .52, 4), round(w, 4), round(h, 4)]

def layout(r: random.Random, n: int) -> list:
    """Kadrdagi n ta odam uchun yuz to'rtburchaklari (deterministik). Uzoqdagilar kichik va yuqoriroqda."""
    out, tries = [], 0
    while len(out) < n and tries < 400:
        tries += 1
        hh = r.uniform(70, 126) if n > 1 else r.uniform(84, 132)
        cy = 212 + (hh - 70) * 1.35 + r.uniform(-8, 8)
        cx = r.uniform(190, 1090) if n > 1 else r.uniform(380, 900)
        if any(abs(cx - c) < (hh + h2) * 1.5 for c, _, h2 in out): continue
        out.append((cx, cy, hh))
    return [make_rect(*o) for o in out]

# ---------------------------------------------------------------------------------------------
# Kadr: sahna + odamlar + kamera effektlari + OSD
# ---------------------------------------------------------------------------------------------
WD = ["Dsh", "Ssh", "Chr", "Pay", "Jum", "Shn", "Yak"]

def scene_image(seed: int, ts: str, cam_name: str, bld: str, direction: str, faces: tuple) -> Image.Image:
    """faces: ((rect tuple, look_seed, female|None), ...). Qaytaradi: RGB 1280x720 (OSD bilan, izohsiz)."""
    t = dt.datetime.fromisoformat(ts)
    night = not (7 <= t.hour < 19 or (t.hour == 19 and t.minute < 30))
    r = random.Random(seed)
    im = Image.new("RGB", (W * SS, H * SS), (200, 200, 200))
    d = ImageDraw.Draw(im)
    _scene(d, r, bld, direction, night, t)
    for _ in range(r.choice([0, 0, 1, 1, 2])):
        if not night: _bystander(d, r, night)          # tunda lobbida boshqa odam yo'q (r ketma-ketligi baribir bir xil)
        else: r.random(); r.random(); r.random()
    people = sorted(faces, key=lambda f: f[0][3])        # uzoqdagilar (kichik) avval
    for rect, lk, fem in people:
        cx, cy, hh = rect_geom(rect)
        _person(d, cx, cy, hh, look(lk, fem))
    im = im.resize((W, H), Image.LANCZOS)
    return camera_look(im, t, cam_name, r, "SINTETIK · demo")

def camera_look(im: Image.Image, t: dt.datetime, cam_name: str, r: random.Random, mark: str, blur: float = 1.25) -> Image.Image:
    """Kamera effektlari (yumshoq fokus, shovqin, rang, vinyetka; tunda IQ — oq-qora) va Hikvision uslubidagi OSD."""
    night = not (7 <= t.hour < 19 or (t.hour == 19 and t.minute < 30))
    # --- kamera effektlari: yumshoq fokus, shovqin, rang, vinyetka; tunda IQ (oq-qora)
    im = im.filter(ImageFilter.GaussianBlur(blur))
    light = Image.linear_gradient("L").resize((W, H)).point(lambda v: int(255 - v * .22))
    im = Image.composite(im, Image.new("RGB", im.size, (0, 0, 0)), light)
    im = ImageEnhance.Contrast(im).enhance(.9)
    if night:
        im = ImageOps.grayscale(im).convert("RGB")
        im = ImageEnhance.Brightness(im).enhance(.82)
        im = ImageEnhance.Contrast(im).enhance(1.12)
    else:
        im = ImageEnhance.Color(im).enhance(.82)
        tint = Image.new("RGB", im.size, (255, 246, 226) if r.random() < .6 else (236, 244, 255))
        im = Image.blend(im, tint, .06)
    noise = Image.effect_noise((W, H), 22 if night else 14).convert("RGB")
    im = Image.blend(im, noise, .09 if night else .06)
    vig = Image.radial_gradient("L").resize((W, H)).point(lambda v: int(255 - v * .35))
    im = Image.composite(im, Image.new("RGB", im.size, (0, 0, 0)), vig)
    # --- OSD (Hikvision uslubi: oq matn, qora hoshiya)
    od = ImageDraw.Draw(im)
    f = font("b", 24)
    osd = f"{t:%d-%m-%Y} {WD[t.weekday()]} {t:%H:%M:%S}"
    od.text((24, 18), osd, font=f, fill=(255, 255, 255), stroke_width=2, stroke_fill=(0, 0, 0))
    tw = od.textlength(cam_name, font=f)
    od.text((W - 24 - tw, H - 46), cam_name, font=f, fill=(255, 255, 255), stroke_width=2, stroke_fill=(0, 0, 0))
    fw = font("b", 13)
    od.text((24, H - 30), mark, font=fw, fill=(255, 255, 255, 140), stroke_width=1, stroke_fill=(40, 40, 40))
    return im

# ---------------------------------------------------------------------------------------------
# Namuna rasmlar to'plami (ixtiyoriy, faqat lokal): data/facecam_photos/manifest.json
#   [{"file": "x.jpg" (1280x720), "faces": [{"r": [x,y,w,h] 0..1, "f": true|false|null}], "src": "...", "lic": "..."}]
# To'plam git'ga kirmaydi (data/ — .gitignore). Bo'lmasa — sintetik chizma ishlatiladi.
# ---------------------------------------------------------------------------------------------
PACK_DIR = Path(__file__).resolve().parent.parent / "data" / "facecam_photos"
_PACK: dict = {}

def photo_pack() -> list:
    import json
    mf = PACK_DIR / "manifest.json"
    try: mt = mf.stat().st_mtime
    except OSError: return []
    if _PACK.get("mt") != mt:
        try: _PACK.update(mt=mt, items=[x for x in json.loads(mf.read_text()) if (PACK_DIR / x["file"]).exists() and x.get("faces")])
        except Exception: _PACK.update(mt=mt, items=[])
    return _PACK["items"]

def photo_scene(seed: int, ts: str, cam_name: str, faces: tuple):
    """faces: ((rect, look, female|None), ...) — voqealar tartibida. Yuzlari soni mos namuna rasm topilsa:
    (rasm, [har bir voqea uchun rasmdagi yuz rect]) qaytaradi, aks holda None."""
    items = [x for x in photo_pack() if len(x["faces"]) == len(faces)]
    if not items: return None
    want = [f[2] for f in faces]
    def score(x):   # jins mosligi (yuzlar tartibini almashtirib ham)
        import itertools
        best = max(itertools.permutations(range(len(x["faces"]))),
                   key=lambda pm: sum(1 for i, j in enumerate(pm) if want[i] is None or x["faces"][j].get("f") is None or x["faces"][j]["f"] == want[i]))
        return sum(1 for i, j in enumerate(best) if want[i] is None or x["faces"][j].get("f") is None or x["faces"][j]["f"] == want[i]), best
    r = random.Random(seed)
    scored = [(score(x), x) for x in items]
    top = max(s[0][0] for s in scored)
    (_, perm), x = r.choice([s for s in scored if s[0][0] == top])
    im = Image.open(PACK_DIR / x["file"]).convert("RGB")
    if im.size != (W, H): im = ImageOps.fit(im, (W, H), Image.LANCZOS)
    if r.random() < .5 and not x.get("nomirror"):            # ko'zgu — bir rasm ikki xil ko'rinadi
        im = ImageOps.mirror(im)
        rects = [[round(1 - f["r"][0] - f["r"][2], 4), *f["r"][1:]] for f in x["faces"]]
    else:
        rects = [list(f["r"]) for f in x["faces"]]
    t = dt.datetime.fromisoformat(ts)
    return camera_look(im, t, cam_name, r, "Namuna rasm · demo", blur=.6), [rects[j] for j in perm]

# ---------------------------------------------------------------------------------------------
# Izoh qatlami
# ---------------------------------------------------------------------------------------------
def annotate(im: Image.Image, faces: list, direction: str, footer: str) -> Image.Image:
    """faces: [{rect, color_key, label, sub, hidden(bool)}]. hidden — yuz pikselga aylantiriladi (ko'lamdan tashqari shaxs)."""
    im = im.copy()
    for f in faces:
        if not f.get("hidden"): continue
        x, y, w, h = f["rect"]
        box = (int(x * W) - 4, int(y * H) - 4, int((x + w) * W) + 4, int((y + h) * H) + 4)
        box = (max(0, box[0]), max(0, box[1]), min(W, box[2]), min(H, box[3]))
        reg = im.crop(box)
        reg = reg.resize((max(1, reg.width // 12), max(1, reg.height // 12)), Image.BILINEAR).resize(reg.size, Image.NEAREST)
        im.paste(reg, box[:2])
    ov = Image.new("RGBA", im.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)
    fl, fs = font("b", 19), font("r", 15)
    placed = [(W - 300, 0, W, 60), (0, 0, 330, 52)]          # yo'nalish belgisi va OSD sanasi — yorliq ularni yopmasin
    def hit(b): return any(not (b[2] < p[0] or b[0] > p[2] or b[3] < p[1] or b[1] > p[3]) for p in placed)
    for f in sorted(faces, key=lambda f: f["rect"][0]):
        x, y, w, h = f["rect"]
        c = KIND_RGB.get(f["color"], KIND_RGB["notanish"])
        x0, y0, x1, y1 = x * W - 6, y * H - 6, (x + w) * W + 6, (y + h) * H + 6
        lw = 3
        if f.get("hidden"):
            d.rectangle([x0, y0, x1, y1], outline=c + (200,), width=2)
        else:
            k = (x1 - x0) * .28        # burchak qavslari (Hikvision uslubi) + ingichka to'liq ramka
            d.rectangle([x0, y0, x1, y1], outline=c + (150,), width=1)
            for (ax, ay, sx, sy) in ((x0, y0, 1, 1), (x1, y0, -1, 1), (x0, y1, 1, -1), (x1, y1, -1, -1)):
                d.line([(ax, ay), (ax + sx * k, ay)], fill=c + (255,), width=lw + 1)
                d.line([(ax, ay), (ax, ay + sy * k)], fill=c + (255,), width=lw + 1)
        placed.append((x0, y0, x1, y1))
        label, sub = f.get("label") or "", f.get("sub") or ""
        if not label: continue
        tw = max(d.textlength(label, font=fl), d.textlength(sub, font=fs) if sub else 0)
        ch, cw = 30 + (20 if sub else 0), tw + 20
        lx = min(max(4, (x0 + x1) / 2 - cw / 2), W - cw - 4)
        cands = [y0 - ch - 8, y1 + 8, y0 - 2 * ch - 14, y1 + ch + 14]
        ly = next((cy for cy in cands if 0 <= cy <= H - ch - 60 and not hit((lx, cy, lx + cw, cy + ch))), cands[0] if cands[0] > 0 else cands[1])
        placed.append((lx, ly, lx + cw, ly + ch))
        d.rounded_rectangle([lx, ly, lx + cw, ly + ch], radius=7, fill=c + (232,))
        mx = min(max((x0 + x1) / 2, lx + 10), lx + cw - 10)
        if ly + ch <= y0:   # ko'rsatkich uchi ramkaga qarab
            d.polygon([(mx - 7, ly + ch), (mx + 7, ly + ch), (mx, ly + ch + 7)], fill=c + (232,))
        elif ly >= y1:
            d.polygon([(mx - 7, ly), (mx + 7, ly), (mx, ly - 7)], fill=c + (232,))
        d.text((lx + 10, ly + 5), label, font=fl, fill=(255, 255, 255, 255))
        if sub: d.text((lx + 10, ly + 30), sub, font=fs, fill=(255, 255, 255, 235))
    # yo'nalish belgisi (yuqori o'ng)
    kir = direction == "kirish"
    col = (22, 163, 74) if kir else (59, 130, 246)
    txt = "KIRISH" if kir else "CHIQISH"
    ft = font("b", 20)
    tw = d.textlength(txt, font=ft)
    bx0, by0 = W - tw - 78, 16
    d.rounded_rectangle([bx0, by0, W - 18, by0 + 38], radius=19, fill=col + (230,))
    ax, ay = bx0 + 24, by0 + 19
    if kir: d.polygon([(ax - 10, ay - 2), (ax, ay - 12), (ax + 10, ay - 2), (ax + 4, ay - 2), (ax + 4, ay + 11), (ax - 4, ay + 11), (ax - 4, ay - 2)], fill=(255, 255, 255, 255))
    else: d.polygon([(ax - 10, ay + 2), (ax, ay + 12), (ax + 10, ay + 2), (ax + 4, ay + 2), (ax + 4, ay - 11), (ax - 4, ay - 11), (ax - 4, ay + 2)], fill=(255, 255, 255, 255))
    d.text((bx0 + 42, by0 + 8), txt, font=ft, fill=(255, 255, 255, 255))
    # pastki satr
    if footer:
        fb = font("b", 15)
        tw = d.textlength(footer, font=fb)
        d.rounded_rectangle([18, H - 80, 18 + tw + 22, H - 52], radius=6, fill=(15, 23, 42, 200))
        d.text((29, H - 75), footer, font=fb, fill=(255, 255, 255, 255))
    out = Image.alpha_composite(im.convert("RGBA"), ov).convert("RGB")
    return out

def to_jpeg(im: Image.Image, width: int | None = None, q: int = 82) -> bytes:
    if width and width < im.width:
        im = im.resize((width, round(im.height * width / im.width)), Image.LANCZOS)
    b = io.BytesIO(); im.save(b, "JPEG", quality=q, optimize=True, progressive=True)
    return b.getvalue()
