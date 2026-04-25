"""
KODED OS — Command Handlers
Full CRUD for tasks and opportunities, detail views, smart opp parsing
"""

import re
from datetime import date, datetime
from telegram import Update
from telegram.ext import ContextTypes
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from database import (
    get_tasks, get_task_by_id, add_task, update_task, delete_task, mark_task_done,
    get_opportunities, get_opportunity_by_id, add_opportunity, update_opportunity,
    delete_opportunity, mark_opportunity_done, clear_tasks, get_week_logs,
    upsert_user, get_user, get_opportunity_by_link
)
from gemini import (
    generate_weekly_summary, parse_opportunity_from_text,
    generate_opp_search_queries, filter_and_extract_opportunities, generate_application_draft
)

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
    from handlers.onboarding import PERSONALITY_PROMPT
    user = update.effective_user
    db_user = await get_user(user.id)

    if db_user and db_user.get("onboarding_complete"):
        name = db_user.get("name") or user.first_name
        await update.message.reply_text(
            f"🧠 *KODED OS — Online*\n\nWelcome back, {name}. What are we getting done today?",
            parse_mode="Markdown"
        )
        return

    if db_user:
        # Mid-onboarding re-entry — re-prompt the current step
        step = db_user.get("onboarding_step", 0)
        if step == 1:
            await update.message.reply_text("Still here! What's your name? 👋")
        elif step == 2:
            name = db_user.get("name", "")
            from handlers.onboarding import AI_PROMPT_TEMPLATE
            await update.message.reply_text(
                f"Hey {name}! Still waiting for your profile — use the prompt above to generate it and paste it here.",
                parse_mode="Markdown"
            )
        elif step == 3:
            await update.message.reply_text(PERSONALITY_PROMPT, parse_mode="Markdown")
        else:
            await upsert_user(user.id, onboarding_step=1)
            await update.message.reply_text(
                "👋 Hey! I'm *KODED OS* — your personal AI chief of staff.\n\nWhat's your name?",
                parse_mode="Markdown"
            )
        return

    # Brand new user
    await upsert_user(user.id, username=user.username, onboarding_step=1)
    await update.message.reply_text(
        "👋 Hey! I'm *KODED OS* — your personal AI chief of staff.\n\nWhat's your name?",
        parse_mode="Markdown"
    )


# ── /settings ──────────────────────────────────────────────────────────────

_PERSONALITY_LABELS = {
    "casual": "Casual & direct",
    "formal": "Formal & professional",
    "honest": "Brutally honest",
    "hype": "Hype mode",
}


async def settings_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    args = context.args

    if not args:
        user = await get_user(user_id)
        if not user or not user.get("onboarding_complete"):
            await update.message.reply_text("Complete setup first with /start")
            return

        personality = _PERSONALITY_LABELS.get(user.get("bot_personality", "casual"), "Casual & direct")
        standup = "ON" if user.get("morning_standup", 1) else "OFF"
        evening = "ON" if user.get("evening_summary", 1) else "OFF"
        has_bio = "Set ✅" if user.get("bio_text") else "Not set ❌"

        await update.message.reply_text(
            f"⚙️ *Your Settings*\n\n"
            f"*Personality:* {personality}\n"
            f"*Morning standup:* {standup}\n"
            f"*Evening summary:* {evening}\n"
            f"*Profile bio:* {has_bio}\n\n"
            f"*Change anything:*\n"
            f"`/settings personality casual|formal|honest|hype`\n"
            f"`/settings standup on|off`\n"
            f"`/settings evening on|off`\n"
            f"`/settings bio [paste new profile here]`\n"
            f"`/settings context [custom AI instructions]`",
            parse_mode="Markdown"
        )
        return

    subcommand = args[0].lower()

    if subcommand == "personality":
        valid = ("casual", "formal", "honest", "hype")
        if len(args) < 2 or args[1].lower() not in valid:
            await update.message.reply_text(
                "Usage: `/settings personality casual|formal|honest|hype`", parse_mode="Markdown"
            )
            return
        p = args[1].lower()
        await upsert_user(user_id, bot_personality=p)
        await update.message.reply_text(
            f"✅ Personality set to *{_PERSONALITY_LABELS[p]}*", parse_mode="Markdown"
        )

    elif subcommand == "standup":
        if len(args) < 2 or args[1].lower() not in ("on", "off"):
            await update.message.reply_text("Usage: `/settings standup on|off`", parse_mode="Markdown")
            return
        val = 1 if args[1].lower() == "on" else 0
        await upsert_user(user_id, morning_standup=val)
        await update.message.reply_text(
            f"✅ Morning standup *{'ON' if val else 'OFF'}*", parse_mode="Markdown"
        )

    elif subcommand == "evening":
        if len(args) < 2 or args[1].lower() not in ("on", "off"):
            await update.message.reply_text("Usage: `/settings evening on|off`", parse_mode="Markdown")
            return
        val = 1 if args[1].lower() == "on" else 0
        await upsert_user(user_id, evening_summary=val)
        await update.message.reply_text(
            f"✅ Evening summary *{'ON' if val else 'OFF'}*", parse_mode="Markdown"
        )

    elif subcommand == "bio":
        new_bio = " ".join(args[1:]).strip()
        if not new_bio:
            await update.message.reply_text(
                "Paste your new profile after the command:\n"
                "`/settings bio [your AI-generated profile text here]`",
                parse_mode="Markdown"
            )
            return
        if len(new_bio) < 60:
            await update.message.reply_text(
                "That's too short — paste the full AI-generated profile for best results."
            )
            return
        await upsert_user(user_id, bio_text=new_bio)
        await update.message.reply_text("✅ Profile updated. I'll use this from now on.", parse_mode="Markdown")

    elif subcommand == "context":
        new_context = " ".join(args[1:]).strip()
        if not new_context:
            await update.message.reply_text(
                "Usage: `/settings context [custom AI instructions]`", parse_mode="Markdown"
            )
            return
        await upsert_user(user_id, context=new_context)
        await update.message.reply_text(
            "✅ Custom AI instructions saved. This overrides your profile.", parse_mode="Markdown"
        )

    else:
        # Legacy: treat all args as a custom context override
        new_context = " ".join(args)
        await upsert_user(user_id, context=new_context)
        await update.message.reply_text("✅ Settings updated.", parse_mode="Markdown")


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


# ── /findopps ──────────────────────────────────────────────────────────────

async def findopps_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/findopps — discover opportunities based on user profile."""
    from scraper import fetch_raw_opportunities

    user_id = update.effective_user.id
    user = await get_user(user_id)

    if not user or not user.get("onboarding_complete"):
        await update.message.reply_text("Complete setup first with /start")
        return

    await update.message.reply_text("🔍 Scanning for opportunities relevant to you...")

    queries = await generate_opp_search_queries(user_id)
    raw = await fetch_raw_opportunities(queries)

    if not raw:
        await update.message.reply_text("😔 Couldn't fetch results right now. Try again in a bit.")
        return

    await update.message.reply_text(f"⚙️ Got {len(raw)} results — filtering for what's relevant to you...")

    opps = await filter_and_extract_opportunities(user_id, raw)

    if not opps:
        await update.message.reply_text(
            "Nothing that matches your profile this round. I'll keep scanning — check back later or run /findopps again."
        )
        return

    # Add to DB, skip duplicates by link
    added = []
    skipped = 0
    for opp in opps:
        link = (opp.get("link") or "").rstrip("/")
        if link and await get_opportunity_by_link(user_id, link):
            skipped += 1
            continue
        opp_id = await add_opportunity(
            user_id=user_id,
            title=opp.get("title", "Untitled"),
            opp_type=opp.get("type", "general"),
            deadline=opp.get("deadline"),
            notes=opp.get("notes"),
            link=link or None,
            auto_discovered=1,
        )
        added.append({**opp, "id": opp_id})

    if not added:
        skip_note = f" ({skipped} already in your list)" if skipped else ""
        await update.message.reply_text(f"No new opportunities found this round{skip_note}.")
        return

    lines = [f"🎯 *{len(added)} new opportunities found:*\n"]
    for o in added:
        emoji = TYPE_EMOJI.get(o.get("type", "general"), "📌")
        dl = f" — `{o['deadline']}`" if o.get("deadline") else ""
        lines.append(f"{emoji} `[{o['id']}]` *{o['title']}*{dl}")
        why = o.get("why_relevant") or o.get("notes", "")
        if why:
            lines.append(f"   _{why}_\n")

    if skipped:
        lines.append(f"\n_{skipped} already in your list, skipped._")
    lines.append("\n`/apply [id]` — get a personalized draft + checklist for any of these")
    lines.append("`/opp [id]` — view details")

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


# ── /apply ─────────────────────────────────────────────────────────────────

async def apply_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/apply [opp_id] — generate personalized application draft + checklist."""
    user_id = update.effective_user.id
    args = context.args

    if not args or not args[0].isdigit():
        await update.message.reply_text("Usage: `/apply 3`", parse_mode="Markdown")
        return

    opp = await get_opportunity_by_id(user_id, int(args[0]))
    if not opp:
        await update.message.reply_text(f"❌ No opportunity with ID `{args[0]}`", parse_mode="Markdown")
        return

    await update.message.reply_text("✍️ Drafting your application...")

    draft = await generate_application_draft(user_id, opp)

    # Create a task so it's on their list
    task_title = f"Apply: {opp['title']}"
    await add_task(user_id=user_id, title=task_title, track="general")

    checklist = "\n".join([f"☐ {item}" for item in draft.get("checklist", [])])
    tips = "\n".join([f"• {tip}" for tip in draft.get("tips", [])])
    deadline_line = f"*Deadline:* `{opp['deadline']}`\n" if opp.get("deadline") else ""

    msg = (
        f"✍️ *Application: {opp['title']}*\n"
        f"{deadline_line}"
        f"\n*Cover Letter / Intro:*\n{draft.get('cover_letter', '')}\n"
        f"\n*Checklist:*\n{checklist}\n"
        f"\n*Tips to stand out:*\n{tips}\n"
        f"\n_Task added: \"{task_title}\" — /done when submitted._"
    )

    # Inline button to open application link directly
    keyboard = None
    if opp.get("link"):
        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("Apply Now 🚀", url=opp["link"])]])

    try:
        await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=keyboard)
    except Exception:
        await update.message.reply_text(msg, reply_markup=keyboard)