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
    ALLOWED_USER_ID,
    MORNING_STANDUP_HOUR, MORNING_STANDUP_MIN,
    EVENING_WINDUP_HOUR, EVENING_WINDUP_MIN,
    WEEKLY_SUMMARY_DAY, WEEKLY_SUMMARY_HOUR
)
from database import get_tasks, get_opportunities, get_week_logs
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
        morning_standup,
        CronTrigger(hour=MORNING_STANDUP_HOUR, minute=MORNING_STANDUP_MIN, timezone=TIMEZONE),
        args=[application],
        id="morning_standup"
    )

    # Evening wind-down
    scheduler.add_job(
        evening_windup,
        CronTrigger(hour=EVENING_WINDUP_HOUR, minute=EVENING_WINDUP_MIN, timezone=TIMEZONE),
        args=[application],
        id="evening_windup"
    )

    # Task reminders — check every 5 minutes
    scheduler.add_job(
        check_task_reminders,
        CronTrigger(minute="*/5", timezone=TIMEZONE),
        args=[application],
        id="task_reminders"
    )

    # Opportunity deadline check — 10am daily
    scheduler.add_job(
        check_opportunity_deadlines,
        CronTrigger(hour=10, minute=0, timezone=TIMEZONE),
        args=[application],
        id="opportunity_check"
    )

    # Weekly summary — Sunday
    scheduler.add_job(
        weekly_summary,
        CronTrigger(
            day_of_week=WEEKLY_SUMMARY_DAY,
            hour=WEEKLY_SUMMARY_HOUR,
            minute=0,
            timezone=TIMEZONE
        ),
        args=[application],
        id="weekly_summary"
    )

    scheduler.start()
    logger.info("⏰ Scheduler started — all jobs armed.")


async def _send(application: Application, text: str, parse_mode: str = "Markdown"):
    """Send a message to the owner."""
    if not ALLOWED_USER_ID:
        logger.warning("No ALLOWED_USER_ID set — can't send proactive messages.")
        return
    try:
        await application.bot.send_message(
            chat_id=ALLOWED_USER_ID,
            text=text,
            parse_mode=parse_mode
        )
    except Exception as e:
        logger.error(f"Failed to send scheduled message: {e}")


async def morning_standup(application: Application):
    logger.info("Triggering morning standup...")
    message = await generate_morning_standup()
    await _send(application, f"☀️ *Morning Standup*\n\n{message}")


async def evening_windup(application: Application):
    logger.info("Triggering evening wind-down...")
    tasks = await get_tasks(done=False)
    all_tasks = await get_tasks(done=True) + tasks
    logs = await get_week_logs()
    message = await generate_evening_summary(all_tasks, logs)
    await _send(application, f"🌙 *Evening Wind-Down*\n\n{message}")


async def check_task_reminders(application: Application):
    """Check if any tasks are due within the next 10 minutes and remind."""
    tasks = await get_tasks(done=False)
    now = datetime.now()
    current_time = now.strftime("%H:%M")

    for task in tasks:
        due = task.get("due_time")
        if not due:
            continue

        try:
            due_hour, due_min = map(int, due.split(":"))
            now_hour, now_min = now.hour, now.minute

            # Total minutes from midnight
            due_total = due_hour * 60 + due_min
            now_total = now_hour * 60 + now_min

            # Remind 10 min before due time
            if due_total - now_total == 10:
                pending = [t for t in tasks if t["id"] != task["id"]]
                reminder = await generate_reminder(task, pending)
                await _send(application, f"⏰ *Task Reminder*\n\n{reminder}")

        except Exception as e:
            logger.error(f"Reminder check error for task {task['id']}: {e}")


async def check_opportunity_deadlines(application: Application):
    """Alert about opportunities with deadlines in the next 7 days."""
    from datetime import date, timedelta

    opps = await get_opportunities(done=False)
    today = date.today()
    soon = today + timedelta(days=7)

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

    if not urgent:
        return

    lines = ["🚨 *Upcoming Deadlines*\n"]
    for opp, days_left in sorted(urgent, key=lambda x: x[1]):
        if days_left == 0:
            label = "TODAY ‼️"
        elif days_left == 1:
            label = "tomorrow ⚠️"
        else:
            label = f"in {days_left} days"
        lines.append(f"• *{opp['title']}* — {label}")

    lines.append("\nDon't sleep on these 👀")
    await _send(application, "\n".join(lines))


async def weekly_summary(application: Application):
    logger.info("Triggering weekly summary...")
    logs = await get_week_logs()
    tasks = await get_tasks(done=False)
    opps = await get_opportunities(done=False)
    summary = await generate_weekly_summary(logs, tasks, opps)
    await _send(application, f"📊 *Weekly Summary — Week Recap*\n\n{summary}")