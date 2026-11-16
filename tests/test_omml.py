"""Word formulalari (OMML) → MathML Core: app/omml.py konvertori, matn belgisi «⟦m:…|…⟧», paket.sanitize / html_unsafe (MathML oq ro'yxati),
kurs muharriri tozalashi (clean_block), docx_lecture → structure_text (tests/fixtures/omml/formulalar.docx) va — PW va CHROME berilganda —
paket va kurs pleyerlarida brauzer sinovi (tools/omml_player_check.js: chizilishi, sanitizer, 1280px / 390px skrinshotlar).

Ishga tushirish:  .venv/bin/python tests/test_omml.py      (server kerak emas; run_all.py --only omml ham bo'ladi)
   PW=/path/node_modules/playwright-core CHROME=/path/to/chrome OUT=/tmp/omml .venv/bin/python tests/test_omml.py
"""
import json, os, re, shutil, subprocess, sys, tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from lxml import etree
from app import omml as OM
from app import paket as PK

FX = ROOT / "tests" / "fixtures" / "omml"
fails = []
def ok(cond, msg):
    print(("  ✓ " if cond else "  ✗ ") + msg)
    if not cond: fails.append(msg)

NS = f'xmlns:m="{OM.M_NS}" xmlns:w="{OM.W_NS}"'
def X(body: str, para=False):
    tag = "oMathPara" if para else "oMath"
    inner = f"<m:oMath>{body}</m:oMath>" if para else body
    return etree.fromstring(f"<m:{tag} {NS}>{inner}</m:{tag}>")
def r(t, sty=None): return (f'<m:r><m:rPr><m:sty m:val="{sty}"/></m:rPr>' if sty else "<m:r>") + f"<m:t>{t}</m:t></m:r>"
def e(x): return f"<m:e>{x}</m:e>"
def conv(body, para=False): return OM.convert(X(body, para))

# =============================================================================================
print("== 1. Konvertor: har bir tuzilma")
ml, tx = conv(r("x+12.5=y"))
ok(ml == '<math alttext="x+12.5=y"><mrow><mi>x</mi><mo>+</mo><mn>12.5</mn><mo>=</mo><mi>y</mi></mrow></math>', f"m:r — mi / mn / mo, alttext ({ml})")
ml, tx = conv(r("sin", "p"))
ok("<mi>sin</mi>" in ml, "m:sty=p — so'z bitta <mi> (tik)")
ml, _ = conv(r("2sinx"))
ok("<mn>2</mn><mi>sin</mi><mi>x</mi>" in ml, f"Ma'lum funksiya nomi (sin) — bitta <mi>, qolgan harflar alohida ({ml})")
ml, _ = conv('<m:r><m:rPr><m:nor/></m:rPr><m:t>bu yerda</m:t></m:r>')
ok("<mtext>bu yerda</mtext>" in ml, "m:nor — <mtext>")
ml, _ = conv('<m:r><m:rPr><m:scr m:val="double-struck"/><m:sty m:val="p"/></m:rPr><m:t>R</m:t></m:r>')
ok('<mi mathvariant="double-struck">R</mi>' in ml, "m:scr=double-struck — mathvariant")
ml, tx = conv(f"<m:f><m:num>{r('a+b')}</m:num><m:den>{r('2')}</m:den></m:f>")
ok("<mfrac><mrow><mi>a</mi><mo>+</mo><mi>b</mi></mrow><mn>2</mn></mfrac>" in ml and tx == "(a+b)/2", f"m:f — <mfrac>, matn «{tx}»")
ml, tx = conv(f'<m:f><m:fPr><m:type m:val="lin"/></m:fPr><m:num>{r("a")}</m:num><m:den>{r("b")}</m:den></m:f>')
ok("<mfrac" not in ml and "<mo>/</mo>" in ml and tx == "a/b", "m:f type=lin — «a/b»")
ml, _ = conv(f'<m:f><m:fPr><m:type m:val="skw"/></m:fPr><m:num>{r("a")}</m:num><m:den>{r("b")}</m:den></m:f>')
ok("<mo>/</mo>" in ml, "m:f type=skw — «a/b»")
ml, _ = conv(f'<m:f><m:fPr><m:type m:val="noBar"/></m:fPr><m:num>{r("n")}</m:num><m:den>{r("k")}</m:den></m:f>')
ok('<mfrac linethickness="0">' in ml, "m:f type=noBar — linethickness=0 (binomial)")
ml, tx = conv(f"<m:sSub>{e(r('a'))}<m:sub>{r('ij')}</m:sub></m:sSub>")
ok("<msub><mi>a</mi><mrow><mi>i</mi><mi>j</mi></mrow></msub>" in ml and tx == "a_{ij}", f"m:sSub — <msub>, «{tx}»")
ml, tx = conv(f"<m:sSup>{e(r('x'))}<m:sup>{r('2')}</m:sup></m:sSup>")
ok("<msup><mi>x</mi><mn>2</mn></msup>" in ml and tx == "x^2", "m:sSup — <msup>, «x^2»")
ml, tx = conv(f"<m:sSubSup>{e(r('x'))}<m:sub>{r('i')}</m:sub><m:sup>{r('n+1')}</m:sup></m:sSubSup>")
ok(ml.count("<msubsup>") == 1 and tx == "x_i^{n+1}", f"m:sSubSup — <msubsup>, «{tx}»")
ml, _ = conv(f"<m:sPre><m:sub>{r('n')}</m:sub><m:sup>{r('k')}</m:sup>{e(r('C'))}</m:sPre>")
ok("<mmultiscripts><mi>C</mi><mprescripts></mprescripts><mi>n</mi><mi>k</mi></mmultiscripts>" in ml, "m:sPre — <mmultiscripts> + <mprescripts>")
ml, tx = conv(f'<m:rad><m:radPr><m:degHide m:val="1"/></m:radPr><m:deg/>{e(r("x"))}</m:rad>')
ok("<msqrt><mi>x</mi></msqrt>" in ml and tx == "√(x)", "m:rad (darajasiz) — <msqrt>")
ml, tx = conv(f'<m:rad><m:radPr/><m:deg>{r("3")}</m:deg>{e(r("8"))}</m:rad>')
ok("<mroot><mn>8</mn><mn>3</mn></mroot>" in ml and tx == "root(3, 8)", "m:rad (daraja bilan) — <mroot> (asos, daraja)")
ml, tx = conv(f'<m:nary><m:naryPr><m:chr m:val="∑"/><m:limLoc m:val="undOvr"/></m:naryPr><m:sub>{r("i=1")}</m:sub><m:sup>{r("n")}</m:sup>{e(r("i"))}</m:nary>')
ok("<munderover><mo>∑</mo>" in ml and tx == "∑_{i=1}^n i", f"m:nary ∑ — <munderover>, «{tx}»")
ml, tx = conv(f'<m:nary><m:naryPr/><m:sub>{r("0")}</m:sub><m:sup>{r("1")}</m:sup>{e(r("f"))}</m:nary>')
ok("<msubsup><mo>∫</mo><mn>0</mn><mn>1</mn></msubsup>" in ml, "m:nary (chr yo'q) — ∫, chegaralar yonida (<msubsup>)")
ml, _ = conv(f'<m:nary><m:naryPr><m:chr m:val="∏"/><m:subHide m:val="1"/><m:supHide m:val="1"/></m:naryPr><m:sub/><m:sup/>{e(r("k"))}</m:nary>')
ok("<mo>∏</mo><mi>k</mi>" in ml and "<munder" not in ml and "<mover" not in ml, "m:nary subHide/supHide — chegarasiz")
ml, _ = conv(f'<m:nary><m:naryPr><m:chr m:val="∑"/><m:supHide m:val="1"/></m:naryPr><m:sub>{r("k")}</m:sub><m:sup/>{e(r("a"))}</m:nary>')
ok("<munder><mo>∑</mo><mi>k</mi></munder>" in ml, "m:nary faqat pastki chegara — <munder>")
ml, tx = conv(f"<m:d>{e(r('a'))}{e(r('b'))}</m:d>")
ok('<mo fence="true" form="prefix" stretchy="true">(</mo>' in ml and '<mo separator="true">|</mo>' in ml and tx.startswith("(") and tx.endswith(")"),
   "m:d — standart qavslar va ajratuvchi «|»")
ml, tx = conv(f'<m:d><m:dPr><m:begChr m:val="["/><m:endChr m:val=""/><m:sepChr m:val=","/></m:dPr>{e(r("0"))}{e(r("1"))}</m:d>')
ok(">[<" in ml and 'form="postfix"' not in ml and '<mo separator="true">,</mo>' in ml and tx == "[0, 1", f"m:d begChr/endChr(bo'sh)/sepChr «{tx}»")
mat = "<m:m>" + "".join("<m:mr>" + "".join(e(r(c)) for c in row) + "</m:mr>" for row in (("a", "b"), ("c", "d"))) + "</m:m>"
ml, tx = conv(f"<m:d>{e(mat)}</m:d>")
ok("<mtable><mtr><mtd><mi>a</mi></mtd><mtd><mi>b</mi></mtd></mtr><mtr><mtd><mi>c</mi></mtd><mtd><mi>d</mi></mtd></mtr></mtable>" in ml
   and tx == "([a, b]; [c, d])", f"m:m 2×2 qavsda — <mtable>, «{tx}»")
ml, tx = conv(f"<m:eqArr>{e(r('x=1'))}{e(r('y=2'))}</m:eqArr>")
ok('<mtable columnalign="left"><mtr><mtd>' in ml and tx == "x=1; y=2", "m:eqArr — <mtable> (har tenglama — qator)")
ml, tx = conv(f"<m:func><m:fName>{r('log')}</m:fName>{e(r('x'))}</m:func>")
ok('<mi>log</mi><mo rspace="0.1667em">\u2061</mo><mi>x</mi>' in ml and tx == "log x", f"m:func — nom + ⁡ (ApplyFunction), «{tx}»")
ml, tx = conv(f"<m:func><m:fName><m:limLow>{e(r('lim', 'p'))}<m:lim>{r('n→∞')}</m:lim></m:limLow></m:fName>{e(r('a'))}</m:func>")
ok("<munder><mi>lim</mi><mrow><mi>n</mi><mo>→</mo><mi>∞</mi></mrow></munder>" in ml and tx.startswith("lim_{n→∞}"), f"m:limLow — <munder>, «{tx}»")
ml, _ = conv(f"<m:limUpp>{e(r('A'))}<m:lim>{r('def')}</m:lim></m:limUpp>")
ok(ml.count("<mover>") == 1, "m:limUpp — <mover>")
ml, tx = conv(f'<m:acc><m:accPr><m:chr m:val="⃗"/></m:accPr>{e(r("v"))}</m:acc>')
ok('<mover accent="true"><mi>v</mi><mo>→</mo></mover>' in ml and tx == "vec(v)", "m:acc (vektor) — <mover accent>, birikuvchi belgi → alohida")
ml, _ = conv(f'<m:acc>{e(r("a"))}</m:acc>')
ok("<mo>^</mo>" in ml, "m:acc (chr yo'q) — standart ̂ (^)")
ml, _ = conv(f'<m:bar><m:barPr><m:pos m:val="top"/></m:barPr>{e(r("x"))}</m:bar>')
ok('<mover accent="true"><mi>x</mi><mo stretchy="true">¯</mo></mover>' in ml, "m:bar top — <mover> ¯")
ml, _ = conv(f'<m:bar>{e(r("x"))}</m:bar>')
ok("<munder accentunder" in ml, "m:bar (standart — pastda) — <munder>")
ml, _ = conv(f'<m:groupChr>{e(r("a+b"))}</m:groupChr>')
ok('<munder><mrow><mi>a</mi><mo>+</mo><mi>b</mi></mrow><mo stretchy="true">⏟</mo></munder>' in ml, "m:groupChr — <munder> ⏟")
ml, _ = conv(f'<m:borderBox>{e(r("E=mc"))}</m:borderBox><m:box>{e(r("2"))}</m:box>')
ok("<mi>E</mi>" in ml and "<mn>2</mn>" in ml and "box" not in ml.lower(), "m:box / m:borderBox — faqat mazmuni")
ml, tx = conv(f'<m:foo><m:r><m:t>q</m:t></m:r></m:foo>{r("+1")}')
ok("<mtext>q</mtext>" in ml and "<mn>1</mn>" in ml, "Noma'lum element — matni <mtext> ichida, qolgani konvertlanadi")
ml, _ = conv(f'<m:r><w:rPr><w:b/></w:rPr><m:t>a</m:t></m:r><w:del><m:r><m:t>DEL</m:t></m:r></w:del><w:ins><m:r><m:t>b</m:t></m:r></w:ins>')
ok("<mi>a</mi>" in ml and "DEL" not in ml and "<mi>b</mi>" in ml, "w:rPr e'tiborsiz, w:del tashlanadi, w:ins mazmuni qoladi")
ml, _ = conv(r("a&lt;b"))
ok("<mo>&lt;</mo>" in ml, "Maxsus belgilar escape qilinadi («<» → &lt;)")
ml, tx = conv(r("x=1"), para=True)
ok(ml.startswith('<math display="block" alttext="x=1">'), "m:oMathPara — display=block")
deep = r("x")
for _ in range(100): deep = f"<m:sSup>{e(deep)}<m:sup>{r('2')}</m:sup></m:sSup>"
ml, _ = conv(deep)
ok(ml.startswith("<math") and ml.count("<msup>") <= OM._MAX_DEPTH, "Juda chuqur ichma-ichlik — cheklangan (rekursiya xatosiz)")

# =============================================================================================
print("== 2. Matn belgisi «⟦m:…|…⟧»")
ml, tx = conv(f"<m:f><m:num>{r('1')}</m:num><m:den>{r('n')}</m:den></m:f>")
mk = OM.marker(ml, tx)
ok(mk.startswith("⟦m:") and mk.endswith("|1/n⟧") and "\n" not in mk and " " not in mk[:-6], f"Belgi bir qatorli, bo'shliqsiz ({len(mk)} belgi)")
m = OM.MARKER_RX.search(f"a {mk} b")
ok(m and OM.decode(m.group(1)) == ml, "Belgi → MathML (aynan)")
ok(OM.linearize(f"Kasr {mk} va {mk}.") == "Kasr 1/n va 1/n.", "linearize — chiziqli matn")
ok(OM.is_math_line(f"{mk} {mk}") and not OM.is_math_line(f"x {mk}"), "is_math_line — faqat formuladan iborat qator")
bad = "⟦m:AAAAbroken|x+1⟧"
ok(PK._inline(bad) == "x+1", "Buzilgan belgi — chiziqli matn (escape bilan)")
import base64, zlib
bomb = base64.urlsafe_b64encode(zlib.compress(b"<math>" + b"a" * 5_000_000, 9)).decode().rstrip("=")
ok(OM.decode(bomb) is None, "Siqilgan «bomba» (5 MB) — rad etiladi (200 KB chegarasi)")
evil = OM.marker('<math><mi onclick="x()" href="javascript:1">a</mi><script>alert(1)</script><maction><mi>b</mi></maction></math>', "a")
h = PK.structure_text("Matn " + evil + " tugadi. " + "Uzun matn. " * 20, "x")["html"]
ok("<math>" in h and "onclick" not in h and "href" not in h and "<script" not in h and "maction" not in h and "<mi>b</mi>" in h and PK.html_unsafe(h) is None,
   "Soxta belgi ichidagi xavfli MathML — sanitize tozalaydi (on*, href, script, maction)")
ok(PK._plain("A\n" + mk + "\n[JADVAL:1]") == "A\n1/n", "_plain — belgilar chiziqli matnga, [JADVAL] qatori olib tashlanadi")

# =============================================================================================
print("== 3. Sanitizer (server): MathML oq ro'yxati")
good = ('<p>Formula <math alttext="x^2"><msup><mi mathvariant="normal">x</mi><mn>2</mn></msup></math>.</p>'
        '<math display="block"><mrow><mo fence="true" form="prefix" stretchy="true">(</mo><mtable columnalign="left"><mtr><mtd><mi>a</mi></mtd></mtr></mtable>'
        '<mo fence="true" form="postfix" stretchy="true">)</mo></mrow><mfrac linethickness="0"><mn>1</mn><mn>2</mn></mfrac><mmultiscripts><mi>C</mi><mprescripts></mprescripts><none></none><mi>k</mi></mmultiscripts></math>')
ok(PK.sanitize(good) == good and PK.html_unsafe(good) is None, "To'g'ri MathML o'zgarmaydi, audit o'tadi")
cl = PK.sanitize('<math><mi onclick="alert(1)" style="color:red" class="x" id="y" href="javascript:alert(1)" xlink:href="javascript:1">x</mi></math>')
ok(cl == "<math><mi>x</mi></math>", f"<mi onclick/style/class/id/href/xlink:href> — atributlar tashlanadi ({cl})")
cl = PK.sanitize('<math><maction actiontype="toggle"><mi>a</mi><mi>b</mi></maction></math>')
ok(cl == "<math><mi>a</mi><mi>b</mi></math>", "<maction> — teg tashlanadi, mazmuni qoladi")
cl = PK.sanitize('<math><semantics><mi>y</mi><annotation encoding="TeX">\\frac</annotation><annotation-xml encoding="text/html"><img src=x onerror=alert(1)><p>z</p></annotation-xml></semantics></math>')
ok(cl == "<math><semantics><mi>y</mi></semantics></math>", f"annotation / annotation-xml — mazmuni bilan tashlanadi ({cl})")
cl = PK.sanitize('<math><mtext><img src="assets/img/a.png"><b>t</b><a href="https://x.uz">l</a></mtext><p>p</p><math><mi>n</mi></math></math>')
ok(cl == "<math><mtext>tl</mtext>p<mi>n</mi></math>", f"<math> ichida HTML teglari va ichma-ich <math> — teg tashlanadi, matn qoladi ({cl})")
cl = PK.sanitize('<mi>stray</mi><mfrac><mn>1</mn></mfrac>')
ok(cl == "stray1", "<math> tashqarisidagi MathML teglari — tashlanadi (matn qoladi)")
cl = PK.sanitize('<math display="evil" mathvariant="url(javascript:alert(1))" columnalign="left;x:y" alttext="a &quot;b&quot; <c>"><mi>q</mi></math>')
ok(cl == '<math alttext="a &quot;b&quot; &lt;c&gt;"><mi>q</mi></math>', f"Atribut qiymatlari: display faqat block/inline, url()/«:»/«;» — rad etiladi, alttext escape ({cl})")
cl = PK.sanitize('<math><mglyph src="https://evil/x.png"></mglyph><malignmark></malignmark><menclose notation="box"><mi>z</mi></menclose><mi>ok</mi></math>')
ok(cl == "<math><mi>z</mi><mi>ok</mi></math>", "mglyph / malignmark / menclose — oq ro'yxatda emas")
cl = PK.sanitize('<math><mi>a</mi><style>*{x}</style><script>alert(1)</script></math><p>keyin</p>')
ok(cl == "<math><mi>a</mi></math><p>keyin</p>", "<math> ichidagi script/style — mazmuni bilan tashlanadi, keyingi matn saqlanadi")
ok(PK.sanitize("<math><mi>a") == "<math><mi>a</mi></math>", "Yopilmagan MathML teglari yopiladi")
for bad_html in ('<math><mi onclick="x">a</mi></math>', '<math><mi href="https://x">a</mi></math>', '<math><maction><mi>a</mi></maction></math>',
                 '<math style="x"><mi>a</mi></math>', '<math display="x"></math>', '<math><mi mathvariant="url(x)">a</mi></math>', '<math><annotation-xml></annotation-xml></math>'):
    ok(PK.html_unsafe(bad_html) is not None, f"Audit rad etadi: {bad_html}")

# =============================================================================================
print("== 4. Kurs muharriri: clean_block HTML tozalashi formulani saqlaydi")
try:
    from app import kurs as KU
    d = KU.clean_block("paragraph", {"html": '<p>Formula: <math alttext="a/b"><mfrac><mi>a</mi><mi>b</mi></mfrac></math></p><math display="block"><msqrt><mi>x</mi></msqrt></math>'}, KU._Assets(None))
    ok('<math alttext="a/b"><mfrac><mi>a</mi><mi>b</mi></mfrac></math>' in d["html"] and '<math display="block"><msqrt>' in d["html"], "paragraph bloki — <math> saqlanadi")
    d = KU.clean_block("list", {"items": ['<math><mi onclick="x">a</mi></math>']}, KU._Assets(None))
    ok(d["items"] == ["<math><mi>a</mi></math>"], "list bandi — xavfli atribut tashlanadi, formula qoladi")
except Exception as ex:      # kurs moduli bazasiz import qilinmasa — test_kurs.py bu qismni server bilan tekshiradi
    ok(False, f"app.kurs import / clean_block: {ex!r}")

# =============================================================================================
print("== 5. docx_lecture → structure_text (tests/fixtures/omml/formulalar.docx)")
docx = FX / "formulalar.docx"
if not docx.is_file():
    subprocess.run([sys.executable, str(FX / "make_fixture.py"), str(docx)], check=True)
dx = PK.docx_lecture(docx.read_bytes())
txt = dx["text"]
ok(txt.count("⟦m:") == 13 and sum(c.count("⟦m:") for t in dx["tables"].values() for row in t for c in row) == 1,
   f"Matnda 13 ta formula belgisi (qator ichida 5, blok 8) + jadval katagida 1 — {txt.count('⟦m:')}")
plain = PK._plain(txt)
ok("⟦" not in plain and "Q=AK^αL^β" in plain and "x=(−b±√(b^2−4ac))/(2a)" in plain and "A=([a_{11}, a_{12}]; [a_{21}, a_{22}])" in plain
   and "∑_{i=1}^n x_i=S" in plain and "∫_0^1 x^2dx=1/3" in plain and "lim_{n→∞}(1+1/n)=e" in plain,
   "_plain (AI, iqtibos) — o'qiladigan chiziqli matn: Q=AK^αL^β, kvadrat tenglama, matritsa, ∑, ∫, lim")
ok("Indekslar: " in plain and "overline(x)." in plain, "Formula va keyingi tinish belgisi orasida bo'shliq yo'q")
st = PK.structure_text(txt, "Ishlab chiqarish funksiyasi va formulalar", {"images": {}, "tables": dx["tables"]})
h = st["html"]
ok(h.count("<math") == 14 and h.count('<math display="block"') == 8, f"HTML: 14 ta <math>, 8 tasi blok (yolg'iz formula ham) ({h.count('<math')} / {h.count('<math display=\"block\"')})")
ok(PK.html_unsafe(h) is None and PK.sanitize(h) == h, "HTML audit o'tadi, sanitize — o'zgarmaydi (idempotent)")
ok(all(x in h for x in ("<mfrac>", "<msqrt>", "<mroot>", "<munderover><mo>∑</mo>", "<msubsup><mo>∫</mo>", "<mtable>", "<mmultiscripts>", "<munder><mi>lim</mi>",
                        '<mo fence="true" form="prefix" stretchy="true">{</mo>', "<mo>⏟</mo>".replace("<mo>", '<mo stretchy="true">'))),
   "HTML: kasr, ildiz, n-darajali ildiz, ∑, ∫, matritsa, oldingi indeks, lim, tizim «{», groupChr")
ok(re.search(r"<p>Kobb–Duglas funksiyasi <math alttext=\"Q=AK\^αL\^β\">", h) is not None, "Qator ichidagi formula paragraf ichida (<p>…<math>…</p>)")
ok(re.search(r'<td><math alttext="a/b"><mfrac>', h) is not None, "Jadval katagidagi formula — qator ichida")
ok(st["plan"] == ["Ishlab chiqarish funksiyasi", "Chegaraviy mahsulot", "Matritsalar va tizimlar"], f"Reja to'g'ri: {st['plan']}")
ok(not any("⟦" in x for x in st["plan"] + st["refs"] + st["questions"]), "Reja/adabiyot/savollarda belgi yo'q")
ok(h.index("<h2>1. Ishlab chiqarish") < h.index('<math display="block" alttext="x=') < h.index("<h2>2. Chegaraviy"), "Blok formula o'z bo'limida")
st2 = PK.structure_text("# Mavzu\n## 1. " + OM.marker(*conv(r("f(x)"))) + " funksiya\nMatn " + "uzun. " * 30 + "\nSavollar:\n1. " + OM.marker(*conv(r("2+2"))) + " nechaga teng?",
                        "Mavzu", assign=True)
ok(st2["questions"] == ["2+2 nechaga teng?"] and "<h2>1. <math" in st2["html"], f"Savollar — chiziqli matn, sarlavhadagi formula — MathML ({st2['questions']})")
ok(PK.doc_title(txt) == "ISHLAB CHIQARISH FUNKSIYASI VA FORMULALAR", f"doc_title ishlaydi ({PK.doc_title(txt)!r})")

# =============================================================================================
print("== 6. Brauzer (paket va kurs pleyerlari)")
PWP, CHROME = os.environ.get("PW"), os.environ.get("CHROME")
node = shutil.which("node")
if PWP and CHROME and node:
    out = os.environ.get("OUT") or str(Path(tempfile.gettempdir()) / "isft_omml")
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
        json.dump({"html": h}, f); jp = f.name
    p = subprocess.run([node, str(ROOT / "tools" / "omml_player_check.js"), jp], capture_output=True, text=True, timeout=180,
                       env={**os.environ, "PW": PWP, "CHROME": CHROME, "OUT": out})
    os.unlink(jp)
    print(p.stdout.rstrip()); print(p.stderr.rstrip()[-2000:]) if p.returncode else None
    ok(p.returncode == 0, f"tools/omml_player_check.js (skrinshotlar: {out})")
else:
    print("  – PW / CHROME berilmagan — brauzer sinovi o'tkazib yuborildi")

print()
if fails:
    print(f"XATO: {len(fails)} ta"); [print("  ✗ " + f) for f in fails]; sys.exit(1)
print("Hammasi o'tdi")
