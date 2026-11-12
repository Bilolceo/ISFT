"""Akkauntlar boshqaruvi — AT bo'limi boshlig'i (it_head) uchun veb-sahifa (static/accounts.js).

Avval akkauntlar faqat CLI orqali boshqarilardi (python -m app.extras reset-passwords). Endi:
  * it_head — to'liq boshqaruv: akkaunt yaratish, lavozim/ism va bo'limni o'zgartirish, parolni tiklash (vaqtinchalik parol bir marta
    ko'rsatiladi, bazada faqat xesh), sinov parolini tiklash (faqat sinov rejimida), blokdan chiqarish (kirish urinishlari cheklovi),
    sessiyalarni yopish, Telegram'ni uzish, faolsizlantirish / faollashtirish;
  * rektor — faqat ko'rish (ro'yxat, holat, oxirgi kirish); har qanday o'zgartirish urinishi 403 va audit jurnaliga yoziladi;
  * boshqalar — 403 (audit jurnaliga yoziladi).

Imtiyozlarni oshirishning oldini olish:
  * Himoyalangan lavozimlar — rahbariyat darajasi (rbac level 1–2: kengash, rektor, prorektorlar, kotib) va it_head. Bu lavozimni
    UI orqali berish ham, olib qo'yish ham mumkin emas; bunday akkauntning profili va holati faqat CLI orqali o'zgaradi.
    Ularga ham parolni tiklash mumkin (doim audit + barcha sessiyalari yopiladi).
  * O'z akkauntini o'zgartirish (rol, holat, parol tiklash) mumkin emas — parol uchun «Parolni o'zgartirish» oynasi bor.
  * O'qituvchi lavozimi (teachers jadvaliga bog'lanadi) bu sahifadan berilmaydi.

Faolsizlantirish: users.active=0 → kirish rad etiladi (main.py /api/login), mavjud sessiyalar o'chiriladi va ishlamay qoladi
(main.ctx), kirish ro'yxatida (/api/users) ko'rinmaydi, Telegram uziladi (bot ham faol bo'lmagan akkauntni tanimaydi).
Har bir amal rbac.audit(resource="accounts").
"""
import datetime as dt, re, secrets, time
from fastapi import APIRouter, Request, HTTPException, Response
from pydantic import BaseModel
from . import clock
from . import db, rbac, sessions as SS
from .rbac import AccessDenied, Ctx

router = APIRouter()
_con = None
_ctx = None
RES = "accounts"
ADMIN, VIEWERS = "it_head", ("it_head", "rektor")

def _add_cols(con, table, cols):
    have = {r[1] for r in con.execute(f"PRAGMA table_info({table})")}
    for n, t in cols:
        if n not in have: con.execute(f"ALTER TABLE {table} ADD COLUMN {n} {t}")

def init(con):
    try:
        _add_cols(con, "users", [("active", "INT DEFAULT 1"), ("unit", "TEXT"), ("created_at", "TEXT"), ("created_by", "INT")])
        con.commit()
        retire_legacy(con)
    except Exception as e:          # bo'sh baza (seed boshlanmagan) — keyingi so'rovda qayta urinadi
        print("accounts.init:", e)

def retire_legacy(con) -> int:
    """Bekor qilingan lavozimdagi akkauntlar (rbac.LEGACY_ROLES — «dekan», users #13) faolsizlantiriladi: kira olmaydi, kirish
    ro'yxatida yo'q, Telegram uziladi, sessiyalari yopiladi. id saqlanadi (eski yozuvlar va testlar id'ga tayanadi). Idempotent."""
    _add_cols(con, "users", [("active", "INT DEFAULT 1")])
    keys = tuple(rbac.LEGACY_ROLES)
    ph = ",".join("?" * len(keys))
    # eski bazalar: dekanga yozilgan majlis topshiriqlari — fakultet darajasidagi vazifa sifatida Registrator ofisiga
    try:
        if con.execute(f"UPDATE tasks SET assignee_role='talabalar', assignee='Registrator ofisi' WHERE assignee_role IN ({ph}) AND unit IS NULL", keys).rowcount:
            con.commit()
    except Exception: pass   # tasks jadvali hali yo'q (bo'sh baza)
    ids = [r[0] for r in con.execute(f"SELECT id FROM users WHERE role IN ({ph}) AND (COALESCE(active,1)!=0 OR telegram_id IS NOT NULL)", keys)]
    if not ids: return 0
    con.execute(f"UPDATE users SET active=0, telegram_id=NULL WHERE id IN ({','.join('?' * len(ids))})", ids)
    try: con.execute(f"DELETE FROM sessions WHERE user_id IN ({','.join('?' * len(ids))})", ids)
    except Exception: pass   # sessiyalar jadvali hali yo'q (yangi seed)
    con.commit()
    return len(ids)

def bind(con, ctx_fn):
    global _con, _ctx
    _con, _ctx = con, ctx_fn
    from . import desks as DK     # lavozim ish stollari (strategik, sifat, marketing, yuridik) — shu router orqali ulanadi
    DK.bind(con, ctx_fn)
    if not getattr(router, "_desks", False):
        router.include_router(DK.router); router._desks = True

def _now(): return clock.now().isoformat(timespec="seconds")
def _short(name): return (name or "").split(":", 1)[1].strip() if ":" in (name or "") else ""
def _pos(name): return (name or "").split(":", 1)[0].strip() if ":" in (name or "") else (name or "")

# ---------------------------------------------------------------------------------------------
# Ruxsatlar
# ---------------------------------------------------------------------------------------------
PROTECTED = frozenset(k for k, r in rbac.ROLES.items() if r.level <= 2) | {"it_head"}
NOT_ASSIGNABLE = PROTECTED | {"oqituvchi"}      # o'qituvchi — teachers yozuviga bog'lanadi (seed/HEMIS orqali)

def assignable_roles() -> list[str]:
    return [k for k in rbac.ACTIVE_ROLES if k not in NOT_ASSIGNABLE]

def _check_role(role: str, field_msg: str, current: str | None = None):
    """Rol mavjud va faol bo'lsin. Bekor qilingan lavozim (rbac.LEGACY_ROLES, masalan «dekan») hech kimga berilmaydi."""
    if role in rbac.LEGACY_ROLES and role != current:
        _bad(f"«{rbac.ROLES[role].title}» — bu lavozim institut tuzilmasida yo'q", "role")
    if role not in rbac.ROLES: _bad(field_msg, "role")

def C(request: Request, write: bool, action: str, detail: str = "") -> Ctx:
    try:
        _con.execute("SELECT active FROM users LIMIT 1")
    except Exception:                # baza qayta seed qilingan (server to'xtatilmagan)
        init(_con)
    c = _ctx(request)
    ok = c.role.key == ADMIN if write else c.role.key in VIEWERS
    if not ok:
        rbac.audit(_con, c, f"akkauntlar: {action}", RES, False, detail)
        raise AccessDenied("⛔ Akkauntlarni boshqarish faqat Axborot texnologiyalari bo'limi boshlig'i uchun"
                           + (" (rektor — faqat ko'rish)" if c.role.key == "rektor" else "") + ". So'rov audit jurnaliga yozildi.")
    return c

def _deny(c: Ctx, action: str, detail: str, message: str):
    rbac.audit(_con, c, f"akkauntlar: {action}", RES, False, detail)
    raise AccessDenied(f"⛔ {message}. Urinish audit jurnaliga yozildi.")

def _bad(message: str, field: str = ""):
    raise HTTPException(400, {"message": message, "field": field})

def _target(uid: int) -> dict:
    u = db.one(_con, "SELECT * FROM users WHERE id=?", (uid,))
    if not u or u.get("role") not in rbac.ROLES: raise HTTPException(404, "Akkaunt topilmadi")
    return u

def _tag(u: dict) -> str:
    return f"#{u['id']} {u.get('full_name') or ''}"[:160]

def demo_mode() -> bool:
    """Sinov rejimi: kirish sahifasida sinov paroli izohi ko'rsatiladi (ISFT_CORE_HIDE_DEMO_HINT o'rnatilmagan)."""
    from . import extras as XT
    return not XT.hide_demo_hint()

def temp_password() -> str:
    """Kuchli vaqtinchalik parol: 3×4 belgi (o'xshash belgilar — 0/O, 1/l/I — yo'q), kamida bitta harf va raqam. ≈69 bit."""
    al = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnpqrstuvwxyz23456789"
    while True:
        s = "".join(secrets.choice(al) for _ in range(12))
        if re.search(r"\d", s) and re.search(r"[A-Za-z]", s):
            return "-".join(s[i:i + 4] for i in range(0, 12, 4))

def _link_code() -> str:
    while True:
        k = "AKK" + "".join(secrets.choice("ABCDEFGHJKMNPQRSTUVWXYZ23456789") for _ in range(5))
        if not db.one(_con, "SELECT 1 x FROM users WHERE upper(link_code)=?", (k,)): return k

# ---------------------------------------------------------------------------------------------
# Bo'limlar (portal.units() — faqat o'qiladi)
# ---------------------------------------------------------------------------------------------
def _units() -> list[dict]:
    from . import portal as PT
    try:
        return PT.units(_con)
    except Exception:
        return []

def _default_unit(role: str, u: dict | None = None) -> str:
    from . import portal as PT
    x = dict(u or {}); x["role"] = role; x["unit"] = None
    return PT.derive_unit(x)

def _resolve_unit(role: str, unit: str, base: dict | None = None) -> tuple[str, dict]:
    """Rol + bo'lim → (unit, ko'lam maydonlari). Fakultet/kafedra ko'lamidagi lavozimlar mos bo'limni talab qiladi."""
    um = {x["key"]: x for x in _units()}
    scope = rbac.ROLES[role].scope
    unit = (unit or "").strip() or _default_unit(role, base)
    if unit not in um: _bad("Bo'lim ro'yxatdan tanlansin", "unit")
    extra: dict = {}
    if scope == "fakultet":
        if not unit.startswith("fak"): _bad(f"«{rbac.ROLES[role].title}» uchun fakultet tanlansin", "unit")
        extra["faculty_id"] = int(unit[3:])
    elif scope == "kafedra":
        if not unit.startswith("kaf"): _bad(f"«{rbac.ROLES[role].title}» uchun kafedra tanlansin", "unit")
        d = db.one(_con, "SELECT id, faculty_id FROM departments WHERE id=?", (int(unit[3:]),))
        if not d: _bad("Kafedra topilmadi", "unit")
        extra.update(department_id=d["id"], faculty_id=d["faculty_id"])
    return unit, extra

# ---------------------------------------------------------------------------------------------
# Ro'yxat
# ---------------------------------------------------------------------------------------------
def _last_logins() -> dict:
    out = {r["user_id"]: r["ts"] for r in db.rows(_con, "SELECT user_id, MAX(ts) ts FROM audit_log WHERE action='tizimga kirish' AND allowed=1 GROUP BY user_id")}
    try:      # audit jurnali tozalangan bo'lsa ham — sessiyalar jadvalidan
        for r in db.rows(_con, "SELECT user_id, MAX(created) c FROM sessions GROUP BY user_id"):
            ts = clock.from_ts(r["c"]).isoformat(timespec="seconds") if r["c"] else None
            if ts and ts > (out.get(r["user_id"]) or ""): out[r["user_id"]] = ts
    except Exception: pass
    return out

def _after(ts, created):
    """id qayta ishlatilgan bo'lsa (o'chirilgan akkaunt), akkaunt yaratilishidan oldingi kirishlar hisobga olinmaydi."""
    return ts if ts and (not created or ts >= created) else None

def _sessions() -> dict:
    try:
        return {r["user_id"]: r["n"] for r in db.rows(_con, "SELECT user_id, COUNT(*) n FROM sessions WHERE expires>? GROUP BY user_id", (time.time(),))}
    except Exception:
        return {}

def _item(u, c: Ctx, um, last, sess) -> dict:
    admin = c.role.key == ADMIN
    role = rbac.ROLES[u["role"]]; unit = u.get("unit") or _default_unit(u["role"], u)
    me, prot = u["id"] == c.user["id"], u["role"] in PROTECTED
    x = {"id": u["id"], "full_name": u["full_name"], "position": _pos(u["full_name"]), "person": _short(u["full_name"]),
         "title": rbac.user_title(u), "role": u["role"], "role_title": role.title, "level": role.level,
         "unit": unit, "unit_name": (um.get(unit) or {}).get("name") or unit,
         "telegram": bool(u.get("telegram_id")), "active": u.get("active") != 0,
         "last_login": _after(last.get(u["id"]), u.get("created_at")), "sessions": sess.get(u["id"], 0), "locked_min": SS.LOGIN_USER.wait_min(u["id"]),
         "protected": prot, "self": me, "created_at": u.get("created_at")}
    if admin:
        x["link_code"] = u.get("link_code") or ""
        x["can"] = {"edit": not prot and not me, "role": not prot and not me, "reset": not me, "status": not prot and not me,
                    "revoke": True, "unlink": bool(u.get("telegram_id")), "unlock": x["locked_min"] > 0}
    return x

@router.get("/api/accounts")
def list_accounts(request: Request):
    c = C(request, False, "ro'yxat")
    um = {x["key"]: x for x in _units()}
    last, sess = _last_logins(), _sessions()
    us = [u for u in db.rows(_con, "SELECT * FROM users ORDER BY id") if u.get("role") in rbac.ROLES]
    us.sort(key=lambda u: (rbac.ROLES[u["role"]].level, u["id"]))
    items = [_item(u, c, um, last, sess) for u in us]
    rbac.audit(_con, c, "akkauntlar: ro'yxat", RES, True, f"{len(items)} ta akkaunt")
    admin = c.role.key == ADMIN
    roles = [{"key": k, "title": r.title, "level": r.level, "scope": r.scope, "assignable": admin and k not in NOT_ASSIGNABLE,
              "default_unit": _default_unit(k) if r.scope in ("institut",) else ""} for k, r in rbac.ACTIVE_ROLES.items()]
    return {"can_edit": admin, "demo": demo_mode() and admin, "me": c.user["id"], "items": items, "roles": roles,
            "units": [{"key": x["key"], "name": x["name"], "group": x["group"]} for x in _units()],
            "counts": {"total": len(items), "active": sum(i["active"] for i in items), "inactive": sum(not i["active"] for i in items),
                       "telegram": sum(i["telegram"] for i in items), "locked": sum(i["locked_min"] > 0 for i in items)}}

# ---------------------------------------------------------------------------------------------
# Yaratish va tahrirlash
# ---------------------------------------------------------------------------------------------
class AccountIn(BaseModel):
    position: str | None = None
    person: str | None = None
    role: str | None = None
    unit: str | None = None

def _clean(v, field, label, required=False, mx=120) -> str:
    v = re.sub(r"\s+", " ", str(v or "")).strip()
    if required and len(v) < 2: _bad(f"{label} kiritilsin", field)
    if len(v) > mx: _bad(f"{label} juda uzun (ko'pi bilan {mx} belgi)", field)
    if ":" in v: _bad(f"{label}da «:» belgisi bo'lmasin", field)
    return v

def _full(position, person) -> str:
    return f"{position}: {person}" if person else position

@router.post("/api/accounts")
def create_account(body: AccountIn, request: Request, response: Response):
    c = C(request, True, "yaratish", f"{body.position or ''} · {body.role or ''}")
    role = (body.role or "").strip()
    if role in NOT_ASSIGNABLE:
        _deny(c, "yaratish", f"rol {role}", f"«{rbac.ROLES[role].title}» lavozimini bu sahifadan berib bo'lmaydi — faqat server administratori (CLI)")
    _check_role(role, "Lavozim (rol) tanlansin")
    pos = _clean(body.position, "position", "Lavozim nomi", required=True)
    person = _clean(body.person, "person", "F.I.Sh.")
    unit, extra = _resolve_unit(role, body.unit or "")
    pw, code = temp_password(), _link_code()
    full = _full(pos, person)
    cols = {"full_name": full, "role": role, "unit": unit, "link_code": code, "pin": rbac.hash_password(pw), "active": 1,
            "created_at": _now(), "created_by": c.user["id"], **extra}
    cur = _con.execute(f"INSERT INTO users({','.join(cols)}) VALUES({','.join('?' * len(cols))})", tuple(cols.values()))
    _con.commit()
    rbac.audit(_con, c, "akkauntlar: yaratildi", RES, True, f"#{cur.lastrowid} {full} · rol {role} · bo'lim {unit}")
    response.headers["Cache-Control"] = "no-store"
    return {"ok": True, "id": cur.lastrowid, "password": pw, "link_code": code,
            "message": "Akkaunt yaratildi. Vaqtinchalik parol faqat hozir ko'rsatiladi — xodimga xavfsiz yo'l bilan yetkazing."}

@router.post("/api/accounts/{uid}/update")
def update_account(uid: int, body: AccountIn, request: Request):
    c = C(request, True, "tahrirlash", f"#{uid}")
    u = _target(uid)
    if u["id"] == c.user["id"]: _deny(c, "tahrirlash", _tag(u), "O'z akkauntingiz lavozimi va bo'limini o'zgartira olmaysiz")
    if u["role"] in PROTECTED:
        _deny(c, "tahrirlash", _tag(u), "Rahbariyat va AT boshlig'i akkaunti faqat server administratori (CLI) orqali o'zgartiriladi")
    role = (body.role or u["role"]).strip()
    if role != u["role"] and role in NOT_ASSIGNABLE:
        _deny(c, "rolni o'zgartirish", f"{_tag(u)} → {role}", f"«{rbac.ROLES[role].title}» lavozimini bu sahifadan berib bo'lmaydi — faqat server administratori (CLI)")
    _check_role(role, "Lavozim (rol) noto'g'ri", u["role"])
    pos = _clean(body.position if body.position is not None else _pos(u["full_name"]), "position", "Lavozim nomi", required=True)
    person = _clean(body.person if body.person is not None else _short(u["full_name"]), "person", "F.I.Sh.")
    unit_in = body.unit if body.unit is not None else ("" if role != u["role"] else (u.get("unit") or ""))
    unit, extra = _resolve_unit(role, unit_in, u)
    full = _full(pos, person)
    ch = []
    if full != u["full_name"]: ch.append(f"nom: «{u['full_name']}» → «{full}»")
    if role != u["role"]: ch.append(f"rol: {u['role']} → {role}")
    if unit != (u.get("unit") or ""): ch.append(f"bo'lim: {u.get('unit') or '—'} → {unit}")
    if not ch: return {"ok": True, "changed": False, "message": "O'zgarish yo'q"}
    cols = {"full_name": full, "role": role, "unit": unit, **extra}
    _con.execute(f"UPDATE users SET {', '.join(k + '=?' for k in cols)} WHERE id=?", (*cols.values(), uid))
    if _short(full) != _short(u["full_name"]):     # ism o'zgardi: bog'lanmagan akkaunt yangi ism bo'yicha boshqa xodimning yozuvlariga ulanmaydi
        from . import staff_absence as SA
        SA.lock_user_link(_con, uid)
    _con.commit()
    n = SS.revoke_user(_con, uid) if role != u["role"] else 0      # rol o'zgarsa — eski ruxsatli sessiyalar yopiladi
    rbac.audit(_con, c, "akkauntlar: tahrirlandi", RES, True, f"#{uid} · " + " · ".join(ch) + (f" · sessiyalar yopildi: {n}" if n else ""))
    return {"ok": True, "changed": True, "message": "Saqlandi" + (" · rol o'zgargani uchun sessiyalari yopildi" if role != u["role"] else "")}

# ---------------------------------------------------------------------------------------------
# Amallar
# ---------------------------------------------------------------------------------------------
ACTIONS = {"reset-password": "parolni tiklash", "demo-password": "sinov parolini tiklash", "unlock": "blokdan chiqarish",
           "revoke": "sessiyalarni yopish", "unlink-telegram": "Telegram'ni uzish", "deactivate": "faolsizlantirish", "activate": "faollashtirish"}

@router.post("/api/accounts/{uid}/{action}")
def account_action(uid: int, action: str, request: Request, response: Response):
    if action not in ACTIONS: raise HTTPException(404)
    label = ACTIONS[action]
    c = C(request, True, label, f"#{uid}")
    u = _target(uid); me = u["id"] == c.user["id"]; tag = _tag(u)
    if me and action in ("reset-password", "demo-password"):
        _deny(c, label, tag, "O'z parolingizni profil menyusidagi «Parolni o'zgartirish» oynasida almashtiring")
    if me and action in ("deactivate", "activate"):
        _deny(c, label, tag, "O'z akkauntingizni faolsizlantira olmaysiz")
    if action in ("deactivate", "activate") and u["role"] in PROTECTED:
        _deny(c, label, tag, "Rahbariyat va AT boshlig'i akkaunti holati faqat server administratori (CLI) orqali o'zgartiriladi")

    if action == "reset-password":
        pw = temp_password(); h = rbac.hash_password(pw)
        tg = rbac.set_password(_con, uid, h)       # parol + Telegram ulanishi uziladi (eski parol bilan ulangan bot ishlamay qoladi)
        n = SS.revoke_user(_con, uid); SS.LOGIN_USER.reset(uid)
        rbac.audit(_con, c, "akkauntlar: parol tiklandi", RES, True, f"{tag} · vaqtinchalik parol · sessiyalar yopildi: {n}" + (" · Telegram uzildi" if tg else ""))
        response.headers["Cache-Control"] = "no-store"
        return {"ok": True, "password": pw, "revoked": n, "telegram_unlinked": tg,
                "message": "Yangi vaqtinchalik parol faqat hozir ko'rsatiladi. Xodim kirgach, uni «Parolni o'zgartirish» oynasida almashtirsin."
                           + (" Telegram ulanishi uzildi — xodim botga kod va yangi parolni qayta yuboradi." if tg else "")}
    if action == "demo-password":
        if not demo_mode():
            rbac.audit(_con, c, f"akkauntlar: {label}", RES, False, f"{tag} · sinov rejimi o'chirilgan")
            _bad("Sinov paroli faqat sinov rejimida tiklanadi (ISFT_CORE_HIDE_DEMO_HINT o'rnatilgan)")
        tg = rbac.set_password(_con, uid, rbac.hash_password(rbac.DEMO_PASSWORD))
        n = SS.revoke_user(_con, uid); SS.LOGIN_USER.reset(uid)
        rbac.audit(_con, c, "akkauntlar: sinov paroli tiklandi", RES, True, f"{tag} · sessiyalar yopildi: {n}" + (" · Telegram uzildi" if tg else ""))
        return {"ok": True, "revoked": n, "telegram_unlinked": tg,
                "message": "Sinov paroli tiklandi. Sessiyalari yopildi." + (" Telegram ulanishi uzildi." if tg else "")}
    if action == "unlock":
        was = SS.LOGIN_USER.wait_min(uid)
        SS.LOGIN_USER.reset(uid)
        try:
            from . import extras as XT
            XT.PW_LIMIT.reset(uid)
        except Exception: pass
        rbac.audit(_con, c, "akkauntlar: blokdan chiqarildi", RES, True, f"{tag} · {'blok edi: ' + str(was) + ' daq' if was else 'blok yo‘q edi'}")
        return {"ok": True, "message": "Kirish urinishlari cheklovi tozalandi" if was else "Akkaunt bloklanmagan edi — cheklov hisoblagichi tozalandi"}
    if action == "revoke":
        n = SS.revoke_user(_con, uid, keep_tok=request.cookies.get("sid") if me else None)
        rbac.audit(_con, c, "akkauntlar: sessiyalar yopildi", RES, True, f"{tag} · {n} ta")
        return {"ok": True, "revoked": n, "message": f"{n} ta sessiya yopildi" if n else "Ochiq sessiya yo'q edi"}
    if action == "unlink-telegram":
        had = u.get("telegram_id")
        _con.execute("UPDATE users SET telegram_id=NULL WHERE id=?", (uid,)); _con.commit()
        rbac.audit(_con, c, "akkauntlar: Telegram uzildi", RES, True, f"{tag}" + ("" if had else " · ulanmagan edi"))
        return {"ok": True, "message": "Telegram uzildi" if had else "Telegram ulanmagan edi"}
    if action == "deactivate":
        if u.get("active") == 0: return {"ok": True, "message": "Akkaunt allaqachon faol emas"}
        _con.execute("UPDATE users SET active=0, telegram_id=NULL WHERE id=?", (uid,)); _con.commit()
        n = SS.revoke_user(_con, uid)
        rbac.audit(_con, c, "akkauntlar: faolsizlantirildi", RES, True, f"{tag} · sessiyalar yopildi: {n}" + (" · Telegram uzildi" if u.get("telegram_id") else ""))
        return {"ok": True, "revoked": n, "message": "Akkaunt faolsizlantirildi: kira olmaydi, sessiyalari yopildi"}
    # activate
    if u["role"] in rbac.LEGACY_ROLES:   # bekor qilingan lavozim (dekan) — avval boshqa lavozim berilsin
        rbac.audit(_con, c, f"akkauntlar: {label}", RES, False, f"{tag} · lavozim bekor qilingan")
        _bad(f"«{rbac.ROLES[u['role']].title}» — avval akkauntga amaldagi lavozim bering")
    if u.get("active") != 0: return {"ok": True, "message": "Akkaunt allaqachon faol"}
    _con.execute("UPDATE users SET active=1 WHERE id=?", (uid,)); _con.commit()
    rbac.audit(_con, c, "akkauntlar: faollashtirildi", RES, True, tag)
    return {"ok": True, "message": "Akkaunt qayta faollashtirildi"}
