"""LRS (app/lrs.py) va «Ortda qolganlar» (app/ortda.py) — docs/lrs.md.

1. Analitika matematikasi (app/lrs_analytics.py — sof funksiyalar): dars jamlanmasi, savol qiyinligi / farqlash / eng ko'p xato javob,
   voronka, taqvim bo'yicha kutilgan progress, xavf qoidalari; faoliyat IRI tahlili, davomiylik, ball.
2. LRS: /xapi/about, versiya sarlavhasi, token (imzo, muddat, bekor qilish), ko'lam (A darsi tokeni B darsga / boshqa kursga / boshqa talaba
   nomidan yoza olmaydi, registration), statement tekshiruvi, idempotentlik (bir xil id — o'tkaziladi, boshqa mazmun — 409), atomik paket,
   bekor qilish (voided), hajm va so'rov cheklovlari, State API, GET filtrlari, CORS, hamkor (NEXTID) kirishi.
3. Ishga tushirish yo'li: havola → 302 (endpoint, auth, actor — taxallus, registration, activity_id) → paket fayllari (CSP, yo'l hujumi).
4. «Ortda qolganlar»: ruxsatlar (bo'lim, tyutor — o'z guruhlari + biriktirilganlar, o'qituvchi — o'z kurslari, kontaktsiz; kafedra va rahbariyat —
   jamlangan), qoidalar, amallar (tyutorga — Topshiriqlar/«Mening vazifalarim», eslatma — cheklov va jurnal, «bog'lanildi»), chegaralar,
   savollar tahlili (Kurs muharriri blokiga havola).
5. Uchidan-uchigacha (PW va CHROME berilganda): eksport → launch havolasi → brauzerda savolga javob → statementlar bazada → ekran yangilanadi
   (tools/lrs_e2e_check.js, skrinshotlar — $OUT yoki vaqtinchalik katalog).

Ishga tushirish: python tests/run_all.py --only lrs. DIQQAT: bazani o'zgartiradi (statementlar, topshiriqlar, xabarlar navbati).
"""
import base64, datetime as dt, json, os, re, shutil, sqlite3, subprocess, sys, tempfile, time, uuid
from pathlib import Path
from urllib.parse import urlsplit, parse_qs
import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
B = os.environ.get("ISFT_TEST_URL", "http://127.0.0.1:8000")
DBP = Path(os.environ.get("ISFT_CORE_DB") or ROOT / "data" / "jarvis.db")
PW = re.search(r'DEMO_PASSWORD = os.getenv\("ISFT_CORE_DEMO_PASSWORD", "([^"]+)"\)', (ROOT / "app" / "rbac.py").read_text()).group(1)
fails = []
def ok(cond, msg):
    print(("  ✓ " if cond else "  ✗ ") + msg)
    if not cond: fails.append(msg)
def q(sql, a=()):
    con = sqlite3.connect(DBP, timeout=30); con.row_factory = sqlite3.Row
    try: return [dict(r) for r in con.execute(sql, a).fetchall()]
    finally: con.close()
def uid(role):
    r = q("SELECT id FROM users WHERE role=? AND COALESCE(active,1)=1 ORDER BY id LIMIT 1", (role,)); assert r, f"{role} akkaunti yo'q"; return r[0]["id"]
def S(u):
    c = httpx.Client(base_url=B, timeout=300)
    r = c.post("/api/login", json={"user_id": u, "password": PW}); assert r.status_code == 200, f"login {u}: {r.text}"
    return c

from app import lrs_analytics as LA
from app import lrs as L

# =============================================================================================
print("== 1. Analitika matematikasi (sof funksiyalar)")
E = lambda verb, ts, **k: {"verb": verb, "ts": ts, "sub": k.pop("sub", False), "success": k.pop("success", None), "completion": k.pop("completion", None),
                           "score": k.pop("score", None), "duration": k.pop("duration", None), "progress": k.pop("progress", None), "item": None, "response": None}
s0 = LA.lesson_summary([])
ok(s0["status"] == "boshlanmagan" and s0["pct"] == 0 and s0["attempts"] == 0, "Bo'sh dars — boshlanmagan, 0 %")
s1 = LA.lesson_summary([E("initialized", "2026-10-01T10:00:00"), E("progressed", "2026-10-01T10:05:00", progress=40),
                        E("suspended", "2026-10-01T10:20:00", duration=1200)])
ok(s1["status"] == "jarayonda" and s1["pct"] == 40 and s1["time_s"] == 1200 and s1["last"] == "2026-10-01T10:20:00", f"Jarayonda: foiz progressed'dan, vaqt — suspended davomiyligidan ({s1})")
s2 = LA.lesson_summary([E("failed", "2026-10-02T10:00:00", sub=True, success=0, score=25), E("failed", "2026-10-02T10:10:00", sub=True, success=0, score=50),
                        E("failed", "2026-10-02T10:20:00", sub=False, success=0, score=50),      # paket: dars darajasidagi takror natija — sanalmaydi
                        E("passed", "2026-10-02T10:30:00", sub=True, success=1, score=75), E("completed", "2026-10-02T10:31:00", completion=1),
                        E("terminated", "2026-10-02T10:32:00", duration=1800)])
ok(s2["status"] == "otdi" and s2["attempts"] == 3 and s2["fails"] == 2 and s2["best"] == 75 and s2["score"] == 75 and s2["pct"] == 100,
   f"Paket: blok darajasidagi natijalar sanaladi (3 urinish, 2 ✗), dars darajasidagi takror — yo'q; eng yaxshi ball 75 ({s2['attempts']}/{s2['fails']})")
s3 = LA.lesson_summary([E("failed", "2026-10-03T09:00:00", success=0, score=40), E("failed", "2026-10-03T09:10:00", success=0, score=55)])
ok(s3["status"] == "otmadi" and s3["attempts"] == 2 and s3["fails"] == 2, "Kurs muharriri: dars darajasidagi natijalar — 2 urinish, testdan o'tmadi")
ok(LA.lesson_summary([E("completed", "2026-10-03T09:00:00", completion=1)])["status"] == "yakunlandi", "completed (testsiz dars) — yakunlandi, 100 %")
ok(LA.lesson_summary([E("failed", "2026-10-03T09:00:00", success=0, score=50), E("completed", "2026-10-03T09:01:00", completion=1)])["status"] == "otmadi",
   "Test yiqilgan, dars «completed» — baribir «testdan o'tmadi» (bajarilgan hisoblanmaydi)")

# savollar: 20 talaba × 3 savol. Q1 — oson, Q2 — kuchlilar topadi (yaxshi farqlaydi), Q3 — hamma «b» ni tanlaydi (chalg'ituvchi)
ans = []
for i in range(20):
    strong = i >= 10
    for it, okk, resp in (("q1", True, "a"), ("q2", strong, "a" if strong else "c"), ("q3", i % 10 == 0, "a" if i % 10 == 0 else "b")):
        ans.append({"student": i, "item": it, "ts": f"2026-10-01T10:{i:02d}:00", "success": int(okk), "response": resp})
ans.append({"student": 0, "item": "q2", "ts": "2026-10-09T10:00:00", "success": 1, "response": "a"})       # keyingi urinish — hisobga olinmaydi
st = LA.item_stats(ans)
ok(st["q1"]["p"] == 1.0 and "oson" in st["q1"]["flags"] and st["q1"]["top_wrong"] is None, "Q1: p = 1,0 — juda oson, noto'g'ri javob yo'q")
ok(st["q2"]["p"] == 0.5 and st["q2"]["n"] == 20, f"Q2: faqat birinchi urinish (p = {st['q2']['p']}, n = {st['q2']['n']})")
ok(st["q3"]["p"] == 0.1 and st["q3"]["top_wrong"] == "b" and st["q3"]["top_wrong_n"] == 18 and st["q3"]["wrong_share"] == 1.0 and {"qiyin", "chalgituvchi"} <= set(st["q3"]["flags"]),
   f"Q3: 90 % xato, eng ko'p xato javob «b» (18 ta, 100 %), belgilar {st['q3']['flags']}")
ok(st["q2"]["d"] is not None and st["q2"]["d"] > st["q3"]["d"] and st["q2"]["r_pb"] is not None, f"Farqlash: Q2 (D={st['q2']['d']}) > Q3 (D={st['q3']['d']}); r_pb={st['q2']['r_pb']}")
small = LA.item_stats([{"student": i, "item": "x", "ts": "t", "success": 1, "response": "a"} for i in range(5)])
ok(small["x"]["d"] is None and small["x"]["flags"] == [], "Kichik tanlov (n < 10) — farqlash hisoblanmaydi, belgi qo'yilmaydi")
fn = LA.funnel(["L1", "L2", "L3"], {(1, "L1"): "otdi", (2, "L1"): "yakunlandi", (1, "L2"): "otmadi", (3, "L1"): "jarayonda"}, 4)
ok([(f["started"], f["done"], f["passed"]) for f in fn] == [(3, 2, 1), (1, 0, 0), (0, 0, 0)] and fn[0]["done_pct"] == 50.0, f"Voronka: boshlagan / yakunlagan / o'tgan ({[(f['started'], f['done'], f['passed']) for f in fn]})")
st0 = dt.date(2026, 9, 1)          # seshanba
ok(LA.week_no(st0, dt.date(2026, 11, 14)) == 11 and LA.week_no(st0, dt.date(2026, 8, 30)) == 0 and LA.week_no(st0, dt.date(2026, 9, 6)) == 1, "Semestr haftasi: 14.11 — 11-hafta, semestrdan oldin — 0")
ok(LA.released(45, st0, dt.date(2026, 11, 14), 15) == 33 and LA.expected_done(45, st0, dt.date(2026, 11, 14), 15, 1) == 30 and LA.expected_done(45, st0, dt.date(2026, 11, 14), 15, 0) == 33,
   "45 dars / 15 hafta: 11-haftada 33 tasi chiqarilgan, kutilgan (1 hafta imtiyoz) — 30")
ok(LA.released(45, st0, dt.date(2027, 3, 1), 15) == 45 and LA.released(0, st0, dt.date(2026, 11, 1), 15) == 0, "Semestr tugagach — hammasi; darssiz kurs — 0")
P0 = dict(LA.DEFAULTS)
r_ = LA.risk_reasons({"expected": 30, "done": 6, "max_fails": 0, "days_inactive": 2, "started": True}, P0)
ok([x["code"] for x in r_] == ["ortda"] and r_[0]["sev"] == 3 and "24 dars ortda (6/30)" in r_[0]["label"], f"NEXTID hikoyasi: 6/30 — 24 dars ortda, og'ir ({r_[0]['label']})")
ok(LA.risk_reasons({"expected": 30, "done": 28, "max_fails": 2, "days_inactive": 6, "started": True}, P0) == [], "Chegaradan past (2 dars, 2 ✗, 6 kun) — sabab yo'q")
r2 = LA.risk_reasons({"expected": 10, "done": 7, "max_fails": 3, "fail_lesson": "A4", "days_inactive": 7, "started": True}, P0)
ok({x["code"] for x in r2} == {"ortda", "test", "faolsiz"} and LA.risk_level(r2) == "yuqori", f"Aynan chegarada (3 dars, 3 ✗, 7 kun) — uchala sabab, yuqori xavf: {[x['label'] for x in r2]}")
ok([x["code"] for x in LA.risk_reasons({"expected": 4, "done": 0, "started": False}, P0)] == ["ortda", "boshlamagan"], "Boshlamagan talaba: ortda + umuman boshlamagan")
ok(LA.risk_reasons({"expected": 0, "done": 0, "started": False}, P0) == [], "Hali dars chiqarilmagan — sabab yo'q")
ok([x["code"] for x in LA.risk_reasons({"expected": 10, "done": 6, "started": True, "days_inactive": 1}, {**P0, "lag_lessons": 5})] == [], "Chegara o'zgarsa (lag 5) — 4 dars kechikish xavf emas")
ok(L.parse_activity("https://isft.uz/xapi/paket/121/3") == ("dl:121", "L3", None) and L.parse_activity("https://isft.uz/xapi/paket/121/A12/block/b9/q/tb7") == ("dl:121", "A12", "block/b9/q/tb7")
   and L.parse_activity("https://isft.uz/xapi/kurs/5/lesson/labc123/q/bq12345") == ("ku:5", "labc123", "q/bq12345") and L.parse_activity("https://isft.uz/xapi/kurs/5") == ("ku:5", "", None)
   and L.parse_activity("https://evil.example/xapi/paket/1/1") is None and L.parse_activity("https://isft.uz/xapi/paket/1/../2") is None, "Faoliyat IRI → kurs / dars / element; begona domen va «..» — yo'q")
ok(L.parse_duration("PT1H2M3.5S") == 3723.5 and L.parse_duration("P1DT1S") == 86401 and L.parse_duration("12 min") is None and L.parse_duration("PT") is None, "ISO 8601 davomiylik")
ok(L._score_pct({"scaled": 0.75}) == 75 and L._score_pct({"raw": 8, "min": 0, "max": 10}) == 80 and L._score_pct(None) is None, "Ball → foiz (scaled yoki raw/min/max)")
ok(L.lesson_activity("dl:121", "L3") == "https://isft.uz/xapi/paket/121/3" and L.lesson_activity("dl:121", "A2") == "https://isft.uz/xapi/paket/121/A2", "Dars → faoliyat IRI (paket bilan bir xil)")

# =============================================================================================
print("== 2. LRS: kirish, ko'lam, tekshiruv, idempotentlik, bekor qilish, cheklovlar")
_con = sqlite3.connect(DBP, timeout=30, check_same_thread=False); _con.row_factory = sqlite3.Row
L._con = _con; L._KEY.clear()                         # token yaratish — server bilan bir xil kalit (baza lrs_meta) va jadval
c121 = q("SELECT * FROM dl_courses WHERE subject='Iqtisodiyot nazariyasi' AND direction='Iqtisodiyot' AND course=1")[0]
studs = [r["id"] for r in q("""SELECT s.id FROM students s JOIN groups_ g ON g.id=s.group_id WHERE s.study_form='masofaviy' AND s.status='faol'
                               AND g.direction=? AND g.course=? ORDER BY s.id""", (c121["direction"], c121["course"]))]
SA, SB = studs[-1], studs[-2]
CR = f"dl:{c121['id']}"
tA = L.make_auth(SA, CR, "L15"); tB = L.make_auth(SB, CR, "L15")
H = lambda t: {"Authorization": t["auth"], "X-Experience-API-Version": "1.0.3", "Content-Type": "application/json"}
ACT1 = f"https://isft.uz/xapi/paket/{c121['id']}/15"
ACTOR_A = {"objectType": "Agent", "account": {"homePage": "https://isft.uz", "name": tA["learner"]}}
def stmt(verb="experienced", act=ACT1, actor=None, **k):
    s = {"id": str(uuid.uuid4()), "actor": actor or ACTOR_A, "verb": {"id": "http://adlnet.gov/expapi/verbs/" + verb, "display": {"en-US": verb}},
         "object": {"objectType": "Activity", "id": act}, "timestamp": dt.datetime.now(dt.timezone.utc).isoformat(), "context": {"registration": tA["registration"]}}
    s.update(k); return s
X = httpx.Client(base_url=B, timeout=60)
ab = X.get("/xapi/about")
ok(ab.status_code == 200 and "1.0.3" in ab.json()["version"] and ab.headers.get("x-experience-api-version") == "1.0.3", "/xapi/about: versiya 1.0.3")
op = X.options("/xapi/statements", headers={"Origin": "null", "Access-Control-Request-Method": "POST"})
ok(op.status_code == 204 and op.headers.get("access-control-allow-origin") == "*" and "Authorization" in op.headers.get("access-control-allow-headers", ""), "CORS preflight: 204, Authorization ruxsat")
s1 = stmt("initialized")
ok(X.post("/xapi/statements", json=s1, headers={"Authorization": tA["auth"]}).status_code == 400, "X-Experience-API-Version sarlavhasisiz — 400")
ok(X.post("/xapi/statements", json=s1, headers={"X-Experience-API-Version": "1.0.3"}).status_code == 401, "Authorization'siz — 401")
bad = "Basic " + base64.b64encode(tA["auth"][6:].encode()[:10]).decode()
ok(X.post("/xapi/statements", json=s1, headers={**H(tA), "Authorization": bad}).status_code == 401, "Buzuq token — 401")
raw = base64.b64decode(tA["auth"][6:]).decode(); forged = raw[:-3] + ("000" if not raw.endswith("000") else "111")
ok(X.post("/xapi/statements", json=s1, headers={**H(tA), "Authorization": "Basic " + base64.b64encode(forged.encode()).decode()}).status_code == 401, "Imzosi o'zgartirilgan token — 401")
jti, _, rest = raw.partition(":"); pl, _, sg = rest.rpartition(".")
pd = json.loads(base64.urlsafe_b64decode(pl + "=" * (-len(pl) % 4))); pd["s"] = "L2"
pl2 = base64.urlsafe_b64encode(json.dumps(pd, separators=(",", ":")).encode()).decode().rstrip("=")
ok(X.post("/xapi/statements", json=s1, headers={**H(tA), "Authorization": "Basic " + base64.b64encode(f"{jti}:{pl2}.{sg}".encode()).decode()}).status_code == 401,
   "Token yukidagi darsni almashtirish (L15 → L2, imzo eski) — 401")
tE = L.make_auth(SA, CR, "L15", hours=-1)
ok(X.post("/xapi/statements", json=s1, headers=H(tE)).status_code == 401, "Muddati o'tgan token — 401")
tR = L.make_auth(SA, CR, "L15"); _con.execute("UPDATE lrs_tokens SET revoked=1 WHERE jti=?", (tR["jti"],)); _con.commit()
ok(X.post("/xapi/statements", json=s1, headers=H(tR)).status_code == 401, "Bekor qilingan token — 401")
r = X.post("/xapi/statements", json=s1, headers=H(tA))
ok(r.status_code == 200 and r.json() == [s1["id"]], f"To'g'ri statement — 200 va id ({r.status_code} {r.text[:120]})")
row = q("SELECT * FROM lrs_statements WHERE id=?", (s1["id"],))
ok(row and row[0]["student_id"] == SA and row[0]["course_ref"] == CR and row[0]["lesson_ref"] == "L15" and row[0]["verb"] == "initialized" and row[0]["src"] == "lrs"
   and row[0]["token"] == tA["jti"], "Bazada: talaba (taxallusdan), kurs, dars, fe'l, token")
ok(X.post("/xapi/statements", json=stmt(act=f"https://isft.uz/xapi/paket/{c121['id']}/14"), headers=H(tA)).status_code == 403, "L15 tokeni L14 darsiga yoza olmaydi — 403")
ok(X.post("/xapi/statements", json=stmt(act=f"https://isft.uz/xapi/paket/{c121['id']}/A1"), headers=H(tA)).status_code == 403, "L15 tokeni A1 (amaliy) darsiga — 403")
ok(X.post("/xapi/statements", json=stmt(act="https://isft.uz/xapi/paket/999999/1"), headers=H(tA)).status_code == 403, "Boshqa kurs — 403")
ok(X.post("/xapi/statements", json=stmt(act="https://isft.uz/xapi/kurs/1"), headers=H(tA)).status_code == 403, "Kurs muharriri faoliyati (boshqa nomlar fazosi) — 403")
ACTOR_B = {"objectType": "Agent", "account": {"homePage": "https://isft.uz", "name": tB["learner"]}}
ok(X.post("/xapi/statements", json=stmt(actor=ACTOR_B), headers=H(tA)).status_code == 403, "A talaba tokeni B talaba nomidan yoza olmaydi — 403")
ok(X.post("/xapi/statements", json=stmt(actor={"objectType": "Agent", "mbox": "mailto:x@isft.uz"}), headers=H(tA)).status_code == 403, "Email bilan actor (taxallus emas) — 403")
ok(X.post("/xapi/statements", json=stmt(context={"registration": str(uuid.uuid4())}), headers=H(tA)).status_code == 403, "Boshqa registration — 403")
ok(q("SELECT COUNT(*) n FROM audit_log WHERE resource='lrs' AND allowed=0 AND action LIKE 'LRS: statement rad etildi%'")[0]["n"] >= 5, "Rad etilgan statementlar audit jurnalida")
def mod(s, **k): s = dict(s); s.update(k); return s
BAD = [("verb.id IRI emas", mod(stmt(), verb={"id": "salom"})), ("ikki identifikator", stmt(actor={**ACTOR_A, "mbox": "mailto:a@b.c"})),
       ("Group actor", stmt(actor={"objectType": "Group", "member": []})), ("score.scaled > 1", stmt("passed", result={"score": {"scaled": 2}})),
       ("raw > max", stmt("passed", result={"score": {"raw": 120, "min": 0, "max": 100}})), ("success matn", stmt("passed", result={"success": "ha"})),
       ("duration noto'g'ri", stmt("terminated", result={"duration": "20 daqiqa"})), ("timestamp noto'g'ri", stmt(timestamp="kecha")),
       ("noma'lum maydon", {**stmt(), "foo": 1}), ("id UUID emas", {**stmt(), "id": "123"}), ("SubStatement obyekt", stmt(object={"objectType": "SubStatement"})),
       ("registration UUID emas", stmt(context={"registration": "x"})), ("actor yo'q", {k: v for k, v in stmt().items() if k != "actor"})]
for nm, sx in BAD:
    rr = X.post("/xapi/statements", json=sx, headers=H(tA))
    ok(rr.status_code == 400, f"Tekshiruv: {nm} — 400 ({rr.status_code})")
# idempotentlik
n0 = q("SELECT COUNT(*) n FROM lrs_statements")[0]["n"]
ok(X.post("/xapi/statements", json=s1, headers=H(tA)).status_code == 200 and q("SELECT COUNT(*) n FROM lrs_statements")[0]["n"] == n0, "Bir xil statement qayta yuborildi — 200, dublikat yozilmadi (idempotent)")
ok(X.post("/xapi/statements", json={**s1, "verb": {"id": "http://adlnet.gov/expapi/verbs/completed"}}, headers=H(tA)).status_code == 409, "Bir xil id, boshqa mazmun — 409")
sp = stmt("progressed", result={"extensions": {L.PROGRESS_EXT: 40}})
ok(X.put("/xapi/statements", params={"statementId": sp["id"]}, json={k: v for k, v in sp.items() if k != "id"}, headers=H(tA)).status_code == 204, "PUT ?statementId — 204")
ok(X.put("/xapi/statements", params={"statementId": sp["id"]}, json={k: v for k, v in sp.items() if k != "id"}, headers=H(tA)).status_code == 204, "PUT takror (bir xil) — 204")
ok(X.put("/xapi/statements", params={"statementId": str(uuid.uuid4())}, json=sp, headers=H(tA)).status_code == 400, "PUT: statementId va id mos emas — 400")
good, badd = stmt("experienced"), mod(stmt(), verb={"id": "x"})
ok(X.post("/xapi/statements", json=[good, badd], headers=H(tA)).status_code == 400 and not q("SELECT 1 FROM lrs_statements WHERE id=?", (good["id"],)), "Paket (batch) atomik: bittasi noto'g'ri — hech biri yozilmaydi")
dup = stmt("experienced")
ok(X.post("/xapi/statements", json=[dup, dup], headers=H(tA)).status_code == 200, "Bir so'rovda aynan bir xil statement ikki marta — bitta yoziladi")
ok(X.post("/xapi/statements", json=[dup, {**dup, "verb": {"id": "http://adlnet.gov/expapi/verbs/completed"}}], headers=H(tA)).status_code in (400, 409), "Bir so'rovda bir id — ikki xil mazmun — rad")
# progress va bekor qilish
pf = [stmt("failed", act=ACT1 + "/block/b9", result={"success": False, "score": {"scaled": 0.25}}) for _ in range(3)]
ok(X.post("/xapi/statements", json=pf, headers=H(tA)).status_code == 200, "3 ta muvaffaqiyatsiz urinish")
pr = q("SELECT * FROM lrs_progress WHERE student_id=? AND course_ref=? AND lesson_ref='L15'", (SA, CR))[0]
ok(pr["status"] == "otmadi" and pr["fails"] == 3 and pr["attempts"] == 3 and pr["pct"] == 40 and pr["src"] == "lrs", f"lrs_progress darhol qayta hisoblandi: otmadi, 3 ✗, 40 % ({pr['status']}, {pr['fails']}, {pr['pct']})")
vd = stmt("voided"); vd["object"] = {"objectType": "StatementRef", "id": pf[0]["id"]}; vd.pop("context")
ok(X.post("/xapi/statements", json=vd, headers=H(tA)).status_code == 200, "voided — 200")
ok(q("SELECT voided FROM lrs_statements WHERE id=?", (pf[0]["id"],))[0]["voided"] == 1 and q("SELECT fails FROM lrs_progress WHERE student_id=? AND course_ref=? AND lesson_ref='L15'", (SA, CR))[0]["fails"] == 2,
   "Bekor qilingan statement hisobdan chiqdi (fails 3 → 2)")
G = lambda t, **p: X.get("/xapi/statements", params=p, headers=H(t))
ok(G(tA, statementId=pf[0]["id"]).status_code == 404 and G(tA, voidedStatementId=pf[0]["id"]).status_code == 200, "GET statementId (bekor qilingan) — 404; voidedStatementId — 200")
vv = stmt("voided"); vv["object"] = {"objectType": "StatementRef", "id": vd["id"]}; vv.pop("context")
ok(X.post("/xapi/statements", json=vv, headers=H(tA)).status_code == 400, "«voided» statementni bekor qilib bo'lmaydi — 400")
sb = stmt("initialized", actor=ACTOR_B, context={"registration": tB["registration"]})
ok(X.post("/xapi/statements", json=sb, headers=H(tB)).status_code == 200, "B talaba o'z tokeni bilan yozdi")
vb = stmt("voided"); vb["object"] = {"objectType": "StatementRef", "id": sb["id"]}; vb.pop("context")
ok(X.post("/xapi/statements", json=vb, headers=H(tA)).status_code == 403 and q("SELECT voided FROM lrs_statements WHERE id=?", (sb["id"],))[0]["voided"] == 0, "A talaba B ning statementini bekor qila olmaydi — 403")
ok(X.post("/xapi/statements", json={**stmt("voided"), "object": {"objectType": "StatementRef", "id": str(uuid.uuid4())}}, headers=H(tA)).status_code == 400, "Mavjud bo'lmagan statementni bekor qilish — 400")
# GET
g = G(tA, verb="http://adlnet.gov/expapi/verbs/failed")
ok(g.status_code == 200 and len(g.json()["statements"]) == 2 and all(s["actor"]["account"]["name"] == tA["learner"] and s["stored"] and s["version"] == "1.0.3" for s in g.json()["statements"]),
   "GET verb filtri: faqat o'z statementlari (bekor qilinganisiz), stored/version bilan")
ok(G(tA, statementId=sb["id"]).status_code == 404, "Boshqa talabaning statementi ko'rinmaydi (404)")
ok(G(tA, agent=json.dumps(ACTOR_B)).status_code == 403 and G(tA, activity="https://isft.uz/xapi/paket/999/1").status_code == 403, "GET: boshqa agent yoki ko'lamdan tashqari faoliyat — 403")
ok(len(G(tA, since=(dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=1)).isoformat()).json()["statements"]) == 0, "GET since (kelajak) — bo'sh")
# State API
SP = {"activityId": ACT1, "agent": json.dumps(ACTOR_A), "stateId": "isft-state", "registration": tA["registration"]}
ok(X.get("/xapi/activities/state", params=SP, headers=H(tA)).status_code == 404, "State: hujjat yo'q — 404")
ok(X.put("/xapi/activities/state", params=SP, content='{"c":3,"v":"1101"}', headers=H(tA)).status_code == 204, "State PUT — 204")
gs = X.get("/xapi/activities/state", params=SP, headers=H(tA))
ok(gs.status_code == 200 and gs.json() == {"c": 3, "v": "1101"}, "State GET — saqlangan hujjat (resume)")
ok(X.post("/xapi/activities/state", params=SP, content='{"x":1}', headers=H(tA)).status_code == 204 and X.get("/xapi/activities/state", params=SP, headers=H(tA)).json() == {"c": 3, "v": "1101", "x": 1},
   "State POST — JSON birlashtiriladi")
ok(X.get("/xapi/activities/state", params={**SP, "agent": json.dumps(ACTOR_B)}, headers=H(tA)).status_code == 403
   and X.put("/xapi/activities/state", params={**SP, "activityId": "https://isft.uz/xapi/paket/1/9"}, content="{}", headers=H(tA)).status_code == 403,
   "State: boshqa agent yoki boshqa dars — 403")
ok(X.put("/xapi/activities/state", params=SP, content="x" * (L.MAX_STATE + 10), headers=H(tA)).status_code == 413, "State hujjati > 64 KB — 413")
# hajm va son chegaralari
big = stmt(object={"objectType": "Activity", "id": ACT1, "definition": {"description": {"uz": "x" * 40000}}})
ok(X.post("/xapi/statements", json=big, headers=H(tA)).status_code == 413, "Statement > 32 KB — 413")
ok(X.post("/xapi/statements", content=b"[" + b" " * (L.MAX_BODY + 10) + b"]", headers=H(tA)).status_code == 413, "So'rov tanasi > 512 KB — 413")
ok(X.post("/xapi/statements", json=[stmt() for _ in range(L.MAX_BATCH + 1)], headers=H(tA)).status_code == 400, f"Bir so'rovda > {L.MAX_BATCH} statement — 400")
ok(X.post("/xapi/statements", json=stmt("answered", result={"response": "x" * 4001}), headers=H(tA)).status_code == 400, "result.response > 4000 belgi — 400")
tL = L.make_auth(SB, CR, "L15")
codes = [X.get("/xapi/statements", headers=H(tL)).status_code for _ in range(L.RATE_REQ[0] + 3)]
ok(codes.count(200) == L.RATE_REQ[0] and codes[-1] == 429, f"Token bo'yicha cheklov: {L.RATE_REQ[0]} so'rov/daqiqa, keyin 429 ({codes.count(429)} ta)")
r429 = X.get("/xapi/statements", headers=H(tL))
ok(r429.status_code == 429 and int(r429.headers.get("retry-after", "0")) > 0, "429 — Retry-After sarlavhasi bilan")
# hamkor (NEXTID) — server-server kirish (jarayon ichida: parse_auth + validate)
os.environ["ISFT_CORE_LRS_PARTNER"] = "nextid:" + "s" * 24
pa = L.parse_auth("Basic " + base64.b64encode(("nextid:" + "s" * 24).encode()).decode())
hem = q("SELECT hemis_id FROM students WHERE id=?", (SA,))[0]["hemis_id"]
v = L.validate(stmt(actor={"objectType": "Agent", "account": {"homePage": "https://my.isft.uz", "name": hem}}, context={}), pa)
ok(pa["kind"] == "partner" and v["student_id"] == SA, "Hamkor kirishi: actor — HEMIS ID (my.isft.uz) → talaba")
try: L.parse_auth("Basic " + base64.b64encode(b"nextid:notogri-parol-1234567890").decode()); ok(False, "Hamkor: noto'g'ri parol rad etilishi kerak")
except L.XErr as e: ok(e.status == 401, "Hamkor: noto'g'ri parol — 401")
try: L.validate(stmt(actor={"objectType": "Agent", "account": {"homePage": "https://my.isft.uz", "name": "0000"}}, context={}), pa); ok(False, "noma'lum HEMIS")
except L.XErr as e: ok(e.status == 400, "Hamkor: noma'lum HEMIS ID — 400")
del os.environ["ISFT_CORE_LRS_PARTNER"]

# =============================================================================================
print("== 3. Ishga tushirish yo'li (launch)")
head, staff, teach, kaf, rek, pro, bux = (S(uid(r)) for r in ("masofaviy", "masofaviy_xodim", "oqituvchi", "kafedra", "rektor", "prorektor_oquv", "buxgalteriya"))
tut_uid = uid("tyutor"); tut = S(tut_uid)
K = "/api/kurs"
kc = head.post(K + "/courses", json={"title": "LRS sinov kursi: talab va taklif", "dl_course_id": c121["id"]}).json()["id"]
co = head.get(f"{K}/courses/{kc}").json()
l1 = co["lessons_list"][0]["id"]; L1 = head.get(f"{K}/lessons/{l1}").json()
head.post(f"{K}/lessons/{l1}", json={"rev": L1["rev"], "title": "Bozor muvozanati", "blocks": [{"type": "heading", "data": {"text": "Talab va taklif"}},
          {"type": "paragraph", "data": {"html": "<p>Muvozanat narxi — talab va taklif tenglashgan nuqta.</p>"}}]})
nq = head.post(f"{K}/courses/{kc}/lessons", json={"type": "quiz"}).json()
lq = nq["course"]["lessons_list"][1]["id"]; LQ = head.get(f"{K}/lessons/{lq}").json()
QS = [{"type": "question", "data": {"kind": "single", "question": "Narx oshsa talab nima bo'ladi?", "answers": [{"text": "Kamayadi", "correct": True}, {"text": "Oshadi"}, {"text": "O'zgarmaydi"}]}},
      {"type": "question", "data": {"kind": "single", "question": "Muvozanat narxi qayerda?", "answers": [{"text": "Talab = taklif", "correct": True}, {"text": "Talab > taklif"}]}}]
sv = head.post(f"{K}/lessons/{lq}", json={"rev": LQ["rev"], "title": "Yakuniy test", "quiz": {"pass_pct": 100, "shuffle": False, "attempts": 0}, "blocks": QS})
ok(sv.status_code == 200, f"Sinov kursi: dars + test (2 savol), Iqtisodiyot nazariyasi (1-kurs) ga bog'langan ({sv.status_code})")
KR = f"ku:{kc}"
nolink = head.post("/api/lrs/launch-link", json={"student_id": SA, "course_ref": KR}).json()
ok(nolink["package"] is False and nolink["note"], "Eksportdan oldin: havola beriladi, lekin «paket hali eksport qilinmagan»")
ok(httpx.get(B + nolink["url"], follow_redirects=False).status_code == 404, "Eksportsiz havola ochilsa — 404 (tushunarli xabar)")
ex = head.post(f"{K}/courses/{kc}/export", json={"mode": "xapi"})
ok(ex.status_code == 200 and ex.json()["ok"], "xAPI eksport")
ok(staff.post("/api/lrs/launch-link", json={"student_id": SA, "course_ref": KR}).status_code == 200, "Bo'lim xodimi ham havola yaratadi")
ok(teach.post("/api/lrs/launch-link", json={"student_id": SA, "course_ref": KR}).status_code == 403 and tut.post("/api/lrs/launch-link", json={"student_id": SA, "course_ref": KR}).status_code == 403,
   "O'qituvchi va tyutor havola yaratmaydi (403)")
ok(head.post("/api/lrs/launch-link", json={"student_id": SA, "course_ref": CR, "lesson_ref": "X9"}).status_code == 400 and head.post("/api/lrs/launch-link", json={"student_id": SA, "course_ref": "dl:9999999", "lesson_ref": "L1"}).status_code == 404,
   "Noto'g'ri dars kodi — 400, noma'lum kurs — 404")
lk = head.post("/api/lrs/launch-link", json={"student_id": SA, "course_ref": KR}).json()
stu = q("SELECT full_name, hemis_id FROM students WHERE id=?", (SA,))[0]
rd = httpx.get(B + lk["url"], follow_redirects=False)
loc = rd.headers.get("location", "")
qp = {k: v[0] for k, v in parse_qs(urlsplit(loc).query).items()}
ok(rd.status_code == 302 and loc.startswith(lk["url"].replace("/xapi/l/", "/xapi/pkg/") + "/index.html?"), "Havola → 302 → /xapi/pkg/<kod>/index.html")
ok(set(qp) == {"endpoint", "auth", "actor", "registration", "activity_id"} and qp["endpoint"].endswith("/xapi/") and qp["auth"].startswith("Basic ")
   and qp["activity_id"] == f"https://isft.uz/xapi/kurs/{kc}" and re.fullmatch(r"[0-9a-f-]{36}", qp["registration"]), "Launch parametrlari: endpoint, auth, actor, registration, activity_id")
act = json.loads(qp["actor"])
ok(act["account"]["homePage"] == "https://isft.uz" and re.fullmatch(r"s[0-9a-f]{20}", act["account"]["name"]) and "name" not in act and "mbox" not in act,
   f"Actor — faqat taxallus ({act['account']['name']}), ism/email yo'q")
low = (lk["url"] + loc).lower()
ok(stu["hemis_id"] not in low and stu["full_name"].split()[0].lower() not in low, "Havola va launch URL'da ism yoki HEMIS ID yo'q")
rd2 = httpx.get(B + lk["url"], follow_redirects=False)
qp2 = {k: v[0] for k, v in parse_qs(urlsplit(rd2.headers["location"]).query).items()}
ok(qp2["auth"] != qp["auth"] and qp2["registration"] == qp["registration"], "Har ochilishda yangi token, registration — barqaror")
base = loc.split("?")[0].rsplit("/", 1)[0]
ix = httpx.get(B + base + "/index.html")
csp = ix.headers.get("content-security-policy", "")
ok(ix.status_code == 200 and "connect-src " in csp and "/xapi/;" in csp and "script-src 'self'" in csp and "default-src 'none'" in csp, f"Paket index.html: qat'iy CSP, connect-src faqat /xapi/")
ok(httpx.get(B + base + "/content.js").status_code == 200 and httpx.get(B + base + "/lms.js").status_code == 200, "content.js va lms.js eksport zip ichidan")
ok(httpx.get(B + base + "/../../etc/passwd").status_code in (400, 404) and httpx.get(B + base + "/a%2F..%2Fb").status_code in (400, 404), "Yo'l hujumi — 400/404")
ok(httpx.get(B + "/xapi/pkg/AAAA.bbbb/index.html").status_code == 403 and httpx.get(B + lk["url"][:-3] + "abc", follow_redirects=False).status_code == 403, "Soxta / o'zgartirilgan havola kodi — 403")
old = L.make_link(SA, KR, "", days=-1)
ok(httpx.get(B + "/xapi/l/" + old, follow_redirects=False).status_code == 403, "Muddati o'tgan havola — 403")
tk = L.parse_auth(qp["auth"])
ok(tk["student_id"] == SA and tk["course_ref"] == KR and tk["lesson_ref"] == "", "Launch tokeni: shu talaba, shu kurs")

# =============================================================================================
print("== 4. «Ortda qolganlar»: ruxsatlar, qoidalar, amallar")
O = "/api/ortda"
m = head.get(O + "/meta").json()
ok(m["caps"]["assign"] and m["caps"]["policy"] and m["caps"]["hemis"] and m["source"] in ("demo", "mixed") and any(x["ref"] == CR for x in m["courses"]),
   f"Bo'lim boshlig'i: to'liq imkoniyatlar, namuna manbasi ({m['source']}), {len(m['courses'])} kurs")
ok(staff.get(O + "/meta").json()["caps"]["policy"] is False, "Bo'lim xodimi chegaralarni o'zgartirmaydi")
lst = head.get(O + "/list", params={"course": CR, "limit": 200}).json()
story = next((x for x in lst["items"] if x["done"] == 6 and x["lessons"] == 45), None)
ok(lst["total"] > 0 and story and story["lag"] >= 3 and any(r["code"] == "ortda" for r in story["reasons"]),
   f"Namuna hikoyasi: 45 darslik kursda 6 ta bajargan talaba ortda ({story and story['done']}/{story and story['expected']})")
ok(all(x["reasons"] for x in lst["items"]) and lst["items"] == sorted(lst["items"], key=lambda r: (-r["risk"], -r["lag"], r["full_name"])), "Ro'yxat: faqat sababi borlar, xavf og'irligi bo'yicha")
ok("hemis_id" in lst["items"][0] and "phone" not in json.dumps(lst), "Bo'lim: HEMIS ID bor, telefon ro'yxatda yo'q")
sm = rek.get(O + "/summary").json()
ok(sm["students"] > 0 and not re.search(r'"full_name"|"hemis_id"|"student_id"', json.dumps(sm)), "Rektor: jamlangan sonlar — ism, HEMIS, talaba id'si yo'q")
ok(rek.get(O + "/list").status_code == 403 and pro.get(O + "/list").status_code == 403 and rek.get(f"{O}/student/{SA}", params={"course": CR}).status_code == 403,
   "Rektor / o'quv prorektori: individual ro'yxat va talaba darslari — 403")
ok(rek.get(O + "/questions", params={"ref": CR}).status_code == 403 and kaf.get(O + "/list").status_code == 403, "Rektor — savollar tahlili 403; kafedra — individual ro'yxat 403")
kd = q("SELECT department_id FROM users WHERE id=?", (uid("kafedra"),))[0]["department_id"]
km = kaf.get(O + "/meta").json()
own_dept = {r["ref"] for r in km["courses"]}
dl_dept = {f"dl:{r['id']}" for r in q("SELECT id FROM dl_courses WHERE department_id=?", (kd,))}
ok(own_dept <= dl_dept | {f"ku:{x}" for x in [kc]} and not re.search(r'"full_name"', json.dumps(kaf.get(O + "/summary").json())), f"Kafedra: faqat o'z kafedrasi kurslari, ismsiz ({len(own_dept)} kurs)")
other_ref = next((r["ref"] for r in m["courses"] if r["ref"] not in own_dept), None)
if other_ref: ok(kaf.get(O + "/course", params={"ref": other_ref}).status_code == 403, "Kafedra begona kurs analitikasini ko'rmaydi (403)")
tm = teach.get(O + "/meta").json()
tt = q("SELECT teacher_id FROM users WHERE id=?", (uid("oqituvchi"),))[0]["teacher_id"]
ok(all(r["ref"] in {f"dl:{x['id']}" for x in q("SELECT id FROM dl_courses WHERE teacher_id=?", (tt,))} | {f"ku:{x['id']}" for x in q("SELECT id FROM ku_courses WHERE author_id=?", (uid("oqituvchi"),))}
       for r in tm["courses"]) and not tm["caps"]["assign"] and not tm["caps"]["remind"], f"O'qituvchi: faqat o'z kurslari ({len(tm['courses'])}), amallarsiz")
tl = teach.get(O + "/list", params={"limit": 200}).json()
ok("hemis_id" not in json.dumps(tl) and "phone" not in json.dumps(tl), "O'qituvchi ro'yxatida HEMIS ID va telefon yo'q")
scope_t = {r["id"] for r in q("SELECT s.id FROM students s WHERE s.group_id IN (SELECT group_id FROM teacher_groups WHERE teacher_id=?)", (tt,))}
ok(all(x["student_id"] in scope_t for x in tl["items"]), f"O'qituvchi faqat o'z guruhlari talabalarini ko'radi (rbac ko'lami, {tl['total']} ta)")
if not tm["courses"]: ok(teach.get(O + "/course", params={"ref": CR}).status_code == 403, "O'qituvchi begona kursni ko'rmaydi (403)")
ok(teach.post(O + "/remind", json={"student_id": SA, "course_ref": CR}).status_code == 403 and teach.post(O + "/assign", json={"student_id": SA, "course_ref": CR, "tutor_id": tut_uid}).status_code == 403,
   "O'qituvchi eslatma yubormaydi va biriktirmaydi (403)")
ok(bux.get(O + "/meta").status_code == 403 and bux.get(O + "/summary").status_code == 403, "Buxgalteriya — 403")
# tyutor: avval — o'z guruhlarida masofaviy talaba yo'q
t0 = tut.get(O + "/list", params={"limit": 200}).json()
ok(all(x["student_id"] != SB for x in t0["items"]) and tut.get(f"{O}/student/{SB}", params={"course": CR}).status_code == 403, "Tyutor: biriktirilmagan talaba ko'rinmaydi (403)")
ok(tut.post(O + "/remind", json={"student_id": SB, "course_ref": CR}).status_code == 403, "Tyutor begona talabaga eslatma yubora olmaydi (403)")
ok(tut.post(O + "/assign", json={"student_id": SB, "course_ref": CR, "tutor_id": tut_uid}).status_code == 403, "Tyutor biriktira olmaydi (403)")
sd = head.get(f"{O}/student/{SB}", params={"course": CR}).json()
ok(len(sd["lessons"]) == 45 and bool(sd["tutors"]) and [x["ref"] for x in sd["lessons"][:3]] == ["L1", "A1", "A2"],f"Talaba darslari: 45 ta, taqvim tartibida; tyutor nomzodlari {len(sd['tutors'])}")
asg = head.post(O + "/assign", json={"student_id": SB, "course_ref": CR, "tutor_id": tut_uid, "note": "Telefon orqali bog'laning"})
ok(asg.status_code == 200 and asg.json()["task_id"], f"Tyutorga biriktirildi — topshiriq #{asg.json().get('task_id')}")
task = q("SELECT * FROM tasks WHERE id=?", (asg.json()["task_id"],))[0]
ok(task["assignee_user"] == tut_uid and task["origin"] == "topshiriq" and (task["src"] or "").startswith("lrs:") and task["status"] == "yangi" and "ortda qolgan" in task["text"],
   "Topshiriqlar tizimida: tyutorga, «yangi», manba lrs")
mw = tut.get("/api/mywork").json()
ok(any(it["link"] and it["link"].get("directive") == task["id"] for it in mw["items"]), "Tyutorning «Mening vazifalarim»ida topshiriq bor")
ok(tut.get(f"/api/dir/{task['id']}").status_code == 200, "Tyutor topshiriq kartasini ochadi")
t1 = tut.get(O + "/list", params={"course": CR, "only_risk": "false", "limit": 200}).json()
ok(any(x["student_id"] == SB for x in t1["items"]) and tut.get(f"{O}/student/{SB}", params={"course": CR}).status_code == 200, "Biriktirilgandan keyin tyutor shu talabani ko'radi")
ok(all(x["student_id"] in ({SB} | {r["id"] for r in q("SELECT s.id FROM students s WHERE s.group_id IN (SELECT group_id FROM tutor_groups WHERE user_id=?)", (tut_uid,))}) for x in t1["items"]),
   "Tyutor ro'yxati: faqat o'z guruhlari + biriktirilganlar")
ok("hemis_id" not in json.dumps(t1), "Tyutorga HEMIS ID berilmaydi")
n_ops = q("SELECT COUNT(*) n FROM ops_notices")[0]["n"]
rm = tut.post(O + "/remind", json={"student_id": SB, "course_ref": CR, "channel": "telegram"})
ok(rm.status_code == 200 and q("SELECT COUNT(*) n FROM ops_notices")[0]["n"] == n_ops + 1, "Tyutor eslatma yubordi — Talabalar markazi xabarlar navbatida (ops_notices)")
nt = q("SELECT * FROM ops_notices WHERE id=?", (rm.json()["notice_id"],))[0]
ok(nt["status"] == "navbatda" and nt["channel"] == "telegram" and "Iqtisodiyot nazariyasi" in nt["text"], "Xabar: navbatda, Telegram, kurs nomi bilan")
ok(head.post(O + "/remind", json={"student_id": SB, "course_ref": CR}).status_code == 429, "Takroriy eslatma (cheklov muddati ichida) — 429, boshqa xodimdan ham")
ok(q("SELECT COUNT(*) n FROM lrs_actions WHERE student_id=? AND kind='eslatma'", (SB,))[0]["n"] == 1 and q("SELECT COUNT(*) n FROM audit_log WHERE action='ortda qolganlar: eslatma cheklovi' AND allowed=0")[0]["n"] >= 1,
   "Eslatma jurnalda bitta; cheklov urinishi auditda")
ct = tut.post(O + "/contacted", json={"student_id": SB, "course_ref": CR, "note": "Gaplashildi"})
ok(ct.status_code == 200 and q("SELECT status FROM lrs_actions WHERE kind='tyutor' AND student_id=? AND tutor_user=?", (SB, tut_uid))[0]["status"] == "yopildi",
   "«Bog'lanildi» — jurnalga yozildi, tyutor biriktirmasi yopildi")
li = head.get(O + "/list", params={"course": CR, "only_risk": "false", "q": q("SELECT full_name FROM students WHERE id=?", (SB,))[0]["full_name"]}).json()["items"]
ok(li and set(li[0]["actions"]) >= {"tyutor", "eslatma", "boglanildi"}, "Ro'yxatda amallar tarixi (tyutor, eslatma, bog'lanildi)")
ok(head.post(O + "/remind", json={"student_id": 10**9, "course_ref": CR}).status_code == 404, "Noma'lum talaba — 404")
# chegaralar
before = head.get(O + "/summary", params={"course": CR}).json()["at_risk"]
ok(staff.post(O + "/policy", json={"lag_lessons": 5}).status_code == 403, "Bo'lim xodimi chegarani o'zgartirmaydi (403)")
ok(head.post(O + "/policy", json={"lag_lessons": 0}).status_code == 400 and head.post(O + "/policy", json={"nima": 1}).status_code == 400, "Chegara oralig'idan tashqari / noma'lum — 400")
ok(head.post(O + "/policy", json={"lag_lessons": 25}).status_code == 200, "Bo'lim boshlig'i: lag_lessons = 25")
after = head.get(O + "/summary", params={"course": CR}).json()["at_risk"]
ok(after < before, f"Chegara oshdi — ortda qolganlar kamaydi ({before} → {after})")
head.post(O + "/policy", json={"lag_lessons": 3})
# kurs voronkasi va savollar
cv = head.get(O + "/course", params={"ref": CR}).json()
ok(len(cv["lessons"]) == 45 and cv["released"] >= cv["expected"] and cv["lessons"][0]["started"] >= cv["lessons"][-1]["started"] and cv["plan_demo"], "Kurs voronkasi: 45 dars, boshlaganlar kamayib boradi")
qv = head.get(O + "/questions", params={"ref": CR}).json()
hard = [x for x in qv["items"] if x["wrong_pct"] and x["wrong_pct"] >= 60]
ok(bool(hard) and hard[0]["top_wrong"] == "b" and bool({"qiyin", "chalgituvchi"} & set(hard[0]["flags"])),f"Savollar: «bu savolni {hard[0]['wrong_pct'] if hard else '?'}% xato topyapti», eng ko'p xato javob «b»")
ok(all(x["link"] and x["link"]["view"] == "paket" for x in qv["items"][:5]), "Paket savollari — «Dars tayyorlash» darsiga havola")
ok(kaf.get(O + "/questions", params={"ref": next(iter(own_dept))}).status_code == 200 if own_dept else True, "Kafedra o'z kursi savollar tahlilini ko'radi")

# =============================================================================================
print("== 5. Uchidan-uchigacha: launch → javob → statementlar → ekran")
def lrs_post_as_player(tok_auth, actor, reg, statements):
    return X.post("/xapi/statements", json=statements, headers={"Authorization": tok_auth, "X-Experience-API-Version": "1.0.3"})
before_row = next((x for x in head.get(O + "/list", params={"course": KR, "only_risk": "false", "limit": 500}).json()["items"] if x["student_id"] == SA), None)
pwj, chrome, node = os.environ.get("PW"), os.environ.get("CHROME"), shutil.which("node")
if node: ok(subprocess.run([node, "--check", str(ROOT / "static" / "ortda.js")], capture_output=True).returncode == 0 and subprocess.run([node, "--check", str(ROOT / "tools" / "lrs_e2e_check.js")], capture_output=True).returncode == 0,
            "node --check static/ortda.js, tools/lrs_e2e_check.js")
browser = bool(pwj and chrome and node)
if browser:
    out = os.environ.get("OUT") or tempfile.mkdtemp(prefix="lrs-e2e-")
    env = dict(os.environ, B=B, OUT=out, LAUNCH=lk["url"], ADMIN_UID=str(uid("masofaviy")), ADMIN_PW=PW, COURSE=KR, STUDENT=stu["full_name"])
    rr = subprocess.run([node, str(ROOT / "tools" / "lrs_e2e_check.js")], cwd=ROOT, env=env, capture_output=True, text=True, timeout=600)
    for ln in (rr.stdout + rr.stderr).splitlines():
        s = ln.strip()
        if s.startswith("✓"): ok(True, "[brauzer] " + s[1:].strip())
        elif s.startswith("✗"): ok(False, "[brauzer] " + s[1:].strip())
    ok(rr.returncode == 0, f"tools/lrs_e2e_check.js chiqish kodi 0 ({rr.returncode})" + ("" if rr.returncode == 0 else ":\n" + "\n".join((rr.stdout + rr.stderr).splitlines()[-15:])))
    print("    skrinshotlar:", out)
else:
    print("  – PW/CHROME berilmagan — brauzer o'rniga pleyer statementlari HTTP orqali yuboriladi")
    tok = L.parse_auth(qp["auth"]); actor = json.loads(qp["actor"]); reg = qp["registration"]
    qlu = q("SELECT uid FROM ku_lessons WHERE id=?", (lq,))[0]["uid"]; qb = q("SELECT uid FROM ku_blocks WHERE lesson_id=? ORDER BY pos LIMIT 1", (lq,))[0]["uid"]
    base_act = f"https://isft.uz/xapi/kurs/{kc}"
    mk = lambda verb, act_, **k: {"id": str(uuid.uuid4()), "actor": actor, "verb": {"id": "http://adlnet.gov/expapi/verbs/" + verb, "display": {"en-US": verb}},
                                  "object": {"objectType": "Activity", "id": act_, **({"definition": k.pop("definition")} if "definition" in k else {})},
                                  "timestamp": dt.datetime.now(dt.timezone.utc).isoformat(), "context": {"registration": reg}, **k}
    rr = lrs_post_as_player(qp["auth"], actor, reg, [mk("initialized", base_act),
        mk("answered", f"{base_act}/lesson/{qlu}/q/{qb}", result={"success": False, "response": "b"},
           definition={"type": "http://adlnet.gov/expapi/activities/cmi.interaction", "interactionType": "choice", "name": {"uz": "Narx oshsa talab nima bo'ladi?"},
                       "choices": [{"id": "a", "description": {"uz": "Kamayadi"}}, {"id": "b", "description": {"uz": "Oshadi"}}], "correctResponsesPattern": ["a"]}),
        mk("failed", f"{base_act}/lesson/{qlu}", result={"success": False, "score": {"scaled": 0.5, "raw": 50, "min": 0, "max": 100}, "completion": True})])
    ok(rr.status_code == 200, "Pleyer statementlari (initialized, answered, failed) qabul qilindi")
st_rows = q("SELECT verb, lesson_ref, item_ref, success, response FROM lrs_statements WHERE student_id=? AND course_ref=? AND voided=0", (SA, KR))
verbs = [r["verb"] for r in st_rows]
ok("answered" in verbs and ("failed" in verbs or "passed" in verbs) and "initialized" in verbs, f"Statementlar bazada: {sorted(set(verbs))}")
ans_row = next(r for r in st_rows if r["verb"] == "answered")
ok(ans_row["response"] and ans_row["success"] in (0, 1) and (ans_row["item_ref"] or "").startswith("q/"), f"answered: javob «{ans_row['response']}», natija, savol yo'li")
after_row = next((x for x in head.get(O + "/list", params={"course": KR, "only_risk": "false", "limit": 500}).json()["items"] if x["student_id"] == SA), None)
ok(before_row and any(r["code"] == "boshlamagan" for r in before_row["reasons"]) and after_row and not any(r["code"] == "boshlamagan" for r in after_row["reasons"])
   and after_row["last"] and after_row["days_inactive"] == 0, "Ekran yangilandi: «umuman boshlamagan» → faollik bugun")
sdk = head.get(f"{O}/student/{SA}", params={"course": KR}).json()
qrow = next(x for x in sdk["lessons"] if x["title"] == "Yakuniy test")
ok(qrow["attempts"] >= 1 and qrow["status"] in ("otmadi", "otdi"), f"Talaba darslari: test — {qrow['status_label']}, {qrow['attempts']} urinish")
qk = head.get(O + "/questions", params={"ref": KR}).json()
link = next((x["link"] for x in qk["items"] if x["link"]), None)
ok(qk["items"] and link and link["view"] == "kurs" and link["cid"] == kc and link["lid"] == lq and link["block"], f"Kurs muharriri savoli: tahlil va blokka havola ({link})")
ok(q("SELECT COUNT(*) n FROM audit_log WHERE resource='lrs' AND allowed=1 AND action LIKE 'ortda qolganlar:%'")[0]["n"] > 5 and q("SELECT COUNT(*) n FROM audit_log WHERE resource='lrs' AND allowed=0 AND action LIKE 'ortda qolganlar:%'")[0]["n"] > 5,
   "Ruxsat berilgan va rad etilgan so'rovlar audit jurnalida")

print()
if fails:
    print(f"XATO: {len(fails)} ta tekshiruv o'tmadi"); sys.exit(1)
print("Hammasi o'tdi")
