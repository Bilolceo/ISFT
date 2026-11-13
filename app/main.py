"""ISFT Core MVP — veb-server. Ishga tushirish: ./run.sh  (http://localhost:8000)"""
import datetime as dt, os
from pathlib import Path
from fastapi import FastAPI, Request, HTTPException, Response
from fastapi.responses import StreamingResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from . import clock
from . import db, rbac, services as S, ai, reports, documents as D, service as SV, occupancy as OC, decisions as DEC, student_ops as OPSM, agent as AG
from . import modules as MODS   # bo'limlar kaliti (yoqilgan/o'chirilgan) — docs/modullar.md
from .rbac import AccessDenied

ROOT = Path(__file__).resolve().parent.parent
app = FastAPI(title="ISFT Core")
con = db.connect()
db.init(con)  # yangi jadvallar (masalan, documents) mavjud bazaga ham qo'shiladi
MODS.init(con)  # bo'limlar kaliti: jadval (idempotent); standartlar — app/modules.py, muhit — ISFT_CORE_MODULES
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

# Tashkiliy tuzilmadagi (04.09.2024) qolgan bo'limlar: Portal orqali xat oladigan akkauntlar (id'lar oxiriga qo'shiladi)
if db.one(con, "SELECT 1 x FROM users"):
    for _nm, _role, _code in [("Strategik bo'lim", "strategik", "STRATEG"), ("Sifatni ta'minlash boshqarmasi", "sifat", "SIFAT"),
                              ("Yuridik bo'lim", "yuridik", "YURIST"), ("Devonxona", "devonxona", "DEVON"),
                              ("Marketing bo'limi", "marketing", "MARKETING"), ("Xarid bo'limi", "xarid", "XARID")]:
        if not db.one(con, "SELECT 1 x FROM users WHERE role=?", (_role,)):
            con.execute("INSERT INTO users(full_name,role,link_code,pin) VALUES(?,?,?,?)", (_nm, _role, _code, rbac.hash_password(rbac.DEMO_PASSWORD)))
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
    # Kameralar: fon so'rovchisi va voqea tinglovchilari doim ishga tushadi, lekin «cams»/«spaces» bo'limi o'chiq bo'lsa hech narsa
    # qilmaydi (har aylanishda MODS.cams_on() tekshiriladi — sahifadan yoqilsa, qayta ishga tushirishsiz ishlay boshlaydi).
    # Simulyator kameralari faqat ISFT_CORE_CAM_SIM=1 bo'lganda so'raladi (app/occupancy.py).
    asyncio.create_task(OC.poller())
    asyncio.create_task(OC.events_supervisor())   # Hikvision voqealar oqimi tinglovchilari
    asyncio.create_task(OPSM.poller())   # qoidalar har 10 daqiqada qayta hisoblanadi
    from . import studio as _STU
    asyncio.create_task(_STU.poller())   # studiya: lease muddati o'tgan montajlar va YouTube navbati («studio» bo'limi o'chiq bo'lsa — hech narsa)

@app.on_event("startup")
async def _bot_start():   # Telegram bot shu jarayonda (TELEGRAM_BOT_TOKEN bo'lsa); token yo'q — faqat log
    try:
        from . import bot as BOT
        await BOT.start_in_app(con)
    except Exception as e:
        print("Telegram bot ishga tushmadi:", type(e).__name__)

@app.on_event("shutdown")
async def _bot_stop():
    try:
        from . import bot as BOT
        await BOT.stop_in_app()
    except Exception as e:
        print("Telegram bot to'xtatishda xato:", type(e).__name__)

from . import sessions as SS
SS.init(con)
COOKIE = "sid"

def ctx(request: Request) -> rbac.Ctx:
    uid = SS.resolve(con, request.cookies.get(COOKIE))
    if not uid:
        raise HTTPException(401, "Kirish talab qilinadi")
    try:
        c = rbac.ctx_for(con, uid)
    except AccessDenied as e:
        raise HTTPException(401, str(e))
    if c.user.get("active") == 0 or c.role.legacy:   # accounts.py: faolsizlantirilgan / bekor qilingan lavozimdagi akkaunt sessiyasi ishlamaydi
        raise HTTPException(401, "Akkaunt faol emas")
    return c

@app.exception_handler(AccessDenied)
async def denied(_, e: AccessDenied):
    return JSONResponse({"denied": True, "message": str(e)}, status_code=403)

class Login(BaseModel):
    user_id: int
    password: str = ""
    pin: str = ""      # eski mijozlar uchun

def _login_item(u, demo: bool, dup: set) -> dict:
    """Kirish ro'yxati uchun bitta qator. Kirishdan oldin shaxsiy ma'lumot (F.I.Sh., rasm) berilmaydi — faqat lavozim nomi;
    bir xil nomli akkauntlar (tyutorlar, bo'lim xodimlari) akkaunt raqami bilan farqlanadi. Namoyish rejimida (ISFT_CORE_SHOW_DEMO_PASSWORD=1)
    avvalgidek ism va rasm ham chiqadi."""
    t = rbac.user_title(u)
    it = {"id": u["id"], "role": t, "level": rbac.ROLES[u["role"]].level}
    if demo: it.update(name=u["full_name"], photo=photo_of(u))
    elif t in dup: it["hint"] = f"akkaunt № {u['id']}"
    if u["role"] == "tyutor": it["search_only"] = True
    return it

@app.get("/api/public/core.js")
def public_core_js():
    """Kirish sahifasidan oldin sinxron o'qiladigan ochiq sozlamalar (static/index.html). Sinov paroli faqat ISFT_CORE_SHOW_DEMO_PASSWORD=1 da."""
    demo = MODS.show_demo_password()
    f = {"real_data": MODS.real_data(), "demo_login": demo, "demo_pw": rbac.DEMO_PASSWORD if demo else ""}
    body = f"window.ISFT_FLAGS={_json.dumps(f)};\n" + ("" if demo else "window.ISFT_HIDE_DEMO_HINT=true;\n")
    return Response(body, media_type="application/javascript", headers={"Cache-Control": "no-store"})

@app.get("/api/users")
def users():
    us = db.rows(con, "SELECT * FROM users ORDER BY id")
    # "Kafedralar" bo'limida kafedra mudirlari va o'qituvchilar (Taqdimot, Vazifalar va testlar); tyutorlar (38 ta) ro'yxatni
    # to'ldirib yubormasligi uchun faqat qidiruvda chiqadi (search_only)
    us = [u for u in us if rbac.ROLES[u["role"]].level != 4 or u["role"] in ("kafedra", "oqituvchi", "tyutor")]
    us = [u for u in us if u.get("active") != 0 and not rbac.ROLES[u["role"]].legacy]   # faolsizlantirilgan / bekor qilingan lavozim — ro'yxatda yo'q
    us.sort(key=lambda u: (rbac.ROLES[u["role"]].level, u.get("department_id") or 0, u["id"]))
    demo = MODS.show_demo_password()
    seen, dup = set(), set()
    for u in us:
        t = rbac.user_title(u)
        (dup if t in seen else seen).add(t)
    return [_login_item(u, demo, dup) for u in us]

# Proksi ortidagi mijoz manzili. start.sh uvicorn'ni --forwarded-allow-ips='*' bilan ishga tushiradi, ya'ni request.client.host —
# X-Forwarded-For ning ENG CHAPDAGI qiymati, uni esa mijozning o'zi yozib yuborishi mumkin (urinishlar cheklovini chetlab o'tish).
# Shuning uchun sarlavhani o'zimiz o'qiymiz: ishonchli proksilar soni N bo'lsa (ISFT_CORE_TRUSTED_PROXIES, standart 1 — Railway),
# haqiqiy mijoz — o'ngdan N-chi yozuv (uni oxirgi ishonchli proksi qo'shgan, mijoz soxtalashtira olmaydi).
# N=0 — proksi yo'q: sarlavha butunlay e'tiborga olinmaydi. Sarlavha yo'q (lokal ishga tushirish) — to'g'ridan-to'g'ri ulanish manzili.
import ipaddress as _ipa
try: TRUSTED_PROXIES = max(0, int(os.getenv("ISFT_CORE_TRUSTED_PROXIES", "1")))
except ValueError: TRUSTED_PROXIES = 1

def _ip(request: Request) -> str:
    peer = (request.client.host if request.client else "") or "?"
    if TRUSTED_PROXIES <= 0: return peer
    hops = [h.strip() for h in ",".join(request.headers.getlist("x-forwarded-for")).split(",") if h.strip()]
    if not hops: return peer
    cand = hops[-TRUSTED_PROXIES] if len(hops) >= TRUSTED_PROXIES else hops[0]
    if cand.startswith("[") and "]" in cand: cand = cand[1:cand.index("]")]            # [IPv6]:port
    elif cand.count(":") == 1: cand = cand.split(":")[0]                                # IPv4:port
    # DIQQAT: bu yerda `peer` ga qaytib bo'lmaydi — uvicorn --proxy-headers uni sarlavhaning chap (mijoz yozgan) qiymatiga almashtirgan bo'lishi mumkin
    for h in [cand] + hops[::-1]:
        try:
            return str(_ipa.ip_address(h))
        except ValueError:
            continue
    return "?"

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
            rbac.audit(con, rbac.Ctx(u, rbac.ROLES[u["role"]]), "tizimga kirish", "auth", False, f"noto'g'ri parol · IP {ip} · {SS.device(request.headers.get('user-agent', ''))}")
        raise HTTPException(401, "Parol noto'g'ri" + (f" · yana {left} ta urinish qoldi" if 0 < left < 3 else ""))
    if u.get("active") == 0 or rbac.ROLES[u["role"]].legacy:   # faolsizlantirilgan akkaunt yoki bekor qilingan lavozim (sobiq dekan #13)
        rbac.audit(con, rbac.Ctx(u, rbac.ROLES[u["role"]]), "tizimga kirish", "auth", False, f"akkaunt faol emas · IP {ip}")
        raise HTTPException(403, "Akkaunt faolsizlantirilgan. AT bo'limiga murojaat qiling.")
    SS.LOGIN_USER.reset(body.user_id)
    if not str(u["pin"]).startswith("pbkdf2$"):   # eski ochiq yozuvni xeshga o'tkazamiz
        u = dict(u); u["pin"] = rbac.hash_password(pw)
        con.execute("UPDATE users SET pin=? WHERE id=?", (u["pin"], u["id"])); con.commit()
    c = rbac.Ctx(u, rbac.ROLES[u["role"]])
    ua = request.headers.get("user-agent", "")
    rbac.audit(con, c, "tizimga kirish", "auth", True, f"IP {ip} · {SS.device(ua)}")
    response.set_cookie(COOKIE, SS.create(con, u, ip, ua), httponly=True, samesite="lax", max_age=SS.TTL,
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
            "labels": rbac.LABELS, "today": clock.today().isoformat(),
            "modules": MODS.state(), "flags": MODS.flags()}   # bo'limlar kaliti (mahsulot sozlamasi, xavfsizlik chegarasi emas)

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
    return SECTIONS[name](con, ctx(request))   # audit jurnali: rektor, kengash, AT bo'limi boshlig'i (rbac.AUDIT)

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

# Eski bir bosishli endpointlar (POST /api/meetings, /api/meetings/extract, /api/tasks/{tid}/status) olib tashlandi: UI ularni chaqirmas,
# kotib qoralama → rahbar tasdig'i oqimini (app/decisions.py: /api/dec/…) chetlab o'tar edi.

class Doc(BaseModel):
    text: str
    mode: str

@app.post("/api/doc")
async def doc(body: Doc, request: Request):
    c = ctx(request)
    if body.mode not in ("translate", "contract", "reply"): raise HTTPException(400)
    if c.role.level > 3:
        raise AccessDenied("⛔ Tarjima va shartnoma yordamchisi rahbariyat va bo'limlar uchun.")
    rbac.audit(con, c, f"tarjima va shartnoma yordamchisi: {body.mode}", "docs", True, body.text[:80])
    return await ai.doc_assist_result(body.text, body.mode)   # {"result", "ai", "source", "reason"} — Tahlil rejimida ai=false

RBAC_FULL_VIEW = ("rektor", "kengash", "it_head")   # to'liq jadval: rahbariyat va tizim ma'muri; boshqalar — faqat o'z lavozimi

@app.get("/api/rbac")
def rbac_matrix(request: Request):
    c = ctx(request)
    rows = rbac.matrix()
    full = c.role.key in RBAC_FULL_VIEW
    return {"roles": rows if full else [r for r in rows if r["key"] == c.role.key], "labels": rbac.LABELS, "full": full}

@app.get("/api/status")
async def status():
    a = await ai.llm_status()
    try:
        from . import bot as BOT
        b = {k: v for k, v in BOT.status().items() if k in ("enabled", "running", "username", "mode", "note", "last_error", "error_at", "started_at", "next_brief", "next_portal")}
    except Exception as e:
        b = {"enabled": False, "running": False, "username": None, "last_error": type(e).__name__}
    try:
        from . import taqdimot as _TQ
        tq = _TQ.status()
    except Exception as e:
        tq = {"engine": None, "error": type(e).__name__}
    try:
        from . import tekshiruv as _TK
        tk = _TK.status()
    except Exception as e:
        tk = {"engine": None, "error": type(e).__name__}
    return {"llm": a["ai"], "model": ai.MODEL, "ai": a, "bot": b, "taqdimot": tq, "tekshiruv": tk, "db": str(db.DB_PATH.name),
            "students": db.one(con, "SELECT COUNT(*) n FROM students")["n"],
            "audit": db.one(con, "SELECT COUNT(*) n FROM audit_log")["n"]}

@app.get("/healthz")
def healthz():   # Railway healthcheck: faqat baza (Ollama/Telegram tekshirilmaydi)
    try:
        db.one(con, "SELECT 1 x")
        return {"ok": True}
    except Exception:
        return JSONResponse({"ok": False, "error": "db"}, status_code=503)


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
          {f"<tr><th>Imzolangan</th><td>{_e(d['signed_at'][:10])}</td></tr>" if d.get('signed_at') else ''}
          {f"<tr><th>Bergan bo'lim</th><td>{_e(d['issuer'])}</td></tr><tr><th>Xodim</th><td>{_e(d['issued_by'])}</td></tr><tr><th>Berilgan vaqt</th><td>{_e(d['issued_at'])}</td></tr>" if d.get('issuer') else ''}</table>"""
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

MODS.bind(con, ctx)
app.include_router(MODS.router)
SV.bind(con, ctx)
app.include_router(SV.router)
OC.bind(con, ctx)
app.include_router(OC.router)
from . import camsec as CS   # kameralar: xavfsizlik voqealari, salomatlik, navbat, haftalik hisobot
CS.bind(con, ctx)
app.include_router(CS.router)
from . import facecam as FC   # Kirish nazorati (Face ID): rozilik reyestri, kirish kameralari, sintetik demo kadrlar
FC.init(con)
FC.bind(con, ctx)
app.include_router(FC.router)
DEC.bind(con, ctx)
app.include_router(DEC.router)
OPSM.bind(con, ctx)
app.include_router(OPSM.router)
from . import registrar as RGM   # Registrator ofisi: ish stoli, imtihonga ruxsatnoma, shaxsiy grafik, otrabotka skanini o'qish
RGM.init(con)
RGM.bind(con, ctx)
app.include_router(RGM.router)
from . import agent_hub as AH
AH.init(con)
AH.bind(con, ctx)
app.include_router(AH.router)
from . import portal as PT   # bo'limlararo portal: yozishmalar, fayllar, umumiy bazalar
PT.init(con)
try: AH.scan(con)   # yangi bazada AH.init paytida org_units hali yo'q edi (brief/ijro skanerlari) — endi bor, qayta skan (idempotent)
except Exception as e: print("agent_hub.scan (portal'dan keyin):", e)
PT.bind(con, ctx)
app.include_router(PT.router)
from . import extras as XT   # parolni o'zgartirish, global qidiruv, bildirishnomalar, kalendar
XT.init(con)
XT.bind(con, ctx)
app.include_router(XT.router)
from . import mywork as MW   # «Mening vazifalarim»: majlis, portal, markaz, imzo va AI takliflari — bitta ro'yxat
MW.bind(con, ctx)
app.include_router(MW.router)
from . import accounts as AC   # akkauntlar boshqaruvi (AT bo'limi boshlig'i): yaratish, parol tiklash, faolsizlantirish
AC.init(con)
AC.bind(con, ctx)
app.include_router(AC.router)
from . import directives as DIR   # ierarxik topshiriqlar (majlisdan tashqari): vakolat, taqsimlash, qabul/qaytarish; demo xodim va zanjirlar
DIR.init(con)
DIR.bind(con, ctx)
app.include_router(DIR.router)
from . import syllabus as SY   # O'quv dasturlari: sillabus oqimi, tayanch OTM solishtiruvi, yuklama kalkulyatori, kafedralarga so'rovlar
SY.init(con)
SY.bind(con, ctx)
app.include_router(SY.router)
from . import staff_absence as SA   # Xodimlar ta'tili: safar, mehnat ta'tili, kasallik varaqasi → dars jadvaliga ta'siri, o'rinbosarlar, tahlil
SA.init(con)
SA.bind(con, ctx)
app.include_router(SA.router)
from . import orders as ORD   # Buyruqlar: arizadan buyruq, reyestr va muvofiqlik auditi, ro'yxat versiyalari, rektor imzosi → bazaga ta'sir
ORD.init(con)
ORD.bind(con, ctx)
app.include_router(ORD.router)
from . import academic_flows as AF   # Talaba harakati: sessiya jadvali, apellyatsiya, qayta o'qish, ko'chirish, ISFT granti, bitiruv (ORD.bind dan keyin)
AF.init(con)
AF.bind(con, ctx)
app.include_router(AF.router)
from . import reyting as RT   # Reyting: talabalar o'zlashtirish reytingi (GPA), qaydnoma, dinamika, a'lochilar, bo'linmalar
RT.init(con)   # kesh (rating_cache) yo'q yoki manba o'zgargan bo'lsa — mavjud baholardan quriladi; qayta seed shart emas
RT.bind(con, ctx)
app.include_router(RT.router)
from . import talaba_karta as TKR   # Talaba kartasi (360°): bitta talaba haqidagi hamma bo'limlar bir joyda (ko'lam — Talabalar markazi)
TKR.bind(con, ctx)
app.include_router(TKR.router)
from . import student_portal as STP   # Talaba kabineti (/talaba): HEMIS ID + parol, alohida sessiya; xodimlar uchun «Talaba murojaatlari» (/talaba/xodim)
STP.init(con)
STP.bind(con, ctx)
app.include_router(STP.router)
from . import xalqaro as XQ   # Xalqaro hamkorlik: shartnomalar hayotiy sikli (yuridik → rektor imzosi → muddat), mobillik tanlovi, xorijiy talabalar vizasi, delegatsiyalar
XQ.init(con)
XQ.bind(con, ctx)
app.include_router(XQ.router)

from . import masofaviy as DL   # Masofaviy ta'lim: LMS faolligi, o'quv kontenti monitoringi, xavf ostidagilar, AI xulosa va hisobot (docs/masofaviy.md)
DL.init(con)   # jadvallar, qoidalar, demo akkauntlar va demo ma'lumot (idempotent — qayta seed shart emas)
DL.bind(con, ctx)
app.include_router(DL.router)
from . import testbank as TB   # Test bank: mavzu matni → AI savollar (Claude) → qoidaviy sifat nazorati → tasdiq → oraliq banklari, Moodle XML/GIFT/Aiken/.docx (docs/testbank.md)
TB.init(con)   # jadvallar va namuna savollar (idempotent; kurslar/mavzular — masofaviy dl_courses/dl_items dan)
TB.bind(con, ctx)
app.include_router(TB.router)
from . import paket as PK   # Kontent paketlari: mavzu manbalari (matn+reja, taqdimot, YouTube, tasdiqlangan test) → SCORM 1.2 / 2004 / xAPI zip (docs/paket.md)
PK.init(con)   # jadvallar va namuna (TB.init dan keyin — Test bank namuna matni va savollari ishlatiladi)
PK.bind(con, ctx)
app.include_router(PK.router)
from . import studio as STU   # Studiya: dars ishlab chiqarish — syomka bandi, AI montaj navbati (ishchi API /api/montaj), YouTube, avtomatik paket (docs/studio.md)
STU.init(con)   # jadvallar, standart «Studiya» xonasi, operator demo akkaunti, namuna bandlar (PK.init dan keyin)
STU.bind(con, ctx)
app.include_router(STU.router)
from . import moliya as MOL   # Moliya: to'lovlar reyestri (qo'lda), kunlik solishtirish, byudjet ijrosi, xarajat tasdig'i, xarid moliyalashtirish, oylik hisobotlar
MOL.init(con)
MOL.bind(con, ctx)
app.include_router(MOL.router)

from . import amaliyot as AML   # Amaliyot: bazalar reyestri (shartnoma, sig'im), davrlar (o'quv reja / jadval), biriktirish, yo'llanma, kundalik, hisobot, baho
AML.init(con)
AML.bind(con, ctx)
app.include_router(AML.router)
from . import ilmiy as ILM   # Ilmiy faoliyat: nashrlar (kafedra → Ilmiy bo'lim tasdig'i → reyestr), grantlar va hisobotlar, magistrlik dissertatsiyasi bosqichlari
ILM.init(con)
ILM.bind(con, ctx)
app.include_router(ILM.router)
from . import kadrlar as KDR   # Kadrlar: shaxsiy ish, ishga qabul (vakansiya → nomzod → buyruq → AT so'rovi), bo'shatish varaqasi, shartnoma muddatlari, attestatsiya, shtat jadvali
KDR.init(con)
KDR.bind(con, ctx)
app.include_router(KDR.router)

from . import yoshlar as YJ   # Yoshlar ishlari: hamkor yotoqxonalar (ariza → navbat → joy → to'lov → tartib), ijara monitoringi, tadbirlar (reja → tasdiq → hisobot)
YJ.init(con)
YJ.bind(con, ctx)
app.include_router(YJ.router)
from . import taqdimot as TQD   # Taqdimot: o'qituvchi materiali (.docx/.pdf/.txt) → reja (Claude API yoki AI siz) → ISFT shablonida .pptx
TQD.init(con)
TQD.bind(con, ctx)
app.include_router(TQD.router)
from . import tekshiruv as TKS   # Ishlarni tekshirish: o'qituvchi talaba ishlarini yuklaydi → AI taklifi (Claude yoki qo'lda) → o'qituvchi tasdiqlaydi
TKS.init(con)
TKS.bind(con, ctx)
app.include_router(TKS.router)
from . import devon as DVN, qabul as QBL, rejalar as RJL, it_requests as ITR   # Kiruvchi xatlar (Devonxona), Qabul (abituriyentlar), KPI maqsadlari / Sifat amallari, AT akkaunt so'rovlari
for _m in (DVN, QBL, RJL, ITR):
    _m.init(con); _m.bind(con, ctx); app.include_router(_m.router)
class _NoCacheStatic(StaticFiles):
    """JS/CSS/HTML har safar ETag bilan qayta tekshiriladi — yangi deploydan keyin brauzer eski kodni ishlatib qolmasin."""
    async def get_response(self, path, scope):
        r = await super().get_response(path, scope)
        if str(path).endswith((".js", ".css", ".html")) or path in ("", ".", "/"): r.headers["Cache-Control"] = "no-cache"
        return r

app.mount("/", _NoCacheStatic(directory=ROOT / "static", html=True), name="static")
