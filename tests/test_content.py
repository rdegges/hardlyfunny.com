import dataclasses
import json
import re
import shutil

import pytest
from PIL import Image as PILImage

from hardlyfunny.build import CONTENT
from hardlyfunny.content import ContentError, Topic, load, slugify, strip_tags, truncate, validate


def test_slugify_makes_readable_ascii_slugs():
    assert slugify("Randall’s Grand Idea") == "randalls-grand-idea"
    assert slugify("Screen of What?!") == "screen-of-what"
    assert slugify("We all can’t live entirely from our keyboards…") == "we-all-cant-live-entirely-from-our-keyboards"


def test_truncate_prefers_sentence_then_word_boundaries():
    assert truncate("Short.", 50) == "Short."
    assert truncate("First sentence here. Second sentence is much longer than the limit.", 36) == "First sentence here."
    assert truncate("one two three four five six", 12) == "one two…"


@pytest.mark.parametrize("text", [
    "word " * 60,
    "x" * 300,  # no space to cut at
    "Short one. " + "A much longer second sentence without a stop " * 5,
    "Ünïcödé — “quoted” words, and an ellipsis… " * 6,
    "a" * 159 + " tail",
])
@pytest.mark.parametrize("limit", [20, 80, 159, 160, 161])
def test_truncate_never_exceeds_its_limit(text, limit):
    # Meta descriptions rely on this: search results cut anything past ~160 characters.
    assert 0 < len(truncate(text, limit)) <= limit


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
        assert 0 < len(c.summary) <= 160, c.number


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


def test_only_short_notes_and_the_redraw_fall_back_to_alt_text(site):
    # Pins the set this change produced, so a threshold or rule change shows up as a reviewed diff.
    from_alt = {c.number for c in site.comics if c.note_text and site.description(c) != c.summary}
    assert from_alt == {1, 6, 43, 82}


def _with_notes(site, *notes_and_alts):
    """The first comics of the real archive, renumbered as-is, with the given (note, alt) pairs."""
    comics = tuple(
        dataclasses.replace(c, note_html=f"<p>{note}</p>" if note else "",
                            images=(dataclasses.replace(c.image, alt=alt), *c.images[1:]))
        for c, (note, alt) in zip(site.comics, notes_and_alts)
    )
    return dataclasses.replace(site, comics=comics)


LONG_ALT = "Randall sits at a desk covered in monitors, typing furiously, while Samantha watches from the doorway with a mug of tea."


def test_a_note_long_enough_to_describe_the_comic_is_kept(site):
    note = "Randall spent the whole weekend rebuilding his desk setup and I barely saw him at all."
    assert len(note) >= 80
    s = _with_notes(site, (note, LONG_ALT))
    assert s.description(s.comics[0]) == note


def test_a_comic_without_a_note_is_described_by_its_alt_text(site):
    s = _with_notes(site, ("", LONG_ALT), ("", "A short alt text here."))
    assert [s.description(c) for c in s.comics] == [LONG_ALT, "A short alt text here."]


def test_a_redraw_with_a_short_note_and_the_same_alt_still_gets_its_own_description(site):
    # The docstring promises no two pages share a description, and here they need not: one page
    # can use the note and the other the alt. Before this change No. 1 used "Hi." and No. 2 the alt.
    s = _with_notes(site, ("Hi.", LONG_ALT), ("Hi.", LONG_ALT))
    first, second = (s.description(c) for c in s.comics)
    assert first != second


@pytest.mark.parametrize("break_it, message", [
    (lambda cs: (cs[1], cs[0], *cs[2:]), "number"),
    (lambda cs: (cs[0], dataclasses.replace(cs[1], slug=cs[0].slug), *cs[2:]), "used twice"),
    (lambda cs: (cs[0], dataclasses.replace(cs[1], slug="Bad Slug"), *cs[2:]), "lowercase"),
    (lambda cs: (dataclasses.replace(cs[0], published=cs[1].published.replace(year=2030)), *cs[1:]), "date order"),
])
def test_validation_catches_hand_editing_mistakes(site, break_it, message):
    with pytest.raises(ContentError, match=message):
        validate(break_it(site.comics), site.topics)


@pytest.mark.parametrize("file", [
    "comics/two words.png",
    "comics/Shouting.png",
    "comics/this&that.png",
    "comics/no-extension",
    "comics/animated.gif",
    "../x.png",
    "comics/../x.png",
    "",
    "x.png",  # README: the field is comics/<name>.<ext>, never a bare name
    "comics/.png",
    "comics/x.PNG",
    "comics/x.jpeg",
    "Comics/x.png",
    "images/x.png",
    "/comics/x.png",
    "comics//x.png",
    "comics/sub/x.png",
    "comics\\x.png",
    "comics/x.png.png",
    "comics/-x.png",
    "comics/x-.png",
    "comics/x--y.png",
    "comics/x_y.png",
    "comics/x%20y.png",
    "comics/x.png?v=2",
    "comics/x.png#top",
    "comics/x.png\n",
    "comics/x.png ",
    " comics/x.png",
    "comics/café.png",
    "comics/\uff11.png",  # fullwidth digit: \d would accept it, [0-9] must not
])
def test_validation_rejects_image_files_that_are_not_url_safe(site, file):
    # These names reach <img src>, the image sitemap, JSON-LD and the feed without percent-encoding.
    second = site.comics[1]
    broken = dataclasses.replace(second, images=(dataclasses.replace(second.image, file=file),))
    with pytest.raises(ContentError, match=r"No\. 2 image") as excinfo:
        validate((site.comics[0], broken, *site.comics[2:]), site.topics)
    assert file in str(excinfo.value)


def test_every_real_image_file_passes_validation(site):
    assert {img.file.rsplit(".", 1)[1] for c in site.comics for img in c.images} == {"png", "jpg"}
    validate(site.comics, site.topics)


def test_archived_links_are_well_formed_wayback_snapshots(site):
    archived = [h for c in site.comics for h in re.findall(r'href="([^"]+)"', c.note_html) if "archive.org" in h]
    assert archived, "dead links in notes are replaced with Internet Archive snapshots"
    for href in archived:
        assert re.fullmatch(r"https://web\.archive\.org/web/(19|20)\d{12}/https?://\S+", href), href


@pytest.mark.parametrize("file", ["comics/a.png", "comics/0.jpg", "comics/404.png", "comics/a-1-b2.jpg"])
def test_validation_accepts_minimal_url_safe_image_files(site, file):
    # Boundaries of the rule: one-character names, digits only, hyphen-joined runs, both extensions.
    second = site.comics[1]
    ok = dataclasses.replace(second, images=(dataclasses.replace(second.image, file=file),))
    validate((site.comics[0], ok, *site.comics[2:]), site.topics)


def test_validation_checks_every_image_not_just_the_first(site):
    # No. 17 is the only multi-image comic; its second panel must be held to the same rule.
    i = 16
    c = site.comics[i]
    assert len(c.images) > 1
    broken = dataclasses.replace(c, images=(c.images[0], dataclasses.replace(c.images[1], file="comics/Panel 2.png")))
    with pytest.raises(ContentError, match=r"No\. 17 image") as excinfo:
        validate((*site.comics[:i], broken, *site.comics[i + 1:]), site.topics)
    assert "comics/Panel 2.png" in str(excinfo.value)


def test_image_name_check_does_not_mask_the_missing_image_and_alt_text_checks(site):
    # The new per-image loop runs first; a comic with no images, or a safe name but blank alt,
    # must still reach the existing "at least one image / alt text" error.
    second = site.comics[1]
    for broken in (dataclasses.replace(second, images=()),
                   dataclasses.replace(second, images=(dataclasses.replace(second.image, alt="  "),))):
        with pytest.raises(ContentError, match="alt text"):
            validate((site.comics[0], broken, *site.comics[2:]), site.topics)


def test_build_refuses_unsafe_image_file_before_touching_the_output(tmp_path):
    # End to end through load(): a traversal path in comics.json must stop the build before
    # _clear() wipes the previous output or images.py copies anything outside out/images.
    from hardlyfunny.build import build

    content = tmp_path / "content"
    shutil.copytree(CONTENT, content)
    data = json.loads((content / "comics.json").read_text(encoding="utf-8"))
    data["comics"][1]["images"][0]["file"] = "../../escape.png"
    (content / "comics.json").write_text(json.dumps(data), encoding="utf-8")
    out = tmp_path / "site"
    out.mkdir()
    (out / "index.html").write_text("previous build")

    with pytest.raises(ContentError, match=r"No\. 2 image"):
        build(out, content=content)
    assert (out / "index.html").read_text() == "previous build"
    assert not (tmp_path / "escape.png").exists()


def _tag_first(cs, n, slug):
    """The comics with `slug` added to the topics of the first n."""
    return tuple(dataclasses.replace(c, topics=(*c.topics, slug)) if i < n else c for i, c in enumerate(cs))


def _topic(slug):
    return Topic(slug=slug, title=slug.title(), intro_html="<p>An intro.</p>")


@pytest.mark.parametrize("break_it, message", [
    (lambda cs, ts: ((dataclasses.replace(cs[0], topics=()), *cs[1:]), ts), r"No\. 1 has no topics"),
    (lambda cs, ts: ((cs[0], dataclasses.replace(cs[1], topics=("gaming", "nope")), *cs[2:]), ts),
     r"No\. 2 has topic “nope”, which isn't in the topics list"),
    (lambda cs, ts: (cs, (*ts, _topic("unused"))), r"Topic “unused” has 0 comics\. Every topic needs at least 3"),
    (lambda cs, ts: (_tag_first(cs, 2, "thin"), (*ts, _topic("thin"))), r"Topic “thin” has 2 comics"),
    (lambda cs, ts: (cs, (*ts, ts[0])), r"Topic slug “working-from-home” is used twice"),
])
def test_validation_catches_topic_mistakes(site, break_it, message):
    with pytest.raises(ContentError, match=message):
        validate(*break_it(site.comics, site.topics))


@pytest.mark.parametrize("slug", ["Gaming", "two words", "tag/gaming", "x_y", "-x", "x-", "x--y", "", "café"])
def test_validation_rejects_topic_slugs_that_are_not_url_safe(site, slug):
    # Topic slugs go into /topics/<slug>/ unescaped, like comic slugs.
    comics = _tag_first(site.comics, 3, slug)
    with pytest.raises(ContentError, match=f"Topic slug “{re.escape(slug)}” must be lowercase"):
        validate(comics, (*site.topics, _topic(slug)))


def test_a_topic_with_exactly_three_comics_is_allowed(site):
    validate(_tag_first(site.comics, 3, "trio"), (*site.topics, _topic("trio")))


def test_every_real_comic_has_known_topics_and_every_topic_has_enough_comics(site):
    slugs = [t.slug for t in site.topics]
    assert len(slugs) == len(set(slugs)) == 8
    for c in site.comics:
        assert c.topics and set(c.topics) <= set(slugs), c.number
    for t in site.topics:
        assert len(site.comics_about(t)) >= 3, t.slug


def test_comics_json_uses_topics_not_tags():
    # Tags were replaced by curated topics; a leftover "tags" field would be silently ignored.
    raw = json.loads((CONTENT / "comics.json").read_text(encoding="utf-8"))
    assert all("tags" not in c and c["topics"] for c in raw["comics"])
    assert [t["slug"] for t in raw["topics"]]


def test_topic_intro_html_escapes_its_text(site):
    # The Dating and Marriage intro says "<3": it must reach the page as text, not as a broken tag.
    [dating] = [t for t in site.topics if t.slug == "dating-and-marriage"]
    assert "&lt;3" in dating.intro_html and "<3" in dating.intro_text


def test_build_refuses_a_comic_added_without_topics(tmp_path):
    # The loader must not default a missing "topics" field to nothing and carry on.
    content = tmp_path / "content"
    shutil.copytree(CONTENT, content)
    data = json.loads((content / "comics.json").read_text(encoding="utf-8"))
    data["comics"][1]["tags"] = data["comics"][1].pop("topics")
    (content / "comics.json").write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ContentError, match=r"No\. 2 has no topics"):
        load(content / "comics.json")


def test_a_comic_listing_a_topic_twice_is_rejected_or_shown_once(site):
    # Either policy is fine: refuse the hand-editing slip, or collapse it. What must not happen is
    # the same topic link, feed category and JSON-LD keyword appearing twice for one comic.
    c = site.comics[1]
    doubled = dataclasses.replace(c, topics=(c.topics[0], c.topics[0]))
    comics = (site.comics[0], doubled, *site.comics[2:])
    try:
        validate(comics, site.topics)
    except ContentError:
        return
    shown = [t.slug for t in dataclasses.replace(site, comics=comics).topics_of(doubled)]
    assert shown == [c.topics[0]]


@pytest.mark.parametrize("field, blank", [("title", "  "), ("intro_html", "<p> </p>")])
def test_a_blank_topic_title_or_intro_is_rejected_or_never_reaches_a_page(site, field, blank):
    # A blank title is an empty h1 and "Comics about  - Hardly Funny"; a blank intro is an empty
    # meta description. Comics get the same guard for alt text.
    from hardlyfunny.build import topic_page
    topics = (dataclasses.replace(site.topics[0], **{field: blank}), *site.topics[1:])
    try:
        validate(site.comics, topics)
    except ContentError:
        return
    topic = topics[0]
    page = topic_page(dataclasses.replace(site, topics=topics), topic)
    assert topic.title.strip() and page.description.strip(), (field, page.title, page.description)


def test_build_refuses_comics_json_without_a_topics_list(tmp_path):
    # Without the top-level list every comic's topic is unknown; that must stop the build, not
    # quietly produce a site with no topic pages.
    content = tmp_path / "content"
    shutil.copytree(CONTENT, content)
    data = json.loads((content / "comics.json").read_text(encoding="utf-8"))
    del data["topics"]
    (content / "comics.json").write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ContentError, match=r"No\. 1 has topic “out-in-public”, which isn't in the topics list"):
        load(content / "comics.json")


def test_topics_of_follows_the_comics_order_and_comics_about_is_newest_first(site):
    # Real data lists every comic's topics in topics-list order, so it can't tell the two apart.
    c = next(c for c in site.comics if len(c.topics) == 2)
    flipped = dataclasses.replace(c, topics=c.topics[::-1])
    assert [t.slug for t in site.topics_of(flipped)] == list(flipped.topics)
    for topic in site.topics:
        numbers = [c.number for c in site.comics_about(topic)]
        assert numbers == sorted(numbers, reverse=True) and len(numbers) >= 3, topic.slug
