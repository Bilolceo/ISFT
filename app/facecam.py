"""Kirish nazorati (Face ID): bino kirishlaridagi kameralar kim kirgani/chiqqanini qayd etadi — faqat yozma roziligi bor shaxslar.

Qanday ishlaydi (haqiqiy kamera):
  1. Yozma rozilik (ZRU-547 "Shaxsga doir ma'lumotlar to'g'risida"gi Qonun: biometrik ma'lumot — alohida yozma rozilik) olingach,
     shaxsga tasodifiy FPID beriladi (face_persons). Kameraning yuz kutubxonasiga (FDLib) faqat FPID + yuz rasmi yuboriladi — ism emas
     (hikvision.HikClient.fdlib_*; navbat — face_sync jadvali). Rozilik qaytarib olinsa: FPID o'chiriladi, kameradagi yozuv o'chiriladi,
     o'tgan voqealar shaxssizlantiriladi.
  2. DeepinView kamera yuzni O'ZI solishtiradi va alertStream orqali `alarmResult` yuboradi: FPID, o'xshashlik, yuz ramkasi, fon rasmi
     manzili. Serverda ML model yo'q: hikvision.parse_json_alert → camsec.process_event → ingest() (shu fayl).
  3. FPID bazada topilmasa yoki rozilik yo'q — "Notanish shaxs"; o'xshashlik < ISFT_CORE_FACE_MATCH_MIN — "Past ishonch" (tasdiqlanmagan).
  4. Fon rasmi faqat kirish kameralaridan, ko'pi bilan ISFT_CORE_FACE_KEEP_DAYS (7) kun saqlanadi (data/face_snaps/, startda tozalanadi);
     voqea metama'lumoti — ISFT_CORE_FACE_EVENTS_DAYS (90) kun.
Demo: tasvirlar SINTETIK (app/facecam_render.py — kadr `seed` bo'yicha har safar qayta chiziladi, saqlanmaydi), voqealar app/seed_facecam.py.

Kim nimani ko'radi (ACCESS): rektor va xo'jalik bo'limi — hammasi; kadrlar — o'qituvchi va xodimlar (punktuallik);
fakultet tyutori — faqat o'z fakulteti talabalari (institutda dekan lavozimi yo'q); AT bo'limi — kamera va kutubxona holati (faqat sonlar); kuzatuv kengashi — jamlangan
ko'rsatkichlar (rasm va ismsiz). Boshqalar — 403. Ko'lamdan tashqari yuzlar rasmda pikselga aylantiriladi. Har ko'rish — audit ("face").
"""
import asyncio, datetime as dt, json, os, random, re, threading, time
from collections import Counter, OrderedDict, defaultdict
from pathlib import Path
from fastapi import APIRouter, Request, HTTPException, Response
from pydantic import BaseModel, Field
from . import clock
from . import db, rbac, seed_facecam as SF
from .rbac import Ctx, AccessDenied

router = APIRouter()
_con = None
_ctx = None
RES = "face"
ROOT = Path(__file__).resolve().parent.parent
SNAP_DIR = db.DATA_DIR / "face_snaps"
KEEP_DAYS = int(os.getenv("ISFT_CORE_FACE_KEEP_DAYS", "7"))
EVENTS_DAYS = int(os.getenv("ISFT_CORE_FACE_EVENTS_DAYS", "90"))
MATCH_MIN = float(os.getenv("ISFT_CORE_FACE_MATCH_MIN", "0.75"))
STAFF_START = os.getenv("ISFT_CORE_STAFF_START", "09:00")
LATE_GRACE = int(os.getenv("ISFT_CORE_FACE_LATE_GRACE_MIN", "0"))
EXIT_CAMS = {int(x) for x in os.getenv("ISFT_CORE_FACE_EXIT_CAMS", "").split(",") if x.strip().isdigit()}   # chiqishga qaragan kameralar
DEDUP_S = 60

KINDS = ("talaba", "oqituvchi", "xodim")
KIND_LABEL = {"talaba": "Talaba", "oqituvchi": "O'qituvchi", "xodim": "Xodim"}
STATUS_LABEL = {"tanildi": "Tanildi", "notanish": "Notanish shaxs", "rozilik_yoq": "Aniqlanmadi (rozilik yo'q)", "past_ishonch": "Past ishonch"}
BANNER = ("Sinov rejimi: tasvirlar sintetik (haqiqiy shaxslar emas). Haqiqiy tizimda faqat yozma roziligi bor shaxslar ro'yxatga olinadi.")

def _enabled():
    from . import camsec as CS
    return CS.FEATURE_FACE

# ---------------------------------------------------------------------------------------------
# Ruxsat
# ---------------------------------------------------------------------------------------------
ALL = KINDS
ACCESS = {
    "rektor": {"mode": "ids", "kinds": ALL, "unknown": True, "manage": ALL},
    "xojalik": {"mode": "ids", "kinds": ALL, "unknown": True, "manage": ALL},
    "kadrlar": {"mode": "ids", "kinds": ("oqituvchi", "xodim"), "unknown": False, "manage": ("oqituvchi", "xodim")},
    "tyutor": {"mode": "ids", "kinds": ("talaba",), "unknown": False, "fac": True, "manage": ()},
    "it_head": {"mode": "health"},
    "kengash": {"mode": "aggregate"},
}
LEVEL = {"health": 1, "aggregate": 2, "ids": 3}
NEED_TXT = {"health": "kamera holati", "aggregate": "jamlangan ko'rsatkichlar", "ids": "shaxslar va kadrlar"}

class Acc:
    def __init__(self, ctx: Ctx):
        c = ACCESS.get(ctx.role.key) or {}
        self.role = ctx.role.key
        self.mode = c.get("mode")
        if self.mode == "ids" and ctx.channel == "telegram": self.mode = "aggregate"     # biometrik tafsilot Telegram'ga chiqmaydi
        self.kinds = tuple(c.get("kinds") or ())
        self.unknown = bool(c.get("unknown"))
        self.fac = int(ctx.user["faculty_id"]) if c.get("fac") and ctx.user.get("faculty_id") else None
        self.manage = tuple(c.get("manage") or ()) if self.mode == "ids" else ()
        self.key = f"{self.role}:{self.fac or ''}:{self.mode}"

    def scope_label(self):
        if self.mode == "health": return "Faqat kamera va yuz kutubxonasi holati (shaxslarsiz)"
        if self.mode == "aggregate": return "Jamlangan ko'rsatkichlar (ism va rasmsiz)"
        if self.fac: return "Faqat o'z fakultetingiz talabalari"
        if self.kinds == ("oqituvchi", "xodim"): return "O'qituvchilar va xodimlar (punktuallik)"
        return "Barcha shaxslar va notanishlar (xavfsizlik)"

def access(con, ctx: Ctx, action: str, need: str = "ids", detail: str = "", quiet: bool = False) -> Acc:
    a = Acc(ctx)
    if not _enabled():
        raise AccessDenied("⛔ Kirish nazorati (Face ID) o'chirilgan (ISFT_CORE_FEATURE_FACE=0).")
    if not a.mode or LEVEL[a.mode] < LEVEL[need]:
        rbac.audit(con, ctx, f"Face ID: {action}", RES, False, detail or NEED_TXT[need])
        if a.mode == "health":
            raise AccessDenied("⛔ AT bo'limi uchun Face ID — faqat kamera va yuz kutubxonasi holati (sonlar). Shaxslar va kadrlar — xo'jalik bo'limi va rektor. So'rov audit jurnaliga yozildi.")
        if a.mode == "aggregate":
            raise AccessDenied("⛔ Face ID: sizga faqat jamlangan ko'rsatkichlar ochiq — ismlar va kadrlar ko'rsatilmaydi. So'rov audit jurnaliga yozildi.")
        raise AccessDenied("⛔ Kirish nazorati (Face ID) — rektor, xo'jalik bo'limi, kadrlar bo'limi (xodimlar) va fakultet tyutori (o'z talabalari) uchun. So'rov audit jurnaliga yozildi.")
    if not quiet:
        rbac.audit(con, ctx, f"Face ID: {action}", RES, True, detail)
    return a

def _visible(a: Acc, e: dict) -> bool:
    if a.mode != "ids": return False
    if e.get("p_kind") and e["status"] in ("tanildi", "past_ishonch"):
        return e["p_kind"] in a.kinds and (not a.fac or e.get("p_fac") == a.fac)
    return a.unknown

# ---------------------------------------------------------------------------------------------
# Tayyorlash (jadvallar, kameralar, demo ma'lumot, tozalash)
# ---------------------------------------------------------------------------------------------
_READY = {"ok": False, "t": 0.0}
_VER = [0]            # rozilik o'zgarsa — rasm keshi yangilanadi

def init(con):
    SF.init(con)
    purge(con)

def purge(con):
    """Rasm (fon) — KEEP_DAYS kundan, voqea metama'lumoti — EVENTS_DAYS kundan ortiq saqlanmaydi."""
    now = time.time()
    if SNAP_DIR.exists():
        for f in SNAP_DIR.glob("*.jpg"):
            try:
                if now - f.stat().st_mtime > KEEP_DAYS * 86400: f.unlink()
            except OSError: pass
    lim = (clock.now() - dt.timedelta(days=EVENTS_DAYS)).isoformat(timespec="seconds")
    try:
        con.execute("DELETE FROM face_events WHERE ts<?", (lim,)); con.execute("DELETE FROM face_frames WHERE ts<?", (lim,)); con.commit()
    except Exception: pass

def ensure(con):
    """Birinchi so'rovda: kameralar va demo shaxslar (bo'sh bo'lsa); har so'rovda: rejadagi voqealar hozirgacha yoziladi (ko'pi bilan 20 s da bir)."""
    if not _READY["ok"]:
        SF.init(con)
        if not db.one(con, "SELECT 1 x FROM face_persons LIMIT 1") or len(SF.entrance_cams(con)) < 2:
            SF.ensure_cameras(con); SF.ensure_persons(con)
        _READY["ok"] = True
    if time.time() - _READY["t"] > 20:
        _READY["t"] = time.time()
        if SF.meta(con, "until") or not db.one(con, "SELECT 1 x FROM face_events LIMIT 1"):
            SF.materialize(con, match_min=MATCH_MIN)

def now():
    from . import occupancy as OC
    return OC.now()

def iso(t): return t.isoformat(timespec="seconds")
def hm(s): h, m = map(int, s.split(":")); return h * 60 + m
def _norm(s): return re.sub(r"[ʻʼ‘’`´']", "", (s or "").lower())

def short_name(n: str) -> str:
    p = (n or "").split()
    return f"{p[0]} {p[1][0]}." if len(p) >= 2 else (n or "")

def _sub_short(s: str, n=30) -> str:
    s = s or ""
    return s if len(s) <= n else s[:n - 1].rstrip() + "…"

# ---------------------------------------------------------------------------------------------
# Real kameradan voqea (camsec.process_event → shu yerga)
# ---------------------------------------------------------------------------------------------
def ingest(con, cam: dict, ev: dict, t: dt.datetime | None = None):
    """Bitta yuz voqeasi (hikvision.normalize kind='yuz'). Faqat kirish zonasidagi kameralar. Qaytaradi: yozuv yoki None."""
    t = t or now()
    SF.ensure_schema(con)     # executescript emas: process_event'ning ochiq tranzaksiyasi (kamera holati) muddatidan oldin commit qilinmaydi
    room = db.one(con, "SELECT zone FROM rooms WHERE id=?", (cam["room_id"],)) or {}
    if room.get("zone") != "kirish":
        return None                                      # bino ichida shaxs kuzatilmaydi
    fpid, sim = ev.get("fpid"), ev.get("similarity")
    p = db.one(con, "SELECT * FROM face_persons WHERE fpid=? AND consent=1 AND revoked_at IS NULL", (fpid,)) if fpid else None
    if p and fpid and db.one(con, "SELECT 1 x FROM face_events WHERE camera_id=? AND fpid=? AND ts>=?", (cam["id"], fpid, iso(t - dt.timedelta(seconds=DEDUP_S)))):
        return None                                      # kamera bir odamni ketma-ket bir necha marta yuboradi
    status = ("tanildi" if (sim or 0) >= MATCH_MIN else "past_ishonch") if p else "notanish"
    rect = ev.get("rect") or [.45, .3, .07, .16]
    direction = ev.get("direction") or ("chiqish" if cam["id"] in EXIT_CAMS else "kirish")
    fr = db.one(con, "SELECT id FROM face_frames WHERE camera_id=? AND source='kamera' AND ts>=? AND ts<=? ORDER BY id DESC LIMIT 1",
                (cam["id"], iso(t - dt.timedelta(seconds=3)), iso(t)))
    if fr:
        fid = fr["id"]; con.execute("UPDATE face_frames SET n=n+1 WHERE id=?", (fid,))
    else:
        fid = con.execute("INSERT INTO face_frames(ts,camera_id,direction,seed,n,source) VALUES(?,?,?,?,1,'kamera')",
                          (iso(t), cam["id"], direction, random.randint(1, 10 ** 7))).lastrowid
        pic = ev.get("picture")
        if pic and pic[:2] == b"\xff\xd8":
            _save_snap(con, fid, pic)
        elif ev.get("bkg_url") and cam.get("mode") == "isapi":
            try: asyncio.get_running_loop().create_task(_fetch_snap(cam["id"], fid, ev["bkg_url"]))
            except RuntimeError: pass
    night = int(not (hm("07:00") <= t.hour * 60 + t.minute <= hm("20:00")))
    eid = con.execute("""INSERT INTO face_events(frame_id,ts,camera_id,direction,person_id,fpid,similarity,rect,status,look,female,night,raw_type)
                         VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                      (fid, iso(t), cam["id"], direction, p["id"] if p else None, fpid if p else None, sim, json.dumps(rect), status,
                       p["avatar_seed"] if p else random.randint(1, 10 ** 7), p["female"] if p else None, night, ev.get("raw_type") or "yuz")).lastrowid
    con.commit()
    return {"id": eid, "kind": "yuz", "status": status, "frame_id": fid, "person_id": p["id"] if p else None}

def _save_snap(con, fid, jpeg: bytes):
    SNAP_DIR.mkdir(parents=True, exist_ok=True)
    (SNAP_DIR / f"{fid}.jpg").write_bytes(jpeg)
    con.execute("UPDATE face_frames SET snap=? WHERE id=?", (f"{fid}.jpg", fid))

async def _fetch_snap(cam_id, fid, url):
    from . import occupancy as OC
    try:
        cam = db.one(_con, "SELECT * FROM cameras WHERE id=?", (cam_id,))
        b = await OC.cam_client(cam).fetch_picture(url)
        if b: _save_snap(_con, fid, b); _con.commit()
    except Exception:
        pass

# ---------------------------------------------------------------------------------------------
# O'qish: kun voqealari
# ---------------------------------------------------------------------------------------------
def _day(s: str | None) -> dt.date:
    try: return dt.date.fromisoformat(s) if s else now().date()
    except ValueError: raise HTTPException(400, "Sana noto'g'ri (YYYY-MM-DD)")

def day_rows(con, d: dt.date, cam: int = 0) -> list:
    a, b = d.isoformat(), (d + dt.timedelta(days=1)).isoformat()
    w, args = "e.ts>=? AND e.ts<?", [a, b]
    if cam: w += " AND e.camera_id=?"; args.append(int(cam))
    return db.rows(con, f"""SELECT e.*, p.kind p_kind, p.name p_name, p.sub p_sub, p.faculty_id p_fac, p.ref_id p_ref, p.group_id p_gid,
                            r.name cam_name, r.building cam_bld
                            FROM face_events e LEFT JOIN face_persons p ON p.id=e.person_id
                            JOIN cameras c ON c.id=e.camera_id JOIN rooms r ON r.id=c.room_id WHERE {w} ORDER BY e.ts, e.id""", args)

def _face_json(a: Acc, e: dict) -> dict:
    vis = _visible(a, e)
    out = {"event_id": e["id"], "status": e["status"], "status_label": STATUS_LABEL.get(e["status"], e["status"]), "visible": vis,
           "similarity": round(100 * e["similarity"]) if e.get("similarity") is not None and vis else None, "rect": json.loads(e["rect"] or "[0,0,0,0]")}
    if vis and e.get("p_kind"):
        out.update(person_id=e["person_id"], kind=e["p_kind"], kind_label=KIND_LABEL[e["p_kind"]], name=e["p_name"], sub=e["p_sub"],
                   candidate=e["status"] == "past_ishonch")
    else:
        out.update(person_id=None, kind=None, name=None, sub=None)
    return out

def _label(a: Acc, e: dict) -> dict:
    """Rasm ustidagi yorliq — ko'ruvchi ko'lamiga qarab."""
    rect = json.loads(e["rect"] or "[0,0,0,0]")
    if not _visible(a, e):
        return {"rect": rect, "color": "yashirin", "label": "", "hidden": True}
    st = e["status"]
    sim = f"{round(100 * e['similarity'])}%" if e.get("similarity") is not None else ""
    if st == "tanildi":
        return {"rect": rect, "color": e["p_kind"], "label": f"{KIND_LABEL[e['p_kind']]} · {short_name(e['p_name'])} · {sim}", "sub": _sub_short(e["p_sub"])}
    if st == "past_ishonch":
        return {"rect": rect, "color": "past_ishonch", "label": f"Past ishonch · {sim}", "sub": f"ehtimol: {short_name(e['p_name'])} — tasdiqlanmagan"}
    if st == "rozilik_yoq":
        return {"rect": rect, "color": "rozilik_yoq", "label": "Aniqlanmadi", "sub": "rozilik yo'q — shaxs ko'rsatilmaydi"}
    return {"rect": rect, "color": "notanish", "label": "Notanish shaxs", "sub": "yuz kutubxonasida yo'q"}

# ---------------------------------------------------------------------------------------------
# Rasm: sahna keshi + izohlangan JPEG keshi (LRU)
# ---------------------------------------------------------------------------------------------
_IMG_LOCK = threading.Lock()
_JPEG: "OrderedDict[tuple, bytes]" = OrderedDict()
_BASE: "OrderedDict[int, object]" = OrderedDict()
_AUD: dict = {}

def _base_image(fr: dict, evs: list):
    from . import facecam_render as FR
    from PIL import Image, ImageDraw
    with _IMG_LOCK:
        if fr["id"] in _BASE:
            _BASE.move_to_end(fr["id"]); return _BASE[fr["id"]]
    if fr.get("snap"):
        p = SNAP_DIR / fr["snap"]
        if not p.exists(): raise HTTPException(410, f"Kadr rasmi saqlash muddati ({KEEP_DAYS} kun) o'tgani uchun o'chirilgan — faqat metama'lumot qoldi")
        im = Image.open(p).convert("RGB").resize((FR.W, FR.H))
    elif fr.get("source") == "kamera":
        im = Image.new("RGB", (FR.W, FR.H), (38, 42, 50)); d = ImageDraw.Draw(im)
        d.text((40, 330), "Kamera fon rasmini yubormadi — faqat metama'lumot", font=FR.font("b", 28), fill=(200, 205, 214))
    else:
        faces = tuple((tuple(json.loads(e["rect"])), int(e["look"] or 1), None if e["female"] is None else bool(e["female"])) for e in evs)
        im = FR.scene_image(int(fr["seed"]), fr["ts"], fr["cam_name"], (fr["cam_bld"] or "A")[0], fr["direction"], faces)
    with _IMG_LOCK:
        _BASE[fr["id"]] = im
        while len(_BASE) > 12: _BASE.popitem(last=False)
    return im

def frame_jpeg(con, a: Acc, fid: int, width: int = 0) -> bytes:
    from . import facecam_render as FR
    width = max(240, min(1280, int(width or 1280)))
    key = (fid, a.key, width, _VER[0])
    with _IMG_LOCK:
        if key in _JPEG:
            _JPEG.move_to_end(key); return _JPEG[key]
    fr = db.one(con, """SELECT f.*, r.name cam_name, r.building cam_bld FROM face_frames f JOIN cameras c ON c.id=f.camera_id
                        JOIN rooms r ON r.id=c.room_id WHERE f.id=?""", (fid,))
    if not fr: raise HTTPException(404, "Kadr topilmadi")
    evs = db.rows(con, """SELECT e.*, p.kind p_kind, p.name p_name, p.sub p_sub, p.faculty_id p_fac FROM face_events e
                          LEFT JOIN face_persons p ON p.id=e.person_id WHERE e.frame_id=? ORDER BY e.id""", (fid,))
    base = _base_image(fr, evs)
    labs = [_label(a, e) for e in evs]
    st = Counter(e["status"] for e in evs if _visible(a, e))
    hid = sum(1 for e in evs if not _visible(a, e))
    parts = [f"{st['tanildi']} tanildi"] if st["tanildi"] else []
    if st["notanish"]: parts.append(f"{st['notanish']} notanish")
    if st["rozilik_yoq"]: parts.append(f"{st['rozilik_yoq']} rozilik yo'q")
    if st["past_ishonch"]: parts.append(f"{st['past_ishonch']} past ishonch")
    if hid: parts.append(f"{hid} ko'lamdan tashqari (yashirilgan)")
    footer = f"ISFT Core · Face ID · {len(evs)} ta yuz: " + ", ".join(parts)
    jpg = FR.to_jpeg(FR.annotate(base, labs, fr["direction"], footer), width)
    with _IMG_LOCK:
        _JPEG[key] = jpg
        while len(_JPEG) > 400: _JPEG.popitem(last=False)
    return jpg

def _audit_view(con, ctx, fid, what="kadr ko'rildi"):
    k = (ctx.user["id"], fid, what)
    if time.time() - _AUD.get(k, 0) > 1800:      # bir kadr — 30 daqiqada bir yozuv (galereya qayta yuklanganda jurnal to'lib ketmasin)
        _AUD[k] = time.time()
        rbac.audit(con, ctx, f"Face ID: {what}", RES, True, f"kadr #{fid}")

# ---------------------------------------------------------------------------------------------
# Ko'rinishlar
# ---------------------------------------------------------------------------------------------
def _match(a: Acc, e: dict, kind: str, q: str) -> bool:
    if not _visible(a, e): return False
    if kind:
        if kind == "notanish": ok = e["status"] in ("notanish", "rozilik_yoq")
        elif kind == "past_ishonch": ok = e["status"] == "past_ishonch"
        else: ok = e["status"] == "tanildi" and e.get("p_kind") == kind
        if not ok: return False
    if q:
        hay = _norm(f"{e.get('p_name') or ''} {e.get('p_sub') or ''}") if e.get("p_kind") else ""
        return all(w in hay for w in _norm(q).split())
    return True

def frames(con, ctx: Ctx, date=None, cam=0, kind="", q="", offset=0, limit=24):
    ensure(con)
    d = _day(date)
    a = access(con, ctx, "kadrlar ro'yxati", "ids", f"{d} · kamera {cam or 'hammasi'} · {kind or 'barcha'}" + (f" · qidiruv: {q[:40]}" if q else ""))
    rows = day_rows(con, d, cam)
    by = OrderedDict()
    for e in rows: by.setdefault(e["frame_id"], []).append(e)
    fr_meta = {f["id"]: f for f in db.rows(con, f"SELECT id, ts, camera_id, direction, source, snap FROM face_frames WHERE id IN ({','.join(str(x) for x in by) or '0'})")}
    out = []
    for fid, evs in by.items():
        if not any(_visible(a, e) for e in evs): continue
        if (kind or q) and not any(_match(a, e, kind, q) for e in evs): continue
        f = fr_meta.get(fid) or {}
        out.append({"id": fid, "ts": evs[0]["ts"], "camera_id": evs[0]["camera_id"], "camera": evs[0]["cam_name"], "direction": f.get("direction") or evs[0]["direction"],
                    "source": f.get("source"), "night": bool(evs[0]["night"]), "img": f"/api/face/events/{evs[0]['id']}/image",
                    "faces": [_face_json(a, e) for e in evs]})
    out.sort(key=lambda x: x["ts"], reverse=True)
    lim = max(1, min(int(limit), 96)); off = max(0, int(offset))
    return {"date": d.isoformat(), "total": len(out), "frames": out[off:off + lim], "offset": off, "limit": lim}

def frame_detail(con, ctx: Ctx, fid: int):
    ensure(con)
    a = access(con, ctx, "kadr tafsiloti", "ids", f"kadr #{fid}", quiet=True)
    evs = db.rows(con, """SELECT e.*, p.kind p_kind, p.name p_name, p.sub p_sub, p.faculty_id p_fac, r.name cam_name FROM face_events e
                          LEFT JOIN face_persons p ON p.id=e.person_id JOIN cameras c ON c.id=e.camera_id JOIN rooms r ON r.id=c.room_id
                          WHERE e.frame_id=? ORDER BY e.id""", (fid,))
    if not evs: raise HTTPException(404, "Kadr topilmadi")
    if not any(_visible(a, e) for e in evs):
        rbac.audit(con, ctx, "Face ID: kadr tafsiloti", RES, False, f"kadr #{fid} — ko'lamdan tashqari")
        raise AccessDenied("⛔ Bu kadrdagi shaxslar sizning ko'lamingizdan tashqarida. So'rov audit jurnaliga yozildi.")
    _audit_view(con, ctx, fid, "kadr tafsiloti ko'rildi")
    fr = db.one(con, "SELECT * FROM face_frames WHERE id=?", (fid,))
    return {"id": fid, "ts": evs[0]["ts"], "camera": evs[0]["cam_name"], "direction": fr["direction"], "source": fr["source"],
            "img": f"/api/face/events/{evs[0]['id']}/image", "faces": [_face_json(a, e) for e in evs],
            "note": "Sintetik kadr: sahna va odamlar kompyuterda chizilgan, haqiqiy shaxslar emas." if fr["source"] == "sintetik" else
                    f"Kamera kadri: {KEEP_DAYS} kundan keyin avtomatik o'chiriladi."}

def event_image(con, ctx: Ctx, eid: int, w: int = 0) -> bytes:
    ensure(con)
    a = access(con, ctx, "kadr rasmi", "ids", f"voqea #{eid}", quiet=True)
    e = db.one(con, "SELECT frame_id FROM face_events WHERE id=?", (eid,))
    if not e: raise HTTPException(404, "Voqea topilmadi")
    fid = e["frame_id"]
    evs = db.rows(con, "SELECT e.*, p.kind p_kind, p.faculty_id p_fac FROM face_events e LEFT JOIN face_persons p ON p.id=e.person_id WHERE e.frame_id=?", (fid,))
    if not any(_visible(a, x) for x in evs):
        rbac.audit(con, ctx, "Face ID: kadr rasmi", RES, False, f"kadr #{fid} — ko'lamdan tashqari")
        raise AccessDenied("⛔ Bu kadrdagi shaxslar sizning ko'lamingizdan tashqarida. So'rov audit jurnaliga yozildi.")
    _audit_view(con, ctx, fid)
    return frame_jpeg(con, a, fid, w)

def _first_slot(con, p: dict, d: dt.date):
    fs = SF.first_slot(con, p["kind"], p["ref_id"], p.get("group_id"), d.weekday())
    if not fs: return None
    n0, n1 = fs
    return {"slot": n0, "start": SF.SLOTS[n0 - 1][1], "end": SF.SLOTS[n1 - 1][2], "last_slot": n1}

def _late_min(arrival_ts: str, start: str) -> int:
    t = dt.datetime.fromisoformat(arrival_ts)
    diff = (t.hour * 60 + t.minute + t.second / 60) - hm(start)
    return max(1, int(diff)) if diff > LATE_GRACE else 0      # 08:50:40 → 20 daqiqa; 08:30:20 → 1 daqiqa (boshlanishdan keyin — kechikkan)

def timeline(con, ctx: Ctx, pid: int, days: int = 14):
    ensure(con)
    a = access(con, ctx, "shaxs tarixi", "ids", f"shaxs #{pid}", quiet=True)
    p = db.one(con, "SELECT * FROM face_persons WHERE id=?", (pid,))
    if not p: raise HTTPException(404, "Shaxs topilmadi")
    if not _visible(a, {"p_kind": p["kind"], "p_fac": p["faculty_id"], "status": "tanildi"}):
        rbac.audit(con, ctx, "Face ID: shaxs tarixi", RES, False, f"shaxs #{pid} ({p['kind']}) — ko'lamdan tashqari")
        raise AccessDenied("⛔ Bu shaxs sizning ko'lamingizdan tashqarida. So'rov audit jurnaliga yozildi.")
    rbac.audit(con, ctx, "Face ID: shaxs tarixi ko'rildi", RES, True, f"{p['name']} ({KIND_LABEL[p['kind']]}), {days} kun")
    t = now(); d0 = t.date() - dt.timedelta(days=max(1, min(int(days), 31)) - 1)
    evs = db.rows(con, """SELECT e.id, e.ts, e.direction, e.similarity, e.status, e.frame_id, r.name cam FROM face_events e JOIN cameras c ON c.id=e.camera_id
                          JOIN rooms r ON r.id=c.room_id WHERE e.person_id=? AND e.ts>=? ORDER BY e.ts""", (pid, d0.isoformat()))
    by = defaultdict(list)
    for e in evs: by[e["ts"][:10]].append(e)
    out = []
    d = t.date()
    while d >= d0:
        k = d.isoformat(); es = by.get(k, [])
        ok = [e for e in es if e["status"] == "tanildi"]
        fin = next((e["ts"] for e in ok if e["direction"] == "kirish"), None)
        lout = next((e["ts"] for e in reversed(ok) if e["direction"] == "chiqish"), None)
        fs = _first_slot(con, p, d) if p["kind"] != "xodim" else {"slot": None, "start": STAFF_START, "end": None}
        late = _late_min(fin, fs["start"]) if fin and fs else 0
        out.append({"date": k, "weekday": ["Du", "Se", "Ch", "Pa", "Ju", "Sh", "Ya"][d.weekday()], "first_in": fin, "last_out": lout,
                    "first_slot": fs, "late_min": late, "events": [{"id": e["id"], "ts": e["ts"], "direction": e["direction"], "camera": e["cam"],
                                                                    "similarity": round(100 * e["similarity"]) if e["similarity"] else None,
                                                                    "status": e["status"], "frame_id": e["frame_id"]} for e in es]})
        d -= dt.timedelta(days=1)
    return {"person": {"id": p["id"], "kind": p["kind"], "kind_label": KIND_LABEL[p["kind"]], "name": p["name"], "sub": p["sub"],
                       "consent": bool(p["consent"]), "consent_doc": p["consent_doc"], "consent_at": p["consent_at"]},
            "days": out, "late_days": sum(1 for x in out if x["late_min"]), "present_days": sum(1 for x in out if x["first_in"])}

# ---------------------------------------------------------------------------------------------
# Faktlar (hisobot, KPI, agent) — faqat koddan hisoblanadi
# ---------------------------------------------------------------------------------------------
def _scope_rows(a: Acc, rows: list, scope: str = "") -> list:
    """Ko'ruvchi ko'lamidagi qatorlar. Jamlangan rejimda (kengash) — hammasi (ismlarsiz ishlatiladi)."""
    if a.mode == "aggregate": out = rows
    else: out = [e for e in rows if _visible(a, e)]
    if scope in KINDS: out = [e for e in out if e.get("p_kind") == scope and e["status"] in ("tanildi", "past_ishonch")]
    elif scope == "notanish": out = [e for e in out if e["status"] in ("notanish", "rozilik_yoq")]
    return out

def facts(con, a: Acc, d: dt.date, scope: str = "") -> dict:
    rows = _scope_rows(a, day_rows(con, d), scope)
    names = a.mode == "ids"
    ent = [e for e in rows if e["direction"] == "kirish"]
    ext = [e for e in rows if e["direction"] == "chiqish"]
    ok = [e for e in rows if e["status"] == "tanildi"]
    uniq = {k: len({e["person_id"] for e in ok if e["p_kind"] == k}) for k in KINDS}
    hours = Counter(int(e["ts"][11:13]) for e in ent)
    peak = max(hours.items(), key=lambda x: (x[1], -x[0])) if hours else None
    first = {}
    for e in ok:
        if e["direction"] == "kirish" and e["person_id"] not in first: first[e["person_id"]] = e
    persons = {p["id"]: p for p in db.rows(con, f"SELECT * FROM face_persons WHERE id IN ({','.join(str(x) for x in first) or '0'})")}
    late_t, late_s, staff_late = [], Counter(), []
    stu_late = 0
    for pid, e in first.items():
        p = persons.get(pid)
        if not p: continue
        if p["kind"] == "xodim":
            m = _late_min(e["ts"], STAFF_START)
            if m: staff_late.append({"name": p["name"], "unit": p["sub"], "arrival": e["ts"][11:16], "minutes": m})
            continue
        fs = _first_slot(con, p, d)
        if not fs: continue
        m = _late_min(e["ts"], fs["start"])
        if not m: continue
        if p["kind"] == "oqituvchi":
            late_t.append({"person_id": pid, "name": p["name"], "kafedra": p["sub"], "slot": fs["slot"], "first_para": fs["start"],
                           "arrival": e["ts"][11:16], "minutes": m, "camera": e["cam_name"]})
        else:
            stu_late += 1; late_s[p["sub"]] += 1
    late_t.sort(key=lambda x: -x["minutes"]); staff_late.sort(key=lambda x: -x["minutes"])
    st = Counter(e["status"] for e in rows)
    night = [e for e in rows if e["night"] and e["direction"] == "kirish"]
    # oldingi 7 ish kuni (yakshanbasiz) o'rtachasi
    prev, dd = [], d - dt.timedelta(days=1)
    while len(prev) < 7 and dd >= d - dt.timedelta(days=14):
        if dd.weekday() != 6: prev.append(dd)
        dd -= dt.timedelta(days=1)
    pe, pu = [], []
    for x in prev:
        r2 = _scope_rows(a, day_rows(con, x), scope)
        if not r2: continue
        pe.append(sum(1 for e in r2 if e["direction"] == "kirish"))
        pu.append(len({e["person_id"] for e in r2 if e["status"] == "tanildi"}))
    avg_e = round(sum(pe) / len(pe), 1) if pe else None
    avg_u = round(sum(pu) / len(pu), 1) if pu else None
    total_u = sum(uniq.values())
    kinds = [k for k in (a.kinds if a.mode == "ids" else KINDS) if not scope or scope == k or scope not in KINDS]
    f = {"date": d.isoformat(), "scope": scope or "hammasi", "scope_label": a.scope_label(), "kinds": kinds, "unknown_ok": a.unknown or a.mode == "aggregate",
         "entries": len(ent), "exits": len(ext), "detections": len(rows),
         "unique": uniq, "unique_total": total_u,
         "peak_hour": {"hour": f"{peak[0]:02d}:00–{peak[0] + 1:02d}:00", "entries": peak[1]} if peak else None,
         "late_teachers_n": len(late_t), "late_students_n": stu_late, "staff_after_n": len(staff_late),
         "late_groups": [{"group": g, "n": n} for g, n in late_s.most_common(5)],
         "unknown": st["notanish"], "no_consent": st["rozilik_yoq"], "low_conf": st["past_ishonch"],
         "low_conf_pct": round(100 * st["past_ishonch"] / len(rows), 1) if rows else 0.0,
         "night_entries": len(night), "night": [{"ts": e["ts"][11:16], "camera": e["cam_name"], "status": STATUS_LABEL[e["status"]]} for e in night],
         "prev7": {"days": len(pe), "entries_avg": avg_e, "unique_avg": avg_u,
                   "entries_delta_pct": round(100 * (len(ent) - avg_e) / avg_e, 1) if avg_e else None,
                   "unique_delta_pct": round(100 * (total_u - avg_u) / avg_u, 1) if avg_u else None},
         "rules": {"teacher_late": f"birinchi para boshlanishidan keyin kirgan (dars jadvali, para vaqtlari {SF.SLOTS[0][1]}–{SF.SLOTS[-1][2]})"
                   + (f", {LATE_GRACE} daqiqa imtiyoz" if LATE_GRACE else ""),
                   "staff_late": f"{STAFF_START} dan keyin kirgan", "match_min": round(100 * MATCH_MIN)}}
    if names:
        f["late_teachers"] = late_t; f["staff_after"] = staff_late
    return f

def narrative_template(f: dict) -> str:
    dmy = f"{f['date'][8:10]}.{f['date'][5:7]}.{f['date'][:4]}"
    u = f["unique"]
    ks = f.get("kinds") or list(KINDS)
    who = ", ".join(f"{u[k]} {KIND_LABEL[k].lower()}" for k in ks)
    s = [f"{dmy} kuni kirish kameralari {'(ko' + chr(39) + 'lamingiz bo' + chr(39) + 'yicha) ' if len(ks) < 3 else ''}{f['entries']} ta kirish va {f['exits']} ta chiqishni qayd etdi; "
         f"aniqlangan shaxslar: {who}."]
    if f["peak_hour"]: s.append(f"Eng gavjum vaqt — {f['peak_hour']['hour']} ({f['peak_hour']['entries']} ta kirish).")
    if "oqituvchi" not in ks: pass
    elif f["late_teachers_n"]:
        if f.get("late_teachers"):
            top = f["late_teachers"][0]
            s.append(f"{f['late_teachers_n']} nafar o'qituvchi birinchi darsi boshlangandan keyin kelgan; eng ko'p kechikish — {top['minutes']} daqiqa "
                     f"({short_name(top['name'])}, {top['first_para']} dagi darsga {top['arrival']} da kirgan).")
        else:
            s.append(f"{f['late_teachers_n']} nafar o'qituvchi birinchi darsi boshlangandan keyin kelgan.")
    else:
        s.append("Birinchi darsiga kechikkan o'qituvchi qayd etilmadi.")
    if f["late_students_n"] and "talaba" in ks:
        g = ", ".join(f"{x['group']} ({x['n']})" for x in f["late_groups"][:3])
        s.append(f"{f['late_students_n']} nafar talaba birinchi para boshlangandan keyin kirgan" + (f", ko'pi — {g}." if g else "."))
    if f["staff_after_n"] and "xodim" in ks: s.append(f"{f['staff_after_n']} nafar xodim {STAFF_START} dan keyin kelgan.")
    sec = []
    if f["unknown"]: sec.append(f"notanish shaxs — {f['unknown']}")
    if f["no_consent"]: sec.append(f"rozilik bermagan (aniqlanmagan) — {f['no_consent']}")
    if f["night_entries"]: sec.append(f"tungi kirish — {f['night_entries']}")
    if sec and f.get("unknown_ok", True): s.append("Xavfsizlik: " + ", ".join(sec) + f"; past ishonchli aniqlash ulushi {f['low_conf_pct']}%.")
    p7 = f["prev7"]
    if p7.get("entries_avg"):
        dlt = p7["entries_delta_pct"]
        s.append(f"Oldingi {p7['days']} ish kuni o'rtachasi {p7['entries_avg']} ta kirish edi — bugun " +
                 (f"{abs(dlt)}% {'ko' + chr(39) + 'p' if dlt > 0 else 'kam'}." if dlt else "xuddi shuncha."))
    return " ".join(s)

def _verify(text: str, src: str) -> dict:
    from . import agent as AG
    return AG.verify(text, src)

async def report(con, ctx: Ctx, date=None, scope=""):
    ensure(con)
    d = _day(date)
    a = access(con, ctx, "AI hisobot", "aggregate", f"{d} · {scope or 'hammasi'}")
    f = facts(con, a, d, scope)
    text, mode = narrative_template(f), "shablon"
    src = json.dumps(f, ensure_ascii=False)
    from . import ai
    if await ai.llm_available():
        try:
            out = await ai.llm_once([{"role": "system", "content": "Sen ISFT instituti rahbariyati uchun hisobot yozuvchisan. Senga kirish kameralari "
                                      "(Face ID) bo'yicha FAKTLAR (JSON) beriladi. 5–7 gapdan iborat rasmiy o'zbek (lotin) tilidagi xulosa yoz. FAQAT "
                                      "faktlardagi raqam va ismlarni ishlat, yangi raqam, foiz yoki sabab o'ylab topma. Ro'yxat va sarlavha yozma."},
                                     {"role": "user", "content": src}], max_tokens=500)
            v = _verify(out, src)
            if out.strip() and not v["bad"]: text, mode = out.strip(), "ai"
        except Exception:
            pass
    return {"facts": f, "narrative": text, "narrative_mode": mode, "verify": _verify(text, src + "\n" + narrative_template(f)),
            "banner": BANNER}

def build_docx(con, ctx: Ctx, base_url: str, date=None, scope=""):
    ensure(con)
    d = _day(date)
    a = access(con, ctx, "Word hisobot", "aggregate", f"{d} · {scope or 'hammasi'}", quiet=True)
    from . import documents as D, brand as B
    f = facts(con, a, d, scope)
    text = narrative_template(f)
    dmy = d.strftime("%d.%m.%Y")
    I = D.Issuer(con, ctx, {"key": "face_daily", "prefix": "KRN", "title": "Kirish nazorati (Face ID) — kunlik hisobot"}, base_url)
    I.page("ISFT instituti (kirish kameralari)")
    B.title(I.doc, "KIRISH NAZORATI (FACE ID) — KUNLIK HISOBOT", f"{dmy} · {f['scope_label']}")
    B.para(I.doc, text)
    B.para(I.doc, "1. Umumiy ko'rsatkichlar", indent=False, bold=True)
    u = f["unique"]; p7 = f["prev7"]
    B.table(I.doc, ["Ko'rsatkich", "Qiymat"], [("Kirishlar / chiqishlar", f"{f['entries']} / {f['exits']}"),
                                               ("Aniqlangan: talaba / o'qituvchi / xodim", f"{u['talaba']} / {u['oqituvchi']} / {u['xodim']}"),
                                               ("Eng gavjum soat", f"{f['peak_hour']['hour']} ({f['peak_hour']['entries']} ta)" if f["peak_hour"] else "—"),
                                               ("Notanish / rozilik yo'q / past ishonch", f"{f['unknown']} / {f['no_consent']} / {f['low_conf']} ({f['low_conf_pct']}%)"),
                                               ("Tungi kirishlar", str(f["night_entries"])),
                                               ("Oldingi 7 ish kuni o'rtachasi (kirish)", f"{p7['entries_avg']} ({'+' if (p7['entries_delta_pct'] or 0) > 0 else ''}{p7['entries_delta_pct']}%)" if p7.get("entries_avg") else "—")],
            [10, 6])
    if f.get("late_teachers"):
        B.para(I.doc, f"2. Birinchi darsi boshlangandan keyin kelgan o'qituvchilar ({f['late_teachers_n']})", indent=False, bold=True)
        B.table(I.doc, ["O'qituvchi", "Kafedra", "Para", "Kirdi", "Kechikish"],
                [(x["name"], x["kafedra"], f"{x['slot']}-para ({x['first_para']})", x["arrival"], f"{x['minutes']} daq.") for x in f["late_teachers"][:25]], [5, 5, 3, 2, 2])
    elif f["late_teachers_n"]:
        B.para(I.doc, f"2. Birinchi darsiga kechikkan o'qituvchilar: {f['late_teachers_n']} nafar (ismlar jamlangan ko'rinishda ko'rsatilmaydi).", indent=False)
    if f["late_groups"]:
        B.para(I.doc, f"3. Birinchi para boshlangandan keyin kirgan talabalar ({f['late_students_n']}) — guruhlar", indent=False, bold=True)
        B.table(I.doc, ["Guruh", "Talabalar"], [(x["group"], x["n"]) for x in f["late_groups"]], [10, 4])
    if f.get("staff_after"):
        B.para(I.doc, f"4. {STAFF_START} dan keyin kelgan xodimlar ({f['staff_after_n']})", indent=False, bold=True)
        B.table(I.doc, ["Xodim", "Bo'lim", "Kirdi", "Kechikish"], [(x["name"], x["unit"], x["arrival"], f"{x['minutes']} daq.") for x in f["staff_after"][:25]], [5, 6, 2, 2])
    if f["night"]:
        B.para(I.doc, "5. Tungi kirishlar (xavfsizlik)", indent=False, bold=True)
        B.table(I.doc, ["Vaqt", "Kamera", "Holat"], [(x["ts"], x["camera"], x["status"]) for x in f["night"]], [3, 7, 5])
    B.para(I.doc, "Raqamlar ISFT Core bazasidagi kirish voqealaridan kod bilan hisoblangan (AI raqam qo'shmaydi). Faqat yozma roziligi bor shaxslar "
                  "aniqlanadi; rozilik bermaganlar va notanishlar ismsiz. Kechikish: o'qituvchi va talaba — dars jadvalidagi birinchi para boshlanishiga, "
                  f"xodim — {STAFF_START} ga nisbatan. DEMO: tasvirlar va voqealar sintetik.", indent=False, size=10)
    B.signature(I.doc, "Xo'jalik va texnik bo'lim boshlig'i")
    I.qr()
    r = I.save({"date": d.isoformat(), "scope": scope or "hammasi", "viewer_scope": f["scope_label"]})
    rbac.audit(con, ctx, "Face ID: Word hisobot", RES, True, f"{d} · {r['file']}")
    return {"ok": True, **r}

# ---------------------------------------------------------------------------------------------
# Umumiy ko'rinish (KPI, kameralar, kutubxona)
# ---------------------------------------------------------------------------------------------
def library(con) -> dict:
    c = Counter(); cons = Counter()
    for k, consent, rev in con.execute("SELECT kind, consent, revoked_at FROM face_persons"):
        c[k] += 1
        if consent: cons[k] += 1
    pend = con.execute("SELECT COUNT(*) FROM face_sync WHERE done_at IS NULL").fetchone()[0]
    rev = con.execute("SELECT COUNT(*) FROM face_persons WHERE revoked_at IS NOT NULL").fetchone()[0]
    return {"persons": dict(c), "consented": dict(cons), "total": sum(c.values()), "consented_total": sum(cons.values()), "revoked": rev,
            "sync_pending": pend, "match_min": round(100 * MATCH_MIN), "keep_days": KEEP_DAYS, "events_days": EVENTS_DAYS}

def summary(con, ctx: Ctx, date=None):
    ensure(con)
    d = _day(date)
    a = access(con, ctx, "umumiy ko'rinish", "health", str(d))
    t = now()
    rows = day_rows(con, d)
    cams = []
    for c in SF.entrance_cams(con):
        n = sum(1 for e in rows if e["camera_id"] == c["id"])
        cams.append({"id": c["id"], "name": c["name"], "model": c["model"], "mode": c["mode"], "status": c["status"], "detections": n,
                     "face_capable": (c["model"] or "").startswith("iDS-2CD7146")})
    out = {"date": d.isoformat(), "today": t.date().isoformat(), "now": iso(t), "mode": a.mode, "scope_label": a.scope_label(), "banner": BANNER,
           "cameras": cams, "library": library(con) if a.mode in ("health",) or a.role in ("rektor", "xojalik") else None,
           "can": {"ids": a.mode == "ids", "manage": list(a.manage), "report": a.mode in ("ids", "aggregate"), "unknown": a.unknown,
                   "kinds": list(a.kinds) if a.mode == "ids" else list(KINDS)},
           "detections": len(rows), "legend": {"talaba": "Talaba", "oqituvchi": "O'qituvchi", "xodim": "Xodim", "notanish": "Notanish / rozilik yo'q",
                                               "past_ishonch": f"Past ishonch (<{round(100 * MATCH_MIN)}%)"}}
    if a.mode in ("ids", "aggregate"):
        f = facts(con, a, d)
        out["kpi"] = {k: (f["unique"][k] if k in f["kinds"] else None) for k in KINDS}
        out["kpi"].update({
                      "notanish": f["unknown"] + f["no_consent"] if (a.unknown or a.mode == "aggregate") else None,
                      "late_teachers": f["late_teachers_n"] if ("oqituvchi" in a.kinds or a.mode == "aggregate") else None,
                      "late_students": f["late_students_n"] if ("talaba" in a.kinds or a.mode == "aggregate") else None,
                      "entries": f["entries"], "exits": f["exits"], "night": f["night_entries"] if (a.unknown or a.mode == "aggregate") else None})
        spark = []
        for i in range(13, -1, -1):
            x = d - dt.timedelta(days=i)
            r2 = _scope_rows(a, day_rows(con, x))
            spark.append({"date": x.isoformat(), "entries": sum(1 for e in r2 if e["direction"] == "kirish")})
        out["spark"] = spark
    else:
        st = Counter(e["status"] for e in rows)
        out["health"] = {"detections": len(rows), "matched_pct": round(100 * st["tanildi"] / len(rows), 1) if rows else 0,
                         "low_conf_pct": round(100 * st["past_ishonch"] / len(rows), 1) if rows else 0,
                         "last_event": rows[-1]["ts"] if rows else None}
    return out

# ---------------------------------------------------------------------------------------------
# Rozilik reyestri
# ---------------------------------------------------------------------------------------------
def persons(con, ctx: Ctx, q="", kind="", consent=""):
    ensure(con)
    a = access(con, ctx, "rozilik reyestri", "ids", q[:60], quiet=True)
    if not a.manage and a.role != "tyutor":
        raise AccessDenied("⛔ Rozilik reyestri — xo'jalik bo'limi, kadrlar bo'limi va rektor uchun.")
    rows = db.rows(con, "SELECT * FROM face_persons ORDER BY kind, name")
    vis = [p for p in rows if _visible(a, {"p_kind": p["kind"], "p_fac": p["faculty_id"], "status": "tanildi"})]
    if kind: vis = [p for p in vis if p["kind"] == kind]
    if consent in ("1", "0"): vis = [p for p in vis if bool(p["consent"]) == (consent == "1")]
    if q: vis = [p for p in vis if all(w in _norm(p["name"] + " " + (p["sub"] or "")) for w in _norm(q).split())]
    rbac.audit(con, ctx, "Face ID: rozilik reyestri", RES, True, f"{len(vis)} ta" + (f" · {q[:40]}" if q else ""))
    return {"persons": [{"id": p["id"], "kind": p["kind"], "kind_label": KIND_LABEL[p["kind"]], "name": p["name"], "sub": p["sub"],
                         "consent": bool(p["consent"]), "consent_doc": p["consent_doc"], "consent_at": p["consent_at"], "revoked_at": p["revoked_at"],
                         "enrolled": bool(p["fpid"]), "can_manage": p["kind"] in a.manage} for p in vis],
            "counts": {"total": len(vis), "consented": sum(1 for p in vis if p["consent"])}, "manage": list(a.manage)}

def set_consent(con, ctx: Ctx, pid: int, action: str, doc: str = ""):
    ensure(con)
    a = access(con, ctx, f"rozilik: {action}", "ids", f"shaxs #{pid}", quiet=True)
    p = db.one(con, "SELECT * FROM face_persons WHERE id=?", (pid,))
    if not p: raise HTTPException(404, "Shaxs topilmadi")
    if p["kind"] not in a.manage:
        rbac.audit(con, ctx, f"Face ID: rozilik ({action})", RES, False, f"{p['name']} — huquq yo'q")
        raise AccessDenied("⛔ Bu shaxs rozilagini boshqarish huquqi yo'q (talabalar — rektor/xo'jalik, o'qituvchi va xodimlar — kadrlar bo'limi ham). So'rov audit jurnaliga yozildi.")
    t = iso(now())
    if action == "revoke":
        if p["fpid"]:
            con.execute("INSERT INTO face_sync(op,fpid,person_id,created_at) VALUES('delete',?,?,?)", (p["fpid"], pid, t))
        con.execute("UPDATE face_persons SET consent=0, fpid=NULL, revoked_at=?, updated_by=? WHERE id=?", (t, ctx.title, pid))
        # ZRU-547: rozilik qaytarib olinsa — biometrik ishlov to'xtaydi; o'tgan yozuvlar shaxssizlantiriladi (bog'lanish o'chiriladi)
        n = con.execute("UPDATE face_events SET person_id=NULL, fpid=NULL, similarity=NULL, status='rozilik_yoq', look=abs(random()) % 10000000, female=NULL "
                        "WHERE person_id=?", (pid,)).rowcount
        detail = f"{p['name']}: rozilik qaytarib olindi, FPID o'chirildi, {n} ta o'tgan yozuv shaxssizlantirildi"
    elif action == "grant":
        doc = (doc or "").strip()
        if len(doc) < 3: raise HTTPException(400, "Yozma rozilik hujjati raqamini kiriting (masalan, RZ-2026/1234)")
        R = random.Random()
        fp = SF._fpid(R)
        while db.one(con, "SELECT 1 x FROM face_persons WHERE fpid=?", (fp,)): fp = SF._fpid(R)
        con.execute("UPDATE face_persons SET consent=1, fpid=?, consent_doc=?, consent_at=?, revoked_at=NULL, updated_by=? WHERE id=?",
                    (fp, doc[:60], t[:10], ctx.title, pid))
        con.execute("INSERT INTO face_sync(op,fpid,person_id,created_at) VALUES('add',?,?,?)", (fp, pid, t))
        detail = f"{p['name']}: yozma rozilik {doc[:60]} — yangi FPID berildi"
    else:
        raise HTTPException(400, "Noma'lum amal")
    con.commit()
    _VER[0] += 1
    rbac.audit(con, ctx, f"Face ID: rozilik ({'berildi' if action == 'grant' else 'qaytarib olindi'})", RES, True, detail)
    q = db.one(con, "SELECT id, consent, revoked_at, consent_doc, fpid IS NOT NULL enrolled FROM face_persons WHERE id=?", (pid,))
    return {"ok": True, "person": q, "note": detail}

def enroll(con, ctx: Ctx, kind: str, ref_id: int, doc: str):
    """Yangi shaxsni rozilik reyestriga qo'shish (yozma rozilik hujjati bilan)."""
    ensure(con)
    a = access(con, ctx, "rozilik: yangi shaxs", "ids", f"{kind} #{ref_id}", quiet=True)
    if kind not in a.manage:
        rbac.audit(con, ctx, "Face ID: yangi shaxs", RES, False, f"{kind} #{ref_id} — huquq yo'q")
        raise AccessDenied("⛔ Bu turdagi shaxsni ro'yxatga olish huquqi yo'q. So'rov audit jurnaliga yozildi.")
    ex = db.one(con, "SELECT id FROM face_persons WHERE kind=? AND ref_id=?", (kind, ref_id))
    if ex: return set_consent(con, ctx, ex["id"], "grant", doc)
    if kind == "talaba":
        r = db.one(con, "SELECT s.full_name name, g.name sub, s.faculty_id fac, NULL dep, s.group_id gid FROM students s JOIN groups_ g ON g.id=s.group_id WHERE s.id=?", (ref_id,))
    elif kind == "oqituvchi":
        r = db.one(con, "SELECT t.full_name name, d.name || ' kaf.' sub, t.faculty_id fac, t.department_id dep, NULL gid FROM teachers t JOIN departments d ON d.id=t.department_id WHERE t.id=?", (ref_id,))
    elif kind == "xodim":
        r = db.one(con, "SELECT full_name name, unit sub, NULL fac, NULL dep, NULL gid FROM staff WHERE id=?", (ref_id,))
    else:
        raise HTTPException(400, "Tur noto'g'ri")
    if not r: raise HTTPException(404, "Shaxs topilmadi")
    if SF._nkey(r["name"]) in SF.excluded_names(con):
        raise HTTPException(400, "Demo rejimida institut rahbarlari (haqiqiy shaxslar) ro'yxatga olinmaydi")
    pid = con.execute("INSERT INTO face_persons(kind,ref_id,name,sub,faculty_id,department_id,group_id,consent,avatar_seed,female,updated_by) VALUES(?,?,?,?,?,?,?,0,?,?,?)",
                      (kind, ref_id, r["name"], r["sub"], r["fac"], r["dep"], r["gid"], random.randint(1, 10 ** 7), SF._female(r["name"]), ctx.title)).lastrowid
    con.commit()
    return set_consent(con, ctx, pid, "grant", doc)

async def sync_cameras(con, ctx: Ctx):
    """Navbatdagi FDLib amallarini haqiqiy (isapi) kirish kameralariga yuboradi. Demo: haqiqiy kamera yo'q — navbat saqlanadi."""
    ensure(con)
    a = access(con, ctx, "yuz kutubxonasini sinxronlash", "health")
    if a.role not in ("rektor", "xojalik", "it_head"): raise AccessDenied("⛔ Sinxronlash — AT bo'limi, xo'jalik bo'limi va rektor.")
    from . import occupancy as OC, hikvision as HK
    cams = [c for c in SF.entrance_cams(con) if c["mode"] == "isapi"]
    q = db.rows(con, "SELECT * FROM face_sync WHERE done_at IS NULL ORDER BY id")
    if not cams:
        return {"ok": True, "cameras": 0, "pending": len(q), "note": "Haqiqiy Face ID kamera hali ulanmagan (demo: simulyator) — navbat saqlanadi, kamera ulanganda yuboriladi."}
    done, errs = 0, []
    for c in cams:
        cl = OC.cam_client(db.one(con, "SELECT * FROM cameras WHERE id=?", (c["id"],)))
        try:
            fdid = await cl.fdlib_ensure()
            for op in q:
                if op["op"] == "delete":
                    await cl.fdlib_delete(fdid, [op["fpid"]])
                else:
                    img = db.DATA_DIR / "face_enroll" / f"{op['fpid']}.jpg"
                    if not img.exists(): errs.append(f"{op['fpid']}: rozilikda olingan yuz rasmi yo'q"); continue
                    await cl.fdlib_add(fdid, op["fpid"], img.read_bytes())
                done += 1
        except HK.IsapiError as e:
            errs.append(f"{c['name']}: {e}")
    if not errs:
        con.execute("UPDATE face_sync SET done_at=?, result='ok' WHERE done_at IS NULL", (iso(now()),)); con.commit()
    return {"ok": not errs, "cameras": len(cams), "done": done, "errors": errs[:10]}

# ---------------------------------------------------------------------------------------------
# AI suhbat (agent.py) uchun
# ---------------------------------------------------------------------------------------------
def agent_tool(con, ctx: Ctx, quiet=False):
    ensure(con)
    a = access(con, ctx, "suhbat uchun faktlar", "aggregate", quiet=quiet)
    return facts(con, a, now().date())

def agent_facts(v: dict) -> dict:
    out = [narrative_template(v)]
    if v.get("late_teachers"):
        out.append("Kechikkan o'qituvchilar: " + "; ".join(f"{x['name']} ({x['kafedra']}) — {x['first_para']} dagi darsga {x['arrival']} da, {x['minutes']} daq."
                                                       for x in v["late_teachers"][:8]) + ".")
    u = v["unique"]
    names = {"talaba": "talabalar", "oqituvchi": "o'qituvchilar", "xodim": "xodimlar"}
    out.append("Bugun binoga kirgan (aniqlangan) " + ", ".join(f"{names[k]}: {u[k]}" for k in v.get("kinds") or KINDS) + f" — ko'lam: {v['scope_label'].lower()}.")
    recs = [{"text": "Kameralar → «Kirish (Face ID)» bo'limida kadrlar va shaxs tarixini ko'ring; Word hisobotni yuklab oling.",
             "action": {"type": "go", "view": "cams", "label": "Kirish (Face ID)"}}]
    return {"facts": out, "why": [], "recs": recs, "sev": 2 if (v["late_teachers_n"] or v["night_entries"]) else 1,
            "head": f"kirish nazorati: {v['entries']} kirish, {v['late_teachers_n']} o'qituvchi kechikkan"}

# ---------------------------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------------------------
def bind(con, ctx_fn):
    global _con, _ctx
    _con, _ctx = con, ctx_fn

@router.get("/api/face/summary")
def api_summary(request: Request, date: str = ""):
    return summary(_con, _ctx(request), date or None)

@router.get("/api/face/frames")
def api_frames(request: Request, date: str = "", camera: int = 0, kind: str = "", q: str = "", offset: int = 0, limit: int = 24):
    return frames(_con, _ctx(request), date or None, camera, kind, q, offset, limit)

@router.get("/api/face/frames/{fid}")
def api_frame(fid: int, request: Request):
    return frame_detail(_con, _ctx(request), fid)

@router.get("/api/face/events/{eid}/image")
def api_image(eid: int, request: Request, w: int = 0):
    jpg = event_image(_con, _ctx(request), eid, w)
    return Response(jpg, media_type="image/jpeg", headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"})

@router.get("/api/face/persons/{pid}/timeline")
def api_timeline(pid: int, request: Request, days: int = 14):
    return timeline(_con, _ctx(request), pid, days)

@router.get("/api/face/persons")
def api_persons(request: Request, q: str = "", kind: str = "", consent: str = ""):
    return persons(_con, _ctx(request), q, kind, consent)

class ConsentIn(BaseModel):
    action: str = Field(..., pattern="^(grant|revoke)$")
    doc: str = Field("", max_length=60)

@router.post("/api/face/persons/{pid}/consent")
def api_consent(pid: int, body: ConsentIn, request: Request):
    return set_consent(_con, _ctx(request), pid, body.action, body.doc)

class EnrollIn(BaseModel):
    kind: str = Field(..., pattern="^(talaba|oqituvchi|xodim)$")
    ref_id: int
    doc: str = Field(..., min_length=3, max_length=60)

@router.post("/api/face/persons")
def api_enroll(body: EnrollIn, request: Request):
    return enroll(_con, _ctx(request), body.kind, body.ref_id, body.doc)

@router.get("/api/face/report")
async def api_report(request: Request, date: str = "", scope: str = ""):
    return await report(_con, _ctx(request), date or None, scope)

class DocxIn(BaseModel):
    date: str = ""
    scope: str = ""

@router.post("/api/face/report/docx")
def api_docx(request: Request, body: DocxIn | None = None):
    b = body or DocxIn()
    return build_docx(_con, _ctx(request), str(request.base_url), b.date or None, b.scope)

@router.post("/api/face/sync")
async def api_sync(request: Request):
    return await sync_cameras(_con, _ctx(request))
