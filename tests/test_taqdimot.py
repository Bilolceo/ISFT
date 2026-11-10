import os
"""«Taqdimot» (app/taqdimot.py): o'qituvchi taqdimoti — material → reja → .pptx (server ishlab turishi kerak).

Ishga tushirish:  ISFT_TEST_URL=http://127.0.0.1:8000 ISFT_CORE_DB=data/jarvis.db .venv/bin/python tests/test_taqdimot.py
Ikki qism:
  1) Jarayon ichida (serversiz): soxta AI (fake_outline) va qoidaviy reja → normalize → render: haqiqiy .pptx, rahmat slaydi oxirida,
     slaydlar soni kontentga moslashadi, rasmlar slaydga tushadi, matn 14 pt dan kichik emas, uzun matn bo'linadi («davomi»).
  2) HTTP (server AI siz — ANTHROPIC_API_KEY yo'q; run_all.py shunday ishga tushiradi): ruxsatlar (oqituvchi, kafedra; boshqalar 403),
     .docx / .pdf / matn yuklash, fayl turi (sehrli baytlar) va hajm cheklovi, reja tahriri, pptx yaratish va yuklab olish, kafedra ko'rishi
     (faqat o'z kafedrasi, tahrirsiz), kunlik cheklov (429), audit jurnali.
Server Claude bilan ishlayotgan bo'lsa (ANTHROPIC_API_KEY), pul sarflamaslik uchun generatsiya testlari o'tkazib yuboriladi.
"""
import io, re, sqlite3, sys, tempfile, zipfile
from pathlib import Path
import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from app import clock as CLK                                         # noqa: E402
from app import taqdimot as TQ, taqdimot_render as RD, taqdimot_extract as EX   # noqa: E402
DB = Path(os.environ.get("ISFT_CORE_DB") or ROOT / "data" / "jarvis.db")
B = os.environ.get("ISFT_TEST_URL", "http://127.0.0.1:8000")
PW = "Isft2026"
N = [0]
P = "/api/taqdimot"


def ok(cond, msg):
    N[0] += 1
    print(("✓ " if cond else "✗ XATO: ") + msg)
    if not cond:
        sys.exit(1)


def q(sql, args=()):
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True, timeout=30)
    try: return con.execute(sql, args).fetchall()
    finally: con.close()


def q1(sql, args=()):
    r = q(sql, args); return r[0][0] if r else None


def w(sql, args=()):
    con = sqlite3.connect(DB, timeout=30)
    try: con.execute(sql, args); con.commit()
    finally: con.close()


def S(uid):
    c = httpx.Client(base_url=B, timeout=300)
    r = c.post("/api/login", json={"user_id": uid, "password": PW})
    assert r.status_code == 200, f"login {uid}: {r.status_code} {r.text}"
    return c


def J(r, code=200):
    assert r.status_code == code, f"{r.request.method} {r.request.url.path}: {r.status_code} {r.text[:400]}"
    return r.json()


# ---------------------------------------------------------------- namuna materiallar
def png(w_=640, h_=400, color=(30, 90, 160)):
    from PIL import Image, ImageDraw
    im = Image.new("RGB", (w_, h_), (235, 238, 245))
    d = ImageDraw.Draw(im)
    d.rectangle([20, 20, w_ - 20, h_ - 20], outline=color, width=10)
    d.line([20, h_ - 20, w_ - 20, 20], fill=(180, 0, 0), width=8)
    for i in range(0, w_, 37):
        d.line([i, 20, i, h_ - 20], fill=(i % 255, 120, 200 - i % 150), width=2)
    b = io.BytesIO(); im.save(b, "PNG"); return b.getvalue()


def make_docx(n_sections=4, with_image=True) -> bytes:
    import docx
    from docx.shared import Inches
    d = docx.Document()
    d.add_heading("Talab va taklif nazariyasi", 0)
    for i in range(n_sections):
        d.add_heading(f"{i + 1}. Bo'lim: bozor mexanizmi {i + 1}", 1)
        d.add_paragraph(("Bozor iqtisodiyotida narx talab va taklif muvozanati orqali shakllanadi. " * 3) + f"Bu {i + 1}-bo'limning asosiy g'oyasi.")
        for k in range(3):
            d.add_paragraph(f"Muhim jihat {k + 1}: iste'molchi va ishlab chiqaruvchi xatti-harakati", style="List Bullet")
        if with_image and i == 1:
            tmp = Path(tempfile.mkdtemp()) / "g.png"; tmp.write_bytes(png())
            d.add_picture(str(tmp), width=Inches(4))
            d.add_paragraph("1-rasm. Talab va taklif grafigi")
    d.add_heading("Nazorat savollari", 1)
    for qn in ("Talab qonuni nima?", "Muvozanat narxi qanday aniqlanadi?", "Elastiklik nima?"):
        d.add_paragraph(qn, style="List Number")
    d.add_heading("Foydalanilgan adabiyotlar", 1)
    d.add_paragraph("Mankiw N. G. Principles of Economics. — Cengage, 2020.", style="List Number")
    b = io.BytesIO(); d.save(b); return b.getvalue()


def make_pdf() -> bytes:
    from PIL import Image
    pages = [Image.open(io.BytesIO(png(900, 600, c))).convert("RGB") for c in ((30, 90, 160), (0, 140, 60))]
    b = io.BytesIO(); pages[0].save(b, "PDF", save_all=True, append_images=pages[1:]); return b.getvalue()


def pptx_info(raw_or_path) -> dict:
    from pptx import Presentation
    from pptx.util import Emu
    p = Presentation(raw_or_path if isinstance(raw_or_path, str) else io.BytesIO(raw_or_path))
    slides = list(p.slides)
    small, pics, texts, outside = [], 0, [], []
    for i, s in enumerate(slides):
        xml = s._element.xml
        for m in re.finditer(r'<a:r>\s*<a:rPr[^>]*\bsz="(\d+)"[^>]*>.*?<a:t>([^<]*)</a:t>', xml, re.S):
            if m.group(2).strip() and int(m.group(1)) < 1400:
                small.append((i + 1, int(m.group(1)), m.group(2)[:30]))
        for sh in s.shapes:
            if sh.shape_type == 13 and i not in (0,) and Emu(sh.left).pt > 200:
                pics += 1
            if 0 < i < len(slides) - 1 and sh.shape_type in (1, 13, 17) and sh.shape_id >= 6 and Emu(sh.top).pt > 70:
                if Emu(sh.left).pt < 280 or Emu(sh.left + sh.width).pt > 925 or Emu(sh.top + sh.height).pt > 522:
                    outside.append((i + 1, sh.name, int(Emu(sh.left).pt), int(Emu(sh.top + sh.height).pt)))
        flat = lambda shapes: [x for sh in shapes for x in (flat(sh.shapes) if sh.shape_type == 6 else [sh])]
        texts.append(" ".join(sh.text_frame.text for sh in flat(s.shapes) if sh.has_text_frame))
    return {"n": len(slides), "small": small, "pics": pics, "texts": texts, "outside": outside, "last": texts[-1] if texts else ""}


# =============================================================================================
print("— 1. Jarayon ichida: ajratish, soxta AI, qoidaviy reja, render —")
ok(EX.sniff(b"%PDF-1.7 ...") == "pdf" and EX.sniff(make_docx(1, False)) == "docx" and EX.sniff("Salom dunyo matn".encode()) == "txt", "Fayl turi sehrli baytlar bo'yicha: pdf / docx / txt")
for bad, why in ((b"PK\x03\x04" + b"\x00" * 50, "boshqa zip"), (b"\x89PNG\r\n\x1a\n" + b"\x00" * 40, "png"), (b"MZ\x90\x00\x03\x00\x00\x00", "exe")):
    try:
        EX.sniff(bad); ok(False, f"{why} qabul qilinmasligi kerak")
    except EX.BadFile:
        ok(True, f"Ruxsat etilmagan fayl rad etiladi: {why}")

tmp = Path(tempfile.mkdtemp())
ex = EX.extract(make_docx(4, True), "docx", tmp / "img")
ok(len(ex["images"]) == 1 and (tmp / "img" / ex["images"][0]["file"]).exists(), f"Word: rasm ajratildi ({ex['images'][0]['w']}×{ex['images'][0]['h']})")
ok(sum(b["k"] == "h" for b in ex["blocks"]) >= 6 and sum(b["k"] == "li" for b in ex["blocks"]) >= 12, "Word: sarlavhalar va ro'yxatlar tanildi")
ok("Bo'lim" in ex["images"][0]["ctx"], "Rasm konteksti (atrofidagi sarlavha) saqlandi")
expdf = EX.extract(make_pdf(), "pdf", tmp / "pimg")
ok(len(expdf["images"]) == 2, "PDF: sahifalardagi 2 ta rasm ajratildi")

# OMML formula → chiziqli matn
from lxml import etree
om = etree.fromstring('<m:oMath xmlns:m="http://schemas.openxmlformats.org/officeDocument/2006/math"><m:sSup><m:e><m:r><m:t>x</m:t></m:r></m:e><m:sup><m:r><m:t>2</m:t></m:r></m:sup></m:sSup>'
                      '<m:r><m:t>+</m:t></m:r><m:f><m:num><m:r><m:t>a</m:t></m:r></m:num><m:den><m:r><m:t>b</m:t></m:r></m:den></m:f></m:oMath>')
ok(EX.omml(om) == "x^(2)+(a)/(b)", f"Word formulasi (OMML) chiziqli matnga: {EX.omml(om)}")

meta = {"subject": "Iqtisodiyot nazariyasi", "topic_no": "5", "title": "Talab va taklif"}
counts = {}
for tgt in (8, 16):
    o = TQ.normalize(TQ.fake_outline(ex, {**meta, "target": tgt}), len(ex["images"]))
    out = tmp / f"fake{tgt}.pptx"
    r = RD.render(o, out, tmp / "img")
    info = pptx_info(str(out))
    counts[tgt] = info["n"]
    types = {s["type"] for s in o["slides"]}
    ok(info["n"] == r["slides"] and "RAHMAT" in info["last"], f"Soxta AI (≈{tgt}): {info['n']} slayd, oxirgisi — «E'tiboringiz uchun rahmat»")
    ok(not info["small"], f"Soxta AI (≈{tgt}): 14 pt dan kichik matn yo'q" + (f" {info['small'][:3]}" if info["small"] else ""))
    ok(not info["outside"], f"Soxta AI (≈{tgt}): kontent x=285…920, y≤520 oralig'ida" + (f" {info['outside'][:3]}" if info["outside"] else ""))
    ok(info["pics"] >= 1, f"Soxta AI (≈{tgt}): rasm slaydga joylashdi")
    ok("IQTISODIYOT NAZARIYASI" in info["texts"][0] and "5-mavzu:" in info["texts"][0], "Titul: fan nomi (katta harf) va «5-mavzu:»")
    ok("REJA" in info["texts"][1].upper() and len(re.findall(r"\d\.\t", info["texts"][1])) >= 3, "2-slayd: reja bandlari")
ok(counts[16] > counts[8], f"Slaydlar soni kontentga moslashadi: ≈8 → {counts[8]}, ≈16 → {counts[16]}")
ok({"definition", "two_column", "steps", "example", "image", "tasks", "questions", "summary", "references"} <= types, "Barcha slayd turlari chiziladi")

o = TQ.normalize(TQ.rule_outline(ex, {**meta, "source_stem": "test"}), len(ex["images"]))
info = pptx_info(str(RD.render(o, tmp / "rule.pptx", tmp / "img") and tmp / "rule.pptx"))
ok("RAHMAT" in info["last"] and info["pics"] == 1 and not info["small"], f"AI siz (qoidaviy) reja: {info['n']} slayd, rasm bilan, 14 pt dan kichik matn yo'q")
ok(any(s["type"] == "questions" for s in o["slides"]) and any(s["type"] == "references" for s in o["slides"]), "Qoidaviy reja: «Nazorat savollari» va «Adabiyotlar» bo'limlari tanildi")

long_o = {"title": "Uzun", "slides": [{"type": "theory", "title": "Juda uzun nazariya", "text": "Kirish matni. " * 30,
                                       "bullets": [f"{i}-band: " + "uzun tushuntirish matni " * 9 for i in range(14)]}]}
lo = TQ.normalize(long_o, 0)
info = pptx_info(str(RD.render(lo, tmp / "long.pptx") and tmp / "long.pptx"))
ok(info["n"] >= 6 and any("(davomi)" in t for t in info["texts"]) and not info["small"], f"Sig'magan matn bo'linadi: {info['n'] - 3} kontent slayd, «(davomi)», 14 pt dan kichik emas")
try:
    TQ.normalize({"slides": [{"type": "plan", "bullets": ["a"]}]}, 0); ok(False, "Bo'sh reja rad etilishi kerak")
except ValueError:
    ok(True, "Kontent slaydisiz reja rad etiladi")
bad = TQ.normalize({"slides": [{"type": "nomalum", "title": "X", "bullets": ["a"]}, {"type": "image", "title": "R", "image": 9, "caption": "c"}]}, 1)
ok(bad["slides"][0]["type"] == "theory" and bad["slides"][1]["type"] == "theory" and bad["slides"][1]["image"] == 0, "Normallashtirish: noma'lum tur → nazariya, mavjud bo'lmagan rasm olib tashlanadi")
ok(TQ.OUTLINE_SCHEMA["properties"]["slides"]["items"]["additionalProperties"] is False and set(TQ.SLIDE_SCHEMA["required"]) == set(TQ.SLIDE_SCHEMA["properties"]),
   "Claude uchun JSON sxema: qat'iy (barcha maydonlar required, additionalProperties=false)")
src = (ROOT / "app" / "taqdimot.py").read_text(encoding="utf-8")
ok("sk-ant" not in src and 'os.getenv("ANTHROPIC_API_KEY"' in src, "API kalit kodda yo'q — faqat ANTHROPIC_API_KEY muhit o'zgaruvchisidan")
tpl = zipfile.ZipFile(RD.TEMPLATE)
meta_xml = (tpl.read("docProps/core.xml") + tpl.read("docProps/app.xml")).decode("utf-8", "ignore")
ok("OpenAI" not in meta_xml and len(tpl.namelist()) < 60 and sum(n.startswith("ppt/slides/slide") for n in tpl.namelist()) == 4, "Shablon: 4 slayd, begona metama'lumot yo'q")

# =============================================================================================
print("— 2. HTTP: ruxsatlar —")
T0 = CLK.now_iso()[:19]
OQ_ID = q1("SELECT id FROM users WHERE role='oqituvchi' AND COALESCE(active,1)=1 ORDER BY id LIMIT 1")
OQ_DEP = q1("SELECT COALESCE(u.department_id, t.department_id) FROM users u LEFT JOIN teachers t ON t.id=u.teacher_id WHERE u.id=?", (OQ_ID,))
KAF_ID = q1("SELECT id FROM users WHERE role='kafedra' AND department_id=? AND COALESCE(active,1)=1 ORDER BY id LIMIT 1", (OQ_DEP,))
KAF2_ID = q1("SELECT id FROM users WHERE role='kafedra' AND department_id!=? AND COALESCE(active,1)=1 ORDER BY id LIMIT 1", (OQ_DEP,))
OQ, KAF, KAF2 = S(OQ_ID), S(KAF_ID), S(KAF2_ID)
ok(httpx.get(B + P + "/meta").status_code == 401, "Kirishsiz (talaba ham — xodim sessiyasi yo'q): 401")
for uid, nm in ((q1("SELECT id FROM users WHERE role='rektor' LIMIT 1"), "rektor"), (q1("SELECT id FROM users WHERE role='call_center' LIMIT 1"), "call-markaz"),
                (q1("SELECT id FROM users WHERE role='talabalar' LIMIT 1"), "registrator"), (q1("SELECT id FROM users WHERE role='it_head' LIMIT 1"), "AT boshlig'i")):
    c = S(uid)
    ok(c.get(P + "/meta").status_code == 403 and c.post(P + "/decks/text", json={"text": "x" * 100}).status_code == 403, f"{nm} (#{uid}): 403")
ok(q1("SELECT COUNT(*) FROM audit_log WHERE resource='presentations' AND allowed=0 AND ts>=?", (T0,)) >= 8, "Rad etilgan so'rovlar audit jurnalida (resource=presentations)")
M = J(OQ.get(P + "/meta"))
ok(M["mode"] == "own" and M["limit"] >= 1 and set(M["types"]) >= {"plan", "example", "image", "summary"}, f"O'qituvchi (#{OQ_ID}): rejim own · {M['label']} · fanlar {len(M['subjects'])}")
ok(J(KAF.get(P + "/meta"))["mode"] == "dept", f"Kafedra mudiri (#{KAF_ID}): rejim dept")
st = J(OQ.get("/api/status"))
ok(st.get("taqdimot", {}).get("engine") == M["engine"] and st["taqdimot"]["label"] == M["label"], f"/api/status: taqdimot → {st['taqdimot']['label']}")

if M["engine"] == "claude":
    print("! Server Claude bilan ishlayapti (ANTHROPIC_API_KEY) — generatsiya testlari o'tkazib yuborildi (pul sarflanmasin).")
    print(f"Hammasi o'tdi: {N[0]} ta tekshiruv.")
    sys.exit(0)

print("— 3. HTTP: material → reja → pptx —")
used0 = M["used"]
D = J(OQ.post(P + "/decks", params={"name": "talab_taklif.docx", "subject": "Iqtisodiyot nazariyasi", "topic_no": "5"}, content=make_docx(4, True),
              headers={"Content-Type": "application/octet-stream"}))
did = D["id"]
ok(D["status"] == "reja" and D["outline"]["slides"] and D["engine"] == M["engine"], f"Word yuklandi → reja: {len(D['outline']['slides'])} slayd · {D['engine_label']}")
ok(D["outline"]["subject"] == "Iqtisodiyot nazariyasi" and D["outline"]["topic_no"] == "5", "O'qituvchi kiritgan fan va mavzu raqami rejada")
ok(D["images"] == 1 and D["image_list"] and any(s.get("image") == 1 for s in D["outline"]["slides"]), "Rasm rejadagi slaydga biriktirildi")
ok(OQ.get(P + f"/decks/{did}/img/1").headers.get("content-type", "").startswith("image/"), "Rasm ko'rinishi (tahrirlovchi uchun)")
ok(J(OQ.get(P + "/meta"))["used"] == used0 + 1, "Kunlik hisoblagich +1")
dir_ = Path(os.environ.get("ISFT_CORE_DATA_DIR") or DB.parent) / "taqdimot" / str(did)
ok(dir_.exists() and (dir_ / "manba.docx").exists() and (dir_ / "material.json").exists(), "Material ma'lumotlar papkasida saqlandi (db.DATA_DIR/taqdimot)")
ok(OQ.get(P + f"/decks/{did}/download").status_code == 404, "PPTX hali yaratilmagan — yuklab olish 404")

o = D["outline"]
o["title"] = "Talab va taklif: bozor muvozanati"
o["slides"].insert(1, {"type": "example", "title": "1-misol. Muvozanat", "text": "$Q_{d} = 100 − 2P$, $Q_{s} = 20 + 3P$.",
                       "steps": [{"title": "Tenglik:", "text": "100 − 2P = 20 + 3P"}, {"title": "Narx:", "text": "P = 16"}], "answer": "P = 16, Q = 68",
                       "check": ["Q = 68 ✓"], "note": "Ishorani adashtirmang."})
o["slides"].append({"type": "summary", "title": "Xulosa", "cards": [{"title": "Talab", "text": "Narx bilan teskari"}, {"title": "Taklif", "text": "Narx bilan to'g'ri"}]})
D2 = J(OQ.post(P + f"/decks/{did}/outline", json={"outline": o}))
ok(D2["title"] == "Talab va taklif: bozor muvozanati" and D2["outline"]["slides"][1]["type"] == "example", "Reja tahriri saqlandi (sarlavha, yangi slaydlar, tartib)")
ok(OQ.post(P + f"/decks/{did}/outline", json={"outline": {"slides": []}}).status_code == 400, "Bo'sh reja saqlanmaydi (400)")
D3 = J(OQ.post(P + f"/decks/{did}/build", json={}))
ok(D3["status"] == "tayyor" and D3["slides"] >= 6, f"PPTX yaratildi: {D3['slides']} slayd")
r = OQ.get(P + f"/decks/{did}/download")
ok(r.status_code == 200 and "presentationml" in r.headers.get("content-type", "") and ".pptx" in r.headers.get("content-disposition", ""), "Yuklab olish: .pptx")
info = pptx_info(r.content)
ok(info["n"] == D3["slides"] and "RAHMAT" in info["last"] and info["pics"] >= 1, f"Fayl: {info['n']} slayd, rasm bor, oxirida rahmat slaydi")
ok(not info["small"], "Fayl: 14 pt dan kichik matn yo'q")
ok("IQTISODIYOT NAZARIYASI" in info["texts"][0] and "Talab va taklif: bozor muvozanati" in info["texts"][0], "Titul tahrirlangan sarlavha bilan")
ok(any("Javob" in t and "P = 16" in t for t in info["texts"]), "Ishlangan misol slaydi: «Javob» bloki")

T = J(OQ.post(P + "/decks/text", json={"text": "# Pul va kredit\nPul — umumiy ekvivalent vazifasini bajaruvchi maxsus tovar. " * 4 + "\n- Muomala vositasi\n- Qiymat o'lchovi\n- Jamg'arish vositasi",
                                       "subject": "Moliya", "slides": 8}))
ok(T["source_kind"] == "txt" and T["outline"]["slides"] and T["target"] == 8, f"Matndan reja: {len(T['outline']['slides'])} slayd")
Pd = J(OQ.post(P + "/decks", params={"name": "rasmlar.pdf"}, content=make_pdf(), headers={"Content-Type": "application/octet-stream"}))
ok(Pd["source_kind"] == "pdf" and Pd["images"] == 2 and sum(1 for s in Pd["outline"]["slides"] if s["type"] == "image") == 2, "PDF (rasmli): 2 ta rasm slaydi")
Pb = J(OQ.post(P + f"/decks/{Pd['id']}/build", json={}))
ok(pptx_info(OQ.get(P + f"/decks/{Pd['id']}/download").content)["pics"] == 2, "PDF rasmlari .pptx da")

print("— 4. HTTP: cheklovlar —")
for raw, nm, code in ((b"\x89PNG\r\n\x1a\n" + b"\x00" * 64, "rasm.png", 415), (b"MZ\x90\x00" + b"\x00" * 64, "dastur.docx", 415),
                      (b"PK\x03\x04" + b"\x00" * 64, "arxiv.docx", 415), (b"", "bosh.txt", 400)):
    ok(OQ.post(P + "/decks", params={"name": nm}, content=raw, headers={"Content-Type": "application/octet-stream"}).status_code == code, f"{nm} → {code}")
ok(OQ.post(P + "/decks", params={"name": "katta.txt"}, content=b"a" * (20 * 1024 * 1024 + 10), headers={"Content-Type": "application/octet-stream"}).status_code == 413, "20 MB dan katta → 413")
ok(OQ.post(P + "/decks/text", json={"text": "qisqa"}).status_code == 400, "Juda qisqa matn → 400")
lim = J(OQ.get(P + "/meta"))
need = lim["limit"] - lim["used"]
day = CLK.today().isoformat()
for _ in range(max(0, need)):
    w("INSERT INTO pres_gen(user_id,deck_id,day,at,engine,ok,ms,err) VALUES(?,0,?,?,'test',1,0,'test-limit')", (OQ_ID, day, CLK.now_iso()))
r = OQ.post(P + "/decks/text", json={"text": "Bozor iqtisodiyoti asoslari haqida batafsil ma'ruza matni. " * 3})
ok(r.status_code == 429 and "cheklov" in r.text, f"Kunlik cheklov ({lim['limit']} ta) → 429")
ok(OQ.post(P + f"/decks/{did}/regenerate", json={}).status_code == 429, "Qayta tuzish ham kunlik cheklovga kiradi → 429")
ok(OQ.post(P + f"/decks/{did}/build", json={}).status_code == 200, "PPTX yaratish cheklovga kirmaydi")
w("DELETE FROM pres_gen WHERE err='test-limit'")
R = J(OQ.post(P + f"/decks/{T['id']}/regenerate", json={"slides": 10}))
ok(R["target"] == 10 and R["outline"]["slides"], "Cheklov bo'shagach — rejani qayta tuzish ishlaydi")

print("— 5. HTTP: kafedra va begona taqdimotlar —")
L = J(KAF.get(P + "/decks", params={"scope": "dept"}))
ok(L["scope"] == "dept" and any(x["id"] == did for x in L["items"]), f"Kafedra mudiri (#{KAF_ID}): o'z kafedrasi o'qituvchisi taqdimotini ko'radi")
V = J(KAF.get(P + f"/decks/{did}"))
ok(not V["can_edit"] and V["outline"], "Kafedra mudiri: ko'rish — tahrirsiz")
ok(KAF.get(P + f"/decks/{did}/download").status_code == 200, "Kafedra mudiri: yuklab oladi")
ok(KAF.post(P + f"/decks/{did}/outline", json={"outline": o}).status_code == 403 and KAF.post(P + f"/decks/{did}/build", json={}).status_code == 403
   and KAF.post(P + f"/decks/{did}/delete", json={}).status_code == 403, "Kafedra mudiri: tahrirlash / yaratish / o'chirish — 403")
ok(not any(x["id"] == did for x in J(KAF2.get(P + "/decks", params={"scope": "dept"}))["items"]), f"Boshqa kafedra (#{KAF2_ID}): ro'yxatda yo'q")
ok(KAF2.get(P + f"/decks/{did}").status_code == 403 and KAF2.get(P + f"/decks/{did}/download").status_code == 403, "Boshqa kafedra: ko'rish va yuklab olish — 403")
ok(J(OQ.get(P + "/decks", params={"scope": "dept"}))["scope"] == "mine", "O'qituvchi «dept» so'rasa ham faqat o'zinikini ko'radi")
mine = J(OQ.get(P + "/decks"))["items"]
ok(any(x["id"] == did for x in mine) and all(True for x in mine), f"Mening taqdimotlarim: {len(mine)} ta")
ok(q1("SELECT COUNT(*) FROM audit_log WHERE resource='presentations' AND action LIKE 'taqdimot: pptx yaratildi%' AND user_id=? AND ts>=?", (OQ_ID, T0)) >= 2, "Audit: pptx yaratilishi yozildi")
ok(q1("SELECT COUNT(*) FROM audit_log WHERE resource='presentations' AND action='taqdimot: begona taqdimot' AND allowed=0 AND ts>=?", (T0,)) >= 2, "Audit: begona taqdimotga urinish yozildi")
J(OQ.post(P + f"/decks/{Pd['id']}/delete", json={}))
ok(OQ.get(P + f"/decks/{Pd['id']}").status_code == 404 and not (dir_.parent / str(Pd["id"])).exists(), "O'chirish: taqdimot va fayllari o'chdi")
print(f"Hammasi o'tdi: {N[0]} ta tekshiruv.")
