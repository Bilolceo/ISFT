"""O'quv paketi + tashqi vositalar (app/office_tools.py): LibreOffice (eski .ppt → .pptx, .pptx → PDF slayd rasmlari, eski .doc → .docx)
va Tesseract OCR (skaner qilingan ma'ruza PDF → sahifa rasmlari galereyasi + OCR matni), «video kamida N% ko'rilsin» sozlamasi.

Asosiy test serveri (tests/run_all.py) vositalarsiz ishlaydi (ISFT_CORE_OFFICE=0, ISFT_CORE_OCR=0) — u yerda eski formatlar aniq xabar bilan
rad etilishi tekshiriladi. Vositali qism uchun shu fayl o'sha ma'lumotlar katalogida o'z uvicorn serverini vositalar YOQIQ holda ishga tushiradi.
Mashinada soffice yoki tesseract bo'lmasa — vositali qism o'tkazib yuboriladi.

Ishga tushirish:  python tests/run_all.py --only paket_office
"""
import io, json, os, re, socket, sqlite3, subprocess, sys, tempfile, time, zipfile
from pathlib import Path
import httpx
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
B = os.environ.get("ISFT_TEST_URL", "http://127.0.0.1:8000")
DBP = Path(os.environ.get("ISFT_CORE_DB") or ROOT / "data" / "jarvis.db")
PW = re.search(r'DEMO_PASSWORD = os.getenv\("ISFT_CORE_DEMO_PASSWORD", "([^"]+)"\)', (ROOT / "app" / "rbac.py").read_text()).group(1)
P = "/api/paket"
fails = []
def ok(cond, msg):
    print(("  ✓ " if cond else "  ✗ ") + msg)
    if not cond: fails.append(msg)
def q(sql, a=()):
    con = sqlite3.connect(DBP); con.row_factory = sqlite3.Row
    try: return [dict(r) for r in con.execute(sql, a).fetchall()]
    finally: con.close()
def uid(role): return q("SELECT id FROM users WHERE role=? ORDER BY id LIMIT 1", (role,))[0]["id"]
def login(base, u):
    c = httpx.Client(base_url=base, timeout=600)
    r = c.post("/api/login", json={"user_id": u, "password": PW}); assert r.status_code == 200, r.text
    return c

from app import office_tools as OT
env_tools = {k: v for k, v in os.environ.items() if k not in ("ISFT_CORE_OFFICE", "ISFT_CORE_OCR")}
os.environ.pop("ISFT_CORE_OFFICE", None); os.environ.pop("ISFT_CORE_OCR", None)     # shu jarayon (fikstura yasash) uchun — yoqiq
HAVE = bool(OT.soffice()) and bool(OT.tesseract() and OT.ocr_lang())

def font(n):
    for p in ("/System/Library/Fonts/Supplemental/Times New Roman.ttf", "/System/Library/Fonts/Supplemental/Arial.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf"):
        try: return ImageFont.truetype(p, n)
        except OSError: pass
    return ImageFont.load_default(size=n)

LINES = ["Matritsa haqida umumiy tushuncha", "Sistemalarni modellashtirishda matritsalar algebrasi degan tushuncha muhim",
         "ahamiyatga ega. Rejalashtirish muammolari, yalpi mahsulot va boshqa masalalar", "hamda ularda kompyuterlarni qo'llash matritsalar algebrasini qarashga olib keladi."]
def page_img(i):
    im = Image.new("RGB", (1654, 1170), "white"); d = ImageDraw.Draw(im)
    d.text((120, 90), f"{i}-sahifa. Matritsalar ustida amallar", fill="black", font=font(44))
    for k, t in enumerate(LINES): d.text((120, 220 + k * 70), t, fill="black", font=font(36))
    return im
def scanned_pdf(n=2):
    ims = [page_img(i) for i in range(1, n + 1)]
    b = io.BytesIO(); ims[0].save(b, "PDF", save_all=True, append_images=ims[1:], resolution=150); return b.getvalue()
def make_pptx(n=3):
    from pptx import Presentation
    pr = Presentation()
    for i in range(1, n + 1):
        s = pr.slides.add_slide(pr.slide_layouts[1]); s.shapes.title.text = f"{i}-slayd: Matritsa"
        s.placeholders[1].text = "Satr va ustunlar\nMatritsalarni qo'shish"
        s.notes_slide.notes_text_frame.text = f"{i}-slayd izohi"
    b = io.BytesIO(); pr.save(b); return b.getvalue()
def make_docx():
    import docx
    d = docx.Document(); d.add_heading("1-MAVZU: MATRITSA VA UNING USTIDA AMALLAR", 1)
    for _ in range(4): d.add_paragraph(" ".join(LINES))
    b = io.BytesIO(); d.save(b); return b.getvalue()

# =============================================================================================
print("== 1. Asosiy server (vositalarsiz): eski formatlar — aniq xabar")
teach = login(B, uid("oqituvchi"))
tid = q("SELECT teacher_id FROM users WHERE id=?", (uid("oqituvchi"),))[0]["teacher_id"]
cid = q("SELECT id FROM dl_courses WHERE teacher_id=? ORDER BY id DESC LIMIT 1", (tid,))[0]["id"]
NO = 9          # boshqa to'plamlar ishlatmaydigan dars
U = f"{P}/courses/{cid}/topics/{NO}"
meta = teach.get(P + "/meta").json()
ok(meta.get("tools") == {"office": False, "ocr": False, "ocr_lang": None}, f"/meta: tools — vositalar o'chiq ({meta.get('tools')})")
if HAVE:
    PPT = OT.convert(make_pptx(), "pptx", "ppt"); DOC = OT.convert(make_docx(), "docx", "doc")
    r = teach.post(U + "/upload", params={"name": "eski.ppt"}, content=PPT)
    ok(r.status_code == 415 and "LibreOffice" in r.text and ".pptx" in r.text, f"Vositasiz: .ppt — 415, «LibreOffice o'rnatilmagan … .pptx» ({r.status_code} {r.text[:120]})")
    r = teach.post(U + "/upload", params={"name": "eski.doc"}, content=DOC)
    ok(r.status_code == 415 and "Word (.doc)" in r.text, f"Vositasiz: .doc — 415 ({r.status_code} {r.text[:120]})")
    r = teach.post(U + "/upload", params={"name": "skaner.pdf", "as": "matn"}, content=scanned_pdf(1))
    ok(r.status_code == 415 and "OCR" in r.text, f"Vositasiz: skaner PDF ma'ruza — 415 «OCR o'rnatilmagan» ({r.status_code} {r.text[:120]})")
r = teach.post(U + "/upload", params={"name": "x.xls"}, content=b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\0" * 2000)
ok(r.status_code == 415, f"Noma'lum OLE (Excel va h.k.) — 415 ({r.status_code})")

# --- video_min sozlamasi (vositasiz ham)
st = teach.get(U).json()["settings"]
base = {k: st[k] for k in ("mode", "completion", "mastery", "layout", "video_source", "quiz_n", "attempts", "shuffle", "show_feedback", "blocks")}
r = teach.post(U + "/settings", json={**base, "video_min": 150})
ok(r.status_code == 422, f"video_min > 100 — 422 ({r.status_code})")
r = teach.post(U + "/settings", json={**base, "video_min": 80})
ok(r.status_code == 200 and teach.get(U).json()["settings"]["video_min"] == 80, "video_min = 80 saqlandi")

# =============================================================================================
if not HAVE:
    print("  – soffice / tesseract yo'q — vositali qism o'tkazib yuborildi")
else:
    print("== 2. Vositali server: .ppt → .pptx + PDF slaydlar, .doc → .docx, skaner PDF → OCR")
    s_ = socket.socket(); s_.bind(("127.0.0.1", 0)); port = s_.getsockname()[1]; s_.close()
    log = open(Path(tempfile.gettempdir()) / f"paket_office_{port}.log", "w")
    srv = subprocess.Popen([sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(port)], cwd=ROOT, env=env_tools,
                           stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
    B2 = f"http://127.0.0.1:{port}"
    try:
        for _ in range(120):
            try:
                if httpx.get(B2 + "/healthz", timeout=3).status_code == 200: break
            except httpx.HTTPError: pass
            time.sleep(1)
        t2 = login(B2, uid("oqituvchi"))
        tools = t2.get(P + "/meta").json().get("tools") or {}
        ok(tools.get("office") and tools.get("ocr"), f"/meta: tools — office va ocr yoqiq ({tools})")
        r = t2.post(U + "/upload", params={"name": "1-MA'RUZA.ppt"}, content=PPT); j = r.json() if r.status_code == 200 else {}
        ok(r.status_code == 200 and j.get("as") == "taqdimot" and j.get("converted") and j.get("rendered") and j.get("pages") == 3,
           f".ppt → taqdimot: .pptx ga o'girildi va PDF slaydlarga chizildi ({r.status_code} {r.text[:200]})")
        rd = t2.get(U).json()["ready"]["slides"]
        ok(rd["src"] == "pdf" and rd["n"] == 3 and rd["display"] == "images" and rd["file"] and rd["pdf"],
           f"Tayyorgarlik: slaydlar PDF rasmlaridan (3), .pptx va .pdf yuklab olish uchun ({rd})")
        r = t2.post(U + "/upload", params={"name": "maruza.doc"}, content=DOC); j = r.json() if r.status_code == 200 else {}
        ok(r.status_code == 200 and j.get("as") == "matn" and j.get("kind") == "docx" and j.get("chars", 0) > 200, f".doc → .docx → ma'ruza matni ({r.status_code} {r.text[:160]})")
        r = t2.post(U + "/upload", params={"name": "skaner.pdf", "as": "matn"}, content=scanned_pdf(2)); j = r.json() if r.status_code == 200 else {}
        ok(r.status_code == 200 and j.get("ocr") == 2 and j.get("chars", 0) > 100, f"Skaner PDF → OCR (2 sahifa) ({r.status_code} {r.text[:160]})")
        ok(t2.get(U).json()["ready"]["text"].get("ocr") is True, "ready.text.ocr = true")
        r = t2.post(U + "/build", json={"mode": "xapi"}); ok(r.status_code == 200, f"Yig'ish (xAPI) ({r.status_code} {r.text[:120]})")
        pid = r.json()["package"]["id"]
        z = zipfile.ZipFile(io.BytesIO(t2.get(f"{P}/packages/{pid}/download").content))
        c = json.loads(z.read("content.json")); bl = c["blocks"]
        lec = [b for b in bl if b["type"] == "slides" and b["title"] == "Ma'ruza matni"]
        ok(lec and len(lec[0]["slides"]) == 2 and all(s["image"] in z.namelist() for s in lec[0]["slides"]) and "Matritsa" in lec[0]["slides"][0].get("text", ""),
           "Paket: skaner ma'ruza — 2 sahifali galereya, OCR matni har sahifada")
        ok(not any(b["type"] in ("text", "plan") for b in bl), "OCR ma'ruzada ko'rinadigan matn bloki va reja chiqmaydi (sahifa rasmi — asl)")
        tq = [b for b in bl if b["type"] == "slides" and b["title"] == "Taqdimot"]
        ok(tq and len(tq[0]["slides"]) == 3 and tq[0]["slides"][0]["notes"] == "1-slayd izohi" and "Matritsa" in tq[0]["slides"][0].get("text", ""),
           "Paket: taqdimot — PDF rasmlari + .pptx izohlari + slayd matni")
        ok(tq and tq[0].get("file_name") == "1-MA'RUZA.pptx" and tq[0].get("pdf_name") == "1-MA'RUZA.pdf" and tq[0].get("file_size", 0) > 0,
           f"Paket: yuklab olish kartochkasida asl nomlar va hajm ({tq and {k: tq[0].get(k) for k in ('file_name', 'pdf_name', 'file_size')}})")
        ok(c["tracking"].get("video_min") == 0.8, f"Paket: tracking.video_min = 0.8 ({c['tracking']})")
        st2 = t2.get(U).json()["settings"]; base2 = {k: st2[k] for k in base}
        t2.post(U + "/settings", json={**base2, "video_min": 0})
        r = t2.post(U + "/build", json={"mode": "xapi"}); c2 = json.loads(zipfile.ZipFile(io.BytesIO(t2.get(f"{P}/packages/{r.json()['package']['id']}/download").content)).read("content.json"))
        ok("video_min" not in c2["tracking"], "video_min = 0 — paketda talab yo'q")
    finally:
        srv.terminate()
        try: srv.wait(10)
        except subprocess.TimeoutExpired: srv.kill()

print(f"\nNatija: {'Hammasi o`tdi' if not fails else str(len(fails)) + ' ta xato'}")
sys.exit(1 if fails else 0)
