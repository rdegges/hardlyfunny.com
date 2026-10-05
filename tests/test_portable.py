"""The portable preview build: every internal reference is relative and resolves on disk."""

import re

import pytest

from hardlyfunny import urls
from hardlyfunny.build import build


@pytest.fixture(scope="module")
def portable(tmp_path_factory):
    out = tmp_path_factory.mktemp("portable")
    build(out, portable=True)
    return out


def pages(portable):
    feed = portable / urls.output_path(urls.FEED)  # Atom: its links stay absolute for feed readers
    return [p for p in portable.rglob("*.html") if p != feed]


def test_feed_links_stay_absolute(portable):
    feed = (portable / urls.output_path(urls.FEED)).read_text()
    assert 'href="https://hardlyfunny.com/feed/"' in feed and 'href="/' not in feed


def test_no_root_relative_references_remain(portable):
    for page in pages(portable):
        assert not re.search(r'(href|src|data-image)="/(?!/)', page.read_text()), page


def test_relative_references_resolve_on_disk(portable):
    for page in pages(portable):
        for ref in re.findall(r'(?:href|src|data-image)="([^"#]+)"', page.read_text()):
            if ref.startswith(("http:", "https:", "data:", "mailto:")):
                continue
            target = (page.parent / ref.split("?")[0]).resolve()
            assert target.exists(), f"{page}: {ref}"


def test_license_links_keep_their_fragment(portable):
    # The check above skips refs with a "#", so the footer's /about/#license link is checked here.
    for page, ref in ((portable / "index.html", "about/index.html#license"),
                      (portable / "comics" / "infinite-recursion" / "index.html", "../../about/index.html#license")):
        assert f'href="{ref}"' in page.read_text(), page
        assert (page.parent / ref.split("#")[0]).resolve().is_file()
    assert 'id="license"' in (portable / "about" / "index.html").read_text()


def test_seo_urls_stay_absolute(portable):
    html = (portable / "comics" / "infinite-recursion" / "index.html").read_text()
    assert '<link rel="canonical" href="https://hardlyfunny.com/comics/infinite-recursion/">' in html
    assert 'content="https://hardlyfunny.com/images/social/infinite-recursion.jpg"' in html


def test_titles_match_the_standard_build(portable, built, parse):
    # The portable rewrite only touches link attributes; tab titles must not drift between the two builds.
    for page in pages(portable):
        assert parse(page).title == parse(built / page.relative_to(portable)).title, page
