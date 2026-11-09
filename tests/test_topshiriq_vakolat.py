"""Ierarxik topshiriqlar (app/directives.py): vakolat matritsasi, taqsimlash zanjiri, qabul/qaytarish, ko'rinish, «Mening vazifalarim»,
bildirishnomalar va audit.

Ishga tushirish (server http://127.0.0.1:8000 da ishlab turishi kerak):  .venv/bin/python tests/test_topshiriq_vakolat.py
Qayta ishga tushirsa bo'ladi: test yaratgan topshiriqlar ("[TEST]" bilan boshlanadi) boshida va oxirida bergan kishi tomonidan
bekor qilinadi (DELETE /api/dir/{id}). Bazaga to'g'ridan-to'g'ri faqat o'qish rejimida murojaat qilinadi.
Institutda dekan lavozimi yo'q — fakultet guruhi (fakultet tyutorlari) hech kimning maqsadlari ro'yxatida bo'lmasligi tekshiriladi.
"""
import datetime as dt, sqlite3, sys
from pathlib import Path
import httpx

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "data" / "jarvis.db"
B = "http://127.0.0.1:8000"
N = [0]

def ok(cond, msg):
    N[0] += 1
    print(("✓ " if cond else "✗ XATO: ") + msg)
    if not cond: sys.exit(1)

def S(uid):
    c = httpx.Client(base_url=B, timeout=120)
    r = c.post("/api/login", json={"user_id": uid, "password": "Isft2026"})
    assert r.status_code == 200, f"login {uid}: {r.status_code} {r.text}"
    return c

def q(sql, args=()):
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    try: return con.execute(sql, args).fetchall()
    finally: con.close()
def one(sql, args=()):
    r = q(sql, args); return r[0] if r else None

def due(days, h=18):
    return (dt.datetime.combine(dt.date.today() + dt.timedelta(days=days), dt.time(h, 0))).isoformat(timespec="minutes")

def denied_audits(action):
    return one("SELECT COUNT(*) FROM audit_log WHERE action=? AND allowed=0", (action,))[0]

NOROV = one("SELECT id FROM users WHERE role='registrator_xodim' ORDER BY id")
ok(NOROV is not None, f"demo akkaunt: Registrator ofisi xodimi (registrator_xodim) #{NOROV and NOROV[0]}")
NOROV = NOROV[0]
ok(one("SELECT unit FROM users WHERE id=?", (NOROV,))[0] == "talabalar" and one("SELECT head_user FROM org_units WHERE key='talabalar'")[0] == 17,
   "Norov A. — Registrator ofisi a'zosi (users.unit='talabalar'), rahbar emas (head_user = 17, Baratov)")
KAF = {k: one("SELECT head_user FROM org_units WHERE key=?", (k,))[0] for k in ("kaf3", "kaf6", "kaf1")}

# 2 rektor, 20 kotib, 3 o'quv prorektori, 5 moliya prorektori, 17 Registrator (Baratov), 18 Akademik bo'lim, 11 buxgalteriya,
# 21 IT boshlig'i, 22 IT muhandisi, 23 Call-markaz (Registrator ofisi a'zosi, TASKS ruxsatisiz), 14 kafedra (kaf4), kaf3/kaf6 mudirlari
U = {k: S(k) for k in (2, 20, 3, 5, 17, 18, 11, 21, 22, 23, 14, NOROV, KAF["kaf3"], KAF["kaf6"])}
rektor, kotib, pro, moliya, reg, akad, bux, ithead, itstaff, cc, kaf4, norov = (U[k] for k in (2, 20, 3, 5, 17, 18, 11, 21, 22, 23, 14, NOROV))
k3, k6 = U[KAF["kaf3"]], U[KAF["kaf6"]]
SESS = {2: rektor, 20: kotib, 3: pro, 5: moliya, 17: reg, 18: akad}

def cleanup():
    n = 0
    for tid, iss in q("SELECT id, issuer_user FROM tasks WHERE origin='topshiriq' AND text LIKE '[TEST]%' AND (parent_id IS NULL OR parent_id NOT IN (SELECT id FROM tasks WHERE text LIKE '[TEST]%'))"):
        c = SESS.get(iss) or S(iss)
        if c.delete(f"/api/dir/{tid}").status_code == 200: n += 1
    return n
print("tozalash (oldingi ishga tushirishdan):", cleanup())

def create(c, **kw):
    body = {"title": "[TEST] topshiriq", "body": "Test matni", "due_at": due(4), "priority": "muhim", "expect": "Excel ro'yxat"}
    body.update(kw)
    return c.post("/api/dir", json=body)

try:
    # =============================================================================================
    print("\n— 1. Vakolat matritsasi")
    T = {k: U[k].get("/api/dir/targets").json() for k in (2, 20, 3, 5, 17, 18, 14, NOROV, 23, 11, KAF["kaf3"])}
    tu = lambda k: {u["key"] for g in T[k]["groups"] for u in g["units"]}
    tp = lambda k: {p["id"] for p in T[k]["people"]}
    ok("registrator" in tu(3) and "buxgalteriya" not in tu(3) and {"kaf1", "kaf3", "sirtqi", "akademik"} <= tu(3),
       "o'quv prorektori: vakolatidagi bo'limlar (Registrator, Akademik, Sirtqi, kafedralar), Buxgalteriya yo'q")
    ok({"buxgalteriya", "xojalik", "marketing", "xarid"} == tu(5), "moliya prorektori: faqat Buxgalteriya, Xo'jalik, Marketing, Xarid")
    ok(tp(17) == {NOROV, 23} and not tu(17), "Registrator rahbari (Baratov): faqat o'z xodimlari — Norov A. va Call-markaz; quyi bo'lim yo'q")
    ok(tu(18) == {f"kaf{i}" for i in range(1, 9)} and not tp(18), "Akademik bo'lim: barcha kafedralar (SUBORDINATE), boshqa bo'lim yo'q")
    ok("kengash" not in tu(2) and "rektorat" not in tu(2) and {"prorektor_oquv", "registrator", "kaf1", "it"} <= tu(2) and 20 in tp(2),
       "rektor: istalgan bo'lim (Rektorat va Kuzatuv kengashidan tashqari) + o'z xodimi (kotib)")
    ok(T[20]["on_behalf"] == "rektor" and tu(20) == tu(2), "kotib: rektor nomidan — rektor bilan bir xil bo'limlar")
    ok(all(not any(g["group"] == "fakultet" for g in T[k]["groups"]) for k in T), "fakultet tyutorlari guruhi hech kimning maqsadlarida yo'q (dekan lavozimi yo'q)")
    ok(not T[NOROV]["can"] and not T[23]["can"] and not T[11]["can"] and not T[KAF["kaf3"]]["can"],
       "oddiy xodim, Call-markaz, bo'lim akkaunti (xodimsiz) va kafedra mudiri (xodimsiz) — topshiriq bera olmaydi")
    ok(tp(14) == {15}, "kafedra mudiri (kaf4): o'z o'qituvchisiga")
    ok(norov.get("/api/dir/list").json()["can_issue"] is False and reg.get("/api/dir/list").json()["can_issue"] is True, "/api/dir/list.can_issue — vakolatga mos")

    a0 = denied_audits("topshiriq berish")
    r = create(pro, unit="buxgalteriya")
    ok(r.status_code == 403 and "vakolatingizda emas" in r.json()["message"], f"o'quv prorektori → Buxgalteriya: 403 («{r.json()['message'][:70]}…»)")
    r = create(reg, user_id=22)
    ok(r.status_code == 403 and "bo'limingizda emas" in r.json()["message"], "Baratov → IT bo'limi xodimi: 403 (boshqa bo'lim xodimi)")
    r = create(U[KAF["kaf3"]], unit="akademik")
    ok(r.status_code == 403 and "yuqori" in r.json()["message"], "kafedra mudiri → Akademik bo'lim (yuqoriga): 403")
    r = create(U[KAF["kaf3"]], unit="prorektor_oquv")
    ok(r.status_code == 403 and "yuqori" in r.json()["message"], "kafedra mudiri → o'quv prorektori (yuqoriga): 403")
    r = create(reg, user_id=3)
    ok(r.status_code == 403 and "yuqori" in r.json()["message"], "Baratov → prorektor (shaxsan, yuqoriga): 403")
    r = create(akad, unit="registrator")
    ok(r.status_code == 403, "Akademik bo'lim → Registrator ofisi (yonma-yon): 403")
    r = create(norov, unit="kaf1")
    ok(r.status_code == 403, "Norov (oddiy xodim) → kafedra: 403")
    r = create(akad, unit="fak2")
    ok(r.status_code == 403, "Akademik bo'lim → fakultet tyutorlari: 403 (fakultet guruhi maqsad emas)")
    ok(denied_audits("topshiriq berish") - a0 == 8, "har bir rad etilgan urinish audit jurnalida (allowed=0) — 8 ta")
    last = one("SELECT user_id, resource, detail FROM audit_log WHERE action='topshiriq berish' AND allowed=0 ORDER BY id DESC")
    ok(last[0] == 18 and last[1] == "tasks" and "rad etildi" in last[2], f"audit yozuvi: kim, resurs, maqsad («{last[2]}»)")
    ok(create(pro, unit="registrator", due_at=due(-1)).status_code == 400, "o'tib ketgan muddat — 400")
    ok(create(pro, unit="registrator", priority="zo'r").status_code == 400, "noto'g'ri ustuvorlik — 400")
    ok(create(pro).status_code == 400, "maqsad tanlanmagan — 400")

    r = create(moliya, unit="buxgalteriya", title="[TEST] Kontrakt tushumlari bo'yicha haftalik ma'lumot")
    ok(r.status_code == 200, "moliya prorektori → Buxgalteriya: ruxsat")
    MOL = r.json()["id"]

    # =============================================================================================
    print("\n— 2. Zanjir: prorektor → Registrator ofisi → Norov A. va Call-markaz")
    r = create(pro, unit="talabalar", title="[TEST] Yakuniy nazorat ro'yxati", due_at=due(4))
    ok(r.status_code == 200, "o'quv prorektori → Registrator ofisi: ruxsat (Portal kaliti 'talabalar' ham qabul qilinadi)")
    P = r.json()["id"]
    row = one("SELECT unit, origin, meeting_id, issuer_user, issuer_unit, parent_id, status, priority, expect FROM tasks WHERE id=?", (P,))
    ok(row == ("registrator", "topshiriq", None, 3, "prorektor_oquv", None, "yangi", "muhim", "Excel ro'yxat"),
       f"tasks qatori: unit=registrator, origin=topshiriq, majlissiz, bergan #3 (prorektor_oquv) — {row}")
    ok(one("SELECT allowed, user_id, detail FROM audit_log WHERE action='topshiriq berish' ORDER BY id DESC")[:2] == (1, 3)
       and one("SELECT detail FROM audit_log WHERE action='topshiriq berish' ORDER BY id DESC")[0].startswith(f"#{P} "), "berish audit jurnalida (allowed=1, #3)")
    ok(one("SELECT action FROM task_log WHERE task_id=? ORDER BY id", (P,))[0] == "topshiriq berildi", "tarix: «topshiriq berildi»")
    ok(norov.get(f"/api/dir/{P}").status_code == 403, "Norov asosiy topshiriqni ko'rmaydi (403) — unga biriktirilmagan")
    ok(norov.post(f"/api/dir/{P}/delegate", json={"items": [{"user_id": NOROV}]}).status_code == 403, "Norov taqsimlay olmaydi (faqat bo'lim rahbari)")
    ok(reg.post(f"/api/dir/{P}/delegate", json={"items": [{"user_id": NOROV, "due_at": due(6)}]}).status_code == 400,
       "quyi muddat asosiy muddatdan kech — 400")
    ok(reg.post(f"/api/dir/{P}/delegate", json={"items": [{"user_id": 22}]}).status_code == 403, "Baratov → IT xodimiga yo'naltirish: 403")
    ok(reg.post(f"/api/dir/{P}/delegate", json={"items": [{"unit": "akademik"}]}).status_code == 403, "Baratov → Akademik bo'lim (yonma-yon): 403")
    r = reg.post(f"/api/dir/{P}/delegate", json={"items": [{"user_id": NOROV, "due_at": due(2)}, {"user_id": 23, "due_at": due(3), "title": "[TEST] Qarzdorlarga qo'ng'iroq"}],
                                              "note": "HEMIS bilan solishtiring"})
    ok(r.status_code == 200 and len(r.json()["ids"]) == 2, "Baratov → Norov A. va Call-markaz: 2 ta quyi topshiriq")
    C1, C2 = r.json()["ids"]
    ok(reg.post(f"/api/dir/{P}/delegate", json={"items": [{"user_id": NOROV}]}).status_code == 409, "o'sha ijrochiga takror — 409")
    ok(one("SELECT parent_id, unit, assignee_user, issuer_user, due_at, body FROM tasks WHERE id=?", (C1,)) == (P, "registrator", NOROV, 17, due(2), "HEMIS bilan solishtiring"),
       "quyi topshiriq: parent_id, bo'lim, ijrochi, bergan (Baratov), o'z muddati, ko'rsatma")
    ok(one("SELECT text FROM tasks WHERE id=?", (C1,))[0] == "[TEST] Yakuniy nazorat ro'yxati", "nom berilmasa — asosiy topshiriq nomi")
    d = reg.get(f"/api/dir/{P}").json()
    ok(d["tree"]["status"] == "jarayonda" and d["tree"]["progress"] == {"done": 0, "total": 2}, "asosiy: jarayonda, progress 0/2")
    ok([c["id"] for c in d["tree"]["children"]] == [C1, C2], "Baratov daraxtda ikkala quyi topshiriqni ko'radi")
    ok([l["action"] for l in d["log"]].count("taqsimlandi") == 2, "tarix: kim kimga yo'naltirgani («taqsimlandi» ×2)")
    r = reg.post(f"/api/dir/{P}/status", json={"status": "bajarildi", "result": "x"})
    ok(r.status_code == 409 and "0/2" in r.text, "quyi topshiriqlar ochiq — asosiyni yakunlab bo'lmaydi (409)")

    print("\n— 3. Ko'rinish")
    d = norov.get(f"/api/dir/{C1}").json()
    ok(d["root"] == C1 and not d["tree"]["children"] and d["parent_hidden"], "Norov: faqat o'z topshirig'i (asosiy va qo'shni yashirin)")
    ok(norov.get(f"/api/dir/{C2}").status_code == 403, "Norov Call-markaz topshirig'ini ko'rmaydi")
    nl = norov.get("/api/dir/list").json()
    ok([x["id"] for x in nl["received"] if x["title"].startswith("[TEST]")] == [C1], "Norov «Menga kelgan»: faqat o'ziniki")
    d = pro.get(f"/api/dir/{C1}").json()
    ok(d["root"] == P and {c["id"] for c in d["tree"]["children"]} == {C1, C2}, "prorektor (bergan): butun zanjir, ildizdan")
    ok(rektor.get(f"/api/dir/{C2}").status_code == 200 and kotib.get(f"/api/dir/{P}").status_code == 200, "rektor va kotib: ko'radi")
    v0 = denied_audits("topshiriqni ko'rish")
    for nm, c in (("Buxgalteriya", bux), ("IT boshlig'i", ithead), ("kafedra mudiri", k3), ("moliya prorektori", moliya), ("Akademik bo'lim", akad)):
        ok(c.get(f"/api/dir/{P}").status_code == 403 and c.get(f"/api/dir/{C1}").status_code == 403, f"{nm}: begona zanjir — 403")
    ok(denied_audits("topshiriqni ko'rish") - v0 == 10, "ko'rish rad etilishlari audit jurnalida (10 ta)")
    ok(norov.get(f"/api/dir/{MOL}").status_code == 403 and pro.get(f"/api/dir/{MOL}").status_code == 403, "moliya topshirig'i o'quv prorektoriga ham ko'rinmaydi")

    st = norov.get("/api/section/tasks").json()["tasks"]
    mine = [t for t in st if t["id"] == C1]
    ok(mine and mine[0]["directive"] and mine[0]["mine"] and mine[0]["meeting"].startswith("Topshiriq ·") and not any(t["id"] in (P, C2) for t in st),
       "/api/section/tasks (Norov): o'z topshirig'i (mine), asosiy va qo'shnisi yo'q")
    st = reg.get("/api/section/tasks").json()["tasks"]
    ok({P: True, C1: False, C2: False} == {t["id"]: t["mine"] for t in st if t["id"] in (P, C1, C2)},
       "Baratov: asosiy — o'z ishi (mine), xodimlarga berilganlar — nazoratda (mine emas)")
    ok(any(t["id"] == P and not t["mine"] for t in pro.get("/api/section/tasks").json()["tasks"]), "prorektor: bergan topshirig'i ro'yxatda (mine emas)")

    print("\n— 4. «Mening vazifalarim» va bildirishnomalar")
    mw = norov.get("/api/mywork").json()["items"]
    it = next((i for i in mw if i["id"] == f"mt{C1}"), None)
    ok(it and it["source"] == "majlis" and it["kind"] == "topshiriq" and it["who"] == "menga" and it["link"] == {"view": "tasks", "directive": C1},
       "Norov /api/mywork: topshiriq «Sizga», havola → topshiriq oynasi")
    ok(not any(i["id"] in (f"mt{P}", f"mt{C2}") for i in mw), "Norov ro'yxatida boshqalarniki yo'q")
    ok(any(i["id"] == f"mt{P}" for i in reg.get("/api/mywork").json()["items"]), "Baratov /api/mywork: asosiy topshiriq")
    ns = norov.get("/api/notifications").json()["items"]
    ok(any(n["id"] == f"dy{C1}" and "Yangi topshiriq" in n["title"] for n in ns), "Norov bildirishnomasi: «Yangi topshiriq»")
    mwc = cc.get("/api/mywork").json()["items"]
    ok(any(i["id"] == f"mt{C2}" for i in mwc), "Call-markaz (TASKS ruxsatisiz): topshiriq «Mening vazifalarim»da")
    ok(any(n["id"] == f"dy{C2}" for n in cc.get("/api/notifications").json()["items"]), "Call-markaz: «Yangi topshiriq» bildirishnomasi")
    ok(cc.get(f"/api/dir/{C2}").status_code == 200 and cc.get(f"/api/dir/{C1}").status_code == 403, "Call-markaz: o'z topshirig'ini ochadi, Norovnikini emas")

    print("\n— 5. Ijro, qabul va qaytarish")
    ok(cc.post(f"/api/dir/{C1}/status", json={"status": "jarayonda"}).status_code == 403, "begona ijrochi holatni o'zgartira olmaydi (403)")
    ok(norov.post(f"/api/dir/{C1}/status", json={"status": "jarayonda", "result": "Bir fakultet tayyor"}).status_code == 200, "Norov: jarayonda + oraliq natija")
    ok(norov.post(f"/api/dir/{C1}/status", json={"status": "bajarildi"}).status_code == 400, "natijasiz yakunlash — 400")
    ok(norov.post(f"/api/dir/{C1}/status", json={"status": "bajarildi", "result": "Ro'yxat tayyor: 37 talaba"}).status_code == 200, "Norov: bajarildi + natija")
    ok(one("SELECT status, review, result_by FROM tasks WHERE id=?", (C1,)) == ("bajarildi", "kutilmoqda", NOROV), "holat: bajarildi, qabul kutilmoqda")
    ok(norov.post(f"/api/dir/{C1}/review", json={"decision": "qabul"}).status_code == 403, "ijrochi o'z natijasini qabul qila olmaydi (403)")
    ok(any(i["id"] == f"dk{C1}" and i["who"] == "nazorat" for i in reg.get("/api/mywork").json()["items"]), "Baratov /api/mywork: «Natijani ko'rib chiqing»")
    ok(any(n["id"] == f"dk{C1}" for n in reg.get("/api/notifications").json()["items"]), "Baratov bildirishnomasi: natija qabulingizni kutmoqda")
    ok(any(x["id"] == C1 for x in reg.get("/api/dir/list?flt=review").json()["review"]), "Baratov «Qabulimni kutmoqda» filtri")
    ok(reg.post(f"/api/dir/{C1}/review", json={"decision": "qaytarish", "note": ""}).status_code == 400, "izohsiz qaytarish — 400")
    ok(reg.post(f"/api/dir/{C1}/review", json={"decision": "qaytarish", "note": "Sirtqi talabalar ham kiritilsin"}).status_code == 200, "Baratov: qayta ishlashga qaytardi")
    ok(one("SELECT status, review, review_note, review_by FROM tasks WHERE id=?", (C1,)) == ("jarayonda", "qaytarildi", "Sirtqi talabalar ham kiritilsin", 17),
       "holat: jarayonda, qaytarildi, izoh va kim qaytargani")
    ok(any(n["id"] == f"dq{C1}" for n in norov.get("/api/notifications").json()["items"]), "Norov bildirishnomasi: «Qayta ishlashga qaytarildi»")
    ok(norov.post(f"/api/dir/{C1}/status", json={"status": "bajarildi", "result": "Ro'yxat tayyor: 41 talaba (sirtqi bilan)"}).status_code == 200, "Norov qayta yubordi")
    ok(reg.post(f"/api/dir/{C1}/review", json={"decision": "qabul", "note": "Rahmat"}).status_code == 200, "Baratov qabul qildi")
    ok(one("SELECT review FROM tasks WHERE id=?", (C1,))[0] == "qabul", "holat: qabul qilindi")
    ok(cc.post(f"/api/dir/{C2}/status", json={"status": "bajarildi", "result": "28 talabaga qo'ng'iroq qilindi"}).status_code == 200, "Call-markaz yakunladi")
    d = reg.get(f"/api/dir/{P}").json()["tree"]
    ok(d["progress"] == {"done": 2, "total": 2} and d["suggest_complete"], "asosiy: 2/2 — yakunlash taklif qilinadi (suggest_complete)")
    ok(reg.post(f"/api/dir/{P}/status", json={"status": "bajarildi", "result": "Ro'yxat va qo'ng'iroqlar natijasi ilova qilindi"}).status_code == 200,
       "Baratov yakuniy natijani yubordi")
    ok(one("SELECT review FROM tasks WHERE id=?", (C2,))[0] == "qabul", "kutilayotgan quyi natija yakuniy natija bilan qabul qilindi")
    ok(reg.post(f"/api/dir/{P}/review", json={"decision": "qabul"}).status_code == 403, "Baratov o'z natijasini qabul qila olmaydi (403)")
    ok(any(x["id"] == P for x in pro.get("/api/dir/list?flt=review").json()["review"]), "prorektor: «Qabulimni kutmoqda»da")
    ok(reg.post(f"/api/dir/{C1}/review", json={"decision": "qaytarish", "note": "x"}).status_code == 409, "allaqachon qabul qilingan — qaytarib bo'lmaydi (409)")
    ok(pro.post(f"/api/dir/{P}/review", json={"decision": "qabul", "note": "Qabul qilindi"}).status_code == 200, "prorektor qabul qildi")
    log = [l["action"] for l in pro.get(f"/api/dir/{P}").json()["log"]]
    ok({"topshiriq berildi", "taqsimlandi", "ish boshlandi", "oraliq natija", "bajarildi — natija yuborildi", "qayta ishlashga qaytarildi", "qabul qilindi"} <= set(log),
       "tarix: berildi → taqsimlandi → ish boshlandi → natija → qaytarildi → qabul")
    ok(one("SELECT COUNT(*) FROM audit_log WHERE action='topshiriq natijasini ko''rib chiqish' AND allowed=0 AND detail=?", (f"#{P}",))[0] >= 1,
       "rad etilgan qabul urinishi audit jurnalida")

    # =============================================================================================
    print("\n— 6. Rektor → Akademik bo'lim → 2 kafedra; zanjirda yuqoridagi bergan (rektor) ham qabul qila oladi")
    r = create(rektor, unit="akademik", title="[TEST] Dars jadvali loyihasi", due_at=due(5))
    ok(r.status_code == 200, "rektor → Akademik bo'lim")
    R = r.json()["id"]
    r = akad.post(f"/api/dir/{R}/delegate", json={"items": [{"unit": "kaf3", "due_at": due(2)}, {"unit": "kaf6", "due_at": due(3)}]})
    ok(r.status_code == 200, "Akademik bo'lim → 2 kafedra (Menejment, Gumanitar)")
    K3, K6 = r.json()["ids"]
    ok(k3.get(f"/api/dir/{K3}").status_code == 200 and k3.get(f"/api/dir/{K6}").status_code == 403 and k6.get(f"/api/dir/{K3}").status_code == 403,
       "har bir kafedra faqat o'zinikini ko'radi")
    ok(any(i["id"] == f"mt{K3}" and i["who"] == "bolimga" for i in k3.get("/api/mywork").json()["items"]), "kafedra mudiri /api/mywork: bo'limiga kelgan topshiriq")
    ok(k3.post(f"/api/dir/{K3}/status", json={"status": "bajarildi", "result": "Takliflar yuborildi"}).status_code == 200, "kaf3 yakunladi")
    ok(one("SELECT assignee_user FROM tasks WHERE id=?", (K3,))[0] == KAF["kaf3"], "rahbar o'zi bajarsa — ijrochi sifatida yoziladi")
    ok(rektor.post(f"/api/dir/{K3}/review", json={"decision": "qabul"}).status_code == 200, "rektor (zanjirda yuqoridagi bergan) quyi natijani qabul qila oladi")
    ok(k6.post(f"/api/dir/{K6}/review", json={"decision": "qabul"}).status_code == 403, "begona kafedra qabul qila olmaydi")
    d = rektor.get(f"/api/dir/{R}").json()["tree"]
    ok(d["progress"] == {"done": 1, "total": 2} and not d["suggest_complete"], "rektor ko'rinishi: 1/2 bajarildi")

    print("\n— 7. Kotib — rektor nomidan")
    r = create(kotib, unit="xojalik", title="[TEST] Majlislar zalini tayyorlash", due_at=due(1))
    ok(r.status_code == 200, "kotib → Xo'jalik bo'limi (rektor nomidan)")
    KT = r.json()["id"]
    v = rektor.get(f"/api/dir/{KT}").json()["tree"]
    ok(v["on_behalf"] == "rektor" and v["issuer_label"].startswith("Rektor nomidan"), f"belgi: «{v['issuer_label']}»")
    ok(any(x["id"] == KT for x in rektor.get("/api/dir/list").json()["given"]), "rektorning «Men bergan» ro'yxatida ham")
    xo = S(16)
    ok(xo.post(f"/api/dir/{KT}/status", json={"status": "bajarildi", "result": "Zal tayyor"}).status_code == 200, "Xo'jalik bo'limi yakunladi")
    ok(rektor.post(f"/api/dir/{KT}/review", json={"decision": "qaytarish", "note": "Proyektor tekshirilsin"}).status_code == 200, "rektor (nomidan berilgan) qaytara oladi")

    print("\n— 8. Muddati o'tgan va demo zanjirlar")
    late = q("SELECT id FROM tasks WHERE origin='topshiriq' AND status!='bajarildi' AND due_at < ?", (dt.datetime.now().isoformat(timespec="seconds"),))
    if late:
        v = rektor.get(f"/api/dir/{late[0][0]}").json()
        node = [n for n in [v["tree"]] + v["tree"]["children"] if n["id"] == late[0][0]]
        ok(node and node[0]["overdue"], f"muddati o'tgan topshiriq #{late[0][0]} — overdue belgisi")
    ov = akad.get("/api/dir/list?flt=overdue").json()["given"]
    ok(all(x["overdue"] for x in ov), f"«Muddati o'tgan» filtri: faqat muddati o'tganlar ({len(ov)} ta)")
    ok(one("SELECT COUNT(*) FROM tasks WHERE origin='topshiriq' AND issuer_user=17 AND assignee_user=?", (NOROV,))[0] >= 1, "demo: Baratov → Norov A. zanjiri bor")
    ok(httpx.get(B + "/directives.js").status_code == 200 and 'src="directives.js"' in httpx.get(B + "/").text, "UI: directives.js ulangan")

    print("\n— 9. Bekor qilish")
    ok(reg.delete(f"/api/dir/{P}").status_code == 403, "Baratov prorektor topshirig'ini bekor qila olmaydi (403)")
    r = pro.delete(f"/api/dir/{P}")
    ok(r.status_code == 200 and r.json()["removed"] == 3, "prorektor bekor qildi — zanjir (3 ta) o'chirildi")
    ok(pro.get(f"/api/dir/{C1}").status_code == 404 and one("SELECT COUNT(*) FROM task_log WHERE task_id IN (?,?,?)", (P, C1, C2))[0] == 0, "yozuvlar va tarix o'chirildi")
    ok(one("SELECT allowed, user_id, detail FROM audit_log WHERE action='topshiriqni bekor qilish' ORDER BY id DESC")[:2] == (1, 3)
       and one("SELECT detail FROM audit_log WHERE action='topshiriqni bekor qilish' ORDER BY id DESC")[0].startswith(f"#{P} "), "bekor qilish audit jurnalida qoladi")
finally:
    print("\ntozalash:", cleanup())

print(f"\nHAMMASI O'TDI: {N[0]} ta tekshiruv.")
