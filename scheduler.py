"""
KODED OS — Scheduler
Proactive pings: morning standup, task reminders, evening wind-down, weekly summary
"""

import logging
from datetime import datetime, time
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from telegram.ext import Application

from config import (
    MORNING_STANDUP_HOUR, MORNING_STANDUP_MIN,
    EVENING_WINDUP_HOUR, EVENING_WINDUP_MIN,
    WEEKLY_SUMMARY_DAY, WEEKLY_SUMMARY_HOUR
)
from database import get_tasks, get_opportunities, get_week_logs, get_all_users, update_task_reminders_sent, reset_daily_reminders_sent
from gemini import (
    generate_morning_standup, generate_evening_summary,
    generate_weekly_summary, generate_reminder
)

logger = logging.getLogger(__name__)

# Lagos is WAT = UTC+1
TIMEZONE = "Africa/Lagos"


def setup_scheduler(application: Application):
    scheduler = AsyncIOScheduler(timezone=TIMEZONE)

    # Morning standup
    scheduler.add_job(
        morning_standup_all,
        CronTrigger(hour=MORNING_STANDUP_HOUR, minute=MORNING_STANDUP_MIN, timezone=TIMEZONE),
        args=[application],
        id="morning_standup"
    )

    # Evening wind-down
    scheduler.add_job(
        evening_windup_all,
        CronTrigger(hour=EVENING_WINDUP_HOUR, minute=EVENING_WINDUP_MIN, timezone=TIMEZONE),
        args=[application],
        id="evening_windup"
    )

    # Task reminders — check every 5 minutes
    scheduler.add_job(
        check_task_reminders_all,
        CronTrigger(minute="*/5", timezone=TIMEZONE),
        args=[application],
        id="task_reminders"
    )

    # Midnight reset — clear reminder flags so tasks fire again next day
    scheduler.add_job(
        reset_all_reminders,
        CronTrigger(hour=0, minute=0, timezone=TIMEZONE),
        id="midnight_reset"
    )

    # Opportunity deadline check — 10am daily
    scheduler.add_job(
        check_opportunity_deadlines_all,
        CronTrigger(hour=10, minute=0, timezone=TIMEZONE),
        args=[application],
        id="opportunity_check"
    )

    # Weekly summary — Sunday
    scheduler.add_job(
        weekly_summary_all,
        CronTrigger(
            day_of_week=WEEKLY_SUMMARY_DAY,
            hour=WEEKLY_SUMMARY_HOUR,
            minute=0,
            timezone=TIMEZONE
        ),
        args=[application],
        id="weekly_summary"
    )

    # Weekly opportunity discovery — Monday 9am
    scheduler.add_job(
        discover_opps_all,
        CronTrigger(day_of_week="mon", hour=9, minute=0, timezone=TIMEZONE),
        args=[application],
        id="opp_discovery"
    )

    scheduler.start()
    logger.info("⏰ Scheduler started — all jobs armed.")


async def _send(application: Application, user_id: int, text: str, parse_mode: str = "Markdown"):
    """Send a message to a specific user."""
    try:
        await application.bot.send_message(
            chat_id=user_id,
            text=text,
            parse_mode=parse_mode
        )
    except Exception as e:
        logger.error(f"Failed to send scheduled message to {user_id}: {e}")


async def morning_standup_all(application: Application):
    logger.info("Triggering morning standup for all users...")
    users = await get_all_users()
    for user in users:
        if not user.get("onboarding_complete") or not user.get("morning_standup", 1):
            continue
        user_id = user["user_id"]
        message = await generate_morning_standup(user_id)
        await _send(application, user_id, f"☀️ *Morning Standup*\n\n{message}")


async def evening_windup_all(application: Application):
    logger.info("Triggering evening wind-down for all users...")
    users = await get_all_users()
    for user in users:
        if not user.get("onboarding_complete") or not user.get("evening_summary", 1):
            continue
        user_id = user["user_id"]
        tasks = await get_tasks(user_id, done=False)
        all_tasks = await get_tasks(user_id, done=True) + tasks
        logs = await get_week_logs(user_id)
        message = await generate_evening_summary(user_id, all_tasks, logs)
        await _send(application, user_id, f"🌙 *Evening Wind-Down*\n\n{message}")


# (min_before, max_before, level_key, label)
_REMINDER_WINDOWS = [
    (28, 35, "30m", "30m warning"),
    (8,  13, "10m", "10m warning"),
    (-3,  3, "now", "due now"),
]


async def check_task_reminders_all(application: Application):
    """Check task reminders for all users using range windows + dedup tracking."""
    users = await get_all_users()
    now = datetime.now()
    now_total = now.hour * 60 + now.minute

    for user in users:
        if not user.get("onboarding_complete"):
            continue
        user_id = user["user_id"]
        tasks = await get_tasks(user_id, done=False)

        for task in tasks:
            due = task.get("due_time")
            if not due:
                continue
            try:
                due_hour, due_min = map(int, due.split(":"))
                due_total = due_hour * 60 + due_min
                minutes_until = due_total - now_total

                sent = set((task.get("reminders_sent") or "").split())

                for min_lo, min_hi, level, _ in _REMINDER_WINDOWS:
                    if min_lo <= minutes_until <= min_hi and level not in sent:
                        pending = [t for t in tasks if t["id"] != task["id"]]
                        reminder = await generate_reminder(user_id, task, pending, level)
                        await _send(application, user_id, f"⏰ *Task Reminder*\n\n{reminder}")
                        sent.add(level)
                        await update_task_reminders_sent(user_id, task["id"], " ".join(sent))
                        break  # one reminder per task per tick

            except Exception as e:
                logger.error(f"Reminder check error for user {user_id} task {task['id']}: {e}")


async def reset_all_reminders():
    """Midnight: clear reminder sent flags so tasks re-fire the next day."""
    await reset_daily_reminders_sent()
    logger.info("🔄 Daily reminder flags cleared.")


async def discover_opps_all(application: Application):
    """Monday 9am: auto-discover opportunities for all onboarded users."""
    from scraper import fetch_raw_opportunities
    from database import get_opportunity_by_link, add_opportunity
    from gemini import generate_opp_search_queries, filter_and_extract_opportunities

    logger.info("🔍 Running weekly opportunity discovery...")
    users = await get_all_users()

    for user in users:
        if not user.get("onboarding_complete"):
            continue
        user_id = user["user_id"]
        try:
            queries = await generate_opp_search_queries(user_id)
            raw = await fetch_raw_opportunities(queries)
            if not raw:
                continue

            opps = await filter_and_extract_opportunities(user_id, raw)
            added = []

            for opp in opps:
                link = (opp.get("link") or "").rstrip("/")
                if link and await get_opportunity_by_link(user_id, link):
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

            if added:
                lines = [f"🎯 *Weekly Opp Scan — {len(added)} new finds:*\n"]
                for o in added:
                    dl = f" — `{o['deadline']}`" if o.get("deadline") else ""
                    lines.append(f"• `[{o['id']}]` *{o['title']}*{dl}")
                    why = o.get("why_relevant") or ""
                    if why:
                        lines.append(f"  _{why}_")
                lines.append("\n`/apply [id]` to draft your application • `/opps` to view all")
                await _send(application, user_id, "\n".join(lines))

        except Exception as e:
            logger.error(f"Opp discovery failed for user {user_id}: {e}")


async def check_opportunity_deadlines_all(application: Application):
    """Alert about opportunities with deadlines in the next 7 days for all users."""
    from datetime import date, timedelta
    users = await get_all_users()
    today = date.today()
    for user in users:
        if not user.get("onboarding_complete"):
            continue
        user_id = user["user_id"]
        opps = await get_opportunities(user_id, done=False)
        urgent = []
        for opp in opps:
            if not opp.get("deadline"):
                continue
            try:
                deadline = datetime.strptime(opp["deadline"], "%Y-%m-%d").date()
                days_left = (deadline - today).days
                if 0 <= days_left <= 7:
                    urgent.append((opp, days_left))
            except Exception:
                continue
        if urgent:
            lines = ["🚨 *Upcoming Deadlines*\n"]
            for opp, days_left in sorted(urgent, key=lambda x: x[1]):
                label = "TODAY ‼️" if days_left == 0 else "tomorrow ⚠️" if days_left == 1 else f"in {days_left} days"
                lines.append(f"• *{opp['title']}* — {label}")
            lines.append("\nDon't sleep on these 👀")
            await _send(application, user_id, "\n".join(lines))


async def weekly_summary_all(application: Application):
    logger.info("Triggering weekly summary for all users...")
    users = await get_all_users()
    for user in users:
        if not user.get("onboarding_complete"):
            continue
        user_id = user["user_id"]
        logs = await get_week_logs(user_id)
        tasks = await get_tasks(user_id, done=False)
        opps = await get_opportunities(user_id, done=False)
        summary = await generate_weekly_summary(user_id, logs, tasks, opps)
        await _send(application, user_id, f"📊 *Weekly Summary — Week Recap*\n\n{summary}")