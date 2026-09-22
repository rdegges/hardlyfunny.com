from xml.etree import ElementTree as ET

from hardlyfunny import feed

A = "{http://www.w3.org/2005/Atom}"


def test_feed_is_valid_atom_with_every_comic_newest_first(site):
    root = ET.fromstring(feed.render(site))
    assert root.tag == f"{A}feed"
    for required in ("id", "title", "updated", "author"):
        assert root.find(f"{A}{required}") is not None, required
    assert root.find(f"{A}link[@rel='self']").get("href") == "https://hardlyfunny.com/feed.xml"

    entries = root.findall(f"{A}entry")
    assert len(entries) == 82
    assert entries[0].find(f"{A}title").text == site.latest.title
    ids = [e.find(f"{A}id").text for e in entries]
    assert len(set(ids)) == len(ids)
    for e in entries:
        for required in ("id", "title", "updated", "link", "content"):
            assert e.find(f"{A}{required}") is not None, required
        assert e.find(f"{A}link").get("href").startswith("https://hardlyfunny.com/comics/")


def test_entries_embed_the_comic_with_alt_text_and_transcript(site):
    html = feed.entry_html(site, site.latest)
    assert 'src="https://hardlyfunny.com/images/comics/' in html
    assert f'alt="{site.latest.alt}"' in html.replace("&#x27;", "'").replace("&#39;", "'")
    assert "<h3>Transcript</h3>" in html


def test_entry_ids_are_stable_tag_uris(site):
    assert feed.entry_id(site, site.comics[69]) == "tag:hardlyfunny.com,2012:comic/70"
