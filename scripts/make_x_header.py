#!/usr/bin/env python3
"""Draw the X (@hardlyfunnycom) profile header into social/x-header.png.

It lives outside content/ because the build would publish it and tests/test_images.py
expects every PNG there to have an archive/ twin. X shows headers at 3:1 and puts the
avatar over the bottom-left corner (about a quarter of the width on phones), so the
banner art sits high and to the right. The seed keeps the pixel squares the same.
"""

import random
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
W, H = 1500, 500

header = Image.new("RGBA", (W, H), "#fff4fa")
draw = ImageDraw.Draw(header)
random.seed(7)
# Soft squares echo the pixel heart behind the couple in the banner.
for _ in range(90):
    size = random.choice([18, 24, 30, 36])
    x, y = random.randrange(0, W), random.randrange(0, H)
    draw.rectangle([x, y, x + size, y + size], fill=random.choice(["#ffd6f0", "#ffc2e8", "#ffe6f5", "#f6d3ea"]))

with Image.open(ROOT / "content" / "brand" / "banner.png") as banner:
    banner = banner.convert("RGBA")
    banner = banner.resize((int(banner.width * 1.2), int(banner.height * 1.2)), Image.LANCZOS)
header.alpha_composite(banner, (W - banner.width - 20, 22))

out = ROOT / "social" / "x-header.png"
out.parent.mkdir(exist_ok=True)
header.convert("RGB").save(out, optimize=True)
print(out.relative_to(ROOT))
