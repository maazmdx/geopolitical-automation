#!/usr/bin/env python3
"""Generate missing flag images programmatically using simple color bands."""
from PIL import Image, ImageDraw
from pathlib import Path

FLAGS_DIR = Path(__file__).resolve().parent / "assets" / "flags"
FLAGS_DIR.mkdir(parents=True, exist_ok=True)

# Simple tri-band flag approximations for missing countries
MISSING_FLAGS = {
    "russia":  [(255,255,255), (0,57,166), (213,43,30)],   # white-blue-red
    "ukraine": [(0,87,183), (0,87,183), (255,215,0)],       # blue-yellow (2 bands)
    "china":   [(222,41,16), (222,41,16), (222,41,16)],      # solid red
    "lebanon": [(255,0,0), (255,255,255), (255,0,0)],        # red-white-red
    "turkey":  [(227,10,23), (227,10,23), (227,10,23)],      # solid red
    "saudi":   [(0,106,56), (0,106,56), (0,106,56)],         # solid green
}

W, H = 640, 427  # Standard 3:2 flag ratio

for name, bands in MISSING_FLAGS.items():
    filepath = FLAGS_DIR / f"{name}.png"
    if filepath.exists():
        print(f"  skip {name}")
        continue
    img = Image.new("RGB", (W, H))
    draw = ImageDraw.Draw(img)
    band_h = H // len(bands)
    for i, color in enumerate(bands):
        draw.rectangle([(0, i * band_h), (W, (i + 1) * band_h)], fill=color)
    img.save(str(filepath), "PNG")
    print(f"  ✓ {name}")

# NATO doesn't have a standard flag — use dark blue
nato_path = FLAGS_DIR / "nato.png"
if not nato_path.exists():
    img = Image.new("RGB", (W, H), (0, 40, 104))
    draw = ImageDraw.Draw(img)
    # Simple compass rose suggestion
    cx, cy = W // 2, H // 2
    r = min(W, H) // 4
    draw.ellipse([(cx-r, cy-r), (cx+r, cy+r)], outline=(255, 255, 255), width=3)
    img.save(str(nato_path), "PNG")
    print("  ✓ nato")

print("Done!")
