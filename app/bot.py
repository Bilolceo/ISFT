"""JARVIS Telegram bot — barcha xodimlar uchun bitta bot, ko'p rol.
Ishga tushirish:  TELEGRAM_BOT_TOKEN=... .venv/bin/python -m app.bot
Ulanish: botga /start, so'ng ulanish kodi va PIN:  REKTOR 1234
Xavfsizlik: kanal 'telegram' — ish haqi va kadrlar ma'lumoti hech kimga chiqmaydi, buxgalteriya va kadrlar bo'limi botga ulanmaydi."""
import os, json, logging
from telegram import Update, BotCommand
from telegram.constants import ChatAction
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters
from . import db, rbac, ai, reports
from .rbac import AccessDenied

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
con = db.connect()

def user_by_tg(tg_id):
    return db.one(con, "SELECT * FROM users WHERE telegram_id=?", (tg_id,))

async def start(update: Update, _: ContextTypes.DEFAULT_TYPE):
    u = user_by_tg(update.effective_user.id)
    if u:
        await update.message.reply_text(f"Siz {rbac.ROLES[u['role']].title} sifatida ulangansiz.\nSavol bering yoki /brifing, /topshiriqlar buyruqlaridan foydalaning.")
        return
    await update.message.reply_text("Assalomu alaykum! Men JARVIS — ISFT institutining sun'iy intellektli yordamchisiman.\n\n"
                                    "Ulanish uchun lavozim kodingiz va PIN'ni yuboring.\nMasalan: REKTOR 1234")

async def logout(update: Update, _):
    con.execute("UPDATE users SET telegram_id=NULL WHERE telegram_id=?", (update.effective_user.id,)); con.commit()
    await update.message.reply_text("Hisob uzildi. Qayta ulanish uchun kod va PIN yuboring.")

async def try_link(update: Update, text: str) -> bool:
    parts = text.strip().split()
    if len(parts) != 2: return False
    u = db.one(con, "SELECT * FROM users WHERE upper(link_code)=? AND pin=?", (parts[0].upper(), parts[1]))
    if not u:
        await update.message.reply_text("Kod yoki PIN noto'g'ri."); return True
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
            await update.message.reply_text("Avval ulaning: lavozim kodi va PIN. Masalan: REKTOR 1234")
        return
    ctx = rbac.Ctx(u, rbac.ROLES[u["role"]], "telegram")
    await context.bot.send_chat_action(update.effective_chat.id, ChatAction.TYPING)
    msg = await update.message.reply_text("⏳ Ma'lumot tekshirilmoqda…")
    out, meta = "", None
    async for chunk in ai.answer(con, ctx, text):
        if meta is None:
            meta = json.loads(chunk); continue
        out += chunk
    src = ("📂 " + "; ".join(meta["sources"]) + "\n\n") if meta and meta["sources"] else ""
    await msg.edit_text((src + out.strip())[:4000] or "Javob topilmadi.")

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

async def post_init(app):
    await app.bot.set_my_commands([BotCommand("brifing", "Haftalik brifing (Word)"), BotCommand("topshiriqlar", "Majlis topshiriqlari"),
                                   BotCommand("chiqish", "Hisobni uzish")])

def main():
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise SystemExit("TELEGRAM_BOT_TOKEN o'rnatilmagan. @BotFather orqali bot yarating va tokenni bering.")
    app = Application.builder().token(token).post_init(post_init).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("chiqish", logout))
    app.add_handler(CommandHandler("brifing", brifing))
    app.add_handler(CommandHandler("topshiriqlar", topshiriqlar))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))
    app.run_polling()

if __name__ == "__main__":
    main()
