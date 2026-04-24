"""
KODED OS — Telegram Second Brain Bot
Powered by Google Gemini 2.5 Flash
"""

import logging
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    filters, ContextTypes
)
from telegram import Update

from config import BOT_TOKEN, ALLOWED_USER_ID
from database import init_db
from scheduler import setup_scheduler
from handlers.commands import (
    start_handler, help_handler, tasks_handler,
    opportunities_handler, clear_handler, summary_handler
)
from handlers.messages import text_message_handler, photo_handler, voice_handler
from handlers.reminders import remindme_handler

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)


async def post_init(application: Application) -> None:
    await init_db()
    setup_scheduler(application)
    logger.info("🧠 KODED OS is online.")


def main():
    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .post_init(post_init)
        .build()
    )

    auth = filters.User(user_id=ALLOWED_USER_ID) if ALLOWED_USER_ID else filters.ALL

    # Commands
    app.add_handler(CommandHandler("start", start_handler))
    app.add_handler(CommandHandler("help", help_handler))
    app.add_handler(CommandHandler("tasks", tasks_handler))
    app.add_handler(CommandHandler("opps", opportunities_handler))
    app.add_handler(CommandHandler("clear", clear_handler))
    app.add_handler(CommandHandler("summary", summary_handler))
    app.add_handler(CommandHandler("remindme", remindme_handler))  # ← NEW

    # Messages
    app.add_handler(MessageHandler(auth & filters.TEXT & ~filters.COMMAND, text_message_handler))
    app.add_handler(MessageHandler(auth & filters.PHOTO, photo_handler))
    app.add_handler(MessageHandler(auth & filters.VOICE, voice_handler))

    logger.info("🚀 Polling started...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()