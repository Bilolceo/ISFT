"""«Yoshlar ishlari» — turar joy (hamkor yotoqxonalar, ijara monitoringi) va tadbirlar (docs/yoshlar.md).

Institutning o'z yotoqxonasi yo'q (NQAAE pasporti). Shuning uchun talabalar turar joyi ikki yo'l bilan yuritiladi:
  1. Hamkor yotoqxonalar — shartnoma asosida ajratilgan joylar: bino → xona → o'rin; ariza → imtiyoz bo'yicha navbat →
     joy biriktirish (bron) → joylashish → chiqish; oylik to'lov hisoblash va to'langanini qo'lda belgilash; tartib buzilishi qaydlari.
  2. Ijarada yashovchi talabalar — manzil va tyutor tashrifi (akt).
Tadbirlar: reja → tasdiqlashga yuborish → prorektor tasdig'i → o'tkazish (ishtirokchilar) → hisobot.
Talaba kabineti (/talaba): yotoqxonaga ariza, holat, to'lovlar; tasdiqlangan tadbirlarga yozilish.
Ruxsat: rol kalitiga qarab rejim (mode); har bir murojaat rbac.audit(resource="youth").
"""
import datetime as dt, random, threading
from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel, Field
from . import clock, db, rbac
from .rbac import Ctx, AccessDenied

router = APIRouter()
_con = None
_ctx = None
_lock = threading.Lock()
RES = rbac.YOUTH
P = "/api/yoshlar"

# ---------------------------------------------------------------------------------------------
# Qoidalar («*» — institut nizomi bilan tasdiqlanadi, docs/yoshlar.md)
# ---------------------------------------------------------------------------------------------
CATS = {   # * imtiyozli toifalar (ariza beruvchi belgilaydi, xodim hujjatlarini tekshiradi)
    "yetim": ("Chin yetim yoki ota-ona qaramog'idan mahrum", 40),
    "nogironlik": ("Nogironligi bor", 35),
    "daftar": ("Ijtimoiy himoya reyestrida (Temir / Ayollar / Yoshlar daftari)", 30),
    "kop_bolali": ("Ko'p bolali yoki kam ta'minlangan oila", 15),
}
AUTO = {"uzoq_hudud": ("Toshkentdan tashqari hududdan", 20), "birinchi_kurs": ("1-kurs talabasi", 10), "alochi": ("A'lochi (o'rtacha ball ≥ 86)", 5)}
NEAR = ("Toshkent sh.",)              # * Toshkent shahrida yashovchilar — faqat imtiyozli toifa bo'lsa
RULES = {"due_day": 10,               # * oylik to'lov — shu oyning 10-sanasigacha
         "violations_warn": 3,        # * 3 ta qayd — chiqarish masalasi ko'riladi
         "reserve_days": 7}           # * bron qilingan o'ringa shu muddatda joylashmasa — bron bekor qilinadi (ogohlantirish)
APP_ST = {"yangi": "Yangi (hujjat tekshiruvi)", "navbatda": "Navbatda", "joy_berildi": "Joy berildi", "rad": "Rad etildi", "bekor": "Bekor qilindi"}
RES_ST = {"band": "Bron (joylashmagan)", "yashaydi": "Yashaydi", "chiqdi": "Chiqib ketgan", "bekor": "Bron bekor qilingan"}
OUT_REASONS = ["O'z xohishi bilan", "O'qishni tamomladi", "Akademik ta'tilga chiqdi", "O'qishdan chetlashtirildi", "Tartib buzilishi (chiqarish)", "Boshqa"]
VIOL_KINDS = ["Kechki tartibni buzish", "Spirtli ichimlik", "Chekish", "Mol-mulkka zarar", "Ruxsatsiz mehmon", "Janjal", "Sanitariya talablari", "Boshqa"]
MEASURES = {"ogohlantirish": "Ogohlantirish", "hayfsan": "Hayfsan", "chiqarish": "Yotoqxonadan chiqarish"}
EV_ST = {"reja": "Reja", "tasdiqlashda": "Tasdiqlashda", "tasdiqlangan": "Tasdiqlangan", "rad": "Rad etilgan", "otkazildi": "O'tkazildi"}
EV_KINDS = {"ma'naviy": "Ma'naviy-ma'rifiy", "sport": "Sport", "intellektual": "Intellektual", "karyera": "Karyera", "madaniy": "Madaniy", "volontyorlik": "Volontyorlik"}
GENDER = {"M": "Yigitlar", "F": "Qizlar"}

SCHEMA = """
CREATE TABLE IF NOT EXISTS yj_buildings(id INTEGER PRIMARY KEY, name TEXT, kind TEXT DEFAULT 'hamkor', address TEXT, partner TEXT,
  contract_no TEXT, contract_until TEXT, gender TEXT, fee_month INT, active INT DEFAULT 1, created_at TEXT);
CREATE TABLE IF NOT EXISTS yj_rooms(id INTEGER PRIMARY KEY, building_id INT, number TEXT, floor INT, beds INT, gender TEXT, note TEXT,
  UNIQUE(building_id, number));
CREATE TABLE IF NOT EXISTS yj_applications(id INTEGER PRIMARY KEY, student_id INT, submitted_at TEXT, channel TEXT, cats TEXT, auto TEXT, score INT,
  verified INT DEFAULT 0, verified_by INT, status TEXT, reason TEXT, note TEXT, decided_by INT, decided_at TEXT, created_by INT);
CREATE INDEX IF NOT EXISTS ix_yja_st ON yj_applications(status, score);
CREATE INDEX IF NOT EXISTS ix_yja_stu ON yj_applications(student_id);
CREATE TABLE IF NOT EXISTS yj_residents(id INTEGER PRIMARY KEY, student_id INT, application_id INT, room_id INT, bed_no INT, reserved_at TEXT,
  check_in TEXT, check_out TEXT, status TEXT, out_reason TEXT, by_user INT);
CREATE INDEX IF NOT EXISTS ix_yjr_room ON yj_residents(room_id, status);
CREATE INDEX IF NOT EXISTS ix_yjr_stu ON yj_residents(student_id, status);
CREATE TABLE IF NOT EXISTS yj_charges(id INTEGER PRIMARY KEY, resident_id INT, period TEXT, amount INT, due TEXT, paid INT DEFAULT 0, paid_at TEXT,
  receipt TEXT, by_user INT, UNIQUE(resident_id, period));
CREATE TABLE IF NOT EXISTS yj_violations(id INTEGER PRIMARY KEY, resident_id INT, student_id INT, date TEXT, kind TEXT, text TEXT, measure TEXT,
  by_user INT, at TEXT);
CREATE TABLE IF NOT EXISTS yj_rentals(id INTEGER PRIMARY KEY, student_id INT UNIQUE, address TEXT, district TEXT, rent INT, since TEXT,
  has_contract INT DEFAULT 0, last_visit TEXT, visit_note TEXT, condition TEXT, visited_by INT, created_by INT, created_at TEXT);
"""
EVENT_COLS = [("status", "TEXT"), ("venue", "TEXT"), ("start_time", "TEXT"), ("audience", "TEXT"), ("capacity", "INT"), ("budget", "INT"),
              ("plan_note", "TEXT"), ("organizer", "TEXT"), ("created_by", "INT"), ("created_at", "TEXT"), ("submitted_at", "TEXT"),
              ("approved_by", "INT"), ("approved_at", "TEXT"), ("reject_reason", "TEXT"), ("report", "TEXT"), ("held_at", "TEXT"), ("held_by", "INT")]

def _today(): return clock.today()
def _now(): return clock.now_iso()
def _bad(msg, code=400): raise HTTPException(code, msg)
def _short(n): return (n or "").split(":", 1)[1].strip() if ":" in (n or "") else (n or "")
def _date(v, label="Sana"):
    try: return dt.date.fromisoformat(str(v)[:10]).isoformat()
    except (TypeError, ValueError): _bad(f"{label} noto'g'ri: {v}")
def _period(v):
    v = str(v or "")[:7]
    try: dt.date.fromisoformat(v + "-01"); return v
    except ValueError: _bad(f"Oy noto'g'ri (YYYY-MM): {v}")

# ---------------------------------------------------------------------------------------------
# Rejim va ruxsat
# ---------------------------------------------------------------------------------------------
NEW_ROLES = [   # (rol, ism, unit, kod) — demo akkauntlar (sintetik ismlar)
    ("manaviyat", "Ma'naviyat va ma'rifat bo'limi boshlig'i: Karimova Dilfuza Anvar qizi", "manaviyat", "MANAVIYAT"),
    ("komendant", "Talabalar turar joyi komendanti: Xolmatov Baxrom Ergash o'g'li", "komendant", "KOMENDANT"),
]
MODES = {"prorektor_yoshlar": "lead", "manaviyat": "staff", "komendant": "komendant", "buxgalteriya": "bux", "tyutor": "tyutor",
         "rektor": "view", "talabalar": "view"}
ALL_TABS = ["umumiy", "arizalar", "joylar", "tolov", "tartib", "ijara", "tadbirlar"]
TAB_TITLES = {"umumiy": "Umumiy", "arizalar": "Arizalar va navbat", "joylar": "Yotoqxonalar", "tolov": "To'lovlar", "tartib": "Tartib qaydlari",
              "ijara": "Ijarada yashovchilar", "tadbirlar": "Tadbirlar"}
TABS = {"lead": ALL_TABS, "staff": ALL_TABS, "view": ALL_TABS, "tyutor": ALL_TABS,
        "komendant": ["umumiy", "arizalar", "joylar", "tolov", "tartib", "ijara"], "bux": ["tolov"]}
MODE_NOTE = {"lead": "To'liq boshqaruv va tasdiqlash", "staff": "Turar joy va tadbirlarni yuritish", "komendant": "Yotoqxona: joylashtirish, to'lov, tartib",
             "bux": "Faqat yotoqxona to'lovlari", "tyutor": "O'z guruhlaringiz talabalari (o'qish) · ijara tashrifi", "view": "Faqat ko'rish"}
# amal → ruxsat etilgan rejimlar
CAN = {
    "apply": ("lead", "staff", "komendant"),
    "dorm": ("lead", "staff", "komendant"),           # tekshirish, joy berish, rad, joylashish, chiqish, bino/xona
    "bulk": ("lead", "staff"),
    "charge": ("lead", "staff", "komendant", "bux"),
    "pay": ("komendant", "bux"),
    "violation": ("lead", "staff", "komendant"),
    "expel": ("lead",),
    "rental": ("lead", "staff", "tyutor"),
    "event": ("lead", "staff"),
    "approve": ("lead",),
}
REGISTRAR_APPLY = ("talabalar",)   # Registrator ofisi — talaba nomidan ariza kirita oladi (view rejimida bo'lsa ham)

def mode(c: Ctx): return MODES.get(c.role.key)

def guard(c: Ctx, tab: str, action: str, detail: str = "", need: str | None = None) -> str:
    m = mode(c)
    ok = m is not None and (tab == "meta" or tab in TABS[m])
    if ok and need:
        ok = m in CAN[need] or (need == "apply" and c.role.key in REGISTRAR_APPLY)
    rbac.audit(_con, c, f"yoshlar: {action}", RES, ok, detail)
    if not ok:
        why = (f"«{TAB_TITLES.get(tab, tab)}» bo'limi lavozimingiz uchun yopiq" if m and tab not in TABS[m] and tab != "meta" else
               "bu amal lavozimingiz uchun emas" if m else f"«{c.role.title}» lavozimi uchun ruxsat yo'q")
        raise AccessDenied(f"⛔ Yoshlar ishlari: {why}. So'rov audit jurnaliga yozildi.")
    return m

def st_scope(c: Ctx, alias="s"):
    if mode(c) == "tyutor":
        return f"{alias}.group_id IN (SELECT group_id FROM tutor_groups WHERE user_id={int(c.user['id'])})"
    return "1=1"

def _in_scope(c: Ctx, sid: int):
    if not db.one(_con, f"SELECT 1 x FROM students s WHERE s.id=? AND {st_scope(c)}", (sid,)):
        raise AccessDenied("⛔ Yoshlar ishlari: bu talaba sizning guruhlaringizda emas.")

# ---------------------------------------------------------------------------------------------
# Ariza bali va navbat
# ---------------------------------------------------------------------------------------------
STU_SQL = """SELECT s.id, s.full_name, s.hemis_id, s.gender, s.region, s.status, s.study_form, s.gpa, s.phone, g.name grp, g.course, f.name faculty
             FROM students s LEFT JOIN groups_ g ON g.id=s.group_id LEFT JOIN faculties f ON f.id=s.faculty_id"""

def auto_cats(s) -> list:
    out = []
    if s.get("region") and s["region"] not in ("Toshkent sh.", "Toshkent vil."): out.append("uzoq_hudud")
    if s.get("course") == 1: out.append("birinchi_kurs")
    if (s.get("gpa") or 0) >= 86: out.append("alochi")
    return out

def score_of(cats, auto) -> int:
    return sum(CATS[k][1] for k in cats if k in CATS) + sum(AUTO[k][1] for k in auto if k in AUTO)

def eligibility(s, cats) -> str | None:
    """None — ariza berish mumkin; aks holda sabab."""
    if s["status"] != "faol": return "Ariza faqat faol talabalar uchun"
    if s.get("study_form") != "kunduzgi": return "Yotoqxona faqat kunduzgi ta'lim talabalari uchun"
    if s.get("region") in NEAR and not [k for k in cats if k in CATS]:
        return "Toshkent shahrida yashovchi talabaga joy faqat imtiyozli toifa bo'lsa beriladi"
    return None

def _split(v): return [x for x in (v or "").split(",") if x]

def _app_row(r):
    cats, auto = _split(r.get("cats")), _split(r.get("auto"))
    r["cats_l"] = [CATS[k][0] for k in cats if k in CATS]
    r["auto_l"] = [AUTO[k][0] for k in auto if k in AUTO]
    r["cats"], r["auto"] = cats, auto
    r["status_l"] = APP_ST.get(r["status"], r["status"])
    r["gender_l"] = GENDER.get(r.get("gender"), "")
    return r

def create_application(c: Ctx | None, sid: int, cats: list, note: str, channel: str) -> dict:
    cats = [k for k in dict.fromkeys(cats or []) if k in CATS]
    with _lock:
        s = db.one(_con, STU_SQL + " WHERE s.id=?", (sid,))
        if not s: _bad("Talaba topilmadi", 404)
        why = eligibility(s, cats)
        if why: _bad(why)
        if db.one(_con, "SELECT 1 x FROM yj_applications WHERE student_id=? AND status IN ('yangi','navbatda')", (sid,)):
            _bad("Bu talabaning ko'rib chiqilayotgan arizasi bor")
        if db.one(_con, "SELECT 1 x FROM yj_residents WHERE student_id=? AND status IN ('band','yashaydi')", (sid,)):
            _bad("Talaba allaqachon yotoqxonada joy olgan")
        auto = auto_cats(s)
        verified = 0 if cats else 1      # imtiyoz da'vo qilinmasa — tekshiradigan hujjat yo'q
        cur = _con.execute("""INSERT INTO yj_applications(student_id,submitted_at,channel,cats,auto,score,verified,status,note,created_by)
                              VALUES(?,?,?,?,?,?,?,?,?,?)""",
                           (sid, _now(), channel, ",".join(cats), ",".join(auto), score_of(cats, auto), verified,
                            "yangi" if cats else "navbatda", (note or "")[:500], c.user["id"] if c else None))
        _con.commit()
        return {"id": cur.lastrowid, "status": "yangi" if cats else "navbatda", "score": score_of(cats, auto)}

def queue_rows(c: Ctx, status="", q="", limit=300):
    w, a = [st_scope(c)], []
    if status == "navbat": w.append("a.status IN ('yangi','navbatda')")
    elif status in APP_ST: w.append("a.status=?"); a.append(status)
    if q: w.append("(s.full_name LIKE ? OR s.hemis_id LIKE ?)"); a += [f"%{q}%", f"{q}%"]
    rs = db.rows(_con, f"""SELECT a.*, s.full_name, s.hemis_id, s.gender, s.region, g.name grp, g.course,
          r.id resident_id, r.status res_status, rm.number room, b.name building
        FROM yj_applications a JOIN students s ON s.id=a.student_id LEFT JOIN groups_ g ON g.id=s.group_id
        LEFT JOIN yj_residents r ON r.application_id=a.id AND r.status IN ('band','yashaydi')
        LEFT JOIN yj_rooms rm ON rm.id=r.room_id LEFT JOIN yj_buildings b ON b.id=rm.building_id
        WHERE {' AND '.join(w)} ORDER BY CASE WHEN a.status IN ('yangi','navbatda') THEN 0 ELSE 1 END, a.score DESC, a.submitted_at LIMIT ?""", a + [limit])
    pos = {r["id"]: i + 1 for i, r in enumerate(db.rows(_con, "SELECT id FROM yj_applications WHERE status IN ('yangi','navbatda') ORDER BY score DESC, submitted_at"))}
    for r in rs:
        _app_row(r); r["position"] = pos.get(r["id"])
    return rs

# ---------------------------------------------------------------------------------------------
# Joylar
# ---------------------------------------------------------------------------------------------
def free_beds(gender=None, room_id=None) -> list:
    """Bo'sh o'rinlar: (room_id, bed_no) — bino faol, xona jinsi mos."""
    w, a = ["b.active=1"], []
    if gender: w.append("rm.gender=?"); a.append(gender)
    if room_id: w.append("rm.id=?"); a.append(room_id)
    out = []
    for rm in db.rows(_con, f"""SELECT rm.id, rm.beds FROM yj_rooms rm JOIN yj_buildings b ON b.id=rm.building_id WHERE {' AND '.join(w)}
                                ORDER BY b.id, rm.floor, rm.number""", a):
        taken = {x["bed_no"] for x in db.rows(_con, "SELECT bed_no FROM yj_residents WHERE room_id=? AND status IN ('band','yashaydi')", (rm["id"],))}
        out += [(rm["id"], b) for b in range(1, rm["beds"] + 1) if b not in taken]
    return out

def allocate(c: Ctx | None, aid: int, room_id: int | None = None, when: str | None = None) -> dict:
    with _lock:
        a = db.one(_con, "SELECT a.*, s.gender, s.status sst FROM yj_applications a JOIN students s ON s.id=a.student_id WHERE a.id=?", (aid,))
        if not a: _bad("Ariza topilmadi", 404)
        if a["status"] not in ("yangi", "navbatda"): _bad(f"Ariza holati: {APP_ST.get(a['status'])} — joy berib bo'lmaydi")
        if not a["verified"]: _bad("Avval imtiyoz hujjatlarini tekshiring («Hujjatlar tekshirildi»)")
        if a["sst"] != "faol": _bad("Talaba faol emas")
        if room_id:
            rm = db.one(_con, "SELECT * FROM yj_rooms WHERE id=?", (room_id,))
            if not rm: _bad("Xona topilmadi", 404)
            if rm["gender"] != a["gender"]: _bad(f"Xona {GENDER.get(rm['gender'], '').lower()} uchun — talabaning jinsiga mos emas")
        beds = free_beds(a["gender"], room_id)
        if not beds: _bad("Bu xonada bo'sh o'rin yo'q" if room_id else f"{GENDER.get(a['gender'])} uchun bo'sh o'rin yo'q — ariza navbatda qoladi")
        rid, bed = beds[0]
        at = when or _now()
        cur = _con.execute("INSERT INTO yj_residents(student_id,application_id,room_id,bed_no,reserved_at,status,by_user) VALUES(?,?,?,?,?,?,?)",
                           (a["student_id"], aid, rid, bed, at, "band", c.user["id"] if c else None))
        _con.execute("UPDATE yj_applications SET status='joy_berildi', decided_by=?, decided_at=? WHERE id=?", (c.user["id"] if c else None, at, aid))
        _con.commit()
        r = db.one(_con, "SELECT rm.number, b.name building FROM yj_rooms rm JOIN yj_buildings b ON b.id=rm.building_id WHERE rm.id=?", (rid,))
        return {"resident_id": cur.lastrowid, "room": r["number"], "building": r["building"], "bed": bed}

def allocate_waitlist(c: Ctx) -> dict:
    done, skipped = [], 0
    for a in db.rows(_con, "SELECT id FROM yj_applications WHERE status IN ('yangi','navbatda') AND verified=1 ORDER BY score DESC, submitted_at"):
        try: done.append(allocate(c, a["id"]))
        except HTTPException: skipped += 1
    return {"allocated": len(done), "left": skipped}

def buildings(c: Ctx) -> list:
    out = []
    for b in db.rows(_con, "SELECT * FROM yj_buildings ORDER BY id"):
        rooms = db.rows(_con, """SELECT rm.*, (SELECT COUNT(*) FROM yj_residents r WHERE r.room_id=rm.id AND r.status='yashaydi') live,
                                 (SELECT COUNT(*) FROM yj_residents r WHERE r.room_id=rm.id AND r.status='band') res
                                 FROM yj_rooms rm WHERE rm.building_id=? ORDER BY rm.floor, rm.number""", (b["id"],))
        cap = sum(r["beds"] for r in rooms); live = sum(r["live"] for r in rooms); res = sum(r["res"] for r in rooms)
        for r in rooms: r["free"] = r["beds"] - r["live"] - r["res"]; r["gender_l"] = GENDER.get(r["gender"], "")
        b.update(rooms=rooms, capacity=cap, live=live, reserved=res, free=cap - live - res, pct=round(100 * (live + res) / cap, 1) if cap else 0,
                 gender_l=GENDER.get(b["gender"], "Aralash"),
                 contract_days=(dt.date.fromisoformat(b["contract_until"]) - _today()).days if b.get("contract_until") else None)
        out.append(b)
    return out

def residents(c: Ctx, status="", q="", building=0, limit=400):
    w, a = [st_scope(c)], []
    if status in RES_ST: w.append("r.status=?"); a.append(status)
    elif status == "faol": w.append("r.status IN ('band','yashaydi')")
    if building: w.append("rm.building_id=?"); a.append(building)
    if q: w.append("(s.full_name LIKE ? OR s.hemis_id LIKE ? OR rm.number=?)"); a += [f"%{q}%", f"{q}%", q]
    today = _today().isoformat()
    rs = db.rows(_con, f"""SELECT r.*, s.full_name, s.hemis_id, s.status sst, s.gender, g.name grp, g.course, rm.number room, rm.floor, b.name building, b.id building_id,
          (SELECT COALESCE(SUM(ch.amount-ch.paid),0) FROM yj_charges ch WHERE ch.resident_id=r.id AND ch.due<? AND ch.paid<ch.amount) debt,
          (SELECT COUNT(*) FROM yj_violations v WHERE v.resident_id=r.id) viol
        FROM yj_residents r JOIN students s ON s.id=r.student_id LEFT JOIN groups_ g ON g.id=s.group_id
        JOIN yj_rooms rm ON rm.id=r.room_id JOIN yj_buildings b ON b.id=rm.building_id
        WHERE {' AND '.join(w)} ORDER BY b.id, rm.floor, rm.number, r.bed_no LIMIT ?""", [today] + a + [limit])
    for r in rs:
        r["status_l"] = RES_ST.get(r["status"], r["status"])
        r["mismatch"] = r["status"] in ("band", "yashaydi") and r["sst"] != "faol"
        r["overdue_reserve"] = r["status"] == "band" and r["reserved_at"] and (_today() - dt.date.fromisoformat(r["reserved_at"][:10])).days > RULES["reserve_days"]
    return rs

def _resident(rid):
    r = db.one(_con, "SELECT r.*, s.full_name FROM yj_residents r JOIN students s ON s.id=r.student_id WHERE r.id=?", (rid,))
    if not r: _bad("Yashovchi topilmadi", 404)
    return r

def check_in(c, rid, date=None):
    with _lock:
        r = _resident(rid)
        if r["status"] != "band": _bad(f"Holat: {RES_ST.get(r['status'])} — joylashtirib bo'lmaydi")
        _con.execute("UPDATE yj_residents SET status='yashaydi', check_in=? WHERE id=?", (_date(date) if date else _today().isoformat(), rid)); _con.commit()
    return {"ok": True}

def check_out(c, rid, reason, date=None):
    if reason not in OUT_REASONS: _bad("Chiqish sababini tanlang")
    with _lock:
        r = _resident(rid)
        if r["status"] != "yashaydi": _bad(f"Holat: {RES_ST.get(r['status'])} — chiqarib bo'lmaydi")
        _con.execute("UPDATE yj_residents SET status='chiqdi', check_out=?, out_reason=? WHERE id=?", (_date(date) if date else _today().isoformat(), reason, rid))
        _con.commit()
    return {"ok": True}

def cancel_reserve(c, rid, requeue=True):
    with _lock:
        r = _resident(rid)
        if r["status"] != "band": _bad("Faqat bron (joylashmagan) bekor qilinadi")
        _con.execute("UPDATE yj_residents SET status='bekor', check_out=? WHERE id=?", (_today().isoformat(), rid))
        if r["application_id"]:
            _con.execute("UPDATE yj_applications SET status=? WHERE id=?", ("navbatda" if requeue else "bekor", r["application_id"]))
        _con.commit()
    return {"ok": True}

# ---------------------------------------------------------------------------------------------
# To'lovlar
# ---------------------------------------------------------------------------------------------
def generate_charges(c: Ctx | None, period: str) -> dict:
    period = _period(period)
    due = f"{period}-{RULES['due_day']:02d}"
    first = period + "-01"
    n = 0
    with _lock:
        for r in db.rows(_con, """SELECT r.id, b.fee_month FROM yj_residents r JOIN yj_rooms rm ON rm.id=r.room_id JOIN yj_buildings b ON b.id=rm.building_id
                                  WHERE r.status IN ('yashaydi','chiqdi') AND r.check_in IS NOT NULL AND r.check_in<=?
                                    AND (r.check_out IS NULL OR r.check_out>=?)""", (f"{period}-31", first)):
            cur = _con.execute("INSERT OR IGNORE INTO yj_charges(resident_id,period,amount,due) VALUES(?,?,?,?)", (r["id"], period, r["fee_month"], due))
            n += cur.rowcount
        _con.commit()
    return {"period": period, "created": n}

def charges(c: Ctx, period="", only_debt=False, q="", limit=500):
    w, a = [st_scope(c)], []
    if period: w.append("ch.period=?"); a.append(_period(period))
    if only_debt: w.append("ch.paid<ch.amount AND ch.due<?"); a.append(_today().isoformat())
    if q: w.append("(s.full_name LIKE ? OR s.hemis_id LIKE ?)"); a += [f"%{q}%", f"{q}%"]
    rs = db.rows(_con, f"""SELECT ch.*, s.full_name, s.hemis_id, g.name grp, rm.number room, b.name building, u.full_name by_name
        FROM yj_charges ch JOIN yj_residents r ON r.id=ch.resident_id JOIN students s ON s.id=r.student_id LEFT JOIN groups_ g ON g.id=s.group_id
        JOIN yj_rooms rm ON rm.id=r.room_id JOIN yj_buildings b ON b.id=rm.building_id LEFT JOIN users u ON u.id=ch.by_user
        WHERE {' AND '.join(w)} ORDER BY ch.period DESC, (ch.amount-ch.paid) DESC, s.full_name LIMIT ?""", a + [limit])
    t = _today().isoformat()
    for r in rs:
        r["state"] = "tolangan" if r["paid"] >= r["amount"] else ("qarz" if r["due"] < t else "kutilmoqda")
        r["by_name"] = _short(r.get("by_name"))
    tot = db.one(_con, f"""SELECT COALESCE(SUM(ch.amount),0) amt, COALESCE(SUM(ch.paid),0) paid,
          COALESCE(SUM(CASE WHEN ch.due<? AND ch.paid<ch.amount THEN ch.amount-ch.paid END),0) debt,
          COUNT(DISTINCT CASE WHEN ch.due<? AND ch.paid<ch.amount THEN r.id END) debtors
        FROM yj_charges ch JOIN yj_residents r ON r.id=ch.resident_id JOIN students s ON s.id=r.student_id
        WHERE {' AND '.join(w)}""", [t, t] + a)
    periods = [x["period"] for x in db.rows(_con, "SELECT DISTINCT period FROM yj_charges ORDER BY period DESC")]
    return {"items": rs, "total": tot, "periods": periods}

def pay(c: Ctx, cid: int, amount: int | None, receipt: str):
    receipt = (receipt or "").strip()[:60]
    if not receipt: _bad("Kvitansiya / to'lov hujjati raqamini kiriting")
    with _lock:
        ch = db.one(_con, "SELECT * FROM yj_charges WHERE id=?", (cid,))
        if not ch: _bad("Hisob topilmadi", 404)
        left = ch["amount"] - ch["paid"]
        if left <= 0: _bad("Bu oy uchun to'lov allaqachon to'liq")
        amt = left if amount is None else int(amount)
        if amt <= 0 or amt > left: _bad(f"Summa 1 … {left} so'm oralig'ida bo'lishi kerak")
        _con.execute("UPDATE yj_charges SET paid=paid+?, paid_at=?, receipt=?, by_user=? WHERE id=?", (amt, _now(), receipt, c.user["id"], cid)); _con.commit()
    return {"ok": True, "paid": ch["paid"] + amt, "left": left - amt}

# ---------------------------------------------------------------------------------------------
# Tartib
# ---------------------------------------------------------------------------------------------
def add_violation(c: Ctx | None, rid: int, kind: str, text: str, measure: str, date=None, by=None):
    if kind not in VIOL_KINDS: _bad("Qoidabuzarlik turini tanlang")
    if measure not in MEASURES: _bad("Choralardan birini tanlang")
    text = (text or "").strip()
    if len(text) < 5: _bad("Qisqacha tavsif yozing (kamida 5 belgi)")
    r = _resident(rid)
    if r["status"] not in ("yashaydi",): _bad("Qayd faqat yashovchi uchun")
    with _lock:
        cur = _con.execute("INSERT INTO yj_violations(resident_id,student_id,date,kind,text,measure,by_user,at) VALUES(?,?,?,?,?,?,?,?)",
                           (rid, r["student_id"], _date(date) if date else _today().isoformat(), kind, text[:500], measure,
                            by or (c.user["id"] if c else None), _now()))
        _con.commit()
    if measure == "chiqarish":
        check_out(c, rid, "Tartib buzilishi (chiqarish)", date)
    n = db.one(_con, "SELECT COUNT(*) n FROM yj_violations WHERE resident_id=?", (rid,))["n"]
    return {"id": cur.lastrowid, "count": n, "warn": n >= RULES["violations_warn"]}

def violations(c: Ctx, q=""):
    w, a = [st_scope(c)], []
    if q: w.append("(s.full_name LIKE ? OR s.hemis_id LIKE ?)"); a += [f"%{q}%", f"{q}%"]
    rs = db.rows(_con, f"""SELECT v.*, s.full_name, g.name grp, rm.number room, b.name building, u.full_name by_name, r.status res_status,
          (SELECT COUNT(*) FROM yj_violations v2 WHERE v2.resident_id=v.resident_id) total
        FROM yj_violations v JOIN students s ON s.id=v.student_id LEFT JOIN groups_ g ON g.id=s.group_id
        JOIN yj_residents r ON r.id=v.resident_id JOIN yj_rooms rm ON rm.id=r.room_id JOIN yj_buildings b ON b.id=rm.building_id
        LEFT JOIN users u ON u.id=v.by_user WHERE {' AND '.join(w)} ORDER BY v.date DESC, v.id DESC LIMIT 300""", a)
    for r in rs: r["measure_l"] = MEASURES.get(r["measure"], r["measure"]); r["by_name"] = _short(r.get("by_name"))
    return rs

# ---------------------------------------------------------------------------------------------
# Ijara
# ---------------------------------------------------------------------------------------------
def rentals(c: Ctx, q="", stale=False):
    w, a = [st_scope(c)], []
    if q: w.append("(s.full_name LIKE ? OR s.hemis_id LIKE ? OR x.district LIKE ?)"); a += [f"%{q}%", f"{q}%", f"%{q}%"]
    lim = (_today() - dt.timedelta(days=90)).isoformat()
    if stale: w.append("(x.last_visit IS NULL OR x.last_visit<?)"); a.append(lim)
    rs = db.rows(_con, f"""SELECT x.*, s.full_name, s.hemis_id, s.region, g.name grp, g.course, u.full_name visited_name
        FROM yj_rentals x JOIN students s ON s.id=x.student_id LEFT JOIN groups_ g ON g.id=s.group_id LEFT JOIN users u ON u.id=x.visited_by
        WHERE {' AND '.join(w)} AND s.status='faol' ORDER BY COALESCE(x.last_visit,'0000'), s.full_name LIMIT 400""", a)
    for r in rs: r["stale"] = not r["last_visit"] or r["last_visit"] < lim; r["visited_name"] = _short(r.get("visited_name"))
    return rs

def add_rental(c: Ctx, sid: int, address: str, district: str, rent: int, since: str, has_contract: bool):
    address, district = (address or "").strip(), (district or "").strip()
    if len(address) < 5 or not district: _bad("Manzil va tumanni kiriting")
    _in_scope(c, sid)
    with _lock:
        if db.one(_con, "SELECT 1 x FROM yj_residents WHERE student_id=? AND status IN ('band','yashaydi')", (sid,)):
            _bad("Talaba yotoqxonada joy olgan — ijara qaydi kerak emas")
        _con.execute("""INSERT INTO yj_rentals(student_id,address,district,rent,since,has_contract,created_by,created_at) VALUES(?,?,?,?,?,?,?,?)
                        ON CONFLICT(student_id) DO UPDATE SET address=excluded.address, district=excluded.district, rent=excluded.rent,
                          since=excluded.since, has_contract=excluded.has_contract""",
                     (sid, address[:200], district[:80], max(0, int(rent or 0)), _date(since) if since else _today().isoformat(), int(bool(has_contract)), c.user["id"], _now()))
        _con.commit()
    return {"ok": True}

def visit_rental(c: Ctx, xid: int, note: str, condition: str, date=None, by=None):
    if condition not in ("yaxshi", "qoniqarli", "qoniqarsiz"): _bad("Sharoit bahosini tanlang")
    note = (note or "").strip()
    if len(note) < 5: _bad("Tashrif bo'yicha qisqa izoh yozing")
    x = db.one(_con, "SELECT * FROM yj_rentals WHERE id=?", (xid,))
    if not x: _bad("Qayd topilmadi", 404)
    if c: _in_scope(c, x["student_id"])
    with _lock:
        _con.execute("UPDATE yj_rentals SET last_visit=?, visit_note=?, condition=?, visited_by=? WHERE id=?",
                     (_date(date) if date else _today().isoformat(), note[:500], condition, by or (c.user["id"] if c else None), xid))
        _con.commit()
    return {"ok": True}

# ---------------------------------------------------------------------------------------------
# Tadbirlar
# ---------------------------------------------------------------------------------------------
def _ev(eid):
    e = db.one(_con, "SELECT * FROM events WHERE id=?", (eid,))
    if not e: _bad("Tadbir topilmadi", 404)
    return e

def _ev_row(e):
    e["status_l"] = EV_ST.get(e.get("status"), e.get("status"))
    e["kind_l"] = EV_KINDS.get(e.get("kind"), e.get("kind"))
    return e

def events(c: Ctx, status=""):
    w, a = ["1=1"], []
    if status in EV_ST: w.append("e.status=?"); a.append(status)
    sc = st_scope(c)
    rs = db.rows(_con, f"""SELECT e.*, (SELECT COUNT(*) FROM event_reg r JOIN students s ON s.id=r.student_id WHERE r.event_id=e.id AND {sc}) reg,
          (SELECT COUNT(*) FROM event_checkin k JOIN students s ON s.id=k.student_id WHERE k.event_id=e.id AND {sc}) came,
          u.full_name approved_name FROM events e LEFT JOIN users u ON u.id=e.approved_by
        WHERE {' AND '.join(w)} ORDER BY CASE e.status WHEN 'tasdiqlashda' THEN 0 WHEN 'tasdiqlangan' THEN 1 WHEN 'reja' THEN 2 ELSE 3 END, e.date DESC""", a)
    for e in rs: _ev_row(e); e["approved_name"] = _short(e.get("approved_name"))
    return rs

def event_detail(c: Ctx, eid: int):
    e = _ev_row(_ev(eid))
    sc = st_scope(c)
    e["people"] = db.rows(_con, f"""SELECT s.id, s.full_name, g.name grp, (r.student_id IS NOT NULL) reg, (k.student_id IS NOT NULL) came
        FROM students s LEFT JOIN groups_ g ON g.id=s.group_id
        LEFT JOIN event_reg r ON r.event_id=? AND r.student_id=s.id LEFT JOIN event_checkin k ON k.event_id=? AND k.student_id=s.id
        WHERE (r.student_id IS NOT NULL OR k.student_id IS NOT NULL) AND {sc} ORDER BY s.full_name LIMIT 500""", (eid, eid))
    e["by_faculty"] = db.rows(_con, f"""SELECT f.name, COUNT(*) n FROM event_checkin k JOIN students s ON s.id=k.student_id JOIN faculties f ON f.id=s.faculty_id
        WHERE k.event_id=? AND {sc} GROUP BY f.id ORDER BY n DESC""", (eid,))
    return e

class EventIn(BaseModel):
    title: str = Field("", max_length=200)
    date: str = ""
    start_time: str = Field("", max_length=5)
    venue: str = Field("", max_length=120)
    kind: str = "ma'naviy"
    audience: str = Field("", max_length=160)
    capacity: int = 0
    budget: int = 0
    plan_note: str = Field("", max_length=1000)
    organizer: str = Field("", max_length=120)

def create_event(c: Ctx, b: EventIn):
    if len(b.title.strip()) < 4: _bad("Tadbir nomini kiriting")
    if b.kind not in EV_KINDS: _bad("Tadbir turini tanlang")
    d = _date(b.date, "Tadbir sanasi")
    if d < _today().isoformat(): _bad("Tadbir sanasi o'tib ketgan")
    with _lock:
        cur = _con.execute("""INSERT INTO events(title,date,kind,participants,status,venue,start_time,audience,capacity,budget,plan_note,organizer,created_by,created_at)
                              VALUES(?,?,?,0,'reja',?,?,?,?,?,?,?,?,?)""",
                           (b.title.strip(), d, b.kind, b.venue.strip(), b.start_time[:5], b.audience.strip(), max(0, b.capacity), max(0, b.budget),
                            b.plan_note.strip(), b.organizer.strip() or _short(c.user["full_name"]), c.user["id"], _now()))
        _con.commit()
    return {"id": cur.lastrowid}

def ev_transition(c: Ctx, eid: int, to: str, reason="", report="", participants=None):
    with _lock:
        e = _ev(eid)
        st = e.get("status")
        if to == "tasdiqlashda":
            if st not in ("reja", "rad"): _bad(f"Holat: {EV_ST.get(st)} — tasdiqlashga yuborib bo'lmaydi")
            if not (e.get("venue") and e.get("start_time")): _bad("Joy va vaqtni ko'rsating — keyin yuboring")
            _con.execute("UPDATE events SET status='tasdiqlashda', submitted_at=?, reject_reason=NULL WHERE id=?", (_now(), eid))
        elif to == "tasdiqlangan":
            if st != "tasdiqlashda": _bad("Faqat tasdiqlashdagi tadbir tasdiqlanadi")
            _con.execute("UPDATE events SET status='tasdiqlangan', approved_by=?, approved_at=? WHERE id=?", (c.user["id"], _now(), eid))
        elif to == "rad":
            if st != "tasdiqlashda": _bad("Faqat tasdiqlashdagi tadbir rad etiladi")
            if len((reason or "").strip()) < 5: _bad("Rad etish sababini yozing")
            _con.execute("UPDATE events SET status='rad', reject_reason=? WHERE id=?", (reason.strip()[:500], eid))
        elif to == "otkazildi":
            if st != "tasdiqlangan": _bad("Faqat tasdiqlangan tadbir o'tkazilgan deb belgilanadi")
            if e["date"] > _today().isoformat(): _bad("Tadbir sanasi hali kelmagan")
            if len((report or "").strip()) < 20: _bad("Hisobot yozing (kamida 20 belgi): nima qilindi, natija")
            came = db.one(_con, "SELECT COUNT(*) n FROM event_checkin WHERE event_id=?", (eid,))["n"]
            n = max(came, int(participants or 0))
            _con.execute("UPDATE events SET status='otkazildi', report=?, participants=?, held_at=?, held_by=? WHERE id=?",
                         (report.strip()[:3000], n, _now(), c.user["id"], eid))
        else: _bad("Noma'lum amal")
        _con.commit()
    return {"ok": True, "status": to}

def ev_people(c: Ctx, eid: int, ids: list, attend: bool):
    e = _ev(eid)
    if e.get("status") not in ("tasdiqlangan", "otkazildi"): _bad("Ishtirokchilar faqat tasdiqlangan tadbirga qo'shiladi")
    if attend and e["date"] > _today().isoformat(): _bad("Qatnashuv tadbir kuni belgilanadi")
    ids = [int(i) for i in dict.fromkeys(ids or [])][:500]
    n = 0
    with _lock:
        for sid in ids:
            if not db.one(_con, "SELECT 1 x FROM students WHERE id=? AND status='faol'", (sid,)): continue
            if attend:
                n += _con.execute("INSERT OR IGNORE INTO event_checkin(event_id,student_id,ts) VALUES(?,?,?)", (eid, sid, _now())).rowcount
            else:
                if e.get("capacity") and db.one(_con, "SELECT COUNT(*) n FROM event_reg WHERE event_id=?", (eid,))["n"] >= e["capacity"]:
                    _bad(f"Joylar to'lgan ({e['capacity']})")
                n += _con.execute("INSERT OR IGNORE INTO event_reg(event_id,student_id) VALUES(?,?)", (eid, sid)).rowcount
        _con.commit()
    return {"added": n}

# ---------------------------------------------------------------------------------------------
# Umumiy
# ---------------------------------------------------------------------------------------------
def overview(c: Ctx):
    sc = st_scope(c)
    bs = buildings(c)
    t = _today().isoformat()
    q1 = lambda sql, a=(): db.one(_con, sql, a)["n"]
    k = {
        "capacity": sum(b["capacity"] for b in bs), "live": sum(b["live"] for b in bs), "reserved": sum(b["reserved"] for b in bs),
        "free_m": len(free_beds("M")), "free_f": len(free_beds("F")),
        "queue": q1(f"SELECT COUNT(*) n FROM yj_applications a JOIN students s ON s.id=a.student_id WHERE a.status IN ('yangi','navbatda') AND {sc}"),
        "unverified": q1(f"SELECT COUNT(*) n FROM yj_applications a JOIN students s ON s.id=a.student_id WHERE a.status='yangi' AND a.verified=0 AND {sc}"),
        "debt": db.one(_con, f"""SELECT COALESCE(SUM(ch.amount-ch.paid),0) n FROM yj_charges ch JOIN yj_residents r ON r.id=ch.resident_id
                                JOIN students s ON s.id=r.student_id WHERE ch.due<? AND ch.paid<ch.amount AND {sc}""", (t,))["n"],
        "debtors": q1(f"""SELECT COUNT(DISTINCT r.id) n FROM yj_charges ch JOIN yj_residents r ON r.id=ch.resident_id JOIN students s ON s.id=r.student_id
                         WHERE ch.due<? AND ch.paid<ch.amount AND {sc}""", (t,)),
        "viol30": q1(f"SELECT COUNT(*) n FROM yj_violations v JOIN students s ON s.id=v.student_id WHERE v.date>=? AND {sc}", ((_today() - dt.timedelta(days=30)).isoformat(),)),
        "rentals": q1(f"SELECT COUNT(*) n FROM yj_rentals x JOIN students s ON s.id=x.student_id WHERE s.status='faol' AND {sc}"),
        "rent_stale": q1(f"SELECT COUNT(*) n FROM yj_rentals x JOIN students s ON s.id=x.student_id WHERE s.status='faol' AND {sc} AND (x.last_visit IS NULL OR x.last_visit<?)",
                         ((_today() - dt.timedelta(days=90)).isoformat(),)),
        "ev_pending": q1("SELECT COUNT(*) n FROM events WHERE status='tasdiqlashda'"),
        "ev_upcoming": q1("SELECT COUNT(*) n FROM events WHERE status='tasdiqlangan' AND date>=?", (t,)),
        "ev_noreport": q1("SELECT COUNT(*) n FROM events WHERE status='tasdiqlangan' AND date<?", (t,)),
    }
    alerts = []
    rs = residents(c, "faol")
    mism = [r for r in rs if r["mismatch"]]
    if mism: alerts.append({"level": "bad", "tab": "joylar", "text": f"{len(mism)} ta yashovchi endi faol talaba emas (chetlashtirilgan / ta'tilda / bitirgan) — chiqarishni rasmiylashtiring"})
    over = [r for r in rs if r["overdue_reserve"]]
    if over: alerts.append({"level": "warn", "tab": "joylar", "text": f"{len(over)} ta bron {RULES['reserve_days']} kundan ortiq joylashmagan — bronni bekor qilib, navbatdagiga bering"})
    for b in bs:
        if b["contract_days"] is not None and b["contract_days"] < 60:
            alerts.append({"level": "warn" if b["contract_days"] >= 0 else "bad", "tab": "joylar",
                           "text": f"{b['name']}: hamkorlik shartnomasi {'muddati o' + chr(39) + 'tgan' if b['contract_days'] < 0 else str(b['contract_days']) + ' kundan keyin tugaydi'}"})
    if k["unverified"]: alerts.append({"level": "info", "tab": "arizalar", "text": f"{k['unverified']} ta arizada imtiyoz hujjatlari tekshirilmagan"})
    if k["queue"] and (k["free_m"] or k["free_f"]): alerts.append({"level": "info", "tab": "arizalar", "text": f"Navbatda {k['queue']} ta ariza, bo'sh o'rin: yigitlar {k['free_m']}, qizlar {k['free_f']}"})
    if k["ev_noreport"]: alerts.append({"level": "warn", "tab": "tadbirlar", "text": f"{k['ev_noreport']} ta tadbir o'tgan, lekin hisobot topshirilmagan"})
    if k["ev_pending"]: alerts.append({"level": "info", "tab": "tadbirlar", "text": f"{k['ev_pending']} ta tadbir prorektor tasdig'ini kutmoqda"})
    many = db.rows(_con, f"""SELECT s.full_name, COUNT(*) n FROM yj_violations v JOIN yj_residents r ON r.id=v.resident_id JOIN students s ON s.id=v.student_id
                             WHERE r.status='yashaydi' AND {sc} GROUP BY v.resident_id HAVING n>=?""", (RULES["violations_warn"],))
    if many: alerts.append({"level": "warn", "tab": "tartib", "text": f"{len(many)} ta yashovchida {RULES['violations_warn']} va undan ko'p qayd — chiqarish masalasini ko'ring"})
    return {"kpi": k, "buildings": [{x: b[x] for x in ("id", "name", "capacity", "live", "reserved", "free", "pct", "gender_l")} for b in bs], "alerts": alerts}

def meta(c: Ctx):
    m = mode(c)
    return {"mode": m, "mode_note": MODE_NOTE[m], "role": c.role.key, "scope": "O'z guruhlaringiz" if m == "tyutor" else "Butun institut",
            "tabs": [{"key": t, "title": TAB_TITLES[t]} for t in TABS[m]], "today": _today().isoformat(),
            "caps": {k: (m in v or (k == "apply" and c.role.key in REGISTRAR_APPLY)) for k, v in CAN.items()},
            "cats": {k: {"label": v[0], "points": v[1]} for k, v in CATS.items()}, "auto": {k: {"label": v[0], "points": v[1]} for k, v in AUTO.items()},
            "app_st": APP_ST, "res_st": RES_ST, "out_reasons": OUT_REASONS, "viol_kinds": VIOL_KINDS, "measures": MEASURES,
            "ev_st": EV_ST, "ev_kinds": EV_KINDS, "rules": RULES}

# =============================================================================================
# HTTP — xodimlar
# =============================================================================================
def C(request: Request) -> Ctx: return _ctx(request)

class AppIn(BaseModel):
    student_id: int
    cats: list[str] = []
    note: str = Field("", max_length=500)
class AllocIn(BaseModel):
    room_id: int | None = None
class ReasonIn(BaseModel):
    reason: str = Field("", max_length=500)
class DateIn(BaseModel):
    date: str = ""
class OutIn(BaseModel):
    reason: str = ""
    date: str = ""
class BuildingIn(BaseModel):
    name: str = Field("", max_length=120)
    address: str = Field("", max_length=200)
    partner: str = Field("", max_length=160)
    contract_no: str = Field("", max_length=60)
    contract_until: str = ""
    gender: str = ""
    fee_month: int = 0
class RoomIn(BaseModel):
    number: str = Field("", max_length=12)
    floor: int = 1
    beds: int = 3
    gender: str = "M"
class PeriodIn(BaseModel):
    period: str = ""
class PayIn(BaseModel):
    amount: int | None = None
    receipt: str = Field("", max_length=60)
class ViolIn(BaseModel):
    resident_id: int
    kind: str = ""
    text: str = Field("", max_length=500)
    measure: str = "ogohlantirish"
    date: str = ""
class RentalIn(BaseModel):
    student_id: int
    address: str = Field("", max_length=200)
    district: str = Field("", max_length=80)
    rent: int = 0
    since: str = ""
    has_contract: bool = False
class VisitIn(BaseModel):
    note: str = Field("", max_length=500)
    condition: str = ""
    date: str = ""
class IdsIn(BaseModel):
    student_ids: list[int] = []
class HoldIn(BaseModel):
    report: str = Field("", max_length=3000)
    participants: int = 0

@router.get(P + "/meta")
def api_meta(request: Request):
    c = C(request); guard(c, "meta", "bo'lim ochildi"); return meta(c)

@router.get(P + "/overview")
def api_overview(request: Request):
    c = C(request); guard(c, "umumiy", "umumiy ko'rinish"); return overview(c)

@router.get(P + "/lookup/students")
def api_lookup(request: Request, q: str = ""):
    c = C(request); guard(c, "meta", "talaba qidiruvi", q[:40])
    q = q.strip()[:60]
    if len(q) < 2: return []
    rs = db.rows(_con, STU_SQL + f" WHERE {st_scope(c)} AND s.status='faol' AND (s.full_name LIKE ? OR s.hemis_id LIKE ?) ORDER BY s.full_name LIMIT 15",
                 (f"%{q}%", f"{q}%"))
    for r in rs: r["gender_l"] = GENDER.get(r["gender"], ""); r.pop("phone", None); r.pop("gpa", None)
    return rs

@router.get(P + "/applications")
def api_apps(request: Request, status: str = "navbat", q: str = ""):
    c = C(request); guard(c, "arizalar", "arizalar ro'yxati", status); return queue_rows(c, status, q.strip()[:60])

@router.post(P + "/applications")
def api_app_new(body: AppIn, request: Request):
    c = C(request); guard(c, "arizalar", "ariza kiritish", f"talaba #{body.student_id}", need="apply")
    return create_application(c, body.student_id, body.cats, body.note, "xodim")

@router.post(P + "/applications/{aid}/verify")
def api_app_verify(aid: int, request: Request):
    c = C(request); guard(c, "arizalar", "imtiyoz hujjatlari tekshirildi", f"#{aid}", need="dorm")
    a = db.one(_con, "SELECT * FROM yj_applications WHERE id=?", (aid,))
    if not a: _bad("Ariza topilmadi", 404)
    if a["status"] != "yangi": _bad("Faqat yangi ariza tekshiriladi")
    _con.execute("UPDATE yj_applications SET verified=1, verified_by=?, status='navbatda' WHERE id=?", (c.user["id"], aid)); _con.commit()
    return {"ok": True}

@router.post(P + "/applications/{aid}/allocate")
def api_app_alloc(aid: int, body: AllocIn, request: Request):
    c = C(request); guard(c, "arizalar", "joy berish", f"#{aid}", need="dorm"); return allocate(c, aid, body.room_id)

@router.post(P + "/applications/{aid}/reject")
def api_app_reject(aid: int, body: ReasonIn, request: Request):
    c = C(request); guard(c, "arizalar", "ariza rad etildi", f"#{aid}", need="dorm")
    if len(body.reason.strip()) < 5: _bad("Rad etish sababini yozing")
    a = db.one(_con, "SELECT * FROM yj_applications WHERE id=?", (aid,))
    if not a: _bad("Ariza topilmadi", 404)
    if a["status"] not in ("yangi", "navbatda"): _bad("Bu ariza allaqachon hal qilingan")
    _con.execute("UPDATE yj_applications SET status='rad', reason=?, decided_by=?, decided_at=? WHERE id=?", (body.reason.strip(), c.user["id"], _now(), aid))
    _con.commit(); return {"ok": True}

@router.post(P + "/allocate-waitlist")
def api_alloc_all(request: Request):
    c = C(request); guard(c, "arizalar", "navbat bo'yicha avtomatik joylashtirish", need="bulk"); return allocate_waitlist(c)

@router.get(P + "/buildings")
def api_buildings(request: Request):
    c = C(request); guard(c, "joylar", "yotoqxonalar"); return buildings(c)

@router.post(P + "/buildings")
def api_building_new(body: BuildingIn, request: Request):
    c = C(request); guard(c, "joylar", "yotoqxona qo'shildi", body.name[:60], need="dorm")
    if len(body.name.strip()) < 3 or body.fee_month <= 0: _bad("Nomi va oylik to'lov summasini kiriting")
    if body.gender not in ("", "M", "F"): _bad("Jins noto'g'ri")
    cur = _con.execute("""INSERT INTO yj_buildings(name,kind,address,partner,contract_no,contract_until,gender,fee_month,created_at) VALUES(?,?,?,?,?,?,?,?,?)""",
                       (body.name.strip(), "hamkor", body.address.strip(), body.partner.strip(), body.contract_no.strip(),
                        _date(body.contract_until, "Shartnoma muddati") if body.contract_until else None, body.gender or None, body.fee_month, _now()))
    _con.commit(); return {"id": cur.lastrowid}

@router.post(P + "/buildings/{bid}/rooms")
def api_room_new(bid: int, body: RoomIn, request: Request):
    c = C(request); guard(c, "joylar", "xona qo'shildi", f"bino #{bid} · {body.number}", need="dorm")
    b = db.one(_con, "SELECT * FROM yj_buildings WHERE id=?", (bid,))
    if not b: _bad("Bino topilmadi", 404)
    if not body.number.strip() or not 1 <= body.beds <= 8: _bad("Xona raqami va o'rinlar soni (1–8) kerak")
    if body.gender not in ("M", "F") or (b["gender"] and b["gender"] != body.gender): _bad("Xona jinsi bino bilan mos emas")
    try:
        cur = _con.execute("INSERT INTO yj_rooms(building_id,number,floor,beds,gender) VALUES(?,?,?,?,?)", (bid, body.number.strip(), body.floor, body.beds, body.gender))
        _con.commit()
    except Exception: _bad("Bu raqamli xona allaqachon bor")
    return {"id": cur.lastrowid}

@router.get(P + "/residents")
def api_residents(request: Request, status: str = "faol", q: str = "", building: int = 0):
    c = C(request); guard(c, "joylar", "yashovchilar", status); return residents(c, status, q.strip()[:60], building)

@router.post(P + "/residents/{rid}/checkin")
def api_checkin(rid: int, body: DateIn, request: Request):
    c = C(request); guard(c, "joylar", "joylashdi", f"#{rid}", need="dorm"); return check_in(c, rid, body.date or None)

@router.post(P + "/residents/{rid}/checkout")
def api_checkout(rid: int, body: OutIn, request: Request):
    c = C(request); guard(c, "joylar", "chiqib ketdi", f"#{rid} · {body.reason}", need="dorm")
    if body.reason == "Tartib buzilishi (chiqarish)" and mode(c) not in CAN["expel"]:
        raise AccessDenied("⛔ Yoshlar ishlari: tartib buzilishi uchun chiqarish — faqat prorektor qarori bilan.")
    return check_out(c, rid, body.reason, body.date or None)

@router.post(P + "/residents/{rid}/cancel")
def api_cancel(rid: int, request: Request):
    c = C(request); guard(c, "joylar", "bron bekor qilindi", f"#{rid}", need="dorm"); return cancel_reserve(c, rid)

@router.get(P + "/charges")
def api_charges(request: Request, period: str = "", debt: int = 0, q: str = ""):
    c = C(request); guard(c, "tolov", "to'lovlar", period); return charges(c, period, bool(debt), q.strip()[:60])

@router.post(P + "/charges/generate")
def api_charges_gen(body: PeriodIn, request: Request):
    c = C(request); guard(c, "tolov", "oylik hisob yaratildi", body.period, need="charge"); return generate_charges(c, body.period or _today().isoformat()[:7])

@router.post(P + "/charges/{cid}/pay")
def api_pay(cid: int, body: PayIn, request: Request):
    c = C(request); guard(c, "tolov", "to'lov belgilandi", f"#{cid} · {body.receipt}", need="pay"); return pay(c, cid, body.amount, body.receipt)

@router.get(P + "/violations")
def api_viol(request: Request, q: str = ""):
    c = C(request); guard(c, "tartib", "tartib qaydlari"); return violations(c, q.strip()[:60])

@router.post(P + "/violations")
def api_viol_new(body: ViolIn, request: Request):
    c = C(request); guard(c, "tartib", "tartib qaydi", f"yashovchi #{body.resident_id} · {body.measure}", need="violation")
    if body.measure == "chiqarish" and mode(c) not in CAN["expel"]:
        raise AccessDenied("⛔ Yoshlar ishlari: yotoqxonadan chiqarish — faqat prorektor qarori bilan.")
    return add_violation(c, body.resident_id, body.kind, body.text, body.measure, body.date or None)

@router.get(P + "/rentals")
def api_rentals(request: Request, q: str = "", stale: int = 0):
    c = C(request); guard(c, "ijara", "ijarada yashovchilar"); return rentals(c, q.strip()[:60], bool(stale))

@router.post(P + "/rentals")
def api_rental_new(body: RentalIn, request: Request):
    c = C(request); guard(c, "ijara", "ijara qaydi", f"talaba #{body.student_id}", need="rental")
    return add_rental(c, body.student_id, body.address, body.district, body.rent, body.since, body.has_contract)

@router.post(P + "/rentals/{xid}/visit")
def api_rental_visit(xid: int, body: VisitIn, request: Request):
    c = C(request); guard(c, "ijara", "ijara tashrifi", f"#{xid}", need="rental"); return visit_rental(c, xid, body.note, body.condition, body.date or None)

@router.get(P + "/events")
def api_events(request: Request, status: str = ""):
    c = C(request); guard(c, "tadbirlar", "tadbirlar"); return events(c, status)

@router.get(P + "/events/{eid}")
def api_event(eid: int, request: Request):
    c = C(request); guard(c, "tadbirlar", "tadbir", f"#{eid}"); return event_detail(c, eid)

@router.post(P + "/events")
def api_event_new(body: EventIn, request: Request):
    c = C(request); guard(c, "tadbirlar", "tadbir rejalashtirildi", body.title[:60], need="event"); return create_event(c, body)

@router.post(P + "/events/{eid}/submit")
def api_event_submit(eid: int, request: Request):
    c = C(request); guard(c, "tadbirlar", "tadbir tasdiqlashga yuborildi", f"#{eid}", need="event"); return ev_transition(c, eid, "tasdiqlashda")

@router.post(P + "/events/{eid}/approve")
def api_event_approve(eid: int, request: Request):
    c = C(request); guard(c, "tadbirlar", "tadbir tasdiqlandi", f"#{eid}", need="approve"); return ev_transition(c, eid, "tasdiqlangan")

@router.post(P + "/events/{eid}/reject")
def api_event_reject(eid: int, body: ReasonIn, request: Request):
    c = C(request); guard(c, "tadbirlar", "tadbir rad etildi", f"#{eid}", need="approve"); return ev_transition(c, eid, "rad", reason=body.reason)

@router.post(P + "/events/{eid}/participants")
def api_event_reg(eid: int, body: IdsIn, request: Request):
    c = C(request); guard(c, "tadbirlar", "ishtirokchi yozildi", f"#{eid} · {len(body.student_ids)}", need="event"); return ev_people(c, eid, body.student_ids, False)

@router.post(P + "/events/{eid}/attend")
def api_event_attend(eid: int, body: IdsIn, request: Request):
    c = C(request); guard(c, "tadbirlar", "qatnashuv belgilandi", f"#{eid} · {len(body.student_ids)}", need="event"); return ev_people(c, eid, body.student_ids, True)

@router.post(P + "/events/{eid}/hold")
def api_event_hold(eid: int, body: HoldIn, request: Request):
    c = C(request); guard(c, "tadbirlar", "tadbir o'tkazildi (hisobot)", f"#{eid}", need="event")
    return ev_transition(c, eid, "otkazildi", report=body.report, participants=body.participants)

# =============================================================================================
# HTTP — talaba kabineti (/talaba)
# =============================================================================================
def _stp(): from . import student_portal as STP; return STP

def _student_audit(s, action, ok=True, detail=""):
    try: _stp()._audit(action, ok, s, detail, resource=RES)
    except Exception: pass

class StuAppIn(BaseModel):
    cats: list[str] = []
    note: str = Field("", max_length=500)

@router.get("/api/talaba/turarjoy")
def api_stu_dorm(request: Request):
    s = _stp().student(request)
    app = db.one(_con, "SELECT * FROM yj_applications WHERE student_id=? ORDER BY id DESC LIMIT 1", (s["id"],))
    if app:
        _app_row(app)
        if app["status"] in ("yangi", "navbatda"):
            app["position"] = db.one(_con, """SELECT COUNT(*)+1 n FROM yj_applications WHERE status IN ('yangi','navbatda')
                                              AND (score>? OR (score=? AND submitted_at<?))""", (app["score"], app["score"], app["submitted_at"]))["n"]
    res = db.one(_con, """SELECT r.*, rm.number room, rm.floor, b.name building, b.address, b.fee_month FROM yj_residents r JOIN yj_rooms rm ON rm.id=r.room_id
                          JOIN yj_buildings b ON b.id=rm.building_id WHERE r.student_id=? AND r.status IN ('band','yashaydi') ORDER BY r.id DESC LIMIT 1""", (s["id"],))
    ch, viol = [], []
    if res:
        res["status_l"] = RES_ST[res["status"]]
        t = _today().isoformat()
        ch = db.rows(_con, "SELECT period, amount, paid, due, paid_at, receipt FROM yj_charges WHERE resident_id=? ORDER BY period DESC", (res["id"],))
        for x in ch: x["state"] = "tolangan" if x["paid"] >= x["amount"] else ("qarz" if x["due"] < t else "kutilmoqda")
        viol = db.rows(_con, "SELECT date, kind, measure FROM yj_violations WHERE resident_id=? ORDER BY date DESC", (res["id"],))
        for v in viol: v["measure_l"] = MEASURES.get(v["measure"], v["measure"])
    full = db.one(_con, STU_SQL + " WHERE s.id=?", (s["id"],))
    auto = auto_cats(full)
    return {"application": app, "resident": res, "charges": ch, "violations": viol, "debt": sum(max(0, x["amount"] - x["paid"]) for x in ch if x["state"] == "qarz"),
            "eligible": eligibility(full, ["yetim"]) is None, "why_not": eligibility(full, []),
            "near": s.get("region") in NEAR, "cats": {k: v[0] for k, v in CATS.items()}, "auto": [AUTO[k][0] for k in auto],
            "office": "Ma'naviyat va ma'rifat bo'limi", "rules": RULES}

@router.post("/api/talaba/turarjoy")
def api_stu_dorm_apply(body: StuAppIn, request: Request):
    s = _stp().student(request)
    try: r = create_application(None, s["id"], body.cats, body.note, "kabinet")
    except HTTPException as e:
        _student_audit(s, "yotoqxonaga ariza", False, str(e.detail)); raise
    _student_audit(s, "yotoqxonaga ariza", True, f"#{r['id']} · ball {r['score']}")
    return r

@router.post("/api/talaba/turarjoy/cancel")
def api_stu_dorm_cancel(request: Request):
    s = _stp().student(request)
    a = db.one(_con, "SELECT id FROM yj_applications WHERE student_id=? AND status IN ('yangi','navbatda') ORDER BY id DESC LIMIT 1", (s["id"],))
    if not a: _bad("Bekor qilinadigan ariza yo'q")
    _con.execute("UPDATE yj_applications SET status='bekor', decided_at=? WHERE id=?", (_now(), a["id"])); _con.commit()
    _student_audit(s, "yotoqxona arizasi bekor qilindi", True, f"#{a['id']}")
    return {"ok": True}

@router.get("/api/talaba/tadbirlar")
def api_stu_events(request: Request):
    s = _stp().student(request)
    rs = db.rows(_con, """SELECT e.id, e.title, e.date, e.start_time, e.venue, e.kind, e.capacity, e.audience,
          (SELECT COUNT(*) FROM event_reg r WHERE r.event_id=e.id) reg,
          EXISTS(SELECT 1 FROM event_reg r WHERE r.event_id=e.id AND r.student_id=?) mine,
          EXISTS(SELECT 1 FROM event_checkin k WHERE k.event_id=e.id AND k.student_id=?) came
        FROM events e WHERE e.status='tasdiqlangan' AND e.date>=? ORDER BY e.date, e.start_time""", (s["id"], s["id"], _today().isoformat()))
    past = db.rows(_con, """SELECT e.id, e.title, e.date, e.kind FROM events e JOIN event_checkin k ON k.event_id=e.id AND k.student_id=?
                            ORDER BY e.date DESC LIMIT 20""", (s["id"],))
    for e in rs + past: e["kind_l"] = EV_KINDS.get(e["kind"], e["kind"])
    return {"upcoming": rs, "attended": past}

@router.post("/api/talaba/tadbirlar/{eid}/register")
def api_stu_event_reg(eid: int, request: Request):
    s = _stp().student(request)
    e = db.one(_con, "SELECT * FROM events WHERE id=?", (eid,))
    if not e or e.get("status") != "tasdiqlangan" or e["date"] < _today().isoformat(): _bad("Bu tadbirga yozilib bo'lmaydi")
    if s["status"] != "faol": _bad("Faqat faol talabalar yoziladi")
    if e.get("capacity") and db.one(_con, "SELECT COUNT(*) n FROM event_reg WHERE event_id=?", (eid,))["n"] >= e["capacity"]: _bad("Joylar to'lgan")
    _con.execute("INSERT OR IGNORE INTO event_reg(event_id,student_id) VALUES(?,?)", (eid, s["id"])); _con.commit()
    _student_audit(s, "tadbirga yozildi", True, f"#{eid}")
    return {"ok": True}

# =============================================================================================
# init / seed
# =============================================================================================
def init(con):
    try:
        con.executescript(SCHEMA)
        have = {r["name"] for r in db.rows(con, "PRAGMA table_info(events)")}
        if not have: return
        for col, typ in EVENT_COLS:
            if col not in have: con.execute(f"ALTER TABLE events ADD COLUMN {col} {typ}")
        con.commit()
    except Exception as e:
        print("yoshlar.init:", e); return
    if not db.one(con, "SELECT 1 x FROM users"): return
    for role, name, unit, code in NEW_ROLES:
        if not db.one(con, "SELECT 1 x FROM users WHERE role=?", (role,)):
            con.execute("INSERT INTO users(full_name,role,unit,link_code,pin) VALUES(?,?,?,?,?)", (name, role, unit, code, rbac.hash_password(rbac.DEMO_PASSWORD)))
    # komendant — alohida bo'lim «Talabalar turar joyi» (portal EXTRA_UNITS, kurator — yoshlar prorektori); eski bazalarda manaviyat edi
    con.execute("UPDATE users SET unit='komendant' WHERE role='komendant' AND unit='manaviyat'")
    con.commit()
    try:
        from . import portal as PT
        PT.sync_units(con)
    except Exception as e:
        print("yoshlar.sync_units:", repr(e))
    # eski tadbirlar (holatsiz) — o'tkazilgan deb hisoblanadi
    con.execute("UPDATE events SET status=CASE WHEN date<? THEN 'otkazildi' ELSE 'tasdiqlangan' END WHERE status IS NULL", (clock.today().isoformat(),))
    con.commit()
    try:
        global _con
        prev = _con; _con = con
        seed_demo(con)
        _con = prev
    except Exception as e:
        import traceback; traceback.print_exc()
        print("yoshlar.seed_demo:", repr(e))

def bind(con, ctx_fn):
    global _con, _ctx
    _con, _ctx = con, ctx_fn

DISTRICTS = ["Qibray t.", "Yunusobod t.", "Mirzo Ulug'bek t.", "Yashnobod t.", "Chilonzor t.", "Shayxontohur t.", "Olmazor t."]
STREETS = ["Bodomzor", "Navro'z", "Ziyokor", "Mustaqillik", "Bog'ishamol", "Yangiobod", "Gulobod", "Sayram", "Istiqlol", "Charxpalak"]

def seed_demo(con):
    if db.one(con, "SELECT 1 x FROM yj_buildings"): return
    R = random.Random(2026)
    today = clock.today()
    now = clock.now_iso()
    # 1) hamkor yotoqxonalar (sintetik)
    year_end = dt.date(today.year + (1 if today.month >= 7 else 0), 6, 30).isoformat()
    b1 = con.execute("""INSERT INTO yj_buildings(name,kind,address,partner,contract_no,contract_until,gender,fee_month,created_at)
                        VALUES(?,?,?,?,?,?,?,?,?)""", ("1-hamkor yotoqxona (yigitlar)", "hamkor", "Qibray tumani, Bodomzor ko'chasi, 14-uy",
                                                       "«Qibray Talaba Uy» MChJ", "HY-2026/07", year_end, "M", 300000, now)).lastrowid
    b2 = con.execute("""INSERT INTO yj_buildings(name,kind,address,partner,contract_no,contract_until,gender,fee_month,created_at)
                        VALUES(?,?,?,?,?,?,?,?,?)""", ("2-hamkor yotoqxona (qizlar)", "hamkor", "Qibray tumani, Navro'z ko'chasi, 3-uy",
                                                       "«Nur Turar Joy» MChJ", "HY-2026/08", (today + dt.timedelta(days=45)).isoformat(), "F", 280000, now)).lastrowid
    for bid, g, floors, per, beds in [(b1, "M", 3, 9, 4), (b2, "F", 3, 7, 3)]:
        for f in range(1, floors + 1):
            for n in range(1, per + 1):
                con.execute("INSERT INTO yj_rooms(building_id,number,floor,beds,gender) VALUES(?,?,?,?,?)", (bid, f"{f}{n:02d}", f, beds, g))
    con.commit()
    # 2) arizalar — kunduzgi faol talabalar (asosan viloyatlardan)
    pool = db.rows(con, STU_SQL + " WHERE s.status='faol' AND s.study_form='kunduzgi' ORDER BY s.id")
    R.shuffle(pool)
    sem_start = dt.date(today.year if today.month >= 9 else today.year - 1, 8, 20)
    apps = []
    for s in pool[:260]:
        if s["region"] in NEAR and R.random() < 0.8: continue
        cats = []
        roll = R.random()
        if roll < 0.04: cats.append("yetim")
        elif roll < 0.07: cats.append("nogironlik")
        elif roll < 0.20: cats.append("daftar")
        if R.random() < 0.15: cats.append("kop_bolali")
        if s["region"] in NEAR and not cats: cats.append("daftar")
        when = dt.datetime.combine(sem_start + dt.timedelta(days=R.randint(0, 25)), dt.time(R.randint(9, 17), R.randint(0, 59))).isoformat(timespec="seconds")
        auto = auto_cats(s)
        apps.append((s, cats, auto, when))
        if len(apps) >= 200: break
    for s, cats, auto, when in apps:
        con.execute("""INSERT INTO yj_applications(student_id,submitted_at,channel,cats,auto,score,verified,status,created_by) VALUES(?,?,?,?,?,?,?,?,NULL)""",
                    (s["id"], when, R.choice(["kabinet", "kabinet", "xodim"]), ",".join(cats), ",".join(auto), score_of(cats, auto), 1, "navbatda"))
    con.commit()
    # 3) navbat bo'yicha joylashtirish (semestr boshida), keyin ko'pchilik joylashgan
    staff = db.one(con, "SELECT id FROM users WHERE role='manaviyat'")
    sid_staff = staff["id"] if staff else None
    class _C: user = {"id": sid_staff}
    for a in db.rows(con, "SELECT id, submitted_at FROM yj_applications WHERE status='navbatda' ORDER BY score DESC, submitted_at"):
        try: allocate(_C, a["id"], when=(sem_start + dt.timedelta(days=12)).isoformat() + "T10:00:00")
        except HTTPException: pass
    res = db.rows(con, "SELECT id FROM yj_residents WHERE status='band' ORDER BY id")
    for i, r in enumerate(res):
        if i % 37 == 5: continue              # bir nechtasi hali joylashmagan (bron)
        con.execute("UPDATE yj_residents SET status='yashaydi', check_in=? WHERE id=?", ((sem_start + dt.timedelta(days=R.randint(12, 16))).isoformat(), r["id"]))
    # 3 ta bo'sh o'rin qoldirish uchun — ikki yashovchi chiqib ketgan
    for r in db.rows(con, "SELECT id FROM yj_residents WHERE status='yashaydi' ORDER BY id DESC LIMIT 2"):
        con.execute("UPDATE yj_residents SET status='chiqdi', check_out=?, out_reason=? WHERE id=?", ((today - dt.timedelta(days=20)).isoformat(), "O'z xohishi bilan", r["id"]))
    # bir nechta yangi (tekshirilmagan) ariza
    for s in pool[300:340]:
        if s["region"] in NEAR: continue
        if db.one(con, "SELECT 1 x FROM yj_applications WHERE student_id=?", (s["id"],)): continue
        cats = ["daftar"] if R.random() < 0.5 else ["kop_bolali"]
        auto = auto_cats(s)
        con.execute("""INSERT INTO yj_applications(student_id,submitted_at,channel,cats,auto,score,verified,status) VALUES(?,?,?,?,?,?,0,'yangi')""",
                    (s["id"], (today - dt.timedelta(days=R.randint(0, 6))).isoformat() + "T11:00:00", "kabinet", ",".join(cats), ",".join(auto), score_of(cats, auto)))
        if db.one(con, "SELECT COUNT(*) n FROM yj_applications WHERE status='yangi'")["n"] >= 6: break
    rej = db.one(con, "SELECT id FROM yj_applications WHERE status='navbatda' ORDER BY score LIMIT 1")
    if rej: con.execute("UPDATE yj_applications SET status='rad', reason=?, decided_at=? WHERE id=?",
                        ("Toshkent viloyatida doimiy ro'yxatda, qatnash imkoniyati bor", now, rej["id"]))
    con.commit()
    # 4) oylik hisoblar va to'lovlar
    m = dt.date(sem_start.year, 9, 1)
    periods = []
    while m <= today:
        periods.append(m.isoformat()[:7]); m = (m.replace(day=28) + dt.timedelta(days=4)).replace(day=1)
    bux = db.one(con, "SELECT id FROM users WHERE role='buxgalteriya'")
    for p in periods: generate_charges(None, p)
    for ch in db.rows(con, "SELECT id, amount, period, due FROM yj_charges"):
        last = ch["period"] == periods[-1]
        x = R.random()
        if (not last and x < 0.9) or (last and x < 0.45):
            paid_on = dt.date.fromisoformat(ch["due"]) - dt.timedelta(days=R.randint(0, 8))
            con.execute("UPDATE yj_charges SET paid=amount, paid_at=?, receipt=?, by_user=? WHERE id=?",
                        (paid_on.isoformat() + "T12:00:00", f"KV-{R.randint(100000, 999999)}", bux["id"] if bux else None, ch["id"]))
        elif not last and x < 0.94:
            con.execute("UPDATE yj_charges SET paid=?, paid_at=?, receipt=?, by_user=? WHERE id=?",
                        (ch["amount"] // 2, ch["due"] + "T12:00:00", f"KV-{R.randint(100000, 999999)}", bux["id"] if bux else None, ch["id"]))
    con.commit()
    # 5) tartib qaydlari
    kom = db.one(con, "SELECT id FROM users WHERE role='komendant'")
    live = db.rows(con, "SELECT id, student_id FROM yj_residents WHERE status='yashaydi' ORDER BY id")
    picks = R.sample(live, min(9, len(live)))
    texts = {"Kechki tartibni buzish": "Soat 23:00 dan keyin qaytdi, navbatchi daftarida qayd etildi", "Chekish": "Xonada chekkani aniqlandi",
             "Ruxsatsiz mehmon": "Ro'yxatdan o'tmagan mehmonni olib kirdi", "Sanitariya talablari": "Xona tozaligi tekshiruvda qoniqarsiz",
             "Janjal": "Qo'shni xona talabalari bilan kelishmovchilik, tinchlantirildi"}
    for i, r in enumerate(picks):
        for j in range(3 if i == 0 else 1):
            k = R.choice(list(texts))
            con.execute("INSERT INTO yj_violations(resident_id,student_id,date,kind,text,measure,by_user,at) VALUES(?,?,?,?,?,?,?,?)",
                        (r["id"], r["student_id"], (today - dt.timedelta(days=R.randint(2, 50))).isoformat(), k, texts[k],
                         "hayfsan" if (i == 0 and j == 2) else "ogohlantirish", kom["id"] if kom else None, now))
    con.commit()
    # 6) ijarada yashovchilar — tyutorlar tashrifi bilan
    tut = {r["group_id"]: r["user_id"] for r in db.rows(con, "SELECT group_id, user_id FROM tutor_groups")}
    taken = {r["student_id"] for r in db.rows(con, "SELECT student_id FROM yj_residents")} | {r["student_id"] for r in db.rows(con, "SELECT student_id FROM yj_applications WHERE status IN ('yangi','navbatda')")}
    rpool = db.rows(con, "SELECT s.id, s.group_id, s.region FROM students s WHERE s.status='faol' AND s.study_form='kunduzgi' AND s.region NOT IN ('Toshkent sh.') ORDER BY s.id")
    R.shuffle(rpool)
    n = 0
    for s in rpool:
        if s["id"] in taken: continue
        visited = R.random() < 0.7
        con.execute("""INSERT OR IGNORE INTO yj_rentals(student_id,address,district,rent,since,has_contract,last_visit,visit_note,condition,visited_by,created_by,created_at)
                       VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (s["id"], f"{R.choice(STREETS)} ko'chasi, {R.randint(1, 80)}-uy" + (f", {R.randint(1, 60)}-xonadon" if R.random() < 0.5 else ""),
                     R.choice(DISTRICTS), R.choice([600, 800, 1000, 1200, 1500]) * 1000, (sem_start + dt.timedelta(days=R.randint(0, 20))).isoformat(),
                     int(R.random() < 0.55),
                     (today - dt.timedelta(days=R.randint(5, 120))).isoformat() if visited else None,
                     R.choice(["Sharoit yaxshi, uy egasi bilan kelishuv bor", "3 nafar talaba birga yashaydi, sharoit o'rtacha", "Isitish yetarli emas, maslahat berildi"]) if visited else None,
                     R.choice(["yaxshi", "yaxshi", "qoniqarli", "qoniqarsiz"]) if visited else None,
                     tut.get(s["group_id"]) if visited else None, sid_staff, now))
        n += 1
        if n >= 140: break
    con.commit()
    # 7) tadbirlar: reja / tasdiqlashda / tasdiqlangan (kelgusi) va o'tgan, hisobotsiz bitta
    pro = db.one(con, "SELECT id FROM users WHERE role='prorektor_yoshlar'")
    org = _short(db.one(con, "SELECT full_name FROM users WHERE role='manaviyat'")["full_name"])
    for title, days, kind, st, venue, tm, cap in [
        ("«Yosh kitobxon» tanlovining institut bosqichi", 6, "ma'naviy", "tasdiqlangan", "Majlislar zali", "14:00", 150),
        ("Talabalar o'rtasida stol tennisi musobaqasi", 11, "sport", "tasdiqlashda", "Sport zali", "15:00", 64),
        ("Karyera kuni: hamkor banklar bilan uchrashuv", 18, "karyera", "reja", "Majlislar zali", "10:00", 200),
        ("Volontyorlar: Qibray tumanidagi mehribonlik uyiga tashrif", -3, "volontyorlik", "tasdiqlangan", "Qibray tumani", "10:00", 30),
    ]:
        d = (today + dt.timedelta(days=days)).isoformat()
        con.execute("""INSERT INTO events(title,date,kind,participants,status,venue,start_time,audience,capacity,budget,plan_note,organizer,created_by,created_at,
                       submitted_at,approved_by,approved_at) VALUES(?,?,?,0,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (title, d, kind, st, venue, tm, "Barcha kunduzgi talabalar", cap, R.choice([0, 1500000, 3000000]),
                     "Maqsad, dastur va mas'ullar rejada ko'rsatilgan", org, sid_staff, now,
                     now if st in ("tasdiqlashda", "tasdiqlangan") else None, pro["id"] if (pro and st == "tasdiqlangan") else None,
                     now if st == "tasdiqlangan" else None))
    con.commit()
    ev = db.one(con, "SELECT id FROM events WHERE status='tasdiqlangan' AND date>=? ORDER BY date LIMIT 1", (today.isoformat(),))
    if ev:
        for s in pool[400:440]:
            con.execute("INSERT OR IGNORE INTO event_reg(event_id,student_id) VALUES(?,?)", (ev["id"], s["id"]))
    con.commit()
