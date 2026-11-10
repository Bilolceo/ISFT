import os
"""Talaba kabineti (/talaba, app/student_portal.py): kirish, majburiy parol almashtirish, ma'lumotlar bazaga mosligi, IDOR,
fayl yuklash, apellyatsiya, ma'lumotnoma so'rovi va xodimlar tomonidan ko'rib chiqish.

Ishga tushirish (server ishlab tursin):  .venv/bin/python tests/test_talaba.py
Muhit: ISFT_TEST_URL (standart http://127.0.0.1:8000), ISFT_CORE_DB / ISFT_CORE_DATA_DIR — server bilan bir xil baza.
Qayta ishga tushirish mumkin: test o'zi yaratgan murojaatlar, apellyatsiyalar, sessiyalar va talaba parollarini oxirida o'chiradi,
dars qoldirish yozuvini asl holiga qaytaradi, bergan ma'lumotnomalarni «bekor» qiladi.
Eslatma: kirish urinishlari cheklovi server xotirasida — bitta IP dan 10 daqiqada 20 ta xato; testning bir o'tishi 7 ta xato qiladi.
"""
import base64, json, sqlite3, sys
from pathlib import Path
import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from app import db as DB, academic_rules as AR, student_ops as OPS, registrar as RG   # noqa: E402

B = os.environ.get("ISFT_TEST_URL", "http://127.0.0.1:8000")
DEMO = os.environ.get("ISFT_CORE_STUDENT_DEMO_PASSWORD", "Talaba2026")
NEWPW = "Sinov2026parol"
N = [0]
con = DB.connect()
q = lambda sql, a=(): [dict(r) for r in con.execute(sql, a).fetchall()]
one = lambda sql, a=(): (q(sql, a) or [None])[0]
TEST_IDS, APPEALS, ABS, DOCS = set(), [], {}, []

def cleanup():
    ids = ",".join(str(i) for i in TEST_IDS) or "0"
    for r in q(f"SELECT file_stored FROM student_requests WHERE student_id IN ({ids}) AND file_stored IS NOT NULL"):
        p = Path(os.environ.get("ISFT_CORE_TALABA_DIR") or (DB.DATA_DIR / "talaba_files")) / r["file_stored"]
        if p.is_file(): p.unlink()
    con.execute(f"DELETE FROM student_requests WHERE student_id IN ({ids})")
    con.execute(f"DELETE FROM student_sessions WHERE student_id IN ({ids})")
    con.execute(f"DELETE FROM student_auth WHERE student_id IN ({ids})")
    for aid in APPEALS: con.execute("DELETE FROM grade_appeals WHERE id=?", (aid,))
    for aid, (reason, doc, note) in ABS.items(): con.execute("UPDATE absences SET reason=?, doc_status=?, note=? WHERE id=?", (reason, doc, note, aid))
    for reg in DOCS: con.execute("UPDATE documents SET status='bekor' WHERE reg_no=?", (reg,))
    con.commit()

def ok(cond, msg):
    N[0] += 1
    print(("✓ " if cond else "✗ XATO: ") + msg)
    if not cond:
        cleanup(); sys.exit(1)

def staff(uid):
    c = httpx.Client(base_url=B, timeout=120)
    r = c.post("/api/login", json={"user_id": uid, "password": "Isft2026"}); assert r.status_code == 200, (uid, r.text)
    return c

def student_login(hemis, pw=DEMO):
    c = httpx.Client(base_url=B, timeout=120)
    return c, c.post("/api/talaba/login", json={"hemis_id": hemis, "password": pw})

def student(s):
    """Birinchi kirish (sinov paroli) + majburiy almashtirish → tayyor mijoz."""
    TEST_IDS.add(s["id"])
    c, r = student_login(s["hemis_id"])
    assert r.status_code == 200, r.text
    r = c.post("/api/talaba/password", json={"current": DEMO, "new": NEWPW}); assert r.status_code == 200, r.text
    return c

# ---------------------------------------------------------------- talabalarni tanlash (hali kabinetga kirmaganlar)
FRESH = "s.id NOT IN (SELECT student_id FROM student_auth)"
cur_ab = f"EXISTS (SELECT 1 FROM absences a WHERE a.student_id=s.id AND a.semester={AR.CURRENT_SEMESTER} AND a.reason='sababsiz' AND a.cleared_by IS NULL)"
A = one(f"""SELECT s.* FROM students s WHERE s.status='faol' AND s.study_form='kunduzgi' AND {FRESH} AND {cur_ab}
            AND s.id IN (SELECT student_id FROM grade_attempts WHERE counted=1 AND semester<{AR.CURRENT_SEMESTER} AND at>=date('now','-2 day'))
            AND s.id NOT IN (SELECT student_id FROM grade_appeals WHERE status!='qaror') ORDER BY s.id LIMIT 1""")
if not A:   # apellyatsiya muddati ichidagi natija topilmasa — oddiy talaba (apellyatsiya bo'limi shunga moslashadi)
    A = one(f"SELECT s.* FROM students s WHERE s.status='faol' AND s.study_form='kunduzgi' AND {FRESH} AND {cur_ab} ORDER BY s.id LIMIT 1")
Bs = one(f"SELECT s.* FROM students s WHERE s.status='faol' AND s.group_id=? AND s.id!=? AND {FRESH} AND {cur_ab} ORDER BY s.id LIMIT 1", (A["group_id"], A["id"])) \
    or one(f"SELECT s.* FROM students s WHERE s.status='faol' AND s.study_form='kunduzgi' AND s.id!=? AND {FRESH} AND {cur_ab} ORDER BY s.id DESC LIMIT 1", (A["id"],))
S = one(f"SELECT s.* FROM students s WHERE s.status='faol' AND s.study_form='sirtqi' AND {FRESH} ORDER BY s.id LIMIT 1")
T = one(f"SELECT s.* FROM students s WHERE s.status='akademik ta''til' AND {FRESH} ORDER BY s.id LIMIT 1")
X = one(f"SELECT s.* FROM students s WHERE s.status NOT IN ('faol','akademik ta''til') AND {FRESH} ORDER BY s.id LIMIT 1")
RL = one(f"SELECT s.* FROM students s WHERE s.status='faol' AND {FRESH} AND s.id NOT IN (?,?,?) ORDER BY random() LIMIT 1", (A["id"], Bs["id"], S["id"]))
RET = one(f"SELECT s.* FROM students s WHERE s.status='faol' AND {FRESH} AND s.id IN (SELECT student_id FROM retakes) AND s.id NOT IN (?,?) LIMIT 1", (A["id"], Bs["id"]))
for x in (A, Bs, S, T, X, RL): TEST_IDS.add(x["id"])
if RET: TEST_IDS.add(RET["id"])
print(f"Talabalar: A #{A['id']}, B #{Bs['id']}, sirtqi #{S['id']}, ta'til #{T['id']}, {X['status']} #{X['id']}")

try:
    # =========================================================== 1. Kirish
    print("— Kirish va sessiyalar —")
    c, r = student_login("9999999999999")
    ok(r.status_code == 401 and "HEMIS ID yoki parol noto'g'ri" in r.json()["detail"], "Noma'lum HEMIS ID — 401, umumiy xabar (ID mavjudligi oshkor qilinmaydi)")
    c, r = student_login(A["hemis_id"], "Notogri123")
    ok(r.status_code == 401 and "HEMIS ID yoki parol noto'g'ri" in r.json()["detail"], "Noto'g'ri parol — 401, xuddi shu xabar")
    ok(not one("SELECT 1 x FROM student_auth WHERE student_id=?", (A["id"],)), "Noto'g'ri urinishda xesh yaratilmaydi")
    ca, r = student_login(A["hemis_id"])
    ok(r.status_code == 200 and r.json()["must_change"] is True, "Sinov paroli bilan birinchi kirish: must_change=true")
    au = one("SELECT * FROM student_auth WHERE student_id=?", (A["id"],))
    ok(au and au["pw_hash"].startswith("pbkdf2$") and DEMO not in au["pw_hash"], "Xesh birinchi kirishda yaratildi (PBKDF2, ochiq parol saqlanmaydi)")
    ok(one("SELECT 1 x FROM student_sessions WHERE student_id=?", (A["id"],)) and "tsid" in ca.cookies and "sid" not in ca.cookies, "Alohida cookie (tsid) va student_sessions")
    tok = ca.cookies["tsid"]
    ok(not one("SELECT 1 x FROM student_sessions WHERE token=?", (tok,)), "Bazada token emas, uning xeshi saqlanadi")
    r = ca.get("/api/talaba/grades")
    ok(r.status_code == 403 and r.json()["detail"]["must_change"] is True, "Parol almashtirilmaguncha ma'lumot berilmaydi (403 must_change)")
    ok(ca.get("/api/talaba/me").json()["must_change"] is True, "/me — must_change bayrog'i")
    for bad, why in (("qisqa1", "8 belgidan qisqa"), (DEMO, "sinov paroli"), (A["hemis_id"] + "a", "HEMIS ID bor"), ("faqatharflar", "raqamsiz")):
        r = ca.post("/api/talaba/password", json={"current": DEMO, "new": bad})
        ok(r.status_code == 400, f"Zaif parol rad etildi: {why}")
    r = ca.post("/api/talaba/password", json={"current": "xato-parol1", "new": NEWPW})
    ok(r.status_code == 400 and r.json()["detail"]["field"] == "current", "Joriy parol noto'g'ri — 400")
    r = ca.post("/api/talaba/password", json={"current": DEMO, "new": NEWPW})
    ok(r.status_code == 200, "Parol almashtirildi")
    ok(ca.get("/api/talaba/grades").status_code == 200, "Almashtirilgandan keyin ma'lumot ochiladi (joriy sessiya saqlanadi)")
    ok(not one("SELECT must_change m FROM student_auth WHERE student_id=?", (A["id"],))["m"], "must_change=0")
    _, r = student_login(A["hemis_id"], DEMO)
    ok(r.status_code == 401, "Sinov paroli endi ishlamaydi")
    c2, r = student_login(A["hemis_id"], NEWPW)
    ok(r.status_code == 200 and r.json()["must_change"] is False, "Yangi parol bilan kirish")
    sess = ca.get("/api/talaba/profile").json()["sessions"]
    ok(len(sess) == 2 and sum(s["current"] for s in sess) == 1, "Profil: 2 ta faol sessiya, joriysi belgilangan")
    r = ca.post("/api/talaba/password", json={"current": NEWPW, "new": NEWPW + "x"})
    ok(r.status_code == 200 and r.json()["closed"] == 1 and c2.get("/api/talaba/home").status_code == 401, "Parol almashtirilsa boshqa sessiyalar yopiladi")
    r = ca.post("/api/talaba/password", json={"current": NEWPW + "x", "new": NEWPW}); assert r.status_code == 200
    c3, _ = student_login(A["hemis_id"], NEWPW)
    old = c3.cookies["tsid"]
    c3.post("/api/talaba/logout")
    c4 = httpx.Client(base_url=B, timeout=60, cookies={"tsid": old})
    ok(c4.get("/api/talaba/home").status_code == 401, "Chiqishdan keyin eski token (nusxa) ishlamaydi")

    # talaba ↔ xodim sessiyalari ajratilgan
    reg = staff(17)
    ok(httpx.get(B + "/api/talaba/home", cookies={"tsid": reg.cookies["sid"]}).status_code == 401, "Xodim tokeni talaba API'sida ishlamaydi (tsid sifatida)")
    ok(reg.get("/api/talaba/home").status_code == 401, "Xodim cookie'si bilan talaba API'si — 401")
    ok(httpx.get(B + "/api/me", cookies={"sid": ca.cookies["tsid"]}).status_code == 401, "Talaba tokeni xodim API'sida ishlamaydi (/api/me)")
    ok(httpx.get(B + "/api/dashboard", cookies={"sid": ca.cookies["tsid"], "tsid": ca.cookies["tsid"]}).status_code == 401, "Talaba tokeni /api/dashboard — 401")
    ok(ca.get("/api/ops/summary").status_code == 401 and ca.get("/api/talaba/staff/requests").status_code == 401, "Talaba sessiyasi xodim endpointlarida (ops, murojaatlar ro'yxati) — 401")

    # maqom
    ct, r = student_login(T["hemis_id"])
    ok(r.status_code == 200, "Akademik ta'tildagi talaba kira oladi")
    ct.post("/api/talaba/password", json={"current": DEMO, "new": NEWPW})
    ok(ct.get("/api/talaba/home").status_code == 200, "Akademik ta'til: bosh sahifa ochiladi")
    r = ct.post("/api/talaba/requests/certificate", json={"lang": "uz", "purpose": "bankka"})
    ok(r.status_code == 403, "Akademik ta'til: ma'lumotnoma so'rovi — 403 (o'qiyotganini tasdiqlab bo'lmaydi)")
    _, r = student_login(X["hemis_id"])
    ok(r.status_code == 403 and X["status"] in r.json()["detail"], f"«{X['status']}» maqomidagi talaba kira olmaydi (403)")
    ok(not one("SELECT 1 x FROM student_auth WHERE student_id=?", (X["id"],)), "Ruxsatsiz maqom — xesh ham yaratilmaydi")
    # urinishlar cheklovi
    codes = [student_login(RL["hemis_id"], f"xato{i}xato")[1].status_code for i in range(5)]
    _, r = student_login(RL["hemis_id"], DEMO)
    ok(codes[0] == 401 and set(codes) <= {401, 429} and r.status_code == 429, "5 ta xato urinishdan keyin to'g'ri parol ham bloklanadi (429)")
    aud = q("SELECT * FROM audit_log WHERE channel='talaba' AND detail LIKE ? ORDER BY id", (f"talaba #{A['id']} %",))
    ok(any(a["action"] == "talaba kabineti: kirish" and a["allowed"] == 0 for a in aud) and any(a["action"] == "talaba kabineti: parol almashtirildi" for a in aud)
       and all(a["user_id"] is None for a in aud), "Audit: kanal «talaba», user_id NULL, talaba — detail'da (xato va muvaffaqiyatli kirish, parol)")

    # =========================================================== 2. Ma'lumotlar bazaga mos
    print("— Ma'lumotlar (bazaga mosligi) —")
    sid = A["id"]
    f = OPS.student_facts(con, sid)
    h = ca.get("/api/talaba/home").json()
    ok(h["attendance"]["unexcused"] == f["unexcused"] and h["attendance"]["excused"] == f["excused"], f"Bosh sahifa: sababsiz {f['unexcused']} / sababli {f['excused']} soat — Talabalar markazi bilan bir xil")
    ok(h["debts"] == len(f["fails"]) and h["gpa"] == f["gpa5"], "Bosh sahifa: akademik qarz va kumulyativ GPA")
    L = h["attendance"]["limits"]
    ok((L["call"], L["reprimand"]) == (30, 48), "Kunduzgi chegaralar: 30 / 48 soat")
    if f["unexcused"] >= 30: ok(any(w["key"] == "davomat" and w["level"] in ("warn", "bad") for w in h["warnings"]), "30+ soat — ogohlantirish chiqadi")
    g = ca.get("/api/talaba/grades").json()
    dbcur = {r["subject"]: r["oraliq"] for r in q("SELECT subject, oraliq FROM grades WHERE student_id=? AND semester=?", (sid, AR.CURRENT_SEMESTER))}
    ok({x["subject"]: x["oraliq"] for x in g["current"]["subjects"]} == dbcur, f"Joriy semestr oraliq ballari ({len(dbcur)} fan)")
    ok(all(x["admitted"] == (x["oraliq"] is not None and x["oraliq"] >= 12) for x in g["current"]["subjects"]), "Oraliq 12/30 chegarasi")
    done = q("SELECT subject, semester, score, credits, attempts FROM grades WHERE student_id=? AND semester<? AND score IS NOT NULL", (sid, AR.CURRENT_SEMESTER))
    api_done = {(x["subject"], x["semester"]): x for s_ in g["semesters"] for x in s_["subjects"]}
    ok(len(api_done) == len(done) and all(api_done[(d["subject"], d["semester"])]["score"] == d["score"] for d in done), f"Yakunlangan semestrlar: {len(done)} ta baho")
    ok(all(x["letter"] == AR.letter(x["score"]) for x in api_done.values()), "Harf baho — akademik qoidalar shkalasi")
    staff(18).post("/api/reyting/recompute")   # oldingi testlar baholarni o'zgartirgan bo'lishi mumkin — kesh yangilansin
    rc = {r["semester"]: r["gpa"] for r in q("SELECT semester, gpa FROM rating_cache WHERE student_id=?", (sid,))}
    ok(all(abs((s_["gpa"] or 0) - rc[s_["semester"]]) < 0.006 for s_ in g["semesters"] if s_["semester"] in rc), "Semestr GPA = reyting keshidagi GPA")
    ok(g["cum_gpa"] == OPS.cum_gpa(con, sid), "Kumulyativ GPA = Talabalar markazi formulasi")
    earned = sum((d["credits"] or AR.CREDIT_DEFAULT) for d in done if d["score"] >= AR.PASS)
    ok(g["credits"]["earned"] == earned and g["credits"]["required"] == 240, f"Kreditlar: {earned} / 240")
    hist = q("SELECT subject, semester FROM grade_attempts WHERE student_id=?", (sid,))
    ok(all(len(api_done[(x["subject"], x["semester"])]["history"]) >= 1 for x in hist if (x["subject"], x["semester"]) in api_done), "Urinishlar tarixi baho yonida")
    rt = ca.get("/api/talaba/rating").json()
    row = one("SELECT * FROM rating_cache WHERE student_id=? ORDER BY semester DESC LIMIT 1", (sid,))
    if row:
        it = rt["items"][0]
        ok(all(it[k] == row[k] for k in ("r_group", "n_group", "r_course", "n_course", "r_faculty", "n_faculty")), f"Reyting: guruhda {row['r_group']}/{row['n_group']}, kursda, fakultetda — keshdan")
    ab = ca.get("/api/talaba/attendance").json()
    ok(ab["unexcused"] == f["unexcused"] and len(ab["items"]) == one("SELECT COUNT(*) n FROM absences WHERE student_id=?", (sid,))["n"], "Davomat: yozuvlar soni va sababsiz soat")
    ok(sum(a["hours"] for a in ab["items"] if a["current"] and a["unexcused"]) == f["unexcused"], "Davomat: sababsiz deb belgilangan yozuvlar yig'indisi = sababsiz soat")
    k = ca.get("/api/talaba/contract").json()
    if A["payment_type"] == "kontrakt" and A["contract_amount"]:
        ok(k["amount"] == A["contract_amount"] and k["paid"] == A["paid_amount"] and len(k["plan"]) == 4, "Kontrakt: summa, to'langan, 4 bosqichli jadval")
        ok([p["due"] for p in k["plan"]] == ["2026-10-01", "2026-11-12", "2027-02-15", "2027-05-01"] and [p["pct"] for p in k["plan"]] == [25, 50, 75, 100], "To'lov muddatlari 25/50/75/100%")
        nx = next((p for p in k["plan"] if A["paid_amount"] < A["contract_amount"] * p["pct"] // 100), None)
        ok((k["next"] or {}).get("due") == (nx or {}).get("due"), "Keyingi to'lov sanasi to'g'ri")
    else:
        ok(k["kind"] != "kontrakt", "Grant talaba: kontrakt jadvali yo'q")
    ex = ca.get("/api/talaba/exams").json()
    pc = RG.permit_check(con, sid)
    ok(ex["permit"]["eligible"] == pc["eligible"] and ex["permit"]["reasons"] == pc["reasons"], "Imtihonga ruxsatnoma: Registrator tekshiruvi bilan bir xil (sabablar bilan)")
    nslots = one("""SELECT COUNT(*) n FROM exam_slots x JOIN exam_sessions e ON e.id=x.session_id WHERE x.group_id=? AND e.status IN ('e''lon qilingan','yakunlangan')""", (A["group_id"],))["n"]
    ok(len(ex["slots"]) == nslots, f"Sessiya jadvali: guruhning e'lon qilingan {nslots} ta imtihoni (loyiha sessiyalar ko'rinmaydi)")
    if RET:
        cr_ = student(RET)
        r = cr_.get("/api/talaba/retakes").json()["items"]
        ok(len(r) == one("SELECT COUNT(*) n FROM retakes WHERE student_id=?", (RET["id"],))["n"] and all(("hours_left" in x) for x in r), "Otrabotka: varaqalar soni va muddat hisobi")
    p = ca.get("/api/talaba/profile").json()
    ok(p["phone"] is None or ("***" in p["phone"] and (A["phone"] or "") not in json.dumps(p)), "Profil: telefon niqoblangan")

    # =========================================================== 3. IDOR va boshqa talabalar ma'lumoti
    print("— IDOR —")
    cb = student(Bs)
    pdf = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"
    a_abs = [a for a in ab["items"] if a["can_upload"]]
    ok(bool(a_abs), "A talabada hujjat yuklanadigan dars qoldirish bor")
    aid = a_abs[0]["id"]
    ABS[aid] = tuple(one("SELECT reason, doc_status, note FROM absences WHERE id=?", (aid,)).values())
    r = ca.post("/api/talaba/requests/excuse", json={"absence_id": aid, "reason": "kasallik", "note": "test", "name": "spravka.pdf", "data": base64.b64encode(pdf).decode()})
    ok(r.status_code == 200, "A: sababli hujjat yuklandi (PDF)")
    rid_a = r.json()["id"]
    r = ca.post("/api/talaba/requests/certificate", json={"lang": "uz", "purpose": "bankka"}); ok(r.status_code == 200, "A: ma'lumotnoma so'rovi"); cid_a = r.json()["id"]
    for path in (f"/api/talaba/requests/{rid_a}/file", f"/api/talaba/requests/{cid_a}/document", f"/api/talaba/requests/{rid_a}/document"):
        ok(cb.get(path).status_code == 404, f"B → A murojaati {path.split('/')[-1]}: 404")
    ok(ca.get(f"/api/talaba/requests/{rid_a}/file").content == pdf, "A o'z faylini oladi")
    r = cb.post("/api/talaba/requests/excuse", json={"absence_id": aid, "reason": "kasallik", "name": "x.pdf", "data": base64.b64encode(pdf).decode()})
    ok(r.status_code == 404, "B A ning dars qoldirishiga hujjat biriktira olmaydi (404)")
    a_sess = ca.get("/api/talaba/profile").json()["sessions"][0]["id"]
    ok(cb.post(f"/api/talaba/sessions/{a_sess}/revoke").status_code == 404 and ca.get("/api/talaba/home").status_code == 200, "B A ning sessiyasini yopa olmaydi")
    for path in ("home", "grades", "rating", "attendance", "retakes", "exams", "appeals", "contract", "requests", "profile", "me"):
        r1 = cb.get(f"/api/talaba/{path}?student_id={sid}&sid={sid}&id={sid}")
        body = r1.text
        ok(r1.status_code == 200 and A["full_name"] not in body and A["hemis_id"] not in body and f'"id":{rid_a},' not in body.replace(" ", ""),
           f"/{path}: B so'rov parametri bilan ham faqat o'z ma'lumotini oladi")
    mates = [r["full_name"] for r in q("SELECT full_name FROM students WHERE group_id=? AND id!=?", (A["group_id"], sid))]
    allbody = "".join(ca.get(f"/api/talaba/{p}").text for p in ("home", "grades", "rating", "attendance", "exams", "appeals", "requests"))
    ok(not any(m in allbody for m in mates), f"Guruhdoshlarning ({len(mates)} nafar) ismi hech bir javobda yo'q (reyting — faqat raqam)")
    ok(not any(k_.startswith("full_name") for k_ in json.dumps(ca.get("/api/talaba/rating").json()).split('"')), "Reyting javobida ism maydoni yo'q")

    # =========================================================== 4. Fayl yuklash
    print("— Fayl yuklash —")
    def up(name, data, **kw):
        return cb.post("/api/talaba/requests/excuse", json={"reason": "kasallik", "start": "2026-10-01", "end": "2026-10-01", "name": name,
                                                           "data": base64.b64encode(data).decode(), **kw})
    ok(up("virus.pdf", b"MZ\x90\x00" + b"\0" * 200).status_code == 415, "Nomi o'zgartirilgan exe (.pdf) — 415")
    ok(up("rasm.jpg", pdf).status_code == 415, "PDF mazmunli .jpg — 415 (kengaytmaga ishonilmaydi)")
    ok(up("rasm.png", b"\x89PNG\r\n\x1a\n" + b"\0" * 50).status_code == 400, "PNG — 400 (faqat PDF/JPG)")
    ok(up("x.exe", b"MZ").status_code == 400, ".exe — 400")
    ok(cb.post("/api/talaba/requests/excuse", json={"reason": "kasallik", "start": "2026-10-01", "name": "a.pdf", "data": "@@@buzuq"}).status_code == 400, "Buzilgan base64 — 400")
    big = cb.post("/api/talaba/requests/excuse", json={"reason": "kasallik", "start": "2026-10-01", "name": "a.pdf", "data": base64.b64encode(b"%PDF-" + b"0" * (10 * 1024 * 1024 + 10)).decode()})
    ok(big.status_code in (413, 422), "10 MB dan katta — rad etildi")
    ok(up("a.pdf", pdf, reason="sababsiz").status_code == 400, "Sabab «sababsiz» — rad etildi")
    ok(up("a.pdf", pdf, start="2030-01-01", end="2030-01-02").status_code == 400, "Kelajakdagi sana — rad etildi")
    jpg = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01" + b"\0" * 100 + b"\xff\xd9"
    r = up("ma'lumotnoma (1).JPG", jpg)
    ok(r.status_code == 200, "Haqiqiy JPG — qabul qilindi"); rid_b = r.json()["id"]
    rr = one("SELECT * FROM student_requests WHERE id=?", (rid_b,))
    ok(rr["file_sha256"] and rr["file_mime"] == "image/jpeg" and rr["unit"] == "talabalar" and rr["file_stored"].endswith(".jpg") and "/" not in rr["file_stored"],
       "Fayl tasodifiy nom bilan saqlandi, sha256 va MIME yozildi, navbat — Registrator ofisi")
    rej = q("SELECT * FROM audit_log WHERE channel='talaba' AND action LIKE '%fayl rad etildi%' AND detail LIKE ?", (f"talaba #{Bs['id']} %",))
    ok(len(rej) >= 3 and all(x["allowed"] == 0 for x in rej), "Rad etilgan fayllar audit jurnalida")

    # =========================================================== 5. Apellyatsiya
    print("— Apellyatsiya —")
    apl = ca.get("/api/talaba/appeals").json()
    if apl["options"]:
        o = apl["options"][0]
        ok(o["deadline"] >= __import__("datetime").date.today().isoformat(), f"Apellyatsiya varianti muddat ichida: {o['subject']} ({o['published_at']} → {o['deadline']})")
        r = ca.post("/api/talaba/appeals", json={"subject": o["subject"], "semester": o["semester"], "reason": "qisqa"})
        ok(r.status_code in (200, 400), "Apellyatsiya so'rovi")
        if r.status_code == 400: r = ca.post("/api/talaba/appeals", json={"subject": o["subject"], "semester": o["semester"], "reason": "Yakuniy nazorat 3-savoli noto'g'ri baholangan"})
        ok(r.status_code == 200, "Apellyatsiya berildi (flows.create_appeal)"); APPEALS.append(r.json()["id"])
        ga = one("SELECT * FROM grade_appeals WHERE id=?", (APPEALS[-1],))
        ok(ga["student_id"] == sid and ga["channel"] == "portal" and ga["status"] == "yangi", "grade_appeals: talaba, kanal «portal», holat «yangi»")
        ok(ca.post("/api/talaba/appeals", json={"subject": o["subject"], "semester": o["semester"], "reason": "Yana bir marta tekshiring"}).status_code == 400, "Takroriy apellyatsiya — 400")
        lst = ca.get("/api/talaba/appeals").json()
        ok(any(x["id"] == APPEALS[-1] and x["status_name"] for x in lst["items"]) and not any(x["subject"] == o["subject"] and x["semester"] == o["semester"] for x in lst["options"]),
           "Holat kuzatiladi; fan variantlardan chiqdi")
        ok(cb.get("/api/talaba/appeals").json()["items"] == [] or all(x["id"] != APPEALS[-1] for x in cb.get("/api/talaba/appeals").json()["items"]), "B A ning apellyatsiyasini ko'rmaydi")
        r = cb.post("/api/talaba/appeals", json={"subject": o["subject"], "semester": o["semester"], "reason": "Begona fan bo'yicha urinish"})
        ok(r.status_code == 400, "B A ning fani bo'yicha apellyatsiya bera olmaydi")
    else:
        print("  (A da apellyatsiya muddati ichidagi natija yo'q — faqat rad etish tekshiriladi)")
    old_ = one("SELECT subject, semester FROM grades WHERE student_id=? AND semester=-1 AND score IS NOT NULL LIMIT 1", (sid,))
    if old_:
        r = ca.post("/api/talaba/appeals", json={"subject": old_["subject"], "semester": -1, "reason": "Eski semestr natijasi bo'yicha"})
        ok(r.status_code == 400 and "muddat" in r.json()["detail"], "Muddati o'tgan natija — 400")

    # =========================================================== 6. Ma'lumotnoma va xodimlar ko'rib chiqishi
    print("— Ma'lumotnoma va «Talaba murojaatlari» —")
    sirtqi, xodim, kotib = staff(27), staff(43), staff(20)
    ok(kotib.get("/api/talaba/staff/requests").status_code == 403, "Boshqa bo'lim (kotib) — 403")
    L17 = reg.get("/api/talaba/staff/requests").json()
    ok({rid_a, cid_a, rid_b} <= {x["id"] for x in L17["items"]}, "Registrator ofisi navbatida A va B murojaatlari")
    ok(not {rid_a, cid_a} & {x["id"] for x in sirtqi.get("/api/talaba/staff/requests?status=all").json()["items"]}, "Sirtqi bo'lim kunduzgi talaba murojaatini ko'rmaydi")
    ok(sirtqi.get(f"/api/talaba/staff/requests/{rid_a}/file").status_code == 403, "Sirtqi bo'lim kunduzgi talaba faylini ocholmaydi (403)")
    ok(reg.get(f"/api/talaba/staff/requests/{rid_a}/file").content == pdf, "Registrator ofisi yuklangan faylni ko'radi")
    ok(ca.get(f"/api/talaba/requests/{cid_a}/document").status_code == 404, "Berilmagan ma'lumotnomani yuklab bo'lmaydi")
    ok(reg.post(f"/api/talaba/staff/requests/{cid_a}/decide", json={"action": "qabul"}).status_code == 400, "Ma'lumotnoma uchun noto'g'ri amal — 400")
    r = reg.post(f"/api/talaba/staff/requests/{cid_a}/decide", json={"action": "berish"})
    ok(r.status_code == 200 and r.json()["doc_reg"].startswith("MT-"), f"Registrator ofisi ma'lumotnoma berdi: {r.json().get('doc_reg')}"); DOCS.append(r.json()["doc_reg"])
    d = one("SELECT * FROM documents WHERE reg_no=?", (DOCS[-1],))
    ok(d["kind"] == "study_cert" and d["holder"] == A["full_name"], "Hujjatlar reyestrida: study_cert, egasi — A")
    r = ca.get(f"/api/talaba/requests/{cid_a}/document")
    ok(r.status_code == 200 and r.content[:2] == b"PK", "A tayyor ma'lumotnomani yuklab oldi (DOCX)")
    ok(cb.get(f"/api/talaba/requests/{cid_a}/document").status_code == 404, "B A ning ma'lumotnomasini yuklab ololmaydi")
    ok(reg.post(f"/api/talaba/staff/requests/{cid_a}/decide", json={"action": "rad", "note": "takror"}).status_code == 409, "Ko'rib chiqilgan murojaat qayta o'zgarmaydi (409)")
    ok(reg.post(f"/api/talaba/staff/requests/{rid_b}/decide", json={"action": "rad", "note": ""}).status_code == 400, "Rad etishda sabab majburiy")
    r = reg.post(f"/api/talaba/staff/requests/{rid_b}/decide", json={"action": "rad", "note": "Hujjat o'qilmaydi"})
    ok(r.status_code == 200 and cb.get("/api/talaba/requests").json()["items"][0]["review_note"] == "Hujjat o'qilmaydi", "Rad etildi — talaba izohni ko'radi")
    before = OPS.student_facts(con, sid)["unexcused"]
    hrs = one("SELECT hours FROM absences WHERE id=?", (aid,))["hours"]
    r = xodim.post(f"/api/talaba/staff/requests/{rid_a}/decide", json={"action": "qabul", "note": "asl nusxa ko'rildi"})
    ok(r.status_code == 200, "Registrator ofisi xodimi (#43) sababli hujjatni qabul qildi")
    ab2 = one("SELECT reason, doc_status FROM absences WHERE id=?", (aid,))
    ok(ab2["reason"] == "kasallik" and ab2["doc_status"] == "tasdiqlangan", "Dars qoldirish: sabab «kasallik», hujjat tasdiqlangan")
    after = ca.get("/api/talaba/attendance").json()["unexcused"]
    ok(after == before - hrs, f"Sababsiz soatlar kamaydi: {before} → {after}")
    ok(next(a for a in ca.get("/api/talaba/attendance").json()["items"] if a["id"] == aid)["request"]["status"] == "qabul", "Talaba davomat sahifasida holatni ko'radi")
    # sirtqi talaba → Sirtqi bo'lim
    cs = student(S)
    r = cs.post("/api/talaba/requests/certificate", json={"lang": "en", "purpose": "elchixonaga (viza uchun)"}); ok(r.status_code == 200 and r.json()["office"] == "Sirtqi bo'lim", "Sirtqi talaba so'rovi → Sirtqi bo'lim")
    cid_s = r.json()["id"]
    ok(cid_s not in {x["id"] for x in reg.get("/api/talaba/staff/requests?status=all").json()["items"]}, "Registrator ofisi navbatida sirtqi so'rov yo'q")
    ok(reg.post(f"/api/talaba/staff/requests/{cid_s}/decide", json={"action": "berish"}).status_code == 403, "Registrator ofisi sirtqi so'rovga qaror qila olmaydi (403)")
    r = sirtqi.post(f"/api/talaba/staff/requests/{cid_s}/decide", json={"action": "berish"})
    ok(r.status_code == 200, f"Sirtqi bo'lim ingliz tilidagi ma'lumotnomani berdi: {r.json().get('doc_reg')}"); DOCS.append(r.json()["doc_reg"])
    ok(cs.get(f"/api/talaba/requests/{cid_s}/document").status_code == 200, "Sirtqi talaba hujjatni yuklab oldi")
    ok(ca.post("/api/talaba/requests/certificate", json={"lang": "uz", "purpose": "bankka"}).status_code == 200 and
       ca.post("/api/talaba/requests/certificate", json={"lang": "uz", "purpose": "bankka"}).status_code == 409, "Bir xil ochiq so'rov takrorlanmaydi (409)")
    aud = q("SELECT * FROM audit_log WHERE resource='talaba' AND action LIKE 'talaba murojaati:%' AND user_id IN (17,43,27)")
    ok(len(aud) >= 4, "Xodimlar qarorlari audit jurnalida")
    ok(httpx.get(B + "/talaba").status_code == 200 and httpx.get(B + "/talaba/xodim").status_code == 200, "Sahifalar: /talaba va /talaba/xodim")
finally:
    cleanup()
print(f"\nHammasi o'tdi: {N[0]} ta tekshiruv ✓")
