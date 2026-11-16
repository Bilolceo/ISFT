#!/usr/bin/env python3
"""Namuna test fayli (app/test_import.py uchun): o'qituvchining Word'dagi testi — Articulate Rise o'quv videosidagi ko'rinishda.

  test.docx — 5 ta test savoli (✅, «(to'g'ri)», faqat qalin bilan belgilangan, belgisiz, Word avtomatik raqamli + ✔️),
              «Glossariy» (4 atama: « - », « — », «: » ajratgichlari) va «Savollar» (3 ta ochiq savol).
  test.txt  — o'sha mazmun oddiy matn ko'rinishida (qalin belgisi o'rniga ✓).
  test_javobsiz.docx — «To'g'ri javobni tanlang» oynasi uchun: 2 ta ✅ belgili savol (biri ko'p javobli) va 3 ta javobsiz savol (3, 4 va 5 variantli;
              uzun matnli ham bor); glossariy yo'q.

Ishga tushirish:  .venv/bin/python tests/fixtures/test_import/make_fixtures.py [qo'shimcha/chiqish/yo'li.docx ...]
(argument berilsa — test.docx o'sha yo'llarga ham yoziladi, masalan Input/namuna_test.docx)
"""
import sys
from pathlib import Path
from docx import Document
from docx.shared import Pt

HERE = Path(__file__).resolve().parent

TITLE = "O‘zbek tilining sohada qo‘llanilishi — 1-mavzu bo‘yicha test"
QUESTIONS = [
    ("“O‘zbek tilining sohada qo‘llanilishi” fanining maqsadi nima?",
     ["Tilning faqat shevalarini o‘rganish", "O‘zbek tilining turli sohalarda qo‘llanilishini o‘rgatish ✅",
      "Faqat badiiy matnlarni yozishni o‘rgatish", "Ingliz tilini o‘rganish"]),
    ("O‘zbek adabiy tilida nechta funksional uslub ajratiladi?", ["3", "4", "5 (to‘g‘ri)"]),
    ("Rasmiy hujjatlar qaysi uslubda yoziladi?",
     ["Badiiy uslub", "Rasmiy-idoraviy uslub", "So‘zlashuv uslubi", "Publitsistik uslub"]),          # faqat qalin bilan belgilangan (B)
    ("Ilmiy uslubning asosiy belgisi qaysi?",
     ["Obrazlilik", "Aniqlik va mantiqiylik", "Hissiyotga boylik", "Shevaga xoslik"]),              # belgisiz — UI tanlatadi
    ("Ish yuritish hujjatlariga qaysilar kiradi?",
     ["Ariza ✔️", "She’r", "Tushuntirish xati ✔️", "Hikoya"]),                                      # ko'p javobli
]
BOLD_CORRECT = {2: 1}          # savol indeksi → qalin variant
GLOSSARY = [("Uslub", " - ", "tilning muayyan nutq sohasida qo‘llanadigan ifoda vositalari tizimi"),
            ("Termin", " — ", "fan yoki kasb sohasidagi tushunchaning aniq nomi"),
            ("Ariza", ": ", "biror iltimos bilan rasmiy murojaat qilish hujjati"),
            ("Dalolatnoma", " — ", "biror voqea yoki holatni tasdiqlovchi hujjat")]
OPEN = ["Rasmiy uslubning o‘ziga xos xususiyatlari nimalardan iborat?",
        "Ilmiy matnda terminlarning o‘rni qanday?",
        "Ish yuritishda qanday hujjat turlaridan foydalaniladi?"]


def make_docx(path: Path) -> None:
    d = Document()
    d.styles["Normal"].font.name = "Times New Roman"; d.styles["Normal"].font.size = Pt(12)
    d.add_heading(TITLE, level=1)
    d.add_paragraph("Test")
    for i, (stem, opts) in enumerate(QUESTIONS):
        if i == 4:                                       # Word avtomatik raqamlash (List Number) — «5.» matnda yo'q
            d.add_paragraph(stem, style="List Number")
        else:
            d.add_paragraph(f"{i + 1}. {stem}")
        for j, o in enumerate(opts):
            p = d.add_paragraph()
            r = p.add_run(f"{'ABCD'[j]}) {o}")
            if BOLD_CORRECT.get(i) == j: r.bold = True
        d.add_paragraph("")
    d.add_heading("Glossariy", level=2)
    for t, sep, df in GLOSSARY:
        d.add_paragraph(f"{t}{sep}{df}")
    d.add_heading("Savollar", level=2)
    for k, q in enumerate(OPEN, 1):
        d.add_paragraph(f"{k}. {q}")
    path.parent.mkdir(parents=True, exist_ok=True)
    d.save(str(path))


UNANSWERED = [
    ("Kompyuterning asosiy qurilmalari qaysilar?", ["Protsessor ✅", "Sichqoncha", "Operativ xotira ✅", "Kolonka"]),     # ko'p javobli (2 ta ✅)
    ("Hujjatning rasmiy rekvizitlaridan qaysi biri sana hisoblanadi?", ["Imzo", "Hujjat sanasi ✅", "Muhr"]),
    ("Ilmiy uslubning asosiy belgisi qaysi? (javobi belgilanmagan)", ["Obrazlilik", "Aniqlik va mantiqiylik", "Hissiyotga boylik"]),
    ("Ish yuritishda quyidagi hujjat turlaridan qaysilari tashkiliy-farmoyish hujjatlariga kiradi? Bir nechta variantni tanlash mumkin.",
     ["Buyruq", "Farmoyish", "Ariza", "Dalolatnoma"]),
    ("O‘zbek tilining davlat tili maqomi qaysi hujjatda mustahkamlangan, va u qachon qabul qilingan?",
     ["Konstitutsiya", "Fuqarolik kodeksi", "Mehnat kodeksi", "Soliq kodeksi", "Jinoyat kodeksi"]),
]


def make_unanswered_docx(path: Path) -> None:
    """2 ta ✅ belgili + 3 ta javobsiz savol (to'g'ri javobni tanlash oynasi sinovi uchun)."""
    d = Document()
    d.styles["Normal"].font.name = "Times New Roman"; d.styles["Normal"].font.size = Pt(12)
    d.add_heading("Ish yuritish — 2-mavzu bo‘yicha test", level=1)
    d.add_paragraph("Test")
    for i, (stem, opts) in enumerate(UNANSWERED):
        d.add_paragraph(f"{i + 1}. {stem}")
        for j, o in enumerate(opts): d.add_paragraph(f"{'ABCDE'[j]}) {o}")
        d.add_paragraph("")
    path.parent.mkdir(parents=True, exist_ok=True)
    d.save(str(path))


def make_txt(path: Path) -> None:
    lines = [TITLE, ""]
    for i, (stem, opts) in enumerate(QUESTIONS):
        lines.append(f"{i + 1}. {stem}")
        for j, o in enumerate(opts):
            lines.append(f"{'ABCD'[j]}) {o}" + (" ✓" if BOLD_CORRECT.get(i) == j else ""))
        lines.append("")
    lines.append("Glossariy")
    lines += [f"{t}{sep}{df}" for t, sep, df in GLOSSARY]
    lines += ["", "Savollar"] + [f"{k}. {q}" for k, q in enumerate(OPEN, 1)]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    make_docx(HERE / "test.docx")
    make_txt(HERE / "test.txt")
    make_unanswered_docx(HERE / "test_javobsiz.docx")
    for extra in sys.argv[1:]:
        make_docx(Path(extra))
    print("tayyor:", HERE / "test.docx", HERE / "test.txt", HERE / "test_javobsiz.docx", *sys.argv[1:])
