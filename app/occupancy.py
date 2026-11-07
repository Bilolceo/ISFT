"""Auditoriyalar bandligi — kameralardan FAQAT odamlar soni (video, yuz, shaxs yo'q).

Ulagichlar:
  • isapi — Hikvision IP-kamera, lokal tarmoq, HTTP Digest. Bandlik = bugungi kirganlar − chiqqanlar
            (POST /ISAPI/System/Video/inputs/channels/{ch}/counting/search, reportType=daily).
            Kamera "region people counting" qo'llasa, OCC_PATH sozlamasi bilan to'g'ridan-to'g'ri son o'qiladi.
  • sim   — kamera hali o'rnatilmagan xonalar uchun simulyator: dars jadvali + davomat asosida real ko'rinishdagi son.
Fon jarayoni har POLL_SEC soniyada kameralarni so'raydi va natijani occupancy jadvaliga yozadi.
Tahlil: hozirgi holat, 4 haftalik bandlik, hafta×para issiqlik xaritasi, "dars bor — xona bo'sh", sig'imdan oshish.
"""
import asyncio, datetime as dt, json, os, random, re, xml.etree.ElementTree as ET
from collections import defaultdict
import httpx
from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel, Field
from . import db, rbac, hikvision as HK, secret_store as SS
from .rbac import Ctx, AccessDenied, SPACES

router = APIRouter()
_con = None
_ctx = None
POLL_SEC = int(os.getenv("JARVIS_CAM_POLL", "60"))
SAMPLE_EVERY_MIN = 5
OFFLINE_FAILS = int(os.getenv("JARVIS_CAM_OFFLINE_FAILS", "3"))   # ketma-ket xato so'rovlar → nosozlik arizasi
WORK_HOURS = os.getenv("JARVIS_WORK_HOURS", "07:30-20:00")        # bundan tashqarida qo'riqlanadigan xonaga kirish — ogohlantirish
EVENT_DEDUP_SEC = 30
OCC_PATH = os.getenv("JARVIS_CAM_OCC_PATH", "")   # masalan: /ISAPI/Intelligent/channels/{ch}/regionPeopleCounting (modelga bog'liq)

SLOTS = [(1, "08:30", "09:50"), (2, "10:00", "11:20"), (3, "11:30", "12:50"), (4, "13:30", "14:50"), (5, "15:00", "16:20"), (6, "16:30", "17:50")]
DAYS = ["Dushanba", "Seshanba", "Chorshanba", "Payshanba", "Juma", "Shanba"]
BUSY_MIN = 5          # xona "band" hisoblanishi uchun minimal odam soni
GHOST_MAX = 2         # dars bor, lekin xonada <= 2 kishi — "tekshirish kerak"

SCHEMA = """
CREATE TABLE IF NOT EXISTS cameras(id INTEGER PRIMARY KEY, room_id INT UNIQUE, vendor TEXT, model TEXT, mode TEXT, host TEXT, channel INT DEFAULT 1,
  username TEXT, password TEXT, status TEXT, last_seen TEXT, last_error TEXT, last_count INT);
CREATE TABLE IF NOT EXISTS occupancy(room_id INT, ts TEXT, count INT);
CREATE INDEX IF NOT EXISTS occ_room_ts ON occupancy(room_id, ts);
CREATE INDEX IF NOT EXISTS occ_ts ON occupancy(ts);
CREATE TABLE IF NOT EXISTS cam_events(id INTEGER PRIMARY KEY, camera_id INT, room_id INT, ts TEXT, dev_ts TEXT, kind TEXT, state TEXT,
  raw_type TEXT, channel INT, count INT, alert INT DEFAULT 0, note TEXT);
CREATE INDEX IF NOT EXISTS ix_cam_events ON cam_events(room_id, ts);
CREATE TABLE IF NOT EXISTS schedule(id INTEGER PRIMARY KEY, room_id INT, weekday INT, slot INT, group_id INT, subject TEXT, teacher_id INT);
CREATE INDEX IF NOT EXISTS sch_room ON schedule(room_id, weekday, slot);
"""

def init(con):
    con.executescript(SCHEMA)
    cols = {r[1] for r in con.execute("PRAGMA table_info(rooms)")}
    if "capacity" not in cols:
        con.execute("ALTER TABLE rooms ADD COLUMN capacity INT DEFAULT 40")
    if "guard" not in cols:
        con.execute("ALTER TABLE rooms ADD COLUMN guard INT DEFAULT 0")   # ish vaqtidan tashqari kirishni kuzatish
    have = {r[1] for r in con.execute("PRAGMA table_info(cameras)")}
    for name, typ in [("scheme", "TEXT DEFAULT 'http'"), ("port", "INT"), ("caps", "TEXT"), ("fail_count", "INT DEFAULT 0"),
                      ("ticket_id", "INT"), ("events", "INT DEFAULT 0"), ("ev_status", "TEXT"), ("ev_last", "TEXT")]:
        if name not in have: con.execute(f"ALTER TABLE cameras ADD COLUMN {name} {typ}")
    # parollar bazadan maxfiy omborga ko'chiriladi (bazada ochiq parol qolmaydi)
    for cid, pw in con.execute("SELECT id, password FROM cameras WHERE COALESCE(password,'')!=''").fetchall():
        SS.put(f"camera:{cid}", pw)
        con.execute("UPDATE cameras SET password='' WHERE id=?", (cid,))
    con.commit()

def bind(con, ctx_fn):
    global _con, _ctx
    _con, _ctx = con, ctx_fn
    init(con)

def now(): return dt.datetime.now().replace(microsecond=0)
def iso(t): return t.isoformat(timespec="seconds")
def hm(s): h, m = map(int, s.split(":")); return h * 60 + m

def slot_at(t: dt.datetime):
    m = t.hour * 60 + t.minute
    for n, a, b in SLOTS:
        if hm(a) <= m <= hm(b): return n
    return None

# =====================================================================
# Ulagichlar
# =====================================================================
def _xml_vals(text, *names):
    """Namespace'dan qat'i nazar kerakli teglar qiymatlarini yig'adi."""
    root = ET.fromstring(text)
    out = defaultdict(list)
    for el in root.iter():
        tag = el.tag.split("}")[-1]
        if tag in names and el.text and el.text.strip().lstrip("-").isdigit():
            out[tag].append(int(el.text.strip()))
    return out

IsapiError = HK.IsapiError

def cam_client(cam) -> HK.HikClient:
    pw = SS.get(f"camera:{cam['id']}") if cam.get("id") else None
    return HK.HikClient(cam["host"], cam["username"] or "", pw if pw is not None else (cam.get("password") or ""),
                        scheme=cam.get("scheme") or "http", port=cam.get("port"))

async def isapi_device_info(cam) -> dict:
    return await cam_client(cam).device_info()

async def isapi_count(cam) -> int:
    return await cam_client(cam).count(int(cam["channel"] or 1), OCC_PATH)

# --- simulyator: jadval + davomat asosida, (xona, sana, para) bo'yicha deterministik ---
_sched_cache = {"t": 0, "map": {}, "gsize": {}, "att": {}}
def _sched(con):
    if _sched_cache["t"] > dt.datetime.now().timestamp() - 300 and _sched_cache["map"]: return _sched_cache
    m = {}
    for s in db.rows(con, "SELECT * FROM schedule"): m[(s["room_id"], s["weekday"], s["slot"])] = s
    gs = {r["group_id"]: r["n"] for r in db.rows(con, "SELECT group_id, COUNT(*) n FROM students GROUP BY group_id")}
    att = {r["group_id"]: r["a"] for r in db.rows(con, "SELECT group_id, AVG(attendance)/100.0 a FROM students GROUP BY group_id")}
    _sched_cache.update(t=dt.datetime.now().timestamp(), map=m, gsize=gs, att=att)
    if GHOST_TEACHER["id"] is None:   # demo ssenariysi: seshanba/payshanba 5-parada darsi bor birinchi o'qituvchi
        cnt = defaultdict(int)
        for x in m.values():
            if x["weekday"] in (1, 3) and x["slot"] == 5 and x["teacher_id"]: cnt[x["teacher_id"]] += 1
        GHOST_TEACHER["id"] = min(cnt, key=lambda k: (-cnt[k], k)) if cnt else 0
    return _sched_cache

GHOST_TEACHER = {"id": None}   # demo: bitta o'qituvchining ma'lum paralarida xona bo'sh qoladi (seed belgilaydi)

def sim_count(con, room_id, t: dt.datetime) -> int:
    sc = _sched(con)
    wd = t.weekday()
    if wd == 6: return 0
    n = slot_at(t)
    rng = random.Random(f"{room_id}|{t.date()}|{n}|{t.hour}{t.minute // 15}")
    if n is None:
        m = t.hour * 60 + t.minute
        return 0 if m < hm("08:15") or m > hm("18:10") else rng.choice([0, 0, 0, 1, 2, 3, 5])
    les = sc["map"].get((room_id, wd, n))
    if not les:
        return rng.choice([0] * 7 + [1, 2, 4, 7])        # bo'sh xona, ba'zan mustaqil ta'lim
    lrng = random.Random(f"{room_id}|{t.date()}|{n}")   # butun para uchun bir xil qaror
    ghost = lrng.random() < 0.008 or (GHOST_TEACHER["id"] and les["teacher_id"] == GHOST_TEACHER["id"] and wd in (1, 3) and n == 5)
    if ghost: return rng.choice([0, 0, 1, 2])
    size = sc["gsize"].get(les["group_id"], 25)
    if les["subject"].startswith("Ma'ruza"): size = int(size * 2.6)   # oqim ma'ruzasi: 2–3 guruh birga
    base = size * sc["att"].get(les["group_id"], .85) * lrng.uniform(.82, 1.02)
    start = hm(SLOTS[n - 1][1]); m = t.hour * 60 + t.minute
    ramp = .55 if m - start < 8 else 1.0                  # boshida hali kelib ulgurmaganlar
    return max(0, int(round(base * ramp + rng.uniform(-1.5, 1.5))))

async def read_camera(con, cam) -> int:
    if cam["mode"] == "isapi": return await isapi_count(cam)
    return sim_count(con, cam["room_id"], now())

# =====================================================================
# Fon so'rovchisi
# =====================================================================
async def poller():
    await asyncio.sleep(3)
    while True:
        try:
            await poll_once()
        except Exception as e:  # fon jarayoni hech qachon to'xtamasin
            print("occupancy poller:", e)
        await asyncio.sleep(POLL_SEC)

async def poll_once():
    con = _con; t = now()
    cams = db.rows(con, "SELECT * FROM cameras")
    async def one(cam):
        try:
            n = await read_camera(con, cam); return cam, n, None
        except Exception as e:
            return cam, None, str(e)[:200] or e.__class__.__name__
    res = await asyncio.gather(*(one(c) for c in cams))
    for cam, n, err in res:
        if err:
            fails = (cam.get("fail_count") or 0) + 1
            con.execute("UPDATE cameras SET status='xato', last_error=?, fail_count=? WHERE id=?", (err, fails, cam["id"]))
            if fails >= OFFLINE_FAILS and cam["mode"] == "isapi":
                open_cam_ticket(con, cam, f"Kamera javob bermayapti ({fails} marta ketma-ket): {err}")
            continue
        con.execute("UPDATE cameras SET status='onlayn', last_seen=?, last_error=NULL, last_count=?, fail_count=0 WHERE id=?", (iso(t), n, cam["id"]))
        if cam.get("ticket_id"): close_cam_ticket(con, cam, "Kamera qayta onlayn — avtomatik yopildi")
        last = db.one(con, "SELECT ts FROM occupancy WHERE room_id=? ORDER BY ts DESC LIMIT 1", (cam["room_id"],))
        if not last or dt.datetime.fromisoformat(last["ts"]) <= t - dt.timedelta(minutes=SAMPLE_EVERY_MIN):
            con.execute("INSERT INTO occupancy(room_id,ts,count) VALUES(?,?,?)", (cam["room_id"], iso(t), n))
    con.commit()

# =====================================================================
# Kamera nosozligi → Xizmat markazi arizasi (avtomatik ochiladi va yopiladi)
# =====================================================================
CAM_ITEM = "Kamera"

def open_cam_ticket(con, cam, reason: str):
    if cam.get("ticket_id"):
        t = db.one(con, "SELECT status FROM tickets WHERE id=?", (cam["ticket_id"],))
        if t and t["status"] != "hal qilindi": return cam["ticket_id"]     # allaqachon ochiq — dublikat yo'q
    cur = con.execute("INSERT INTO tickets(room_id,item,text,photo,reporter,created_at,status) VALUES(?,?,?,?,?,?,?)",
                      (cam["room_id"], CAM_ITEM, reason[:600], None, "JARVIS (avtomatik)", iso(now()), "yangi"))
    con.execute("UPDATE cameras SET ticket_id=? WHERE id=?", (cur.lastrowid, cam["id"]))
    return cur.lastrowid

def close_cam_ticket(con, cam, note: str):
    con.execute("UPDATE tickets SET status='hal qilindi', resolved_at=?, note=? WHERE id=? AND status!='hal qilindi'",
                (iso(now()), note, cam["ticket_id"]))
    con.execute("UPDATE cameras SET ticket_id=NULL WHERE id=?", (cam["id"],))

# =====================================================================
# Voqealar oqimi (alertStream): har bir kamera uchun fon tinglovchisi, qayta ulanish backoff bilan
# =====================================================================
EVT = {"tasks": {}}

def _in_work_hours(t: dt.datetime) -> bool:
    a, b = WORK_HOURS.split("-")
    return t.weekday() != 6 and hm(a) <= t.hour * 60 + t.minute <= hm(b)

def handle_event(con, cam, raw: dict, t: dt.datetime | None = None):
    """Bitta xom voqeani qayta ishlaydi. Qaytaradi: saqlangan yozuv yoki None (yurak urishi / shovqin / takror)."""
    t = t or now()
    con.execute("UPDATE cameras SET ev_last=?, ev_status='onlayn' WHERE id=?", (iso(t), cam["id"]))
    ev = HK.normalize(raw)
    if not ev:
        con.commit(); return None
    last = db.one(con, "SELECT ts FROM cam_events WHERE camera_id=? AND kind=? AND state=? ORDER BY id DESC LIMIT 1",
                  (cam["id"], ev["kind"], ev["state"]))
    if last and dt.datetime.fromisoformat(last["ts"]) > t - dt.timedelta(seconds=EVENT_DEDUP_SEC):
        con.commit(); return None                         # bir xil voqea 30 s ichida takrorlansa — bitta yozuv
    room = db.one(con, "SELECT guard, name FROM rooms WHERE id=?", (cam["room_id"],)) or {}
    alert, note = 0, None
    if ev["kind"] in ("hududga_kirish", "chiziq_kesish") and room.get("guard") and not _in_work_hours(t):
        alert, note = 1, f"Ish vaqtidan tashqari ({WORK_HOURS}) qo'riqlanadigan xonaga kirish"
    if ev["kind"] in ("kamera_yopildi", "video_yoqoldi", "kamera_siljidi") and ev["state"] == "active":
        alert = 1; note = HK.KIND_LABEL.get(ev["kind"], ev["kind"])
        open_cam_ticket(con, db.one(con, "SELECT * FROM cameras WHERE id=?", (cam["id"],)), f"Kamera voqeasi: {note}")
    cur = con.execute("""INSERT INTO cam_events(camera_id,room_id,ts,dev_ts,kind,state,raw_type,channel,count,alert,note)
                         VALUES(?,?,?,?,?,?,?,?,?,?,?)""", (cam["id"], cam["room_id"], iso(t), ev["dev_ts"], ev["kind"], ev["state"],
                                                          ev["raw_type"], ev["channel"], ev["count"], alert, note))
    con.commit()
    return {"id": cur.lastrowid, **ev, "alert": alert, "note": note}

async def _listen(cam_id: int):
    delay = 5
    while True:
        cam = db.one(_con, "SELECT * FROM cameras WHERE id=?", (cam_id,))
        if not cam or cam["mode"] != "isapi" or not cam.get("events"): return
        try:
            async for raw in cam_client(cam).alert_stream():
                handle_event(_con, cam, raw); delay = 5
            err = "Voqealar oqimi yopildi"
        except HK.IsapiError as e:
            err = str(e)
        except Exception as e:   # tinglovchi hech qachon butun serverni yiqitmasin
            err = f"{e.__class__.__name__}: {str(e)[:120]}"
        _con.execute("UPDATE cameras SET ev_status=? WHERE id=?", (f"uzildi: {err}"[:200], cam_id)); _con.commit()
        await asyncio.sleep(delay); delay = min(delay * 2, 120)

async def events_supervisor():
    """Voqealar yoqilgan kameralar uchun tinglovchilarni ishga tushiradi/to'xtatadi (har 30 s)."""
    await asyncio.sleep(4)
    while True:
        try:
            want = {c["id"] for c in db.rows(_con, "SELECT id FROM cameras WHERE mode='isapi' AND events=1")}
            for cid, task in list(EVT["tasks"].items()):
                if cid not in want or task.done():
                    task.cancel(); EVT["tasks"].pop(cid, None)
            for cid in want - set(EVT["tasks"]):
                EVT["tasks"][cid] = asyncio.create_task(_listen(cid))
        except Exception as e:
            print("events supervisor:", e)
        await asyncio.sleep(30)

# =====================================================================
# Tahlil
# =====================================================================
def _need(ctx: Ctx, action, quiet=False):
    if quiet:
        if not ctx.can(SPACES): raise AccessDenied("")
    else:
        rbac.require(_con, ctx, SPACES, action)

def _rooms(con):
    return db.rows(con, "SELECT r.*, c.id cam_id, c.mode, c.status, c.last_seen, c.last_count, c.last_error FROM rooms r JOIN cameras c ON c.room_id=r.id ORDER BY r.name")

def _slot_avgs(con, since, until):
    """(xona, sana, para) bo'yicha o'rtacha son — paraning 10-daqiqasidan keyingi o'lchovlar."""
    rows = con.execute("SELECT room_id, ts, count FROM occupancy WHERE ts>=? AND ts<?", (iso(since), iso(until))).fetchall()
    acc = defaultdict(list)
    for rid, ts, c in rows:
        t = dt.datetime.fromisoformat(ts); n = slot_at(t)
        if n and t.hour * 60 + t.minute - hm(SLOTS[n - 1][1]) >= 10:
            acc[(rid, t.date(), n)].append(c)
    return {k: sum(v) / len(v) for k, v in acc.items()}

def overview(con, ctx: Ctx, quiet=False):
    _need(ctx, "auditoriyalar bandligi", quiet)
    t = now(); rooms = _rooms(con); sc = _sched(con)
    show_teacher = ctx.role.key in ("rektor", "prorektor_oquv")
    gnames = {g["id"]: g["name"] for g in db.rows(con, "SELECT id, name FROM groups_")}
    tnames = {x["id"]: x["full_name"] for x in db.rows(con, "SELECT id, full_name FROM teachers")}
    # --- hozir ---
    n_now = slot_at(t); wd = t.weekday()
    live = []
    for r in rooms:
        les = sc["map"].get((r["id"], wd, n_now)) if n_now and wd < 6 else None
        cnt = r["last_count"] if r["status"] == "onlayn" else None
        stale = not r["last_seen"] or dt.datetime.fromisoformat(r["last_seen"]) < t - dt.timedelta(seconds=POLL_SEC * 3)
        if r["status"] != "onlayn" or stale: state = "offline"
        elif cnt > r["capacity"]: state = "over"
        elif les and cnt <= GHOST_MAX and n_now and t.hour * 60 + t.minute - hm(SLOTS[n_now - 1][1]) >= 15: state = "ghost"
        elif cnt >= BUSY_MIN: state = "busy"
        else: state = "free"
        live.append({"id": r["id"], "name": r["name"].split(" ·")[0], "building": r["building"], "capacity": r["capacity"], "kind": r["kind"],
                     "count": cnt, "state": state, "mode": r["mode"], "lesson": les and {"group": gnames.get(les["group_id"]), "subject": les["subject"]}})
    # --- 4 hafta ---
    until = dt.datetime.combine(t.date(), dt.time()); since = until - dt.timedelta(days=28)
    av = _slot_avgs(con, since, until)
    days = [since.date() + dt.timedelta(days=i) for i in range(28)]
    workdays = [d for d in days if d.weekday() < 6]
    by_room = []
    heat = [[[] for _ in SLOTS] for _ in DAYS]
    ghosts, overs = [], []
    for r in rooms:
        used = tot = 0; fill = []
        for d in workdays:
            for n, _, _ in SLOTS:
                a = av.get((r["id"], d, n))
                if a is None: continue
                tot += 1
                heat[d.weekday()][n - 1].append(min(1.0, a / r["capacity"]))
                if a >= BUSY_MIN: used += 1; fill.append(a / r["capacity"])
                les = sc["map"].get((r["id"], d.weekday(), n))
                if les and a <= GHOST_MAX and d >= (t.date() - dt.timedelta(days=14)):
                    ghosts.append({"date": d.isoformat(), "day": DAYS[d.weekday()], "slot": n, "room": r["name"].split(" ·")[0],
                                   "group": gnames.get(les["group_id"]), "subject": les["subject"], "avg": round(a, 1),
                                   "teacher": tnames.get(les["teacher_id"]) if show_teacher else None, "teacher_id": les["teacher_id"] if show_teacher else None})
                if a > r["capacity"] * 1.05:
                    overs.append({"date": d.isoformat(), "slot": n, "room": r["name"].split(" ·")[0], "avg": round(a), "capacity": r["capacity"]})
        sched_n = sum(1 for (rid, w, s) in sc["map"] if rid == r["id"])
        by_room.append({"id": r["id"], "name": r["name"].split(" ·")[0], "building": r["building"], "capacity": r["capacity"], "kind": r["kind"],
                        "util": round(100 * used / tot, 1) if tot else 0, "fill": round(100 * sum(fill) / len(fill), 1) if fill else 0,
                        "scheduled_per_week": sched_n})
    heatmap = [[round(100 * sum(c) / len(c), 1) if c else None for c in row] for row in heat]
    rep = defaultdict(int)
    for g in ghosts:
        if g["teacher_id"]: rep[g["teacher_id"]] += 1
    for g in ghosts: g["repeat"] = rep.get(g["teacher_id"], 0)
    ghosts.sort(key=lambda g: g["date"], reverse=True); ghosts.sort(key=lambda g: -g["repeat"])
    over_rooms = defaultdict(lambda: {"n": 0, "max": 0})
    for o in overs:
        x = over_rooms[(o["room"], o["capacity"])]; x["n"] += 1; x["max"] = max(x["max"], o["avg"])
    util_all = [x["util"] for x in by_room]
    low = sorted([x for x in by_room if x["util"] < 35], key=lambda x: x["util"])
    cams = db.rows(con, """SELECT c.id, c.mode, c.vendor, c.model, c.host, c.port, c.scheme, c.channel, c.status, c.last_seen, c.last_error, c.last_count,
                           c.caps, c.fail_count, c.ticket_id, c.events, c.ev_status, c.ev_last, r.name room, r.guard
                           FROM cameras c JOIN rooms r ON r.id=c.room_id ORDER BY r.name""")
    for c in cams:
        c["room"] = c["room"].split(" ·")[0]
        caps = json.loads(c.pop("caps") or "null")
        c["warnings"] = (caps or {}).get("warnings", []); c["probed"] = bool(caps)
    events = db.rows(con, """SELECT e.ts, e.kind, e.state, e.alert, e.note, e.count, r.name room FROM cam_events e JOIN rooms r ON r.id=e.room_id
                             WHERE e.ts>=? ORDER BY e.id DESC LIMIT 30""", (iso(t - dt.timedelta(days=7)),))
    for e in events: e["room"] = e["room"].split(" ·")[0]; e["label"] = HK.KIND_LABEL.get(e["kind"], e["kind"])
    return {
        "now": iso(t), "slot": n_now, "slot_label": f"{n_now}-para ({SLOTS[n_now-1][1]}–{SLOTS[n_now-1][2]})" if n_now else "tanaffus / dars vaqtidan tashqari",
        "live": live, "rooms": by_room, "heatmap": heatmap, "days": DAYS, "slots": [f"{n}-para" for n, _, _ in SLOTS],
        "kpi": {"rooms": len(rooms), "busy_now": sum(1 for x in live if x["state"] in ("busy", "over")),
                "util": round(sum(util_all) / len(util_all), 1) if util_all else 0,
                "fill": round(sum(x["fill"] for x in by_room if x["fill"]) / max(1, sum(1 for x in by_room if x["fill"])), 1),
                "ghosts": len(ghosts), "over_rooms": len(over_rooms), "low_rooms": len(low),
                "online": sum(1 for c in cams if c["status"] == "onlayn"), "real": sum(1 for c in cams if c["mode"] == "isapi")},
        "low": low[:10], "ghosts": ghosts[:25],
        "over": sorted([{"room": k[0], "capacity": k[1], **v} for k, v in over_rooms.items()], key=lambda x: -x["n"])[:10],
        "cameras": cams, "can_manage": ctx.role.key in ("rektor", "xojalik"), "show_teacher": show_teacher,
        "poll_sec": POLL_SEC, "events": events, "cred_store": SS.status(), "work_hours": WORK_HOURS,
    }

def room_day(con, ctx: Ctx, room_id: int, day: str | None = None):
    _need(ctx, "xona kunlik bandligi")
    r = db.one(con, "SELECT * FROM rooms WHERE id=?", (room_id,))
    if not r: raise HTTPException(404)
    d = dt.date.fromisoformat(day) if day else now().date()
    pts = db.rows(con, "SELECT ts, count FROM occupancy WHERE room_id=? AND ts>=? AND ts<? ORDER BY ts",
                  (room_id, d.isoformat(), (d + dt.timedelta(days=1)).isoformat()))
    sc = _sched(con); gnames = {g["id"]: g["name"] for g in db.rows(con, "SELECT id, name FROM groups_")}
    lessons = [{"slot": n, "from": a, "to": b, "group": gnames.get(sc["map"][(room_id, d.weekday(), n)]["group_id"]),
                "subject": sc["map"][(room_id, d.weekday(), n)]["subject"]} for n, a, b in SLOTS if (room_id, d.weekday(), n) in sc["map"]]
    return {"room": r["name"], "capacity": r["capacity"], "date": d.isoformat(), "points": pts, "lessons": lessons}

def alerts(con, ctx: Ctx):
    try:
        o = overview(con, ctx, quiet=True)
    except AccessDenied:
        return []
    out = []
    k = o["kpi"]
    rep = sorted({(g["teacher"], g["repeat"]) for g in o["ghosts"] if g.get("teacher") and g["repeat"] >= 3}, key=lambda x: -x[1])
    if rep:
        out.append({"level": "mid", "area": "Auditoriyalar", "text": f"Kamera: {rep[0][0]} darslarida xona 2 hafta ichida {rep[0][1]} marta bo'sh — darslar o'tganini tekshirish kerak"})
    if k["low_rooms"]:
        out.append({"level": "low", "area": "Auditoriyalar", "text": f"{k['low_rooms']} ta xona 4 haftada 35% dan kam band — o'rtacha bandlik {k['util']}%"})
    night = [e for e in o["events"] if e["alert"] and e["kind"] in ("hududga_kirish", "chiziq_kesish") and e["ts"] >= iso(now() - dt.timedelta(hours=24))]
    if night:
        out.append({"level": "high", "area": "Xavfsizlik", "text": f"{night[0]['room']}: {night[0]['note']} ({night[0]['ts'][11:16]}) — 24 soatda {len(night)} ta"})
    off = [c for c in o["cameras"] if c["mode"] == "isapi" and (c["fail_count"] or 0) >= OFFLINE_FAILS]
    if off:
        out.append({"level": "mid", "area": "Kameralar", "text": f"{len(off)} ta kamera javob bermayapti — Xizmat markazida nosozlik arizasi ochildi"})
    if o["over"]:
        x = o["over"][0]
        out.append({"level": "mid", "area": "Auditoriyalar", "text": f"{x['room']} ({x['capacity']} o'rin) 4 haftada {x['n']} marta sig'imdan oshgan (eng ko'p {x['max']} kishi)"})
    return out

# =====================================================================
# HTTP
# =====================================================================
@router.get("/api/spaces/overview")
def api_overview(request: Request):
    return overview(_con, _ctx(request))

@router.get("/api/spaces/room/{rid}")
def api_room(rid: int, request: Request, day: str = ""):
    try:
        return room_day(_con, _ctx(request), rid, day or None)
    except ValueError:
        raise HTTPException(400, "Sana formati noto'g'ri")

class CamIn(BaseModel):
    room_id: int
    mode: str = Field("isapi", pattern="^(isapi|sim)$")
    host: str = Field("", max_length=64, pattern=r"^[A-Za-z0-9.\-:\[\]]*$")
    channel: int = Field(1, ge=1, le=64)
    username: str = Field("", max_length=64)
    password: str = Field("", max_length=128)
    scheme: str = Field("http", pattern="^(http|https)$")
    port: int | None = Field(None, ge=1, le=65535)
    events: bool = False
    guard: bool = False

def _manage(ctx: Ctx, action, detail=""):
    rbac.require(_con, ctx, SPACES, action, detail)
    if ctx.role.key not in ("rektor", "xojalik"):
        raise AccessDenied("⛔ Kameralarni faqat xo'jalik bo'limi va rektor sozlaydi.")

@router.post("/api/spaces/cameras")
def api_cam_save(body: CamIn, request: Request):
    c = _ctx(request); _manage(c, "kamera sozlamasi", f"xona #{body.room_id} → {body.mode} {body.host}")
    if not db.one(_con, "SELECT id FROM rooms WHERE id=?", (body.room_id,)): raise HTTPException(404, "Xona topilmadi")
    if body.mode == "isapi" and not body.host: raise HTTPException(400, "Kamera IP manzili kerak")
    ex = db.one(_con, "SELECT * FROM cameras WHERE room_id=?", (body.room_id,))
    vendor = "Hikvision" if body.mode == "isapi" else "Simulyator"
    if ex:
        _con.execute("""UPDATE cameras SET mode=?, host=?, channel=?, username=?, password='', vendor=?, scheme=?, port=?, events=?,
                        status='kutilmoqda', last_error=NULL, fail_count=0, caps=NULL WHERE id=?""",
                     (body.mode, body.host, body.channel, body.username, vendor, body.scheme, body.port, int(body.events), ex["id"]))
        cid = ex["id"]
    else:
        cid = _con.execute("""INSERT INTO cameras(room_id,vendor,mode,host,channel,username,password,status,scheme,port,events)
                              VALUES(?,?,?,?,?,?,'','kutilmoqda',?,?,?)""",
                           (body.room_id, vendor, body.mode, body.host, body.channel, body.username, body.scheme, body.port, int(body.events))).lastrowid
    if body.password: SS.put(f"camera:{cid}", body.password)       # parol faqat maxfiy omborda
    _con.execute("UPDATE rooms SET guard=? WHERE id=?", (int(body.guard), body.room_id))
    _con.commit()
    return {"ok": True, "id": cid, "cred_store": SS.status()["mode"]}

@router.post("/api/spaces/cameras/{cid}/test")
async def api_cam_test(cid: int, request: Request):
    c = _ctx(request); _manage(c, "kamera ulanishini tekshirish", f"#{cid}")
    cam = db.one(_con, "SELECT * FROM cameras WHERE id=?", (cid,))
    if not cam: raise HTTPException(404)
    if cam["mode"] == "sim":
        return {"ok": True, "info": "Simulyator rejimi — haqiqiy kamera ulanmagan", "count": sim_count(_con, cam["room_id"], now())}
    try:
        caps = await cam_client(cam).probe(int(cam["channel"] or 1), OCC_PATH)
    except HK.IsapiError as e:
        return {"ok": False, "error": str(e)[:200]}
    try:
        n = await isapi_count(cam); cnt_err = None
    except HK.IsapiError as e:
        n, cnt_err = None, str(e)[:200]
    d = caps["device"]
    _con.execute("UPDATE cameras SET model=?, caps=? WHERE id=?", (d.get("model"), json.dumps(caps, ensure_ascii=False), cid))
    if cnt_err is None:   # tekshiruv muvaffaqiyatli — holat darhol yangilanadi (keyingi so'rovni kutmasdan)
        _con.execute("UPDATE cameras SET status='onlayn', last_seen=?, last_count=?, last_error=NULL, fail_count=0 WHERE id=?", (iso(now()), n, cid))
    _con.commit()
    return {"ok": cnt_err is None, "info": f"{d.get('model')} · proshivka {d.get('firmware')}", "count": n, "error": cnt_err,
            "caps": {k: caps[k] for k in ("counting", "region_counting", "events", "clock_skew_s")}, "warnings": caps["warnings"]}
