#!/usr/bin/env python3
"""
Generate all required visual assets for the geopolitics automation system:
1. High-resolution dark world map (2048x1024 Mercator projection)
2. Country-specific locator maps with red markers
3. Dark silhouette images for key geopolitical actors/regions
"""

import math
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

BASE_DIR = Path(__file__).resolve().parent
ASSETS_DIR = BASE_DIR / "assets"
FLAGS_DIR = ASSETS_DIR / "flags"

# Colors
OCEAN = (8, 12, 21)          # #080C15 — deep dark navy
LAND = (25, 32, 45)          # #19202D — dark slate
BORDER = (40, 50, 65)        # #283241 — subtle border
GRID = (15, 20, 30)          # #0F141E — very subtle grid
MARKER = (217, 4, 41)        # #D90429 — red marker
MARKER_GLOW = (217, 4, 41, 80)
TEXT_COLOR = (161, 161, 170)  # #A1A1AA — footer gray


def _hex(color):
    h = color.lstrip("#")
    return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))


# ═══════════════════════════════════════════════════════════
# SIMPLIFIED CONTINENT POLYGONS (Mercator lat/lon coordinates)
# ═══════════════════════════════════════════════════════════

# Rough continent outlines for a stylized dark map
CONTINENTS = {
    "north_america": [
        (-170, 65), (-168, 72), (-141, 70), (-130, 72), (-120, 60),
        (-125, 50), (-120, 33), (-105, 25), (-98, 20), (-87, 15),
        (-82, 10), (-80, 8), (-78, 10), (-75, 12), (-62, 47),
        (-55, 48), (-55, 52), (-60, 54), (-65, 60), (-75, 62),
        (-80, 65), (-95, 68), (-120, 70), (-140, 68), (-170, 65),
    ],
    "south_america": [
        (-82, 10), (-78, 2), (-70, -5), (-75, -15), (-70, -20),
        (-68, -22), (-65, -28), (-58, -35), (-68, -52), (-75, -53),
        (-72, -45), (-75, -30), (-80, -5), (-82, 10),
    ],
    "europe": [
        (-10, 36), (-5, 36), (3, 37), (10, 37), (15, 38),
        (28, 36), (30, 40), (28, 42), (25, 42), (28, 45),
        (30, 48), (24, 55), (28, 58), (30, 62), (25, 65),
        (20, 68), (15, 70), (5, 62), (0, 52), (-5, 44),
        (-10, 44), (-10, 36),
    ],
    "africa": [
        (-18, 15), (-15, 28), (-5, 36), (10, 37), (15, 32),
        (25, 32), (33, 30), (35, 20), (42, 12), (50, 12),
        (52, 2), (42, -5), (40, -12), (35, -25), (30, -30),
        (28, -34), (18, -35), (12, -18), (10, -5), (8, 5),
        (-5, 5), (-10, 8), (-18, 15),
    ],
    "asia": [
        (28, 36), (35, 32), (45, 25), (50, 25), (55, 25),
        (60, 25), (65, 25), (70, 25), (75, 15), (78, 8),
        (80, 10), (85, 22), (90, 22), (95, 15), (100, 5),
        (105, -6), (115, -8), (120, 0), (125, 5), (130, 35),
        (135, 35), (140, 45), (145, 50), (155, 60), (170, 65),
        (180, 68), (180, 72), (120, 72), (100, 68), (80, 70),
        (60, 68), (50, 55), (40, 48), (30, 48), (28, 42),
        (28, 36),
    ],
    "australia": [
        (115, -15), (120, -14), (130, -12), (137, -14),
        (142, -12), (145, -15), (150, -25), (153, -28),
        (150, -35), (142, -38), (135, -35), (125, -33),
        (115, -30), (114, -22), (115, -15),
    ],
}

# Key geopolitical hotspots with lat/lon
HOTSPOT_COUNTRIES = {
    "us": ("United States", 39.0, -98.0),
    "ru": ("Russia", 60.0, 100.0),
    "ua": ("Ukraine", 49.0, 32.0),
    "cn": ("China", 35.0, 105.0),
    "ir": ("Iran", 32.0, 53.0),
    "il": ("Israel", 31.5, 34.8),
    "ps": ("Palestine", 31.9, 35.2),
    "kp": ("North Korea", 40.0, 127.0),
    "kr": ("South Korea", 36.0, 128.0),
    "tw": ("Taiwan", 23.5, 121.0),
    "tr": ("Turkey", 39.0, 35.0),
    "in": ("India", 21.0, 78.0),
    "pk": ("Pakistan", 30.0, 70.0),
    "sy": ("Syria", 35.0, 38.0),
    "iq": ("Iraq", 33.0, 44.0),
    "sa": ("Saudi Arabia", 24.0, 45.0),
    "jp": ("Japan", 36.0, 138.0),
    "gb": ("United Kingdom", 54.0, -2.0),
    "fr": ("France", 46.0, 2.0),
    "de": ("Germany", 51.0, 10.0),
    "ye": ("Yemen", 15.5, 48.0),
    "lb": ("Lebanon", 33.9, 35.9),
    "eg": ("Egypt", 26.0, 30.0),
    "af": ("Afghanistan", 33.0, 65.0),
    "sd": ("Sudan", 16.0, 32.0),
    "mm": ("Myanmar", 19.0, 96.0),
    "ly": ("Libya", 27.0, 17.0),
    "pl": ("Poland", 52.0, 20.0),
    "so": ("Somalia", 6.0, 46.0),
    "et": ("Ethiopia", 9.0, 38.7),
}


def latlon_to_pixel(lat, lon, w, h):
    """Convert lat/lon to pixel coordinates on a Mercator projection."""
    px = int((lon + 180) / 360 * w)
    lat_rad = math.radians(max(-85, min(85, lat)))
    merc_y = math.log(math.tan(math.pi / 4 + lat_rad / 2))
    py = int((1 - (merc_y / math.pi + 1) / 2) * h)
    return px, py


def draw_polygon(draw, points, w, h, fill, outline=None):
    """Draw a polygon from lat/lon coordinates."""
    pixels = [latlon_to_pixel(lat, lon, w, h) for lon, lat in points]
    draw.polygon(pixels, fill=fill, outline=outline)


def generate_dark_world_map():
    """Generate a high-resolution dark world map."""
    print("Generating dark_world_map.png (2048x1024)...")

    W, H = 2048, 1024
    img = Image.new("RGB", (W, H), OCEAN)
    draw = ImageDraw.Draw(img)

    # Draw subtle grid lines (every 30 degrees)
    for lon in range(-180, 181, 30):
        px, _ = latlon_to_pixel(0, lon, W, H)
        draw.line([(px, 0), (px, H)], fill=GRID, width=1)
    for lat in range(-60, 61, 30):
        _, py = latlon_to_pixel(lat, 0, W, H)
        draw.line([(0, py), (W, py)], fill=GRID, width=1)

    # Draw continents
    for name, polygon in CONTINENTS.items():
        draw_polygon(draw, polygon, W, H, fill=LAND, outline=BORDER)

    # Save
    output = ASSETS_DIR / "dark_world_map.png"
    img.save(str(output), "PNG")
    print(f"  Saved: {output} ({W}x{H})")
    return img


def generate_country_locator_maps():
    """Generate country-specific locator maps with red markers."""
    print("Generating country locator maps...")

    base_map = ASSETS_DIR / "dark_world_map.png"
    if not base_map.exists():
        print("  Base map not found, generating first...")
        generate_dark_world_map()

    world = Image.open(base_map).convert("RGBA")
    W, H = world.size

    maps_dir = ASSETS_DIR / "country_maps"
    maps_dir.mkdir(parents=True, exist_ok=True)

    for code, (name, lat, lon) in HOTSPOT_COUNTRIES.items():
        img = world.copy()
        draw = ImageDraw.Draw(img)

        px, py = latlon_to_pixel(lat, lon, W, H)

        # Glow ring (outer)
        for r in range(20, 8, -2):
            alpha = int(40 * (20 - r) / 12)
            draw.ellipse(
                [(px - r, py - r), (px + r, py + r)],
                outline=(*MARKER, alpha),
                width=2,
            )

        # Solid marker (inner)
        r = 10
        draw.ellipse(
            [(px - r, py - r), (px + r, py + r)],
            fill=MARKER,
            outline=(255, 255, 255),
            width=2,
        )

        # Small label
        try:
            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 18)
        except Exception:
            font = ImageFont.load_default()

        label = name.upper()
        bbox = draw.textbbox((0, 0), label, font=font)
        tw = bbox[2] - bbox[0]
        lx = max(5, min(px - tw // 2, W - tw - 5))
        ly = py + 16
        # Background for label
        draw.rectangle(
            [(lx - 4, ly - 2), (lx + tw + 4, ly + 20)],
            fill=(8, 12, 21, 200),
        )
        draw.text((lx, ly), label, fill=TEXT_COLOR, font=font)

        output = maps_dir / f"{code}_locator.png"
        img.save(str(output), "PNG")
        print(f"  {code}: {name} saved → {output.name}")


def generate_dark_actor_images():
    """Generate dark silhouette profile images for key actors/regions."""
    print("Generating dark actor silhouette images...")

    actors_dir = ASSETS_DIR / "actors"
    actors_dir.mkdir(parents=True, exist_ok=True)

    # Key geopolitical actors with their visual style
    actors = {
        "military": {"label": "ARMED FORCES", "icon": "⚔", "bg": (15, 20, 35)},
        "diplomat": {"label": "DIPLOMACY", "icon": "🏛", "bg": (12, 18, 30)},
        "conflict": {"label": "CONFLICT ZONE", "icon": "💥", "bg": (25, 10, 10)},
        "sanctions": {"label": "SANCTIONS", "icon": "⛔", "bg": (20, 15, 10)},
        "nuclear": {"label": "NUCLEAR", "icon": "☢", "bg": (20, 20, 8)},
        "ceasefire": {"label": "CEASEFIRE", "icon": "🕊", "bg": (10, 18, 25)},
        "crisis": {"label": "CRISIS", "icon": "🚨", "bg": (30, 8, 8)},
        "alliance": {"label": "ALLIANCE", "icon": "🤝", "bg": (10, 15, 25)},
    }

    for key, info in actors.items():
        W, H = 800, 800
        img = Image.new("RGB", (W, H), info["bg"])
        draw = ImageDraw.Draw(img)

        # Subtle radial gradient
        cx, cy = W // 2, H // 2
        for r in range(min(W, H) // 2, 0, -1):
            alpha = int(30 * r / (min(W, H) // 2))
            color = tuple(min(255, c + alpha) for c in info["bg"])
            draw.ellipse(
                [(cx - r, cy - r), (cx + r, cy + r)],
                outline=color,
            )

        # Grid overlay
        for x in range(0, W, 40):
            draw.line([(x, 0), (x, H)], fill=GRID, width=1)
        for y in range(0, H, 40):
            draw.line([(0, y), (W, y)], fill=GRID, width=1)

        # Icon (large)
        try:
            icon_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 120)
        except Exception:
            icon_font = ImageFont.load_default()

        icon = info["icon"]
        ibbox = draw.textbbox((0, 0), icon, font=icon_font)
        iw = ibbox[2] - ibbox[0]
        ih = ibbox[3] - ibbox[1]
        draw.text(((W - iw) // 2, (H - ih) // 2 - 40), icon, fill=(60, 70, 85), font=icon_font)

        # Label
        try:
            label_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 32)
        except Exception:
            label_font = ImageFont.load_default()

        label = info["label"]
        lbbox = draw.textbbox((0, 0), label, font=label_font)
        lw = lbbox[2] - lbbox[0]
        draw.text(((W - lw) // 2, H - 120), label, fill=TEXT_COLOR, font=label_font)

        # Red accent line
        draw.line([(W // 2 - 60, H - 80), (W // 2 + 60, H - 80)], fill=MARKER, width=3)

        output = actors_dir / f"{key}.png"
        img.save(str(output), "PNG")
        print(f"  {key}: {info['label']} saved → {output.name}")


if __name__ == "__main__":
    ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    FLAGS_DIR.mkdir(parents=True, exist_ok=True)

    generate_dark_world_map()
    generate_country_locator_maps()
    generate_dark_actor_images()

    print("\n✓ All assets generated successfully!")
