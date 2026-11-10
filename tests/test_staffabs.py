import os
"""Xodimlar ta'tili (app/staff_absence.py): uchidan-uchigacha HTTP testlar (server http://127.0.0.1:8000 da ishlab turishi kerak).

Ishga tushirish:  .venv/bin/python tests/test_staffabs.py
Qayta ishga tushirish mumkin (qayta seed shart emas): test o'z yozuvlarini 3–5 hafta keyingi oynada (demo yozuvlar bilan kesishmaydigan
o'qituvchilar uchun) yaratadi, oxirida API orqali bekor qiladi va izdan tozalash uchun bazadan o'chiradi (faqat izohida test belgisi bor
yozuvlar, ularning o'rinbosarliklari va asos fayllari); yaratilgan buyruq loyihasi Hujjatlar markazida bekor qilinadi.
Demo yozuvlar faqat o'qiladi.
"""
import datetime as dt, sqlite3, sys, time
from pathlib import Path
import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT)); from app import clock as CLK   # noqa: E402 — institut vaqti (ISFT_CORE_TZ / ISFT_CORE_FAKE_TODAY), server bilan bir xil
DB = Path(os.environ.get("ISFT_CORE_DB") or ROOT / "data" / "jarvis.db")
B = os.environ.get("ISFT_TEST_URL", "http://127.0.0.1:8000")
PW = "Isft2026"
TAG = f"[test {time.strftime('%Y%m%d-%H%M%S')}]"
N = [0]
MADE, DOCS = [], []

def ok(cond, msg):
    N[0] += 1
    print(("✓ " if cond else "✗ XATO: ") + msg)
    if not cond: sys.exit(1)

def S(uid):
    c = httpx.Client(base_url=B, timeout=60)
    r = c.post("/api/login", json={"user_id": uid, "password": PW})
    assert r.status_code == 200, f"login {uid}: {r.status_code} {r.text}"
    return c

def q(sql, args=()):
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    try: return con.execute(sql, args).fetchall()
    finally: con.close()

kadr, kaf4, kaf2, akad, rektor, pro, teacher, reg, buxg = (S(i) for i in (12, 14, 31, 18, 2, 3, 15, 17, 11))
AUDIT0 = q("SELECT COALESCE(MAX(id),0) FROM audit_log")[0][0]
T0 = CLK.now().isoformat(timespec="seconds")
today = dt.date.fromisoformat(kadr.get("/api/me").json()["today"])
mon = today + dt.timedelta(days=(7 - today.weekday()) % 7 + 21)          # 3–4 hafta keyingi dushanba
W0, W1 = mon.isoformat(), (mon + dt.timedelta(days=4)).isoformat()    # dushanba–juma

def free_teacher(dep, skip=()):
    """Kafedraning darsi bor, test oynasida yo'qligi bo'lmagan o'qituvchisi."""
    for tid, name, pos in q("""SELECT t.id, t.full_name, t.position FROM teachers t JOIN schedule s ON s.teacher_id=t.id WHERE t.department_id=? AND t.position!='Kafedra mudiri'
                               GROUP BY t.id ORDER BY COUNT(*) DESC""", (dep,)):
        if tid in skip: continue
        if q("SELECT 1 FROM staff_absences WHERE teacher_id=? AND status='faol' AND start<=? AND end>=?", (tid, W1, W0)): continue
        if len(q("SELECT 1 FROM teachers WHERE full_name=?", (name,))) > 1: continue
        st = [x for x in kadr.get("/api/staffabs/staff", params={"q": name}).json() if x["teacher_id"] == tid]
        if st: return tid, st[0]
    raise SystemExit(f"kafedra {dep}: mos o'qituvchi topilmadi")

def cleanup():
    print("\n— Tozalash —")
    for aid in MADE:
        r = kadr.post(f"/api/staffabs/{aid}/cancel", json={"note": "test yakuni"})
        print(f"  #{aid} bekor: {r.status_code}")
    for oid in DOCS:   # «Buyruqlar»dagi test loyihasi o'chiriladi (versiya/jurnal saqlanadi)
        print(f"  buyruq loyihasi #{oid} o'chirildi: {kadr.post(f'/api/orders/{oid}/delete').status_code}")
    # izsiz qoldirish: faqat shu test belgisi bor yozuvlar (asos fayllari diskdan ham)
    con = sqlite3.connect(DB, timeout=30)
    try:
        ids = [r[0] for r in con.execute("SELECT id FROM staff_absences WHERE note LIKE ?", (f"%{TAG}%",))]
        if ids:
            ph = ",".join("?" * len(ids))
            for (stored,) in con.execute(f"SELECT stored FROM staff_abs_files WHERE absence_id IN ({ph})", ids):
                (ROOT / "data" / "staffabs_files" / stored).unlink(missing_ok=True)
            con.execute(f"DELETE FROM staff_abs_files WHERE absence_id IN ({ph})", ids)
            con.execute(f"DELETE FROM staff_subs WHERE absence_id IN ({ph})", ids)
            con.execute(f"DELETE FROM staff_absences WHERE id IN ({ph})", ids)
            con.commit()
        print(f"  bazadan o'chirildi: {len(ids)} ta test yozuvi")
    finally:
        con.close()

def main():
    print(f"Test oynasi: {W0} — {W1}")
    # ============================================================== 1. Rollar va menyu
    print("— 1. Rollar —")
    modes = {u: S(u).get("/api/staffabs/meta").json()["mode"] for u in (12, 14, 31, 18, 2, 3, 15, 17, 11)}
    ok(modes == {12: "full", 14: "kaf", 31: "kaf", 18: "all", 2: "all", 3: "all", 15: "own", 17: "own", 11: "own"}, f"rejimlar: {modes}")
    js, html = httpx.get(f"{B}/app.js").text, httpx.get(f"{B}/index.html").text
    ok('data-v="staffabs"' in html and "staffabs.js" in html, "index.html: menyu bandi va skript")
    ok('["kadrlar", "kafedra", "akademik", "rektor", "prorektor_oquv", "oqituvchi"]' in js and "renderStaffabs" in js, "app.js: menyu faqat kerakli lavozimlarga, go() ulangan")
    ok(kadr.get("/api/staffabs/staff", params={"q": "Karimov"}).json(), "kadrlar: xodim qidiruvi")
    for c, n in ((kaf4, "kafedra"), (akad, "akademik"), (rektor, "rektor")):
        ok(c.get("/api/staffabs/staff", params={"q": "Karimov"}).status_code == 403, f"{n}: xodim qidiruvi 403")

    # ============================================================== 2. Yaratish
    print("— 2. Ro'yxatga olish —")
    tA, sA = free_teacher(2)
    tX, sX = free_teacher(2, skip=(tA,))
    body = {"staff_id": sA["id"], "kind": "safar", "start": W0, "end": W1, "note": f"Konferensiya {TAG}"}
    for c, n in ((kaf2, "kafedra mudiri"), (akad, "akademik"), (rektor, "rektor"), (teacher, "o'qituvchi")):
        ok(c.post("/api/staffabs", json=body).status_code == 403, f"{n}: yaratish 403")
    ok(kadr.post("/api/staffabs", json={**body, "kind": "dam"}).status_code == 400, "noto'g'ri tur — 400")
    ok(kadr.post("/api/staffabs", json={**body, "start": W1, "end": W0}).status_code == 400, "tugash < boshlanish — 400")
    ok(kadr.post("/api/staffabs", json={**body, "staff_id": 0}).status_code == 400, "xodimsiz — 400")
    r = kadr.post("/api/staffabs", json=body); ok(r.status_code == 200 and r.json()["lessons"] > 0, f"safar ro'yxatga olindi: {r.json()}")
    A = r.json()["id"]; MADE.append(A)
    ok(kadr.post("/api/staffabs", json={**body, "kind": "kasallik"}).status_code == 409, "shu davrda ikkinchi yozuv — 409")
    expected = sum(q("SELECT COUNT(*) FROM schedule WHERE teacher_id=? AND weekday=?", (tA, d))[0][0] for d in range(5))
    ok(r.json()["lessons"] == expected, f"ta'sir: {expected} ta dars (5 kun × haftalik jadval)")

    # ============================================================== 3. Ko'rinish (RBAC)
    print("— 3. Ko'rinish —")
    def ids(c, **p): return {x["id"]: x for x in c.get("/api/staffabs", params={"period": "all", **p}).json()["items"]}
    ok(A in ids(kadr) and ids(kadr)[A]["note"].startswith("Konferensiya"), "kadrlar: yozuv va izoh ko'rinadi")
    for c, n in ((kaf2, "o'z kafedrasi mudiri"), (akad, "akademik"), (rektor, "rektor"), (pro, "o'quv prorektori")):
        x = ids(c).get(A); ok(x is not None and x["note"] is None, f"{n}: yozuv ko'rinadi, izoh yashirin")
    ok(A not in ids(kaf4), "boshqa kafedra mudiri: ko'rinmaydi")
    ok(kaf4.get(f"/api/staffabs/{A}").status_code == 403, "boshqa kafedra mudiri: tafsilot 403")
    ok(all(x["own"] for x in ids(teacher).values()) and A not in ids(teacher), "o'qituvchi: faqat o'z yozuvlari")
    ok(ids(reg) == {} or all(x["own"] for x in ids(reg).values()), "Registrator: faqat o'ziniki (bo'lsa)")
    ok(set(ids(kadr, kind="safar")) >= {A} and A not in ids(kadr, kind="kasallik"), "tur filtri")
    ok(A in ids(kadr, dept=2) and A not in ids(kadr, dept=4), "kafedra filtri")
    ok(A in {x["id"] for x in kadr.get("/api/staffabs", params={"period": "upcoming"}).json()["items"]}, "«Kelgusi» davrida")
    ok(kadr.get("/api/staffabs", params={"period": "active", "dept": ""}).status_code == 200, "bo'sh dept parametri — 200")
    d = kaf2.get(f"/api/staffabs/{A}").json()
    ok(d["can_assign"] and not d["can_edit"] and len(d["lesson_list"]) == expected and d["file_list"] == [], "kafedra mudiri: o'rinbosar tayinlaydi, tahrir yo'q, asos hujjat yo'q")
    ok(not akad.get(f"/api/staffabs/{A}").json()["can_assign"], "akademik: faqat ko'radi")

    # ============================================================== 4. O'rinbosar
    print("— 4. O'rinbosar —")
    L = d["lesson_list"][0]
    sg = kaf2.get(f"/api/staffabs/{A}/suggest", params={"sched_id": L["sched_id"], "date": L["date"]}).json()["items"]
    ok(sg, f"tavsiyalar: {len(sg)} ta")
    wd, slot = dt.date.fromisoformat(L["date"]).weekday(), L["slot"]
    ok(all(not q("SELECT 1 FROM schedule WHERE teacher_id=? AND weekday=? AND slot=?", (x["teacher_id"], wd, slot)) for x in sg), "tavsiya etilganlar shu parada bo'sh")
    ok(not sg[0]["other_kafedra"] and all(x["teacher_id"] != tA for x in sg), "birinchi tavsiya — o'sha kafedradan, yo'qlikdagi o'qituvchi emas")
    ok(teacher.get(f"/api/staffabs/{A}/suggest", params={"sched_id": L["sched_id"], "date": L["date"]}).status_code == 403, "o'qituvchi: tavsiya 403")
    sub = {"sched_id": L["sched_id"], "date": L["date"], "teacher_id": sg[0]["teacher_id"], "note": "test"}
    for c, n in ((kaf4, "boshqa kafedra"), (akad, "akademik"), (kadr, "kadrlar"), (rektor, "rektor")):
        ok(c.post(f"/api/staffabs/{A}/subs", json=sub).status_code == 403, f"{n}: tayinlash 403")
    busy_t = q("SELECT teacher_id FROM schedule WHERE weekday=? AND slot=? AND teacher_id IN (SELECT id FROM teachers WHERE department_id=2) AND teacher_id!=? LIMIT 1", (wd, slot, tA))
    if busy_t:
        r = kaf2.post(f"/api/staffabs/{A}/subs", json={**sub, "teacher_id": busy_t[0][0]})
        ok(r.status_code == 409 and "o'z darsi" in r.json()["detail"], "shu parada darsi bor o'qituvchi — 409")
    ok(kaf2.post(f"/api/staffabs/{A}/subs", json={**sub, "date": (mon + dt.timedelta(days=40)).isoformat()}).status_code == 400, "yo'qlik oralig'idan tashqari sana — 400")
    ok(kaf2.post(f"/api/staffabs/{A}/subs", json={**sub, "teacher_id": tA}).status_code == 400, "o'zini o'rinbosar qilish — 400")
    r = kaf2.post(f"/api/staffabs/{A}/subs", json=sub); ok(r.status_code == 200 and r.json()["assigned"] == [L["date"]], "o'rinbosar tayinlandi")
    x = next(l for l in kaf2.get(f"/api/staffabs/{A}").json()["lesson_list"] if l["sched_id"] == L["sched_id"] and l["date"] == L["date"])
    ok(x["sub"] and x["sub"]["teacher_id"] == sg[0]["teacher_id"] and x["sub"]["by"], "darsda o'rinbosar va kim tayinlagani")
    ch = akad.get("/api/staffabs/changes", params={"days": 60}).json()["items"]
    ok(any(c_["absence_id"] == A and c_["sub"] and c_["date"] == L["date"] for c_ in ch), "akademik: jadval o'zgarishlarida ko'rinadi")
    nd = kaf2.get("/api/staffabs/needs", params={"days": 60}).json()
    g = [g_ for g_ in nd["groups"] if g_["department_id"] == 2]
    ok(g and any(i["absence_id"] == A and i["can_assign"] for i in g[0]["items"]) and g[0]["covered"] >= 1, "kafedra: «O'rinbosar kerak» ro'yxati, tayinlangan hisobi")
    ok(all(g_["department_id"] == 2 for g_ in nd["groups"]), "kafedra mudiri: faqat o'z kafedrasi guruhi")
    ok(not [g_ for g_ in kaf4.get("/api/staffabs/needs", params={"days": 60}).json()["groups"] if any(i["absence_id"] == A for i in g_["items"])], "boshqa kafedrada ko'rinmaydi")
    # o'zi ham yo'q bo'lgan o'qituvchi tavsiya qilinmaydi va tayinlanmaydi
    rX = kadr.post("/api/staffabs", json={"staff_id": sX["id"], "kind": "kasallik", "start": W0, "end": W1, "note": f"Kasallik {TAG}"})
    ok(rX.status_code == 200, "ikkinchi o'qituvchi (kasallik) — kesishgan yo'qlik"); MADE.append(rX.json()["id"])
    sg2 = kaf2.get(f"/api/staffabs/{A}/suggest", params={"sched_id": L["sched_id"], "date": L["date"]}).json()["items"]
    ok(all(x["teacher_id"] != tX for x in sg2), "yo'qlikdagi o'qituvchi tavsiyada yo'q")
    if not q("SELECT 1 FROM schedule WHERE teacher_id=? AND weekday=? AND slot=?", (tX, wd, slot)):
        r = kaf2.post(f"/api/staffabs/{A}/subs", json={**sub, "teacher_id": tX})
        ok(r.status_code == 409 and "o'zi ham yo'q" in r.json()["detail"], "yo'qlikdagi o'qituvchini tayinlash — 409")
    # barcha sanalarga
    L2 = next((l for l in d["lesson_list"] if l["sched_id"] != L["sched_id"]), None)
    if L2:
        sg3 = kaf2.get(f"/api/staffabs/{A}/suggest", params={"sched_id": L2["sched_id"], "date": L2["date"]}).json()["items"]
        r = kaf2.post(f"/api/staffabs/{A}/subs", json={"sched_id": L2["sched_id"], "date": L2["date"], "teacher_id": sg3[0]["teacher_id"], "all_dates": True})
        ok(r.status_code == 200 and L2["date"] in r.json()["assigned"], f"«barcha sanalar»: {len(r.json()['assigned'])} ta tayinlandi, {len(r.json()['skipped'])} ta o'tkazildi")
    sid = x["sub"]["id"]
    ok(kaf4.delete(f"/api/staffabs/{A}/subs/{sid}").status_code == 403, "boshqa kafedra: olib tashlash 403")
    ok(kaf2.delete(f"/api/staffabs/{A}/subs/{sid}").status_code == 200, "o'rinbosar olib tashlandi")
    ok(kaf2.post(f"/api/staffabs/{A}/subs", json=sub).status_code == 200, "qayta tayinlandi")

    # ============================================================== 5. Tahrir, asos hujjat, buyruq
    print("— 5. Tahrir, asos hujjat, buyruq —")
    ok(kaf2.put(f"/api/staffabs/{A}", json={**body, "end": W0}).status_code == 403, "kafedra mudiri: tahrir 403")
    subs_before = q("SELECT COUNT(*) FROM staff_subs WHERE absence_id=?", (A,))[0][0]
    later = q("SELECT COUNT(*) FROM staff_subs WHERE absence_id=? AND date>?", (A, W0))[0][0]
    r = kadr.put(f"/api/staffabs/{A}", json={**body, "end": W0, "note": f"Konferensiya (1 kun) {TAG}"})
    ok(r.status_code == 200 and r.json()["dropped_subs"] == later, f"oraliq qisqardi: {later} ta o'rinbosarlik o'chirildi")
    ok(q("SELECT COUNT(*) FROM staff_subs WHERE absence_id=?", (A,))[0][0] == subs_before - later, "bazada qolgan o'rinbosarliklar to'g'ri")
    pdf = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"
    up = lambda c, name, data: c.post(f"/api/staffabs/{A}/files", params={"name": name}, content=data, headers={"Content-Type": "application/octet-stream"})
    ok(up(kaf2, "buyruq.pdf", pdf).status_code == 403, "kafedra mudiri: yuklash 403")
    ok(up(kadr, "virus.pdf", b"MZ\x90\x00" + b"\x00" * 64).status_code == 415, "nomi o'zgartirilgan exe — 415")
    ok(up(kadr, "skript.js", b"alert(1)").status_code == 415, "ruxsat etilmagan tur — 415")
    r = up(kadr, "xizmat_topshirigi.pdf", pdf); ok(r.status_code == 200, "asos hujjat yuklandi")
    fid = r.json()["id"]
    ok(kadr.get(f"/api/staffabs/files/{fid}").content == pdf, "kadrlar: yuklab olish (mazmuni bir xil)")
    for c, n in ((kaf2, "kafedra"), (rektor, "rektor"), (akad, "akademik")):
        ok(c.get(f"/api/staffabs/files/{fid}").status_code == 403, f"{n}: asos hujjat 403")
    ok(kadr.get(f"/api/staffabs/{A}").json()["file_list"][0]["name"] == "xizmat_topshirigi.pdf" and kaf2.get(f"/api/staffabs/{A}").json()["file_list"] == [],
       "fayllar ro'yxati faqat kadrlarga")
    ok(kadr.post(f"/api/staffabs/{A}/order", json={}).status_code == 400, "safar uchun mehnat ta'tili buyrug'i — 400")
    st_m = next(x for x in kadr.get("/api/staffabs/staff", params={"q": "Marketing"}).json() if not x["teacher_id"]
                if not q("SELECT 1 FROM staff_absences WHERE staff_id=? AND status='faol' AND start<=? AND end>=?", (x["id"], W1, W0)))
    rM = kadr.post("/api/staffabs", json={"staff_id": st_m["id"], "kind": "mehnat", "start": W0, "end": W1, "note": f"Ta'til {TAG}"})
    M = rM.json()["id"]; MADE.append(M)
    ok(rM.json()["lessons"] == 0, "dars o'tmaydigan xodim: ta'sir 0")
    ok(kaf2.post(f"/api/staffabs/{M}/order", json={}).status_code == 403, "kafedra: buyruq 403")
    ok(kadr.post(f"/api/staffabs/{M}/order", json={"reg_no": "ShT-00/9999"}).status_code == 404, "mavjud bo'lmagan buyruq — 404")
    # mehnat ta'tili buyrug'i — «Buyruqlar» bo'limida (talabalar va xodimlar buyruqlarining yagona joyi), Hujjatlar markazida emas
    r = kadr.post(f"/api/staffabs/{M}/order", json={}); ok(r.status_code == 200 and r.json()["order_id"] and r.json()["link"] == {"view": "orders", "order": r.json()["order_id"]},
                                                           f"buyruq loyihasi «Buyruqlar»da yaratildi: {r.json()}")
    OID = r.json()["order_id"]; DOCS.append(OID)
    ok(q("SELECT kind, status FROM orders WHERE id=?", (OID,))[0] == ("xodim_tatil", "loyiha"), "orders: xodim_tatil, «loyiha»")
    ok(not q("SELECT 1 FROM documents WHERE kind='leave_order' AND created_at>=? AND status='loyiha'", (T0,)), "Hujjatlar markazida yangi buyruq loyihasi yaratilmadi")
    o = kadr.get(f"/api/staffabs/{M}").json()["order"]
    ok(o["raw_status"] == "loyiha" and o["link"]["order"] == OID, "yo'qlik kartasida buyruq holati va Buyruqlarga havola")
    od = kadr.get(f"/api/orders/{OID}").json()
    ok(od["staff"] and od["order"]["params"]["staff_id"] == st_m["id"] and od["order"]["params"]["date_from"] == W0, "Buyruqlar: xodim va sanalar to'g'ri")
    ok(kadr.post(f"/api/staffabs/{A}/order", json={"reg_no": f"#{OID}"}).status_code == 400, "boshqa xodim buyrug'ini bog'lash — 400")
    mw = kadr.get("/api/mywork").json()["items"]
    ok(not any(it["link"].get("absence") == M for it in mw), "«Mening vazifalarim»: buyrug'i bor ta'til «buyruqsiz» ro'yxatida yo'q")

    # ============================================================== 6. Tahlil
    print("— 6. Tahlil —")
    an = kadr.get("/api/staffabs/analytics").json()
    ok(len(an["months"]) == 7 and an["by_unit"] and "absent_now" in an["kpi"], "tahlil: 7 oy, kafedra/bo'lim kesimi, KPI")
    ok(any(o_["unit"].startswith("Biznes boshqaruvi") and o_["from"] == W0 for o_ in an["overlaps"]), "kesishgan yo'qliklar: test oynasidagi 2 o'qituvchi")
    ok(an["frequent_sick"], "tez-tez kasallik varaqasi (demo)")
    ka = kaf2.get("/api/staffabs/analytics").json()
    ok(all(u["department_id"] == 2 for u in ka["by_unit"]), "kafedra mudiri: tahlil faqat o'z kafedrasi")
    ok(teacher.get("/api/staffabs/analytics").status_code == 403, "o'qituvchi: tahlil 403")
    ok(rektor.get("/api/staffabs/analytics").status_code == 200 and pro.get("/api/staffabs/analytics").status_code == 200, "rektor, prorektor: tahlil")
    mine = teacher.get("/api/staffabs/changes").json()
    ok("mine" in mine and mine["items"] == [], "o'qituvchi: «O'rinbosarligim» (faqat o'zi)")

    # ============================================================== 7. Bekor qilish
    print("— 7. Bekor qilish —")
    ok(kaf2.post(f"/api/staffabs/{A}/cancel", json={}).status_code == 403, "kafedra: bekor qilish 403")
    r = kadr.post(f"/api/staffabs/{A}/cancel", json={"note": "safar qoldirildi"}); ok(r.status_code == 200 and r.json()["dropped_subs"] >= 1, "bekor qilindi, o'rinbosarliklar o'chdi")
    ok(kadr.post(f"/api/staffabs/{A}/cancel", json={}).status_code == 409, "takroriy bekor — 409")
    ok(kaf2.post(f"/api/staffabs/{A}/subs", json=sub).status_code == 409, "bekor qilingan yozuvga tayinlash — 409")
    ok(A not in {x["id"] for x in kadr.get("/api/staffabs", params={"period": "active"}).json()["items"]}, "faol ro'yxatda yo'q")
    ok(kadr.get(f"/api/staffabs/{A}").json()["status"] == "bekor", "holat: bekor")

    # ============================================================== 8. Demo va audit
    print("— 8. Demo va audit —")
    demo = kadr.get("/api/staffabs", params={"period": "all"}).json()["items"]
    ok(any(x["kind"] == "kasallik" and x["phase"] == "joriy" and x["teacher"] for x in demo), "demo: hozir kasallik varaqasidagi o'qituvchi")
    ok(any(x["kind"] == "mehnat" and x["order"] for x in demo), "demo: buyruq bog'langan mehnat ta'tili")
    ok(any(x["phase"] == "kelgusi" and x["kind"] == "safar" for x in demo), "demo: kelgusi xizmat safari")
    rows = q("SELECT action, allowed, user_id FROM audit_log WHERE id>? AND resource='staff_absence'", (AUDIT0,))
    seen = lambda a, u, al=1: any(x == a and uid == u and y == al for x, y, uid in rows)
    ok(seen("xodimlar ta'tili: ro'yxatga olindi", 12) and seen("xodimlar ta'tili: yaratish", 31, 0), "audit: yaratildi (12), kafedraga rad")
    ok(seen("xodimlar ta'tili: o'rinbosar tayinlandi", 31) and seen("xodimlar ta'tili: o'rinbosar tayinlash", 14, 0), "audit: tayinlandi (31), boshqa kafedraga rad")
    ok(seen("xodimlar ta'tili: asos hujjat yuklandi", 12) and seen("xodimlar ta'tili: asos hujjat rad etildi", 12, 0), "audit: hujjat yuklandi / rad etildi")
    ok(seen("xodimlar ta'tili: asos hujjat yuklab olindi", 2, 0), "audit: rektorning asos hujjat urinishi rad")
    ok(seen("xodimlar ta'tili: ko'rish", 14, 0) and seen("xodimlar ta'tili: ro'yxat", 18), "audit: ko'rish rad (14), ro'yxat (18)")
    ok(seen("xodimlar ta'tili: o'zgartirildi", 12) and seen("xodimlar ta'tili: bekor qilindi", 12) and seen("xodimlar ta'tili: buyruq bog'landi", 12), "audit: tahrir, bekor, buyruq")
    ok(seen("xodimlar ta'tili: tahlil", 15, 0), "audit: o'qituvchining tahlil urinishi rad")

if __name__ == "__main__":
    try:
        main()
    finally:
        cleanup()
    print(f"\nJami tekshiruvlar: {N[0]} · hammasi o'tdi")
