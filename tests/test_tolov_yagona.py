import os
"""Yagona to'lov reyestri (W6): Talaba harakati (qayta o'qish) va Yoshlar (turar joy) to'lovlari Moliya'ning yagona kvitansiya
reyestri (app/moliya.py _post_payment) orqali o'tadi. Uchidan-uchigacha HTTP testlar (server ishlab turishi kerak).

Ishga tushirish:  ISFT_TEST_URL=http://127.0.0.1:8000 ISFT_CORE_DB=data/jarvis.db .venv/bin/python tests/test_tolov_yagona.py
Qamrov:
  * qayta o'qish to'lovi (POST /api/flows/restudy/{rid}/pay, buxgalteriya) → fin_payments da BITTA yozuv (turi «qayta_oqish», ref_id),
    restudy.paid yangilanadi, kontrakt (students.paid_amount) o'zgarmaydi; Moliya reyestri, talaba to'lov tarixi, ochiq hisoblar va
    Talaba kartasi (360°) shu to'lovni bir martadan ko'rsatadi;
  * turar joy to'lovi (POST /api/yoshlar/charges/{cid}/pay, komendant/buxgalteriya) → xuddi shunday (turi «turar_joy», yj_charges.paid);
  * kvitansiya raqami barcha turlar bo'yicha yagona: modul ichida ham, modullar o'rtasida ham takror → 409 (yozuv qo'shilmaydi);
  * qoldiqdan oshgan summa, to'liq to'langan hisob, ruxsatsiz lavozimlar; storno hisobni tiklaydi (Moliya'dan);
  * kontrakt to'lovi talaba kartasidagi qarzni kamaytiradi; kunlik solishtirish va «Bugun» ko'rsatkichi barcha turlarni qamraydi.
Test o'z to'lovlarini oxirida storno qiladi (balanslar tiklanadi; storno yozuvlari «TEST» izohi bilan qoladi).
"""
import sqlite3, sys, time
from pathlib import Path
import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT)); from app import clock as CLK   # noqa: E402
DB = Path(os.environ.get("ISFT_CORE_DB") or ROOT / "data" / "jarvis.db")
B = os.environ.get("ISFT_TEST_URL", "http://127.0.0.1:8000")
PW = "Isft2026"
N = [0]
TODAY = CLK.today().isoformat()
MINE = []          # test yaratgan to'lovlar (oxirida storno)

def ok(cond, msg):
    N[0] += 1
    print(("✓ " if cond else "✗ XATO: ") + msg)
    if not cond:
        cleanup(); sys.exit(1)

def S(uid):
    c = httpx.Client(base_url=B, timeout=120)
    r = c.post("/api/login", json={"user_id": uid, "password": PW})
    assert r.status_code == 200, f"login {uid}: {r.status_code} {r.text}"
    return c

def q(sql, args=()):
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True, timeout=30)
    con.row_factory = sqlite3.Row
    try: return [dict(r) for r in con.execute(sql, args).fetchall()]
    finally: con.close()

def q1(sql, args=()):
    r = q(sql, args); return next(iter(r[0].values())) if r else None

def J(r, code=200):
    assert r.status_code == code, f"{r.request.method} {r.request.url.path}: {r.status_code} {r.text[:400]}"
    return r.json()

def uid(role):
    return q1("SELECT id FROM users WHERE role=? AND COALESCE(active,1)=1 ORDER BY id LIMIT 1", (role,))

def cleanup():
    for pid in MINE:
        try:
            if q1("SELECT status FROM fin_payments WHERE id=?", (pid,)) == "faol":
                pro.post(f"{M}/payments/{pid}/storno", json={"reason": "TEST: yagona reyestr testi — tozalash"})
        except Exception as e:
            print("  (tozalash:", e, ")")
    MINE.clear()

M, F, Y, K = "/api/moliya", "/api/flows", "/api/yoshlar", "/api/karta"
bux, pro, kom, reg, man = (S(uid(r)) for r in ("buxgalteriya", "prorektor_moliya", "komendant", "talabalar", "manaviyat"))
STAMP = time.strftime("%H%M%S")
REC = {k: f"TEST{k}{STAMP}" for k in ("QO1", "QO2", "TJ1", "TJ2", "KT1")}

def fin_rows(rec): return q("SELECT * FROM fin_payments WHERE receipt_no=?", (rec,))
def reg_items(rec, **kw): return J(bux.get(M + "/payments", params={"q": rec, **kw}))
def card(sid): return J(reg.get(f"{K}/{sid}"))

# bugungi kun yopilgan bo'lsa (oldingi test) — qayta ochamiz, aks holda to'lov kiritilmaydi
if q1("SELECT status FROM fin_recon WHERE day=?", (TODAY,)) in ("yopildi", "farq bilan yopildi"):
    J(pro.post(f"{M}/recon/{TODAY}/reopen", json={"reason": "TEST: yagona reyestr testi oldidan"}))
    print("  (bugungi kun qayta ochildi)")

# ---------------------------------------------------------------------------------------------
print("— 1. Qayta o'qish to'lovi Talaba harakati orqali → yagona reyestr")
R = q("""SELECT r.id, r.student_id, r.subject, r.amount, COALESCE(r.paid,0) paid FROM restudy r JOIN students s ON s.id=r.student_id
         WHERE r.decision='qayta_oqish' AND COALESCE(r.paid,0) + 2000 <= COALESCE(r.amount,0) ORDER BY r.id LIMIT 1""")
ok(bool(R), "Seed'da to'lanmagan qayta o'qish hisobi bor")
R = R[0]; rid, sid = R["id"], R["student_id"]
P0 = q1("SELECT paid_amount FROM students WHERE id=?", (sid,))
debt0 = card(sid)["base"]["debt"]
left0 = R["amount"] - R["paid"]; half = left0 // 2
ob = J(bux.get(f"{M}/obligations/{sid}"))["items"]
ok(any(o["kind"] == "qayta_oqish" and o["ref_id"] == rid and o["left"] == left0 for o in ob), f"Moliya: ochiq hisoblarda «{R['subject']}» — qoldiq {left0}")

ok(reg.post(f"{F}/restudy/{rid}/pay", json={"amount": half, "receipt": REC["QO1"]}).status_code == 403, "Registrator ofisi qayta o'qish to'lovini kirita olmaydi → 403")
r = J(bux.post(f"{F}/restudy/{rid}/pay", json={"amount": half, "receipt": REC["QO1"].lower(), "method": "click"}))
MINE.append(r["payment_id"])
ok(r["ok"] and r["receipt_no"] == REC["QO1"] and r["paid"] == R["paid"] + half, f"Buxgalteriya: qayta o'qish to'lovi qabul qilindi ({half} so'm, kvitansiya normallashtirildi)")
fr = fin_rows(REC["QO1"])
ok(len(fr) == 1, "fin_payments: aynan BITTA yozuv (takror yo'q)")
fr = fr[0]
ok(fr["id"] == r["payment_id"] and fr["kind"] == "qayta_oqish" and fr["ref_id"] == rid and fr["student_id"] == sid and fr["amount"] == half
   and fr["method"] == "click" and fr["status"] == "faol" and fr["paid_on"] == TODAY, "fin_payments: turi «qayta_oqish», ref_id, talaba, summa, usul, sana to'g'ri")
ok(q1("SELECT paid FROM restudy WHERE id=?", (rid,)) == R["paid"] + half, "restudy.paid bir marta oshdi")
ok(q1("SELECT paid_amount FROM students WHERE id=?", (sid,)) == P0, "Kontrakt to'lovi (students.paid_amount) o'zgarmadi")
ok(q1("SELECT COUNT(*) FROM audit_log WHERE action='moliya: to''lov kiritildi' AND detail LIKE ?", (f"{REC['QO1']}%",)) == 1
   and q1("SELECT COUNT(*) FROM audit_log WHERE action='talaba harakati: qayta o''qish to''lovi' AND detail LIKE ?", (f"%{REC['QO1']}%",)) == 1,
   "Audit: Moliya va Talaba harakati yozuvlari (bittadan)")
# Moliya reyestri
d = reg_items(REC["QO1"])
ok(d["total"] == 1 and d["items"][0]["kind"] == "qayta_oqish" and d["items"][0]["kind_label"] == "Qayta o'qish" and d["items"][0]["id"] == fr["id"],
   "Moliya reyestri: bitta yozuv, turi «Qayta o'qish»")
ok(reg_items(REC["QO1"], kind="qayta_oqish")["total"] == 1 and reg_items(REC["QO1"], kind="kontrakt")["total"] == 0, "Moliya reyestri: tur filtri (qayta o'qish — bor, kontrakt — yo'q)")
st = J(bux.get(f"{M}/student/{sid}"))
mine = [p for p in st["payments"] if p["receipt_no"] == REC["QO1"]]
ok(len(mine) == 1 and mine[0].get("kind") == "qayta_oqish" and mine[0].get("kind_label") == "Qayta o'qish", "Moliya: talaba to'lov tarixida bir marta, turi bilan (kontrakt bilan aralashmaydi)")
ok(st["contract"] is None or st["contract"]["paid"] == P0, "Moliya: talabaning kontrakt holati o'zgarmadi")
ob = J(bux.get(f"{M}/obligations/{sid}"))["items"]
ok(any(o["ref_id"] == rid and o["left"] == left0 - half for o in ob), f"Moliya: ochiq hisob qoldig'i {left0 - half} ga kamaydi")
# Talaba kartasi
cd = card(sid)
ok(sum(p["receipt_no"] == REC["QO1"] for p in cd["payments"]) == 1 and next(p for p in cd["payments"] if p["receipt_no"] == REC["QO1"])["kind"] == "qayta_oqish",
   "Talaba kartasi: to'lov bir marta, turi «qayta_oqish»")
ok(any(x["subject"] == R["subject"] and x["paid"] == R["paid"] + half for x in cd["restudy"]), "Talaba kartasi: qayta o'qish qatorida to'langan summa yangilandi")
ok(cd["base"]["debt"] == debt0 and cd["base"]["student"]["paid_amount"] == P0, "Talaba kartasi: kontrakt qarzi o'zgarmadi")
fl = J(bux.get(f"{F}/restudy"))
ok(any(x["id"] == rid and x["paid"] == R["paid"] + half for x in fl["items"]), "Talaba harakati ro'yxati (buxgalteriya): to'langan summa yangilandi")

print("\n— 2. Takroriy kvitansiya va noto'g'ri summa — yozuv qo'shilmaydi")
ok(bux.post(f"{F}/restudy/{rid}/pay", json={"amount": 1000, "receipt": REC["QO1"]}).status_code == 409, "Talaba harakati: o'sha kvitansiya qayta → 409")
ok(bux.post(f"{F}/restudy/{rid}/pay", json={"amount": 1000, "receipt": " " + REC["QO1"].lower() + " "}).status_code == 409, "Talaba harakati: bo'shliq/kichik harf bilan takror → 409")
ok(bux.post(M + "/payments", json={"student_id": sid, "receipt_no": REC["QO1"], "paid_on": TODAY, "amount": 1000, "method": "bank"}).status_code == 409,
   "Moliya: o'sha kvitansiya kontrakt sifatida → 409 (raqam barcha turlar bo'yicha yagona)")
ok(bux.post(f"{F}/restudy/{rid}/pay", json={"amount": left0 - half + 1, "receipt": REC["QO2"]}).status_code == 409, "Qoldiqdan oshgan summa → 409")
ok(bux.post(f"{F}/restudy/{rid}/pay", json={"amount": 0, "receipt": REC["QO2"]}).status_code == 400, "Nol summa → 400")
ok(len(fin_rows(REC["QO1"])) == 1 and not fin_rows(REC["QO2"]) and q1("SELECT paid FROM restudy WHERE id=?", (rid,)) == R["paid"] + half,
   "Rad etilgan urinishlardan keyin: reyestr va restudy.paid o'zgarmagan")
# qolganini Moliya'ning o'zidan (shu hisobga) to'lash — bitta reyestr
r = J(bux.post(M + "/payments", json={"student_id": sid, "receipt_no": REC["QO2"], "paid_on": TODAY, "amount": left0 - half, "method": "payme",
                                       "kind": "qayta_oqish", "ref_id": rid}))
MINE.append(r["id"])
ok(r["kind"] == "qayta_oqish" and r["left"] == 0 and q1("SELECT paid FROM restudy WHERE id=?", (rid,)) == R["amount"], "Moliya'dan qolgan qism to'landi — hisob yopildi")
ok(not any(o["ref_id"] == rid and o["kind"] == "qayta_oqish" for o in J(bux.get(f"{M}/obligations/{sid}"))["items"]), "Ochiq hisoblar ro'yxatidan chiqdi")
ok(bux.post(f"{F}/restudy/{rid}/pay", json={"amount": 1000, "receipt": f"TESTQO3{STAMP}"}).status_code == 409, "To'liq to'langan hisobga yana to'lov → 409")
cd = card(sid)
ok(sorted(p["receipt_no"] for p in cd["payments"] if p["receipt_no"] in (REC["QO1"], REC["QO2"])) == sorted([REC["QO1"], REC["QO2"]]),
   "Talaba kartasi: ikkala to'lov bir martadan")
ok(q1("SELECT paid_amount FROM students WHERE id=?", (sid,)) == P0, "Kontrakt summasi hamon o'zgarmagan")

# ---------------------------------------------------------------------------------------------
print("\n— 3. Turar joy to'lovi Yoshlar orqali → yagona reyestr")
C = q("""SELECT ch.id, ch.period, ch.amount, ch.paid, rs.student_id FROM yj_charges ch JOIN yj_residents rs ON rs.id=ch.resident_id
         WHERE ch.paid + 2000 <= ch.amount ORDER BY ch.id LIMIT 1""")
ok(bool(C), "Seed'da to'lanmagan turar joy hisobi bor")
C = C[0]; cid, sid2 = C["id"], C["student_id"]
P2 = q1("SELECT paid_amount FROM students WHERE id=?", (sid2,))
debt2 = card(sid2)["base"]["debt"]
tleft = C["amount"] - C["paid"]; part = tleft // 2
ok(man.post(f"{Y}/charges/{cid}/pay", json={"amount": part, "receipt": REC["TJ1"]}).status_code == 403, "Ma'naviyat bo'limi to'lov kirita olmaydi → 403")
ok(kom.post(M + "/payments", json={"student_id": sid2, "receipt_no": REC["TJ1"], "paid_on": TODAY, "amount": part, "method": "kassa", "kind": "turar_joy"}).status_code == 403,
   "Komendant Moliya reyestriga to'g'ridan-to'g'ri kirita olmaydi → 403")
r = J(kom.post(f"{Y}/charges/{cid}/pay", json={"amount": part, "receipt": REC["TJ1"]}))
MINE.append(r["payment_id"])
ok(r["ok"] and r["receipt_no"] == REC["TJ1"] and r["paid"] == C["paid"] + part and r["left"] == tleft - part, f"Komendant: turar joy to'lovi ({part} so'm)")
fr = fin_rows(REC["TJ1"])
ok(len(fr) == 1, "fin_payments: aynan BITTA yozuv")
fr = fr[0]
ok(fr["kind"] == "turar_joy" and fr["ref_id"] == cid and fr["student_id"] == sid2 and fr["amount"] == part and fr["method"] == "kassa" and fr["status"] == "faol",
   "fin_payments: turi «turar_joy», ref_id = hisob, usul — kassa (komendant)")
ch = q("SELECT paid, receipt, by_user FROM yj_charges WHERE id=?", (cid,))[0]
ok(ch["paid"] == C["paid"] + part and ch["receipt"] == REC["TJ1"] and ch["by_user"] == uid("komendant"), "yj_charges: to'langan summa, kvitansiya va kim kiritgani")
ok(q1("SELECT paid_amount FROM students WHERE id=?", (sid2,)) == P2, "Kontrakt (students.paid_amount) o'zgarmadi")
d = reg_items(REC["TJ1"])
ok(d["total"] == 1 and d["items"][0]["kind"] == "turar_joy" and d["items"][0]["kind_label"] == "Turar joy", "Moliya reyestri: bitta yozuv, turi «Turar joy»")
ok(reg_items(REC["TJ1"], kind="turar_joy")["total"] == 1 and reg_items(REC["TJ1"], kind="qayta_oqish")["total"] == 0, "Moliya reyestri: tur filtri")
ob = J(bux.get(f"{M}/obligations/{sid2}"))["items"]
ok(any(o["kind"] == "turar_joy" and o["ref_id"] == cid and o["left"] == tleft - part for o in ob), f"Moliya: turar joy hisobi qoldig'i {tleft - part}")
mine = [p for p in J(bux.get(f"{M}/student/{sid2}"))["payments"] if p["receipt_no"] == REC["TJ1"]]
ok(len(mine) == 1 and mine[0].get("kind") == "turar_joy", "Moliya: talaba to'lov tarixida bir marta, turi bilan")
cd = card(sid2)
ok(sum(p["receipt_no"] == REC["TJ1"] for p in cd["payments"]) == 1 and next(p for p in cd["payments"] if p["receipt_no"] == REC["TJ1"])["kind"] == "turar_joy",
   "Talaba kartasi: to'lov bir marta, turi «turar_joy»")
ok(any(x["id"] == cid and x["paid"] == C["paid"] + part for x in cd.get("dorm_charges", [])), "Talaba kartasi: turar joy hisobi qoldig'i yangilandi")
ok(cd["base"]["debt"] == debt2, "Talaba kartasi: kontrakt qarzi o'zgarmadi")
yl = J(kom.get(f"{Y}/charges", params={"period": C["period"]}))
ok(any(x["id"] == cid and x["paid"] == C["paid"] + part for x in yl["items"]), "Yoshlar «To'lovlar» bo'limi: summa yangilandi")
# takrorlar
ok(kom.post(f"{Y}/charges/{cid}/pay", json={"amount": 1000, "receipt": REC["TJ1"]}).status_code == 409, "Yoshlar: o'sha kvitansiya qayta → 409")
ok(kom.post(f"{Y}/charges/{cid}/pay", json={"amount": 1000, "receipt": REC["QO1"]}).status_code == 409, "Yoshlar: qayta o'qish kvitansiyasi bilan → 409 (modullararo yagona raqam)")
ok(bux.post(f"{F}/restudy/{rid}/pay", json={"amount": 1, "receipt": REC["TJ1"]}).status_code == 409, "Talaba harakati: turar joy kvitansiyasi bilan → 409")
ok(kom.post(f"{Y}/charges/{cid}/pay", json={"amount": tleft - part + 1, "receipt": REC["TJ2"]}).status_code in (400, 409), "Qoldiqdan oshgan summa → rad etildi")
ok(len(fin_rows(REC["TJ1"])) == 1 and not fin_rows(REC["TJ2"]) and q1("SELECT paid FROM yj_charges WHERE id=?", (cid,)) == C["paid"] + part,
   "Rad etilgan urinishlardan keyin: reyestr va yj_charges o'zgarmagan")
# qolgan qism — buxgalteriya (Yoshlar orqali, usul — bank)
r = J(bux.post(f"{Y}/charges/{cid}/pay", json={"receipt": REC["TJ2"]}))
MINE.append(r["payment_id"])
ok(r["left"] == 0 and fin_rows(REC["TJ2"])[0]["method"] == "bank" and fin_rows(REC["TJ2"])[0]["amount"] == tleft - part,
   "Buxgalteriya: qolgan qism (summasiz — to'liq qoldiq), usul — bank")
ok(not any(o["ref_id"] == cid and o["kind"] == "turar_joy" for o in J(bux.get(f"{M}/obligations/{sid2}"))["items"]), "Turar joy hisobi ochiq hisoblardan chiqdi")
ok(kom.post(f"{Y}/charges/{cid}/pay", json={"amount": 1, "receipt": f"TESTTJ3{STAMP}"}).status_code == 400, "To'liq to'langan oyga yana to'lov → 400")

# ---------------------------------------------------------------------------------------------
print("\n— 4. Kontrakt to'lovi va storno — talaba kartasi va Moliya bir xil balansni ko'rsatadi")
KT = q("""SELECT id FROM students WHERE status='faol' AND payment_type='kontrakt' AND COALESCE(contract_amount,0) - COALESCE(paid_amount,0) >= 5000
          AND id NOT IN (?, ?) ORDER BY id LIMIT 1""", (sid, sid2))[0]["id"]
c0 = card(KT); m0 = J(bux.get(f"{M}/student/{KT}"))["contract"]
ok(c0["base"]["debt"] == m0["debt"] and c0["base"]["student"]["paid_amount"] == m0["paid"], f"#{KT}: kartadagi va Moliya'dagi kontrakt qarzi bir xil ({m0['debt']})")
r = J(bux.post(M + "/payments", json={"student_id": KT, "receipt_no": REC["KT1"], "paid_on": TODAY, "amount": 5000, "method": "bank"}))
MINE.append(r["id"])
c1 = card(KT); m1 = J(bux.get(f"{M}/student/{KT}"))["contract"]
ok(c1["base"]["debt"] == c0["base"]["debt"] - 5000 == m1["debt"] and c1["base"]["student"]["paid_amount"] == m1["paid"] == m0["paid"] + 5000,
   "Kontrakt to'lovi: kartada va Moliya'da qarz 5 000 ga kamaydi")
ok(next(p for p in c1["payments"] if p["receipt_no"] == REC["KT1"])["kind"] == "kontrakt", "Kartada turi «kontrakt»")
# storno: turar joy → yj_charges, qayta o'qish → restudy, kontrakt → paid_amount
tj1 = fin_rows(REC["TJ1"])[0]["id"]
J(bux.post(f"{M}/payments/{tj1}/storno", json={"reason": "TEST: turar joy storno"}))
ok(q1("SELECT paid FROM yj_charges WHERE id=?", (cid,)) == C["amount"] - part and q1("SELECT paid_amount FROM students WHERE id=?", (sid2,)) == P2,
   "Turar joy storno: yj_charges qaytarildi, kontrakt tegilmadi")
cd = card(sid2)
ok(next(p for p in cd["payments"] if p["receipt_no"] == REC["TJ1"])["status"] == "storno" and any(x["id"] == cid and x["paid"] == C["amount"] - part for x in cd["dorm_charges"]),
   "Talaba kartasi: storno holati va turar joy qoldig'i")
qo1 = fin_rows(REC["QO1"])[0]["id"]
J(bux.post(f"{M}/payments/{qo1}/storno", json={"reason": "TEST: qayta o'qish storno"}))
ok(q1("SELECT paid FROM restudy WHERE id=?", (rid,)) == R["amount"] - half and q1("SELECT paid_amount FROM students WHERE id=?", (sid,)) == P0,
   "Qayta o'qish storno: restudy.paid qaytarildi, kontrakt tegilmadi")
ok(any(o["ref_id"] == rid and o["left"] == half for o in J(bux.get(f"{M}/obligations/{sid}"))["items"]), "Storno'dan keyin hisob yana ochiq (qoldiq qaytdi)")
ok(bux.post(f"{M}/payments/{qo1}/storno", json={"reason": "TEST: ikkinchi storno"}).status_code == 409, "Ikkinchi storno → 409 (balans ikki marta ayirilmaydi)")
ok(q1("SELECT paid FROM restudy WHERE id=?", (rid,)) == R["amount"] - half, "restudy.paid ikkinchi stornoda o'zgarmadi")

# ---------------------------------------------------------------------------------------------
print("\n— 5. Kunlik solishtirish va «Bugun» — barcha turlar bitta reyestrda")
rc = J(bux.get(f"{M}/recon", params={"month": TODAY[:7]}))
day = next((x for x in rc["days"] if x["day"] == TODAY), None)
s_all = q1("SELECT COALESCE(SUM(amount),0) FROM fin_payments WHERE status='faol' AND paid_on=?", (TODAY,))
n_all = q1("SELECT COUNT(*) FROM fin_payments WHERE status='faol' AND paid_on=?", (TODAY,))
ok(day is not None and day["system"] == s_all and day["n"] == n_all, f"Solishtirish: bugungi tizim summasi barcha turlarni qamraydi ({n_all} ta, {s_all} so'm)")
ok(sum(m["system"] for m in day["methods"].values()) == s_all, "Solishtirish: usullar kesimi yig'indisi = kun summasi")
bg = J(bux.get("/api/bugun"))
k = next(k for k in bg["kpis"] if k["label"] == "Bugun kiritilgan to'lovlar")
ok(k["value"] == n_all, f"«Bugun»: kiritilgan to'lovlar = {n_all} (qayta o'qish va turar joy ham)")
ok(all(q1("SELECT COUNT(*) FROM fin_payments WHERE receipt_no=?", (rec,)) <= 1 for rec in REC.values()), "Har bir test kvitansiyasi reyestrda ko'pi bilan bir marta")

cleanup()
ok(q1("SELECT COUNT(*) FROM fin_payments WHERE receipt_no IN (?,?,?,?,?) AND status='faol'", tuple(REC.values())) == 0, "Tozalash: test to'lovlari storno qilindi")
ok(q1("SELECT paid FROM restudy WHERE id=?", (rid,)) == R["paid"] and q1("SELECT paid FROM yj_charges WHERE id=?", (cid,)) == C["paid"]
   and q1("SELECT paid_amount FROM students WHERE id=?", (KT,)) == m0["paid"], "Tozalash: restudy, yj_charges va kontrakt balanslari asl holatida")
print(f"\nHammasi o'tdi: {N[0]} ta tekshiruv.")
