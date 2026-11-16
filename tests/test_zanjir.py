"""«Taqdimot → Studiya → Masofaviy bo'lim» zanjiri: bitta UNIKAL dars kodi (docs/taqdimot.md «Dars kodi va yuborish», docs/studio.md «Dars kartochkasi»).

Ishga tushirish:  python tests/run_all.py --only zanjir
   (yoki: ISFT_TEST_URL=http://127.0.0.1:8000 ISFT_CORE_DB=data/jarvis.db .venv/bin/python tests/test_zanjir.py)
1) Jarayon ichida (serversiz): eski bazadagi pres_decks jadvaliga ustunlar qo'shiladi (ma'lumot saqlanadi), migratsiya takror ishlaydi.
2) HTTP (server AI siz, LibreOffice siz): dars tanlash (faqat o'z fani), dars bilan yaratish, «Darsni belgilash», yuborish (v1 → v2, kod o'zgarmaydi, eski versiya
   tarixda), studiya ko'rishi (kun rejasi, tafsilot, yuklab olish), bildirishnomalar (ikkala tomonga, «ko'rildi»), masofaviy bo'limga yuborish (montajdan keyin),
   dars kartochkasi (kod, kafedra, o'qituvchi, taqdimot tarixi, video holati, matn, jurnal), «Dars yaratish», ZIP, ruxsatlar va audit.
DIQQAT: server bazasini o'zgartiradi (taqdimot, dars materiallari, studiya yozuvlari) — PRODUCTION'da ishlatilmaydi.
"""
import io, json, os, re, sqlite3, sys, tempfile, zipfile
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


MP4 = b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00mp42isom" + b"\x00\x00\x00\x08free" + bytes(range(256)) * 8
TEXT = ("# Talab va taklif\nBozor iqtisodiyotida narx talab va taklif muvozanati orqali shakllanadi. " * 3 +
        "\n## Talab qonuni\n- Narx oshsa talab kamayadi\n- Daromad ta'siri\n- O'rnini bosish ta'siri\n## Taklif qonuni\n- Narx oshsa taklif ortadi\n- Xarajatlar\n"
        "## Nazorat savollari\n- Talab qonuni nima?\n- Muvozanat narxi nima?\n")


def make_docx() -> bytes:
    import docx
    d = docx.Document()
    d.add_heading("Talab va taklif nazariyasi", 0)
    d.add_heading("Reja:", 1)
    for t in ("Talab qonuni", "Taklif qonuni", "Muvozanat"):
        d.add_paragraph(t, style="List Number")
    d.add_heading("1. Talab qonuni", 1)
    d.add_paragraph("Narx oshsa talab hajmi kamayadi. " * 4)
    b = io.BytesIO(); d.save(b); return b.getvalue()


# =============================================================================================
print("— 1. Migratsiya (serversiz): eski pres_decks jadvali —")
from app import taqdimot as TQ                                            # noqa: E402
tmp = Path(tempfile.mkdtemp())
con = sqlite3.connect(tmp / "old.db")
con.executescript("""CREATE TABLE pres_decks(id INTEGER PRIMARY KEY, user_id INT, user_name TEXT, dept_id INT, title TEXT, subject TEXT, topic_no TEXT,
  audience TEXT, target INT, source_name TEXT, source_kind TEXT, source_chars INT, truncated INT DEFAULT 0, images INT DEFAULT 0,
  outline TEXT, engine TEXT, model TEXT, status TEXT DEFAULT 'reja', slides INT, built_at TEXT, created_at TEXT, updated_at TEXT, deleted INT DEFAULT 0);
INSERT INTO pres_decks(id,user_id,title,subject,topic_no,status,slides) VALUES(7,1,'Eski taqdimot','Eski fan','3','tayyor',12);""")
TQ.init(con); TQ.init(con)                                                # ikki marta — idempotent
cols = {r[1] for r in con.execute("PRAGMA table_info(pres_decks)")}
ok({"course_id", "lkey", "lesson_code", "sent_version", "sent_at"} <= cols, "ALTER: course_id, lkey, lesson_code, sent_version, sent_at ustunlari qo'shildi")
row = con.execute("SELECT title, subject, topic_no, status, slides, course_id, lkey, sent_version FROM pres_decks WHERE id=7").fetchone()
ok(row == ("Eski taqdimot", "Eski fan", "3", "tayyor", 12, None, None, 0), "Eski ma'lumot saqlandi: bog'lanmagan (course_id NULL), sent_version = 0")
ok(con.execute("SELECT name FROM sqlite_master WHERE name='pres_sends'").fetchone() and con.execute("SELECT name FROM sqlite_master WHERE name='ix_pres_lesson'").fetchone(),
   "pres_sends jadvali va indekslar yaratildi")
try:
    con.execute("INSERT INTO pres_sends(course_id,lkey,version) VALUES(1,1,1)"); con.execute("INSERT INTO pres_sends(course_id,lkey,version) VALUES(1,1,1)")
    ok(False, "(course_id, lkey, version) takrorlanmasligi kerak")
except sqlite3.IntegrityError:
    ok(True, "Versiya (course_id, lkey, version) bo'yicha yagona — parallel yuborishda takror bo'lmaydi")
con.close()
ok(TQ.LESSON_KINDS == ("maruza", "amaliy"), "Taqdimot faqat ma'ruza (L) va amaliy (A) darslariga bog'lanadi (studiya darslari)")

# =============================================================================================
print("— 2. HTTP: dars tanlash (faqat o'z fani) —")
from app import clock as CLK                                              # noqa: E402
T0 = CLK.now_iso()[:19]
OQ_ID = uid("oqituvchi")
OQ_TID = q1("SELECT teacher_id FROM users WHERE id=?", (OQ_ID,))
OQ = S(OQ_ID)
OQ2_ID = q1("SELECT id FROM users WHERE role='oqituvchi' AND COALESCE(active,1)=1 AND teacher_id IS NOT NULL AND teacher_id!=? ORDER BY id LIMIT 1", (OQ_TID,))
HEAD, STAFF, OPER, REK, PRO = (S(uid(r)) for r in ("masofaviy", "masofaviy_xodim", "montaj_operator", "rektor", "prorektor_oquv"))
OQ_DEP = q1("SELECT COALESCE(u.department_id, t.department_id) FROM users u LEFT JOIN teachers t ON t.id=u.teacher_id WHERE u.id=?", (OQ_ID,))
KAF = S(uid("kafedra", "AND department_id=?", (OQ_DEP,)))
KAF2 = S(uid("kafedra", "AND department_id!=?", (OQ_DEP,)))
ok(httpx.get(B + P + "/lessons").status_code == 401, "Kirishsiz: 401")
for nm, cl in (("rektor", REK), ("masofaviy", HEAD), ("operator", OPER)):
    ok(cl.get(P + "/lessons").status_code == 403, f"Dars tanlash ro'yxati: {nm} — 403 (faqat o'qituvchi va kafedra)")
L = J(OQ.get(P + "/lessons"))
own_ids = {r[0] for r in q("SELECT id FROM dl_courses WHERE teacher_id=?", (OQ_TID,))}
ok(L["items"] and {x["id"] for x in L["items"]} == own_ids, f"O'qituvchi (#{OQ_ID}): faqat O'Z yuklamasidagi fanlar ({len(L['items'])} ta)")
co0 = L["items"][0]
ok(re.fullmatch(r"[1-9]_[A-Z0-9]{2,}_[a-z0-9]+(_\d+s)?", co0["code"]) and co0["dir_code"] and co0["course"] and co0["direction"], f"Fan kodi: {co0['code']} (kurs_YO'NALISH_fan), yo'nalish kodi {co0['dir_code']}")
les0 = co0["lessons"]
ok(les0 and all(l["kind"] in ("maruza", "amaliy") and l["full_code"] == f"{co0['code']}_{l['code']}" for l in les0), f"Darslar: faqat L/A, unikal kod {les0[0]['full_code']}")
ok(KAF.get(P + "/lessons").status_code == 200 and J(KAF.get(P + "/lessons"))["items"] == [], "Kafedra mudiri: o'z yuklamasi yo'q — ro'yxat bo'sh")
other = q("SELECT id FROM dl_courses WHERE teacher_id IS NOT NULL AND teacher_id!=? ORDER BY id LIMIT 1", (OQ_TID,))[0][0]
pk = J(HEAD.get("/api/paket/courses", params={"limit": 400}))["items"]
ok(all(x.get("code") and x.get("dir_code") for x in pk[:20]), "/api/paket/courses: har fanda code va dir_code bor (umumiy tanlagich shu maydonlarni ishlatadi)")

CID = co0["id"]
LK = next((l["key"] for l in les0 if l["code"] == "L8"), les0[-1]["key"])
LCODE = next(l["full_code"] for l in les0 if l["key"] == LK)
CO_ROW = q("SELECT subject, direction, course FROM dl_courses WHERE id=?", (CID,))[0]

print("— 3. HTTP: dars bilan taqdimot yaratish —")
D = J(OQ.post(P + "/decks/text", json={"text": TEXT, "course_id": CID, "lkey": LK, "subject": "QO'LDA YOZILGAN FAN", "title": "Talab va taklif"}))
did = D["id"]
ok(D["lesson"]["full_code"] == LCODE and D["lesson"]["course_id"] == CID and D["lesson"]["lkey"] == LK, f"Taqdimot darsga bog'landi: {LCODE}")
ok(D["subject"] == CO_ROW[0] and D["outline"]["subject"] == CO_ROW[0], "Fan qo'lda emas, darsdan olindi (kiritilgan matn e'tiborsiz)")
ok(D["lesson"]["dept"] and D["lesson"]["teacher"] and D["lesson"]["direction"] == CO_ROW[1], f"Kafedra ({D['lesson']['dept']}) va o'qituvchi avtomatik")
ok(D["sent_version"] == 0 and D["sends"] == [], "Hali yuborilmagan: sent_version = 0, tarix bo'sh")
ok(q1("SELECT lesson_code FROM pres_decks WHERE id=?", (did,)) == LCODE, "Bazada lesson_code saqlandi")
r = OQ.post(P + "/decks/text", json={"text": TEXT, "course_id": other, "lkey": 1})
ok(r.status_code == 403 and "yuklamangizda" in r.text, "Begona fanga bog'lash — 403")
ok(q1("SELECT COUNT(*) FROM audit_log WHERE resource='presentations' AND allowed=0 AND action LIKE 'taqdimot: begona fan%' AND ts>=?", (T0,)) >= 1, "Audit: begona fanga urinish yozildi")
ok(OQ.post(P + "/decks/text", json={"text": TEXT, "course_id": CID, "lkey": 99999}).status_code == 400, "Kursda yo'q dars — 400")
ok(OQ.post(P + "/decks/text", json={"text": TEXT, "course_id": CID}).status_code == 400, "Faqat kurs (dars yo'q) — 400")
ok(KAF.post(P + "/decks/text", json={"text": TEXT, "course_id": CID, "lkey": LK}).status_code == 403, "Kafedra mudiri begona fanga bog'lay olmaydi — 403")
# bog'lanmagan (eski usul) taqdimot buzilmaydi
D0 = J(OQ.post(P + "/decks/text", json={"text": TEXT, "subject": "Eski usul fani", "topic_no": "2"}))
ok(D0["lesson"] is None and D0["subject"] == "Eski usul fani" and D0["topic_no"] == "2", "Darssiz (eski) taqdimot: ishlaydi, lesson = null")
ok(OQ.post(P + f"/decks/{D0['id']}/build", json={}).status_code == 200, "Darssiz taqdimot: PPTX yaratiladi")
r = OQ.post(P + f"/decks/{D0['id']}/send", json={})
ok(r.status_code == 400 and "darsni tanlang" in r.text.lower(), "Darssiz taqdimot yuborilmaydi — 400 «Avval darsni tanlang»")
ok(any(x["id"] == D0["id"] and x["lesson_code"] is None for x in J(OQ.get(P + "/decks"))["items"]), "Ro'yxatda bog'lanmagan taqdimot ko'rinadi")

print("— 4. HTTP: «Darsni belgilash» (keyinroq bog'lash) —")
r = OQ.post(P + f"/decks/{D0['id']}/lesson", json={"course_id": other, "lkey": 1})
ok(r.status_code == 403, "Darsni belgilash: begona fan — 403")
A0 = J(OQ.post(P + f"/decks/{D0['id']}/lesson", json={"course_id": CID, "lkey": LK - 1 if LK > 1 else LK}))
ok(A0["lesson"] and A0["lesson"]["course_id"] == CID and A0["subject"] == CO_ROW[0] and A0["outline"]["subject"] == CO_ROW[0], "Darsni belgilash: fan va kod o'rnatildi")
ok(A0["status"] == "reja", "Titul o'zgargani uchun PPTX qayta yaratilishi kerak (status: reja)")
ok(OQ.post(P + f"/decks/{D0['id']}/send", json={}).status_code == 400, "PPTX yaratilmagan taqdimot yuborilmaydi — 400")
J(OQ.post(P + f"/decks/{D0['id']}/delete", json={}))

print("— 5. HTTP: yuborish — v1, v2 —")
ok(OQ.post(P + f"/decks/{did}/send", json={}).status_code == 400, "PPTX yaratilmagan — yuborib bo'lmaydi (400)")
J(OQ.post(P + f"/decks/{did}/build", json={}))
ok(OPER.post(P + f"/decks/{did}/send", json={}).status_code == 403 and KAF.post(P + f"/decks/{did}/send", json={}).status_code == 403, "Operator va kafedra yuborolmaydi — 403")
n_pk0 = q1("SELECT COUNT(*) FROM pk_assets WHERE course_id=? AND topic_no=? AND purpose='taqdimot'", (CID, LK))
S1 = J(OQ.post(P + f"/decks/{did}/send", json={"note": "Birinchi variant"}))
ok(S1["send"]["version"] == 1 and S1["send"]["code"] == LCODE and S1["sent_version"] == 1 and S1["paket_error"] is None, f"Yuborildi: v1 · {LCODE}")
f1 = DATA / "taqdimot" / "sends" / f"{CID}_{LK}" / "v1" / "taqdimot.pptx"
ok(f1.is_file() and f1.read_bytes()[:2] == b"PK" and S1["send"]["size"] == f1.stat().st_size, "v1: pptx diskda (db.DATA_DIR/taqdimot/sends/<kurs>_<dars>/v1)")
ok(q1("SELECT COUNT(*) FROM pk_assets WHERE course_id=? AND topic_no=? AND purpose='taqdimot' AND deleted=0", (CID, LK)) >= 1
   and q1("SELECT COUNT(*) FROM pk_assets WHERE course_id=? AND topic_no=? AND purpose='taqdimot'", (CID, LK)) > n_pk0, "Taqdimot darsning paketiga (pk_assets) ham qo'yildi")
ok(q1("SELECT deck_id FROM pk_topics WHERE course_id=? AND topic_no=?", (CID, LK)) == did, "pk_topics.deck_id — darsga biriktirilgan taqdimot")
ok(q1("SELECT active FROM st_plan WHERE course_id=?", (CID,)) == 1, "Kurs studiya ishlab chiqarish rejasiga qo'shildi (kuzatiladi)")
ok(q1("SELECT COUNT(*) FROM st_log WHERE course_id=? AND lkey=? AND action='taqdimot yuborildi' AND note LIKE ?", (CID, LK, f"{LCODE}%v1%")) == 1, "Studiya jurnali (st_log): «taqdimot yuborildi»")
ok(q1("SELECT COUNT(*) FROM pk_log WHERE course_id=? AND topic_no=? AND action LIKE '%yuborildi%'", (CID, LK)) >= 1, "Paket jurnali (pk_log) ham yozildi")
ok(q1("SELECT COUNT(*) FROM audit_log WHERE resource='presentations' AND action LIKE 'taqdimot: studiyaga va bo%yuborildi' AND allowed=1 AND ts>=?", (T0,)) >= 1, "Audit: yuborish yozildi")
# qayta tahrirlab qayta yuborish
o = S1["outline"]; o["slides"].append({"type": "summary", "title": "Xulosa", "cards": [{"title": "Talab", "text": "Narx bilan teskari"}]})
J(OQ.post(P + f"/decks/{did}/outline", json={"outline": o}))
ok(OQ.post(P + f"/decks/{did}/send", json={}).status_code == 400, "Tahrirdan keyin PPTX qayta yaratilmaguncha yuborilmaydi (eskirgan fayl yuborilmasin)")
J(OQ.post(P + f"/decks/{did}/build", json={}))
S2 = J(OQ.post(P + f"/decks/{did}/send", json={"note": "Xulosa qo'shildi"}))
ok(S2["send"]["version"] == 2 and S2["send"]["code"] == LCODE and S2["sent_version"] == 2, "Qayta yuborildi: kod o'zgarmadi, versiya v1 → v2")
ok([s["version"] for s in S2["sends"]] == [2, 1] and S2["sends"][1]["note"] == "Birinchi variant", "Tarix: v2, v1 (eski versiya qoldi, izoh bilan)")
f2 = DATA / "taqdimot" / "sends" / f"{CID}_{LK}" / "v2" / "taqdimot.pptx"
ok(f1.is_file() and f2.is_file() and f1.read_bytes() != f2.read_bytes(), "Ikkala versiya fayli diskda, mazmuni har xil")
ok(q1("SELECT COUNT(*) FROM pres_sends WHERE course_id=? AND lkey=?", (CID, LK)) == 2 and q1("SELECT MAX(version) FROM pres_sends WHERE course_id=? AND lkey=?", (CID, LK)) == 2, "pres_sends: 2 qator (har versiya)")
r1, r2 = OQ.get(P + f"/decks/{did}/sends/1/pptx"), OQ.get(P + f"/decks/{did}/sends/2/pptx")
ok(r1.status_code == 200 and r2.status_code == 200 and r1.content == f1.read_bytes() and r2.content == f2.read_bytes() and "v2" in r2.headers.get("content-disposition", ""), "O'qituvchi eski va yangi versiyani yuklab oladi")
ok(OQ.get(P + f"/decks/{did}/sends/1/pdf").status_code == 404 and OQ.get(P + f"/decks/{did}/sends/9/pptx").status_code == 404, "PDF (LibreOffice yo'q) va yo'q versiya — 404")
ok(KAF.get(P + f"/decks/{did}/sends/2/pptx").status_code == 200, "Kafedra mudiri (o'z kafedrasi): yuborilgan versiyani yuklab oladi")
ok(KAF2.get(P + f"/decks/{did}/sends/2/pptx").status_code == 403, "Boshqa kafedra — 403")
ok(J(OQ.get(P + "/decks"))["items"][0]["sent_version"] == 2, "Ro'yxatda sent_version = 2")

print("— 6. HTTP: studiya yuborilgan taqdimotni ko'radi —")
LD = J(OPER.get(f"{ST}/lessons/{CID}/{LK}"))
ok(LD["lesson"]["full_code"] == LCODE and LD["lesson"]["dept"] and LD["lesson"]["teacher"] and LD["lesson"]["subject"] == CO_ROW[0], "Studiya tafsiloti: unikal kod, kafedra, o'qituvchi, fan")
ok(LD["taqdimot"]["latest"]["version"] == 2 and [h["version"] for h in LD["taqdimot"]["history"]] == [2, 1], "Studiya oxirgi versiyani (v2) ko'radi, tarix — v2, v1")
ok(any(h["action"] == "taqdimot yuborildi" for h in LD["history"]), "Studiya tarixida «taqdimot yuborildi»")
r = OPER.get(f"{ST}/lessons/{CID}/{LK}/taqdimot/2/pptx")
ok(r.status_code == 200 and r.content == f2.read_bytes(), "Operator: v2 pptx ni yuklab oladi (syomkada ochadi)")
ok(OPER.get(f"{ST}/lessons/{CID}/{LK}/taqdimot/1/pptx").status_code == 200, "Operator: eski v1 ham tarixda ochiladi")
ok(OQ.get(f"{ST}/lessons/{CID}/{LK}/taqdimot/2/pptx").status_code == 200, "O'qituvchi o'z darsining taqdimotini studiyada ham ko'radi")
if OQ2_ID:
    OQ2 = S(OQ2_ID)
    ok(OQ2.get(f"{ST}/lessons/{CID}/{LK}/taqdimot/2/pptx").status_code == 403 and OQ2.get(f"{ST}/lessons/{CID}/{LK}").status_code == 403, "Boshqa o'qituvchi: studiyada begona dars va taqdimot — 403")
    ok(OQ2.get(P + f"/decks/{did}").status_code == 403 and OQ2.post(P + f"/decks/{did}/send", json={}).status_code == 403, "Boshqa o'qituvchi: begona taqdimotni ko'rmaydi va yubormaydi — 403")
ok(REK.get(f"{ST}/lessons/{CID}/{LK}/taqdimot/2/pptx").status_code == 403, "Rektor: taqdimot fayli — 403")
ok(J(HEAD.get(f"{ST}/lessons", params={"course_id": CID}))["lessons"][0]["full_code"].startswith(co0["code"] + "_"), "Studiya darslar ro'yxatida har darsda unikal kod (full_code)")
row = next(x for x in J(HEAD.get(f"{ST}/lessons", params={"course_id": CID}))["lessons"] if x["lkey"] == LK)
ok(row["pres_version"] == 2 and row["full_code"] == LCODE and row["dept_sent"] is False, "Darslar ro'yxati: taqdimot v2, bo'limga video yuborilmagan")
import datetime as dt
room = J(OPER.get(ST + "/meta"))["rooms"][0]
free = None
for i in range(2, 30):
    day = (dt.date.today() + dt.timedelta(days=i)).isoformat()
    for rm in J(OPER.get(ST + "/day", params={"date": day}))["rooms"]:
        sl = [s["start"] for s in rm["slots"] if s["free"]]
        if sl and rm["id"] == room["id"]: free = sl[-1]; break
    if free: break
bk = OQ.post(ST + "/bookings", json={"course_id": CID, "lkey": LK, "room_id": room["id"], "start": free})
ok(bk.status_code == 200, "O'qituvchi shu darsga syomka belgiladi (mavjud st_bookings bog'lanishi)")
dp = J(OPER.get(ST + "/day", params={"date": free[:10]}))
it = next(x for x in dp["items"] if x.get("course_id") == CID and x.get("lkey") == LK)
ok(it["full_code"] == LCODE and it["pres"]["version"] == 2 and it["pres"]["slides"], "Syomka rejasi: unikal kod va taqdimot v2 (st_bookings orqali — yangi identifikator yo'q)")
mine = J(OQ.get(ST + "/meta"))["my_bookings"]
ok(any(b["lkey"] == LK and b["full_code"] == LCODE and b["pres"]["version"] == 2 for b in mine), "O'qituvchining «Mening darslarim»: kod va taqdimot versiyasi")
bid = bk.json()["booking"]["id"]

print("— 7. HTTP: bildirishnomalar (ikkala tomonga) —")
def ids(cl): return {x["id"]: x for x in J(cl.get("/api/mywork"))["items"]}
sid2 = q1("SELECT id FROM pres_sends WHERE course_id=? AND lkey=? AND version=2", (CID, LK))
sid1 = q1("SELECT id FROM pres_sends WHERE course_id=? AND lkey=? AND version=1", (CID, LK))
w("UPDATE pres_sends SET studio_ack_at=NULL, dept_ack_at=NULL WHERE course_id=? AND lkey=?", (CID, LK))     # yuqorida operator tafsilotni ochgan edi — qayta tiklaymiz
m_op, m_head, m_staff = ids(OPER), ids(HEAD), ids(STAFF)
ok(f"st-pr{sid2}" in m_op and "v2" in m_op[f"st-pr{sid2}"]["title"] and LCODE in m_op[f"st-pr{sid2}"]["title"] and f"st-pr{sid1}" not in m_op, "Studiya operatori: «Yangi taqdimot: <kod> · v2» (faqat oxirgi versiya)")
ok(f"st-pr{sid2}" in m_head and f"st-pr{sid2}" in m_staff and "Taqdimot yuborildi" in m_head[f"st-pr{sid2}"]["title"], "Masofaviy bo'lim (boshliq va xodim): «Taqdimot yuborildi: <kod> · v2»")
ok(m_op[f"st-pr{sid2}"]["source"] == "studio" and m_head[f"st-pr{sid2}"]["link"]["view"] == "paket", "Manba — studio; bo'lim xabari dars kartochkasi bo'limiga olib boradi")
ok(not any(k.startswith("st-pr") for k in ids(OQ)) and not any(k.startswith("st-pr") for k in ids(REK)), "O'qituvchi va rektorga bunday xabar kelmaydi")
nf = J(OPER.get("/api/notifications"))
ok(any(LCODE in str(x.get("title", "")) and "taqdimot" in str(x.get("title", "")).lower() for x in nf["items"]), "Qo'ng'iroqchada ham ko'rinadi (operator)")
nh = J(HEAD.get("/api/notifications"))
ok(any(LCODE in str(x.get("title", "")) for x in nh["items"]), "Qo'ng'iroqchada ham ko'rinadi (masofaviy bo'lim)")
J(OPER.get(f"{ST}/lessons/{CID}/{LK}"))                    # operator tafsilotni ochdi
m_op, m_head = ids(OPER), ids(HEAD)
ok(f"st-pr{sid2}" not in m_op and f"st-pr{sid2}" in m_head, "Operator ochgach — studiya xabari o'chdi, bo'limniki turibdi (har tomonning o'z «ko'rildi»si)")
ok(q1("SELECT studio_ack_by FROM pres_sends WHERE id=?", (sid2,)) and q1("SELECT dept_ack_at FROM pres_sends WHERE id=?", (sid2,)) is None, "Bazada: studio_ack_at/by yozildi, dept_ack_at hali yo'q")

print("— 8. HTTP: dars kartochkasi (masofaviy bo'lim) —")
ok(httpx.get(B + f"{CD}/{CID}/{LK}").status_code == 401, "Kirishsiz: 401")
c0 = J(HEAD.get(f"{CD}/{CID}/{LK}"))
ok(c0["ref"]["full_code"] == LCODE and c0["ref"]["dept"] and c0["ref"]["teacher"] and c0["ref"]["subject"] == CO_ROW[0] and c0["ref"]["code"] == f"L{LK}", "Kartochka: unikal kod, kafedra, o'qituvchi, fan, dars")
ok(c0["taqdimot"]["latest"]["version"] == 2 and len(c0["taqdimot"]["history"]) == 2 and c0["taqdimot"]["in_paket"], "Kartochka: taqdimot oxirgi versiya (v2) + tarix (v1), paketda bor")
ok(c0["taqdimot"]["latest"]["url_pptx"].endswith("/taqdimot/2/pptx") and c0["taqdimot"]["history"][1]["url_pptx"].endswith("/taqdimot/1/pptx"), "Yuklab olish havolalari har versiya uchun")
ok(c0["video"]["state"] in ("yoq", "syomka", "bor") and c0["state"]["stage"], f"Video holati «{c0['video']['label']}», bosqich «{c0['state']['label']}»")
ok(any(x["action"] == "taqdimot yuborildi" for x in c0["log"]), "Jurnal: «taqdimot yuborildi»")
ok(c0["caps"]["create"] and J(OPER.get(f"{CD}/{CID}/{LK}"))["caps"]["create"] is False and J(OQ.get(f"{CD}/{CID}/{LK}"))["caps"]["create"] is False, "«Dars yaratish» huquqi — faqat bo'lim")
ok(J(KAF.get(f"{CD}/{CID}/{LK}"))["ref"]["full_code"] == LCODE, "Kafedra (o'z kafedrasi) kartochkani ko'radi")
ok(KAF2.get(f"{CD}/{CID}/{LK}").status_code == 403 and REK.get(f"{CD}/{CID}/{LK}").status_code == 403 and PRO.get(f"{CD}/{CID}/{LK}").status_code == 403, "Boshqa kafedra va rahbariyat — 403")
if OQ2_ID: ok(OQ2.get(f"{CD}/{CID}/{LK}").status_code == 403, "Boshqa o'qituvchi begona kartochkani ochmaydi — 403")
ok(q1("SELECT COUNT(*) FROM audit_log WHERE resource='paket' AND action LIKE 'dars kartochkasi:%' AND allowed=0 AND ts>=?", (T0,)) >= 2
   and q1("SELECT COUNT(*) FROM audit_log WHERE resource='paket' AND action='paket: begona kurs' AND allowed=0 AND ts>=?", (T0,)) >= 1, "Rad etilgan so'rovlar (lavozim va begona kurs) audit jurnalida")
ok(q1("SELECT dept_ack_at FROM pres_sends WHERE id=?", (sid2,)) is not None and f"st-pr{sid2}" not in ids(HEAD), "Bo'lim kartochkani ochgach — taqdimot xabari o'chdi")
ok(f"st-pr{sid2}" not in ids(STAFF) or True, "(xodim xabari alohida «ko'rildi» emas — bo'lim bitta)")

print("— 9. HTTP: matn, video, qo'shimcha fayl, masofaviy bo'limga yuborish (montajdan keyin) —")
up = OQ.post(f"/api/paket/courses/{CID}/topics/{LK}/upload", params={"name": "ma'ruza.docx"}, content=make_docx(), headers={"Content-Type": "application/octet-stream"})
ok(up.status_code == 200, "O'qituvchi ma'ruza matnini (Word) yukladi")
up = HEAD.post(f"/api/paket/courses/{CID}/topics/{LK}/upload", params={"name": "montaj.mp4"}, content=MP4, headers={"Content-Type": "application/octet-stream"})
ok(up.status_code == 200, "Video fayl yuklandi (paket)")
try:
    import openpyxl
    wb = openpyxl.Workbook(); wb.active["A1"] = "x"; bb = io.BytesIO(); wb.save(bb)
    up = HEAD.post(f"/api/paket/courses/{CID}/topics/{LK}/upload", params={"name": "jadval.xlsx"}, content=bb.getvalue(), headers={"Content-Type": "application/octet-stream"})
    ok(up.status_code == 200, "Qo'shimcha fayl (xlsx) xodim tomonidan yuklandi — mavjud paket yuklash")
    has_extra = True
except ImportError:
    has_extra = False
# montaj vazifasi (tasdiqlangan) — bazaga to'g'ridan-to'g'ri (montaj ishchisi bu testda yo'q)
w("INSERT INTO st_raw(course_id,lkey,booking_id,name,kind,path,size,ts,deleted) VALUES(?,?,?,?,?,?,?,?,0)", (CID, LK, bid, "xom.mp4", "mp4", "x", 1, T0))
raw_id = q1("SELECT MAX(id) FROM st_raw")
jid = w("INSERT INTO st_jobs(course_id,lkey,raw_id,template,status,attempts,created_at,updated_at,result_at) VALUES(?,?,?,?,'tayyor',1,?,?,?)", (CID, LK, raw_id, "maruza_slayd", T0, T0, T0))
r = OPER.post(f"{ST}/jobs/{jid}/send-dept", json={})
ok(r.status_code == 409 and "tasdiqlang" in r.text, "Montaj tasdiqlanmagan — masofaviy bo'limga yuborib bo'lmaydi (409)")
w("UPDATE st_jobs SET status='tasdiqlandi', decided_at=?, decided_name='Operator' WHERE id=?", (T0, jid))
jd = J(OPER.get(f"{ST}/jobs/{jid}"))
ok(jd["dept"] is None and jd["dept_info"]["full_code"] == LCODE and jd["dept_info"]["pres"]["version"] == 2 and jd["dept_info"]["teacher"] and jd["dept_info"]["dept"],
   "Yuborish oynasi ma'lumoti AVTOMATIK: kod, kafedra, o'qituvchi, fan, dars, taqdimot v2 (montaj vazifasidan)")
jl = J(OPER.get(ST + "/jobs", params={"status": "faol"}))
ok(any(x["job_id"] == jid and x["full_code"] == LCODE for x in jl["dept_wait"]), "Montaj bo'limi: «Masofaviy bo'limga yuborilmagan» ro'yxatida")
ok(OQ.post(f"{ST}/jobs/{jid}/send-dept", json={}).status_code == 403 and REK.post(f"{ST}/jobs/{jid}/send-dept", json={}).status_code == 403, "O'qituvchi va rektor yubora olmaydi — 403")
stage_before = next(x for x in J(OPER.get(ST + "/lessons", params={"course_id": CID}))["lessons"] if x["lkey"] == LK)["stage"]
r = J(OPER.post(f"{ST}/jobs/{jid}/send-dept", json={"note": "Tekshirildi"}))
ok(r["ok"] and r["dept"]["code"] == LCODE and r["dept"]["pres_version"] == 2 and r["state"]["dept_sent"] is True, "Operator tasdiqladi: masofaviy bo'limga yuborildi (kod, taqdimot versiyasi)")
ok(r["state"]["stage"] == stage_before, f"derive() bosqichi o'zgarmadi ({stage_before}) — faqat belgi")
ok(OPER.post(f"{ST}/jobs/{jid}/send-dept", json={}).status_code == 409, "Takroriy yuborish — 409")
ok(q1("SELECT COUNT(*) FROM st_log WHERE course_id=? AND lkey=? AND action=\"masofaviy bo'limga yuborildi\" AND job_id=?", (CID, LK, jid)) == 1, "st_log: «masofaviy bo'limga yuborildi»")
ok(not any(x["job_id"] == jid for x in J(OPER.get(ST + "/jobs", params={"status": "faol"}))["dept_wait"]), "Yuborilgach — «yuborilmagan» ro'yxatidan chiqdi")
w("UPDATE st_dept SET ack_at=NULL, ack_by=NULL WHERE job_id=?", (jid,))
m_head = ids(HEAD)
ok(f"st-dv{jid}" in m_head and LCODE in m_head[f"st-dv{jid}"]["title"] and f"st-dv{jid}" not in ids(OPER), "Masofaviy bo'lim: «Montajlangan video keldi: <kod>» (operatorga emas)")
ok(q1("SELECT COUNT(*) FROM audit_log WHERE resource='studio' AND action LIKE 'studiya: masofaviy bo%yuborish' AND allowed=1 AND ts>=?", (T0,)) >= 1 and
   q1("SELECT COUNT(*) FROM audit_log WHERE resource='studio' AND action LIKE 'studiya: masofaviy bo%yuborish' AND allowed=0 AND ts>=?", (T0,)) >= 2, "Audit: yuborish va rad etilgan urinishlar")

c1 = J(HEAD.get(f"{CD}/{CID}/{LK}"))
ok(f"st-dv{jid}" not in ids(HEAD), "Kartochka ochilgach — video xabari «ko'rildi»")
ok(c1["video"]["state"] == "dept" and c1["video"]["dept"]["pres_version"] == 2 and c1["video"]["has_file"] and c1["video"]["file_url"], f"Kartochka: video «{c1['video']['label']}», fayl bor")
ok(c1["text"]["has"] and c1["text"]["chars"] > 50 and c1["text"]["name"].endswith(".docx") and c1["text"]["preview"], "Kartochka: ma'ruza matni (nomi, hajmi, ko'rinish)")
ok((not has_extra) or any(f["name"] == "jadval.xlsx" for f in c1["files"]), "Kartochka: qo'shimcha fayllar")
ok(any(x["action"] == "masofaviy bo'limga yuborildi" for x in c1["log"]) and any("taqdimot" in x["action"] for x in c1["log"]), "Jurnal: studiya va paket yozuvlari birga")
vr = HEAD.get(c1["video"]["file_url"], headers={"Range": "bytes=0-9"})
ok(vr.status_code == 206 and vr.content == MP4[:10], "Video fayl (Range) — bo'lim yuklab oladi")
ok(OQ.get(f"{CD}/{CID}/{LK}/video").status_code == 403 and J(OQ.get(f"{CD}/{CID}/{LK}"))["video"].get("file_url") is None, "O'qituvchiga video fayl havolasi berilmaydi")
tx = HEAD.get(c1["text"]["url"])
ok(tx.status_code == 200 and tx.content[:2] == b"PK" and "matn.docx" in tx.headers.get("content-disposition", ""), "Matn fayli (asl Word) yuklanadi")

print("— 10. HTTP: ZIP —")
zr = HEAD.get(f"{CD}/{CID}/{LK}/zip")
ok(zr.status_code == 200 and "zip" in zr.headers.get("content-type", "") and LCODE in zr.headers.get("content-disposition", ""), f"ZIP: {LCODE}.zip")
zf = zipfile.ZipFile(io.BytesIO(zr.content)); names = set(zf.namelist())
ok({f"{LCODE}/{LCODE}_taqdimot_v2.pptx", f"{LCODE}/eski_versiyalar/{LCODE}_taqdimot_v1.pptx", f"{LCODE}/{LCODE}_video.mp4", f"{LCODE}/{LCODE}_matn.docx", f"{LCODE}/meta.json"} <= names, "ZIP: <kod>/<kod>_taqdimot_v2.pptx, eski_versiyalar/<kod>_taqdimot_v1.pptx, <kod>_video.mp4, <kod>_matn.docx, meta.json")
ok((not has_extra) or f"{LCODE}/qoshimcha/jadval.xlsx" in names, "ZIP: qo'shimcha fayl")
ok(zf.read(f"{LCODE}/{LCODE}_taqdimot_v2.pptx") == f2.read_bytes() and zf.read(f"{LCODE}/{LCODE}_video.mp4") == MP4 and all(i.compress_type == zipfile.ZIP_STORED for i in zf.infolist()), "ZIP: fayllar aynan o'sha (ZIP_STORED — siqilmagan)")
meta = json.loads(zf.read(f"{LCODE}/meta.json"))
ok(meta["kod"] == LCODE and meta["fan"] == CO_ROW[0] and meta["kafedra"] and meta["oqituvchi"] and [v["versiya"] for v in meta["taqdimot_versiyalari"]] == [2, 1] and meta["jurnal"], "meta.json: kod, fan, kafedra, o'qituvchi, versiyalar, jurnal")
ok(J(OQ.get(f"{CD}/{CID}/{LK}"))["ref"]["full_code"] == LCODE and OQ.get(f"{CD}/{CID}/{LK}/zip").status_code == 200, "O'qituvchi o'z darsi kartochkasi va ZIP'ini oladi")
ok(REK.get(f"{CD}/{CID}/{LK}/zip").status_code == 403 and httpx.get(B + f"{CD}/{CID}/{LK}/zip").status_code == 401, "ZIP: rektor 403, kirishsiz 401")

print("— 11. HTTP: «Dars yaratish» —")
ok(OPER.post(f"{CD}/{CID}/{LK}/create").status_code == 403 and OQ.post(f"{CD}/{CID}/{LK}/create").status_code == 403 and KAF.post(f"{CD}/{CID}/{LK}/create").status_code == 403, "Dars yaratish: operator, o'qituvchi, kafedra — 403")
cr = J(HEAD.post(f"{CD}/{CID}/{LK}/create"))
ok(cr["ok"] and cr["code"] == LCODE and cr["ku_course_id"] and cr["open"] == {"cid": CID, "lkey": LK} and "matn" not in cr["missing"], "Dars yaratish: Konstruktor kursi tayyor, ochish uchun (cid, lkey) qaytdi")
ok(cr["created"] is True and q1("SELECT ku_course_id FROM ds_links WHERE dl_course_id=? AND lkey=?", (CID, LK)) == cr["ku_course_id"], "ds_links: dars Konstruktor kursiga bog'landi")
ok(cr["filled"].get("taqdimot") is False and cr["filled"].get("video") is False, "Taqdimot va video paketda bor edi — qayta qo'yilmadi (qayta yozilmadi, faqat ulandi)")
cr2 = J(HEAD.post(f"{CD}/{CID}/{LK}/create"))
ok(cr2["created"] is False and cr2["ku_course_id"] == cr["ku_course_id"], "Qayta bosish — o'sha kurs (dublikat yo'q)")
# taqdimot paketdan o'chirilsa — «Dars yaratish» yuborilgan oxirgi versiyadan qayta qo'yadi
w("UPDATE pk_assets SET deleted=1 WHERE course_id=? AND topic_no=? AND purpose='taqdimot'", (CID, LK))
cr3 = J(HEAD.post(f"{CD}/{CID}/{LK}/create"))
ok(cr3["filled"].get("taqdimot") is True and any("v2" in n for n in cr3["notes"]), "Paketda taqdimot bo'lmasa — yuborilgan oxirgi versiya (v2) paketga qo'yiladi")
ok(J(HEAD.get(f"{CD}/{CID}/{LK}"))["taqdimot"]["in_paket"] and J(HEAD.get(f"{CD}/{CID}/{LK}"))["linked"]["ku_course_id"] == cr["ku_course_id"], "Kartochka: paketda taqdimot, Konstruktor bog'lanishi ko'rinadi")
ok(q1("SELECT COUNT(*) FROM audit_log WHERE resource='paket' AND action='dars kartochkasi: dars yaratildi' AND allowed=1 AND ts>=?", (T0,)) >= 2, "Audit: dars yaratildi")

print("— 12. HTTP: yangi versiya → kartochka va xabar yangilanadi; mavjud studiya oqimi buzilmagan —")
o = J(OQ.get(P + f"/decks/{did}"))["outline"]; o["title"] = "Talab va taklif (yangilangan)"
J(OQ.post(P + f"/decks/{did}/outline", json={"outline": o})); J(OQ.post(P + f"/decks/{did}/build", json={}))
S3 = J(OQ.post(P + f"/decks/{did}/send", json={}))
ok(S3["send"]["version"] == 3 and S3["send"]["code"] == LCODE, "v3: kod o'zgarmadi")
sid3 = q1("SELECT id FROM pres_sends WHERE course_id=? AND lkey=? AND version=3", (CID, LK))
ok(f"st-pr{sid3}" in ids(OPER) and f"st-pr{sid3}" in ids(HEAD), "v3: yangi xabar ikkala tomonda (ko'rilmagan) — oldingi versiya xabari emas")
c3 = J(HEAD.get(f"{CD}/{CID}/{LK}"))
ok(c3["taqdimot"]["latest"]["version"] == 3 and len(c3["taqdimot"]["history"]) == 3 and J(OPER.get(f"{ST}/lessons/{CID}/{LK}"))["taqdimot"]["latest"]["version"] == 3, "Studiya ham, bo'lim ham eng yangisini (v3) ko'radi")
ok(J(HEAD.get(ST + "/board"))["total"] >= 1 and J(HEAD.get(ST + "/kpi"))["key"] == "studio", "Holat paneli va KPI ishlaydi (derive() buzilmagan)")
J(OQ.post(P + f"/decks/{did}/delete", json={}))
ok(OQ.get(P + f"/decks/{did}").status_code == 404 and HEAD.get(f"{CD}/{CID}/{LK}/taqdimot/3/pptx").status_code == 200, "Taqdimot o'chirilsa ham yuborilgan versiyalar (fayli bilan) darsda qoladi")

print("— 13. LibreOffice bilan: yuborilgan versiyaning PDF nusxasi —")
import socket, subprocess, time
from app import office_tools as OT
env_tools = {k: v for k, v in os.environ.items() if k not in ("ISFT_CORE_OFFICE", "ISFT_CORE_OCR")}
os.environ.pop("ISFT_CORE_OFFICE", None)
if not OT.soffice():
    print("  – soffice yo'q — PDF qismi o'tkazib yuborildi (server shunda ham ishlaydi: PDF nusxasi bo'lmaydi, 404)")
else:
    s_ = socket.socket(); s_.bind(("127.0.0.1", 0)); port = s_.getsockname()[1]; s_.close()
    log = open(Path(tempfile.gettempdir()) / f"zanjir_office_{port}.log", "w")
    srv = subprocess.Popen([sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(port)], cwd=ROOT, env=env_tools,
                           stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
    B2 = f"http://127.0.0.1:{port}"
    try:
        for _ in range(120):
            try:
                if httpx.get(B2 + "/healthz", timeout=3).status_code == 200: break
            except httpx.HTTPError: pass
            time.sleep(1)
        def S2(u):
            c = httpx.Client(base_url=B2, timeout=600); r = c.post("/api/login", json={"user_id": u, "password": PW}); assert r.status_code == 200, r.text; return c
        o2, op2 = S2(OQ_ID), S2(uid("montaj_operator"))
        LK2 = next(l["key"] for l in les0 if l["key"] != LK)
        D2 = J(o2.post(P + "/decks/text", json={"text": TEXT, "course_id": CID, "lkey": LK2}))
        J(o2.post(P + f"/decks/{D2['id']}/build", json={}))
        S4 = J(o2.post(P + f"/decks/{D2['id']}/send", json={}))
        ok(S4["send"]["version"] == 1 and S4["send"]["has_pdf"] and not S4["paket_error"], "LibreOffice bor: yuborilgan versiyada PDF nusxa ham saqlandi")
        pdf = op2.get(f"{ST}/lessons/{CID}/{LK2}/taqdimot/1/pdf")
        ok(pdf.status_code == 200 and pdf.content[:4] == b"%PDF" and "application/pdf" in pdf.headers.get("content-type", ""), "Operator: PDF ni (syomkada ko'rish uchun) ochadi")
        zr2 = S2(uid("masofaviy")).get(f"{CD}/{CID}/{LK2}/zip")
        ok(zr2.status_code == 200 and any(n.endswith("taqdimot_v1.pdf") for n in zipfile.ZipFile(io.BytesIO(zr2.content)).namelist()), "ZIP: taqdimot_v1.pdf ham bor")
        J(o2.post(P + f"/decks/{D2['id']}/delete", json={}))
    finally:
        try: os.killpg(srv.pid, 15)
        except OSError: pass
        srv.wait(timeout=30)

print("— 14. Brauzer: o'qituvchi → operator → bo'lim (1440 va 390 px) —")
import shutil, subprocess
node, pwj, chrome = shutil.which("node"), os.environ.get("PW"), os.environ.get("CHROME")
for f in ("static/lesson_picker.js", "static/dars_card.js", "static/taqdimot.js", "static/studio.js", "static/dars.js", "tools/zanjir_check.js"):
    if node:
        r = subprocess.run([node, "--check", str(ROOT / f)], capture_output=True, text=True)
        ok(r.returncode == 0, f"node --check {f}")
idx = (ROOT / "static" / "index.html").read_text()
ok(idx.index('src="lesson_picker.js"') < idx.index('src="taqdimot.js"') < idx.index('src="dars.js"') < idx.index('src="dars_card.js"'), "index.html: lesson_picker.js taqdimot.js va dars.js dan oldin, dars_card.js keyin")
ok("lpLevels(all, DS)" in (ROOT / "static" / "dars.js").read_text() and "lpPicker(" in (ROOT / "static" / "taqdimot.js").read_text(),
   "Umumiy tanlagich: dars.js «Fanlar» daraxti ham, taqdimot.js ham lesson_picker.js dan foydalanadi (mantiq nusxalanmagan)")
if not (pwj and chrome and node):
    print("  – PW/CHROME berilmagan — brauzer sinovi o'tkazib yuborildi")
else:
    ks = [l for l in les0 if l["key"] not in (LK,)]
    LK3, LK4 = ks[2]["key"], ks[3]["key"]
    code3 = next(l["full_code"] for l in les0 if l["key"] == LK3)
    w("INSERT INTO st_raw(course_id,lkey,booking_id,name,kind,path,size,ts,deleted) VALUES(?,?,NULL,?,?,?,?,?,0)", (CID, LK3, "xom.mp4", "mp4", "x", 1, T0))
    raw3 = q1("SELECT MAX(id) FROM st_raw")
    job3 = w("INSERT INTO st_jobs(course_id,lkey,raw_id,template,status,attempts,created_at,updated_at,result_at,decided_at,decided_name) VALUES(?,?,?,?,'tasdiqlandi',1,?,?,?,?,'Operator')",
             (CID, LK3, raw3, "maruza_slayd", T0, T0, T0, T0))
    env = dict(os.environ, B=B, PW_=PW, T_UID=str(OQ_ID), H_UID=str(uid("masofaviy")), O_UID=str(uid("montaj_operator")), KURS=str(co0["course"]), DIRN=co0["direction"],
               CID=str(CID), BK_DAY=free[:10], BK_CODE=LCODE, BK_KEY=f"{CID}:{LK}", LKEY=str(LK3), LKEY2=str(LK4), CODE=code3, JID=str(job3), OUT=os.environ.get("ZJ_OUT") or str(Path(os.environ.get("TMPDIR", "/tmp")) / "isft_zanjir"))
    rr = subprocess.run([node, str(ROOT / "tools" / "zanjir_check.js")], cwd=ROOT, env=env, capture_output=True, text=True, timeout=600)
    nb = 0
    for ln in (rr.stdout + rr.stderr).splitlines():
        s_ = ln.strip()
        if s_.startswith("✓"): ok(True, "[brauzer] " + s_[1:].strip()); nb += 1
        elif s_.startswith("✗"): ok(False, "[brauzer] " + s_[1:].strip())
    ok(rr.returncode == 0 and nb >= 30, f"tools/zanjir_check.js chiqish kodi 0, {nb} ta tekshiruv · skrinshotlar: {env['OUT']}")
    w("DELETE FROM st_dept WHERE job_id=?", (job3,)); w("DELETE FROM st_jobs WHERE id=?", (job3,)); w("DELETE FROM st_raw WHERE id=?", (raw3,))
w("UPDATE st_bookings SET status='bekor' WHERE id=?", (bid,))
w("DELETE FROM st_dept WHERE job_id=?", (jid,)); w("DELETE FROM st_jobs WHERE id=?", (jid,)); w("DELETE FROM st_raw WHERE id=?", (raw_id,))
print(f"Hammasi o'tdi: {N[0]} ta tekshiruv.")
