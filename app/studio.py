"""«Studiya» — dars ishlab chiqarish oqimi (Masofaviy ta'lim bo'limi): ma'ruza → syomka bandi → syomka → AI montaj → operator ko'rigi →
YouTube → avtomatik paket → tasdiq → NEXTID. docs/studio.md

Bugungi qo'lda ish: o'qituvchi ma'ruza tayyorlaydi → studiyada syomka → montajni qo'lda qiladi → materiallar bo'limga yuboriladi → bo'lim
videoni YouTube'ga yuklab havolani ko'chiradi → Articulate'da xAPI paket yig'adi. Shu modul hammasini bitta oqimga bog'laydi:

  * Bosqichlar (STAGES) — har dars uchun: iloji boricha mavjud ma'lumotdan HISOBLANADI (paket manbalari, paketlar, tasdiqlar, studiya yozuvlari),
    hisoblab bo'lmaydigani saqlanadi (syomka bandi va «syomka qilindi», xom video, montaj vazifasi, YouTube navbati, «NEXTID'ga yuklandi»).
    Har bosqichning egasi (lavozim) va muddati (SLA kunlari, sozlanadi) bor; muddati o'tgani — qizil (rahbariyat KPI, «Mening vazifalarim»).
  * Studiya bandi: xonalar (standart bitta «Studiya»), ish vaqti, slot uzunligi; ziddiyat (xona, o'qituvchi, dars) — 409; ko'chirish va bekor
    qilish sabab bilan; eslatmalar (o'qituvchi va operator) — bir kun oldin va 1 soat oldin «Mening vazifalarim»da.
  * Xom video (oqim bilan diskka, ISFT_CORE_RAW_MAX_GB, standart 8 GB; mp4/mov/mkv/webm — baytlardan) → montaj shabloni → navbat.
  * Montaj ishchisi API (/api/montaj/*, X-Worker-Token = ISFT_CORE_WORKER_TOKEN): claim (lease 2 soat; progress uzaytiradi), imzolangan
    fayl havolalari (HMAC, HTTP Range), progress, natija (multipart, oqim bilan), xato (3 urinish, keyin operator).
  * Operator ko'rigi: natija videosi (Range), kesilganlar va bo'limlar → «Tasdiqlash» (paket ilgagi: video fayl + subtitr + poster) yoki «Qayta montaj».
  * YouTube (app/studio_yt.py; sozlanmaguncha o'chiq): unlisted, resumable upload, holat so'rovi → paketda YouTube havolasi (fayl zaxirada).
  * Avtomatik paket: «YouTube'da» (yoki YouTube o'chiq bo'lsa — tasdiqlangan fayl video) + matn va taqdimot bor → paket.build_topic.

Ruxsat (moduldagi jadval, har so'rov audit jurnalida — rbac.STUDIO):
  montaj_operator — kun rejasi, hamma bandlar, xom video, montaj, ko'rik/tasdiq, xonalar;  masofaviy (boshliq) — hammasi + SLA, YouTube, reja, NEXTID;
  masofaviy_xodim — boshliq kabi, sozlamalarsiz;  rektor, prorektor_oquv — faqat jamlangan holat va qizil belgilar (fayllarsiz);
  oqituvchi — o'z darslari: bosqich, band qilish / ko'chirish / bekor qilish;  it_head — faqat YouTube sozlamasi.
"""
from __future__ import annotations
import asyncio, datetime as dt, hashlib, hmac, json, os, re, secrets, shutil, threading, time
from pathlib import Path
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel
from . import clock, db, rbac
from . import studio_yt as YT
from .paket import _ascii, _short, _stream_upload, range_response     # umumiy yordamchilar (nusxa emas)
from .rbac import Ctx, AccessDenied

router = APIRouter()
_con = None
_ctx = None
_lock = threading.RLock()
_yt_lock = threading.Lock()
P = "/api/studio"
W = "/api/montaj"
RES = rbac.STUDIO

HEAD, STAFF, OPER, TEACH, IT = "masofaviy", "masofaviy_xodim", "montaj_operator", "oqituvchi", "it_head"
DEPT = (HEAD, STAFF)
LEAD = ("rektor", "prorektor_oquv")
OPS = DEPT + (OPER,)                      # kun rejasi, hamma bandlar, montaj, ko'rik
ALL = OPS + LEAD + (TEACH, IT)
YT_ADMIN = (HEAD, IT)                     # YouTube OAuth sirlari
ROOM_EDIT = (HEAD, OPER)
BOARD = OPS + LEAD
KINDS_OK = ("maruza", "amaliy")           # NEXTID darslari: L (ma'ruza), A (amaliy)

TEMPLATES = {"maruza_slayd": "Ma'ruza: o'qituvchi + slayd", "faqat_oqituvchi": "Faqat o'qituvchi", "ekran": "Ekran yozuvi + o'qituvchi burchakda"}
# (kalit, nomi, egasi — shu bosqichda kim harakat qiladi, SLA kunlari, keyingi qadam)
STAGES = [("bosh", "Ma'ruza tayyorlanmoqda", TEACH, 14, "Ma'ruza matni va taqdimotni «Dars tayyorlash»ga yuklash"),
          ("maruza", "Ma'ruza tayyor", TEACH, 5, "Studiyada syomkaga yozilish"),
          ("syomka_belgilandi", "Syomka belgilandi", OPER, 1, "Belgilangan vaqtda syomka"),
          ("syomka_qilindi", "Syomka qilindi", OPER, 1, "Xom videoni yuklash va montajga yuborish"),
          ("montaj", "Montajda (AI)", OPER, 1, "AI montaj (studiya kompyuteri)"),
          ("korib", "Ko'rib chiqishda (operator)", OPER, 2, "Montajni ko'rib chiqish: tasdiqlash yoki qayta montaj"),
          ("youtube", "YouTube'da", HEAD, 3, "Dars paketini tayyorlash"),
          ("paket", "Paket tayyor", HEAD, 3, "Paketni tekshirib tasdiqlash"),
          ("tasdiq", "Tasdiqlandi", HEAD, 3, "NEXTID'ga yuklash va belgilash"),
          ("nextid", "NEXTID'ga yuklandi", None, 0, "")]
ST = {s[0]: {"key": s[0], "label": s[1], "owner": s[2], "sla": s[3], "next": s[4], "i": i} for i, s in enumerate(STAGES)}
ORDER = [s[0] for s in STAGES]
OWNER_T = {TEACH: "O'qituvchi", OPER: "Studiya operatori", HEAD: "Masofaviy ta'lim bo'limi", None: "Tizim"}
JOB_ST = {"navbatda": "Navbatda", "ishlanmoqda": "Montaj qilinmoqda", "tayyor": "Ko'rib chiqish kutmoqda", "operator": "Xato — operator kerak",
          "tasdiqlandi": "Tasdiqlangan", "qayta": "Qayta montajga yuborilgan", "bekor": "Bekor qilingan"}
BOOK_ST = {"band": "Band", "otdi": "Syomka qilindi", "kelmadi": "Kelmadi", "bekor": "Bekor qilingan"}
YT_ST = {"navbatda": "Navbatda", "yuklanmoqda": "Yuklanmoqda", "ishlanmoqda": "YouTube'da qayta ishlanmoqda", "kutilmoqda": "Kvota — keyinroq",
         "tayyor": "YouTube'da", "xato": "Xato", "yuklandi_boglanmadi": "YouTube'ga yuklandi — darsga bog'lanmadi",
         "bekor": "Bekor qilindi (YouTube o'chiq — video fayl bilan)"}
YT_ACTIVE = ("navbatda", "yuklanmoqda", "ishlanmoqda", "kutilmoqda")      # fon oqimi ishlaydigan holatlar (YouTube API kerak)
YT_OPEN = YT_ACTIVE + ("xato", "yuklandi_boglanmadi")                      # hali yakunlanmagan (dars «ko'rib chiqishda» turadi)
JOB_ACTIVE = ("navbatda", "ishlanmoqda", "operator", "tayyor")             # natijasi / xom videosi hali kerak bo'lgan vazifalar
RAW_KINDS = ("mp4", "mov", "mkv", "webm")
SWEEP_S = 3600                                                              # saqlash muddati tozalovi — soatiga bir marta
SLOT_CHOICES = (30, 45, 60, 90, 120)
LEASE = 2 * 3600
URL_TTL = 2 * 3600
MAX_ATTEMPTS = 3
YT_MAX_RETRY = 8
HORIZON_DAYS = 90
POLL_S = 30
MAX_CAPTIONS = 2 * 1024 * 1024
MAX_THUMB = 10 * 1024 * 1024
MAX_REPORT = 2 * 1024 * 1024
STORE: Path | None = None                 # None → <DATA_DIR>/studio (testlarda almashtiriladi)
WORKER_NAME = "Montaj ishchisi: studiya kompyuteri"

SCHEMA = """
CREATE TABLE IF NOT EXISTS st_rooms(id INTEGER PRIMARY KEY, name TEXT, open_from TEXT DEFAULT '09:00', open_to TEXT DEFAULT '18:00', slot_min INT DEFAULT 90,
  days TEXT DEFAULT '1,2,3,4,5,6', active INT DEFAULT 1, updated_at TEXT, updated_by TEXT);
CREATE TABLE IF NOT EXISTS st_plan(course_id INTEGER PRIMARY KEY, ts TEXT, by_name TEXT, active INT DEFAULT 1);
CREATE TABLE IF NOT EXISTS st_bookings(id INTEGER PRIMARY KEY, room_id INT, course_id INT, lkey INT, teacher_id INT, start TEXT, end TEXT,
  status TEXT DEFAULT 'band', note TEXT, reason TEXT, created_at TEXT, created_by INT, created_name TEXT, updated_at TEXT, done_at TEXT, src TEXT DEFAULT '');
CREATE INDEX IF NOT EXISTS ix_st_b_room ON st_bookings(room_id, start);
CREATE INDEX IF NOT EXISTS ix_st_b_lesson ON st_bookings(course_id, lkey);
CREATE TABLE IF NOT EXISTS st_raw(id INTEGER PRIMARY KEY, course_id INT, lkey INT, booking_id INT, name TEXT, kind TEXT, path TEXT, size INT, sha256 TEXT,
  ts TEXT, user_id INT, user_name TEXT, deleted INT DEFAULT 0);
CREATE INDEX IF NOT EXISTS ix_st_raw ON st_raw(course_id, lkey);
CREATE TABLE IF NOT EXISTS st_jobs(id INTEGER PRIMARY KEY, course_id INT, lkey INT, raw_id INT, template TEXT, status TEXT, attempts INT DEFAULT 0,
  not_before TEXT, lease_until TEXT, claimed_at TEXT, stage TEXT, pct INT, message TEXT, error TEXT, note TEXT, report TEXT, files TEXT, result_at TEXT,
  created_at TEXT, created_by INT, created_name TEXT, updated_at TEXT, decided_at TEXT, decided_by INT, decided_name TEXT, prev_id INT, lease TEXT);
CREATE INDEX IF NOT EXISTS ix_st_jobs ON st_jobs(status, id);
CREATE INDEX IF NOT EXISTS ix_st_jobs_l ON st_jobs(course_id, lkey);
CREATE TABLE IF NOT EXISTS st_yt(id INTEGER PRIMARY KEY, course_id INT, lkey INT, job_id INT, status TEXT, session_url TEXT, offset INT DEFAULT 0, size INT,
  video_id TEXT, privacy TEXT, attempts INT DEFAULT 0, next_try TEXT, error TEXT, warning TEXT, day TEXT, created_at TEXT, updated_at TEXT, done_at TEXT);
CREATE INDEX IF NOT EXISTS ix_st_yt ON st_yt(status, next_try);
CREATE TABLE IF NOT EXISTS st_marks(course_id INT, lkey INT, stage TEXT, ref INT, ts TEXT, by_name TEXT, PRIMARY KEY(course_id, lkey, stage));
CREATE TABLE IF NOT EXISTS st_log(id INTEGER PRIMARY KEY, ts TEXT, course_id INT, lkey INT, action TEXT, note TEXT, user_id INT, user_name TEXT,
  job_id INT, booking_id INT);
CREATE INDEX IF NOT EXISTS ix_st_log ON st_log(course_id, lkey);
CREATE TABLE IF NOT EXISTS st_meta(k TEXT PRIMARY KEY, v TEXT);
"""
DEMO_OPERATOR = ("Masofaviy ta'lim bo'limi — studiya operatori: Xolmatov Sardor Baxtiyor o'g'li", OPER, "STUDIYA")


# =============================================================================================
# Yordamchilar
# =============================================================================================
def _now() -> dt.datetime: return clock.now().replace(microsecond=0)
def _iso(t: dt.datetime | None) -> str | None: return t.replace(microsecond=0).isoformat(timespec="seconds") if t else None
def store() -> Path: return STORE or (Path(db.DATA_DIR) / "studio")

def _pdt(s) -> dt.datetime | None:
    s = str(s or "").strip().replace(" ", "T")
    if not s: return None
    try: return dt.datetime.fromisoformat(s[:19])
    except ValueError: return None

def _gb(name: str, default: float) -> int:
    try: v = float(os.getenv(name, str(default)))
    except ValueError: v = default
    return int(max(1e-6, v) * 1024 ** 3)

def raw_max() -> int: return _gb("ISFT_CORE_RAW_MAX_GB", 8)
def result_max() -> int: return _gb("ISFT_CORE_RESULT_MAX_GB", raw_max() / 1024 ** 3)

def worker_token() -> str: return (os.getenv("ISFT_CORE_WORKER_TOKEN") or "").strip()

def raw_keep_days() -> float:
    """Dars videosi tasdiqlangandan keyin xom video necha kun saqlanadi (ISFT_CORE_RAW_KEEP_DAYS, standart 14)."""
    try: return max(0.0, float(os.getenv("ISFT_CORE_RAW_KEEP_DAYS", "14")))
    except ValueError: return 14.0

def _meta(k: str, default=None):
    r = db.one(_con, "SELECT v FROM st_meta WHERE k=?", (k,))
    if not r: return default
    try: return json.loads(r["v"])
    except (TypeError, ValueError): return default

def _set_meta(k: str, v) -> None:
    _con.execute("INSERT INTO st_meta(k,v) VALUES(?,?) ON CONFLICT(k) DO UPDATE SET v=excluded.v", (k, json.dumps(v, ensure_ascii=False)))

def _log(c: Ctx | None, cid, lkey, action: str, note: str = "", job_id=None, booking_id=None, who: str | None = None) -> None:
    u = c.user if c else {"id": None, "full_name": who or "Tizim"}
    _con.execute("INSERT INTO st_log(ts,course_id,lkey,action,note,user_id,user_name,job_id,booking_id) VALUES(?,?,?,?,?,?,?,?,?)",
                 (_iso(_now()), cid, lkey, action, (note or "")[:500], u.get("id"), u.get("full_name"), job_id, booking_id))

def _mw_invalidate():
    try:
        from . import mywork as MW
        MW.invalidate()
    except Exception: pass

def _PK():
    from . import paket as PK
    return PK

def sla() -> dict:
    st = _meta("sla", {}) or {}
    out = {}
    for k, v in ST.items():
        try: out[k] = max(0, min(90, int(st.get(k, v["sla"]))))
        except (TypeError, ValueError): out[k] = v["sla"]
    return out


# =============================================================================================
# Sxema, demo
# =============================================================================================
def init(con):
    try:
        con.executescript(SCHEMA)
        if "lease" not in {r[1] for r in con.execute("PRAGMA table_info(st_jobs)")}:     # eski baza: lease identifikatori ustuni
            con.execute("ALTER TABLE st_jobs ADD COLUMN lease TEXT")
        if not db.one(con, "SELECT 1 x FROM st_rooms"):
            con.execute("INSERT INTO st_rooms(name,open_from,open_to,slot_min,days,active,updated_at,updated_by) VALUES('Studiya','09:00','18:00',90,'1,2,3,4,5,6',1,?,'Tizim')",
                        (_iso(_now()),))
        con.commit()
    except Exception as e:
        print("studio.init:", repr(e)); return
    if not db.one(con, "SELECT 1 x FROM users"): return
    try:
        _ensure_user(con)
        _seed(con)
    except Exception as e:      # demo ilovani to'xtatmasin
        print("studio seed:", repr(e))

def _ensure_user(con):
    name, role, code = DEMO_OPERATOR
    if not db.one(con, "SELECT 1 x FROM users WHERE role=?", (role,)):
        con.execute("INSERT INTO users(full_name,role,unit,link_code,pin) VALUES(?,?,?,?,?)",
                    (name, role, "masofaviy", code, rbac.hash_password(rbac.DEMO_PASSWORD)))
        con.commit()

def _grid_day(room: dict, day: dt.date) -> list[tuple[dt.datetime, dt.datetime]]:
    if str(day.isoweekday()) not in str(room["days"] or "").split(","): return []
    a = dt.datetime.combine(day, dt.time.fromisoformat(room["open_from"])); z = dt.datetime.combine(day, dt.time.fromisoformat(room["open_to"]))
    step, out = dt.timedelta(minutes=int(room["slot_min"])), []
    while a + step <= z:
        out.append((a, a + step)); a += step
    return out

def _seed(con):
    """Namuna (bir marta): o'qituvchi demo akkauntining kursi va «Mikroiqtisodiyot» ishlab chiqarish rejasida; yaqin kunlarga 3 ta syomka bandi."""
    if db.one(con, "SELECT 1 x FROM st_meta WHERE k='seed_v1'"): return
    now = _now()
    t = db.one(con, "SELECT teacher_id FROM users WHERE role='oqituvchi' AND teacher_id IS NOT NULL ORDER BY id LIMIT 1")
    own = db.one(con, "SELECT * FROM dl_courses WHERE teacher_id=? ORDER BY id LIMIT 1", (t["teacher_id"],)) if t else None
    mikro = db.one(con, "SELECT * FROM dl_courses WHERE subject='Mikroiqtisodiyot' ORDER BY id LIMIT 1")
    room = db.one(con, "SELECT * FROM st_rooms ORDER BY id LIMIT 1")
    for co in (own, mikro):
        if co: con.execute("INSERT OR IGNORE INTO st_plan(course_id,ts,by_name,active) VALUES(?,?,?,1)", (co["id"], _iso(now - dt.timedelta(days=3)), "Namuna"))
    days, d = [], now.date()
    while len(days) < 3:
        d += dt.timedelta(days=1)
        if _grid_day(room, d): days.append(d)
    plan = [(own, 3, days[0], 0), (own, 4, days[1], 1), (mikro, 3, days[0], 3)]
    for co, no, day, slot in plan:
        if not co: continue
        g = _grid_day(room, day)
        a, b = g[min(slot, len(g) - 1)]
        con.execute("""INSERT INTO st_bookings(room_id,course_id,lkey,teacher_id,start,end,status,note,created_at,created_by,created_name,updated_at,src)
                       VALUES(?,?,?,?,?,?,'band','Namuna band',?,NULL,'Namuna',?,'demo')""",
                    (room["id"], co["id"], no, co["teacher_id"], _iso(a), _iso(b), _iso(now), _iso(now)))
    con.execute("INSERT OR REPLACE INTO st_meta(k,v) VALUES('seed_v1', ?)", (json.dumps(_iso(now)),))
    con.commit()

def bind(con, ctx_fn):
    global _con, _ctx
    _con, _ctx = con, ctx_fn


# =============================================================================================
# Ruxsat
# =============================================================================================
def C(request: Request) -> Ctx: return _ctx(request)

def guard(c: Ctx, action: str, roles=ALL, detail: str = ""):
    ok = c.role.key in roles and c.channel == "web"
    rbac.audit(_con, c, f"studiya: {action}", RES, ok, detail)
    if not ok:
        raise AccessDenied(f"⛔ Studiya: {action} — '{c.role.title}' lavozimi uchun ruxsat yo'q. So'rov audit jurnaliga yozildi.")

def _tid(c: Ctx) -> int: return int(c.user.get("teacher_id") or 0)

def _course(c: Ctx, cid: int, write: bool = False) -> dict:
    co = db.one(_con, """SELECT c.*, d.name dept, t.full_name teacher FROM dl_courses c LEFT JOIN departments d ON d.id=c.department_id
                         LEFT JOIN teachers t ON t.id=c.teacher_id WHERE c.id=?""", (int(cid),))
    if not co: raise HTTPException(404, "Kurs topilmadi")
    k = c.role.key
    if k == TEACH and co["teacher_id"] != _tid(c):
        rbac.audit(_con, c, "studiya: begona kurs", RES, False, f"kurs #{cid}")
        raise AccessDenied("⛔ Bu kurs sizniki emas. So'rov audit jurnaliga yozildi.")
    if k not in OPS + (TEACH,) or (write and k not in OPS + (TEACH,)):
        rbac.audit(_con, c, "studiya: dars darajasi rad etildi", RES, False, f"kurs #{cid}")
        raise AccessDenied("⛔ Studiya: dars tafsiloti — faqat bo'lim, operator va o'qituvchi. So'rov audit jurnaliga yozildi.")
    return co

def _lesson(co: dict, lkey: int) -> dict:
    les = _PK().lesson_info(co, int(lkey))
    if les["kind"] not in KINDS_OK: raise HTTPException(400, "Studiyada faqat ma'ruza (L) va amaliy (A) darslari tayyorlanadi")
    return les


# =============================================================================================
# Bosqichlar: hisoblash (derive) — sof funksiya
# =============================================================================================
def _plus(t: dt.datetime | None, days: int) -> dt.datetime | None:
    return t + dt.timedelta(days=days) if t else None

def derive(L: dict, now: dt.datetime, sla_: dict, yt_on: bool) -> dict:
    """Bitta dars holati. L: r (paket tayyorgarligi: text/slides/video), last/appr (paket qatorlari), bk (faol band), bdone (oxirgi «syomka qilindi»),
    raw (oxirgi xom video), job (oxirgi montaj vazifasi), yt (oxirgi YouTube navbati), mark (NEXTID belgisi), plan_ts, mat_ts, vid_ts, tracked.
    Avval faol studiya tsikli (band → syomka → montaj → ko'rik → YouTube), u bo'lmasa — ma'lumotdan (NEXTID > tasdiq > paket > video > ma'ruza)."""
    r = L.get("r") or {}
    bk, bd, raw, job, yt, mark = (L.get(k) for k in ("bk", "bdone", "raw", "job", "yt", "mark"))
    last, appr = L.get("last"), L.get("appr")
    plan_ts = _pdt(L.get("plan_ts"))
    appr_job = job if job and job["status"] == "tasdiqlandi" else None
    ytc = yt if yt and appr_job and yt.get("job_id") == appr_job["id"] else None
    yt_pending = bool(ytc and ytc["status"] in YT_OPEN)                 # «bekor» (YouTube o'chirildi) — fayl video bilan davom etiladi
    raw_new = bool(raw and (not job or raw["id"] > int(job.get("raw_id") or 0)))
    bd_t = _pdt(bd["done_at"]) if bd else None
    bd_new = bool(bd_t and not raw_new and (not raw or bd_t > _pdt(raw["ts"])) and (not job or bd_t > _pdt(job["created_at"])))
    stage, since, due, wait, owner, studio = None, None, None, "", "-", True
    if bk:
        stage, since = "syomka_belgilandi", _pdt(bk["created_at"])
        due = _plus(_pdt(bk["end"]), sla_[stage]); wait = f"Syomka: {bk['start'][8:10]}.{bk['start'][5:7]} soat {bk['start'][11:16]}"
    elif raw_new:
        stage, since, wait = "syomka_qilindi", _pdt(raw["ts"]), "Xom video yuklangan — montajga yuborilmagan"
    elif job and job["status"] in ("navbatda", "ishlanmoqda", "operator"):
        stage, since = "montaj", _pdt(job["created_at"])
        wait = {"navbatda": "Montaj navbatida", "ishlanmoqda": f"Montaj: {job.get('pct') or 0}%",
                "operator": "Montaj 3 marta muvaffaqiyatsiz — operator qayta yuborishi kerak"}[job["status"]]
    elif job and job["status"] == "tayyor":
        stage, since, wait = "korib", _pdt(job["result_at"]), "Montaj tayyor — ko'rib chiqing"
    elif yt_pending:
        stage, since = "korib", _pdt(appr_job["decided_at"])
        if ytc["status"] == "xato": wait, owner = f"YouTube xatosi: {ytc.get('error') or ''}"[:200], HEAD
        elif ytc["status"] == "yuklandi_boglanmadi": wait, owner = f"YouTube'ga yuklandi, darsga bog'lanmadi: {ytc.get('error') or ''}"[:200], HEAD
        else: wait, owner = f"YouTube: {YT_ST.get(ytc['status'], ytc['status'])}", None
    elif bd_new:
        stage, since, wait = "syomka_qilindi", bd_t, "Syomka qilindi — xom video yuklanmagan"
    if stage is None:
        studio = False
        mt = None
        if mark and appr and last and appr["id"] == last["id"] and int(mark.get("ref") or 0) == appr["id"]:
            stage, mt = "nextid", _pdt(mark["ts"])
        elif last and last["status"] == "tasdiqlandi":
            stage, mt = "tasdiq", _pdt(last.get("approved_at") or last.get("built_at"))
        elif last and last["status"] == "tayyor":
            stage, mt = "paket", _pdt(last["built_at"])
        elif r.get("video") or (ytc and ytc["status"] == "tayyor"):
            stage = "youtube"
            mt = _pdt((ytc or {}).get("done_at")) or _pdt((appr_job or {}).get("decided_at")) or _pdt(L.get("vid_ts"))
            if last and last["status"] == "qoralama" and last.get("note"):
                wait, owner = f"Bo'lim qaytargan: {last['note']}"[:200], TEACH
            elif not (r.get("text") and r.get("slides")):
                wait, owner = "Paket uchun ma'ruza matni yoki taqdimot yetishmaydi", TEACH
            elif not yt_on and appr_job:
                wait = "Video fayl (YouTube ulanmagan) — paketni tayyorlang"
        elif r.get("text") and r.get("slides"):
            stage, mt = "maruza", _pdt(L.get("mat_ts"))
        else:
            stage = "bosh"
        since = max([x for x in (mt, plan_ts) if x], default=None)
        due = _plus(since, sla_[stage]) if stage != "nextid" else None
    else:
        due = due or _plus(since, sla_[stage])
    s = ST[stage]
    if owner == "-": owner = s["owner"]
    tracked = bool(L.get("tracked"))
    over = bool(tracked and due and due < now and stage != "nextid")
    return {"stage": stage, "label": s["label"], "i": s["i"], "since": _iso(since), "due": _iso(due), "over": over,
            "days_over": max(0, (now - due).days) if over else 0, "owner": owner, "owner_label": OWNER_T.get(owner, "Tizim"),
            "next": wait or s["next"], "studio": studio, "tracked": tracked}


# =============================================================================================
# Ma'lumot yig'ish (bir nechta kurs uchun bitta o'tishda)
# =============================================================================================
def _in(cids) -> tuple[str, tuple]:
    cids = sorted({int(x) for x in cids})
    return (f"course_id IN ({','.join('?' * len(cids))})", tuple(cids)) if cids else ("0", ())

def tracked_courses() -> list[int]:
    out = {r["course_id"] for r in db.rows(_con, "SELECT course_id FROM st_plan WHERE active=1")}
    for t in ("st_bookings", "st_raw", "st_jobs"):
        out |= {r["course_id"] for r in db.rows(_con, f"SELECT DISTINCT course_id FROM {t}" + (" WHERE status!='bekor'" if t != "st_raw" else " WHERE deleted=0"))}
    return sorted(out)

def _courses(cids) -> list[dict]:
    if not cids: return []
    w, a = _in(cids)
    return db.rows(_con, f"""SELECT c.*, d.name dept, t.full_name teacher FROM dl_courses c LEFT JOIN departments d ON d.id=c.department_id
                             LEFT JOIN teachers t ON t.id=c.teacher_id WHERE c.{w.replace('course_id', 'id')} ORDER BY c.subject, c.id""", a)

def states(courses: list[dict], only_keys: dict | None = None) -> list[dict]:
    """[{course…, lesson…, state…}] — kurslarning L/A darslari bo'yicha. only_keys: {cid: {lkey,…}} — faqat shular."""
    if not courses: return []
    PK = _PK()
    cids = [co["id"] for co in courses]
    w, a = _in(cids)
    now, sla_, yt_on = _now(), sla(), YT.configured()
    rm = PK.readiness_map()
    plan = {r["course_id"]: r["ts"] for r in db.rows(_con, f"SELECT course_id, ts FROM st_plan WHERE active=1 AND {w}", a)}
    bk, bdone, rec = {}, {}, set()
    for r in db.rows(_con, f"SELECT * FROM st_bookings WHERE {w} ORDER BY start", a):
        k = (r["course_id"], r["lkey"])
        if r["status"] != "bekor": rec.add(k)
        if r["status"] == "band": bk[k] = r
        elif r["status"] == "otdi": bdone[k] = r
    raw = {}
    for r in db.rows(_con, f"SELECT * FROM st_raw WHERE deleted=0 AND {w} ORDER BY id", a): raw[(r["course_id"], r["lkey"])] = r; rec.add((r["course_id"], r["lkey"]))
    job = {}
    for r in db.rows(_con, f"SELECT * FROM st_jobs WHERE status!='bekor' AND {w} ORDER BY id", a): job[(r["course_id"], r["lkey"])] = r; rec.add((r["course_id"], r["lkey"]))
    yt = {(r["course_id"], r["lkey"]): r for r in db.rows(_con, f"SELECT * FROM st_yt WHERE {w} ORDER BY id", a)}
    marks = {(r["course_id"], r["lkey"]): r for r in db.rows(_con, f"SELECT * FROM st_marks WHERE stage='nextid' AND {w}", a)}
    last, appr = {}, {}
    for r in db.rows(_con, f"SELECT id, course_id, topic_no, version, status, built_at, approved_at, note FROM pk_packages WHERE topic_no>0 AND {w} ORDER BY version", a):
        k = (r["course_id"], r["topic_no"]); last[k] = r
        if r["status"] == "tasdiqlandi": appr[k] = r
    mat = {(r["course_id"], r["topic_no"]): r["t"] for r in db.rows(_con, f"""SELECT course_id, topic_no, MAX(ts) t FROM pk_assets WHERE deleted=0
                                                                              AND purpose IN ('matn','taqdimot','slayd') AND {w} GROUP BY course_id, topic_no""", a)}
    vid = {(r["course_id"], r["topic_no"]): r["t"] for r in db.rows(_con, f"""SELECT course_id, topic_no, MAX(ts) t FROM pk_assets WHERE deleted=0
                                                                              AND purpose='video' AND {w} GROUP BY course_id, topic_no""", a)}
    for r in db.rows(_con, f"SELECT course_id, topic_no, video_at FROM pk_topics WHERE video_url IS NOT NULL AND video_url!='' AND {w}", a):
        k = (r["course_id"], r["topic_no"]); vid[k] = max(x for x in (vid.get(k), r["video_at"]) if x) if (vid.get(k) or r["video_at"]) else None
    out = []
    for co in courses:
        for les in PK.lessons(co["id"], co):
            if les["kind"] not in KINDS_OK: continue
            if only_keys is not None and les["key"] not in only_keys.get(co["id"], ()): continue
            k = (co["id"], les["key"])
            L = {"r": rm.get(k), "last": last.get(k), "appr": appr.get(k), "bk": bk.get(k), "bdone": bdone.get(k), "raw": raw.get(k), "job": job.get(k),
                 "yt": yt.get(k), "mark": marks.get(k), "plan_ts": plan.get(co["id"]), "mat_ts": mat.get(k), "vid_ts": vid.get(k),
                 "tracked": co["id"] in plan or k in rec}
            s = derive(L, now, sla_, yt_on)
            rr = rm.get(k) or {}
            out.append({"course_id": co["id"], "subject": co["subject"], "direction": co.get("direction"), "course": co.get("course"),
                        "dept": co.get("dept") or "", "department_id": co.get("department_id"), "teacher": _short(co.get("teacher") or ""),
                        "teacher_id": co.get("teacher_id"), "lkey": les["key"], "code": les["code"], "kind": les["kind"], "title": les["title"],
                        "planned": co["id"] in plan, "ready": {x: bool(rr.get(x)) for x in ("text", "slides", "video")},
                        "booking": _bk_row(bk[k]) if k in bk else None, "job": {"id": job[k]["id"], "status": job[k]["status"]} if k in job else None,
                        **s})
    return out


# =============================================================================================
# Holat paneli (board), KPI, darslar
# =============================================================================================
def board(c: Ctx, group: str = "course") -> dict:
    guard(c, "holat paneli", BOARD, group)
    if group not in ("course", "kafedra", "teacher"): group = "course"
    S = states(_courses(tracked_courses()))
    S = [s for s in S if s["tracked"]]
    keyf = {"course": lambda s: (s["course_id"], f"{s['subject']} ({s['direction'] or ''}, {s['course'] or ''}-kurs)"),
            "kafedra": lambda s: (s["department_id"] or 0, s["dept"] or "Kafedra ko'rsatilmagan"),
            "teacher": lambda s: (s["teacher_id"] or 0, s["teacher"] or "O'qituvchi ko'rsatilmagan")}[group]
    rows, totals = {}, {k: 0 for k in ORDER}
    for s in S:
        kid, name = keyf(s)
        row = rows.setdefault(kid, {"key": kid, "name": name, "counts": {k: 0 for k in ORDER}, "red": 0, "total": 0})
        row["counts"][s["stage"]] += 1; row["total"] += 1; totals[s["stage"]] += 1
        if s["over"]: row["red"] += 1
    red = sorted((s for s in S if s["over"]), key=lambda s: (-s["days_over"], s["subject"], s["lkey"]))
    lead = c.role.key in LEAD
    keep = ("course_id", "subject", "teacher", "dept", "lkey", "code", "title", "stage", "label", "owner_label", "next", "due", "days_over")
    return {"group": group, "stages": [{"key": k, "label": ST[k]["label"], "owner": OWNER_T.get(ST[k]["owner"], "")} for k in ORDER],
            "totals": totals, "total": len(S), "red_total": len(red), "done": totals["nextid"],
            "rows": sorted(rows.values(), key=lambda r: (-r["red"], r["name"])),
            "red": [{k: s[k] for k in keep} for s in red[:200]], "aggregate": lead, "sla": sla()}

def kpi(c: Ctx) -> dict:
    guard(c, "KPI", BOARD)
    S = [s for s in states(_courses(tracked_courses())) if s["tracked"]]
    red = sum(1 for s in S if s["over"])
    act = sum(1 for s in S if s["stage"] != "nextid")
    return {"key": "studio", "label": "Dars ishlab chiqarish", "value": red, "sub": f"ta muddati o'tgan · {act} ta dars jarayonda",
            "bad": red > 0, "red": red, "active": act, "done": len(S) - act}

def lessons_list(c: Ctx, course_id: int = 0) -> dict:
    guard(c, "darslar", OPS + (TEACH,), f"kurs #{course_id}" if course_id else "")
    if c.role.key == TEACH:
        cos = db.rows(_con, """SELECT c.*, d.name dept, t.full_name teacher FROM dl_courses c LEFT JOIN departments d ON d.id=c.department_id
                               LEFT JOIN teachers t ON t.id=c.teacher_id WHERE c.teacher_id=? ORDER BY c.subject, c.id""", (_tid(c),))
        if course_id: cos = [co for co in cos if co["id"] == int(course_id)]
    elif course_id:
        cos = [_course(c, course_id)]
    else:
        cos = _courses(tracked_courses())
    S = states(cos)
    plan = {r["course_id"] for r in db.rows(_con, "SELECT course_id FROM st_plan WHERE active=1")}
    return {"courses": [{"id": co["id"], "subject": co["subject"], "direction": co.get("direction"), "course": co.get("course"), "dept": co.get("dept"),
                         "teacher": _short(co.get("teacher") or ""), "planned": co["id"] in plan} for co in cos],
            "lessons": S, "stages": [{"key": k, "label": ST[k]["label"]} for k in ORDER]}

def course_search(c: Ctx, q: str = "") -> list[dict]:
    guard(c, "kurs qidirish", OPS)
    q = (q or "").strip()
    plan = {r["course_id"] for r in db.rows(_con, "SELECT course_id FROM st_plan WHERE active=1")}
    w, a = "1=1", []
    if q:
        w = "(c.subject LIKE ? OR c.direction LIKE ? OR t.full_name LIKE ?)"; a = [f"%{q}%"] * 3
    rows = db.rows(_con, f"""SELECT c.id, c.subject, c.direction, c.course, d.name dept, t.full_name teacher FROM dl_courses c
                             LEFT JOIN departments d ON d.id=c.department_id LEFT JOIN teachers t ON t.id=c.teacher_id WHERE {w}
                             ORDER BY c.subject, c.id LIMIT 40""", a)
    return [{**r, "teacher": _short(r["teacher"] or ""), "planned": r["id"] in plan} for r in rows]

def set_plan(c: Ctx, cid: int, on: bool) -> dict:
    guard(c, "ishlab chiqarish rejasi", DEPT, f"kurs #{cid} · {'qo`shildi' if on else 'olindi'}")
    co = _course(c, cid)
    with _lock:
        if on:
            _con.execute("INSERT INTO st_plan(course_id,ts,by_name,active) VALUES(?,?,?,1) ON CONFLICT(course_id) DO UPDATE SET active=1, by_name=excluded.by_name",
                         (co["id"], _iso(_now()), c.user["full_name"]))
        else:
            _con.execute("UPDATE st_plan SET active=0 WHERE course_id=?", (co["id"],))
        _log(c, co["id"], 0, "reja: kurs qo'shildi" if on else "reja: kurs olib tashlandi", co["subject"]); _con.commit()
    _mw_invalidate()
    return {"ok": True, "course_id": co["id"], "planned": bool(on)}

def lesson_detail(c: Ctx, cid: int, lkey: int) -> dict:
    guard(c, "dars", OPS + (TEACH,), f"kurs #{cid} · {lkey}")
    co = _course(c, cid); les = _lesson(co, lkey)
    st = states([co], {co["id"]: {les["key"]}})
    ops = c.role.key in OPS
    bks = [_bk_row(b) for b in db.rows(_con, "SELECT * FROM st_bookings WHERE course_id=? AND lkey=? ORDER BY start DESC LIMIT 20", (co["id"], les["key"]))]
    raws = [{k: r[k] for k in ("id", "name", "kind", "size", "ts", "user_name")} for r in
            db.rows(_con, "SELECT * FROM st_raw WHERE course_id=? AND lkey=? AND deleted=0 ORDER BY id DESC LIMIT 10", (co["id"], les["key"]))] if ops else []
    jobs = [_job_row(j) for j in db.rows(_con, "SELECT * FROM st_jobs WHERE course_id=? AND lkey=? ORDER BY id DESC LIMIT 10", (co["id"], les["key"]))]
    yts = [_yt_row(y) for y in db.rows(_con, "SELECT * FROM st_yt WHERE course_id=? AND lkey=? ORDER BY id DESC LIMIT 5", (co["id"], les["key"]))]
    log = db.rows(_con, "SELECT ts, action, note, user_name FROM st_log WHERE course_id=? AND lkey=? ORDER BY id DESC LIMIT 60", (co["id"], les["key"]))
    pk = db.rows(_con, "SELECT ts, action, note, user_name FROM pk_log WHERE course_id=? AND topic_no=? ORDER BY id DESC LIMIT 30", (co["id"], les["key"]))
    hist = sorted([{**x, "src": "studiya", "user_name": _short(x["user_name"])} for x in log] +
                  [{**x, "src": "paket", "user_name": _short(x["user_name"])} for x in pk], key=lambda x: x["ts"] or "", reverse=True)[:80]
    return {"lesson": {"course_id": co["id"], "lkey": les["key"], "code": les["code"], "kind": les["kind"], "title": les["title"], "subject": co["subject"],
                       "teacher": _short(co.get("teacher") or ""), "dept": co.get("dept")},
            "state": st[0] if st else None, "bookings": bks, "raws": raws, "jobs": jobs if ops else [{k: j[k] for k in ("id", "status", "status_label", "created_at")} for j in jobs],
            "youtube": yts, "history": hist}

def mark_nextid(c: Ctx, cid: int, lkey: int, undo: bool = False) -> dict:
    guard(c, "NEXTID belgisi", DEPT, f"kurs #{cid} · {lkey} · {'bekor' if undo else 'yuklandi'}")
    co = _course(c, cid); les = _lesson(co, lkey)
    with _lock:
        if undo:
            _con.execute("DELETE FROM st_marks WHERE course_id=? AND lkey=? AND stage='nextid'", (co["id"], les["key"]))
            _log(c, co["id"], les["key"], "NEXTID belgisi olib tashlandi")
        else:
            p = db.one(_con, "SELECT * FROM pk_packages WHERE course_id=? AND topic_no=? ORDER BY version DESC LIMIT 1", (co["id"], les["key"]))
            if not p or p["status"] != "tasdiqlandi": raise HTTPException(409, "Avval dars paketining oxirgi versiyasi tasdiqlanishi kerak")
            _con.execute("INSERT OR REPLACE INTO st_marks(course_id,lkey,stage,ref,ts,by_name) VALUES(?,?,'nextid',?,?,?)",
                         (co["id"], les["key"], p["id"], _iso(_now()), c.user["full_name"]))
            _log(c, co["id"], les["key"], "NEXTID'ga yuklandi", f"paket v{p['version']}")
        _con.commit()
    _mw_invalidate()
    return {"ok": True, "state": states([co], {co["id"]: {les["key"]}})[0]}


# =============================================================================================
# Studiya bandi
# =============================================================================================
_HHMM = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")

def _rooms(active_only: bool = True) -> list[dict]:
    return db.rows(_con, "SELECT * FROM st_rooms" + (" WHERE active=1" if active_only else "") + " ORDER BY id")

def _room(rid: int) -> dict:
    r = db.one(_con, "SELECT * FROM st_rooms WHERE id=?", (int(rid),))
    if not r or not r["active"]: raise HTTPException(404, "Studiya xonasi topilmadi")
    return r

def _bk_row(b: dict) -> dict:
    return {k: b.get(k) for k in ("id", "room_id", "course_id", "lkey", "teacher_id", "start", "end", "status", "note", "reason", "created_name", "done_at", "src")} | \
           {"status_label": BOOK_ST.get(b["status"], b["status"]), "created_name": _short(b.get("created_name"))}

def _check_slot(room: dict, start: dt.datetime) -> dt.datetime:
    now = _now()
    if start <= now: raise HTTPException(400, "O'tib ketgan vaqtni band qilib bo'lmaydi")
    if start.date() > (now + dt.timedelta(days=HORIZON_DAYS)).date(): raise HTTPException(400, f"Ko'pi bilan {HORIZON_DAYS} kun oldinga band qilinadi")
    g = _grid_day(room, start.date())
    if not g: raise HTTPException(400, f"«{room['name']}» bu kuni ishlamaydi")
    for a, b in g:
        if a == start: return b
    raise HTTPException(400, f"Vaqt jadvalga mos emas: «{room['name']}» {room['open_from']}–{room['open_to']}, har {room['slot_min']} daqiqa")

def _conflict(room_id: int, start: dt.datetime, end: dt.datetime, teacher_id, cid: int, lkey: int, exclude: int = 0) -> str | None:
    a, b = _iso(start), _iso(end)
    if db.one(_con, "SELECT id FROM st_bookings WHERE status='band' AND room_id=? AND start<? AND end>? AND id<>?", (room_id, b, a, exclude)):
        return "Bu vaqt band — boshqa slot tanlang"
    if teacher_id and db.one(_con, "SELECT id FROM st_bookings WHERE status='band' AND teacher_id=? AND start<? AND end>? AND id<>?", (teacher_id, b, a, exclude)):
        return "O'qituvchining shu vaqtda boshqa syomkasi bor"
    if db.one(_con, "SELECT id FROM st_bookings WHERE status='band' AND course_id=? AND lkey=? AND id<>?", (cid, lkey, exclude)):
        return "Bu dars uchun syomka allaqachon belgilangan — ko'chiring yoki bekor qiling"
    return None

def book(c: Ctx, cid: int, lkey: int, room_id: int, start: str, note: str = "") -> dict:
    guard(c, "syomkaga yozilish", OPS + (TEACH,), f"kurs #{cid} · {lkey} · {start}")
    co = _course(c, cid, write=True); les = _lesson(co, lkey)
    room = _room(room_id or (_rooms() or [{"id": 0}])[0]["id"])
    t0 = _pdt(start)
    if not t0: raise HTTPException(400, "Vaqt noto'g'ri (YYYY-MM-DDTHH:MM)")
    with _lock:
        t1 = _check_slot(room, t0)
        why = _conflict(room["id"], t0, t1, co["teacher_id"], co["id"], les["key"])
        if why:
            rbac.audit(_con, c, "studiya: band ziddiyati", RES, False, f"kurs #{cid} · {les['code']} · {start} · {why}")
            raise HTTPException(409, why)
        now = _iso(_now())
        bid = _con.execute("""INSERT INTO st_bookings(room_id,course_id,lkey,teacher_id,start,end,status,note,created_at,created_by,created_name,updated_at)
                              VALUES(?,?,?,?,?,?,'band',?,?,?,?,?)""",
                           (room["id"], co["id"], les["key"], co["teacher_id"], _iso(t0), _iso(t1), (note or "").strip()[:300] or None, now,
                            c.user["id"], c.user["full_name"], now)).lastrowid
        _log(c, co["id"], les["key"], "syomka belgilandi", f"{room['name']} · {_iso(t0)[:16].replace('T', ' ')}", booking_id=bid); _con.commit()
    _mw_invalidate()
    rr = _PK().readiness_map().get((co["id"], les["key"])) or {}
    warn = "" if rr.get("text") and rr.get("slides") else "Diqqat: ma'ruza matni yoki taqdimot hali «Dars tayyorlash»ga yuklanmagan"
    return {"ok": True, "booking": _bk_row(db.one(_con, "SELECT * FROM st_bookings WHERE id=?", (bid,))), "warning": warn}

def _booking(c: Ctx, bid: int) -> dict:
    b = db.one(_con, "SELECT * FROM st_bookings WHERE id=?", (int(bid),))
    if not b: raise HTTPException(404, "Band topilmadi")
    if c.role.key == TEACH:
        co = db.one(_con, "SELECT teacher_id FROM dl_courses WHERE id=?", (b["course_id"],))
        if not co or co["teacher_id"] != _tid(c):
            rbac.audit(_con, c, "studiya: begona band", RES, False, f"band #{bid}")
            raise AccessDenied("⛔ Bu band sizniki emas. So'rov audit jurnaliga yozildi.")
    return b

def move(c: Ctx, bid: int, start: str, reason: str, room_id: int = 0) -> dict:
    guard(c, "bandni ko'chirish", OPS + (TEACH,), f"band #{bid} → {start}")
    b = _booking(c, bid)
    if b["status"] != "band": raise HTTPException(409, "Faqat faol band ko'chiriladi")
    if len((reason or "").strip()) < 3: raise HTTPException(400, "Ko'chirish sababini yozing")
    room = _room(room_id or b["room_id"])
    t0 = _pdt(start)
    if not t0: raise HTTPException(400, "Vaqt noto'g'ri (YYYY-MM-DDTHH:MM)")
    with _lock:
        t1 = _check_slot(room, t0)
        why = _conflict(room["id"], t0, t1, b["teacher_id"], b["course_id"], b["lkey"], exclude=b["id"])
        if why: raise HTTPException(409, why)
        _con.execute("UPDATE st_bookings SET room_id=?, start=?, end=?, reason=?, updated_at=? WHERE id=?",
                     (room["id"], _iso(t0), _iso(t1), reason.strip()[:300], _iso(_now()), b["id"]))
        _log(c, b["course_id"], b["lkey"], "syomka ko'chirildi", f"{b['start'][:16].replace('T', ' ')} → {_iso(t0)[:16].replace('T', ' ')} · {reason.strip()}",
             booking_id=b["id"]); _con.commit()
    _mw_invalidate()
    return {"ok": True, "booking": _bk_row(db.one(_con, "SELECT * FROM st_bookings WHERE id=?", (b["id"],)))}

def cancel(c: Ctx, bid: int, reason: str) -> dict:
    guard(c, "bandni bekor qilish", OPS + (TEACH,), f"band #{bid}")
    b = _booking(c, bid)
    if b["status"] != "band": raise HTTPException(409, "Faqat faol band bekor qilinadi")
    if len((reason or "").strip()) < 3: raise HTTPException(400, "Bekor qilish sababini yozing")
    with _lock:
        _con.execute("UPDATE st_bookings SET status='bekor', reason=?, updated_at=? WHERE id=?", (reason.strip()[:300], _iso(_now()), b["id"]))
        _log(c, b["course_id"], b["lkey"], "syomka bekor qilindi", reason.strip(), booking_id=b["id"]); _con.commit()
    _mw_invalidate()
    return {"ok": True}

def mark_done(c: Ctx, bid: int, status: str, note: str = "") -> dict:
    guard(c, "syomka natijasi", OPS, f"band #{bid} · {status}")
    b = _booking(c, bid)
    if status not in ("otdi", "kelmadi"): raise HTTPException(400, "Holat: otdi (syomka qilindi) yoki kelmadi")
    if b["status"] != "band": raise HTTPException(409, "Bu band allaqachon yopilgan")
    if _pdt(b["start"]) > _now() + dt.timedelta(hours=12): raise HTTPException(409, "Syomka vaqti hali kelmagan")
    with _lock:
        _con.execute("UPDATE st_bookings SET status=?, done_at=?, note=COALESCE(?, note), updated_at=? WHERE id=?",
                     (status, _iso(_now()), (note or "").strip()[:300] or None, _iso(_now()), b["id"]))
        _log(c, b["course_id"], b["lkey"], "syomka qilindi" if status == "otdi" else "o'qituvchi kelmadi", note, booking_id=b["id"]); _con.commit()
    _mw_invalidate()
    return {"ok": True}

def day_plan(c: Ctx, day: str = "", room_id: int = 0) -> dict:
    guard(c, "kun rejasi", OPS + (TEACH,), day)
    try: d = dt.date.fromisoformat(day) if day else _now().date()
    except ValueError: raise HTTPException(400, "Sana noto'g'ri")
    ops, tid, now = c.role.key in OPS, _tid(c), _now()
    rooms = [r for r in _rooms() if not room_id or r["id"] == int(room_id)]
    a, z = _iso(dt.datetime.combine(d, dt.time(0))), _iso(dt.datetime.combine(d + dt.timedelta(days=1), dt.time(0)))
    rows = db.rows(_con, """SELECT b.*, c.subject, c.direction, c.course, t.full_name teacher FROM st_bookings b JOIN dl_courses c ON c.id=b.course_id
                            LEFT JOIN teachers t ON t.id=b.teacher_id WHERE b.start<? AND b.end>? AND b.status!='bekor' ORDER BY b.start""", (z, a))
    titles = {}
    def les_title(r):
        k = (r["course_id"], r["lkey"])
        if k not in titles:
            try: titles[k] = _PK().lesson_info({"id": r["course_id"], "topics": (db.one(_con, "SELECT topics FROM dl_courses WHERE id=?", (r["course_id"],)) or {}).get("topics"),
                                                "subject": r["subject"]}, r["lkey"])
            except HTTPException: titles[k] = {"code": "?", "title": "(dars o'chirilgan)"}
        return titles[k]
    jobs = {}
    if ops and rows:
        w, a2 = _in({r["course_id"] for r in rows})
        for j in db.rows(_con, f"SELECT id, course_id, lkey, status, pct FROM st_jobs WHERE status!='bekor' AND {w} ORDER BY id", a2): jobs[(j["course_id"], j["lkey"])] = j
        raws = {(x["course_id"], x["lkey"]) for x in db.rows(_con, f"SELECT DISTINCT course_id, lkey FROM st_raw WHERE deleted=0 AND {w}", a2)}
    items = []
    for r in rows:
        mine = r["teacher_id"] == tid and c.role.key == TEACH
        if not ops and not mine:
            items.append({"id": None, "room_id": r["room_id"], "start": r["start"], "end": r["end"], "busy": True, "mine": False}); continue
        L = les_title(r)
        it = {**_bk_row(r), "busy": True, "mine": mine, "subject": r["subject"], "group": f"{r['direction'] or ''}, {r['course'] or ''}-kurs",
              "teacher": _short(r["teacher"] or ""), "code": L["code"], "title": L["title"], "past": _pdt(r["end"]) <= now}
        if ops:
            j = jobs.get((r["course_id"], r["lkey"]))
            it["job"] = {"id": j["id"], "status": j["status"], "status_label": JOB_ST.get(j["status"]), "pct": j["pct"]} if j else None
            it["has_raw"] = (r["course_id"], r["lkey"]) in raws
        items.append(it)
    out_rooms = []
    for rm in rooms:
        slots = []
        for s0, s1 in _grid_day(rm, d):
            occ = next((it for it in items if it["room_id"] == rm["id"] and it["start"] < _iso(s1) and it["end"] > _iso(s0)), None)
            slots.append({"start": _iso(s0), "end": _iso(s1), "free": occ is None and s0 > now, "past": s0 <= now, "booking": occ})
        out_rooms.append({"id": rm["id"], "name": rm["name"], "open_from": rm["open_from"], "open_to": rm["open_to"], "slot_min": rm["slot_min"],
                          "works": bool(slots), "slots": slots})
    return {"date": d.isoformat(), "rooms": out_rooms, "items": items, "ops": ops, "now": _iso(now)}

def my_bookings(c: Ctx) -> list[dict]:
    """O'qituvchi: o'z kelgusi (va bugungi) bandlari."""
    if c.role.key != TEACH: return []
    rows = db.rows(_con, """SELECT b.*, c.subject, r.name room FROM st_bookings b JOIN dl_courses c ON c.id=b.course_id LEFT JOIN st_rooms r ON r.id=b.room_id
                            WHERE c.teacher_id=? AND b.status='band' AND b.end>? ORDER BY b.start""", (_tid(c), _iso(_now() - dt.timedelta(hours=12))))
    out = []
    for r in rows:
        try: L = _PK().lesson_info({"id": r["course_id"], "topics": (db.one(_con, "SELECT topics FROM dl_courses WHERE id=?", (r["course_id"],)) or {}).get("topics"),
                                    "subject": r["subject"]}, r["lkey"])
        except HTTPException: continue
        out.append({**_bk_row(r), "subject": r["subject"], "room": r["room"], "code": L["code"], "title": L["title"]})
    return out


# =============================================================================================
# Xom video va montaj vazifalari (operator)
# =============================================================================================
def sniff_raw(head: bytes) -> str | None:
    """Xom video turi birinchi baytlardan: mp4 / mov (ISO BMFF, QuickTime), mkv / webm (Matroska EBML). Kengaytmaga ishonilmaydi."""
    if len(head) >= 12 and head[4:8] == b"ftyp":
        b = head[8:12]
        if b in (b"M4A ", b"M4B ", b"M4P "): return None
        return "mov" if b == b"qt  " else "mp4"
    if len(head) >= 8 and head[4:8] in (b"moov", b"mdat", b"wide", b"free", b"skip"): return "mov"
    if head[:4] == b"\x1a\x45\xdf\xa3":
        return "webm" if b"webm" in head[:64] else "mkv" if b"matroska" in head[:64] else None
    return None

async def _stream_raw(request: Request, limit: int) -> dict:
    """Xom video oqim bilan diskka — paket._stream_upload (o'sha 413 / 415 / 400 qoidalari), tur aniqlagichi sniff_raw, studiya tmp katalogida."""
    return await _stream_upload(request, limit, RAW_KINDS, "Xom video: .mp4, .mov, .mkv yoki .webm bo'lishi kerak", sniff=sniff_raw,
                                tmp_dir=store() / "tmp", prefix="raw_", too_big=f"Fayl hajmi {limit / 1024 ** 3:.0f} GB dan oshmasin")

def save_raw(c: Ctx, cid: int, lkey: int, up: dict, name: str, template: str = "", booking_id: int = 0) -> dict:
    try:
        co = _course(c, cid, write=True); les = _lesson(co, lkey)
        if template and template not in TEMPLATES: raise HTTPException(400, "Montaj shabloni noma'lum")
        d = store() / "raw" / str(co["id"]) / str(les["key"]); d.mkdir(parents=True, exist_ok=True)
        with _lock:
            rid = _con.execute("""INSERT INTO st_raw(course_id,lkey,booking_id,name,kind,path,size,sha256,ts,user_id,user_name) VALUES(?,?,?,?,?,'',?,?,?,?,?)""",
                               (co["id"], les["key"], booking_id or None, (name or "video")[:160], up["kind"], up["size"], up["sha256"], _iso(_now()),
                                c.user["id"], c.user["full_name"])).lastrowid
            fn = f"{rid}_{_ascii(Path(name or 'video').stem, 40)}.{up['kind']}"
            os.replace(up["path"], d / fn)
            _con.execute("UPDATE st_raw SET path=? WHERE id=?", (str(Path("raw") / str(co["id"]) / str(les["key"]) / fn), rid))
            # syomka qilingan (faol band vaqti kelgan bo'lsa) — avtomatik yopiladi
            b = db.one(_con, "SELECT * FROM st_bookings WHERE course_id=? AND lkey=? AND status='band' ORDER BY start LIMIT 1", (co["id"], les["key"]))
            if b and _pdt(b["start"]) <= _now() + dt.timedelta(hours=12):
                _con.execute("UPDATE st_bookings SET status='otdi', done_at=?, updated_at=? WHERE id=?", (_iso(_now()), _iso(_now()), b["id"]))
                _log(c, co["id"], les["key"], "syomka qilindi", "xom video yuklandi", booking_id=b["id"])
            _log(c, co["id"], les["key"], "xom video yuklandi", f"{name[:80]} · {up['kind']} · {up['size'] // (1024 * 1024)} MB"); _con.commit()
    finally:
        Path(up["path"]).unlink(missing_ok=True)
    rbac.audit(_con, c, "studiya: xom video yuklandi", RES, True, f"kurs #{cid} · {les['code']} · {up['size']} bayt")
    out = {"ok": True, "raw_id": rid, "kind": up["kind"], "size": up["size"], "job": None}
    if template: out["job"] = create_job(c, co["id"], les["key"], template, raw_id=rid)["job"]
    _mw_invalidate()
    return out

def _job_row(j: dict) -> dict:
    rep = {}
    try: rep = json.loads(j.get("report") or "{}") or {}
    except ValueError: pass
    files = {}
    try: files = json.loads(j.get("files") or "{}") or {}
    except ValueError: pass
    return {"id": j["id"], "course_id": j["course_id"], "lkey": j["lkey"], "raw_id": j["raw_id"], "template": j["template"],
            "template_label": TEMPLATES.get(j["template"], j["template"]), "status": j["status"], "status_label": JOB_ST.get(j["status"], j["status"]),
            "attempts": j["attempts"], "stage": j["stage"], "pct": j["pct"], "message": j["message"], "error": j["error"], "note": j["note"],
            "created_at": j["created_at"], "created_name": _short(j["created_name"]), "result_at": j["result_at"], "lease_until": j["lease_until"],
            "decided_at": j["decided_at"], "decided_name": _short(j["decided_name"]), "prev_id": j["prev_id"], "files": files,
            "report": rep if j["status"] in ("tayyor", "tasdiqlandi", "qayta") else None}

def create_job(c: Ctx, cid: int, lkey: int, template: str, raw_id: int = 0, note: str = "", prev_id: int = 0, redo_of: int = 0) -> dict:
    """Yangi montaj vazifasi. redo_of — «Qayta montaj»: eski vazifa «qayta» holatiga YANGI vazifa bilan BITTA tranzaksiyada (_lock ostida, hamma
    tekshiruvdan keyin) o'tadi — tekshiruv yiqilsa (xom video yo'q, montaj bajarilmoqda) ko'rib chiqilgan natija «tayyor» bo'lib qoladi."""
    guard(c, "montajga yuborish", OPS, f"kurs #{cid} · {lkey} · {template}")
    co = _course(c, cid, write=True); les = _lesson(co, lkey)
    if template not in TEMPLATES: raise HTTPException(400, "Montaj shabloni noma'lum")
    gone = []
    with _lock:
        raw = (db.one(_con, "SELECT * FROM st_raw WHERE id=? AND course_id=? AND lkey=? AND deleted=0", (raw_id, co["id"], les["key"])) if raw_id else
               db.one(_con, "SELECT * FROM st_raw WHERE course_id=? AND lkey=? AND deleted=0 ORDER BY id DESC LIMIT 1", (co["id"], les["key"])))
        if not raw or not (store() / raw["path"]).is_file(): raise HTTPException(409, "Avval xom videoni yuklang")
        if db.one(_con, "SELECT 1 x FROM st_jobs WHERE course_id=? AND lkey=? AND status='ishlanmoqda'", (co["id"], les["key"])):
            raise HTTPException(409, "Bu dars montaji hozir bajarilmoqda — tugashini kuting")
        now = _iso(_now())
        if redo_of:
            if _con.execute("""UPDATE st_jobs SET status='qayta', decided_at=?, decided_by=?, decided_name=?, updated_at=? WHERE id=? AND course_id=? AND lkey=?
                               AND status IN ('tayyor','operator')""", (now, c.user["id"], c.user["full_name"], now, redo_of, co["id"], les["key"])).rowcount != 1:
                raise HTTPException(409, "Qayta montaj — faqat tayyor yoki xatolik bergan vazifa uchun")
            _log(c, co["id"], les["key"], "qayta montajga qaytarildi", (note or "").strip(), job_id=redo_of)
        for o in db.rows(_con, "SELECT id FROM st_jobs WHERE course_id=? AND lkey=? AND status IN ('navbatda','operator','tayyor')", (co["id"], les["key"])):
            _con.execute("UPDATE st_jobs SET status='bekor', updated_at=? WHERE id=?", (now, o["id"])); gone.append(o["id"])
        jid = _con.execute("""INSERT INTO st_jobs(course_id,lkey,raw_id,template,status,attempts,note,created_at,created_by,created_name,updated_at,prev_id)
                              VALUES(?,?,?,?,'navbatda',0,?,?,?,?,?,?)""",
                           (co["id"], les["key"], raw["id"], template, (note or "").strip()[:500] or None, now, c.user["id"], c.user["full_name"], now,
                            prev_id or None)).lastrowid
        _log(c, co["id"], les["key"], "montajga yuborildi", f"{TEMPLATES[template]}{' · ' + note.strip() if note and note.strip() else ''}", job_id=jid); _con.commit()
    if gone: cleanup_lesson(co["id"], les["key"])            # almashtirilgan (bekor) vazifalar natijasi diskdan
    _mw_invalidate()
    return {"ok": True, "job": _job_row(db.one(_con, "SELECT * FROM st_jobs WHERE id=?", (jid,)))}

def _job(c: Ctx, jid: int) -> dict:
    j = db.one(_con, "SELECT * FROM st_jobs WHERE id=?", (int(jid),))
    if not j: raise HTTPException(404, "Montaj vazifasi topilmadi")
    return j

def jobs_list(c: Ctx, status: str = "") -> dict:
    guard(c, "montaj navbati", OPS, status)
    w, a = "1=1", []
    if status == "faol": w = "j.status IN ('navbatda','ishlanmoqda','tayyor','operator')"
    elif status in JOB_ST: w, a = "j.status=?", [status]
    rows = db.rows(_con, f"""SELECT j.*, c.subject, c.direction, c.course, c.topics, t.full_name teacher FROM st_jobs j JOIN dl_courses c ON c.id=j.course_id
                             LEFT JOIN teachers t ON t.id=c.teacher_id WHERE {w} ORDER BY CASE j.status WHEN 'tayyor' THEN 0 WHEN 'operator' THEN 1
                             WHEN 'ishlanmoqda' THEN 2 WHEN 'navbatda' THEN 3 ELSE 4 END, j.id DESC LIMIT 200""", a)
    out = []
    for j in rows:
        try: L = _PK().lesson_info({"id": j["course_id"], "topics": j["topics"], "subject": j["subject"]}, j["lkey"])
        except HTTPException: L = {"code": "?", "title": "(dars o'chirilgan)"}
        out.append({**_job_row(j), "subject": j["subject"], "teacher": _short(j["teacher"] or ""), "code": L["code"], "title": L["title"]})
    counts = {r["status"]: r["n"] for r in db.rows(_con, "SELECT status, COUNT(*) n FROM st_jobs GROUP BY status")}
    return {"items": out, "counts": counts, "templates": TEMPLATES, "worker": bool(worker_token())}

def job_detail(c: Ctx, jid: int) -> dict:
    guard(c, "montaj natijasi", OPS, f"#{jid}")
    j = _job(c, jid)
    co = _course(c, j["course_id"])
    try: L = _PK().lesson_info(co, j["lkey"])
    except HTTPException: L = {"code": "?", "title": "(dars o'chirilgan)"}
    d = _job_dir(j["id"])
    row = _job_row(j)
    row["media"] = {k: f"{P}/jobs/{j['id']}/media/{k}" for k, fn in (("video", "video.mp4"), ("thumb", "thumb.jpg"), ("captions", "captions.vtt")) if (d / fn).is_file()}
    raw = db.one(_con, "SELECT id, name, kind, size, ts FROM st_raw WHERE id=?", (j["raw_id"],))
    yt = db.one(_con, "SELECT * FROM st_yt WHERE job_id=? ORDER BY id DESC LIMIT 1", (j["id"],))
    return {"job": row, "lesson": {"course_id": co["id"], "lkey": j["lkey"], "code": L["code"], "title": L["title"], "subject": co["subject"],
                                   "teacher": _short(co.get("teacher") or "")}, "raw": raw, "youtube": _yt_row(yt) if yt else None,
            "yt_on": YT.configured()}

def _job_dir(jid: int) -> Path: return store() / "jobs" / str(int(jid))

def media(c: Ctx, jid: int, what: str, rng: str | None) -> Response:
    if what not in ("video", "thumb", "captions"): raise HTTPException(404, "Fayl yo'q")
    if c.role.key not in OPS or c.channel != "web" or not rng or rng.replace(" ", "").startswith("bytes=0-"):   # Range davomi audit qilinmaydi
        guard(c, "montaj natijasini ko'rish", OPS, f"#{jid} · {what}")
    j = _job(c, jid)
    f = _job_dir(j["id"]) / {"video": "video.mp4", "thumb": "thumb.jpg", "captions": "captions.vtt"}[what]
    if not f.is_file(): raise HTTPException(404, "Fayl yo'q")
    return serve_file(f, {"video": "video/mp4", "thumb": "image/jpeg", "captions": "text/vtt; charset=utf-8"}[what], rng)

def serve_file(f: Path, ct: str, rng: str | None, extra: dict | None = None) -> Response:
    """Diskdagi fayl HTTP Range bilan (206 + Content-Range; noto'g'ri oraliq — 416); xotiraga to'liq o'qilmaydi — paket.range_response."""
    return range_response(f, ct, rng, {"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff", **(extra or {})}, chunk=512 * 1024)

def approve(c: Ctx, jid: int) -> dict:
    """Tasdiqlash: holat _lock ostida atomar o'tadi (UPDATE … WHERE status='tayyor', rowcount == 1) — HAR QANDAY yon ta'sirdan (video darsga,
    YouTube navbati, paket) OLDIN; parallel ikkinchi tasdiq — 409, takroriy asset / YouTube qatori bo'lmaydi. Video qo'yilmasa — «tayyor»ga qaytadi."""
    guard(c, "montajni tasdiqlash", OPS, f"#{jid}")
    j = _job(c, jid); co = _course(c, j["course_id"]); les = _lesson(co, j["lkey"])
    if j["status"] != "tayyor": raise HTTPException(409, "Faqat ko'rib chiqish kutayotgan montaj tasdiqlanadi")
    d = _job_dir(j["id"])
    if not (d / "video.mp4").is_file(): raise HTTPException(410, "Montaj videosi diskda topilmadi")
    now = _iso(_now())
    with _lock:
        n = _con.execute("UPDATE st_jobs SET status='tasdiqlandi', decided_at=?, decided_by=?, decided_name=?, updated_at=? WHERE id=? AND status='tayyor'",
                         (now, c.user["id"], c.user["full_name"], now, j["id"])).rowcount
        _con.commit()
    if n != 1: raise HTTPException(409, "Bu montaj allaqachon tasdiqlangan yoki holati o'zgargan")
    try:
        cap = (d / "captions.vtt").read_bytes() if (d / "captions.vtt").is_file() else None
        thumb = (d / "thumb.jpg").read_bytes() if (d / "thumb.jpg").is_file() else None
        res = _PK().studio_set_video(c, co["id"], les["key"], d / "video.mp4", cap, thumb, name=f"{les['code']} studiya montaji #{j['id']}")
    except BaseException:
        with _lock:
            _con.execute("UPDATE st_jobs SET status='tayyor', decided_at=NULL, decided_by=NULL, decided_name=NULL, updated_at=? WHERE id=? AND status='tasdiqlandi'",
                         (_iso(_now()), j["id"])); _con.commit()
        raise
    yt_id, pkg = None, None
    with _lock:
        _log(c, co["id"], les["key"], "montaj tasdiqlandi", "video darsga qo'yildi (fayl)" + (f" · subtitr {res['captions']} yozuv" if res.get("captions") else ""), job_id=j["id"])
        if YT.configured():
            yt_id = _con.execute("""INSERT INTO st_yt(course_id,lkey,job_id,status,size,attempts,created_at,updated_at) VALUES(?,?,?,'navbatda',?,0,?,?)""",
                                 (co["id"], les["key"], j["id"], (d / "video.mp4").stat().st_size, _iso(_now()), _iso(_now()))).lastrowid
            _log(c, co["id"], les["key"], "YouTube navbatiga qo'yildi", job_id=j["id"])
        _con.commit()
    if not yt_id: pkg = auto_package(co["id"], les["key"])
    cleanup_lesson(co["id"], les["key"])                      # qayta montajga yuborilgan / almashtirilgan eski natijalar diskdan
    _mw_invalidate()
    return {"ok": True, "paket": res, "youtube": yt_id, "package": pkg, "state": states([co], {co["id"]: {les["key"]}})[0]}

def redo(c: Ctx, jid: int, note: str, template: str = "") -> dict:
    guard(c, "qayta montaj", OPS, f"#{jid}")
    j = _job(c, jid)
    if j["status"] not in ("tayyor", "operator"): raise HTTPException(409, "Qayta montaj — faqat tayyor yoki xatolik bergan vazifa uchun")
    if len((note or "").strip()) < 3: raise HTTPException(400, "Qayta montaj sababini yozing (ishchi uchun izoh)")
    # eski vazifa «qayta» holatiga yangisi bilan birga, tekshiruvlardan KEYIN o'tadi (create_job ichida, bitta tranzaksiya)
    return create_job(c, j["course_id"], j["lkey"], template or j["template"], raw_id=j["raw_id"], note=note, prev_id=j["id"], redo_of=j["id"])

def retry(c: Ctx, jid: int) -> dict:
    guard(c, "montajni qayta urinish", OPS, f"#{jid}")
    j = _job(c, jid)
    if j["status"] != "operator": raise HTTPException(409, "Faqat xatolik bergan vazifa qayta navbatga qo'yiladi")
    with _lock:
        _con.execute("UPDATE st_jobs SET status='navbatda', attempts=0, not_before=NULL, lease_until=NULL, updated_at=? WHERE id=?", (_iso(_now()), j["id"]))
        _log(c, j["course_id"], j["lkey"], "montaj qayta navbatga qo'yildi", j["error"] or "", job_id=j["id"]); _con.commit()
    _mw_invalidate()
    return {"ok": True}

def cancel_job(c: Ctx, jid: int) -> dict:
    guard(c, "montajni bekor qilish", OPS, f"#{jid}")
    j = _job(c, jid)
    if j["status"] not in ("navbatda", "operator", "tayyor"): raise HTTPException(409, "Bu vazifani bekor qilib bo'lmaydi")
    with _lock:
        if _con.execute("UPDATE st_jobs SET status='bekor', updated_at=? WHERE id=? AND status IN ('navbatda','operator','tayyor')",
                        (_iso(_now()), j["id"])).rowcount != 1:
            raise HTTPException(409, "Bu vazifani bekor qilib bo'lmaydi")
        _log(c, j["course_id"], j["lkey"], "montaj bekor qilindi", job_id=j["id"]); _con.commit()
    cleanup_lesson(j["course_id"], j["lkey"])                 # natija papkasi (va almashtirilgan xom video) diskdan
    _mw_invalidate()
    return {"ok": True}


# =============================================================================================
# Montaj ishchisi API — kontrakt docs/studio.md bilan AYNAN bir xil
# =============================================================================================
def worker_ctx() -> Ctx:
    return Ctx({"id": 0, "full_name": WORKER_NAME, "role": OPER}, rbac.ROLES[OPER], "worker")

def worker_auth(request: Request, action: str) -> Ctx:
    tok = worker_token()
    if not tok: raise HTTPException(503, "worker o'chiq")
    got = request.headers.get("x-worker-token") or ""
    wc = worker_ctx()
    if not hmac.compare_digest(got.encode("utf-8", "replace"), tok.encode("utf-8")):
        rbac.audit(_con, wc, f"montaj ishchisi: {action}", RES, False, "noto'g'ri X-Worker-Token")
        raise HTTPException(401, "Ishchi tokeni noto'g'ri")
    return wc

def _url_key() -> bytes:
    k = _meta("url_key")
    if not k:
        with _lock:
            _con.execute("INSERT OR IGNORE INTO st_meta(k,v) VALUES('url_key', ?)", (json.dumps(secrets.token_hex(32)),)); _con.commit()
        k = _meta("url_key")
    return bytes.fromhex(k)

def sign(jid: int, kind: str, exp: int | None = None, lease: str | None = None) -> str:
    """Imzolangan fayl havolasi: «jid.kind.exp[.lease].imzo». lease — claim'da berilgan identifikator: havola faqat SHU lease davomida ishlaydi
    (lease muddati o'tib vazifa boshqa ishchiga berilsa — eski havola 409)."""
    msg = f"{int(jid)}.{kind}.{int(exp or time.time() + URL_TTL)}" + (f".{lease}" if lease else "")
    return msg + "." + hmac.new(_url_key(), msg.encode(), hashlib.sha256).hexdigest()[:40]

def unsign(token: str) -> tuple[int, str, str | None]:
    """→ (jid, kind, lease | None). Lease'siz (eski) havola ham qabul qilinadi — imzo va muddat tekshiriladi."""
    bad = HTTPException(403, "Havola yaroqsiz yoki muddati o'tgan")
    m = re.fullmatch(r"(\d{1,10})\.(raw|slides|logo)\.(\d{1,12})(?:\.([0-9a-f]{16,64}))?\.([0-9a-f]{40})", token or "")
    if not m: raise bad
    msg = f"{m[1]}.{m[2]}.{m[3]}" + (f".{m[4]}" if m[4] else "")
    if not hmac.compare_digest(hmac.new(_url_key(), msg.encode(), hashlib.sha256).hexdigest()[:40], m[5]) or int(m[3]) < time.time(): raise bad
    return int(m[1]), m[2], m[4]

def _lease_hdr(request: Request) -> str:
    """X-Worker-Lease (claim javobidagi «lease»). Yo'q bo'lsa — eski ishchi: lease tekshirilmaydi (orqaga moslik)."""
    return (request.headers.get("x-worker-lease") or "").strip()[:64]

def _check_lease(j: dict, lease: str | None) -> None:
    if lease and not hmac.compare_digest(lease.encode("utf-8", "replace"), (j.get("lease") or "").encode()):
        raise HTTPException(409, "Lease eskirgan — vazifa boshqa ishchiga berilgan yoki qayta navbatga qo'yilgan (ishni to'xtating)")

def _base(request: Request) -> str:
    return (os.getenv("ISFT_CORE_PUBLIC_URL") or str(request.base_url)).rstrip("/")

def requeue_expired(now: dt.datetime | None = None) -> int:
    """Lease muddati o'tgan («ishlanmoqda», ishchi javob bermadi) — navbatga qaytadi (3-urinishdan keyin — operator)."""
    now, n = now or _now(), 0
    with _lock:
        for j in db.rows(_con, "SELECT * FROM st_jobs WHERE status='ishlanmoqda' AND lease_until<?", (_iso(now),)):
            st = "operator" if int(j["attempts"] or 0) >= MAX_ATTEMPTS else "navbatda"
            _con.execute("UPDATE st_jobs SET status=?, lease_until=NULL, lease=NULL, error=?, updated_at=? WHERE id=? AND status='ishlanmoqda'",
                         (st, "Ishchi javob bermadi (lease muddati o'tdi)", _iso(now), j["id"]))
            _log(None, j["course_id"], j["lkey"], "montaj lease muddati o'tdi", "operatorga" if st == "operator" else "navbatga qaytdi", job_id=j["id"], who=WORKER_NAME); n += 1
        if n: _con.commit()
    if n: _mw_invalidate()
    return n

def claim(request: Request) -> dict | None:
    """Navbatdagi birinchi vazifa. Dars ma'lumoti (paket.studio_lesson, taqdimot, logo) vazifa qulflanishidan OLDIN olinadi: olib bo'lmasa —
    vazifa «operator kerak» (aniq xato bilan), urinish va lease sarflanmaydi, keyingi vazifaga o'tiladi. Qulflash — atomar
    (UPDATE … WHERE status='navbatda'); har claim'da yangi lease identifikatori (javobda «lease», imzolangan havolalar ichida ham)."""
    wc = worker_auth(request, "claim")
    now = _now()
    requeue_expired(now)
    PK = _PK()
    while True:
        with _lock:
            j = db.one(_con, "SELECT * FROM st_jobs WHERE status='navbatda' AND (not_before IS NULL OR not_before<=?) ORDER BY id LIMIT 1", (_iso(now),))
            if not j: return None
            raw = db.one(_con, "SELECT * FROM st_raw WHERE id=?", (j["raw_id"],))
            if not raw or raw["deleted"] or not (store() / raw["path"]).is_file():
                _con.execute("UPDATE st_jobs SET status='operator', error=?, updated_at=? WHERE id=? AND status='navbatda'", ("Xom video fayli topilmadi", _iso(now), j["id"]))
                _con.commit()
                continue
        try:
            les = PK.studio_lesson(j["course_id"], j["lkey"])
            lesson = {k: les[k] for k in ("course_id", "no", "code", "kind", "title", "subject", "teacher", "plan")}
            has_slides, has_logo = bool(PK.studio_slides_pdf(j["course_id"], j["lkey"])), bool(PK.studio_logo())
        except Exception as e:
            why = str(e.detail) if isinstance(e, HTTPException) else type(e).__name__
            err = f"Dars ma'lumotini olib bo'lmadi: {why}"[:500]
            with _lock:
                if _con.execute("UPDATE st_jobs SET status='operator', error=?, lease_until=NULL, updated_at=? WHERE id=? AND status='navbatda'",
                                (err, _iso(now), j["id"])).rowcount:
                    _log(None, j["course_id"], j["lkey"], "montaj boshlanmadi", err + " · operator kerak", job_id=j["id"], who=WORKER_NAME)
                _con.commit()
            rbac.audit(_con, wc, "montaj ishchisi: claim — dars ma'lumoti yo'q", RES, True, f"#{j['id']} · {why[:120]}")
            _mw_invalidate()
            continue
        lease = secrets.token_hex(8)
        with _lock:
            if _con.execute("""UPDATE st_jobs SET status='ishlanmoqda', attempts=COALESCE(attempts,0)+1, lease=?, lease_until=?, claimed_at=?, stage='boshlandi',
                               pct=0, message=NULL, updated_at=? WHERE id=? AND status='navbatda'""",
                            (lease, _iso(now + dt.timedelta(seconds=LEASE)), _iso(now), _iso(now), j["id"])).rowcount != 1:
                _con.commit(); continue                       # boshqa so'rov oldinroq oldi / holat o'zgardi
            _log(None, j["course_id"], j["lkey"], "montaj boshlandi", f"{j['attempts'] + 1}-urinish · {TEMPLATES.get(j['template'], j['template'])}", job_id=j["id"], who=WORKER_NAME)
            _con.commit()
        break
    base = _base(request)
    f = lambda kind: f"{base}{W}/files/{sign(j['id'], kind, lease=lease)}"
    out = {"job_id": j["id"], "template": j["template"], "lesson": lesson, "lease": lease, "raw_url": f("raw"),
           "slides_url": f("slides") if has_slides else None, "logo_url": f("logo") if has_logo else None}
    if j.get("note"): out["note"] = j["note"]
    rbac.audit(_con, wc, "montaj ishchisi: claim", RES, True, f"#{j['id']} · kurs #{j['course_id']} · {lesson['code']} · {j['template']}")
    _mw_invalidate()
    return out

def worker_file(token: str, rng: str | None, lease_hdr: str = "") -> Response:
    jid, kind, lease = unsign(token)
    j = db.one(_con, "SELECT * FROM st_jobs WHERE id=?", (jid,))
    if not j or j["status"] != "ishlanmoqda": raise HTTPException(410, "Vazifa faol emas (lease tugagan yoki yakunlangan)")
    _check_lease(j, lease); _check_lease(j, lease_hdr)
    if kind == "raw":
        raw = db.one(_con, "SELECT * FROM st_raw WHERE id=?", (j["raw_id"],))
        f = store() / raw["path"] if raw else None
        ct = {"mp4": "video/mp4", "mov": "video/quicktime", "mkv": "video/x-matroska", "webm": "video/webm"}.get((raw or {}).get("kind"), "application/octet-stream")
    elif kind == "slides":
        f, ct = _PK().studio_slides_pdf(j["course_id"], j["lkey"]), "application/pdf"
    else:
        f = _PK().studio_logo(); ct = "image/png" if f and f.suffix.lower() == ".png" else "image/jpeg"
    if not f or not Path(f).is_file(): raise HTTPException(404, "Fayl topilmadi")
    if not rng or rng.replace(" ", "").startswith("bytes=0-"):
        rbac.audit(_con, worker_ctx(), f"montaj ishchisi: {kind} yuklab olindi", RES, True, f"#{jid}")
    return serve_file(Path(f), ct, rng)

def _active_job(jid: int, result: bool = False, lease: str | None = None) -> dict:
    """result=True — natija qayta yuborilsa (ishchi 5xx/uzilishda qayta urinadi, javob yo'qolgan bo'lishi mumkin): «tayyor» (hali ko'rilmagan)
    vazifaga ham qabul qilinadi — fayllar almashtiriladi (idempotent). lease (X-Worker-Lease) berilsa — joriy lease bilan mos bo'lishi shart (409)."""
    j = db.one(_con, "SELECT * FROM st_jobs WHERE id=?", (int(jid),))
    if not j: raise HTTPException(404, "Vazifa topilmadi")
    if j["status"] != "ishlanmoqda" and not (result and j["status"] == "tayyor"): raise HTTPException(409, f"Vazifa holati: {JOB_ST.get(j['status'], j['status'])} — faqat «ishlanmoqda» vazifaga yoziladi")
    _check_lease(j, lease)
    return j

def progress(request: Request, jid: int, stage: str, pct, message: str) -> dict:
    wc = worker_auth(request, "progress")
    with _lock:
        j = _active_job(jid, lease=_lease_hdr(request))
        try: p = max(0, min(100, int(float(pct or 0))))
        except (TypeError, ValueError): p = 0
        stg = re.sub(r"\s+", " ", str(stage or "")).strip()[:40] or None
        now = _now()
        _con.execute("UPDATE st_jobs SET stage=?, pct=?, message=?, lease_until=?, updated_at=? WHERE id=?",
                     (stg, p, re.sub(r"\s+", " ", str(message or "")).strip()[:300] or None, _iso(now + dt.timedelta(seconds=LEASE)), _iso(now), j["id"]))
        _con.commit()
    if stg != j["stage"]: rbac.audit(_con, wc, "montaj ishchisi: progress", RES, True, f"#{jid} · {stg} · {p}%")
    return {"ok": True, "lease_until": _iso(now + dt.timedelta(seconds=LEASE))}

STOP_ERROR = "Worker to'xtatildi yoki ish bekor qilindi"   # tools/montaj: SIGTERM / to'xtatish — urinish hisoblanmaydi

def fail(request: Request, jid: int, error: str) -> dict:
    wc = worker_auth(request, "fail")
    err = re.sub(r"\s+", " ", str(error or "")).strip()[:500] or "Noma'lum xato"
    stop = err == STOP_ERROR
    lease = _lease_hdr(request)
    with _lock:
        j = _active_job(jid, lease=lease)
        att = int(j["attempts"] or 0)
        if stop:                              # ishchi to'xtatildi — navbatga, urinish qaytariladi
            att = max(0, att - 1)
            _con.execute("UPDATE st_jobs SET status='navbatda', attempts=?, error=?, lease_until=NULL, lease=NULL, not_before=NULL, updated_at=? WHERE id=?",
                         (att, err, _iso(_now()), j["id"]))
            _log(None, j["course_id"], j["lkey"], "montaj to'xtatildi", "navbatga qaytdi (urinish hisoblanmadi)", job_id=j["id"], who=WORKER_NAME)
            _con.commit()
    if stop:
        rbac.audit(_con, wc, "montaj ishchisi: fail (to'xtatildi)", RES, True, f"#{jid}")
        _mw_invalidate()
        return {"ok": True, "status": "navbatda", "attempts": att, "retry": True}
    with _lock:
        j = _active_job(jid, lease=lease)
        att = int(j["attempts"] or 0)
        st = "operator" if att >= MAX_ATTEMPTS else "navbatda"
        nb = _iso(_now() + dt.timedelta(seconds=60 * att)) if st == "navbatda" else None
        _con.execute("UPDATE st_jobs SET status=?, error=?, lease_until=NULL, lease=NULL, not_before=?, updated_at=? WHERE id=?", (st, err, nb, _iso(_now()), j["id"]))
        _log(None, j["course_id"], j["lkey"], "montaj xatosi", f"{att}-urinish: {err}" + (" · operator kerak" if st == "operator" else " · qayta uriniladi"),
             job_id=j["id"], who=WORKER_NAME)
        _con.commit()
    rbac.audit(_con, wc, "montaj ishchisi: fail", RES, True, f"#{jid} · {att}-urinish · {err[:120]}")
    _mw_invalidate()
    return {"ok": True, "status": st, "attempts": att, "retry": st == "navbatda"}

# --- natija: multipart/form-data oqim bilan (python-multipart'siz) --------------------------------------------------------
async def stream_multipart(request: Request, limits: dict, d: Path) -> dict:
    """multipart/form-data → {maydon: {"path", "size", "sha256", "head", "filename"}}. Har maydon o'z chegarasi bilan (oshsa — 413 darhol),
    noma'lum yoki takroriy maydon — 400. Fayllar d ichida vaqtinchalik nom bilan; xatoda o'chiriladi."""
    ct = request.headers.get("content-type") or ""
    m = re.search(r'boundary="?([^";]{1,200})"?', ct)
    if not ct.lower().startswith("multipart/form-data") or not m: raise HTTPException(400, "multipart/form-data kutilmoqda")
    delim = b"--" + m.group(1).encode("latin-1")
    total_lim = sum(limits.values()) + 64 * 1024
    cl = request.headers.get("content-length")
    if cl and cl.isdigit() and int(cl) > total_lim: raise HTTPException(413, "So'rov hajmi chegaradan katta")
    d.mkdir(parents=True, exist_ok=True)
    parts, buf, state, cur, total = {}, b"", "pre", None, 0
    def close_cur():
        nonlocal cur
        if cur: cur["f"].close(); parts[cur["name"]] = {k: cur[k] for k in ("path", "size", "sha256", "head", "filename")}; cur = None
    try:
        async for chunk in request.stream():
            if not chunk: continue
            total += len(chunk)
            if total > total_lim: raise HTTPException(413, "So'rov hajmi chegaradan katta")
            buf += chunk
            while True:
                if state == "pre":
                    i = buf.find(delim)
                    if i < 0:
                        if len(buf) > 64 * 1024: raise HTTPException(400, "multipart chegarasi topilmadi")
                        break
                    buf, state = buf[i + len(delim):], "after"
                if state == "after":
                    if len(buf) < 2: break
                    if buf[:2] == b"--": state = "done"; buf = b""; break
                    if buf[:2] != b"\r\n": raise HTTPException(400, "multipart tuzilishi noto'g'ri")
                    buf, state = buf[2:], "hdr"
                if state == "hdr":
                    i = buf.find(b"\r\n\r\n")
                    if i < 0:
                        if len(buf) > 16 * 1024: raise HTTPException(400, "multipart sarlavhasi juda uzun")
                        break
                    hdr = buf[:i].decode("utf-8", "replace"); buf = buf[i + 4:]
                    cd = next((l for l in hdr.split("\r\n") if l.lower().startswith("content-disposition:")), "")
                    nm = re.search(r'\bname="([^"]*)"', cd); fnm = re.search(r'\bfilename="([^"]*)"', cd)
                    name = nm.group(1) if nm else ""
                    if name not in limits: raise HTTPException(400, f"Noma'lum maydon: {name[:40]}")
                    if name in parts: raise HTTPException(400, f"Takroriy maydon: {name}")
                    p = d / f".up_{name}_{secrets.token_hex(6)}"
                    cur = {"name": name, "path": p, "f": open(p, "wb"), "size": 0, "h": hashlib.sha256(), "head": b"", "filename": (fnm.group(1) if fnm else "")[:160]}
                    state = "body"
                if state == "body":
                    j = buf.find(b"\r\n" + delim)
                    take = buf[:j] if j >= 0 else buf[:max(0, len(buf) - (len(delim) + 2))]
                    if take:
                        cur["size"] += len(take)
                        if cur["size"] > limits[cur["name"]]:
                            raise HTTPException(413, f"«{cur['name']}» hajmi {limits[cur['name']] // (1024 * 1024)} MB dan oshmasin")
                        if len(cur["head"]) < 64: cur["head"] += take[:64 - len(cur["head"])]
                        cur["h"].update(take); cur["f"].write(take)
                    if j < 0:
                        buf = buf[len(take):]; break
                    cur["sha256"] = cur["h"].hexdigest(); close_cur()
                    buf, state = buf[j + 2 + len(delim):], "after"
                if state == "done": break
        if state != "done": raise HTTPException(400, "multipart oxiri topilmadi (yuklash uzildimi?)")
    except BaseException:
        if cur: cur["f"].close()
        for p in list(d.glob(".up_*")): p.unlink(missing_ok=True)
        raise
    return parts

def _num(v, lo=0.0, hi=24 * 3600.0) -> float:
    try: x = float(v)
    except (TypeError, ValueError): raise ValueError("raqam emas")
    if x != x or x < lo or x > hi: raise ValueError("chegaradan tashqari")
    return round(x, 3)

def clean_report(raw: bytes) -> dict:
    """Montaj hisoboti → me'yorlangan JSON. Noto'g'ri tuzilma — ValueError (o'zbekcha)."""
    try: d = json.loads(raw.decode("utf-8-sig"))
    except (UnicodeDecodeError, ValueError): raise ValueError("report — JSON emas")
    if not isinstance(d, dict): raise ValueError("report — JSON obyekt bo'lishi kerak")
    s = lambda v, n: re.sub(r"\s+", " ", str(v if v is not None else "")).strip()[:n]
    try:
        out = {"duration_in": _num(d.get("duration_in") or 0), "duration_out": _num(d.get("duration_out") or 0),
               "cuts": [{"start": _num(x["start"]), "end": _num(x["end"]), "reason": s(x.get("reason"), 120)} for x in (d.get("cuts") or [])[:5000]],
               "chapters": [{"start": _num(x["start"]), "title": s(x.get("title"), 100)} for x in (d.get("chapters") or [])[:300]],
               "slide_changes": [{"t": _num(x["t"]), "slide": None if x.get("slide") is None else int(x["slide"])} for x in (d.get("slide_changes") or [])[:3000]],
               "warnings": [s(x, 300) for x in (d.get("warnings") or [])[:100]]}
        tm = d.get("timings")                 # ixtiyoriy: ishchi bosqichlari vaqti (soniya)
        if isinstance(tm, dict):
            out["timings"] = {s(k, 40): _num(v, 0, 7 * 86400) for k, v in list(tm.items())[:40] if isinstance(v, (int, float))}
    except (KeyError, TypeError, AttributeError) as e:
        raise ValueError(f"report tuzilishi noto'g'ri ({type(e).__name__})")
    if any(x["end"] < x["start"] for x in out["cuts"]): raise ValueError("report: kesish oxiri boshidan oldin")
    out["cut_total"] = round(sum(x["end"] - x["start"] for x in out["cuts"]), 3)
    return out

async def result(request: Request, jid: int) -> dict:
    wc = worker_auth(request, "result")
    lease = _lease_hdr(request)
    _active_job(jid, result=True, lease=lease)                   # eskirgan lease — tana o'qilmasdan 409
    d = _job_dir(jid)
    up_dir = d / ".incoming"
    lim = {"video": result_max(), "captions": MAX_CAPTIONS, "thumbnail": MAX_THUMB, "report": MAX_REPORT}
    parts = await stream_multipart(request, lim, up_dir)
    try:
        miss = [k for k in ("video", "thumbnail", "report") if k not in parts or not parts[k]["size"]]
        if miss: raise HTTPException(400, "Majburiy maydon yo'q: " + ", ".join(miss))
        if sniff_raw(parts["video"]["head"]) != "mp4": raise HTTPException(415, "video — mp4 (ftyp) bo'lishi kerak")
        if parts["thumbnail"]["head"][:3] != b"\xff\xd8\xff": raise HTTPException(415, "thumbnail — JPEG bo'lishi kerak")
        try: rep = clean_report(Path(parts["report"]["path"]).read_bytes())
        except ValueError as e: raise HTTPException(400, str(e))
        warn = []
        cap_ok = False
        if "captions" in parts and parts["captions"]["size"]:
            try: _PK().to_vtt(Path(parts["captions"]["path"]).read_bytes()); cap_ok = True
            except HTTPException as e: warn.append(f"Subtitr qabul qilinmadi: {e.detail}")
        with _lock:
            j = _active_job(jid, result=True, lease=lease)   # yuklash davomida lease boshqa ishchiga o'tmaganmi
            for nm, fn in (("video", "video.mp4"), ("thumbnail", "thumb.jpg"), ("report", "report.json")):
                os.replace(parts[nm]["path"], d / fn)
            if cap_ok: os.replace(parts["captions"]["path"], d / "captions.vtt")
            else: (d / "captions.vtt").unlink(missing_ok=True)
            rep["warnings"] = (rep["warnings"] + warn)[:100]
            files = {"video": {"size": parts["video"]["size"], "sha256": parts["video"]["sha256"]}, "captions": cap_ok, "thumbnail": True}
            now = _iso(_now())
            _con.execute("""UPDATE st_jobs SET status='tayyor', stage='tayyor', pct=100, lease_until=NULL, report=?, files=?, result_at=?, error=NULL, updated_at=?
                            WHERE id=?""", (json.dumps(rep, ensure_ascii=False), json.dumps(files), now, now, j["id"]))
            dur = f"{int(rep['duration_in'] // 60)}:{int(rep['duration_in'] % 60):02d} → {int(rep['duration_out'] // 60)}:{int(rep['duration_out'] % 60):02d}"
            _log(None, j["course_id"], j["lkey"], "montaj tayyor — ko'rib chiqish kutmoqda", f"{dur} · {len(rep['cuts'])} ta kesish · {len(rep['chapters'])} ta bo'lim",
                 job_id=j["id"], who=WORKER_NAME)
            _con.commit()
    finally:
        shutil.rmtree(up_dir, ignore_errors=True)
    rbac.audit(_con, wc, "montaj ishchisi: result", RES, True, f"#{jid} · video {parts['video']['size']} bayt")
    _mw_invalidate()
    return {"ok": True, "status": "tayyor", "warnings": warn}


# =============================================================================================
# YouTube navbati (fon oqimi: tick())
# =============================================================================================
def _yt_row(y: dict | None) -> dict | None:
    if not y: return None
    return {"id": y["id"], "job_id": y["job_id"], "status": y["status"], "status_label": YT_ST.get(y["status"], y["status"]), "offset": y["offset"],
            "size": y["size"], "pct": round(100 * (y["offset"] or 0) / y["size"]) if y["size"] else 0, "video_id": y["video_id"],
            "url": f"https://youtu.be/{y['video_id']}" if y["video_id"] else None, "privacy": y["privacy"], "attempts": y["attempts"],
            "next_try": y["next_try"], "error": y["error"], "warning": y["warning"], "done_at": y["done_at"]}

def _yt_upd(yid: int, **kw) -> None:
    """Fon oqimidan ham chaqiriladi (poller → asyncio.to_thread) — umumiy ulanishga yozish faqat _lock ostida."""
    kw["updated_at"] = _iso(_now())
    with _lock:
        _con.execute(f"UPDATE st_yt SET {', '.join(k + '=?' for k in kw)} WHERE id=?", (*kw.values(), yid)); _con.commit()

def _yt_backoff(att: int) -> int: return min(3600, 30 * 2 ** att)

def yt_fallback(why: str = "") -> int:
    """YouTube o'chirildi (sirlar o'chirildi yoki ISFT_CORE_YT_OFF): yakunlanmagan navbat qatorlari «bekor» — darslar video FAYL bilan davom
    etadi (avtomatik paket), «ko'rib chiqishda» osilib qolmaydi. YouTube'ga yuklangan, lekin bog'lanmagan qatorlar tegilmaydi — havolani
    darsga qo'yish uchun YouTube API kerak emas (yt_tick ularni baribir qayta bog'laydi)."""
    why = why or "YouTube o'chirildi — dars video fayl bilan davom etadi"
    lessons = []
    with _lock:
        rows = db.rows(_con, f"SELECT * FROM st_yt WHERE status IN ({','.join('?' * (len(YT_OPEN) - 1))}) ORDER BY id",
                       tuple(x for x in YT_OPEN if x != "yuklandi_boglanmadi"))
        for y in rows:
            _con.execute("UPDATE st_yt SET status='bekor', next_try=NULL, error=?, updated_at=? WHERE id=?", (why, _iso(_now()), y["id"]))
            _log(None, y["course_id"], y["lkey"], "YouTube navbati bekor qilindi", why, job_id=y["job_id"], who="YouTube")
            if (y["course_id"], y["lkey"]) not in lessons: lessons.append((y["course_id"], y["lkey"]))
        if rows: _con.commit()
    for cid, lk in lessons: auto_package(cid, lk)
    if rows: _mw_invalidate()
    return len(rows)

def _next_quota(now: dt.datetime) -> dt.datetime:
    """YouTube kvotasi Tinch okeani vaqti bilan yarim tunda tiklanadi (Toshkentda ≈ 12:00–13:00) — keyingi 13:05."""
    t = now.replace(hour=13, minute=5, second=0)
    return t if t > now else t + dt.timedelta(days=1)

def yt_tick(now: dt.datetime | None = None, max_items: int = 3) -> list[dict]:
    """Muddati kelgan YouTube vazifalari (bittadan): yuklash (davom ettirish), holatni so'rash, yakunlash; yuklangan-u bog'lanmaganlarini
    qayta bog'lash (qayta yuklamasdan). Sozlanmagan / ISFT_CORE_YT_OFF bo'lsa — yakunlanmagan navbat «bekor» (yt_fallback), fayl video bilan."""
    if not _yt_lock.acquire(blocking=False): return []
    try:
        now = now or _now()
        on = YT.configured()
        if not on: yt_fallback()
        sts = (YT_ACTIVE if on else ()) + ("yuklandi_boglanmadi",)
        rows = db.rows(_con, f"""SELECT * FROM st_yt WHERE status IN ({','.join('?' * len(sts))}) AND (next_try IS NULL OR next_try<=?)
                                 AND (status!='yuklandi_boglanmadi' OR COALESCE(attempts,0)<?) ORDER BY id LIMIT ?""",
                         (*sts, _iso(now), YT_MAX_RETRY, int(max_items)))
        out = []
        for y in rows:
            try: out.append(_yt_process(y, now))
            except Exception as e:           # kutilmagan xato — navbat to'xtamasin; yuklangan video (video_id) hech qachon «xato» bilan yopilmaydi
                print("studio.yt:", type(e).__name__)
                out.append(_yt_unexpected(y["id"], e, now))
        return out
    finally:
        _yt_lock.release()

def _yt_unexpected(yid: int, e: Exception, now: dt.datetime) -> dict:
    cur = db.one(_con, "SELECT * FROM st_yt WHERE id=?", (yid,)) or {}
    msg = f"Ichki xato: {type(e).__name__}"
    if cur.get("status") in ("tayyor", "bekor"): return {"id": yid, "status": cur["status"]}       # muvaffaqiyatli natija ustidan yozilmaydi
    if cur.get("video_id"):                 # video YouTube'da bor — faqat qayta urinish (holat so'rash / bog'lash), qayta yuklash emas
        att = int(cur.get("attempts") or 0) + 1
        st = cur["status"] if att < YT_MAX_RETRY else "yuklandi_boglanmadi"
        _yt_upd(yid, status=st, attempts=att, error=msg, next_try=_iso(now + dt.timedelta(seconds=_yt_backoff(att))))
        return {"id": yid, "status": st, "error": msg}
    _yt_upd(yid, status="xato", error=msg)
    return {"id": yid, "status": "xato"}

def _yt_process(y: dict, now: dt.datetime) -> dict:
    PK = _PK()
    if y["status"] == "yuklandi_boglanmadi" and y["video_id"]:      # faqat qayta bog'lash — YouTube API'siz, qayta yuklamasdan
        return _yt_done(y, y["video_id"], y["privacy"], now)
    f = _job_dir(y["job_id"]) / "video.mp4"
    if not f.is_file():
        _yt_upd(y["id"], status="xato", error="Montaj videosi diskda topilmadi"); return {"id": y["id"], "status": "xato"}
    size = f.stat().st_size
    try:
        with YT.client() as cl:
            st, vid = y["status"], y["video_id"]
            if st in ("navbatda", "kutilmoqda", "yuklanmoqda"):
                session, offset, done = y["session_url"], 0, None
                if not session:
                    used = (db.one(_con, "SELECT COUNT(*) n FROM st_yt WHERE day=? AND id<>?", (now.date().isoformat(), y["id"])) or {}).get("n") or 0
                    if used >= YT.daily_cap():
                        nt = dt.datetime.combine(now.date() + dt.timedelta(days=1), dt.time(0, 10))
                        _yt_upd(y["id"], status="kutilmoqda", next_try=_iso(nt), error=f"Kunlik chegara ({YT.daily_cap()} ta yuklash) — ertaga davom etadi")
                        return {"id": y["id"], "status": "kutilmoqda"}
                    j = db.one(_con, "SELECT report FROM st_jobs WHERE id=?", (y["job_id"],)) or {}
                    try: chapters = (json.loads(j.get("report") or "{}") or {}).get("chapters") or []
                    except ValueError: chapters = []
                    meta = YT.metadata(PK.studio_lesson(y["course_id"], y["lkey"]), chapters)
                    session = YT.start_session(cl, meta, size)
                    _yt_upd(y["id"], session_url=session, offset=0, size=size, status="yuklanmoqda", day=now.date().isoformat(), error=None)
                    with _lock: _log(None, y["course_id"], y["lkey"], "YouTube yuklash boshlandi", meta["snippet"]["title"], job_id=y["job_id"], who="YouTube"); _con.commit()
                else:
                    offset, done = YT.query_offset(cl, session, size)
                if done is None:
                    done = YT.upload(cl, session, f, size, offset, on_chunk=lambda o: _yt_upd(y["id"], offset=o, status="yuklanmoqda"))
                vid = (done or {}).get("id")
                if not vid: raise YT.YTError("retry", "YouTube video identifikatorini qaytarmadi")
                pv = ((done or {}).get("status") or {}).get("privacyStatus")
                _yt_upd(y["id"], video_id=vid, status="ishlanmoqda", offset=size, privacy=pv, attempts=0, next_try=_iso(now + dt.timedelta(seconds=60)), error=None)
                with _lock: _log(None, y["course_id"], y["lkey"], "YouTube'ga yuklandi", f"https://youtu.be/{vid} · qayta ishlanmoqda", job_id=y["job_id"], who="YouTube"); _con.commit()
            s = YT.video_status(cl, vid)
            if not s:
                _yt_upd(y["id"], status="xato", error="Video YouTube'da topilmadi (o'chirilgan bo'lishi mumkin)"); return {"id": y["id"], "status": "xato"}
            sst = s.get("status") or {}
            us, pv = sst.get("uploadStatus"), sst.get("privacyStatus")
            if us == "processed":
                return _yt_done(y, vid, pv, now)
            if us in ("failed", "rejected", "deleted"):
                why = sst.get("failureReason") or sst.get("rejectionReason") or us
                _yt_upd(y["id"], status="xato", privacy=pv, error=f"YouTube videoni qabul qilmadi: {why}")
                return {"id": y["id"], "status": "xato"}
            _yt_upd(y["id"], status="ishlanmoqda", privacy=pv, next_try=_iso(now + dt.timedelta(seconds=60)))
            return {"id": y["id"], "status": "ishlanmoqda"}
    except YT.YTError as e:
        if e.kind == "quota":
            _yt_upd(y["id"], status="kutilmoqda", next_try=_iso(_next_quota(now)), error=e.message)
        elif e.kind == "retry":
            att = int(y["attempts"] or 0) + 1
            if att >= YT_MAX_RETRY: _yt_upd(y["id"], status="xato", attempts=att, error=e.message + f" ({att} marta urinildi)")
            else: _yt_upd(y["id"], attempts=att, next_try=_iso(now + dt.timedelta(seconds=_yt_backoff(att))), error=e.message)
        elif e.kind == "session":
            _yt_upd(y["id"], session_url=None, offset=0, status="navbatda", next_try=_iso(now), error=e.message, day=None)
        else:
            _yt_upd(y["id"], status="xato", error=e.message)
            if e.kind == "auth":
                with _lock: _set_meta("yt_error", {"ts": _iso(now), "error": e.message}); _con.commit()
        with _lock: _log(None, y["course_id"], y["lkey"], "YouTube xatosi", e.message, job_id=y["job_id"], who="YouTube"); _con.commit()
        _mw_invalidate()
        return {"id": y["id"], "status": "xato" if e.kind in ("auth", "fatal") else y["status"], "error": e.message, "kind": e.kind}

def _yt_done(y: dict, vid: str, pv: str | None, now: dt.datetime) -> dict:
    """YouTube «processed»: havola darsga (studio_set_youtube) → avtomatik paket → shundan KEYIN «tayyor». Bog'lash yiqilsa — «yuklandi_boglanmadi»
    (haqiqiy xato matni bilan, video_id saqlanadi): qayta urinish faqat bog'laydi, videoni qayta yuklamaydi."""
    url = f"https://youtu.be/{vid}"
    warn = None
    if pv == "private":
        warn = "YouTube videoni «private» qilib qo'ydi (tasdiqlanmagan ilova cheklovi) — talabalar ko'ra olmaydi; darsda video fayl qoldi"
    elif pv and pv != "unlisted":
        warn = f"Video maxfiyligi: {pv}"
    try:
        if pv != "private":
            _PK().studio_set_youtube(None, y["course_id"], y["lkey"], url)
        pkg = auto_package(y["course_id"], y["lkey"])
    except Exception as e:
        why = str(e.detail) if isinstance(e, HTTPException) else f"{type(e).__name__}: {e}"
        att = int(y.get("attempts") or 0) + 1
        err = f"Darsga bog'lanmadi: {why}"[:500]
        _yt_upd(y["id"], status="yuklandi_boglanmadi", video_id=vid, privacy=pv, warning=warn, error=err, attempts=att,
                next_try=_iso(now + dt.timedelta(seconds=_yt_backoff(att))))
        with _lock: _log(None, y["course_id"], y["lkey"], "YouTube'ga yuklandi — darsga bog'lanmadi", f"{url} · {why}"[:500], job_id=y["job_id"], who="YouTube"); _con.commit()
        _mw_invalidate()
        return {"id": y["id"], "status": "yuklandi_boglanmadi", "video_id": vid, "error": err}
    _yt_upd(y["id"], status="tayyor", video_id=vid, privacy=pv, done_at=_iso(now), warning=warn, error=None, next_try=None, attempts=0)
    with _lock: _set_meta("yt_error", None); _log(None, y["course_id"], y["lkey"], "YouTube'da tayyor", url + (f" · {warn}" if warn else ""), job_id=y["job_id"], who="YouTube"); _con.commit()
    cleanup_lesson(y["course_id"], y["lkey"])
    _mw_invalidate()
    return {"id": y["id"], "status": "tayyor", "video_id": vid, "warning": warn, "package": pkg}

def yt_retry(c: Ctx, yid: int) -> dict:
    guard(c, "YouTube qayta urinish", OPS, f"#{yid}")
    y = db.one(_con, "SELECT * FROM st_yt WHERE id=?", (int(yid),))
    if not y: raise HTTPException(404, "Topilmadi")
    if y["status"] not in ("xato", "kutilmoqda", "yuklandi_boglanmadi"): raise HTTPException(409, "Faqat xato yoki kutilayotgan yuklash qayta boshlanadi")
    st = "yuklandi_boglanmadi" if y["status"] == "yuklandi_boglanmadi" else "ishlanmoqda" if y["video_id"] else "navbatda"   # yuklangan — qayta yuklanmaydi
    with _lock:
        _con.execute("UPDATE st_yt SET status=?, attempts=0, next_try=NULL, error=NULL, updated_at=? WHERE id=?", (st, _iso(_now()), y["id"]))
        _log(c, y["course_id"], y["lkey"], "YouTube qayta navbatga qo'yildi", job_id=y["job_id"]); _con.commit()
    return {"ok": True}

def auto_package(cid: int, lkey: int) -> dict:
    """Avtomatik paket: matn va taqdimot bo'lsa — paket.build_topic (tizim nomidan); natija tarixga yoziladi. Xato oqimni to'xtatmaydi."""
    try:
        r = _PK().studio_build(cid, lkey)
    except HTTPException as e:
        note, out = f"Paket avtomatik tayyorlanmadi: {e.detail}", {"ok": False, "error": str(e.detail)}
    except Exception as e:
        note, out = f"Paket avtomatik tayyorlanmadi: {type(e).__name__}", {"ok": False, "error": type(e).__name__}
    else:
        if not r.get("ok") and r.get("missing"):
            nm = {"text": "ma'ruza matni", "slides": "taqdimot"}
            note, out = "Paket tayyorlanmadi: " + ", ".join(nm[m] for m in r["missing"]) + " yo'q", r
        else:
            p = r.get("package") or {}
            note = f"Paket avtomatik tayyorlandi: v{p.get('version')} · " + ({"tayyor": "tasdiq kutilmoqda", "qoralama": "qoralama"}.get(p.get("status"), p.get("status") or "")) \
                if not r.get("unchanged") else f"Paket o'zgarmagan (v{p.get('version')})"
            out = {"ok": True, "package_id": p.get("id"), "version": p.get("version"), "status": p.get("status"), "unchanged": bool(r.get("unchanged"))}
    with _lock: _log(None, cid, lkey, "avtomatik paket", note, who="Tizim"); _con.commit()
    return out

def tick() -> dict:
    return {"requeued": requeue_expired(), "youtube": yt_tick(), "swept": sweep()}


# =============================================================================================
# Disk tozalovi: bekor / almashtirilgan natijalar, saqlash muddati o'tgan xom videolar
# =============================================================================================
_last_sweep = 0.0

def _asset_files(cid: int, lkey: int) -> list[Path]:
    """Darsning faol paket fayllari (pk_assets, deleted=0) — tasdiqlangan montaj videosi ular bilan qattiq havola (bir xil inode)."""
    root = _PK().store()
    return [root / a["path"] for a in db.rows(_con, "SELECT path FROM pk_assets WHERE course_id=? AND topic_no=? AND deleted=0 AND path!=''", (cid, lkey))]

def _referenced(f: Path, refs: list[Path]) -> bool:
    """f biror faol asset bilan bir xil faylmi (qattiq havola — bir xil inode)? Havolalar soni > 1 bo'lsa-yu, egasi topilmasa ham — ehtiyot: ha
    (asset almashtirilib, uning fayli o'chirilgach havolalar soni 1 ga tushadi va keyingi tozalovda o'chiriladi)."""
    try: st = f.stat()
    except OSError: return False
    for r in refs:
        try:
            if os.path.samefile(f, r): return True
        except OSError: continue
    return st.st_nlink > 1

def _rm_file(f: Path, refs: list[Path]) -> bool:
    if not f.is_file() or _referenced(f, refs): return False
    f.unlink(missing_ok=True); return True

def _purge_job_dir(jid: int, refs: list[Path]) -> bool:
    """Vazifa natijasi papkasi o'chiriladi; faol asset bilan bog'langan (qattiq havola) fayl qoldiriladi."""
    d = _job_dir(jid)
    if not d.is_dir(): return False
    kept = False
    for f in sorted(d.rglob("*"), reverse=True):
        if f.is_file():
            if _referenced(f, refs): kept = True
            else: f.unlink(missing_ok=True)
    if not kept: shutil.rmtree(d, ignore_errors=True)
    return True

def cleanup_lesson(cid: int, lkey: int, now: dt.datetime | None = None) -> dict:
    """Bitta dars bo'yicha disk tozalovi (xato oqimni to'xtatmaydi):
      * «bekor» vazifa natijasi — darhol;  «qayta» (qayta montajga yuborilgan) — shu darsning YANGIROQ montaji tasdiqlangach;
      * eski «tasdiqlandi» natija — yangiroq montaj tasdiqlangan va uning YouTube navbati tugagan bo'lsa;
      * xom video — hech qaysi faol vazifa (navbatda/ishlanmoqda/operator/tayyor) ishlatmasa va: (a) darsning videosi tasdiqlanganiga
        ISFT_CORE_RAW_KEEP_DAYS (14) kun o'tgan bo'lsa yoki (b) darsga yangiroq xom video yuklangan, bu esa faqat bekor/qayta vazifalarda bo'lsa.
    Faol paket fayllariga (pk_assets) bog'langan fayllar (qattiq havola) hech qachon o'chirilmaydi."""
    now, out = now or _now(), {"jobs": 0, "raw": 0}
    try:
        jobs = db.rows(_con, "SELECT id, raw_id, status, decided_at FROM st_jobs WHERE course_id=? AND lkey=? ORDER BY id", (cid, lkey))
        raws = db.rows(_con, "SELECT * FROM st_raw WHERE course_id=? AND lkey=? AND deleted=0 ORDER BY id", (cid, lkey))
        appr = [j for j in jobs if j["status"] == "tasdiqlandi"]
        last = appr[-1] if appr else None
        yt_open = {y["job_id"] for y in db.rows(_con, f"SELECT job_id FROM st_yt WHERE course_id=? AND lkey=? AND status IN ({','.join('?' * len(YT_OPEN))})",
                                                 (cid, lkey, *YT_OPEN))}
        refs = _asset_files(cid, lkey)
        for j in jobs:
            gone = (j["status"] == "bekor" or (j["status"] == "qayta" and last and last["id"] > j["id"])
                    or (j["status"] == "tasdiqlandi" and j is not last and j["id"] not in yt_open and last["id"] not in yt_open))
            if gone and _purge_job_dir(j["id"], refs): out["jobs"] += 1
        busy = {j["raw_id"] for j in jobs if j["status"] in JOB_ACTIVE}
        keep_s = raw_keep_days() * 86400
        dec = _pdt(last["decided_at"]) if last else None
        for r in raws:
            if r["id"] in busy: continue
            used = [j for j in jobs if j["raw_id"] == r["id"]]
            aged = bool(dec and (r["id"] <= int(last["raw_id"] or 0) or (_pdt(r["ts"]) or now) <= dec) and (now - dec).total_seconds() >= keep_s)
            superseded = bool(used and all(j["status"] in ("bekor", "qayta") for j in used) and any(x["id"] > r["id"] for x in raws))
            if not (aged or superseded): continue
            f = store() / r["path"] if r["path"] else None
            if f and _referenced(f, refs): continue
            if f: f.unlink(missing_ok=True)
            with _lock:
                _con.execute("UPDATE st_raw SET deleted=2 WHERE id=? AND deleted=0", (r["id"],))
                _log(None, cid, lkey, "xom video diskdan o'chirildi", ("saqlash muddati o'tdi" if aged else "almashtirilgan") + f" · {r['name'][:80]}", who="Tizim")
                _con.commit()
            out["raw"] += 1
    except Exception as e:
        print("studio.cleanup:", type(e).__name__, e)
    return out

def sweep(now: dt.datetime | None = None, force: bool = False) -> dict:
    """Davriy (poller, soatiga bir marta) disk tozalovi — fayli bor barcha darslar bo'yicha cleanup_lesson."""
    global _last_sweep
    if not force and time.monotonic() - _last_sweep < SWEEP_S: return {}
    _last_sweep = time.monotonic()
    tot = {"jobs": 0, "raw": 0}
    keys = {(r["course_id"], r["lkey"]) for r in db.rows(_con, "SELECT DISTINCT course_id, lkey FROM st_raw WHERE deleted=0")}
    keys |= {(r["course_id"], r["lkey"]) for r in db.rows(_con, "SELECT DISTINCT course_id, lkey FROM st_jobs WHERE status IN ('bekor','qayta','tasdiqlandi')")}
    for cid, lk in sorted(keys):
        r = cleanup_lesson(cid, lk, now)
        for k in tot: tot[k] += r[k]
    return tot

async def poller():
    """Fon: har POLL_S soniyada lease muddati o'tgan montajlar va YouTube navbati (bo'lim o'chiq bo'lsa — hech narsa)."""
    from . import modules as MODS
    while True:
        await asyncio.sleep(POLL_S)
        try:
            if MODS.on("studio"): await asyncio.to_thread(tick)
        except Exception as e:
            print("studio.poller:", type(e).__name__)


# =============================================================================================
# Sozlamalar: xonalar, SLA, YouTube
# =============================================================================================
def settings(c: Ctx) -> dict:
    guard(c, "sozlamalar", ROOM_EDIT + (STAFF, IT))
    k = c.role.key
    out = {"rooms": _rooms(False) if k != IT else [], "sla": sla(), "stages": [{"key": s, "label": ST[s]["label"], "owner": OWNER_T.get(ST[s]["owner"], "")}
                                                                       for s in ORDER if s != "nextid"],
           "can": {"rooms": k in ROOM_EDIT, "sla": k == HEAD, "youtube": k in YT_ADMIN}, "slot_choices": list(SLOT_CHOICES),
           "worker": {"configured": bool(worker_token()), "raw_max_gb": round(raw_max() / 1024 ** 3, 2)}}
    if k in YT_ADMIN: out["youtube"] = yt_status()
    return out

def yt_status() -> dict:
    s = YT.status()
    s["used_today"] = (db.one(_con, "SELECT COUNT(*) n FROM st_yt WHERE day=?", (_now().date().isoformat(),)) or {}).get("n") or 0
    s["queue"] = {r["status"]: r["n"] for r in db.rows(_con, "SELECT status, COUNT(*) n FROM st_yt GROUP BY status")}
    s["last_error"] = _meta("yt_error")
    return s

def save_room(c: Ctx, b: dict) -> dict:
    guard(c, "studiya xonasi", ROOM_EDIT, str(b.get("name") or "")[:60])
    name = re.sub(r"\s+", " ", str(b.get("name") or "")).strip()[:60]
    a, z = str(b.get("open_from") or ""), str(b.get("open_to") or "")
    if not name: raise HTTPException(400, "Xona nomini yozing")
    if not (_HHMM.match(a) and _HHMM.match(z)) or a >= z: raise HTTPException(400, "Ish vaqti noto'g'ri (masalan 09:00 – 18:00)")
    try: slot = int(b.get("slot_min") or 0)
    except (TypeError, ValueError): slot = 0
    if slot not in SLOT_CHOICES: raise HTTPException(400, "Slot uzunligi: " + ", ".join(map(str, SLOT_CHOICES)) + " daqiqa")
    days = sorted({int(x) for x in re.findall(r"[1-7]", ",".join(map(str, b.get("days") or [])) if isinstance(b.get("days"), list) else str(b.get("days") or ""))})
    if not days: raise HTTPException(400, "Kamida bitta ish kuni tanlang")
    act = 1 if b.get("active", True) else 0
    with _lock:
        rid = int(b.get("id") or 0)
        if rid:
            if not db.one(_con, "SELECT 1 x FROM st_rooms WHERE id=?", (rid,)): raise HTTPException(404, "Xona topilmadi")
            if not act and db.one(_con, "SELECT 1 x FROM st_bookings WHERE room_id=? AND status='band' AND end>?", (rid, _iso(_now()))):
                raise HTTPException(409, "Bu xonada kelgusi bandlar bor — avval ko'chiring yoki bekor qiling")
            _con.execute("UPDATE st_rooms SET name=?, open_from=?, open_to=?, slot_min=?, days=?, active=?, updated_at=?, updated_by=? WHERE id=?",
                         (name, a, z, slot, ",".join(map(str, days)), act, _iso(_now()), c.user["full_name"], rid))
        else:
            rid = _con.execute("INSERT INTO st_rooms(name,open_from,open_to,slot_min,days,active,updated_at,updated_by) VALUES(?,?,?,?,?,?,?,?)",
                               (name, a, z, slot, ",".join(map(str, days)), act, _iso(_now()), c.user["full_name"])).lastrowid
        _con.commit()
    return {"ok": True, "rooms": _rooms(False)}

def save_sla(c: Ctx, vals: dict) -> dict:
    guard(c, "SLA muddatlari", (HEAD,))
    cur = _meta("sla", {}) or {}
    for k, v in (vals or {}).items():
        if k not in ST or k == "nextid": continue
        try: n = int(v)
        except (TypeError, ValueError): raise HTTPException(400, f"«{ST[k]['label']}»: kun soni noto'g'ri")
        if not 0 <= n <= 90: raise HTTPException(400, f"«{ST[k]['label']}»: 0–90 kun")
        cur[k] = n
    with _lock: _set_meta("sla", cur); _con.commit()
    _mw_invalidate()
    return {"ok": True, "sla": sla()}

def yt_save(c: Ctx, client_id: str, client_secret: str, refresh_token: str) -> dict:
    guard(c, "YouTube sozlamasi", YT_ADMIN)
    try: ch = YT.save(client_id, client_secret, refresh_token)
    except ValueError as e:
        rbac.audit(_con, c, "studiya: YouTube sozlamasi rad etildi", RES, False, str(e)[:120])
        raise HTTPException(400, str(e))
    rbac.audit(_con, c, "studiya: YouTube sozlamasi saqlandi", RES, True, "o'zgargan: " + (", ".join(ch) or "hech narsa"))
    with _lock: _set_meta("yt_error", None); _con.commit()
    return {"ok": True, "changed": ch, "youtube": yt_status()}

def yt_clear(c: Ctx) -> dict:
    guard(c, "YouTube sozlamasini o'chirish", YT_ADMIN)
    YT.clear()
    rbac.audit(_con, c, "studiya: YouTube sozlamasi o'chirildi", RES, True, "")
    yt_fallback("YouTube sozlamasi o'chirildi — dars video fayl bilan davom etadi")
    return {"ok": True, "youtube": yt_status()}

def yt_test(c: Ctx) -> dict:
    guard(c, "YouTube ulanishini tekshirish", YT_ADMIN)
    if not YT.configured(): raise HTTPException(409, "Avval client id, client secret va refresh token kiriting")
    try:
        with YT.client() as cl: r = YT.channel(cl)
    except YT.YTError as e:
        if e.kind == "auth":
            with _lock: _set_meta("yt_error", {"ts": _iso(_now()), "error": e.message}); _con.commit()
        raise HTTPException(502, e.message)
    with _lock: _set_meta("yt_error", None); _con.commit()
    return r


# =============================================================================================
# Meta, «Mening vazifalarim», «Bugun»
# =============================================================================================
TABS = {HEAD: ["holat", "kun", "montaj", "darslar", "sozlama"], STAFF: ["holat", "kun", "montaj", "darslar"],
        OPER: ["kun", "montaj", "darslar", "holat", "sozlama"], "rektor": ["holat"], "prorektor_oquv": ["holat"], TEACH: ["darslar"], IT: ["sozlama"]}
TAB_T = {"holat": "Holat", "kun": "Kun rejasi", "montaj": "Montaj", "darslar": "Darslar", "sozlama": "Sozlamalar"}

def meta(c: Ctx) -> dict:
    guard(c, "ochish", ALL)
    k = c.role.key
    tl = dict(TAB_T)
    if k == TEACH: tl["darslar"] = "Mening darslarim"
    return {"role": k, "tabs": TABS[k], "tab_labels": tl, "templates": TEMPLATES, "stages": [{"key": s, "label": ST[s]["label"]} for s in ORDER],
            "rooms": [{"id": r["id"], "name": r["name"], "open_from": r["open_from"], "open_to": r["open_to"], "slot_min": r["slot_min"], "days": r["days"]}
                      for r in _rooms()] if k != IT else [],
            "caps": {"ops": k in OPS, "dept": k in DEPT, "teacher": k == TEACH, "board": k in BOARD, "aggregate": k in LEAD, "plan": k in DEPT,
                     "nextid": k in DEPT, "review": k in OPS},
            "yt_on": YT.configured(), "worker_on": bool(worker_token()), "today": _now().date().isoformat(), "now": _iso(_now()),
            "limits": {"raw_gb": round(raw_max() / 1024 ** 3, 2)}, "my_bookings": my_bookings(c) if k == TEACH else []}

def _red_items(c: Ctx, I, owner: str, S: list[dict]) -> list:
    red = [s for s in S if s["over"] and s["owner"] == owner]
    if not red: return []
    tab = {TEACH: "darslar", OPER: "montaj", HEAD: "holat"}[owner]
    if len(red) <= 5:
        return [I("studio", "muddat", f"st-r{s['course_id']}-{s['lkey']}", f"Studiya: {s['code']} «{s['title']}» — {s['label'].lower()}, muddati o'tgan",
                  f"{s['subject']} · {s['next']} · {s['days_over']} kun kechikdi", s["due"], {"view": "studio", "tab": tab}, "menga" if owner == TEACH else "bolimga",
                  "muddati o'tgan", "high", icon="alert") for s in red]
    first = min(s["due"] for s in red)
    return [I("studio", "muddat", f"st-red-{owner}", f"Dars ishlab chiqarish: {len(red)} ta dars muddati o'tgan",
              " · ".join(sorted({s['label'] for s in red}))[:160], first, {"view": "studio", "tab": tab}, "bolimga", "muddati o'tgan", "high", len(red), icon="alert")]

def mywork_items(c: Ctx, I) -> list:
    """«Mening vazifalarim» (app/pending.py): syomka eslatmalari (bir kun oldin, bugun, 1 soat oldin), ko'rik navbati, montaj/YouTube xatolari,
    muddati o'tgan darslar — faqat shu bosqich egasiga."""
    k = c.role.key
    if k not in OPS + (TEACH,): return []
    now, out = _now(), []
    tmr = now.date() + dt.timedelta(days=1)
    hz = _iso(dt.datetime.combine(tmr + dt.timedelta(days=1), dt.time(0)))
    if k == TEACH:
        rows = db.rows(_con, """SELECT b.*, c.subject, c.topics, r.name room FROM st_bookings b JOIN dl_courses c ON c.id=b.course_id LEFT JOIN st_rooms r ON r.id=b.room_id
                                WHERE c.teacher_id=? AND b.status='band' AND b.start>? AND b.start<? ORDER BY b.start""", (_tid(c), _iso(now), hz))
        cos = db.rows(_con, "SELECT c.*, d.name dept, t.full_name teacher FROM dl_courses c LEFT JOIN departments d ON d.id=c.department_id "
                            "LEFT JOIN teachers t ON t.id=c.teacher_id WHERE c.teacher_id=?", (_tid(c),))
    else:
        rows = db.rows(_con, """SELECT b.*, c.subject, c.topics, r.name room, t.full_name teacher FROM st_bookings b JOIN dl_courses c ON c.id=b.course_id
                                LEFT JOIN st_rooms r ON r.id=b.room_id LEFT JOIN teachers t ON t.id=b.teacher_id
                                WHERE b.status='band' AND b.start>? AND b.start<? ORDER BY b.start""", (_iso(now), hz))
        cos = _courses(tracked_courses())
    soon = [r for r in rows if _pdt(r["start"]) - now <= dt.timedelta(hours=1)]
    for r in rows:
        t0 = _pdt(r["start"])
        try: L = _PK().lesson_info({"id": r["course_id"], "topics": r["topics"], "subject": r["subject"]}, r["lkey"])
        except HTTPException: continue
        hh = r["start"][11:16]
        if t0 - now <= dt.timedelta(hours=1): ttl, prio = f"1 soatdan keyin syomka: {L['code']} «{L['title']}» — soat {hh}", "high"
        elif t0.date() == now.date(): ttl, prio = f"Bugun syomka: {L['code']} «{L['title']}» — soat {hh}", "mid"
        else: ttl, prio = f"Ertaga syomka: {L['code']} «{L['title']}» — soat {hh}", "mid"
        if k != TEACH and r not in soon and len(rows) > 5: continue
        sub = " · ".join(x for x in [r["subject"], r["room"], _short(r.get("teacher") or "") if k != TEACH else "slayd va ma'ruza matnini olib keling"] if x)
        out.append(I("studio", "syomka", f"st-b{r['id']}", ttl, sub, r["start"], {"view": "studio", "tab": "darslar" if k == TEACH else "kun"},
                     "menga" if k == TEACH else "bolimga", "band", prio, icon="clock"))
    if k != TEACH and len(rows) > 5:
        rest = [r for r in rows if r not in soon]
        if rest:
            out.append(I("studio", "syomka", "st-day", f"Studiya: {len(rest)} ta syomka (bugun va ertaga)", "Kun rejasini oching", rest[0]["start"],
                         {"view": "studio", "tab": "kun"}, "bolimga", "", "mid", len(rest), icon="clock"))
    if k in OPS:
        n = db.rows(_con, "SELECT id, result_at FROM st_jobs WHERE status='tayyor' ORDER BY result_at")
        if n and k in (OPER,) + DEPT:
            out.append(I("studio", "montaj", "st-rev", f"Montaj tayyor — ko'rib chiqing: {len(n)} ta", "AI montaj natijasi: tasdiqlash yoki qayta montaj",
                         _iso(_pdt(n[0]["result_at"]) + dt.timedelta(days=sla()["korib"])) if n[0]["result_at"] else None, {"view": "studio", "tab": "montaj"},
                         "bolimga", "tayyor", "mid", len(n), icon="video"))
        for j in db.rows(_con, "SELECT * FROM st_jobs WHERE status='operator' ORDER BY id LIMIT 5"):
            out.append(I("studio", "montaj", f"st-op{j['id']}", f"Montaj xatosi (#{j['id']}) — operator kerak", (j["error"] or "")[:160], None,
                         {"view": "studio", "tab": "montaj"}, "bolimga", "xato", "high", icon="alert"))
        for y in db.rows(_con, "SELECT * FROM st_yt WHERE status IN ('xato','yuklandi_boglanmadi') ORDER BY id DESC LIMIT 5"):
            out.append(I("studio", "youtube", f"st-yt{y['id']}", "YouTube'ga yuklashda xato" if y["status"] == "xato" else "YouTube videosi darsga bog'lanmadi",
                         (y["error"] or "")[:160], None,
                         {"view": "studio", "tab": "montaj"}, "bolimga", "xato", "high", icon="alert"))
    S = states(cos)
    if k == TEACH: out += _red_items(c, I, TEACH, S)
    elif k == OPER: out += _red_items(c, I, OPER, S)
    elif k in DEPT: out += _red_items(c, I, HEAD, S)
    return out

def bugun(c: Ctx) -> list[dict]:
    """Operator bosh sahifasi: 4 ta ko'rsatkich."""
    if c.role.key != OPER: return []
    now = _now()
    a, z = _iso(dt.datetime.combine(now.date(), dt.time(0))), _iso(dt.datetime.combine(now.date() + dt.timedelta(days=1), dt.time(0)))
    today = (db.one(_con, "SELECT COUNT(*) n FROM st_bookings WHERE status IN ('band','otdi') AND start>=? AND start<?", (a, z)) or {}).get("n") or 0
    left = (db.one(_con, "SELECT COUNT(*) n FROM st_bookings WHERE status='band' AND start>=? AND start<?", (_iso(now), z)) or {}).get("n") or 0
    q = {r["status"]: r["n"] for r in db.rows(_con, "SELECT status, COUNT(*) n FROM st_jobs WHERE status IN ('navbatda','ishlanmoqda','tayyor','operator') GROUP BY status")}
    S = [s for s in states(_courses(tracked_courses())) if s["tracked"]]
    red = sum(1 for s in S if s["over"] and s["owner"] == OPER)
    L = lambda tab: {"view": "studio", "tab": tab}
    return [{"label": "Bugungi syomkalar", "value": today, "sub": f"yana {left} ta oldinda", "tone": "", "link": L("kun")},
            {"label": "Montaj navbatida", "value": q.get("navbatda", 0) + q.get("ishlanmoqda", 0), "sub": f"xato: {q.get('operator', 0)}",
             "tone": "bad" if q.get("operator") else "", "link": L("montaj")},
            {"label": "Ko'rib chiqish kutmoqda", "value": q.get("tayyor", 0), "sub": "AI montaj natijasi", "tone": "warn" if q.get("tayyor") else "", "link": L("montaj")},
            {"label": "Muddati o'tgan", "value": red, "sub": "studiya bosqichlarida", "tone": "bad" if red else "good", "link": L("darslar")}]


# =============================================================================================
# HTTP — ilova (sessiya)
# =============================================================================================
class BookIn(BaseModel):
    course_id: int
    lkey: int
    room_id: int = 0
    start: str
    note: str = ""

class MoveIn(BaseModel):
    start: str
    reason: str = ""
    room_id: int = 0

class ReasonIn(BaseModel):
    reason: str = ""

class DoneIn(BaseModel):
    status: str = "otdi"
    note: str = ""

class JobIn(BaseModel):
    template: str
    raw_id: int = 0
    note: str = ""

class RedoIn(BaseModel):
    note: str = ""
    template: str = ""

class PlanIn(BaseModel):
    course_id: int
    on: bool = True

class NextIn(BaseModel):
    undo: bool = False

class SlaIn(BaseModel):
    sla: dict

class YtIn(BaseModel):
    client_id: str = ""
    client_secret: str = ""
    refresh_token: str = ""

@router.get(P + "/meta")
def api_meta(request: Request): return meta(C(request))

@router.get(P + "/board")
def api_board(request: Request, group: str = "course"): return board(C(request), group)

@router.get(P + "/kpi")
def api_kpi(request: Request): return kpi(C(request))

@router.get(P + "/lessons")
def api_lessons(request: Request, course_id: int = 0): return lessons_list(C(request), course_id)

@router.get(P + "/lessons/{cid}/{lkey}")
def api_lesson(cid: int, lkey: int, request: Request): return lesson_detail(C(request), cid, lkey)

@router.post(P + "/lessons/{cid}/{lkey}/raw")
async def api_raw(cid: int, lkey: int, request: Request, name: str = "video", template: str = "", booking_id: int = 0):
    c = C(request)
    guard(c, "xom video yuklash", OPS, f"kurs #{cid} · {lkey}")
    _lesson(_course(c, cid, write=True), lkey)              # kurs, ruxsat va dars (mavjud, L/A) — tana o'qilishidan OLDIN (aks holda GB'lab behuda)
    if template and template not in TEMPLATES: raise HTTPException(400, "Montaj shabloni noma'lum")
    up = await _stream_raw(request, raw_max())
    return save_raw(c, cid, lkey, up, name, template, booking_id)

@router.post(P + "/lessons/{cid}/{lkey}/jobs")
def api_job_new(cid: int, lkey: int, body: JobIn, request: Request): return create_job(C(request), cid, lkey, body.template, body.raw_id, body.note)

@router.post(P + "/lessons/{cid}/{lkey}/nextid")
def api_nextid(cid: int, lkey: int, body: NextIn, request: Request): return mark_nextid(C(request), cid, lkey, body.undo)

@router.get(P + "/courses")
def api_courses(request: Request, q: str = ""): return {"items": course_search(C(request), q)}

@router.post(P + "/plan")
def api_plan(body: PlanIn, request: Request): return set_plan(C(request), body.course_id, body.on)

@router.get(P + "/day")
def api_day(request: Request, date: str = "", room_id: int = 0): return day_plan(C(request), date, room_id)

@router.post(P + "/bookings")
def api_book(body: BookIn, request: Request): return book(C(request), body.course_id, body.lkey, body.room_id, body.start, body.note)

@router.post(P + "/bookings/{bid}/move")
def api_move(bid: int, body: MoveIn, request: Request): return move(C(request), bid, body.start, body.reason, body.room_id)

@router.post(P + "/bookings/{bid}/cancel")
def api_cancel(bid: int, body: ReasonIn, request: Request): return cancel(C(request), bid, body.reason)

@router.post(P + "/bookings/{bid}/done")
def api_done(bid: int, body: DoneIn, request: Request): return mark_done(C(request), bid, body.status, body.note)

@router.get(P + "/jobs")
def api_jobs(request: Request, status: str = "faol"): return jobs_list(C(request), status)

@router.get(P + "/jobs/{jid}")
def api_job(jid: int, request: Request): return job_detail(C(request), jid)

@router.get(P + "/jobs/{jid}/media/{what}")
def api_media(jid: int, what: str, request: Request): return media(C(request), jid, what, request.headers.get("range"))

@router.post(P + "/jobs/{jid}/approve")
def api_approve(jid: int, request: Request): return approve(C(request), jid)

@router.post(P + "/jobs/{jid}/redo")
def api_redo(jid: int, body: RedoIn, request: Request): return redo(C(request), jid, body.note, body.template)

@router.post(P + "/jobs/{jid}/retry")
def api_retry(jid: int, request: Request): return retry(C(request), jid)

@router.post(P + "/jobs/{jid}/cancel")
def api_job_cancel(jid: int, request: Request): return cancel_job(C(request), jid)

@router.post(P + "/youtube/{yid}/retry")
def api_yt_retry(yid: int, request: Request): return yt_retry(C(request), yid)

@router.get(P + "/settings")
def api_settings(request: Request): return settings(C(request))

@router.post(P + "/rooms")
async def api_room(request: Request):
    try: b = await request.json()
    except ValueError: raise HTTPException(400, "JSON kutilmoqda")
    if not isinstance(b, dict): raise HTTPException(400, "JSON obyekt kutilmoqda")
    return save_room(C(request), b)

@router.post(P + "/sla")
def api_sla(body: SlaIn, request: Request): return save_sla(C(request), body.sla)

@router.get(P + "/youtube")
def api_yt(request: Request):
    c = C(request); guard(c, "YouTube holati", YT_ADMIN)
    return yt_status()

@router.post(P + "/youtube")
def api_yt_save(body: YtIn, request: Request): return yt_save(C(request), body.client_id, body.client_secret, body.refresh_token)

@router.post(P + "/youtube/clear")
def api_yt_clear(request: Request): return yt_clear(C(request))

@router.post(P + "/youtube/test")
def api_yt_test(request: Request): return yt_test(C(request))


# =============================================================================================
# HTTP — montaj ishchisi (X-Worker-Token; sessiya cookie kerak emas)
# =============================================================================================
async def _wbody(request: Request) -> dict:
    try: b = await request.json()
    except ValueError: raise HTTPException(400, "JSON kutilmoqda")
    if not isinstance(b, dict): raise HTTPException(400, "JSON obyekt kutilmoqda")
    return b

@router.post(W + "/jobs/claim")
def api_w_claim(request: Request):
    r = claim(request)
    return r if r is not None else Response(status_code=204)

@router.get(W + "/files/{token}")
def api_w_file(token: str, request: Request): return worker_file(token, request.headers.get("range"), _lease_hdr(request))

@router.post(W + "/jobs/{jid}/progress")
async def api_w_progress(jid: int, request: Request):
    worker_auth(request, "progress")              # token tanadan oldin tekshiriladi (503 / 401)
    b = await _wbody(request)
    return progress(request, jid, b.get("stage"), b.get("pct"), b.get("message"))

@router.post(W + "/jobs/{jid}/result")
async def api_w_result(jid: int, request: Request): return await result(request, jid)

@router.post(W + "/jobs/{jid}/fail")
async def api_w_fail(jid: int, request: Request):
    worker_auth(request, "fail")
    b = await _wbody(request)
    return fail(request, jid, b.get("error"))
