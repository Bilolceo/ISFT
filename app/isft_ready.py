"""«ISFT Ready» — masofaviy ta'limga kirish kursi shabloni (docs/keyslar.md).

Nima uchun: Open University «OU Ready» va FernUni onboarding kurslari tajribasi — birinchi hafta faolligi eng erta xavf signali. Bu modul Kurs
muharririda (app/kurs.py) qisqa kurs yaratadi: platformadan foydalanish, haftalik muddatlar, yordam qayerdan olinadi, akademik halollik,
sun'iy intellektdan mas'uliyatli foydalanish, o'qish odatlari — har bo'limda bilimni tekshirish savoli, oxirida yakuniy tekshiruv (80 %,
urinishlar cheklanmagan). Yakunlagan talaba kabinetida «ISFT Ready» nishoni chiqadi.

Oqim: bo'lim «ISFT Ready shabloni»ni bosadi → qoralama kurs (tahrirlash mumkin) → odatdagidek tasdiqlash va xAPI eksport → talaba kabinetida
(«Mening darslarim») kirish kursi kartasi. Kurs tasdiqlangach «Ortda qolganlar» 1-kurs masofaviy talabalarini kuzatadi: muddat (semestrning
1-haftasi oxiri; kurs semestr o'rtasida e'lon qilinsa — e'londan 7 kun) o'tib, kurs tugatilmagan bo'lsa — «boshlamagan» erta bayrog'i
(lrs_analytics.ready_reasons).

Mazmun original va qisqa; qonunchilik haqida yagona da'vo — yakuniy imtihonlar universitet qoidalariga ko'ra yuzma-yuz o'tkaziladi.
Ruxsat: yaratish — Masofaviy ta'lim bo'limi (masofaviy, masofaviy_xodim); holatni ko'rish — Kurs muharriri ko'rish rollari.
"""
from __future__ import annotations
import datetime as dt, json, threading
from fastapi import APIRouter, Request, HTTPException
from . import clock, db, rbac, lrs_analytics as LA
from .rbac import Ctx, AccessDenied

router = APIRouter()
_con = None
_ctx = None
_lock = threading.RLock()
P = "/api/kurs/isft-ready"
TITLE = "ISFT Ready — masofaviy ta'limga kirish"
META_KEY = "isft_ready_id"

def bind(con, ctx_fn):
    global _con, _ctx
    _con, _ctx = con, ctx_fn


# =============================================================================================
# Mazmun (original, o'zbek lotin)
# =============================================================================================
def _hp(h, p): return ("heading_paragraph", {"heading": h, "html": p})
def _ls(items, style="bulleted"): return ("list", {"style": style, "items": [f"<p>{x}</p>" for x in items]})
def _p(t): return ("paragraph", {"html": f"<p>{t}</p>"})
def _q(btype, question, answers, fb_ok="", fb_bad="", kind="single"):
    return (btype, {"kind": kind, "question": question, "answers": [{"text": t, "correct": bool(c)} for t, c in answers],
                    "feedback_correct": fb_ok, "feedback_wrong": fb_bad})
def _tf(btype, question, true, fb_ok="", fb_bad=""):
    return (btype, {"kind": "truefalse", "question": question, "answers": [{"text": "To'g'ri", "correct": bool(true)}, {"text": "Noto'g'ri", "correct": not true}],
                    "feedback_correct": fb_ok, "feedback_wrong": fb_bad})

LESSONS = [
    ("Platformadan foydalanish", [
        _hp("Talaba kabineti — asosiy kirish nuqtasi",
            "<p>Masofaviy darslaringiz ISFT talaba kabinetidagi <b>«Mening darslarim»</b> bo'limida. Kabinetga HEMIS ID va parolingiz bilan kirasiz; "
            "birinchi kirishda parolni almashtirish so'raladi.</p>"),
        _ls(["Kabinetga kiring va «Mening darslarim»ni oching.",
             "Kursni tanlang: darslar taqvim tartibida, har birida holat va muddat ko'rsatilgan.",
             "«Ochish» darsni yangi oynada ochadi. Tugatilmagan dars «Davom etish» bilan qolgan joyidan ochiladi.",
             "Dars yoki test tugagach, kabinet sahifasini yangilang — natija shu yerda ko'rinadi."], "numbered"),
        _p("Eslatmalarni Telegram'da olish uchun «Mening darslarim» pastidagi <b>«Telegram eslatmalari»</b> kartasida bir martalik kod oling va uni ISFT botiga yuboring."),
        _q("knowledge", "Tugatilmagan darsni qayerdan davom ettirasiz?",
           [("«Mening darslarim» → kurs → «Davom etish»", 1), ("Darsni boshidan qayta yuklab olib", 0), ("Tyutordan yangi havola so'rab", 0)],
           "To'g'ri: dars qolgan joyidan ochiladi.", "Kabinetdagi «Davom etish» tugmasi darsni qolgan joyidan ochadi."),
    ]),
    ("Haftalik ritm va muddatlar", [
        _hp("Har hafta — yangi darslar",
            "<p>Darslar har hafta chiqariladi. Har bir darsning muddati — odatda o'sha haftaning oxiri (yakshanba). «Mening darslarim»dagi "
            "<b>«Bu hafta»</b> bloki joriy haftaning darslari va muddatlarini ko'rsatadi.</p>"),
        _ls(["Hafta boshida «Bu hafta» blokini ko'rib chiqing va o'qish vaqtingizni rejalang.",
             "Muddati o'tgan dars «Kechikkan» deb belgilanadi — iloji boricha tezroq yetib oling.",
             "Bir necha dars ortda qolsangiz, tyutoringiz siz bilan bog'lanadi: bu jazo emas, yordam taklifi.",
             "Yakuniy imtihonlar universitet qoidalariga ko'ra yuzma-yuz o'tkaziladi — sana va joy alohida e'lon qilinadi."]),
        _tf("knowledge", "Dars muddati odatda o'sha haftaning oxiri — yakshanba.", True,
            "To'g'ri. Aniq muddat «Bu hafta» blokida ko'rsatiladi.", "Muddat odatda hafta oxiri (yakshanba); aniq sanasi «Bu hafta» blokida."),
    ]),
    ("Yordam qayerdan olinadi", [
        _hp("Savol bo'lsa — kutmang, yozing",
            "<p>Qiyinchilik paydo bo'lishi bilan murojaat qilish — ortda qolib ketmaslikning eng ishonchli yo'li.</p>"),
        _ls(["<b>Tyutor</b> — o'qish rejasi, kechikish, shaxsiy qiyinchiliklar.",
             "<b>Fan o'qituvchisi</b> — mavzu bo'yicha savollar.",
             "<b>Masofaviy ta'lim bo'limi</b> — kabinet, darsni ochish, natija ko'rinmasligi kabi texnik masalalar.",
             "Murojaatda kurs nomi, dars kodi (masalan, L3) va muammoni qisqa yozing — shunda tezroq yordam berishadi."]),
        _q("knowledge", "Dars ochilmayapti. Kimga murojaat qilasiz?",
           [("Masofaviy ta'lim bo'limiga — kurs nomi va dars kodi bilan", 1), ("Hech kimga — o'zi tuzalib qoladi", 0), ("Kursdoshimga parolimni beraman", 0)],
           "To'g'ri: texnik masalalar — Masofaviy ta'lim bo'limida.", "Texnik muammo bilan Masofaviy ta'lim bo'limiga murojaat qiling."),
    ]),
    ("Akademik halollik", [
        _hp("O'z ishingiz — o'z bilimingiz",
            "<p>Topshiriq va testlar sizning bilimingizni ko'rsatishi kerak. Akademik halollik qoidalarini universitet belgilaydi; ularning buzilishi "
            "ish natijasining bekor qilinishiga va boshqa choralarga olib kelishi mumkin.</p>"),
        _ls(["Topshiriqni o'zingiz bajaring: boshqaga bajartirmang va o'z ishingizni ko'chirish uchun bermang.",
             "Boshqa manbadan foydalansangiz — manbani ko'rsating.",
             "Kabinet parolingizni hech kimga bermang: nomingizdan qilingan har bir harakat sizniki hisoblanadi.",
             "Dars oxiridagi qisqa testlar — o'zingizni tekshirish uchun: qayta urinish mumkin, maqsad — tushunish."]),
        _q("knowledge", "Ishingizda boshqa manbadan iqtibos keltirdingiz. Nima qilish kerak?",
           [("Manbani ko'rsatish", 1), ("Hech narsa — internetdagi matn hammaniki", 0), ("Matnni biroz o'zgartirib, manbasiz yozish", 0)],
           "To'g'ri.", "Har qanday iqtibos va boshqa birovning fikri uchun manba ko'rsatiladi."),
    ]),
    ("Sun'iy intellektdan mas'uliyatli foydalanish", [
        _hp("AI — yordamchi, o'rinbosar emas",
            "<p>Sun'iy intellekt vositalari mavzuni tushuntirish, misol so'rash yoki o'z javobingizni tekshirish uchun foydali bo'lishi mumkin. "
            "Lekin topshiriqni AI'ga yozdirib, o'zingizniki sifatida topshirish — o'zingizni o'qishdan mahrum qilish va akademik halollikni buzish.</p>"),
        _ls(["Fan o'qituvchisi AI'dan qaysi topshiriqda va qanday foydalanishga ruxsat berganini aniqlang; ruxsat bo'lmasa — foydalanmang.",
             "Foydalangan bo'lsangiz — qanday foydalanganingizni ochiq ayting.",
             "AI xato qiladi va mavjud bo'lmagan manbalarni «o'ylab topishi» mumkin: har bir faktni darslik yoki ishonchli manba bilan tekshiring.",
             "Shaxsiy ma'lumotlaringizni (parol, pasport, HEMIS ID) AI vositalariga kiritmang.",
             "Avval o'zingiz urinib ko'ring, keyin AI'dan izoh so'rang — shunda bilim sizda qoladi."]),
        _q("knowledge", "Qaysilar AI'dan mas'uliyatli foydalanish? (bir nechta javob)",
           [("Tushunmagan mavzuni sodda tilda tushuntirib berishini so'rash", 1), ("AI keltirgan faktni darslik bilan tekshirish", 1),
            ("Topshiriqni to'liq AI'ga yozdirib, o'z nomingizdan topshirish", 0), ("Parolingizni AI suhbatiga yozish", 0)],
           "To'g'ri.", "AI — tushunish uchun yordamchi; ishni uning o'rniga topshirish va shaxsiy ma'lumot kiritish mumkin emas.", "multiple"),
    ]),
    ("O'qish odatlari", [
        _hp("Kam-kamdan, lekin muntazam",
            "<p>Masofaviy o'qishda eng katta xavf — ishni oxirgi kunga qoldirish. Quyidagi odatlar ko'p talabaga yordam beradi.</p>"),
        _ls(["Haftada aniq kun va soatlarni o'qish uchun ajrating va ularni taqvimingizga yozing.",
             "Uzoq bitta seans o'rniga 25–45 daqiqalik qisqa seanslar bilan ishlang.",
             "O'qib bo'lgach o'zingizni sinang: dars oxiridagi qisqa testni yeching yoki asosiy fikrlarni yozib chiqing — esga olish mashqi qayta o'qishdan samaraliroq.",
             "O'tgan mavzularni bir necha kundan keyin qisqa takrorlang.",
             "Ortda qolayotganingizni sezsangiz — darhol tyutoringizga yozing."]),
        _q("knowledge", "Qaysi usul o'rganilganni yaxshiroq eslab qolishga yordam beradi?",
           [("O'zini qisqa test bilan sinash", 1), ("Bir xil matnni ko'p marta qayta o'qish", 0), ("Hammasini imtihon oldidan bir kechada o'qish", 0)],
           "To'g'ri: esga olish mashqi (retrieval practice).", "O'zini sinash (esga olish mashqi) qayta o'qishdan samaraliroq."),
    ]),
]
QUIZ_TITLE = "Yakuniy tekshiruv"
QUIZ_SETTINGS = {"pass_pct": 80, "attempts": 0, "shuffle": True, "randomize": True, "reveal": "always",
                 "intro": "8 ta savol. O'tish bali — 80 %. Urinishlar cheklanmagan. Muvaffaqiyatli topshirsangiz, kabinetingizda «ISFT Ready» nishoni paydo bo'ladi."}
QUIZ = [
    _q("question", "Masofaviy darslaringiz qayerda joylashgan?",
       [("Talaba kabineti → «Mening darslarim»", 1), ("Faqat Telegram kanalida", 0), ("O'qituvchining shaxsiy saytida", 0)]),
    _tf("question", "«Bu hafta» bloki joriy haftaning darslari va ularning muddatlarini ko'rsatadi.", True),
    _q("question", "Dars muddati o'tib ketdi. Eng to'g'ri qadam qaysi?",
       [("Iloji boricha tezroq bajarish, kerak bo'lsa tyutorga yozish", 1), ("Keyingi semestrni kutish", 0), ("Darsni tashlab ketish", 0)]),
    _q("question", "Yakuniy imtihonlar qanday o'tkaziladi?",
       [("Universitet qoidalariga ko'ra yuzma-yuz", 1), ("Telegram orqali", 0), ("Uyda, istalgan vaqtda", 0)]),
    _tf("question", "Kabinet parolimni kursdoshimga bersam, bu muammo emas.", False),
    _q("question", "AI'dan foydalanganda nimalar to'g'ri? (bir nechta javob)",
       [("Faktlarni ishonchli manba bilan tekshirish", 1), ("Ruxsat berilgan topshiriqda va buni ochiq aytgan holda foydalanish", 1),
        ("AI yozgan matnni o'z ishim sifatida topshirish", 0)], kind="multiple"),
    _q("question", "Dars ochilmayapti. Kimga murojaat qilasiz?",
       [("Masofaviy ta'lim bo'limiga", 1), ("Hech kimga", 0), ("Kursdoshimga parolimni berib", 0)]),
    _q("question", "Qaysi o'qish rejasi samaraliroq?",
       [("Har hafta belgilangan vaqtda qisqa seanslar va o'zini sinash", 1), ("Semestr oxirida hamma darslarni bir kunda ko'rish", 0),
        ("Faqat qiziq darslarni ochish", 0)]),
]
DESCRIPTION = ("<p>Masofaviy ta'limni boshlayotgan talabalar uchun qisqa kurs (taxminan 40 daqiqa): platformadan foydalanish, haftalik muddatlar, yordam "
               "qayerdan olinadi, akademik halollik, sun'iy intellektdan mas'uliyatli foydalanish va o'qish odatlari. Yakuniy tekshiruvdan o'tgan talaba "
               "«ISFT Ready» nishonini oladi.</p>")
LABELS = {"finish": "Tabriklaymiz! «ISFT Ready» nishoni sizniki", "passed": "Tekshiruvdan o'tdingiz — nishon sizniki"}


# =============================================================================================
# Holat va muddat
# =============================================================================================
def info(con=None) -> dict | None:
    """Joriy «ISFT Ready» kursi (o'chirilmagan): {id, ref, status, published, approved_at, author_id}. Yo'q bo'lsa None."""
    con = con or _con
    try:
        r = db.one(con, "SELECT v FROM ku_meta WHERE k=?", (META_KEY,))
        if not r: return None
        co = db.one(con, "SELECT id, status, approved_at, author_id, deleted FROM ku_courses WHERE id=?", (int(r["v"]),))
    except Exception:
        return None
    if not co or co["deleted"]: return None
    return {"id": co["id"], "ref": f"ku:{co['id']}", "status": co["status"], "published": co["status"] == "tasdiqlangan",
            "approved_at": co["approved_at"], "author_id": co["author_id"]}

def deadline(sem_start: dt.date, con=None) -> dt.date:
    """Muddat: semestrning 1-haftasi oxiri (yakshanba). Kurs undan keyin e'lon qilingan (tasdiqlangan) bo'lsa — e'londan 7 kun (semestr
    o'rtasida yangi kurs paydo bo'lishi bilan butun kurs bir zumda «bayroqli» bo'lib qolmasin)."""
    end1 = LA.monday(sem_start) + dt.timedelta(days=6)
    i = info(con)
    try: ap = dt.date.fromisoformat((i or {}).get("approved_at", "")[:10])
    except (TypeError, ValueError): ap = None
    return max(end1, ap + dt.timedelta(days=7)) if ap else end1

def student_status(con, sid: int) -> dict | None:
    """Talaba kabineti uchun: {ref, title, status: yangi|jarayonda|tugatildi, badge, deadline, done, total, can_open}. Kurs e'lon qilinmagan — None."""
    i = info(con)
    if not i or not i["published"]: return None
    from . import lrs as L
    rows = {r["lesson_ref"]: r for r in db.rows(con, "SELECT lesson_ref, status, best FROM lrs_progress WHERE student_id=? AND course_ref=?", (int(sid), i["ref"]))}
    total = db.one(con, "SELECT COUNT(*) n FROM ku_lessons WHERE course_id=? AND deleted=0", (i["id"],))["n"]
    done = sum(1 for k, r in rows.items() if k and r["status"] in LA.DONE_ST)
    fin = (rows.get("") or {}).get("status") in LA.DONE_ST or (total and done >= total)
    from . import academic_rules as AR
    dl = deadline(dt.date.fromisoformat(AR.term_dates(AR.CURRENT_SEMESTER)[0]), con)
    return {"ref": i["ref"], "title": TITLE, "status": "tugatildi" if fin else "jarayonda" if rows else "yangi", "badge": bool(fin),
            "deadline": dl.isoformat(), "late": (not fin) and clock.today() > dl, "done": total if fin else done, "total": total,
            "can_open": bool(L.package_for(i["ref"], "", approved_only=True))}


# =============================================================================================
# Yaratish
# =============================================================================================
def create(c: Ctx, recreate: bool = False) -> dict:
    """Kurs muharririda «ISFT Ready» qoralamasini yaratadi (mavjud bo'lsa — o'shani qaytaradi; recreate — yangisi, eskisi o'zgarmaydi)."""
    from . import kurs as KU
    cur = info()
    if cur and not recreate: return {"ok": True, "id": cur["id"], "created": False, "status": cur["status"]}
    A = KU._Assets(None)
    with _lock:
        cid = KU.create_course(c, TITLE, DESCRIPTION, None, "isft_ready", first_lesson=False)["id"]
        st = KU.clean_settings({"completion": "view_and_quiz", "sequential": False, "mode": "xapi"})
        _con.execute("UPDATE ku_courses SET settings=?, labels=? WHERE id=?", (json.dumps(st), json.dumps(KU.clean_labels(LABELS), ensure_ascii=False), cid))
        now = clock.now().replace(microsecond=0).isoformat(timespec="seconds")
        def lesson(pos, ltype, title, settings, blocks):
            lid = _con.execute("INSERT INTO ku_lessons(course_id,uid,pos,type,title,settings,rev,updated_at,updated_by) VALUES(?,?,?,?,?,?,1,?,?)",
                               (cid, KU._uid("l"), pos, ltype, title, json.dumps(settings), now, c.user["full_name"])).lastrowid
            for k, (bt, d) in enumerate(blocks, 1):
                _con.execute("INSERT INTO ku_blocks(lesson_id,uid,pos,type,data) VALUES(?,?,?,?,?)",
                             (lid, KU._uid("b"), k, bt, json.dumps(KU.clean_block(bt, d, A), ensure_ascii=False)))
        for i, (t, bl) in enumerate(LESSONS, 1): lesson(i, "blocks", f"{i}. {t}", {}, bl)
        lesson(len(LESSONS) + 1, "quiz", QUIZ_TITLE, KU.clean_quiz(QUIZ_SETTINGS), QUIZ)
        _con.execute("INSERT OR REPLACE INTO ku_meta(k,v) VALUES(?,?)", (META_KEY, str(cid)))
        KU._log(c, cid, "«ISFT Ready» shablonidan yaratildi", "")
        _con.commit()
    rbac.audit(_con, c, "kurs: «ISFT Ready» yaratildi", KU.RES, True, f"kurs #{cid}")
    return {"ok": True, "id": cid, "created": True, "status": "qoralama"}


# =============================================================================================
# HTTP
# =============================================================================================
def C(request: Request) -> Ctx: return _ctx(request)

@router.get(P)
def api_info(request: Request):
    from . import kurs as KU
    c = C(request); KU.guard(c, "«ISFT Ready» holati", KU.ALL)
    i = info()
    out = {"exists": bool(i), "can_create": c.role.key in KU.DEPT}
    if i:
        from . import academic_rules as AR
        start = dt.date.fromisoformat(AR.term_dates(AR.CURRENT_SEMESTER)[0])
        out.update(id=i["id"], status=i["status"], published=i["published"], deadline=deadline(start).isoformat())
        if i["published"] and c.role.key in KU.DEPT + KU.LEAD:      # jamlangan son: nechta 1-kurs masofaviy talaba tugatgan
            n = db.one(_con, """SELECT COUNT(*) n FROM students s JOIN groups_ g ON g.id=s.group_id WHERE s.study_form='masofaviy' AND s.status='faol'
                                AND g.form='masofaviy' AND g.course=1""")["n"]
            f = db.one(_con, "SELECT COUNT(DISTINCT student_id) n FROM lrs_progress WHERE course_ref=? AND lesson_ref='' AND status IN ('otdi','yakunlandi')",
                       (i["ref"],))["n"]
            out.update(students=n, completed=f)
    return out

@router.post(P)
def api_create(request: Request, body: dict | None = None):
    from . import kurs as KU
    c = C(request); KU.guard(c, "«ISFT Ready» yaratish", KU.DEPT)
    return create(c, bool((body or {}).get("recreate")))
