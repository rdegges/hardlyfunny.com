import dataclasses
import json
from xml.etree import ElementTree as ET

from hardlyfunny import seo


def node(block, type_):
    """The one node of this @type in a JSON-LD @graph (a KeyError or a failed match, never a vacuous pass)."""
    [found] = [n for n in json.loads(block)["@graph"] if n["@type"] == type_]
    return found


def test_jsonld_cannot_break_out_of_its_script_element(site):
    nasty = dataclasses.replace(site.comics[0], title="</script><!--<script>", transcript=("Randall: <b>&</b>",))
    block = seo.comic_jsonld(site, nasty)
    assert "<" not in block and ">" not in block and "&" not in block
    assert node(block, "ComicStory")["name"] == "</script><!--<script>"


def test_keywords_are_omitted_when_a_comic_has_no_tags(site):
    untagged = dataclasses.replace(site.comics[0], tags=())
    story = node(seo.comic_jsonld(site, untagged), "ComicStory")
    assert story["name"] == untagged.title and "keywords" not in story


def test_comic_story_lists_every_image_and_names_its_publisher(site):
    two = next(c for c in site.comics if len(c.images) > 1)
    story = node(seo.comic_jsonld(site, two), "ComicStory")
    assert story["@id"] == f"{site.url}/comics/{two.slug}/#comic"
    assert [i["contentUrl"] for i in story["image"]] == [f"{site.url}/images/{img.file}" for img in two.images]
    assert story["publisher"] == story["artist"] == story["author"] == {"@id": f"{site.url}/about/#samantha"}


def test_breadcrumbs_lead_home_then_archive_then_the_comic(site):
    # A comic that shares its title with another, so the last crumb must be the numbered display title.
    twin = next(c for c in site.comics if site.display_title(c) != c.title)
    crumbs = node(seo.comic_jsonld(site, twin), "BreadcrumbList")["itemListElement"]
    assert [c["position"] for c in crumbs] == [1, 2, 3]
    assert [c["item"] for c in crumbs] == [f"{site.url}/", f"{site.url}/archive/", f"{site.url}/comics/{twin.slug}/"]
    assert [c["name"] for c in crumbs] == ["Home", "Archive", f"{twin.title} (No. {twin.number})"]


def test_robots_sitemap_follows_the_site_url(site):
    # The Sitemap line must be absolute (RFC 9309) and built from site.url, not a hardcoded host.
    moved = dataclasses.replace(site, url="https://example.test/")
    text = seo.robots(moved)
    assert text.splitlines()[-1] == "Sitemap: https://example.test/sitemap.xml"
    assert "hardlyfunny.com" not in text


SM = "{http://www.sitemaps.org/schemas/sitemap/0.9}"
IMG = "{http://www.google.com/schemas/sitemap-image/1.1}"


def test_sitemap_image_urls_are_xml_escaped(site):
    # comics.json file names aren't validated, so a "&" or "<" must not break the XML.
    nasty = dataclasses.replace(site.comics[0].images[0], file="comics/a&b<c>.png")
    comic = dataclasses.replace(site.comics[0], images=(nasty,))
    root = ET.fromstring(seo.sitemap(dataclasses.replace(site, comics=(comic,))))
    assert [el.text for el in root.iter(f"{IMG}loc")] == [f"{site.url}/images/comics/a&b<c>.png"]


def test_sitemap_image_urls_follow_the_site_url(site):
    text = seo.sitemap(dataclasses.replace(site, url="https://example.test/"))
    locs = [el.text for el in ET.fromstring(text).iter(f"{IMG}loc")]
    assert locs and all(loc.startswith("https://example.test/images/comics/") for loc in locs)
    assert "hardlyfunny.com" not in text


def test_sitemap_images_follow_loc_and_lastmod_in_each_url(site):
    # sitemap 0.9's XSD is a sequence: loc, lastmod?, changefreq?, priority?, then extensions.
    for url in ET.fromstring(seo.sitemap(site)).iter(f"{SM}url"):
        tags = [child.tag for child in url]
        core = [t for t in tags if t.startswith(SM)]
        assert core in ([f"{SM}loc"], [f"{SM}loc", f"{SM}lastmod"]), tags
        assert tags[: len(core)] == core and set(tags[len(core):]) <= {f"{IMG}image"}, tags


def test_sitemap_lists_a_comics_images_in_panel_order(site):
    two = next(c for c in site.comics if len(c.images) > 1)
    swapped = dataclasses.replace(two, images=two.images[::-1])
    root = ET.fromstring(seo.sitemap(dataclasses.replace(site, comics=(swapped,))))
    page = next(u for u in root.iter(f"{SM}url") if u.find(f"{SM}loc").text.endswith(f"/comics/{two.slug}/"))
    assert [i.find(f"{IMG}loc").text for i in page.iter(f"{IMG}image")] == [
        site.url + "/images/" + img.file for img in swapped.images]
