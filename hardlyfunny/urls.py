"""Every public URL on the site lives here, so links, feeds and sitemaps agree."""

from __future__ import annotations

from .content import Comic, Image

HOME = "/"
ARCHIVE = "/archive/"
ABOUT = "/about/"
RANDOM = "/random/"
FEED = "/feed/"
SITEMAP = "/sitemap.xml"


def comic(c: Comic) -> str:
    return f"/comics/{c.slug}/"


def comic_image(img: Image) -> str:
    return "/images/" + img.file  # file is "comics/<slug>.png"


def thumbnail(c: Comic) -> str:
    return f"/images/thumbs/{c.slug}.webp"


def social_card(c: Comic | None) -> str:
    return f"/images/social/{c.slug}.jpg" if c else "/images/social/hardly-funny.jpg"


def absolute(site_url: str, path: str) -> str:
    return site_url.rstrip("/") + path


def output_path(path: str) -> str:
    """Where a URL path lives in the build directory ("/about/" -> "about/index.html")."""
    path = path.lstrip("/")
    return path + "index.html" if path == "" or path.endswith("/") else path
