"""«Mening vazifalarim» — xodim shaxsan bajarishi kerak bo'lgan hamma ish bitta ro'yxatda.

Manbalar (yangi jadval yo'q — hammasi mavjud modullardan, ularning RBAC qoidalari bilan):
  * majlis — majlis topshiriqlari (services.tasks_list → extras._visible_tasks): menga/bo'limimga, bajarilmagan;
             rektor va kotib uchun — institut bo'yicha muddati o'tganlar nazorati (bitta jamlangan qator);
             kotib uchun — tasdiqlanmagan bayonnoma qoralamalari.
  * portal — menga biriktirilgan xatlar, bo'lim rahbari uchun biriktirilmagan kelgan xatlar (portal.reminders_for + muddatsizlari),
             men yuborgan va muddatida javob kelmagan xatlar, men qo'ygan va ijrosi tugamagan rezolyutsiyalar.
  * markaz — Talabalar markazi navbati (student_ops: faqat o'z lavozimimga tushgan ochiq topshiriqlar, ko'lam _task_scope_sql bo'yicha);
             katta navbat tur bo'yicha bitta qatorga jamlanadi.
  * hujjat — imzo kutayotgan buyruq loyihalari (faqat rektor imzolaydi — documents.py bilan bir xil).
  * agent  — AI agent takliflari, tasdiqlash huquqi bo'lsa (agent_hub.can_approve); 3 tadan ko'p bo'lsa jamlanadi.
Havolalar (`link`) bildirishnomalar markazidagi bilan bir xil ko'rinishda — static/extras.js openLink() ochadi.
"""
import datetime as dt, json
from fastapi import APIRouter, Request
from . import db, rbac
from .rbac import Ctx, AccessDenied

router = APIRouter()
_con = None
_ctx = None

def bind(con, ctx_fn):
    global _con, _ctx
    _con, _ctx = con, ctx_fn

SOURCES = ("majlis", "portal", "markaz", "hujjat", "agent", "sillabus")
OPS_ROLES = ("call_center", "tyutor", "talabalar", "sirtqi")     # Talabalar markazida o'z navbati bor lavozimlar (student_ops._can_act; sirtqi — sirtqi talabalar xatlari)
OPS_LIST_MAX = 5                                      # bundan ko'p bo'lsa — tur bo'yicha jamlanadi
DOC_LIST_MAX = 12

def _today() -> dt.date:
    from . import services as S
    return S.TODAY

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
    now, td = dt.datetime.now().replace(microsecond=0).isoformat(timespec="seconds"), _today().isoformat()
    w = f"{OPSM._task_scope_sql(c)} AND t.assignee_role=? AND t.status='yangi'"
    act = f"COALESCE(t.planned_on,'') <= '{td}'"          # keyingi kunlarga rejalashtirilgan qo'ng'iroqlar bugungi ish emas
    rows = db.rows(_con, f"""SELECT t.kind, COUNT(*) n, SUM(t.due_at < ?) late, MIN(t.due_at) first, SUM(NOT ({act})) later
                             FROM ops_tasks t WHERE {w} GROUP BY t.kind ORDER BY late DESC, n DESC""", (now, k))
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
        first = db.one(_con, f"SELECT MIN(t.due_at) d FROM ops_tasks t WHERE {w} AND t.kind=? AND {act}", (k, r["kind"]))["d"]
        out.append(_item("markaz", "navbat", f"oq{r['kind']}", f"Talabalar markazi: {n:,} ta {kt}".replace(",", " ") + (f" ({late:,} kechikkan)".replace(",", " ") if late else ""),
                         " · ".join(x for x in [OPSM.ROLE_T.get(k, "Mening navbatim") + " navbati",
                                                f"yana {r['later']:,} tasi keyingi kunlarga rejalashtirilgan".replace(",", " ") if r["later"] else ""] if x),
                         first, {"view": "ops", "tab": "navbat", "kind": r["kind"]}, "menga" if k != "talabalar" else "bolimga",
                         f"{n} ta ochiq", "high" if late else None, n, icon="users"))
    return out

# ---------------------------------------------------------------------------------------------
# 4. Imzo kutayotgan hujjatlar (faqat rektor — documents.py: "Buyruqlarni faqat rektor imzolaydi")
# ---------------------------------------------------------------------------------------------
def _hujjat(c: Ctx) -> list[dict]:
    if c.role.key != "rektor": return []
    rows = db.rows(_con, "SELECT id, reg_no, title, holder, creator_role, created_at FROM documents WHERE status='loyiha' ORDER BY id")
    out = []
    for r in rows[:DOC_LIST_MAX]:
        role = rbac.ROLES.get(r["creator_role"])
        out.append(_item("hujjat", "imzo", f"dc{r['id']}", f"Imzo kutilmoqda: {r['title']}",
                         " · ".join(x for x in [r["reg_no"], r["holder"], f"loyihalagan: {role.title}" if role else "", _dmy(r["created_at"])] if x),
                         None, {"view": "documents", "reg": r["reg_no"]}, "menga", "loyiha", "mid", icon="pen"))
    if len(rows) > DOC_LIST_MAX:
        out.append(_item("hujjat", "imzo", "dcall", f"Yana {len(rows) - DOC_LIST_MAX} ta hujjat imzo kutmoqda", "Hujjatlar markazi → reyestr", None,
                         {"view": "documents"}, "menga", "loyiha", "mid", len(rows) - DOC_LIST_MAX, icon="file"))
    return out

# ---------------------------------------------------------------------------------------------
# 5. AI agentlar takliflari (extras.notifications bilan bir xil shart)
# ---------------------------------------------------------------------------------------------
def _agent(c: Ctx) -> list[dict]:
    from . import agent_hub as AH
    if not AH.can_view_page(c) or c.role.key == "kengash": return []
    props = [r for r in db.rows(_con, "SELECT id, agent, title, created_at FROM agent_actions WHERE status='taklif' ORDER BY id")
             if AH.can_approve(c, r["agent"])]
    name = lambda a: AH.AG.get(a, {}).get("name", a)
    if len(props) <= 3:
        return [_item("agent", "taklif", f"ag{r['id']}", f"AI agent taklifi: {r['title']}", f"{name(r['agent'])} · tasdiqingizni kutmoqda · {_dmy(r['created_at'])}",
                      None, {"view": "agents"}, "menga", "taklif", "mid", icon="spark") for r in props]
    names = sorted({name(r["agent"]) for r in props})
    return [_item("agent", "taklif", "agall", f"AI agentlar: {len(props)} ta taklif tasdiqingizni kutmoqda",
                  " · ".join(names[:3]) + (f" va yana {len(names) - 3}" if len(names) > 3 else ""), None, {"view": "agents"},
                  "menga", "taklif", "mid", len(props), icon="spark")]

# ---------------------------------------------------------------------------------------------
# Yig'ish
# ---------------------------------------------------------------------------------------------
def _sillabus(c: Ctx) -> list[dict]:   # O'quv dasturlari (app/syllabus.py): biriktirish, tekshiruv, kelishuv, kafedra so'rovlari
    from . import syllabus as SY
    return SY.mywork_items(c, _item)

COLLECT = [("majlis", _majlis), ("portal", _portal), ("markaz", _markaz), ("hujjat", _hujjat), ("agent", _agent), ("sillabus", _sillabus)]
_PRIO_ORDER = {"high": 0, "mid": 1, "low": 2}
_BUCKET_ORDER = {"overdue": 0, "today": 1, "week": 2, "later": 3, "none": 4}

def _due_key(v) -> str:
    s = str(v or "").replace(" ", "T")[:19]
    return s + "T23:59:59" if len(s) == 10 else s

def collect(c: Ctx) -> dict:
    today, now = _today(), dt.datetime.now()
    items, errors = [], []
    for key, fn in COLLECT:
        try:
            items += fn(c)
        except AccessDenied:
            pass                                  # ruxsat yo'q — manba umuman ko'rsatilmaydi
        except Exception as e:                    # bitta manbadagi xato butun sahifani yiqitmasin
            print(f"mywork.{key}:", repr(e)); errors.append(key)
    for it in items:
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
              "by_source": {k: v for k, v in by.items() if v}}
    return {"items": items, "counts": counts, "today": today.isoformat(), "now": now.replace(microsecond=0).isoformat(timespec="seconds"),
            "partial": errors}

@router.get("/api/mywork")
def api_mywork(request: Request):
    return collect(_ctx(request))
