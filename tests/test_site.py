"""Checks on the built site: SEO tags, accessibility basics, links, and machine-readable files."""

import json
import re
from urllib.parse import urlparse
from xml.etree import ElementTree as ET

import pytest

from hardlyfunny import urls

SITE_URL = "https://hardlyfunny.com"


def html_pages(built):
    return sorted(built.rglob("*.html"))


def test_every_comic_gets_a_clean_permanent_url(built, site):
    for comic in site.comics:
        assert (built / "comics" / comic.slug / "index.html").exists()
    assert not list(built.glob("20[0-9][0-9]")), "no WordPress /yyyy/ directories"


def test_pages_have_one_h1_a_title_and_a_description(built, parse):
    titles = set()
    for path in html_pages(built):
        page = parse(path)
        h1s = [h for h in page.headings if h[0] == "h1"]
        assert len(h1s) == 1, f"{path}: {h1s}"
        assert page.title.strip() and page.title not in titles, path
        titles.add(page.title)
        assert page.meta("description"), path
        assert page.all("html")[0].get("lang") == "en"


@pytest.mark.parametrize("key", [
    "og:title", "og:description", "og:url", "og:image", "og:image:alt", "og:type",
    "twitter:card", "twitter:image",
])
def test_comic_pages_are_ready_for_social_sharing(built, site, parse, key):
    for comic in site.comics:
        page = parse(built / "comics" / comic.slug / "index.html")
        value = page.meta(key)
        assert value, f"{comic.slug} is missing {key}"
        if key in ("og:url", "og:image", "twitter:image"):
            assert value.startswith(SITE_URL + "/"), value
        if key == "og:image":
            assert (built / urlparse(value).path.lstrip("/")).exists(), value


def test_canonical_urls_match_og_urls(built, site, parse):
    for comic in site.comics:
        page = parse(built / "comics" / comic.slug / "index.html")
        canonical = page.all("link", rel="canonical")[0]["href"]
        assert canonical == page.meta("og:url") == f"{SITE_URL}/comics/{comic.slug}/"


def test_structured_data_describes_each_comic(built, site):
    comic = site.comics[69]
    html = (built / "comics" / comic.slug / "index.html").read_text()
    block = re.search(r'<script type="application/ld\+json">(.*?)</script>', html, re.S).group(1)
    data = json.loads(block)
    assert data["@type"] == "ComicStory"
    assert data["name"] == comic.title
    assert data["isPartOf"]["@type"] == "ComicSeries"
    assert data["image"]["caption"] == comic.alt


def test_images_have_alt_text_and_dimensions(built, parse):
    for path in html_pages(built):
        for img in parse(path).all("img"):
            assert "alt" in img, f"{path}: {img.get('src')} has no alt attribute"
            assert img.get("width") and img.get("height"), f"{path}: {img.get('src')}"


def test_comic_images_use_their_descriptions(built, site, parse):
    for comic in site.comics:
        page = parse(built / "comics" / comic.slug / "index.html")
        alts = [i["alt"] for i in page.all("img") if i["src"].startswith("/images/comics/")]
        assert alts[0] == comic.alt


def test_landmarks_and_skip_link(built, parse):
    for path in html_pages(built):
        page = parse(path)
        assert len(page.all("main")) == 1, path
        assert page.all("main")[0].get("id") == "main"
        assert page.all("a", href="#main"), path
        assert page.all("header") and page.all("footer") and page.all("nav"), path


def test_external_links_are_safe_and_announced(built, parse):
    for path in html_pages(built):
        for a in parse(path).all("a"):
            if a.get("target") == "_blank":
                assert "noopener" in a.get("rel", ""), a
                assert "new tab" in a.get("aria-label", ""), a


def test_internal_links_resolve(built, parse):
    for path in html_pages(built):
        for tag, attr in (("a", "href"), ("img", "src"), ("link", "href"), ("script", "src")):
            for el in parse(path).all(tag):
                ref = el.get(attr)
                if not ref or not ref.startswith("/") or ref.startswith("//"):
                    continue
                target = built / urls.output_path(urlparse(ref).path)
                assert target.exists(), f"{path} links to missing {ref}"


def test_nothing_links_to_old_wordpress_urls(built):
    for path in html_pages(built):
        assert not re.search(r'href="(https?://hardlyfunny\.com)?/20\d\d/\d\d/\d\d/', path.read_text()), path


def test_share_links_on_every_comic(built, site, parse):
    page = parse(built / "comics" / site.latest.slug / "index.html")
    hosts = {urlparse(a["href"]).netloc for a in page.all("a") if a.get("target") == "_blank"}
    assert {"x.com", "bsky.app", "www.facebook.com", "www.linkedin.com", "www.reddit.com", "news.ycombinator.com"} <= hosts
    assert [b for b in page.all("button") if "data-share-instagram" in b]


def test_feed_is_linked_and_labelled_feed(built, parse):
    page = parse(built / "index.html")
    alternates = page.all("link", rel="alternate", type="application/atom+xml")
    assert alternates and alternates[0]["href"] == urls.FEED
    assert "RSS" not in (built / "index.html").read_text()
    ET.parse(built / "feed.xml")


def test_sitemap_robots_and_llms_txt(built, site):
    ns = "{http://www.sitemaps.org/schemas/sitemap/0.9}"
    locs = [l.text for l in ET.parse(built / "sitemap.xml").getroot().iter(f"{ns}loc")]
    assert len(locs) == len(site.comics) + 3
    assert f"{SITE_URL}/random/" not in locs
    assert f"Sitemap: {SITE_URL}/sitemap.xml" in (built / "robots.txt").read_text()
    llms = (built / "llms.txt").read_text()
    assert llms.startswith("# Hardly Funny") and llms.count("/comics/") == len(site.comics)
    assert "Transcript:" in (built / "llms-full.txt").read_text()


def test_random_and_404_are_not_indexed(built, parse):
    for name in ("random/index.html", "404.html"):
        page = parse(built / name)
        assert page.meta("robots") == "noindex"
        assert not page.all("link", rel="canonical")


def test_cloudflare_headers_file_is_published(built):
    headers = (built / "_headers").read_text()
    assert "X-Content-Type-Options: nosniff" in headers
    assert "Strict-Transport-Security: max-age=31536000\n" in headers
    assert "/fonts/*" in headers and "immutable" in headers


def header_rules(text):
    """`_headers` as {path: {lower-cased name: value}}, read the way Cloudflare's parser reads it:
    each line trimmed, `#` lines skipped (indented ones too), a line starting with `/` opens a rule.
    Any other line without a colon is one Cloudflare would drop, so it fails here."""
    rules, path = {}, None
    for number, line in enumerate(text.splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("/"):
            path = line
            assert path not in rules, f"line {number}: {path} is listed twice"
            rules[path] = {}
            continue
        name, colon, value = line.partition(":")
        assert path and colon, f"line {number}: Cloudflare would ignore {line!r}"
        rules[path][name.strip().lower()] = value.strip()
    return rules


def test_hsts_is_sent_on_every_path_and_nowhere_else(built):
    # The runtime tests check the header on the wire, but CI skips them; this is the CI check.
    # HSTS belongs on `/*` so pages, 404s and assets all carry it, at the strength WordPress.com
    # used. includeSubDomains or preload would bind subdomains (and, for preload, browsers' lists)
    # in ways that are slow to undo, so either one appearing here must be a deliberate change.
    rules = header_rules((built / "_headers").read_text())
    assert rules["/*"]["strict-transport-security"] == "max-age=31536000"
    assert [p for p, h in rules.items() if "strict-transport-security" in h] == ["/*"]
    # Every other `/*` header survived the comment line added inside that rule.
    assert set(rules["/*"]) == {"x-content-type-options", "referrer-policy", "x-frame-options",
                                "permissions-policy", "strict-transport-security"}


def test_404_page_offers_scribbles_and_comics_to_try(built, site, parse):
    page = parse(built / "404.html")
    dog = [i for i in page.all("img") if i["src"].endswith("scribbles.png") and i.get("alt")]
    assert dog, "Scribbles appears with alt text"
    cards = [li for li in page.all("li") if "data-default-pick" in li or "data-pick" in li]
    defaults = [li for li in cards if "data-default-pick" in li]
    pool = [li for li in cards if "data-pick" in li]
    assert len(defaults) == 3 and not any("hidden" in li for li in defaults)
    assert len(pool) == len(site.comics) and all("hidden" in li for li in pool)
    assert page.all("a", href=urls.RANDOM)
    assert page.meta("robots") == "noindex"


def test_404_defaults_load_eagerly_and_the_hidden_pool_stays_lazy(built, site, parse):
    # site.js only flips loading="eager" on the three pool cards it reveals; that is safe only
    # because the build ships every pool thumbnail lazy (so a 404 doesn't fetch the whole archive)
    # and the no-JS defaults without loading="lazy" (so they render at once).
    page = parse(built / "404.html")
    kind, thumbs = None, {"default": [], "pool": []}
    for tag, attrs in page.elements:
        if tag == "li":
            kind = "default" if "data-default-pick" in attrs else "pool" if "data-pick" in attrs else None
        elif tag == "img" and kind:
            thumbs[kind].append(attrs)
    assert len(thumbs["default"]) == 3 and len(thumbs["pool"]) == len(site.comics)
    assert not [i for i in thumbs["default"] if "loading" in i]
    assert all(i.get("loading") == "lazy" for i in thumbs["pool"])


def test_every_share_link_has_an_icon(built, site):
    html = (built / "comics" / site.latest.slug / "index.html").read_text()
    for host in ("x.com", "bsky.app", "www.facebook.com", "www.linkedin.com"):
        anchor = re.search(rf'<a href="https://{re.escape(host)}/[^>]*>(.*?)</a>', html, re.S).group(1)
        assert "<svg" in anchor and 'aria-hidden="true"' in anchor, host


def test_share_buttons_follow_the_samantha_randall_switch(built, site, parse):
    page = parse(built / "comics" / site.latest.slug / "index.html")
    items = [li for li in page.all("li") if "data-side" in li]
    samantha = [li for li in items if li["data-side"] == "samantha"]
    randall = [li for li in items if li["data-side"] == "randall"]
    assert len(samantha) == 3 and len(randall) == 4  # X, Facebook, Instagram / Bluesky, LinkedIn, Reddit, HN
    assert not [li for li in items if li["data-side"] not in ("samantha", "randall")]
    css = (built / "site.css").read_text()
    assert '[data-side="samantha"] { display: var(--samantha-only); }' in css
    assert '[data-side="randall"] { display: var(--randall-only); }' in css
    # Both Randall theme blocks (OS dark mode and the switch) swap the sets.
    assert css.count("--samantha-only: none; --randall-only: block;") == 2


def test_header_shows_her_banner_and_his_wordmark(built, parse):
    for path in html_pages(built):
        page = parse(path)
        banners = [i for i in page.all("img") if i["src"].endswith("images/brand/banner.png") and "banner" in i.get("class", "")]
        assert len(banners) == 1, path
        assert banners[0]["alt"] == "", "decorative: the brand link's text names it"
        assert banners[0]["width"] == "1000" and banners[0]["height"] == "280"
    # The site name and tagline stay in the page as text in both modes.
    home = (built / "index.html").read_text()
    assert re.search(r'<a class="brand"[^>]*>.*?<h1 class="wordmark"[^>]*>Hardly Funny</h1>.*?class="tagline"', home, re.S)
    css = (built / "site.css").read_text()
    assert ".brand .banner { display: var(--samantha-only);" in css
    assert ".brand .couple { display: var(--randall-only);" in css
    # Randall mode undoes the hidden wordmark for both the switch and the OS dark setting.
    assert '[data-mode="randall"] .brand-text' in css and ':not([data-mode="samantha"]) .brand-text' in css
