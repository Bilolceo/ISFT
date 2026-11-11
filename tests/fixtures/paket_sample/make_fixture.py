"""Namuna paket (kontrakt v2) generatori: content.json/content.js va kichik PNG rasmlar (PIL).

    .venv/bin/python tests/fixtures/paket_sample/make_fixture.py

Natija deterministik (rasm va JSON bir xil kirishda bir xil). Hujum satrlari (XSS) ataylab qo'shilgan — pleyer ularni zararsizlantirishi kerak.
"""
import json
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

FX = Path(__file__).resolve().parent
BRAND = (139, 0, 51)
GREEN = (46, 140, 86)


def font(size, bold=False):
    for p in (["/System/Library/Fonts/Supplemental/Arial Bold.ttf"] if bold else []) + ["/System/Library/Fonts/Supplemental/Arial.ttf",
              "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"]:
        try:
            return ImageFont.truetype(p, size)
        except OSError:
            pass
    return ImageFont.load_default(size=size)


def png(path, im):
    path.parent.mkdir(parents=True, exist_ok=True)
    im.convert("P", palette=Image.ADAPTIVE, colors=32).save(path, optimize=True)


def chart_supply_demand(w=880, h=520):
    im = Image.new("RGB", (w, h), "white"); d = ImageDraw.Draw(im)
    ox, oy = 90, h - 70
    d.line([(ox, 40), (ox, oy), (w - 40, oy)], fill=(40, 40, 40), width=3)
    d.text((ox + 14, 30), "Narx (P)", fill=(40, 40, 40), font=font(20))
    d.text((w - 170, oy + 20), "Miqdor (Q)", fill=(40, 40, 40), font=font(20))
    d.line([(ox + 40, 80), (w - 90, oy - 40)], fill=BRAND, width=6)          # D
    d.line([(ox + 40, oy - 40), (w - 90, 80)], fill=GREEN, width=6)          # S
    cx, cy = (ox + 40 + w - 90) // 2, (80 + oy - 40) // 2
    d.line([(ox, cy), (cx, cy)], fill=(150, 150, 150), width=2); d.line([(cx, cy), (cx, oy)], fill=(150, 150, 150), width=2)
    d.ellipse([cx - 10, cy - 10, cx + 10, cy + 10], fill=(30, 30, 30))
    d.text((w - 80, oy - 60), "D", fill=BRAND, font=font(30, True)); d.text((w - 80, 60), "S", fill=GREEN, font=font(30, True))
    d.text((cx + 16, cy - 36), "E (muvozanat)", fill=(30, 30, 30), font=font(20))
    d.text((ox - 40, cy - 12), "P*", fill=(30, 30, 30), font=font(20)); d.text((cx - 10, oy + 8), "Q*", fill=(30, 30, 30), font=font(20))
    return im


def chart_bars(w=880, h=420):
    im = Image.new("RGB", (w, h), (250, 250, 252)); d = ImageDraw.Draw(im)
    vals = [("Non", 0.2), ("Sut", 0.4), ("Kiyim", 0.9), ("Avtomobil", 1.6), ("Sayohat", 2.1)]
    bw = 110
    for i, (n, v) in enumerate(vals):
        x = 80 + i * 155; top = h - 70 - int(v * 140)
        d.rounded_rectangle([x, top, x + bw, h - 70], radius=10, fill=GREEN if v < 1 else BRAND)
        d.text((x + 10, h - 58), n, fill=(40, 40, 40), font=font(20)); d.text((x + 30, top - 30), str(v), fill=(40, 40, 40), font=font(22, True))
    d.line([(60, h - 70), (w - 30, h - 70)], fill=(60, 60, 60), width=2)
    d.text((60, 20), "Talabning narx bo'yicha elastikligi (|Ed|)", fill=(30, 30, 30), font=font(24, True))
    return im


def slide(n, title, lines, w=1280, h=720):
    im = Image.new("RGB", (w, h), "white"); d = ImageDraw.Draw(im)
    if n == 1:
        d.rectangle([0, 0, w, h], fill=BRAND)
        d.rectangle([0, h - 120, w, h], fill=(110, 0, 40))
        d.text((90, 250), title, fill="white", font=font(64, True))
        for i, t in enumerate(lines):
            d.text((90, 350 + i * 50), t, fill=(255, 220, 230), font=font(34))
        d.text((90, h - 82), "ISFT · Iqtisodiyot kafedrasi", fill="white", font=font(28))
        return im
    d.rectangle([0, 0, w, 120], fill=BRAND)
    d.text((60, 34), title, fill="white", font=font(50, True))
    for i, t in enumerate(lines):
        y = 190 + i * 90
        d.ellipse([70, y + 10, 94, y + 34], fill=GREEN)
        d.text((120, y), t, fill=(30, 30, 30), font=font(40))
    d.line([(60, h - 70), (w - 60, h - 70)], fill=BRAND, width=4)
    d.text((60, h - 56), "ISFT", fill=(110, 110, 110), font=font(26, True)); d.text((w - 100, h - 56), str(n), fill=(110, 110, 110), font=font(26))
    return im


SLIDES = [
    ("Talab va taklif nazariyasi", ["Mikroiqtisodiyot · L1", "3-kurs, Iqtisodiyot yo'nalishi"], "Mavzuga kirish."),
    ("Talab qonuni", ["Narx oshsa — talab miqdori kamayadi", "Daromad effekti", "O'rinbosarlik effekti", "Giffen tovarlari — istisno"], "D — talab egri chizig'i."),
    ("Taklif qonuni", ["Narx oshsa — taklif miqdori ortadi", "Texnologiya va xarajatlar", "Soliq va subsidiyalar"], ""),
    ("Bozor muvozanati", ["Talab = taklif", "Taqchillik va ortiqchalik", "Narx shifti va narx tagi"], "E nuqtasi — muvozanat."),
    ("Xulosa", ["Muvozanat narxi bozorni tozalaydi", "Elastiklik — narxga sezgirlik", "Davlat aralashuvi oqibatlari"], ""),
]

TEXT = (
    "<p>Bozor iqtisodiyotining markazida <strong>talab va taklif</strong> o'zaro ta'siri turadi. Ushbu ma'ruzada asosiy tushunchalar, "
    "qonunlar va bozor muvozanati ko'rib chiqiladi.</p>\n"
    "<h2>Talab tushunchasi</h2>\n<p>Talab — iste'molchilarning ma'lum narxda va ma'lum vaqtda sotib olishga <strong>tayyor va qodir</strong> bo'lgan "
    "tovar miqdori. Talab individual va bozor talabiga bo'linadi; bozor talabi barcha individual talablarning yig'indisidir.</p>\n"
    "<p>Talab qonuni: boshqa sharoitlar o'zgarmaganda narx oshsa, talab miqdori <em>kamayadi</em>. Bu bog'liqlik daromad va o'rinbosarlik "
    "effektlari bilan izohlanadi.</p>\n<ul><li>individual talab;</li><li>bozor talabi;</li><li>samarali talab.</li></ul>\n"
    "<script>window.__xss = 1</script>\n"
    "<figure><img src=\"assets/img/fig1.png\" alt=\"Talab va taklif egri chiziqlari\" width=\"880\" height=\"520\">"
    "<figcaption>1.1-rasm. Talab (D) va taklif (S) egri chiziqlari, E — muvozanat nuqtasi</figcaption></figure>\n"
    "<h2>Taklif tushunchasi</h2>\n<p onclick=\"window.__xss=2\">Taklif — ishlab chiqaruvchilar ma'lum narxda bozorga chiqarishga tayyor bo'lgan "
    "tovar miqdori. Taklifga texnologiya, resurslar narxi, soliqlar va kutilmalar ta'sir qiladi.</p>\n"
    "<blockquote>Narx oshsa, taklif miqdori ortadi (taklif qonuni).</blockquote>\n"
    "<img src=\"https://evil.example/x.png\" onerror=\"window.__xss=3\" alt=\"tashqi rasm\">\n"
    "<img src=\"http://evil\" alt=\"http rasm\">\n"
    "<img src=\"data:image/svg+xml;base64,PHN2ZyBvbmxvYWQ9YWxlcnQoMSk+\" alt=\"data rasm\">\n"
    "<img src=\"java\tscript:window.__xss=9\" alt=\"js rasm\">\n"
    "<h3>Taklif omillari</h3>\n<p>Quyidagi jadvalda turli tarmoqlar bo'yicha taklif omillarining ta'siri keltirilgan.</p>\n"
    "<table><thead><tr><th>Tarmoq</th><th>Texnologiya darajasi</th><th>Resurslar narxi (so'm)</th><th>Soliq yuki (%)</th><th>Subsidiya</th>"
    "<th>Kutilayotgan narx</th><th>Ishlab chiqaruvchilar soni</th><th>Taklif o'zgarishi</th></tr></thead>\n<tbody>"
    "<tr><td>Qishloq xo'jaligi</td><td>O'rta</td><td>1 250 000</td><td>12</td><td>Bor</td><td>Oshadi</td><td>4 820</td><td>+8%</td></tr>"
    "<tr><td>To'qimachilik</td><td>Yuqori</td><td>2 900 000</td><td>15</td><td>Yo'q</td><td>Barqaror</td><td>1 140</td><td>+3%</td></tr>"
    "<tr><td>Qurilish materiallari</td><td>O'rta</td><td>4 100 000</td><td>18</td><td>Yo'q</td><td>Kamayadi</td><td>620</td><td>−2%</td></tr>"
    "</tbody></table>\n"
    "<h2>Bozor muvozanati</h2>\n<p>Muvozanat narxi — talab va taklif miqdorlari teng bo'lgan narx. Narx muvozanatdan yuqori bo'lsa ortiqcha "
    "taklif, past bo'lsa taqchillik yuzaga keladi. Batafsil: <a href=\"https://isft.uz/kutubxona\">ISFT kutubxonasi</a>,\n"
    "<a href=\"javascript:window.__xss=4\">xavfli havola</a>.</p>\n"
    "<table><thead><tr><th>Narx (so'm)</th><th>Talab</th><th>Taklif</th></tr></thead>\n<tbody><tr><td>1 000</td><td>120</td><td>40</td></tr>"
    "<tr><td>2 000</td><td>80</td><td>80</td></tr><tr><td>3 000</td><td>50</td><td>130</td></tr></tbody></table>\n"
    "<iframe src=\"https://evil.example/\"></iframe><style>body{display:none}</style>\n"
    "<figure><img src=\"assets/img/fig2.png\" alt=\"Elastiklik diagrammasi\"><figcaption>1.2-rasm. Turli tovarlar talabining elastikligi</figcaption></figure>\n"
    "<h3>Elastiklik haqida qisqacha</h3>\n<p>Talabning narx bo'yicha elastikligi: E<sub>d</sub> = %ΔQ / %ΔP.</p>"
)

CONTENT = {
    "v": 1, "id": "isft-12-5-v4", "title": "Talab va taklif nazariyasi", "lang": "uz", "layout": "steps",
    "lesson": {"code": "L1", "kind": "maruza", "no": 1, "title": "Talab va taklif nazariyasi"},
    "course": {"subject": "Mikroiqtisodiyot", "direction": "Iqtisodiyot", "course": 3, "kafedra": "Iqtisodiyot kafedrasi", "teacher": "A. Karimov"},
    "topic": {"no": 5, "title": "Talab va taklif nazariyasi"},
    "brand": {"name": "ISFT", "full": "International School of Finance and Technology", "color": "#8B0033", "logo": "assets/logo.png"},
    "built": "2026-11-11T10:00:00+05:00",
    "blocks": [
        {"id": "b1", "type": "section", "title": "VIDEODARS"},
        {"id": "b2", "type": "video", "title": "Videodars", "provider": "youtube", "video_id": "dQw4w9WgXcQ",
         "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ", "start": 15},
        {"id": "b3", "type": "section", "title": "MA'RUZA MATNI"},
        {"id": "b4", "type": "plan", "title": "Reja", "heading": "1-MAVZU: TALAB VA TAKLIF NAZARIYASI",
         "items": ["Talab tushunchasi", "Taklif tushunchasi", "Bozor muvozanati", "Mustaqil ish uchun savollar"]},
        {"id": "b5", "type": "text", "title": "Ma'ruza matni", "html": TEXT},
        {"id": "b6", "type": "keypoints", "title": "Asosiy xulosalar", "items": [
            "Narx oshsa, talab miqdori kamayadi — taklif miqdori esa ortadi.",
            "Muvozanat narxida talab va taklif miqdorlari teng bo'ladi.",
            "Narx shifti taqchillikka, narx tagi ortiqcha taklifga olib keladi."]},
        {"id": "b7", "type": "refs", "title": "Foydalanilgan adabiyotlar ro'yxati", "items": [
            "Mankiw N. G. Principles of Economics. 9th ed. — Cengage, 2020.",
            "Shodmonov Sh., G'afurov U. Iqtisodiyot nazariyasi. — T.: Iqtisod-moliya, 2019.",
            "ISFT elektron kutubxonasi: https://isft.uz/kutubxona.",
            "Xavfli havola sinovi: javascript:alert(1)",
            {"text": "Khan Academy — Microeconomics", "url": "https://www.khanacademy.org/economics-finance-domain/microeconomics"}]},
        {"id": "b8", "type": "section", "title": "DARS TAQDIMOTI"},
        {"id": "b9", "type": "slides", "title": "Taqdimot", "display": "images", "file": "assets/taqdimot.pptx", "pdf": "assets/taqdimot.pdf",
         "slides": [{"title": t, "bullets": b, "notes": n, "image": f"assets/slides/s{i + 1}.png"} for i, (t, b, n) in enumerate(SLIDES)]},
        {"id": "b10", "type": "file", "title": "Uslubiy qo'llanma (PDF)", "href": "assets/qollanma.pdf", "size": 1234},
        {"id": "b99", "type": "hotspot", "title": "Noma'lum blok — e'tiborsiz qoldiriladi"},
        {"id": "b11", "type": "quiz", "title": "Test", "pass_pct": 60, "shuffle": True, "attempts": 3, "show_feedback": True, "questions": [
            {"id": "q101", "type": "mcq", "stem": "Talab qonuniga ko'ra narx oshsa, talab miqdori qanday o'zgaradi?",
             "options": ["Kamayadi", "Ortadi", "O'zgarmaydi", "Avval ortadi, keyin kamayadi"], "correct": [0],
             "explanation": "Boshqa sharoitlar o'zgarmaganda narx va talab miqdori teskari bog'langan."},
            {"id": "q102", "type": "mcq", "stem": "Quyidagilardan qaysilari talab omillari hisoblanadi? (bir nechtasini tanlang)",
             "options": ["Iste'molchi daromadi", "Ishlab chiqarish texnologiyasi", "O'rinbosar tovar narxi", "Soliq stavkasi ishlab chiqaruvchiga"],
             "correct": [0, 2], "explanation": "Texnologiya va ishlab chiqaruvchiga soliq — taklif omillari."},
            {"id": "q103", "type": "tf", "stem": "Muvozanat narxida talab miqdori taklif miqdoriga teng bo'ladi.", "options": ["To'g'ri", "Noto'g'ri"],
             "correct": [0], "explanation": ""},
            {"id": "q104", "type": "fill", "stem": "Normal tovar uchun daromad oshganda talab ... (bir so'z bilan yozing)",
             "answers": ["o'sadi", "ortadi", "oshadi"], "explanation": "Normal tovarlarda daromad va talab to'g'ri bog'langan."},
            {"id": "q105", "type": "mcq", "stem": "Narx shifti (maksimal narx) muvozanat narxidan past belgilansa nima yuzaga keladi?",
             "options": ["Taqchillik", "Ortiqcha taklif", "Muvozanat"], "correct": [0]}]},
        {"id": "b12", "type": "reflect", "title": "O'z-o'zini baholash", "question": "Darsni to'liq o'zlashtirdingizmi?", "options": [
            {"text": "Ha, albatta", "feedback": "Ajoyib! Bilimingizni mustahkamlash uchun keyingi mavzuga o'ting."},
            {"text": "Yo'q, to'liq o'zlashtirmadim", "feedback": "Hechqisi yo'q. Ma'ruza matni va taqdimotni qayta ko'rib chiqing, savollarni o'qituvchiga yozing."}]},
    ],
    "tracking": {"mode": "scorm12", "completion": "view_and_quiz", "mastery": 60, "activity_id": "https://isft.uz/xapi/paket/12/5"},
}

if __name__ == "__main__":
    png(FX / "assets/img/fig1.png", chart_supply_demand())
    png(FX / "assets/img/fig2.png", chart_bars())
    for i, (t, b, _) in enumerate(SLIDES):
        png(FX / f"assets/slides/s{i + 1}.png", slide(i + 1, t, b))
    (FX / "content.json").write_text(json.dumps(CONTENT, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    (FX / "content.js").write_text("window.PAKET = " + json.dumps(CONTENT, ensure_ascii=False) + ";\n", encoding="utf-8")
    print("ok")
