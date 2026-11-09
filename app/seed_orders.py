"""«Buyruqlar» moduli uchun demo ma'lumot (sun'iy, mavjud bazaga qo'shiladi; to'liq qayta seed shart emas).

run(con) — idempotent:
  1. Buyruqlar reyestri (arxiv, historic=1): barcha talabalar uchun qabul buyruqlari (yil × ta'lim shakli), kursga o'tkazish
     buyruqlari, akademik ta'til buyruqlari (student_leaves.order_no raqamlari bilan), bir nechta guruh o'zgarishi.
     Ataylab kiritilgan nomuvofiqliklar (≈14 ta) — «Muammoli talabalar» sahifasini namoyish qilish uchun; ro'yxati order_meta('anomalies').
  2. Namuna arizalar (PDF matnli, PDF skan, PNG, DOCX) va katta ro'yxatlar (XLSX ~7 800 qator, 2 versiya; sirtqi CSV) — data/orders/samples.
  3. Demo buyruqlar: katta ro'yxatli chetlashtirish loyihasi (2 versiya), imzoga yuborilgan familiya o'zgarishi,
     prorektor kelishgan akademik ta'til, Sirtqi bo'limning loyihasi.
Hech bir talaba ma'lumoti o'zgartirilmaydi (ta'sir faqat rektor imzolaganda)."""
import datetime as dt, io, json, random
from . import db, rbac

META = "CREATE TABLE IF NOT EXISTS order_meta(k TEXT PRIMARY KEY, v TEXT)"

def _meta(con, k, v=None):
    con.execute(META)
    if v is None:
        r = con.execute("SELECT v FROM order_meta WHERE k=?", (k,)).fetchone()
        return json.loads(r[0]) if r else None
    con.execute("INSERT OR REPLACE INTO order_meta(k,v) VALUES(?,?)", (k, json.dumps(v, ensure_ascii=False)))

def run(con, force=False):
    con.execute(META)
    if force or not con.execute("SELECT 1 FROM orders WHERE historic=1 LIMIT 1").fetchone():
        registry(con)
    from . import orders as O
    if force or not (O.SAMPLES / "index.json").exists():
        samples(con)
    if force or not con.execute("SELECT 1 FROM orders WHERE demo IS NOT NULL LIMIT 1").fetchone():
        demo(con)
    con.commit()

# ---------------------------------------------------------------------------------------------
# 1. Reyestr
# ---------------------------------------------------------------------------------------------
Q_DATE = {"kunduzgi": "08-28", "magistr": "09-02", "sirtqi": "10-12", "masofaviy": "10-14"}
K_DATE = {"kunduzgi": "08-30", "sirtqi": "09-15", "masofaviy": "09-16"}
FORM_UZ = {"kunduzgi": "kunduzgi ta'lim (bakalavriat)", "magistr": "magistratura", "sirtqi": "sirtqi ta'lim", "masofaviy": "masofaviy ta'lim"}
LEAVE_REASONS = ["sog'lig'i bo'yicha (tibbiy xulosa)", "homiladorlik va tug'ish", "oilaviy sharoit", "muddatli harbiy xizmat", "bola parvarishi"]

def registry(con):
    R = random.Random(20261109)
    YEAR = dt.date.today().year if dt.date.today().month >= 9 else dt.date.today().year - 1
    st = db.rows(con, """SELECT s.id, s.hemis_id, s.full_name, s.group_id, s.status, s.study_form, s.gender, g.name grp, g.course, g.form, g.level, g.direction
                         FROM students s JOIN groups_ g ON g.id=s.group_id ORDER BY s.id""")
    if not st: return
    groups = db.rows(con, "SELECT id, name, course, form, level, direction FROM groups_")
    gk = {}
    for g in groups: gk.setdefault((g["form"], g["level"], g["course"]), []).append(g)
    fk = lambda s: "magistr" if s["level"] == "magistr" else (s["form"] or s["study_form"] or "kunduzgi")
    adm = lambda s: YEAR - int(s["course"] or 1) + 1
    used = set()
    pool = [s for s in st if s["status"] == "faol"]; R.shuffle(pool)
    def pick(cond, n):
        out = []
        for s in pool:
            if len(out) >= n: break
            if s["id"] not in used and cond(s): out.append(s); used.add(s["id"])
        return out
    def alt(s, prefer_dir=True):
        c = [g for g in gk.get((s["form"], s["level"], s["course"]), []) if g["id"] != s["group_id"]]
        same = [g for g in c if g["direction"] == s["direction"]] if prefer_dir else []
        return R.choice(same or c) if (same or c) else None
    kb = lambda s: s["form"] == "kunduzgi" and s["level"] == "bakalavr"
    sq = lambda s: s["form"] == "sirtqi"
    A = {"no_admission": pick(lambda s: kb(s), 2) + pick(sq, 1),
         "no_transfer": pick(lambda s: kb(s) and s["course"] >= 3, 2) + pick(lambda s: sq(s) and s["course"] >= 2, 1),
         "double_admission": pick(lambda s: kb(s) and s["course"] >= 2, 1),
         "exit_then_order": pick(lambda s: sq(s) and s["course"] >= 3, 1),
         "group_mismatch": pick(lambda s: kb(s) and alt(s), 2) + pick(lambda s: sq(s) and alt(s), 1),
         "expelled_active": pick(kb, 1) + pick(sq, 1),
         "group_ok": pick(lambda s: kb(s) and s["course"] >= 2 and alt(s), 4)}
    lv = db.rows(con, """SELECT l.*, s.hemis_id, s.full_name, s.group_id, s.study_form, g.name grp, g.course FROM student_leaves l
                         JOIN students s ON s.id=l.student_id JOIN groups_ g ON g.id=s.group_id ORDER BY l.id""")
    A["leave_no_order"] = [x for x in lv if x["student_id"] not in used][:1]
    skip_adm = {s["id"] for s in A["no_admission"]}
    skip_tr = {s["id"] for s in A["no_transfer"]}
    old_group = {s["id"]: alt(s) for s in A["group_ok"]}            # qabul/kurs buyruqlarida eski guruh — keyin guruh o'zgarishi buyrug'i
    specs = []                                                      # (sana, kind, title, form, items, reg|None, params)
    def it(s, gid=None, gname=None, course=None, data=None):
        return (s["id"], s["hemis_id"], s["full_name"], gid or s["group_id"], gname or s["grp"], course, json.dumps(data or {}, ensure_ascii=False))
    # qabul
    by = {}
    for s in st: by.setdefault((adm(s), fk(s)), []).append(s)
    for (y, f), ss in sorted(by.items()):
        its = []
        for s in ss:
            if s["id"] in skip_adm: continue
            og = old_group.get(s["id"])
            its.append(it(s, og["id"] if og else None, og["name"] if og else None, 1))
        specs.append((f"{y}-{Q_DATE[f]}", "qabul", f"Talabalar safiga qabul qilish to'g'risida ({y}-yil, {FORM_UZ[f]})", f if f != "magistr" else "kunduzgi", its, None, {}))
    # ikki marta qabul (ziddiyat): masofaviy qabul buyrug'ida ham, boshqa guruh bilan
    for s in A["double_admission"]:
        mg = gk.get(("masofaviy", "bakalavr", s["course"])) or gk.get(("masofaviy", "bakalavr", 1))
        g = R.choice(mg)
        y = adm(s)
        specs.append((f"{y}-{Q_DATE['masofaviy']}", "qabul", f"Talabalar safiga qabul qilish to'g'risida ({y}-yil, masofaviy ta'lim, qo'shimcha)", "kunduzgi",
                      [it(s, g["id"], g["name"], 1)], None, {}))
    # kursga o'tkazish
    for y in range(YEAR - 2, YEAR + 1):
        for form in ("kunduzgi", "sirtqi", "masofaviy"):
            its = []
            for s in st:
                if (s["form"] or "kunduzgi") != form or adm(s) >= y: continue
                if y == YEAR and s["id"] in skip_tr: continue
                og = old_group.get(s["id"])
                its.append(it(s, og["id"] if og else None, og["name"] if og else None, y - adm(s) + 1))
            if its:
                specs.append((f"{y}-{K_DATE[form]}", "kurs", f"Talabalarni keyingi kursga o'tkazish to'g'risida ({y}-{y + 1} o'quv yili, {FORM_UZ[form]})", form, its, None, {}))
    # akademik ta'til (student_leaves raqamlari bilan)
    skip_lv = {x["id"] for x in A["leave_no_order"]}
    byno = {}
    for x in lv:
        if x["id"] in skip_lv: continue
        byno.setdefault(x["order_no"] or f"TH-?/{x['id']}", []).append(x)
    for no, xs in byno.items():
        d0 = min(x["start"] for x in xs)
        date = (dt.date.fromisoformat(d0) - dt.timedelta(days=R.randint(2, 6))).isoformat()
        its = [(x["student_id"], x["hemis_id"], x["full_name"], x["group_id"], x["grp"], x["course"],
                json.dumps({"date_from": x["start"], "date_to": x["end"], "reason": R.choice(LEAVE_REASONS)}, ensure_ascii=False)) for x in xs]
        forms = {x["study_form"] for x in xs}
        specs.append((date, "akademik_tatil", None, forms.pop() if len(forms) == 1 else "aralash", its, no, {}))
    # guruh o'zgarishi (muvofiq): eski guruh → joriy guruh
    its = [it(s, old_group[s["id"]]["id"], old_group[s["id"]]["name"], s["course"], {"group_from": old_group[s["id"]]["name"], "group_to": s["grp"],
              "group_to_id": s["group_id"], "reason": "talabaning arizasi (o'qish tili / jadval)"}) for s in A["group_ok"]]
    if its: specs.append((f"{YEAR}-09-20", "guruh", None, "kunduzgi", its, None, {}))
    # guruh mos emas: buyruq bor, bazada eski guruh qolib ketgan
    for form in ("kunduzgi", "sirtqi"):
        its = []
        for s in A["group_mismatch"]:
            if (s["form"] or "kunduzgi") != form: continue
            g = alt(s)
            its.append(it(s, None, None, s["course"], {"group_from": s["grp"], "group_to": g["name"], "group_to_id": g["id"], "reason": "talabaning arizasi"}))
        if its: specs.append((f"{YEAR}-10-05" if form == "kunduzgi" else f"{YEAR}-10-07", "guruh", None, form, its, None, {}))
    # chetlashtirilgan, keyin kursga o'tkazilgan (ziddiyat)
    its = [it(s, course=s["course"] - 2, data={"date_from": f"{YEAR - 1}-03-10", "reason": "oilaviy sharoit"}) for s in A["exit_then_order"]]
    if its: specs.append((f"{YEAR - 1}-03-07", "chetlashtirish_xohish", None, "sirtqi", its, None, {}))
    # chetlashtirilgan, bazada faol
    for form in ("kunduzgi", "sirtqi"):
        its = [it(s, course=s["course"], data={"date_from": f"{YEAR}-10-20"}) for s in A["expelled_active"] if (s["form"] or "kunduzgi") == form]
        if its: specs.append((f"{YEAR}-10-18", "chetlashtirish_tolov", None, form, its, None, {"date_from": f"{YEAR}-10-20"}))
    # raqamlash (xronologik) va yozish
    from .orders import KINDS
    specs.sort(key=lambda x: x[0])
    cnt = {}
    for date, kind, title, form, its, reg, params in specs:
        if not reg:
            yy = int(date[:4]) % 100; cnt[yy] = cnt.get(yy, 0) + 1; reg = f"TB-{yy:02d}/{cnt[yy]:04d}"
        ts = f"{date}T11:00:00"
        cur = con.execute("""INSERT INTO orders(kind,title,status,reg_no,order_date,study_form,source,basis,params,version,count,created_at,submitted_at,signed_at,applied_at,historic)
                             VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,1)""",
                          (kind, title or KINDS[kind]["title"], "imzolangan", reg, date, form, "arxiv", None, json.dumps(params), 1, len(its), ts, ts, ts, ts))
        oid = cur.lastrowid
        con.execute("""INSERT INTO order_versions(order_id,no,created_by,created_by_name,created_at,source,count,added,removed,unmatched,note)
                       VALUES(?,?,?,?,?,?,?,?,?,?,?)""", (oid, 1, None, "Arxiv: HEMIS importi", ts, "arxiv", len(its), len(its), 0, 0, "Qog'oz arxivdan import (demo)"))
        con.executemany("INSERT INTO order_students(order_id,version,student_id,hemis_id,full_name,group_id,group_name,course,data) VALUES(?,?,?,?,?,?,?,?,?)",
                        [(oid, 1) + x for x in its])
        con.execute("INSERT INTO order_log(order_id,ts,user_id,user_name,action,detail) VALUES(?,?,?,?,?,?)", (oid, ts, None, "Tizim", "arxivdan import qilindi", f"{reg} · {len(its)} ta talaba"))
    _meta(con, "anomalies", {k: [x.get("student_id", x["id"]) for x in v] for k, v in A.items()})
    con.commit()
    print(f"Buyruqlar reyestri: {len(specs)} ta arxiv buyrug'i, {sum(len(x[4]) for x in specs)} ta yozuv; nomuvofiqliklar: "
          + ", ".join(f"{k}={len(v)}" for k, v in A.items() if k != "group_ok"))

# ---------------------------------------------------------------------------------------------
# 2. Namuna fayllar
# ---------------------------------------------------------------------------------------------
def _wrap(text, n=88):
    out = []
    for para in text.split("\n"):
        line = ""
        for w in para.split(" "):
            if len(line) + len(w) + 1 > n: out.append(line); line = w
            else: line = (line + " " + w).strip()
        out.append(line)
    return out

def text_pdf(lines, bold_idx=()) -> bytes:
    """Matn qatlamli oddiy PDF (Helvetica, WinAnsi) — tashqi kutubxonasiz."""
    def esc(s): return s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    body = ["BT", "15 TL", "60 790 Td"]
    for i, l in enumerate(lines):
        body.append(f"/{'F2' if i in bold_idx else 'F1'} 11 Tf ({esc(l)}) Tj T*")
    body.append("ET")
    content = "\n".join(body).encode("latin-1", "replace")
    objs = [b"<< /Type /Catalog /Pages 2 0 R >>", b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 4 0 R /F2 5 0 R >> >> /Contents 6 0 R >>",
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>",
            b"<< /Length %d >>\nstream\n" % len(content) + content + b"\nendstream"]
    out = io.BytesIO(); out.write(b"%PDF-1.4\n"); offs = []
    for i, o in enumerate(objs, 1):
        offs.append(out.tell()); out.write(b"%d 0 obj\n" % i + o + b"\nendobj\n")
    x = out.tell()
    out.write(b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1) + b"".join(b"%010d 00000 n \n" % o for o in offs))
    out.write(b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objs) + 1, x))
    return out.getvalue()

def text_png(lines, bold_idx=()):
    """Skanerlangan qog'oz ko'rinishidagi rasm (OCR namoyishi uchun)."""
    from PIL import Image, ImageDraw, ImageFont
    def font(b):
        for p in (["/System/Library/Fonts/Supplemental/Arial Bold.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"] if b else
                  ["/System/Library/Fonts/Supplemental/Arial.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"]):
            try: return ImageFont.truetype(p, 30)
            except OSError: continue
        return ImageFont.load_default()
    f1, f2 = font(False), font(True)
    W, H = 1654, 140 + 46 * len(lines) + 120
    im = Image.new("RGB", (W, H), (250, 249, 245)); d = ImageDraw.Draw(im)
    y = 110
    for i, l in enumerate(lines):
        d.text((120, y), l, fill=(25, 25, 30), font=f2 if i in bold_idx else f1); y += 46
    return im.rotate(0.4, expand=False, fillcolor=(250, 249, 245))

def _docx(lines, bold_idx=()) -> bytes:
    from docx import Document
    from docx.shared import Pt
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    d = Document()
    for i, l in enumerate(lines):
        p = d.add_paragraph(); r = p.add_run(l); r.font.size = Pt(12); r.bold = i in bold_idx
        if l.strip() == "ARIZA": p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        elif i < 6: p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    b = io.BytesIO(); d.save(b); return b.getvalue()

def _app_lines(s, fac, body, date_str):
    head = ["ISFT instituti rektori", "I.R. G'ulomovga", f"{fac} fakulteti", f"{s['grp']} guruh talabasi", f"{s['full_name']}dan",
            f"(HEMIS ID: {s['hemis_id']}, tel.: {s.get('phone') or '+998 90 000 00 00'})", "", "ARIZA", ""]
    return head + _wrap(body) + ["", f"{date_str}" + " " * 40 + f"Imzo: ________  {s['full_name'].split()[1][0]}. {s['full_name'].split()[0]}"]

def samples(con):
    from . import orders as O
    from .documents import d_uz
    R = random.Random(7731)
    O.SAMPLES.mkdir(parents=True, exist_ok=True)
    anom = set(x for v in (_meta(con, "anomalies") or {}).values() for x in v)
    today = dt.date.today()
    base = """SELECT s.*, g.name grp, g.course, g.form, g.direction, f.name fac FROM students s JOIN groups_ g ON g.id=s.group_id JOIN faculties f ON f.id=s.faculty_id
              WHERE {w} ORDER BY s.id"""
    def one(w, salt):
        rs = [r for r in db.rows(con, base.format(w=w)) if r["id"] not in anom]
        return random.Random(salt).choice(rs) if rs else None
    idx, made = [], {}
    def put(fname, data, title, kind, sid, sirtqi=False, typ="ariza", note=""):
        (O.SAMPLES / fname).write_bytes(data)
        idx.append({"file": fname, "title": title, "kind": kind, "student_id": sid, "sirtqi": sirtqi, "type": typ, "note": note,
                    "format": fname.rsplit(".", 1)[1].upper()})
    # 1) familiya — PDF (matn qatlami)
    s = one("s.status='faol' AND s.gender='F' AND g.form='kunduzgi' AND g.level='bakalavr' AND s.full_name LIKE '%va %' AND s.full_name NOT LIKE 'Karimova%'", 11)
    if s:
        new = R.choice([x for x in ("Karimova", "Rashidova", "Tursunova", "Aliyeva", "Saidova") if not s["full_name"].startswith(x)])
        old = s["full_name"].split()[0]; wd = today - dt.timedelta(days=22)
        body = (f"Men, {s['full_name']}, {d_uz(wd)}da turmush qurganligim munosabati bilan familiyamni {old}dan {new}ga o'zgartirishingizni so'rayman. "
                f"Nikoh to'g'risidagi guvohnoma I-TN No 0451277, {wd.strftime('%d.%m.%Y')} yilda Yunusobod tumani FHDYO bo'limi tomonidan berilgan.\n"
                "Ilova: nikoh to'g'risidagi guvohnoma nusxasi, pasport nusxasi (2 varaq).")
        L = _app_lines(s, s["fac"], body, (today - dt.timedelta(days=6)).strftime("%d.%m.%Y"))
        put("ariza_familiya.pdf", text_pdf(L, {7}), "Familiya o'zgartirish (nikoh guvohnomasi)", "familiya", s["id"], note="PDF, matn qatlami")
        made["familiya"] = (s, L)
    # 2) akademik ta'til — DOCX
    s = one("s.status='faol' AND g.form='kunduzgi' AND g.level='bakalavr' AND s.gender='M' AND g.course=2", 12)
    if s:
        a, b = today + dt.timedelta(days=7), today + dt.timedelta(days=7 + 364)
        body = (f"Men, {s['full_name']}, sog'lig'im yomonlashgani sababli (tibbiy xulosa ilova qilinadi) menga {d_uz(a)}dan {d_uz(b)}gacha "
                "akademik ta'til berishingizni so'rayman. Ta'til tugagach o'qishni davom ettirishga majburman.\nIlova: VKK tibbiy xulosasi No 118/26.")
        L = _app_lines(s, s["fac"], body, (today - dt.timedelta(days=3)).strftime("%d.%m.%Y"))
        put("ariza_akademik_tatil.docx", _docx(L, {7}), "Akademik ta'til (sog'lig'i bo'yicha)", "akademik_tatil", s["id"], note="DOCX")
        made["akademik_tatil"] = (s, L)
    # 3) ta'tildan qaytish — PNG (OCR)
    s = one("s.status=\"akademik ta'til\" AND g.form='kunduzgi' AND s.id IN (SELECT student_id FROM student_leaves)", 13)
    if s:
        d = today + dt.timedelta(days=11)
        body = (f"Men, {s['full_name']}, akademik ta'tildan qaytganim munosabati bilan {d_uz(d)}dan o'qishni davom ettirishimga ruxsat berishingizni so'rayman.")
        L = _app_lines(s, s["fac"], body, (today - dt.timedelta(days=2)).strftime("%d.%m.%Y"))
        b = io.BytesIO(); text_png(L, {7}).save(b, "PNG")
        put("ariza_tatildan_qaytish.png", b.getvalue(), "Akademik ta'tildan qaytish (rasm — OCR)", "tatildan_qaytish", s["id"], note="PNG skan — OCR kerak")
    # 4) o'z xohishi — DOCX, sirtqi
    s = one("s.status='faol' AND g.form='sirtqi' AND g.course=2", 14)
    if s:
        d = today + dt.timedelta(days=6)
        body = (f"Men, {s['full_name']}, oilaviy sharoitim tufayli o'z xohishimga ko'ra {d_uz(d)}dan talabalar safidan chetlashtirishingizni so'rayman. "
                "To'lov-kontrakt bo'yicha hisob-kitob qilinishini so'rayman.")
        L = _app_lines(s, s["fac"], body, (today - dt.timedelta(days=1)).strftime("%d.%m.%Y"))
        put("ariza_ozi_xohishi_sirtqi.docx", _docx(L, {7}), "O'z xohishi bilan chetlashtirish (sirtqi)", "chetlashtirish_xohish", s["id"], sirtqi=True, note="DOCX · sirtqi talaba")
        made["chetlashtirish_xohish"] = (s, L)
    # 5) boshqa OTMga ko'chirish — PDF (matn)
    s = one("s.status='faol' AND g.form='kunduzgi' AND g.level='bakalavr' AND g.course=2", 15)
    if s:
        body = ("Men, " + s["full_name"] + ", yashash joyim o'zgarganligi sababli qabul qiluvchi OTMning roziligi (" + d_uz(today - dt.timedelta(days=12)) +
                "dagi 412-son xat) asosida o'qishimni Samarqand iqtisodiyot va servis institutiga ko'chirishingizni so'rayman. "
                f"Talabalar safidan {d_uz(today + dt.timedelta(days=14))}dan chiqarishingizni so'rayman.")
        L = _app_lines(s, s["fac"], body, (today - dt.timedelta(days=4)).strftime("%d.%m.%Y"))
        put("ariza_kochirish.pdf", text_pdf(L, {7}), "Boshqa OTMga ko'chirish", "kochirish", s["id"], note="PDF, matn qatlami")
    # 6) guruh o'zgarishi — skanerlangan PDF (rasm, matn qatlamisiz)
    s = one("s.status='faol' AND g.form='kunduzgi' AND g.level='bakalavr' AND g.course=3", 16)
    if s:
        tg = db.one(con, "SELECT name FROM groups_ WHERE form='kunduzgi' AND level='bakalavr' AND course=? AND direction=? AND id!=? ORDER BY id LIMIT 1",
                    (s["course"], s["direction"], s["group_id"]))
        if tg:
            body = (f"Men, {s['full_name']}, {s['grp']} guruh talabasi, ish vaqtim o'zgargani sababli meni {tg['name']} guruhiga o'tkazishingizni so'rayman.")
            L = _app_lines(s, s["fac"], body, (today - dt.timedelta(days=2)).strftime("%d.%m.%Y"))
            b = io.BytesIO(); text_png(L, {7}).save(b, "PDF", resolution=150)
            put("ariza_guruh_skan.pdf", b.getvalue(), "Guruhni o'zgartirish (skanerlangan PDF — OCR)", "guruh", s["id"], note="PDF skan, matn qatlami yo'q — OCR kerak")
    # 7) katta ro'yxatlar: kontrakt qarzdorlari (2 versiya) va sirtqi CSV
    debt = db.rows(con, """SELECT s.id, s.hemis_id, s.full_name, g.name grp, s.study_form, s.contract_amount - s.paid_amount debt FROM students s JOIN groups_ g ON g.id=s.group_id
                          WHERE s.status='faol' AND s.payment_type='kontrakt' AND s.contract_amount > s.paid_amount ORDER BY g.name, s.full_name""")
    if debt:
        RR = random.Random(99)
        broken = set(RR.sample(range(len(debt)), 3))
        def row(i, x, brk=False):
            h, n = x["hemis_id"], x["full_name"]
            if brk: h = h[:-3] + str((int(h[-3:]) + 7) % 1000).zfill(3); n = n.replace("o", "a", 1) if "o" in n else n + "x"
            return [i, n, h, x["grp"], int(x["debt"])]
        v1 = [row(i, x, i - 1 in broken) for i, x in enumerate(debt, 1)]
        paid = set(RR.sample(range(len(debt)), min(214, len(debt) // 10)))
        extra = db.rows(con, """SELECT s.id, s.hemis_id, s.full_name, g.name grp, 3500000 debt FROM students s JOIN groups_ g ON g.id=s.group_id
                               WHERE s.status='faol' AND s.payment_type='kontrakt' AND s.contract_amount <= s.paid_amount AND g.form='kunduzgi' ORDER BY s.id LIMIT 6""")
        v2 = [row(0, x) for i, x in enumerate(debt) if i not in paid] + [row(0, x) for x in extra]
        for k, r in enumerate(v2, 1): r[0] = k
        H = ["№", "F.I.Sh.", "HEMIS ID", "Guruh", "Qarzdorlik (so'm)"]
        ok = _xlsx(O.SAMPLES / "qarzdorlar_v1.xlsx", H, v1, "Kontrakt qarzdorlari — 1-ro'yxat (buxgalteriya)")
        if ok:
            _xlsx(O.SAMPLES / "qarzdorlar_v2.xlsx", H, v2, "Kontrakt qarzdorlari — tuzatilgan ro'yxat")
            idx.append({"file": "qarzdorlar_v1.xlsx", "title": f"Kontrakt qarzdorlari: 1-ro'yxat ({len(v1)} ta, 3 tasida HEMIS xato)", "type": "royxat", "format": "XLSX", "sirtqi": False})
            idx.append({"file": "qarzdorlar_v2.xlsx", "title": f"Kontrakt qarzdorlari: tuzatilgan ro'yxat ({len(v2)} ta: −{len(paid)} to'lagan, +{len(extra)})", "type": "royxat", "format": "XLSX", "sirtqi": False})
        sq = [x for x in debt if x["study_form"] == "sirtqi"][:45]
        import csv
        b = io.StringIO(); w = csv.writer(b, delimiter=";"); w.writerow(H)
        for k, x in enumerate(sq, 1): w.writerow(row(k, x))
        (O.SAMPLES / "sirtqi_qarzdorlar.csv").write_bytes(("﻿" + b.getvalue()).encode("utf-8"))
        idx.append({"file": "sirtqi_qarzdorlar.csv", "title": f"Sirtqi: kontrakt qarzdorlari ({len(sq)} ta, CSV)", "type": "royxat", "format": "CSV", "sirtqi": True})
    (O.SAMPLES / "index.json").write_text(json.dumps(idx, ensure_ascii=False, indent=1), encoding="utf-8")
    _meta(con, "samples", {k: v[0]["id"] for k, v in made.items()})
    con.commit()

def _xlsx(path, head, rows, title) -> bool:
    try:
        from openpyxl import Workbook
    except ImportError:
        return False
    wb = Workbook(write_only=True); ws = wb.create_sheet("Ro'yxat")
    ws.append([title]); ws.append([]); ws.append(head)
    for r in rows: ws.append(r)
    wb.save(path); return True

# ---------------------------------------------------------------------------------------------
# 3. Demo buyruqlar
# ---------------------------------------------------------------------------------------------
def demo(con):
    from . import orders as O, orders_intake as IN
    if O._con is None: O._con = con
    reg = db.one(con, "SELECT id FROM users WHERE role='talabalar' ORDER BY id LIMIT 1")
    if not reg: return
    cr = rbac.ctx_for(con, reg["id"])
    now = dt.datetime.now().replace(microsecond=0)
    idx = {x["file"]: x for x in json.loads((O.SAMPLES / "index.json").read_text(encoding="utf-8"))} if (O.SAMPLES / "index.json").exists() else {}
    # a) katta ro'yxat: 2 versiya
    if "qarzdorlar_v1.xlsx" in idx:
        o = O.create_order(cr, "chetlashtirish_tolov", [], "fayl", "To'lov-kontrakt qarzdorligini bartaraf etmagan talabalarni chetlashtirish to'g'risida (kuzgi semestr)",
                           params={"date_from": (dt.date.today() + dt.timedelta(days=10)).isoformat()},
                           note="Buxgalteriya ro'yxati asosida. To'lov qilganlar keyingi versiyalarda chiqariladi.")
        con.execute("UPDATE orders SET demo='bulk', created_at=? WHERE id=?", ((now - dt.timedelta(days=2, hours=3)).isoformat(), o["id"]))
        for f, ago in (("qarzdorlar_v1.xlsx", dt.timedelta(days=2, hours=2)), ("qarzdorlar_v2.xlsx", dt.timedelta(days=1, hours=5))):
            O._upload_list(cr, o["id"], f, (O.SAMPLES / f).read_bytes(), ts=(now - ago).isoformat())
    # b) arizadan: imzoga yuborilgan / kelishilgan / sirtqi loyiha
    pro = db.one(con, "SELECT id FROM users WHERE role='prorektor_oquv' ORDER BY id LIMIT 1")
    sir = db.one(con, "SELECT id FROM users WHERE role='sirtqi' ORDER BY id LIMIT 1")
    for fname, status, who in (("ariza_familiya.pdf", "yuborilgan", cr), ("ariza_akademik_tatil.docx", "kelishilgan", cr),
                               ("ariza_ozi_xohishi_sirtqi.docx", "loyiha", rbac.ctx_for(con, sir["id"]) if sir else None)):
        x = idx.get(fname)
        if not x or not who: continue
        raw = (O.SAMPLES / fname).read_bytes()
        ex = IN.extract(fname, raw); det = IN.detect(ex["text"])
        f = {k: v for k, v in det["fields"].items() if not k.startswith("_")}
        if det["kind"] == "familiya" and not f.get("old_surname"):
            f["old_surname"] = db.one(con, "SELECT full_name FROM students WHERE id=?", (x["student_id"],))["full_name"].split()[0]
        o = O.create_order(who, det["kind"] or x["kind"], [{"student_id": x["student_id"], "data": f}], "ariza")
        stored = O._save_upload(raw, fname)
        O._attach(o["id"], who, "ariza", fname, stored, len(raw), x["student_id"])
        con.execute("INSERT INTO order_applications(created_by,created_at,filename,stored,method,text,kind,fields,student_id,order_id,status) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                    (who.user["id"], (now - dt.timedelta(hours=30)).isoformat(), fname, stored, ex["method"], ex["text"], det["kind"], json.dumps(f, ensure_ascii=False),
                     x["student_id"], o["id"], "loyihada"))
        sets = {"demo": fname, "created_at": (now - dt.timedelta(hours=28)).isoformat()}
        con.execute("UPDATE order_versions SET created_at=? WHERE order_id=?", (sets["created_at"], o["id"]))
        con.execute("UPDATE order_log SET ts=? WHERE order_id=?", (sets["created_at"], o["id"]))
        if status in ("yuborilgan", "kelishilgan"): sets["status"] = "yuborilgan"; sets["submitted_at"] = (now - dt.timedelta(hours=20)).isoformat()
        if status == "kelishilgan" and pro: sets.update(status="kelishilgan", forwarded_by=pro["id"], forwarded_at=(now - dt.timedelta(hours=6)).isoformat())
        con.execute(f"UPDATE orders SET {', '.join(f'{k}=?' for k in sets)} WHERE id=?", (*sets.values(), o["id"]))
        if status != "loyiha": O._log(o["id"], who, "imzoga yuborildi", "demo")
        if status == "kelishilgan": O._log(o["id"], rbac.ctx_for(con, pro["id"]), "prorektor kelishdi", "demo")
    con.commit()
