"""Hikvision ulagichi testlari — jonli bazaga TEGMAYDI (vaqtinchalik nusxa + alohida maxfiy papka + emulyator).

    .venv/bin/python tests/test_hikvision.py
"""
import asyncio, os, random, sqlite3, stat, subprocess, sys, tempfile, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT)); from app import clock as CLK   # noqa: E402 — institut vaqti (ISFT_CORE_TZ / ISFT_CORE_FAKE_TODAY), server bilan bir xil
TMP = Path(tempfile.mkdtemp(prefix="jarvis-hik-"))
os.environ["ISFT_CORE_SECRETS_DIR"] = str(TMP / "secrets")        # importdan OLDIN
# Kameralar standart holda o'chiq (app/modules.py): bu to'plam bo'limni va simulyatorni o'z muhitida yoqadi
os.environ["ISFT_CORE_MODULES"] = "+cams,+spaces"; os.environ["ISFT_CORE_CAM_SIM"] = "1"
sys.path.insert(0, str(ROOT))
from app import db, hikvision as HK, secret_store as SS          # noqa: E402

fails = 0
def ok(cond, msg):
    global fails
    print(("✓ " if cond else "✗ XATO: ") + msg); fails += (not cond)

PORT_OK, PORT_BAD, PORT_DEAD, PORT_Q, PORT_EV = 18090, 18091, 18099, 18092, 18093
PY = sys.executable   # joriy interpretator (lokal .venv yoki CI)
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
    src = sqlite3.connect(Path(os.environ.get("ISFT_CORE_DB") or ROOT / "data" / "jarvis.db")); dst = sqlite3.connect(tmpdb); src.backup(dst); src.close(); dst.close()
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
    # kechagi sana: bugungi kelajakdagi vaqt (masalan, yarim tundan keyin 23:40) takror-filtrni buzib, fon testini yiqitadi
    night = (CLK.now() - dt.timedelta(days=1)).replace(hour=23, minute=40)
    r1 = OC.handle_event(con, camd, {"type": "fielddetection", "state": "active"}, night)
    ok(r1 and r1["alert"] == 1, "Tunda qo'riqlanadigan xonaga kirish → ogohlantirish")
    ok(OC.handle_event(con, camd, {"type": "fielddetection", "state": "active"}, night + dt.timedelta(seconds=10)) is None, "Dedup oynasida (5 daqiqa) takror voqea — bitta yozuv")
    day = (CLK.now() - dt.timedelta(days=1)).replace(hour=11, minute=0)
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

    # ---------------- D. Kengaytma: yangi eventType'lar, ustuvorlik, dedup, bayroqlar, RBAC, navbat ----------------
    from app import camsec as CS, rbac
    from app.rbac import AccessDenied
    NEW = {"linedetection": "chiziq_kesish", "fielddetection": "hududga_kirish", "regionEntrance": "hududga_kirish", "regionExiting": "hududdan_chiqish",
           "loitering": "uzoq_turish", "peopleGathering": "toplanish", "running": "yugurish", "unattendedBaggage": "qarovsiz_buyum",
           "attendedBaggage": "buyum_olindi", "objectRemoval": "buyum_olindi", "shelteralarm": "kamera_yopildi", "videoloss": "video_yoqoldi",
           "defocus": "kamera_siljidi", "scenechangedetection": "kamera_siljidi", "fireDetection": "yongin", "smokeDetection": "tutun",
           "TMA": "harorat", "temperature": "harorat", "personQueueDetection": "navbat", "regionPeopleCounting": "odam_soni"}
    bad = [k for k, v in NEW.items() if (HK.normalize({"type": k, "state": "active"}) or {}).get("kind") != v]
    ok(not bad, f"{len(NEW)} ta eventType normallashtirildi" + (f" — XATO: {bad}" if bad else ""))
    ok(all(k in CS.POLICY for k in set(NEW.values())), "Har bir tur uchun ustuvorlik siyosati bor (P1–P4, kimga)")
    ok(HK.normalize({"type": "VMD"}, keep_vmd=True)["kind"] == "harakat", "VMD faqat qo'riqlanadigan hududda saqlanadi")
    ok(HK.normalize({"type": "faceSnap"}) is None and HK.normalize({"type": "ANPR"}) is None and not CS.FEATURE_ANPR,
       "Yuzni tanish va avtoraqam — bayroqsiz (face/anpr=False) voqea umuman qayta ishlanmaydi; avtoraqam standart holatda O'CHIQ")
    ok((HK.normalize({"type": "alarmResult", "fpid": "FP1"}, face=True) or {}).get("kind") == "yuz",
       "Yuz (FEATURE_FACE=1, demo): faqat kirish kameralari va rozilik reyestri orqali — app/facecam.py, tests/test_facecam.py")
    q = HK.parse_alert('<EventNotificationAlert><eventType>personQueueDetection</eventType><queueLength>27</queueLength><waitingTime>840</waitingTime></EventNotificationAlert>')
    ok(q["count"] == 27 and q["wait_s"] == 840, "Navbat voqeasi: uzunlik va kutish vaqti o'qildi")
    ok(len(HK.warnings({"clock_skew_s": 75, "counting": True, "events": True, "device": {}})) == 1, "Soat farqi > 60 s — ogohlantirish")

    con.execute("UPDATE cameras SET ticket_id=NULL WHERE id=?", (cid,)); con.commit()
    camd = db.one(con, "SELECT * FROM cameras WHERE id=?", (cid,))
    base = (CLK.now() - dt.timedelta(days=2)).replace(hour=14, minute=0, second=0, microsecond=0)
    if base.weekday() == 6: base -= dt.timedelta(days=1)
    e1 = OC.handle_event(con, camd, {"type": "unattendedBaggage", "state": "active"}, base)
    ok(e1 and e1["priority"] == 2 and "rektor" in e1["route"], f"Qarovsiz buyum → P{e1 and e1['priority']}, kimga: {e1 and e1['route']}")
    ok(OC.handle_event(con, camd, {"type": "unattendedBaggage", "state": "active"}, base + dt.timedelta(minutes=4)) is None, "Dedup: 4 daqiqadan keyin takror — yangi yozuv yo'q")
    ok(db.one(con, "SELECT dup FROM cam_events WHERE id=?", (e1["id"],))["dup"] == 1, "Dedup: takror mavjud yozuvga qo'shildi (dup=1)")
    e3 = OC.handle_event(con, camd, {"type": "unattendedBaggage", "state": "active"}, base + dt.timedelta(minutes=10))
    ok(e3 is not None, "Dedup oynasi (5 daqiqa) tugagach — yangi yozuv")
    f1 = OC.handle_event(con, camd, {"type": "fireDetection", "state": "active"}, base + dt.timedelta(minutes=20))
    ok(f1 and f1["priority"] == 1 and f1["ticket_id"], "Yong'in → P1, darhol xavfsizlik tiketi")
    n0 = db.one(con, "SELECT COUNT(*) n FROM cam_events")["n"]
    OC.handle_event(con, camd, {"type": "fireDetection", "state": "inactive"}, base + dt.timedelta(minutes=22))
    ok(db.one(con, "SELECT COUNT(*) n FROM cam_events")["n"] == n0 and db.one(con, "SELECT status FROM cam_events WHERE id=?", (f1["id"],))["status"] == "yopildi",
       "Voqea tugadi (inactive) — ochiq yozuv yopildi, yangi qator yo'q")

    # RBAC: kamerani sozlash va voqeani belgilash — faqat rektor va xo'jalik
    def uid(role): return db.one(con, "SELECT id FROM users WHERE role=? ORDER BY id LIMIT 1", (role,))["id"]
    pro, dek, xoj = rbac.ctx_for(con, uid("prorektor_oquv")), rbac.ctx_for(con, uid("tyutor")), rbac.ctx_for(con, uid("xojalik"))
    OC._con = con
    for c_, nm in ((pro, "O'quv prorektori"), (dek, "Tyutor")):
        try: OC._manage(c_, "kamera sozlamasi"); ok(False, f"{nm} kamerani sozlay olmasligi kerak")
        except AccessDenied: ok(True, f"{nm} kamerani sozlay olmaydi (403)")
        try: CS.event_action(con, c_, e1["id"], "notogri"); ok(False, f"{nm} voqeani belgilay olmasligi kerak")
        except AccessDenied: ok(True, f"{nm} voqeani belgilay olmaydi (403)")
    r = CS.event_action(con, xoj, e1["id"], "notogri", "test")
    ok(r["status"] == "notogri", "Xo'jalik bo'limi voqeani 'noto'g'ri signal' deb belgiladi")
    ok(db.one(con, "SELECT COUNT(*) n FROM audit_log WHERE action LIKE 'kamera voqeasi:%' AND allowed=0")["n"] >= 2, "Rad etilgan urinishlar audit jurnalida")
    st = CS.events(con, xoj, days=7, quiet=True)["stats"]
    ok(st["false"] >= 1, f"Noto'g'ri signal statistikaga kirdi ({st['false']} ta, {st['false_rate']}%)")

    # Oflayn kamera (simulyator nosozligi) → 10 daqiqadan keyin BITTA tiket, ko'p so'rovda ham dublikat yo'q
    sim = db.one(con, "SELECT c.id, c.room_id FROM cameras c JOIN rooms r ON r.id=c.room_id WHERE c.mode='sim' AND r.zone IS NULL AND c.id!=? "
                      "AND c.sim_fault IS NULL LIMIT 1", (cid,))
    con.execute("UPDATE cameras SET sim_fault='oflayn', ticket_id=NULL, fail_count=0, last_seen=? WHERE id=?",
                ((CLK.now() - dt.timedelta(minutes=12)).isoformat(timespec="seconds"), sim["id"])); con.commit()
    for _ in range(OC.OFFLINE_FAILS + 3):
        await OC.poll_once()
    tk = db.rows(con, "SELECT id FROM tickets WHERE room_id=? AND item='Kamera' AND status!='hal qilindi'", (sim["room_id"],))
    ok(len(tk) == 1, f"Oflayn kamera → bitta tiket (dublikat yo'q): {len(tk)} ta")
    con.execute("UPDATE cameras SET sim_fault=NULL WHERE id=?", (sim["id"],)); con.commit()
    await OC.poll_once()
    ok(db.one(con, "SELECT status FROM tickets WHERE id=?", (tk[0]["id"],))["status"] == "hal qilindi", "Kamera qayta onlayn → tiket avtomatik yopildi")

    # Navbat: emulyatordan holat + chegaradan oshganda voqea va cam_queue namunasi
    emulator(PORT_Q, model="iDS-2CD7A46G0-IZHS", queue_len=27)
    ok(wait_port(PORT_Q), "DeepinView emulyatori ishga tushdi")
    qs = await HK.HikClient("127.0.0.1", "jarvis", "Test-Pass-123", port=PORT_Q).queue_status(1)
    ok(qs["length"] == 27, f"Navbat holati (ISAPI queueManagement): {qs}")
    qroom = db.one(con, "SELECT id FROM rooms WHERE zone='qabul'")
    if qroom:
        qc = db.one(con, "SELECT c.*, r.zone, r.capacity FROM cameras c JOIN rooms r ON r.id=c.room_id WHERE c.room_id=?", (qroom["id"],))
        r = OC.handle_event(con, qc, {"type": "personQueueDetection", "state": "active", "count": 27, "wait_s": 840}, base + dt.timedelta(hours=1))
        ok(r and r["priority"] == 3 and r["route"] == ["qabul"], f"Navbat 27 > 20 → P3, Qabul komissiyasiga ({r and r['route']})")
        ok(db.one(con, "SELECT COUNT(*) n FROM cam_queue WHERE room_id=? AND length=27", (qroom["id"],))["n"] >= 1, "Navbat namunasi saqlandi")
    else:
        ok(False, "Qabul zonasi topilmadi (seed eskirgan — python -m app.seed)")

    # Emulyatordagi yangi voqealar oqimi: rasm qismlari tashlanadi, voqealar saqlanadi
    emulator(PORT_EV, events="unattendedBaggage+jpeg,running,fireDetection+jpeg,videoloss:inactive,TMA=72.5", stream_limit=5, event_sec=0.1, thermal=1)
    ok(wait_port(PORT_EV), "Termal emulyator ishga tushdi")
    stats = {}
    evs = [e async for e in HK.HikClient("127.0.0.1", "jarvis", "Test-Pass-123", port=PORT_EV).alert_stream(stats)]
    ok([e["type"] for e in evs] == ["unattendedBaggage", "running", "fireDetection", "videoloss", "TMA"] and stats.get("dropped_bytes", 0) > 2000,
       f"Yangi voqealar o'qildi, JPEG qismlar xotirada tashlandi ({stats.get('dropped_bytes')} bayt)")
    tma = next(e for e in evs if e["type"] == "TMA")
    ok(tma["value"] == 72.5, "Termal: harorat qiymati o'qildi (72.5 °C)")
    ok(not any(Path(TMP).rglob("*.jp*g")), "Diskda birorta ham rasm fayli yo'q")

try:
    asyncio.run(main())
finally:
    for p in procs: p.terminate()
print("\nNATIJA:", "HAMMASI O'TDI" if not fails else f"{fails} TA XATO")
sys.exit(1 if fails else 0)
