"""Sinov uchun sintetik media: macOS `say` nutqi (pauzalar, to'ldiruvchilar, dubl), "o'qituvchi" videosi,
4 sahifali PDF slaydlar. Hech narsa yuklab olinmaydi. Natija keshlanadi (bir xil papkada qayta yaratilmaydi).
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from pipeline.common import FFMPEG, find_font  # noqa: E402

VOICE = "Eddy (English (US))"
SCRATCH = Path("/private/tmp/claude-501/-Users-levi-Desktop-isft/c7457261-2842-4588-b99e-aae3cce064d9/scratchpad/montaj")
ARTICULATE = Path("/Users/levi/Desktop/Articulate yasash.mp4")

# (tur, matn yoki davomiylik). tur: say | sil | filler | retake_a (kesilishi kerak) | cue (kesilishi kerak)
SCRIPT = [
    ("sil", 0.6),
    ("say", "Hello everyone, and welcome to the lecture on databases."),
    ("sil", 0.4),
    ("say", "Today we will learn the basics of relational databases."),
    ("sil", 2.6),                                             # uzun pauza → kesiladi
    ("say", "First, let us talk about the relational model."),
    ("sil", 0.4),
    ("say", "In the relational model, data is stored in tables made of rows and columns."),
    ("sil", 0.7),
    ("filler", "Ummm... ehhh..."),                              # to'ldiruvchi → kesiladi
    ("sil", 0.7),
    ("say", "Every table has a primary key that identifies each row."),
    ("sil", 0.5),
    ("retake_a", "A foreign key links one table to"),           # chala dubl → kesiladi
    ("sil", 1.1),
    ("say", "A foreign key links one table to another table."),
    ("sil", 3.0),                                             # uzun pauza → kesiladi
    ("say", "Now let us move to SQL queries."),
    ("sil", 0.4),
    ("say", "The SELECT statement reads data, and the WHERE clause filters rows."),
    ("sil", 0.4),
    ("cue_prev", "The JOIN operation is the slowest part of"),  # signaldan oldingi gap → kesiladi
    ("sil", 0.8),
    ("cue", "Stop. Again."),                                    # signal → kesiladi
    ("sil", 0.8),
    ("say", "The JOIN operation combines rows from two tables using a common key."),
    ("sil", 2.2),                                             # uzun pauza → kesiladi
    ("say", "Finally, we will discuss indexes and performance."),
    ("sil", 0.4),
    ("say", "An index makes searching much faster, like the index at the end of a book."),
    ("sil", 0.4),
    ("say", "But every index also slows down inserts and updates."),
    ("sil", 0.6),
    ("retake_a", "Remember to practice these queries at home."),  # to'liq dubl → birinchisi kesiladi
    ("sil", 1.2),
    ("say", "Remember to practice these queries at home."),
    ("sil", 0.5),
    ("say", "Thank you for your attention, see you in the next lecture."),
    ("sil", 1.5),
]

SLIDES = [
    ("Introduction to databases", ["Lecture on databases", "Basics of relational databases", "Welcome"]),
    ("Relational model", ["Data is stored in tables", "Tables are made of rows and columns",
                          "Primary key identifies each row", "Foreign key links one table to another table"]),
    ("SQL queries", ["SELECT statement reads data", "WHERE clause filters rows",
                     "JOIN operation combines rows from two tables using a common key"]),
    ("Indexes and performance", ["An index makes searching much faster", "Like the index at the end of a book",
                                 "Every index slows down inserts and updates", "Practice these queries at home"]),
]

PLAN = ["1. Relational model", "2. SQL queries", "3. Indexes and performance"]


def sh(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"{cmd[:3]}: {r.stderr[-800:]}")
    return r


def make_audio(d: Path) -> tuple[Path, list[dict]]:
    """Bo'laklarni yaratib, birlashtiradi. Qaytaradi: (wav, vaqt jadvali)."""
    parts = d / "parts"
    parts.mkdir(parents=True, exist_ok=True)
    timeline, files, t = [], [], 0.0
    for i, (kind, val) in enumerate(SCRIPT):
        f = parts / f"{i:02d}.wav"
        if kind == "sil":
            sh([FFMPEG, "-y", "-loglevel", "error", "-f", "lavfi", "-i", "anullsrc=r=48000:cl=mono",
                "-t", f"{val}", "-c:a", "pcm_s16le", str(f)])
        else:
            aiff = parts / f"{i:02d}.aiff"
            rate = "140" if kind == "filler" else "175"
            sh(["say", "-v", VOICE, "-r", rate, "-o", str(aiff), val])
            sh([FFMPEG, "-y", "-loglevel", "error", "-i", str(aiff), "-ar", "48000", "-ac", "1",
                "-af", "silenceremove=start_periods=1:start_threshold=-50dB,areverse,"
                       "silenceremove=start_periods=1:start_threshold=-50dB,areverse",
                "-c:a", "pcm_s16le", str(f)])
        dur = _wav_dur(f)
        timeline.append({"kind": kind, "text": val if kind != "sil" else "", "start": round(t, 3),
                         "end": round(t + dur, 3)})
        files.append(f)
        t += dur
    lst = d / "parts.txt"
    lst.write_text("".join(f"file '{f}'\n" for f in files))
    speech = d / "speech_clean.wav"
    sh([FFMPEG, "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(lst), "-c:a", "pcm_s16le",
        str(speech)])
    # xona shovqini + biroz pastroq ovoz (loudnorm sinovi uchun)
    noisy = d / "speech.wav"
    sh([FFMPEG, "-y", "-loglevel", "error", "-i", str(speech), "-f", "lavfi", "-i",
        f"anoisesrc=colour=pink:amplitude=0.004:r=48000:d={t:.3f}",
        "-filter_complex", "[0:a]volume=0.5[s];[s][1:a]amix=inputs=2:duration=first:normalize=0[a]",
        "-map", "[a]", "-ac", "1", "-c:a", "pcm_s16le", str(noisy)])
    return noisy, timeline


def _wav_dur(f: Path) -> float:
    import wave
    with wave.open(str(f)) as w:
        return w.getnframes() / w.getframerate()


def make_teacher_png(d: Path) -> tuple[Path, Path]:
    """Studiya foni va "o'qituvchi" siluetini chizadi."""
    from PIL import Image, ImageDraw, ImageFilter, ImageFont
    W, H = 1920, 1080
    bg = Image.new("RGB", (W, H))
    px = bg.load()
    for y in range(H):
        for x in range(0, W, 4):
            k = x / W
            c = (int(70 + 40 * k), int(84 + 30 * k), int(104 + 20 * (1 - y / H)))
            for dx in range(4):
                px[x + dx, y] = c
    dd = ImageDraw.Draw(bg)
    dd.rectangle((1300, 180, 1760, 520), fill=(52, 64, 82))   # devordagi doska
    dd.rectangle((1316, 196, 1744, 504), fill=(38, 74, 60))
    dd.text((1340, 220), "STUDIYA · TEST", font=ImageFont.truetype(find_font(True), 40), fill=(220, 230, 220))
    bg = bg.filter(ImageFilter.GaussianBlur(3))
    bg.save(d / "studio_bg.png")
    fig = Image.new("RGBA", (700, 900), (0, 0, 0, 0))
    fd = ImageDraw.Draw(fig)
    fd.rounded_rectangle((110, 430, 590, 900), 180, fill=(110, 30, 50, 255))   # tana (bordo kostyum)
    fd.polygon([(300, 430), (400, 430), (350, 560)], fill=(240, 240, 240, 255))  # ko'ylak
    fd.ellipse((215, 120, 485, 420), fill=(226, 186, 160, 255))                  # bosh
    fd.chord((205, 95, 495, 300), 180, 360, fill=(50, 36, 30, 255))             # soch
    fd.ellipse((290, 245, 315, 270), fill=(40, 30, 30, 255))
    fd.ellipse((385, 245, 410, 270), fill=(40, 30, 30, 255))
    fig.save(d / "figure.png")
    return d / "studio_bg.png", d / "figure.png"


def make_teacher_video(d: Path, audio: Path, dur: float, out: Path, fps: int = 25):
    bg, fig = make_teacher_png(d)
    # siluet sekin chayqaladi (harakatlanuvchi element), 25 fps — 30 ga normallashtirish sinovi
    sh([FFMPEG, "-y", "-loglevel", "error", "-framerate", "1", "-loop", "1", "-t", f"{dur:.3f}", "-i", str(bg),
        "-framerate", "1", "-loop", "1", "-t", f"{dur:.3f}", "-i", str(fig), "-i", str(audio),
        "-filter_complex",
        f"[0:v]fps={fps}[b];[1:v]fps={fps}[f];[b][f]overlay=x='610+40*sin(t*0.7)':y='190+6*sin(t*1.9)',"
        f"drawtext=fontfile='{find_font(False)}':text='%{{pts\\:hms}}':x=40:y=40:fontsize=36:fontcolor=white,"
        f"format=yuv420p[v]",
        "-map", "[v]", "-map", "2:a", "-c:v", "libx264", "-preset", "ultrafast", "-crf", "26", "-r", str(fps),
        "-c:a", "aac", "-b:a", "128k", "-shortest", str(out)])
    return out


def make_slides_pdf(out: Path):
    from PIL import Image, ImageDraw, ImageFont
    pages = []
    for i, (title, bullets) in enumerate(SLIDES):
        im = Image.new("RGB", (1600, 900), "white")
        d = ImageDraw.Draw(im)
        d.rectangle((0, 0, 1600, 14), fill=(0x87, 0, 0x37))
        d.text((90, 90), title, font=ImageFont.truetype(find_font(True), 72), fill=(30, 20, 26))
        y = 260
        for b in bullets:
            d.ellipse((96, y + 22, 112, y + 38), fill=(0x87, 0, 0x37))
            d.text((140, y), b, font=ImageFont.truetype(find_font(False), 46), fill=(60, 50, 56))
            y += 100
        d.text((1480, 820), f"{i + 1}/4", font=ImageFont.truetype(find_font(False), 30), fill=(150, 140, 146))
        pages.append(im)
    # Pillow PDF'i matn qatlamini saqlamaydi — matnli PDF uchun minimal PDF yozuvchidan foydalanamiz
    _write_text_pdf(out, pages)
    return out


def _write_text_pdf(out: Path, pages):
    """Har sahifa: rasm (fon) + ko'rinmas matn qatlami (pdfium o'qiy oladi). Faqat standart kutubxona."""
    import io
    import zlib
    objs = []

    def add(b: bytes) -> int:
        objs.append(b)
        return len(objs)

    font_id = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    page_ids = []
    pages_id_placeholder = len(objs) + 1
    add(b"")  # Pages — keyin to'ldiriladi
    for (title, bullets), im in zip(SLIDES, pages):
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=88)
        jpg = buf.getvalue()
        img_id = add(b"<< /Type /XObject /Subtype /Image /Width %d /Height %d /ColorSpace /DeviceRGB "
                     b"/BitsPerComponent 8 /Filter /DCTDecode /Length %d >>\nstream\n" % (im.width, im.height, len(jpg))
                     + jpg + b"\nendstream")
        lines = [title] + bullets
        txt = "BT /F1 12 Tf 3 Tr 20 880 Td " + " ".join(
            f"({ln.replace('(', '').replace(')', '')}) Tj 0 -40 Td" for ln in lines) + " ET"
        content = f"q 1600 0 0 900 0 0 cm /Im0 Do Q {txt}".encode()
        comp = zlib.compress(content)
        c_id = add(b"<< /Length %d /Filter /FlateDecode >>\nstream\n" % len(comp) + comp + b"\nendstream")
        p_id = add(b"<< /Type /Page /Parent %d 0 R /MediaBox [0 0 1600 900] /Contents %d 0 R "
                   b"/Resources << /Font << /F1 %d 0 R >> /XObject << /Im0 %d 0 R >> >> >>"
                   % (pages_id_placeholder, c_id, font_id, img_id))
        page_ids.append(p_id)
    objs[pages_id_placeholder - 1] = b"<< /Type /Pages /Kids [%s] /Count %d >>" % (
        b" ".join(b"%d 0 R" % p for p in page_ids), len(page_ids))
    cat = add(b"<< /Type /Catalog /Pages %d 0 R >>" % pages_id_placeholder)
    out_b = bytearray(b"%PDF-1.4\n")
    offs = []
    for i, o in enumerate(objs, 1):
        offs.append(len(out_b))
        out_b += b"%d 0 obj\n" % i + o + b"\nendobj\n"
    xref = len(out_b)
    out_b += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1)
    for o in offs:
        out_b += b"%010d 00000 n \n" % o
    out_b += b"trailer << /Size %d /Root %d 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objs) + 1, cat, xref)
    out.write_bytes(bytes(out_b))


def make_all(d: Path = SCRATCH / "fixtures", force: bool = False) -> dict:
    d.mkdir(parents=True, exist_ok=True)
    meta_f = d / "meta.json"
    if meta_f.exists() and not force:
        return json.loads(meta_f.read_text())
    audio, timeline = make_audio(d)
    dur = timeline[-1]["end"]
    teacher = make_teacher_video(d, audio, dur, d / "teacher_raw.mp4")
    pdf = make_slides_pdf(d / "slides.pdf")
    meta = {"audio": str(audio), "teacher": str(teacher), "slides": str(pdf), "timeline": timeline,
            "duration": dur, "plan": PLAN}
    # ekran shabloni: Articulate yozuvidan qisqa bo'lak (faqat o'qiladi) + sintetik nutq
    if ARTICULATE.exists():
        screen = d / "screen_raw.mp4"
        sh([FFMPEG, "-y", "-loglevel", "error", "-ss", "120", "-t", f"{dur:.3f}", "-i", str(ARTICULATE), "-i",
            str(audio), "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy", "-c:a", "aac", "-b:a", "128k",
            "-shortest", str(screen)])
        meta["screen"] = str(screen)
        # haqiqiy o'zbek nutqi bilan qisqa bo'lak (ishlash tezligi va ASR sifatini o'lchash uchun)
        real = d / "real_uz_120s.mp4"
        sh([FFMPEG, "-y", "-loglevel", "error", "-ss", "60", "-t", "120", "-i", str(ARTICULATE), "-c", "copy",
            str(real)])
        meta["real"] = str(real)
    meta_f.write_text(json.dumps(meta, indent=2))
    return meta


if __name__ == "__main__":
    m = make_all(force="--force" in sys.argv)
    print(json.dumps({k: v for k, v in m.items() if k != "timeline"}, indent=2))
    for t in m["timeline"]:
        if t["kind"] != "sil":
            print(f"{t['start']:6.2f}-{t['end']:6.2f} {t['kind']:9s} {t['text']}")
