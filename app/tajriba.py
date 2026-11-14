"""Aralashuvlar tajribasi va to'siq nuqtalaridagi eslatmalar (docs/keyslar.md).

Nima uchun (dalil): ommaviy eslatmalar qolishga deyarli ta'sir qilmaydi (Oreopoulos — 9 000+ talabali RCT: nol; FAFSA SMS milliy takrorlashda
nol). Shuning uchun Telegram eslatmalari faqat aniq TO'SIQ NUQTALARIDA yuboriladi va ta'siri guruhlararo tajriba bilan o'lchanadi —
«yaxshilanishga o'xshagan narsa» sababiy bo'lmasligi mumkin (Purdue Course Signals).

1. To'siq nuqtalari (TRIGGERS):
   t_login     — semestrning 3-kunigacha talaba kabinetiga birinchi marta kirmagan va LMS faolligi yo'q (semestrda bir marta; Telegram ulanmagan
                 bo'lishi tabiiy — SMS navbati, telefon bo'lmasa Telegram navbati);
   t_due48     — dars muddatiga 48 soatdan kam qoldi va dars bajarilmagan (haftalik taqvim — app/haftalik.py; bitta muddat sanasi uchun bitta xabar);
   t_inactive7 — boshlagan talaba 7+ kun faolliksiz (har faolsizlik davri uchun bir marta).
   Cheklovlar: bitta talabaga avtomatik eslatmalar orasida ≥ gap_hours (48) soat va 7 kunda ≤ week_max (2) ta; kuniga jami ≤ daily_max.
   Har hodisa tj_events jurnalida (dedupe kaliti — UNIQUE, qayta yuborilmaydi), yuborilgani — ops_notices + notice_delivery (app/talaba_darslar).

2. Tajriba (har aralashuv uchun rejim): off — o'chiq; all — hammaga; tajriba — guruhlarning tasodifiy yarmiga. Guruh qo'li barqaror:
   sha256(«kalit|tuz|guruh id») juft/toq — guruh har doim bir xil qo'lda, tuz yangi tajriba boshlanganda almashadi. Nazorat qo'lidagi mos
   hodisalar ham yoziladi (yuborilmaydi) — taqqoslash niyat bo'yicha (ITT): cheklov tufayli yuborilmaganlar ham tajriba qo'lida qoladi.

3. Taqqoslash (compare — sof funksiya): natija — hodisadan keyin 7 kun ichida LMS faolligi (qayta faollashish) va 14 kun ichida yakunlangan darslar.
   Randomizatsiya birligi — guruh, shuning uchun farqning ishonch oralig'i GURUHLAR darajasida (har guruh ulushi — bitta kuzatuv, Welch t,
   95 %) hisoblanadi; guruhlar < 2 bo'lsa — oraliq hisoblanmaydi. Ogohlantirishlar: kichik tanlov, oraliq 0 ni qamrashi, oynasi tugamagan hodisalar.

Ruxsat: ko'rish — bo'lim (masofaviy, masofaviy_xodim) va rahbariyat (rektor, prorektor_oquv — faqat jamlangan); rejim va cheklovlar — bo'lim
boshlig'i (audit bilan).
"""
from __future__ import annotations
import datetime as dt, hashlib, json, math, secrets, statistics, threading
from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel, Field
from . import clock, db, rbac, lrs_analytics as LA
from .rbac import Ctx, AccessDenied

router = APIRouter()
_con = None
_ctx = None
_lock = threading.RLock()
P = "/api/ortda/tajriba"
RES = "lrs"
HEAD, STAFF = "masofaviy", "masofaviy_xodim"
DEPT = (HEAD, STAFF)
VIEW = DEPT + ("rektor", "prorektor_oquv")

TRIGGERS = {
    "t_login": ("Birinchi kirish yo'q (semestrning 3-kuni)", "Semestr boshlanganiga 2 kun o'tdi, talaba kabinetga hali kirmagan va LMS faolligi yo'q"),
    "t_due48": ("Dars muddatiga 48 soat qoldi", "Haftalik taqvim bo'yicha dars muddati 48 soat ichida tugaydi, dars hali bajarilmagan"),
    "t_inactive7": ("7 kun faolsiz", "Kursni boshlagan talaba 7 kundan beri LMS'ga kirmagan"),
}
MODES = {"off": "O'chiq", "all": "Hammaga", "tajriba": "Tajriba: guruhlarning yarmiga"}
ARMS = {"tajriba": "Tajriba (eslatma)", "nazorat": "Nazorat (eslatmasiz)", "hammasi": "Hammaga"}
LIMITS = [("gap_hours", 48, "Bitta talabaga avtomatik eslatmalar orasidagi eng kam vaqt (soat)", (12, 336)),
          ("week_max", 2, "Bitta talabaga 7 kunda eng ko'p avtomatik eslatma", (1, 7)),
          ("daily_max", 500, "Kuniga jami avtomatik eslatmalar", (1, 5000))]
REENG_DAYS, PROG_DAYS = 7, 14

SCHEMA = """
CREATE TABLE IF NOT EXISTS tj_experiments(key TEXT PRIMARY KEY, mode TEXT DEFAULT 'off', salt TEXT, started_at TEXT, updated_at TEXT, updated_by TEXT);
CREATE TABLE IF NOT EXISTS tj_events(id INTEGER PRIMARY KEY, ts TEXT, key TEXT, salt TEXT, student_id INT, group_id INT, course_ref TEXT, arm TEXT,
  sent INT DEFAULT 0, status TEXT, notice_id INT, dedupe TEXT UNIQUE, detail TEXT);
CREATE INDEX IF NOT EXISTS ix_tj_ev ON tj_events(key, salt, arm);
CREATE INDEX IF NOT EXISTS ix_tj_ev_st ON tj_events(student_id, ts);
CREATE TABLE IF NOT EXISTS tj_limits(k TEXT PRIMARY KEY, v INT);
"""

def init(con):
    con.executescript(SCHEMA)
    for k in TRIGGERS:
        con.execute("INSERT OR IGNORE INTO tj_experiments(key,mode,salt,started_at) VALUES(?,?,?,?)", (k, "off", secrets.token_hex(4), None))
    con.commit()

def bind(con, ctx_fn):
    global _con, _ctx
    _con, _ctx = con, ctx_fn

def _now() -> dt.datetime: return clock.now().replace(microsecond=0)
def _iso(t) -> str: return t.replace(microsecond=0).isoformat(timespec="seconds")
def _P(s):
    try: return dt.datetime.fromisoformat(str(s)[:19]) if s else None
    except ValueError: return None

def limits(con=None) -> dict:
    con = con or _con
    have = {r["k"]: r["v"] for r in db.rows(con, "SELECT k, v FROM tj_limits")}
    return {k: int(have.get(k, v)) for k, v, _, _ in LIMITS}

def experiments(con=None) -> dict:
    con = con or _con
    return {r["key"]: r for r in db.rows(con, "SELECT * FROM tj_experiments")}


# =============================================================================================
# Sof funksiyalar: qo'l, taqqoslash
# =============================================================================================
def arm(key: str, salt: str, group_id) -> str:
    """Barqaror guruh qo'li: sha256 juft/toq. Bir xil (kalit, tuz, guruh) — har doim bir xil qo'l."""
    h = hashlib.sha256(f"{key}|{salt}|{int(group_id or 0)}".encode()).digest()
    return "tajriba" if h[0] % 2 == 0 else "nazorat"

_T95 = {1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447, 7: 2.365, 8: 2.306, 9: 2.262, 10: 2.228, 12: 2.179, 15: 2.131, 20: 2.086,
        25: 2.060, 30: 2.042, 40: 2.021, 60: 2.000, 120: 1.980}
def t95(df: float) -> float:
    """Ikki tomonlama 95 % t kritik qiymati (jadval, oraliqda — yuqoriga yaqin, ya'ni ehtiyotkor)."""
    if df is None or df < 1: return float("nan")
    for k in sorted(_T95):
        if df <= k: return _T95[k]
    return 1.96

def compare(rows: list[dict], min_groups: int = 5, min_n: int = 30) -> dict:
    """rows: [{group, arm (tajriba|nazorat), y (0/1 — qayta faollashdi), lessons (yakunlangan darslar soni)}] — bitta talaba bitta qator.
    → {arms: {qo'l: {n, groups, rate, lessons}}, diff (tajriba − nazorat, foiz punkt), ci (95 %, guruhlar darajasida) | None,
       diff_lessons, ci_lessons, caveats: [...]}."""
    out = {"arms": {}, "diff": None, "ci": None, "diff_lessons": None, "ci_lessons": None, "caveats": []}
    per: dict = {}
    for r in rows:
        if r.get("arm") not in ("tajriba", "nazorat"): continue
        g = per.setdefault(r["arm"], {}).setdefault(r["group"], [])
        g.append(r)
    gm: dict = {}
    for a in ("tajriba", "nazorat"):
        gs = per.get(a, {})
        allr = [x for v in gs.values() for x in v]
        n = len(allr)
        out["arms"][a] = {"n": n, "groups": len(gs), "rate": round(100 * sum(x["y"] for x in allr) / n, 1) if n else None,
                          "lessons": round(sum(x.get("lessons") or 0 for x in allr) / n, 2) if n else None}
        gm[a] = ([100 * sum(x["y"] for x in v) / len(v) for v in gs.values()], [sum(x.get("lessons") or 0 for x in v) / len(v) for v in gs.values()])
    A, B = out["arms"]["tajriba"], out["arms"]["nazorat"]
    if A["n"] and B["n"]:
        out["diff"] = round(A["rate"] - B["rate"], 1)
        out["diff_lessons"] = round(A["lessons"] - B["lessons"], 2)
        def welch(xs, ys):
            if len(xs) < 2 or len(ys) < 2: return None
            vx, vy = statistics.variance(xs), statistics.variance(ys)
            se = math.sqrt(vx / len(xs) + vy / len(ys))
            d = statistics.mean(xs) - statistics.mean(ys)
            if se == 0: return (round(d, 2), round(d, 2))
            num = (vx / len(xs) + vy / len(ys)) ** 2
            den = (vx / len(xs)) ** 2 / (len(xs) - 1) + (vy / len(ys)) ** 2 / (len(ys) - 1)
            df = num / den if den else len(xs) + len(ys) - 2
            t = t95(df)
            return (round(d - t * se, 1), round(d + t * se, 1))
        out["ci"] = welch(gm["tajriba"][0], gm["nazorat"][0])
        ci2 = welch(gm["tajriba"][1], gm["nazorat"][1])
        out["ci_lessons"] = (round(ci2[0], 2), round(ci2[1], 2)) if ci2 else None
    cv = out["caveats"]
    if not A["n"] or not B["n"]: cv.append("Qo'llardan birida hodisa yo'q — taqqoslab bo'lmaydi.")
    if min(A["groups"], B["groups"]) < 2:
        cv.append("Har qo'lda kamida 2 ta guruh bo'lmaguncha ishonch oralig'i hisoblanmaydi (randomizatsiya birligi — guruh).")
    elif min(A["groups"], B["groups"]) < min_groups:
        cv.append(f"Guruhlar soni kam ({A['groups']} va {B['groups']}) — ishonch oralig'i keng, natija ishonchsiz.")
    if min(A["n"], B["n"]) < min_n: cv.append(f"Talabalar soni kam ({A['n']} va {B['n']}; har qo'lda kamida {min_n} tavsiya etiladi).")
    if out["ci"] and out["ci"][0] <= 0 <= out["ci"][1]: cv.append("Ishonch oralig'i 0 ni o'z ichiga oladi — farq statistik jihatdan aniqlanmadi.")
    cv.append("Oraliq guruhlar darajasida (har guruh ulushi — bitta kuzatuv, Welch t, 95 %); talabalar bo'yicha ulushlar — tavsif uchun.")
    return out


# =============================================================================================
# To'siq nuqtalari: nomzodlar
# =============================================================================================
def _sem_start() -> dt.date:
    from . import academic_rules as AR
    return dt.date.fromisoformat(AR.term_dates(AR.CURRENT_SEMESTER)[0])

def candidates(now: dt.datetime) -> list[dict]:
    """Hozir mos keladigan hodisalar: [{key, student_id, group_id, course_ref, dedupe, text_args}]. Bazaga yozmaydi."""
    from . import ortda as ORT, haftalik as H
    today = now.date()
    out = []
    start = _sem_start()
    studs = {r["id"]: r for r in db.rows(_con, """SELECT s.id, s.full_name, s.phone, s.group_id, a.last_login FROM students s JOIN groups_ g ON g.id=s.group_id
                                                LEFT JOIN student_auth a ON a.student_id=s.id WHERE s.study_form='masofaviy' AND s.status='faol' AND g.form='masofaviy'""")}
    # 1) birinchi kirish yo'q — semestrning 3-kuni va undan keyin (semestrda bir marta)
    if today >= start + dt.timedelta(days=2):
        active = {r["s"] for r in db.rows(_con, "SELECT DISTINCT student_id s FROM lrs_statements WHERE voided=0 AND ts>=?", (start.isoformat(),))}
        for sid, s in studs.items():
            if s["last_login"] or sid in active: continue
            out.append({"key": "t_login", "student_id": sid, "group_id": s["group_id"], "course_ref": "", "dedupe": f"t_login:{sid}:{start}", "args": {}})
    # 2) va 3) — kurslar bo'yicha (haftalik taqvim, lrs_progress)
    due_by: dict = {}
    for co in ORT._course_rows():
        if co.get("ready"): continue
        rows = {r["student_id"]: r for r in ORT.course_rows(co)}
        if not rows: continue
        ls = ORT.lessons_of(co)
        prog: dict = {}
        for r in db.rows(_con, "SELECT student_id, lesson_ref, status FROM lrs_progress WHERE course_ref=?", (co["ref"],)):
            prog.setdefault(r["student_id"], {})[r["lesson_ref"]] = r["status"]
        plans: dict = {}
        for sid, r in rows.items():
            if sid not in studs: continue
            gid = r["group_id"]
            if gid not in plans: plans[gid] = H.plan(co, gid, ls)["items"]
            pr = prog.get(sid, {})
            for it in plans[gid]:
                end = dt.datetime.combine(it["due"], dt.time(23, 59))
                if it["release"] <= today and now < end <= now + dt.timedelta(hours=48) and pr.get(it["ref"]) not in LA.DONE_ST:
                    d = due_by.setdefault((sid, it["due"]), {"group_id": gid, "courses": {}})
                    d["courses"].setdefault(co["title"], []).append(it["code"])
            di = r.get("days_inactive")
            if r.get("last") and di is not None and di >= 7:
                out.append({"key": "t_inactive7", "student_id": sid, "group_id": gid, "course_ref": co["ref"],
                            "dedupe": f"t_inactive7:{sid}:{r['last'][:10]}", "args": {"days": di}})
    for (sid, due), d in due_by.items():
        out.append({"key": "t_due48", "student_id": sid, "group_id": d["group_id"], "course_ref": "", "dedupe": f"t_due48:{sid}:{due}",
                    "args": {"due": due, "courses": d["courses"]}})
    # bitta talabaga bir xil kalit bir necha kursdan kelsa (faolsizlik) — bitta hodisa
    seen, uniq = set(), []
    for x in out:
        if x["dedupe"] in seen: continue
        seen.add(x["dedupe"]); uniq.append(x)
    return uniq

def message(x: dict, s: dict) -> str:
    from . import talaba_darslar as TD
    name = (s["full_name"].split() + [""])[1] or s["full_name"]
    hint = TD.cabinet_hint()
    if x["key"] == "t_login":
        return (f"Hurmatli {name}! ISFT masofaviy ta'lim: semestr boshlandi, lekin siz hali talaba kabinetiga kirmadingiz. Darslaringiz: {hint}. "
                "Kirishda muammo bo'lsa — Masofaviy ta'lim bo'limiga yoki tyutoringizga murojaat qiling.")
    if x["key"] == "t_due48":
        d = x["args"]["due"]
        what = "; ".join(f"«{t}» — {', '.join(cs[:6])}" for t, cs in list(x["args"]["courses"].items())[:3])
        return f"Hurmatli {name}! Darslar muddati {d.day:02d}.{d.month:02d} (yakshanba) kuni tugaydi: {what}. Darslaringiz: {hint}."
    return (f"Hurmatli {name}! Siz {x['args'].get('days', 7)} kundan beri masofaviy darslarga kirmadingiz. Qiyinchilik bo'lsa — tyutoringizga yozing, "
            f"yordam beramiz. Darslaringiz: {hint}.")


# =============================================================================================
# Ishga tushirish (fon va «Hozir tekshirish»)
# =============================================================================================
def run_due(now: dt.datetime | None = None, dry: bool = False, sender=None) -> dict:
    """Yoqilgan aralashuvlar bo'yicha hodisalarni yozish va (tajriba / hammaga qo'lida) yuborish. dry — faqat hisob (bazaga yozmaydi)."""
    from . import talaba_darslar as TD
    now = now or _now()
    ex = experiments()
    on = {k: e for k, e in ex.items() if e["mode"] in ("all", "tajriba")}
    st = {"eligible": 0, "sent": 0, "control": 0, "limited": 0, "dup": 0, "by": {}}
    if not on: return st
    lim = limits()
    cands = [x for x in candidates(now) if x["key"] in on]
    sids = {x["student_id"] for x in cands}
    info = {r["id"]: r for r in db.rows(_con, f"SELECT id, full_name, phone FROM students WHERE id IN ({','.join(map(str, sids)) or '0'})")}
    deliver = []
    with _lock:
        have = {r["dedupe"] for r in db.rows(_con, f"""SELECT dedupe FROM tj_events WHERE dedupe IN ({','.join('?' * len(cands)) or "''"})""",
                                              [x["dedupe"] for x in cands])} if cands else set()
        day0 = _iso(dt.datetime.combine(now.date(), dt.time()))
        n_day = db.one(_con, "SELECT COUNT(*) n FROM tj_events WHERE sent=1 AND ts>=?", (day0,))["n"]
        for x in cands:
            if x["dedupe"] in have: st["dup"] += 1; continue
            e = on[x["key"]]
            a = arm(x["key"], e["salt"], x["group_id"]) if e["mode"] == "tajriba" else "hammasi"
            st["eligible"] += 1
            b = st["by"].setdefault(x["key"], {"eligible": 0, "sent": 0, "control": 0, "limited": 0})
            b["eligible"] += 1
            status, send = "nazorat", False
            if a != "nazorat":
                last = db.one(_con, "SELECT MAX(ts) t FROM tj_events WHERE student_id=? AND sent=1", (x["student_id"],))["t"]
                wk = db.one(_con, "SELECT COUNT(*) n FROM tj_events WHERE student_id=? AND sent=1 AND ts>=?", (x["student_id"], _iso(now - dt.timedelta(days=7))))["n"]
                if last and (now - _P(last)).total_seconds() < lim["gap_hours"] * 3600: status = "cheklov: oraliq"
                elif wk >= lim["week_max"]: status = "cheklov: haftalik"
                elif n_day >= lim["daily_max"]: status = "cheklov: kunlik"
                else: status, send = "yuborildi", True
            if dry:
                st["sent" if send else "control" if a == "nazorat" else "limited"] += 1
                continue
            nid = None
            if send:
                s = info.get(x["student_id"]) or {"full_name": "", "phone": None}
                ch = "sms" if x["key"] == "t_login" and s.get("phone") else "telegram"
                nid = _con.execute("INSERT INTO ops_notices(ts,channel,task_id,case_id,student_id,phone,text,status,user_id) VALUES(?,?,?,?,?,?,?,?,?)",
                                   (_iso(now), ch, None, None, x["student_id"], s.get("phone") if ch == "sms" else None, message(x, s)[:900], "navbatda", None)).lastrowid
                n_day += 1
                if ch == "telegram": deliver.append(nid)
            _con.execute("""INSERT INTO tj_events(ts,key,salt,student_id,group_id,course_ref,arm,sent,status,notice_id,dedupe,detail) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                         (_iso(now), x["key"], e["salt"], x["student_id"], x["group_id"], x["course_ref"], a, int(send), status, nid, x["dedupe"],
                          json.dumps(x["args"], default=str, ensure_ascii=False)[:500]))
            k = "sent" if send else "control" if a == "nazorat" else "limited"
            st[k] += 1; b[k] += 1
        if not dry: _con.commit()
    for nid in deliver:                                     # tarmoq — qulfdan tashqarida
        try: TD.deliver(_con, nid, sender)
        except Exception as e: print("tajriba deliver:", repr(e))
    return st


# =============================================================================================
# Natijalar
# =============================================================================================
def outcomes(key: str) -> dict:
    """Joriy tajriba (tuz) hodisalari bo'yicha taqqoslash: har talabaning shu tajribadagi birinchi hodisasi; oynasi tugaganlar."""
    e = experiments().get(key)
    if not e: raise HTTPException(404, "Aralashuv topilmadi")
    now = _now()
    evs = db.rows(_con, "SELECT * FROM tj_events WHERE key=? AND salt=? ORDER BY id", (key, e["salt"]))
    first: dict = {}
    for v in evs: first.setdefault(v["student_id"], v)
    rows, pending = [], 0
    for sid, v in first.items():
        t = _P(v["ts"])
        if now < t + dt.timedelta(days=REENG_DAYS): pending += 1; continue
        y = db.one(_con, "SELECT 1 x FROM lrs_statements WHERE student_id=? AND voided=0 AND ts>? AND ts<=? LIMIT 1",
                   (sid, v["ts"], _iso(t + dt.timedelta(days=REENG_DAYS))))
        les = db.one(_con, """SELECT COUNT(DISTINCT course_ref||'|'||lesson_ref) n FROM lrs_statements WHERE student_id=? AND voided=0 AND ts>? AND ts<=?
                              AND verb IN ('completed','passed') AND lesson_ref!=''""", (sid, v["ts"], _iso(t + dt.timedelta(days=PROG_DAYS))))["n"]
        rows.append({"group": v["group_id"], "arm": v["arm"], "y": 1 if y else 0, "lessons": les})
    cmp_ = compare(rows)
    if pending: cmp_["caveats"].insert(0, f"Oynasi ({REENG_DAYS} kun) hali tugamagan {pending} ta hodisa hisobga olinmadi.")
    sent = sum(1 for v in evs if v["sent"])
    return {"key": key, "mode": e["mode"], "started_at": e["started_at"], "events": len(evs), "students": len(first), "sent": sent, "pending": pending,
            "hammasi": sum(1 for v in evs if v["arm"] == "hammasi"), **cmp_}

def arms_of_groups(key: str) -> dict:
    """Masofaviy guruhlar qaysi qo'lda (soni) — tajriba rejimida."""
    e = experiments().get(key) or {}
    gs = [r["id"] for r in db.rows(_con, "SELECT id FROM groups_ WHERE form='masofaviy'")]
    a = [arm(key, e.get("salt") or "", g) for g in gs]
    return {"tajriba": a.count("tajriba"), "nazorat": a.count("nazorat")}


# =============================================================================================
# HTTP
# =============================================================================================
def C(request: Request) -> Ctx: return _ctx(request)

def guard(c: Ctx, action: str, roles=VIEW, detail: str = ""):
    ok = c.role.key in roles and c.channel == "web"
    rbac.audit(_con, c, f"tajriba: {action}", RES, ok, detail)
    if not ok: raise AccessDenied(f"⛔ Eslatmalar va tajribalar: {action} — '{c.role.title}' lavozimi uchun ruxsat yo'q. So'rov audit jurnaliga yozildi.")

@router.get(P)
def api_view(request: Request):
    c = C(request); guard(c, "ko'rish")
    ex = experiments()
    since = _iso(_now() - dt.timedelta(days=7))
    cnt = {(r["key"], r["status"]): r["n"] for r in db.rows(_con, "SELECT key, status, COUNT(*) n FROM tj_events WHERE ts>=? GROUP BY 1, 2", (since,))}
    items = []
    for k, (t, d) in TRIGGERS.items():
        e = ex.get(k) or {}
        o = outcomes(k)
        items.append({"key": k, "title": t, "desc": d, "mode": e.get("mode", "off"), "mode_label": MODES.get(e.get("mode", "off")), "started_at": e.get("started_at"),
                      "week": {s: n for (kk, s), n in cnt.items() if kk == k}, "groups": arms_of_groups(k), "result": o})
    log = []
    if c.role.key in DEPT:
        log = db.rows(_con, """SELECT e.ts, e.key, e.arm, e.status, e.notice_id, g.name grp, d.status delivery FROM tj_events e LEFT JOIN groups_ g ON g.id=e.group_id
                               LEFT JOIN notice_delivery d ON d.id=(SELECT MAX(id) FROM notice_delivery WHERE notice_id=e.notice_id) ORDER BY e.id DESC LIMIT 60""")
    return {"items": items, "modes": MODES, "arms": ARMS, "limits": limits(), "limits_meta": [{"k": k, "label": lb, "min": lo, "max": hi} for k, _, lb, (lo, hi) in LIMITS],
            "can_edit": c.role.key == HEAD, "log": log, "windows": {"reeng": REENG_DAYS, "progress": PROG_DAYS},
            "note": "Eslatmalar faqat to'siq nuqtalarida yuboriladi. Ommaviy eslatmalar soni muvaffaqiyat ko'rsatkichi emas — ta'sir faqat tajriba bilan baholanadi."}

class ModeIn(BaseModel):
    key: str = Field(..., max_length=30)
    mode: str = Field(..., max_length=10)
    restart: bool = False

@router.post(P + "/mode")
def api_mode(body: ModeIn, request: Request):
    """Rejim: off | all | tajriba. Tajribani yangidan boshlash (restart) yoki o'chiqdan tajribaga o'tish — yangi tuz (qo'llar qayta taqsimlanadi)."""
    c = C(request); guard(c, "rejimni o'zgartirish", (HEAD,), f"{body.key} → {body.mode}")
    if body.key not in TRIGGERS: raise HTTPException(400, "Noma'lum aralashuv")
    if body.mode not in MODES: raise HTTPException(400, "Rejim: off, all yoki tajriba")
    e = experiments().get(body.key) or {}
    now = _iso(_now())
    new_salt = body.restart or (body.mode == "tajriba" and e.get("mode") != "tajriba")
    with _lock:
        _con.execute("UPDATE tj_experiments SET mode=?, salt=?, started_at=?, updated_at=?, updated_by=? WHERE key=?",
                     (body.mode, secrets.token_hex(4) if new_salt else e.get("salt"), now if new_salt or not e.get("started_at") else e.get("started_at"),
                      now, c.user["full_name"], body.key))
        _con.commit()
    rbac.audit(_con, c, "tajriba: rejim", RES, True, f"{body.key}: {e.get('mode')} → {body.mode}" + (" · yangi tuz" if new_salt else ""))
    return {"ok": True}

@router.post(P + "/limits")
def api_limits(body: dict, request: Request):
    c = C(request); guard(c, "cheklovlarni o'zgartirish", (HEAD,))
    lim = {k: (lo, hi) for k, _, _, (lo, hi) in LIMITS}
    ch = []
    with _lock:
        for k, v in (body or {}).items():
            if k not in lim: raise HTTPException(400, f"Noma'lum cheklov: {k}")
            try: v = int(v)
            except (TypeError, ValueError): raise HTTPException(400, f"{k}: butun son kerak")
            if not lim[k][0] <= v <= lim[k][1]: raise HTTPException(400, f"{k}: {lim[k][0]}–{lim[k][1]} oralig'ida")
            _con.execute("INSERT OR REPLACE INTO tj_limits(k,v) VALUES(?,?)", (k, v)); ch.append(f"{k}={v}")
        _con.commit()
    rbac.audit(_con, c, "tajriba: cheklovlar", RES, True, ", ".join(ch))
    return {"ok": True, "limits": limits()}

@router.post(P + "/run")
def api_run(request: Request, dry: bool = False):
    """«Hozir tekshirish» — fon jarayonini kutmasdan (bo'lim boshlig'i). dry=true — faqat hisob."""
    c = C(request); guard(c, "hozir tekshirish", (HEAD,), "dry" if dry else "")
    return run_due(dry=dry)
