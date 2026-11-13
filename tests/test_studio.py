"""Studiya (app/studio.py, app/studio_yt.py) — dars ishlab chiqarish: ruxsatlar, syomka bandi (ziddiyat, ko'chirish, bekor qilish, eslatmalar),
bosqichlarni hisoblash (derive), montaj ishchisi API (token, claim / lease / muddati o'tishi, progress, natija multipart, fail / qayta urinish),
imzolangan havolalar va HTTP Range, operator ko'rigi → paket videosi, YouTube yuklovchisi (httpx.MockTransport — tarmoqqa chiqilmaydi: token
yangilash, resumable sessiya, bo'laklar, unlisted, xato / kvota / backoff, sirlar javoblarda yo'q), avtomatik paket, holat paneli raqamlari.

Ishga tushirish:  ISFT_TEST_URL=http://127.0.0.1:8000 ISFT_CORE_DB=data/jarvis.db .venv/bin/python tests/test_studio.py
   (yoki: python tests/run_all.py --only studio)
A qism — ishlab turgan server orqali (HTTP): ruxsatlar, bandlar, xom video, ishchi o'chiq (503).
B qism — JARAYON ICHIDA: bazaning NUSXASI (vaqtinchalik katalog) + to'liq ilova (fastapi TestClient), ISFT_CORE_WORKER_TOKEN shu jarayonda;
YouTube HTTP — studio_yt.TRANSPORT = httpx.MockTransport. Server bazasiga B qism tegmaydi.
DIQQAT: A qism lokal bazani o'zgartiradi (bandlar, xom video, montaj vazifasi) — PRODUCTION'da ishlatilmaydi.
"""
import datetime as dt, io, json, os, re, shutil, sqlite3, sys, tempfile, time
from pathlib import Path
import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
B = os.environ.get("ISFT_TEST_URL", "http://127.0.0.1:8000")
DBP = Path(os.environ.get("ISFT_CORE_DB") or ROOT / "data" / "jarvis.db")
DATA = Path(os.environ.get("ISFT_CORE_DATA_DIR") or DBP.parent)
PW = re.search(r'DEMO_PASSWORD = os.getenv\("ISFT_CORE_DEMO_PASSWORD", "([^"]+)"\)', (ROOT / "app" / "rbac.py").read_text()).group(1)
fails = []
def ok(cond, msg):
    print(("  ✓ " if cond else "  ✗ ") + msg)
    if not cond: fails.append(msg)
def q(sql, a=()):
    con = sqlite3.connect(DBP, timeout=30); con.row_factory = sqlite3.Row
    try: return [dict(r) for r in con.execute(sql, a).fetchall()]
    finally: con.close()
def uid(role, where="", args=()):
    r = q(f"SELECT id FROM users WHERE role=? AND COALESCE(active,1)=1 {where} ORDER BY id LIMIT 1", (role, *args)); assert r, f"{role} akkaunti yo'q"; return r[0]["id"]
def S(u):
    c = httpx.Client(base_url=B, timeout=120)
    r = c.post("/api/login", json={"user_id": u, "password": PW}); assert r.status_code == 200, f"login {u}: {r.text}"
    return c
P, W = "/api/studio", "/api/montaj"
MP4 = b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00mp42isom" + b"\x00\x00\x00\x08free"
def fake_mp4(n=4096, seed=1):
    import random
    rnd = random.Random(seed)
    return MP4 + bytes(rnd.getrandbits(8) for _ in range(max(0, n - len(MP4))))

# =============================================================================================
print("== A1. Ruxsatlar (server orqali)")
head, staff, oper, rek, pro, teach, kaf, bux, ith = (S(uid(r)) for r in ("masofaviy", "masofaviy_xodim", "montaj_operator", "rektor", "prorektor_oquv",
                                                                        "oqituvchi", "kafedra", "buxgalteriya", "it_head"))
teach_uid = uid("oqituvchi")
teach_tid = q("SELECT teacher_id FROM users WHERE id=?", (teach_uid,))[0]["teacher_id"]
own = q("SELECT * FROM dl_courses WHERE teacher_id=? ORDER BY id LIMIT 1", (teach_tid,))[0]
other = q("SELECT * FROM dl_courses WHERE teacher_id!=? AND subject='Mikroiqtisodiyot' ORDER BY id LIMIT 1", (teach_tid,))[0]
me = oper.get("/api/me").json()
ok(me["role_key"] == "montaj_operator" and me["modules"].get("studio") is True and "studio" in me["allow"], "Operator: yangi lavozim, «studio» bo'limi yoqilgan, STUDIO resursi")
M = {n: c.get(P + "/meta") for n, c in (("head", head), ("staff", staff), ("oper", oper), ("rek", rek), ("pro", pro), ("teach", teach), ("ith", ith))}
ok(all(r.status_code == 200 for r in M.values()), "meta: bo'lim, xodim, operator, rektor, prorektor, o'qituvchi, AT boshlig'i — 200")
ok(M["head"].json()["tabs"] == ["holat", "kun", "montaj", "darslar", "sozlama"], "Bo'lim boshlig'i: Holat, Kun rejasi, Montaj, Darslar, Sozlamalar")
ok(M["oper"].json()["tabs"][:2] == ["kun", "montaj"] and M["oper"].json()["caps"]["review"], "Operator: Kun rejasi va Montaj birinchi, ko'rik huquqi")
ok(M["rek"].json()["tabs"] == ["holat"] and M["rek"].json()["caps"]["aggregate"] and M["pro"].json()["tabs"] == ["holat"], "Rektor va o'quv prorektori: faqat jamlangan Holat")
ok(M["teach"].json()["tabs"] == ["darslar"] and M["teach"].json()["tab_labels"]["darslar"] == "Mening darslarim", "O'qituvchi: «Mening darslarim»")
ok(M["ith"].json()["tabs"] == ["sozlama"], "AT boshlig'i: faqat Sozlamalar (YouTube)")
ok(kaf.get(P + "/meta").status_code == 403 and bux.get(P + "/meta").status_code == 403, "Kafedra mudiri va buxgalteriya — 403")
ok(rek.get(P + "/board").status_code == 200 and rek.get(P + "/kpi").status_code == 200, "Rektor: holat paneli va KPI")
ok(rek.get(f"{P}/lessons/{own['id']}/1").status_code == 403 and rek.get(P + "/day").status_code == 403 and rek.get(P + "/jobs").status_code == 403,
   "Rektor: dars tafsiloti, kun rejasi, montaj navbati — 403 (fayllarsiz)")
ok(teach.get(P + "/board").status_code == 403 and teach.get(P + "/jobs").status_code == 403, "O'qituvchi: holat paneli va montaj navbati — 403")
ok(ith.get(P + "/board").status_code == 403 and ith.get(P + "/youtube").status_code == 200, "AT boshlig'i: holat yo'q, YouTube holati bor")
ok(staff.get(P + "/youtube").status_code == 403 and oper.get(P + "/youtube").status_code == 403, "YouTube sozlamasi: bo'lim xodimi va operator — 403")
tl = teach.get(P + "/lessons").json()
ok(tl["courses"] and all(c["id"] in {r["id"] for r in q("SELECT id FROM dl_courses WHERE teacher_id=?", (teach_tid,))} for c in tl["courses"]),
   f"O'qituvchi: faqat o'z kurslari ({len(tl['courses'])} ta)")
ok(all(l["kind"] in ("maruza", "amaliy") for l in tl["lessons"]) and all(l["stage"] for l in tl["lessons"]), "Darslar: faqat L va A, har birida bosqich")
ok(teach.get(f"{P}/lessons/{other['id']}/1").status_code == 403, "O'qituvchi begona kurs darsini ochmaydi (403)")
ok(oper.post(P + "/plan", json={"course_id": own["id"], "on": True}).status_code == 403, "Ishlab chiqarish rejasi — faqat bo'lim (operator 403)")
ok(head.post(P + "/plan", json={"course_id": own["id"], "on": True}).status_code == 200, "Bo'lim boshlig'i kursni rejaga qo'shadi")
a_log = q("SELECT COUNT(*) n FROM audit_log WHERE resource='studio' AND allowed=0")[0]["n"]
ok(a_log > 0, f"Rad etilgan so'rovlar audit jurnalida ({a_log})")

# =============================================================================================
print("== A2. Ishchi API: token sozlanmagan — 503")
r = httpx.post(B + W + "/jobs/claim", headers={"X-Worker-Token": "x"})
if os.environ.get("ISFT_CORE_WORKER_TOKEN"):
    print("  · ISFT_CORE_WORKER_TOKEN serverda o'rnatilgan — 503 tekshiruvi o'tkazib yuborildi")
else:
    ok(r.status_code == 503 and "worker o'chiq" in r.text, "claim: token yo'q → 503 «worker o'chiq»")
    ok(httpx.post(B + W + "/jobs/1/progress", json={"stage": "x"}).status_code == 503 and httpx.post(B + W + "/jobs/1/fail", json={}).status_code == 503,
       "progress / fail ham 503")

# =============================================================================================
print("== A3. Studiya bandi (server orqali)")
room = M["oper"].json()["rooms"][0]
def free_slots(c, n=3, skip=0):
    out, d = [], dt.date.today()
    for i in range(1, 30):
        day = (d + dt.timedelta(days=i)).isoformat()
        pl = c.get(P + "/day", params={"date": day}).json()
        for rm in pl["rooms"]:
            if rm["id"] != room["id"]: continue
            out += [s["start"] for s in rm["slots"] if s["free"]]
        if len(out) >= n + skip: break
    return out[skip:skip + n]
sl = free_slots(oper, 3, 2)
ok(len(sl) == 3, f"Bo'sh slotlar topildi: {', '.join(x[5:16] for x in sl)}")
L5, L6 = 5, 6
r = teach.post(P + "/bookings", json={"course_id": own["id"], "lkey": L5, "room_id": room["id"], "start": sl[0], "note": "test"})
ok(r.status_code == 200 and r.json()["booking"]["status"] == "band", "O'qituvchi o'z darsiga syomka belgiladi")
b1 = r.json()["booking"]["id"]
r = oper.post(P + "/bookings", json={"course_id": other["id"], "lkey": L5, "room_id": room["id"], "start": sl[0]})
ok(r.status_code == 409 and "band" in r.json().get("detail", ""), "Xona ziddiyati: o'sha vaqtni boshqa dars ololmaydi (409)")
r = teach.post(P + "/bookings", json={"course_id": own["id"], "lkey": L5, "room_id": room["id"], "start": sl[1]})
ok(r.status_code == 409, "Bitta darsga ikkinchi faol band — 409")
ok(teach.post(P + "/bookings", json={"course_id": other["id"], "lkey": L5, "room_id": room["id"], "start": sl[1]}).status_code == 403, "O'qituvchi begona kursga band qilmaydi (403)")
past = (dt.datetime.now() - dt.timedelta(days=1)).replace(hour=9, minute=0, second=0, microsecond=0).isoformat()
ok(teach.post(P + "/bookings", json={"course_id": own["id"], "lkey": L6, "room_id": room["id"], "start": past}).status_code == 400, "O'tgan vaqt — 400")
odd = sl[1][:14] + "07:00"
ok(teach.post(P + "/bookings", json={"course_id": own["id"], "lkey": L6, "room_id": room["id"], "start": odd}).status_code == 400, "Jadvalga mos kelmagan vaqt — 400")
ok(teach.post(f"{P}/bookings/{b1}/move", json={"start": sl[1], "reason": ""}).status_code == 400, "Ko'chirish sababsiz — 400")
r = teach.post(f"{P}/bookings/{b1}/move", json={"start": sl[1], "reason": "Kafedra majlisi"})
ok(r.status_code == 200 and r.json()["booking"]["start"] == sl[1] and r.json()["booking"]["reason"] == "Kafedra majlisi", "Ko'chirildi (sabab bilan)")
r = oper.post(P + "/bookings", json={"course_id": other["id"], "lkey": L5, "room_id": room["id"], "start": sl[0]})
ok(r.status_code == 200, "Bo'shagan slotga operator boshqa darsni yozdi")
b2 = r.json()["booking"]["id"]
ok(teach.post(f"{P}/bookings/{b2}/cancel", json={"reason": "x y z"}).status_code == 403, "O'qituvchi begona bandni bekor qilmaydi (403)")
ok(oper.post(f"{P}/bookings/{b2}/cancel", json={"reason": ""}).status_code == 400, "Bekor qilish sababsiz — 400")
ok(oper.post(f"{P}/bookings/{b2}/cancel", json={"reason": "O'qituvchi kasal"}).status_code == 200, "Bekor qilindi")
ok(q("SELECT status, reason FROM st_bookings WHERE id=?", (b2,))[0] == {"status": "bekor", "reason": "O'qituvchi kasal"}, "Bazada: bekor + sabab")
dp = teach.get(P + "/day", params={"date": sl[1][:10]}).json()
mine = [i for i in dp["items"] if i.get("mine")]
ok(any(i["id"] == b1 for i in mine) and all(set(i) <= {"id", "room_id", "start", "end", "busy", "mine"} for i in dp["items"] if not i.get("mine")),
   "O'qituvchi kun rejasida: o'z bandi to'liq, boshqalar — faqat «band»")
dpo = oper.get(P + "/day", params={"date": sl[1][:10]}).json()
ok(any(i["id"] == b1 and i["teacher"] and i["code"] == "L5" for i in dpo["items"]), "Operator kun rejasida: dars kodi, o'qituvchi")
st = teach.get(f"{P}/lessons/{own['id']}/{L5}").json()["state"]
ok(st["stage"] == "syomka_belgilandi" and st["owner"] == "montaj_operator", "Bosqich: «Syomka belgilandi», egasi — operator")
r = oper.post(f"{P}/bookings/{b1}/done", json={"status": "otdi"})
ok(r.status_code in (200, 409), "Kelajakdagi syomkani «qilindi» deb belgilash: 12 soatdan uzoq bo'lsa 409")

# =============================================================================================
print("== A4. Xom video va montaj navbati (server orqali)")
url = f"{P}/lessons/{own['id']}/{L6}/raw"
ok(teach.post(url, content=fake_mp4()).status_code == 403, "O'qituvchi xom video yuklamaydi (403)")
ok(oper.post(url + "?name=x.mp4", content=b"\x00" * 200).status_code == 415, "Noto'g'ri tur (baytlar bo'yicha) — 415")
ok(oper.post(url + "?name=x.mp4&template=yoq", content=fake_mp4()).status_code == 400, "Noma'lum shablon — 400")
r = oper.post(url + "?name=dars.mp4&template=maruza_slayd", content=fake_mp4(20000))
ok(r.status_code == 200 and r.json()["kind"] == "mp4" and r.json()["job"]["status"] == "navbatda", "Xom video yuklandi va montaj navbatiga qo'yildi")
mov = b"\x00\x00\x00\x14ftypqt  \x00\x00\x00\x00qt  " + b"\x01" * 100
r2 = oper.post(f"{P}/lessons/{own['id']}/7/raw?name=a.mov", content=mov)
ok(r2.status_code == 200 and r2.json()["kind"] == "mov", "QuickTime (.mov) — baytlardan aniqlandi")
mkv = b"\x1a\x45\xdf\xa3\x9f\x42\x86\x81\x01\x42\xf7\x81\x01\x42\xf2\x81\x04\x42\xf3\x81\x08\x42\x82\x88matroska" + b"\x00" * 64
ok(oper.post(f"{P}/lessons/{own['id']}/7/raw?name=a.mkv", content=mkv).json().get("kind") == "mkv", "Matroska (.mkv) — baytlardan aniqlandi")
jl = oper.get(P + "/jobs").json()
ok(any(j["code"] == "L6" and j["status"] == "navbatda" and j["template_label"] == "Ma'ruza: o'qituvchi + slayd" for j in jl["items"]), "Montaj navbatida (operator ro'yxati)")
ok(not jl["worker"] or os.environ.get("ISFT_CORE_WORKER_TOKEN"), "Ishchi holati: token sozlanmagan")
st = oper.get(f"{P}/lessons/{own['id']}/{L6}").json()
ok(st["state"]["stage"] == "montaj" and st["raws"] and st["jobs"][0]["status"] == "navbatda", "Bosqich: «Montajda (AI)», xom video va vazifa tarixda")
ok(any(h["action"] == "montajga yuborildi" for h in st["history"]), "Tarix (st_log)")

# =============================================================================================
print("== B. Jarayon ichida: bazaning nusxasi, to'liq ilova, ishchi tokeni")
tmp = Path(tempfile.mkdtemp(prefix="studio-"))
srcc = sqlite3.connect(DBP); dst = sqlite3.connect(tmp / "jarvis.db"); srcc.backup(dst); srcc.close(); dst.close()
if (DATA / "paket").is_dir(): shutil.copytree(DATA / "paket", tmp / "paket")
if (DATA / "studio").is_dir(): shutil.copytree(DATA / "studio", tmp / "studio")
TOKEN = "test-ishchi-" + os.urandom(8).hex()
os.environ.update(ISFT_CORE_DATA_DIR=str(tmp), ISFT_CORE_DB=str(tmp / "jarvis.db"), ISFT_CORE_SECRETS_DIR=str(tmp / "secrets"),
                  ISFT_CORE_FILES_DIR=str(tmp / "portal_files"), ISFT_CORE_STAFFABS_DIR=str(tmp / "staffabs_files"),
                  ISFT_CORE_WORKER_TOKEN=TOKEN, ISFT_CORE_RAW_MAX_GB="0.0005", ISFT_CORE_RESULT_MAX_GB="0.01", ISFT_CORE_YT_CHUNK_MB="0.25", ISFT_CORE_PUBLIC_URL="http://testserver")
for k in ("ISFT_CORE_YT_OFF", "ISFT_CORE_YT_DAILY", "ISFT_CORE_MODULES"): os.environ.pop(k, None)
import contextlib
with contextlib.redirect_stdout(io.StringIO()):
    from app import main as APP           # noqa: E402 — nusxa bazaga ulanadi
from fastapi.testclient import TestClient   # noqa: E402
from app import studio as STU, studio_yt as YT, paket as PK, db as DB, rbac as RB   # noqa: E402
assert Path(DB.DB_PATH) == tmp / "jarvis.db" and STU.store() == tmp / "studio", "nusxa emas!"
con = APP.con
def X(sql, a=()): r = con.execute(sql, a); con.commit(); return r
def Q(sql, a=()): return DB.rows(con, sql, a)
def T(u):
    c = TestClient(APP.app, base_url="http://testserver")
    r = c.post("/api/login", json={"user_id": u, "password": PW}); assert r.status_code == 200, r.text
    return c
H, O, TE, RK, KF = (T(uid(r)) for r in ("masofaviy", "montaj_operator", "oqituvchi", "rektor", "kafedra"))
WC = TestClient(APP.app, base_url="http://testserver")
WH = {"X-Worker-Token": TOKEN}
X("UPDATE st_jobs SET status='bekor' WHERE status IN ('navbatda','ishlanmoqda','operator')")
SEEN = []                                  # barcha JSON javoblar — sirlar tekshiruvi uchun
def J(r, code=200):
    assert r.status_code == code, f"{r.request.method} {r.request.url.path}: {r.status_code} {r.text[:300]}"
    try: SEEN.append(r.text)
    except Exception: pass
    return r.json() if r.content and r.headers.get("content-type", "").startswith("application/json") else None

print("-- B1. Ishchi autentifikatsiyasi")
ok(WC.post(W + "/jobs/claim").status_code == 401, "Sarlavhasiz — 401")
n0 = Q("SELECT COUNT(*) n FROM audit_log WHERE resource='studio' AND allowed=0 AND action LIKE 'montaj ishchisi%'")[0]["n"]
ok(WC.post(W + "/jobs/claim", headers={"X-Worker-Token": TOKEN + "x"}).status_code == 401, "Noto'g'ri token — 401")
ok(Q("SELECT COUNT(*) n FROM audit_log WHERE resource='studio' AND allowed=0 AND action LIKE 'montaj ishchisi%'")[0]["n"] == n0 + 1, "Noto'g'ri token audit jurnalida")
r = WC.post(W + "/jobs/claim", headers=WH)
ok(r.status_code == 204 and not r.content, "Navbat bo'sh — 204")
ok(H.post(W + "/jobs/claim").status_code == 401, "Sessiya cookie ishchi tokeni o'rnini bosmaydi (401)")

print("-- B2. Xom video → claim → imzolangan havolalar (Range)")
CID, MIK = own["id"], other["id"]
raw = fake_mp4(60000, seed=7)
r = O.post(f"{P}/lessons/{CID}/8/raw?name=l8.mp4&template=faqat_oqituvchi", content=raw)
ok(r.status_code == 200, "Operator xom video yukladi (8-dars)")
ok(O.post(f"{P}/lessons/{CID}/8/raw?name=big.mp4", content=fake_mp4(600_000)).status_code == 413, "ISFT_CORE_RAW_MAX_GB chegarasidan katta — 413")
ok(not list((tmp / "studio" / "tmp").glob("raw_*.part")), "Rad etilgan yuklashdan vaqtinchalik fayl qolmadi")
r = WC.post(W + "/jobs/claim", headers=WH); cj = J(r)
ok(set(cj) == {"job_id", "template", "lesson", "lease", "raw_url", "slides_url", "logo_url"} and cj["template"] == "faqat_oqituvchi", "claim javobi — kontrakt kalitlari aniq (+ lease)")
ok(re.fullmatch(r"[0-9a-f]{16}", cj["lease"] or "") and cj["lease"] in cj["raw_url"], "claim: lease identifikatori javobda va imzolangan havola ichida")
ok(set(cj["lesson"]) == {"course_id", "no", "code", "kind", "title", "subject", "teacher", "plan"} and cj["lesson"]["code"] == "L8" and cj["lesson"]["no"] == 8
   and cj["lesson"]["subject"] == own["subject"] and isinstance(cj["lesson"]["plan"], list), "lesson: course_id, no, code, kind, title, subject, teacher, plan")
JID = cj["job_id"]
jr = Q("SELECT * FROM st_jobs WHERE id=?", (JID,))[0]
lease = dt.datetime.fromisoformat(jr["lease_until"])
ok(jr["status"] == "ishlanmoqda" and jr["attempts"] == 1 and 7000 < (lease - STU._now()).total_seconds() <= 7200, "Qulflandi: ishlanmoqda, 1-urinish, lease ≈ 2 soat")
ok(WC.post(W + "/jobs/claim", headers=WH).status_code == 204, "Boshqa vazifa yo'q — 204 (qulflangan qayta berilmaydi)")
ok(cj["slides_url"] is None and cj["logo_url"] and cj["raw_url"].startswith("http://testserver/api/montaj/files/"), "slides_url — PDF yo'q → null; logo_url va raw_url — to'liq manzil")
ru = cj["raw_url"].replace("http://testserver", "")
r = WC.get(ru); ok(r.status_code == 200 and r.content == raw and r.headers["accept-ranges"] == "bytes", "raw: to'liq fayl (token sarlavhasiz — imzo yetarli)")
r = WC.get(ru, headers={"Range": "bytes=10-19"})
ok(r.status_code == 206 and r.content == raw[10:20] and r.headers["content-range"] == f"bytes 10-19/{len(raw)}", "Range 10-19 → 206 + Content-Range")
r = WC.get(ru, headers={"Range": "bytes=-5"}); ok(r.status_code == 206 and r.content == raw[-5:], "Range oxirgi 5 bayt")
r = WC.get(ru, headers={"Range": f"bytes={len(raw) + 5}-"}); ok(r.status_code == 416 and r.headers["content-range"] == f"bytes */{len(raw)}", "Qondirib bo'lmaydigan Range — 416")
tok = ru.rsplit("/", 1)[1]
bad = tok[:-1] + ("0" if tok[-1] != "0" else "1")
ok(WC.get(W + "/files/" + bad).status_code == 403, "Imzosi buzilgan havola — 403")
ok(WC.get(W + "/files/" + STU.sign(JID, "raw", int(time.time()) - 5)).status_code == 403, "Muddati o'tgan havola — 403")
ok(WC.get(W + "/files/" + tok.replace(".raw.", ".slides.", 1)).status_code == 403, "Boshqa fayl turiga almashtirilgan imzo — 403")
ok(WC.get(cj["logo_url"].replace("http://testserver", "")).status_code == 200, "logo_url — 200")
mk = Q("SELECT * FROM pk_assets WHERE course_id=? AND topic_no=1 AND deleted=0 AND purpose='taqdimot'", (MIK,))
pdf_ok = bool(Q("SELECT 1 x FROM pk_assets WHERE course_id=? AND topic_no=1 AND deleted=0 AND purpose='taqdimot' AND kind='pdf'", (MIK,)))

print("-- B3. progress, lease muddati, fail / qayta urinish")
ok(WC.post(f"{W}/jobs/{JID}/progress", json={"stage": "x"}).status_code == 401, "progress tokensiz — 401")
r = WC.post(f"{W}/jobs/{JID}/progress", headers=WH, json={"stage": "tahlil", "pct": 35, "message": "Sukutlar topilmoqda"})
jr = Q("SELECT * FROM st_jobs WHERE id=?", (JID,))[0]
ok(r.status_code == 200 and jr["stage"] == "tahlil" and jr["pct"] == 35 and jr["message"] == "Sukutlar topilmoqda", "progress: bosqich, foiz, xabar saqlandi")
ok(WC.post(f"{W}/jobs/{JID}/progress", headers=WH, json={"stage": "kesish", "pct": 250}).status_code == 200 and Q("SELECT pct FROM st_jobs WHERE id=?", (JID,))[0]["pct"] == 100,
   "pct 0–100 oralig'iga keltiriladi")
X("UPDATE st_jobs SET lease_until=? WHERE id=?", ((STU._now() - dt.timedelta(minutes=1)).isoformat(), JID))
r = WC.post(W + "/jobs/claim", headers=WH)
jr = Q("SELECT * FROM st_jobs WHERE id=?", (JID,))[0]
ok(r.status_code == 200 and r.json()["job_id"] == JID and jr["attempts"] == 2, "Lease muddati o'tdi → navbatga qaytdi va qayta berildi (2-urinish)")
# [6] lease identifikatori: eski ishchi (eskirgan lease) yozolmaydi va fayl ololmaydi; sarlavhasiz (eski ishchi dasturi) — orqaga moslik
cj_b = r.json(); OLD, NEW = cj["lease"], cj_b["lease"]
ok(NEW and NEW != OLD and jr["lease"] == NEW, "Qayta claim — yangi lease")
ok(WC.get(ru).status_code == 409 and WC.get(cj_b["raw_url"].replace("http://testserver", "")).status_code == 200,
   "Eski lease havolasi — 409 (eskirgan), yangi lease havolasi — 200")
ok(WC.post(f"{W}/jobs/{JID}/progress", headers={**WH, "X-Worker-Lease": OLD}, json={"stage": "x"}).status_code == 409, "progress eskirgan lease bilan — 409 (ishchi bekor qiladi)")
ok(WC.post(f"{W}/jobs/{JID}/fail", headers={**WH, "X-Worker-Lease": OLD}, json={"error": "eski"}).status_code == 409
   and Q("SELECT status FROM st_jobs WHERE id=?", (JID,))[0]["status"] == "ishlanmoqda", "fail eskirgan lease bilan — 409, vazifa o'zgarmadi")
ok(WC.post(f"{W}/jobs/{JID}/progress", headers={**WH, "X-Worker-Lease": NEW}, json={"stage": "tahlil", "pct": 5}).status_code == 200, "progress joriy lease bilan — 200")
ok(WC.post(f"{W}/jobs/{JID}/progress", headers=WH, json={"stage": "tahlil", "pct": 6}).status_code == 200, "progress X-Worker-Lease'siz (eski ishchi) — 200")
ru = cj_b["raw_url"].replace("http://testserver", "")
r = WC.post(f"{W}/jobs/{JID}/fail", headers=WH, json={"error": "ffmpeg: audio yo'lagi topilmadi"})
jr = Q("SELECT * FROM st_jobs WHERE id=?", (JID,))[0]
ok(r.status_code == 200 and r.json()["retry"] and jr["status"] == "navbatda" and jr["not_before"] and "audio" in jr["error"], "fail (2-urinish) → navbat, kechiktirib")
ok(WC.get(ru).status_code == 410, "Faol bo'lmagan vazifa fayli — 410")
ok(WC.post(W + "/jobs/claim", headers=WH).status_code == 204, "not_before kelmaguncha qayta berilmaydi (204)")
X("UPDATE st_jobs SET not_before=NULL WHERE id=?", (JID,))
ok(WC.post(W + "/jobs/claim", headers=WH).json()["job_id"] == JID, "3-urinish berildi")
r = WC.post(f"{W}/jobs/{JID}/fail", headers=WH, json={"error": "yana xato"})
ok(r.json()["status"] == "operator" and Q("SELECT status FROM st_jobs WHERE id=?", (JID,))[0]["status"] == "operator", "3 urinishdan keyin — operator kerak")
ok(WC.post(f"{W}/jobs/{JID}/fail", headers=WH, json={"error": "x"}).status_code == 409 and WC.post(f"{W}/jobs/{JID}/progress", headers=WH, json={}).status_code == 409,
   "Faol bo'lmagan vazifaga progress / fail — 409")
mw = J(O.get("/api/mywork"))
ok(any(it["id"] == f"st-op{JID}" and it["priority"] == "high" for it in mw["items"]), "Operator «Mening vazifalarim»: montaj xatosi")
ok(TE.post(f"{P}/jobs/{JID}/retry").status_code == 403, "O'qituvchi qayta navbatga qo'ya olmaydi (403)")
J(O.post(f"{P}/jobs/{JID}/retry"))
ok(Q("SELECT status, attempts FROM st_jobs WHERE id=?", (JID,))[0] == {"status": "navbatda", "attempts": 0}, "Operator: qayta navbatga (urinishlar 0)")
ok(WC.post(W + "/jobs/claim", headers=WH).json()["job_id"] == JID, "Qayta claim")
r = WC.post(f"{W}/jobs/{JID}/fail", headers=WH, json={"error": "Worker to'xtatildi yoki ish bekor qilindi"})
ok(r.status_code == 200 and Q("SELECT status, attempts, not_before FROM st_jobs WHERE id=?", (JID,))[0] == {"status": "navbatda", "attempts": 0, "not_before": None},
   "Ishchi to'xtatildi (SIGTERM) → darhol navbatga, urinish hisoblanmaydi")
cj_c = WC.post(W + "/jobs/claim", headers=WH).json()
ok(cj_c["job_id"] == JID and Q("SELECT attempts FROM st_jobs WHERE id=?", (JID,))[0]["attempts"] == 1, "Qayta claim (1-urinish)")

print("-- B4. Natija (multipart, oqim bilan)")
from PIL import Image  # noqa: E402
bio = io.BytesIO(); Image.new("RGB", (160, 90), (120, 20, 40)).save(bio, "JPEG"); JPG = bio.getvalue()
VTT = "WEBVTT\n\n00:00:00.000 --> 00:00:03.000\nAssalomu alaykum\n\n00:00:03.500 --> 00:00:07.000\nBugungi mavzu\n".encode()
REPORT = {"duration_in": 3725.4, "duration_out": 2950.0, "cuts": [{"start": 0, "end": 42.5, "reason": "boshlanishdagi sukut"}, {"start": 1200, "end": 1300.2, "reason": "takror"}],
          "chapters": [{"start": 0, "title": "Kirish"}, {"start": 300, "title": "Bozor muvozanati"}, {"start": 1500, "title": "Xulosa"}],
          "slide_changes": [{"t": 12.5, "slide": 1}, {"t": 300, "slide": None}], "warnings": ["Mikrofon 12:40 da shovqinli"],
          "timings": {"3_nutq": 21.0, "jami": 35.0}}   # docs/montaj.md: slide null (slaydsiz bo'lak) va timings — qabul qilinadi
VIDEO = fake_mp4(700_000, seed=3)
def files(**over):
    f = {"video": ("v.mp4", VIDEO, "video/mp4"), "captions": ("c.vtt", VTT, "text/vtt"), "thumbnail": ("t.jpg", JPG, "image/jpeg"),
         "report": ("r.json", json.dumps(REPORT).encode(), "application/json")}
    for k, v in over.items():
        if v is None: f.pop(k)
        else: f[k] = (f[k][0], v, f[k][2])
    return f
RU = f"{W}/jobs/{JID}/result"
ok(WC.post(RU, files=files()).status_code == 401, "result tokensiz — 401")
ok(WC.post(RU, headers={**WH, "X-Worker-Lease": OLD}, files=files()).status_code == 409 and not (STU._job_dir(JID) / "video.mp4").exists(),
   "result eskirgan lease bilan — 409 (tana qabul qilinmaydi)")
ok(WC.post(RU, headers=WH, files=files(thumbnail=None)).status_code == 400, "thumbnail yo'q — 400")
ok(WC.post(RU, headers=WH, files=files(video=b"\x00" * 3000)).status_code == 415, "video mp4 emas — 415")
ok(WC.post(RU, headers=WH, files=files(thumbnail=b"\x89PNG\r\n\x1a\n" + b"0" * 100)).status_code == 415, "thumbnail JPEG emas — 415")
ok(WC.post(RU, headers=WH, files=files(report=b"{oops")).status_code == 400, "report JSON emas — 400")
ok(WC.post(RU, headers=WH, files=files(report=json.dumps({"cuts": [{"start": 5}]}).encode())).status_code == 400, "report tuzilishi noto'g'ri — 400")
ok(WC.post(RU, headers=WH, files=files(captions=b"WEBVTT\n\n" + b"x" * (2 * 1024 * 1024 + 10))).status_code == 413, "captions > 2 MB — 413 (oqimda to'xtatildi)")
ok(WC.post(RU, headers=WH, data={"boshqa": "1"}, files=files()).status_code == 400, "Noma'lum maydon — 400")
ok(Q("SELECT status FROM st_jobs WHERE id=?", (JID,))[0]["status"] == "ishlanmoqda" and not (STU._job_dir(JID) / "video.mp4").exists(), "Rad etilgan natija vazifani o'zgartirmadi")
# multipart'ni mayda bo'laklarda (chegaralar bo'lak orasida qoladi) yuborish
bnd = "----isftChegara" + os.urandom(4).hex()
def part(name, fn, ct, data): return (f"--{bnd}\r\nContent-Disposition: form-data; name=\"{name}\"; filename=\"{fn}\"\r\nContent-Type: {ct}\r\n\r\n").encode() + data + b"\r\n"
body = part("video", "v.mp4", "video/mp4", VIDEO) + part("captions", "c.vtt", "text/vtt", VTT) + part("thumbnail", "t.jpg", "image/jpeg", JPG) + \
       part("report", "r.json", "application/json", json.dumps(REPORT).encode()) + f"--{bnd}--\r\n".encode()
def gen(b, n=997):
    for i in range(0, len(b), n): yield b[i:i + n]
r = WC.post(RU, headers={**WH, "X-Worker-Lease": cj_c["lease"], "Content-Type": f"multipart/form-data; boundary={bnd}"}, content=gen(body))
ok(r.status_code == 200 and r.json()["status"] == "tayyor", "Natija qabul qilindi (997 baytli bo'laklar — chegaralar bo'lak orasida)")
d = STU._job_dir(JID)
ok((d / "video.mp4").read_bytes() == VIDEO and (d / "thumb.jpg").read_bytes() == JPG and (d / "captions.vtt").read_bytes() == VTT, "Fayllar baytma-bayt to'g'ri saqlandi")
ok(not (d / ".incoming").exists(), "Vaqtinchalik katalog tozalandi")
jr = Q("SELECT * FROM st_jobs WHERE id=?", (JID,))[0]; rep = json.loads(jr["report"])
ok(jr["status"] == "tayyor" and jr["pct"] == 100 and jr["lease_until"] is None and len(rep["cuts"]) == 2 and rep["cut_total"] == 142.7
   and rep["slide_changes"][1]["slide"] is None and rep["timings"]["jami"] == 35.0, "Vazifa: tayyor, hisobot me'yorlangan (slide: null, timings)")
r = WC.post(RU, headers={**WH, "X-Worker-Lease": cj_c["lease"]}, files=files())
ok(r.status_code == 200 and Q("SELECT status FROM st_jobs WHERE id=?", (JID,))[0]["status"] == "tayyor" and (d / "video.mp4").read_bytes() == VIDEO,
   "Natija qayta yuborilsa (ishchi 5xx dan keyin qayta uradi) — idempotent: 200, holat o'zgarmaydi")
st = J(O.get(f"{P}/lessons/{CID}/8"))["state"]
ok(st["stage"] == "korib" and st["owner"] == "montaj_operator", "Bosqich: «Ko'rib chiqishda (operator)»")
ok(any(it["id"] == "st-rev" for it in J(O.get("/api/mywork"))["items"]), "Operator «Mening vazifalarim»: «Montaj tayyor — ko'rib chiqing»")

print("-- B5. Operator ko'rigi: ko'rish (Range), qayta montaj, tasdiqlash → paket videosi")
jd = J(O.get(f"{P}/jobs/{JID}"))
ok(jd["job"]["report"]["chapters"][1]["title"] == "Bozor muvozanati" and set(jd["job"]["media"]) == {"video", "thumb", "captions"}, "Ko'rik: bo'limlar, kesishlar, media havolalari")
r = O.get(jd["job"]["media"]["video"], headers={"Range": "bytes=0-99"})
ok(r.status_code == 206 and r.content == VIDEO[:100], "Natija videosi Range bilan (206)")
ok(TE.get(jd["job"]["media"]["video"]).status_code == 403 and RK.get(jd["job"]["media"]["video"]).status_code == 403, "O'qituvchi va rektor natija videosini ko'rmaydi (403)")
ok(O.post(f"{P}/jobs/{JID}/redo", json={"note": ""}).status_code == 400, "Qayta montaj izohsiz — 400")
r = J(O.post(f"{P}/jobs/{JID}/redo", json={"note": "Kirishdagi sukutni qoldiring", "template": "maruza_slayd"}))
J2 = r["job"]["id"]
ok(r["job"]["status"] == "navbatda" and r["job"]["prev_id"] == JID and Q("SELECT status FROM st_jobs WHERE id=?", (JID,))[0]["status"] == "qayta", "Qayta montaj: eski — «qayta», yangi vazifa navbatda")
cj2 = J(WC.post(W + "/jobs/claim", headers=WH))
ok(cj2["job_id"] == J2 and cj2.get("note") == "Kirishdagi sukutni qoldiring" and cj2["template"] == "maruza_slayd", "Ishchi izohni va yangi shablonni oladi")
J(WC.post(f"{W}/jobs/{J2}/result", headers=WH, files=files()))
ok(TE.post(f"{P}/jobs/{J2}/approve").status_code == 403, "O'qituvchi tasdiqlay olmaydi (403)")
ok(not YT.configured(), "YouTube sozlanmagan")
r = J(O.post(f"{P}/jobs/{J2}/approve"))
va = Q("SELECT * FROM pk_assets WHERE course_id=? AND topic_no=8 AND purpose='video' AND deleted=0", (CID,))
ok(len(va) == 1 and va[0]["src"] == "studio" and (PK.store() / va[0]["path"]).read_bytes() == VIDEO, "Paket: darsning video fayli (src=studio), baytlar bir xil")
ok(Q("SELECT COUNT(*) n FROM pk_assets WHERE course_id=? AND topic_no=8 AND purpose='subs' AND deleted=0", (CID,))[0]["n"] == 1 and
   Q("SELECT COUNT(*) n FROM pk_assets WHERE course_id=? AND topic_no=8 AND purpose='poster' AND deleted=0", (CID,))[0]["n"] == 1, "Subtitr (WebVTT) va poster (thumbnail) qo'yildi")
ok(PK.topic_settings(CID, 8)[0]["video_source"] == "file", "video_source = fayl")
g = PK.gather(CID, 8)
ok(g["ready"]["video"]["ok"] and g["ready"]["video"]["provider"] == "file" and g["ready"]["video"]["file"]["studio"] and len(g["ready"]["video"]["captions"]) == 1,
   "Paket manbalarida: video fayl (studiya), subtitr bilan")
ok(r["youtube"] is None and r["package"] and not r["package"].get("ok") and "missing" in r["package"], "YouTube o'chiq → avtomatik paket urinildi: matn/taqdimot yo'q — tayyorlanmadi")
st = r["state"]
ok(st["stage"] == "youtube" and st["owner"] == "oqituvchi" and "yetishmaydi" in st["next"], "Bosqich: video tayyor (YouTube o'chiq — fayl); paket uchun o'qituvchi matn/taqdimot yuklashi kerak")
ok(Q("SELECT status FROM st_jobs WHERE id=?", (J2,))[0]["status"] == "tasdiqlandi", "Vazifa tasdiqlandi")
ok(O.post(f"{P}/jobs/{J2}/approve").status_code == 409, "Ikkinchi marta tasdiqlash — 409")
ok(not STU._job_dir(JID).exists() and (STU._job_dir(J2) / "video.mp4").is_file(), "[9] Yangi montaj tasdiqlandi → «qayta» natija papkasi diskdan o'chirildi, joriysi qoldi")
ok(STU._purge_job_dir(J2, STU._asset_files(CID, 8)) and (STU._job_dir(J2) / "video.mp4").is_file() and (PK.store() / va[0]["path"]).read_bytes() == VIDEO,
   "[9] Asset bilan qattiq havoladagi video tozalovda o'chirilmaydi (inode / havolalar soni tekshiriladi)")

print("-- B6. Avtomatik paket (matn + taqdimot bor dars)")
X("UPDATE pk_packages SET status='qoralama' WHERE course_id=? AND topic_no=1 AND status='tayyor'", (MIK,))
def montage(cid, no, video=VIDEO, report=None):
    J(O.post(f"{P}/lessons/{cid}/{no}/raw?name=r.mp4&template=maruza_slayd", content=fake_mp4(30000, seed=no)))
    cj = J(WC.post(W + "/jobs/claim", headers=WH))
    assert cj["lesson"]["course_id"] == cid and cj["lesson"]["no"] == no, cj
    f = files(); f["video"] = ("v.mp4", video, "video/mp4")
    if report: f["report"] = ("r.json", json.dumps(report).encode(), "application/json")
    J(WC.post(f"{W}/jobs/{cj['job_id']}/result", headers=WH, files=f))
    return cj
cjm = montage(MIK, 1)
ok(cjm["slides_url"] is None or pdf_ok, "slides_url faqat PDF taqdimot bo'lsa")
n_before = Q("SELECT COUNT(*) n FROM pk_packages WHERE course_id=? AND topic_no=1", (MIK,))[0]["n"]
r = J(O.post(f"{P}/jobs/{cjm['job_id']}/approve"))
ok(r["package"] and r["package"]["ok"] and not r["package"]["unchanged"] and r["package"]["status"] == "tayyor", f"Avtomatik paket tayyorlandi: v{r['package'].get('version')} — tasdiq kutilmoqda")
pk_ = Q("SELECT * FROM pk_packages WHERE course_id=? AND topic_no=1 ORDER BY version DESC LIMIT 1", (MIK,))[0]
ok(Q("SELECT COUNT(*) n FROM pk_packages WHERE course_id=? AND topic_no=1", (MIK,))[0]["n"] == n_before + 1 and pk_["built_by_name"] == "Tizim", "pk_packages: yangi versiya, tizim nomidan")
import zipfile  # noqa: E402
with zipfile.ZipFile(PK.store() / pk_["file"]) as z:
    ok("assets/video/video.mp4" in z.namelist() and z.read("assets/video/video.mp4") == VIDEO, "Paket ichida — studiya videosi (fayl)")
ok(any(h["action"] == "avtomatik paket" and "tayyorlandi" in h["note"] for h in J(O.get(f"{P}/lessons/{MIK}/1"))["history"]), "Tarixda: «Paket avtomatik tayyorlandi»")
st = r["state"]
ok(st["stage"] == "paket" and st["owner"] == "masofaviy", "Bosqich: «Paket tayyor» → bo'lim tasdig'i")
ok(H.post(f"{P}/lessons/{MIK}/1/nextid", json={}).status_code == 409, "NEXTID belgisi — paket tasdiqlanmaguncha 409")
J(H.post(f"/api/paket/packages/{pk_['id']}/action", json={"action": "approve"}))
ok(J(H.get(f"{P}/lessons/{MIK}/1"))["state"]["stage"] == "tasdiq", "Paket tasdiqlandi → bosqich «Tasdiqlandi»")
ok(O.post(f"{P}/lessons/{MIK}/1/nextid", json={}).status_code == 403, "NEXTID belgisi — faqat bo'lim (operator 403)")
ok(J(H.post(f"{P}/lessons/{MIK}/1/nextid", json={}))["state"]["stage"] == "nextid", "«NEXTID'ga yuklandi» belgilandi — oxirgi bosqich")
ok(J(H.post(f"{P}/lessons/{MIK}/1/nextid", json={"undo": True}))["ok"] and J(H.get(f"{P}/lessons/{MIK}/1"))["state"]["stage"] == "tasdiq", "Belgini olib tashlash")

print("-- B7. Bosqichlarni hisoblash (derive, sof funksiya)")
now = dt.datetime(2026, 11, 13, 12, 0); SL = STU.sla()
D = lambda **k: STU.derive({"tracked": True, "plan_ts": "2026-11-01T09:00:00", **k}, now, SL, False)
ok(D()["stage"] == "bosh" and D()["over"] is False, "Hech narsa yo'q → «Ma'ruza tayyorlanmoqda» (14 kun ichida)")
ok(STU.derive({"tracked": True, "plan_ts": "2026-10-01T09:00:00"}, now, SL, False)["over"], "Reja sanasidan 14 kun o'tgan → qizil")
ok(STU.derive({"tracked": False, "plan_ts": None}, now, SL, False)["over"] is False, "Kuzatilmayotgan dars hech qachon qizil emas")
ok(D(r={"text": True, "slides": True})["stage"] == "maruza", "Matn + taqdimot → «Ma'ruza tayyor»")
bk = {"created_at": "2026-11-10T10:00:00", "start": "2026-11-12T09:00:00", "end": "2026-11-12T10:30:00"}
s = D(r={"text": True, "slides": True}, bk=bk)
ok(s["stage"] == "syomka_belgilandi" and s["due"] == "2026-11-13T10:30:00" and s["over"], "Band: muddat = syomka oxiri + 1 kun; o'tgan → qizil, egasi operator")
raw_ = {"id": 5, "ts": "2026-11-12T11:00:00"}
ok(D(raw=raw_)["stage"] == "syomka_qilindi", "Xom video bor, montaj yo'q → «Syomka qilindi»")
job = {"id": 9, "raw_id": 5, "status": "navbatda", "created_at": "2026-11-12T11:05:00", "pct": 0}
ok(D(raw=raw_, job=job)["stage"] == "montaj", "Montaj navbatida → «Montajda (AI)»")
ok(D(raw=raw_, job={**job, "status": "tayyor", "result_at": "2026-11-12T13:00:00"})["stage"] == "korib", "Natija bor → «Ko'rib chiqishda»")
aj = {**job, "status": "tasdiqlandi", "decided_at": "2026-11-12T14:00:00"}
s = STU.derive({"tracked": True, "raw": raw_, "job": aj, "yt": {"job_id": 9, "status": "yuklanmoqda"}, "r": {"video": True}}, now, SL, True)
ok(s["stage"] == "korib" and s["owner"] is None and "YouTube" in s["next"], "Tasdiqlangan, YouTube yuklanmoqda → hali «Ko'rib chiqishda», egasi — tizim")
s = STU.derive({"tracked": True, "raw": raw_, "job": aj, "yt": {"job_id": 9, "status": "xato", "error": "kvota"}, "r": {"video": True}}, now, SL, True)
ok(s["owner"] == "masofaviy" and "YouTube xatosi" in s["next"], "YouTube xatosi → egasi bo'lim")
s = STU.derive({"tracked": True, "raw": raw_, "job": aj, "yt": {"job_id": 9, "status": "tayyor", "done_at": "2026-11-12T15:00:00"}, "r": {"video": True, "text": True, "slides": True}},
               now, SL, True)
ok(s["stage"] == "youtube" and s["since"] == "2026-11-12T15:00:00", "YouTube'da tayyor → «YouTube'da» (vaqt — YouTube tugagan payt)")
ok(D(r={"video": True, "text": True, "slides": True}, raw=raw_, job=aj)["stage"] == "youtube", "YouTube o'chiq: tasdiqlangan fayl video → «YouTube'da» bosqichi")
last = {"id": 3, "status": "tayyor", "built_at": "2026-11-12T16:00:00"}
ok(D(r={"video": True}, last=last)["stage"] == "paket", "Paket «tayyor» → «Paket tayyor»")
lastA = {"id": 3, "status": "tasdiqlandi", "built_at": "2026-11-12T16:00:00", "approved_at": "2026-11-12T17:00:00"}
ok(D(last=lastA, appr=lastA)["stage"] == "tasdiq", "Tasdiqlangan → «Tasdiqlandi»")
ok(D(last=lastA, appr=lastA, mark={"ref": 3, "ts": "2026-11-12T18:00:00"})["stage"] == "nextid", "NEXTID belgisi (shu paketga) → oxirgi bosqich, qizil emas")
lastB = {**lastA, "id": 4}
ok(D(last=lastB, appr=lastB, mark={"ref": 3, "ts": "x"})["stage"] == "tasdiq", "Yangi versiya tasdiqlangan — eski NEXTID belgisi amal qilmaydi")
ok(D(last=lastA, appr=lastA, bk=bk)["stage"] == "syomka_belgilandi", "Qayta syomka (faol band) — studiya tsikli ma'lumot bosqichidan ustun")
ok(D(r={"video": True, "text": True, "slides": True}, last={"id": 2, "status": "qoralama", "note": "Ovoz yo'q", "built_at": "x"})["owner"] == "oqituvchi",
   "Bo'lim qaytargan paket → o'qituvchi")

print("-- B8. Eslatmalar (bir kun oldin, bugun, 1 soat oldin)")
nowp = STU._now()
soon = (nowp + dt.timedelta(minutes=40)).replace(second=0)
tom = (nowp + dt.timedelta(days=1)).replace(hour=10, minute=30, second=0)
for lk, t0 in ((9, soon), (10, tom)):
    X("""INSERT INTO st_bookings(room_id,course_id,lkey,teacher_id,start,end,status,created_at,created_name,updated_at)
         VALUES(?,?,?,?,?,?,'band',?,'test',?)""", (room["id"], CID, lk, own["teacher_id"], t0.isoformat(), (t0 + dt.timedelta(minutes=90)).isoformat(), nowp.isoformat(), nowp.isoformat()))
b_soon = Q("SELECT id FROM st_bookings WHERE course_id=? AND lkey=9 AND status='band'", (CID,))[0]["id"]
b_tom = Q("SELECT id FROM st_bookings WHERE course_id=? AND lkey=10 AND status='band'", (CID,))[0]["id"]
for nm, cl in (("o'qituvchi", TE), ("operator", O)):
    its = {it["id"]: it for it in J(cl.get("/api/mywork"))["items"]}
    a, b = its.get(f"st-b{b_soon}"), its.get(f"st-b{b_tom}")
    ok(a and a["title"].startswith("1 soatdan keyin syomka: L9") and a["priority"] == "high" and a["bucket"] in ("today", "overdue"), f"{nm}: «1 soatdan keyin syomka» (yuqori ustuvorlik)")
    if nm == "operator" and not b:          # operatorda 5 tadan ko'p bo'lsa — bitta jamlangan qator («st-day»), 1 soat ichidagilari alohida
        b = its.get("st-day"); ok(b and "syomka" in b["title"] and b["count"] >= 1, f"{nm}: kelgusi syomkalar — jamlangan qator")
    else:
        ok(b and b["title"].startswith("Ertaga syomka: L10") and b["link"]["view"] == "studio", f"{nm}: «Ertaga syomka»")
    nt = J(cl.get("/api/notifications"))["items"]
    ok(any(x["id"] == f"st-b{b_soon}" for x in nt), f"{nm}: qo'ng'iroqchada ham")
ok(not any(it["source"] == "studio" and it["id"].startswith("st-b") for it in J(RK.get("/api/mywork"))["items"]), "Rektorga syomka eslatmasi kelmaydi")

print("-- B9. Holat paneli va KPI raqamlari")
X("UPDATE st_bookings SET start=?, end=?, created_at=? WHERE id=?", ((nowp - dt.timedelta(days=4)).isoformat(), (nowp - dt.timedelta(days=4, minutes=-90)).isoformat(),
                                                                   (nowp - dt.timedelta(days=6)).isoformat(), b_tom))
bd = J(H.get(P + "/board"))
ok(sum(bd["totals"].values()) == bd["total"] == sum(r_["total"] for r_ in bd["rows"]), f"Jami: bosqichlar yig'indisi = qatorlar yig'indisi = {bd['total']}")
ok(bd["red_total"] == len(bd["red"]) == sum(r_["red"] for r_ in bd["rows"]) and bd["red_total"] >= 1, f"Qizil: {bd['red_total']} = ro'yxat = qatorlar")
ok(any(x["code"] == "L10" and x["course_id"] == CID and x["stage"] == "syomka_belgilandi" and x["days_over"] >= 2 for x in bd["red"]), "O'tgan syomka (L10) — qizil ro'yxatda, kechikish kunlari bilan")
states_ = STU.states(STU._courses(STU.tracked_courses()))
ok(bd["red_total"] == sum(1 for s in states_ if s["tracked"] and s["over"]), "Panel = states() hisobiga mos")
for grp in ("kafedra", "teacher"):
    g_ = J(H.get(P + "/board", params={"group": grp}))
    ok(g_["total"] == bd["total"] and g_["red_total"] == bd["red_total"], f"Guruhlash «{grp}»: jami va qizil o'zgarmaydi")
rb = J(RK.get(P + "/board"))
ok(rb["aggregate"] and rb["red_total"] == bd["red_total"] and all(set(x) <= {"course_id", "subject", "teacher", "dept", "lkey", "code", "title", "stage", "label",
                                                                              "owner_label", "next", "due", "days_over"} for x in rb["red"]),
   "Rektor: o'sha raqamlar, qizil belgilar — fayl/havolasiz")
k = J(RK.get(P + "/kpi"))
ok(k["value"] == bd["red_total"] and k["label"] == "Dars ishlab chiqarish" and "muddati o'tgan" in k["sub"] and k["bad"], f"Rektor KPI: «Dars ishlab chiqarish: {k['value']} ta muddati o'tgan»")
ok(any(it["id"] in (f"st-r{CID}-10", "st-red-montaj_operator") for it in J(O.get("/api/mywork"))["items"]), "Operator «Mening vazifalarim»: muddati o'tgan syomka")
bg = J(O.get("/api/bugun"))
ok([x["label"] for x in bg["kpis"]] == ["Bugungi syomkalar", "Montaj navbatida", "Ko'rib chiqish kutmoqda", "Muddati o'tgan"], "Operator bosh sahifasi: 4 ko'rsatkich")
J(H.post(P + "/sla", json={"sla": {"syomka_belgilandi": 10}}))
ok(J(H.get(P + "/board"))["red_total"] == bd["red_total"] - 1, "SLA o'zgartirildi (10 kun) → qizil kamaydi")
ok(O.post(P + "/sla", json={"sla": {"bosh": 3}}).status_code == 403, "SLA — faqat bo'lim boshlig'i")
J(H.post(P + "/sla", json={"sla": {"syomka_belgilandi": 1}}))

print("-- B10. YouTube yuklovchisi (soxta HTTP)")
CL_ID, CL_SEC, RTOK = "123456789-abcdefgh.apps.googleusercontent.com", "GOCSPX-sirli-qiymat-" + os.urandom(6).hex(), "1//0g-refresh-" + os.urandom(12).hex()
SECRETS = (CL_SEC, RTOK)
ok(TE.post(P + "/youtube", json={"refresh_token": RTOK}).status_code == 403 and O.post(P + "/youtube", json={"refresh_token": RTOK}).status_code == 403,
   "YouTube sirlari — o'qituvchi va operator kirita olmaydi (403)")
ok(H.post(P + "/youtube", json={"client_id": "noto'g'ri"}).status_code == 400, "Client ID ko'rinishi tekshiriladi (400)")
ys = J(H.post(P + "/youtube", json={"client_id": CL_ID, "client_secret": CL_SEC, "refresh_token": RTOK}))
ok(ys["changed"] == ["client_id", "client_secret", "refresh_token"] and ys["youtube"]["configured"] and ys["youtube"]["refresh_token"] is True, "Saqlandi: faqat «bor» belgilari qaytdi")
G = {"tok": 0, "sess": 0, "put": [], "fail_put": set(), "status": [], "meta": None, "auth": [], "mode": "ok", "privacy": "unlisted", "vid": "VID" + os.urandom(4).hex()[:8]}
SESSION = "https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&upload_id=SESS1"
STORE_BYTES = {}
def gh(req: httpx.Request):
    u = str(req.url)
    if u.startswith(YT.TOKEN_URL):
        G["tok"] += 1
        f = dict(x.split("=", 1) for x in req.content.decode().split("&"))
        assert f["grant_type"] == "refresh_token"
        if G["mode"] == "invalid_grant": return httpx.Response(400, json={"error": "invalid_grant", "error_description": "Token has been expired or revoked."})
        return httpx.Response(200, json={"access_token": f"ya29.at{G['tok']}", "expires_in": 3599, "token_type": "Bearer"})
    G["auth"].append(req.headers.get("authorization"))
    if req.method == "POST" and u.startswith(YT.UPLOAD_URL):
        if G["mode"] == "503start": return httpx.Response(503, json={"error": {"code": 503, "message": "backend"}})
        if G["mode"] == "quota": return httpx.Response(403, json={"error": {"code": 403, "message": "quota", "errors": [{"reason": "quotaExceeded", "domain": "youtube.quota"}]}})
        G["sess"] += 1; G["meta"] = json.loads(req.content); G["size"] = int(req.headers["x-upload-content-length"]); G["ctype"] = req.headers["x-upload-content-type"]
        STORE_BYTES.clear()
        return httpx.Response(200, headers={"Location": SESSION})
    if req.method == "PUT" and u == SESSION:
        cr = req.headers["content-range"]
        if cr.startswith("bytes */"):
            n = len(STORE_BYTES.get("b", b""))
            if G["mode"] == "lost": return httpx.Response(404, json={"error": {"code": 404, "message": "not found"}})
            return httpx.Response(308, headers={"Range": f"bytes=0-{n - 1}"} if n else {})
        m = re.match(r"bytes (\d+)-(\d+)/(\d+)", cr); a, b, tot = map(int, m.groups())
        if G["mode"] == "401once" and not G.get("did401"):
            G["did401"] = True; return httpx.Response(401, json={"error": {"code": 401, "message": "expired"}})
        if len(G["put"]) in G["fail_put"]:
            G["fail_put"].discard(len(G["put"])); G["put"].append(("fail", a, b)); return httpx.Response(503, json={"error": {"code": 503}})
        G["put"].append((a, b, len(req.content)))
        cur = STORE_BYTES.get("b", b"")
        assert a == len(cur), (a, len(cur))
        STORE_BYTES["b"] = cur + req.content
        if b + 1 < tot: return httpx.Response(308, headers={"Range": f"bytes=0-{b}"})
        return httpx.Response(200, json={"id": G["vid"], "status": {"uploadStatus": "uploaded", "privacyStatus": G["privacy"]}})
    if req.method == "GET" and u.startswith(YT.API + "/videos"):
        G["status"].append(1)
        us = "uploaded" if len(G["status"]) == 1 else "processed"
        return httpx.Response(200, json={"items": [{"id": G["vid"], "status": {"uploadStatus": us, "privacyStatus": G["privacy"]}}]})
    if req.method == "GET" and u.startswith(YT.API + "/channels"):
        return httpx.Response(200, json={"items": [{"id": "UCisft", "snippet": {"title": "ISFT Masofaviy"}}]})
    return httpx.Response(500, json={"error": "kutilmagan so'rov " + req.method + " " + u})
YT.TRANSPORT = httpx.MockTransport(gh); YT.reset_token()
t = J(H.post(P + "/youtube/test"))
ok(t["ok"] and t["channel"] == "ISFT Masofaviy", "Ulanishni tekshirish: token yangilandi, kanal nomi o'qildi")
YV = fake_mp4(600_000, seed=11)
REP3 = {**REPORT, "chapters": [{"start": 0, "title": "Kirish"}, {"start": 95, "title": "Talab va taklif"}, {"start": 3700, "title": "Xulosa"}]}
cjy = montage(MIK, 2, video=YV, report=REP3)
r = J(O.post(f"{P}/jobs/{cjy['job_id']}/approve"))
yid = r["youtube"]
ok(yid and Q("SELECT status FROM st_yt WHERE id=?", (yid,))[0]["status"] == "navbatda" and r["package"] is None, "YouTube sozlangan → tasdiqdan keyin yuklash navbatida (paket hali yig'ilmaydi)")
ok(r["state"]["stage"] == "korib" and r["state"]["owner"] is None, "Bosqich: YouTube yuklanguncha «Ko'rib chiqishda» (tizim)")
G["mode"] = "401once"; G["fail_put"] = {1}
t0 = STU._now()
res = STU.yt_tick(now=t0)
y = Q("SELECT * FROM st_yt WHERE id=?", (yid,))[0]
ok(res and y["status"] == "yuklanmoqda" and y["offset"] == 262144 and y["attempts"] == 1 and y["next_try"] > t0.isoformat(), "Bo'lak 2 da 503 → offset saqlandi (256 KiB), keyinroq qayta (backoff)")
ok(G["sess"] == 1 and G["tok"] >= 2, f"401 → token qayta yangilandi (jami {G['tok']} marta)")
ok(G["meta"]["status"]["privacyStatus"] == "unlisted" and G["meta"]["snippet"]["categoryId"] == "27" and G["ctype"] == "video/mp4" and G["size"] == len(YV),
   "Sessiya: unlisted, Ta'lim toifasi, X-Upload-Content-Length/-Type")
sub = Q("SELECT subject FROM dl_courses WHERE id=?", (MIK,))[0]["subject"]
lt = PK.lesson_info(Q("SELECT * FROM dl_courses WHERE id=?", (MIK,))[0], 2)["title"]
ok(G["meta"]["snippet"]["title"] == f"{sub} · L2: {lt}"[:100], f"Sarlavha: «{G['meta']['snippet']['title']}»")
desc = G["meta"]["snippet"]["description"]
ok("0:00 Kirish" in desc and "1:35 Talab va taklif" in desc and "1:01:40 Xulosa" in desc, "Tavsif: YouTube bo'limlari (0:00, 1:35, 1:01:40)")
ok(sub in G["meta"]["snippet"]["tags"] and "ISFT" in G["meta"]["snippet"]["tags"], "Teglar")
ok(all(a and a.startswith("Bearer ya29.") for a in G["auth"]), "Har so'rovda Bearer access token")
res = STU.yt_tick(now=dt.datetime.fromisoformat(y["next_try"]) + dt.timedelta(seconds=1))
y = Q("SELECT * FROM st_yt WHERE id=?", (yid,))[0]
ok(STORE_BYTES["b"] == YV and [p[0] for p in G["put"] if p[0] != "fail"] == [0, 262144, 524288], "Davom ettirildi (bytes */N → 308 Range): bo'laklar 0, 256K, 512K — fayl to'liq yetib bordi")
ok(y["status"] == "ishlanmoqda" and y["video_id"] == G["vid"], "Yuklandi → YouTube'da qayta ishlanmoqda (holat so'raladi)")
res = STU.yt_tick(now=dt.datetime.fromisoformat(y["next_try"]) + dt.timedelta(seconds=1))
y = Q("SELECT * FROM st_yt WHERE id=?", (yid,))[0]
tr = PK._topic_row(MIK, 2)
ok(y["status"] == "tayyor" and y["privacy"] == "unlisted" and PK.parse_video(tr.get("video_url") or "").get("video_id") == G["vid"], "processed → paketda YouTube havolasi")
ok(PK.topic_settings(MIK, 2)[0]["video_source"] == "youtube" and Q("SELECT COUNT(*) n FROM pk_assets WHERE course_id=? AND topic_no=2 AND purpose='video' AND deleted=0", (MIK,))[0]["n"] == 1,
   "video_source → YouTube, video fayl zaxirada qoldi")
st2 = J(O.get(f"{P}/lessons/{MIK}/2"))
ok(st2["state"]["stage"] in ("youtube", "paket") and any(h["action"] == "avtomatik paket" for h in st2["history"]), f"YouTube'da → avtomatik paket urinildi (bosqich: {st2['state']['label']})")
# xatolar: 503 (backoff), kvota (ertaga 13:05), sessiya yo'qoldi, invalid_grant, kunlik chegara, private
def new_yt():
    return X("""INSERT INTO st_yt(course_id,lkey,job_id,status,size,attempts,created_at,updated_at) VALUES(?,?,?,'navbatda',?,0,?,?)""",
             (MIK, 2, cjy["job_id"], len(YV), STU._now().isoformat(), STU._now().isoformat())).lastrowid
G["mode"] = "503start"; y2 = new_yt(); t0 = STU._now(); STU.yt_tick(now=t0)
y = Q("SELECT * FROM st_yt WHERE id=?", (y2,))[0]
ok(y["status"] == "navbatda" and y["attempts"] == 1 and "vaqtincha" in y["error"] and 55 <= (dt.datetime.fromisoformat(y["next_try"]) - t0).total_seconds() <= 65,
   "503 → qayta urinish 60 s dan keyin (eksponensial: 30·2^n)")
t1 = dt.datetime.fromisoformat(y["next_try"]) + dt.timedelta(seconds=1)
X("UPDATE st_yt SET attempts=4 WHERE id=?", (y2,)); STU.yt_tick(now=t1)
y = Q("SELECT * FROM st_yt WHERE id=?", (y2,))[0]
ok(y["attempts"] == 5 and (dt.datetime.fromisoformat(y["next_try"]) - t1).total_seconds() == 960, "5-urinish → 960 s kutish (backoff o'sadi)")
X("UPDATE st_yt SET attempts=7, next_try=NULL WHERE id=?", (y2,)); STU.yt_tick()
ok(Q("SELECT status FROM st_yt WHERE id=?", (y2,))[0]["status"] == "xato", f"{STU.YT_MAX_RETRY} urinishdan keyin — xato (operator qayta boshlaydi)")
G["mode"] = "quota"; y3 = new_yt(); t0 = STU._now().replace(hour=15); STU.yt_tick(now=t0)
y = Q("SELECT * FROM st_yt WHERE id=?", (y3,))[0]
ok(y["status"] == "kutilmoqda" and y["next_try"] == (t0 + dt.timedelta(days=1)).replace(hour=13, minute=5, second=0, microsecond=0).isoformat() and "kvota" in y["error"],
   "403 quotaExceeded → «Kvota — keyinroq», ertaga 13:05")
G["mode"] = "ok"; X("UPDATE st_yt SET status='xato' WHERE id IN (?,?)", (y2, y3))
J(O.post(f"{P}/youtube/{y3}/retry")); ok(Q("SELECT status, attempts FROM st_yt WHERE id=?", (y3,))[0] == {"status": "navbatda", "attempts": 0}, "Operator: YouTube qayta navbatga")
X("UPDATE st_yt SET status='xato' WHERE id=?", (y3,))
G["mode"] = "ok"; G["put"] = []; y4 = new_yt(); X("UPDATE st_yt SET session_url=?, status='yuklanmoqda', offset=1000 WHERE id=?", (SESSION, y4))
G["mode"] = "lost"; STU.yt_tick()
y = Q("SELECT * FROM st_yt WHERE id=?", (y4,))[0]
ok(y["session_url"] is None and y["offset"] == 0 and y["status"] == "navbatda", "Sessiya yo'qoldi (404) → yangidan boshlanadi")
X("UPDATE st_yt SET status='xato' WHERE id=?", (y4,))
G["mode"] = "invalid_grant"; YT.reset_token(); y5 = new_yt(); STU.yt_tick()
y = Q("SELECT * FROM st_yt WHERE id=?", (y5,))[0]
ok(y["status"] == "xato" and "Refresh token yaroqsiz" in y["error"], "invalid_grant → xato: «Refresh token yaroqsiz…» (o'zbekcha)")
ys = J(H.get(P + "/youtube"))
ok(ys["last_error"] and "Refresh token" in ys["last_error"]["error"], "Sozlamalarda oxirgi xato ko'rinadi")
ok(any(it["id"] == f"st-yt{y5}" for it in J(H.get("/api/mywork"))["items"]), "Bo'lim «Mening vazifalarim»: YouTube xatosi")
X("UPDATE st_yt SET status='xato' WHERE id=?", (y5,))
G["mode"] = "ok"; YT.reset_token(); os.environ["ISFT_CORE_YT_DAILY"] = "1"; y6 = new_yt(); STU.yt_tick()
y = Q("SELECT * FROM st_yt WHERE id=?", (y6,))[0]
ok(y["status"] == "kutilmoqda" and "Kunlik chegara" in y["error"], "ISFT_CORE_YT_DAILY chegarasi → ertaga")
os.environ.pop("ISFT_CORE_YT_DAILY"); X("UPDATE st_yt SET status='xato' WHERE id=?", (y6,))
G.update(mode="ok", put=[], status=[], privacy="private", vid="PRIV" + os.urandom(4).hex()[:7]); X("UPDATE pk_topics SET video_url=NULL WHERE course_id=? AND topic_no=2", (MIK,))
y7 = new_yt(); STU.yt_tick(); STU.yt_tick(now=STU._now() + dt.timedelta(minutes=2))
y = Q("SELECT * FROM st_yt WHERE id=?", (y7,))[0]
ok(y["status"] == "tayyor" and y["privacy"] == "private" and "private" in (y["warning"] or "") and not PK._topic_row(MIK, 2).get("video_url"),
   "YouTube «private» qilib qo'ysa — ogohlantirish, darsga havola qo'yilmaydi (fayl qoladi)")
# [4] processed, lekin darsga bog'lash yiqildi → «yuklandi_boglanmadi» (video_id saqlanadi); qayta urinish faqat bog'laydi, qayta yuklamaydi
X("UPDATE st_yt SET status='xato' WHERE id=?", (y7,))
G.update(mode="ok", put=[], status=[], privacy="unlisted", vid="LNK" + os.urandom(4).hex()[:8]); X("UPDATE pk_topics SET video_url=NULL WHERE course_id=? AND topic_no=2", (MIK,))
_orig_syt = PK.studio_set_youtube
def _bad_syt(*a, **k): raise RuntimeError("disk to'la (sinov)")
PK.studio_set_youtube = _bad_syt
try:
    y8 = new_yt(); STU.yt_tick(); t8 = STU._now() + dt.timedelta(minutes=2); STU.yt_tick(now=t8)
finally:
    PK.studio_set_youtube = _orig_syt
y = Q("SELECT * FROM st_yt WHERE id=?", (y8,))[0]
ok(y["status"] == "yuklandi_boglanmadi" and y["video_id"] == G["vid"] and "disk to'la" in (y["error"] or "") and y["next_try"] and not y["done_at"],
   "[4] Bog'lash yiqildi → «yuklandi_boglanmadi», haqiqiy xato matni, video_id saqlandi (tayyor EMAS)")
ok(not PK._topic_row(MIK, 2).get("video_url"), "[4] Havola darsga qo'yilmagan")
st8 = J(O.get(f"{P}/lessons/{MIK}/2"))["state"]
ok(st8["stage"] == "korib" and st8["owner"] == "masofaviy" and "bog'lanmadi" in st8["next"], "[4] Bosqich: ko'rib chiqishda, egasi — bo'lim («darsga bog'lanmadi»)")
ok(any(it["id"] == f"st-yt{y8}" for it in J(H.get("/api/mywork"))["items"]), "[4] Bo'lim «Mening vazifalarim»da")
sess0, put0, st0 = G["sess"], len(G["put"]), len(G["status"])
STU.yt_tick(now=dt.datetime.fromisoformat(y["next_try"]) + dt.timedelta(seconds=1))
y = Q("SELECT * FROM st_yt WHERE id=?", (y8,))[0]
ok(y["status"] == "tayyor" and PK.parse_video(PK._topic_row(MIK, 2).get("video_url") or "").get("video_id") == G["vid"], "[4] Qayta urinish → bog'landi, «tayyor»")
ok(G["sess"] == sess0 and len(G["put"]) == put0 and len(G["status"]) == st0, "[4] Qayta urinishda video QAYTA YUKLANMADI (sessiya/PUT/holat so'rovi yo'q)")
# [4] yt_tick catch-all: yuklangan videoni «xato» bilan yopmaydi; «tayyor» natija ustidan yozmaydi
y9 = new_yt(); X("UPDATE st_yt SET status='ishlanmoqda', video_id='VIDCATCH01', offset=size WHERE id=?", (y9,))
_orig_vs = YT.video_status
def _boom(*a, **k): raise KeyError("kutilmagan")
YT.video_status = _boom
try: STU.yt_tick()
finally: YT.video_status = _orig_vs
y = Q("SELECT * FROM st_yt WHERE id=?", (y9,))[0]
ok(y["status"] == "ishlanmoqda" and y["video_id"] == "VIDCATCH01" and y["attempts"] == 1 and "Ichki xato" in y["error"] and y["next_try"],
   "[4] Kutilmagan xato, video_id bor → «xato» EMAS: holat saqlanadi, keyinroq qayta (faqat holat so'rash)")
X("UPDATE st_yt SET status='xato' WHERE id=?", (y9,))
G.update(status=[], vid="TAY" + os.urandom(4).hex()[:8]); y10 = new_yt()
_orig_cl = STU.cleanup_lesson
def _cl_boom(*a, **k): raise OSError("tozalovda kutilmagan xato")
STU.cleanup_lesson = _cl_boom
try: STU.yt_tick(); STU.yt_tick(now=STU._now() + dt.timedelta(minutes=2))
finally: STU.cleanup_lesson = _orig_cl
y = Q("SELECT * FROM st_yt WHERE id=?", (y10,))[0]
ok(y["status"] == "tayyor" and y["video_id"] == G["vid"] and not y["error"], "[4] «tayyor»dan keyingi kutilmagan xato catch-all'da muvaffaqiyatli yuklash ustidan yozilmadi")
# [7] fon oqimidagi yozuvlar _lock ostida: qulf band bo'lsa _yt_upd kutadi
import threading  # noqa: E402
STU._lock.acquire()
th = threading.Thread(target=STU._yt_upd, args=(y10,), kwargs={"warning": "qulf sinovi"}); th.start(); th.join(0.3)
blocked = th.is_alive()
STU._lock.release(); th.join(5)
ok(blocked and not th.is_alive() and Q("SELECT warning FROM st_yt WHERE id=?", (y10,))[0]["warning"] == "qulf sinovi",
   "[7] _yt_upd (poller oqimi) umumiy ulanishga faqat _lock ostida yozadi")
# [3] YouTube o'chirildi (ISFT_CORE_YT_OFF) → yakunlanmagan navbat «bekor», dars fayl video bilan davom etadi (avtomatik paket)
yq = new_yt()
na = len([h for h in J(O.get(f"{P}/lessons/{MIK}/2"))["history"] if h["action"] == "avtomatik paket"])
ok(J(O.get(f"{P}/lessons/{MIK}/2"))["state"]["stage"] == "korib", "[3] YouTube navbatida — «Ko'rib chiqishda»")
os.environ["ISFT_CORE_YT_OFF"] = "1"
try: STU.yt_tick()
finally: os.environ.pop("ISFT_CORE_YT_OFF")
yr = Q("SELECT * FROM st_yt WHERE id=?", (yq,))[0]
lh = J(O.get(f"{P}/lessons/{MIK}/2"))
ok(yr["status"] == "bekor" and "YouTube" in (yr["error"] or ""), "[3] ISFT_CORE_YT_OFF → navbat qatori «bekor» (sababi bilan)")
ok(lh["state"]["stage"] != "korib" and len([h for h in lh["history"] if h["action"] == "avtomatik paket"]) == na + 1,
   f"[3] derive bekor qatorni kutmaydi (bosqich: {lh['state']['label']}); fayl video bilan avtomatik paket urinildi")
ok(Q("SELECT COUNT(*) n FROM st_yt WHERE status IN ('navbatda','yuklanmoqda','ishlanmoqda','kutilmoqda','xato')")[0]["n"] == 0, "[3] Yakunlanmagan YouTube qatori qolmadi")
yq2 = new_yt()
# sirlar hech qaysi javobda / audit jurnalida / bazada yo'q
for u in ("/api/studio/youtube", "/api/studio/settings", "/api/studio/meta", "/api/me"):
    SEEN.append(H.get(u).text)
SEEN.append(T(uid("it_head")).get("/api/studio/settings").text)
ok(not any(sx in txt for sx in SECRETS + (CL_ID,) for txt in SEEN), f"Sirlar {len(SEEN)} ta javobning hech birida yo'q")
aud = " ".join(r_["detail"] or "" for r_ in Q("SELECT detail FROM audit_log WHERE resource='studio'"))
ok(not any(sx in aud for sx in SECRETS), "Sirlar audit jurnalida yo'q")
with open(tmp / "jarvis.db", "rb") as fh: dbb = fh.read()
ok(not any(sx.encode() in dbb for sx in SECRETS + (CL_ID,)), "Sirlar bazada yo'q (secret_store — alohida)")
ok(not any(sx in json.dumps(STU.yt_status()) for sx in SECRETS), "yt_status() — faqat belgilar")
J(H.post(P + "/youtube/clear")); ok(not YT.configured(), "Sirlar o'chirildi → YouTube yana o'chiq")
ok(Q("SELECT status FROM st_yt WHERE id=?", (yq2,))[0]["status"] == "bekor" and J(O.get(f"{P}/lessons/{MIK}/2"))["state"]["stage"] != "korib",
   "[3] YouTube sozlamasi o'chirildi → navbatdagi qator darhol «bekor», dars ko'rib chiqishda osilmaydi")
ok(STU.yt_tick() == [], "Sozlanmagan YouTube — tick hech narsa qilmaydi")

print("-- B11. Xonalar sozlamasi va bo'limlar kaliti")
ok(TE.post(P + "/rooms", json={"name": "X", "open_from": "09:00", "open_to": "18:00", "slot_min": 60, "days": [1]}).status_code == 403, "O'qituvchi xona qo'sha olmaydi")
ok(O.post(P + "/rooms", json={"name": "X", "open_from": "18:00", "open_to": "09:00", "slot_min": 60, "days": [1]}).status_code == 400, "Ish vaqti noto'g'ri — 400")
ok(O.post(P + "/rooms", json={"name": "X", "open_from": "09:00", "open_to": "18:00", "slot_min": 50, "days": [1]}).status_code == 400, "Slot uzunligi ro'yxatdan — 400")
rr = J(O.post(P + "/rooms", json={"name": "Kichik studiya", "open_from": "10:00", "open_to": "16:00", "slot_min": 60, "days": [1, 2, 3, 4, 5]}))
ok(any(x["name"] == "Kichik studiya" and x["slot_min"] == 60 for x in rr["rooms"]), "Operator yangi xona qo'shdi (60 daqiqalik slotlar)")
rid0 = room["id"]
ok(O.post(P + "/rooms", json={"id": rid0, "name": "Studiya", "open_from": "09:00", "open_to": "18:00", "slot_min": 90, "days": [1, 2, 3, 4, 5, 6], "active": False}).status_code == 409,
   "Kelgusi bandi bor xonani o'chirib bo'lmaydi (409)")
from app import modules as MODS  # noqa: E402
ok(any(m["key"] == "studio" and m["default"] for m in MODS.MODULES) and MODS.on("studio"), "Bo'limlar kaliti: «studio» standart yoqilgan")

print("-- B13. Kod tekshiruvi tuzatishlari (regressiya)")
import asyncio, threading  # noqa: E402
def raw_of(jid): return Q("SELECT r.* FROM st_raw r JOIN st_jobs j ON j.raw_id=r.id WHERE j.id=?", (jid,))[0]
# [1] redo: tekshiruv yiqilsa (xom video yo'q) — ko'rib chiqilgan natija «tayyor» bo'lib qoladi
c13 = montage(CID, 13); j13 = c13["job_id"]
(STU.store() / raw_of(j13)["path"]).unlink()
n_jobs = Q("SELECT COUNT(*) n FROM st_jobs")[0]["n"]
r = O.post(f"{P}/jobs/{j13}/redo", json={"note": "Ovozni kuchaytiring"})
ok(r.status_code == 409 and Q("SELECT status, decided_at FROM st_jobs WHERE id=?", (j13,))[0] == {"status": "tayyor", "decided_at": None}
   and Q("SELECT COUNT(*) n FROM st_jobs")[0]["n"] == n_jobs, "[1] Qayta montaj tekshiruvi yiqildi (409) → vazifa «tayyor» qoldi, yangi vazifa yo'q")
ok((STU._job_dir(j13) / "video.mp4").is_file(), "[1] Natija fayllari joyida")
# [9] bekor qilingan vazifa natijasi o'chiriladi
J(O.post(f"{P}/jobs/{j13}/cancel"))
ok(not STU._job_dir(j13).exists(), "[9] Bekor qilingan montaj natijasi papkasi diskdan o'chirildi")
# [2] parallel tasdiqlash: bittasi 200, ikkinchisi 409; asset va YouTube qatori takrorlanmaydi
c11 = montage(CID, 11); j11 = c11["job_id"]
_orig_sv = PK.studio_set_video
def _slow_sv(*a, **k): time.sleep(0.4); return _orig_sv(*a, **k)
PK.studio_set_video = _slow_sv
O2 = T(uid("montaj_operator")); res2 = {}
def _ap(nm, cl): res2[nm] = cl.post(f"{P}/jobs/{j11}/approve").status_code
try:
    ths = [threading.Thread(target=_ap, args=(nm, cl)) for nm, cl in (("a", O), ("b", O2))]
    for t_ in ths: t_.start()
    for t_ in ths: t_.join(60)
finally:
    PK.studio_set_video = _orig_sv
ok(sorted(res2.values()) == [200, 409], f"[2] Ikki parallel tasdiq: {sorted(res2.values())} (biri 200, biri 409)")
ok(Q("SELECT COUNT(*) n FROM pk_assets WHERE course_id=? AND topic_no=11 AND purpose='video' AND src='studio'", (CID,))[0]["n"] == 1
   and Q("SELECT COUNT(*) n FROM st_log WHERE job_id=? AND action='montaj tasdiqlandi'", (j11,))[0]["n"] == 1, "[2] Video asset va tarix yozuvi — bittadan")
# [2] video darsga qo'yilmasa — vazifa «tayyor»ga qaytadi
c12 = montage(CID, 12); j12 = c12["job_id"]
def _bad_sv(*a, **k): raise PK.HTTPException(507, "Disk to'la (sinov)")
PK.studio_set_video = _bad_sv
try: r = O.post(f"{P}/jobs/{j12}/approve")
finally: PK.studio_set_video = _orig_sv
ok(r.status_code == 507 and Q("SELECT status, decided_by FROM st_jobs WHERE id=?", (j12,))[0] == {"status": "tayyor", "decided_by": None},
   "[2] Yon ta'sir yiqildi → vazifa «tayyor»ga qaytdi (qayta tasdiqlash mumkin)")
ok(J(O.post(f"{P}/jobs/{j12}/approve"))["ok"], "[2] Qayta tasdiqlash — 200")
# [5] claim: dars ma'lumoti olinmasa — vazifa «operator» (urinish/lease sarflanmaydi), keyingi vazifa beriladi
J(O.post(f"{P}/lessons/{CID}/14/raw?name=a.mp4&template=maruza_slayd", content=fake_mp4(9000, seed=14)))
J(O.post(f"{P}/lessons/{CID}/15/raw?name=b.mp4&template=maruza_slayd", content=fake_mp4(9000, seed=15)))
j14 = Q("SELECT id FROM st_jobs WHERE course_id=? AND lkey=14 AND status='navbatda'", (CID,))[0]["id"]
_orig_sl = PK.studio_lesson
def _sl(cid, no):
    if int(no) == 14: raise PK.HTTPException(400, "Dars (mavzu) raqami noto'g'ri — bunday dars kursda yo'q")
    return _orig_sl(cid, no)
PK.studio_lesson = _sl
try: cj15 = J(WC.post(W + "/jobs/claim", headers=WH))
finally: PK.studio_lesson = _orig_sl
jr14 = Q("SELECT * FROM st_jobs WHERE id=?", (j14,))[0]
ok(cj15["lesson"]["no"] == 15, "[5] Keyingi vazifa (L15) berildi")
ok(jr14["status"] == "operator" and jr14["attempts"] == 0 and jr14["lease_until"] is None and jr14["lease"] is None and "Dars ma'lumotini olib bo'lmadi" in jr14["error"],
   "[5] L14: «operator kerak», aniq xato, urinish va lease sarflanmadi")
J(WC.post(f"{W}/jobs/{cj15['job_id']}/fail", headers={**WH, "X-Worker-Lease": cj15["lease"]}, json={"error": STU.STOP_ERROR}))
# [8] xom video: dars (mavjud, L/A) va ruxsat tana o'qilishidan OLDIN tekshiriladi
octx = RB.Ctx(Q("SELECT * FROM users WHERE id=?", (uid("montaj_operator"),))[0], RB.ROLES["montaj_operator"], "web")
class _Rq:
    def __init__(self): self.headers, self.n = {}, 0
    async def stream(self):
        while True:
            self.n += 1; yield fake_mp4(65536)
_octx = STU._ctx; STU._ctx = lambda rq: octx
try:
    rq = _Rq()
    try: asyncio.run(STU.api_raw(CID, 999, rq, name="x.mp4")); code = 200
    except PK.HTTPException as e: code = e.status_code
    ok(code == 400 and rq.n == 0, f"[8] Mavjud bo'lmagan dars — {code}, tana o'qilmadi ({rq.n} bo'lak)")
    tctx = RB.Ctx(Q("SELECT * FROM users WHERE id=?", (teach_uid,))[0], RB.ROLES["oqituvchi"], "web"); STU._ctx = lambda rq: tctx
    rq = _Rq()
    try: asyncio.run(STU.api_raw(CID, 8, rq, name="x.mp4")); code = 200
    except Exception as e: code = getattr(e, "status_code", 403)
    ok(code == 403 and rq.n == 0, "[8] Ruxsatsiz (o'qituvchi) — 403, tana o'qilmadi")
finally:
    STU._ctx = _octx
# [9] xom video: dars videosi tasdiqlangach ISFT_CORE_RAW_KEEP_DAYS (14) kun saqlanadi, keyin davriy tozalovda o'chiriladi
rw = raw_of(cjm["job_id"]); fpath = STU.store() / rw["path"]
STU.sweep(force=True)
ok(fpath.is_file() and Q("SELECT deleted FROM st_raw WHERE id=?", (rw["id"],))[0]["deleted"] == 0, "[9] Tasdiqdan 14 kun o'tmagan — xom video saqlanadi")
X("UPDATE st_jobs SET decided_at=? WHERE id=?", ((STU._now() - dt.timedelta(days=15)).isoformat(), cjm["job_id"]))
sw = STU.sweep(force=True)
ok(not fpath.exists() and Q("SELECT deleted FROM st_raw WHERE id=?", (rw["id"],))[0]["deleted"] == 2 and sw["raw"] >= 1, f"[9] 15 kun o'tdi → xom video o'chirildi (tozalov: {sw})")
va1 = Q("SELECT path FROM pk_assets WHERE course_id=? AND topic_no=1 AND purpose='video' AND deleted=0", (MIK,))
ok(va1 and (PK.store() / va1[0]["path"]).read_bytes() == VIDEO, "[9] Darsning video fayli (asset) tegilmadi")
ok(raw_of(j11)["path"] and (STU.store() / raw_of(j11)["path"]).is_file(), "[9] Yangi tasdiqlangan darsning xom videosi qoldi")
# [10] umumiy yordamchilar paketdan
ok(STU._short is PK._short and STU._ascii is PK._ascii and STU._stream_upload is PK._stream_upload and STU.range_response is PK.range_response,
   "[10] _short, _ascii, oqimli yuklash va Range javobi — app/paket.py dan (nusxa emas)")

print("-- B12. Fayllar va JS")
sj = (ROOT / "static" / "studio.js").read_text(encoding="utf-8")
ok("function renderStudio" in sj and "/api/studio/meta" in sj, "static/studio.js: renderStudio")
ix = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
ok('data-v="studio"' in ix and 'id="v-studio"' in ix and 'src="studio.js"' in ix, "index.html: menyu bandi, bo'lim, skript")
ok((ROOT / "docs" / "studio.md").is_file() and "X-Worker-Token" in (ROOT / "docs" / "studio.md").read_text(encoding="utf-8"), "docs/studio.md: ishchi API kontrakti")

YT.TRANSPORT = None
shutil.rmtree(tmp, ignore_errors=True)
print(f"\n{'XATO: ' + str(len(fails)) + ' ta' if fails else 'Hammasi o`tdi'}")
sys.exit(1 if fails else 0)
