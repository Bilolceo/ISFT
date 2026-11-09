"""ISFT Core MVP — veb-server. Ishga tushirish: ./run.sh  (http://localhost:8000)"""
import datetime as dt
from pathlib import Path
from fastapi import FastAPI, Request, HTTPException, Response
from fastapi.responses import StreamingResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from . import db, rbac, services as S, ai, reports, documents as D, service as SV, occupancy as OC, decisions as DEC, student_ops as OPSM, agent as AG
from .rbac import AccessDenied

ROOT = Path(__file__).resolve().parent.parent
app = FastAPI(title="ISFT Core")
con = db.connect()
db.init(con)  # yangi jadvallar (masalan, documents) mavjud bazaga ham qo'shiladi
DEC.init(con)  # majlis qarori oqimi: meetings/tasks kengaytmasi, chat, tarix, demo akkauntlar
OPSM.init(con)  # talabalar markazi: qoidalar, holatlar, call-markaz, otrabotka
# "Lavozim ism" hujjatidagi bo'lim (id'lar o'zgarmasligi uchun seed'dan keyin qo'shiladi)
if db.one(con, "SELECT 1 x FROM users") and not db.one(con, "SELECT 1 x FROM users WHERE role='amaliyot'"):
    con.execute("INSERT INTO users(full_name,role,link_code,pin) VALUES(?,?,?,?)",
                ("Amaliyot bo'limi: Suhrob Bahodirovich", "amaliyot", "AMALIYOT", rbac.hash_password(rbac.DEMO_PASSWORD))); con.commit()
# Har bir kafedra mudiri uchun akkaunt ("Lavozim ism" hujjati) — kirish sahifasidagi "Kafedralar" bo'limi
if db.one(con, "SELECT 1 x FROM users"):
    for d in db.rows(con, "SELECT * FROM departments ORDER BY id"):
        if not d.get("head") or db.one(con, "SELECT 1 x FROM users WHERE role='kafedra' AND department_id=?", (d["id"],)): continue
        con.execute("INSERT INTO users(full_name,role,faculty_id,department_id,link_code,pin) VALUES(?,?,?,?,?,?)",
                    (f"{d['name']} kafedrasi mudiri: {d['head']}", "kafedra", d["faculty_id"], d["id"], f"KAF{d['id']}", rbac.hash_password(rbac.DEMO_PASSWORD)))
    con.commit()

# Rahbarlar rasmlari (isft.uz saytidan): static/brand/people/index.json — {ism: /brand/people/av/…jpg}
import json as _json, re as _re
def _pkey(n):
    n = _re.sub(r"[ʻʼ‘’'`´]", "", (n or "").split(":")[-1].lower()).split()
    return " ".join(n[:2])
try:
    PHOTOS = {_pkey(k): v for k, v in _json.load(open(ROOT / "static" / "brand" / "people" / "index.json", encoding="utf-8")).items()}
except (OSError, ValueError):
    PHOTOS = {}
def photo_of(u): return PHOTOS.get(_pkey(u["full_name"])) if ":" in (u.get("full_name") or "") else None

@app.on_event("startup")
async def _warm():
    import asyncio
    asyncio.create_task(ai.warmup())
    asyncio.create_task(OC.poller())
    asyncio.create_task(OC.events_supervisor())   # Hikvision voqealar oqimi tinglovchilari
    asyncio.create_task(OPSM.poller())   # qoidalar har 10 daqiqada qayta hisoblanadi

from . import sessions as SS
SS.init(con)
COOKIE = "sid"

def ctx(request: Request) -> rbac.Ctx:
    uid = SS.resolve(con, request.cookies.get(COOKIE))
    if not uid:
        raise HTTPException(401, "Kirish talab qilinadi")
    try:
        return rbac.ctx_for(con, uid)
    except AccessDenied as e:
        raise HTTPException(401, str(e))

@app.exception_handler(AccessDenied)
async def denied(_, e: AccessDenied):
    return JSONResponse({"denied": True, "message": str(e)}, status_code=403)

class Login(BaseModel):
    user_id: int
    password: str = ""
    pin: str = ""      # eski mijozlar uchun

@app.get("/api/users")
def users():
    us = db.rows(con, "SELECT * FROM users ORDER BY id")
    # "Kafedralar" bo'limida faqat kafedra mudirlari (kafedralar tartibida); dekan/tyutor/o'qituvchi demo akkauntlari
    # kirish ro'yxatida ko'rsatilmaydi (API orqali ishlashda davom etadi)
    us = [u for u in us if rbac.ROLES[u["role"]].level != 4 or u["role"] == "kafedra"]
    us.sort(key=lambda u: (rbac.ROLES[u["role"]].level, u.get("department_id") or 0, u["id"]))
    return [{"id": u["id"], "name": u["full_name"], "role": rbac.user_title(u), "level": rbac.ROLES[u["role"]].level, "photo": photo_of(u)} for u in us]

def _ip(request: Request) -> str:
    return (request.client.host if request.client else "") or "?"

@app.post("/api/login")
def login(body: Login, request: Request, response: Response):
    ip = _ip(request)
    wait = SS.LOGIN_USER.wait_min(body.user_id) or SS.LOGIN_IP.wait_min(ip)
    if wait:
        raise HTTPException(429, f"Juda ko'p noto'g'ri urinish. {wait} daqiqadan keyin qayta urinib ko'ring.")
    u = db.one(con, "SELECT * FROM users WHERE id=?", (body.user_id,))
    pw = body.password or body.pin
    if not u or not rbac.check_password(u["pin"], pw):
        left = SS.LOGIN_USER.fail(body.user_id); SS.LOGIN_IP.fail(ip)
        if u:
            rbac.audit(con, rbac.Ctx(u, rbac.ROLES[u["role"]]), "tizimga kirish", "auth", False, f"noto'g'ri parol · IP {ip}")
        raise HTTPException(401, "Parol noto'g'ri" + (f" · yana {left} ta urinish qoldi" if 0 < left < 3 else ""))
    SS.LOGIN_USER.reset(body.user_id)
    if not str(u["pin"]).startswith("pbkdf2$"):   # eski ochiq yozuvni xeshga o'tkazamiz
        u = dict(u); u["pin"] = rbac.hash_password(pw)
        con.execute("UPDATE users SET pin=? WHERE id=?", (u["pin"], u["id"])); con.commit()
    c = rbac.Ctx(u, rbac.ROLES[u["role"]])
    rbac.audit(con, c, "tizimga kirish", "auth", True)
    response.set_cookie(COOKIE, SS.create(con, u, ip), httponly=True, samesite="lax", max_age=SS.TTL,
                        secure=request.url.scheme == "https")
    response.delete_cookie("uid")       # eski formatdagi cookie
    return {"ok": True}

@app.post("/api/logout")
def logout(request: Request, response: Response):
    tok = request.cookies.get(COOKIE)
    uid = SS.resolve(con, tok)
    if uid: AG.forget(uid)
    SS.revoke(con, tok)
    response.delete_cookie(COOKIE); response.delete_cookie("uid"); return {"ok": True}

@app.get("/api/me")
def me(request: Request):
    c = ctx(request)
    return {"id": c.user["id"], "name": c.user["full_name"], "role": c.title, "greet": rbac.greeting(c.user), "photo": photo_of(c.user), "role_key": c.role.key, "level": c.role.level,
            "scope": c.scope_label(con), "allow": sorted(c.role.allow), "deny_note": c.role.deny_note,
            "labels": rbac.LABELS, "today": S.TODAY.isoformat()}

SECTIONS = {"academic": S.academic_overview, "risk": S.at_risk_students, "contracts": S.contracts_summary, "finance": S.finance_summary,
            "payroll": S.payroll_summary, "hr": S.hr_list, "science": S.science_summary, "international": S.international_summary,
            "admissions": S.admissions_summary, "youth": S.youth_summary, "masters": S.masters_summary, "tasks": S.tasks_list,
            "audit": S.audit_log, "mygroups": S.teacher_groups}

@app.get("/api/dashboard")
def dashboard(request: Request):
    c = ctx(request)
    rbac.audit(con, c, "boshqaruv paneli", "kpi", True)
    panels = {}
    for k, fn in SECTIONS.items():
        if k == "audit": continue
        try:
            v = fn(con, c, quiet=True)
            if v is not None: panels[k] = v
        except AccessDenied:
            pass
    return {"kpis": S.kpis(con, c), "alerts": S.alerts(con, c), "panels": panels}

@app.get("/api/section/{name}")
def section(name: str, request: Request):
    if name not in SECTIONS: raise HTTPException(404)
    return SECTIONS[name](con, ctx(request))

class Q(BaseModel):
    q: str

@app.post("/api/chat")
async def chat(body: Q, request: Request):
    c = ctx(request)
    return StreamingResponse(AG.run(con, c, body.q.strip()[:1000]), media_type="application/x-ndjson; charset=utf-8")

class Reason(BaseModel):
    reason: str

@app.post("/api/students/breakglass")
def breakglass(body: Reason, request: Request):
    try:
        return AG.breakglass(con, ctx(request), body.reason)
    except ValueError as e:
        raise HTTPException(400, str(e))

@app.get("/api/report/{kind}")
def report(kind: str, request: Request):
    if kind not in reports.REPORTS_META: raise HTTPException(404)
    p = reports.build(con, ctx(request), kind)
    return FileResponse(p, filename=p.name, media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document")

class Transcript(BaseModel):
    transcript: str

@app.post("/api/meetings/extract")
async def extract(body: Transcript, request: Request):
    c = ctx(request); rbac.require(con, c, rbac.TASKS, "bayonnomadan topshiriq ajratish")
    return {"tasks": await ai.extract_tasks(body.transcript)}

class Meeting(BaseModel):
    title: str
    transcript: str
    tasks: list[dict]

# Mas'ul lavozimni aniqlash. Tartib muhim: "Xalqaro iqtisodiyot va moliya fakulteti dekani" — dekan, prorektor emas;
# prorektor yo'nalishlari faqat matnda "prorektor" so'zi bo'lsa tekshiriladi.
ROLE_FIRST = [("dekan", "dekan"), ("kafedra", "kafedra"), ("o'qituvchi", "oqituvchi")]
ROLE_PROREKTOR = [("o'quv", "prorektor_oquv"), ("ilmiy", "prorektor_ilmiy"), ("moliya", "prorektor_moliya"), ("yoshlar", "prorektor_yoshlar")]
ROLE_UNITS = [("qabul", "qabul"), ("xalqaro", "xalqaro"), ("registrator", "talabalar"), ("axborot texnologiyalari", "it_head"), ("buxgalter", "buxgalteriya"), ("kadr", "kadrlar"), ("talabalar bilan", "talabalar"),
              ("magistr", "magistratura"), ("ilmiy tadqiqot", "ilmiy_bolim"), ("xo'jalik", "xojalik"),
              ("akademik faoliyat", "akademik"), ("imtihon", "imtihon"),
              ("sirtqi", "sirtqi"), ("ma'lumotlar bazasi", "malumotlar_bazasi")]

def role_for(who: str) -> str:
    low = ai.norm(who or "")
    for h, r in ROLE_FIRST:
        if h in low: return r
    if "prorektor" in low:
        for h, r in ROLE_PROREKTOR:
            if h in low: return r
    for h, r in ROLE_UNITS:
        if h in low: return r
    return "rektor"

def _valid_due(v) -> str:
    try:
        return dt.date.fromisoformat(str(v)).isoformat()
    except (ValueError, TypeError):
        return (S.TODAY + dt.timedelta(days=14)).isoformat()

@app.post("/api/meetings")
def save_meeting(body: Meeting, request: Request):
    c = ctx(request); rbac.require(con, c, rbac.TASKS, "majlisni saqlash", body.title)
    if c.role.key not in ("rektor", "kengash") and not c.role.key.startswith("prorektor_"):
        raise AccessDenied("⛔ Majlis topshiriqlarini faqat rahbariyat kiritadi.")
    cur = con.execute("INSERT INTO meetings(title,date,kind,transcript) VALUES(?,?,?,?)", (body.title, S.TODAY.isoformat(), "Rektorat", body.transcript))
    for t in body.tasks:
        who = str(t.get("assignee") or "").strip()[:120]
        con.execute("INSERT INTO tasks(meeting_id,assignee,assignee_role,text,due,status) VALUES(?,?,?,?,?,?)",
                    (cur.lastrowid, who, role_for(who), str(t.get("text", ""))[:500], _valid_due(t.get("due")), "jarayonda"))
    con.commit()
    return {"ok": True, "count": len(body.tasks)}

class Status(BaseModel):
    status: str

@app.post("/api/tasks/{tid}/status")
def task_status(tid: int, body: Status, request: Request):
    c = ctx(request); rbac.require(con, c, rbac.TASKS, "topshiriq holatini o'zgartirish", str(tid))
    t = db.one(con, "SELECT * FROM tasks WHERE id=?", (tid,))
    if not t: raise HTTPException(404)
    if t.get("unit"):   # majlis qarori oqimidagi topshiriq — holatni faqat ijrochi o'z oynasidan yangilaydi
        raise AccessDenied("⛔ Bu topshiriq holatini bo'lim rahbari yoki biriktirilgan xodim yangilaydi.")
    if c.role.key not in ("rektor", "kengash") and t["assignee_role"] != c.role.key:
        raise AccessDenied("⛔ Bu topshiriq sizga tegishli emas.")
    if body.status not in ("bajarildi", "jarayonda", "bajarilmagan"): raise HTTPException(400, "Noto'g'ri holat")
    con.execute("UPDATE tasks SET status=? WHERE id=?", (body.status, tid)); con.commit()
    return {"ok": True}

class Doc(BaseModel):
    text: str
    mode: str

@app.post("/api/doc")
async def doc(body: Doc, request: Request):
    c = ctx(request)
    if body.mode not in ("translate", "contract", "reply"): raise HTTPException(400)
    if c.role.level > 3 and c.role.key != "dekan":
        raise AccessDenied("⛔ Tarjima va shartnoma yordamchisi rahbariyat va bo'limlar uchun.")
    rbac.audit(con, c, f"tarjima va shartnoma yordamchisi: {body.mode}", "docs", True, body.text[:80])
    return {"result": await ai.doc_assist(body.text, body.mode)}

@app.get("/api/rbac")
def rbac_matrix():
    return {"roles": rbac.matrix(), "labels": rbac.LABELS}

@app.get("/api/status")
async def status():
    return {"llm": await ai.llm_available(), "model": ai.MODEL, "db": str(db.DB_PATH.name),
            "students": db.one(con, "SELECT COUNT(*) n FROM students")["n"],
            "audit": db.one(con, "SELECT COUNT(*) n FROM audit_log")["n"]}


# ---------- Hujjatlar markazi ----------
from fastapi.responses import HTMLResponse
from html import escape as _e

@app.get("/api/docs/catalog")
def docs_catalog(request: Request):
    return D.catalog_for(ctx(request))

@app.get("/api/docs/lookup/{kind}")
def docs_lookup(kind: str, request: Request, q: str = "", group_id: int = 0):
    return D.lookup(con, ctx(request), kind, q, group_id)

class Issue(BaseModel):
    key: str
    params: dict = {}

@app.post("/api/docs/issue")
async def docs_issue(body: Issue, request: Request):
    c = ctx(request); p = dict(body.params)
    if body.key == "memo" and p.get("use_ai") and (p.get("points") or "").strip() and c.role.key in D.CAT["memo"]["roles"]:
        p["_ai_text"] = await D.ai_memo_text(p.get("recipient", ""), p.get("subject_line", ""), p["points"])
    try:
        return D.issue(con, c, body.key, p, SV.public_base(request))
    except ValueError as e:
        raise HTTPException(400, str(e))

@app.get("/api/docs/registry")
def docs_registry(request: Request):
    return D.registry(con, ctx(request))

@app.post("/api/docs/{doc_id}/{action}")
def docs_status(doc_id: int, action: str, request: Request):
    if action not in ("sign", "cancel"): raise HTTPException(400)
    try:
        return D.set_status(con, ctx(request), doc_id, action)
    except ValueError as e:
        raise HTTPException(400, str(e))

@app.get("/api/docs/file/{fname}")
def docs_file(fname: str, request: Request):
    c = ctx(request); f = (D.OUT / fname).resolve()
    if f.parent != D.OUT.resolve() or not f.exists(): raise HTTPException(404)
    if not D.can_download(con, c, fname): raise AccessDenied("⛔ Bu hujjat faylini yuklab olishga ruxsat yo'q.")
    rbac.audit(con, c, "hujjat yuklab olindi", "docs", True, fname)
    return FileResponse(f, filename=fname, media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document")

@app.get("/verify/{code}", response_class=HTMLResponse)
def verify_page(code: str):
    d = D.verify(con, code[:16])
    st = {"berilgan": ("Haqiqiy hujjat", "ok"), "imzolangan": ("Haqiqiy · rektor imzolagan", "ok"),
          "loyiha": ("Loyiha — hali imzolanmagan", "warn"), "bekor": ("BEKOR QILINGAN", "bad")}
    if d:
        label, cls = st.get(d["status"], (d["status"], "warn"))
        body = f"""<div class="badge {cls}">{_e(label)}</div><table>
          <tr><th>Ro'yxat raqami</th><td>{_e(d['reg_no'])}</td></tr><tr><th>Hujjat</th><td>{_e(d['title'])}</td></tr>
          <tr><th>Kimga / kim haqida</th><td>{_e(d['holder'] or '')}</td></tr><tr><th>Berilgan sana</th><td>{_e(d['created_at'][:10])}</td></tr>
          {f"<tr><th>Imzolangan</th><td>{_e(d['signed_at'][:10])}</td></tr>" if d.get('signed_at') else ''}</table>"""
    else:
        body = '<div class="badge bad">Hujjat topilmadi</div><p>Bu kod ISFT reyestrida yo\'q. Hujjat soxta bo\'lishi mumkin.</p>'
    return f"""<!doctype html><html lang="uz"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Hujjatni tekshirish — ISFT</title><link rel="stylesheet" href="/fonts/manrope.css"><style>
:root{{--bg:#F4F5F7;--card:#fff;--ink:#0D0D0D;--muted:#838383;--teal:#870037}}
@media (prefers-color-scheme:dark){{:root{{--bg:#151011;--card:#201819;--ink:#e8eef0;--muted:#9fb0b4;--teal:#f0727a}}}}
body{{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 Manrope,-apple-system,Segoe UI,Roboto,sans-serif;display:grid;place-items:center;min-height:100vh;padding:16px;box-sizing:border-box}}
.c{{background:var(--card);border-radius:24px;max-width:520px;width:100%;overflow:hidden}}
.h{{background:#870037;color:#fff;padding:18px 22px;display:flex;gap:12px;align-items:center}}
.h img{{width:58px;height:46px;object-fit:contain;background:#fff;border-radius:8px;padding:3px}}.h b{{font-size:18px;letter-spacing:.06em}}.h small{{display:block;opacity:.85}}
.b{{padding:20px}}table{{width:100%;border-collapse:collapse;margin-top:12px}}th{{text-align:left;color:var(--muted);font-weight:500;width:42%}}th,td{{padding:8px 0;border-bottom:1px solid rgba(127,127,127,.2)}}
.badge{{display:inline-block;padding:6px 12px;border-radius:999px;font-weight:600}}.ok{{background:#e3f4ec;color:#17643f}}.warn{{background:#fdf1df;color:#8a4b00}}.bad{{background:#fdebe1;color:#9a3412}}
.f{{color:var(--muted);font-size:12px;padding:0 20px 18px}}</style></head><body><div class="c">
<div class="h"><img src="/brand/{'logo-sm.png' if (D.B.BRAND_DIR / 'logo-sm.png').exists() else 'isft-mark.png'}" alt="ISFT"><div><b>ISFT INSTITUTI</b><small>Hujjat haqiqiyligini tekshirish</small></div></div>
<div class="b">{body}</div><div class="f">Tekshiruv kodi: {_e(code.upper())} · Shaxsiy ma'lumotlar qisqartirilgan holda ko'rsatiladi.</div></div></body></html>"""

SV.bind(con, ctx)
app.include_router(SV.router)
OC.bind(con, ctx)
app.include_router(OC.router)
from . import camsec as CS   # kameralar: xavfsizlik voqealari, salomatlik, navbat, haftalik hisobot
CS.bind(con, ctx)
app.include_router(CS.router)
DEC.bind(con, ctx)
app.include_router(DEC.router)
OPSM.bind(con, ctx)
app.include_router(OPSM.router)
from . import agent_hub as AH
AH.init(con)
AH.bind(con, ctx)
app.include_router(AH.router)
from . import portal as PT   # bo'limlararo portal: yozishmalar, fayllar, umumiy bazalar
PT.init(con)
PT.bind(con, ctx)
app.include_router(PT.router)
from . import extras as XT   # parolni o'zgartirish, global qidiruv, bildirishnomalar, kalendar
XT.init(con)
XT.bind(con, ctx)
app.include_router(XT.router)

app.mount("/", StaticFiles(directory=ROOT / "static", html=True), name="static")
