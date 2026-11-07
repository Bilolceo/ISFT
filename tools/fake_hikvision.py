"""Hikvision ISAPI emulyatori — haqiqiy kamera kelgunicha ulagichni sinash uchun (FAQAT ishlab chiqish/test).

Taqlid qiladi: HTTP Digest (MD5, qop=auth), deviceInfo, time (soat farqi bilan), counting capabilities/search,
Event/triggers va alertStream (multipart: yurak urishi, chiziq kesish/hududga kirish voqealari, ba'zan JPEG qism).
Javob tuzilmasi Hikvision ISAPI hujjatlariga yaqin, lekin har bir model farq qilishi mumkin — haqiqiy kamerada albatta qayta sinash kerak.

Ishga tushirish:
    .venv/bin/python -m uvicorn tools.fake_hikvision:app --host 127.0.0.1 --port 18090
Sozlash (muhit o'zgaruvchilari): FAKE_HIK_USER, FAKE_HIK_PASS, FAKE_HIK_MODEL, FAKE_HIK_SKEW (soniya), FAKE_HIK_COUNTING (1/0),
    FAKE_HIK_FW_DATE (masalan "build 230815"), FAKE_HIK_EVENT_SEC (voqealar oralig'i), FAKE_HIK_STREAM_LIMIT (test uchun: N qismdan keyin oqim tugaydi).
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

@app.get("/ISAPI/Event/triggers")
def triggers():
    return xml(f'<EventTriggerList version="2.0" {NS}><EventTrigger><id>linedetection-1</id><eventType>linedetection</eventType></EventTrigger></EventTriggerList>')

def _alert(event_type: str, state="active", extra=""):
    t = (dt.datetime.now().astimezone() + dt.timedelta(seconds=CFG["skew"])).replace(microsecond=0).isoformat()
    return (f'<EventNotificationAlert version="2.0" {NS}><ipAddress>127.0.0.1</ipAddress><channelID>1</channelID><dateTime>{t}</dateTime>'
            f'<activePostCount>1</activePostCount><eventType>{event_type}</eventType><eventState>{state}</eventState>'
            f'<eventDescription>{event_type} alarm</eventDescription>{extra}</EventNotificationAlert>')

@app.get("/ISAPI/Event/notification/alertStream")
async def alert_stream():
    async def gen():
        seq = ["videoloss:inactive", "linedetection", "videoloss:inactive", "fielddetection+jpeg", "VMD", "shelteralarm", "videoloss:inactive"]
        n = 0
        while True:
            item = seq[n % len(seq)]; n += 1
            typ, _, st = item.partition(":")
            jpeg = typ.endswith("+jpeg"); typ = typ.replace("+jpeg", "")
            x = _alert(typ, st or "active").encode()
            yield b"--boundary\r\nContent-Type: application/xml; charset=\"UTF-8\"\r\nContent-Length: " + str(len(x)).encode() + b"\r\n\r\n" + x + b"\r\n"
            if jpeg:   # haqiqiy kameralar voqea bilan rasm ham yuboradi — ulagich uni saqlamasdan tashlashi kerak
                img = b"\xff\xd8\xff\xe0" + os.urandom(2048) + b"\xff\xd9"
                yield b"--boundary\r\nContent-Type: image/jpeg\r\nContent-Length: " + str(len(img)).encode() + b"\r\n\r\n" + img + b"\r\n"
            if CFG["stream_limit"] and n >= CFG["stream_limit"]: return
            await asyncio.sleep(CFG["event_sec"])
    return StreamingResponse(gen(), media_type="multipart/mixed; boundary=boundary")

@app.get("/__stats")   # faqat emulyator: test uchun hisoblagichlar (haqiqiy kamerada yo'q)
def stats():
    return STATS
