import os
import httpx, sqlite3, sys, asyncio
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
B = os.environ.get("ISFT_TEST_URL", "http://127.0.0.1:8000"); DB=sqlite3.connect(str(Path(os.environ.get("ISFT_CORE_DB") or ROOT / "data" / "jarvis.db")))
fails=[]
def ok(cond, msg):
    print(("  ✓ " if cond else "  ✗ ")+msg)
    if not cond: fails.append(msg)
def login(uid):
    c=httpx.Client(base_url=B, timeout=60); assert c.post("/api/login",json={"user_id":uid,"password": "Isft2026"}).status_code==200; return c
# faol akkauntlar (faolsizlantirilganlar — masalan, sobiq dekan #13 — kira olmaydi, pastda alohida tekshiriladi)
users=DB.execute("select id,role from users where coalesce(active,1)!=0").fetchall()
print("== 16 rol × barcha GET endpointlar")
eps=["/api/me","/api/dashboard","/api/section/tasks","/api/docs/catalog","/api/docs/registry","/api/svc/overview","/api/spaces/overview","/api/rbac"]
err=0
for uid,role in users:
    c=login(uid)
    for e in eps:
        r=c.get(e)
        if r.status_code>=500 or r.status_code not in (200,403): err+=1; print("   ",role,e,r.status_code,r.text[:120])
    for sec in ["academic","risk","contracts","finance","payroll","hr","science","international","admissions","youth","masters","audit","mygroups"]:
        r=c.get("/api/section/"+sec)
        if r.status_code not in (200,403): err+=1; print("   ",role,sec,r.status_code)
ok(err==0, f"{len(users)} rol, xatolar: {err}")
# institutda dekan lavozimi yo'q (Yevropa modeli): fakultet darajasidagi vazifalar Registrator ofisida (#17), fakultet ko'lami — tyutorda (#24)
rk,reg,ty,oq,xo,kg=login(2),login(17),login(24),login(15),login(16),login(1)
print("== Backend tuzatishlari")
ok(httpx.post(B+"/api/login",json={"user_id":13,"password":"Isft2026"}).status_code==403, "sobiq dekan (#13) kira olmaydi")
ok(all(u["id"]!=13 for u in httpx.get(B+"/api/users").json()), "sobiq dekan kirish ro'yxatida yo'q")
ok(xo.get("/api/docs/lookup/student?q=").status_code==403, "xo'jalik talaba qidira olmaydi (lookup RBAC)")
ok(kg.get("/api/docs/lookup/student?q=").status_code==403, "kengash talaba qidira olmaydi")
ok(oq.get("/api/docs/lookup/task").status_code==403, "o'qituvchi rektorat topshiriqlarini ko'rmaydi")
ok(reg.get("/api/docs/lookup/student?q=").status_code==200, "Registrator ofisi talabalarni qidira oladi")
ok(ty.post("/api/svc/incidents/2/notify",json={"text":"x"*30}).status_code==403, "tyutor umumiy hodisa xabarini yubora olmaydi")
ok("requests" not in ty.get("/api/svc/overview").json(), "tyutorda murojaatlar (umumiy xabar) yorlig'i yo'q")
# eski bir bosishli holat API (main.py) — bo'limli (yagona oqimdagi) topshiriqni o'zgartirmaydi: 403 (avval whitelist 400 edi)
ok(rk.post("/api/tasks/1/status",json={"status":"<script>"}).status_code in (400,403), "topshiriq holati: eski API orqali o'zgartirib bo'lmaydi")
r=rk.post("/api/meetings",json={"title":"Test","transcript":"t","tasks":[{"assignee":"Moliya fakulteti dekani","text":"x","due":"15.11"},{"assignee":"Moliya-iqtisod ishlari prorektori","text":"y","due":"2026-11-31"}]})
ok(r.status_code==200, "buzuq sanali majlis saqlandi (400/500 emas)")
row=DB.execute("select assignee_role,due from tasks order by id desc limit 2").fetchall()
ok(row[1][0]=="talabalar" and row[0][0]=="prorektor_moliya", f"rol aniqlash ('dekani' → Registrator ofisi): {row}")
ok(rk.get("/api/dashboard").status_code==200 and rk.get("/api/section/tasks").status_code==200, "panel buzuq sanadan keyin ham ishlaydi")
from app import ai
SAMPLE="""Rektorat yig'ilishi, 2026-yil 6-noyabr.
Rektor: Moliya fakulteti 2-kurslaridagi vaziyat jiddiy. Registrator ofisi: pasaygan guruhlar bo'yicha har bir talaba bilan individual reja tuzsin, muddat 17.11.
O'quv ishlari prorektori: qo'shimcha konsultatsiya jadvalini tasdiqlash, muddat 12.11.
Buxgalteriya: kommunal xarajatlar bo'yicha "Toshkent issiqlik" bilan solishtirma dalolatnoma olish, muddat 14.11.
Xalqaro aloqalar bo'limi: Riga Technical University bilan shartnomani uzaytirish xatini yuborish, muddat 10.11.
Yoshlar ishlari prorektori: 2-bino isitish masalasini bir hafta ichida yopish va hisobot berish."""
async def fb():
    orig=ai.llm_available
    async def no(): return False
    ai.llm_available=no
    try: return await ai.extract_tasks(SAMPLE)
    finally: ai.llm_available=orig
t=asyncio.run(fb())
ok(len(t)==5 and t[0]["assignee"].startswith("Registrator"), f"AI o'chiq: {len(t)} ta topshiriq, 1-mas'ul: {t[0]['assignee'] if t else '-'}")
ok(ai._parse_date("31.02") is None, "mavjud bo'lmagan sana rad etiladi")
evs=rk.get("/api/svc/overview").json()["events"]["events"]
ok(any(e["date"]>"2026-11-06" for e in evs), "kelgusi tadbirlar ro'yxatda (LEFT JOIN)")
print("== Auditoriyalar")
o=rk.get("/api/spaces/overview").json()
# demo: bir nechta kamera ataylab oflayn (kameralar moduli hikoyasi) — ko'pchiligi onlayn bo'lishi kerak
ok(o["kpi"]["rooms"]>=36 and o["kpi"]["online"]>=0.9*o["kpi"]["rooms"], f"kameralarning ko'pchiligi onlayn: {o['kpi']['online']}/{o['kpi']['rooms']}")
ok(len(o["heatmap"])==6 and len(o["heatmap"][0])==6, "issiqlik xaritasi 6×6")
ok(any(g["repeat"]>=3 for g in o["ghosts"]), "takror bo'sh dars signali bor")
ok(o["ghosts"][0].get("teacher") is not None, "rektor o'qituvchi ismini ko'radi")
xo_o=xo.get("/api/spaces/overview").json()
ok(all(g.get("teacher") is None for g in xo_o["ghosts"]), "xo'jalik o'qituvchi ismini ko'rmaydi")
ok(oq.get("/api/spaces/overview").status_code==403, "o'qituvchiga yopiq")
rd=rk.get(f"/api/spaces/room/{o['live'][0]['id']}").json(); ok("points" in rd, "xona kunlik grafigi")
ok(rk.get(f"/api/spaces/room/1?day=bad").status_code==400, "noto'g'ri sana → 400")
ok(reg.post("/api/spaces/cameras",json={"room_id":1,"mode":"isapi","host":"1.2.3.4"}).status_code==403, "Registrator ofisi kamera sozlay olmaydi")
ok(xo.post("/api/spaces/cameras",json={"room_id":1,"mode":"isapi","host":"x; rm -rf"}).status_code==422, "IP maydonida injeksiya rad etiladi")
r=xo.post("/api/spaces/cameras",json={"room_id":1,"mode":"isapi","host":"10.255.255.1","username":"jarvis","password":"secret"})
cid=DB.execute("select id from cameras where room_id=1").fetchone()[0]
t=xo.post(f"/api/spaces/cameras/{cid}/test").json(); ok(t["ok"] is False and "Ulanib" in t["error"], f"yetib bo'lmaydigan kamera → aniq xato: {t.get('error','')[:60]}")
ok("secret" not in xo.get("/api/spaces/overview").text, "parol API javobida yo'q")
xo.post("/api/spaces/cameras",json={"room_id":1,"mode":"sim"})
# tozalash: test yaratgan «Test» majlisi (matn "t") va uning "x"/"y" topshiriqlari bazada qolmasin (decisions.cleanup_junk bilan bir xil)
for (mid,) in DB.execute("select id from meetings where title='Test' and transcript='t'").fetchall():
    ids=[r[0] for r in DB.execute("select id from tasks where meeting_id=?",(mid,))]
    q=",".join(map(str,ids)) or "0"
    DB.execute(f"delete from task_log where task_id in ({q})"); DB.execute(f"delete from task_msgs where task_id in ({q})")
    DB.execute(f"delete from tasks where id in ({q})"); DB.execute("delete from meetings where id=?",(mid,))
DB.commit()
print("\nNATIJA:", "HAMMASI O'TDI" if not fails else f"{len(fails)} ta xato: {fails}")
sys.exit(1 if fails else 0)
