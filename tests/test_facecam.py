"""Kirish nazorati (Face ID): HTTP (jonli server http://127.0.0.1:8000) + ulagich (emulyator) + mantiq (vaqtinchalik baza nusxasi).

Ishga tushirish:  .venv/bin/python tests/test_facecam.py
Qayta ishga tushirish mumkin (qayta seed shart emas). Jonli bazaga yozadigan yagona joy — rozilik oqimi testi: test o'zi tanlagan
(demo ro'yxatida bo'lmagan) bitta xodimni ro'yxatga oladi, sinov voqealarini yozadi va roziligini qaytarib oladi; oxirida sinov
voqealari o'chiriladi, reyestr yozuvi "rozilik qaytarib olingan" holatida qoladi (audit izi). Boshqa tekshiruvlar faqat o'qiydi;
mantiq testlari baza nusxasida. Har ishga tushirishda Hujjatlar markazida 1 ta KRN-… hisobot yaratiladi.
"""
import asyncio, datetime as dt, io, json, os, random, sqlite3, subprocess, sys, tempfile, time, zipfile
from pathlib import Path
import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT)); from app import clock as CLK   # noqa: E402 — institut vaqti (ISFT_CORE_TZ / ISFT_CORE_FAKE_TODAY), server bilan bir xil
sys.path.insert(0, str(ROOT))
DB = Path(os.environ.get("ISFT_CORE_DB") or ROOT / "data" / "jarvis.db")
B = os.environ.get("ISFT_TEST_URL", "http://127.0.0.1:8000")
PW = "Isft2026"
PY = sys.executable   # joriy interpretator (lokal .venv yoki CI)
N = [0]

def ok(cond, msg):
    N[0] += 1
    print(("✓ " if cond else "✗ XATO: ") + msg)
    if not cond: sys.exit(1)

def S(uid):
    c = httpx.Client(base_url=B, timeout=90)
    r = c.post("/api/login", json={"user_id": uid, "password": PW})
    assert r.status_code == 200, f"login {uid}: {r.status_code} {r.text}"
    return c

def q(sql, args=()):
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    try: return con.execute(sql, args).fetchall()
    finally: con.close()

def run_py(code: str) -> str:
    r = subprocess.run([PY, "-c", code], cwd=ROOT, capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stderr[-2000:]
    return r.stdout.strip().splitlines()[-1] if r.stdout.strip() else ""

from app import hikvision as HK                                     # noqa: E402

# =====================================================================
print("\n— A. Hikvision: yuz voqeasini o'qish (alarmResult JSON, eski XML, multipart oqim) —")
SAMPLE = {   # DeepinView yuzni solishtirish voqeasi (alertStream JSON qismi) — Hikvision ISAPI ko'rinishiga yaqin namuna
    "ipAddress": "10.10.1.21", "portNo": 80, "protocol": "HTTP", "macAddress": "44:19:b6:2a:10:01", "channelID": 1,
    "dateTime": "2026-11-09T08:12:33+05:00", "activePostCount": 1, "eventType": "alarmResult", "eventState": "active", "eventDescription": "alarmResult",
    "alarmResult": [{"targetAttrs": {"deviceName": "Bosh kirish", "deviceChannel": 1, "faceTime": "2026-11-09T08:12:33+05:00",
                                     "bkgUrl": "http://10.10.1.21/picture/Streaming/tracks/203/?name=ch00001_00000000123&size=184320"},
                     "faces": [{"faceId": 1, "faceRect": {"height": 0.153, "width": 0.066, "x": 0.512, "y": 0.268},
                                "URL": "http://10.10.1.21/picture/Streaming/tracks/203/?name=ch00001_00000000124", "age": {"range": 5, "value": 21},
                                "identify": [{"maxsimilarity": 0.94, "candidate": [
                                    {"blacklist_id": 1, "similarity": 0.81, "reserve_field": {"FDID": "1", "FPID": "FP00000000AA"}},
                                    {"blacklist_id": 1, "similarity": 0.94, "reserve_field": {"FDID": "1", "FPID": "FP9A31C0D2E1"}}]}]},
                               {"faceId": 2, "faceRect": {"height": 0.12, "width": 0.05, "x": 0.2, "y": 0.3}, "identify": []}]}]}
evs = HK.parse_json_alert(json.dumps(SAMPLE))
ok(len(evs) == 2 and evs[0]["type"] == "alarmResult", f"alarmResult: har bir yuz alohida voqea ({len(evs)} ta)")
ok(evs[0]["fpid"] == "FP9A31C0D2E1" and evs[0]["similarity"] == 0.94, f"Eng o'xshash nomzod tanlandi: {evs[0]['fpid']} {evs[0]['similarity']}")
ok(evs[0]["rect"] == [0.512, 0.268, 0.066, 0.153], f"Yuz ramkasi 0..1: {evs[0]['rect']}")
ok(evs[1]["fpid"] is None and evs[1]["similarity"] is None, "Kutubxonada yo'q yuz — FPID yo'q (notanish)")
ok(evs[0]["bkg_url"].startswith("http://10.10.1.21/picture/"), "Fon rasmi manzili (bkgUrl) olindi")
n = HK.normalize(evs[0], face=True)
ok(n and n["kind"] == "yuz" and n["fpid"] == "FP9A31C0D2E1" and n["rect"] and n["similarity"] == 0.94, f"normalize(face=True) → kind=yuz, FPID, o'xshashlik ({n and n['kind']})")
ok(HK.normalize(evs[0], face=False) is None, "Bayroq o'chiq (face=False) — yuz voqeasi umuman qayta ishlanmaydi")
ok(HK.normalize({"type": "AccessControllerEvent", "subject": "E-101"}, face=True)["kind"] == "xodim_keldi", "Kirish terminali (xodim raqami) — eski xodim_keldi oqimi saqlangan")
xml = ('<EventNotificationAlert version="2.0" xmlns="http://www.hikvision.com/ver20/XMLSchema"><channelID>1</channelID><dateTime>2026-11-09T08:12:33+05:00</dateTime>'
       '<eventType>faceContrast</eventType><eventState>active</eventState><FaceContrastResult><FPID>FP0000000042</FPID><similarity>91</similarity>'
       '<faceRect><x>512</x><y>268</y><width>66</width><height>153</height></faceRect></FaceContrastResult></EventNotificationAlert>')
x = HK.parse_alert(xml)
ok(x["fpid"] == "FP0000000042" and x["similarity"] == 0.91 and x["rect"] == [0.512, 0.268, 0.066, 0.153], f"Eski XML (faceContrast): FPID, 91 → 0.91, 0..1000 → 0..1 ({x['rect']})")
jpeg = b"\xff\xd8" + bytes(random.Random(1).getrandbits(8) for _ in range(3000)) + b"\xff\xd9"
part = lambda ct, body: b"--boundary\r\nContent-Type: " + ct + b"\r\nContent-Length: " + str(len(body)).encode() + b"\r\n\r\n" + body + b"\r\n"
stream = (part(b"application/xml", b'<EventNotificationAlert><eventType>videoloss</eventType><eventState>inactive</eventState></EventNotificationAlert>')
          + part(b'application/json; charset="UTF-8"', json.dumps(SAMPLE).encode()) + part(b"image/jpeg", jpeg)
          + part(b"application/xml", b'<EventNotificationAlert><eventType>linedetection</eventType><eventState>active</eventState></EventNotificationAlert>'))
p, got, rnd, i = HK.AlertStreamParser(), [], random.Random(5), 0
while i < len(stream):
    k = rnd.randint(1, 83); got += p.feed(stream[i:i + k]); i += k
ok([g["type"] for g in got] == ["videoloss", "alarmResult", "alarmResult", "linedetection"] and got[1]["fpid"] == "FP9A31C0D2E1",
   f"Multipart oqim (XML + JSON + JPEG, tasodifiy bo'laklar): {[g['type'] for g in got]}")
ok(p.dropped_bytes >= len(jpeg), "JPEG qism oqim parserida saqlanmadi")

# =====================================================================
print("\n— B. Emulyator: yuz kutubxonasi (FDLib) va alertStream JSON —")
PORT = 18094
env = {**os.environ, "FAKE_HIK_MODEL": "iDS-2CD7146G0-IZS", "FAKE_HIK_EVENTS": "alarmResult=FP0123456789:0.93,videoloss:inactive,alarmResult=:0",
       "FAKE_HIK_EVENT_SEC": "0.05", "FAKE_HIK_STREAM_LIMIT": "3"}
emu = subprocess.Popen([PY, "-m", "uvicorn", "tools.fake_hikvision:app", "--host", "127.0.0.1", "--port", str(PORT), "--log-level", "warning"],
                       cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
try:
    import socket
    for _ in range(75):
        with socket.socket() as s_:
            if s_.connect_ex(("127.0.0.1", PORT)) == 0: break
        time.sleep(.2)
    async def emu_flow():
        cl = HK.HikClient("127.0.0.1", "jarvis", "Test-Pass-123", port=PORT)
        fdid = await cl.fdlib_ensure("ISFT_Kirish")
        fdid2 = await cl.fdlib_ensure("ISFT_Kirish")
        await cl.fdlib_add(fdid, "FP0123456789", b"\xff\xd8" + b"0" * 500 + b"\xff\xd9")
        n1 = httpx.get(f"http://127.0.0.1:{PORT}/__stats", auth=httpx.DigestAuth("jarvis", "Test-Pass-123")).json()["fdlib"]
        await cl.fdlib_delete(fdid, ["FP0123456789"])
        n2 = httpx.get(f"http://127.0.0.1:{PORT}/__stats", auth=httpx.DigestAuth("jarvis", "Test-Pass-123")).json()["fdlib"]
        out = [e async for e in cl.alert_stream()]
        pic = await cl.fetch_picture(f"http://127.0.0.1:{PORT}/picture/face/1?type=bkg")
        evil = await cl.fetch_picture("http://169.254.169.254/latest/meta-data")
        return fdid, fdid2, n1, n2, out, pic, evil
    fdid, fdid2, n1, n2, out, pic, evil = asyncio.run(emu_flow())
    ok(fdid and fdid == fdid2, f"FDLib: kutubxona yaratildi va qayta topildi (FDID={fdid})")
    ok(n1 == 1 and n2 == 0, f"FDLib: FPID qo'shildi ({n1}) va rozilik qaytarilganda o'chirildi ({n2})")
    faces = [e for e in out if e["type"] == "alarmResult"]
    ok(len(faces) == 2 and faces[0]["fpid"] == "FP0123456789" and faces[0]["similarity"] == 0.93 and faces[1]["fpid"] is None,
       f"alertStream JSON qismlari o'qildi: {[(f['fpid'], f['similarity']) for f in faces]}")
    ok(pic and pic[:2] == b"\xff\xd8", "Fon rasmi kameradan olinadi (faqat shu kamera manzili)")
    ok(evil is None or evil[:2] != b"\xff\xd8", "Boshqa xostga yo'naltirish (SSRF) — kamera manzilidan tashqariga so'rov ketmaydi")
finally:
    emu.terminate()

# =====================================================================
print("\n— C. Rasm va kadrlar (jonli server) —")
from PIL import Image                                                # noqa: E402
R = S(2)
s = R.get("/api/face/summary").json()
ok(s["mode"] == "ids" and len(s["cameras"]) >= 3 and all(c["face_capable"] for c in s["cameras"]), f"Rektor: {len(s['cameras'])} ta kirish kamerasi (yuzni solishtirish)")
ok("sintetik" in s["banner"] and "yozma roziligi" in s["banner"], "Banner: sintetik tasvir va yozma rozilik eslatmasi")
# Kadrlar soni kun vaqtiga bog'liq (yarim tundan keyin "bugun" deyarli bo'sh) — kadrlari eng ko'p bo'lgan oxirgi kunni olamiz.
FDAY = q("""SELECT substr(ts,1,10) d FROM face_frames WHERE substr(ts,1,10)<=? GROUP BY d HAVING COUNT(*)>20 ORDER BY d DESC LIMIT 1""", (s["today"],))
FDAY = FDAY[0][0] if FDAY else s["today"]
fr = R.get("/api/face/frames", params={"limit": 96, "date": FDAY}).json()
ok(fr["total"] > 20, f"Kadrlar ({FDAY}): {fr['total']}")
multi = next((f for f in fr["frames"] if len(f["faces"]) >= 2), fr["frames"][0])
img = R.get(multi["img"])
ok(img.status_code == 200 and img.headers["content-type"] == "image/jpeg" and img.content[:2] == b"\xff\xd8", "Rasm: JPEG")
im = Image.open(io.BytesIO(img.content)); ok(im.size == (1280, 720), f"Rasm o'lchami 1280×720 ({im.size})")
th = Image.open(io.BytesIO(R.get(multi["img"], params={"w": 480}).content)); ok(th.size == (480, 270), f"Kichik nusxa 480×270 ({th.size})")
ok("no-store" in img.headers.get("cache-control", ""), "Rasm brauzerda keshlanmaydi (bir kompyuterda boshqa lavozim — boshqa ko'lam)")
bad = []
for f in fr["frames"]:
    for x in f["faces"]:
        row = q("""SELECT e.status, e.similarity, p.name, p.kind, p.sub, p.consent FROM face_events e LEFT JOIN face_persons p ON p.id=e.person_id
                   WHERE e.id=?""", (x["event_id"],))[0]
        if x["status"] != row[0]: bad.append(("status", x["event_id"]))
        if x["status"] == "tanildi" and (x["name"] != row[2] or x["kind"] != row[3] or x["sub"] != row[4] or x["similarity"] != round(100 * row[1]) or not row[5]):
            bad.append(("person", x["event_id"]))
        if x["status"] in ("notanish", "rozilik_yoq") and x["name"]: bad.append(("leak", x["event_id"]))
ok(not bad, f"Yorliqlar bazadagi shaxslar bilan mos (ism, tur, guruh/kafedra/bo'lim, o'xshashlik): {sum(len(f['faces']) for f in fr['frames'])} ta yuz" + (f" — XATO {bad[:5]}" if bad else ""))
d = R.get(f"/api/face/frames/{multi['id']}").json()
ok(d["faces"] == multi["faces"] and d["source"] == "sintetik", "Kadr tafsiloti ro'yxat bilan bir xil")
gr = q("SELECT p.sub FROM face_persons p WHERE p.kind='talaba' AND p.consent=1 LIMIT 1")[0][0]
srch = R.get("/api/face/frames", params={"q": gr, "limit": 96}).json()
ok(all(any(x["visible"] and gr in (x.get("sub") or "") for x in f["faces"]) for f in srch["frames"]), f"Qidiruv guruh bo'yicha ({gr}): {srch['total']} kadr")

# =====================================================================
print("\n— D. Ruxsatlar (lavozim bo'yicha) —")
def kinds_seen(c):
    r = c.get("/api/face/frames", params={"limit": 96})
    if r.status_code != 200: return r.status_code, None
    return 200, {(x["kind"] or x["status"]) for f in r.json()["frames"] for x in f["faces"] if x["visible"]}
st, kk = kinds_seen(S(16)); ok(st == 200 and {"talaba", "oqituvchi", "xodim"} <= kk, f"Xo'jalik bo'limi (xavfsizlik): hammasi ({sorted(kk)})")
K = S(12); st, kk = kinds_seen(K)
ok(st == 200 and kk and kk <= {"oqituvchi", "xodim"}, f"Kadrlar bo'limi: faqat o'qituvchi va xodimlar ({sorted(kk)})")
stu_only = next((f for f in fr["frames"] if all(x["status"] == "tanildi" and x["kind"] == "talaba" for x in f["faces"])), None)
if stu_only:
    ok(K.get(stu_only["img"]).status_code == 403 and K.get(f"/api/face/frames/{stu_only['id']}").status_code == 403, "Kadrlar: faqat talabalar bor kadr — 403")
    sp = q("SELECT person_id FROM face_events WHERE id=?", (stu_only["faces"][0]["event_id"],))[0][0]
    ok(K.get(f"/api/face/persons/{sp}/timeline").status_code == 403, "Kadrlar: talaba tarixi — 403")
# institutda dekan lavozimi yo'q (Yevropa modeli): Face ID fakultet ko'lami — faqat fakultet tyutorida (#24, fak2); sobiq dekan (#13) kira olmaydi
ok(httpx.post(B + "/api/login", json={"user_id": 13, "password": PW}).status_code == 403, "Sobiq dekan (#13): kirish rad etildi")
D13 = S(24); st, kk = kinds_seen(D13)
ok(st == 200 and kk is not None and kk <= {"talaba"}, f"Tyutor: faqat talabalar ({sorted(kk or [])})")
fac = q("SELECT faculty_id FROM users WHERE id=24")[0][0]
dv = D13.get("/api/face/frames", params={"limit": 96}).json()
pids = {x["person_id"] for f in dv["frames"] for x in f["faces"] if x["visible"] and x["person_id"]}
ok(pids and all(q("SELECT faculty_id FROM face_persons WHERE id=?", (p,))[0][0] == fac for p in pids), f"Tyutor: barcha shaxslar o'z fakultetidan (#{fac}, {len(pids)} kishi)")
mixed = next((f for f in dv["frames"] if any(not x["visible"] for x in f["faces"])), None)
if mixed:
    ok(all(x["name"] is None and x["similarity"] is None for x in mixed["faces"] if not x["visible"]), "Tyutor: kadrdagi boshqa shaxslar yashirin (ism, o'xshashlik yo'q; rasmda piksel)")
other = q("SELECT id FROM face_persons WHERE kind='talaba' AND faculty_id!=? AND consent=1 LIMIT 1", (fac,))[0][0]
ok(D13.get(f"/api/face/persons/{other}/timeline").status_code == 403, "Tyutor: boshqa fakultet talabasi tarixi — 403")
T24 = S(24); st, kk = kinds_seen(T24); ok(st == 200 and (kk or set()) <= {"talaba"}, "Tyutor: faqat o'z fakulteti talabalari")
IT = S(21); sm = IT.get("/api/face/summary").json()
ok(sm["mode"] == "health" and "kpi" not in sm and sm["library"]["total"] > 0 and IT.get("/api/face/frames").status_code == 403
   and IT.get(multi["img"]).status_code == 403 and IT.get("/api/face/report").status_code == 403, "AT boshlig'i: faqat kamera/kutubxona holati (sonlar), kadr va hisobot — 403")
KG = S(1); sm = KG.get("/api/face/summary").json(); rp = KG.get("/api/face/report")
ok(sm["mode"] == "aggregate" and KG.get("/api/face/frames").status_code == 403 and KG.get(multi["img"]).status_code == 403
   and rp.status_code == 200 and "late_teachers" not in rp.json()["facts"] and "staff_after" not in rp.json()["facts"], "Kuzatuv kengashi: jamlangan ko'rsatkichlar, ism va rasmsiz")
for uid, who in ((17, "Registrator ofisi"), (3, "O'quv prorektori"), (14, "Kafedra mudiri"), (15, "O'qituvchi"), (11, "Buxgalteriya")):
    c = S(uid)
    ok(all(c.get(u).status_code == 403 for u in ("/api/face/summary", "/api/face/frames", multi["img"], "/api/face/report")), f"{who} ({uid}): 403")

# =====================================================================
print("\n— E. Rozilik: rozilik bermaganlar hech qachon aniqlanmaydi; qaytarib olish —")
ok(q("SELECT COUNT(*) FROM face_events e JOIN face_persons p ON p.id=e.person_id WHERE p.consent=0 OR p.fpid IS NULL")[0][0] == 0,
   "Roziligi yo'q (yoki qaytarib olingan) shaxsga bog'langan birorta voqea yo'q")
ok(q("SELECT COUNT(*) FROM face_events WHERE status IN ('notanish','rozilik_yoq') AND (person_id IS NOT NULL OR fpid IS NOT NULL)")[0][0] == 0,
   "Notanish / rozilik yo'q voqealarida shaxs ham, FPID ham saqlanmaydi")
ok(q("SELECT COUNT(*) FROM face_persons p WHERE p.consent=0 AND p.revoked_at IS NULL AND EXISTS(SELECT 1 FROM face_events e WHERE e.person_id=p.id)")[0][0] == 0
   and q("SELECT COUNT(*) FROM face_persons WHERE consent=0")[0][0] > 0, "Seed: rozilik bermagan shaxslar bor va ular birorta kadrda tanilmagan")
users = {" ".join(n.split(":")[-1].replace("'", "").replace("ʻ", "").replace("’", "").lower().split()[:2]) for (n,) in q("SELECT full_name FROM users WHERE role!='tyutor'")}   # tyutorlar — sintetik xodimlar (haqiqiy rahbarlar emas)
lead = [n for (n,) in q("SELECT name FROM face_persons") if " ".join(n.replace("'", "").lower().split()[:2]) in users]
heads = q("SELECT COUNT(*) FROM face_persons p JOIN teachers t ON t.id=p.ref_id AND p.kind='oqituvchi' WHERE t.position='Kafedra mudiri'")[0][0]
ok(not lead and heads == 0, f"Haqiqiy rahbarlar (foydalanuvchilar, kafedra mudirlari) ro'yxatga olinmagan ({lead[:3]})")
cand = q("""SELECT id, full_name FROM staff WHERE unit NOT IN ('Professor-o''qituvchi','Rektorat') AND position NOT LIKE '%boshlig%'
            AND id NOT IN (SELECT ref_id FROM face_persons WHERE kind='xodim') ORDER BY id DESC""")
cand = [c for c in cand if " ".join(c[1].replace("'", "").lower().split()[:2]) not in users]
sid = cand[0][0]
r = K.post("/api/face/persons", json={"kind": "xodim", "ref_id": sid, "doc": "RZ-TEST/0001"})
ok(r.status_code == 200 and r.json()["person"]["enrolled"], f"Kadrlar bo'limi xodimni yozma rozilik bilan ro'yxatga oldi (staff #{sid})")
pid, fpid = q("SELECT id, fpid FROM face_persons WHERE kind='xodim' AND ref_id=?", (sid,))[0]
ok(fpid and fpid.startswith("FP") and len(fpid) == 12, f"Tasodifiy FPID berildi (ism emas): {fpid}")
ok(D13.post(f"/api/face/persons/{pid}/consent", json={"action": "revoke"}).status_code == 403, "Tyutor xodim roziligini boshqara olmaydi — 403")
stu_p = q("SELECT id FROM face_persons WHERE kind='talaba' AND consent=1 LIMIT 1")[0][0]
ok(K.post(f"/api/face/persons/{stu_p}/consent", json={"action": "revoke"}).status_code == 403, "Kadrlar talaba roziligini boshqara olmaydi — 403")
cam = q("SELECT c.id FROM cameras c JOIN rooms r ON r.id=c.room_id WHERE r.zone='kirish' ORDER BY c.id LIMIT 1")[0][0]
ING = """
import json, datetime as dt
from app import db, facecam as FC
con = db.connect()
cam = db.one(con, "SELECT * FROM cameras WHERE id=?", ({cam},))
t = FC.now() - dt.timedelta(seconds={ago})
r = FC.ingest(con, cam, {{"kind": "yuz", "fpid": {fpid!r}, "similarity": {sim}, "rect": [0.45, 0.28, 0.07, 0.16], "raw_type": "alarmResult (test)"}}, t)
print(json.dumps(r))
"""
r1 = json.loads(run_py(ING.format(cam=cam, fpid=fpid, sim=0.95, ago=200)))
ok(r1 and r1["status"] == "tanildi" and r1["person_id"] == pid, f"Kamera voqeasi (FPID, 95%) → tanildi: shaxs #{r1 and r1['person_id']}")
r1b = json.loads(run_py(ING.format(cam=cam, fpid=fpid, sim=0.95, ago=170)))
ok(r1b is None, "Bir kameradan 60 s ichida takroriy moslik — yozilmaydi (dedup)")
r1c = json.loads(run_py(ING.format(cam=cam, fpid=fpid, sim=0.66, ago=60)))
ok(r1c and r1c["status"] == "past_ishonch", "O'xshashlik 66% (< 75%) → past ishonch (tasdiqlanmagan)")
tl = K.get(f"/api/face/persons/{pid}/timeline").json()
ok(any(e["status"] == "tanildi" for dd in tl["days"] for e in dd["events"]), "Kadrlar bo'limi xodim tarixini ko'radi")
fid1 = r1["frame_id"]
img1 = R.get(f"/api/face/events/{r1['id']}/image")
ok(img1.status_code == 200 and Image.open(io.BytesIO(img1.content)).size == (1280, 720), "Kamera kadri (fon rasmi kelmagan) — metama'lumot bilan izohlangan rasm")
rv = K.post(f"/api/face/persons/{pid}/consent", json={"action": "revoke"})
ok(rv.status_code == 200, "Rozilik qaytarib olindi")
row = q("SELECT consent, fpid, revoked_at FROM face_persons WHERE id=?", (pid,))[0]
ok(row[0] == 0 and row[1] is None and row[2], "FPID o'chirildi, qaytarib olingan sana yozildi")
ok(q("SELECT COUNT(*) FROM face_sync WHERE op='delete' AND fpid=? AND person_id=?", (fpid, pid))[0][0] == 1, "Kamera kutubxonasidan o'chirish navbatga qo'yildi (FDLib delete)")
ok(q("SELECT COUNT(*) FROM face_events WHERE person_id=?", (pid,))[0][0] == 0 and q("SELECT status FROM face_events WHERE id=?", (r1["id"],))[0][0] == "rozilik_yoq",
   "O'tgan voqealar shaxssizlantirildi (ZRU-547)")
r2 = json.loads(run_py(ING.format(cam=cam, fpid=fpid, sim=0.97, ago=0)))
ok(r2 and r2["status"] == "notanish" and r2["person_id"] is None, "Qaytarib olingandan keyin eski FPID bilan voqea → notanish (aniqlanmaydi)")
ok(R.get(f"/api/face/persons/{pid}/timeline").json()["present_days"] == 0, "Shaxs tarixi bo'sh")

# =====================================================================
print("\n— F. Hisobot: faktlar SQL bilan bir xil —")
d = dt.date.fromisoformat(s["today"]) - dt.timedelta(days=1)
while d.weekday() == 6: d -= dt.timedelta(days=1)
rp = R.get("/api/face/report", params={"date": d.isoformat()}).json(); f = rp["facts"]
a, b = d.isoformat(), (d + dt.timedelta(days=1)).isoformat()
sql = lambda w, *x: q(f"SELECT COUNT(*) FROM face_events WHERE ts>=? AND ts<? AND {w}", (a, b, *x))[0][0]
ok(f["entries"] == sql("direction='kirish'") and f["exits"] == sql("direction='chiqish'"), f"{d}: kirish {f['entries']}, chiqish {f['exits']}")
for k in ("talaba", "oqituvchi", "xodim"):
    n_ = q("SELECT COUNT(DISTINCT e.person_id) FROM face_events e JOIN face_persons p ON p.id=e.person_id WHERE e.ts>=? AND e.ts<? AND e.status='tanildi' AND p.kind=?", (a, b, k))[0][0]
    ok(f["unique"][k] == n_, f"Noyob {k}: {f['unique'][k]} = SQL {n_}")
ok(f["unknown"] == sql("status='notanish'") and f["no_consent"] == sql("status='rozilik_yoq'") and f["low_conf"] == sql("status='past_ishonch'"),
   f"Notanish {f['unknown']}, rozilik yo'q {f['no_consent']}, past ishonch {f['low_conf']}")
ok(f["night_entries"] == sql("night=1 AND direction='kirish'"), f"Tungi kirishlar: {f['night_entries']}")
hrs = q("SELECT substr(ts,12,2) h, COUNT(*) n FROM face_events WHERE ts>=? AND ts<? AND direction='kirish' GROUP BY h ORDER BY n DESC, h LIMIT 1", (a, b))
ok(f["peak_hour"]["entries"] == hrs[0][1] and f["peak_hour"]["hour"].startswith(hrs[0][0]), f"Eng gavjum soat: {f['peak_hour']}")
for x in f.get("late_teachers", []):
    p_ = q("SELECT ref_id FROM face_persons WHERE id=?", (x["person_id"],))[0][0]
    sl = q("SELECT MIN(slot) FROM schedule WHERE teacher_id=? AND weekday=?", (p_, d.weekday()))[0][0]
    first = q("SELECT MIN(ts) FROM face_events WHERE person_id=? AND ts>=? AND ts<? AND status='tanildi' AND direction='kirish'", (x["person_id"], a, b))[0][0]
    ok(sl == x["slot"] and first[11:16] == x["arrival"] and first[11:16] > x["first_para"], f"Kechikkan: {x['name']} — {x['slot']}-para {x['first_para']}, kirdi {x['arrival']} (+{x['minutes']})")
nums = [w for w in __import__("re").findall(r"\d+(?:\.\d+)?", rp["narrative"])]
ok(rp["verify"]["bad"] == [] and rp["narrative_mode"] in ("ai", "shablon"), f"Xulosa ({rp['narrative_mode']}): {rp['verify']['n']} ta raqam tekshirildi, mos kelmagani yo'q")
dx = R.post("/api/face/report/docx", json={"date": d.isoformat()})
ok(dx.status_code == 200 and dx.json()["file"].startswith("KRN-"), f"Word hisobot: {dx.json().get('file')}")
fb = R.get(f"/api/docs/file/{dx.json()['file']}")
xmlb = zipfile.ZipFile(io.BytesIO(fb.content)).read("word/document.xml").decode()
ok("KIRISH NAZORATI (FACE ID)" in xmlb and str(f["entries"]) in xmlb and (not f.get("late_teachers") or f["late_teachers"][0]["name"].split()[0] in xmlb), "DOCX: sarlavha, raqamlar va ismlar")

# =====================================================================
print("\n— G. Kechikish mantig'i (qurilgan holat, baza nusxasida) —")
tmp = Path(tempfile.mkdtemp(prefix="facecam-")) / "copy.db"
src = sqlite3.connect(DB); dst = sqlite3.connect(tmp); src.backup(dst); src.close(); dst.close()
con = sqlite3.connect(tmp, check_same_thread=False); con.row_factory = sqlite3.Row
from app import facecam as FC, seed_facecam as SF, rbac  # noqa: E402
FC.SNAP_DIR = tmp.parent / "snaps"
D0 = dt.date.fromisoformat(s["today"]) + dt.timedelta(days=21)
while D0.weekday() != 1: D0 += dt.timedelta(days=1)            # kelajakdagi seshanba — u kunga voqea yo'q
tch = q("""SELECT p.id, p.ref_id, MIN(s.slot) FROM face_persons p JOIN schedule s ON s.teacher_id=p.ref_id AND s.weekday=1
           WHERE p.kind='oqituvchi' AND p.consent=1 GROUP BY p.id ORDER BY p.id LIMIT 3""")
starts = {1: "08:30", 2: "10:00", 3: "11:30", 4: "13:30", 5: "15:00", 6: "16:30"}
def put(pid_, hhmmss, direction="kirish", status="tanildi", cam_=cam):
    ts = f"{D0.isoformat()}T{hhmmss}"
    fid_ = con.execute("INSERT INTO face_frames(ts,camera_id,direction,seed,n,source) VALUES(?,?,?,1,1,'sintetik')", (ts, cam_, direction)).lastrowid
    con.execute("INSERT INTO face_events(frame_id,ts,camera_id,direction,person_id,fpid,similarity,rect,status,look,night) VALUES(?,?,?,?,?,?,?,?,?,1,0)",
                (fid_, ts, cam_, direction, pid_, "FPX", .93 if status == "tanildi" else .6, "[0.4,0.3,0.07,0.16]", status))
def hm_add(hm, mins, sec=0):
    t = dt.datetime.combine(D0, dt.time(*map(int, hm.split(":")))) + dt.timedelta(minutes=mins, seconds=sec)
    return t.strftime("%H:%M:%S")
(p1, _, s1), (p2, _, s2), (p3, _, s3) = tch
put(p1, hm_add(starts[s1], 7, 40)); put(p1, hm_add(starts[s1], 40))               # birinchi kirish +7:40 → 7 daqiqa (keyingi kirish hisobga olinmaydi)
put(p2, hm_add(starts[s2], -12))                                                   # o'z vaqtida
put(p3, hm_add(starts[s3], 25, 0), status="past_ishonch")                         # past ishonch — kechikkan deb hisoblanmaydi
put(p3, hm_add(starts[s3], -2))
con.commit()
ctx = rbac.ctx_for(con, 2)
ff = FC.facts(con, FC.Acc(ctx), D0)
lt = {x["person_id"]: x for x in ff["late_teachers"]}
ok(set(lt) == {p1}, f"Faqat birinchi o'qituvchi kechikkan: {sorted(lt)} (kutilgan {[p1]})")
ok(lt[p1]["minutes"] == 7 and lt[p1]["first_para"] == starts[s1] and lt[p1]["arrival"] == hm_add(starts[s1], 7, 40)[:5],
   f"Kechikish: {lt[p1]['first_para']} → {lt[p1]['arrival']} = {lt[p1]['minutes']} daqiqa")
ok(FC._late_min(f"{D0}T08:30:00", "08:30") == 0 and FC._late_min(f"{D0}T08:30:20", "08:30") == 1 and FC._late_min(f"{D0}T08:52:59", "08:30") == 22,
   "Chegaralar: 08:30:00 — o'z vaqtida, 08:30:20 — 1 daq., 08:52:59 — 22 daq.")
ff12 = FC.facts(con, FC.Acc(rbac.ctx_for(con, 12)), D0)
ff13 = FC.facts(con, FC.Acc(rbac.ctx_for(con, 24)), D0)
ok(ff12["late_teachers_n"] == 1 and ff13["late_teachers_n"] == 0 and ff13["unique"]["oqituvchi"] == 0, "Ko'lam: kadrlar kechikishni ko'radi, tyutor — o'qituvchilarni ko'rmaydi")
ok(FC.ACCESS.get("dekan") is None and FC.Acc(rbac.ctx_for(con, 13)).mode is None, "Face ID: dekan ko'lami yo'q (lavozim bekor qilingan)")
old = FC.SNAP_DIR / "999999.jpg"; old.parent.mkdir(parents=True, exist_ok=True); old.write_bytes(b"\xff\xd8x\xff\xd9")
os.utime(old, (time.time() - 9 * 86400,) * 2); new = FC.SNAP_DIR / "999998.jpg"; new.write_bytes(b"\xff\xd8y\xff\xd9")
FC.purge(con)
ok(not old.exists() and new.exists(), f"Saqlash muddati: {FC.KEEP_DAYS} kundan eski kadr rasmi o'chirildi, yangisi qoldi")
con.close()

# =====================================================================
print("\n— H. Audit jurnali —")
since = (CLK.now() - dt.timedelta(minutes=30)).isoformat(timespec="seconds")
aud = lambda uid, allowed: q("SELECT COUNT(*) FROM audit_log WHERE resource='face' AND user_id=? AND allowed=? AND ts>=?", (uid, allowed, since))[0][0]
ok(aud(2, 1) >= 3, f"Rektor ko'rishlari jurnalda ({aud(2, 1)})")
ok(aud(12, 1) >= 2 and aud(12, 0) >= 1, f"Kadrlar: ruxsat ({aud(12, 1)}) va rad etish ({aud(12, 0)}) jurnalda")
ok(aud(17, 0) >= 1 and aud(21, 0) >= 1, "Ruxsatsiz urinishlar (registrator, AT) jurnalda")
ok(q("SELECT COUNT(*) FROM audit_log WHERE resource='face' AND action LIKE '%shaxs tarixi%' AND ts>=?", (since,))[0][0] >= 1, "Shaxs tarixini ko'rish jurnalda")
ok(q("SELECT COUNT(*) FROM audit_log WHERE resource='face' AND action LIKE '%rozilik%qaytarib%' AND user_id=12 AND ts>=?", (since,))[0][0] >= 1, "Rozilikni qaytarib olish jurnalda")

# sinov voqealari (kamera emulyatsiyasi) jonli demo galereyasida qolmasin; rozilik reyestridagi yozuv (qaytarib olingan) — audit izi sifatida qoladi
run_py("""
from app import db
con = db.connect()
fids = [r[0] for r in con.execute("SELECT DISTINCT frame_id FROM face_events WHERE raw_type='alarmResult (test)'")]
con.execute("DELETE FROM face_events WHERE raw_type='alarmResult (test)'")
for f in fids: con.execute("DELETE FROM face_frames WHERE id=? AND NOT EXISTS(SELECT 1 FROM face_events WHERE frame_id=?)", (f, f))
con.commit(); print(len(fids))
""")
ok(q("SELECT COUNT(*) FROM face_events WHERE raw_type='alarmResult (test)'")[0][0] == 0, "Sinov voqealari tozalandi")

print(f"\nHammasi o'tdi: {N[0]} ta tekshiruv ✓")
