"""ISFT Core AI qatlami. Til modeli mahalliy (Ollama) ishlaydi — ma'lumot serverdan chiqmaydi.
Muhim tamoyil: model bazaga to'g'ridan-to'g'ri kirmaydi. U faqat RBAC dan o'tgan servis natijalarini ko'radi.

Til modeli ulanmagan bo'lsa (masalan, Railway'da Ollama yo'q) — «Tahlil rejimi»: raqamlar va xulosalar qoidalar bilan
hisoblanadi (source="qoida"), matn yaratuvchi vositalar (tarjima, javob loyihasi) o'chiriladi va {"ai": false, "reason": ...} qaytadi.
Har bir AI natijasida "source": "ai" | "qoida" bor.

Til modeli manzili (faqat institut nazoratidagi server — shaxsiy ma'lumot O'zbekistondan tashqariga chiqmasligi shart):
  ISFT_CORE_LLM_URL   — masalan http://10.0.0.5:11434 (Ollama) yoki http://10.0.0.5:8000/v1 (OpenAI-mos: vLLM, llama.cpp, Ollama /v1)
  ISFT_CORE_LLM_API   — ollama | openai (bo'sh bo'lsa: manzil /v1 bilan tugasa openai, aks holda ollama)
  ISFT_CORE_LLM_KEY   — ixtiyoriy Bearer kalit (institut serveri himoyalangan bo'lsa)
  ISFT_CORE_LLM=0     — til modelini butunlay o'chirish (doim «Tahlil rejimi»)
  OLLAMA_URL          — eski nom; ISFT_CORE_LLM_URL bo'lmasa ishlatiladi. Standart: http://localhost:11434
Hech qanday bulut AI provayderi standart holatda ulanmagan."""
import json, os, re, time, datetime as dt
import httpx
from . import clock
from . import services as S, db
from .rbac import AccessDenied, Ctx, audit

LLM_URL = (os.getenv("ISFT_CORE_LLM_URL") or os.getenv("OLLAMA_URL") or "http://localhost:11434").rstrip("/")
LLM_API = (os.getenv("ISFT_CORE_LLM_API") or ("openai" if LLM_URL.endswith("/v1") else "ollama")).strip().lower()
LLM_KEY = os.getenv("ISFT_CORE_LLM_KEY", "")
LLM_ON = os.getenv("ISFT_CORE_LLM", "1").strip().lower() not in ("0", "false", "no", "off")
OLLAMA = LLM_URL      # eski nom (moslik uchun)
MODEL = os.getenv("ISFT_CORE_MODEL", "qwen3:8b")

def _headers():
    return {"Authorization": f"Bearer {LLM_KEY}"} if LLM_KEY else {}

TOOLS = {
    "academic": (S.academic_overview, "o'zlashtirish, o'rtacha ball, davomat, pasaygan guruhlar"),
    "risk": (S.at_risk_students, "o'qishda xavf ostidagi talabalar (o'zlashtirish yoki davomat)"),
    "contracts": (S.contracts_summary, "kontrakt to'lovlari va qarzdorlik"),
    "finance": (S.finance_summary, "byudjet rejasi va haqiqiy xarajatlar"),
    "payroll": (S.payroll_summary, "ish haqi fondi"),
    "hr": (S.hr_list, "xodimlar (kadrlar) ro'yxati"),
    "science": (S.science_summary, "ilmiy maqolalar, Scopus, grantlar, ilmiy daraja"),
    "international": (S.international_summary, "xalqaro hamkorlar va shartnomalar"),
    "admissions": (S.admissions_summary, "qabul, abituriyentlar"),
    "youth": (S.youth_summary, "tadbirlar, anonim murojaatlar, hamkor turar joylar bandligi"),
    "masters": (S.masters_summary, "magistratura, dissertatsiyalar"),
    "tasks": (S.tasks_list, "majlis topshiriqlari va ularning muddati"),
    "cameras": (lambda con, ctx, quiet=False: __import__("app.camsec", fromlist=["agent_tool"]).agent_tool(con, ctx, quiet),
                "kameralar: bo'sh turgan xonalar, xavfsizlik voqealari, navbat, kamera holati (faqat metama'lumot)"),
    # faqat sonlar (rbac.HR_STATS): rektor ham so'ray oladi; ism-sharif va shaxsiy ishlar — yo'q (app/staff_absence.py agent_tool)
    "staffabs": (lambda con, ctx, quiet=False: __import__("app.staff_absence", fromlist=["agent_tool"]).agent_tool(con, ctx, quiet),
                 "xodimlar yo'qligi: bugun nechta xodim ta'tilda, kasallik varaqasida, xizmat safarida (faqat sonlar)"),
    "facecam": (lambda con, ctx, quiet=False: __import__("app.facecam", fromlist=["agent_tool"]).agent_tool(con, ctx, quiet),
                "kirish nazorati (Face ID): bugun kim kirdi, kechikkan o'qituvchilar, notanish shaxslar (faqat rozilik bergan shaxslar)"),
}
KEYWORDS = {
    "academic": ["o'zlashtir", "baho", "ball", "gpa", "davomat", "akademik", "pasay", "o'quv", "kurs", "guruh"],
    "risk": ["xavf", "chetlash", "risk", "qiynal", "yiqil", "qolib ket"],
    "contracts": ["kontrakt", "to'lov", "qarz", "tushum"],
    "finance": ["byudjet", "xarajat", "moliya", "kommunal", "pul", "sarf"],
    "payroll": ["maosh", "ish haqi", "oylik", "ish haq"],
    "hr": ["xodim", "kadr", "pasport", "shtat"],
    "staffabs": ["xodim ta'til", "xodimlar ta'til", "xodim ta'tilda", "ta'tilda", "mehnat ta'til", "kasallik varaq", "xizmat safar", "komandirovka",
                 "ishda yo'q", "ishga chiqma", "nechta xodim", "xodimlar soni", "necha xodim"],
    "science": ["ilmiy", "maqola", "scopus", "nashr", "grant", "h-index", "salohiyat", "web of science", "phd", "daraja"],
    "international": ["xalqaro", "hamkor", "xorij", "erasmus", "almashinuv", "shartnoma"],
    "admissions": ["qabul", "abituriyent", "ariza"],
    "youth": ["yotoqxona", "tadbir", "murojaat", "yoshlar", "ma'naviy", "isitish"],
    "masters": ["magistr", "dissertatsiya", "ilmiy rahbar"],
    "tasks": ["topshiriq", "majlis", "kengash", "muddat", "vazifa", "bajaril"],
    "cameras": ["kamera", "xavfsizlik voqea", "xavfsizlik hodisa", "bo'sh turdi", "bo'sh turgan", "bo'sh qolgan", "xonalar bo'sh", "bo'sh xona",
                "oshxona", "serverxona", "navbat uzun", "navbatda", "navbat qancha", "oflayn", "tungi kirish", "noto'g'ri signal"],
    "facecam": ["face id", "kirish nazorat", "yuzni tanish", "o'qituvchilar kechik", "o'qituvchi kechik", "kechikkan o'qituvchi", "darsga kechik",
                "xodimlar kechik", "kechikkan xodim", "talaba kirdi", "talabalar kirdi", "o'qituvchi kirdi", "xodim kirdi", "binoga kir",
                "institutga kir", "kim kirdi", "notanish shaxs"],
}
STRATEGIC = ["ortda", "muammo", "umumiy holat", "nima qilish", "tavsiya", "xulosa", "qanday holat", "e'tibor", "strateg", "brifing", "bugun"]

def norm(t: str) -> str:
    return re.sub(r"[ʻʼ‘’`´]", "'", t.lower())

def route(q: str) -> list[str]:
    q = norm(q)
    hit = [k for k, ws in KEYWORDS.items() if any(w in q for w in ws)]
    if "cameras" in hit and "risk" in hit and not any(w in q.replace("xavfsizlik", "") for w in KEYWORDS["risk"]):
        hit.remove("risk")      # "xavfsizlik voqeasi" — kamera mavzusi, "o'qishda xavf" emas
    if "risk" in hit and "academic" in hit: hit.remove("academic")
    if "staffabs" in hit and "hr" in hit and not any(w in q for w in ("pasport", "ro'yxat", "royxat", "shaxsiy ish")):
        hit.remove("hr")        # «nechta xodim ta'tilda» — jamlangan son; shaxsiy ma'lumot (kadrlar bazasi) so'ralmagan
    if "staffabs" in hit and "talaba" in q and "xodim" not in q: hit.remove("staffabs")   # talabaning akademik ta'tili — boshqa mavzu
    return hit

def strategic(q: str) -> bool:
    q = norm(q); return any(w in q for w in STRATEGIC)

def _oa_body(messages, max_tokens, stream, fmt=None):
    body = {"model": MODEL, "messages": messages, "stream": stream, "temperature": 0.1, "max_tokens": max_tokens}
    if fmt == "json": body["response_format"] = {"type": "json_object"}
    elif isinstance(fmt, dict): body["response_format"] = {"type": "json_schema", "json_schema": {"name": "javob", "schema": fmt}}
    return body

async def llm(messages):
    """Javobni token-token oqim ko'rinishida beradi."""
    if not LLM_ON: raise RuntimeError("til modeli o'chirilgan")
    async with httpx.AsyncClient(timeout=180, headers=_headers()) as c:
        if LLM_API == "openai":
            async with c.stream("POST", f"{LLM_URL}/chat/completions", json=_oa_body(messages, 320, True)) as r:
                r.raise_for_status()
                async for line in r.aiter_lines():
                    if not line.startswith("data:"): continue
                    data = line[5:].strip()
                    if data == "[DONE]": break
                    ch = (json.loads(data).get("choices") or [{}])[0]
                    tok = (ch.get("delta") or {}).get("content")
                    if tok: yield tok
            return
        body = {"model": MODEL, "messages": messages, "stream": True, "think": False,
                "keep_alive": "60m", "options": {"temperature": 0.1, "num_ctx": 6144, "num_predict": 320}}
        async with c.stream("POST", f"{LLM_URL}/api/chat", json=body) as r:
            r.raise_for_status()
            async for line in r.aiter_lines():
                if line:
                    tok = json.loads(line).get("message", {}).get("content")
                    if tok:
                        yield tok

async def llm_once(messages, fmt=None, max_tokens=700):
    if not LLM_ON: raise RuntimeError("til modeli o'chirilgan")
    async with httpx.AsyncClient(timeout=240, headers=_headers()) as c:
        if LLM_API == "openai":
            r = await c.post(f"{LLM_URL}/chat/completions", json=_oa_body(messages, max_tokens, False, fmt)); r.raise_for_status()
            return r.json()["choices"][0]["message"]["content"]
        body = {"model": MODEL, "messages": messages, "stream": False, "think": False, "keep_alive": "60m",
                "options": {"temperature": 0.1, "num_ctx": 6144, "num_predict": max_tokens}}
        if fmt: body["format"] = fmt
        r = await c.post(f"{LLM_URL}/api/chat", json=body); r.raise_for_status()
        return r.json()["message"]["content"]

async def warmup():
    """Modelni xotiraga oldindan yuklab qo'yadi — birinchi javob tez chiqishi uchun."""
    if not LLM_ON or LLM_API != "ollama":
        await llm_available(); return
    try:
        async with httpx.AsyncClient(timeout=120, headers=_headers()) as c:
            await c.post(f"{LLM_URL}/api/chat", json={"model": MODEL, "messages": [{"role": "user", "content": "salom"}],
                         "stream": False, "think": False, "keep_alive": "60m", "options": {"num_ctx": 6144, "num_predict": 1}})
    except Exception:
        pass

# «Tahlil rejimi» sabablari — foydalanuvchiga ko'rsatiladigan matn (dasturchi buyrug'i emas)
TAHLIL = "Tizim «Tahlil rejimi»da ishlaydi: raqamlar va xulosalar qoidalar asosida hisoblanadi."
REASONS = {
    "off": "Til modeli administrator tomonidan o'chirilgan.",
    "unreachable": "Til modeli serveri hozir ulanmagan.",
    "no_model": "Til modeli serverida kerakli model yuklanmagan.",
    "error": "Til modeli javob bermadi.",
}
_AVAIL = {"t": -1e9, "ok": False, "code": None}

async def _probe() -> tuple[bool, str | None]:
    if not LLM_ON: return False, "off"
    want = MODEL.split(":")[0]
    try:
        async with httpx.AsyncClient(timeout=2, headers=_headers()) as c:
            if LLM_API == "openai":
                r = await c.get(f"{LLM_URL}/models"); r.raise_for_status()
                names = [m.get("id", "") for m in r.json().get("data", [])]
            else:
                r = await c.get(f"{LLM_URL}/api/tags"); r.raise_for_status()
                names = [m.get("name", "") for m in r.json().get("models", [])]
    except Exception:
        return False, "unreachable"
    return (True, None) if any(n.split("/")[-1].startswith(want) for n in names) else (False, "no_model")

async def llm_available() -> bool:
    """Natija qisqa muddat keshlanadi (har so'rovda tarmoq tekshiruvi bo'lmasin)."""
    if time.monotonic() - _AVAIL["t"] > (30 if _AVAIL["ok"] else 15):
        ok, code = await _probe()
        _AVAIL.update(t=time.monotonic(), ok=ok, code=code)
    return _AVAIL["ok"]

async def llm_status() -> dict:
    """/api/status → "ai". tools: har bir vosita uchun "ai" | "qoida" | None (None — vosita o'chiq, UI tugmani o'chiradi)."""
    ok = await llm_available()
    code = None if ok else (_AVAIL["code"] or "unreachable")
    return {"ai": ok, "mode": "ai" if ok else "tahlil", "model": MODEL, "backend": LLM_API, "local": _is_local(),
            "reason": None if ok else f"{REASONS[code]} {TAHLIL}", "reason_code": code,
            "tools": {"chat": "ai" if ok else "qoida", "extract": "ai" if ok else "qoida", "contract": "ai" if ok else "qoida",
                      "translate": "ai" if ok else None, "reply": "ai" if ok else None}}

def _is_local() -> bool:
    host = httpx.URL(LLM_URL).host or ""
    return host in ("localhost", "127.0.0.1", "::1")

async def classify(q: str) -> list[str]:
    """Kalit so'z topilmasa, modeldan qaysi ma'lumot kerakligini so'raymiz."""
    menu = "\n".join(f"- {k}: {d}" for k, (_, d) in TOOLS.items())
    try:
        out = await llm_once([{"role": "system", "content": f"Foydalanuvchi savoliga javob berish uchun qaysi ma'lumot manbalari kerak? Ro'yxat:\n{menu}\n"
                               'Faqat JSON qaytar: {"tools": ["..."]}. Ko\'pi bilan 3 ta.'},
                              {"role": "user", "content": q}], fmt="json")
        return [t for t in json.loads(out).get("tools", []) if t in TOOLS][:3]
    except Exception:
        return []

MONEY_KEYS = {"total", "paid", "debt", "planned", "actual", "fund", "avg", "amount", "salary", "total_fund", "contract_amount", "paid_amount"}

KEY_UZ = {"gpa": "o'rtacha_ball", "gpa_prev": "o'tgan_semestr_bali", "delta": "ball_o'zgarishi", "attendance": "davomat_foizi",
          "pct": "bajarilish_foizi", "n": "soni", "debtors": "qarzdorlar_soni", "debt": "qarz_summasi", "paid": "to'langan",
          "total": "jami", "planned": "reja", "actual": "haqiqiy", "over_pct": "rejadan_oshish_foizi", "name": "nomi", "grp": "guruh",
          "risk": "xavf_bali", "reasons": "sabablar", "count": "soni", "of": "jami_talaba", "days_left": "qolgan_kun", "scopus": "scopus_wos_2026",
          "degree_pct": "ilmiy_darajalilik_foizi", "applied": "arizalar", "enrolled": "talaba_bo'lganlar", "conv": "konversiya_foizi",
          "fund": "oylik_fond", "course": "kurs", "faculty": "fakultet", "due": "muddat", "overdue": "muddati_otgan", "assignee": "mas'ul"}

def trim(obj, n=6, key=None):
    """Modelga yuboriladigan ma'lumotni qisqartiradi va summalarni tayyor matnga aylantiradi (birlik xatolarining oldini oladi)."""
    if isinstance(obj, list): return [trim(x, n) for x in obj[:n]]
    if isinstance(obj, dict): return {KEY_UZ.get(k, k): trim(v, n, k) for k, v in obj.items() if k not in ("id", "hemis_id", "meeting_id", "assignee_role")}
    if isinstance(obj, int) and not isinstance(obj, bool) and (key in MONEY_KEYS) and obj >= 1_000_000:
        return S.mln(obj)
    return obj

HINTS = {
    "academic": "Pasaygan guruhlar bo'yicha kafedra mudirlari va kuratorlar bilan alohida yig'ilish o'tkazish; qo'shimcha konsultatsiya jadvalini joriy etish; 2 haftadan so'ng takroriy monitoring.",
    "risk": "Xavf ostidagi har bir talabaga kurator biriktirish; ota-onalar bilan bog'lanish; qayta topshirish jadvalini oldindan tuzish.",
    "contracts": "Eng past tushumli guruhlar bo'yicha individual to'lov jadvali taklif qilish; muddatli bo'lib to'lash imkoniyatini e'lon qilish.",
    "finance": "Rejadan oshgan moddalar bo'yicha buxgalteriyadan solishtirma dalolatnoma so'rash; keyingi chorak limitlarini qayta ko'rib chiqish.",
    "payroll": "Ish haqi fondini shtat jadvali bilan solishtirish; bo'sh shtat birliklarini aniqlash.",
    "science": "Nashri yo'q o'qituvchilar uchun individual ilmiy reja tuzish; Scopus jurnallariga maqola tayyorlash bo'yicha seminar o'tkazish.",
    "international": "Muddati tugayotgan shartnomalarni uzaytirish xatlarini shu hafta yuborish; faol bo'lmagan hamkorliklarni qayta baholash.",
    "admissions": "Arizalar kam bo'lgan yo'nalishlar uchun maqsadli targ'ibot rejasini tuzish.",
    "youth": "Hal qilinmagan murojaatlar bo'yicha mas'ullarni belgilab, bir hafta ichida javob berish.",
    "masters": "Dastlabki bosqichdagi magistrantlar bilan ilmiy rahbarlar uchrashuvini rejalashtirish.",
    "tasks": "Muddati o'tgan topshiriqlar bo'yicha mas'ullardan yozma tushuntirish so'rash va yangi muddat belgilash.",
}

def gather(con, ctx: Ctx, names: list[str], q: str):
    data, denied = {}, []
    for n in names:
        fn = TOOLS[n][0]
        try:
            data[n] = fn(con, ctx)
        except AccessDenied as e:
            denied.append(str(e))
    return data, denied

SYSTEM = """Sen ISFT Core — {inst} rahbariyati uchun sun'iy intellektli yordamchisan.
Bugun: {today}. Suhbatdosh: {who} ({role}). Ko'rish ko'lami: {scope}.
QOIDALAR:
1. Faqat o'zbek tilida (lotin yozuvida) javob ber. Rasmiy, qisqa va aniq yoz.
2. Faqat quyidagi MA'LUMOT ichidagi raqamlardan foydalan. Raqam o'ylab topma. Ma'lumot bo'lmasa, "bu ma'lumot menda yo'q" de.
3. Avval asosiy xulosani 1-2 jumlada ayt, so'ng 3-5 ta muhim faktni "•" bilan ro'yxat qil, oxirida "Tavsiya:" bilan 1-2 amaliy qadam ber.
4. Summalar ma'lumotda tayyor yozilgan ("1.31 mlrd so'm") — ularni aynan shunday ko'chir, qayta hisoblama. Guruh nomlarini aynan ko'chir.
5. Agar ba'zi ma'lumotga ruxsat berilmagan bo'lsa, buni ochiq ayt va aylanib o'tishga urinma.
6. Markdown sarlavhalar (#) ishlatma. Javob 110 so'zdan oshmasin, ortiqcha kirish so'zlarisiz.
7. Maydon nomlarini pastki chiziq bilan yozma (o'rtacha_ball emas, "o'rtacha ball"). Foizlarni qaysi ko'rsatkichga tegishli ekanini to'g'ri ayt.
8. Agar ma'lumot "jamlangan" bo'lsa (note maydoni), shaxsiy ma'lumot berilmasligini qisqa eslat."""

def fallback_answer(data: dict, denied: list[str]) -> str:
    """Model ishlamasa ham demo to'xtamasligi uchun shablon javob."""
    lines = []
    for k, v in data.items():
        if k == "academic":
            t = v["total"]; lines.append(f"• {v['scope']}: {t['n']} talaba, o'rtacha ball {t['gpa']} (avval {t['gpa_prev']}), davomat {t['attendance']}%.")
            for c in v.get("declining_clusters", [])[:3]: lines.append(f"• {S.decline_text(c)}.")
        elif k == "risk":
            lines.append(f"• O'qishda xavf: {v['count']} nafar talaba ({v['of']} nafardan; o'zlashtirish yoki davomat). Eng ko'p: " + ", ".join(f"{g['group']} ({g['count']} nafar)" for g in v["by_group"][:4]) + ".")
            if v.get("note"): lines.append(f"• {v['note']}.")
            for st in v.get("students", [])[:5]: lines.append(f"  – {st['full_name']} ({st['grp']}): xavf bali {st['risk']}, sabab: {st['reasons']}")
        elif k == "contracts":
            t = v["total"]; lines.append(f"• Kontrakt bo'yicha jami hisoblangan: {S.mln(t['total'])}, to'langan: {S.mln(t['paid'])}, tushum {t['pct']}%. Qarz: {S.mln(t['debt'])}. Qarzdor talabalar: {t['debtors']} nafar ({t['n']} kontrakt talabadan).")
            for f in v["by_faculty"]: lines.append(f"• {f['name']}: tushum {f['pct']}%, qarz {S.mln(f['debt'])}, qarzdorlar {f['debtors']} nafar.")
            lines.append("• Eng past tushumli guruhlar: " + ", ".join(f"{g['grp']} ({g['pct']}%)" for g in v["worst_groups"][:4]) + ".")
        elif k == "finance":
            t = v["total"]; lines.append(f"• Byudjet ijrosi {t['pct']}% ({S.mln(t['actual'])} / {S.mln(t['planned'])}).")
            for o in v["overruns"][:2]: lines.append(f"• {o['category']} {o['month']}: xarajat {S.mln(o['actual'])} — rejadagi {S.mln(o['planned'])} dan {o['over_pct']}% ko'p.")
        elif k == "science":
            lines.append(f"• Ilmiy daraja: {v['degree_pct']}%. 2026 nashrlari: " + ", ".join(f"{x['kind']} {x['n']}" for x in v["kinds_2026"]) + f". 2025 yildan beri nashrsiz: {v['no_pubs_since_2025']} o'qituvchi.")
        elif k == "international":
            lines.append(f"• Faol hamkorlar: {v['active']}. Tugayotganlar: " + (", ".join(f"{p['name']} ({p['days_left']} kun)" for p in v["expiring"]) or "yo'q") + ".")
        elif k == "admissions":
            lines.append(f"• Qabul: {v['total']} ariza. " + ", ".join(f"{f['status']}: {f['n']}" for f in v["funnel"]) + ".")
        elif k == "youth":
            lines.append((f"• Yotoqxona: " + ", ".join(f"{d['building']} {d['pct']}%" for d in v["dormitory"]) if v["dormitory"] else "• Hamkor turar joylar kiritilmagan") + f". Hal qilinmagan murojaatlar: {v['appeals_open']}.")
        elif k == "masters":
            lines.append(f"• Magistrantlar: {v['total']}. " + ", ".join(f"{s['stage']}: {s['n']}" for s in v["stages"]) + ".")
        elif k == "tasks":
            lines.append(f"• Topshiriqlar: {len(v['tasks'])} ta, bajarilgan {v['done']}, muddati o'tgan {v['overdue']}.")
            for t in [t for t in v["tasks"] if t["overdue"]][:3]: lines.append(f"  – {t['assignee']}: {t['text']} (muddat {t['due']})")
        elif k == "payroll":
            lines.append(f"• Oylik ish haqi fondi jami: {S.mln(v['total_fund'])}. " + ", ".join(f"{u['unit']}: {S.mln(u['fund'])} ({u['n']} xodim)" for u in v["by_unit"][:5]) + ".")
            if "staff" not in v: lines.append("• Shaxsiy ish haqi ma'lumotlari bu darajaga faqat jamlangan shaklda chiqadi.")
        elif k == "staffabs":
            lines.append("• " + v["text"])
            if v.get("by_unit"): lines.append("• Shtat: " + ", ".join(f"{u['unit']} {u['n']}" for u in v["by_unit"][:5]) + ".")
        elif k == "hr":
            lines.append(f"• Xodimlar: " + ", ".join(f"{u['unit']} {u['n']}" for u in v["by_unit"][:5]) + ".")
        elif k == "alerts":
            for a in v[:5]: lines.append(f"• [{a['area']}] {a['text']}")
    lines += denied
    return "\n".join(lines) or "Savolingizni aniqlashtiring: o'zlashtirish, kontrakt, byudjet, ilmiy faoliyat, xalqaro hamkorlik, qabul, topshiriqlar."

async def answer(con, ctx: Ctx, q: str):
    """Asinxron generator: avval meta (JSON qator), keyin javob matni bo'laklari."""
    audit(con, ctx, "savol", "chat", True, q)
    names = route(q)
    if not names and not strategic(q) and await llm_available():
        names = await classify(q)
    if strategic(q) and not names:
        names = [n for n in ("academic", "contracts", "tasks") if n in TOOLS]
    data, denied = gather(con, ctx, names, q)
    if strategic(q) or not names:
        data["alerts"] = S.alerts(con, ctx)
        audit(con, ctx, "strategik xulosa", "kpi", True, q)
    used = list(data.keys())
    use_llm = bool(data) and await llm_available()
    yield json.dumps({"sources": [TOOLS[n][1] if n in TOOLS else "proaktiv ogohlantirishlar" for n in used], "denied": denied,
                      "source": "ai" if use_llm else "qoida"}, ensure_ascii=False) + "\n"
    if not data and denied:
        yield "\n".join(denied); return
    if not use_llm:
        yield fallback_answer(data, denied); return
    payload = json.dumps(trim(data, 4), ensure_ascii=False, default=str)
    if len(payload) > 1800:   # katta JSON promptni sekinlashtiradi — faktlar yetarli
        payload = "(faktlar yetarli)"
    hints = " ".join(HINTS[k] for k in data if k in HINTS)
    sys = SYSTEM.format(inst="ISFT instituti", today=clock.today().isoformat(), who=ctx.user["full_name"], role=ctx.role.title, scope=ctx.scope_label(con))
    msgs = [{"role": "system", "content": sys},
            {"role": "user", "content": f"SAVOL: {q}\n\nASOSIY FAKTLAR (tekshirilgan, aynan shu raqamlarni ishlat):\n{fallback_answer(data, [])}\n\nQO'SHIMCHA TAFSILOT (JSON, faqat kerak bo'lsa):\n{payload}\n\nRUXSAT BERILMAGAN: {denied or 'yoq'}\n\nTAVSIYA UCHUN NAMUNALAR (shulardan eng mosini tanla, o'zgartirmasdan yoki qisqartirib yoz): {hints or 'umumiy holatga qarab'}"}]
    try:
        async for tok in llm(msgs):
            yield tok
    except Exception:
        yield fallback_answer(data, denied)

# ---------- Majlis bayonnomasidan topshiriqlarni ajratish ----------
TASK_RE = re.compile(r"(?P<who>[A-ZА-Я][\w'ʻ’\- .]+?)\s*[:—–-]\s*(?P<text>.+?)(?:[,.;]?\s*(?:muddat(?:i)?|gacha|до)\s*[:\-]?\s*(?P<due>\d{1,2}[./]\d{1,2}(?:[./]\d{2,4})?|\d{4}-\d{2}-\d{2}))", re.I)

def _parse_date(s):
    if not s: return None
    try:
        if re.match(r"\d{4}-\d{2}-\d{2}", s): return dt.date.fromisoformat(s[:10]).isoformat()
        p = re.split(r"[./]", s); d, m = int(p[0]), int(p[1]); y = int(p[2]) if len(p) > 2 else (clock.today().year if m >= clock.today().month - 1 else clock.today().year + 1)
        if y < 100: y += 2000
        return dt.date(y, m, d).isoformat()
    except ValueError:
        return None   # "31.02" kabi mavjud bo'lmagan sana

async def extract_tasks(transcript: str) -> list[dict]:
    return (await extract_tasks_result(transcript))["tasks"]

async def extract_tasks_result(transcript: str) -> dict:
    """{"tasks": [...], "source": "ai" | "qoida"} — model ishlamasa, bayonnoma qoidalar (regex) bilan ajratiladi."""
    if await llm_available():
        try:
            out = await llm_once([{"role": "system", "content":
                "Sen majlis kotibisan. Bayonnomadan aniq topshiriqlarni ajrat. Har biri uchun: assignee (kim mas'ul — lavozim yoki ism), "
                f"text (nima qilish kerak, qisqa buyruq shaklida), due (YYYY-MM-DD; bugun {clock.today().isoformat()}; ko'rsatilmagan bo'lsa bugundan 14 kun keyin: {(clock.today() + dt.timedelta(days=14)).isoformat()}). "
                'Faqat JSON: {"tasks":[{"assignee":"","text":"","due":""}]}'},
                {"role": "user", "content": transcript}], fmt="json")
            tasks = json.loads(out).get("tasks", [])
            tasks = [t for t in tasks if t.get("text")]
            if tasks: return {"tasks": tasks, "source": "ai"}
        except Exception:
            pass
    out = []
    for line in transcript.splitlines():
        # bir qatorda bir nechta gap: "Rektor: ... jiddiy. Registrator ofisi: ... tuzsin, muddat 15.11."
        for sent in re.split(r"(?<=[.!?])\s+(?=[A-ZА-ЯЎҚҒҲ])", line.strip()):
            m = TASK_RE.search(sent)
            if m:
                out.append({"assignee": m["who"].strip(), "text": m["text"].strip(), "due": _parse_date(m["due"])}); continue
            m = WHO_RE.match(sent)
            if m and ACTION_RE.search(m["text"]):   # muddatsiz, lekin aniq topshiriq ("... bir hafta ichida yopish")
                days = 7 if "hafta" in m["text"].lower() else 14
                out.append({"assignee": m["who"].strip(), "text": m["text"].strip().rstrip("."), "due": (clock.today() + dt.timedelta(days=days)).isoformat()})
    return {"tasks": out, "source": "qoida"}

WHO_RE = re.compile(r"^(?P<who>[A-ZА-Я][\w'ʻ’\- ]{2,60}?)\s*:\s*(?P<text>.+)$")
ACTION_RE = re.compile(r"\w+(sin|ish|ishni|ishsin|ilsin|asin)\b", re.I)

async def doc_assist_result(text: str, mode: str) -> dict:
    """{"result": str, "ai": bool, "source": "ai"|"qoida"|None, "reason": str (ai=false bo'lsa), "mode": ...}"""
    prompts = {
        "translate": "Quyidagi xatni o'zbek tiliga (lotin) rasmiy uslubda tarjima qil. Agar matn o'zbekcha bo'lsa, ingliz tiliga rasmiy tarjima qil. Faqat tarjimani yoz.",
        "contract": "Sen oliy ta'lim muassasasi yuristiga yordamchisan. Quyidagi shartnoma matnidan e'tibor talab qiladigan bandlarni top: "
                    "moliyaviy majburiyatlar, jarimalar, bir tomonlama bekor qilish, intellektual mulk, muddat, javobgarlik, nizolarni hal qilish joyi. "
                    "Har bir xavfli band uchun FAQAT bitta qator yoz: '⚠ <band raqami>: <xavf, 1 qisqa jumla> → <tavsiya, 1 qisqa jumla>'. Ko'pi bilan 6 qator. "
                    "O'zbek tilida (lotin). Oxirida: 'Yakuniy qarorni yurist qabul qiladi.'",
        "reply": "Quyidagi xorijiy hamkor xatiga institut nomidan qisqa, xushmuomala rasmiy javob loyihasini ingliz tilida yoz. So'ng o'zbekcha qisqa mazmunini ber.",
    }
    code = None
    if await llm_available():
        try:
            out = await llm_once([{"role": "system", "content": prompts[mode]}, {"role": "user", "content": text[:12000]}])
            return {"result": out, "ai": True, "source": "ai", "mode": mode}
        except Exception:
            code = "error"
    code = code or _AVAIL["code"] or "unreachable"
    reason = f"{REASONS[code]} {TAHLIL}"
    if mode == "contract":   # shartnoma: kalit so'zlar bo'yicha qoidaviy tekshiruv
        return {"result": contract_rules(text), "ai": False, "source": "qoida", "reason": reason, "mode": mode}
    what = {"translate": "Tarjima", "reply": "Javob loyihasi"}[mode]
    return {"result": f"{what} hozircha mavjud emas. {REASONS[code]} Bu vosita til modelini talab qiladi va «Tahlil rejimi»da o'chirilgan. "
                      "Keyinroq qayta urinib ko'ring yoki matnni xalqaro bo'limga yuboring.",
            "ai": False, "source": None, "reason": reason, "mode": mode}

# ---------- Shartnoma: qoidaviy tekshiruv (til modeli yo'q paytda) ----------
CONTRACT_RULES = [
    (r"jarima|penya|neustoyka|penalt|liquidated damages", "jarima/penya bandi",
     "miqdori va yuqori chegarasini aniqlang, ikki tomonga teng bo'lsin"),
    (r"bir tomonlama|unilateral|terminate|bekor qil", "bekor qilish sharti",
     "ogohlantirish muddati kamida 30 kun va ikki tomonga teng bo'lsin"),
    (r"intellektual|mualliflik|dasturiy ta'minot|intellectual property|copyright|mulki hisoblanadi", "intellektual mulk",
     "institut yaratilgan natijalardan foydalanish huquqini saqlab qolsin"),
    (r"oldindan to'la|avans|prepay|in advance|advance payment", "oldindan to'lov",
     "to'lov bosqichma-bosqich, bajarilgan ish dalolatnomasi bo'yicha bo'lsin"),
    (r"javobgar|liabilit|indemn|zararni qopla|kompensatsiya", "javobgarlik",
     "javobgarlik chegarasi va istisnolarini aniq yozing"),
    (r"nizo|arbitraj|arbitration|governing law|jurisdiction|sudida|qonunchiligi", "nizolarni hal qilish joyi",
     "O'zbekiston Respublikasi qonunchiligi va sudi ko'rsatilsin"),
    (r"shaxsiy ma'lumot|personal data|uchinchi shaxs|third part|maxfiy|confidential", "ma'lumotlar va maxfiylik",
     "shaxsiy ma'lumotlar O'zbekistondan tashqariga chiqmasligi yozilsin"),
    (r"avtomatik uzaytiril|automatically renew|auto-renew|muddatsiz", "muddat va uzaytirish",
     "avtomatik uzaytirish o'rniga yozma kelishuv talab qilinsin"),
]

def contract_rules(text: str) -> str:
    """Kalit so'zlar bo'yicha e'tibor talab qiladigan bandlar. Til modeli emas — topilmagan xavf bo'lishi mumkin."""
    rows, seen = [], set()
    for line in [x.strip() for x in re.split(r"\n+|(?<=[.;])\s+(?=\d+\.\d+)", text or "") if x.strip()]:
        n = re.match(r"^(\d+(?:\.\d+)*)\.?\s", line)
        low = norm(line)
        for pat, what, tip in CONTRACT_RULES:
            if what in seen or not re.search(pat, low): continue
            seen.add(what)
            rows.append(f"⚠ {n.group(1) if n else 'band'}: {what} — tekshirish kerak → {tip}.")
        if len(rows) >= 6: break
    head = "Qoidalar asosida tekshiruv (til modeli ulanmagan): kalit so'zlar bo'yicha topilgan bandlar. Barcha xavflar topilmagan bo'lishi mumkin."
    body = "\n".join(rows) if rows else "Kalit so'zlar bo'yicha xavfli band topilmadi."
    return f"{head}\n{body}\nYakuniy qarorni yurist qabul qiladi."

async def doc_assist(text: str, mode: str) -> str:
    """Eski (faqat matn) interfeys — moslik uchun."""
    return (await doc_assist_result(text, mode))["result"]
