"""ISFT Core Telegram bot — barcha xodimlar uchun bitta bot, ko'p rol.
Ishga tushirish:  TELEGRAM_BOT_TOKEN=... .venv/bin/python -m app.bot
Ulanish: botga /start, so'ng lavozim kodi va shaxsiy parol (masalan: REKTOR <parol>). Xato urinishlar cheklangan.
Xavfsizlik: kanal 'telegram' — ish haqi va kadrlar ma'lumoti hech kimga chiqmaydi, buxgalteriya va kadrlar bo'limi botga ulanmaydi."""
import os, json, logging
from telegram import Update, BotCommand
from telegram.constants import ChatAction
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters
from . import db, rbac, ai, reports, agent as AG, agent_hub as AH, sessions as SS
from .rbac import AccessDenied

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
con = db.connect()

TG_LIMIT = SS.Limiter(5, 600)     # bitta Telegram akkaunt yoki bitta lavozim kodi: 10 daqiqada 5 ta xato

def user_by_tg(tg_id):
    return db.one(con, "SELECT * FROM users WHERE telegram_id=?", (tg_id,))

async def start(update: Update, _: ContextTypes.DEFAULT_TYPE):
    u = user_by_tg(update.effective_user.id)
    if u:
        await update.message.reply_text(f"Siz {rbac.ROLES[u['role']].title} sifatida ulangansiz.\nSavol bering yoki /brifing, /topshiriqlar buyruqlaridan foydalaning.")
        return
    await update.message.reply_text("Assalomu alaykum! Men ISFT Core — institutning sun'iy intellektli boshqaruv tizimiman.\n\n"
                                    "Ulanish uchun lavozim kodingiz va parolingizni bitta xabarda yuboring.\nKo'rinishi: KOD parol")

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
    con.execute("UPDATE users SET telegram_id=? WHERE id=?", (update.effective_user.id, u["id"])); con.commit()
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
        p = reports.build(con, ctx, "brifing")
        await update.message.reply_document(open(p, "rb"), filename=p.name, caption="Rahbariyat uchun haftalik brifing")
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

BRIEF_ROLES = ("rektor", "kengash", "prorektor_oquv", "prorektor_ilmiy", "prorektor_moliya", "prorektor_yoshlar")
BRIEF_AT = os.getenv("ISFT_CORE_BRIEF_TIME", "08:00")

async def send_briefs(bot):
    """Rektor yordamchisi agenti: ulangan rahbarlarga kunlik brifing."""
    try:
        AH.scan(con)
    except Exception:         # skaner xatosi brifingni to'xtatmaydi — mavjud takliflar bilan yuboriladi
        logging.exception("agent skaneri xatosi")
    for u in db.rows(con, f"SELECT * FROM users WHERE telegram_id IS NOT NULL AND role IN ({','.join('?' * len(BRIEF_ROLES))})", BRIEF_ROLES):
        ctx = rbac.Ctx(u, rbac.ROLES[u["role"]], "telegram")
        try:
            await bot.send_message(u["telegram_id"], AH.brief_text(con, ctx))
            rbac.audit(con, ctx, "kunlik brifing Telegram'ga yuborildi", "agents", True)
        except Exception as e:
            logging.warning("brifing yuborilmadi (%s): %s", u["id"], e)

async def brief_loop(app):
    import asyncio, datetime as dt
    hh, mm = map(int, BRIEF_AT.split(":"))
    while True:
        now = dt.datetime.now()
        nxt = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
        if nxt <= now: nxt += dt.timedelta(days=1)
        await asyncio.sleep((nxt - now).total_seconds())
        try:
            await send_briefs(app.bot)
        except Exception:      # bitta xato (masalan, "database is locked") ertangi brifinglarni to'xtatmasin
            logging.exception("kunlik brifing yuborilmadi — ertaga qayta urinadi")
            await asyncio.sleep(60)

PORTAL_AT = os.getenv("ISFT_CORE_PORTAL_REMIND", "09:00")   # ish kunlari: portal muddat eslatmalari

async def send_portal_reminders(bot):
    """Portal: muddati yaqin/o'tgan xatlar — ijrochi xodimga, bo'lim rahbariga, yuboruvchiga va rezolyutsiya muallifiga.
    Bir xil eslatma kuniga bir marta; muddati o'tganlar — har 3 kunda (portal_reminders jurnali)."""
    from . import portal as PT
    for u, text, keys in PT.telegram_digest(con):
        try:
            await bot.send_message(u["telegram_id"], text)
            PT.mark_reminded(con, u["id"], keys)
            rbac.audit(con, rbac.Ctx(u, rbac.ROLES[u["role"]], "telegram"), "portal: muddat eslatmasi Telegram'ga yuborildi", "portal", True, f"{len(keys)} ta xat")
        except Exception as e:
            logging.warning("portal eslatmasi yuborilmadi (%s): %s", u["id"], e)

async def portal_loop(app):
    import asyncio, datetime as dt
    hh, mm = map(int, PORTAL_AT.split(":"))
    while True:
        now = dt.datetime.now()
        nxt = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
        if nxt <= now: nxt += dt.timedelta(days=1)
        while nxt.weekday() == 6: nxt += dt.timedelta(days=1)        # yakshanba — dam olish
        await asyncio.sleep((nxt - now).total_seconds())
        try:
            await send_portal_reminders(app.bot)
        except Exception:
            logging.exception("portal eslatmalari yuborilmadi — ertaga qayta urinadi")
            await asyncio.sleep(60)

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

async def post_init(app):
    import asyncio
    AH.init(con)              # bot veb-ilovadan oldin ishga tushsa ham agent jadvallari tayyor bo'lsin
    from . import portal as PT
    PT.migrate(con)           # portal jadvallari (eslatmalar jurnali, org_units) tayyor bo'lsin
    app.bot_data["brief_task"] = asyncio.get_running_loop().create_task(brief_loop(app))   # havola saqlanadi (GC yig'ib olmasin)
    app.bot_data["portal_task"] = asyncio.get_running_loop().create_task(portal_loop(app))
    await app.bot.set_my_commands([BotCommand("bugun", "Bugungi brifing (Rektor yordamchisi)"), BotCommand("brifing", "Haftalik brifing (Word)"), BotCommand("topshiriqlar", "Majlis topshiriqlari"),
                                   BotCommand("xatlar", "Portal: muddati yaqin xatlar"),
                                   BotCommand("chiqish", "Hisobni uzish")])

def main():
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise SystemExit("TELEGRAM_BOT_TOKEN o'rnatilmagan. @BotFather orqali bot yarating va tokenni bering.")
    app = Application.builder().token(token).post_init(post_init).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("chiqish", logout))
    app.add_handler(CommandHandler("brifing", brifing))
    app.add_handler(CommandHandler("bugun", brifing_matn))
    app.add_handler(CommandHandler("topshiriqlar", topshiriqlar))
    app.add_handler(CommandHandler("xatlar", xatlar))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))
    app.run_polling()

if __name__ == "__main__":
    main()
