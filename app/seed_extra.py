"""Seed'ni boyitish: majlis bayonnomalari, har bir lavozimga topshiriqlar, tadbirlar, murojaatlar,
qo'shimcha hamkorlar/grantlar, 2-semestr baholari va 3 haftalik audit tarixi.
seed.run() ichidan chaqiriladi. HIKOYA saqlanadi: muddati o'tgan topshiriqlar aynan 3 ta."""
import datetime as dt
from . import db
from .rbac import ROLES

TRANSCRIPTS = {
1: """Institut Kengashi yig'ilishi №3, 28.09.2026. Raislik: rektor.
Rektor: Yangi o'quv yili boshlandi, birinchi oy natijalarini ko'rib chiqamiz. Xalqaro iqtisodiyot va moliya fakulteti 2-kursida oraliq nazorat natijalari past chiqdi.
Xalqaro iqtisodiyot va moliya fakulteti dekani: Sabablarini o'rganamiz, 15-oktabrgacha tahliliy ma'lumotnoma tayyorlab beraman.
O'quv ishlari bo'yicha prorektor: Akkreditatsiya muddati yaqinlashmoqda. O'quv dasturlarini yangilash rejasini 20-oktabrgacha tasdiqlashga kiritaman.
Moliya-iqtisod ishlari bo'yicha prorektor: Kontrakt qarzdorligi 16 foiz atrofida. Guruhlar kesimida undirish rejasini 25-oktabrgacha ishlab chiqamiz.
Kadrlar bo'limi: Ilmiy darajali o'qituvchilar ulushi bo'yicha attestatsiya jadvalini tayyorlaymiz.
Rektor: Barcha topshiriqlar ISFT Core orqali nazoratga olinsin.""",
2: """Rektorat yig'ilishi, 13.10.2026.
Rektor: Xalqaro hamkorlik shartnomalarining bir qismi tugayapti. Latviya va Avstriyadagi hamkor OTMlar bilan uzaytirish xati 30-oktabrgacha yuborilsin.
Xalqaro hamkorlik bo'limi: Tushunarli, xatlar loyihasi tayyor.
Ilmiy ishlar va innovatsiyalar bo'yicha prorektor: Scopus rejasini kafedralar kesimida 10-noyabrgacha taqsimlab chiqaman.
Yoshlar masalalari bo'yicha birinchi prorektor: 2-o'quv binosi isitish tizimi bo'yicha murojaatlar kelgan, xo'jalik bo'limi bilan 6-noyabrgacha hal qilamiz.
Magistratura bo'limi: Dastlabki himoyalar jadvalini oy oxirigacha e'lon qilamiz.""",
3: """Rektorat yig'ilishi, 27.10.2026.
Rektor: Kommunal xarajatlar uch oydan beri rejadan oshib ketyapti. Buxgalteriya sababini 12-noyabrgacha tahlil qilsin.
Buxgalteriya: Hisoblagich ko'rsatkichlari va tariflarni solishtiramiz.
Qabul komissiyasi: 2027 qabul kampaniyasi uchun marketing rejasini 20-noyabrgacha taqdim etamiz.
Registrator ofisi: Qarzdor talabalar bilan individual suhbatlarni 15-noyabrgacha tugatamiz.
Kafedra mudiri (Buxgalteriya hisobi): 2-kurs uchun qo'shimcha konsultatsiya jadvali tuzildi.""",
}
MORE_MEETINGS = [
    ("Xalqaro iqtisodiyot va moliya fakulteti kengashi", "2026-10-06", "Fakultet kengashi",
     """Fakultet kengashi, 06.10.2026. Dekan: 2-kurs guruhlarida davomat 80 foizdan tushib ketgan.
Kafedra mudiri: Korporativ moliya va Moliyaviy matematika fanlaridan qo'shimcha darslar tashkil qilamiz.
O'qituvchi: Oraliq nazoratdan o'ta olmaganlar uchun qayta topshirish jadvalini 1-noyabrgacha beraman.
Dekan: Ota-onalar bilan uchrashuv 8-noyabrda o'tkazilsin."""),
    ("Institut Kengashi yig'ilishi №4", "2026-10-30", "Kengash",
     """Institut Kengashi yig'ilishi №4, 30.10.2026.
Rektor: Birinchi chorak yakunlari. Topshiriqlarning bir qismi muddatida bajarilmagan, mas'ullar yozma tushuntirish bersin.
Kuzatuv kengashi a'zosi: Kengash uchun choraklik KPI hisobotini 25-noyabrgacha ko'rishni istaymiz.
Ilmiy ishlar va innovatsiyalar bo'yicha prorektor: Ikkita grant arizasi Innovatsion rivojlanish agentligiga topshirildi.
Kadrlar bo'limi: O'qituvchilar malaka oshirish rejasi 1-dekabrgacha tasdiqlanadi."""),
    ("Rektorat yig'ilishi", "2026-11-03", "Rektorat",
     """Rektorat yig'ilishi, 03.11.2026.
Rektor: Qishki sessiyaga tayyorgarlik. Imtihon jadvali 18-noyabrgacha e'lon qilinsin.
O'quv ishlari bo'yicha prorektor: Jadval loyihasi tayyor, dekanatlar bilan kelishamiz.
Xalqaro hamkorlik bo'limi: Erasmus+ almashinuv dasturiga 12 nafar talaba tanlovini 28-noyabrgacha o'tkazamiz.
Yoshlar masalalari bo'yicha birinchi prorektor: Institutda yotoqxona yo'q — talabalarga ijara uy topishda yordam (hamkor uy-joy ro'yxati) masalasini o'rganamiz."""),
]
# (meeting_no, assignee, role, text, due, status) — due < 2026-11-04 bo'lsa status "bajarildi" (overdue = 3 bo'lib qoladi)
MORE_TASKS = [
    (1, "Kadrlar bo'limi", "kadrlar", "Ilmiy darajali o'qituvchilar attestatsiya jadvalini tayyorlash", "2026-10-18", "bajarildi"),
    (1, "Moliya-iqtisod ishlari bo'yicha prorektor", "prorektor_moliya", "Kontrakt to'lov muddatlarini bo'lib to'lash tartibini ishlab chiqish", "2026-11-14", "jarayonda"),
    (2, "Magistratura bo'limi", "magistratura", "Magistrlik dastlabki himoyalar jadvalini e'lon qilish", "2026-10-31", "bajarildi"),
    (2, "Xalqaro hamkorlik bo'limi", "xalqaro", "Koreyadagi hamkor OTM bilan qo'shma dastur loyihasini kelishish", "2026-11-25", "jarayonda"),
    (3, "Kafedra mudiri (Buxgalteriya hisobi)", "kafedra", "2-kurs uchun qo'shimcha konsultatsiya jadvalini tasdiqlash", "2026-10-31", "bajarildi"),
    (3, "Qabul komissiyasi", "qabul", "Maktab va kollejlarda ochiq eshiklar kuni jadvalini tuzish", "2026-11-28", "jarayonda"),
    (4, "Kafedra mudiri (Buxgalteriya hisobi)", "kafedra", "Korporativ moliya va Moliyaviy matematika fanlaridan qo'shimcha darslar tashkil qilish", "2026-10-20", "bajarildi"),
    (4, "O'qituvchi (Buxgalteriya hisobi kafedrasi)", "oqituvchi", "Oraliq nazoratdan o'tmaganlar uchun qayta topshirish jadvalini berish", "2026-11-01", "bajarildi"),
    (4, "O'qituvchi (Buxgalteriya hisobi kafedrasi)", "oqituvchi", "Xavf ostidagi talabalar bilan individual konsultatsiya o'tkazish", "2026-11-13", "jarayonda"),
    (4, "Xalqaro iqtisodiyot va moliya fakulteti dekani", "dekan", "2-kurs talabalarining ota-onalari bilan uchrashuv o'tkazish", "2026-11-08", "jarayonda"),
    (5, "Devonxona", "kengash", "Kuzatuv kengashi uchun choraklik KPI hisobotini tayyorlash", "2026-11-25", "jarayonda"),
    (5, "Ilmiy ishlar va innovatsiyalar bo'yicha prorektor", "prorektor_ilmiy", "Innovatsion rivojlanish agentligiga 2 ta grant arizasini topshirish", "2026-10-29", "bajarildi"),
    (5, "Kadrlar bo'limi", "kadrlar", "O'qituvchilar malaka oshirish rejasini tasdiqlash", "2026-12-01", "jarayonda"),
    (5, "Buxgalteriya", "buxgalteriya", "3-chorak moliyaviy hisobotini kengashga taqdim etish", "2026-11-18", "jarayonda"),
    (6, "O'quv ishlari bo'yicha prorektor", "prorektor_oquv", "Qishki sessiya imtihon jadvalini e'lon qilish", "2026-11-18", "jarayonda"),
    (6, "Xalqaro hamkorlik bo'limi", "xalqaro", "Erasmus+ almashinuviga 12 nafar talaba tanlovini o'tkazish", "2026-11-28", "jarayonda"),
    (6, "Yoshlar masalalari bo'yicha birinchi prorektor", "prorektor_yoshlar", "Talabalar uchun ijara uy-joy hamkorlari ro'yxatini tuzish", "2026-11-22", "jarayonda"),
    (6, "Registrator ofisi", "talabalar", "Grant asosida o'qiyotgan talabalar ro'yxatini HEMIS bilan solishtirish", "2026-11-11", "jarayonda"),
    (6, "Magistratura bo'limi", "magistratura", "Ilmiy rahbarlar yuklamasini qayta taqsimlash", "2026-11-21", "jarayonda"),
    (6, "Kafedra mudiri (Buxgalteriya hisobi)", "kafedra", "Kafedra o'qituvchilarining Scopus rejasi bo'yicha hisobot", "2026-11-30", "jarayonda"),
    (6, "O'qituvchi (Buxgalteriya hisobi kafedrasi)", "oqituvchi", "Qishki sessiya uchun test savollarini yangilash", "2026-11-20", "jarayonda"),
]
EVENTS = [
    ("Bilimlar kuni tantanasi", "2026-09-02", "ma'naviy", 1150), ("1-kurs talabalari uchun adaptatsiya treningi", "2026-09-08", "ma'naviy", 380),
    ("Ustoz-shogird uchrashuvi", "2026-09-12", "ma'naviy", 140), ("Sport kuni: yengil atletika", "2026-09-19", "sport", 260),
    ("IT-hakaton \"FinTech 48\"", "2026-09-26", "intellektual", 96), ("Ustozlar va murabbiylar kuni bayrami", "2026-09-30", "ma'naviy", 520),
    ("Shaxmat turniri", "2026-10-03", "sport", 64), ("Ingliz tili debat turniri", "2026-10-07", "intellektual", 88),
    ("Moliyaviy savodxonlik haftaligi", "2026-10-10", "karyera", 310), ("Bank sektori vakillari bilan uchrashuv", "2026-10-14", "karyera", 175),
    ("O'zbek tili bayrami — she'riyat kechasi", "2026-10-21", "ma'naviy", 230), ("Qon topshirish aksiyasi", "2026-10-24", "volontyorlik", 72),
    ("Voleybol bo'yicha fakultetlararo musobaqa", "2026-10-28", "sport", 150), ("Startap pitch-kuni", "2026-10-31", "karyera", 120),
    ("Ekologik aksiya: daraxt ekish", "2026-11-01", "volontyorlik", 210), ("Psixolog bilan ochiq suhbat", "2026-11-03", "ma'naviy", 55),
    ("Karyera yarmarkasi: 25 ta kompaniya", "2026-11-12", "karyera", 0), ("Konstitutsiya kuni viktorinasi", "2026-12-07", "intellektual", 0),
]
APPEALS = [
    ("O'quv jarayoni", "Ba'zi o'qituvchilar dars materiallarini HEMIS'ga yuklamayapti"), ("Turar joy (ijara)", "Ijara uy narxlari juda qimmat"),
    ("Ovqatlanish", "Oshxonada narxlar oshib ketdi"), ("O'quv jarayoni", "Kompyuter xonasida dasturlar eskirgan"),
    ("Moliya", "Kontraktni bo'lib to'lash imkoniyati haqida ma'lumot yo'q"), ("O'quv binosi", "Xonalarda namlik va mog'or bor (1-o'quv binosi)"),
    ("Boshqa", "Avtoturargoh yetishmaydi"), ("O'quv jarayoni", "Ingliz tili guruhlari juda katta"),
    ("Moliya", "To'lov kvitansiyasi kech tasdiqlanyapti"), ("Ovqatlanish", "Vegetarian taomlar yo'q"),
    ("Transport", "Kechki darsdan keyin transport yo'q"), ("O'quv jarayoni", "Imtihon jadvali kech e'lon qilinadi"),
    ("Boshqa", "Wi-Fi o'quv binosida uziladi"), ("O'quv jarayoni", "Kutubxonada elektron bazalarga kirish yo'q"),
    ("Ovqatlanish", "Oshxona jihozlari buzilgan (3-o'quv binosi)"), ("Boshqa", "Hojatxonalar tozaligi"),
    ("O'quv jarayoni", "Amaliyot o'tash joylari bilan ta'minlash"), ("Moliya", "Stipendiya kechikib tushdi"),
    ("Boshqa", "Lift ishlamayapti (bosh bino)"), ("O'quv jarayoni", "Qayta topshirish narxi qimmat"),
    ("O'quv binosi", "Hojatxonada issiq suv yo'q (2-o'quv binosi)"), ("Ovqatlanish", "Bufet erta yopiladi"),
    ("O'quv jarayoni", "Ma'ruzalar yozib olinmaydi"), ("Boshqa", "Sport zal jihozlari yetarli emas"),
    ("O'quv binosi", "Avtoturargohda xavfsizlik kameralari yetarli emas"), ("O'quv jarayoni", "Tanlov fanlari ro'yxati kech chiqdi"),
    ("Boshqa", "Psixologik yordam xonasi kerak"), ("Moliya", "Ijtimoiy himoyaga muhtojlar uchun chegirma"),
    ("O'quv jarayoni", "Ba'zi auditoriyalarda proyektor yo'q"), ("O'quv binosi", "Isitish 3-o'quv binosida ham sust"),
    ("Ovqatlanish", "Oshxonada to'lov kartasi qabul qilinmaydi"), ("Boshqa", "Talabalar klublari uchun xona yo'q"),
]
PARTNERS = [(f"Hamkor OTM — {c} (namuna)", c) for c in ["O'zbekiston", "Janubiy Koreya (2)", "Avstriya (2)", "Turkiya (2)", "Qozog'iston (2)", "Italiya"]]
GRANTS = ["Raqamli moliyaviy xizmatlar inklyuzivligi", "Universitet-sanoat hamkorligi", "Ta'lim sifatini monitoring qilish tizimi",
          "Erasmus+ CBHE: Raqamli universitet", "Qishloq hududlarida tadbirkorlik", "Ochiq ta'lim resurslari", "Kiberxavfsizlik savodxonligi",
          "Islom moliyasi bo'yicha o'quv kursi"]

QUESTIONS = {
    "rektor": ["Qaysi yo'nalishda ortda qolyapmiz?", "Bu hafta nimaga e'tibor berishim kerak?", "Kontrakt qarzdorligi qancha?",
               "Kommunal xarajatlar nega oshdi?", "Muddati o'tgan topshiriqlar kimda?"],
    "kengash": ["Institutning umumiy holati qanday?", "Moliyaviy barqarorlik qanday?"],
    "prorektor_oquv": ["Xalqaro iqtisodiyot va moliya fakulteti 2-kurs o'zlashtirishi", "Davomat eng past guruhlar"],
    "prorektor_ilmiy": ["Scopus maqolalar soni", "2025 yildan beri maqolasi yo'q o'qituvchilar"],
    "prorektor_moliya": ["Byudjet bajarilishi", "Qarzdorlik fakultetlar kesimida"],
    "prorektor_yoshlar": ["Tadbirlar qamrovi", "Hal qilinmagan murojaatlar"],
    "qabul": ["Qabul konversiyasi yo'nalishlar bo'yicha"], "talabalar": ["Qarzdor talabalar soni"],
    "magistratura": ["Dissertatsiya bosqichlari"], "xalqaro": ["Tugayotgan shartnomalar"],
    "buxgalteriya": ["Ish haqi fondi", "Kommunal xarajatlar"], "kadrlar": ["Yangi ishga olinganlar"],
    "dekan": ["Fakultetimda xavf ostidagi talabalar"], "kafedra": ["Kafedra o'qituvchilari yuklamasi"], "oqituvchi": ["Mening guruhlarim natijasi"],
}
VIEWS = {"academic": "o'zlashtirish ko'rsatkichlari", "students": "xavf ostidagi talabalar", "contracts": "kontrakt to'lovlari",
         "finance": "byudjet bajarilishi", "payroll": "ish haqi fondi", "hr": "xodimlar ro'yxati", "science": "ilmiy faoliyat",
         "international": "xalqaro hamkorlik", "admissions": "qabul kampaniyasi", "youth": "yoshlar ishlari", "masters": "magistratura",
         "tasks": "majlis topshiriqlari", "audit": "audit jurnali"}
# rad etiladigan urinishlar (RBAC'ni ko'rsatish uchun)
DENIED = [("oqituvchi", "finance"), ("oqituvchi", "hr"), ("qabul", "payroll"), ("kafedra", "contracts"), ("talabalar", "hr"),
          ("dekan", "payroll"), ("prorektor_yoshlar", "finance"), ("xalqaro", "students"), ("kengash", "hr"), ("magistratura", "finance")]


def run(con, R, TODAY, teachers):
    c = con.cursor()
    for mid, txt in TRANSCRIPTS.items():
        c.execute("UPDATE meetings SET transcript=? WHERE id=?", (txt, mid))
    for t, d, k, tr in MORE_MEETINGS:
        c.execute("INSERT INTO meetings(title,date,kind,transcript) VALUES(?,?,?,?)", (t, d, k, tr))
    for mi, who, role, text, due, st in MORE_TASKS:
        c.execute("INSERT INTO tasks(meeting_id,assignee,assignee_role,text,due,status) VALUES(?,?,?,?,?,?)", (mi, who, role, text, due, st))

    for t, d, k, p in EVENTS:
        c.execute("INSERT INTO events(title,date,kind,participants) VALUES(?,?,?,?)", (t, d, k, p))
    for cat, txt in APPEALS:
        days = R.randint(0, 60)
        st = R.choices(["hal qilindi", "ko'rib chiqilmoqda", "yangi"], [55, 30, 15])[0] if days > 10 else R.choice(["yangi", "ko'rib chiqilmoqda"])
        c.execute("INSERT INTO appeals(date,category,text,status) VALUES(?,?,?,?)", ((TODAY - dt.timedelta(days=days)).isoformat(), cat, txt, st))

    for n, cn in PARTNERS:
        signed = TODAY - dt.timedelta(days=R.randint(60, 900))
        c.execute("INSERT INTO partners(name,country,kind,signed,expires,status,students_exchanged) VALUES(?,?,?,?,?,?,?)",
                  (n, cn, R.choice(["Akademik almashinuv", "Ilmiy hamkorlik", "Qo'shma dastur (2+2)", "Erasmus+ KA171"]),
                   signed.isoformat(), (signed + dt.timedelta(days=1825)).isoformat(), "faol", R.randint(0, 9)))
    for g in GRANTS:
        c.execute("INSERT INTO grants(title,leader_id,funder,amount,status,year) VALUES(?,?,?,?,?,?)",
                  (g + " loyihasi", R.choice(teachers)[0], R.choice(["Innovatsion rivojlanish agentligi", "Erasmus+", "Vazirlik", "Jahon banki", "Xalqaro hamkor"]),
                   R.choice([120, 250, 380, 520, 760, 1100]) * 1_000_000,
                   R.choices(["bajarilmoqda", "ariza berilgan", "yakunlangan", "rad etilgan"], [5, 4, 3, 2])[0], R.choice([2025, 2026])))

    # o'tgan (bahorgi) semestr baholari: gpa_prev atrofida — dinamikani ko'rsatish uchun
    for s in db.rows(con, "SELECT id, gpa_prev FROM students"):
        for g in db.rows(con, "SELECT subject, teacher_id FROM grades WHERE student_id=? AND semester=1", (s["id"],)):
            c.execute("INSERT INTO grades VALUES(?,?,?,?,?)", (s["id"], g["subject"], g["teacher_id"],
                      int(max(8, min(100, R.gauss(s["gpa_prev"], 7)))), 0))

    # 3 haftalik audit tarixi (eng yangisi oxirida bo'lishi uchun vaqt bo'yicha tartiblab yoziladi)
    users = {u["role"]: u for u in db.rows(con, "SELECT id, full_name, role FROM users")}
    log = []
    for day in range(21, 0, -1):
        d = TODAY - dt.timedelta(days=day)
        if d.weekday() == 6: continue
        for role, u in users.items():
            if R.random() > (0.95 if role in ("rektor", "prorektor_oquv", "prorektor_moliya", "dekan") else 0.55): continue
            title = ROLES[role].title
            tg = role not in ("buxgalteriya", "kadrlar") and R.random() < 0.25
            ch = "telegram" if tg else "web"
            t0 = dt.datetime.combine(d, dt.time(R.randint(8, 17), R.randint(0, 59)))
            log.append((t0, u, title, ch, "tizimga kirish", "auth", 1, ""))
            log.append((t0 + dt.timedelta(minutes=1), u, title, ch, "boshqaruv paneli", "kpi", 1, ""))
            allow = [r for r in ROLES[role].allow if r in VIEWS and not (tg and r in ("payroll", "hr"))]
            for k in range(R.randint(1, 4)):
                if allow:
                    r = R.choice(allow)
                    log.append((t0 + dt.timedelta(minutes=3 + k * 4), u, title, ch, VIEWS[r], r, 1, ""))
            if role in QUESTIONS and R.random() < 0.6:
                log.append((t0 + dt.timedelta(minutes=20), u, title, ch, "savol", "chat", 1, R.choice(QUESTIONS[role])))
            if role in ("rektor", "kengash", "prorektor_oquv", "prorektor_moliya") and R.random() < 0.2:
                log.append((t0 + dt.timedelta(minutes=30), u, title, "web", "hisobot: Rahbariyat uchun haftalik brifing", "reports", 1, ""))
    for i, (role, res) in enumerate(DENIED):
        u = users[role]
        t0 = dt.datetime.combine(TODAY - dt.timedelta(days=R.randint(1, 20)), dt.time(R.randint(9, 18), R.randint(0, 59)))
        log.append((t0, u, ROLES[role].title, R.choice(["web", "telegram"]), VIEWS[res], res, 0, ""))
    # Telegram orqali maxfiy ma'lumot so'rash urinishi (kanal cheklovi)
    u = users["rektor"]
    log.append((dt.datetime.combine(TODAY - dt.timedelta(days=2), dt.time(21, 14)), u, ROLES["rektor"].title, "telegram", "ish haqi fondi", "payroll", 0, "telegram kanali"))
    log.sort(key=lambda x: x[0])
    for ts, u, title, ch, act, res, ok, det in log:
        c.execute("INSERT INTO audit_log(ts,user_id,user_name,role,channel,action,resource,allowed,detail) VALUES(?,?,?,?,?,?,?,?,?)",
                  (ts.isoformat(timespec="seconds"), u["id"], u["full_name"], title, ch, act, res, ok, det))
