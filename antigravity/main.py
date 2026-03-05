#!/usr/bin/env python3
"""
Aerospace & Advanced Physics Breaking News Automation
=====================================================
Deterministic single-post-per-run system.
Scrapes RSS feeds, filters for aerospace/physics breakthroughs,
generates a professional 60/40 split Instagram card, and uploads to Drive.
"""

import os
import sys
import json
import html
import re
import hashlib
import textwrap
import logging
from datetime import datetime, timezone
from pathlib import Path
from io import BytesIO

import feedparser
import requests
from dateutil import parser as dateparser
from bs4 import BeautifulSoup
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = BASE_DIR / "output"
FONTS_DIR = BASE_DIR / "fonts"
LOGOS_DIR = BASE_DIR / "assets" / "logos"
POSTED_LINKS_FILE = BASE_DIR / "posted_links.json"
AI_USAGE_FILE = BASE_DIR / "ai_usage.json"

CARD_WIDTH = 1080
CARD_HEIGHT = 1080
SAFE_MARGIN = 60

# --- RSS Feeds ---
RSS_FEEDS = {
    "NASA Spaceflight": "https://www.nasaspaceflight.com/feed/",
    "SpaceNews": "https://spacenews.com/feed/",
    "Phys.org": "https://phys.org/rss-feed/space-news/",
    "Ars Technica": "https://feeds.arstechnica.com/arstechnica/science",
}

BACKUP_FEEDS = {
    "Google News Aerospace": "https://news.google.com/rss/search?q=aerospace+propulsion+superconductor+quantum+breakthrough&hl=en-US&gl=US&ceid=US:en",
    "Google News Physics": "https://news.google.com/rss/search?q=antigravity+levitation+fusion+propulsion+warp+drive&hl=en-US&gl=US&ceid=US:en",
}

# --- Keyword Priority (highest to lowest) ---
KEYWORD_PRIORITY = [
    "antigravity", "propulsion", "quantum", "superconductor",
    "breakthrough", "levitation", "uap", "fusion propulsion",
    "zero gravity", "warp", "advanced materials", "fusion",
    "plasma", "ion drive", "hypersonic", "scramjet",
    "magnetohydrodynamic", "metamaterial", "topological",
]

ARTICLE_KEYWORDS = [
    "antigravity", "propulsion", "superconductor", "levitation",
    "uap", "quantum breakthrough", "fusion propulsion", "zero gravity",
    "warp research", "advanced materials", "quantum", "plasma",
    "ion drive", "hypersonic", "scramjet", "aerospace", "rocket",
    "spacecraft", "satellite", "orbit", "launch", "thruster",
    "magnetohydrodynamic", "metamaterial", "topological",
    "breakthrough", "fusion", "particle accelerator",
]

EXCLUDE_MARKERS = [
    "opinion", "editorial", "analysis", "blog", "commentary",
    "column", "perspective", "op-ed", "review", "podcast",
    "interview", "letter", "explainer", "quiz", "gallery",
    "conspiracy", "ufo sighting", "alien cover", "clickbait",
    "you won't believe", "shocking",
]

# --- Agency Detection ---
AGENCY_MAP = {
    "nasa":       "nasa.png",
    "spacex":     "spacex.png",
    "esa":        "esa.png",
    "cern":       "cern.png",
    "darpa":      "darpa.png",
    "lockheed":   "lockheed.png",
    "blue origin": "blueorigin.png",
    "dod":        "pentagon.png",
    "department of defense": "pentagon.png",
    "pentagon":   "pentagon.png",
    "boeing":     "boeing.png",
    "northrop":   "northrop.png",
}

# --- Colors ---
HEADER_COLOR = "#00E5FF"
FOOTER_COLOR = "#A1A1AA"
PANEL_BG = "#0F172A"
SEPARATOR_COLOR = "#FFFFFF"

# --- Drive ---
DRIVE_FOLDER_NAME = "Antigravity"

HTTP_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}

# Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("antigravity")


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


# ===========================================================================
# 1. RSS FEED SCRAPING
# ===========================================================================

def fetch_feeds() -> list[dict]:
    """Scrape all configured RSS feeds and return article dicts."""
    articles = []

    for source_name, url in RSS_FEEDS.items():
        log.info(f"Fetching feed: {source_name} → {url}")
        try:
            feed = feedparser.parse(url)
            entries = feed.get("entries", [])
            if not entries:
                log.warning(f"No entries from {source_name}")
            else:
                log.info(f"  → {source_name}: {len(entries)} entries fetched")

            for entry in entries:
                title = entry.get("title", "").strip()
                link = entry.get("link", "").strip()
                if not title or not link:
                    continue

                summary = ""
                if entry.get("summary"):
                    summary = BeautifulSoup(entry["summary"], "html.parser").get_text(strip=True)

                pub_date = None
                for date_field in ["published", "updated", "created"]:
                    if entry.get(date_field):
                        try:
                            pub_date = dateparser.parse(entry[date_field])
                        except Exception:
                            pass
                        break

                image_url = None
                if entry.get("media_content"):
                    for mc in entry["media_content"]:
                        if mc.get("url"):
                            image_url = mc["url"]
                            break
                if not image_url and entry.get("media_thumbnail"):
                    for mt in entry["media_thumbnail"]:
                        if mt.get("url"):
                            image_url = mt["url"]
                            break
                if not image_url and entry.get("links"):
                    for lnk in entry["links"]:
                        if lnk.get("type", "").startswith("image"):
                            image_url = lnk.get("href")
                            break

                articles.append({
                    "title": html.unescape(title),
                    "link": link,
                    "summary": html.unescape(summary) if summary else "",
                    "source": source_name,
                    "pub_date": pub_date,
                    "image_url": image_url,
                })
        except Exception as exc:
            log.warning(f"Failed to fetch {source_name}: {exc}")

    # Also try backup feeds
    for source_name, url in BACKUP_FEEDS.items():
        log.info(f"Fetching backup feed: {source_name}")
        try:
            feed = feedparser.parse(url)
            entries = feed.get("entries", [])
            if entries:
                log.info(f"  → {source_name}: {len(entries)} entries fetched")
            for entry in entries:
                title = entry.get("title", "").strip()
                link = entry.get("link", "").strip()
                if not title or not link:
                    continue
                summary = ""
                if entry.get("summary"):
                    summary = BeautifulSoup(entry["summary"], "html.parser").get_text(strip=True)
                pub_date = None
                for date_field in ["published", "updated", "created"]:
                    if entry.get(date_field):
                        try:
                            pub_date = dateparser.parse(entry[date_field])
                        except Exception:
                            pass
                        break
                articles.append({
                    "title": html.unescape(title),
                    "link": link,
                    "summary": html.unescape(summary) if summary else "",
                    "source": source_name,
                    "pub_date": pub_date,
                    "image_url": None,
                })
        except Exception as exc:
            log.warning(f"Failed to fetch backup {source_name}: {exc}")

    log.info(f"Total articles fetched: {len(articles)}")
    return articles


# ===========================================================================
# 2. FILTER FOR AEROSPACE/PHYSICS CONTENT
# ===========================================================================

def _text_contains_keyword(text: str, keywords: list[str]) -> bool:
    text_lower = text.lower()
    return any(kw in text_lower for kw in keywords)


def _text_contains_exclude(text: str) -> bool:
    text_lower = text.lower()
    return any(marker in text_lower for marker in EXCLUDE_MARKERS)


def filter_aerospace_news(articles: list[dict]) -> list[dict]:
    """Keep only articles matching aerospace/physics keywords."""
    filtered = []
    for article in articles:
        combined = f"{article['title']} {article['summary']}".lower()
        if _text_contains_exclude(combined):
            continue
        if _text_contains_keyword(combined, ARTICLE_KEYWORDS):
            filtered.append(article)
    log.info(f"Articles after aerospace/physics filter: {len(filtered)}")
    return filtered


# ===========================================================================
# 3. KEYWORD PRIORITY SCORING
# ===========================================================================

def _keyword_score(article: dict) -> int:
    """Lower score = higher priority."""
    combined = f"{article['title']} {article['summary']}".lower()
    for idx, kw in enumerate(KEYWORD_PRIORITY):
        if kw in combined:
            return idx
    return len(KEYWORD_PRIORITY) + 1


def sort_by_priority(articles: list[dict]) -> list[dict]:
    """Sort by publish datetime (latest first), then keyword priority."""
    def sort_key(a):
        pub = a.get("pub_date")
        if pub and pub.tzinfo:
            ts = pub.timestamp()
        elif pub:
            ts = pub.replace(tzinfo=timezone.utc).timestamp()
        else:
            ts = 0
        kw_score = _keyword_score(a)
        return (-ts, kw_score)

    return sorted(articles, key=sort_key)


# ===========================================================================
# 4. POSTED LINKS TRACKER (SHA256)
# ===========================================================================

def load_posted_links() -> dict:
    """Load posted_links.json → dict of {sha256: {url, timestamp}}."""
    if POSTED_LINKS_FILE.exists():
        try:
            with open(POSTED_LINKS_FILE, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_posted_links(data: dict) -> None:
    with open(POSTED_LINKS_FILE, "w") as f:
        json.dump(data, f, indent=2)


def url_hash(url: str) -> str:
    return hashlib.sha256(url.encode("utf-8")).hexdigest()


def is_already_posted(link: str, posted: dict) -> bool:
    return url_hash(link) in posted


def mark_as_posted(link: str, pub_date, posted: dict) -> dict:
    h = url_hash(link)
    posted[h] = {
        "url": link,
        "timestamp": pub_date.isoformat() if pub_date else datetime.now(timezone.utc).isoformat(),
    }
    return posted


# ===========================================================================
# 5. SELECT SINGLE ARTICLE (STRICT MODE)
# ===========================================================================

def select_article(articles: list[dict], posted: dict) -> dict | None:
    """Select the first valid, unposted article. Returns None if none found."""
    sorted_articles = sort_by_priority(articles)
    for article in sorted_articles:
        link = article.get("link", "")
        if not link:
            continue
        if is_already_posted(link, posted):
            continue
        return article
    return None


# ===========================================================================
# 6. ARTICLE IMAGE EXTRACTION
# ===========================================================================

def extract_article_image(article: dict) -> Image.Image | None:
    """Download and return the article's image, or None."""
    image_url = article.get("image_url")

    # Try og:image from the article page if no RSS image
    if not image_url:
        try:
            resp = requests.get(article["link"], headers=HTTP_HEADERS, timeout=8)
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, "html.parser")
                og = soup.find("meta", property="og:image")
                if og and og.get("content"):
                    image_url = og["content"]
        except Exception:
            pass

    if not image_url:
        return None

    try:
        log.info(f"  Downloading image: {image_url[:80]}…")
        resp = requests.get(image_url, headers=HTTP_HEADERS, timeout=10)
        if resp.status_code == 200:
            return Image.open(BytesIO(resp.content)).convert("RGBA")
    except Exception as exc:
        log.warning(f"  Failed to download image: {exc}")

    return None


# ===========================================================================
# 7. AGENCY DETECTION
# ===========================================================================

def detect_agencies(article: dict) -> list[str]:
    """Detect up to 2 agencies from headline + summary. Returns list of logo filenames."""
    combined = f"{article['title']} {article.get('summary', '')}".lower()
    detected = []

    for keyword, logo_file in AGENCY_MAP.items():
        if keyword in combined and logo_file not in detected:
            detected.append(logo_file)
            if len(detected) >= 2:
                break

    return detected


# ===========================================================================
# 8. AI ENHANCEMENT (SINGLE CALL, INSTANT FALLBACK)
# ===========================================================================

def _load_ai_usage() -> dict:
    if AI_USAGE_FILE.exists():
        try:
            with open(AI_USAGE_FILE, "r") as f:
                data = json.load(f)
            today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            if data.get("date") != today:
                return {"date": today, "gemini": 0, "huggingface": 0}
            return data
        except Exception:
            pass
    return {"date": datetime.now(timezone.utc).strftime("%Y-%m-%d"), "gemini": 0, "huggingface": 0}


def _save_ai_usage(data: dict):
    with open(AI_USAGE_FILE, "w") as f:
        json.dump(data, f, indent=2)


def _build_prompt(article: dict) -> str:
    title = article.get("title", "")
    summary = article.get("summary", "")[:800]
    return (
        f"Summarize the following aerospace/physics news.\n\n"
        f"Return strictly:\n"
        f"HEADLINE: (rewrite concisely)\n"
        f"SUMMARY: (3 lines maximum, factual, neutral)\n"
        f"STAGE: (theoretical / prototype / deployed / unknown)\n\n"
        f"Tone: Precise, technical, neutral.\n"
        f"No hype. No adjectives like 'mind-blowing'.\n"
        f"Keep under 200 words.\n\n"
        f"Article:\n{title}\n{summary}"
    )


def _parse_ai_response(text: str, article: dict) -> dict:
    """Parse AI response into structured fields."""
    headline = article["title"]
    summary_text = article.get("summary", "")[:300]
    stage = "unknown"

    lines = text.strip().split("\n")
    for line in lines:
        line_stripped = line.strip()
        if line_stripped.upper().startswith("HEADLINE:"):
            headline = line_stripped[9:].strip()
        elif line_stripped.upper().startswith("SUMMARY:"):
            summary_text = line_stripped[8:].strip()
        elif line_stripped.upper().startswith("STAGE:"):
            stage = line_stripped[6:].strip()

    # Collect multi-line summary
    in_summary = False
    summary_lines = []
    for line in lines:
        ls = line.strip()
        if ls.upper().startswith("SUMMARY:"):
            summary_lines.append(ls[8:].strip())
            in_summary = True
        elif in_summary:
            if ls.upper().startswith("STAGE:") or ls.upper().startswith("HEADLINE:"):
                in_summary = False
            elif ls:
                summary_lines.append(ls)

    if summary_lines:
        summary_text = " ".join(summary_lines)[:400]

    return {
        **article,
        "headline": headline,
        "ai_summary": summary_text,
        "stage": stage,
    }


def _internal_fallback(article: dict) -> dict:
    """Extract first 3 sentences as summary."""
    raw = article.get("summary", article.get("title", ""))
    sentences = re.split(r'(?<=[.!?])\s+', raw)
    summary = " ".join(sentences[:3])
    return {
        **article,
        "headline": article["title"],
        "ai_summary": summary[:400] if summary else article["title"],
        "stage": "unknown",
    }


def enhance_with_ai(article: dict) -> dict:
    """Single AI call with instant fallback. No retry loops."""
    usage = _load_ai_usage()
    prompt = _build_prompt(article)

    # --- Try Gemini (single call) ---
    gemini_key = os.environ.get("GEMINI_API_KEY")
    if gemini_key and usage.get("gemini", 0) < 10:
        try:
            import google.generativeai as genai
            genai.configure(api_key=gemini_key)
            model = genai.GenerativeModel("gemini-2.0-flash")
            response = model.generate_content(
                prompt,
                generation_config=genai.GenerationConfig(
                    max_output_tokens=400,
                    temperature=0.3,
                ),
            )
            if response and response.text:
                usage["gemini"] = usage.get("gemini", 0) + 1
                _save_ai_usage(usage)
                log.info("  AI: Gemini response received.")
                return _parse_ai_response(response.text, article)
        except Exception as exc:
            log.warning(f"  Gemini failed: {str(exc)[:120]}")

    # --- Try HuggingFace (single call) ---
    hf_key = os.environ.get("HUGGINGFACE_API_KEY")
    if hf_key and usage.get("huggingface", 0) < 20:
        try:
            hf_url = "https://router.huggingface.co/models/google/flan-t5-small"
            hf_resp = requests.post(
                hf_url,
                headers={"Authorization": f"Bearer {hf_key}"},
                json={"inputs": prompt[:1200]},
                timeout=15,
            )
            if hf_resp.status_code == 200:
                result = hf_resp.json()
                text = result[0].get("generated_text", "") if isinstance(result, list) else ""
                if text:
                    usage["huggingface"] = usage.get("huggingface", 0) + 1
                    _save_ai_usage(usage)
                    log.info("  AI: HuggingFace response received.")
                    return _parse_ai_response(text, article)
            else:
                log.warning(f"  HuggingFace failed with status {hf_resp.status_code}")
        except Exception as exc:
            log.warning(f"  HuggingFace failed: {str(exc)[:120]}")

    # --- Internal fallback ---
    log.info("  Using internal fallback text extraction.")
    return _internal_fallback(article)


# ===========================================================================
# 9. CARD GENERATION (60/40 SPLIT LAYOUT)
# ===========================================================================

def _hex_to_rgb(hex_color: str) -> tuple:
    h = hex_color.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _draw_gradient_overlay(img: Image.Image, direction="left_to_right", opacity=0.25) -> Image.Image:
    """Apply a black gradient overlay."""
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    w, h = img.size

    if direction == "left_to_right":
        for x in range(w):
            alpha = int(255 * opacity * (x / w))
            draw.line([(x, 0), (x, h)], fill=(0, 0, 0, alpha))

    return Image.alpha_composite(img.convert("RGBA"), overlay)


def _wrap_text(draw, text: str, font, max_width: int, max_lines: int = 4) -> list[str]:
    """Wrap text to fit within max_width, respecting max_lines."""
    words = text.split()
    lines = []
    current_line = ""

    for word in words:
        test = f"{current_line} {word}".strip()
        bbox = draw.textbbox((0, 0), test, font=font)
        if bbox[2] - bbox[0] <= max_width:
            current_line = test
        else:
            if current_line:
                lines.append(current_line)
            current_line = word
            if len(lines) >= max_lines:
                break

    if current_line and len(lines) < max_lines:
        lines.append(current_line)

    return lines[:max_lines]


def _auto_scale_font(draw, text: str, font_name: str, max_width: int, max_lines: int,
                     start_size: int = 48, min_size: int = 32) -> tuple:
    """Find the largest font size that fits the text."""
    for size in range(start_size, min_size - 1, -2):
        font = _load_font(font_name, size)
        lines = _wrap_text(draw, text, font, max_width, max_lines)
        if len(lines) <= max_lines:
            return font, lines
    font = _load_font(font_name, min_size)
    lines = _wrap_text(draw, text, font, max_width, max_lines)
    return font, lines


def generate_news_card(article: dict, output_path: Path) -> None:
    """Generate the 60/40 split aerospace news card."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    canvas = Image.new("RGBA", (CARD_WIDTH, CARD_HEIGHT), _hex_to_rgb(PANEL_BG) + (255,))

    left_width = int(CARD_WIDTH * 0.6)   # 648px
    right_width = CARD_WIDTH - left_width  # 432px

    # ── LEFT SIDE: Article Image ──
    article_img = extract_article_image(article)
    if article_img:
        # Resize to fill left panel
        img_ratio = article_img.width / article_img.height
        target_ratio = left_width / CARD_HEIGHT

        if img_ratio > target_ratio:
            new_h = CARD_HEIGHT
            new_w = int(new_h * img_ratio)
        else:
            new_w = left_width
            new_h = int(new_w / img_ratio)

        article_img = article_img.resize((new_w, new_h), Image.LANCZOS)

        # Center crop
        x_off = (new_w - left_width) // 2
        y_off = (new_h - CARD_HEIGHT) // 2
        article_img = article_img.crop((x_off, y_off, x_off + left_width, y_off + CARD_HEIGHT))

        # Slight contrast boost (+5%)
        enhancer = ImageEnhance.Contrast(article_img)
        article_img = enhancer.enhance(1.05)

        # 25% black gradient overlay (left to right)
        article_img = _draw_gradient_overlay(article_img, "left_to_right", 0.25)

        canvas.paste(article_img, (0, 0))
        log.info("  Layout: article image placed on left 60%")
    else:
        # No image: use dark carbon-textured background
        left_panel = Image.new("RGBA", (left_width, CARD_HEIGHT), (20, 20, 28, 255))
        draw_left = ImageDraw.Draw(left_panel)
        # Subtle grid pattern
        for y in range(0, CARD_HEIGHT, 20):
            draw_left.line([(0, y), (left_width, y)], fill=(30, 30, 40, 80), width=1)
        for x in range(0, left_width, 20):
            draw_left.line([(x, 0), (x, CARD_HEIGHT)], fill=(30, 30, 40, 80), width=1)
        canvas.paste(left_panel, (0, 0))
        log.info("  Layout: no article image, using carbon texture")

    # ── RIGHT SIDE: Agency Logos ──
    right_panel = Image.new("RGBA", (right_width, CARD_HEIGHT), _hex_to_rgb(PANEL_BG) + (255,))
    agencies = detect_agencies(article)

    if len(agencies) >= 2:
        # Dual logo split
        half_w = right_width // 2
        for i, logo_file in enumerate(agencies[:2]):
            logo_path = LOGOS_DIR / logo_file
            if logo_path.exists():
                try:
                    logo = Image.open(logo_path).convert("RGBA")
                    max_logo_size = min(half_w - 20, 160)
                    logo.thumbnail((max_logo_size, max_logo_size), Image.LANCZOS)
                    x = i * half_w + (half_w - logo.width) // 2
                    y = (CARD_HEIGHT - logo.height) // 2
                    right_panel.paste(logo, (x, y), logo)
                except Exception as exc:
                    log.warning(f"  Failed to load logo {logo_file}: {exc}")

        # 2px white separator line
        sep_draw = ImageDraw.Draw(right_panel)
        sep_draw.line([(half_w, SAFE_MARGIN), (half_w, CARD_HEIGHT - SAFE_MARGIN)],
                      fill=_hex_to_rgb(SEPARATOR_COLOR), width=2)
        log.info(f"  Layout: dual logos ({agencies[0]}, {agencies[1]})")

    elif len(agencies) == 1:
        # Single logo centered
        logo_path = LOGOS_DIR / agencies[0]
        if logo_path.exists():
            try:
                logo = Image.open(logo_path).convert("RGBA")
                max_logo_size = min(right_width - 40, 240)
                logo.thumbnail((max_logo_size, max_logo_size), Image.LANCZOS)
                x = (right_width - logo.width) // 2
                y = (CARD_HEIGHT - logo.height) // 2
                right_panel.paste(logo, (x, y), logo)
            except Exception as exc:
                log.warning(f"  Failed to load logo {agencies[0]}: {exc}")
        log.info(f"  Layout: single logo ({agencies[0]})")

    else:
        # No agency: neutral carbon texture (no sci-fi)
        draw_r = ImageDraw.Draw(right_panel)
        for y in range(0, CARD_HEIGHT, 16):
            draw_r.line([(0, y), (right_width, y)], fill=(25, 30, 45, 60), width=1)
        log.info("  Layout: no agency detected, carbon texture")

    canvas.paste(right_panel, (left_width, 0))

    # ── TEXT OVERLAY ──
    draw = ImageDraw.Draw(canvas)

    # Header: "🚀 BREAKING DISCOVERY"
    header_font = _load_font("header", 42)
    header_text = "🚀 BREAKING DISCOVERY"
    header_bbox = draw.textbbox((0, 0), header_text, font=header_font)
    header_w = header_bbox[2] - header_bbox[0]
    header_x = (CARD_WIDTH - header_w) // 2
    header_y = SAFE_MARGIN

    # Header background pill
    pill_padding = 16
    pill_rect = [
        header_x - pill_padding,
        header_y - pill_padding // 2,
        header_x + header_w + pill_padding,
        header_y + (header_bbox[3] - header_bbox[1]) + pill_padding // 2,
    ]
    draw.rounded_rectangle(pill_rect, radius=8, fill=(0, 0, 0, 180))
    draw.text((header_x, header_y), header_text, fill=HEADER_COLOR, font=header_font)

    # Headline
    headline = article.get("headline", article["title"])
    content_top = header_y + (header_bbox[3] - header_bbox[1]) + 40
    content_width = CARD_WIDTH - (SAFE_MARGIN * 2)

    headline_font, headline_lines = _auto_scale_font(
        draw, headline, "headline", content_width, max_lines=4, start_size=48, min_size=32
    )

    # Dark semi-transparent text background
    line_height = headline_font.size + 8
    text_block_height = len(headline_lines) * line_height + 20
    bg_rect = [
        SAFE_MARGIN - 10,
        content_top - 10,
        CARD_WIDTH - SAFE_MARGIN + 10,
        content_top + text_block_height,
    ]
    draw.rounded_rectangle(bg_rect, radius=6, fill=(0, 0, 0, 160))

    for i, line in enumerate(headline_lines):
        draw.text(
            (SAFE_MARGIN, content_top + i * line_height),
            line,
            fill="#FFFFFF",
            font=headline_font,
        )

    # Summary
    summary_text = article.get("ai_summary", article.get("summary", ""))
    if summary_text:
        summary_font = _load_font("summary", 24)
        summary_top = content_top + text_block_height + 20
        summary_lines = _wrap_text(draw, summary_text, summary_font, content_width, max_lines=3)

        s_line_height = 32
        s_block_height = len(summary_lines) * s_line_height + 16
        s_bg_rect = [
            SAFE_MARGIN - 10,
            summary_top - 8,
            CARD_WIDTH - SAFE_MARGIN + 10,
            summary_top + s_block_height,
        ]
        draw.rounded_rectangle(s_bg_rect, radius=6, fill=(0, 0, 0, 140))

        for i, line in enumerate(summary_lines):
            draw.text(
                (SAFE_MARGIN, summary_top + i * s_line_height),
                line,
                fill="#E0E0E0",
                font=summary_font,
            )

    # Footer
    footer_font = _load_font("footer", 18)
    source = article.get("source", "Unknown")
    pub = article.get("pub_date")
    if pub:
        date_str = pub.strftime("%d %b %Y")
        time_str = pub.strftime("%H:%M GMT")
    else:
        now = datetime.now(timezone.utc)
        date_str = now.strftime("%d %b %Y")
        time_str = now.strftime("%H:%M GMT")

    footer_text = f"SOURCE: {source.upper()} · {date_str.upper()} · {time_str}"

    # 1px separator line
    sep_y = CARD_HEIGHT - SAFE_MARGIN - 30
    draw.line(
        [(SAFE_MARGIN, sep_y), (CARD_WIDTH - SAFE_MARGIN, sep_y)],
        fill=_hex_to_rgb(FOOTER_COLOR), width=1,
    )

    footer_y = sep_y + 8
    draw.text((SAFE_MARGIN, footer_y), footer_text, fill=FOOTER_COLOR, font=footer_font)

    # Save
    canvas_rgb = canvas.convert("RGB")
    canvas_rgb.save(str(output_path), "PNG", quality=95)
    log.info(f"  Card saved: {output_path}")


# ===========================================================================
# 10. CAPTION GENERATION
# ===========================================================================

def generate_caption(article: dict, output_path: Path) -> None:
    """Generate the .txt caption file."""
    headline = article.get("headline", article["title"])
    summary = article.get("ai_summary", article.get("summary", ""))
    source = article.get("source", "Unknown")
    link = article.get("link", "")
    stage = article.get("stage", "unknown")
    pub = article.get("pub_date")

    pub_str = pub.strftime("%d %b %Y %H:%M GMT") if pub else "N/A"

    lines = [
        headline,
        "",
        summary,
        "",
        f"Development Stage: {stage.capitalize()}",
        "",
        "Sources:",
        f"• {source} — {link}",
        f"• Published: {pub_str}",
        "",
        "#Antigravity #Propulsion #QuantumPhysics #Aerospace #TechBreakthrough",
    ]

    output_path.write_text("\n".join(lines), encoding="utf-8")
    log.info(f"  Caption saved: {output_path}")


# ===========================================================================
# 11. FILENAME GENERATION
# ===========================================================================

def get_filename_prefix() -> str:
    now = datetime.now(timezone.utc)
    day = now.strftime("%d")
    month = now.strftime("%b").lower()
    hour = now.strftime("%I").lstrip("0") or "12"
    minute = now.strftime("%M")
    ampm = now.strftime("%p").lower()
    return f"{day}_{month}_{hour}-{minute}{ampm}"


# ===========================================================================
# 12. GOOGLE DRIVE UPLOAD
# ===========================================================================

def get_drive_service():
    """Build Google Drive API service using OAuth token or Service Account fallback."""
    try:
        from google.oauth2.credentials import Credentials
        from google.oauth2 import service_account
        from googleapiclient.discovery import build

        oauth_json = os.environ.get("GOOGLE_OAUTH_TOKEN_JSON")
        creds_json = os.environ.get("GOOGLE_CREDENTIALS_JSON")

        if oauth_json:
            log.info("Using Personal OAuth Token for Drive Authentication")
            creds_info = json.loads(oauth_json)
            credentials = Credentials.from_authorized_user_info(
                creds_info, scopes=["https://www.googleapis.com/auth/drive.file"]
            )
            return build("drive", "v3", credentials=credentials)
        elif creds_json:
            log.info("Using Service Account for Drive Authentication")
            creds_info = json.loads(creds_json)
            credentials = service_account.Credentials.from_service_account_info(
                creds_info, scopes=["https://www.googleapis.com/auth/drive.file"]
            )
            return build("drive", "v3", credentials=credentials)
        else:
            log.warning("No Drive credentials found. Skipping upload.")
            return None
    except Exception as exc:
        log.error(f"Failed to initialize Drive service: {exc}")
        return None


def find_or_create_folder(service, folder_name: str, parent_id: str = None) -> str:
    query = (
        f"name = '{folder_name}' and mimeType = 'application/vnd.google-apps.folder'"
        f" and trashed = false"
    )
    if parent_id:
        query += f" and '{parent_id}' in parents"

    results = service.files().list(
        q=query, spaces="drive", fields="files(id, name)",
        includeItemsFromAllDrives=True, supportsAllDrives=True,
    ).execute()
    files = results.get("files", [])

    if files:
        return files[0]["id"]

    metadata = {"name": folder_name, "mimeType": "application/vnd.google-apps.folder"}
    if parent_id:
        metadata["parents"] = [parent_id]

    folder = service.files().create(
        body=metadata, fields="id", supportsAllDrives=True,
    ).execute()
    log.info(f"Created Drive folder: {folder_name}")
    return folder["id"]


def upload_to_drive(service, filepath: Path, parent_folder_id: str) -> None:
    from googleapiclient.http import MediaFileUpload

    mime_map = {".png": "image/png", ".txt": "text/plain"}
    mime_type = mime_map.get(filepath.suffix, "application/octet-stream")

    file_metadata = {"name": filepath.name, "parents": [parent_folder_id]}
    media = MediaFileUpload(str(filepath), mimetype=mime_type)

    uploaded = service.files().create(
        body=file_metadata, media_body=media, fields="id, name", supportsAllDrives=True,
    ).execute()
    log.info(f"  Uploaded to Drive: {uploaded.get('name')} (ID: {uploaded.get('id')})")


def upload_files_to_drive(png_path: Path, txt_path: Path) -> None:
    service = get_drive_service()
    if not service:
        return

    try:
        DRIVE_ROOT_FOLDER_ID = "1AVFFrHH89quUE8wMO_C5XHu7T62RuBNZ"

        # Create Antigravity/Outputs structure
        antigravity_id = find_or_create_folder(service, "Antigravity", DRIVE_ROOT_FOLDER_ID)
        outputs_id = find_or_create_folder(service, "Outputs", antigravity_id)

        upload_to_drive(service, png_path, outputs_id)
        upload_to_drive(service, txt_path, outputs_id)
    except Exception as exc:
        log.error(f"Drive upload failed: {exc}")


# ===========================================================================
# 13. MAIN ORCHESTRATOR
# ===========================================================================

def main() -> None:
    """Main entry point — single article pipeline."""
    log.info("=" * 60)
    log.info("Aerospace & Physics Breaking News Automation — Starting run")
    log.info("=" * 60)

    # Step 1: Fetch all RSS feeds
    articles = fetch_feeds()
    if not articles:
        log.info("No articles fetched from any feed. Exiting.")
        return

    # Step 2: Filter for aerospace/physics content
    aero_articles = filter_aerospace_news(articles)
    if not aero_articles:
        log.info("No aerospace/physics news found. Exiting.")
        return

    # Step 3: Select single best article (strict mode)
    posted = load_posted_links()
    article = select_article(aero_articles, posted)
    if article is None:
        log.info("All matching articles already posted. Exiting.")
        return

    log.info(f"Selected article: {article['title'][:80]}…")
    log.info(f"Source: {article['source']} | Link: {article['link'][:60]}…")

    # Step 4: Enhance with AI (single call)
    enhanced = enhance_with_ai(article)

    # Step 5: Generate card + caption
    prefix = get_filename_prefix()
    png_path = OUTPUT_DIR / f"{prefix}.png"
    txt_path = OUTPUT_DIR / f"{prefix}.txt"

    generate_news_card(enhanced, png_path)
    generate_caption(enhanced, txt_path)

    # Step 6: Upload to Drive
    upload_files_to_drive(png_path, txt_path)

    # Step 7: Mark as posted
    posted = mark_as_posted(article["link"], article.get("pub_date"), posted)
    save_posted_links(posted)
    log.info("Updated posted_links.json.")

    log.info("=" * 60)
    log.info("Run complete. One card generated.")
    log.info("=" * 60)


if __name__ == "__main__":
    main()
