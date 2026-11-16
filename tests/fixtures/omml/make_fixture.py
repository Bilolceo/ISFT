#!/usr/bin/env python3
"""Word formulalari (OMML) bilan namunaviy ma'ruza: tests/fixtures/omml/formulalar.docx (test_omml.py ishlatadi).

  .venv/bin/python tests/fixtures/omml/make_fixture.py [chiqish.docx]

OMML qo'lda yoziladi (Word 365 saqlaydigan shaklda): kasr, indeks/daraja, ildiz, ∑ / ∫ / ∏ chegaralar bilan, 2×2 matritsa qavsda,
funksiya (sin, lim), urg'u (vektor), chiziq, tenglamalar tizimi (eqArr), oldingi indeks (sPre), groupChr — qator ichida va alohida (oMathPara).
"""
import sys
from pathlib import Path
from docx import Document
from docx.oxml import parse_xml

M = "http://schemas.openxmlformats.org/officeDocument/2006/math"
W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NS = f'xmlns:m="{M}" xmlns:w="{W}"'


def r(t, sty=None):
    pr = f'<m:rPr><m:sty m:val="{sty}"/></m:rPr>' if sty else ""
    return f'<m:r>{pr}<w:rPr><w:rFonts w:ascii="Cambria Math" w:hAnsi="Cambria Math"/></w:rPr><m:t xml:space="preserve">{t}</m:t></m:r>'

def e(*xs): return "<m:e>" + "".join(xs) + "</m:e>"
def frac(n, d, typ=None):
    pr = f'<m:fPr><m:type m:val="{typ}"/></m:fPr>' if typ else "<m:fPr><m:ctrlPr/></m:fPr>"
    return f"<m:f>{pr}<m:num>{n}</m:num><m:den>{d}</m:den></m:f>"
def ssub(b, s): return f"<m:sSub><m:sSubPr><m:ctrlPr/></m:sSubPr>{e(b)}<m:sub>{s}</m:sub></m:sSub>"
def ssup(b, s): return f"<m:sSup><m:sSupPr><m:ctrlPr/></m:sSupPr>{e(b)}<m:sup>{s}</m:sup></m:sSup>"
def ssubsup(b, lo, hi): return f"<m:sSubSup>{e(b)}<m:sub>{lo}</m:sub><m:sup>{hi}</m:sup></m:sSubSup>"
def rad(x, deg=None):
    pr = "<m:radPr><m:degHide m:val=\"1\"/></m:radPr><m:deg/>" if deg is None else f"<m:radPr/><m:deg>{deg}</m:deg>"
    return f"<m:rad>{pr}{e(x)}</m:rad>"
def nary(ch, lo, hi, body, loc=None, sub_hide=False, sup_hide=False):
    pr = (f'<m:chr m:val="{ch}"/>' if ch else "") + (f'<m:limLoc m:val="{loc}"/>' if loc else "") + \
         ('<m:subHide m:val="1"/>' if sub_hide else "") + ('<m:supHide m:val="1"/>' if sup_hide else "")
    return f"<m:nary><m:naryPr>{pr}<m:ctrlPr/></m:naryPr><m:sub>{lo}</m:sub><m:sup>{hi}</m:sup>{e(body)}</m:nary>"
def d(*items, beg=None, end=None, sep=None):
    pr = (f'<m:begChr m:val="{beg}"/>' if beg is not None else "") + (f'<m:endChr m:val="{end}"/>' if end is not None else "") + \
         (f'<m:sepChr m:val="{sep}"/>' if sep is not None else "")
    return f"<m:d><m:dPr>{pr}<m:ctrlPr/></m:dPr>" + "".join(e(x) for x in items) + "</m:d>"
def matrix(rows):
    return "<m:m><m:mPr><m:mcs><m:mc><m:mcPr><m:count m:val=\"2\"/><m:mcJc m:val=\"center\"/></m:mcPr></m:mc></m:mcs></m:mPr>" + \
           "".join("<m:mr>" + "".join(e(c) for c in row) + "</m:mr>" for row in rows) + "</m:m>"
def func(name, arg): return f"<m:func><m:funcPr><m:ctrlPr/></m:funcPr><m:fName>{name}</m:fName>{e(arg)}</m:func>"
def limlow(b, lim): return f"<m:limLow><m:limLowPr><m:ctrlPr/></m:limLowPr>{e(b)}<m:lim>{lim}</m:lim></m:limLow>"
def acc(x, ch="⃗"): return f'<m:acc><m:accPr><m:chr m:val="{ch}"/></m:accPr>{e(x)}</m:acc>'
def bar(x): return f'<m:bar><m:barPr><m:pos m:val="top"/></m:barPr>{e(x)}</m:bar>'
def eqarr(*rows): return "<m:eqArr><m:eqArrPr/>" + "".join(e(x) for x in rows) + "</m:eqArr>"
def spre(b, lo, hi): return f"<m:sPre><m:sPrePr/><m:sub>{lo}</m:sub><m:sup>{hi}</m:sup>{e(b)}</m:sPre>"
def groupchr(x): return f'<m:groupChr><m:groupChrPr><m:chr m:val="⏟"/><m:pos m:val="bot"/></m:groupChrPr>{e(x)}</m:groupChr>'

def omath(*xs): return f"<m:oMath {NS}>" + "".join(xs) + "</m:oMath>"
def omathpara(*xs): return f"<m:oMathPara {NS}><m:oMathParaPr><m:jc m:val=\"center\"/></m:oMathParaPr><m:oMath>" + "".join(xs) + "</m:oMath></m:oMathPara>"
def wr(t): return f'<w:r {NS}><w:t xml:space="preserve">{t}</w:t></w:r>'

FORMULAS = {
    # nom: (OMML qismlari, display)
    "kvadrat": ([r("x="), frac(r("−b±") + rad(ssup(r("b"), r("2")) + r("−4ac")), r("2a"))], True),
    "yigindi": ([nary("∑", r("i=1"), r("n"), ssub(r("x"), r("i"))), r("=") , r("S")], True),
    "integral": ([nary(None, r("0"), r("1"), ssup(r("x"), r("2")) + r("dx")), r("="), frac(r("1"), r("3"))], True),
    "matritsa": ([r("A="), d(matrix([[ssub(r("a"), r("11")), ssub(r("a"), r("12"))], [ssub(r("a"), r("21")), ssub(r("a"), r("22"))]]))], True),
    "limit": ([func(limlow(r("lim", "p"), r("n→∞")), d(r("1+") + frac(r("1"), r("n")))) , r("=e")], True),
    "kopaytma": ([nary("∏", r("k=1"), r("n"), r("k")), r("=n!")], True),
    "tizim": ([d(eqarr(r("2x+y=5"), r("x−y=1")), beg="{", end="")], True),
    "ildiz3": ([rad(r("27"), deg=r("3")), r("=3")], True),
}

def build(path: Path) -> None:
    doc = Document()
    doc.add_heading("7-MAVZU: ISHLAB CHIQARISH FUNKSIYASI VA FORMULALAR", 1)
    doc.add_paragraph("Reja:")
    for t in ("Ishlab chiqarish funksiyasi", "Chegaraviy mahsulot", "Matritsalar va tizimlar"):
        doc.add_paragraph(t, style="List Number")
    doc.add_heading("1. Ishlab chiqarish funksiyasi", 2)
    p = doc.add_paragraph("Kobb–Duglas funksiyasi ")
    p._p.append(parse_xml(omath(r("Q=A"), ssup(r("K"), r("α")), ssup(r("L"), r("β")))))
    p._p.append(parse_xml(wr(" ko'rinishida yoziladi, bu yerda ")))
    p._p.append(parse_xml(omath(r("α+β=1"))))
    p._p.append(parse_xml(wr(" bo'lsa, masshtab samarasi o'zgarmas bo'ladi. Indekslar: ")))
    p._p.append(parse_xml(omath(ssubsup(r("x"), r("i"), r("2")), r(","), spre(r("C"), r("n"), r("k")), r(","), acc(r("v")), r(","), bar(r("x")))))
    p._p.append(parse_xml(wr(".")))
    doc.add_paragraph("Kvadrat tenglama ildizlari quyidagi formula bilan topiladi:")
    for name in ("kvadrat", "yigindi"):
        doc.add_paragraph()._p.append(parse_xml(omathpara(*FORMULAS[name][0])))
    doc.add_heading("2. Chegaraviy mahsulot", 2)
    doc.add_paragraph("Chegaraviy mahsulot hosila orqali aniqlanadi. Integral misoli (aniq integral, chegaralari 0 va 1):")
    doc.add_paragraph()._p.append(parse_xml(omathpara(*FORMULAS["integral"][0])))
    doc.add_paragraph("Ajoyib limit va ko'paytma:")
    for name in ("limit", "kopaytma"):
        doc.add_paragraph()._p.append(parse_xml(omathpara(*FORMULAS[name][0])))
    p = doc.add_paragraph("Funksiya qiymati ")
    p._p.append(parse_xml(omath(func(r("sin", "p"), r("x")), r("+"), func(r("cos", "p"), r("x")))))
    p._p.append(parse_xml(wr(" va guruh belgisi ")))
    p._p.append(parse_xml(omath(groupchr(r("a+b")))))
    p._p.append(parse_xml(wr(" matn ichida.")))
    doc.add_heading("3. Matritsalar va tizimlar", 2)
    doc.add_paragraph("Ikki o'lchamli matritsa elementlari indekslar bilan belgilanadi:")
    doc.add_paragraph()._p.append(parse_xml(omathpara(*FORMULAS["matritsa"][0])))
    doc.add_paragraph("Chiziqli tenglamalar tizimi:")
    doc.add_paragraph()._p.append(parse_xml(omathpara(*FORMULAS["tizim"][0])))
    p = doc.add_paragraph()
    p._p.append(parse_xml(omath(rad(r("27"), deg=r("3")), r("=3"))))
    doc.add_paragraph("Formulalar jadvalda ham uchraydi:")
    t = doc.add_table(rows=2, cols=2)
    t.cell(0, 0).text, t.cell(0, 1).text = "Nomi", "Formula"
    t.cell(1, 0).text = "Kasr"
    t.cell(1, 1).paragraphs[0]._p.append(parse_xml(omath(frac(r("a"), r("b")))))
    doc.add_paragraph("Xulosa: formulalar Word'dagidek ko'rinadi.")
    path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(path))


if __name__ == "__main__":
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).with_name("formulalar.docx")
    build(out)
    print(out)
