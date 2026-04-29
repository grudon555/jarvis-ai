"""Telegram bot interface for Jarvis."""
from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Optional

from interface.conversation import ConversationManager

if TYPE_CHECKING:
    from agents.manager import ManagerAgent

log = logging.getLogger(__name__)

_HELP = """\
*Jarvis Befehle*

/start   — Willkommensnachricht
/help    — Diese Hilfe
/reset   — Gesprächskontext löschen
/skills  — Gelernte Skills anzeigen
/status  — Systemstatus
/ping    — Verbindungstest

_Einfach schreiben — Jarvis antwortet._"""


async def run_bot(token: str, manager: "ManagerAgent", conv: ConversationManager) -> None:
    """Start the Telegram bot (runs until cancelled)."""
    try:
        from telegram import Update
        from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
        from telegram.constants import ChatAction, ParseMode
    except ImportError:
        log.error("python-telegram-bot not installed. Run: pip install python-telegram-bot")
        return

    loop = asyncio.get_event_loop()

    async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        await update.message.reply_text(
            "⚡ *Jarvis ist bereit!*\n\nMulti-Agenten KI — schreib mir einfach.\n\n/help für alle Befehle.",
            parse_mode=ParseMode.MARKDOWN,
        )

    async def cmd_ping(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        await update.message.reply_text("🟢 Online.")

    async def cmd_reset(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        uid = str(update.effective_user.id)
        conv.reset(uid)
        await update.message.reply_text("🔄 Kontext gelöscht.")

    async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        await update.message.reply_text(_HELP, parse_mode=ParseMode.MARKDOWN)

    async def cmd_status(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        from core.config import settings
        from skills.registry import SkillRegistry
        from core.plugin_loader import PluginLoader
        try:
            from core.llm import LocalLLM
            model = LocalLLM().get_active_model().split(":")[0]
            ollama = f"✓ {model}"
        except Exception:
            ollama = "✗ offline"
        reg = SkillRegistry(skills_dir="skills", db_dir=".jarvis_db")
        loader = PluginLoader(plugins_dir="plugins")
        loader.load_all()
        msg = (
            f"*Jarvis Status*\n"
            f"Ollama   {ollama}\n"
            f"Cloud    {settings.cloud_model}\n"
            f"Skills   {reg.count}\n"
            f"Tools    {len(loader.get_tools())}"
        )
        await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)

    async def cmd_skills(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        from skills.registry import SkillRegistry
        reg = SkillRegistry(skills_dir="skills", db_dir=".jarvis_db")
        all_s = reg.list_all()
        if not all_s:
            await update.message.reply_text("📚 Noch keine Skills gelernt.")
            return
        lines = [f"*Skills ({len(all_s)})*"]
        for s in all_s:
            lines.append(f"• `{s['name']}` — {s['description'][:60]}  _(×{s.get('use_count',0)})_")
        await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN)

    async def handle_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        uid = str(update.effective_user.id)
        text = update.message.text or ""
        if not text:
            return

        await ctx.bot.send_chat_action(update.effective_chat.id, ChatAction.TYPING)
        msg = await update.message.reply_text("⏳")

        prompt = conv.build_prompt(uid, text)

        def _run():
            return manager.run(prompt)

        try:
            content, agent_log, meta = await loop.run_in_executor(None, _run)
        except Exception as e:
            await msg.edit_text(f"❌ Fehler: {str(e)[:300]}")
            return

        # Telegram max 4096 chars per message
        reply = content[:4096]
        try:
            await msg.edit_text(reply, parse_mode=ParseMode.MARKDOWN)
        except Exception:
            await msg.edit_text(reply)

        if meta.get("skill_saved"):
            await update.message.reply_text(f"💡 Skill gelernt: `{meta['skill_saved']}`", parse_mode=ParseMode.MARKDOWN)

        conv.add_turn(uid, text, content)

    async def handle_voice(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        await update.message.reply_text("🎤 Sprachnachrichten werden per WhatsApp unterstützt.")

    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("ping", cmd_ping))
    app.add_handler(CommandHandler("reset", cmd_reset))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("skills", cmd_skills))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))

    print(f"✓ Telegram bot starting (@{(await app.bot.get_me()).username})")
    await app.initialize()
    await app.start()
    await app.updater.start_polling(drop_pending_updates=True)

    # Keep running until cancelled
    try:
        await asyncio.Event().wait()
    finally:
        await app.updater.stop()
        await app.stop()
        await app.shutdown()
