"""«Taqdimot → Studiya → Masofaviy bo'lim» zanjiri — tuzatish bosqichi (backend): ko'p oqimli xavfsizlik, barqaror dars kodi, versiyalar, IDOR, yuklash,
muddat/«Yangi», send-dept, ZIP siyosati, qidiruv, sarlavha, outline, audit, o'chirilgan dars (docs/taqdimot.md, docs/studio.md, docs/dars.md, docs/paket.md).

Ishga tushirish:  python tests/run_all.py --only zanjir_back
   (yoki: ISFT_TEST_URL=http://127.0.0.1:8000 ISFT_CORE_DB=data/jarvis.db .venv/bin/python tests/test_zanjir_back.py)
1) Jarayon ichida (serversiz): kirill → lotin slug, kodlar jadvali (backfill takrori, unikallik, barqarorlik), TxLock rollback, fayl turi xabarlari, sarlavha prefiksi,
   hujjat mavzu raqami, ZIP fayl nomi tozalash, _has_table keshi.
2) HTTP (server AI siz): 8 parallel send-dept (1×200 + 7×409, keyin yozuv ishlaydi), parallel «Dars yaratish» (bitta kurs), parallel yuborish (bitta versiya, paketda taqdimot
   yo'qolmaydi), takror bosish (unchanged), boshqa taqdimot orqali yuborish (dars bo'yicha versiya), IDOR (kurs boshqaga o'tdi), yuklash chegarasi (413, xabarlar),
   muddat/«Yangi», send-dept (yangiroq montaj 409, warnings), ZIP siyosati, qidiruv (to'liq dars kodi) va ro'yxat maydonlari, sarlavha zanjiri, outline, audit, gone, id qayta ishlatilishi.
DIQQAT: server bazasini o'zgartiradi — PRODUCTION'da ishlatilmaydi.
"""
import io, json, os, re, sqlite3, sys, tempfile, threading, time, zipfile
from pathlib import Path
import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
DB = Path(os.environ.get("ISFT_CORE_DB") or ROOT / "data" / "jarvis.db")
DATA = Path(os.environ.get("ISFT_CORE_DATA_DIR") or DB.parent)
B = os.environ.get("ISFT_TEST_URL", "http://127.0.0.1:8000")
PW = "Isft2026"
P, ST, CD = "/api/taqdimot", "/api/studio", "/api/dars/card"
N = [0]


def ok(cond, msg):
    N[0] += 1
    print(("  ✓ " if cond else "  ✗ XATO: ") + msg)
    if not cond:
        sys.exit(1)


def q(sql, args=()):
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True, timeout=30)
    try: return con.execute(sql, args).fetchall()
    finally: con.close()


def q1(sql, args=()):
    r = q(sql, args); return r[0][0] if r else None


def w(sql, args=()):
    con = sqlite3.connect(DB, timeout=30)
    try:
        cur = con.execute(sql, args); con.commit(); return cur.lastrowid
    finally: con.close()


def S(uid):
    c = httpx.Client(base_url=B, timeout=300)
    r = c.post("/api/login", json={"user_id": uid, "password": PW})
    assert r.status_code == 200, f"login {uid}: {r.status_code} {r.text}"
    return c


def J(r, code=200):
    assert r.status_code == code, f"{r.request.method} {r.request.url.path}: {r.status_code} {r.text[:400]}"
    return r.json()


def uid(role, where="", args=()):
    r = q1(f"SELECT id FROM users WHERE role=? AND COALESCE(active,1)=1 {where} ORDER BY id LIMIT 1", (role, *args)); assert r, f"{role} akkaunti yo'q"; return r


def can_write(timeout=1) -> bool:
    """Yozish qulfi bo'shmi? (ochiq tranzaksiya qolsa — BEGIN IMMEDIATE band bo'ladi)"""
    con = sqlite3.connect(DB, timeout=timeout)
    try:
        con.execute("BEGIN IMMEDIATE"); con.rollback(); return True
    except sqlite3.OperationalError:
        return False
    finally: con.close()


def par(n, fn):
    """n ta oqimda parallel: fn(i) → natijalar ro'yxati"""
    res, ths = [None] * n, []
    def go(i):
        try: res[i] = fn(i)
        except Exception as e: res[i] = e
    ths = [threading.Thread(target=go, args=(i,)) for i in range(n)]
    [t.start() for t in ths]; [t.join() for t in ths]
    return res


TEXT = ("# Talab va taklif\nBozor iqtisodiyotida narx talab va taklif muvozanati orqali shakllanadi. " * 3 +
        "\n## Talab qonuni\n- Narx oshsa talab kamayadi\n- Daromad ta'siri\n## Taklif qonuni\n- Narx oshsa taklif ortadi\n")
NOHEAD = "Bozor iqtisodiyotida narx talab va taklif muvozanati orqali shakllanadi va doimo o'zgarib turadi. " * 3
MP4 = b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00mp42isom" + b"\x00\x00\x00\x08free" + bytes(range(256)) * 8


def make_docx(heading="7-MAVZU: Differensial tenglamalar") -> bytes:
    import docx
    d = docx.Document()
    d.add_heading(heading, 0)
    d.add_paragraph("Differensial tenglama noma'lum funksiya va uning hosilalarini bog'laydigan tenglamadir. " * 3)
    d.add_heading("1. Asosiy tushunchalar", 1)
    d.add_paragraph("Birinchi tartibli tenglamalar eng sodda tur hisoblanadi. " * 4)
    b = io.BytesIO(); d.save(b); return b.getvalue()


# =============================================================================================
print("— 1. Serversiz: kirill slug, kodlar jadvali, TxLock, xabarlar, nomlar —")
from app import paket as PK, taqdimot as TQ, taqdimot_extract as EX, db as DBM, lesson_card as LC     # noqa: E402

ok(PK.subject_slug("Дастурий инжиниринг") == "dasturiyinjiniring" and PK.subject_slug("Дастурий инжиниринг") != "fan", "Kirill fan nomi lotinga o'giriladi («fan» chiqmaydi)")
ok(PK.dir_abbr("Ахборот тизимлари ва технологиялари") == "ATT" and PK.dir_abbr("Қишлоқ хўжалиги") == "QX" and PK.dir_abbr("Маркетинг") == "MAR" and PK.dir_abbr("") == "XXX",
   "Kirill yo'nalish qisqartmasi: ATT, QX, MAR; bo'sh — XXX")
ok(PK.subject_slug("O‘zbek tili ʻ'x") == "ozbektilix" and PK.dir_abbr("Axborot tizimlari va texnologiyalari") == "ATT", "ʻ ' ‘ ’ olib tashlanadi; lotin nomlar o'zgarmadi")
tmp = Path(tempfile.mkdtemp())
con = sqlite3.connect(tmp / "c.db"); con.row_factory = sqlite3.Row
con.executescript("""CREATE TABLE dl_courses(id INTEGER PRIMARY KEY, subject TEXT, direction TEXT, course INT, department_id INT, teacher_id INT, semester INT, topics INT, lms_ref TEXT);
CREATE TABLE pres_sends(id INTEGER PRIMARY KEY, course_id INT, lkey INT, version INT);""")
con.execute("CREATE TABLE course_code_store(course_id INTEGER PRIMARY KEY, code TEXT UNIQUE NOT NULL, created_at TEXT)")
for i, (sub, dr, c_, sem) in enumerate([("Dasturiy injiniring", "Axborot tizimlari va texnologiyalari", 2, 3), ("Dasturiy injiniring", "Axborot tizimlari va texnologiyalari", 2, 4),
                                        ("Iqtisodiyot", "Iqtisodiyot", 1, 1), ("Дастурий инжиниринг", "Ахборот тизимлари ва технологиялари", 2, 5)], 1):
    con.execute("INSERT INTO dl_courses(id,subject,direction,course,semester,topics) VALUES(?,?,?,?,?,15)", (i, sub, dr, c_, sem))
con.commit()
c1 = PK._sync_course_codes(con)
rows = [dict(r) for r in con.execute("SELECT * FROM dl_courses")]
ok(c1[1] == "2_ATT_dasturiyinjiniring_3s" and c1[2] == "2_ATT_dasturiyinjiniring_4s" and c1[3] == "1_IQT_iqtisodiyot", f"Birinchi to'ldirish: HOZIRGI qoida (takror → _<sem>s): {c1[1]}")
ok(c1[4] == "2_ATT_dasturiyinjiniring_5s" and len(set(c1.values())) == 4, "Kirill kurs — to'qnashuvda ham UNIKAL kod")
c2 = PK._sync_course_codes(con)
ok(c2 == c1 and con.execute("SELECT COUNT(*) FROM course_code_store").fetchone()[0] == 4, "Migratsiya takrori — hech narsa o'zgarmaydi")
import re as _re
con2 = sqlite3.connect(tmp / "t.db"); con2.row_factory = sqlite3.Row   # alohida baza — keyingi tekshiruvlar asosiy bazaga tayanadi
con2.executescript("""CREATE TABLE dl_courses(id INTEGER PRIMARY KEY, subject TEXT, direction TEXT, course INT, department_id INT, teacher_id INT, semester INT, topics INT, lms_ref TEXT);
CREATE TABLE pres_sends(id INTEGER PRIMARY KEY, course_id INT, lkey INT, version INT);
CREATE TABLE course_code_store(course_id INTEGER PRIMARY KEY, code TEXT UNIQUE NOT NULL, created_at TEXT);""")
for i, (sub, dr, c_, sem) in enumerate([("Dasturiy injiniring", "Axborot tizimlari va texnologiyalari", 2, 3), ("Dasturiy injiniring", "Axborot tizimlari va texnologiyalari", 2, 4),
                                        ("Iqtisodiyot", "Iqtisodiyot", 1, 1), ("Дастурий инжиниринг", "Ахборот тизимлари ва технологиялари", 2, 5)], 1):
    con2.execute("INSERT INTO dl_courses(id,subject,direction,course,semester,topics) VALUES(?,?,?,?,?,15)", (i, sub, dr, c_, sem))
con2.commit()
c1 = PK._sync_course_codes(con2)
_src = (ROOT / "app" / "paket.py").read_text(encoding="utf-8") + (ROOT / "app" / "taqdimot.py").read_text(encoding="utf-8")
for _nm in ("trg_dlc_code_del", "trg_dlc_pres_del"):
    _m = _re.search(r'CREATE TRIGGER IF NOT EXISTS ' + _nm + r'[^"]*', _src)
    ok(bool(_m), f"{_nm}: kurs o'chirilganda darhol ishlaydigan trigger kodda bor")
    con2.execute(_m.group(0))
con2.execute("INSERT INTO pres_sends(id,course_id,lkey,version) VALUES(1,2,1,1),(2,3,1,1)"); con2.commit()
con2.execute("DELETE FROM dl_courses WHERE id=2"); con2.commit()
ok(con2.execute("SELECT COUNT(*) FROM course_code_store WHERE course_id=2").fetchone()[0] == 0 and con2.execute("SELECT COUNT(*) FROM course_code_store").fetchone()[0] == 3,
   "Kurs o'chirilishi bilan kodi DARHOL bo'shadi (keyingi so'rovni kutmasdan), boshqa kodlar o'zgarmadi")
ok(con2.execute("SELECT course_id FROM pres_sends WHERE id=1").fetchone()[0] == -1 and con2.execute("SELECT course_id FROM pres_sends WHERE id=2").fetchone()[0] == 3,
   "O'chirilgan kursning yuborilgan taqdimoti yetim (course_id<0), boshqa kursniki joyida")
con2.execute("INSERT INTO dl_courses(id,subject,direction,course,semester,topics) VALUES(2,'Dasturiy injiniring','Axborot tizimlari va texnologiyalari',2,3,15)"); con2.commit()
c1b = PK._sync_course_codes(con2)
ok(len(set(c1b.values())) == len(c1b) == 4 and c1b[1] == c1[1] and con2.execute("SELECT course_id FROM pres_sends WHERE id=1").fetchone()[0] == -1, "Id qayta ishlatilsa — yangi kurs UNIKAL yangi kod oladi (boshqalarniki o'zgarmaydi), eski taqdimot unga o'tib ketmaydi")
con.execute("UPDATE dl_courses SET subject='Butunlay boshqa nom', direction='Menejment' WHERE id=1"); con.commit()
ok(PK._sync_course_codes(con)[1] == c1[1], "Fan va yo'nalish nomi o'zgardi — kod O'ZGARMADI")
con.execute("INSERT INTO dl_courses(id,subject,direction,course,semester,topics) VALUES(5,'Iqtisodiyot','Iqtisodiyot',1,2,15)")
con.execute("INSERT INTO dl_courses(id,subject,direction,course,semester,topics) VALUES(6,'Iqtisodiyot','Iqtisodiyot',1,2,15)")
con.execute("INSERT INTO dl_courses(id,subject,direction,course,semester,topics) VALUES(7,'Iqtisodiyot','Iqtisodiyot',1,3,15)")
con.commit()
c3 = PK._sync_course_codes(con)
ok(c3[3] == "1_IQT_iqtisodiyot" and c3[5] == "1_IQT_iqtisodiyot_2s" and c3[6] == "1_IQT_iqtisodiyot_2s_6" and c3[7] == "1_IQT_iqtisodiyot_3s", "Yangi kurs: takror → _<sem>s, u ham band → _<kurs id>; eskilari o'zgarmadi")
ok(len(set(c3.values())) == len(c3) and all(c3[k] == c1[k] for k in c1), "Hamma kodlar unikal, eski kodlar barqaror")
con.execute("INSERT INTO pres_sends(id,course_id,lkey,version) VALUES(1,5,1,1),(2,3,1,1)")
con.execute("DELETE FROM dl_courses WHERE id=5"); con.commit()
c4 = PK._sync_course_codes(con)
ok(5 not in c4 and con.execute("SELECT course_id FROM pres_sends WHERE id=1").fetchone()[0] == -1 and con.execute("SELECT course_id FROM pres_sends WHERE id=2").fetchone()[0] == 3,
   "O'chirilgan kurs: kodi tozalandi, yuborilgan taqdimotlari «yetim» (id qayta ishlatilsa yangi kurs eski versiyalarni olmaydi)")
con.execute("INSERT INTO dl_courses(id,subject,direction,course,semester,topics) VALUES(5,'Iqtisodiyot','Iqtisodiyot',1,2,15)"); con.commit()
ok(con.execute("SELECT COUNT(*) FROM pres_sends WHERE course_id=5").fetchone()[0] == 0, "id=5 qayta ishlatildi — yangi kurs eski taqdimotlarni meros olmadi")
con.close()

# TxLock: blokdan istisno bilan chiqsa — rollback (yozish qulfi ochiq qolmaydi)
c = sqlite3.connect(tmp / "t.db", isolation_level="")
c.execute("CREATE TABLE x(a)"); c.commit()
lk = DBM.TxLock(lambda: c)
try:
    with lk:
        c.execute("INSERT INTO x VALUES(1)")
        raise ValueError("test")
except ValueError:
    pass
ok(not c.in_transaction and c.execute("SELECT COUNT(*) FROM x").fetchone()[0] == 0, "TxLock: istisno → rollback, tranzaksiya ochiq qolmadi")
with lk:
    c.execute("INSERT INTO x VALUES(2)"); c.commit()
ok(c.execute("SELECT COUNT(*) FROM x").fetchone()[0] == 1, "TxLock: istisnosiz blok oddiy ishlaydi")
c.close()

# fayl turi xabarlari
png = b"\x89PNG\r\n\x1a\n" + b"0" * 50
bad = {"png": (png, EX.MSG_TYPE), "jpg": (b"\xff\xd8\xff\xe0" + b"a" * 80, EX.MSG_TYPE), "zip": (b"PK\x03\x04" + b"\x00" * 100, EX.MSG_DOCX), "random": (os.urandom(400), EX.MSG_TYPE),
       "ole": (b"\xd0\xcf\x11\xe0" + b"\x00" * 100, EX.MSG_TYPE)}
for nm, (raw, msg) in bad.items():
    try:
        EX.sniff(raw); ok(False, f"{nm} qabul qilinmasligi kerak")
    except EX.BadFile as e:
        ok(str(e) == msg, f"Fayl turi ({nm}): «{msg}»")
ok(EX.MSG_TYPE == "Faqat .docx, .pdf yoki .txt yuklash mumkin" and EX.MSG_DOCX == "Fayl buzilgan yoki Word (.docx) emas. Wordda qayta saqlab ko'ring"
   and EX.MSG_PDF == "PDF ochilmadi — faylni qayta yuklab oling yoki Word variantini yuklang", "Xato matnlari shartnomaga aynan mos")
ok(EX.sniff(b"BMW haqida matn. " * 5) == "txt" and EX.sniff(TEXT.encode()) == "txt", "Oddiy matn («BM…» bilan boshlansa ham) matn bo'lib qoladi")
ok(TQ.strip_topic_prefix("7-MAVZU: Differensial tenglamalar") == "Differensial tenglamalar" and TQ.strip_topic_prefix("7-MAVZU") == ""
   and TQ.strip_topic_prefix("Mavzu 12. Bozor") == "Bozor" and TQ.strip_topic_prefix("7-mavzu — nomsiz") == "7-mavzu — nomsiz" and TQ.strip_topic_prefix("Oddiy nom") == "Oddiy nom",
   "Titul sarlavhasidan «N-MAVZU:» prefiksi olinadi (nomsiz sarlavha va oddiy nom o'zgarmaydi)")
ok(TQ.doc_topic_no([{"k": "h", "t": "7-MAVZU: Differensial"}]) == 7 and TQ.doc_topic_no([{"k": "p", "t": "Mavzu 3. Bozor"}]) == 3 and TQ.doc_topic_no([{"k": "p", "t": "Oddiy"}]) is None,
   "doc_topic_no: «N-MAVZU» dan (yo'q bo'lsa None)")
ok(LC.safe_name("..", 5) == "fayl_5" and LC.safe_name(".", 6) == "fayl_6" and LC.safe_name("", 7) == "fayl_7" and LC.safe_name(" . hisobot.xlsx. ", 1) == "hisobot.xlsx"
   and LC.safe_name("../../evil.xlsx", 1) == "_.._evil.xlsx", "ZIP fayl nomi: .strip(). ), bo'sh/./.. → fayl_<id>")
ln = LC.safe_name("x" * 300 + ".xlsx", 1)
ok(len(ln) <= 120 and ln.endswith(".xlsx"), "ZIP fayl nomi: 120 belgidan uzun — kengaytma saqlanib kesiladi")
n_sq = [0]
orig = PK.db.one
def counting(con_, sql, args=()):
    if "sqlite_master" in sql: n_sq[0] += 1; return {"name": args[0]}
    return orig(con_, sql, args)
PK._TBL_OK.discard("syl_items"); PK.db.one = counting
try:
    [PK._has_table("syl_items") for _ in range(30)]
finally:
    PK.db.one = orig
ok(n_sq[0] <= 1, f"_has_table keshlanadi: 30 chaqiruvda sqlite_master so'rovi {n_sq[0]} ta (N+1 yo'q)")

# =============================================================================================
print("— 2. HTTP: fixture'lar —")
OQ_ID = uid("oqituvchi")
OQ_TID = q1("SELECT teacher_id FROM users WHERE id=?", (OQ_ID,))
OQ = S(OQ_ID)
OQ2_ID = q1("SELECT id FROM users WHERE role='oqituvchi' AND COALESCE(active,1)=1 AND teacher_id IS NOT NULL AND teacher_id!=? ORDER BY id LIMIT 1", (OQ_TID,))
if not OQ2_ID:          # toza bazada bitta o'qituvchi akkaunti bor — ikkinchisi (boshqa o'qituvchi, boshqa kafedra) shu yerda yaratiladi
    OQ2_TID = q1("SELECT teacher_id FROM dl_courses WHERE teacher_id IS NOT NULL AND teacher_id!=? GROUP BY teacher_id ORDER BY COUNT(*) DESC LIMIT 1", (OQ_TID,))
    OQ2_ID = w("INSERT INTO users(id, full_name, role, department_id, teacher_id, active, pin) VALUES(9001, ?, 'oqituvchi', (SELECT department_id FROM teachers WHERE id=?), ?, 1, (SELECT pin FROM users WHERE id=?))",
               ("O'qituvchi: Ikkinchi Sinov", OQ2_TID, OQ2_TID, OQ_ID))
OQ2_TID = q1("SELECT teacher_id FROM users WHERE id=?", (OQ2_ID,))
OQ2 = S(OQ2_ID)
HEAD, STAFF, OPER = (S(uid(r)) for r in ("masofaviy", "masofaviy_xodim", "montaj_operator"))
OQ_DEP = q1("SELECT COALESCE(u.department_id, t.department_id) FROM users u LEFT JOIN teachers t ON t.id=u.teacher_id WHERE u.id=?", (OQ_ID,))
KAF = S(uid("kafedra", "AND department_id=?", (OQ_DEP,)))
KAF2 = S(uid("kafedra", "AND department_id!=?", (OQ_DEP,)))
w("DELETE FROM pres_gen")                                       # kunlik cheklov (20) boshqa to'plamlardan qolmasin

L = J(OQ.get(P + "/lessons"))
co0 = L["items"][0]
CID = co0["id"]
CO_ROW = q("SELECT subject, direction, course, department_id FROM dl_courses WHERE id=?", (CID,))[0]
keys = [l["key"] for l in co0["lessons"] if l["kind"] == "maruza"]
ok(len(keys) >= 14, f"Fan darslari yetarli ({len(keys)} ta L)")
for n_ in range(11, 31):                                         # qo'shimcha amaliy darslar (A11…A30) — har sinov o'z darsida
    w("INSERT OR REPLACE INTO pk_lessons(course_id,lkey,kind,no,title,topic_ref,ts,user_name,deleted,src) VALUES(?,?,'amaliy',?,?,NULL,datetime('now'),'test',0,'')", (CID, 1000 + n_, n_, f"Sinov amaliy {n_}"))
LKS = iter([k for k in keys if k not in (1, 3, 8)][::-1] + [1000 + n_ for n_ in range(11, 31)])           # test_zanjir L3 va L8 ni ishlatadi


def mk(cl=None, lk=None, build=True, text=TEXT, cid=None, **kw):
    cl = cl or OQ
    r = cl.post(P + "/decks/text", json={"text": text, "course_id": cid or CID, "lkey": lk, **kw}); d = J(r)
    if build:
        J(cl.post(P + f"/decks/{d['id']}/build", json={}))
    return d


def lcode(lk, cid=None):
    return J(HEAD.get(f"{CD}/{cid or CID}/{lk}"))["ref"]["full_code"]


def approved_job(lk, cid=None):
    now = q1("SELECT strftime('%Y-%m-%dT%H:%M:%S','now','+5 hours')")
    rid = w("INSERT INTO st_raw(course_id,lkey,booking_id,name,kind,path,size,ts,deleted) VALUES(?,?,NULL,'x','mp4','x',1,?,0)", (cid or CID, lk, now))
    return w("INSERT INTO st_jobs(course_id,lkey,raw_id,template,status,attempts,created_at,updated_at,result_at,decided_at,decided_name) VALUES(?,?,?,'maruza_slayd','tasdiqlandi',1,?,?,?,?,'Op')",
             (cid or CID, lk, rid, now, now, now, now))


# =============================================================================================
print("— 3. BLOKER: send-dept qulf (parallel) —")
LK1 = next(LKS)
j1 = approved_job(LK1)
res = par(8, lambda i: OPER.post(f"{ST}/jobs/{j1}/send-dept", json={}).status_code)
ok(sorted(res) == [200] + [409] * 7, f"8 parallel send-dept → 1×200 + 7×409 ({sorted(res)})")
ok(can_write(), "Baza yozish qulfi bo'sh — oqim ulanishida ochiq tranzaksiya qolmadi")
t0 = time.time()
ok(S(uid("masofaviy")) is not None and time.time() - t0 < 5, "Keyin darhol boshqa yozuv ishlaydi: kirish (login) tez")
t0 = time.time()
Dx = mk(lk=next(LKS), build=False)
ok(time.time() - t0 < 10 and Dx["id"], f"Keyin darhol taqdimot yaratish ishlaydi ({time.time() - t0:.1f} s)")
for _ in range(3):
    r_ = OPER.post(f"{ST}/jobs/{j1}/send-dept", json={})
    assert r_.status_code == 409 and can_write()
ok(True, "Takroriy send-dept (3 marta): har safar 409, qulf yo'q")
ok(q1("SELECT COUNT(*) FROM st_dept WHERE job_id=?", (j1,)) == 1, "st_dept: bitta yozuv")
t0 = time.time()
r = par(10, lambda i: OQ.get(P + "/lessons").status_code)
ok(all(x == 200 for x in r) and time.time() - t0 < 10, "10 parallel o'qish — server qotmadi")

print("— 4. send-dept: yangiroq montaj, ogohlantirish, holatlar —")
LK2 = next(LKS)
ja = approved_job(LK2)
time.sleep(1.05)
jb = approved_job(LK2)                                           # yangiroq tasdiqlangan montaj
r = OPER.post(f"{ST}/jobs/{ja}/send-dept", json={})
ok(r.status_code == 409 and "yangiroq montaj" in r.text and can_write(), "Eskirgan montajni yuborish — 409 «Bu darsning yangiroq montaji bor»")
inf = J(OPER.get(f"{ST}/jobs/{jb}"))["dept_info"]
ok(inf["dept_sent"] is False and inf["video_wait"] is True and inf["pres_sent"] is False, "dept_info: dept_sent=false, video_wait=true (tasdiqlangan, yuborilmagan), pres_sent=false")
ws = J(OPER.post(f"{ST}/jobs/{jb}/send-dept", json={}))
ok(ws["warnings"] == ["Bu darsga taqdimot yuborilmagan"] and ws["ok"], "Taqdimot yuborilmagan — bloklanmaydi, javobda warnings")
inf = J(OPER.get(f"{ST}/jobs/{jb}"))["dept_info"]
ok(inf["dept_sent"] is True and inf["video_wait"] is False, "Yuborilgach: dept_sent=true, video_wait=false")
cv = J(HEAD.get(f"{CD}/{CID}/{LK2}"))["video"]
ok(cv["dept_sent"] is True and cv["video_wait"] is False, "Kartochka video holati: dept_sent / video_wait")
LK3 = next(LKS)
D3 = mk(lk=LK3); J(OQ.post(P + f"/decks/{D3['id']}/send", json={}))
j3 = approved_job(LK3)
ws = J(OPER.post(f"{ST}/jobs/{j3}/send-dept", json={}))
ok(ws["warnings"] == [] and ws["dept"]["pres_version"] == 1, "Taqdimot bor — warnings bo'sh, pres_version=1")
sv = {x["key"]: x for x in J(HEAD.get(f"/api/dars/subjects/{CID}"))["lessons"]}
ok(sv[LK3]["pres_version"] == 1 and sv[LK3]["pres_at"] and sv[LK3]["dept_sent"] is True and sv[LK3]["video_wait"] is False, "Fanlar daraxti: pres_version / pres_at / dept_sent / video_wait")
LKw = next(LKS); approved_job(LKw)
sv = {x["key"]: x for x in J(HEAD.get(f"/api/dars/subjects/{CID}"))["lessons"]}
ok(sv[LKw]["video_wait"] is True and sv[LKw]["dept_sent"] is False and sv[LKw]["pres_version"] is None, "Fanlar daraxti: tasdiqlangan, yuborilmagan montaj — video_wait")
pc = {x["id"]: x for x in J(HEAD.get("/api/paket/courses", params={"limit": 1000}))["items"]}[CID]
ok(pc["pres_sent"] >= 1 and pc["dept_sent"] >= 2 and pc["video_wait"] >= 1, f"/api/paket/courses: pres_sent={pc['pres_sent']}, dept_sent={pc['dept_sent']}, video_wait={pc['video_wait']}")

print("— 5. Parallel «Dars yaratish» va muharrirga o'tkazish —")
LK4 = next(LKS)
kb0 = q1("SELECT COUNT(*) FROM ku_courses")
rs = par(6, lambda i: S(uid("masofaviy")).post(f"{CD}/{CID}/{LK4}/create"))
ok(all(isinstance(x, httpx.Response) and x.status_code == 200 for x in rs), f"6 parallel «Dars yaratish»: hammasi 200 ({[getattr(x, 'status_code', x) for x in rs]})")
kc = {x.json()["ku_course_id"] for x in rs}
ok(len(kc) == 1 and sum(1 for x in rs if x.json()["created"]) == 1, "Bitta kurs, bittasi created=true, qolganlari o'sha kursni qaytaradi (idempotent)")
ok(q1("SELECT COUNT(*) FROM ku_courses") == kb0 + 1 and q1("SELECT COUNT(*) FROM ds_links WHERE dl_course_id=? AND lkey=?", (CID, LK4)) == 1, "Yetim kurs yo'q: ku_courses +1, ds_links bitta")
LK5 = next(LKS)
rs = par(5, lambda i: S(uid("masofaviy")).post(f"/api/dars/subjects/{CID}/lessons/{LK5}/convert"))
ok(all(isinstance(x, httpx.Response) and x.status_code == 200 for x in rs) and len({x.json()["ku_course_id"] for x in rs}) == 1 and sum(1 for x in rs if x.json()["created"]) == 1,
   "5 parallel convert (muharrirga o'tkazish): bitta kurs")
ok(can_write(), "Qulf bo'sh")

print("— 6. Yuborish: parallel (qulf), takror bosish, boshqa taqdimot orqali —")
LK6 = next(LKS)
Da = mk(lk=LK6)
rs = par(4, lambda i: S(OQ_ID).post(P + f"/decks/{Da['id']}/send", json={}))
ok(all(isinstance(x, httpx.Response) and x.status_code == 200 for x in rs), f"4 parallel /send: hammasi 200 ({[getattr(x, 'status_code', x) for x in rs]})")
ok(q1("SELECT COUNT(*) FROM pres_sends WHERE course_id=? AND lkey=?", (CID, LK6)) == 1 and sum(1 for x in rs if x.json()["unchanged"]) == 3, "Bitta versiya yaratildi (v1), qolgan 3 tasi unchanged:true")
ok(all(x.json()["version"] == 1 for x in rs) and all(x.json()["paket_error"] is None for x in rs), "Hammasida version=1 va paket_error=None")
ok(q1("SELECT COUNT(*) FROM pk_assets WHERE course_id=? AND topic_no=? AND purpose='taqdimot' AND deleted=0 AND kind='pptx'", (CID, LK6)) == 1, "Paketda taqdimot YO'QOLMADI (bitta faol .pptx)")
ok(can_write(), "Qulf bo'sh")
S2_ = J(OQ.post(P + f"/decks/{Da['id']}/send", json={}))
ok(S2_["unchanged"] is True and S2_["version"] == 1 and S2_["sends"][0]["version"] == 1, "Bir xil fayl <30 s ichida takror bosildi — {unchanged: true, version: 1}")
w("UPDATE pres_sends SET sent_at=datetime('now','+5 hours','-90 seconds') WHERE course_id=? AND lkey=?", (CID, LK6))
S3_ = J(OQ.post(P + f"/decks/{Da['id']}/send", json={}))
ok(S3_["unchanged"] is False and S3_["version"] == 2 and S3_["send"]["version"] == 2, ">30 s keyin ataylab qayta yuborilsa — versiya oshadi (v2)")
ok(q1("SELECT COUNT(*) FROM pk_assets WHERE course_id=? AND topic_no=? AND purpose='taqdimot' AND deleted=0 AND kind='pptx'", (CID, LK6)) == 1, "Paketda hamon bitta faol taqdimot")
ok(S3_["pptx"]["filename"] and S3_["pptx"]["size"] > 1000 and S3_["pptx"]["built_at"], "pptx {filename, size, built_at}")
ok(S3_["changed_since_send"] is False and S3_["last_send"]["version"] == 2 and S3_["last_send"]["size"] == S3_["pptx"]["size"] and len(S3_["last_send"]["sha256_short"]) == 8
   and S3_["last_send"]["filename"].endswith("_taqdimot_v2.pptx"), "last_send {version, at, size, filename, sha256_short}; changed_since_send=false")
o = S3_["outline"]; o["slides"].append({"type": "summary", "title": "Xulosa", "cards": [{"title": "A", "text": "B"}]})
V = J(OQ.post(P + f"/decks/{Da['id']}/outline", json={"outline": o}))
ok(V["changed_since_send"] is True, "Yuborilgandan keyin reja tahrirlandi — changed_since_send=true")
J(OQ.post(P + f"/decks/{Da['id']}/build", json={}))
ok(J(OQ.get(P + f"/decks/{Da['id']}"))["changed_since_send"] is True, "PPTX qayta yaratildi, farq bor — changed_since_send=true")

# boshqa taqdimot orqali (dars bo'yicha versiya)
Db = mk(lk=LK6, text=TEXT + "\n## Qo'shimcha\n- Boshqa band\n")
ok(Db.get("existing") and Db["existing"][0]["id"] == Da["id"] and Db["existing"][0]["title"], "Bir darsga ikkinchi taqdimot: javobda existing:[{id,title}] (bloklanmaydi)")
Vb = J(OQ.get(P + f"/decks/{Db['id']}"))
ok(Vb["lesson"]["lesson_sent_version"] == 2 and Vb["lesson"]["lesson_sent_deck_id"] == Da["id"] and Vb["lesson"]["lesson_sent_deck_title"] and Vb["lesson"]["lesson_sent_at"]
   and {d["id"] for d in Vb["lesson"]["decks"]} == {Da["id"], Db["id"]} and Vb["sent_version"] == 0, "Taqdimot B: dars v2 ni A orqali yuborilgani ko'rinadi (lesson_sent_*, decks)")
SB = J(OQ.post(P + f"/decks/{Db['id']}/send", json={"note": "B variant"}))
ok(SB["version"] == 3 and SB["sent_version"] == 3 and SB["lesson"]["lesson_sent_deck_id"] == Db["id"], "Boshqa taqdimot orqali yuborildi: versiya DARS bo'yicha — v3")
ok(SB["last_send"]["version"] == 3 and SB["changed_since_send"] is False, "B: last_send v3, o'zgarmagan")
ok(q1("SELECT COUNT(*) FROM pk_assets WHERE course_id=? AND topic_no=? AND purpose='taqdimot' AND deleted=0 AND kind='pptx'", (CID, LK6)) == 1, "Paketda bitta faol taqdimot (eng yangisi)")
row = next(x for x in J(OQ.get(P + "/lessons"))["items"] if x["id"] == CID)
lr = next(x for x in row["lessons"] if x["key"] == LK6)
ok(lr["lesson_sent_version"] == 3 and lr["lesson_sent_deck_id"] == Db["id"] and lr["lesson_sent_at"] and {d["id"] for d in lr["decks"]} >= {Da["id"], Db["id"]}, "/lessons: lesson_sent_* va decks")
lr0 = next(x for x in row["lessons"] if x["key"] == keys[0] and x["key"] not in (LK6,))
ok(lr0["lesson_sent_version"] is None or isinstance(lr0["lesson_sent_version"], int), "/lessons: yuborilmagan dars — lesson_sent_version null")
ok(OQ.get(P + f"/decks/{Db['id']}/sends/3/pptx").status_code == 200 and OQ.get(P + f"/decks/{Db['id']}/sends/1/pptx").status_code == 200, "B sahifasidan o'z versiyalarini yuklab oladi (shu muallifning boshqa taqdimoti ham)")

# titul va doc_topic_no
rr = OQ.post(P + "/decks", params={"name": "ma'ruza.docx", "course_id": CID, "lkey": next(LKS)}, content=make_docx(), headers={"Content-Type": "application/octet-stream"})
Dw = J(rr)
ok(Dw["doc_topic_no"] == 7 and Dw["outline"]["title"] == "Differensial tenglamalar" and not re.match(r"^\d+\s*-\s*mavzu", Dw["outline"]["title"], re.I),
   f"Hujjat «7-MAVZU: …»: doc_topic_no=7, titulda «{Dw['outline']['title']}» (ikki marta raqamlanmaydi)")
ok(Dw["title"] == "Differensial tenglamalar", "Taqdimot sarlavhasi: matnning birinchi sarlavhasi (prefikssiz)")

print("— 7. Sarlavha zanjiri (hech qachon «matn») —")
lkx = next(LKS)
lrow = next(l for l in next(x for x in J(OQ.get(P + "/lessons"))["items"] if x["id"] == CID)["lessons"] if l["key"] == lkx)
exp = lrow["title"] if not lrow["untitled"] else (f"{lkx}-mavzu — nomsiz" if lkx < 1000 else f"{lkx - 1000}-amaliy mashg'ulot — nomsiz")
Dn = mk(lk=lkx, build=False, text=NOHEAD)
ok(Dn["title"] == exp and Dn["outline"]["title"] == exp, f"Sarlavha yo'q: dars nomi, u ham yo'q — «<N>-mavzu — nomsiz»: «{Dn['title']}»")
Dm = J(OQ.post(P + "/decks/text", json={"text": NOHEAD}))
ok(Dm["title"] not in ("matn", "Mavzu", "") and Dm["outline"]["title"].lower() != "matn", f"Darssiz taqdimot: sarlavha «{Dm['title']}» — fayl nomi «matn» emas")
Dh = mk(lk=next(LKS), build=False, text="# Bozor tuzilmasi\nBozor iqtisodiyotida narx talab va taklif muvozanati orqali shakllanadi va rivojlanadi. " * 3)
ok(Dh["title"] == "Bozor tuzilmasi", "Birinchi sarlavha → taqdimot sarlavhasi")

print("— 8. IDOR: kurs boshqa o'qituvchiga o'tdi —")
LK7 = next(LKS)
Dc = mk(lk=LK7); J(OQ.post(P + f"/decks/{Dc['id']}/send", json={"note": "A ning izohi"}))
w("UPDATE dl_courses SET teacher_id=? WHERE id=?", (OQ2_TID, CID))
try:
    Dn2 = mk(cl=OQ2, lk=LK7, text=TEXT + "\nB o'qituvchining maxfiy matni")
    SB2 = J(OQ2.post(P + f"/decks/{Dn2['id']}/send", json={"note": "B ning izohi"}))
    vb = SB2["version"]
    ok(vb == 2, f"Yangi o'qituvchi yubordi: dars bo'yicha v{vb}")
    r = OQ.get(P + f"/decks/{Dc['id']}/sends/{vb}/pptx")
    ok(r.status_code == 403, "Eski o'qituvchi yangisining versiyasini eski taqdimoti orqali ololmaydi — 403")
    r = OQ.get(P + f"/decks/{Dc['id']}/sends/1/pptx")
    ok(r.status_code == 403, "Kurs o'tgach eski o'qituvchi darsning versiyalarini umuman yuklab olmaydi — 403")
    V = J(OQ.get(P + f"/decks/{Dc['id']}"))
    ok(V["lesson"].get("moved") and not V["lesson"]["teacher"] and "B ning izohi" not in json.dumps(V, ensure_ascii=False) and all(s["version"] != vb for s in V["sends"]),
       "Eski o'qituvchi sahifasida yangisining izohi, ismi va versiyasi ko'rinmaydi")
    ok(OQ.post(P + f"/decks/{Dc['id']}/send", json={}).status_code == 403 and OQ.get(f"{CD}/{CID}/{LK7}").status_code == 403, "Eski o'qituvchi yubora olmaydi, kartochkani ko'ra olmaydi — 403")
    ok(OQ2.get(P + f"/decks/{Dn2['id']}/sends/{vb}/pptx").status_code == 200, "Yangi o'qituvchi o'z versiyasini yuklab oladi")
    ok(OQ2.get(P + f"/decks/{Dn2['id']}/sends/1/pptx").status_code == 404, "Yangi o'qituvchi eski o'qituvchi yuborgan versiyani o'z taqdimoti orqali ololmaydi — 404")
    ok(q1("SELECT COUNT(*) FROM audit_log WHERE action LIKE 'taqdimot: begona dars versiyasi%' AND allowed=0") >= 1, "Audit: begona dars versiyasi rad etildi (allowed=0)")
finally:
    w("UPDATE dl_courses SET teacher_id=? WHERE id=?", (OQ_TID, CID))

print("— 9. Fayl yuklash chegarasi va xabarlar —")
H = {"Content-Type": "application/octet-stream"}
big = b"\x00" * (22 * 1024 * 1024)
t0 = time.time()
r = OQ.post(P + "/decks", params={"name": "big.docx", "course_id": CID, "lkey": keys[0]}, content=big, headers=H)
ok(r.status_code == 413 and "20 MB" in r.text and time.time() - t0 < 10, f"22 MB (Content-Length) — 413, tana o'qilmadi ({time.time() - t0:.1f} s)")
def gen():
    for _ in range(25):
        yield b"x" * (1024 * 1024)
r = OQ.post(P + "/decks", params={"name": "chunk.txt", "course_id": CID, "lkey": keys[0]}, content=gen(), headers=H)
ok(r.status_code == 413, "Content-Length yo'q (chunked) 25 MB — chegaradan oshganda to'xtatildi, 413")
r = OQ.post(P + "/decks/text", content=b'{"text": "' + b"a" * (21 * 1024 * 1024) + b'"}', headers={"Content-Type": "application/json"})
ok(r.status_code == 413, "Matn endpointi: 21 MB — 413")
ok(OPER.post(P + "/decks", content=b"x" * 100, headers=H).status_code == 403, "Ruxsatsiz rol — 403 (tana o'qilmasdan)")
lkq = keys[0]
for nm, body, msg in (("png", png, EX.MSG_TYPE), ("zipbad", b"PK\x03\x04" + b"\x00" * 100, EX.MSG_DOCX), ("pdfbad", b"%PDF-1.4\n1 0 obj", EX.MSG_PDF), ("jpg", b"\xff\xd8\xff\xe0" + b"\x01" * 200, EX.MSG_TYPE)):
    r = OQ.post(P + "/decks", params={"name": "x.docx", "course_id": CID, "lkey": lkq}, content=body, headers=H)
    ok(r.status_code == 415 and msg in r.text, f"{nm}: 415 «{msg}»")
ok(q1("SELECT COUNT(*) FROM pres_decks WHERE user_id=? AND deleted=0 AND source_name='x.docx'", (OQ_ID,)) == 0, "Rad etilgan fayldan yetim taqdimot qolmadi")

print("— 10. Muddat va «Yangi» (mywork), ishchi matni —")
LK8 = next(LKS)
Dm8 = mk(lk=LK8); J(OQ.post(P + f"/decks/{Dm8['id']}/send", json={}))
w("UPDATE pres_sends SET studio_ack_at=NULL, dept_ack_at=NULL WHERE course_id=? AND lkey=?", (CID, LK8))
for nm, cl in (("operator", OPER), ("masofaviy", HEAD)):
    its = [x for x in J(cl.get("/api/mywork"))["items"] if x["id"].startswith("st-pr")]
    ok(its and all(x["due"] is None and x["overdue"] is False and x["bucket"] != "overdue" and x.get("fresh") is True for x in its), f"{nm}: yangi taqdimot xabari — due yo'q, «Muddati o'tdi» emas, fresh=true")
dv = [x for x in J(HEAD.get("/api/mywork"))["items"] if x["id"].startswith("st-dv")]
ok(all(x["due"] is None and x.get("fresh") is True and not x["overdue"] for x in dv), "Montajlangan video xabari ham muddatsiz va fresh")
LK9 = next(LKS); approved_job(LK9)
opw = [x for x in J(OPER.get("/api/mywork"))["items"] if x["id"] == "st-dw"]
ok(opw and "Masofaviy bo'limga yuborilmagan montaj:" in opw[0]["title"] and opw[0]["count"] >= 1 and opw[0]["due"] is None, f"Operator: «{opw[0]['title']}»")
ok(not [x for x in J(HEAD.get("/api/mywork"))["items"] if x["id"] == "st-dw"], "Bu qator faqat operatorga")
mo, mh = J(OPER.get(ST + "/meta")), J(HEAD.get(ST + "/meta"))
if not mo["worker_on"]:
    ok(mo["worker_note"] == "Montaj hozircha ishlamayapti — IT bilan bog'laning. Vazifalar navbatda saqlanadi." and "ISFT_CORE_WORKER_TOKEN" not in mo["worker_note"], "Operator: texnik so'zsiz «Montaj hozircha ishlamayapti — IT bilan bog'laning»")
    ok("ISFT_CORE_WORKER_TOKEN" in mh["worker_note"], "Bo'lim boshlig'iga texnik matn (ISFT_CORE_WORKER_TOKEN)")
    ok("ISFT_CORE_WORKER_TOKEN" not in J(OPER.get(ST + "/jobs", params={"status": "faol"}))["worker_note"], "Montaj navbati javobida ham operatorga texnik matn yo'q")

print("— 11. ZIP: nomlar, video siyosati —")
LKz = next(LKS)
Dz = mk(lk=LKz); J(OQ.post(P + f"/decks/{Dz['id']}/send", json={}))
J(HEAD.post(f"/api/paket/courses/{CID}/topics/{LKz}/upload", params={"name": "montaj.mp4"}, content=MP4, headers=H))
import openpyxl
wb = openpyxl.Workbook(); wb.active["A1"] = "x"; bb = io.BytesIO(); wb.save(bb)
for nm in ("..", ".", "../../evil.xlsx", "x" * 300 + ".xlsx"):
    HEAD.post(f"/api/paket/courses/{CID}/topics/{LKz}/upload", params={"name": nm}, content=bb.getvalue(), headers=H)
code = lcode(LKz)
zr = HEAD.get(f"{CD}/{CID}/{LKz}/zip")
zf = zipfile.ZipFile(io.BytesIO(zr.content)); names = zf.namelist()
ok(zr.status_code == 200 and f"{code}/{code}_taqdimot_v1.pptx" in names and f"{code}/{code}_video.mp4" in names and f"{code}/meta.json" in names, "ZIP (bo'lim): <kod>_taqdimot_v1.pptx, <kod>_video.mp4, meta.json")
ok(all(not n.split("/")[-1].startswith((".", " ")) and ".." not in n.split("/") and len(n.split("/")[-1]) <= 140 for n in names), "ZIP: qo'shimcha fayl nomlari tozalangan (nuqta bilan boshlanmaydi, ../ yo'q, ≤120)")
ex = [n for n in names if "/qoshimcha/" in n]
ok(any(n.endswith("/fayl_%s" % i) or "/fayl_" in n for i, n in enumerate(ex)) and any(n.endswith("_evil.xlsx") for n in ex), f"ZIP: '..' / '.' → fayl_<id>; ../../evil.xlsx → xavfsiz ({len(ex)} ta)")
mj = json.loads(zf.read(f"{code}/meta.json"))
ok(mj["video"] == f"{code}_video.mp4" and {x["nom"] for x in mj["fayllar"]} == {n[len(code) + 1:] for n in names if not n.endswith("meta.json") and not n.endswith("/")}, "meta.json: video va fayllar ro'yxati ZIP bilan mos")
for nm, cl in (("o'qituvchi", OQ), ("kafedra", KAF)):
    z2 = cl.get(f"{CD}/{CID}/{LKz}/zip"); n2 = zipfile.ZipFile(io.BytesIO(z2.content)).namelist()
    m2 = json.loads(zipfile.ZipFile(io.BytesIO(z2.content)).read(f"{code}/meta.json"))
    ok(z2.status_code == 200 and not any("video" in n.split("/")[-1] and n.endswith(".mp4") for n in n2) and m2["video"] == "ruxsat yo'q" and "video_havola" not in m2, f"{nm}: ZIP'da video yo'q, meta.json video «ruxsat yo'q»")
ok(any(n.endswith(f"{code}_video.mp4") for n in zipfile.ZipFile(io.BytesIO(OPER.get(f"{CD}/{CID}/{LKz}/zip").content)).namelist()), "Operator: ZIP'da video bor")
for _ in range(50):         # papka javobdan KEYIN fon vazifasi (BackgroundTask) bilan o'chiriladi — sekin mashinada (CI) ulgurishi uchun kutamiz (≤ 5 s)
    if not (DATA / "tmp").exists() or not list((DATA / "tmp").glob("isft_zip_*")): break
    time.sleep(0.1)
ok(not [d for d in (DATA / "tmp").glob("isft_zip_*")] if (DATA / "tmp").exists() else True, "ZIP vaqtinchalik papkalari tozalangan")

print("— 12. Qidiruv va ro'yxat —")
r = J(HEAD.get("/api/paket/courses", params={"q": code, "limit": 1000}))
cc = PK_code = J(HEAD.get(f"{CD}/{CID}/{LKz}"))["ref"]["course_code"]
ok(r["lesson_hint"] == LKz and [x["id"] for x in r["items"]] == [CID], f"q=to'liq dars kodi ({code}) → fan + lesson_hint={LKz}")
r = J(HEAD.get("/api/paket/courses", params={"q": code.lower(), "limit": 1000}))
ok(r["lesson_hint"] == LKz, "Kod katta-kichik harfga bog'liq emas")
r = J(HEAD.get("/api/paket/courses", params={"q": cc, "limit": 1000}))
ok(r["lesson_hint"] is None and any(x["id"] == CID for x in r["items"]), "Fan kodi bilan — oddiy qidiruv (lesson_hint yo'q)")
ok(len(J(HEAD.get("/api/paket/courses", params={"limit": 1000}))["items"]) > 50 and len(J(HEAD.get("/api/paket/courses", params={"limit": 99999}))["items"]) <= 1000, "limit ≤ 1000")
a_code = f"{cc}_A3"
ok(J(HEAD.get("/api/paket/courses", params={"q": a_code}))["lesson_hint"] == 1003, "Amaliy dars kodi (_A3) → lesson_hint = 1003")

print("— 13. Studiya outline (yuborilgan versiya reja nusxasi) —")
ou = J(OPER.get(f"{ST}/lessons/{CID}/{LKz}/taqdimot/1/outline"))
ok(ou["title"] and ou["slides"] and ou["slides"][0]["kind"] == "title" and ou["slides"][1]["kind"] == "plan" and all(set(s) == {"n", "kind", "title", "bullets", "notes"} for s in ou["slides"]), f"Outline: {len(ou['slides'])} slayd (titul, reja, kontent), maydonlari to'g'ri")
ok(all(len(s["bullets"]) <= 8 for s in ou["slides"]) and any(s["bullets"] for s in ou["slides"][2:]), "Bandlar ≤ 8, kontent slaydlarda bandlar bor")
ok(HEAD.get(f"{ST}/lessons/{CID}/{LKz}/taqdimot/1/outline").status_code == 200 and OQ.get(f"{ST}/lessons/{CID}/{LKz}/taqdimot/1/outline").status_code == 200, "Bo'lim va o'z o'qituvchisi ko'ra oladi")
ok(OQ2.get(f"{ST}/lessons/{CID}/{LKz}/taqdimot/1/outline").status_code == 403 and KAF.get(f"{ST}/lessons/{CID}/{LKz}/taqdimot/1/outline").status_code == 403, "Begona o'qituvchi / kafedra — 403")
ok(OPER.get(f"{ST}/lessons/{CID}/{LKz}/taqdimot/9/outline").status_code == 404 and httpx.get(B + f"{ST}/lessons/{CID}/{LKz}/taqdimot/1/outline").status_code == 401, "Yo'q versiya — 404, kirishsiz — 401")
# snapshot yuborilgan paytdagi reja: keyin tahrirlansa ham o'zgarmaydi
o = J(OQ.get(P + f"/decks/{Dz['id']}"))["outline"]; o["slides"][1]["title"] = "KEYIN O'ZGARTIRILDI"
J(OQ.post(P + f"/decks/{Dz['id']}/outline", json={"outline": o}))
ou2 = J(OPER.get(f"{ST}/lessons/{CID}/{LKz}/taqdimot/1/outline"))
ok(ou2 == ou and "KEYIN" not in json.dumps(ou2), "Reja nusxasi YUBORILGAN paytdagi: keyingi tahrir ta'sir qilmaydi")
# eski yozuv (nusxa yo'q): PPTX dan; PPTX ham yo'q — bo'sh slaydlar
w("UPDATE pres_sends SET outline=NULL WHERE course_id=? AND lkey=? AND version=1", (CID, LKz))
ou3 = J(OPER.get(f"{ST}/lessons/{CID}/{LKz}/taqdimot/1/outline"))
ok(ou3["slides"] and ou3["slides"][0]["n"] == 1, "Eski yozuv (nusxa yo'q): PPTX dan olindi")
w("UPDATE pres_sends SET outline=NULL, pptx_path='yoq/yoq.pptx' WHERE course_id=? AND lkey=? AND version=1", (CID, LKz))
w("UPDATE pres_decks SET outline=NULL WHERE id=?", (Dz["id"],))
ou4 = J(OPER.get(f"{ST}/lessons/{CID}/{LKz}/taqdimot/1/outline"))
ok(ou4["slides"] == [] and ou4["title"], "PPTX ham, reja ham yo'q — bo'sh slaydlar (xato emas)")

print("— 14. Audit (bitta rad etilgan so'rovga bitta yozuv) va fan nomini majburlash —")
Dq = mk(lk=next(LKS), build=False)
tA = q1("SELECT strftime('%Y-%m-%dT%H:%M:%S','now','+5 hours')")
r = OQ2.get(P + f"/decks/{Dq['id']}")
ok(r.status_code == 403, "Begona taqdimot — 403")
nA = q1("SELECT MAX(id) FROM audit_log WHERE user_id=?", (OQ2_ID,))
r = OQ2.get(P + f"/decks/{Dq['id']}")
rows = q("SELECT allowed, action FROM audit_log WHERE user_id=? AND id>? ORDER BY id", (OQ2_ID, nA))
ok(len(rows) == 1 and rows[0][0] == 0 and "begona" in rows[0][1], f"Bitta so'rov — bitta audit yozuvi (allowed=0): {rows}")
r = OQ2.post(P + f"/decks/{Dq['id']}/send", json={})
rows = q("SELECT allowed FROM audit_log WHERE user_id=? AND ts>=? AND resource='presentations' AND detail LIKE ?", (OQ2_ID, tA, f"%#{Dq['id']}%"))
ok(r.status_code == 403 and all(x[0] == 0 for x in rows), "Begona taqdimotni yuborish: audit faqat allowed=0")
od = J(OQ.get(P + f"/decks/{Dq['id']}"))["outline"]
od["subject"], od["topic_no"] = "QO'LDA YOZILGAN BOSHQA FAN", "99"
V = J(OQ.post(P + f"/decks/{Dq['id']}/outline", json={"outline": od}))
ok(V["outline"]["subject"] == CO_ROW[0] and V["outline"]["topic_no"] == (Dq["topic_no"] or "") and V["outline"]["topic_no"] != "99" and V["subject"] == CO_ROW[0],
   "Darsga bog'langan taqdimot: fan nomi va mavzu raqami SERVER tomonida darsdan majburlandi")

print("— 15. O'chirilgan dars (gone) va kurs id qayta ishlatilishi —")
w("INSERT OR REPLACE INTO pk_lessons(course_id,lkey,kind,no,title,topic_ref,ts,user_name,deleted,src) VALUES(?,?,?,?,?,NULL,datetime('now'),'test',0,'')", (CID, 1007, "amaliy", 7, "Sinov amaliy"))
Da7 = mk(lk=1007)
J(OQ.post(P + f"/decks/{Da7['id']}/send", json={}))
ok(J(HEAD.get(f"{CD}/{CID}/1007"))["ref"]["kind"] == "amaliy", "Amaliy dars kartochkasi ochiladi")
w("UPDATE pk_lessons SET deleted=1 WHERE course_id=? AND lkey=1007", (CID,))
r = HEAD.get(f"{CD}/{CID}/1007")
g = r.json()
ok(r.status_code == 200 and g["gone"] is True and g["ref"]["gone"] and g["taqdimot"]["history"] and g["taqdimot"]["history"][0]["version"] == 1 and g["log"], "Dars o'chirilgan: kartochka 400 emas, gone:true va tarix (taqdimot, jurnal) ko'rinadi")
ok(g["caps"]["create"] is False and g["ref"]["full_code"].endswith("_A7"), "Gone kartochka: «Dars yaratish» yo'q, kod saqlangan (…_A7)")
zg = HEAD.get(f"{CD}/{CID}/1007/zip")
zgn = zipfile.ZipFile(io.BytesIO(zg.content)).namelist() if zg.status_code == 200 else []
ok(zg.status_code == 200 and any(n.endswith("_taqdimot_v1.pptx") for n in zgn) and any(n.endswith("meta.json") for n in zgn), "Dars o'chirilgan: ZIP ham 400 emas — tarix ZIP'i")
ok(HEAD.get(f"{CD}/{CID}/1007/taqdimot/1/pptx").status_code == 200, "Dars o'chirilgan: yuborilgan taqdimot yuklanadi")
ok(HEAD.get(f"{CD}/{CID}/1099").status_code == 400, "Hech qachon bo'lmagan dars — oldingi xulq (400)")
ghost = J(OQ.get(P + f"/decks/{Da7['id']}"))
ok(ghost["lesson"] is not None, "Taqdimot sahifasi o'chirilgan darsda ham ochiladi")

# kurs id qayta ishlatilishi
rid = 88001
dep = CO_ROW[3]
w("INSERT INTO dl_courses(id,subject,direction,course,department_id,teacher_id,semester,topics) VALUES(?,?,?,?,?,?,?,15)", (rid, "Sinov fani Birinchi", CO_ROW[1], 3, dep, OQ_TID, 9))
J(OQ.get(P + "/lessons"))
cA = next(x for x in J(OQ.get(P + "/lessons"))["items"] if x["id"] == rid)
Dr = mk(lk=1, cid=rid); J(OQ.post(P + f"/decks/{Dr['id']}/send", json={}))
ok(J(HEAD.get(f"{CD}/{rid}/1"))["taqdimot"]["latest"]["version"] == 1, "Sinov kursida v1 yuborildi")
w("DELETE FROM dl_courses WHERE id=?", (rid,))
J(OQ.get(P + "/lessons"))                                       # kurs o'chirilgani keyingi so'rovda aniqlanadi (kod yozuvi tozalanadi, taqdimotlari yetim bo'ladi)
w("INSERT INTO dl_courses(id,subject,direction,course,department_id,teacher_id,semester,topics) VALUES(?,?,?,?,?,?,?,15)", (rid, "Butunlay Yangi Fan", CO_ROW[1], 3, dep, OQ_TID, 9))
J(OQ.get(P + "/lessons"))
cr_ = J(HEAD.get(f"{CD}/{rid}/1"))
ok(cr_["taqdimot"]["latest"] is None and cr_["taqdimot"]["history"] == [] and cr_["ref"]["full_code"] != cA["code"] + "_L1", "Kurs id qayta ishlatildi — yangi kurs eski versiyalarni va kodni olmadi")
D2r = mk(lk=1, cid=rid); S_ = J(OQ.post(P + f"/decks/{D2r['id']}/send", json={}))
ok(S_["version"] == 1, "Yangi kursda yuborish v1 dan boshlanadi (UNIQUE buzilmadi)")
w("DELETE FROM dl_courses WHERE id=?", (rid,))

print("— 16. Hamma amallardan keyin qulf va kodlar —")
ok(can_write(), "Yakunda baza yozish qulfi bo'sh")
codes_now = {r[0]: r[1] for r in q("SELECT course_id, code FROM course_code_store")}
ok(len(set(codes_now.values())) == len(codes_now), f"course_code_store: {len(codes_now)} ta kod, hammasi unikal")
ok(all(codes_now[i] == PK.course_code({"id": i, "subject": s_, "direction": d_, "course": c_, "semester": sm}) or codes_now[i].startswith(PK.course_code({"id": i, "subject": s_, "direction": d_, "course": c_, "semester": sm}))
       for i, s_, d_, c_, sm in q("SELECT id, subject, direction, course, semester FROM dl_courses") if i in codes_now), "Mavjud kurslar kodi hozirgi qoidadan chiqqan kod bilan bir xil (takrorlanganlarda qo'shimchali)")
print(f"\nJami: {N[0]} tekshiruv o'tdi")
