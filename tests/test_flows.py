import os
"""«Talaba harakati» (app/academic_flows.py): uchidan-uchigacha HTTP testlar (server ishlab turishi kerak).

Ishga tushirish:  ISFT_TEST_URL=http://127.0.0.1:8000 ISFT_CORE_DB=data/jarvis.db .venv/bin/python tests/test_flows.py
Test bazani o'zgartiradi (apellyatsiya qarori, qayta o'qish qarorlari, buyruq loyihalari, grant komissiyasi, bitirish) — demo holatini
tiklash uchun keyin `python -m app.seed`. Imzolangan test buyruqlari tuzatuvchi («bekor qilish») buyruq bilan qaytariladi.
Qamrov: 6 oqim (sessiya jadvali va to'qnashuvlar, apellyatsiya komissiyasi, qayta o'qish / kursda qoldirish / chetlashtirish, ko'chirish va
farq fanlari, ISFT granti, bitiruv va diplom) + lavozimlar ko'lami (17, 18, 8, 31, 27, 11, 2; 23 → 403).
"""
import datetime as dt, io, json, sqlite3, sys, time, zipfile
from pathlib import Path
import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT)); from app import clock as CLK   # noqa: E402 — institut vaqti (ISFT_CORE_TZ / ISFT_CORE_FAKE_TODAY), server bilan bir xil
DB = Path(os.environ.get("ISFT_CORE_DB") or ROOT / "data" / "jarvis.db")
B = os.environ.get("ISFT_TEST_URL", "http://127.0.0.1:8000")
PW = "Isft2026"
N = [0]
sys.path.insert(0, str(ROOT))

def ok(cond, msg):
    N[0] += 1
    print(("✓ " if cond else "✗ XATO: ") + msg)
    if not cond: sys.exit(1)

def S(uid):
    c = httpx.Client(base_url=B, timeout=180)
    r = c.post("/api/login", json={"user_id": uid, "password": PW})
    assert r.status_code == 200, f"login {uid}: {r.status_code} {r.text}"
    return c

def q(sql, args=()):
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True, timeout=30)
    try: return con.execute(sql, args).fetchall()
    finally: con.close()

def q1(sql, args=()):
    r = q(sql, args); return r[0][0] if r else None

def w(sql, args=()):
    con = sqlite3.connect(DB, timeout=30)
    try: con.execute(sql, args); con.commit()
    finally: con.close()

def J(r, code=200):
    assert r.status_code == code, f"{r.request.method} {r.request.url.path}: {r.status_code} {r.text[:400]}"
    return r.json()

def uid(role):
    return q1("SELECT id FROM users WHERE role=? AND COALESCE(active,1)=1 ORDER BY id LIMIT 1", (role,))

T0 = time.strftime("%Y-%m-%dT%H:%M:%S")
TODAY = CLK.today()
reg, aka, imt, kaf, sir, bux, rek, cc = S(17), S(18), S(8), S(31), S(27), S(11), S(2), S(23)
pro = S(uid("prorektor_oquv"))
KAF_DEPT = q1("SELECT department_id FROM users WHERE id=31")

def sign_order(oid, editor=reg):
    J(editor.post(f"/api/orders/{oid}/submit"))
    return J(rek.post(f"/api/orders/{oid}/sign"))

def annul(oid, editor=reg):
    n = J(editor.post(f"/api/orders/{oid}/annul", json={"note": "test_flows: tuzatuvchi buyruq"}))["id"]
    return sign_order(n, editor)

print("— Ruxsatlar va ko'lam —")
ok(httpx.get(B + "/api/flows/meta").status_code == 401, "Kirishsiz: 401")
for path in ("/api/flows/meta", "/api/flows/sessions", "/api/flows/appeals", "/api/flows/restudy", "/api/flows/transfers", "/api/flows/grant", "/api/flows/grad"):
    ok(cc.get(path).status_code == 403, f"Call-markaz (23): {path} → 403")
ok(q1("SELECT COUNT(*) FROM audit_log WHERE resource='flows' AND allowed=0 AND user_id=23 AND ts>=?", (T0,)) >= 7, "Rad etilgan so'rovlar audit jurnalida (resource=flows)")
ALL = ["sessiya", "apellyatsiya", "qayta", "kochirish", "grant", "bitiruv"]
want = {17: ALL, 18: ALL, 8: ["sessiya", "apellyatsiya"], 31: ALL, 27: ["sessiya", "apellyatsiya", "qayta", "kochirish", "bitiruv"], 11: ["qayta", "grant"], 2: ALL}
for u, c in ((17, reg), (18, aka), (8, imt), (31, kaf), (27, sir), (11, bux), (2, rek)):
    m = J(c.get("/api/flows/meta"))
    ok([t["key"] for t in m["tabs"]] == want[u], f"#{u} ({m['mode']}): bo'limlar {[t['key'] for t in m['tabs']]}")
ok(imt.get("/api/flows/restudy").status_code == 403 and imt.get("/api/flows/grad").status_code == 403, "Imtihon bo'limi: qayta o'qish va bitiruv yopiq (403)")
ok(bux.get("/api/flows/sessions").status_code == 403 and bux.get("/api/flows/appeals").status_code == 403 and bux.get("/api/flows/transfers").status_code == 403,
   "Buxgalteriya: sessiya, apellyatsiya, ko'chirish yopiq (403)")
ok(sir.get("/api/flows/grant").status_code == 403, "Sirtqi bo'lim: ISFT granti (kunduzgi) yopiq (403)")
ok(all(s["study_form"] == "sirtqi" for s in J(sir.get("/api/flows/sessions"))["items"]), "Sirtqi bo'lim: faqat sirtqi sessiyalar")
sr = J(sir.get("/api/flows/restudy?view="))["items"]
ok(sr and {r["study_form"] for r in sr} == {"sirtqi"}, f"Sirtqi bo'lim: qayta o'qish — faqat sirtqi talabalar ({len(sr)})")
kr = J(kaf.get("/api/flows/restudy?view="))["items"]
ok(all(q1("SELECT g.department_id FROM students s JOIN groups_ g ON g.id=s.group_id WHERE s.id=?", (r["student_id"],)) == KAF_DEPT for r in kr),
   f"Kafedra mudiri (31): qayta o'qish — faqat o'z kafedrasi guruhlari ({len(kr)})")
br = J(bux.get("/api/flows/restudy"))["items"]
ok(br and all(r["decision"] == "qayta_oqish" and "failed_at" not in r for r in br), f"Buxgalteriya: faqat qayta o'qish to'lov qatorlari, baholarsiz ({len(br)})")

print("— 1. Imtihon sessiyasi va jadvali —")
ss = J(aka.get("/api/flows/sessions"))["items"]
kq = next(s for s in ss if s["study_form"] == "kunduzgi" and s["season"] == "qishki" and s["semester"] == 1)
ok(kq["status"] == "e'lon qilingan" and kq["slots"] > 1000 and kq["conflicts"] == 0 and kq["windows"], f"Kunduzgi qishki sessiya e'lon qilingan: {kq['slots']} ta imtihon, to'qnashuvsiz, qayta topshirish muddati bilan")
ok({s["study_form"] for s in ss} >= {"kunduzgi", "sirtqi", "masofaviy"} and any(s["study_form"] == "sirtqi" and s["season"] == "yozgi" for s in ss), "Sessiyalar: kunduzgi, masofaviy, sirtqi qishki va yozgi")
mq = next(s for s in ss if s["study_form"] == "masofaviy" and s["status"] == "loyiha")
ok(mq["conflicts"] >= 2, f"Masofaviy loyiha sessiyada ataylab qoldirilgan to'qnashuvlar aniqlandi ({mq['conflicts']})")
ok(aka.post(f"/api/flows/sessions/{mq['id']}/publish").status_code == 400, "To'qnashuvli jadval e'lon qilinmaydi (400)")
kd = J(kaf.get(f"/api/flows/sessions/{kq['id']}?limit=1000"))
ok(kd["items"] and all(x["dept_id"] == KAF_DEPT or q1("SELECT department_id FROM teachers WHERE id=?", (x["examiner_id"],)) == KAF_DEPT for x in kd["items"]),
   f"Kafedra: jadvalda faqat o'z guruhlari yoki imtihon oluvchilari ({kd['total']})")
ok(reg.post("/api/flows/sessions", json={"study_form": "kunduzgi", "season": "qishki", "start": "2027-01-04", "end": "2027-01-10"}).status_code == 403,
   "Registrator ofisi jadval tuzmaydi (403) — Akademik bo'lim tuzadi")
ok(sir.post("/api/flows/sessions", json={"study_form": "kunduzgi", "season": "qishki", "start": "2027-01-04", "end": "2027-01-10"}).status_code == 403,
   "Sirtqi bo'lim kunduzgi sessiya tuza olmaydi (403)")
ns = J(aka.post("/api/flows/sessions", json={"study_form": "kunduzgi", "season": "yozgi", "semester": 2, "start": "2027-07-05", "end": "2027-07-10", "name": "test_flows sessiyasi"}))
g1, g2 = q("SELECT id FROM groups_ WHERE form='kunduzgi' ORDER BY id LIMIT 2")
room = q1("SELECT id FROM rooms WHERE kind='auditoriya' ORDER BY capacity DESC LIMIT 1")
tch = q1("SELECT id FROM teachers ORDER BY id LIMIT 1")
a1 = J(aka.post(f"/api/flows/sessions/{ns['id']}/slots", json={"group_id": g1[0], "subject": "Test fani", "exam_date": "2027-07-05", "start_time": "09:00", "end_time": "11:00",
                                                               "room_id": room, "examiner_id": tch}))
ok(a1["ok"] and not a1["conflicts"], "Jadvalga yozuv qo'shildi")
for body, kind in (({"group_id": g2[0], "room_id": room, "examiner_id": None}, "xona"), ({"group_id": g2[0], "room_id": None, "examiner_id": tch}, "imtihon oluvchi"),
                   ({"group_id": g1[0], "room_id": None, "examiner_id": None}, "guruh")):
    r = aka.post(f"/api/flows/sessions/{ns['id']}/slots", json={"subject": "Boshqa fan", "exam_date": "2027-07-05", "start_time": "10:00", "end_time": "12:00", **body})
    ok(r.status_code == 409 and kind in r.text, f"To'qnashuv tekshiruvi: {kind} band — 409")
f = J(aka.post(f"/api/flows/sessions/{ns['id']}/slots", json={"group_id": g2[0], "subject": "Boshqa fan", "exam_date": "2027-07-05", "start_time": "10:00", "room_id": room, "force": True}))
ok(f["conflicts"] and aka.post(f"/api/flows/sessions/{ns['id']}/publish").status_code == 400, "Majburan qo'shilgan to'qnashuv e'lon qilishni to'xtatadi")
J(aka.post(f"/api/flows/slots/{f['id']}/delete"))
ok(aka.post(f"/api/flows/sessions/{ns['id']}/windows", json={"start": "2027-07-08", "end": "2027-07-12"}).status_code == 400, "Qayta topshirish muddati sessiyadan keyin bo'lishi shart (400)")
J(aka.post(f"/api/flows/sessions/{ns['id']}/windows", json={"name": "Qayta topshirish", "start": "2027-07-15", "end": "2027-07-20"}))
J(aka.post(f"/api/flows/sessions/{ns['id']}/publish"))
ok(q1("SELECT status FROM exam_sessions WHERE id=?", (ns["id"],)) == "e'lon qilingan", "To'qnashuvsiz jadval e'lon qilindi")
x = imt.get(f"/api/flows/sessions/{kq['id']}/export")
ok(x.status_code == 200 and "spreadsheetml" in x.headers["content-type"], "Imtihon bo'limi: jadval XLSX eksporti")
from openpyxl import load_workbook
wb = load_workbook(io.BytesIO(x.content)); ws = wb.active
ok("Imtihon oluvchi" in [c.value for c in ws[5]] and ws.max_row > 1000, f"XLSX: sarlavha va {ws.max_row} qator")
ok(imt.post(f"/api/flows/sessions/{ns['id']}/slots", json={"group_id": g1[0], "subject": "x", "exam_date": "2027-07-06", "start_time": "09:00"}).status_code == 403,
   "Imtihon bo'limi jadvalni o'zgartira olmaydi (403)")
w("DELETE FROM exam_slots WHERE session_id=?", (ns["id"],)); w("DELETE FROM retake_windows WHERE session_id=?", (ns["id"],)); w("DELETE FROM exam_sessions WHERE id=?", (ns["id"],))

print("— 2. Apellyatsiya —")
lo = (TODAY - dt.timedelta(days=3)).isoformat()
cand = q(f"""SELECT a.student_id, a.subject, a.semester FROM grade_attempts a JOIN students s ON s.id=a.student_id JOIN grades g ON g.student_id=a.student_id AND g.subject=a.subject AND g.semester=a.semester
            WHERE a.counted=1 AND a.at>=? AND s.status='faol' AND s.study_form='kunduzgi' AND g.yakuniy BETWEEN 30 AND 60
            AND NOT EXISTS (SELECT 1 FROM grade_appeals p WHERE p.student_id=a.student_id AND p.subject=a.subject AND p.semester=a.semester) ORDER BY a.id DESC LIMIT 2""", (lo,))
while len(cand) < 2:   # qayta ishga tushirishda yaqinda e'lon qilingan natija qolmagan bo'lsa — yangi qayta topshirish urinishi (fixture)
    g = q("""SELECT g.student_id, g.subject, g.semester, g.oraliq, g.yakuniy, g.score, g.attempts FROM grades g JOIN students s ON s.id=g.student_id WHERE g.semester=-1
             AND s.status='faol' AND s.study_form='kunduzgi' AND g.yakuniy BETWEEN 30 AND 60 AND COALESCE(g.attempts,1)=1
             AND NOT EXISTS (SELECT 1 FROM grade_attempts a WHERE a.student_id=g.student_id AND a.subject=g.subject AND a.semester=g.semester) LIMIT 1 OFFSET ?""", (len(cand) * 7,))[0]
    w("INSERT INTO grade_attempts(student_id,subject,semester,attempt,kind,oraliq,yakuniy,score,at,counted,note) VALUES(?,?,?,1,'asosiy',?,?,?,?,1,'test_flows')",
      (g[0], g[1], g[2], g[3], g[4], g[5], TODAY.isoformat()))
    cand.append((g[0], g[1], g[2]))
sid, subj, sem = cand[0]
opts = J(reg.get(f"/api/flows/appeals/options/{sid}"))
ok(any(o["subject"] == subj for o in opts), "Registrator: talabaning apellyatsiya muddatidagi baholari ro'yxati")
ok(imt.post("/api/flows/appeals", json={"student_id": sid, "subject": subj, "semester": sem, "reason": "Javoblarim to'liq baholanmagan"}).status_code == 403,
   "Imtihon bo'limi apellyatsiya arizasini qabul qilmaydi (403) — Registrator qabul qiladi")
ap = J(reg.post("/api/flows/appeals", json={"student_id": sid, "subject": subj, "semester": sem, "reason": "Yozma ishimdagi 2-savol javobi baholanmagan"}))
ok(ap["ok"] and ap["deadline"] >= TODAY.isoformat(), f"Apellyatsiya qabul qilindi (#{ap['id']}, muddat {ap['deadline']})")
ok(reg.post("/api/flows/appeals", json={"student_id": sid, "subject": subj, "semester": sem, "reason": "Takroriy ariza"}).status_code == 400, "Takroriy apellyatsiya rad etiladi (400)")
old = q("""SELECT g.student_id, g.subject, g.semester FROM grades g JOIN students s ON s.id=g.student_id WHERE g.semester=-3 AND s.status='faol' AND g.score IS NOT NULL
           AND NOT EXISTS (SELECT 1 FROM grade_attempts a WHERE a.student_id=g.student_id AND a.subject=g.subject AND a.semester=g.semester) LIMIT 1""")[0]
r = reg.post("/api/flows/appeals", json={"student_id": old[0], "subject": old[1], "semester": old[2], "reason": "Eski natija bo'yicha ariza"})
ok(r.status_code == 400 and "muddati o'tgan" in r.text, "Muddati o'tgan natijaga apellyatsiya rad etiladi (400)")
# talaba portali uchun python funksiyasi
from app import academic_flows as AF
con = sqlite3.connect(DB, timeout=30); con.row_factory = sqlite3.Row
try:
    AF.create_appeal(con, old[0], old[1], old[2], "Portal orqali eski natija", "portal"); ok(False, "create_appeal: muddat tekshirilmadi")
except ValueError as e:
    ok("muddati o'tgan" in str(e), "create_appeal(): muddati o'tgan natija — ValueError")
pa = AF.create_appeal(con, cand[1][0], cand[1][1], cand[1][2], "Portal orqali yuborilgan ariza (test)", "portal")
con.close()
ok(pa["channel"] == "portal" and pa["status"] == "yangi" and pa["deadline"], f"create_appeal(): talaba portali kanali (#{pa['id']})")
a = next(x for x in J(aka.get("/api/flows/appeals?status=ochiq"))["items"] if x["id"] == ap["id"])
yk = a["yakuniy_old"]
ok(aka.post(f"/api/flows/appeals/{a['id']}/decide", json={"decision": "oshirish", "yakuniy": yk + 5, "note": "erta"}).status_code == 400, "Kvorumsiz qaror chiqarilmaydi (400)")
J(imt.post(f"/api/flows/appeals/{a['id']}/vote", json={"vote": "oshirish", "yakuniy": yk + 5, "note": "ish qayta ko'rildi"}))
ok(imt.post(f"/api/flows/appeals/{a['id']}/vote", json={"vote": "saqlash"}).status_code == 400, "Bir a'zo ikki marta ovoz bera olmaydi (400)")
kh = q1("SELECT id FROM users WHERE role='kafedra' AND department_id=? AND COALESCE(active,1)=1", (a["dept_id"],))
other = q1("SELECT id FROM users WHERE role='kafedra' AND department_id!=? AND COALESCE(active,1)=1 ORDER BY id LIMIT 1", (a["dept_id"],))
ok(S(other).post(f"/api/flows/appeals/{a['id']}/vote", json={"vote": "saqlash"}).status_code == 403, f"Boshqa kafedra mudiri (#{other}) komissiya a'zosi emas (403)")
if kh: J(S(kh).post(f"/api/flows/appeals/{a['id']}/vote", json={"vote": "oshirish", "yakuniy": yk + 4}))
else: J(aka.post(f"/api/flows/appeals/{a['id']}/vote", json={"vote": "oshirish", "yakuniy": yk + 5}))
ok(reg.post(f"/api/flows/appeals/{a['id']}/decide", json={"decision": "oshirish", "yakuniy": yk + 5, "note": "x"}).status_code == 403, "Registrator qaror chiqara olmaydi (403)")
ok(aka.post(f"/api/flows/appeals/{a['id']}/decide", json={"decision": "oshirish", "yakuniy": yk - 1, "note": "noto'g'ri"}).status_code == 400, "«Oshirish» uchun pastroq ball rad etiladi (400)")
d = J(aka.post(f"/api/flows/appeals/{a['id']}/decide", json={"decision": "oshirish", "yakuniy": yk + 5, "note": "Komissiya bayonnomasi №7"}))
g = q("SELECT score, oraliq, yakuniy, attempts FROM grades WHERE student_id=? AND subject=? AND semester=?", (sid, subj, sem))[0]
att = q("SELECT kind, counted, score, note FROM grade_attempts WHERE student_id=? AND subject=? AND semester=? ORDER BY attempt", (sid, subj, sem))
ok(d["changed"] and g[2] == yk + 5 and g[0] == g[1] + g[2], f"Baho yangilandi: yakuniy {yk} → {g[2]}, jami {g[0]}")
ok(att[-1][0] == "apellyatsiya" and att[-1][1] == 1 and sum(x[1] for x in att) == 1 and "Komissiya bayonnomasi" in att[-1][3], "Baho faqat grade_attempts orqali: «apellyatsiya» urinishi, sabab bilan, yagona hisobdagi")
ok(q1("SELECT status FROM grade_appeals WHERE id=?", (a["id"],)) == "qaror", "Apellyatsiya holati: qaror")

print("— 3. Qayta o'qish, kursda qoldirish, chetlashtirish —")
rl = J(reg.get("/api/flows/restudy?view=kutilmoqda"))
ok(rl["items"] and all(r["decision"] == "kutilmoqda" for r in rl["items"]), f"Qaror kutilayotgan takliflar: {len(rl['items'])}")
fail = q1(f"""SELECT COUNT(*) FROM restudy r WHERE NOT EXISTS (SELECT 1 FROM grade_attempts a WHERE a.id=r.attempt_id AND a.kind IN ('qayta topshirish','otrabotka') AND a.score<40)""")
ok(fail == 0, "Har bir taklif baholar tarixidagi o'tmagan qayta topshirishga asoslangan")
pend = []
for r in rl["items"]:
    if r["study_form"] == "kunduzgi" and r["student_id"] not in pend: pend.append(r["student_id"])
s_pay, s_rep = pend[0], pend[1]
ok(bux.post(f"/api/flows/restudy/student/{s_pay}/decide", json={"decision": "qayta_oqish"}).status_code == 403, "Buxgalteriya qaror kiritmaydi (403)")
r = J(reg.post(f"/api/flows/restudy/student/{s_pay}/decide", json={"decision": "qayta_oqish", "note": "ariza"}))
exp_amt = q1("SELECT SUM(credits*per_credit) FROM restudy WHERE student_id=? AND decision='qayta_oqish'", (s_pay,))
ok(r["amount"] == exp_amt and r["amount"] > 0, f"Qayta o'qish: kredit × narx = {r['amount']:,} so'm".replace(",", " "))
row = next(x for x in J(bux.get("/api/flows/restudy?view=qayta_oqish"))["items"] if x["student_id"] == s_pay)
ok(reg.post(f"/api/flows/restudy/{row['id']}/pay", json={"amount": 1000}).status_code == 403, "Registrator to'lovni qayd eta olmaydi (403)")
p = J(bux.post(f"/api/flows/restudy/{row['id']}/pay", json={"amount": row["amount"]}))
ok(p["paid"] == row["amount"], "Buxgalteriya to'lovni qayd etdi (qarz qatori yopildi)")
r = J(reg.post(f"/api/flows/restudy/student/{s_rep}/decide", json={"decision": "kursda_qoldirish"}))
o = q("SELECT kind, status FROM orders WHERE id=?", (r["order_id"],))[0]
gt = q("SELECT g.course FROM order_students i JOIN groups_ g ON g.id=json_extract(i.data,'$.group_to_id') WHERE i.order_id=?", (r["order_id"],))
cur_course = q1("SELECT g.course FROM students s JOIN groups_ g ON g.id=s.group_id WHERE s.id=?", (s_rep,))
ok(o == ("kursda_qoldirish", "loyiha") and gt and gt[0][0] == cur_course - 1, f"Kursda qoldirish: Buyruqlar loyihasi #{r['order_id']}, guruh {cur_course - 1}-kursda")
before = q("SELECT group_id, study_form FROM students WHERE id=?", (s_rep,))[0]
sg = sign_order(r["order_id"])
after = q("SELECT group_id, study_form FROM students WHERE id=?", (s_rep,))[0]
ok(sg["changed"] == 1 and after[0] != before[0] and after[1] == before[1], f"Imzolandi ({sg['reg_no']}): talaba quyi kurs guruhiga o'tdi")
annul(r["order_id"])
ok(q("SELECT group_id, study_form FROM students WHERE id=?", (s_rep,))[0] == before, "Tuzatuvchi buyruq: guruh qaytarildi")
ex = J(reg.get("/api/flows/restudy/expulsion"))["items"]
ok(len(ex) >= 1, f"Chetlashtirish nomzodlari (muddat o'tgan / rad etgan): {len(ex)}")
e = J(reg.post("/api/flows/restudy/expulsion/order", json={"ids": [ex[0]["id"]]}))
ok(q("SELECT kind, status FROM orders WHERE id=?", (e["order_id"],))[0] == ("akademik_qarz", "loyiha"), f"«Akademik qarzdorlik sababli chetlashtirish» loyihasi #{e['order_id']}")
ok(ex[0]["id"] not in {x["id"] for x in J(reg.get("/api/flows/restudy/expulsion"))["items"]}, "Loyihaga kiritilgan talaba nomzodlar ro'yxatidan chiqdi")
ok(any(k["key"] == "akademik_qarz" for k in J(reg.get("/api/orders/meta"))["kinds"]), "Buyruqlar: yangi tur «akademik_qarz» mavjud")
sg = sign_order(e["order_id"])
ok(q1("SELECT status FROM students WHERE id=?", (ex[0]["id"],)) == "chetlashtirilgan", f"Imzolandi ({sg['reg_no']}): holat «chetlashtirilgan»")
annul(e["order_id"])
ok(q1("SELECT status FROM students WHERE id=?", (ex[0]["id"],)) == "faol", "Tuzatuvchi buyruq: holat qaytarildi")

print("— 4. Ko'chirish va qayta tiklash —")
busy = {x[0] for x in q("SELECT student_id FROM transfers WHERE student_id IS NOT NULL")} | {x[0] for x in q("SELECT student_id FROM restudy")}
st = next(x[0] for x in q("""SELECT s.id FROM students s JOIN groups_ g ON g.id=s.group_id WHERE s.status='faol' AND g.form='kunduzgi' AND g.course=2 AND g.direction='Marketing'
                             ORDER BY s.id DESC LIMIT 200""") if x[0] not in busy)
tg = q1("SELECT id FROM groups_ WHERE form='kunduzgi' AND course=2 AND direction='Xalqaro munosabatlar' ORDER BY id LIMIT 1")
pv = J(reg.get(f"/api/flows/transfers/preview?student_id={st}&group_id={tg}"))
ok(sir.post("/api/flows/transfers", json={"kind": "ichki", "student_id": st, "to_group_id": tg}).status_code == 403, "Sirtqi bo'lim kunduzgi talabani ko'chira olmaydi (403)")
t = J(reg.post("/api/flows/transfers", json={"kind": "ichki", "student_id": st, "to_group_id": tg, "reason": "test_flows"}))
ok(t["diffs"] == len(pv["diffs"]) > 0 and t["status"] == "farq fanlari", f"Ichki ko'chirish: farq fanlari o'quv rejalari farqidan — {t['diffs']} ta")
ok(q1("SELECT deadline FROM transfers WHERE id=?", (t["id"],)) == (TODAY + dt.timedelta(days=120)).isoformat(), "Farq fanlari topshirish muddati: 120 kun")
did = q1("SELECT id FROM transfer_diff WHERE transfer_id=? ORDER BY id LIMIT 1", (t["id"],))
ok(kaf.post(f"/api/flows/transfers/diff/{did}", json={"score": 70}).status_code == 403, "Kafedra farq fani natijasini kiritmaydi (403)")
ok(J(aka.post(f"/api/flows/transfers/diff/{did}", json={"score": 71}))["passed"], "Akademik bo'lim: farq fani topshirildi")
ok(reg.post("/api/flows/transfers", json={"kind": "ichki", "student_id": st, "to_group_id": tg}).status_code == 400, "Ko'rib chiqilayotgan arizasi bor talaba — 400")
to = J(reg.post(f"/api/flows/transfers/{t['id']}/order"))
ok(q("SELECT kind, status FROM orders WHERE id=?", (to["order_id"],))[0] == ("ichki_kochirish", "loyiha"), f"Buyruqlar: «Ichki ko'chirish» loyihasi #{to['order_id']}")
ok(reg.post(f"/api/flows/transfers/{t['id']}/order").status_code == 400, "Ikkinchi loyiha tuzilmaydi (400)")
bf = q("SELECT group_id, faculty_id FROM students WHERE id=?", (st,))[0]
sign_order(to["order_id"])
ok(q1("SELECT group_id FROM students WHERE id=?", (st,)) == tg, "Imzolandi: talaba yangi yo'nalish guruhida")
ok(next(x for x in J(reg.get("/api/flows/transfers"))["items"] if x["id"] == t["id"])["status"] == "yakunlangan", "Ariza holati: yakunlangan")
annul(to["order_id"])
ok(q("SELECT group_id, faculty_id FROM students WHERE id=?", (st,))[0] == bf, "Tuzatuvchi buyruq: guruh qaytarildi")
# shaklni o'zgartirish (kunduzgi → sirtqi): ta'lim shakli guruhdan olinadi
st2 = next(x[0] for x in q("""SELECT s.id FROM students s JOIN groups_ g ON g.id=s.group_id WHERE s.status='faol' AND g.form='kunduzgi' AND g.course=3 AND g.direction='Iqtisodiyot'
                              ORDER BY s.id DESC LIMIT 200""") if x[0] not in busy)
sg2 = q1("SELECT id FROM groups_ WHERE form='sirtqi' AND course=3 AND direction='Iqtisodiyot' ORDER BY id LIMIT 1")
t2 = J(reg.post("/api/flows/transfers", json={"kind": "ichki", "student_id": st2, "to_group_id": sg2}))
o2 = J(reg.post(f"/api/flows/transfers/{t2['id']}/order"))["order_id"]
sign_order(o2)
ok(q1("SELECT study_form FROM students WHERE id=?", (st2,)) == "sirtqi", "Shakl o'zgarishi: imzodan keyin ta'lim shakli «sirtqi»")
annul(o2)
ok(q1("SELECT study_form FROM students WHERE id=?", (st2,)) == "kunduzgi", "Tuzatuvchi buyruq: ta'lim shakli qaytarildi")
# boshqa OTMdan ko'chirib kelish
tk = J(reg.post("/api/flows/transfers", json={"kind": "kirish", "applicant": "Testova Madina Anvar qizi", "other_otm": "Namuna universiteti", "to_group_id": tg,
                                               "prior_subjects": ["Oliy matematika", "Ingliz tili"]}))
ko = J(reg.post(f"/api/flows/transfers/{tk['id']}/order"))
ok(q1("SELECT status FROM students WHERE id=?", (ko["student_id"],)) == "qabul kutilmoqda", "Ko'chirib kelish: shaxs «qabul kutilmoqda» holatida, buyruq loyihasi tuzildi")
sign_order(ko["order_id"])
ok(q("SELECT status, group_id FROM students WHERE id=?", (ko["student_id"],))[0] == ("faol", tg), "Imzolandi: talabalar safiga qabul qilindi")
ok(not any(x["student"]["id"] == ko["student_id"] for x in J(S(uid("malumotlar_bazasi")).get("/api/orders/audit/issues"))["items"]),
   "Muvofiqlik auditi: ko'chirish tartibida qabul qilingan talaba «qabul buyrug'ida yo'q» deb chiqmaydi")
ok(reg.post("/api/flows/transfers", json={"kind": "chiqish", "student_id": st}).status_code == 400, "Boshqa OTMga: qabul qiluvchi OTM nomi majburiy (400)")
ok(reg.post("/api/flows/transfers", json={"kind": "tiklash", "student_id": st, "to_group_id": tg}).status_code == 400, "Qayta tiklash faqat chetlashtirilgan talaba uchun (400)")
kinds = {x["kind"] for x in J(reg.get("/api/flows/transfers"))["items"]}
ok(kinds >= {"ichki", "kirish", "chiqish", "tiklash", "tatildan_qaytish"}, f"Demo arizalar: barcha turlar {sorted(kinds)}")

print("— 5. ISFT granti —")
G = J(reg.get("/api/flows/grant"))
ok("davlat granti" not in json.dumps(G, ensure_ascii=False).lower(), "Matnlarda «davlat granti» yo'q — ISFT granti")
tot = sum(x["n"] for x in G["holders"])
ok(1100 <= tot <= 1300 and G["quota"] == {"merit": 250, "social": 50}, f"Grant egalari: {tot} (yiliga 250 + 50)")
R = G["round"]
if R["status"] not in ("komissiya", "loyiha"):
    ok(reg.post("/api/flows/grant/rounds").status_code == 200, "Yangi raund tuzildi (qayta ishga tushirish)")
    R = J(reg.get("/api/flows/grant"))["round"]
if R["status"] == "loyiha": J(reg.post(f"/api/flows/grant/rounds/{R['id']}/submit"))
G = J(reg.get(f"/api/flows/grant?round={R['id']}")); C = G["candidates"]
ok(reg.post("/api/flows/grant/rounds").status_code == 400, "Yakunlanmagan raund bor — yangisi tuzilmaydi (400)")
lose = [x for x in C if x["kind"] == "mahrum"]; award = [x for x in C if x["kind"] == "tavsiya"]
ok(lose and all(x["debts"] or x["gpa"] is None or x["gpa"] < (3.0 if x["category"] == "ijtimoiy" else 4.0) for x in lose), f"Saqlab qolish qoidasi: {len(lose)} ta mahrum nomzodi (qarz yoki GPA past)")
ok(award and all(not x["debts"] and x["gpa"] >= 4.0 and x["payment_type"] == "kontrakt" for x in award), f"Tavsiya: {len(award)} ta qarzsiz kontrakt talabasi, GPA ≥ 4.0")
sid0 = award[0]["student_id"]
gp = q(f"SELECT credits, score FROM grades WHERE student_id=? AND semester IN (-1,0)", (sid0,))
g5 = lambda s: 5 if s >= 65 else 4 if s >= 50 else 3 if s >= 40 else 2
ok(abs(award[0]["gpa"] - round(sum(c * g5(s) for c, s in gp) / sum(c for c, _ in gp) + 1e-9, 2)) < 0.011, "Yillik GPA — kredit bilan tortilgan (academic_rules.gpa formulasi)")
ok(reg.post(f"/api/flows/grant/rounds/{R['id']}/decide", json={}).status_code == 403 and bux.post(f"/api/flows/grant/rounds/{R['id']}/decide", json={}).status_code == 403,
   "Komissiya qarori: Registrator va Buxgalteriya uchun yopiq (403)")
ok(reg.post(f"/api/flows/grant/rounds/{R['id']}/orders").status_code == 400, "Komissiya qarorisiz buyruq tuzilmaydi (400)")
rad = award[-1]["id"]
dd = J(rek.post(f"/api/flows/grant/rounds/{R['id']}/decide", json={"decisions": {str(rad): "rad"}, "note": "Komissiya bayonnomasi"}))
ok(dd["no"] == 1 and dd["ok"] == len(C) - 1, f"Rektor: komissiya qarori (tasdiq {dd['ok']}, rad {dd['no']})")
ok(pro.post(f"/api/flows/grant/rounds/{R['id']}/decide", json={}).status_code == 400, "Qaror takrorlanmaydi (400)")
F = J(bux.get(f"/api/flows/grant?round={R['id']}"))
ok(F["candidates"] and all(x["decision"] == "tasdiqlandi" for x in F["candidates"]) and F["finance"]["revoke_income"] > 0, "Buxgalteriya: tasdiqlangan o'zgarishlar va moliyaviy ta'sir")
oo = J(reg.post(f"/api/flows/grant/rounds/{R['id']}/orders"))["orders"]
ok(q1("SELECT count FROM orders WHERE id=?", (oo["isft_granti"],)) == len(award) - 1 and q1("SELECT count FROM orders WHERE id=?", (oo["isft_granti_mahrum"],)) == len(lose),
   "Buyruqlar: «ISFT granti berish» va «ISFT grantidan mahrum qilish» loyihalari")
m1 = lose[0]["student_id"]
sign_order(oo["isft_granti_mahrum"])
ok(q("SELECT payment_type, contract_amount>0 FROM students WHERE id=?", (m1,))[0] == ("kontrakt", 1), "Imzolandi: mahrum qilingan talaba kontraktga o'tdi (summa bilan)")
annul(oo["isft_granti_mahrum"])
ok(q("SELECT payment_type, contract_amount FROM students WHERE id=?", (m1,))[0] == ("grant", 0), "Tuzatuvchi buyruq: grant va summa qaytarildi")

print("— 6. Bitiruv —")
D = J(reg.get("/api/flows/grad?view=eligible&limit=500"))
el = [x for x in D["items"] if x["eligible"]]
ok(D["summary"]["total"] > 1000 and all(all(c["ok"] for c in x["checks"]) for x in el), f"Bitiruvchi kurs: {D['summary']['total']}, talablarga javob beradi: {len(el)}")
nb = [x for x in J(reg.get("/api/flows/grad?limit=100"))["items"] if x["level"] == "bakalavr"]
ok(nb and not nb[0]["eligible"] and any(c["key"] == "credits" and not c["ok"] for c in nb[0]["checks"]), "Joriy 4-kurs: kredit hali yetmaydi (240 talab)")
s4 = nb[0]["id"]
ok(imt.post(f"/api/flows/grad/{s4}/thesis", json={"topic": "x"}).status_code == 403 and bux.post(f"/api/flows/grad/{s4}/thesis", json={"topic": "x"}).status_code == 403,
   "Bitiruv ishi: Imtihon bo'limi va Buxgalteriya uchun yopiq (403)")
J(reg.post(f"/api/flows/grad/{s4}/thesis", json={"topic": "Test mavzusi: raqamli moliya", "defense_date": "2027-06-01", "status": "tasdiqlangan"}))
ok(q1("SELECT topic FROM theses WHERE student_id=?", (s4,)) == "Test mavzusi: raqamli moliya", "Bitiruv ishi mavzusi, rahbar va himoya sanasi saqlanadi")
ok(reg.post(f"/api/flows/grad/{s4}/yda", json={"score": 80, "exam_date": "2027-06-10"}).status_code == 403, "YDA natijasini faqat Akademik bo'lim kiritadi (403)")
ok(reg.post("/api/flows/grad/order", json={"ids": [s4]}).status_code == 400, "Talablarga javob bermaydigan talabaga bitirish buyrug'i tuzilmaydi (400)")
dip0 = q1("SELECT COUNT(*) FROM diplomas")
if el:
    ids = [x["id"] for x in el if not x.get("order")]
    go = J(reg.post("/api/flows/grad/order", json={"ids": ids}))
    sign_order(go["order_id"])
    ok(all(q1("SELECT status FROM students WHERE id=?", (i,)) == "bitirgan" for i in ids), f"Bitirish buyrug'i imzolandi: {len(ids)} ta talaba «bitirgan»")
    rg = J(reg.post("/api/flows/grad/diplomas"))
    ok(rg["registered"] == len(ids), f"Diplom raqamlari berildi: {rg['registered']}")
else:
    print("  (qayta ishga tushirish: kechiktirilgan bitiruvchilar allaqachon bitirgan)")
DL = J(reg.get("/api/flows/grad/diplomas"))["items"]
ok(len(DL) >= dip0 and all(x["series"].startswith(("B-", "M-")) and len(x["number"]) == 6 for x in DL) and len({(x["series"], x["number"]) for x in DL}) == len(DL),
   f"Diplomlar reyestri: {len(DL)} ta, seriya va raqam takrorlanmaydi")
for dpl in [x for x in DL if x["honours"]][:3]:
    sc = [r[0] for r in q("SELECT score FROM grades WHERE student_id=? AND score IS NOT NULL", (dpl["student_id"],))]
    ok(sum(s >= 65 for s in sc) / len(sc) >= 0.75 and min(sc) >= 50, f"Imtiyozli diplom qoidasi: {dpl['full_name']} — «A» {sum(s >= 65 for s in sc)}/{len(sc)}, eng past {min(sc)}")
gid = DL[0]["student_id"]
x = reg.get(f"/api/flows/grad/{gid}/supplement")
ok(x.status_code == 200 and "wordprocessingml" in x.headers["content-type"], "Diplom ilovasi (.docx)")
xml = zipfile.ZipFile(io.BytesIO(x.content)).read("word/document.xml").decode("utf-8")
subs = [r[0] for r in q("SELECT subject FROM grades WHERE student_id=?", (gid,))]
ok(DL[0]["number"] in xml and all(s.replace("'", "&apos;") in xml or s in xml for s in subs[:5]) and "Jami o'zlashtirilgan kredit".replace("'", "&apos;") in xml.replace("'", "&apos;"),
   f"Ilovada diplom raqami va barcha semestrlar fanlari ({len(subs)} ta)")
out = q1("SELECT s.id FROM students s JOIN groups_ g ON g.id=s.group_id WHERE g.department_id!=? AND s.status='faol' LIMIT 1", (KAF_DEPT,))
ok(kaf.get(f"/api/flows/grad/{out}/supplement").status_code == 403, "Kafedra: boshqa kafedra talabasining ilovasi yopiq (403)")
kg = J(kaf.get("/api/flows/grad?limit=100"))["items"]
ok(all(q1("SELECT g.department_id FROM students s JOIN groups_ g ON g.id=s.group_id WHERE s.id=?", (r["id"],)) == KAF_DEPT for r in kg), "Kafedra: bitiruvchilar — faqat o'z kafedrasi")
ok(q1("SELECT COUNT(*) FROM audit_log WHERE resource='flows' AND allowed=1 AND ts>=?", (T0,)) > 50, "Barcha amallar audit jurnalida (resource=flows)")

print(f"\nHammasi o'tdi: {N[0]} ta tekshiruv")
