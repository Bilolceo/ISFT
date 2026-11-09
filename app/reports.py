"""Word (.docx) hisobot generatori. Har bir hisobot so'rovchining ruxsatlari doirasida tuziladi."""
import datetime as dt
from pathlib import Path
from docx import Document
from docx.shared import Pt, RGBColor, Cm
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.oxml import OxmlElement
from . import services as S
from .rbac import Ctx, require, AccessDenied, REPORTS, ACADEMIC, STUDENTS, FINANCE, SCIENCE

OUT = Path(__file__).resolve().parent.parent / "reports"
ACCENT = RGBColor(0x9B, 0x1C, 0x1C)

REPORTS_META = {
    "brifing": ("Rahbariyat uchun haftalik brifing", None),
    "akademik": ("Akademik holat va xavf ostidagi talabalar", ACADEMIC),
    "moliya": ("Moliyaviy holat va kontrakt tushumi", FINANCE),
    "ilmiy": ("Ilmiy salohiyat hisoboti", SCIENCE),
}

def _shade(cell, hex_):
    tcPr = cell._tc.get_or_add_tcPr(); sh = OxmlElement("w:shd")
    sh.set(qn("w:val"), "clear"); sh.set(qn("w:color"), "auto"); sh.set(qn("w:fill"), hex_); tcPr.append(sh)

def _table(doc, head, rows):
    t = doc.add_table(rows=1, cols=len(head)); t.style = "Table Grid"
    for i, h in enumerate(head):
        c = t.rows[0].cells[i]; c.text = ""; r = c.paragraphs[0].add_run(str(h)); r.bold = True; r.font.size = Pt(9.5)
        r.font.color.rgb = RGBColor(255, 255, 255); _shade(c, "9B1C1C")
    for row in rows:
        cells = t.add_row().cells
        for i, v in enumerate(row):
            cells[i].text = ""; r = cells[i].paragraphs[0].add_run(str(v)); r.font.size = Pt(9.5)
    doc.add_paragraph()

def _h(doc, text):
    p = doc.add_paragraph(); r = p.add_run(text); r.bold = True; r.font.size = Pt(13); r.font.color.rgb = ACCENT

def _bullets(doc, items):
    for i in items:
        p = doc.add_paragraph(style="List Bullet"); p.add_run(i).font.size = Pt(10.5)

def build(con, ctx: Ctx, kind: str) -> Path:
    title, res = REPORTS_META[kind]
    require(con, ctx, REPORTS, f"hisobot: {title}")
    if res: require(con, ctx, res, f"hisobot ma'lumoti: {title}")
    doc = Document()
    st = doc.styles["Normal"]; st.font.name = "Times New Roman"; st.font.size = Pt(11)
    for s in doc.sections: s.left_margin = s.right_margin = Cm(2)
    p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = p.add_run("ISFT INSTITUTI"); r.bold = True; r.font.size = Pt(12); r.font.color.rgb = ACCENT
    p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = p.add_run(title.upper()); r.bold = True; r.font.size = Pt(15)
    p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = p.add_run(f"Sana: {S.TODAY.strftime('%d.%m.%Y')}   ·   Tayyorladi: ISFT Core   ·   So'rovchi: {ctx.role.title}   ·   Ko'lam: {ctx.scope_label(con)}")
    r.font.size = Pt(9); r.italic = True

    def safe(fn, *a):
        try: return fn(con, ctx, *a, quiet=True)
        except AccessDenied: return None

    if kind == "brifing":
        _h(doc, "1. Asosiy ko'rsatkichlar")
        _table(doc, ["Ko'rsatkich", "Qiymat", "Izoh"], [(k["label"], k["value"], k["sub"]) for k in S.kpis(con, ctx)])
        _h(doc, "2. E'tibor talab qiladigan masalalar")
        lv = {"high": "YUQORI", "mid": "O'RTA", "low": "PAST"}
        _table(doc, ["Daraja", "Yo'nalish", "Holat"], [(lv[a["level"]], a["area"], a["text"]) for a in S.alerts(con, ctx)])
        t = safe(S.tasks_list)
        if t:
            _h(doc, "3. Majlis topshiriqlari ijrosi")
            _table(doc, ["Mas'ul", "Topshiriq", "Muddat", "Holat"],
                   [(x["assignee"], x["text"], x["due"], ("MUDDATI O'TGAN" if x["overdue"] else x["status"])) for x in t["tasks"]])
    if kind == "akademik":
        a = S.academic_overview(con, ctx, quiet=True)
        _h(doc, "1. Umumiy holat")
        t = a["total"]
        _bullets(doc, [f"Faol talabalar: {t['n']} nafar", f"O'rtacha ball: {t['gpa']} (o'tgan semestr: {t['gpa_prev']})", f"O'rtacha davomat: {t['attendance']}%"])
        _h(doc, f"2. {a['breakdown_by'].capitalize()}lar kesimida")
        _table(doc, [a["breakdown_by"].capitalize(), "Talaba", "O'rt. ball", "Avvalgi", "O'zgarish", "Davomat"],
               [(r["name"], r["n"], r["gpa"], r["gpa_prev"], r["delta"], f"{r['attendance']}%" if r['attendance'] is not None else "—") for r in a["breakdown"]])
        if a["declining_groups"]:
            _h(doc, "3. O'zlashtirishi keskin pasaygan guruhlar")
            _bullets(doc, [S.decline_text(c) for c in a["declining_clusters"]])
            _table(doc, ["Guruh", "Fakultet", "Kurs", "Avvalgi ball", "Hozirgi ball", "O'zgarish", "Davomat"],
                   [(g["name"], g["faculty"], g["course"], g["gpa_prev"], g["gpa"], S._num(g["delta"]), f"{g['attendance']}%" if g['attendance'] is not None else "—") for g in a["declining_groups"]])
        r = safe(S.at_risk_students, 40)
        if r:
            _h(doc, "4. O'qishda xavf ostidagi talabalar")
            doc.add_paragraph(f"Jami: {r['count']} nafar ({r['of']} nafardan). Hisoblash: {S.RISK_DEF}. "
                              "Talabalar markazidagi holatlar soni (barcha qoidalar, jumladan kontrakt) — alohida ko'rsatkich.")
            if "students" in r:
                _table(doc, ["F.I.Sh.", "Guruh", "Ball", "Davomat", "Xavf", "Sabab"],
                       [(s["full_name"], s["grp"], s["gpa"], f"{s['attendance']}%" if s['attendance'] is not None else "—", s["risk"], s["reasons"]) for s in r["students"]])
            else:
                doc.add_paragraph(r.get("note", "")).runs[0].italic = True
                _table(doc, ["Guruh", "Xavf ostidagilar soni"], [(g["group"], g["count"]) for g in r["by_group"]])
        _h(doc, "Tavsiyalar")
        _bullets(doc, ["Pasaygan guruhlar bo'yicha kafedra mudirlari bilan alohida yig'ilish o'tkazish",
                       "Xavf ostidagi talabalarga kurator va qo'shimcha konsultatsiya biriktirish",
                       "2 haftadan so'ng ISFT Core orqali takroriy monitoring"])
    if kind == "moliya":
        f = S.finance_summary(con, ctx, quiet=True)
        _h(doc, "1. Byudjet ijrosi (yanvar–oktabr)")
        _table(doc, ["Modda", "Reja", "Haqiqiy", "Ijro %"], [(c["category"], S.mln(c["planned"]), S.mln(c["actual"]), f"{c['pct']}%") for c in f["categories"]] +
               [("JAMI", S.mln(f["total"]["planned"]), S.mln(f["total"]["actual"]), f"{f['total']['pct']}%")])
        if f["overruns"]:
            _h(doc, "2. Rejadan oshgan xarajatlar")
            _table(doc, ["Modda", "Oy", "Reja", "Haqiqiy", "Oshish"], [(o["category"], o["month"], S.mln(o["planned"]), S.mln(o["actual"]), f"+{o['over_pct']}%") for o in f["overruns"]])
        c = safe(S.contracts_summary)
        if c:
            _h(doc, "3. Kontrakt to'lovlari")
            _table(doc, ["Fakultet", "Hisoblangan", "To'langan", "Qarz", "Tushum %", "Qarzdorlar"],
                   [(r["name"], S.mln(r["total"]), S.mln(r["paid"]), S.mln(r["debt"]), f"{r['pct']}%", r["debtors"]) for r in c["by_faculty"]])
            _table(doc, ["Eng past tushumli guruh", "Fakultet", "Qarz", "Tushum %"], [(g["grp"], g["faculty"], S.mln(g["debt"]), f"{g['pct']}%") for g in c["worst_groups"]])
    if kind == "ilmiy":
        s = S.science_summary(con, ctx, quiet=True)
        _h(doc, "1. Umumiy ko'rsatkichlar")
        _bullets(doc, [f"Professor-o'qituvchilar: {s['teachers']} nafar", f"Ilmiy darajalilik: {s['degree_pct']}%",
                       "2026 yil nashrlari: " + ", ".join(f"{k['kind']} — {k['n']}" for k in s["kinds_2026"]),
                       f"2025 yildan beri nashri yo'q o'qituvchilar: {s['no_pubs_since_2025']} nafar"])
        _h(doc, "2. Kafedralar kesimida")
        _table(doc, ["Kafedra", "O'qituvchilar", "Ilmiy daraja %", "Scopus/WoS 2026"], [(d["name"], d["teachers"], f"{d['degree_pct']:.0f}%", d["scopus"]) for d in s["by_department"]])
        _h(doc, "3. Eng faol mualliflar")
        _table(doc, ["F.I.Sh.", "Daraja", "h-indeks", "Nashrlar", "Scopus/WoS"], [(t["full_name"], t["degree"], t["h_index"], t["pubs"], t["scopus"] or 0) for t in s["top_authors"]])
        if s["grants"]:
            _h(doc, "4. Grant loyihalari")
            _table(doc, ["Loyiha", "Rahbar", "Manba", "Summa", "Holat"], [(g["title"], g["leader"], g["funder"], S.mln(g["amount"]), g["status"]) for g in s["grants"]])

    doc.add_paragraph()
    p = doc.add_paragraph(); r = p.add_run("Ushbu hisobot ISFT Core tizimi tomonidan avtomatik tayyorlandi. Ma'lumotlar institut serveridan olingan; "
                                           "so'rov audit jurnalida qayd etilgan. (MVP: demo ma'lumotlar)"); r.italic = True; r.font.size = Pt(8.5)
    OUT.mkdir(exist_ok=True)
    path = OUT / f"ISFT_CORE_{kind}_{ctx.role.key}_{dt.datetime.now().strftime('%H%M%S')}.docx"
    doc.save(path)
    return path
