"""Xizmat markazi uchun demo ma'lumotlar: xonalar, nosozliklar, murojaatlar (LMS uzilishi bilan), tadbir qatnashuvi.
Vaqtlar haqiqiy joriy vaqtga nisbatan qo'yiladi — operativ modul "hozir" bilan ishlaydi."""
import datetime as dt, json, secrets
from . import service as SV

# NQAAE: 5 ta o'quv binosi, umumiy sig'im 7 500 o'rin. Bino nomlari va qavatlar — TAXMIN.
BUILDINGS = {"A": "A-bino (bosh bino)", "B": "B-bino (o'quv binosi)", "C": "C-bino (IT markazi)", "D": "D-bino (o'quv binosi)", "E": "E-bino (o'quv binosi)"}

TICKET_TEXTS = {
    "Proyektor": ["Proyektor yoqilmayapti", "Rasm xira, ranglar buzilgan", "HDMI kabeli ishlamayapti", "Proyektor 10 daqiqada o'chib qolyapti"],
    "Kompyuter": ["Kompyuter yonmayapti", "Windows yangilanishda qotib qolgan", "Sichqoncha ishlamayapti"],
    "Mikrofon / ovoz": ["Mikrofon shovqin beryapti", "Kolonka ovozi yo'q"],
    "Konditsioner / isitish": ["Xona juda sovuq, isitish ishlamayapti", "Konditsioner suv tomizyapti", "Radiator sovuq"],
    "Elektr / rozetka": ["Rozetka ishlamayapti", "Uzaytirgich kuygan hidi chiqyapti"],
    "Chiroq": ["2 ta chiroq yonmayapti", "Chiroq yonib-o'chyapti"],
    "Doska": ["Marker doska tozalanmaydi", "Doska qiyshayib qolgan"],
    "Mebel": ["Stul singan", "Parta oyog'i qimirlaydi"],
    "Internet / Wi-Fi": ["Wi-Fi ulanmayapti", "Internet juda sekin"],
    "Printer": ["Printer qog'oz tiqyapti", "Kartrij tugagan"],
    "Santexnika": ["Kran oqyapti", "Unitaz ishlamayapti"],
    "Eshik / qulf": ["Eshik qulfi buzilgan"], "Isitish": ["Koridor juda sovuq"], "Tozalik": ["Axlat qutisi to'lib ketgan"],
}

LMS_MSGS = ["LMS ga kira olmayapman, parol xato deyapti", "lms ochilmayapti", "LMS platformasi ishlamayapti, topshiriq yuklay olmayman",
            "Moodle sahifasi yuklanmayapti 502 error", "LMSga kiraolmayapman bugun ertalabdan", "Platforma ochilmayapti, test bor edi",
            "lms ga kirolmayapman yordam bering", "LMS da xato chiqyapti, dars videosi ochilmayapti", "LMS ishlamayapti, deadline bugun",
            "Platformaga kira olmayapmiz butun guruh", "LMS login sahifasi ochilmayapti", "lms xato beryapti 504",
            "LMS ga kira olmayapman, boshqa brauzerda ham", "Topshiriqni LMSga yuklay olmayapman, sahifa ochilmayapti",
            "LMS ishlamayapti telefonda ham", "lms ochilmayapti nima qilay"]
OTHER_MSGS = [
    "Akademik ma'lumotnoma kerak edi, qayerdan olsam bo'ladi", "Transkriptimni ingliz tilida olsam bo'ladimi", "Kontrakt to'lovini Click orqali qildim, HEMISda ko'rinmayapti",
    "To'ladim, chek bor, lekin qarzdor deb chiqyapti", "HEMISda bahoyim noto'g'ri qo'yilgan, apellyatsiya qanday beriladi", "Dars jadvalida auditoriya ko'rsatilmagan",
    "Ertangi dars qayerda bo'ladi, jadval o'zgaribdi", "Ijara uy topishga yordam bera olasizmi", "Korporativ pochtaga parolni unutdim", "Wi-Fi parolini bilmayman",
    "Diplom ilovasi qachon tayyor bo'ladi", "Qayta topshirish uchun ariza qayerga beriladi", "Kontrakt summasini bo'lib to'lasam bo'ladimi",
    "Amaliyot uchun yo'llanma kerak", "Reytingda ballarim ko'rinmayapti", "Auditoriyada isitish ishlamayapti",
    "Spravka harbiy komissariat uchun kerak", "Payme orqali to'lov o'tmayapti", "Kutubxona kartasi yo'qoldi", "Stipendiya qachon tushadi",
]

def run(con, R):
    SV.init(con)
    c = con.cursor(); now = SV.now()
    # --- xonalar ---
    rooms = []
    for b, bname in BUILDINGS.items():
        for floor in (1, 2, 3, 4):
            for n in range(1, 10):
                code = f"{b}-{floor}{n:02d}"
                kind = "kompyuter sinfi" if b == "C" and n <= 3 else "auditoriya"
                rooms.append((secrets.token_hex(4), b + "-bino", f"{code} · {bname.split(' (')[0]}", kind, json.dumps(SV.EQUIP[kind], ensure_ascii=False)))
        rooms.append((secrets.token_hex(4), b + "-bino", f"{b}-bino · 1-qavat koridori va hojatxona", "umumiy", json.dumps(SV.EQUIP["umumiy"], ensure_ascii=False)))
    c.executemany("INSERT INTO rooms(code,building,name,kind,equipment) VALUES(?,?,?,?,?)", rooms)
    allrooms = [dict(r) for r in con.execute("SELECT * FROM rooms")]
    byname = {r["name"].split(" ·")[0]: r for r in allrooms}

    def ticket(room, item, days_ago, status, reports=1, hours_to_fix=None, text=None):
        t0 = now - dt.timedelta(days=days_ago, hours=R.randint(0, 8), minutes=R.randint(0, 59))
        res = None
        if status == "hal qilindi":
            res = SV.iso(t0 + dt.timedelta(hours=hours_to_fix or R.choice([1, 2, 3, 5, 8, 20, 30])))
        c.execute("INSERT INTO tickets(room_id,item,text,photo,reporter,created_at,status,reports,resolved_at) VALUES(?,?,?,?,?,?,?,?,?)",
                  (room["id"], item, text or R.choice(TICKET_TEXTS.get(item, ["Ishlamayapti"])), None,
                   R.choice(["", "", "BHM-2402", "o'qituvchi", "MSB-2401", "Talaba"]), SV.iso(t0), status, reports, res))

    # takror buzilayotgan jihozlar (rahbar ko'radigan "almashtirish kerak" signal)
    for d in (52, 31, 17, 3): ticket(byname["B-204"], "Proyektor", d, "hal qilindi" if d > 3 else "jarayonda", reports=R.randint(1, 4))
    for d in (44, 20, 6): ticket(byname["A-301"], "Konditsioner / isitish", d, "hal qilindi")
    for d in (38, 12, 1): ticket(byname["C-102"], "Internet / Wi-Fi", d, "hal qilindi" if d > 1 else "yangi", reports=3 if d == 1 else 1)
    # tasodifiy oqim
    for _ in range(46):
        r = R.choice(allrooms); items = json.loads(r["equipment"])
        d = R.randint(2, 58); ticket(r, R.choice(items), d, "hal qilindi")
    # ochiq / muddati o'tgan
    ticket(byname["A-104"], "Chiroq", 2, "yangi"); ticket(byname["B-302"], "Mebel", 3, "jarayonda")
    ticket(byname["C-201"], "Printer", 0, "yangi", reports=2); ticket(byname["A-202"], "Proyektor", 0, "yangi")
    ticket(byname["B-101"], "Elektr / rozetka", 1, "jarayonda"); ticket(byname["A-bino"], "Santexnika", 0, "yangi", reports=4)

    # --- murojaatlar: oldingi oylar ---
    for _ in range(70):
        t = now - dt.timedelta(days=R.randint(1, 45), hours=R.randint(0, 10), minutes=R.randint(0, 59))
        st = R.choices(["hal qilindi", "javob berildi", "jarayonda"], [70, 20, 10])[0]
        r = SV.create_request(con, R.choice(OTHER_MSGS), hemis_id=_rand_hemis(con, R), channel=R.choice(["veb-forma", "Telegram", "call-markaz"]), when=t)
        if st != "jarayonda":
            c.execute("UPDATE requests SET status=?, resolved_at=? WHERE id=?", (st, SV.iso(t + dt.timedelta(hours=R.randint(2, 40))), r["id"]))
    c.execute("UPDATE requests SET incident_id=NULL"); c.execute("DELETE FROM incidents")  # tasodifiy tarixdan hodisa yasalmasin
    # o'tgan oy: HEMIS uzilishi (hal qilingan hodisa)
    base = now - dt.timedelta(days=19, hours=3)
    for i in range(9):
        SV.create_request(con, R.choice(["HEMIS ochilmayapti", "hemis ga kira olmayapman", "HEMIS xato beryapti, baholar ko'rinmayapti", "HEMIS ishlamayapti"]),
                          hemis_id=_rand_hemis(con, R), when=base + dt.timedelta(minutes=9 * i))
    inc = con.execute("SELECT id FROM incidents WHERE topic='hemis'").fetchone()
    if inc:
        t = SV.iso(base + dt.timedelta(hours=3))
        c.execute("UPDATE incidents SET status='hal qilindi', resolved_at=?, notified_at=?, notice=? WHERE id=?",
                  (t, SV.iso(base + dt.timedelta(minutes=50)), "Hurmatli talabalar! HEMIS tizimida texnik ishlar olib borilmoqda...", inc[0]))
        c.execute("UPDATE requests SET status='hal qilindi', resolved_at=? WHERE incident_id=?", (t, inc[0]))
    # BUGUN: LMS uzilishi — 16 ta xabar 2 soat ichida (demo: hodisa ochiq, talabalarga hali xabar berilmagan)
    start = now - dt.timedelta(hours=2, minutes=10)
    for i, msg in enumerate(LMS_MSGS):
        SV.create_request(con, msg, hemis_id=_rand_hemis(con, R), channel=R.choice(["veb-forma", "Telegram", "call-markaz"]),
                          when=start + dt.timedelta(minutes=8 * i + R.randint(0, 5)))
    for msg in ["Kontrakt to'lovini Click orqali qildim, HEMISda ko'rinmayapti", "Akademik ma'lumotnoma kerak edi", "Dars jadvalida auditoriya ko'rsatilmagan"]:
        SV.create_request(con, msg, hemis_id=_rand_hemis(con, R), when=now - dt.timedelta(minutes=R.randint(10, 90)))

    # --- tadbirlar: QR qatnashuv ---
    students = [dict(r) for r in con.execute("SELECT id, group_id, faculty_id FROM students WHERE study_form='kunduzgi'")]   # tadbirlar — kampusdagi talabalar
    groups = sorted({s["group_id"] for s in students})
    cold = set(R.sample(groups, 7))  # hech bir tadbirga yetib borilmagan guruhlar
    warm = [s for s in students if s["group_id"] not in cold]
    regulars = R.sample(warm, 60)
    evs = [dict(r) for r in con.execute("SELECT id, date, participants FROM events WHERE date<=? ORDER BY date DESC LIMIT 10", (now.date().isoformat(),))]
    for ev in evs:
        SV.event_code(con, ev["id"])
        n_reg = min(len(warm) - 1, int(ev["participants"] * R.uniform(1.15, 1.45)))
        reg = R.sample(warm, n_reg)
        c.executemany("INSERT OR IGNORE INTO event_reg VALUES(?,?)", [(ev["id"], s["id"]) for s in reg])
        rate = R.uniform(0.58, 0.9)
        came = [s for s in reg if R.random() < rate] + [s for s in regulars if R.random() < 0.7]
        came += R.sample(warm, R.randint(3, 15))  # ro'yxatsiz kelganlar
        t0 = dt.datetime.fromisoformat(ev["date"] + "T14:00:00")
        c.executemany("INSERT OR IGNORE INTO event_checkin VALUES(?,?,?)",
                      [(ev["id"], s["id"], SV.iso(t0 + dt.timedelta(seconds=R.randint(0, 2400)))) for s in came])
    # bugungi jonli demo tadbiri — ro'yxat ochiq, hali hech kim belgilanmagan
    cur = c.execute("INSERT INTO events(title,date,kind,participants) VALUES(?,?,?,?)",
                    ("Ochiq ma'ruza: Sun'iy intellekt va moliya kelajagi", now.date().isoformat(), "intellektual", 0))
    eid = cur.lastrowid
    SV.event_code(con, eid)
    c.execute("UPDATE event_qr SET open=1 WHERE event_id=?", (eid,))
    c.executemany("INSERT OR IGNORE INTO event_reg VALUES(?,?)", [(eid, s["id"]) for s in R.sample(warm, 140)])
    con.commit()

def _rand_hemis(con, R):
    return con.execute("SELECT hemis_id FROM students ORDER BY random() LIMIT 1").fetchone()[0] if R.random() < 0.8 else ""
