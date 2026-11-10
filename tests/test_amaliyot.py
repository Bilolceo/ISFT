import os
"""«Amaliyot» (app/amaliyot.py): uchidan-uchigacha HTTP testlar (server ishlab turishi kerak).

Ishga tushirish:  ISFT_TEST_URL=http://127.0.0.1:8000 ISFT_CORE_DB=data/jarvis.db .venv/bin/python tests/test_amaliyot.py
Test bazani o'zgartiradi (yangi baza, davrlar, biriktirish, yo'llanma, baho, talaba hisoboti) — demo holatini tiklash uchun keyin `python -m app.seed`.
Qamrov: lavozimlar ko'lami (29 amaliyot, 14/31 kafedra, 15 o'qituvchi, tyutor, 17/27 registrator/sirtqi, 2 rektor; 23 → 403), bazalar reyestri
(shartnoma, sig'im), davrlar (jadval va o'quv reja), biriktirish (sig'im, shartnoma muddati, kafedra rahbari), yo'llanma (Hujjatlar markazi),
holatlar va baho (faqat kafedra rahbari), ogohlantirishlar, statistika, talaba kabineti (kundalik, hisobot).
"""
import datetime as dt, hashlib, secrets, sqlite3, sys, time
from pathlib import Path
import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT)); from app import clock as CLK, sessions as SS   # noqa: E402
DB = Path(os.environ.get("ISFT_CORE_DB") or ROOT / "data" / "jarvis.db")
B = os.environ.get("ISFT_TEST_URL", "http://127.0.0.1:8000")
PW = "Isft2026"
N = [0]
P = "/api/practice"

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

T0 = CLK.now_iso()[:19]
TODAY = CLK.today()
AML, KAF4, KAF2, OQ, REG, SIR, REK, CC = S(29), S(14), S(31), S(15), S(17), S(27), S(2), S(23)
TID = q1("SELECT teacher_id FROM users WHERE id=15")
TUT_ID = q1("SELECT tg.user_id FROM tutor_groups tg JOIN prac_periods p ON p.group_id=tg.group_id ORDER BY tg.user_id LIMIT 1")
TUT = S(TUT_ID)

print("— Ruxsatlar va ko'lam —")
ok(httpx.get(B + P + "/meta").status_code == 401, "Kirishsiz: 401")
for path in ("/meta", "/periods", "/bases", "/alerts", "/stats"):
    ok(CC.get(P + path).status_code == 403, f"Call-markaz (23): {path} → 403")
ok(q1("SELECT COUNT(*) FROM audit_log WHERE resource='practice' AND allowed=0 AND user_id=23 AND ts>=?", (T0,)) >= 5, "Rad etilgan so'rovlar audit jurnalida (resource=practice)")
want = {29: "full", 14: "kafedra", 15: "oqituvchi", 17: "reg", 27: "reg", 2: "lead", TUT_ID: "tyutor"}
for u, c in ((29, AML), (14, KAF4), (15, OQ), (17, REG), (27, SIR), (2, REK), (TUT_ID, TUT)):
    m = J(c.get(P + "/meta"))
    ok(m["mode"] == want[u], f"#{u}: rejim {m['mode']} · bo'limlar {m['tabs']}")
M = J(AML.get(P + "/meta"))
ok(M["caps"]["edit"] and not M["caps"]["grade"], "Amaliyot bo'limi: tahrirlaydi, lekin baho qo'ymaydi")
ok(J(OQ.get(P + "/meta"))["caps"]["grade"] and not J(OQ.get(P + "/meta"))["caps"]["edit"], "O'qituvchi: baho qo'yadi, bazalar/davrlar tahriri yo'q")
ok(REK.get(P + "/periods").status_code == 403 and REK.get(P + "/assign/1").status_code == 403, "Rektor: talabalar ro'yxati yopiq (faqat jamlangan)")
ok(J(REK.get(P + "/stats"))["by_base"], "Rektor: statistika ochiq")
ra = J(REK.get(P + "/alerts"))
ok(all(x["full_name"] == "—" for k in ra["items"] for x in ra["items"][k]), "Rektor: ogohlantirishlarda ism-shariflar yashirilgan")
for c, path, body, who in ((KAF4, "/bases", {"name": "X"}, "kafedra"), (REG, "/periods", {"group_ids": [1]}, "registrator"), (OQ, "/periods/1/assign", {"base_id": 1}, "o'qituvchi"),
                           (TUT, "/periods/1/referrals", {}, "tyutor")):
    ok(c.post(P + path, json=body).status_code == 403, f"{who}: {path} yozish → 403")

print("— Demo ma'lumot —")
ok(q1("SELECT COUNT(*) FROM prac_bases") >= 10, f"Bazalar: {q1('SELECT COUNT(*) FROM prac_bases')}")
ok(q1("SELECT COUNT(*) FROM prac_periods") >= 8, f"Davrlar: {q1('SELECT COUNT(*) FROM prac_periods')}")
ok(q1("SELECT COUNT(DISTINCT status) FROM prac_assign") >= 4, "Biriktirishlar barcha holatlarda")
AL = J(AML.get(P + "/alerts"))
ok(AL["counts"]["hisobot_kechikdi"] > 0, f"Hisobot muddati o'tganlar: {AL['counts']['hisobot_kechikdi']}")
ok(AL["counts"]["boshlanmagan"] > 0, f"Amaliyotga chiqmaganlar: {AL['counts']['boshlanmagan']}")
st = {a["agreement_state"] for a in AL["agreements"]}
ok({"tugayapti", "muddati o'tgan"} <= st, f"Shartnoma ogohlantirishlari: {st}")
ok(all(r["report_due"] < TODAY.isoformat() for r in AL["items"]["hisobot_kechikdi"]), "Kechikkanlar — faqat muddati o'tganlar")

print("— Ko'lam —")
ps_oq = J(OQ.get(P + "/periods"))
ok(ps_oq and all(q1("SELECT COUNT(*) FROM prac_assign WHERE period_id=? AND kaf_supervisor_id=?", (p["id"], TID)) for p in ps_oq),
   f"O'qituvchi: faqat o'zi rahbar bo'lgan davrlar ({len(ps_oq)})")
d_oq = J(OQ.get(f"{P}/periods/{ps_oq[0]['id']}"))
ok(d_oq["rows"] and all(r["kaf_supervisor_id"] == TID for r in d_oq["rows"]), "O'qituvchi: davr ichida faqat o'z talabalari")
other = q1("SELECT id FROM prac_assign WHERE kaf_supervisor_id!=? AND kaf_supervisor_id IS NOT NULL LIMIT 1", (TID,))
ok(OQ.get(f"{P}/assign/{other}").status_code == 403, "O'qituvchi: boshqa rahbarning talabasi → 403")
ps_k4 = J(KAF4.get(P + "/periods"))
ok(ps_k4 and all(p["department_id"] == 4 for p in ps_k4), "Kafedra mudiri: faqat o'z kafedrasi guruhlari")
ps_t = J(TUT.get(P + "/periods"))
tg = {r[0] for r in q("SELECT group_id FROM tutor_groups WHERE user_id=?", (TUT_ID,))}
ok(ps_t and all(p["group_id"] in tg for p in ps_t), f"Tyutor: faqat o'z guruhlari ({len(ps_t)})")
ok(all(p["form"] == "sirtqi" for p in J(SIR.get(P + "/periods"))), "Sirtqi bo'lim: faqat sirtqi guruhlar")
ok(len(J(REG.get(P + "/periods"))) == q1("SELECT COUNT(*) FROM prac_periods"), "Registrator: barcha davrlar (o'qish)")

print("— Bazalar reyestri —")
DIR4 = "Buxgalteriya hisobi va moliya"
bad = AML.post(P + "/bases", json={"name": "Test baza", "kind": "xususiy", "agreement_no": "T-1", "agreement_date": "2026-01-01", "agreement_expires": "2025-01-01", "caps": {DIR4: 3}})
ok(bad.status_code == 400, "Shartnoma muddati imzodan oldin → 400")
ok(AML.post(P + "/bases", json={"name": "Test baza", "kind": "xususiy", "agreement_no": "T-1", "agreement_date": "2026-01-01", "agreement_expires": "2028-01-01", "caps": {}}).status_code == 400,
   "Sig'imsiz baza → 400")
ok(AML.post(P + "/bases", json={"name": "Test baza", "kind": "xususiy", "agreement_no": "T-1", "agreement_date": "2026-01-01", "agreement_expires": "2028-01-01", "caps": {"Yo'q yo'nalish": 3}}).status_code == 400,
   "Noma'lum yo'nalish → 400")
nm = f"Test amaliyot bazasi {secrets.token_hex(3)}"
BID = J(AML.post(P + "/bases", json={"name": nm, "kind": "xususiy", "agreement_no": "T-1", "agreement_date": "2026-01-01", "agreement_expires": "2028-01-01", "caps": {DIR4: 3}}))["id"]
ok(AML.post(P + "/bases", json={"name": nm, "kind": "xususiy", "agreement_no": "T-2", "agreement_date": "2026-01-01", "agreement_expires": "2028-01-01", "caps": {DIR4: 3}}).status_code == 400,
   "Takror nom → 400")
BSHORT = J(AML.post(P + "/bases", json={"name": nm + " (qisqa)", "kind": "davlat", "agreement_no": "T-3", "agreement_date": "2025-01-01", "agreement_expires": (TODAY + dt.timedelta(days=20)).isoformat(), "caps": {DIR4: 30}}))["id"]
bl = {b["id"]: b for b in J(AML.get(P + "/bases"))}
ok(bl[BID]["agreement_state"] == "amalda" and bl[BSHORT]["agreement_state"] == "tugayapti", "Shartnoma holati: amalda / tugayapti")
ok(q1("SELECT COUNT(*) FROM audit_log WHERE resource='practice' AND allowed=1 AND user_id=29 AND action LIKE '%baza qo''shildi%' AND ts>=?", (T0,)) >= 2, "Baza qo'shish auditda")

print("— Davrlar —")
G = q("SELECT id, name FROM groups_ WHERE department_id=4 AND form='kunduzgi' AND course=1 AND id NOT IN (SELECT group_id FROM prac_periods) ORDER BY id LIMIT 1")[0]
GID, GSIZE = G[0], q1("SELECT COUNT(*) FROM students WHERE group_id=? AND status='faol'", (G[0],))
s0, e0 = (TODAY + dt.timedelta(days=20)).isoformat(), (TODAY + dt.timedelta(days=40)).isoformat()
ok(AML.post(P + "/periods", json={"group_ids": [GID], "kind": "oquv", "start": e0, "end": s0}).status_code == 400, "Tugash boshlanishdan oldin → 400")
r = J(AML.post(P + "/periods", json={"group_ids": [GID], "kind": "oquv", "start": s0, "end": e0, "credits": 3}))
ok(len(r["created"]) == 1, f"Jadval bo'yicha davr yaratildi: {G[1]}")
PID = r["created"][0]["id"]
ok(q1("SELECT report_due FROM prac_periods WHERE id=?", (PID,)) == (dt.date.fromisoformat(e0) + dt.timedelta(days=7)).isoformat(), "Hisobot muddati — standart (tugash + 7 kun)")
r = J(AML.post(P + "/periods", json={"group_ids": [GID], "kind": "ishlab", "start": s0, "end": e0}))
ok(not r["created"] and r["skipped"], "Shu vaqtda ikkinchi davr — o'tkazib yuborildi")
pl = J(AML.get(P + "/plan?term=2"))
ok(pl["rows"] and all("amaliyot" in x["subject"].lower() for x in pl["rows"]), f"O'quv reja (keyingi semestr): {len(pl['rows'])} ta guruhda amaliyot")
ok(all(x["sem_no"] == 2 * x["course"] for x in pl["rows"]), "O'quv reja: bahorgi semestr raqami to'g'ri (2·kurs)")
pick = [x["group_id"] for x in pl["rows"] if not x["exists"] and x["form"] == "kunduzgi"][:2]
r = J(AML.post(P + "/periods/from-curriculum", json={"term": 2, "group_ids": pick}))
ok(len(r["created"]) == len(pick) == 2, "O'quv reja bo'yicha 2 ta davr yaratildi")
ok(q1(f"SELECT COUNT(*) FROM prac_periods WHERE source='o''quv reja' AND group_id IN ({pick[0]},{pick[1]}) AND kind='malakaviy' AND start>=?", (pl["start"],)) == 2,
   "Davr turi «malakaviy», manba «o'quv reja», bahorgi sanalar")
ok(all(x["exists"] for x in J(AML.get(P + "/plan?term=2"))["rows"] if x["group_id"] in pick), "Rejada «davr bor» belgilandi")
ok(KAF4.get(P + "/plan?term=2").status_code == 200 and KAF4.post(P + "/periods/from-curriculum", json={"term": 2}).status_code == 403,
   "Kafedra: rejani ko'radi, davr yaratmaydi")

print("— Biriktirish —")
d = J(AML.get(f"{P}/periods/{PID}"))
ok(len(d["unassigned"]) == GSIZE and any(b["id"] == BID for b in d["bases"]), f"Biriktirilmagan: {GSIZE}; test bazasi ro'yxatda")
ok(not next(b for b in d["bases"] if b["id"] == BSHORT)["ok"], "Shartnomasi amaliyotdan oldin tugaydigan baza — «ok» emas")
ok(AML.post(f"{P}/periods/{PID}/assign", json={"base_id": BSHORT, "all_unassigned": True}).status_code == 400, "Shartnoma muddati yetmaydi → 400")
r = AML.post(f"{P}/periods/{PID}/assign", json={"base_id": BID, "all_unassigned": True})
ok(r.status_code == 400 and "Sig'im" in r.text, "Sig'imdan ko'p (3 o'rin) → 400")
other_t = q1("SELECT id FROM teachers WHERE department_id!=4 LIMIT 1")
st3 = [x["id"] for x in d["unassigned"][:3]]
ok(AML.post(f"{P}/periods/{PID}/assign", json={"base_id": BID, "student_ids": st3, "kaf_supervisor_id": other_t}).status_code == 400, "Boshqa kafedra o'qituvchisi rahbar → 400")
r = J(AML.post(f"{P}/periods/{PID}/assign", json={"base_id": BID, "student_ids": st3, "kaf_supervisor_id": TID, "org_supervisor": "Test Rahbar", "org_phone": "+998 90 000 00 00"}))
ok(r["assigned"] == 3 and r["free_left"] == 0, "3 talaba biriktirildi, bo'sh joy 0")
ok(AML.post(f"{P}/periods/{PID}/assign", json={"base_id": BID, "student_ids": [d["unassigned"][3]["id"]]}).status_code == 400, "Bazada joy qolmadi → 400")
ok(AML.post(f"{P}/periods/{PID}/assign", json={"base_id": BID, "student_ids": [st3[0]]}).status_code == 400, "Takror biriktirish → 400")
d = J(AML.get(f"{P}/periods/{PID}"))
a_ids = [x["id"] for x in d["rows"]]
ok(J(AML.post(f"{P}/assign/{a_ids[2]}/unassign"))["ok"] and len(J(AML.get(f"{P}/periods/{PID}"))["rows"]) == 2, "Biriktirish bekor qilindi")
ok(J(KAF4.post(f"{P}/periods/{PID}/supervisor", json={"org_supervisor": "Yangi Rahbar"}))["updated"] == 2, "Kafedra mudiri: rahbarni yangiladi")
ok(KAF2.post(f"{P}/periods/{PID}/supervisor", json={"org_supervisor": "X"}).status_code == 403, "Boshqa kafedra mudiri: → 403")
ok(AML.post(f"{P}/assign/{a_ids[0]}/status", json={"status": "start"}).status_code == 400, "Amaliyot boshlanmagan — «amaliyotga chiqdi» → 400")

print("— Yo'llanma (Hujjatlar markazi) —")
n0 = q1("SELECT COUNT(*) FROM documents WHERE kind='practice'")
r = J(AML.post(f"{P}/periods/{PID}/referrals"))
ok(r["issued"] == 2 and q1("SELECT COUNT(*) FROM documents WHERE kind='practice'") == n0 + 2, f"Yo'llanma berildi: {r['regs']}")
ok(q1("SELECT COUNT(*) FROM prac_assign WHERE period_id=? AND doc_reg LIKE 'AY-%'", (PID,)) == 2, "Ro'yxat raqami biriktirishga yozildi")
ok(AML.post(f"{P}/periods/{PID}/referrals").status_code == 400, "Takror yo'llanma → 400")

print("— Holatlar va baho —")
A_START = q1("""SELECT a.id FROM prac_assign a JOIN prac_periods p ON p.id=a.period_id WHERE a.status='biriktirildi' AND p.start<=? AND a.base_id IS NOT NULL LIMIT 1""", (TODAY.isoformat(),))
ok(J(AML.post(f"{P}/assign/{A_START}/status", json={"status": "start"}))["ok"] and q1("SELECT status FROM prac_assign WHERE id=?", (A_START,)) == "boshlandi", "Amaliyot bo'limi: «amaliyotga chiqdi»")
A_REP = q1("SELECT a.id FROM prac_assign a WHERE a.status='hisobot' AND a.kaf_supervisor_id=? LIMIT 1", (TID,))
A_BOSH = q1("SELECT a.id FROM prac_assign a WHERE a.status='boshlandi' AND a.kaf_supervisor_id=? LIMIT 1", (TID,))
ok(AML.post(f"{P}/assign/{A_REP}/grade", json={"score": 80}).status_code == 403, "Amaliyot bo'limi baho qo'ymaydi → 403")
ok(KAF2.post(f"{P}/assign/{A_REP}/grade", json={"score": 80}).status_code == 403, "Boshqa kafedra mudiri baho qo'ymaydi → 403")
ok(OQ.post(f"{P}/assign/{A_BOSH}/grade", json={"score": 80}).status_code == 400, "Hisobotsiz baho → 400")
ok(OQ.post(f"{P}/assign/{A_REP}/grade", json={"score": 120}).status_code == 400, "Ball 0..100 → 400")
r = J(OQ.post(f"{P}/assign/{A_REP}/grade", json={"score": 82, "note": "Yaxshi"}))
ok(r["letter"] == "A" and r["passed"] and q1("SELECT status||score FROM prac_assign WHERE id=?", (A_REP,)) == "baholandi82", "O'qituvchi (rahbar): 82 → «A», baholandi")
ok(OQ.post(f"{P}/assign/{A_REP}/grade", json={"score": 70}).status_code == 400, "Bahoni o'zgartirish sababsiz → 400")
ok(J(KAF4.post(f"{P}/assign/{A_REP}/grade", json={"score": 75, "note": "Tavsifnoma qayta ko'rildi"}))["ok"], "Kafedra mudiri: sabab bilan qayta baholadi")
ok(J(OQ.post(f"{P}/assign/{A_BOSH}/status", json={"status": "receive", "report": "Qog'ozdagi hisobot qabul qilindi, kundalik ilova"}))["ok"]
   and q1("SELECT report_by FROM prac_assign WHERE id=?", (A_BOSH,)) not in (None, "talaba"), "Rahbar qog'oz hisobotni qabul qildi")
ok(OQ.post(f"{P}/assign/{A_BOSH}/status", json={"status": "return", "note": ""}).status_code == 400, "Sababsiz qaytarish → 400")
ok(J(OQ.post(f"{P}/assign/{A_BOSH}/status", json={"status": "return", "note": "Xulosa qismi yo'q"}))["ok"]
   and q1("SELECT status FROM prac_assign WHERE id=?", (A_BOSH,)) == "qaytarildi", "Hisobot qaytarildi")
ok(J(OQ.post(f"{P}/assign/{A_BOSH}/diary", json={"text": "Rahbar: xulosani to'ldiring"}))["ok"], "Rahbar kundalikka izoh yozdi")
det = J(OQ.get(f"{P}/assign/{A_BOSH}"))
ok(det["diary"][-1]["author_kind"] == "rahbar" and det["return_note"], "Talaba kartasida izoh va qaytarish sababi")
ok(TUT.post(f"{P}/assign/{A_BOSH}/diary", json={"text": "tyutor izohi"}).status_code == 403, "Tyutor: yozish → 403")

print("— Talaba kabineti —")
SID = q1("""SELECT a.student_id FROM prac_assign a JOIN prac_periods p ON p.id=a.period_id JOIN students s ON s.id=a.student_id
    WHERE a.status='boshlandi' AND p.end>=? AND s.status='faol' AND a.student_id NOT IN (SELECT student_id FROM student_auth) LIMIT 1""", (TODAY.isoformat(),))
AID = q1("SELECT id FROM prac_assign WHERE student_id=? AND status='boshlandi'", (SID,))
pwh = "test-amaliyot-" + secrets.token_hex(4)
w("INSERT OR REPLACE INTO student_auth(student_id,pw_hash,must_change,created_at) VALUES(?,?,0,?)", (SID, pwh, CLK.now_iso()))
tok = secrets.token_urlsafe(32)
w("INSERT INTO student_sessions(token,student_id,created,expires,pw_tag,ip,ua,last_seen) VALUES(?,?,?,?,?,?,?,?)",
  (hashlib.sha256(tok.encode()).hexdigest(), SID, time.time(), time.time() + 3600, SS.pw_tag(pwh), "127.0.0.1", "test", time.time()))
ST = httpx.Client(base_url=B, timeout=60, cookies={"tsid": tok})
ok(httpx.get(B + "/api/talaba/amaliyot").status_code == 401, "Talaba kabineti: kirishsiz 401")
t = J(ST.get("/api/talaba/amaliyot"))
it = next(x for x in t["items"] if x["id"] == AID)
ok(it["base"] and it["can_diary"] and it["can_report"], f"Talaba o'z amaliyotini ko'radi: {it['base']}")
ok(ST.post(f"/api/talaba/amaliyot/{AID}/diary", json={"text": "Bugun hisobot jadvalini tayyorladim", "day": (TODAY + dt.timedelta(days=1)).isoformat()}).status_code == 400,
   "Ertangi kun uchun kundalik → 400")
ok(J(ST.post(f"/api/talaba/amaliyot/{AID}/diary", json={"text": "Bugun hisobot jadvalini tayyorladim"}))["ok"], "Talaba kundalik yozdi")
ok(ST.post(f"/api/talaba/amaliyot/{AID}/report", json={"text": "qisqa"}).status_code == 400, "Qisqa hisobot → 400")
other_a = q1("SELECT id FROM prac_assign WHERE student_id!=? LIMIT 1", (SID,))
ok(ST.post(f"/api/talaba/amaliyot/{other_a}/report", json={"text": "x" * 300}).status_code == 404, "Boshqa talabaning amaliyoti → 404")
rep = "Amaliyot davomida tashkilotning moliya bo'limida ishladim. " * 6
ok(J(ST.post(f"/api/talaba/amaliyot/{AID}/report", json={"text": rep}))["ok"] and q1("SELECT status||report_by FROM prac_assign WHERE id=?", (AID,)) == "hisobottalaba",
   "Talaba hisobot topshirdi → «Hisobot topshirildi»")
ok(ST.post(f"/api/talaba/amaliyot/{AID}/report", json={"text": rep}).status_code == 400, "Takror topshirish → 400")
ok(q1("SELECT COUNT(*) FROM audit_log WHERE resource='practice' AND role='Talaba' AND ts>=?", (T0,)) >= 3, "Talaba amallari auditda (resource=practice)")
w("DELETE FROM student_sessions WHERE student_id=?", (SID,)); w("DELETE FROM student_auth WHERE student_id=? AND pw_hash=?", (SID, pwh))

print("— Statistika —")
s = J(AML.get(P + "/stats"))
ok(s["by_base"] and s["by_group"] and s["by_kind"], f"Statistika: {len(s['by_base'])} baza, {len(s['by_group'])} davr, {len(s['by_kind'])} tur")
ok(sum(x["students"] or 0 for x in s["by_base"]) == q1("SELECT COUNT(*) FROM prac_assign WHERE base_id IS NOT NULL"), "Bazalar kesimida jami = biriktirishlar soni")
sk = J(KAF4.get(P + "/stats"))
ok(all(q1("SELECT department_id FROM groups_ WHERE id=?", (g["id"],)) == 4 for g in sk["by_group"]), "Kafedra statistikasi — faqat o'z guruhlari")
ok(q1("SELECT COUNT(*) FROM audit_log WHERE resource='practice' AND ts>=?", (T0,)) > 50, "Barcha murojaatlar auditda")
print(f"Hammasi o'tdi: {N[0]} ta tekshiruv.")
