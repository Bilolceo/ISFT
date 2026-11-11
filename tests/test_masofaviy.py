"""Masofaviy ta'lim moduli (app/masofaviy.py) — ruxsatlar, hisob izchilligi, material oqimi, kafedraga topshiriq, import, qoidalar, AI xulosa, hisobot.

Ishga tushirish:  ISFT_TEST_URL=http://127.0.0.1:8000 ISFT_CORE_DB=data/jarvis.db .venv/bin/python tests/test_masofaviy.py
   (yoki hammasi toza muhitda: python tests/run_all.py --only masofaviy)
DIQQAT: lokal bazani o'zgartiradi (material holatlari, import, topshiriq) — PRODUCTION'da ishlatilmaydi.
"""
import csv, io, json, os, re, sqlite3, sys, zipfile
from pathlib import Path
import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
B = os.environ.get("ISFT_TEST_URL", "http://127.0.0.1:8000")
DBP = Path(os.environ.get("ISFT_CORE_DB") or ROOT / "data" / "jarvis.db")
PW = re.search(r'DEMO_PASSWORD = os.getenv\("ISFT_CORE_DEMO_PASSWORD", "([^"]+)"\)', (ROOT / "app" / "rbac.py").read_text()).group(1)
fails = []
def ok(cond, msg):
    print(("  ✓ " if cond else "  ✗ ") + msg)
    if not cond: fails.append(msg)
def q(sql, a=()):
    con = sqlite3.connect(DBP); con.row_factory = sqlite3.Row
    try: return [dict(r) for r in con.execute(sql, a).fetchall()]
    finally: con.close()
def uid(role):
    r = q("SELECT id FROM users WHERE role=? ORDER BY id LIMIT 1", (role,)); assert r, f"{role} akkaunti yo'q"; return r[0]["id"]
def S(u):
    c = httpx.Client(base_url=B, timeout=300)
    r = c.post("/api/login", json={"user_id": u, "password": PW}); assert r.status_code == 200, f"login {u}: {r.text}"
    return c
P = "/api/masofaviy"

head, staff, rek, pro, kaf, teach, bux, cc = (S(uid(r)) for r in ("masofaviy", "masofaviy_xodim", "rektor", "prorektor_oquv", "kafedra", "oqituvchi", "buxgalteriya", "call_center"))
teach_tid = q("SELECT teacher_id FROM users WHERE id=?", (uid("oqituvchi"),))[0]["teacher_id"]
kaf_dept = q("SELECT department_id FROM users WHERE id=?", (uid("kafedra"),))[0]["department_id"]

print("== Ruxsatlar va ko'lam")
m = head.get(P + "/meta").json()
ok(m["tabs"] == ["umumiy", "talabalar", "kontent", "xavf", "hafta", "import"] and m["names"] and m["caps"]["policy"], "Bo'lim boshlig'i: 6 ta bo'lim, ismlar, qoidalar")
ms = staff.get(P + "/meta").json()
ok(ms["names"] and ms["caps"]["review"] and not ms["caps"]["policy"], "Bo'lim xodimi: ismlar va tekshirish bor, qoidalar yo'q")
ok(m["caps"]["remind"] and not ms["caps"]["remind"], "Kafedraga topshiriq — faqat bo'lim boshlig'i (xodimda «Topshiriq» tugmasi yo'q)")
mr = rek.get(P + "/meta").json()
ok(not mr["names"] and "talabalar" not in mr["tabs"] and mr["caps"]["report"], "Rektor: jamlangan ko'rinish, talabalar ro'yxati yo'q, hisobot bor")
ok(rek.get(P + "/students").status_code == 403, "Rektor individual talabalar ro'yxatini ololmaydi (403)")
ok(rek.get(P + "/risk").json()["items"] == [], "Rektor: xavf ro'yxatida ismlar yo'q (faqat sabablar soni)")
ok(kaf.get(P + "/students").status_code == 403 and kaf.get(P + "/overview").status_code == 403, "Kafedra mudiri talabalar va umumiy holatni ko'rmaydi")
ok(bux.get(P + "/meta").status_code == 403 and cc.get(P + "/meta").status_code == 403, "Buxgalteriya va call-markaz — ruxsat yo'q (403)")
den = q("SELECT COUNT(*) n FROM audit_log WHERE resource='distance' AND allowed=0")[0]["n"]
ok(den >= 5, f"Rad etilgan so'rovlar audit jurnalida ({den} ta)")
ki = kaf.get(P + "/items?due=&limit=300").json()
ok(ki["total"] > 0 and all(i["department_id"] == kaf_dept for i in ki["items"]), f"Kafedra faqat o'z kafedrasi materiallarini ko'radi ({ki['total']} ta)")
ti = teach.get(P + "/items?due=&limit=300").json()
ok(ti["total"] > 0 and all(i["teacher_id"] == teach_tid for i in ti["items"]), f"O'qituvchi faqat o'z materiallarini ko'radi ({ti['total']} ta)")

print("== Hisob izchilligi")
o = head.get(P + "/overview").json()
s, t = o["students"], o["content"]["total"]
ok(s["aktiv"] + s["noaktiv"] + s["kirmagan"] + s["tatil"] == s["total"] == q("SELECT COUNT(*) n FROM students WHERE study_form='masofaviy'")[0]["n"],
   f"Talabalar: aktiv+noaktiv+kirmagan+ta'tilda = jami ({s['total']})")
ok(s["tatil"] == q("SELECT COUNT(*) n FROM students WHERE study_form='masofaviy' AND status!='faol'")[0]["n"], "Ta'tildagilar soni bazadagi maqom bilan bir xil")
ok(s["qarzdor"] == q("""SELECT COUNT(DISTINCT g.student_id) n FROM grades g JOIN students s ON s.id=g.student_id WHERE s.study_form='masofaviy'
                       AND g.semester<1 AND g.score IS NOT NULL AND g.score<40""")[0]["n"], "Qarzdorlar soni baholar jadvalidan mustaqil hisob bilan mos")
deps = o["content"]["departments"]
ok(sum(d["due"] for d in deps) == t["due"] and sum(d["overdue"] for d in deps) == t["overdue"], "Kafedralar yig'indisi = jami (muddati kelgan, muddati o'tgan)")
ok(t["given"] <= t["due"] <= t["plan"] == q("SELECT COUNT(*) n FROM dl_items")[0]["n"], "Berilgan ≤ muddati kelgan ≤ reja")
ok(t["overdue"] == q("SELECT COUNT(*) n FROM dl_items WHERE status IN ('kutilmoqda','qaytarildi') AND due<?", (m["today"],))[0]["n"], "Muddati o'tganlar SQL bilan mos")
ok(deps[0]["pct"] == min(d["pct"] for d in deps), f"Eng ortda kafedra birinchi: {deps[0]['name']} ({deps[0]['pct']}%)")
kir = head.get(P + "/students?state=kirmagan&limit=200").json()
ok(kir["total"] == s["kirmagan"] and all(r["last_login"] is None for r in kir["items"]), "«Kirmagan» filtri: hammasida oxirgi kirish yo'q")
hi = head.get(P + "/students?sort=risk&limit=5").json()["items"]
ok(all(hi[i]["risk"] >= hi[i + 1]["risk"] for i in range(len(hi) - 1)) and all(x["reasons"] for x in hi), "Xavf bo'yicha tartib va har birida sabab bor")
card = head.get(f"{P}/students/{hi[0]['id']}").json()
ok(len(card["weeks"]) == 8 and "grades" in card, "Talaba kartasi: 8 haftalik faollik va baholar")
ok(head.get(f"{P}/students/{q('SELECT id FROM students WHERE study_form=? LIMIT 1', ('kunduzgi',))[0]['id']}").status_code == 404, "Kunduzgi talaba kartasi bu modulda ochilmaydi (404)")
ok(s["buyruq_jarayon"] >= 1, f"Imzolanmagan buyruq loyihasidagi talabalar ko'rinadi ({s['buyruq_jarayon']})")

print("== Material oqimi: yuklandi → tasdiqlandi / qaytarildi")
mine = teach.get(P + "/items?due=overdue&limit=50").json()["items"]
it = next(i for i in mine if i["status"] == "kutilmoqda")
ok(teach.post(f"{P}/items/{it['id']}/upload", json={"url": "javascript:alert(1)"}).status_code in (400, 422), "Noto'g'ri havola rad etiladi")
other = q("SELECT i.id FROM dl_items i JOIN dl_courses c ON c.id=i.course_id WHERE c.teacher_id!=? AND i.status='kutilmoqda' LIMIT 1", (teach_tid,))[0]["id"]
ok(teach.post(f"{P}/items/{other}/upload", json={"url": "https://lms.isft.uz/x"}).status_code == 404, "Boshqa o'qituvchi materialini belgilab bo'lmaydi (404)")
r = teach.post(f"{P}/items/{it['id']}/upload", json={"url": "https://lms.isft.uz/course/1/topic/1"}).json()
ok(r["status"] == "yuklandi", "O'qituvchi «yuklandi» deb belgiladi (havola bilan)")
ok(head.post(f"{P}/items/{it['id']}/review", json={"ok": False, "note": "x"}).status_code == 400, "Qaytarishda sabab majburiy")
ok(kaf.post(f"{P}/items/{it['id']}/review", json={"ok": True}).status_code == 403, "Kafedra mudiri tasdiqlay olmaydi (403)")
ok(staff.post(f"{P}/items/{it['id']}/review", json={"ok": True}).json()["status"] == "tasdiqlandi", "Bo'lim xodimi tasdiqladi")
ok(staff.post(f"{P}/items/{it['id']}/review", json={"ok": True}).status_code == 409, "Qayta tasdiqlash — 409")
ok(teach.post(f"{P}/items/{it['id']}/upload", json={"url": "https://lms.isft.uz/y"}).status_code == 409, "Tasdiqlangan materialni qayta belgilab bo'lmaydi (409)")
it2 = next(i for i in mine if i["status"] == "kutilmoqda" and i["id"] != it["id"])
teach.post(f"{P}/items/{it2['id']}/upload", json={"url": "https://youtu.be/abc"})
ok(head.post(f"{P}/items/{it2['id']}/review", json={"ok": False, "note": "Video ovozi yo'q"}).json()["status"] == "qaytarildi", "Boshliq qaytardi (sabab bilan)")
lg = teach.get(f"{P}/items/{it2['id']}/log").json()["items"]
ok([x["action"] for x in lg] == ["yuklandi", "qaytarildi"], "Material tarixi: yuklandi → qaytarildi")
tw = teach.get("/api/mywork").json()
ok(any(x["source"] == "masofaviy" for x in tw["items"]), "O'qituvchining «Mening vazifalarim»ida yuklanmagan materiallar bor")

print("== Kafedraga topshiriq")
d0 = deps[0]["department_id"]
ok(staff.post(P + "/remind", json={"department_id": d0, "days": 3}).status_code == 403, "Bo'lim xodimi kafedra mudiriga topshiriq bera olmaydi (403, faqat boshliq)")
r1 = head.post(P + "/remind", json={"department_id": d0, "days": 3}).json()
ok(r1.get("ok") and r1["items"] > 0, f"Topshiriq yaratildi: {r1.get('items')} ta material, {r1.get('teachers')} o'qituvchi")
tk = q("SELECT unit, src, origin, priority, body FROM tasks WHERE id=?", (r1["task_id"],))
ok(tk and tk[0]["unit"] == f"kaf{d0}" and tk[0]["src"] == f"dl:{d0}" and tk[0]["origin"] == "topshiriq", "Topshiriq kafedra navbatida (unit, manba, tur)")
ok(head.post(P + "/remind", json={"department_id": d0}).json().get("already") is True, "Bir kunda ikkinchi marta yuborilmaydi (already)")
ok(teach.post(P + "/remind", json={"department_id": d0}).status_code == 403, "O'qituvchi topshiriq yubora olmaydi (403)")

print("== Import (CSV)")
st2 = q("SELECT s.id, s.hemis_id FROM students s WHERE s.study_form='masofaviy' AND s.status='faol' ORDER BY s.id LIMIT 2")
mon = q("SELECT MAX(week) w FROM dl_activity")[0]["w"]
before = q("SELECT * FROM dl_activity WHERE week=? AND student_id IN (?,?)", (mon, st2[0]["id"], st2[1]["id"]))
buf = io.StringIO(); w = csv.writer(buf, delimiter=";")
w.writerow(["hemis_id", "hafta", "kirishlar", "daqiqa", "korilgan_material", "vk_qatnashgan", "vk_jami", "topshiriq_bajarilgan", "topshiriq_jami", "oxirgi_kirish"])
w.writerow([st2[0]["hemis_id"], mon, 5, 140, 9, 2, 2, 2, 2, f"{mon} 19:40"]); w.writerow([st2[1]["hemis_id"], mon, 1, 20, 1, 0, 2, 0, 2, ""])
w.writerow(["000000000000", mon, 1, 1, 1, 1, 1, 1, 1, ""])
r = head.post(f"{P}/import/activity?name=lms.csv", content=buf.getvalue().encode("utf-8")).json()
ok(r["ok"] == 2 and r["skipped"] == 1 and "topilmadi" in r["errors"][0], "Faollik importi: 2 qabul, 1 noma'lum HEMIS ID o'tkazib yuborildi")
ok(q("SELECT logins FROM dl_activity WHERE student_id=? AND week=?", (st2[0]["id"], mon))[0]["logins"] == 5, "Import qiymati bazaga yozildi")
ok(head.post(f"{P}/import/activity?name=x.csv", content=b"a;b\n1;2").status_code == 400, "Ustunlari noto'g'ri fayl rad etiladi")
ok(head.post(f"{P}/import/activity?name=x.exe", content=b"x").status_code == 400, "Faqat .csv/.xlsx qabul qilinadi")
ok(rek.post(f"{P}/import/activity?name=lms.csv", content=buf.getvalue().encode()).status_code == 403, "Rektor import qila olmaydi (403)")
ci = q("""SELECT c.subject, c.direction, c.course, i.topic_no, i.kind FROM dl_items i JOIN dl_courses c ON c.id=i.course_id
          WHERE i.status='kutilmoqda' ORDER BY i.id DESC LIMIT 1""")[0]
cb = io.StringIO(); cw = csv.writer(cb, delimiter=";"); cw.writerow(["fan", "yonalish", "kurs", "mavzu_no", "tur", "holat", "havola", "muddat"])
cw.writerow([ci["subject"], ci["direction"], ci["course"], ci["topic_no"], {"maruza": "Ma'ruza", "taqdimot": "taqdimot", "video": "Video", "test": "test"}[ci["kind"]],
             "yuklandi", "https://lms.isft.uz/z", ""])
cw.writerow(["Yo'q fan", "X", 1, 1, "video", "yuklandi", "", ""])
xi = q("""SELECT i.id, i.url, i.status, c.subject, c.direction, c.course, i.topic_no, i.kind FROM dl_items i JOIN dl_courses c ON c.id=i.course_id
          WHERE i.id!=(SELECT i2.id FROM dl_items i2 JOIN dl_courses c2 ON c2.id=i2.course_id WHERE c2.subject=? AND c2.direction=? AND c2.course=? AND i2.topic_no=? AND i2.kind=?)
          ORDER BY i.id LIMIT 1""", (ci["subject"], ci["direction"], ci["course"], ci["topic_no"], ci["kind"]))[0]
cw.writerow([xi["subject"], xi["direction"], xi["course"], xi["topic_no"], xi["kind"], "yuklandi", "javascript:alert(document.cookie)", ""])
r = head.post(f"{P}/import/content?name=checklist.csv", content=cb.getvalue().encode("utf-8")).json()
ok(r["ok"] == 1 and r["skipped"] == 2, f"Kontent nazorat varag'i importi: 1 yangilandi, 1 rejada yo'q, 1 xavfli havola ({r['ok']}/{r['skipped']})")
ok(any("http" in e for e in r["errors"]), "Importda javascript: havola rad etildi (sababi ko'rsatildi)")
xa = q("SELECT url, status FROM dl_items WHERE id=?", (xi["id"],))[0]
ok(xa["url"] == xi["url"] and xa["status"] == xi["status"], "Rad etilgan qator materialga yozilmadi (XSS havolasi bazada yo'q)")
ok(not q("SELECT 1 FROM dl_items WHERE url NOT LIKE 'http://%' AND url NOT LIKE 'https://%' AND url IS NOT NULL"), "Bazada http(s) bo'lmagan havola yo'q")
# demo holatni tiklash (faollik qatorlari va manba)
con = sqlite3.connect(DBP)
for b0 in before:
    con.execute("INSERT OR REPLACE INTO dl_activity VALUES(?,?,?,?,?,?,?,?,?,?,?)", tuple(b0[k] for k in
                ("student_id", "week", "logins", "minutes", "views", "vc_att", "vc_total", "tasks_done", "tasks_total", "last_login", "src")))
con.execute("UPDATE dl_meta SET v='demo' WHERE k='source'"); con.commit(); con.close()

print("== Qoidalar")
ok(staff.post(P + "/policy", json={"values": {"inactive_days": 10}}).status_code == 403, "Xodim qoidani o'zgartira olmaydi (403)")
ok(head.post(P + "/policy", json={"values": {"inactive_days": 999}}).status_code == 400, "Chegaradan tashqari qiymat rad etiladi")
ok(head.post(P + "/policy", json={"values": {"nomalum": 1}}).status_code == 400, "Noma'lum qoida rad etiladi")
ok(head.post(P + "/policy", json={"values": {"irregular_min_active": 9, "irregular_weeks": 6}}).status_code == 400, "Notekis faollik: min > haftalar — rad etiladi")
ok(set(m["policy"]) >= {"irregular_weeks", "irregular_min_active", "early_min_logins"}, "Yangi qoidalar (notekis faollik, semestr boshi) meta'da")
n14 = head.get(P + "/overview").json()["students"]["noaktiv"]
head.post(P + "/policy", json={"values": {"inactive_days": 7}})
n7 = head.get(P + "/overview").json()["students"]["noaktiv"]
head.post(P + "/policy", json={"values": {"inactive_days": 14}})
ok(n7 > n14, f"Qoida darhol ta'sir qiladi: noaktiv {n14} → {n7} (7 kun), keyin tiklandi")

print("== Erta ogohlantirish: notekis faollik va semestr boshi")
rs = {x["code"]: x["n"] for x in head.get(P + "/risk").json()["reasons"]}
ok(rs.get("notekis", 0) > 0 and rs.get("erta_sust", 0) > 0, f"Yangi sabablar hisoblanadi: notekis {rs.get('notekis')}, semestr boshida sust {rs.get('erta_sust')}")
for code in ("notekis", "erta_sust"):
    lst = head.get(f"{P}/students?reason={code}&limit=200").json()
    ok(lst["total"] == rs[code] and all(r["state"] == "aktiv" for r in lst["items"]), f"«{code}»: faqat aktiv talabalar ({lst['total']})")
    ok(not any({x["code"] for x in r["reasons"]} & {"kirmagan", "noaktiv"} for r in lst["items"]), f"«{code}»: kirmagan/noaktiv bilan ikki marta sanalmaydi")
    ok(all(x["sev"] == 1 for r in lst["items"] for x in r["reasons"] if x["code"] == code), f"«{code}»: og'irligi 1")
nt = head.get(f"{P}/students?reason=notekis&limit=1").json()["items"][0]
wk = head.get(f"{P}/students/{nt['id']}").json()["weeks"]
pol = head.get(P + "/meta").json()["policy"]
full = sorted(w["week"] for w in wk)[:-1][-pol["irregular_weeks"]:]                    # oxirgi to'liq haftalar (joriy hafta hisobga olinmaydi)
ok(sum(1 for w in wk if w["week"] in full and w["logins"] > 0) < pol["irregular_min_active"], "Notekis faollik — talaba kartasidagi haftalar bilan mos")
head.post(P + "/policy", json={"values": {"irregular_min_active": 1}})
n1 = {x["code"]: x["n"] for x in head.get(P + "/risk").json()["reasons"]}.get("notekis", 0)
head.post(P + "/policy", json={"values": {"irregular_min_active": 3}})
ok(n1 < rs["notekis"], f"Notekis faollik chegarasi darhol ta'sir qiladi: {rs['notekis']} → {n1}")
ok(staff.post(P + "/policy", json={"values": {"early_min_logins": 2}}).status_code == 403, "Xodim yangi qoidalarni ham o'zgartira olmaydi (403)")

print("== Havolalar: «Mening vazifalarim» filtr bilan")
hw = [x for x in head.get("/api/mywork").json()["items"] if x["source"] == "masofaviy"]
rv = next((x for x in hw if "tekshiruv" in x["title"]), None)
ok(rv and rv["link"]["tab"].startswith("kontent:view=materiallar") and "status=yuklandi" in rv["link"]["tab"], "Tekshiruv kutayotganlar havolasi materiallar ro'yxatiga (status=yuklandi) olib boradi")
kp = head.get("/api/bugun").json()["kpis"]
ok(kp and not any("None" in str(k["value"]) or "None" in str(k["sub"]) for k in kp), "Bosh sahifa ko'rsatkichlarida «None» yo'q")

print("== AI xulosa va hisobot")
a = head.post(P + "/ai/summary", json={"force": True}).json()
ok(a["xulosa"] and a["tavsiyalar"] and a["engine"] in ("claude", "qoida"), f"Xulosa tayyor (dvigatel: {a['engine']})")
names = [r["full_name"] for r in q("SELECT full_name FROM students WHERE study_form='masofaviy' LIMIT 400")]
fj = json.dumps(a["facts"], ensure_ascii=False)
ok(not any(n in fj for n in names) and "hemis" not in fj.lower(), "AI'ga yuboriladigan faktlarda talaba ismi yoki HEMIS ID yo'q")
ok(head.post(P + "/ai/summary", json={}).json()["cached"] is True, "Ma'lumot o'zgarmasa — saqlangan xulosa qaytadi")
ok(kaf.post(P + "/ai/summary", json={}).status_code == 403, "Kafedra mudiri AI xulosani so'ray olmaydi (403)")
from app import masofaviy as DLm
known = DLm._numbers({"a": 3765, "berilgan_foiz": 92.9, "c": "2026-11-10"})
txt, dropped = DLm._verify("Jami 3765 talaba. Kontent 92,9% berilgan. Taxminan 4100 nafar faol.", known)
ok("3765" in txt and "92,9" in txt and len(dropped) == 1 and "4100" in dropped[0], "AI matnidagi to'qilgan raqamli jumla olib tashlanadi")
_, d5 = DLm._verify("5 ta kafedra butunlay to'xtagan.", known)
ok(d5, "Qat'iy tekshiruv: kichik to'qima son ham (5 ta kafedra) olib tashlanadi")
t3, d3 = DLm._verify("Qaytarilganlarni 3 kun ichida qayta yuklash.", known, lenient=True)
ok(t3 and not d3, "Tavsiyalarda kichik sonlarga ruxsat (3 kun ichida)")
ok(not DLm._verify("10.11.2026 holatiga 2-kurs talabalari.", known)[1] and DLm._verify("11.12.2026 holatiga.", known)[1], "Sana faqat faktlardagi bilan aynan bir xil bo'lsa o'tadi; «2-kurs» yorliq")
kp = DLm._numbers({"aktiv_foiz": 90.9, "oraliq_min": 12, "kafedralar": [{"berilgan_foiz": 61.5}]})
ok(not DLm._verify("Aktivlik 90,9% ni tashkil etadi. Bir kafedrada 61,5%.", kp)[1], "Foiz faktlardagi foiz maydoni bilan mos — o'tadi")
ok(DLm._verify("Aktivlik keyingi oyda 12% ga oshadi.", kp)[1] and DLm._verify("12% ga oshirish.", kp, lenient=True)[1],
   "«12%» — 12 soni faktlarda boshqa ma'noda bor, lekin foiz emas: jumla olib tashlanadi (tavsiyalarda ham)")
F = a["facts"]
def boom(f): raise RuntimeError("tarmoq xatosi")
d_, e_, _, c_ = DLm._ai_result(F, boom)
ok(e_ == "qoida" and not c_ and d_.get("ai_error") and d_["xulosa"], "AI xatosi: qoidaga asoslangan xulosa, KESHLANMAYDI")
for bad in ({"xulosa": None}, {"xulosa": "", "asosiy": [], "xavflar": [], "tavsiyalar": []}, {"xulosa": "Matn.", "asosiy": "x"}, ["x"]):
    d_, e_, _, c_ = DLm._ai_result(F, lambda f, b=bad: (b, {"in": 1, "out": 1}))
    ok(e_ == "qoida" and not c_ and d_["xulosa"], f"Buzuq/bo'sh AI javobi ({str(bad)[:30]}) — zaxira xulosa, keshlanmaydi")
d_, e_, _, c_ = DLm._ai_result(F, lambda f: ({"xulosa": "Jami 999999 talaba.", "asosiy": ["5 ta kafedra to'xtagan."], "xavflar": [], "tavsiyalar": []}, {}))
ok(e_ == "qoida" and not c_ and len(d_["removed"]) == 2, "Hamma jumla to'qima bo'lsa — zaxira xulosa, keshlanmaydi")
tot = F["talabalar"]["jami"]
d_, e_, _, c_ = DLm._ai_result(F, lambda f: ({"xulosa": f"Masofaviy ta'limda {tot} nafar talaba.", "asosiy": [], "xavflar": [], "tavsiyalar": ["Kafedralar bilan 3 kun ichida uchrashish."]}, {}))
ok(e_ == "claude" and c_ and d_["tavsiyalar"], "To'g'ri AI javobi — keshlanadi")
ok(DLm._ai_result(F, None)[1:4:2] == ("qoida", True), "Kalit yo'q: qoidaviy xulosa keshlanadi (deterministik)")
import copy
F2 = copy.deepcopy(F); F2["kontent"]["berilgan_foiz"] = None; F2["talabalar"]["videokonferensiya_qatnashish_foiz"] = None
for k2 in F2["kontent"]["kafedralar"]: k2["berilgan_foiz"] = None
ok("None" not in json.dumps(DLm._rule_summary(F2), ensure_ascii=False) and DLm._pf(None) == "—", "Foiz yo'q bo'lsa «—» («None%» emas)")
def docx_text(b):
    z = zipfile.ZipFile(io.BytesIO(b)); return re.sub(r"<[^>]+>", " ", z.read("word/document.xml").decode())
rh = head.get(P + "/report.docx"); rr = rek.get(P + "/report.docx")
ok(rh.status_code == 200 and rh.content[:2] == b"PK" and rr.status_code == 200, "Hisobot (.docx) — bo'lim va rektor uchun")
top = head.get(P + "/students?sort=risk&limit=1").json()["items"][0]["full_name"]
ok(top in docx_text(rh.content) and top not in docx_text(rr.content), "Rektor nusxasida talaba ismlari yo'q, bo'lim nusxasida bor")
ok(kaf.get(P + "/report.docx").status_code == 403, "Kafedra mudiri hisobot ololmaydi (403)")
ok("None" not in docx_text(rh.content), "Hisobotda «None» yo'q")
ok("5. Xulosa (qoidalar asosida)" in docx_text(rh.content) or "5. Xulosa (AI" in docx_text(rh.content), "Hisobotga joriy faktlarga mos xulosa kiritildi")
con = sqlite3.connect(DBP); con.execute("UPDATE dl_ai SET digest='eskirgan'"); con.commit(); con.close()
rs2 = docx_text(head.get(P + "/report.docx").content)
ok("tekshirilgan" not in rs2 and "kiritilmadi" in rs2, "Eskirgan xulosa (boshqa faktlar) hisobotga «tekshirilgan» deb tushmaydi")

print("== Demo ma'lumotni joriy haftaga surish (redate)")
import datetime as dt, shutil, tempfile
tmp = Path(tempfile.mkdtemp()) / "copy.db"
src = sqlite3.connect(DBP); dst = sqlite3.connect(tmp); src.backup(dst); src.close()
today = dt.date.fromisoformat(m["today"]); mon = today - dt.timedelta(days=today.weekday())
ok(dst.execute("SELECT v FROM dl_meta WHERE k='anchor'").fetchone()[0] == mon.isoformat(), "Langar (anchor) — joriy hafta dushanbasi")
ok(DLm.redate(dst, today) == 0, "Joriy haftada surish kerak emas (0)")
# 2 hafta oldin yaratilgan bazani taqlid qilish: demo qatorlar va langar 14 kun orqaga
dst.execute("UPDATE dl_activity SET week='~' || date(week,'-14 days'), last_login=strftime('%Y-%m-%dT%H:%M:%S', last_login, '-14 days') WHERE src='demo'")
dst.execute("UPDATE dl_activity SET week=substr(week,2) WHERE week LIKE '~%'")
dst.execute("UPDATE dl_items SET due=date(due,'-14 days') WHERE src!='import'")
dst.execute("UPDATE dl_meta SET v=? WHERE k='anchor'", ((mon - dt.timedelta(days=14)).isoformat(),))
sid0 = dst.execute("SELECT student_id FROM dl_activity LIMIT 1").fetchone()[0]
dst.execute("INSERT OR REPLACE INTO dl_activity VALUES(?,?,?,?,?,?,?,?,?,?,?)", (sid0, "2020-01-06", 1, 1, 1, 0, 0, 0, 0, "2020-01-07T10:00:00", "import"))
imp = dst.execute("SELECT id, due FROM dl_items WHERE src='import' LIMIT 1").fetchone()
dst.commit()
ok(dst.execute("SELECT MAX(week) FROM dl_activity WHERE src='demo'").fetchone()[0] == (mon - dt.timedelta(days=14)).isoformat(), "Taqlid: demo faollik 2 hafta eskirgan")
ok(DLm.redate(dst, today) == 2, "redate: 2 haftaga surildi")
ok(dst.execute("SELECT MAX(week) FROM dl_activity WHERE src='demo'").fetchone()[0] == mon.isoformat(), "Demo faollik yana joriy haftagacha")
ok(dst.execute("SELECT MAX(last_login) FROM dl_activity WHERE src='demo'").fetchone()[0] <= f"{today.isoformat()}T23:59:59", "Oxirgi kirish kelajakka o'tib ketmadi")
ok(dst.execute("SELECT week FROM dl_activity WHERE src='import' AND student_id=?", (sid0,)).fetchone()[0] == "2020-01-06", "Import qilingan faollikka tegilmadi")
ok(not imp or dst.execute("SELECT due FROM dl_items WHERE id=?", (imp[0],)).fetchone()[0] == imp[1], "Import qilingan material muddatiga tegilmadi")
ok(dst.execute("SELECT v FROM dl_meta WHERE k='anchor'").fetchone()[0] == mon.isoformat() and DLm.redate(dst, today) == 0, "Idempotent: ikkinchi chaqiruv — 0")
dst.execute("UPDATE dl_meta SET v=? WHERE k='anchor'", ((mon - dt.timedelta(days=21)).isoformat(),)); dst.execute("UPDATE dl_meta SET v='import' WHERE k='source'"); dst.commit()
ok(DLm.redate(dst, today) == 0, "Haqiqiy import bo'lgan bazada surilmaydi")
dst.close(); shutil.rmtree(tmp.parent, ignore_errors=True)
ok(head.get(P + "/template/activity.csv").text.lstrip("﻿").startswith("hemis_id;hafta"), "Import namunasi (CSV) yuklab olinadi")

print("\nNATIJA:", "HAMMASI O'TDI" if not fails else f"{len(fails)} TA XATO")
sys.exit(1 if fails else 0)
