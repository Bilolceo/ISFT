"""Studiya UI (static/studio.js, studio.css) — «Taqdimot → Studiya → Masofaviy bo'lim» zanjirining studiya tomoni: brauzer sinovi.

Ishga tushirish:  PW=<playwright-core> CHROME=<chrome> python tests/run_all.py --only zanjir_ux_studio
   (yoki: ISFT_TEST_URL=http://127.0.0.1:8000 ISFT_CORE_DB=data/jarvis.db PW=… CHROME=… .venv/bin/python tests/test_zanjir_ux_studio.py)
Tayyorlash (HTTP + baza): o'qituvchi dars uchun taqdimot yuboradi (v1, v2), syomka bandi, montaj vazifalari (ko'rib chiqish kutayotgan — videosi bor va yo'q,
tasdiqlangan — taqdimotli va taqdimotsiz). Keyin tools/zanjir_ux_studio.js (1440 va 390 px, yorug'/qorong'i, operator va bo'lim boshlig'i):
  stModal: boshlang'ich fokus, Tab aylanishi, Esc (faqat <a>/[data-x] bor «Taqdimot» oynasida ham), fokus qaytishi, fon inert, fonni bosish, so'rov paytida yopilmasligi,
  xato oyna ichida (role=alert); «Taqdimot» oynasi (sarlavha, o'qish rejimi ←/→, .pptx / PDF, eski versiyalar); «Masofaviy bo'limga yuborish» matni, ogohlantirish,
  409 da yopilishi, ikki marta bosish; montaj tartibi; kun rejasi (kod pilyulasi, chip, fokus, kontrast); tarix guruhlanishi; rolga mos matn; 44 px; gorizontal siljish yo'q.
DIQQAT: server bazasini o'zgartiradi — PRODUCTION'da ishlatilmaydi.
"""
import json, os, re, shutil, sqlite3, subprocess, sys
import datetime as dt
from pathlib import Path
import httpx

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


def q(sql, args=()):
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True, timeout=30)
    try: return con.execute(sql, args).fetchall()
    finally: con.close()


def q1(sql, args=()):
    r = q(sql, args); return r[0][0] if r else None


def w(sql, args=()):
    con = sqlite3.connect(DB, timeout=30)
    try:
        cur = con.execute(sql, args); con.commit(); return cur.lastrowid
    finally: con.close()


def S(uid):
    c = httpx.Client(base_url=B, timeout=300)
    r = c.post("/api/login", json={"user_id": uid, "password": PW})
    assert r.status_code == 200, f"login {uid}: {r.status_code} {r.text}"
    return c


def J(r, code=200):
    assert r.status_code == code, f"{r.request.method} {r.request.url.path}: {r.status_code} {r.text[:400]}"
    return r.json()


def uid(role):
    r = q1("SELECT id FROM users WHERE role=? AND COALESCE(active,1)=1 ORDER BY id LIMIT 1", (role,)); assert r, f"{role} akkaunti yo'q"; return r


TEXT = ("# Talab va taklif\nBozor iqtisodiyotida narx talab va taklif muvozanati orqali shakllanadi. " * 3 +
        "\n## Talab qonuni\n- Narx oshsa talab kamayadi\n- Daromad ta'siri\n- O'rnini bosish ta'siri\n## Taklif qonuni\n- Narx oshsa taklif ortadi\n- Xarajatlar\n"
        "## Nazorat savollari\n- Talab qonuni nima?\n- Muvozanat narxi nima?\n")
MP4 = b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00mp42isom" + b"\x00\x00\x00\x08free" + bytes(range(256)) * 8


def make_video(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    ff = shutil.which("ffmpeg")
    if ff:
        r = subprocess.run([ff, "-y", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc=size=320x180:rate=10:duration=2", "-pix_fmt", "yuv420p", str(path)], capture_output=True)
        if r.returncode == 0 and path.is_file():
            return
    path.write_bytes(MP4)


# =============================================================================================
print("— 1. Tayyorlash: o'qituvchi taqdimoti, syomka, montaj vazifalari —")
from app import clock as CLK                                              # noqa: E402
T0 = CLK.now_iso()[:19]
OQ_ID = uid("oqituvchi"); OQ = S(OQ_ID)
OPER_ID, HEAD_ID = uid("montaj_operator"), uid("masofaviy")
OPER, HEAD = S(OPER_ID), S(HEAD_ID)
co0 = J(OQ.get(P + "/lessons"))["items"][0]
CID = co0["id"]
rows = J(HEAD.get(ST + "/lessons", params={"course_id": CID}))["lessons"]
clean = [r["lkey"] for r in rows if not r.get("pres_version") and not r.get("dept_sent") and not r.get("booking") and r["stage"] != "nextid"]
ok(len(clean) >= 7, f"Kursda tayyorlash uchun kamida 7 ta toza dars bor ({len(clean)})")
LK_A, LK_W, LK_D, LK_E, LK_R, LK_N = clean[:6]
code_of = {r["lkey"]: r["full_code"] for r in rows}
D = J(OQ.post(P + "/decks/text", json={"text": TEXT, "course_id": CID, "lkey": LK_A, "title": "Talab va taklif"}))
did = D["id"]
J(OQ.post(P + f"/decks/{did}/build", json={}))
S1 = J(OQ.post(P + f"/decks/{did}/send", json={"note": "Birinchi variant"}))
o = S1["outline"]; o["slides"].append({"type": "summary", "title": "Xulosa", "cards": [{"title": "Talab", "text": "Narx bilan teskari"}]})
J(OQ.post(P + f"/decks/{did}/outline", json={"outline": o})); J(OQ.post(P + f"/decks/{did}/build", json={}))
S2 = J(OQ.post(P + f"/decks/{did}/send", json={"note": "Xulosa qo'shildi"}))
VER = S2["send"]["version"]
ok(VER >= 2, f"Taqdimot yuborildi: v{S1['send']['version']} → v{VER} ({code_of[LK_A]})")
room = J(OPER.get(ST + "/meta"))["rooms"][0]
free = None
for i in range(2, 30):
    day = (dt.date.today() + dt.timedelta(days=i)).isoformat()
    for rm in J(OPER.get(ST + "/day", params={"date": day}))["rooms"]:
        sl = [s["start"] for s in rm["slots"] if s["free"]]
        if sl and rm["id"] == room["id"]: free = sl[-1]; break
    if free: break
bk = OQ.post(ST + "/bookings", json={"course_id": CID, "lkey": LK_A, "room_id": room["id"], "start": free})
ok(bk.status_code == 200, "O'qituvchi dars A ga syomka belgiladi")
bid = bk.json()["booking"]["id"]

created = {"jobs": [], "raws": []}


def mk_job(lk, status, video=False, with_booking=False):
    raw = w("INSERT INTO st_raw(course_id,lkey,booking_id,name,kind,path,size,ts,deleted) VALUES(?,?,?,?,?,?,?,?,0)", (CID, lk, bid if with_booking else None, f"xom_{lk}.mp4", "mp4", "x", 1, T0))
    rep = json.dumps({"duration_in": 3722, "duration_out": 3010, "cut_total": 712, "warnings": ["Ovoz darajasi 3:20–3:45 oralig'ida past"],
                      "chapters": [{"start": 0, "title": "Kirish"}, {"start": 420, "title": "Talab qonuni"}, {"start": 1500, "title": "Taklif qonuni"}],
                      "cuts": [{"start": 120, "end": 150, "reason": "silence"}, {"start": 900, "end": 960, "reason": "retake"}]}, ensure_ascii=False)
    j = w("INSERT INTO st_jobs(course_id,lkey,raw_id,template,status,attempts,created_at,updated_at,result_at,decided_at,decided_name,report,files) VALUES(?,?,?,?,?,1,?,?,?,?,?,?,?)",
          (CID, lk, raw, "maruza_slayd", status, T0, T0, T0, T0 if status == "tasdiqlandi" else None, "Operator" if status == "tasdiqlandi" else None, rep, "{}"))
    if video: make_video(DATA / "studio" / "jobs" / str(j) / "video.mp4")
    created["jobs"].append(j); created["raws"].append(raw)
    return j


JID_P = mk_job(LK_A, "tasdiqlandi", video=True, with_booking=True)   # taqdimotli, yuborilmagan
JID_W = mk_job(LK_W, "tasdiqlandi", video=True)                      # taqdimotsiz (ogohlantirish)
JID_D = mk_job(LK_D, "tasdiqlandi", video=True)                      # 409 sinovi
JID_E = mk_job(LK_E, "tasdiqlandi", video=True)                      # ikki marta bosish / so'rov paytida yopilmasligi
JID_R = mk_job(LK_R, "tayyor", video=True)                           # ko'rib chiqish: video bor
JID_N = mk_job(LK_N, "tayyor", video=False)                          # ko'rib chiqish: video fayli yo'q
for jid_, lk_ in ((JID_P, LK_A), (JID_W, LK_W), (JID_D, LK_D), (JID_E, LK_E)):
    jd = J(OPER.get(f"{ST}/jobs/{jid_}"))
    ok(jd["dept"] is None and jd["dept_info"]["full_code"] == code_of[lk_], f"Tasdiqlangan montaj #{jid_}: bo'limga yuborilmagan, kod {code_of[lk_]}")
ok(J(OPER.get(f"{ST}/jobs/{JID_W}"))["dept_info"]["pres"] is None, "Montaj W: taqdimot yuborilmagan (ogohlantirish chiqishi kerak)")
ok(J(OPER.get(f"{ST}/jobs/{JID_R}"))["job"]["media"].get("video") and not J(OPER.get(f"{ST}/jobs/{JID_N}"))["job"]["media"].get("video"), "Montaj R videosi bor, N videosi yo'q")

print("— 2. Brauzer: operator va bo'lim boshlig'i (1440 / 390 px, yorug'/qorong'i) —")
node, pwj, chrome = shutil.which("node"), os.environ.get("PW"), os.environ.get("CHROME")
for f in ("static/studio.js", "tools/zanjir_ux_studio.js"):
    if node:
        r = subprocess.run([node, "--check", str(ROOT / f)], capture_output=True, text=True)
        ok(r.returncode == 0, f"node --check {f}" + ("" if r.returncode == 0 else " — " + r.stderr[:300]))
if not (pwj and chrome and node):
    print("  – PW/CHROME berilmagan — brauzer sinovi o'tkazib yuborildi")
else:
    env = dict(os.environ, B=B, PW_=PW, O_UID=str(OPER_ID), H_UID=str(HEAD_ID), CID=str(CID), LK_A=str(LK_A), CODE_A=code_of[LK_A], VER=str(VER),
               JID_P=str(JID_P), JID_W=str(JID_W), JID_D=str(JID_D), JID_E=str(JID_E), JID_R=str(JID_R), JID_N=str(JID_N), BK_DAY=free[:10], BK_KEY=f"{CID}:{LK_A}",
               CODE_W=code_of[LK_W], CODE_R=code_of[LK_R], CODE_N=code_of[LK_N], CODE_D=code_of[LK_D],
               OUT=os.environ.get("ZJ_OUT") or str(Path(os.environ.get("TMPDIR", "/tmp")) / "isft_zanjir_ux_studio"))
    rr = subprocess.run([node, str(ROOT / "tools" / "zanjir_ux_studio.js")], cwd=ROOT, env=env, capture_output=True, text=True, timeout=900)
    nb = 0
    for ln in (rr.stdout + rr.stderr).splitlines():
        s_ = ln.strip()
        if s_.startswith("✓"): ok(True, "[brauzer] " + s_[1:].strip()); nb += 1
        elif s_.startswith("✗"):
            print((rr.stdout + rr.stderr)[-2500:])
            ok(False, "[brauzer] " + s_[1:].strip())
        elif s_.startswith("–") or s_.startswith("Error") or "TypeError" in s_ or "Timeout" in s_: print("  " + s_)
    ok(rr.returncode == 0 and nb >= 60, f"tools/zanjir_ux_studio.js chiqish kodi {rr.returncode}, {nb} ta tekshiruv · skrinshotlar: {env['OUT']}" + ("" if rr.returncode == 0 else "\n" + (rr.stdout + rr.stderr)[-1500:]))

# tozalash: keyingi to'plamlarga ta'sir qilmasin
for j in created["jobs"]:
    w("DELETE FROM st_dept WHERE job_id=?", (j,)); w("DELETE FROM st_yt WHERE job_id=?", (j,)); w("DELETE FROM st_jobs WHERE id=?", (j,))
for r_ in created["raws"]:
    w("DELETE FROM st_raw WHERE id=?", (r_,))
w("UPDATE st_bookings SET status='bekor' WHERE id=?", (bid,))
J(OQ.post(P + f"/decks/{did}/delete", json={}))
print(f"Hammasi o'tdi: {N[0]} ta tekshiruv.")
