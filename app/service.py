"""Murojaatlar va nosozliklar (avval «Xizmat markazi») — "Offers" hujjatining 1-bosqich modullari:
  1) Xonadagi QR orqali nosozlik yuborish (xo'jalik va texnik bo'lim)
  2) Yagona murojaat kartasi: avtomatik tasniflash + bir xil nosozliklarni bitta hodisaga birlashtirish
  3) Tadbirga QR orqali qatnashuvni belgilash (ma'naviyat va yoshlar)

Tamoyil: tizim tasniflaydi va loyiha tayyorlaydi — qarorni mas'ul xodim qabul qiladi.
Ommaviy QR sahifalari (login'siz) faqat ma'lumot QABUL qiladi; hech qanday shaxsiy ma'lumot ko'rsatmaydi.
"""
import base64, binascii, datetime as dt, html, io, json, os, re, secrets, socket, time
from collections import defaultdict, deque
from pathlib import Path
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import HTMLResponse, FileResponse
from pydantic import BaseModel, Field
from . import db, rbac, brand, academic_rules as AR
from .rbac import Ctx, AccessDenied, FACILITIES, REQUESTS, YOUTH

router = APIRouter()
_con = None
_ctx = None
UPLOADS = db.DATA_DIR / "uploads"

SCHEMA = """
CREATE TABLE IF NOT EXISTS rooms(id INTEGER PRIMARY KEY, code TEXT UNIQUE, building TEXT, name TEXT, kind TEXT, equipment TEXT);
CREATE TABLE IF NOT EXISTS tickets(id INTEGER PRIMARY KEY, room_id INT, item TEXT, text TEXT, photo TEXT, reporter TEXT,
  created_at TEXT, status TEXT, reports INT DEFAULT 1, resolved_at TEXT, note TEXT);
CREATE TABLE IF NOT EXISTS incidents(id INTEGER PRIMARY KEY, topic TEXT, category TEXT, title TEXT, opened_at TEXT, status TEXT,
  notice TEXT, notified_at TEXT, resolved_at TEXT);
CREATE TABLE IF NOT EXISTS requests(id INTEGER PRIMARY KEY, created_at TEXT, channel TEXT, student_id INT, faculty_id INT, name TEXT,
  contact TEXT, text TEXT, category TEXT, topic TEXT, unit TEXT, incident_id INT, status TEXT, answer TEXT, resolved_at TEXT);
CREATE TABLE IF NOT EXISTS event_qr(event_id INTEGER PRIMARY KEY, code TEXT UNIQUE, open INT DEFAULT 0);
CREATE TABLE IF NOT EXISTS event_reg(event_id INT, student_id INT, PRIMARY KEY(event_id, student_id));
CREATE TABLE IF NOT EXISTS event_checkin(event_id INT, student_id INT, ts TEXT, PRIMARY KEY(event_id, student_id));
"""

def init(con):
    con.executescript(SCHEMA); con.commit()

def bind(con, ctx_fn):
    global _con, _ctx
    _con, _ctx = con, ctx_fn
    init(con)

def now(): return dt.datetime.now().replace(microsecond=0)
def iso(t): return t.isoformat(timespec="seconds")
def e(s): return html.escape(str(s or ""))

def mask(full):
    p = (full or "").split()
    return f"{p[0]} {p[1][0]}." if len(p) > 1 else (p[0] if p else "")

def _audit_public(con, action, resource, detail=""):
    con.execute("INSERT INTO audit_log(ts,user_id,user_name,role,channel,action,resource,allowed,detail) VALUES(?,?,?,?,?,?,?,?,?)",
                (iso(now()), 0, "Ommaviy QR", "—", "qr", action, resource, 1, detail[:300]))

def public_base(request: Request) -> str:
    """QR havolalari telefondan ochilishi uchun: localhost o'rniga kompyuterning lokal tarmoq (Wi-Fi) manzili."""
    env = os.getenv("ISFT_CORE_PUBLIC_URL")
    if env: return env.rstrip("/") + "/"
    host, port = request.url.hostname, request.url.port or 80
    if host in ("localhost", "127.0.0.1", "::1"):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); s.connect(("10.255.255.255", 1)); host = s.getsockname()[0]; s.close()
        except OSError:
            pass
    return f"http://{host}:{port}/"

# --- oddiy so'rov cheklovi (ommaviy sahifalar uchun spamdan himoya) ---
_hits: dict[str, deque] = defaultdict(deque)
def _limit(request: Request, n=15, window=600):
    ip = request.client.host if request.client else "?"
    q = _hits[(ip, request.url.path)]; t = time.time()
    while q and q[0] < t - window: q.popleft()
    if len(q) >= n: raise HTTPException(429, "Juda ko'p so'rov. Birozdan keyin urinib ko'ring.")
    q.append(t)

def _g(ctx: Ctx, res, action, detail=""):
    rbac.require(_con, ctx, res, action, detail)

# =====================================================================
# 1) NOSOZLIKLAR (QR)
# =====================================================================
EQUIP = {"auditoriya": ["Proyektor", "Kompyuter", "Mikrofon / ovoz", "Konditsioner / isitish", "Elektr / rozetka", "Chiroq", "Doska", "Mebel"],
         "kompyuter sinfi": ["Kompyuter", "Internet / Wi-Fi", "Proyektor", "Printer", "Konditsioner / isitish", "Elektr / rozetka", "Mebel"],
         "umumiy": ["Santexnika", "Elektr / rozetka", "Chiroq", "Eshik / qulf", "Isitish", "Tozalik"]}
TICKET_STATUSES = ["yangi", "jarayonda", "hal qilindi"]

def _photo_save(data_url: str | None) -> str | None:
    if not data_url: return None
    m = re.match(r"^data:image/(jpeg|png|webp);base64,(.+)$", data_url, re.S)
    if not m: raise HTTPException(400, "Rasm formati noto'g'ri")
    try: raw = base64.b64decode(m.group(2), validate=True)
    except binascii.Error: raise HTTPException(400, "Rasm buzilgan")
    if len(raw) > 2_500_000: raise HTTPException(413, "Rasm juda katta")
    from PIL import Image
    try:
        im = Image.open(io.BytesIO(raw)); im.verify(); im = Image.open(io.BytesIO(raw)).convert("RGB")
    except Exception:
        raise HTTPException(400, "Rasm o'qilmadi")
    im.thumbnail((1280, 1280))
    UPLOADS.mkdir(parents=True, exist_ok=True)
    name = secrets.token_hex(8) + ".jpg"
    im.save(UPLOADS / name, "JPEG", quality=82)  # qayta saqlash EXIF (joylashuv va h.k.) ni olib tashlaydi
    return name

def create_ticket(con, room_code, item, text, photo, reporter, channel="qr", when=None):
    room = db.one(con, "SELECT * FROM rooms WHERE code=?", (room_code,))
    if not room: raise HTTPException(404, "Xona topilmadi")
    items = json.loads(room["equipment"])
    if item not in items + ["Boshqa"]: item = "Boshqa"
    when = when or now()
    dup = db.one(con, "SELECT * FROM tickets WHERE room_id=? AND item=? AND status!='hal qilindi' ORDER BY id DESC LIMIT 1", (room["id"], item))
    if dup and item != "Boshqa":
        con.execute("UPDATE tickets SET reports=reports+1 WHERE id=?", (dup["id"],))
        con.commit()
        return {"duplicate": True, "id": dup["id"], "room": room["name"], "item": item, "reports": dup["reports"] + 1, "status": dup["status"]}
    cur = con.execute("INSERT INTO tickets(room_id,item,text,photo,reporter,created_at,status) VALUES(?,?,?,?,?,?,?)",
                      (room["id"], item, (text or "")[:600], photo, (reporter or "")[:80], iso(when), "yangi"))
    con.commit()
    return {"duplicate": False, "id": cur.lastrowid, "room": room["name"], "item": item}

def facilities(con, ctx: Ctx, quiet=False):
    if quiet:
        if not ctx.can(FACILITIES): raise AccessDenied("")
    else:
        _g(ctx, FACILITIES, "nosozliklar ro'yxati")
    t = db.rows(con, """SELECT t.*, r.name room, r.building, r.code room_code FROM tickets t JOIN rooms r ON r.id=t.room_id
                        ORDER BY CASE t.status WHEN 'yangi' THEN 0 WHEN 'jarayonda' THEN 1 ELSE 2 END, t.created_at DESC""")
    n = now()
    for x in t:
        end = dt.datetime.fromisoformat(x["resolved_at"]) if x["resolved_at"] else n
        x["hours"] = round((end - dt.datetime.fromisoformat(x["created_at"])).total_seconds() / 3600, 1)
        x["overdue"] = x["status"] != "hal qilindi" and x["hours"] > 24
    since = iso(n - dt.timedelta(days=60))
    repeat = db.rows(con, """SELECT r.name room, r.building, t.item, COUNT(*) n, SUM(t.reports) reports, MAX(t.created_at) last
                             FROM tickets t JOIN rooms r ON r.id=t.room_id WHERE t.created_at>=? AND t.item!='Boshqa'
                             GROUP BY t.room_id, t.item HAVING COUNT(*)>=3 ORDER BY n DESC""", (since,))
    done = [x for x in t if x["status"] == "hal qilindi" and x["created_at"] >= since]
    by_building = db.rows(con, """SELECT r.building, COUNT(*) n FROM tickets t JOIN rooms r ON r.id=t.room_id
                                  WHERE t.status!='hal qilindi' GROUP BY r.building ORDER BY r.building""")
    return {"tickets": t[:120], "open": sum(1 for x in t if x["status"] != "hal qilindi"),
            "overdue": sum(1 for x in t if x["overdue"]), "repeat": repeat, "by_building": by_building,
            "avg_hours": round(sum(x["hours"] for x in done) / len(done), 1) if done else None,
            "dup_saved": sum(max(0, (x["reports"] or 1) - 1) for x in t), "rooms": db.one(con, "SELECT COUNT(*) n FROM rooms")["n"]}

# =====================================================================
# 2) MUROJAATLAR: tasniflash va hodisaga birlashtirish
# =====================================================================
CATS = [  # (toifa, mas'ul bo'lim, kalit so'zlar)
    ("LMS / onlayn ta'lim", "Axborot texnologiyalari bo'limi", ["lms", "moodle", "platforma", "onlayn dars", "video dars", "kursga kir"]),
    # Registrator ofisi e'loni (07.09): baholar, akademik natijalar, hujjatlar, talaba maqomi, akademik ta'til, shartnoma hujjatlari
    ("HEMIS / baholar", "Registrator ofisi", ["hemis", "baho", "reyting", "ball", "qayta topshir", "apellyatsiya"]),
    ("Wi-Fi / internet", "Axborot texnologiyalari bo'limi", ["wifi", "wi-fi", "internet", "tarmoq"]),
    ("Pochta / akkaunt", "Axborot texnologiyalari bo'limi", ["pochta", "email", "e-mail", "parol", "login", "akkaunt"]),
    ("Hujjat / ma'lumotnoma", "Registrator ofisi", ["ma'lumotnoma", "malumotnoma", "spravka", "hujjat", "transkript", "diplom", "buyruq",
                                                     "arxiv", "bitiruv marosim", "maqom", "akademik ta'til", "shartnoma",
                                                     "talabalikdan", "qayta tiklash", "o'qishni ko'chir", "akademik natija"]),
    ("Sirtqi ta'lim", "Sirtqi bo'lim", ["sirtqi", "chaqiruv xat"]),
    # akademik qoidalar taqdimoti (app/academic_rules.py DUTIES): akademik taqvim, Enrollment, akademik guruhlar, nazorat jadvali
    ("Akademik taqvim / fanga yozilish", "Akademik faoliyatni boshqarish bo'limi",
     ["fanga yozil", "fanlarga yozil", "enrollment", "tanlov fan", "akademik taqvim", "akademik guruh", "imtihon jadval",
      "nazorat jadval", "yakuniy nazorat", "oraliq nazorat", "sessiya"]),
    ("To'lov / kontrakt", "Buxgalteriya bo'limi", ["to'lov", "tolov", "kontrakt", "chek", "click", "payme", "to'ladim", "toladim"]),
    ("Dars jadvali", "Akademik faoliyatni boshqarish bo'limi", ["jadval", "auditoriya", "dars vaqti", "dars qayer", "xona o'zgar"]),
    ("Turar joy (ijara)", "Ma'naviyat va ma'rifat bo'limi", ["ijara", "turar joy", "yotoqxona", "kvartira"]),
]
TOPICS = {"lms": ["lms", "moodle", "platforma"], "hemis": ["hemis"], "wifi": ["wifi", "wi-fi", "internet"],
          "pochta": ["pochta", "email", "e-mail"], "tolov_tizimi": ["click", "payme"]}
TOPIC_CAT = {"lms": "LMS / onlayn ta'lim", "hemis": "HEMIS / baholar", "wifi": "Wi-Fi / internet", "pochta": "Pochta / akkaunt",
             "tolov_tizimi": "To'lov / kontrakt"}
TOPIC_TITLE = {"lms": "LMS platformasiga kirishda uzilish", "hemis": "HEMIS tizimida nosozlik", "wifi": "Wi-Fi / internet uzilishi",
               "pochta": "Korporativ pochtaga kirish muammosi", "tolov_tizimi": "Onlayn to'lov tizimida nosozlik"}
FAIL = ["ochilmay", "kira olmay", "kirolmay", "kiraolmay", "ishlamay", "xato", "ko'rinmay", "korinmay", "o'tmay", "otmay",
        "uzil", "yuklanmay", "kirmayap", "ochmay", "error", "parol"]
INCIDENT_MIN = 3          # nechta bir xil murojaat bo'lsa — umumiy hodisa
INCIDENT_WINDOW_H = 6     # qaysi vaqt oralig'ida

def _norm(t):
    t = (t or "").lower().replace("ʻ", "'").replace("ʼ", "'").replace("‘", "'").replace("’", "'").replace("`", "'")
    return t

def classify(text):
    t = _norm(text)
    cat, unit = "Boshqa", "Registrator ofisi"
    best = 0
    for c, u, kws in CATS:
        s = sum(1 for k in kws if k in t)
        if s > best: best, cat, unit = s, c, u
    topic = None
    if any(f in t for f in FAIL):
        # hodisa mavzusi faqat murojaat toifasiga mos bo'lsa (masalan, "Click orqali to'ladim, HEMISda ko'rinmayapti" — HEMIS uzilishi emas)
        topic = next((k for k, kws in TOPICS.items() if TOPIC_CAT[k] == cat and any(w in t for w in kws)), None)
    # HEMIS'ning texnik nosozligi (kira olmayapti, ochilmayapti) — IT ishi; baho/natija mazmuni bo'yicha savollar — Registrator ofisida
    if topic == "hemis": unit = "Axborot texnologiyalari bo'limi"
    return cat, unit, topic

def create_request(con, text, name="", contact="", hemis_id="", channel="veb-forma", when=None):
    text = (text or "").strip()[:1500]
    if len(text) < 5: raise HTTPException(400, "Murojaat matni juda qisqa")
    st = db.one(con, "SELECT id, faculty_id, full_name FROM students WHERE hemis_id=?", ((hemis_id or "").strip(),)) if hemis_id else None
    cat, unit, topic = classify(text)
    when = when or now()
    cur = con.execute("""INSERT INTO requests(created_at,channel,student_id,faculty_id,name,contact,text,category,topic,unit,status)
                         VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                      (iso(when), channel, st and st["id"], st and st["faculty_id"], (name or (st and st["full_name"]) or "")[:80],
                       (contact or "")[:80], text, cat, topic, unit, "yangi"))
    rid = cur.lastrowid
    inc = _group_incident(con, topic, when) if topic else None
    con.commit()
    return {"id": rid, "number": f"M-{rid:04d}", "category": cat, "unit": unit, "incident": inc}

def _group_incident(con, topic, when):
    """Bir xil tizim nosozligi haqida qisqa vaqt ichida >= INCIDENT_MIN murojaat kelsa — bitta hodisa ochiladi."""
    open_inc = db.one(con, "SELECT * FROM incidents WHERE topic=? AND status!='hal qilindi' ORDER BY id DESC LIMIT 1", (topic,))
    since = iso(when - dt.timedelta(hours=INCIDENT_WINDOW_H))
    if open_inc:
        con.execute("UPDATE requests SET incident_id=? WHERE topic=? AND incident_id IS NULL AND created_at>=? AND status!='hal qilindi'",
                    (open_inc["id"], topic, open_inc["opened_at"][:10]))
        return open_inc["id"]
    loose = db.rows(con, "SELECT id, created_at FROM requests WHERE topic=? AND incident_id IS NULL AND created_at>=? AND created_at<=? AND status!='hal qilindi'",
                    (topic, since, iso(when)))
    if len(loose) < INCIDENT_MIN: return None
    cat = TOPIC_CAT[topic]
    cur = con.execute("INSERT INTO incidents(topic,category,title,opened_at,status) VALUES(?,?,?,?,?)",
                      (topic, cat, TOPIC_TITLE[topic], min(x["created_at"] for x in loose), "ochiq"))
    con.execute(f"UPDATE requests SET incident_id=? WHERE id IN ({','.join(str(x['id']) for x in loose)})", (cur.lastrowid,))
    return cur.lastrowid

def _req_scope(ctx: Ctx):
    return f"faculty_id={int(ctx.user['faculty_id'])}" if ctx.role.scope == "fakultet" else "1=1"

def requests_overview(con, ctx: Ctx, quiet=False):
    if quiet:
        if not ctx.can(REQUESTS): raise AccessDenied("")
    else:
        _g(ctx, REQUESTS, "murojaatlar ro'yxati")
    w = _req_scope(ctx)
    reqs = db.rows(con, f"SELECT * FROM requests WHERE {w} ORDER BY created_at DESC LIMIT 300")
    incs = db.rows(con, f"""SELECT i.*, (SELECT COUNT(*) FROM requests r WHERE r.incident_id=i.id AND {w}) n,
                            (SELECT MAX(created_at) FROM requests r WHERE r.incident_id=i.id) last
                            FROM incidents i ORDER BY CASE i.status WHEN 'ochiq' THEN 0 ELSE 1 END, i.opened_at DESC""")
    incs = [i for i in incs if i["n"]]
    since = iso(now() - dt.timedelta(days=30))
    by_cat = db.rows(con, f"SELECT category, COUNT(*) n, SUM(status!='hal qilindi' AND status!='javob berildi') open FROM requests WHERE {w} AND created_at>=? GROUP BY category ORDER BY n DESC", (since,))
    single_open = [r for r in reqs if r["status"] in ("yangi", "jarayonda") and not r["incident_id"]]
    for r in reqs: r["number"] = f"M-{r['id']:04d}"
    return {"incidents": incs, "requests": reqs, "by_cat": by_cat, "open_single": len(single_open), "can_broadcast": ctx.role.scope != "fakultet",
            "open_total": sum(1 for r in reqs if r["status"] in ("yangi", "jarayonda")),
            "grouped": sum(1 for r in reqs if r["incident_id"]), "scope": ctx.scope_label(con)}

def notice_template(inc, n):
    return (f"Hurmatli talabalar! {inc['title']} bo'yicha {n} ta murojaat qabul qilindi. "
            f"Muammo umumiy bo'lib, Axborot texnologiyalari bo'limi tomonidan bartaraf etilmoqda. Har biringiz alohida murojaat yuborishingiz shart emas — "
            f"tizim tiklangach shu kanal orqali xabar beramiz. Shoshilinch holatda: Registrator ofisiga murojaat qiling.")

# =====================================================================
# 3) TADBIRLAR: QR orqali qatnashuv
# =====================================================================
def event_code(con, eid):
    r = db.one(con, "SELECT code FROM event_qr WHERE event_id=?", (eid,))
    if r: return r["code"]
    c = secrets.token_hex(4)
    con.execute("INSERT INTO event_qr(event_id,code,open) VALUES(?,?,0)", (eid, c)); con.commit()
    return c

def events_overview(con, ctx: Ctx, quiet=False):
    if quiet:
        if not ctx.can(YOUTH): raise AccessDenied("")
    else:
        _g(ctx, YOUTH, "tadbirlar qatnashuvi")
    ev = db.rows(con, """SELECT e.*, q.code, COALESCE(q.open,0) open,
                         (SELECT COUNT(*) FROM event_reg r WHERE r.event_id=e.id) reg,
                         (SELECT COUNT(*) FROM event_checkin c WHERE c.event_id=e.id) came,
                         (SELECT COUNT(*) FROM event_checkin c WHERE c.event_id=e.id AND c.student_id IN (SELECT student_id FROM event_reg r WHERE r.event_id=e.id)) came_reg
                         FROM events e LEFT JOIN event_qr q ON q.event_id=e.id ORDER BY e.date DESC""")
    for x in ev:
        x["pct"] = round(100 * x["came_reg"] / x["reg"], 1) if x["reg"] else None
        x["walkin"] = x["came"] - x["came_reg"]
    by_fac = db.rows(con, """SELECT f.name faculty, COUNT(DISTINCT s.id) students,
                             COUNT(DISTINCT c.student_id) reached FROM students s JOIN faculties f ON f.id=s.faculty_id
                             LEFT JOIN event_checkin c ON c.student_id=s.id GROUP BY f.id ORDER BY f.id""")
    for f in by_fac: f["pct"] = round(100 * f["reached"] / f["students"], 1)
    unreached = db.rows(con, """SELECT g.name grp, f.name faculty, COUNT(s.id) n FROM groups_ g JOIN faculties f ON f.id=g.faculty_id
                                JOIN students s ON s.group_id=g.id
                                WHERE g.id NOT IN (SELECT DISTINCT s2.group_id FROM event_checkin c JOIN students s2 ON s2.id=c.student_id)
                                GROUP BY g.id ORDER BY g.name""")
    regulars = db.one(con, "SELECT COUNT(*) n FROM (SELECT student_id FROM event_checkin GROUP BY student_id HAVING COUNT(*)>=3)")["n"]
    past = [x for x in ev if x["reg"] and x["came"]]
    return {"events": ev, "by_faculty": by_fac, "unreached": unreached, "regulars": regulars,
            "avg_pct": round(sum(x["pct"] for x in past) / len(past), 1) if past else None}

def checkin(con, code, hemis_id, when=None):
    q = db.one(con, "SELECT q.*, e.title FROM event_qr q JOIN events e ON e.id=q.event_id WHERE q.code=?", (code,))
    if not q: raise HTTPException(404, "Tadbir topilmadi")
    if not q["open"]: raise HTTPException(409, "Ro'yxatga olish hozir yopiq. Tashkilotchiga murojaat qiling.")
    st = db.one(con, "SELECT id, full_name FROM students WHERE hemis_id=?", ((hemis_id or "").strip(),))
    if not st: raise HTTPException(404, "Bu HEMIS ID topilmadi. Raqamni tekshiring.")
    ex = db.one(con, "SELECT ts FROM event_checkin WHERE event_id=? AND student_id=?", (q["event_id"], st["id"]))
    if ex: return {"ok": True, "again": True, "name": mask(st["full_name"]), "title": q["title"]}
    con.execute("INSERT INTO event_checkin(event_id,student_id,ts) VALUES(?,?,?)", (q["event_id"], st["id"], iso(when or now())))
    reg = db.one(con, "SELECT 1 x FROM event_reg WHERE event_id=? AND student_id=?", (q["event_id"], st["id"]))
    con.commit()
    return {"ok": True, "again": False, "name": mask(st["full_name"]), "title": q["title"], "registered": bool(reg)}

# =====================================================================
# Rahbariyat paneli uchun ogohlantirishlar
# =====================================================================
def alerts(con, ctx: Ctx):
    out = []
    try:
        r = requests_overview(con, ctx, quiet=True)
        for i in r["incidents"]:
            if i["status"] == "ochiq":
                out.append({"level": "high", "area": "Murojaatlar", "text": f"{i['title']}: {i['n']} ta murojaat bitta hodisaga birlashtirildi" + ("" if i["notified_at"] else " — talabalarga hali xabar berilmagan")})
    except AccessDenied: pass
    try:
        f = facilities(con, ctx, quiet=True)
        if f["repeat"]:
            x = f["repeat"][0]
            out.append({"level": "mid", "area": "Xo'jalik", "text": f"{x['room']}: «{x['item']}» 60 kunda {x['n']} marta buzilgan — almashtirish masalasi"})
        if f["overdue"]:
            out.append({"level": "mid", "area": "Xo'jalik", "text": f"{f['overdue']} ta nosozlik 24 soatdan beri hal qilinmagan"})
    except AccessDenied: pass
    try:
        ev = events_overview(con, ctx, quiet=True)
        if ev["unreached"]:
            out.append({"level": "low", "area": "Tadbirlar", "text": f"{len(ev['unreached'])} ta guruh bu semestr birorta tadbirga qatnashmagan"})
    except AccessDenied: pass
    return out

# =====================================================================
# HTTP: xodimlar uchun API
# =====================================================================
def C(request: Request) -> Ctx: return _ctx(request)

@router.get("/api/svc/overview")
def overview(request: Request):
    c = C(request); out = {"tabs": []}
    for key, fn, res in (("facilities", facilities, FACILITIES), ("requests", requests_overview, REQUESTS), ("events", events_overview, YOUTH)):
        if c.can(res):
            out[key] = fn(_con, c); out["tabs"].append(key)
    if not out["tabs"]:
        rbac.audit(_con, c, "murojaatlar va nosozliklar", FACILITIES, False)
    out["base"] = public_base(request)
    return out

class TStatus(BaseModel):
    status: str
    note: str = ""

@router.post("/api/svc/tickets/{tid}/status")
def ticket_status(tid: int, body: TStatus, request: Request):
    c = C(request); _g(c, FACILITIES, "nosozlik holatini o'zgartirish", f"#{tid} → {body.status}")
    if body.status not in TICKET_STATUSES: raise HTTPException(400)
    _con.execute("UPDATE tickets SET status=?, note=COALESCE(NULLIF(?,''),note), resolved_at=? WHERE id=?",
                 (body.status, body.note[:300], iso(now()) if body.status == "hal qilindi" else None, tid))
    _con.commit(); return {"ok": True}

@router.get("/api/svc/photo/{name}")
def photo(name: str, request: Request):
    c = C(request); _g(c, FACILITIES, "nosozlik rasmini ko'rish", name)
    if not re.fullmatch(r"[0-9a-f]{16}\.jpg", name): raise HTTPException(404)
    p = UPLOADS / name
    if not p.exists(): raise HTTPException(404)
    return FileResponse(p, media_type="image/jpeg")

@router.get("/svc/qr-sheet", response_class=HTMLResponse)
def qr_sheet(request: Request, building: str = ""):
    c = C(request); _g(c, FACILITIES, "xona QR stikerlarini chop etish", building)
    base = public_base(request)
    rooms = db.rows(_con, "SELECT * FROM rooms WHERE (?='' OR building=?) ORDER BY building, name", (building, building))
    cards = "".join(f"""<div class="st"><div class="hd"><img src="/brand/logo-sm.png" alt=""><b>ISFT · Nosozlik haqida xabar</b></div>
        <img class="qr" src="data:image/png;base64,{base64.b64encode(brand.qr_png(base + 'q/' + r['code']).getvalue()).decode()}" alt="QR">
        <div class="rm">{e(r['name'])}</div><div class="hint">Telefon kamerasi bilan skanerlang → muammoni tanlang → yuboring.<br>Ro'yxatdan o'tish shart emas.</div></div>""" for r in rooms)
    return f"""<!doctype html><html lang="uz"><head><meta charset="utf-8"><title>Xona QR stikerlari — ISFT</title><link rel="stylesheet" href="/fonts/manrope.css"><style>
    body{{font:13px Manrope,-apple-system,Segoe UI,Roboto,sans-serif;margin:16px;color:#0D0D0D}}.bar{{margin-bottom:12px}}
    .g{{display:grid;grid-template-columns:repeat(3,1fr);gap:10px}}.st{{border:2px solid #870037;border-radius:14px;padding:10px;text-align:center;break-inside:avoid}}
    .hd{{display:flex;gap:6px;align-items:center;justify-content:center;color:#870037;font-size:11.5px}}.hd img{{height:22px}}
    .qr{{width:150px;height:150px}}.rm{{font-size:17px;font-weight:800;color:#870037}}.hint{{font-size:10.5px;color:#555;margin-top:4px}}
    @media print{{.bar{{display:none}}body{{margin:0}}}}</style></head><body>
    <div class="bar"><button onclick="print()">🖨 Chop etish</button> · {len(rooms)} ta xona · QR manzil: {e(base)}</div><div class="g">{cards}</div></body></html>"""

class RStatus(BaseModel):
    status: str
    answer: str = ""

@router.post("/api/svc/requests/{rid}/status")
def request_status(rid: int, body: RStatus, request: Request):
    c = C(request); _g(c, REQUESTS, "murojaat holatini o'zgartirish", f"M-{rid:04d} → {body.status}")
    r = db.one(_con, f"SELECT id FROM requests WHERE id=? AND {_req_scope(c)}", (rid,))
    if not r: raise HTTPException(404)
    if body.status not in ("yangi", "jarayonda", "javob berildi", "hal qilindi"): raise HTTPException(400)
    _con.execute("UPDATE requests SET status=?, answer=COALESCE(NULLIF(?,''),answer), resolved_at=? WHERE id=?",
                 (body.status, body.answer[:1000], iso(now()) if body.status == "hal qilindi" else None, rid))
    _con.commit(); return {"ok": True}

def _incident_guard(c: Ctx):
    # hodisa butun institut bo'yicha — umumiy xabarni fakultet emas, talabalar bo'limi / rahbariyat yuboradi
    if c.role.scope == "fakultet":
        raise AccessDenied("⛔ Umumiy hodisa bo'yicha xabarni talabalar bo'limi yoki rahbariyat yuboradi.")

@router.post("/api/svc/incidents/{iid}/draft")
async def incident_draft(iid: int, request: Request, ai_: int = 0):
    c = C(request); _g(c, REQUESTS, "hodisa xabari loyihasi", f"#{iid}"); _incident_guard(c)
    inc = db.one(_con, "SELECT * FROM incidents WHERE id=?", (iid,))
    if not inc: raise HTTPException(404)
    n = db.one(_con, "SELECT COUNT(*) n FROM requests WHERE incident_id=?", (iid,))["n"]
    text = notice_template(inc, n)
    if ai_:
        from . import ai
        sample = [r["text"] for r in db.rows(_con, "SELECT text FROM requests WHERE incident_id=? ORDER BY created_at DESC LIMIT 6", (iid,))]
        try:
            text = (await ai.llm_once([
                {"role": "system", "content": "Sen ISFT institutining rasmiy xabar yozuvchisisan. Faqat o'zbek (lotin) tilida, 3-4 gapda, xotirjam va aniq ohangda yoz. Sabab yoki muddatni o'ylab topma — noma'lum bo'lsa 'aniqlanmoqda' de. Shaxsiy ism yozma."},
                {"role": "user", "content": f"Hodisa: {inc['title']}. Murojaatlar soni: {n}. Namuna xabarlar: {json.dumps(sample, ensure_ascii=False)}\nTalabalarga umumiy holat xabari loyihasini yoz: muammo tan olinadi, alohida murojaat shart emasligi, tiklangach xabar berilishi."}],
                max_tokens=260)).strip() or text
        except Exception:
            pass
    return {"text": text, "n": n}

class Notice(BaseModel):
    text: str = Field(..., max_length=1500)

@router.post("/api/svc/incidents/{iid}/notify")
def incident_notify(iid: int, body: Notice, request: Request):
    c = C(request); _g(c, REQUESTS, "hodisa bo'yicha umumiy xabar yuborish", f"#{iid}"); _incident_guard(c)
    return {"ok": True, "answered": notify_incident(_con, iid, body.text)}

def notify_incident(con, iid, text) -> int:
    """Hodisa bo'yicha umumiy xabar: hodisaga yoziladi, ochiq murojaatlarga javob sifatida qo'yiladi (majlis qarori oqimi ham ishlatadi)."""
    con.execute("UPDATE incidents SET notice=?, notified_at=? WHERE id=?", (text, iso(now()), iid))
    cur = con.execute("UPDATE requests SET status='javob berildi', answer=? WHERE incident_id=? AND status IN ('yangi','jarayonda')", (text, iid))
    con.commit(); return cur.rowcount

@router.post("/api/svc/incidents/{iid}/resolve")
def incident_resolve(iid: int, request: Request):
    c = C(request); _g(c, REQUESTS, "hodisani yopish", f"#{iid}"); _incident_guard(c)
    t = iso(now())
    _con.execute("UPDATE incidents SET status='hal qilindi', resolved_at=? WHERE id=?", (t, iid))
    cur = _con.execute("UPDATE requests SET status='hal qilindi', resolved_at=? WHERE incident_id=? AND status!='hal qilindi'", (t, iid))
    _con.commit(); return {"ok": True, "closed": cur.rowcount}

@router.post("/api/svc/events/{eid}/{action}")
def event_toggle(eid: int, action: str, request: Request):
    c = C(request); _g(c, YOUTH, f"tadbir ro'yxatini {'ochish' if action == 'open' else 'yopish'}", f"#{eid}")
    if action not in ("open", "close"): raise HTTPException(400)
    event_code(_con, eid)
    _con.execute("UPDATE event_qr SET open=? WHERE event_id=?", (1 if action == "open" else 0, eid)); _con.commit()
    return {"ok": True}

@router.get("/api/svc/events/{eid}/live")
def event_live(eid: int, request: Request):
    c = C(request)
    if not c.can(YOUTH): raise AccessDenied("⛔ Ruxsat yo'q")
    last = db.rows(_con, """SELECT s.full_name, g.name grp, c.ts FROM event_checkin c JOIN students s ON s.id=c.student_id
                            JOIN groups_ g ON g.id=s.group_id WHERE c.event_id=? ORDER BY c.ts DESC LIMIT 6""", (eid,))
    for x in last: x["full_name"] = mask(x["full_name"])
    n = db.one(_con, "SELECT COUNT(*) n FROM event_checkin WHERE event_id=?", (eid,))["n"]
    reg = db.one(_con, "SELECT COUNT(*) n FROM event_reg WHERE event_id=?", (eid,))["n"]
    return {"n": n, "reg": reg, "last": last}

@router.get("/svc/event-screen/{eid}", response_class=HTMLResponse)
def event_screen(eid: int, request: Request):
    c = C(request); _g(c, YOUTH, "tadbir QR ekranini ochish", f"#{eid}")
    ev = db.one(_con, "SELECT * FROM events WHERE id=?", (eid,))
    if not ev: raise HTTPException(404)
    url = public_base(request) + "t/" + event_code(_con, eid)
    qr = base64.b64encode(brand.qr_png(url).getvalue()).decode()
    return f"""<!doctype html><html lang="uz"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
    <title>{e(ev['title'])} — qatnashuv</title><link rel="stylesheet" href="/style.css"><style>
    .scr{{min-height:100vh;display:grid;place-items:center;padding:24px}}.box{{max-width:980px;width:100%;display:grid;grid-template-columns:1fr 1fr;gap:28px;align-items:center}}
    .qrw{{background:#fff;border-radius:28px;padding:22px;text-align:center}}.qrw img{{width:100%;max-width:380px}}
    .big{{font-size:72px;font-weight:800;line-height:1;color:var(--accent)}}h1{{font-size:28px;margin:6px 0 14px}}
    .ls div{{padding:8px 12px;border-radius:12px;margin:6px 0;background:var(--surface-2)}}
    @media(max-width:760px){{.box{{grid-template-columns:1fr}}}}</style></head><body><div class="scr"><div class="box">
    <div class="qrw card"><img src="data:image/png;base64,{qr}" alt="QR"><div class="muted tiny">{e(url)}</div></div>
    <div class="card"><div class="brand"><img class="logo" src="/brand/logo-sm.png" alt=""><div><b>ISFT</b><small>Tadbirga qatnashuvni belgilash</small></div></div>
    <h1>{e(ev['title'])}</h1><p class="muted">Kamerani QR'ga qarating → HEMIS ID'ingizni kiriting → tayyor.</p>
    <div class="big" id="n">0</div><div class="muted" id="reg">kishi belgilandi</div><div class="ls" id="ls"></div></div></div></div>
    <script>async function t(){{try{{const j=await (await fetch('/api/svc/events/{eid}/live')).json();document.getElementById('n').textContent=j.n;
    document.getElementById('reg').textContent='kishi belgilandi · ro\\'yxatdan o\\'tgan: '+j.reg;
    document.getElementById('ls').innerHTML=j.last.map(x=>'<div>✅ '+x.full_name.replace(/[<>&]/g,'')+' <span class=muted>· '+x.grp.replace(/[<>&]/g,'')+'</span></div>').join('')}}catch(e){{}}}}
    t();setInterval(t,3000)</script></body></html>"""

# =====================================================================
# HTTP: ommaviy (login'siz) QR sahifalari
# =====================================================================
def _page(title, body, script=""):
    return f"""<!doctype html><html lang="uz"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="theme-color" content="#870037"><title>{e(title)} — ISFT</title><link rel="icon" href="/brand/favicon.png"><link rel="stylesheet" href="/style.css">
<style>.pub{{min-height:100vh;background:linear-gradient(#870037 0 210px,var(--bg-solid) 210px);display:grid;place-items:start center;padding:18px 16px 40px}}.pc{{width:min(520px,100%)}}
.pc .head{{display:flex;gap:12px;align-items:center;justify-content:flex-start;margin-bottom:14px}}
.pc input:not([type=file]){{padding:12px 14px;border:1px solid var(--line-2);border-radius:12px;background:var(--surface);color:var(--ink);font:inherit}}
.pc input[type=file]{{font-size:14px;color:var(--muted)}}.pc .head img{{width:62px;height:48px;object-fit:contain}}
.pc label{{display:flex;flex-direction:column;gap:5px;font-size:13px;font-weight:600;color:var(--muted);margin:12px 0}}
.pc input,.pc select,.pc textarea{{width:100%;flex:none;font-size:16px}}.pc textarea{{min-height:110px}}
.chips{{display:flex;flex-wrap:wrap;gap:8px}}.chips button{{font-size:14px}}.chips button.on{{background:var(--brand);border-color:var(--brand);color:#fff}}
.ok{{text-align:center;padding:10px 0}}.ok .i{{font-size:52px}}.err{{color:var(--bad);font-weight:600;margin-top:8px}}
.prev{{max-width:100%;border-radius:14px;margin-top:8px}}</style></head>
<body><div class="pub"><div class="pc card"><div class="head"><img src="/brand/logo-sm.png" alt="ISFT"><div><b style="color:var(--accent)">ISFT instituti</b><div class="muted tiny">{e(title)}</div></div></div>{body}</div></div>
<script>const $=s=>document.querySelector(s);async function post(u,b){{const r=await fetch(u,{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify(b)}});
const j=await r.json().catch(()=>({{}}));if(!r.ok)throw new Error(j.detail||'Xatolik');return j}}
const E=s=>String(s??'').replace(/[&<>"']/g,c=>({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[c]));{script}</script></body></html>"""

@router.get("/q/{code}", response_class=HTMLResponse)
def public_room(code: str):
    room = db.one(_con, "SELECT * FROM rooms WHERE code=?", (code,))
    if not room:
        return HTMLResponse(_page("Xona topilmadi", "<p>Bu QR kod eskirgan yoki noto'g'ri. Xo'jalik bo'limiga xabar bering.</p>"), status_code=404)
    items = json.loads(room["equipment"]) + ["Boshqa"]
    chips = "".join(f'<button type="button" class="btn" data-i="{e(i)}">{e(i)}</button>' for i in items)
    body = f"""<div id="f"><h2 style="margin:0">{e(room['name'])}</h2><p class="muted" style="margin:4px 0 0">Nima ishlamayapti? Xona avtomatik aniqlandi.</p>
    <label>Muammo turi<div class="chips" id="chips">{chips}</div></label>
    <label>Qisqacha izoh (ixtiyoriy)<textarea id="t" maxlength="600" placeholder="Masalan: proyektor yoqilmayapti, chiroq yonib-o'chyapti"></textarea></label>
    <label>Rasm (ixtiyoriy)<input type="file" id="p" accept="image/*" capture="environment"><img id="pv" class="prev" hidden></label>
    <label>Ismingiz yoki guruh (ixtiyoriy)<input id="w" maxlength="80"></label>
    <button class="btn primary" id="s" style="width:100%;padding:13px" disabled>Yuborish</button><div class="err" id="er"></div></div>"""
    script = f"""let item=null,photo=null;document.querySelectorAll('#chips button').forEach(b=>b.onclick=()=>{{document.querySelectorAll('#chips button').forEach(x=>x.classList.remove('on'));b.classList.add('on');item=b.dataset.i;$('#s').disabled=false}});
    $('#p').onchange=async e=>{{const f=e.target.files[0];if(!f)return;const img=new Image();img.src=URL.createObjectURL(f);await img.decode();
    const k=Math.min(1,1280/Math.max(img.width,img.height)),c=document.createElement('canvas');c.width=img.width*k;c.height=img.height*k;c.getContext('2d').drawImage(img,0,0,c.width,c.height);
    photo=c.toDataURL('image/jpeg',.8);$('#pv').src=photo;$('#pv').hidden=false}};
    $('#s').onclick=async()=>{{$('#s').disabled=true;$('#er').textContent='';try{{const j=await post('/api/public/ticket',{{code:'{e(code)}',item,text:$('#t').value,photo,reporter:$('#w').value}});
    $('#f').innerHTML=j.duplicate?`<div class="ok"><div class="i">👌</div><h2>Rahmat! Bu muammo allaqachon qayd etilgan</h2><p class="muted">${{E(j.room)}} · ${{E(j.item)}} — mas'ul xodim xabardor (holat: ${{E(j.status)}}). Sizning xabaringiz tasdiq sifatida qo'shildi: jami ${{j.reports}} ta.</p></div>`
    :`<div class="ok"><div class="i">✅</div><h2>Qabul qilindi — №${{j.id}}</h2><p class="muted">${{E(j.room)}} · ${{E(j.item)}}. Xo'jalik va texnik bo'limiga yuborildi.</p></div>`}}catch(err){{$('#er').textContent=err.message;$('#s').disabled=false}}}}"""
    return _page("Nosozlik haqida xabar", body, script)

class PubTicket(BaseModel):
    code: str = Field(..., max_length=32)
    item: str = Field("Boshqa", max_length=60)
    text: str = Field("", max_length=600)
    photo: str | None = Field(None, max_length=3_500_000)
    reporter: str = Field("", max_length=80)

@router.post("/api/public/ticket")
def public_ticket(body: PubTicket, request: Request):
    _limit(request)
    ph = _photo_save(body.photo)
    r = create_ticket(_con, body.code, body.item, body.text, ph, body.reporter)
    _audit_public(_con, "QR orqali nosozlik" + (" (takror)" if r["duplicate"] else ""), "facilities", f"{r['room']} · {r['item']}"); _con.commit()
    return r

@router.get("/m", response_class=HTMLResponse)
def public_request_page():
    body = """<div id="f"><h2 style="margin:0">Murojaat yuborish</h2><p class="muted" style="margin:4px 0 0">Muammoingizni o'z so'zlaringiz bilan yozing — tizim uni kerakli bo'limga yo'naltiradi.</p>
    <label>Murojaat matni<textarea id="t" maxlength="1500" placeholder="Masalan: LMS ga kira olmayapman, parol xato deyapti"></textarea></label>
    <label>HEMIS ID (ixtiyoriy — javob tezroq bo'ladi)<input id="h" inputmode="numeric" maxlength="20"></label>
    <label>Telefon yoki Telegram (ixtiyoriy)<input id="c" maxlength="80"></label>
    <button class="btn primary" id="s" style="width:100%;padding:13px">Yuborish</button><div class="err" id="er"></div></div>"""
    script = """$('#s').onclick=async()=>{$('#s').disabled=true;$('#er').textContent='';try{const j=await post('/api/public/request',{text:$('#t').value,hemis_id:$('#h').value,contact:$('#c').value});
    $('#f').innerHTML=`<div class="ok"><div class="i">📨</div><h2>Qabul qilindi — ${E(j.number)}</h2><p class="muted">Yo'nalish: <b>${E(j.unit)}</b> (${E(j.category)}).${j.room?'<br>Shaxsan murojaat uchun: '+E(j.room)+'.':''}${j.incident?'<br>Bu muammo bo\\'yicha boshqa talabalar ham yozgan — umumiy hodisa sifatida ko\\'rilmoqda, alohida qayta yozish shart emas.':''}</p></div>`}catch(err){$('#er').textContent=err.message;$('#s').disabled=false}}"""
    return _page("Yagona murojaat oynasi", body, script)

class PubRequest(BaseModel):
    text: str = Field(..., max_length=1500)
    hemis_id: str = Field("", max_length=20)
    contact: str = Field("", max_length=80)

@router.post("/api/public/request")
def public_request(body: PubRequest, request: Request):
    _limit(request)
    r = create_request(_con, body.text, contact=body.contact, hemis_id=body.hemis_id)
    _audit_public(_con, "murojaat qabul qilindi", "requests", f"{r['number']} · {r['category']}"); _con.commit()
    out = {k: r[k] for k in ("number", "category", "unit", "incident")}
    if r["unit"] == AR.REGISTRAR_UNIT: out["room"] = AR.REGISTRAR_ROOMS_TEXT   # Registrator ofisi e'loni (07.09)
    return out

@router.get("/t/{code}", response_class=HTMLResponse)
def public_event(code: str):
    q = db.one(_con, "SELECT q.*, e.title, e.date FROM event_qr q JOIN events e ON e.id=q.event_id WHERE q.code=?", (code,))
    if not q:
        return HTMLResponse(_page("Tadbir topilmadi", "<p>QR kod noto'g'ri yoki eskirgan.</p>"), status_code=404)
    body = f"""<div id="f"><h2 style="margin:0">{e(q['title'])}</h2><p class="muted" style="margin:4px 0 0">{e(q['date'])} · qatnashuvni belgilash</p>
    {'' if q['open'] else '<p class="err">Ro`yxatga olish hozir yopiq.</p>'}
    <label>HEMIS ID<input id="h" inputmode="numeric" maxlength="20" placeholder="Talaba guvohnomangizdagi raqam" autofocus></label>
    <button class="btn primary" id="s" style="width:100%;padding:13px">Men keldim ✋</button><div class="err" id="er"></div></div>"""
    script = f"""$('#s').onclick=async()=>{{$('#s').disabled=true;$('#er').textContent='';try{{const j=await post('/api/public/checkin',{{code:'{e(code)}',hemis_id:$('#h').value}});
    $('#f').innerHTML=`<div class="ok"><div class="i">${{j.again?'👍':'🎉'}}</div><h2>${{j.again?'Siz allaqachon belgilangansiz':'Belgilandi!'}}</h2><p class="muted">${{E(j.name)}} · ${{E(j.title)}}</p></div>`}}catch(err){{$('#er').textContent=err.message;$('#s').disabled=false}}}};
    $('#h').onkeydown=ev=>{{if(ev.key==='Enter')$('#s').click()}}"""
    return _page("Tadbirga qatnashuv", body, script)

class PubCheckin(BaseModel):
    code: str = Field(..., max_length=32)
    hemis_id: str = Field(..., max_length=20)

@router.post("/api/public/checkin")
def public_checkin(body: PubCheckin, request: Request):
    _limit(request, n=40, window=300)   # bir telefondan bir nechta talaba belgilashi mumkin (masalan, guruh sardori)
    r = checkin(_con, body.code, body.hemis_id)
    _audit_public(_con, "tadbirga qatnashuv belgilandi", "youth", r["title"]); _con.commit()
    return r
