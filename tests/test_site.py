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
    assert {"x.com", "www.facebook.com", "www.linkedin.com", "www.reddit.com", "news.ycombinator.com"} <= hosts
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
    assert "/fonts/*" in headers and "immutable" in headers


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
