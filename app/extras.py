"""Qo'shimcha imkoniyatlar: parolni o'zgartirish, global qidiruv (Ctrl+K), bildirishnomalar markazi va majlislar kalendari.

Tamoyillar:
  * Hamma narsa mavjud ma'lumotdan hisoblanadi — yangi xabar shinasi yo'q. Yangi jadval faqat bitta: `notif_reads`
    (foydalanuvchi bildirishnomalarni qachongacha o'qiganini bildiruvchi "suv belgisi").
  * Qidiruv natijalari RBAC bo'yicha filtrlanadi: ruxsat yo'q bo'lsa natija umuman qaytarilmaydi ("ruxsatingiz yo'q" deb ham ko'rsatilmaydi).
    Jamlangan ko'rinishdagi lavozimlar (rektor, kengash) individual talaba natijasini olmaydi.
  * Talaba ismi bo'yicha qidiruv audit jurnaliga yoziladi (portal umumiy bazalaridagi `q=` qidiruvi kabi), takrorlar birlashtiriladi.
  * Parolni o'zgartirish: joriy parol tekshiriladi, xeshlanadi, audit jurnaliga yoziladi; 10 daqiqada 5 ta xato urinishdan keyin bloklanadi.

CLI (faqat server administratori — server fayl tizimiga kirishi bor odam):
    python -m app.extras reset-passwords            # barcha akkauntlar paroli → sinov paroli (rbac.DEMO_PASSWORD)
    python -m app.extras reset-passwords --user 2   # bitta akkaunt
"""
import datetime as dt, os, re, sys, threading, time
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel
from . import clock
from . import db, rbac, sessions as SS
from .rbac import AccessDenied, Ctx

router = APIRouter()
_con = None
_ctx = None

SCHEMA = """
CREATE TABLE IF NOT EXISTS notif_reads(user_id INTEGER PRIMARY KEY, seen_at TEXT);
CREATE TABLE IF NOT EXISTS notif_first(user_id INT, item_id TEXT, ts TEXT, PRIMARY KEY(user_id, item_id));
CREATE INDEX IF NOT EXISTS ix_students_hemis ON students(hemis_id);
CREATE INDEX IF NOT EXISTS ix_students_name_nc ON students(full_name COLLATE NOCASE);
"""

def init(con):
    try:
        con.executescript(SCHEMA); con.commit()
    except Exception as e:      # bo'sh baza (seed boshlanmagan) — keyingi so'rovda qayta urinadi
        print("extras.init:", e)

def bind(con, ctx_fn):
    global _con, _ctx
    _con, _ctx = con, ctx_fn

def C(request: Request) -> Ctx:
    try:
        _con.execute("SELECT 1 FROM notif_reads LIMIT 1")
    except Exception:            # baza qayta seed qilingan (server to'xtatilmagan)
        init(_con)
    return _ctx(request)

def _now(): return clock.now().replace(microsecond=0)
def _iso(t): return t.isoformat(timespec="seconds")
def _today() -> dt.date:
    from . import services as S
    return clock.today()
def _ts(v) -> str:
    """Har xil sana ko'rinishini solishtirsa bo'ladigan ISO satrga keltiradi."""
    v = str(v or "").replace(" ", "T")[:19]
    return v + "T00:00:00" if len(v) == 10 else v
def _short(name): return (name or "").split(":", 1)[1].strip() if ":" in (name or "") else (name or "")
def _pos(name): return (name or "").split(":", 1)[0].strip() if ":" in (name or "") else ""
def _dmy(v) -> str:
    v = str(v or "")[:10]
    return f"{v[8:10]}.{v[5:7]}.{v[:4]}" if len(v) == 10 and v[4] == "-" else v
def _norm(q: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[ʻʼ‘’`´]", "'", str(q or ""))).strip()

# =============================================================================================
# 1. Ochiq sozlama: sinov paroli izohini yashirish (jonli namoyish uchun)
# =============================================================================================
def hide_demo_hint() -> bool:
    return os.getenv("ISFT_CORE_HIDE_DEMO_HINT", "").strip().lower() in ("1", "true", "yes", "ha")

@router.get("/api/public/config")
def public_config():
    return {"hide_demo_hint": hide_demo_hint()}

@router.get("/api/public/config.js")
def public_config_js():
    """Kirish sahifasi variantlari (static/login/vN.js) yuklanishidan oldin sinxron o'qiladi."""
    body = f"window.ISFT_HIDE_DEMO_HINT={'true' if hide_demo_hint() else 'false'};\n"
    return Response(body, media_type="application/javascript", headers={"Cache-Control": "no-store"})

# =============================================================================================
# 2. Parolni o'zgartirish
# =============================================================================================
PW_LIMIT = SS.Limiter(5, 600)       # 10 daqiqada 5 ta xato urinish

class PasswordIn(BaseModel):
    current: str = ""
    new: str = ""

def password_problem(pw: str) -> str | None:
    if len(pw) < 8: return "Yangi parol kamida 8 ta belgidan iborat bo'lsin"
    if len(pw) > 128: return "Parol juda uzun (ko'pi bilan 128 belgi)"
    if not re.search(r"[^\W\d_]", pw): return "Yangi parolda kamida bitta harf bo'lsin"
    if not re.search(r"\d", pw): return "Yangi parolda kamida bitta raqam bo'lsin"
    if pw.strip() != pw: return "Parol bo'sh joy bilan boshlanmasin va tugamasin"
    return None

def _err(status, field, message, **extra):
    raise HTTPException(status, {"field": field, "message": message, **extra})

@router.post("/api/me/password")
def change_password(body: PasswordIn, request: Request):
    c = C(request); uid = c.user["id"]
    wait = PW_LIMIT.wait_min(uid)
    if wait:
        rbac.audit(_con, c, "parolni o'zgartirish", "auth", False, "bloklangan: ko'p marta noto'g'ri joriy parol")
        _err(429, "current", f"Juda ko'p noto'g'ri urinish. {wait} daqiqadan keyin qayta urinib ko'ring.", wait_min=wait)
    if not rbac.check_password(c.user.get("pin"), body.current):
        left = PW_LIMIT.fail(uid)
        rbac.audit(_con, c, "parolni o'zgartirish", "auth", False, "joriy parol noto'g'ri")
        _err(400, "current", "Joriy parol noto'g'ri" + (f" · yana {left} ta urinish qoldi" if 0 < left < PW_LIMIT.limit else ""), left=left)
    p = password_problem(body.new)
    if p: _err(400, "new", p)
    if body.new == body.current: _err(400, "new", "Yangi parol joriy paroldan farq qilsin")
    h = rbac.hash_password(body.new)
    tg = rbac.set_password(_con, uid, h)     # Telegram ulanishi ham uziladi — botga yangi parol bilan qayta ulanadi
    PW_LIMIT.reset(uid)
    # boshqa brauzer/qurilmalardagi sessiyalar bekor qilinadi, joriy sessiya yangi parol bilan davom etadi
    n = SS.revoke_user(_con, uid, keep_tok=request.cookies.get("sid"), new_pin=h)
    rbac.audit(_con, c, "parol o'zgartirildi", "auth", True, f"boshqa sessiyalar yopildi: {n}" + (" · Telegram uzildi" if tg else ""))
    return {"ok": True, "telegram_unlinked": tg, "message": "Parol o'zgartirildi. Boshqa qurilmalardagi sessiyalar yopildi."
            + (" Telegram ulanishi uzildi — botga lavozim kodi va yangi parolni qayta yuboring." if tg else "")}

# =============================================================================================
# 2b. Shaxsiy ma'lumotlar: lavozim, bo'lim, rahbar/kurator, ruxsatlar, Telegram, kirishlar tarixi
#     Faqat o'zi haqidagi ma'lumot — boshqa foydalanuvchining profili bu yerdan ochilmaydi.
# =============================================================================================
def _person(u) -> dict | None:
    if not u: return None
    return {"name": _short(u["full_name"]) or u["full_name"], "position": _pos(u["full_name"]) or rbac.user_title(u)}

@router.get("/api/me/profile")
def my_profile(request: Request):
    c = C(request); u = c.user; uid = u["id"]
    from . import portal as P
    unit_key = P.my_unit(c)
    ou = db.one(_con, "SELECT * FROM org_units WHERE key=?", (unit_key,)) or {}
    head = db.one(_con, "SELECT * FROM users WHERE id=?", (ou.get("head_user"),)) if ou.get("head_user") and ou.get("head_user") != uid else None
    cur = None
    if ou.get("curator") and ou.get("curator") != c.role.key:
        cur = db.one(_con, "SELECT * FROM users WHERE role=? AND COALESCE(active,1)=1 ORDER BY id LIMIT 1", (ou["curator"],))
    staff = db.one(_con, "SELECT COUNT(*) n FROM users WHERE unit=? AND COALESCE(active,1)=1", (unit_key,))["n"] if unit_key else 0
    curated = [r["name"] for r in db.rows(_con, "SELECT name FROM org_units WHERE curator=? ORDER BY grp, ord", (c.role.key,))] if c.role.key.startswith("prorektor_") else []
    cur_h = SS._h(request.cookies.get("sid") or "")
    try:
        sess = [{"created": _iso(clock.from_ts(s["created"])), "ip": s["ip"] or "—", "device": SS.device(s.get("ua") or ""),
                 "current": s["token"] == cur_h}
                for s in db.rows(_con, "SELECT * FROM sessions WHERE user_id=? AND expires>? ORDER BY (token=?) DESC, created DESC", (uid, time.time(), cur_h))]
    except Exception:
        sess = []
    def _login(r):
        d = r["detail"] or ""
        ip = re.search(r"IP ([^ ·]+)", d); parts = d.split(" · ")
        dev = parts[-1] if len(parts) > 1 and not parts[-1].startswith("IP") else ""
        reason = "" if r["allowed"] else (d.split(" · ")[0] if d else "rad etildi")
        return {"ts": r["ts"], "ok": bool(r["allowed"]), "ip": ip.group(1) if ip else "", "device": dev, "reason": reason, "channel": r["channel"]}
    logins = [_login(r) for r in db.rows(_con, "SELECT ts, allowed, detail, channel FROM audit_log WHERE user_id=? AND action='tizimga kirish' ORDER BY id DESC LIMIT 8", (uid,))]
    fails30 = db.one(_con, "SELECT COUNT(*) n FROM audit_log WHERE user_id=? AND action='tizimga kirish' AND allowed=0 AND ts>=?",
                     (uid, (clock.now() - dt.timedelta(days=30)).isoformat(timespec="seconds")))["n"]
    pw = db.one(_con, "SELECT ts FROM audit_log WHERE user_id=? AND action='parol o''zgartirildi' ORDER BY id DESC LIMIT 1", (uid,))
    try: scope = c.scope_label(_con)
    except Exception: scope = ""
    return {
        "name": _short(u["full_name"]) or u["full_name"], "position": c.title, "role_key": c.role.key,
        "unit": {"key": unit_key, "name": ou.get("name") or unit_key, "staff": staff, "am_head": ou.get("head_user") == uid},
        "head": _person(head), "curator": _person(cur), "curated": curated, "scope": scope,
        "allow": [{"key": a, "label": rbac.LABELS.get(a, a), "agg": bool(c.aggregate_only(a))} for a in sorted(c.role.allow)],
        "telegram": {"linked": bool(u.get("telegram_id")), "code": u.get("link_code") or ""},
        "id": uid, "sessions": sess, "logins": logins, "fails30": fails30, "password_changed": pw["ts"] if pw else None,
        "since": u.get("created_at"),
    }

@router.post("/api/me/sessions/close-others")
def close_other_sessions(request: Request):
    c = C(request)
    n = SS.revoke_user(_con, c.user["id"], keep_tok=request.cookies.get("sid"))
    rbac.audit(_con, c, "sessiyalar yopildi", "auth", True, f"boshqa qurilmalar: {n}")
    return {"ok": True, "closed": n}

# =============================================================================================
# 3. Global qidiruv
# =============================================================================================
LIM = 6
_last_search: dict[int, tuple] = {}

def _student_detail(c: Ctx) -> bool:
    return c.can(rbac.STUDENTS) and not c.aggregate_only(rbac.STUDENTS)

def _ops_card(c: Ctx) -> bool:
    """Talabalar markazidagi kartani ochishi mumkinmi (student_ops._view_guard bilan bir xil shart)."""
    from . import student_ops as OPSM
    return c.can(rbac.OPS) and c.role.key not in OPSM.AGG_VIEW and c.role.key != "call_center" and (
        c.role.key in OPSM.FULL_VIEW or c.role.key in OPSM.FAC_VIEW)

def _like_parts(q):
    """"aliyev elyor" → '%aliyev%elyor%' (so'zlar tartibi saqlanadi)."""
    return "%" + "%".join(q.split(" ")) + "%"

def _search_students(c: Ctx, q: str) -> list[dict]:
    if not _student_detail(c): return []
    sc = c.student_scope("s")
    base = f"""SELECT s.id, s.full_name, s.hemis_id, s.status, g.name grp, g.course, f.name fac FROM students s
               LEFT JOIN groups_ g ON g.id=s.group_id LEFT JOIN faculties f ON f.id=s.faculty_id WHERE {sc} AND """
    out, seen = [], set()
    def add(rows):
        for r in rows:
            if r["id"] not in seen and len(out) < LIM: seen.add(r["id"]); out.append(r)
    if q.isdigit():
        if len(q) >= 3: add(db.rows(_con, base + "s.hemis_id GLOB ? ORDER BY s.hemis_id LIMIT ?", (q + "*", LIM)))
    else:
        add(db.rows(_con, base + "s.full_name LIKE ? ORDER BY s.full_name LIMIT ?", (q + "%", LIM)))      # indeksli prefiks
        if len(out) < LIM:
            add(db.rows(_con, base + "s.full_name LIKE ? ORDER BY s.full_name LIMIT ?", (_like_parts(q), LIM * 2)))
    card = _ops_card(c)
    return [{"id": r["id"], "title": r["full_name"], "sub": " · ".join(x for x in [r["grp"], f"{r['course']}-kurs" if r["course"] else "", r["fac"],
             f"HEMIS {r['hemis_id']}", "" if r["status"] == "faol" else r["status"]] if x),
             "icon": "user", "link": {"view": "ops", "student": r["id"]} if card else {"view": "portal", "dataset": "kontingent", "q": r["full_name"]}}
            for r in out]

def _search_groups(c: Ctx, q: str) -> list[dict]:
    rows = db.rows(_con, """SELECT g.id, g.name, g.course, g.direction, g.form, f.name fac FROM groups_ g LEFT JOIN faculties f ON f.id=g.faculty_id
                            WHERE g.name LIKE ? OR g.direction LIKE ? ORDER BY CASE WHEN g.name LIKE ? THEN 0 ELSE 1 END, g.name LIMIT ?""",
                   (f"%{q}%", f"%{q}%", f"{q}%", LIM))
    return [{"id": r["id"], "title": r["name"], "sub": " · ".join(x for x in [f"{r['course']}-kurs" if r["course"] else "", r["direction"], r["fac"], r["form"]] if x),
             "icon": "users", "link": {"view": "portal", "dataset": "kontingent", "q": r["name"]}} for r in rows]

def _search_people(c: Ctx, q: str) -> list[dict]:
    from . import portal as PT
    out = []
    like = _like_parts(q)
    for u in db.rows(_con, "SELECT id, full_name, role, faculty_id, department_id FROM users WHERE full_name LIKE ? ORDER BY id LIMIT ?", (like, LIM)):
        if u["role"] not in rbac.ROLES: continue
        pos = rbac.user_title(u); nm = _short(u["full_name"])
        out.append({"id": f"u{u['id']}", "title": nm or pos, "sub": pos if nm else "Lavozim", "icon": "shield",
                    "link": {"view": "portal", "compose": PT.unit_key(u)}, "hint": "Xat yozish"})
    if len(out) < LIM:
        for t in db.rows(_con, """SELECT t.id, t.full_name, t.position, t.degree, d.name dep FROM teachers t LEFT JOIN departments d ON d.id=t.department_id
                                  WHERE t.full_name LIKE ? OR t.position LIKE ? ORDER BY t.full_name LIMIT ?""", (like, f"%{q}%", LIM - len(out))):
            out.append({"id": f"t{t['id']}", "title": t["full_name"], "sub": " · ".join(x for x in [t["position"], t["degree"] if t["degree"] not in (None, "", "—") else "", t["dep"] and t["dep"] + " kafedrasi"] if x),
                        "icon": "cap", "link": {"view": "portal", "dataset": "oqituvchilar", "q": t["full_name"]}})
    if c.can(rbac.HR) and len(out) < LIM:      # kadrlar ro'yxati — faqat Kadrlar bo'limi (maosh va pasport ko'rsatilmaydi)
        for s in db.rows(_con, "SELECT id, full_name, unit, position FROM staff WHERE (full_name LIKE ? OR position LIKE ?) AND id NOT IN (SELECT staff_id FROM hr_files WHERE status='boshatilgan') ORDER BY full_name LIMIT ?",
                         (like, f"%{q}%", LIM - len(out))):
            out.append({"id": f"s{s['id']}", "title": s["full_name"], "sub": f"{s['position']} · {s['unit']}", "icon": "user",
                        "link": {"view": "panel", "tab": "ijro"}})
    return out

def _search_docs(c: Ctx, q: str) -> list[dict]:
    w = "1=1" if c.role.key == "rektor" else f"created_by={int(c.user['id'])}"     # documents.registry bilan bir xil
    rows = db.rows(_con, f"""SELECT id, reg_no, title, holder, status, created_at FROM documents WHERE {w}
                             AND (reg_no LIKE ? OR title LIKE ? OR holder LIKE ?) ORDER BY id DESC LIMIT ?""", (f"%{q}%", f"%{q}%", f"%{q}%", LIM))
    st = {"loyiha": "imzo kutilmoqda", "imzolangan": "imzolangan", "berilgan": "berilgan", "bekor": "bekor qilingan"}
    return [{"id": r["id"], "title": r["title"], "sub": " · ".join(x for x in [r["reg_no"], r["holder"], st.get(r["status"], r["status"]), _dmy(r["created_at"])] if x),
             "icon": "file", "link": {"view": "documents", "reg": r["reg_no"]}} for r in rows]

def _search_letters(c: Ctx, q: str) -> list[dict]:
    from . import portal as PT
    me = PT.my_unit(c)
    if PT.is_leader(c): w, a = "1=1", ()
    else: w, a = PT._part_sql(), (me, me, me)
    rows = db.rows(_con, f"""SELECT t.id, t.ref_no, t.subject, t.from_unit, t.due, t.created_at FROM portal_threads t WHERE {w}
                             AND (t.subject LIKE ? OR t.ref_no LIKE ?) ORDER BY t.updated_at DESC, t.id DESC LIMIT ?""", (*a, f"%{q}%", f"%{q}%", LIM))
    um = PT.unit_map(_con)
    return [{"id": r["id"], "title": r["subject"], "sub": " · ".join(x for x in [r["ref_no"], PT._uname(um, r["from_unit"]), f"muddat {_dmy(r['due'])}" if r["due"] else ""] if x),
             "icon": "mail", "link": {"view": "portal", "thread": r["id"]}} for r in rows]

def _search_files(c: Ctx, q: str) -> list[dict]:
    from . import portal as PT
    vw, va = PT._vis_sql(c)
    rows = db.rows(_con, f"""SELECT f.id, f.name, f.ext, f.category, f.owner_unit, f.created_at FROM portal_files f WHERE f.latest=1 AND {vw}
                             AND (f.name LIKE ? OR f.note LIKE ?) ORDER BY f.created_at DESC LIMIT ?""", (*va, f"%{q}%", f"%{q}%", LIM))
    um = PT.unit_map(_con)
    return [{"id": r["id"], "title": r["name"], "sub": " · ".join(x for x in [r["category"], PT._uname(um, r["owner_unit"]), _dmy(r["created_at"])] if x),
             "icon": "folder", "link": {"view": "portal", "file": r["name"]}} for r in rows]

def _visible_tasks(c: Ctx) -> list[dict]:
    from . import services as S
    try:
        return S.tasks_list(_con, c, quiet=True)["tasks"]
    except AccessDenied:
        return []

def _task_link(t):
    """Aniq topshiriqqa havola: ierarxik topshiriq — o'z kartasi; majlis topshirig'i (eski yoki qaror oqimidagi) — majlis + topshiriq."""
    if t.get("origin") == "topshiriq": return {"view": "tasks", "directive": t["id"]}   # app/directives.py
    if t.get("meeting_id"): return {"view": "tasks", "meeting": t["meeting_id"], "task": t["id"]}
    return {"view": "tasks", "task": t["id"]}

def _search_tasks(c: Ctx, q: str) -> list[dict]:
    ql = q.lower(); out = []
    for t in _visible_tasks(c):
        hay = _norm(f"{t.get('text')} {t.get('assignee')} {t.get('meeting')}").lower()
        if all(w in hay for w in ql.split(" ")):
            due = t.get("due_at") or t.get("due")
            out.append({"id": t["id"], "title": t["text"], "sub": " · ".join(x for x in [t.get("assignee"), t.get("meeting"),
                        f"muddat {_dmy(due)}" if due else "", "muddati o'tgan" if t.get("overdue") else t.get("status")] if x),
                        "icon": "tasks", "link": _task_link(t), "bad": bool(t.get("overdue"))})
        if len(out) >= LIM: break
    return out

GROUPS = [("talabalar", "Talabalar", _search_students), ("guruhlar", "Guruhlar", _search_groups), ("xodimlar", "Xodimlar va lavozimlar", _search_people),
          ("hujjatlar", "Hujjatlar", _search_docs), ("xatlar", "Portal xatlari", _search_letters), ("fayllar", "Portal fayllari", _search_files),
          ("topshiriqlar", "Topshiriqlar", _search_tasks)]

def _audit_student_search(c: Ctx, q: str, n: int):
    """Talaba ma'lumoti ko'rsatildi — auditga yoziladi. Har bir harf uchun alohida yozuv bo'lmasin: bir qidiruv seansida
    (oldingisini davom ettiruvchi so'rovlar, 60 soniya ichida, ko'pi bilan 5 daqiqa) bitta yozuv yangilanib boradi va unda
    eng to'liq (aniq) so'rov qoladi — oxirida haqiqatan qidirilgan talaba nomi jurnalda ko'rinadi."""
    uid = c.user["id"]; now = time.time(); ql = q.lower()
    prev = _last_search.get(uid)    # (eng to'liq so'rov, oxirgi vaqt, seans boshi, audit yozuvi id)
    if prev and now - prev[1] < 60 and now - prev[2] < 300:
        if prev[0].startswith(ql):               # takror yoki qisqartirish — yozuvdagi aniqroq so'rov yetarli
            _last_search[uid] = (prev[0], now, prev[2], prev[3]); return
        if ql.startswith(prev[0]):               # davom ettirish — yozuv aniqroq so'rov bilan yangilanadi
            _con.execute("UPDATE audit_log SET detail=? WHERE id=?", (f"q={q[:60]} · {n} ta natija", prev[3])); _con.commit()
            _last_search[uid] = (ql, now, prev[2], prev[3]); return
    rid = rbac.audit(_con, c, "global qidiruv: talabalar", rbac.STUDENTS, True, f"q={q[:60]} · {n} ta natija")
    _last_search[uid] = (ql, now, now, rid)

@router.get("/api/search")
def search(request: Request, q: str = ""):
    c = C(request); q = _norm(q)[:60]
    if len(q) < 2: return {"q": q, "groups": [], "ms": 0}
    t0 = time.perf_counter(); groups = []
    for key, title, fn in GROUPS:
        try:
            items = fn(c, q)
        except AccessDenied:
            items = []         # ruxsat yo'q — guruh umuman ko'rsatilmaydi
        if items: groups.append({"key": key, "title": title, "items": items})
    st = next((g for g in groups if g["key"] == "talabalar"), None)
    if st: _audit_student_search(c, q, len(st["items"]))
    return {"q": q, "groups": groups, "ms": round(1000 * (time.perf_counter() - t0), 1)}

# =============================================================================================
# 4. Bildirishnomalar markazi
# =============================================================================================
def _seen(uid) -> str | None:
    r = db.one(_con, "SELECT seen_at FROM notif_reads WHERE user_id=?", (uid,))
    return r["seen_at"] if r else None

def _day_ts(d: dt.date) -> str: return _iso(dt.datetime.combine(d, dt.time(0, 0)))

def _due_date(v) -> dt.date | None:
    try: return dt.date.fromisoformat(str(v)[:10]) if v else None
    except ValueError: return None

# Qo'ng'iroqchadagi «ish» yozuvlari — mywork.collect() elementlaridan (yagona manba). Bu yerda faqat ko'rinish: sarlavha, daraja, vaqt.
SRC_T = {"majlis": "Topshiriqlar", "portal": "Yozishmalar", "markaz": "Talabalar markazi", "buyruq": "Buyruqlar", "murojaat": "Murojaatlar", "xodim": "Xodimlar ta'tili",
         "agent": "AI agentlar", "sillabus": "O'quv dasturlari"}
SRC_CAP = 8            # bitta manbadan qo'ng'iroqchada ko'pi bilan shuncha qator; qolgani — bitta jamlangan yozuv («Mening vazifalarim»ga havola)
_NF_SCHEMA = "CREATE TABLE IF NOT EXISTS notif_first(user_id INT, item_id TEXT, ts TEXT, PRIMARY KEY(user_id, item_id))"

def _first_seen(uid, ids: list) -> dict:
    """Ish qachon birinchi marta shu xodim ro'yxatida paydo bo'lgan — «yangi» belgisi shu vaqtdan (har kuni qayta «o'qilmagan» bo'lmaydi).
    Ro'yxatdan chiqqan ish yozuvi o'chiriladi (qayta paydo bo'lsa — yana yangi)."""
    try: have = {r["item_id"]: r["ts"] for r in db.rows(_con, "SELECT item_id, ts FROM notif_first WHERE user_id=?", (uid,))}
    except Exception: _con.execute(_NF_SCHEMA); _con.commit(); have = {}
    now = _iso(_now()); cur = set(ids)
    new, gone = [i for i in cur if i not in have], [i for i in have if i not in cur]
    if new or gone:
        _con.executemany("INSERT OR IGNORE INTO notif_first(user_id,item_id,ts) VALUES(?,?,?)", [(uid, i, now) for i in new])
        _con.executemany("DELETE FROM notif_first WHERE user_id=? AND item_id=?", [(uid, i) for i in gone])
        _con.commit()
    return {i: have.get(i, now) for i in cur}

def _work_notifs(c: Ctx, events: list) -> list[dict]:
    from . import mywork as MW
    work = MW.collect_cached(c)["items"]
    today = _today(); uid = c.user["id"]
    ev_ids = {e["id"] for e in events}
    ev_links = [e["link"] for e in events if e.get("kind") in ("topshiriq", "topshiriq_muddat", "sillabus")]   # shu obyekt hodisa sifatida allaqachon bor
    fs = _first_seen(uid, [it["id"] for it in work])
    out = []
    for it in work:
        src, iid = it["source"], it["id"]
        if iid in ev_ids or (src in ("majlis", "sillabus") and it["link"] in ev_links): continue
        d = _due_date(it["due"]); over = bool(it.get("overdue")); days = (d - today).days if d else None
        soon = d is not None and not over and days <= 2
        when = "" if not soon else "bugun" if days <= 0 else "ertaga" if days == 1 else "2 kundan keyin"
        nid, kind, title = iid, src, it["title"]
        if src == "majlis" and it["kind"] == "topshiriq" and iid.startswith("mt"):
            nid, kind = ("to" if over else "tn") + iid[2:], "topshiriq_muddat" if over else "topshiriq"
            title = (f"Topshiriq muddati o'tgan: {title}" if over else f"Topshiriq muddati {when}: {title}" if soon else title)
        elif src == "majlis":
            kind = "topshiriq_muddat" if over else "topshiriq"
            if iid == "mtall": nid = "tall"
        elif src == "portal":
            kind = "xat_muddat" if d else "xat"
            if it["kind"] == "xat":
                title = f"Javob muddati o'tgan: «{title}»" if over else f"Javob muddati {when}: «{title}»" if soon else f"«{title}»"
            elif it["kind"] == "rezolyutsiya" and over:
                title = title.replace("Rezolyutsiya ijrosi:", "Rezolyutsiya ijrosi kechikmoqda:", 1)
        ts = fs.get(iid) or _iso(_now())
        if d and over: ts = max(ts, _day_ts(d + dt.timedelta(days=1)))          # muddat o'tganda yana «yangi» bo'lib ko'tariladi
        elif soon: ts = max(ts, _day_ts(d - dt.timedelta(days=2)))
        out.append({"id": nid, "kind": kind, "icon": ("alert" if over else "clock") if kind in ("xat_muddat", "topshiriq", "topshiriq_muddat") and (over or soon) else (it.get("icon") or "list"),
                    "level": "bad" if over else "warn" if (it.get("sign") or soon or it.get("priority") == "high") else "info",
                    "title": title, "sub": " · ".join(x for x in [it.get("sub") or "", f"muddat {d.strftime('%d.%m.%Y')}" if d else ""] if x),
                    "ts": ts, "link": it["link"], "_src": src})
    # qo'ng'iroqchani to'ldirmaslik: AI takliflari 3 tadan ko'p bo'lsa — bitta yozuv; boshqa manbalar — SRC_CAP tadan, qolgani jamlanadi (soni aniq)
    res = []
    for src in dict.fromkeys(x["_src"] for x in out):
        rows = sorted((x for x in out if x["_src"] == src), key=lambda x: ({"bad": 0, "warn": 1, "info": 2}[x["level"]], x["ts"]))
        if src == "agent" and len(rows) > 3:
            res.append({"id": "agall", "kind": "agent", "icon": "spark", "level": "info", "title": f"AI agentlar: {len(rows)} ta taklif tasdiqingizni kutmoqda",
                        "sub": "Har biri «Mening vazifalarim»da alohida qator", "ts": max(x["ts"] for x in rows), "link": max(rows, key=lambda x: x["ts"])["link"]})
            continue
        keep = rows if len(rows) <= SRC_CAP else rows[:SRC_CAP - 1]
        res += keep
        if len(rows) > len(keep):
            rest = rows[len(keep):]
            res.append({"id": f"more-{src}", "kind": src, "icon": "list", "level": "info", "title": f"{SRC_T.get(src, 'Boshqa ishlar')}: yana {len(rest)} ta ish kutmoqda",
                        "sub": "To'liq ro'yxat — «Mening vazifalarim»da", "ts": max(x["ts"] for x in rest), "link": {"view": "mywork"}})
    for x in res: x.pop("_src", None)
    return res

def notifications(c: Ctx) -> list[dict]:
    from . import portal as PT
    items = []; me = PT.my_unit(c); um = PT.unit_map(_con)
    # --- portal: o'qilmagan xatlar va javoblar (shu xodim bo'yicha; tizim yozuvlari hisobga olinmaydi) ---
    uid = c.user["id"]
    rows = db.rows(_con, """SELECT t.id, t.subject, t.ref_no, t.from_unit, t.priority, m.created_at last_at, m.unit last_unit, m.kind last_kind
        FROM portal_threads t
        JOIN (SELECT thread_id, MAX(id) mid FROM portal_msgs WHERE unit!=? AND COALESCE(kind,'xat')!='tizim' GROUP BY thread_id) x ON x.thread_id=t.id
        JOIN portal_msgs m ON m.id=x.mid
        LEFT JOIN portal_user_reads pr ON pr.thread_id=t.id AND pr.user_id=?
        WHERE t.status='ochiq' AND NOT EXISTS(SELECT 1 FROM portal_hidden h WHERE h.thread_id=t.id AND h.user_id=?)
          AND (t.from_unit=? OR EXISTS(SELECT 1 FROM portal_recipients r WHERE r.thread_id=t.id AND r.unit=?)
               OR EXISTS(SELECT 1 FROM portal_watchers w WHERE w.thread_id=t.id AND w.unit=?))
          AND x.mid > COALESCE(pr.last_msg, 0)
        ORDER BY x.mid DESC LIMIT 15""", (me, uid, uid, me, me, me))
    for r in rows:
        res = r["last_kind"] == "rezolyutsiya"
        reply = r["from_unit"] == me
        items.append({"id": f"pt{r['id']}", "kind": "xat", "icon": "mail", "level": "bad" if r["priority"] == "shoshilinch" or res else "info",
                      "title": ("Rezolyutsiya: " if res else "Javob keldi: " if reply else "Yangi xat: ") + f"«{r['subject']}»",
                      "sub": " · ".join(x for x in [PT._uname(um, r["last_unit"]), r["ref_no"], "shoshilinch" if r["priority"] == "shoshilinch" else ""] if x),
                      "ts": _ts(r["last_at"]), "link": {"view": "portal", "thread": r["id"]}})
    # ko'p xat bo'lsa — qo'ng'iroqchani to'ldirmaslik uchun oddiylari bitta jamlangan yozuvga (rezolyutsiya va shoshilinchlar alohida qoladi)
    letters = [i for i in items if i["kind"] == "xat"]
    plain = [i for i in letters if i["level"] == "info"]
    if len(letters) > 3 and len(plain) > 1:
        items = [i for i in items if i not in plain]
        subj = [re.sub(r"^(Yangi xat|Javob keldi): ", "", i["title"]) for i in plain[:2]]
        items.append({"id": "ptall", "kind": "xat", "icon": "mail", "level": "info", "title": f"Portal: {len(plain)} ta o'qilmagan xat va javob",
                      "sub": " · ".join(subj) + (f" va yana {len(plain) - 2} ta" if len(plain) > 2 else ""),
                      "ts": max(i["ts"] for i in plain), "link": {"view": "portal", "flt": "unread"}})
    # --- hodisalar (jonli): ierarxik topshiriqlar — yangi, qaytarildi, qabulimni kutmoqda (app/directives.py); sillabuslar (app/syllabus.py) ---
    try:
        from . import directives as DIR
        items += DIR.notifications(c)
    except Exception as e:
        print("notifications.directives:", repr(e))
    try:
        from . import syllabus as SY
        items += SY.notif_items(c)
    except Exception as e: print("notifications.syllabus:", repr(e))
    # --- kutilayotgan ishlar: «Mening vazifalarim» bilan AYNAN bitta yig'uvchi (mywork.collect — majlis, portal muddatlari, markaz, buyruqlar,
    #     murojaatlar, AI takliflari va barcha modul adapterlari). Alohida hisob-kitob yo'q — sonlar ikki joyda bir xil. ---
    try:
        items += _work_notifs(c, items)
    except Exception as e:
        print("notifications.work:", repr(e))
    now = _iso(_now())
    for it in items: it["ts"] = min(it["ts"], now)      # kelajakdagi vaqt "… oldin" deb ko'rinmasin
    items.sort(key=lambda x: x["ts"], reverse=True)
    return items[:40]

@router.get("/api/notifications")
def api_notifications(request: Request):
    c = C(request); seen = _seen(c.user["id"])
    items = notifications(c)
    for it in items: it["unread"] = not seen or it["ts"] > seen
    from . import mywork as MW
    wc = MW.collect_cached(c)["counts"]       # notifications() hozirgina to'ldirgan kesh — «Mening vazifalarim»dagi sonning o'zi
    return {"items": items, "unread": sum(it["unread"] for it in items), "seen_at": seen, "now": _iso(_now()),
            "work": {"total": wc["total"], "overdue": wc["overdue"], "today": wc["today"], "by_source": wc["by_source"]}}

@router.post("/api/notifications/read")
def api_notifications_read(request: Request):
    c = C(request); now = _iso(_now())
    _con.execute("INSERT INTO notif_reads(user_id, seen_at) VALUES(?,?) ON CONFLICT(user_id) DO UPDATE SET seen_at=excluded.seen_at", (c.user["id"], now))
    _con.commit()
    return {"ok": True, "seen_at": now}

# =============================================================================================
# 5. Majlislar kalendari
# =============================================================================================
@router.get("/api/calendar")
def api_calendar(request: Request, month: str = ""):
    from . import portal as PT
    c = C(request); today = _today()
    m = re.fullmatch(r"(\d{4})-(\d{2})", month or "")
    y, mo = (int(m[1]), int(m[2])) if m and 1 <= int(m[2]) <= 12 else (today.year, today.month)
    first = dt.date(y, mo, 1); nxt = dt.date(y + (mo == 12), mo % 12 + 1, 1)
    lo, hi = first - dt.timedelta(days=7), nxt + dt.timedelta(days=7)      # to'rdagi qo'shni oylar kunlari uchun ham
    inr = lambda d: d is not None and lo <= d < hi
    ev = []
    tl = _visible_tasks(c)
    has_tasks = c.can(rbac.TASKS)
    if has_tasks:
        lead = c.role.key in ("rektor", "kengash", "kotib")
        mids = {t["meeting_id"] for t in tl}
        for mt in db.rows(_con, "SELECT id, title, date, kind, status, source FROM meetings WHERE COALESCE(status,'')!='qoralama' ORDER BY date"):
            d = _due_date(mt["date"])
            if not inr(d) or not (lead or mt["id"] in mids): continue
            n = sum(1 for t in tl if t["meeting_id"] == mt["id"])
            ev.append({"id": f"m{mt['id']}", "type": "majlis", "date": d.isoformat(), "title": mt["title"],
                       "sub": " · ".join(x for x in [mt["kind"], f"{n} ta topshiriq" if n else "", "majlis qarori (ISFT Core)" if mt["source"] else ""] if x),
                       "status": mt["status"] or "o'tkazildi", "overdue": False, "done": d < today,
                       "link": {"view": "tasks", "meeting": mt["id"]}})
        for t in tl:
            due = t.get("due_at") or t.get("due"); d = _due_date(due)
            if not inr(d): continue
            ev.append({"id": f"t{t['id']}", "type": "topshiriq", "date": d.isoformat(), "time": str(due)[11:16] if "T" in str(due) else "",
                       "title": t["text"], "sub": " · ".join(x for x in [t.get("assignee"), t.get("meeting")] if x),
                       "status": t["status"], "overdue": bool(t.get("overdue")), "done": t["status"] == "bajarildi", "mine": bool(t.get("mine")),
                       "link": _task_link(t)})
    me = PT.my_unit(c); um = PT.unit_map(_con)
    for r in db.rows(_con, """SELECT * FROM (SELECT t.id, t.subject, t.ref_no, t.from_unit, t.status tstatus,
                                     COALESCE(NULLIF((SELECT x.due FROM portal_recipients x WHERE x.thread_id=t.id AND x.unit=?),''), t.due) due,
                                     (SELECT status FROM portal_recipients x WHERE x.thread_id=t.id AND x.unit=?) my_status,
                                     (SELECT COUNT(*) FROM portal_recipients x WHERE x.thread_id=t.id AND x.status IN ('yangi','o''qilgan')) pending
                              FROM portal_threads t WHERE (t.from_unit=? OR EXISTS(SELECT 1 FROM portal_recipients x WHERE x.thread_id=t.id AND x.unit=?)))
                              WHERE due IS NOT NULL AND due!='' AND due>=? AND due<? ORDER BY due""", (me, me, me, me, lo.isoformat(), hi.isoformat())):
        d = _due_date(r["due"])
        if not d: continue
        sent = r["from_unit"] == me
        done = r["tstatus"] == "yopilgan" or ((r["pending"] == 0) if sent else (r["my_status"] in ("javob berilgan", "yo'naltirilgan")))
        ev.append({"id": f"p{r['id']}", "type": "xat", "date": d.isoformat(), "title": r["subject"],
                   "sub": " · ".join(x for x in [r["ref_no"], ("Yuborilgan · " + (f"{r['pending']} ta bo'lim javob bermagan" if r["pending"] else "hammasi javob bergan"))
                                                 if sent else f"{PT._uname(um, r['from_unit'])}dan"] if x),
                   "status": "javob berilgan" if done else "javob kutilmoqda", "overdue": (not done) and d < today, "done": done,
                   "link": {"view": "portal", "thread": r["id"]}})
    order = {"majlis": 0, "topshiriq": 1, "xat": 2}
    ev.sort(key=lambda e: (e["date"], order[e["type"]], e["title"]))
    rbac.audit(_con, c, "majlislar kalendari", rbac.TASKS if has_tasks else "portal", True, f"{y}-{mo:02d}")
    return {"month": f"{y}-{mo:02d}", "today": today.isoformat(), "events": ev, "has_tasks": has_tasks,
            "counts": {k: sum(1 for e in ev if e["type"] == k and first <= dt.date.fromisoformat(e["date"]) < nxt) for k in order}}

# =============================================================================================
# CLI: demo parollarini tiklash
# =============================================================================================
def reset_passwords(con, user_id: int | None = None) -> int:
    h = rbac.hash_password(rbac.DEMO_PASSWORD)    # bitta xesh — hamma uchun (sinov rejimi)
    if user_id:
        n = con.execute("UPDATE users SET pin=? WHERE id=?", (h, user_id)).rowcount
    else:
        n = con.execute("UPDATE users SET pin=?", (h,)).rowcount
    rbac.unlink_telegram_all(con, user_id)     # parol almashdi — Telegram ulanishi ham uziladi (eski izsiz ulanishlar ham)
    con.execute("INSERT INTO audit_log(ts,user_id,user_name,role,channel,action,resource,allowed,detail) VALUES(?,?,?,?,?,?,?,?,?)",
                (_iso(_now()), 0, "Server administratori (CLI)", "admin", "cli", "demo parollari tiklandi", "auth", 1,
                 f"{n} ta akkaunt" + (f" · #{user_id}" if user_id else "")))
    con.commit()
    return n

def _cli(argv):
    if not argv or argv[0] not in ("reset-passwords",):
        print("Foydalanish: python -m app.extras reset-passwords [--user ID]\n"
              "  barcha (yoki bitta) akkaunt parolini sinov paroliga qaytaradi — faqat server administratori uchun", file=sys.stderr); return 2
    uid = None
    if "--user" in argv:
        try: uid = int(argv[argv.index("--user") + 1])
        except (IndexError, ValueError):
            print("--user dan keyin akkaunt raqamini yozing", file=sys.stderr); return 2
    con = db.connect()
    if uid and not db.one(con, "SELECT 1 x FROM users WHERE id=?", (uid,)):
        print(f"#{uid} akkaunt topilmadi", file=sys.stderr); return 1
    n = reset_passwords(con, uid)
    print(f"Tayyor: {n} ta akkaunt paroli sinov paroliga qaytarildi ({'#' + str(uid) if uid else 'barchasi'}). Audit jurnaliga yozildi.")
    return 0

if __name__ == "__main__":
    sys.exit(_cli(sys.argv[1:]))
