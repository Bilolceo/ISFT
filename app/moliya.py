"""Moliya: Buxgalteriya va Moliya-iqtisod prorektori ish jarayoni (1C/bank importisiz — qo'lda kiritish).

Nima qiladi:
  * To'lovlar reyestri — talaba kontrakt to'lovini kvitansiya/to'lov hujjati bo'yicha qo'lda kiritish (raqam, sana, summa, usul,
    to'lovchi). Kvitansiya raqami takrorlansa (faol yozuvlar orasida) — 409 va mavjud yozuv ko'rsatiladi. Ortiqcha to'lov qabul
    qilinmaydi (qarzdan oshsa — 409). Kiritilgan to'lov darhol students.paid_amount ga qo'shiladi: Talabalar markazi (kontrakt
    qoidasi, call-markaz navbati), Talaba kabineti, Registrator kartasi va panel — barchasi shu maydonni o'qiydi (yagona manba).
    Storno — sabab bilan; paid_amount dan ayiriladi. Yopilgan (solishtirilgan) kun to'lovini faqat moliya prorektori storno qiladi.
  * Kunlik solishtirish — kun bo'yicha usullar kesimida tizimdagi summa va bank/kassa ko'chirmasidagi summa; farq bo'lsa izoh
    majburiy. Yopilgan kunga yangi to'lov kiritilmaydi; qayta ochish — faqat moliya prorektori (sabab bilan).
  * Byudjet ijrosi — yillik byudjet moddalari (reja), fakt = budget jadvalidagi oylik «actual» yig'indisi (panel va hisobotlar
    o'qiydigan yagona jadval). Xarajat kiritilganda: LIMIT dan kichik va moddadan oshirmasa — darhol o'tkaziladi; aks holda
    moliya prorektori tasdig'iga tushadi. Tasdiqlangan xarajat budget(month, category).actual ga qo'shiladi.
    Ogohlantirish: modda ijrosi ≥ 90% — «chegaraga yaqin», > 100% — «oshib ketgan»; tasdiq kutayotgan xarajatlar bilan prognoz.
  * Xarid so'rovlari (app/service.py, procurements) — «buyurtma berildi»/«yetkazildi» holatidagi so'rovni buxgalteriya
    moliyalashtiradi: bog'langan xarajat yaratiladi (procurements.fin_expense_id); tasdiqlangach — «to'langan».
  * Oylik hisobotlar — to'lovlar, solishtirish, byudjet ijrosi: .xlsx yoki .csv.
Ruxsat (rbac.ROLES o'zgartirilmaydi — modul ichidagi qoida, resurslar CONTRACTS va FINANCE):
  buxgalteriya — kiritish (to'lov, storno, solishtirish, xarajat, xarid moliyalashtirish), hammasini ko'rish;
  prorektor_moliya — hammasini ko'rish, xarajatni tasdiqlash/rad etish, yillik rejani o'zgartirish, kunni qayta ochish,
                     yopilgan kun to'lovini storno qilish;
  rektor, kengash — faqat jamlangan ko'rsatkichlar (ism-shariflarsiz);
  talabalar (Registrator ofisi) — talaba bo'yicha to'lov holati va tarixi (faqat o'qish). Call-markaz — avvalgidek Talabalar markazi orqali.
Har bir ko'rish, o'zgartirish va rad etilgan urinish audit jurnaliga yoziladi.
"""
import csv, datetime as dt, difflib, io, json, random, re, sqlite3
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field
from . import clock, db, rbac, moliya_match as MM
from .rbac import AccessDenied, Ctx, CONTRACTS, FINANCE

router = APIRouter()
P = "/api/moliya"
_con = None
_ctx = None

ENTER = {"buxgalteriya"}
APPROVE = {"prorektor_moliya"}
FULL = ENTER | APPROVE
AGG = {"rektor", "kengash"}
STUDENT_READ = {"talabalar"}
LIMIT = 50_000_000          # shundan katta (yoki teng) xarajat — moliya prorektori tasdig'i bilan
WARN_PCT = 90
METHODS = {"bank": "Bank o'tkazmasi", "click": "Click", "payme": "Payme", "uzum": "Uzum", "kassa": "Kassa (naqd)"}
EXP_ST = ["kutilmoqda", "tasdiqlandi", "rad etildi", "bekor qilindi"]
BACKDATE_DAYS = 60
UNMATCHED_ALERT_DAYS = 3   # aniqlanmagan to'lov shuncha kundan ortiq tursa — qizil ogohlantirish
PREFIX = {"bank": "TP", "click": "CL", "payme": "PM", "uzum": "UZ", "kassa": "KO"}
# Yagona kvitansiya reyestri: to'lov turlari (kvitansiya raqami barcha turlar bo'yicha yagona; kunlik solishtirish hammasini qamraydi).
# Talaba harakati (qayta o'qish) va Yoshlar (turar joy) dagi «To'lov» tugmalari shu yerdagi _post_payment orqali o'tadi.
PAY_KINDS = {"kontrakt": "Kontrakt", "qayta_oqish": "Qayta o'qish", "turar_joy": "Turar joy"}
OBL_WORDS = {"qayta_oqish": ("qayta oqish", "qayta o qish", "qaytaoqish", "povtorn", "qayta topshir", "retake", "fan qarzi", "akademik qarz", "qayta uqish"),
             "turar_joy": ("turar joy", "turarjoy", "yotoqxona", "yotoq xona", "obshejit", "obshchezhit", "obshezhit", "ijara", "dorm", "yashash joy")}

SCHEMA = """
CREATE TABLE IF NOT EXISTS fin_payments(id INTEGER PRIMARY KEY, student_id INT, receipt_no TEXT, paid_on TEXT, amount INT, method TEXT,
  payer TEXT, note TEXT, status TEXT DEFAULT 'faol', seeded INT DEFAULT 0, storno_reason TEXT, storno_by TEXT, storno_at TEXT,
  created_by INT, created_by_name TEXT, created_at TEXT);
CREATE UNIQUE INDEX IF NOT EXISTS ux_fin_pay_receipt ON fin_payments(receipt_no) WHERE status='faol';
CREATE INDEX IF NOT EXISTS ix_fin_pay_day ON fin_payments(paid_on, method);
CREATE INDEX IF NOT EXISTS ix_fin_pay_st ON fin_payments(student_id);
CREATE TABLE IF NOT EXISTS fin_recon(day TEXT PRIMARY KEY, status TEXT, system_total INT, bank_total INT, diff INT, by_method TEXT, note TEXT,
  closed_by TEXT, closed_at TEXT, reopened_by TEXT, reopened_at TEXT, reopen_reason TEXT);
CREATE TABLE IF NOT EXISTS fin_budget_lines(id INTEGER PRIMARY KEY, year INT, category TEXT, plan INT, updated_by TEXT, updated_at TEXT,
  UNIQUE(year, category));
CREATE TABLE IF NOT EXISTS fin_expenses(id INTEGER PRIMARY KEY, year INT, category TEXT, spent_on TEXT, amount INT, payee TEXT, purpose TEXT,
  doc_no TEXT, status TEXT, reason_route TEXT, procurement_id INT, posted INT DEFAULT 0, created_by INT, created_by_name TEXT, created_at TEXT,
  decided_by TEXT, decided_at TEXT, decide_note TEXT);
CREATE INDEX IF NOT EXISTS ix_fin_exp ON fin_expenses(year, category, status);
CREATE TABLE IF NOT EXISTS fin_meta(k TEXT PRIMARY KEY, v TEXT);
CREATE TABLE IF NOT EXISTS fin_bank_lines(id INTEGER PRIMARY KEY, import_id TEXT, line_date TEXT, amount INT, payer TEXT, purpose TEXT, doc_no TEXT,
  hash TEXT UNIQUE, status TEXT, student_id INT, payment_id INT, match_kind TEXT, match_score INT, match_reasons TEXT, candidates TEXT,
  resolved_by TEXT, resolved_at TEXT, resolve_note TEXT, created_by INT, created_by_name TEXT, created_at TEXT);
CREATE INDEX IF NOT EXISTS ix_fin_bank_st ON fin_bank_lines(status, line_date);
"""

def _now() -> str: return clock.now().replace(microsecond=0).isoformat(timespec="seconds")
def _today() -> dt.date: return clock.today()
def _d(s) -> dt.date: return dt.date.fromisoformat(str(s)[:10])
def _short(n): return (n or "").split(":", 1)[-1].strip()

def init(con):
    global _con
    _con = _con or con
    con.executescript(SCHEMA)
    cols = {r[1] for r in con.execute("PRAGMA table_info(procurements)")}
    if cols and "fin_expense_id" not in cols:
        con.execute("ALTER TABLE procurements ADD COLUMN fin_expense_id INT")
    pc = {r[1] for r in con.execute("PRAGMA table_info(fin_payments)")}
    if "bank_line_id" not in pc: con.execute("ALTER TABLE fin_payments ADD COLUMN bank_line_id INT")
    if "kind" not in pc: con.execute("ALTER TABLE fin_payments ADD COLUMN kind TEXT DEFAULT 'kontrakt'")
    if "ref_id" not in pc: con.execute("ALTER TABLE fin_payments ADD COLUMN ref_id INT")
    con.commit()
    try:
        seed_demo(con)
    except Exception as e:      # demo ma'lumot tayyorlanmasa ham server ishlashi kerak
        import traceback; traceback.print_exc(); print("moliya.seed xatosi:", e)
    try:
        seed_bank_demo(con)
    except Exception as e:
        import traceback; traceback.print_exc(); print("moliya.seed_bank xatosi:", e)

def bind(con, ctx_fn):
    global _con, _ctx
    _con, _ctx = con, ctx_fn

# ---------------------------------------------------------------------------------------------
# Kim nimani qiladi
# ---------------------------------------------------------------------------------------------
def mode(c: Ctx) -> str | None:
    k = c.role.key
    if k in ENTER: return "enter"
    if k in APPROVE: return "approve"
    if k in AGG: return "agg"
    if k in STUDENT_READ and c.can(CONTRACTS): return "student"
    return None

def _audit(c, action, res=CONTRACTS, ok=True, detail=""):
    rbac.audit(_con, c, action, res, ok, detail)

def _need(c: Ctx, modes: set, action: str, res=CONTRACTS, detail="", msg=None):
    m = mode(c)
    if m not in modes:
        _audit(c, action, res, False, detail)
        raise AccessDenied(msg or f"⛔ '{c.role.title}' lavozimi uchun ruxsat yo'q ({action}).")
    return m

def C(request: Request) -> Ctx: return _ctx(request)

# ---------------------------------------------------------------------------------------------
# Demo ma'lumot (bir marta, sintetik): o'tgan kunlar to'lovlari (paid_amount ga allaqachon kirgan — «seeded»),
# solishtirilgan kunlar, yillik reja (budget jadvalidan), bir nechta xarajat (bittasi tasdiq kutmoqda).
# ---------------------------------------------------------------------------------------------
def _workdays_back(n, today):
    out, d = [], today
    while len(out) < n:
        if d.weekday() < 6: out.append(d)
        d -= dt.timedelta(days=1)
    return list(reversed(out))

def seed_demo(con):
    if con.execute("SELECT 1 FROM fin_meta WHERE k='seed'").fetchone(): return
    today = _today(); rnd = random.Random(2026)
    studs = db.rows(con, """SELECT id, paid_amount, full_name FROM students WHERE payment_type='kontrakt' AND status='faol' AND paid_amount>2000000
                            ORDER BY id""")
    bux = db.one(con, "SELECT id, full_name FROM users WHERE role='buxgalteriya' ORDER BY id LIMIT 1") or {"id": None, "full_name": "Buxgalteriya bo'limi"}
    days = _workdays_back(10, today)
    used = set(); n = 0
    for d in days:
        k = rnd.randint(12, 26) if d != today else rnd.randint(4, 8)
        for _ in range(k):
            if not studs: break
            s = studs[rnd.randrange(len(studs))]
            if s["id"] in used: continue
            used.add(s["id"])
            amt = min(s["paid_amount"], rnd.choice([1_500_000, 2_000_000, 2_500_000, 3_000_000, 4_250_000, 5_000_000, 6_500_000]))
            meth = rnd.choices(list(METHODS), [40, 20, 20, 8, 12])[0]
            n += 1
            rec = PREFIX[meth] + f"-{d.strftime('%y%m%d')}-{n:04d}"
            ts = dt.datetime.combine(d, dt.time(9 + rnd.randint(0, 8), rnd.randint(0, 59))).isoformat(timespec="seconds")
            con.execute("""INSERT INTO fin_payments(student_id,receipt_no,paid_on,amount,method,payer,note,status,seeded,created_by,created_by_name,created_at)
                           VALUES(?,?,?,?,?,?,?,?,1,?,?,?)""", (s["id"], rec, d.isoformat(), amt, meth, _short(s["full_name"]) if rnd.random() < .7 else "Ota-onasi",
                                                                 "", "faol", bux["id"], bux["full_name"], ts))
    # solishtirish: oxirgi 2 ish kunidan oldingilari yopilgan; bittasida kichik farq (bank komissiyasi) izoh bilan
    for i, d in enumerate(days[:-2]):
        bm = _day_methods(con, d.isoformat())
        sys_t = sum(x["system"] for x in bm.values())
        diff = -15_000 if i == 3 else 0
        bank = {k: v["system"] for k, v in bm.items()}
        if diff and "bank" in bank: bank["bank"] += diff
        else: diff = 0
        con.execute("""INSERT OR IGNORE INTO fin_recon(day,status,system_total,bank_total,diff,by_method,note,closed_by,closed_at)
                       VALUES(?,?,?,?,?,?,?,?,?)""", (d.isoformat(), "farq bilan yopildi" if diff else "yopildi", sys_t, sys_t + diff, diff, json.dumps(bank),
                                                      "Bank komissiyasi ushlab qolingan (ko'chirma №...)" if diff else "", bux["full_name"],
                                                      dt.datetime.combine(d, dt.time(18, 10)).isoformat(timespec="seconds")))
    # yillik reja: budget jadvalidagi oylik rejalar yig'indisi → 12 oyga
    for y, cat, s, m in con.execute("SELECT CAST(substr(month,1,4) AS INT), category, SUM(planned), COUNT(DISTINCT month) FROM budget GROUP BY 1,2").fetchall():
        con.execute("INSERT OR IGNORE INTO fin_budget_lines(year,category,plan,updated_by,updated_at) VALUES(?,?,?,?,?)",
                    (y, cat, int(round(s * 12 / max(m, 1), -6)), "Demo (budget jadvalidan)", _now()))
    con.commit()
    # xarajatlar: kichiklari darhol o'tkazilgan, kattasi tasdiq kutmoqda, bittasi rad etilgan
    y = today.year
    demo = [("Kommunal xizmatlar", 18_400_000, "«Toshkent shahar elektr tarmoqlari» AJ", "Oktyabr oyi elektr energiyasi", "HF-1184", "tasdiqlandi"),
            ("IT va uskunalar", 12_900_000, "«Sinov Texno» MChJ", "Kartrij va printer ehtiyot qismlari", "HF-1187", "tasdiqlandi"),
            ("Xo'jalik va ta'mir", 86_000_000, "«Qurilish Servis Demo» MChJ", "3-bino tomini qisman ta'mirlash", "SH-2026/57", "kutilmoqda"),
            ("Talabalar tadbirlari", 64_500_000, "«Event Demo» MChJ", "Talabalar kuni tadbiri (sahna, ovoz)", "SH-2026/61", "rad etildi")]
    for cat, amt, payee, purpose, doc, st in demo:
        cur = con.execute("""INSERT INTO fin_expenses(year,category,spent_on,amount,payee,purpose,doc_no,status,reason_route,created_by,created_by_name,created_at,
                             decided_by,decided_at,decide_note) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                          (y, cat, today.isoformat(), amt, payee, purpose, doc, "kutilmoqda", _route_reason(amt, False), bux["id"], bux["full_name"], _now(),
                           None, None, None))
        if st == "tasdiqlandi":
            _post(con, cur.lastrowid); con.execute("UPDATE fin_expenses SET status='tasdiqlandi', reason_route=NULL WHERE id=?", (cur.lastrowid,))
        elif st == "rad etildi":
            con.execute("UPDATE fin_expenses SET status='rad etildi', decided_by=?, decided_at=?, decide_note=? WHERE id=?",
                        ("Moliya-iqtisod ishlari bo'yicha prorektor", _now(), "Smeta qayta ko'rib chiqilsin — 3 ta tijorat taklifi ilova qilinmagan", cur.lastrowid))
    con.execute("INSERT INTO fin_meta(k,v) VALUES('seed',?)", (_now(),)); con.commit()

# ---------------------------------------------------------------------------------------------
# Yordamchilar
# ---------------------------------------------------------------------------------------------
def _norm_receipt(s: str) -> str: return re.sub(r"\s+", "", (s or "").upper())

def _day_methods(con, day: str) -> dict:
    out = {k: {"label": v, "system": 0, "n": 0} for k, v in METHODS.items()}
    for m, s, n in con.execute("SELECT method, SUM(amount), COUNT(*) FROM fin_payments WHERE status='faol' AND paid_on=? GROUP BY method", (day,)).fetchall():
        if m in out: out[m]["system"], out[m]["n"] = s or 0, n
    return out

def _closed(con, day: str) -> bool:
    r = db.one(con, "SELECT status FROM fin_recon WHERE day=?", (day,))
    return bool(r and r["status"] in ("yopildi", "farq bilan yopildi"))

def _contract(con, sid: int):
    return db.one(con, """SELECT s.id, s.full_name, s.hemis_id, s.status, s.payment_type, s.contract_amount, s.paid_amount, s.study_form, g.name grp
                          FROM students s LEFT JOIN groups_ g ON g.id=s.group_id WHERE s.id=?""", (sid,))

def _plan_status(con, s: dict) -> dict:
    """Shartnoma jadvali (contract_plan, kumulyativ %) bo'yicha joriy holat — registrar.py bilan bir xil hisob."""
    amt, paid = s["contract_amount"] or 0, s["paid_amount"] or 0
    today = _today().isoformat()
    plan = db.rows(con, "SELECT due, cum_pct, label FROM contract_plan ORDER BY due")
    need = 0; overdue = None; nxt = None
    for p in plan:
        req = amt * p["cum_pct"] // 100
        if p["due"] <= today:
            need = req
            if paid < req: overdue = {"label": p["label"], "due": p["due"], "short": req - paid}
        elif nxt is None and paid < req:
            nxt = {"label": p["label"], "due": p["due"], "need": req - paid}
    return {"amount": amt, "paid": paid, "debt": max(0, amt - paid), "pct": round(100 * paid / amt, 1) if amt else None,
            "required_now": need, "overdue": overdue, "next": nxt,
            "plan": [{"label": p["label"], "due": p["due"], "pct": p["cum_pct"], "sum": amt * p["cum_pct"] // 100, "met": paid >= amt * p["cum_pct"] // 100} for p in plan]}

def _line(con, year: int, cat: str) -> dict:
    l = db.one(con, "SELECT * FROM fin_budget_lines WHERE year=? AND category=?", (year, cat))
    fact = db.one(con, "SELECT COALESCE(SUM(actual),0) a FROM budget WHERE substr(month,1,4)=? AND category=?", (str(year), cat))["a"]
    pend = db.one(con, "SELECT COALESCE(SUM(amount),0) a FROM fin_expenses WHERE year=? AND category=? AND status='kutilmoqda'", (year, cat))["a"]
    plan = (l or {}).get("plan") or 0
    pct = round(100 * fact / plan, 1) if plan else None
    fpct = round(100 * (fact + pend) / plan, 1) if plan else None
    st = "oshib ketgan" if pct is not None and pct > 100 else "chegaraga yaqin" if pct is not None and pct >= WARN_PCT else \
         "tasdiqlansa oshadi" if fpct is not None and fpct > 100 else "me'yorda"
    return {"id": (l or {}).get("id"), "year": year, "category": cat, "plan": plan, "fact": fact, "pending": pend, "left": plan - fact,
            "pct": pct, "forecast_pct": fpct, "status": st}

def _route_reason(amount: int, over: bool) -> str | None:
    if amount >= LIMIT: return f"Summa {LIMIT:,} so'mdan katta — moliya prorektori tasdig'i".replace(",", " ")
    if over: return "Byudjet moddasidan oshadi — moliya prorektori tasdig'i"
    return None

def _post(con, eid: int):
    """Tasdiqlangan xarajat → budget(month, category).actual (panel va hisobotlar o'qiydigan yagona jadval)."""
    e = db.one(con, "SELECT * FROM fin_expenses WHERE id=?", (eid,))
    if not e or e["posted"]: return
    month = e["spent_on"][:7]
    if con.execute("SELECT 1 FROM budget WHERE month=? AND category=?", (month, e["category"])).fetchone():
        con.execute("UPDATE budget SET actual=COALESCE(actual,0)+? WHERE month=? AND category=?", (e["amount"], month, e["category"]))
    else:
        l = db.one(con, "SELECT plan FROM fin_budget_lines WHERE year=? AND category=?", (int(month[:4]), e["category"]))
        con.execute("INSERT INTO budget(month,category,planned,actual) VALUES(?,?,?,?)", (month, e["category"], ((l or {}).get("plan") or 0) // 12, e["amount"]))
    con.execute("UPDATE fin_expenses SET posted=1 WHERE id=?", (eid,))
    if e["procurement_id"]:
        con.execute("UPDATE procurements SET note=?, updated_at=? WHERE id=?", (f"Moliyalashtirildi: xarajat M-{eid:04d} (to'langan)", _now(), e["procurement_id"]))

def _categories(con):
    return [r[0] for r in con.execute("SELECT DISTINCT category FROM fin_budget_lines ORDER BY plan DESC").fetchall()] or \
           [r[0] for r in con.execute("SELECT DISTINCT category FROM budget").fetchall()]

# ---------------------------------------------------------------------------------------------
# Meta va umumiy ko'rinish
# ---------------------------------------------------------------------------------------------
@router.get(P + "/meta")
def meta(request: Request):
    c = C(request); m = mode(c)
    if not m:
        _audit(c, "moliya: bo'limni ochish", FINANCE, False); raise AccessDenied("⛔ Moliya bo'limi buxgalteriya va moliya prorektori uchun.")
    tabs = {"enter": ["overview", "bank", "payments", "recon", "budget", "expenses", "procurement", "reports"],
            "approve": ["overview", "bank", "payments", "recon", "budget", "expenses", "procurement", "reports"],
            "agg": ["overview", "budget"], "student": ["student"]}[m]
    return {"mode": m, "tabs": tabs, "methods": METHODS, "limit": LIMIT, "warn_pct": WARN_PCT, "today": _today().isoformat(),
            "year": _today().year, "categories": _categories(_con), "backdate_days": BACKDATE_DAYS,
            "can": {"enter": m == "enter", "approve": m == "approve"},
            "bank": bank_stats(_con) if m in ("enter", "approve") else None, "alert_days": UNMATCHED_ALERT_DAYS}

@router.get(P + "/overview")
def overview(request: Request):
    c = C(request); _need(c, {"enter", "approve", "agg"}, "moliya: umumiy ko'rinish", FINANCE)
    _audit(c, "moliya: umumiy ko'rinish", FINANCE)
    today = _today(); y = today.year
    ct = db.one(_con, """SELECT COUNT(*) n, SUM(contract_amount) total, SUM(paid_amount) paid, SUM(contract_amount>paid_amount) debtors
                         FROM students WHERE payment_type='kontrakt' AND status='faol' AND contract_amount>0""")
    td = db.one(_con, "SELECT COUNT(*) n, COALESCE(SUM(amount),0) s FROM fin_payments WHERE status='faol' AND paid_on=?", (today.isoformat(),))
    wk = db.one(_con, "SELECT COUNT(*) n, COALESCE(SUM(amount),0) s FROM fin_payments WHERE status='faol' AND paid_on>=?", ((today - dt.timedelta(days=6)).isoformat(),))
    days = db.rows(_con, """SELECT paid_on day, SUM(amount) s, COUNT(*) n FROM fin_payments WHERE status='faol' AND paid_on>=? GROUP BY paid_on ORDER BY paid_on""",
                   ((today - dt.timedelta(days=20)).isoformat(),))
    open_days = [d["day"] for d in days if d["day"] < today.isoformat() and not _closed(_con, d["day"])]
    lines = [_line(_con, y, cat) for cat in _categories(_con)]
    plan = sum(l["plan"] for l in lines); fact = sum(l["fact"] for l in lines)
    pend = db.one(_con, "SELECT COUNT(*) n, COALESCE(SUM(amount),0) s FROM fin_expenses WHERE status='kutilmoqda'")
    proc = db.one(_con, """SELECT COUNT(*) n, COALESCE(SUM(est_cost),0) s FROM procurements WHERE status IN ('buyurtma berildi','yetkazildi')
                           AND fin_expense_id IS NULL""")
    alerts = []
    for l in lines:
        if l["status"] == "oshib ketgan": alerts.append({"level": "bad", "text": f"«{l['category']}» moddasi {l['pct']}% — rejadan oshib ketgan"})
        elif l["status"] == "chegaraga yaqin": alerts.append({"level": "warn", "text": f"«{l['category']}» moddasi {l['pct']}% — chegaraga yaqin"})
        elif l["status"] == "tasdiqlansa oshadi": alerts.append({"level": "warn", "text": f"«{l['category']}»: tasdiq kutayotgan xarajatlar bilan {l['forecast_pct']}%"})
    if open_days: alerts.append({"level": "warn", "text": f"Solishtirilmagan kunlar: {len(open_days)} ta ({', '.join(_d(x).strftime('%d.%m') for x in open_days[:5])})"})
    if pend["n"]: alerts.append({"level": "info", "text": f"Moliya prorektori tasdig'ini kutayotgan xarajatlar: {pend['n']} ta"})
    bk = bank_stats(_con)
    if bk["stale"]: alerts.insert(0, {"level": "bad", "text": f"Aniqlanmagan to'lovlar {UNMATCHED_ALERT_DAYS} kundan ortiq turibdi: {bk['stale']} ta ({bk['stale_sum']:,} so'm)".replace(",", " ")})
    elif bk["n"]: alerts.insert(0, {"level": "warn", "text": f"Aniqlanmagan to'lovlar: {bk['n']} ta ({bk['sum']:,} so'm) — talabaga biriktiring".replace(",", " ")})
    if proc["n"]: alerts.append({"level": "info", "text": f"Moliyalashtirilmagan xarid so'rovlari: {proc['n']} ta"})
    total, paid = ct["total"] or 0, ct["paid"] or 0
    return {"contracts": {"n": ct["n"], "total": total, "paid": paid, "debt": total - paid, "debtors": ct["debtors"] or 0,
                          "pct": round(100 * paid / total, 1) if total else None},
            "today": {"n": td["n"], "sum": td["s"]}, "week": {"n": wk["n"], "sum": wk["s"]}, "days": days, "open_days": open_days,
            "budget": {"year": y, "plan": plan, "fact": fact, "pct": round(100 * fact / plan, 1) if plan else None, "lines": lines},
            "pending": pend, "procurement": proc, "alerts": alerts, "bank": bk}

# ---------------------------------------------------------------------------------------------
# To'lovlar
# ---------------------------------------------------------------------------------------------
@router.get(P + "/students")
def students(request: Request, q: str = ""):
    c = C(request); _need(c, {"enter", "approve", "student"}, "moliya: talaba qidirish")
    q = (q or "").strip()
    if len(q) < 2: return {"items": []}
    _audit(c, "moliya: talaba qidirish", CONTRACTS, True, q[:60])
    rows = db.rows(_con, """SELECT s.id, s.full_name, s.hemis_id, s.status, s.payment_type, s.contract_amount, s.paid_amount, g.name grp
                            FROM students s LEFT JOIN groups_ g ON g.id=s.group_id
                            WHERE (s.full_name LIKE ? COLLATE NOCASE OR s.hemis_id LIKE ?) ORDER BY s.payment_type='kontrakt' DESC, s.full_name LIMIT 15""",
                   (f"%{q}%", f"{q}%"))
    for r in rows: r["debt"] = max(0, (r["contract_amount"] or 0) - (r["paid_amount"] or 0))
    return {"items": rows}

@router.get(P + "/student/{sid}")
def student(sid: int, request: Request):
    c = C(request); _need(c, {"enter", "approve", "student"}, "moliya: talaba to'lov holati", detail=f"#{sid}")
    s = _contract(_con, sid)
    if not s: raise HTTPException(404, "Talaba topilmadi")
    _audit(c, "moliya: talaba to'lov holati", CONTRACTS, True, f"#{sid} {_short(s['full_name'])}")
    pays = db.rows(_con, """SELECT id, receipt_no, paid_on, amount, method, payer, status, storno_reason, storno_by, storno_at, created_by_name, created_at
                            FROM fin_payments WHERE student_id=? ORDER BY paid_on DESC, id DESC""", (sid,))
    for p in pays: p["method_label"] = METHODS.get(p["method"], p["method"]); p["created_by_name"] = _short(p["created_by_name"])
    return {"student": s, "contract_no": MM.contract_no(sid) if s["payment_type"] == "kontrakt" else None,
            "contract": _plan_status(_con, s) if s["payment_type"] == "kontrakt" else None, "payments": pays,
            "note": "Tizimdagi to'lovlar reyestri ISFT Core'da kiritilganlarni ko'rsatadi; oldingi to'lovlar «to'langan» summasiga kiritilgan."}

@router.get(P + "/payments")
def payments(request: Request, day: str = "", month: str = "", method: str = "", status: str = "", q: str = "", page: int = 1, kind: str = ""):
    c = C(request); _need(c, {"enter", "approve"}, "moliya: to'lovlar reyestri")
    _audit(c, "moliya: to'lovlar reyestri", CONTRACTS, True, day or month or "")
    w, a = ["1=1"], []
    if day: w.append("p.paid_on=?"); a.append(day[:10])
    elif month: w.append("substr(p.paid_on,1,7)=?"); a.append(month[:7])
    if method in METHODS: w.append("p.method=?"); a.append(method)
    if status in ("faol", "storno"): w.append("p.status=?"); a.append(status)
    if kind in PAY_KINDS: w.append("COALESCE(p.kind,'kontrakt')=?"); a.append(kind)
    if q.strip(): w.append("(s.full_name LIKE ? COLLATE NOCASE OR p.receipt_no LIKE ? OR s.hemis_id LIKE ?)"); a += [f"%{q.strip()}%"] * 2 + [f"{q.strip()}%"]
    where = " AND ".join(w); page = max(1, page)
    tot = db.one(_con, f"""SELECT COUNT(*) n, COALESCE(SUM(CASE WHEN p.status='faol' THEN p.amount END),0) s FROM fin_payments p
                           JOIN students s ON s.id=p.student_id WHERE {where}""", a)
    rows = db.rows(_con, f"""SELECT p.*, s.full_name, s.hemis_id, g.name grp FROM fin_payments p JOIN students s ON s.id=p.student_id
                             LEFT JOIN groups_ g ON g.id=s.group_id WHERE {where} ORDER BY p.paid_on DESC, p.id DESC LIMIT 50 OFFSET ?""", a + [(page - 1) * 50])
    for r in rows:
        r["method_label"] = METHODS.get(r["method"], r["method"]); r["created_by_name"] = _short(r["created_by_name"])
        r["kind"] = r.get("kind") or "kontrakt"; r["kind_label"] = PAY_KINDS.get(r["kind"], r["kind"])
        r["day_closed"] = _closed(_con, r["paid_on"])
    return {"items": rows, "total": tot["n"], "sum": tot["s"], "page": page, "pages": max(1, -(-tot["n"] // 50))}

class PayIn(BaseModel):
    student_id: int
    receipt_no: str = Field(..., min_length=3, max_length=40)
    paid_on: str
    amount: int
    method: str
    payer: str = Field("", max_length=120)
    note: str = Field("", max_length=300)
    kind: str = "kontrakt"
    ref_id: int | None = None

@router.post(P + "/payments")
def pay_create(body: PayIn, request: Request):
    c = C(request); _need(c, {"enter"}, "moliya: to'lov kiritish", detail=body.receipt_no, msg="⛔ To'lovni buxgalteriya kiritadi.")
    return _post_payment(c, body.student_id, body.receipt_no, body.paid_on, body.amount, body.method, body.payer, body.note,
                         kind=body.kind, ref_id=body.ref_id)

@router.get(P + "/obligations/{sid}")
def obligations(sid: int, request: Request):
    """Talabaning ochiq qayta o'qish va turar joy hisoblari — to'lov kiritish formasi uchun."""
    c = C(request); _need(c, {"enter", "approve"}, "moliya: talaba hisoblari", detail=f"#{sid}")
    return {"items": [o for o in _obligations(_con) if o["sid"] == sid], "kinds": PAY_KINDS}

def _obligation(con, kind: str, ref_id, student_id: int) -> dict:
    """Qayta o'qish yoki turar joy hisobi: {ref_id, sid, amount, paid, left, label}. Topilmasa — HTTPException."""
    if kind == "qayta_oqish":
        r = db.one(con, "SELECT id, student_id, subject, amount, COALESCE(paid,0) paid, decision FROM restudy WHERE id=?", (int(ref_id or 0),))
        if not r or r["decision"] != "qayta_oqish": raise HTTPException(404, "Qayta o'qish to'lov qatori topilmadi")
        o = {"ref_id": r["id"], "sid": r["student_id"], "amount": r["amount"] or 0, "paid": r["paid"], "label": f"Qayta o'qish: {r['subject']}"}
    elif kind == "turar_joy":
        r = db.one(con, """SELECT ch.id, rs.student_id, ch.period, ch.amount, ch.paid FROM yj_charges ch JOIN yj_residents rs ON rs.id=ch.resident_id
                           WHERE ch.id=?""", (int(ref_id or 0),))
        if not r: raise HTTPException(404, "Turar joy hisobi topilmadi")
        o = {"ref_id": r["id"], "sid": r["student_id"], "amount": r["amount"] or 0, "paid": r["paid"] or 0, "label": f"Turar joy: {r['period']}"}
    else:
        raise HTTPException(400, "To'lov turi noto'g'ri")
    if o["sid"] != student_id: raise HTTPException(409, "Hisob boshqa talabaga tegishli")
    o["left"] = max(0, o["amount"] - o["paid"])
    return o

def _oldest_obligation(con, kind: str, student_id: int, amount: int):
    """Talabaning shu turdagi eng eski ochiq hisobi (summa sig'adigani afzal)."""
    if kind == "qayta_oqish":
        rs = db.rows(con, """SELECT id FROM restudy WHERE student_id=? AND decision='qayta_oqish' AND COALESCE(paid,0)<COALESCE(amount,0)
                             ORDER BY (COALESCE(amount,0)-COALESCE(paid,0) < ?), pay_due, id""", (student_id, amount))
    else:
        rs = db.rows(con, """SELECT ch.id FROM yj_charges ch JOIN yj_residents rs ON rs.id=ch.resident_id WHERE rs.student_id=? AND ch.paid<ch.amount
                             ORDER BY (ch.amount-ch.paid < ?), ch.period, ch.id""", (student_id, amount))
    return rs[0]["id"] if rs else None

def _post_payment(c: Ctx, student_id: int, receipt_no: str, paid_on: str, amount: int, method: str, payer: str = "", note: str = "",
                  bank_line_id: int | None = None, commit: bool = True, kind: str = "kontrakt", ref_id: int | None = None) -> dict:
    """Yagona to'lov o'tkazish (barcha turlar): tekshiruvlar → fin_payments + tegishli hisob (kontrakt: students.paid_amount;
    qayta o'qish: restudy.paid; turar joy: yj_charges.paid). Qo'lda kiritish, bank qatori, Talaba harakati va Yoshlar shu yerdan o'tadi."""
    if kind not in PAY_KINDS: raise HTTPException(400, "To'lov turi noto'g'ri")
    rec = _norm_receipt(receipt_no)
    if len(rec) < 3: raise HTTPException(400, "Kvitansiya / to'lov hujjati raqamini kiriting")
    try: d = _d(paid_on)
    except Exception: raise HTTPException(400, "Sana noto'g'ri")
    today = _today()
    if d > today: raise HTTPException(400, "To'lov sanasi kelajakda bo'lishi mumkin emas")
    if (today - d).days > BACKDATE_DAYS: raise HTTPException(400, f"{BACKDATE_DAYS} kundan eski to'lov — moliya prorektori bilan kelishilib, alohida kiritiladi")
    if method not in METHODS: raise HTTPException(400, "To'lov usuli noto'g'ri")
    if amount <= 0 or amount > 200_000_000: raise HTTPException(400, "Summa noto'g'ri")
    if _closed(_con, d.isoformat()): raise HTTPException(409, f"{d.strftime('%d.%m.%Y')} kuni solishtirilib yopilgan — avval moliya prorektori qayta ochishi kerak")
    s = _contract(_con, student_id)
    if not s: raise HTTPException(404, "Talaba topilmadi")
    dup = db.one(_con, """SELECT p.id, p.paid_on, p.amount, p.kind, s.full_name FROM fin_payments p JOIN students s ON s.id=p.student_id
                          WHERE p.receipt_no=? AND p.status='faol'""", (rec,))
    if dup:
        _audit(c, "moliya: takroriy kvitansiya rad etildi", CONTRACTS, False, rec)
        raise HTTPException(409, f"Kvitansiya {rec} allaqachon kiritilgan: {_d(dup['paid_on']).strftime('%d.%m.%Y')}, "
                                 f"{dup['amount']:,} so'm — {_short(dup['full_name'])} ({PAY_KINDS.get(dup['kind'] or 'kontrakt', '')})".replace(",", " "))
    ob = None
    if kind == "kontrakt":
        if s["payment_type"] != "kontrakt" or not s["contract_amount"]: raise HTTPException(409, "Talaba kontrakt asosida o'qimaydi")
        debt = (s["contract_amount"] or 0) - (s["paid_amount"] or 0)
        if amount > debt:
            raise HTTPException(409, f"Summa qarzdan oshadi: qolgan qarz {max(debt, 0):,} so'm. Ortiqcha to'lov qaytariladi yoki keyingi o'quv yiliga alohida hisoblanadi".replace(",", " "))
    else:
        if ref_id is None: ref_id = _oldest_obligation(_con, kind, s["id"], amount)
        if ref_id is None: raise HTTPException(404, f"Talabada ochiq «{PAY_KINDS[kind]}» hisobi yo'q")
        ob = _obligation(_con, kind, ref_id, s["id"])
        if ob["left"] <= 0: raise HTTPException(409, f"{ob['label']} — to'lov allaqachon to'liq")
        if amount > ob["left"]: raise HTTPException(409, f"Summa qoldiqdan oshadi: {ob['label']} bo'yicha qolgan {ob['left']:,} so'm".replace(",", " "))
    cur = _con.execute("""INSERT INTO fin_payments(student_id,receipt_no,paid_on,amount,method,payer,note,status,created_by,created_by_name,created_at,bank_line_id,kind,ref_id)
                          VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", (s["id"], rec, d.isoformat(), amount, method, (payer or "").strip(), (note or "").strip(),
                                                                   "faol", c.user["id"], c.user["full_name"], _now(), bank_line_id, kind, ob["ref_id"] if ob else None))
    if kind == "kontrakt":
        _con.execute("UPDATE students SET paid_amount=COALESCE(paid_amount,0)+? WHERE id=?", (amount, s["id"]))
    elif kind == "qayta_oqish":
        _con.execute("UPDATE restudy SET paid=COALESCE(paid,0)+?, paid_at=? WHERE id=?", (amount, _now(), ob["ref_id"]))
    else:
        _con.execute("UPDATE yj_charges SET paid=paid+?, paid_at=?, receipt=?, by_user=? WHERE id=?", (amount, _now(), rec, c.user["id"], ob["ref_id"]))
    if commit: _con.commit()
    _audit(c, "moliya: to'lov kiritildi", CONTRACTS, True, f"{rec} · {PAY_KINDS[kind]} · {amount} so'm · #{s['id']} {_short(s['full_name'])}"
           + (f" · {ob['label']}" if ob else "") + (f" · bank qatori #{bank_line_id}" if bank_line_id else ""))
    if kind == "kontrakt":
        st = _plan_status(_con, _contract(_con, s["id"]))
        return {"ok": True, "id": cur.lastrowid, "receipt_no": rec, "kind": kind, "contract": st, "left": st["debt"]}
    return {"ok": True, "id": cur.lastrowid, "receipt_no": rec, "kind": kind, "ref_id": ob["ref_id"], "label": ob["label"], "contract": None,
            "paid": ob["paid"] + amount, "amount": ob["amount"], "left": ob["left"] - amount}

class StornoIn(BaseModel):
    reason: str = Field(..., min_length=5, max_length=300)

@router.post(P + "/payments/{pid}/storno")
def pay_storno(pid: int, body: StornoIn, request: Request):
    c = C(request); m = _need(c, {"enter", "approve"}, "moliya: storno", detail=f"#{pid}")
    p = db.one(_con, "SELECT * FROM fin_payments WHERE id=?", (pid,))
    if not p: raise HTTPException(404)
    if p["status"] != "faol": raise HTTPException(409, "To'lov allaqachon storno qilingan")
    if _closed(_con, p["paid_on"]) and m != "approve":
        _audit(c, "moliya: storno (yopilgan kun)", CONTRACTS, False, p["receipt_no"])
        raise AccessDenied("⛔ Kun solishtirilib yopilgan — stornoni moliya prorektori qiladi.")
    _con.execute("UPDATE fin_payments SET status='storno', storno_reason=?, storno_by=?, storno_at=? WHERE id=?",
                 (body.reason.strip(), c.user["full_name"], _now(), pid))
    k = p.get("kind") or "kontrakt"
    if k == "qayta_oqish" and p.get("ref_id"):
        _con.execute("UPDATE restudy SET paid=MAX(0, COALESCE(paid,0)-?) WHERE id=?", (p["amount"], p["ref_id"]))
    elif k == "turar_joy" and p.get("ref_id"):
        _con.execute("UPDATE yj_charges SET paid=MAX(0, paid-?) WHERE id=?", (p["amount"], p["ref_id"]))
    else:
        _con.execute("UPDATE students SET paid_amount=MAX(0, COALESCE(paid_amount,0)-?) WHERE id=?", (p["amount"], p["student_id"]))
    if p.get("bank_line_id"):   # bank qatoridan o'tgan to'lov storno → qator yana «aniqlanmagan» navbatiga qaytadi
        _con.execute("""UPDATE fin_bank_lines SET status='aniqlanmagan', student_id=NULL, payment_id=NULL, match_kind=NULL,
                        resolve_note=? WHERE id=?""", (f"To'lov storno qilindi: {body.reason.strip()[:200]}", p["bank_line_id"]))
    if _closed(_con, p["paid_on"]):   # yopilgan kun summasi qayta hisoblanadi, farq ko'rinadi
        r = db.one(_con, "SELECT bank_total FROM fin_recon WHERE day=?", (p["paid_on"],))
        st = sum(x["system"] for x in _day_methods(_con, p["paid_on"]).values())
        _con.execute("UPDATE fin_recon SET system_total=?, diff=?, status=CASE WHEN ?=0 THEN 'yopildi' ELSE 'farq bilan yopildi' END WHERE day=?",
                     (st, (r["bank_total"] or 0) - st, (r["bank_total"] or 0) - st, p["paid_on"]))
    _con.commit()
    _audit(c, "moliya: to'lov storno qilindi", CONTRACTS, True, f"{p['receipt_no']} · {p['amount']} so'm · {body.reason[:120]}")
    return {"ok": True}

# ---------------------------------------------------------------------------------------------
# Kunlik solishtirish
# ---------------------------------------------------------------------------------------------
@router.get(P + "/recon")
def recon(request: Request, month: str = ""):
    c = C(request); _need(c, {"enter", "approve"}, "moliya: solishtirish", FINANCE)
    month = (month or _today().isoformat())[:7]
    _audit(c, "moliya: solishtirish", FINANCE, True, month)
    days = {r["day"]: {"day": r["day"], "system": r["s"], "n": r["n"]} for r in db.rows(_con,
            "SELECT paid_on day, SUM(amount) s, COUNT(*) n FROM fin_payments WHERE status='faol' AND substr(paid_on,1,7)=? GROUP BY paid_on", (month,))}
    for r in db.rows(_con, "SELECT * FROM fin_recon WHERE substr(day,1,7)=?", (month,)):
        x = days.setdefault(r["day"], {"day": r["day"], "system": 0, "n": 0})
        x.update({"status": r["status"], "bank": r["bank_total"], "diff": r["diff"], "note": r["note"], "closed_by": _short(r["closed_by"]),
                  "closed_at": r["closed_at"], "reopen_reason": r["reopen_reason"], "bank_by_method": json.loads(r["by_method"] or "{}")})
    out = sorted(days.values(), key=lambda x: x["day"], reverse=True)
    for x in out:
        x.setdefault("status", "ochiq"); x["methods"] = _day_methods(_con, x["day"])
        x["stale"] = x["status"] in ("ochiq", "qayta ochildi") and x["day"] < _today().isoformat()
    return {"month": month, "days": out}

class ReconIn(BaseModel):
    bank: dict[str, int]
    note: str = Field("", max_length=400)

@router.post(P + "/recon/{day}/close")
def recon_close(day: str, body: ReconIn, request: Request):
    c = C(request); _need(c, {"enter"}, "moliya: kunni yopish", FINANCE, day, msg="⛔ Kunni buxgalteriya solishtiradi va yopadi.")
    try: d = _d(day)
    except Exception: raise HTTPException(400)
    if d > _today(): raise HTTPException(400, "Kelajakdagi kunni yopib bo'lmaydi")
    if _closed(_con, d.isoformat()): raise HTTPException(409, "Kun allaqachon yopilgan")
    meth = _day_methods(_con, d.isoformat())
    bank = {k: int(body.bank.get(k) or 0) for k in METHODS}
    if any(v < 0 for v in bank.values()): raise HTTPException(400)
    sys_t = sum(v["system"] for v in meth.values()); bank_t = sum(bank.values()); diff = bank_t - sys_t
    if diff and len(body.note.strip()) < 5: raise HTTPException(400, f"Farq {diff:,} so'm — izoh majburiy (sababi)".replace(",", " "))
    st = "farq bilan yopildi" if diff else "yopildi"
    _con.execute("""INSERT INTO fin_recon(day,status,system_total,bank_total,diff,by_method,note,closed_by,closed_at) VALUES(?,?,?,?,?,?,?,?,?)
                    ON CONFLICT(day) DO UPDATE SET status=excluded.status, system_total=excluded.system_total, bank_total=excluded.bank_total,
                    diff=excluded.diff, by_method=excluded.by_method, note=excluded.note, closed_by=excluded.closed_by, closed_at=excluded.closed_at""",
                 (d.isoformat(), st, sys_t, bank_t, diff, json.dumps(bank), body.note.strip(), c.user["full_name"], _now()))
    _con.commit()
    _audit(c, "moliya: kun yopildi", FINANCE, True, f"{d.isoformat()} · tizim {sys_t} · ko'chirma {bank_t} · farq {diff}")
    return {"ok": True, "status": st, "diff": diff, "system": sys_t, "bank": bank_t}

@router.post(P + "/recon/{day}/reopen")
def recon_reopen(day: str, body: StornoIn, request: Request):
    c = C(request); _need(c, {"approve"}, "moliya: kunni qayta ochish", FINANCE, day, msg="⛔ Yopilgan kunni moliya prorektori qayta ochadi.")
    if not _closed(_con, day[:10]): raise HTTPException(409, "Kun yopilmagan")
    _con.execute("UPDATE fin_recon SET status='qayta ochildi', reopened_by=?, reopened_at=?, reopen_reason=? WHERE day=?",
                 (c.user["full_name"], _now(), body.reason.strip(), day[:10]))
    _con.commit(); _audit(c, "moliya: kun qayta ochildi", FINANCE, True, f"{day[:10]} · {body.reason[:120]}")
    return {"ok": True}

# ---------------------------------------------------------------------------------------------
# Byudjet ijrosi va xarajatlar
# ---------------------------------------------------------------------------------------------
@router.get(P + "/budget")
def budget(request: Request, year: int = 0):
    c = C(request); _need(c, {"enter", "approve", "agg"}, "moliya: byudjet ijrosi", FINANCE)
    y = year or _today().year
    _audit(c, "moliya: byudjet ijrosi", FINANCE, True, str(y))
    lines = [_line(_con, y, cat) for cat in _categories(_con)]
    months = db.rows(_con, "SELECT month, category, planned, actual FROM budget WHERE substr(month,1,4)=? ORDER BY month", (str(y),))
    mm = sorted({m["month"] for m in months})
    over = [m for m in months if m["planned"] and m["actual"] > m["planned"]]
    return {"year": y, "lines": lines, "months": mm, "cells": months, "monthly_over": over,
            "total": {"plan": sum(l["plan"] for l in lines), "fact": sum(l["fact"] for l in lines), "pending": sum(l["pending"] for l in lines)},
            "years": [r[0] for r in _con.execute("SELECT DISTINCT year FROM fin_budget_lines ORDER BY year").fetchall()]}

class PlanIn(BaseModel):
    year: int
    category: str = Field(..., min_length=2, max_length=80)
    plan: int

@router.post(P + "/budget/plan")
def budget_plan(body: PlanIn, request: Request):
    c = C(request); _need(c, {"approve"}, "moliya: yillik reja", FINANCE, body.category, msg="⛔ Yillik rejani moliya prorektori o'zgartiradi.")
    if body.plan < 0 or body.plan > 10**13: raise HTTPException(400)
    old = db.one(_con, "SELECT plan FROM fin_budget_lines WHERE year=? AND category=?", (body.year, body.category.strip()))
    _con.execute("""INSERT INTO fin_budget_lines(year,category,plan,updated_by,updated_at) VALUES(?,?,?,?,?)
                    ON CONFLICT(year,category) DO UPDATE SET plan=excluded.plan, updated_by=excluded.updated_by, updated_at=excluded.updated_at""",
                 (body.year, body.category.strip(), body.plan, c.user["full_name"], _now()))
    _con.commit()
    _audit(c, "moliya: yillik reja o'zgartirildi", FINANCE, True, f"{body.year} · {body.category} · {(old or {}).get('plan')} → {body.plan}")
    return {"ok": True, "line": _line(_con, body.year, body.category.strip())}

def _exp_rows(where="1=1", args=()):
    rows = db.rows(_con, f"""SELECT e.*, p.item proc_item, p.room proc_room FROM fin_expenses e LEFT JOIN procurements p ON p.id=e.procurement_id
                             WHERE {where} ORDER BY CASE e.status WHEN 'kutilmoqda' THEN 0 ELSE 1 END, e.created_at DESC, e.id DESC LIMIT 300""", args)
    for r in rows: r["number"] = f"M-{r['id']:04d}"; r["created_by_name"] = _short(r["created_by_name"]); r["decided_by"] = _short(r["decided_by"])
    return rows

@router.get(P + "/expenses")
def expenses(request: Request, status: str = "", year: int = 0):
    c = C(request); _need(c, {"enter", "approve"}, "moliya: xarajatlar", FINANCE)
    _audit(c, "moliya: xarajatlar", FINANCE, True, status)
    w, a = ["e.year=?"], [year or _today().year]
    if status in EXP_ST: w.append("e.status=?"); a.append(status)
    rows = _exp_rows(" AND ".join(w), a)
    return {"items": rows, "limit": LIMIT, "statuses": EXP_ST, "pending": sum(1 for r in rows if r["status"] == "kutilmoqda")}

class ExpIn(BaseModel):
    category: str
    amount: int
    payee: str = Field(..., min_length=2, max_length=160)
    purpose: str = Field(..., min_length=3, max_length=400)
    doc_no: str = Field("", max_length=60)
    spent_on: str = ""
    procurement_id: int | None = None

def _create_expense(c: Ctx, body: ExpIn) -> dict:
    cats = _categories(_con)
    if body.category not in cats: raise HTTPException(400, "Byudjet moddasi noto'g'ri")
    if body.amount <= 0 or body.amount > 10**12: raise HTTPException(400, "Summa noto'g'ri")
    try: d = _d(body.spent_on) if body.spent_on else _today()
    except Exception: raise HTTPException(400, "Sana noto'g'ri")
    if d > _today(): raise HTTPException(400, "Sana kelajakda bo'lishi mumkin emas")
    l = _line(_con, d.year, body.category)
    over = bool(l["plan"]) and l["fact"] + l["pending"] + body.amount > l["plan"]
    why = _route_reason(body.amount, over)
    cur = _con.execute("""INSERT INTO fin_expenses(year,category,spent_on,amount,payee,purpose,doc_no,status,reason_route,procurement_id,created_by,created_by_name,created_at)
                          VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""", (d.year, body.category, d.isoformat(), body.amount, body.payee.strip(), body.purpose.strip(),
                                                                 body.doc_no.strip(), "kutilmoqda" if why else "tasdiqlandi", why, body.procurement_id,
                                                                 c.user["id"], c.user["full_name"], _now()))
    eid = cur.lastrowid
    if not why: _post(_con, eid)
    _con.commit()
    route_txt = "tasdiqqa yuborildi" if why else "o'tkazildi"
    _audit(c, "moliya: xarajat kiritildi", FINANCE, True, f"M-{eid:04d} · {body.category} · {body.amount} so'm · {route_txt}")
    return {"ok": True, "id": eid, "number": f"M-{eid:04d}", "status": "kutilmoqda" if why else "tasdiqlandi", "route": why,
            "line": _line(_con, d.year, body.category)}

@router.post(P + "/expenses")
def expense_create(body: ExpIn, request: Request):
    c = C(request); _need(c, {"enter"}, "moliya: xarajat kiritish", FINANCE, msg="⛔ Xarajatni buxgalteriya kiritadi.")
    if body.procurement_id: raise HTTPException(400, "Xarid so'rovini «Xaridlar» bo'limidan moliyalashtiring")
    return _create_expense(c, body)

class DecideIn(BaseModel):
    decision: str
    note: str = Field("", max_length=300)

@router.post(P + "/expenses/{eid}/decide")
def expense_decide(eid: int, body: DecideIn, request: Request):
    c = C(request); _need(c, {"approve"}, "moliya: xarajatni tasdiqlash", FINANCE, f"M-{eid:04d}", msg="⛔ Xarajatni moliya prorektori tasdiqlaydi.")
    if body.decision not in ("tasdiqlandi", "rad etildi"): raise HTTPException(400)
    e = db.one(_con, "SELECT * FROM fin_expenses WHERE id=?", (eid,))
    if not e: raise HTTPException(404)
    if e["status"] != "kutilmoqda": raise HTTPException(409, "Xarajat allaqachon ko'rib chiqilgan")
    if body.decision == "rad etildi" and len(body.note.strip()) < 5: raise HTTPException(400, "Rad etish sababi majburiy")
    _con.execute("UPDATE fin_expenses SET status=?, decided_by=?, decided_at=?, decide_note=? WHERE id=?",
                 (body.decision, c.user["full_name"], _now(), body.note.strip(), eid))
    if body.decision == "tasdiqlandi": _post(_con, eid)
    elif e["procurement_id"]:
        _con.execute("UPDATE procurements SET fin_expense_id=NULL, note=?, updated_at=? WHERE id=?",
                     (f"Moliyalashtirish rad etildi: {body.note.strip()[:200]}", _now(), e["procurement_id"]))
    _con.commit()
    _audit(c, f"moliya: xarajat {body.decision}", FINANCE, True, f"M-{eid:04d} · {e['amount']} so'm · {body.note[:100]}")
    return {"ok": True, "line": _line(_con, e["year"], e["category"])}

@router.post(P + "/expenses/{eid}/cancel")
def expense_cancel(eid: int, request: Request):
    c = C(request); _need(c, {"enter"}, "moliya: xarajatni bekor qilish", FINANCE, f"M-{eid:04d}")
    e = db.one(_con, "SELECT * FROM fin_expenses WHERE id=?", (eid,))
    if not e: raise HTTPException(404)
    if e["status"] != "kutilmoqda": raise HTTPException(409, "Faqat tasdiq kutayotgan xarajat bekor qilinadi")
    _con.execute("UPDATE fin_expenses SET status='bekor qilindi', decided_by=?, decided_at=? WHERE id=?", (c.user["full_name"], _now(), eid))
    if e["procurement_id"]: _con.execute("UPDATE procurements SET fin_expense_id=NULL WHERE id=?", (e["procurement_id"],))
    _con.commit(); _audit(c, "moliya: xarajat bekor qilindi", FINANCE, True, f"M-{eid:04d}")
    return {"ok": True}

# ---------------------------------------------------------------------------------------------
# Xarid so'rovlarini moliyalashtirish (app/service.py procurements)
# ---------------------------------------------------------------------------------------------
FUNDABLE = ("buyurtma berildi", "yetkazildi")

@router.get(P + "/procurements")
def procurements(request: Request):
    c = C(request); _need(c, {"enter", "approve"}, "moliya: xarid so'rovlari", FINANCE)
    _audit(c, "moliya: xarid so'rovlari", FINANCE)
    rows = db.rows(_con, """SELECT p.id, p.room, p.item, p.text, p.qty, p.est_cost, p.status, p.note, p.created_at, p.fin_expense_id,
                            e.status fin_status, e.amount fin_amount, e.category fin_category FROM procurements p
                            LEFT JOIN fin_expenses e ON e.id=p.fin_expense_id ORDER BY p.created_at DESC LIMIT 200""")
    for r in rows:
        r["number"] = f"X-{r['id']:04d}"
        r["fin"] = ("to'langan" if r["fin_status"] == "tasdiqlandi" else "tasdiq kutmoqda" if r["fin_status"] == "kutilmoqda"
                    else "moliyalashtirilmagan" if r["status"] in FUNDABLE else "xarid bo'limida")
        r["fundable"] = r["status"] in FUNDABLE and not r["fin_expense_id"]
    return {"items": rows, "fundable_statuses": list(FUNDABLE)}

class FundIn(BaseModel):
    category: str
    amount: int | None = None
    payee: str = Field(..., min_length=2, max_length=160)
    doc_no: str = Field("", max_length=60)

@router.post(P + "/procurements/{pid}/fund")
def procurement_fund(pid: int, body: FundIn, request: Request):
    c = C(request); _need(c, {"enter"}, "moliya: xaridni moliyalashtirish", FINANCE, f"X-{pid:04d}", msg="⛔ Xaridni buxgalteriya moliyalashtiradi.")
    p = db.one(_con, "SELECT * FROM procurements WHERE id=?", (pid,))
    if not p: raise HTTPException(404)
    if p["fin_expense_id"]: raise HTTPException(409, "Bu xarid allaqachon moliyalashtirilgan")
    if p["status"] not in FUNDABLE: raise HTTPException(409, "Xarid bo'limi buyurtma bermagan — hali moliyalashtirilmaydi")
    amt = body.amount or p["est_cost"] or 0
    if amt <= 0: raise HTTPException(400, "Summa ko'rsatilmagan")
    r = _create_expense(c, ExpIn(category=body.category, amount=amt, payee=body.payee, doc_no=body.doc_no,
                                 purpose=f"Xarid X-{pid:04d}: {p['item']} ({p['room']}) × {p['qty']}"[:400], procurement_id=pid))
    _con.execute("UPDATE procurements SET fin_expense_id=?, updated_at=? WHERE id=?", (r["id"], _now(), pid))
    if r["status"] == "tasdiqlandi":
        _con.execute("UPDATE procurements SET note=? WHERE id=?", (f"Moliyalashtirildi: xarajat {r['number']} (to'langan)", pid))
    _con.commit()
    return r

# ---------------------------------------------------------------------------------------------
# Oylik hisobotlar (.xlsx / .csv)
# ---------------------------------------------------------------------------------------------
def _report(kind: str, month: str):
    if kind == "payments":
        head = ["Sana", "Kvitansiya", "Talaba", "HEMIS ID", "Guruh", "Usul", "Summa (so'm)", "Holat", "Kiritgan", "Turi"]
        rows = [(r["paid_on"], r["receipt_no"], r["full_name"], r["hemis_id"], r["grp"], METHODS.get(r["method"], r["method"]), r["amount"],
                 r["status"] + (f" ({r['storno_reason']})" if r["storno_reason"] else ""), _short(r["created_by_name"]), PAY_KINDS.get(r.get("kind") or "kontrakt", ""))
                for r in db.rows(_con, """SELECT p.*, s.full_name, s.hemis_id, g.name grp FROM fin_payments p JOIN students s ON s.id=p.student_id
                                          LEFT JOIN groups_ g ON g.id=s.group_id WHERE substr(p.paid_on,1,7)=? ORDER BY p.paid_on, p.id""", (month,))]
        tot = sum(r[6] for r in rows if r[7] == "faol")
        return "To'lovlar reyestri", head, rows, ["", "", "Jami (faol)", "", "", "", tot, "", "", ""]
    if kind == "recon":
        head = ["Kun", "To'lovlar soni", "Tizim (so'm)", "Ko'chirma (so'm)", "Farq (so'm)", "Holat", "Izoh", "Yopgan"]
        R = recon_rows(month)
        rows = [(x["day"], x["n"], x["system"], x.get("bank"), x.get("diff"), x.get("status", "ochiq"), x.get("note") or "", _short(x.get("closed_by"))) for x in R]
        return "Kunlik solishtirish", head, rows, ["Jami", sum(r[1] for r in rows), sum(r[2] or 0 for r in rows), sum(r[3] or 0 for r in rows),
                                                   sum(r[4] or 0 for r in rows), "", "", ""]
    if kind == "budget":
        y = int(month[:4])
        head = ["Byudjet moddasi", "Yillik reja (so'm)", "Fakt (so'm)", f"{month} fakt (so'm)", "Tasdiq kutmoqda (so'm)", "Qoldiq (so'm)", "Ijro %", "Holat"]
        rows = []
        for cat in _categories(_con):
            l = _line(_con, y, cat)
            mf = db.one(_con, "SELECT COALESCE(SUM(actual),0) a FROM budget WHERE month=? AND category=?", (month, cat))["a"]
            rows.append((cat, l["plan"], l["fact"], mf, l["pending"], l["left"], l["pct"], l["status"]))
        return f"Byudjet ijrosi — {y}", head, rows, ["Jami", sum(r[1] for r in rows), sum(r[2] for r in rows), sum(r[3] for r in rows),
                                                     sum(r[4] for r in rows), sum(r[5] for r in rows), "", ""]
    raise HTTPException(400, "Hisobot turi noto'g'ri")

def recon_rows(month):
    days = {r["day"]: {"day": r["day"], "system": r["s"], "n": r["n"]} for r in db.rows(_con,
            "SELECT paid_on day, SUM(amount) s, COUNT(*) n FROM fin_payments WHERE status='faol' AND substr(paid_on,1,7)=? GROUP BY paid_on", (month,))}
    for r in db.rows(_con, "SELECT * FROM fin_recon WHERE substr(day,1,7)=?", (month,)):
        days.setdefault(r["day"], {"day": r["day"], "system": 0, "n": 0}).update(
            {"status": r["status"], "bank": r["bank_total"], "diff": r["diff"], "note": r["note"], "closed_by": r["closed_by"]})
    return sorted(days.values(), key=lambda x: x["day"])

@router.get(P + "/export")
def export(request: Request, kind: str = "payments", month: str = "", fmt: str = "xlsx"):
    c = C(request); _need(c, {"enter", "approve"}, "moliya: hisobot eksporti", FINANCE, kind)
    month = (month or _today().isoformat())[:7]
    if not re.fullmatch(r"\d{4}-\d{2}", month): raise HTTPException(400, "Oy noto'g'ri")
    title, head, rows, total = _report(kind, month)
    _audit(c, "moliya: hisobot eksporti", FINANCE, True, f"{kind} · {month} · {fmt} · {len(rows)} qator")
    fn = f"moliya_{kind}_{month}"
    if fmt == "csv":
        buf = io.StringIO(); w = csv.writer(buf, delimiter=";"); w.writerow(head); w.writerows(rows); w.writerow(total)
        return Response(("﻿" + buf.getvalue()).encode("utf-8"), media_type="text/csv; charset=utf-8",
                        headers={"Content-Disposition": f'attachment; filename="{fn}.csv"'})
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.utils import get_column_letter
    thin = Side(style="thin", color="C9CED6"); border = Border(left=thin, right=thin, top=thin, bottom=thin)
    wb = Workbook(); ws = wb.active; ws.title = title[:30]
    end = get_column_letter(len(head))
    ws.append(["ISFT INSTITUTI — International School of Finance and Technology"]); ws.merge_cells(f"A1:{end}1")
    ws["A1"].font = Font(bold=True, size=14, color="7A0E14")
    ws.append([f"{title} · {month}"]); ws.merge_cells(f"A2:{end}2"); ws["A2"].font = Font(bold=True, size=12)
    ws.append([f"Tuzildi: ISFT Core, {clock.now().strftime('%d.%m.%Y %H:%M')} · {_short(c.user['full_name']) or c.role.title}"])
    ws.merge_cells(f"A3:{end}3"); ws["A3"].font = Font(size=9, color="555B63"); ws.append([])
    ws.append(head)
    for cell in ws[ws.max_row]:
        cell.font = Font(bold=True, color="FFFFFF"); cell.fill = PatternFill("solid", fgColor="7A0E14"); cell.border = border
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    for r in rows:
        ws.append(list(r))
        for cell in ws[ws.max_row]:
            cell.border = border
            if isinstance(cell.value, int) and abs(cell.value) >= 1000: cell.number_format = "#,##0"
    ws.append(total)
    for cell in ws[ws.max_row]:
        cell.font = Font(bold=True); cell.border = border
        if isinstance(cell.value, int): cell.number_format = "#,##0"
    for i in range(1, len(head) + 1): ws.column_dimensions[get_column_letter(i)].width = 18 if i > 1 else 22
    ws.append([]); ws.append(["Bosh buxgalter", None, "______________"]); ws.append(["Moliya-iqtisod ishlari bo'yicha prorektor", None, "______________"])
    out = io.BytesIO(); wb.save(out)
    return Response(out.getvalue(), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f'attachment; filename="{fn}.xlsx"'})


# ---------------------------------------------------------------------------------------------
# Bank ko'chirmasi: aniqlanmagan to'lovlar (moslashtirish yordamchisi — app/moliya_match.py)
#   Qatorlar qo'lda yoki CSV (sana, summa, to'lovchi, maqsad, hujjat №) orqali kiritiladi. Aniq ma'lumot (shartnoma raqami, HEMIS ID,
#   aniq F.I.Sh. + guruh) bo'lsa — avtomatik biriktiriladi va to'lov o'tkaziladi; aks holda «aniqlanmagan» navbatiga nomzodlar
#   (ball va sabablar bilan) bilan tushadi. Buxgalter taklifni tasdiqlaydi, boshqa talabani tanlaydi yoki «shartnoma to'lovi emas» /
#   «qaytarish» deb belgilaydi. Inson tasdiqlagan moslashtirish match_kind='qo'lda' (kim, qachon) sifatida saqlanadi.
# ---------------------------------------------------------------------------------------------
BANK_ST = {"avto": "Avtomatik biriktirildi", "aniqlanmagan": "Aniqlanmagan", "qo'lda": "Qo'lda biriktirildi",
           "shartnoma emas": "Shartnoma to'lovi emas", "qaytarish": "Qaytariladi"}

def bank_stats(con) -> dict:
    lim = (_today() - dt.timedelta(days=UNMATCHED_ALERT_DAYS)).isoformat()
    a = db.one(con, """SELECT COUNT(*) n, COALESCE(SUM(amount),0) s, COALESCE(SUM(line_date<?),0) stale, COALESCE(SUM(CASE WHEN line_date<? THEN amount END),0) ss,
                       MIN(line_date) oldest FROM fin_bank_lines WHERE status='aniqlanmagan'""", (lim, lim))
    by = {r["status"]: r["n"] for r in db.rows(con, "SELECT status, COUNT(*) n FROM fin_bank_lines GROUP BY status")}
    return {"n": a["n"], "sum": a["s"], "stale": a["stale"], "stale_sum": a["ss"], "oldest": a["oldest"],
            "oldest_days": (_today() - _d(a["oldest"])).days if a["oldest"] else None, "by_status": by}

def _plan_rows(con): return db.rows(con, "SELECT due, cum_pct, label FROM contract_plan ORDER BY due")

def _bank_hash(d, amount, payer, purpose, doc):
    return "|".join([d, str(amount), MM.norm(doc), MM.norm(purpose), MM.norm(payer)])

def _parse_amount(v) -> int:
    v = str(v or "").strip().replace(" ", " ")
    v = re.sub(r"[.,]\d{1,2}$", "", v)            # tiyin qismi
    v = re.sub(r"[^\d]", "", v)
    return int(v) if v else 0

def _parse_date(v) -> str:
    v = str(v or "").strip()
    for f in ("%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y", "%d.%m.%y"):
        try: return dt.datetime.strptime(v[:10], f).date().isoformat()
        except Exception: pass
    raise ValueError(v)

def _parse_csv(text: str) -> list[dict]:
    text = (text or "").lstrip("﻿").strip()
    if not text: return []
    first = text.splitlines()[0]
    delim = max([";", "\t", ","], key=lambda d: first.count(d))
    rows = list(csv.reader(io.StringIO(text), delimiter=delim))
    cols = ["date", "amount", "payer", "purpose", "doc_no"]
    alias = {"date": ("date", "sana", "дата"), "amount": ("amount", "summa", "сумма"), "payer": ("payer", "tolovchi", "to'lovchi", "плательщик"),
             "purpose": ("purpose", "maqsad", "izoh", "назначение"), "doc_no": ("doc_no", "doc", "hujjat", "nomer", "№", "номер")}
    h = [c.strip().lower() for c in rows[0]]
    if any(x in alias["date"] + alias["amount"] for x in h):
        cols = [next((k for k, al in alias.items() if any(c == a or c.startswith(a) for a in al)), f"_{i}") for i, c in enumerate(h)]
        rows = rows[1:]
    return [dict(zip(cols, [x.strip() for x in r])) for r in rows if any(x.strip() for x in r)]

# --- kontraktdan boshqa ochiq hisoblar (qayta o'qish, turar joy) — bank qatorini ularga ham moslashtirish ---
def _obligations(con) -> list[dict]:
    out = []
    q = [("qayta_oqish", """SELECT r.id ref, r.student_id sid, 'Qayta o''qish: ' || r.subject label, COALESCE(r.amount,0)-COALESCE(r.paid,0) lft,
                             s.full_name, s.hemis_id, g.name grp FROM restudy r JOIN students s ON s.id=r.student_id LEFT JOIN groups_ g ON g.id=s.group_id
                             WHERE r.decision='qayta_oqish' AND COALESCE(r.paid,0) < COALESCE(r.amount,0)"""),
         ("turar_joy", """SELECT ch.id ref, rs.student_id sid, 'Turar joy: ' || ch.period label, ch.amount-ch.paid lft, s.full_name, s.hemis_id, g.name grp
                          FROM yj_charges ch JOIN yj_residents rs ON rs.id=ch.resident_id JOIN students s ON s.id=rs.student_id
                          LEFT JOIN groups_ g ON g.id=s.group_id WHERE ch.paid < ch.amount""")]
    for kind, sql in q:
        try:
            for r in db.rows(con, sql):
                out.append({"kind": kind, "ref_id": r["ref"], "sid": r["sid"], "left": r["lft"], "label": r["label"], "full_name": r["full_name"],
                            "hemis_id": r["hemis_id"] or "", "grp": r["grp"] or ""})
        except sqlite3.OperationalError:      # modul jadvali hali yo'q
            pass
    return out

def _obl_index(con) -> dict:
    obs = _obligations(con); by_root, by_hemis = {}, {}
    for o in obs:
        tk = MM.tokens(o["full_name"]); o["sur"] = tk[0] if tk else ""; o["giv"] = tk[1] if len(tk) > 1 else ""
        if o["sur"]: by_root.setdefault(MM.root(o["sur"]), []).append(o)
        if o["hemis_id"]: by_hemis.setdefault(o["hemis_id"], []).append(o)
    return {"obs": obs, "by_root": by_root, "roots": list(by_root), "by_hemis": by_hemis}

def _hint(purpose: str, payer: str) -> set:
    t = MM.norm(f"{purpose} {payer}")
    return {k for k, ws in OBL_WORDS.items() if any(w in t for w in ws)}

def _obl_candidates(OI: dict, purpose: str, payer: str, doc_no: str, amount: int, limit: int = 4) -> list[dict]:
    hint = _hint(purpose, payer)
    seqs = MM.digit_seqs(purpose, doc_no)
    toks = [t for t in MM.tokens(purpose) + MM.tokens(payer) if t not in MM.STOP and len(t) >= 3]
    pool = {}
    for t in set(toks):
        r = MM.root(t)
        for k in ([r] if r in OI["by_root"] else []) + difflib.get_close_matches(r, OI["roots"], n=3, cutoff=0.8):
            for o in OI["by_root"].get(k, ()): pool[(o["kind"], o["ref_id"])] = o
    for sq in seqs:
        for o in OI["by_hemis"].get(sq, ()): pool[(o["kind"], o["ref_id"])] = o
    out = []
    for o in pool.values():
        sc, why = 0.0, []
        if o["hemis_id"] and o["hemis_id"] in seqs: sc += 100; why.append("HEMIS ID aniq mos")
        sur = max((MM.ratio(MM.root(o["sur"]), MM.root(x)) for x in toks), default=0) if o["sur"] else 0
        giv = max((MM.ratio(o["giv"], x) for x in toks), default=0) if o["giv"] else 0
        if sur >= 0.8 and giv >= 0.8:
            sim = round(100 * (sur + giv) / 2); sc += 30 + (sim - 80) * 0.75; why.append(f"F.I.Sh. o'xshash {sim}%")
        elif sur >= 0.85:
            sc += 12; why.append(f"familiya mos ({o['sur'].capitalize()})")
        if amount and amount == o["left"]:
            sc += 15; why.append("summa qayta o'qish to'loviga teng" if o["kind"] == "qayta_oqish" else "summa turar joy oylik to'loviga teng")
        elif amount and amount > o["left"]:
            sc -= 25; why.append(f"summa qoldiqdan katta (qoldiq {o['left']:,} so'm)".replace(",", " "))
        if o["kind"] in hint:
            sc += 15; why.append("maqsadda «qayta o'qish» deyilgan" if o["kind"] == "qayta_oqish" else "maqsadda turar joy / yotoqxona deyilgan")
        if sc < 25: continue
        out.append({"student_id": o["sid"], "full_name": o["full_name"], "hemis_id": o["hemis_id"], "grp": o["grp"], "contract_no": None,
                    "debt": o["left"], "score": max(1, min(97, round(sc))), "reasons": why, "kinds": [], "exact": False,
                    "pay_kind": o["kind"], "ref_id": o["ref_id"], "ref_label": o["label"]})
    out.sort(key=lambda x: (-x["score"], x["full_name"]))
    return out[:limit]

def _match_all(con, L: dict, plan: list, OI: dict | None = None) -> dict:
    """Kontrakt (moliya_match) + qayta o'qish va turar joy nomzodlari — bitta ro'yxat. Avto-biriktirish faqat kontrakt uchun."""
    m = MM.match(con, L["purpose"], L["payer"], L["doc_no"], L["amount"], plan)
    hint = _hint(L["purpose"], L["payer"])
    for c in m["candidates"]:
        c.update(pay_kind="kontrakt", ref_id=None, ref_label="Kontrakt")
        if hint:
            c["score"] = max(1, c["score"] - 15); c["reasons"].append("maqsadda kontrakt emas, " + ("qayta o'qish" if "qayta_oqish" in hint else "turar joy") + " deyilgan")
    if hint: m["auto"] = None
    other = _obl_candidates(OI or _obl_index(con), L["purpose"], L["payer"], L["doc_no"], L["amount"])
    m["candidates"] = sorted(m["candidates"] + other, key=lambda x: (-x["score"], x["full_name"]))[:6]
    return m

def _bank_process(c: Ctx, line_id: int) -> dict:
    """Bitta qatorni moslashtirish: avto bo'lsa — to'lov o'tkaziladi; aks holda nomzodlar saqlanadi."""
    L = db.one(_con, "SELECT * FROM fin_bank_lines WHERE id=?", (line_id,))
    m = _match_all(_con, L, _plan_rows(_con))
    rec = _norm_receipt(L["doc_no"]) if (L["doc_no"] or "").strip() else f"BK-{line_id}"
    dup = db.one(_con, "SELECT id, student_id FROM fin_payments WHERE receipt_no=? AND status='faol'", (rec,))
    note = None
    if dup:
        note = f"Diqqat: {rec} raqamli to'lov allaqachon kiritilgan (to'lov #{dup['id']}) — ikki marta o'tkazilmaydi"
        m["auto"] = None
    if m["auto"]:
        a = m["auto"]
        try:
            r = _post_payment(c, a["student_id"], rec, L["line_date"], L["amount"], "bank", L["payer"], f"Bank ko'chirmasi: {L['purpose'][:200]}",
                              bank_line_id=line_id, commit=False)
            _con.execute("""UPDATE fin_bank_lines SET status='avto', student_id=?, payment_id=?, match_kind='avto', match_score=?, match_reasons=?,
                            candidates=?, resolved_by='ISFT Core (avto)', resolved_at=? WHERE id=?""",
                         (a["student_id"], r["id"], a["score"], json.dumps(a["reasons"], ensure_ascii=False), json.dumps(m["candidates"], ensure_ascii=False), _now(), line_id))
            return {"status": "avto", "student_id": a["student_id"]}
        except HTTPException as e:
            note = f"Avtomatik biriktirilmadi: {e.detail}"
    _con.execute("UPDATE fin_bank_lines SET status='aniqlanmagan', candidates=?, resolve_note=? WHERE id=?",
                 (json.dumps(m["candidates"], ensure_ascii=False), note, line_id))
    return {"status": "aniqlanmagan", "top": m["candidates"][0] if m["candidates"] else None}

def _bank_add(c: Ctx, items: list[dict], import_id: str) -> dict:
    res = {"added": 0, "auto": 0, "unmatched": 0, "duplicates": 0, "errors": [], "ids": []}
    for i, it in enumerate(items, 1):
        try:
            d = _parse_date(it.get("date")); amt = _parse_amount(it.get("amount"))
            if amt <= 0: raise ValueError("summa")
            if _d(d) > _today(): raise ValueError("kelajak sanasi")
        except Exception as e:
            res["errors"].append(f"{i}-qator: sana yoki summa noto'g'ri ({e})"); continue
        payer, purpose, doc = (it.get("payer") or "")[:200], (it.get("purpose") or "")[:500], (it.get("doc_no") or "")[:60]
        h = _bank_hash(d, amt, payer, purpose, doc)
        if _con.execute("SELECT 1 FROM fin_bank_lines WHERE hash=?", (h,)).fetchone():
            res["duplicates"] += 1; continue
        cur = _con.execute("""INSERT INTO fin_bank_lines(import_id,line_date,amount,payer,purpose,doc_no,hash,status,created_by,created_by_name,created_at)
                              VALUES(?,?,?,?,?,?,?,?,?,?,?)""", (import_id, d, amt, payer, purpose, doc, h, "aniqlanmagan", c.user["id"], c.user["full_name"], _now()))
        r = _bank_process(c, cur.lastrowid); res["added"] += 1; res["ids"].append(cur.lastrowid)
        res["auto" if r["status"] == "avto" else "unmatched"] += 1
    _con.commit()
    return res

class BankIn(BaseModel):
    csv: str = Field("", max_length=2_000_000)
    lines: list[dict] = []

@router.post(P + "/bank/import")
def bank_import(body: BankIn, request: Request):
    c = C(request); _need(c, {"enter"}, "moliya: bank ko'chirmasi", CONTRACTS, msg="⛔ Bank ko'chirmasini buxgalteriya kiritadi.")
    items = (_parse_csv(body.csv) if body.csv.strip() else []) + list(body.lines or [])
    if not items: raise HTTPException(400, "Qatorlar topilmadi: CSV (sana; summa; to'lovchi; maqsad; hujjat №) yoki qo'lda kiriting")
    if len(items) > 2000: raise HTTPException(400, "Bir martada ko'pi bilan 2000 qator")
    imp = f"IMP-{clock.now().strftime('%Y%m%d%H%M%S')}"
    res = _bank_add(c, items, imp)
    _audit(c, "moliya: bank ko'chirmasi yuklandi", CONTRACTS, True,
           f"{imp} · {res['added']} qator · avto {res['auto']} · aniqlanmagan {res['unmatched']} · takroriy {res['duplicates']} · xato {len(res['errors'])}")
    return {"ok": True, "import_id": imp, **{k: v for k, v in res.items() if k != "ids"}, "stats": bank_stats(_con)}

@router.get(P + "/bank")
def bank_list(request: Request, status: str = "aniqlanmagan", q: str = ""):
    c = C(request); _need(c, {"enter", "approve"}, "moliya: aniqlanmagan to'lovlar")
    _audit(c, "moliya: aniqlanmagan to'lovlar", CONTRACTS, True, status)
    w, a = [], []
    if status in BANK_ST: w.append("b.status=?"); a.append(status)
    if q.strip(): w.append("(b.payer LIKE ? COLLATE NOCASE OR b.purpose LIKE ? COLLATE NOCASE OR b.doc_no LIKE ?)"); a += [f"%{q.strip()}%"] * 3
    rows = db.rows(_con, f"""SELECT b.*, s.full_name, s.hemis_id, g.name grp FROM fin_bank_lines b LEFT JOIN students s ON s.id=b.student_id
                             LEFT JOIN groups_ g ON g.id=s.group_id {'WHERE ' + ' AND '.join(w) if w else ''}
                             ORDER BY CASE b.status WHEN 'aniqlanmagan' THEN 0 ELSE 1 END, b.line_date, b.id LIMIT 200""", a)
    plan = _plan_rows(_con); today = _today(); OI = _obl_index(_con)
    for r in rows:
        if r["status"] == "aniqlanmagan":    # qarzlar o'zgargan bo'lishi mumkin — nomzodlar har safar yangilanadi
            m = _match_all(_con, r, plan, OI)
            r["candidates"] = m["candidates"]
            _con.execute("UPDATE fin_bank_lines SET candidates=? WHERE id=?", (json.dumps(m["candidates"], ensure_ascii=False), r["id"]))
        else:
            r["candidates"] = json.loads(r["candidates"] or "[]")
        r["match_reasons"] = json.loads(r["match_reasons"] or "[]")
        r["age_days"] = (today - _d(r["line_date"])).days
        r["stale"] = r["status"] == "aniqlanmagan" and r["age_days"] > UNMATCHED_ALERT_DAYS
        r["status_label"] = BANK_ST.get(r["status"], r["status"]); r["resolved_by"] = _short(r["resolved_by"]); r["created_by_name"] = _short(r["created_by_name"])
        r.pop("hash", None)
    _con.commit()
    return {"items": rows, "stats": bank_stats(_con), "statuses": BANK_ST, "alert_days": UNMATCHED_ALERT_DAYS}

class BankConfirm(BaseModel):
    student_id: int
    note: str = Field("", max_length=300)
    pay_kind: str = "kontrakt"
    ref_id: int | None = None

@router.post(P + "/bank/{lid}/confirm")
def bank_confirm(lid: int, body: BankConfirm, request: Request):
    c = C(request); _need(c, {"enter"}, "moliya: to'lovni biriktirish", CONTRACTS, f"bank #{lid}", msg="⛔ To'lovni buxgalteriya biriktiradi.")
    L = db.one(_con, "SELECT * FROM fin_bank_lines WHERE id=?", (lid,))
    if not L: raise HTTPException(404)
    if L["status"] != "aniqlanmagan":
        _audit(c, "moliya: qayta biriktirish rad etildi", CONTRACTS, False, f"bank #{lid} · {L['status']}")
        raise HTTPException(409, f"Qator allaqachon ko'rib chiqilgan: {BANK_ST.get(L['status'], L['status'])}")
    cands = json.loads(L["candidates"] or "[]")
    if body.pay_kind not in PAY_KINDS: raise HTTPException(400, "To'lov turi noto'g'ri")
    pos = next((i for i, x in enumerate(cands) if x["student_id"] == body.student_id and (x.get("pay_kind") or "kontrakt") == body.pay_kind
                and (body.ref_id is None or x.get("ref_id") == body.ref_id)), None)
    ref = body.ref_id if body.ref_id is not None else (cands[pos].get("ref_id") if pos is not None else None)
    rec = _norm_receipt(L["doc_no"]) if (L["doc_no"] or "").strip() else f"BK-{lid}"
    try:
        r = _post_payment(c, body.student_id, rec, L["line_date"], L["amount"], "bank", L["payer"], f"Bank ko'chirmasi: {L['purpose'][:200]}",
                          bank_line_id=lid, commit=False, kind=body.pay_kind, ref_id=ref)
    except Exception:
        _con.rollback(); raise
    how = (f"taklif #{pos + 1} tasdiqlandi ({cands[pos]['score']} ball)" if pos is not None else "qidiruv orqali boshqa talaba tanlandi") + \
          ("" if body.pay_kind == "kontrakt" else f" · {r.get('label') or PAY_KINDS[body.pay_kind]}")
    cur = _con.execute("""UPDATE fin_bank_lines SET status='qo''lda', student_id=?, payment_id=?, match_kind='qo''lda', match_score=?, match_reasons=?,
                          resolved_by=?, resolved_at=?, resolve_note=? WHERE id=? AND status='aniqlanmagan'""",
                       (body.student_id, r["id"], cands[pos]["score"] if pos is not None else None,
                        json.dumps(cands[pos]["reasons"] if pos is not None else [], ensure_ascii=False), c.user["full_name"], _now(),
                        (how + (f" · {body.note.strip()}" if body.note.strip() else ""))[:300], lid))
    if cur.rowcount != 1:      # parallel tasdiq — ikki marta o'tkazilmaydi
        _con.rollback(); raise HTTPException(409, "Qator boshqa xodim tomonidan allaqachon biriktirildi")
    _con.commit()
    _audit(c, "moliya: to'lov qo'lda biriktirildi", CONTRACTS, True, f"bank #{lid} → talaba #{body.student_id} · {how}")
    return {"ok": True, "payment_id": r["id"], "contract": r["contract"], "kind": body.pay_kind, "left": r["left"], "label": r.get("label"), "how": how}

class BankDismiss(BaseModel):
    kind: str
    reason: str = Field(..., min_length=5, max_length=300)

@router.post(P + "/bank/{lid}/dismiss")
def bank_dismiss(lid: int, body: BankDismiss, request: Request):
    c = C(request); _need(c, {"enter"}, "moliya: bank qatorini belgilash", CONTRACTS, f"bank #{lid}", msg="⛔ Buxgalteriya belgilaydi.")
    if body.kind not in ("shartnoma emas", "qaytarish"): raise HTTPException(400)
    cur = _con.execute("""UPDATE fin_bank_lines SET status=?, match_kind='qo''lda', resolved_by=?, resolved_at=?, resolve_note=? WHERE id=? AND status='aniqlanmagan'""",
                       (body.kind, c.user["full_name"], _now(), body.reason.strip(), lid))
    if cur.rowcount != 1: raise HTTPException(409, "Qator topilmadi yoki allaqachon ko'rib chiqilgan")
    _con.commit(); _audit(c, f"moliya: bank qatori — {body.kind}", CONTRACTS, True, f"bank #{lid} · {body.reason[:150]}")
    return {"ok": True}

# ---------------------------------------------------------------------------------------------
# Kutilayotgan ishlar (Mening vazifalarim / qo'ng'iroqcha / bosh sahifa uchun): [{kind,title,sub,due,view,src,sign}]
# ---------------------------------------------------------------------------------------------
def pending(c: Ctx) -> list[dict]:
    m = mode(c); out = []
    if m not in ("enter", "approve"): return out
    sp = lambda v: f"{v:,}".replace(",", " ")
    bk = bank_stats(_con)
    if bk["n"] and m == "enter":
        out.append({"kind": "moliya_bank", "title": f"Aniqlanmagan to'lovlar: {bk['n']} ta — talabaga biriktiring",
                    "sub": f"{sp(bk['sum'])} so'm" + (f" · {bk['stale']} tasi {UNMATCHED_ALERT_DAYS} kundan eski" if bk["stale"] else ""),
                    "due": bk["oldest"], "view": "moliya", "tab": "bank", "src": "Moliya", "sign": False})
    today = _today()
    days = [r["d"] for r in db.rows(_con, "SELECT DISTINCT paid_on d FROM fin_payments WHERE status='faol' AND paid_on>=? AND paid_on<? ORDER BY paid_on",
                                     ((today - dt.timedelta(days=20)).isoformat(), today.isoformat()))]
    open_days = [d for d in days if not _closed(_con, d)]
    if open_days and m == "enter":
        out.append({"kind": "moliya_recon", "title": f"Solishtirilmagan kunlar: {len(open_days)} ta",
                    "sub": ", ".join(_d(x).strftime("%d.%m") for x in open_days[:6]), "due": open_days[0], "view": "moliya", "tab": "recon",
                    "src": "Moliya", "sign": False})
    if m == "approve":
        for e in db.rows(_con, "SELECT * FROM fin_expenses WHERE status='kutilmoqda' ORDER BY created_at LIMIT 20"):
            out.append({"kind": "moliya_expense", "title": f"Xarajat tasdig'i: {e['payee'] or e['category']} — {sp(e['amount'] or 0)} so'm",
                        "sub": f"{e['category']} · {(e['purpose'] or '')[:120]}" + (f" · {e['reason_route']}" if e.get("reason_route") else ""),
                        "due": (e["created_at"] or e["spent_on"] or "")[:10], "view": "moliya", "tab": "expenses", "src": "Moliya", "sign": True})
    return out

# --- demo: haqiqiy hayotdagi xatoli ko'chirma qatorlari (sintetik, mavjud demo talabalar bo'yicha) ---
_L2C = [("sh", "ш"), ("ch", "ч"), ("o'", "ў"), ("g'", "ғ"), ("yo", "ё"), ("ye", "е"), ("yu", "ю"), ("ya", "я"), ("a", "а"), ("b", "б"), ("d", "д"), ("e", "е"), ("f", "ф"),
        ("g", "г"), ("h", "ҳ"), ("i", "и"), ("j", "ж"), ("k", "к"), ("l", "л"), ("m", "м"), ("n", "н"), ("o", "о"), ("p", "п"), ("q", "қ"), ("r", "р"),
        ("s", "с"), ("t", "т"), ("u", "у"), ("v", "в"), ("x", "х"), ("y", "й"), ("z", "з"), ("'", "ъ")]
def to_cyr(s: str) -> str:
    out, i, low = [], 0, s
    while i < len(s):
        for la, cy in _L2C:
            if low[i:i + len(la)].lower() == la:
                out.append(cy.upper() if s[i].isupper() else cy); i += len(la); break
        else:
            out.append(s[i]); i += 1
    return "".join(out)

def demo_students(con, n: int, offset: int = 0, need_apos: bool = False, exclude=()) -> list[dict]:
    """F.I.Sh. (familiya ildizi + ism + otasining ismi) bo'yicha yagona, qarzi bor, patronimli kontrakt talabalari — demo va testlar uchun."""
    rows = db.rows(con, """SELECT s.id, s.full_name, s.hemis_id, s.contract_amount, s.paid_amount, g.name grp FROM students s JOIN groups_ g ON g.id=s.group_id
                           WHERE s.payment_type='kontrakt' AND s.status='faol' AND s.contract_amount - s.paid_amount >= 4000000
                           AND s.full_name LIKE '% % % %' ORDER BY (s.id * 7919) % 10007""")
    cnt = {}
    for r in db.rows(con, "SELECT full_name FROM students WHERE payment_type='kontrakt'"):
        t = MM.tokens(r["full_name"]); k = (MM.root(t[0]), t[1], t[2]) if len(t) > 2 else None; cnt[k] = cnt.get(k, 0) + 1
    out = []
    for r in rows:
        t = MM.tokens(r["full_name"])
        if cnt.get((MM.root(t[0]), t[1], t[2])) != 1 or r["id"] in exclude: continue
        if need_apos and "'" not in r["full_name"].split()[0] + r["full_name"].split()[1]: continue
        if offset: offset -= 1; continue
        out.append(r)
        if len(out) >= n: break
    return out

def demo_lines(con, studs: list[dict], apos: dict, day: str, tag: str = "") -> list[tuple[dict, int, str]]:
    """[(qator, kutilgan talaba id, holat turi)] — 1 aniq shartnoma, 1 aniq HEMIS, 8 xatoli/aniqlanmagan, 1 shartnoma emas."""
    def parts(s):
        w = s["full_name"].split(); return w[0], w[1], w[2]
    def typo(word):   # bitta harf almashadi
        i = len(word) // 2; return word[:i] + ("a" if word[i] != "a" else "e") + word[i + 1:]
    L = []
    s = studs[0]; L.append(({"date": day, "amount": 2_000_000, "payer": "Ota-onasi", "purpose": f"Kontrakt to'lovi shartnoma {MM.contract_no(s['id'])} {s['full_name']}",
                            "doc_no": f"PP{tag}0101"}, s["id"], "avto: shartnoma"))
    s = studs[1]; L.append(({"date": day, "amount": 1_500_000, "payer": parts(s)[0], "purpose": f"HEMIS {s['hemis_id']} kontrakt", "doc_no": f"PP{tag}0102"}, s["id"], "avto: HEMIS"))
    s = studs[2]; cd = MM._contract_digits(s["id"]); bad = cd[:6] + str((int(cd[6]) + 3) % 10) + cd[7]
    L.append(({"date": day, "amount": 2_500_000, "payer": f"{parts(s)[0]} {parts(s)[1]}", "purpose": f"Shartnoma №{bad[:2]}-{bad[2:7]}-{bad[7]} uchun to'lov", "doc_no": f"PP{tag}0103"},
              s["id"], "shartnoma raqami 1 belgi xato"))
    s = studs[3]; cd = MM._contract_digits(s["id"]); i = 3 if cd[3] != cd[4] else 5; sw = cd[:i] + cd[i + 1] + cd[i] + cd[i + 2:]
    L.append(({"date": day, "amount": 3_000_000, "payer": "", "purpose": f"oplata kontrakta {sw[:2]}-{sw[2:7]}-{sw[7]} {parts(s)[0]}", "doc_no": f"PP{tag}0104"},
              s["id"], "raqamlar o'rni almashgan"))
    s = studs[4]; f, g, p = parts(s)
    L.append(({"date": day, "amount": 4_000_000, "payer": to_cyr(f"{f} {g}"), "purpose": "Контракт тўлови " + to_cyr(f"{f} {g} {p} {s['grp']}") + " гуруҳ", "doc_no": f"PP{tag}0105"},
              s["id"], "kirillcha F.I.Sh. + guruh"))
    s = studs[5]; f, g, p = parts(s); fam = re.sub(r"(ova|eva)$", lambda m: m.group(1)[:-1], f)
    L.append(({"date": day, "amount": 2_200_000, "payer": f"{fam} {p}", "purpose": f"{'Qizim' if s['full_name'].endswith('qizi') else 'O‘g‘lim'} {g} uchun kontrakt pul",
               "doc_no": f"PP{tag}0106"}, s["id"], "to'lovchi — ota, raqamsiz"))
    s = apos; f, g, p = parts(s); debt = s["contract_amount"] - s["paid_amount"]
    L.append(({"date": day, "amount": debt, "payer": typo(f.replace("'", "ʻ")), "purpose": f"{typo(f.replace(chr(39), '`'))} {g.replace(chr(39), '’')} {p} {s['grp']} kontrakt",
               "doc_no": f"PP{tag}0107"}, s["id"], "F.I.Sh. xatoli, apostrof turlari, summa = qarz"))
    s = studs[6]; h = s["hemis_id"]; hb = h[:5] + str((int(h[5]) + 1) % 10) + h[6:]
    L.append(({"date": day, "amount": 1_800_000, "payer": "", "purpose": f"Talaba ID {hb} oqish uchun", "doc_no": f"PP{tag}0108"}, s["id"], "HEMIS ID 1 belgi xato"))
    s = studs[7]; f, g, p = parts(s)
    L.append(({"date": day, "amount": 2_700_000, "payer": f"{g} {p} {f}", "purpose": "kontrakt to'lov 2026-2027 o'quv yili", "doc_no": f"PP{tag}0109"},
              s["id"], "raqamsiz, ism-familiya tartibi teskari"))
    L.append(({"date": day, "amount": 450_000, "payer": "«Demo Savdo» MChJ", "purpose": "Majlislar zali ijarasi uchun, 15.11 tadbir", "doc_no": f"PP{tag}0110"},
              None, "shartnoma to'lovi emas"))
    return L

def seed_bank_demo(con):
    if con.execute("SELECT 1 FROM fin_meta WHERE k='bank_seed'").fetchone(): return
    studs = demo_students(con, 8); ap = demo_students(con, 1, need_apos=True, exclude={x["id"] for x in studs})
    if len(studs) < 8 or not ap: return
    uid = (db.one(con, "SELECT id FROM users WHERE role='buxgalteriya' AND active=1 ORDER BY id LIMIT 1") or {}).get("id")
    if not uid: return
    c = rbac.ctx_for(con, uid)
    days = [d for d in _workdays_back(6, _today())]
    lines = demo_lines(con, studs, ap[0], days[-1].isoformat())
    # bir nechta qator — eskiroq (ogohlantirish ko'rinishi uchun), o'sha kunlar ochiq bo'lishi kerak emas: aniqlanmaganlar to'lov o'tkazmaydi
    for i, (ln, _, _) in enumerate(lines):
        if i in (5, 8, 9): ln["date"] = days[0].isoformat()
    res = _bank_add(c, [ln for ln, _, _ in lines], "IMP-DEMO")
    ids = res["ids"]
    con.execute("INSERT OR REPLACE INTO fin_meta(k,v) VALUES('bank_demo',?)", (json.dumps({str(i): [sid, kind] for i, (_, sid, kind) in zip(ids, lines)}, ensure_ascii=False),))
    con.execute("INSERT INTO fin_meta(k,v) VALUES('bank_seed',?)", (_now(),)); con.commit()
