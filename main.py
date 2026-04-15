#!/usr/bin/env python3
"""
Geopolitical Breaking News Automation — v19.1 (Global OSINT Syndicate)
======================================================================
3-Tier article sourcing (NewsAPI → GDELT → RSS) + Telethon native
Telegram video hunting + YouTube Data API fallback → Pillow news cards
+ FFmpeg vertical video → Google Drive output.
Self-learning via LLM dedup, cross-source triangulation, and
reinforcement learning feedback loop. Groq Llama 3 / Gemini 2.5 Flash
for GOAT Mode caption generation.
"""

import os
import asyncio
import trafilatura
import sys
import json
import hashlib
import re
import logging
import math
import time
import subprocess
import random
import textwrap
from difflib import SequenceMatcher
from datetime import datetime, timezone, timedelta
from pathlib import Path
from io import BytesIO
from urllib.parse import quote as url_quote

import yt_dlp
import feedparser
import requests
import cloudscraper
import dateparser as dp
from bs4 import BeautifulSoup
from PIL import Image, ImageDraw, ImageFont, ImageEnhance, ImageFilter, ImageOps
import pillow_avif

# V19.1: Telethon native Telegram client
try:
    from telethon import TelegramClient
    from telethon.sessions import StringSession
    from telethon.tl.types import InputMessagesFilterVideo
    TELETHON_AVAILABLE = True
except ImportError:
    TELETHON_AVAILABLE = False

# V19.1: NewsAPI Python wrapper
try:
    from newsapi import NewsApiClient
    NEWSAPI_AVAILABLE = True
except ImportError:
    NEWSAPI_AVAILABLE = False

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent
# Track run number for DD_NN format
tracker_file = BASE_DIR / "run_tracker.json"
today_dd = datetime.now(timezone.utc).strftime("%d")
run_nn = 1

if os.path.exists(tracker_file):
    try:
        with open(tracker_file, "r") as f:
            tracker = json.load(f)
        if tracker.get("date") == today_dd:
            run_nn = tracker.get("run_number", 0) + 1
    except Exception: pass

with open(tracker_file, "w") as f:
    json.dump({"date": today_dd, "run_number": run_nn}, f)

FN = f"{today_dd}_{run_nn}" # e.g., 08_1
folder_name = f"DD_FN----{FN}"
RUN_DIR = BASE_DIR / "output" / folder_name
os.makedirs(RUN_DIR, exist_ok=True)
os.makedirs(BASE_DIR / "videos", exist_ok=True)

successful_post_counter = 1

OUTPUT_DIR = RUN_DIR
VIDEO_DIR = RUN_DIR
FONTS_DIR = BASE_DIR / "fonts"
FLAGS_DIR = BASE_DIR / "assets" / "flags"
COUNTRY_MAPS_DIR = BASE_DIR / "assets" / "country_maps"
ACTORS_DIR = BASE_DIR / "assets" / "actors"
POSTED_LINKS_FILE = BASE_DIR / "posted_links.json"
AI_USAGE_FILE = BASE_DIR / "ai_usage.json"
DARK_MAP_FILE = BASE_DIR / "assets" / "dark_world_map.png"
BRAIN_WEIGHTS_FILE = BASE_DIR / "brain_weights.json"  # V19.0: Reinforcement learning weights

CARD_WIDTH = 1080
CARD_HEIGHT = 1080

# V3.4 Layout Constants
HEADER_HEIGHT_PCT = 0.08          # 8% header (≈86px)
LEFT_PANEL_PCT = 0.45             # 45% image panel
RIGHT_PANEL_PCT = 0.55            # 55% text panel
RIGHT_MARGIN = 45                 # strict 45px horizontal padding
FLAG_TOP_GAP = 25                 # 25px below header
HEADLINE_TOP_GAP = 25            # 25px below flags
SUMMARY_TOP_GAP = 20             # 20px below headline
SUMMARY_CHAR_LIMIT = 500         # V7.0: Groq generates 450-480 chars
LINE_SPACING_MULT = 1.3          # summary line-height multiplier
FLAG_SCALE_DOWN = 0.85           # 15% smaller flags
MIN_EXTRACT_CHARS = 150
BATCH_SIZE = 4                   # V18.30: 4 AI-generated News Cards per run
MAX_VIDEOS = 5                   # V18.30: 5 Telegram OSINT videos per run
HIGHLIGHT_COLOR = "#FBBF24"      # V7.0: keyword highlight gold
MAX_ARTICLE_AGE_HOURS = 24       # V15.6: 24h strict freshness window

# ---------------------------------------------------------------------------
# V17.0: Instagram Clone & Rebrand Configuration
# ---------------------------------------------------------------------------

TARGET_IG_CHANNELS = [
    "iran_military_officiall",
    "middle_east_spectator",
    "irgc.intel",
]

# ---------------------------------------------------------------------------
# V19.1: GOAT MODE — Real-Time Clock Injection
# ---------------------------------------------------------------------------

def _goat_timestamp() -> str:
    """V19.1: Returns current UTC time string for real-time caption injection."""
    return datetime.now(timezone.utc).strftime("%B %d, %Y at %H:%M UTC")

_IG_REWRITE_PROMPT = """You are an elite OSINT analyst and social media growth expert for the breaking news channel @geopolitics.
I will give you a caption from another news source. Rewrite it completely in your own words so it is unique.

The current real-time clock is: {current_time}.

Original caption:
{caption}

Return strict JSON with exactly 3 keys:
- "rewritten_caption": Rewrite following this STRICT structure:
  1. THE HOOK: Start with a hard-hitting, real-time breaking news indicator using an emoji (e.g., 🚨 BREAKING:, ⚡ JUST IN:). You MUST reference the current time or state that this is happening "right now" or "minutes ago".
  2. THE BRIEF: Write 2 clinical, objective sentences explaining exactly WHAT is happening on the ground.
  3. THE MACRO: Add 1 sentence explaining the broader GEOPOLITICAL IMPACT (why this shifts the balance of power).
  4. THE ENGAGEMENT TRAP: End the text with one sharp, highly analytical question designed to force people to debate in the comments + "👇".
- "image_hook": Write 1 to 2 sentences summarizing this like a viral military Twitter post. Extremely simple English.
- "dynamic_hashtags": Generate 5-7 hyper-specific hashtags based ONLY on the exact entities, cities, weapons, or leaders mentioned. THE SPAM BAN: You are strictly FORBIDDEN from using generic, mass-produced hashtags like #news, #worldnews, #geopolitics, #war, or #viral. Every tag must be strictly unique to the tactical event. Always end the block with your branded tag #geopolitics.

Return ONLY the JSON object, no markdown, no explanation."""



# ---------------------------------------------------------------------------
# Anti-Bot Headers
# ---------------------------------------------------------------------------

HTTP_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1"
}

# ---------------------------------------------------------------------------
# RSS Sources
# ---------------------------------------------------------------------------

RSS_FEEDS = {
    "Tasnim News": "https://www.tasnimnews.com/en/rss",
    "Press TV": "https://www.presstv.ir/rss",
    "IRNA": "https://en.irna.ir/rss",
    "Fars News": "https://english.farsnews.ir/rss",
    "Tehran Times": "https://www.tehrantimes.com/rss",
    "Mehr News": "https://en.mehrnews.com/rss",
    "Al Mayadeen": "https://english.almayadeen.net/rss",
    "Al Manar": "https://english.almanar.com.lb/rss",
    "SANA": "https://sana.sy/en/?feed=rss2",
    "Al Jazeera": "https://www.aljazeera.com/xml/rss/all.xml",
    "Defense News": "https://www.defensenews.com/arc/outboundfeeds/rss/",
    "Defense Post": "https://www.thedefensepost.com/feed/",
    "BBC ME": "https://feeds.bbci.co.uk/news/world/middle_east/rss.xml",
    "Defense Update": "https://defense-update.com/feed/"
}

GOOGLE_NEWS_QUERIES = [
    '"Fattah missile" OR "hypersonic" OR "supersonic"',
    '"ballistic missile" AND "strike"',
    '"IRGC" AND "air defense"',
    '"Israel strike" OR "US base attack"',
    '"Hezbollah rockets" OR "Lebanon airstrike"'
]

# ---------------------------------------------------------------------------
# Keyword Systems
# ---------------------------------------------------------------------------

COMBAT_KEYWORDS = [
    # Core Weapons & Tech
    'missile', 'ballistic', 'hypersonic', 'fattah', 'fatteh', 
    'supersonic', 'bomb', 'rocket', 'drone', 'uav', 'shahed', 'cruise missile', 
    'warhead', 'munition', 'artillery', 'radar', 'interceptor',
    
    # Specific Iranian/Resistance Arsenal
    'khorramshahr', 'sejjil', 'qiam', 'zolfaghar', 'bavar', 'khordad', 'ababil', 'mohajer',
    
    # Strict Combat Actions & Events
    'war', 'intercepted', 'explosion', 'airstrike', 'air strike', 'missile strike', 
    'assault', 'raid', 'ambush', 'destroyed', 'blast', 'missile launch', 'barrage', 
    'salvo', 'retaliation', 'revenge', 'military offensive', 'escalation',
    
    # Entities, Factions & Forces
    'idf', 'irgc', 'hezbollah', 'houthi', 'ansarallah', 'quds force', 
    'axis of resistance', 'hamas', 'al-qassam', 'zionist', 'centcom', 
    'hashd', 'pmu', 'air defense', 'military base', 'outpost', 'military facility'
]

def is_combat_relevant(text: str) -> bool:
    if not text:
        return False
    text_lower = text.lower()
    return any(keyword in text_lower for keyword in COMBAT_KEYWORDS)

SEVERITY_KEYWORDS = [
    "war", "strike", "attack", "military", "defense",
    "sanctions", "crisis", "emergency",
]

GEOPOLITICS_KEYWORDS = [
    "war", "strike", "death", "missile", "airstrike", "drone", "casualties",
    "offensive", "invasion", "frontline", "troops", "skirmish", "ceasefire",
    "escalation", "retaliation", "bombing", "artillery", "ambush", "fighter jet",
    "naval", "warship", "submarine", "tank", "radar", "air defense", "ballistic",
    "cruise missile", "hypersonic", "nuclear", "uranium", "stealth",
    "aircraft carrier", "treaty", "sanctions", "summit", "ambassador", "diplomat",
    "veto", "nato", "alliance", "proxy", "embargo", "blockade", "bilateral",
    "intelligence", "espionage", "cyberattack", "assassination", "covert",
    "rebel", "insurgent", "militia", "guerilla", "terror", "hostage",
    "evacuation", "refugee", "humanitarian", "annexation", "sovereignty",
    "territory", "border", "strait", "chokepoint", "deployment", "garrison",
    "battalion", "infantry", "special forces", "reconnaissance", "kamikaze",
    "intercept", "dogfight", "casualty", "fatality", "wounded", "civilian",
    "collateral damage", "war crime", "tribunal", "paramilitary", "regime",
    "coup", "overthrow", "uprising", "protest", "riot", "crackdown",
    "martial law", "curfew", "mobilization", "conscription", "draft", "mutiny",
    "desertion", "defector", "pow", "prisoner of war", "interrogation",
    "surrender", "armistice", "truce", "peacekeeping", "unsc", "resolution",
    "condemnation", "diplomatic fallout", "expulsion", "persona non grata",
    "embassy", "consulate", "geopolitics", "hegemony", "superpower",
    "deterrence", "brinkmanship", "standoff", "stalemate", "flashpoint",
    "no-fly zone", "demilitarized", "wmd", "chemical weapon", "biological weapon",
    "fallout", "radioactive", "emp", "jamming", "electronic warfare", "satellite",
    "recon", "surveillance", "black op", "clandestine", "mercenary", "pmc",
    "wagner", "cartel", "smuggling", "contraband", "piracy", "hijack",
    "maritime", "freedom of navigation", "airspace", "violation", "incursion",
    "scramble", "alert", "defcon", "threat level", "readiness", "drill",
    "exercise", "wargame", "live fire", "munitions", "shrapnel", "ied",
    "minefield", "trench", "fortification", "bunker", "barracks",
    "command post", "headquarters", "logistics", "supply chain",
    "embassy attack", "drone swarm",
]

EXCLUDE_MARKERS = [
    "opinion", "editorial", "analysis", "blog", "commentary",
    "column", "perspective", "op-ed", "review", "podcast",
    "interview", "letter", "explainer", "quiz", "gallery",
    "feature", "retrospective", "history of",
]

# V15.4 Strict Rejection Firewall — block sports, entertainment, domestic noise
REJECTION_KEYWORDS = [
    "sports", "football", "soccer", "la liga", "premier league",
    "madrid", "barca", "barcelona", "hollywood", "celebrity",
    "entertainment", "gossip", "nba", "nfl", "mlb", "cricket",
    "tennis", "golf", "olympics", "champions league", "serie a",
    "bundesliga", "ligue 1", "transfer", "playoffs", "super bowl",
    # V15.4: Strict domestic/business noise rejection
    "murder", "homicide", "suicide", "domestic violence", "robbery",
    "burglary", "theft", "fraud", "scam", "acquisition", "merger",
    "ipo", "stock market", "earnings report", "quarterly results",
    "real estate", "housing market", "recipe", "cookbook", "fashion",
    "lifestyle", "wellness", "fitness", "diet", "weight loss",
]


# ---------------------------------------------------------------------------
# Colors
# ---------------------------------------------------------------------------

RED_STRIP = "#D90429"
TEXT_PANEL_BG = "#111827"
HEADLINE_COLOR = "#FFFFFF"
SUMMARY_COLOR = "#D1D5DB"
FOOTER_COLOR = "#A1A1AA"
HEADER_TEXT_COLOR = "#FFFFFF"
BIG_PICTURE_COLOR = "#FBBF24"

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("geopolitics")


# ===========================================================================
# FONT MANAGEMENT
# ===========================================================================

def _load_font(name: str, size: int) -> ImageFont.FreeTypeFont:
    font_map = {
        "header": "Oswald-Bold.ttf",
        "headline": "Roboto-Variable.ttf",
        "summary": "Roboto-Variable.ttf",
        "footer": "CourierPrime-Regular.ttf",
    }
    filename = font_map.get(name, "Roboto-Variable.ttf")
    font_path = FONTS_DIR / filename
    if font_path.exists():
        try:
            return ImageFont.truetype(str(font_path), size)
        except Exception:
            pass
    system_fonts = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for fp in system_fonts:
        if os.path.exists(fp):
            return ImageFont.truetype(fp, size)
    return ImageFont.load_default()


def _hex(color: str) -> tuple:
    h = color.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


# ===========================================================================
# SMART TYPOGRAPHY
# ===========================================================================

def smart_typography(text: str) -> str:
    """Convert straight quotes to curly and double-hyphens to em-dashes."""
    # Curly double quotes
    text = re.sub(r'"([^"]*)"', lambda m: "\u201c" + m.group(1) + "\u201d", text)
    # Curly single quotes / apostrophes
    text = re.sub(r"(\w)'(\w)", lambda m: m.group(1) + "\u2019" + m.group(2), text)
    text = re.sub(r"'([^']*)'", lambda m: "\u2018" + m.group(1) + "\u2019", text)
    # Em-dashes
    text = text.replace("--", "\u2014")
    return text


# ===========================================================================
# BULLETPROOF DATE PARSING
# ===========================================================================

def parse_date_bulletproof(raw_date) -> datetime | None:
    if raw_date is None:
        return None
    if isinstance(raw_date, datetime):
        if raw_date.tzinfo is None:
            return raw_date.replace(tzinfo=timezone.utc)
        return raw_date
    raw_str = str(raw_date).strip()
    if not raw_str:
        return None
    try:
        parsed = dp.parse(
            raw_str,
            settings={"TIMEZONE": "UTC", "RETURN_AS_TIMEZONE_AWARE": True, "PREFER_DATES_FROM": "past"}
        )
        if parsed:
            return parsed
    except Exception:
        pass
    try:
        from dateutil import parser as dup
        return dup.parse(raw_str)
    except Exception:
        pass
    return None


def format_dateline(dt: datetime | None) -> str:
    if dt is None:
        dt = datetime.now(timezone.utc)
    return dt.strftime("%d %b %Y \u00b7 %H:%M GMT").upper()


# ===========================================================================
# 1. GOOGLE NEWS REDIRECT RESOLUTION
# ===========================================================================

def resolve_google_news_url(url: str) -> str:
    if "news.google.com" not in url and "google.com/rss" not in url:
        return url
    try:
        resp = requests.head(url, headers=HTTP_HEADERS, allow_redirects=True, timeout=10)
        if resp.url and "news.google.com" not in resp.url:
            log.info(f"  Resolved: {resp.url[:80]}\u2026")
            return resp.url
    except Exception:
        pass
    try:
        resp = requests.get(url, headers=HTTP_HEADERS, allow_redirects=True, timeout=10, stream=True)
        final = resp.url
        resp.close()
        if final and "news.google.com" not in final:
            return final
    except Exception as exc:
        log.warning(f"  Redirect failed: {exc}")
    return url


# ===========================================================================
# 2. ARTICLE FETCHING — V19.1 3-TIER OSINT ENGINE
# ===========================================================================

def _fetch_newsapi() -> list[dict]:
    """V19.1 Tier 1: NewsAPI — Pull breaking conflict news via 'everything' endpoint."""
    api_key = os.environ.get("NEWS_API_KEY", "")
    if not api_key:
        log.info("  [TIER 1] NEWS_API_KEY not set. Skipping NewsAPI.")
        return []
    if not NEWSAPI_AVAILABLE:
        log.warning("  [TIER 1] newsapi-python not installed. Skipping NewsAPI.")
        return []

    articles = []
    try:
        client = NewsApiClient(api_key=api_key)
        # Build query from top combat keywords
        query_terms = " OR ".join(COMBAT_KEYWORDS[:8])
        log.info(f"  [TIER 1] NewsAPI query: {query_terms[:80]}…")

        result = client.get_everything(
            q=query_terms,
            language="en",
            sort_by="publishedAt",
            page_size=20,
        )

        for item in result.get("articles", []):
            title = (item.get("title") or "").strip()
            link = (item.get("url") or "").strip()
            if not title or not link or title == "[Removed]":
                continue
            pub_date = parse_date_bulletproof(item.get("publishedAt"))
            articles.append({
                "title": title,
                "link": link,
                "summary": (item.get("description") or "").strip(),
                "source": f"NewsAPI:{(item.get('source', {}).get('name', 'Unknown'))}",
                "pub_date": pub_date,
                "image_url": item.get("urlToImage"),
                "full_text": None,
            })
        log.info(f"  [TIER 1] NewsAPI returned {len(articles)} articles.")
    except Exception as exc:
        log.warning(f"  [TIER 1] NewsAPI failed: {exc}")
    return articles


def _fetch_gdelt() -> list[dict]:
    """V19.1 Tier 2: GDELT 2.0 Doc API — Real-time global event monitoring (no API key)."""
    articles = []
    try:
        # Build query from top combat keywords
        query_terms = " OR ".join(COMBAT_KEYWORDS[:5])
        params = {
            "query": query_terms,
            "mode": "artlist",
            "format": "json",
            "maxrecords": 15,
            "timespan": "24h",
        }
        log.info(f"  [TIER 2] GDELT query: {query_terms[:80]}…")
        resp = requests.get(
            "https://api.gdeltproject.org/api/v2/doc/doc",
            params=params,
            headers=HTTP_HEADERS,
            timeout=20,
        )
        if resp.status_code != 200:
            log.warning(f"  [TIER 2] GDELT returned HTTP {resp.status_code}")
            return []

        data = resp.json()
        for item in data.get("articles", []):
            title = (item.get("title") or "").strip()
            link = (item.get("url") or "").strip()
            if not title or not link:
                continue
            pub_date = parse_date_bulletproof(item.get("seendate"))
            articles.append({
                "title": title,
                "link": link,
                "summary": "",
                "source": f"GDELT:{(item.get('domain', 'Unknown'))}",
                "pub_date": pub_date,
                "image_url": item.get("socialimage"),
                "full_text": None,
            })
        log.info(f"  [TIER 2] GDELT returned {len(articles)} articles.")
    except Exception as exc:
        log.warning(f"  [TIER 2] GDELT failed: {exc}")
    return articles


def _fetch_rss() -> list[dict]:
    """V19.1 Tier 3: Direct RSS Feeds + Google News RSS (preserved from legacy)."""
    articles = []

    # Direct RSS Feeds
    for source_name, url in RSS_FEEDS.items():
        log.info(f"Fetching RSS: {source_name}")
        try:
            feed = feedparser.parse(url)
            for entry in feed.get("entries", []):
                title = entry.get("title", "").strip()
                link = entry.get("link", "").strip()
                if not title or not link:
                    continue
                summary = ""
                if entry.get("summary"):
                    summary = BeautifulSoup(entry["summary"], "html.parser").get_text(strip=True)
                pub_date = None
                for df in ["published", "updated", "created"]:
                    if entry.get(df):
                        pub_date = parse_date_bulletproof(entry[df])
                        if pub_date:
                            break
                image_url = None
                for field in ["media_content", "media_thumbnail"]:
                    if entry.get(field):
                        for mc in entry[field]:
                            if mc.get("url"):
                                image_url = mc["url"]
                                break
                    if image_url:
                        break
                # V15.8: Chronological cutoff — stop parsing if we hit old news
                if pub_date:
                    _cut_now = datetime.now(timezone.utc)
                    _cut_pub = pub_date if pub_date.tzinfo else pub_date.replace(tzinfo=timezone.utc)
                    _cut_age = (_cut_now - _cut_pub).total_seconds() / 3600
                    if _cut_age > 48 and _cut_age < 700:
                        log.info(f"  [SKIP] Reached old news in {source_name} feed ({_cut_age:.0f}h). Moving to next source.")
                        break
                articles.append({
                    "title": title, "link": link, "summary": summary,
                    "source": source_name, "pub_date": pub_date,
                    "image_url": image_url, "full_text": None,
                })
        except Exception as exc:
            log.warning(f"RSS {source_name} failed: {exc}")

    # Google News RSS search
    for query in GOOGLE_NEWS_QUERIES:
        gn_url = f"https://news.google.com/rss/search?q={url_quote(query)}&hl=en-US&gl=US&ceid=US:en"
        gn_source = f"GoogleNews:{query[:30]}"
        log.info(f"Fetching Google News RSS: {gn_source}")
        try:
            feed = feedparser.parse(gn_url)
            for entry in feed.get("entries", []):
                title = entry.get("title", "").strip()
                link = entry.get("link", "").strip()
                if not title or not link:
                    continue
                summary = ""
                if entry.get("summary"):
                    summary = BeautifulSoup(entry["summary"], "html.parser").get_text(strip=True)
                pub_date = None
                for df in ["published", "updated", "created"]:
                    if entry.get(df):
                        pub_date = parse_date_bulletproof(entry[df])
                        if pub_date:
                            break
                image_url = None
                for field in ["media_content", "media_thumbnail"]:
                    if entry.get(field):
                        for mc in entry[field]:
                            if mc.get("url"):
                                image_url = mc["url"]
                                break
                    if image_url:
                        break
                # V15.8: Chronological cutoff
                if pub_date:
                    _cut_now = datetime.now(timezone.utc)
                    _cut_pub = pub_date if pub_date.tzinfo else pub_date.replace(tzinfo=timezone.utc)
                    _cut_age = (_cut_now - _cut_pub).total_seconds() / 3600
                    if _cut_age > 48 and _cut_age < 700:
                        log.info(f"  [SKIP] Reached old news in {gn_source} ({_cut_age:.0f}h). Moving to next query.")
                        break
                articles.append({
                    "title": title, "link": link, "summary": summary,
                    "source": gn_source, "pub_date": pub_date,
                    "image_url": image_url, "full_text": None,
                })
        except Exception as exc:
            log.warning(f"Google News RSS {gn_source} failed: {exc}")

    return articles


def fetch_articles() -> list[dict]:
    """V19.1: 3-Tier OSINT Article Sourcing — NewsAPI → GDELT → RSS."""
    log.info("\n" + "=" * 60)
    log.info("V19.1: 3-Tier OSINT Article Sourcing")
    log.info("=" * 60)

    # Tier 1: NewsAPI (premium structured data)
    log.info("\n--- TIER 1: NewsAPI ---")
    tier1 = _fetch_newsapi()

    # Tier 2: GDELT (global real-time event monitoring)
    log.info("\n--- TIER 2: GDELT 2.0 ---")
    tier2 = _fetch_gdelt()

    # Tier 3: RSS (direct feeds + Google News)
    log.info("\n--- TIER 3: RSS Feeds ---")
    tier3 = _fetch_rss()

    # Merge & deduplicate by URL hash
    all_articles = tier1 + tier2 + tier3
    seen_hashes = set()
    deduped = []
    for a in all_articles:
        h = url_hash(a.get("link", ""))
        if h not in seen_hashes:
            seen_hashes.add(h)
            deduped.append(a)

    log.info(f"Total articles fetched: {len(all_articles)} (T1:{len(tier1)} T2:{len(tier2)} T3:{len(tier3)}) → {len(deduped)} after dedup")
    return deduped


# ===========================================================================
# 3. GEOPOLITICS FILTER
# ===========================================================================

def _is_excluded(text: str) -> bool:
    return any(m in text.lower() for m in EXCLUDE_MARKERS)

def _is_rejected(text: str) -> bool:
    """V3.7 Rejection Firewall: block sports, entertainment, domestic noise."""
    low = text.lower()
    return any(kw in low for kw in REJECTION_KEYWORDS)

def _is_geopolitics(text: str) -> bool:
    return any(kw in text.lower() for kw in GEOPOLITICS_KEYWORDS)

def filter_geopolitics(articles: list[dict]) -> list[dict]:
    filtered = []
    rejected = 0
    for a in articles:
        combined = f"{a['title']} {a['summary']} {a.get('link', '')}"
        if _is_rejected(combined):
            rejected += 1
            continue
        if _is_excluded(combined):
            continue
        if _is_geopolitics(combined):
            filtered.append(a)
    log.info(f"After geopolitics filter: {len(filtered)} (rejected {rejected} noise)")
    return filtered


# ===========================================================================
# 4. KINETIC SCORING & SEVERITY SORTING
# ===========================================================================

KINETIC_KEYWORDS = [
    'dead', 'injured', 'killed', 'strike', 'bombed', 'attacked',
    'casualty', 'offensive', 'missile', 'assassination',
]

def _kinetic_score(article: dict) -> int:
    """V8.9: Score articles by kinetic warfare keyword density."""
    combined = f"{article.get('title', '')} {article.get('summary', '')}".lower()
    return sum(1 for kw in KINETIC_KEYWORDS if kw in combined)

def _keyword_severity(article: dict) -> float:
    """V8.9: Kinetic-first scoring. Higher kinetic = more negative = sorted first."""
    kinetic = _kinetic_score(article)
    combined = f"{article['title']} {article.get('summary', '')}".lower()
    legacy = 0.0
    for idx, kw in enumerate(SEVERITY_KEYWORDS):
        if kw in combined:
            legacy -= (1.0 - idx * 0.1)
    return -(kinetic * 10) + legacy  # kinetic dominates

def sort_by_priority(articles: list[dict]) -> list[dict]:
    """V8.9: Sort by kinetic score (most urgent first), then recency."""
    def key(a):
        pub = a.get("pub_date")
        if pub and pub.tzinfo:
            ts = pub.timestamp()
        elif pub:
            ts = pub.replace(tzinfo=timezone.utc).timestamp()
        else:
            ts = 0
        severity = _keyword_severity(a)
        return (severity, -ts)  # most negative first, then most recent
    return sorted(articles, key=key)


# ===========================================================================
# 5. POSTED LINKS TRACKER
# ===========================================================================

def load_posted() -> dict:
    if POSTED_LINKS_FILE.exists():
        try:
            with open(POSTED_LINKS_FILE, "r") as f:
                data = json.load(f)
            if isinstance(data, list):
                log.warning("posted_links.json list \u2192 dict conversion")
                converted = {}
                for item in data:
                    if isinstance(item, str):
                        h = hashlib.sha256(item.encode("utf-8")).hexdigest()
                        converted[h] = {"url": item, "timestamp": "unknown"}
                    elif isinstance(item, dict) and "url" in item:
                        h = hashlib.sha256(item["url"].encode("utf-8")).hexdigest()
                        converted[h] = item
                return converted
            if not isinstance(data, dict):
                return {}
            return data
        except Exception:
            pass
    return {}

def save_posted(data: dict):
    # Keep only the 150 most recent links to prevent permanent lockup/starvation
    MAX_MEMORY_SIZE = 150
    if len(data) > MAX_MEMORY_SIZE:
        log.info(f"  [SYSTEM] Memory full. Pruning oldest {len(data) - MAX_MEMORY_SIZE} links.")
        # Sort by timestamp and keep newest 150 (since it's a dict)
        sorted_keys = sorted(data.keys(), key=lambda k: data[k].get("published", ""), reverse=True)
        new_data = {k: data[k] for k in sorted_keys[:MAX_MEMORY_SIZE]}
        data = new_data
        
    with open(POSTED_LINKS_FILE, "w") as f:
        json.dump(data, f, indent=2)

def url_hash(url: str) -> str:
    return hashlib.sha256(url.encode("utf-8")).hexdigest()

def is_posted(link: str, posted: dict) -> bool:
    return url_hash(link) in posted

def _is_headline_duplicate(headline: str, posted: dict) -> bool:
    """V19.0: Deep Semantic Memory — LLM-based dedup with SequenceMatcher fallback."""
    if not headline or not posted:
        return False

    # Extract last 20 posted headlines for comparison
    recent_entries = sorted(
        posted.values(),
        key=lambda x: x.get("published", ""),
        reverse=True
    )[:20]
    recent_titles = [e.get("title", "").strip() for e in recent_entries if e.get("title", "").strip()]

    if not recent_titles:
        return False

    # === PRIMARY: LLM Semantic Check via Groq (Tier 1) ===
    groq_key = os.environ.get("GROQ_API_KEY")
    if groq_key:
        try:
            from groq import Groq
            client = Groq(api_key=groq_key)

            titles_block = "\n".join(f"- {t}" for t in recent_titles)
            dedup_prompt = (
                f"Compare this new headline to this list of our last {len(recent_titles)} posted headlines. "
                f"Reply with 'DUPLICATE' if it covers the exact same event, or 'UNIQUE' if it is a genuinely new development.\n\n"
                f"New headline: {headline}\n\n"
                f"Posted headlines:\n{titles_block}\n\n"
                f"Reply with ONLY one word: DUPLICATE or UNIQUE."
            )

            response = client.chat.completions.create(
                model="llama-3.1-8b-instant",
                messages=[{"role": "user", "content": dedup_prompt}],
                temperature=0.0,
                max_tokens=10,
            )
            verdict = (response.choices[0].message.content or "").strip().upper()
            if "DUPLICATE" in verdict:
                log.info(f"  [V19.0 DEDUP] LLM verdict: DUPLICATE for '{headline[:50]}'")
                return True
            elif "UNIQUE" in verdict:
                log.info(f"  [V19.0 DEDUP] LLM verdict: UNIQUE for '{headline[:50]}'")
                return False
            else:
                log.warning(f"  [V19.0 DEDUP] Ambiguous LLM response: '{verdict}'. Falling back to SequenceMatcher.")
        except Exception as e:
            log.warning(f"  [V19.0 DEDUP] Groq dedup failed: {e}. Falling back to SequenceMatcher.")

    # === FALLBACK: SequenceMatcher (V8.9 legacy) ===
    headline_lower = headline.lower().strip()
    for entry in posted.values():
        old_title = entry.get("title", "").lower().strip()
        if old_title and SequenceMatcher(None, headline_lower, old_title).ratio() > 0.60:
            log.info(f"  Semantic dedup (fallback): '{headline[:50]}' ~= '{old_title[:50]}'")
            return True
    return False

def mark_posted(link: str, pub_date, posted: dict, title: str = "") -> dict:
    if not isinstance(posted, dict):
        posted = {}
    h = url_hash(link)
    posted[h] = {
        "url": link,
        "title": title,
        "published": pub_date.isoformat() if pub_date else datetime.now(timezone.utc).isoformat(),
    }
    return posted


# ===========================================================================
# 5B. AI USAGE TRACKER
# ===========================================================================

def load_ai_usage() -> dict:
    if AI_USAGE_FILE.exists():
        try:
            with open(AI_USAGE_FILE, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {"total_calls": 0, "tiers": {"openrouter": 0, "groq": 0, "gemini": 0}, "log": []}

def save_ai_usage(data: dict):
    try:
        with open(AI_USAGE_FILE, "w") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        log.warning(f"Failed to save AI usage: {e}")

def track_ai_usage(tier_name: str, article_title: str):
    try:
        usage = load_ai_usage()
        usage["total_calls"] = usage.get("total_calls", 0) + 1
        if "tiers" not in usage:
            usage["tiers"] = {}
        usage["tiers"][tier_name] = usage["tiers"].get(tier_name, 0) + 1
        if "log" not in usage:
            usage["log"] = []
        usage["log"].append({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "tier": tier_name,
            "article": article_title
        })
        usage["log"] = usage["log"][-100:]  # Keep last 100 entries
        save_ai_usage(usage)
    except Exception as e:
        log.warning(f"Failed to track AI usage: {e}")


# ===========================================================================
# 6. TRAFILATURA EXTRACTION + INTELLIGENT SELECTION
# ===========================================================================

# V3.7 Deep regex scrubbing patterns
JUNK_REGEX_PATTERNS = [
    r"list of \d+ items?[^.]*",
    r"recommended stories[^.]*",
    r"the take:[^.]*",
    r"read more:[^.]*",
    r"click here[^.]*",
    r"subscribe to[^.]*",
    r"sign up for[^.]*",
    r"advertisement[^.]*",
    r"\d+ of \d+[^.]*",
    r"newsletter[^.]*",
    r"follow us[^.]*",
    r"share this[^.]*",
    r"privacy policy[^.]*",
    r"terms of use[^.]*",
    r"all rights reserved[^.]*",
    r"cookie[^.]*consent[^.]*",
    # V6.0: Block date metadata from becoming summary sentences
    r"published on \d{1,2} \w+ \d{4}[^.]*",
    r"updated:?\s*\d{1,2}[^.]*\d{4}[^.]*",
    r"last updated[^.]*",
    r"published:?\s*\d{1,2}[^.]*",
    r"your phone[^.]*",
    r"a rare metal[^.]*",
    r"related:?[^.]*",
    r"also read[^.]*",
    r"watch:?[^.]*video[^.]*",
]

def _deep_scrub(text: str) -> str:
    """V3.7 Deep regex scrubbing to remove all UI artifacts."""
    for pattern in JUNK_REGEX_PATTERNS:
        text = re.sub(pattern, "", text, flags=re.IGNORECASE)
    # Also remove lines that are too short (nav fragments)
    lines = text.split("\n")
    cleaned = [l for l in lines if len(l.strip()) >= 15]
    result = "\n".join(cleaned).strip()
    # Collapse multiple whitespace
    result = re.sub(r"\s{3,}", "  ", result)
    log.info(f"  Deep scrub: {len(text)} -> {len(result)} chars")
    return result


def extract_article(url: str) -> dict | None:
    """V11.7: Cloudscraper Anti-Bot Hardening + Hybrid Extraction."""
    try:
        scraper = cloudscraper.create_scraper()
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml"
        }
        response = scraper.get(url, headers=headers, timeout=15, allow_redirects=True)
        response.raise_for_status()
        
        # Try Trafilatura first
        text = trafilatura.extract(response.text, include_comments=False)
        
        # Fallback to BeautifulSoup if Trafilatura fails
        soup = BeautifulSoup(response.content, 'html.parser')
        if not text or len(text) < 150:
            paragraphs = soup.find_all('p')
            text = ' '.join([p.get_text() for p in paragraphs])
            
        if not text or len(text) < 150:
            print("  [WARNING] Extraction failed: Article text hidden by JS paywall.")
            return None
            
        text = _deep_scrub(text)
        if len(text) < MIN_EXTRACT_CHARS:
            print("  [WARNING] Extraction failed: Text too short after deep scrub.")
            return None
            
        title = ""
        og_title = soup.find("meta", property="og:title")
        if og_title and og_title.get("content"):
            title = og_title["content"]
        image = ""
        og_img = soup.find("meta", property="og:image")
        if og_img and og_img.get("content"):
            image = og_img["content"]
        source = ""
        og_site = soup.find("meta", property="og:site_name")
        if og_site and og_site.get("content"):
            source = og_site["content"]
            
        return {"text": text, "title": title, "image": image, "date": "", "source": source}
    except Exception as e:
        log.warning(f"  Extraction failed: {type(e).__name__} for {url}")
        return None


def _fallback_scrape_image(url: str) -> str | None:
    try:
        resp = requests.get(url, headers=HTTP_HEADERS, timeout=10)
        if resp.status_code != 200:
            return None
        soup = BeautifulSoup(resp.text, "html.parser")
        og = soup.find("meta", property="og:image")
        if og and og.get("content"):
            return og["content"]
    except Exception:
        pass
    return None


def _is_too_old(article: dict) -> bool:
    """V15.6: Reject articles older than MAX_ARTICLE_AGE_HOURS with Iranian date fix."""
    pub = article.get("pub_date")
    if not pub:
        return False  # Give benefit of doubt if no date
    now = datetime.now(timezone.utc)
    if not pub.tzinfo:
        pub = pub.replace(tzinfo=timezone.utc)
    age_hours = (now - pub).total_seconds() / 3600
    # V18.27: Only bypass negative timestamps (clock skew), not genuinely old articles
    if age_hours < 0:
        log.info(f"  [FIX] Bypassing clock skew (age={age_hours:.1f}h). Assuming fresh.")
        age_hours = 1.0  # Treat as 1 hour old
    if age_hours > MAX_ARTICLE_AGE_HOURS:
        log.info(f"  Rejected (age: {age_hours:.1f}h > {MAX_ARTICLE_AGE_HOURS}h)")
        return True
    return False


def select_and_extract_batch(articles: list[dict], posted: dict) -> list[dict]:
    """V9.6: Smart Queue Logic. Pre-filter, then dynamically extract until we hit 2 Kinetic, 1 General."""
    sorted_a = sort_by_priority(articles)
    
    valid_articles = []
    
    # Pre-filter all articles without deep scraping
    for a in sorted_a:
        if not a or not isinstance(a, dict):
            continue
        link = a.get("link", "")
        if not link or is_posted(link, posted):
            continue
        # V8.9: Semantic headline deduplication
        if _is_headline_duplicate(a.get("title", ""), posted):
            continue
        # V4.0: Recency firewall
        if _is_too_old(a):
            continue
            
        real_url = resolve_google_news_url(link)
        a["real_url"] = real_url
        valid_articles.append(a)

    if not valid_articles:
        return []

    # Queue Separation
    kinetic_queue = [a for a in valid_articles if _kinetic_score(a) > 0]
    general_queue = [a for a in valid_articles if _kinetic_score(a) == 0]

    final_batch = []
    
    def _try_extract(article: dict) -> bool:
        log.info(f"Targeting: {article['title'][:70]}\u2026")
        extracted = extract_article(article["real_url"])
        
        # 1. Try standard text extraction
        extracted_text = extracted.get("text") if extracted and isinstance(extracted, dict) else None
        
        # 2. Fallback to RSS summary if text is blocked
        if not extracted_text or len(extracted_text) < 100:
            log.info("  [WARNING] Full text extraction failed or too short. Using RSS summary fallback.")
            extracted_text = article.get("summary") or article.get("description", "")
            
        # 3. SMART FILTER: Ultimate fallback to the Headline itself
        if not extracted_text or len(extracted_text) < 20:
            log.info(f"  [SMART FILTER] Paywall detected for {article['real_url']}. Falling back to Headline.")
            extracted_text = article.get("title")

        if not is_combat_relevant(extracted_text) and not is_combat_relevant(article.get('title', '')):
            log.info(f"  [SKIP] Out of context (No combat/missile keywords): {article.get('title', '')}")
            return False

        article["full_text"] = extracted_text
        log.info(f"  Extracted/Fallback text: {len(extracted_text)} chars \u2713")

        if extracted and isinstance(extracted, dict):
            if extracted.get("title"):
                article["title"] = extracted["title"]
            if extracted.get("image"):
                article["image_url"] = extracted["image"]
            elif not article.get("image_url"):
                fb = _fallback_scrape_image(article["real_url"])
                if fb:
                    article["image_url"] = fb
            if extracted.get("source"):
                article["source"] = extracted["source"]
            if extracted.get("date"):
                pd = parse_date_bulletproof(extracted["date"])
                if pd:
                    article["pub_date"] = pd
        else:
            if not article.get("image_url"):
                fb = _fallback_scrape_image(article["real_url"])
                if fb:
                    article["image_url"] = fb
        
        return True

    # V11.3: Dynamic Proportional Quota
    target_kinetic = max(1, BATCH_SIZE - 1)
    target_general = BATCH_SIZE - target_kinetic

    # 1. Fill Kinetic Quota
    kinetic_count = 0
    for a in kinetic_queue:
        if kinetic_count >= target_kinetic:
            break
        if _try_extract(a):
            final_batch.append(a)
            kinetic_count += 1
            log.info(f"  \u2713 Kinetic Slot Filled ({kinetic_count}/{target_kinetic})")

    # 2. Fill General Quota
    general_count = 0
    for a in reversed(general_queue):
        if general_count >= target_general:
            break
        if _try_extract(a):
            final_batch.append(a)
            general_count += 1
            log.info(f"  \u2713 General Slot Filled ({general_count}/{target_general})")

    # 3. Fallback Filler
    if len(final_batch) < BATCH_SIZE:
        log.info(f"  Quota not met ({len(final_batch)}/{BATCH_SIZE}). Pulling from remaining valid articles...")
        for a in valid_articles:
            if len(final_batch) >= BATCH_SIZE:
                break
            if a not in final_batch:
                if _try_extract(a):
                    final_batch.append(a)
                    log.info(f"  \u2713 Fallback Slot Filled ({len(final_batch)}/{BATCH_SIZE})")

    # V19.0: OSINT Triangulation — bundle + cross-reference similar articles
    if len(final_batch) >= 2:
        final_batch = _triangulate_articles(final_batch)

    return final_batch




# ===========================================================================
# 6B. V19.0 OSINT TRIANGULATION ENGINE
# ===========================================================================

_TRIANGULATION_PROMPT_TEMPLATE = """You are an elite OSINT analyst and social media growth expert for the breaking news channel @geopolitics.
I am providing multiple reports on the same event from different sources. Cross-reference them, eliminate bias, and output one unified, verified intelligence brief.

The current real-time clock is: {current_time}.

Report 1:
Headline: {headline_1}
Source: {source_1}
Text: {text_1}

Report 2:
Headline: {headline_2}
Source: {source_2}
Text: {text_2}

Return strict JSON with exactly 6 keys:
- "instagram_caption": Write a highly engaging, algorithm-optimized caption using this STRICT structure:
  1. THE HOOK: Start with a hard-hitting, real-time breaking news indicator using an emoji (e.g., 🚨 BREAKING:, ⚡ JUST IN:). You MUST reference the current time or state that this is happening "right now" or "minutes ago".
  2. THE BRIEF: Write 2 clinical, objective sentences summarizing the verified facts from both reports. Eliminate any single-source bias.
  3. THE MACRO: Add 1 sentence explaining the broader GEOPOLITICAL IMPACT (why this shifts the balance of power).
  4. THE ENGAGEMENT TRAP: End the text with one sharp, highly analytical question designed to force people to debate in the comments + "👇".
- "dynamic_hashtags": Generate 5-7 hyper-specific hashtags based ONLY on the exact entities, cities, weapons, or leaders mentioned. THE SPAM BAN: You are strictly FORBIDDEN from using generic, mass-produced hashtags like #news, #worldnews, #geopolitics, #war, or #viral. Every tag must be strictly unique to the tactical event. Always end the block with your branded tag #geopolitics.
- "flags": A list of up to two 2-letter ISO country codes (lowercase) of the PRIMARY nations physically involved.
- "threat_level": Rate the geopolitical severity as an integer from 1 to 10.
- "video_overlays": An array of 5 to 7 short, punchy sentences (MAXIMUM 40 characters per sentence) that tell the verified story.
- "image_hook": Write exactly 1 to 2 sentences summarizing the verified event. Write it like a viral military Twitter post.

Return ONLY the JSON object, no markdown, no explanation."""

def _jaccard_similarity(title_a: str, title_b: str) -> float:
    """V19.0: Jaccard similarity on title word sets for triangulation clustering."""
    words_a = set(title_a.lower().split())
    words_b = set(title_b.lower().split())
    if not words_a or not words_b:
        return 0.0
    intersection = words_a & words_b
    union = words_a | words_b
    return len(intersection) / len(union)

def _triangulate_articles(batch: list[dict]) -> list[dict]:
    """V19.0: OSINT Triangulation — find similar article pairs, cross-reference via AI."""
    if len(batch) < 2:
        return batch

    log.info("  [V19.0 TRIANGULATION] Scanning batch for cross-referenceable clusters...")
    used_indices = set()
    merged_articles = []

    for i in range(len(batch)):
        if i in used_indices:
            continue
        best_match = -1
        best_sim = 0.0
        for j in range(i + 1, len(batch)):
            if j in used_indices:
                continue
            sim = _jaccard_similarity(
                batch[i].get("title", ""),
                batch[j].get("title", "")
            )
            if sim > best_sim:
                best_sim = sim
                best_match = j

        if best_sim > 0.40 and best_match >= 0:
            # Found a cluster — triangulate
            a1, a2 = batch[i], batch[best_match]
            log.info(f"  [TRIANGULATION] Clustering: '{a1['title'][:40]}' + '{a2['title'][:40]}' (sim={best_sim:.2f})")
            used_indices.add(i)
            used_indices.add(best_match)

            try:
                prompt = _TRIANGULATION_PROMPT_TEMPLATE.format(
                    current_time=_goat_timestamp(),
                    headline_1=a1.get("title", ""),
                    source_1=a1.get("source", "Unknown"),
                    text_1=(a1.get("full_text") or a1.get("summary", ""))[:2000],
                    headline_2=a2.get("title", ""),
                    source_2=a2.get("source", "Unknown"),
                    text_2=(a2.get("full_text") or a2.get("summary", ""))[:2000],
                )

                # Use the existing AI waterfall for triangulation
                tri_result = _run_ai_waterfall_raw(prompt)
                if tri_result:
                    parsed = _parse_ai_result(tri_result)
                    if parsed:
                        # Build merged article
                        merged = {
                            "title": a1.get("title", ""),  # Keep primary title
                            "link": a1.get("link", ""),
                            "real_url": a1.get("real_url", a1.get("link", "")),
                            "source": f"{a1.get('source', '')} + {a2.get('source', '')}",
                            "pub_date": a1.get("pub_date") or a2.get("pub_date"),
                            "image_url": a1.get("image_url") or a2.get("image_url"),
                            "full_text": a1.get("full_text", ""),
                            "summary": a1.get("summary", ""),
                            "instagram_caption": parsed.get("instagram_caption", ""),
                            "countries": parsed.get("countries", []),
                            "threat_level": parsed.get("threat_level", 8),
                            "video_overlays": parsed.get("video_overlays", []),
                            "image_hook": parsed.get("image_hook", ""),
                            "_triangulated": True,  # Flag: skip re-summarization in main loop
                        }
                        merged_articles.append(merged)
                        log.info(f"  [TRIANGULATION] \u2713 Merged into verified intelligence brief.")
                        continue
            except Exception as e:
                log.warning(f"  [TRIANGULATION] AI merge failed: {e}. Keeping articles separate.")

            # If merge failed, keep both
            merged_articles.append(batch[i])
            merged_articles.append(batch[best_match])
        else:
            # No match found — keep solo
            merged_articles.append(batch[i])

    log.info(f"  [TRIANGULATION] Result: {len(batch)} articles -> {len(merged_articles)} (after merge)")
    return merged_articles


# ===========================================================================
# 7B. UNIFIED AI BRAIN — GROQ → GEMINI FAILOVER
# ===========================================================================

_AI_PROMPT_TEMPLATE = """You are an elite OSINT analyst and social media growth expert for the breaking news channel @geopolitics. Read this raw text, ignoring ads/menus.

The current real-time clock is: {current_time}.

Headline: {headline}

Article text:
{text}

Return strict JSON with exactly 6 keys:
- "instagram_caption": Write a highly engaging, algorithm-optimized caption using this STRICT structure:
  1. THE HOOK: Start with a hard-hitting, real-time breaking news indicator using an emoji (e.g., \"🚨 BREAKING:\", \"⚡ JUST IN:\"). You MUST reference the current time or state that this is happening \"right now\" or \"minutes ago\".
  2. THE BRIEF: Write 2 clinical, objective sentences explaining exactly WHAT is happening on the ground.
  3. THE MACRO: Add 1 sentence explaining the broader GEOPOLITICAL IMPACT (why this shifts the balance of power).
  4. THE ENGAGEMENT TRAP: End the text with one sharp, highly analytical question designed to force people to debate in the comments + \"👇\".
  Use simple English. No robotic language.
- "dynamic_hashtags": Generate exactly 5-7 hyper-specific hashtags based ONLY on the exact entities, cities, weapons, or leaders mentioned. THE SPAM BAN: You are strictly FORBIDDEN from using generic, mass-produced hashtags like #news, #worldnews, #geopolitics, #war, or #viral. Every tag must be strictly unique to the tactical event. Always end the block with your branded tag #geopolitics.
- "flags": A list of up to two 2-letter ISO country codes (lowercase) of the PRIMARY nations physically involved in this specific event. DO NOT blindly default to \"us\" and \"ir\". Be highly specific to the article text.
- "threat_level": Rate the geopolitical severity as an integer from 1 to 10. Return ONLY the integer.
- "video_overlays": An array of 5 to 7 short, punchy Hinglish sentences (MAXIMUM 40 characters per sentence) that tell the story of this event.
- "image_hook": Write exactly 1 to 2 sentences summarizing the event like a viral military Twitter post. Extremely simple English.

Return ONLY the JSON object, no markdown, no explanation."""


def _parse_ai_result(result: dict) -> dict | None:
    """V14.0: Parse simplified AI response with instagram_caption."""
    countries = result.get("flags", result.get("countries", []))
    instagram_caption = result.get("instagram_caption", "")
    video_overlays = result.get("video_overlays", [])
    image_hook = result.get("image_hook", "")

    if not instagram_caption and not image_hook:
        return None

    out = {
        "instagram_caption": instagram_caption,
        "countries": countries,
        "video_overlays": video_overlays,
        "image_hook": image_hook,
    }
    try:
        out["threat_level"] = int(result.get("threat_level", 8))
    except (ValueError, TypeError):
        out["threat_level"] = 8

    return out


def _strip_markdown_json(text: str) -> str:
    """V9.7: Brutally strip markdown ```json fences from AI responses before parsing."""
    cleaned_text = text.replace('```json', '').replace('```', '').strip()
    return cleaned_text




def generate_intelligence_cascade(article_title: str, article_text: str) -> dict | None:
    """
    V12.1: 3-Tier API Waterfall (Zero Downtime).
    Tries Groq (Llama 3) -> Gemini 2.5 Flash -> OpenRouter in order.
    No time.sleep() needed, it just falls back instantly on hit rate limits.
    """
    input_text = article_text[:4000] if len(article_text) > 4000 else article_text
    prompt = _AI_PROMPT_TEMPLATE.format(current_time=_goat_timestamp(), headline=article_title, text=input_text)

    # === ATTEMPT 1: GROQ (Meta Llama 3) ===
    groq_key = os.environ.get("GROQ_API_KEY")
    if groq_key:
        try:
            from groq import Groq
            client = Groq(api_key=groq_key)

            response = client.chat.completions.create(
                model="llama-3.1-8b-instant",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=4000,
                response_format={"type": "json_object"},
            )

            resp_text = _strip_markdown_json(response.choices[0].message.content or "")
            if resp_text:
                raw = json.loads(resp_text)
                result = _parse_ai_result(raw)
                if result:
                    log.info(f"  \u2728 Groq AI Success \u2728")
                    track_ai_usage("groq", article_title)
                    return result
        except ImportError:
            log.warning("  groq package not installed")
            print("[WARNING] Tier 1 (Llama-3.1-8b-instant) failed: Missing groq package")
        except Exception as e:
            if "429" in str(e) or "rate limit" in str(e).lower() or "resource exhausted" in str(e).lower():
                print("[INFO] Rate limit hit on Tier 1. Cooling down for 5 seconds...")
                time.sleep(5)
            log.warning(f"  [FALLBACK] Groq failed: {e}. Falling back to Gemini...")
            print(f"[WARNING] Tier 1 (Llama-3.1-8b-instant) failed: {e}")

    # === ATTEMPT 2: GEMINI (2.5 Flash) ===
    gemini_key = os.environ.get("GEMINI_API_KEY")
    if gemini_key:
        try:
            from google import genai
            client = genai.Client(api_key=gemini_key)
            
            response = client.models.generate_content(
                model='gemini-2.5-flash',
                contents=prompt,
            )
            
            resp_text = _strip_markdown_json(response.text if response.text else "")
            if resp_text:
                raw = json.loads(resp_text)
                result = _parse_ai_result(raw)
                if result:
                    log.info(f"  \u2728 Gemini AI Success \u2728")
                    track_ai_usage("gemini", article_title)
                    return result
        except ImportError:
            log.warning("  google-genai not installed")
            print("[WARNING] Tier 2 (Gemini-2.5-Flash) failed: Missing google-genai package")
        except Exception as e:
            if "429" in str(e) or "rate limit" in str(e).lower() or "resource exhausted" in str(e).lower():
                print("[INFO] Rate limit hit on Tier 2. Cooling down for 5 seconds...")
                time.sleep(5)
            log.warning(f"  [FALLBACK] Gemini failed: {e}. Falling back to OpenRouter...")
            print(f"[WARNING] Tier 2 (Gemini-2.5-Flash) failed: {e}")
            
    # === ATTEMPT 3: OPENROUTER (Gemini 2.0 Flash Lite) ===
    or_key = os.environ.get("OPENROUTER_API_KEY")
    if or_key:
        try:
            from openai import OpenAI
            client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=or_key)
            
            response = client.chat.completions.create(
                model="google/gemini-2.0-flash-lite-preview-02-05:free",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=4000,
                response_format={"type": "json_object"},
            )
            
            resp_text = _strip_markdown_json(response.choices[0].message.content or "")
            if resp_text:
                raw = json.loads(resp_text)
                result = _parse_ai_result(raw)
                if result:
                    log.info(f"  \u2728 OpenRouter AI Success \u2728")
                    track_ai_usage("openrouter", article_title)
                    return result
        except ImportError:
            log.warning("  openai package not installed for OpenRouter")
            print("[WARNING] Tier 3 (Gemini 2.0 Flash Lite) failed: Missing openai package")
        except Exception as e:
            if "429" in str(e) or "rate limit" in str(e).lower() or "resource exhausted" in str(e).lower():
                print("[INFO] Rate limit hit on Tier 3. Cooling down for 5 seconds...")
                time.sleep(5)
            log.warning(f"  [FATAL] OpenRouter fallback failed: {e}")
            print(f"[WARNING] Tier 3 (Gemini 2.0 Flash Lite) failed: {e}")

    # If all 3 fail:
    print(f"[ERROR] API Waterfall exhausted. Skipping article.")
    raise Exception("All 3 AI APIs failed in cascade.")


def _run_ai_waterfall_raw(prompt: str) -> dict | None:
    """V19.0: Raw AI waterfall for arbitrary prompts (used by triangulation & RL loop)."""
    # === ATTEMPT 1: GROQ ===
    groq_key = os.environ.get("GROQ_API_KEY")
    if groq_key:
        try:
            from groq import Groq
            client = Groq(api_key=groq_key)
            response = client.chat.completions.create(
                model="llama-3.1-8b-instant",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=4000,
                response_format={"type": "json_object"},
            )
            resp_text = _strip_markdown_json(response.choices[0].message.content or "")
            if resp_text:
                return json.loads(resp_text)
        except Exception as e:
            log.warning(f"  [AI RAW] Groq failed: {e}")

    # === ATTEMPT 2: GEMINI ===
    gemini_key = os.environ.get("GEMINI_API_KEY")
    if gemini_key:
        try:
            from google import genai
            client = genai.Client(api_key=gemini_key)
            response = client.models.generate_content(
                model='gemini-2.5-flash',
                contents=prompt,
            )
            resp_text = _strip_markdown_json(response.text if response.text else "")
            if resp_text:
                return json.loads(resp_text)
        except Exception as e:
            log.warning(f"  [AI RAW] Gemini failed: {e}")

    # === ATTEMPT 3: OPENROUTER ===
    or_key = os.environ.get("OPENROUTER_API_KEY")
    if or_key:
        try:
            from openai import OpenAI
            client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=or_key)
            response = client.chat.completions.create(
                model="google/gemini-2.0-flash-lite-preview-02-05:free",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=4000,
                response_format={"type": "json_object"},
            )
            resp_text = _strip_markdown_json(response.choices[0].message.content or "")
            if resp_text:
                return json.loads(resp_text)
        except Exception as e:
            log.warning(f"  [AI RAW] OpenRouter failed: {e}")

    return None


# ===========================================================================
# 7C. V19.0 REINFORCEMENT LEARNING LOOP (MIDNIGHT RUN)
# ===========================================================================

def load_brain_weights() -> None:
    """V19.0: Load learned engagement weights and inject into scoring systems."""
    if not BRAIN_WEIGHTS_FILE.exists():
        log.info("  [BRAIN] No brain_weights.json found. Running with default keywords.")
        return

    try:
        with open(BRAIN_WEIGHTS_FILE, "r") as f:
            data = json.load(f)

        keywords = data.get("boosted_keywords", [])
        if not keywords:
            log.info("  [BRAIN] brain_weights.json exists but has no boosted keywords.")
            return

        injected = 0
        for kw in keywords:
            kw_lower = kw.lower().strip()
            if kw_lower and kw_lower not in COMBAT_KEYWORDS:
                COMBAT_KEYWORDS.append(kw_lower)
                injected += 1
            if kw_lower and kw_lower not in KINETIC_KEYWORDS:
                KINETIC_KEYWORDS.append(kw_lower)  # Brain-boosted for kinetic scoring

        log.info(f"  [BRAIN] \u2728 Loaded {injected} brain-boosted keywords: {keywords}")
        log.info(f"  [BRAIN] COMBAT_KEYWORDS now: {len(COMBAT_KEYWORDS)} | KINETIC_KEYWORDS now: {len(KINETIC_KEYWORDS)}")
    except Exception as e:
        log.warning(f"  [BRAIN] Failed to load brain_weights.json: {e}")


def analyze_past_performance() -> None:
    """V19.0: Midnight Run — fetch IG engagement data via Meta Graph API and generate brain weights."""
    log.info("\n" + "=" * 60)
    log.info("V19.0: MIDNIGHT RUN — Reinforcement Learning Analysis")
    log.info("=" * 60)

    meta_token = os.environ.get("META_ACCESS_TOKEN", "")
    ig_user_id = os.environ.get("META_IG_USER_ID", "")

    performance_data = []

    # === Phase 1: Fetch engagement data from Meta Graph API ===
    if meta_token and ig_user_id:
        log.info("  [MIDNIGHT] Fetching Instagram engagement via Meta Graph API...")
        try:
            url = f"https://graph.facebook.com/v19.0/{ig_user_id}/media"
            params = {
                "fields": "id,caption,like_count,comments_count,timestamp",
                "limit": 10,
                "access_token": meta_token,
            }
            resp = requests.get(url, params=params, timeout=15)
            resp.raise_for_status()
            media_items = resp.json().get("data", [])

            for item in media_items:
                performance_data.append({
                    "caption": (item.get("caption") or "")[:300],
                    "likes": item.get("like_count", 0),
                    "comments": item.get("comments_count", 0),
                    "engagement": item.get("like_count", 0) + item.get("comments_count", 0),
                })

            log.info(f"  [MIDNIGHT] Fetched {len(performance_data)} posts from Meta API.")
        except Exception as e:
            log.warning(f"  [MIDNIGHT] Meta Graph API failed: {e}. Falling back to local data.")
    else:
        log.info("  [MIDNIGHT] No META_ACCESS_TOKEN/META_IG_USER_ID. Using local posted_links data.")

    # === Phase 1B: Fallback to local posted_links.json ===
    if not performance_data:
        log.info("  [MIDNIGHT] Generating weights from local posted_links history...")
        posted = load_posted()
        recent = sorted(
            posted.values(),
            key=lambda x: x.get("published", ""),
            reverse=True
        )[:10]
        for entry in recent:
            title = entry.get("title", "")
            if title:
                performance_data.append({
                    "caption": title[:300],
                    "likes": 0,
                    "comments": 0,
                    "engagement": 0,
                })

    if not performance_data:
        log.info("  [MIDNIGHT] No performance data available. Skipping brain weight generation.")
        return

    # === Phase 2: Feed to AI for keyword extraction ===
    perf_text = "\n".join(
        f"- Caption: \"{p['caption']}\" | Likes: {p['likes']} | Comments: {p['comments']} | Total Engagement: {p['engagement']}"
        for p in performance_data
    )

    rl_prompt = (
        "Analyze this Instagram performance data from a geopolitics/military news page. "
        "What topics/keywords generated the most engagement? "
        "Output a JSON object with exactly 1 key:\n"
        '- "boosted_keywords": A JSON list of exactly 5 high-priority keywords to target tomorrow. '
        "These should be specific military/geopolitical terms (e.g. 'drone strike', 'F-35', 'hypersonic') "
        "not generic words.\n\n"
        f"Performance data:\n{perf_text}\n\n"
        "Return ONLY the JSON object, no markdown, no explanation."
    )

    try:
        result = _run_ai_waterfall_raw(rl_prompt)
        if result and "boosted_keywords" in result:
            keywords = result["boosted_keywords"]
            if isinstance(keywords, list) and len(keywords) > 0:
                brain_data = {
                    "generated_at": datetime.now(timezone.utc).isoformat(),
                    "boosted_keywords": [str(kw).lower().strip() for kw in keywords[:5]],
                    "source_posts_analyzed": len(performance_data),
                }
                with open(BRAIN_WEIGHTS_FILE, "w") as f:
                    json.dump(brain_data, f, indent=2)
                log.info(f"  [MIDNIGHT] \u2728 Brain weights saved: {brain_data['boosted_keywords']}")
            else:
                log.warning("  [MIDNIGHT] AI returned empty/invalid keyword list.")
        else:
            log.warning("  [MIDNIGHT] AI did not return boosted_keywords key.")
    except Exception as e:
        log.error(f"  [MIDNIGHT] Brain weight generation failed: {e}")



def generate_internal_summary(article: dict) -> dict:
    """
    V14.0: Triggers the API waterfall with simplified caption output.
    """
    full_text = (article.get("full_text") or "") or (article.get("summary") or "")
    headline = article.get("title", "")

    if not full_text:
        article["instagram_caption"] = headline
        article["countries"] = []
        article["image_hook"] = headline
        return article

    # Run the 3-Tier API Waterfall
    result = generate_intelligence_cascade(headline, full_text)

    article["instagram_caption"] = result.get("instagram_caption", "")
    article["countries"] = result.get("countries", [])
    article["threat_level"] = result.get("threat_level", 8)
    article["video_overlays"] = result.get("video_overlays", [])
    article["image_hook"] = result.get("image_hook", "")

    return article


# ===========================================================================
# 8. COUNTRY FLAG DETECTION (flair NER)
# ===========================================================================

# Mapping from entity text to flag code
ENTITY_TO_FLAG = {
    "united states": "us", "u.s.": "us", "us": "us", "america": "us",
    "american": "us", "americans": "us",
    "russia": "ru", "russian": "ru", "russians": "ru", "moscow": "ru",
    "ukraine": "ua", "ukrainian": "ua", "ukrainians": "ua", "kyiv": "ua",
    "china": "cn", "chinese": "cn", "beijing": "cn",
    "iran": "ir", "iranian": "ir", "iranians": "ir", "tehran": "ir", "irgc": "ir",
    "israel": "il", "israeli": "il", "israelis": "il", "idf": "il", "tel aviv": "il",
    "palestine": "ps", "palestinian": "ps", "palestinians": "ps", "gaza": "ps", "hamas": "ps",
    "north korea": "kp", "north korean": "kp", "pyongyang": "kp",
    "south korea": "kr", "south korean": "kr", "seoul": "kr",
    "taiwan": "tw", "taiwanese": "tw",
    "turkey": "tr", "turkish": "tr", "ankara": "tr",
    "india": "in", "indian": "in", "indians": "in", "new delhi": "in",
    "pakistan": "pk", "pakistani": "pk", "islamabad": "pk",
    "syria": "sy", "syrian": "sy", "damascus": "sy",
    "iraq": "iq", "iraqi": "iq", "baghdad": "iq",
    "saudi arabia": "sa", "saudi": "sa", "riyadh": "sa",
    "japan": "jp", "japanese": "jp", "tokyo": "jp",
    "britain": "gb", "british": "gb", "uk": "gb",
    "united kingdom": "gb", "london": "gb",
    "france": "fr", "french": "fr", "paris": "fr",
    "germany": "de", "german": "de", "berlin": "de",
    "yemen": "ye", "yemeni": "ye", "houthi": "ye", "houthis": "ye",
    "lebanon": "lb", "lebanese": "lb", "hezbollah": "lb", "beirut": "lb",
    "egypt": "eg", "egyptian": "eg", "cairo": "eg",
    "poland": "pl", "polish": "pl", "warsaw": "pl",
    "afghanistan": "af", "afghan": "af", "taliban": "af", "kabul": "af",
    "ethiopia": "et", "ethiopian": "et", "addis ababa": "et",
    "sudan": "sd", "sudanese": "sd", "khartoum": "sd",
    "myanmar": "mm",
    "somalia": "so", "somali": "so", "mogadishu": "so",
    "libya": "ly", "libyan": "ly", "tripoli": "ly",
    "nato": "nato",
    # V6.0: African & additional nations
    "rwanda": "rw", "rwandan": "rw", "rwandans": "rw", "kigali": "rw",
    "congo": "cd", "congolese": "cd", "drc": "cd", "dr congo": "cd", "kinshasa": "cd",
    "m23": "cd",
    "nigeria": "ng", "nigerian": "ng", "abuja": "ng", "lagos": "ng",
    "kenya": "ke", "kenyan": "ke", "nairobi": "ke",
    "south africa": "za", "south african": "za",
    "morocco": "ma", "moroccan": "ma",
    "algeria": "dz", "algerian": "dz",
    "tunisia": "tn", "tunisian": "tn",
    "mozambique": "mz",
    "cameroon": "cm", "cameroonian": "cm",
    "mali": "ml", "malian": "ml",
    "niger": "ne",
    "burkina faso": "bf",
    "senegal": "sn", "senegalese": "sn",
    "venezuela": "ve", "venezuelan": "ve", "caracas": "ve", "maduro": "ve",
    "brazil": "br", "brazilian": "br",
    "mexico": "mx", "mexican": "mx",
    "colombia": "co", "colombian": "co",
    "argentina": "ar", "argentine": "ar",
    "cuba": "cu", "cuban": "cu", "cubans": "cu", "havana": "cu",
    "haiti": "ht", "haitian": "ht",
    "honduras": "hn", "honduran": "hn",
    "guatemala": "gt", "guatemalan": "gt",
    "nicaragua": "ni", "nicaraguan": "ni",
    "dominican republic": "do",
    "indonesia": "id", "indonesian": "id",
    "philippines": "ph", "philippine": "ph", "filipino": "ph",
    "thailand": "th", "thai": "th",
    "vietnam": "vn", "vietnamese": "vn",
    "malaysia": "my", "malaysian": "my",
    "european union": "eu", "eu": "eu",
}


def detect_countries(article: dict) -> list[str]:
    """V7.0: Use Groq-detected countries, fallback to keyword scan."""
    # Prefer countries already set by Groq in generate_internal_summary
    groq_countries = article.get("countries", [])
    if groq_countries:
        log.info(f"  Flags from Groq AI: {groq_countries}")
        return groq_countries[:2]

    # Fallback: keyword scan on headline
    headline = article.get("title", "")
    if not headline:
        return []
    headline_lower = headline.lower()
    codes = []
    seen = set()
    for keyword, code in ENTITY_TO_FLAG.items():
        if keyword in headline_lower and code not in seen:
            codes.append(code)
            seen.add(code)
            if len(codes) >= 2:
                break
    if codes:
        log.info(f"  Flags from keywords: {codes}")
    else:
        log.info("  No flags detected")
    return codes

def download_flag(country_code: str) -> Image.Image | None:
    local = FLAGS_DIR / f"{country_code}.png"
    if local.exists():
        try:
            return Image.open(local).convert("RGBA")
        except Exception:
            pass
    url = f"https://flagcdn.com/w640/{country_code}.png"
    try:
        resp = requests.get(url, headers=HTTP_HEADERS, timeout=8)
        if resp.status_code == 200:
            img = Image.open(BytesIO(resp.content)).convert("RGBA")
            FLAGS_DIR.mkdir(parents=True, exist_ok=True)
            img.save(str(local), "PNG")
            # Load the image from the local file path to build the permanent local library
            return Image.open(local).convert("RGBA")
    except Exception:
        pass
    return None


# ===========================================================================
# 9. IMAGE DOWNLOAD + GRADING
# ===========================================================================

def download_article_image(article: dict) -> Image.Image | None:
    """V17.1: Cloudscraper with browser mimicry for Iranian server bypasses."""
    # V17.3: Extract URL but don't immediately abort if missing (we can use Wikipedia fallback)
    url = article.get("image_url")
    
    # V17.1: Full browser mimicry to bypass Iranian server blocks
    scraper = cloudscraper.create_scraper(browser={'browser': 'chrome', 'platform': 'windows', 'mobile': False})
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
        "Referer": "https://news.google.com/"
    }
    
    if url:
        # V18.26 Fix: Direct Local File Bypass for Telegram Engine
        if not url.startswith('http') and os.path.exists(url):
            try:
                log.info(f"  Using local image: {url}")
                return Image.open(url).convert("RGB")
            except Exception as e:
                log.warning(f"  Failed local image load: {e}")
                return None
                
        try:
            log.info(f"  Downloading image: {url[:60]}\u2026")
            response = scraper.get(url, headers=headers, timeout=20)  # V17.1: Increased timeout
            response.raise_for_status()
            
            # Failsafe: Ensure the server actually sent an image, not an HTML Cloudflare block
            content_type = response.headers.get('Content-Type', '')
            if not content_type.startswith('image/'):
                log.warning(f"  Server blocked image download (returned {content_type}).")
            else:
                image = Image.open(BytesIO(response.content)).convert("RGB")
                return image
        except Exception as e:
            log.warning(f"  Primary image download failed: {type(e).__name__}")
    
    # V17.3: Wikipedia Image Fallback
    try:
        import wikipedia
        log.info("  [FALLBACK] Attempting Wikipedia image search...")
        
        # Clean headline to get a subject query
        title = article.get("title", article.get("image_hook", ""))
        clean_title = title.replace("\U0001f6a8 BREAKING:", "").replace("BREAKING:", "").strip()
        
        # Use first 3-4 significant words as query
        words = [w for w in clean_title.split() if len(w) > 3]
        search_query = " ".join(words[:3]) if words else clean_title
        
        log.info(f"  [FALLBACK] Searching Wikipedia for: '{search_query}'")
        results = wikipedia.search(search_query, results=1)
        
        if results:
            page = wikipedia.page(results[0], auto_suggest=False)
            # Filter for valid high-res image types (avoiding SVG icons)
            valid_images = [img for img in page.images if img.lower().endswith(('.jpg', '.jpeg', '.png')) and 'icon' not in img.lower()]
            
            if valid_images:
                wiki_img_url = valid_images[0]
                log.info(f"  [FALLBACK] Found Wikipedia image for '{results[0]}': {wiki_img_url[:60]}...")
                
                wiki_resp = scraper.get(wiki_img_url, headers=headers, timeout=15)
                wiki_resp.raise_for_status()
                image = Image.open(BytesIO(wiki_resp.content)).convert("RGB")
                return image
            else:
                log.info(f"  [FALLBACK] No suitable images found on Wikipedia page for '{results[0]}'")
    except Exception as wiki_e:
        log.warning(f"  [FALLBACK] Wikipedia image search failed: {wiki_e}")
        
    return None




def _center_crop(img: Image.Image, tw: int, th: int) -> Image.Image:
    r = img.width / img.height
    tr = tw / th
    if r > tr:
        nw = int(th * r)
        img = img.resize((nw, th), Image.LANCZOS)
    else:
        nh = int(tw / r)
        img = img.resize((tw, nh), Image.LANCZOS)
    x = (img.width - tw) // 2
    y = (img.height - th) // 2
    return img.crop((x, y, x + tw, y + th))


# ===========================================================================
# 11. LOCATOR MAP / ACTOR IMAGE FALLBACK
# ===========================================================================

def get_locator_map(article: dict) -> Image.Image | None:
    countries = detect_countries(article)
    if countries:
        path = COUNTRY_MAPS_DIR / f"{countries[0]}_locator.png"
        if path.exists():
            try:
                log.info(f"  Locator map: {countries[0]}")
                return Image.open(path).convert("RGBA")
            except Exception:
                pass
    if DARK_MAP_FILE.exists():
        try:
            return Image.open(DARK_MAP_FILE).convert("RGBA")
        except Exception:
            pass
    return None


def get_actor_image(article: dict) -> Image.Image | None:
    combined = f"{article['title']} {article.get('summary', '')}".lower()
    actor_map = {
        "conflict": ["war", "attack", "strike", "airstrike", "bomb"],
        "military": ["military", "armed forces", "troops", "soldier"],
        "sanctions": ["sanctions", "embargo"],
        "nuclear": ["nuclear", "atomic"],
        "ceasefire": ["ceasefire", "truce", "peace"],
        "crisis": ["crisis", "emergency", "escalat"],
        "diplomat": ["diplomat", "ambassador", "negotiat", "summit"],
        "alliance": ["alliance", "nato", "coalition"],
    }
    for key, kws in actor_map.items():
        if any(kw in combined for kw in kws):
            path = ACTORS_DIR / f"{key}.png"
            if path.exists():
                try:
                    return Image.open(path).convert("RGBA")
                except Exception:
                    pass
    return None


# ===========================================================================
# 12. PIXEL-PERFECT TEXT WRAPPING
# ===========================================================================

def _pixel_wrap(draw, text: str, font, max_width: int, max_lines: int) -> list[str]:
    """
    Pixel-perfect word wrapping using draw.textlength().
    Packs as many words as possible per line until the pixel limit is hit.
    No textwrap module — pure pixel measurement for proportional fonts.
    """
    words = text.split()
    if not words:
        return []

    lines = []
    current_line = ""

    for word in words:
        # Try adding the next word
        test_line = f"{current_line} {word}".strip() if current_line else word
        # Measure pixel width
        try:
            line_w = draw.textlength(test_line, font=font)
        except AttributeError:
            # Fallback for older Pillow versions
            bbox = draw.textbbox((0, 0), test_line, font=font)
            line_w = bbox[2] - bbox[0]

        if line_w <= max_width:
            current_line = test_line
        else:
            # Current line is full, save it
            if current_line:
                lines.append(current_line)
                if len(lines) >= max_lines:
                    return lines
            current_line = word

            # Check if single word exceeds max width
            try:
                word_w = draw.textlength(word, font=font)
            except AttributeError:
                bbox = draw.textbbox((0, 0), word, font=font)
                word_w = bbox[2] - bbox[0]
            if word_w > max_width:
                # Truncate the word
                for i in range(len(word), 0, -1):
                    truncated = word[:i] + "\u2026"
                    try:
                        tw = draw.textlength(truncated, font=font)
                    except AttributeError:
                        bbox = draw.textbbox((0, 0), truncated, font=font)
                        tw = bbox[2] - bbox[0]
                    if tw <= max_width:
                        current_line = truncated
                        break

    # Don't forget the last line
    if current_line:
        lines.append(current_line)

    return lines[:max_lines]




# ===========================================================================
# 12B. FLAG IMAGE HELPER
# ===========================================================================

def get_flag_image(country_code: str) -> Image.Image | None:
    """V14.0: Download a small flag image for drawing on the white canvas."""
    local = FLAGS_DIR / f"{country_code}.png"
    if local.exists():
        try:
            return Image.open(local).convert("RGBA")
        except Exception:
            pass
    url = f"https://flagcdn.com/w80/{country_code.lower()}.png"
    try:
        resp = requests.get(url, headers=HTTP_HEADERS, timeout=8)
        if resp.status_code == 200:
            img = Image.open(BytesIO(resp.content)).convert("RGBA")
            FLAGS_DIR.mkdir(parents=True, exist_ok=True)
            img.save(str(local), "PNG")
            return Image.open(local).convert("RGBA")
    except Exception:
        pass
    return None


# ===========================================================================
# 13. NEWS CARD GENERATION (V14.0 — White Canvas Bulletin)
# ===========================================================================

def generate_card(article: dict, output_path: Path, threat_level: int = 8) -> None:
    """V16.4: Dynamic Typography & Image Sourcing — no cutoffs, premium font, source attribution."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    pad_x = 50

    # ── White canvas base ──
    canvas = Image.new("RGB", (CARD_WIDTH, CARD_HEIGHT), (255, 255, 255))
    draw = ImageDraw.Draw(canvas)

    # ── Premium System Font (Ubuntu/GitHub Actions) ──
    try:
        font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
        ImageFont.truetype(font_path, 20)  # Test load
    except (IOError, OSError):
        font_path = None  # Will use _load_font fallback

    # ── Prepare news image (980x550 with rounded corners) ──
    art_img = download_article_image(article)
    if not art_img:
        fallback = get_locator_map(article) or get_actor_image(article)
        if fallback:
            art_img = fallback
            
    # V17.7: Premium Image Cropping - Perfectly center-crop without distortion
    if art_img:
        news_img = ImageOps.fit(art_img.convert("RGB"), (980, 550), method=Image.Resampling.LANCZOS)
    else:
        news_img = None  # V17.7: Skip logic handled in main loop

    # ── Apply rounded corners to news image ──
    if news_img is not None:
        news_img = news_img.convert("RGBA")
        mask = Image.new("L", news_img.size, 0)
        mask_draw = ImageDraw.Draw(mask)
        mask_draw.rounded_rectangle((0, 0, news_img.size[0], news_img.size[1]), radius=40, fill=255)
        news_img.putalpha(mask)

    # ── Prepare flags (top-left) ──
    countries = detect_countries(article)
    flag_images = []
    for code in countries[:2]:
        fi = get_flag_image(code)
        if fi:
            fi.thumbnail((120, 80), Image.LANCZOS)
            flag_images.append(fi)

    # ── Paste flags at top-left ──
    flag_x = pad_x
    flag_y = 50
    for fi in flag_images:
        canvas.paste(fi, (flag_x, flag_y), fi)
        flag_x += fi.width + 20

    # ── Get the punchy image_hook text ──
    text_content = article.get("image_hook", "").strip()
    if not text_content:
        words = article.get("title", "BREAKING NEWS").split()
        text_content = " ".join(words[:15])
    text_content = smart_typography(text_content)

    # ── V18.11: Premium Typography Engine ──
    max_text_height = 280  # Space between flags (y=150) and image (y=430)
    
    # Force a smaller max font size for an elegant, premium look
    font_size = 38
    
    # Wrap text wider to form a robust paragraph
    wrap_width = 45
    line_spacing = 20  # Increased for breathability

    while font_size > 20:
        if font_path:
            font = ImageFont.truetype(font_path, font_size)
        else:
            font = _load_font("header", font_size)
            
        wrapped_text = textwrap.fill(text_content, width=wrap_width)
        # Calculate total height of wrapped text
        bbox = draw.multiline_textbbox((0, 0), wrapped_text, font=font, spacing=line_spacing)
        text_height = bbox[3] - bbox[1]
        if text_height <= max_text_height:
            break  # It fits!
        font_size -= 2  # Shrink font and try again

    # ── Draw left-aligned text ──
    draw.multiline_text((pad_x, 150), wrapped_text, fill="black", font=font, align="left", spacing=line_spacing)

    text_bottom = 150 + text_height

    # ── Paste rounded-corner news image below text ──
    if news_img is not None:
        img_y = max(text_bottom + 40, 430)  # At least y=430, or 40px below text
        # Clamp so image doesn't overflow canvas
        if img_y + 550 > CARD_HEIGHT - 60:
            img_y = CARD_HEIGHT - 550 - 60
        canvas.paste(news_img, (pad_x, img_y), news_img)

    # ── @geopoliticsoficial watermark — bottom right, light gray ──
    if font_path:
        watermark_font = ImageFont.truetype(font_path, 22)
    else:
        watermark_font = _load_font("footer", 22)
    draw.text((1040, 1050), "@geopoliticsoficial", fill=_hex("#888888"), font=watermark_font, anchor="rs")

    canvas.save(str(output_path), "PNG", quality=95)
    log.info(f"  Card saved: {output_path}")


# ===========================================================================
# 14. CAPTION GENERATION
# ===========================================================================

def generate_caption(article: dict, output_path: Path) -> None:
    """V18.30: Algorithm-optimized Instagram caption with dynamic hashtags."""
    instagram_caption = article.get("instagram_caption", "News update.")
    source = article.get("source", "Unknown")
    link = article.get("real_url", article.get("link", ""))
    dynamic_hashtags = article.get("dynamic_hashtags", "")

    # Build dynamic hashtag string from AI output
    if isinstance(dynamic_hashtags, list):
        hashtag_str = " ".join(dynamic_hashtags)
    elif isinstance(dynamic_hashtags, str) and dynamic_hashtags.strip():
        hashtag_str = dynamic_hashtags
    else:
        hashtag_str = "#geopolitics"

    caption_content = f"{instagram_caption}\n\n"
    caption_content += f"\U0001f4f0 Source: {source}\n"
    caption_content += f"\U0001f517 {link}\n\n"
    caption_content += f"Follow @geopoliticsoficial for daily intelligence. \U0001f30d\n\n"
    caption_content += f"{hashtag_str}\n"

    output_path.write_text(caption_content, encoding="utf-8")
    log.info(f"  Caption saved: {output_path}")


# ===========================================================================
# 15. FILENAME
# ===========================================================================

def get_filename_prefix() -> str:
    """V11.3: Strict D[Day]_[Time] file naming convention."""
    now = datetime.now(timezone.utc)
    day = now.isoweekday()
    time_str = now.strftime("%H%M")
    return f"D{day}_{time_str}"


# ===========================================================================
# 15.5 V11.0 OSINT VIDEO EXTRACTION & RENDERING
# ===========================================================================

def extract_and_process_video(article_url: str, headline: str, output_filepath: Path, caption_filepath: Path, summary_text: str, parsed_json: dict) -> bool:
    """V16.2: Independent-First Video Sourcing + Iranian Fallback."""
    log.info("  [OSINT] Attempting to source OSINT video footage...")
    
    # Needs a temp file for yt-dlp before FFmpeg processing
    temp_raw = output_filepath.with_name(f"{output_filepath.stem}_raw.mp4")
    
    class YTDLPLooger:
        def debug(self, msg): pass
        def warning(self, msg): pass
        def error(self, msg): pass

    ydl_opts = {
        'outtmpl': str(temp_raw),
        'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
        'quiet': True,
        'no_warnings': True,
        'logger': YTDLPLooger(),
        'match_filter': lambda info, *args, **kwargs: 'Video is too long' if info.get('duration', 0) > 180 else None,
        # V17.1: YouTube Android client bypass — avoids "Sign in to confirm" bot block
        'extractor_args': {'youtube': {'player_client': ['android']}},
    }
    
    video_found = False
    
    # V16.2: PRIMARY — Search The Independent for high-quality combat footage
    try:
        safe_query = ''.join(char for char in headline if char.isalnum() or char.isspace())
        search_query = f"ytsearch1:{safe_query} The Independent news short"
        log.info(f"  [OSINT] PRIMARY: Searching Independent video: {search_query[:80]}...")
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([search_query])
        if temp_raw.exists():
            video_found = True
            log.info("  [OSINT] ✓ Independent video sourced successfully.")
    except Exception as e:
        log.warning(f"  [OSINT] Independent search failed ({type(e).__name__}). Trying Iranian source...")
    
    # V16.3: FALLBACK — Try direct extraction from Iranian article URL
    if not video_found:
        try:
            log.info(f"  [OSINT] FALLBACK: Extracting from original URL: {article_url[:60]}...")
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([article_url])
            if temp_raw.exists():
                video_found = True
                log.info("  [OSINT] ✓ Iranian source video extracted.")
        except Exception as e:
            log.warning(f"  [OSINT] Iranian source extraction failed ({type(e).__name__}).")
    
    if not video_found or not temp_raw.exists():
        log.info("  [OSINT] No video found from any source.")
        return False
    
    return format_vertical_video(str(temp_raw), headline, output_filepath, caption_filepath, article_url, parsed_json)

def format_vertical_video(input_video: str, headline: str, output_filepath: Path, caption_filepath: Path, article_url: str, parsed_json: dict) -> bool:
    """V18.0: Standalone FFmpeg Vertical formatting (bypasses yt-dlp)."""
    try:
        # Build FFmpeg Vertical Mirror Blur + AJ+ Overlays
        log.info("  [OSINT] Processing video with FFmpeg vertical filters...")
        
        # 1. Set up the 9:16 Mirror Blur and Watermark
        watermark_text = "@geopoliticsoficial"
        fc = "[0:v]split=2[bg][fg];"
        fc += "[bg]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=20:20[bg_blurred];"
        fc += "[fg]scale=1080:1920:force_original_aspect_ratio=decrease[fg_scaled];"
        fc += "[bg_blurred][fg_scaled]overlay=(W-w)/2:(H-h)/2[merged];"
        fc += f"[merged]drawtext=text='{watermark_text}':fontcolor=white@0.4:fontsize=35:x=W-tw-30:y=50[with_wm]"
        
        # 2. Add the dynamic text overlays (AJ+ Style)
        last_node = "with_wm"
        overlay_nodes = []
        chunk_duration = 5

        overlays = parsed_json.get("video_overlays", [])
        if not overlays:
            overlays = [headline]
            
        for idx, text_chunk in enumerate(overlays):
            start_t = idx * chunk_duration
            end_t = start_t + chunk_duration
            # Sanitize text
            safe_text = text_chunk.replace("'", "").replace(":", "\\\\:").replace(",", "")
            next_node = f"v{idx}"
            # Place text in the bottom third over the blurred background
            drawtext_cmd = f"[{last_node}]drawtext=text='{safe_text}':fontcolor=white:fontsize=45:box=1:boxcolor=black@0.6:boxborderw=20:x=(W-text_w)/2:y=H-(H/3.5):enable='between(t,{start_t},{end_t})'[{next_node}]"
            overlay_nodes.append(drawtext_cmd)
            last_node = next_node

        filter_complex_str = fc + ";" + ";".join(overlay_nodes)

        command = [
            'ffmpeg', '-y', '-i', str(Path(input_video)), '-t', '90',
            '-filter_complex', filter_complex_str,
            '-map', f'[{last_node}]', '-map', '0:a?',
            '-c:v', 'libx264', '-preset', 'fast', '-c:a', 'aac', str(output_filepath)
        ]
        
        subprocess.run(command, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT, check=True)
        
        # V18.30: Build algorithm-optimized OSINT Video Caption
        instagram_caption = parsed_json.get("instagram_caption", "News update.")
        dynamic_hashtags = parsed_json.get("dynamic_hashtags", "")
        if isinstance(dynamic_hashtags, list):
            hashtag_str = " ".join(dynamic_hashtags)
        elif isinstance(dynamic_hashtags, str) and dynamic_hashtags.strip():
            hashtag_str = dynamic_hashtags
        else:
            hashtag_str = "#geopolitics"

        video_caption_content = f"{instagram_caption}\n\n"
        video_caption_content += f"\U0001f4f0 Source: {headline}\n"
        video_caption_content += f"\U0001f517 {article_url}\n\n"
        video_caption_content += "Follow @geopoliticsoficial for daily intelligence. \U0001f30d\n\n"
        video_caption_content += f"{hashtag_str}\n"

        with open(caption_filepath, "w", encoding="utf-8") as vf:
            vf.write(video_caption_content)
        
        # Cleanup
        if Path(input_video).exists():
            Path(input_video).unlink()
            
        return True
    except Exception as e:
        print(f"  [INFO] No extractable/processable video found on this page. ({e})")
        if Path(input_video).exists():
            Path(input_video).unlink()
        return False


# ===========================================================================
# 16. GOOGLE DRIVE UPLOAD
# ===========================================================================

def get_drive_service():
    try:
        from google.oauth2.credentials import Credentials
        from google.oauth2 import service_account
        from googleapiclient.discovery import build
        oauth = os.environ.get("GOOGLE_OAUTH_TOKEN_JSON")
        creds = os.environ.get("GOOGLE_CREDENTIALS_JSON")
        if oauth:
            log.info("Drive: OAuth Token")
            ci = json.loads(oauth)
            c = Credentials.from_authorized_user_info(ci, scopes=["https://www.googleapis.com/auth/drive.file"])
            return build("drive", "v3", credentials=c)
        elif creds:
            log.info("Drive: Service Account")
            ci = json.loads(creds)
            c = service_account.Credentials.from_service_account_info(
                ci, scopes=["https://www.googleapis.com/auth/drive.file"])
            return build("drive", "v3", credentials=c)
        else:
            log.warning("No Drive credentials.")
            return None
    except Exception as exc:
        log.error(f"Drive init failed: {exc}")
        return None

def find_or_create_folder(service, name, parent_id=None):
    q = f"name = '{name}' and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
    if parent_id:
        q += f" and '{parent_id}' in parents"
    r = service.files().list(q=q, spaces="drive", fields="files(id, name)",
                             includeItemsFromAllDrives=True, supportsAllDrives=True).execute()
    files = r.get("files", [])
    if files:
        return files[0]["id"]
    meta = {"name": name, "mimeType": "application/vnd.google-apps.folder"}
    if parent_id:
        meta["parents"] = [parent_id]
    f = service.files().create(body=meta, fields="id", supportsAllDrives=True).execute()
    log.info(f"  Created folder: {name}")
    return f["id"]

def upload_to_drive(service, filepath, parent_id):
    from googleapiclient.http import MediaFileUpload
    mm = {".png": "image/png", ".txt": "text/plain"}
    mt = mm.get(filepath.suffix, "application/octet-stream")
    fm = {"name": filepath.name, "parents": [parent_id]}
    media = MediaFileUpload(str(filepath), mimetype=mt)
    u = service.files().create(body=fm, media_body=media, fields="id, name", supportsAllDrives=True).execute()
    log.info(f"  Uploaded: {u.get('name')} (ID: {u.get('id')})")

# V15.3: Video-Only Drive Routing
VIDEO_DRIVE_FOLDER_ID = os.environ.get("VIDEO_DRIVE_FOLDER_ID", "")

def upload_files_to_drive(file_paths: list[Path]):
    svc = get_drive_service()
    if not svc:
        return
    try:
        ROOT_ID = os.getenv("DRIVE_ROOT_ID", "1AVFFrHH89quUE8wMO_C5XHu7T62RuBNZ")
        
        # User requested new folder structure: DD_FN----Date_FolderNumber-1,2,3
        target_folder_id = find_or_create_folder(svc, folder_name, ROOT_ID)
        
        for p in file_paths:
            if p and p.exists():
                log.info(f"  [ROUTING] Sending Asset to Target Folder: {p.name}")
                upload_to_drive(svc, p, target_folder_id)
    except Exception as exc:
        log.error(f"Drive upload failed: {exc}")


# ===========================================================================
# 17. MAIN ORCHESTRATOR (V18.30 — Content Factory)
# ===========================================================================


def run_telegram_hunter(posted_links, successful_post_counter, image_count, tg_video_count, tg_image_count, drive_queue):
    """V19.1: Telethon native Telegram video hunter with BS4 fallback."""
    print("  [SYSTEM] Engaging Telegram Video Hunter (Target: 5 Videos)...")

    TG_CHANNELS = [
        'thecradlemedia', 'middle_east_spectator', 'ResistanceTrench',
        'RNN_webed', 'PalestineResist', 'QudsNen', 'DDGeopolitics',
        'warmonitors', 'BellumActaNews', 'militarywave', 'presstv', 'CensoredMen'
    ]

    # --- V19.1: PRIMARY — Telethon Native Client ---
    tg_api_id = os.environ.get("TG_API_ID", "")
    tg_api_hash = os.environ.get("TG_API_HASH", "")
    tg_session = os.environ.get("TG_SESSION_STRING", "")

    if TELETHON_AVAILABLE and tg_api_id and tg_api_hash and tg_session:
        log.info("  [TG] Telethon credentials found. Using native MTProto client.")

        async def _telethon_hunt():
            nonlocal successful_post_counter, image_count, tg_video_count, tg_image_count

            client = TelegramClient(
                StringSession(tg_session),
                int(tg_api_id),
                tg_api_hash,
            )
            await client.start()
            log.info("  [TG] Telethon connected ✓")

            for channel in TG_CHANNELS:
                if tg_video_count >= MAX_VIDEOS:
                    log.info("  [TG] Video quota fully met! Exiting Telegram engine.")
                    break

                try:
                    entity = await client.get_entity(channel)
                    log.info(f"  [TG] Scanning channel: {channel}")

                    async for message in client.iter_messages(
                        entity, limit=20, filter=InputMessagesFilterVideo
                    ):
                        if tg_video_count >= MAX_VIDEOS:
                            break

                        # Dedup check
                        msg_link = f"tg://{channel}/{message.id}"
                        if is_posted(msg_link, posted_links):
                            continue

                        # Combat relevance filter
                        caption_text = message.text or ""
                        if not is_combat_relevant(caption_text):
                            continue

                        # Download video natively via Telethon
                        temp_video_path = str(BASE_DIR / "videos" / f"temp_tg_raw_{successful_post_counter:02d}.mp4")
                        log.info(f"  [TG] Downloading video from {channel}/{message.id}...")
                        await client.download_media(message, file=temp_video_path)

                        if not os.path.exists(temp_video_path):
                            log.warning(f"  [TG] Download failed for {channel}/{message.id}")
                            continue

                        print(f"  [TG] ✓ Video downloaded from {channel}")

                        # AI rewrite for GOAT Mode caption
                        rewrite_result = rewrite_caption_ai(caption_text)
                        if not rewrite_result:
                            rewritten_caption = caption_text[:200]
                            image_hook = rewritten_caption[:80]
                        else:
                            rewritten_caption = rewrite_result.get("rewritten_caption", "News update.")
                            image_hook = rewrite_result.get("image_hook", rewritten_caption[:80])

                        clean_caption = re.sub(r'[\*"]', '', rewritten_caption).strip()

                        final_file_path = OUTPUT_DIR / f"{successful_post_counter:02d}_Video.mp4"
                        caption_path = OUTPUT_DIR / f"{successful_post_counter:02d}_Caption.txt"

                        # FFmpeg 9:16 processing
                        print("  [TG] Applying FFmpeg vertical processing...")
                        ffmpeg_cmd = [
                            'ffmpeg', '-y', '-i', temp_video_path,
                            '-vf', 'split[original][copy];[copy]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=20:20[blurred];[original]scale=1080:1920:force_original_aspect_ratio=decrease[scaled];[blurred][scaled]overlay=(main_w-overlay_w)/2:(main_h-overlay_h)/2',
                            '-c:v', 'libx264', '-crf', '23', '-preset', 'fast', '-c:a', 'aac', '-b:a', '128k',
                            '-t', '90',
                            str(final_file_path)
                        ]
                        res = subprocess.run(ffmpeg_cmd, capture_output=True)
                        if res.returncode != 0:
                            log.error(f"  [TG] FFmpeg failed: {res.stderr.decode('utf-8', errors='replace')[:200]}")
                            if os.path.exists(temp_video_path):
                                os.unlink(temp_video_path)
                            continue

                        # Cleanup raw
                        if os.path.exists(temp_video_path):
                            os.unlink(temp_video_path)

                        # Build GOAT Mode caption with dynamic hashtags
                        dynamic_hashtags = rewrite_result.get("dynamic_hashtags", "") if rewrite_result else ""
                        if isinstance(dynamic_hashtags, list):
                            hashtag_str = " ".join(dynamic_hashtags)
                        elif isinstance(dynamic_hashtags, str) and dynamic_hashtags.strip():
                            hashtag_str = dynamic_hashtags
                        else:
                            hashtag_str = "#geopolitics"

                        with open(caption_path, "w", encoding="utf-8") as f:
                            f.write(f"{clean_caption}\n\nFollow @geopoliticsoficial for daily intelligence. \U0001f30d\n\n{hashtag_str}\n")

                        drive_queue.extend([Path(final_file_path), Path(caption_path)])
                        tg_video_count += 1
                        successful_post_counter += 1
                        mark_posted(msg_link, None, posted_links, title=image_hook)
                        log.info(f"  [TG] ✓ Video {tg_video_count}/{MAX_VIDEOS} processed from {channel}")

                except Exception as e:
                    log.warning(f"  [TG] Telethon error on {channel}: {e}")
                    continue

            await client.disconnect()

        try:
            asyncio.run(_telethon_hunt())
        except Exception as e:
            log.error(f"  [TG] Telethon async execution failed: {e}. Falling back to BS4...")
            # Fall through to BS4 fallback below

    else:
        # --- FALLBACK: Legacy BS4 HTML Scraping ---
        if not TELETHON_AVAILABLE:
            log.info("  [TG] Telethon not installed. Using BS4 HTML scraping fallback.")
        else:
            log.info("  [TG] TG_API_ID/TG_API_HASH/TG_SESSION_STRING not set. Using BS4 fallback.")

        for channel in TG_CHANNELS:
            if tg_video_count >= MAX_VIDEOS:
                print("  [TG] Video quota fully met! Exiting Telegram engine.")
                break

            url = f"https://t.me/s/{channel}"
            try:
                response = requests.get(url, timeout=15)
                soup = BeautifulSoup(response.text, 'html.parser')
                messages = soup.find_all('div', class_='tgme_widget_message')

                for msg in reversed(messages):
                    if tg_video_count >= MAX_VIDEOS:
                        break

                    msg_link = msg.get('data-post')
                    if not msg_link or is_posted(msg_link, posted_links):
                        continue

                    text_div = msg.find('div', class_='tgme_widget_message_text')
                    caption = text_div.text if text_div else ""

                    if not is_combat_relevant(caption):
                        continue

                    video_tag = msg.find('video')
                    if not (video_tag and video_tag.get('src')):
                        continue  # Video-only mode

                    media_url = video_tag['src']
                    print(f"  [TG-BS4] Found valid combat video from {channel}")

                    rewrite_result = rewrite_caption_ai(caption)
                    if not rewrite_result:
                        rewritten_caption = caption[:200]
                        image_hook = rewritten_caption[:80]
                    else:
                        rewritten_caption = rewrite_result.get("rewritten_caption", "News update.")
                        image_hook = rewrite_result.get("image_hook", rewritten_caption[:80])

                    clean_caption = re.sub(r'[\*"]', '', rewritten_caption).strip()

                    final_file_path = OUTPUT_DIR / f"{successful_post_counter:02d}_Video.mp4"
                    caption_path = OUTPUT_DIR / f"{successful_post_counter:02d}_Caption.txt"

                    media_resp = requests.get(media_url, stream=True, timeout=30)
                    media_resp.raise_for_status()

                    temp_video_path = os.path.join("videos", f"temp_tg_raw_{successful_post_counter:02d}.mp4")
                    with open(temp_video_path, 'wb') as f:
                        for chunk in media_resp.iter_content(chunk_size=8192):
                            f.write(chunk)

                    print("  [TG-BS4] Applying FFmpeg processing...")
                    ffmpeg_cmd = [
                        'ffmpeg', '-y', '-i', temp_video_path,
                        '-vf', 'split[original][copy];[copy]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=20:20[blurred];[original]scale=1080:1920:force_original_aspect_ratio=decrease[scaled];[blurred][scaled]overlay=(main_w-overlay_w)/2:(main_h-overlay_h)/2',
                        '-c:v', 'libx264', '-crf', '23', '-preset', 'fast', '-c:a', 'aac', '-b:a', '128k',
                        str(final_file_path)
                    ]
                    res = subprocess.run(ffmpeg_cmd, capture_output=True)
                    if res.returncode != 0:
                        log.error(f"  [TG-BS4] FFmpeg failed: {res.stderr.decode('utf-8', errors='replace')[:200]}")
                        continue

                    dynamic_hashtags = rewrite_result.get("dynamic_hashtags", "") if rewrite_result else ""
                    if isinstance(dynamic_hashtags, list):
                        hashtag_str = " ".join(dynamic_hashtags)
                    elif isinstance(dynamic_hashtags, str) and dynamic_hashtags.strip():
                        hashtag_str = dynamic_hashtags
                    else:
                        hashtag_str = "#geopolitics"

                    with open(caption_path, "w", encoding="utf-8") as f:
                        f.write(f"{clean_caption}\n\nFollow @geopoliticsoficial for daily intelligence. \U0001f30d\n\n{hashtag_str}\n")

                    drive_queue.extend([Path(final_file_path), Path(caption_path)])
                    tg_video_count += 1
                    successful_post_counter += 1
                    mark_posted(msg_link, None, posted_links, title=image_hook)

            except Exception as e:
                print(f"  [ERROR] Telegram BS4 scraping failed for {channel}: {e}")

    return successful_post_counter, image_count, tg_video_count, tg_image_count


def run_youtube_hunter(posted_links, successful_post_counter, tg_video_count, drive_queue):
    """V19.1: YouTube Data API v3 + yt-dlp fallback video hunter."""
    yt_api_key = os.environ.get("YOUTUBE_API_KEY", "")
    if not yt_api_key:
        log.info("  [YT] YOUTUBE_API_KEY not set. Skipping YouTube hunter.")
        return successful_post_counter, tg_video_count

    remaining = MAX_VIDEOS - tg_video_count
    if remaining <= 0:
        log.info("  [YT] Video quota already met. Skipping YouTube hunter.")
        return successful_post_counter, tg_video_count

    log.info(f"  [YT] YouTube hunter engaged. Filling {remaining} remaining video slots...")

    try:
        from googleapiclient.discovery import build as yt_build
        youtube = yt_build("youtube", "v3", developerKey=yt_api_key)

        # Build search query from top kinetic keywords
        search_query = " | ".join(KINETIC_KEYWORDS[:5]) + " news"
        published_after = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()

        log.info(f"  [YT] Search query: {search_query[:60]}…")

        search_response = youtube.search().list(
            q=search_query,
            part="snippet",
            type="video",
            order="date",
            maxResults=min(remaining + 2, 10),  # Over-fetch slightly for filtering
            publishedAfter=published_after,
            videoDuration="short",
            relevanceLanguage="en",
        ).execute()

        items = search_response.get("items", [])
        log.info(f"  [YT] Found {len(items)} YouTube results.")

        class YTDLPLogger:
            def debug(self, msg): pass
            def warning(self, msg): pass
            def error(self, msg): pass

        for item in items:
            if tg_video_count >= MAX_VIDEOS:
                break

            video_id = item.get("id", {}).get("videoId", "")
            snippet = item.get("snippet", {})
            title = snippet.get("title", "")
            description = snippet.get("description", "")

            if not video_id or not title:
                continue

            # Combat relevance check
            combined_text = f"{title} {description}"
            if not is_combat_relevant(combined_text):
                log.info(f"  [YT] Skipping non-combat video: {title[:50]}…")
                continue

            video_url = f"https://www.youtube.com/watch?v={video_id}"
            if is_posted(video_url, posted_links):
                continue

            # Download with yt-dlp
            temp_raw = str(BASE_DIR / "videos" / f"temp_yt_raw_{successful_post_counter:02d}.mp4")
            ydl_opts = {
                'outtmpl': temp_raw,
                'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
                'quiet': True,
                'no_warnings': True,
                'logger': YTDLPLogger(),
                'match_filter': lambda info, *args, **kwargs: 'Video is too long' if info.get('duration', 0) > 180 else None,
                'extractor_args': {'youtube': {'player_client': ['android']}},
            }

            try:
                log.info(f"  [YT] Downloading: {title[:60]}…")
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    ydl.download([video_url])

                if not os.path.exists(temp_raw):
                    log.warning(f"  [YT] Download failed for {video_id}")
                    continue

                # AI rewrite caption
                rewrite_result = rewrite_caption_ai(f"{title}. {description[:500]}")
                if not rewrite_result:
                    rewritten_caption = title[:200]
                    image_hook = title[:80]
                else:
                    rewritten_caption = rewrite_result.get("rewritten_caption", "News update.")
                    image_hook = rewrite_result.get("image_hook", rewritten_caption[:80])

                clean_caption = re.sub(r'[\*"]', '', rewritten_caption).strip()

                final_file_path = OUTPUT_DIR / f"{successful_post_counter:02d}_Video.mp4"
                caption_path = OUTPUT_DIR / f"{successful_post_counter:02d}_Caption.txt"

                # Build parsed_json for format_vertical_video
                parsed_json = {
                    "instagram_caption": clean_caption,
                    "video_overlays": rewrite_result.get("video_overlays", [title]) if rewrite_result else [title],
                    "dynamic_hashtags": rewrite_result.get("dynamic_hashtags", "") if rewrite_result else "",
                }

                success = format_vertical_video(
                    temp_raw, title, final_file_path, caption_path, video_url, parsed_json
                )

                if success:
                    drive_queue.extend([Path(final_file_path), Path(caption_path)])
                    tg_video_count += 1
                    successful_post_counter += 1
                    mark_posted(video_url, None, posted_links, title=image_hook)
                    log.info(f"  [YT] ✓ Video {tg_video_count}/{MAX_VIDEOS} processed from YouTube")

            except Exception as e:
                log.warning(f"  [YT] Failed to process video {video_id}: {e}")
                if os.path.exists(temp_raw):
                    os.unlink(temp_raw)
                continue

    except ImportError:
        log.warning("  [YT] google-api-python-client not available for YouTube search.")
    except Exception as e:
        log.error(f"  [YT] YouTube hunter failed: {e}")

    return successful_post_counter, tg_video_count


def rewrite_caption_ai(original_caption: str) -> dict | None:
    """V17.0: AI-rewrite an Instagram caption for copyright safety."""
    if not original_caption.strip():
        return None
    
    prompt = _IG_REWRITE_PROMPT.format(current_time=_goat_timestamp(), caption=original_caption[:2000])
    
    # Reuse the same 3-tier API waterfall
    # Attempt Groq first
    groq_key = os.environ.get("GROQ_API_KEY")
    if groq_key:
        try:
            from groq import Groq
            client = Groq(api_key=groq_key)
            response = client.chat.completions.create(
                model="llama-3.1-8b-instant",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.4,
                max_tokens=500,
                response_format={"type": "json_object"},
            )
            resp_text = _strip_markdown_json(response.choices[0].message.content or "")
            if resp_text:
                return json.loads(resp_text)
        except Exception as e:
            log.warning(f"  [IG] Groq rewrite failed: {e}")
    
    # Attempt Gemini
    gemini_key = os.environ.get("GEMINI_API_KEY")
    if gemini_key:
        try:
            from google import genai
            client = genai.Client(api_key=gemini_key)
            response = client.models.generate_content(
                model='gemini-2.5-flash',
                contents=prompt,
            )
            resp_text = _strip_markdown_json(response.text if response.text else "")
            if resp_text:
                return json.loads(resp_text)
        except Exception as e:
            log.warning(f"  [IG] Gemini rewrite failed: {e}")
    
    log.warning("  [IG] All AI tiers failed for caption rewrite.")
    return None


def main() -> None:
    log.info("=" * 60)
    log.info("Geopolitical Breaking News v19.1 — Global OSINT Syndicate")
    log.info("=" * 60)

    # V19.0: Load brain weights from reinforcement learning loop
    load_brain_weights()

    # V19.0: Midnight Run gate — if triggered by midnight cron, run analysis and exit
    run_mode = os.environ.get("RUN_MODE", "normal")
    if run_mode == "midnight_analysis":
        analyze_past_performance()
        log.info("  [MIDNIGHT] Analysis complete. Exiting without posting.")
        return

    # Ensure output directories exist for both static cards and video assets.
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    VIDEO_DIR.mkdir(parents=True, exist_ok=True)

    articles = fetch_articles()
    if not articles:
        log.info("No articles fetched. Proceeding to video engines...")
        articles = []

    geo = filter_geopolitics(articles)
    if not geo:
        log.info("No geopolitics articles. Proceeding to video engines...")
        geo = []

    posted = load_posted()
    batch = select_and_extract_batch(geo, posted) if geo else []
    if not batch:
        log.info("No extractable articles found. Proceeding to video engines...")

    log.info(f"Batch: {len(batch)} articles selected for processing")

    processed_count = 0
    failed_count = 0
    
    # V11.0 Carousel
    carousel_caption = ""
    prefix = get_filename_prefix()
    
    # V19.1 Content Quotas
    tg_video_count = 0
    tg_image_count = 0
    image_count = 0

    # Store dynamic files for Drive
    drive_upload_queue = []
    
    global successful_post_counter

    # --------------------------------------------------
    # PHASE 1: 3-Tier News Card Generation (Target: 4 cards)
    # --------------------------------------------------
    log.info("\n" + "=" * 60)
    log.info("V19.1 Phase 1: News Card Generation (Target: %d cards)", BATCH_SIZE)
    log.info("=" * 60)

    for idx, article in enumerate(batch, 1):
        try:
            log.info(f"\n{'=' * 40}")
            log.info(f"Processing [{idx}/{len(batch)}]: {article['title'][:70]}\u2026")
            log.info(f"Source: {article['source']} | {article.get('real_url', article['link'])[:60]}\u2026")

            # Try AI generation, if it throws rate limits/errors, it will be caught below
            # V19.0: Skip re-summarization for triangulated articles (already AI-processed)
            if not article.get("_triangulated"):
                article = generate_internal_summary(article)

            # V17.7: Strict "No Image = Skip" Rule
            temp_img = download_article_image(article)
            fallback = get_locator_map(article) or get_actor_image(article) if not temp_img else None
            if not temp_img and not fallback:
                print(f"  [SKIP] No high-quality image found for '{article.get('title')[:40]}...'. Skipping post generation.")
                continue
                
            # IMAGE mode: standard card generation
            log.info("  Generating static card")
            
            png = OUTPUT_DIR / f"{successful_post_counter:02d}_Image.png"
            txt = OUTPUT_DIR / f"{successful_post_counter:02d}_Caption.txt"

            threat_level = int(article.get("threat_level", 8))
            generate_card(article, png, threat_level=threat_level)
            generate_caption(article, txt)
            
            drive_upload_queue.extend([png, txt])
            successful_post_counter += 1
            image_count += 1

            # Append local txt to combined carousel string
            if txt.exists():
                carousel_caption += txt.read_text(encoding="utf-8") + "\n\n---\n\n"

            posted = mark_posted(
                article.get("real_url", article["link"]),
                article.get("pub_date"), posted,
                title=article.get("title", "")
            )
            save_posted(posted)
            processed_count += 1
            log.info(f"  Card {processed_count}/{BATCH_SIZE} complete \u2713")

            # Stop after BATCH_SIZE valid articles
            if processed_count >= BATCH_SIZE:
                break

            # V9.1: Rate limiting smart delay
            log.info("  Rate limiting: sleeping 15s...")
            print("[INFO] Sleeping for 15 seconds to respect AI rate limits...")
            time.sleep(15)

        except Exception as e:
            log.error(f"  Failed processing article '{article.get('title', 'Unknown')}': {e}", exc_info=False)
            failed_count += 1
            continue

    # --------------------------------------------------
    # PHASE 2: Telethon Video Hunting (Target: 5 videos)
    # --------------------------------------------------
    log.info("\n" + "=" * 60)
    log.info("V19.1 Phase 2: Telegram Video Hunting (Target: %d videos)", MAX_VIDEOS)
    log.info("=" * 60)
    try:
        successful_post_counter, image_count, tg_video_count, tg_image_count = run_telegram_hunter(
            posted, successful_post_counter, image_count, tg_video_count, tg_image_count, drive_upload_queue
        )
    except Exception as e:
        log.exception("[PHASE 2] Telegram video engine failed")

    # --------------------------------------------------
    # PHASE 3: YouTube Fallback (Fill remaining video quota)
    # --------------------------------------------------
    if tg_video_count < MAX_VIDEOS:
        log.info("\n" + "=" * 60)
        log.info("V19.1 Phase 3: YouTube Fallback (Need %d more videos)", MAX_VIDEOS - tg_video_count)
        log.info("=" * 60)
        try:
            successful_post_counter, tg_video_count = run_youtube_hunter(
                posted, successful_post_counter, tg_video_count, drive_upload_queue
            )
        except Exception as e:
            log.exception("[PHASE 3] YouTube fallback engine failed")
    else:
        log.info("\n[PHASE 3] Video quota met. Skipping YouTube hunter.")

    save_posted(posted)  # Save posted duplicate tracker after all engines run

    # --------------------------------------------------
    # PHASE 4: Carousel Compilation & Drive Upload
    # --------------------------------------------------
    log.info("\n" + "=" * 60)
    log.info("V19.1 Phase 4: Drive Upload")
    log.info("=" * 60)

    if carousel_caption:
        combo_txt = Path(RUN_DIR) / f"{FN}_Carousel_Combined.txt"
        combo_txt.write_text(carousel_caption, encoding="utf-8")
        drive_upload_queue.append(combo_txt)
        log.info(f"  Carousel Combined caption saved: {combo_txt.name}")
        
    if drive_upload_queue:
        # Sort files alphabetically/numerically so 1.png and 1.txt upload together
        raw_files = [f for f in os.listdir(RUN_DIR) if os.path.isfile(os.path.join(RUN_DIR, f))]
        sorted_files = sorted(raw_files)
        files_to_upload = [Path(os.path.join(RUN_DIR, f)) for f in sorted_files]
        
        # Combine lists and dedupe (safely avoiding unordered set)
        all_ups = list(dict.fromkeys(drive_upload_queue + files_to_upload))
        
        # Strict alphanumeric sort before sequential Google Drive loop
        all_ups = sorted(all_ups, key=lambda x: x.name)
        upload_files_to_drive(all_ups)

    log.info("\n" + "=" * 60)
    log.info(f"V19.1 Run complete. {processed_count} cards + {tg_video_count} videos. {failed_count} failed.")
    log.info("=" * 60)


if __name__ == "__main__":
    main()
