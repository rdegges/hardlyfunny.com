#!/usr/bin/env python3
"""Losslessly recompress every PNG under content/ in place.

Needs zopflipng (Debian package `zopfli`) and pyoxipng, so run it in Docker (see README).
Each file gets the smallest of: the original, zopflipng's output and oxipng's output. A
candidate only counts if it decodes to the same mode, size and pixels as the original and
keeps every color chunk (gAMA, cHRM, sRGB, iCCP) byte for byte. Only text metadata goes.
"""

from __future__ import annotations

import struct
import subprocess
import sys
import tempfile
from pathlib import Path

import oxipng
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
CONTENT = ROOT / "content"
COLOR_CHUNKS = (b"gAMA", b"cHRM", b"sRGB", b"iCCP")


def color_chunks(png: bytes) -> list[tuple[bytes, bytes]]:
    chunks, i = [], 8
    while i < len(png):
        length, kind = struct.unpack(">I4s", png[i : i + 8])
        if kind in COLOR_CHUNKS:
            chunks.append((kind, png[i + 8 : i + 8 + length]))
        i += 12 + length
    return sorted(chunks)


def decoded(path: Path) -> tuple[str, tuple[int, int], bytes]:
    with Image.open(path) as im:
        return im.mode, im.size, im.convert("RGBA").tobytes()


def compress(src: Path, tmp: Path) -> tuple[str, int, int]:
    zop, oxi = tmp / "zopflipng.png", tmp / "oxipng.png"
    subprocess.run(
        ["zopflipng", "-y", "-m", "--keepchunks=gAMA,cHRM,sRGB,iCCP,pHYs", str(src), str(zop)],
        check=True,
        capture_output=True,
    )
    oxipng.optimize(src, oxi, level=6, strip=oxipng.StripChunks.safe())

    original = src.read_bytes()
    want_pixels, want_chunks = decoded(src), color_chunks(original)
    best, best_name = original, "original"
    for name, path in (("zopflipng", zop), ("oxipng", oxi)):
        data = path.read_bytes()
        if len(data) < len(best) and decoded(path) == want_pixels and color_chunks(data) == want_chunks:
            best, best_name = data, name
    if best is not original:
        src.write_bytes(best)
    return best_name, len(original), len(best)


def main() -> int:
    pngs = sorted(CONTENT.rglob("*.png"))
    if not pngs:
        print(f"no PNGs under {CONTENT}")
        return 1
    before = after = 0
    with tempfile.TemporaryDirectory() as tmp:
        for png in pngs:
            winner, old, new = compress(png, Path(tmp))
            before, after = before + old, after + new
            print(f"{png.relative_to(ROOT)}: {old} -> {new} ({winner})")
    print(f"{len(pngs)} files: {before} -> {after} bytes, {100 * (before - after) / before:.2f}% smaller")
    return 0


if __name__ == "__main__":
    sys.exit(main())
