"""«HEMIS almashinuvi» (app/hemis.py, hemis_map.py, hemis_plan.py, hemis_api.py; app/nazorat.py — «HEMIS almashinuvi» bo'limi; docs/hemis.md).

1. Birlik: ustun xaritasi (o'zbek lotin/kirill, rus, ingliz sarlavhalar; tepada sarlavha qatorlari; Familiya/Ism/Otasining ismi alohida;
   JShShIR o'qilmaydi), qiymatlarni normallashtirish, kirill/lotin ism-sharif solishtirish.
2. HTTP: dry-run sonlari (yangi / o'zgargan / ziddiyatli / topilmadi), ko'rib chiqishda baza o'zgarmaydi, profil, qo'llash (snapshot, audit),
   hech narsa o'chirilmaydi, qayta import — farq «mos keldi», «qaytdi», farqlar hayotiy sikli, eksport (.xlsx tuzilmasi + SHA-256),
   API ulagichi (standart o'chiq, token bazada yo'q, probe), ruxsatlar (rektor — jamlangan, kafedra — 403), sifat tekshiruvlari.
3. Jarayon ichida (bazaning nusxasi): qo'llash o'rtasidagi xato — hammasi qaytariladi; Nazorat markazi detektori.
4. Brauzer (PW va CHROME berilganda): import ko'rib chiqish va Farqlar navbati (tools/hemis_check.js).

Barcha ma'lumot SINTETIK (test ichida yaratiladi; haqiqiy shaxsiy ma'lumot yo'q). Oxirida test yozuvlari tozalanadi.
Ishga tushirish: python tests/run_all.py --only hemis
"""
import contextlib, datetime as dt, hashlib, io, json, os, re, shutil, sqlite3, subprocess, sys, tempfile
from pathlib import Path
import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
B = os.environ.get("ISFT_TEST_URL", "http://127.0.0.1:8000")
DBP = Path(os.environ.get("ISFT_CORE_DB") or ROOT / "data" / "jarvis.db")
PW = re.search(r'DEMO_PASSWORD = os.getenv\("ISFT_CORE_DEMO_PASSWORD", "([^"]+)"\)', (ROOT / "app" / "rbac.py").read_text()).group(1)
P = "/api/hemis"
fails = []
def ok(cond, msg):
    print(("  ✓ " if cond else "  ✗ ") + msg)
    if not cond: fails.append(msg)
def q(sql, a=()):
    con = sqlite3.connect(DBP, timeout=30); con.row_factory = sqlite3.Row
    try: return [dict(r) for r in con.execute(sql, a).fetchall()]
    finally: con.close()
def w(sql, a=()):
    con = sqlite3.connect(DBP, timeout=30)
    try: cur = con.execute(sql, a); con.commit(); return cur.lastrowid
    finally: con.close()
def uid(role):
    r = q("SELECT id FROM users WHERE role=? AND COALESCE(active,1)=1 ORDER BY id LIMIT 1", (role,)); assert r, role; return r[0]["id"]
def S(u):
    c = httpx.Client(base_url=B, timeout=300)
    r = c.post("/api/login", json={"user_id": u, "password": PW}); assert r.status_code == 200, f"login {u}: {r.text}"
    return c
def last_audit(): return (q("SELECT MAX(id) m FROM audit_log") or [{"m": 0}])[0]["m"] or 0
def xlsx(rows):
    from openpyxl import Workbook
    wb = Workbook(); ws = wb.active
    for r in rows: ws.append(r)
    b = io.BytesIO(); wb.save(b); return b.getvalue()
def csv_bytes(rows, delim=";", enc="utf-8-sig"):
    return "\n".join(delim.join(str(c) for c in r) for r in rows).encode(enc)

# =============================================================================================
print("== 1. Birlik: ustun xaritasi, normallashtirish, kirill/lotin")
from app import hemis_map as HM   # noqa: E402
cases = [
    (["№", "Талаба ИД", "Ф.И.Ш.", "Гуруҳ", "Таълим шакли", "Ҳолати", "Фуқаролиги", "ЖШШИР"], "o'zbek kirill"),
    (["T/r", "HEMIS ID", "F.I.Sh.", "Guruh", "Ta'lim shakli", "Holati", "Fuqarolik", "JShShIR"], "o'zbek lotin"),
    (["№", "ИД студента", "ФИО", "Группа", "Форма обучения", "Статус", "Гражданство", "ПИНФЛ"], "rus"),
    (["#", "Student ID", "Full name", "Group", "Education form", "Status", "Citizenship", "PINFL"], "ingliz"),
]
for hdr, nm in cases:
    m = HM.auto_map(hdr, "students")
    ok(set(m["map"].values()) == {"hemis_id", "full_name", "group", "study_form", "status", "citizenship"} and not m["missing"] and len(m["ignored"]) == 1,
       f"Sarlavhalar ({nm}): 6 maydon tanildi, JShShIR/PINFL o'qilmaydi")
m = HM.auto_map(["ID", "Фамилия", "Имя", "Отчество", "Группа"], "students")
ok({"last_name", "first_name", "middle_name"} <= set(m["map"].values()) and not m["missing"], "Familiya / Ism / Otasining ismi alohida ustunlarda — F.I.Sh. majburiyligi bajariladi")
raw = csv_bytes([["Talabalar ro'yxati (HEMIS eksporti)"], ["Sana: 14.11.2026"], [], ["HEMIS ID", "Familiya", "Ism", "Otasining ismi", "Guruh"],
                 ["3.525966527469E12", "Hasanov", "Doniyor", "Komil o‘g‘li", "IQT-2601"]])
p = HM.parse(raw, "royxat.csv", "students")
ok(p["header_row"] == 4 and p["records"][0]["hemis_id"] == "3.525966527469E12" and p["records"][0]["full_name"] == "Hasanov Doniyor Komil o‘g‘li",
   "Tepada sarlavha qatorlari — sarlavha 4-qatordan topildi; F.I.Sh. ustunlardan yig'ildi")
ok(HM.hemis_id("3.525966527469E12") == "3525966527469" and HM.hemis_id(3525966527469.0) == "3525966527469" and HM.hemis_id(" 3525 966 ") == "3525966",
   "HEMIS ID: Excel son / ilmiy yozuv / bo'shliqlar → matn")
ok(HM.parse(raw, "royxat.csv", "students", mapping={"Guruh": ""})["missing"] == ["group"], "Qo'lda «e'tiborsiz» belgilangan majburiy ustun — yetishmaydi")
ok((HM.status("Обучается"), HM.status("O'qimoqda"), HM.status("Академический отпуск"), HM.status("Chetlashtirilgan")) == ("faol", "faol", "akademik ta'til", "chetlashtirilgan"),
   "Holat: rus/o'zbek variantlari → ISFT Core qiymati")
ok((HM.form("Дистанционная"), HM.form("Masofaviy"), HM.form("Очная"), HM.form("Sirtqi")) == ("masofaviy", "masofaviy", "kunduzgi", "sirtqi"), "Ta'lim shakli (masofaviy ham)")
ok((HM.citizenship("Гражданин РУз"), HM.citizenship("O'zbekiston Respublikasi fuqarosi"), HM.citizenship("Qozog‘iston"), HM.citizenship("Xorijiy fuqaro")) == ("UZ", "UZ", "KZ", "XX"),
   "Fuqarolik → ISO kod (davlati ko'rsatilmagan xorijiy — XX)")
ok(HM.name_key("Ҳасанов Шоҳрух Комил ўғли") == HM.name_key("Hasanov Shohrux Komil o‘g‘li") == HM.name_key("Хасанов Шохрух Комил угли") == HM.name_key("Shohrux Hasanov Komil o'g'li"),
   "Ism-sharif: o'zbek kirill / lotin / rus kirill / so'z tartibi — bitta kalit")
ok(HM.name_key("Ergashev Otabek") == HM.name_key("Эргашев Отабек") and HM.name_key("Ergashev Otabek") != HM.name_key("Ergashev Otabek Baxtiyor o'g'li")
   and HM.name_key("Qodirov Ali") == HM.name_key("Кодиров Али") and HM.name_key("Karimov Ali") != HM.name_key("Karimova Aliya"),
   "Haqiqiy farq (otasining ismi qo'shilgan, boshqa ism) — farq; қ/к — bir xil")
ok(HM.translit("Ўзбекистон Ғалаба Ёшлар") == "O'zbekiston G'alaba Yoshlar", "Kirill → lotin (ў, ғ, ё)")
from app import hemis_api as HA   # noqa: E402
ok(HA.probe({"api_enabled": False, "api_base_url": "https://hemis.example.uz"})["sent"] is False and HA.VERIFIED is False, "Probe: o'chirilgan — tarmoqqa chiqmaydi; ulagich TASDIQLANMAGAN")
bad_urls = 0
for u in ("ftp://x.uz", "https://user:pw@x.uz", "https://x.uz/?token=1", "javascript:alert(1)"):
    try: HA.validate_url(u)
    except ValueError: bad_urls += 1
ok(bad_urls == 4 and HA.validate_url("https://hemis.isft.uz/") == "https://hemis.isft.uz", "API manzili: faqat http(s), login/parol va so'rov parametrlari yo'q")
ok(HM.pii_cols(["Telefon raqami", "Tug'ilgan sanasi", "Yashash manzili", "E-mail", "Guruh", "F.I.Sh.", "Адрес проживания", "Pasport seriyasi"]) == {0, 1, 2, 3, 6, 7},
   "Shaxsiy ustunlar qo'shimcha so'z bilan ham taniladi (telefon raqami, tug'ilgan sanasi, manzil, email, адрес)")
sp = HM.strip_pii([["HEMIS ID", "F.I.Sh.", "Guruh", "Telefon raqami"], ["1", "Manzila Karimova", "G1", "+998901234567"]])
ok(sp[1] == ["1", "Manzila Karimova", "G1", ""], "strip_pii: telefon bo'shatildi; «Manzila» ismi (ma'lumot qatori) sarlavha deb olinmadi")
ssrf = 0
for u in ("http://127.0.0.1:8000", "http://localhost", "http://169.254.169.254", "http://[::1]:80", "http://10.0.0.5", "http://192.168.1.1"):
    try: HA.validate_url(u)
    except ValueError: ssrf += 1
pr0 = HA.probe({"api_enabled": True, "api_base_url": "http://169.254.169.254", "api_probe_path": "/latest/meta-data"})
ok(ssrf == 6 and pr0["sent"] is False and pr0["result"] == "ichki_manzil", "SSRF: ichki manzillar (localhost, xususiy IP, metadata) rad etiladi; probe yubormaydi")
import zipfile as _zf   # noqa: E402
_bomb = io.BytesIO()
with _zf.ZipFile(_bomb, "w", _zf.ZIP_DEFLATED) as z_:
    z_.writestr("[Content_Types].xml", "<Types/>")
    with z_.open("xl/sharedStrings.xml", "w", force_zip64=True) as f_:
        blk = b" " * (1 << 20)
        for _ in range(HM.MAX_UNZIPPED // len(blk) + 2): f_.write(blk)
_bomb = _bomb.getvalue()
try: HM.read_rows(_bomb, "bomba.xlsx"); bomb_ok = False
except HM.ReadError as e_: bomb_ok = "katta" in str(e_)
ok(len(_bomb) < 2_000_000 and bomb_ok, f"XLSX zip bomba ({len(_bomb) // 1024} KB → >{HM.MAX_UNZIPPED >> 20} MB) — o'qilmaydi")
from openpyxl import Workbook as _WB   # noqa: E402
_wb = _WB(); _ws = _wb.active; _ws.append(["HEMIS ID", "F.I.Sh.", "Guruh"]); _ws.append(["1", "A B", "G"]); _ws.cell(row=3, column=5000, value="x")
_b = io.BytesIO(); _wb.save(_b)
ok(max(len(r_) for r_ in HM.read_rows(_b.getvalue(), "keng.xlsx")) <= HM.MAX_COLS, "Juda keng varaq — ustunlar soni cheklangan")
try: HA.HemisAdapter({"api_enabled": True}).fetch_students(); ad = False
except NotImplementedError: ad = True
ok(ad, "Adapter metodlari tasdiqlanmagan endpointlar uchun NotImplementedError beradi")

# =============================================================================================
print("== 2. HTTP: ruxsatlar")
REG, REGX, DIST, REK, KAF = (uid(r) for r in ("talabalar", "registrator_xodim", "masofaviy", "rektor", "kafedra"))
reg, regx, dist, rek, kaf = S(REG), S(REGX), S(DIST), S(REK), S(KAF)
a0 = last_audit()
ok(kaf.get(P + "/meta").status_code == 403 and kaf.get(P + "/summary").status_code == 403 and kaf.get(P + "/diffs").status_code == 403, "Kafedra mudiri — 403")
ok(q("SELECT 1 FROM audit_log WHERE id>? AND action LIKE 'hemis:%' AND allowed=0", (a0,)) != [], "Rad etilgan so'rov audit jurnalida")
sm = rek.get(P + "/summary")
ok(sm.status_code == 200 and "diffs_open" in sm.json() and rek.get(P + "/diffs").status_code == 403 and rek.post(P + "/import/students", content=b"x").status_code == 403,
   "Rektor: jamlangan sonlar bor; navbat va import — 403")
rq = rek.get(P + "/quality").json()
ok(all(i["sample"] == [] for i in rq["items"]), "Rektor: sifat tekshiruvlarida ism/ID yo'q (faqat son)")
ok(rek.get(P + "/meta").json()["caps"]["manage"] is False and dist.get(P + "/meta").json()["caps"]["settings"] is True, "Meta: rektor — boshqarmaydi; masofaviy boshlig'i — sozlamalar")

# =============================================================================================
print("== 3. HTTP: sintetik ma'lumot va dry-run")
fac, dep = q("SELECT faculty_id, id FROM departments ORDER BY id LIMIT 1")[0].values()
for nm in ("HMT-01", "HMT-02", "HMT-03"):
    w("DELETE FROM students WHERE group_id IN (SELECT id FROM groups_ WHERE name=?)", (nm,)); w("DELETE FROM groups_ WHERE name=?", (nm,))
w("DELETE FROM students WHERE hemis_id LIKE '99000000000%'")
G1 = w("INSERT INTO groups_(department_id,faculty_id,name,course,direction,level,form) VALUES(?,?,'HMT-01',2,'Test yo''nalishi','bakalavr','masofaviy')", (dep, fac))
G2 = w("INSERT INTO groups_(department_id,faculty_id,name,course,direction,level,form) VALUES(?,?,'HMT-02',2,'Test yo''nalishi','bakalavr','masofaviy')", (dep, fac))
def stu(hid, name, g, status="faol", pay="kontrakt", cit=None):
    return w("""INSERT INTO students(hemis_id,full_name,group_id,faculty_id,status,level,study_form,payment_type,citizenship)
                VALUES(?,?,?,?,?,'bakalavr','masofaviy',?,?)""", (hid, name, g, fac, status, pay, cit))
SA = stu("9900000000001", "Testov  Anvar Botir o‘g‘li", G1)         # o'zgarmagan (HEMIS'da kirillcha)
SB = stu("9900000000002", "Sinovov Bekzod", G1)                      # holat farqi
SC = stu("9900000000003", "Sinovova Charos", G1)                     # guruh farqi
SD = stu("9900000000004", "Namunov Davron", G1)                      # fuqarolik farqi
SE = stu("9900000000005", "Misolov Eldor", G1, pay=None)             # to'lov shakli bo'sh → to'ldiriladi
SZ = stu("9900000000009", "Yo'qolov Zafar", G1)                      # faylda yo'q → «topilmadi»
N0 = q("SELECT COUNT(*) n FROM students")[0]["n"]
F1 = xlsx([["HEMIS: Talabalar ro'yxati — sintetik test"], ["Eksport sanasi: 14.11.2026"],
           ["№", "Талаба ИД", "Ф.И.Ш.", "Гуруҳ", "Курс", "Таълим шакли", "Ҳолати", "Фуқаролиги", "Тўлов шакли", "ЖШШИР"],
           [1, 9900000000001, "Тестов Анвар Ботир ўғли", "HMT-01", "3-kurs", "Масофавий", "Ўқимоқда", "Ўзбекистон", "Контракт", "00000000000000"],
           [2, 9900000000002, "Sinovov Bekzod", "HMT-01", 3, "Masofaviy", "Akademik ta'til", "O'zbekiston", "Kontrakt", ""],
           [3, 9900000000003, "Sinovova Charos", "HMT-02", 2, "Masofaviy", "O'qimoqda", "O'zbekiston", "Kontrakt", ""],
           [4, 9900000000004, "Namunov Davron", "HMT-01", 3, "Masofaviy", "O'qimoqda", "Qozog'iston", "Kontrakt", ""],
           [5, 9900000000005, "Misolov Eldor", "HMT-01", 3, "Masofaviy", "O'qimoqda", "O'zbekiston", "Kontrakt", ""],
           [6, 9900000000006, "Yangiyev Farrux", "HMT-01", 3, "Masofaviy", "O'qimoqda", "O'zbekiston", "Grant", ""],
           [7, 9900000000007, "Notanish Guruhov", "XYZ-99", 1, "Masofaviy", "O'qimoqda", "O'zbekiston", "Grant", ""],
           [8, 9900000000002, "Takror Bekzod", "HMT-01", 3, "Masofaviy", "O'qimoqda", "O'zbekiston", "Grant", ""]])
r = regx.post(P + "/import/students", params={"name": "hemis_talabalar.xlsx"}, content=F1)
ok(r.status_code == 200, f"Registrator xodimi faylni yukladi ({r.status_code})")
pv = r.json(); IMP = pv.get("id")
c = pv.get("counts") or {}
print("   ", c)
ok(pv["header_row"] == 3 and pv["ignored"] == ["ЖШШИР"] and not pv["missing_fields"], "Kirill sarlavhalar 3-qatorda topildi; JShShIR o'qilmadi")
ok((c.get("new"), c.get("changed"), c.get("unchanged"), c.get("conflicting"), c.get("missing")) == (1, 1, 1, 5, 1),
   "Dry-run: yangi 1, o'zgargan 1, o'zgarmagan 1, ziddiyatli 5 (3 farq + noma'lum guruh + takror ID), topilmadi 1")
ok(c.get("spelling") == 1 and c.get("diffs") == 4, "Kirillcha ism — faqat yozuv farqi (navbatga tushmaydi); 4 farq (3 talaba + guruh kursi)")
whys = " | ".join(x["why"] for x in pv["samples"]["conflict"])
ok("XYZ-99" in whys and "takrorlangan" in whys and "Holat" in whys, "Ziddiyatli namunalar: noma'lum guruh, takror ID, holat farqi")
ok(q("SELECT COUNT(*) n FROM students")[0]["n"] == N0 and not q("SELECT 1 FROM students WHERE hemis_id='9900000000006'")
   and q("SELECT payment_type FROM students WHERE id=?", (SE,))[0]["payment_type"] is None, "Ko'rib chiqishda baza o'zgarmadi")
rr_ = q("SELECT raw_rows FROM hemis_imports WHERE id=?", (IMP,))[0]["raw_rows"]
ok("Sinovov Bekzod" in rr_ and "00000000000000" not in rr_, "Ko'rib chiqish nusxasida JShShIR qiymati yo'q (ustun tozalangan)")
r = regx.post(P + "/import/students", params={"name": "pii.csv"},
              content=csv_bytes([["HEMIS ID", "F.I.Sh.", "Guruh", "Telefon raqami", "Tug'ilgan sanasi", "Yashash manzili"],
                                 ["9900000000077", "Shaxsiy Sinov", "HMT-01", "+998 90 777 66 55", "2001-02-03", "Toshkent, Sinov ko'chasi 7"]]))
rr2 = q("SELECT raw_rows FROM hemis_imports WHERE id=?", (r.json()["id"],))[0]["raw_rows"]
ok(r.status_code == 200 and "Shaxsiy Sinov" in rr2 and not any(x_ in rr2 for x_ in ("777 66 55", "2001-02-03", "Sinov ko'chasi")) and len(r.json()["ignored"]) == 3,
   "Telefon / tug'ilgan sana / manzil ustunlari ko'rib chiqish nusxasiga ham yozilmadi")
regx.post(f"{P}/imports/{r.json()['id']}/cancel", json={})
ok(regx.post(P + "/import/students", params={"name": "katta.csv"}, content=b"a;b\n" * (HM.MAX_BYTES // 4 + 10)).status_code == 413, "25 MB dan katta yuklama — 413")
r = regx.post(f"{P}/imports/{IMP}/remap", json={"mapping": {"Курс": ""}, "save_profile": "Sintetik test profili"})
ok(r.status_code == 200 and r.json()["counts"]["diffs"] == 3 and "Курс" not in r.json()["map"], "Qo'lda moslash: «Kurs» e'tiborsiz — guruh kursi farqi yo'qoldi")
prof = [p_ for p_ in regx.get(P + "/meta").json()["profiles"] if p_["name"] == "Sintetik test profili"]
ok(len(prof) == 1, "Profil saqlandi")
regx.post(f"{P}/imports/{IMP}/remap", json={"mapping": {"Курс": "course"}})
ok(regx.get(f"{P}/imports/{IMP}").json()["counts"]["diffs"] == 4, "Xarita qaytarildi")

print("== 4. Qo'llash: snapshot, audit, hech narsa o'chirilmaydi")
a0 = last_audit()
r = regx.post(f"{P}/imports/{IMP}/apply")
ok(r.status_code == 200, f"Qo'llandi ({r.status_code} {r.text[:200]})")
ok(q("SELECT COUNT(*) n FROM students")[0]["n"] == N0 + 1 and q("SELECT 1 FROM students WHERE hemis_id='9900000000006' AND group_id=?", (G1,)),
   "Yangi talaba qo'shildi (guruh HMT-01)")
ok(q("SELECT payment_type FROM students WHERE id=?", (SE,))[0]["payment_type"] == "kontrakt", "Bo'sh to'lov shakli HEMIS qiymati bilan to'ldirildi")
ok(q("SELECT status FROM students WHERE id=?", (SB,))[0]["status"] == "faol" and q("SELECT group_id FROM students WHERE id=?", (SC,))[0]["group_id"] == G1,
   "Farqli maydonlar ustiga YOZILMADI (navbatga tushdi)")
ok(q("SELECT 1 FROM students WHERE id=?", (SZ,)) != [] and q("SELECT status FROM hemis_missing WHERE entity='students' AND ref='9900000000009'")[0]["status"] == "ochiq",
   "Faylda yo'q talaba o'chirilmadi — «HEMIS'da topilmadi» belgilandi")
DF = {(d["ref"], d["field"]): d for d in q("SELECT * FROM hemis_diffs WHERE status='ochiq' AND (ref LIKE '99000000000%' OR ref='HMT-01')")}
ok(set(DF) == {("9900000000002", "status"), ("9900000000003", "group"), ("9900000000004", "citizenship"), ("HMT-01", "course")},
   "Farqlar navbati: holat, guruh, fuqarolik, guruh kursi")
ok(DF[("9900000000004", "citizenship")]["core_value"] == "UZ" and DF[("9900000000004", "citizenship")]["hemis_value"] == "KZ"
   and DF[("9900000000002", "status")]["owner_user"] == q("SELECT head_user FROM org_units WHERE key='talabalar'")[0]["head_user"], "Qiymatlar normallashgan; egasi — Registrator ofisi boshlig'i")
sn = q("SELECT op, tbl, before, after FROM hemis_snapshots WHERE import_id=?", (IMP,))
ok(any(s["op"] == "insert" and s["tbl"] == "students" for s in sn) and any(s["op"] == "update" and json.loads(s["before"]).get("payment_type") is None for s in sn),
   "Snapshot: qo'shilgan yozuv va o'zgarishdan oldingi qiymat saqlandi")
ok(q("SELECT 1 FROM audit_log WHERE id>? AND action='hemis: import qo''llandi' AND allowed=1", (a0,)) != [], "Audit: import qo'llandi")
ok(regx.post(f"{P}/imports/{IMP}/apply").status_code == 409, "Qayta qo'llash — 409")
F2 = csv_bytes([["ИД студента", "ФИО", "Группа", "Статус", "Гражданство"],
                ["9900000000002", "Sinovov Bekzod", "HMT-01", "Обучается", "Гражданин РУз"],
                ["9900000000003", "Sinovova Charos", "HMT-02", "Обучается", "Гражданин РУз"],
                ["9900000000009", "Yo'qolov Zafar", "HMT-01", "Обучается", "Гражданин РУз"]], delim=",", enc="cp1251")
r = reg.post(P + "/import/students", params={"name": "hemis_ru.csv"}, content=F2)
ok(r.status_code == 200 and r.json()["counts"]["conflicting"] == 1, f"Ikkinchi fayl (rus sarlavhalar, cp1251, vergul): 1 ziddiyatli ({r.json().get('counts')})")
IMP2 = r.json()["id"]
ok(reg.post(f"{P}/imports/{IMP2}/apply").status_code == 200, "Ikkinchi import qo'llandi")
d2 = q("SELECT status, decision FROM hemis_diffs WHERE id=?", (DF[("9900000000002", "status")]["id"],))[0]
ok(d2 == {"status": "hal", "decision": "mos"}, "HEMIS'da tuzatilgan holat — farq «mos keldi» deb yopildi")
ok(len(q("SELECT 1 FROM hemis_diffs WHERE ref='9900000000003' AND field='group'")) == 1, "Takror importda farq ikkilanmaydi")
ok(q("SELECT status FROM hemis_missing WHERE ref='9900000000009' ORDER BY id DESC LIMIT 1")[0]["status"] == "qaytdi", "Faylda qayta paydo bo'lgan talaba — «qaytdi»")

print("== 5. Farqlar navbati: qarorlar")
d = reg.get(P + "/diffs", params={"q": "99000000000"}).json()
ok(d["total"] >= 2 and all(x["status"] == "ochiq" for x in d["items"]), f"Navbat: {d['total']} ta ochiq (filtr bo'yicha)")
DC, DD, DG = DF[("9900000000003", "group")]["id"], DF[("9900000000004", "citizenship")]["id"], DF[("HMT-01", "course")]["id"]
a0 = last_audit()
r = regx.post(f"{P}/diffs/{DC}/resolve", json={"decision": "hemis", "note": ""})
ok(r.status_code == 200 and q("SELECT group_id FROM students WHERE id=?", (SC,))[0]["group_id"] == G2, "«HEMIS to'g'ri» — talaba guruhi ISFT Core'da yangilandi")
ok(regx.post(f"{P}/diffs/{DC}/resolve", json={"decision": "hemis"}).status_code == 409, "Hal qilingan farq — qayta qaror 409")
ok(regx.post(f"{P}/diffs/{DD}/resolve", json={"decision": "core", "note": ""}).status_code == 400, "«ISFT Core to'g'ri» izohsiz — 400")
r = regx.post(f"{P}/diffs/{DD}/resolve", json={"decision": "core", "note": "Pasport nusxasi: O'zbekiston fuqarosi"})
ok(r.status_code == 200 and r.json()["export_pending"] == 1 and q("SELECT citizenship FROM students WHERE id=?", (SD,))[0]["citizenship"] is None,
   "«ISFT Core to'g'ri» — Core o'zgarmaydi, HEMIS'ga tuzatish eksportiga tushdi")
ok(regx.post(f"{P}/diffs/{DG}/resolve", json={"decision": "qolda", "value": "", "note": "x"}).status_code == 400, "«Qo'lda» qiymatsiz — 400")
r = regx.post(f"{P}/diffs/{DG}/resolve", json={"decision": "qolda", "value": "4", "note": "O'quv rejasi bo'yicha 4-kurs"})
ok(r.status_code == 200 and q("SELECT course FROM groups_ WHERE id=?", (G1,))[0]["course"] == 4 and r.json()["final_value"] == "4", "«Qo'lda» — qiymat ISFT Core'ga yozildi va eksportga")
lg = reg.get(f"{P}/diffs/{DD}").json()["log"]
ok([x["action"] for x in lg] == ["yaratildi", "ISFT Core to'g'ri"], "Hal qilish jurnali")
ok(len(q("SELECT 1 FROM audit_log WHERE id>? AND action='hemis: farq hal qilindi'", (a0,))) == 3, "Har bir qaror auditda")
mi = q("SELECT id FROM hemis_missing WHERE status='ochiq' LIMIT 1")
if mi:
    ok(reg.post(f"{P}/missing/{mi[0]['id']}/review", json={"note": ""}).status_code == 400
       and reg.post(f"{P}/missing/{mi[0]['id']}/review", json={"note": "Test: tekshirildi"}).json()["status"] == "tekshirildi", "«Topilmadi» — izoh bilan ko'rib chiqildi")

print("== 6. Boshqa turlar: guruhlar, xodimlar, yuklama, baholar (dry-run va qo'llash)")
GR = xlsx([["Группа", "Направление", "Курс", "Форма обучения", "Уровень"], ["HMT-03", "Test yo'nalishi", 1, "Дистанционная", "Бакалавриат"],
           ["HMT-02", "Test yo'nalishi", 2, "Очная", "Бакалавр"]])
r = reg.post(P + "/import/groups", params={"name": "guruhlar.xlsx"}, content=GR).json()
ok((r["counts"]["new"], r["counts"]["conflicting"]) == (1, 1), f"Guruhlar: 1 yangi, 1 farq (ta'lim shakli) ({r['counts']})")
ok(reg.post(f"{P}/imports/{r['id']}/apply").status_code == 200 and q("SELECT form FROM groups_ WHERE name='HMT-03'")[0]["form"] == "masofaviy", "Yangi guruh qo'shildi")
dname = q("SELECT name FROM departments WHERE id=?", (dep,))[0]["name"]
TF = csv_bytes([["Xodim HEMIS ID", "F.I.Sh.", "Kafedra", "Lavozim"], ["8800000000001", "Sinovchi Ustoz Aliyevich", dname, "Dotsent"]])
r = reg.post(P + "/import/teachers", params={"name": "xodimlar.csv"}, content=TF).json()
ok(r["counts"]["new"] == 1 and reg.post(f"{P}/imports/{r['id']}/apply").status_code == 200, "Xodimlar: yangi o'qituvchi qo'shildi")
LF = csv_bytes([["O'qituvchi", "Guruh", "Fan", "Soat"], ["Sinovchi Ustoz Aliyevich", "HMT-01", "Test fani", 60], ["Noma'lum Odam", "HMT-01", "Test fani", 30]])
r = reg.post(P + "/import/load", params={"name": "yuklama.csv"}, content=LF).json()
ok((r["counts"]["new"], r["counts"]["conflicting"], r["hours"]) == (1, 1, 60.0), f"Yuklama: 1 yangi bog'lanish, 1 ziddiyatli (noma'lum o'qituvchi), 60 soat ({r['counts']})")
reg.post(f"{P}/imports/{r['id']}/cancel")
ok(reg.post(f"{P}/imports/{r['id']}/apply").status_code == 409, "Bekor qilingan import qo'llanmaydi")
w("INSERT INTO grades(student_id,subject,score,semester,sem_no) VALUES(?,'Test fani',70,1,3)", (SA,))
BF = csv_bytes([["Talaba HEMIS ID", "Fan", "Semestr", "Ball"], ["9900000000001", "Test fani", "3-semestr", "75"], ["9900000000001", "Ikkinchi test fani", 3, "88"],
                ["9900000000001", "Uchinchi fan", 3, "120"]])
r = reg.post(P + "/import/grades", params={"name": "baholar.csv"}, content=BF).json()
ok((r["counts"]["new"], r["counts"]["conflicting"], r["counts"]["diffs"]) == (1, 2, 1), f"Baholar: 1 yangi, ball farqi navbatga, 120 ball — xato ({r['counts']})")
ok(reg.post(f"{P}/imports/{r['id']}/apply").status_code == 200, "Baholar qo'llandi")
gd = q("SELECT id FROM hemis_diffs WHERE entity='grades' AND status='ochiq' AND ref LIKE '9900000000001|%'")
ok(len(gd) == 1 and reg.post(f"{P}/diffs/{gd[0]['id']}/resolve", json={"decision": "hemis"}).status_code == 200
   and q("SELECT score FROM grades WHERE student_id=? AND subject='Test fani'", (SA,))[0]["score"] == 75, "Ball farqi: «HEMIS to'g'ri» — baho yangilandi")

print("== 7. Eksport: .xlsx tuzilmasi va SHA-256")
from openpyxl import load_workbook   # noqa: E402
r = regx.post(P + "/export/tuzatishlar", json={})
ok(r.status_code == 200 and r.json()["rows"] >= 2, f"Tuzatishlar eksporti ({r.status_code}): {r.json().get('rows')} qator")
ex = r.json()
f = regx.get(ex["url"])
ok(f.status_code == 200 and hashlib.sha256(f.content).hexdigest() == ex["sha256"] == f.headers.get("x-content-sha256")
   == q("SELECT sha256 FROM hemis_exports WHERE id=?", (ex["id"],))[0]["sha256"], "Fayl SHA-256 = jurnal = sarlavha")
wb = load_workbook(io.BytesIO(f.content))
hdr = [c_.value for c_ in wb["HEMIS"][1]]
ok(hdr == ["Tur", "HEMIS ID / kalit", "Nomi", "Maydon", "HEMIS'dagi qiymat", "To'g'ri qiymat", "Qaror", "Qaror sanasi", "Kim"], "Shablon ustunlari")
data = [list(r_) for r_ in wb["HEMIS"].iter_rows(values_only=True)]
meta = {k: v for k, v in wb["Ma'lumot"].iter_rows(values_only=True)}
ok(hashlib.sha256(json.dumps([[("" if v is None else v) for v in r_] for r_ in data], ensure_ascii=False, default=str).encode()).hexdigest()
   == meta["Mazmun SHA-256 (sarlavha + qatorlar, JSON)"] == ex["content_sha256"], "Mazmun SHA-256 («Ma'lumot» varag'i) qayta hisoblandi")
ok(any(r_[1] == "9900000000004" and r_[5] == "UZ" for r_ in data[1:]), "Tuzatishda: fuqarolik — to'g'ri qiymat UZ")
ok(q("SELECT COUNT(*) n FROM hemis_diffs WHERE export_pending=1")[0]["n"] == 0 and regx.post(P + "/export/tuzatishlar", json={}).status_code == 409,
   "Eksport qilinganlar navbatdan chiqdi; yangi tuzatish yo'q — 409")
reg.post(P + "/templates", json={"kind": "davomat", "headers": {"status": "Davomat holati"}})
r = dist.post(P + "/export/davomat", json={"weeks": 2})
ok(r.status_code == 200 and r.json()["rows"] > 0 and "TASDIQLANMAGAN" in r.json()["rule"], f"Davomat (masofaviy, LRS): {r.json().get('rows')} qator, qoida TASDIQLANMAGAN")
wb = load_workbook(io.BytesIO(dist.get(r.json()["url"]).content))
ok("Davomat holati" in [c_.value for c_ in wb["HEMIS"][1]] and "TASDIQLANMAGAN" in str(dict(wb["Ma'lumot"].iter_rows(values_only=True))["Diqqat"]),
   "Shablon ustun nomi sozlandi; «Diqqat» qatorida tasdiqlanmagan qoida")
r = regx.post(P + "/export/yuzma", json={})
ok(r.status_code == 200 and r.json()["rows"] > 0, f"Yuzma-yuz qaydnoma natijalari: {r.json().get('rows')} qator")
r = regx.post(P + "/export/baholar", json={})
ok(r.status_code in (200, 409), f"LRS oraliq ballar eksporti ({r.status_code}, {r.json().get('rows')})")
ok(regx.post(P + "/export/yoq", json={}).status_code == 404 and rek.post(P + "/export/yuzma", json={}).status_code == 403, "Noma'lum tur — 404; rektor eksport qilmaydi — 403")
ok(len(q("SELECT 1 FROM audit_log WHERE action='hemis: eksport tayyorlandi'")) >= 3, "Eksportlar auditda")

print("== 8. API ulagichi va sozlamalar")
st = reg.get(P + "/settings").json()
ok(st["api_enabled"] is False and st["verified"] is False and "TASDIQLANMAGAN" in st["label"], "Standart: o'chirilgan, TASDIQLANMAGAN")
pr = reg.post(P + "/api/probe").json()
ok(pr["sent"] is False and pr["result"] == "o'chirilgan", "Probe (o'chirilgan) — so'rov yuborilmadi")
ok(regx.post(P + "/settings", json={"values": {"api_enabled": True}}).status_code == 403 and regx.post(P + "/api/token", json={"token": "x"}).status_code == 403,
   "Registrator xodimi sozlama va tokenni o'zgartira olmaydi")
TOK = "tst-" + hashlib.sha1(os.urandom(8)).hexdigest()
ok(reg.post(P + "/api/token", json={"token": TOK}).json()["token_set"] is True, "Token maxfiy omborga saqlandi")
ok(not q("SELECT 1 FROM hemis_settings WHERE v LIKE ?", (f"%{TOK[4:]}%",)) and not q("SELECT 1 FROM audit_log WHERE detail LIKE ?", (f"%{TOK[4:]}%",))
   and TOK not in DBP.read_bytes().decode("latin-1"), "Token bazada yo'q (sozlamalar, audit, butun fayl)")
ok(reg.post(P + "/settings", json={"values": {"api_base_url": "https://u:p@hemis.example.uz"}}).status_code == 400, "Manzilda login/parol — 400")
ok(reg.post(P + "/settings", json={"values": {"api_base_url": B}}).status_code == 400 and reg.post(P + "/settings", json={"values": {"api_base_url": "http://169.254.169.254"}}).status_code == 400,
   "SSRF: ichki manzil (localhost, metadata) sozlamada — 400")
ok(reg.post(P + "/settings", json={"values": {"api_base_url": "https://hemis.example.uz", "api_probe_path": "healthz", "api_enabled": True}}).status_code == 200, "Ulagich yoqildi")
w("UPDATE hemis_settings SET v=? WHERE k='api_base_url'", (json.dumps(B),))     # eski (tekshiruvdan oldingi) yozuv — probe baribir yubormaydi
pr = reg.post(P + "/api/probe").json()
ok(pr["sent"] is False and pr["result"] == "ichki_manzil", f"Probe: bazadagi ichki manzilga so'rov yuborilmadi ({pr.get('result')})")
os.environ["ISFT_CORE_HEMIS_ALLOW_PRIVATE"] = "1"       # faqat test jarayonida: GET mantig'ini mahalliy server bilan tekshirish
try: pr = HA.probe({"api_enabled": True, "api_base_url": B, "api_probe_path": "/healthz"})
finally: os.environ.pop("ISFT_CORE_HEMIS_ALLOW_PRIVATE", None)
ok(pr["sent"] and pr["status"] == 200 and pr["auth"] is False and "TASDIQLAMAYDI" in pr["message"], f"Probe: bitta GET → {pr.get('status')} ({pr.get('result')}); token yuborilmadi")
reg.post(P + "/settings", json={"values": {"api_enabled": False, "api_base_url": "", "api_probe_path": ""}})
reg.post(P + "/api/token", json={"token": None})
ok(reg.get(P + "/settings").json()["token_set"] is False, "Token o'chirildi, ulagich qayta o'chirildi")

print("== 9. Ma'lumot sifati")
w("UPDATE groups_ SET form='kunduzgi' WHERE id=?", (G2,))
w("INSERT INTO students(hemis_id,full_name,group_id,faculty_id,status,level,study_form) VALUES('9900000000008','Dublikat Test',?,?,'faol','bakalavr','masofaviy')", (G1, fac))
w("INSERT INTO students(hemis_id,full_name,group_id,faculty_id,status,level,study_form) VALUES('9900000000008','Dublikat Ikki',?,?,'faol','bakalavr','masofaviy')", (G1, fac))
w("INSERT INTO students(hemis_id,full_name,group_id,faculty_id,status,level,study_form) VALUES('','HEMIS IDsiz Test',?,?,'faol','bakalavr','masofaviy')", (G1, fac))
Q = {i["key"]: i for i in reg.get(P + "/quality").json()["items"]}
ok(Q["dup_hemis"]["n"] >= 1 and any("9900000000008" in s for s in Q["dup_hemis"]["sample"]), "Takroriy HEMIS ID topildi")
ok(Q["no_hemis"]["n"] >= 1 and Q["dist_form"]["n"] >= 1 and any("HMT-02" in s for s in Q["dist_form"]["sample"]), "HEMIS IDsiz talaba; masofaviy talaba kunduzgi guruhda")
sm = rek.get(P + "/summary").json()
ok(any(x["key"] == "dup_hemis" and x["n"] >= 1 for x in sm["quality"]), "Rektor jamlanmasida sifat soni")

# =============================================================================================
print("== 10. Jarayon ichida (bazaning nusxasi): tranzaksiya qaytishi, Nazorat detektori")
tmp = Path(tempfile.mkdtemp(prefix="hemis-test-"))
src = sqlite3.connect(DBP, timeout=30); dst = sqlite3.connect(tmp / "jarvis.db"); src.backup(dst); src.close(); dst.close()
os.environ.update(ISFT_CORE_DATA_DIR=str(tmp), ISFT_CORE_DB=str(tmp / "jarvis.db"), ISFT_CORE_FILES_DIR=str(tmp / "portal_files"),
                  ISFT_CORE_STAFFABS_DIR=str(tmp / "staffabs_files"), ISFT_CORE_SECRETS_DIR=str(tmp / "secrets"))
os.environ.pop("ANTHROPIC_API_KEY", None); os.environ.pop("TELEGRAM_BOT_TOKEN", None)
for m_ in [k for k in sys.modules if k == "app" or k.startswith("app.")]: del sys.modules[m_]
_had_pub, _had_tp = "ISFT_CORE_PUBLIC_URL" in os.environ, "ISFT_CORE_TUTOR_PROVIDER" in os.environ
os.environ.update(JARVIS_DB=str(tmp / "BOSHQA.db"), JARVIS_DATA_DIR=str(tmp / "boshqa"), JARVIS_PUBLIC_URL="https://eski.example.uz", JARVIS_TUTOR_PROVIDER="claude")
try:
    with contextlib.redirect_stdout(io.StringIO()):
        from app import main as MAIN   # noqa: E402
    from app import db as _DB   # noqa: E402
    ok(_DB.DB_PATH == tmp / "jarvis.db" and os.environ["ISFT_CORE_DB"] == str(tmp / "jarvis.db") and not (tmp / "BOSHQA.db").exists()
       and (_had_pub or os.environ.get("ISFT_CORE_PUBLIC_URL") == "https://eski.example.uz") and (_had_tp or "ISFT_CORE_TUTOR_PROVIDER" not in os.environ),
       "Eski JARVIS_* nomlari: faqat avval mavjud bo'lganlari (PUBLIC_URL) ko'chiriladi; JARVIS_DB / JARVIS_TUTOR_PROVIDER va h.k. — yo'q")
finally:
    for k_ in ("JARVIS_DB", "JARVIS_DATA_DIR", "JARVIS_PUBLIC_URL", "JARVIS_TUTOR_PROVIDER"): os.environ.pop(k_, None)
    if not _had_tp: os.environ.pop("ISFT_CORE_TUTOR_PROVIDER", None)
    if not _had_pub: os.environ.pop("ISFT_CORE_PUBLIC_URL", None)
from app import hemis as H, nazorat as NZ, rbac as RB   # noqa: E402
_xb, _ = H.build_xlsx("tuzatishlar", [("a", "Nomi"), ("b", "Qiymat")], [{"a": '=HYPERLINK("http://evil.example","x")', "b": "+998901234567"}, {"a": "@SUM(1)", "b": "-1+2"}],
                        [("Kim", "=cmd|' /C calc'!A0")], dt.datetime(2026, 11, 15, 10, 0))
from openpyxl import load_workbook as _lw   # noqa: E402
_w2 = _lw(io.BytesIO(_xb))
_cells = [c_ for r_ in _w2["HEMIS"].iter_rows(min_row=2) for c_ in r_] + [c_ for r_ in _w2["Ma'lumot"].iter_rows() for c_ in r_]
ok(all(c_.data_type == "s" for c_ in _cells) and _w2["HEMIS"]["A2"].value.startswith("=HYPERLINK") and _w2["HEMIS"]["A2"].quotePrefix,
   "Eksport .xlsx: «=», «+», «-», «@» bilan boshlangan qiymatlar formula emas — matn (qiymat o'zgarmaydi)")
con = MAIN.con
u = dict(con.execute("SELECT * FROM users WHERE id=?", (REG,)).fetchone())
CX = RB.Ctx(user=u, role=RB.ROLES["talabalar"])
F3 = csv_bytes([["HEMIS ID", "F.I.Sh.", "Guruh", "Holat"], ["9900000000071", "Qaytish Testov", "HMT-01", "O'qimoqda"],
                ["9900000000001", "Testov Anvar Botir o'g'li", "HMT-01", "Chetlashtirilgan"]])
pv = H.create_preview(CX, "students", F3, "qaytish.csv", None, "toliq")
n_st, n_sn, n_df = (con.execute(s_).fetchone()[0] for s_ in ("SELECT COUNT(*) FROM students", "SELECT COUNT(*) FROM hemis_snapshots", "SELECT COUNT(*) FROM hemis_diffs"))
orig = H._apply_missing
def boom(*a, **k): raise RuntimeError("sun'iy xato (test)")
H._apply_missing = boom
try: H.apply_import(CX, pv["id"]); raised = False
except Exception as e: raised = "hech narsa o'zgarmadi" in str(getattr(e, "detail", e))
H._apply_missing = orig
ok(raised and (con.execute("SELECT COUNT(*) FROM students").fetchone()[0], con.execute("SELECT COUNT(*) FROM hemis_snapshots").fetchone()[0],
               con.execute("SELECT COUNT(*) FROM hemis_diffs").fetchone()[0]) == (n_st, n_sn, n_df)
   and not con.execute("SELECT 1 FROM students WHERE hemis_id='9900000000071'").fetchone(), "Qo'llash o'rtasida xato — hammasi qaytarildi (talaba, snapshot, farq yo'q)")
imp = dict(con.execute("SELECT status, error FROM hemis_imports WHERE id=?", (pv["id"],)).fetchone())
ok(imp["status"] == "preview" and "sun'iy xato" in imp["error"], "Import holati «preview» qoldi, xato matni saqlandi")
res = H.apply_import(CX, pv["id"])
ok(res["counts"]["missing"] > 100 and con.execute("SELECT COUNT(*) FROM students").fetchone()[0] == n_st + 1, f"Qayta urinish o'tdi; «to'liq» ko'lam: {res['counts']['missing']} ta topilmadi — hech biri o'chirilmadi")
NOW = clock_now = dt.datetime.now().replace(microsecond=0)
keys = lambda: {x["key"] for x in NZ.scan(con, NOW, write=False)}
con.execute("UPDATE hemis_diffs SET created_at=? WHERE status='ochiq'", ((NOW - dt.timedelta(days=2)).isoformat(),)); con.commit()
ok("hemis:farq" not in keys(), "Nazorat: 2 kunlik farq — istisno emas (chegara 7 kun)")
con.execute("UPDATE hemis_diffs SET created_at=? WHERE status='ochiq'", ((NOW - dt.timedelta(days=10)).isoformat(),)); con.commit()
k = keys()
ok("hemis:farq" in k and "hemis:sifat" in k, "Nazorat: 10 kunlik ochiq farqlar — «hemis:farq»; sifat — «hemis:sifat»")
it = {x["key"]: x for x in NZ.scan(con, NOW, write=False)}
ok(not re.search(r"\d{13}", json.dumps(it["hemis:farq"], ensure_ascii=False, default=str)) and it["hemis:farq"]["owner"] == q("SELECT head_user FROM org_units WHERE key='talabalar'")[0]["head_user"],
   "Nazorat elementi: HEMIS ID yo'q (jamlangan), egasi — Registrator ofisi")
con.execute("INSERT OR REPLACE INTO nz_rules(k,v) VALUES('hemis_diff_days',30)"); con.commit()
ok("hemis:farq" not in keys(), "Rektor chegarani 30 kunga o'zgartirsa — istisno yo'qoladi")
shutil.rmtree(tmp, ignore_errors=True)

# =============================================================================================
print("== 11. Brauzer")
node = shutil.which("node")
if node:
    ok(subprocess.run([node, "--check", str(ROOT / "static" / "hemis.js")], capture_output=True).returncode == 0, "node --check: hemis.js")
if node and os.getenv("PW") and os.getenv("CHROME"):
    fx = Path(tempfile.mkdtemp(prefix="hemis-fx-")) / "hemis_talabalar.xlsx"
    fx.write_bytes(F1)
    env = dict(os.environ, ISFT_TEST_URL=B, HM_UID=str(REG), HM_PW=PW, HM_FILE=str(fx),
               HM_OUT=os.getenv("HM_OUT") or str(Path(os.getenv("ISFT_CORE_DATA_DIR", "/tmp")) / "hemis_shots"))
    rr = subprocess.run([node, str(ROOT / "tools" / "hemis_check.js")], cwd=ROOT, env=env, capture_output=True, text=True, timeout=300)
    print(rr.stdout[-2500:], rr.stderr[-800:])
    ok(rr.returncode == 0, "Brauzer: import ko'rib chiqish va Farqlar navbati (keng va telefon)")
else:
    print("  · brauzer tekshiruvi o'tkazildi (PW/CHROME berilmagan)")

# tozalash: sintetik yozuvlar (keyingi to'plamlarga ta'sir qilmasin)
w("DELETE FROM grades WHERE student_id IN (SELECT id FROM students WHERE hemis_id LIKE '99000000000%' OR group_id IN (SELECT id FROM groups_ WHERE name LIKE 'HMT-0%'))")
w("DELETE FROM students WHERE hemis_id LIKE '99000000000%' OR group_id IN (SELECT id FROM groups_ WHERE name LIKE 'HMT-0%')")
w("DELETE FROM teacher_groups WHERE group_id IN (SELECT id FROM groups_ WHERE name LIKE 'HMT-0%')")
w("DELETE FROM groups_ WHERE name LIKE 'HMT-0%'"); w("DELETE FROM teachers WHERE hemis_id='8800000000001'")
for t_ in ("hemis_diffs", "hemis_diff_log", "hemis_missing", "hemis_snapshots"): w(f"DELETE FROM {t_}")
print(f"\n{'XATO: ' + str(len(fails)) if fails else 'Hammasi o‘tdi'}")
sys.exit(1 if fails else 0)
