"""Image outputs: original comics, archive thumbnails, social cards and favicons."""

from __future__ import annotations

import shutil
from pathlib import Path

from PIL import Image as PILImage
from PIL import ImageDraw

from .content import Comic

CARD_SIZE = (1200, 630)  # the size Facebook, LinkedIn and X all render as a large card
CARD_GROUND = (255, 244, 250)  # --ground in Samantha mode
CARD_PANEL = (255, 255, 255)
THUMB_WIDTH = 320


def copy_originals(comics: tuple[Comic, ...], content: Path, out: Path) -> None:
    for comic in comics:
        for img in comic.images:
            dest = out / "images" / img.file
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(content / img.file, dest)


def thumbnail(comic: Comic, content: Path, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    with PILImage.open(content / comic.image.file) as im:
        flat = PILImage.new("RGB", im.size, (255, 255, 255))  # transparency -> white, not black
        flat.paste(im.convert("RGBA"), mask=im.convert("RGBA"))
        im = flat
        ratio = THUMB_WIDTH / im.width
        im = im.resize((THUMB_WIDTH, round(im.height * ratio)), PILImage.LANCZOS)
        im.save(dest, "WEBP", quality=82, method=6)


def _paste_fit(card: PILImage.Image, art: PILImage.Image, box: tuple[int, int, int, int]) -> None:
    x0, y0, x1, y1 = box
    art = art.copy()
    art.thumbnail((x1 - x0, y1 - y0), PILImage.LANCZOS)
    x = x0 + (x1 - x0 - art.width) // 2
    y = y0 + (y1 - y0 - art.height) // 2
    card.paste(art, (x, y), art if art.mode == "RGBA" else None)


def social_card(comic: Comic | None, content: Path, dest: Path) -> None:
    """1200x630: the comic on a white panel at left, her banner (Scribbles included) at right."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    card = PILImage.new("RGB", CARD_SIZE, CARD_GROUND)
    draw = ImageDraw.Draw(card)
    brand = content / "brand"
    with PILImage.open(brand / "banner.png") as banner:
        if comic is None:
            _paste_fit(card, banner.convert("RGBA"), (60, 140, 1140, 490))
        else:
            draw.rounded_rectangle((30, 25, 615, 605), radius=28, fill=CARD_PANEL)
            with PILImage.open(content / comic.image.file) as art:
                _paste_fit(card, art.convert("RGBA"), (50, 45, 595, 585))
            _paste_fit(card, banner.convert("RGBA"), (640, 60, 1175, 570))
    card.save(dest, "JPEG", quality=86, optimize=True, progressive=True)


def favicons(content: Path, out: Path) -> None:
    with PILImage.open(content / "brand" / "scribbles.png") as dog:
        dog = dog.convert("RGBA")
        for name, size, ground in (("favicon.png", 64, None), ("apple-touch-icon.png", 180, CARD_GROUND)):
            icon = PILImage.new("RGBA", (size, size), ground + (255,) if ground else (0, 0, 0, 0))
            pad = size // 10 if ground else 0
            _paste_fit(icon, dog, (pad, pad, size - pad, size - pad))
            icon.save(out / name, "PNG", optimize=True)
