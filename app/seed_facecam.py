"""Kirish nazorati (Face ID) — demo (sintetik) ma'lumot. Idempotent: qayta chaqirilsa mavjud yozuvlar saqlanadi.

  * Kirish kameralari: "Bosh kirish · A-bino" (mavjud) + "Kirish · B-bino", "Kirish · E-bino" (yo'q bo'lsa qo'shiladi),
    model — DeepinView yuzni solishtirish (iDS-2CD7146G0-IZS, TAXMINIY; AT bo'limi tasdiqlaydi).
  * Shaxslar (face_persons): ~60 talaba (sun'iy seed talabalari), ~25 o'qituvchi (kafedra mudirlari EMAS), ~15 xodim (bo'lim
    boshliqlari EMAS). Haqiqiy rahbarlar (rektor, prorektorlar, kafedra mudirlari, "Lavozim ism" hujjatidagi bo'lim
    rahbarlari, static/brand/people/index.json) ro'yxatga olinmaydi. ~85% — yozma rozilik bergan (FPID bor), qolgani — yo'q.
  * Voqealar: har bir kun uchun deterministik reja (random seed = sana) — dars jadvali (birinchi para), ish vaqti, tushlik,
    notanish mehmonlar (~3%), past ishonch (~2%), tungi kirishlar. Rasm saqlanmaydi: kadr `seed` bo'yicha qayta chiziladi.
  * `materialize(con, until)` — rejadan oxirgi yozilgan vaqtdan `until` gacha bo'lgan voqealarni yozadi (server ishlab turganda
    "jonli" ko'rinish: har so'rovda bugungi kun davom ettiriladi). Rozilik holati yozish paytidagi holat bo'yicha olinadi.
"""
import datetime as dt, json, hashlib, random, re, secrets, threading
from pathlib import Path
from . import db

ROOT = Path(__file__).resolve().parent.parent
FACE_MODEL = "iDS-2CD7146G0-IZS"
ENTRANCES = [("A-bino", "Bosh kirish · A-bino", .58), ("B-bino", "Kirish · B-bino", .27), ("E-bino", "Kirish · E-bino", .15)]
DAYS_BACK = 13            # bugun + 13 kun = 14 kun
N_STUDENTS, N_TEACHERS, N_STAFF = 60, 25, 15
CONSENT_P = .85
SLOTS = [(1, "08:30", "09:50"), (2, "10:00", "11:20"), (3, "11:30", "12:50"), (4, "13:30", "14:50"), (5, "15:00", "16:20"), (6, "16:30", "17:50")]
_LOCK = threading.RLock()
_PLAN_CACHE: dict = {}

SCHEMA = """
CREATE TABLE IF NOT EXISTS face_persons(id INTEGER PRIMARY KEY, kind TEXT, ref_id INT, name TEXT, sub TEXT, faculty_id INT, department_id INT,
  group_id INT, fpid TEXT UNIQUE, consent INT DEFAULT 0, consent_doc TEXT, consent_at TEXT, revoked_at TEXT, avatar_seed INT, female INT,
  updated_by TEXT, UNIQUE(kind, ref_id));
CREATE TABLE IF NOT EXISTS face_frames(id INTEGER PRIMARY KEY, ts TEXT, camera_id INT, direction TEXT, seed INT, n INT,
  source TEXT DEFAULT 'sintetik', snap TEXT, plan_key TEXT UNIQUE);
CREATE INDEX IF NOT EXISTS ix_face_frames_ts ON face_frames(ts);
CREATE TABLE IF NOT EXISTS face_events(id INTEGER PRIMARY KEY, frame_id INT, ts TEXT, camera_id INT, direction TEXT, person_id INT, fpid TEXT,
  similarity REAL, rect TEXT, status TEXT, look INT, female INT, night INT DEFAULT 0, raw_type TEXT);
CREATE INDEX IF NOT EXISTS ix_face_ev_ts ON face_events(ts);
CREATE INDEX IF NOT EXISTS ix_face_ev_person ON face_events(person_id, ts);
CREATE INDEX IF NOT EXISTS ix_face_ev_frame ON face_events(frame_id);
CREATE TABLE IF NOT EXISTS face_sync(id INTEGER PRIMARY KEY, op TEXT, fpid TEXT, person_id INT, created_at TEXT, done_at TEXT, result TEXT);
CREATE TABLE IF NOT EXISTS face_meta(key TEXT PRIMARY KEY, value TEXT);
"""

def init(con):
    con.executescript(SCHEMA)
    con.commit()

def meta(con, k, v=None):
    if v is None:
        r = con.execute("SELECT value FROM face_meta WHERE key=?", (k,)).fetchone()
        return r[0] if r else None
    con.execute("INSERT OR REPLACE INTO face_meta(key,value) VALUES(?,?)", (k, str(v)))

def _now():
    from . import occupancy as OC
    return OC.now()

def iso(t): return t.isoformat(timespec="seconds")
def hm(s): h, m = map(int, s.split(":")); return h * 60 + m

# ---------------------------------------------------------------------------------------------
# Kameralar
# ---------------------------------------------------------------------------------------------
def ensure_cameras(con) -> list:
    from . import camsec as CS
    t = _now()
    caps = json.dumps(CS.MODELS[FACE_MODEL]["caps"])
    out = []
    for i, (bld, name, _) in enumerate(ENTRANCES):
        r = db.one(con, "SELECT id FROM rooms WHERE name=?", (name,))
        if not r:
            rid = con.execute("INSERT INTO rooms(code,building,name,kind,equipment,capacity,guard,floor,zone) VALUES(?,?,?,?,?,?,?,?,?)",
                              (secrets.token_hex(4), bld, name, "xizmat", "[]", 0, 0, 1, "kirish")).lastrowid
        else:
            rid = r["id"]
        c = db.one(con, "SELECT id, model, mode FROM cameras WHERE room_id=?", (rid,))
        if not c:
            con.execute("""INSERT INTO cameras(room_id,vendor,model,mode,host,channel,status,last_seen,last_count,fw,fw_date,ai_caps,clock_skew,installed)
                           VALUES(?,?,?,?,?,1,'onlayn',?,0,?,?,?,?,?)""",
                        (rid, "Hikvision", FACE_MODEL, "sim", f"10.10.{ 'ABCDE'.index(bld[0]) + 1}.{40 + i}", iso(t), "V5.7.20", "build 250310",
                         caps, 1, (t.date() - dt.timedelta(days=120)).isoformat()))
        elif c["mode"] == "sim" and c["model"] != FACE_MODEL:
            con.execute("UPDATE cameras SET vendor='Hikvision', model=?, ai_caps=?, fw='V5.7.20', fw_date='build 250310' WHERE id=?", (FACE_MODEL, caps, c["id"]))
        out.append(db.one(con, "SELECT c.id, c.room_id, r.name, r.building FROM cameras c JOIN rooms r ON r.id=c.room_id WHERE c.room_id=?", (rid,)))
    con.commit()
    return out

def entrance_cams(con) -> list:
    """Yuz voqealari faqat kirish zonasidagi kameralardan (bino ichida kuzatuv yo'q)."""
    return db.rows(con, """SELECT c.id, c.room_id, c.model, c.mode, c.status, c.host, r.name, r.building FROM cameras c JOIN rooms r ON r.id=c.room_id
                           WHERE r.zone='kirish' ORDER BY r.building, r.name""")

# ---------------------------------------------------------------------------------------------
# Shaxslar (rozilik reyestri)
# ---------------------------------------------------------------------------------------------
def _nkey(n: str) -> str:
    n = re.sub(r"[ʻʼ‘’'`´]", "", (n or "").split(":")[-1].lower()).split()
    return " ".join(n[:2])

def excluded_names(con) -> set:
    """Haqiqiy rahbarlar: foydalanuvchilar (rektor, prorektorlar, bo'lim rahbarlari, kafedra mudirlari...), tuzilma rahbarlari, rasmlar.
    faculties.dean — eski bazalar uchun (institutda dekan lavozimi yo'q, yangi seed'da bo'sh)."""
    ex = {_nkey(r[0]) for r in con.execute("SELECT full_name FROM users") if r[0]}
    ex |= {_nkey(r[0]) for r in con.execute("SELECT head FROM departments WHERE head IS NOT NULL")}
    ex |= {_nkey(r[0]) for r in con.execute("SELECT dean FROM faculties WHERE dean IS NOT NULL")}
    try: ex |= {_nkey(r[0]) for r in con.execute("SELECT head FROM org_units WHERE head IS NOT NULL")}
    except Exception: pass
    try: ex |= {_nkey(k) for k in json.load(open(ROOT / "static" / "brand" / "people" / "index.json", encoding="utf-8"))}
    except (OSError, ValueError): pass
    ex.discard("")
    return ex

def _female(name: str) -> int:
    n = (name or "").lower()
    return int(n.endswith("qizi") or n.split()[0].endswith(("ova", "eva", "yeva")) if n else 0)

def _fpid(R) -> str:
    return "FP" + "".join(R.choice("0123456789ABCDEF") for _ in range(10))

def ensure_persons(con):
    if con.execute("SELECT COUNT(*) FROM face_persons").fetchone()[0]:
        return
    R = random.Random(547)
    ex = excluded_names(con)
    t = _now()
    rows = []
    # talabalar: dars jadvali bor kunduzgi guruhlar, fakultetlar bo'yicha teng (har guruhdan 3 nafar)
    groups = db.rows(con, """SELECT g.id, g.name, g.faculty_id, COUNT(DISTINCT s.weekday) days FROM groups_ g JOIN schedule s ON s.group_id=g.id
                             WHERE g.form='kunduzgi' GROUP BY g.id HAVING days>=4 ORDER BY g.id""")
    by_fac = {}
    for g in groups: by_fac.setdefault(g["faculty_id"], []).append(g)
    pick = []
    for fac in sorted(by_fac):
        R.shuffle(by_fac[fac]); pick += by_fac[fac][:7]
    pick = pick[:N_STUDENTS // 3]
    for g in pick:
        st = db.rows(con, "SELECT id, full_name FROM students WHERE group_id=? AND status='faol' ORDER BY id", (g["id"],))
        st = [s for s in st if _nkey(s["full_name"]) not in ex]
        R.shuffle(st)
        for s in st[:3]:
            rows.append(("talaba", s["id"], s["full_name"], g["name"], g["faculty_id"], None, g["id"]))
    # o'qituvchilar: kafedra mudiri emas, jadvalda darsi bor
    tch = db.rows(con, """SELECT t.id, t.full_name, t.department_id, t.faculty_id, d.name dep FROM teachers t JOIN departments d ON d.id=t.department_id
                          WHERE COALESCE(t.position,'')!='Kafedra mudiri' AND t.id IN (SELECT DISTINCT teacher_id FROM schedule) ORDER BY t.id""")
    tch = [x for x in tch if _nkey(x["full_name"]) not in ex]
    by_dep = {}
    for x in tch: by_dep.setdefault(x["department_id"], []).append(x)
    tpick = []
    while len(tpick) < N_TEACHERS and any(by_dep.values()):
        for dep in sorted(by_dep):
            if by_dep[dep] and len(tpick) < N_TEACHERS:
                tpick.append(by_dep[dep].pop(R.randrange(len(by_dep[dep]))))
    for x in tpick:
        rows.append(("oqituvchi", x["id"], x["full_name"], f"{x['dep']} kaf.", x["faculty_id"], x["department_id"], None))
    # xodimlar: bo'lim boshliqlari va rektorat emas
    stf = db.rows(con, """SELECT id, full_name, unit FROM staff WHERE unit NOT IN ('Professor-o''qituvchi','Rektorat') AND COALESCE(position,'') NOT LIKE '%boshlig%'
                          ORDER BY id""")
    stf = [x for x in stf if _nkey(x["full_name"]) not in ex]
    R.shuffle(stf)
    seen_u = {}
    for x in stf:
        if sum(seen_u.values()) >= N_STAFF: break
        if seen_u.get(x["unit"], 0) >= 2: continue
        seen_u[x["unit"]] = seen_u.get(x["unit"], 0) + 1
        rows.append(("xodim", x["id"], x["full_name"], x["unit"], None, None, None))
    used = set()
    for i, (kind, ref, name, sub, fac, dep, gid) in enumerate(rows):
        consent = R.random() < CONSENT_P
        fp = None
        if consent:
            fp = _fpid(R)
            while fp in used: fp = _fpid(R)
            used.add(fp)
        cat = (t.date() - dt.timedelta(days=R.randint(25, 70))).isoformat()
        con.execute("""INSERT OR IGNORE INTO face_persons(kind,ref_id,name,sub,faculty_id,department_id,group_id,fpid,consent,consent_doc,consent_at,avatar_seed,female,updated_by)
                       VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (kind, ref, name, sub, fac, dep, gid, fp, int(consent), f"RZ-2026/{1000 + i:04d}" if consent else None, cat if consent else None,
                     R.randint(1, 10 ** 7), _female(name), "seed (demo)"))
    # hikoya: 2 o'qituvchi tez-tez kechikadi (rozilik bergan, darsi ko'p)
    late = db.rows(con, """SELECT p.id FROM face_persons p WHERE p.kind='oqituvchi' AND p.consent=1
                           ORDER BY (SELECT COUNT(DISTINCT weekday) FROM schedule s WHERE s.teacher_id=p.ref_id) DESC, p.id LIMIT 2""")
    meta(con, "late_teachers", ",".join(str(x["id"]) for x in late))
    meta(con, "cohort_max", con.execute("SELECT MAX(id) FROM face_persons").fetchone()[0])
    con.commit()

def cohort_max(con) -> int:
    """Sintetik rejadagi shaxslar — seed paytidagi ro'yxat (keyin qo'shilganlar faqat haqiqiy kameradan keladi; reja barqaror qoladi)."""
    v = meta(con, "cohort_max")
    if v is None:
        v = con.execute("SELECT MAX(id) FROM face_persons WHERE updated_by='seed (demo)'").fetchone()[0] or 0
        meta(con, "cohort_max", v); con.commit()
    return int(v)

# ---------------------------------------------------------------------------------------------
# Kunlik reja (deterministik)
# ---------------------------------------------------------------------------------------------
def _sched(con):
    g = {}
    for gid, wd, a, b in con.execute("SELECT group_id, weekday, MIN(slot), MAX(slot) FROM schedule GROUP BY group_id, weekday"):
        g[(gid, wd)] = (a, b)
    tt = {}
    for tid, wd, a, b in con.execute("SELECT teacher_id, weekday, MIN(slot), MAX(slot) FROM schedule GROUP BY teacher_id, weekday"):
        tt[(tid, wd)] = (a, b)
    return g, tt

def first_slot(con, kind, ref_id, group_id, wd):
    """Shaxsning shu hafta kunidagi birinchi va oxirgi parasi (talaba — guruhi bo'yicha, o'qituvchi — o'zi). Yo'q bo'lsa None."""
    if kind == "talaba" and group_id:
        r = con.execute("SELECT MIN(slot), MAX(slot) FROM schedule WHERE group_id=? AND weekday=?", (group_id, wd)).fetchone()
    elif kind == "oqituvchi":
        r = con.execute("SELECT MIN(slot), MAX(slot) FROM schedule WHERE teacher_id=? AND weekday=?", (ref_id, wd)).fetchone()
    else:
        return None
    return (r[0], r[1]) if r and r[0] else None

def _home(pid: int) -> int:
    h = int(hashlib.md5(f"home{pid}".encode()).hexdigest()[:8], 16) / 0xFFFFFFFF
    acc = 0
    for i, (_, _, w) in enumerate(ENTRANCES):
        acc += w
        if h <= acc: return i
    return 0

def day_plan(con, d: dt.date, persons: list, cams: list, sched) -> list:
    """Kun rejasi: [(ts, cam_index, direction, [kishilar])], kishi = {"pid": id | None, "unknown": bool}. Faqat reja — holat yozishda aniqlanadi."""
    R = random.Random(f"facecam|{d.isoformat()}")
    wd = d.weekday()
    gs, ts_ = sched
    late_t = {int(x) for x in (meta(con, "late_teachers") or "").split(",") if x}
    app = []          # (minute, sec, cam_i, dir, pid|None)
    def at(m): return max(0, min(24 * 60 - 1, int(m)))
    for p in persons:
        home = _home(p["id"])
        cam_in = home if R.random() < .85 else R.randrange(len(cams))
        cam_out = home if R.random() < .8 else R.randrange(len(cams))
        arr = dep = None
        if wd == 6:
            continue
        if p["kind"] == "talaba":
            sl = gs.get((p["group_id"], wd))
            if not sl or R.random() > .9: continue
            st, en = hm(SLOTS[sl[0] - 1][1]), hm(SLOTS[sl[1] - 1][2])
            arr = st + R.uniform(2, 28) if R.random() < .12 else st - R.uniform(4, 38)
            dep = en + R.uniform(1, 45)
            if R.random() < .15 and st < hm("12:50") < en:      # tushlikka chiqib-kirish
                o = hm("12:50") + R.uniform(0, 12); app.append((o, cam_out, "chiqish", p["id"])); app.append((o + R.uniform(18, 34), cam_in, "kirish", p["id"]))
        elif p["kind"] == "oqituvchi":
            sl = ts_.get((p["ref_id"], wd))
            if sl:
                if R.random() > .97: continue
                st, en = hm(SLOTS[sl[0] - 1][1]), hm(SLOTS[sl[1] - 1][2])
                lp = .55 if p["id"] in late_t else .07
                arr = st + R.uniform(4, 26) if R.random() < lp else st - R.uniform(6, 50)
                dep = en + R.uniform(5, 70)
            elif wd < 5 and R.random() < .45:
                arr = hm("09:00") + R.uniform(0, 110); dep = arr + R.uniform(180, 330)
            else:
                continue
        else:
            if wd == 5:
                if R.random() > .25: continue
                arr = hm("09:00") + R.uniform(0, 50); dep = hm("13:00") + R.uniform(0, 70)
            else:
                if R.random() > .95: continue
                arr = hm("09:00") + R.uniform(1, 42) if R.random() < .18 else hm("08:24") + R.uniform(0, 34)
                dep = hm("17:30") + R.uniform(0, 70)
                if R.random() < .3:
                    o = hm("12:55") + R.uniform(0, 20); app.append((o, cam_out, "chiqish", p["id"])); app.append((o + R.uniform(25, 45), cam_in, "kirish", p["id"]))
        app.append((arr, cam_in, "kirish", p["id"]))
        app.append((dep, cam_out, "chiqish", p["id"]))
    # notanish mehmonlar (~3%): kunduzi kiradi va chiqadi
    n_unk = 0 if wd == 6 else max(1, round(len(app) * .015 + R.uniform(-1, 1.5)))
    for _ in range(n_unk):
        a = hm("09:00") + R.uniform(0, 420); c = R.randrange(len(cams))
        app.append((a, c, "kirish", None))
        if R.random() < .8: app.append((a + R.uniform(15, 120), c, "chiqish", None))
    if wd == 6 and R.random() < .5:
        a = hm("10:00") + R.uniform(0, 240); app.append((a, 0, "kirish", None)); app.append((a + R.uniform(20, 90), 0, "chiqish", None))
    # tungi kirishlar (xavfsizlik hikoyasi): ba'zi kunlari B yoki E binoga tunda notanish shaxs
    o = d.toordinal() % 6
    if o == 2: app.append((hm("23:00") + R.uniform(5, 50), 1, "kirish", None))
    if o == 5: app.append((hm("02:00") + R.uniform(0, 40), 2 if len(cams) > 2 else 0, "kirish", None))
    # kadrlarga birlashtirish: bir kamera, bir yo'nalish, 75 s oynasi, ko'pi bilan 3 kishi
    app = [(at(m), c, di, pid) for m, c, di, pid in app]
    app.sort(key=lambda x: (x[1], x[2], x[0]))
    frames, cur = [], None
    for m, c, di, pid in app:
        if cur and cur["cam"] == c and cur["dir"] == di and m - cur["m"] <= 2.0 and len(cur["people"]) < 3:
            cur["people"].append(pid); continue
        cur = {"m": m, "cam": c, "dir": di, "people": [pid]}
        frames.append(cur)
    out = []
    for i, f in enumerate(sorted(frames, key=lambda f: (f["m"], f["cam"]))):
        sec = R.randint(0, 59)
        mm = int(f["m"])
        t = dt.datetime.combine(d, dt.time(mm // 60, mm % 60, sec))
        out.append({"key": f"{d.isoformat()}#{i}", "ts": t, "cam": f["cam"], "dir": f["dir"], "people": f["people"],
                    "seed": int(hashlib.md5(f"{d}{i}".encode()).hexdigest()[:7], 16)})
    return out

# ---------------------------------------------------------------------------------------------
# Rejani bazaga yozish (rozilik holati — yozish paytidagi)
# ---------------------------------------------------------------------------------------------
def _is_night(t: dt.datetime) -> int:
    return int(not (hm("07:00") <= t.hour * 60 + t.minute <= hm("20:00")))

def write_frame(con, f: dict, cam_id: int, persons: dict, match_min: float):
    from . import facecam_render as FR
    R = random.Random(f["seed"])
    rects = FR.layout(R, len(f["people"]))
    fid = con.execute("INSERT OR IGNORE INTO face_frames(ts,camera_id,direction,seed,n,source,plan_key) VALUES(?,?,?,?,?,?,?)",
                      (iso(f["ts"]), cam_id, f["dir"], f["seed"], len(rects), "sintetik", f["key"])).lastrowid
    if not fid: return None
    night = _is_night(f["ts"])
    for pid, rect in zip(f["people"], rects):
        p = persons.get(pid) if pid else None
        rr = random.Random(f"{f['seed']}|{pid}")
        if p is None:
            st, person, fp, sim, lk, fem = "notanish", None, None, None, rr.randint(1, 10 ** 7), None
        elif not (p["consent"] and p["fpid"]):        # rozilik yo'q — shaxs aniqlanmaydi, bog'lanmaydi, tashqi ko'rinishi ham tasodifiy
            st, person, fp, sim, lk, fem = "rozilik_yoq", None, None, None, rr.randint(1, 10 ** 7), None
        else:
            low = rr.random() < .02
            sim = round(rr.uniform(.58, match_min - .01), 3) if low else round(min(.99, max(match_min + .02, rr.gauss(.925, .028))), 3)
            st = "past_ishonch" if sim < match_min else "tanildi"
            person, fp, lk, fem = p["id"], p["fpid"], p["avatar_seed"], p["female"]
        con.execute("""INSERT INTO face_events(frame_id,ts,camera_id,direction,person_id,fpid,similarity,rect,status,look,female,night,raw_type)
                       VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (fid, iso(f["ts"]), cam_id, f["dir"], person, fp, sim, json.dumps(rect), st, lk, fem, night, "alarmResult (sintetik)"))
    return fid

def materialize(con, until: dt.datetime | None = None, match_min: float = .75) -> int:
    """Rejadagi voqealarni oxirgi yozilgan vaqtdan `until` gacha yozadi. Qaytaradi: yangi kadrlar soni."""
    with _LOCK:
        until = until or _now()
        last = meta(con, "until")
        start = dt.datetime.fromisoformat(last) if last else dt.datetime.combine(until.date() - dt.timedelta(days=DAYS_BACK), dt.time())
        if until <= start: return 0
        cams = [c["id"] for c in entrance_cams(con)]
        if not cams: return 0
        persons = {p["id"]: p for p in db.rows(con, "SELECT * FROM face_persons WHERE id<=? ORDER BY id", (cohort_max(con),))}
        plist = list(persons.values())
        sched = _sched(con)
        n = 0
        d = start.date()
        while d <= until.date():
            key = (d.isoformat(), len(plist), len(cams))
            plan = _PLAN_CACHE.get(key)
            if plan is None:
                plan = day_plan(con, d, plist, cams, sched)
                _PLAN_CACHE.clear() if len(_PLAN_CACHE) > 20 else None
                _PLAN_CACHE[key] = plan
            for f in plan:
                if start < f["ts"] <= until:
                    if write_frame(con, f, cams[f["cam"] % len(cams)], persons, match_min): n += 1
            d += dt.timedelta(days=1)
        meta(con, "until", iso(until))
        con.commit()
        return n

def run(con):
    """Seed oqimidan (app/seed_cameras.run oxiri) yoki API birinchi so'rovida chaqiriladi. Idempotent."""
    init(con)
    ensure_cameras(con)
    ensure_persons(con)
    return materialize(con)
