"""Kameralar moduli uchun demo (sun'iy) ma'lumot: xizmat zonalari, kamera modellari va holati, 30 kunlik voqealar, navbatlar.

Hikoyalar (rektorga ko'rsatish uchun, o'ylab topilgan):
  1. C-binodagi 2 ta auditoriya dars jadvaliga qaramay 2 hafta deyarli bo'sh (xonani optimallashtirish).
  2. Qabul komissiyasida har dushanba 10:00–12:00 navbat 25+ kishi.
  3. Serverxona: tungi hududga kirish voqealari — ikkitasi "noto'g'ri signal", biri tiketga aylangan.
  4. Bitta kamera 3 kundan beri oflayn — tiket ochiq va muddati o'tgan.
  5. Oshxonada tushlikda olomon — sig'imning ~120%.
Shaxsiy ma'lumot yo'q, rasm yo'q. Vaqtlar seed paytidagi "hozir"ga nisbatan (dateshift kerak emas).
"""
import datetime as dt, json, secrets
from . import occupancy as OC, camsec as CS

# (bino, nom, zona, qavat, sig'im, qo'riq) — xizmat zonalari (TAXMIN joylashuv)
ZONES = [
    ("A", "Qabul komissiyasi · A-bino, 1-qavat", "qabul", 1, 60, 0),
    ("A", "Kassa · A-bino, 1-qavat", "kassa", 1, 20, 0),
    ("A", "Majlislar zali · A-bino, 2-qavat", "zal", 2, 320, 0),
    ("A", "Bosh kirish · A-bino", "kirish", 1, 0, 0),
    ("B", "Kirish · B-bino", "kirish", 1, 0, 0),          # Kirish nazorati (Face ID) — app/seed_facecam.py
    ("E", "Kirish · E-bino", "kirish", 1, 0, 0),
    ("C", "Serverxona · C-bino, 1-qavat", "serverxona", 1, 4, 1),
    ("B", "Texnik xona (elektr shchiti) · B-bino, yerto'la", "texnik", 0, 4, 1),
    ("D", "Tomga chiqish joyi · D-bino, 4-qavat", "tom", 4, 0, 1),
    ("E", "Oshxona · E-bino, 1-qavat", "oshxona", 1, 150, 0),
]

def prepare(con, R):
    """Jadval tuzilgandan keyin, kameralar va bandlik tarixidan OLDIN: xizmat zonalari va hikoya-1 (bo'sh auditoriyalar)."""
    CS.init(con)
    for b, name, zone, floor, cap, guard in ZONES:
        con.execute("INSERT INTO rooms(code,building,name,kind,equipment,capacity,guard,floor,zone) VALUES(?,?,?,?,?,?,?,?,?)",
                    (secrets.token_hex(4), b + "-bino", name, "xizmat", "[]", cap, guard, floor, zone))
    # hikoya 1: C-bino, jadvali eng zich 2 ta oddiy auditoriya (kompyuter sinfi va "sovuq" yuqori qavat emas)
    rows = con.execute("""SELECT r.id, r.name, COUNT(s.id) n FROM rooms r JOIN schedule s ON s.room_id=r.id
                          WHERE r.building='C-bino' AND r.kind='auditoriya' AND substr(r.name,3,1) IN ('1','2') GROUP BY r.id ORDER BY n DESC, r.name LIMIT 2""").fetchall()
    since = (OC.now().date() - dt.timedelta(days=14)).isoformat()
    con.executemany("INSERT OR REPLACE INTO cam_story(key,value) VALUES(?,?)",
                    [("idle_rooms", ",".join(str(r[0]) for r in rows)), ("idle_since", since), ("idle_names", "|".join(r[1].split(" ·")[0] for r in rows))])
    con.commit()
    OC._sched_cache["t"] = 0

def _model_for(r):
    z, n = r["zone"], r["name"].split(" ·")[0]
    if z in ("serverxona", "texnik", "tom"): return "DS-2TD2617-6/QA"
    if z == "kirish": return "iDS-2CD7146G0-IZS"          # DeepinView, yuzni solishtirish (FDLib) — Kirish nazorati (Face ID)
    if z in ("qabul", "kassa", "oshxona", "zal", "kirish", "koridor") or n in ("A-101", "A-201", "D-101", "E-101"): return "iDS-2CD7A46G0-IZHS"
    if r["kind"] == "kompyuter sinfi" or (r["building"] in ("B-bino",) and (r["floor"] or 0) >= 3): return "DS-2CD3D46G2T-IZHS"
    return "DS-2CD2346G2-ISU/SL"

def run(con, R):
    t = OC.now(); c = con.cursor()
    cams = [dict(x) for x in con.execute("""SELECT c.id, c.room_id, r.name, r.building, r.floor, r.zone, r.kind, r.capacity, r.guard
                                             FROM cameras c JOIN rooms r ON r.id=c.room_id ORDER BY r.building, r.floor, r.name""")]
    bidx = {"A-bino": 1, "B-bino": 2, "C-bino": 3, "D-bino": 4, "E-bino": 5}
    seq = {}
    for cam in cams:   # --- model, imkoniyatlar, IP, proshivka ---
        m = _model_for(cam); fam = CS.model_of(m)
        b = bidx.get(cam["building"], 9); seq[b] = seq.get(b, 10) + 1
        fwd = R.choice(["230815", "231020", "240312", "240627", "250118"])
        fw = {"AcuSense": "V5.7.15", "Oddiy": "V5.7.12", "DeepinView": "V5.6.10", "Termal": "V5.5.80"}.get(fam["family"], "V5.7.0")
        c.execute("""UPDATE cameras SET vendor='Hikvision', model=?, host=?, fw=?, fw_date=?, ai_caps=?, clock_skew=?, thermal=?, installed=?,
                     sim_fault=NULL WHERE id=?""",
                  (m, f"10.10.{b}.{seq[b]}", fw, f"build {fwd}", json.dumps(fam["caps"]), R.randint(-4, 4), int(fam["family"] == "Termal"),
                   (t.date() - dt.timedelta(days=R.randint(200, 900))).isoformat(), cam["id"]))
    byname = {x["name"].split(" ·")[0]: x for x in cams}
    aud = [x for x in cams if x["zone"] is None and x["kind"] in ("auditoriya", "kompyuter sinfi")]
    st = CS.story(con); idle = {int(i) for i in st.get("idle_rooms", "").split(",") if i}
    pool = [x for x in aud if x["room_id"] not in idle]
    R.shuffle(pool)
    # --- eski proshivka (CVE-2021-36260 ogohlantirishi) ---
    for x in pool[:5]:
        c.execute("UPDATE cameras SET fw='V5.5.0', fw_date='build 210628' WHERE id=?", (x["id"],))
    # --- soat farqi (1–2 ta) ---
    c.execute("UPDATE cameras SET clock_skew=? WHERE id=?", (95, pool[5]["id"]))
    c.execute("UPDATE cameras SET clock_skew=? WHERE id=?", (-420, pool[6]["id"]))
    # --- oflayn (~4%): hikoya 4 — bittasi 3 kundan beri, tiket ochiq va muddati o'tgan ---
    off = [(pool[7], dt.timedelta(days=3, hours=2)), (pool[8], dt.timedelta(hours=7)), (pool[9], dt.timedelta(hours=2, minutes=20)),
           (pool[10], dt.timedelta(minutes=55)), (pool[11], dt.timedelta(minutes=34)), (pool[12], dt.timedelta(minutes=17)),
           (pool[13], dt.timedelta(minutes=12))]
    for x, ago in off:
        since = t - ago
        c.execute("""UPDATE cameras SET sim_fault='oflayn', status='xato', fail_count=?, last_seen=?, last_count=NULL,
                     last_error='Ulanib bo''lmadi: qurilma javob bermadi (timeout) — IP manzil, tarmoq yoki firewall''ni tekshiring' WHERE id=?""",
                  (max(3, int(ago.total_seconds() // 60)), OC.iso(since), x["id"]))
        tk = c.execute("INSERT INTO tickets(room_id,item,text,photo,reporter,created_at,status) VALUES(?,?,?,?,?,?,?)",
                       (x["room_id"], OC.CAM_ITEM, f"Kamera {CS.OFFLINE_MIN}+ daqiqa javob bermayapti: ulanib bo'lmadi (timeout) — IP manzil, "
                        "tarmoq yoki quvvatni tekshiring", None, "ISFT Core (avtomatik)", OC.iso(since + dt.timedelta(minutes=CS.OFFLINE_MIN)), "yangi")).lastrowid
        c.execute("UPDATE cameras SET ticket_id=?, ticket_kind='aloqa' WHERE id=?", (tk, x["id"]))
    # --- to'sib qo'yilgan (~2%) ---
    blocked = pool[14:18]
    for x in blocked:
        ts = t - dt.timedelta(hours=R.randint(2, 16), minutes=R.randint(0, 59))   # 24 soatdan kam — muddati o'tgani faqat hikoya-4
        tk = c.execute("INSERT INTO tickets(room_id,item,text,photo,reporter,created_at,status) VALUES(?,?,?,?,?,?,?)",
                       (x["room_id"], OC.CAM_ITEM, "Kamera voqeasi: Kamera to'sib qo'yildi / buzildi", None, "ISFT Core (avtomatik)", OC.iso(ts), "yangi")).lastrowid
        c.execute("UPDATE cameras SET ticket_id=?, ticket_kind='voqea' WHERE id=?", (tk, x["id"]))
        _ev(c, x, "kamera_yopildi", ts, status="tiket", ticket_id=tk, dup=R.randint(0, 3))
    con.commit()
    _events(con, R, cams, t, byname)
    _queues(con, R, t)
    _overflows(con, R, t, cams)
    con.commit()
    from . import seed_facecam    # Kirish nazorati (Face ID): shaxslar (rozilik), 14 kunlik sintetik kirish/chiqish voqealari
    seed_facecam.run(con)

def _ev(c, cam, kind, ts, status=None, note=None, dup=0, count=None, value=None, ticket_id=None, handled_by=None, last=None):
    room = {"guard": cam["guard"], "zone": cam["zone"], "id": cam["room_id"]}
    night = CS.is_night(ts); pr = CS.priority(kind, room, night)
    if status is None: status = "qayd" if pr == 4 else "yopildi"
    if note is None:
        note = (f"Ish vaqtidan tashqari ({OC.WORK_HOURS}) qo'riqlanadigan " + ("hududda harakat" if kind == "harakat" else "hududga kirish")
                if kind in CS.INTRUSION and cam["guard"] and night
                else CS.HK.KIND_LABEL.get(kind, kind))
    hb = handled_by or ("Xo'jalik va texnik bo'lim" if status in ("yopildi", "notogri", "tiket", "korildi") else None)
    lt = last or ts + dt.timedelta(seconds=dup * 40)     # birlashtirilgan takrorlar (dedup) — har ~40 s
    c.execute("""INSERT INTO cam_events(camera_id,room_id,ts,last_ts,kind,state,raw_type,count,alert,note,priority,route,status,dup,value,night,ticket_id,
                 handled_by,handled_at) VALUES(?,?,?,?,?,'active',?,?,?,?,?,?,?,?,?,?,?,?,?)""",
              (cam["id"], cam["room_id"], OC.iso(ts), OC.iso(lt), kind, kind, count, int(pr <= 2), note, pr, ",".join(CS.route(kind, room, pr)),
               status, dup, value, int(night), ticket_id, hb, OC.iso(ts + dt.timedelta(minutes=25)) if hb else None))
    return c.lastrowid

def _events(con, R, cams, t, byname):
    """30 kunlik oqim: ish kunlari ko'p, dam olish kunlari kam; tunda qo'riqlanadigan hududlarda harakat/kirish ko'proq.
    Turlar nisbati: ko'pchilik tasvir yo'qolishi va harakat (VMD), kamroq chiziq kesish, juda kam qarovsiz buyum/tutun."""
    c = con.cursor()
    z = lambda name: [x for x in cams if x["zone"] == name]
    guarded = [x for x in cams if x["guard"]]
    corridors = z("koridor") + z("kirish")
    public = corridors + z("zal") + z("oshxona")
    allc = cams
    # (tur, kun/tun, ish kuni uchun o'rtacha soni, kameralar to'plami)
    plan = [("video_yoqoldi", "any", 3.2, allc), ("harakat", "night", 2.6, guarded), ("harakat", "day", 0.6, guarded),
            ("chiziq_kesish", "day", 1.6, corridors + z("tom")), ("chiziq_kesish", "night", 0.35, guarded),
            ("hududga_kirish", "day", 0.5, z("texnik") + z("tom")), ("hududga_kirish", "night", 0.12, z("tom") + z("texnik")),
            ("hududdan_chiqish", "day", 0.4, corridors), ("uzoq_turish", "day", 0.45, z("kirish") + z("kassa") + z("koridor")),
            ("toplanish", "day", 0.5, corridors), ("yugurish", "day", 0.3, z("koridor")), ("kamera_siljidi", "any", 0.25, allc),
            ("qarovsiz_buyum", "day", 0.08, public), ("buyum_olindi", "day", 0.06, z("zal") + z("koridor"))]
    start = t.date() - dt.timedelta(days=30)
    for i in range(31):
        d = start + dt.timedelta(days=i)
        f = 1.0 if d.weekday() < 5 else (.55 if d.weekday() == 5 else .3)
        for kind, when, lam, pool in plan:
            if not pool: continue
            k = _poisson(R, lam * (f if when != "night" else 1.0))
            for _ in range(k):
                if when == "night": hh = R.choice([20, 21, 22, 23, 0, 1, 2, 3, 4, 5]); mm = R.randint(0, 59)
                elif when == "day": hh = R.randint(8, 18); mm = R.randint(0, 59)
                else: hh = R.randint(0, 23); mm = R.randint(0, 59)
                ts = dt.datetime.combine(d, dt.time(hh, mm, R.randint(0, 59)))
                if ts >= t: continue
                cam = R.choice(pool)
                pr = CS.priority(kind, {"guard": cam["guard"], "zone": cam["zone"]}, CS.is_night(ts))
                age_h = (t - ts).total_seconds() / 3600
                if pr == 4: stt = "qayd"
                elif age_h < 30 and R.random() < .6: stt = "yangi"
                elif kind in CS.INTRUSION | {"toplanish", "yugurish", "qarovsiz_buyum", "buyum_olindi"} and R.random() < .18: stt = "notogri"
                else: stt = "yopildi"
                _ev(c, cam, kind, ts, status=stt, dup=R.choice([0, 0, 0, 1, 2, 4]))
    # --- favqulodda: serverxona harorati (P1, haqiqiy, hal qilingan) va texnik xonada tutun (P1, noto'g'ri signal — chang) ---
    sx, tx = (z("serverxona") or [None])[0], (z("texnik") or [None])[0]
    if sx:
        ts = dt.datetime.combine(t.date() - dt.timedelta(days=9), dt.time(15, 42))
        tk = c.execute("INSERT INTO tickets(room_id,item,text,photo,reporter,created_at,status,resolved_at,note) VALUES(?,?,?,?,?,?,?,?,?)",
                       (sx["room_id"], "Xavfsizlik", "Harorat chegaradan oshdi: Serverxona 41.5 °C (termal kamera)", None, "ISFT Core (kamera voqeasi)",
                        OC.iso(ts), "hal qilindi", OC.iso(ts + dt.timedelta(minutes=48)), "Konditsioner to'xtagan — qayta ishga tushirildi")).lastrowid
        _ev(c, sx, "harorat", ts, status="yopildi", note="Harorat 41.5 °C — konditsioner to'xtagan, qayta ishga tushirildi", value=41.5, ticket_id=tk, dup=6)
    if tx:
        ts = dt.datetime.combine(t.date() - dt.timedelta(days=4), dt.time(11, 7))
        _ev(c, tx, "tutun", ts, status="notogri", note="Tutun aniqlandi — ta'mirlash changi (noto'g'ri signal)", dup=1)
    # --- hikoya 3: serverxona yonida tungi hududga kirish: 2 ta noto'g'ri signal + 1 ta tiket ---
    if sx:
        for days, hm, note in ((6, (23, 18), "Tungi kirish — tozalovchi xodim (jadvalga kiritilmagan) · noto'g'ri signal"),
                               (3, (1, 52), "Tungi kirish — kamera oldida hasharot / yorug'lik aksi · noto'g'ri signal")):
            ts = dt.datetime.combine(t.date() - dt.timedelta(days=days), dt.time(*hm))
            _ev(c, sx, "hududga_kirish", ts, status="notogri", note=note, dup=R.randint(1, 3))
        last = dt.datetime.combine(t.date(), dt.time(2, 14))
        if last >= t: last -= dt.timedelta(days=1)
        tk = c.execute("INSERT INTO tickets(room_id,item,text,photo,reporter,created_at,status) VALUES(?,?,?,?,?,?,?)",
                       (sx["room_id"], "Xavfsizlik", f"Serverxona: tungi hududga kirish {last.strftime('%d.%m %H:%M')} — qo'riqlash xizmati eshik qulfi va "
                        "kirish jurnalini tekshirsin (kamera voqeasi, faqat metama'lumot)", None, "Xo'jalik va texnik bo'lim", OC.iso(last + dt.timedelta(minutes=9)),
                        "jarayonda")).lastrowid
        _ev(c, sx, "hududga_kirish", last, status="tiket", note=f"Ish vaqtidan tashqari ({OC.WORK_HOURS}) qo'riqlanadigan hududga kirish — tiket #{tk}",
            ticket_id=tk, dup=2)
    con.commit()

def _poisson(R, lam):
    import math
    L, k, p = math.exp(-lam), 0, 1.0
    while True:
        p *= R.random()
        if p <= L: return k
        k += 1

def _queues(con, R, t):
    """30 kunlik navbat tarixi (har 15 daqiqa, 09:00–17:30) + chegaradan oshganda soatiga bitta voqea. Hikoya 2: Qabul, dushanba 10–12."""
    c = con.cursor()
    for zone, cfg in CS.QUEUE_ZONES.items():
        r = con.execute("SELECT c.id, c.room_id, r.name, r.building, r.floor, r.zone, r.kind, r.capacity, r.guard FROM cameras c JOIN rooms r ON r.id=c.room_id "
                        "WHERE r.zone=?", (zone,)).fetchone()
        if not r: continue
        cam = dict(zip(("id", "room_id", "name", "building", "floor", "zone", "kind", "capacity", "guard"), r))
        d = t.date() - dt.timedelta(days=30); rows = []; flagged = set()
        while d <= t.date():
            if d.weekday() < 6:
                x = dt.datetime.combine(d, dt.time(9, 0))
                while x.time() <= dt.time(17, 30) and x <= t:
                    n = CS.queue_sim(zone, x); rows.append((cam["room_id"], OC.iso(x), n, round(n * cfg["svc"], 1)))
                    if n > cfg["limit"] and (d, x.hour) not in flagged:
                        flagged.add((d, x.hour))
                        age = (t - x).total_seconds() / 3600
                        _ev(c, cam, "navbat", x, status="yangi" if age < 3 else "yopildi", count=n, dup=R.randint(1, 4),
                            note=f"Navbatda {n} kishi (chegara {cfg['limit']}), kutish ~{round(n * cfg['svc'])} daqiqa — {cfg['unit']}ga xabar",
                            handled_by=cfg["unit"] if age >= 3 else None)
                    x += dt.timedelta(minutes=15)
            d += dt.timedelta(days=1)
        c.executemany("INSERT INTO cam_queue(room_id,ts,length,wait_min) VALUES(?,?,?,?)", rows)
    con.commit()

def _overflows(con, R, t, cams):
    """Sig'imning 110% dan oshishi (bandlik tarixidan): har (xona, kun) uchun bitta voqea — xo'jalik bo'limiga. Hikoya 5: oshxona tushlikda."""
    c = con.cursor()
    by_room = {x["room_id"]: x for x in cams if (x["capacity"] or 0) > 0}
    since = OC.iso(dt.datetime.combine(t.date() - dt.timedelta(days=21), dt.time()))
    rows = con.execute("""SELECT o.room_id, substr(o.ts,1,13) h, MAX(o.count) mx, MIN(o.ts) ts FROM occupancy o JOIN rooms r ON r.id=o.room_id
                          WHERE o.ts>=? AND r.capacity>0 AND o.count > r.capacity * ? GROUP BY o.room_id, substr(o.ts,1,10)""", (since, CS.OVER_PCT)).fetchall()
    for rid, h, mx, ts in rows:
        cam = by_room.get(rid)
        if not cam: continue
        x = dt.datetime.fromisoformat(ts); age = (t - x).total_seconds() / 3600
        _ev(c, cam, "sigim_oshdi", x, status="yangi" if age < 4 else "yopildi", count=mx, dup=R.randint(0, 3),
            note=f"{mx} kishi / {cam['capacity']} o'rin ({round(100 * mx / cam['capacity'])}%) — xo'jalik bo'limiga")
    con.commit()
