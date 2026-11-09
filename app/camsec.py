"""Kameralar: xavfsizlik voqealari, kamera salomatligi, navbat va olomon, haftalik xavfsizlik hisoboti.

Tamoyillar (buzilmaydi):
  * Privacy-by-design: rasm/kadr saqlanmaydi — faqat voqea metama'lumoti (vaqt, kamera, tur, son, holat).
  * Yuzni tanish va avtoraqam — bayroq ortida (ZRU-547: alohida yozma rozilik va huquqiy asos). Yuz: faqat kirish kameralari,
    faqat yozma roziligi bor shaxslar (app/facecam.py — "Kirish nazorati (Face ID)"); demo uchun bayroq yoqilgan, tasvirlar sintetik.
  * Talaba yoki xodim ismi kamera voqeasiga bog'lanmaydi: hisobotlar xona/bino/qavat bo'yicha, jamlangan holda.
  * Kamera boshqaruvi va voqealarni belgilash — faqat rektor va xo'jalik bo'limi; har amal audit jurnaliga yoziladi.
  * Voqea vaqti — server vaqti (Asia/Tashkent), kamera soati emas; soat farqi > 60 s — ogohlantirish.
  * Qarorlarni deterministik qoidalar chiqaradi (POLICY); AI faqat bazadagi faktlarni matnga aylantiradi.
"""
import datetime as dt, json, math, os, random
from collections import Counter, defaultdict
from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel, Field
from . import db, rbac, hikvision as HK
from .rbac import Ctx, AccessDenied, SPACES

router = APIRouter()
_con = None
_ctx = None

FEATURE_FACE = os.getenv("ISFT_CORE_FEATURE_FACE", "1") == "1"    # Kirish nazorati (Face ID): app/facecam.py — faqat rozilik bergan shaxslar
FEATURE_ANPR = os.getenv("ISFT_CORE_FEATURE_ANPR", "0") == "1"
DEDUP_SEC = int(os.getenv("ISFT_CORE_CAM_DEDUP_SEC", "300"))      # bir xil voqea 5 daqiqa ichida — bitta yozuv (dup+1)
DEDUP_LONG_SEC = 3600                                              # navbat / sig'im — soatiga bitta yozuv
QUEUE_PATH = os.getenv("ISFT_CORE_CAM_QUEUE_PATH", "/ISAPI/Intelligent/channels/{ch}/queueManagement/status")
OFFLINE_MIN = 10            # kamera shuncha daqiqa javob bermasa — avtomatik tiket
OVER_PCT = 1.10             # sig'imning 110% dan oshsa — xo'jalik bo'limiga ogohlantirish
UNSCHED_MIN = 20            # dars yo'q, xonada 20+ kishi
MANAGERS = ("rektor", "xojalik")
CAMERA_ADMINS = ("it_head",)          # AT bo'limi: faqat kamera texnik holati (oflayn, to'sish, fokus, proshivka) — xavfsizlik voqealari emas
NO_SECURITY_VIEW = ("kengash",)       # Kuzatuv kengashi: bandlik/olomon statistikasi — ha; xavfsizlik voqealari va kameralar ro'yxati — yo'q

# ---------------------------------------------------------------------------------------------
# Voqealar siyosati: tur → (yorliq, kun ustuvorligi, tun ustuvorligi, kimga, guruh)
# ---------------------------------------------------------------------------------------------
POLICY = {
    "yongin": (1, 1, ("rektor", "xojalik"), "favqulodda"),
    "tutun": (1, 1, ("rektor", "xojalik"), "favqulodda"),
    "harorat": (1, 1, ("rektor", "xojalik"), "favqulodda"),
    "hududga_kirish": (3, 2, ("xojalik",), "xavfsizlik"),
    "chiziq_kesish": (4, 2, ("xojalik",), "xavfsizlik"),
    "hududdan_chiqish": (4, 3, ("xojalik",), "xavfsizlik"),
    "uzoq_turish": (3, 2, ("xojalik",), "xavfsizlik"),
    "toplanish": (3, 2, ("xojalik", "prorektor_yoshlar"), "xavfsizlik"),
    "yugurish": (4, 3, ("xojalik",), "xavfsizlik"),
    "qarovsiz_buyum": (2, 2, ("xojalik", "rektor"), "xavfsizlik"),
    "buyum_olindi": (3, 2, ("xojalik",), "xavfsizlik"),
    "harakat": (4, 3, ("xojalik",), "xavfsizlik"),
    "kamera_yopildi": (2, 2, ("xojalik", "it_head"), "kamera"),
    "video_yoqoldi": (3, 3, ("xojalik", "it_head"), "kamera"),
    "kamera_siljidi": (3, 3, ("xojalik", "it_head"), "kamera"),
    "olomon": (3, 3, ("xojalik",), "olomon"),
    "navbat": (3, 3, (), "olomon"),
    "sigim_oshdi": (3, 3, ("xojalik",), "olomon"),
    "odam_soni": (4, 4, (), "olomon"),
    "xodim_keldi": (4, 4, ("kadrlar",), "bayroq"),
    "avtoraqam": (4, 4, ("xojalik",), "bayroq"),
}
INTRUSION = {"hududga_kirish", "chiziq_kesish", "hududdan_chiqish", "harakat", "uzoq_turish"}
CAM_KINDS = {"kamera_yopildi", "video_yoqoldi", "kamera_siljidi"}
GROUP_LABEL = {"favqulodda": "Favqulodda (yong'in, tutun, harorat)", "xavfsizlik": "Xavfsizlik", "kamera": "Kamera holati",
               "olomon": "Olomon va navbat", "bayroq": "Bayroq ortida"}
STATUS_LABEL = {"yangi": "Yangi", "korildi": "Ko'rildi", "tiket": "Tiketga aylandi", "notogri": "Noto'g'ri signal",
                "yopildi": "Yopildi", "qayd": "Qayd (P4)"}
PRIO_LABEL = {1: "P1 — favqulodda", 2: "P2 — yuqori", 3: "P3 — o'rta", 4: "P4 — qayd"}

# Zonalar: xizmat hududlari (auditoriyalardan tashqari)
ZONE_LABEL = {"qabul": "Qabul komissiyasi", "kassa": "Kassa", "oshxona": "Oshxona", "zal": "Majlislar zali", "kirish": "Bosh kirish",
              "serverxona": "Serverxona", "texnik": "Texnik xona", "tom": "Tomga chiqish", "koridor": "Koridor"}
ZONE_ROUTE = {"qabul": ("qabul",), "kassa": ("buxgalteriya",), "oshxona": ("xojalik",), "zal": ("prorektor_yoshlar", "xojalik")}
QUEUE_ZONES = {   # navbat chegarasi (kishi), mas'ul, xizmat ko'rsatish (daqiqa/kishi) — TAXMIN, institut tasdiqlaydi
    "qabul": {"limit": 20, "unit": "Qabul komissiyasi", "role": "qabul", "svc": 2.0},
    "kassa": {"limit": 10, "unit": "Buxgalteriya (kassa)", "role": "buxgalteriya", "svc": 1.5},
    "oshxona": {"limit": 25, "unit": "Xo'jalik bo'limi (oshxona)", "role": "xojalik", "svc": 0.35},
}

# Kamera modellari: imkoniyatlar TAXMINIY — har model datasheet'i va proshivkasi bo'yicha AT bo'limi tasdiqlashi kerak
MODELS = {
    "DS-2CD2346G2-ISU/SL": {"family": "AcuSense", "caps": ["VMD", "videoloss", "shelteralarm", "defocus", "scenechangedetection", "linedetection",
                                                         "fielddetection", "regionEntrance", "regionExiting"],
                            "counting": "chiziq kesish orqali (taxminiy)"},
    "DS-2CD3D46G2T": {"family": "Oddiy", "caps": ["VMD", "videoloss", "shelteralarm", "linedetection", "fielddetection"], "counting": "yo'q"},
    "iDS-2CD7A46G0": {"family": "DeepinView", "caps": ["VMD", "videoloss", "shelteralarm", "defocus", "scenechangedetection", "linedetection",
                                                     "fielddetection", "regionEntrance", "regionExiting", "loitering", "peopleGathering", "running",
                                                     "unattendedBaggage", "attendedBaggage", "objectRemoval", "personQueueDetection",
                                                     "peopleCounting", "regionPeopleCounting"], "counting": "bor (to'g'ridan-to'g'ri)"},
    "iDS-2CD7146G0-IZS": {"family": "DeepinView (yuz)", "caps": ["VMD", "videoloss", "shelteralarm", "defocus", "linedetection", "fielddetection",
                                                             "faceCapture", "faceContrast", "FDLib", "peopleCounting"],
                          "counting": "bor (kirish chizig'i)"},
    "DS-2TD2617": {"family": "Termal", "caps": ["fireDetection", "smokeDetection", "TMA", "linedetection", "fielddetection", "VMD", "videoloss",
                                               "shelteralarm"], "counting": "yo'q"},
}
CAP_LABEL = {"VMD": "harakat", "videoloss": "tasvir yo'qolishi", "shelteralarm": "to'sib qo'yish", "defocus": "fokus buzilishi",
             "scenechangedetection": "kamera siljishi", "linedetection": "chiziq kesish", "fielddetection": "hududga kirish",
             "regionEntrance": "hududga kirish/chiqish", "regionExiting": "hududdan chiqish", "loitering": "uzoq turib qolish",
             "peopleGathering": "to'planish", "running": "yugurish", "unattendedBaggage": "qarovsiz buyum", "attendedBaggage": "buyum olib ketish",
             "objectRemoval": "buyum olib ketish", "personQueueDetection": "navbat", "peopleCounting": "odam sanash",
             "regionPeopleCounting": "hududda odam sanash", "faceCapture": "yuzni ajratish", "faceContrast": "yuzni solishtirish (rozilik bilan)",
             "FDLib": "yuz kutubxonasi", "fireDetection": "yong'in", "smokeDetection": "tutun", "TMA": "harorat"}

def model_of(m: str) -> dict:
    for k, v in MODELS.items():
        if (m or "").startswith(k[:13]): return {"name": k, **v}
    return {"name": m or "", "family": "noma'lum", "caps": [], "counting": "noma'lum"}

SCHEMA = """
CREATE TABLE IF NOT EXISTS cam_queue(room_id INT, ts TEXT, length INT, wait_min REAL);
CREATE INDEX IF NOT EXISTS ix_cam_queue ON cam_queue(room_id, ts);
CREATE TABLE IF NOT EXISTS cam_story(key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS face_consent(staff_id INT PRIMARY KEY, employee_no TEXT UNIQUE, consent_doc TEXT, granted_at TEXT, revoked_at TEXT);
CREATE TABLE IF NOT EXISTS staff_vehicles(id INTEGER PRIMARY KEY, staff_id INT, plate TEXT UNIQUE, consent_doc TEXT);
"""

def init(con):
    con.executescript(SCHEMA)
    def add(table, cols):
        have = {r[1] for r in con.execute(f"PRAGMA table_info({table})")}
        for name, typ in cols:
            if name not in have: con.execute(f"ALTER TABLE {table} ADD COLUMN {name} {typ}")
    add("rooms", [("floor", "INT"), ("zone", "TEXT")])
    add("cameras", [("fw", "TEXT"), ("fw_date", "TEXT"), ("ai_caps", "TEXT"), ("clock_skew", "INT"), ("sim_fault", "TEXT"),
                    ("ticket_kind", "TEXT"), ("thermal", "INT DEFAULT 0"), ("installed", "TEXT")])
    add("cam_events", [("priority", "INT"), ("route", "TEXT"), ("status", "TEXT"), ("dup", "INT DEFAULT 0"), ("last_ts", "TEXT"),
                       ("ticket_id", "INT"), ("value", "REAL"), ("wait_s", "REAL"), ("night", "INT DEFAULT 0"),
                       ("handled_by", "TEXT"), ("handled_at", "TEXT")])
    con.execute("CREATE INDEX IF NOT EXISTS ix_cam_ev_kind ON cam_events(camera_id, kind, last_ts)")
    con.execute("CREATE INDEX IF NOT EXISTS ix_cam_ev_ts ON cam_events(ts)")
    # qavat: "A-205 · ..." → 2; koridor "A-bino · 1-qavat ..." → 1
    for rid, name in con.execute("SELECT id, name FROM rooms WHERE floor IS NULL").fetchall():
        n = name or ""
        f = int(n[2]) if len(n) > 2 and n[1] == "-" and n[2].isdigit() else (int(n.split("· ")[1][0]) if "-qavat" in n and n.split("· ")[1][:1].isdigit() else None)
        if f is not None: con.execute("UPDATE rooms SET floor=? WHERE id=?", (f, rid))
    con.execute("UPDATE rooms SET zone='koridor' WHERE kind='umumiy' AND zone IS NULL")
    con.commit()

def bind(con, ctx_fn):
    global _con, _ctx
    _con, _ctx = con, ctx_fn

def _oc():
    from . import occupancy as OC
    return OC

def now(): return _oc().now()
def iso(t): return t.isoformat(timespec="seconds")
def room_label(r) -> str:
    n = r.get("name") or r.get("room") or ""
    return n.replace(" · ", ", ") if r.get("zone") else n.split(" ·")[0]

# ---------------------------------------------------------------------------------------------
# Ustuvorlik va yo'naltirish (deterministik)
# ---------------------------------------------------------------------------------------------
def is_night(t: dt.datetime) -> bool:
    return not _oc()._in_work_hours(t)

def priority(kind: str, room: dict, night: bool) -> int:
    pd, pn, _, _ = POLICY.get(kind, (4, 4, (), "boshqa"))
    p = pn if night else pd
    if kind in INTRUSION and not room.get("guard"):     # qo'riqlanmaydigan joyda bir daraja past
        p = min(4, p + 1)
    return p

def route(kind: str, room: dict, pr: int) -> list:
    roles = list(POLICY.get(kind, (4, 4, (), ""))[2])
    if kind in ("navbat", "olomon", "sigim_oshdi") and room.get("zone") in ZONE_ROUTE:
        roles = list(ZONE_ROUTE[room["zone"]])
    if pr == 1 and "rektor" not in roles: roles.append("rektor")
    return roles

def role_title(k): return rbac.ROLES[k].title if k in rbac.ROLES else k

def _room(con, rid):
    return db.one(con, "SELECT id, name, building, floor, zone, guard, capacity, kind FROM rooms WHERE id=?", (rid,)) or {}

# ---------------------------------------------------------------------------------------------
# Voqeani qayta ishlash: normallashtirish → bayroqlar → dedup → ustuvorlik → yozuv (+ tiket / navbat)
# ---------------------------------------------------------------------------------------------
def process_event(con, cam: dict, raw: dict, t: dt.datetime | None = None):
    t = t or now()
    con.execute("UPDATE cameras SET ev_last=?, ev_status='onlayn' WHERE id=?", (iso(t), cam["id"]))
    room = _room(con, cam["room_id"])
    ev = HK.normalize(raw, keep_vmd=bool(room.get("guard")), face=FEATURE_FACE, anpr=FEATURE_ANPR)
    if not ev:
        con.commit(); return None
    if ev["kind"] == "yuz":            # yuzni solishtirish (FPID) — Kirish nazorati moduli: rozilik, ko'lam, rasm muddati o'sha yerda
        from . import facecam
        r = facecam.ingest(con, cam, ev, t)
        con.commit(); return r
    if ev["kind"] == "xodim_keldi":    # faqat yozma rozilik bergan xodim (ro'yxatda) — aks holda hech narsa saqlanmaydi
        ok = ev.get("subject") and db.one(con, "SELECT 1 x FROM face_consent WHERE employee_no=? AND revoked_at IS NULL", (ev["subject"],))
        if not ok:
            con.commit(); return None
    if ev["kind"] == "avtoraqam":
        ok = ev.get("subject") and db.one(con, "SELECT 1 x FROM staff_vehicles WHERE plate=?", (ev["subject"],))
        if not ok:
            con.commit(); return None
    if ev["state"] == "inactive":      # voqea tugadi — ochiq yozuv yopiladi (alohida qator yozilmaydi)
        _resolve(con, cam, ev["kind"], t, "Kamera: voqea tugadi (inactive)")
        con.commit(); return None
    return record(con, cam, ev["kind"], t, room=room, raw_type=ev["raw_type"], count=ev.get("count"), value=ev.get("value"),
                  wait_s=ev.get("wait_s"), dev_ts=ev.get("dev_ts"), channel=ev.get("channel"))

def _resolve(con, cam, kind, t, note):
    con.execute("""UPDATE cam_events SET status='yopildi', handled_at=?, handled_by='ISFT Core (avtomatik)', note=COALESCE(note,'') || ?
                   WHERE camera_id=? AND kind=? AND status IN ('yangi','korildi')""", (iso(t), f" · {note}", cam["id"], kind))
    if kind in CAM_KINDS:
        c = db.one(con, "SELECT * FROM cameras WHERE id=?", (cam["id"],))
        if c and c.get("ticket_id") and c.get("ticket_kind") == "voqea":
            _oc().close_cam_ticket(con, c, "Kamera voqeasi tugadi — avtomatik yopildi")

def record(con, cam, kind, t, *, room=None, raw_type=None, count=None, value=None, wait_s=None, dev_ts=None, channel=None, note=None):
    """Bitta voqea. Qaytaradi: yozuv (dict) yoki None — dedup oynasida takror (mavjud yozuvning dup soni oshadi)."""
    room = room or _room(con, cam["room_id"])
    night = is_night(t)
    pr = priority(kind, room, night)
    win = DEDUP_LONG_SEC if kind in ("navbat", "sigim_oshdi", "olomon") else DEDUP_SEC
    last = db.one(con, """SELECT id FROM cam_events WHERE camera_id=? AND kind=? AND COALESCE(last_ts, ts)>=? AND ts<=?
                          ORDER BY id DESC LIMIT 1""",   # noto'g'ri deb belgilangan voqea oynasidagi takror ham unga qo'shiladi
                  (cam["id"], kind, iso(t - dt.timedelta(seconds=win)), iso(t + dt.timedelta(seconds=win))))
    if last:
        con.execute("""UPDATE cam_events SET dup=COALESCE(dup,0)+1, last_ts=MAX(COALESCE(last_ts,ts), ?),
                       count=MAX(COALESCE(count,0), COALESCE(?,0)), value=COALESCE(?, value) WHERE id=?""", (iso(t), count, value, last["id"]))
        if kind == "navbat" and count is not None: _queue_sample(con, cam["room_id"], t, count, wait_s, room)
        con.commit(); return None
    roles = route(kind, room, pr)
    if note is None:
        if kind in INTRUSION and room.get("guard") and night:
            note = f"Ish vaqtidan tashqari ({_oc().WORK_HOURS}) qo'riqlanadigan " + ("hududda harakat" if kind == "harakat" else "hududga kirish")
        elif kind == "harorat" and value is not None:
            note = f"Harorat {value:.1f} °C"
        elif kind == "navbat" and count is not None:
            note = f"Navbatda {count} kishi" + (f", kutish ~{round(wait_s / 60)} daqiqa" if wait_s else "")
        else:
            note = HK.KIND_LABEL.get(kind, kind)
    status = "qayd" if pr == 4 else "yangi"
    cur = con.execute("""INSERT INTO cam_events(camera_id,room_id,ts,last_ts,dev_ts,kind,state,raw_type,channel,count,alert,note,priority,route,status,
                         dup,value,wait_s,night) VALUES(?,?,?,?,?,?,'active',?,?,?,?,?,?,?,?,0,?,?,?)""",
                      (cam["id"], cam["room_id"], iso(t), iso(t), dev_ts, kind, raw_type or kind, channel, count, int(pr <= 2), note, pr,
                       ",".join(roles), status, value, wait_s, int(night)))
    eid = cur.lastrowid
    tid = None
    if kind in CAM_KINDS:
        c = db.one(con, "SELECT * FROM cameras WHERE id=?", (cam["id"],))
        tid = _oc().open_cam_ticket(con, c, f"Kamera voqeasi: {HK.KIND_LABEL.get(kind, kind)}", kind="voqea")
    elif pr == 1:     # favqulodda — xo'jalik bo'limida kuzatiladigan ariza darhol ochiladi
        tid = _security_ticket(con, room, f"{HK.KIND_LABEL.get(kind, kind)}: {note}", t)
    if tid:
        con.execute("UPDATE cam_events SET ticket_id=?, status=CASE WHEN status='yangi' AND ?=1 THEN 'yangi' ELSE status END WHERE id=?", (tid, pr, eid))
    if kind == "navbat" and count is not None: _queue_sample(con, cam["room_id"], t, count, wait_s, room)
    con.commit()
    return {"id": eid, "kind": kind, "priority": pr, "alert": int(pr <= 2), "note": note, "route": roles, "ticket_id": tid, "state": "active"}

def _security_ticket(con, room, text, t):
    cur = con.execute("INSERT INTO tickets(room_id,item,text,photo,reporter,created_at,status) VALUES(?,?,?,?,?,?,?)",
                      (room.get("id"), "Xavfsizlik", text[:600], None, "ISFT Core (kamera voqeasi)", iso(t), "yangi"))
    return cur.lastrowid

def _queue_sample(con, room_id, t, length, wait_s, room=None):
    last = db.one(con, "SELECT ts FROM cam_queue WHERE room_id=? ORDER BY ts DESC LIMIT 1", (room_id,))
    if last and last["ts"] > iso(t - dt.timedelta(minutes=5)): return
    z = QUEUE_ZONES.get((room or {}).get("zone") or "", {})
    wm = round(wait_s / 60, 1) if wait_s else round(length * z.get("svc", 1.0), 1)
    con.execute("INSERT INTO cam_queue(room_id,ts,length,wait_min) VALUES(?,?,?,?)", (room_id, iso(t), int(length), wm))

# ---------------------------------------------------------------------------------------------
# Simulyator (kamera hali ulanmagan zonalar): deterministik, real ko'rinishdagi raqamlar
# ---------------------------------------------------------------------------------------------
def _hm(s): h, m = map(int, s.split(":")); return h * 60 + m

def queue_sim(zone: str, t: dt.datetime) -> int:
    wd, m = t.weekday(), t.hour * 60 + t.minute
    if wd == 6 or m < _hm("09:00") or m > _hm("17:30"): return 0
    rng = random.Random(f"q{zone}|{t.date()}|{t.hour}|{t.minute // 15}")
    if zone == "qabul":
        base = 27 if (wd == 0 and _hm("10:00") <= m < _hm("12:00")) else (11 if wd == 0 else 7) + 3 * math.sin((m - 540) / 120)
    elif zone == "kassa":
        base = 8 if (t.day <= 10 and _hm("09:00") <= m < _hm("11:30")) else 3
    elif zone == "oshxona":
        base = 22 if _hm("12:50") <= m <= _hm("13:30") else (6 if _hm("09:50") <= m <= _hm("10:00") or _hm("11:20") <= m <= _hm("11:30") else 1)
    else:
        return 0
    return max(0, int(round(base + rng.uniform(-3, 3.5))))

def zone_sim(zone: str, cap: int, room_id: int, t: dt.datetime, events: dict) -> int:
    wd, m = t.weekday(), t.hour * 60 + t.minute
    rng = random.Random(f"z{room_id}|{t.date()}|{t.hour}|{t.minute // 15}")
    if wd == 6: return 0
    brk = any(_hm(a) <= m <= _hm(b) for a, b in (("09:50", "10:00"), ("11:20", "11:30"), ("12:50", "13:30"), ("14:50", "15:00"), ("16:20", "16:30")))
    if zone == "oshxona":
        if _hm("12:50") <= m <= _hm("13:30"): f = rng.uniform(1.15, 1.26) if wd < 5 else rng.uniform(.45, .6)
        elif brk: f = rng.uniform(.25, .4)
        elif _hm("08:30") <= m <= _hm("17:00"): f = rng.uniform(.05, .15)
        else: f = 0
        return int(round(cap * f))
    if zone in ("qabul", "kassa"):
        q = queue_sim(zone, t)
        return q + (3 if q or _hm("09:00") <= m <= _hm("17:30") else 0)
    if zone == "zal":
        n = events.get(t.date().isoformat())
        if n and _hm("14:00") <= m <= _hm("16:00"): return int(round(min(cap * 1.05, n * rng.uniform(1.02, 1.14))))
        return rng.choice([0, 0, 0, 2, 4]) if _hm("08:30") <= m <= _hm("18:00") else 0
    if zone == "koridor":
        if brk: return rng.randint(25, 60)
        return rng.randint(2, 10) if _hm("08:15") <= m <= _hm("18:15") else 0
    if zone == "kirish":
        if _hm("08:00") <= m <= _hm("08:35") or _hm("12:50") <= m <= _hm("13:30") or _hm("17:50") <= m <= _hm("18:10"): return rng.randint(30, 80)
        return rng.randint(3, 15) if _hm("07:30") <= m <= _hm("19:00") else 0
    # serverxona / texnik / tom — odatda bo'sh; kunduzi ba'zan 1 kishi (xizmat ko'rsatish)
    return 1 if (_hm("09:00") <= m <= _hm("17:00") and rng.random() < .05) else 0

def story(con) -> dict:
    try:
        return {r[0]: r[1] for r in con.execute("SELECT key, value FROM cam_story").fetchall()}
    except Exception:
        return {}

# ---------------------------------------------------------------------------------------------
# Fon so'rovchisi uchun ilmoq: sig'im (110%+) va navbat namunasi
# ---------------------------------------------------------------------------------------------
async def after_count(con, cam: dict, n: int, t: dt.datetime):
    cap, zone = cam.get("capacity") or 0, cam.get("zone")
    if cap and n > cap * OVER_PCT and not is_night(t):
        record(con, cam, "sigim_oshdi", t, count=n, note=f"{n} kishi / {cap} o'rin ({round(100 * n / cap)}%)")
    if zone in QUEUE_ZONES:
        last = db.one(con, "SELECT ts FROM cam_queue WHERE room_id=? ORDER BY ts DESC LIMIT 1", (cam["room_id"],))
        if last and last["ts"] > iso(t - dt.timedelta(minutes=5)): return
        if cam.get("mode") == "isapi":
            try:
                q = await _oc().cam_client(cam).queue_status(int(cam.get("channel") or 1), QUEUE_PATH)
            except HK.IsapiError:
                return
            length, wait_s = q["length"], q["wait_s"]
        else:
            length, wait_s = queue_sim(zone, t), None
        room = {"zone": zone}
        _queue_sample(con, cam["room_id"], t, length, wait_s, room)
        if length > QUEUE_ZONES[zone]["limit"]:
            record(con, cam, "navbat", t, count=length, wait_s=wait_s)

# ---------------------------------------------------------------------------------------------
# Ruxsat
# ---------------------------------------------------------------------------------------------
def _view(con, ctx: Ctx, action, quiet=False):
    if quiet:
        if not ctx.can(SPACES): raise AccessDenied("")
    else:
        rbac.require(con, ctx, SPACES, action)

def _security_view(con, ctx: Ctx, action, quiet=False):
    _view(con, ctx, action, quiet)
    if ctx.role.key in NO_SECURITY_VIEW:
        rbac.audit(con, ctx, action, SPACES, False, "xavfsizlik voqealari — operativ ma'lumot")
        raise AccessDenied("⛔ Kamera voqealari va holati — operativ ma'lumot (xo'jalik bo'limi, AT bo'limi va rektor). Kuzatuv kengashiga jamlangan bandlik statistikasi ochiq.")

def _manage(con, ctx: Ctx, action, detail=""):
    rbac.require(con, ctx, SPACES, action, detail)
    if ctx.role.key not in MANAGERS + CAMERA_ADMINS:
        rbac.audit(con, ctx, action, SPACES, False, "faqat xo'jalik bo'limi, AT bo'limi va rektor")
        raise AccessDenied("⛔ Kameralar va voqealarni faqat xo'jalik bo'limi va rektor boshqaradi (kamera texnik holati — AT bo'limi). So'rov audit jurnaliga yozildi.")

# ---------------------------------------------------------------------------------------------
# D. Kamera salomatligi
# ---------------------------------------------------------------------------------------------
def _cams(con):
    return db.rows(con, """SELECT c.*, r.name room, r.building, r.floor, r.zone, r.guard, r.capacity, r.kind room_kind
                           FROM cameras c JOIN rooms r ON r.id=c.room_id ORDER BY r.building, r.floor, r.name""")

def _dur(sec: float) -> str:
    sec = int(sec)
    if sec < 3600: return f"{max(1, sec // 60)} daqiqa"
    if sec < 86400: return f"{sec // 3600} soat"
    return f"{sec // 86400} kun"

def camera_health(con, t=None) -> list:
    t = t or now()
    active = defaultdict(set)
    for r in con.execute("""SELECT camera_id, kind FROM cam_events WHERE kind IN ('kamera_yopildi','video_yoqoldi','kamera_siljidi')
                            AND status IN ('yangi','korildi','tiket')""").fetchall():
        active[r[0]].add(r[1])
    tickets = {r[0]: r for r in con.execute("SELECT id, status, created_at FROM tickets WHERE item='Kamera'").fetchall()}
    out = []
    for c in _cams(con):
        reasons, lvl = [], "yashil"
        hb = c.get("last_seen"); age = (t - dt.datetime.fromisoformat(hb)).total_seconds() if hb else None
        if c["status"] == "xato" or (age is not None and age > OFFLINE_MIN * 60):
            lvl = "qizil"; reasons.append(f"Javob bermayapti{' — ' + _dur(age) if age else ''}")
        elif c["status"] == "kutilmoqda" or hb is None:
            lvl = "sariq"; reasons.append("Hali ulanmagan")
        if "kamera_yopildi" in active[c["id"]]: lvl = "qizil"; reasons.append("Kamera to'sib qo'yilgan")
        if "video_yoqoldi" in active[c["id"]]: lvl = "qizil"; reasons.append("Tasvir yo'q")
        if "kamera_siljidi" in active[c["id"]]:
            if lvl == "yashil": lvl = "sariq"
            reasons.append("Kamera siljigan / fokus")
        sk = c.get("clock_skew")
        if sk is not None and abs(sk) > HK.SKEW_WARN_S:
            if lvl == "yashil": lvl = "sariq"
            reasons.append(f"Soat farqi {HK._dur(abs(sk))} — NTP sozlansin")
        if HK.fw_too_old(c.get("fw_date") or ""):
            if lvl == "yashil": lvl = "sariq"
            reasons.append("Proshivka 2021-sentabrdan eski (CVE-2021-36260) — yangilansin")
        fw_age = None
        d = "".join(ch for ch in (c.get("fw_date") or "") if ch.isdigit())
        if len(d) == 6: fw_age = round((t.date() - dt.date(2000 + int(d[:2]), int(d[2:4]), max(1, int(d[4:6])))).days / 365, 1)
        tk = tickets.get(c.get("ticket_id")) if c.get("ticket_id") else None
        m = model_of(c.get("model"))
        out.append({"id": c["id"], "room": room_label(c), "building": c["building"], "floor": c["floor"], "zone": c.get("zone"),
                    "model": c.get("model") or ("Simulyator" if c["mode"] == "sim" else ""), "family": m["family"], "ip": c.get("host") or "",
                    "fw": c.get("fw"), "fw_age": fw_age, "skew": sk, "heartbeat": hb, "age_s": int(age) if age is not None else None,
                    "level": lvl, "reasons": reasons, "mode": c["mode"], "thermal": bool(c.get("thermal")),
                    "ticket": {"id": tk[0], "status": tk[1], "created_at": tk[2],
                               "overdue": tk[1] != "hal qilindi" and (t - dt.datetime.fromisoformat(tk[2])).total_seconds() > 86400} if tk else None})
    return out

def health(con, ctx: Ctx, quiet=False):
    _security_view(con, ctx, "kameralar holati", quiet)
    t = now(); cams = camera_health(con, t)
    by_b = defaultdict(lambda: defaultdict(list))
    for c in cams: by_b[c["building"]][c["floor"] if c["floor"] is not None else -1].append(c)
    cnt = Counter(c["level"] for c in cams)
    buildings = [{"building": b, "floors": [{"floor": f, "label": "yerto'la" if f == 0 else f"{f}-qavat",
                                             "cams": [{k: c[k] for k in ("id", "room", "level", "reasons", "model", "zone")} for c in fl],
                                             "levels": dict(Counter(c["level"] for c in fl))} for f, fl in sorted(floors.items())],
                  "levels": dict(Counter(c["level"] for fl in floors.values() for c in fl))} for b, floors in sorted(by_b.items())]
    offline = [c for c in cams if any(r.startswith("Javob bermayapti") for r in c["reasons"])]
    blocked = [c for c in cams if "Kamera to'sib qo'yilgan" in c["reasons"]]
    models = Counter(c["model"] for c in cams)
    return {"now": iso(t), "total": len(cams), "levels": {"yashil": cnt["yashil"], "sariq": cnt["sariq"], "qizil": cnt["qizil"]},
            "online": len(cams) - len(offline) - len(blocked), "offline": len(offline), "blocked": len(blocked),
            "online_pct": round(100 * (len(cams) - len(offline) - len(blocked)) / max(1, len(cams)), 1),
            "skew": sum(1 for c in cams if c["skew"] is not None and abs(c["skew"]) > HK.SKEW_WARN_S),
            "old_fw": sum(1 for c in cams if any("Proshivka" in r for r in c["reasons"])),
            "buildings": buildings, "problems": sorted([c for c in cams if c["level"] != "yashil"], key=lambda c: (c["level"] != "qizil", c["room"])),
            "models": [{"model": k, **{x: model_of(k)[x] for x in ("family", "counting")}, "n": v,
                        "caps": list(dict.fromkeys(CAP_LABEL.get(x, x) for x in model_of(k)["caps"]))} for k, v in models.most_common()],
            "offline_after_min": OFFLINE_MIN, "can_manage": ctx.role.key in MANAGERS + CAMERA_ADMINS,
            "flags": {"face": FEATURE_FACE, "anpr": FEATURE_ANPR}}

# ---------------------------------------------------------------------------------------------
# B. Xavfsizlik voqealari
# ---------------------------------------------------------------------------------------------
def events(con, ctx: Ctx, days=7, prio=0, status="", group="", limit=150, quiet=False):
    _security_view(con, ctx, "kamera voqealari", quiet)
    t = now(); since = iso(t - dt.timedelta(days=max(1, min(int(days), 31))))
    w, a = ["e.ts>=?"], [since]
    if prio: w.append("e.priority<=?"); a.append(int(prio))
    if status: w.append("e.status=?"); a.append(status)
    rows = db.rows(con, f"""SELECT e.id, e.ts, e.last_ts, e.kind, e.priority, e.route, e.status, e.dup, e.note, e.count, e.value, e.night,
                            e.ticket_id, e.handled_by, e.handled_at, r.name room, r.building, r.floor, r.zone, c.model
                            FROM cam_events e JOIN rooms r ON r.id=e.room_id JOIN cameras c ON c.id=e.camera_id
                            WHERE {' AND '.join(w)} ORDER BY e.ts DESC""", a)
    for r in rows:
        r["group"] = POLICY.get(r["kind"], (4, 4, (), "boshqa"))[3]
        r["label"] = HK.KIND_LABEL.get(r["kind"], r["kind"]); r["room"] = room_label(r)
        r["route_titles"] = [role_title(x) for x in (r["route"] or "").split(",") if x]
        r["priority"] = r["priority"] or 4
    if group: rows = [r for r in rows if r["group"] == group]
    st = _stats(rows)
    return {"days": days, "events": rows[:limit], "stats": st, "can_manage": ctx.role.key in MANAGERS + CAMERA_ADMINS,
            "manage_groups": ["kamera"] if ctx.role.key in CAMERA_ADMINS else None,
            "status_label": STATUS_LABEL, "prio_label": PRIO_LABEL, "group_label": GROUP_LABEL, "dedup_sec": DEDUP_SEC}

def _stats(rows):
    sec = [r for r in rows if (r["priority"] or 4) <= 3]
    handled = [r for r in sec if r["status"] in ("yopildi", "notogri", "tiket")]
    false_ = [r for r in sec if r["status"] == "notogri"]
    by_kind = Counter(r["kind"] for r in rows)
    return {"total": len(rows), "by_priority": {p: sum(1 for r in rows if (r["priority"] or 4) == p) for p in (1, 2, 3, 4)},
            "open": sum(1 for r in sec if r["status"] in ("yangi", "korildi")), "false": len(false_), "tickets": sum(1 for r in rows if r["ticket_id"]),
            "false_rate": round(100 * len(false_) / max(1, len(handled)), 1), "merged": sum(r["dup"] or 0 for r in rows),
            "night": sum(1 for r in sec if r["night"]),
            "by_kind": [{"kind": k, "label": HK.KIND_LABEL.get(k, k), "n": n} for k, n in by_kind.most_common(12)],
            "by_building": dict(Counter(r["building"] for r in sec))}

ACTIONS = {"korildi": "ko'rildi", "notogri": "noto'g'ri signal deb belgilandi", "tiket": "tiketga aylantirildi", "yopildi": "yopildi"}

def event_action(con, ctx: Ctx, eid: int, action: str, note: str = ""):
    if action not in ACTIONS: raise HTTPException(400, "Noma'lum amal")
    _manage(con, ctx, f"kamera voqeasi: {ACTIONS[action]}", f"#{eid}")
    e = db.one(con, "SELECT e.*, r.name room, r.zone, r.id rid FROM cam_events e JOIN rooms r ON r.id=e.room_id WHERE e.id=?", (eid,))
    if not e: raise HTTPException(404, "Voqea topilmadi")
    if ctx.role.key in CAMERA_ADMINS and (POLICY.get(e["kind"]) or (0, 0, (), ""))[3] != "kamera":
        rbac.audit(con, ctx, f"kamera voqeasi: {ACTIONS[action]}", SPACES, False, f"#{eid} {e['kind']} — AT bo'limi faqat kamera texnik holati")
        raise AccessDenied("⛔ AT bo'limi faqat kamera texnik holati voqealarini (to'sish, tasvir yo'qolishi, siljish) boshqaradi. So'rov audit jurnaliga yozildi.")
    t = now(); who = ctx.title
    if action == "tiket":
        if e.get("ticket_id"):
            return {"ok": True, "ticket_id": e["ticket_id"], "status": e["status"]}
        tid = _security_ticket(con, {"id": e["rid"]}, f"{HK.KIND_LABEL.get(e['kind'], e['kind'])} — {room_label(e)}, {e['ts'][:16].replace('T', ' ')}"
                               + (f": {note}" if note else "") + " (kamera voqeasi, faqat metama'lumot)", t)
        con.execute("UPDATE cam_events SET status='tiket', ticket_id=?, handled_by=?, handled_at=? WHERE id=?", (tid, who, iso(t), eid))
    else:
        con.execute("UPDATE cam_events SET status=?, handled_by=?, handled_at=?, note=CASE WHEN ?!='' THEN COALESCE(note,'') || ' · ' || ? ELSE note END WHERE id=?",
                    (action, who, iso(t), note[:200], note[:200], eid))
    con.commit()
    return {"ok": True, **db.one(con, "SELECT status, ticket_id FROM cam_events WHERE id=?", (eid,))}

# ---------------------------------------------------------------------------------------------
# C. Navbat va olomon
# ---------------------------------------------------------------------------------------------
DAYS = ["Dushanba", "Seshanba", "Chorshanba", "Payshanba", "Juma", "Shanba"]

def _queue_view_ok(ctx: Ctx, zone: str) -> bool:
    return ctx.can(SPACES) or ctx.role.key == QUEUE_ZONES.get(zone, {}).get("role")

def queues(con, ctx: Ctx, quiet=False):
    zones = [z for z in QUEUE_ZONES if _queue_view_ok(ctx, z)]
    if not zones:
        rbac.require(con, ctx, SPACES, "navbat va olomon")    # ruxsatsiz urinish — har doim auditga
    rbac.audit(con, ctx, "navbat va olomon", SPACES, True) if not quiet else None
    t = now(); today = t.date().isoformat(); since = iso(dt.datetime.combine(t.date() - dt.timedelta(days=28), dt.time()))
    out = []
    for z in zones:
        r = db.one(con, "SELECT id, name, zone, capacity FROM rooms WHERE zone=?", (z,))
        if not r: continue
        cfg = QUEUE_ZONES[z]
        rows = con.execute("SELECT ts, length, wait_min FROM cam_queue WHERE room_id=? AND ts>=? ORDER BY ts", (r["id"], since)).fetchall()
        cur = next(((x[0], x[1], x[2]) for x in reversed(rows) if x[0][:10] == today), None)
        today_s = [{"ts": x[0], "n": x[1], "wait": x[2]} for x in rows if x[0][:10] == today]
        acc = defaultdict(list); breach_days = set(); mx = {}
        for ts, n, _ in rows:
            d = dt.date.fromisoformat(ts[:10])
            if d.weekday() < 6 and 9 <= int(ts[11:13]) <= 17: acc[(d.weekday(), int(ts[11:13]))].append(n)
            if n > cfg["limit"]: breach_days.add(ts[:10])
            mx[ts[:10]] = max(mx.get(ts[:10], 0), n)
        heat = [[round(sum(acc[(wd, h)]) / len(acc[(wd, h)]), 1) if acc[(wd, h)] else None for h in range(9, 18)] for wd in range(6)]
        pattern = []
        for wd in range(6):     # chegaradan oshgan ketma-ket soatlar → "Dushanba 10:00–12:00, o'rtacha 28 kishi"
            hs = [h for h in range(9, 18) if (heat[wd][h - 9] or 0) > cfg["limit"]]
            if hs:
                vals = [heat[wd][h - 9] for h in hs]
                pattern.append({"day": DAYS[wd], "from": f"{hs[0]:02d}:00", "to": f"{hs[-1] + 1:02d}:00", "avg": round(sum(vals) / len(vals)),
                                "text": f"{DAYS[wd]} {hs[0]:02d}:00–{hs[-1] + 1:02d}:00 — o'rtacha {round(sum(vals) / len(vals))} kishi (chegara {cfg['limit']})"})
        out.append({"zone": z, "name": ZONE_LABEL[z], "room": room_label(r), "limit": cfg["limit"], "unit": cfg["unit"],
                    "now": {"ts": cur[0], "n": cur[1], "wait": cur[2]} if cur else None, "today": today_s,
                    "heat": heat, "hours": [f"{h:02d}" for h in range(9, 18)], "days": DAYS, "pattern": pattern,
                    "breach_days": len(breach_days), "peak": max(mx.values()) if mx else 0,
                    "daily_max": [{"date": d, "n": n} for d, n in sorted(mx.items())[-14:]]})
    crowd = _crowd(con, t) if ctx.can(SPACES) else None
    hall = _hall(con, t) if ctx.can(SPACES) else None
    return {"now": iso(t), "zones": out, "crowd": crowd, "hall": hall}

def _crowd(con, t):
    r = db.one(con, "SELECT id, name, zone, capacity FROM rooms WHERE zone='oshxona'")
    if not r or not r["capacity"]: return None
    since = (t.date() - dt.timedelta(days=14)).isoformat()
    rows = con.execute("""SELECT substr(ts,1,10) d, MAX(count) mx FROM occupancy WHERE room_id=? AND ts>=? AND substr(ts,12,5) BETWEEN '12:45' AND '13:35'
                          GROUP BY d ORDER BY d""", (r["id"], since)).fetchall()
    days = [{"date": d, "peak": mx, "pct": round(100 * mx / r["capacity"])} for d, mx in rows]
    over = [x for x in days if x["pct"] > 100 * OVER_PCT]
    return {"room": room_label(r), "capacity": r["capacity"], "days": days, "over_days": len(over),
            "max_pct": max((x["pct"] for x in days), default=0),
            "text": (f"Oshxona tushlikda (12:50–13:30) 14 kundan {len(over)} kunida sig'imdan {max(x['pct'] for x in over) - 100}% gacha oshgan"
                     if over else "Oshxona sig'imdan oshmagan")}

def _hall(con, t):
    r = db.one(con, "SELECT id, name, capacity FROM rooms WHERE zone='zal'")
    if not r: return None
    since = (t.date() - dt.timedelta(days=45)).isoformat()
    evs = db.rows(con, """SELECT e.id, e.title, e.date, e.participants, (SELECT COUNT(*) FROM event_checkin c WHERE c.event_id=e.id) checkin
                          FROM events e WHERE e.date>=? AND e.date<=? ORDER BY e.date DESC LIMIT 12""",
                   (since, (t.date() if t.hour >= 16 else t.date() - dt.timedelta(days=1)).isoformat()))
    out = []
    for e in evs:
        pk = con.execute("SELECT MAX(count) FROM occupancy WHERE room_id=? AND substr(ts,1,10)=?", (r["id"], e["date"])).fetchone()[0]
        out.append({**e, "camera_peak": pk, "fill_pct": round(100 * pk / r["capacity"]) if pk and r["capacity"] else None,
                    "gap": (pk - e["checkin"]) if pk is not None and e["checkin"] else None})
    return {"room": room_label({"name": r["name"], "zone": "zal"}), "capacity": r["capacity"], "events": out}

# ---------------------------------------------------------------------------------------------
# E. KPI, ogohlantirishlar, AI suhbat uchun faktlar, haftalik hisobot
# ---------------------------------------------------------------------------------------------
def kpi(con, ctx: Ctx):
    if not ctx.can(SPACES): return None
    t = now(); d0 = dt.datetime.combine(t.date(), dt.time())
    p12 = con.execute("SELECT COUNT(*) FROM cam_events WHERE ts>=? AND priority<=2 AND COALESCE(status,'')!='notogri'", (iso(d0),)).fetchone()[0]
    ser = []
    for i in range(6, -1, -1):
        a = d0 - dt.timedelta(days=i)
        ser.append(con.execute("SELECT COUNT(*) FROM cam_events WHERE ts>=? AND ts<? AND priority<=2 AND COALESCE(status,'')!='notogri'",
                               (iso(a), iso(a + dt.timedelta(days=1)))).fetchone()[0])
    cams = camera_health(con, t)
    off = sum(1 for c in cams if any(r.startswith("Javob bermayapti") for r in c["reasons"]))
    b = busiest_building(con)
    sub = f"{off} kamera oflayn" + (f" · eng band: {b['building']} ({b['pct']}%)" if b else "")
    return {"label": "Kameralar: P1/P2 bugun", "value": p12, "sub": sub, "key": "kameralar", "source": "Hikvision kameralari (demo: simulyator)",
            "updated": iso(t), "spark": ser, "spark_kind": "bars", "spark_labels": [(t.date() - dt.timedelta(days=6 - i)).isoformat() for i in range(7)],
            "bad": bool(p12 or off), "offline": off}

def busiest_building(con):
    rows = con.execute("""SELECT r.building, SUM(c.last_count) n, SUM(r.capacity) cap FROM cameras c JOIN rooms r ON r.id=c.room_id
                          WHERE c.status='onlayn' AND r.capacity>0 AND r.zone IS NULL GROUP BY r.building""").fetchall()
    rows = [(b, n or 0, cap) for b, n, cap in rows if cap]
    if not rows: return None
    b, n, cap = max(rows, key=lambda x: x[1] / x[2])
    return {"building": b, "people": n, "pct": round(100 * n / cap)}

def alerts(con, ctx: Ctx) -> list:
    out = []
    t = now()
    if ctx.can(SPACES):
        p1 = db.rows(con, """SELECT e.kind, e.ts, e.note, r.name room, r.zone FROM cam_events e JOIN rooms r ON r.id=e.room_id
                             WHERE e.ts>=? AND e.priority=1 AND e.status IN ('yangi','korildi','tiket') ORDER BY e.ts DESC""", (iso(t - dt.timedelta(hours=24)),))
        for e in p1[:2]:
            out.append({"level": "high", "area": "Favqulodda", "text": f"{room_label(e)}: {HK.KIND_LABEL.get(e['kind'])} ({e['ts'][11:16]}) — {e['note']}"})
        night = db.rows(con, """SELECT e.ts, e.note, r.name room, r.zone FROM cam_events e JOIN rooms r ON r.id=e.room_id
                                WHERE e.ts>=? AND e.priority=2 AND e.kind IN ('hududga_kirish','chiziq_kesish','harakat','uzoq_turish')
                                AND COALESCE(e.status,'')!='notogri' ORDER BY e.ts DESC""", (iso(t - dt.timedelta(hours=24)),))
        if night:
            out.append({"level": "high", "area": "Xavfsizlik", "text": f"{room_label(night[0])}: {night[0]['note']} ({night[0]['ts'][11:16]}) — 24 soatda {len(night)} ta"})
        late = [c for c in camera_health(con, t) if c["ticket"] and c["ticket"]["overdue"]]
        if late:
            c = max(late, key=lambda c: c["age_s"] or 0)
            out.append({"level": "mid", "area": "Kameralar", "text": f"{c['room']} kamerasi {_dur(c['age_s'] or 0)}dan beri oflayn — tiket #{c['ticket']['id']} muddati o'tgan"
                        + (f" (jami {len(late)} ta muddati o'tgan kamera tiketi)" if len(late) > 1 else "")})
    for z, cfg in QUEUE_ZONES.items():
        if not _queue_view_ok(ctx, z) or (z == "oshxona" and not ctx.can(SPACES)): continue
        r = db.one(con, "SELECT id FROM rooms WHERE zone=?", (z,))
        if not r: continue
        cur = db.one(con, "SELECT length, ts FROM cam_queue WHERE room_id=? AND ts>=? ORDER BY ts DESC LIMIT 1", (r["id"], iso(t - dt.timedelta(minutes=20))))
        if cur and cur["length"] > cfg["limit"]:
            out.append({"level": "mid", "area": "Navbat", "text": f"{ZONE_LABEL[z]}: hozir navbatda {cur['length']} kishi (chegara {cfg['limit']}) — {cfg['unit']}ga xabar berildi"})
    return out

def agent_tool(con, ctx: Ctx, quiet=False):
    """AI suhbat uchun faqat bazadagi faktlar (shaxssiz, xona/bino kesimida)."""
    _view(con, ctx, "kameralar: suhbat uchun faktlar", quiet)
    OC = _oc(); t = now()
    d = t.date() - dt.timedelta(days=1)
    while d.weekday() == 6: d -= dt.timedelta(days=1)
    a0 = dt.datetime.combine(d, dt.time()); av = OC._slot_avgs(con, a0, a0 + dt.timedelta(days=1))
    sc = OC._sched(con); rooms = OC._rooms(con)
    empty_les, unused = [], []
    for r in rooms:
        used = False
        for n, _, _ in OC.SLOTS:
            v = av.get((r["id"], d, n))
            if v is None: continue
            if v >= OC.BUSY_MIN: used = True
            les = sc["map"].get((r["id"], d.weekday(), n))
            if les and v <= OC.GHOST_MAX: empty_les.append({"room": r["name"].split(" ·")[0], "slot": n, "avg": round(v, 1)})
        if not used: unused.append(r["name"].split(" ·")[0])
    w0 = iso(dt.datetime.combine(t.date() - dt.timedelta(days=6), dt.time()))     # so'nggi 7 kun (bugun bilan)
    ev = db.rows(con, "SELECT kind, priority, status, ticket_id, night FROM cam_events WHERE ts>=?", (w0,))
    sec = [e for e in ev if (e["priority"] or 4) <= 3]
    h = camera_health(con, t)
    q = queues(con, ctx, quiet=True) if any(_queue_view_ok(ctx, z) for z in QUEUE_ZONES) else {"zones": [], "crowd": None}
    st = story(con)
    idle = [x for x in st.get("idle_names", "").split("|") if x]
    return {"day": d.isoformat(), "day_note": "" if d == t.date() - dt.timedelta(days=1) else "oxirgi ish kuni", "empty_lessons": empty_les, "unused_rooms": unused, "rooms_total": len(rooms),
            "week": {"from": w0[:10], "total": len(sec), "p1": sum(1 for e in sec if e["priority"] == 1), "p2": sum(1 for e in sec if e["priority"] == 2),
                     "p3": sum(1 for e in sec if e["priority"] == 3), "false": sum(1 for e in sec if e["status"] == "notogri"),
                     "tickets": sum(1 for e in sec if e["ticket_id"]), "night": sum(1 for e in sec if e["night"]),
                     "kinds": Counter(HK.KIND_LABEL.get(e["kind"], e["kind"]) for e in sec).most_common(4)},
            "offline": [c["room"] + f" ({_dur(c['age_s'] or 0)})" for c in h if any(r.startswith("Javob bermayapti") for r in c["reasons"])],
            "blocked": [c["room"] for c in h if "Kamera to'sib qo'yilgan" in c["reasons"]],
            "cams_total": len(h), "patterns": [p["text"] for z in q["zones"] for p in [{"text": f"{z['name']}: {x['text']}"} for x in z["pattern"]]],
            "crowd": (q.get("crowd") or {}).get("text"), "idle_rooms": idle}

def agent_facts(v: dict) -> dict:
    """agent.py uchun: faktlar, sabablar, tavsiyalar (raqamlar koddan)."""
    dmy = lambda s: f"{s[8:10]}.{s[5:7]}.{s[:4]}"
    facts = []
    el = v["empty_lessons"]
    if el:
        rooms = Counter(x["room"] for x in el)
        facts.append(f"{dmy(v['day'])}{' (' + v['day_note'] + ')' if v.get('day_note') else ''} kuni jadvaldagi {len(el)} ta darsda xona deyarli bo'sh turdi (kamera ≤ 2 kishi): "
                     + ", ".join(f"{r} ({n} para)" for r, n in rooms.most_common(6)) + ".")
    else:
        facts.append(f"{dmy(v['day'])} kuni jadvaldagi barcha darslarda xonalarda odam bo'lgan.")
    if v["unused_rooms"]:
        facts.append(f"Shu kuni {len(v['unused_rooms'])} ta auditoriya ({v['rooms_total']} tadan) kun bo'yi ishlatilmadi: " + ", ".join(v["unused_rooms"][:8])
                     + ("…" if len(v["unused_rooms"]) > 8 else "") + ".")
    w = v["week"]
    facts.append(f"So'nggi 7 kunda ({dmy(w['from'])} dan) {w['total']} ta xavfsizlik voqeasi (P1–P3): P1 — {w['p1']}, P2 — {w['p2']}, P3 — {w['p3']}; "
                 f"noto'g'ri signal — {w['false']}, tiketga aylangan — {w['tickets']}, tunda — {w['night']}.")
    if w["kinds"]: facts.append("Eng ko'p turlar: " + ", ".join(f"{k} ({n})" for k, n in w["kinds"]) + ".")
    facts.append(f"Kameralar: {v['cams_total']} ta, oflayn — {len(v['offline'])}" + (f" ({', '.join(v['offline'][:4])})" if v["offline"] else "")
                 + f", to'sib qo'yilgan — {len(v['blocked'])}.")
    why = []
    if v["idle_rooms"]:
        why.append(f"{' va '.join(v['idle_rooms'])} 2 haftadan beri jadvalga qaramay deyarli bo'sh — dars boshqa xonaga ko'chgan yoki o'tmayapti.")
    why += v["patterns"][:3]
    if v.get("crowd"): why.append(v["crowd"] + ".")
    recs = [{"text": "Kameralar sahifasida voqealarni ko'rib chiqing: noto'g'ri signallarni belgilash statistikani aniqlashtiradi.",
             "action": {"type": "go", "view": "cams", "label": "Kameralar va xavfsizlik"}}]
    if v["idle_rooms"]:
        recs.insert(0, {"text": f"O'quv bo'limiga: {', '.join(v['idle_rooms'])} jadvalini tekshirish — darslarni ko'chirish yoki xonani boshqa maqsadga berish.",
                        "action": {"type": "go", "view": "spaces", "label": "Auditoriyalar bandligi"}})
    return {"facts": facts, "why": why, "recs": recs, "sev": 2 if (w["p1"] or w["p2"] or v["offline"]) else 1,
            "head": f"kameralar: 7 kunda {w['total']} voqea, {len(v['offline'])} kamera oflayn"}

def build_report(con, ctx: Ctx, base_url: str) -> dict:
    """Haftalik xavfsizlik hisoboti (.docx, rasmiy blank, QR bilan tekshiriladi). Shaxsiy ma'lumot yo'q."""
    _view(con, ctx, "haftalik xavfsizlik hisoboti")
    if not ctx.can(rbac.REPORTS) and ctx.role.key not in MANAGERS:
        raise AccessDenied("⛔ Hisobot tayyorlash huquqi yo'q.")
    from . import documents as D, brand as B
    t = now(); d1 = t.date(); d0 = d1 - dt.timedelta(days=7)
    ev = events(con, ctx, days=7, quiet=True); st = ev["stats"]; h = health(con, ctx, quiet=True); q = queues(con, ctx, quiet=True)
    I = D.Issuer(con, ctx, {"key": "cam_weekly", "prefix": "XAV", "title": "Haftalik xavfsizlik hisoboti"}, base_url)
    I.page("ISFT instituti (kameralar tizimi)")
    B.title(I.doc, "HAFTALIK XAVFSIZLIK HISOBOTI", f"{d0.strftime('%d.%m.%Y')} — {d1.strftime('%d.%m.%Y')} · kameralar (faqat metama'lumot)")
    B.para(I.doc, f"Hisobot davrida kameralar {st['total']} ta voqea qayd etdi (takrorlari birlashtirilgan: yana {st['merged']} ta signal). "
                  f"P1 — {st['by_priority'][1]}, P2 — {st['by_priority'][2]}, P3 — {st['by_priority'][3]}, P4 (qayd) — {st['by_priority'][4]}. "
                  f"Noto'g'ri signallar ulushi — {st['false_rate']}%, tiketga aylangan — {st['tickets']}, hozir ochiq — {st['open']}.")
    B.para(I.doc, "1. Voqealar turlari bo'yicha", indent=False, bold=True)
    B.table(I.doc, ["Tur", "Soni"], [(k["label"], k["n"]) for k in st["by_kind"]], [12, 3])
    top = [e for e in ev["events"] if e["priority"] <= 2][:15]
    if top:
        B.para(I.doc, "2. Yuqori ustuvorlikdagi voqealar (P1–P2)", indent=False, bold=True)
        B.table(I.doc, ["Vaqt", "Joy", "Voqea", "Holat"], [(f"{e['ts'][8:10]}.{e['ts'][5:7]} {e['ts'][11:16]}", e["room"], e["label"] + (f" ×{e['dup'] + 1}" if e["dup"] else ""),
                                                            STATUS_LABEL.get(e["status"], e["status"])) for e in top], [3, 5, 6, 3])
    B.para(I.doc, "3. Kameralar holati", indent=False, bold=True)
    B.para(I.doc, f"Jami {h['total']} ta kamera: onlayn {h['online']} ({h['online_pct']}%), oflayn {h['offline']}, to'sib qo'yilgan {h['blocked']}, "
                  f"soat farqi > 60 s — {h['skew']}, eskirgan proshivka — {h['old_fw']}.")
    pr = [c for c in h["problems"] if c["level"] == "qizil"][:12]
    if pr:
        B.table(I.doc, ["Joy", "Model", "Muammo", "Tiket"], [(c["room"], c["model"], "; ".join(c["reasons"]),
                                                              (f"#{c['ticket']['id']}" + (" (muddati o'tgan)" if c["ticket"]["overdue"] else "")) if c["ticket"] else "—")
                                                             for c in pr], [4, 4, 7, 2])
    pats = [f"{z['name']}: {p['text']}" for z in q["zones"] for p in z["pattern"]]
    if pats or q.get("crowd"):
        B.para(I.doc, "4. Navbat va olomon", indent=False, bold=True)
        for x in pats + ([q["crowd"]["text"]] if q.get("crowd") else []): B.para(I.doc, "• " + x, indent=False)
    B.para(I.doc, "Tamoyillar: rasm va video saqlanmaydi, yuzni tanish o'chirilgan, voqealar shaxsga bog'lanmaydi — hisobot xona, bino va qavat "
                  "kesimida jamlangan. Ma'lumotlar demo (sun'iy) — haqiqiy kameralar ulangach haqiqiy voqealar bilan almashadi.", indent=False, size=10)
    B.signature(I.doc, "Xo'jalik va texnik bo'lim boshlig'i")
    I.qr()
    r = I.save({"period": f"{d0}..{d1}"})
    return {"ok": True, **r}

# ---------------------------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------------------------
@router.get("/api/cams/health")
def api_health(request: Request):
    return health(_con, _ctx(request))

@router.get("/api/cams/events")
def api_events(request: Request, days: int = 7, prio: int = 0, status: str = "", group: str = ""):
    c = _ctx(request)
    return events(_con, c, days, prio, status, group, quiet=c.can(SPACES))   # ruxsat bo'lsa — qayta audit yo'q; bo'lmasa — rad etish auditga

class ActIn(BaseModel):
    note: str = Field("", max_length=200)

@router.post("/api/cams/events/{eid}/{action}")
def api_event_action(eid: int, action: str, request: Request, body: ActIn | None = None):
    return event_action(_con, _ctx(request), eid, action, (body.note if body else "") or "")

@router.get("/api/cams/queues")
def api_queues(request: Request):
    return queues(_con, _ctx(request), quiet=True)

@router.get("/api/cams/summary")
def api_summary(request: Request):
    c = _ctx(request); _view(_con, c, "kameralar: qisqacha")
    return {"kpi": kpi(_con, c), "alerts": alerts(_con, c), "flags": {"face": FEATURE_FACE, "anpr": FEATURE_ANPR}}

@router.post("/api/cams/report")
def api_report(request: Request):
    c = _ctx(request)
    return build_report(_con, c, str(request.base_url))
