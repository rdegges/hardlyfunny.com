"""Machine-readable descriptions of the site: JSON-LD, sitemap, robots.txt, llms.txt."""

from __future__ import annotations

import json
from xml.sax.saxutils import escape as xml_escape

from . import urls
from .content import Comic, Site

# Content Signals (contentsignals.org) say what crawlers may do with a page after fetching it.
# The comic wants to be found, quoted and remembered, so all three are yes.
CONTENT_SIGNALS = "search=yes, ai-input=yes, ai-train=yes"


def _samantha_id(site: Site) -> str:
    return urls.absolute(site.url, urls.ABOUT) + "#samantha"


def _people(site: Site) -> list[dict]:
    """Samantha and Randall. Every page that references them by @id includes these nodes."""
    about = urls.absolute(site.url, urls.ABOUT)
    # Samantha has no public social media: her node must never get sameAs or an off-site url.
    samantha = {"@type": "Person", "@id": _samantha_id(site), "name": site.author, "url": about}
    randall = {"@type": "Person", "@id": about + "#randall", "name": site.randall.name, "url": site.randall.url}
    return [samantha, randall]


def _series(site: Site) -> dict:
    return {
        "@type": "ComicSeries",
        "@id": site.url + "/#series",
        "name": site.title,
        "description": site.tagline,
        "url": site.url + "/",
        "author": {"@id": _samantha_id(site)},
        "character": [{"@id": p["@id"]} for p in _people(site)],
        "startDate": site.comics[0].published.isoformat(),
        "endDate": site.latest.published.isoformat(),
        "inLanguage": "en",
    }


def comic_jsonld(site: Site, comic: Comic) -> str:
    page = urls.absolute(site.url, urls.comic(comic))
    author = {"@id": _samantha_id(site)}
    story = {
        "@type": "ComicStory",
        "@id": page + "#comic",
        "name": comic.title,
        "url": page,
        "position": comic.number,
        "datePublished": comic.published.isoformat(),
        "author": author,
        "artist": author,
        "publisher": author,
        "description": site.description(comic),
        "image": [
            {
                "@type": "ImageObject",
                "contentUrl": urls.absolute(site.url, urls.comic_image(img)),
                "width": img.width,
                "height": img.height,
                "caption": img.alt,
            }
            for img in comic.images
        ],
        "isPartOf": _series(site),
        "inLanguage": "en",
    }
    if comic.tags:
        story["keywords"] = ", ".join(comic.tags)
    if comic.transcript:
        story["text"] = "\n".join(comic.transcript)
    crumbs = [("Home", urls.HOME), ("Archive", urls.ARCHIVE), (site.display_title(comic), urls.comic(comic))]
    breadcrumbs = {
        "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": i, "name": name, "item": urls.absolute(site.url, path)}
            for i, (name, path) in enumerate(crumbs, 1)
        ],
    }
    return _dump({"@context": "https://schema.org", "@graph": [story, breadcrumbs, *_people(site)]})


def home_jsonld(site: Site) -> str:
    return _dump({
        "@context": "https://schema.org",
        "@graph": [
            {"@type": "WebSite", "@id": site.url + "/#website", "name": site.title,
             "url": site.url + "/", "description": site.tagline, "inLanguage": "en"},
            _series(site),
            *_people(site),
        ],
    })


def about_jsonld(site: Site) -> str:
    page = urls.absolute(site.url, urls.ABOUT)
    return _dump({
        "@context": "https://schema.org",
        "@graph": [
            {"@type": "AboutPage", "@id": page, "name": f"About {site.title}", "url": page,
             "about": {"@id": site.url + "/#series"}, "inLanguage": "en"},
            _series(site),
            *_people(site),
        ],
    })


def _dump(data: dict) -> str:
    # Inside <script>, "</script" or "<!--" in the data could end or swallow the element,
    # so escape every <, > and & as JSON unicode escapes.
    text = json.dumps(data, ensure_ascii=False, indent=2)
    return text.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")


def sitemap(site: Site) -> str:
    # Image entries go on comic pages only, so each image is listed once, under its permalink.
    rows = [(urls.HOME, site.latest.published, ()), (urls.ARCHIVE, site.latest.published, ()), (urls.ABOUT, None, ())]
    rows += [(urls.comic(c), c.published, c.images) for c in site.comics]
    body = "".join(
        f"  <url><loc>{xml_escape(urls.absolute(site.url, path))}</loc>"
        + (f"<lastmod>{when.isoformat()}</lastmod>" if when else "")
        + "".join(f"<image:image><image:loc>{xml_escape(urls.absolute(site.url, urls.comic_image(img)))}"
                  "</image:loc></image:image>" for img in images)
        + "</url>\n"
        for path, when, images in rows
    )
    return ('<?xml version="1.0" encoding="utf-8"?>\n'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"'
            ' xmlns:image="http://www.google.com/schemas/sitemap-image/1.1">\n' + body + "</urlset>\n")


def robots(site: Site) -> str:
    # No Disallow for /random/: a crawler blocked from it can't read its noindex tag.
    return (f"User-agent: *\nContent-Signal: {CONTENT_SIGNALS}\nAllow: /\n\n"
            f"Sitemap: {urls.absolute(site.url, urls.SITEMAP)}\n")


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
        f"{site.title} ran from {site.comics[0].published:%B %Y} to {site.latest.published:%B %Y} and is complete. "
        f"All {len(site.comics)} comics are listed below; no new comics are planned.",
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
