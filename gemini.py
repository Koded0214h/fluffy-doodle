"""
KODED OS — Gemini AI Layer
Handles: text chat, image parsing (task lists), voice transcription + parsing
"""

import json
import logging
import re
import google.generativeai as genai
from config import GEMINI_API_KEY, GEMINI_MODEL, KODED_CONTEXT

logger = logging.getLogger(__name__)

genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel(GEMINI_MODEL)


def _clean_json(text: str) -> str:
    """Strip markdown code fences from Gemini JSON responses."""
    text = re.sub(r"```(?:json)?", "", text)
    return text.strip().strip("`").strip()


async def chat_with_gemini(user_message: str, extra_context: str = "") -> str:
    """General chat — handles task logging, questions, freeform input."""
    prompt = f"""{KODED_CONTEXT}

{extra_context}

USER MESSAGE:
{user_message}

Respond naturally as KODED OS. If the message contains tasks or to-dos, acknowledge them and confirm you've noted them.
Keep it conversational and punchy. No markdown headers in replies — just clean text with occasional emojis."""

    try:
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        logger.error(f"Gemini chat error: {e}")
        return "⚠️ Gemini had a moment. Try again in a sec."


async def parse_task_list_from_image(image_bytes: bytes, mime_type: str = "image/jpeg") -> dict:
    """
    Takes a photo of a task list and returns structured JSON:
    {
        "tasks": [
            {"title": "...", "track": "skurel|teenovatex|stackd|unilag|microsoft|personal", "due_time": "HH:MM or null"},
            ...
        ],
        "summary": "...",
        "vibe_check": "..."  // Gemini's take on the day ahead
    }
    """
    prompt = f"""{KODED_CONTEXT}

Koded just snapped a photo of his task list for today. 

Extract ALL tasks you can see. For each task:
1. Identify which of his tracks it belongs to: skurel, teenovatex, stackd, unilag, microsoft, personal
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

    try:
        image_part = {"mime_type": mime_type, "data": image_bytes}
        response = model.generate_content([prompt, image_part])
        cleaned = _clean_json(response.text)
        return json.loads(cleaned)
    except json.JSONDecodeError as e:
        logger.error(f"JSON parse error from image: {e}\nRaw: {response.text}")
        return {"tasks": [], "summary": "Couldn't read the list clearly", "vibe_check": "Send a clearer snap next time 📸"}
    except Exception as e:
        logger.error(f"Gemini vision error: {e}")
        return {"tasks": [], "summary": "Error processing image", "vibe_check": "Something broke 😬"}


async def parse_voice_message(audio_bytes: bytes, mime_type: str = "audio/ogg") -> dict:
    """
    Transcribes voice note and extracts intent:
    {
        "transcript": "...",
        "intent": "add_task | add_opportunity | general_chat | standup",
        "tasks": [...],          // if intent is add_task
        "opportunity": {...},    // if intent is add_opportunity
        "response": "..."        // natural language reply
    }
    """
    prompt = f"""{KODED_CONTEXT}

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

    try:
        audio_part = {"mime_type": mime_type, "data": audio_bytes}
        response = model.generate_content([prompt, audio_part])
        cleaned = _clean_json(response.text)
        return json.loads(cleaned)
    except json.JSONDecodeError as e:
        logger.error(f"Voice parse JSON error: {e}")
        return {
            "transcript": "",
            "intent": "general_chat",
            "tasks": [],
            "opportunity": {},
            "response": "Couldn't catch that clearly, try again or type it out 🎙️"
        }
    except Exception as e:
        logger.error(f"Gemini voice error: {e}")
        return {"transcript": "", "intent": "general_chat", "tasks": [], "opportunity": {}, "response": "Voice processing failed 😬"}


async def parse_text_for_tasks(text: str) -> dict:
    """
    Parse freeform text for tasks/opportunities.
    Returns same structure as voice parser.
    """
    prompt = f"""{KODED_CONTEXT}

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

    try:
        response = model.generate_content(prompt)
        cleaned = _clean_json(response.text)
        return json.loads(cleaned)
    except Exception as e:
        logger.error(f"Text parse error: {e}")
        return {"intent": "general_chat", "tasks": [], "opportunity": {}, "response": await chat_with_gemini(text)}


async def generate_reminder(task: dict, tasks_remaining: list) -> str:
    """Generate a contextual reminder ping for a specific task."""
    remaining_titles = [t["title"] for t in tasks_remaining[:5]]
    prompt = f"""{KODED_CONTEXT}

Time to remind Koded about: "{task['title']}" (track: {task.get('track', 'general')})

Other tasks still pending today: {remaining_titles}

Write a SHORT, punchy reminder (2-3 sentences max). 
Be direct. No fluff. Nigerian energy welcome. Include relevant emoji."""

    try:
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        logger.error(f"Reminder gen error: {e}")
        return f"⏰ Reminder: {task['title']}"


async def generate_morning_standup() -> str:
    """Generate morning standup prompt."""
    prompt = f"""{KODED_CONTEXT}

It's morning standup time for Koded (7:30am Lagos time).

Write a short, energetic morning check-in message (3-5 sentences):
- Greet him based on time of day
- Ask what's on his plate today
- Optional: drop a quick motivation hit or reminder about his bigger goals
- End with a clear prompt asking him to share his tasks for the day

Keep it punchy, not corporate. Nigerian energy."""

    try:
        response = model.generate_content(prompt)
        return response.text
    except Exception:
        return "🌅 Morning Koded! What's on deck today? Drop your list and I'll keep you on track."


async def generate_evening_summary(tasks: list, logs: list) -> str:
    """Generate end-of-day summary."""
    done = [t for t in tasks if t.get("done")]
    pending = [t for t in tasks if not t.get("done")]

    prompt = f"""{KODED_CONTEXT}

It's end of day for Koded (9pm Lagos time).

Today's stats:
- Tasks completed: {len(done)} → {[t['title'] for t in done]}
- Tasks still pending: {len(pending)} → {[t['title'] for t in pending]}

Write an evening wind-down message (4-6 sentences):
- Acknowledge what got done (gas him up if it's good)
- Call out what's still pending (no sugarcoating)
- Set the energy for tomorrow
- Ask how the day actually went (invite a reply)

Real talk, not corporate. Max 1-2 emojis."""

    try:
        response = model.generate_content(prompt)
        return response.text
    except Exception:
        return f"🌙 Day done. {len(done)} tasks wrapped, {len(pending)} still pending. How'd it go?"


async def generate_weekly_summary(logs: list, tasks: list, opps: list) -> str:
    """Generate Sunday weekly summary."""
    log_content = "\n".join([f"{l['type']} ({l['date']}): {l['content']}" for l in logs])

    prompt = f"""{KODED_CONTEXT}

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
        response = model.generate_content(prompt)
        return response.text
    except Exception:
        return "📊 Weekly summary unavailable — Gemini's having a moment. Check your logs manually."