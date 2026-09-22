"""The portable preview build: every internal reference is relative and resolves on disk."""

import re

import pytest

from hardlyfunny.build import build


@pytest.fixture(scope="module")
def portable(tmp_path_factory):
    out = tmp_path_factory.mktemp("portable")
    build(out, portable=True)
    return out


def test_no_root_relative_references_remain(portable):
    for page in portable.rglob("*.html"):
        assert not re.search(r'(href|src|data-image)="/(?!/)', page.read_text()), page


def test_relative_references_resolve_on_disk(portable):
    for page in portable.rglob("*.html"):
        for ref in re.findall(r'(?:href|src|data-image)="([^"#]+)"', page.read_text()):
            if ref.startswith(("http:", "https:", "data:", "mailto:")):
                continue
            target = (page.parent / ref.split("?")[0]).resolve()
            assert target.exists(), f"{page}: {ref}"


def test_seo_urls_stay_absolute(portable):
    html = (portable / "comics" / "infinite-recursion" / "index.html").read_text()
    assert '<link rel="canonical" href="https://hardlyfunny.com/comics/infinite-recursion/">' in html
    assert 'content="https://hardlyfunny.com/images/social/infinite-recursion.jpg"' in html
