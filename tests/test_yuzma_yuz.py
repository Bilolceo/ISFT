"""«Yuzma-yuz tadbirlar» va masofaviy ta'limning huquqiy chegaralari (app/yuzma_yuz.py, app/nazorat.py — «Yuzma-yuz» bo'limi, docs/yuzma_yuz.md).

1. Birlik: umumiy akkaunt alomatlari (sof funksiya), chegara darajalari (90 % / 100 %), semestr kaliti.
2. HTTP: sessiya yaratish, sig'im (ortiqcha tayinlash — 409), xorijiy fuqaro — ozod, shaxsni tekshirish (to'liq hujjat raqami — 400; raqamlar
   bazada yo'q; HEMIS ma'lumotnomasi — xesh), qaydnoma (faqat bo'lim boshlig'i; .docx/.pdf; reyestr va /verify), muddat bayrog'i (talaba
   kabineti va Nazorat markazi), ruxsatlar (talaba — faqat o'zi, tyutor — o'z guruhlari, rektor — ismsiz, kafedra — 403, jurnal — faqat bo'lim).
3. Kirish jurnali: talaba kabinetiga turli tarmoq va qurilmadan kirish → alomat (bloklanmaydi), xom IP saqlanmaydi, ko'rib chiqish.
4. Jarayon ichida (bazaning nusxasi): huquqiy chegaralar detektorlari — 299/300/301 (bakalavr), 30/31 (magistratura), 50/51 (o'qituvchi),
   kunduzgisiz yo'nalish, pedagogik yo'nalish (qo'lda bekor qilish), rektor qoidasini o'zgartirish.
5. Brauzer (PW va CHROME berilganda): xodim ekrani (keng va telefon) va talaba kartasi telefon kengligida (tools/yuzma_check.js).

Ishga tushirish: python tests/run_all.py --only yuzma_yuz. DIQQAT: bazani o'zgartiradi (sessiyalar, fuqarolik, muddat, kirishlar).
"""
import datetime as dt, io, json, os, re, shutil, sqlite3, subprocess, sys, tempfile, zipfile
from pathlib import Path
import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
B = os.environ.get("ISFT_TEST_URL", "http://127.0.0.1:8000")
DBP = Path(os.environ.get("ISFT_CORE_DB") or ROOT / "data" / "jarvis.db")
PW = re.search(r'DEMO_PASSWORD = os.getenv\("ISFT_CORE_DEMO_PASSWORD", "([^"]+)"\)', (ROOT / "app" / "rbac.py").read_text()).group(1)
SDEMO = os.getenv("ISFT_CORE_STUDENT_DEMO_PASSWORD", "Talaba2026")
NEWPW = "Yuzma2026x"
P = "/api/yuzma"
fails = []
def ok(cond, msg):
    print(("  ✓ " if cond else "  ✗ ") + msg)
    if not cond: fails.append(msg)
def q(sql, a=()):
    con = sqlite3.connect(DBP, timeout=30); con.row_factory = sqlite3.Row
    try: return [dict(r) for r in con.execute(sql, a).fetchall()]
    finally: con.close()
def w(sql, a=()):
    con = sqlite3.connect(DBP, timeout=30)
    try: cur = con.execute(sql, a); con.commit(); return cur.lastrowid
    finally: con.close()
def uid(role):
    r = q("SELECT id FROM users WHERE role=? AND COALESCE(active,1)=1 ORDER BY id LIMIT 1", (role,)); assert r, role; return r[0]["id"]
def S(u):
    c = httpx.Client(base_url=B, timeout=300)
    r = c.post("/api/login", json={"user_id": u, "password": PW}); assert r.status_code == 200, f"login {u}: {r.text}"
    return c
def ST(sid, ip=None, ua="Mozilla/5.0 (Windows NT 10.0) Chrome/129"):
    h = q("SELECT hemis_id FROM students WHERE id=?", (sid,))[0]["hemis_id"]
    hd = {"User-Agent": ua, **({"X-Forwarded-For": ip} if ip else {})}
    c = httpx.Client(base_url=B, timeout=120, headers=hd)
    r = c.post("/api/talaba/login", json={"hemis_id": h, "password": SDEMO})
    if r.status_code != 200: r = c.post("/api/talaba/login", json={"hemis_id": h, "password": NEWPW})
    assert r.status_code == 200, r.text
    if r.json().get("must_change"):
        assert c.post("/api/talaba/password", json={"current": SDEMO, "new": NEWPW}).status_code == 200
    return c
def last_audit(): return (q("SELECT MAX(id) m FROM audit_log") or [{"m": 0}])[0]["m"] or 0

# =============================================================================================
print("== 1. Birlik: alomatlar, chegara darajalari, semestr")
from app import yuzma_yuz as Y0   # noqa: E402 — faqat sof funksiyalar
t = lambda h, m=0: f"2026-11-10T{h:02d}:{m:02d}:00"
ev = [{"ts": t(9), "net": "A", "ua": "u1", "parallel": 0}, {"ts": t(9, 6), "net": "B", "ua": "u2", "parallel": 0}]
ok({f["kind"] for f in Y0.analyze(ev)} == {"almashish"}, "6 daqiqada boshqa tarmoq + boshqa qurilma — «imkonsiz almashish»")
ok(not Y0.analyze([ev[0], {"ts": t(9, 6), "net": "B", "ua": "u1", "parallel": 0}]), "Faqat tarmoq almashgan (o'sha qurilma: Wi-Fi → mobil) — alomat emas")
ok(not Y0.analyze([ev[0], {"ts": t(9, 30), "net": "B", "ua": "u2", "parallel": 0}]), "30 daqiqadan keyin almashish — alomat emas")
ok([f["kind"] for f in Y0.analyze([{**ev[1], "parallel": 1}])] == ["parallel"], "Kirish paytida boshqa tarmoqdagi faol sessiya — «bir vaqtda»")
many = [{"ts": t(8 + 2 * i), "net": f"N{i}", "ua": "u1", "parallel": 0} for i in range(4)]
ok({f["kind"] for f in Y0.analyze(many)} == {"kop_tarmoq"} and not Y0.analyze(many[:3]), "Sutkada 4 tarmoq — alomat; 3 tarmoq — yo'q")
ok([Y0.level_of(n, 300, 90) for n in (269, 270, 299, 300, 301)] == ["ok", "amber", "amber", "red", "red"], "Kvota: 270 (90 %) — sariq, 300 (100 %) — qizil")
ok(Y0.term_of(dt.date(2026, 11, 14)) == "2026-K" and Y0.term_of(dt.date(2027, 1, 20)) == "2026-K" and Y0.term_of(dt.date(2027, 3, 1)) == "2027-B"
   and Y0.term_of(dt.date(2027, 8, 20)) == "2027-K", "Semestr kaliti (iyul–avgust — kelayotgan kuzgi semestr)")

# =============================================================================================
print("== 2. HTTP: sessiya, sig'im, ozod, shaxsni tekshirish, qaydnoma")
HEAD, XOD, REG, REGX, REK, KAF, TUTU = (uid(r) for r in ("masofaviy", "masofaviy_xodim", "talabalar", "registrator_xodim", "rektor", "kafedra", "tyutor"))
head, xod, reg, regx, rek, kaf = S(HEAD), S(XOD), S(REG), S(REGX), S(REK), S(KAF)
a0 = last_audit()
ok(kaf.get(P + "/overview").status_code == 403 and kaf.get(P + "/limits").status_code == 403, "Kafedra mudiri: yuzma-yuz va chegaralar — 403")
ok(q("SELECT 1 FROM audit_log WHERE id>? AND action LIKE 'yuzma-yuz:%' AND allowed=0", (a0,)) != [], "Rad etilgan so'rov audit jurnalida")
M = xod.get(P + "/meta").json()
TODAY, TERM = M["today"], M["term"]
ov = head.get(P + "/overview").json()
ok(ov["deadline_passed"] and ov["counts"]["muddati_otgan"] > 0 and ov["counts"]["ozod"] > 0, f"Namuna: muddat o'tgan {ov['counts']['muddati_otgan']}, ozod {ov['counts']['ozod']}")
over = [r for r in xod.get(P + "/students", params={"state": "muddati_otgan", "limit": 200}).json()["items"]]
ok(len(over) >= 8 and all(r["state"] == "muddati_otgan" for r in over), "Ro'yxat: muddat o'tganlar filtri")
up_ids = {r["student_id"] for r in q("SELECT DISTINCT student_id FROM yy_assign UNION SELECT student_id FROM student_auth")}      # hech qayerga tayinlanmaganlar
free_over = [r["id"] for r in over if r["id"] not in up_ids]
S1, S2, S3, S4, S5 = free_over[:5]
SX = free_over[5]                         # brauzer: banner (muddat o'tgan)
r = xod.post(P + "/sessions", json={"kind": "royxat", "title": "Test: bugungi sessiya", "date": TODAY, "start_time": "08:00", "end_time": "09:30",
                                     "room": "Test xona 1", "capacity": 3})
ok(r.status_code == 200 and r.json()["session"]["capacity"] == 3, f"Xodim sessiya yaratdi ({r.status_code})")
SID = r.json()["session"]["id"]
ok(xod.post(P + "/sessions", json={"kind": "royxat", "date": TODAY, "start_time": "09:00", "end_time": "10:00", "room": "Test xona 1", "capacity": 5}).status_code == 409,
   "Shu xonada vaqti kesishgan sessiya — 409")
ok(xod.post(P + "/sessions", json={"kind": "royxat", "date": "2020-01-01", "room": "Test xona 2", "capacity": 5}).status_code == 400, "O'tgan sanaga — 400")
r4 = xod.post(f"{P}/sessions/{SID}/assign", json={"student_ids": [S1, S2, S3, S4]})
ok(r4.status_code == 409 and "Sig'im" in r4.text and not q("SELECT 1 FROM yy_assign WHERE session_id=?", (SID,)), "4 talaba > sig'im 3 — 409, hech kim yozilmadi")
r3 = xod.post(f"{P}/sessions/{SID}/assign", json={"student_ids": [S1, S2, S3]})
ok(r3.status_code == 200 and r3.json()["assigned"] == 3 and r3.json()["free"] == 0, "3 talaba tayinlandi — bo'sh joy 0")
nts = q("SELECT n.text FROM yy_assign a JOIN ops_notices n ON n.id=a.notice_id WHERE a.session_id=?", (SID,))
ok(len(nts) == 3 and all("Test xona 1" in n["text"] and "ID kartangizni" in n["text"] for n in nts), "Har bir talabaga xabar navbatda (sana, xona, hujjat)")
ok(xod.post(f"{P}/sessions/{SID}/assign", json={"student_ids": [S4]}).status_code == 409, "To'lgan sessiyaga yana — 409")
# xorijiy fuqaro — ozod
FOR = q("SELECT id FROM students WHERE study_form='masofaviy' AND status='faol' AND citizenship IS NOT NULL ORDER BY id LIMIT 1")[0]["id"]
r = xod.post(P + "/sessions", json={"kind": "imtihon", "title": "Test: yakuniy", "date": TODAY, "start_time": "14:00", "end_time": "15:00", "room": "Test xona 2", "capacity": 10})
SID2 = r.json()["session"]["id"]
ra = xod.post(f"{P}/sessions/{SID2}/assign", json={"student_ids": [FOR, S4]}).json()
ok(ra["assigned"] == 1 and any(x["student_id"] == FOR and "xorijiy" in x["why"] for x in ra["skipped"]), "Xorijiy fuqaro tayinlanmadi — «ozod»")
ok(any(r_["id"] == FOR for r_ in xod.get(P + "/students", params={"state": "ozod", "limit": 200}).json()["items"]), "Ro'yxatda «Ozod (xorijiy fuqaro)»")
ok(xod.post(f"{P}/students/{S5}/citizenship", json={"citizenship": "KZ"}).status_code == 403, "Xodim (masofaviy) fuqarolikni o'zgartira olmaydi — 403")
ok(regx.post(f"{P}/students/{S5}/citizenship", json={"citizenship": "KZ"}).json().get("foreign") is True, "Registrator xodimi fuqarolikni belgiladi (KZ)")
pend = xod.get(P + "/students", params={"state": "ozod", "q": q("SELECT hemis_id FROM students WHERE id=?", (S5,))[0]["hemis_id"]}).json()["items"]
ok(len(pend) == 1, "Fuqarolik o'zgarishi bilan talaba «ozod»ga o'tdi")
regx.post(f"{P}/students/{S5}/citizenship", json={"citizenship": "UZ"})

# shaxsni tekshirish
print("== 2b. Shaxsni tekshirish: hujjat raqami saqlanmaydi")
CK = f"{P}/sessions/{SID}/check"
ok(xod.post(CK, json={"student_id": S1, "method": "pasport", "code": "AB1234567", "photo_ok": True}).status_code == 400, "To'liq pasport raqami — 400")
ok(xod.post(CK, json={"student_id": S1, "method": "id_karta", "code": "12345678", "photo_ok": True}).status_code == 400, "4 tadan ortiq raqam — 400")
r = xod.post(CK, json={"student_id": S1, "method": "pasport", "code": "7351", "doc_ok": True, "photo_ok": True, "note": "pasport AA7654321 ko'rildi"})
ok(r.status_code == 200 and r.json()["status"] == "keldi" and r.json()["match_src"] == "xodim", "Ma'lumotnoma yo'q: xodim ko'zdan tasdiqladi + rasm mos — «keldi»")
ok(regx.post(P + "/idref", json={"student_id": S2, "last4": "123456"}).status_code == 400 and regx.post(P + "/idref", json={"student_id": S2, "last4": "4821"}).status_code == 200,
   "HEMIS ma'lumotnomasi: faqat 4 raqam (xesh sifatida)")
r = xod.post(CK, json={"student_id": S2, "method": "id_karta", "code": "0000", "photo_ok": True})
ok(r.json()["status"] == "shubhali" and not r.json()["doc_match"] and r.json()["match_src"] == "tizim", "Raqam ma'lumotnomaga mos emas — «shaxsi tasdiqlanmagan»")
r = xod.post(CK, json={"student_id": S2, "method": "id_karta", "code": "4821", "photo_ok": True})
ok(r.json()["status"] == "keldi" and r.json()["doc_match"], "To'g'ri oxirgi 4 raqam + rasm — «keldi» (tizim solishtirdi)")
h3 = q("SELECT hemis_id FROM students WHERE id=?", (S3,))[0]["hemis_id"]
r = xod.post(CK, json={"student_id": S3, "method": "hemis", "code": h3, "photo_ok": False})
ok(r.json()["status"] == "shubhali" and r.json()["doc_match"] and not r.json()["photo_ok"], "HEMIS ID mos, rasm mos emas — «shubhali»")
dump = "\n".join(json.dumps(x, ensure_ascii=False) for tb in ("yy_assign", "yy_idref", "yy_protocols", "yy_sessions") for x in q(f"SELECT * FROM {tb}"))
ok(not any(s in dump for s in ("7351", "4821", "AA7654321", "7654321", "1234567")), "Bazada kiritilgan hujjat raqamlari (va izohdagi raqam) yo'q")
ok(q("SELECT last4_hash FROM yy_idref WHERE student_id=?", (S2,))[0]["last4_hash"] not in ("4821", ""), "yy_idref — faqat xesh")
cols = {r_["name"] for r_ in q("PRAGMA table_info(yy_assign)")}
ok(not cols & {"doc_no", "passport", "document", "code", "last4"}, f"yy_assign ustunlari: hujjat raqami uchun ustun yo'q ({sorted(cols)[:6]}…)")
ok(xod.post(f"{P}/sessions/{SID2}/check", json={"student_id": S4, "method": "pasport", "code": "1111", "doc_ok": True, "photo_ok": True}).json()["status"] == "keldi",
   "Yakuniy nazorat sessiyasida ham shaxs tekshiriladi")

# qaydnoma
print("== 2c. Qaydnoma")
ok(xod.post(f"{P}/sessions/{SID}/sign").status_code == 403 and regx.post(f"{P}/sessions/{SID}/sign").status_code == 403, "Xodimlar qaydnomani imzolay olmaydi — 403")
ok(head.get(f"{P}/sessions/{SID}/protocol.docx").status_code == 404, "Imzolanmagan — qaydnoma yo'q (404)")
sg = head.post(f"{P}/sessions/{SID}/sign")
ok(sg.status_code == 200 and sg.json()["reg_no"].startswith("YQ-") and sg.json()["stats"] == {"tayinlangan": 3, "keldi": 2, "shubhali": 1, "kelmadi": 0},
   f"Bo'lim boshlig'i imzoladi: {sg.json().get('reg_no')} · {sg.json().get('stats')}")
REGNO, CODE = sg.json()["reg_no"], sg.json()["verify_code"]
ok(head.post(f"{P}/sessions/{SID}/sign").status_code == 409 and xod.post(CK, json={"student_id": S1, "method": "hemis", "code": "1", "photo_ok": True}).status_code == 409,
   "Imzodan keyin qayta imzo va davomat o'zgarishi — 409")
dx = head.get(f"{P}/sessions/{SID}/protocol.docx")
xml = zipfile.ZipFile(io.BytesIO(dx.content)).read("word/document.xml").decode() if dx.status_code == 200 else ""
n1 = q("SELECT full_name FROM students WHERE id=?", (S1,))[0]["full_name"]
ok(dx.status_code == 200 and REGNO in xml and n1 in xml and "QAYDNOMA" in xml and "yurist" in xml and "7351" not in xml, "Qaydnoma .docx: ro'yxat raqami, talabalar, me'yoriy izoh; hujjat raqami yo'q")
pf = head.get(f"{P}/sessions/{SID}/protocol.pdf")
ptxt = ""
if pf.status_code == 200:
    from pypdf import PdfReader
    ptxt = "\n".join(pg.extract_text() or "" for pg in PdfReader(io.BytesIO(pf.content)).pages)
ok(pf.status_code == 200 and pf.content[:5] == b"%PDF-" and REGNO in ptxt and "QAYDNOMA" in ptxt and CODE in ptxt, "Qaydnoma .pdf: o'qiladi, ro'yxat raqami va tekshirish kodi bor")
pr = q("SELECT * FROM yy_protocols WHERE session_id=?", (SID,))[0]
ok(pr["signed_by"] == HEAD and len(pr["sha256"]) == 64 and head.get(f"{P}/sessions/{SID}").json()["protocol"]["sha256"] == pr["sha256"], "Imzo: kim, qachon, mazmun SHA-256")
vf = httpx.get(B + f"/verify/{CODE}")
ok(vf.status_code == 200 and REGNO in vf.text and "Haqiqiy" in vf.text, "Hujjatlar reyestri: /verify/KOD — haqiqiy")
ok(rek.get(f"{P}/sessions/{SID}/protocol.pdf").status_code == 200 and kaf.get(f"{P}/sessions/{SID}/protocol.pdf").status_code == 403, "Rektor qaydnomani ko'radi, kafedra — 403")

# =============================================================================================
print("== 3. Muddat bayrog'i: talaba kabineti va Nazorat markazi")
c1 = ST(S1)
k1 = c1.get("/api/talaba/yuzma").json()
ok(k1["applies"] and k1["state"] == "otgan" and k1["banner"] is None, "Ro'yxatdan o'tgan talaba: «Ro'yxatdan o'tgan», banner yo'q")
c3 = ST(S3)
k3 = c3.get("/api/talaba/yuzma").json()
ok(k3["state"] == "muddati_otgan" and k3["banner"]["level"] == "bad", "Shaxsi tasdiqlanmagan talaba — muddat o'tgan (qizil banner)")
cx = ST(SX)
kx = cx.get("/api/talaba/yuzma").json()
ok(kx["state"] == "muddati_otgan" and kx["banner"]["level"] == "bad" and "Masofaviy ta'lim bo'limiga" in kx["banner"]["text"], "Tayinlanmagan, muddat o'tgan — qizil banner, bo'limga murojaat")
r = xod.post(P + "/sessions", json={"kind": "royxat", "title": "Test: keyingi", "date": (dt.date.fromisoformat(TODAY) + dt.timedelta(days=3)).isoformat(),
                                     "start_time": "10:00", "end_time": "12:00", "room": "Test xona 3", "capacity": 5})
SID3 = r.json()["session"]["id"]
xod.post(f"{P}/sessions/{SID3}/assign", json={"student_ids": [SX]})
kx = cx.get("/api/talaba/yuzma").json()
ok(kx["next"] and kx["next"]["room"] == "Test xona 3" and "Test xona 3" in kx["banner"]["text"], "Banner keyingi sessiyani ko'rsatadi (sana, xona)")
ok(xod.post(P + "/deadline", json={"date": TODAY}).status_code == 403, "Muddatni xodim o'zgartira olmaydi — 403")
old_dl = M["deadline"]
fut = (dt.date.fromisoformat(TODAY) + dt.timedelta(days=10)).isoformat()
ok(head.post(P + "/deadline", json={"date": fut}).status_code == 200, "Bo'lim boshlig'i muddatni surdi")
kx2 = cx.get("/api/talaba/yuzma").json()
ok(kx2["state"] == "tayinlangan" and kx2["banner"]["level"] == "warn", "Muddat oldidan: sariq banner («tayinlangan»)")
head.post(P + "/deadline", json={"date": old_dl})
D = rek.get("/api/nazorat").json()
I = {x["key"]: x for a in D["areas"] for x in a["items"] + a["lower"]}
cn = head.get(P + "/overview").json()["counts"]
ok("yy:royxat" in I and I["yy:royxat"]["title"].startswith(f"{cn['muddati_otgan']} ta") and I["yy:royxat"]["stage"] == 2,
   f"Nazorat markazi (talabalar): «{I.get('yy:royxat', {}).get('title')}» — rektorgacha yetgan")
ok(not re.search(r"\b\d{12,}\b", I["yy:royxat"]["title"] + I["yy:royxat"]["why"]), "Nazorat istisnosida ism / HEMIS ID yo'q")

# =============================================================================================
print("== 4. Ruxsatlar: talaba, tyutor, rektor, jurnal")
ok(n1 not in json.dumps(k3, ensure_ascii=False) and n1 not in json.dumps(kx, ensure_ascii=False), "Talaba javobida boshqa talaba ismi yo'q")
ok(len(k1["items"]) == 1 and k1["items"][0]["title"] == "Test: bugungi sessiya", "Talaba faqat o'z tadbirlarini ko'radi")
ok(c1.get(P + "/overview").status_code == 401 and httpx.get(B + "/api/talaba/yuzma").status_code == 401, "Talaba cookie'si xodim API'sida — 401; kirishsiz — 401")
ok(head.get("/api/talaba/yuzma").status_code == 401, "Xodim cookie'si talaba API'sida — 401")
nonmas = q("SELECT id FROM students WHERE study_form='kunduzgi' AND status='faol' AND id NOT IN (SELECT student_id FROM student_auth) ORDER BY id DESC LIMIT 1")[0]["id"]
ok(ST(nonmas).get("/api/talaba/yuzma").json() == {"applies": False}, "Kunduzgi talaba — kartasi yo'q")
g1 = q("SELECT group_id FROM students WHERE id=?", (S1,))[0]["group_id"]
prev_tut = q("SELECT user_id FROM tutor_groups WHERE group_id=?", (g1,))
w("INSERT OR REPLACE INTO tutor_groups(group_id,user_id) VALUES(?,?)", (g1, TUTU))
try:
    tut = S(TUTU)
    ts_ = tut.get(P + "/students", params={"limit": 200}).json()
    gname = q("SELECT name FROM groups_ WHERE id=?", (g1,))[0]["name"]
    ok(ts_["total"] > 0 and all(x["grp"] == gname for x in ts_["items"]), f"Tyutor: faqat o'z guruhi talabalari ({ts_['total']} ta, {gname})")
    sd = tut.get(f"{P}/sessions/{SID}").json()
    ok(sd["roster"] and all(x["grp"] == gname for x in sd["roster"]), "Tyutor: sessiya ro'yxatida faqat o'z talabalari")
    oth = q("""SELECT s.id FROM yy_sessions s WHERE EXISTS (SELECT 1 FROM yy_assign a0 WHERE a0.session_id=s.id) AND NOT EXISTS (SELECT 1 FROM yy_assign a JOIN students st ON st.id=a.student_id
               WHERE a.session_id=s.id AND st.group_id=?) LIMIT 1""", (g1,))[0]["id"]
    ok(tut.get(f"{P}/sessions/{oth}").status_code == 403, "Tyutor: o'z talabasi yo'q sessiya — 403")
    ok(tut.post(f"{P}/sessions/{SID3}/assign", json={"student_ids": [S4]}).status_code == 403 and tut.post(P + "/sessions", json={"kind": "royxat", "date": TODAY, "room": "Test xona 9", "capacity": 1}).status_code == 403,
       "Tyutor: tayinlash va sessiya yaratish — 403")
    ok(tut.get(P + "/journal/" + str(S1)).status_code == 403 and tut.get(P + "/limits").status_code == 403, "Tyutor: kirish jurnali va chegaralar — 403")
finally:
    if prev_tut: w("UPDATE tutor_groups SET user_id=? WHERE group_id=?", (prev_tut[0]["user_id"], g1))
    else: w("DELETE FROM tutor_groups WHERE group_id=?", (g1,))
rd = rek.get(f"{P}/sessions/{SID}").json()
ok(rd["names"] is False and rd["roster"] == [] and rd["session"]["came"] == 2, "Rektor: sessiya — faqat jamlangan sonlar, ismlar yo'q")
ok(rek.get(P + "/students").status_code == 403 and rek.get(P + "/journal/" + str(S1)).status_code == 403 and rek.get(P + "/limits").status_code == 200,
   "Rektor: talabalar ro'yxati va jurnal — 403, huquqiy chegaralar — 200")
ok(reg.get(P + "/journal/" + str(S1)).status_code == 403 and xod.get(P + "/journal/" + str(S1)).status_code == 200, "Kirish jurnali — faqat Masofaviy ta'lim bo'limi")

# =============================================================================================
print("== 5. Kirish jurnali va umumiy akkaunt alomati")
SA = S4
ca = ST(SA, ip="10.31.7.21", ua="Mozilla/5.0 (Windows NT 10.0) Chrome/129")
cb = ST(SA, ip="10.88.4.9", ua="Mozilla/5.0 (iPhone; CPU iPhone OS 17) Safari/604")
fl = q("SELECT kind, status FROM yy_flags WHERE student_id=?", (SA,))
ok({"parallel", "almashish"} <= {f["kind"] for f in fl} and all(f["status"] == "yangi" for f in fl), f"Ikki tarmoq + ikki qurilmadan kirish → alomatlar: {sorted({f['kind'] for f in fl})}")
ok(ca.get("/api/talaba/yuzma").status_code == 200 and cb.get("/api/talaba/yuzma").status_code == 200, "Avtomatik bloklanmaydi — ikkala sessiya ishlaydi")
acc = json.dumps(q("SELECT * FROM yy_access WHERE student_id=?", (SA,)))
ok("10.31.7" not in acc and "10.88.4" not in acc and "iPhone OS 17" not in acc and q("SELECT COUNT(*) n FROM yy_access WHERE student_id=?", (SA,))[0]["n"] >= 2,
   "Jurnalda xom IP va User-Agent yo'q (faqat xesh va qurilma nomi)")
jr = xod.get(P + f"/journal/{SA}").json()
ok(jr["totals"]["networks"] >= 2 and jr["totals"]["devices"] >= 2 and any(l["parallel"] for l in jr["logins"]) and jr["flags"], "Jurnal: tarmoqlar T1/T2, qurilmalar, «bir vaqtda» belgisi, alomatlar")
FL = xod.get(P + "/flags").json()
mine = [f for f in FL["items"] if f["student_id"] == SA]
ok(mine and FL["counts"]["yangi"] >= len(mine), f"Bo'lim ro'yxatida ko'rib chiqilmagan alomatlar ({FL['counts']['yangi']})")
fid = mine[0]["id"]
ok(xod.post(f"{P}/flags/{fid}/review", json={"decision": "asossiz", "note": ""}).status_code == 400, "Izohsiz ko'rib chiqish — 400")
ok(xod.post(f"{P}/flags/{fid}/review", json={"decision": "asossiz", "note": "Talaba bilan gaplashildi: telefon va noutbuk"}).json()["status"] == "asossiz"
   and xod.post(f"{P}/flags/{fid}/review", json={"decision": "asossiz", "note": "takror"}).status_code == 409, "Ko'rib chiqildi (asossiz); qayta — 409")
ok(reg.get(P + "/flags").status_code == 403, "Registrator ofisi alomatlarni ko'rmaydi — 403")
ok("yy:umumiy" in {x["key"] for a in rek.get("/api/nazorat").json()["areas"] for x in a["items"] + a["lower"]}, "Nazorat markazida «umumiy akkaunt alomati» istisnosi")

# =============================================================================================
print("== 6. Jarayon ichida: huquqiy chegaralar detektorlari (bazaning nusxasi)")
tmp = Path(tempfile.mkdtemp(prefix="yy-test-"))
src = sqlite3.connect(DBP, timeout=30); dst = sqlite3.connect(tmp / "jarvis.db"); src.backup(dst); src.close(); dst.close()
os.environ.update(ISFT_CORE_DATA_DIR=str(tmp), ISFT_CORE_DB=str(tmp / "jarvis.db"), ISFT_CORE_FILES_DIR=str(tmp / "portal_files"),
                  ISFT_CORE_STAFFABS_DIR=str(tmp / "staffabs_files"), ISFT_CORE_SECRETS_DIR=str(tmp / "secrets"))
os.environ.pop("ANTHROPIC_API_KEY", None); os.environ.pop("TELEGRAM_BOT_TOKEN", None)
for m in [k for k in sys.modules if k == "app" or k.startswith("app.")]: del sys.modules[m]
import contextlib   # noqa: E402
with contextlib.redirect_stdout(io.StringIO()):
    from app import main as MAIN   # noqa: E402
from app import nazorat as NZ, yuzma_yuz as YY   # noqa: E402
con = MAIN.con
R = NZ.rules(con)
ok((R["dl_quota_bachelor"], R["dl_quota_master"], R["dl_per_teacher"], R["dl_quota_warn_pct"]) == (300, 30, 50, 90), "Standart qoidalar: 300 / 30 / 50, ogohlantirish 90 %")
fac, dep = con.execute("SELECT faculty_id, id FROM departments ORDER BY id LIMIT 1").fetchone()
def prog(name, level, n_dist, n_full=1):
    gd = con.execute("INSERT INTO groups_(department_id,faculty_id,name,course,direction,level,form) VALUES(?,?,?,?,?,?,'masofaviy')", (dep, fac, name[:6] + "-M", 1, name, level)).lastrowid
    gf = con.execute("INSERT INTO groups_(department_id,faculty_id,name,course,direction,level,form) VALUES(?,?,?,?,?,?,'kunduzgi')", (dep, fac, name[:6] + "-K", 1, name, level)).lastrowid
    for i in range(n_dist):
        con.execute("INSERT INTO students(hemis_id,full_name,group_id,faculty_id,status,level,study_form) VALUES(?,?,?,?,'faol',?,'masofaviy')", (f"T{gd}-{i}", f"Test {i}", gd, fac, level))
    for i in range(n_full):
        con.execute("INSERT INTO students(hemis_id,full_name,group_id,faculty_id,status,level,study_form) VALUES(?,?,?,?,'faol',?,'kunduzgi')", (f"K{gf}-{i}", f"Test K{i}", gf, fac, level))
    con.commit(); return gd
def yy_items():
    return {x["key"]: x for x in NZ._yy_limit_cands(con, NOW, NZ.rules(con), NZ.Org(con))}
NOW = dt.datetime.combine(dt.date.fromisoformat(TODAY), dt.time(10))
for n in (299, 300, 301): prog(f"Kvota test {n}", "bakalavr", n)
for n in (30, 31): prog(f"Magistr test {n}", "magistr", n)
gnf = prog("Kunduzgisiz test", "bakalavr", 5, n_full=0)
prog("Test pedagogikasi", "bakalavr", 5)
it = yy_items()
k = lambda n, lv="bakalavr": it.get(f"yy:kvota:{lv}:Kvota test {n}" if lv == "bakalavr" else f"yy:kvota:magistr:Magistr test {n}")
ok(k(299) and "99.7 %" in k(299)["title"] and NZ.stage_of(k(299)["since"], NOW, NZ.rules(con)) == 0, "299 / 300 — sariq (egasida, rektor ko'rmaydi)")
ok(k(300) and "to'lgan" in k(300)["title"] and NZ.stage_of(k(300)["since"], NOW, NZ.rules(con)) == 2, "300 / 300 — qizil (chegara to'lgan, darhol rektorda)")
ok(k(301) and "OSHGAN" in k(301)["title"] and NZ.stage_of(k(301)["since"], NOW, NZ.rules(con)) == 2, "301 / 300 — qizil (chegaradan oshgan)")
ok(k(30, "m") and "to'lgan" in k(30, "m")["title"] and k(31, "m") and "OSHGAN" in k(31, "m")["title"], "Magistratura: 30 — to'lgan, 31 — oshgan (chegara 30)")
ok("yy:kunduzgi:bakalavr:Kunduzgisiz test" in it and not any(x.startswith("yy:kunduzgi:") and "Kvota" in x for x in it), "Kunduzgi shakli yo'q masofaviy yo'nalish — qizil")
ok("yy:ped" in it and "Test pedagogikasi" in json.dumps(it["yy:ped"]["state"], ensure_ascii=False), "Pedagogik yo'nalishda masofaviy talaba — PF-73 istisnosi")
ped_n0 = len(it["yy:ped"]["state"])
con.execute("INSERT OR REPLACE INTO yy_programs(direction,level,pedagogik,src) VALUES('Test pedagogikasi','bakalavr',0,'qo''lda')"); con.commit()
ok(len(yy_items()["yy:ped"]["state"]) == ped_n0 - 1, "Qo'lda «pedagogik emas» deb belgilansa — istisnodan chiqadi")
# o'qituvchiga 50 / 51
con.execute("DELETE FROM teacher_groups"); con.commit()
ok("yy:oqit" not in yy_items() and "yy:oqit90" not in yy_items(), "Biriktirish yo'q — o'qituvchi istisnosi yo'q")
t50 = con.execute("INSERT INTO teachers(full_name,department_id,faculty_id) VALUES('Ellik O.',?,?)", (dep, fac)).lastrowid
t51 = con.execute("INSERT INTO teachers(full_name,department_id,faculty_id) VALUES('Ellikbir O.',?,?)", (dep, fac)).lastrowid
g50 = prog("Oqit test A", "bakalavr", 50); g51 = prog("Oqit test B", "bakalavr", 51)
con.execute("INSERT INTO teacher_groups(teacher_id,group_id,subject) VALUES(?,?,'Fan')", (t50, g50))
con.execute("INSERT INTO teacher_groups(teacher_id,group_id,subject) VALUES(?,?,'Fan')", (t51, g51)); con.commit()
rep = YY.limits_report(con)
tl = {t_["name"]: t_ for t_ in rep["teachers"]}
it = yy_items()
ok(tl["Ellik O."]["n"] == 50 and tl["Ellik O."]["level_flag"] == "amber" and tl["Ellikbir O."]["n"] == 51 and tl["Ellikbir O."]["level_flag"] == "red",
   "O'qituvchi: 50 — chegarada (sariq), 51 — oshgan (qizil)")
ok(it["yy:oqit"]["title"].startswith("1 ta") and it["yy:oqit90"]["title"].startswith("1 ta"), "Nazorat: «1 ta o'qituvchiga 50 tadan ortiq» va «1 ta chegaraga yaqin»")
con.execute("INSERT OR REPLACE INTO nz_rules(k,v) VALUES('dl_quota_bachelor',302)"); con.commit()
it = yy_items()
ok(it[f"yy:kvota:bakalavr:Kvota test 301"]["title"].endswith("chegaraning 99.7 %") and "yy:kvota:bakalavr:Kvota test 300" in it, "Rektor chegarani 302 ga o'zgartirsa — 301 sariqqa tushadi")
scan = {x["key"] for x in NZ.scan(con, NOW, write=False)}
ok({"yy:ped", "yy:royxat", "yy:oqit"} <= scan, "Umumiy skan (Nazorat markazi) yangi detektorlarni o'z ichiga oladi")
shutil.rmtree(tmp, ignore_errors=True)

# =============================================================================================
print("== 7. Brauzer")
node = shutil.which("node")
if node:
    ok(all(subprocess.run([node, "--check", str(ROOT / "static" / f)], capture_output=True).returncode == 0 for f in ("yuzma.js", "yuzma_talaba.js")), "node --check: yuzma.js, yuzma_talaba.js")
if node and os.getenv("PW") and os.getenv("CHROME"):
    hm = q("SELECT hemis_id FROM students WHERE id=?", (SX,))[0]["hemis_id"]
    env = dict(os.environ, ISFT_TEST_URL=B, YY_UID=str(XOD), YY_PW=PW, YY_SESS=str(SID2), YY_HEMIS=hm, YY_SPW=NEWPW,
               YY_OUT=os.getenv("YY_OUT") or str(Path(os.getenv("ISFT_CORE_DATA_DIR", "/tmp")) / "yuzma_shots"))
    rr = subprocess.run([node, str(ROOT / "tools" / "yuzma_check.js")], cwd=ROOT, env=env, capture_output=True, text=True, timeout=300)
    print(rr.stdout[-2500:], rr.stderr[-800:])
    ok(rr.returncode == 0, "Brauzer: xodim ekrani (keng va telefon) va talaba kartasi (telefon)")
else:
    print("  · brauzer tekshiruvi o'tkazildi (PW/CHROME berilmagan)")

print(f"\n{'XATO: ' + str(len(fails)) if fails else 'Hammasi o‘tdi'}")
sys.exit(1 if fails else 0)
