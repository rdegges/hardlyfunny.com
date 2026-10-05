"""The comic archive as plain Python objects, loaded from content/comics.json."""

from __future__ import annotations

import html
import json
import re
import unicodedata
from dataclasses import dataclass
from datetime import date
from pathlib import Path

# Shorter notes are asides ("We love dinosaurs…") that don't say what the comic shows.
MIN_NOTE_DESCRIPTION = 80

# Slugs and image file names go into URLs unescaped, so both must already be URL-safe.
SAFE_NAME = r"[a-z0-9]+(-[a-z0-9]+)*"

# A topic page with one or two comics is a thin page that search engines treat as low quality.
MIN_TOPIC_COMICS = 3


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
    topics: tuple[str, ...]  # Topic slugs

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
class Topic:
    slug: str
    title: str
    intro_html: str

    @property
    def intro_text(self) -> str:
        return strip_tags(self.intro_html)


@dataclass(frozen=True)
class Person:
    name: str
    url: str


@dataclass(frozen=True)
class License:
    credit: str  # creditText on every comic image
    contact: str  # permission requests; shown only in HTML, never in JSON-LD


@dataclass(frozen=True)
class Site:
    title: str
    tagline: str
    author: str
    randall: Person
    url: str
    license: License
    about_html: str
    comics: tuple[Comic, ...]
    topics: tuple[Topic, ...]

    @property
    def latest(self) -> Comic:
        return self.comics[-1]

    @property
    def copyright(self) -> str:
        """The copyright line, with years from the comics so it can't drift from the archive."""
        return f"© {self.comics[0].published.year}–{self.latest.published.year} {self.author}. All rights reserved."

    def description(self, comic: Comic) -> str:
        """Meta description: the first of these that no earlier comic already uses (No. 82 redraws No. 20):
        the note if it has at least MIN_NOTE_DESCRIPTION characters, then the alt text, then the short note."""
        taken: set[str] = set()
        # One pass in number order: each pick depends on the picks before it, and recursing would redo them exponentially.
        for c in [*(c for c in self.comics if c.number < comic.number), comic]:
            candidates = [c.summary] if len(c.summary) >= MIN_NOTE_DESCRIPTION else []
            pick = next((d for d in [*candidates, truncate(c.alt, 160), c.summary] if d not in taken), None)
            if pick is None:
                raise ValueError(f"No. {c.number} has no description that an earlier comic isn't already using.")
            taken.add(pick)
        return pick

    def display_title(self, comic: Comic) -> str:
        """The comic's title, plus its number when another comic shares the title."""
        if sum(c.title == comic.title for c in self.comics) > 1:
            return f"{comic.title} (No. {comic.number})"
        return comic.title

    def topics_of(self, comic: Comic) -> list[Topic]:
        return [t for slug in comic.topics for t in self.topics if t.slug == slug]

    def comics_about(self, topic: Topic) -> list[Comic]:
        """The topic's comics, newest first."""
        return [c for c in reversed(self.comics) if topic.slug in c.topics]

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


class ContentError(ValueError):
    """content/comics.json is inconsistent; the message says what to fix."""


def validate(comics: tuple[Comic, ...], topics: tuple[Topic, ...]) -> None:
    """Catch hand-editing mistakes before they become broken navigation."""
    topic_slugs: set[str] = set()
    for t in topics:
        if not re.fullmatch(SAFE_NAME, t.slug):
            raise ContentError(f"Topic slug “{t.slug}” must be lowercase letters, digits and hyphens.")
        if t.slug in topic_slugs:
            raise ContentError(f"Topic slug “{t.slug}” is used twice. Every topic needs its own.")
        if not t.title.strip():
            raise ContentError(f"Topic “{t.slug}” needs a title.")
        if not strip_tags(t.intro_html).strip():
            raise ContentError(f"Topic “{t.slug}” needs an intro.")
        topic_slugs.add(t.slug)
    seen: set[str] = set()
    for i, c in enumerate(comics):
        if c.number != i + 1:
            raise ContentError(f"Comic “{c.title}” is number {c.number}, but it's entry {i + 1}. Numbers must run 1, 2, 3… in order.")
        if i and c.published < comics[i - 1].published:
            raise ContentError(f"No. {c.number} ({c.published}) is dated before No. {c.number - 1}. Keep comics in date order.")
        if c.slug in seen:
            raise ContentError(f"Slug “{c.slug}” is used twice. Every comic needs its own.")
        seen.add(c.slug)
        if not re.fullmatch(SAFE_NAME, c.slug):
            raise ContentError(f"Slug “{c.slug}” must be lowercase letters, digits and hyphens.")
        for img in c.images:
            if not re.fullmatch(rf"comics/{SAFE_NAME}\.(png|jpg)", img.file):
                raise ContentError(f"No. {c.number} image “{img.file}” must be comics/ then lowercase letters, digits and hyphens, ending .png or .jpg.")
        if not c.images or any(not img.alt.strip() for img in c.images):
            raise ContentError(f"No. {c.number} needs at least one image, and every image needs alt text.")
        if not c.topics:
            raise ContentError(f"No. {c.number} has no topics. Give it at least one slug from the topics list.")
        if len(set(c.topics)) != len(c.topics):
            repeated = next(s for s in c.topics if c.topics.count(s) > 1)
            raise ContentError(f"No. {c.number} lists topic “{repeated}” twice. List each topic once.")
        for slug in c.topics:
            if slug not in topic_slugs:
                raise ContentError(f"No. {c.number} has topic “{slug}”, which isn't in the topics list.")
    for t in topics:
        count = sum(t.slug in c.topics for c in comics)
        if count < MIN_TOPIC_COMICS:
            raise ContentError(f"Topic “{t.slug}” has {count} comics. Every topic needs at least {MIN_TOPIC_COMICS}.")


def load(path: Path) -> Site:
    data = json.loads(path.read_text(encoding="utf-8"))
    comics = tuple(
        Comic(
            number=c["number"],
            slug=c["slug"],
            title=c["title"],
            published=date.fromisoformat(c["date"]),
            images=tuple(Image(**img) for img in c["images"]),
            transcript=tuple(c["transcript"]),
            note_html=c["note_html"],
            topics=tuple(c.get("topics", ())),
        )
        for c in data["comics"]
    )
    topics = tuple(Topic(**t) for t in data.get("topics", ()))
    validate(comics, topics)
    site = data["site"]
    return Site(
        title=site["title"],
        tagline=site["tagline"],
        author=site["author"],
        randall=Person(**site["randall"]),
        url=site["url"].rstrip("/"),
        license=License(**site["license"]),
        about_html=site["about_html"],
        comics=comics,
        topics=topics,
    )
