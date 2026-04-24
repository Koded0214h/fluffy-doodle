"""
KODED OS — Reminder Handler
Handles: "remind me in X minutes/hours", /remindme command
"""

import logging
import re
from datetime import datetime, timedelta
from telegram import Update
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)


def parse_relative_time(text: str) -> int | None:
    """
    Parse relative time from natural language.
    Returns total seconds, or None if not found.
    Examples:
      "remind me in 10 minutes" -> 600
      "remind me in 2 hours" -> 7200
      "in 30 mins" -> 1800
    """
    text = text.lower()

    # Match patterns like "in 10 minutes", "in 2 hours", "in 1 hour 30 minutes"
    hours = 0
    minutes = 0

    hour_match = re.search(r'(\d+)\s*h(?:our|rs?)?', text)
    min_match = re.search(r'(\d+)\s*m(?:in(?:ute)?s?)?', text)

    if hour_match:
        hours = int(hour_match.group(1))
    if min_match:
        minutes = int(min_match.group(1))

    total_seconds = (hours * 3600) + (minutes * 60)
    return total_seconds if total_seconds > 0 else None


async def schedule_reminder_job(context: ContextTypes.DEFAULT_TYPE):
    """Job callback — fires when reminder is due."""
    job = context.job
    chat_id = job.chat_id
    message = job.data

    await context.bot.send_message(
        chat_id=chat_id,
        text=f"⏰ *Reminder:* {message}",
        parse_mode="Markdown"
    )


async def remindme_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handle /remindme and natural language reminder requests.
    Usage: /remindme in 10 minutes check Skurel PR
           /remindme in 2 hours join HSIL sync
    """
    text = update.message.text

    # Strip command prefix if present
    if text.startswith("/remindme"):
        text = text[len("/remindme"):].strip()

    seconds = parse_relative_time(text)

    if not seconds:
        await update.message.reply_text(
            "Couldn't parse that time. Try:\n"
            "`/remindme in 10 minutes check Skurel PR`\n"
            "`/remindme in 2 hours join HSIL sync`",
            parse_mode="Markdown"
        )
        return

    # Extract the reminder message (strip the time part)
    reminder_msg = re.sub(r'in\s+(\d+\s*h(?:our|rs?)?\s*)?(\d+\s*m(?:in(?:ute)?s?)?)?', '', text, flags=re.IGNORECASE)
    reminder_msg = reminder_msg.strip().strip(',').strip()
    if not reminder_msg:
        reminder_msg = "You asked me to remind you about something."

    # Schedule the job
    when = datetime.now() + timedelta(seconds=seconds)
    context.job_queue.run_once(
        schedule_reminder_job,
        when=seconds,
        chat_id=update.effective_chat.id,
        data=reminder_msg,
        name=f"reminder_{update.effective_chat.id}_{int(datetime.now().timestamp())}"
    )

    # Format confirmation
    if seconds < 3600:
        time_str = f"{seconds // 60} minute(s)"
    else:
        h = seconds // 3600
        m = (seconds % 3600) // 60
        time_str = f"{h}h {m}m" if m else f"{h} hour(s)"

    await update.message.reply_text(
        f"✅ I'll remind you in *{time_str}*\n_{reminder_msg}_",
        parse_mode="Markdown"
    )


async def detect_reminder_in_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """
    Called from text_message_handler to intercept natural language reminders.
    Returns True if it handled a reminder, False otherwise.
    """
    text = update.message.text.lower()

    trigger_phrases = ["remind me in", "remind me after", "ping me in", "alert me in"]
    if not any(p in text for p in trigger_phrases):
        return False

    await remindme_handler(update, context)
    return True