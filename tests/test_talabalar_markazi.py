"""Talabalar markazi: API + qoidalar dvigateli testlari (jonli server :8000, sun'iy ma'lumot)."""
import httpx, sys, sqlite3, datetime as dt, base64, io, json
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from app import db as DB, student_ops as OPS
B = "http://127.0.0.1:8000"; DBP = str(ROOT / "data" / "jarvis.db")
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
ok(all(reg.get(f"/api/ops/cases?faculty={f}").json() for f in (1, 2, 3)), "Registrator ofisi: uchala fakultet holatlari (fakultet darajasidagi ko'rinish)")
t2 = ty2.get("/api/ops/tasks").json(); ok(t2 and all(t["faculty"] == "Xalqaro iqtisodiyot va moliya" and t["assignee_role"] == "tyutor" for t in t2), f"Tyutor: o'z fakulteti topshiriqlari ({len(t2)})")
ok(pro.get("/api/ops/cases").status_code == 200, "O'quv prorektori: to'liq ko'rinish")
sc = ct[0]["script"]; ok(sc["say"] and "o'ylab topilmaydi" in sc["basis"][0], "Skript: faktlar bor, me'yoriy havola o'ylab topilmagan")

# --- idempotentlik ---
con = DB.connect()
st = OPS.evaluate(con); ok(st["opened"] == 0 and st["tasks"] == 0, f"Dvigatel qayta ishga tushdi: yangi holat/topshiriq yo'q {st}")
dup = q("SELECT COUNT(*) FROM (SELECT case_id, kind FROM ops_tasks WHERE status='yangi' GROUP BY case_id, kind HAVING COUNT(*)>1)")[0][0]
ok(dup == 0, "Bitta holat+tur bo'yicha ochiq topshiriq dublikati yo'q")

# --- call-markaz: va'da → muddat o'tsa qayta qo'ng'iroq ---
kt = cc.get("/api/ops/tasks?rule=kontrakt").json()[0]
r = cc.post(f"/api/ops/tasks/{kt['id']}/outcome", json={"outcome": "vada", "promise_date": "2020-01-01"}); ok(r.status_code == 400, "Va'da sanasi o'tmishda bo'lsa — rad")
pd = (dt.date.today() + dt.timedelta(days=2)).isoformat()
ok(cc.post(f"/api/ops/tasks/{kt['id']}/outcome", json={"outcome": "vada", "promise_date": pd, "note": "oylik tushgach to'layman"}).json()["ok"], "Va'da berdi (2 kun)")
ok(cc.post(f"/api/ops/tasks/{kt['id']}/outcome", json={"outcome": "gaplashildi"}).status_code == 409, "Yopilgan topshiriqqa qayta natija — 409")
st = OPS.evaluate(con, today=dt.date.today() + dt.timedelta(days=3))
fu = q("SELECT COUNT(*) FROM ops_tasks WHERE case_id=? AND status='yangi' AND title LIKE 'Va''da muddati%'", (kt["case_id"],))[0][0]
ok(fu == 1, f"Va'da muddati o'tgach qayta qo'ng'iroq yaratildi (followups={st['followups']})")
OPS.evaluate(con, today=dt.date.today() + dt.timedelta(days=3))
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
if bt: r = reg.post(f"/api/ops/tasks/{bt['id']}/document", json={}).json(); ok(r["reg_no"].startswith("HB-") and r["status"] == "loyiha", f"Hayfsan buyrug'i loyihasi (rektor imzosini kutadi): {r['reg_no']}")
ok(cc.post(f"/api/ops/tasks/{xt['id']}/document", json={}).status_code in (403, 409), "Call-markaz hujjat chiqara olmaydi")

# --- kontrakt to'landi → holat yopiladi ---
kc = q("SELECT id, student_id FROM ops_cases WHERE rule='kontrakt' AND status='ochiq' LIMIT 1")[0]
con.execute("UPDATE students SET paid_amount=contract_amount WHERE id=?", (kc[1],)); con.commit()
OPS.evaluate(con)
ok(q("SELECT status, close_reason FROM ops_cases WHERE id=?", (kc[0],))[0][0] == "yopildi", "To'lov qilindi → kontrakt holati yopildi, ochiq topshiriqlar bekor")
ok(q("SELECT COUNT(*) FROM ops_tasks WHERE case_id=? AND status='yangi'", (kc[0],))[0][0] == 0, "Yopilgan holatda ochiq topshiriq qolmadi")

# --- otrabotka ---
# seed ba'zi talabalarga allaqachon otrabotka bergan — ochiq otrabotkasi yo'q fan tanlanadi
open_rt = {(r[0], r[1]) for r in q("SELECT student_id, subject FROM retakes WHERE status IN ('berildi','topshirildi')")}
sid, subj = next((c["student_id"], f["subject"]) for c in ty2.get("/api/ops/cases?rule=akademik").json()
                 for f in c["facts"]["fails"] if (c["student_id"], f["subject"]) not in open_rt)
r = ty2.post("/api/ops/retakes", json={"student_id": sid, "subject": subj}).json(); ok(r["reg_no"].startswith("OV-"), f"Tyutor otrabotka varaqasi berdi: {r['reg_no']}")
rid = r["id"]
ok(ty2.post("/api/ops/retakes", json={"student_id": sid, "subject": subj}).status_code == 409, "Shu fan bo'yicha ikkinchi ochiq otrabotka — 409")
ok(ty1.post("/api/ops/retakes", json={"student_id": sid, "subject": subj}).status_code == 403, "Boshqa fakultet tyutori bera olmaydi")
bad = "data:image/png;base64," + base64.b64encode(b"%PDF-1.4 fake").decode()
ok(ty2.post(f"/api/ops/retakes/{rid}/upload", json={"data_url": bad}).status_code == 400, "Mazmuni turiga mos bo'lmagan fayl rad etildi")
from PIL import Image; buf = io.BytesIO(); Image.new("RGB", (40, 40), "white").save(buf, "PNG")
ok(ty2.post(f"/api/ops/retakes/{rid}/upload", json={"data_url": "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()}).json()["ok"], "Skan yuklandi")
ok(ty2.post(f"/api/ops/retakes/{rid}/approve", json={"score": 71}).status_code == 403, "Tyutor bahoni tasdiqlay olmaydi")
ok(reg.get(f"/api/ops/retakes/{rid}/file").status_code == 200, "Registrator skanni ko'radi")
ok(reg.post(f"/api/ops/retakes/{rid}/approve", json={"score": 71}).json()["ok"], "Registrator tasdiqladi")
ok(q("SELECT score FROM grades WHERE student_id=? AND subject=? AND semester=1", (sid, subj))[0][0] == 71, "Baho bazada yangilandi (71)")
ok(reg.post(f"/api/ops/retakes/{rid}/approve", json={"score": 90}).status_code == 409, "Qayta tasdiqlash — 409")
ok(any(a[0] == "baho o'zgartirildi (otrabotka)" for a in q("SELECT action FROM audit_log ORDER BY id DESC LIMIT 20")), "Baho o'zgarishi audit jurnalida")

# --- bo'sh ruxsatlar ---
cc_q = {r[0] for r in q("SELECT student_id FROM ops_tasks WHERE assignee_role='call_center'")}
other = next(r[0] for r in q("SELECT id FROM students ORDER BY id") if r[0] not in cc_q)
ok(cc.get(f"/api/ops/student/{other}").status_code == 403, "Call-markaz o'z navbatida yo'q talaba kartasini ocholmaydi")
ccs = cc.get(f"/api/ops/student/{ct[1]['student_id']}").json(); ok(ccs.get("limited") and not ccs["absences"] and "grades" not in json.dumps(ccs), "Call-markaz kartasi: minimal ma'lumot")
print("\nNATIJA:", "HAMMASI O'TDI" if not fails else f"{fails} TA XATO")
