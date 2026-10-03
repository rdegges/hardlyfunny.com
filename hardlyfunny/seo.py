"""Machine-readable descriptions of the site: JSON-LD, sitemap, robots.txt, llms.txt."""

from __future__ import annotations

import json
from xml.sax.saxutils import escape as xml_escape

from . import urls
from .content import Comic, Site


def _series(site: Site) -> dict:
    return {
        "@type": "ComicSeries",
        "@id": site.url + "/#series",
        "name": site.title,
        "description": site.tagline,
        "url": site.url + "/",
        "author": {"@type": "Person", "name": site.author},
        "startDate": site.comics[0].published.isoformat(),
        "endDate": site.latest.published.isoformat(),
        "inLanguage": "en",
    }


def comic_jsonld(site: Site, comic: Comic) -> str:
    img = comic.image
    data = {
        "@context": "https://schema.org",
        "@type": "ComicStory",
        "name": comic.title,
        "url": urls.absolute(site.url, urls.comic(comic)),
        "position": comic.number,
        "datePublished": comic.published.isoformat(),
        "author": {"@type": "Person", "name": site.author},
        "artist": {"@type": "Person", "name": site.author},
        "description": comic.summary,
        "image": {
            "@type": "ImageObject",
            "contentUrl": urls.absolute(site.url, urls.comic_image(img)),
            "width": img.width,
            "height": img.height,
            "caption": img.alt,
        },
        "isPartOf": _series(site),
        "inLanguage": "en",
    }
    if comic.tags:
        data["keywords"] = ", ".join(comic.tags)
    if comic.transcript:
        data["text"] = "\n".join(comic.transcript)
    return _dump(data)


def home_jsonld(site: Site) -> str:
    return _dump({
        "@context": "https://schema.org",
        "@graph": [
            {"@type": "WebSite", "@id": site.url + "/#website", "name": site.title,
             "url": site.url + "/", "description": site.tagline, "inLanguage": "en"},
            _series(site),
        ],
    })


def _dump(data: dict) -> str:
    # Inside <script>, "</script" or "<!--" in the data could end or swallow the element,
    # so escape every <, > and & as JSON unicode escapes.
    text = json.dumps(data, ensure_ascii=False, indent=2)
    return text.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")


def sitemap(site: Site) -> str:
    rows = [(urls.HOME, site.latest.published), (urls.ARCHIVE, site.latest.published), (urls.ABOUT, None)]
    rows += [(urls.comic(c), c.published) for c in site.comics]
    body = "".join(
        f"  <url><loc>{xml_escape(urls.absolute(site.url, path))}</loc>"
        + (f"<lastmod>{when.isoformat()}</lastmod>" if when else "")
        + "</url>\n"
        for path, when in rows
    )
    return ('<?xml version="1.0" encoding="utf-8"?>\n'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' + body + "</urlset>\n")


def robots(site: Site) -> str:
    return f"User-agent: *\nDisallow: {urls.RANDOM}\n\nSitemap: {urls.absolute(site.url, urls.SITEMAP)}\n"


def llms_txt(site: Site, full: bool = False) -> str:
    """llms.txt (llmstxt.org): a plain-text map of the site for AI assistants and answer engines.

    The full variant adds every transcript and note, so the comics can be quoted accurately.
    """
    from .content import strip_tags

    lines = [
        f"# {site.title}",
        "",
        f"> {site.tagline}. An autobiographical webcomic drawn by {site.author}, "
        f"{len(site.comics)} comics published {site.comics[0].published:%B %Y} to {site.latest.published:%B %Y}.",
        "",
        strip_tags(site.about_html),
        "",
        "## Pages",
        "",
        f"- [Archive]({urls.absolute(site.url, urls.ARCHIVE)}): every comic, newest first",
        f"- [About]({urls.absolute(site.url, urls.ABOUT)}): who Samantha, Randall and Scribbles are",
        f"- [Atom feed]({urls.absolute(site.url, urls.FEED)})",
        "",
        "## Comics",
        "",
    ]
    for c in site.comics:
        lines.append(f"- [#{c.number}: {c.title}]({urls.absolute(site.url, urls.comic(c))}) "
                     f"({c.published.isoformat()}): {c.alt}")
        if full:
            if c.transcript:
                lines += ["", "  Transcript:", *[f"  {t}" for t in c.transcript]]
            if c.note_text:
                lines += ["", f"  Samantha's note: {c.note_text}"]
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"
