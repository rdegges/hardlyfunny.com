import dataclasses
import json
import re

import pytest
from PIL import Image as PILImage

from hardlyfunny.build import CONTENT
from hardlyfunny.content import ContentError, slugify, strip_tags, truncate, validate


def test_slugify_makes_readable_ascii_slugs():
    assert slugify("Randall’s Grand Idea") == "randalls-grand-idea"
    assert slugify("Screen of What?!") == "screen-of-what"
    assert slugify("We all can’t live entirely from our keyboards…") == "we-all-cant-live-entirely-from-our-keyboards"


def test_truncate_prefers_sentence_then_word_boundaries():
    assert truncate("Short.", 50) == "Short."
    assert truncate("First sentence here. Second sentence is much longer than the limit.", 36) == "First sentence here."
    assert truncate("one two three four five six", 12) == "one two…"


def test_strip_tags_flattens_paragraphs():
    assert strip_tags("<p>Hi &amp; <em>bye</em></p><p>Next</p>") == "Hi & bye Next"


def test_archive_is_complete_and_in_order(site):
    raw = json.loads((CONTENT / "comics.json").read_text(encoding="utf-8"))["comics"]
    assert len(site.comics) == len(raw) >= 82
    assert [c.number for c in site.comics] == list(range(1, len(raw) + 1))
    dates = [c.published for c in site.comics]
    assert dates == sorted(dates)


def test_slugs_are_unique_clean_and_not_wordpress_style(site):
    slugs = [c.slug for c in site.comics]
    assert len(set(slugs)) == len(slugs)
    for slug in slugs:
        assert re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", slug), slug
        assert not re.fullmatch(r"\d{3}", slug) or slug == "404", f"{slug} looks like a WordPress post id"


def test_every_comic_has_real_alt_text_and_a_transcript(site):
    for c in site.comics:
        for img in c.images:
            assert (CONTENT / img.file).exists(), img.file
            assert img.width > 0 and img.height > 0
            assert 20 <= len(img.alt) <= 250, f"#{c.number} alt length {len(img.alt)}"
            assert img.alt.strip().lower() != c.title.lower()
            assert not img.alt.lower().startswith(("image of", "picture of", "comic of"))
        assert c.transcript, f"#{c.number} has no transcript"


def test_summaries_fit_meta_description_length(site):
    for c in site.comics:
        assert 0 < len(c.summary) <= 161, c.number


def test_image_dimensions_match_the_files(site):
    for c in site.comics:
        for img in c.images:
            with PILImage.open(CONTENT / img.file) as im:
                assert (img.width, img.height) == im.size, img.file


def test_meta_descriptions_are_unique(site):
    descriptions = [site.description(c) for c in site.comics]
    assert len(set(descriptions)) == len(descriptions)
    assert all(0 < len(d) <= 160 for d in descriptions)


def test_comics_with_a_short_note_are_described_by_their_alt_text(site):
    for number in (1, 6, 43):
        comic = site.comics[number - 1]
        assert site.description(comic) == truncate(comic.alt, 160), number


@pytest.mark.parametrize("break_it, message", [
    (lambda cs: (cs[1], cs[0], *cs[2:]), "number"),
    (lambda cs: (cs[0], dataclasses.replace(cs[1], slug=cs[0].slug), *cs[2:]), "used twice"),
    (lambda cs: (cs[0], dataclasses.replace(cs[1], slug="Bad Slug"), *cs[2:]), "lowercase"),
    (lambda cs: (dataclasses.replace(cs[0], published=cs[1].published.replace(year=2030)), *cs[1:]), "date order"),
])
def test_validation_catches_hand_editing_mistakes(site, break_it, message):
    with pytest.raises(ContentError, match=message):
        validate(break_it(site.comics))


def test_archived_links_are_well_formed_wayback_snapshots(site):
    archived = [h for c in site.comics for h in re.findall(r'href="([^"]+)"', c.note_html) if "archive.org" in h]
    assert archived, "dead links in notes are replaced with Internet Archive snapshots"
    for href in archived:
        assert re.fullmatch(r"https://web\.archive\.org/web/(19|20)\d{12}/https?://\S+", href), href
