"""Reyting moduli — talabalar o'zlashtirish reytingi: uchidan-uchigacha testlar.

Ishga tushirish (server http://127.0.0.1:8000 da ishlab tursin):  .venv/bin/python tests/test_reyting.py
Bazani o'zgartirmaydi (faqat reyting keshini qayta hisoblaydi; barmoq izi tekshiruvida bitta bahoni o'zgartirib, darhol qaytaradi).
Tekshiradi:
  1. Kesh: faqat faol talabalar; har darajada o'rin = 1 + undan qat'iy yaxshilar soni (RANK), jami = bo'lim hajmi; GPA formulasi.
  2. Teng kelganda tartib: GPA → o'rtacha ball → davomat (qayd etilmagan — oxirida).
  3. Ro'yxat API: jami, sahifalash, saralash, «37 / 1 240» va foiz, o'tgan semestrga nisbatan o'zgarish, filtrlar.
  4. Talaba kartasi: fanlar (oraliq + yakuniy = ball, harf, baho, kredit), semestr va kumulyativ GPA, o'rinlar, trend.
  5. Ko'lam: Registrator (17, 43), Akademik (18) — hammasi; Sirtqi (27) — faqat sirtqi; kafedra (31) — o'z kafedrasi;
     o'qituvchi (15) — o'zi baholagan talabalar; Kuzatuv kengashi (1) — faqat jamlangan, ism-shariflarsiz; Buxgalteriya (11) — 403.
  6. Eksport: qaydnoma .xlsx / .docx (sarlavha, imzo qatorlari), a'lochilar .xlsx — haqiqiy fayllar.
  7. Qayta hisoblash — faqat Registrator ofisi va Akademik bo'lim; rad etilganlar audit jurnalida.
"""
import io, json, math, sqlite3, sys
from pathlib import Path
import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from app import academic_rules as AR, reyting as RTM   # noqa: E402

B = "http://127.0.0.1:8000"
N = [0]
def ok(cond, msg):
    N[0] += 1
    print(("✓ " if cond else "✗ XATO: ") + msg)
    if not cond: sys.exit(1)

def S(uid):
    c = httpx.Client(base_url=B, timeout=120)
    r = c.post("/api/login", json={"user_id": uid, "password": "Isft2026"}); assert r.status_code == 200, (uid, r.text)
    return c

db = sqlite3.connect(ROOT / "data" / "jarvis.db", timeout=30)
q = lambda sql, a=(): db.execute(sql, a).fetchall()
q1 = lambda sql, a=(): db.execute(sql, a).fetchone()[0]

reg, regx, akad, sir, kaf, oq, ken, bux, rek, pro = S(17), S(43), S(18), S(27), S(31), S(15), S(1), S(11), S(2), S(3)
CUR, PREV = AR.CURRENT_SEMESTER, AR.CURRENT_SEMESTER - 1

print("— Qayta hisoblash va kesh —")
r = reg.post("/api/reyting/recompute")
ok(r.status_code == 200 and r.json()["rows"] > 0, f"Registrator ofisi qayta hisoblaydi ({r.json().get('rows')} qator, {r.json().get('seconds')} s)")
ok(akad.post("/api/reyting/recompute").status_code == 200, "Akademik bo'lim qayta hisoblaydi")
for who, c in (("kengash (1)", ken), ("kafedra (31)", kaf), ("o'qituvchi (15)", oq), ("Sirtqi bo'lim (27)", sir), ("Buxgalteriya (11)", bux)):
    ok(c.post("/api/reyting/recompute").status_code == 403, f"Qayta hisoblash: {who} — 403")
ok(q1("SELECT COUNT(*) FROM audit_log WHERE resource='rating' AND action='reyting: qayta hisoblash' AND allowed=0") >= 5,
   "Rad etilgan qayta hisoblash so'rovlari audit jurnalida (resurs «rating»)")

faol = {s for (s,) in q("SELECT DISTINCT g.student_id FROM grades g JOIN students s ON s.id=g.student_id WHERE s.status='faol' AND g.semester=?", (CUR,))}
cached = {s for (s,) in q("SELECT student_id FROM rating_cache WHERE semester=?", (CUR,))}
ok(cached == faol, f"Keshda faqat faol talabalar va hammasi ({len(cached)})")
ok(q1("SELECT COUNT(*) FROM rating_cache r JOIN students s ON s.id=r.student_id WHERE s.status!='faol'") == 0, "Akademik ta'tildagilar reytingda yo'q")
ok(q1("SELECT COUNT(*) FROM rating_cache WHERE semester=? AND n_f>0", (CUR,)) > 0, "«F» bo'lgan talabalar reytingda qoladi (akademik qarzdor)")

# --- GPA formulasi (Python'da qayta hisoblash, academic_rules) ---
credits = AR.subject_credits(db)
rows = q("SELECT student_id, gpa, avg_score, credits, credits_ok, n_f, min_score FROM rating_cache WHERE semester=? ORDER BY student_id LIMIT 400", (CUR,))
bad = 0
for sid, gpa, avg, cr, crok, nf, mn in rows:
    gs = q("SELECT subject, score FROM grades WHERE student_id=? AND semester=?", (sid, CUR))
    items = [(AR.credit_of(credits, s), AR.grade5(sc)[0]) for s, sc in gs]
    exp = AR.gpa(items)
    if exp != gpa or AR.ratio2(sum(sc for _, sc in gs), len(gs)) != avg or cr != sum(k for k, _ in items) \
       or nf != sum(sc < AR.PASS for _, sc in gs) or crok != sum(AR.credit_of(credits, s) for s, sc in gs if sc >= AR.PASS) or mn != min(sc for _, sc in gs):
        bad += 1
ok(bad == 0, f"GPA = Σ(kredit × baho) / Σ kredit, o'rtacha ball, kreditlar, «F» soni — {len(rows)} talabada Python hisobi bilan bir xil")
ok(q1("SELECT COUNT(*) FROM rating_credits WHERE source=?", (AR.CREDIT_SOURCE_SYL,)) == len([s for (s,) in q("SELECT subject FROM rating_credits") if s in credits]),
   f"Kredit manbai: o'quv dasturidan {len(credits)} fan, qolganlari standart {AR.CREDIT_DEFAULT}")

# --- o'rinlar: har darajada RANK va jami ---
cols = "student_id, semester, gpa, avg_score, attendance, group_id, course, level, direction, faculty_id, " + \
       ", ".join(f"r_{k}, n_{k}" for k, _ in AR.RATING_LEVELS)
data = [dict(zip([c.strip() for c in cols.split(",")], r)) for r in q(f"SELECT {cols} FROM rating_cache")]
PARTS = {"group": ("semester", "group_id"), "course": ("semester", "level", "course"), "direction": ("semester", "level", "direction"),
         "faculty": ("semester", "faculty_id"), "institute": ("semester",)}
key = lambda r: (-r["gpa"], -r["avg_score"], r["attendance"] is None, -(r["attendance"] or 0))
for lv, pk in PARTS.items():
    parts = {}
    for r in data: parts.setdefault(tuple(r[k] for k in pk), []).append(r)
    errs = 0
    for rs in parts.values():
        rs.sort(key=key)
        for i, r in enumerate(rs):
            expect = 1 if i == 0 else (rs[i - 1][f"r_{lv}"] if key(rs[i - 1]) == key(r) else i + 1)
            if r[f"r_{lv}"] != expect or r[f"n_{lv}"] != len(rs): errs += 1
        if rs and (rs[0][f"r_{lv}"] != 1 or max(x[f"r_{lv}"] for x in rs) > len(rs)): errs += 1
    ok(errs == 0, f"O'rinlar — {dict(AR.RATING_LEVELS)[lv].lower()}: {len(parts)} bo'lim, o'rin = 1 + qat'iy yaxshilar soni, jami = bo'lim hajmi")

# --- teng kelganda tartib ---
cur = [r for r in data if r["semester"] == CUR]
by_gpa = {}
for r in cur: by_gpa.setdefault(r["gpa"], []).append(r)
pair_avg = next(((a, b) for rs in by_gpa.values() for a in rs for b in rs if a["avg_score"] > b["avg_score"]), None)
ok(pair_avg and pair_avg[0]["r_institute"] < pair_avg[1]["r_institute"],
   f"GPA teng ({pair_avg and pair_avg[0]['gpa']}) — o'rtacha ball yuqorisi oldinda ({pair_avg and pair_avg[0]['avg_score']} > {pair_avg and pair_avg[1]['avg_score']})")
by_ga = {}
for r in cur: by_ga.setdefault((r["gpa"], r["avg_score"]), []).append(r)
pair_att = next(((a, b) for rs in by_ga.values() for a in rs for b in rs if a["attendance"] is not None and b["attendance"] is not None
                 and a["attendance"] > b["attendance"]), None)
ok(pair_att and pair_att[0]["r_institute"] < pair_att[1]["r_institute"], "GPA va o'rtacha ball teng — davomati yuqorisi oldinda")
pair_null = next(((a, b) for rs in by_ga.values() for a in rs for b in rs if a["attendance"] is not None and b["attendance"] is None), None)
ok(pair_null is None or pair_null[0]["r_institute"] < pair_null[1]["r_institute"], "Davomat qayd etilmagan (masofaviy) — teng kelganda oxirida")

print("— Ro'yxat API —")
L = reg.get("/api/reyting/list", params={"sem": CUR, "per": 50}).json()
ok(L["total"] == len(faol) and len(L["rows"]) == 50 and [x["place"]["rank"] for x in L["rows"]] == sorted(x["place"]["rank"] for x in L["rows"]),
   f"Registrator: jami {L['total']}, 50 qator, o'rin bo'yicha tartib")
x = L["rows"][0]
ok(x["place"]["n"] == len(faol) and x["place"]["pct"] == AR.percentile(x["place"]["rank"], x["place"]["n"]), f"O'rin «{x['place']['rank']} / {x['place']['n']}», yuqori {x['place']['pct']}%")
pr = q1("SELECT r_institute FROM rating_cache WHERE student_id=? AND semester=?", (x["id"], PREV))
ok(x["delta"] == pr - x["place"]["rank"], f"O'zgarish = o'tgan semestr o'rni − joriy o'rin ({x['delta']:+d})")
L2 = reg.get("/api/reyting/list", params={"sem": CUR, "per": 50, "page": 3}).json()
ok(L2["rows"][0]["place"]["rank"] >= L["rows"][-1]["place"]["rank"] and L2["page"] == 3, "Sahifalash: 3-sahifa davom etadi")
G = reg.get("/api/reyting/list", params={"sort": "gpa", "dir": "asc", "per": 20}).json()["rows"]
ok([r["gpa"] for r in G] == sorted(r["gpa"] for r in G), "Saralash: GPA o'sish tartibida")
D = reg.get("/api/reyting/list", params={"flag": "qarzdor", "per": 30}).json()
ok(D["total"] == q1("SELECT COUNT(*) FROM rating_cache WHERE semester=? AND n_f>0", (CUR,)) and all(r["debtor"] and r["n_f"] > 0 for r in D["rows"]),
   f"Filtr «faqat qarzdorlar»: {D['total']}")
E = reg.get("/api/reyting/list", params={"flag": "alochi", "per": 30}).json()
ok(E["total"] > 0 and all(r["excellent"] and r["n_f"] == 0 for r in E["rows"]), f"Filtr «faqat a'lochilar»: {E['total']}")
gid = x["group_id"]
GR = reg.get("/api/reyting/list", params={"group": gid, "level": "group", "per": 200}).json()
ok(GR["total"] == q1("SELECT COUNT(*) FROM rating_cache WHERE group_id=? AND semester=?", (gid, CUR)) and
   sorted(r["place"]["rank"] for r in GR["rows"])[0] == 1 and all(r["place"]["n"] == GR["total"] for r in GR["rows"]), "Guruh filtri va guruh darajasidagi o'rin")
nm = x["name"].split()[0]
ok(any(r["id"] == x["id"] for r in reg.get("/api/reyting/list", params={"q": x["hemis_id"]}).json()["rows"]), "Qidiruv: HEMIS ID bo'yicha")
ok(reg.get("/api/reyting/list", params={"level": "xato"}).status_code == 400 and reg.get("/api/reyting/list", params={"sem": 9}).status_code == 400,
   "Noto'g'ri daraja/semestr — 400")
P0 = reg.get("/api/reyting/list", params={"sem": PREV, "per": 10}).json()
ok(P0["total"] == q1("SELECT COUNT(*) FROM rating_cache WHERE semester=?", (PREV,)) and not P0["has_prev"], "O'tgan semestr reytingi (oldingisi yo'q — o'zgarish ko'rsatilmaydi)")

print("— Talaba kartasi —")
C = reg.get(f"/api/reyting/student/{x['id']}").json()
sem = next(s for s in C["semesters"] if s["sem"] == CUR)
ok(all(g["oraliq"] + g["yakuniy"] == g["score"] and 0 <= g["oraliq"] <= AR.ORALIQ_MAX and g["letter"] == AR.letter(g["score"]) and g["grade"] == AR.grade5(g["score"])[0]
       and g["credits"] == AR.credit_of(credits, g["subject"]) and g["teacher"] for g in sem["subjects"]),
   f"Fanlar: ball = oraliq + yakuniy, harf, 5 baho, kredit, o'qituvchi ({len(sem['subjects'])} fan)")
allg = q("SELECT subject, score FROM grades WHERE student_id=?", (x["id"],))
ok(C["cumulative"]["gpa"] == AR.gpa([(AR.credit_of(credits, s), AR.grade5(sc)[0]) for s, sc in allg]) and
   sem["gpa"] == x["gpa"], f"Semestr GPA {sem['gpa']} va kumulyativ GPA {C['cumulative']['gpa']}")
ok(set(sem["places"]) == {k for k, _ in AR.RATING_LEVELS} and sem["places"]["institute"]["rank"] == x["place"]["rank"] and "delta" in sem["places"]["group"],
   "O'rinlar har darajada (guruh, kurs, yo'nalish, fakultet, institut) va o'zgarish")
ok(len(C["trend"]) == 2 and [t["sem"] for t in C["trend"]] == [PREV, CUR], "Trend: semestrlar bo'yicha")
ak = q1("SELECT id FROM students WHERE status!='faol' LIMIT 1")
CA = reg.get(f"/api/reyting/student/{ak}").json()
ok(CA["ranked"] is False and all(s["places"] is None for s in CA["semesters"]), "Akademik ta'tildagi talaba: baholar ko'rinadi, reytingda emas")
ok(reg.get("/api/reyting/student/99999999").status_code == 404, "Mavjud bo'lmagan talaba — 404")

print("— Ko'lam va ruxsatlar —")
for who, c in (("Registrator ofisi xodimi (43)", regx), ("Akademik bo'lim (18)", akad), ("Rektor (2)", rek), ("O'quv prorektori (3)", pro)):
    ok(c.get("/api/reyting/list", params={"per": 10}).json()["total"] == len(faol), f"{who}: butun institut")
n_sir = q1("SELECT COUNT(*) FROM rating_cache WHERE semester=? AND study_form='sirtqi'", (CUR,))
Ls = sir.get("/api/reyting/list", params={"per": 200}).json()
ok(Ls["total"] == n_sir and all(r["form"] == "sirtqi" for r in Ls["rows"]), f"Sirtqi bo'lim (27): faqat sirtqi talabalar ({n_sir})")
kun = q1("SELECT student_id FROM rating_cache WHERE study_form='kunduzgi' AND semester=? LIMIT 1", (CUR,))
ok(sir.get(f"/api/reyting/student/{kun}").status_code == 403, "Sirtqi bo'lim: kunduzgi talaba kartasi — 403")
Ms = sir.get("/api/reyting/meta").json()
ok(all(g["form"] == "sirtqi" for g in Ms["groups"]) and Ms["mode"] == "scoped", "Sirtqi bo'lim: guruhlar ro'yxati — faqat sirtqi")
Ts = sir.get("/api/reyting/top", params={"pct": 10}).json()
ok(all(r["study_form"] == "sirtqi" for cc in Ts["courses"] for r in cc["rows"]), "Sirtqi bo'lim: a'lochilar — faqat sirtqi")

dep = q1("SELECT department_id FROM users WHERE id=31")
n_kaf = q1("SELECT COUNT(*) FROM rating_cache WHERE semester=? AND group_id IN (SELECT id FROM groups_ WHERE department_id=?)", (CUR, dep))
Lk = kaf.get("/api/reyting/list", params={"per": 200}).json()
own_groups = {g for (g,) in q("SELECT id FROM groups_ WHERE department_id=?", (dep,))}
ok(Lk["total"] == n_kaf and all(r["group_id"] in own_groups for r in Lk["rows"]), f"Kafedra mudiri (31): o'z kafedrasi guruhlari ({n_kaf})")
other = q1("SELECT r.student_id FROM rating_cache r JOIN groups_ g ON g.id=r.group_id WHERE g.department_id!=? AND r.semester=? LIMIT 1", (dep, CUR))
other_g = q1("SELECT id FROM groups_ WHERE department_id!=? LIMIT 1", (dep,))
ok(kaf.get(f"/api/reyting/student/{other}").status_code == 403 and kaf.get(f"/api/reyting/qaydnoma/{other_g}").status_code == 403 and
   kaf.get(f"/api/reyting/qaydnoma/{other_g}/export", params={"fmt": "xlsx"}).status_code == 403, "Kafedra mudiri: boshqa kafedra talabasi va qaydnomasi — 403")
Uk = kaf.get("/api/reyting/units", params={"kind": "kafedra"}).json()
ok([r["id"] for r in Uk["rows"]] == [dep] and Uk["rows"][0]["of"] >= 1, f"Kafedra mudiri: kafedralar reytingida faqat o'z kafedrasi (o'rni {Uk['rows'][0]['rank']} / {Uk['rows'][0]['of']})")
Ut = kaf.get("/api/reyting/units", params={"kind": "teacher"}).json()
ok(Ut["rows"] and all(r["department_id"] == dep for r in Ut["rows"]), "Kafedra mudiri: o'z kafedrasi o'qituvchilari")
Ug = kaf.get("/api/reyting/units", params={"kind": "group"}).json()
ok(Ug["rows"] and all(r["id"] in own_groups for r in Ug["rows"]), "Kafedra mudiri: o'z guruhlari reytingi")

tid = q1("SELECT teacher_id FROM users WHERE id=15")
graded = {s for (s,) in q("SELECT DISTINCT g.student_id FROM grades g JOIN students s ON s.id=g.student_id WHERE g.teacher_id=? AND s.status='faol'", (tid,))}
Lo = oq.get("/api/reyting/list", params={"per": 200}).json()
ok(Lo["total"] == len(graded) and all(r["id"] in graded for r in Lo["rows"]), f"O'qituvchi (15): faqat o'zi baholagan talabalar ({len(graded)})")
notg = q1(f"SELECT student_id FROM rating_cache WHERE semester=? AND student_id NOT IN ({','.join(map(str, graded)) or 0}) LIMIT 1", (CUR,))
ok(oq.get(f"/api/reyting/student/{notg}").status_code == 403, "O'qituvchi: boshqa talaba kartasi — 403")
ok([r["id"] for r in oq.get("/api/reyting/units", params={"kind": "teacher"}).json()["rows"]] == [tid], "O'qituvchi: o'qituvchilar reytingida faqat o'zi")

ok(ken.get("/api/reyting/overview").status_code == 200, "Kuzatuv kengashi (1): umumiy ko'rinish (jamlangan)")
for path in ("/api/reyting/list", f"/api/reyting/student/{x['id']}", f"/api/reyting/qaydnoma/{gid}", f"/api/reyting/qaydnoma/{gid}/export?fmt=docx",
             "/api/reyting/top", "/api/reyting/top/export", "/api/reyting/units?kind=teacher"):
    r = ken.get(path)
    ok(r.status_code == 403 and r.json().get("denied"), f"Kuzatuv kengashi: {path.split('?')[0]} — 403")
Mk = ken.get("/api/reyting/meta").json()
Dk = ken.get("/api/reyting/dynamics").json()
Uk1 = ken.get("/api/reyting/units", params={"kind": "group"}).json()
blob = json.dumps([Mk, Dk, Uk1, ken.get("/api/reyting/overview").json()], ensure_ascii=False)
names = [n for (n,) in q("SELECT s.full_name FROM rating_cache r JOIN students s ON s.id=r.student_id WHERE r.semester=? ORDER BY r.r_institute LIMIT 50", (CUR,))]
ok(Mk["mode"] == "aggregate" and not Mk["groups"] and "risers" not in Dk and "list" not in Mk["tabs"] and
   not any(n in blob for n in names) and "hemis_id" not in blob and "full_name" not in blob, "Kuzatuv kengashi: ism-sharif va HEMIS ID umuman yuborilmaydi")
ok(Dk["groups_up"] and Dk["summary"]["n"] == len(faol), "Kuzatuv kengashi: dinamika — guruhlar bo'yicha jamlangan")
for path in ("/api/reyting/meta", "/api/reyting/overview", "/api/reyting/list", "/api/reyting/dynamics", "/api/reyting/units"):
    ok(bux.get(path).status_code == 403, f"Buxgalteriya (11): {path} — 403")
ok(q1("SELECT COUNT(*) FROM audit_log WHERE resource='rating' AND allowed=0 AND user_id=11") >= 5, "Buxgalteriya so'rovlari audit jurnalida (rad etilgan)")
ok(q1("SELECT COUNT(*) FROM audit_log WHERE resource='rating' AND allowed=1 AND user_id=17 AND action LIKE 'reyting:%'") >= 5, "Ruxsat etilgan murojaatlar ham audit jurnalida")

print("— Qaydnoma va eksport —")
from openpyxl import load_workbook   # noqa: E402
from docx import Document            # noqa: E402
Q = reg.get(f"/api/reyting/qaydnoma/{gid}").json()
ok(len(Q["rows"]) == GR["total"] and all(len(r["scores"]) == len(Q["subjects"]) for r in Q["rows"]) and
   [r["place"]["rank"] for r in Q["rows"]] == sorted(r["place"]["rank"] for r in Q["rows"]), f"Qaydnoma {Q['group']['name']}: {len(Q['rows'])} talaba × {len(Q['subjects'])} fan, o'rin tartibida")
r = reg.get(f"/api/reyting/qaydnoma/{gid}/export", params={"fmt": "xlsx"})
wb = load_workbook(io.BytesIO(r.content)); ws = wb.active
vals = [str(c.value) for row in ws.iter_rows() for c in row if c.value is not None]
ok(r.status_code == 200 and r.headers["content-type"].startswith("application/vnd.openxmlformats-officedocument.spreadsheetml") and
   "ISFT INSTITUTI" in vals[0] and any("REYTING QAYDNOMASI" in v for v in vals) and any(Q["rows"][0]["name"] == v for v in vals) and
   any("Registrator ofisi boshlig'i" == v for v in vals) and any(v.startswith(AR.ACADEMIC_UNIT) for v in vals), "Qaydnoma .xlsx: sarlavha, talabalar, imzo qatorlari")
r = reg.get(f"/api/reyting/qaydnoma/{gid}/export", params={"fmt": "docx"})
doc = Document(io.BytesIO(r.content))
text = "\n".join(p.text for p in doc.paragraphs) + "\n".join(c.text for t in doc.tables for row in t.rows for c in row.cells)
ok(r.status_code == 200 and "REYTING QAYDNOMASI" in text and "ISFT INSTITUTI" in text and Q["rows"][0]["name"] in text and
   "Registrator ofisi boshlig'i" in text and f"{AR.ACADEMIC_UNIT} boshlig'i" in text and doc.sections[0].page_width > doc.sections[0].page_height,
   "Qaydnoma .docx: blank, jadval, imzo qatorlari, albom yo'nalishi")
ok(reg.get(f"/api/reyting/qaydnoma/{gid}/export", params={"fmt": "pdf"}).status_code == 400, "Noma'lum format — 400")
kg = sorted(own_groups)[0]
ok(kaf.get(f"/api/reyting/qaydnoma/{kg}/export", params={"fmt": "docx"}).status_code == 200, "Kafedra mudiri: o'z guruhi qaydnomasi eksporti")
T = reg.get("/api/reyting/top", params={"pct": 10, "min_att": 85, "max_f": 0}).json()
okT = all(r["n_f"] == 0 and (r["attendance"] is None or r["attendance"] >= 85) and r["rank"] <= math.ceil(r["n"] * 0.10) for cc in T["courses"] for r in cc["rows"])
ok(T["total"] > 0 and okT, f"A'lochilar: kurs bo'yicha eng yaxshi 10%, qarzsiz, davomat ≥ 85% — {T['total']} talaba")
r = reg.get("/api/reyting/top/export", params={"pct": 10})
wb = load_workbook(io.BytesIO(r.content)); ws = wb.active
ok(r.status_code == 200 and ws.max_row >= T["total"] + 6, "A'lochilar .xlsx — haqiqiy fayl, barcha qatorlar")

print("— Dinamika, bo'linmalar, metodika —")
Dy = reg.get("/api/reyting/dynamics", params={"level": "course", "limit": 10}).json()
ok(Dy["risers"][0]["delta"] >= Dy["risers"][-1]["delta"] and Dy["fallers"][0]["delta"] <= 0 and
   Dy["risers"][0]["delta"] == Dy["risers"][0]["rank_prev"] - Dy["risers"][0]["rank"], "Dinamika: eng ko'p ko'tarilgan va tushgan talabalar")
Ug = reg.get("/api/reyting/units", params={"kind": "group"}).json()
elig = [r for r in Ug["rows"] if r["eligible"]]
ok(all(r["n_students"] >= AR.UNIT_MIN["group"] for r in elig) and all(not r["eligible"] and r["rank"] is None for r in Ug["rows"] if r["n_students"] < AR.UNIT_MIN["group"])
   and all((a["pass_pct"], a["avg"]) >= (b["pass_pct"], b["avg"]) for a, b in zip(elig, elig[1:])), f"Guruhlar reytingi: o'tish foizi → o'rtacha ball, kamida {AR.UNIT_MIN['group']} talaba")
Uk = reg.get("/api/reyting/units", params={"kind": "kafedra"}).json()
ok(len(Uk["rows"]) >= 7 and Uk["rows"][0]["rank"] == 1, f"Kafedralar reytingi ({len(Uk['rows'])})")
M = reg.get("/api/reyting/meta").json()["methodology"]
ok(M["pass"] == AR.PASS and M["formula"] == AR.GPA_FORMULA and [o["key"] for o in M["order"]] == ["gpa", "avg_score", "attendance"] and
   M["credit_default"] == AR.CREDIT_DEFAULT, "Metodika academic_rules'dan: formula, tartib, chegaralar")

print("— Kesh yangilanishi (barmoq izi) —")
sid0, subj0, sc0 = q("SELECT student_id, subject, score FROM grades WHERE semester=? LIMIT 1", (CUR,))[0]
fp0 = RTM.fingerprint(db)
db.execute("UPDATE grades SET score=? WHERE student_id=? AND subject=? AND semester=?", (sc0 + 1 if sc0 < 100 else sc0 - 1, sid0, subj0, CUR)); db.commit()
fp1 = RTM.fingerprint(db)
db.execute("UPDATE grades SET score=? WHERE student_id=? AND subject=? AND semester=?", (sc0, sid0, subj0, CUR)); db.commit()
ok(fp0 != fp1 and RTM.fingerprint(db) == fp0, "Baho o'zgarsa barmoq izi o'zgaradi → kesh avtomatik qayta quriladi (qayta seed shart emas)")

print("— Interfeys —")
html = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
ok('data-v="reyting"' in html and 'id="v-reyting"' in html and 'src="reyting.js"' in html, "index.html: menyu, bo'lim va skript ulangan")
js = (ROOT / "static" / "app.js").read_text(encoding="utf-8")
ok('reyting: typeof renderReyting' in js and '"buxgalteriya"' not in js.split('data-v="reyting"')[1].split("\n")[0], "app.js: yo'naltirish; menyu Buxgalteriyaga ko'rinmaydi")

print(f"\nJami: {N[0]} ta tekshiruv o'tdi.")
