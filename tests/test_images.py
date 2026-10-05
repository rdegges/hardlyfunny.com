"""The PNGs in content/ are recompressed losslessly (scripts/compress_pngs.py).

Each one must decode pixel-identical to its untouched twin in archive/: the same width and
height, and the same bytes after Image.convert("RGBA"). Converting first lets a palette file
and an RGBA file of the same picture compare equal, and catches any change to a color or
to transparency. Comics pair by `number` and image index (content images[i].file with
archive images[i].src); brand art pairs by file name.
"""

import json

from PIL import Image as PILImage

from hardlyfunny.build import CONTENT, ROOT

ARCHIVE = ROOT / "archive"


def png_pairs() -> list[tuple]:
    archive = {c["number"]: c for c in json.loads((ARCHIVE / "comics.json").read_text())["comics"]}
    pairs = []
    for comic in json.loads((CONTENT / "comics.json").read_text())["comics"]:
        assert comic["number"] in archive, f"#{comic['number']} is not in archive/comics.json"
        twins = archive[comic["number"]]["images"]
        assert len(twins) == len(comic["images"]), f"#{comic['number']} image count differs from archive/"
        for img, twin in zip(comic["images"], twins):
            if img["file"].endswith(".png"):
                pairs.append((CONTENT / img["file"], ARCHIVE / twin["src"]))
    pairs += [(png, ARCHIVE / "brand" / png.name) for png in sorted((CONTENT / "brand").glob("*.png"))]
    return pairs


def test_every_content_png_has_an_archive_twin():
    pairs = png_pairs()
    paired = [content for content, _ in pairs]
    every_png = sorted(CONTENT.rglob("*.png"))
    assert every_png, "no PNGs under content/"
    assert len(paired) == len(set(paired)), "a content PNG is listed twice"
    assert sorted(paired) == every_png
    for _, twin in pairs:
        assert twin.is_file(), f"missing archive twin {twin.relative_to(ROOT)}"
    # Renamed slugs and the one two-image comic, so pairing by name alone can't pass.
    known = {
        "qwerty.png": "014-3.png",
        "first-impressions.png": "017-first-impressions.png",
        "first-impressions-2.png": "017-first-impressions-2.png",
        "holiday-shopping.png": "020-shopping-with-a-nerd.png",
        "wow.png": "023-w-o-w.png",
        "time-machine.png": "044-uncommon-problems.png",
        "precious-heartbeats.png": "061-507.png",
        "slow-internet.png": "074-all-hope-is-lost.png",
    }
    names = {c.name: a.name for c, a in pairs}
    assert {name: names.get(name) for name in known} == known


def test_every_content_png_has_its_archive_twins_pixels():
    pairs = png_pairs()
    assert pairs
    changed = []
    for content, twin in pairs:
        with PILImage.open(content) as new, PILImage.open(twin) as old:
            if new.size != old.size or new.convert("RGBA").tobytes() != old.convert("RGBA").tobytes():
                changed.append(str(content.relative_to(ROOT)))
    assert not changed, f"pixels differ from archive/: {changed}"
