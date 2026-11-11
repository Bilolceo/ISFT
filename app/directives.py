"""Ierarxik topshiriqlar ("topshiriq / vazifa berish") — majlisdan tashqari, rahbardan quyi bo'lim va xodimlarga.

Rektor topshirig'i: "Prorektorlar o'z vakolatidagi bo'lim rahbarlariga topshiriq beradi; bo'lim rahbarlari o'z xodimlariga yoki quyi
bo'limlarga beradi. Masalan, prorektor Registrator ofisiga topshiriq beradi; M. Baratov uni Registrator ofisi xodimi A. Norovga
yo'naltiradi va ijrosini ta'minlaydi."

Saqlash: majlis topshiriqlari bilan bitta `tasks` jadvali (app/decisions.py). Farqi:
  tasks.origin = 'topshiriq' (majlissiz, meeting_id IS NULL), issuer_user / issuer_unit — kim bergan, on_behalf='rektor' — kotib rektor
  nomidan bergan, parent_id — taqsimlash zanjiri (ota topshiriq), priority, body (matn), expect (talab qilinadigan natija),
  attach / result_attach — Portal fayllari (portal_files.id, JSON), review — natijani qabul qilish holati:
      'kutilmoqda' (ijrochi «bajarildi» dedi, bergan kishi ko'rib chiqadi) · 'qabul' · 'qaytarildi' (qayta ishlashga, izoh bilan).
  Holatlar o'zgarmaydi: yangi → jarayonda → bajarildi (majlis topshiriqlari bilan bir xil — rektor paneli, kalendar, bildirishnomalar,
  «Mening vazifalarim» ularni avtomatik ko'radi: services.tasks_list → task_rows()).

VAKOLAT (kim kimga topshiriq bera oladi) — YAGONA joy: targets(). authorize() shu ro'yxat bo'yicha tekshiradi va rad etilsa audit
jurnaliga yozib 403 qaytaradi. Topshiriq faqat yuqoridan quyiga: yuqoriga (rahbariyatga, o'z kuratoriga) va yonma-yon (boshqa
bo'limga) berilmaydi.
"""
import datetime as dt, json
from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel, Field
from . import clock
from . import db, rbac, decisions as DEC
from .rbac import Ctx, AccessDenied, TASKS

router = APIRouter()
_con = None
_ctx = None

ORIGIN = "topshiriq"
PRIOS = {"oddiy": "Oddiy", "muhim": "Muhim", "shoshilinch": "Shoshilinch"}
READ_ALL = ("rektor", "kengash", "kotib")       # barcha topshiriqlarni ko'radi (o'qish) — decisions.LEADERS + kotib kabi
TOP_UNITS = ("rektorat", "kengash")              # rektor/kotib uchun ham maqsad emas (o'zi va kuzatuv kengashi)

# Quyi bo'limlar: bo'lim rahbari o'z xodimlaridan tashqari qaysi bo'limlarga topshiriq bera oladi (org_units kalitlari).
# "@<guruh>" — shu guruhdagi hamma bo'limlar (masalan, "@kafedra" — barcha kafedralar). Institut tuzilmasi o'zgarsa — faqat shu yer.
#   * Akademik faoliyatni boshqarish bo'limi → barcha kafedralar (o'quv-akademik masalalar: jadval, yuklama, nazorat);
#   * Registrator ofisi → faqat o'z xodimlari (Registrator xodimi, Call-markaz — users.unit='talabalar', ya'ni bo'lim a'zolari),
#     quyi bo'lim yo'q. Institutda dekanat yo'q (Yevropa modeli): fakultet darajasidagi vazifani Registrator ofisi bajaradi;
#   * kafedralarni yana o'quv ishlari prorektori boshqaradi — u kurator sifatida (org_units.curator), bu xaritada emas.
SUBORDINATE = {
    "akademik": ["@kafedra"],
    "masofaviy": ["@kafedra"],     # Masofaviy ta'lim bo'limi → kafedralar (LMS'ga materiallar yuklash)
    "talabalar": [],
}

# Demo: Registrator ofisi oddiy xodimi (bo'lim a'zosi, rahbar emas). Server ishga tushganda oxiriga qo'shiladi (id'lar o'zgarmaydi).
STAFF_ROLE = "registrator_xodim"
DEMO_STAFF = ("Registrator ofisi xodimi: Norov Aziz Bahodir o'g'li", STAFF_ROLE, "talabalar", "REGXODIM")

def _now(): return clock.now().replace(microsecond=0)
def _iso(t): return t.isoformat(timespec="seconds")
_short = DEC._short

# ---------------------------------------------------------------------------------------------
# Sxema, demo akkaunt va demo topshiriqlar (idempotent)
# ---------------------------------------------------------------------------------------------
COLS = [("origin", "TEXT"), ("parent_id", "INT"), ("issuer_user", "INT"), ("issuer_unit", "TEXT"), ("on_behalf", "TEXT"),
        ("priority", "TEXT"), ("body", "TEXT"), ("expect", "TEXT"), ("attach", "TEXT"), ("result_attach", "TEXT"),
        ("review", "TEXT"), ("review_note", "TEXT"), ("review_at", "TEXT"), ("review_by", "INT"), ("created_at", "TEXT"),
        ("src", "TEXT")]     # manba: 'syl:<so'rov id>' (O'quv dasturlari — kafedra so'rovi), 'portal' / 'portal:<xat id>' (Portal — ma'lumot so'rovi)
SRC_LABEL = {"syl": "O'quv dasturlari · kafedra so'rovi", "portal": "Portal · ma'lumot so'rovi", "dl": "Masofaviy ta'lim · kontent monitoringi"}

def init(con):
    try:
        DEC._add_cols(con, "tasks", COLS)
        con.executescript("""
        CREATE INDEX IF NOT EXISTS ix_tasks_parent ON tasks(parent_id);
        CREATE INDEX IF NOT EXISTS ix_tasks_origin ON tasks(origin);
        CREATE TABLE IF NOT EXISTS dir_meta(k TEXT PRIMARY KEY, v TEXT);
        """)
        con.commit()
    except Exception as e:            # bo'sh baza (seed boshlanmagan)
        print("directives.init:", e); return
    if not db.one(con, "SELECT 1 x FROM users"): return
    name, role, unit, code = DEMO_STAFF
    if not db.one(con, "SELECT 1 x FROM users WHERE role=?", (role,)):
        con.execute("INSERT INTO users(full_name,role,unit,link_code,pin) VALUES(?,?,?,?,?)",
                    (name, role, unit, code, rbac.hash_password(rbac.DEMO_PASSWORD)))
        con.commit()
    try:
        seed_demo(con)
    except Exception as e:
        print("directives.seed_demo:", repr(e))
    try:     # eski (bo'limsiz) majlis topshiriqlari → yagona ijro oqimi (decisions.migrate_legacy, idempotent)
        n = DEC.migrate_legacy(con)
        if n: print(f"decisions: {n} ta eski majlis topshirig'i yagona oqimga o'tkazildi")
    except Exception as e:
        print("decisions.migrate_legacy:", repr(e))

def bind(con, ctx_fn):
    global _con, _ctx
    _con, _ctx = con, ctx_fn

def _uid(con, sql, args=()):
    r = db.one(con, sql, args)
    return list(r.values())[0] if r else None

def seed_demo(con):
    """Demo zanjirlar (bir marta; dir_meta.seed_v1). Sanalar bugungi kunga nisbatan."""
    if db.one(con, "SELECT 1 x FROM dir_meta WHERE k='seed_v1'"): return
    head = lambda k: _uid(con, "SELECT head_user FROM org_units WHERE key=?", (k,))
    U = {"rektor": _uid(con, "SELECT id FROM users WHERE role='rektor' ORDER BY id"),
         "pro": _uid(con, "SELECT id FROM users WHERE role='prorektor_oquv' ORDER BY id"),
         "reg": head("talabalar"), "norov": _uid(con, "SELECT id FROM users WHERE role=? ORDER BY id", (STAFF_ROLE,)),
         "akad": head("akademik"), "kaf3": head("kaf3"), "kaf6": head("kaf6"), "kaf7": head("kaf7")}
    if not all(U.values()): return
    now, today = _now(), clock.today()
    at = lambda days, h, m=0: _iso(dt.datetime.combine(today + dt.timedelta(days=days), dt.time(h, m)))
    names = {r["id"]: r["full_name"] for r in db.rows(con, "SELECT id, full_name FROM users")}

    def mk(issuer, issuer_unit, unit, title, body, due, prio="oddiy", expect="", parent=None, assignee=None, created=None, **upd):
        tid = _insert(con, issuer, issuer_unit, None, title, body, unit, assignee, due, prio, expect, [], parent, created)
        if upd:
            con.execute(f"UPDATE tasks SET {', '.join(k + '=?' for k in upd)} WHERE id=?", (*upd.values(), tid))
        return tid

    def log(tid, uid, ts, action, detail=""):
        con.execute("INSERT INTO task_log(task_id,ts,user_id,user_name,action,detail) VALUES(?,?,?,?,?,?)",
                    (tid, ts, uid, names[uid], action, detail))

    # 1) O'quv ishlari prorektori → Registrator ofisi; Baratov → Norov A. (jarayonda)
    c1 = at(-1, 9, 30)
    d1 = mk(U["pro"], "prorektor_oquv", "registrator", "Yakuniy nazoratga ruxsat etilmagan talabalar ro'yxatini tayyorlash",
            "Kuzgi semestr yakuniy nazorati oldidan kontrakt qarzdorligi va davomat bo'yicha ruxsat etilmagan talabalar ro'yxatini "
            "fakultetlar kesimida tayyorlang.", at(3, 18), "muhim", "Fakultetlar kesimida ro'yxat (Excel) va qisqa izoh", created=c1,
            status="jarayonda")
    log(d1, U["pro"], c1, "topshiriq berildi", "Registrator ofisiga")
    c1a = at(-1, 11, 5)
    d1a = mk(U["reg"], "registrator", "registrator", "Ro'yxatni HEMIS ma'lumotlari bilan solishtirib tayyorlash",
             "Kontrakt qarzdorligi (Buxgalteriya ma'lumoti) va davomat bo'yicha ro'yxatni HEMIS bilan solishtiring.", at(2, 17), "muhim",
             "Fakultetlar kesimida ro'yxat (Excel)", parent=d1, assignee=U["norov"], created=c1a, status="jarayonda",
             result="Iqtisodiyot va axborot texnologiyalari fakulteti bo'yicha solishtirildi; qolgan ikki fakultet ustida ishlanmoqda.",
             result_at=at(0, 10, 15), result_by=U["norov"])
    log(d1, U["reg"], c1a, "taqsimlandi", f"{_short(names[U['norov']])} — muddat {at(2, 17)[:16].replace('T', ' ')}")
    log(d1a, U["reg"], c1a, "topshiriq berildi", _short(names[U["norov"]]))
    log(d1a, U["norov"], at(-1, 14), "ish boshlandi")
    log(d1a, U["norov"], at(0, 10, 15), "oraliq natija", "Iqtisodiyot va axborot texnologiyalari fakulteti bo'yicha solishtirildi")

    # 2) Rektor → Akademik bo'lim → 2 kafedra (biri bajardi — qabul kutilmoqda, biri muddati o'tgan)
    c2 = at(-4, 10)
    d2 = mk(U["rektor"], "rektorat", "akademik", "Bahorgi semestr dars jadvali loyihasini kafedralar bilan kelishish",
            "Bahorgi semestr dars jadvali loyihasini har bir kafedra o'qituvchilari yuklamasi bilan kelishib, yakuniy loyihani taqdim eting.",
            at(5, 18), "oddiy", "Kelishilgan jadval loyihasi va kafedralar takliflari jamlanmasi", created=c2, status="jarayonda")
    log(d2, U["rektor"], c2, "topshiriq berildi", "Akademik faoliyatni boshqarish bo'limiga")
    c2k = at(-3, 9)
    sub = "Kafedra o'qituvchilari yuklamasi bo'yicha jadval takliflarini yuborish"
    d2a = mk(U["akad"], "akademik", "kaf3", sub, "Bahorgi semestr uchun o'qituvchilar yuklamasi va qulay vaqtlar bo'yicha takliflar.",
             at(1, 17), expect="Takliflar jadvali", parent=d2, created=c2k, status="bajarildi", assignee=U["kaf3"],
             result="Menejment kafedrasi takliflari yuborildi: 14 o'qituvchi, 3 ta vaqt to'qnashuvi bartaraf etildi.",
             result_at=at(-1, 16, 40), result_by=U["kaf3"], review="kutilmoqda")
    d2b = mk(U["akad"], "akademik", "kaf6", sub, "Bahorgi semestr uchun o'qituvchilar yuklamasi va qulay vaqtlar bo'yicha takliflar.",
             at(-1, 17), expect="Takliflar jadvali", parent=d2, created=c2k)
    for k, tid in (("kaf3", d2a), ("kaf6", d2b)):
        log(d2, U["akad"], c2k, "taqsimlandi", DEC.unit_name(k) or k)
        log(tid, U["akad"], c2k, "topshiriq berildi", DEC.unit_name(k) or k)
    log(d2a, U["kaf3"], at(-2, 11), "ish boshlandi")
    log(d2a, U["kaf3"], at(-1, 16, 40), "bajarildi — natija yuborildi", "Menejment kafedrasi takliflari yuborildi")

    # 3) O'quv ishlari prorektori → kafedra (kurator); natija qayta ishlashga qaytarilgan
    c3 = at(-5, 15)
    d3 = mk(U["pro"], "prorektor_oquv", "kaf7", "Talabalar davomati bo'yicha oylik tahliliy ma'lumot tayyorlash",
            "Oktabr oyi bo'yicha kafedra fanlari kesimida davomat tahlili.", at(2, 17), "oddiy", "Guruhlar kesimida davomat foizi va izoh",
            created=c3, status="jarayonda", assignee=U["kaf7"],
            result="Kafedra bo'yicha o'rtacha davomat 87%.", result_at=at(-2, 12), result_by=U["kaf7"],
            review="qaytarildi", review_note="Guruhlar kesimidagi foizlar yo'q — jadvalni guruhlar bo'yicha to'ldiring.",
            review_at=at(-1, 9, 20), review_by=U["pro"])
    log(d3, U["pro"], c3, "topshiriq berildi", DEC.unit_name("kaf7") or "kaf7")
    log(d3, U["kaf7"], at(-2, 12), "bajarildi — natija yuborildi", "Kafedra bo'yicha o'rtacha davomat 87%.")
    log(d3, U["pro"], at(-1, 9, 20), "qayta ishlashga qaytarildi", "Guruhlar kesimidagi foizlar yo'q — jadvalni guruhlar bo'yicha to'ldiring.")
    con.execute("INSERT OR REPLACE INTO dir_meta(k,v) VALUES('seed_v1',?)", (_iso(now),))
    con.commit()

def _insert(con, issuer, issuer_unit, on_behalf, title, body, unit, assignee, due, prio, expect, attach, parent, created=None):
    a = db.one(con, "SELECT full_name, role FROM users WHERE id=?", (assignee,)) if assignee else None
    ts = created or _iso(_now())
    cur = con.execute("""INSERT INTO tasks(meeting_id,assignee,assignee_role,text,due,due_at,status,unit,assignee_user,pos,updated_at,
                           origin,parent_id,issuer_user,issuer_unit,on_behalf,priority,body,expect,attach,created_at)
                         VALUES(NULL,?,?,?,?,?,'yangi',?,?,0,?,?,?,?,?,?,?,?,?,?,?)""",
                      (_short(a["full_name"]) if a else "", a["role"] if a else DEC._head_role(unit), title[:300], (due or "")[:10] or None, due,
                       unit, assignee, ts, ORIGIN, parent, issuer, issuer_unit, on_behalf, prio, body, expect,
                       json.dumps(attach) if attach else None, ts))
    return cur.lastrowid

def create_linked(con, issuer: int, issuer_unit: str | None, unit: str, title: str, body: str, due: str, prio: str = "oddiy", expect: str = "",
                  src: str | None = None, created: str | None = None, attach: list | None = None, on_behalf: str | None = None) -> int:
    """Boshqa modullar (O'quv dasturlari, Portal) uchun topshiriq yaratish — vakolat chaqiruvchida tekshirilgan bo'lishi kerak.
    Modul global holatiga bog'liq emas (seed paytida ham ishlaydi). due — 'YYYY-MM-DD' (18:00 deb olinadi) yoki ISO vaqt."""
    if due and "T" not in due: due = f"{due[:10]}T18:00"
    h = db.one(con, "SELECT u.role FROM org_units o JOIN users u ON u.id=o.head_user WHERE o.key=?", (DEC.org_key(unit),))
    ts = created or _iso(_now())
    tid = con.execute("""INSERT INTO tasks(meeting_id,assignee,assignee_role,text,due,due_at,status,unit,assignee_user,pos,updated_at,
                           origin,parent_id,issuer_user,issuer_unit,on_behalf,priority,body,expect,attach,created_at,src)
                         VALUES(NULL,'',?,?,?,?,'yangi',?,NULL,0,?,?,NULL,?,?,?,?,?,?,?,?,?)""",
                      (h["role"] if h else None, title[:300], (due or "")[:10] or None, due, unit, ts, ORIGIN, issuer, issuer_unit, on_behalf,
                       prio if prio in PRIOS else "oddiy", body, expect, json.dumps(attach) if attach else None, ts, src)).lastrowid
    u = db.one(con, "SELECT full_name FROM users WHERE id=?", (issuer,))
    con.execute("INSERT INTO task_log(task_id,ts,user_id,user_name,action,detail) VALUES(?,?,?,?,?,?)",
                (tid, ts, issuer, u["full_name"] if u else "", "topshiriq berildi", SRC_LABEL.get((src or "").split(":")[0], "")))
    return tid

def src_info(t) -> dict | None:
    s = t.get("src") or ""
    if not s: return None
    kind, _, ref = s.partition(":")
    link = {"view": "syllabus", "tab": "tasks", "task": int(ref)} if kind == "syl" and ref.isdigit() else \
           {"view": "portal", "thread": int(ref)} if kind == "portal" and ref.isdigit() else None
    return {"kind": kind, "label": SRC_LABEL.get(kind, kind), "link": link}

# ---------------------------------------------------------------------------------------------
# VAKOLAT — yagona funksiya
# ---------------------------------------------------------------------------------------------
def subordinate_units(org_unit: str) -> list[str]:
    """SUBORDINATE xaritasidan: bo'lim rahbari topshiriq bera oladigan quyi bo'limlar (org_units kalitlari)."""
    from . import portal as PT
    out = []
    for s in SUBORDINATE.get(org_unit, []):
        if s.startswith("@"): out += [u["key"] for u in PT.units(_con) if u["group"] == s[1:]]
        else: out.append(s)
    return [k for k in dict.fromkeys(out) if k != org_unit]

def targets(c: Ctx) -> dict:
    """KIM KIMGA TOPSHIRIQ BERA OLADI. Natija: {"units": {topshiriq kaliti: asos}, "people": {user_id: asos}, "on_behalf": None|"rektor"}.
      * rektor — istalgan bo'limga (Rektorat va Kuzatuv kengashidan tashqari); kotib — xuddi shunday, lekin «rektor nomidan»;
      * prorektor_* — o'z vakolatidagi bo'limlarga (org_units.curator == uning roli);
      * bo'lim rahbari (org_units.head_user == men) — o'z bo'limi xodimlariga (shaxsan) va SUBORDINATE dagi quyi bo'limlarga;
      * fakultet tyutorlari (fakultet guruhi) — ierarxik topshiriq maqsadi emas: dekan lavozimi yo'q, fakultet vazifalari — Registrator ofisida;
      * boshqalar — hech kimga. Yuqoriga va yonma-yon topshiriq berilmaydi (authorize → 403 + audit).
    Rahbari (head_user) yo'q bo'lim maqsad bo'la olmaydi — topshiriq hech kimning navbatiga tushmay qoladi."""
    from . import portal as PT
    uid, role = c.user["id"], c.role.key
    reg = DEC.registry()
    heads = {r["key"]: r["head_user"] for r in db.rows(_con, "SELECT key, head_user FROM org_units")}
    units, people, behalf = {}, {}, None
    if role in ("rektor", "kotib"):
        behalf = "rektor" if role == "kotib" else None
        for k, x in reg.items():
            if x["org"] not in TOP_UNITS: units[k] = "rektor nomidan" if behalf else "rektor"
    if role.startswith("prorektor_"):
        for k in DEC.curated_units(c): units.setdefault(k, "vakolatidagi bo'lim")
    me = PT.my_unit(c)
    if me and heads.get(me) == uid:
        for m in PT.members(_con, me):
            if m["id"] != uid: people[m["id"]] = "o'z xodimi"
        for k in subordinate_units(me): units.setdefault(DEC.task_key(k), "quyi bo'lim")
    # Fakultet guruhi maqsad emas: institutda dekan lavozimi yo'q (Yevropa modeli) — fakultet darajasidagi vazifani Registrator ofisi bajaradi
    units = {k: v for k, v in units.items() if reg[k]["group"] != "fakultet"
             and heads.get(DEC.org_key(k)) and heads.get(DEC.org_key(k)) != uid and DEC.org_key(k) != me}
    return {"units": units, "people": people, "on_behalf": behalf}

def can_issue(c: Ctx) -> bool:
    t = targets(c)
    return bool(t["units"] or t["people"])

def _upward(c: Ctx, org: str) -> bool:
    """Rad etish sababini aniqlash uchun: maqsad men uchun yuqori turuvchimi (rahbariyat, kuratorim yoki meni boshqaradigan bo'lim)."""
    from . import portal as PT
    me = PT.my_unit(c)
    um = PT.unit_map(_con)
    if (um.get(org) or {}).get("group") == "rahbariyat": return True
    if (um.get(me) or {}).get("curator") == org: return True
    return me in subordinate_units(org)

def authorize(c: Ctx, action: str, unit: str | None = None, user_id: int | None = None):
    """targets() bo'yicha tekshiradi. Ruxsat — (unit, user_id|None); rad — audit (allowed=0) va 403 (o'zbekcha izoh)."""
    from . import portal as PT
    T = targets(c)
    if user_id:
        u = db.one(_con, "SELECT * FROM users WHERE id=?", (user_id,))
        if not u: raise HTTPException(400, "Xodim topilmadi")
        if user_id in T["people"]: return DEC.task_key(PT.unit_key(u)), user_id
        org, label = PT.unit_key(u), _short(u["full_name"]) or u["full_name"]
        why = ("yuqori turuvchi rahbarga topshiriq berilmaydi" if _upward(c, org) or rbac.ROLES[u["role"]].level < c.role.level
               else "bu xodim sizning bo'limingizda emas — boshqa bo'lim xodimiga uning rahbari orqali (bo'limga) beriladi")
    else:
        k = DEC.task_key(unit) if unit else None
        if not k or k not in DEC.registry(): raise HTTPException(400, "Noma'lum bo'lim")
        if k in T["units"]: return k, None
        org, label = DEC.org_key(k), DEC.unit_name(k) or k
        why = ("yuqori turuvchi rahbariyatga topshiriq berilmaydi" if _upward(c, org)
               else "bu bo'lim sizning vakolatingizda emas (yonma-yon bo'limga topshiriq berilmaydi)")
    rbac.audit(_con, c, action, TASKS, False, f"→ {label}: rad etildi")
    raise AccessDenied(f"⛔ «{label}»: {why}. Topshiriq faqat yuqoridan quyiga — vakolatingizdagi bo'limlar va o'z xodimlaringizga beriladi. "
                       "So'rov audit jurnaliga yozildi.")

def targets_view(c: Ctx) -> dict:
    """UI tanlash ro'yxati: faqat ruxsat etilgan maqsadlar, guruhlangan."""
    from . import portal as PT
    T = targets(c)
    um = PT.unit_map(_con); gname = dict(PT.GROUPS)
    reg = DEC.registry()
    groups = {}
    for k, basis in T["units"].items():
        x = reg[k]; u = um.get(x["org"]) or {}
        groups.setdefault(x["group"], []).append({"key": k, "name": x["name"], "head": u.get("head") or "", "basis": basis})
    order = [g for g, _ in PT.GROUPS]
    out = [{"group": g, "name": gname.get(g, g), "units": groups[g]} for g in order if g in groups]
    ppl = []
    for uid, basis in T["people"].items():
        u = db.one(_con, "SELECT id, full_name, role FROM users WHERE id=? AND COALESCE(active,1)=1", (uid,))
        if u: ppl.append({"id": u["id"], "name": _short(u["full_name"]) or u["full_name"], "position": rbac.user_title(u), "basis": basis})
    return {"can": bool(out or ppl), "on_behalf": T["on_behalf"], "groups": out, "people": ppl,
            "my_unit": DEC.unit_name(DEC.unit_of(c)), "prios": PRIOS}

# ---------------------------------------------------------------------------------------------
# Ko'rinish va harakat huquqlari (xotirada — bitta so'rovda barcha topshiriqlar bo'yicha tez)
# ---------------------------------------------------------------------------------------------
class W:
    """Foydalanuvchi + bo'limlar rahbarlari xaritasi + topshiriqlar (id → yozuv)."""
    def __init__(self, c: Ctx, rows=None):
        self.c, self.uid, self.role = c, c.user["id"], c.role.key
        self.heads = {r["key"]: r["head_user"] for r in db.rows(_con, "SELECT key, head_user FROM org_units")}
        self.cur = DEC.curated_units(c)
        if rows is None: rows = db.rows(_con, "SELECT * FROM tasks WHERE origin=?", (ORIGIN,))
        self.by = {t["id"]: t for t in rows}
        self.kids = {}
        for t in rows:
            if t.get("parent_id"): self.kids.setdefault(t["parent_id"], []).append(t)
        for v in self.kids.values(): v.sort(key=lambda t: t["id"])

    def head(self, unit) -> bool: return bool(unit) and self.heads.get(DEC.org_key(unit)) == self.uid
    def ancestors(self, t):
        out, seen, p = [], {t["id"]}, t.get("parent_id")
        while p and p in self.by and p not in seen:
            seen.add(p); a = self.by[p]; out.append(a); p = a.get("parent_id")
        return out
    def over(self, t) -> bool:
        """Topshiriq ustidan nazorat tomoni: bergan, bergan bo'lim rahbari, ijrochi bo'lim rahbari, kurator prorektor."""
        return (t.get("issuer_user") == self.uid or self.head(t.get("issuer_unit")) or self.head(t.get("unit"))
                or (t.get("unit") in self.cur) or (t.get("on_behalf") == "rektor" and self.role == "rektor"))
    def view(self, t) -> bool:
        if self.role in READ_ALL or t.get("assignee_user") == self.uid or self.over(t): return True
        return any(self.over(a) for a in self.ancestors(t))     # zanjir: yuqoridagi topshiriqni bergan/nazorat qilgan — quyisini ham ko'radi
    def act(self, t) -> bool:
        return t["status"] != "bajarildi" and (self.head(t.get("unit")) or t.get("assignee_user") == self.uid)
    def delegate(self, t) -> bool:
        return t["status"] != "bajarildi" and self.head(t.get("unit"))
    def reviewer(self, t) -> bool:
        """Natijani qabul qiladi / qaytaradi: bergan kishi, bergan bo'lim rahbari (kotib bergan bo'lsa — rektor ham) yoki zanjirda yuqoridagi bergan."""
        def iss(x): return x.get("issuer_user") == self.uid or self.head(x.get("issuer_unit")) or (x.get("on_behalf") == "rektor" and self.role == "rektor")
        return iss(t) or any(iss(a) for a in self.ancestors(t))
    def review(self, t) -> bool:
        return t["status"] == "bajarildi" and t.get("review") == "kutilmoqda" and self.reviewer(t) and t.get("result_by") != self.uid
    def cancel(self, t) -> bool:
        return t.get("issuer_user") == self.uid or (self.role == "rektor" and (t.get("on_behalf") == "rektor" or self.head(t.get("issuer_unit"))))
    def mine(self, t) -> bool:
        """Ijro men zimmamda: menga biriktirilgan yoki bo'limimga kelgan va hali xodimga biriktirilmagan."""
        if t["status"] == "bajarildi": return False
        return t.get("assignee_user") == self.uid or (self.head(t.get("unit")) and t.get("assignee_user") in (None, self.uid))

def _due_dt(due):
    if not due: return None
    try: return dt.datetime.fromisoformat(due) if "T" in due else dt.datetime.combine(dt.date.fromisoformat(due), dt.time(23, 59))
    except ValueError: return None

def _overdue(t) -> bool:
    d = _due_dt(t.get("due_at") or t.get("due"))
    return bool(d and t["status"] != "bajarildi" and d < clock.now())

def _uinfo(uid):
    if not uid: return None
    u = db.one(_con, "SELECT id, full_name, role, unit FROM users WHERE id=?", (uid,))
    if not u: return None
    return {"id": u["id"], "name": _short(u["full_name"]) or u["full_name"], "position": rbac.user_title(u)}

def _issuer_label(t) -> str:
    i = _uinfo(t.get("issuer_user"))
    if not i: return "—"
    if t.get("on_behalf") == "rektor": return f"Rektor nomidan · {i['position'].lower()} {i['name']}"
    return f"{i['position']} {i['name']}" if i["name"] != i["position"] else i["position"]

def _files(raw):
    ids = json.loads(raw) if raw else []
    if not ids: return []
    rows = db.rows(_con, f"SELECT id, name, ext, size FROM portal_files WHERE id IN ({','.join('?' * len(ids))})", ids)
    return [{"id": r["id"], "name": r["name"], "ext": r["ext"], "size": r["size"]} for r in rows]

def node(w: W, t, deep=False) -> dict:
    kids = w.kids.get(t["id"], [])
    done = sum(k["status"] == "bajarildi" for k in kids)
    due = t.get("due_at") or t.get("due")
    v = {k: t.get(k) for k in ("id", "parent_id", "status", "review", "review_note", "review_at", "result", "result_at", "priority",
                                "body", "expect", "created_at", "updated_at", "unit", "assignee_user", "on_behalf")}
    v.update({"title": t["text"], "due": due, "overdue": _overdue(t), "unit_name": DEC.unit_name(t.get("unit")),
              "assignee_name": _short(DEC._uname(t.get("assignee_user"))) or None,
              "issuer": _uinfo(t.get("issuer_user")), "issuer_label": _issuer_label(t), "issuer_unit_name": DEC.unit_name(t.get("issuer_unit")),
              "result_by": _short(DEC._uname(t.get("result_by"))), "review_by": _short(DEC._uname(t.get("review_by"))),
              "progress": {"done": done, "total": len(kids)},
              "suggest_complete": bool(kids) and done == len(kids) and t["status"] != "bajarildi" and w.act(t),
              "can_act": w.act(t), "can_delegate": w.delegate(t), "can_review": w.review(t), "can_cancel": w.cancel(t),
              "can_assign": w.head(t.get("unit")) and t["status"] != "bajarildi",
              "mine": w.mine(t), "awaiting_me": w.review(t), "source": src_info(t)})
    if deep:
        v["attachments"] = _files(t.get("attach"))
        v["result_attachments"] = _files(t.get("result_attach"))
    return v

def _get(tid) -> dict:
    t = db.one(_con, "SELECT * FROM tasks WHERE id=? AND origin=?", (tid, ORIGIN))
    if not t: raise HTTPException(404, "Topshiriq topilmadi")
    return t

# ---------------------------------------------------------------------------------------------
# Boshqa modullar uchun (services.tasks_list, decisions.queue, extras bildirishnomalari, mywork)
# ---------------------------------------------------------------------------------------------
def task_rows(c: Ctx) -> list[dict]:
    """services.tasks_list ga qo'shiladigan qatorlar: ko'rinadigan topshiriqlar, majlis qatorlari shaklida (meeting — kim bergani)."""
    if _con is None: return []   # server starti: modul hali ulanmagan (agent_hub skanerlari DIR.init dan oldin ishlaydi)
    DEC.ensure_migrated()     # /api/meetings orqali yangi kiritilgan bo'limsiz topshiriqlar ham yagona oqimga o'tadi
    w = W(c)
    now, out = clock.now(), []
    for t in w.by.values():
        if not w.view(t): continue
        r = dict(t)
        r.update({"meeting": f"Topshiriq · {_issuer_label(t)}", "meeting_date": (t.get("created_at") or "")[:10], "source": None,
                  "decision": False, "directive": True, "mine": w.mine(t)})
        d = _due_dt(t.get("due_at") or t.get("due"))
        r["overdue"] = bool(d and t["status"] != "bajarildi" and d < now)
        r["days"] = (d.date() - clock.today()).days if d else None
        out.append(r)
    return out

def queue_extra(c: Ctx, t) -> dict:
    """decisions.queue() qatori uchun: topshiriq kartasi ma'lumotlari (UI «Ochish» → topshiriq oynasi)."""
    w = W(c)
    tt = w.by.get(t["id"]) or t
    kids = w.kids.get(t["id"], [])
    return {"directive": True, "meeting": f"Topshiriq · {_issuer_label(tt)}", "meeting_date": (tt.get("created_at") or "")[:10],
            "priority": tt.get("priority"), "review": tt.get("review"), "review_note": tt.get("review_note"),
            "progress": {"done": sum(k["status"] == "bajarildi" for k in kids), "total": len(kids)}, "parent_id": tt.get("parent_id")}

def _link(t): return {"view": "tasks", "directive": t["id"]}

def notifications(c: Ctx) -> list[dict]:
    """extras.notifications ga: yangi topshiriq, qayta ishlashga qaytarildi, natija qabulingizni kutmoqda, natija qabul qilindi.
    (Muddat eslatmalari — services.tasks_list orqali umumiy «topshiriq» bildirishnomalarida.) TASKS ruxsati yo'q ijrochi
    (masalan, Call-markaz) uchun muddat eslatmalari ham shu yerda."""
    w = W(c)
    items, today = [], clock.today()
    recent = _iso(_now() - dt.timedelta(days=3))
    for t in w.by.values():
        sub = " · ".join(x for x in [_issuer_label(t), DEC.unit_name(t.get("unit")) or "",
                                     f"muddat {_due_dt(t.get('due_at') or t.get('due')).strftime('%d.%m.%Y %H:%M')}" if _due_dt(t.get("due_at") or t.get("due")) else ""] if x)
        if w.mine(t) and t["status"] == "yangi" and t.get("issuer_user") != w.uid:
            items.append({"id": f"dy{t['id']}", "kind": "topshiriq", "icon": "tasks", "level": "bad" if t.get("priority") == "shoshilinch" else "info",
                          "title": f"Yangi topshiriq: {t['text']}", "sub": sub, "ts": t.get("created_at") or t.get("updated_at"), "link": _link(t)})
        if w.mine(t) and t.get("review") == "qaytarildi" and t["status"] != "bajarildi":
            items.append({"id": f"dq{t['id']}", "kind": "topshiriq", "icon": "alert", "level": "bad",
                          "title": f"Qayta ishlashga qaytarildi: {t['text']}", "sub": (t.get("review_note") or "")[:140],
                          "ts": t.get("review_at") or t.get("updated_at"), "link": _link(t)})
        if w.review(t):
            items.append({"id": f"dk{t['id']}", "kind": "topshiriq", "icon": "check", "level": "warn",
                          "title": f"Natija qabulingizni kutmoqda: {t['text']}",
                          "sub": " · ".join(x for x in [_short(DEC._uname(t.get("result_by"))), DEC.unit_name(t.get("unit"))] if x),
                          "ts": t.get("result_at") or t.get("updated_at"), "link": _link(t)})
        if t.get("result_by") == w.uid and t.get("review") == "qabul" and (t.get("review_at") or "") >= recent:
            items.append({"id": f"da{t['id']}", "kind": "topshiriq", "icon": "check", "level": "info",
                          "title": f"Natijangiz qabul qilindi: {t['text']}", "sub": _short(DEC._uname(t.get("review_by"))) or "",
                          "ts": t.get("review_at"), "link": _link(t)})
        if not c.can(TASKS) and w.mine(t):
            d = _due_dt(t.get("due_at") or t.get("due"))
            if d and _overdue(t):
                items.append({"id": f"do{t['id']}", "kind": "topshiriq_muddat", "icon": "alert", "level": "bad", "title": f"Topshiriq muddati o'tgan: {t['text']}",
                              "sub": sub, "ts": _iso(dt.datetime.combine(d.date() + dt.timedelta(days=1), dt.time(0))), "link": _link(t)})
            elif d and 0 <= (d.date() - today).days <= 2:
                items.append({"id": f"dn{t['id']}", "kind": "topshiriq", "icon": "clock", "level": "warn", "title": f"Topshiriq muddati yaqin: {t['text']}",
                              "sub": sub, "ts": _iso(dt.datetime.combine(d.date() - dt.timedelta(days=2), dt.time(0))), "link": _link(t)})
    for t in DEC.review_rows(c):      # majlis topshiriqlari: natija qabulingizni kutmoqda / qayta ishlashga qaytarildi
        if t["_kind"] == "review":
            items.append({"id": f"mk{t['id']}", "kind": "topshiriq", "icon": "check", "level": "warn", "title": f"Natija qabulingizni kutmoqda: {t['text']}",
                          "sub": " · ".join(x for x in [t.get("meeting") or "Majlis", _short(DEC._uname(t.get("result_by"))), DEC.unit_name(t.get("unit"))] if x),
                          "ts": t.get("result_at") or t.get("updated_at"), "link": DEC.task_link(t)})
        else:
            items.append({"id": f"mq{t['id']}", "kind": "topshiriq", "icon": "alert", "level": "bad", "title": f"Qayta ishlashga qaytarildi: {t['text']}",
                          "sub": (t.get("review_note") or "")[:140], "ts": t.get("review_at") or t.get("updated_at"), "link": DEC.task_link(t)})
    for it in items: it["ts"] = it["ts"] or _iso(_now())
    return items

def mywork_items(c: Ctx) -> list[dict]:
    """mywork._majlis ga: (1) natija qabulimni kutayotgan topshiriqlar («nazorat»); (2) TASKS ruxsati yo'q ijrochiga biriktirilganlari
    (TASKS bo'lsa ular services.tasks_list orqali allaqachon keladi)."""
    from . import mywork as MW
    w = W(c); out = []
    for t in sorted(w.by.values(), key=lambda t: t["id"]):
        due = t.get("due_at") or t.get("due")
        if w.review(t):
            out.append(MW._item("majlis", "qabul", f"dk{t['id']}", f"Natijani ko'rib chiqing: {t['text']}",
                                " · ".join(x for x in [_short(DEC._uname(t.get("result_by"))), DEC.unit_name(t.get("unit")), "qabul qiling yoki qaytaring"] if x),
                                due, _link(t), "nazorat", "natija kutilmoqda", "mid", icon="check"))
        elif not c.can(TASKS) and w.mine(t):
            out.append(MW._item("majlis", "topshiriq", f"mt{t['id']}", t["text"], " · ".join(x for x in [f"Topshiriq · {_issuer_label(t)}", t["status"]] if x),
                                due, _link(t), "menga" if t.get("assignee_user") == w.uid else "bolimga", t["status"], icon="tasks"))
    for t in DEC.review_rows(c):      # majlis topshiriqlari natijasini rektor qabul qiladi (qaytarilganlari tasks_list orqali «mine» bo'lib keladi)
        if t["_kind"] != "review": continue
        out.append(MW._item("majlis", "qabul", f"mk{t['id']}", f"Natijani ko'rib chiqing: {t['text']}",
                            " · ".join(x for x in [t.get("meeting") or "Majlis", _short(DEC._uname(t.get("result_by"))), DEC.unit_name(t.get("unit")), "qabul qiling yoki qaytaring"] if x),
                            t.get("due_at") or t.get("due"), DEC.task_link(t), "nazorat", "natija kutilmoqda", "mid", icon="check"))
    return out

# ---------------------------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------------------------
def C(request: Request) -> Ctx: return _ctx(request)

def _ok(c: Ctx, action, detail=""):
    rbac.audit(_con, c, action, TASKS, True, detail)

def _deny(c: Ctx, action, detail, msg):
    rbac.audit(_con, c, action, TASKS, False, detail)
    raise AccessDenied(msg)

def _log(tid, c: Ctx, action, detail=""):
    DEC._log(tid, c, action, detail)

def _valid_due(v, required=True):
    if not v:
        if required: raise HTTPException(400, "Muddatni kiriting")
        return None
    try:
        return dt.datetime.fromisoformat(v).isoformat(timespec="minutes") if "T" in v else dt.datetime.combine(dt.date.fromisoformat(v), dt.time(18)).isoformat(timespec="minutes")
    except ValueError:
        raise HTTPException(400, "Muddat formati noto'g'ri")

def _check_files(c: Ctx, ids: list[int], share_units: list[str]) -> list[int]:
    """Portal fayllari: foydalanuvchi ko'ra oladigan bo'lishi shart; topshiriq ijrochi/bergan bo'limlariga ulashiladi (portal_shares)."""
    from . import portal as PT
    out = []
    for i in dict.fromkeys(ids or []):
        f = db.one(_con, "SELECT * FROM portal_files WHERE id=?", (int(i),))
        if not f or not PT.can_see_file(_con, c, f): raise HTTPException(400, f"Ilova #{i} topilmadi yoki sizga ochiq emas")
        own = PT.can_share(c, f)       # yangi ulashmani faqat fayl egasi bo'lim yaratadi (Portal qoidasi)
        for u in share_units:
            o = DEC.org_key(u)
            if not o or o == f["owner_unit"] or PT._has_access(_con, f, o): continue
            if not own: raise HTTPException(400, f"«{f['name']}» fayli boshqa bo'limga tegishli — uni faqat egasi bo'lim ulasha oladi")
            _con.execute("INSERT OR IGNORE INTO portal_shares(file_id,unit) VALUES(?,?)", (f["id"], o))
        out.append(f["id"])
    if len(out) > 10: raise HTTPException(400, "Ilovalar 10 tadan oshmasin")
    return out

@router.get("/api/dir/targets")
def api_targets(request: Request):
    c = C(request)
    return targets_view(c)

class DirIn(BaseModel):
    title: str = Field(..., min_length=3, max_length=300)
    body: str = Field("", max_length=5000)
    unit: str | None = None
    user_id: int | None = None
    due_at: str | None = None
    priority: str = "oddiy"
    expect: str = Field("", max_length=1000)
    attachments: list[int] = []

@router.post("/api/dir")
def api_create(body: DirIn, request: Request):
    c = C(request)
    action = "topshiriq berish"
    if not body.unit and not body.user_id: raise HTTPException(400, "Kimga berilishini tanlang (bo'lim yoki xodim)")
    if body.unit and body.user_id: raise HTTPException(400, "Bo'lim yoki xodimdan bittasini tanlang")
    if body.priority not in PRIOS: raise HTTPException(400, "Noto'g'ri ustuvorlik")
    unit, person = authorize(c, action, body.unit, body.user_id)
    due = _valid_due(body.due_at)
    if due[:10] < clock.today().isoformat(): raise HTTPException(400, "Muddat o'tib ketgan sana bo'lmasin")
    T = targets(c)
    my = DEC.unit_of(c) or ("rektorat" if c.role.key in ("rektor", "kotib") else None)
    files = _check_files(c, body.attachments, [unit, my])
    tid = _insert(_con, c.user["id"], my, T["on_behalf"], body.title.strip(), body.body.strip(), unit, person, due, body.priority,
                  body.expect.strip(), files, None)
    who = _short(DEC._uname(person)) if person else DEC.unit_name(unit)
    _log(tid, c, "topshiriq berildi", (who or "") + (" · rektor nomidan" if T["on_behalf"] else ""))
    _con.commit()
    _ok(c, action, f"#{tid} → {who}")
    return {"ok": True, "id": tid}

@router.get("/api/dir/list")
def api_list(request: Request, flt: str = "all"):
    """«Men bergan topshiriqlar» (filtrlar: overdue — muddati o'tgan, review — qabulimni kutayotgan, open, done) va «Menga kelgan»."""
    c = C(request)
    w = W(c)
    uid = w.uid
    given = [t for t in w.by.values() if t.get("issuer_user") == uid or (c.role.key == "rektor" and t.get("on_behalf") == "rektor")]
    review = [t for t in w.by.values() if w.review(t)]
    got = [t for t in w.by.values() if (t.get("assignee_user") == uid or w.head(t.get("unit"))) and t.get("issuer_user") != uid]
    def f(ts):
        if flt == "overdue": ts = [t for t in ts if _overdue(t)]
        elif flt == "review": ts = [t for t in ts if w.review(t)]
        elif flt == "open": ts = [t for t in ts if t["status"] != "bajarildi" or t.get("review") == "kutilmoqda"]
        elif flt == "done": ts = [t for t in ts if t["status"] == "bajarildi" and t.get("review") != "kutilmoqda"]
        return [node(w, t) for t in sorted(ts, key=lambda t: (t["status"] == "bajarildi", t.get("due_at") or "9999", t["id"]))]
    return {"can_issue": can_issue(c), "given": f(given), "received": f(got), "review": [node(w, t) for t in review],
            "counts": {"given": len(given), "overdue": sum(_overdue(t) for t in given), "review": len(review),
                       "received_open": sum(t["status"] != "bajarildi" for t in got)}}

@router.get("/api/dir/{tid}")
def api_get(tid: int, request: Request):
    c = C(request)
    t = _get(tid)
    w = W(c)
    t = w.by[tid]
    if not w.view(t): _deny(c, "topshiriqni ko'rish", f"#{tid}", "⛔ Bu topshiriq sizga tegishli emas. So'rov audit jurnaliga yozildi.")
    root = t
    while root.get("parent_id") and root["parent_id"] in w.by and w.view(w.by[root["parent_id"]]): root = w.by[root["parent_id"]]
    ids = []
    def rec(x, depth):
        v = node(w, x, deep=True); v["depth"] = depth; ids.append(x["id"])
        v["children"] = [rec(k, depth + 1) for k in w.kids.get(x["id"], []) if w.view(k)]
        return v
    tree = rec(root, 0)
    q = ",".join(map(str, ids))
    log = db.rows(_con, f"SELECT * FROM task_log WHERE task_id IN ({q}) ORDER BY ts, id")
    msgs = db.rows(_con, f"SELECT * FROM task_msgs WHERE task_id IN ({q}) ORDER BY ts, id")
    for x in log + msgs: x["user_short"] = _short(x["user_name"])
    staff = DEC._staff_for(c) if any(w.head(w.by[i].get("unit")) for i in ids) else []
    _ok(c, "topshiriqni ko'rish", f"#{tid}")
    return {"focus": tid, "root": root["id"], "tree": tree, "log": log, "msgs": msgs, "staff": staff,
            "targets": targets_view(c) if any(w.delegate(w.by[i]) for i in ids) else None,
            "parent_hidden": bool(root.get("parent_id"))}

class DelItem(BaseModel):
    unit: str | None = None
    user_id: int | None = None
    title: str | None = Field(None, max_length=300)
    due_at: str | None = None

class DelegateIn(BaseModel):
    items: list[DelItem] = Field(..., min_length=1, max_length=20)
    note: str = Field("", max_length=3000)

@router.post("/api/dir/{tid}/delegate")
def api_delegate(tid: int, body: DelegateIn, request: Request):
    c = C(request)
    action = "topshiriqni taqsimlash"
    t = _get(tid); w = W(c); t = w.by[tid]
    if not w.head(t.get("unit")):
        _deny(c, action, f"#{tid}", "⛔ Topshiriqni faqat uni olgan bo'lim rahbari taqsimlaydi. So'rov audit jurnaliga yozildi.")
    if t["status"] == "bajarildi": raise HTTPException(409, "Yakunlangan topshiriqni taqsimlab bo'lmaydi")
    pdue = t.get("due_at")
    plan = []
    for it in body.items:
        if bool(it.unit) == bool(it.user_id): raise HTTPException(400, "Har bir qatorda bo'lim yoki xodimdan bittasini tanlang")
        unit, person = authorize(c, action, it.unit, it.user_id)
        due = _valid_due(it.due_at, required=False) or pdue
        if pdue and due and due > pdue: raise HTTPException(400, f"Quyi topshiriq muddati asosiy topshiriq muddatidan ({pdue.replace('T', ' ')}) kech bo'lmasin")
        if due and due[:10] < clock.today().isoformat(): raise HTTPException(400, "Muddat o'tib ketgan sana bo'lmasin")
        dup = [k for k in w.kids.get(tid, []) if k["status"] != "bajarildi" and k["unit"] == unit and k.get("assignee_user") == person]
        if dup or any(p[0] == unit and p[1] == person for p in plan):
            raise HTTPException(409, f"«{_short(DEC._uname(person)) if person else DEC.unit_name(unit)}» ga bu topshiriq allaqachon berilgan")
        plan.append((unit, person, due, (it.title or "").strip() or t["text"]))
    files = json.loads(t["attach"]) if t.get("attach") else []
    if files: _check_files(c, files, [p[0] for p in plan])
    out = []
    for unit, person, due, title in plan:
        cid = _insert(_con, c.user["id"], DEC.unit_of(c), None, title, body.note.strip() or t.get("body") or "", unit, person, due,
                      t.get("priority") or "oddiy", t.get("expect") or "", files, tid)
        who = _short(DEC._uname(person)) if person else DEC.unit_name(unit)
        _log(cid, c, "topshiriq berildi", who or "")
        _log(tid, c, "taqsimlandi", f"{who} — muddat {(due or '').replace('T', ' ')}")
        out.append(cid)
    if t["status"] == "yangi":
        _con.execute("UPDATE tasks SET status='jarayonda', updated_at=? WHERE id=?", (_iso(_now()), tid))
    _con.commit()
    _ok(c, action, f"#{tid} → {len(out)} ta")
    return {"ok": True, "ids": out}

class StatusIn(BaseModel):
    status: str
    result: str | None = Field(None, max_length=5000)
    attachments: list[int] = []

def set_status(c: Ctx, tid: int, body: StatusIn):
    action = "topshiriq holatini yangilash"
    t = _get(tid); w = W(c); t = w.by[tid]
    if not w.act(t):
        if t["status"] == "bajarildi": raise HTTPException(409, "Topshiriq allaqachon yakunlangan")
        _deny(c, action, f"#{tid}", "⛔ Holatni faqat ijrochi yoki topshiriqni olgan bo'lim rahbari yangilaydi. So'rov audit jurnaliga yozildi.")
    if body.status not in ("jarayonda", "bajarildi"): raise HTTPException(400, "Noto'g'ri holat")
    res = (body.result or "").strip()
    now = _iso(_now())
    if body.status == "bajarildi":
        if not res: raise HTTPException(400, "Yakunlash uchun natijani yozing")
        kids = w.kids.get(tid, [])
        open_ = [k for k in kids if k["status"] != "bajarildi"]
        if open_:
            raise HTTPException(409, f"Avval quyi topshiriqlar bajarilishi kerak ({len(kids) - len(open_)}/{len(kids)} bajarildi)")
    files = _check_files(c, body.attachments, [t.get("issuer_unit")]) if body.attachments else []
    if not t.get("assignee_user") and body.status == "bajarildi" or (not t.get("assignee_user") and t["status"] == "yangi"):
        _con.execute("UPDATE tasks SET assignee_user=?, assignee=? WHERE id=?", (c.user["id"], _short(c.user["full_name"]), tid))
    if body.status == "bajarildi":
        self_issued = t.get("issuer_user") == c.user["id"]
        rv = "qabul" if self_issued else "kutilmoqda"
        _con.execute("""UPDATE tasks SET status='bajarildi', result=?, result_at=?, result_by=?, updated_at=?, review=?, review_note=NULL,
                        result_attach=COALESCE(?, result_attach) WHERE id=? AND status!='bajarildi'""",
                     (res, now, c.user["id"], now, rv, json.dumps(files) if files else None, tid))
        _log(tid, c, "bajarildi — natija yuborildi", res[:200])
        for k in w.kids.get(tid, []):          # yakuniy natija bilan quyi natijalar ham qabul qilinadi (ularni shu rahbar bergan)
            if k.get("review") == "kutilmoqda":
                _con.execute("UPDATE tasks SET review='qabul', review_at=?, review_by=? WHERE id=?", (now, c.user["id"], k["id"]))
                _log(k["id"], c, "qabul qilindi", "yakuniy natija bilan")
    else:
        if res and res != (t.get("result") or ""):
            _con.execute("UPDATE tasks SET result=?, result_by=?, result_at=? WHERE id=?", (res, c.user["id"], now, tid))
            _log(tid, c, "oraliq natija", res[:200])
        if files: _con.execute("UPDATE tasks SET result_attach=? WHERE id=?", (json.dumps(files), tid))
        if t["status"] != "jarayonda":
            _log(tid, c, "ish boshlandi")
        _con.execute("UPDATE tasks SET status='jarayonda', updated_at=? WHERE id=?", (now, tid))
    _con.commit()
    _ok(c, action, f"#{tid} → {body.status}")
    return {"ok": True}

@router.post("/api/dir/{tid}/status")
def api_status(tid: int, body: StatusIn, request: Request):
    return set_status(C(request), tid, body)

class ReviewIn(BaseModel):
    decision: str
    note: str = Field("", max_length=2000)

@router.post("/api/dir/{tid}/review")
def api_review(tid: int, body: ReviewIn, request: Request):
    return do_review(C(request), tid, body.decision, body.note)

def do_review(c: Ctx, tid: int, decision: str, note: str = ""):
    body = ReviewIn(decision=decision, note=note or "")
    action = "topshiriq natijasini ko'rib chiqish"
    t = _get(tid); w = W(c); t = w.by[tid]
    if not w.reviewer(t):
        _deny(c, action, f"#{tid}", "⛔ Natijani topshiriqni bergan rahbar (yoki zanjirda yuqoridagi rahbar) qabul qiladi. So'rov audit jurnaliga yozildi.")
    if t["status"] != "bajarildi" or t.get("review") != "kutilmoqda": raise HTTPException(409, "Natija hali yuborilmagan yoki allaqachon ko'rib chiqilgan")
    if t.get("result_by") == c.user["id"]: raise HTTPException(409, "O'z natijangizni o'zingiz qabul qila olmaysiz")
    now, note = _iso(_now()), body.note.strip()
    if body.decision == "qabul":
        _con.execute("UPDATE tasks SET review='qabul', review_note=?, review_at=?, review_by=?, updated_at=? WHERE id=?", (note or None, now, c.user["id"], now, tid))
        _log(tid, c, "qabul qilindi", note)
    elif body.decision == "qaytarish":
        if not note: raise HTTPException(400, "Qaytarish sababini yozing")
        p = w.by.get(t.get("parent_id"))
        if p and p["status"] == "bajarildi": raise HTTPException(409, "Asosiy topshiriq yakunlangan — quyi natijani qaytarib bo'lmaydi")
        _con.execute("UPDATE tasks SET status='jarayonda', review='qaytarildi', review_note=?, review_at=?, review_by=?, updated_at=? WHERE id=?",
                     (note, now, c.user["id"], now, tid))
        _log(tid, c, "qayta ishlashga qaytarildi", note)
    else:
        raise HTTPException(400, "Noto'g'ri qaror")
    _con.commit()
    _ok(c, action, f"#{tid} → {body.decision}")
    return {"ok": True}

class MsgIn(BaseModel):
    text: str = Field(..., min_length=1, max_length=2000)

@router.post("/api/dir/{tid}/msg")
def api_msg(tid: int, body: MsgIn, request: Request):
    c = C(request)
    t = _get(tid); w = W(c); t = w.by[tid]
    if not w.view(t): _deny(c, "topshiriqqa izoh yozish", f"#{tid}", "⛔ Bu topshiriq sizga tegishli emas.")
    txt = body.text.strip()
    if not txt: raise HTTPException(400, "Bo'sh xabar")
    _con.execute("INSERT INTO task_msgs(task_id,ts,user_id,user_name,role,text) VALUES(?,?,?,?,?,?)",
                 (tid, _iso(_now()), c.user["id"], c.user["full_name"], c.title, txt))
    _con.commit()
    return {"ok": True}

@router.post("/api/dir/{tid}/assign")
def api_assign(tid: int, body: DEC.Assign, request: Request):
    """Bo'lim rahbari topshiriqni o'z bo'limi xodimiga biriktiradi (decisions.assign bilan bir xil qoida)."""
    _get(tid)
    return DEC.assign(tid, body, request)

@router.delete("/api/dir/{tid}")
def api_cancel(tid: int, request: Request):
    """Bekor qilish: faqat bergan kishi (kotib bergan bo'lsa — rektor ham). Butun quyi zanjir o'chiriladi; audit jurnalida qoladi."""
    c = C(request)
    action = "topshiriqni bekor qilish"
    t = _get(tid); w = W(c); t = w.by[tid]
    if not w.cancel(t): _deny(c, action, f"#{tid}", "⛔ Topshiriqni faqat uni bergan kishi bekor qiladi. So'rov audit jurnaliga yozildi.")
    ids, stack = [], [tid]
    while stack:
        i = stack.pop(); ids.append(i); stack += [k["id"] for k in w.kids.get(i, [])]
    q = ",".join(map(str, ids))
    _con.execute(f"DELETE FROM task_msgs WHERE task_id IN ({q})"); _con.execute(f"DELETE FROM task_log WHERE task_id IN ({q})")
    _con.execute(f"DELETE FROM tasks WHERE id IN ({q})")
    _con.commit()
    _ok(c, action, f"#{tid} «{t['text'][:80]}» · {len(ids)} ta yozuv")
    return {"ok": True, "removed": len(ids)}
