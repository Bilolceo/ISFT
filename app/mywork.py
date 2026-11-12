"""«Mening vazifalarim» — xodim shaxsan bajarishi kerak bo'lgan hamma ish bitta ro'yxatda.

Manbalar (yangi jadval yo'q — hammasi mavjud modullardan, ularning RBAC qoidalari bilan):
  * majlis — majlis topshiriqlari (services.tasks_list → extras._visible_tasks): menga/bo'limimga, bajarilmagan;
             rektor va kotib uchun — institut bo'yicha muddati o'tganlar nazorati (bitta jamlangan qator);
             kotib uchun — tasdiqlanmagan bayonnoma qoralamalari.
  * portal — menga biriktirilgan xatlar, bo'lim rahbari uchun biriktirilmagan kelgan xatlar (portal.reminders_for + muddatsizlari),
             men yuborgan va muddatida javob kelmagan xatlar, men qo'ygan va ijrosi tugamagan rezolyutsiyalar.
  * markaz — Talabalar markazi navbati (student_ops: faqat o'z lavozimimga tushgan ochiq topshiriqlar, ko'lam _task_scope_sql bo'yicha);
             katta navbat tur bo'yicha bitta qatorga jamlanadi.
  * buyruq — «Buyruqlar» (app/orders.py — talabalar va xodimlar buyruqlarining yagona joyi): rektor — imzo kutayotganlar, o'quv prorektori —
             kelishuv kutayotganlar, Registrator ofisi / Kadrlar — qaytarilgan loyihalar, Devonxona — jurnalga olinmagan imzolanganlar (orders.pending).
  * murojaat — «Murojaatlar va nosozliklar»: menga biriktirilgan murojaatlar va bo'limim navbatida hech kim olmaganlari (service.my_queue);
             xo'jalik — ochiq nosozliklar navbati; xarid — yangi xarid so'rovlari.
  * xodim  — xodimlar ta'tili: kafedra mudiri — o'rinbosarsiz darslar, kadrlar — buyrug'i yo'q mehnat ta'tillari (staff_absence.mywork_items).
  * agent  — AI agent takliflari, tasdiqlash huquqi bo'lsa (agent_hub.can_approve) — har biri alohida qator (agentlar sahifasi bilan teng).
  * sillabus — O'quv dasturlari (app/syllabus.py).
Har bir element havolasi aniq obyektni ochadi (buyruq, murojaat, yo'qlik, taklif, topshiriq). Menyudagi raqam = shu sahifadagi «Jami ish».
Havolalar (`link`) bildirishnomalar markazidagi bilan bir xil ko'rinishda — static/extras.js openLink() ochadi.
"""
import datetime as dt, json
from fastapi import APIRouter, Request
from . import clock
from . import db, rbac
from .rbac import Ctx, AccessDenied

router = APIRouter()
_con = None
_ctx = None

def bind(con, ctx_fn):
    global _con, _ctx
    _con, _ctx = con, ctx_fn
    from . import pending as PD; PD.bind(con)   # yangi modullar (moliya, kadrlar, ilmiy, xalqaro, yoshlar, amaliyot, harakat, tekshiruv, talaba)

SOURCES = ("majlis", "portal", "markaz", "buyruq", "murojaat", "xodim", "agent", "sillabus",
           "moliya", "kadrlar", "ilmiy", "xalqaro", "yoshlar", "amaliyot", "harakat", "tekshiruv", "talaba", "devon", "qabul", "rejalar", "it_req", "masofaviy", "testbank", "paket")
OPS_ROLES = ("call_center", "tyutor", "talabalar", "sirtqi")     # Talabalar markazida o'z navbati bor lavozimlar (student_ops._can_act; sirtqi — sirtqi talabalar xatlari)
OPS_LIST_MAX = 5                                      # bundan ko'p bo'lsa — tur bo'yicha jamlanadi
DOC_LIST_MAX = 12
QUEUE_LIST_MAX = 5                                    # bo'lim navbati shundan ko'p bo'lsa — bitta jamlangan qator

def _today() -> dt.date:
    from . import services as S
    return clock.today()

def _short(name): return (name or "").split(":", 1)[1].strip() if ":" in (name or "") else (name or "")
def _dmy(v) -> str:
    v = str(v or "")[:10]
    return f"{v[8:10]}.{v[5:7]}.{v[:4]}" if len(v) == 10 and v[4] == "-" else v

def _parse_due(v) -> tuple[dt.date | None, dt.datetime | None]:
    """'2026-11-12' yoki '2026-11-12T18:00:00' → (sana, aniq vaqt yoki None)."""
    s = str(v or "").strip().replace(" ", "T")
    if not s: return None, None
    try:
        if "T" in s:
            t = dt.datetime.fromisoformat(s[:19]); return t.date(), t
        return dt.date.fromisoformat(s[:10]), None
    except ValueError:
        return None, None

def _bucket(due, today: dt.date, now: dt.datetime) -> tuple[str, bool]:
    d, t = _parse_due(due)
    if not d: return "none", False
    over = (t < now) if t else (d < today)
    if over: return "overdue", True
    days = (d - today).days
    return ("today" if days <= 0 else "week" if days <= 7 else "later"), False

def _item(source, kind, iid, title, sub, due, link, who, status="", prio=None, count=None, icon=None) -> dict:
    return {"id": iid, "source": source, "kind": kind, "title": title, "sub": sub, "due": due or None, "status": status, "who": who,
            "link": link, "priority": prio, "count": count, "icon": icon}

# ---------------------------------------------------------------------------------------------
# 1. Majlis topshiriqlari
# ---------------------------------------------------------------------------------------------
MULTI_UNIT = {"kafedra": "kafedra", "oqituvchi": "kafedra", "tyutor": "fakultet"}

def _core(name: str) -> str:
    n = (name or "").strip()
    for suf in (" kafedrasi", " fakulteti tyutorlari", " fakulteti"):
        if n.endswith(suf): return n[: -len(suf)]
    return n

def _other_unit(c: Ctx, t: dict) -> bool:
    """Bir nechta kafedra/fakultetda bir xil lavozim bor: topshiriq matnida boshqa kafedra/fakultet nomi bo'lsa — u menga emas.
    (tasks_list rol bo'yicha 'mine' beradi; "Kafedra mudiri (Buxgalteriya hisobi)" boshqa kafedra mudiriga ko'rinmasin.)"""
    grp = MULTI_UNIT.get(c.role.key)
    if not grp or t.get("assignee_user") == c.user["id"]: return False
    from . import portal as PT
    me = PT.my_unit(c); hay = f"{t.get('assignee') or ''} {t.get('unit') or ''}".lower()
    hits = [u["key"] for u in PT.units(_con) if u.get("group") == grp and _core(u["name"]).lower() in hay]
    return bool(hits) and me not in hits

def _majlis(c: Ctx) -> list[dict]:
    from . import extras as XT
    out = []
    tl = XT._visible_tasks(c)          # ruxsat yo'q bo'lsa — [] (tasks_list AccessDenied)
    uid = c.user["id"]
    for t in tl:
        if not t.get("mine") or t["status"] in ("bajarildi", "qoralama") or _other_unit(c, t): continue
        due = t.get("due_at") or t.get("due")
        sub = " · ".join(x for x in [t.get("meeting") or "Majlis", t.get("assignee"), t.get("status"),
                                      t.get("due_text") if not due and t.get("due_text") else ""] if x)
        out.append(_item("majlis", "topshiriq", f"mt{t['id']}", t["text"], sub, due, XT._task_link(t),
                         "menga" if t.get("assignee_user") == uid else "bolimga", t["status"], icon="tasks"))
    if c.role.key in ("rektor", "kotib") and tl:      # ijro nazorati — boshqalarning muddati o'tgan topshiriqlari (bitta qator)
        over = [t for t in tl if t.get("overdue") and not t.get("mine")]
        if over:
            first = min((str(t.get("due_at") or t.get("due")) for t in over))
            names = sorted({str(t.get("assignee") or "") for t in over if t.get("assignee")})
            out.append(_item("majlis", "nazorat", "mtall", f"Ijro nazorati: {len(over)} ta topshiriq muddati o'tgan",
                             " · ".join(names[:4]) + (f" va yana {len(names) - 4}" if len(names) > 4 else ""), first, {"view": "tasks"},
                             "nazorat", "muddati o'tgan", "high", len(over), icon="alert"))
    if c.role.key == "kotib" and c.can(rbac.TASKS):    # decisions._secretary: bayonnomani kotib tasdiqlaydi
        for m in db.rows(_con, "SELECT id, title, date FROM meetings WHERE status='qoralama' ORDER BY id DESC LIMIT 10"):
            out.append(_item("majlis", "bayonnoma", f"mq{m['id']}", f"Bayonnoma qoralamasini tasdiqlang: {m['title']}",
                             f"Majlis {_dmy(m['date'])} · topshiriqlar bo'limlarga tasdiqlangandan keyin tushadi", None,
                             {"view": "tasks", "meeting": m["id"]}, "menga", "qoralama", "mid", icon="pen"))
    from . import directives as DIR   # topshiriqlar: natija qabulimni kutayotganlar (+ TASKS ruxsatisiz ijrochiga berilganlar)
    out += DIR.mywork_items(c)
    return out

# ---------------------------------------------------------------------------------------------
# 2. Portal: xatlar va rezolyutsiyalar
# ---------------------------------------------------------------------------------------------
def _portal(c: Ctx) -> list[dict]:
    from . import portal as PT
    me, uid = PT.my_unit(c), c.user["id"]
    um = PT.unit_map(_con)
    head = PT.head_user(_con, me) == uid
    out, seen = [], set()
    rem = PT.reminders_for(_con, c.user, horizon=3650)
    # muddatsiz xatlar ham ish — reminders_for faqat muddatlilarini beradi (shart aynan o'sha: menga / biriktirilmagan + bo'lim rahbari)
    nodue = db.rows(_con, f"""SELECT t.id, t.ref_no, t.subject, t.from_unit, r.assignee FROM portal_recipients r JOIN portal_threads t ON t.id=r.thread_id
                               WHERE r.unit=? AND t.status='ochiq' AND r.status IN {PT._PEND_SQL} AND {PT._EFF_DUE} IS NULL ORDER BY t.id""", (me,))
    for r in nodue:
        who = "menga" if r["assignee"] == uid else "bolimga" if not r["assignee"] and head else None
        if who: rem.append({"thread_id": r["id"], "ref_no": r["ref_no"], "subject": r["subject"], "due": None, "who": who, "from_unit": r["from_unit"]})
    ids = sorted({it["thread_id"] for it in rem if it["who"] in ("menga", "bolimga", "yuborgan")})
    meta, mine, pend = {}, {}, {}
    if ids:
        ph = ",".join("?" * len(ids))
        meta = {r["id"]: r for r in db.rows(_con, f"SELECT id, kind, priority FROM portal_threads WHERE id IN ({ph})", ids)}
        mine = {r["thread_id"]: r for r in db.rows(_con, f"SELECT thread_id, status FROM portal_recipients WHERE unit=? AND thread_id IN ({ph})", (me, *ids))}
        pend = {r["thread_id"]: r["n"] for r in db.rows(_con, f"""SELECT thread_id, COUNT(*) n FROM portal_recipients
                                                                   WHERE thread_id IN ({ph}) AND status IN {PT._PEND_SQL} GROUP BY thread_id""", ids)}
    for it in rem:
        who, tid = it["who"], it["thread_id"]
        if who == "nazorat" or (who, tid) in seen: continue     # rezolyutsiyalar pastda — har biri alohida
        seen.add((who, tid))
        m = meta.get(tid) or {}
        prio = m.get("priority")
        kind_t = PT.KINDS.get(m.get("kind"), "Xat")
        if who == "yuborgan":
            n = pend.get(tid, 0)
            out.append(_item("portal", "javob_kutish", f"py{tid}", f"Javob kelmadi: «{it['subject']}»",
                             " · ".join(x for x in [f"{n} ta bo'lim javob bermagan" if n else "", it["ref_no"]] if x), it["due"],
                             {"view": "portal", "thread": tid}, "yuborgan", "javob kutilmoqda", icon="mail"))
            continue
        st = (mine.get(tid) or {}).get("status") or "yangi"
        if m.get("kind") == "xabarnoma" and st != "yangi" and not it["due"]: continue   # o'qilgan, muddatsiz xabarnoma — ish emas
        out.append(_item("portal", "xat", f"p{who[0]}{tid}", it["subject"],
                         " · ".join(x for x in [PT.WHO_LABEL[who].capitalize(), f"{kind_t} · {PT._uname(um, it.get('from_unit'))}dan", it["ref_no"],
                                                PT.PRIOS.get(prio, "") if prio in ("muhim", "shoshilinch") else ""] if x),
                         it["due"], {"view": "portal", "thread": tid}, who, st,
                         "high" if prio == "shoshilinch" else None, icon="inbox" if who == "bolimga" else "mail"))
    # men qo'ygan rezolyutsiyalar — ijrosi hali tugamagan (portal.counts dagi "control" sharti, muallif — aynan shu xodim)
    for z in db.rows(_con, f"""SELECT z.id, z.thread_id, z.text, z.due, z.units, t.subject, t.ref_no FROM portal_resolutions z
                               JOIN portal_threads t ON t.id=z.thread_id
                               WHERE z.author_id=? AND z.state='nazoratda' AND t.status='ochiq'
                                 AND EXISTS(SELECT 1 FROM json_each(z.units) j JOIN portal_recipients r ON r.thread_id=z.thread_id AND r.unit=j.value
                                            WHERE r.status IN {PT._PEND_SQL}) ORDER BY z.id""", (uid,)):
        us = json.loads(z["units"] or "[]")
        left = [r["unit"] for r in db.rows(_con, f"SELECT unit FROM portal_recipients WHERE thread_id=? AND status IN {PT._PEND_SQL}", (z["thread_id"],)) if r["unit"] in us]
        names = [PT._uname(um, u) for u in left]
        txt = " ".join((z["text"] or "").split())
        out.append(_item("portal", "rezolyutsiya", f"pz{z['id']}", f"Rezolyutsiya ijrosi: «{z['subject']}»",
                         " · ".join(x for x in [f"«{txt[:70]}{'…' if len(txt) > 70 else ''}»" if txt else "",
                                                "Kutilmoqda: " + ", ".join(names[:3]) + (f" va yana {len(names) - 3}" if len(names) > 3 else ""), z["ref_no"]] if x),
                         z["due"], {"view": "portal", "thread": z["thread_id"]}, "nazorat", "nazoratda", icon="flag"))
    return out

# ---------------------------------------------------------------------------------------------
# 3. Talabalar markazi navbati
# ---------------------------------------------------------------------------------------------
def _markaz(c: Ctx) -> list[dict]:
    from . import student_ops as OPSM
    k = c.role.key
    if k not in OPS_ROLES or not c.can(rbac.OPS): return []
    now, td = clock.now().replace(microsecond=0).isoformat(timespec="seconds"), _today().isoformat()
    w = f"{OPSM._task_scope_sql(c)} AND t.assignee_role=? AND t.status='yangi'"
    act = f"COALESCE(t.planned_on,'') <= '{td}'"          # keyingi kunlarga rejalashtirilgan qo'ng'iroqlar bugungi ish emas
    # ko'lam sharti talaba jadvaliga (s) ham murojaat qilishi mumkin (masalan, tyutor — o'z guruhlari) — har doim bog'lanadi
    rows = db.rows(_con, f"""SELECT t.kind, COUNT(*) n, SUM(t.due_at < ?) late, MIN(t.due_at) first, SUM(NOT ({act})) later
                             FROM ops_tasks t JOIN students s ON s.id=t.student_id WHERE {w} GROUP BY t.kind ORDER BY late DESC, n DESC""", (now, k))
    total = sum(r["n"] - (r["later"] or 0) for r in rows)
    out = []
    if 0 < total <= OPS_LIST_MAX:
        for t in db.rows(_con, f"""SELECT t.id, t.kind, t.title, t.due_at, t.level, t.student_id, s.full_name, g.name grp FROM ops_tasks t
                                   JOIN students s ON s.id=t.student_id LEFT JOIN groups_ g ON g.id=s.group_id
                                   WHERE {w} AND {act} ORDER BY t.due_at""", (k,)):
            out.append(_item("markaz", "talaba", f"ot{t['id']}", t["title"] or OPSM.KINDS.get(t["kind"], t["kind"]),
                             " · ".join(x for x in [t["full_name"], t["grp"], OPSM.LEVELS.get(t["level"], "")] if x), t["due_at"],
                             {"view": "ops", "student": t["student_id"]}, "menga" if k != "talabalar" else "bolimga", "yangi",
                             "high" if (t["level"] or 0) >= 3 else None, icon="users"))
        return out
    for r in rows:
        n = r["n"] - (r["later"] or 0)
        if n <= 0: continue
        late = r["late"] or 0
        kt = OPSM.KINDS.get(r["kind"], r["kind"]).lower()
        first = db.one(_con, f"SELECT MIN(t.due_at) d FROM ops_tasks t JOIN students s ON s.id=t.student_id WHERE {w} AND t.kind=? AND {act}", (k, r["kind"]))["d"]
        out.append(_item("markaz", "navbat", f"oq{r['kind']}", f"Talabalar markazi: {n:,} ta {kt}".replace(",", " ") + (f" ({late:,} kechikkan)".replace(",", " ") if late else ""),
                         " · ".join(x for x in [OPSM.ROLE_T.get(k, "Mening navbatim") + " navbati",
                                                f"yana {r['later']:,} tasi keyingi kunlarga rejalashtirilgan".replace(",", " ") if r["later"] else ""] if x),
                         first, {"view": "ops", "tab": "navbat", "kind": r["kind"]}, "menga" if k != "talabalar" else "bolimga",
                         f"{n} ta ochiq", "high" if late else None, n, icon="users"))
    return out

# ---------------------------------------------------------------------------------------------
# 4. Buyruqlar: imzo, kelishuv, qaytarilgan loyiha, devonxona jurnali (app/orders.py — yagona joy)
# ---------------------------------------------------------------------------------------------
def _buyruq(c: Ctx) -> list[dict]:
    from . import orders as ORD
    if c.role.key not in ORD.REG_READ: return []
    pd = ORD.pending(c)
    out = []
    def who_of(p): return p.get("staff_name") if isinstance(p, dict) else None
    for kind, rows, title, status, prio in (("imzo", pd["sign"], "Imzo kutilmoqda", "imzoda", "high"), ("kelishuv", pd["forward"], "Kelishuv kutilmoqda", "kelishuvda", "mid"),
                                            ("qaytarilgan", pd["returned"], "Qaytarilgan loyiha", "qaytarilgan", "mid"),
                                            ("jurnal", pd["register"], "Jurnalga ro'yxatga oling", "imzolangan", "low")):
        for r in rows:
            sub = " · ".join(x for x in [r.get("reg_no") or f"Loyiha #{r['id']}", r["kind_name"], who_of(r["params"]) or (f"{r['count']} ta talaba" if r.get("count") else ""),
                                         f"«{r['returned_note']}»" if kind == "qaytarilgan" and r.get("returned_note") else "",
                                         f"yuborilgan {_dmy(r['submitted_at'])}" if kind in ("imzo", "kelishuv") and r.get("submitted_at") else "",
                                         f"imzolangan {_dmy(r['signed_at'])}" if kind == "jurnal" and r.get("signed_at") else ""] if x)
            out.append(_item("buyruq", kind, f"or{kind[0]}{r['id']}", f"{title}: {r['title']}", sub, None, {"view": "orders", "order": r["id"]},
                             "menga" if kind in ("imzo", "kelishuv", "jurnal") else "bolimga", status, prio, icon="pen" if kind == "imzo" else "file"))
    return out

# ---------------------------------------------------------------------------------------------
# 4b. Murojaatlar va nosozliklar: menga biriktirilgan + bo'limim navbati; xo'jalik nosozliklari; xarid so'rovlari
# ---------------------------------------------------------------------------------------------
def _murojaat(c: Ctx) -> list[dict]:
    from . import service as SV
    out = []
    q = SV.my_queue(_con, c)
    for r in q["mine"]:
        out.append(_item("murojaat", "murojaat", f"rq{r['id']}", f"Murojaat {r['number']}: {(r['text'] or '')[:90]}",
                         " · ".join(x for x in [r["category"], r["unit"], r["status"], r["channel"]] if x), None,
                         {"view": "service", "tab": "requests", "request": r["id"]}, "menga", r["status"], "mid", icon="mail"))
    un = q["unit"]
    if 0 < len(un) <= QUEUE_LIST_MAX:
        for r in un:
            out.append(_item("murojaat", "murojaat", f"rq{r['id']}", f"Murojaat {r['number']}: {(r['text'] or '')[:90]}",
                             " · ".join(x for x in [r["category"], f"{q['unit_name']} navbati — hech kim olmagan", r["channel"]] if x), None,
                             {"view": "service", "tab": "requests", "request": r["id"]}, "bolimga", "yangi", None, icon="inbox"))
    elif un:
        out.append(_item("murojaat", "navbat", "rqall", f"Murojaatlar navbati: {len(un)} ta yangi murojaat",
                         f"{q['unit_name']} · hech kim olmagan · eng eskisi {_dmy(un[0]['created_at'])}", None,
                         {"view": "service", "tab": "requests", "queue": "unit"}, "bolimga", f"{len(un)} ta yangi", "mid", len(un), icon="inbox"))
    if c.role.key == "xojalik" and c.can(rbac.FACILITIES):   # nosozliklar: hali hech kim olmagan (yangi)
        t = db.rows(_con, """SELECT t.id, t.item, t.created_at, r.name room FROM tickets t JOIN rooms r ON r.id=t.room_id
                             WHERE t.status='yangi' ORDER BY t.created_at""")
        if 0 < len(t) <= QUEUE_LIST_MAX:
            for x in t:
                out.append(_item("murojaat", "nosozlik", f"tk{x['id']}", f"Nosozlik: {x['room']} — {x['item']}", f"QR orqali · kelgan {_dmy(x['created_at'])}", None,
                                 {"view": "service", "tab": "facilities", "ticket": x["id"]}, "bolimga", "yangi", None, icon="alert"))
        elif t:
            out.append(_item("murojaat", "navbat", "tkall", f"Nosozliklar navbati: {len(t)} ta yangi", f"eng eskisi {_dmy(t[0]['created_at'])} · «Olindi» bosilmagan",
                             None, {"view": "service", "tab": "facilities"}, "bolimga", f"{len(t)} ta yangi", "mid", len(t), icon="alert"))
    if c.role.key == "xarid" and c.can(rbac.PROCUREMENT):
        for p in db.rows(_con, "SELECT * FROM procurements WHERE status IN ('yangi','ko''rib chiqilmoqda') ORDER BY created_at"):
            out.append(_item("murojaat", "xarid", f"pr{p['id']}", f"Xarid so'rovi X-{p['id']:04d}: {p['item']} ({p['room']})",
                             " · ".join(x for x in [f"{p['qty']} dona", p["status"], (p["text"] or "")[:60]] if x), None,
                             {"view": "service", "tab": "procurement", "procurement": p["id"]}, "menga", p["status"], "mid" if p["status"] == "yangi" else None, icon="file"))
    return out

def _xodim(c: Ctx) -> list[dict]:
    from . import staff_absence as SA
    return SA.mywork_items(c, _item)

# ---------------------------------------------------------------------------------------------
# 5. AI agentlar takliflari (extras.notifications bilan bir xil shart)
# ---------------------------------------------------------------------------------------------
def _agent(c: Ctx) -> list[dict]:
    from . import agent_hub as AH
    if not AH.can_view_page(c) or c.role.key == "kengash": return []
    props = [r for r in db.rows(_con, "SELECT id, agent, title, created_at FROM agent_actions WHERE status='taklif' ORDER BY id")
             if AH.can_approve(c, r["agent"])]
    name = lambda a: AH.AG.get(a, {}).get("name", a)
    # har bir taklif alohida (agentlar sahifasidagi «tasdiqingizni kutmoqda» soni bilan teng; havola aynan shu taklifni ochadi)
    return [_item("agent", "taklif", f"ag{r['id']}", f"AI agent taklifi: {r['title']}", f"{name(r['agent'])} · tasdiqingizni kutmoqda · {_dmy(r['created_at'])}",
                  None, {"view": "agents", "action": r["id"]}, "menga", "taklif", "mid", icon="spark") for r in props]

# ---------------------------------------------------------------------------------------------
# Yig'ish
# ---------------------------------------------------------------------------------------------
def _sillabus(c: Ctx) -> list[dict]:   # O'quv dasturlari (app/syllabus.py): biriktirish, tekshiruv, kelishuv, kafedra so'rovlari
    from . import syllabus as SY
    return SY.mywork_items(c, _item)

COLLECT = [("majlis", _majlis), ("portal", _portal), ("markaz", _markaz), ("buyruq", _buyruq), ("murojaat", _murojaat), ("xodim", _xodim),
           ("agent", _agent), ("sillabus", _sillabus)]
def _pd(fn): return lambda c: fn(c, _item)
from . import pending as _PD
COLLECT += [(k, _pd(f)) for k, f in _PD.ADAPTERS]

SIGN_KINDS = {("buyruq", "imzo"), ("buyruq", "kelishuv")}   # buyruqlar: imzo / kelishuv — «Imzo papkasi»
_PRIO_ORDER = {"high": 0, "mid": 1, "low": 2}
_BUCKET_ORDER = {"overdue": 0, "today": 1, "week": 2, "later": 3, "none": 4}

def _due_key(v) -> str:
    s = str(v or "").replace(" ", "T")[:19]
    return s + "T23:59:59" if len(s) == 10 else s

# Qisqa kesh (xodim bo'yicha): qo'ng'iroqcha har 60 soniyada so'raydi — har safar barcha manbalarni (20+ modul) qayta yig'masin.
# «Mening vazifalarim» sahifasi va bosh sahifa (collect) HAR DOIM yangi hisoblaydi va keshni yangilaydi; qo'ng'iroqcha (extras.notifications →
# collect_cached) keshdan oladi, CACHE_TTL dan eski bo'lsa — qayta yig'adi. Shu sabab ikki joydagi sonlar bitta hisobdan chiqadi.
CACHE_TTL = 75
_CACHE: dict = {}

def collect_cached(c: Ctx, max_age: float = CACHE_TTL) -> dict:
    import time
    hit = _CACHE.get(c.user["id"])
    if hit and hit[1] == c.role.key and time.time() - hit[0] <= max_age: return hit[2]
    return collect(c)

def invalidate(uid=None) -> None:
    _CACHE.pop(uid, None) if uid is not None else _CACHE.clear()

def collect(c: Ctx) -> dict:
    import time
    d = _collect(c)
    if c.channel == "web": _CACHE[c.user["id"]] = (time.time(), c.role.key, d)
    return d

def _collect(c: Ctx) -> dict:
    today, now = _today(), clock.now()
    items, errors = [], []
    for key, fn in COLLECT:
        try:
            items += fn(c)
        except AccessDenied:
            pass                                  # ruxsat yo'q — manba umuman ko'rsatilmaydi
        except Exception as e:                    # bitta manbadagi xato butun sahifani yiqitmasin
            print(f"mywork.{key}:", repr(e)); errors.append(key)
    for it in items:
        if (it["source"], it["kind"]) in SIGN_KINDS: it["sign"] = True
        it.setdefault("sign", False)
        it["bucket"], it["overdue"] = _bucket(it["due"], today, now)
        if not it["priority"]:
            it["priority"] = "high" if it["bucket"] in ("overdue", "today") else "mid" if it["bucket"] == "week" or it["who"] == "nazorat" else "low"
        elif it["bucket"] in ("overdue", "today"):
            it["priority"] = "high"
        d, _ = _parse_due(it["due"])
        it["days"] = (d - today).days if d else None
    items.sort(key=lambda x: (_BUCKET_ORDER[x["bucket"]], _due_key(x["due"]) if x["due"] else "~", _PRIO_ORDER[x["priority"]], SOURCES.index(x["source"]), x["id"]))
    by = {s: sum(1 for it in items if it["source"] == s) for s in SOURCES}
    counts = {"total": len(items), "overdue": sum(it["bucket"] == "overdue" for it in items), "today": sum(it["bucket"] == "today" for it in items),
              "week": sum(it["bucket"] == "week" for it in items), "later": sum(it["bucket"] == "later" for it in items),
              "none": sum(it["bucket"] == "none" for it in items), "units": sum(it.get("count") or 1 for it in items),
              "badge": len(items),   # menyudagi raqam = «Jami ish» (har bir qator — mendan harakat kutayotgan bitta ish yoki jamlangan navbat)
              "by_source": {k: v for k, v in by.items() if v}, "sign": sum(1 for it in items if it.get("sign"))}
    return {"items": items, "counts": counts, "today": today.isoformat(), "now": now.replace(microsecond=0).isoformat(timespec="seconds"),
            "partial": errors}

@router.get("/api/mywork")
def api_mywork(request: Request):
    return collect(_ctx(request))

@router.get("/api/bugun")
def api_bugun(request: Request):
    """Bosh sahifa: «Sizdan kutilmoqda» (shu sahifadagi ro'yxatning eng yaqinlari) + lavozimning o'z sohasidagi ko'rsatkichlar."""
    from . import pending as PD
    c = _ctx(request)
    d = collect(c)
    return {"items": d["items"][:5], "counts": d["counts"], "kpis": PD.bugun(c), "institute": c.role.key in ("rektor", "kengash")}
