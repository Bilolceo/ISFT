"""AI agentlar markazi: ISFT Core ichidagi ixtisoslashgan agentlar, ularning avtonomiya darajasi va inson tasdig'i oqimi.

Tamoyillar:
  * Agent faqat ruxsat etilgan ma'lumotni ko'radi (ichki rektor konteksti, `quiet=True` — faqat jamlangan servislar).
  * Xavfli amal (topshiriq berish, rasmiy eslatma) — faqat inson tasdig'idan keyin (`agent_actions.status='taklif'`).
  * Xavfi past amal (muddatdan oldingi eslatma, ma'lumot xulosasi) — avtomatik, lekin baribir jurnalga yoziladi.
  * Har bir qaror audit jurnalida (rbac.audit, resurs "agents").
  * `scan()` idempotent: har bir amal kaliti sanani o'z ichiga oladi (agent_actions.key UNIQUE).
"""
import datetime as dt, hashlib, json
from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel
from . import db, rbac, services as S
from .rbac import AccessDenied, Ctx, ROLES

router = APIRouter()
_con = None
_ctx = None

RES = "agents"
AGENT_MEETING = "ISFT Core agentlari takliflari (rahbariyat tasdiqlagan)"

LEVELS = {0: "Faqat o'qiydi", 1: "Qoralama tayyorlaydi", 2: "Tasdiqdan keyin bajaradi", 3: "Avtomatik (xavfi past)"}

AGENTS = [
    {"key": "brief", "name": "Rektor yordamchisi", "emoji": "☀️", "level": 0, "status": "faol",
     "desc": "Har kuni 08:00 da rektor uchun qisqa brifing: 3 ta ustuvor masala, kontrakt prognozi va tasdiq kutayotgan takliflar.",
     "does": ["Panelda kunlik brifing", "Telegram'ga har kuni 08:00 da yuboriladi", "Har bir masala uchun ISFT Core'ga tayyor savol"],
     "sees": "KPI va ogohlantirishlar (jamlangan)"},
    {"key": "ijro", "name": "Ijro nazorati agenti", "emoji": "📌", "level": 2, "status": "faol",
     "desc": "Majlis topshiriqlari muddatini kuzatadi: muddatga 2 kun qolganda ijrochiga avtomatik eslatma, muddat o'tsa — rasmiy eslatma taklifi.",
     "does": ["Muddatdan 2 kun oldin avtomatik eslatma (3-daraja)", "Muddati o'tgan topshiriq → rasmiy eslatma taklifi", "Tasdiqlovchi: rektor yoki rektorat kotibi"],
     "sees": "Majlis topshiriqlari"},
    {"key": "talaba", "name": "Talabani qo'llab-quvvatlash agenti", "emoji": "🎓", "level": 2, "status": "faol",
     "desc": "Talabalar bilan ishlash markazi holatlarini kuzatadi: call-markaz navbati, jiddiy akademik holatlar bo'yicha registratorga topshiriq taklifi.",
     "does": ["Call-markaz navbati xulosasi (avtomatik)", "Jiddiy akademik holatlar → registratorga topshiriq taklifi", "Tasdiqlovchi: rektor yoki o'quv prorektori"],
     "sees": "Talabalar markazi (faqat jamlangan raqamlar)"},
    {"key": "moliya", "name": "Moliya prognoz agenti", "emoji": "💰", "level": 1, "status": "faol",
     "desc": "Kontrakt tushumi prognozini hisoblaydi va byudjet moddalari rejadan oshsa buxgalteriyaga tahlil topshirig'i qoralamasini tayyorlaydi.",
     "does": ["O'quv yili oxiriga tushum prognozi", "Rejadan oshgan xarajat → buxgalteriyaga topshiriq qoralamasi", "Tasdiqlovchi: rektor yoki moliya prorektori"],
     "sees": "Kontrakt va byudjet (jamlangan)"},
    {"key": "hujjat", "name": "Hujjat agenti", "emoji": "📄", "level": 1, "status": "faol",
     "desc": "Hujjatlar reyestri va xalqaro shartnomalarni kuzatadi: imzo kutayotgan hujjatlar, muddati tugayotgan hamkorlik shartnomalari.",
     "does": ["Berilgan va imzo kutayotgan hujjatlar xulosasi", "Tugayotgan shartnoma → xalqaro bo'limga topshiriq qoralamasi", "Tasdiqlovchi: rektor"],
     "sees": "Hujjatlar reyestri, xalqaro shartnomalar"},
    {"key": "talaba247", "name": "Talabalar uchun 24/7 yordamchi", "emoji": "🤖", "level": 1, "status": "pilot",
     "desc": "Rejada: talabalar Telegram orqali kecha-kunduz savol beradi, ma'lumotnoma buyurtma qiladi. Hozircha faol emas — pilot bosqichida.",
     "does": ["Telegram bot orqali murojaat", "HEMIS ID bilan shaxsni tasdiqlash", "Tez-tez beriladigan savollar (FAQ)", "Ma'lumotnoma buyurtmasi → Hujjatlar markazi"],
     "sees": "Faqat talabaning o'z ma'lumoti (rejada)"},
]
AG = {a["key"]: a for a in AGENTS}

VIEW_ROLES = {"rektor", "kengash", "kotib"}            # + barcha prorektor_*
APPROVER = {"moliya": "prorektor_moliya", "talaba": "prorektor_oquv", "ijro": "kotib"}   # rektor — hammasi
VIS_RES = {"brief": rbac.KPI, "ijro": rbac.TASKS, "talaba": rbac.OPS, "moliya": rbac.FINANCE, "hujjat": rbac.INTL, "talaba247": rbac.KPI}
EFFECTS = {"task", "remind", "none"}

def _now(): return dt.datetime.now().replace(microsecond=0).isoformat(timespec="seconds")
def _today(): return S.TODAY.isoformat()
def _dmy(iso): return f"{iso[8:10]}.{iso[5:7]}.{iso[:4]}" if iso and len(iso) >= 10 else (iso or "")
def _short(name): return (name or "").split(":", 1)[-1].strip()
def _cut(t, n=70):
    t = (t or "").strip()
    return t if len(t) <= n else t[:n].rsplit(" ", 1)[0].rstrip(",.;:") + "…"

# ---------------------------------------------------------------------------------------------
def init(con):
    con.executescript("""
    CREATE TABLE IF NOT EXISTS agent_actions(id INTEGER PRIMARY KEY, key TEXT UNIQUE, agent TEXT, level INT, title TEXT, detail TEXT,
      status TEXT, created_at TEXT, decided_at TEXT, decided_by TEXT, payload TEXT, result TEXT);
    CREATE INDEX IF NOT EXISTS ix_agent_actions_st ON agent_actions(status, agent);
    """)
    con.commit()
    try:
        scan(con)
    except Exception as e:      # demo: agent skaneri ishga tushmasa ham server ishlashi kerak
        print("agent_hub.scan xatosi:", e)

def bind(con, ctx_fn):
    global _con, _ctx
    _con, _ctx = con, ctx_fn

def _rector(con) -> Ctx:
    u = db.one(con, "SELECT * FROM users WHERE role='rektor' ORDER BY id LIMIT 1")
    if u: return Ctx(u, ROLES["rektor"])
    return Ctx({"id": 0, "full_name": "ISFT Core", "role": "rektor", "faculty_id": None, "department_id": None, "teacher_id": None}, ROLES["rektor"])

def _jarvis(agent):
    return {"id": None, "full_name": f"ISFT Core · {AG[agent]['name']}"}

# ---------- ruxsatlar ----------
def can_view_page(c: Ctx) -> bool:
    return c.role.key in VIEW_ROLES or c.role.key.startswith("prorektor_")

def can_approve(c: Ctx, agent: str) -> bool:
    if agent not in AG or AG[agent]["status"] != "faol": return False
    return c.role.key == "rektor" or APPROVER.get(agent) == c.role.key

def can_see_agent(c: Ctx, agent: str) -> bool:
    if c.role.key in ("rektor", "kengash"): return True
    return can_approve(c, agent) or c.can(VIS_RES.get(agent, rbac.KPI))

def _guard(c: Ctx, action: str, detail=""):
    ok = can_view_page(c)
    rbac.audit(_con, c, action, RES, ok, detail)
    if not ok:
        raise AccessDenied(f"⛔ AI agentlar markazi: '{c.role.title}' lavozimi uchun ruxsat yo'q. So'rov audit jurnaliga yozildi.")

# ---------- amal yaratish va bajarish ----------
def _add(con, key, agent, level, title, detail="", payload=None, auto=False, result=""):
    """Yangi amal (kalit takrorlansa — hech narsa qilinmaydi). auto=True → darhol bajariladi."""
    if con.execute("SELECT 1 FROM agent_actions WHERE key=?", (key,)).fetchone():
        return None
    payload = payload or {"effect": "none"}
    cur = con.execute("""INSERT INTO agent_actions(key,agent,level,title,detail,status,created_at,payload,result) VALUES(?,?,?,?,?,?,?,?,?)""",
                      (key, agent, level, title[:300], detail[:1000], "taklif", _now(), json.dumps(payload, ensure_ascii=False), ""))
    aid = cur.lastrowid
    if auto:
        res = _execute(con, payload, _jarvis(agent), agent, auto=True)
        con.execute("UPDATE agent_actions SET status='bajarildi', decided_at=?, decided_by=?, result=? WHERE id=?",
                    (_now(), "ISFT Core (avtomatik)", (result or res)[:600], aid))
    con.commit()
    return aid

def _agent_meeting(con) -> int:
    m = db.one(con, "SELECT id FROM meetings WHERE title=? ORDER BY id LIMIT 1", (AGENT_MEETING,))
    if m: return m["id"]
    return con.execute("INSERT INTO meetings(title,date,kind,transcript) VALUES(?,?,?,?)",
                       (AGENT_MEETING, _today(), "Agent", "ISFT Core agentlari tayyorlagan va rahbariyat tasdiqlagan topshiriqlar.")).lastrowid

def _cols(con, table):
    return {r[1] for r in con.execute(f"PRAGMA table_info({table})").fetchall()}

def _execute(con, p: dict, who: dict, agent: str, auto=False) -> str:
    eff = p.get("effect", "none")
    if eff == "task":
        mid = _agent_meeting(con)
        role = p["role"]
        cols = _cols(con, "tasks")
        fields = {"meeting_id": mid, "assignee": p.get("assignee") or ROLES[role].title, "assignee_role": role,
                  "text": p["text"][:500], "due": p["due"], "status": "jarayonda"}
        if "unit" in cols:
            try:
                from .decisions import UNIT_OF_ROLE
                if UNIT_OF_ROLE.get(role): fields["unit"] = UNIT_OF_ROLE[role]
            except Exception:
                pass
        if "updated_at" in cols: fields["updated_at"] = _now()
        tid = con.execute(f"INSERT INTO tasks({','.join(fields)}) VALUES({','.join('?' * len(fields))})", tuple(fields.values())).lastrowid
        con.execute("INSERT INTO task_log(task_id,ts,user_id,user_name,action,detail) VALUES(?,?,?,?,?,?)",
                    (tid, _now(), who.get("id"), who.get("full_name"), "ISFT Core agenti taklifi",
                     f"{AG[agent]['name']} tayyorlagan; {_short(who.get('full_name'))} tasdiqladi"))
        return f"Topshiriq #{tid} yaratildi: {fields['assignee']} · muddat {_dmy(p['due'])}. «Majlislar va topshiriqlar» bo'limida ko'rinadi."
    if eff == "remind":
        ids = [int(i) for i in p.get("task_ids", [])]
        ok = []
        for i in ids:
            if not con.execute("SELECT 1 FROM tasks WHERE id=?", (i,)).fetchone(): continue
            detail = (p.get("note") or "Muddatga oz qoldi — avtomatik eslatma (xavfi past amal)") if auto else \
                     f"Rasmiy eslatma yuborildi ({_short(who.get('full_name'))} tasdiqladi)"
            con.execute("INSERT INTO task_log(task_id,ts,user_id,user_name,action,detail) VALUES(?,?,?,?,?,?)",
                        (i, _now(), who.get("id"), who.get("full_name") if not auto else f"ISFT Core · {AG[agent]['name']}", "ISFT Core eslatmasi", detail))
            ok.append(i)
        if not ok: return "Topshiriq topilmadi — eslatma yuborilmadi."
        return (f"{len(ok)} ta topshiriq ijrochisiga eslatma yuborildi" if auto else f"{len(ok)} ta topshiriq bo'yicha rasmiy eslatma yuborildi") + \
               f" (#{', #'.join(map(str, ok))}); topshiriq tarixiga yozildi."
    return "Qayd etildi."

# ---------- skaner: real ma'lumotdan amallar ----------
def scan(con) -> int:
    rc = _rector(con)
    d = _today()
    new = 0
    def add(*a, **k):
        nonlocal new
        if _add(con, *a, **k): new += 1

    # 1) Rektor yordamchisi — kunlik brifing tayyorlandi
    try:
        al = S.alerts(con, rc)
        hi = sum(a["level"] == "high" for a in al)
        add(f"brief:{d}", "brief", 0, f"Kunlik brifing tayyorlandi — {_dmy(d)}",
            f"{len(al)} ta ogohlantirish, shundan {hi} tasi yuqori darajali. Eng muhim 3 tasi panelda va Telegram'da.",
            auto=True, result=f"Brifing panelga chiqarildi; Telegram'ga 08:00 da yuboriladi. Yuqori darajali masalalar: {hi}.")
    except Exception as e:
        print("brief scan:", e)

    # 2) Ijro nazorati
    try:
        tl = S.tasks_list(con, rc, quiet=True)["tasks"]
        soon = [t for t in tl if t["status"] not in ("bajarildi", "qoralama") and not t["overdue"] and t["days"] is not None and 0 <= t["days"] <= 2]
        for t in soon:
            add(f"ijro:soon:{t['id']}:{d}", "ijro", 3, f"Eslatma: «{_cut(t['text'])}» — muddatga {t['days']} kun qoldi",
                f"Ijrochi: {t['assignee'] or ROLES.get(t['assignee_role'], ROLES['rektor']).title} · muddat {_dmy(t['due'])}",
                payload={"effect": "remind", "task_ids": [t["id"]], "note": f"Muddatga {t['days']} kun qoldi — ISFT Core avtomatik eslatmasi"}, auto=True)
        over = [t for t in tl if t["overdue"]]
        for t in over:
            who = t["assignee"] or ROLES.get(t["assignee_role"], ROLES["rektor"]).title
            add(f"ijro:overdue:{t['id']}:{d}", "ijro", 2, f"Rasmiy eslatma: «{_cut(t['text'])}»",
                f"{who} · muddat {_dmy(t['due'])} ({abs(t['days'] or 0)} kun o'tgan). Tasdiqlansa, rasmiy eslatma yuboriladi va topshiriq tarixiga yoziladi.",
                payload={"effect": "remind", "task_ids": [t["id"]]})
    except Exception as e:
        print("ijro scan:", e)

    # 3) Talabani qo'llab-quvvatlash
    try:
        has_ops = con.execute("SELECT 1 FROM sqlite_master WHERE name='ops_tasks'").fetchone()
        if has_ops:
            from .student_ops import calls_summary
            cs = calls_summary(con); late = cs["late"]
            fmt_ = lambda x: f"{x:,}".replace(",", " ")
            add(f"talaba:queue:{d}", "talaba", 3, f"Call-markaz: bugun {fmt_(cs['today'])} ta qo'ng'iroq, {fmt_(cs['scheduled'])} tasi rejalashtirilgan",
                f"Jami navbat {fmt_(cs['total'])} ta; kunlik imkoniyat {cs['capacity']} ta ({cs['operators']} operator) — navbat ~{cs['days']} ish kunida tugaydi. "
                f"Bugungi ro'yxatda kechikkan: {late}. Har bir qo'ng'iroq uchun suhbat skripti tayyor.",
                auto=True, result=(f"Xulosa tayyorlandi: {late} ta kechikkan qo'ng'iroq birinchi navbatda." if late else "Xulosa tayyorlandi: kechikkan qo'ng'iroq yo'q, navbat jiddiylik darajasi bo'yicha."))
            jid = con.execute("SELECT COUNT(*) FROM ops_cases WHERE rule='akademik' AND level=3 AND status='ochiq'").fetchone()[0]
            if jid:
                add(f"talaba:jiddiy:{d}", "talaba", 2, f"Registratorga topshiriq: {jid} ta jiddiy akademik holat",
                    "«Jiddiy» darajadagi akademik qarzdorlik holatlari bo'yicha ogohlantirish xatlari va buyruq loyihalarini tayyorlash taklif etiladi.",
                    payload={"effect": "task", "assignee": "Registrator ofisi", "role": "talabalar",
                             "text": f"{jid} ta «Jiddiy» darajadagi akademik holat bo'yicha talabalarga ogohlantirish xatlarini yuborish va zarur buyruq loyihalarini tayyorlash",
                             "due": (S.TODAY + dt.timedelta(days=5)).isoformat()})
    except Exception as e:
        print("talaba scan:", e)

    # 4) Moliya prognozi
    try:
        from .agent import contract_forecast
        f = contract_forecast(con)
        nx = f.get("next")
        line = f"Yil oxiriga prognoz: {f['forecast_pct']}% (hozir {f['pct_now']}%), kutilayotgan kamomad {S.mln(f['gap'])}."
        if nx: line += f" {nx['label']} ({_dmy(nx['due'])}, {nx['days']} kun): {nx['behind']} nafar talaba grafikdan ortda."
        add(f"moliya:forecast:{d}", "moliya", 1, f"Kontrakt tushumi prognozi: {f['forecast_pct']}%", line, auto=True,
            result="Prognoz hisoblandi va brifingga qo'shildi.")
        fs = S.finance_summary(con, rc, quiet=True)
        seen = set()
        for o in fs["overruns"]:
            if o["category"] in seen: continue
            seen.add(o["category"])
            n = sum(1 for x in fs["overruns"] if x["category"] == o["category"])
            add(f"moliya:over:{o['category']}:{d}", "moliya", 2, f"Buxgalteriyaga topshiriq: «{o['category']}» rejadan {o['over_pct']}% oshgan",
                f"{o['month']} oyida reja {S.mln(o['planned'])}, amalda {S.mln(o['actual'])}; ketma-ket {n} oy oshish. Sabablar tahlili va tejash choralari taklif etiladi.",
                payload={"effect": "task", "assignee": "Buxgalteriya bo'limi", "role": "buxgalteriya",
                         "text": f"«{o['category']}» xarajatlari rejadan {o['over_pct']}% oshishi sabablarini tahlil qilish va tejash choralari bo'yicha taklif kiritish",
                         "due": (S.TODAY + dt.timedelta(days=7)).isoformat()})
            if len(seen) >= 2: break
    except Exception as e:
        print("moliya scan:", e)

    # 5) Hujjat agenti
    try:
        cnt = {r["status"]: r["n"] for r in db.rows(con, "SELECT status, COUNT(*) n FROM documents GROUP BY status")}
        today_n = con.execute("SELECT COUNT(*) FROM documents WHERE substr(created_at,1,10)=?", (d,)).fetchone()[0]
        add(f"hujjat:sum:{d}", "hujjat", 1, f"Hujjatlar: {cnt.get('loyiha', 0)} ta imzo kutmoqda",
            f"Berilgan: {cnt.get('berilgan', 0) + cnt.get('imzolangan', 0)} ta, imzo kutayotgan loyihalar: {cnt.get('loyiha', 0)} ta, bugun yaratilgan: {today_n} ta.",
            auto=True, result=f"Xulosa tayyorlandi: {cnt.get('loyiha', 0)} ta loyiha «Hujjatlar markazi»da imzo kutmoqda.")
        intl = S.international_summary(con, rc, quiet=True)
        for p in intl["expiring"]:
            add(f"hujjat:partner:{p['id']}:{d}", "hujjat", 2, f"Xalqaro bo'limga: {p['name']} shartnomasi {p['days_left']} kunda tugaydi",
                f"{p['country']} · amal qilish muddati {_dmy(p['expires'])}. Uzaytirish bo'yicha xat va kelishuv loyihasini tayyorlash taklif etiladi.",
                payload={"effect": "task", "assignee": "Xalqaro hamkorlik bo'limi", "role": "xalqaro",
                         "text": f"{p['name']} ({p['country']}) bilan hamkorlik shartnomasini uzaytirish: hamkorga xat va kelishuv loyihasini tayyorlash",
                         "due": (S.TODAY + dt.timedelta(days=max(3, min(14, p['days_left'] - 7)))).isoformat()})
    except Exception as e:
        print("hujjat scan:", e)
    return new

# ---------- ko'rinishlar ----------
def _view(c: Ctx, a: dict) -> dict:
    p = json.loads(a["payload"] or "{}")
    return {"id": a["id"], "agent": a["agent"], "agent_name": AG.get(a["agent"], {}).get("name", a["agent"]),
            "emoji": AG.get(a["agent"], {}).get("emoji", "🤖"), "level": a["level"], "title": a["title"], "detail": a["detail"],
            "status": a["status"], "created_at": a["created_at"], "decided_at": a["decided_at"], "decided_by": a["decided_by"],
            "result": a["result"], "effect": p.get("effect"), "assignee": p.get("assignee"), "due": p.get("due"),
            "can_approve": a["status"] == "taklif" and can_approve(c, a["agent"])}

def overview(c: Ctx) -> dict:
    d = _today()
    rows = db.rows(_con, "SELECT * FROM agent_actions ORDER BY id DESC LIMIT 400")
    vis = [r for r in rows if can_see_agent(c, r["agent"])]
    agents = []
    for a in AGENTS:
        mine = [r for r in rows if r["agent"] == a["key"]]
        agents.append({**a, "can_approve": can_approve(c, a["key"]), "visible": can_see_agent(c, a["key"]),
                       "approvers": ["Rektor"] + ([ROLES[APPROVER[a["key"]]].title] if a["key"] in APPROVER else []) if a["status"] == "faol" else [],
                       "stats": {"today": sum((r["created_at"] or "")[:10] == d for r in mine),
                                 "pending": sum(r["status"] == "taklif" for r in mine),
                                 "done": sum(r["status"] == "bajarildi" for r in mine)}})
    pending = [_view(c, r) for r in vis if r["status"] == "taklif"]
    recent = [_view(c, r) for r in vis if r["status"] != "taklif"][:40]
    return {"agents": agents, "levels": LEVELS, "pending": pending, "actions": recent,
            "can_run": c.role.key != "kengash", "read_only": not any(can_approve(c, a["key"]) for a in AGENTS), "today": d}

def decide(c: Ctx, aid: int, approve: bool) -> dict:
    a = db.one(_con, "SELECT * FROM agent_actions WHERE id=?", (aid,))
    if not a: raise HTTPException(404, "Amal topilmadi")
    ok = can_approve(c, a["agent"])
    rbac.audit(_con, c, "agent taklifini " + ("tasdiqlash" if approve else "rad etish"), RES, ok, f"#{aid} {a['title']}")
    if not ok:
        raise AccessDenied(f"⛔ «{AG.get(a['agent'], {}).get('name', a['agent'])}» takliflarini faqat rektor"
                           + (f" yoki {ROLES[APPROVER[a['agent']]].title.lower()}" if a["agent"] in APPROVER else "") + " tasdiqlaydi.")
    # atomar o'tish: qayta bosish ikkinchi marta bajarmaydi
    n = _con.execute("UPDATE agent_actions SET status=?, decided_at=?, decided_by=? WHERE id=? AND status='taklif'",
                     ("bajarildi" if approve else "rad", _now(), c.user["full_name"], aid)).rowcount
    if not n:
        _con.commit()
        return {"ok": False, "status": a["status"], "result": a["result"] or "Bu taklif bo'yicha qaror allaqachon qabul qilingan."}
    if approve:
        res = _execute(_con, json.loads(a["payload"] or "{}"), c.user, a["agent"])
    else:
        res = f"Rad etildi ({_short(c.user['full_name'])}). Hech qanday amal bajarilmadi."
    _con.execute("UPDATE agent_actions SET result=? WHERE id=?", (res[:600], aid))
    _con.commit()
    return {"ok": True, "status": "bajarildi" if approve else "rad", "result": res}

def brief(c: Ctx) -> dict:
    if not (c.role.key in ("rektor", "kengash") or c.role.key.startswith("prorektor_")):
        rbac.audit(_con, c, "kunlik brifing", RES, False)
        raise AccessDenied("⛔ Kunlik brifing faqat rahbariyat uchun.")
    rbac.audit(_con, c, "kunlik brifing", RES, True)
    Q = {"O'quv": "Qaysi guruhlarda o'zlashtirish pasaygan va nega?", "Talabalar": "Xavf ostidagi talabalar qaysi guruhlarda ko'p?",
         "Kontrakt": "Kontrakt qarzdorligi qanday?", "Moliya": "Qaysi xarajat moddasi rejadan oshgan?", "Xalqaro": "Qaysi xalqaro shartnomalar tugayapti?",
         "Topshiriqlar": "Qaysi topshiriqlar muddati o'tgan?", "Yotoqxona": "Yotoqxona holati qanday?", "Murojaatlar": "Hal qilinmagan murojaatlar bormi?"}
    al = S.alerts(_con, c)
    top, areas = [], set()
    for a in al:                     # har xil yo'nalishdan 3 ta (yuqori daraja birinchi)
        if a["area"] in areas: continue
        areas.add(a["area"])
        top.append({"level": a["level"], "area": a["area"], "text": a["text"], "q": Q.get(a["area"], f"{a['area']} bo'yicha holat qanday?")})
        if len(top) == 3: break
    fc = None
    if c.can(rbac.CONTRACTS):
        try:
            from .agent import contract_forecast
            f = contract_forecast(_con)
            fc = f"Kontrakt tushumi hozir {f['pct_now']}%, o'quv yili oxiriga prognoz {f['forecast_pct']}% (kamomad ≈ {S.mln(f['gap'])})."
            if f.get("next"): fc += f" Keyingi muddat — {f['next']['label']}, {_dmy(f['next']['due'])}: {f['next']['behind']} nafar ortda."
        except Exception:
            fc = None
    pend = [r for r in db.rows(_con, "SELECT agent FROM agent_actions WHERE status='taklif'") if can_see_agent(c, r["agent"])]
    mine = sum(can_approve(c, r["agent"]) for r in pend)
    return {"date": _today(), "priorities": top, "forecast": fc, "pending": len(pend), "pending_mine": mine,
            "note": "Telegram'ga har kuni 08:00 da yuboriladi", "agent": AG["brief"]["name"]}

def brief_text(con, c: Ctx) -> str:
    """Telegram uchun matn (bot.py 08:00 jadvali chaqirishi mumkin)."""
    global _con
    if _con is None: _con = con
    b = brief(c)
    lines = [f"☀️ Bugungi brifing — {_dmy(b['date'])}"]
    for i, p in enumerate(b["priorities"], 1): lines.append(f"{i}. {p['area']}: {p['text']}")
    if b["forecast"]: lines.append("💰 " + b["forecast"])
    if b["pending"]: lines.append(f"🕓 Tasdiqlash kutilmoqda: {b['pending']} ta agent taklifi")
    return "\n".join(lines)

# ---------- API ----------
def C(request: Request) -> Ctx: return _ctx(request)

@router.get("/api/agents")
def api_agents(request: Request):
    c = C(request); _guard(c, "AI agentlar markazi")
    return overview(c)

@router.post("/api/agents/run")
def api_run(request: Request):
    c = C(request); _guard(c, "agentlarni ishga tushirish")
    if c.role.key == "kengash":
        raise AccessDenied("⛔ Kuzatuv kengashi uchun faqat ko'rish rejimi.")
    n = scan(_con)
    return {"ok": True, "new": n, "message": f"Agentlar ishga tushirildi: {n} ta yangi amal" if n else "Agentlar ishga tushirildi: yangi amal yo'q — barchasi dolzarb"}

@router.post("/api/agents/actions/{aid}/approve")
def api_approve(aid: int, request: Request):
    c = C(request); _guard(c, "agent taklifi", f"#{aid}")
    return decide(c, aid, True)

@router.post("/api/agents/actions/{aid}/reject")
def api_reject(aid: int, request: Request):
    c = C(request); _guard(c, "agent taklifi", f"#{aid}")
    return decide(c, aid, False)

@router.get("/api/agents/brief")
def api_brief(request: Request):
    return brief(C(request))

class ProposeIn(BaseModel):
    agent: str
    label: str
    payload: dict

def _clean_payload(p: dict) -> dict:
    eff = p.get("effect")
    if eff not in EFFECTS: raise HTTPException(400, "Noma'lum amal turi")
    if eff == "task":
        role = p.get("role")
        if role not in ROLES: raise HTTPException(400, "Noma'lum lavozim")
        text = str(p.get("text") or "").strip()
        if not text: raise HTTPException(400, "Topshiriq matni bo'sh")
        try: due = dt.date.fromisoformat(str(p.get("due"))).isoformat()
        except (ValueError, TypeError): due = (S.TODAY + dt.timedelta(days=7)).isoformat()
        return {"effect": "task", "assignee": str(p.get("assignee") or ROLES[role].title)[:150], "role": role, "text": text[:500], "due": due}
    if eff == "remind":
        try: ids = [int(i) for i in p.get("task_ids") or []][:20]
        except (ValueError, TypeError): raise HTTPException(400, "Topshiriq raqamlari noto'g'ri")
        if not ids: raise HTTPException(400, "Topshiriq ko'rsatilmagan")
        return {"effect": "remind", "task_ids": ids}
    return {"effect": "none"}

@router.post("/api/agents/propose")
def api_propose(body: ProposeIn, request: Request):
    c = C(request)
    if body.agent not in AG or AG[body.agent]["status"] != "faol": raise HTTPException(400, "Noma'lum agent")
    p = _clean_payload(body.payload)
    _guard(c, "chatdan agent taklifi", f"{body.agent}: {body.label[:120]}")
    if c.role.key == "kengash":
        raise AccessDenied("⛔ Kuzatuv kengashi uchun faqat ko'rish rejimi.")
    h = hashlib.sha1(json.dumps(p, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:12]
    key = f"chat:{body.agent}:{h}:{_today()}"
    ex = db.one(_con, "SELECT * FROM agent_actions WHERE key=?", (key,))
    if ex:
        return {"id": ex["id"], "status": ex["status"], "result": ex["result"] or "Bu taklif bugun allaqachon yuborilgan.", "duplicate": True}
    detail = f"ISFT Core suhbatida {_short(c.user['full_name'])} ({c.role.title}) taklif qildi."
    if p["effect"] == "task": detail += f" Mas'ul: {p['assignee']}, muddat {_dmy(p['due'])}. «{p['text']}»"
    cur = _con.execute("""INSERT INTO agent_actions(key,agent,level,title,detail,status,created_at,payload,result) VALUES(?,?,?,?,?,?,?,?,?)""",
                       (key, body.agent, 2, body.label.strip()[:300] or "Chatdan taklif", detail[:1000], "taklif", _now(), json.dumps(p, ensure_ascii=False), ""))
    aid = cur.lastrowid
    _con.commit()
    if can_approve(c, body.agent):
        r = decide(c, aid, True)
        return {"id": aid, "status": r["status"], "result": r["result"]}
    approvers = "rektor" + (f" yoki {ROLES[APPROVER[body.agent]].title.lower()}" if body.agent in APPROVER else "")
    return {"id": aid, "status": "taklif", "result": f"Taklif {approvers} tasdig'iga yuborildi — «AI agentlar» bo'limida."}
