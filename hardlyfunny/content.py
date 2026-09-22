"""The comic archive as plain Python objects, loaded from content/comics.json."""

from __future__ import annotations

import html
import json
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path


@dataclass(frozen=True)
class Image:
    file: str  # path relative to content/, e.g. "comics/infinite-recursion.png"
    width: int
    height: int
    alt: str


@dataclass(frozen=True)
class Comic:
    number: int
    slug: str
    title: str
    published: date
    images: tuple[Image, ...]
    transcript: tuple[str, ...]
    note_html: str
    tags: tuple[str, ...] = field(default_factory=tuple)

    @property
    def image(self) -> Image:
        return self.images[0]

    @property
    def alt(self) -> str:
        return self.image.alt

    @property
    def note_text(self) -> str:
        """Samantha's note as plain text, for descriptions and feeds."""
        return strip_tags(self.note_html)

    @property
    def summary(self) -> str:
        """One or two sentences that describe this comic (meta description, og:description)."""
        return truncate(self.note_text or self.alt, 160)


@dataclass(frozen=True)
class Site:
    title: str
    tagline: str
    author: str
    url: str
    about_html: str
    comics: tuple[Comic, ...]

    @property
    def latest(self) -> Comic:
        return self.comics[-1]

    def display_title(self, comic: Comic) -> str:
        """The comic's title, plus its number when another comic shares the title."""
        if sum(c.title == comic.title for c in self.comics) > 1:
            return f"{comic.title} (No. {comic.number})"
        return comic.title

    def neighbours(self, comic: Comic) -> tuple[Comic | None, Comic | None]:
        i = comic.number - 1
        prev = self.comics[i - 1] if i > 0 else None
        nxt = self.comics[i + 1] if i + 1 < len(self.comics) else None
        return prev, nxt


def slugify(text: str) -> str:
    """URL slug: lowercase ASCII words joined by hyphens ("Randall’s Idea!" -> "randalls-idea")."""
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    text = re.sub(r"['’]", "", text.lower())
    return re.sub(r"[^a-z0-9]+", "-", text).strip("-")


def strip_tags(markup: str) -> str:
    text = re.sub(r"</p>\s*<p>", " ", markup)
    text = re.sub(r"<[^>]+>", "", text)
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def truncate(text: str, limit: int) -> str:
    """Cut at a sentence or word boundary, never mid-word."""
    if len(text) <= limit:
        return text
    cut = text[:limit]
    sentence = max(cut.rfind(". "), cut.rfind("! "), cut.rfind("? "))
    if sentence > limit * 0.5:
        return cut[: sentence + 1]
    return cut[: cut.rfind(" ")].rstrip(",;:—–- ") + "…"


def load(path: Path) -> Site:
    data = json.loads(path.read_text())
    comics = tuple(
        Comic(
            number=c["number"],
            slug=c["slug"],
            title=c["title"],
            published=date.fromisoformat(c["date"]),
            images=tuple(Image(**img) for img in c["images"]),
            transcript=tuple(c["transcript"]),
            note_html=c["note_html"],
            tags=tuple(c.get("tags", ())),
        )
        for c in data["comics"]
    )
    site = data["site"]
    return Site(
        title=site["title"],
        tagline=site["tagline"],
        author=site["author"],
        url=site["url"].rstrip("/"),
        about_html=site["about_html"],
        comics=comics,
    )
