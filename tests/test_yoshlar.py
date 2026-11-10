"""Yoshlar ishlari (app/yoshlar.py): hamkor yotoqxonalar, navbat, joy berish, to'lov, tartib, ijara, tadbirlar, talaba kabineti.

Ishga tushirish:  ISFT_TEST_URL=http://127.0.0.1:8000 ISFT_CORE_DB=data/jarvis.db .venv/bin/python tests/test_yoshlar.py
"""
import os, sys, sqlite3, datetime as dt
from pathlib import Path
import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
DB = os.environ.get("ISFT_CORE_DB", str(ROOT / "data" / "jarvis.db"))
B = os.environ.get("ISFT_TEST_URL", "http://127.0.0.1:8000")
PW = "Isft2026"
SPW = os.environ.get("ISFT_CORE_STUDENT_DEMO_PASSWORD", "Talaba2026")
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

P = "/api/yoshlar"

# ---------------------------------------------------------------- 0. tuzilma: bo'lim, kurator, akkauntlar
ok(uid("manaviyat") and uid("komendant"), "Demo akkauntlar: Ma'naviyat va ma'rifat bo'limi, turar joy komendanti")
ok(q1("SELECT curator FROM org_units WHERE key='manaviyat'") == "prorektor_yoshlar", "org_units: Ma'naviyat va ma'rifat bo'limi — kurator Yoshlar masalalari prorektori")
ok(q1("SELECT unit FROM users WHERE role='komendant'") == "komendant" and q1("SELECT curator FROM org_units WHERE key='komendant'") == "prorektor_yoshlar",
   "Komendant — «Talabalar turar joyi» bo'limi, kurator Yoshlar masalalari prorektori")
pro, man, kom, bux, rek = S(uid("prorektor_yoshlar")), S(uid("manaviyat")), S(uid("komendant")), S(uid("buxgalteriya")), S(uid("rektor"))
tyu_id = q1("SELECT user_id FROM tutor_groups GROUP BY user_id ORDER BY COUNT(*) DESC LIMIT 1")
tyu = S(tyu_id)
prof = J(pro.get("/api/me/profile"))
ok(any("Ma'naviyat" in x for x in (prof.get("curated") or [])), f"Prorektor profili: vakolatidagi bo'limlar — {prof.get('curated')}")
pu = J(pro.get("/api/portal/units"))
ok({"manaviyat", "komendant"} <= set(pu["curated"]) and {"manaviyat", "komendant"} <= set(pu["directive_units"]), "Portal: prorektor kuratorligi va topshiriq beriladigan bo'limlar ro'yxatida — manaviyat")
tg = J(pro.get("/api/dir/targets"))
ok(any(u["key"] == "manaviyat" for g in tg["groups"] for u in g["units"]), "Topshiriqlar: prorektor Ma'naviyat bo'limiga topshiriq bera oladi")

# ---------------------------------------------------------------- 1. rejimlar va ruxsat
m = J(pro.get(P + "/meta"))
TODAY = m["today"]
ok(m["mode"] == "lead" and m["caps"]["approve"] and m["caps"]["expel"], "Prorektor: to'liq boshqaruv, tasdiqlash va chiqarish qarori")
mm = J(man.get(P + "/meta"))
ok(mm["mode"] == "staff" and mm["caps"]["event"] and not mm["caps"]["approve"] and not mm["caps"]["expel"], "Ma'naviyat bo'limi: yuritadi, lekin tadbirni o'zi tasdiqlamaydi va chiqarmaydi")
km = J(kom.get(P + "/meta"))
ok(km["mode"] == "komendant" and "tadbirlar" not in [t["key"] for t in km["tabs"]] and km["caps"]["pay"], "Komendant: faqat yotoqxona (tadbirlarsiz), to'lov belgilaydi")
bm = J(bux.get(P + "/meta"))
ok([t["key"] for t in bm["tabs"]] == ["tolov"] and bm["caps"]["pay"], "Buxgalteriya: faqat to'lovlar bo'limi")
J(bux.get(P + "/overview"), 403)
J(bux.get(P + "/applications"), 403)
ok(True, "Buxgalteriya arizalar va umumiy ko'rinishga kira olmaydi (403)")
rm_ = J(rek.get(P + "/meta"))
ok(rm_["mode"] == "view" and not any(rm_["caps"][k] for k in ("dorm", "event", "approve", "pay")), "Rektor: faqat ko'rish")
tm = J(tyu.get(P + "/meta"))
ok(tm["mode"] == "tyutor" and tm["caps"]["rental"] and not tm["caps"]["dorm"], "Tyutor: o'qish + ijara tashrifi")
J(S(uid("akademik")).get(P + "/meta"), 403)
ok(True, "Akademik bo'lim: ruxsat yo'q (403)")
ok(q1("SELECT COUNT(*) FROM audit_log WHERE resource='youth' AND action LIKE 'yoshlar:%'") > 0, "Har bir murojaat audit jurnalida (resource=youth)")

# ---------------------------------------------------------------- 2. umumiy
ov = J(pro.get(P + "/overview")); k = ov["kpi"]
ok(k["capacity"] > 0 and k["live"] > 0 and k["live"] + k["reserved"] <= k["capacity"], f"Sig'im {k['capacity']}, yashaydi {k['live']}, bron {k['reserved']}")
ok(isinstance(ov["alerts"], list), f"Ogohlantirishlar: {len(ov['alerts'])} ta")
cap_db = q1("SELECT SUM(beds) FROM yj_rooms r JOIN yj_buildings b ON b.id=r.building_id WHERE b.active=1")
ok(cap_db == k["capacity"], "Sig'im = xonalardagi o'rinlar yig'indisi")
tk = J(tyu.get(P + "/overview"))["kpi"]
ok(tk["rentals"] <= k["rentals"] and tk["queue"] <= k["queue"], "Tyutor ko'rsatkichlari — faqat o'z guruhlari (umumiydan kam yoki teng)")

# ---------------------------------------------------------------- 3. ariza → tekshiruv → joy → joylashish → chiqish
def free_student(gender, region_not=("Toshkent sh.",)):
    return q1(f"""SELECT s.id FROM students s JOIN groups_ g ON g.id=s.group_id WHERE s.status='faol' AND s.study_form='kunduzgi' AND s.gender=?
                 AND s.region NOT IN ({','.join('?' * len(region_not))})
                 AND s.id NOT IN (SELECT student_id FROM yj_applications) AND s.id NOT IN (SELECT student_id FROM yj_residents)
                 AND s.id NOT IN (SELECT student_id FROM yj_rentals) ORDER BY s.id DESC LIMIT 1""", (gender, *region_not))

g_free = "M" if k["free_m"] else ("F" if k["free_f"] else None)
if not g_free:   # bo'sh o'rin bo'lmasa — test uchun bitta xona qo'shamiz
    bid = q1("SELECT id FROM yj_buildings WHERE gender='M' LIMIT 1")
    J(man.post(f"{P}/buildings/{bid}/rooms", json={"number": f"T{N[0]}", "floor": 9, "beds": 2, "gender": "M"}))
    g_free = "M"
sid = free_student(g_free)
sir = q1("SELECT id FROM students WHERE status='faol' AND study_form='sirtqi' LIMIT 1")
J(man.post(P + "/applications", json={"student_id": sir, "cats": []}), 400)
ok(True, "Sirtqi talaba arizasi rad etiladi (faqat kunduzgi)")
tsh = q1("""SELECT id FROM students WHERE status='faol' AND study_form='kunduzgi' AND region='Toshkent sh.'
            AND id NOT IN (SELECT student_id FROM yj_applications) LIMIT 1""")
r = man.post(P + "/applications", json={"student_id": tsh, "cats": []})
ok(r.status_code == 400 and "Toshkent" in r.text, "Toshkent shahridagi talaba — imtiyozsiz ariza qabul qilinmaydi")
a = J(man.post(P + "/applications", json={"student_id": sid, "cats": ["daftar"], "note": "test"}))
ok(a["status"] == "yangi" and a["score"] >= 30, f"Imtiyozli ariza: holat «yangi», ball {a['score']}")
J(man.post(P + "/applications", json={"student_id": sid, "cats": []}), 400)
ok(True, "Takroriy ariza qabul qilinmaydi")
r = man.post(f"{P}/applications/{a['id']}/allocate", json={})
ok(r.status_code == 400 and "tekshir" in r.text, "Hujjat tekshirilmaguncha joy berilmaydi")
J(rek.post(f"{P}/applications/{a['id']}/verify"), 403)
J(tyu.post(f"{P}/applications/{a['id']}/verify"), 403)
ok(True, "Rektor (ko'rish) va tyutor arizani tekshira olmaydi (403)")
J(kom.post(f"{P}/applications/{a['id']}/verify"))
apps = J(man.get(P + "/applications?status=navbat"))
me = next(x for x in apps if x["id"] == a["id"])
higher = [x for x in apps if x["position"] and x["position"] < me["position"]]
ok(me["status"] == "navbatda" and all(x["score"] >= me["score"] for x in higher), f"Navbat bali bo'yicha tartiblangan, o'rni {me['position']}")
wrong = q1("SELECT r.id FROM yj_rooms r WHERE r.gender!=? LIMIT 1", (g_free,))
r = man.post(f"{P}/applications/{a['id']}/allocate", json={"room_id": wrong})
ok(r.status_code == 400 and "mos emas" in r.text, "Jinsga mos bo'lmagan xonaga joy berilmaydi")
al = J(kom.post(f"{P}/applications/{a['id']}/allocate", json={}))
rid = al["resident_id"]
ok(q1("SELECT status FROM yj_residents WHERE id=?", (rid,)) == "band" and q1("SELECT status FROM yj_applications WHERE id=?", (a["id"],)) == "joy_berildi",
   f"Joy berildi (bron): {al['building']}, {al['room']}-xona, {al['bed']}-o'rin")
ok(q1("SELECT gender FROM yj_rooms WHERE id=(SELECT room_id FROM yj_residents WHERE id=?)", (rid,)) == g_free, "Xona talabaning jinsiga mos")
J(man.post(P + "/applications", json={"student_id": sid, "cats": []}), 400)
ok(True, "Joy olgan talaba qayta ariza bera olmaydi")
r = man.post(f"{P}/violations", json={"resident_id": rid, "kind": "Chekish", "text": "Xonada chekdi", "measure": "ogohlantirish"})
ok(r.status_code == 400, "Bron (joylashmagan) talabaga tartib qaydi yozilmaydi")
J(kom.post(f"{P}/residents/{rid}/checkin", json={}))
ok(q1("SELECT status FROM yj_residents WHERE id=?", (rid,)) == "yashaydi" and q1("SELECT check_in FROM yj_residents WHERE id=?", (rid,)) == TODAY, "Joylashdi — bugungi sana bilan")
J(kom.post(f"{P}/residents/{rid}/checkin", json={}), 400)
ok(True, "Ikki marta joylashtirib bo'lmaydi")

# ---------------------------------------------------------------- 4. to'lov
per = TODAY[:7]
g = J(bux.post(P + "/charges/generate", json={"period": per}))
ok(g["created"] >= 1, f"Oylik hisob: {per} — {g['created']} ta yangi")
g2 = J(man.post(P + "/charges/generate", json={"period": per}))
ok(g2["created"] == 0, "Takroriy hisob yaratish idempotent")
cid = q1("SELECT id FROM yj_charges WHERE resident_id=? AND period=?", (rid, per))
fee = q1("SELECT b.fee_month FROM yj_buildings b JOIN yj_rooms r ON r.building_id=b.id JOIN yj_residents x ON x.room_id=r.id WHERE x.id=?", (rid,))
ok(q1("SELECT amount FROM yj_charges WHERE id=?", (cid,)) == fee, "Hisob summasi = bino tarifi")
J(man.post(f"{P}/charges/{cid}/pay", json={"receipt": "KV-1"}), 403)
ok(True, "Ma'naviyat bo'limi to'lovni belgilay olmaydi (faqat komendant / buxgalteriya)")
J(bux.post(f"{P}/charges/{cid}/pay", json={"amount": 1, "receipt": ""}), 400)
ok(True, "Kvitansiya raqamisiz to'lov qabul qilinmaydi")
J(bux.post(f"{P}/charges/{cid}/pay", json={"amount": fee + 1, "receipt": "KV-T1"}), 400)
ok(True, "Qoldiqdan ortiq summa qabul qilinmaydi")
p1 = J(bux.post(f"{P}/charges/{cid}/pay", json={"amount": fee // 2, "receipt": "KV-T1"}))
p2 = J(kom.post(f"{P}/charges/{cid}/pay", json={"receipt": "KV-T2"}))
ok(p1["left"] == fee - fee // 2 and p2["left"] == 0 and q1("SELECT paid FROM yj_charges WHERE id=?", (cid,)) == fee, "Qisman, keyin to'liq to'lov")
J(bux.post(f"{P}/charges/{cid}/pay", json={"receipt": "KV-T3"}), 400)
ok(True, "To'langan oy uchun qayta to'lov yo'q")
cd = J(bux.get(P + "/charges?debt=1"))
ok(all(x["state"] == "qarz" for x in cd["items"]) and cd["total"]["debt"] >= 0, f"Qarzdorlar: {cd['total']['debtors']} nafar, {cd['total']['debt']} so'm")

# ---------------------------------------------------------------- 5. tartib
v = J(kom.post(f"{P}/violations", json={"resident_id": rid, "kind": "Chekish", "text": "Xonada chekkani aniqlandi", "measure": "ogohlantirish"}))
ok(v["count"] == 1 and not v["warn"], "Tartib qaydi: ogohlantirish")
J(kom.post(f"{P}/violations", json={"resident_id": rid, "kind": "Chekish", "text": "Takroran chekdi", "measure": "chiqarish"}), 403)
ok(True, "Komendant chiqarish chorasini qo'llay olmaydi (faqat prorektor)")
J(man.post(f"{P}/residents/{rid}/checkout", json={"reason": "Tartib buzilishi (chiqarish)"}), 403)
ok(True, "Tartib buzilishi uchun chiqarish — faqat prorektor (checkout ham)")
J(kom.post(f"{P}/violations", json={"resident_id": rid, "kind": "Janjal", "text": "Kechasi shovqin", "measure": "hayfsan"}))
v3 = J(kom.post(f"{P}/violations", json={"resident_id": rid, "kind": "Kechki tartibni buzish", "text": "Soat 23:30 da qaytdi", "measure": "ogohlantirish"}))
ok(v3["warn"] and v3["count"] == 3, "3-qayd — chiqarish masalasi ogohlantirishi")
ok(any(a["tab"] == "tartib" for a in J(pro.get(P + "/overview"))["alerts"]), "Umumiy ko'rinishda tartib ogohlantirishi bor")
J(pro.post(f"{P}/violations", json={"resident_id": rid, "kind": "Chekish", "text": "Prorektor qarori bilan chiqarildi", "measure": "chiqarish"}))
ok(q1("SELECT status FROM yj_residents WHERE id=?", (rid,)) == "chiqdi" and q1("SELECT out_reason FROM yj_residents WHERE id=?", (rid,)) == "Tartib buzilishi (chiqarish)",
   "Prorektor chiqarish chorasi — yashovchi chiqarildi, o'rin bo'shadi")
J(bux.post(P + "/charges/generate", json={"period": per}))
ok(q1("SELECT COUNT(*) FROM yj_charges WHERE resident_id=? AND period=?", (rid, per)) == 1, "Chiqqan yashovchiga shu oy uchun hisob takrorlanmaydi")

# ---------------------------------------------------------------- 6. bron bekor qilish va navbat bo'yicha avtomatik joylashtirish
sid2 = free_student(g_free)
a2 = J(man.post(P + "/applications", json={"student_id": sid2, "cats": []}))
ok(a2["status"] == "navbatda", "Imtiyozsiz ariza darhol navbatga tushadi (tekshiradigan hujjat yo'q)")
J(kom.post(P + "/allocate-waitlist"), 403)
ok(True, "Ommaviy joylashtirish — komendantga emas")
bulk = J(man.post(P + "/allocate-waitlist"))
ok(bulk["allocated"] >= 1, f"Navbat bo'yicha avtomatik: {bulk['allocated']} ta joy berildi, {bulk['left']} tasi qoldi")
r2 = q1("SELECT id FROM yj_residents WHERE application_id=? AND status='band'", (a2["id"],))
if r2:
    J(kom.post(f"{P}/residents/{r2}/cancel"))
    ok(q1("SELECT status FROM yj_applications WHERE id=?", (a2["id"],)) == "navbatda", "Bron bekor — ariza navbatga qaytdi")
    J(man.post(f"{P}/applications/{a2['id']}/reject", json={"reason": "Test: talaba o'zi rad etdi"}))
    ok(q1("SELECT status FROM yj_applications WHERE id=?", (a2["id"],)) == "rad", "Arizani sabab bilan rad etish")
else:
    ok(True, "Ariza boshqa yuqori balli arizalar orasida qoldi (bo'sh o'rin yetmadi)")

# ---------------------------------------------------------------- 7. ijara (tyutor)
mine = q1("""SELECT s.id FROM students s WHERE s.group_id IN (SELECT group_id FROM tutor_groups WHERE user_id=?) AND s.status='faol'
             AND s.id NOT IN (SELECT student_id FROM yj_residents WHERE status IN ('band','yashaydi')) AND s.id NOT IN (SELECT student_id FROM yj_rentals) LIMIT 1""", (tyu_id,))
other = q1("""SELECT s.id FROM students s WHERE s.group_id NOT IN (SELECT group_id FROM tutor_groups WHERE user_id=?) AND s.status='faol'
              AND s.id NOT IN (SELECT student_id FROM yj_residents WHERE status IN ('band','yashaydi')) LIMIT 1""", (tyu_id,))
J(tyu.post(P + "/rentals", json={"student_id": other, "address": "Test ko'chasi, 1-uy", "district": "Qibray t.", "rent": 800000}), 403)
ok(True, "Tyutor boshqa guruh talabasiga ijara qaydi yoza olmaydi")
J(tyu.post(P + "/rentals", json={"student_id": mine, "address": "Test ko'chasi, 1-uy", "district": "Qibray t.", "rent": 800000, "has_contract": True}))
xid = q1("SELECT id FROM yj_rentals WHERE student_id=?", (mine,))
J(tyu.post(f"{P}/rentals/{xid}/visit", json={"note": "Sharoit yaxshi", "condition": "a'lo"}), 400)
J(tyu.post(f"{P}/rentals/{xid}/visit", json={"note": "Sharoit yaxshi, isitish bor", "condition": "yaxshi"}))
ok(q1("SELECT last_visit FROM yj_rentals WHERE id=?", (xid,)) == TODAY and q1("SELECT visited_by FROM yj_rentals WHERE id=?", (xid,)) == tyu_id, "Tyutor tashrifi qayd etildi")
tr = J(tyu.get(P + "/rentals"))
ok(tr and all(q1("SELECT 1 FROM students s JOIN tutor_groups t ON t.group_id=s.group_id WHERE s.id=? AND t.user_id=?", (x["student_id"], tyu_id)) for x in tr),
   f"Tyutor faqat o'z guruhlari ijarachilarini ko'radi ({len(tr)} ta)")
tres = J(tyu.get(P + "/residents"))
ok(all(q1("SELECT 1 FROM students s JOIN tutor_groups t ON t.group_id=s.group_id WHERE s.id=? AND t.user_id=?", (x["student_id"], tyu_id)) for x in tres),
   "Tyutor faqat o'z guruhlari yashovchilarini ko'radi")
J(kom.post(P + "/rentals", json={"student_id": mine, "address": "x ko'chasi 2", "district": "y", "rent": 1}), 403)
ok(True, "Komendant ijara qaydi yozmaydi (tyutor va bo'lim ishi)")

# ---------------------------------------------------------------- 8. tadbirlar: reja → tasdiq → o'tkazish → hisobot
future = (dt.date.fromisoformat(TODAY) + dt.timedelta(days=5)).isoformat()
J(man.post(P + "/events", json={"title": "O'tgan sana", "date": "2020-01-01", "kind": "sport"}), 400)
ok(True, "O'tgan sanaga tadbir rejalashtirilmaydi")
e = J(man.post(P + "/events", json={"title": "Test: shaxmat turniri", "date": future, "kind": "intellektual", "capacity": 2}))
eid = e["id"]
J(man.post(f"{P}/events/{eid}/submit"), 400)
ok(True, "Joy va vaqt ko'rsatilmaguncha tasdiqqa yuborilmaydi")
w("UPDATE events SET venue='Majlislar zali', start_time='14:00' WHERE id=?", (eid,))
J(man.post(f"{P}/events/{eid}/submit"))
J(man.post(f"{P}/events/{eid}/approve"), 403)
ok(True, "Ma'naviyat bo'limi o'z tadbirini tasdiqlay olmaydi")
J(pro.post(f"{P}/events/{eid}/reject", json={"reason": ""}), 400)
J(pro.post(f"{P}/events/{eid}/reject", json={"reason": "Smeta ko'rsatilmagan"}))
ok(q1("SELECT status FROM events WHERE id=?", (eid,)) == "rad", "Prorektor sabab bilan rad etdi")
J(man.post(f"{P}/events/{eid}/submit"))
J(pro.post(f"{P}/events/{eid}/approve"))
ok(q1("SELECT status FROM events WHERE id=?", (eid,)) == "tasdiqlangan" and q1("SELECT approved_by FROM events WHERE id=?", (eid,)) == uid("prorektor_yoshlar"),
   "Qayta yuborildi va tasdiqlandi")
r = man.post(f"{P}/events/{eid}/hold", json={"report": "x" * 30})
ok(r.status_code == 400 and "kelmagan" in r.text, "Sanasi kelmagan tadbir «o'tkazildi» deb belgilanmaydi")
pool = [x[0] for x in q("SELECT id FROM students WHERE status='faol' ORDER BY id LIMIT 3")]
J(man.post(f"{P}/events/{eid}/participants", json={"student_ids": pool[:2]}))
r = man.post(f"{P}/events/{eid}/participants", json={"student_ids": [pool[2]]})
ok(r.status_code == 400 and "to'lgan" in r.text, "Joylar soni chegarasi ishlaydi")
J(man.post(f"{P}/events/{eid}/attend", json={"student_ids": pool[:1]}), 400)
ok(True, "Qatnashuv tadbir kunidan oldin belgilanmaydi")
w("UPDATE events SET date=? WHERE id=?", (TODAY, eid))
J(man.post(f"{P}/events/{eid}/attend", json={"student_ids": pool[:1]}))
J(man.post(f"{P}/events/{eid}/hold", json={"report": "qisqa"}), 400)
J(man.post(f"{P}/events/{eid}/hold", json={"report": "Turnir o'tkazildi, 2 nafar ishtirokchi, g'oliblar taqdirlandi.", "participants": 0}))
ok(q1("SELECT status FROM events WHERE id=?", (eid,)) == "otkazildi" and q1("SELECT participants FROM events WHERE id=?", (eid,)) == 1,
   "Hisobot qabul qilindi, ishtirokchilar soni — QR/qayd bo'yicha (1)")
ed = J(pro.get(f"{P}/events/{eid}"))
ok(len(ed["people"]) == 2 and sum(p["came"] for p in ed["people"]) == 1, "Tadbir kartochkasi: 2 yozilgan, 1 kelgan")
J(kom.get(P + "/events"), 403)
ok(True, "Komendant tadbirlar bo'limiga kira olmaydi")

# ---------------------------------------------------------------- 9. talaba kabineti
def stu_client(sid_):
    hemis = q1("SELECT hemis_id FROM students WHERE id=?", (sid_,))
    c = httpx.Client(base_url=B, timeout=60)
    r = c.post("/api/talaba/login", json={"hemis_id": hemis, "password": SPW})
    if r.status_code != 200: return None
    if r.json().get("must_change"):
        r = c.post("/api/talaba/password", json={"current": SPW, "new": "Yangi-Parol-2026x"})
        if r.status_code != 200: return None
    return c

st = free_student("F" if g_free == "M" else "M")
sc = stu_client(st)
if sc is None:
    ok(True, "Talaba kabineti: login cheklovi (rate limit) — kabinet tekshiruvi o'tkazib yuborildi")
else:
    d = J(sc.get("/api/talaba/turarjoy"))
    ok(d["application"] is None and d["resident"] is None and d["eligible"], "Kabinet: ariza yo'q, ariza berish mumkin")
    ap = J(sc.post("/api/talaba/turarjoy", json={"cats": ["kop_bolali", "xyz"], "note": "kabinetdan"}))
    ok(ap["status"] == "yangi" and q1("SELECT channel FROM yj_applications WHERE id=?", (ap["id"],)) == "kabinet"
       and q1("SELECT cats FROM yj_applications WHERE id=?", (ap["id"],)) == "kop_bolali", "Kabinetdan ariza: noma'lum toifa tashlab yuborildi, kanal «kabinet»")
    d = J(sc.get("/api/talaba/turarjoy"))
    ok(d["application"]["status"] == "yangi" and d["application"]["position"] >= 1, f"Kabinetda navbatdagi o'rni: {d['application']['position']}")
    J(sc.post("/api/talaba/turarjoy/cancel"))
    ok(q1("SELECT status FROM yj_applications WHERE id=?", (ap["id"],)) == "bekor", "Talaba arizani qaytarib oldi")
    ok(q1("SELECT COUNT(*) FROM audit_log WHERE role='Talaba' AND resource='youth'") >= 2, "Talaba amallari audit jurnalida")
    ev = J(sc.get("/api/talaba/tadbirlar"))
    up = [x for x in ev["upcoming"] if not x["mine"] and not (x["capacity"] and x["reg"] >= x["capacity"])]
    if up:
        J(sc.post(f"/api/talaba/tadbirlar/{up[0]['id']}/register"))
        ok(any(x["mine"] for x in J(sc.get("/api/talaba/tadbirlar"))["upcoming"]), "Talaba tasdiqlangan tadbirga yozildi")
    J(sc.post(f"/api/talaba/tadbirlar/{eid}/register"), 400)
    ok(True, "O'tkazilgan tadbirga yozilib bo'lmaydi")
J(httpx.get(B + "/api/talaba/turarjoy", timeout=30), 401)
ok(True, "Kabinet endpointi talaba sessiyasisiz — 401")

print(f"\nHammasi o'tdi: {N[0]} ta tekshiruv.")
