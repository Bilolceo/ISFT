"""Registrator ofisi — talabaning markaziy hamrohi (M. Baratov talablari): uchidan-uchigacha testlar.

Ishga tushirish (server http://127.0.0.1:8000 da ishlab tursin):  .venv/bin/python tests/test_registrar.py
Qayta ishga tushirish mumkin: test o'zi yaratgan otrabotkalar, holat/topshiriqlar va kontrakt uzaytirishini oxirida o'chiradi,
o'zgartirgan baholarni asl holiga qaytaradi, chiqargan hujjatlarini «bekor» holatiga o'tkazadi (ro'yxat raqamlari ketma-ketligi buzilmasin).
Tekshiradi:
  1. Otrabotka varaqasini Registrator ofisi / tyutor / (sirtqi talabaga) Sirtqi bo'lim beradi — Imtihon bo'limi faqat ko'radi.
  2. Sirtqi bo'lim — sirtqi talabalar uchun registrator: varaqa, tasdiqlash, topshiriq, hujjatlar faqat sirtqi talabaga; kontrakt — o'qish.
  3. Otrabotka muddati: yashil/sariq/qizil; muddat o'tsa — tyutor + call-markaz topshirig'i (idempotent, jurnalda).
  4. Skan: ro'yxat raqami bo'yicha moslashtirish, imzo bor/yo'q, ball (OCR bo'lsa); imzosiz skan belgilanadi; tasdiqlash → baho o'tadi.
  5. Imtihonga kirish ruxsatnomasi: faktlardan tekshiruv, rad etish sabablari, guruh bo'yicha, QR tekshiruvida kim/qachon.
  6. Shaxsiy grafik (QR: bergan bo'lim, xodim, vaqt). 7. Zinapoya: 30 → qo'ng'iroq + xat, 48 dan oshsa → hayfsan, ish stoli.
  8. Akademik ta'til: ~3 oy oldin call-markaz; qaytish — buyruq loyihasi topshirig'i (buyruqlar moduli bilan bog'lanadi).
"""
import base64, datetime as dt, json, re, sqlite3, sys
from pathlib import Path
import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from app import db as DB, student_ops as OPS, registrar as RG, registrar_scan as RS   # noqa: E402

B = "http://127.0.0.1:8000"
N = [0]
def ok(cond, msg):
    N[0] += 1
    print(("✓ " if cond else "✗ XATO: ") + msg)
    if not cond:
        cleanup(); sys.exit(1)

def S(uid):
    c = httpx.Client(base_url=B, timeout=120)
    r = c.post("/api/login", json={"user_id": uid, "password": "Isft2026"}); assert r.status_code == 200, (uid, r.text)
    return c

con = DB.connect()
OPS.bind(con, None)
q = lambda sql, a=(): con.execute(sql, a).fetchall()
CREATED_RT, CREATED_DOCS, DEFER, GRADES = [], [], [], {}

def cleanup():
    """Test yaratgan yozuvlarni olib tashlaydi (hujjatlar — «bekor»)."""
    for rid in CREATED_RT:
        r = q("SELECT student_id, subject FROM retakes WHERE id=?", (rid,))
        cids = [x[0] for x in q("SELECT id FROM ops_cases WHERE key LIKE ?", (f"%:otrabotka:{rid}",))]
        for cid in cids:
            con.execute("DELETE FROM ops_tasks WHERE case_id=?", (cid,)); con.execute("DELETE FROM ops_log WHERE case_id=?", (cid,))
            con.execute("DELETE FROM ops_cases WHERE id=?", (cid,))
        con.execute("DELETE FROM retakes WHERE id=?", (rid,))
    for (sid, subj), sc in GRADES.items():
        con.execute("UPDATE grades SET score=? WHERE student_id=? AND subject=? AND semester=1", (sc, sid, subj))
    for did in DEFER: con.execute("DELETE FROM contract_deferments WHERE id=?", (did,))
    for reg in CREATED_DOCS: con.execute("UPDATE documents SET status='bekor' WHERE reg_no=? AND status!='bekor'", (reg,))
    con.commit()
    CREATED_RT.clear(); GRADES.clear(); DEFER.clear()
    try: OPS.evaluate(con)
    except Exception: pass

def docs_from(r):
    regs = r.get("regs") or ([r["reg_no"]] if r.get("reg_no") else [])
    if r.get("count", 0) > len(regs) and regs:   # paket: ketma-ket raqamlar
        pre, n0 = regs[0].rsplit("/", 1); regs = [f"{pre}/{int(n0) + i:04d}" for i in range(r["count"])]
    CREATED_DOCS.extend(regs); return regs

def retake_for(client, form="kunduzgi", faculty=None):
    """Ochiq otrabotkasi yo'q, o'tish balidan past fan — yangi varaqa (client nomidan)."""
    busy = {(a, b) for a, b in q("SELECT student_id, subject FROM retakes")}
    fw = f" AND s.faculty_id={int(faculty)}" if faculty else ""
    for sid, subj, sc in q(f"""SELECT g.student_id, g.subject, g.score FROM grades g JOIN students s ON s.id=g.student_id
                               WHERE g.semester=1 AND g.score<40 AND s.status='faol' AND s.study_form=?{fw} ORDER BY g.student_id DESC LIMIT 400""", (form,)):
        if (sid, subj) in busy: continue
        r = client.post("/api/ops/retakes", json={"student_id": sid, "subject": subj})
        if r.status_code == 200:
            j = r.json(); CREATED_RT.append(j["id"]); GRADES.setdefault((sid, subj), sc); docs_from(j)
            return j["id"], sid, subj, sc
    raise RuntimeError("mos talaba topilmadi")

def data_url(raw, ext): return f"data:{'application/pdf' if ext == '.pdf' else 'image/png'};base64," + base64.b64encode(raw).decode()

reg, sir, imt, ty2, cc, pro = S(17), S(27), S(8), S(24), S(23), S(3)
try:
    # ---------------------------------------------------------------- 1. egalik
    print("— 1. Otrabotka varaqasini kim beradi —")
    kd = q("SELECT g.student_id, g.subject FROM grades g JOIN students s ON s.id=g.student_id WHERE g.semester=1 AND g.score<40 AND s.status='faol' LIMIT 1")[0]
    ok(imt.post("/api/ops/retakes", json={"student_id": kd[0], "subject": kd[1]}).status_code == 403, "Imtihon bo'limi otrabotka varaqasini bera olmaydi (403)")
    ok(imt.get("/api/ops/retakes").status_code == 200, "Imtihon bo'limi otrabotkalarni ko'radi (faqat o'qish)")
    ok({r["rule"] for r in imt.get("/api/ops/summary").json()["by_rule"]} <= {"akademik", "otrabotka"}, "Imtihon bo'limi: o'zlashtirish va otrabotka holatlari")
    ok("imtihon" not in OPS.RETAKE_ISSUERS and "sirtqi" in OPS.RETAKE_ISSUERS, "RETAKE_ISSUERS: Registrator, tyutor, Sirtqi bo'lim")
    from app import documents as D
    ok("imtihon" not in D.CAT["retake_sheet"]["roles"] and "sirtqi" in D.CAT["retake_sheet"]["roles"], "Varaqa shabloni: Imtihon bo'limida yo'q, Sirtqi bo'limda bor")

    # ---------------------------------------------------------------- 2. sirtqi bo'lim
    print("— 2. Sirtqi bo'lim — sirtqi talabalar registratori —")
    rid_s, sid_s, subj_s, _ = retake_for(sir, "sirtqi")
    ok(q("SELECT study_form FROM students WHERE id=?", (sid_s,))[0][0] == "sirtqi", f"Sirtqi bo'lim sirtqi talabaga varaqa berdi (#{rid_s})")
    kd2 = q("SELECT g.student_id, g.subject FROM grades g JOIN students s ON s.id=g.student_id WHERE g.semester=1 AND g.score<40 AND s.status='faol' AND s.study_form='kunduzgi' LIMIT 1")[0]
    ok(sir.post("/api/ops/retakes", json={"student_id": kd2[0], "subject": kd2[1]}).status_code == 403, "Sirtqi bo'lim kunduzgi talabaga varaqa bera olmaydi (403)")
    ok(sir.get(f"/api/registrar/permit/{kd2[0]}").status_code == 403, "Sirtqi bo'lim kunduzgi talabaning ruxsatnomasini tekshira olmaydi")
    r = sir.post("/api/docs/issue", json={"key": "study_cert", "params": {"target": f"s:{kd2[0]}"}})
    ok(r.status_code == 403, "Hujjatlar markazi: sirtqi bo'lim kunduzgi talabaga ma'lumotnoma chiqara olmaydi (403)")
    r = sir.post("/api/docs/issue", json={"key": "study_cert", "params": {"target": f"s:{sid_s}"}}); ok(r.status_code == 200, "Sirtqi talabaga o'qish joyidan ma'lumotnoma")
    docs_from(r.json())
    from docx import Document
    txt = "\n".join(p.text for p in Document(str(ROOT / "data" / "docs" / r.json()["file"])).paragraphs) + "\n".join(c.text for t in Document(str(ROOT / "data" / "docs" / r.json()["file"])).tables for row in t.rows for c in row.cells)
    ok("sirtqi ta'lim shaklida" in txt and "kunduzgi ta'lim" not in txt, "Ma'lumotnoma: ta'lim shakli to'g'ri (sirtqi)")
    ok("Sirtqi bo'lim boshlig'i" in txt and "dekan" not in txt.lower(), "Imzo: Sirtqi bo'lim boshlig'i (dekan yo'q)")
    lk = sir.get("/api/docs/lookup/student?q=a").json()
    ok(lk and {x[0] for x in q(f"SELECT DISTINCT study_form FROM students WHERE id IN ({','.join(str(x['id']) for x in lk)})")} == {"sirtqi"}, "Sirtqi bo'lim qidiruvi: faqat sirtqi talabalar")
    gl = sir.get("/api/docs/lookup/group").json()
    ok(gl and {x[0] for x in q(f"SELECT DISTINCT s.study_form FROM students s WHERE s.group_id IN ({','.join(str(x['id']) for x in gl[:50])})")} == {"sirtqi"}, "Sirtqi bo'lim guruhlari: faqat sirtqi")
    ok("kontrakt" in {r["rule"] for r in sir.get("/api/ops/summary").json()["by_rule"]}, "Sirtqi bo'lim: o'z talabalarining kontrakt holatlari (o'qish — sessiyaga qo'yish uchun)")
    ok("contracts" not in sir.get("/api/me").json()["allow"], "Sirtqi bo'lim: institut kontrakt jamlanmasi yopiq")
    kt = sir.get("/api/ops/tasks?rule=kontrakt").json()
    ok(all(not t["can_act"] for t in kt), "Sirtqi bo'lim kontrakt topshirig'ini bajarmaydi (faqat ko'radi)")
    xt = [t for t in sir.get("/api/ops/tasks?kind=xat&rule=akademik").json() if t["can_act"] and t["assignee_role"] == "sirtqi"]
    ok(xt, f"Sirtqi talabalar ogohlantirish xatlari Sirtqi bo'lim navbatida ({len(xt)})")
    r = sir.post(f"/api/ops/tasks/{xt[0]['id']}/document", json={}); ok(r.status_code == 200 and r.json()["reg_no"].startswith("OX-"), f"Sirtqi bo'lim ogohlantirish xatini chiqardi: {r.json().get('reg_no')}")
    CREATED_DOCS.append(r.json()["reg_no"])
    con.execute("UPDATE ops_tasks SET status='yangi', outcome=NULL, doc_reg=NULL, done_at=NULL, done_by=NULL, note=NULL WHERE id=?", (xt[0]["id"],)); con.commit()
    rx = [t for t in reg.get("/api/ops/tasks?kind=xat&rule=akademik").json()]
    ok(rx and all(t["can_act"] for t in rx), "Registrator ofisi (nazoratchi) baribir har qanday topshiriqni bajara oladi")

    # ---------------------------------------------------------------- 3. muddat ranglari va avtomatik topshiriq
    print("— 3. Otrabotka muddati: yashil → sariq → qizil, muddat o'tsa — topshiriq —")
    ok([OPS.retake_tone(h) for h in (70, 48.5, 47, 24.5, 23, -5)] == ["green", "green", "amber", "amber", "red", "red"], "Rang chegaralari: >48 soat yashil, ≤48 sariq, ≤24 va o'tgan — qizil")
    rid, sid, subj, sc0 = retake_for(reg, "kunduzgi", 2)
    rows = {r["id"]: r for r in reg.get("/api/ops/retakes").json()}
    ok(rows[rid]["tone"] == "green" and 71 < rows[rid]["hours_left"] <= 72, "Yangi varaqa: 3 kun, yashil")
    con.execute("UPDATE retakes SET due_at=? WHERE id=?", ((dt.datetime.now() - dt.timedelta(hours=5)).isoformat(timespec="seconds"), rid)); con.commit()
    OPS.evaluate(con)
    case = q("SELECT id, level FROM ops_cases WHERE key=? AND status='ochiq'", (f"{sid}:otrabotka:{rid}",))
    ok(case and case[0][1] == 2, "Muddat o'tdi → otrabotka holati (kritik)")
    roles = sorted(x[0] for x in q("SELECT assignee_role FROM ops_tasks WHERE case_id=? AND status='yangi'", (case[0][0],)))
    ok(roles == ["call_center", "tyutor"], f"Avtomatik topshiriqlar: tyutor ogohlantiradi + call-markaz qo'ng'iroq qiladi {roles}")
    sc = json.loads(q("SELECT script FROM ops_tasks WHERE case_id=? AND assignee_role='call_center'", (case[0][0],))[0][0])
    ok("MUDDAT O'TDI" in sc["say"][0], "Call-markaz skripti: muddat o'tgani aytiladi")
    OPS.evaluate(con)
    ok(q("SELECT COUNT(*) FROM ops_tasks WHERE case_id=?", (case[0][0],))[0][0] == 2, "Qayta tekshiruv dublikat yaratmadi (idempotent)")
    ok(q("SELECT COUNT(*) FROM ops_log WHERE case_id=? AND action='topshiriq yaratildi'", (case[0][0],))[0][0] == 2, "Jurnalda qayd etilgan")
    ok(reg.get("/api/ops/retakes").json() and next(r for r in reg.get("/api/ops/retakes").json() if r["id"] == rid)["overdue"], "Ro'yxatda: muddati o'tgan (qizil)")
    card = reg.get(f"/api/ops/student/{sid}").json()
    ok(next(r for r in card["retakes"] if r["id"] == rid)["tone"] == "red" and card["can_permit"], "Talaba kartasida ham muddat rangi; registrator amallari ochiq")

    # ---------------------------------------------------------------- 4. skan
    print("— 4. Skanni o'qish va tasdiqlash —")
    r0 = DB.one(con, "SELECT * FROM retakes WHERE id=?", (rid,))
    raw, ext, drawn = RS.make_sheet(RG.demo_info(con, r0), "signed", "pdf", seed=11)
    up = reg.post(f"/api/ops/retakes/{rid}/upload", json={"data_url": data_url(raw, ext)}); ok(up.status_code == 200, "Imzolangan skan (PDF) yuklandi")
    m = up.json()["scan"]
    ok(m["reg_no"] == r0["reg_no"] and m["match"] is True, f"Ro'yxat raqami o'qildi va mos keldi: {m['reg_no']}")
    ok(m["signed"] is True and m["score_filled"] is True, "O'qituvchi imzosi va ball katagi aniqlandi")
    if RS.tesseract_bin(): ok(m["score"] == drawn["score"], f"Ball OCR bilan o'qildi: {m['score']} (varaqada {drawn['score']})")
    else: ok(m["score"] is None and any("qo'lda" in w for w in m["warnings"]), "OCR yo'q — ball qo'lda kiritiladi (ochiq aytiladi)")
    ok(reg.get(f"/api/registrar/retakes/{rid}/preview").headers["content-type"] == "image/png", "Skan ko'rinishi (PDF ichidagi rasm) — PNG")
    ok(next(r for r in reg.get("/api/ops/retakes").json() if r["id"] == rid)["scan"]["signed"] is True, "Ro'yxatda o'qish natijasi va HEMIS bahosi bor")
    ok(ty2.post(f"/api/ops/retakes/{rid}/approve", json={"score": drawn["score"]}).status_code == 403, "Tyutor bahoni tasdiqlay olmaydi")
    ok(reg.post(f"/api/ops/retakes/{rid}/approve", json={"score": drawn["score"]}).status_code == 200, "Registrator «Tasdiqlash» — baho o'tdi")
    ok(q("SELECT score FROM grades WHERE student_id=? AND subject=? AND semester=1", (sid, subj))[0][0] == drawn["score"], "Baho jadvali yangilandi")
    ok(q("SELECT status FROM ops_cases WHERE key=?", (f"{sid}:otrabotka:{rid}",))[0][0] == "yopildi", "Otrabotka holati yopildi")
    # imzosiz → belgilanadi
    rid2, sid2, subj2, _ = retake_for(reg, "kunduzgi", 2)
    r2 = DB.one(con, "SELECT * FROM retakes WHERE id=?", (rid2,))
    raw, ext, drawn2 = RS.make_sheet(RG.demo_info(con, r2), "unsigned", "png", seed=12)
    sm = reg.post("/api/registrar/scan", json={"data_url": data_url(raw, ext)})   # avtomatik moslashtirish (OCR bo'lsa)
    if RS.tesseract_bin():
        ok(sm.status_code == 200 and sm.json()["retake_id"] == rid2, "Skan otrabotkani tanlamasdan yuklandi — raqam bo'yicha topildi")
    else:
        ok(sm.status_code == 422, "OCR yo'q, PNG — raqam o'qilmadi (422), ro'yxatdan tanlab yuklanadi")
        reg.post(f"/api/ops/retakes/{rid2}/upload", json={"data_url": data_url(*RS.make_sheet(RG.demo_info(con, r2), "unsigned", "pdf", seed=12)[:2])})
    m2 = next(r for r in reg.get("/api/ops/retakes").json() if r["id"] == rid2)["scan"]
    ok(m2["signed"] is False and any("imzo" in w.lower() for w in m2["warnings"]), "Imzosiz skan belgilandi")
    ok(reg.post(f"/api/ops/retakes/{rid2}/approve", json={"score": 60}).status_code == 409, "Imzosiz varaqani oddiy tasdiqlab bo'lmaydi (409)")
    ok(reg.post(f"/api/ops/retakes/{rid2}/approve", json={"score": 60, "force": True}).status_code == 400, "Qo'lda tasdiqlash — izohsiz rad")
    ok(reg.post(f"/api/ops/retakes/{rid2}/return", json={"note": "O'qituvchi imzosi yo'q"}).status_code == 200, "Varaqa qaytarildi (yangi muddat)")
    # boshqa varaqaning skani → mos emas
    raw, ext, _ = RS.make_sheet(RG.demo_info(con, r0), "signed", "pdf", seed=13)
    up = reg.post(f"/api/ops/retakes/{rid2}/upload", json={"data_url": data_url(raw, ext)})
    ok(up.json()["scan"]["match"] is False, "Boshqa varaqaning skani — raqam mos emas deb belgilandi")
    ok(reg.post(f"/api/ops/retakes/{rid2}/approve", json={"score": 60}).status_code == 409, "Mos kelmagan skan bilan tasdiqlash — 409")
    reg.post(f"/api/ops/retakes/{rid2}/return", json={"note": "Boshqa talabaning varaqasi"})
    d = reg.post(f"/api/registrar/retakes/{rid2}/demo-scan", json={"variant": "signed", "fmt": "pdf"}); ok(d.status_code == 200 and d.json()["scan"]["signed"], "Demo generator: imzolangan skan oqimdan o'tdi")
    ok(imt.post(f"/api/registrar/retakes/{rid2}/demo-scan", json={"variant": "signed"}).status_code == 403, "Imtihon bo'limi skan yuklay olmaydi")
    # sirtqi bo'lim o'z talabasining bahosini tasdiqlaydi, registrator — boshqasini ham
    rs = DB.one(con, "SELECT * FROM retakes WHERE id=?", (rid_s,))
    ok(sir.post(f"/api/registrar/retakes/{rid_s}/demo-scan", json={"variant": "signed", "fmt": "pdf"}).status_code == 200, "Sirtqi bo'lim skan yukladi")
    ok(sir.post(f"/api/ops/retakes/{rid_s}/approve", json={"score": 64}).status_code == 200, "Sirtqi bo'lim sirtqi talabaning bahosini tasdiqladi")
    ok(sir.post(f"/api/ops/retakes/{rid2}/approve", json={"score": 64}).status_code == 403, "Sirtqi bo'lim kunduzgi talabaning bahosini tasdiqlay olmaydi")

    # ---------------------------------------------------------------- 5. imtihonga ruxsatnoma
    print("— 5. Imtihonga kirish ruxsatnomasi —")
    rid3, sid3, subj3, _ = retake_for(reg, "kunduzgi", 2)   # ochiq otrabotka → ruxsat yo'q
    pc = reg.get(f"/api/registrar/permit/{sid3}").json()
    ok(not pc["eligible"] and any("otrabotka" in x.lower() for x in pc["reasons"]), "Ochiq otrabotka → ruxsat yo'q, sabab ko'rsatiladi")
    r = reg.post("/api/docs/issue", json={"key": "exam_permit", "params": {"target": f"s:{sid3}"}})
    ok(r.status_code == 400 and "otrabotka" in r.text.lower(), "Rad etilgan talabaga ruxsatnoma chiqmaydi (sabablari bilan)")
    grp = next(g for g, in q("""SELECT s.group_id FROM students s WHERE s.status='faol' AND s.study_form='kunduzgi' AND s.faculty_id=2
                                GROUP BY s.group_id HAVING COUNT(*) BETWEEN 10 AND 40 ORDER BY s.group_id LIMIT 1"""))
    pg = reg.get(f"/api/registrar/permits?group={grp}").json()
    ok(pg["rows"] and 0 < pg["eligible"] <= len(pg["rows"]), f"Guruh bo'yicha: {pg['eligible']} / {len(pg['rows'])} ruxsat")
    ok(all(r["reasons"] for r in pg["rows"] if not r["eligible"]), "Ruxsat yo'qlarning har biri uchun sabab bor")
    subj = pg["subjects"][0]
    pgs = reg.get(f"/api/registrar/permits?group={grp}&subject={subj}").json()
    ok(all(any(c["key"] == "oraliq" for c in r["checks"]) for r in pgs["rows"]), f"Fan tanlansa — oraliq nazorat ham tekshiriladi («{subj}»)")
    r = reg.post("/api/docs/issue", json={"key": "exam_permit", "params": {"target": f"g:{grp}"}}); ok(r.status_code == 200 and r.json()["count"] == pg["eligible"], f"Guruhga ruxsatnoma: faqat {pg['eligible']} ta ruxsat olganga")
    regs = docs_from(r.json())
    code = q("SELECT verify_code FROM documents WHERE reg_no=?", (regs[0],))[0][0]
    vp = httpx.get(f"{B}/verify/{code}").text
    ok("Bergan bo'lim" in vp and "Registrator ofisi" in vp and "Baratov" in vp and "Berilgan vaqt" in vp, "QR tekshiruvi: bergan bo'lim, xodim va vaqt ko'rsatiladi")
    # kontrakt: muddat uzaytirilsa — ruxsat
    cand = None
    for s_id, in q("""SELECT id FROM students WHERE status='faol' AND payment_type='kontrakt' AND contract_amount>paid_amount AND study_form='kunduzgi' ORDER BY id LIMIT 600"""):
        c_ = RG.permit_check(con, s_id)
        if not c_["eligible"] and [x["key"] for x in c_["checks"] if not x["ok"]] == ["kontrakt"]: cand = s_id; break
    ok(cand, "Faqat kontrakt sababli ruxsat olmaydigan talaba topildi")
    ok(reg.post("/api/registrar/deferment", json={"student_id": cand, "until": (dt.date.today() + dt.timedelta(days=10)).isoformat(), "note": "test: buxgalteriya kelishuvi"}).status_code == 200, "Registrator kontrakt muddatini uzaytirdi")
    DEFER.extend(x[0] for x in q("SELECT id FROM contract_deferments WHERE student_id=? AND note LIKE 'test:%'", (cand,)))
    ok(reg.get(f"/api/registrar/permit/{cand}").json()["eligible"], "Muddat uzaytirilgach — ruxsat beriladi")
    ok(sir.post("/api/registrar/deferment", json={"student_id": sid_s, "until": (dt.date.today() + dt.timedelta(days=10)).isoformat(), "note": "x y z"}).status_code == 403, "Sirtqi bo'lim kontrakt muddatini uzaytira olmaydi")

    # ---------------------------------------------------------------- 6. shaxsiy grafik
    print("— 6. Shaxsiy grafik —")
    r = reg.post("/api/docs/issue", json={"key": "personal_schedule", "params": {"target": f"s:{sid3}", "deadline": (dt.date.today() + dt.timedelta(days=20)).isoformat()}})
    ok(r.status_code == 200 and r.json()["regs"][0].startswith("SG-"), f"Shaxsiy grafik chiqdi: {r.json().get('regs')}")
    reg_sg = docs_from(r.json())[0]
    code = q("SELECT verify_code FROM documents WHERE reg_no=?", (reg_sg,))[0][0]
    vp = httpx.get(f"{B}/verify/{code}").text
    ok("Shaxsiy grafik" in vp and "Baratov" in vp and "Bergan bo'lim" in vp, "Tekshiruv sahifasi: kim va qachon bergan")
    ok(q("SELECT COUNT(*) FROM ops_log WHERE student_id=? AND action='shaxsiy grafik berildi'", (sid3,))[0][0] >= 1, "Talaba tarixida qayd etildi")
    txt = "\n".join(c.text for t in Document(str(ROOT / "data" / "docs" / r.json()["file"])).tables for row in t.rows for c in row.cells)
    ok(subj3 in txt, "Grafikda ochiq otrabotka bandi bor")
    clean = next((s_id for s_id, in q("""SELECT s.id FROM students s WHERE s.status='faol' AND s.payment_type='grant' AND s.study_form='kunduzgi'
                 AND NOT EXISTS (SELECT 1 FROM grades g WHERE g.student_id=s.id AND g.score<40)
                 AND NOT EXISTS (SELECT 1 FROM absences a WHERE a.student_id=s.id) LIMIT 1""")), None)
    if clean: ok(reg.post("/api/docs/issue", json={"key": "personal_schedule", "params": {"target": f"s:{clean}"}}).status_code == 400, "Qarzi yo'q talabaga grafik kerak emas (400)")
    ok(imt.post("/api/docs/issue", json={"key": "personal_schedule", "params": {"target": f"s:{sid3}"}}).status_code == 403, "Imtihon bo'limi grafik bera olmaydi")

    # ---------------------------------------------------------------- 7. zinapoya
    print("— 7. Eskalatsiya zinapoyasi va ish stoli —")
    P = OPS.policy(con)
    ok((P["att_call_hours"], P["att_letter_hours"], P["att_reprimand_hours"]) == (30, 30, 48), "Institut me'yori: 30 soat — qo'ng'iroq va xat, 48 dan oshsa — hayfsan")
    ok([OPS.davomat_level(h, P) for h in (29, 30, 48, 49)] == [0, 2, 2, 3], "48 soat — hali xat bosqichi; 49 — hayfsan (qat'iy «oshsa»)")
    ok({k for k, _, _ in OPS.PLAN[("davomat", 2)]} == {"qongiroq", "xat"} and {k for k, _, _ in OPS.PLAN[("davomat", 3)]} == {"buyruq", "suhbat"}, "30 soat: call-markaz + xat; >48: hayfsan loyihasi + tyutor")
    ok(all(r[0] > 48 for r in q("""SELECT CAST(json_extract(facts,'$.hours') AS INT) FROM ops_cases WHERE rule='davomat' AND status='ochiq' AND level=3""")), "Bazadagi hayfsan holatlari — faqat 48 soatdan oshganlar")
    ok(not q("""SELECT 1 FROM ops_cases oc WHERE oc.rule='davomat' AND oc.status='ochiq' AND oc.level=2 AND NOT EXISTS
               (SELECT 1 FROM ops_tasks t WHERE t.case_id=oc.id AND t.kind='xat') LIMIT 1"""), "Har 30+ soatli holatda ogohlantirish xati topshirig'i bor")
    dk = reg.get("/api/registrar/desk").json(); st = {s["key"]: s for s in dk["stages"]}
    ok({"kontrakt_kritik", "kontrakt_otgan", "davomat_30", "davomat_hayfsan", "chetlashtirish", "akademik_jpa_ok", "tatil_oldin", "tatil_qaytish"} <= set(st), "Ish stoli: barcha bosqichlar")
    ok(all(s["say"] and s["basis"] for s in dk["stages"]), "Har bosqichda nima deyish va asos bor")
    basis = " ".join(b for s in dk["stages"] for b in s["basis"])
    ok("manba aniqlashtiriladi" in basis and not re.search(r"\d+\s*-?\s*son", basis), "Huquqiy asos — umumiy, «manba aniqlashtiriladi»; qaror raqami o'ylab topilmagan")
    ok(st["kontrakt_kritik"]["n"] == q("SELECT COUNT(DISTINCT student_id) FROM ops_cases WHERE rule='kontrakt' AND level=2 AND status='ochiq'")[0][0], "Kontrakt ≤3 kun soni holatlar bilan bir xil")
    ls = reg.get("/api/registrar/stage/davomat_hayfsan").json()
    ok(all(r["facts"]["hours"] > 48 for r in ls["rows"]), "Bir bosishda ro'yxat: hayfsan bosqichi")
    ok(sir.get("/api/registrar/desk").json()["scope"].startswith("Sirtqi"), "Sirtqi bo'lim ish stoli — o'z ko'lamida")
    ok(pro.get("/api/registrar/desk").status_code == 200 and cc.get("/api/registrar/desk").status_code == 403, "Prorektor ko'radi, call-markazga yopiq")
    # JPA yetarli, lekin qarzdor fanlar ≥ fails_warn → baribir ogohlantirish
    gok = q("""SELECT json_extract(facts,'$.gpa5'), json_array_length(json_extract(facts,'$.fails')) FROM ops_cases WHERE rule='akademik' AND status='ochiq'
               AND json_extract(facts,'$.gpa_ok') IN (1,'true') LIMIT 50""")
    ok(gok and all(g >= P["gpa_min"] and n >= P["fails_warn"] for g, n in gok) and st["akademik_jpa_ok"]["n"] > 0, f"JPA yetarli + ≥{int(P['fails_warn'])} qarzdor fan → ogohlantirish holati ({st['akademik_jpa_ok']['n']})")

    # ---------------------------------------------------------------- 7b. Registrator ofisi xodimi
    print("— 7b. Registrator ofisi xodimi (registrator_xodim) —")
    xid = q("SELECT id FROM users WHERE role='registrator_xodim' ORDER BY id LIMIT 1")
    if xid:
        xo = S(xid[0][0])
        ok(xo.get("/api/ops/cases?rule=kontrakt").status_code == 200 and len(xo.get("/api/ops/cases").json()) > 0, "Xodim: Talabalar markazi — to'liq (registrator) ko'rinishi")
        ok(xo.get("/api/registrar/desk").status_code == 200, "Xodim: ish stoli ochiq")
        ridx, sidx, _, _ = retake_for(xo, "kunduzgi", 2)
        ok(ridx > 0, "Xodim otrabotka varaqasini berdi")
        dx = xo.post(f"/api/registrar/retakes/{ridx}/demo-scan", json={"variant": "signed", "fmt": "pdf"})
        ok(dx.status_code == 200 and dx.json()["scan"]["signed"], "Xodim skan yukladi (o'qildi)")
        ok(xo.post(f"/api/ops/retakes/{ridx}/approve", json={"score": 70}).status_code == 403, "Bahoni tasdiqlash — boshliqda (xodimga 403)")
        ok(xo.post("/api/registrar/deferment", json={"student_id": sidx, "until": (dt.date.today() + dt.timedelta(days=5)).isoformat(), "note": "x y z"}).status_code == 403, "Kontrakt muddatini uzaytirish — boshliqda")
        tx = [t for t in xo.get("/api/ops/tasks?rule=davomat&kind=xat").json() if t["assignee_role"] == "talabalar"]
        ok(tx and all(t["can_act"] for t in tx), "Xodim Registrator navbatidagi xatlarni bajara oladi")
        tb = xo.get("/api/ops/tasks?kind=buyruq").json()
        ok(all(not t["can_act"] for t in tb), "Buyruq loyihalari (hayfsan, qaytish) — boshliqda")
        r = xo.post("/api/docs/issue", json={"key": "personal_schedule", "params": {"target": f"s:{sid3}"}})
        ok(r.status_code == 200, f"Xodim shaxsiy grafik chiqardi {r.text[:120] if r.status_code != 200 else ''}"); docs_from(r.json())
        code = q("SELECT verify_code FROM documents WHERE reg_no=?", (r.json()["regs"][0],))[0][0]
        ok("Norov" in httpx.get(f"{B}/verify/{code}").text or "Registrator ofisi xodimi" in httpx.get(f"{B}/verify/{code}").text, "QR tekshiruvida grafikni bergan xodim ko'rinadi")
    else:
        print("  (registrator_xodim akkaunti yo'q — o'tkazib yuborildi)")

    # ---------------------------------------------------------------- 8. akademik ta'til
    print("— 8. Akademik ta'til —")
    ok(P["leave_warn_days"] == 90, "Ta'til tugashidan ~3 oy (90 kun) oldin ogohlantirish")
    t1 = q("""SELECT t.script FROM ops_tasks t JOIN ops_cases oc ON oc.id=t.case_id WHERE oc.rule='tatil' AND oc.level=1 AND t.assignee_role='call_center' LIMIT 1""")
    ok(t1 and "qaytish" in t1[0][0].lower(), "≤90 kun: call-markaz topshirig'i skript bilan")
    far = q("""SELECT json_extract(facts,'$.days') FROM ops_cases WHERE rule='tatil' AND level=1 AND status='ochiq' ORDER BY 1 DESC LIMIT 1""")
    ok(far and 30 < far[0][0] <= 90, f"Ogohlantirish oynasi kengaydi (eng uzog'i {far[0][0] if far else '—'} kun)")
    ok(any(k == "buyruq" for k, _, _ in OPS.PLAN[("tatil", 2)]), "Qaytishga ≤7 kun: Registrator ofisiga buyruq loyihasi topshirig'i")
    sc = OPS.script("tatil", "buyruq", {"order_no": "TH-25/1", "end": dt.date.today().isoformat(), "days": 5}, {"full_name": "Test Talaba"}, P)
    ok(any("qayta tiklash" in x and "buyruqlar modulida" in x for x in sc["say"]), "Buyruq topshirig'i: «ta'tildan qaytish» loyihasi va buyruqlar moduliga bog'lanish")
finally:
    cleanup()
print(f"\nJami: {N[0]} tekshiruv · HAMMASI O'TDI")
