"""
KODED OS — Gemini AI Layer
Multi-key rotation: automatically switches to next key on 429 rate limit.
"""

import json
import logging
import re
from datetime import datetime
import google.generativeai as genai
import httpx
from config import (
    GEMINI_API_KEYS, GEMINI_MODEL, KODED_CONTEXT,
    NVIDIA_API_KEYS, NVIDIA_MODEL
)
from database import get_user

logger = logging.getLogger(__name__)

# ── Key rotation state ─────────────────────────────────────────────────────

_current_key_index = 0
_current_nvidia_key_index = 0


def _get_model():
    """Configure Gemini with current key and return model instance."""
    global _current_key_index
    key = GEMINI_API_KEYS[_current_key_index]
    genai.configure(api_key=key)
    return genai.GenerativeModel(GEMINI_MODEL)


def _rotate_key():
    """Switch to next available Gemini API key."""
    global _current_key_index
    _current_key_index = (_current_key_index + 1) % len(GEMINI_API_KEYS)
    logger.info(f"🔄 Rotated to Gemini key #{_current_key_index + 1}")


async def _nvidia_generate(prompt: str) -> str:
    """Fallback to NVIDIA (Llama 3.1) with multi-key rotation on 429."""
    global _current_nvidia_key_index

    if not NVIDIA_API_KEYS:
        logger.warning("No NVIDIA API keys configured — skipping fallback")
        return ""

    url = "https://integrate.api.nvidia.com/v1/chat/completions"
    payload = {
        "model": NVIDIA_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.2,
        "top_p": 0.7,
        "max_tokens": 1024,
    }

    for attempt in range(len(NVIDIA_API_KEYS)):
        key = NVIDIA_API_KEYS[_current_nvidia_key_index]
        logger.info(f"⚡ Trying NVIDIA key #{_current_nvidia_key_index + 1} (attempt {attempt + 1}/{len(NVIDIA_API_KEYS)})")
        headers = {
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        }
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(url, headers=headers, json=payload)
                if resp.status_code == 429:
                    logger.warning(f"NVIDIA key #{_current_nvidia_key_index + 1} rate limited. Rotating...")
                    _current_nvidia_key_index = (_current_nvidia_key_index + 1) % len(NVIDIA_API_KEYS)
                    continue
                resp.raise_for_status()
                return resp.json()["choices"][0]["message"]["content"]
        except Exception as e:
            logger.error(f"NVIDIA key #{_current_nvidia_key_index + 1} failed: {e}")
            _current_nvidia_key_index = (_current_nvidia_key_index + 1) % len(NVIDIA_API_KEYS)
            continue

    logger.error("All NVIDIA keys exhausted or rate limited")
    return ""


async def _generate(prompt, extra_parts=None) -> str:
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
    
    # All Gemini keys failed, try NVIDIA (text only)
    if not extra_parts:
        nv_res = await _nvidia_generate(prompt)
        if nv_res:
            return nv_res
            
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


async def _generate_json(prompt, extra_parts=None) -> dict:
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
            
    # Fallback to NVIDIA
    if not extra_parts:
        nv_res = await _nvidia_generate(prompt)
        if nv_res:
            try:
                cleaned = _clean_json(nv_res)
                return json.loads(cleaned)
            except json.JSONDecodeError:
                return {}

    return {}


# ── Public API ─────────────────────────────────────────────────────────────

_PERSONALITY_DESCRIPTIONS = {
    "casual": "Casual and direct — like a smart friend who knows everything going on. Not corporate, not stiff.",
    "formal": "Formal and professional — precise, structured, respectful. Clear and composed at all times.",
    "honest": "Brutally honest — no sugarcoating, call things out directly. Real talk, always.",
    "hype": "High energy hype mode — motivating, enthusiastic, always pumping them up.",
}


async def get_effective_context(user_id: int) -> str:
    """Build per-user AI context from bio + personality, or fall back to default."""
    user = await get_user(user_id)
    if not user:
        return KODED_CONTEXT

    # Custom context override takes priority
    if user.get("context"):
        return user["context"]

    # Dynamic context built from user's profile
    if user.get("bio_text") and user.get("name"):
        name = user["name"]
        bio = user["bio_text"]
        personality = _PERSONALITY_DESCRIPTIONS.get(
            user.get("bot_personality", "casual"),
            _PERSONALITY_DESCRIPTIONS["casual"]
        )
        return f"""You are KODED OS — the personal AI chief of staff for {name}.

ABOUT {name.upper()}:
{bio}

YOUR PERSONALITY:
{personality}
- You're their second brain — know everything about what's going on in their life
- Short and punchy for reminders, detailed when explicitly asked
- Help them stay focused, not overwhelmed
- Honest when things pile up, encouraging when they win

YOUR JOB:
- Parse daily task lists from photos, voice notes, or text
- Schedule proactive reminders throughout the day
- Track opportunities (hackathons, deadlines, pitches, internships)
- Morning standup and evening wind-down
- Weekly summaries every Sunday
- Be the system that holds everything together so they can focus on building"""

    return KODED_CONTEXT


async def chat_with_gemini(user_id: int, user_message: str, extra_context: str = "") -> str:
    """General chat — handles task logging, questions, freeform input."""
    context = await get_effective_context(user_id)
    prompt = f"""{context}

{_get_date_context()}

{extra_context}

USER MESSAGE:
{user_message}

Respond naturally as the user's personal AI chief of staff. If the message contains tasks or to-dos, acknowledge them and confirm you've noted them.
Keep it conversational and punchy. No markdown headers in replies — just clean text with occasional emojis."""

    try:
        return await _generate(prompt)
    except Exception:
        return "⚠️ Gemini had a moment. Try again in a sec."


async def parse_task_list_from_image(user_id: int, image_bytes: bytes, mime_type: str = "image/jpeg") -> dict:
    """
    Takes a photo of a task list and returns structured JSON.
    """
    context = await get_effective_context(user_id)
    prompt = f"""{context}

{_get_date_context()}

The user just snapped a photo of their task list for today.

Extract ALL tasks you can see. For each task:
1. Identify which track it belongs to.
2. If a time is mentioned or implied, extract it as HH:MM (24h format)
3. If no time, set due_time to null

Also give:
- A brief "summary" of what kind of day this is shaping up to be
- A "vibe_check" — a short hype/roast about the workload (be real with them)

Return ONLY valid JSON. No explanation, no markdown fences:
{{
    "tasks": [
        {{"title": "task name", "track": "track_name", "due_time": "HH:MM or null"}}
    ],
    "summary": "...",
    "vibe_check": "..."
}}"""

    image_part = {"mime_type": mime_type, "data": image_bytes}
    result = await _generate_json(prompt, extra_parts=[image_part])

    if not result:
        return {"tasks": [], "summary": "Couldn't read the list clearly", "vibe_check": "Send a clearer snap next time 📸"}
    return result


async def parse_voice_message(user_id: int, audio_bytes: bytes, mime_type: str = "audio/ogg") -> dict:
    """
    Transcribes voice note and extracts intent.
    """
    context = await get_effective_context(user_id)
    prompt = f"""{context}

{_get_date_context()}

The user just sent a voice message.

1. Transcribe it accurately
2. Identify the intent:
   - add_task: they're listing things to do
   - add_opportunity: they're mentioning a hackathon, deadline, internship app
   - standup: they're giving a morning/evening update on their day
   - general_chat: just talking

3. Extract relevant structured data based on intent
4. Write a natural "response" to send back to them

Return ONLY valid JSON:
{{
    "transcript": "...",
    "intent": "add_task|add_opportunity|standup|general_chat",
    "tasks": [{{"title": "...", "track": "...", "due_time": "HH:MM or null"}}],
    "opportunity": {{"title": "...", "type": "hackathon|internship|deadline|event", "deadline": "YYYY-MM-DD or null", "notes": "..."}},
    "response": "..."
}}"""

    audio_part = {"mime_type": mime_type, "data": audio_bytes}
    result = await _generate_json(prompt, extra_parts=[audio_part])

    if not result:
        return {
            "transcript": "",
            "intent": "general_chat",
            "tasks": [],
            "opportunity": {},
            "response": "Couldn't catch that clearly, try again or type it out 🎙️"
        }
    return result


async def parse_text_for_tasks(user_id: int, text: str) -> dict:
    """Parse freeform text for tasks/opportunities."""
    context = await get_effective_context(user_id)
    prompt = f"""{context}

{_get_date_context()}

The user just texted: "{text}"

Determine if this contains:
- Tasks to add (add_task)
- An opportunity to track (add_opportunity) - Note: Social media links (Instagram, LinkedIn, etc.) should be treated as opportunities.
- A standup update (standup)
- Just chatting (general_chat)

Rules for Opportunities:
- If the user shares a link (e.g., Instagram, LinkedIn, Twitter/X) without much text, assume it's an opportunity.
- **NEVER** tell the user to "review" the link in your response. Instead, tell them you've tracked it.
- Title: If no title is clear, use a descriptive placeholder like "Opportunity from Instagram" or "LinkedIn Post".
- Notes: If details are thin, write "Click the link to see the full post and details."

Return ONLY valid JSON:
{{
    "intent": "add_task|add_opportunity|standup|general_chat",
    "tasks": [{{"title": "...", "track": "...", "due_time": "HH:MM or null"}}],
    "opportunity": {{"title": "...", "type": "hackathon|internship|deadline|event|general", "deadline": "YYYY-MM-DD or null", "notes": "..."}},
    "response": "..."
}}

Examples:
1. "https://instagram.com/p/..." -> {{"intent": "add_opportunity", "opportunity": {{"title": "Instagram Opportunity", "type": "general", "notes": "Click link for details."}}, "response": "🎯 Got that Instagram link! I've added it to your opportunities so you don't lose it."}}
"""

    result = await _generate_json(prompt)
    if not result:
        return {"intent": "general_chat", "tasks": [], "opportunity": {}, "response": await chat_with_gemini(user_id, text)}
    return result


async def parse_opportunity_from_text(user_id: int, text: str) -> dict:
    """
    Parse a pasted opportunity description and extract structured data.
    """
    context = await get_effective_context(user_id)
    prompt = f"""{context}

{_get_date_context()}

The user pasted this opportunity text or link. Extract all key details:

TEXT:
{text}

Rules:
- title: short, clear name for this opportunity (max 80 chars). 
- If it is just a social media link (Instagram, LinkedIn, etc.), use a title like "Opportunity from [Platform]".
- type: one of hackathon, internship, deadline, event, grant, competition, general
- deadline: extract the application/submission deadline as YYYY-MM-DD. If no deadline found, return null.
- link: extract any URL present, or null
- notes: 1-2 sentence summary of what this opportunity is and why it matters. 
- If it's a social media link with no description, use "Click link for full post and details."

Return ONLY valid JSON, no markdown:
{{"title": "...", "type": "...", "deadline": "YYYY-MM-DD or null", "link": "... or null", "notes": "..."}}"""

    result = await _generate_json(prompt)
    if not result:
        return {"title": text[:80], "type": "general", "deadline": None, "link": None, "notes": ""}
    return result


async def generate_reminder(user_id: int, task: dict, tasks_remaining: list, level: str = "10m") -> str:
    """Generate a contextual reminder ping. level: '30m' | '10m' | 'now'"""
    context = await get_effective_context(user_id)
    remaining_titles = [t["title"] for t in tasks_remaining[:5]]

    urgency = {
        "30m": f'This task is coming up in ~30 minutes: "{task["title"]}". Give a heads-up so they can wrap up whatever they\'re doing and prepare.',
        "10m": f'This task starts in ~10 minutes: "{task["title"]}". Be direct and urgent — time to move.',
        "now": f'It\'s time for: "{task["title"]}". This is due RIGHT NOW. Short, sharp, get them moving.',
    }.get(level, f'Reminder: "{task["title"]}"')

    prompt = f"""{context}

{urgency}
Track: {task.get('track', 'general')}
Other pending tasks today: {remaining_titles}

Write a SHORT, punchy reminder (2 sentences max). No fluff. Relevant emoji."""

    try:
        return await _generate(prompt)
    except Exception:
        return f"⏰ {task['title']}"


async def generate_morning_standup(user_id: int) -> str:
    """Generate morning standup prompt."""
    context = await get_effective_context(user_id)
    prompt = f"""{context}

{_get_date_context()}

It's morning standup time for the user.

Write a short, energetic morning check-in message (3-5 sentences):
- Greet them based on time of day
- Ask what's on their plate today
- Optional: drop a quick motivation hit or reminder about their bigger goals
- End with a clear prompt asking him to share his tasks for the day

Keep it punchy, not corporate."""

    try:
        return await _generate(prompt)
    except Exception:
        return "🌅 Morning! What's on deck today? Drop your list and I'll keep you on track."


async def generate_evening_summary(user_id: int, tasks: list, logs: list) -> str:
    """Generate end-of-day summary."""
    context = await get_effective_context(user_id)
    done = [t for t in tasks if t.get("done")]
    pending = [t for t in tasks if not t.get("done")]

    prompt = f"""{context}

{_get_date_context()}

It's end of day for the user.

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
        return await _generate(prompt)
    except Exception:
        return f"🌙 Day done. {len(done)} tasks wrapped, {len(pending)} still pending. How'd it go?"


async def generate_weekly_summary(user_id: int, logs: list, tasks: list, opps: list) -> str:
    """Generate Sunday weekly summary."""
    context = await get_effective_context(user_id)
    log_content = "\n".join([f"{l['type']} ({l['date']}): {l['content']}" for l in logs])

    prompt = f"""{context}

{_get_date_context()}

It's Sunday — time for the user's weekly summary.

WEEK LOGS:
{log_content if log_content else "No standup logs recorded this week"}

PENDING TASKS: {[t['title'] for t in tasks[:10]]}
OPEN OPPORTUNITIES: {[o['title'] for o in opps[:5]]}

Write a comprehensive weekly summary (8-12 sentences):
1. What kind of week was it overall?
2. Key wins
3. What slipped or got neglected
4. Opportunities they need to act on
5. Energy/direction for next week

Be like a trusted advisor who knows them well. Real, direct, caring."""

    try:
        return await _generate(prompt)
    except Exception:
        return "📊 Weekly summary unavailable — Gemini's having a moment. Check your logs manually."


# ── Opportunity Discovery ───────────────────────────────────────────────────

async def generate_opp_search_queries(user_id: int) -> list[str]:
    """Generate targeted search queries from the user's profile."""
    context = await get_effective_context(user_id)
    prompt = f"""{context}

{_get_date_context()}

Based on this user's profile, generate 4 targeted web search queries to find relevant opportunities.
Think: hackathons, internships, grants, fellowships, competitions, accelerators, programs.
Account for their location (Nigeria/Africa), their tech stack, career stage, and goals.

Return ONLY valid JSON — a dict with a "queries" key containing a list of strings:
{{"queries": ["query 1", "query 2", "query 3", "query 4"]}}

Make queries specific and include the current year. Examples:
"Africa fintech hackathon 2026", "Nigeria software developer internship 2026 remote" """

    result = await _generate_json(prompt)
    queries = result.get("queries", []) if isinstance(result, dict) else []
    if not queries:
        return ["Africa tech hackathon 2026", "Nigeria developer internship 2026", "web3 hackathon 2026 open"]
    return queries


async def filter_and_extract_opportunities(user_id: int, raw_results: list[dict]) -> list[dict]:
    """
    Filter raw search results for relevance and return structured opportunity data.
    Each result: {title, type, deadline, link, notes, why_relevant}
    """
    context = await get_effective_context(user_id)

    raw_text = "\n\n".join([
        f"Source: {r.get('source', 'web')}\nTitle: {r['title']}\nURL: {r['url']}\nSnippet: {r['snippet']}"
        for r in raw_results
        if r.get("title") and r.get("url")
    ])

    prompt = f"""{context}

{_get_date_context()}

Here are raw search results. Filter for opportunities genuinely relevant to this user and extract structured data.

RAW RESULTS:
{raw_text}

Rules:
- Only include opportunities relevant to this user's profile, skills, and goals
- Skip expired opportunities (deadline already passed based on current date)
- Skip irrelevant results (news articles, job boards for unrelated fields, etc.)
- deadline: extract as YYYY-MM-DD if visible in the text, else null
- type: one of hackathon, internship, grant, competition, fellowship, event, general
- notes: 1–2 sentence description of what it is and why it's relevant to THIS specific user
- link: the direct URL to the opportunity page
- why_relevant: one short sentence explaining relevance to this user
- Return max 8, ranked by relevance

Return ONLY valid JSON:
{{
    "opportunities": [
        {{"title": "...", "type": "...", "deadline": "YYYY-MM-DD or null", "link": "...", "notes": "...", "why_relevant": "..."}}
    ]
}}"""

    result = await _generate_json(prompt)
    return result.get("opportunities", []) if isinstance(result, dict) else []


async def generate_application_draft(user_id: int, opp: dict) -> dict:
    """
    Generate a personalized application draft, checklist, and tips for an opportunity.
    Returns {cover_letter, checklist, tips}
    """
    context = await get_effective_context(user_id)
    prompt = f"""{context}

{_get_date_context()}

The user wants to apply for this opportunity:
Title: {opp.get('title')}
Type: {opp.get('type', 'general')}
Deadline: {opp.get('deadline') or 'Not specified'}
Details: {opp.get('notes') or opp.get('title')}

Generate:
1. cover_letter — A punchy 2–3 paragraph intro/cover letter tailored to this user and this specific opportunity. First person. Genuine, not generic. Highlight their most relevant projects and skills.
2. checklist — 5–7 specific things they need to prepare or submit (tailored to the opportunity type and any requirements visible in the details)
3. tips — 2–3 specific tips to make their application stand out, based on their background and the opportunity

Return ONLY valid JSON:
{{"cover_letter": "...", "checklist": ["item 1", "item 2", ...], "tips": ["tip 1", "tip 2", ...]}}"""

    result = await _generate_json(prompt)
    if not result:
        return {
            "cover_letter": f"I'm excited to apply for {opp.get('title', 'this opportunity')}.",
            "checklist": ["Review requirements", "Prepare portfolio/CV", "Write your application", "Submit before deadline"],
            "tips": ["Be specific about your projects", "Show impact with numbers where possible"],
        }
    return result