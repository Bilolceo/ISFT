"""Hikvision ulagichi testlari — jonli bazaga TEGMAYDI (vaqtinchalik nusxa + alohida maxfiy papka + emulyator).

    .venv/bin/python tests/test_hikvision.py
"""
import asyncio, os, random, sqlite3, stat, subprocess, sys, tempfile, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TMP = Path(tempfile.mkdtemp(prefix="jarvis-hik-"))
os.environ["JARVIS_SECRETS_DIR"] = str(TMP / "secrets")        # importdan OLDIN
sys.path.insert(0, str(ROOT))
from app import db, hikvision as HK, secret_store as SS          # noqa: E402

fails = 0
def ok(cond, msg):
    global fails
    print(("✓ " if cond else "✗ XATO: ") + msg); fails += (not cond)

PORT_OK, PORT_BAD, PORT_DEAD = 18090, 18091, 18099
PY = str(ROOT / ".venv" / "bin" / "python")
procs = []
def emulator(port, **env):
    e = {**os.environ, **{f"FAKE_HIK_{k.upper()}": str(v) for k, v in env.items()}}
    p = subprocess.Popen([PY, "-m", "uvicorn", "tools.fake_hikvision:app", "--host", "127.0.0.1", "--port", str(port), "--log-level", "warning"],
                         cwd=ROOT, env=e, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    procs.append(p)
    return p

def wait_port(port, t=15):
    import socket
    end = time.time() + t
    while time.time() < end:
        with socket.socket() as s:
            if s.connect_ex(("127.0.0.1", port)) == 0: return True
        time.sleep(0.2)
    return False

async def main():
    # ---------------- A. birlik testlari ----------------
    hb = HK.AlertStreamParser()
    xml = lambda t, st="active": (f'<EventNotificationAlert version="2.0" xmlns="http://www.hikvision.com/ver20/XMLSchema"><channelID>1</channelID>'
                                  f'<dateTime>2026-11-06T22:10:00+05:00</dateTime><eventType>{t}</eventType><eventState>{st}</eventState></EventNotificationAlert>').encode()
    jpeg = b"\xff\xd8" + bytes(random.Random(1).getrandbits(8) for _ in range(4096)) + b"\xff\xd9"
    stream = (b"--boundary\r\nContent-Type: application/xml\r\n\r\n" + xml("videoloss", "inactive") + b"\r\n--boundary\r\nContent-Type: application/xml\r\n\r\n"
              + xml("linedetection") + b"\r\n--boundary\r\nContent-Type: image/jpeg\r\n\r\n" + jpeg + b"\r\n--boundary\r\n\r\n" + xml("fielddetection"))
    got, rnd = [], random.Random(7)
    i = 0
    while i < len(stream):                       # tasodifiy bo'laklar: teglar chunk chegarasida bo'linadi
        n = rnd.randint(1, 97); got += hb.feed(stream[i:i + n]); i += n
    ok([g["type"] for g in got] == ["videoloss", "linedetection", "fielddetection"], f"Oqim parseri: 3 ta XML voqea, bo'laklarga bo'lingan oqimdan ({[g['type'] for g in got]})")
    ok(hb.dropped_bytes >= len(jpeg), f"JPEG qism saqlanmasdan tashlandi ({hb.dropped_bytes} bayt)")
    ok(HK.normalize({"type": "videoloss", "state": "inactive"}) is None, "Yurak urishi (videoloss inactive) — saqlanmaydi")
    ok(HK.normalize({"type": "VMD", "state": "active"}) is None, "Harakat (VMD) shovqini — saqlanmaydi")
    ok(HK.normalize({"type": "linedetection", "state": "active"})["kind"] == "chiziq_kesish", "linedetection → chiziq_kesish")
    ok(HK.normalize({"type": "personDensityDetection"})["kind"] == "olomon", "zichlik voqeasi → olomon")
    ok(HK.normalize({"type": "newThing"})["kind"] == "boshqa:newthing", "Noma'lum tur yo'qolmaydi — 'boshqa:' bilan saqlanadi")
    ok(HK.parse_alert("<buzilgan") is None, "Buzilgan XML — xatosiz o'tkazib yuboriladi")
    w = HK.warnings({"clock_skew_s": 600, "counting": False, "events": True, "device": {"firmware_date": "build 210628"}})
    ok(len(w) == 3, f"Ogohlantirishlar: soat farqi, sanash yo'q, eski proshivka ({len(w)})")
    ok(HK.warnings({"clock_skew_s": 5, "counting": True, "events": True, "device": {"firmware_date": "build 230815"}}) == [], "Sog'lom qurilma — ogohlantirish yo'q")
    SS.put("t:1", "Maxfiy-123!")
    ok(SS.get("t:1") == "Maxfiy-123!", f"Maxfiy ombor: yozish/o'qish ({SS.mode()} rejimi)")
    ok(stat.S_IMODE(os.stat(SS.STORE).st_mode) == 0o600, "Ombor fayli 0600 huquqda")
    ok(b"Maxfiy-123!" not in SS.STORE.read_bytes(), "Parol faylda ochiq matn sifatida yo'q")

    # ---------------- B. emulyator bilan ----------------
    emulator(PORT_OK, stream_limit=7, event_sec=0.2)
    emulator(PORT_BAD, skew=600, counting=0, fw_date="build 210628")
    ok(wait_port(PORT_OK) and wait_port(PORT_BAD), "Emulyatorlar ishga tushdi")
    good = HK.HikClient("127.0.0.1", "jarvis", "Test-Pass-123", port=PORT_OK)
    info = await good.device_info(); ok(info["model"].startswith("DS-2CD"), f"Digest avtorizatsiya + deviceInfo: {info['model']}")
    try:
        await HK.HikClient("127.0.0.1", "jarvis", "notogri", port=PORT_OK).device_info(); ok(False, "Noto'g'ri parol rad etilishi kerak")
    except HK.IsapiError as e:
        ok("Login yoki parol" in str(e), "Noto'g'ri parol → tushunarli xato")
    try:
        await HK.HikClient("127.0.0.1", "x", "y", port=PORT_DEAD).device_info(); ok(False, "Yopiq port")
    except HK.IsapiError as e:
        ok("Ulanib bo'lmadi" in str(e), "Ulanmaydigan qurilma → 'Ulanib bo'lmadi'")
    caps = await good.probe(1)
    ok(caps["counting"] is True and caps["events"] is True and abs(caps["clock_skew_s"]) < 5 and not caps["warnings"], f"Imkoniyatlar: sanash ✓ voqealar ✓ soat farqi {caps['clock_skew_s']} s")
    bad = await HK.HikClient("127.0.0.1", "jarvis", "Test-Pass-123", port=PORT_BAD).probe(1)
    ok(bad["counting"] is False and len(bad["warnings"]) == 3, f"Muammoli qurilma aniqlandi: {bad['warnings']}")
    n = await good.count(1); ok(isinstance(n, int) and n >= 0, f"Odam sanash (kirdi − chiqdi): {n}")
    try:
        await HK.HikClient("127.0.0.1", "jarvis", "Test-Pass-123", port=PORT_BAD).count(1); ok(False, "sanashsiz model")
    except HK.IsapiError as e:
        ok("odam sanash" in str(e).lower(), "Sanashni qo'llamaydigan model → aniq xabar")
    evs = [e async for e in good.alert_stream()]
    types = [e["type"] for e in evs]
    ok({"linedetection", "fielddetection", "shelteralarm"} <= set(types), f"Voqealar oqimi o'qildi: {types}")

    # ---------------- C. occupancy integratsiyasi (vaqtinchalik baza) ----------------
    tmpdb = TMP / "jarvis.db"
    src = sqlite3.connect(ROOT / "data" / "jarvis.db"); dst = sqlite3.connect(tmpdb); src.backup(dst); src.close(); dst.close()
    db.DB_PATH = tmpdb
    from app import occupancy as OC
    con = db.connect()
    OC.init(con)                                         # yangi ustunlar (eski baza nusxasiga ham)
    room = db.one(con, "SELECT id FROM rooms ORDER BY id LIMIT 1")["id"]
    con.execute("DELETE FROM cameras WHERE room_id=?", (room,))
    cid = con.execute("INSERT INTO cameras(room_id,vendor,mode,host,channel,username,password,status,port) VALUES(?,?,?,?,?,?,?,?,?)",
                      (room, "Hikvision", "isapi", "127.0.0.1", 1, "jarvis", "Test-Pass-123", "kutilmoqda", PORT_DEAD)).lastrowid
    con.commit()
    OC.bind(con, None)                                   # init: parol bazadan omborga ko'chiriladi
    ok(db.one(con, "SELECT password FROM cameras WHERE id=?", (cid,))["password"] == "" and SS.get(f"camera:{cid}") == "Test-Pass-123",
       "Migratsiya: parol bazadan o'chirildi, maxfiy omborda")
    con.execute("UPDATE cameras SET mode='sim' WHERE id!=?", (cid,)); con.commit()
    for _ in range(OC.OFFLINE_FAILS + 1):
        await OC.poll_once()
    cam = db.one(con, "SELECT * FROM cameras WHERE id=?", (cid,))
    tks = db.rows(con, "SELECT * FROM tickets WHERE room_id=? AND item='Kamera' AND status!='hal qilindi'", (room,))
    ok(cam["status"] == "xato" and cam["fail_count"] == OC.OFFLINE_FAILS + 1, f"Kamera javob bermadi: {cam['fail_count']} marta")
    ok(len(tks) == 1 and cam["ticket_id"] == tks[0]["id"], "Xizmat markazida BITTA nosozlik arizasi ochildi (takror yo'q)")
    con.execute("UPDATE cameras SET port=? WHERE id=?", (PORT_OK, cid)); con.commit()
    await OC.poll_once()
    cam = db.one(con, "SELECT * FROM cameras WHERE id=?", (cid,))
    t = db.one(con, "SELECT status, note FROM tickets WHERE id=?", (tks[0]["id"],))
    ok(cam["status"] == "onlayn" and cam["ticket_id"] is None and t["status"] == "hal qilindi", f"Kamera tiklandi → ariza avtomatik yopildi ({t['note']})")
    ok(db.one(con, "SELECT COUNT(*) n FROM occupancy WHERE room_id=? AND ts>=date('now','localtime')", (room,))["n"] >= 1, "Bandlik o'lchovi yozildi")

    import datetime as dt
    con.execute("UPDATE rooms SET guard=1 WHERE id=?", (room,)); con.commit()
    camd = db.one(con, "SELECT * FROM cameras WHERE id=?", (cid,))
    night = dt.datetime.now().replace(hour=23, minute=40)
    r1 = OC.handle_event(con, camd, {"type": "fielddetection", "state": "active"}, night)
    ok(r1 and r1["alert"] == 1, "Tunda qo'riqlanadigan xonaga kirish → ogohlantirish")
    ok(OC.handle_event(con, camd, {"type": "fielddetection", "state": "active"}, night + dt.timedelta(seconds=10)) is None, "30 s ichida takror voqea — bitta yozuv")
    day = dt.datetime.now().replace(hour=11, minute=0)
    if day.weekday() == 6: day -= dt.timedelta(days=1)
    r2 = OC.handle_event(con, camd, {"type": "linedetection", "state": "active"}, day)
    ok(r2 and r2["alert"] == 0, "Ish vaqtida kirish — ogohlantirishsiz qayd")
    ok(OC.handle_event(con, camd, {"type": "videoloss", "state": "inactive"}) is None, "Yurak urishi bazaga yozilmaydi")
    r3 = OC.handle_event(con, camd, {"type": "shelteralarm", "state": "active"})
    ok(r3 and r3["alert"] == 1 and db.one(con, "SELECT ticket_id FROM cameras WHERE id=?", (cid,))["ticket_id"], "Kamera yopildi → nosozlik arizasi")
    al = OC.alerts(con, __import__("app.rbac", fromlist=["ctx_for"]).ctx_for(con, 2))
    ok(any(a["area"] == "Xavfsizlik" for a in al), "Rektor ogohlantirishlarida tungi kirish ko'rinadi")

    con.execute("UPDATE cameras SET events=1, ticket_id=NULL WHERE id=?", (cid,)); con.commit()
    before = db.one(con, "SELECT COUNT(*) n FROM cam_events WHERE camera_id=?", (cid,))["n"]
    try:
        await asyncio.wait_for(OC._listen(cid), timeout=4)
    except asyncio.TimeoutError:
        pass
    after = db.one(con, "SELECT COUNT(*) n FROM cam_events WHERE camera_id=?", (cid,))["n"]
    ok(after > before, f"Fon tinglovchisi voqealarni yozdi (+{after - before}); uzilgandan keyin qayta ulanadi")
    ok(not any(Path(TMP).rglob("*.jpg")) and db.one(con, "SELECT COUNT(*) n FROM cam_events WHERE raw_type LIKE '%jpeg%'")["n"] == 0, "Rasm/kadr saqlanmadi")

try:
    asyncio.run(main())
finally:
    for p in procs: p.terminate()
print("\nNATIJA:", "HAMMASI O'TDI" if not fails else f"{fails} TA XATO")
sys.exit(1 if fails else 0)
