"""Turn content/ into a static site in _site/."""

from __future__ import annotations

import hashlib
import re
import shutil
from dataclasses import dataclass, replace
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape
from markupsafe import Markup

from . import feed, images, seo, share, urls
from .content import Comic, Site, load

ROOT = Path(__file__).resolve().parent.parent
CONTENT = ROOT / "content"
PACKAGE = Path(__file__).resolve().parent
SHARE_NETWORKS = ("x", "facebook", "linkedin", "reddit", "ycombinator", "instagram")


@dataclass(frozen=True)
class Page:
    """Everything the <head> needs to describe one page."""

    path: str
    title: str
    description: str
    og_type: str = "website"
    image: str = urls.social_card(None)
    image_alt: str = "The Hardly Funny banner: Samantha and Randall with a pink pixel heart, and Scribbles the chihuahua."
    jsonld: str | None = None
    noindex: bool = False
    nav: str | None = None  # which site-nav item is current
    published: str | None = None


def _icon(name: str) -> Markup:
    svg = (PACKAGE / "static" / "icons" / f"{name}.svg").read_text()
    svg = re.sub(r"<title>.*?</title>", "", svg)
    svg = svg.replace('role="img"', 'aria-hidden="true" focusable="false" fill="currentColor" width="20" height="20"')
    return Markup(svg)


def _fingerprint(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:10]


def environment(site: Site) -> Environment:
    env = Environment(
        loader=FileSystemLoader(PACKAGE / "templates"),
        autoescape=select_autoescape(["html", "xml"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    static = PACKAGE / "static"
    env.globals.update(
        site=site,
        urls=urls,
        icons={name: _icon(name) for name in SHARE_NETWORKS},
        asset_version={"css": _fingerprint(static / "site.css"), "js": _fingerprint(static / "site.js")},
        absolute=lambda path: urls.absolute(site.url, path),
    )
    env.filters["long_date"] = lambda d: f"{d:%B} {d.day}, {d.year}"
    env.filters["epoch"] = lambda d: str(int(__import__("calendar").timegm(d.timetuple())))
    return env


def comic_page(site: Site, comic: Comic, *, home: bool = False) -> Page:
    if home:
        return Page(
            path=urls.HOME,
            title=f"{site.title}: {site.tagline.lower()}",
            description=f"{site.tagline}. {len(site.comics)} autobiographical comics by {site.author}.",
            image=urls.social_card(comic),
            image_alt=comic.alt,
            jsonld=seo.home_jsonld(site),
            nav="home",
        )
    return Page(
        path=urls.comic(comic),
        title=f"{site.display_title(comic)} · {site.title}",
        description=comic.summary,
        og_type="article",
        image=urls.social_card(comic),
        image_alt=comic.alt,
        jsonld=seo.comic_jsonld(site, comic),
        published=comic.published.isoformat(),
    )


def write(out: Path, path: str, text: str) -> None:
    dest = out / urls.output_path(path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(text)


def build(out: Path, site_url: str | None = None, content: Path = CONTENT) -> Site:
    site = load(content / "comics.json")
    if site_url:
        site = replace(site, url=site_url.rstrip("/"))
    env = environment(site)

    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)

    comic_tpl = env.get_template("comic.html")
    for comic in site.comics:
        prev, nxt = site.neighbours(comic)
        page = comic_page(site, comic)
        links = share.links(urls.absolute(site.url, page.path), comic.title, site.title)
        write(out, page.path, comic_tpl.render(page=page, comic=comic, prev=prev, next=nxt, share_links=links, home=False))

    latest = site.latest
    prev, _ = site.neighbours(latest)
    home = comic_page(site, latest, home=True)
    links = share.links(urls.absolute(site.url, urls.comic(latest)), latest.title, site.title)
    write(out, urls.HOME, comic_tpl.render(page=home, comic=latest, prev=prev, next=None, share_links=links, home=True))

    write(out, urls.ARCHIVE, env.get_template("archive.html").render(page=Page(
        path=urls.ARCHIVE, title=f"Archive · {site.title}", nav="archive",
        description=f"All {len(site.comics)} Hardly Funny comics, {site.comics[0].published:%B %Y} to {latest.published:%B %Y}.")))
    write(out, urls.ABOUT, env.get_template("about.html").render(page=Page(
        path=urls.ABOUT, title=f"About · {site.title}", nav="about",
        description="Hardly Funny is an autobiographical webcomic by Samantha Degges about life with Randall, a programmer, and their chihuahua Scribbles.")))
    write(out, urls.RANDOM, env.get_template("random.html").render(page=Page(
        path=urls.RANDOM, title=f"Random comic · {site.title}", description="Opens a random Hardly Funny comic.", noindex=True)))
    write(out, "/404.html", env.get_template("404.html").render(page=Page(
        path="/404.html", title=f"Page not found · {site.title}", description="This page doesn't exist.", noindex=True)))

    write(out, urls.FEED, feed.render(site))
    write(out, urls.SITEMAP, seo.sitemap(site))
    write(out, "/robots.txt", seo.robots(site))
    write(out, "/llms.txt", seo.llms_txt(site))
    write(out, "/llms-full.txt", seo.llms_txt(site, full=True))

    shutil.copy2(PACKAGE / "static" / "site.css", out / "site.css")
    shutil.copy2(PACKAGE / "static" / "site.js", out / "site.js")
    shutil.copytree(content / "brand", out / "images" / "brand")
    images.copy_originals(site.comics, content, out)
    images.favicons(content, out)
    images.social_card(None, content, out / urls.social_card(None).lstrip("/"))
    for comic in site.comics:
        images.thumbnail(comic, content, out / urls.thumbnail(comic).lstrip("/"))
        images.social_card(comic, content, out / urls.social_card(comic).lstrip("/"))
    return site
