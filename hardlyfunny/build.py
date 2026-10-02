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
    og_title: str | None = None  # title for social cards, without the " · Hardly Funny" suffix
    published: str | None = None


def _icon(name: str) -> Markup:
    svg = (PACKAGE / "static" / "icons" / f"{name}.svg").read_text(encoding="utf-8")
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
        og_title=site.display_title(comic),
        description=site.description(comic),
        og_type="article",
        image=urls.social_card(comic),
        image_alt=comic.alt,
        jsonld=seo.comic_jsonld(site, comic),
        published=comic.published.isoformat(),
    )


# Root-relative references in src/href/data-image attributes, e.g. href="/archive/".
ROOT_RELATIVE = re.compile(r'(\b(?:href|src|data-image)=")/(?!/)([^"#?]*)')


def make_portable(out: Path) -> None:
    """Rewrite root-relative links as relative ones with explicit index.html, so the
    built site works opened from disk or hosted under any path. Canonical and OG URLs
    stay absolute."""
    for page in out.rglob("*.html"):
        prefix = "../" * (len(page.relative_to(out).parts) - 1)

        def rel(m: re.Match) -> str:
            path = m.group(2)
            if path == "" or path.endswith("/"):
                path += "index.html"
            return f"{m.group(1)}{prefix}{path}"

        page.write_text(ROOT_RELATIVE.sub(rel, page.read_text(encoding="utf-8")), encoding="utf-8")


MARKER = ".hardlyfunny-build"


def _clear(out: Path) -> None:
    """Empty the output directory, refusing anything that isn't a previous build."""
    out = out.resolve()
    if out.exists():
        if out == ROOT or out in ROOT.parents or (out / ".git").exists() or (out / "comics.json").exists():
            raise SystemExit(f"Refusing to delete {out}: that's not a build directory.")
        earlier_build = all((out / f).exists() for f in ("index.html", "site.css", "feed.xml"))
        if any(out.iterdir()) and not ((out / MARKER).exists() or earlier_build):
            raise SystemExit(f"Refusing to delete {out}: it isn't empty and wasn't made by this build.")
        shutil.rmtree(out)
    out.mkdir(parents=True)
    (out / MARKER).write_text("Built by python -m hardlyfunny. Safe to delete.\n", encoding="utf-8")


def write(out: Path, path: str, text: str) -> None:
    dest = out / urls.output_path(path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(text, encoding="utf-8")


def build(out: Path, site_url: str | None = None, content: Path = CONTENT, portable: bool = False) -> Site:
    """Build the site into out/. portable=True makes a preview that runs from disk: relative
    links, and no generated thumbnails or social cards (the archive shows the originals)."""
    site = load(content / "comics.json")
    if site_url:
        site = replace(site, url=site_url.rstrip("/"))
    env = environment(site)
    env.globals["thumbnail"] = (lambda c: urls.comic_image(c.image)) if portable else urls.thumbnail

    _clear(out)

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
    shutil.copytree(PACKAGE / "static" / "fonts", out / "fonts")
    shutil.copytree(content / "brand", out / "images" / "brand")
    images.copy_originals(site.comics, content, out)
    images.favicons(content, out)
    if portable:
        make_portable(out)
        return site
    images.social_card(None, content, out / urls.social_card(None).lstrip("/"))
    for comic in site.comics:
        images.thumbnail(comic, content, out / urls.thumbnail(comic).lstrip("/"))
        images.social_card(comic, content, out / urls.social_card(comic).lstrip("/"))
    return site
