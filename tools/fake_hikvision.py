"""Hikvision ISAPI emulyatori — haqiqiy kamera kelgunicha ulagichni sinash uchun (FAQAT ishlab chiqish/test).

Taqlid qiladi: HTTP Digest (MD5, qop=auth), deviceInfo, time (soat farqi bilan), counting capabilities/search,
Event/triggers (model oilasiga qarab), alertStream (multipart: yurak urishi, aqlli voqealar, ba'zan JPEG qism)
va navbat holati (queueManagement/status).

DIQQAT: teg va maydon nomlari (eventType qiymatlari, <maxTemperature>, <queueLength>, <waitingTime>, <regionPeopleNum>,
queueManagement yo'li, triggers ro'yxati) Hikvision ISAPI hujjatlariga TAXMINAN yaqin. Har bir model/proshivkada farq
qilishi mumkin — haqiqiy kamerada albatta qayta tekshirilishi SHART (docs/hikvision.md, "Haqiqiy kamerada qayta sinash").

Ishga tushirish:
    .venv/bin/python -m uvicorn tools.fake_hikvision:app --host 127.0.0.1 --port 18090
Sozlash (muhit o'zgaruvchilari):
    FAKE_HIK_USER, FAKE_HIK_PASS, FAKE_HIK_SKEW (soniya), FAKE_HIK_COUNTING (1/0), FAKE_HIK_FW_DATE (masalan "build 230815"),
    FAKE_HIK_MODEL        — model; Event/triggers ro'yxati shunga bog'liq (AcuSense / oddiy / DeepinView / termal)
    FAKE_HIK_EVENT_SEC    — voqealar oralig'i (soniya)
    FAKE_HIK_STREAM_LIMIT — test uchun: N ta XML qismdan keyin oqim tugaydi (JPEG qismlar hisoblanmaydi)
    FAKE_HIK_EVENTS       — vergul bilan ro'yxat; berilsa aylanish AYNAN shu (o'zgarishsiz). Element sintaksisi:
                            tur[:holat][+jpeg][=qiymat], masalan "videoloss:inactive,fielddetection+jpeg,TMA=80.5,personQueueDetection=30"
                            (=qiymat: TMA → maxTemperature, personQueueDetection → queueLength, regionPeopleCounting → regionPeopleNum)
    FAKE_HIK_THERMAL      — 1: standart aylanishga fireDetection/smokeDetection/TMA qo'shiladi (standart 0)
    FAKE_HIK_QUEUE        — 1/0: queueManagement/status bormi (0 → 404; standart 1)
    FAKE_HIK_QUEUE_LEN    — navbat uzunligini qat'iy belgilash (test uchun); bo'sh bo'lsa vaqtga qarab
"""
import asyncio, datetime as dt, hashlib, os, random, secrets
from fastapi import FastAPI, Request
from fastapi.responses import Response, StreamingResponse

CFG = {
    "user": os.getenv("FAKE_HIK_USER", "jarvis"), "password": os.getenv("FAKE_HIK_PASS", "Test-Pass-123"),
    "model": os.getenv("FAKE_HIK_MODEL", "DS-2CD2346G2-ISU/SL"), "realm": "IP Camera(E1234)",
    "skew": int(os.getenv("FAKE_HIK_SKEW", "0")), "counting": os.getenv("FAKE_HIK_COUNTING", "1") == "1",
    "fw_date": os.getenv("FAKE_HIK_FW_DATE", "build 230815"), "event_sec": float(os.getenv("FAKE_HIK_EVENT_SEC", "2")),
    "stream_limit": int(os.getenv("FAKE_HIK_STREAM_LIMIT", "0")),
    "events": os.getenv("FAKE_HIK_EVENTS", "").strip(), "thermal": os.getenv("FAKE_HIK_THERMAL", "0") == "1",
    "queue": os.getenv("FAKE_HIK_QUEUE", "1") == "1", "queue_len": os.getenv("FAKE_HIK_QUEUE_LEN", "").strip(),
}
NS = 'xmlns="http://www.hikvision.com/ver20/XMLSchema"'
app = FastAPI(title="Fake Hikvision ISAPI")
NONCES = set()
STATS = {"auth_fail": 0, "requests": 0}

def md5(s: str) -> str: return hashlib.md5(s.encode()).hexdigest()

def _challenge():
    n = secrets.token_hex(16); NONCES.add(n)
    return Response(status_code=401, headers={"WWW-Authenticate": f'Digest realm="{CFG["realm"]}", qop="auth", nonce="{n}", opaque="{secrets.token_hex(8)}", algorithm=MD5'})

def _parse(h: str) -> dict:
    out = {}
    for part in h[len("Digest "):].split(","):
        if "=" in part:
            k, v = part.strip().split("=", 1); out[k] = v.strip().strip('"')
    return out

def _authorized(req: Request) -> bool:
    h = req.headers.get("authorization", "")
    if not h.startswith("Digest "): return False
    p = _parse(h)
    if p.get("username") != CFG["user"] or p.get("nonce") not in NONCES: return False
    ha1 = md5(f'{CFG["user"]}:{CFG["realm"]}:{CFG["password"]}')
    ha2 = md5(f'{req.method}:{p.get("uri")}')
    ok = p.get("response") == md5(f'{ha1}:{p["nonce"]}:{p.get("nc")}:{p.get("cnonce")}:{p.get("qop")}:{ha2}')
    if not ok: STATS["auth_fail"] += 1
    return ok

def xml(body: str) -> Response:
    return Response(f'<?xml version="1.0" encoding="UTF-8"?>\n{body}', media_type="application/xml")

@app.middleware("http")
async def digest(req: Request, call_next):
    STATS["requests"] += 1
    if not _authorized(req): return _challenge()
    return await call_next(req)

@app.get("/ISAPI/System/deviceInfo")
def device_info():
    return xml(f'<DeviceInfo version="2.0" {NS}><deviceName>ISFT-A101</deviceName><deviceID>fake-0001</deviceID><model>{CFG["model"]}</model>'
               f'<serialNumber>DS-FAKE0001</serialNumber><firmwareVersion>V5.7.12</firmwareVersion><firmwareReleasedDate>{CFG["fw_date"]}</firmwareReleasedDate>'
               f'<deviceType>IPCamera</deviceType></DeviceInfo>')

@app.get("/ISAPI/System/time")
def time_():
    t = (dt.datetime.now().astimezone() + dt.timedelta(seconds=CFG["skew"])).replace(microsecond=0)
    return xml(f'<Time version="2.0" {NS}><timeMode>NTP</timeMode><localTime>{t.isoformat()}</localTime><timeZone>CST-5:00:00</timeZone></Time>')

@app.get("/ISAPI/System/Video/inputs/channels/{ch}/counting/capabilities")
def counting_caps(ch: int):
    if not CFG["counting"]: return Response(status_code=404)
    return xml(f'<Counting version="2.0" {NS}><enabled opt="true,false"/><reportType opt="daily,weekly,monthly"/></Counting>')

def _counts(t: dt.datetime):
    """Kun davomida kirdi/chiqdi: dars paytida xonada ~20–30 kishi."""
    m = t.hour * 60 + t.minute
    r = random.Random(t.date().toordinal())
    inside = 0 if m < 8 * 60 + 20 or m > 18 * 60 else 18 + r.randint(0, 12)
    enter = 40 + (m // 10)
    return enter, enter - inside

@app.post("/ISAPI/System/Video/inputs/channels/{ch}/counting/search")
async def counting_search(ch: int, req: Request):
    if not CFG["counting"]: return Response(status_code=404)
    body = (await req.body()).decode()
    if "CountingStatisticsDescription" not in body: return Response(status_code=400)
    e, x = _counts(dt.datetime.now())
    return xml(f'<CountingStatisticsResult version="2.0" {NS}><responseStatus>true</responseStatus><matchList><matchElement>'
               f'<timeSpan><startTime>{dt.date.today()}T00:00:00</startTime><endTime>{dt.date.today()}T23:59:59</endTime></timeSpan>'
               f'<enterCount>{e}</enterCount><exitCount>{x}</exitCount></matchElement></matchList></CountingStatisticsResult>')

# --- Model oilalari → qo'llanadigan eventType'lar (TAXMINIY; datasheet/proshivka bo'yicha tasdiqlash kerak) ---
BASIC = ["VMD", "videoloss", "shelteralarm", "linedetection", "fielddetection"]
ACUSENSE = BASIC + ["defocus", "scenechangedetection", "regionEntrance", "regionExiting"]
DEEPINVIEW = ACUSENSE + ["loitering", "peopleGathering", "running", "unattendedBaggage", "objectRemoval", "attendedBaggage",
                         "personQueueDetection", "regionPeopleCounting", "peopleCounting"]
THERMAL = ["fireDetection", "smokeDetection", "TMA", "linedetection", "fielddetection", "VMD", "videoloss", "shelteralarm"]
# tartib muhim: aniqroq prefikslar birinchi ("iDS-2CD7…" ichida "DS-2CD" ham bor)
FAMILIES = [("deepinview", ("iDS-2CD7",), DEEPINVIEW), ("thermal", ("DS-2TD",), THERMAL),
            ("acusense", ("DS-2CD2346G2", "G2-I"), ACUSENSE), ("basic", ("DS-2CD3D46G2T", "DS-2CD"), BASIC)]

def _family(model: str):
    for name, keys, evs in FAMILIES:
        if any(model.startswith(k) or k in model for k in keys): return name, evs
    return "basic", BASIC

@app.get("/ISAPI/Event/triggers")
def triggers():
    _, evs = _family(CFG["model"])
    items = "".join(f'<EventTrigger><id>{e}-1</id><eventType>{e}</eventType><videoInputChannelID>1</videoInputChannelID></EventTrigger>' for e in evs)
    return xml(f'<EventTriggerList version="2.0" {NS}>{items}</EventTriggerList>')

def _queue(t: dt.datetime, ch: int = 1):
    """Navbat (kishi, kutish soniyasi): dushanba 10–12 → 25+, tushlik 12–14 → 8–18, qolgan ish vaqti 0–8, kechasi 0."""
    if CFG["queue_len"]: n = int(CFG["queue_len"])
    else:
        r = random.Random(t.date().toordinal() * 100 + t.hour * 7 + ch)
        if t.weekday() == 0 and 10 <= t.hour < 12: n = 25 + r.randint(0, 12)
        elif 12 <= t.hour < 14: n = 8 + r.randint(0, 10)
        elif 8 <= t.hour < 18 and t.weekday() < 6: n = r.randint(0, 8)
        else: n = 0
    return n, n * 40                           # ~40 s bir kishiga (taxmin)

@app.get("/ISAPI/Intelligent/channels/{ch}/queueManagement/status")   # yo'l TAXMINIY — modelga qarab farq qiladi
def queue_status(ch: int):
    if not CFG["queue"]: return Response(status_code=404)
    n, w = _queue(dt.datetime.now(), ch)
    return xml(f'<QueueStatus version="2.0" {NS}><channelID>{ch}</channelID><queueLength>{n}</queueLength><waitingTime>{w}</waitingTime></QueueStatus>')

def _extra(typ: str, val: str) -> str:
    """Voqea turiga xos qo'shimcha maydonlar (teg nomlari TAXMINIY)."""
    if typ == "TMA":
        return f'<ThermometryAlarm><ruleID>1</ruleID><maxTemperature>{val or "71.5"}</maxTemperature><alarmRule>highestGreater</alarmRule></ThermometryAlarm>'
    if typ == "personQueueDetection":
        n = int(val) if val else _queue(dt.datetime.now())[0]
        return f'<QueueInfo><queueLength>{n}</queueLength><waitingTime>{n * 40}</waitingTime></QueueInfo>'
    if typ == "regionPeopleCounting":
        return f'<RegionPeopleCounting><regionPeopleNum>{val or random.randint(5, 40)}</regionPeopleNum></RegionPeopleCounting>'
    return ""

def _alert(event_type: str, state="active", extra=""):
    t = (dt.datetime.now().astimezone() + dt.timedelta(seconds=CFG["skew"])).replace(microsecond=0).isoformat()
    return (f'<EventNotificationAlert version="2.0" {NS}><ipAddress>127.0.0.1</ipAddress><channelID>1</channelID><dateTime>{t}</dateTime>'
            f'<activePostCount>1</activePostCount><eventType>{event_type}</eventType><eventState>{state}</eventState>'
            f'<eventDescription>{event_type} alarm</eventDescription>{extra}</EventNotificationAlert>')

# Standart aylanish: dastlabki 7 ta element o'zgarmagan (testlar STREAM_LIMIT=7 bilan shularga tayanadi), keyin yangi aqlli voqealar.
BASE_SEQ = ["videoloss:inactive", "linedetection", "videoloss:inactive", "fielddetection+jpeg", "VMD", "shelteralarm", "videoloss:inactive"]
SMART_SEQ = ["regionEntrance+jpeg", "regionExiting", "videoloss:inactive", "loitering", "peopleGathering", "running", "videoloss:inactive",
             "unattendedBaggage+jpeg", "attendedBaggage", "objectRemoval", "videoloss:inactive", "defocus", "scenechangedetection",
             "personQueueDetection", "regionPeopleCounting", "videoloss:inactive"]
THERMAL_SEQ = ["fireDetection+jpeg", "smokeDetection", "TMA", "videoloss:inactive"]

def _sequence() -> list:
    if CFG["events"]: return [s.strip() for s in CFG["events"].split(",") if s.strip()]   # aynan berilgani
    return BASE_SEQ + SMART_SEQ + (THERMAL_SEQ if CFG["thermal"] else [])

def _item(item: str):
    """'tur[:holat][+jpeg][=qiymat]' → (tur, holat, jpeg, qiymat)."""
    item, _, val = item.partition("=")
    jpeg = "+jpeg" in item; item = item.replace("+jpeg", "")
    typ, _, st = item.partition(":")
    return typ.strip(), (st.strip() or "active"), jpeg, val.strip()

@app.get("/ISAPI/Event/notification/alertStream")
async def alert_stream():
    seq = _sequence()
    async def gen():
        n = 0
        while seq:
            typ, st, jpeg, val = _item(seq[n % len(seq)]); n += 1
            x = _alert(typ, st, _extra(typ, val)).encode()
            yield b"--boundary\r\nContent-Type: application/xml; charset=\"UTF-8\"\r\nContent-Length: " + str(len(x)).encode() + b"\r\n\r\n" + x + b"\r\n"
            if jpeg:   # haqiqiy kameralar voqea bilan rasm ham yuboradi — ulagich uni saqlamasdan tashlashi kerak
                img = b"\xff\xd8\xff\xe0" + os.urandom(2048) + b"\xff\xd9"
                yield b"--boundary\r\nContent-Type: image/jpeg\r\nContent-Length: " + str(len(img)).encode() + b"\r\n\r\n" + img + b"\r\n"
            if CFG["stream_limit"] and n >= CFG["stream_limit"]: return
            await asyncio.sleep(CFG["event_sec"])
    return StreamingResponse(gen(), media_type="multipart/mixed; boundary=boundary")

@app.get("/__stats")   # faqat emulyator: test uchun hisoblagichlar (haqiqiy kamerada yo'q)
def stats():
    return {**STATS, "model": CFG["model"], "family": _family(CFG["model"])[0], "events": len(_sequence())}
