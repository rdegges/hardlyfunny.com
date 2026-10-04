"""Permanent redirects from the old WordPress.com URLs, as a Cloudflare `_redirects` file.

Old links keep working, but every visitor and search engine is sent (301) to the
clean URL, so the WordPress date-style paths are retired rather than preserved.

Cloudflare limits: 2,000 static + 100 dynamic (splat) rules, and `/path` and `/path/`
are different paths, so both are listed.
https://developers.cloudflare.com/workers/static-assets/redirects/

No two dynamic rules may overlap. Cloudflare's edge does not apply overlapping splats in
file order (`/2012/*` beat the earlier `/2012/01/02/engineers/*` in production, while
`cf dev` honored the order), so order can't be relied on. An exact rule does win over a
splat, so every date archive WordPress served is listed exactly instead of a year
catch-all, and a path WordPress never served gets the 404 page.
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from . import urls
from .content import Site

MAX_STATIC = 2000
MAX_DYNAMIC = 100


@dataclass(frozen=True)
class Redirect:
    source: str
    destination: str
    status: int = 301

    @property
    def dynamic(self) -> bool:
        return "*" in self.source or ":" in self.source

    def line(self) -> str:
        return f"{self.source} {self.destination} {self.status}"


def _both(path: str, dest: str) -> list[Redirect]:
    """`/a/b/` and `/a/b`: Cloudflare matches them separately."""
    path = path.rstrip("/")
    return [Redirect(path + "/", dest), Redirect(path, dest)]


def _spellings(period: str) -> list[str]:
    """WordPress also accepted months and days without the leading zero (`/2012/1/2/`)."""
    y, *rest = period.split("/")
    out = [y]
    for part in rest:
        out = [f"{o}/{v}" for o in out for v in dict.fromkeys((part, part.lstrip("0")))]
    return out


def _date_archives(posts: list[str]) -> list[Redirect]:
    """Year, month and day listings, their pages and their feeds, for every date that had a post.

    Pages go up to one per post: the old posts-per-page setting isn't known, and spare rules are free.
    Unpadded spellings only get the listing itself, and feed formats only the slashed form WordPress
    linked to, to stay under Cloudflare's 2,000 static rules.
    """
    periods = Counter()
    for post in posts:
        y, m, d = post.strip("/").split("/")[:3]
        periods.update([y, f"{y}/{m}", f"{y}/{m}/{d}"])
    out: list[Redirect] = []
    for period, count in sorted(periods.items()):
        for spelling in _spellings(period):
            out += _both(f"/{spelling}", urls.ARCHIVE)
        out += _both(f"/{period}/feed", urls.FEED)
        out += [Redirect(f"/{period}/feed/{fmt}/", urls.FEED) for fmt in ("atom", "rss2")]
        for n in range(1, count + 1):
            out += _both(f"/{period}/page/{n}", urls.ARCHIVE)
    return out


def build(site: Site, wordpress_urls: Path) -> list[Redirect]:
    old = json.loads(wordpress_urls.read_text(encoding="utf-8"))["comics"]
    by_number = {c.number: c for c in site.comics}
    static: list[Redirect] = []
    dynamic: list[Redirect] = []

    for entry in old:
        comic = by_number[entry["number"]]
        page = urls.comic(comic)
        static += _both(entry["post"], page)
        # WordPress also served an "attachment page" per image under the post URL.
        dynamic.append(Redirect(entry["post"].rstrip("/") + "/*", page))
        # Hotlinked originals (Reddit, forums, old blog posts) go to the same image here.
        for upload, img in zip(entry["uploads"], comic.images):
            static.append(Redirect(upload, urls.comic_image(img)))

    static += [
        Redirect("/wp-content/uploads/2014/01/2011_theme_bannerpng241.png", "/images/brand/banner.png"),
        *_both("/feed/atom", urls.FEED),
        *_both("/feed/rss2", urls.FEED),
        *_both("/comments/feed", urls.FEED),
        *_both("/feed/rss", urls.FEED),
        *_both("/feed/rdf", urls.FEED),
        *_both("/comments/feed/atom", urls.FEED),
        *_both("/comments/feed/rss2", urls.FEED),
        *_both("/category/posts", urls.ARCHIVE),
        *_both("/author/samanthadegges", urls.ABOUT),
        # Found in the Wayback Machine's captures of the old site, not in the export.
        *_both("/author/samanthadegges/feed", urls.FEED),
        *_both("/about/feed", urls.FEED),
        Redirect("/atom.xml", urls.FEED),
        # The feed lived at /feed.xml from the move off WordPress until it took back /feed/.
        Redirect("/feed.xml", urls.FEED),
        Redirect("/news-sitemap.xml", urls.SITEMAP),
        Redirect("/favicon.ico", "/favicon.png"),
    ]
    static += _date_archives([entry["post"] for entry in old])
    dynamic += [
        Redirect(f"/{prefix}/*", urls.ARCHIVE)
        for prefix in ("tag", "category", "page", "type", "author/samanthadegges/page")
    ]
    return static + dynamic


def _check_dynamic(redirects: list[Redirect]) -> None:
    """Refuse dynamic rules whose result would depend on the edge's (unreliable) ordering."""
    prefixes = []
    for r in redirects:
        if not r.dynamic:
            continue
        if ":" in r.source or not r.source.endswith("/*") or "*" in r.source[:-1]:
            raise ValueError(f"{r.source}: only a trailing /* splat can be checked for overlaps")
        prefixes.append(r.source[:-1])
    prefixes.sort()
    for a, b in zip(prefixes, prefixes[1:]):
        if b.startswith(a):
            raise ValueError(f"{a}* overlaps {b}*: Cloudflare doesn't apply overlapping splats in file order")


def render(redirects: list[Redirect]) -> str:
    _check_dynamic(redirects)
    static = sum(not r.dynamic for r in redirects)
    dynamic = len(redirects) - static
    if static > MAX_STATIC or dynamic > MAX_DYNAMIC:
        raise ValueError(f"{static} static / {dynamic} dynamic redirects exceeds Cloudflare's {MAX_STATIC}/{MAX_DYNAMIC} limit")
    header = (
        "# Generated by `python -m hardlyfunny build` from archive/wordpress_urls.json. Don't edit.\n"
        f"# {static} static + {dynamic} dynamic rules (Cloudflare allows {MAX_STATIC} + {MAX_DYNAMIC}).\n"
    )
    return header + "\n".join(r.line() for r in redirects) + "\n"
