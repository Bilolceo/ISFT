"""Auditoriyalar bandligi uchun demo: xona sig'imlari, haftalik dars jadvali, kameralar (simulyator) va 4 haftalik tarix."""
import datetime as dt
from . import occupancy as OC

def run(con, R):
    OC.init(con)
    c = con.cursor()
    rooms = [dict(r) for r in con.execute("SELECT * FROM rooms WHERE kind!='umumiy' ORDER BY name")]
    short = lambda r: r["name"].split(" ·")[0]
    cap = {}
    for r in rooms:
        n = short(r)
        if n in ("A-101", "A-201", "D-101", "E-101"): cap[r["id"]] = 120   # katta ma'ruza zallari
        elif r["kind"] == "kompyuter sinfi": cap[r["id"]] = 24
        elif n in ("B-103", "B-104"): cap[r["id"]] = 20            # kichik seminar xonalari
        else: cap[r["id"]] = R.choice([36, 40, 40, 44, 48, 50])   # jami ≈ 7 500 o'rin (NQAAE)
        c.execute("UPDATE rooms SET capacity=? WHERE id=?", (cap[r["id"]], r["id"]))
    c.execute("UPDATE rooms SET capacity=0 WHERE kind='umumiy'")

    # --- haftalik jadval: har guruhga ~12 para, bo'sh (xona, kun, para) dan ---
    # jadval faqat kampusda o'qiydiganlar uchun: kunduzgi bakalavr va magistratura (sirtqi — sessiya, masofaviy — onlayn)
    tg = [dict(x) for x in con.execute("SELECT tg.* FROM teacher_groups tg JOIN groups_ g ON g.id=tg.group_id WHERE g.form='kunduzgi'")]
    by_group = {}
    for x in tg: by_group.setdefault(x["group_id"], []).append(x)
    gsize = {g: n for g, n in con.execute("SELECT group_id, COUNT(*) FROM students GROUP BY group_id")}
    busy_room, busy_group, busy_teacher = set(), set(), set()
    lecture = [r for r in rooms if cap[r["id"]] >= 100]
    comp = [r for r in rooms if r["kind"] == "kompyuter sinfi"]
    small = [r for r in rooms if cap[r["id"]] <= 20]
    cold = [r for r in rooms if short(r) in ("C-301", "C-302", "C-304", "B-304")]   # yuqori qavat — kam ishlatiladi
    normal = [r for r in rooms if r not in lecture and r not in comp and r not in small and r not in cold]
    rows = []
    def place(gid, subj, tid, pool, label=None, tries=60):
        for _ in range(tries):
            wd = R.choices(range(6), [10, 10, 10, 10, 9, 3])[0]; sl = R.choices(range(1, 7), [9, 10, 9, 8, 6, 3])[0]
            room = R.choice(pool)
            if (room["id"], wd, sl) in busy_room or (gid, wd, sl) in busy_group or (tid, wd, sl) in busy_teacher: continue
            busy_room.add((room["id"], wd, sl)); busy_group.add((gid, wd, sl)); busy_teacher.add((tid, wd, sl))
            rows.append((room["id"], wd, sl, gid, label or subj, tid)); return True
        return False
    for gid, subs in by_group.items():
        k = 0
        for x in subs:
            place(gid, x["subject"], x["teacher_id"], lecture if k == 0 else normal, label=f"Ma'ruza: {x['subject']}" if k == 0 else None); k += 1
            place(gid, x["subject"], x["teacher_id"], normal)
            if R.random() < .45: place(gid, x["subject"], x["teacher_id"], comp + normal)
        if gsize.get(gid, 0) >= 27 and R.random() < .5:      # katta guruh kichik xonaga — sig'imdan oshish
            x = R.choice(subs); place(gid, x["subject"], x["teacher_id"], small)
        if R.random() < .25:
            x = R.choice(subs); place(gid, x["subject"], x["teacher_id"], cold)
    c.executemany("INSERT INTO schedule(room_id,weekday,slot,group_id,subject,teacher_id) VALUES(?,?,?,?,?,?)", rows)
    # demo: bitta o'qituvchi seshanba va payshanba 5-parada darsga kelmaydi (kamera xonani bo'sh ko'radi)
    con.commit()
    OC._sched_cache["t"] = 0; OC.GHOST_TEACHER["id"] = None
    OC._sched(con)

    # --- xizmat zonalari (qabul, kassa, oshxona, serverxona...) va hikoya-1 — app/seed_cameras.py ---
    from . import seed_cameras
    seed_cameras.prepare(con, R)
    OC._sched(con)
    rooms = [dict(r) for r in con.execute("SELECT * FROM rooms ORDER BY name")]   # endi koridor va xizmat zonalari ham kamerali
    # --- kameralar: hammasi simulyator (haqiqiy kamera ulanganda rejim 'isapi' ga o'tkaziladi) ---
    for r in rooms:
        c.execute("INSERT INTO cameras(room_id,vendor,mode,channel,status) VALUES(?,?,?,1,'kutilmoqda')", (r["id"], "Simulyator", "sim"))
    # --- 4 hafta + bugun: har 15 daqiqada o'lchov (08:00–18:15) ---
    now = OC.now(); start = dt.datetime.combine(now.date() - dt.timedelta(days=28), dt.time(8, 0))
    pts = []
    d = start
    while d <= now:
        if d.weekday() < 6 and dt.time(8, 0) <= d.time() <= dt.time(18, 15):
            for r in rooms:
                pts.append((r["id"], OC.iso(d), OC.sim_count(con, r["id"], d)))
        d += dt.timedelta(minutes=15)
        if d.time() > dt.time(18, 15): d = dt.datetime.combine(d.date() + dt.timedelta(days=1), dt.time(8, 0))
    c.executemany("INSERT INTO occupancy(room_id,ts,count) VALUES(?,?,?)", pts)
    for r in rooms:
        c.execute("UPDATE cameras SET status='onlayn', last_seen=?, last_count=? WHERE room_id=?", (OC.iso(now), OC.sim_count(con, r["id"], now), r["id"]))
    con.commit()
    seed_cameras.run(con, R)    # modellar, holat (oflayn / to'sib qo'yilgan / soat farqi), 30 kunlik voqealar, navbatlar
