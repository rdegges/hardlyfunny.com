"""The WordPress → new-site redirects, checked the way Cloudflare applies them."""

import json
import re
from collections import Counter

import pytest

from hardlyfunny import redirects, urls
from hardlyfunny.build import ROOT
from hardlyfunny.content import Topic

OLD = json.loads((ROOT / "archive" / "wordpress_urls.json").read_text(encoding="utf-8"))["comics"]
ARCHIVED = json.loads((ROOT / "archive" / "comics.json").read_text(encoding="utf-8"))["comics"]


def rules(built):
    lines = [l for l in (built / "_redirects").read_text().splitlines() if l and not l.startswith("#")]
    return [tuple(l.split()) for l in lines]


def splat_matches(source, path):
    """A trailing /* matches anything below the prefix, but not the bare prefix itself (`/tag/*` does not match `/tag`; cf dev and the production edge both return 404)."""
    return path.startswith(source[:-1])


def follow(built, path):
    """How the edge behaves: an exact rule wins; otherwise the one splat that matches.

    File order between different splats is not used, because production Cloudflare doesn't honor it.
    The build guarantees at most one splat can match, and this model asserts it.
    """
    rs = rules(built)
    for source, dest, status in rs:
        if source == path:
            return dest, int(status)
    hits = [(dest, int(status)) for source, dest, status in rs if source.endswith("/*") and splat_matches(source, path)]
    assert len(hits) <= 1, f"{path} matches {len(hits)} splats; the edge picks one unpredictably"
    return hits[0] if hits else (None, None)


def exists(built, path):
    return (built / urls.output_path(path)).exists()


def test_within_cloudflare_limits_and_all_permanent(built):
    rs = rules(built)
    dynamic = [r for r in rs if "*" in r[0] or ":" in r[0]]
    assert len(rs) - len(dynamic) <= 2000 and len(dynamic) <= 100
    assert all(status == "301" for _, _, status in rs)


@pytest.mark.parametrize("static, dynamic", [(redirects.MAX_STATIC + 1, 0), (0, redirects.MAX_DYNAMIC + 1)])
def test_render_refuses_more_rules_than_cloudflare_reads(static, dynamic):
    # Cloudflare reads at most this many rules, so the build must fail rather than ship a partial file.
    rs = [redirects.Redirect(f"/s{i}", "/") for i in range(static)]
    rs += [redirects.Redirect(f"/d{i}/*", "/") for i in range(dynamic)]
    with pytest.raises(ValueError):
        redirects.render(rs)
    redirects.render(rs[1:])


VARIANTS = {
    "with slash": lambda post: post,
    "without slash": lambda post: post.rstrip("/"),
    "attachment page": lambda post: post + "attachment-page/",
    "named attachment": lambda post: post + "attachment/crane-2/",
    "post feed": lambda post: post + "feed/",
    "amp": lambda post: post + "amp/",
    "comment page": lambda post: post + "comment-page-1/",
    "deep path": lambda post: post + "anything/deeper",
}


def old_urls(site):
    """Every old WordPress URL we know of, with where it must land. Built from the data, not from `_redirects`."""
    out = {}
    both = lambda path, dest: out.update({path.rstrip("/") + "/": dest, path.rstrip("/"): dest})
    periods = {}
    for entry in OLD:
        comic = site.comics[entry["number"] - 1]
        for variant in VARIANTS.values():
            out[variant(entry["post"])] = urls.comic(comic)
        for upload, img in zip(entry["uploads"], comic.images):
            out[upload] = urls.comic_image(img)
            out[upload + "?w=300"] = urls.comic_image(img) + "?w=300"
        y, m, d = entry["post"].strip("/").split("/")[:3]
        for period in (y, f"{y}/{m}", f"{y}/{m}/{d}"):
            periods[period] = periods.get(period, 0) + 1
    for period, count in periods.items():
        both(f"/{period}/", urls.ARCHIVE)
        both(f"/{period}/feed/", urls.FEED)
        out[f"/{period}/feed/atom/"] = urls.FEED
        out[f"/{period}/feed/rss2/"] = urls.FEED
        for n in range(1, count + 1):
            both(f"/{period}/page/{n}/", urls.ARCHIVE)
        # WordPress accepted months and days without the leading zero too.
        y, *rest = period.split("/")
        unpadded = "/".join([y, *(str(int(part)) for part in rest)])
        both(f"/{unpadded}/", urls.ARCHIVE)
        if len(rest) == 2:
            both(f"/{y}/{rest[0]}/{int(rest[1])}/", urls.ARCHIVE)
            both(f"/{y}/{int(rest[0])}/{rest[1]}/", urls.ARCHIVE)
    # The tags live on in the WordPress export only. A tag a topic took over goes to that topic's page,
    # with its feed and one page per tagged post; every other tag goes to the archive.
    topic_of = {name: urls.topic(t) for t in site.topics for name in t.wordpress_tags}
    posts = Counter(t.casefold() for c in ARCHIVED for t in c["tags"])
    tags = {t for c in ARCHIVED for t in c["tags"]}
    assert topic_of and set(topic_of) < {t.casefold() for t in tags}, "the tag checks would cover only one side"
    for tag in tags:
        base = f"/tag/{redirects.wordpress_slug(tag)}/"
        dest = topic_of.get(tag.casefold())
        if dest:
            both(base, dest)
            both(base + "feed/", dest)
            out[base + "feed/atom/"] = out[base + "feed/rss2/"] = dest
            for n in range(1, posts[tag.casefold()] + 1):
                both(f"{base}page/{n}/", dest)
        else:
            for suffix in ("", "page/2/", "feed/"):
                both(base + suffix, urls.ARCHIVE)
    # /feed/ itself is the feed again; /feed reaches it through Cloudflare's trailing-slash handling.
    for path in ("/feed/atom/", "/feed/rss2/", "/feed/rss/", "/feed/rdf/", "/comments/feed/",
                 "/comments/feed/atom/", "/comments/feed/rss2/"):
        both(path, urls.FEED)
    both("/category/posts/", urls.ARCHIVE)
    both("/category/posts/page/2/", urls.ARCHIVE)
    both("/page/2/", urls.ARCHIVE)
    both("/type/image/", urls.ARCHIVE)
    both("/author/samanthadegges/", urls.ABOUT)
    # Captured by the Wayback Machine but missing from the export.
    both("/author/samanthadegges/feed/", urls.FEED)
    both("/author/samanthadegges/page/2/", urls.ARCHIVE)
    both("/about/feed/", urls.FEED)
    out["/atom.xml"] = urls.FEED
    out["/feed.xml"] = urls.FEED
    out["/news-sitemap.xml"] = urls.SITEMAP
    out["/favicon.ico"] = "/favicon.png"
    out["/wp-content/uploads/2014/01/2011_theme_bannerpng241.png"] = "/images/brand/banner.png"
    return out


def test_every_old_url_lands_on_a_real_page(built, site):
    for path, dest in old_urls(site).items():
        got, status = follow(built, path.split("?")[0])
        assert (got, status) == (dest.split("?")[0], 301), path
        assert exists(built, got) or (built / got.lstrip("/")).is_file(), f"{path} -> {got}"


def test_dynamic_rules_never_overlap(built):
    prefixes = sorted(source[:-1] for source, _, _ in rules(built) if "*" in source)
    assert all(source.endswith("/*") for source, _, _ in rules(built) if "*" in source or ":" in source)
    for a, b in zip(prefixes, prefixes[1:]):
        assert not b.startswith(a), f"{a}* overlaps {b}*"


@pytest.mark.parametrize("sources", [
    ["/2012/*", "/2012/01/02/engineers/*"],  # the overlap that broke production
    ["/2012/:month/*"],                      # placeholders can't be checked for overlaps
    ["/2012/*/engineers/"],                  # nor can a splat mid-path
    ["/2012*"],                              # nor a splat that isn't a whole segment
])
def test_render_refuses_order_dependent_rules(sources):
    with pytest.raises(ValueError):
        redirects.render([redirects.Redirect(s, "/archive/") for s in sources])


# WordPress.com platform files the Wayback Machine captured on the old domain. They were never the
# comic's content, so the 404 page is the right answer, not a redirect.
WORDPRESS_PLATFORM = [
    "/wp-login.php", "/wp-signup.php", "/wp-admin/", "/xmlrpc.php", "/press-this.php", "/remote-login.php",
    "/osd.xml", "/ads.txt", "/app-ads.txt", "/i/rss/pink-medium.png", "/wp-content/js/bilmur.min.js",
    "/.well-known/security.txt", "/.well-known/nodeinfo/",
]


@pytest.mark.parametrize("path", ["/2012/99/", "/2012/01/02/no-such-post/", "/2015/", "/2012/01/03/", *WORDPRESS_PLATFORM])
def test_paths_wordpress_never_served_are_not_redirected(built, path):
    assert follow(built, path) == (None, None)


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
    ("/feed.xml", "/feed/"), ("/comments/feed/", "/feed/"),
    ("/tag/things-randall-says/", "/archive/"), ("/category/posts/", "/archive/"),
    ("/page/2/", "/archive/"), ("/2013/05/", "/archive/"), ("/2013/05/page/2/", "/archive/"),
    ("/2013/05/feed/", "/feed/"), ("/2012/feed", "/feed/"), ("/2012/feed/atom/", "/feed/"),
    ("/2013/05/feed/rss2/", "/feed/"), ("/2012/page/1/", "/archive/"), ("/2013/05/page/1", "/archive/"),
    ("/2012/1/", "/archive/"), ("/2012/1/2/", "/archive/"), ("/2012/01/2", "/archive/"), ("/2012/1/02/", "/archive/"),
    ("/author/samanthadegges/", "/about/"),
])
def test_feeds_and_listing_pages(built, old, new):
    assert follow(built, old) == (new, 301)
    assert exists(built, new)


# Every tag URL the old site had a post under, from WordPress.com's public API
# (public-api.wordpress.com/rest/v1.1/sites/hardlyfunny.com/tags, fetched 2026-10-05). The export
# kept only tag names, so this is what proves `wordpress_slug` rebuilds the real URLs.
WORDPRESS_TAG_SLUGS = {
    "antisocial", "api", "back-to-the-future", "beard", "caffeine", "chihuahua", "cloudsharing", "code",
    "computer", "couples", "date-night", "defcon", "django", "first-world-problems", "gaming", "github",
    "hacker", "hardware", "heroku", "hexadecimal", "home-life", "husband", "irc", "isp", "logic",
    "married-life", "memcache", "nerd", "nerd-alert", "non-technical", "number-generator", "office",
    "operating-system", "parking", "political", "priority", "programming", "randall", "random", "reddit",
    "religion", "samantha", "says", "scribbles-the-chihuahua", "servers", "tech-support", "technical",
    "telephony", "the-first-comic", "the-heroku-hackers-guide", "things-randall-says", "troubleshooting",
    "unix", "web-design", "windows", "working-from-home",
}

# Written out rather than derived, so a mistake shared by the generator and `old_urls` still fails.
# tests/test_cloudflare_runtime.py sends the same requests to a running server.
TAG_EXAMPLES = [
    ("/tag/gaming/", "/topics/gaming/"),
    ("/tag/working-from-home", "/topics/working-from-home/"),
    ("/tag/the-heroku-hackers-guide/feed/", "/topics/non-techie-wife/"),
    ("/tag/religion/feed/atom/", "/topics/holidays/"),
    ("/tag/code/page/3/", "/topics/working-from-home/"),
    ("/tag/web-design/", "/topics/dating-and-marriage/"),
    ("/tag/things-randall-says/", "/archive/"),
    ("/tag/home-life/page/2/", "/archive/"),
    ("/tag/married-life/feed/", "/archive/"),
    ("/tag/code/page/4/", "/archive/"),  # past the tag's last page: the catch-all
    ("/tag/1337/", "/archive/"),  # a tag the old site had with no posts
]


def test_wordpress_slug_rebuilds_every_old_tag_url():
    names = {t for c in ARCHIVED for t in c["tags"]}
    assert len(names) == len(WORDPRESS_TAG_SLUGS)
    assert {redirects.wordpress_slug(n) for n in names} == WORDPRESS_TAG_SLUGS


@pytest.mark.parametrize("old, new", TAG_EXAMPLES)
def test_old_tag_urls_land_on_their_topic_or_the_archive(built, old, new):
    assert follow(built, old) == (new, 301)
    assert exists(built, new)


def test_every_old_tag_lands_on_its_topic_or_the_archive(built, site):
    topic_of = {name: urls.topic(t) for t in site.topics for name in t.wordpress_tags}
    posts = Counter(t.casefold() for c in ARCHIVED for t in c["tags"])
    landed = Counter()
    for tag in {t for c in ARCHIVED for t in c["tags"]}:
        base = f"/tag/{redirects.wordpress_slug(tag)}/"
        dest = topic_of.get(tag.casefold(), urls.ARCHIVE)
        last = posts[tag.casefold()]
        for path in (base, base.rstrip("/"), base + "feed/", f"{base}page/{last}/"):
            assert follow(built, path) == (dest, 301), path
        assert exists(built, dest), dest
        assert follow(built, f"{base}page/{last + 1}/") == (urls.ARCHIVE, 301), base
        landed["topic" if dest != urls.ARCHIVE else "archive"] += 1
    assert landed["topic"] == len(topic_of) > 0 and landed["archive"] > 0, landed


def test_only_tags_a_topic_took_over_get_their_own_rules(built, site):
    expected = {redirects.wordpress_slug(n): urls.topic(t) for t in site.topics for n in t.wordpress_tags}
    got = {}
    for source, dest, _ in rules(built):
        if source.startswith("/tag/") and "*" not in source:
            assert got.setdefault(source.split("/")[2], dest) == dest, source
    assert got and got == expected


def _topic_with_tags(*names):
    return Topic(slug="t", title="T", intro_html="<p>An intro.</p>", wordpress_tags=names)


def test_tag_listings_cover_the_listing_its_feeds_and_one_page_per_post():
    rs = redirects._tag_listings((_topic_with_tags("back to the future"),),
                                 (("Back to the Future",), ("Back to the Future", "other")))
    base = "/tag/back-to-the-future"
    assert {r.source for r in rs} == {
        f"{base}/", base, f"{base}/feed/", f"{base}/feed", f"{base}/feed/atom/", f"{base}/feed/rss2/",
        f"{base}/page/1/", f"{base}/page/1", f"{base}/page/2/", f"{base}/page/2",
    }
    assert len(rs) == 10 and {r.destination for r in rs} == {"/topics/t/"} and not any(r.dynamic for r in rs)


@pytest.mark.parametrize("post, listed", [
    (("Web Design", "web-design"), "web design"),  # two tags, one URL: one of them really had another slug
    (("gaming",), "games"),                        # not a tag of the old site
    (("???",), "???"),                             # no slug at all
])
def test_tag_listings_refuse_a_tag_without_exactly_one_old_url(post, listed):
    with pytest.raises(ValueError, match="exactly one old /tag/ URL"):
        redirects._tag_listings((_topic_with_tags(listed),), (post,))


def test_no_rule_shadows_a_real_page(built):
    # Cloudflare applies _redirects even when a file exists at the path.
    for source, _, _ in rules(built):
        prefix = source[:-1] if source.endswith("*") else source
        hits = [p for p in built.rglob("*") if p.is_file() and ("/" + str(p.relative_to(built))).startswith(prefix)]
        if not source.endswith("*"):
            hits = [p for p in hits if re.fullmatch(re.escape(source.rstrip("/")) + r"(/index\.html)?", "/" + str(p.relative_to(built)))]
        assert not hits, f"{source} would shadow {hits[:3]}"


def test_new_urls_are_not_redirected(built, site):
    for path in ["/", urls.ARCHIVE, urls.ABOUT, urls.FEED, urls.TOPICS, *(urls.topic(t) for t in site.topics),
                 *(urls.comic(c) for c in site.comics)]:
        assert follow(built, path) == (None, None), path


def test_old_feed_url_is_the_feed_again(built):
    # WordPress subscribers poll /feed/; it must be served, not redirected, and /feed must be left
    # to Cloudflare's trailing-slash handling (a rule there would shadow feed/index.html).
    assert urls.FEED == "/feed/" and (built / urls.output_path(urls.FEED)).exists()
    assert follow(built, "/feed") == (None, None)


def test_no_two_rules_share_a_source(built):
    # With file order unreliable on the edge, two rules for one path would make the result a coin toss.
    sources = [source for source, _, _ in rules(built)]
    assert len(sources) == len(set(sources))


def test_no_year_catch_all(built):
    # `/2012/*` beat every post's own splat in production; it must not come back.
    assert not [s for s, _, _ in rules(built) if s.endswith("/*") and re.fullmatch(r"/\d{4}/\*", s)]


@pytest.mark.parametrize("period, spellings", [
    ("2012", ["2012"]),
    ("2012/01", ["2012/01", "2012/1"]),
    ("2012/10", ["2012/10"]),
    ("2012/12/20", ["2012/12/20"]),
    ("2012/01/02", ["2012/01/02", "2012/01/2", "2012/1/02", "2012/1/2"]),
    ("2012/11/05", ["2012/11/05", "2012/11/5"]),
])
def test_spellings_add_unpadded_months_and_days_once(period, spellings):
    assert redirects._spellings(period) == spellings


def test_date_archives_of_no_posts_is_empty():
    assert redirects._date_archives([]) == []


def test_date_archives_page_count_follows_posts_per_period():
    posts = ["/2012/01/02/a/", "/2012/01/02/b/", "/2012/03/04/c/"]
    sources = {r.source for r in redirects._date_archives(posts)}
    # Two posts on 2012/01/02, so pages 1 and 2 of that day, its month, and of the year (3 posts: 1..3).
    assert {"/2012/01/02/page/2/", "/2012/01/page/2/", "/2012/page/3/", "/2012/page/3"} <= sources
    assert not {"/2012/01/02/page/3/", "/2012/03/04/page/2/", "/2012/page/4/"} & sources
    # Dates with no post get nothing.
    assert not [s for s in sources if s.startswith(("/2012/02", "/2012/01/03", "/2013"))]


def test_date_archives_unpadded_spellings_get_only_the_listing():
    sources = {r.source for r in redirects._date_archives(["/2012/01/02/a/"])}
    assert {"/2012/1/2/", "/2012/1/2", "/2012/1/", "/2012/1"} <= sources
    assert not [s for s in sources if re.match(r"/2012/(1/|01/2(/|$)|1/02)", s) and ("feed" in s or "page" in s)]


def test_date_archives_are_order_independent():
    posts = [e["post"] for e in OLD]
    assert redirects._date_archives(posts) == redirects._date_archives(list(reversed(posts)))


def test_date_archives_send_listings_to_archive_and_feeds_to_feed():
    for r in redirects._date_archives([e["post"] for e in OLD]):
        assert r.destination == (urls.FEED if "/feed" in r.source else urls.ARCHIVE), r.source
        assert not r.dynamic, r.source


def _overlaps(prefixes):
    return any(a != b and b.startswith(a) for a in prefixes for b in prefixes)


def test_overlap_check_agrees_with_a_pairwise_check():
    # `_check_dynamic` only compares sorted neighbours; this proves that is enough, against every pair.
    import itertools
    import random

    rng = random.Random(0)
    segments = ["a", "a-b", "a0", "ab", "b"]
    paths = ["/" + "/".join(p) + "/" for n in (1, 2, 3) for p in itertools.product(segments, repeat=n)]
    for _ in range(3000):
        chosen = rng.sample(paths, rng.randint(2, 6))
        rs = [redirects.Redirect(p + "*", "/archive/") for p in chosen]
        if _overlaps(chosen):
            with pytest.raises(ValueError):
                redirects.render(rs)
        else:
            redirects.render(rs)


@pytest.mark.parametrize("sources", [
    ["/tag/*", "/tags/*"],
    ["/a/*", "/a-b/*", "/a0/*"],
    ["/page/*", "/author/samanthadegges/page/*"],
])
def test_render_accepts_sibling_splats_that_share_only_a_string_prefix(sources):
    redirects.render([redirects.Redirect(s, "/archive/") for s in sources])
