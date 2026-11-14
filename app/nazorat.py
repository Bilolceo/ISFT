"""«Nazorat markazi» — rektor faqat NAZORAT qiladi: mayda ishlar emas, faqat istisnolar (muammo bor joylar) va har birining egasi.

Rektor talabi: «Rektor faqat nazorat qilishi kerak, mayda ishlarni emas». Shu sahifa rektorning bosh sahifasi; prorektorlar — o'z
vakolatidagi (kuratorligidagi) bo'limlar bo'yicha shu sahifaning qisqartirilgan ko'rinishi.

Yangi ma'lumot manbai YO'Q — istisnolar mavjud modullardan hisoblanadi (qoidalar — nz_rules, rektor «Sozlamalar»da o'zgartiradi):
  ijro      — topshiriqlar (majlis qarorlari va ierarxik topshiriqlar — `tasks`): muddati ≥ N kun o'tgan (standart 3);
  oquv      — masofaviy ta'lim: guruhda «ortda qolgan» talabalar soni chegaradan oshgan (app/ortda.py — jamlangan sonlar),
              dars paketi / kurs tasdiqni > N kun kutmoqda (app/paket.py, app/kurs.py);
  talabalar — ≥ 7 kun faolsiz masofaviy talabalar (tyutor bo'yicha jamlangan), Talabalar markazi navbatida kechikkan topshiriqlar;
  moliya    — aniqlanmagan bank to'lovlari, tasdiq kutayotgan xarajatlar («moliya» bo'limi yoqilgan bo'lsa);
  kadrlar   — muddati o'tgan mehnat shartnomalari (jamlangan son; «kadrlar» bo'limi yoqilgan bo'lsa);
  hujjat    — buyruqlar: prorektor kelishuvini / devonxona jurnalini kutib qolganlari.
Har bir istisno: nima, qachondan, egasi (xodim + lavozim), muddat va nega qizil. Bo'limi o'chirilgan soha (app/modules.py) kuzatilmaydi.

ESKALATSIYA (egasi → uning rahbari → rektor): istisno paydo bo'lgan vaqtdan (since) boshlab owner_days kun — egasida, keyingi head_days
kun — rahbarida (bo'lim boshlig'i; egasi bo'lim boshlig'ining o'zi bo'lsa — kurator prorektor), shundan keyingina rektorga yetadi.
Har bosqichga o'tganda o'sha kishiga bitta bildirishnoma (nz_items.notified_level — idempotent). Fon skaneri — har 10 daqiqada (scan()).

4 AMAL (har biri audit jurnalida va Topshiriqlar tizimida — app/directives.py):
  eslatish    — egasiga bildirishnoma + topshiriq chatida eslatma (topshiriq bo'lmasa — «Nazorat» topshirig'i yaratiladi, src='nz:<kalit>');
  muddat      — yangi muddat + izoh: topshiriq muddati o'zgaradi (agregat istisno — shu muddatgacha «kutishda»);
  tayinlash   — boshqa mas'ulga (bo'lim yoki rahbariga ko'tarish): topshiriq qayta tayinlanadi, eskalatsiya soati qaytadan boshlanadi;
  korildi     — «Ko'rdim»: shu foydalanuvchi uchun holati o'zgarmaguncha yashiriladi (state_hash).

IMZO NAVBATI — rahbar qarorini kutayotgan hujjatlar («Mening vazifalarim»dagi sign=True ishlar, eng eskisi birinchi); buyruqlarni shu yerning
o'zida imzolash / izoh bilan qaytarish (app/orders.py qoidalari bilan).

HAFTALIK HISOBOT — dushanba 08:00 (Toshkent): 5–8 qator (nima yaxshilandi, nima to'xtab qoldi, kerakli 3 qaror). Ilovada (bildirishnoma +
sahifa) va rektorga Telegram orqali (bot ulangan bo'lsa; TELEGRAM_BOT_TOKEN yo'q — jim o'tkaziladi). ANTHROPIC_API_KEY bo'lsa — matnni
Claude qisqartiradi: unga FAQAT jamlangan sonlar beriladi (ism, lavozim, topshiriq matni yo'q), javob — qat'iy JSON; kalit bo'lmasa yoki
xato bo'lsa — qoidaviy (deterministik) matn.

Ruxsat: faqat rektor va prorektorlar (prorektor — o'z ko'lami). Qoidalar va haftalik hisobot — rektor.
"""
from __future__ import annotations
import datetime as dt, hashlib, json, os, threading, urllib.parse, urllib.request
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from . import clock, db, rbac, modules as MODS
from .rbac import Ctx, AccessDenied

router = APIRouter()
_con = None
_ctx = None
_lock = threading.RLock()
RES = "nazorat"
P = "/api/nazorat"

LEAD = "rektor"
PRO = ("prorektor_oquv", "prorektor_ilmiy", "prorektor_moliya", "prorektor_yoshlar")
ROLES = (LEAD,) + PRO

AREAS = [("ijro", "Ijro va topshiriqlar", "tasks"), ("oquv", "O'quv jarayoni va masofaviy ta'lim", "monitor"),
         ("talabalar", "Talabalar", "users"), ("moliya", "Moliya", "money"), ("kadrlar", "Kadrlar", "idcard"),
         ("hujjat", "Hujjatlar va imzo", "scroll")]
AREA_T = {k: t for k, t, _ in AREAS}
# soha qaysi bo'lim(lar) kalitiga bog'liq (app/modules.py): birortasi yoqilgan bo'lsa kuzatiladi
AREA_MODS = {"ijro": ("tasks",), "oquv": ("masofaviy", "paket"), "talabalar": ("masofaviy", "ops"), "moliya": ("moliya",),
             "kadrlar": ("kadrlar",), "hujjat": ("orders",)}

# ---- qoidalar (rektor o'zgartiradi) ----
RULES = {   # kalit: (standart, min, max, nomi)
    "task_overdue_days": (3, 1, 30, "Topshiriq muddati o'tganiga (kun) — istisno"),
    "student_inactive_days": (7, 3, 60, "Talaba faolsizligi (kun)"),
    "tutor_inactive_min": (3, 1, 100, "Tyutor bo'yicha faolsiz talabalar soni (kamida)"),
    "group_risk_threshold": (3, 1, 100, "Guruhda ortda qolgan talabalar soni (kamida)"),
    "review_wait_days": (5, 1, 60, "Dars paketi / kurs tasdiqni kutishi (kun)"),
    "ops_overdue_days": (2, 1, 30, "Talabalar markazi topshirig'i kechikishi (kun)"),
    "doc_wait_days": (3, 1, 30, "Buyruq kelishuv / jurnalni kutishi (kun)"),
    "fin_unmatched_days": (3, 1, 60, "Aniqlanmagan bank to'lovi (kun)"),
    "fin_expense_days": (3, 1, 60, "Xarajat tasdig'ini kutishi (kun)"),
    "hr_contract_expired": (1, 1, 100, "Muddati o'tgan mehnat shartnomalari (kamida)"),
    "owner_days": (2, 0, 30, "Eskalatsiya: egasida (kun)"),
    "head_days": (2, 0, 30, "Eskalatsiya: rahbarida (kun), keyin — rektorga"),
}
STAGE_T = {0: "Egasida", 1: "Rahbarida", 2: "Rektorda"}

SCHEMA = """
CREATE TABLE IF NOT EXISTS nz_rules(k TEXT PRIMARY KEY, v INT, updated_at TEXT, updated_by TEXT);
CREATE TABLE IF NOT EXISTS nz_items(key TEXT PRIMARY KEY, area TEXT, kind TEXT, title TEXT, first_seen TEXT, last_seen TEXT, status TEXT,
    closed_at TEXT, since TEXT, reset_at TEXT, snooze_until TEXT, notified_level INT DEFAULT -1, notified_user INT, task_id INT,
    owner_user INT, owner_unit TEXT, ov_user INT, ov_unit TEXT, state_hash TEXT, stage INT, data TEXT);
CREATE TABLE IF NOT EXISTS nz_acks(user_id INT, key TEXT, hash TEXT, ts TEXT, PRIMARY KEY(user_id, key));
CREATE TABLE IF NOT EXISTS nz_notes(id INTEGER PRIMARY KEY, user_id INT, ts TEXT, kind TEXT, level TEXT, title TEXT, sub TEXT, link TEXT, item_key TEXT);
CREATE INDEX IF NOT EXISTS ix_nz_notes_user ON nz_notes(user_id, ts);
CREATE TABLE IF NOT EXISTS nz_log(id INTEGER PRIMARY KEY, ts TEXT, user_id INT, user_name TEXT, key TEXT, action TEXT, detail TEXT);
CREATE TABLE IF NOT EXISTS nz_briefs(id INTEGER PRIMARY KEY, week TEXT UNIQUE, created_at TEXT, source TEXT, lines TEXT, decisions TEXT,
    stats TEXT, tg TEXT);
"""


def init(con):
    con.executescript(SCHEMA)
    con.commit()


def bind(con, ctx_fn):
    global _con, _ctx
    _con, _ctx = con, ctx_fn


def _now() -> dt.datetime: return clock.now().replace(microsecond=0)
def _iso(t: dt.datetime) -> str: return t.replace(microsecond=0).isoformat(timespec="seconds")
def _short(n): return (n or "").split(":", 1)[1].strip() if ":" in (n or "") else (n or "")
def _dmy(v) -> str:
    v = str(v or "")[:10]
    return f"{v[8:10]}.{v[5:7]}.{v[:4]}" if len(v) == 10 and v[4] == "-" else v


def _dt(v) -> dt.datetime | None:
    s = str(v or "").strip().replace(" ", "T")
    if not s: return None
    try:
        return dt.datetime.fromisoformat(s[:19]) if "T" in s else dt.datetime.combine(dt.date.fromisoformat(s[:10]), dt.time(23, 59))
    except ValueError:
        return None


def _days(a: dt.datetime, b: dt.datetime) -> float:
    return (b - a).total_seconds() / 86400


# =============================================================================================
# Qoidalar
# =============================================================================================
def rules(con=None) -> dict:
    con = con or _con
    out = {k: v[0] for k, v in RULES.items()}
    try:
        for r in db.rows(con, "SELECT k, v FROM nz_rules"):
            if r["k"] in RULES: out[r["k"]] = int(r["v"])
    except Exception:
        pass
    return out


def rules_view(con=None) -> list[dict]:
    cur = rules(con)
    return [{"key": k, "value": cur[k], "default": d, "min": lo, "max": hi, "label": t} for k, (d, lo, hi, t) in RULES.items()]


# =============================================================================================
# Egalar va eskalatsiya zanjiri
# =============================================================================================
class Org:
    """Bitta skan uchun: bo'limlar rahbarlari, kuratorlar, foydalanuvchilar (xotirada)."""
    def __init__(self, con):
        self.units = {r["key"]: r for r in db.rows(con, "SELECT key, name, grp, head_user, curator FROM org_units")}
        self.users = {r["id"]: r for r in db.rows(con, "SELECT id, full_name, role, unit, telegram_id, active FROM users")}
        first = {}
        for u in sorted(self.users.values(), key=lambda u: u["id"]):
            if u.get("active") == 0: continue
            first.setdefault(u["role"], u["id"])
        self.by_role = first
        self.rektor = first.get("rektor")

    def head(self, unit) -> int | None:
        return (self.units.get(unit) or {}).get("head_user")

    def unit_name(self, unit) -> str:
        from . import decisions as DEC
        return (self.units.get(unit) or {}).get("name") or DEC.unit_name(DEC.task_key(unit)) or unit or "—"

    def person(self, uid) -> dict | None:
        u = self.users.get(uid)
        if not u: return None
        return {"id": u["id"], "name": _short(u["full_name"]) or u["full_name"], "position": rbac.user_title(u), "role": u["role"]}

    def chain(self, owner, unit) -> list:
        """[egasi, rahbari, rektor]. Egasi bo'lim boshlig'i (yoki egasi yo'q) bo'lsa — rahbari kurator prorektor, u ham bo'lmasa — rektor."""
        h = self.head(unit)
        if owner and h and owner != h:
            head = h
        else:
            cur = (self.units.get(unit) or {}).get("curator")
            cu = self.by_role.get(cur) if cur else None
            head = cu if cu and cu != owner else self.rektor
        if not owner: owner = h if h and h != head else None
        if head == owner: head = self.rektor
        return [owner, head, self.rektor]


def stage_of(since: dt.datetime, now: dt.datetime, R: dict, head_is_rektor: bool = False) -> int:
    """Eskalatsiya bosqichi: 0 — egasida, 1 — rahbarida, 2 — rektorda. Rahbari rektorning o'zi bo'lsa 1-bosqich bo'lmaydi."""
    e = _days(since, now)
    if e < R["owner_days"]: return 0
    if head_is_rektor or e >= R["owner_days"] + R["head_days"]: return 2
    return 1


# =============================================================================================
# Istisnolarni aniqlash (detektorlar). Har biri nomzodlar ro'yxatini qaytaradi:
#   {key, area, kind, title, why, since (dt), owner (user id|None), unit (org kaliti), deadline, link, state (hash uchun), task_id, aggregate}
# =============================================================================================
def _task_cands(con, now, R, O: Org) -> list[dict]:
    from . import decisions as DEC
    T = R["task_overdue_days"]
    rows = db.rows(con, """SELECT t.* FROM tasks t LEFT JOIN meetings m ON m.id=t.meeting_id
                           WHERE t.status NOT IN ('bajarildi','qoralama') AND (t.meeting_id IS NULL OR COALESCE(m.status,'') != 'qoralama')""")
    late = {}
    for t in rows:
        d = _dt(t.get("due_at") or t.get("due"))
        if d and _days(d, now) >= T: late[t["id"]] = (t, d)
    parents_with_late_kids = {t["parent_id"] for t, _ in late.values() if t.get("parent_id")}
    out = []
    for tid, (t, d) in late.items():
        if tid in parents_with_late_kids: continue           # zanjirda — eng quyi (haqiqiy ijrochi) ko'rsatiladi
        unit = DEC.org_key(t.get("unit")) or (O.users.get(t.get("assignee_user")) or {}).get("unit")
        owner = t.get("assignee_user") or O.head(unit)
        n = int(_days(d, now))
        link = {"view": "tasks", "directive": tid} if t.get("origin") == "topshiriq" else DEC.task_link(t)
        src = "Majlis qarori" if t.get("meeting_id") else "Topshiriq"
        out.append({"key": f"task:{tid}", "area": "ijro", "kind": "topshiriq", "title": t["text"], "task_id": tid,
                    "why": f"Muddati {_dmy(d.date().isoformat())} edi — {n} kun kechikmoqda (qoida: ≥ {T} kun)", "src": src,
                    "since": d + dt.timedelta(days=T), "owner": owner, "unit": unit, "deadline": (t.get("due_at") or t.get("due")),
                    "link": link, "state": [t["status"], t.get("due_at") or t.get("due"), t.get("assignee_user"), t.get("unit"), t.get("review")]})
    return out


def _rektor_ctx(con, O: Org) -> Ctx | None:
    return rbac.Ctx(O.users[O.rektor], rbac.ROLES["rektor"], "web") if O.rektor in O.users else None


def _lrs_cands(con, now, R, O: Org) -> list[dict]:
    """Masofaviy ta'lim (app/ortda.py — faqat jamlangan sonlar): guruhlar bo'yicha ortda qolganlar va tyutorlar bo'yicha faolsizlar."""
    from . import ortda as ORT
    c = _rektor_ctx(con, O)
    if not c or ORT._con is None: return []
    try:
        rows = ORT.all_rows(c)
    except Exception as e:
        print("nazorat.lrs:", repr(e)); return []
    tut = {r["group_id"]: r["user_id"] for r in db.rows(con, "SELECT group_id, user_id FROM tutor_groups")}
    out = []
    if MODS.on("masofaviy") or MODS.on("paket"):
        by = {}
        for r in rows:
            if not r["reasons"]: continue
            g = by.setdefault(r["group_id"], {"grp": r["grp"], "sids": set(), "codes": {}})
            if r["student_id"] in g["sids"]: continue
            g["sids"].add(r["student_id"])
            for x in r["reasons"]: g["codes"][x["label"]] = g["codes"].get(x["label"], 0) + 1
        th = R["group_risk_threshold"]
        for gid, g in by.items():
            n = len(g["sids"])
            if n < th: continue
            top = ", ".join(f"{k.lower()} — {v}" for k, v in sorted(g["codes"].items(), key=lambda kv: -kv[1])[:3])
            out.append({"key": f"grp:{gid}", "area": "oquv", "kind": "guruh", "title": f"{g['grp'] or 'Guruh'}: {n} talaba masofaviy kursda ortda qolmoqda",
                        "why": f"Ortda qolganlar {n} ta (chegara — {th}); sabablar: {top}", "src": "Ortda qolganlar (LRS)",
                        "since": None, "owner": tut.get(gid) or O.head("masofaviy"), "unit": "masofaviy", "deadline": None,
                        "link": {"view": "ortda"}, "state": [n], "aggregate": True})
    if MODS.on("masofaviy"):
        D, mn = R["student_inactive_days"], R["tutor_inactive_min"]
        per = {}
        for r in rows:
            di = r.get("days_inactive")
            if di is None or di < D: continue
            k = tut.get(r["group_id"]) or 0
            cross = dt.datetime.combine(dt.date.fromisoformat(r["last"][:10]) + dt.timedelta(days=D), dt.time(8))
            p = per.setdefault(k, {})
            p[r["student_id"]] = min(p.get(r["student_id"], cross), cross)
        for k, st in per.items():
            n = len(st)
            if n < mn: continue
            since = sorted(st.values())[mn - 1]                       # chegaradan oshgan kun — mn-chi talaba faolsiz bo'lgan kun
            who = O.person(k)
            out.append({"key": f"tut:{k}", "area": "talabalar", "kind": "faolsiz",
                        "title": f"{n} ta masofaviy talaba {D}+ kun faolsiz" + (f" — {who['name']} guruhlari" if who else " — tyutori biriktirilmagan guruhlar"),
                        "why": f"LMS'ga {D} kundan beri kirmagan talabalar: {n} ta (chegara — {mn})", "src": "Ortda qolganlar (LRS)",
                        "since": since, "owner": k or O.head("masofaviy"), "unit": "masofaviy", "deadline": None,
                        "link": {"view": "ortda"}, "state": [n], "aggregate": True})
    return out


def _review_cands(con, now, R, O: Org) -> list[dict]:
    if not MODS.on("paket"): return []
    N, out = R["review_wait_days"], []
    lim = _iso(now - dt.timedelta(days=N))
    for kind, sql, label, link in (
            ("paket", "SELECT COUNT(*) n, MIN(built_at) d FROM pk_packages WHERE status='tayyor' AND topic_no>0 AND built_at<?", "dars paketi",
             {"view": "paket"}),
            ("kurs", "SELECT COUNT(*) n, MIN(submitted_at) d FROM ku_courses WHERE deleted=0 AND status='korib_chiqishda' AND submitted_at<?", "kurs",
             {"view": "kurs"})):
        try: r = db.one(con, sql, (lim,)) or {}
        except Exception: continue
        if not r.get("n"): continue
        d0 = _dt(r["d"]) or now
        out.append({"key": f"rev:{kind}", "area": "oquv", "kind": "tasdiq", "title": f"{r['n']} ta {label} tasdiqni {N} kundan ortiq kutmoqda",
                    "why": f"Eng eskisi {_dmy(r['d'])} dan beri bo'lim tasdig'ida (qoida: > {N} kun)", "src": "Dars tayyorlash",
                    "since": d0 + dt.timedelta(days=N), "owner": O.head("masofaviy"), "unit": "masofaviy", "deadline": None,
                    "link": link, "state": [r["n"]], "aggregate": True})
    return out


OPS_UNIT = {"call_center": "talabalar", "talabalar": "talabalar", "registrator_xodim": "talabalar", "tyutor": "talabalar", "sirtqi": "sirtqi",
            "buxgalteriya": "buxgalteriya", "imtihon": "imtihon", "akademik": "akademik"}

def _ops_cands(con, now, R, O: Org) -> list[dict]:
    if not MODS.on("ops"): return []
    from . import student_ops as OPSM
    N = R["ops_overdue_days"]
    out = []
    for r in db.rows(con, "SELECT assignee_role r, COUNT(*) n, MIN(due_at) d FROM ops_tasks WHERE status='yangi' AND due_at<? GROUP BY assignee_role",
                     (_iso(now - dt.timedelta(days=N)),)):
        unit = OPS_UNIT.get(r["r"], r["r"])
        role_t = OPSM.ROLE_T.get(r["r"]) if hasattr(OPSM, "ROLE_T") else None
        out.append({"key": f"ops:{r['r']}", "area": "talabalar", "kind": "navbat",
                    "title": f"Talabalar markazi: {r['n']} ta topshiriq {N}+ kun kechikkan ({role_t or rbac.ROLES.get(r['r'], rbac.ROLES['talabalar']).title} navbati)",
                    "why": f"Eng eski muddat — {_dmy(r['d'])} (qoida: ≥ {N} kun)", "src": "Talabalar navbati",
                    "since": (_dt(r["d"]) or now) + dt.timedelta(days=N), "owner": O.head(unit), "unit": unit, "deadline": None,
                    "link": {"view": "ops", "tab": "navbat"}, "state": [r["n"]], "aggregate": True})
    return out


def _doc_cands(con, now, R, O: Org) -> list[dict]:
    if not MODS.on("orders"): return []
    from . import orders as ORD
    N, out = R["doc_wait_days"], []
    lim = _iso(now - dt.timedelta(days=N))
    staff = "(" + ",".join(f"'{k}'" for k in ORD.STAFF_KINDS) + ")" if ORD.STAFF_KINDS else "('')"
    r = db.one(con, f"SELECT COUNT(*) n, MIN(submitted_at) d FROM orders WHERE status='yuborilgan' AND kind NOT IN {staff} AND submitted_at<?", (lim,)) or {}
    if r.get("n"):
        pro = O.by_role.get("prorektor_oquv")
        out.append({"key": "doc:kelishuv", "area": "hujjat", "kind": "kelishuv", "title": f"{r['n']} ta buyruq loyihasi prorektor kelishuvini kutmoqda",
                    "why": f"Imzoga {_dmy(r['d'])} da yuborilgan, {N} kundan ortiq kelishilmagan", "src": "Buyruqlar",
                    "since": (_dt(r["d"]) or now) + dt.timedelta(days=N), "owner": pro, "unit": "prorektor_oquv", "deadline": None,
                    "link": {"view": "orders"}, "state": [r["n"]], "aggregate": True})
    r = db.one(con, """SELECT COUNT(*) n, MIN(signed_at) d FROM orders WHERE status='imzolangan' AND COALESCE(historic,0)=0 AND journal_at IS NULL
                       AND signed_at<?""", (lim,)) or {}
    if r.get("n"):
        out.append({"key": "doc:jurnal", "area": "hujjat", "kind": "jurnal", "title": f"{r['n']} ta imzolangan buyruq devonxona jurnaliga olinmagan",
                    "why": f"Eng eskisi {_dmy(r['d'])} da imzolangan (qoida: > {N} kun)", "src": "Buyruqlar",
                    "since": (_dt(r["d"]) or now) + dt.timedelta(days=N), "owner": O.head("devonxona"), "unit": "devonxona", "deadline": None,
                    "link": {"view": "orders"}, "state": [r["n"]], "aggregate": True})
    return out


def _fin_cands(con, now, R, O: Org) -> list[dict]:
    if not MODS.on("moliya"): return []
    out = []
    try:
        N = R["fin_unmatched_days"]
        r = db.one(con, "SELECT COUNT(*) n, COALESCE(SUM(amount),0) s, MIN(line_date) d FROM fin_bank_lines WHERE status='aniqlanmagan' AND line_date<?",
                   ((now.date() - dt.timedelta(days=N)).isoformat(),)) or {}
        if r.get("n"):
            out.append({"key": "fin:bank", "area": "moliya", "kind": "bank", "title": f"{r['n']} ta bank to'lovi {N}+ kundan beri aniqlanmagan",
                        "why": f"Jami {int(r['s']):,} so'm; eng eskisi {_dmy(r['d'])}".replace(",", " "), "src": "Moliya",
                        "since": (_dt(r["d"]) or now) + dt.timedelta(days=N), "owner": O.head("buxgalteriya"), "unit": "buxgalteriya", "deadline": None,
                        "link": {"view": "moliya", "tab": "bank"}, "state": [r["n"]], "aggregate": True})
        N = R["fin_expense_days"]
        r = db.one(con, "SELECT COUNT(*) n, MIN(created_at) d FROM fin_expenses WHERE status='kutilmoqda' AND created_at<?",
                   (_iso(now - dt.timedelta(days=N)),)) or {}
        if r.get("n"):
            out.append({"key": "fin:xarajat", "area": "moliya", "kind": "xarajat", "title": f"{r['n']} ta xarajat tasdig'i {N}+ kun kutmoqda",
                        "why": f"Eng eskisi {_dmy(r['d'])} da kiritilgan", "src": "Moliya",
                        "since": (_dt(r["d"]) or now) + dt.timedelta(days=N), "owner": O.by_role.get("prorektor_moliya"), "unit": "prorektor_moliya",
                        "deadline": None, "link": {"view": "moliya", "tab": "expenses"}, "state": [r["n"]], "aggregate": True})
    except Exception as e:
        print("nazorat.moliya:", repr(e))
    return out


def _hr_cands(con, now, R, O: Org) -> list[dict]:
    if not MODS.on("kadrlar"): return []
    from . import kadrlar as KD
    c = _rektor_ctx(con, O)
    try:
        q = KD.kpi(c, "rektor") if c and KD._con is not None else {}
    except Exception as e:
        print("nazorat.kadrlar:", repr(e)); q = {}
    n = int(q.get("contract_expired") or 0)
    if n < R["hr_contract_expired"]: return []
    return [{"key": "hr:shartnoma", "area": "kadrlar", "kind": "shartnoma", "title": f"{n} ta mehnat shartnomasi muddati o'tgan",
             "why": f"Uzaytirilmagan yoki bo'shatish rasmiylashtirilmagan (chegara — {R['hr_contract_expired']})", "src": "Kadrlar",
             "since": None, "owner": O.head("kadrlar"), "unit": "kadrlar", "deadline": None, "link": {"view": "kadrlar"}, "state": [n], "aggregate": True}]


DETECTORS = [_task_cands, _lrs_cands, _review_cands, _ops_cands, _doc_cands, _fin_cands, _hr_cands]


def _hash(state) -> str:
    return hashlib.sha1(json.dumps(state, ensure_ascii=False, default=str).encode()).hexdigest()[:16]


def detect(con, now: dt.datetime, R: dict | None = None) -> list[dict]:
    R = R or rules(con)
    O = Org(con)
    out = []
    for fn in DETECTORS:
        area = {"_task_cands": "ijro"}.get(fn.__name__)
        if area and not MODS.on("tasks"): continue
        try:
            out += fn(con, now, R, O)
        except Exception as e:          # bitta manba xatosi butun sahifani yiqitmasin
            print(f"nazorat.{fn.__name__}:", repr(e))
    return out


# =============================================================================================
# Skan: nomzodlar → nz_items (idempotent), eskalatsiya va bildirishnomalar
# =============================================================================================
def _note(con, uid, title, sub, link, level="warn", kind="nazorat", key=None, ts=None):
    if not uid: return
    con.execute("INSERT INTO nz_notes(user_id,ts,kind,level,title,sub,link,item_key) VALUES(?,?,?,?,?,?,?,?)",
                (uid, ts or _iso(_now()), kind, level, title[:300], (sub or "")[:300], json.dumps(link or {}), key))


FRESH_S = 60              # ko'rinishlar (overview / item / amal) shu soniyagacha oxirgi skan natijasidan foydalanadi
_CACHE: dict = {}         # {"t": monotonic, "items": [...], "dv": PRAGMA data_version}
_cache_lock = threading.Lock()


def _data_version(con) -> int | None:
    try: return con.execute("PRAGMA data_version").fetchone()[0]
    except Exception: return None


def invalidate():
    """Shu jarayondagi yozuvdan keyin (qoidalar, amallar) — keyingi ko'rinish qayta hisoblaydi."""
    with _cache_lock: _CACHE.clear()


def latest() -> list[dict]:
    """Oxirgi skan natijasi, agar yangi bo'lsa (< FRESH_S soniya va boshqa ulanish bazaga yozmagan — PRAGMA data_version); aks holda
    YOZMAYDIGAN hisob (scan(write=False)). nz_items va bildirishnomalar — fon skaneri (10 daqiqa) va amaldan keyingi bitta skanda yoziladi.
    Shu jarayon ichidagi boshqa bo'limlar o'zgarishlari ko'pi bilan FRESH_S soniyada ko'rinadi."""
    import time as _t
    with _cache_lock:
        c = dict(_CACHE)
    if c and _t.monotonic() - c["t"] < FRESH_S and c["dv"] == _data_version(_con):
        return c["items"]
    return scan(_con, write=False)


def scan(con=None, now: dt.datetime | None = None, R: dict | None = None, write: bool = True) -> list[dict]:
    """Istisnolarni qayta hisoblash va nz_items bilan solishtirish. Idempotent: bir xil holatda qayta chaqirilsa hech narsa o'zgarmaydi
    (yangi bildirishnoma faqat eskalatsiya bosqichi oshganda). Natija — ochiq istisnolar (bosqichi, zanjiri bilan).
    Aniqlash (detect — og'ir o'qish) qulfdan tashqarida; nz_items bilan solishtirish va yozish — qulf ostida. write=False — hech narsa
    yozilmaydi (faqat ko'rish uchun: yangi istisnolar «hozir paydo bo'lgan» deb hisoblanadi, bildirishnoma yo'q)."""
    import time as _t
    con = con or _con
    real_now = now is None
    now = (now or _now()).replace(microsecond=0)
    R = R or rules(con)
    cands = detect(con, now, R)
    if write:
        with _lock:
            res = _apply(con, now, R, cands, True)
    else:
        res = _apply(con, now, R, cands, False)
    if real_now and con is _con and _con is not None:
        with _cache_lock:
            _CACHE.clear(); _CACHE.update(t=_t.monotonic(), items=res, dv=_data_version(con))
    return res


def _open_row(con, x: dict, ts: str, first_seen: str | None = None):
    """Yangi yoki qayta ochilgan istisno qatori (nz_items) — ochiq holatga, eskalatsiya/ustidan yozishlar tozalanadi."""
    since = x["since"] if isinstance(x.get("since"), str) else (_iso(x["since"]) if x.get("since") else ts)
    con.execute("""INSERT INTO nz_items(key,area,kind,title,first_seen,last_seen,status,since,notified_level,task_id)
                   VALUES(?,?,?,?,?,?,'open',?,-1,?) ON CONFLICT(key) DO UPDATE SET status='open', closed_at=NULL, first_seen=excluded.first_seen,
                   last_seen=excluded.last_seen, since=excluded.since, reset_at=NULL, snooze_until=NULL, notified_level=-1, ov_user=NULL, ov_unit=NULL""",
                (x["key"], x["area"], x["kind"], x["title"], first_seen or ts, ts, since, x.get("task_id")))


def _ensure_row(it: dict):
    """Amal (qulf ostida): istisno faqat YOZMAYDIGAN hisobda ko'ringan bo'lsa (qatori yo'q yoki yopilgan) — qator ochiladi, amal unga yoziladi;
    amaldan keyingi bitta skan qolganini (bosqich, bildirishnoma) yozadi."""
    o = db.one(_con, "SELECT status FROM nz_items WHERE key=?", (it["key"],))
    if o and o["status"] == "open": return
    _open_row(_con, it, _iso(_now()), it.get("first_seen"))


def _apply(con, now: dt.datetime, R: dict, cands: list, write: bool) -> list[dict]:
    O = Org(con)
    old = {r["key"]: r for r in db.rows(con, "SELECT * FROM nz_items")}
    ts = _iso(now)
    seen, res = set(), []
    for x in cands:
        k = x["key"]; seen.add(k)
        o = old.get(k)
        reopened = o is not None and o["status"] != "open"
        if (o is None or reopened) and not write:
            o = {"key": k, "status": "open", "first_seen": ts, "since": _iso(x["since"]) if x["since"] else ts, "reset_at": None, "snooze_until": None,
                 "notified_level": -1, "task_id": x.get("task_id"), "ov_user": None, "ov_unit": None}
        elif o is None or reopened:
            _open_row(con, x, ts)
            o = db.one(con, "SELECT * FROM nz_items WHERE key=?", (k,))
        since = x["since"] or _dt(o["first_seen"]) or now
        if o.get("reset_at") and (_dt(o["reset_at"]) or since) > since: since = _dt(o["reset_at"])
        owner, unit = (o.get("ov_user") or x["owner"]), (o.get("ov_unit") or x["unit"])
        if x["kind"] == "topshiriq": owner, unit = x["owner"], x["unit"]        # topshiriq — egasi topshiriqning o'zidan
        ch = O.chain(owner, unit)
        st = stage_of(since, now, R, head_is_rektor=ch[1] == O.rektor)
        sn = _dt(o.get("snooze_until"))
        snoozed = bool(sn and sn > now)
        h = _hash(x["state"])
        data = {k2: x.get(k2) for k2 in ("why", "src", "deadline", "link", "aggregate")}
        if not write:
            res.append({**x, "since": since, "stage": st, "chain": ch, "unit": unit, "hash": h, "snoozed": snoozed, "snooze_until": o.get("snooze_until"),
                        "task_id": o.get("task_id") or x.get("task_id"), "first_seen": o["first_seen"]})
            continue
        con.execute("""UPDATE nz_items SET area=?, kind=?, title=?, last_seen=?, since=COALESCE(?, since), owner_user=?, owner_unit=?, state_hash=?, stage=?,
                       task_id=COALESCE(task_id, ?), data=? WHERE key=?""",
                    (x["area"], x["kind"], x["title"], ts, _iso(x["since"]) if x["since"] else None, ch[0], unit, h, st,
                     x.get("task_id"), json.dumps(data, ensure_ascii=False, default=str), k))
        # eskalatsiya bildirishnomalari: har bosqichga birinchi marta yetganda — o'sha bosqich egasiga (kutishda bo'lsa — yo'q)
        nl = o.get("notified_level") if o.get("notified_level") is not None else -1
        if not snoozed and st > nl:
            for lv in range(nl + 1, st + 1):
                if lv == 1 and ch[1] == O.rektor: continue
                who = ch[lv]
                if not who: continue
                msg = {0: "Sizga tegishli istisno", 1: "Xodimingiz muddatni o'tkazdi", 2: "Rektor nazoratida"}[lv]
                _note(con, who, f"{msg}: {x['title']}", x["why"], {"view": "nazorat", "item": k}, "bad" if lv else "warn", key=k, ts=ts)
            con.execute("UPDATE nz_items SET notified_level=? WHERE key=?", (st, k))
        res.append({**x, "since": since, "stage": st, "chain": ch, "unit": unit, "hash": h, "snoozed": snoozed, "snooze_until": o.get("snooze_until"),
                    "task_id": o.get("task_id") or x.get("task_id"), "first_seen": o["first_seen"]})
    if write:
        for k, o in old.items():
            if o["status"] == "open" and k not in seen:
                con.execute("UPDATE nz_items SET status='closed', closed_at=? WHERE key=?", (ts, k))
        con.commit()
    return res


async def poller():
    """Fon: har 10 daqiqada skan (eskalatsiya) va dushanba 08:00 dan keyin — shu haftaning hisoboti (bir marta)."""
    import asyncio
    await asyncio.sleep(20)
    while True:
        try:
            if MODS.on("nazorat"):
                await asyncio.to_thread(scan, _con)
                await asyncio.to_thread(weekly_due, _con)
        except Exception as e:
            print("nazorat poller:", repr(e))
        await asyncio.sleep(600)


# =============================================================================================
# Ko'rinish (rektor / prorektor ko'lami)
# =============================================================================================
def _guard(c: Ctx, action: str, roles=ROLES, detail: str = ""):
    ok = c.role.key in roles and c.channel == "web"
    if not ok:
        rbac.audit(_con, c, f"nazorat: {action}", RES, False, detail)
        raise AccessDenied(f"⛔ Nazorat markazi: {action} — faqat rektor va prorektorlar uchun. So'rov audit jurnaliga yozildi.")


def _curated(c: Ctx) -> set:
    if c.role.key not in PRO: return set()
    return {r["key"] for r in db.rows(_con, "SELECT key FROM org_units WHERE curator=?", (c.role.key,))} | {c.role.key}


def _visible(c: Ctx, it: dict, cur: set) -> bool:
    if c.role.key == LEAD: return True
    return it["unit"] in cur or c.user["id"] in it["chain"][:2]


def _red(c: Ctx, it: dict, cur: set) -> bool:
    """Shu foydalanuvchiga YETIB KELGAN istisno: rektor — 2-bosqich; prorektor — zanjirdagi o'rni yoki kuratorlik (rahbar darajasi)."""
    if c.role.key == LEAD: return it["stage"] >= 2
    uid = c.user["id"]
    if uid == it["chain"][0]: return True
    if uid == it["chain"][1] or it["unit"] in cur: return it["stage"] >= 1
    return False


def _view_item(c: Ctx, it: dict, O: Org, now: dt.datetime) -> dict:
    owner = O.person(it["chain"][0])
    head = O.person(it["chain"][1])
    unit_name = O.unit_name(it["unit"])
    age = max(0, int(_days(it["since"], now))) if it.get("since") else 0
    return {"key": it["key"], "area": it["area"], "kind": it["kind"], "title": it["title"], "why": it["why"], "src": it.get("src"),
            "since": _iso(it["since"]) if it.get("since") else None, "age_days": age, "deadline": it.get("deadline"),
            "owner": owner or {"id": None, "name": "Rahbar tayinlanmagan", "position": unit_name}, "unit": it["unit"], "unit_name": unit_name,
            "head": head, "stage": it["stage"], "stage_label": STAGE_T[it["stage"]], "link": it.get("link"), "task_id": it.get("task_id"),
            "aggregate": bool(it.get("aggregate")), "snooze_until": it.get("snooze_until") if it.get("snoozed") else None}


def overview(c: Ctx, now: dt.datetime | None = None) -> dict:
    """Faqat ko'rish: oxirgi (yangi) skan natijasi yoki YOZMAYDIGAN hisob — nz_items/bildirishnomalar fon skaneri va amallarda yoziladi."""
    items = scan(_con, now, write=False) if now else latest()
    now = now or _now()
    O = Org(_con)
    cur = _curated(c)
    acks = {r["key"]: r["hash"] for r in db.rows(_con, "SELECT key, hash FROM nz_acks WHERE user_id=?", (c.user["id"],))}
    areas = []
    tot = {"red": 0, "lower": 0, "acked": 0, "snoozed": 0}
    for key, title, icon in AREAS:
        if not any(MODS.on(m) for m in AREA_MODS[key]): continue
        red, lower = [], []
        for it in items:
            if it["area"] != key or not _visible(c, it, cur): continue
            if it["snoozed"]: tot["snoozed"] += 1; continue
            if acks.get(it["key"]) == it["hash"]: tot["acked"] += 1; continue
            (red if _red(c, it, cur) else lower).append(_view_item(c, it, O, now))
        red.sort(key=lambda x: (x["since"] or "", x["key"])); lower.sort(key=lambda x: (-x["stage"], x["since"] or "", x["key"]))
        tot["red"] += len(red); tot["lower"] += len(lower)
        areas.append({"key": key, "title": title, "icon": icon, "status": "red" if red else "amber" if lower else "green", "items": red, "lower": lower})
    return {"role": c.role.key, "scope": "Butun institut" if c.role.key == LEAD else f"{c.role.title}: vakolatidagi bo'limlar",
            "areas": areas, "counts": tot, "now": _iso(now), "rules": rules(), "can_rules": c.role.key == LEAD,
            "sign_count": len(sign_queue(c)["items"])}


# =============================================================================================
# 4 amal
# =============================================================================================
def _item(c: Ctx, key: str) -> tuple[dict, Org]:
    """Oxirgi (yangi) skan natijasidan; amal nz_items qatorini _ensure_row bilan ta'minlaydi — amal uchun to'liq skan faqat bitta (amaldan keyin)."""
    items = {x["key"]: x for x in latest()}
    it = items.get(key)
    if not it: raise HTTPException(404, "Bu istisno endi yo'q (holat o'zgargan yoki yopilgan)")
    if not _visible(c, it, _curated(c)):
        rbac.audit(_con, c, "nazorat: amal", RES, False, key)
        raise AccessDenied("⛔ Bu istisno sizning vakolatingizda emas. So'rov audit jurnaliga yozildi.")
    return it, Org(_con)


def _nzlog(c: Ctx, key, action, detail=""):
    _con.execute("INSERT INTO nz_log(ts,user_id,user_name,key,action,detail) VALUES(?,?,?,?,?,?)",
                 (_iso(_now()), c.user["id"], c.user["full_name"], key, action, (detail or "")[:500]))


def _task_log(tid, c: Ctx, action, detail=""):
    _con.execute("INSERT INTO task_log(task_id,ts,user_id,user_name,action,detail) VALUES(?,?,?,?,?,?)",
                 (tid, _iso(_now()), c.user["id"], c.user["full_name"], action, (detail or "")[:500]))


def _task_msg(tid, c: Ctx, text):
    _con.execute("INSERT INTO task_msgs(task_id,ts,user_id,user_name,role,text) VALUES(?,?,?,?,?,?)",
                 (tid, _iso(_now()), c.user["id"], c.user["full_name"], c.title, text[:2000]))


def _my_unit(c: Ctx) -> str:
    return "rektorat" if c.role.key == LEAD else c.role.key


def ensure_task(c: Ctx, it: dict, due: str | None = None) -> int:
    """Istisnoga bog'langan topshiriq: topshiriq istisnosi — o'zi; agregat — «Nazorat» topshirig'i (bir marta yaratiladi, src='nz:<kalit>')."""
    from . import directives as DIR, decisions as DEC
    tid = it.get("task_id")
    if tid and db.one(_con, "SELECT 1 x FROM tasks WHERE id=?", (tid,)):
        if it["kind"] != "topshiriq":
            t = db.one(_con, "SELECT status FROM tasks WHERE id=?", (tid,))
            if t and t["status"] != "bajarildi": return tid
        else:
            return tid
    due = due or (clock.today() + dt.timedelta(days=3)).isoformat()
    unit = DEC.task_key(it["unit"]) or "rektorat"
    if unit not in DEC.registry(): unit = DEC.task_key("talabalar")
    body = f"{it['why']}\n\nNazorat markazi: {it.get('src') or AREA_T.get(it['area'], '')}. Muammoni bartaraf eting va natijani yozing."
    tid = DIR.create_linked(_con, c.user["id"], _my_unit(c), unit, f"Nazorat: {it['title']}"[:300], body, due, "muhim",
                            "Muammo bartaraf etilgani haqida qisqa natija", src=f"nz:{it['key']}")
    if it["chain"][0] and it["chain"][0] != O_head(it["unit"]):
        u = db.one(_con, "SELECT full_name FROM users WHERE id=?", (it["chain"][0],))
        _con.execute("UPDATE tasks SET assignee_user=?, assignee=? WHERE id=?", (it["chain"][0], _short(u["full_name"]) if u else "", tid))
    _con.execute("UPDATE nz_items SET task_id=? WHERE key=?", (tid, it["key"]))
    return tid


def _task_link(tid) -> dict:
    from . import decisions as DEC
    t = db.one(_con, "SELECT id, origin, meeting_id FROM tasks WHERE id=?", (tid,)) or {"id": tid, "origin": "topshiriq", "meeting_id": None}
    return {"view": "tasks", "directive": tid} if t.get("origin") == "topshiriq" or not t.get("meeting_id") else DEC.task_link(t)


def O_head(unit):
    r = db.one(_con, "SELECT head_user FROM org_units WHERE key=?", (unit,))
    return r["head_user"] if r else None


class _tx:
    """Amal tranzaksiyasi (qulf ostida): istisno bo'lsa — rollback (yarim yozuv umumiy ulanishda qolib, keyin boshqa commit bilan
    saqlanib ketmasin), muvaffaqiyatli bo'lsa — commit."""
    def __enter__(self):
        _lock.acquire(); return self
    def __exit__(self, et, ev, tb):
        try:
            if et is None: _con.commit()
            else: _con.rollback()
        finally:
            _lock.release()
        return False


def _after_action():
    """Amaldan keyin BITTA to'liq skan (yopilish, yangi egasiga bildirishnoma) — natija keshga tushadi, keyingi ko'rinish qayta hisoblamaydi."""
    invalidate()
    try: scan(_con)
    except Exception as e: print("nazorat.after_action:", repr(e))


def act_remind(c: Ctx, key: str, note: str = "") -> dict:
    _guard(c, "eslatish", detail=key)
    it, O = _item(c, key)
    owner = it["chain"][0] or it["chain"][1]
    with _tx():
        _ensure_row(it)
        tid = ensure_task(c, it)
        text = f"Eslatma (Nazorat markazi): «{it['title']}». {it['why']}." + (f" {note.strip()}" if note.strip() else "")
        _task_msg(tid, c, text)
        _task_log(tid, c, "eslatma yuborildi", (O.person(owner) or {}).get("name", "") + (f" · {note.strip()}" if note.strip() else ""))
        _note(_con, owner, f"Eslatma: {it['title']}", (note.strip() or it["why"]), _task_link(tid), "warn", key=key)
        _nzlog(c, key, "eslatish", note)
    rbac.audit(_con, c, "nazorat: eslatish", RES, True, f"{key} → #{tid} · {(O.person(owner) or {}).get('name', '—')}")
    _after_action()
    return {"ok": True, "task_id": tid, "to": O.person(owner)}


def act_deadline(c: Ctx, key: str, due: str, note: str = "") -> dict:
    _guard(c, "muddat berish", detail=key)
    try:
        d = dt.date.fromisoformat((due or "")[:10])
    except ValueError:
        raise HTTPException(400, "Yangi muddatni YYYY-MM-DD ko'rinishida kiriting")
    if d <= clock.today(): raise HTTPException(400, "Yangi muddat kelajakdagi sana bo'lsin")
    if not (note or "").strip(): raise HTTPException(400, "Izoh yozing (nega muddat berilmoqda)")
    it, O = _item(c, key)
    due_at = f"{d.isoformat()}T18:00"
    with _tx():
        _ensure_row(it)
        tid = ensure_task(c, it, d.isoformat())
        old = db.one(_con, "SELECT due, due_at FROM tasks WHERE id=?", (tid,)) or {}
        _con.execute("UPDATE tasks SET due=?, due_at=?, updated_at=? WHERE id=?", (d.isoformat(), due_at, _iso(_now()), tid))
        _task_log(tid, c, "muddat o'zgartirildi", f"{_dmy(old.get('due_at') or old.get('due'))} → {_dmy(d.isoformat())} · {note.strip()}")
        _task_msg(tid, c, f"Yangi muddat: {_dmy(d.isoformat())}. {note.strip()}")
        if it["kind"] != "topshiriq":    # agregat istisno — yangi muddatgacha «kutishda» (keyin holat yaxshilanmagan bo'lsa qaytadi)
            _con.execute("UPDATE nz_items SET snooze_until=?, reset_at=?, notified_level=-1 WHERE key=?", (due_at, _iso(_now()), key))
        owner = it["chain"][0] or it["chain"][1]
        _note(_con, owner, f"Yangi muddat {_dmy(d.isoformat())}: {it['title']}", note.strip(), {"view": "nazorat", "item": key}, "warn", key=key)
        _nzlog(c, key, "muddat", f"{d.isoformat()} · {note.strip()}")
    rbac.audit(_con, c, "nazorat: muddat berish", RES, True, f"{key} → #{tid} · {d.isoformat()} · {note.strip()[:120]}")
    _after_action()
    return {"ok": True, "task_id": tid, "due": d.isoformat()}


def reassign_targets(c: Ctx, it: dict, O: Org) -> dict:
    from . import directives as DIR
    T = DIR.targets(c)
    head = O.person(it["chain"][1]) if it["chain"][1] and it["chain"][1] != it["chain"][0] else None
    units = [{"key": k, "name": DIR.DEC.unit_name(k) or k} for k in T["units"]]
    return {"head": head, "units": units}


def act_reassign(c: Ctx, key: str, unit: str | None = None, to_head: bool = False, note: str = "") -> dict:
    """Qayta tayinlash: boshqa bo'limga (vakolat — directives.authorize) yoki egasining rahbariga («yuqoriga ko'tarish»)."""
    from . import directives as DIR, decisions as DEC
    _guard(c, "qayta tayinlash", detail=key)
    it, O = _item(c, key)
    if bool(unit) == bool(to_head): raise HTTPException(400, "Yangi mas'ulni tanlang: bo'lim yoki «rahbariga ko'tarish»")
    # AVVAL tekshiruv (topshiriq yaratilmasdan): rahbar aniqlanmasa yoki bo'lim vakolatdan tashqari bo'lsa — hech narsa yozilmaydi
    # (DIR.authorize rad etganda audit commit qiladi — oldin yaratilgan topshiriq umumiy ulanishda «yetim» bo'lib saqlanib qolardi)
    if to_head:
        new_user = it["chain"][1]
        if not new_user or new_user == it["chain"][0]: raise HTTPException(400, "Egasining rahbari aniqlanmadi")
        u = db.one(_con, "SELECT * FROM users WHERE id=?", (new_user,))
        from . import portal as PT
        new_unit = PT.unit_key(u) if u else it["unit"]
        label = f"{rbac.user_title(u)} {_short(u['full_name'])}".strip() if u else "rahbar"
    else:
        tunit, _ = DIR.authorize(c, "nazorat: qayta tayinlash", unit, None)
        new_unit = DEC.org_key(tunit)
        new_user = O_head(new_unit)
        label = DEC.unit_name(tunit) or tunit
        u = db.one(_con, "SELECT full_name, role FROM users WHERE id=?", (new_user,)) if new_user else None
    with _tx():
        _ensure_row(it)
        tid = ensure_task(c, it)
        if to_head:
            tunit = DEC.task_key(new_unit)
            if tunit not in DEC.registry(): tunit = db.one(_con, "SELECT unit FROM tasks WHERE id=?", (tid,))["unit"]
            _con.execute("UPDATE tasks SET unit=?, assignee_user=?, assignee=?, assignee_role=?, updated_at=? WHERE id=?",
                         (tunit, new_user, _short(u["full_name"]) if u else "", u["role"] if u else None, _iso(_now()), tid))
            action = "rahbariga ko'tarildi"
        else:
            _con.execute("UPDATE tasks SET unit=?, assignee_user=NULL, assignee=?, assignee_role=?, status=CASE WHEN status='jarayonda' THEN 'jarayonda' ELSE 'yangi' END, updated_at=? WHERE id=?",
                         (tunit, _short(u["full_name"]) if u else "", u["role"] if u else DEC._head_role(tunit), _iso(_now()), tid))
            action = "qayta tayinlandi"
        _task_log(tid, c, action, f"{label}" + (f" · {note.strip()}" if note.strip() else ""))
        _con.execute("UPDATE nz_items SET ov_user=?, ov_unit=?, reset_at=?, notified_level=-1 WHERE key=?", (new_user, new_unit, _iso(_now()), key))
        _nzlog(c, key, action, f"{label} · {note.strip()}")
    rbac.audit(_con, c, "nazorat: qayta tayinlash", RES, True, f"{key} → #{tid} · {label}")
    _after_action()     # yangi egasiga darhol bildirishnoma (eskalatsiya soati qaytadan) — amal uchun yagona skan
    return {"ok": True, "task_id": tid, "to": label}


def act_ack(c: Ctx, key: str) -> dict:
    _guard(c, "ko'rdim", detail=key)
    it, _ = _item(c, key)
    with _tx():
        _con.execute("INSERT INTO nz_acks(user_id,key,hash,ts) VALUES(?,?,?,?) ON CONFLICT(user_id,key) DO UPDATE SET hash=excluded.hash, ts=excluded.ts",
                     (c.user["id"], key, it["hash"], _iso(_now())))
        _nzlog(c, key, "ko'rdim")
    rbac.audit(_con, c, "nazorat: ko'rdim", RES, True, key)
    return {"ok": True}


# =============================================================================================
# Imzo navbati
# =============================================================================================
_SOFT = ("chat", "kiruvchi")
def _link_on(link) -> bool:
    v = (link or {}).get("view")
    if not v: return True
    if v == "service": v = {"events": "yoshlar", "requests": "ops"}.get((link or {}).get("tab"), "service")
    return v in _SOFT or MODS.on("tasks" if v == "calendar" else v)


def sign_queue(c: Ctx) -> dict:
    from . import mywork as MW
    d = MW.collect(c)
    items = [it for it in d["items"] if it.get("sign") and _link_on(it.get("link"))]
    oids = [int(it["link"]["order"]) for it in items if (it.get("link") or {}).get("view") == "orders" and it["link"].get("order")]
    od = {}
    if oids:
        od = {r["id"]: r for r in db.rows(_con, f"SELECT id, status, submitted_at, forwarded_at, kind FROM orders WHERE id IN ({','.join(map(str, oids))})")}
    out = []
    now = _now()
    for it in items:
        o = od.get((it.get("link") or {}).get("order"))
        since = (o.get("forwarded_at") or o.get("submitted_at")) if o else None
        acts = {}
        if o:
            if c.role.key == "rektor" and o["status"] in ("yuborilgan", "kelishilgan"): acts = {"approve": "Imzolash", "return": "Qaytarish"}
            elif c.role.key == "prorektor_oquv" and o["status"] == "yuborilgan": acts = {"approve": "Kelishish", "return": "Qaytarish"}
        out.append({"id": it["id"], "kind": "order" if o else it["source"], "ref": o["id"] if o else None, "title": it["title"], "sub": it["sub"],
                    "since": since, "age_days": int(_days(_dt(since), now)) if since and _dt(since) else None, "link": it.get("link"),
                    "actions": acts, "source": it["source"]})
    out.sort(key=lambda x: (x["since"] is None, x["since"] or "", x["id"]))
    return {"items": out, "count": len(out)}


def sign_decide(c: Ctx, request: Request, kind: str, ref: int, decision: str, note: str = "") -> dict:
    _guard(c, "imzo navbati", detail=f"{kind}#{ref}")
    if kind != "order": raise HTTPException(400, "Bu hujjat o'z bo'limida ko'rib chiqiladi — «Ochish» tugmasini bosing")
    from . import orders as ORD
    if c.role.key not in ORD.SIGN + ORD.FORWARD:
        rbac.audit(_con, c, "nazorat: imzo navbati", RES, False, f"buyruq #{ref}")
        raise AccessDenied("⛔ Buyruqni rektor imzolaydi, o'quv ishlari prorektori kelishadi. So'rov audit jurnaliga yozildi.")
    o = ORD._order(c, ref)
    if decision == "approve":
        if c.role.key in ORD.SIGN:
            from . import service as SV
            res = ORD.sign(o, c, SV.public_base(request))
            label = f"imzolandi ({res.get('reg_no')})"
        else:
            ORD._transition(c, o, ("yuborilgan",), "kelishilgan", "prorektor kelishdi", "Nazorat markazi · imzo navbati",
                            forwarded_by=c.user["id"], forwarded_at=ORD._now()); res = {"ok": True}
            label = "kelishildi"
    elif decision == "return":
        n = (note or "").strip()[:500]
        if len(n) < 3: raise HTTPException(400, "Qaytarish sababini yozing")
        frm = ("yuborilgan", "kelishilgan") if c.role.key in ORD.SIGN else ("yuborilgan",)
        ORD._transition(c, o, frm, "loyiha", "qaytarildi", n, returned_note=n, forwarded_by=None, forwarded_at=None)
        res, label = {"ok": True}, "izoh bilan qaytarildi"
    else:
        raise HTTPException(400, "Noto'g'ri qaror")
    from . import mywork as MW
    MW.invalidate(c.user["id"])
    rbac.audit(_con, c, "nazorat: imzo navbati", RES, True, f"buyruq #{ref} {label}")
    return {**res, "ok": True, "label": label}


# =============================================================================================
# Haftalik hisobot
# =============================================================================================
BRIEF_SCHEMA = {"type": "object", "additionalProperties": False, "required": ["lines", "decisions"],
                "properties": {"lines": {"type": "array", "items": {"type": "string"}},
                               "decisions": {"type": "array", "items": {"type": "string"}}}}
BRIEF_SYSTEM = ("Siz oliy ta'lim muassasasi rektori uchun haftalik nazorat hisobotini o'zbek tilida (lotin) yozasiz. Faqat berilgan jamlangan "
                "sonlardan foydalaning, yangi fakt o'ylab topmang. 'lines' — 5–8 ta qisqa qator: nima yaxshilandi, nima to'xtab qoldi. "
                "'decisions' — rektor qabul qilishi kerak bo'lgan aynan 3 ta qaror (qisqa, buyruq maylida emas).")


def week_key(d: dt.date) -> str:
    y, w, _ = d.isocalendar()
    return f"{y}-W{w:02d}"


def brief_stats(con, now: dt.datetime) -> dict:
    """FAQAT jamlangan sonlar (AI'ga shu yuboriladi): sohalar bo'yicha ochiq / yangi / yopilgan / rektorgacha yetgan, imzo navbati."""
    items = scan(con, now)
    wk = _iso(now - dt.timedelta(days=7))
    closed = db.rows(con, "SELECT area, COUNT(*) n FROM nz_items WHERE status='closed' AND closed_at>=? GROUP BY area", (wk,))
    closed = {r["area"]: r["n"] for r in closed}
    areas = {}
    for k, t, _ in AREAS:
        if not any(MODS.on(m) for m in AREA_MODS[k]): continue
        xs = [i for i in items if i["area"] == k]
        areas[k] = {"nomi": t, "ochiq": len(xs), "rektorda": sum(1 for i in xs if i["stage"] >= 2), "rahbarda": sum(1 for i in xs if i["stage"] == 1),
                    "yangi_hafta": sum(1 for i in xs if (i.get("first_seen") or "") >= wk), "yopildi_hafta": closed.get(k, 0),
                    "eng_eski_kun": max((int(_days(i["since"], now)) for i in xs if i.get("since")), default=0)}
    prev = db.one(con, "SELECT stats FROM nz_briefs WHERE week<? ORDER BY week DESC LIMIT 1", (week_key(now.date()),))
    prev_open = {}
    if prev:
        try: prev_open = {k: v.get("ochiq", 0) for k, v in json.loads(prev["stats"]).get("sohalar", {}).items()}
        except Exception: prev_open = {}
    for k, v in areas.items():
        v["otgan_hafta_ochiq"] = prev_open.get(k)
    sign = []
    rid = (db.one(con, "SELECT id FROM users WHERE role='rektor' AND COALESCE(active,1)=1 ORDER BY id") or {}).get("id")
    if rid:
        try:
            sq = sign_queue(rbac.ctx_for(con, rid))["items"]
            sign = [i["age_days"] for i in sq]
        except Exception as e:
            print("nazorat.brief.sign:", repr(e))
    return {"hafta": week_key(now.date()), "sohalar": areas, "imzo_navbati": len(sign),
            "imzo_eng_eski_kun": max([a for a in sign if a is not None], default=0)}


def _age_t(n) -> str:
    return "bugun kelgan" if not n else f"{n} kun kutmoqda"


def fallback_text(s: dict) -> tuple[list[str], list[str]]:
    """Qoidaviy (AI'siz) matn — deterministik."""
    A = s["sohalar"]
    lines = []
    tot_open = sum(v["ochiq"] for v in A.values()); tot_closed = sum(v["yopildi_hafta"] for v in A.values())
    tot_new = sum(v["yangi_hafta"] for v in A.values()); tot_r = sum(v["rektorda"] for v in A.values())
    lines.append(f"Hafta {s['hafta']}: {tot_open} ta ochiq istisno, shundan {tot_r} tasi rektor darajasiga yetgan.")
    better = [(v["nomi"], v["yopildi_hafta"]) for v in A.values() if v["yopildi_hafta"]]
    lines.append("Yaxshilandi: " + ", ".join(f"{n} — {k} ta yopildi" for n, k in better) + "." if better else "Yaxshilandi: bu hafta yopilgan istisno yo'q.")
    down = [v["nomi"] for v in A.values() if v.get("otgan_hafta_ochiq") is not None and v["ochiq"] < v["otgan_hafta_ochiq"]]
    if down: lines.append("O'tgan haftaga nisbatan kamaydi: " + ", ".join(down) + ".")
    stuck = sorted(((v["eng_eski_kun"], v["nomi"], v["rektorda"]) for v in A.values() if v["rektorda"]), reverse=True)
    lines.append("To'xtab qoldi: " + "; ".join(f"{n} — {r} ta rektorda, eng eskisi {d} kun" for d, n, r in stuck[:3]) + "." if stuck
                 else "To'xtab qolgan (rektor darajasidagi) istisno yo'q.")
    lines.append(f"Bu hafta yangi istisnolar: {tot_new} ta; yopilganlari: {tot_closed} ta.")
    if s["imzo_navbati"]:
        lines.append(f"Imzo navbatida {s['imzo_navbati']} ta hujjat, eng eskisi {_age_t(s['imzo_eng_eski_kun'])}.")
    green = [v["nomi"] for v in A.values() if not v["ochiq"]]
    if green: lines.append("Hammasi joyida: " + ", ".join(green) + ".")
    while len(lines) < 5: lines.append("Qolgan sohalarda o'zgarish yo'q.")
    lines = lines[:8]
    dec = []
    if s["imzo_navbati"]: dec.append(f"Imzo navbatidagi {s['imzo_navbati']} ta hujjat bo'yicha qaror (eng eskisi {_age_t(s['imzo_eng_eski_kun'])}).")
    for d, n, r in stuck:
        if len(dec) >= 3: break
        dec.append(f"{n}: rektor darajasidagi {r} ta istisno — mas'ulni almashtirish yoki yangi muddat berish.")
    for v in sorted(A.values(), key=lambda v: -v["rahbarda"]):
        if len(dec) >= 3: break
        if v["rahbarda"]: dec.append(f"{v['nomi']}: rahbarlar darajasidagi {v['rahbarda']} ta istisno bo'yicha prorektorlardan hisobot so'rash.")
    defaults = ["Eskalatsiya qoidalarini (kunlar) tasdiqlash yoki o'zgartirish.", "Keyingi hafta uchun ustuvor sohani belgilash.",
                "Haftalik majlis kun tartibiga eng eski istisnolarni kiritish."]
    for x in defaults:
        if len(dec) >= 3: break
        dec.append(x)
    return lines, dec[:3]


def _ai_default(stats: dict) -> tuple[list, list]:
    from . import claude_client as CC
    model = os.getenv("ISFT_CORE_NZ_MODEL", "claude-opus-5-5").strip() or "claude-opus-5-5"
    data, _ = CC.call_json(model=model, system=BRIEF_SYSTEM, content=[{"type": "text", "text": json.dumps(stats, ensure_ascii=False)}],
                           schema=BRIEF_SCHEMA, max_tokens=2000, effort="low", timeout=90, what="haftalik hisobot")
    return data.get("lines") or [], data.get("decisions") or []


def _tg_default(chat_id, text) -> tuple[bool, str]:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if not token: return False, "TELEGRAM_BOT_TOKEN o'rnatilmagan — Telegram'ga yuborilmadi"
    body = urllib.parse.urlencode({"chat_id": chat_id, "text": text}).encode()
    try:
        with urllib.request.urlopen(f"https://api.telegram.org/bot{token}/sendMessage", body, timeout=15) as r:
            return r.status == 200, "yuborildi"
    except Exception as e:
        return False, f"Telegram xatosi: {type(e).__name__}"


AI_FN = _ai_default      # testlar almashtiradi
TG_FN = _tg_default


def _clean_lines(xs, lo, hi) -> list[str]:
    out = [" ".join(str(x).split())[:240] for x in (xs or []) if str(x).strip()]
    return out[:hi] if len(out) >= lo else []


_BRIEF_BUSY: set = set()       # tayyorlanayotgan haftalar — bir vaqtda ikkinchi (takroriy) tayyorlash yo'q
_brief_flag = threading.Lock()


def make_brief(con=None, now: dt.datetime | None = None, force: bool = False, ai_fn=None, tg_fn=None, use_ai: bool | None = None) -> dict | None:
    """Shu haftaning hisoboti (bir marta; force — qayta). AI faqat jamlangan sonlarni oladi; xato/kalitsiz — qoidaviy matn.
    Ma'lumot yig'ish va yozish — qisqa qulflar ostida; Claude API va Telegram so'rovlari — qulfdan TASHQARIDA. Shu hafta hisoboti boshqa
    oqimda tayyorlanayotgan bo'lsa — None (takroriy AI chaqiruvi / Telegram xabari yo'q)."""
    from . import claude_client as CC
    con = con or _con
    now = now or _now()
    wk = week_key(now.date())
    with _brief_flag:
        if wk in _BRIEF_BUSY: return None
        have = db.one(con, "SELECT * FROM nz_briefs WHERE week=?", (wk,))
        if have and not force: return _brief_row(have)
        _BRIEF_BUSY.add(wk)
    try:
        stats = brief_stats(con, now)                 # skan o'zi yozish qismini qulf ostida bajaradi
        lines, dec = fallback_text(stats)
        source = "qoida"
        if use_ai is None: use_ai = CC.has_key() or ai_fn is not None
        if use_ai:                                    # tarmoq — qulfsiz
            try:
                al, ad = (ai_fn or AI_FN)(stats)
                al, ad = _clean_lines(al, 5, 8), _clean_lines(ad, 3, 3)
                if al and ad: lines, dec, source = al, ad, "ai"
            except Exception as e:
                print("nazorat.brief.ai:", type(e).__name__, str(e)[:120])
        ts = _iso(now)
        text = f"📊 Haftalik nazorat hisoboti ({wk})\n\n" + "\n".join(f"• {x}" for x in lines) + "\n\nKerakli qarorlar:\n" + "\n".join(f"{i}. {x}" for i, x in enumerate(dec, 1))
        with _lock:
            con.execute("""INSERT INTO nz_briefs(week,created_at,source,lines,decisions,stats,tg) VALUES(?,?,?,?,?,?,NULL)
                           ON CONFLICT(week) DO UPDATE SET created_at=excluded.created_at, source=excluded.source, lines=excluded.lines,
                           decisions=excluded.decisions, stats=excluded.stats""",
                        (wk, ts, source, json.dumps(lines, ensure_ascii=False), json.dumps(dec, ensure_ascii=False), json.dumps(stats, ensure_ascii=False)))
            # yetkazish: ilova (bildirishnoma) va Telegram (rektor botga ulangan bo'lsa)
            targets = []
            for u in db.rows(con, "SELECT * FROM users WHERE role='rektor' AND COALESCE(active,1)=1 ORDER BY id"):
                _note(con, u["id"], f"Haftalik hisobot tayyor ({wk})", lines[0] if lines else "", {"view": "haftalik"}, "info", "hisobot", ts=ts)
                if u.get("telegram_id") and u.get("tg_pin_fp") == rbac.pin_fp(u.get("pin")): targets.append(u)
            con.commit()
        tg, sent = [], []
        for u in targets:                             # Telegram — qulfsiz
            ok, msg = (tg_fn or TG_FN)(u["telegram_id"], text)
            tg.append({"user": u["id"], "ok": bool(ok), "note": msg}); sent.append((u, bool(ok), msg))
        with _lock:
            for u, ok, msg in sent:
                rbac.audit(con, rbac.Ctx(u, rbac.ROLES["rektor"], "telegram"), "haftalik nazorat hisoboti Telegram'ga", RES, ok, msg)
            con.execute("UPDATE nz_briefs SET tg=? WHERE week=?", (json.dumps(tg, ensure_ascii=False), wk))
            con.commit()
            return _brief_row(db.one(con, "SELECT * FROM nz_briefs WHERE week=?", (wk,)))
    finally:
        with _brief_flag: _BRIEF_BUSY.discard(wk)


def _brief_row(r) -> dict:
    j = lambda v, d: json.loads(v) if v else d
    return {"week": r["week"], "created_at": r["created_at"], "source": r["source"], "lines": j(r["lines"], []), "decisions": j(r["decisions"], []),
            "stats": j(r["stats"], {}), "telegram": j(r["tg"], [])}


def brief_due(now: dt.datetime) -> bool:
    """Shu haftaning hisoboti vaqti keldimi: dushanba 08:00 dan keyin (server o'sha payt o'chiq bo'lsa — keyingi skanda)."""
    return now.weekday() > 0 or now.time() >= dt.time(8, 0)


def weekly_due(con=None, now: dt.datetime | None = None):
    con = con or _con
    now = now or _now()
    if brief_due(now) and not db.one(con, "SELECT 1 x FROM nz_briefs WHERE week=?", (week_key(now.date()),)):
        return make_brief(con, now)
    return None


# =============================================================================================
# Bildirishnomalar (app/extras.py notifications) va menyu
# =============================================================================================
def notif_items(c: Ctx) -> list[dict]:
    if _con is None or not MODS.on("nazorat"): return []
    since = _iso(_now() - dt.timedelta(days=14))
    out = []
    for r in db.rows(_con, "SELECT * FROM nz_notes WHERE user_id=? AND ts>=? ORDER BY id DESC LIMIT 15", (c.user["id"], since)):
        out.append({"id": f"nz{r['id']}", "kind": r["kind"] or "nazorat", "icon": "alert" if r["level"] == "bad" else "flag", "level": r["level"] or "warn",
                    "title": r["title"], "sub": r["sub"] or "", "ts": r["ts"], "link": json.loads(r["link"] or "{}") or {"view": "nazorat"}})
    return out


def menu(c: Ctx) -> dict:
    """Rektor menyusi (≤ 5 band): Nazorat markazi, Imzo navbati, Haftalik hisobot, suhbat («chat» yoqilgan bo'lsa), Barcha bo'limlar.
    Prorektor — to'liq menyusi saqlanadi, boshiga Nazorat markazi va Imzo navbati qo'shiladi. Bo'lim o'chiq bo'lsa — eski menyu."""
    if not MODS.on("nazorat") or c.role.key not in ROLES: return {"lean": False, "items": []}
    if c.role.key == LEAD:
        items = ["nazorat", "imzo", "haftalik"] + (["chat"] if MODS.on("chat") else []) + ["barcha"]
        return {"lean": True, "items": items, "home": "nazorat"}
    return {"lean": False, "items": ["nazorat", "imzo"], "home": None}


# =============================================================================================
# HTTP
# =============================================================================================
def C(request: Request) -> Ctx: return _ctx(request)

def _mod_guard():
    if not MODS.on("nazorat"): raise HTTPException(404, "«Nazorat markazi» bo'limi o'chirilgan")

@router.get(P + "/meta")
def api_meta(request: Request):
    c = C(request)
    return {"menu": menu(c), "role": c.role.key, "can": c.role.key in ROLES and MODS.on("nazorat"), "can_rules": c.role.key == LEAD,
            "can_brief": c.role.key == LEAD}

@router.get(P)
def api_overview(request: Request):
    _mod_guard()
    c = C(request); _guard(c, "ko'rish")
    d = overview(c)
    rbac.audit(_con, c, "nazorat: ko'rish", RES, True, f"{d['counts']['red']} ta qizil")
    return d

@router.get(P + "/item")
def api_item(request: Request, key: str):
    _mod_guard()
    c = C(request); _guard(c, "istisno", detail=key)
    it, O = _item(c, key)
    log = db.rows(_con, "SELECT ts, user_name, action, detail FROM nz_log WHERE key=? ORDER BY id DESC LIMIT 20", (key,))
    for x in log: x["user_name"] = _short(x["user_name"]) or x["user_name"]
    return {"item": _view_item(c, it, O, _now()), "targets": reassign_targets(c, it, O), "log": log}

class ActIn(BaseModel):
    key: str = Field(..., min_length=3, max_length=80)
    action: str
    note: str = Field("", max_length=1000)
    due: str | None = None
    unit: str | None = None
    to_head: bool = False

@router.post(P + "/act")
def api_act(body: ActIn, request: Request):
    _mod_guard()
    c = C(request)
    if body.action == "eslatish": return act_remind(c, body.key, body.note)
    if body.action == "muddat": return act_deadline(c, body.key, body.due or "", body.note)
    if body.action == "tayinlash": return act_reassign(c, body.key, body.unit, body.to_head, body.note)
    if body.action == "korildi": return act_ack(c, body.key)
    raise HTTPException(400, "Noma'lum amal")

@router.get(P + "/rules")
def api_rules(request: Request):
    _mod_guard()
    c = C(request); _guard(c, "qoidalar")
    return {"rules": rules_view(), "can_edit": c.role.key == LEAD}

@router.post(P + "/rules")
def api_rules_set(body: dict, request: Request):
    _mod_guard()
    c = C(request); _guard(c, "qoidalarni o'zgartirish", roles=(LEAD,))
    vals = body.get("rules") if isinstance(body.get("rules"), dict) else body
    if not isinstance(vals, dict): raise HTTPException(400, "Qoidalar lug'ati kerak")
    new = {}
    for k, v in vals.items():                       # 1) AVVAL hammasi tekshiriladi — bittasi xato bo'lsa hech biri yozilmaydi
        if k not in RULES: raise HTTPException(400, f"Noma'lum qoida: {k}")
        d, lo, hi, t = RULES[k]
        try: v = int(v)
        except (TypeError, ValueError): raise HTTPException(400, f"«{t}» — butun son bo'lsin")
        if not lo <= v <= hi: raise HTTPException(400, f"«{t}»: {lo}–{hi} oralig'ida bo'lsin")
        new[k] = v
    old = rules()
    ch = [f"{k}: {old.get(k)} → {v}" for k, v in new.items()]
    with _tx():                                     # 2) bitta tranzaksiyada yoziladi (xato — rollback)
        for k, v in new.items():
            _con.execute("INSERT INTO nz_rules(k,v,updated_at,updated_by) VALUES(?,?,?,?) ON CONFLICT(k) DO UPDATE SET v=excluded.v, updated_at=excluded.updated_at, updated_by=excluded.updated_by",
                         (k, v, _iso(_now()), c.title))
    invalidate()
    rbac.audit(_con, c, "nazorat: qoidalar o'zgartirildi", RES, True, ", ".join(ch) or "o'zgarish yo'q")
    return {"ok": True, "rules": rules_view()}

@router.get(P + "/imzo")
def api_sign(request: Request):
    _mod_guard()
    c = C(request); _guard(c, "imzo navbati")
    return sign_queue(c)

class SignIn(BaseModel):
    decision: str
    note: str = Field("", max_length=500)

@router.post(P + "/imzo/{kind}/{ref}")
def api_sign_decide(kind: str, ref: int, body: SignIn, request: Request):
    _mod_guard()
    return sign_decide(C(request), request, kind, ref, body.decision, body.note)

@router.get(P + "/hafta")
def api_brief(request: Request):
    from . import claude_client as CC
    _mod_guard()
    c = C(request); _guard(c, "haftalik hisobot", roles=(LEAD,))
    rows = db.rows(_con, "SELECT * FROM nz_briefs ORDER BY week DESC LIMIT 8")
    rbac.audit(_con, c, "nazorat: haftalik hisobot", RES, True)
    nxt = clock.today() + dt.timedelta(days=(7 - clock.today().weekday()) % 7 or 7)
    return {"latest": _brief_row(rows[0]) if rows else None, "history": [{"week": r["week"], "created_at": r["created_at"], "source": r["source"]} for r in rows],
            "next": f"{nxt.isoformat()}T08:00", "ai": CC.has_key(),
            "telegram": bool(os.getenv("TELEGRAM_BOT_TOKEN", "").strip()),
            "linked": bool(db.one(_con, "SELECT 1 x FROM users WHERE id=? AND telegram_id IS NOT NULL", (c.user["id"],)))}

@router.get(P + "/hafta/{week}")
def api_brief_week(week: str, request: Request):
    _mod_guard()
    c = C(request); _guard(c, "haftalik hisobot", roles=(LEAD,))
    r = db.one(_con, "SELECT * FROM nz_briefs WHERE week=?", (week,))
    if not r: raise HTTPException(404, "Hisobot topilmadi")
    return _brief_row(r)

@router.post(P + "/hafta")
def api_brief_make(request: Request):
    _mod_guard()
    c = C(request); _guard(c, "haftalik hisobotni tayyorlash", roles=(LEAD,))
    b = make_brief(_con, force=True)
    if b is None: raise HTTPException(409, "Haftalik hisobot hozir tayyorlanmoqda — birozdan keyin sahifani yangilang")
    rbac.audit(_con, c, "nazorat: haftalik hisobot tayyorlandi", RES, True, f"{b['week']} · {b['source']}")
    return b


# =============================================================================================
# =============================================================================================
# «ORTDA QOLGANLAR» KEYSLARI — NATIJA KO'RSATKICHLARI (app/keyslar.py). Alohida bo'lim: yuqoridagi kodga tegmaydi,
# faqat RULES va DETECTORS ro'yxatlariga qo'shadi va bitta yangi API qo'shadi (/api/nazorat/keyslar).
#   Istisnolar («talabalar» sohasi): SLA ichida bog'lanilmagan keyslar (tyutor bo'yicha, jamlangan) va tyutor yuklamasi chegaradan oshgani.
#   Ko'rsatkichlar: ochilgan / yopilgan, median bog'lanish vaqti, SLA ichida bog'lanish ulushi, qayta faollashish — bayroqlar soni emas, natija.
# =============================================================================================
# =============================================================================================
RULES.update({"case_sla_min": (1, 1, 100, "Keyslar: SLA ichida bog'lanilmagan keyslar (tyutor bo'yicha, kamida)")})


def _case_cands(con, now, R, O: Org) -> list[dict]:
    if not MODS.on("masofaviy"): return []
    try:
        from . import keyslar as KS
        if KS._con is None: return []
        pol = KS.policy(con)
        rows = db.rows(con, "SELECT id, owner_user, sla_due, first_contact_at FROM ok_cases WHERE status IN ('ochiq','jarayonda')")
    except Exception as e:
        print("nazorat.keyslar:", repr(e)); return []
    out, head = [], O.head("masofaviy")
    late: dict = {}
    for r in rows:
        due = _dt(r["sla_due"])
        if r["first_contact_at"] or not due or due >= now: continue
        late.setdefault(r["owner_user"] or 0, []).append(due)
    mn = R.get("case_sla_min", 1)
    for k, ds in late.items():
        if len(ds) < mn: continue
        who = O.person(k) if k else None
        out.append({"key": f"keys_sla:{k}", "area": "talabalar", "kind": "keys",
                    "title": f"{len(ds)} ta ortda qolgan talaba keysi SLA ichida bog'lanilmagan" + (f" — {who['name']}" if who else " — tyutor biriktirilmagan"),
                    "why": f"Birinchi bog'lanish muddati ({pol['sla_days']} ish kuni) o'tgan, qo'ng'iroq yoki uchrashuv qayd etilmagan: {len(ds)} ta (chegara — {mn})",
                    "src": "Ortda qolganlar — keyslar", "since": min(ds), "owner": k or head, "unit": "masofaviy", "deadline": None,
                    "link": {"view": "ortda", "tab": "keyslar"}, "state": [len(ds)], "aggregate": True})
    lim = pol["caseload_max"]
    for uid, n in KS.loads(con).items():
        if n <= lim: continue
        who = O.person(uid)
        out.append({"key": f"keys_load:{uid}", "area": "talabalar", "kind": "yuklama",
                    "title": f"Tyutor yuklamasi oshgan: {who['name'] if who else '#' + str(uid)} — {n} ta ochiq keys",
                    "why": f"Chegara — {lim} ta (1:50 nisbat). Keyslarni boshqa tyutorlarga taqsimlang («Ortda qolganlar» → Keyslar → Biriktirish)",
                    "src": "Ortda qolganlar — keyslar", "since": None, "owner": head, "unit": "masofaviy", "deadline": None,
                    "link": {"view": "ortda", "tab": "keyslar"}, "state": [n], "aggregate": True})
    return out


DETECTORS.append(_case_cands)


@router.get(P + "/keyslar")
def api_case_outcomes(request: Request):
    """Rektor / o'quv prorektori: keyslar natija ko'rsatkichlari (jamlangan; talaba ismi yo'q, tyutorlar — xodim sifatida)."""
    _mod_guard()
    c = C(request); _guard(c, "keyslar natijasi", roles=(LEAD, "prorektor_oquv"))
    if not MODS.on("masofaviy"): return {"enabled": False}
    from . import keyslar as KS
    d = KS.metrics_data()
    t = d["total"]
    rbac.audit(_con, c, "nazorat: keyslar natijasi", RES, True, f"{t['opened']} ochilgan · SLA {t['sla_pct']}%")
    return {"enabled": True, "total": t, "since": d["since"], "demo": d["demo"], "policy": d["policy"], "definitions": d["definitions"],
            "tutors": [{k: x[k] for k in ("id", "name", "load", "over", "opened", "open", "overdue", "sla_pct", "median_contact_h", "reeng_pct", "closed")}
                       for x in d["tutors"]][:30]}
