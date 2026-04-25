"""
KODED OS — Opportunity Scraper
Sources:
  - Devpost          (JSON API — hackathons)
  - MLH              (HTML — student hackathons)
  - Opportunities for Africans (RSS — internships, scholarships, fellowships)
  - ETH Global       (HTML — Web3/blockchain hackathons)
  - Techstars        (HTML — accelerator programs)
  - Antler           (static Africa entries — early-stage VC residency)
  - DuckDuckGo       (search fallback + fixed Africa/blockchain queries)
"""

import asyncio
import logging
import re
import xml.etree.ElementTree as ET
from datetime import datetime

import httpx
from bs4 import BeautifulSoup
from duckduckgo_search import DDGS

logger = logging.getLogger(__name__)

DEVPOST_API = "https://devpost.com/api/hackathons.json"

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

# Fixed search queries always included (supplements user-context queries)
_FIXED_QUERIES = [
    f"Africa blockchain hackathon {datetime.now().year} open applications",
    f"Nigeria tech startup program grant {datetime.now().year}",
]

# Month abbrs used to split MLH event card text
_MONTHS = r"(?:JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)"


# ── Individual scrapers ─────────────────────────────────────────────────────

async def _fetch_devpost(max_results: int = 20) -> list[dict]:
    """Devpost public JSON API — open hackathons globally."""
    try:
        async with httpx.AsyncClient(timeout=15, headers=_HEADERS) as client:
            resp = await client.get(
                DEVPOST_API,
                params={"status[]": "open", "order_by": "deadline", "per_page": max_results},
            )
            resp.raise_for_status()
        results = []
        for h in resp.json().get("hackathons", []):
            snippet = h.get("tagline", "")
            if h.get("submission_period_dates"):
                snippet += f" | {h['submission_period_dates']}"
            results.append({
                "title": h.get("title", ""),
                "url": h.get("url") or h.get("website_url", ""),
                "snippet": snippet,
                "source": "devpost",
            })
        return results
    except Exception as e:
        logger.warning(f"Devpost: {e}")
        return []


async def _fetch_mlh() -> list[dict]:
    """MLH — student hackathons (events.mlh.io links embedded in main events page)."""
    try:
        year = datetime.now().year
        async with httpx.AsyncClient(timeout=15, headers=_HEADERS, follow_redirects=True) as client:
            resp = await client.get(f"https://mlh.io/seasons/{year}/events")
            resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        results = []
        for link in soup.select('a[href*="events.mlh.io/events"]'):
            raw = link.get_text(separator=" ", strip=True)
            url = link.get("href", "https://mlh.io")
            # Split at month abbreviation to get the event name
            month_match = re.search(_MONTHS, raw)
            name = raw[:month_match.start()].strip() if month_match else raw[:80].strip()
            date_str = raw[month_match.start():month_match.start() + 20].strip() if month_match else ""
            if not name:
                continue
            results.append({
                "title": f"{name} — MLH Hackathon",
                "url": url,
                "snippet": f"MLH hackathon. {date_str}".strip(),
                "source": "mlh",
            })
        return results
    except Exception as e:
        logger.warning(f"MLH: {e}")
        return []


async def _fetch_opp_for_africans() -> list[dict]:
    """Opportunities for Africans — RSS feed (internships, scholarships, fellowships, grants)."""
    try:
        async with httpx.AsyncClient(timeout=15, headers=_HEADERS, follow_redirects=True) as client:
            resp = await client.get("https://www.opportunitiesforafricans.com/feed/")
            resp.raise_for_status()
        root = ET.fromstring(resp.content)
        results = []
        for item in root.findall(".//item")[:25]:
            title = (item.findtext("title") or "").strip()
            link = (item.findtext("link") or "").strip()
            desc = (item.findtext("description") or "").strip()
            desc_clean = BeautifulSoup(desc, "html.parser").get_text()[:250] if desc else ""
            if title and link:
                results.append({
                    "title": title,
                    "url": link,
                    "snippet": desc_clean,
                    "source": "opportunities-for-africans",
                })
        return results
    except Exception as e:
        logger.warning(f"Opportunities for Africans: {e}")
        return []


async def _fetch_ethglobal() -> list[dict]:
    """ETH Global — Web3 hackathons worldwide."""
    try:
        async with httpx.AsyncClient(timeout=15, headers=_HEADERS, follow_redirects=True) as client:
            resp = await client.get("https://ethglobal.com/events")
            resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        results = []
        seen_slugs: set[str] = set()
        for link in soup.select('a[href*="/events/"]'):
            href = link.get("href", "")
            slug = href.replace("/events/", "").strip("/")
            # Skip index page self-links and duplicates
            if not slug or slug in seen_slugs or slug == "events":
                continue
            seen_slugs.add(slug)

            raw = link.get_text(separator=" ", strip=True)
            # Strip leading date tokens: month names, weekday abbrs, numbers, dashes
            _DATE_TOKEN = (
                r"(?:January|February|March|April|May|June|July|August|September|October|November|December"
                r"|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Oct|Nov|Dec"
                r"|Mon|Tue|Wed|Thu|Fri|Sat|Sun|—|\d+|\s)+"
            )
            cleaned = re.sub(r'^' + _DATE_TOKEN, '', raw).strip()
            # Strip trailing call-to-action and event-type labels
            cleaned = re.sub(
                r'\s*(Apply to Attend|IRL Hackathon|Async Hackathon|Online Hackathon|Conference)\s*.*',
                '', cleaned, flags=re.IGNORECASE
            ).strip()
            name = cleaned if len(cleaned) > 4 else slug.replace("-", " ").title()

            results.append({
                "title": f"{name} — ETH Global",
                "url": f"https://ethglobal.com{href}",
                "snippet": f"ETH Global Web3 hackathon. {raw[:100]}",
                "source": "ethglobal",
            })
        return results
    except Exception as e:
        logger.warning(f"ETH Global: {e}")
        return []


async def _fetch_techstars() -> list[dict]:
    """Techstars — open accelerator programs with deadlines."""
    try:
        async with httpx.AsyncClient(timeout=15, headers=_HEADERS, follow_redirects=True) as client:
            resp = await client.get("https://www.techstars.com/programs")
            resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        results = []
        for link in soup.select('a[href*="/accelerators/"]'):
            href = link.get("href", "")
            raw = link.get_text(separator=" ", strip=True)
            if not raw or len(raw) < 10:
                continue

            # Extract deadline: "Apply by May 6"
            deadline_match = re.search(r'Apply by (\w+ \d+)', raw)
            deadline_str = deadline_match.group(1) if deadline_match else ""

            # Program name: text after deadline, before location (last 2 words look like "City, Country")
            name = re.sub(r'^Apply by \w+ \d+\s*', '', raw).strip()
            # Remove location suffix (last comma-separated segment)
            name = re.sub(r',\s*[^,]+$', '', name).strip()

            url = href if href.startswith("http") else f"https://www.techstars.com{href}"
            results.append({
                "title": name,
                "url": url,
                "snippet": f"Techstars accelerator program.{f' Apply by {deadline_str}.' if deadline_str else ''}",
                "source": "techstars",
            })
        return results
    except Exception as e:
        logger.warning(f"Techstars: {e}")
        return []


def _antler_africa_entries() -> list[dict]:
    """
    Antler — Africa locations (Nigeria, Kenya).
    Antler's pages are heavily JS-rendered so we return known entries
    and let Gemini determine deadline relevance.
    """
    return [
        {
            "title": "Antler Nigeria — Startup Residency Program",
            "url": "https://www.antler.co/location/nigeria",
            "snippet": (
                "Antler's early-stage VC residency in Nigeria. "
                "Co-founder matching, seed funding ($250k+), mentorship, and access to a global network. "
                "Apply at antler.co/apply"
            ),
            "source": "antler",
        },
        {
            "title": "Antler East Africa (Kenya) — Startup Residency",
            "url": "https://www.antler.co/location/kenya",
            "snippet": (
                "Build your startup in 10 weeks with Antler East Africa. "
                "Co-founder matching, seed funding, and mentorship for early-stage founders."
            ),
            "source": "antler",
        },
    ]


# ── DuckDuckGo search ───────────────────────────────────────────────────────

def _sync_ddg_search(query: str, max_results: int = 5) -> list[dict]:
    try:
        raw = DDGS().text(query, max_results=max_results)
        return [
            {
                "title": r.get("title", ""),
                "url": r.get("href", ""),
                "snippet": r.get("body", ""),
                "source": "search",
            }
            for r in (raw or [])
        ]
    except Exception as e:
        logger.warning(f"DDG '{query}': {e}")
        return []


async def _ddg_search(query: str, max_results: int = 5) -> list[dict]:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _sync_ddg_search, query, max_results)


# ── Main entry point ────────────────────────────────────────────────────────

async def fetch_raw_opportunities(queries: list[str]) -> list[dict]:
    """
    Pull raw opportunity data from all sources concurrently.
    Returns deduplicated list of {title, url, snippet, source}.
    """
    # Run all dedicated scrapers in parallel
    scraper_results = await asyncio.gather(
        _fetch_devpost(),
        _fetch_mlh(),
        _fetch_opp_for_africans(),
        _fetch_ethglobal(),
        _fetch_techstars(),
        return_exceptions=True,
    )

    results: list[dict] = []
    for r in scraper_results:
        if isinstance(r, list):
            results.extend(r)

    # Antler Africa (static, no I/O needed)
    results.extend(_antler_africa_entries())

    # DuckDuckGo: user-context queries + fixed Africa/blockchain queries
    all_queries = list(queries[:4]) + _FIXED_QUERIES
    ddg_results = await asyncio.gather(
        *[_ddg_search(q, max_results=5) for q in all_queries],
        return_exceptions=True,
    )
    for r in ddg_results:
        if isinstance(r, list):
            results.extend(r)

    # Deduplicate by URL
    seen: set[str] = set()
    unique: list[dict] = []
    for r in results:
        key = r.get("url", "").lower().rstrip("/")
        if key and key not in seen:
            seen.add(key)
            unique.append(r)

    logger.info(f"fetch_raw_opportunities: {len(unique)} unique results from {len(results)} total")
    return unique
