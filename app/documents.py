"""Hujjatlar markazi: OTMdagi qog'ozbozlik ishlarini avtomatlashtirish.
Har bir hujjat: ISFT rasmiy blanki, ro'yxatga olish raqami (jurnal), QR orqali haqiqiylikni tekshirish,
lavozim va ko'lam (fakultet/kafedra/o'qituvchi) bo'yicha ruxsat, audit jurnali, buyruqlar uchun imzolash jarayoni.
Ma'lumot to'g'ridan-to'g'ri bazadan olinadi — qo'lda ko'chirish yo'q."""
import datetime as dt, json, secrets
from pathlib import Path
from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from . import db, brand as B
from .rbac import Ctx, AccessDenied, audit
from .services import TODAY, mln
from . import academic_rules as AR

OUT = Path(__file__).resolve().parent.parent / "data" / "docs"
UZ_MONTHS = ["yanvar", "fevral", "mart", "aprel", "may", "iyun", "iyul", "avgust", "sentabr", "oktabr", "noyabr", "dekabr"]
EN_MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]
ACAD_YEAR = "2026-2027"
PASS = AR.PASS       # o'tish bali (100 ballik) — institut qoidasi: 40 ball = «3»
CREDITS = 6          # bir fan uchun kredit (demo; taqdimotdagi GPA misolida ham 6 kredit)
LOAD_NORM = 840      # 1 stavka yillik o'quv yuklamasi, soat (institut nizomiga ko'ra sozlanadi)

def d_uz(d): d = dt.date.fromisoformat(d) if isinstance(d, str) else d; return f"{d.year}-yil {d.day}-{UZ_MONTHS[d.month-1]}"
def d_en(d): d = dt.date.fromisoformat(d) if isinstance(d, str) else d; return f"{d.day} {EN_MONTHS[d.month-1]} {d.year}"
def short(full):
    p = (full or "").split()
    return f"{p[0]} {p[1][0]}." if len(p) > 1 else full
grade5, letter = AR.grade5, AR.letter   # 65–100 «5» A · 60–64 «4» B · 50–59 «4» C · 45–49 «3» D · 40–44 «3» E · 0–39 «2» F

# ---------------- katalog ----------------
DEAN_SIDE = {"dekan", "talabalar", "prorektor_oquv"}
LEAD = {"rektor", "kengash", "prorektor_oquv", "prorektor_ilmiy", "prorektor_moliya", "prorektor_yoshlar"}
EVERYONE_STAFF = LEAD | {"qabul", "talabalar", "magistratura", "xalqaro", "buxgalteriya", "kadrlar", "dekan", "kafedra"}

STUDENT_ACTIONS = {
    "akademik_tatil": "akademik ta'til berish",
    "kochirish": "boshqa oliy ta'lim muassasasiga o'qishini ko'chirish munosabati bilan talabalar safidan chiqarish",
    "chetlashtirish_tolov": "to'lov-kontrakt shartnomasi bo'yicha majburiyat bajarilmagani sababli talabalar safidan chetlashtirish",
    "chetlashtirish_xohish": "o'z xohishiga ko'ra talabalar safidan chetlashtirish",
    "tiklash": "talabalar safiga qayta tiklash",
}
PURPOSES = ["talab qilingan joyga", "harbiy komissariatga", "soliq inspeksiyasiga", "bankka", "ijtimoiy himoya organlariga", "ish joyiga", "elchixonaga (viza uchun)"]

CATALOG = [
    # key, kategoriya, nomi, tavsif, ruxsat etilgan lavozimlar, parametrlar, prefiks, imzo kerakmi
    dict(key="study_cert", cat="Talabalar va dekanat", title="O'qish joyidan ma'lumotnoma", prefix="MT",
         desc="Talaba haqiqatan o'qishini tasdiqlovchi ma'lumotnoma (o'zbek/ingliz). Guruh bo'yicha ommaviy chiqarish mumkin.",
         roles=DEAN_SIDE, params=[("target", "student_or_group"), ("purpose", "select:" + "|".join(PURPOSES)), ("lang", "select:uz|en")]),
    dict(key="transcript", cat="Talabalar va dekanat", title="Akademik ma'lumotnoma (transkript)", prefix="AM",
         desc="Fanlar, kreditlar, 100 ballik, harfli va 5 ballik baholar, GPA (kreditga vaznli) — HEMIS baholaridan avtomatik.",
         roles=DEAN_SIDE, params=[("target", "student")]),
    dict(key="debt_letter", cat="Talabalar va dekanat", title="Kontrakt qarzdorligi: ota-onaga xat", prefix="QX",
         desc="Qarzdor talabalar ota-onasiga rasmiy ogohlantirish. Guruh yoki fakultet bo'yicha bir tugmada barcha qarzdorlarga.",
         roles={"prorektor_moliya", "buxgalteriya", "talabalar", "dekan"}, params=[("target", "student_or_group_or_faculty"), ("deadline", "date")]),
    dict(key="practice", cat="Talabalar va dekanat", title="Amaliyot yo'llanmasi", prefix="AY",
         desc="Talabani malakaviy amaliyotga yo'llash xati (tashkilot, muddat).",
         roles={"dekan", "kafedra", "talabalar"}, params=[("target", "student_or_group"), ("org", "text"), ("start", "date"), ("end", "date")]),
    dict(key="order_student", cat="Buyruqlar", title="Buyruq loyihasi: talabalar harakati", prefix="TH",
         desc="Akademik ta'til, ko'chirish, chetlashtirish, qayta tiklash. Rektor imzosidan keyin kuchga kiradi.",
         roles={"dekan", "prorektor_oquv", "talabalar"}, sign=True,
         params=[("target", "student"), ("action", "select:" + "|".join(STUDENT_ACTIONS)), ("reason", "text"), ("from_date", "date")]),
    dict(key="warn_letter", cat="Talabalar va dekanat", title="Ogohlantirish xati (davomat / o'zlashtirish)", prefix="OX",
         desc="Sababsiz dars qoldirgan yoki fanlardan o'zlashtira olmayotgan talabaga rasmiy ogohlantirish. Faktlar bazadan avtomatik.",
         roles={"talabalar", "dekan", "prorektor_oquv"}, params=[("target", "student"), ("basis", "select:davomat|akademik")]),
    dict(key="reprimand", cat="Buyruqlar", title="Buyruq loyihasi: hayfsan e'lon qilish", prefix="HB",
         desc="Sababsiz dars qoldirish chegarasidan oshgan talabaga hayfsan. Rektor imzosidan keyin kuchga kiradi.",
         roles={"talabalar", "prorektor_oquv"}, sign=True, params=[("target", "student"), ("reason", "text")]),
    dict(key="retake_sheet", cat="O'quv jarayoni", title="Otrabotka (qayta topshirish) varaqasi", prefix="OV", hidden=True,
         desc="Talabalar markazidan beriladi: fan, o'qituvchi, muddat, baho va imzo uchun joy, QR.",
         roles={"talabalar", "tyutor", "dekan"}, params=[("retake", "retake")]),
    dict(key="leave_order", cat="Buyruqlar", title="Mehnat ta'tili berish to'g'risida buyruq", prefix="ShT",
         desc="Xodimga yillik mehnat ta'tili. Kadrlar loyihalaydi, rektor imzolaydi.",
         roles={"kadrlar"}, sign=True, params=[("staff", "staff"), ("start", "date"), ("days", "number")]),
    dict(key="exam_sheet", cat="O'quv jarayoni", title="Yakuniy nazorat qaydnomasi", prefix="QN",
         desc="Guruh + fan bo'yicha qaydnoma: oraliq (30) + yakuniy (70) = jami ball, harf va 5 ballik baho, o'zlashtirish foizi. 'Barcha fanlar' — butun guruh paketi.",
         # yakuniy nazoratni imtihon bo'limi o'tkazadi, Akademik faoliyatni boshqarish bo'limi tashkil qiladi (akademik qoidalar)
         roles={"dekan", "kafedra", "oqituvchi", "prorektor_oquv", "imtihon", "akademik"}, params=[("group", "group"), ("subject", "subject")]),
    dict(key="debtors_list", cat="O'quv jarayoni", title="Akademik qarzdorlar ro'yxati", prefix="AQ",
         desc=f"{AR.PASS} balldan past (o'zlashtirilmagan) fanlari bor talabalar, fanlar kesimida, qayta topshirish muddati bilan.",
         roles={"dekan", "kafedra", "prorektor_oquv"}, params=[("deadline", "date")]),
    dict(key="load", cat="O'quv jarayoni", title="O'quv yuklama taqsimoti", prefix="OY",
         desc="Kafedra o'qituvchilari yuklamasi, stavka, fanlar va guruhlar — ortiqcha/kam yuklama belgilanadi.",
         roles={"kafedra", "dekan", "prorektor_oquv"}, params=[("department", "department")]),
    dict(key="minutes", cat="Rektorat va ijro nazorati", title="Majlis bayonnomasi", prefix="MB",
         desc="Majlis yozuvidan rasmiy bayonnoma: eshitildi, qaror qilindi, mas'ullar va muddatlar.",
         roles=LEAD, params=[("meeting", "meeting")]),
    dict(key="exec_notice", cat="Rektorat va ijro nazorati", title="Ijro nazorati: muddati o'tgan topshiriq", prefix="IN",
         desc="Muddati o'tgan topshiriq bo'yicha mas'ulga rasmiy xat. 'Barchasi' — hamma qarzdor ijrochilarga birdan.",
         roles={"rektor", "kengash"}, params=[("task", "task")]),
    dict(key="memo", cat="Rektorat va ijro nazorati", title="Xizmat xati", prefix="XX",
         desc="Qabul qiluvchi, mavzu va asosiy fikrlarni yozing — ISFT Core rasmiy uslubda matnni tuzadi (mahalliy AI).",
         roles=EVERYONE_STAFF, params=[("recipient", "text"), ("subject_line", "text"), ("points", "textarea"), ("use_ai", "check")]),
    dict(key="work_cert", cat="Kadrlar", title="Ish joyidan ma'lumotnoma", prefix="IJ",
         desc="Xodim ishlashini tasdiqlovchi ma'lumotnoma, ixtiyoriy ravishda o'rtacha oylik bilan.",
         roles={"kadrlar"}, params=[("staff", "staff"), ("with_salary", "check"), ("purpose", "select:" + "|".join(PURPOSES))]),
    dict(key="invitation", cat="Xalqaro aloqalar", title="Invitation letter (viza uchun taklifnoma)", prefix="INV",
         desc="Xorijiy mehmon/professor uchun ingliz tilidagi rasmiy taklifnoma.",
         roles={"xalqaro", "rektor"}, params=[("guest", "text"), ("guest_org", "text"), ("country", "text"), ("purpose_en", "text"),
                                              ("passport", "text"), ("start", "date"), ("end", "date"), ("expenses", "select:ISFT|guest")]),
]
CAT = {t["key"]: t for t in CATALOG}

LABELS = {"target": "Talaba / guruh", "purpose": "Qayerga taqdim etish uchun", "lang": "Til", "deadline": "Muddat", "org": "Tashkilot",
          "start": "Boshlanish sanasi", "end": "Tugash sanasi", "action": "Buyruq turi", "reason": "Asos / sabab", "from_date": "Sanadan boshlab",
          "staff": "Xodim", "days": "Kunlar soni", "group": "Guruh", "subject": "Fan", "department": "Kafedra", "meeting": "Majlis",
          "task": "Topshiriq", "recipient": "Kimga", "subject_line": "Mavzu", "points": "Asosiy fikrlar", "use_ai": "Matnni ISFT Core tuzsin (AI)",
          "with_salary": "O'rtacha oylikni ko'rsatish", "guest": "Mehmon F.I.Sh.", "guest_org": "Mehmon tashkiloti", "country": "Davlat",
          "purpose_en": "Tashrif maqsadi (inglizcha)", "basis": "Asos", "retake": "Otrabotka", "passport": "Pasport raqami (ixtiyoriy)", "expenses": "Xarajatlarni kim qoplaydi"}
DEFAULTS = {"deadline": (TODAY + dt.timedelta(days=21)).isoformat(), "start": (TODAY + dt.timedelta(days=14)).isoformat(),
            "end": (TODAY + dt.timedelta(days=42)).isoformat(), "from_date": TODAY.isoformat(), "days": "", "lang": "uz"}

def catalog_for(ctx: Ctx):
    out = []
    for t in CATALOG:
        if t.get("hidden"): continue   # faqat tegishli modul ichidan beriladi
        out.append({"key": t["key"], "cat": t["cat"], "title": t["title"], "desc": t["desc"], "sign": t.get("sign", False),
                    "allowed": ctx.role.key in t["roles"],
                    "params": [{"name": n, "type": ty, "label": LABELS.get(n, n), "default": DEFAULTS.get(n)} for n, ty in t["params"]]})
    return out

# ---------------- ko'lam (scope) ----------------
def _groups_sql(ctx: Ctx):
    sc, u = ctx.role.scope, ctx.user
    if sc == "fakultet": return f"g.faculty_id={int(u['faculty_id'])}"
    if sc == "kafedra": return f"g.department_id={int(u['department_id'])}"
    if sc == "o'qituvchi": return f"g.id IN (SELECT group_id FROM teacher_groups WHERE teacher_id={int(u['teacher_id'])})"
    return "1=1"

def lookup(con, ctx: Ctx, kind: str, q: str = "", group_id: int = 0):
    # qidiruv faqat shu turdagi maydoni bor shablonga ruxsati bo'lgan lavozimga ochiq (shaxsiy ma'lumot sizib chiqmasin)
    allowed = {r for t in CATALOG for _, ty in t["params"] if kind in str(ty) for r in t["roles"]}
    if ctx.role.key not in allowed:
        audit(con, ctx, f"hujjat qidiruvi: {kind}", "docs", False)
        raise AccessDenied("⛔ Bu ma'lumotni qidirish sizning lavozimingiz uchun ochiq emas.")
    q = f"%{q.strip()}%"
    if kind == "student":
        return db.rows(con, f"""SELECT s.id, s.full_name || ' · ' || g.name || ' · ' || s.hemis_id label FROM students s JOIN groups_ g ON g.id=s.group_id
            WHERE {ctx.student_scope('s')} AND (s.full_name LIKE ? OR s.hemis_id LIKE ? OR g.name LIKE ?) ORDER BY s.full_name LIMIT 15""", (q, q, q))
    if kind == "group":
        return db.rows(con, f"SELECT g.id, g.name || ' · ' || g.course || '-kurs · ' || g.direction label FROM groups_ g WHERE {_groups_sql(ctx)} ORDER BY g.name")
    if kind == "faculty":
        w = f"id={int(ctx.user['faculty_id'])}" if ctx.role.scope == "fakultet" else "1=1"
        return db.rows(con, f"SELECT id, name label FROM faculties WHERE {w}")
    if kind == "subject":
        w = f" AND teacher_id={int(ctx.user['teacher_id'])}" if ctx.role.scope == "o'qituvchi" else ""
        return db.rows(con, f"SELECT DISTINCT subject id, subject label FROM teacher_groups WHERE group_id=?{w}", (group_id,))
    if kind == "department":
        w = {"kafedra": f"id={int(ctx.user['department_id'] or 0)}", "fakultet": f"faculty_id={int(ctx.user['faculty_id'] or 0)}"}.get(ctx.role.scope, "1=1")
        return db.rows(con, f"SELECT id, name label FROM departments WHERE {w}")
    if kind == "meeting":
        return db.rows(con, "SELECT id, title || ' · ' || date label FROM meetings WHERE COALESCE(status,'')!='qoralama' ORDER BY date DESC")
    if kind == "task":
        return db.rows(con, "SELECT id, assignee || ': ' || substr(text,1,70) || ' (muddat ' || due || ')' label FROM tasks WHERE status NOT IN ('bajarildi','qoralama') AND due<? ORDER BY due",
                       (TODAY.isoformat(),))
    if kind == "staff":
        return db.rows(con, "SELECT id, full_name || ' · ' || unit || ' · ' || position label FROM staff WHERE full_name LIKE ? ORDER BY full_name LIMIT 15", (q,))
    return []

def _student(con, ctx, sid):
    s = db.one(con, f"""SELECT s.*, g.name grp, g.course, g.direction, g.level glevel, f.name faculty, f.dean, d.name dept
        FROM students s JOIN groups_ g ON g.id=s.group_id JOIN faculties f ON f.id=s.faculty_id JOIN departments d ON d.id=g.department_id
        WHERE s.id=? AND {ctx.student_scope('s')}""", (int(sid),))
    if not s: raise AccessDenied("⛔ Bu talaba sizning ko'lamingizda emas yoki topilmadi. So'rov audit jurnaliga yozildi.")
    return s

def _group(con, ctx, gid):
    g = db.one(con, f"SELECT g.*, f.name faculty, f.dean FROM groups_ g JOIN faculties f ON f.id=g.faculty_id WHERE g.id=? AND {_groups_sql(ctx)}", (int(gid),))
    if not g: raise AccessDenied("⛔ Bu guruh sizning ko'lamingizda emas. So'rov audit jurnaliga yozildi.")
    return g

def _expand_students(con, ctx, p, debt_only=False):
    """target: 's:ID' | 'g:ID' | 'f:ID' -> talabalar ro'yxati (ko'lam tekshiruvi bilan)."""
    tgt = str(p.get("target") or "")
    kind, _, val = tgt.partition(":")
    if kind == "s": ids = [int(val)]
    elif kind == "g": ids = [r["id"] for r in db.rows(con, "SELECT id FROM students WHERE group_id=? ORDER BY full_name", (_group(con, ctx, val)["id"],))]
    elif kind == "f":
        if ctx.role.scope == "fakultet" and int(val) != int(ctx.user["faculty_id"]): raise AccessDenied("⛔ Boshqa fakultet. So'rov audit jurnaliga yozildi.")
        ids = [r["id"] for r in db.rows(con, "SELECT id FROM students WHERE faculty_id=? ORDER BY group_id, full_name", (int(val),))]
    else: raise ValueError("Talaba yoki guruhni tanlang")
    out = [_student(con, ctx, i) for i in ids]
    if debt_only: out = [s for s in out if s["payment_type"] == "kontrakt" and s["contract_amount"] > s["paid_amount"]]
    if not out: raise ValueError("Tanlangan ko'lamda mos talaba topilmadi")
    return out

# ---------------- ro'yxatga olish ----------------
def _next_reg(con, prefix):
    n = db.one(con, "SELECT COUNT(*) n FROM documents WHERE reg_no LIKE ?", (f"{prefix}-26/%",))["n"] + 1
    return f"{prefix}-26/{n:04d}"

class Issuer:
    def __init__(self, con, ctx, tpl, base_url):
        self.con, self.ctx, self.tpl, self.base = con, ctx, tpl, base_url.rstrip("/")
        self.doc = Document(); B.setup(self.doc); self.items = []
    def page(self, holder, lang="uz", title=None):
        if self.items: self.doc.add_page_break()
        reg = _next_reg(self.con, self.tpl["prefix"]) if not self.items else self._bump(self.items[-1]["reg_no"])
        code = secrets.token_hex(4).upper()
        self.items.append({"reg_no": reg, "code": code, "holder": holder, "title": title or self.tpl["title"]})
        B.letterhead(self.doc, lang)
        today = dt.date.today()  # hujjat haqiqiy berilgan sana bilan chiqadi
        B.regline(self.doc, reg, d_en(today) if lang == "en" else d_uz(today), lang)
        return reg, code
    def _bump(self, reg):
        pre, n = reg.rsplit("/", 1); return f"{pre}/{int(n)+1:04d}"
    def qr(self, lang="uz"):
        it = self.items[-1]
        note = ("This document was generated from the institute's information system. Scan the QR code to verify its authenticity."
                if lang == "en" else "Hujjat institut axborot tizimi ma'lumotlari asosida shakllantirildi. Haqiqiyligini QR-kod orqali tekshiring.")
        B.footer_qr(self.doc, f"{self.base}/verify/{it['code']}", it["code"], note)
    def save(self, params):
        OUT.mkdir(parents=True, exist_ok=True)
        first = self.items[0]["reg_no"].replace("/", "-")
        fname = f"{first}{'_paket' + str(len(self.items)) if len(self.items) > 1 else ''}.docx"
        self.doc.save(OUT / fname)
        status = "loyiha" if self.tpl.get("sign") else "berilgan"
        now = dt.datetime.now().isoformat(timespec="seconds")
        for it in self.items:
            self.con.execute("""INSERT INTO documents(reg_no,kind,title,holder,created_by,creator_role,created_at,status,verify_code,file,params)
                VALUES(?,?,?,?,?,?,?,?,?,?,?)""", (it["reg_no"], self.tpl["key"], it["title"], it["holder"], self.ctx.user["id"], self.ctx.role.title,
                now, status, it["code"], fname, json.dumps(params, ensure_ascii=False)))
        self.con.commit()
        audit(self.con, self.ctx, f"hujjat: {self.tpl['title']}", "docs", True, f"{len(self.items)} ta · {self.items[0]['reg_no']} · {self.items[0]['holder']}")
        return {"file": fname, "count": len(self.items), "regs": [i["reg_no"] for i in self.items[:50]], "status": status}

# ---------------- shablonlar ----------------
def _years(s):
    start = 2026 - int(s["course"]) + 1
    return start, start + (2 if s["glevel"] == "magistr" else 4)

def g_study_cert(I, p):
    lang = p.get("lang") or "uz"; purpose = p.get("purpose") or PURPOSES[0]
    for s in _expand_students(I.con, I.ctx, p):
        I.page(s["full_name"], lang)
        y0, y1 = _years(s)
        if lang == "en":
            B.title(I.doc, "CERTIFICATE OF ENROLMENT")
            B.para(I.doc, f"This is to certify that {s['full_name']} (student ID {s['hemis_id']}) is a full-time "
                   f"{'Master' if s['glevel'] == 'magistr' else 'Bachelor'}'s student in year {s['course']} of the {s['direction']} programme, "
                   f"group {s['grp']}, Faculty of {s['faculty']}, ISFT Institute, for the {ACAD_YEAR} academic year.")
            B.para(I.doc, f"Period of study: September {y0} – June {y1}. Mode of study: full-time. "
                   f"Basis of study: {'state grant' if s['payment_type'] == 'grant' else 'tuition contract'}.")
            B.para(I.doc, "This certificate is issued upon the student's request for submission to the relevant authority.")
            B.signature(I.doc, "Dean of the Faculty", short(s["dean"]), "en")
        else:
            B.title(I.doc, "MA'LUMOTNOMA")
            B.para(I.doc, f"Ushbu ma'lumotnoma {s['full_name']}ga (HEMIS ID: {s['hemis_id']}) shu haqda berildiki, u haqiqatan ham "
                   f"ISFT institutining {s['faculty']} fakulteti «{s['direction']}» {'magistratura mutaxassisligi' if s['glevel'] == 'magistr' else 'bakalavriat ta`lim yo`nalishi'.replace('`', chr(39))} "
                   f"{s['course']}-kurs {s['grp']}-guruh talabasi bo'lib, kunduzgi ta'lim shaklida "
                   f"{'davlat granti' if s['payment_type'] == 'grant' else 'to`lov-kontrakt'.replace('`', chr(39))} asosida tahsil olmoqda.")
            B.para(I.doc, f"O'qish muddati: {y0}-yil sentabr — {y1}-yil iyun. Joriy o'quv yili: {ACAD_YEAR}.")
            B.para(I.doc, f"Ma'lumotnoma {purpose} taqdim etish uchun berildi.")
            B.signature(I.doc, "Fakultet dekani", short(s["dean"]))
        I.qr(lang)

def g_transcript(I, p):
    s = _expand_students(I.con, I.ctx, p)[0]
    I.page(s["full_name"])
    B.title(I.doc, "AKADEMIK MA'LUMOTNOMA", "(transkript)")
    t = [("F.I.Sh.", s["full_name"]), ("HEMIS ID", s["hemis_id"]), ("Fakultet", s["faculty"]), ("Yo'nalish", s["direction"]),
         ("Kurs / guruh", f"{s['course']}-kurs, {s['grp']}"), ("Ta'lim shakli / asosi", f"kunduzgi, {s['payment_type']}")]
    B.table(I.doc, ["Ma'lumot", ""], t, widths=[5, 12], size=10.5)
    done = None   # yakunlangan semestr: (o'zlashtirilgan kredit, jami kredit, GPA)
    for sem, label in [(0, "2025-2026 o'quv yili, bahorgi semestr (yakuniy)"), (1, f"{ACAD_YEAR} o'quv yili, kuzgi semestr (joriy natija)")]:
        rows = db.rows(I.con, "SELECT subject, score FROM grades WHERE student_id=? AND semester=? ORDER BY subject", (s["id"], sem))
        if not rows: continue
        p_ = I.doc.add_paragraph(); B.run(p_, label, 11, True, B.RGB_TEAL_DARK)
        data = []
        for i, r in enumerate(rows, 1):
            g5, word = grade5(r["score"]); data.append((i, r["subject"], CREDITS, r["score"], letter(r["score"]), f"{g5} ({word})"))
        B.table(I.doc, ["№", "Fan", "Kredit", "Ball (100)", "Harf", "Baho (5)"], data, widths=[1, 7, 1.6, 2.2, 1.4, 3.8], size=10)
        if sem == 0:
            done = (sum(CREDITS for r in rows if r["score"] >= PASS), CREDITS * len(rows), AR.gpa([(CREDITS, grade5(r["score"])[0]) for r in rows]))
    if done:
        B.para(I.doc, f"Yakunlangan semestr bo'yicha o'zlashtirilgan kreditlar: {done[0]} / {done[1]}. GPA (5 ballik): {done[2]:.2f}.", indent=False, size=10.5, bold=True)
    B.para(I.doc, f"Baholash shkalasi (100 ballik → 5 baho → harf): {AR.SCALE_TEXT}. Fan kamida {PASS} ball bilan o'zlashtirilganda "
           "uning krediti to'liq hisoblanadi.", indent=False, size=9.5)
    B.para(I.doc, f"{AR.GPA_FORMULA}; {AR.CREDIT_NOTE}.", indent=False, size=9.5)
    B.signature(I.doc, "Fakultet dekani", short(s["dean"]))
    I.qr()

def g_debt_letter(I, p):
    deadline = p.get("deadline") or DEFAULTS["deadline"]
    for s in _expand_students(I.con, I.ctx, p, debt_only=True):
        debt = s["contract_amount"] - s["paid_amount"]
        I.page(s["full_name"])
        p_ = I.doc.add_paragraph(); p_.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        B.run(p_, f"{s['full_name']}ning\nota-onasi (qonuniy vakili)ga", 12, True)
        B.title(I.doc, "Kontrakt to'lovi bo'yicha qarzdorlik haqida", None)
        B.para(I.doc, "Hurmatli ota-ona!", indent=False, bold=True)
        B.para(I.doc, f"Farzandingiz {s['full_name']} ISFT institutining {s['faculty']} fakulteti {s['course']}-kurs {s['grp']}-guruhida "
               f"to'lov-kontrakt asosida tahsil olmoqda. {ACAD_YEAR} o'quv yili uchun shartnoma summasi {s['contract_amount']:,} so'm".replace(",", " ")
               + f", shundan {s['paid_amount']:,} so'm to'langan.".replace(",", " "))
        B.para(I.doc, f"Bugungi kunda qarzdorlik {debt:,} so'mni tashkil etadi.".replace(",", " "), bold=True)
        B.para(I.doc, f"Qarzdorlikni {d_uz(deadline)}gacha to'lashingizni so'raymiz. Belgilangan muddatda to'lov amalga oshirilmasa, "
               "to'lov-kontrakt shartnomasi shartlariga muvofiq choralar ko'rilishi, jumladan farzandingizni talabalar safidan chetlashtirish "
               "masalasi ko'rib chiqilishi mumkin. To'lovni bo'lib to'lash bo'yicha savollar bo'lsa, buxgalteriyaga murojaat qiling.")
        B.para(I.doc, f"To'lov uchun: shartnoma raqami va HEMIS ID ({s['hemis_id']}) ko'rsatilishi shart. Murojaat uchun: {B.INST['phone']}.")
        B.signature(I.doc, "Moliya-iqtisod ishlari bo'yicha prorektor")
        I.qr()

def g_practice(I, p):
    org = (p.get("org") or "").strip() or "____________________"
    for s in _expand_students(I.con, I.ctx, p):
        I.page(s["full_name"])
        p_ = I.doc.add_paragraph(); p_.alignment = WD_ALIGN_PARAGRAPH.RIGHT; B.run(p_, f"{org}\nrahbariyatiga", 12, True)
        B.title(I.doc, "AMALIYOT YO'LLANMASI")
        B.para(I.doc, f"ISFT instituti {s['faculty']} fakulteti «{s['direction']}» yo'nalishi {s['course']}-kurs {s['grp']}-guruh talabasi "
               f"{s['full_name']} o'quv rejasiga muvofiq {d_uz(p.get('start') or DEFAULTS['start'])}dan {d_uz(p.get('end') or DEFAULTS['end'])}gacha "
               f"malakaviy amaliyot o'tash uchun Sizning tashkilotingizga yuboriladi.")
        B.para(I.doc, "Talabaga amaliyot rahbari biriktirilishini, amaliyot yakunida esa tavsifnoma va amaliyot kundaligi tasdiqlab berilishini so'raymiz.")
        B.signature(I.doc, "Fakultet dekani", short(s["dean"]))
        p_ = I.doc.add_paragraph(); B.run(p_, "✂ - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -", 9, False, B.RGB_GREY)
        p_ = I.doc.add_paragraph(); B.run(p_, "QAYTARMA QISM. ", 10.5, True); B.run(p_, f"Talaba {short(s['full_name'])} amaliyotga {d_uz(p.get('start') or DEFAULTS['start'])}da "
            "qabul qilindi. Amaliyot rahbari: ______________________  Imzo: ________  M.O.", 10.5)
        I.qr()

def _agree(doc, who):
    doc.add_paragraph(); p = doc.add_paragraph(); B.run(p, "KELISHILDI:", 10.5, True, B.RGB_TEAL_DARK)
    for w in who:
        p = doc.add_paragraph(); B.run(p, f"{w}  _______________", 10.5)

def g_order_student(I, p):
    s = _expand_students(I.con, I.ctx, p)[0]
    act = p.get("action") or "akademik_tatil"
    if act not in STUDENT_ACTIONS: raise ValueError("Noma'lum buyruq turi")
    reason = (p.get("reason") or "").strip()
    I.page(s["full_name"], title=f"Buyruq loyihasi: {STUDENT_ACTIONS[act]}")
    B.title(I.doc, "BUYRUQ (LOYIHA)", "Talabalar harakati to'g'risida")
    basis = {"akademik_tatil": "talabaning arizasi va tibbiy/oilaviy holatni tasdiqlovchi hujjat",
             "kochirish": "talabaning arizasi va qabul qiluvchi OTMning roziligi",
             "chetlashtirish_tolov": "buxgalteriyaning qarzdorlik to'g'risidagi ma'lumotnomasi va fakultet dekanining bildirgisi",
             "chetlashtirish_xohish": "talabaning arizasi", "tiklash": "talabaning arizasi va fakultet dekanining taqdimnomasi"}[act]
    B.para(I.doc, f"«Oliy ta'lim to'g'risida»gi qonunchilik, institut Ustavi va ichki nizomlariga muvofiq, {basis} asosida")
    p_ = I.doc.add_paragraph(); p_.alignment = WD_ALIGN_PARAGRAPH.CENTER; B.run(p_, "BUYURAMAN:", 12, True)
    debt = s["contract_amount"] - s["paid_amount"]
    B.para(I.doc, f"1. {s['faculty']} fakulteti «{s['direction']}» yo'nalishi {s['course']}-kurs {s['grp']}-guruh talabasi {s['full_name']} "
           f"(HEMIS ID {s['hemis_id']}) ga {d_uz(p.get('from_date') or TODAY)}dan boshlab {STUDENT_ACTIONS[act]}." + (f" Sabab: {reason}." if reason else ""))
    if act == "chetlashtirish_tolov":
        B.para(I.doc, f"2. Buxgalteriya: talabaning {debt:,} so'm qarzdorligini hisob-kitobda qayd etsin.".replace(",", " "))
    B.para(I.doc, f"{'3' if act == 'chetlashtirish_tolov' else '2'}. Fakultet dekanati ushbu o'zgarishni HEMIS tizimida 3 ish kuni ichida aks ettirsin.")
    B.para(I.doc, f"{'4' if act == 'chetlashtirish_tolov' else '3'}. Buyruq ijrosini nazorat qilish o'quv ishlari bo'yicha prorektor zimmasiga yuklansin.")
    p_ = I.doc.add_paragraph(); B.run(p_, f"Asos: {basis}.", 11, False, italic=True)
    B.signature(I.doc, "Rektor", B.INST["rector_short"])
    p_ = I.doc.add_paragraph(); B.run(p_, f"Loyiha kiritdi: {I.ctx.role.title}  _______________", 10.5)
    _agree(I.doc, ["O'quv ishlari bo'yicha prorektor", "Yuriskonsult", f"Fakultet dekani ({short(s['dean'])})"])
    I.qr()

def g_warn_letter(I, p):
    from . import student_ops as OPS
    s = _expand_students(I.con, I.ctx, p)[0]
    basis = p.get("basis") or "davomat"
    if basis not in ("davomat", "akademik"): raise ValueError("Asos noto'g'ri")
    f = OPS.student_facts(I.con, s["id"])
    I.page(s["full_name"], title=f"Ogohlantirish xati ({basis})")
    p_ = I.doc.add_paragraph(); p_.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    B.run(p_, f"{s['faculty']} fakulteti {s['course']}-kurs {s['grp']}-guruh talabasi\n{s['full_name']}ga\n(nusxasi: ota-onasi / qonuniy vakiliga)", 11.5, True)
    B.title(I.doc, "OGOHLANTIRISH", "davomat bo'yicha" if basis == "davomat" else "o'zlashtirish bo'yicha")
    if basis == "davomat":
        B.para(I.doc, f"Registrator ofisi ma'lumotlariga ko'ra, Siz {ACAD_YEAR} o'quv yilining joriy semestrida "
               f"jami {f['unexcused']} soat mashg'ulotni sababsiz qoldirgansiz (sababli qoldirilgan {f['excused']} soat hisobga olinmagan).")
        B.para(I.doc, "Mashg'ulotlarga muntazam qatnashish talabaning asosiy majburiyatlaridan biridir. Sababsiz qoldirishlar davom etsa, "
               "institut ichki tartib qoidalariga muvofiq intizomiy choralar (hayfsan, talabalar safidan chetlashtirish masalasini ko'rib chiqish) qo'llanilishi mumkin.")
    else:
        fl = ", ".join(f"{x['subject']} ({x['score']} ball)" for x in f["fails"]) or "—"
        B.para(I.doc, f"Joriy semestr natijalariga ko'ra Sizning JPA ko'rsatkichingiz {f['gpa5']} (5 ballik), o'zlashtirilmagan fanlar: {fl}.")
        B.para(I.doc, "Hatto umumiy ko'rsatkich yetarli bo'lsa ham, o'zlashtirilmagan fanlar akademik qarzdorlikka va keyingi kursga o'tkazilmaslikka olib kelishi mumkin. "
               f"Qayta topshirish (otrabotka) tartibi bo'yicha tyutoringiz yoki Registrator ofisiga ({AR.REGISTRAR_ROOMS_TEXT}) murojaat qiling.")
    B.para(I.doc, "Ushbu ogohlantirish bilan tanishganingizni imzongiz bilan tasdiqlang.")
    B.signature(I.doc, "Registrator ofisi boshlig'i")
    p_ = I.doc.add_paragraph(); B.run(p_, "Tanishdim: ____________________  (talaba imzosi)        Sana: «___» __________ 20___ y.", 10.5)
    I.qr()

def g_reprimand(I, p):
    from . import student_ops as OPS
    s = _expand_students(I.con, I.ctx, p)[0]
    f = OPS.student_facts(I.con, s["id"])
    reason = (p.get("reason") or "").strip() or f"joriy semestrda {f['unexcused']} soat mashg'ulotni sababsiz qoldirgani"
    I.page(s["full_name"], title="Buyruq loyihasi: hayfsan e'lon qilish")
    B.title(I.doc, "BUYRUQ (LOYIHA)", "Talabaga intizomiy jazo qo'llash to'g'risida")
    B.para(I.doc, "Institut Ustavi va ichki tartib qoidalariga muvofiq, Registrator ofisining bildirgisi asosida")
    p_ = I.doc.add_paragraph(); p_.alignment = WD_ALIGN_PARAGRAPH.CENTER; B.run(p_, "BUYURAMAN:", 12, True)
    B.para(I.doc, f"1. {s['faculty']} fakulteti {s['course']}-kurs {s['grp']}-guruh talabasi {s['full_name']} (HEMIS ID {s['hemis_id']})ga "
           f"{reason} uchun HAYFSAN e'lon qilinsin.")
    B.para(I.doc, "2. Tyutor talaba bilan suhbat o'tkazsin va natijasini Registrator ofisiga ma'lum qilsin.")
    B.para(I.doc, "3. Buyruq ijrosini nazorat qilish o'quv ishlari bo'yicha prorektor zimmasiga yuklansin.")
    B.signature(I.doc, "Rektor", B.INST["rector_short"])
    p_ = I.doc.add_paragraph(); B.run(p_, f"Loyiha kiritdi: {I.ctx.role.title}  _______________", 10.5)
    _agree(I.doc, ["O'quv ishlari bo'yicha prorektor", "Yuridik bo'lim", f"Fakultet dekani ({short(s['dean'])})"])
    I.qr()

def g_retake_sheet(I, p):
    r = db.one(I.con, "SELECT * FROM retakes WHERE id=?", (int(p.get("retake") or 0),))
    if not r: raise ValueError("Otrabotka topilmadi")
    s = _student(I.con, I.ctx, r["student_id"])
    t = db.one(I.con, "SELECT full_name FROM teachers WHERE id=?", (r["teacher_id"],)) if r["teacher_id"] else None
    I.page(s["full_name"], title=f"Otrabotka varaqasi: {r['subject']}")
    B.title(I.doc, "OTRABOTKA (QAYTA TOPSHIRISH) VARAQASI", f"{ACAD_YEAR} o'quv yili · joriy semestr")
    B.table(I.doc, ["Ko'rsatkich", "Ma'lumot"], [
        ("Talaba", f"{s['full_name']} (HEMIS ID {s['hemis_id']})"), ("Fakultet / guruh", f"{s['faculty']} · {s['grp']}"),
        ("Fan", r["subject"]), ("O'qituvchi", t["full_name"] if t else "—"), ("Sabab", r["reason"] or "—"),
        ("Avvalgi ball", str(r["score_old"]) if r["score_old"] is not None else "—"),
        ("Topshirish muddati", d_uz(r["due_at"][:10]) + (f", soat {r['due_at'][11:16]}" if len(r["due_at"] or "") > 10 else ""))],
        widths=[4.5, 11.5], size=10)
    B.para(I.doc, f"Varaqa o'qituvchi tomonidan to'ldiriladi va belgilangan muddatda Registrator ofisiga ({AR.REGISTRAR_ROOMS_TEXT}) qaytariladi. "
           "Muddat o'tsa, tyutorga ogohlantirish topshirig'i yuboriladi.", size=10.5)
    B.table(I.doc, ["Topshirilgan sana", "Ball (100 ballik)", "O'qituvchi imzosi"], [("«___» ________ 20___", "", "")], widths=[5.5, 5, 5.5], size=11)
    B.signature(I.doc, "Registrator ofisi")
    I.qr()

def g_leave_order(I, p):
    st = db.one(I.con, "SELECT * FROM staff WHERE id=?", (int(p.get("staff") or 0),))
    if not st: raise ValueError("Xodimni tanlang")
    start = dt.date.fromisoformat(p.get("start") or DEFAULTS["start"])
    # Mehnat kodeksi: kamida 21 kalendar kun; pedagog xodimlar uchun uzaytirilgan ta'til (VM 263-son, 2023: 56 kun) — institut nizomi bilan tasdiqlansin
    days = int(p.get("days") or (56 if st["unit"] == "Professor-o'qituvchi" else 21))
    end = start + dt.timedelta(days=days - 1)
    I.page(st["full_name"], title="Buyruq loyihasi: mehnat ta'tili")
    B.title(I.doc, "BUYRUQ (LOYIHA)", "Mehnat ta'tili berish to'g'risida")
    B.para(I.doc, "O'zbekiston Respublikasi Mehnat kodeksiga va ta'tillar jadvaliga muvofiq, xodimning arizasi asosida")
    p_ = I.doc.add_paragraph(); p_.alignment = WD_ALIGN_PARAGRAPH.CENTER; B.run(p_, "BUYURAMAN:", 12, True)
    B.para(I.doc, f"1. {st['unit']} — {st['position']} {st['full_name']}ga {d_uz(start)}dan {d_uz(end)}gacha {days} kalendar kunlik "
           "yillik asosiy mehnat ta'tili berilsin.")
    B.para(I.doc, "2. Buxgalteriya ta'til haqini belgilangan tartibda hisoblab, ta'til boshlanishidan oldin to'lab bersin.")
    B.para(I.doc, "3. Ta'til davrida xodimning vazifalarini bajarish bo'lim boshlig'i tomonidan taqsimlansin.")
    p_ = I.doc.add_paragraph(); B.run(p_, "Asos: xodimning arizasi, ta'tillar jadvali.", 11, False, italic=True)
    B.signature(I.doc, "Rektor", B.INST["rector_short"])
    p_ = I.doc.add_paragraph(); B.run(p_, "Loyiha kiritdi: Kadrlar bo'limi  _______________", 10.5)
    _agree(I.doc, ["Bosh buxgalter", "Yuriskonsult"])
    I.qr()

def g_exam_sheet(I, p):
    g = _group(I.con, I.ctx, p.get("group") or 0)
    subj = p.get("subject") or "*"
    allowed = [r["label"] for r in lookup(I.con, I.ctx, "subject", group_id=g["id"])]
    subjects = allowed if subj == "*" else [subj]
    if not subjects or any(x not in allowed for x in subjects): raise AccessDenied("⛔ Bu fan sizga biriktirilmagan. So'rov audit jurnaliga yozildi.")
    for sb in subjects:
        tch = db.one(I.con, "SELECT t.full_name FROM teacher_groups tg JOIN teachers t ON t.id=tg.teacher_id WHERE tg.group_id=? AND tg.subject=?", (g["id"], sb))
        rows = db.rows(I.con, """SELECT s.full_name, s.hemis_id, gr.score FROM students s JOIN grades gr ON gr.student_id=s.id
            WHERE s.group_id=? AND gr.subject=? AND gr.semester=1 ORDER BY s.full_name""", (g["id"], sb))
        I.page(f"{g['name']} · {sb}", title=f"Qaydnoma: {g['name']} — {sb}")
        B.title(I.doc, "YAKUNIY NAZORAT QAYDNOMASI", f"{ACAD_YEAR} o'quv yili, kuzgi semestr")
        B.table(I.doc, ["Fakultet", "Guruh", "Fan", "O'qituvchi"], [(g["faculty"], f"{g['name']} ({g['course']}-kurs)", sb, short(tch["full_name"]) if tch else "—")], size=10)
        data, cnt, nadmit = [], {5: 0, 4: 0, 3: 0, 2: 0}, 0
        for i, r in enumerate(rows, 1):
            g5, w = grade5(r["score"]); cnt[g5] += 1
            o, y = AR.split_score(r["score"], f"{r['hemis_id']}|{sb}")
            admitted = o >= AR.ORALIQ_MIN
            nadmit += not admitted
            data.append((i, r["full_name"], r["hemis_id"], o, y if admitted else "kiritilmagan", r["score"], letter(r["score"]), f"{g5} ({w})", ""))
        B.table(I.doc, ["№", "Talaba F.I.Sh.", "HEMIS ID", f"Oraliq ({AR.ORALIQ_MAX})", f"Yakuniy ({AR.YAKUNIY_MAX})", "Jami (100)", "Harf", "Baho", "Imzo"],
                data, widths=[0.7, 4.8, 2.4, 1.4, 1.6, 1.3, 0.9, 2.3, 1.6], size=8.5)
        n = max(1, len(rows))
        B.para(I.doc, f"Jami: {len(rows)} nafar. «A'lo» — {cnt[5]}, «yaxshi» — {cnt[4]}, «qoniqarli» — {cnt[3]}, «qoniqarsiz» — {cnt[2]}"
               + (f" (shundan yakuniy nazoratga kiritilmagan — {nadmit})" if nadmit else "") + ". "
               f"O'zlashtirish: {round(100 * (n - cnt[2]) / n, 1)}%, sifat ko'rsatkichi: {round(100 * (cnt[5] + cnt[4]) / n, 1)}%.", indent=False, size=10.5)
        B.para(I.doc, f"Oraliq nazorat: maksimal {AR.ORALIQ_MAX}, minimal {AR.ORALIQ_MIN} ball; yakuniy nazorat: maksimal {AR.YAKUNIY_MAX}, "
               f"minimal {AR.YAKUNIY_MIN} ball. Yakuniy nazoratga oraliq nazoratdan kamida {AR.ORALIQ_MIN} ball ({AR.ADMIT_PCT}%) to'plagan talaba kiritiladi; "
               f"fan kamida {PASS} ball bilan o'zlashtirilgan hisoblanadi. Shkala: {AR.SCALE_TEXT}. Yakuniy nazoratni fan bo'yicha "
               "mashg'ulot olib bormagan professor-o'qituvchi yoki imtihon bo'limi o'tkazadi.", indent=False, size=9)
        B.signature(I.doc, "Imtihon oluvchi (imtihon bo'limi)")
        B.signature(I.doc, "Fakultet dekani", short(g["dean"]))
        I.qr()

def g_debtors_list(I, p):
    deadline = p.get("deadline") or DEFAULTS["deadline"]
    rows = db.rows(I.con, f"""SELECT f.name faculty, g.name grp, s.full_name, s.hemis_id, GROUP_CONCAT(gr.subject || ' (' || gr.score || ')', '; ') subj, COUNT(*) n
        FROM students s JOIN groups_ g ON g.id=s.group_id JOIN faculties f ON f.id=s.faculty_id JOIN grades gr ON gr.student_id=s.id AND gr.semester=1 AND gr.score<{PASS}
        WHERE {I.ctx.student_scope('s')} GROUP BY s.id ORDER BY f.name, g.name, s.full_name""")
    I.page(I.ctx.scope_label(I.con))
    B.title(I.doc, "AKADEMIK QARZDORLAR RO'YXATI", f"{ACAD_YEAR} o'quv yili, kuzgi semestr · {I.ctx.scope_label(I.con)}")
    B.table(I.doc, ["№", "Guruh", "Talaba", "HEMIS ID", "Qarzdor fanlar (ball)", "Soni"],
            [(i, r["grp"], r["full_name"], r["hemis_id"], r["subj"], r["n"]) for i, r in enumerate(rows, 1)], widths=[0.8, 2.2, 4.8, 2.8, 5.6, 1], size=8.5)
    B.para(I.doc, f"Jami {len(rows)} nafar talaba, {sum(r['n'] for r in rows)} ta fan bo'yicha qarzdor. Qayta topshirish muddati: {d_uz(deadline)}gacha. "
           "Kafedralar qayta topshirish jadvalini 3 ish kuni ichida dekanatga taqdim etsin.", indent=False, size=10.5)
    B.signature(I.doc, "Fakultet dekani" if I.ctx.role.scope == "fakultet" else I.ctx.role.title)
    I.qr()

def g_load(I, p):
    did = int(p.get("department") or 0)
    if not any(int(r["id"]) == did for r in lookup(I.con, I.ctx, "department")): raise AccessDenied("⛔ Bu kafedra sizning ko'lamingizda emas.")
    d = db.one(I.con, "SELECT d.*, f.name faculty FROM departments d LEFT JOIN faculties f ON f.id=d.faculty_id WHERE d.id=?", (did,))
    ts = db.rows(I.con, """SELECT t.*, (SELECT GROUP_CONCAT(DISTINCT tg.subject) FROM teacher_groups tg WHERE tg.teacher_id=t.id) subj,
        (SELECT COUNT(DISTINCT tg.group_id) FROM teacher_groups tg WHERE tg.teacher_id=t.id) ng FROM teachers t WHERE department_id=? ORDER BY t.load_hours DESC""", (did,))
    I.page(d["name"])
    p_ = I.doc.add_paragraph(); p_.alignment = WD_ALIGN_PARAGRAPH.RIGHT; B.run(p_, "TASDIQLAYMAN\nO'quv ishlari bo'yicha prorektor\n_______________", 11, True)
    B.title(I.doc, "O'QUV YUKLAMA TAQSIMOTI", f"«{d['name']}» kafedrasi · {ACAD_YEAR} o'quv yili")
    data = []
    for i, t in enumerate(ts, 1):
        st = round(t["load_hours"] / LOAD_NORM, 2)
        flag = "ortiqcha" if st > 1.5 else "kam" if st < 0.75 else "me'yorda"
        data.append((i, t["full_name"], t["position"], t["degree"], t["ng"], (t["subj"] or "—").replace(",", ", "), t["load_hours"], st, flag))
    B.table(I.doc, ["№", "F.I.Sh.", "Lavozim", "Daraja", "Guruh", "Fanlar", "Soat", "Stavka", "Holat"], data,
            widths=[0.7, 3.8, 2.3, 1.4, 1.1, 4.2, 1.2, 1.3, 1.6], size=8)
    tot = sum(t["load_hours"] for t in ts)
    B.para(I.doc, f"Kafedra bo'yicha jami yuklama: {tot} soat ({round(tot / LOAD_NORM, 2)} stavka, me'yor: 1 stavka = {LOAD_NORM} soat). "
           f"Ortiqcha yuklama: {sum(1 for r in data if r[8] == 'ortiqcha')} nafar, kam yuklama: {sum(1 for r in data if r[8] == 'kam')} nafar.", indent=False, size=10.5)
    B.signature(I.doc, "Kafedra mudiri", short(d["head"]))
    I.qr()

def g_minutes(I, p):
    m = db.one(I.con, "SELECT * FROM meetings WHERE id=?", (int(p.get("meeting") or 0),))
    if not m: raise ValueError("Majlisni tanlang")
    ts = db.rows(I.con, "SELECT * FROM tasks WHERE meeting_id=? AND status!='qoralama' ORDER BY COALESCE(due,'9999'), id", (m["id"],))
    I.page(m["title"], title=f"Bayonnoma: {m['title']}")
    B.title(I.doc, f"BAYONNOMA", f"{m['title']} · {d_uz(m['date'])}")
    lines = [l.strip() for l in (m["transcript"] or "").splitlines() if l.strip()]
    speakers = []
    for l in lines:
        if ":" in l[:60]:
            who = l.split(":", 1)[0].strip()
            if who not in speakers and len(who) < 50: speakers.append(who)
    B.para(I.doc, f"Raislik qildi: {speakers[0] if speakers else 'Rektor'}.  Kotib: rektor devoni.", indent=False)
    B.para(I.doc, "Qatnashdilar: " + (", ".join(speakers[1:]) if len(speakers) > 1 else "rektorat a'zolari") + ".", indent=False)
    B.para(I.doc, "KUN TARTIBI: " + "; ".join(dict.fromkeys(t["text"][:70] for t in ts[:5])) + ("." if ts else " joriy masalalar."), indent=False, size=11)
    p_ = I.doc.add_paragraph(); B.run(p_, "ESHITILDI:", 12, True, B.RGB_TEAL_DARK)
    for l in lines[1:] if len(lines) > 1 else lines:
        if ":" in l[:60]:
            who, txt = l.split(":", 1); q = I.doc.add_paragraph(); B.run(q, who.strip() + ": ", 11, True); B.run(q, txt.strip(), 11)
    p_ = I.doc.add_paragraph(); B.run(p_, "QAROR QILINDI:", 12, True, B.RGB_TEAL_DARK)
    B.table(I.doc, ["№", "Topshiriq", "Mas'ul", "Muddat", "Holat"],
            [(i, t["text"], t["assignee"] or "biriktirilmagan", d_uz(t["due"]) if t["due"] else "aytilmagan", t["status"]) for i, t in enumerate(ts, 1)] or [("—", "Topshiriq qayd etilmagan", "", "", "")],
            widths=[0.8, 8, 4, 3, 2], size=9.5)
    B.para(I.doc, "Topshiriqlar ijrosi ISFT Core tizimida nazoratga olindi; muddati o'tganlar haqida mas'ullarga avtomatik eslatma yuboriladi.", indent=False, size=10.5)
    B.signature(I.doc, "Majlis raisi")
    B.signature(I.doc, "Kotib")
    I.qr()

def g_exec_notice(I, p):
    tid = str(p.get("task") or "")
    q = "SELECT t.*, m.title meeting, m.date mdate FROM tasks t JOIN meetings m ON m.id=t.meeting_id WHERE t.status NOT IN ('bajarildi','qoralama') AND t.due<?"
    ts = db.rows(I.con, q + ("" if tid == "*" else " AND t.id=?"), (TODAY.isoformat(),) if tid == "*" else (TODAY.isoformat(), int(tid or 0)))
    if not ts: raise ValueError("Muddati o'tgan topshiriq topilmadi")
    for t in ts:
        late = (TODAY - dt.date.fromisoformat(t["due"])).days
        I.page(t["assignee"], title=f"Ijro nazorati: {t['assignee']}")
        p_ = I.doc.add_paragraph(); p_.alignment = WD_ALIGN_PARAGRAPH.RIGHT; B.run(p_, f"{t['assignee']}ga", 12, True)
        B.title(I.doc, "Topshiriq ijrosi to'g'risida")
        B.para(I.doc, f"{d_uz(t['mdate'])}dagi «{t['meeting']}»da Sizga quyidagi topshiriq {d_uz(t['due'])}gacha muddat bilan berilgan edi:")
        B.para(I.doc, f"«{t['text']}»", bold=True)
        B.para(I.doc, f"Bugungi kunga qadar topshiriq ijrosi bo'yicha ma'lumot taqdim etilmagan (muddatdan {late} kun o'tdi). "
               "Topshiriq ijrosini ta'minlash va kechikish sabablari haqida 3 ish kuni ichida yozma tushuntirish berishingiz so'raladi. "
               "Ijro holati ISFT Core tizimida qayd etib boriladi.")
        B.signature(I.doc, "Rektor", B.INST["rector_short"])
        I.qr()

async def ai_memo_text(recipient, subject, points):
    from . import ai
    msgs = [{"role": "system", "content": "Sen OTM devonxonasi xodimisan. O'zbek (lotin) tilida rasmiy xizmat xati matnini yoz: 2-4 xatboshi, "
             "faqat asosiy matn (murojaat, sarlavha va imzosiz). Berilgan faktlardan tashqari raqam, sana yoki ism to'qima."},
            {"role": "user", "content": f"Kimga: {recipient}\nMavzu: {subject}\nAsosiy fikrlar:\n{points}"}]
    try:
        return (await ai.llm_once(msgs, max_tokens=450)).strip()
    except Exception:
        return None

def g_memo(I, p):
    rec = (p.get("recipient") or "").strip() or "____________"; sub = (p.get("subject_line") or "").strip() or "____________"
    body = (p.get("_ai_text") or "").strip() or (p.get("points") or "").strip()
    I.page(rec, title=f"Xizmat xati: {sub}")
    p_ = I.doc.add_paragraph(); p_.alignment = WD_ALIGN_PARAGRAPH.RIGHT; B.run(p_, f"{rec}ga", 12, True)
    p_ = I.doc.add_paragraph(); B.run(p_, f"Mavzu: {sub}", 11.5, True, B.RGB_TEAL_DARK); I.doc.add_paragraph()
    for chunk in [c.strip() for c in body.split("\n") if c.strip()]:
        B.para(I.doc, chunk.lstrip("-•* "))
    B.signature(I.doc, I.ctx.role.title)
    p_ = I.doc.add_paragraph(); B.run(p_, f"Ijrochi: {I.ctx.user['full_name']} · tel. {B.INST['phone']}", 9, False, B.RGB_GREY)
    I.qr()

def g_work_cert(I, p):
    st = db.one(I.con, "SELECT * FROM staff WHERE id=?", (int(p.get("staff") or 0),))
    if not st: raise ValueError("Xodimni tanlang")
    I.page(st["full_name"])
    B.title(I.doc, "MA'LUMOTNOMA")
    B.para(I.doc, f"Ushbu ma'lumotnoma {st['full_name']}ga shu haqda berildiki, u haqiqatan ham ISFT institutida {st['unit']} — "
           f"{st['position']} lavozimida {d_uz(st['hired'])}dan buyon asosiy ish joyi sifatida ishlab kelmoqda.")
    if p.get("with_salary") in (True, "true", "1", 1, "on"):
        B.para(I.doc, f"Oxirgi 6 oy bo'yicha o'rtacha oylik ish haqi (soliqlar ushlangunga qadar): {st['salary']:,} so'm.".replace(",", " "))
    B.para(I.doc, f"Ma'lumotnoma {p.get('purpose') or PURPOSES[0]} taqdim etish uchun berildi.")
    B.signature(I.doc, "Kadrlar bo'limi boshlig'i")
    I.qr()

def g_invitation(I, p):
    guest = (p.get("guest") or "").strip() or "__________"
    I.page(guest, "en", title=f"Invitation letter: {guest}")
    B.title(I.doc, "LETTER OF INVITATION")
    B.para(I.doc, "To whom it may concern,", indent=False)
    B.para(I.doc, f"ISFT Institute (Tashkent region, Republic of Uzbekistan) is pleased to invite {guest}"
           f"{', ' + p['guest_org'] if p.get('guest_org') else ''}{', citizen of ' + p['country'] if p.get('country') else ''}"
           f"{', passport No ' + p['passport'] if p.get('passport') else ''}, "
           f"to visit our institute from {d_en(p.get('start') or DEFAULTS['start'])} to {d_en(p.get('end') or DEFAULTS['end'])} "
           f"for the purpose of {(p.get('purpose_en') or 'academic cooperation').strip()}.")
    who = "ISFT Institute will cover accommodation and local transportation during the visit." if (p.get("expenses") or "ISFT") == "ISFT" \
        else "All travel and accommodation expenses will be covered by the guest or the sending institution."
    B.para(I.doc, who + " We kindly ask the relevant consular authorities to issue the necessary visa.")
    B.para(I.doc, f"For any enquiries please contact the International Relations Office: {B.INST['email']}, {B.INST['phone']}.")
    B.signature(I.doc, "Rector", "", "en")
    I.qr("en")

GEN = {"warn_letter": g_warn_letter, "reprimand": g_reprimand, "retake_sheet": g_retake_sheet, "study_cert": g_study_cert, "transcript": g_transcript, "debt_letter": g_debt_letter, "practice": g_practice,
       "order_student": g_order_student, "leave_order": g_leave_order, "exam_sheet": g_exam_sheet, "debtors_list": g_debtors_list,
       "load": g_load, "minutes": g_minutes, "exec_notice": g_exec_notice, "memo": g_memo, "work_cert": g_work_cert, "invitation": g_invitation}

def issue(con, ctx: Ctx, key: str, params: dict, base_url: str):
    tpl = CAT.get(key)
    if not tpl: raise ValueError("Noma'lum shablon")
    if ctx.role.key not in tpl["roles"]:
        audit(con, ctx, f"hujjat: {tpl['title']}", "docs", False)
        raise AccessDenied(f"⛔ «{tpl['title']}»: '{ctx.role.title}' lavozimi bu hujjatni tayyorlay olmaydi. So'rov audit jurnaliga yozildi.")
    I = Issuer(con, ctx, tpl, base_url)
    try:
        GEN[key](I, params)
    except AccessDenied as e:
        audit(con, ctx, f"hujjat: {tpl['title']}", "docs", False, str(e)[:120]); raise
    return I.save({k: v for k, v in params.items() if not k.startswith("_")})

# ---------------- jurnal va imzo ----------------
def registry(con, ctx: Ctx, limit=200):
    w = "1=1" if ctx.role.key == "rektor" else f"created_by={int(ctx.user['id'])}"
    return db.rows(con, f"SELECT id, reg_no, kind, title, holder, creator_role, created_at, status, verify_code, signed_at, file FROM documents WHERE {w} ORDER BY id DESC LIMIT ?", (limit,))

def set_status(con, ctx: Ctx, doc_id: int, action: str):
    d = db.one(con, "SELECT * FROM documents WHERE id=?", (doc_id,))
    if not d: raise ValueError("Hujjat topilmadi")
    if action == "sign":
        if ctx.role.key != "rektor": raise AccessDenied("⛔ Buyruqlarni faqat rektor imzolaydi.")
        if d["status"] != "loyiha": raise ValueError("Faqat loyiha holatidagi hujjat imzolanadi")
        con.execute("UPDATE documents SET status='imzolangan', signed_at=? WHERE id=?", (dt.datetime.now().isoformat(timespec="seconds"), doc_id))
    elif action == "cancel":
        if ctx.role.key != "rektor" and d["created_by"] != ctx.user["id"]: raise AccessDenied("⛔ Hujjatni faqat muallif yoki rektor bekor qiladi.")
        if d["status"] == "imzolangan" and ctx.role.key != "rektor": raise AccessDenied("⛔ Rektor imzolagan buyruqni faqat rektor bekor qiladi.")
        if d["status"] == "bekor": raise ValueError("Hujjat allaqachon bekor qilingan")
        con.execute("UPDATE documents SET status='bekor' WHERE id=?", (doc_id,))
    con.commit(); audit(con, ctx, f"hujjat {action}", "docs", True, d["reg_no"])
    return db.one(con, "SELECT status FROM documents WHERE id=?", (doc_id,))

def can_download(con, ctx: Ctx, fname: str):
    if ctx.role.key in ("rektor",): return True
    return bool(db.one(con, "SELECT 1 FROM documents WHERE file=? AND created_by=?", (fname, ctx.user["id"])))

def verify(con, code: str):
    d = db.one(con, "SELECT reg_no, title, holder, created_at, status, signed_at, kind FROM documents WHERE verify_code=?", (code.upper(),))
    if d and d["status"] == "imzolangan": d["title"] = d["title"].replace("Buyruq loyihasi", "Buyruq")
    if d:  # shaxsiy ma'lumotni yashirish: faqat familiya va initsial
        parts = (d["holder"] or "").split()
        d["holder"] = (parts[0] + " " + " ".join(x[0] + "." for x in parts[1:3])) if parts and CAT.get(d["kind"], {}).get("cat") in ("Talabalar va dekanat", "Kadrlar", "Buyruqlar") else d["holder"]
    return d
