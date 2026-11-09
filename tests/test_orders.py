import os
"""«Buyruqlar» moduli: uchidan-uchigacha HTTP testlar (server http://127.0.0.1:8000 da ishlab turishi kerak).

Ishga tushirish:  .venv/bin/python tests/test_orders.py
Qayta ishga tushirish mumkin: test o'z buyruqlarini yaratadi, imzolaydi va tuzatuvchi («bekor qilish») buyruq bilan talabalar
ma'lumotini avvalgi holatiga qaytaradi; katta ro'yxat loyihasi oxirida o'chiriladi (versiyalari saqlanadi). Muvofiqlik tuzatishi
(guruhga biriktirish, izoh) sinovidan keyin baza to'g'ridan-to'g'ri SQL bilan asl holiga qaytariladi. Seed qilingan demo buyruqlar
(imzoga yuborilgan familiya o'zgarishi va h.k.) faqat o'qiladi.
"""
import io, json, re, sqlite3, sys, time, zipfile
from pathlib import Path
import httpx

ROOT = Path(__file__).resolve().parent.parent
DB = Path(os.environ.get("ISFT_CORE_DB") or ROOT / "data" / "jarvis.db")
B = os.environ.get("ISFT_TEST_URL", "http://127.0.0.1:8000")
PW = "Isft2026"
N = [0]

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

def w(sql, args=()):
    con = sqlite3.connect(DB, timeout=30)
    try: con.execute(sql, args); con.commit()
    finally: con.close()

def J(r, code=200):
    assert r.status_code == code, f"{r.request.method} {r.request.url.path}: {r.status_code} {r.text[:400]}"
    return r.json()

def uid(role):
    return q("SELECT id FROM users WHERE role=? AND COALESCE(active,1)=1 ORDER BY id LIMIT 1", (role,))[0][0]

reg, rek, pro, sir, mb, kad = S(uid("talabalar")), S(uid("rektor")), S(uid("prorektor_oquv")), S(uid("sirtqi")), S(uid("malumotlar_bazasi")), S(uid("kadrlar"))
T0 = time.strftime("%Y-%m-%dT%H:%M:%S")

def denied_audit(action_like):
    return q("SELECT COUNT(*) FROM audit_log WHERE resource='orders' AND allowed=0 AND ts>=? AND action LIKE ?", (T0, f"%{action_like}%"))[0][0]

def busy_ids():
    """Ko'rib chiqilayotgan (imzolanmagan) buyruqlardagi talabalar — test ularga tegmaydi."""
    return {r[0] for r in q("""SELECT DISTINCT i.student_id FROM order_students i JOIN orders o ON o.id=i.order_id AND i.version=o.version
                              WHERE o.status IN ('loyiha','yuborilgan','kelishilgan') AND o.count < 1000""")}

def anomaly_ids():
    r = q("SELECT v FROM order_meta WHERE k='anomalies'")
    return {x for v in json.loads(r[0][0]).values() for x in v} if r else set()

print("— Ruxsatlar —")
ok(httpx.get(B + "/api/orders/meta").status_code == 401, "Kirishsiz: 401")
ok(kad.get("/api/orders/meta").status_code == 403 and kad.get("/api/orders").status_code == 403 and kad.get("/api/orders/audit/issues").status_code == 403,
   "Kadrlar bo'limi: Buyruqlar yopiq (403)")
ok(denied_audit("buyruqlar") >= 3, "Rad etilgan urinishlar audit jurnalida (resource=orders, allowed=0)")
m = J(reg.get("/api/orders/meta"))
ok(m["caps"]["edit"] and not m["caps"]["sign"], "Registrator: loyiha tuzadi, imzolamaydi")
ok(J(rek.get("/api/orders/meta"))["caps"]["sign"] and not J(rek.get("/api/orders/meta"))["caps"]["edit"], "Rektor: imzolaydi, loyiha tuzmaydi")
ok(J(pro.get("/api/orders/meta"))["caps"]["forward"], "O'quv prorektori: kelishadi")
mbm = J(mb.get("/api/orders/meta"))
ok(mbm["caps"]["fix"] and not mbm["caps"]["edit"], "Ma'lumotlar bazasi: o'qish + muvofiqlik tuzatishi, loyiha yo'q")
ok(mb.post("/api/orders", json={"kind": "guruh", "students": []}).status_code == 403, "Ma'lumotlar bazasi: loyiha yarata olmaydi (403)")
ok(pro.post("/api/orders", json={"kind": "guruh", "students": []}).status_code == 403, "Prorektor: loyiha yarata olmaydi (403)")
sl = J(sir.get("/api/orders?status=&limit=200"))
ok(sl["total"] > 0 and {x["study_form"] for x in sl["items"]} == {"sirtqi"}, f"Sirtqi bo'lim: faqat sirtqi buyruqlar ({sl['total']} ta)")
nonsir = q("SELECT id FROM orders WHERE study_form='kunduzgi' AND historic=1 LIMIT 1")[0][0]
ok(sir.get(f"/api/orders/{nonsir}").status_code == 403, "Sirtqi bo'lim: kunduzgi buyrug'ini ocha olmaydi (403)")
kst = q("SELECT id FROM students WHERE study_form='kunduzgi' AND status='faol' LIMIT 1")[0][0]
ok(sir.post("/api/orders", json={"kind": "akademik_tatil", "students": [{"student_id": kst, "data": {"date_from": "2026-12-01", "date_to": "2027-11-30"}}]}).status_code == 403,
   "Sirtqi bo'lim: kunduzgi talabaga loyiha tuza olmaydi (403)")
ok({x["study_form"] for x in J(sir.get("/api/orders/lookup/students?q=ov"))} <= {"sirtqi"}, "Sirtqi bo'lim: talaba qidiruvi faqat sirtqi")

print("— Reyestr va muvofiqlik auditi —")
ok(q("SELECT COUNT(*) FROM orders WHERE historic=1 AND kind='qabul'")[0][0] >= 8, "Reyestr: qabul buyruqlari (yil × shakl) seed qilingan")
ok(q("SELECT COUNT(*) FROM orders WHERE historic=1 AND kind='kurs'")[0][0] >= 6, "Reyestr: kursga o'tkazish buyruqlari")
cover = q("""SELECT COUNT(*) FROM students s WHERE s.status IN ('faol',"akademik ta'til") AND s.id NOT IN
             (SELECT i.student_id FROM order_students i JOIN orders o ON o.id=i.order_id AND i.version=o.version WHERE o.kind='qabul' AND o.status='imzolangan')""")[0][0]
ok(cover <= 10, f"Deyarli barcha talabalar qabul buyrug'ida (tashqarida: {cover})")
a = J(mb.get("/api/orders/audit/issues"))
kinds = {s["kind"]: s["count"] for s in a["summary"]}
ok(all(kinds.get(k, 0) >= 1 for k in ("no_admission", "no_transfer", "contradiction", "group_mismatch", "expelled_active", "leave_no_order")),
   f"Muammoli talabalar: barcha 6 tur topildi {kinds}")
found = {x["student"]["id"] for x in a["items"]}
an = anomaly_ids() - {x for x in json.loads(q("SELECT v FROM order_meta WHERE k='anomalies'")[0][0]).get("group_ok", [])}
fixed = {r[0] for r in q("SELECT student_id FROM order_issue_fixes WHERE action='izoh'")}
ok((an - fixed) <= found, f"Ataylab kiritilgan nomuvofiqliklar ({len(an)} ta) auditda aniqlandi")
ok(not (set(json.loads(q("SELECT v FROM order_meta WHERE k='anomalies'")[0][0]).get("group_ok", [])) & found), "Muvofiq guruh o'zgarishlari (buyruq bilan) muammo sifatida chiqmaydi")
sa = J(sir.get("/api/orders/audit/issues"))
ok(sa["items"] and {x["student"]["study_form"] for x in sa["items"]} == {"sirtqi"}, "Sirtqi bo'lim: auditda faqat sirtqi talabalar")
gm = next(x for x in a["items"] if x["kind"] == "group_mismatch")
act = {x["action"]: x for x in gm["actions"]}
ok(act["guruhga_biriktirish"]["needs_doc"] and act["guruhga_biriktirish"]["allowed"] and not act["loyiha"]["allowed"], "Guruh mos emas: «Guruhga biriktirish» (hujjat talab qiladi); MB uchun loyiha yo'q")
r = mb.post("/api/orders/audit/fix", json={"key": gm["key"], "action": "guruhga_biriktirish"})
ok(r.status_code == 400 and "hujjat" in r.text.lower(), "Asos hujjatsiz tuzatish rad etiladi (400)")
ok(mb.post("/api/orders/audit/fix", json={"key": gm["key"], "action": "loyiha"}).status_code == 403, "MB: tuzatuvchi buyruq loyihasini tuza olmaydi (403)")
sid = gm["student"]["id"]
before = q("SELECT group_id, faculty_id FROM students WHERE id=?", (sid,))[0]
pdf = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"
up = J(mb.post(f"/api/orders/files?name=buyruq_skan.pdf&student_id={sid}", content=pdf, headers={"Content-Type": "application/octet-stream"}))
ok(up["id"] > 0, "Asos hujjat (PDF) yuklandi")
ok(mb.post(f"/api/orders/files?name=x.exe", content=b"MZ", headers={"Content-Type": "application/octet-stream"}).status_code == 400, "Ruxsat etilmagan fayl turi rad etiladi")
try:
    J(mb.post("/api/orders/audit/fix", json={"key": gm["key"], "action": "guruhga_biriktirish", "file_id": up["id"]}))
    now = q("SELECT group_id FROM students WHERE id=?", (sid,))[0][0]
    ok(now == gm["order_group"]["id"], f"Guruhga biriktirildi: {gm['student']['grp']} → {gm['order_group']['name']}")
    ok(q("SELECT COUNT(*) FROM student_changes WHERE student_id=? AND field='group_id' AND ts>=?", (sid, T0))[0][0] == 1, "O'zgarish jurnalga yozildi")
    ok(gm["key"] not in {x["key"] for x in J(mb.get("/api/orders/audit/issues"))["items"]}, "Muammo ro'yxatdan chiqdi")
finally:   # asl holiga qaytarish (test qayta ishga tushirilishi uchun)
    w("UPDATE students SET group_id=?, faculty_id=? WHERE id=?", (before[0], before[1], sid))
    w("DELETE FROM student_changes WHERE student_id=? AND ts>=?", (sid, T0))
    w("DELETE FROM order_issue_fixes WHERE key=? AND ts>=?", (gm["key"], T0))
ea = next(x for x in a["items"] if x["kind"] == "expelled_active")
ref = ea["orders"][0]["id"]
try:
    r = reg.post("/api/orders/audit/fix", json={"key": ea["key"], "action": "izoh", "ref_order_id": ref, "note": "x"})
    ok(r.status_code == 400, "Izohsiz «Hujjat bilan izohlash» rad etiladi")
    J(reg.post("/api/orders/audit/fix", json={"key": ea["key"], "action": "izoh", "ref_order_id": ref, "note": "Talaba to'lovni amalga oshirgan, buyruq bekor qilish jarayonida (test)"}))
    ok(ea["key"] not in {x["key"] for x in J(reg.get("/api/orders/audit/issues"))["items"]}, "Hujjat bilan izohlangan holat «hal qilingan»")
finally:
    w("DELETE FROM order_issue_fixes WHERE key=? AND ts>=?", (ea["key"], T0))
na = next(x for x in a["items"] if x["kind"] == "no_admission" and x["student"]["study_form"] != "sirtqi")
r = J(reg.post("/api/orders/audit/fix", json={"key": na["key"], "action": "loyiha"}))
d = J(reg.get(f"/api/orders/{r['order_id']}"))
ok(d["order"]["kind"] == "qabul" and d["all"] == 1 and d["items"][0]["student_id"] == na["student"]["id"], "Qabul buyrug'ida yo'q → tuzatuvchi qabul loyihasi tuzildi")
J(reg.post(f"/api/orders/{r['order_id']}/delete"))

print("— Arizadan buyruq (namuna arizalar) —")
samples = {x["file"]: x for x in m["samples"]}
ok(len([x for x in samples.values() if x["type"] == "ariza"]) >= 5, f"Namuna arizalar: {len(samples)} ta fayl")
for f, x in samples.items():
    if x["type"] != "ariza": continue
    r = J(reg.post(f"/api/orders/intake/sample/{f}"))
    if r["method"] == "manual":
        ok(not m["ocr"], f"{f}: OCR yo'q — qo'lda kiritish taklif qilindi (xato emas)")
        continue
    top = r["candidates"][0]["id"] if r["candidates"] else None
    ok(r["kind"] == x["kind"] and top == x["student_id"], f"{f} ({r['method']}): tur «{r['kind_name']}», talaba topildi, maydonlar {sorted(r['fields'])}")
fam = J(reg.post("/api/orders/intake/sample/ariza_familiya.pdf"))
ok(fam["fields"].get("new_surname") and fam["fields"].get("old_surname") and "guvohnoma" in fam["fields"].get("basis", "").lower(), "Familiya: eski/yangi familiya va asos hujjat (nikoh guvohnomasi) aniqlandi")
cyr = J(reg.post("/api/orders/intake/text", json={"text": "Мен, Каримов Азиз, академик таътил беришингизни сўрайман. 01.12.2026 дан 30.11.2027 гача."}))
ok(cyr["kind"] == "akademik_tatil" and cyr["fields"].get("date_from") == "2026-12-01" and cyr["fields"].get("date_to") == "2027-11-30", "Kirill yozuvidagi ariza ham aniqlanadi")
tk = J(reg.post("/api/orders/intake/text", json={"text": "Men, Aliyev Vali, meni talabalar safiga qayta tiklashingizni so'rayman. IQT-2402 guruhiga, 2026-yil 1-dekabrdan."}))
ok(tk["kind"] == "tiklash" and tk["fields"].get("group_to") == "IQT-2402" and tk["fields"].get("date_from") == "2026-12-01", "Qayta tiklash arizasi: guruh va sana")
ok(reg.post("/api/orders/intake?name=virus.exe", content=b"MZ..", headers={"Content-Type": "application/octet-stream"}).status_code == 400, "Ariza: ruxsat etilmagan format rad etiladi")

print("— To'liq oqim: familiya o'zgarishi → imzo → bazaga ta'sir → bekor qilish —")
busy, anom = busy_ids(), anomaly_ids()
cand = [r for r in q("""SELECT s.id, s.full_name, s.hemis_id, g.name FROM students s JOIN groups_ g ON g.id=s.group_id
                       WHERE s.status='faol' AND s.study_form='kunduzgi' AND s.gender='F' AND s.full_name LIKE '%va %' ORDER BY s.id DESC LIMIT 400""")
        if r[0] not in busy and r[0] not in anom]
st = cand[int(time.time()) % len(cand)]
old_name = st[1]; new_sur = "Testova" if not old_name.startswith("Testova") else "Sinovova"
text = (f"ISFT instituti rektoriga\n{st[3]} guruh talabasi\n{old_name}dan (HEMIS ID: {st[2]})\nARIZA\nMen, {old_name}, turmush qurganligim munosabati bilan "
        f"familiyamni {old_name.split()[0]}dan {new_sur}ga o'zgartirishingizni so'rayman. Nikoh to'g'risidagi guvohnoma I-TN No 7712345, 01.11.2026.")
an_ = J(reg.post("/api/orders/intake/text", json={"text": text}))
ok(an_["kind"] == "familiya" and an_["candidates"][0]["id"] == st[0] and an_["fields"]["new_surname"] == new_sur, "Ariza matni tahlil qilindi: familiya, talaba (HEMIS), yangi familiya")
oid = J(reg.post(f"/api/orders/intake/{an_['app_id']}/order", json={"kind": "familiya", "student_id": st[0], "fields": an_["fields"]}))["id"]
d = J(reg.get(f"/api/orders/{oid}"))
ok(d["order"]["status"] == "loyiha" and d["all"] == 1 and not d["checks"]["errors"], "Loyiha shablondan to'ldirildi, xato yo'q")
ok(rek.post(f"/api/orders/{oid}/sign").status_code == 400, "Loyiha (yuborilmagan) imzolanmaydi")
ok(reg.post(f"/api/orders/{oid}/sign").status_code == 403, "Registrator imzolay olmaydi (403)")
J(reg.post(f"/api/orders/{oid}/submit"))
ok(reg.post(f"/api/orders/{oid}/items", json={"remove": [d["items"][0]["id"]]}).status_code == 400, "Imzoga yuborilgan loyiha o'zgartirilmaydi")
ok(pro.post(f"/api/orders/{oid}/return", json={"note": ""}).status_code == 400, "Qaytarish sababsiz bo'lmaydi")
J(pro.post(f"/api/orders/{oid}/return", json={"note": "Asos hujjat raqamini tekshiring"}))
d = J(reg.get(f"/api/orders/{oid}"))
ok(d["order"]["status"] == "loyiha" and "tekshiring" in (d["order"]["returned_note"] or ""), "Prorektor qaytardi → loyiha, sabab ko'rinadi")
J(reg.post(f"/api/orders/{oid}/submit")); J(pro.post(f"/api/orders/{oid}/forward"))
ok(J(reg.get(f"/api/orders/{oid}"))["order"]["status"] == "kelishilgan", "Prorektor kelishdi")
s = J(rek.post(f"/api/orders/{oid}/sign"))
ok(re.match(r"TB-\d\d/\d{4}$", s["reg_no"]) and s["changed"] == 1, f"Rektor imzoladi: {s['reg_no']}, bazaga ta'sir 1 ta talaba")
nm = q("SELECT full_name FROM students WHERE id=?", (st[0],))[0][0]
ok(nm == " ".join([new_sur] + old_name.split()[1:]), f"F.I.Sh. o'zgardi: {old_name} → {nm}")
ok(q("SELECT old, new FROM student_changes WHERE student_id=? AND field='full_name' ORDER BY id DESC LIMIT 1", (st[0],))[0] == (old_name, nm), "O'zgarishlar jurnali: eski va yangi qiymat")
doc = q("SELECT verify_code, status, file FROM documents WHERE reg_no=?", (s["reg_no"],))
ok(doc and doc[0][1] == "imzolangan", "Hujjatlar reyestriga (documents) yozildi")
v = httpx.get(f"{B}/verify/{doc[0][0]}")
ok(v.status_code == 200 and "rektor imzolagan" in v.text and old_name.split()[1] not in v.text.split("Kimga")[1][:200], "QR tekshiruvi: haqiqiy, shaxsiy ma'lumot qisqartirilgan")
ok(reg.post(f"/api/orders/{oid}/items", json={"remove": [d["items"][0]["id"]]}).status_code == 403, "Imzolangan buyruq ro'yxati muzlatilgan (403, audit)")
dx = reg.get(f"/api/orders/{oid}/docx")
ok(dx.status_code == 200 and zipfile.is_zipfile(io.BytesIO(dx.content)) and s["reg_no"].encode() in zipfile.ZipFile(io.BytesIO(dx.content)).read("word/document.xml"),
   "Imzolangan buyruq DOCX: raqam bilan")
xml = zipfile.ZipFile(io.BytesIO(dx.content)).read("word/document.xml").decode()
ok("Registrator ofisi boshlig" in xml and "dekan" not in xml.lower(), "KELISHILDI: Registrator ofisi boshlig'i va O'quv prorektori (dekan yo'q)")
ann = J(reg.post(f"/api/orders/{oid}/annul", json={"note": "Talaba arizasini qaytarib oldi (test)"}))["id"]
ok(reg.post(f"/api/orders/{oid}/annul", json={"note": "yana bir bor"}).status_code == 400, "Bitta buyruqqa ikkinchi bekor qiluvchi loyiha tuzilmaydi")
J(reg.post(f"/api/orders/{ann}/submit")); s2 = J(rek.post(f"/api/orders/{ann}/sign"))
ok(q("SELECT full_name FROM students WHERE id=?", (st[0],))[0][0] == old_name and s2["reverted"] == 1, f"Tuzatuvchi buyruq {s2['reg_no']}: F.I.Sh. qaytarildi")
ok(q("SELECT status, cancelled_by FROM orders WHERE id=?", (oid,))[0] == ("bekor_qilingan", ann), "Asl buyruq «bekor qilingan», havola saqlangan")
ok(q("SELECT COUNT(*) FROM student_changes WHERE student_id=? AND order_id=? AND reverted=1", (st[0], oid))[0][0] == 1, "Jurnal: o'zgarish «qaytarilgan» deb belgilandi")

print("— Akademik ta'til va guruh o'zgarishi (ta'sir va qaytarish) —")
busy = busy_ids()
s3 = next(r for r in q("SELECT s.id, s.group_id FROM students s WHERE s.status='faol' AND s.study_form='kunduzgi' ORDER BY s.id DESC LIMIT 300") if r[0] not in busy and r[0] not in anom and r[0] != st[0])
o2 = J(reg.post("/api/orders", json={"kind": "akademik_tatil", "students": [{"student_id": s3[0], "data": {"date_from": "2026-12-01", "date_to": "2027-11-30", "reason": "sog'lig'i bo'yicha"}}]}))["id"]
ok(reg.post("/api/orders", json={"kind": "akademik_tatil", "students": [{"student_id": s3[0], "data": {"date_from": "2026-12-01", "date_to": "2026-01-01"}}]}).status_code == 400,
   "Ta'til tugashi boshlanishidan oldin — rad etiladi")
J(reg.post(f"/api/orders/{o2}/submit")); J(rek.post(f"/api/orders/{o2}/sign"))
reg2 = q("SELECT reg_no FROM orders WHERE id=?", (o2,))[0][0]
ok(q("SELECT status FROM students WHERE id=?", (s3[0],))[0][0] == "akademik ta'til" and q("SELECT COUNT(*) FROM student_leaves WHERE student_id=? AND order_no=?", (s3[0], reg2))[0][0] == 1,
   "Akademik ta'til: holat o'zgardi, student_leaves yozuvi buyruq raqami bilan")
a2 = J(reg.post(f"/api/orders/{o2}/annul", json={"note": "test"}))["id"]; J(reg.post(f"/api/orders/{a2}/submit")); J(rek.post(f"/api/orders/{a2}/sign"))
ok(q("SELECT status FROM students WHERE id=?", (s3[0],))[0][0] == "faol" and q("SELECT COUNT(*) FROM student_leaves WHERE student_id=? AND order_no=?", (s3[0], reg2))[0][0] == 0,
   "Bekor qilindi: holat «faol», ta'til yozuvi o'chirildi")
g2 = q("SELECT g2.id, g2.name FROM groups_ g1 JOIN groups_ g2 ON g2.course=g1.course AND g2.form=g1.form AND g2.id!=g1.id WHERE g1.id=? LIMIT 1", (s3[1],))[0]
o3 = J(reg.post("/api/orders", json={"kind": "guruh", "students": [{"student_id": s3[0], "data": {"group_to": g2[1], "reason": "test"}}]}))["id"]
J(reg.post(f"/api/orders/{o3}/submit")); J(rek.post(f"/api/orders/{o3}/sign"))
ok(q("SELECT group_id FROM students WHERE id=?", (s3[0],))[0][0] == g2[0], f"Guruh o'zgarishi: talaba {g2[1]} guruhiga o'tdi")
a3 = J(reg.post(f"/api/orders/{o3}/annul", json={"note": "test"}))["id"]; J(reg.post(f"/api/orders/{a3}/submit")); J(rek.post(f"/api/orders/{a3}/sign"))
ok(q("SELECT group_id FROM students WHERE id=?", (s3[0],))[0][0] == s3[1], "Bekor qilindi: guruh qaytarildi")
h = J(reg.get(f"/api/orders/student/{s3[0]}"))
ok(len([x for x in h["orders"] if x["id"] in (o2, a2, o3, a3)]) == 4 and len(h["changes"]) >= 4, "Talaba tarixi: 4 ta buyruq va o'zgarishlar")
ch = J(reg.get(f"/api/orders/changes/log?q={reg2}"))
ok(ch["total"] >= 1, "O'zgarishlar jurnali buyruq raqami bo'yicha qidiriladi")

print("— Katta ro'yxat: versiyalar, farq, tiklash —")
pool = q("""SELECT s.hemis_id, s.full_name, g.name FROM students s JOIN groups_ g ON g.id=s.group_id WHERE s.status='faol' AND s.study_form='sirtqi'
            ORDER BY s.id LIMIT 40""")
def csv_bytes(rows): return ("﻿№;F.I.Sh.;HEMIS ID;Guruh\n" + "\n".join(f"{i};{r[1]};{r[0]};{r[2]}" for i, r in enumerate(rows, 1))).encode()
v1 = pool[:30] + [("9999999999999", "Noma'lum Talaba Testovich", "IQT-2501")]
o4 = J(sir.post("/api/orders", json={"kind": "chetlashtirish_tolov", "title": "Test: sirtqi qarzdorlar", "params": {"date_from": "2026-12-15"}, "students": []}))["id"]
ok(reg.post(f"/api/orders/{o4}/upload?name=x.pdf", content=b"%PDF", headers={"Content-Type": "application/octet-stream"}).status_code == 400, "Ro'yxat: faqat Excel/CSV")
u1 = J(sir.post(f"/api/orders/{o4}/upload?name=royxat_v1.csv", content=csv_bytes(v1), headers={"Content-Type": "application/octet-stream"}))
ok(u1["version"]["no"] == 1 and u1["version"]["count"] == 31 and u1["version"]["unmatched"] == 1, "1-versiya: 31 qator (30 mos, 1 mos emas)")
kund = q("SELECT s.hemis_id, s.full_name, g.name FROM students s JOIN groups_ g ON g.id=s.group_id WHERE s.study_form='kunduzgi' LIMIT 1")
ok(sir.post(f"/api/orders/{o4}/upload?name=aralash.csv", content=csv_bytes(pool[:3] + kund), headers={"Content-Type": "application/octet-stream"}).status_code == 403,
   "Sirtqi bo'lim: ro'yxatda kunduzgi talaba bo'lsa rad etiladi (403)")
ok(sir.post(f"/api/orders/{o4}/submit").status_code == 400, "Mos kelmagan qator bor — imzoga yuborib bo'lmaydi")
v2 = pool[5:30] + pool[30:32]
u2 = J(reg.post(f"/api/orders/{o4}/upload?name=royxat_v2.csv", content=csv_bytes(v2), headers={"Content-Type": "application/octet-stream"}))
ok(u2["version"]["no"] == 2 and u2["version"]["added"] == 2 and u2["version"]["removed"] == 6, "2-versiya: +2 / −6 (5 talaba + mos kelmagan qator)")
df = J(reg.get(f"/api/orders/{o4}/versions/2/diff"))
ok(df["n_added"] == 2 and df["n_removed"] == 6 and {x["hemis_id"] for x in df["added"]} == {pool[30][0], pool[31][0]}, "Farq: kim qo'shildi / olib tashlandi")
d = J(reg.get(f"/api/orders/{o4}"))
J(reg.post(f"/api/orders/{o4}/items", json={"remove": [d["items"][0]["id"], d["items"][1]["id"]]}))
J(reg.post(f"/api/orders/{o4}/versions/1/restore"))
d = J(reg.get(f"/api/orders/{o4}"))
vs = {v["no"]: v for v in d["versions"]}
ok(d["order"]["version"] == 4 and d["all"] == 31 and vs[4]["restored_from"] == 1 and len(vs) == 4, "1-versiya tiklandi → 4-versiya (tarix o'chmaydi)")
ok(vs[1]["created_by_name"] and vs[2]["filename"] == "royxat_v2.csv", "Versiyada kim yuklagani va fayl nomi saqlanadi")
xl = reg.get(f"/api/orders/{o4}/xlsx?version=2")
ok(xl.status_code == 200 and zipfile.is_zipfile(io.BytesIO(xl.content)), "Versiya ro'yxatini XLSX yuklab olish")
dd = reg.get(f"/api/orders/{o4}/docx")
ok(dd.status_code == 200 and b"LOYIHA" in zipfile.ZipFile(io.BytesIO(dd.content)).read("word/document.xml"), "Loyiha DOCX (oxirgi versiyadan)")
J(reg.post(f"/api/orders/{o4}/delete"))
ok(q("SELECT status FROM orders WHERE id=?", (o4,))[0][0] == "bekor" and q("SELECT COUNT(*) FROM order_versions WHERE order_id=?", (o4,))[0][0] == 4, "Loyiha o'chirildi, versiyalar saqlandi")
bulk = q("SELECT id, version, count FROM orders WHERE demo='bulk'")
if bulk:
    bd = J(reg.get(f"/api/orders/{bulk[0][0]}?limit=5"))
    ok(bd["all"] > 5000 and len(bd["versions"]) >= 2, f"Demo: katta chetlashtirish ro'yxati {bd['all']} ta, {len(bd['versions'])} versiya")

print("— Audit jurnali —")
acts = {r[0] for r in q("SELECT action FROM audit_log WHERE resource='orders' AND allowed=1 AND ts>=?", (T0,))}
ok({"buyruqlar: buyruq imzolandi", "buyruqlar: ro'yxat yuklandi", "buyruqlar: imzoga yuborildi", "buyruqlar: muvofiqlik tuzatishi", "buyruqlar: ariza tahlil qilindi"} <= acts,
   "Har bir amal audit jurnalida (resource=orders)")
print(f"\nJami: {N[0]} tekshiruv · HAMMASI O'TDI")
