"""
KODED OS — Message Handlers
Text, Photo (vision), Voice (audio)
"""

import logging
from datetime import date
from telegram import Update
from telegram.ext import ContextTypes
from database import add_task, add_opportunity, log_standup
from gemini import (
    parse_task_list_from_image, parse_voice_message,
    parse_text_for_tasks, chat_with_gemini
)

logger = logging.getLogger(__name__)

TRACK_EMOJI = {
    "skurel": "💼", "teenovatex": "🔬", "stackd": "🎓",
    "unilag": "📚", "microsoft": "🏢", "personal": "👤", "general": "📌"
}


async def _save_tasks(user_id: int, tasks: list) -> list:
    """Persist extracted tasks to DB and return them with their IDs."""
    saved = []
    for t in tasks:
        task_id = await add_task(
            user_id=user_id,
            title=t.get("title", "Unnamed task"),
            track=t.get("track", "general"),
            due_time=t.get("due_time"),
            remind_at=t.get("due_time")  # schedule reminder at task time
        )
        saved.append({**t, "id": task_id})
    return saved


def _format_task_list(tasks: list) -> str:
    lines = []
    for t in tasks:
        emoji = TRACK_EMOJI.get(t.get("track", "general"), "📌")
        time_str = f" @ _{t['due_time']}_" if t.get("due_time") else ""
        lines.append(f"{emoji} {t['title']}{time_str}")
    return "\n".join(lines)


# ── Photo Handler ──────────────────────────────────────────────────────────

async def photo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Parse a snapped task list photo."""
    user_id = update.effective_user.id
    await update.message.reply_text("👀 Reading your list...")

    photo = update.message.photo[-1]  # highest resolution
    file = await context.bot.get_file(photo.file_id)
    image_bytes = await file.download_as_bytearray()

    result = await parse_task_list_from_image(user_id, bytes(image_bytes))

    tasks = result.get("tasks", [])
    summary = result.get("summary", "")
    vibe = result.get("vibe_check", "")

    if not tasks:
        await update.message.reply_text(
            "😬 Couldn't extract any tasks from that photo. Try a clearer snap or better lighting."
        )
        return

    saved = await _save_tasks(user_id, tasks)

    # Log as standup
    task_titles = ", ".join([t["title"] for t in saved])
    await log_standup(user_id, str(date.today()), "photo_list", task_titles)

    # Build reply
    task_list_str = _format_task_list(saved)
    reply = f"""📸 *List locked in!* {len(saved)} tasks logged.

{task_list_str}

_{vibe}_

I'll ping you as the day goes on. Let's get it 🔥"""

    await update.message.reply_text(reply, parse_mode="Markdown")


# ── Voice Handler ──────────────────────────────────────────────────────────

async def voice_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Transcribe and parse a voice note."""
    user_id = update.effective_user.id
    await update.message.reply_text("🎙️ Listening...")

    voice = update.message.voice
    file = await context.bot.get_file(voice.file_id)
    audio_bytes = await file.download_as_bytearray()

    result = await parse_voice_message(user_id, bytes(audio_bytes), mime_type="audio/ogg")

    intent = result.get("intent", "general_chat")
    response = result.get("response", "Got it.")
    tasks = result.get("tasks", [])
    opportunity = result.get("opportunity", {})
    transcript = result.get("transcript", "")

    # Save based on intent
    if intent == "add_task" and tasks:
        saved = await _save_tasks(user_id, tasks)
        task_list_str = _format_task_list(saved)
        reply = f"""🎙️ *Heard you!* Logged {len(saved)} task(s):

{task_list_str}

{response}"""
        await log_standup(user_id, str(date.today()), "voice", transcript[:300])

    elif intent == "add_opportunity" and opportunity.get("title"):
        opp_id = await add_opportunity(
            user_id=user_id,
            title=opportunity.get("title", ""),
            opp_type=opportunity.get("type", "general"),
            deadline=opportunity.get("deadline"),
            notes=opportunity.get("notes")
        )
        reply = f"🎯 Opportunity tracked!\n\n*{opportunity['title']}*"
        if opportunity.get("deadline"):
            reply += f"\nDeadline: {opportunity['deadline']}"
        reply += f"\n\n{response}"

    elif intent == "standup":
        await log_standup(user_id, str(date.today()), "voice_standup", transcript[:300])
        reply = response

    else:
        reply = response

    await update.message.reply_text(reply, parse_mode="Markdown")


# ── Text Handler ──────────────────────────────────────────────────────────

async def text_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle freeform text messages."""
    from handlers.reminders import detect_reminder_in_text

    user_id = update.effective_user.id
    text = update.message.text.strip()

    # Check for natural language reminders first
    if await detect_reminder_in_text(update, context):
        return

    # Quick done detection
    done_triggers = ["done with", "finished", "completed", "mark", "done —", "✅"]
    if any(t in text.lower() for t in done_triggers):
        # Let Gemini handle it as general chat with context
        reply = await chat_with_gemini(
            user_id,
            text,
            extra_context="User seems to be marking something as done. Acknowledge it and encourage them."
        )
        await update.message.reply_text(reply)
        return

    result = await parse_text_for_tasks(user_id, text)
    intent = result.get("intent", "general_chat")
    response = result.get("response", "")
    tasks = result.get("tasks", [])
    opportunity = result.get("opportunity", {})

    if intent == "add_task" and tasks:
        saved = await _save_tasks(user_id, tasks)
        task_list_str = _format_task_list(saved)
        reply = f"✅ Logged {len(saved)} task(s):\n\n{task_list_str}\n\n{response}"
        await log_standup(user_id, str(date.today()), "text", text[:300])

    elif intent == "add_opportunity" and opportunity.get("title"):
        await add_opportunity(
            user_id=user_id,
            title=opportunity.get("title", ""),
            opp_type=opportunity.get("type", "general"),
            deadline=opportunity.get("deadline"),
            notes=opportunity.get("notes")
        )
        reply = f"🎯 Got it! Tracking: *{opportunity['title']}*"
        if opportunity.get("deadline"):
            reply += f"\nDeadline: `{opportunity['deadline']}`"
        reply += f"\n\n{response}"

    elif intent == "standup":
        await log_standup(user_id, str(date.today()), "text_standup", text[:300])
        reply = response

    else:
        reply = response

    await update.message.reply_text(reply, parse_mode="Markdown")