"""Demo (sun'iy) ma'lumotlar generatori. Haqiqiy shaxslarga aloqasi yo'q.
Ishga tushirish: python -m app.seed
Ichiga rektorga ko'rsatish uchun ataylab "hikoyalar" joylangan:
  * Xalqaro iqtisodiyot va moliya fakulteti 2-kursida o'zlashtirish keskin pasaygan
Tuzilma: ISFT rasmiy tashkiliy tuzilmasi (2024, 04.09.2024 tasdiqlangan) — fakultet, kafedra va yo'nalish nomlari.
  * Kontrakt qarzdorligi ~17%, ayrim guruhlarda yuqori
  * Kengash topshiriqlaridan 3 tasi muddati o'tgan
  * 2 ta xalqaro shartnoma 60 kun ichida tugaydi
  * Kommunal xarajatlar rejadan oshgan
"""
import random, datetime as dt
from . import db

R = random.Random(42)
TODAY = dt.date(2026, 11, 4)

MALE = ["Aziz","Bekzod","Jasur","Sardor","Otabek","Shoxrux","Doniyor","Javohir","Islom","Sherzod","Ulug'bek","Akmal",
        "Bobur","Diyorbek","Firdavs","Abdulloh","Muhammadali","Asadbek","Temur","Nodirbek","Sanjar","Elyor","Rustam","Kamron"]
FEMALE = ["Madina","Dilnoza","Sevara","Nilufar","Gulnoza","Zarina","Shahzoda","Malika","Mohinur","Kamola","Feruza","Nigora",
          "Sabina","Diyora","Munisa","Odina","Laylo","Mubina","Charos","Hilola","Barno","Rayhona","Sitora","Zilola"]
SURN = ["Karimov","Rahimov","Tursunov","Yusupov","Abdullayev","Ismoilov","Qodirov","Nazarov","Ergashev","Sobirov","Xolmatov",
        "Mirzayev","Aliyev","Hasanov","Usmonov","Jo'rayev","Saidov","Normatov","Toshpo'latov","Rashidov","Hamroyev","Bakirov"]
PATR_M = ["Anvar","Baxtiyor","Shavkat","Ravshan","Ilhom","Farhod","Komil","Murod","Odil","Erkin"]
REGIONS = ["Toshkent sh.","Toshkent vil.","Samarqand","Farg'ona","Andijon","Namangan","Qashqadaryo","Surxondaryo","Buxoro","Xorazm","Jizzax","Sirdaryo","Navoiy","Qoraqalpog'iston"]

def person(gender=None):
    g = gender or R.choice("MF")
    s = R.choice(SURN)
    if g == "M":
        return f"{s} {R.choice(MALE)} {R.choice(PATR_M)} o'g'li", g
    return f"{s}a {R.choice(FEMALE)} {R.choice(PATR_M)} qizi", g

def short(full):
    p = full.split()
    return f"{p[0]} {p[1][0]}."

# =====================================================================================================
# ISFT HAQIQIY PROFILI — ochiq manbalardan (2026-11-06 da o'qilgan). Shaxslar (talaba, o'qituvchi, xodim) — SUN'IY.
#   NQAAE pasporti: https://nqaae.uz/en/higher/303974882 (talabalar 26.06.2026, xodimlar 01.05.2026)
#   Narxlar va grantlar: https://isft.uz/en/faq ;  fakultet/yo'nalishlar: https://isft.uz/en/about/structure/faculty
#   Kafedralar: ISFT tashkiliy tuzilmasi (04.09.2024 tasdiqlangan)
# "TAXMIN" deb belgilanganlar manbada yo'q — demo uchun qo'yilgan, institut bilan aniqlashtiriladi.
# =====================================================================================================
PROFILE = {
    # NQAAE: kunduzgi 8 956 / sirtqi 16 478 / masofaviy 3 769 = 29 203 (bakalavr 28 833 + magistr 370) — magistrlar kunduzgi ichida
    "students_by_form": {"kunduzgi": 8956 - 370, "sirtqi": 16478, "masofaviy": 3769},
    "master_students": 370, "teachers": 255, "degree_share": 0.24, "founded": 2016, "accepted_2026": 8184,
    "scopus_total": 62, "buildings": 5, "seats": 7500, "dormitories": 0, "grants_per_year": 300, "grants_social": 50,
    "bcv": 412_000,   # bazaviy hisoblash miqdori (isft.uz/en/faq)
    "tuition_bcv": {"kunduzgi_xalqaro": 50, "kunduzgi": 46, "masofaviy": 25, "magistr": 65,
                    "sirtqi": 25},   # sirtqi narxi saytda ko'rsatilmagan — TAXMIN: masofaviy bilan teng
    "family_discount": 0.10,        # oilada 2+ talaba — har biriga 10%
    "other_staff": 180,             # TAXMIN: professor-o'qituvchilardan tashqari xodimlar
}
FORM_GROUP = {"kunduzgi": ("", 25), "sirtqi": ("S", 32), "masofaviy": ("M", 40)}   # guruh nomi qo'shimchasi, o'rtacha hajmi (TAXMIN)
COURSE_W = [0.29, 0.27, 0.23, 0.21]   # 1-kurs ≈ 2026 qabul (8 184) / jami — TAXMIN taqsimot

# Fakultet → kafedra → bakalavr yo'nalishlari (saytdagi joriy ro'yxat; kafedralar — 2024 tuzilmasi). Vazn — mashhurlik (TAXMIN).
# Tartib muhim: 2-fakultet — "moliya" hikoyasi (2-kurs pasayishi), 4-kafedra — demo kafedra mudiri akkaunti.
FACULTIES = [
    ("Iqtisodiyot va axborot texnologiyalari", [
        ("Iqtisodiyot va kompyuter injiniring", [("Iqtisodiyot", 1.4), ("Bank ishi va audit", 1.2), ("Menejment", 1.0), ("Marketing", 0.8),
                                                 ("Axborot tizimlari va texnologiyalari", 1.0), ("Axborot xavfsizligi", 0.6), ("Xalqaro munosabatlar", 0.7)])]),
    ("Xalqaro iqtisodiyot va moliya", [   # "xalqaro yo'nalishlar" — 50 BHM
        ("Biznes boshqaruvi", [("Biznes va menejment", 1.0)]),
        ("Menejment", [("Moliya sohasida boshqaruv", 1.0)]),
        ("Buxgalteriya hisobi", [("Buxgalteriya hisobi va moliya", 1.1)])]),   # saytda 7 kafedra (2024 dagi "Fundamental iqtisodiy fanlar" yo'q)
    ("Ijtimoiy-gumanitar va tillar", [
        ("Psixologiya va pedagogika", [("Pedagogika", 1.3), ("Psixologiya", 1.3)]),
        ("Gumanitar va tabiiy fanlar", [("Boshlang'ich ta'lim", 1.4), ("Maktabgacha ta'lim", 1.2)]),
        ("Filologiya va tillarni o'qitish", [("Xorijiy til va adabiyoti", 1.2), ("Filologiya va tillarni o'qitish (ingliz tili)", 1.0)])]),
]
INTL_FACULTY = 2
# Magistratura (isft.uz/en/applicants/master): dastur → kafedra raqami (FACULTIES tartibida, 1 dan)
MASTERS = [("Davlat moliyaviy nazorati va auditi", 4), ("Pedagogika", 5), ("Xorijiy til va adabiyoti", 7)]
GROUP_CODE = {"Iqtisodiyot": "IQT", "Bank ishi va audit": "BIA", "Menejment": "MEN", "Marketing": "MRK", "Axborot tizimlari va texnologiyalari": "ATT",
              "Axborot xavfsizligi": "AXV", "Xalqaro munosabatlar": "XM", "Biznes va menejment": "BM", "Moliya sohasida boshqaruv": "MSB",
              "Buxgalteriya hisobi va moliya": "BHM", "Pedagogika": "PED", "Psixologiya": "PSX", "Boshlang'ich ta'lim": "BT", "Maktabgacha ta'lim": "MT",
              "Xorijiy til va adabiyoti": "XTA", "Filologiya va tillarni o'qitish (ingliz tili)": "FIL",
              "Davlat moliyaviy nazorati va auditi": "MAG-DMN", }
SUBJECTS = {
    "Iqtisodiyot": ["Makroiqtisodiyot","Ekonometrika","Statistika","Iqtisodiy tarix","Ingliz tili"],
    "Bank ishi va audit": ["Bank ishi","Pul va kredit","Risk menejmenti","Audit","Ingliz tili"],
    "Menejment": ["Menejment asoslari","Tashkiliy xulq","Statistika","Loyiha boshqaruvi","Ingliz tili"],
    "Marketing": ["Marketing asoslari","Iste'molchi xulqi","Raqamli marketing","Statistika","Ingliz tili"],
    "Axborot tizimlari va texnologiyalari": ["Dasturlash asoslari","Ma'lumotlar bazasi","Tarmoqlar","Oliy matematika","Ingliz tili"],
    "Axborot xavfsizligi": ["Kriptografiya asoslari","Tarmoq xavfsizligi","Operatsion tizimlar","Oliy matematika","Ingliz tili"],
    "Xalqaro munosabatlar": ["Xalqaro munosabatlar nazariyasi","Diplomatiya tarixi","Xalqaro huquq","Mikroiqtisodiyot","Ingliz tili"],
    "Biznes va menejment": ["Menejment asoslari","Biznesni rejalashtirish","Marketing","Statistika","Ingliz tili"],
    "Moliya sohasida boshqaruv": ["Moliya","Korporativ moliya","FinTech asoslari","Moliyaviy matematika","Ingliz tili"],
    "Buxgalteriya hisobi va moliya": ["Buxgalteriya hisobi","Korporativ moliya","Moliyaviy matematika","Moliyaviy hisobot (IFRS)","Ingliz tili"],
    "Pedagogika": ["Umumiy pedagogika","Didaktika","Pedagogik mahorat","Ta'lim texnologiyalari","Ingliz tili"],
    "Psixologiya": ["Umumiy psixologiya","Ijtimoiy psixologiya","Yosh psixologiyasi","Statistika","Ingliz tili"],
    "Boshlang'ich ta'lim": ["Boshlang'ich ta'lim metodikasi","Ona tili","Matematika o'qitish metodikasi","Pedagogika","Ingliz tili"],
    "Maktabgacha ta'lim": ["Maktabgacha pedagogika","Bolalar psixologiyasi","Nutq o'stirish","Pedagogika","Ingliz tili"],
    "Xorijiy til va adabiyoti": ["Amaliy grammatika","Fonetika","Adabiyot tarixi","Tarjima nazariyasi","Ikkinchi xorijiy til"],
    "Filologiya va tillarni o'qitish (ingliz tili)": ["Amaliy grammatika","Til o'qitish metodikasi","Leksikologiya","Tarjima amaliyoti","Akademik yozuv"],
    "Davlat moliyaviy nazorati va auditi": ["Davlat moliyaviy nazorati","Davlat auditi standartlari","Byudjet tizimi","Ilmiy tadqiqot metodologiyasi"],
    "Pedagogika (magistratura)": ["Pedagogik tadqiqot metodlari","Oliy ta'lim pedagogikasi","Ta'lim menejmenti","Ilmiy tadqiqot metodologiyasi"],
    "Xorijiy til va adabiyoti (magistratura)": ["Qiyosiy tilshunoslik","Adabiy tahlil","Diskurs tahlili","Ilmiy tadqiqot metodologiyasi"],
}
# Hamkorlar: isft.uz'da ro'yxat e'lon qilinmagan — haqiqiy universitet nomlari ishlatilmaydi (yolg'on hamkorlik ko'rinmasin). NAMUNA.
COUNTRIES = [(f"Hamkor OTM — {c} (namuna)", c) for c in ["Buyuk Britaniya", "Polsha", "Latviya", "Janubiy Koreya", "Turkiya", "Avstriya",
             "Malayziya", "Litva", "Qozog'iston", "Xitoy", "Ispaniya", "Germaniya"]]

def run():
    if db.DB_PATH.exists():
        db.DB_PATH.unlink()
    con = db.connect(); db.init(con)
    c = con.cursor()

    # --- tuzilma: fakultet → kafedra → yo'nalish × ta'lim shakli × kurs → guruhlar ---
    P = PROFILE
    dept_rows = []   # (did, fi, [(direction, weight)])
    for fi, (fname, depts) in enumerate(FACULTIES, 1):
        dean, _ = person("M" if fi != 3 else "F")
        c.execute("INSERT INTO faculties VALUES(?,?,?)", (fi, fname, dean))
        for dname, directions in depts:
            head, _ = person()
            c.execute("INSERT INTO departments(faculty_id,name,head) VALUES(?,?,?)", (fi, dname, head))
            dept_rows.append((c.lastrowid, fi, directions))
    wsum = sum(w for _, _, ds in dept_rows for _, w in ds)
    group_rows = []   # (gid, did, fi, course, direction, form, size)
    for did, fi, directions in dept_rows:
        for d, w in directions:
            code = GROUP_CODE.get(d, "G")
            for form, total in P["students_by_form"].items():
                suffix, size = FORM_GROUP[form]
                for course in range(1, 5):
                    n = round(total * w / wsum * COURSE_W[course - 1])
                    k = max(1, round(n / size))
                    for gi in range(1, k + 1):
                        cnt = n // k + (1 if gi <= n % k else 0)
                        if cnt <= 0: continue
                        name = f"{code}-{26 - course}{suffix}{gi:02d}"
                        c.execute("INSERT INTO groups_(department_id,faculty_id,name,course,direction,level,form) VALUES(?,?,?,?,?,?,?)",
                                  (did, fi, name, course, d, "bakalavr", form))
                        group_rows.append((c.lastrowid, did, fi, course, d, form, cnt, "bakalavr"))
    # magistratura: 370 talaba, 3 dastur, 2 kurs, kunduzgi
    for prog, dept_no in MASTERS:
        did, fi, _ = dept_rows[dept_no - 1]
        per_course = P["master_students"] // len(MASTERS) // 2
        for course in (1, 2):
            k = max(1, round(per_course / 22))
            for gi in range(1, k + 1):
                cnt = per_course // k + (1 if gi <= per_course % k else 0)
                code = GROUP_CODE.get(prog, "MAG-" + "".join(w[0] for w in prog.split()[:2]).upper())
                c.execute("INSERT INTO groups_(department_id,faculty_id,name,course,direction,level,form) VALUES(?,?,?,?,?,?,?)",
                          (did, fi, f"{code}-{27 - course}{gi:02d}", course, prog, "magistr", "kunduzgi"))
                group_rows.append((c.lastrowid, did, fi, course, prog, "kunduzgi", cnt, "magistr"))

    # --- o'qituvchilar: jami 255, kafedralar bo'yicha guruhlar ulushiga qarab; ilmiy darajalilar ~24% (NQAAE) ---
    load = {did: sum(1 for g in group_rows if g[1] == did) for did, _, _ in dept_rows}
    tot = sum(load.values())
    alloc = {did: max(10, round(P["teachers"] * load[did] / tot)) for did in load}
    while sum(alloc.values()) > P["teachers"]: alloc[max(alloc, key=alloc.get)] -= 1
    while sum(alloc.values()) < P["teachers"]: alloc[max(alloc, key=alloc.get)] += 1
    teachers = []
    for did, fi, _ in dept_rows:
        head = db.one(con, "SELECT head FROM departments WHERE id=?", (did,))["head"]
        for k in range(alloc[did]):
            nm = head if k == 0 else person()[0]
            deg = R.choice(["PhD", "DSc"]) if k == 0 else R.choices(["PhD", "DSc", "—", "Magistr"], [20, 4, 30, 46])[0]
            pos = "Kafedra mudiri" if k == 0 else R.choice(["Dotsent", "Katta o'qituvchi", "Professor"]) if deg in ("PhD", "DSc") else R.choice(["Katta o'qituvchi", "Assistent", "Assistent"])
            c.execute("INSERT INTO teachers(full_name,department_id,faculty_id,degree,position,load_hours,h_index) VALUES(?,?,?,?,?,?,?)",
                      (nm, did, fi, deg, pos, R.randint(560, 980), R.choice([0, 0, 1, 1, 2, 3, 4, 5, 7]) if deg in ("PhD", "DSc") else R.choice([0, 0, 1])))
            teachers.append((c.lastrowid, did, fi))
    # o'qituvchi-guruh-fan
    tg = {}
    skey = lambda d, level: f"{d} (magistratura)" if level == "magistr" and f"{d} (magistratura)" in SUBJECTS else d
    for gid, did, fi, course, d, form, cnt, level in group_rows:
        key = skey(d, level)
        dept_teachers = [t for t in teachers if t[1] == did]
        for subj in SUBJECTS[key]:
            t = R.choice(dept_teachers)
            c.execute("INSERT INTO teacher_groups VALUES(?,?,?)", (t[0], gid, subj))
            tg[(gid, subj)] = t[0]

    # --- talabalar: 29 203 (NQAAE), shakli bo'yicha; narx — BHM × koeffitsiyent (isft.uz) ---
    bcv, tb = P["bcv"], P["tuition_bcv"]
    sid = 0
    day_pool = {}   # kurs → kunduzgi bakalavr talabalar (grant taqsimoti uchun)
    for gid, did, fi, course, d, form, cnt, level in group_rows:
        key = skey(d, level)
        if level == "magistr": price = tb["magistr"] * bcv
        elif form == "kunduzgi": price = (tb["kunduzgi_xalqaro"] if fi == INTL_FACULTY else tb["kunduzgi"]) * bcv
        else: price = tb[form] * bcv
        for _ in range(cnt):
            sid += 1
            nm, g = person()
            amount = price
            if R.random() < 0.04: amount = int(price * (1 - P["family_discount"]))   # oilaviy chegirma
            base = R.gauss(74, 9)
            # HIKOYA: Xalqaro iqtisodiyot va moliya fakulteti 2-kurs keskin pasaygan
            drop = 11 if (fi == 2 and course == 2) else R.uniform(-2, 3)
            gpa = max(35, min(99, base - drop))
            prev = max(40, min(99, base + R.uniform(-2, 2)))
            if form == "masofaviy": att = None                     # masofaviy — auditoriya davomati yo'q
            elif form == "sirtqi": att = max(50, min(100, R.gauss(91, 6) - (12 if gpa < 55 else 0)))   # sessiya davomati
            else: att = max(40, min(100, R.gauss(88, 7) - (9 if (fi == 2 and course == 2) else 0) - (12 if gpa < 55 else 0)))
            paid_ratio = R.choices([1, 0.75, 0.5, 0.25, 0], [72, 10, 9, 5, 4])[0]
            if fi == 2 and course == 2 and R.random() < .15: paid_ratio = 0.25
            status = "faol" if R.random() > 0.01 else "akademik ta'til"
            c.execute("""INSERT INTO students(hemis_id,full_name,group_id,faculty_id,gender,region,payment_type,contract_amount,
                      paid_amount,gpa,attendance,gpa_prev,status,level,study_form) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                      (f"3{R.randint(10**11, 10**12-1)}", nm, gid, fi, g, R.choice(REGIONS), "kontrakt", amount, int(amount * paid_ratio),
                       round(gpa, 1), round(att, 1) if att is not None else None, round(prev, 1), status, level, form))
            if form == "kunduzgi" and level == "bakalavr": day_pool.setdefault(course, []).append((sid, gpa))
            for subj in SUBJECTS[key]:
                c.execute("INSERT INTO grades VALUES(?,?,?,?,?)", (sid, subj, tg[(gid, subj)], int(max(20, min(100, R.gauss(gpa, 8)))), 1))
    # grantlar: har yili 300 (250 umumiy tanlov — eng yuqori natija, 50 ijtimoiy) — faqat kunduzgi bakalavr (isft.uz/en/faq)
    for course, pool in day_pool.items():
        top = [s for s, _ in sorted(pool, key=lambda x: -x[1])[:P["grants_per_year"] - P["grants_social"]]]
        rest = [s for s, _ in pool if s not in set(top)]
        social = R.sample(rest, min(P["grants_social"], len(rest)))
        c.executemany("UPDATE students SET payment_type='grant', contract_amount=0, paid_amount=0 WHERE id=?", [(s,) for s in top + social])
    # magistrlar dissertatsiyasi
    for s in db.rows(con, "SELECT id, faculty_id FROM students WHERE level='magistr'"):
        sup = R.choice([t for t in teachers if t[2] == s["faculty_id"]])[0]
        c.execute("INSERT INTO masters(student_id,supervisor_id,topic,stage) VALUES(?,?,?,?)",
                  (s["id"], sup, R.choice(["Raqamli to'lov tizimlarining rivojlanishi","Kichik biznesni moliyalashtirish",
                   "Bank risklarini baholash modellari","Ta'limda sun'iy intellekt","Soliq ma'muriyatchiligini raqamlashtirish",
                   "IFRS ga o'tish muammolari","E-tijorat bozorining tahlili"]),
                   R.choices(["Mavzu tasdiqlangan","1-bob tayyor","2-bob tayyor","Dastlabki himoya"], [30, 35, 25, 10])[0]))

    # --- ilmiy faoliyat ---
    for t, did, fi in teachers:
        for _ in range(R.choices([0, 1, 2, 3, 4, 6], [25, 25, 20, 15, 10, 5])[0]):
            kind = R.choices(["Scopus","Web of Science","OAK jurnali","Konferensiya tezisi"], [11, 2, 45, 42])[0]   # Scopus jami ~62 (NQAAE)
            c.execute("INSERT INTO publications(teacher_id,title,kind,year,citations) VALUES(?,?,?,?,?)",
                      (t, R.choice(["Raqamli iqtisodiyotda","O'zbekiston bank sektorida","Oliy ta'limda","Kichik biznesda","Moliyaviy bozorlarda"]) + " " +
                       R.choice(["innovatsion yondashuvlar","risklarni boshqarish","raqamli transformatsiya","samaradorlikni baholash","barqaror rivojlanish"]),
                       kind, R.choice([2024, 2025, 2025, 2026, 2026, 2026]), R.randint(0, 25) if kind in ("Scopus","Web of Science") else 0))
    for i in range(14):
        t = R.choice(teachers)[0]
        c.execute("INSERT INTO grants(title,leader_id,funder,amount,status,year) VALUES(?,?,?,?,?,?)",
                  (R.choice(["Raqamli ta'lim platformasi","Moliyaviy savodxonlik","Yashil iqtisodiyot","AI asosida kredit skoring","Mintaqaviy innovatsiyalar"]) + " loyihasi",
                   t, R.choice(["Innovatsion rivojlanish agentligi","Erasmus+","Xalqaro hamkor","Vazirlik"]),
                   R.choice([150, 280, 400, 650, 900]) * 1_000_000, R.choices(["bajarilmoqda","ariza berilgan","yakunlangan","rad etilgan"], [5, 4, 3, 2])[0],
                   R.choice([2025, 2026])))

    # --- xalqaro ---
    for i, (n, cn) in enumerate(COUNTRIES):
        signed = TODAY - dt.timedelta(days=R.randint(300, 1400))
        exp = signed + dt.timedelta(days=R.choice([1095, 1825]))
        if i in (2, 5): exp = TODAY + dt.timedelta(days=R.choice([23, 47]))  # HIKOYA: tez orada tugaydi
        st = "faol" if exp > TODAY else "muddati tugagan"
        c.execute("INSERT INTO partners(name,country,kind,signed,expires,status,students_exchanged) VALUES(?,?,?,?,?,?,?)",
                  (n, cn, R.choice(["Akademik almashinuv","Qo'shma dastur (2+2)","Ilmiy hamkorlik","Erasmus+ KA171"]),
                   signed.isoformat(), exp.isoformat(), st, R.randint(0, 14)))

    # --- qabul (2026) ---
    # 2026 qabul: talaba bo'lganlar = 8 184 (NQAAE accepted_count); ariza berganlar soni — TAXMIN (~1,65 baravar)
    dirs = [(d, fi, w) for (_, fi, ds) in dept_rows for d, w in ds]
    n_acc = P["accepted_2026"]; n_all = int(n_acc * 1.65)
    stats = ["talaba bo'ldi"] * n_acc + R.choices(["tavsiya etildi", "rad etildi", "hujjat topshirdi"], [10, 55, 35], k=n_all - n_acc)
    R.shuffle(stats)
    for st in stats:
        d, fi, _ = R.choices(dirs, [w for _, _, w in dirs])[0]
        day = dt.date(2026, 6, 1) + dt.timedelta(days=min(121, int(abs(R.gauss(45, 25)))))   # qabul: 1 iyun – 30 sentabr (mentalaba.uz)
        c.execute("INSERT INTO applicants(direction,faculty_id,applied,status,score,payment_type) VALUES(?,?,?,?,?,?)",
                  (d, fi, day.isoformat(), st, round(R.uniform(55, 189), 1), R.choices(["kontrakt","grant"], [90, 10])[0]))

    # --- moliya ---
    # TAXMIN (ochiq manbada yo'q): 255 o'qituvchi + ~180 xodim ish haqi, 5 o'quv binosi kommunal xarajati
    cats = {"Ish haqi": 4_600_000_000, "Kommunal xizmatlar": 520_000_000, "Ilmiy faoliyat": 250_000_000,
            "Xo'jalik va ta'mir": 600_000_000, "IT va uskunalar": 380_000_000, "Xalqaro faoliyat": 150_000_000, "Talabalar tadbirlari": 200_000_000}
    for m in range(1, 11):
        for cat, plan in cats.items():
            k = R.uniform(0.86, 1.04)
            if cat == "Kommunal xizmatlar" and m >= 8: k = R.uniform(1.18, 1.31)  # HIKOYA
            c.execute("INSERT INTO budget(month,category,planned,actual) VALUES(?,?,?,?)", (f"2026-{m:02d}", cat, plan, int(plan * k)))

    # --- kadrlar (shaxsiy ma'lumot — faqat kadrlar bo'limiga) ---
    units = ["Rektorat","Buxgalteriya bo'limi","Kadrlar bo'limi","Akademik faoliyat va registrator departamenti","Marketing bo'limi","Xalqaro hamkorlik bo'limi",
             "Xo'jalik va texnik bo'lim","Axborot texnologiyalari bo'limi","Axborot-resurs markazi","Devonxona","Yuridik bo'lim"]
    for t, did, fi in teachers:
        nm = db.one(con, "SELECT full_name, position FROM teachers WHERE id=?", (t,))
        c.execute("INSERT INTO staff(full_name,unit,position,salary,hired,passport) VALUES(?,?,?,?,?,?)",
                  (nm["full_name"], "Professor-o'qituvchi", nm["position"], R.choice([7, 8, 9, 11, 13, 16]) * 1_000_000,
                   (TODAY - dt.timedelta(days=R.randint(100, 3000))).isoformat(), f"AD{R.randint(1000000, 9999999)}"))
    for _ in range(P["other_staff"]):
        nm, _ = person(); u = R.choice(units)
        c.execute("INSERT INTO staff(full_name,unit,position,salary,hired,passport) VALUES(?,?,?,?,?,?)",
                  (nm, u, R.choice(["Bosh mutaxassis","Mutaxassis","Bo'lim boshlig'i","Inspektor"]), R.choice([5, 6, 7, 9, 12]) * 1_000_000,
                   (TODAY - dt.timedelta(days=R.randint(100, 3000))).isoformat(), f"AD{R.randint(1000000, 9999999)}"))

    # --- yoshlar ---
    for t in ["Ma'naviyat soati: Yangi O'zbekiston","Intellektual o'yin \"Zakovat\"","Sport musobaqasi: mini-futbol","Kitobxonlik tanlovi",
              "Volontyorlik aksiyasi","Startap-tashabbuslar haftaligi","Karyera kuni (Career Day)","Debat klubi finali","Bayram konserti"]:
        c.execute("INSERT INTO events(title,date,kind,participants) VALUES(?,?,?,?)",
                  (t, (TODAY - dt.timedelta(days=R.randint(1, 60))).isoformat(), R.choice(["ma'naviy","sport","intellektual","karyera"]), R.randint(40, 420)))
    # yotoqxona: NQAAE pasportiga ko'ra institutda yotoqxona YO'Q — jadval bo'sh qoladi
    for cat, txt in [("Turar joy (ijara)","Institut yaqinida arzon ijara uy topish qiyin"),("O'quv jarayoni","Dars jadvali tez-tez o'zgaradi"),
                     ("Ovqatlanish","Oshxonada navbat juda uzun"),("Transport","Qibraydan Toshkentga qatnov avtobusi kam"),("O'quv jarayoni","Kutubxona shanba kuni yopiq"),
                     ("Boshqa","Sport zalga yozilish qiyin"),("O'quv jarayoni","HEMIS da baho kech chiqyapti"),("O'quv binosi","Isitish tizimi ishlamayapti (2-o'quv binosi)")]:
        c.execute("INSERT INTO appeals(date,category,text,status) VALUES(?,?,?,?)",
                  ((TODAY - dt.timedelta(days=R.randint(0, 30))).isoformat(), cat, txt, R.choice(["yangi","ko'rib chiqilmoqda","hal qilindi"])))

    # --- majlislar va topshiriqlar ---
    meetings = [
        ("Institut Kengashi yig'ilishi №3", "2026-09-28", "Kengash"),
        ("Rektorat yig'ilishi", "2026-10-13", "Rektorat"),
        ("Rektorat yig'ilishi", "2026-10-27", "Rektorat"),
    ]
    fac = db.rows(con, "SELECT * FROM faculties")
    task_seed = [
        (0, "Xalqaro iqtisodiyot va moliya fakulteti dekani", "dekan", "Xalqaro iqtisodiyot va moliya fakulteti 2-kurs talabalari o'zlashtirishi bo'yicha tahliliy ma'lumotnoma tayyorlash", "2026-10-15", "bajarilmagan"),
        (0, "O'quv ishlari prorektori", "prorektor_oquv", "Akkreditatsiya uchun o'quv dasturlarini yangilash rejasini tasdiqlash", "2026-10-20", "bajarilmagan"),
        (0, "Moliya-iqtisod prorektori", "prorektor_moliya", "Kontrakt qarzdorligi bo'yicha guruhlar kesimida reja ishlab chiqish", "2026-10-25", "bajarildi"),
        (1, "Xalqaro aloqalar bo'limi", "xalqaro", "Muddati tugayotgan hamkorlik shartnomalarini uzaytirish xatlarini yuborish", "2026-10-30", "bajarilmagan"),
        (1, "Ilmiy ishlar prorektori", "prorektor_ilmiy", "Scopus maqolalar rejasini kafedralar kesimida taqsimlash", "2026-11-10", "jarayonda"),
        (1, "Yoshlar ishlari prorektori", "prorektor_yoshlar", "2-bino isitish tizimi bo'yicha murojaatni hal qilish", "2026-11-06", "jarayonda"),
        (2, "Qabul bo'limi", "qabul", "2027 qabul kampaniyasi uchun marketing rejasini taqdim etish", "2026-11-20", "jarayonda"),
        (2, "Talabalar bilan ishlash bo'limi", "talabalar", "Qarzdor talabalar bilan individual suhbatlar o'tkazish", "2026-11-15", "jarayonda"),
        (2, "Buxgalteriya", "buxgalteriya", "Kommunal xarajatlar oshishi sabablarini tahlil qilish", "2026-11-12", "jarayonda"),
    ]
    for i, (t, d, k) in enumerate(meetings, 1):
        c.execute("INSERT INTO meetings(title,date,kind,transcript) VALUES(?,?,?,?)", (t, d, k, ""))
    for mi, who, role, text, due, st in task_seed:
        c.execute("INSERT INTO tasks(meeting_id,assignee,assignee_role,text,due,status) VALUES(?,?,?,?,?,?)", (mi + 1, who, role, text, due, st))

    # --- foydalanuvchilar (demo rollar) ---
    def tid_of(dept_id):
        return db.one(con, "SELECT id, full_name FROM teachers WHERE department_id=? AND position!='Kafedra mudiri' LIMIT 1", (dept_id,))
    dept4 = db.one(con, "SELECT * FROM departments WHERE id=4")
    t = tid_of(4)
    users = [
        ("Kuzatuv kengashi a'zosi", "kengash", None, None, None, "KENGASH"),
        ("Rektor", "rektor", None, None, None, "REKTOR"),
        ("O'quv ishlari bo'yicha prorektor", "prorektor_oquv", None, None, None, "OQUV"),
        ("Ilmiy ishlar va innovatsiyalar bo'yicha prorektor", "prorektor_ilmiy", None, None, None, "ILMIY"),
        ("Moliya-iqtisod ishlari bo'yicha prorektor", "prorektor_moliya", None, None, None, "MOLIYA"),
        ("Yoshlar masalalari va ma'naviy-ma'rifiy ishlar bo'yicha birinchi prorektor", "prorektor_yoshlar", None, None, None, "YOSHLAR"),
        ("Qabul komissiyasi", "qabul", None, None, None, "QABUL"),
        ("Akademik faoliyat va registrator departamenti: Yusupova Dilnoza Bahodir qizi", "talabalar", None, None, None, "TALABA"),
        ("Magistratura bo'limi", "magistratura", None, None, None, "MAGISTR"),
        ("Xalqaro hamkorlik bo'limi", "xalqaro", None, None, None, "XALQARO"),
        ("Buxgalteriya bo'limi", "buxgalteriya", None, None, None, "BUXGALTER"),
        ("Kadrlar bo'limi", "kadrlar", None, None, None, "KADR"),
        (f"Dekan: {fac[1]['dean']}", "dekan", 2, None, None, "DEKAN"),
        (f"Kafedra mudiri: {dept4['head']}", "kafedra", 2, 4, None, "KAFEDRA"),
        (f"O'qituvchi: {t['full_name']}", "oqituvchi", 2, 4, t["id"], "USTOZ"),
        ("Xo'jalik va texnik bo'lim", "xojalik", None, None, None, "XOJALIK"),
        # rasmiy tuzilmadagi qolgan prorektorlar (id'lar 17–19: mavjud demo akkauntlar id'si o'zgarmasligi uchun oxirida)
        ("Umumiy masalalar bo'yicha prorektor", "prorektor_umumiy", None, None, None, "UMUMIY"),
        ("Xalqaro aloqalar bo'yicha prorektor", "prorektor_xalqaro", None, None, None, "XALQAROPR"),
        ("Raqamlashtirish va moliya masalalari bo'yicha prorektor", "prorektor_raqam", None, None, None, "RAQAM"),
    ]
    for nm, role, f, d, tid, code in users:
        c.execute("INSERT INTO users(full_name,role,faculty_id,department_id,teacher_id,link_code,pin) VALUES(?,?,?,?,?,?,?)",
                  (nm, role, f, d, tid, code, "1234"))
    from . import seed_extra
    seed_extra.run(con, R, TODAY, teachers)
    con.commit()
    from . import dateshift   # hikoya 2026-11-04 ga nisbatan yozilgan — hammasini bugungi sanaga suramiz
    print("Sanalar surildi:", dateshift.shift_all(con, (dt.date.today() - TODAY).days), "kun")
    from . import seed_service
    seed_service.run(con, R)
    from . import seed_occupancy
    seed_occupancy.run(con, R)
    # --- Hujjatlar markazi: demo uchun tayyor hujjatlar (fayllari bilan) ---
    import shutil
    from . import documents as D, rbac
    shutil.rmtree(D.OUT, ignore_errors=True)
    base = "http://localhost:8000/"
    def as_(uid): return rbac.ctx_for(con, uid)
    dean, rect, kadr, xal, mol, kaf = as_(13), as_(2), as_(12), as_(10), as_(5), as_(14)
    st = D.lookup(con, dean, "student", "")[:4]
    grp = [g for g in D.lookup(con, dean, "group") if "-24" in g["label"]][0]["id"]
    for x in st[:3]: D.issue(con, dean, "study_cert", {"target": f"s:{x['id']}", "purpose": R.choice(D.PURPOSES[:5])}, base)
    D.issue(con, dean, "study_cert", {"target": f"s:{st[3]['id']}", "lang": "en"}, base)
    D.issue(con, dean, "transcript", {"target": f"s:{st[0]['id']}"}, base)
    D.issue(con, dean, "exam_sheet", {"group": grp, "subject": "*"}, base)
    D.issue(con, dean, "debtors_list", {}, base)
    D.issue(con, dean, "order_student", {"target": f"s:{st[1]['id']}", "action": "akademik_tatil", "reason": "sog'lig'i bo'yicha (tibbiy xulosa ilova qilingan)"}, base)
    D.issue(con, mol, "debt_letter", {"target": f"g:{grp}"}, base)
    D.issue(con, kaf, "load", {"department": 4}, base)
    D.issue(con, rect, "minutes", {"meeting": 5}, base)
    D.issue(con, rect, "exec_notice", {"task": "*"}, base)
    stf = D.lookup(con, kadr, "staff", "")[0]["id"]
    D.issue(con, kadr, "work_cert", {"staff": stf, "with_salary": True}, base)
    D.issue(con, kadr, "leave_order", {"staff": D.lookup(con, kadr, "staff", "")[5]["id"], "start": "2026-12-01"}, base)
    D.issue(con, xal, "invitation", {"guest": "Dr. A. Namuna (sun'iy)", "guest_org": "Hamkor OTM — Latviya (namuna)", "country": "Latvia",
            "purpose_en": "a guest lecture series on FinTech and joint summer school planning", "start": "2027-02-10", "end": "2027-02-17"}, base)
    con.execute("UPDATE documents SET created_at = strftime('%Y-%m-%dT%H:%M:%S', created_at, '-' || (abs(random()) % 12 + 1) || ' days', '-' || (abs(random()) % 300) || ' minutes') WHERE status!='loyiha'")
    con.commit()
    from . import decisions   # majlis qarori oqimi: jadval kengaytmalari va demo akkauntlar (kotib, IT, Registrator)
    decisions.init(con)
    from . import student_ops   # talabalar markazi: telefonlar, to'lov jadvali, dars qoldirishlar, ta'tillar, otrabotkalar (sun'iy)
    student_ops.init(con)
    student_ops.evaluate(con)
    counts = {t: con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in
              ["faculties","departments","groups_","teachers","students","grades","publications","grants","partners","applicants","budget","staff","events","appeals","meetings","tasks","users","documents","audit_log","rooms","tickets","requests","incidents","event_checkin","schedule","cameras","occupancy"]}
    print("Seed tayyor:", counts)

if __name__ == "__main__":
    run()
