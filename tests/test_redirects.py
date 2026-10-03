"""The WordPress → new-site redirects, checked the way Cloudflare applies them."""

import json
import re

import pytest

from hardlyfunny import urls
from hardlyfunny.build import ROOT

OLD = json.loads((ROOT / "archive" / "wordpress_urls.json").read_text(encoding="utf-8"))["comics"]


def rules(built):
    lines = [l for l in (built / "_redirects").read_text().splitlines() if l and not l.startswith("#")]
    return [tuple(l.split()) for l in lines]


def follow(built, path):
    """First matching rule wins; a trailing * matches anything (including nothing after the slash)."""
    for source, dest, status in rules(built):
        if source.endswith("/*") and (path.startswith(source[:-1]) or path == source[:-2]):
            return dest, int(status)
        if source == path:
            return dest, int(status)
    return None, None


def exists(built, path):
    return (built / urls.output_path(path)).exists()


def test_within_cloudflare_limits_and_all_permanent(built):
    rs = rules(built)
    dynamic = [r for r in rs if "*" in r[0] or ":" in r[0]]
    assert len(rs) - len(dynamic) <= 2000 and len(dynamic) <= 100
    assert all(status == "301" for _, _, status in rs)


VARIANTS = {
    "with slash": lambda post: post,
    "without slash": lambda post: post.rstrip("/"),
    "attachment page": lambda post: post + "attachment-page/",
}


@pytest.mark.parametrize("variant", VARIANTS)
def test_every_old_post_url_lands_on_its_comic(built, site, variant):
    for entry in OLD:
        path = VARIANTS[variant](entry["post"])
        dest, status = follow(built, path)
        assert dest == urls.comic(site.comics[entry["number"] - 1]), path
        assert status == 301 and exists(built, dest), path


def test_old_image_hotlinks_land_on_the_same_artwork(built, site):
    for entry in OLD:
        comic = site.comics[entry["number"] - 1]
        for upload, img in zip(entry["uploads"], comic.images):
            dest, _ = follow(built, upload)
            assert dest == urls.comic_image(img) and (built / dest.lstrip("/")).exists(), upload


@pytest.mark.parametrize("old, new", [
    ("/feed/", "/feed.xml"), ("/feed", "/feed.xml"), ("/comments/feed/", "/feed.xml"),
    ("/tag/things-randall-says/", "/archive/"), ("/category/posts/", "/archive/"),
    ("/page/2/", "/archive/"), ("/2013/05/", "/archive/"), ("/author/samanthadegges/", "/about/"),
])
def test_feeds_and_listing_pages(built, old, new):
    assert follow(built, old) == (new, 301)
    assert exists(built, new)


def test_no_rule_shadows_a_real_page(built):
    # Cloudflare applies _redirects even when a file exists at the path.
    for source, _, _ in rules(built):
        prefix = source[:-1] if source.endswith("*") else source
        hits = [p for p in built.rglob("*") if p.is_file() and ("/" + str(p.relative_to(built))).startswith(prefix)]
        if not source.endswith("*"):
            hits = [p for p in hits if re.fullmatch(re.escape(source.rstrip("/")) + r"(/index\.html)?", "/" + str(p.relative_to(built)))]
        assert not hits, f"{source} would shadow {hits[:3]}"


def test_new_urls_are_not_redirected(built, site):
    for path in ["/", urls.ARCHIVE, urls.ABOUT, urls.FEED, *(urls.comic(c) for c in site.comics)]:
        assert follow(built, path) == (None, None), path
