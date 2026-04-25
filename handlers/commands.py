"""
KODED OS — Command Handlers
Full CRUD for tasks and opportunities, detail views, smart opp parsing
"""

import re
from datetime import date, datetime
from telegram import Update
from telegram.ext import ContextTypes
from database import (
    get_tasks, get_task_by_id, add_task, update_task, delete_task, mark_task_done,
    get_opportunities, get_opportunity_by_id, add_opportunity, update_opportunity,
    delete_opportunity, mark_opportunity_done, clear_tasks, get_week_logs,
    upsert_user, get_user
)
from gemini import generate_weekly_summary, parse_opportunity_from_text

TRACK_EMOJI = {
    "skurel": "💼", "teenovatex": "🔬", "stackd": "🎓", "setld": "🏠",
    "unilag": "📚", "microsoft": "🏢", "mca": "🎨", "echobridge": "♿",
    "hsil": "🏥", "personal": "👤", "general": "📌"
}
TYPE_EMOJI = {
    "hackathon": "🏆", "internship": "🏢", "deadline": "⏰",
    "event": "📅", "grant": "💰", "competition": "🥇", "general": "📌"
}


# ── /start ─────────────────────────────────────────────────────────────────

async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await upsert_user(user.id, username=user.username)
    
    msg = f"""🧠 *KODED OS — Online*

Welcome {user.first_name}. Your personal AI chief of staff is live.

📸 Snap your task list → I read + schedule reminders
🎙️ Voice note → transcribed + logged
💬 Text anything → tasks, opps, updates
⏰ Proactive pings throughout the day

*Customization:*
/settings [text] — Configure how I behave or sound. 
Example: `/settings You are JARVIS from Ironman. Be formal and call me Sir.`

*Task commands:*
/tasks — view active tasks
/task [id] — view task details
/done [id] — mark task done
/edit [id] [text] — edit a task
/del [id] — delete a task
/clear — wipe all active tasks

*Opportunity commands:*
/opps — view all opportunities
/opp [id] — view opportunity details
/addobp [paste opp text] — AI parses deadline + details
/dopp [id] — mark opportunity done
/delopp [id] — delete an opportunity

*Other:*
/summary — weekly AI summary
/help — full usage guide"""
    await update.message.reply_text(msg, parse_mode="Markdown")


# ── /settings ──────────────────────────────────────────────────────────────

async def settings_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not context.args:
        user = await get_user(user_id)
        current_context = user.get("context") if user else "Not set (using default Koded context)"
        msg = f"""⚙️ *Your AI Settings*

*Current Behavior/Context:*
{current_context}

To change how I behave or sound, use:
`/settings [your instructions here]`

Example:
`/settings You are a pirate assistant. End every sentence with Arrr!`"""
        await update.message.reply_text(msg, parse_mode="Markdown")
        return

    new_context = " ".join(context.args)
    await upsert_user(user_id, context=new_context)
    await update.message.reply_text("✅ Settings updated. I'll behave as you requested from now on.", parse_mode="Markdown")


# ── /help ──────────────────────────────────────────────────────────────────

async def help_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = """*KODED OS — Full Guide*

*➕ Adding tasks:*
• Snap a photo of your list 📸
• Voice note 🎙️
• Type: `fix farmIntel bug at 3pm skurel`
• Text naturally: "I need to prep Stackd session by 6"

*✅ Managing tasks:*
• `/tasks` — list all active tasks
• `/task 3` — full details of task #3
• `/done 3` — mark #3 complete
• `/edit 3 new task title at 5pm` — edit task #3
• `/del 3` — delete task #3
• `/clear` — wipe all active tasks

*🎯 Adding opportunities:*
• `/addobp` followed by pasted opp text — AI extracts everything
• Natural text: "ETH Lagos hackathon, deadline June 15"
• With link: "Microsoft SIWES apply by May 30 https://..."

*📋 Managing opportunities:*
• `/opps` — list all open opps
• `/opp 2` — full details of opp #2
• `/dopp 2` — mark opp #2 as applied/done
• `/delopp 2` — delete opp #2
• `/editopp 2 deadline 2026-06-15` — update deadline
• `/editopp 2 notes application submitted` — update notes

*⏰ Reminders:*
• `/remindme in 10 minutes check Skurel PR`
• `/remindme in 2 hours HSIL sync`
• Or just say "remind me in 30 mins to push that fix"

*📊 Summaries:*
• `/summary` — generate weekly summary now

Standup: 7:30am | Wind-down: 9pm | Weekly: Sunday 8pm 🦾"""
    await update.message.reply_text(msg, parse_mode="Markdown")


# ── TASK COMMANDS ──────────────────────────────────────────────────────────

async def tasks_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """List all active tasks."""
    user_id = update.effective_user.id
    tasks = await get_tasks(user_id, done=False)
    if not tasks:
        await update.message.reply_text("✅ No active tasks. Drop your list and let's get moving.")
        return

    lines = [f"📋 *Active Tasks* ({len(tasks)})\n"]
    for t in tasks:
        emoji = TRACK_EMOJI.get(t["track"], "📌")
        time_str = f" `{t['due_time']}`" if t["due_time"] else ""
        lines.append(f"{emoji} `[{t['id']}]` {t['title']}{time_str}")

    lines.append(f"\n_/task [id] for details • /done [id] to complete_")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def task_detail_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/task [id] — view full task details."""
    user_id = update.effective_user.id
    args = context.args
    if not args or not args[0].isdigit():
        await update.message.reply_text("Usage: `/task 3`", parse_mode="Markdown")
        return

    task = await get_task_by_id(user_id, int(args[0]))
    if not task:
        await update.message.reply_text(f"❌ No task with ID `{args[0]}`", parse_mode="Markdown")
        return

    emoji = TRACK_EMOJI.get(task["track"], "📌")
    status = "✅ Done" if task["done"] else "🔄 Active"
    msg = f"""{emoji} *Task #{task['id']}*

*Title:* {task['title']}
*Track:* {task['track'].title()}
*Status:* {status}
*Due:* {task['due_time'] or 'No time set'}
*Notes:* {task['notes'] or 'None'}
*Created:* {task['created_at'][:16]}

_/done {task['id']} • /edit {task['id']} [new title] • /del {task['id']}_"""
    await update.message.reply_text(msg, parse_mode="Markdown")


async def done_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/done [id] — mark task complete."""
    user_id = update.effective_user.id
    args = context.args
    if not args or not args[0].isdigit():
        await update.message.reply_text("Usage: `/done 3`", parse_mode="Markdown")
        return

    task = await get_task_by_id(user_id, int(args[0]))
    if not task:
        await update.message.reply_text(f"❌ No task with ID `{args[0]}`", parse_mode="Markdown")
        return

    await mark_task_done(user_id, int(args[0]))
    await update.message.reply_text(f"✅ Done: _{task['title']}_\n\nOne down. Keep going.", parse_mode="Markdown")


async def edit_task_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/edit [id] [new title/time] — edit a task."""
    user_id = update.effective_user.id
    args = context.args
    if not args or not args[0].isdigit() or len(args) < 2:
        await update.message.reply_text("Usage: `/edit 3 push farmIntel fix at 4pm`", parse_mode="Markdown")
        return

    task_id = int(args[0])
    new_text = " ".join(args[1:])

    task = await get_task_by_id(user_id, task_id)
    if not task:
        await update.message.reply_text(f"❌ No task with ID `{task_id}`", parse_mode="Markdown")
        return

    # Extract time if present
    time_match = re.search(r'at (\d{1,2})(?::(\d{2}))?\s*(am|pm)?', new_text, re.IGNORECASE)
    due_time = None
    title = new_text

    if time_match:
        hour = int(time_match.group(1))
        minute = int(time_match.group(2) or 0)
        period = (time_match.group(3) or "").lower()
        if period == "pm" and hour != 12:
            hour += 12
        elif period == "am" and hour == 12:
            hour = 0
        due_time = f"{hour:02d}:{minute:02d}"
        title = new_text[:time_match.start()].strip()

    await update_task(user_id, task_id, title=title or task["title"], due_time=due_time or task["due_time"])
    await update.message.reply_text(f"✏️ Task `{task_id}` updated:\n_{title or task['title']}_" + (f"\nTime: `{due_time}`" if due_time else ""), parse_mode="Markdown")


async def delete_task_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/del [id] — delete a task."""
    user_id = update.effective_user.id
    args = context.args
    if not args or not args[0].isdigit():
        await update.message.reply_text("Usage: `/del 3`", parse_mode="Markdown")
        return

    task = await get_task_by_id(user_id, int(args[0]))
    if not task:
        await update.message.reply_text(f"❌ No task with ID `{args[0]}`", parse_mode="Markdown")
        return

    await delete_task(user_id, int(args[0]))
    await update.message.reply_text(f"🗑️ Deleted: _{task['title']}_", parse_mode="Markdown")


async def clear_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    await clear_tasks(user_id)
    await update.message.reply_text("🗑️ All active tasks cleared. Fresh slate.")


# ── OPPORTUNITY COMMANDS ───────────────────────────────────────────────────

async def opportunities_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """List all open opportunities."""
    user_id = update.effective_user.id
    opps = await get_opportunities(user_id, done=False)
    if not opps:
        await update.message.reply_text("🎯 No opportunities tracked. Use /addobp [paste opp text] to add one.")
        return

    today = date.today()
    lines = [f"🎯 *Opportunities* ({len(opps)})\n"]
    for o in opps:
        emoji = TYPE_EMOJI.get(o["type"], "📌")
        if o["deadline"]:
            try:
                dl = datetime.strptime(o["deadline"], "%Y-%m-%d").date()
                days_left = (dl - today).days
                if days_left < 0:
                    dl_str = f" `OVERDUE`"
                elif days_left == 0:
                    dl_str = f" `TODAY ‼️`"
                elif days_left <= 3:
                    dl_str = f" `{days_left}d left ⚠️`"
                else:
                    dl_str = f" `{o['deadline']} ({days_left}d)`"
            except:
                dl_str = f" `{o['deadline']}`"
        else:
            dl_str = ""
        lines.append(f"{emoji} `[{o['id']}]` {o['title']}{dl_str}")

    lines.append(f"\n_/opp [id] for details • /dopp [id] to mark done_")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def opp_detail_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/opp [id] — full opportunity details."""
    user_id = update.effective_user.id
    args = context.args
    if not args or not args[0].isdigit():
        await update.message.reply_text("Usage: `/opp 2`", parse_mode="Markdown")
        return

    opp = await get_opportunity_by_id(user_id, int(args[0]))
    if not opp:
        await update.message.reply_text(f"❌ No opportunity with ID `{args[0]}`", parse_mode="Markdown")
        return

    emoji = TYPE_EMOJI.get(opp["type"], "📌")
    status = "✅ Done/Applied" if opp["done"] else "🔄 Open"

    # Days left
    days_str = ""
    if opp["deadline"]:
        try:
            dl = datetime.strptime(opp["deadline"], "%Y-%m-%d").date()
            days_left = (dl - date.today()).days
            if days_left < 0:
                days_str = " *(OVERDUE)*"
            elif days_left == 0:
                days_str = " *(TODAY ‼️)*"
            else:
                days_str = f" *({days_left} days left)*"
        except:
            pass

    msg = f"""{emoji} *Opportunity #{opp['id']}*

*Title:* {opp['title']}
*Type:* {opp['type'].title()}
*Status:* {status}
*Deadline:* {opp['deadline'] or 'Not set'}{days_str}
*Link:* {opp['link'] or 'None'}
*Notes:* {opp['notes'] or 'None'}
*Added:* {opp['created_at'][:16]}

_/dopp {opp['id']} • /editopp {opp['id']} • /delopp {opp['id']}_"""
    await update.message.reply_text(msg, parse_mode="Markdown")


async def add_opp_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/addobp [paste any opp text] — AI parses everything."""
    user_id = update.effective_user.id
    text = " ".join(context.args) if context.args else ""

    # Also check message caption or reply
    if not text and update.message.text:
        text = update.message.text.replace("/addobp", "").strip()

    if not text:
        await update.message.reply_text(
            "Paste the opportunity text after /addobp:\n\n"
            "`/addobp ETH Lagos Hackathon — Build on Ethereum, win $5k. Deadline: June 15 2026. Apply at ethlagos.io`",
            parse_mode="Markdown"
        )
        return

    await update.message.reply_text("🔍 Parsing opportunity...")
    result = await parse_opportunity_from_text(user_id, text)

    opp_id = await add_opportunity(
        user_id=user_id,
        title=result.get("title", text[:80]),
        opp_type=result.get("type", "general"),
        deadline=result.get("deadline"),
        notes=result.get("notes"),
        link=result.get("link")
    )

    emoji = TYPE_EMOJI.get(result.get("type", "general"), "📌")
    msg = f"""{emoji} *Opportunity logged! #{opp_id}*

*Title:* {result.get('title', 'N/A')}
*Type:* {result.get('type', 'general').title()}
*Deadline:* {result.get('deadline') or 'Not found — update with /editopp'}
*Link:* {result.get('link') or 'None'}
*Notes:* {result.get('notes') or 'None'}

_/opp {opp_id} to view • /editopp {opp_id} deadline YYYY-MM-DD to fix deadline_"""
    await update.message.reply_text(msg, parse_mode="Markdown")


async def done_opp_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/dopp [id] — mark opportunity as applied/done."""
    user_id = update.effective_user.id
    args = context.args
    if not args or not args[0].isdigit():
        await update.message.reply_text("Usage: `/dopp 2`", parse_mode="Markdown")
        return

    opp = await get_opportunity_by_id(user_id, int(args[0]))
    if not opp:
        await update.message.reply_text(f"❌ No opportunity with ID `{args[0]}`", parse_mode="Markdown")
        return

    await mark_opportunity_done(user_id, int(args[0]))
    await update.message.reply_text(f"✅ Marked as done: _{opp['title']}_\n\nShot your shot. Respect.", parse_mode="Markdown")


async def delete_opp_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/delopp [id] — delete an opportunity."""
    user_id = update.effective_user.id
    args = context.args
    if not args or not args[0].isdigit():
        await update.message.reply_text("Usage: `/delopp 2`", parse_mode="Markdown")
        return

    opp = await get_opportunity_by_id(user_id, int(args[0]))
    if not opp:
        await update.message.reply_text(f"❌ No opportunity with ID `{args[0]}`", parse_mode="Markdown")
        return

    await delete_opportunity(user_id, int(args[0]))
    await update.message.reply_text(f"🗑️ Deleted: _{opp['title']}_", parse_mode="Markdown")


async def edit_opp_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/editopp [id] [field] [value] — update a specific field.
    Fields: deadline, notes, link, title, type
    Example: /editopp 2 deadline 2026-06-15
             /editopp 2 notes submitted via portal
             /editopp 2 link https://apply.microsoft.com
    """
    user_id = update.effective_user.id
    args = context.args
    if not args or not args[0].isdigit() or len(args) < 3:
        await update.message.reply_text(
            "Usage:\n`/editopp 2 deadline 2026-06-15`\n`/editopp 2 notes submitted via portal`\n`/editopp 2 link https://...`",
            parse_mode="Markdown"
        )
        return

    opp_id = int(args[0])
    field = args[1].lower()
    value = " ".join(args[2:])

    allowed_fields = {"deadline", "notes", "link", "title", "type"}
    if field not in allowed_fields:
        await update.message.reply_text(f"❌ Unknown field `{field}`. Use: deadline, notes, link, title, type", parse_mode="Markdown")
        return

    opp = await get_opportunity_by_id(user_id, opp_id)
    if not opp:
        await update.message.reply_text(f"❌ No opportunity with ID `{opp_id}`", parse_mode="Markdown")
        return

    await update_opportunity(user_id, opp_id, **{field: value})
    await update.message.reply_text(f"✏️ Opp `{opp_id}` updated:\n*{field}* → `{value}`", parse_mode="Markdown")


# ── /summary ───────────────────────────────────────────────────────────────

async def summary_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    await update.message.reply_text("⏳ Generating your weekly summary...")
    logs = await get_week_logs(user_id)
    tasks = await get_tasks(user_id, done=False)
    opps = await get_opportunities(user_id, done=False)
    summary = await generate_weekly_summary(user_id, logs, tasks, opps)
    await update.message.reply_text(f"📊 *Weekly Summary*\n\n{summary}", parse_mode="Markdown")