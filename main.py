#!/usr/bin/env python3
"""
Geopolitical Breaking News Automation — v15.8
==============================================
Axis of Resistance Mega-Expansion + Strict Freshness.
9 Pro-Iran/Resistance RSS feeds. 24h strict freshness enforcement.
Groq Llama 3 for summarization, entity extraction, keyword
highlighting. Hybrid video/image pipeline.
"""

import os
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
from difflib import SequenceMatcher
from datetime import datetime, timezone
from pathlib import Path
from io import BytesIO

import yt_dlp
import feedparser
import requests
import cloudscraper
import dateparser as dp
from bs4 import BeautifulSoup
from PIL import Image, ImageDraw, ImageFont, ImageEnhance, ImageFilter, ImageOps
import pillow_avif

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = BASE_DIR / "output"
VIDEO_DIR = BASE_DIR / "videos"
FONTS_DIR = BASE_DIR / "fonts"
FLAGS_DIR = BASE_DIR / "assets" / "flags"
COUNTRY_MAPS_DIR = BASE_DIR / "assets" / "country_maps"
ACTORS_DIR = BASE_DIR / "assets" / "actors"
POSTED_LINKS_FILE = BASE_DIR / "posted_links.json"
AI_USAGE_FILE = BASE_DIR / "ai_usage.json"
DARK_MAP_FILE = BASE_DIR / "assets" / "dark_world_map.png"

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
BATCH_SIZE = 3                   # V11.0: 3 posts per run
HIGHLIGHT_COLOR = "#FBBF24"      # V7.0: keyword highlight gold
MAX_ARTICLE_AGE_HOURS = 24       # V15.6: 24h strict freshness window



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
}

GOOGLE_NEWS_QUERIES = [
    '"IRGC" OR "Islamic Revolutionary Guard Corps"',
    '"Iran missile" OR "Iran drone" OR "air defense"',
    '"US base attack" OR "Israel strike"',
    '"Hezbollah" OR "Lebanon strike"',
    '"Houthi" OR "Red Sea ship"',
    '"Axis of Resistance" OR "proxy forces"',
]

# ---------------------------------------------------------------------------
# Keyword Systems
# ---------------------------------------------------------------------------

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
# Country Detection Map
# ---------------------------------------------------------------------------

COUNTRY_MAP = {
    "united states": "us", "u.s.": "us", "america": "us", "washington": "us",
    "pentagon": "us", "white house": "us",
    "russia": "ru", "moscow": "ru", "kremlin": "ru",
    "ukraine": "ua", "kyiv": "ua", "kiev": "ua",
    "china": "cn", "beijing": "cn",
    "iran": "ir", "tehran": "ir",
    "israel": "il", "tel aviv": "il", "jerusalem": "il", "idf": "il",
    "palestine": "ps", "gaza": "ps", "hamas": "ps",
    "north korea": "kp", "pyongyang": "kp",
    "south korea": "kr", "seoul": "kr",
    "taiwan": "tw", "taipei": "tw",
    "turkey": "tr", "ankara": "tr",
    "india": "in", "new delhi": "in",
    "pakistan": "pk", "islamabad": "pk",
    "syria": "sy", "damascus": "sy",
    "iraq": "iq", "baghdad": "iq",
    "saudi": "sa", "riyadh": "sa",
    "japan": "jp", "tokyo": "jp",
    "uk": "gb", "britain": "gb", "london": "gb",
    "france": "fr", "paris": "fr",
    "germany": "de", "berlin": "de",
    "nato": "nato",
    "european union": "eu", "eu ": "eu",
    "yemen": "ye", "houthi": "ye",
    "lebanon": "lb", "hezbollah": "lb",
    "egypt": "eg", "cairo": "eg",
    "poland": "pl", "warsaw": "pl",
    "afghanistan": "af", "kabul": "af", "taliban": "af",
    "ethiopia": "et", "sudan": "sd", "myanmar": "mm",
    "somalia": "so", "libya": "ly",
}

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
# 2. ARTICLE FETCHING
# ===========================================================================

def fetch_articles() -> list[dict]:
    articles = []
    for query in GOOGLE_NEWS_QUERIES:
        # V15.8: Append when:24h to strictly filter server-side
        url = f"https://news.google.com/rss/search?q={requests.utils.quote(query + ' when:24h')}&hl=en-US&gl=US&ceid=US:en"
        log.info(f"Fetching Google News: {query[:50]}\u2026")
        try:
            feed = feedparser.parse(url)
            for entry in feed.get("entries", []):
                title = entry.get("title", "").strip()
                link = entry.get("link", "").strip()
                if not title or not link:
                    continue
                source_name = ""
                if " - " in title:
                    parts = title.rsplit(" - ", 1)
                    title = parts[0].strip()
                    source_name = parts[1].strip()
                pub_date = None
                for df in ["published", "updated", "created"]:
                    if entry.get(df):
                        pub_date = parse_date_bulletproof(entry[df])
                        if pub_date:
                            break
                articles.append({
                    "title": title, "link": link, "summary": "",
                    "source": source_name or "Google News",
                    "pub_date": pub_date, "image_url": None, "full_text": None,
                })
        except Exception as exc:
            log.warning(f"Google News failed: {exc}")

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

    log.info(f"Total articles fetched: {len(articles)}")
    return articles


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
    with open(POSTED_LINKS_FILE, "w") as f:
        json.dump(data, f, indent=2)

def url_hash(url: str) -> str:
    return hashlib.sha256(url.encode("utf-8")).hexdigest()

def is_posted(link: str, posted: dict) -> bool:
    return url_hash(link) in posted

def _is_headline_duplicate(headline: str, posted: dict) -> bool:
    """V8.9: Semantic dedup — reject if headline is >60% similar to any posted."""
    headline_lower = headline.lower().strip()
    for entry in posted.values():
        old_title = entry.get("title", "").lower().strip()
        if old_title and SequenceMatcher(None, headline_lower, old_title).ratio() > 0.60:
            log.info(f"  Semantic dedup: '{headline[:50]}' ~= '{old_title[:50]}'")
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
        print(f"  [ERROR] Extraction failed: {e}")
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
    # V15.6: Fix broken Iranian server timestamps
    if age_hours > 100 or age_hours < 0:
        log.info(f"  [FIX] Bypassing date parser error (age={age_hours:.1f}h). Assuming live RSS feed article is fresh.")
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
        if extracted is None:
            log.info("  Extraction failed. Continuing to next URL...\u2026")
            return False

        article["full_text"] = extracted["text"]
        log.info(f"  Extracted: {len(extracted['text'])} chars \u2713")

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

    return final_batch


# ===========================================================================
# 7A. MARKET DATA (yfinance)
# ===========================================================================

def get_market_data() -> str:
    """V8.0: Fetch Brent Crude & Gold prices via yfinance."""
    try:
        import yfinance as yf
        parts = []
        for ticker, name in [("BZ=F", "Brent Crude"), ("GC=F", "Gold")]:
            t = yf.Ticker(ticker)
            hist = t.history(period="2d")
            if len(hist) >= 2:
                price = hist["Close"].iloc[-1]
                prev = hist["Close"].iloc[-2]
                pct = ((price - prev) / prev) * 100
                sign = "+" if pct >= 0 else ""
                parts.append(f"{name}: ${price:.2f} ({sign}{pct:.1f}%)")
            elif len(hist) == 1:
                price = hist["Close"].iloc[-1]
                parts.append(f"{name}: ${price:.0f}")
        if parts:
            return " | ".join(parts)
        return ""
    except ImportError:
        log.warning("  yfinance not installed, skipping market data")
        return ""
    except Exception as exc:
        log.warning(f"  Market data error: {exc}")
        return ""


# ===========================================================================
# 7B. UNIFIED AI BRAIN — GROQ → GEMINI FAILOVER
# ===========================================================================

_AI_PROMPT_TEMPLATE = """Act as a high-level military intelligence officer. Read this raw text, ignoring ads/menus.

Headline: {headline}

Article text:
{text}

Return strict JSON with exactly 5 keys:
- "instagram_caption": Write exactly one engaging, easy-to-understand paragraph summarizing the news. Explain it in simple English. Do not use standard robotic news words. Make it sound human.
- "flags": A list of up to two 2-letter ISO country codes (lowercase) of the PRIMARY nations physically involved in this specific event. DO NOT blindly default to "us" and "ir". If the strike happens in Bahrain, you MUST include "bh". If it involves Ukraine, include "ua". Be highly specific to the article text.
- "threat_level": Rate the geopolitical severity of this event as an integer from 1 to 10. (1-4 = low/diplomatic, 5-7 = medium/tensions, 8-10 = high/war/missile strike/casualties). Return ONLY the integer.
- "video_overlays": An array of 5 to 7 short, punchy Hinglish sentences (MAXIMUM 40 characters per sentence) that tell the story of this event. These will be flashed sequentially on a video like an Al Jazeera news reel. Make them aggressive and informative.
- "image_hook": Write exactly 1 or 2 lines summarizing the event. MAXIMUM 15 words. Use EXTREMELY simple, basic English (5th-grade level). Do not use complex words like 'escalation' or 'retaliation'. Just say who attacked who, or what happened. This will go on the image.

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


# Category icon mapping for flag-less articles
ICON_CATEGORIES = {
    "un": ["united nations", "un ", "unsc", "security council", "general assembly"],
    "nato": ["nato", "otan", "stoltenberg", "rutte", "north atlantic treaty"],
    "military": ["military", "army", "navy", "pentagon", "troops", "soldier",
                 "base", "defense", "weapon", "missile", "airstrike", "war",
                 "combat", "battalion", "brigade", "drone strike", "bombing"],
    "defense": ["boeing", "lockheed", "raytheon", "northrop", "bae systems",
                "defense contractor", "fighter jet", "f-35", "f-16"],
    "space": ["spacex", "nasa", "blue origin", "esa", "rocket", "satellite",
              "orbit", "astronaut", "iss"],
    "ai": ["openai", "anthropic", "chatgpt", "claude", "sam altman", "deepmind",
           "artificial intelligence"],
    "google": ["google", "alphabet", "sundar pichai", "gemini", "youtube", "android"],
    "meta": ["meta", "facebook", "zuckerberg", "instagram", "whatsapp", "threads"],
    "apple": ["apple", "tim cook", "iphone", "ios", "macbook", "vision pro"],
    "microsoft": ["microsoft", "satya nadella", "windows", "azure", "xbox"],
    "social": ["tiktok", "x ", "twitter", "elon musk", "bytedance", "social media",
               "algorithm"],
    "cyber": ["cyber", "hack", "ransomware", "malware", "data breach",
             "infrastructure strike", "digital", "tech"],
    "diplomacy": ["summit", "treaty", "diplomat", "ambassador",
                  "ceasefire", "negotiations", "talks", "accord", "peace",
                  "handshake", "alliance", "g7", "g20", "asean", "eu", "brics"],
    "finance": ["sanctions", "tariff", "trade war", "economy", "oil",
               "crude", "inflation", "market", "treasury", "bank",
               "currency", "dollar", "embargo", "imf", "world bank"],
}

ICON_DIR = Path(__file__).parent / "assets" / "icons"
ICON_DIR.mkdir(parents=True, exist_ok=True)

# V8.4: Real Logos Database for dynamic downloads
LOGO_DOMAINS = {
    "un": "un.org",
    "nato": "nato.int",
    "military": "defense.gov",
    "defense": "lockheedmartin.com",
    "space": "nasa.gov",
    "ai": "openai.com",
    "google": "google.com",
    "meta": "meta.com",
    "apple": "apple.com",
    "microsoft": "microsoft.com",
    "social": "x.com",
    "cyber": "cybercom.mil",
    "diplomacy": "state.gov",
    "finance": "imf.org",
}

def download_category_icon(category: str, dest_path: Path) -> bool:
    """V8.4: Download real corporate/org logo via Clearbit, or generic globe."""
    if category == "globe":
        url = "https://upload.wikimedia.org/wikipedia/commons/thumb/e/e6/Globe_icon_grey.svg/512px-Globe_icon_grey.svg.png"
    else:
        domain = LOGO_DOMAINS.get(category)
        if not domain:
            return False
        url = f"https://logo.clearbit.com/{domain}"
        
    try:
        import requests
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        if r.status_code == 200:
            with open(dest_path, "wb") as f:
                f.write(r.content)
            log.info(f"  Downloaded real logo for '{category}' from {url}")
            return True
        else:
            log.warning(f"  Logo download failed for '{category}': HTTP {r.status_code}")
    except Exception as exc:
        log.warning(f"  Failed to download logo for '{category}': {exc}")
    return False


def generate_intelligence_cascade(article_title: str, article_text: str) -> dict | None:
    """
    V12.1: 3-Tier API Waterfall (Zero Downtime).
    Tries Groq (Llama 3) -> Gemini 2.5 Flash -> OpenRouter in order.
    No time.sleep() needed, it just falls back instantly on hit rate limits.
    """
    input_text = article_text[:4000] if len(article_text) > 4000 else article_text
    prompt = _AI_PROMPT_TEMPLATE.format(headline=article_title, text=input_text)

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


def _fallback_summary(text: str, headline: str) -> dict:
    """V7.0: Regex-based fallback when Groq is unavailable."""
    text = _deep_scrub(text)
    sentences = re.split(r'(?<=[.!?])\s+', text.strip())
    good = [s.strip() for s in sentences if len(s.strip()) > 30]

    s1 = good[0] if good else headline
    s2 = good[1] if len(good) > 1 else ""

    if s2:
        summary = f"{s1}\n\nTHE BIG PICTURE: {s2}"
    else:
        summary = s1

    if len(summary) > SUMMARY_CHAR_LIMIT:
        summary = summary[:SUMMARY_CHAR_LIMIT - 1] + "\u2026"

    # Keyword scan for countries
    hl = headline.lower()
    codes = []
    seen = set()
    for keyword, code in ENTITY_TO_FLAG.items():
        if keyword in hl and code not in seen:
            codes.append(code)
            seen.add(code)
            if len(codes) >= 2:
                break

    return {
        "summary": summary,
        "countries": codes,
        "keywords": [],
    }


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
    url = article.get("image_url")
    if not url:
        return None
    
    scraper = cloudscraper.create_scraper()
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
        "Referer": "https://news.google.com/"
    }
    try:
        log.info(f"  Downloading image: {url[:60]}\u2026")
        response = scraper.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        
        # Failsafe: Ensure the server actually sent an image, not an HTML Cloudflare block
        content_type = response.headers.get('Content-Type', '')
        if not content_type.startswith('image/'):
            print(f"  [ERROR] Server blocked image download (returned {content_type}).")
            return None
            
        image = Image.open(BytesIO(response.content)).convert("RGB")
        return image
    except Exception as e:
        print(f"  [ERROR] Image download failed: {e}")
        return None


# ===========================================================================
# 10. OPENCV SMART CROP
# ===========================================================================

def smart_crop(img: Image.Image, target_w: int, target_h: int) -> Image.Image:
    try:
        import cv2
        import numpy as np

        cv_img = cv2.cvtColor(np.array(img.convert("RGB")), cv2.COLOR_RGB2BGR)
        h, w = cv_img.shape[:2]
        focal_x, focal_y = w // 2, h // 2

        cascade_paths = [
            cv2.data.haarcascades + "haarcascade_frontalface_default.xml",
            cv2.data.haarcascades + "haarcascade_profileface.xml",
            cv2.data.haarcascades + "haarcascade_upperbody.xml",
            "/usr/share/opencv4/haarcascades/haarcascade_frontalface_default.xml",
        ]
        
        found_focus = False
        gray = cv2.cvtColor(cv_img, cv2.COLOR_BGR2GRAY)
        
        for cp in cascade_paths:
            if os.path.exists(cp):
                objects = cv2.CascadeClassifier(cp).detectMultiScale(gray, 1.1, 4, minSize=(30, 30))
                if len(objects) > 0:
                    largest = max(objects, key=lambda f: f[2] * f[3])
                    focal_x = largest[0] + largest[2] // 2
                    focal_y = largest[1] + largest[3] // 2
                    log.info(f"  Subject detected via {os.path.basename(cp)} at ({focal_x}, {focal_y})")
                    found_focus = True
                    break

        if not found_focus:
            edges = cv2.Canny(gray, 50, 150)
            m = cv2.moments(edges)
            if m["m00"] > 0:
                focal_x = int(m["m10"] / m["m00"])
                focal_y = int(m["m01"] / m["m00"])
                log.info(f"  No subject detected. Used mass center at ({focal_x}, {focal_y})")

        scale = max(target_w / w, target_h / h)
        nw, nh = int(w * scale), int(h * scale)
        resized = img.resize((nw, nh), Image.LANCZOS)
        fx_r, fy_r = int(focal_x * scale), int(focal_y * scale)
        x1 = max(0, min(fx_r - target_w // 2, nw - target_w))
        y1 = max(0, min(fy_r - target_h // 2, nh - target_h))
        return resized.crop((x1, y1, x1 + target_w, y1 + target_h))

    except ImportError:
        pass
    except Exception:
        pass
    return _center_crop(img, target_w, target_h)


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


def _auto_scale(draw, text: str, font_name: str, max_width: int, max_lines: int,
                start: int, minimum: int) -> tuple:
    for size in range(start, minimum - 1, -2):
        font = _load_font(font_name, size)
        lines = _pixel_wrap(draw, text, font, max_width, max_lines)
        if len(lines) <= max_lines:
            # V6.0: Check if text was truncated; add ellipsis if so
            all_words = text.split()
            wrapped_words = " ".join(lines).split()
            if len(wrapped_words) < len(all_words) and lines:
                last = lines[-1]
                if not last.endswith("\u2026"):
                    lines[-1] = last.rstrip(".,;:!? ") + "\u2026"
            return font, lines
    font = _load_font(font_name, minimum)
    lines = _pixel_wrap(draw, text, font, max_width, max_lines)
    # Same truncation check at minimum size
    all_words = text.split()
    wrapped_words = " ".join(lines).split()
    if len(wrapped_words) < len(all_words) and lines:
        last = lines[-1]
        if not last.endswith("\u2026"):
            lines[-1] = last.rstrip(".,;:!? ") + "\u2026"
    return font, lines


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
    """V14.0: White-background News Bulletin with prominent flags and dynamic layouts."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # ── Threat-level border color ──
    if threat_level >= 8:
        banner_color = "#990000"  # Blood Red
    elif threat_level >= 5:
        banner_color = "#B8860B"  # Yellow/Dark Goldenrod
    else:
        banner_color = "#1E3A8A"  # Deep Blue

    BORDER_PX = 6
    pad_x = 50

    # ── White canvas base ──
    canvas = Image.new("RGB", (CARD_WIDTH, CARD_HEIGHT), (255, 255, 255))
    draw = ImageDraw.Draw(canvas)

    # ── Prepare news image (half-screen 1080x540) ──
    art_img = download_article_image(article)
    if not art_img:
        fallback = get_locator_map(article) or get_actor_image(article)
        if fallback:
            art_img = fallback
    if art_img:
        news_img = ImageOps.fit(art_img.convert("RGB"), (CARD_WIDTH, 540), Image.LANCZOS)
    else:
        news_img = Image.new("RGB", (CARD_WIDTH, 540), (30, 30, 40))

    # ── Prepare flags ──
    countries = detect_countries(article)
    flag_images = []
    for code in countries[:2]:
        fi = get_flag_image(code)
        if fi:
            fi.thumbnail((120, 80), Image.LANCZOS)
            flag_images.append(fi)

    # ── Get the punchy image_hook text ──
    hook_text = article.get("image_hook", "").strip()
    if not hook_text:
        words = article.get("title", "BREAKING NEWS").split()
        hook_text = " ".join(words[:15])
    hook_text = smart_typography(hook_text)

    # ── Auto-scale hook font ──
    hook_max_width = CARD_WIDTH - pad_x * 2
    hook_font_size = 72
    hook_font = _load_font("header", hook_font_size)
    hook_lines = _pixel_wrap(draw, hook_text, hook_font, hook_max_width, 4)
    while len(hook_lines) > 4 and hook_font_size > 40:
        hook_font_size -= 4
        hook_font = _load_font("header", hook_font_size)
        hook_lines = _pixel_wrap(draw, hook_text, hook_font, hook_max_width, 4)

    line_h = hook_font_size + 10
    text_block_h = len(hook_lines) * line_h

    # ── Random layout ──
    layout = random.choice(["image_top", "image_bottom", "image_center"])
    log.info(f"  Card layout: {layout}")

    if layout == "image_top":
        # Image at top
        canvas.paste(news_img, (0, 0))
        # Flags centered around y=600
        _draw_flags_centered(canvas, flag_images, y_center=600)
        # Hook text centered around y=750
        text_y = 750 - text_block_h // 2
        for i, line in enumerate(hook_lines):
            try:
                lw = draw.textlength(line, font=hook_font)
            except AttributeError:
                bbox = draw.textbbox((0, 0), line, font=hook_font)
                lw = bbox[2] - bbox[0]
            lx = (CARD_WIDTH - lw) / 2
            draw.text((lx, text_y + i * line_h), line, fill=(0, 0, 0), font=hook_font)

    elif layout == "image_bottom":
        # Flags centered around y=120
        _draw_flags_centered(canvas, flag_images, y_center=120)
        # Hook text centered around y=280
        text_y = 280 - text_block_h // 2
        for i, line in enumerate(hook_lines):
            try:
                lw = draw.textlength(line, font=hook_font)
            except AttributeError:
                bbox = draw.textbbox((0, 0), line, font=hook_font)
                lw = bbox[2] - bbox[0]
            lx = (CARD_WIDTH - lw) / 2
            draw.text((lx, text_y + i * line_h), line, fill=(0, 0, 0), font=hook_font)
        # Image at bottom
        canvas.paste(news_img, (0, 540))

    elif layout == "image_center":
        # Smaller image in center band
        center_img = ImageOps.fit(art_img.convert("RGB") if art_img else news_img, (CARD_WIDTH, 400), Image.LANCZOS)
        # Hook text at top y=150
        text_y = 150 - text_block_h // 2
        if text_y < 30:
            text_y = 30
        for i, line in enumerate(hook_lines):
            try:
                lw = draw.textlength(line, font=hook_font)
            except AttributeError:
                bbox = draw.textbbox((0, 0), line, font=hook_font)
                lw = bbox[2] - bbox[0]
            lx = (CARD_WIDTH - lw) / 2
            draw.text((lx, text_y + i * line_h), line, fill=(0, 0, 0), font=hook_font)
        # Image in center
        canvas.paste(center_img, (0, 340))
        # Flags at bottom y=850
        _draw_flags_centered(canvas, flag_images, y_center=850)

    # ── Threat-level border ──
    border_rgb = _hex(banner_color)
    draw = ImageDraw.Draw(canvas)
    draw.rectangle([(0, 0), (CARD_WIDTH - 1, BORDER_PX)], fill=border_rgb)
    draw.rectangle([(0, CARD_HEIGHT - BORDER_PX), (CARD_WIDTH - 1, CARD_HEIGHT - 1)], fill=border_rgb)
    draw.rectangle([(0, 0), (BORDER_PX, CARD_HEIGHT - 1)], fill=border_rgb)
    draw.rectangle([(CARD_WIDTH - BORDER_PX, 0), (CARD_WIDTH - 1, CARD_HEIGHT - 1)], fill=border_rgb)

    # ── @geopoliticsofical watermark — bottom center, dark gray ──
    brand_str = "@geopoliticsofical"
    brand_font = _load_font("footer", 18)
    try:
        brand_w = draw.textlength(brand_str, font=brand_font)
    except AttributeError:
        bbox = draw.textbbox((0, 0), brand_str, font=brand_font)
        brand_w = bbox[2] - bbox[0]
    brand_x = (CARD_WIDTH - int(brand_w)) // 2
    brand_y = CARD_HEIGHT - BORDER_PX - 28
    draw.text((brand_x, brand_y), brand_str, fill=_hex("#555555"), font=brand_font)

    canvas.save(str(output_path), "PNG", quality=95)
    log.info(f"  Card saved: {output_path}")


def _draw_flags_centered(canvas: Image.Image, flag_images: list, y_center: int) -> None:
    """Paste flag images horizontally centered at the given y_center."""
    if not flag_images:
        return
    gap = 30
    total_w = sum(f.width for f in flag_images) + gap * (len(flag_images) - 1)
    x = (CARD_WIDTH - total_w) // 2
    for fi in flag_images:
        fy = y_center - fi.height // 2
        canvas.paste(fi, (x, fy), fi)
        x += fi.width + gap


# ===========================================================================
# 14. CAPTION GENERATION
# ===========================================================================

def generate_caption(article: dict, output_path: Path) -> None:
    """V14.1: Clean, human-readable Instagram caption."""
    headline = smart_typography(article.get("title", ""))
    instagram_caption = article.get("instagram_caption", "News update.")
    source = article.get("source", "Unknown")
    link = article.get("real_url", article.get("link", ""))

    caption_content = f"\U0001f6a8 BREAKING: {headline}\n\n"
    caption_content += f"{instagram_caption}\n\n"
    caption_content += f"\U0001f4f0 Source: {source}\n"
    caption_content += f"\U0001f517 {link}\n\n"
    caption_content += "Follow @geopoliticsofical for daily intelligence. \U0001f30d\n\n"
    caption_content += "#Geopolitics #Military #IRGC #BreakingNews #MiddleEast\n"

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
    log.info("  [OSINT] Attempting to rip raw OSINT video footage...")
    
    # Needs a temp file for yt-dlp before FFmpeg processing
    temp_raw = output_filepath.with_name(f"{output_filepath.stem}_raw.mp4")
    
    ydl_opts = {
        'outtmpl': str(temp_raw),
        'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
        'quiet': True,
        'no_warnings': True,
        'match_filter': lambda info, *args, **kwargs: 'Video is too long' if info.get('duration', 0) > 180 else None
    }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([article_url])
            
        if not temp_raw.exists():
            return False

        # Build FFmpeg Vertical Mirror Blur + AJ+ Overlays
        log.info("  [OSINT] Processing video with FFmpeg vertical filters...")
        
        # 1. Set up the 9:16 Mirror Blur and Watermark
        watermark_text = "@geopoliticsofical"
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
            'ffmpeg', '-y', '-i', str(temp_raw), '-t', '90',
            '-filter_complex', filter_complex_str,
            '-map', f'[{last_node}]', '-map', '0:a?',
            '-c:v', 'libx264', '-preset', 'fast', '-c:a', 'aac', str(output_filepath)
        ]
        
        subprocess.run(command, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT, check=True)
        
        # V14.1: Build simplified OSINT Video Caption
        instagram_caption = parsed_json.get("instagram_caption", "News update.")

        video_caption_content = f"\U0001f6a8 BREAKING: {headline}\n\n"
        video_caption_content += f"{instagram_caption}\n\n"
        video_caption_content += f"\U0001f4f0 Source: {headline}\n"
        video_caption_content += f"\U0001f517 {article_url}\n\n"
        video_caption_content += "Follow @geopoliticsofical for daily intelligence. \U0001f30d\n\n"
        video_caption_content += "#Geopolitics #Military #IRGC #BreakingNews #MiddleEast\n"

        with open(caption_filepath, "w", encoding="utf-8") as vf:
            vf.write(video_caption_content)
        
        # Cleanup
        if temp_raw.exists():
            temp_raw.unlink()
            
        return True
    except Exception as e:
        print(f"  [INFO] No extractable/processable video found on this page. ({e})")
        if 'temp_raw' in locals() and temp_raw.exists():
            temp_raw.unlink()
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
        ROOT_ID = "1AVFFrHH89quUE8wMO_C5XHu7T62RuBNZ"
        geo = find_or_create_folder(svc, "Geopolitics", ROOT_ID)
        out = find_or_create_folder(svc, "Outputs", geo)
        for p in file_paths:
            if p and p.exists():
                # V15.3: Route strictly ONLY the video file to the Video Folder
                if p.suffix == ".mp4" and VIDEO_DRIVE_FOLDER_ID:
                    log.info(f"  [ROUTING] Sending video to Video Folder: {p.name}")
                    upload_to_drive(svc, p, VIDEO_DRIVE_FOLDER_ID)
                # Route ALL other files (.txt, .png, .jpg) to the standard Outputs folder
                else:
                    upload_to_drive(svc, p, out)
    except Exception as exc:
        log.error(f"Drive upload failed: {exc}")


# ===========================================================================
# 17. MAIN ORCHESTRATOR (V8.9 — Image-Only Engine)
# ===========================================================================

def main() -> None:
    log.info("=" * 60)
    log.info("Geopolitical Breaking News v11.0 — Omni-Channel Engine starting")
    log.info("=" * 60)

    # Ensure output directories exist for both static cards and video assets.
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    VIDEO_DIR.mkdir(parents=True, exist_ok=True)

    articles = fetch_articles()
    if not articles:
        log.info("No articles. Exiting.")
        return

    geo = filter_geopolitics(articles)
    if not geo:
        log.info("No geopolitics articles. Exiting.")
        return

    posted = load_posted()
    batch = select_and_extract_batch(geo, posted)
    if not batch:
        log.info("No extractable articles found. Exiting.")
        return

    log.info(f"Batch: {len(batch)} articles selected for processing")

    processed_count = 0
    failed_count = 0
    
    # V11.0 Carousel
    carousel_caption = ""
    prefix = get_filename_prefix()
    
    # V12.2 Always-On Video Engine
    run_video = True
    
    # Store dynamic files for Drive
    drive_upload_queue = []

    for idx, article in enumerate(batch, 1):
        try:
            log.info(f"\n{'=' * 40}")
            log.info(f"Processing [{idx}/{len(batch)}]: {article['title'][:70]}\u2026")
            log.info(f"Source: {article['source']} | {article.get('real_url', article['link'])[:60]}\u2026")

            # Try AI generation, if it throws rate limits/errors, it will be caught below
            article = generate_internal_summary(article)

            # IMAGE mode: standard card generation
            log.info("  Generating static card")
            png = OUTPUT_DIR / f"{prefix}_Card{idx}.png"
            txt = OUTPUT_DIR / f"{prefix}_Card{idx}.txt"
            
            threat_level = int(article.get("threat_level", 8))
            generate_card(article, png, threat_level=threat_level)
            generate_caption(article, txt)
            
            drive_upload_queue.extend([png, txt])
            
            # Append local txt to combined string
            if txt.exists():
                carousel_caption += txt.read_text(encoding="utf-8") + "\n\n---\n\n"

            # V11.0 OSINT Video
            if run_video:
                video_filepath = VIDEO_DIR / f"{prefix}_OSINT_Video.mp4"
                video_txt = VIDEO_DIR / f"{prefix}_OSINT_Video_Caption.txt"
                video_success = extract_and_process_video(
                    article['real_url'], 
                    article['title'], 
                    video_filepath, 
                    video_txt, 
                    article.get('summary', ''),
                    article
                )
                if video_success:
                    print(f"[SUCCESS] Prepared OSINT video: {video_filepath}")
                    drive_upload_queue.extend([video_filepath, video_txt])

            posted = mark_posted(
                article.get("real_url", article["link"]),
                article.get("pub_date"), posted,
                title=article.get("title", "")
            )
            save_posted(posted)
            processed_count += 1
            log.info(f"  Card {processed_count} complete \u2713")

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

    # ----------------------------------------------------
    # V11.0 CAROUSEL COMPILATION & DRIVE UPLOAD
    if carousel_caption:
        combo_txt = OUTPUT_DIR / f"{prefix}_Carousel_Combined.txt"
        combo_txt.write_text(carousel_caption, encoding="utf-8")
        drive_upload_queue.append(combo_txt)
        
    if drive_upload_queue:
        upload_files_to_drive(drive_upload_queue)

    log.info("\n" + "=" * 60)
    log.info(f"Run complete. {processed_count} cards generated successfully. {failed_count} failed.")
    log.info("=" * 60)


if __name__ == "__main__":
    main()
