"""Atom 1.0 feed (RFC 4287) at /feed/, newest comic first."""

from __future__ import annotations

from datetime import date, datetime, time, timezone
from xml.etree import ElementTree as ET

from markupsafe import escape

from . import urls
from .content import Comic, Site

ATOM = "http://www.w3.org/2005/Atom"
# Tag URIs (RFC 4151) keep entry IDs stable even if the site moves domains or a preview
# build uses another URL. Never change this, or every reader re-shows every comic.
TAG_AUTHORITY = "hardlyfunny.com,2012"


def _timestamp(d: date) -> str:
    return datetime.combine(d, time(12, 0), tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")


def entry_id(site: Site, comic: Comic) -> str:
    return f"tag:{TAG_AUTHORITY}:comic/{comic.number}"


def entry_html(site: Site, comic: Comic) -> str:
    parts = [
        f'<p><img src="{escape(urls.absolute(site.url, urls.comic_image(img)))}" '
        f'width="{img.width}" height="{img.height}" alt="{escape(img.alt)}"></p>'
        for img in comic.images
    ]
    if comic.note_html:
        parts.append(comic.note_html)
    if comic.transcript:
        lines = "".join(f"<li>{escape(line)}</li>" for line in comic.transcript)
        parts.append(f"<h3>Transcript</h3><ul>{lines}</ul>")
    return "".join(parts)


def render(site: Site) -> str:
    ET.register_namespace("", ATOM)
    q = lambda tag: f"{{{ATOM}}}{tag}"  # noqa: E731
    feed = ET.Element(q("feed"), {"xml:lang": "en"})

    def sub(parent, tag, text=None, **attrs):
        el = ET.SubElement(parent, q(tag), attrs)
        if text is not None:
            el.text = text
        return el

    sub(feed, "id", f"tag:{TAG_AUTHORITY}:feed")
    sub(feed, "title", site.title)
    sub(feed, "subtitle", site.tagline)
    sub(feed, "updated", _timestamp(site.latest.published))
    sub(feed, "link", rel="alternate", type="text/html", href=site.url + "/")
    sub(feed, "link", rel="self", type="application/atom+xml", href=urls.absolute(site.url, urls.FEED))
    author = sub(feed, "author")
    sub(author, "name", site.author)
    sub(feed, "icon", urls.absolute(site.url, "/favicon.png"))

    for comic in reversed(site.comics):
        entry = sub(feed, "entry")
        sub(entry, "id", entry_id(site, comic))
        sub(entry, "title", comic.title)
        sub(entry, "link", rel="alternate", type="text/html", href=urls.absolute(site.url, urls.comic(comic)))
        sub(entry, "published", _timestamp(comic.published))
        sub(entry, "updated", _timestamp(comic.published))
        sub(entry, "summary", comic.alt)
        for tag in comic.tags:
            sub(entry, "category", term=tag)
        sub(entry, "content", entry_html(site, comic), type="html")

    ET.indent(feed)
    return '<?xml version="1.0" encoding="utf-8"?>\n' + ET.tostring(feed, encoding="unicode") + "\n"
