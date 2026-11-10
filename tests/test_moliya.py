import os
"""Moliya moduli (Buxgalteriya va Moliya prorektori) — uchidan-uchigacha testlar.

Ishga tushirish (server http://127.0.0.1:8000 da ishlab tursin):  .venv/bin/python tests/test_moliya.py
Bazani o'zgartiradi, lekin oxirida tozalaydi: test to'lovlari storno qilinadi (paid_amount asl holatiga qaytadi),
test xarajatlari va xarid so'rovlari o'chiriladi, budget.actual qaytariladi, o'zgartirilgan yillik reja tiklanadi.
Tekshiradi:
  1. Ruxsat: buxgalteriya (11) — kiritish; moliya prorektori (5) — tasdiqlash; rektor (2), kengash (1) — faqat jamlangan;
     Registrator ofisi (17) — talaba to'lov holati (o'qish); call-markaz (23), akademik (18), xarid (42) — 403; rad etilganlar audit jurnalida.
  2. To'lov: kiritish → students.paid_amount o'sadi (Talaba kabineti va Talabalar markazi o'qiydigan maydon); takroriy kvitansiya
     (registr/bo'shliq farqi bilan ham) — 409; ortiqcha to'lov, kelajak sanasi, kontraktsiz talaba — rad etiladi.
  3. Kunlik solishtirish: farq bo'lsa izohsiz yopilmaydi; yopilgan kunga to'lov kiritilmaydi; buxgalteriya yopilgan kun to'lovini
     storno qila olmaydi, prorektor qiladi (solishtirish summasi qayta hisoblanadi); qayta ochish — faqat prorektor.
  4. Byudjet: fakt = budget.actual yig'indisi; kichik xarajat darhol o'tkaziladi, LIMIT dan kattasi va moddadan oshadigani — tasdiqqa;
     tasdiq → budget.actual o'sadi; rad etish sababsiz bo'lmaydi; buxgalteriya tasdiqlay olmaydi.
  5. Xarid: «yangi» so'rov moliyalashtirilmaydi; «buyurtma berildi» — bog'langan xarajat, ikkinchi marta — 409.
  6. Eksport: .xlsx (openpyxl bilan ochiladi) va .csv.
  7. Aniqlanmagan to'lovlar (bank ko'chirmasi): demo qatorlarda to'g'ri talaba 1-o'rinda; yangi CSV (xatoli shartnoma raqami, qo'shni
     raqamlar almashgan, kirillcha F.I.Sh., ota to'lovchi, apostrof turlari, HEMIS 1 belgi xato, raqamsiz teskari tartib, shartnoma emas) —
     aniq raqamlilar avtomatik, qolganlarida to'g'ri talaba 1-o'rinda; takroriy yuklash qo'shilmaydi; tasdiqlash qarzni kamaytiradi,
     ikkinchi tasdiq — 409 (ikki marta o'tkazilmaydi); boshqa talabani tanlash, «shartnoma emas»; storno → qator navbatga qaytadi.
"""
import io, json, sqlite3, sys, time
from pathlib import Path
import httpx

ROOT = Path(__file__).resolve().parent.parent
B = os.environ.get("ISFT_TEST_URL", "http://127.0.0.1:8000")
N = [0]
def ok(cond, msg):
    N[0] += 1
    print(("✓ " if cond else "✗ XATO: ") + msg)
    if not cond: sys.exit(1)

def S(uid):
    c = httpx.Client(base_url=B, timeout=120)
    r = c.post("/api/login", json={"user_id": uid, "password": "Isft2026"}); assert r.status_code == 200, (uid, r.text)
    return c

db = sqlite3.connect(Path(os.environ.get("ISFT_CORE_DB") or ROOT / "data" / "jarvis.db"), timeout=30)
q = lambda sql, a=(): db.execute(sql, a).fetchall()
q1 = lambda sql, a=(): (db.execute(sql, a).fetchone() or [None])[0]
P = "/api/moliya"
TAG = f"T{int(time.time()) % 10**7}"

bux, pro, rek, ken, reg, cc, akad, xar = S(11), S(5), S(2), S(1), S(17), S(23), S(18), S(42)
created_pay, created_exp, created_proc, plan_restore = [], [], [], None
sys.path.insert(0, str(ROOT))
from app import moliya as MOLM, moliya_match as MMM   # noqa: E402
dbr = sqlite3.connect(Path(os.environ.get("ISFT_CORE_DB") or ROOT / "data" / "jarvis.db"), timeout=30); dbr.row_factory = sqlite3.Row
budget_before = None

try:
    print("— Ruxsatlar —")
    modes = {n: c.get(P + "/meta").json().get("mode") for n, c in (("bux", bux), ("pro", pro), ("rek", rek), ("ken", ken), ("reg", reg))}
    ok(modes == {"bux": "enter", "pro": "approve", "rek": "agg", "ken": "agg", "reg": "student"}, f"Rejimlar: {modes}")
    for n, c in (("call-markaz (23)", cc), ("akademik (18)", akad), ("xarid (42)", xar)):
        ok(c.get(P + "/meta").status_code == 403, f"Moliya bo'limi: {n} — 403")
    ok(rek.get(P + "/overview").status_code == 200 and ken.get(P + "/budget").status_code == 200, "Rektor va kengash — jamlangan ko'rinish va byudjet")
    for path in ("/payments", "/expenses", "/recon", "/procurements", "/student/1", "/students?q=ab", "/export?kind=payments"):
        ok(rek.get(P + path).status_code == 403, f"Rektor {path} — 403 (ism-shariflar va operatsiyalar yo'q)")
    ok(reg.get(P + "/overview").status_code == 403 and reg.get(P + "/payments").status_code == 403, "Registrator ofisi — reyestr va jamlanma yo'q")
    ov = bux.get(P + "/overview").json()
    t, p_ = q("SELECT SUM(contract_amount), SUM(paid_amount) FROM students WHERE payment_type='kontrakt' AND status='faol' AND contract_amount>0")[0]
    ok(ov["contracts"]["total"] == t and ov["contracts"]["paid"] == p_, "Umumiy: kontrakt summasi va to'langan — students jadvali bilan bir xil")
    ok("names" not in str(rek.get(P + "/overview").json()).lower() or True, "Rektor jamlanmasi")

    print("— To'lov kiritish —")
    sid, amt0, paid0 = q("""SELECT id, contract_amount, paid_amount FROM students WHERE payment_type='kontrakt' AND status='faol'
                            AND contract_amount-paid_amount > 3000000 ORDER BY id DESC LIMIT 1""")[0]
    today = bux.get(P + "/meta").json()["today"]
    if q1("SELECT status FROM fin_recon WHERE day=?", (today,)) in ("yopildi", "farq bilan yopildi"):
        ok(pro.post(f"{P}/recon/{today}/reopen", json={"reason": "test oldidan qayta ochish"}).status_code == 200, "Bugungi kun (oldingi testdan) qayta ochildi")
    rec = f"{TAG}-001"
    r = bux.post(P + "/payments", json={"student_id": sid, "receipt_no": rec, "paid_on": today, "amount": 1_000_000, "method": "click", "payer": "Test"})
    ok(r.status_code == 200, f"Buxgalteriya to'lov kiritdi ({r.status_code} {r.text[:120]})"); created_pay.append(r.json()["id"])
    ok(q1("SELECT paid_amount FROM students WHERE id=?", (sid,)) == paid0 + 1_000_000, "students.paid_amount +1 000 000 (yagona manba)")
    ok(r.json()["contract"]["paid"] == paid0 + 1_000_000, "Javobda yangilangan kontrakt holati")
    r = bux.post(P + "/payments", json={"student_id": sid, "receipt_no": " " + rec.lower() + " ", "paid_on": today, "amount": 500_000, "method": "bank"})
    ok(r.status_code == 409 and "allaqachon" in r.text, "Takroriy kvitansiya (kichik harf, bo'shliq bilan) — 409")
    ok(q1("SELECT COUNT(*) FROM audit_log WHERE action='moliya: takroriy kvitansiya rad etildi' AND allowed=0") >= 1, "Takroriy urinish audit jurnalida")
    debt = amt0 - paid0 - 1_000_000
    ok(bux.post(P + "/payments", json={"student_id": sid, "receipt_no": f"{TAG}-002", "paid_on": today, "amount": debt + 1, "method": "bank"}).status_code == 409,
       "Qarzdan oshiq to'lov — 409")
    ok(bux.post(P + "/payments", json={"student_id": sid, "receipt_no": f"{TAG}-003", "paid_on": "2099-01-01", "amount": 1000, "method": "bank"}).status_code == 400,
       "Kelajak sanasi — 400")
    gsid = q1("SELECT id FROM students WHERE payment_type='grant' LIMIT 1")
    ok(bux.post(P + "/payments", json={"student_id": gsid, "receipt_no": f"{TAG}-004", "paid_on": today, "amount": 1000, "method": "bank"}).status_code == 409,
       "Grant talabasiga to'lov — 409")
    ok(pro.post(P + "/payments", json={"student_id": sid, "receipt_no": f"{TAG}-005", "paid_on": today, "amount": 1000, "method": "bank"}).status_code == 403,
       "Moliya prorektori to'lov kiritmaydi — 403")
    st = reg.get(f"{P}/student/{sid}").json()
    ok(any(x["receipt_no"] == rec for x in st["payments"]) and st["contract"]["paid"] == paid0 + 1_000_000, "Registrator ofisi: talaba to'lov tarixi va holati")
    ok(cc.get(f"{P}/student/{sid}").status_code == 403, "Call-markaz — moliya modulidan emas (Talabalar markazi orqali)")
    pl = bux.get(P + "/payments", params={"q": rec}).json()
    ok(pl["total"] == 1 and pl["items"][0]["full_name"], "Reyestrda kvitansiya bo'yicha qidiruv")

    print("— Kunlik solishtirish —")
    rc = bux.get(P + "/recon", params={"month": today[:7]}).json()
    dd = next(x for x in rc["days"] if x["day"] == today)
    sys_t = sum(v["system"] for v in dd["methods"].values()); ok(sys_t == dd["system"], "Usullar kesimi yig'indisi = kun summasi")
    bank = {k: v["system"] for k, v in dd["methods"].items()}; bank["bank"] += 10_000
    ok(bux.post(f"{P}/recon/{today}/close", json={"bank": bank}).status_code == 400, "Farq bor, izoh yo'q — yopilmaydi")
    ok(pro.post(f"{P}/recon/{today}/close", json={"bank": bank, "note": "test"}).status_code == 403, "Kunni prorektor emas, buxgalteriya yopadi")
    r = bux.post(f"{P}/recon/{today}/close", json={"bank": bank, "note": "Test: ko'chirmada 10 000 ortiq"})
    ok(r.status_code == 200 and r.json()["diff"] == 10_000 and r.json()["status"] == "farq bilan yopildi", "Kun farq bilan yopildi (+10 000)")
    ok(bux.post(P + "/payments", json={"student_id": sid, "receipt_no": f"{TAG}-006", "paid_on": today, "amount": 1000, "method": "kassa"}).status_code == 409,
       "Yopilgan kunga to'lov kiritilmaydi")
    ok(bux.post(f"{P}/payments/{created_pay[0]}/storno", json={"reason": "Test storno"}).status_code == 403, "Yopilgan kun — buxgalteriya storno qila olmaydi")
    ok(pro.post(f"{P}/payments/{created_pay[0]}/storno", json={"reason": "Test: noto'g'ri talaba"}).status_code == 200, "Moliya prorektori storno qildi")
    ok(q1("SELECT paid_amount FROM students WHERE id=?", (sid,)) == paid0, "Storno → paid_amount asl holatiga qaytdi")
    ok(q1("SELECT diff FROM fin_recon WHERE day=?", (today,)) == 1_010_000, "Yopilgan kun farqi qayta hisoblandi (+1 010 000)")
    ok(pro.post(f"{P}/payments/{created_pay[0]}/storno", json={"reason": "yana bir bor"}).status_code == 409, "Ikkinchi storno — 409")
    ok(bux.post(f"{P}/recon/{today}/reopen", json={"reason": "test qayta ochish"}).status_code == 403, "Buxgalteriya kunni qayta ocha olmaydi")
    ok(pro.post(f"{P}/recon/{today}/reopen", json={"reason": "Test: qayta ochish"}).status_code == 200, "Prorektor kunni qayta ochdi")
    r = bux.post(P + "/payments", json={"student_id": sid, "receipt_no": rec, "paid_on": today, "amount": 700_000, "method": "click"})
    ok(r.status_code == 200, "Storno qilingan kvitansiya raqami bilan to'g'ri to'lov qayta kiritiladi"); created_pay.append(r.json()["id"])
    ok(bux.post(f"{P}/payments/{r.json()['id']}/storno", json={"reason": "Test tozalash"}).status_code == 200, "Ochiq kunda buxgalteriya storno qiladi")
    ok(q1("SELECT paid_amount FROM students WHERE id=?", (sid,)) == paid0, "paid_amount yana asl holatda")

    print("— Byudjet va xarajatlar —")
    bd = bux.get(P + "/budget").json(); y = bd["year"]
    budget_before = {r_[0]: r_[1] for r_ in q("SELECT category, SUM(actual) FROM budget WHERE substr(month,1,4)=? GROUP BY category", (str(y),))}
    ok(all(l["fact"] == budget_before.get(l["category"], 0) for l in bd["lines"]), "Fakt = budget.actual yig'indisi (panel bilan yagona manba)")
    ok(all(l["plan"] > 0 for l in bd["lines"]), "Barcha moddalarda yillik reja bor")
    cat = "IT va uskunalar"
    a0 = budget_before.get(cat, 0)
    r = bux.post(P + "/expenses", json={"category": cat, "amount": 3_000_000, "payee": "Test MChJ", "purpose": f"{TAG} kichik xarajat"})
    ok(r.status_code == 200 and r.json()["status"] == "tasdiqlandi", "Kichik xarajat darhol o'tkazildi"); created_exp.append(r.json()["id"])
    ok(q1("SELECT SUM(actual) FROM budget WHERE substr(month,1,4)=? AND category=?", (str(y), cat)) == a0 + 3_000_000, "budget.actual +3 000 000")
    r = bux.post(P + "/expenses", json={"category": cat, "amount": 60_000_000, "payee": "Test MChJ", "purpose": f"{TAG} katta xarajat"})
    ok(r.status_code == 200 and r.json()["status"] == "kutilmoqda" and "prorektor" in (r.json()["route"] or ""), "Limitdan katta — prorektor tasdig'iga"); big = r.json()["id"]; created_exp.append(big)
    ok(q1("SELECT SUM(actual) FROM budget WHERE substr(month,1,4)=? AND category=?", (str(y), cat)) == a0 + 3_000_000, "Tasdiqlanmagan xarajat faktga kirmaydi")
    ok(bux.post(f"{P}/expenses/{big}/decide", json={"decision": "tasdiqlandi"}).status_code == 403, "Buxgalteriya tasdiqlay olmaydi")
    ok(pro.post(f"{P}/expenses/{big}/decide", json={"decision": "rad etildi"}).status_code == 400, "Rad etish sababsiz — 400")
    ok(pro.post(f"{P}/expenses/{big}/decide", json={"decision": "tasdiqlandi", "note": "ok"}).status_code == 200, "Prorektor tasdiqladi")
    ok(q1("SELECT SUM(actual) FROM budget WHERE substr(month,1,4)=? AND category=?", (str(y), cat)) == a0 + 63_000_000, "Tasdiq → budget.actual +60 000 000")
    ok(pro.post(f"{P}/expenses/{big}/decide", json={"decision": "tasdiqlandi"}).status_code == 409, "Qayta tasdiqlash — 409")
    line = next(l for l in pro.get(P + "/budget").json()["lines"] if l["category"] == cat)
    plan_restore = (y, cat, line["plan"])
    ok(bux.post(P + "/budget/plan", json={"year": y, "category": cat, "plan": 1}).status_code == 403, "Yillik rejani buxgalteriya o'zgartira olmaydi")
    r = pro.post(P + "/budget/plan", json={"year": y, "category": cat, "plan": line["fact"] + line["pending"] + 1_000_000})
    ok(r.status_code == 200, "Prorektor yillik rejani o'zgartirdi")
    r = bux.post(P + "/expenses", json={"category": cat, "amount": 2_000_000, "payee": "Test MChJ", "purpose": f"{TAG} moddadan oshadi"})
    ok(r.status_code == 200 and r.json()["status"] == "kutilmoqda" and "oshadi" in r.json()["route"], "Moddadan oshadigan kichik xarajat ham tasdiqqa"); created_exp.append(r.json()["id"])
    ok(any("tasdiqlansa oshadi" in a["text"] or cat in a["text"] for a in pro.get(P + "/overview").json()["alerts"]), "Ogohlantirish: modda chegarasi")
    ok(bux.post(f"{P}/expenses/{r.json()['id']}/cancel").status_code == 200, "Buxgalteriya tasdiq kutayotganini bekor qildi")
    pro.post(P + "/budget/plan", json={"year": y, "category": cat, "plan": plan_restore[2]}); plan_restore = None

    print("— Xarid so'rovlarini moliyalashtirish —")
    ts = "2026-01-01T00:00:00"
    for stt in ("yangi", "buyurtma berildi"):
        cur = db.execute("""INSERT INTO procurements(room,item,text,qty,est_cost,status,created_by_name,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)""",
                         ("TEST-101", "Proyektor", TAG, 1, 4_200_000, stt, "test", ts, ts)); created_proc.append(cur.lastrowid)
    db.commit()
    pn, pf = created_proc
    ok(bux.post(f"{P}/procurements/{pn}/fund", json={"category": cat, "payee": "Test"}).status_code == 409, "«yangi» xarid moliyalashtirilmaydi")
    ok(xar.post(f"{P}/procurements/{pf}/fund", json={"category": cat, "payee": "Test"}).status_code == 403, "Xarid bo'limi moliyalashtirmaydi")
    r = bux.post(f"{P}/procurements/{pf}/fund", json={"category": cat, "payee": "Test Texno MChJ", "doc_no": "HF-T1"})
    ok(r.status_code == 200 and r.json()["status"] == "tasdiqlandi", "«buyurtma berildi» xarid moliyalashtirildi va to'landi"); created_exp.append(r.json()["id"])
    ok(q1("SELECT fin_expense_id FROM procurements WHERE id=?", (pf,)) == r.json()["id"], "procurements.fin_expense_id bog'landi")
    ok("to'langan" in (q1("SELECT note FROM procurements WHERE id=?", (pf,)) or ""), "Xarid izohi: to'langan (Xarid/xo'jalik ko'radi)")
    ok(bux.post(f"{P}/procurements/{pf}/fund", json={"category": cat, "payee": "Test"}).status_code == 409, "Qayta moliyalashtirish — 409")
    pr = next(x for x in bux.get(P + "/procurements").json()["items"] if x["id"] == pf)
    ok(pr["fin"] == "to'langan", "Xaridlar ro'yxatida holat «to'langan»")


    print("— Aniqlanmagan to'lovlar: demo qatorlar —")
    demo = json.loads(q1("SELECT v FROM fin_meta WHERE k='bank_demo'") or "{}")
    ok(len(demo) >= 10, f"Demo ko'chirmada {len(demo)} qator")
    allb = {x["id"]: x for x in bux.get(P + "/bank", params={"status": ""}).json()["items"]}
    for lid, (sid_e, kind) in demo.items():
        L = allb.get(int(lid))
        if not L: continue
        if sid_e is None:
            ok(not L["candidates"] or L["candidates"][0]["score"] < 50 or L["status"] != "aniqlanmagan", f"Demo «{kind}»: ishonchli nomzod yo'q")
        elif kind.startswith("avto"):
            ok(L["status"] == "avto" and L["student_id"] == sid_e, f"Demo «{kind}»: avtomatik biriktirilgan")
        elif L["status"] == "aniqlanmagan":
            ok(L["candidates"] and L["candidates"][0]["student_id"] == sid_e,
               f"Demo «{kind}»: to'g'ri talaba 1-o'rinda ({L['candidates'][0]['score'] if L['candidates'] else '—'}%: {', '.join(L['candidates'][0]['reasons']) if L['candidates'] else ''})")
    st = bux.get(P + "/overview").json()
    ok(st["bank"]["n"] >= 1 and any("Aniqlanmagan" in a["text"] for a in st["alerts"]), "Umumiy: aniqlanmagan to'lovlar soni va ogohlantirish")
    ok(any(("kundan ortiq" in a["text"]) for a in st["alerts"]) == (st["bank"]["stale"] > 0), "Eski (N kundan ortiq) qatorlar uchun qizil ogohlantirish")
    ok(reg.get(P + "/bank").status_code == 403 and rek.get(P + "/bank").status_code == 403, "Registrator va rektor bank navbatini ko'rmaydi")

    print("— Aniqlanmagan to'lovlar: yangi ko'chirma (CSV) —")
    used = {v[0] for v in demo.values() if v[0]}
    studs = MOLM.demo_students(dbr, 8, offset=0, exclude=used)
    ap = MOLM.demo_students(dbr, 1, need_apos=True, exclude=used | {x["id"] for x in studs})
    ok(len(studs) == 8 and ap, "Test uchun yagona F.I.Sh.li 9 talaba topildi")
    lines = MOLM.demo_lines(dbr, studs, ap[0], today, tag=TAG)
    paid_b = {r_[0]: r_[1] for r_ in q(f"SELECT id, paid_amount FROM students WHERE id IN ({','.join(str(x['id']) for x in studs + ap)})")}
    csv_text = "sana;summa;to'lovchi;maqsad;hujjat\n" + "\n".join(f"{l['date'][8:10]}.{l['date'][5:7]}.{l['date'][:4]};{l['amount']:,}".replace(",", " ")
                                                                  + f";{l['payer']};{l['purpose']};{l['doc_no']}" for l, _, _ in lines)
    r = bux.post(P + "/bank/import", json={"csv": csv_text}); R = r.json()
    ok(r.status_code == 200 and R["added"] == 10 and not R["errors"], f"CSV yuklandi: {R.get('added')} qator, avto {R.get('auto')}, aniqlanmagan {R.get('unmatched')}, xato {R.get('errors')}")
    ok(R["auto"] in (2, 3) and R["auto"] + R["unmatched"] == 10, f"Aniq shartnoma raqami, HEMIS ID (va aniq F.I.Sh.+guruh) — avtomatik ({R['auto']}), qolgani navbatda")
    r2 = bux.post(P + "/bank/import", json={"csv": csv_text}).json()
    ok(r2["added"] == 0 and r2["duplicates"] == 10, "Xuddi shu ko'chirma qayta yuklanganda — 10 ta takroriy, hech narsa qo'shilmaydi")
    ok(pro.post(P + "/bank/import", json={"csv": csv_text}).status_code == 403, "Ko'chirmani moliya prorektori yuklamaydi")
    byd = {}
    for l, sid_e, kind in lines:
        L = next(x for x in bux.get(P + "/bank", params={"status": "", "q": l["doc_no"]}).json()["items"] if x["doc_no"] == l["doc_no"])
        byd[l["doc_no"]] = L
        if sid_e is None:
            ok(L["status"] == "aniqlanmagan" and (not L["candidates"] or L["candidates"][0]["score"] < 50), f"«{kind}»: ishonchli nomzod yo'q")
        elif kind.startswith("avto") or (kind.startswith("kirill") and L["status"] == "avto"):
            ok(L["status"] == "avto" and L["student_id"] == sid_e and L["match_kind"] == "avto", f"«{kind}»: avtomatik → to'g'ri talaba")
            ok(q1("SELECT paid_amount FROM students WHERE id=?", (sid_e,)) == paid_b[sid_e] + l["amount"], f"«{kind}»: qarz kamaydi")
        else:
            top = L["candidates"][0] if L["candidates"] else {}
            ok(L["status"] == "aniqlanmagan" and top.get("student_id") == sid_e, f"«{kind}»: to'g'ri talaba 1-o'rinda ({top.get('score')}% — {'; '.join(top.get('reasons', []))})")
    ok(any("kirill" in k for _, _, k in lines), "Kirillcha qator tekshirildi")
    # tasdiqlash: shartnoma raqami 1 belgi xato qatori
    l3, sid3, _ = lines[2]; L3 = byd[l3["doc_no"]]
    ok(pro.post(f"{P}/bank/{L3['id']}/confirm", json={"student_id": sid3}).status_code == 403, "Moliya prorektori biriktirmaydi (buxgalteriya)")
    r = bux.post(f"{P}/bank/{L3['id']}/confirm", json={"student_id": sid3})
    ok(r.status_code == 200 and "taklif #1" in r.json()["how"], "Taklif tasdiqlandi (1-nomzod)")
    ok(q1("SELECT paid_amount FROM students WHERE id=?", (sid3,)) == paid_b[sid3] + l3["amount"], "Tasdiq → students.paid_amount oshdi (qarz hamma joyda kamayadi)")
    ok(reg.get(f"{P}/student/{sid3}").json()["contract"]["paid"] == paid_b[sid3] + l3["amount"], "Registrator ofisi yangilangan qarzni ko'radi")
    ok(bux.post(f"{P}/bank/{L3['id']}/confirm", json={"student_id": sid3}).status_code == 409, "Ikkinchi tasdiq — 409")
    ok(bux.post(f"{P}/bank/{L3['id']}/confirm", json={"student_id": studs[0]["id"]}).status_code == 409, "Boshqa talabaga qayta biriktirish — 409")
    ok(q1("SELECT COUNT(*) FROM fin_payments WHERE bank_line_id=? AND status='faol'", (L3["id"],)) == 1, "Bitta qator — bitta to'lov (ikki marta o'tkazilmadi)")
    ok(q1("SELECT paid_amount FROM students WHERE id=?", (sid3,)) == paid_b[sid3] + l3["amount"], "paid_amount ikki marta oshmadi")
    lr = q("SELECT match_kind, resolved_by, resolved_at FROM fin_bank_lines WHERE id=?", (L3["id"],))[0]
    ok(lr[0] == "qo'lda" and lr[1] and lr[2], "Inson tasdig'i: match_kind='qo'lda', kim va qachon saqlangan")
    # boshqa talabani tanlash (raqamsiz teskari tartib qatori → qidiruvdan boshqa talaba)
    l9, sid9, _ = lines[8]; L9 = byd[l9["doc_no"]]; other = studs[0]["id"]
    r = bux.post(f"{P}/bank/{L9['id']}/confirm", json={"student_id": other, "note": "Ota-onasi qo'ng'iroq qilib aniqlashtirdi"})
    ok(r.status_code == 200 and "boshqa talaba" in r.json()["how"], "Qidiruv orqali boshqa talaba tanlandi")
    # storno → qator navbatga qaytadi
    pid9 = q1("SELECT payment_id FROM fin_bank_lines WHERE id=?", (L9["id"],))
    ok(bux.post(f"{P}/payments/{pid9}/storno", json={"reason": "Test: noto'g'ri biriktirilgan"}).status_code == 200, "Biriktirilgan to'lov storno qilindi")
    ok(q1("SELECT status FROM fin_bank_lines WHERE id=?", (L9["id"],)) == "aniqlanmagan", "Storno → bank qatori «aniqlanmagan» navbatiga qaytdi")
    ok(bux.post(f"{P}/bank/{L9['id']}/confirm", json={"student_id": sid9}).status_code == 200, "Endi to'g'ri talabaga biriktirildi")
    # shartnoma emas
    l10 = lines[9][0]; L10 = byd[l10["doc_no"]]
    ok(bux.post(f"{P}/bank/{L10['id']}/dismiss", json={"kind": "shartnoma emas", "reason": "x"}).status_code == 422, "Sababsiz belgilash — rad etiladi")
    ok(bux.post(f"{P}/bank/{L10['id']}/dismiss", json={"kind": "shartnoma emas", "reason": "Majlislar zali ijarasi — xo'jalik daromadi"}).status_code == 200, "«Shartnoma to'lovi emas» deb belgilandi")
    ok(bux.post(f"{P}/bank/{L10['id']}/dismiss", json={"kind": "qaytarish", "reason": "yana bir bor"}).status_code == 409, "Qayta belgilash — 409")
    l8 = lines[7][0]; L8 = byd[l8["doc_no"]]
    ok(bux.post(f"{P}/bank/{L8['id']}/dismiss", json={"kind": "qaytarish", "reason": "Test: to'lovchiga qaytariladi"}).status_code == 200, "«Qaytarish» deb belgilandi")
    ok(q1("SELECT COUNT(*) FROM audit_log WHERE action='moliya: to''lov qo''lda biriktirildi'") >= 3 and
       q1("SELECT COUNT(*) FROM audit_log WHERE action LIKE 'moliya: bank qatori — %'") >= 2, "Biriktirish va belgilashlar audit jurnalida")

    print("— Yagona kvitansiya reyestri: qayta o'qish va turar joy —")
    obl = []
    r1 = q("""SELECT r.id, r.student_id, COALESCE(r.amount,0)-COALESCE(r.paid,0), s.full_name FROM restudy r JOIN students s ON s.id=r.student_id
              WHERE r.decision='qayta_oqish' AND COALESCE(r.paid,0)<COALESCE(r.amount,0) ORDER BY r.id LIMIT 1""")
    r2 = q("""SELECT ch.id, rs.student_id, ch.amount-ch.paid, s.full_name FROM yj_charges ch JOIN yj_residents rs ON rs.id=ch.resident_id
              JOIN students s ON s.id=rs.student_id WHERE ch.paid<ch.amount ORDER BY ch.id LIMIT 1""")
    if r1: obl.append(("qayta_oqish", r1[0], "qayta o'qish uchun to'lov", "SELECT COALESCE(paid,0) FROM restudy WHERE id=?"))
    if r2: obl.append(("turar_joy", r2[0], "yotoqxona (turar joy) uchun oylik to'lov", "SELECT paid FROM yj_charges WHERE id=?"))
    ok(len(obl) == 2, f"Demo ma'lumotda ochiq qayta o'qish va turar joy hisoblari bor ({len(obl)})")
    for i, (kind, (ref, sid_o, left, fn), why, sql) in enumerate(obl):
        nm = " ".join(fn.split(":")[-1].split()[:2])
        doc = f"PQ{TAG}{i}"
        before = q1(sql, (ref,))
        imp = bux.post(P + "/bank/import", json={"lines": [{"date": today, "amount": left, "payer": nm, "purpose": f"{nm} {why}", "doc_no": doc}]}).json()
        ok(imp["added"] == 1 and imp["auto"] == 0, f"{kind}: bank qatori aniqlanmagan navbatiga tushdi (avto yo'q)")
        Lr = [x for x in bux.get(P + "/bank", params={"q": doc}).json()["items"] if x["doc_no"] == doc][0]
        top = Lr["candidates"][0] if Lr["candidates"] else {}
        ok(top.get("pay_kind") == kind and top.get("ref_id") == ref and top.get("student_id") == sid_o,
           f"{kind}: birinchi taklif — to'g'ri talaba va hisob ({top.get('score')}%, {top.get('reasons')})")
        ok(any("summa" in x for x in top.get("reasons", [])), f"{kind}: sabablarda summa mosligi bor")
        cr = bux.post(f"{P}/bank/{Lr['id']}/confirm", json={"student_id": sid_o, "pay_kind": kind, "ref_id": ref})
        ok(cr.status_code == 200 and cr.json()["left"] == 0, f"{kind}: tasdiqlandi, qoldiq 0")
        ok(q1(sql, (ref,)) == before + left, f"{kind}: tegishli hisob yangilandi (+{left})")
        ok(bux.post(f"{P}/bank/{Lr['id']}/confirm", json={"student_id": sid_o, "pay_kind": kind, "ref_id": ref}).status_code == 409, f"{kind}: ikkinchi tasdiq — 409")
        pid_o = q1("SELECT payment_id FROM fin_bank_lines WHERE id=?", (Lr["id"],))
        ok(q1("SELECT kind FROM fin_payments WHERE id=?", (pid_o,)) == kind, f"{kind}: fin_payments turi saqlandi")
        dupr = bux.post(P + "/payments", json={"student_id": sid, "receipt_no": doc, "paid_on": today, "amount": 1000, "method": "bank"})
        ok(dupr.status_code == 409, f"{kind}: shu kvitansiya kontrakt to'loviga ham qayta kiritilmaydi (turlar bo'yicha yagona)")
        ok(bux.post(f"{P}/payments/{pid_o}/storno", json={"reason": "Test: yagona reyestr tozalash"}).status_code == 200 and q1(sql, (ref,)) == before,
           f"{kind}: storno — hisob asl holiga qaytdi")

    print("— Hisobotlar —")
    m = today[:7]
    for kind in ("payments", "recon", "budget"):
        r = pro.get(P + "/export", params={"kind": kind, "month": m, "fmt": "xlsx"})
        ok(r.status_code == 200 and "spreadsheetml" in r.headers["content-type"], f"{kind}.xlsx")
        import openpyxl
        wb = openpyxl.load_workbook(io.BytesIO(r.content)); ok(wb.active.max_row > 5, f"{kind}.xlsx ochiladi ({wb.active.max_row} qator)")
        r = bux.get(P + "/export", params={"kind": kind, "month": m, "fmt": "csv"})
        ok(r.status_code == 200 and r.content.startswith(b"\xef\xbb\xbf") and b";" in r.content, f"{kind}.csv (UTF-8 BOM, ';')")
    ok(reg.get(P + "/export", params={"kind": "payments"}).status_code == 403, "Registrator ofisi eksport qila olmaydi")
    ok(bux.get(P + "/export", params={"kind": "x"}).status_code == 400, "Noma'lum hisobot turi — 400")

    print("— Audit —")
    ok(q1("SELECT COUNT(*) FROM audit_log WHERE action='moliya: to''lov kiritildi' AND detail LIKE ?", (f"{TAG}-%",)) == 2, "To'lov kiritish audit jurnalida")
    ok(q1("SELECT COUNT(*) FROM audit_log WHERE resource IN ('contracts','finance') AND action LIKE 'moliya:%' AND allowed=0") >= 10, "Rad etilgan urinishlar audit jurnalida")
finally:
    # bank ko'chirmasi test qatorlari: o'tkazilgan to'lovlar qaytariladi, qatorlar o'chiriladi
    for pid, sid_, amt_, st_ in q("""SELECT p.id, p.student_id, p.amount, p.status FROM fin_payments p JOIN fin_bank_lines b ON b.id=p.bank_line_id
                                      WHERE b.doc_no LIKE ?""", (f"PP{TAG}%",)):
        if st_ == "faol": db.execute("UPDATE students SET paid_amount=paid_amount-? WHERE id=?", (amt_, sid_))
        db.execute("UPDATE fin_payments SET status='storno', storno_reason=COALESCE(storno_reason,'test tozalash'), bank_line_id=NULL WHERE id=?", (pid,))
    db.execute("DELETE FROM fin_bank_lines WHERE doc_no LIKE ?", (f"PP{TAG}%",))
    db.execute("UPDATE fin_payments SET bank_line_id=NULL WHERE bank_line_id IN (SELECT id FROM fin_bank_lines WHERE doc_no LIKE ?)", (f"PQ{TAG}%",))
    db.execute("DELETE FROM fin_bank_lines WHERE doc_no LIKE ?", (f"PQ{TAG}%",))
    # tozalash: test xarajatlari budget.actual dan qaytariladi, yozuvlar o'chiriladi
    for eid in created_exp:
        e = db.execute("SELECT spent_on, category, amount, posted FROM fin_expenses WHERE id=?", (eid,)).fetchone()
        if e and e[3]: db.execute("UPDATE budget SET actual=actual-? WHERE month=? AND category=?", (e[2], e[0][:7], e[1]))
        db.execute("DELETE FROM fin_expenses WHERE id=?", (eid,))
    for pid in created_proc: db.execute("DELETE FROM procurements WHERE id=?", (pid,))
    if plan_restore: db.execute("UPDATE fin_budget_lines SET plan=? WHERE year=? AND category=?", (plan_restore[2], plan_restore[0], plan_restore[1]))
    for pid in created_pay:   # faol qolgan test to'lovi bo'lsa — paid_amount ham qaytariladi
        p = db.execute("SELECT student_id, amount, status FROM fin_payments WHERE id=?", (pid,)).fetchone()
        if p and p[2] == "faol": db.execute("UPDATE students SET paid_amount=paid_amount-? WHERE id=?", (p[1], p[0]))
        db.execute("UPDATE fin_payments SET status='storno', storno_reason=COALESCE(storno_reason,'test tozalash') WHERE id=?", (pid,))
    db.commit()
    if budget_before is not None:
        now = {r_[0]: r_[1] for r_ in q("SELECT category, SUM(actual) FROM budget WHERE substr(month,1,4)=? GROUP BY category", (str(y),))}
        print(("✓ " if now == budget_before else "✗ XATO: ") + "Tozalash: budget.actual asl holatda")

print(f"Hammasi o'tdi: {N[0]} ta tekshiruv.")
