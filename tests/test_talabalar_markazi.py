import os
"""Talabalar markazi: API + qoidalar dvigateli testlari (jonli server :8000, sun'iy ma'lumot)."""
import httpx, sys, sqlite3, datetime as dt, base64, io, json
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT)); from app import clock as CLK   # noqa: E402 — institut vaqti (ISFT_CORE_TZ / ISFT_CORE_FAKE_TODAY), server bilan bir xil
sys.path.insert(0, str(ROOT))
from app import db as DB, student_ops as OPS, academic_rules as AR
B = os.environ.get("ISFT_TEST_URL", "http://127.0.0.1:8000"); DBP = str(Path(os.environ.get("ISFT_CORE_DB") or ROOT / "data" / "jarvis.db"))
def S(uid):
    c = httpx.Client(base_url=B, timeout=120); assert c.post("/api/login", json={"user_id": uid, "password": "Isft2026"}).status_code == 200; return c
fails = 0
def ok(cond, msg):
    global fails
    print(("✓ " if cond else "✗ XATO: ") + msg); fails += (not cond)
q = lambda sql, a=(): sqlite3.connect(DBP).execute(sql, a).fetchall()
reg, cc, ty2, ty1, rek, pro, bux = S(17), S(23), S(24), S(25), S(2), S(3), S(11)
# institutda dekan lavozimi yo'q (Yevropa modeli): sobiq dekan akkaunti (#13) kira olmaydi, fakultet ko'lami — tyutorda, to'liq — Registratorda
ok(httpx.post(B + "/api/login", json={"user_id": 13, "password": "Isft2026"}).status_code == 403, "Sobiq dekan (#13): kirish rad etildi (lavozim bekor qilingan)")

# --- ruxsatlar ---
ok(rek.get("/api/ops/summary").status_code == 200, "Rektor: jamlangan holat ochiladi")
ok(rek.get("/api/ops/cases").status_code == 403, "Rektor: individual ro'yxat yopiq (faqat jamlangan)")
bs = bux.get("/api/ops/summary"); ok(bs.status_code == 200 and {r["rule"] for r in bs.json()["by_rule"]} <= {"kontrakt"}, "Buxgalteriya: faqat kontrakt holatlari")
bc = bux.get("/api/ops/cases").json(); ok(bc and all(x["rule"] == "kontrakt" for x in bc), "Buxgalteriya: holatlar ro'yxatida faqat kontrakt")
bk = bux.get(f"/api/ops/student/{bc[0]['student_id']}").json(); ok(not bk["facts"] and not bk["absences"] and all(x["rule"] == "kontrakt" for x in bk["cases"]), "Buxgalteriya: talaba kartasida baho va davomat yo'q")
ok(bux.get("/api/ops/retakes").status_code == 403, "Buxgalteriya: otrabotkalar yopiq")
ok(cc.get("/api/ops/cases").status_code == 403, "Call-markaz: holatlar ro'yxati yopiq")
ct = cc.get("/api/ops/tasks").json(); ok(ct and all(t["kind"] == "qongiroq" for t in ct), f"Call-markaz navbati: faqat qo'ng'iroqlar ({len(ct)})")
ok(all("*" not in (t["phone"] or "") for t in ct), "Call-markaz telefonni to'liq ko'radi")
dc = ty2.get("/api/ops/cases").json(); ok(dc and all(c["faculty"] == "Xalqaro iqtisodiyot va moliya" for c in dc), f"Tyutor: holatlar — faqat o'z fakulteti ({len(dc)})")
# 15. tyutorlar: ~10 kunduzgi guruhga bitta; navbatda faqat o'z guruhlari talabalari
tg24 = {g for (g,) in q("SELECT group_id FROM tutor_groups WHERE user_id=24")}
ntut, ngr = q("SELECT COUNT(DISTINCT user_id), COUNT(*) FROM tutor_groups")[0]
nkun = q("SELECT COUNT(*) FROM groups_ WHERE form='kunduzgi'")[0][0]
ok(ngr == nkun and 8 <= ngr / ntut <= 12 and {24, 25, 26} <= {u for (u,) in q("SELECT DISTINCT user_id FROM tutor_groups")},
   f"Tyutorlar: {ntut} nafar, {nkun} kunduzgi guruh (~{round(ngr / ntut, 1)} guruhdan); 24–26 ham ro'yxatda")
ok(all(r[0] == "tyutor" for r in q("SELECT u.role FROM tutor_groups t JOIN users u ON u.id=t.user_id")), "Biriktirmada faqat tyutor akkauntlari")
gid_of = lambda sid: q("SELECT group_id FROM students WHERE id=?", (sid,))[0][0]
ok(all(gid_of(c["student_id"]) in tg24 for c in dc), "Tyutor (24): holatlar — faqat o'ziga biriktirilgan guruhlar talabalari")
_tut = {r[0] for r in q("SELECT DISTINCT user_id FROM tutor_groups")}
ok(all(u.get("search_only") for u in httpx.get(B + "/api/users").json() if u["id"] in _tut),
   "Tyutorlar kirish ro'yxatining bo'limlarida ko'rsatilmaydi — faqat qidiruvda (search_only)")
ok(all(reg.get(f"/api/ops/cases?faculty={f}").json() for f in (1, 2, 3)), "Registrator ofisi: uchala fakultet holatlari (fakultet darajasidagi ko'rinish)")
t2 = ty2.get("/api/ops/tasks").json(); ok(t2 and all(t["assignee_role"] == "tyutor" and gid_of(t["student_id"]) in tg24 for t in t2), f"Tyutor navbati: faqat o'z guruhlari talabalari ({len(t2)})")
ok(not q("""SELECT 1 FROM ops_tasks t JOIN students s ON s.id=t.student_id WHERE t.assignee_role='tyutor' AND t.status='yangi'
            AND s.study_form!='kunduzgi' LIMIT 1"""), "Sirtqi/masofaviy talabaning tyutor ishi — Sirtqi bo'lim / Registrator ofisida (tyutorga tushmaydi)")
ok(pro.get("/api/ops/cases").status_code == 200, "O'quv prorektori: to'liq ko'rinish")
sc = ct[0]["script"]; ok(sc["say"] and "o'ylab topilmaydi" in sc["basis"][0], "Skript: faktlar bor, me'yoriy havola o'ylab topilmagan")

# --- idempotentlik ---
con = DB.connect()
OPS.evaluate(con)   # oldingi testlar ma'lumotni o'zgartirgan bo'lishi mumkin — avval bir marta, so'ng idempotentlik
st = OPS.evaluate(con); ok(st["opened"] == 0 and st["tasks"] == 0, f"Dvigatel qayta ishga tushdi: yangi holat/topshiriq yo'q {st}")
dup = q("SELECT COUNT(*) FROM (SELECT case_id, kind FROM ops_tasks WHERE status='yangi' GROUP BY case_id, kind HAVING COUNT(*)>1)")[0][0]
ok(dup == 0, "Bitta holat+tur bo'yicha ochiq topshiriq dublikati yo'q")

# --- call-markaz: va'da → muddat o'tsa qayta qo'ng'iroq ---
kt = dict(zip(("id", "case_id"), q("""SELECT t.id, t.case_id FROM ops_tasks t JOIN ops_cases oc ON oc.id=t.case_id WHERE t.status='yangi' AND t.assignee_role='call_center'
                                     AND oc.rule='kontrakt' AND CAST(json_extract(oc.facts,'$.days') AS INT) < 0 ORDER BY t.id LIMIT 1""")[0]))   # muddati o'tgan (daraja o'zgarmaydi)
r = cc.post(f"/api/ops/tasks/{kt['id']}/outcome", json={"outcome": "vada", "promise_date": "2020-01-01"}); ok(r.status_code == 400, "Va'da sanasi o'tmishda bo'lsa — rad")
pd = (CLK.today() + dt.timedelta(days=2)).isoformat()
ok(cc.post(f"/api/ops/tasks/{kt['id']}/outcome", json={"outcome": "vada", "promise_date": pd, "note": "oylik tushgach to'layman"}).json()["ok"], "Va'da berdi (2 kun)")
ok(cc.post(f"/api/ops/tasks/{kt['id']}/outcome", json={"outcome": "gaplashildi"}).status_code == 409, "Yopilgan topshiriqqa qayta natija — 409")
st = OPS.evaluate(con, today=CLK.today() + dt.timedelta(days=3))
fu = q("SELECT COUNT(*) FROM ops_tasks WHERE case_id=? AND status='yangi' AND title LIKE 'Va''da muddati%'", (kt["case_id"],))[0][0]
ok(fu == 1, f"Va'da muddati o'tgach qayta qo'ng'iroq yaratildi (followups={st['followups']})")
OPS.evaluate(con, today=CLK.today() + dt.timedelta(days=3))
ok(q("SELECT COUNT(*) FROM ops_tasks WHERE case_id=? AND status='yangi' AND kind='qongiroq'", (kt["case_id"],))[0][0] == 1, "Qayta ishga tushirish follow-up dublikatini yaratmadi")

# --- javob bermadi x3 → tyutor ---
t = cc.get("/api/ops/tasks?rule=davomat").json()[0]
for i in range(1, 4):
    r = cc.post(f"/api/ops/tasks/{t['id']}/outcome", json={"outcome": "javob_bermadi"}).json()
ok(r.get("escalated"), "3 marta javob bermadi → tyutorga topshiriq")
ok(q("SELECT assignee_role FROM ops_tasks WHERE id=?", (r["escalated"],))[0][0] == "tyutor", "Yangi topshiriq tyutorda")

# --- tyutor: boshqa fakultet topshirig'iga tegolmaydi; hujjat keldi → holat yopiladi ---
t1 = ty1.get("/api/ops/tasks").json()[0]
ok(ty2.post(f"/api/ops/tasks/{t1['id']}/outcome", json={"outcome": "bajarildi"}).status_code == 403, "Tyutor boshqa fakultet topshirig'iga ruxsatsiz (403)")
ht = ty2.get("/api/ops/tasks?kind=hujjat").json()[0]
sid = ht["student_id"]
before = OPS.student_facts(con, sid)
ok(ty2.post(f"/api/ops/tasks/{ht['id']}/outcome", json={"outcome": "hujjat_keldi", "note": "kasallik varaqasi olindi"}).json()["ok"], "Tyutor: hujjat keldi")
ok(q("SELECT status FROM ops_cases WHERE id=?", (ht["case_id"],))[0][0] == "yopildi", "Hujjat holati avtomatik yopildi")
ok(OPS.student_facts(con, sid)["unexcused"] <= before["unexcused"], "Sababsiz soatlar oshmadi (hujjat tasdiqlandi)")

# --- registrator: xat va hayfsan hujjatlari ---
rt = reg.get("/api/ops/tasks?kind=xat").json() + reg.get("/api/ops/tasks?kind=buyruq").json()
xt = reg.get("/api/ops/tasks?rule=davomat&kind=xat").json()[0]
r = reg.post(f"/api/ops/tasks/{xt['id']}/document", json={}).json(); ok(r["reg_no"].startswith("OX-"), f"Davomat ogohlantirish xati: {r['reg_no']}")
kx = next((t for t in rt if t["kind"] == "xat" and t["rule"] == "kontrakt"), None)
if kx: r = reg.post(f"/api/ops/tasks/{kx['id']}/document", json={}).json(); ok(r["reg_no"].startswith("QX-"), f"Kontrakt: ota-onaga xat {r['reg_no']}")
bt = next(iter(reg.get("/api/ops/tasks?rule=davomat&kind=buyruq").json()), None)
if bt:   # hayfsan — buyruq: «Buyruqlar» modulida loyiha (rektor imzolaydi), imzolangach hayfsan «amalda»
    r = reg.post(f"/api/ops/tasks/{bt['id']}/document", json={}).json(); ok(r.get("order_id") and r["reg_no"] == f"BUYRUQ#{r['order_id']}" and r["status"] == "loyiha", f"Hayfsan buyrug'i loyihasi Buyruqlar bo'limida: {r['reg_no']}")
    ok(q("SELECT kind, status FROM orders WHERE id=?", (r["order_id"],)) == [("hayfsan", "loyiha")], "Buyruq turi — «hayfsan», holati — loyiha")
    ok(q("SELECT status FROM discipline WHERE doc_reg=?", (r["reg_no"],)) == [("loyiha",)], "11. Hayfsan qayd etildi (discipline: loyiha)")
    ok(reg.post(f"/api/orders/{r['order_id']}/submit").status_code == 200 and rek.post(f"/api/orders/{r['order_id']}/sign").status_code == 200, "Buyruq imzoga yuborildi va rektor imzoladi")
    OPS.sync_discipline(con)
    ok(q("SELECT status FROM discipline WHERE doc_reg=?", (r["reg_no"],)) == [("amalda",)], "11. Rektor buyruqni imzoladi → hayfsan «amalda»")
    ok(reg.get(f"/api/registrar/discipline?student_id={bt['student_id']}").json()["rows"][0]["status"] == "amalda", "11. Hayfsan ma'lumoti API orqali ochiq (/api/registrar/discipline)")
ok(cc.post(f"/api/ops/tasks/{xt['id']}/document", json={}).status_code in (403, 409), "Call-markaz hujjat chiqara olmaydi")

# --- kontrakt to'landi → holat yopiladi ---
kc = q("SELECT id, student_id FROM ops_cases WHERE rule='kontrakt' AND status='ochiq' LIMIT 1")[0]
con.execute("UPDATE students SET paid_amount=contract_amount WHERE id=?", (kc[1],)); con.commit()
OPS.evaluate(con)
ok(q("SELECT status, close_reason FROM ops_cases WHERE id=?", (kc[0],))[0][0] == "yopildi", "To'lov qilindi → kontrakt holati yopildi, ochiq topshiriqlar bekor")
ok(q("SELECT COUNT(*) FROM ops_tasks WHERE case_id=? AND status='yangi'", (kc[0],))[0][0] == 0, "Yopilgan holatda ochiq topshiriq qolmadi")

# --- otrabotka: o'tgan semestr qarzi (o'sha semestr yozuvi), baholar tarixi, pasaytirmaslik ---
open_rt = {(r[0], r[1]) for r in q("SELECT student_id, subject FROM retakes WHERE status IN ('berildi','topshirildi')")}
sid, subj, fsem = next((c["student_id"], f["subject"], f["semester"]) for c in ty2.get("/api/ops/cases?rule=akademik").json()
                       for f in c["facts"]["fails"] if (c["student_id"], f["subject"]) not in open_rt)
ok(fsem < AR.CURRENT_SEMESTER, f"2. Qarz — yakunlangan semestrdan ({AR.SEMESTER_SHORT[fsem]})")
r = ty2.post("/api/ops/retakes", json={"student_id": sid, "subject": subj}).json(); ok(r["reg_no"].startswith("OV-") and r["kind"] == "qarz" and r["semester"] == fsem, f"Tyutor otrabotka varaqasi berdi: {r['reg_no']} (qarz, {r['semester']})")
rid = r["id"]
ok(ty2.post("/api/ops/retakes", json={"student_id": sid, "subject": subj}).status_code == 409, "Shu fan bo'yicha ikkinchi ochiq otrabotka — 409")
ok(ty1.post("/api/ops/retakes", json={"student_id": sid, "subject": subj}).status_code == 403, "Boshqa tyutor (boshqa guruhlar) bera olmaydi")
bad = "data:image/png;base64," + base64.b64encode(b"%PDF-1.4 fake").decode()
ok(ty2.post(f"/api/ops/retakes/{rid}/upload", json={"data_url": bad}).status_code == 400, "Mazmuni turiga mos bo'lmagan fayl rad etildi")
from PIL import Image; buf = io.BytesIO(); Image.new("RGB", (40, 40), "white").save(buf, "PNG")
png = "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()
ok(ty2.post(f"/api/ops/retakes/{rid}/upload", json={"data_url": png}).json()["ok"], "Skan yuklandi")
ok(ty2.post(f"/api/ops/retakes/{rid}/approve", json={"score": 71}).status_code == 403, "Tyutor bahoni tasdiqlay olmaydi")
ok(reg.get(f"/api/ops/retakes/{rid}/file").status_code == 200, "Registrator skanni ko'radi")
old = q("SELECT score FROM grades WHERE student_id=? AND subject=? AND semester=?", (sid, subj, fsem))[0][0]
ok(reg.post(f"/api/ops/retakes/{rid}/approve", json={"score": 71}).json()["ok"], "Registrator tasdiqladi")
ok(q("SELECT score FROM grades WHERE student_id=? AND subject=? AND semester=?", (sid, subj, fsem))[0][0] == 71, "2. O'sha semestr yozuvi yangilandi (71)")
hist = q("SELECT attempt, kind, score, counted FROM grade_attempts WHERE student_id=? AND subject=? AND semester=? ORDER BY attempt", (sid, subj, fsem))
ok(len(hist) >= 2 and hist[0][1] in ("asosiy",) and hist[0][2] <= old and hist[-1][2] == 71 and hist[-1][3] == 1 and sum(h[3] for h in hist) == 1,
   f"9. Baholar tarixi: asl urinish + otrabotka, hisobda faqat bittasi {hist}")
ok(not any(f["subject"] == subj and f["semester"] == fsem for f in OPS.student_facts(con, sid)["fails"]), "2. Qarz yopildi (akademik qarzlar ro'yxatidan chiqdi)")
ok(reg.post(f"/api/ops/retakes/{rid}/approve", json={"score": 90}).status_code == 409, "Qayta tasdiqlash — 409")
ok(any(a[0] == "baho o'zgartirildi (otrabotka)" for a in q("SELECT action FROM audit_log ORDER BY id DESC LIMIT 20")), "Baho o'zgarishi audit jurnalida")
mt = q(f"SELECT gpa FROM students WHERE id=?", (sid,))[0][0]
exp = q(f"SELECT {AR.ratio2_sql('SUM(score)', 'COUNT(*)')} FROM grades WHERE student_id=? AND semester=? AND score IS NOT NULL", (sid, AR.RATING_SEMESTER))[0][0]
ok(mt == exp, f"5. students.gpa qayta hisoblandi va baholardan hisoblangan qiymatga teng ({mt})")
# 9. pasaytirmaslik: past natija hisobga olinmaydi
cand = next(((c["student_id"], f["subject"], f["semester"], f["score"]) for c in reg.get("/api/ops/cases?rule=akademik").json()
             for f in c["facts"]["fails"] if f["score"] >= 10 and (c["student_id"], f["subject"]) not in open_rt and c["student_id"] != sid), None)
if cand:
    s2, sb2, se2, sc2 = cand
    r2 = reg.post("/api/ops/retakes", json={"student_id": s2, "subject": sb2}).json()
    reg.post(f"/api/ops/retakes/{r2['id']}/upload", json={"data_url": png})
    j = reg.post(f"/api/ops/retakes/{r2['id']}/approve", json={"score": sc2 - 5}).json()
    ok(j["ok"] and j["result"]["counted"] is False and q("SELECT score FROM grades WHERE student_id=? AND subject=? AND semester=?", (s2, sb2, se2))[0][0] == sc2,
       f"9. Pastroq natija ({sc2 - 5} < {sc2}) bahoni pasaytirmadi; urinish tarixda (hisobga olinmagan)")
# 9/10. «dars» otrabotkasi: qoldirilgan dars yopiladi, baho o'zgarmaydi
dsid = next((r[0] for r in q(f"""SELECT a.student_id FROM absences a JOIN students s ON s.id=a.student_id WHERE a.semester={AR.CURRENT_SEMESTER}
              AND a.reason='sababsiz' AND a.cleared_by IS NULL AND s.status='faol' AND s.study_form='kunduzgi'
              AND NOT EXISTS (SELECT 1 FROM grades g WHERE g.student_id=s.id AND g.semester={AR.CURRENT_SEMESTER} AND COALESCE(g.oraliq,0)<12)
              AND NOT EXISTS (SELECT 1 FROM grades g WHERE g.student_id=s.id AND g.semester<{AR.CURRENT_SEMESTER} AND g.score<40) LIMIT 1""")), None)
if dsid:
    dsub, dor = q("SELECT subject, oraliq FROM grades WHERE student_id=? AND semester=? ORDER BY subject LIMIT 1", (dsid, AR.CURRENT_SEMESTER))[0]
    u0 = OPS.student_facts(con, dsid)["unexcused"]
    r3 = reg.post("/api/ops/retakes", json={"student_id": dsid, "subject": dsub}).json()
    ok(r3.get("kind") == "dars", f"Qarz va past oraliq yo'q, sababsiz dars bor → «dars» otrabotkasi ({r3.get('reg_no')})")
    reg.post(f"/api/ops/retakes/{r3['id']}/upload", json={"data_url": png})
    j = reg.post(f"/api/ops/retakes/{r3['id']}/approve", json={}).json()
    ok(j["ok"] and q("SELECT oraliq FROM grades WHERE student_id=? AND subject=? AND semester=?", (dsid, dsub, AR.CURRENT_SEMESTER))[0][0] == dor
       and OPS.student_facts(con, dsid)["unexcused"] < u0, f"9. Qoldirilgan dars yopildi ({u0} → {OPS.student_facts(con, dsid)['unexcused']} soat), baho o'zgarmadi")

# --- bo'sh ruxsatlar ---
cc_q = {r[0] for r in q("SELECT student_id FROM ops_tasks WHERE assignee_role='call_center'")}
other = next(r[0] for r in q("SELECT id FROM students ORDER BY id") if r[0] not in cc_q)
ok(cc.get(f"/api/ops/student/{other}").status_code == 403, "Call-markaz o'z navbatida yo'q talaba kartasini ocholmaydi")
ccs = cc.get(f"/api/ops/student/{ct[1]['student_id']}").json(); ok(ccs.get("limited") and not ccs["absences"] and "grades" not in json.dumps(ccs), "Call-markaz kartasi: minimal ma'lumot")
# --- 1, 8, 10, 12, 14: akademik model va davomat chegaralari ---
cur = AR.CURRENT_SEMESTER
ok(q(f"SELECT COUNT(*) FROM grades WHERE semester={cur} AND score IS NOT NULL")[0][0] == 0 and q(f"SELECT COUNT(*) FROM grades WHERE semester={cur} AND oraliq IS NOT NULL")[0][0] > 0,
   "1. Joriy semestr: faqat oraliq nazorat bali (yakuniy hali yo'q)")
ok(q(f"SELECT COUNT(*) FROM grades WHERE semester<{cur} AND (score IS NULL OR oraliq IS NULL)")[0][0] == 0
   and q(f"SELECT COUNT(*) FROM grades WHERE semester<{cur} AND yakuniy IS NOT NULL AND oraliq + yakuniy != score")[0][0] == 0,
   "1. Yakunlangan semestrlar: hisobdagi ball = oraliq + yakuniy (yoki faqat oraliq — yakuniyga kiritilmagan)")
ok(q("""SELECT COUNT(*) FROM grades g JOIN students s ON s.id=g.student_id JOIN student_leaves l ON l.student_id=s.id
        WHERE s.status="akademik ta'til" AND g.semester=1""")[0][0] == 0 and
   q("""SELECT COUNT(*) FROM students WHERE status="akademik ta'til" AND attendance IS NOT NULL""")[0][0] == 0 and
   q("""SELECT COUNT(*) FROM absences a JOIN students s ON s.id=a.student_id WHERE s.status="akademik ta'til" AND a.semester=1""")[0][0] == 0,
   "8. Akademik ta'tildagilar: joriy semestr baholari, davomati va dars qoldirishlari yo'q")
lv = q("""SELECT l.start, l.end, (SELECT GROUP_CONCAT(DISTINCT g.semester) FROM grades g WHERE g.student_id=l.student_id) FROM student_leaves l""")
def overl(a, b, t): t0, t1 = AR.term_dates(t); return a <= t1 and b >= t0
ok(all(not any(overl(a, b, int(t)) for t in (sems or "").split(",") if t) for a, b, sems in lv), f"8. Ta'til davri bilan kesishgan semestrlarda baho yo'q ({len(lv)} ta ta'til)")
s0 = q(f"SELECT a.student_id, SUM(a.hours) FROM absences a WHERE a.semester={cur - 1} GROUP BY a.student_id LIMIT 1")
if s0:
    f0 = OPS.student_facts(con, s0[0][0]); cur_h = q(f"SELECT COALESCE(SUM(hours),0) FROM absences WHERE student_id=? AND semester={cur}", (s0[0][0],))[0][0]
    ok(f0["unexcused"] + f0["excused"] == cur_h, f"10. O'tgan semestr qoldirishlari ({s0[0][1]} soat) joriy semestr chegaralariga kirmaydi")
ok(q("""SELECT COUNT(*) FROM absences a JOIN students s ON s.id=a.student_id WHERE COALESCE(s.study_form,'kunduzgi')!='sirtqi'
        AND a.reason IN ('komandirovka','mehnat_tatili')""")[0][0] == 0, "14. Kunduzgi talabada «komandirovka»/«mehnat ta'tili» sababi yo'q")
ok(q("SELECT COUNT(*) FROM absences a JOIN students s ON s.id=a.student_id WHERE s.study_form='sirtqi' AND a.reason='sababsiz'")[0][0] > 0,
   "12. Sirtqi: sababsiz qoldirishlar ham qayd etiladi (sessiya davomati)")
P = OPS.policy(con)
bad_att = q(f"""SELECT COUNT(*) FROM students s WHERE s.status='faol' AND s.study_form IN ('kunduzgi','sirtqi') AND ABS(s.attendance -
               ROUND(100.0 * ((CASE s.study_form WHEN 'sirtqi' THEN {int(P['session_hours'])} ELSE {int(P['hours_to_date'])} END) -
               COALESCE((SELECT SUM(a.hours) FROM absences a WHERE a.student_id=s.id AND a.semester={cur}), 0)) /
               (CASE s.study_form WHEN 'sirtqi' THEN {int(P['session_hours'])} ELSE {int(P['hours_to_date'])} END), 1)) > 0.11""")[0][0]
ok(bad_att == 0, "12. Davomat foizi (kunduzgi va sirtqi) — joriy semestr dars qoldirishlaridan hisoblangan (bir manba)")
sq = q("SELECT oc.student_id FROM ops_cases oc JOIN students s ON s.id=oc.student_id WHERE oc.rule='davomat' AND s.study_form='sirtqi' AND oc.status='ochiq' LIMIT 1")
ok(bool(sq), "12. Davomat qoidalari sirtqi talabalarga ham ishlaydi")
ok(OPS.adult({"study_form": "sirtqi"}) and OPS.adult({"study_form": "kunduzgi", "level": "magistr"}) and not OPS.adult({"study_form": "kunduzgi", "level": "bakalavr"}),
   "13. Ota-onaga xat faqat kunduzgi bakalavrga (sirtqi/masofaviy/magistr — talabaning o'ziga)")
ok(not q("""SELECT 1 FROM ops_tasks t JOIN students s ON s.id=t.student_id WHERE t.title LIKE 'Ota-onaga%' AND (s.study_form!='kunduzgi' OR s.level='magistr') LIMIT 1"""),
   "13. Sirtqi/masofaviy/magistr talabalar uchun «Ota-onaga qarzdorlik xati» topshirig'i yo'q")
# =====================================================================================================
# NAVBAT v2: haqiqiy muddat, imkoniyat va muqobil yo'llar; ommaviy amallar; ko'lam; skript so'zlovchisi; agent «Nega?»
# =====================================================================================================
print("— Call-markaz navbati: haqiqiy muddat (SLA) va rejalashtirish —")
con.commit()
now_s, td = CLK.now().replace(microsecond=0).isoformat(), CLK.today().isoformat()
CALLQ = "SELECT t.id, t.due_at, t.planned_on, t.level, t.created_at, t.attempts, t.title, oc.rule, oc.facts FROM ops_tasks t JOIN ops_cases oc ON oc.id=t.case_id WHERE t.status='yangi' AND t.assignee_role='call_center'"
before = {r[0]: r[1] for r in q(CALLQ)}
OPS.schedule_calls(con); con.commit()
ok(before and before == {r[0]: r[1] for r in q(CALLQ)}, f"1. Rejalashtirish haqiqiy muddatni (due_at) o'zgartirmaydi ({len(before)} ta qo'ng'iroq)")
rows = q(CALLQ)
rem = [r for r in rows if r[7] == "kontrakt" and json.loads(r[8]).get("days", -1) >= 0]
ok(rem and all(r[1] <= json.loads(r[8])["due"] + "T18:00:00" for r in rem), f"1. Kontrakt eslatmasi muddati — to'lov sanasidan kech emas ({len(rem)} ta, masalan {rem[0][1] if rem else '—'})")
dav = [r for r in rows if r[7] == "davomat" and not r[5] and not r[6].startswith("Va'da")]
ok(dav and all(dt.datetime.fromisoformat(r[1]) - dt.datetime.fromisoformat(r[4]) == dt.timedelta(hours=24) for r in dav), f"1. Davomat 30+ soat: qo'ng'iroq muddati — 24 soat ({len(dav)} ta)")
cs = reg.get("/api/ops/summary").json()["calls"]
late_sql = q("SELECT COUNT(*) FROM ops_tasks WHERE status='yangi' AND assignee_role='call_center' AND due_at < ?", (CLK.now().replace(microsecond=0).isoformat(),))[0][0]
ok(abs(cs["late"] - late_sql) <= 2, f"1. «Kechikkan» — haqiqiy (muddati o'tgan) son: {cs['late']} (SQL: {late_sql})")
cap = cs["capacity"]
per_day = q("SELECT planned_on, COUNT(*) FROM ops_tasks WHERE status='yangi' AND assignee_role='call_center' GROUP BY planned_on")
ok(all(n <= cap for d, n in per_day if d), f"1. Har ish kuniga imkoniyatdan ortiq qo'ng'iroq rejalashtirilmagan (≤ {cap})")
ok(cs["shortfall_today"] == max(0, cs["due_today"] - cs["capacity_today"]) and
   (f"{cs['capacity_today']} ta imkoniyat" in cs["text"] and ("kechikadi" in cs["text"] or not cs["shortfall_today"])),
   f"1. Yetishmovchilik ochiq aytiladi: «{cs['text'][:140]}…»")
ok(cs["projected_late"] > 0 and cs["alternatives"]["sms"] > 0 and cs["alternatives"]["overflow"] > 0, f"1. Rejaga ko'ra kechikadigan {cs['projected_late']} ta; muqobil: SMS {cs['alternatives']['sms']}, taqsimlash {cs['alternatives']['overflow']}")
bk = lambda r: (max((r[1] or "9999")[:10], td), -(r[3] or 0))
today_b = [bk(r) for r in rows if r[2] == td]; later_b = [bk(r) for r in rows if r[2] and r[2] > td and not r[5]]
ok(not today_b or not later_b or max(today_b) <= min(later_b), "1. Ustuvorlik: avval muddati yaqin va jiddiyroq qo'ng'iroqlar (bugungi ro'yxat)")
ct2 = cc.get("/api/ops/tasks").json()
ok(all(t["late"] == (t["due_at"] < CLK.now().isoformat(timespec="seconds")) for t in ct2), "3. Kartada «kechikdi» faqat muddati haqiqatda o'tganlarda")
ok(cc.post("/api/ops/calls/operators", json={"items": [{"user_id": 23, "capacity": 100}]}).status_code == 403, "Operator me'yorini faqat Registrator ofisi boshlig'i o'zgartiradi")
r = reg.post("/api/ops/calls/operators", json={"items": [{"user_id": 23, "capacity": 100, "active": True}]}).json()
ok(r["summary"]["capacity"] == 100 and q("SELECT COUNT(*) FROM ops_tasks WHERE status='yangi' AND assignee_role='call_center' AND planned_on=?", (td,))[0][0] <= 100 + 4,
   "1. Operator me'yori sozlanadi (100) — navbat qayta rejalashtirildi")
# ikkinchi operator (test uchun vaqtinchalik akkaunt)
uid2 = con.execute("INSERT INTO users(full_name,role,pin) VALUES('Call-markaz operatori: Test Operator','call_center','x')").lastrowid; con.commit()
r = reg.post("/api/ops/calls/operators", json={"items": [{"user_id": 23, "capacity": 60}, {"user_id": uid2, "capacity": 40}]}).json()
own = q("SELECT assignee_user, COUNT(*) FROM ops_tasks WHERE status='yangi' AND assignee_role='call_center' AND planned_on=? GROUP BY 1", (td,))
ok(r["summary"]["operators"] == 2 and r["summary"]["capacity"] == 100 and {u for u, _ in own} == {23, uid2}, f"1. Bir nechta operator: imkoniyat 60 + 40, bugungi ro'yxat taqsimlandi {own}")
ok(all(t["assignee_user"] in (23, None) for t in cc.get("/api/ops/tasks").json()), "1. Operator (#23) faqat o'ziga taqsimlangan qo'ng'iroqlarni ko'radi")
con.execute("DELETE FROM call_operators WHERE user_id=?", (uid2,)); con.execute("DELETE FROM users WHERE id=?", (uid2,)); con.commit()
reg.post("/api/ops/calls/operators", json={"items": [{"user_id": 23, "capacity": 60}]})
ok(q("SELECT COUNT(*) FROM ops_tasks WHERE status='yangi' AND assignee_user=?", (uid2,))[0][0] == 0, "Vaqtinchalik operator olib tashlandi — navbat qayta taqsimlandi")

print("— Muqobil yo'llar: ommaviy SMS/Telegram, kechikadiganlarni taqsimlash —")
ok(cc.post("/api/ops/calls/notify", json={"preview": True}).status_code == 403, "Ommaviy SMS — faqat Registrator ofisi boshlig'i")
pv = reg.post("/api/ops/calls/notify", json={"channel": "sms", "preview": True}).json()
ok(pv["n"] == cs["alternatives"]["sms"] and "shlyuzi ulanmagan" in pv["gateway"] and pv["sample"], f"SMS ko'rib chiqish: {pv['n']} ta, namuna bor, shlyuz holati ochiq aytilgan")
tot0 = reg.get("/api/ops/summary").json()["calls"]["total"]
r = reg.post("/api/ops/calls/notify", json={"channel": "sms", "preview": False}).json()
ok(r["sent"] == pv["n"] - pv["no_phone"] and q("SELECT COUNT(*) FROM ops_notices WHERE channel='sms' AND status='navbatda'")[0][0] >= r["sent"]
   and r["summary"]["alternatives"]["sms"] == 0 and r["summary"]["total"] == tot0 - r["sent"], f"SMS: {r['sent']} ta eslatma chiqish navbatida, qo'ng'iroq navbati {tot0} → {r['summary']['total']}")
ok(q("SELECT COUNT(*) FROM ops_tasks WHERE outcome='sms' AND status='bajarildi'")[0][0] >= r["sent"] and
   not q("SELECT 1 FROM ops_cases oc JOIN ops_tasks t ON t.case_id=oc.id WHERE t.outcome='sms' AND oc.status!='ochiq' AND oc.rule='kontrakt' AND oc.closed_at IS NULL LIMIT 1"),
   "SMS: qo'ng'iroq topshirig'i yopildi, kontrakt holati ochiq qoladi (to'lanmasa — qayta qo'ng'iroq)")
pr = reg.post("/api/ops/calls/redistribute", json={"target": "tyutor", "preview": True}).json()
mv_due = {r_[0]: r_[1] for r_ in q(CALLQ)}
r = reg.post("/api/ops/calls/redistribute", json={"target": "tyutor", "preview": False}).json()
moved = q("""SELECT t.id, t.assignee_role, t.due_at, t.script, s.study_form, s.group_id FROM ops_tasks t JOIN students s ON s.id=t.student_id
             WHERE t.status='yangi' AND t.kind='qongiroq' AND t.note LIKE 'Call-markazdan o''tkazildi%'""")
ok(r["moved"] == pr["n"] > 0 and len(moved) >= r["moved"], f"Bir bosishda {r['moved']} ta kechikadigan qo'ng'iroq o'tkazildi: {r['by_role']}")
ok(all(m[2] == mv_due.get(m[0], m[2]) for m in moved), "Taqsimlashda muddat (SLA) o'zgarmadi")
ok(all((m[1] == "tyutor" and m[4] == "kunduzgi") or (m[1] == "sirtqi" and m[4] == "sirtqi") for m in moved if m[1] != "registrator_xodim"),
   "Kunduzgi — guruh tyutoriga, sirtqi — Sirtqi bo'limga")
# so'zlovchi: odatiy skriptda 1-qator (salomlashish), otrabotka eslatmasida 2-qator «(Qo'ng'iroq: guruh tyutori.)» — qaysi qo'ng'iroqlar
# navbatdan oshishi kun vaqtiga bog'liq, shuning uchun ikkala shakl ham tekshiriladi
spk = lambda m: " ".join(json.loads(m[3])["say"][:2])
ok(all("tyutori qo'ng'iroq" in spk(m) or "Qo'ng'iroq: guruh tyutori" in spk(m) for m in moved if m[1] == "tyutor") and
   all("Sirtqi bo'limidan" in spk(m) for m in moved if m[1] == "sirtqi"), "4. O'tkazilgan qo'ng'iroq skripti yangi so'zlovchi nomidan")
tq = ty2.get("/api/ops/tasks?kind=qongiroq").json()
ok(all(gid_of(t["student_id"]) in tg24 and t["can_act"] for t in tq), f"3. Tyutor (#24): o'tkazilgan qo'ng'iroqlar faqat o'z guruhlaridan ({len(tq)} ta), bajara oladi")
xo, sir = S(43), S(27)
r = reg.post("/api/ops/calls/redistribute", json={"target": "registrator_xodim", "preview": False}).json()
xq = xo.get("/api/ops/tasks?kind=qongiroq").json()
ok(r["moved"] > 0 and xq and all(t["assignee_role"] == "registrator_xodim" and t["can_act"] for t in xq), f"Registrator xodimiga {r['moved']} ta o'tkazildi — xodim navbatida, bajara oladi")

print("— 3. Ko'lam: kim nimani ko'radi —")
xt_all = xo.get("/api/ops/tasks?limit=500").json()
ok(xt_all and not any(t["assignee_role"] == "call_center" for t in xt_all) and not any(t["kind"] == "buyruq" for t in xt_all),
   f"Registrator xodimi «Mening navbatim»: call-markaz qo'ng'iroqlari va buyruq loyihalari yo'q ({len(xt_all)} ta)")
ok(not any(t["assignee_role"] == "call_center" for t in reg.get("/api/ops/tasks?limit=500").json()), "Registrator ofisi «Mening navbatim» (standart): call-markaz kartalari yo'q")
ok(reg.get("/api/ops/tasks?role=call_center").json() and all(t["assignee_role"] == "call_center" for t in reg.get("/api/ops/tasks?role=call_center").json()), "Registrator ofisi «Mas'ul» filtri bilan call-markaz navbatini ko'ra oladi")
sq_ = sir.get("/api/ops/tasks?limit=500").json()
ok(sq_ and all(t["assignee_role"] == "sirtqi" and t["study_form"] == "sirtqi" for t in sq_), f"Sirtqi bo'lim «Mening navbatim»: faqat o'z topshiriqlari, sirtqi talabalar ({len(sq_)})")
ccs_ = cc.get("/api/ops/summary").json()
ok(set(ccs_["rule_scope"]) == {"kontrakt", "davomat", "tatil", "otrabotka"} and not {r_["rule"] for r_ in ccs_["by_rule"]} - set(ccs_["rule_scope"]),
   f"Call-markaz: ko'lamdan tashqari qoida kartalari (O'zlashtirish, Hujjat) ko'rsatilmaydi — {ccs_['rule_scope']}")
ok(set(ty2.get("/api/ops/summary").json()["rule_scope"]) >= {"davomat", "akademik", "hujjat"}, "Tyutor: o'z qoidalari kartalari")

print("— 3. Filtrlar: kurs va guruh —")
fc = reg.get("/api/ops/tasks/facets").json()
c2 = fc["courses"][0]["course"]
rc = reg.get(f"/api/ops/tasks?course={c2}&limit=500").json()
ok(rc and all(t["course"] == c2 for t in rc), f"Kurs filtri: faqat {c2}-kurs ({len(rc)})")
g1 = fc["groups"][0]["name"]
rg_ = reg.get("/api/ops/tasks", params={"grp": g1, "limit": 500}).json()
ok(rg_ and all(t["grp"] == g1 for t in rg_) and len(rg_) == fc["groups"][0]["n"], f"Guruh filtri: {g1} — {len(rg_)} ta (facets bilan mos)")
ok(reg.get("/api/ops/cases", params={"course": c2}).json() and all(x["course"] == c2 for x in reg.get("/api/ops/cases", params={"course": c2}).json()), "Holatlar: kurs filtri")
lt = reg.get("/api/ops/tasks?late=1&role=all&limit=500").json()
ok(all(t["late"] for t in lt), f"«Faqat kechikkan» filtri: {len(lt)} ta, hammasi muddati o'tgan")

print("— 2. Ommaviy amallar —")
sel = [t["id"] for t in reg.get("/api/ops/tasks?kind=suhbat").json()[:3]]
ok(reg.post("/api/ops/tasks/bulk-outcome", json={"ids": sel, "note": ""}).status_code in (400, 422), "Tanlanganlarni belgilash: natija izohi majburiy")
r = reg.post("/api/ops/tasks/bulk-outcome", json={"ids": sel + [999999999], "note": "Guruh yig'ilishida gaplashildi"}).json()
ok(r["done"] == len(sel) and len(r["skipped"]) == 1 and all(x == ("bajarildi", "Guruh yig'ilishida gaplashildi") for x in q(f"SELECT status, note FROM ops_tasks WHERE id IN ({','.join(map(str, sel))})")),
   f"«Tanlanganlarni bajarildi deb belgilash»: {r['done']} ta, izoh bilan; noma'lum id o'tkazib yuborildi")
ok(cc.post("/api/ops/tasks/bulk-outcome", json={"ids": [t["id"] for t in reg.get("/api/ops/tasks?kind=xat").json()[:2]], "note": "test x"}).json()["done"] == 0, "Boshqa navbat topshirig'ini belgilab bo'lmaydi")
grp2 = q("""SELECT g.name FROM ops_tasks t JOIN ops_cases oc ON oc.id=t.case_id JOIN students s ON s.id=t.student_id JOIN groups_ g ON g.id=s.group_id
            WHERE t.status='yangi' AND t.kind='xat' AND t.assignee_role='talabalar' GROUP BY g.name
            HAVING SUM(oc.rule='kontrakt')>0 AND SUM(oc.rule!='kontrakt')>0 ORDER BY COUNT(*) LIMIT 1""")[0][0]
pv = reg.post("/api/ops/bulk/preview", json={"kind": "xat", "grp": grp2}).json()
ok(pv["n"] >= 2 and {p["key"] for p in pv["packets"]} == {"warn_letter", "debt_letter"} and pv["zip"] and pv["sample"], f"Ommaviy xatlar ko'rib chiqish ({grp2}): {[(p['key'], p['n']) for p in pv['packets']]}")
from app import documents as DOC
r = reg.post("/api/ops/bulk/run", json={"kind": "xat", "grp": grp2}).json()
ok(r["ok"] and r["n"] == pv["n"] and len(r["files"]) == 2 and all((DOC.OUT / f["file"]).exists() for f in r["files"]), f"Ommaviy: {r['n']} ta xat — 2 ta birlashtirilgan DOCX paket")
ok(all(q("SELECT COUNT(*) FROM documents WHERE file=?", (f["file"],))[0][0] == f["n"] for f in r["files"]), "Har bir xat hujjatlar reyestrida o'z ro'yxat raqami bilan")
ok(not reg.get("/api/ops/tasks", params={"grp": grp2, "kind": "xat"}).json() and
   all(x[0] and x[0][:3] in ("OX-", "QX-") for x in q("SELECT doc_reg FROM ops_tasks t JOIN students s ON s.id=t.student_id JOIN groups_ g ON g.id=s.group_id WHERE g.name=? AND t.kind='xat' AND t.status='bajarildi' AND t.outcome='bajarildi' AND t.done_at>=?", (grp2, td))),
   "Xat topshiriqlari yopildi va ro'yxat raqamiga bog'landi")
z = reg.get(f"/api/ops/bulk/{r['batch']}/zip")
import zipfile
ok(z.status_code == 200 and len(zipfile.ZipFile(io.BytesIO(z.content)).namelist()) == 2, f"ZIP: {r['zip']} (2 ta paket)")
ok(xo.get(f"/api/ops/bulk/{r['batch']}/zip").status_code == 403, "ZIP — tayyorlagan xodim yoki boshliq yuklab oladi")
ok(xo.post("/api/ops/bulk/run", json={"kind": "buyruq"}).status_code in (400, 403), "Buyruq loyihalari (ommaviy) — xodimga yo'q")
pb = reg.post("/api/ops/bulk/preview", json={"kind": "buyruq", "rule": "davomat"}).json()
if pb["n"]:
    nb = pb["n"]
    r = reg.post("/api/ops/bulk/run", json={"kind": "buyruq", "rule": "davomat"}).json()
    oid = r["orders"][0]["order_id"] if r.get("orders") else None
    ok(oid and len(r["orders"]) == 1 and q("SELECT kind, status FROM orders WHERE id=?", (oid,)) == [("hayfsan", "loyiha")]
       and q("SELECT COUNT(*) FROM order_students WHERE order_id=? AND version=(SELECT version FROM orders WHERE id=?)", (oid, oid))[0][0] == nb,
       f"Ommaviy hayfsan: BITTA buyruq loyihasi #{oid}, {nb} ta talaba ro'yxati bilan (Buyruqlar moduli)")
    ok(q("SELECT COUNT(*) FROM discipline WHERE doc_reg=? AND status='loyiha'", (f"BUYRUQ#{oid}",))[0][0] == nb, "Har talabaga hayfsan yozuvi (loyiha)")
pt = reg.post("/api/ops/bulk/preview", json={"kind": "buyruq", "rule": "tatil"}).json()
if pt["n"]:
    r = reg.post("/api/ops/bulk/run", json={"kind": "buyruq", "rule": "tatil"}).json()
    ok(len(r["orders"]) == 1 and q("SELECT kind FROM orders WHERE id=?", (r["orders"][0]["order_id"],)) == [("tatildan_qaytish",)], f"Ta'tildan qaytish: bitta buyruq loyihasi, {pt['n']} ta talaba")

print("— 4. Skript: so'zlovchi lavozim va ta'lim shakli bo'yicha —")
P = OPS.policy(con)
fk = {"hours": 34, "next": 48, "form": "kunduzgi"}
s_cc = OPS.script("davomat", "qongiroq", fk, {"full_name": "Ali Vali", "study_form": "kunduzgi"}, P, "call_center")["say"]
s_ty = OPS.script("davomat", "qongiroq", fk, {"full_name": "Ali Vali", "study_form": "kunduzgi"}, P, "tyutor")["say"]
s_si = OPS.script("davomat", "qongiroq", {**fk, "form": "sirtqi"}, {"full_name": "Ali Vali", "study_form": "sirtqi"}, P, "call_center")["say"]
s_ss = OPS.script("davomat", "qongiroq", {**fk, "form": "sirtqi"}, {"full_name": "Ali Vali", "study_form": "sirtqi"}, P, "sirtqi")["say"]
ok("call-markazidan" in s_cc[0] and "guruh tyutori bilan uchrashuv" in " ".join(s_cc), "Call-markaz (kunduzgi): «call-markazidan», uchrashuv — guruh tyutori bilan")
ok("tyutori qo'ng'iroq" in s_ty[0] and "tyutor bilan uchrashuv" not in " ".join(s_ty) and "Registrator ofisidan" not in " ".join(s_ty), "Tyutor: o'z nomidan, «tyutor bilan uchrashuv belgilang» demaydi")
ok("tyutor" not in " ".join(s_si).lower() and "Sirtqi bo'lim" in " ".join(s_si) and "xizmat safari" in " ".join(s_si), "Sirtqi talaba (call-markaz): tyutor emas — Sirtqi bo'lim; xizmat safari sababi")
ok("Sirtqi bo'limidan" in s_ss[0] and "Registrator ofisidan" not in " ".join(s_ss), "Sirtqi bo'lim: o'z nomidan gapiradi")
ok("xizmat safari" not in " ".join(s_cc) and "Kasallik yoki oilaviy" in " ".join(s_cc), "Kunduzgi: xizmat safari sababi aytilmaydi")
bad = q("""SELECT COUNT(*) FROM ops_tasks t JOIN students s ON s.id=t.student_id WHERE t.status='yangi' AND (
           (t.assignee_role='tyutor' AND t.script LIKE '%tyutor bilan uchrashuv%') OR
           (t.assignee_role IN ('tyutor','call_center','sirtqi') AND t.script LIKE '%Registrator ofisidan qo''ng''iroq%') OR
           (s.study_form='sirtqi' AND t.script LIKE '%guruh tyutori bilan%'))""")[0][0]
ok(bad == 0, "Bazadagi ochiq topshiriqlar skriptlarida noto'g'ri so'zlovchi yo'q")
ok(all("call-markazidan" in " ".join(t["script"]["say"]) and "Registrator ofisidan" not in " ".join(t["script"]["say"]) for t in cc.get("/api/ops/tasks").json() if not t["title"].startswith("Va'da")),
   "Call-markaz navbatidagi skriptlar: «ISFT institutining call-markazidan» (Registrator ofisi nomidan emas)")

print("— 6. Agent: «Nega?» — guruh/kurs/fakultet/fan turi kesimida, raqamlar manbaga mos —")
from app import ai, agent as AG
ctxr = rbac_ctx = __import__("app.rbac", fromlist=["ctx_for"]).ctx_for(con, 2)
va = ai.TOOLS["academic"][0](con, ctxr); pa = AG.an_academic(con, ctxr, va, True)
d = va.get("drivers") or {}
ok(d and d["by_course"] and d["categories"] and d["compare"].get("cohort"), f"academic_drivers: kurs ({len(d.get('by_course', []))}), fakultet ({len(d.get('by_faculty', []))}), fan turi ({len(d.get('categories', []))}) kesimlari bor")
why = "\n".join(pa["why"])
vv = AG.verify(why, json.dumps(va, ensure_ascii=False, default=str))
ok(len(pa["why"]) >= 4 and not vv["bad"], f"«Nega?» sabablari ({len(pa['why'])} ta): {vv['n']} ta raqam — barchasi manba ma'lumotida")
ok("O'tish ulushi" in why and "Kurs kesimida" in why and "Fan turlari" in why, "«Nega?»: o'tish ulushi, kurs va fan turi kesimlari")

print("\nNATIJA:", "HAMMASI O'TDI" if not fails else f"{fails} TA XATO")
sys.exit(1 if fails else 0)
