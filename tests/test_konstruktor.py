"""Konstruktor (A versiya, static/konstruktor.js) va muharrirning «Rise ko'rinishi» (static/kurs.js) — server ma'lumoti tayyorlanadi,
brauzer qismi tools/konstruktor_check.js (PW va CHROME berilganda). Fayllar: ma'ruza (Word), YouTube havola, ✅ belgili test (Word).

Ishga tushirish:  PW=… CHROME=… python tests/run_all.py --only konstruktor
DIQQAT: bazani o'zgartiradi — PRODUCTION'da ishlatilmaydi.
"""
import io, os, re, shutil, sqlite3, subprocess, sys
from pathlib import Path
import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
B = os.environ.get("ISFT_TEST_URL", "http://127.0.0.1:8000")
DBP = Path(os.environ.get("ISFT_CORE_DB") or ROOT / "data" / "jarvis.db")
PW = re.search(r'DEMO_PASSWORD = os.getenv\("ISFT_CORE_DEMO_PASSWORD", "([^"]+)"\)', (ROOT / "app" / "rbac.py").read_text()).group(1)
fails = []
def ok(cond, msg):
    print(("  ✓ " if cond else "  ✗ ") + msg)
    if not cond: fails.append(msg)
def q(sql, a=()):
    con = sqlite3.connect(DBP); con.row_factory = sqlite3.Row
    try: return [dict(r) for r in con.execute(sql, a).fetchall()]
    finally: con.close()

print("== 1. Statik: fayllar, sintaksis")
node = shutil.which("node")
for f in ("static/konstruktor.js", "static/kurs.js", "static/dars.js", "tools/konstruktor_check.js", "tools/kx_materials_assert.js", "tools/bulk_upload_check.js"):
    if node:
        r = subprocess.run([node, "--check", str(ROOT / f)], capture_output=True, text=True)
        ok(r.returncode == 0, f"node --check {f}" + ("" if r.returncode == 0 else ": " + r.stderr.strip()[:200]))
idx = (ROOT / "static" / "index.html").read_text()
ok(idx.index('src="dars.js"') < idx.index('src="konstruktor.js"'), "index.html: konstruktor.js — dars.js dan keyin")
kxjs, djs, dcss = [(ROOT / "static" / f).read_text() for f in ("konstruktor.js", "dars.js", "dars.css")]
ok(".kx,.ds-grid.a,.kxb{--brand-fill:#7837a8" in dcss and "ds-grid ${A ?" in djs, "dars.css/dars.js: Konstruktor va dars qatorlarida asosiy tugmalar binafsha (CSS o'zgaruvchisi shu ko'rinishlarga cheklangan)")
ok("dsProgress" in djs and "Mavzu nomi kiritilmagan" in djs and '"Eksport"' not in djs.replace('"Eksport:', ''), "dars.js: 3 qadamli tayyorlik (Material · Video · Paket), nomi yo'q dars matni, «Eksport» atamasi yo'q")
ok("kxbMatch" in kxjs and "kxbParse" in kxjs and "/captions/auto" in kxjs and "kx-more" in kxjs and "window.scrollTo(0, 0)" in kxjs, "konstruktor.js: ko'p fayl moslashtirish, avtomatik subtitr endpointi, «Batafsil», sahifa tepaga qaytadi")
kjs = (ROOT / "static" / "kurs.js").read_text()
ok("kuUi()" in kjs and "ku-rise" in kjs and "kuQuickBar" in kjs and "kuPublish" in kjs, "kurs.js: Rise ko'rinishi (kuUi), tez qo'shish paneli, «Tayyor» oynasi (kuPublish)")
ok('id="kuDone"' in kjs and 'id="kxPub"' in kjs and "Nashr qilish →" not in kjs and "KU_THUMB" in kjs and 'data-dev="' in kjs, "kurs.js: yagona «Tayyor» tugmasi, blok eskizlari (KU_THUMB), ko'rish qurilma almashtirgichi")
ok('"#7837A8"' in (ROOT / "app" / "kurs.py").read_text(), "kurs.py: NEXTID binafsha rangi palitrada")

print("== 2. Ma'lumot: dars uchun materiallar")
head_u = q("SELECT id FROM users WHERE role='masofaviy' AND active=1 ORDER BY id LIMIT 1")[0]["id"]
c = httpx.Client(base_url=B, timeout=300)
ok(c.post("/api/login", json={"user_id": head_u, "password": PW}).status_code == 200, "Kirish: masofaviy ta'lim bo'limi boshlig'i")
cid = q("SELECT id FROM dl_courses ORDER BY id DESC LIMIT 1")[0]["id"]
KEY = 7
U = f"/api/paket/courses/{cid}/topics/{KEY}"
import docx
d = docx.Document(); d.add_paragraph("Mavzu: Talab va taklif"); d.add_paragraph("Reja:")
for i, t in enumerate(["Talab qonuni", "Taklif qonuni", "Bozor muvozanati"], 1): d.add_paragraph(f"{i}. {t}")
for _ in range(4): d.add_paragraph("Talab — iste'molchilarning ma'lum narxda sotib olishga tayyor bo'lgan tovar miqdori. Narx oshsa, talab miqdori kamayadi. " * 2)
b = io.BytesIO(); d.save(b)
r = c.post(U + "/upload", params={"name": "maruza.docx", "as": "matn"}, content=b.getvalue())
ok(r.status_code == 200, f"Ma'ruza Word yuklandi ({r.status_code} {r.text[:120]})")
r = c.post(U + "/video", json={"url": "https://youtu.be/dQw4w9WgXcQ"})
ok(r.status_code == 200, "YouTube havola saqlandi")
test_docx = ROOT / "tests" / "fixtures" / "test_import" / "test.docx"
ok(test_docx.is_file(), "✅ belgili test namunasi (tests/fixtures/test_import/test.docx)")

print("== 3. Brauzer: Konstruktor va Rise ko'rinishi")
pwj, chrome = os.environ.get("PW"), os.environ.get("CHROME")
if not (pwj and chrome and node):
    print("  – PW/CHROME berilmagan — brauzer sinovi o'tkazib yuborildi")
else:
    env = dict(os.environ, B=B, KX_UID=str(head_u), KX_PW=PW, KX_CID=str(cid), KX_KEY=str(KEY), KX_TEST=str(test_docx) if test_docx.is_file() else "",
               OUT=os.environ.get("KX_OUT") or str(Path(os.environ.get("TMPDIR", "/tmp")) / "isft_konstruktor"))
    rr = subprocess.run([node, str(ROOT / "tools" / "konstruktor_check.js")], cwd=ROOT, env=env, capture_output=True, text=True, timeout=600)
    for ln in (rr.stdout + rr.stderr).splitlines():
        s = ln.strip()
        if s.startswith("✓"): ok(True, "[brauzer] " + s[1:].strip())
        elif s.startswith("✗"): ok(False, "[brauzer] " + s[1:].strip())
    ok(rr.returncode == 0, f"tools/konstruktor_check.js chiqish kodi 0 ({rr.returncode})" + ("" if rr.returncode == 0 else ":\n" + "\n".join((rr.stdout + rr.stderr).splitlines()[-12:])))

print("== 4. «Ko'p faylni yuklash»: moslashtirish (node) va 3 ta Word bilan yuklash")
import tempfile, docx as _docx
bkdir = Path(tempfile.mkdtemp(prefix="isft_bulk_"))
for fn, mv in (("1-ma'ruza.docx", "Matritsa"), ("L3.docx", "Limit"), ("maruza_08.docx", "Hosila"), ("izoh.docx", "Izoh")):
    dd = _docx.Document(); dd.add_paragraph(f"Mavzu: {mv}"); dd.add_paragraph("Reja:")
    for i, t in enumerate(["Birinchi savol", "Ikkinchi savol"], 1): dd.add_paragraph(f"{i}. {t}")
    for _ in range(3): dd.add_paragraph(f"{mv} — qisqa namunaviy ma'ruza matni, sinov uchun. " * 3)
    dd.save(bkdir / fn)
if test_docx.is_file(): shutil.copy(test_docx, bkdir / "L2 test.docx")
(bkdir / "L9.pptx").write_bytes(b"bu pptx emas" * 20)      # buzuq fayl — server rad etadi, xato matni o'qiladi
if node:
    env2 = dict(os.environ, B=B, KX_UID=str(head_u), KX_PW=PW, KX_CID=str(cid), BK_DIR=str(bkdir),
                OUT=os.environ.get("KX_OUT") or str(Path(os.environ.get("TMPDIR", "/tmp")) / "isft_konstruktor"))
    if not (pwj and chrome): env2.pop("PW", None); env2.pop("CHROME", None)
    rb = subprocess.run([node, str(ROOT / "tools" / "bulk_upload_check.js")], cwd=ROOT, env=env2, capture_output=True, text=True, timeout=600)
    nb = 0
    for ln in (rb.stdout + rb.stderr).splitlines():
        s_ = ln.strip()
        if s_.startswith("✓"): ok(True, "[bulk] " + s_[1:].strip()); nb += 1
        elif s_.startswith("✗"): ok(False, "[bulk] " + s_[1:].strip())
    ok(rb.returncode == 0 and nb >= 25, f"tools/bulk_upload_check.js chiqish kodi 0, {nb} ta tekshiruv ({rb.returncode})" + ("" if rb.returncode == 0 else ":\n" + "\n".join((rb.stdout + rb.stderr).splitlines()[-12:])))
shutil.rmtree(bkdir, ignore_errors=True)

print()
if fails:
    print(f"XATO: {len(fails)} ta tekshiruv o'tmadi"); sys.exit(1)
print("Hammasi o'tdi")
