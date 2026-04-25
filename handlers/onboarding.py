"""
KODED OS — Onboarding Flow
New user setup: name → AI-generated profile → personality choice
"""

from telegram import Update
from telegram.ext import ContextTypes
from database import get_user, upsert_user

AI_PROMPT_TEMPLATE = """Here's a prompt — copy it into any AI (ChatGPT, Claude, Gemini, whatever you use):

─────────────────────────────
I'm setting up a personal AI chief of staff on Telegram. Write a comprehensive third-person profile about me for it to use as context.

My name is {name}.

[Fill in details about yourself below, then delete this line:]
• What you do — job, studies, projects
• Your active commitments and responsibilities
• Your goals and what you're working toward
• Your typical schedule / weekly commitments
• How you work — your style, pace, personality

Write it as 2–3 detailed paragraphs in third person. Be specific — the more detail, the more useful the bot will be.
─────────────────────────────

Paste the result back here and I'll get you fully set up. 🧠"""

PERSONALITY_PROMPT = """Last step — how should I talk to you?

Reply with a number:

*1.* Casual & direct _(default — smart friend energy)_
*2.* Formal & professional _(precise, structured)_
*3.* Brutally honest _(no sugarcoating, real talk)_
*4.* Hype mode _(high energy, always pumping you up)_

Or just type *skip* to go with the default."""

_PERSONALITY_MAP = {"1": "casual", "2": "formal", "3": "honest", "4": "hype"}
_PERSONALITY_LABELS = {
    "casual": "casual & direct",
    "formal": "formal & professional",
    "honest": "brutally honest",
    "hype": "hype mode",
}


async def handle_onboarding(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """
    Returns True if message was consumed by onboarding (caller should not process further).
    Returns False if user is fully onboarded and message should proceed normally.
    """
    user_id = update.effective_user.id
    text = (update.message.text or "").strip()

    user = await get_user(user_id)

    if not user:
        # First ever message — register and start onboarding
        await upsert_user(user_id, username=update.effective_user.username, onboarding_step=1)
        await update.message.reply_text(
            "👋 Hey! I'm *KODED OS* — your personal AI chief of staff.\n\nWhat's your name?",
            parse_mode="Markdown"
        )
        return True

    if user.get("onboarding_complete"):
        return False

    step = user.get("onboarding_step", 0)

    if step == 0:
        # Registered but /start was never properly called
        await upsert_user(user_id, onboarding_step=1)
        await update.message.reply_text(
            "👋 Hey! I'm *KODED OS* — your personal AI chief of staff.\n\nWhat's your name?",
            parse_mode="Markdown"
        )
        return True

    if step == 1:
        await _receive_name(update, user_id, text)
        return True

    if step == 2:
        await _receive_bio(update, user_id, text)
        return True

    if step == 3:
        await _receive_personality(update, user_id, text)
        return True

    return False


async def _receive_name(update: Update, user_id: int, text: str):
    name = text.strip().split()[0] if text.strip() else ""
    if not name or len(name) < 2:
        await update.message.reply_text("Hmm, that doesn't look like a name. What should I call you?")
        return

    # Capitalize properly
    name = name.capitalize()
    await upsert_user(user_id, name=name, onboarding_step=2)

    prompt = AI_PROMPT_TEMPLATE.format(name=name)
    await update.message.reply_text(
        f"Nice to meet you, *{name}!* 🤝\n\n"
        f"To set me up right, I need the full picture of who you are.\n\n"
        f"{prompt}",
        parse_mode="Markdown"
    )


async def _receive_bio(update: Update, user_id: int, bio_text: str):
    if len(bio_text) < 60:
        await update.message.reply_text(
            "That's a bit short — I need more context to be useful.\n\n"
            "Use the AI prompt above to generate a detailed profile, then paste it here."
        )
        return

    await upsert_user(user_id, bio_text=bio_text, onboarding_step=3)

    user = await get_user(user_id)
    name = user.get("name", "")

    await update.message.reply_text(
        f"Profile saved, *{name}!* 🧠\n\n"
        f"I now know who you are and what you're working on. "
        f"I'll use this for everything — reminders, summaries, daily standups.\n\n"
        + PERSONALITY_PROMPT,
        parse_mode="Markdown"
    )


async def _receive_personality(update: Update, user_id: int, text: str):
    choice = text.strip().lower()

    if choice in ("skip", "default", "/skip"):
        personality = "casual"
    else:
        personality = _PERSONALITY_MAP.get(choice[:1], "casual")

    await upsert_user(user_id, bot_personality=personality, onboarding_complete=1, onboarding_step=4)

    user = await get_user(user_id)
    name = user.get("name", "there")
    label = _PERSONALITY_LABELS.get(personality, "casual & direct")

    await update.message.reply_text(
        f"Done! I'll keep it *{label}*, {name}. 🔥\n\n"
        f"You're all set. Use /settings anytime to update your profile or preferences.\n\n"
        f"Now — drop your tasks, snap your list, or send a voice note. Let's get to work.",
        parse_mode="Markdown"
    )
