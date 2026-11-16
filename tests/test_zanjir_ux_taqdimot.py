"""«Taqdimot» sahifasi — o'qituvchi UX tuzatishlari (zanjir tuzatish bosqichi, B agenti): brauzer regressiya testi.

Ishga tushirish:  python tests/run_all.py --only zanjir_ux_taqdimot
   (yoki: ISFT_TEST_URL=http://127.0.0.1:8000 ISFT_CORE_DB=data/jarvis.db PW=... CHROME=... .venv/bin/python tests/test_zanjir_ux_taqdimot.py)
1) Statik tekshiruv: node --check, index.html ulanish tartibi, app.js go() ilgagi, taqdimot.js dagi asosiy belgilar.
2) Serverda o'qituvchi tanlanadi (o'z fanlari va ≥3 darsi bor; boshqa to'plamlar bilan to'qnashmaslik uchun OXIRGI shunday o'qituvchi),
   keyin tools/zanjir_ux_taqdimot.js ishga tushiriladi (1440 va 390 px, yorug' va qorong'i, 390×380 va 320×568 kichik ekranlar) — barcha UX tuzatishlar
   (yuborish dialogi versiyasi darsdan, boshqa taqdimot ogohlantirishi, eskirgan tab, mobil kartochka ro'yxat, 44 px, Esc/fokus, chip wrap, 320 px tugma,
   scrollWidth=clientWidth, ARIA, kontrast, saqlanmagan tahrir, aria-busy). Backend maydonlari bo'lmasa ham javoblar shartnoma bo'yicha to'ldiriladi (page.route).
DIQQAT: server bazasiga taqdimotlar yozadi (testdan keyin o'chiriladi) — PRODUCTION'da ishlatilmaydi.
"""
import os, shutil, sqlite3, subprocess, sys
from pathlib import Path
import httpx

ROOT = Path(__file__).resolve().parent.parent
DB = Path(os.environ.get("ISFT_CORE_DB") or ROOT / "data" / "jarvis.db")
B = os.environ.get("ISFT_TEST_URL", "http://127.0.0.1:8000")
PW = "Isft2026"
N = [0]


def ok(cond, msg):
    N[0] += 1
    print(("  ✓ " if cond else "  ✗ XATO: ") + msg)
    if not cond:
        sys.exit(1)


def q(sql, args=()):
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True, timeout=30)
    try: return con.execute(sql, args).fetchall()
    finally: con.close()


print("— 1. Statik tekshiruv —")
node, pwj, chrome = shutil.which("node"), os.environ.get("PW"), os.environ.get("CHROME")
for f in ("static/taqdimot.js", "tools/zanjir_ux_taqdimot.js", "static/app.js"):
    if node:
        r = subprocess.run([node, "--check", str(ROOT / f)], capture_output=True, text=True)
        ok(r.returncode == 0, f"node --check {f}")
js = (ROOT / "static" / "taqdimot.js").read_text()
app = (ROOT / "static" / "app.js").read_text()
css = (ROOT / "static" / "taqdimot.css").read_text()
ok("function go(v) {\n  if (window.tqBeforeLeave && window.tqBeforeLeave(v) === false) return;" in app,
   "app.js go(): birinchi qatorda tqBeforeLeave ilgagi (saqlanmagan tahrir)")
ok("beforeunload" in js and "sessionStorage" in js and "#taqdimot/" in js, "taqdimot.js: beforeunload va yangilangandan keyin tiklash (sessionStorage + xesh)")
ok("dl_courses" not in js and "AI siz (shablon)" not in js, "taqdimot.js: o'qituvchiga texnik matn (dl_courses, «AI siz (shablon)») ko'rsatilmaydi")
ok("lesson_sent_version" in js and "changed_since_send" in js and "doc_topic_no" in js and "aria-disabled" in js, "taqdimot.js: shartnoma maydonlari va aria-disabled ishlatiladi")
ok(".tq-t.stack" in css and "max-width:760px" in css and "min-height:44px" in css and "position:sticky" in css, "taqdimot.css: mobil kartochka ro'yxat, 44 px va sticky tugmalar qoidalari")
ok('role="alert"' in js and 'role="tablist"' in js and 'role="tab"' in js and "aria-busy" in js, "taqdimot.js: role=alert, tablist/tab, aria-busy")

print("— 2. Brauzer —")
if not (pwj and chrome and node):
    print("  – PW/CHROME berilmagan — brauzer sinovi o'tkazib yuborildi")
else:
    rows = q("SELECT u.id, u.teacher_id FROM users u WHERE u.role='oqituvchi' AND COALESCE(u.active,1)=1 AND u.teacher_id IS NOT NULL ORDER BY u.id")
    cand = None
    for uid_, tid in reversed(rows):
        cs = q("SELECT id FROM dl_courses WHERE teacher_id=?", (tid,))
        if not cs: continue
        c = httpx.Client(base_url=B, timeout=120)
        r = c.post("/api/login", json={"user_id": uid_, "password": PW})
        if r.status_code != 200: continue
        items = c.get("/api/taqdimot/lessons").json().get("items", [])
        for co in items:
            ls = [l for l in co["lessons"] if l["kind"] == "maruza"]
            if len(ls) >= 3 and co.get("course") and co.get("direction"):
                cand = (uid_, co, ls); break
        if cand: break
    ok(cand is not None, "Darslari bor o'qituvchi topildi")
    uid_, co, ls = cand
    ok(len(ls) >= 3, f"O'qituvchi #{uid_}: fan #{co['id']} ({len(ls)} ta ma'ruza)")
    outdir = os.environ.get("ZJ_OUT") or str(Path(os.environ.get("TMPDIR", "/tmp")) / "isft_zanjir_ux_taqdimot")
    env = dict(os.environ, B=B, PW_=PW, T_UID=str(uid_), CID=str(co["id"]), KURS=str(co["course"]), DIRN=co["direction"], LK0=str(ls[0]["key"]), LK1=str(ls[1]["key"]), LK2=str(ls[2]["key"]), OUT=outdir)
    rr = subprocess.run([node, str(ROOT / "tools" / "zanjir_ux_taqdimot.js")], cwd=ROOT, env=env, capture_output=True, text=True, timeout=1500)
    nb = 0
    for ln in (rr.stdout + rr.stderr).splitlines():
        s_ = ln.strip()
        if s_.startswith("✓"): ok(True, "[brauzer] " + s_[1:].strip()); nb += 1
        elif s_.startswith("✗"): ok(False, "[brauzer] " + s_[1:].strip())
    ok(rr.returncode == 0 and nb >= 100, f"tools/zanjir_ux_taqdimot.js chiqish kodi 0, {nb} ta tekshiruv · skrinshotlar: {outdir}")
print(f"Hammasi o'tdi: {N[0]} ta tekshiruv.")
