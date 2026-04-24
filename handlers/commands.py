"""
KODED OS — Command Handlers
"""

from datetime import date
from telegram import Update
from telegram.ext import ContextTypes
from database import get_tasks, get_opportunities, mark_task_done, mark_opportunity_done, clear_tasks, get_week_logs
from gemini import generate_weekly_summary


async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = """🧠 *KODED OS — Online*

Your personal AI chief of staff is up and running.

What I can do:
📸 Snap your task list → I'll read it and schedule reminders
🎙️ Send a voice note → I'll transcribe and log it
💬 Text me anything → tasks, opportunities, updates
⏰ I'll ping you throughout the day automatically

Commands:
/tasks — see today's active tasks
/opps — see tracked opportunities & deadlines
/summary — get your weekly summary now
/clear — wipe today's task list

Let's get it. What's on your plate today? 🚀"""
    await update.message.reply_text(msg, parse_mode="Markdown")


async def help_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = """*KODED OS — Help*

*Adding tasks:*
• Snap a photo of your list 📸
• Send a voice note 🎙️  
• Type it out: "fix farmIntel bug by 3pm, prep Stackd session at 6"

*Tracking opportunities:*
• Just mention it: "Microsoft internship deadline is May 30"
• "add hackathon — ETH Lagos, June 15"

*Checking in:*
• /tasks — active tasks
• /opps — opportunities & deadlines
• /summary — weekly AI summary
• /clear — clear today's list

*Done with a task?*
• Tell me: "done with the farmIntel bug"
• Or: "mark task 3 done"

I ping you at 7:30am (standup) and 9pm (wind-down) daily.
Weekly summary drops every Sunday at 8pm. 🦾"""
    await update.message.reply_text(msg, parse_mode="Markdown")


async def tasks_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tasks = await get_tasks(done=False)
    if not tasks:
        await update.message.reply_text("✅ No active tasks! Either you cleared it or you haven't added any yet. Drop your list.")
        return

    lines = ["📋 *Active Tasks*\n"]
    track_emoji = {
        "skurel": "💼", "teenovatex": "🔬", "stackd": "🎓",
        "unilag": "📚", "microsoft": "🏢", "personal": "👤", "general": "📌"
    }
    for t in tasks:
        emoji = track_emoji.get(t["track"], "📌")
        time_str = f" _{t['due_time']}_" if t["due_time"] else ""
        lines.append(f"{emoji} `[{t['id']}]` {t['title']}{time_str}")

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def opportunities_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    opps = await get_opportunities(done=False)
    if not opps:
        await update.message.reply_text("🎯 No opportunities tracked yet. Tell me about any hackathons, internship deadlines, or events.")
        return

    lines = ["🎯 *Tracked Opportunities*\n"]
    type_emoji = {
        "hackathon": "🏆", "internship": "🏢", "deadline": "⏰",
        "event": "📅", "general": "📌"
    }
    for o in opps:
        emoji = type_emoji.get(o["type"], "📌")
        deadline_str = f" — deadline: *{o['deadline']}*" if o["deadline"] else ""
        notes_str = f"\n   _{o['notes']}_" if o["notes"] else ""
        lines.append(f"{emoji} `[{o['id']}]` {o['title']}{deadline_str}{notes_str}")

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def clear_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await clear_tasks()
    await update.message.reply_text("🗑️ Task list cleared. Fresh start — drop your new list whenever you're ready.")


async def summary_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("⏳ Generating your weekly summary...")
    logs = await get_week_logs()
    tasks = await get_tasks(done=False)
    opps = await get_opportunities(done=False)
    summary = await generate_weekly_summary(logs, tasks, opps)
    await update.message.reply_text(f"📊 *Weekly Summary*\n\n{summary}", parse_mode="Markdown")