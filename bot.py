"""
KODED OS — Telegram Second Brain Bot
"""

import logging
from telegram.ext import Application, CommandHandler, MessageHandler, filters
from telegram import Update

from config import BOT_TOKEN, ALLOWED_USER_ID
from database import init_db
from scheduler import setup_scheduler
from handlers.commands import (
    start_handler, help_handler, settings_handler,
    tasks_handler, task_detail_handler, done_handler, edit_task_handler, delete_task_handler, clear_handler,
    opportunities_handler, opp_detail_handler, add_opp_handler, done_opp_handler, delete_opp_handler, edit_opp_handler,
    summary_handler
)
from handlers.messages import text_message_handler, photo_handler, voice_handler
from handlers.reminders import remindme_handler

logging.basicConfig(format="%(asctime)s | %(levelname)s | %(name)s | %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)


async def post_init(application: Application) -> None:
    await init_db()
    setup_scheduler(application)
    logger.info("🧠 KODED OS is online.")


def main():
    app = Application.builder().token(BOT_TOKEN).post_init(post_init).build()

    # Core
    app.add_handler(CommandHandler("start", start_handler))
    app.add_handler(CommandHandler("help", help_handler))
    app.add_handler(CommandHandler("settings", settings_handler))
    app.add_handler(CommandHandler("summary", summary_handler))
    app.add_handler(CommandHandler("remindme", remindme_handler))

    # Tasks
    app.add_handler(CommandHandler("tasks", tasks_handler))
    app.add_handler(CommandHandler("task", task_detail_handler))
    app.add_handler(CommandHandler("done", done_handler))
    app.add_handler(CommandHandler("edit", edit_task_handler))
    app.add_handler(CommandHandler("del", delete_task_handler))
    app.add_handler(CommandHandler("clear", clear_handler))

    # Opportunities
    app.add_handler(CommandHandler("opps", opportunities_handler))
    app.add_handler(CommandHandler("opp", opp_detail_handler))
    app.add_handler(CommandHandler("addobp", add_opp_handler))
    app.add_handler(CommandHandler("dopp", done_opp_handler))
    app.add_handler(CommandHandler("delopp", delete_opp_handler))
    app.add_handler(CommandHandler("editopp", edit_opp_handler))

    # Messages
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_message_handler))
    app.add_handler(MessageHandler(filters.PHOTO, photo_handler))
    app.add_handler(MessageHandler(filters.VOICE, voice_handler))

    logger.info("🚀 Polling started...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()