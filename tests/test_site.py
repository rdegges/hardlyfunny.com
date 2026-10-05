"""Checks on the built site: SEO tags, accessibility basics, links, and machine-readable files."""

import dataclasses
import json
import re
from datetime import date
from urllib import robotparser
from urllib.parse import urlparse
from xml.etree import ElementTree as ET

import pytest

from hardlyfunny import seo, share, urls
from hardlyfunny.build import CONTENT, comic_page, environment
from hardlyfunny.content import strip_tags

SITE_URL = "https://hardlyfunny.com"


def html_pages(built):
    feed = built / urls.output_path(urls.FEED)  # Atom, built as an index.html so /feed/ serves it
    return sorted(p for p in built.rglob("*.html") if p != feed)


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


def test_titles_follow_the_house_format(built, site, parse):
    comics = {built / "comics" / c.slug / "index.html": site.display_title(c) for c in site.comics}
    others = {
        built / "archive" / "index.html": f"Archive - {site.title}",
        built / "about" / "index.html": f"About - {site.title}",
        built / "random" / "index.html": f"Random comic - {site.title}",
        built / "404.html": f"Page not found - {site.title}",
    }
    checked = set()
    for path in html_pages(built):
        page = parse(path)
        assert "·" not in page.title, path
        if path in comics:
            assert page.title == f"{comics[path]} - A {site.title} Comic", path
            # Social cards show the bare comic title; the suffix is only for browser tabs and search results.
            assert page.meta("og:title") == page.meta("twitter:title") == comics[path], path
        elif path != built / "index.html":
            assert page.title == others[path], path
            assert page.meta("og:title") == page.meta("twitter:title") == page.title, path
        checked.add(path)
    assert checked >= comics.keys() | others.keys()


def test_comic_title_suffix_keeps_the_number_that_tells_twins_apart(site):
    # Built from a copy, so the check holds even if the real archive loses its duplicate titles.
    first, second, *rest = site.comics
    twins = dataclasses.replace(site, comics=(first, dataclasses.replace(second, title=first.title), *rest))
    page = comic_page(twins, twins.comics[1])
    assert page.title == f"{first.title} (No. 2) - A {site.title} Comic"
    assert page.og_title == f"{first.title} (No. 2)"
    assert comic_page(twins, twins.comics[0]).title == f"{first.title} (No. 1) - A {site.title} Comic"


def test_home_page_title_is_the_site_not_the_latest_comic(built, site, parse):
    home = parse(built / "index.html")
    assert home.title.startswith(f"{site.title}: ")
    assert site.latest.title not in home.title and not home.title.endswith(" Comic")


def test_home_page_says_the_comic_is_complete(built, site):
    first, latest = site.comics[0].published, site.latest.published
    [line] = re.findall(r'<p class="intro">(.*?)</p>', (built / "index.html").read_text(), re.S)
    assert re.sub(r"<[^>]+>", "", line) == (f"{site.title} ran from {first:%B %Y} to {latest:%B %Y} and is complete. "
                                            f"Read all {len(site.comics)} comics in the archive.")
    assert f'<a href="{urls.ARCHIVE}">archive</a>' in line
    assert 'class="intro"' not in (built / "comics" / site.latest.slug / "index.html").read_text()


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


def jsonld_blocks(html):
    return [json.loads(b) for b in re.findall(r'<script type="application/ld\+json">(.*?)</script>', html, re.S)]


def jsonld_nodes(value):
    """Every object in a JSON-LD value, at any depth (top level, @graph, nested and in lists)."""
    if isinstance(value, dict):
        yield value
        for v in value.values():
            yield from jsonld_nodes(v)
    elif isinstance(value, list):
        for v in value:
            yield from jsonld_nodes(v)


def test_structured_data_describes_each_comic(built, site):
    comic = site.comics[69]
    [block] = jsonld_blocks((built / "comics" / comic.slug / "index.html").read_text())
    [data] = [n for n in block["@graph"] if n["@type"] == "ComicStory"]
    assert data["name"] == comic.title
    assert data["isPartOf"]["@type"] == "ComicSeries"
    assert data["image"][0]["caption"] == comic.alt


def test_every_comic_page_describes_that_comic_and_its_breadcrumb_trail(built, site):
    # Every page, not one sample: a field that drifts from the comic it sits on is a wrong rich result.
    for comic in site.comics:
        page = f"{SITE_URL}/comics/{comic.slug}/"
        [block] = jsonld_blocks((built / "comics" / comic.slug / "index.html").read_text())
        assert sorted(n["@type"] for n in block["@graph"]) == ["BreadcrumbList", "ComicStory", "Person", "Person"], comic.slug
        [story] = [n for n in block["@graph"] if n["@type"] == "ComicStory"]
        [trail] = [n for n in block["@graph"] if n["@type"] == "BreadcrumbList"]
        assert (story["@id"], story["url"], story["position"]) == (page + "#comic", page, comic.number)
        assert story["datePublished"] == comic.published.isoformat()
        assert story["text"] == "\n".join(comic.transcript)
        assert [(i["contentUrl"], i["width"], i["height"], i["caption"]) for i in story["image"]] == [
            (f"{SITE_URL}/images/{img.file}", img.width, img.height, img.alt) for img in comic.images
        ]
        crumbs = trail["itemListElement"]
        assert [c["position"] for c in crumbs] == list(range(1, len(crumbs) + 1))
        assert (crumbs[-1]["item"], crumbs[-1]["name"]) == (story["url"], site.display_title(comic))


def test_comic_descriptions_match_in_meta_social_and_jsonld(built, site, parse):
    for comic in site.comics:
        path = built / "comics" / comic.slug / "index.html"
        page = parse(path)
        [block] = jsonld_blocks(path.read_text())
        [story] = [n for n in block["@graph"] if n["@type"] == "ComicStory"]
        assert story["description"] == page.meta("description") == site.description(comic), comic.slug
        assert page.meta("og:description") == page.meta("twitter:description") == page.meta("description"), comic.slug


def test_archive_description_counts_the_comics_and_fits_search_results(built, site, parse):
    description = parse(built / "archive" / "index.html").meta("description")
    assert 120 <= len(description) <= 160, description
    assert f"All {len(site.comics)} " in description


def test_archive_description_spans_the_first_to_the_latest_year(built, site, parse):
    description = parse(built / "archive" / "index.html").meta("description")
    assert f"{site.comics[0].published.year} to {site.latest.published.year}" in description


def test_redraw_no_82_has_its_own_structured_data_description(built, site):
    # No. 82 redraws No. 20 with the same note; JSON-LD used to repeat it while the meta tag did not.
    def story(number):
        comic = site.comics[number - 1]
        [block] = jsonld_blocks((built / "comics" / comic.slug / "index.html").read_text())
        [node] = [n for n in block["@graph"] if n["@type"] == "ComicStory"]
        return node["description"]
    assert site.comics[19].summary == site.comics[81].summary
    assert story(20) != story(82)


def test_indexable_pages_have_distinct_descriptions(built, parse):
    seen = {}
    for path in html_pages(built):
        page = parse(path)
        if page.meta("robots") == "noindex":
            continue
        description = page.meta("description")
        assert description not in seen, f"{path} repeats {seen.get(description)}"
        seen[description] = path


def test_about_page_describes_the_series_and_its_two_people(built, site):
    [block] = jsonld_blocks((built / "about" / "index.html").read_text())
    nodes = {n["@id"]: n for n in block["@graph"]}
    randall = SITE_URL + "/about/#randall"
    [about] = [n for n in block["@graph"] if n["@type"] == "AboutPage"]
    assert (about["url"], about["about"]) == (f"{SITE_URL}/about/", {"@id": f"{SITE_URL}/#series"})
    assert nodes[f"{SITE_URL}/#series"]["character"] == [{"@id": SAMANTHA}, {"@id": randall}]
    assert nodes[SAMANTHA] == {"@type": "Person", "@id": SAMANTHA, "name": site.author, "url": f"{SITE_URL}/about/"}
    assert nodes[randall] == {"@type": "Person", "@id": randall, "name": "Randall Degges", "url": "https://rdegges.com"}


def test_about_page_says_the_comic_is_complete_and_links_randall(built):
    html = (built / urls.output_path(urls.ABOUT)).read_text()
    # The text itself, not the site nav, which links the archive on every page.
    [body] = re.findall(r'<div class="body">(.*?)</div>', html, re.S)
    assert "Hardly Funny is complete.</strong>" in body
    assert set(re.findall(r'href="([^"]+)"', body)) == {"https://rdegges.com", urls.ARCHIVE}
    for stale in ("Now, Samantha illustrates", "works from home as a lead developer"):
        assert stale not in html



def test_about_page_counts_and_dates_match_the_comics(site):
    # The About prose states the count and run as plain text; this ties it to the data so a
    # corrected date or an added comic can't leave the About page contradicting the archive.
    text = strip_tags(site.about_html)
    counts = [int(n) for n in re.findall(r"\b(\d+) comics\b", text)]
    months = re.findall(r"\b(?:January|February|March|April|May|June|July|August|September|October|November|December) \d{4}\b", text)
    assert counts and set(counts) == {len(site.comics)}, counts
    assert f"{site.latest.published:%B %Y}" in months, months
    assert set(months) <= {f"{site.comics[0].published:%B %Y}", f"{site.latest.published:%B %Y}"}, months


def render_home(site):
    latest = site.latest
    prev, _ = site.neighbours(latest)
    links = share.links(urls.absolute(site.url, urls.comic(latest)), latest.title, site.title)
    return environment(site).get_template("comic.html").render(
        page=comic_page(site, latest, home=True), comic=latest, prev=prev, next=None, share_links=links, home=True)


def shortened(site, count, last_date):
    """The first `count` comics, with the last one re-dated, so the run and count differ from the real data."""
    comics = (*site.comics[:count - 1], dataclasses.replace(site.comics[count - 1], published=last_date))
    return dataclasses.replace(site, comics=comics)


def test_home_intro_and_llms_txt_follow_the_data_not_frozen_text(site):
    # The built-site tests compare against the real data, which a hard-coded sentence would also pass.
    small = shortened(site, 5, date(2013, 3, 9))
    expected = f"{small.title} ran from January 2012 to March 2013 and is complete."
    [line] = re.findall(r'<p class="intro">(.*?)</p>', render_home(small), re.S)
    assert re.sub(r"<[^>]+>", "", line) == f"{expected} Read all 5 comics in the archive."
    for full in (False, True):
        assert f"{expected} All 5 comics are listed below; no new comics are planned." in seo.llms_txt(small, full=full).splitlines()


def test_home_intro_escapes_the_site_title(site):
    hostile = dataclasses.replace(site, title='<script>alert(1)</script> & "Co"')
    [line] = re.findall(r'<p class="intro">(.*?)</p>', render_home(hostile), re.S)
    assert "<script>" not in line and line.startswith("&lt;script&gt;alert(1)&lt;/script&gt; &amp; ")

# Adding a type or an off-site URL must be a deliberate edit here. The type list only catches typos.
# Off-site detection covers http(s) and protocol-relative values under any key, plus every value
# under JSONLD_LINK_KEYS (sameAs included), which must be an exact allowlist entry or a built page.
# An allowlist entry is keyed (node @id, property), so it grants one URL on one property of one node.
# Samantha's Person node may never carry sameAs or an off-site url: the test enforces that, so no
# allowlist entry can grant it.
JSONLD_TYPES = {"WebSite", "ComicSeries", "ComicStory", "Person", "ImageObject", "BreadcrumbList", "ListItem",
                "AboutPage"}
JSONLD_OFFSITE_URLS = {(SITE_URL + "/about/#randall", "url"): "https://rdegges.com"}
JSONLD_LINK_KEYS = ("url", "item", "contentUrl", "acquireLicensePage", "sameAs")
SAMANTHA = SITE_URL + "/about/#samantha"


def offsite_allowed(node, key, value):
    return JSONLD_OFFSITE_URLS.get((node.get("@id"), key)) == value


def is_samantha(node, site):
    """Any object that names her or points at her @id, whatever its @type and however the @id is spelled."""
    ids, names = node.get("@id", []), node.get("name", [])
    ids, names = ids if isinstance(ids, list) else [ids], names if isinstance(names, list) else [names]
    return site.author in names or any("samantha" in urlparse(str(i)).fragment.lower() for i in ids)


def test_jsonld_is_well_formed_on_site_and_self_contained(built, site, parse):
    home, about = built / "index.html", built / urls.output_path(urls.ABOUT)
    comics = sorted((built / "comics").glob("*/index.html"))
    assert site.comics and len(comics) == len(site.comics)
    assert not any(node_id == SAMANTHA for node_id, _ in JSONLD_OFFSITE_URLS), "no off-site URL for Samantha"
    ids = {}  # target page -> its id= attributes

    def page_ids(path):
        if path not in ids:
            ids[path] = {a["id"] for _, a in parse(path).elements if a.get("id")}
        return ids[path]

    for path in html_pages(built):
        html = path.read_text()
        blocks = jsonld_blocks(html)
        # A block the regex misses would skip every check below, so count script tags separately.
        assert len(blocks) == len(parse(path).all("script", type="application/ld+json")), path
        if path in (home, about) or path in comics:
            assert blocks, f"{path} has no JSON-LD"
        nodes = [n for b in blocks for n in jsonld_nodes(b)]
        defined = {n["@id"] for n in nodes if "@id" in n and "@type" in n and "name" in n}
        for n in nodes:
            types = n.get("@type", [])
            types = types if isinstance(types, list) else [types]
            assert set(types) <= JSONLD_TYPES, f"{path}: {types}"
            if is_samantha(n, site):
                assert "sameAs" not in n, f"{path}: {site.author} has sameAs"
                # A bare reference or her full node, nothing else: any other key (a profile link, say) fails.
                assert set(n) in ({"@id"}, {"@type", "@id", "name", "url"}), f"{path}: {site.author} has {sorted(n)}"
                urls_on_her = n.get("url", [])
                for url in urls_on_her if isinstance(urls_on_her, list) else [urls_on_her]:
                    assert url.startswith(site.url + "/"), f"{path}: {site.author} has url={url}"
            if "@id" in n:
                assert isinstance(n["@id"], str) and n["@id"].startswith(site.url + "/"), f"{path}: {n['@id']}"
                assert n["@id"] in defined, f"{path}: {n['@id']} is referenced but never defined"
            # Any absolute URL under any key (sameAs, license, ...) is on-site or allowlisted.
            values = [(k, v) for k, vs in n.items() if k != "@context" for v in (vs if isinstance(vs, list) else [vs])]
            for key, value in values:
                if isinstance(value, str) and re.match(r"(https?:)?//", value, re.I):
                    assert value.startswith(site.url + "/") or offsite_allowed(n, key, value), f"{path}: {key}={value}"
            for key, value in values:
                if key not in JSONLD_LINK_KEYS or isinstance(value, dict) or offsite_allowed(n, key, value):
                    continue  # a nested node is checked on its own
                link = urlparse(value)
                target = built / urls.output_path(link.path)
                assert value.startswith(site.url + "/") and target.is_file(), f"{path}: {key}={value}"
                if link.fragment:
                    assert link.fragment in page_ids(target), f"{path}: {key}={value} has no anchor on that page"


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
    ET.parse(built / urls.output_path(urls.FEED))


def test_sitemap_robots_and_llms_txt(built, site):
    ns = "{http://www.sitemaps.org/schemas/sitemap/0.9}"
    locs = [l.text for l in ET.parse(built / "sitemap.xml").getroot().iter(f"{ns}loc")]
    assert len(locs) == len(site.comics) + 3
    assert f"{SITE_URL}/random/" not in locs
    assert (built / "robots.txt").read_text() == (
        "User-agent: *\n"
        "Content-Signal: search=yes, ai-input=yes, ai-train=yes\n"
        "Allow: /\n"
        "\n"
        f"Sitemap: {SITE_URL}/sitemap.xml\n"
    )
    llms = (built / "llms.txt").read_text()
    assert llms.startswith("# Hardly Funny") and llms.count("/comics/") == len(site.comics)
    assert "Transcript:" in (built / "llms-full.txt").read_text()


def test_llms_txt_says_the_comic_is_complete(built, site):
    first, latest = site.comics[0].published, site.latest.published
    line = (f"{site.title} ran from {first:%B %Y} to {latest:%B %Y} and is complete. "
            f"All {len(site.comics)} comics are listed below; no new comics are planned.")
    for name in ("llms.txt", "llms-full.txt"):
        assert line in (built / name).read_text().splitlines(), name


def test_sitemap_lists_each_comic_image_once_on_its_page(built, parse):
    sm, im = "{http://www.sitemaps.org/schemas/sitemap/0.9}", "{http://www.google.com/schemas/sitemap-image/1.1}"
    root = ET.parse(built / "sitemap.xml").getroot()
    tags = {el.tag for el in root.iter()}
    assert tags == {sm + t for t in ("urlset", "url", "loc", "lastmod")} | {im + "image", im + "loc"}
    by_page = {}
    for url in root.iter(f"{sm}url"):
        page = url.find(f"{sm}loc").text
        assert all(len(img) == 1 for img in url.findall(f"{im}image")), page
        locs = [img.find(f"{im}loc").text for img in url.findall(f"{im}image")]
        path = urlparse(page).path
        if not path.startswith("/comics/"):
            assert not locs, f"{page} lists images"
            continue
        srcs = [SITE_URL + i["src"] for i in parse(built / urls.output_path(path)).all("img")
                if i["src"].startswith("/images/comics/")]
        assert locs == srcs, page
        assert all((built / urlparse(loc).path.lstrip("/")).is_file() for loc in locs), page
        by_page[path] = locs
    # Read comics.json directly, not through the loader, so a dropped image can't hide on both sides.
    raw = json.loads((CONTENT / "comics.json").read_text(encoding="utf-8"))["comics"]
    expected = [f"{SITE_URL}/images/{img['file']}" for c in raw for img in c["images"]]
    listed = [loc for locs in by_page.values() for loc in locs]
    assert sorted(listed) == sorted(expected) and len(set(listed)) == len(listed)
    no_17 = next(c for c in raw if c["number"] == 17)  # the one comic with two images
    assert len(by_page[f"/comics/{no_17['slug']}/"]) == len(no_17["images"]) == 2


ROBOT_AGENTS = ["*", "Googlebot", "Bingbot", "GPTBot", "ClaudeBot", "PerplexityBot", "Google-Extended"]


def robots_allows(text, agent, path):
    """RFC 9309 matching: the group naming the agent (else `*`), longest matching rule wins, Allow
    wins a tie. The stdlib's robotparser takes the first matching rule instead, so a leading
    `Allow: /` would hide every Disallow after it."""
    groups, agents, in_rules = {}, [], False
    for line in text.splitlines():
        key, _, value = (part.strip() for part in line.split("#", 1)[0].partition(":"))
        key = key.lower()
        if key == "user-agent":
            if in_rules:
                agents, in_rules = [], False
            agents.append(value.lower())
            for a in agents:
                groups.setdefault(a, [])
        elif key in {"allow", "disallow"} and agents:
            in_rules = True
            for a in agents:
                groups[a].append((key == "allow", value))
    rules = groups.get(agent.lower(), groups.get("*", []))
    best = (-1, True)
    for allow, pattern in rules:
        if not pattern:
            continue
        regex = re.escape(pattern).replace(r"\*", ".*")
        regex = regex[:-2] + "$" if regex.endswith(r"\$") else regex
        if re.match(regex, path) and (len(pattern), allow) > best:
            best = (len(pattern), allow)
    return best[1]


def built_url_paths(built):
    """Every URL path the build serves, the way Cloudflare maps files to URLs."""
    for file in sorted(built.rglob("*")):
        if file.is_dir() or file.name in {"_headers", "_redirects"}:
            continue
        rel = file.relative_to(built).as_posix()
        yield "/" + rel.removesuffix("index.html") if file.name == "index.html" else "/" + rel


def test_robots_txt_lets_every_crawler_fetch_every_built_url(built):
    # Parsed, not string-matched: a reformatted robots.txt still passes, and a Disallow anywhere
    # in the file that blocks a real URL still fails.
    text = (built / "robots.txt").read_text()
    paths = list(built_url_paths(built))
    assert urls.RANDOM in paths and "/404.html" in paths and urls.FEED in paths
    blocked = [(agent, p) for agent in ROBOT_AGENTS for p in paths if not robots_allows(text, agent, p)]
    assert blocked == []
    stdlib = robotparser.RobotFileParser()
    stdlib.parse(text.splitlines())
    assert stdlib.site_maps() == [f"{SITE_URL}/sitemap.xml"]


@pytest.mark.parametrize("text, agent, path, allowed", [
    ("User-agent: *\nAllow: /\nDisallow: /fonts/\n", "*", "/fonts/a.woff2", False),
    ("User-agent: *\nDisallow: /random/\n", "GPTBot", "/random/", False),
    ("User-agent: *\nDisallow: /random/\n", "GPTBot", "/about/", True),
    ("User-agent: *\nDisallow: /\n\nUser-agent: GPTBot\nAllow: /\n", "GPTBot", "/x", True),
    ("User-agent: *\nDisallow: /*.png$\n", "*", "/a.png", False),
    ("User-agent: *\nDisallow: /*.png$\n", "*", "/a.png?x", True),
    ("User-agent: *\nDisallow: /a\nAllow: /a\n", "*", "/a", True),
    ("User-agent: *\nDisallow:\n", "*", "/", True),
])
def test_robots_allows_matches_rfc_9309(text, agent, path, allowed):
    assert robots_allows(text, agent, path) is allowed


def test_noindex_pages_are_crawlable_so_the_noindex_is_seen(built, parse):
    # A page blocked in robots.txt is never fetched, so its noindex is never read and the URL can
    # still be indexed from links. /random/ used to be disallowed; this keeps that from returning.
    text = (built / "robots.txt").read_text()
    noindex = [path for path in html_pages(built) if parse(path).meta("robots") == "noindex"]
    assert {"random/index.html", "404.html"} <= {p.relative_to(built).as_posix() for p in noindex}
    for path in noindex:
        url = "/" + path.relative_to(built).as_posix().removesuffix("index.html")
        assert all(robots_allows(text, agent, url) for agent in ROBOT_AGENTS), url


def test_content_signal_is_well_formed_and_inside_the_wildcard_group(built):
    # contentsignals.org: a Content-Signal line belongs to the user-agent group above it and
    # holds comma-separated `signal=yes|no` pairs from a fixed vocabulary.
    lines = (built / "robots.txt").read_text().splitlines()
    signals = [i for i, line in enumerate(lines) if line.lower().startswith("content-signal:")]
    assert len(signals) == 1
    start = max((i + 1 for i, line in enumerate(lines[:signals[0]]) if not line.strip()), default=0)
    agents = [l.split(":", 1)[1].strip() for l in lines[start:signals[0]] if l.lower().startswith("user-agent:")]
    assert agents == ["*"]
    pairs = [p.strip().split("=") for p in lines[signals[0]].split(":", 1)[1].split(",")]
    assert all(len(p) == 2 for p in pairs)
    values = dict(pairs)
    assert len(values) == len(pairs), "no signal listed twice"
    assert set(values) <= {"search", "ai-input", "ai-train"}
    assert set(values.values()) <= {"yes", "no"}


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


def test_feed_url_is_sent_as_atom_and_no_stale_rule_remains(built):
    # The feed is built as an index.html, so without this rule the edge sends it as HTML (with the
    # analytics beacon). CI skips the runtime check, and the rule must follow urls.FEED if it moves.
    rules = header_rules((built / "_headers").read_text())
    assert rules[urls.FEED]["content-type"] == "application/atom+xml; charset=utf-8"
    assert [p for p, h in rules.items() if "content-type" in h] == [urls.FEED]


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
