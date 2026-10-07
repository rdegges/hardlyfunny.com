#!/usr/bin/env python3
"""Export every Hardly Funny comic out of WordPress.com into a portable archive.

Historical: the WordPress.com site was deleted on 2026-10-06, so the API below no
longer returns it and this script can't run again. It's kept to show how archive/
was made.

Pulls posts from the public WordPress.com REST API, downloads the original
comic images, and writes:

    archive/comics.json   canonical, human-readable manifest (source of truth)
    archive/comics.js     the same data as `window.HARDLY_FUNNY = {...}` so the
                          static design mockups work straight from file://
    archive/comics/*.png  original artwork, renamed NNN-slug.ext

Stdlib only. Re-running is safe: images that already exist are skipped.

    python3 scripts/export_wordpress.py
"""

from __future__ import annotations

import html
import json
import re
import struct
import sys
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

SITE = "hardlyfunny.com"
API = f"https://public-api.wordpress.com/rest/v1.1/sites/{SITE}/posts"
ROOT = Path(__file__).resolve().parent.parent
ARCHIVE = ROOT / "archive"
IMAGES = ARCHIVE / "comics"

# Known data quirks in the WordPress export, fixed here rather than by hand.
TITLE_FIXES = {"404": "404"}  # 2013-02-04 post has an empty title; its slug is the joke.
# Corrections to her About page text (applied after sanitising).
ABOUT_FIXES = {"Scribbles(2005-2014)": "Scribbles (2003–2014)"}
DATE_FLAGS = {
    "engineers": (
        "Dated 2012-01-02 in WordPress, but the image was uploaded in 2012/12 "
        "it's drawn on the 600x600 canvas she used from Dec 2012, and the 2012-08-26 "
        "post is tagged 'the first comic'. Probably 2013-01-02."
    ),
}


def fetch_json(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=30) as resp:
        return json.load(resp)


def fetch_posts() -> list[dict]:
    fields = "ID,date,title,slug,URL,content,tags"
    posts: list[dict] = []
    page = 1
    while True:
        data = fetch_json(f"{API}?number=100&page={page}&fields={fields}")
        posts.extend(data["posts"])
        if len(posts) >= data["found"] or not data["posts"]:
            return posts
        page += 1


class NoteSanitizer(HTMLParser):
    """Keep the author's note as tiny, safe HTML: paragraphs, links, emphasis."""

    ALLOWED = {"p", "a", "em", "strong", "br"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.out: list[str] = []
        self.in_img_link = 0

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "a" and re.search(r"\.(png|jpe?g|gif)(\?|$)", attrs.get("href", "")):
            self.in_img_link += 1  # the wrapper link around the comic image
            return
        if tag in self.ALLOWED:
            if tag == "a":
                href = html.escape(attrs.get("href", ""), quote=True)
                self.out.append(f'<a href="{href}">')
            else:
                self.out.append(f"<{tag}>")

    def handle_endtag(self, tag):
        if tag == "a" and self.in_img_link:
            self.in_img_link -= 1
            return
        if tag in self.ALLOWED and tag != "br":
            self.out.append(f"</{tag}>")

    def handle_data(self, data):
        if not self.in_img_link:
            self.out.append(html.escape(data, quote=False))


def clean_note(content: str) -> str:
    parser = NoteSanitizer()
    parser.feed(content)
    note = "".join(parser.out)
    note = re.sub(r"\s*&nbsp;\s*|\u00a0", " ", note)
    note = re.sub(r"<p>\s*</p>", "", note)
    note = re.sub(r"[ \t]+", " ", note).strip()
    return note


def comic_images(content: str) -> list[dict]:
    images = []
    for tag in re.findall(r"<img[^>]+>", content):
        src = re.search(r'data-orig-file="([^"]+)"', tag) or re.search(r'src="([^"?]+)', tag)
        if src:
            images.append({"url": src.group(1)})
    return images


def image_size(path: Path) -> tuple[int, int]:
    """Read width/height from a PNG or JPEG header (stdlib only)."""
    data = path.read_bytes()
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return struct.unpack(">II", data[16:24])
    i = 2  # JPEG: walk segments until a start-of-frame marker
    while i < len(data):
        marker, length = data[i + 1], struct.unpack(">H", data[i + 2:i + 4])[0]
        if 0xC0 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC):
            height, width = struct.unpack(">HH", data[i + 5:i + 9])
            return width, height
        i += 2 + length
    raise ValueError(f"Unrecognised image format: {path}")


def era_for(width: int) -> str:
    """The art style shifts are visible in the canvas size she drew on."""
    if width > 600:
        return "early"  # Aug-Dec 2012: larger, freer canvases on white
    if width == 600:
        return "square"  # Dec 2012 - Mar 2013: 600x600 squares
    return "panels"  # Mar 2013 on: 500x500 with pastel pink/green panels


def download(url: str, dest: Path) -> None:
    if dest.exists():
        return
    with urllib.request.urlopen(url, timeout=60) as resp:
        dest.write_bytes(resp.read())


def build() -> list[dict]:
    IMAGES.mkdir(parents=True, exist_ok=True)
    posts = sorted(fetch_posts(), key=lambda p: p["date"])
    comics = []
    for number, post in enumerate(posts, start=1):
        slug = post["slug"]
        title = html.unescape(post["title"]).strip() or TITLE_FIXES.get(slug, slug)
        images = []
        for i, img in enumerate(comic_images(post["content"])):
            ext = Path(img["url"]).suffix.lower()
            suffix = f"-{i + 1}" if i else ""
            name = f"{number:03d}-{slug}{suffix}{ext}"
            download(img["url"], IMAGES / name)
            width, height = image_size(IMAGES / name)
            images.append({"src": f"comics/{name}", "width": width, "height": height})
        comic = {
            "number": number,
            "slug": slug,
            "title": title,
            "date": post["date"][:10],
            "images": images,
            "note_html": clean_note(post["content"]),
            "tags": sorted(post["tags"].keys(), key=str.lower),
            "era": era_for(images[0]["width"]) if images else None,
            "wordpress_url": post["URL"].replace("http://", "https://"),
        }
        if slug in DATE_FLAGS:
            comic["date_flag"] = DATE_FLAGS[slug]
        comics.append(comic)
    return comics


def fetch_about() -> str:
    """Her About page, kept as the same tiny safe HTML as the comic notes."""
    data = fetch_json(f"{API}?type=page&number=20&fields=slug,content")
    page = next(p for p in data["posts"] if p["slug"] == "about")
    about = clean_note(page["content"])
    for wrong, right in ABOUT_FIXES.items():
        about = about.replace(wrong, right)
    return about


def main() -> int:
    comics = build()
    manifest = {
        "site": "Hardly Funny",
        "tagline": "A webcomic about being married to a computer programmer",
        "author": "Samantha Degges",
        "source": f"https://{SITE}",
        "about_html": fetch_about(),
        "comics": comics,
    }
    (ARCHIVE / "comics.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
    (ARCHIVE / "comics.js").write_text(
        "// Generated by scripts/export_wordpress.py. Do not edit by hand.\n"
        f"window.HARDLY_FUNNY = {json.dumps(manifest, ensure_ascii=False)};\n"
    )
    print(f"Exported {len(comics)} comics to {ARCHIVE.relative_to(ROOT)}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
