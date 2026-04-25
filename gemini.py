"""
KODED OS — Gemini AI Layer
Multi-key rotation: automatically switches to next key on 429 rate limit.
"""

import json
import logging
import re
from datetime import datetime
import google.generativeai as genai
from config import GEMINI_API_KEYS, GEMINI_MODEL, KODED_CONTEXT

logger = logging.getLogger(__name__)

# ── Key rotation state ─────────────────────────────────────────────────────

_current_key_index = 0


def _get_model():
    """Configure Gemini with current key and return model instance."""
    global _current_key_index
    key = GEMINI_API_KEYS[_current_key_index]
    genai.configure(api_key=key)
    return genai.GenerativeModel(GEMINI_MODEL)


def _rotate_key():
    """Switch to next available API key."""
    global _current_key_index
    _current_key_index = (_current_key_index + 1) % len(GEMINI_API_KEYS)
    logger.info(f"🔄 Rotated to Gemini key #{_current_key_index + 1}")


def _generate(prompt, extra_parts=None) -> str:
    """
    Core generation function with automatic key rotation on 429.
    extra_parts: list of image/audio parts to include alongside prompt.
    """
    for attempt in range(len(GEMINI_API_KEYS)):
        try:
            model = _get_model()
            if extra_parts:
                response = model.generate_content([prompt] + extra_parts)
            else:
                response = model.generate_content(prompt)
            return response.text
        except Exception as e:
            if "429" in str(e) or "quota" in str(e).lower():
                logger.warning(f"Key #{_current_key_index + 1} rate limited. Rotating...")
                _rotate_key()
                continue
            logger.error(f"Gemini error: {e}")
            raise e
    return "⚠️ All Gemini keys are rate limited right now. Try again in a bit."


# ── Helpers ────────────────────────────────────────────────────────────────

def _clean_json(text: str) -> str:
    """Strip markdown code fences from Gemini JSON responses."""
    text = re.sub(r"```(?:json)?", "", text)
    return text.strip().strip("`").strip()


def _get_date_context() -> str:
    """Inject current date/time so Gemini never hallucinates dates."""
    now = datetime.now()
    return f"""
CURRENT DATE & TIME: {now.strftime("%A, %B %d, %Y")} | {now.strftime("%I:%M %p")} (Lagos WAT, UTC+1)
CURRENT YEAR: {now.year}
When parsing dates or times, always use this as your reference. Never guess or assume dates.
"""


def _generate_json(prompt, extra_parts=None) -> dict:
    """Generate and parse JSON response, with key rotation built in."""
    for attempt in range(len(GEMINI_API_KEYS)):
        try:
            model = _get_model()
            if extra_parts:
                response = model.generate_content([prompt] + extra_parts)
            else:
                response = model.generate_content(prompt)
            cleaned = _clean_json(response.text)
            return json.loads(cleaned)
        except json.JSONDecodeError as e:
            logger.error(f"JSON parse error: {e}")
            return {}
        except Exception as e:
            if "429" in str(e) or "quota" in str(e).lower():
                logger.warning(f"Key #{_current_key_index + 1} rate limited. Rotating...")
                _rotate_key()
                continue
            logger.error(f"Gemini error: {e}")
            return {}
    return {}


# ── Public API ─────────────────────────────────────────────────────────────

async def chat_with_gemini(user_message: str, extra_context: str = "") -> str:
    """General chat — handles task logging, questions, freeform input."""
    prompt = f"""{KODED_CONTEXT}

{_get_date_context()}

{extra_context}

USER MESSAGE:
{user_message}

Respond naturally as KODED OS. If the message contains tasks or to-dos, acknowledge them and confirm you've noted them.
Keep it conversational and punchy. No markdown headers in replies — just clean text with occasional emojis."""

    try:
        return _generate(prompt)
    except Exception:
        return "⚠️ Gemini had a moment. Try again in a sec."


async def parse_task_list_from_image(image_bytes: bytes, mime_type: str = "image/jpeg") -> dict:
    """
    Takes a photo of a task list and returns structured JSON.
    """
    prompt = f"""{KODED_CONTEXT}

{_get_date_context()}

Koded just snapped a photo of his task list for today.

Extract ALL tasks you can see. For each task:
1. Identify which of his tracks it belongs to: skurel, teenovatex, stackd, setld, unilag, microsoft, mca, echobridge, hsil, personal, general
2. If a time is mentioned or implied, extract it as HH:MM (24h format)
3. If no time, set due_time to null

Also give:
- A brief "summary" of what kind of day this is shaping up to be
- A "vibe_check" — a short hype/roast about the workload (be real with him)

Return ONLY valid JSON. No explanation, no markdown fences:
{{
    "tasks": [
        {{"title": "task name", "track": "track_name", "due_time": "HH:MM or null"}}
    ],
    "summary": "...",
    "vibe_check": "..."
}}"""

    image_part = {"mime_type": mime_type, "data": image_bytes}
    result = _generate_json(prompt, extra_parts=[image_part])

    if not result:
        return {"tasks": [], "summary": "Couldn't read the list clearly", "vibe_check": "Send a clearer snap next time 📸"}
    return result


async def parse_voice_message(audio_bytes: bytes, mime_type: str = "audio/ogg") -> dict:
    """
    Transcribes voice note and extracts intent.
    """
    prompt = f"""{KODED_CONTEXT}

{_get_date_context()}

Koded just sent a voice message.

1. Transcribe it accurately
2. Identify the intent:
   - add_task: he's listing things to do
   - add_opportunity: he's mentioning a hackathon, deadline, internship app
   - standup: he's giving a morning/evening update on his day
   - general_chat: just talking

3. Extract relevant structured data based on intent
4. Write a natural "response" to send back to him

Return ONLY valid JSON:
{{
    "transcript": "...",
    "intent": "add_task|add_opportunity|standup|general_chat",
    "tasks": [{{"title": "...", "track": "...", "due_time": "HH:MM or null"}}],
    "opportunity": {{"title": "...", "type": "hackathon|internship|deadline|event", "deadline": "YYYY-MM-DD or null", "notes": "..."}},
    "response": "..."
}}"""

    audio_part = {"mime_type": mime_type, "data": audio_bytes}
    result = _generate_json(prompt, extra_parts=[audio_part])

    if not result:
        return {
            "transcript": "",
            "intent": "general_chat",
            "tasks": [],
            "opportunity": {},
            "response": "Couldn't catch that clearly, try again or type it out 🎙️"
        }
    return result


async def parse_text_for_tasks(text: str) -> dict:
    """Parse freeform text for tasks/opportunities."""
    prompt = f"""{KODED_CONTEXT}

{_get_date_context()}

Koded just texted: "{text}"

Determine if this contains:
- Tasks to add (add_task)
- An opportunity to track (add_opportunity)
- A standup update (standup)
- Just chatting (general_chat)

Extract structured data and write a natural response.

Return ONLY valid JSON:
{{
    "intent": "add_task|add_opportunity|standup|general_chat",
    "tasks": [{{"title": "...", "track": "...", "due_time": "HH:MM or null"}}],
    "opportunity": {{"title": "...", "type": "hackathon|internship|deadline|event", "deadline": "YYYY-MM-DD or null", "notes": "..."}},
    "response": "..."
}}"""

    result = _generate_json(prompt)
    if not result:
        return {"intent": "general_chat", "tasks": [], "opportunity": {}, "response": await chat_with_gemini(text)}
    return result


async def parse_opportunity_from_text(text: str) -> dict:
    """
    Parse a pasted opportunity description and extract structured data.
    """
    prompt = f"""{KODED_CONTEXT}

{_get_date_context()}

Koded pasted this opportunity text. Extract all key details:

TEXT:
{text}

Rules:
- title: short, clear name for this opportunity (max 80 chars)
- type: one of hackathon, internship, deadline, event, grant, competition, general
- deadline: extract the application/submission deadline as YYYY-MM-DD. If a month+day is given with no year, assume {datetime.now().year} unless it's already passed, then use {datetime.now().year + 1}. If no deadline found, return null.
- link: extract any URL present, or null
- notes: 1-2 sentence summary of what this opportunity is and why it matters to Koded

Return ONLY valid JSON, no markdown:
{{"title": "...", "type": "...", "deadline": "YYYY-MM-DD or null", "link": "... or null", "notes": "..."}}"""

    result = _generate_json(prompt)
    if not result:
        return {"title": text[:80], "type": "general", "deadline": None, "link": None, "notes": ""}
    return result


async def generate_reminder(task: dict, tasks_remaining: list) -> str:
    """Generate a contextual reminder ping for a specific task."""
    remaining_titles = [t["title"] for t in tasks_remaining[:5]]
    prompt = f"""{KODED_CONTEXT}

Time to remind Koded about: "{task['title']}" (track: {task.get('track', 'general')})

Other tasks still pending today: {remaining_titles}

Write a SHORT, punchy reminder (2-3 sentences max).
Be direct. No fluff. Include relevant emoji."""

    try:
        return _generate(prompt)
    except Exception:
        return f"⏰ Reminder: {task['title']}"


async def generate_morning_standup() -> str:
    """Generate morning standup prompt."""
    prompt = f"""{KODED_CONTEXT}

{_get_date_context()}

It's morning standup time for Koded (7:30am Lagos time).

Write a short, energetic morning check-in message (3-5 sentences):
- Greet him based on time of day
- Ask what's on his plate today
- Optional: drop a quick motivation hit or reminder about his bigger goals
- End with a clear prompt asking him to share his tasks for the day

Keep it punchy, not corporate."""

    try:
        return _generate(prompt)
    except Exception:
        return "🌅 Morning Koded! What's on deck today? Drop your list and I'll keep you on track."


async def generate_evening_summary(tasks: list, logs: list) -> str:
    """Generate end-of-day summary."""
    done = [t for t in tasks if t.get("done")]
    pending = [t for t in tasks if not t.get("done")]

    prompt = f"""{KODED_CONTEXT}

{_get_date_context()}

It's end of day for Koded (9pm Lagos time).

Today's stats:
- Tasks completed: {len(done)} → {[t['title'] for t in done]}
- Tasks still pending: {len(pending)} → {[t['title'] for t in pending]}

Write an evening wind-down message (4-6 sentences):
- Acknowledge what got done
- Call out what's still pending
- Set the energy for tomorrow
- Ask how the day actually went

Real talk, not corporate. Max 1-2 emojis."""

    try:
        return _generate(prompt)
    except Exception:
        return f"🌙 Day done. {len(done)} tasks wrapped, {len(pending)} still pending. How'd it go?"


async def generate_weekly_summary(logs: list, tasks: list, opps: list) -> str:
    """Generate Sunday weekly summary."""
    log_content = "\n".join([f"{l['type']} ({l['date']}): {l['content']}" for l in logs])

    prompt = f"""{KODED_CONTEXT}

{_get_date_context()}

It's Sunday — time for Koded's weekly summary.

WEEK LOGS:
{log_content if log_content else "No standup logs recorded this week"}

PENDING TASKS: {[t['title'] for t in tasks[:10]]}
OPEN OPPORTUNITIES: {[o['title'] for o in opps[:5]]}

Write a comprehensive weekly summary (8-12 sentences):
1. What kind of week was it overall?
2. Key wins across his tracks
3. What slipped or got neglected
4. Opportunities he needs to act on
5. Energy/direction for next week

Be like a trusted advisor who knows him well. Real, direct, caring."""

    try:
        return _generate(prompt)
    except Exception:
        return "📊 Weekly summary unavailable — Gemini's having a moment. Check your logs manually."