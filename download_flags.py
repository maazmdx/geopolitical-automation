#!/usr/bin/env python3
"""
Download country flag images for the 60/40 split layout.
Flags are desaturated and muted during card generation, not here.
Source: flagcdn.com (public, no auth required)
"""

import os
import requests
from pathlib import Path

FLAGS_DIR = Path(__file__).resolve().parent / "assets" / "flags"
FLAGS_DIR.mkdir(parents=True, exist_ok=True)

# Country name → ISO 3166-1 alpha-2 code
COUNTRY_CODES = {
    "russia": "ru",
    "ukraine": "ua",
    "israel": "il",
    "palestine": "ps",
    "iran": "ir",
    "china": "cn",
    "taiwan": "tw",
    "pakistan": "pk",
    "india": "in",
    "syria": "sy",
    "lebanon": "lb",
    "yemen": "ye",
    "iraq": "iq",
    "afghanistan": "af",
    "north_korea": "kp",
    "usa": "us",
    "turkey": "tr",
    "saudi": "sa",
    "egypt": "eg",
    "sudan": "sd",
    "libya": "ly",
    "somalia": "so",
    "myanmar": "mm",
    "uk": "gb",
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; FlagDownloader/1.0)"
}


def download_flags():
    print("Downloading country flags…")
    for name, code in COUNTRY_CODES.items():
        filepath = FLAGS_DIR / f"{name}.png"
        if filepath.exists():
            print(f"  ✓ {name} (cached)")
            continue

        # flagcdn provides flags at various widths
        url = f"https://flagcdn.com/w640/{code}.png"
        try:
            resp = requests.get(url, headers=HEADERS, timeout=10)
            resp.raise_for_status()
            filepath.write_bytes(resp.content)
            print(f"  ✓ {name} ({len(resp.content)} bytes)")
        except Exception as exc:
            print(f"  ✗ {name}: {exc}")

    print(f"\nDone! Flags saved to {FLAGS_DIR}")


if __name__ == "__main__":
    download_flags()
