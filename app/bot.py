"""ISFT Core Telegram bot — barcha xodimlar uchun bitta bot, ko'p rol.

Ishga tushirish (ikki yo'l, bir vaqtda faqat bittasi ishlaydi — data papkasidagi fayl qulfi):
  1) Veb-jarayon ichida (asosiy yo'l, Railway): TELEGRAM_BOT_TOKEN o'rnatilgan bo'lsa, app/main.py startup'da
     `start_in_app()` polling'ni asyncio vazifasi sifatida ishga tushiradi, shutdown'da `stop_in_app()` to'xtatadi.
     O'chirish: ISFT_CORE_BOT=0.
  2) Alohida jarayon:  TELEGRAM_BOT_TOKEN=... .venv/bin/python -m app.bot
Ulanish: botga /start, so'ng lavozim kodi va shaxsiy parol (masalan: REKTOR <parol>). Xato urinishlar cheklangan.
Xavfsizlik: kanal 'telegram' — ish haqi va kadrlar ma'lumoti hech kimga chiqmaydi, buxgalteriya va kadrlar bo'limi botga ulanmaydi.
Rejali ishlar (kunlik brifing 08:00, portal eslatmalari 09:00) Toshkent vaqtida: ISFT_CORE_TZ (standart Asia/Tashkent)."""
from __future__ import annotations
import asyncio, datetime as dt, hashlib, json, logging, os, re
try:
    from telegram import Update, BotCommand
    from telegram.constants import ChatAction
    from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters
    from telegram.error import InvalidToken, Conflict
except ImportError:          # kutubxona yo'q bo'lsa ham veb-ilova ishlaydi — bot o'chiq deb ko'rsatiladi
    Application = None
from . import clock
from . import db, rbac, ai, reports, agent as AG, agent_hub as AH, sessions as SS
from .rbac import AccessDenied

log = logging.getLogger("isft.bot")
logging.getLogger("httpx").setLevel(logging.WARNING)   # httpx INFO qatorlarida so'rov URL'i (ichida bot tokeni) bo'ladi — logga chiqmasin
con = db.connect()           # veb-jarayon ichida start_in_app() ilovaning ulanishini beradi

TG_LIMIT = SS.Limiter(5, 600)     # bitta Telegram akkaunt yoki bitta lavozim kodi: 10 daqiqada 5 ta xato

TZ = clock.TZ   # ISFT_CORE_TZ (standart Asia/Tashkent; tzdata bo'lmasa UTC+5) — app/clock.py

# ---------- holat (/api/status → "bot") ----------
STATE = {"enabled": False, "running": False, "username": None, "mode": None, "note": None,
         "last_error": None, "error_at": None, "started_at": None, "next_brief": None, "next_portal": None}
STATE_FILE = db.DATA_DIR / "bot_state.json"
_RUN: dict = {}

def _now_iso():
    return dt.datetime.now(TZ).isoformat(timespec="seconds")

def _redact(s) -> str:
    return _redact_all(str(s))[:300]

class _RedactFormatter(logging.Formatter):
    """PTB o'z xatolarida (traceback) tokenni ochiq yozadi — log qatoriga chiqishdan oldin yashiriladi."""
    def format(self, record):
        return _redact_all(super().format(record))

def _redact_all(s: str) -> str:
    tok = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if tok: s = s.replace(tok, "***")
    return re.sub(r"\d{5,}:[A-Za-z0-9_-]{20,}", "***", s)

def _save_state():
    """Holat faylga ham yoziladi — bot alohida jarayonda (python -m app.bot) ishlasa, veb /api/status uni o'qiydi."""
    if STATE.get("mode") not in ("web", "standalone"):   # qulf egasi bo'lmagan jarayon boshqa jarayon holatini ustidan yozmasin
        return
    try:
        tmp = STATE_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps({**STATE, "pid": os.getpid(), "updated": _now_iso()}, ensure_ascii=False))
        tmp.replace(STATE_FILE)
    except OSError:
        pass

def _set(**kw):
    STATE.update(kw)
    _save_state()

def _error(e, note=None):
    msg = _redact(e if isinstance(e, str) else f"{type(e).__name__}: {e}")
    _set(last_error=msg, error_at=_now_iso(), **({"note": note} if note else {}))
    log.warning("Telegram bot: %s", msg)

def status() -> dict:
    out = dict(STATE)
    if out.get("mode") == "external":          # boshqa jarayon (python -m app.bot) qulfni ushlab turibdi
        try:
            ext = json.loads(STATE_FILE.read_text())
            if ext.get("pid") != os.getpid():
                out.update({k: ext.get(k) for k in ("running", "username", "last_error", "error_at", "started_at", "next_brief", "next_portal")})
        except (OSError, ValueError):
            pass
    return out

def _lock(token):
    """Bitta token — bitta poller. Fayl qulfi data papkasida; jarayon tugasa OS qulfni o'zi bo'shatadi."""
    path = db.DATA_DIR / f".bot-{hashlib.sha256(token.encode()).hexdigest()[:12]}.lock"
    path.parent.mkdir(parents=True, exist_ok=True)
    f = open(path, "a+")
    try:
        import fcntl
        fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except ImportError:      # Windows: qulf yo'q — ISFT_CORE_BOT=0 bilan qo'lda boshqariladi
        pass
    except OSError:
        f.close(); return None
    f.seek(0); f.truncate(); f.write(str(os.getpid())); f.flush()
    return f

# ---------- foydalanuvchi buyruqlari ----------
def _ensure_fp():
    if "tg_pin_fp" not in {r[1] for r in con.execute("PRAGMA table_info(users)")}:
        con.execute("ALTER TABLE users ADD COLUMN tg_pin_fp TEXT"); con.commit()

def still_linked(u) -> bool:
    """Ulanish hali amaldami: akkaunt faol va parol ulanish paytidagidek. Parol qaysi yo'l bilan o'zgargan bo'lmasin (tiklash, o'zi almashtirgan,
    CLI) — ulanish uziladi va bot qayta tasdiqlashni (KOD parol) so'raydi. Eski ulanishlar (parol izi yo'q — iz joriy qilinishidan oldin
    ulangan) ham uziladi: ular qaysi parol bilan tasdiqlangani noma'lum, parol o'shandan beri o'zgargan bo'lishi mumkin — joriy parolga
    jimgina bog'lab qo'yish o'zgargan parolni «qonuniylashtirib» yuborardi. Foydalanuvchi bir marta KOD parol bilan qayta ulanadi."""
    if not u or u.get("active") == 0: return False   # accounts.py: faolsizlantirilgan akkaunt
    try:
        _ensure_fp()
        if "pin" not in u or "tg_pin_fp" not in u: u = db.one(con, "SELECT * FROM users WHERE id=?", (u["id"],)) or u
        if not u.get("telegram_id"): return False
        fp = rbac.pin_fp(u.get("pin"))
        if u.get("tg_pin_fp") != fp:
            con.execute("UPDATE users SET telegram_id=NULL, tg_pin_fp=NULL WHERE id=?", (u["id"],)); con.commit()
            why = "parol o'zgargan" if u.get("tg_pin_fp") else "eski ulanish (parol izi yo'q)"
            rbac.audit(con, rbac.Ctx(u, rbac.ROLES[u["role"]], "telegram"), "telegram ulanishi uzildi", "auth", True, f"{why} — qayta tasdiqlash kerak")
            return False
    except Exception as e:
        log.warning("still_linked: %s", e)
    return True

def user_by_tg(tg_id):
    u = db.one(con, "SELECT * FROM users WHERE telegram_id=?", (tg_id,))
    return u if still_linked(u) else None

async def start(update: Update, _: ContextTypes.DEFAULT_TYPE):
    u = user_by_tg(update.effective_user.id)
    if u:
        await update.message.reply_text(f"Siz {rbac.ROLES[u['role']].title} sifatida ulangansiz.\nSavol bering yoki /brifing, /topshiriqlar buyruqlaridan foydalaning.")
        return
    await update.message.reply_text("Assalomu alaykum! Men ISFT Core — institutning sun'iy intellektli boshqaruv tizimiman.\n\n"
                                    "Ulanish uchun lavozim kodingiz va parolingizni bitta xabarda yuboring.\nKo'rinishi: KOD parol\n"
                                    "(Parol o'zgartirilgan yoki tiklangan bo'lsa, ulanish uziladi — yangi parol bilan qayta ulaning.)")

async def logout(update: Update, _):
    con.execute("UPDATE users SET telegram_id=NULL WHERE telegram_id=?", (update.effective_user.id,)); con.commit()
    await update.message.reply_text("Hisob uzildi. Qayta ulanish uchun kod va parol yuboring.")

async def try_link(update: Update, text: str) -> bool:
    parts = text.strip().split()
    if len(parts) != 2: return False
    tg = update.effective_user.id
    wait = TG_LIMIT.wait_min(tg) or TG_LIMIT.wait_min(("kod", parts[0].upper()))
    if wait:
        await update.message.reply_text(f"⛔ Juda ko'p noto'g'ri urinish. {wait} daqiqadan keyin qayta urinib ko'ring."); return True
    u = db.one(con, "SELECT * FROM users WHERE upper(link_code)=?", (parts[0].upper(),))
    if u and u.get("active") == 0: u = None   # accounts.py: faolsizlantirilgan akkaunt ulanmaydi
    if u and not rbac.check_password(u["pin"], parts[1]):
        rbac.audit(con, rbac.Ctx(u, rbac.ROLES[u["role"]], "telegram"), "telegram ulanish", "auth", False, f"noto'g'ri parol · tg {tg}")
        TG_LIMIT.fail(("kod", parts[0].upper())); u = None
    if not u:
        TG_LIMIT.fail(tg)
        await update.message.reply_text("Kod yoki parol noto'g'ri."); return True
    TG_LIMIT.reset(tg)
    role = rbac.ROLES[u["role"]]
    ctx = rbac.Ctx(u, role, "telegram")
    if role.local_only:
        rbac.audit(con, ctx, "telegram ulanish", "auth", False, "local_only")
        await update.message.reply_text(f"⛔ {role.title} ma'lumotlari faqat institut ichki tarmog'ida ishlaydi. Telegram orqali ulanish mumkin emas.")
        return True
    con.execute("UPDATE users SET telegram_id=NULL WHERE telegram_id=?", (update.effective_user.id,))
    _ensure_fp()
    con.execute("UPDATE users SET telegram_id=?, tg_pin_fp=? WHERE id=?", (update.effective_user.id, rbac.pin_fp(u["pin"]), u["id"])); con.commit()
    rbac.audit(con, ctx, "telegram ulanish", "auth", True)
    await update.message.reply_text(f"✅ Ulandi: {role.title}\nKo'lam: {ctx.scope_label(con)}\n\nSavol bering, masalan: «Qaysi yo'nalishda ortda qolyapmiz?»\nBuyruqlar: /brifing /topshiriqlar /chiqish")
    return True

async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text or ""
    u = user_by_tg(update.effective_user.id)
    if not u:
        if not await try_link(update, text):
            await update.message.reply_text("Avval ulaning: lavozim kodi va parolni bitta xabarda yuboring (KOD parol).")
        return
    ctx = rbac.Ctx(u, rbac.ROLES[u["role"]], "telegram")
    await context.bot.send_chat_action(update.effective_chat.id, ChatAction.TYPING)
    msg = await update.message.reply_text("⏳ Ma'lumot tekshirilmoqda…")
    ans = None
    async for line in AG.run(con, ctx, text):
        e = json.loads(line)
        if e.get("t") == "answer": ans = e
    if not ans:
        return await msg.edit_text("Javob topilmadi.")
    src = ("📂 " + "; ".join(ans["sources"]) + "\n\n") if ans["sources"] else ""
    v = ans.get("verify") or {}
    chk = f"\n\n✓ {v['ok']}/{v['n']} raqam manbadan tekshirildi" if v.get("n") else ""
    await msg.edit_text((src + ans["text"].strip() + chk)[:4000])

async def brifing(update: Update, _):
    u = user_by_tg(update.effective_user.id)
    if not u: return await start(update, _)
    ctx = rbac.Ctx(u, rbac.ROLES[u["role"]], "telegram")
    try:
        p = await asyncio.to_thread(reports.build, con, ctx, "brifing")   # Word fayl — veb so'rovlarini to'xtatmasin
        with open(p, "rb") as f:
            await update.message.reply_document(f, filename=p.name, caption="Rahbariyat uchun haftalik brifing")
    except AccessDenied as e:
        await update.message.reply_text(str(e))

async def topshiriqlar(update: Update, _):
    u = user_by_tg(update.effective_user.id)
    if not u: return await start(update, _)
    from . import services as S
    ctx = rbac.Ctx(u, rbac.ROLES[u["role"]], "telegram")
    try:
        t = S.tasks_list(con, ctx)
    except AccessDenied as e:
        return await update.message.reply_text(str(e))
    lines = [f"📋 Topshiriqlar: {len(t['tasks'])} · bajarilgan {t['done']} · muddati o'tgan {t['overdue']}\n"]
    for x in t["tasks"]:
        mark = "✅" if x["status"] == "bajarildi" else ("🔴" if x["overdue"] else "🟡")
        lines.append(f"{mark} {x['assignee']}: {x['text']} — {x['due']}")
    await update.message.reply_text("\n".join(lines)[:4000])

# ---------- rejali ishlar (Toshkent vaqti) ----------
BRIEF_ROLES = ("rektor", "kengash", "prorektor_oquv", "prorektor_ilmiy", "prorektor_moliya", "prorektor_yoshlar")
BRIEF_AT = os.getenv("ISFT_CORE_BRIEF_TIME", "08:00")
PORTAL_AT = os.getenv("ISFT_CORE_PORTAL_REMIND", "09:00")   # ish kunlari: portal muddat eslatmalari

def _hhmm(s, default):
    try:
        hh, mm = map(int, str(s).strip().split(":"))
        if 0 <= hh < 24 and 0 <= mm < 60: return hh, mm
    except ValueError:
        pass
    log.warning("noto'g'ri vaqt %r — %s ishlatiladi", s, default)
    return tuple(map(int, default.split(":")))

def next_run(hhmm: str, default: str, skip_sunday=False, now: dt.datetime | None = None) -> dt.datetime:
    """Keyingi ishga tushish vaqti — ISFT_CORE_TZ (Toshkent) bo'yicha, server soat zonasidan qat'i nazar."""
    hh, mm = _hhmm(hhmm, default)
    now = now or dt.datetime.now(TZ)
    nxt = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
    if nxt <= now: nxt += dt.timedelta(days=1)
    while skip_sunday and nxt.weekday() == 6: nxt += dt.timedelta(days=1)   # yakshanba — dam olish
    return nxt

async def _sleep_until(when: dt.datetime):
    while True:   # uzoq uyqu o'rniga bo'laklab — soat/zona o'zgarishi yoki tizim uyqusidan keyin ham aniq
        left = (when.astimezone(dt.timezone.utc) - dt.datetime.now(dt.timezone.utc)).total_seconds()   # UTC bo'yicha (DST'da ham to'g'ri)
        if left <= 0: return
        await asyncio.sleep(min(left, 300))

async def send_briefs(bot):
    """Rektor yordamchisi agenti: ulangan rahbarlarga kunlik brifing."""
    try:
        await asyncio.to_thread(AH.scan, con)
    except Exception:         # skaner xatosi brifingni to'xtatmaydi — mavjud takliflar bilan yuboriladi
        log.exception("agent skaneri xatosi")
    for u in db.rows(con, f"SELECT * FROM users WHERE telegram_id IS NOT NULL AND role IN ({','.join('?' * len(BRIEF_ROLES))})", BRIEF_ROLES):
        if not still_linked(u): continue       # parol o'zgargan — qayta tasdiqlanmaguncha hech narsa yuborilmaydi
        ctx = rbac.Ctx(u, rbac.ROLES[u["role"]], "telegram")
        try:
            await bot.send_message(u["telegram_id"], AH.brief_text(con, ctx))
            rbac.audit(con, ctx, "kunlik brifing Telegram'ga yuborildi", "agents", True)
        except Exception as e:
            log.warning("brifing yuborilmadi (%s): %s", u["id"], _redact(e))

async def brief_loop(app):
    while True:
        nxt = next_run(BRIEF_AT, "08:00")
        _set(next_brief=nxt.isoformat(timespec="minutes"))
        await _sleep_until(nxt)
        try:
            await send_briefs(app.bot)
        except Exception as e:      # bitta xato (masalan, "database is locked") ertangi brifinglarni to'xtatmasin
            log.exception("kunlik brifing yuborilmadi — ertaga qayta urinadi"); _error(e)
        await asyncio.sleep(61)     # bir daqiqa ichida qayta yubormaslik

async def send_portal_reminders(bot):
    """Portal: muddati yaqin/o'tgan xatlar — ijrochi xodimga, bo'lim rahbariga, yuboruvchiga va rezolyutsiya muallifiga.
    Bir xil eslatma kuniga bir marta; muddati o'tganlar — har 3 kunda (portal_reminders jurnali)."""
    from . import portal as PT
    for u, text, keys in await asyncio.to_thread(lambda: list(PT.telegram_digest(con))):
        if not still_linked(u): continue
        try:
            await bot.send_message(u["telegram_id"], text)
            PT.mark_reminded(con, u["id"], keys)
            rbac.audit(con, rbac.Ctx(u, rbac.ROLES[u["role"]], "telegram"), "portal: muddat eslatmasi Telegram'ga yuborildi", "portal", True, f"{len(keys)} ta xat")
        except Exception as e:
            log.warning("portal eslatmasi yuborilmadi (%s): %s", u["id"], _redact(e))

async def portal_loop(app):
    while True:
        nxt = next_run(PORTAL_AT, "09:00", skip_sunday=True)
        _set(next_portal=nxt.isoformat(timespec="minutes"))
        await _sleep_until(nxt)
        try:
            await send_portal_reminders(app.bot)
        except Exception as e:
            log.exception("portal eslatmalari yuborilmadi — ertaga qayta urinadi"); _error(e)
        await asyncio.sleep(61)

async def xatlar(update: Update, _):
    """/xatlar — portal: menga va bo'limimga tegishli, muddati yaqin/o'tgan xatlar."""
    u = user_by_tg(update.effective_user.id)
    if not u: return await start(update, _)
    from . import portal as PT
    items = PT.reminders_for(con, u, horizon=7)
    if not items:
        return await update.message.reply_text("📬 Portal: muddati yaqin yoki o'tgan xat yo'q.")
    lines = [f"📬 Portal: {len(items)} ta xat nazoratda\n"]
    for it in items[:20]:
        mark = "🔴" if it["kind"] == "otgan" else "🟠" if it["kind"] == "bugun" else "🟡"
        lines.append(f"{mark} {it['ref_no']} «{it['subject'][:80]}» — {PT.REMIND_LABEL[it['kind']]} ({it['due'][8:10]}.{it['due'][5:7]}), {PT.WHO_LABEL[it['who']]}")
    await update.message.reply_text("\n".join(lines)[:4000])

async def brifing_matn(update: Update, _):
    u = user_by_tg(update.effective_user.id)
    if not u: return await start(update, _)
    if u["role"] not in BRIEF_ROLES:
        return await update.message.reply_text("⛔ Kunlik brifing rahbariyat uchun.")
    await update.message.reply_text(AH.brief_text(con, rbac.Ctx(u, rbac.ROLES[u["role"]], "telegram")))

# ---------- Application hayot sikli ----------
async def post_init(app):
    AH.init(con)              # bot veb-ilovadan oldin ishga tushsa ham agent jadvallari tayyor bo'lsin
    from . import portal as PT
    PT.migrate(con)           # portal jadvallari (eslatmalar jurnali, org_units) tayyor bo'lsin
    loop = asyncio.get_running_loop()
    app.bot_data["brief_task"] = loop.create_task(brief_loop(app))   # havola saqlanadi (GC yig'ib olmasin)
    app.bot_data["portal_task"] = loop.create_task(portal_loop(app))
    await app.bot.set_my_commands([BotCommand("bugun", "Bugungi brifing (Rektor yordamchisi)"), BotCommand("brifing", "Haftalik brifing (Word)"), BotCommand("topshiriqlar", "Majlis topshiriqlari"),
                                   BotCommand("xatlar", "Portal: muddati yaqin xatlar"),
                                   BotCommand("chiqish", "Hisobni uzish")])
    _set(running=True, username=app.bot.username, started_at=_now_iso())
    log.info("Telegram bot ishga tushdi: @%s", app.bot.username)

async def post_stop(app):
    for k in ("brief_task", "portal_task"):
        t = app.bot_data.pop(k, None)
        if t: t.cancel()
    _set(running=False)

async def on_error(update, context):
    _error(context.error)

def _poll_error(e):
    """Updater polling xatosi (tarmoq, 409 Conflict) — PTB o'zi qayta urinadi, biz faqat holatga yozamiz."""
    if Application is not None and isinstance(e, Conflict):
        _error(e, note="Shu token bilan boshqa joyda ham bot ishlayapti (409 Conflict) — bittasini to'xtating.")
    else:
        _error(e)

def build_app(token: str):
    app = Application.builder().token(token).post_init(post_init).post_stop(post_stop).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("chiqish", logout))
    app.add_handler(CommandHandler("brifing", brifing))
    app.add_handler(CommandHandler("bugun", brifing_matn))
    app.add_handler(CommandHandler("topshiriqlar", topshiriqlar))
    app.add_handler(CommandHandler("xatlar", xatlar))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))
    app.add_error_handler(on_error)
    return app

def _off(v) -> bool:
    return str(v).strip().lower() in ("0", "false", "no", "off", "yoq", "yo'q")

async def _stop_app(app):
    for step in ("updater", "stop", "shutdown"):
        try:
            if step == "updater":
                if app.updater and app.updater.running: await app.updater.stop()
            elif step == "stop":
                if app.running: await app.stop()
                else: await post_stop(app)      # start() gacha yetmagan bo'lsa ham fon vazifalari to'xtasin
            else:
                await app.shutdown()
        except Exception as e:
            log.debug("bot %s: %s", step, e)

async def _supervise(token: str):
    """Polling'ni ishga tushiradi. Token noto'g'ri — to'xtaydi; tarmoq xatosi — kutib qayta urinadi."""
    delay = 30
    while True:
        app = build_app(token)
        _RUN["app"] = app
        try:
            await app.initialize()                       # getMe — token shu yerda tekshiriladi
            await post_init(app)                         # run_polling ishlatilmagani uchun qo'lda
            await app.updater.start_polling(drop_pending_updates=False, error_callback=_poll_error)
            await app.start()
            _set(last_error=None, error_at=None, note=None)
            return                                       # polling fon vazifalarida davom etadi
        except asyncio.CancelledError:
            await _stop_app(app); raise
        except InvalidToken as e:
            await _stop_app(app); _RUN.pop("app", None)
            _error(e, note="Token Telegram tomonidan rad etildi — @BotFather'dan yangi token olib, TELEGRAM_BOT_TOKEN'ni yangilang.")
            return
        except Exception as e:
            await _stop_app(app); _RUN.pop("app", None)
            _error(e, note=f"Ulanib bo'lmadi — {delay} soniyadan keyin qayta urinadi.")
            await asyncio.sleep(delay); delay = min(delay * 2, 600)

def _console_log():
    """uvicorn ildiz loggerni sozlamaydi — bot (va PTB) xabarlari Railway logida tokensiz ko'rinsin."""
    fmt = _RedactFormatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    for name, level in (("isft.bot", logging.INFO), ("telegram", logging.WARNING)):
        lg = logging.getLogger(name)
        if not lg.handlers:
            h = logging.StreamHandler(); h.setFormatter(fmt)
            lg.addHandler(h); lg.setLevel(level); lg.propagate = False

async def start_in_app(app_con=None):
    """FastAPI startup: token bo'lsa — bot shu jarayonda (asyncio vazifasi). Token yo'q — ilova odatdagidek, faqat log."""
    global con
    _console_log()
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    _set(enabled=False, running=False, mode=None, note=None, last_error=None, error_at=None, username=None)
    if not token:
        _set(note="TELEGRAM_BOT_TOKEN o'rnatilmagan"); log.info("Telegram bot o'chiq: TELEGRAM_BOT_TOKEN o'rnatilmagan"); return
    if _off(os.getenv("ISFT_CORE_BOT", "1")):
        _set(note="ISFT_CORE_BOT=0 — veb-jarayonda bot o'chirilgan"); log.info("Telegram bot o'chiq: ISFT_CORE_BOT=0"); return
    if Application is None:
        _error("python-telegram-bot o'rnatilmagan", note="pip install -r requirements.txt"); return
    lock = _lock(token)
    if lock is None:
        STATE.update(enabled=True, mode="external", note="Bot boshqa jarayonda ishlayapti (fayl qulfi band) — bu jarayon polling qilmaydi")
        log.info("Telegram bot: boshqa jarayon allaqachon ishlatmoqda — bu yerda ishga tushmaydi"); return
    if app_con is not None: con = app_con
    _RUN["lock"] = lock
    _set(enabled=True, mode="web")
    _RUN["task"] = asyncio.get_running_loop().create_task(_supervise(token))

async def stop_in_app():
    """FastAPI shutdown: polling, fon vazifalari va qulf toza yopiladi."""
    t = _RUN.pop("task", None)
    if t and not t.done():
        t.cancel()
        try: await t
        except (asyncio.CancelledError, Exception): pass
    app = _RUN.pop("app", None)
    if app is not None:
        await _stop_app(app)
    lock = _RUN.pop("lock", None)
    if lock is not None:
        lock.close()
        if STATE.get("mode") == "web": _set(running=False)

def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    for h in logging.getLogger().handlers: h.setFormatter(_RedactFormatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    logging.getLogger("httpx").setLevel(logging.WARNING)
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        raise SystemExit("TELEGRAM_BOT_TOKEN o'rnatilmagan. @BotFather orqali bot yarating va tokenni bering.")
    if Application is None:
        raise SystemExit("python-telegram-bot o'rnatilmagan: pip install -r requirements.txt")
    lock = _lock(token)
    if lock is None:
        raise SystemExit("Bu token bilan bot allaqachon ishlayapti (veb-jarayon ichida yoki boshqa `python -m app.bot`). "
                         "Veb-jarayondagi botni o'chirish: ISFT_CORE_BOT=0.")
    _set(enabled=True, mode="standalone", note=None, last_error=None, error_at=None)
    try:
        build_app(token).run_polling()
    except InvalidToken as e:
        _error(e); raise SystemExit("Token Telegram tomonidan rad etildi — @BotFather'dan to'g'ri tokenni oling.")
    finally:
        _set(running=False); lock.close()

if __name__ == "__main__":
    main()
