"""The PNGs in content/ are recompressed losslessly (scripts/compress_pngs.py).

Each one must decode pixel-identical to its untouched twin in archive/: the same width and
height, and the same bytes after Image.convert("RGBA"). Converting first lets a palette file
and an RGBA file of the same picture compare equal, and catches any change to a color or
to transparency. Comics pair by `number` and image index (content images[i].file with
archive images[i].src); brand art pairs by file name.
"""

import json
import struct

from PIL import Image as PILImage

from hardlyfunny.build import CONTENT, ROOT

ARCHIVE = ROOT / "archive"
RULE = "every PNG in content/ must have its untouched original in archive/ (see README, Adding a comic)"
# Chunks that change how a browser renders the pixels. Losing one is a visible change even
# though the decoded pixels match.
COLOR_CHUNKS = (b"gAMA", b"cHRM", b"sRGB", b"iCCP")


def same_pixels(a: PILImage.Image, b: PILImage.Image) -> bool:
    return a.size == b.size and a.convert("RGBA").tobytes() == b.convert("RGBA").tobytes()


def color_chunks(png: bytes) -> list[tuple[bytes, bytes]]:
    chunks, i = [], 8
    while i < len(png):
        length, kind = struct.unpack(">I4s", png[i : i + 8])
        if kind in COLOR_CHUNKS:
            chunks.append((kind, png[i + 8 : i + 8 + length]))
        i += 12 + length
    return sorted(chunks)


def png_pairs() -> list[tuple]:
    archive = {c["number"]: c for c in json.loads((ARCHIVE / "comics.json").read_text())["comics"]}
    pairs = []
    for comic in json.loads((CONTENT / "comics.json").read_text())["comics"]:
        assert comic["number"] in archive, f"{RULE}: #{comic['number']} is not in archive/comics.json"
        twins = archive[comic["number"]]["images"]
        assert len(twins) == len(comic["images"]), f"{RULE}: #{comic['number']} image count differs from archive/"
        for img, twin in zip(comic["images"], twins):
            if img["file"].endswith(".png"):
                pairs.append((CONTENT / img["file"], ARCHIVE / twin["src"]))
    pairs += [(png, ARCHIVE / "brand" / png.name) for png in sorted((CONTENT / "brand").glob("*.png"))]
    for _, twin in pairs:
        assert twin.is_file(), f"{RULE}: missing {twin.relative_to(ROOT)}"
    return pairs


def test_every_content_png_has_an_archive_twin():
    pairs = png_pairs()
    paired = [content for content, _ in pairs]
    every_png = sorted(CONTENT.rglob("*.png"))
    assert every_png, "no PNGs under content/"
    assert len(paired) == len(set(paired)), "a content PNG is listed twice"
    strays = [str(png.relative_to(ROOT)) for png in every_png if png not in paired]
    assert sorted(paired) == every_png, f"{RULE}: no original for {strays}"
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
            if not same_pixels(new, old):
                changed.append(str(content.relative_to(ROOT)))
    assert not changed, f"pixels differ from archive/: {changed}"


def test_every_content_png_keeps_its_archive_twins_color_chunks():
    # Pixel equality alone passes a file that lost gAMA/cHRM/sRGB/iCCP, but a color-managed
    # browser then draws it differently. first-impressions-2.png is the one file that has them.
    pairs = png_pairs()
    with_color = [c.name for c, a in pairs if color_chunks(a.read_bytes())]
    assert with_color == ["first-impressions-2.png"]
    changed = [
        str(content.relative_to(ROOT))
        for content, twin in pairs
        if color_chunks(content.read_bytes()) != color_chunks(twin.read_bytes())
    ]
    assert not changed, f"color chunks differ from archive/: {changed}"


def test_same_pixels_ignores_encoding_but_catches_any_visible_change():
    # The pixel test above is only as good as this comparison, so prove it can fail.
    rgba = PILImage.new("RGBA", (3, 2), (255, 255, 255, 255))
    rgba.putpixel((1, 1), (0, 0, 0, 255))
    palette = rgba.convert("RGB").quantize(colors=2).convert("P")
    assert palette.mode == "P" and same_pixels(palette, rgba)

    one_pixel = rgba.copy()
    one_pixel.putpixel((2, 0), (254, 255, 255, 255))
    assert not same_pixels(one_pixel, rgba)

    see_through = rgba.copy()
    see_through.putpixel((0, 0), (255, 255, 255, 254))
    assert not same_pixels(see_through, rgba)

    assert not same_pixels(rgba.crop((0, 0, 3, 1)), rgba)
    assert not same_pixels(rgba.transpose(PILImage.Transpose.FLIP_TOP_BOTTOM), rgba)


def test_color_chunks_reads_every_color_chunk_and_nothing_else():
    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I4s", len(data), kind) + data + b"\0\0\0\0"  # CRC isn't read

    ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 0, 0, 0, 0)
    png = b"\x89PNG\r\n\x1a\n" + b"".join([
        chunk(b"IHDR", ihdr), chunk(b"sRGB", b"\0"), chunk(b"tEXt", b"gAMA\0fake"),
        chunk(b"gAMA", b"\0\0\xb1\x8f"), chunk(b"iCCP", b"p\0\0x"), chunk(b"cHRM", b"c" * 32),
        chunk(b"IDAT", b""), chunk(b"IEND", b""),
    ])
    assert color_chunks(png) == sorted([
        (b"sRGB", b"\0"), (b"gAMA", b"\0\0\xb1\x8f"), (b"iCCP", b"p\0\0x"), (b"cHRM", b"c" * 32),
    ])
    assert color_chunks(png[:8] + chunk(b"IHDR", ihdr) + chunk(b"IEND", b"")) == []
