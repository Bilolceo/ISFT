"""Talaba kabineti: «Mening darslarim», talaba Telegram ulanishi va eslatmani bot orqali yetkazish (app/talaba_darslar.py, docs/talaba-kabineti.md).

1. Ko'lam: talaba faqat o'z guruhi kurslarini ko'radi; tasdiqlanmagan (va boshlanmagan) darslar ko'rinmaydi; begona / yozilmagan kurs yoki
   tasdiqlanmagan dars ochilmaydi (404); boshqa talabaning ma'lumoti javobda yo'q; xodim cookie'si va kirishsiz — 401.
2. Kabinetdan ochish → launch (302, token) → statementlar → holat kabinetda va «Ortda qolganlar»da yangilanadi; resume (State API) yangi tokenda ham.
3. Telegram ulash: bir martalik kod (xesh, muddat, bitta ishlatish, cheklov), parol almashsa — ulanish uziladi.
4. Eslatma: launch havolasi/tokeni xabarda yo'q (kabinet havolasi); bot o'chiq — navbatda; soxta yuboruvchi bilan — yuborildi / xato / ulanmagan;
   cheklov (3 kunda bir marta); talaba ulanganda navbatdagilar yuboriladi; «Ortda qolganlar» ro'yxatida Telegram belgisi va yetkazish holati.
5. Brauzer (PW va CHROME berilganda): telefon kengligida kabinet sahifasi (tools/talaba_darslar_check.js, skrinshotlar — $TD_OUT).

Ishga tushirish: python tests/run_all.py --only talaba_darslar. DIQQAT: bazani o'zgartiradi (paket qatorlari, statementlar, xabarlar navbati).
"""
import json, os, re, shutil, sqlite3, subprocess, sys, time, uuid
from pathlib import Path
from urllib.parse import urlsplit, parse_qs
import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
B = os.environ.get("ISFT_TEST_URL", "http://127.0.0.1:8000")
DBP = Path(os.environ.get("ISFT_CORE_DB") or ROOT / "data" / "jarvis.db")
PW = re.search(r'DEMO_PASSWORD = os.getenv\("ISFT_CORE_DEMO_PASSWORD", "([^"]+)"\)', (ROOT / "app" / "rbac.py").read_text()).group(1)
SDEMO = os.getenv("ISFT_CORE_STUDENT_DEMO_PASSWORD", "Talaba2026")
NEWPW = "Darslar2026x"
fails = []
def ok(cond, msg):
    print(("  ✓ " if cond else "  ✗ ") + msg)
    if not cond: fails.append(msg)
def q(sql, a=()):
    con = sqlite3.connect(DBP, timeout=30); con.row_factory = sqlite3.Row
    try: return [dict(r) for r in con.execute(sql, a).fetchall()]
    finally: con.close()
def x(sql, a=()):
    con = sqlite3.connect(DBP, timeout=30)
    try: cur = con.execute(sql, a); con.commit(); return cur.lastrowid
    finally: con.close()
def uid(role):
    return q("SELECT id FROM users WHERE role=? AND COALESCE(active,1)=1 ORDER BY id LIMIT 1", (role,))[0]["id"]
def S(u):
    c = httpx.Client(base_url=B, timeout=300)
    r = c.post("/api/login", json={"user_id": u, "password": PW}); assert r.status_code == 200, f"login {u}: {r.text}"
    return c
def ST(sid):
    """Talaba sessiyasi (birinchi kirish — boshlang'ich parol, keyin majburiy almashtirish)."""
    h = q("SELECT hemis_id FROM students WHERE id=?", (sid,))[0]["hemis_id"]
    c = httpx.Client(base_url=B, timeout=120)
    r = c.post("/api/talaba/login", json={"hemis_id": h, "password": SDEMO})
    if r.status_code != 200: r = c.post("/api/talaba/login", json={"hemis_id": h, "password": NEWPW})
    assert r.status_code == 200, r.text
    if r.json().get("must_change"):
        assert c.post("/api/talaba/password", json={"current": SDEMO, "new": NEWPW}).status_code == 200
    return c

from app import lrs as L, talaba_darslar as TD
_con = sqlite3.connect(DBP, timeout=30, check_same_thread=False); _con.row_factory = sqlite3.Row
L._con = _con; L._KEY.clear()

co = q("SELECT * FROM dl_courses WHERE subject='Iqtisodiyot nazariyasi' AND direction='Iqtisodiyot' AND course=1")[0]
CID, CR = co["id"], f"dl:{co['id']}"
studs = [r["id"] for r in q("""SELECT s.id FROM students s JOIN groups_ g ON g.id=s.group_id WHERE s.study_form='masofaviy' AND s.status='faol'
                               AND g.form='masofaviy' AND g.direction=? AND g.course=? ORDER BY s.id""", (co["direction"], co["course"]))]
# test_lrs oxirgi ikkitasini ishlatadi (eslatma cheklovi) — bu yerda boshqalari; L14 bo'yicha progressi yo'q talaba
SA = next(s for s in studs[1:-2] if not q("SELECT 1 FROM lrs_progress WHERE student_id=? AND course_ref=? AND lesson_ref IN ('L1','L14')", (s, CR)))
SB = next(s for s in studs[1:-2] if s != SA)
other = q("""SELECT s.id FROM students s JOIN groups_ g ON g.id=s.group_id WHERE s.status='faol' AND (s.study_form!='masofaviy' OR g.direction!=?)
             AND s.id NOT IN (SELECT student_id FROM student_auth) ORDER BY s.id LIMIT 1""", (co["direction"],))[0]["id"]
other_co = q("SELECT id FROM dl_courses WHERE direction!=? ORDER BY id LIMIT 1", (co["direction"],))[0]["id"]
head = S(uid("masofaviy"))

# =============================================================================================
print("== 1. Paketlar: L1 tasdiqlangan (haqiqiy xAPI yig'ish), L14 — tasdiqlanmagan, boshqa yo'nalish kursi — tasdiqlangan")
P = "/api/paket"
vd = head.post(f"{P}/courses/{CID}/topics/1/video", json={"url": "https://youtu.be/dQw4w9WgXcQ"})
bd = head.post(f"{P}/courses/{CID}/topics/1/build", json={"mode": "xapi", "force": True})
ok(bd.status_code == 200 and bd.json().get("ok"), f"L1 xAPI paketi yig'ildi (video {vd.status_code}, yig'ish {bd.status_code} {bd.text[:150] if bd.status_code != 200 else ''})")
pk = bd.json()["package"]
if pk["status"] == "qoralama": head.post(f"{P}/packages/{pk['id']}/action", json={"action": "submit"})
ap = head.post(f"{P}/packages/{pk['id']}/action", json={"action": "approve"})
ok(ap.status_code == 200 and q("SELECT status FROM pk_packages WHERE id=?", (pk["id"],))[0]["status"] == "tasdiqlandi", f"L1 tasdiqlandi ({ap.status_code} {ap.text[:120]})")
row = q("SELECT * FROM pk_packages WHERE id=?", (pk["id"],))[0]
cols = [k for k in row if k != "id"]
def clone(course_id, topic_no, status):
    r = dict(row, course_id=course_id, topic_no=topic_no, status=status, version=900 + topic_no)
    return x(f"INSERT INTO pk_packages({','.join(cols)}) VALUES({','.join('?' * len(cols))})", [r[k] for k in cols])
clone(CID, 14, "tayyor")                       # L14 — bo'limga yuborilgan, lekin tasdiqlanmagan
clone(other_co, 1, "tasdiqlandi")              # boshqa yo'nalish kursi — tasdiqlangan, lekin SA yozilmagan

# =============================================================================================
print("== 2. Ko'lam: o'z kurslari, tasdiqlanmagan darslar yashirin, begona kurs/dars ochilmaydi")
anon = httpx.Client(base_url=B, timeout=60)
ok(anon.get("/api/talaba/darslar").status_code == 401 and anon.post("/api/talaba/darslar/launch", json={"course_ref": CR, "lesson": "L1"}).status_code == 401,
   "Kirishsiz — 401")
ok(head.get("/api/talaba/darslar").status_code == 401, "Xodim cookie'si talaba API'sida ishlamaydi (401)")
ca, cb, cc = ST(SA), ST(SB), ST(other)
da = ca.get("/api/talaba/darslar").json()
refs = {c["ref"] for c in da["courses"]}
ok(CR in refs and f"dl:{other_co}" not in refs, f"SA: o'z guruhi kurslari ({len(refs)} ta), boshqa yo'nalish kursi yo'q")
ca_co = next(c for c in da["courses"] if c["ref"] == CR)
codes = [l["code"] for l in ca_co["lessons"]]
ok("L1" in codes and next(l for l in ca_co["lessons"] if l["code"] == "L1")["can_open"], "L1 (tasdiqlangan) ro'yxatda va ochiladi")
ok("L14" not in codes, "L14 (tasdiqlanmagan, boshlanmagan) — ko'rinmaydi")
ls = [l for l in ca_co["lessons"] if l["code"][0] in "LA"]
order_ok = all(not (a["code"].startswith("A") and b["code"].startswith("L")) for a, b in zip(ls, ls[1:]))
ok(order_ok, "NEXTID tartibi: avval L (ma'ruza), keyin A (amaliy)")
ok(ca_co["total"] == 45 and ca_co["expected"] >= 0 and "next" in ca_co and da["total"]["lessons"] >= 45, f"Kurs: 45 dars, kutilgan {ca_co['expected']}, ortda {ca_co['lag']}")
ok(da["next"] and da["next"]["code"] == "L1", f"Keyingi tavsiya — ochiladigan birinchi bajarilmagan dars ({da['next'] and da['next']['code']})")
marks = {l["mark"] for l in ca_co["lessons"]}
ok(marks <= {"kechikkan", "bu_hafta", "keyinroq", None}, f"Taqvim belgilari: {sorted(m for m in marks if m)}")
sa_name = q("SELECT full_name, hemis_id FROM students WHERE id=?", (SA,))[0]
db_ = cb.get("/api/talaba/darslar").json()
ok(sa_name["full_name"] not in json.dumps(db_, ensure_ascii=False) and sa_name["hemis_id"] not in json.dumps(db_), "SB javobida SA'ning ismi va HEMIS ID'si yo'q")
ok(not "student_id" in json.dumps(da) and "learner" not in json.dumps(da), "Javobda talaba id / taxallus yo'q")
ok(ca.post("/api/talaba/darslar/launch", json={"course_ref": CR, "lesson": "L14"}).status_code == 404, "Tasdiqlanmagan L14 ni ochib bo'lmaydi (404)")
ok(ca.post("/api/talaba/darslar/launch", json={"course_ref": f"dl:{other_co}", "lesson": "L1"}).status_code == 404, "Yozilmagan kurs (tasdiqlangan bo'lsa ham) — 404")
ok(cc.post("/api/talaba/darslar/launch", json={"course_ref": CR, "lesson": "L1"}).status_code == 404 and not any(c["ref"] == CR for c in cc.get("/api/talaba/darslar").json()["courses"]),
   "Boshqa guruh talabasi bu kursni ko'rmaydi va ocholmaydi")
ok(ca.post("/api/talaba/darslar/launch", json={"course_ref": "ku:1", "lesson": "L1"}).status_code == 404 and ca.post("/api/talaba/darslar/launch", json={"course_ref": CR, "lesson": "Z1"}).status_code == 404,
   "Soxta kurs/dars kodi — 404")
ok(q("SELECT COUNT(*) n FROM audit_log WHERE action='talaba kabineti: darsni ochish' AND allowed=0")[0]["n"] >= 2, "Rad etilgan ochish urinishlari auditda")

# =============================================================================================
print("== 3. Kabinetdan ochish → statementlar → holat (kabinet va «Ortda qolganlar»), resume")
la = ca.post("/api/talaba/darslar/launch", json={"course_ref": CR, "lesson": "L1", "student_id": SB})
ok(la.status_code == 200 and la.json()["url"].startswith("/xapi/l/"), "Ochish — /xapi/l/<kod> (so'rovdagi student_id e'tiborsiz)")
pl = L.parse_link(la.json()["url"].rsplit("/", 1)[1])
ok(pl["student_id"] == SA and pl["course_ref"] == CR and pl["lesson_ref"] == "L1", "Havola — SA, shu kurs, shu dars")
import base64
exp = json.loads(base64.urlsafe_b64decode(la.json()["url"].rsplit("/", 1)[1].split(".")[0] + "=="))["e"]
ok(exp - time.time() <= 2 * 3600 + 5, "Kabinet havolasi qisqa muddatli (≤ 2 soat)")
def launch_params(url):
    rd = httpx.get(B + url, follow_redirects=False)
    return rd.status_code, {k: v[0] for k, v in parse_qs(urlsplit(rd.headers.get("location", "")).query).items()}
code, qp = launch_params(la.json()["url"])
ok(code == 302 and qp.get("auth", "").startswith("Basic ") and qp.get("activity_id") == L.lesson_activity(CR, "L1"), "302 → paket, xAPI launch parametrlari bilan")
H = lambda a: {"Authorization": a, "X-Experience-API-Version": "1.0.3", "Content-Type": "application/json"}
actor = json.loads(qp["actor"]); reg = qp["registration"]; act = qp["activity_id"]
def stmt(verb, **res):
    s = {"id": str(uuid.uuid4()), "actor": actor, "verb": {"id": L.VERB + verb}, "object": {"objectType": "Activity", "id": act},
         "context": {"registration": reg}}
    if res: s["result"] = res
    return s
r = httpx.post(B + "/xapi/statements", headers=H(qp["auth"]), json=[stmt("initialized"), stmt("progressed", extensions={L.PROGRESS_EXT: 50})])
ok(r.status_code == 200, f"Pleyer statementlari qabul qilindi ({r.status_code})")
st_q = {"activityId": act, "agent": json.dumps(actor), "stateId": "isft-state", "registration": reg}
ok(httpx.put(B + "/xapi/activities/state", params=st_q, headers=H(qp["auth"]), content=json.dumps({"slide": 4})).status_code == 204, "Resume holati saqlandi")
l1 = lambda c: next(l for co_ in c.get("/api/talaba/darslar").json()["courses"] if co_["ref"] == CR for l in co_["lessons"] if l["code"] == "L1")
v = l1(ca)
ok(v["status"] == "jarayonda" and v["pct"] == 50 and v["resume"], f"Kabinet: L1 — jarayonda 50 %, «Davom etish» ({v['status']} {v['pct']})")
la2 = ca.post("/api/talaba/darslar/launch", json={"course_ref": CR, "lesson": "L1"}).json()
code2, qp2 = launch_params(la2["url"])
gs = httpx.get(B + "/xapi/activities/state", params={**st_q, "registration": qp2["registration"]}, headers=H(qp2["auth"]))
ok(qp2["auth"] != qp["auth"] and qp2["registration"] == reg and gs.status_code == 200 and gs.json() == {"slide": 4}, "Qayta ochish: yangi token, o'sha registration — holat tiklandi")
r = httpx.post(B + "/xapi/statements", headers=H(qp2["auth"]),
               json=[stmt("passed", success=True, completion=True, score={"scaled": 0.8}), stmt("completed", completion=True)])
v = l1(ca)
ok(r.status_code == 200 and v["status"] == "otdi" and v["best"] == 80 and not v["resume"], f"Test o'tildi — kabinetda «O'tdi · 80 ball» ({v['status']} {v['best']})")
os_ = head.get(f"/api/ortda/student/{SA}", params={"course": CR}).json()
ok(next(l for l in os_["lessons"] if l["ref"] == "L1")["status"] == "otdi", "«Ortda qolganlar»: talaba darslarida L1 — o'tdi")
ok(l1(cb)["status"] != "otdi" or q("SELECT status FROM lrs_progress WHERE student_id=? AND course_ref=? AND lesson_ref='L1'", (SB, CR)), "SB holatiga SA natijasi ta'sir qilmaydi")
ok(httpx.post(B + "/xapi/statements", headers=H(qp2["auth"]), json=stmt("experienced") | {"object": {"objectType": "Activity", "id": L.lesson_activity(CR, "L14")}}).status_code == 403,
   "L1 tokeni bilan L14 ga yozib bo'lmaydi (403)")

print("== 3b. Tasdiq bekor qilinsa — ochish va fayllar to'xtaydi (410), tasdiqlanmagan versiyaga qaytish yo'q")
la3 = ca.post("/api/talaba/darslar/launch", json={"course_ref": CR, "lesson": "L1"}).json()["url"]
rd = httpx.get(B + la3, follow_redirects=False)
pbase = rd.headers["location"].split("?")[0].rsplit("/", 1)[0]
ok(rd.status_code == 302 and httpx.get(B + pbase + "/index.html").status_code == 200, "Ochiq sessiya: paket fayllari beriladi")
rj_ = head.post(f"{P}/packages/{pk['id']}/action", json={"action": "reject", "note": "Video almashtiriladi"})
ok(rj_.status_code == 200 and q("SELECT status FROM pk_packages WHERE id=?", (pk["id"],))[0]["status"] == "qoralama", "Bo'lim L1 paketini qaytardi (endi tasdiqlanmagan)")
g1 = httpx.get(B + pbase + "/index.html"); g2 = httpx.get(B + pbase + "/content.js")
ok(g1.status_code == 410 and g2.status_code == 410 and "tasdiqlangan holatda emas" in g1.text, "Allaqachon ochilgan sessiya: fayllar 410 (tasdiqlanmagan versiya berilmaydi)")
g3 = httpx.get(B + la3, follow_redirects=False)
ok(g3.status_code == 410 and "tasdiqlangan holatda emas" in g3.text, "2 soatlik kabinet havolasi endi ochilmaydi — 410, o'zbekcha xabar")
ok(ca.post("/api/talaba/darslar/launch", json={"course_ref": CR, "lesson": "L1"}).status_code == 404, "Kabinet: L1 ni yangidan ochib bo'lmaydi (404)")
v = l1(ca)
ok(v["can_open"] is False and v["status"] == "otdi", "Kabinetda L1 natijasi ko'rinadi, lekin «Ochish» yo'q")
ok(q("SELECT COUNT(*) n FROM audit_log WHERE action LIKE 'LRS: tasdiqlanmagan paketni ochish rad etildi%'")[0]["n"] >= 1, "Rad etish auditda")
v2 = head.post(f"{P}/courses/{CID}/topics/1/build", json={"mode": "xapi", "force": True}).json()["package"]       # yangi versiya — tasdiqlanmagan
x("UPDATE pk_packages SET status='tasdiqlandi' WHERE id=?", (pk["id"],))                                          # eski versiya qayta tasdiqlandi
ok(httpx.get(B + pbase + "/index.html").status_code == 200 and v2["id"] != pk["id"] and q("SELECT status FROM pk_packages WHERE id=?", (v2["id"],))[0]["status"] != "tasdiqlandi",
   "Qayta tasdiqlangach — fayllar yana beriladi (yangi tasdiqlanmagan v2 emas, tasdiqlangan versiya)")
x("UPDATE pk_packages SET status='qoralama' WHERE id=?", (pk["id"],))
ok(httpx.get(B + pbase + "/index.html").status_code == 410, "Tasdiqlangan versiya yo'q, faqat tasdiqlanmaganlar bor — 410 (fallback yo'q)")
x("UPDATE pk_packages SET status='tasdiqlandi' WHERE id=?", (pk["id"],))
# muharrir kursi: kabinet (strict) havolasi — kurs tasdiqlanmagan bo'lsa 410; xodim havolasi (strict emas) — avvalgidek
kc = head.post("/api/kurs/courses", json={"title": "Kabinet sinovi: muharrir kursi", "dl_course_id": CID}).json()["id"]
kl0 = head.get(f"/api/kurs/courses/{kc}").json()["lessons_list"][0]["id"]; KL = head.get(f"/api/kurs/lessons/{kl0}").json()
head.post(f"/api/kurs/lessons/{kl0}", json={"rev": KL["rev"], "title": "Kirish", "blocks": [{"type": "paragraph", "data": {"html": "<p>Matn</p>"}}]})
ok(head.post(f"/api/kurs/courses/{kc}/export", json={"mode": "xapi"}).status_code == 200, "Muharrir kursi eksport qilindi (tasdiqlanmagan)")
ks = L.make_link(SA, f"ku:{kc}", "", days=0.05, strict=True); kn = L.make_link(SA, f"ku:{kc}", "", days=0.05)
ok(httpx.get(B + "/xapi/l/" + ks, follow_redirects=False).status_code == 410 and httpx.get(B + "/xapi/l/" + kn, follow_redirects=False).status_code == 302,
   "Muharrir kursi: kabinet havolasi — 410 (tasdiqlanmagan), xodim havolasi — 302")

# =============================================================================================
print("== 4. Telegram ulash: bir martalik kod")
ok(TD.bot_enabled() is False, "Testda bot tokeni yo'q — yuborish o'chiq")
g0 = ca.get("/api/talaba/telegram").json()
ok(g0["linked"] is False and g0["bot"] is False, "Boshlang'ich holat: ulanmagan, bot o'chiq")
k1 = ca.post("/api/talaba/telegram/code").json()["code"]
ok(re.fullmatch(r"[A-Z2-9]{8}", k1) and not q("SELECT 1 FROM student_tg_codes WHERE code_hash=?", (k1,)) and q("SELECT 1 FROM student_tg_codes WHERE code_hash=?", (TD._h(k1),)),
   "Kod: 8 belgi, bazada faqat xesh")
TG_A, TG_B = 7770001, 7770002
ok(TD.link_student(_con, TG_A, "ZZZZZZZZ")["ok"] is False, "Noto'g'ri kod — rad")
k2 = ca.post("/api/talaba/telegram/code").json()["code"]
ok(TD.link_student(_con, TG_A, k1)["error"] == "noto'g'ri", "Yangi kod olinganda eskisi bekor qilinadi")
x("UPDATE student_tg_codes SET expires=? WHERE code_hash=?", (time.time() - 1, TD._h(k2)))
ok(TD.link_student(_con, TG_A, k2)["error"] == "muddati o'tgan", "Muddati o'tgan kod — rad")
k3 = ca.post("/api/talaba/telegram/code").json()["code"]
ok(TD.link_student(_con, TG_A, k3.lower())["ok"] is True, "To'g'ri kod (kichik harf bilan ham) — ulandi")
ok(TD.link_student(_con, TG_B, k3)["error"] == "ishlatilgan", "Kod ikkinchi marta ishlatilmaydi")
ok(ca.get("/api/talaba/telegram").json()["linked"] is True and TD.student_by_tg(_con, TG_A) == SA, "Kabinet: ulangan; bot taxallusdan talabani topadi")
codes_n = [ca.post("/api/talaba/telegram/code").status_code for _ in range(3)]
ok(codes_n[-1] == 429, f"Kod so'rash cheklovi — soatiga 5 ta ({codes_n})")

# =============================================================================================
print("== 5. Eslatma: yetkazish (bot o'chiq / soxta yuboruvchi), cheklov, navbat")
O = "/api/ortda"
rm = head.post(O + "/remind", json={"student_id": SA, "course_ref": CR, "channel": "telegram", "note": "L2 ni shu hafta tugating"})
ok(rm.status_code == 200, f"Eslatma yaratildi ({rm.status_code})")
rj = rm.json(); nt = q("SELECT * FROM ops_notices WHERE id=?", (rj["notice_id"],))[0]
ok("/xapi/" not in nt["text"] and "/talaba#darslarim" in nt["text"] and "L2 ni shu hafta tugating" in nt["text"], "Xabar: launch havolasi/tokeni yo'q, kabinet havolasi va shaxsiy izoh bor")
ok(rj["delivery"] == "bot_ochiq" and nt["status"] == "navbatda", "Bot o'chiq — xabar navbatda (bot_ochiq)")
ok(head.post(O + "/remind", json={"student_id": SA, "course_ref": CR}).status_code == 429, "3 kun ichida ikkinchi eslatma — 429")
sent = []
dv = TD.deliver(_con, rj["notice_id"], sender=lambda chat, text: sent.append((chat, text)))
nt = q("SELECT * FROM ops_notices WHERE id=?", (rj["notice_id"],))[0]
ok(dv["status"] == "yuborildi" and sent and sent[0][0] == TG_A and "darslarim" in sent[0][1] and nt["status"] == "yuborildi", "Soxta bot: yuborildi — talaba chat id'siga, holat «yuborildi»")
ok(TD.deliver(_con, rj["notice_id"], sender=lambda *a: sent.append(a))["status"] == "yuborildi" and len(sent) == 1, "Qayta chaqirish — ikkinchi marta yuborilmaydi")
dl = [r["status"] for r in q("SELECT status FROM notice_delivery WHERE notice_id=? ORDER BY id", (rj["notice_id"],))]
ok(dl == ["bot_ochiq", "yuborildi"], f"Yetkazish jurnali: {dl}")
ok("yuborildi" in q("SELECT note FROM lrs_actions WHERE notice_id=?", (rj["notice_id"],))[0]["note"].lower(), "lrs_actions izohida yetkazish holati")
# xato
nid_f = x("INSERT INTO ops_notices(ts,channel,student_id,text,status,user_id) VALUES(datetime('now'),'telegram',?,?,'navbatda',?)", (SA, "sinov", uid("masofaviy")))
def boom(*a): raise RuntimeError("Telegram HTTP 403")
ok(TD.deliver(_con, nid_f, sender=boom)["status"] == "xato" and q("SELECT status FROM ops_notices WHERE id=?", (nid_f,))[0]["status"] == "xato"
   and q("SELECT detail FROM notice_delivery WHERE notice_id=?", (nid_f,))[0]["detail"].startswith("Telegram HTTP 403"), "Yuborish xatosi — «xato», sababi jurnalda")
# ulanmagan
rb = head.post(O + "/remind", json={"student_id": SB, "course_ref": CR, "channel": "telegram"}).json()
ok(rb["delivery"] == "ulanmagan" and TD.deliver(_con, rb["notice_id"], sender=lambda *a: sent.append(a))["status"] == "ulanmagan" and len(sent) == 1,
   "Ulanmagan talaba — «Telegram ulanmagan», navbatda qoladi (yuborilmaydi)")
li = head.get(O + "/list", params={"course": CR, "only_risk": "false", "limit": 200}).json()["items"]
ia = next((i for i in li if i["student_id"] == SA), None); ib = next((i for i in li if i["student_id"] == SB), None)
ok(ia and ia["telegram"] is True and ia["actions"]["eslatma"]["delivery"] == "yuborildi" and ib and ib["telegram"] is False and ib["actions"]["eslatma"]["delivery"] == "ulanmagan",
   "«Ortda qolganlar» ro'yxati: Telegram belgisi va oxirgi eslatma holati")
ok(head.get(f"{O}/student/{SB}", params={"course": CR}).json()["student"]["telegram"] is False, "Talaba kartasida «Telegram ulanmagan»")
# SB ulanadi — navbatdagi eslatma yuboriladi
kb = cb.post("/api/talaba/telegram/code").json()["code"]
ok(TD.link_student(_con, TG_B, kb)["ok"], "SB ulandi")
got = []
ok(TD.flush_student(_con, SB, sender=lambda c, t: got.append(c)) == 1 and got == [TG_B] and q("SELECT status FROM ops_notices WHERE id=?", (rb["notice_id"],))[0]["status"] == "yuborildi",
   "Ulangandan keyin navbatdagi eslatma yuborildi")
# parol almashsa — ulanish uziladi
ok(ca.post("/api/talaba/password", json={"current": NEWPW, "new": NEWPW + "y"}).status_code == 200, "SA parolini almashtirdi")
ok(TD.student_by_tg(_con, TG_A) is None and ca.get("/api/talaba/telegram").json()["linked"] is False, "Parol almashgach Telegram ulanishi uzildi (qayta kod kerak)")
ok(cb.post("/api/talaba/telegram/unlink").json()["unlinked"] and TD.student_by_tg(_con, TG_B) is None, "Kabinetdan uzish")

# =============================================================================================
print("== 6. Statik fayllar va brauzer tekshiruvi")
node = shutil.which("node")
if node:
    ok(all(subprocess.run([node, "--check", str(ROOT / "static" / f)], capture_output=True).returncode == 0 for f in ("talaba.js", "talaba_darslar.js", "ortda.js")),
       "node --check: talaba.js, talaba_darslar.js, ortda.js")
ok(httpx.get(B + "/talaba_darslar.js").status_code == 200 and "talaba_darslar.js" in httpx.get(B + "/talaba").text, "Kabinet sahifasi kengaytmani yuklaydi")
if node and os.getenv("PW") and os.getenv("CHROME") and (ROOT / "tools" / "talaba_darslar_check.js").exists():
    hm = q("SELECT hemis_id FROM students WHERE id=?", (SB,))[0]["hemis_id"]
    env = dict(os.environ, ISFT_TEST_URL=B, TD_HEMIS=hm, TD_PASS=NEWPW, TD_OUT=os.getenv("TD_OUT") or str(Path(os.getenv("ISFT_CORE_DATA_DIR", "/tmp")) / "talaba_darslar_shots"))
    rr = subprocess.run([node, str(ROOT / "tools" / "talaba_darslar_check.js")], cwd=ROOT, env=env, capture_output=True, text=True, timeout=300)
    print(rr.stdout[-1500:], rr.stderr[-800:])
    ok(rr.returncode == 0, "Brauzer: telefon kengligida «Mening darslarim» (gorizontal aylantirishsiz, konsol xatosiz)")
else:
    print("  · brauzer tekshiruvi o'tkazildi (PW/CHROME berilmagan)")

print(f"\n{'XATO: ' + str(len(fails)) if fails else 'Hammasi o‘tdi'}")
sys.exit(1 if fails else 0)
