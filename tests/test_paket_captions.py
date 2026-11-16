"""Dars paketi: AVTOMATIK SUBTITR (app/paket_captions.py) — ruxsatlar, YouTube / video yo'q / ishchi yo'q holatlari, navbat (idempotent),
kurs ishchi yo'llari orqali claim / media (Range) / progress / fail / result, natija → darsning «subs» fayli, yig'ish (zipda .vtt va content.json
video.captions, pleyerda <track>), mavzu sozlamasi auto_captions (tekshiruv + video yuklangach avtomatik navbat), qo'lda subtitr ustuvorligi,
video almashtirilganda eskirgan natija, kurs navbati bilan birga ishlash.

Soxta ishchi: ISFT_CORE_WORKER_TOKEN shu jarayonda; "ishchi" — TestClient (X-Worker-Token). Haqiqiy Whisper kerak emas.
Hamma narsa JARAYON ICHIDA: bazaning NUSXASI (vaqtinchalik katalog) + to'liq ilova — server bazasiga tegmaydi.

Ishga tushirish:  ISFT_CORE_DB=data/jarvis.db .venv/bin/python tests/test_paket_captions.py   (yoki: python tests/run_all.py --only paket_captions)
"""
import io, json, os, re, shutil, sqlite3, subprocess, sys, tempfile, zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DBP = Path(os.environ.get("ISFT_CORE_DB") or ROOT / "data" / "jarvis.db")
PW = re.search(r'DEMO_PASSWORD = os.getenv\("ISFT_CORE_DEMO_PASSWORD", "([^"]+)"\)', (ROOT / "app" / "rbac.py").read_text()).group(1)

CHILD = r'''
import contextlib, io, json, os, sqlite3, sys, zipfile
from pathlib import Path
sys.path.insert(0, os.environ["ROOT"])
with contextlib.redirect_stdout(io.StringIO()):
    from app import main as APP
from fastapi.testclient import TestClient
from app import paket as PK, paket_captions as PC, kurs as K, db as DB
TOKEN = "pk-ishchi-" + os.environ["RND"]
def ok(c, m): print(("✓ " if c else "✗ ") + m)
assert str(PK.store()).startswith(os.environ["ISFT_CORE_DATA_DIR"]), "nusxa emas"
P, W = "/api/paket", "/api/montaj/kurs-captions"
def login(role, where="", args=()):
    r = DB.rows(APP.con, f"SELECT id FROM users WHERE role=? {where} ORDER BY id LIMIT 1", (role, *args)); assert r, role
    c = TestClient(APP.app, base_url="http://testserver")
    assert c.post("/api/login", json={"user_id": r[0]["id"], "password": os.environ["ISFT_PW"]}).status_code == 200
    return c, r[0]["id"]
head, _ = login("masofaviy"); teach, tuid = login("oqituvchi"); kaf, _ = login("kafedra"); rek, _ = login("rektor")
tid = DB.one(APP.con, "SELECT teacher_id FROM users WHERE id=?", (tuid,))["teacher_id"]
own = DB.one(APP.con, "SELECT * FROM dl_courses WHERE teacher_id=? ORDER BY id LIMIT 1", (tid,))
foreign = DB.one(APP.con, "SELECT * FROM dl_courses WHERE teacher_id!=? ORDER BY id LIMIT 1", (tid,))
cid = own["id"]; U = lambda no: f"{P}/courses/{cid}/topics/{no}"
os.environ.pop("ISFT_CORE_WORKER_TOKEN", None)
APP.con.execute("UPDATE ku_caption_jobs SET status='bekor' WHERE status IN ('navbatda','ishlanmoqda')"); APP.con.commit()
MP4 = b"\x00\x00\x00\x20ftypisom\x00\x00\x02\x00isomiso2avc1mp41" + bytes(range(256)) * 40
VTT = "WEBVTT\n\n1\n00:00:00.200 --> 00:00:02.000\nAssalomu alaykum.\n\n2\n00:00:02.100 --> 00:00:04.000\nBugun yangi mavzu.\n"
cap = lambda c, no, lang="uz": c.post(U(no) + "/captions/auto", json={"lang": lang})
WH = {"X-Worker-Token": TOKEN}
WC = TestClient(APP.app, base_url="http://testserver")

# --- ruxsatlar va ko'lam
ok(kaf.post(U(2) + "/captions/auto", json={}).status_code == 403 and rek.post(U(2) + "/captions/auto", json={}).status_code == 403, "Kafedra mudiri va rektor — 403 (faqat o'qituvchi / bo'lim)")
ok(teach.post(f"{P}/courses/{foreign['id']}/topics/2/captions/auto", json={}).status_code == 403, "O'qituvchi begona kursga — 403")
ok(teach.post(U(999) + "/captions/auto", json={}).status_code == 400, "Noma'lum dars raqami — 400")
ok(cap(teach, 2, "xx").status_code == 400, "Noma'lum til — 400")
ok(head.post(U(2) + "/captions/auto", json={}).status_code == 200, "Bo'lim boshlig'i — ruxsat")

# --- video fayl yo'q / YouTube / ishchi yo'q
t = teach.post(U(5) + "/captions/auto", json={"lang": "uz"}).json()
ok(t["ok"] is False and t["state"] == "unavailable" and "avval video fayl" in t["message"], f"Video fayl yo'q — unavailable ({t.get('message', '')[:50]})")
teach.post(U(3) + "/video", json={"url": "https://youtu.be/dQw4w9WgXcQ"})
t = cap(teach, 3).json()
ok(t["ok"] is False and t["state"] == "unavailable" and t["message"] == "YouTube videosiga avtomatik subtitr qo'yib bo'lmaydi — .srt/.vtt yuklang", "YouTube havolasi — unavailable, aniq xabar")
g3 = teach.get(U(3) + "/captions/auto").json()
ok(g3["state"] == "unavailable" and g3["has_file"] is False, "GET holat: YouTube — unavailable")
r = teach.post(U(2) + "/video/file", params={"name": "dars2.mp4"}, content=MP4)
ok(r.status_code == 200 and r.json()["kind"] == "mp4" and "auto_captions" not in r.json(), "Video fayl yuklandi (auto_captions o'chiq — navbat yo'q)")
ok(not PC.worker_on(), "Ishchi tokeni sozlanmagan")
t = cap(teach, 2).json()
ok(t["ok"] is False and t["state"] == "unavailable" and t["reason"] == "no_worker" and "sozlanmagan" in t["message"], f"Ishchi yo'q — unavailable, aniq o'zbekcha xabar")
ok(DB.one(APP.con, "SELECT COUNT(*) n FROM pk_caption_jobs")["n"] == 0, "Ishchi yo'q — vazifa yaratilmadi (soxta natija yo'q)")
ok(WC.post(W + "/claim", headers=WH).status_code == 503, "Ishchi tokeni yo'q — claim 503")
vd = teach.get(U(2)).json()["ready"]["video"]
ok(vd["file"] and vd["captions"] == [] and vd["captions_job"] is None, "GET mavzu: ready.video.captions_job — vazifa yo'q (None)")

# --- navbat (ishchi yoqildi)
os.environ["ISFT_CORE_WORKER_TOKEN"] = TOKEN
t = cap(teach, 2).json()
ok(t["ok"] and t["state"] == "queued" and t["job_id"] and t["message"].startswith("Subtitr navbatga qo'yildi") and t["existing"] is False, f"Video fayl — queued ({t})")
jid = t["job_id"]
t2 = cap(teach, 2).json()
ok(t2["ok"] and t2["state"] == "queued" and t2["job_id"] == jid and t2["existing"] is True, "Ikkinchi so'rov — idempotent (o'sha vazifa)")
ok(DB.one(APP.con, "SELECT COUNT(*) n FROM pk_caption_jobs")["n"] == 1, "Bazada bitta vazifa")
vd = teach.get(U(2)).json()["ready"]["video"]
ok(vd["captions_job"]["state"] == "queued" and vd["captions_job"]["job_id"] == jid and vd["captions_job"]["message"], "GET mavzu: ready.video.captions_job {state, message, job_id}")
g = teach.get(U(2) + "/captions/auto").json()
ok(g["state"] == "queued" and g["job_id"] == jid and g["worker"] is True and g["can_request"] is True, "GET holat: queued")
ok(kaf.get(U(2) + "/captions/auto").status_code in (200, 403) and rek.get(U(2) + "/captions/auto").status_code == 403, "Holatni rektor ko'rmaydi (403)")

# --- ishchi: kurs yo'llari orqali (paket vazifasi raqami >= 10^9)
ok(WC.post(W + "/claim").status_code == 401 and WC.post(W + "/claim", headers={"X-Worker-Token": TOKEN + "x"}).status_code == 401, "Tokensiz / noto'g'ri token — 401")
c = WC.post(W + "/claim", headers=WH).json()
ok(c["kind"] == "captions" and c["job_id"] == PC.JOB_BASE + jid and c["lang"] == "uz" and len(c["lease"]) == 16 and c["media_url"] == f"{W}/{c['job_id']}/media" and c["media_ext"] == ".mp4",
   f"claim: paket vazifasi (raqam = 10^9 + {jid}), til, lease, media_url")
ok(WC.post(W + "/claim", headers=WH).status_code == 204, "Boshqa vazifa yo'q — 204")
m = WC.get(c["media_url"], headers={**WH, "Range": "bytes=4-11"})
ok(m.status_code == 206 and m.content == MP4[4:12] and WC.get(c["media_url"]).status_code == 401, "Video — token bilan, Range (206); tokensiz — 401")
ok(teach.get(U(2) + "/captions/auto").json()["state"] == "running", "Holat: running")
L = {**WH, "X-Worker-Lease": c["lease"]}
ok(WC.post(f"{W}/{c['job_id']}/progress", headers={**WH, "X-Worker-Lease": "0" * 16}, json={"stage": "nutq", "pct": 40}).status_code == 409, "Eskirgan lease — 409")
ok(WC.post(f"{W}/{c['job_id']}/progress", headers=L, json={"stage": "nutq", "pct": 40}).status_code == 200
   and teach.get(U(2) + "/captions/auto").json()["pct"] == 40 and "40%" in teach.get(U(2) + "/captions/auto").json()["message"], "progress: foiz va xabar ko'rinadi")
ok(WC.post(f"{W}/{c['job_id']}/result", headers={**L, "Content-Type": "text/vtt"}, content=b"not a vtt").status_code == 400
   and teach.get(U(2) + "/captions/auto").json()["state"] == "running", "Buzilgan VTT — 400 (vazifa ochiq qoladi)")
rr = WC.post(f"{W}/{c['job_id']}/result", headers={**L, "Content-Type": "text/vtt"}, content=VTT.encode())
ok(rr.status_code == 200 and rr.json()["cues"] == 2 and rr.json()["asset"], f"result: 2 yozuv ({rr.text[:80]})")
ok(WC.post(f"{W}/{c['job_id']}/result", headers=L, content=VTT.encode()).status_code == 410, "Qayta natija — 410 (idempotent, ikkinchi fayl yo'q)")
subs = DB.rows(APP.con, "SELECT * FROM pk_assets WHERE course_id=? AND topic_no=2 AND purpose='subs' AND deleted=0", (cid,))
sm = json.loads(subs[0]["meta"]) if subs else {}
ok(len(subs) == 1 and sm.get("lang") == "uz" and sm.get("auto") == "whisper" and sm.get("cues") == 2 and "(avto)" in sm.get("label", "") and (PK.store() / subs[0]["path"]).read_text().startswith("WEBVTT"),
   "Natija — darsning subs fayli (lang=uz, auto=whisper, «O'zbekcha (avto)»)")
vd = teach.get(U(2)).json()["ready"]["video"]
ok([x["lang"] for x in vd["captions"]] == ["uz"] and vd["captions"][0]["auto"] == "whisper" and vd["captions_job"]["state"] == "done" and vd["captions_job"]["cues"] == 2, "GET mavzu: captions[uz, auto], captions_job = done")
ok(cap(teach, 2).json()["state"] == "exists" and teach.get(U(2) + "/captions/auto").json()["state"] == "exists", "Shu tilda subtitr bor — exists")
ok(DB.one(APP.con, "SELECT COUNT(*) n FROM pk_caption_jobs")["n"] == 1, "exists — yangi vazifa yaratilmadi")

# --- yig'ish: zipda .vtt, content.json captions, pleyerda <track>
b = teach.post(U(2) + "/build", json={"mode": "none"})
ok(b.status_code == 200, f"Paket yig'ildi ({b.status_code} {b.text[:100] if b.status_code != 200 else ''})")
if b.status_code == 200:
    prow = DB.one(APP.con, "SELECT * FROM pk_packages WHERE id=?", (b.json()["package"]["id"],))
    z = zipfile.ZipFile(PK.store() / prow["file"]); names = set(z.namelist()); cj = json.loads(z.read("content.json"))
    vb = next(x for x in cj["blocks"] if x["type"] == "video")
    ok("assets/video/video.uz.vtt" in names and z.read("assets/video/video.uz.vtt").decode().startswith("WEBVTT") and "Assalomu alaykum." in z.read("assets/video/video.uz.vtt").decode(),
       "Zipda assets/video/video.uz.vtt (Whisper matni)")
    ok(vb["provider"] == "file" and vb["captions"] == [{"lang": "uz", "label": "O'zbekcha (avto)", "src": "assets/video/video.uz.vtt"}], f"content.json video.captions: {vb['captions']}")
    ok("el('track'" in z.read("player.js").decode("utf-8", "replace") and b.json()["validation"]["ok"], "Pleyer captions[] dan <track> chizadi; validate_zip o'tdi")

# --- mavzu sozlamasi auto_captions: tekshiruv va yuklangach avtomatik navbat
ok(teach.get(U(4)).json()["settings"]["auto_captions"] is False, "auto_captions — standart False")
base = {"mode": "xapi", "completion": "view_all"}
ok(teach.post(U(4) + "/settings", json={**base, "auto_captions": "xyz"}).status_code == 422, "auto_captions noto'g'ri qiymat — 422")
ok(teach.post(U(4) + "/settings", json={**base, "auto_captions": True}).json()["settings"]["auto_captions"] is True and teach.get(U(4)).json()["settings"]["auto_captions"] is True, "auto_captions = True saqlandi")
ok(PK._clean_settings({"auto_captions": 1}, PK.DEFAULTS)["auto_captions"] is True and PK._clean_settings({}, PK.DEFAULTS)["auto_captions"] is False, "_clean_settings: bool")
r = teach.post(U(4) + "/video/file", params={"name": "dars4.mp4"}, content=MP4 + b"1")
ac = r.json().get("auto_captions") or {}
ok(r.status_code == 200 and ac.get("state") == "queued" and ac.get("job_id") and ac.get("auto") is True, f"Video yuklangach avtomatik navbatga ({ac.get('state')})")
ok(teach.get(U(4)).json()["ready"]["video"]["captions_job"]["state"] == "queued", "Mavzuda captions_job = queued")
# video almashtirildi → eskirgan vazifa natijasi qabul qilinmaydi (yangi video uchun yangi vazifa)
c4 = WC.post(W + "/claim", headers=WH).json()
r = teach.post(U(4) + "/video/file", params={"name": "dars4-yangi.mp4"}, content=MP4 + b"22")
ok(r.json().get("auto_captions", {}).get("state") == "queued" and r.json()["auto_captions"]["job_id"] != ac["job_id"], "Video almashtirildi — yangi video uchun yangi vazifa")
rr = WC.post(f"{W}/{c4['job_id']}/result", headers={**WH, "X-Worker-Lease": c4["lease"]}, content=VTT.encode())
ok(rr.status_code == 410 and not DB.rows(APP.con, "SELECT 1 FROM pk_assets WHERE course_id=? AND topic_no=4 AND purpose='subs' AND deleted=0", (cid,)), "Eski video uchun natija — 410, subtitr qo'shilmadi")

# --- qo'lda yuklangan subtitr ustuvor; ishchi xatosi; bekor qilish
r = teach.post(U(6) + "/video/file", params={"name": "d6.mp4"}, content=MP4 + b"6")
j6 = cap(teach, 6).json()["job_id"]
man = teach.post(U(6) + "/video/captions", params={"name": "qolda.vtt", "lang": "uz"}, content=VTT.replace("yangi", "QOLDA").encode())
ok(man.status_code == 200 and cap(teach, 6).json()["state"] in ("exists", "queued"), "Qo'lda subtitr yuklandi")
c6 = WC.post(W + "/claim", headers=WH)
# navbatdagi birinchi vazifa (4-dars, yangi video) birinchi olinadi — uni xato bilan yopamiz
cj4 = c6.json()
ok(cj4["job_id"] != PC.JOB_BASE + j6, "claim tartibi: avval navbatdagi eski vazifa (FIFO)")
ok(WC.post(f"{W}/{cj4['job_id']}/fail", headers={**WH, "X-Worker-Lease": cj4["lease"]}, json={"error": "Videoda nutq topilmadi"}).status_code == 200
   and teach.get(U(4) + "/captions/auto").json()["state"] == "failed" and "nutq topilmadi" in teach.get(U(4) + "/captions/auto").json()["message"], "fail: xato matni holatda")
cc = WC.post(W + "/claim", headers=WH).json()
ok(cc["job_id"] == PC.JOB_BASE + j6, "6-dars vazifasi olindi")
rr = WC.post(f"{W}/{cc['job_id']}/result", headers={**WH, "X-Worker-Lease": cc["lease"]}, content=VTT.encode())
cur = [x for x in DB.rows(APP.con, "SELECT * FROM pk_assets WHERE course_id=? AND topic_no=6 AND purpose='subs' AND deleted=0", (cid,)) if json.loads(x["meta"]).get("lang") == "uz"]
ok(rr.status_code == 200 and rr.json().get("skipped") and len(cur) == 1 and "QOLDA" in (PK.store() / cur[0]["path"]).read_text() and json.loads(cur[0]["meta"]).get("auto") != "whisper",
   "Qo'lda yuklangan subtitr avtomatik bilan almashtirilmaydi")
rq = cap(teach, 4).json()
ok(rq["state"] == "queued" and teach.post(U(4) + "/captions/auto/cancel", json={"lang": "uz"}).json()["cancelled"] >= 1 and teach.get(U(4) + "/captions/auto").json()["state"] in ("none", "failed"), "Bekor qilish")

# --- kurs navbati bilan birga: kurs vazifasi avval, paket keyin; kurs yo'llari buzilmagan
cc_id = head.post("/api/kurs/courses", json={"title": "Subtitr aralash"}).json()["id"]
kv = head.post(f"/api/kurs/courses/{cc_id}/assets?kind=video&name=v.mp4", content=MP4 + b"k").json()["id"]
kj = head.post(f"/api/kurs/courses/{cc_id}/captions", json={"asset": kv, "lang": "uz"}).json()["job"]
pj = cap(teach, 4).json()["job_id"]
first = WC.post(W + "/claim", headers=WH).json(); second = WC.post(W + "/claim", headers=WH).json()
ok(first["job_id"] == kj["id"] and second["job_id"] == PC.JOB_BASE + pj, "Aralash navbat: avval kurs vazifasi, keyin paket vazifasi")
ok(WC.post(f"{W}/{first['job_id']}/result", headers={**WH, "X-Worker-Lease": first["lease"]}, content=VTT.encode()).json().get("attached") == 0, "Kurs vazifasi natijasi — eski yo'lda (kurs.cap_result)")
ok(WC.post(f"{W}/{second['job_id']}/fail", headers={**WH, "X-Worker-Lease": second["lease"]}, json={"error": "x"}).status_code == 200, "Paket vazifasi fail — kurs yo'li orqali")
au = DB.one(APP.con, "SELECT COUNT(*) n FROM audit_log WHERE action LIKE 'paket subtitr:%'")["n"]
ok(au >= 6, f"Ishchi amallari audit jurnalida ({au})")
ok(DB.one(APP.con, "SELECT COUNT(*) n FROM audit_log WHERE action='paket: avto-subtitr navbatga'")["n"] >= 3, "Navbatga qo'yish audit jurnalida")
'''

if len(sys.argv) > 1 and sys.argv[1] == "--child":
    exec(compile(CHILD, "paket_captions_child", "exec")); sys.exit(0)

fails = []
def ok(cond, msg):
    print(("  ✓ " if cond else "  ✗ ") + msg)
    if not cond: fails.append(msg)

print("== Avtomatik subtitr (jarayon ichida: bazaning nusxasi, soxta ishchi)")
wtmp = Path(tempfile.mkdtemp(prefix="pk-cap-"))
try:
    s_, d_ = sqlite3.connect(DBP), sqlite3.connect(wtmp / "jarvis.db"); s_.backup(d_); s_.close(); d_.close()
    wenv = dict(os.environ, ROOT=str(ROOT), ISFT_CORE_DATA_DIR=str(wtmp), ISFT_CORE_DB=str(wtmp / "jarvis.db"), ISFT_CORE_SECRETS_DIR=str(wtmp / "secrets"),
                ISFT_CORE_FILES_DIR=str(wtmp / "portal_files"), ISFT_CORE_STAFFABS_DIR=str(wtmp / "staffabs_files"), RND=os.urandom(6).hex(), ISFT_PW=PW)
    wenv.pop("ISFT_CORE_WORKER_TOKEN", None)
    rr = subprocess.run([sys.executable, str(Path(__file__).resolve()), "--child"], cwd=str(wtmp), env=wenv, capture_output=True, text=True, timeout=600)
    lines = [ln.strip() for ln in rr.stdout.splitlines() if ln.strip()[:1] in ("✓", "✗")]
    for ln in lines: ok(ln.startswith("✓"), ln[1:].strip())
    ok(rr.returncode == 0 and len(lines) >= 40, f"Jarayon ({rr.returncode}, {len(lines)} tekshiruv)" + ("" if rr.returncode == 0 else ":\n" + "\n".join((rr.stdout + rr.stderr).splitlines()[-25:])))
finally:
    shutil.rmtree(wtmp, ignore_errors=True)

print()
if fails:
    print(f"XATO: {len(fails)} ta tekshiruv o'tmadi"); sys.exit(1)
print("Hammasi o'tdi")
