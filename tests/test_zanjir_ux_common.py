"""«Taqdimot → Studiya → Masofaviy bo'lim» zanjirining UMUMIY interfeys qismi (static/paket.js, dars.js, lesson_picker.js, dars_card.js, konstruktor.js; tools/zanjir_ux_common.js).

Ishga tushirish:  python tests/run_all.py --only zanjir_ux_common
   (yoki: ISFT_TEST_URL=http://127.0.0.1:8000 ISFT_CORE_DB=data/jarvis.db PW=… CHROME=… .venv/bin/python tests/test_zanjir_ux_common.py)
1) Statik: sintaksis (node --check), toast z-index modallardan yuqori, pkModal infratuzilmasi (inert, Tab tuzog'i, document darajasidagi Esc, busy, bg mousedown+mouseup),
   pkModalError / pkFail / hash tiklash / kod bilan qidirish kodi, skriptlar tartibi.
2) Brauzer (PW va CHROME berilganda): 1440 va 390 px, yorug' va qorong'i — modal (Tab 30 marta ichida, Esc, fokus qaytishi, toast ustida), tab ARIA, Fanlar daraxti (fokus, aria-live,
   hash tiklash, kod bilan qidirish, bitta fan, fani yo'q, limit, xato + qayta urinish, holat chiplari, tugma nomlari), lpPicker (strelkalar, aria-live), dars kartochkasi
   (scrollTop=0, ikki marta ochilmaslik, tasdiq, jurnal guruhlash, joyida yangilash), tegish maydonlari >= 44 px, .ds-prg 320/375 px.
DIQQAT: server bazasiga matn/fayl yuklaydi — PRODUCTION'da ishlatilmaydi.
"""
import io, os, re, shutil, sqlite3, subprocess, sys
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


def q1(sql, args=()):
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True, timeout=30)
    try:
        r = con.execute(sql, args).fetchall(); return r[0][0] if r else None
    finally: con.close()


def S(uid):
    c = httpx.Client(base_url=B, timeout=300)
    r = c.post("/api/login", json={"user_id": uid, "password": PW}); assert r.status_code == 200, f"login {uid}: {r.status_code} {r.text}"
    return c


def uid(role):
    r = q1("SELECT id FROM users WHERE role=? AND COALESCE(active,1)=1 ORDER BY id LIMIT 1", (role,)); assert r, f"{role} akkaunti yo'q"; return r


def src(f): return (ROOT / "static" / f).read_text()


print("— 1. Statik tekshiruvlar —")
node = shutil.which("node")
for f in ("static/paket.js", "static/dars.js", "static/lesson_picker.js", "static/dars_card.js", "static/konstruktor.js", "tools/zanjir_ux_common.js"):
    if node:
        r = subprocess.run([node, "--check", str(ROOT / f)], capture_output=True, text=True)
        ok(r.returncode == 0, f"node --check {f}" + ("" if r.returncode == 0 else ": " + r.stderr.strip()[:200]))
st, pk, ds, lp, dc = src("style.css"), src("paket.js"), src("dars.js"), src("lesson_picker.js"), src("dars_card.js")
z = [int(m) for m in re.findall(r"\.toast\{[^}]*?z-index:(\d+)", st)]
ok(z and min(z) >= 1100, f"Toast z-index modallardan (.pk-modal-bg 80, .st-modal-bg 1000) yuqori: {z}")
ok(re.search(r"\.pk-modal-bg\{[^}]*z-index:80", src("paket.css")), ".pk-modal-bg z-index 80 (toast 1100+ undan yuqori)")
ok(all(k in pk for k in ("document.addEventListener(\"keydown\"", "inert", "PK_MODALS", "preventScroll", "pkModalError", "pkModalBusy", "pkFail", "MutationObserver")), "paket.js: pkModal — Tab tuzog'i, document Esc, inert, busy, pkModalError, pkFail")
ok("mousedown" in pk and "mouseup" in pk and "Date.now() - opened > 400" in pk, "Orqa fonni bosish — mousedown va mouseup ikkalasi fonda (+ochilgach 0,4 s himoya)")
ok('role="tablist"' in pk and "aria-controls" in pk and 'role="tabpanel"' in pk and "ArrowRight" in pk and '"Home"' in pk, "Tablar: aria-controls, tabpanel, ←/→, Home/End")
ok("#fanlar=" in ds and "history.replaceState" in ds and "dsHashLoad" in ds and "dsAnnounce" in ds and "lesson_hint" in ds and "limit=1000" in ds and "limit=400" not in ds, "Fanlar: hash tiklash, aria-live, lesson_hint, limit=1000")
ok("data-lp-live" in lp and "lastKey" in lp, "lpPicker: aria-live bloki bir marta, klaviatura himoyasi")
ok("lcLogGroups" in dc and "lcConfirm" in dc and "LC_BUSY" in dc and "Baribir ochaymi" in dc and "lcWhen" in dc, "Kartochka: jurnal guruhlash, tasdiq, yuklanish himoyasi")
ok("kx-fcode" in src("konstruktor.js"), "Konstruktor sarlavhasida unikal kod chipi")
idx = src("index.html")
ok(idx.index('src="paket.js"') < idx.index('src="dars.js"') < idx.index('src="dars_card.js"'), "index.html: paket.js dars.js dan, dars_card.js keyin")

print("— 2. Brauzer: umumiy interfeys (1440 va 390 px, yorug' va qorong'i) —")
pwj, chrome = os.environ.get("PW"), os.environ.get("CHROME")
if not (pwj and chrome and node):
    print("  – PW/CHROME berilmagan — brauzer sinovi o'tkazib yuborildi")
else:
    HEAD_ID, OQ_ID = uid("masofaviy"), uid("oqituvchi")
    H = S(HEAD_ID)
    items = H.get("/api/paket/courses", params={"limit": 1000}).json()["items"]
    co = next(c for c in items if c["lessons"] >= 10)
    sj = H.get(f"/api/dars/subjects/{co['id']}").json()
    L = [l for l in sj["lessons"] if l["kind"] == "maruza"]
    lk, lk0 = L[7]["key"] if len(L) > 7 else L[-1]["key"], L[4]["key"]
    ok(lk != lk0, f"Fixture: kurs {co['id']} ({co['code']}), matnli dars L{lk}, bo'sh dars L{lk0}")
    import docx
    d = docx.Document(); d.add_heading("Talab va taklif nazariyasi", 0); d.add_paragraph("Narx oshsa talab hajmi kamayadi. " * 6)
    bio = io.BytesIO(); d.save(bio)
    r = H.post(f"/api/paket/courses/{co['id']}/topics/{lk}/upload", params={"name": "ma'ruza.docx"}, content=bio.getvalue(), headers={"Content-Type": "application/octet-stream"})
    ok(r.status_code == 200, f"Fixture: L{lk} ga ma'ruza matni yuklandi (jurnal va matn ko'rinishi uchun)")
    out = os.environ.get("ZUC_OUT") or str(Path(os.environ.get("TMPDIR", "/tmp")) / "isft_zanjir_ux_common")
    env = dict(os.environ, B=B, PW_=PW, H_UID=str(HEAD_ID), T_UID=str(OQ_ID), CID=str(co["id"]), LKEY=str(lk), LKEY0=str(lk0), CODE=co["code"], OUT=out)
    rr = subprocess.run([node, str(ROOT / "tools" / "zanjir_ux_common.js")], cwd=ROOT, env=env, capture_output=True, text=True, timeout=900)
    nb = 0
    for ln in (rr.stdout + rr.stderr).splitlines():
        s_ = ln.strip()
        if s_.startswith("✓"): ok(True, "[brauzer] " + s_[1:].strip()); nb += 1
        elif s_.startswith("✗"): ok(False, "[brauzer] " + s_[1:].strip())
    ok(rr.returncode == 0 and nb >= 200, f"tools/zanjir_ux_common.js chiqish kodi 0, {nb} ta tekshiruv · skrinshotlar: {out}")
print(f"Hammasi o'tdi: {N[0]} ta tekshiruv.")
