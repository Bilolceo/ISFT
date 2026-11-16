"""Taqdimot slaydlari → PNG va PDF (LibreOffice'siz, Pillow): app/taqdimot_slides.py + taqdimot.send() ulanishi (docs/taqdimot.md «Slayd rasmlari»).

Ishga tushirish:  python tests/run_all.py --only taqdimot_slides
   (yoki: ISFT_TEST_URL=http://127.0.0.1:8000 ISFT_CORE_DB=data/jarvis.db .venv/bin/python tests/test_taqdimot_slides.py)
1) Serversiz: outline'dan PNG (1600×900) va PDF (sahifa soni = slaydlar = pptx slaydlari), bo'sh emas (piksel dispersiyasi), 6+ slayd turi, uzun matn bo'linishi,
   o'zbekcha ʻ va kirill, daraja/indeks (ichma-ich ham), rasmli slayd, shrift topilmasa xato bermaydi, bitta slayd xatosi butun taqdimotni to'xtatmaydi,
   20 slayd < 5 s, paket.render_pdf (pdfium) bizning PDF'ni o'qiydi, pres_sends.png_count migratsiyasi (takror ishlaydi).
2) HTTP (server AI siz): yuborish → PDF + slides/NN.png diskda, /decks/{id}/sends/{ver}/slides/{n}.png (200, PNG, 1600×900; 404: yo'q n / eski versiya), PDF endi 200,
   ruxsat (begona kafedra, boshqa o'qituvchi, rektor — 403), studiya endpointi (operator 200, rektor 403), outline javobida `images`, paketda PDF (pleyer rasmlari),
   eski yuborilgan versiya (PNG yo'q): rasm/PDF 404, outline images = 0 (matnli zaxira ko'rinish).
DIQQAT: server bazasini o'zgartiradi — PRODUCTION'da ishlatilmaydi.
"""
import io, json, os, re, sqlite3, sys, tempfile, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
DB = Path(os.environ.get("ISFT_CORE_DB") or ROOT / "data" / "jarvis.db")
DATA = Path(os.environ.get("ISFT_CORE_DATA_DIR") or DB.parent)
B = os.environ.get("ISFT_TEST_URL", "http://127.0.0.1:8000")
PW = "Isft2026"
P, ST = "/api/taqdimot", "/api/studio"
N = [0]


def ok(cond, msg):
    N[0] += 1
    print(("  ✓ " if cond else "  ✗ XATO: ") + msg)
    if not cond:
        sys.exit(1)


from PIL import Image, ImageStat                                          # noqa: E402
from app import taqdimot_slides as TS, taqdimot_render as RD, taqdimot as TQ   # noqa: E402

tmp = Path(tempfile.mkdtemp())
(tmp / "img").mkdir()
Image.new("RGB", (900, 520), (235, 240, 250)).save(tmp / "img" / "img1.png")
tall = Image.new("RGB", (500, 640), (250, 240, 230)); tall.paste((0, 120, 60), (60, 60, 440, 580)); tall.save(tmp / "img" / "img2.png")
LONG = " ".join(["Differensial tenglama — noma'lum funksiya va uning hosilalarini bog'lovchi tenglama bo'lib, ʻoʻ va gʻ harflari bilan yoziladi."] * 6)
OUTLINE = {"subject": "Oliy matematika", "topic_no": 7, "title": "Birinchi tartibli differensial tenglamalar", "subtitle": "Ma'ruza · 2-kurs", "slides": [
    {"type": "plan", "title": "Reja", "bullets": ["Tushuncha", "Ajraluvchan tenglamalar", "Хулоса (Ўзбекча кирилл)"]},
    {"type": "definition", "title": "Ta'rif", "text": "**Differensial tenglama** — $x$, $y(x)$ va hosilalar bog'lanishi.", "highlight": "F(x, y, y') = 0", "note": "Tartib — eng yuqori hosila."},
    {"type": "theory", "title": "Nazariya", "text": "Tenglama $y' = f(x, y)$.", "bullets": ["Yechim $y = e^{x^{2}}$", "Shart $y(x_{0}) = y_{0}$", "Daraja $x^{2} + y^{2} = R^{2}$"]},
    {"type": "theory", "title": "Uzun matn", "text": LONG, "bullets": [f"Band {i}: " + "juda uzun band matni sig'masa slayd bo'linadi " * 2 for i in range(1, 9)]},
    {"type": "two_column", "title": "Ikki ustun", "columns": [{"title": "A", "bullets": ["$y' = 2xy$", "Ajratish"]}, {"title": "B", "bullets": ["$y' + y = 0$", "Chiziqli"]}]},
    {"type": "steps", "title": "Qadamlar", "steps": [{"title": "1.", "text": "Ajrating."}, {"title": "2.", "text": "Integrallang."}]},
    {"type": "example", "title": "Misol", "text": "$y' = 2xy$, $y(0) = 1$.", "steps": [{"title": "Ajrat.", "text": "$dy/y = 2x\\,dx$"}, {"title": "Yech.", "text": "$y = Ce^{x^{2}}$"}],
     "answer": "y = e^{x^{2}}", "check": ["$y' = 2xe^{x^{2}}$"], "note": "Tekshiring."},
    {"type": "image", "title": "Keng rasm", "image": 1, "caption": "1-rasm", "bullets": ["Yo'nalishlar maydoni"]},
    {"type": "image", "title": "Tik rasm", "image": 2, "caption": "2-rasm", "bullets": ["Rasm o'ngda"]},
    {"type": "tasks", "title": "Topshiriqlar", "cards": [{"title": "1", "text": "Yeching: $y' = 3x^{2}y$."}, {"title": "2", "text": "Koshi masalasi."}]},
    {"type": "questions", "title": "Nazorat savollari", "bullets": ["Differensial tenglama nima?", "Tartib qanday aniqlanadi?"]},
    {"type": "summary", "title": "Xulosa", "cards": [{"title": f"K{i}", "text": "Qisqa mazmun."} for i in range(6)]},
    {"type": "references", "title": "Adabiyotlar", "bullets": ["Saaduddinov A. Oliy matematika. T., 2020.", "Мирзиёев Ш. Ўзбекистон. Т., 2019."]},
]}

# =============================================================================================
print("— 1. Serversiz: outline → PNG + PDF —")
pages = RD.plan_pages(OUTLINE)
types = {pg["kind"] for pg in pages}
ok(len(types) >= 6 and {"stack", "two_column", "example", "image", "tasks", "questions", "summary"} <= types, f"Slayd turlari: {len(types)} xil ({', '.join(sorted(types))})")
ok(any("(davomi)" in (pg.get("title") or "") for pg in pages), "Uzun matn: «(davomi)» bilan bir nechta slaydga bo'lindi (taqdimot_render mantig'i)")
t0 = time.time()
r = TS.render_deck(OUTLINE, tmp / "img", tmp / "slides")
dt = time.time() - t0
n = TS.slide_count(OUTLINE)
ok(r["slides"] == n == 3 + len(pages), f"Slaydlar soni: {r['slides']} (titul + reja + {len(pages)} kontent + rahmat)")
from pptx import Presentation                                              # noqa: E402
RD.render(OUTLINE, tmp / "d.pptx", tmp / "img")
ok(len(Presentation(str(tmp / "d.pptx")).slides) == r["slides"], "PNG slaydlar soni = .pptx slaydlari soni (bir xil bo'linish, umumiy mantiq)")
files = sorted((tmp / "slides").glob("*.png"))
ok([f.name for f in files] == [f"{i:02d}.png" for i in range(1, n + 1)], "Fayllar: slides/01.png … NN.png")
bad = []
for f in files:
    im = Image.open(f)
    st = ImageStat.Stat(im.convert("L"))
    if im.size != (1600, 900) or im.mode != "RGB" or st.var[0] < 400 or st.mean[0] > 254.5:
        bad.append((f.name, im.size, round(st.var[0])))
ok(not bad, f"Har PNG 1600×900 va bo'sh emas (piksel dispersiyasi) — {len(files)} ta" + (f" XATO: {bad}" if bad else ""))
import pypdfium2 as pdfium                                                 # noqa: E402
pdf = r["pdf"]
doc = pdfium.PdfDocument(pdf)
ok(pdf[:5] == b"%PDF-" and len(doc) == n, f"PDF: {len(doc)} sahifa = slaydlar soni, {len(pdf) // 1024} KB")
pw, ph = doc[0].get_size()
ok(abs(pw / ph - 16 / 9) < 0.01 and abs(pw - 960) < 2, f"PDF sahifa 16:9 ({pw:.0f}×{ph:.0f} pt)")
doc.close()
from app import paket as PK                                                # noqa: E402
rp = PK.render_pdf(pdf)
ok(rp["pages"] == n and len(rp["images"]) == n, "paket.render_pdf (pdfium) bizning PDF'ni o'qiydi: har sahifa slayd rasmi (pleyer uchun)")
ok(dt < 5, f"{n} slayd {dt:.2f} s da chizildi (< 5 s)")
big = {**OUTLINE, "slides": OUTLINE["slides"] * 2}
t0 = time.time(); rb = TS.render_deck(big, tmp / "img", None); db_ = time.time() - t0
ok(rb["slides"] >= 20 and db_ < 5, f"{rb['slides']} slaydli taqdimot (PNG xotirada + PDF): {db_:.2f} s < 5 s")

print("— 2. Matn: ʻ (U+02BB), kirill, formula —")
ok(all(TS._covers("serif", ch) for ch in "ʻʼ’Ўўҳқғ«»№") and TS._pick("serif", "ʻ") == "serif", "Liberation Serif: ʻ, kirill (Ў ҳ қ ғ), tirnoqlar bor — zaxira kerak emas")
ok(TS._pick("serif", "∈") == "math" and TS._pick("math", "Қ") == "serif", "Shriftda yo'q belgi boshqa shriftdan olinadi (∈ → STIX; formuladagi o'zbek kirill Қ → Liberation)")
w1 = TS._words("$x^{2}$", 20, "000000", False, False, 1.0)[0]
ok(len(w1) == 2 and w1[1][2] < w1[0][2] and w1[1][4] < 0 and w1[0][4] == 0, "x^{2}: daraja kichikroq va yuqoriga ko'tarilgan")
w2 = TS._words("$e^{x^{2}}$", 20, "000000", False, False, 1.0)[0]
ok(len(w2) == 3 and w2[2][2] < w2[1][2] < w2[0][2], "e^{x^{2}}: ichma-ich daraja yana kichik (matnda «^{2}» chiqmaydi)")
w3 = TS._words("$a_{1}$", 20, "000000", False, False, 1.0)[0]
ok(w3[1][4] > 0, "a_{1}: indeks pastga tushirilgan")
# ʻ va kirill matnli slayd haqiqatan chiziladi (bo'sh emas, qayta chizganda bir xil)
from PIL import ImageDraw                                                   # noqa: E402
cv = TS.Canvas(); cv.canvas_box(100, 100, 600, 200, [RD.para("Oʻzbekiston Gʻarbiy · Ўзбекистон ҳудуди", 24)])
bb = ImageStat.Stat(cv.finish().convert("L"))
ok(bb.var[0] > 50, "ʻ va kirill matni chizildi")

print("— 3. Zaxira va xatolar —")
import app.taqdimot_slides as TS2                                           # noqa: E402
orig = TS._font_path
TS._font_path = lambda kind: None
TS._font.cache_clear(); TS._covers.cache_clear()
try:
    rf = TS.render_deck(OUTLINE, tmp / "img", None)
    ok(rf["slides"] == n and len(rf["pdf"]) > 1000, "Shrift fayllari topilmasa — xato bermaydi (Pillow ichki shrifti), slaydlar soni o'zgarmaydi")
finally:
    TS._font_path = orig
    TS._font.cache_clear(); TS._covers.cache_clear()
orig_draw = RD.draw
calls = [0]
def flaky(sl, pg, imgs):
    calls[0] += 1
    if calls[0] == 2: raise RuntimeError("sinov: chizish xatosi")
    return orig_draw(sl, pg, imgs)
RD.draw = flaky
try:
    re2 = TS.render_deck(OUTLINE, tmp / "img", None)
    ok(re2["slides"] == n, "Bitta slaydni chizishdagi xato butun taqdimotni to'xtatmaydi (shu slayd faqat shablon bilan qoladi)")
finally:
    RD.draw = orig_draw
rm = TS.render_deck(OUTLINE, tmp / "yoq_papka", None)
ok(rm["slides"] == n, "Rasm fayli yo'q (images_dir mavjud emas) — rasm slaydlari kulrang ramka/matn bilan chiziladi, xato yo'q")
e0 = TS.render_deck({"title": "Bo'sh", "slides": []}, None, None)
ok(e0["slides"] == 3, "Kontentsiz taqdimot: titul + reja + rahmat (3 slayd, pptx bilan bir xil)")

print("— 4. Migratsiya: pres_sends.png_count (eski baza) —")
con = sqlite3.connect(tmp / "old.db")
con.executescript("""CREATE TABLE pres_decks(id INTEGER PRIMARY KEY, user_id INT, user_name TEXT, dept_id INT, title TEXT, subject TEXT, topic_no TEXT,
  audience TEXT, target INT, source_name TEXT, source_kind TEXT, source_chars INT, truncated INT DEFAULT 0, images INT DEFAULT 0,
  outline TEXT, engine TEXT, model TEXT, status TEXT DEFAULT 'reja', slides INT, built_at TEXT, created_at TEXT, updated_at TEXT, deleted INT DEFAULT 0);
CREATE TABLE pres_sends(id INTEGER PRIMARY KEY, deck_id INT, course_id INT, lkey INT, code TEXT, version INT, title TEXT, slides INT,
  pptx_path TEXT, pdf_path TEXT, size INT, sha256 TEXT, note TEXT, sent_by INT, sent_by_name TEXT, sent_at TEXT,
  studio_ack_at TEXT, studio_ack_by TEXT, dept_ack_at TEXT, dept_ack_by TEXT, paket_asset_id INT, paket_error TEXT, UNIQUE(course_id, lkey, version));
INSERT INTO pres_sends(id,course_id,lkey,version,code,pptx_path,slides) VALUES(5,1,1,3,'1_X_y_L1','sends/1_1/v3/taqdimot.pptx',9);""")
TQ.init(con); TQ.init(con)
cols = {r_[1] for r_ in con.execute("PRAGMA table_info(pres_sends)")}
ok("png_count" in cols, "ALTER: pres_sends.png_count qo'shildi (init takror ishlaydi)")
row = con.execute("SELECT version, slides, png_count, pdf_path FROM pres_sends WHERE id=5").fetchone()
ok(row == (3, 9, None, None), "Eski yuborilgan versiya saqlandi: png_count = NULL (rasm yo'q), PDF yo'q")
pub = TQ._send_pub({**dict(zip(["id", "version", "code", "title", "slides", "size", "note", "sent_at", "sent_by_name", "deck_id", "pdf_path", "studio_ack_at", "dept_ack_at", "paket_error", "png_count"],
                               [5, 3, "c", "t", 9, 1, None, "2026-01-01", "x", 1, None, None, None, None, None]))})
ok(pub["png"] == 0 and pub["has_pdf"] is False, "_send_pub: eski versiya — png = 0, has_pdf = false (matnli zaxira ko'rinish)")
con.close()

# =============================================================================================
print("— 5. HTTP: yuborish → PDF + PNG, endpointlar, ruxsat —")
import httpx                                                                # noqa: E402

def q(sql, args=()):
    c = sqlite3.connect(f"file:{DB}?mode=ro", uri=True, timeout=30)
    try: return c.execute(sql, args).fetchall()
    finally: c.close()

def q1(sql, args=()):
    r_ = q(sql, args); return r_[0][0] if r_ else None

def w(sql, args=()):
    c = sqlite3.connect(DB, timeout=30)
    try:
        cur = c.execute(sql, args); c.commit(); return cur.lastrowid
    finally: c.close()

def S(uid_):
    c = httpx.Client(base_url=B, timeout=300)
    r_ = c.post("/api/login", json={"user_id": uid_, "password": PW})
    assert r_.status_code == 200, f"login {uid_}: {r_.status_code} {r_.text}"
    return c

def J(r_, code=200):
    assert r_.status_code == code, f"{r_.request.method} {r_.request.url.path}: {r_.status_code} {r_.text[:400]}"
    return r_.json()

def uid(role, where="", args=()):
    r_ = q1(f"SELECT id FROM users WHERE role=? AND COALESCE(active,1)=1 {where} ORDER BY id LIMIT 1", (role, *args)); assert r_, f"{role} akkaunti yo'q"; return r_

TEXT = ("# Talab va taklif\nBozor iqtisodiyotida narx talab va taklif muvozanati orqali shakllanadi. " * 3 +
        "\n## Talab qonuni\n- Narx oshsa talab kamayadi\n- Daromad ta'siri\n## Taklif qonuni\n- Narx oshsa taklif ortadi\n## Nazorat savollari\n- Talab qonuni nima?\n")
from app import clock as CLK                                                # noqa: E402
T0 = CLK.now_iso()[:19]
OQ_ID = uid("oqituvchi"); OQ_TID = q1("SELECT teacher_id FROM users WHERE id=?", (OQ_ID,))
OQ = S(OQ_ID)
OQ2_ID = q1("SELECT id FROM users WHERE role='oqituvchi' AND COALESCE(active,1)=1 AND teacher_id IS NOT NULL AND teacher_id!=? ORDER BY id LIMIT 1", (OQ_TID,))
OPER, REK = S(uid("montaj_operator")), S(uid("rektor"))
OQ_DEP = q1("SELECT COALESCE(u.department_id, t.department_id) FROM users u LEFT JOIN teachers t ON t.id=u.teacher_id WHERE u.id=?", (OQ_ID,))
KAF = S(uid("kafedra", "AND department_id=?", (OQ_DEP,)))
KAF2 = S(uid("kafedra", "AND department_id!=?", (OQ_DEP,)))
co0 = J(OQ.get(P + "/lessons"))["items"][0]
CID = co0["id"]
LK = next((l["key"] for l in co0["lessons"] if l["code"] == "L5"), co0["lessons"][-1]["key"])
D = J(OQ.post(P + "/decks/text", json={"text": TEXT, "course_id": CID, "lkey": LK, "title": "Talab va taklif (slayd rasmlari)"}))
did = D["id"]
J(OQ.post(P + f"/decks/{did}/build", json={}))
t0 = time.time()
S1 = J(OQ.post(P + f"/decks/{did}/send", json={"note": "slayd rasmlari"}))
ok(S1["send"]["version"] == 1 and S1["send"]["has_pdf"] and S1["send"]["png"] >= 4 and not S1.get("slides_error"), f"Yuborildi: v1, PDF bor, {S1['send']['png']} ta slayd rasmi ({time.time() - t0:.1f} s)")
PNG = S1["send"]["png"]
vd = DATA / "taqdimot" / "sends" / f"{CID}_{LK}" / "v1"
ok((vd / "taqdimot.pdf").is_file() and (vd / "taqdimot.pptx").is_file() and sorted(f.name for f in (vd / "slides").glob("*.png")) == [f"{i:02d}.png" for i in range(1, PNG + 1)],
   "Diskda: sends/<kurs>_<dars>/v1/{taqdimot.pptx, taqdimot.pdf, slides/01.png …}")
ok(q1("SELECT png_count FROM pres_sends WHERE course_id=? AND lkey=? AND version=1", (CID, LK)) == PNG and PNG == S1["send"]["slides"], "pres_sends.png_count = slaydlar soni = pptx slaydlari")
pdf_r = OQ.get(P + f"/decks/{did}/sends/1/pdf")
doc = pdfium.PdfDocument(pdf_r.content)
ok(pdf_r.status_code == 200 and "application/pdf" in pdf_r.headers.get("content-type", "") and len(doc) == PNG, f"PDF endi doim 200 (LibreOffice'siz ham): {len(doc)} sahifa")
doc.close()
r1 = OQ.get(P + f"/decks/{did}/sends/1/slides/1.png")
im = Image.open(io.BytesIO(r1.content))
ok(r1.status_code == 200 and r1.headers["content-type"] == "image/png" and im.size == (1600, 900) and r1.content[:8] == b"\x89PNG\r\n\x1a\n", "GET …/sends/1/slides/1.png: 200, PNG 1600×900")
ok(OQ.get(P + f"/decks/{did}/sends/1/slides/{PNG}.png").status_code == 200, "Oxirgi slayd (rahmat) ham 200")
ok(OQ.get(P + f"/decks/{did}/sends/1/slides/{PNG + 1}.png").status_code == 404 and OQ.get(P + f"/decks/{did}/sends/1/slides/0.png").status_code == 404, "Yo'q slayd raqami (0 va N+1) — 404")
ok(OQ.get(P + f"/decks/{did}/sends/9/slides/1.png").status_code == 404, "Yo'q versiya — 404")
ok(KAF.get(P + f"/decks/{did}/sends/1/slides/2.png").status_code == 200, "Kafedra mudiri (o'z kafedrasi): slayd rasmini ko'radi")
ok(KAF2.get(P + f"/decks/{did}/sends/1/slides/1.png").status_code == 403, "Boshqa kafedra — 403")
ok(REK.get(P + f"/decks/{did}/sends/1/slides/1.png").status_code == 403, "Rektor — 403")
if OQ2_ID:
    ok(S(OQ2_ID).get(P + f"/decks/{did}/sends/1/slides/1.png").status_code == 403, "Boshqa o'qituvchi — 403")
ok(httpx.get(B + P + f"/decks/{did}/sends/1/slides/1.png").status_code == 401, "Kirishsiz — 401")
ok(q1("SELECT COUNT(*) FROM audit_log WHERE resource='presentations' AND allowed=0 AND ts>=? AND detail LIKE ?", (T0, f"%#{did}%")) >= 1, "Audit: rad etilgan urinishlar yozildi")
n_aud = q1("SELECT COUNT(*) FROM audit_log WHERE user_id=? AND ts>=? AND action LIKE '%slayd%'", (OQ_ID, T0))
for i in range(1, 4): OQ.get(P + f"/decks/{did}/sends/1/slides/{i}.png")
ok(q1("SELECT COUNT(*) FROM audit_log WHERE user_id=? AND ts>=? AND action LIKE '%slayd%'", (OQ_ID, T0)) == n_aud, "Har rasm so'rovi audit jurnalini to'ldirmaydi (faqat rad etish yoziladi)")

print("— 6. HTTP: studiya (syomkada o'qish) —")
so = OPER.get(f"{ST}/lessons/{CID}/{LK}/taqdimot/1/outline")
oj = J(so)
ok(oj["images"] == PNG and oj["slides"] and any(x["n"] == 3 for x in oj["slides"]), f"Studiya outline: images = {PNG}, slaydlar (n — pptx raqami) bor")
sp = OPER.get(f"{ST}/lessons/{CID}/{LK}/taqdimot/1/slides/2.png")
ok(sp.status_code == 200 and Image.open(io.BytesIO(sp.content)).size == (1600, 900), "Operator: slayd rasmi (studiya endpointi) 200")
ok(OPER.get(f"{ST}/lessons/{CID}/{LK}/taqdimot/1/slides/{PNG + 1}.png").status_code == 404, "Studiya: yo'q slayd — 404")
sd = OPER.get(f"{ST}/lessons/{CID}/{LK}/taqdimot/1/pdf")
ok(sd.status_code == 200 and sd.content[:5] == b"%PDF-", "Studiya PDF havolasi ishlaydi (200, %PDF)")
ok(OQ.get(f"{ST}/lessons/{CID}/{LK}/taqdimot/1/slides/1.png").status_code == 200, "O'qituvchi o'z darsining slaydini studiyada ham ko'radi")
ok(REK.get(f"{ST}/lessons/{CID}/{LK}/taqdimot/1/slides/1.png").status_code == 403, "Rektor: studiya slayd rasmi — 403")
if OQ2_ID:
    ok(S(OQ2_ID).get(f"{ST}/lessons/{CID}/{LK}/taqdimot/1/slides/1.png").status_code == 403, "Boshqa o'qituvchi: begona dars slaydi — 403")
ok(httpx.get(B + f"{ST}/lessons/{CID}/{LK}/taqdimot/1/slides/1.png").status_code == 401, "Kirishsiz — 401")
latest = J(OPER.get(f"{ST}/lessons/{CID}/{LK}"))["taqdimot"]["latest"]
ok(latest["png"] == PNG and latest["has_pdf"], "Dars tafsiloti: taqdimot.latest.png va has_pdf (PDF havolasi ko'rinadi)")

print("— 7. Paket: pleyerda aniq slayd rasmlari (LibreOffice'siz) —")
rows = q("SELECT kind, meta FROM pk_assets WHERE course_id=? AND topic_no=? AND purpose='taqdimot' AND deleted=0 ORDER BY id", (CID, LK))
ok([r_[0] for r_ in rows][-2:] == ["pptx", "pdf"], "Paketda .pptx va undan KEYIN PDF (pleyer PDF sahifalarini slayd rasmi qiladi)")
pm = json.loads(rows[-1][1])
ok(pm.get("rendered") == PNG and len(pm.get("images") or []) == PNG, f"Paket PDF'i: {PNG} sahifa slayd rasmiga aylantirildi")
ok(S1["paket_error"] is None and q1("SELECT COUNT(*) FROM pk_assets WHERE course_id=? AND topic_no=? AND purpose='taqdimot' AND kind='pdf' AND deleted=0", (CID, LK)) == 1,
   "Faol PDF taqdimot bitta (studiya montaji ham shu PDF'dan slayd oladi), paket xatosi yo'q")

print("— 8. Eski yuborilgan versiya (PNG yo'q) —")
old = q("SELECT * FROM pres_sends WHERE course_id=? AND lkey=? AND version=1", (CID, LK))
cols_ = [r_[1] for r_ in q("PRAGMA table_info(pres_sends)")]
rec = dict(zip(cols_, old[0])); rec.pop("id"); rec.update(version=7, png_count=None, pdf_path=None)
w(f"INSERT INTO pres_sends({','.join(rec)}) VALUES({','.join('?' * len(rec))})", tuple(rec.values()))
try:
    ok(OQ.get(P + f"/decks/{did}/sends/7/slides/1.png").status_code == 404 and OQ.get(P + f"/decks/{did}/sends/7/pdf").status_code == 404, "Eski versiya: slayd rasmi va PDF — 404 (xato emas, «yo'q»)")
    ok(OQ.get(P + f"/decks/{did}/sends/7/pptx").status_code == 200, "Eski versiya: .pptx ochiladi")
    oo = J(OPER.get(f"{ST}/lessons/{CID}/{LK}/taqdimot/7/outline"))
    ok(oo["images"] == 0 and oo["slides"], "Eski versiya outline: images = 0 → o'qish rejimi matnli zaxira ko'rinishda (slaydlar matni bor)")
    ok(OPER.get(f"{ST}/lessons/{CID}/{LK}/taqdimot/7/slides/1.png").status_code == 404, "Studiya: eski versiya slayd rasmi — 404")
    # brauzer: studiyada o'qish rejimi (rasm) va eski versiya (matnli zaxira) — PW va CHROME berilsa
    import shutil, subprocess
    node, pwj, chrome = shutil.which("node"), os.environ.get("PW"), os.environ.get("CHROME")
    if node:
        rc = subprocess.run([node, "--check", str(ROOT / "tools" / "taqdimot_slides_check.js")], capture_output=True, text=True)
        ok(rc.returncode == 0, "node --check tools/taqdimot_slides_check.js")
        rc = subprocess.run([node, "--check", str(ROOT / "static" / "studio.js")], capture_output=True, text=True)
        ok(rc.returncode == 0, "node --check static/studio.js")
    if not (pwj and chrome and node):
        print("  – PW/CHROME berilmagan — brauzer sinovi o'tkazib yuborildi")
    else:
        out = os.environ.get("ZJ_OUT") or str(Path(os.environ.get("TMPDIR", "/tmp")) / "isft_taqdimot_slides")
        env = dict(os.environ, B=B, PW_=PW, O_UID=str(uid("montaj_operator")), CID=str(CID), LK=str(LK), VER="1", OLD_VER="7", OUT=out)
        rr = subprocess.run([node, str(ROOT / "tools" / "taqdimot_slides_check.js")], cwd=ROOT, env=env, capture_output=True, text=True, timeout=300)
        nb = 0
        for ln in (rr.stdout + rr.stderr).splitlines():
            s_ = ln.strip()
            if s_.startswith("✓"): ok(True, "[brauzer] " + s_[1:].strip()); nb += 1
            elif s_.startswith("✗"): ok(False, "[brauzer] " + s_[1:].strip())
        ok(rr.returncode == 0 and nb >= 20, f"tools/taqdimot_slides_check.js: chiqish kodi 0, {nb} ta tekshiruv · skrinshotlar: {out}" + ("" if rr.returncode == 0 else " · " + (rr.stdout + rr.stderr)[-400:]))
finally:
    w("DELETE FROM pres_sends WHERE course_id=? AND lkey=? AND version=7", (CID, LK))

print("— 9. Qayta yuborish (v2): yangi rasmlar —")
o2 = J(OQ.get(P + f"/decks/{did}"))["outline"]
o2["slides"].append({"type": "summary", "title": "Xulosa", "cards": [{"title": "Talab", "text": "Narx bilan teskari"}]})
J(OQ.post(P + f"/decks/{did}/outline", json={"outline": o2})); J(OQ.post(P + f"/decks/{did}/build", json={}))
S2 = J(OQ.post(P + f"/decks/{did}/send", json={}))
ok(S2["send"]["version"] == 2 and S2["send"]["png"] == PNG + 1, f"v2: {S2['send']['png']} slayd rasmi (xulosa qo'shildi), v1 rasmlari o'zgarmadi")
ok(OQ.get(P + f"/decks/{did}/sends/1/slides/{PNG}.png").status_code == 200 and OQ.get(P + f"/decks/{did}/sends/1/slides/{PNG + 1}.png").status_code == 404, "v1 tarixda o'z rasmlari bilan qoladi")
J(OQ.post(P + f"/decks/{did}/delete", json={}))
ok((vd / "slides" / "01.png").is_file(), "Taqdimot o'chirilgach ham yuborilgan versiya rasmlari tarixda qoladi")

print(f"\n✓ {N[0]} ta tekshiruv o'tdi")
