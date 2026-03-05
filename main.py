#!/usr/bin/env python3
"""
Geopolitical Breaking News Automation — v7.0
==============================================
API-driven intelligence engine (2 posts per 30-min run).
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
from difflib import SequenceMatcher
from datetime import datetime, timezone
from pathlib import Path
from io import BytesIO

import feedparser
import requests
import dateparser as dp
from bs4 import BeautifulSoup
from PIL import Image, ImageDraw, ImageFont, ImageEnhance

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = BASE_DIR / "output"
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
BATCH_SIZE = 2                   # V10.12: 2 posts per 30-min run
HIGHLIGHT_COLOR = "#FBBF24"      # V7.0: keyword highlight gold
MAX_ARTICLE_AGE_HOURS = 20       # V9.6: 20h hyper-recency window



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
    "Sky News": "https://feeds.skynews.com/feeds/rss/world.xml",
    "The Guardian": "https://www.theguardian.com/world/rss",
    "France 24": "https://www.france24.com/en/rss",
    "DW World": "https://rss.dw.com/rdf/rss-en-world",
    "Independent": "https://www.independent.co.uk/news/world/rss",
    "Al Jazeera": "https://www.aljazeera.com/xml/rss/all.xml",
    "BBC World": "http://feeds.bbci.co.uk/news/world/rss.xml",
    "Defense One": "https://www.defenseone.com/feed/",
    "Associated Press": "https://rsshub.app/apnews/topics/apf-topnews",
    "Reuters": "https://www.reutersagency.com/feed/?best-topics=world-news",
    "Defense News": "https://www.defensenews.com/arc/outboundfeeds/rss/",
    "CNN World": "http://rss.cnn.com/rss/edition_world.rss",
}

GOOGLE_NEWS_QUERIES = [
    '"active combat" OR "casualties" OR "war"',
    '"military strike" OR "airstrike" OR "missile"',
    '"troop deployment" OR "defense announcement"',
    '"cyberattack" OR "infrastructure strike" OR "drone strike"',
    '"strategic shift" OR "military hardware"',
]

# ---------------------------------------------------------------------------
# Keyword Systems
# ---------------------------------------------------------------------------

SEVERITY_KEYWORDS = [
    "war", "strike", "attack", "military", "defense",
    "sanctions", "crisis", "emergency",
]

GEOPOLITICS_KEYWORDS = [
    "war", "military", "sanctions", "strike", "defense", "crisis",
    "conflict", "diplomatic", "ceasefire", "troops", "deployment",
    "invasion", "missile", "airstrike", "bombardment", "armed forces",
    "escalation", "battlefield", "retaliation", "national security",
    "alliance", "nuclear", "interstate",
]

EXCLUDE_MARKERS = [
    "opinion", "editorial", "analysis", "blog", "commentary",
    "column", "perspective", "op-ed", "review", "podcast",
    "interview", "letter", "explainer", "quiz", "gallery",
    "feature", "retrospective", "history of",
]

# V3.7 Rejection Firewall — block non-geopolitics noise
REJECTION_KEYWORDS = [
    "sports", "football", "soccer", "la liga", "premier league",
    "madrid", "barca", "barcelona", "hollywood", "celebrity",
    "entertainment", "gossip", "nba", "nfl", "mlb", "cricket",
    "tennis", "golf", "olympics", "champions league", "serie a",
    "bundesliga", "ligue 1", "transfer", "playoffs", "super bowl",
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
        url = f"https://news.google.com/rss/search?q={requests.utils.quote(query)}&hl=en-US&gl=US&ceid=US:en&when=4h"
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
    """V10.12: Hybrid Scraper (Requests + Trafilatura Bypass + BS4 Fallback)."""
    try:
        session = requests.Session()
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml"
        }
        response = session.get(url, headers=headers, timeout=15, allow_redirects=True)
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
    """V4.0: Reject articles older than MAX_ARTICLE_AGE_HOURS."""
    pub = article.get("pub_date")
    if not pub:
        return False  # Give benefit of doubt if no date
    now = datetime.now(timezone.utc)
    if not pub.tzinfo:
        pub = pub.replace(tzinfo=timezone.utc)
    age_hours = (now - pub).total_seconds() / 3600
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

    # 1. Fill Kinetic Quota (Target: 2)
    kinetic_count = 0
    for a in kinetic_queue:
        if kinetic_count >= 2:
            break
        if _try_extract(a):
            final_batch.append(a)
            kinetic_count += 1
            log.info(f"  \u2713 Kinetic Slot Filled ({kinetic_count}/2)")

    # 2. Fill General Quota (Target: 1)
    # Start from bottom of general_queue (least severe first)
    general_count = 0
    for a in reversed(general_queue):
        if general_count >= 1:
            break
        if _try_extract(a):
            final_batch.append(a)
            general_count += 1
            log.info(f"  \u2713 General Slot Filled ({general_count}/1)")

    # 3. Fallback Filler (If either queue was exhausted before hitting target)
    if len(final_batch) < 3:
        log.info(f"  Quota not met ({len(final_batch)}/3). Pulling from remaining valid articles...")
        for a in valid_articles:
            if len(final_batch) >= 3:
                break
            if a not in final_batch:
                if _try_extract(a):
                    final_batch.append(a)
                    log.info(f"  \u2713 Fallback Slot Filled ({len(final_batch)}/3)")

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
- "image_summary": A comprehensive 3-4 sentence tactical summary (400-500 chars). Provide high detail on military hardware used, exact strike locations, casualty reports, and the kinetic facts. Ensure all sentences are grammatically complete. Do not end on floating or cut-off quotes. DO NOT include the phrase "THE BIG PICTURE:" anywhere — the system handles that prefix.
- "detailed_caption": A deeply analytical, multi-paragraph intelligence briefing (4-5 paragraphs, 1000-1200 chars). This MUST be entirely distinct from image_summary. DO NOT copy-paste or repeat any sentences. Deeply explore the strategic context, regional geopolitical impact, potential diplomatic fallout, and relevant historical precedent. Explain the broader ramifications for global power dynamics. Ensure all sentences are grammatically complete.
- "flags": A list of up to two 2-letter ISO country codes (lowercase) of the PRIMARY nations physically involved in this specific event. DO NOT blindly default to "us" and "ir". If the strike happens in Bahrain, you MUST include "bh". If it involves Ukraine, include "ua". Be highly specific to the article text.
- "keywords": Generate a massive, comma-separated list of EXACTLY 50 to 60 highly relevant, trending SEO keywords, tags, and search terms related to the article (e.g., missile, war, pentagon, drone strike, geopolitics, etc.). Do not use hashtags (#), just comma-separated words.

Return ONLY the JSON object, no markdown, no explanation."""


def _parse_ai_result(result: dict) -> dict | None:
    """V8.6: Normalize AI response keys and validate."""
    countries = result.get("flags", result.get("countries", []))
    # V8.6: Support both new split fields and legacy single summary
    image_summary = result.get("image_summary", "")
    detailed_caption = result.get("detailed_caption", "")
    legacy_summary = result.get("summary", "")
    # Use image_summary if available, else fall back to legacy summary
    summary = image_summary or legacy_summary
    keywords = result.get("keywords", [])
    if not summary:
        return None
    out = {"summary": summary, "countries": countries, "keywords": keywords}
    if detailed_caption:
        out["detailed_caption"] = detailed_caption
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
    V9.5: 3-Tier API Waterfall (Zero Downtime).
    Tries OpenRouter (Llama 3) -> Groq (Llama 3) -> Gemini 2.5 Flash in order.
    No time.sleep() needed, it just falls back instantly on hit rate limits.
    """
    input_text = article_text[:4000] if len(article_text) > 4000 else article_text
    prompt = _AI_PROMPT_TEMPLATE.format(headline=article_title, text=input_text)

    # === ATTEMPT 1: OPENROUTER (Meta Llama 3) ===
    or_key = os.environ.get("OPENROUTER_API_KEY")
    if or_key:
        try:
            from openai import OpenAI
            client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=or_key)
            
            response = client.chat.completions.create(
                model="qwen/qwen-2.5-7b-instruct:free",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=600,
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
            print("[WARNING] Tier 1 (qwen/qwen-2.5-7b-instruct:free) failed: Missing openai package")
        except Exception as e:
            if "429" in str(e) or "rate limit" in str(e).lower() or "resource exhausted" in str(e).lower():
                print("[INFO] Rate limit hit on Tier 1. Cooling down for 5 seconds...")
                time.sleep(5)
            log.warning(f"  [FALLBACK] OpenRouter failed: {e}. Falling back to Groq...")
            print(f"[WARNING] Tier 1 (qwen/qwen-2.5-7b-instruct:free) failed: {e}")

    # === ATTEMPT 2: GROQ (Meta Llama 3) ===
    groq_key = os.environ.get("GROQ_API_KEY")
    if groq_key:
        try:
            from groq import Groq
            client = Groq(api_key=groq_key)

            response = client.chat.completions.create(
                model="llama-3.1-8b-instant",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=600,
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
            print("[WARNING] Tier 2 (Llama-3.1-8b-instant) failed: Missing groq package")
        except Exception as e:
            if "429" in str(e) or "rate limit" in str(e).lower() or "resource exhausted" in str(e).lower():
                print("[INFO] Rate limit hit on Tier 2. Cooling down for 5 seconds...")
                time.sleep(5)
            log.warning(f"  [FALLBACK] Groq failed: {e}. Falling back to Gemini...")
            print(f"[WARNING] Tier 2 (Llama-3.1-8b-instant) failed: {e}")

    # === ATTEMPT 3: GEMINI (2.5 Flash) ===
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
            print("[WARNING] Tier 3 (Gemini-2.5-Flash) failed: Missing google-genai package")
        except Exception as e:
            if "429" in str(e) or "rate limit" in str(e).lower() or "resource exhausted" in str(e).lower():
                print("[INFO] Rate limit hit on Tier 3. Cooling down for 5 seconds...")
                time.sleep(5)
            log.warning(f"  [FATAL] Gemini fallback failed: {e}")
            print(f"[WARNING] Tier 3 (Gemini-2.5-Flash) failed: {e}")

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
    V9.5: Triggers the new API waterfall.
    """
    full_text = (article.get("full_text") or "") or (article.get("summary") or "")
    headline = article.get("title", "")

    if not full_text:
        article["paragraphs"] = [headline]
        article["card_summary"] = headline
        article["countries"] = []
        article["keywords"] = []
        return article

    # Run the 3-Tier API Waterfall
    result = generate_intelligence_cascade(headline, full_text)

    card_summary = smart_typography(result["summary"])
    article["card_summary"] = card_summary
    article["countries"] = result.get("countries", [])
    article["keywords"] = result.get("keywords", [])

    # Build paragraphs for caption
    parts = card_summary.split("\n\n")
    article["paragraphs"] = parts
    
    if "detailed_caption" in result:
        article["paragraphs"].append(smart_typography(result["detailed_caption"]))
    else:
        # Find official statement for caption (from original text)
        all_sentences = re.split(r'(?<=[.!?])\s+', full_text.strip())
        statement_kw = ["said", "stated", "announced", "confirmed", "declared", "spokesperson"]
        for s in all_sentences[3:]:
            if any(kw in s.lower() for kw in statement_kw):
                article["paragraphs"].append(smart_typography(s))
                break

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
    try:
        log.info(f"  Downloading image: {url[:60]}\u2026")
        resp = requests.get(url, headers=HTTP_HEADERS, timeout=10)
        if resp.status_code == 200:
            img = Image.open(BytesIO(resp.content)).convert("RGBA")
            # Color grading: contrast +5%, saturation +10%
            img = ImageEnhance.Contrast(img).enhance(1.05)
            img = ImageEnhance.Color(img).enhance(1.10)
            log.info("  Graded: contrast +5%, saturation +10%")
            return img
    except Exception as e:
        print(f"[ERROR] Image download failed: {e}. Falling back to default.")
        try:
            return Image.open("assets/default_bg.jpg").convert("RGBA")
        except Exception:
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
# 13. NEWS CARD GENERATION (V3.4 LAYOUT)
# ===========================================================================

def generate_card(article: dict, output_path: Path) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    canvas = Image.new("RGB", (CARD_WIDTH, CARD_HEIGHT), _hex(TEXT_PANEL_BG))
    draw = ImageDraw.Draw(canvas)

    # ── HEADER: 8% red strip ──
    strip_h = int(CARD_HEIGHT * HEADER_HEIGHT_PCT)  # ~86px
    draw.rectangle([(0, 0), (CARD_WIDTH, strip_h)], fill=_hex(RED_STRIP))
    hf = _load_font("header", 42)
    ht = "\u26a1 BREAKING NEWS"
    hbox = draw.textbbox((0, 0), ht, font=hf)
    draw.text(
        ((CARD_WIDTH - (hbox[2] - hbox[0])) // 2, (strip_h - (hbox[3] - hbox[1])) // 2),
        ht, fill=_hex(HEADER_TEXT_COLOR), font=hf,
    )

    # ── LAYOUT ──
    body_top = strip_h
    body_h = CARD_HEIGHT - strip_h
    left_w = int(CARD_WIDTH * LEFT_PANEL_PCT)    # 486px (45%)
    right_w = CARD_WIDTH - left_w                # 594px (55%)
    rx = left_w

    # ── LEFT 45%: Image ──
    art_img = download_article_image(article)
    bw = 4
    ia_w = left_w - bw * 2
    ia_h = body_h - 40 - bw * 2

    if art_img:
        art_img = smart_crop(art_img, ia_w, ia_h)
        draw.rectangle([(0, body_top), (left_w, body_top + ia_h + bw * 2)], fill=(255, 255, 255))
        canvas.paste(art_img.convert("RGB"), (bw, body_top + bw))
        cf = _load_font("footer", 14)
        draw.text((bw + 4, body_top + ia_h + bw * 2 + 6),
                  f"Photo: {article.get('source', 'Unknown')}", fill=_hex(FOOTER_COLOR), font=cf)
        log.info("  Card: image (smart crop + graded)")
    else:
        fallback = get_locator_map(article) or get_actor_image(article)
        if fallback:
            fallback = _center_crop(fallback, ia_w, ia_h)
            draw.rectangle([(0, body_top), (left_w, body_top + ia_h + bw * 2)], fill=(255, 255, 255))
            canvas.paste(fallback.convert("RGB"), (bw, body_top + bw))
            cf = _load_font("footer", 14)
            draw.text((bw + 4, body_top + ia_h + bw * 2 + 6),
                      "LOCATOR MAP", fill=_hex(FOOTER_COLOR), font=cf)
            log.info("  Card: fallback image")
        else:
            draw.rectangle([(0, body_top), (left_w, CARD_HEIGHT)], fill=_hex("#0F172A"))
            for y in range(body_top, CARD_HEIGHT, 20):
                draw.line([(0, y), (left_w, y)], fill=(25, 30, 42), width=1)

    # ── RIGHT 55%: Text panel ──
    draw.rectangle([(rx, body_top), (CARD_WIDTH, CARD_HEIGHT)], fill=_hex(TEXT_PANEL_BG))

    # ── FLAGS: 25px below header, 15% smaller ──
    countries = detect_countries(article)
    flag_top = body_top + FLAG_TOP_GAP
    flag_area_h = int(150 * FLAG_SCALE_DOWN)  # ~127px

    if len(countries) >= 2:
        half = right_w // 2
        for i, code in enumerate(countries[:2]):
            fi = download_flag(code)
            if fi:
                max_f = int(min(half - 20, 140) * FLAG_SCALE_DOWN)
                fi.thumbnail((max_f, int(max_f * 0.66)), Image.LANCZOS)
                fx = rx + i * half + (half - fi.width) // 2
                fy = flag_top + (flag_area_h - fi.height) // 2
                canvas.paste(fi, (fx, fy), fi)
        sep_x = rx + half
        draw.line([(sep_x, flag_top + 10), (sep_x, flag_top + flag_area_h - 10)],
                  fill=(255, 255, 255), width=2)
        log.info(f"  Flags: {countries[0]}, {countries[1]}")
    elif len(countries) == 1:
        fi = download_flag(countries[0])
        if fi:
            max_f = int(min(right_w - 40, 180) * FLAG_SCALE_DOWN)
            fi.thumbnail((max_f, int(max_f * 0.66)), Image.LANCZOS)
            fx = rx + (right_w - fi.width) // 2
            fy = flag_top + (flag_area_h - fi.height) // 2
            canvas.paste(fi, (fx, fy), fi)
    else:
        # V8.3: No flags — show category icon based on headline keywords
        headline_lower = article.get("title", "").lower()
        icon_name = "globe"  # default
        for category, keywords_list in ICON_CATEGORIES.items():
            if any(kw in headline_lower for kw in keywords_list):
                icon_name = category
                break
        icon_path = ICON_DIR / f"{icon_name}.png"
        
        # Auto-download real logo if missing
        if not icon_path.exists():
            download_category_icon(icon_name, icon_path)

        if icon_path.exists():
            try:
                icon = Image.open(icon_path).convert("RGBA")
                icon_size = int(flag_area_h * 0.8)
                icon.thumbnail((icon_size, icon_size), Image.LANCZOS)
                ix = rx + (right_w - icon.width) // 2
                iy = flag_top + (flag_area_h - icon.height) // 2
                canvas.paste(icon, (ix, iy), icon)
                log.info(f"  Category icon: {icon_name}")
            except Exception as exc:
                log.warning(f"  Failed to load icon {icon_name}: {exc}")

    # ── HEADLINE: 25px below flags ──
    text_x = rx + RIGHT_MARGIN
    text_w = right_w - RIGHT_MARGIN * 2
    hl_top = flag_top + flag_area_h + HEADLINE_TOP_GAP

    hl_font, hl_lines = _auto_scale(
        draw, smart_typography(article["title"]), "headline", text_w,
        max_lines=4, start=51, minimum=37,
    )
    hl_line_h = hl_font.size + 6
    for i, line in enumerate(hl_lines):
        draw.text((text_x, hl_top + i * hl_line_h),
                  line, fill=_hex(HEADLINE_COLOR), font=hl_font)

    # ── SUMMARY: 20px below headline, keyword highlighting ──
    raw_summary = article.get("card_summary", article.get("summary", ""))
    # V8.6: Strip any AI-injected "THE BIG PICTURE:" then hardcode it as prefix
    raw_summary = raw_summary.replace("THE BIG PICTURE: ", "").replace("THE BIG PICTURE:", "")
    summary = f"THE BIG PICTURE: {raw_summary}" if raw_summary else ""
    keywords_set = {kw.lower().strip() for kw in article.get("keywords", [])}
    if summary:
        sum_top = hl_top + len(hl_lines) * hl_line_h + SUMMARY_TOP_GAP
        sum_fs = 22
        sum_font = _load_font("summary", sum_fs)
        bold_font = _load_font("headline", sum_fs)  # Bold variant for keywords
        s_line_h = int(sum_fs * LINE_SPACING_MULT)

        # Footer boundary
        div_y = CARD_HEIGHT - RIGHT_MARGIN - 28
        max_bottom = div_y - 16
        avail_h = max_bottom - sum_top
        max_lines = max(1, avail_h // s_line_h)

        # Split on Axios sections
        parts = summary.split("\n\n")
        all_lines = []
        for part in parts:
            part = part.strip()
            if not part:
                continue
            is_bp = part.startswith("THE BIG PICTURE:")
            rem = max_lines - len(all_lines)
            if rem <= 0:
                break
            if is_bp and all_lines:
                all_lines.append(("", False))
                rem -= 1
                if rem <= 0:
                    break
            for pl in _pixel_wrap(draw, part, sum_font, text_w, rem):
                all_lines.append((pl, is_bp))

        # Truncate with ellipsis
        if len(all_lines) > max_lines:
            all_lines = all_lines[:max_lines]
            lt, bp = all_lines[-1]
            if lt and not lt.endswith("\u2026"):
                w = lt.split()
                if len(w) > 1:
                    all_lines[-1] = (" ".join(w[:-1]) + "\u2026", bp)

        # V7.0: Word-by-word rendering with keyword highlighting
        for i, (lt, is_bp) in enumerate(all_lines):
            yp = sum_top + i * s_line_h
            if yp + s_line_h > max_bottom:
                break
            if not lt:
                continue

            # Determine base color for this line
            base_color = _hex(BIG_PICTURE_COLOR) if is_bp and lt.startswith("THE BIG") else _hex(SUMMARY_COLOR)

            if keywords_set:
                # Word-by-word rendering with keyword highlighting
                cursor_x = text_x
                words = lt.split(" ")
                space_w = draw.textlength(" ", font=sum_font)
                for wi, word in enumerate(words):
                    clean_word = re.sub(r'[^a-zA-Z]', '', word).lower()
                    if clean_word in keywords_set:
                        draw.text((cursor_x, yp), word, fill=_hex(HIGHLIGHT_COLOR), font=bold_font)
                        cursor_x += draw.textlength(word, font=bold_font)
                    else:
                        draw.text((cursor_x, yp), word, fill=base_color, font=sum_font)
                        cursor_x += draw.textlength(word, font=sum_font)
                    if wi < len(words) - 1:
                        cursor_x += space_w
            else:
                # No keywords — render line normally
                draw.text((text_x, yp), lt, fill=base_color, font=sum_font)

    # ── FOOTER ──
    ff = _load_font("footer", 15)
    source = article.get("source", "Unknown")
    dateline = format_dateline(article.get("pub_date"))
    div_y = CARD_HEIGHT - RIGHT_MARGIN - 28
    draw.line([(rx + RIGHT_MARGIN, div_y), (CARD_WIDTH - RIGHT_MARGIN, div_y)],
              fill=_hex(FOOTER_COLOR), width=1)
    fy = div_y + 5
    draw.text((rx + RIGHT_MARGIN, fy), f"SOURCE: {source.upper()}", fill=_hex(FOOTER_COLOR), font=ff)
    draw.text((rx + RIGHT_MARGIN, fy + 18), f"DATELINE: {dateline}", fill=_hex(FOOTER_COLOR), font=ff)

    # V8.1: Market data on right panel beneath dateline, gold color
    market_str = get_market_data()
    if market_str:
        mf = _load_font("footer", 12)
        draw.text((rx + RIGHT_MARGIN, fy + 36), market_str, fill=_hex(HIGHLIGHT_COLOR), font=mf)

    # V8.8: Engraved Channel Branding Watermark — larger, gold-tinted
    brand_str = "@geopoliticsofical"
    brand_font = _load_font("footer", 18)
    brand_w = draw.textlength(brand_str, font=brand_font)
    brand_x = rx + right_w - int(brand_w) - RIGHT_MARGIN
    brand_y = div_y - 24
    draw.text((brand_x, brand_y), brand_str,
              fill=(251, 191, 36, 140), font=brand_font)

    canvas.save(str(output_path), "PNG", quality=95)
    log.info(f"  Card saved: {output_path}")


# ===========================================================================
# 14. CAPTION GENERATION
# ===========================================================================

def generate_caption(article: dict, output_path: Path) -> None:
    """V8.6: Multi-paragraph exhaustive caption with distinct text from card."""
    headline = smart_typography(article.get("title", ""))
    paragraphs = article.get("paragraphs", [])
    summary = article.get("card_summary", article.get("summary", ""))
    detailed = article.get("detailed_caption", "")
    source = article.get("source", "Unknown")
    link = article.get("real_url", article.get("link", ""))
    dateline = format_dateline(article.get("pub_date"))
    keywords = article.get("keywords", [])
    countries = article.get("countries", [])

    lines = []
    # Title block
    lines.append(f"\u26a0\ufe0f {headline}")
    lines.append("")

    # AI-generated tactical summary (short hook from card)
    if summary:
        lines.append("\U0001f4cc INTELLIGENCE BRIEF:")
        lines.append(f"THE BIG PICTURE: {summary.replace('THE BIG PICTURE: ', '').replace('THE BIG PICTURE:', '')}")
        lines.append("")

    # V8.6: Detailed caption — entirely distinct from image_summary
    if detailed:
        lines.append("\U0001f4cb DETAILED ANALYSIS:")
        for part in detailed.split("\n\n"):
            part = part.strip()
            if part:
                lines.append(part)
                lines.append("")
    elif paragraphs:
        lines.append("\U0001f4cb DETAILED ANALYSIS:")
        for para in paragraphs:
            lines.append(para)
            lines.append("")

    # Metadata
    lines.append("\u2500" * 30)
    lines.append(f"\U0001f4f0 Source: {source}")
    lines.append(f"\U0001f517 {link}")
    lines.append(f"\U0001f4c5 {dateline}")
    if countries:
        flag_str = " ".join(f":{c}:" for c in countries)
        lines.append(f"\U0001f30d Nations: {flag_str}")
    if keywords:
        lines.append(f"\U0001f3af Keywords: {', '.join(keywords)}")
    lines.append("")
    lines.append("#Geopolitics #BreakingNews #WarUpdate #MilitaryIntel #GlobalAffairs")
    lines.append("")
    lines.append("Follow @geopoliticsofical for real-time intelligence updates.")

    output_path.write_text("\n".join(lines), encoding="utf-8")
    log.info(f"  Caption saved: {output_path}")


# ===========================================================================
# 15. FILENAME
# ===========================================================================

def get_filename_prefix() -> str:
    """V8.8: ISO-format file naming: YYYY-MM-DD_HHMM"""
    now = datetime.now(timezone.utc)
    return now.strftime("%Y-%m-%d_%H%M")


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

def upload_files_to_drive(png_path: Path, txt_path: Path):
    svc = get_drive_service()
    if not svc:
        return
    try:
        ROOT_ID = "1AVFFrHH89quUE8wMO_C5XHu7T62RuBNZ"
        geo = find_or_create_folder(svc, "Geopolitics", ROOT_ID)
        out = find_or_create_folder(svc, "Outputs", geo)
        upload_to_drive(svc, png_path, out)
        upload_to_drive(svc, txt_path, out)
    except Exception as exc:
        log.error(f"Drive upload failed: {exc}")


# ===========================================================================
# 17. MAIN ORCHESTRATOR (V8.9 — Image-Only Engine)
# ===========================================================================

def main() -> None:
    log.info("=" * 60)
    log.info("Geopolitical Breaking News v8.0 — Batch run starting")
    log.info("=" * 60)

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
    for idx, article in enumerate(batch, 1):
        try:
            log.info(f"\n{'=' * 40}")
            log.info(f"Processing [{idx}/{len(batch)}]: {article['title'][:70]}\u2026")
            log.info(f"Source: {article['source']} | {article.get('real_url', article['link'])[:60]}\u2026")

            # Try AI generation, if it throws rate limits/errors, it will be caught below
            article = generate_internal_summary(article)

            prefix = get_filename_prefix()

            # IMAGE mode: standard card generation
            log.info("  Generating static card")
            png = OUTPUT_DIR / f"{prefix}_Card{idx}.png"
            txt = OUTPUT_DIR / f"{prefix}_Card{idx}.txt"
            
            generate_card(article, png)
            generate_caption(article, txt)
            
            upload_files_to_drive(png, txt)

            posted = mark_posted(
                article.get("real_url", article["link"]),
                article.get("pub_date"), posted,
                title=article.get("title", "")
            )
            save_posted(posted)
            processed_count += 1
            log.info(f"  Card {processed_count} complete \u2713")

            # V8.9: Stop after BATCH_SIZE valid articles
            if processed_count >= BATCH_SIZE:
                break

            # V9.1: Rate limiting smart delay
            log.info("  Rate limiting: sleeping 15s...")
            print("[INFO] Sleeping for 15 seconds to respect AI rate limits...")
            time.sleep(15)
        except Exception as e:
            print(f"[ERROR] Pipeline failed for article '{article.get('title', 'Unknown')}': {e}")
            failed_count += 1
            continue

    log.info("\n" + "=" * 60)
    log.info(f"Run complete. {processed_count} cards generated successfully. {failed_count} failed.")
    log.info("=" * 60)


if __name__ == "__main__":
    main()
