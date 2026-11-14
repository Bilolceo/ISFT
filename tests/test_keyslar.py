"""«Ortda qolganlar» → keys boshqaruvi, haftalik ritm, to'siq nuqtalaridagi eslatmalar va tajriba, dars oxiri testi, «ISFT Ready» (docs/keyslar.md).

1. Sof funksiyalar: ish kunlari (SLA), SLA holati, ko'rsatkichlar matematikasi (median, SLA ulushi, qayta faollashish), yuklama tavsiyasi,
   tushuntirish matni, haftalik jadval (avvalgi hisob bilan tenglik, muddatni o'zgartirish), «ISFT Ready» qoidasi, savollar taqsimoti
   (takrorsiz, 3–5, faqat berilgan tasdiqlangan to'plamdan), tajriba qo'li (barqaror, ~yarmi), taqqoslash (guruh darajasidagi Welch oraliq).
2. Demografiya yo'q: qoidalar demografik maydonlarni o'qimaydi (natija o'zgarmaydi; kodda bunday nom yo'q).
3. Keyslar (HTTP): ruxsatlar, hayot sikli (natija majburiy, «boshqa» — izoh, keyingi qadam), yuklama chegarasi (409 + tavsiya, force — audit),
   14 kundan keyin avtomatik qayta ochish, bayroq yo'qolsa tizim yopishi, ko'rsatkichlar, Nazorat markazi (istisno va /api/nazorat/keyslar).
4. Haftalik taqvim → kutilgan progress (guruh taqvimi), talaba kabineti «Bu hafta».
5. To'siq nuqtalari: rejim (faqat bo'lim boshlig'i), qo'llar, nazorat qo'li yuborilmaydi, takror yo'q (dedupe), cheklovlar (oraliq, haftalik, kunlik),
   natija taqqoslash.
6. Dars oxiri testi (Kurs muharriri va Dars tayyorlash): faqat tasdiqlangan, fan bo'yicha takrorsiz, 3–5, idempotent, ruxsatlar.
7. «ISFT Ready»: yaratish, mazmun, tasdiqlash → eksport → kabinet kartasi va ishga tushirish, «boshlamagan» bayrog'i.
8. Brauzer (PW va CHROME berilganda): keyslar ekrani, keys kartasi, natija, eslatmalar, Nazorat kartasi, kabinet «Bu hafta» (tools/keyslar_check.js;
   skrinshotlar — $KS_OUT).

Ishga tushirish: python tests/run_all.py --only keyslar. DIQQAT: bazani o'zgartiradi (keyslar, taqvim, kurslar); yaratgan eslatmalari va
«ISFT Ready» kursini oxirida tozalaydi.
"""
import datetime as dt, inspect, json, os, re, shutil, sqlite3, statistics, subprocess, sys, uuid
from pathlib import Path
import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
B = os.environ.get("ISFT_TEST_URL", "http://127.0.0.1:8000")
DBP = Path(os.environ.get("ISFT_CORE_DB") or ROOT / "data" / "jarvis.db")
PW = re.search(r'DEMO_PASSWORD = os.getenv\("ISFT_CORE_DEMO_PASSWORD", "([^"]+)"\)', (ROOT / "app" / "rbac.py").read_text()).group(1)
SDEMO = os.getenv("ISFT_CORE_STUDENT_DEMO_PASSWORD", "Talaba2026")
NEWPW = "Darslar2026x"
fails = []
def ok(cond, msg):
    print(("  ✓ " if cond else "  ✗ ") + msg)
    if not cond: fails.append(msg)
def q(sql, a=()):
    con = sqlite3.connect(DBP, timeout=30); con.row_factory = sqlite3.Row
    try: return [dict(r) for r in con.execute(sql, a).fetchall()]
    finally: con.close()
def x(sql, a=()):
    con = sqlite3.connect(DBP, timeout=30)
    try: cur = con.execute(sql, a); con.commit(); return cur.lastrowid
    finally: con.close()
def uid(role):
    return q("SELECT id FROM users WHERE role=? AND COALESCE(active,1)=1 ORDER BY id LIMIT 1", (role,))[0]["id"]
def S(u):
    c = httpx.Client(base_url=B, timeout=300)
    r = c.post("/api/login", json={"user_id": u, "password": PW}); assert r.status_code == 200, f"login {u}: {r.text}"
    return c
def ST(sid):
    h = q("SELECT hemis_id FROM students WHERE id=?", (sid,))[0]["hemis_id"]
    c = httpx.Client(base_url=B, timeout=120)
    r = c.post("/api/talaba/login", json={"hemis_id": h, "password": SDEMO})
    if r.status_code != 200: r = c.post("/api/talaba/login", json={"hemis_id": h, "password": NEWPW})
    assert r.status_code == 200, r.text
    if r.json().get("must_change"):
        assert c.post("/api/talaba/password", json={"current": SDEMO, "new": NEWPW}).status_code == 200
    return c

from app import lrs_analytics as LA, keyslar as KS, tajriba as TJ, dars_testi as DT, haftalik as H, isft_ready as RDY, ortda as ORT, lrs as L, clock
_con = sqlite3.connect(DBP, timeout=30, check_same_thread=False); _con.row_factory = sqlite3.Row
L._con = _con; L._KEY.clear(); ORT._con = _con; H._con = _con; TJ._con = _con; KS._con = _con; RDY._con = _con
P_ = lambda s: dt.datetime.fromisoformat(s)

# =============================================================================================
print("== 1. Sof funksiyalar")
ok(KS.add_workdays(P_("2026-11-13T10:00:00"), 2) == P_("2026-11-17T10:00:00") and KS.add_workdays(P_("2026-11-14T09:00:00"), 2) == P_("2026-11-17T09:00:00")
   and KS.add_workdays(P_("2026-11-16T09:00:00"), 2) == P_("2026-11-18T09:00:00"), "SLA: 2 ish kuni (juma → seshanba, shanba → seshanba, dushanba → chorshanba)")
NOW = P_("2026-11-14T12:00:00")
C6 = [
    {"status": "jarayonda", "opened_at": "2026-11-10T09:00:00", "sla_due": "2026-11-12T09:00:00", "first_contact_at": "2026-11-11T09:00:00", "reengaged_at": "2026-11-13T10:00:00"},
    {"status": "jarayonda", "opened_at": "2026-11-01T09:00:00", "sla_due": "2026-11-04T09:00:00", "first_contact_at": "2026-11-05T09:00:00", "reengaged_at": None},
    {"status": "ochiq", "opened_at": "2026-11-11T09:00:00", "sla_due": "2026-11-13T09:00:00", "first_contact_at": None},
    {"status": "yopilgan", "outcome": KS.AUTO, "opened_at": "2026-11-11T09:00:00", "sla_due": "2026-11-13T09:00:00", "closed_at": "2026-11-12T08:00:00"},
    {"status": "yopilgan", "outcome": "gaplashildi", "opened_at": "2026-10-20T09:00:00", "sla_due": "2026-10-22T09:00:00", "first_contact_at": "2026-10-21T09:00:00",
     "closed_at": "2026-10-23T09:00:00", "reengaged_at": "2026-10-30T09:00:00"},
    {"status": "yopilgan", "outcome": "javob_bermadi", "opened_at": "2026-10-19T09:00:00", "sla_due": "2026-10-21T09:00:00", "first_contact_at": "2026-10-19T21:00:00",
     "closed_at": "2026-10-19T21:00:00", "reengaged_at": None},
]
m = KS.metrics(C6, NOW, 14)
ok((m["opened"], m["closed"], m["auto_closed"], m["open"], m["overdue"], m["contacted"]) == (6, 2, 1, 3, 1, 4), f"Sonlar: ochilgan/yopilgan/tizim/ochiq/SLA o'tgan/bog'lanilgan ({m['opened']}, {m['closed']}, {m['auto_closed']}, {m['open']}, {m['overdue']}, {m['contacted']})")
ok(m["median_contact_h"] == 24.0, f"Median bog'lanish vaqti: 12, 24, 24, 96 soat → 24 ({m['median_contact_h']})")
ok((m["sla_n"], m["sla_ok"], m["sla_pct"]) == (5, 3, 60.0), f"SLA: 5 ta baholanadi (SLA'dan oldin tizim yopgani — yo'q), 3 tasi muddatida → 60 % ({m['sla_n']}, {m['sla_ok']}, {m['sla_pct']})")
ok((m["reeng_n"], m["reeng_ok"], m["reeng_pending"], m["reeng_pct"]) == (3, 2, 1, 66.7), f"Qayta faollashish: 2/3, 1 ta oynasi tugamagan → 66,7 % ({m['reeng_n']}, {m['reeng_ok']}, {m['reeng_pending']}, {m['reeng_pct']})")
ok(m["outcomes"] == {"gaplashildi": 1, "javob_bermadi": 1}, "Natijalar taqsimoti (tizim yopgani — kirmaydi)")
ok(KS.metrics([], NOW)["sla_pct"] is None and KS.metrics([], NOW)["median_contact_h"] is None, "Bo'sh to'plam — ulush va median yo'q (0 emas)")
ok([KS.sla_state(c, NOW) for c in C6] == ["met", "missed", "overdue", "ok", "met", "met"], f"SLA holati: {[KS.sla_state(c, NOW) for c in C6]}")
cands = [{"id": 1, "load": 50, "group_tutor": True, "same_faculty": True}, {"id": 2, "load": 12, "group_tutor": False, "same_faculty": True},
         {"id": 3, "load": 3, "group_tutor": False, "same_faculty": False}, {"id": 4, "load": 20, "group_tutor": False, "same_faculty": True}]
ok(KS.suggest(cands, 50)["id"] == 2 and KS.suggest(cands, 60)["id"] == 1 and KS.suggest([dict(c, load=99) for c in cands], 50) is None,
   "Yuklama tavsiyasi: to'la guruh tyutori o'tkaziladi → shu fakultetning eng kam yuklangani; hamma to'la — tavsiya yo'q")
ex = KS.explain([{"title": "Iqtisodiyot nazariyasi", "expected": 30, "done": 6, "days_inactive": 12, "max_fails": 4, "fail_lesson": "A7",
                  "reasons": [{"code": "ortda"}, {"code": "faolsiz"}, {"code": "test"}]}], LA.DEFAULTS)
ok(len(ex) == 3 and "30 ta dars" in ex[0] and "24 dars ortda" in ex[0] and "qoida: 3" in ex[0] and "12 kun" in ex[1] and "A7" in ex[2], f"Tushuntirish — raqamlar va qoida chegarasi bilan: {ex[0]}")
# haftalik jadval
st0 = dt.date(2026, 8, 31)                # dushanba
bad = [(n, d) for n in (1, 7, 15, 45, 46) for d in range(-5, 130)
       if LA.expected_by_due(LA.schedule(n, st0, 15), st0 + dt.timedelta(days=d), 1) != LA.expected_done(n, st0, st0 + dt.timedelta(days=d), 15, 1)
       or LA.released_by(LA.schedule(n, st0, 15), st0 + dt.timedelta(days=d)) != LA.released(n, st0, st0 + dt.timedelta(days=d), 15)]
ok(not bad, f"Standart taqvim: muddat bo'yicha kutilgan progress avvalgi hisob bilan aynan bir xil (5 kurs × 135 kun; farq: {bad[:3]})")
sc = LA.schedule(45, dt.date(2026, 9, 1), 15)
ok(sc[0]["release"] == dt.date(2026, 9, 1) and sc[0]["due"] == dt.date(2026, 9, 6) and sc[3]["release"] == dt.date(2026, 9, 7) and sc[3]["due"] == dt.date(2026, 9, 13)
   and sc[-1]["week"] == 15, "Jadval: dars o'z haftasi boshida chiqadi (1-hafta — semestr boshlangan kun), muddati — yakshanba")
ov = LA.schedule(45, dt.date(2026, 9, 1), 15, {0: dt.date(2026, 9, 20), 1: dt.date(2026, 8, 1)})
ok(ov[0]["due"] == dt.date(2026, 9, 20) and ov[1]["due"] == dt.date(2026, 9, 6), "Muddatni o'zgartirish; chiqarilishdan oldingi muddat qabul qilinmaydi")
ok(LA.expected_by_due(ov, dt.date(2026, 9, 14), 1) == LA.expected_by_due(sc, dt.date(2026, 9, 14), 1) - 1, "Kechiktirilgan muddat — o'sha dars hali kutilmaydi")
ok(LA.ready_reasons(False, False, dt.date(2026, 9, 8), dt.date(2026, 9, 6))[0]["code"] == "ready" and "Boshlamagan" in LA.ready_reasons(False, False, dt.date(2026, 9, 8), dt.date(2026, 9, 6))[0]["label"]
   and LA.ready_reasons(True, True, dt.date(2026, 9, 8), dt.date(2026, 9, 6)) == [] and LA.ready_reasons(False, False, dt.date(2026, 9, 6), dt.date(2026, 9, 6)) == [],
   "«ISFT Ready» qoidasi: muddat o'tgan va tugatilmagan — «boshlamagan»; tugatgan yoki muddat kuni — bayroq yo'q")
# savollar taqsimoti
pool = {1: list(range(1, 11)), 2: [11, 12], 3: list(range(21, 27))}
plan, skip = DT.allocate([(101, 1), (102, 1), (103, 2), (104, None), (105, 3)], pool, {3}, seed="t")
allq = [i for v in plan.values() for i in v]
ok(set(plan) == {101, 102, 105} and set(skip) == {103, 104} and len(allq) == len(set(allq)) and 3 not in allq and all(3 <= len(v) <= 5 for v in plan.values())
   and set(plan[101]) | set(plan[102]) <= set(pool[1]) and set(plan[105]) <= set(pool[3]),
   f"Taqsimot: takrorsiz, 3–5 ta, faqat o'z mavzusining tasdiqlangan to'plamidan, ishlatilgan savol yo'q; yetmasa / mavzu yo'q — o'tkaziladi ({ {k: len(v) for k, v in plan.items()} })")
ok(DT.allocate([(101, 1), (102, 1), (103, 2), (104, None), (105, 3)], pool, {3}, seed="t")[0] == plan and any(v != sorted(v) for v in plan.values()),
   "Taqsimot barqaror (bir xil urug') va aralashtirilgan")
# tajriba qo'li va taqqoslash
arms = [TJ.arm("t_due48", "abc", g) for g in range(1, 1001)]
ok(arms == [TJ.arm("t_due48", "abc", g) for g in range(1, 1001)] and 0.45 < arms.count("tajriba") / 1000 < 0.55, f"Qo'l barqaror, guruhlarning ~yarmi ({arms.count('tajriba')}/1000)")
ok(sum(a != TJ.arm("t_due48", "xyz", g) for g, a in zip(range(1, 1001), arms)) > 300, "Yangi tuz — qo'llar qayta taqsimlanadi")
rows = []
for g, rate, a in [(1, 5, "tajriba"), (2, 6, "tajriba"), (3, 7, "tajriba"), (4, 8, "tajriba"), (5, 4, "nazorat"), (6, 5, "nazorat"), (7, 5, "nazorat"), (8, 6, "nazorat")]:
    rows += [{"group": g, "arm": a, "y": 1 if i < rate else 0, "lessons": 2 if i < rate else 0} for i in range(10)]
cm = TJ.compare(rows)
se = (statistics.variance([50, 60, 70, 80]) / 4 + statistics.variance([40, 50, 50, 60]) / 4) ** 0.5
num_ = (statistics.variance([50, 60, 70, 80]) / 4 + statistics.variance([40, 50, 50, 60]) / 4) ** 2
df = num_ / ((statistics.variance([50, 60, 70, 80]) / 4) ** 2 / 3 + (statistics.variance([40, 50, 50, 60]) / 4) ** 2 / 3)
lo, hi = 15 - TJ.t95(df) * se, 15 + TJ.t95(df) * se
ok(cm["arms"]["tajriba"]["rate"] == 65.0 and cm["arms"]["nazorat"]["rate"] == 50.0 and cm["diff"] == 15.0 and cm["arms"]["tajriba"]["groups"] == 4,
   f"Taqqoslash: 65 % va 50 % → farq 15 f.p. (4 va 4 guruh)")
ok(cm["ci"] and abs(cm["ci"][0] - lo) < 0.06 and abs(cm["ci"][1] - hi) < 0.06 and 4.9 < df < 5.2 and TJ.t95(df) == 2.447,
   f"95 % oraliq guruhlar darajasida (Welch, df≈{df:.2f}, t=2,447): [{cm['ci'][0]}; {cm['ci'][1]}] ≈ [{lo:.1f}; {hi:.1f}]")
ok(any("0 ni o'z ichiga" in c for c in cm["caveats"]) and any("Guruhlar soni kam" in c for c in cm["caveats"]), "Ogohlantirishlar: oraliq 0 ni qamraydi, guruhlar kam")
one = TJ.compare([{"group": 1, "arm": "tajriba", "y": 1}, {"group": 2, "arm": "nazorat", "y": 0}])
ok(one["ci"] is None and any("kamida 2 ta guruh" in c for c in one["caveats"]) and any("Talabalar soni kam" in c for c in one["caveats"]), "Bitta guruhda — oraliq hisoblanmaydi, kichik tanlov ogohlantirishi")

# =============================================================================================
print("== 2. Demografiya qoidalarda yo'q")
base = {"expected": 20, "done": 5, "max_fails": 4, "fail_lesson": "A3", "days_inactive": 10, "started": True}
demo = {"gender": "ayol", "jins": "erkak", "birth_date": "2001-01-01", "age": 19, "yosh": 40, "region": "Qashqadaryo", "viloyat": "Toshkent", "millat": "x",
        "nationality": "y", "payment": "kontrakt", "grant": True, "disability": True, "income": 0}
ok(LA.risk_reasons({**base, **demo}) == LA.risk_reasons(base) and set(LA.RULE_INPUTS) == set(base), "Qoida natijasi demografik maydonlardan bog'liq emas; kirishlar — faqat o'quv faolligi")
src = inspect.getsource(LA.risk_reasons) + inspect.getsource(LA.ready_reasons) + inspect.getsource(KS.flagged) + inspect.getsource(KS.explain)
hits = [w for w in KS.DEMOGRAPHIC if re.search(rf"\b{w}", src, re.I)]
ok(not hits, f"Qoida kodida demografik so'zlar yo'q ({hits})")
csrc = inspect.getsource(ORT.course_rows)
cols = {r["name"] for r in q("PRAGMA table_info(students)")}
dcols = [c for c in cols if any(w in c.lower() for w in ("gender", "birth", "region", "nation", "citizen", "address", "passport", "sex"))]
ok(not [c for c in dcols if re.search(rf"\b{c}\b", csrc)], f"«Ortda qolganlar» hisobi talabaning demografik ustunlarini o'qimaydi ({sorted(dcols)})")

# =============================================================================================
print("== 3. Keyslar: ruxsatlar, hayot sikli, yuklama, qayta ochish, ko'rsatkichlar")
head, staff, rek, pro = S(uid("masofaviy")), S(uid("masofaviy_xodim")), S(uid("rektor")), S(uid("prorektor_oquv"))
teach, kaf, bux = S(uid("oqituvchi")), S(uid("kafedra")), S(uid("buxgalteriya"))
TUTS = [r["id"] for r in q("SELECT id FROM users WHERE role='tyutor' AND COALESCE(active,1)!=0 ORDER BY id")]
T1, T2 = TUTS[5], TUTS[6]
t1, t2 = S(T1), S(T2)
K = "/api/ortda/keys"
sy = head.post(K + "/sync")
ok(sy.status_code == 200 and staff.post(K + "/sync").status_code == 200 and t1.post(K + "/sync").status_code == 403, f"Sinxronizatsiya: bo'lim — ha, tyutor — 403 ({sy.json()})")
lh = head.get(K, params={"limit": 200}).json()
ok(lh["total"] > 0 and lh["items"] and all(i["explain"] for i in lh["items"]) and "phone" not in json.dumps(lh), f"Bo'lim: {lh['total']} ta faol keys, har birida tushuntirish; ro'yxatda telefon yo'q")
ok(all(not re.search(r"jins|yosh|millat|viloyat|tug'il", " ".join(i["explain"]), re.I) for i in lh["items"]), "Tushuntirishlarda demografiya yo'q")
for who, cl in (("rektor", rek), ("o'quv prorektori", pro), ("o'qituvchi", teach), ("kafedra", kaf), ("buxgalteriya", bux)):
    ok(cl.get(K).status_code == 403, f"{who}: keyslar ro'yxati — 403")
mr = rek.get(K + "/metrics")
ok(mr.status_code == 200 and "total" in mr.json() and not re.search(r'"student"|"full_name"|"hemis', json.dumps(mr.json())), "Rektor: ko'rsatkichlar — jamlangan, talaba ismi yo'q")
ok(teach.get(K + "/metrics").status_code == 403 and bux.get(K + "/metrics").status_code == 403, "O'qituvchi / buxgalteriya — ko'rsatkichlar 403")
case = next(i for i in lh["items"] if i["status"] == "ochiq" and (not i["owner"] or i["owner"]["id"] not in (T1, T2)))
CID = case["id"]
ok(t1.get(f"{K}/{CID}").status_code == 403, "Tyutor begona keysni ochmaydi (403)")
ok(t1.post(f"{K}/{CID}/assign", json={"tutor_id": T1}).status_code == 403, "Tyutor biriktira olmaydi (403)")
a1 = head.post(f"{K}/{CID}/assign", json={"tutor_id": T1, "note": "Telefon orqali"})
ok(a1.status_code == 200 and q("SELECT owner_user FROM ok_cases WHERE id=?", (CID,))[0]["owner_user"] == T1, f"Bo'lim tyutorga biriktirdi ({a1.json().get('load')}/{a1.json().get('limit')})")
cv = t1.get(f"{K}/{CID}").json()
ok(cv["can_act"] and "phone" in cv["student"] and cv["explain"] and "demografik" in cv["note"], "Egasi (tyutor) keys kartasini ochadi: tushuntirish, telefon (qo'ng'iroq uchun)")
ok(any(i["id"] == CID for i in t1.get(K).json()["items"]) and t1.get(f"/api/ortda/student/{case['student']['id']}", params={"course": cv["course_rows"][0]["ref"]}).status_code == 200,
   "Tyutor ro'yxatida keys bor va talaba darslarini ko'radi (ko'lam keys orqali)")
ok(t1.post(f"{K}/{CID}/contact", json={"outcome": ""}).status_code == 400, "Bog'lanish — natijasiz 400")
c1 = t1.post(f"{K}/{CID}/contact", json={"outcome": "javob_bermadi", "note": "Ikki marta qo'ng'iroq"})
r1 = q("SELECT * FROM ok_cases WHERE id=?", (CID,))[0]
ok(c1.status_code == 200 and r1["status"] == "jarayonda" and r1["first_contact_at"] and r1["contacts"] == 1, "Bog'lanish qayd etildi → «jarayonda», birinchi bog'lanish vaqti")
ok(t2.post(f"{K}/{CID}/close", json={"outcome": "gaplashildi", "next_step": (clock.today() + dt.timedelta(days=7)).isoformat()}).status_code == 403, "Boshqa tyutor yopa olmaydi (403)")
nxt = (clock.today() + dt.timedelta(days=7)).isoformat()
ok(t1.post(f"{K}/{CID}/close", json={"outcome": "", "next_step": nxt}).status_code == 400, "Yopish — natija majburiy (400)")
ok(t1.post(f"{K}/{CID}/close", json={"outcome": "boshqa", "next_step": nxt}).status_code == 400, "«Boshqa» — izohsiz 400")
ok(t1.post(f"{K}/{CID}/close", json={"outcome": "gaplashildi"}).status_code == 400, "Keyingi qadam sanasisiz — 400")
ok(t1.post(f"{K}/{CID}/close", json={"outcome": "gaplashildi", "next_step": "2020-01-01"}).status_code == 400, "O'tgan keyingi qadam sanasi — 400")
cl = t1.post(f"{K}/{CID}/close", json={"outcome": "gaplashildi", "note": "Kasal bo'lgan, shu hafta yetib oladi", "next_step": nxt})
r1 = q("SELECT * FROM ok_cases WHERE id=?", (CID,))[0]
ok(cl.status_code == 200 and r1["status"] == "yopilgan" and r1["outcome"] == "gaplashildi" and r1["next_step"] == nxt and r1["closed_by"] == T1, "Yopildi: natija, izoh, keyingi qadam")
ok(t1.post(f"{K}/{CID}/close", json={"outcome": "gaplashildi", "next_step": nxt}).status_code == 400, "Yopilgan keysni qayta yopib bo'lmaydi (400)")
lg = [l["action"] for l in head.get(f"{K}/{CID}").json()["log"]]
ok(lg[:3] == ["yopildi", "bog'lanildi", "biriktirildi"], f"Keys tarixi: {lg[:4]}")
ok(q("SELECT COUNT(*) n FROM audit_log WHERE action LIKE 'keyslar:%' AND allowed=0")[0]["n"] >= 3, "Rad etilgan urinishlar audit jurnalida")
# avtomatik qayta ochish
SID = r1["student_id"]
head.post(K + "/sync")
ok(not q("SELECT 1 FROM ok_cases WHERE student_id=? AND status IN ('ochiq','jarayonda')", (SID,)), "Yopilganiga 14 kun bo'lmagan — talaba bayroqli bo'lsa ham yangi keys ochilmaydi")
x("UPDATE ok_cases SET closed_at=? WHERE id=?", ((dt.datetime.fromisoformat(r1["closed_at"]) - dt.timedelta(days=15)).isoformat(timespec="seconds"), CID))
sy2 = head.post(K + "/sync").json()
ro = q("SELECT * FROM ok_cases WHERE student_id=? AND status='ochiq' ORDER BY id DESC", (SID,))
ok(sy2["reopened"] >= 1 and ro and ro[0]["reopened_from"] == CID and ro[0]["src"] == "qayta", f"15 kundan keyin hali bayroqli — keys avtomatik qayta ochildi (#{ro[0]['id'] if ro else '?'} ← #{CID})")
ok(head.get(f"{K}/{ro[0]['id']}").json()["src_label"] == "Qayta ochildi" if ro else False, "Kartada «Qayta ochildi»")
# bayroq yo'qolsa — tizim yopadi (bog'lanilmagan bo'lsa), bog'lanilgan keys ochiq qoladi
flagged = set(KS.flagged())
calm = [r["id"] for r in q("""SELECT s.id FROM students s JOIN groups_ g ON g.id=s.group_id WHERE s.study_form='masofaviy' AND s.status='faol' AND g.form='masofaviy'
                              ORDER BY s.id LIMIT 400""") if r["id"] not in flagged][:2]
now_s = clock.now().replace(microsecond=0).isoformat(timespec="seconds")
ida = x("INSERT INTO ok_cases(student_id,status,opened_at,sla_due,src,reasons,courses) VALUES(?,?,?,?,?,?,?)", (calm[0], "ochiq", now_s, now_s, "qolda", "[]", "[]"))
idb = x("INSERT INTO ok_cases(student_id,status,opened_at,sla_due,first_contact_at,contacts,src,reasons,courses) VALUES(?,?,?,?,?,?,?,?,?)",
        (calm[1], "jarayonda", now_s, now_s, now_s, 1, "qolda", "[]", "[]"))
head.post(K + "/sync")
ra, rb = q("SELECT * FROM ok_cases WHERE id=?", (ida,))[0], q("SELECT * FROM ok_cases WHERE id=?", (idb,))[0]
ok(ra["status"] == "yopilgan" and ra["outcome"] == KS.AUTO and rb["status"] == "jarayonda", "Bayroq yo'qoldi: bog'lanilmagan keys — tizim yopdi («avto»), bog'lanilgani — ochiq qoladi")
x("UPDATE ok_cases SET status='yopilgan', closed_at=?, outcome='gaplashildi', next_step=? WHERE id=?", (now_s, nxt, idb))
# yuklama chegarasi
ok(staff.post("/api/ortda/keys-qoidalar", json={"caseload_max": 5}).status_code == 403 and head.post("/api/ortda/keys-qoidalar", json={"caseload_max": 2}).status_code == 400,
   "Qoidalar: xodim — 403, oraliqdan tashqari — 400")
ok(head.post("/api/ortda/keys-qoidalar", json={"caseload_max": 5}).status_code == 200, "Bo'lim boshlig'i: yuklama chegarasi 5")
pool_c = [i["id"] for i in head.get(K, params={"limit": 200}).json()["items"] if not i["owner"] or i["owner"]["id"] != T2]
load = lambda u: q("SELECT COUNT(*) n FROM ok_cases WHERE owner_user=? AND status IN ('ochiq','jarayonda')", (u,))[0]["n"]
it_ = iter(pool_c)
while load(T2) < 5: head.post(f"{K}/{next(it_)}/assign", json={"tutor_id": T2, "force": True})
cid6 = next(it_)
w6 = head.post(f"{K}/{cid6}/assign", json={"tutor_id": T2})
d6 = w6.json().get("detail") or {}
ok(w6.status_code == 409 and d6.get("overload") and d6.get("load") == 5 and d6.get("limit") == 5 and d6.get("suggest") and d6["suggest"]["id"] != T2 and d6["suggest"]["load"] < 5,
   f"6-keys: ogohlantirish (409) va taqsimlash tavsiyasi — {d6.get('suggest', {}).get('name')} ({d6.get('suggest', {}).get('load')} ta)")
ok(head.get(f"{K}/{cid6}/tyutorlar").json()["suggest"] == d6["suggest"]["id"], "Nomzodlar ro'yxatidagi tavsiya bilan bir xil")
f6 = head.post(f"{K}/{cid6}/assign", json={"tutor_id": T2, "force": True})
ok(f6.status_code == 200 and f6.json()["over"] and load(T2) == 6 and q("SELECT 1 FROM audit_log WHERE action='keyslar: biriktirildi' AND detail LIKE ?", (f"keys #{cid6}%chegaradan%",)),
   "Ataylab (force) — biriktirildi, audit jurnalida «chegaradan oshirildi»")
# Nazorat markazi: yuklama va SLA istisnolari
x("UPDATE ok_cases SET sla_due=?, first_contact_at=NULL WHERE id=?", ((clock.now() - dt.timedelta(days=1)).replace(microsecond=0).isoformat(timespec="seconds"), cid6))
from app import nazorat as NZ
NZ._con = _con
items = {i["key"]: i for i in NZ.detect(_con, clock.now().replace(microsecond=0))}
ok(f"keys_load:{T2}" in items and items[f"keys_load:{T2}"]["area"] == "talabalar" and "yuklamasi oshgan" in items[f"keys_load:{T2}"]["title"],
   "Nazorat: tyutor yuklamasi oshgani — istisno (egasi — Masofaviy ta'lim bo'limi)")
ok(f"keys_sla:{T2}" in items and items[f"keys_sla:{T2}"]["owner"] == T2 and "SLA" in items[f"keys_sla:{T2}"]["title"], "Nazorat: SLA ichida bog'lanilmagan keyslar — tyutor bo'yicha istisno")
nk = rek.get("/api/nazorat/keyslar")
ok(nk.status_code == 200 and nk.json()["enabled"] and "sla_pct" in nk.json()["total"] and not re.search(r'"student"', json.dumps(nk.json())), "Rektor: /api/nazorat/keyslar — jamlangan natija ko'rsatkichlari")
ok(teach.get("/api/nazorat/keyslar").status_code == 403 and S(uid("prorektor_ilmiy")).get("/api/nazorat/keyslar").status_code == 403, "O'qituvchi va ilmiy prorektor — 403")
head.post("/api/ortda/keys-qoidalar", json={"caseload_max": 50})
# ko'rsatkichlar serverda — sof funksiya bilan bir xil
md = head.get(K + "/metrics").json()
rows_ = q("SELECT * FROM ok_cases WHERE opened_at>=?", (md["since"],))
for r in rows_:
    r["reengaged_at"] = q("SELECT MIN(ts) t FROM lrs_statements WHERE student_id=? AND voided=0 AND ts>?", (r["student_id"], r["first_contact_at"]))[0]["t"] if r["first_contact_at"] else None
loc = KS.metrics(rows_, P_(md["now"]), md["policy"]["reengage_days"])
ok({k: loc[k] for k in ("opened", "closed", "sla_pct", "reeng_pct", "median_contact_h", "overdue")} == {k: md["total"][k] for k in ("opened", "closed", "sla_pct", "reeng_pct", "median_contact_h", "overdue")},
   f"Server ko'rsatkichlari = sof hisob (SLA {md['total']['sla_pct']} %, qayta faollashish {md['total']['reeng_pct']} %, median {md['total']['median_contact_h']} soat)")
mt = t1.get(K + "/metrics").json()
ok(all(t["id"] == T1 for t in mt["tutors"]), "Tyutor — faqat o'z ko'rsatkichlari")

# =============================================================================================
print("== 4. Haftalik taqvim → kutilgan progress; kabinet «Bu hafta»")
c121 = q("SELECT * FROM dl_courses WHERE subject='Iqtisodiyot nazariyasi' AND direction='Iqtisodiyot' AND course=1")[0]
CR = f"dl:{c121['id']}"
studs = [r["id"] for r in q("""SELECT s.id FROM students s JOIN groups_ g ON g.id=s.group_id WHERE s.study_form='masofaviy' AND s.status='faol'
                               AND g.form='masofaviy' AND g.direction=? AND g.course=? ORDER BY s.id""", (c121["direction"], c121["course"]))]
SX = studs[2]
G = q("SELECT group_id FROM students WHERE id=?", (SX,))[0]["group_id"]
TQ = "/api/ortda/taqvim"
tv = head.get(TQ, params={"course": CR, "group": G}).json()
ok(tv["src"] in ("reja", "kurs") and len(tv["items"]) == 45 and all(i["due"] >= i["release"] for i in tv["items"]) and tv["items"][0]["due_label"].endswith("(yakshanba)"),
   f"Kurs taqvimi: 45 dars, muddat — yakshanba ({tv['items'][0]['due_label']})")
ok(teach.get(TQ, params={"course": CR}).status_code in (200, 403) and bux.get(TQ, params={"course": CR}).status_code == 403 and t1.post(TQ, json={"course": CR, "start": "2026-09-01"}).status_code == 403,
   "Taqvim: buxgalteriya — 403, tyutor o'zgartira olmaydi (403)")
row0 = next(r for r in head.get("/api/ortda/list", params={"course": CR, "only_risk": "false", "limit": 500}).json()["items"] if r["student_id"] == SX)
pol = head.get("/api/ortda/meta").json()["policy"]
start2 = (dt.date.fromisoformat(tv["start"]) + dt.timedelta(weeks=3)).isoformat()
ok(head.post(TQ, json={"course": CR, "group_id": G, "start": start2, "weeks": 15}).status_code == 200, f"Guruh taqvimi: boshlanish 3 hafta keyin ({start2})")
row1 = next(r for r in head.get("/api/ortda/list", params={"course": CR, "only_risk": "false", "limit": 500}).json()["items"] if r["student_id"] == SX)
exp1 = LA.expected_by_due(LA.schedule(45, dt.date.fromisoformat(start2), 15), clock.today(), pol["grace_weeks"])
ok(row1["expected"] == exp1 and row1["expected"] < row0["expected"], f"Kutilgan progress guruh taqvimi bo'yicha: {row0['expected']} → {row1['expected']} (hisob: {exp1})")
other = next((r for r in head.get("/api/ortda/list", params={"course": CR, "only_risk": "false", "limit": 500}).json()["items"] if r["group_id"] != G), None)
ok(other is None or other["expected"] == row0["expected"], "Boshqa guruhlar — o'zgarmagan")
ok(head.post(TQ, json={"course": CR, "group_id": G, "dues": {"L1": "2020-01-01"}}).status_code == 400 and head.post(TQ, json={"course": CR, "group_id": G, "dues": {"ZZ9": "2026-12-01"}}).status_code == 400,
   "Muddat chiqarilishdan oldin yoki noma'lum dars — 400")
ok(head.post(TQ, json={"course": CR, "group_id": G, "reset": True}).status_code == 200 and
   next(r for r in head.get("/api/ortda/list", params={"course": CR, "only_risk": "false", "limit": 500}).json()["items"] if r["student_id"] == SX)["expected"] == row0["expected"],
   "Guruh taqvimi o'chirildi — standartga qaytdi")
# «Bu hafta»: shu haftaning darslari ochiladigan bo'lsin (tasdiqlangan paket nusxasi — test oxirida o'chiriladi)
cur = [i for i in tv["items"] if i["release"] <= clock.today().isoformat() <= i["due"]]
src_pkg = q("SELECT * FROM pk_packages WHERE file IS NOT NULL AND file!='' AND mode!='none' ORDER BY id LIMIT 1")
PKG_IDS = []
if src_pkg and cur:
    rowp = src_pkg[0]; colsp = [k for k in rowp if k != "id"]
    for i in cur[:3]:
        r = dict(rowp, course_id=c121["id"], topic_no=L.code_to_key(i["code"]), status="tasdiqlandi", version=950 + len(PKG_IDS))
        PKG_IDS.append(x(f"INSERT INTO pk_packages({','.join(colsp)}) VALUES({','.join('?' * len(colsp))})", [r[k] for k in colsp]))
cx = ST(SX)
dd = cx.get("/api/talaba/darslar").json()
wk = dd["this_week"]
ok(isinstance(wk, list) and all(w["due_label"] and (w["late"] or w["due"] >= clock.today().isoformat()) for w in wk), f"«Bu hafta»: {len(wk)} ta dars, har birida muddat")
if PKG_IDS:
    ok(any(w["code"] == cur[0]["code"] and w["can_open"] and not w["late"] for w in wk), f"Joriy hafta darsi ({cur[0]['code']}, muddat {cur[0]['due_label']}) «Bu hafta»da va ochiladi")
cc = next(c for c in dd["courses"] if c["ref"] == CR)
ok(all(l.get("due") for l in cc["lessons"] if l["cal"] is not None) and cc["lag"] == max(0, cc["expected"] - cc["done"]), "Kabinet darslarida muddat; ortda = kutilgan − bajarilgan")
ok(not re.search(r'"student_id"|"hemis', json.dumps(wk)), "«Bu hafta» — boshqa talaba ma'lumoti yo'q")

# =============================================================================================
print("== 5. To'siq nuqtalari, tajriba, cheklovlar")
TA = "/api/ortda/tajriba"
ok(rek.get(TA).status_code == 200 and teach.get(TA).status_code == 403 and t1.get(TA).status_code == 403, "Ko'rish: bo'lim va rahbariyat; o'qituvchi, tyutor — 403")
ok(staff.post(TA + "/mode", json={"key": "t_inactive7", "mode": "tajriba"}).status_code == 403 and head.post(TA + "/mode", json={"key": "nima", "mode": "all"}).status_code == 400,
   "Rejim: faqat bo'lim boshlig'i; noma'lum aralashuv — 400")
v0 = head.get(TA).json()
ok(all(i["mode"] == "off" for i in v0["items"]) and len(v0["items"]) == 3, "Standart: barcha avtomatik eslatmalar o'chiq (ommaviy yuborish yo'q)")
ok(TJ.run_due()["eligible"] == 0, "O'chiq rejimda hech narsa yozilmaydi va yuborilmaydi")
ok(head.post(TA + "/mode", json={"key": "t_inactive7", "mode": "tajriba"}).status_code == 200, "t_inactive7 → tajriba (guruhlarning yarmi)")
salt = q("SELECT salt FROM tj_experiments WHERE key='t_inactive7'")[0]["salt"]
NOWT = clock.now().replace(microsecond=0)
sent_to = []
r5 = TJ.run_due(now=NOWT, sender=lambda chat, text: sent_to.append(chat))
ev = q("SELECT * FROM tj_events WHERE key='t_inactive7' AND salt=?", (salt,))
ok(r5["eligible"] == len(ev) > 0 and all(e["arm"] == TJ.arm("t_inactive7", salt, e["group_id"]) for e in ev), f"Hodisalar: {len(ev)} ta, qo'l — guruh xeshi bo'yicha ({r5})")
ok(all(not e["sent"] and not e["notice_id"] and e["status"] == "nazorat" for e in ev if e["arm"] == "nazorat"), "Nazorat qo'li: yozildi, yuborilmadi")
ok(all((e["sent"] and e["notice_id"]) or e["status"].startswith("cheklov") for e in ev if e["arm"] == "tajriba"), "Tajriba qo'li: yuborildi (yoki cheklov sababi bilan)")
nts = [e["notice_id"] for e in ev if e["notice_id"]]
if nts:
    nt = q("SELECT * FROM ops_notices WHERE id=?", (nts[0],))[0]
    ok(nt["channel"] == "telegram" and "kundan beri" in nt["text"] and "/xapi/l/" not in nt["text"] and q("SELECT 1 FROM notice_delivery WHERE notice_id=?", (nts[0],)),
       "Xabar: Telegram, matnda faollik va kabinet yo'riqnomasi (launch havolasi yo'q), yetkazish jurnalda")
r5b = TJ.run_due(now=NOWT + dt.timedelta(minutes=5))
ok(r5b["eligible"] == 0 and r5b["dup"] >= len(ev), "Qayta ishga tushirish — takroriy hodisa yo'q (dedupe)")
# cheklovlar: oraliq va haftalik (sintetik yuborilgan hodisalar), kunlik
ok(head.post(TA + "/mode", json={"key": "t_login", "mode": "all"}).status_code == 200, "t_login → hammaga")
lc = [c for c in TJ.candidates(NOWT) if c["key"] == "t_login"]
XS, YS = lc[0]["student_id"], lc[1]["student_id"]
iso = lambda t: t.replace(microsecond=0).isoformat(timespec="seconds")
x("INSERT INTO tj_events(ts,key,salt,student_id,group_id,arm,sent,status,dedupe) VALUES(?,?,?,?,?,?,?,?,?)", (iso(NOWT - dt.timedelta(hours=3)), "test", "s", XS, 0, "hammasi", 1, "yuborildi", f"test:{uuid.uuid4()}"))
for h in (60, 100):
    x("INSERT INTO tj_events(ts,key,salt,student_id,group_id,arm,sent,status,dedupe) VALUES(?,?,?,?,?,?,?,?,?)", (iso(NOWT - dt.timedelta(hours=h)), "test", "s", YS, 0, "hammasi", 1, "yuborildi", f"test:{uuid.uuid4()}"))
day0 = iso(dt.datetime.combine(NOWT.date(), dt.time()))
n_today = q("SELECT COUNT(*) n FROM tj_events WHERE sent=1 AND ts>=?", (day0,))[0]["n"]
ok(head.post(TA + "/limits", json={"daily_max": n_today + 3}).status_code == 200 and staff.post(TA + "/limits", json={"daily_max": 9}).status_code == 403, f"Kunlik chegara: {n_today + 3}")
r6 = TJ.run_due(now=NOWT)
st_ = {r["student_id"]: r["status"] for r in q("SELECT student_id, status FROM tj_events WHERE key='t_login'")}
ok(st_.get(XS) == "cheklov: oraliq" and st_.get(YS) == "cheklov: haftalik", f"Cheklov: 48 soat oralig'i va 7 kunda 2 ta ({st_.get(XS)}, {st_.get(YS)})")
ok(r6["sent"] == 3 and r6["limited"] == r6["eligible"] - 3 and q("SELECT COUNT(*) n FROM tj_events WHERE sent=1 AND ts>=?", (day0,))[0]["n"] == n_today + 3,
   f"Kunlik chegara: aynan 3 ta yuborildi, qolgan {r6['limited']} ta — cheklov (jurnalda)")
smsn = q("SELECT channel FROM ops_notices WHERE id IN (SELECT notice_id FROM tj_events WHERE key='t_login' AND sent=1)")
ok(smsn and all(n["channel"] in ("sms", "telegram") for n in smsn), "Birinchi kirish yo'q — SMS navbati (telefon bo'lsa; Telegram hali ulanmagan)")
# natija taqqoslash: o'tgan hodisalar (sintetik, 10 kun oldin) — oynasi tugagan
studs_g = q("""SELECT s.id, s.group_id FROM students s JOIN groups_ g ON g.id=s.group_id WHERE s.study_form='masofaviy' AND s.status='faol' AND g.form='masofaviy'
               AND s.id IN (SELECT DISTINCT student_id FROM lrs_progress) ORDER BY s.id LIMIT 60""")
t10 = iso(NOWT - dt.timedelta(days=10))
for r in studs_g:
    x("INSERT OR IGNORE INTO tj_events(ts,key,salt,student_id,group_id,arm,sent,status,dedupe) VALUES(?,?,?,?,?,?,?,?,?)",
      (t10, "t_inactive7", salt, r["id"], r["group_id"], TJ.arm("t_inactive7", salt, r["group_id"]), 0, "nazorat", f"test10:{r['id']}"))
oc = TJ.outcomes("t_inactive7")
one_ = studs_g[0]
y1 = bool(q("SELECT 1 FROM lrs_statements WHERE student_id=? AND voided=0 AND ts>? AND ts<=?", (one_["id"], t10, iso(NOWT - dt.timedelta(days=3)))))
ok(oc["arms"]["tajriba"]["n"] + oc["arms"]["nazorat"]["n"] >= 1 and oc["pending"] >= 1 and any("tugamagan" in c for c in oc["caveats"]),
   f"Taqqoslash: {oc['arms']['tajriba']['n']} / {oc['arms']['nazorat']['n']} talaba, {oc['pending']} ta oynasi tugamagan — ogohlantirish bilan")
vv = head.get(TA).json()
it7 = next(i for i in vv["items"] if i["key"] == "t_inactive7")
ok(it7["mode"] == "tajriba" and it7["groups"]["tajriba"] + it7["groups"]["nazorat"] == q("SELECT COUNT(*) n FROM groups_ WHERE form='masofaviy'")[0]["n"] and it7["result"]["caveats"],
   f"Ekran: rejim, guruhlar qo'llarda ({it7['groups']}), natija va ogohlantirishlar")
ok(vv["log"] and not rek.get(TA).json()["log"], "Jurnal — faqat bo'limga (rahbariyat — jamlangan)")

# =============================================================================================
print("== 6. Dars oxiri testi (Test bankdan)")
tb = q("""SELECT course_id, topic_no, COUNT(*) n FROM tb_questions WHERE status='tasdiqlandi' AND deleted=0 GROUP BY 1, 2 ORDER BY n DESC""")
DLC = tb[0]["course_id"]
appr = {(r["topic_no"]): r["n"] for r in tb if r["course_id"] == DLC}
tps = sorted(appr, key=lambda t: -appr[t])[:2]
for i in range(4):          # qoralama savollar — ishlatilmasligi kerak
    x("INSERT INTO tb_questions(course_id,topic_no,qtype,stem,options,correct,status,deleted,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
      (DLC, 99, "single", f"Qoralama savol {i}", json.dumps(["a", "b", "c"]), json.dumps([0]), "qoralama", 0, now_s))
mk = head.post("/api/kurs/courses", json={"title": "Dars oxiri testi sinovi", "dl_course_id": DLC}).json()
KC = mk["id"]
lid1 = q("SELECT id FROM ku_lessons WHERE course_id=? AND deleted=0", (KC,))[0]["id"]
for t in range(2, max(tps) + 1): head.post(f"/api/kurs/courses/{KC}/lessons", json={"type": "blocks", "title": f"{t}-dars"})
ok(teach.post(f"/api/kurs/courses/{KC}/dars-testlari").status_code == 403 and rek.post(f"/api/kurs/courses/{KC}/dars-testlari").status_code == 403,
   "Begona o'qituvchi va rektor — 403")
aq = head.post(f"/api/kurs/courses/{KC}/dars-testlari")
aj = aq.json()
ok(aq.status_code == 200 and aj["added"], f"Qo'shildi: {len(aj.get('added', []))} ta test, o'tkazildi: {len(aj.get('skipped', []))} ({[s['reason'][:40] for s in aj.get('skipped', [])][:2]})")
qls = q("SELECT l.id, l.pos, l.type, l.settings FROM ku_lessons l WHERE l.course_id=? AND l.deleted=0 ORDER BY l.pos", (KC,))
aqs = q("SELECT * FROM ku_autoquiz WHERE ku_course_id=?", (KC,))
used = [i for a in aqs for i in json.loads(a["tb_ids"])]
appr_ids = {r["id"] for r in q("SELECT id FROM tb_questions WHERE course_id=? AND status='tasdiqlandi' AND deleted=0", (DLC,))}
ok(len(used) == len(set(used)) and set(used) <= appr_ids and all(3 <= len(json.loads(a["tb_ids"])) <= 5 for a in aqs),
   f"Savollar: takrorsiz ({len(used)} ta), faqat tasdiqlangan, har testda 3–5")
ok(all(q("SELECT topic_no FROM tb_questions WHERE id=?", (i,))[0]["topic_no"] == a["topic_no"] for a in aqs for i in json.loads(a["tb_ids"])), "Har test — o'z darsining mavzusidan")
pos = {r["id"]: r["pos"] for r in qls}
ok(all(pos[a["quiz_lesson_id"]] == pos[a["lesson_id"]] + 1 for a in aqs), "Test darsi — o'z darsidan keyin")
st_ = json.loads(next(r for r in qls if r["id"] == aqs[0]["quiz_lesson_id"])["settings"])
nb = q("SELECT COUNT(*) n FROM ku_blocks WHERE lesson_id=? AND type='question'", (aqs[0]["quiz_lesson_id"],))[0]["n"]
ok(st_["attempts"] == 0 and st_["shuffle"] and st_["randomize"] and st_["pass_pct"] == 60 and nb == len(json.loads(aqs[0]["tb_ids"])),
   "Past xavfli: urinishlar cheklanmagan, aralashtirilgan, o'tish 60 %; bloklar — savollar")
ok(head.post(f"/api/kurs/courses/{KC}/dars-testlari").json()["added"] == [], "Qayta bosish — yangi test qo'shilmaydi (idempotent)")
mk2 = head.post("/api/kurs/courses", json={"title": "Dars oxiri testi sinovi 2", "dl_course_id": DLC}).json()
aj2 = head.post(f"/api/kurs/courses/{mk2['id']}/dars-testlari").json()
used2 = [i for a in q("SELECT tb_ids FROM ku_autoquiz WHERE ku_course_id=?", (mk2["id"],)) for i in json.loads(a["tb_ids"])]
ok(not set(used2) & set(used), f"Shu fanning boshqa kursida ham savollar takrorlanmaydi ({len(used2)} ta yangi yoki o'tkazildi: {[s['reason'][:30] for s in aj2['skipped']][:1]})")
ok(q("SELECT kind FROM ku_versions WHERE course_id=? ORDER BY id DESC LIMIT 1", (KC,))[0]["kind"] == "avto", "O'zgarishdan oldin versiya saqlandi")
nl = q("SELECT id FROM dl_courses WHERE id NOT IN (SELECT DISTINCT course_id FROM tb_questions WHERE status='tasdiqlandi') ORDER BY id LIMIT 1")[0]["id"]
mk3 = head.post("/api/kurs/courses", json={"title": "Savolsiz fan", "dl_course_id": nl}).json()
aj3 = head.post(f"/api/kurs/courses/{mk3['id']}/dars-testlari").json()
ok(aj3["added"] == [] and aj3["skipped"] and "yetarli emas" in aj3["skipped"][0]["reason"], "Tasdiqlangan savoli yo'q fan — test qo'shilmaydi, sabab ko'rsatiladi")
mk4 = head.post("/api/kurs/courses", json={"title": "Fansiz kurs"}).json()
ok(head.post(f"/api/kurs/courses/{mk4['id']}/dars-testlari").status_code == 400, "Fanga bog'lanmagan kurs — 400 (tushuntirish bilan)")
ds = head.post(f"/api/dars/subjects/{DLC}/dars-testlari")
ok(ds.status_code in (200, 400) and teach.post(f"/api/dars/subjects/{DLC}/dars-testlari").status_code in (403, 400), f"Dars tayyorlash: fan bo'yicha amal ({ds.status_code})")
for k_ in (KC, mk2["id"], mk3["id"], mk4["id"]): x("UPDATE ku_courses SET deleted=1 WHERE id=?", (k_,))
x("DELETE FROM tb_questions WHERE course_id=? AND topic_no=99 AND status='qoralama'", (DLC,))

# =============================================================================================
print("== 7. «ISFT Ready» kirish kursi")
RD = "/api/kurs/isft-ready"
ok(teach.post(RD, json={}).status_code == 403 and rek.post(RD, json={}).status_code == 403, "Yaratish: o'qituvchi, rektor — 403")
cr = head.post(RD, json={})
RID = cr.json().get("id")
ok(cr.status_code == 200 and cr.json()["created"] and head.post(RD, json={}).json()["id"] == RID, f"Yaratildi (#{RID}); qayta bosish — o'sha kurs")
ls = q("SELECT id, type, title FROM ku_lessons WHERE course_id=? AND deleted=0 ORDER BY pos", (RID,))
bl = q("SELECT b.type, b.data FROM ku_blocks b JOIN ku_lessons l ON l.id=b.lesson_id WHERE l.course_id=?", (RID,))
txt = " ".join(json.loads(b["data"]).get("html", "") + json.loads(b["data"]).get("heading", "") + " ".join(json.loads(b["data"]).get("items", []) or []) for b in bl
               if b["type"] in ("heading_paragraph", "list", "paragraph"))
ok(len(ls) == 7 and ls[-1]["type"] == "quiz" and sum(1 for b in bl if b["type"] == "knowledge") == 6 and sum(1 for b in bl if b["type"] == "question") == 8,
   "Mazmun: 6 bo'lim (har birida bilimni tekshirish) + yakuniy tekshiruv (8 savol)")
ok(all(k in txt for k in ("Mening darslarim", "yakshanba", "Tyutor", "Akademik halollik", "manbani ko'rsating", "AI", "yuzma-yuz")) and not re.search(r"VMQ|qaror|nizom|qonun", txt, re.I),
   "Mavzular: platforma, muddatlar, yordam, halollik, AI, odatlar; qonun da'volari yo'q (faqat yakuniy imtihon — yuzma-yuz)")
ri = head.get(RD).json()
ok(ri["exists"] and not ri["published"], "Holat: qoralama (hali e'lon qilinmagan) — kabinetda va «Ortda qolganlar»da yo'q")
ap = head.post(f"/api/kurs/courses/{RID}/action", json={"action": "approve"})
exr = head.post(f"/api/kurs/courses/{RID}/export", json={"mode": "xapi"})
ok(ap.status_code == 200 and exr.status_code == 200, f"Tasdiqlandi va xAPI eksport ({ap.status_code}, {exr.status_code} {exr.text[:120] if exr.status_code != 200 else ''})")
REF = f"ku:{RID}"
mm = head.get("/api/ortda/meta").json()
ok(any(c["ref"] == REF for c in mm["courses"]), "«Ortda qolganlar»: kirish kursi kuzatiladi")
S1 = q("""SELECT s.id FROM students s JOIN groups_ g ON g.id=s.group_id WHERE s.study_form='masofaviy' AND s.status='faol' AND g.form='masofaviy' AND g.course=1
          AND g.direction=? ORDER BY s.id""", (c121["direction"],))[3]["id"]
cs1 = ST(S1)
rd = cs1.get("/api/talaba/darslar").json()["ready"]
ok(rd and rd["status"] == "yangi" and rd["can_open"] and not rd["badge"], f"Kabinet: kirish kursi kartasi (muddat {rd and rd['deadline']})")
lu = cs1.post("/api/talaba/darslar/launch", json={"course_ref": REF, "lesson": ""})
ok(lu.status_code == 200 and lu.json()["url"].startswith("/xapi/l/"), "Kabinetdan ochish — launch havolasi")
ok(cs1.post("/api/talaba/darslar/launch", json={"course_ref": f"ku:{RID + 999}", "lesson": ""}).status_code == 404, "Boshqa kurs muharriri kursini ochib bo'lmaydi (404)")
# muddat hali o'tmagan (kurs hozir e'lon qilindi → +7 kun) — bayroq yo'q
lr = head.get("/api/ortda/list", params={"course": REF, "limit": 500}).json()
ok(not any(any(r_["code"] == "ready" for r_ in i["reasons"]) for i in lr["items"]), "E'londan 7 kun ichida — «boshlamagan» bayrog'i yo'q")
# muddat o'tgan holat: kurs semestr boshidan oldin e'lon qilingan bo'lsin
x("UPDATE ku_courses SET approved_at='2026-08-20T10:00:00' WHERE id=?", (RID,))
ORT._CACHE.clear()
N1 = q("SELECT full_name FROM students WHERE id=?", (S1,))[0]["full_name"]
lr2 = head.get("/api/ortda/list", params={"course": REF, "limit": 200}).json()
fl = [i for i in lr2["items"] if any(r_["code"] == "ready" for r_ in i["reasons"])]
n1 = q("""SELECT COUNT(*) n FROM students s JOIN groups_ g ON g.id=s.group_id WHERE s.study_form='masofaviy' AND s.status='faol' AND g.form='masofaviy' AND g.course=1""")[0]["n"]
me2 = head.get("/api/ortda/list", params={"course": REF, "q": N1, "limit": 50}).json()["items"]
ok(fl and lr2["total"] == n1 and all(i["level"] == "orta" for i in fl) and any("Boshlamagan" in r_["label"] for i in fl for r_ in i["reasons"])
   and any(i["student_id"] == S1 for i in me2),
   f"1-hafta o'tdi, kurs tugatilmagan — «boshlamagan» erta bayrog'i (barcha {lr2['total']} ta 1-kurs masofaviy talabasi)")
# talaba yakunlaydi → bayroq yo'qoladi, nishon
tok = L.make_auth(S1, REF, "")
done_st = {"id": str(uuid.uuid4()), "actor": {"objectType": "Agent", "account": {"homePage": "https://isft.uz", "name": tok["learner"]}},
           "verb": {"id": "http://adlnet.gov/expapi/verbs/completed", "display": {"en-US": "completed"}},
           "object": {"objectType": "Activity", "id": f"https://isft.uz/xapi/kurs/{RID}"}, "result": {"completion": True},
           "timestamp": dt.datetime.now(dt.timezone.utc).isoformat(), "context": {"registration": tok["registration"]}}
ps = httpx.post(B + "/xapi/statements", json=done_st, headers={"Authorization": tok["auth"], "X-Experience-API-Version": "1.0.3"})
ok(ps.status_code == 200, f"Talaba kursni yakunladi (xAPI completed) ({ps.status_code})")
lr3 = head.get("/api/ortda/list", params={"course": REF, "q": N1, "limit": 50, "only_risk": "false"}).json()
me3 = next((i for i in lr3["items"] if i["student_id"] == S1), None)
rd2 = cs1.get("/api/talaba/darslar").json()["ready"]
ok(me3 and not me3["reasons"] and rd2["badge"] and rd2["status"] == "tugatildi", "Yakunlagandan keyin: bayroq yo'q, kabinetda «ISFT Ready» nishoni")
ok(rek.get(RD).json().get("completed", 0) >= 1, "Rahbariyat: nechta talaba tugatgani (jamlangan son)")
x("UPDATE ku_courses SET approved_at=? WHERE id=?", (now_s, RID))
ORT._CACHE.clear()

# =============================================================================================
print("== 8. Brauzer")
pwj, chrome, node = os.environ.get("PW"), os.environ.get("CHROME"), shutil.which("node")
if node: ok(subprocess.run([node, "--check", str(ROOT / "static" / "keyslar.js")], capture_output=True).returncode == 0 and
            subprocess.run([node, "--check", str(ROOT / "tools" / "keyslar_check.js")], capture_output=True).returncode == 0, "node --check static/keyslar.js, tools/keyslar_check.js")
if pwj and chrome and node:
    out = os.environ.get("KS_OUT") or "/private/tmp/claude-501/isft-keys/shots"
    env = dict(os.environ, ISFT_TEST_URL=B, KS_OUT=out, ADMIN_UID=str(uid("masofaviy")), REK_UID=str(uid("rektor")), ADMIN_PW=PW,
               TD_HEMIS=q("SELECT hemis_id FROM students WHERE id=?", (SX,))[0]["hemis_id"], TD_PASS=NEWPW)
    rr = subprocess.run([node, str(ROOT / "tools" / "keyslar_check.js")], cwd=ROOT, env=env, capture_output=True, text=True, timeout=600)
    for ln in (rr.stdout + rr.stderr).splitlines():
        s = ln.strip()
        if s.startswith("✓"): ok(True, "[brauzer] " + s[1:].strip())
        elif s.startswith("✗"): ok(False, "[brauzer] " + s[1:].strip())
    ok(rr.returncode == 0, f"tools/keyslar_check.js chiqish kodi 0 ({rr.returncode})" + ("" if rr.returncode == 0 else ":\n" + "\n".join((rr.stdout + rr.stderr).splitlines()[-15:])))
    print("    skrinshotlar:", out)
else:
    print("  – PW/CHROME berilmagan — brauzer tekshiruvi o'tkazildi")

# =============================================================================================
print("== 9. Tozalash")
for k_ in TJ.TRIGGERS: head.post(TA + "/mode", json={"key": k_, "mode": "off"})
head.post(TA + "/limits", json={"daily_max": 500})
nids = [r["notice_id"] for r in q("SELECT notice_id FROM tj_events WHERE notice_id IS NOT NULL")]
if nids:
    x(f"DELETE FROM notice_delivery WHERE notice_id IN ({','.join(map(str, nids))})"); x(f"DELETE FROM ops_notices WHERE id IN ({','.join(map(str, nids))})")
for pid in PKG_IDS: x("DELETE FROM pk_packages WHERE id=?", (pid,))
x("UPDATE ku_courses SET deleted=1 WHERE id=?", (RID,))
ok(all(i["mode"] == "off" for i in head.get(TA).json()["items"]) and not RDY.info(_con), "Eslatmalar o'chirildi, test xabarlari va «ISFT Ready» sinov kursi olib tashlandi")

print()
if fails:
    print(f"XATO: {len(fails)} ta tekshiruv o'tmadi"); sys.exit(1)
print("Hammasi o'tdi")
