"""The built site as the Cloudflare runtime actually serves it (static assets, `_redirects`, `_headers`).

The rest of the suite checks `_redirects` with a Python model of Cloudflare's matching
(`test_redirects.follow`). This module replays the same paths against a running server, so a
difference between that model and the runtime fails here instead of in production. `cf dev`
is not enough on its own: it applied overlapping `_redirects` splats in file order while the
real edge did not, so run it against a deployed Worker too. It is skipped unless
HARDLYFUNNY_RUNTIME_URL is set:

    python -m hardlyfunny build
    npx cf dev                                   # in a Node container, serves _site on :8787
    HARDLYFUNNY_RUNTIME_URL=http://localhost:8787 python -m pytest tests/test_cloudflare_runtime.py
    HARDLYFUNNY_RUNTIME_URL=https://hardlyfunny.com python -m pytest tests/test_cloudflare_runtime.py

The server must serve a build of the same checkout the tests run from.
"""

import http.client
import os
import re
import threading
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlsplit

import pytest

from hardlyfunny import urls
from tests.test_redirects import OLD, VARIANTS, follow, old_urls, rules

BASE = os.environ.get("HARDLYFUNNY_RUNTIME_URL")
pytestmark = pytest.mark.skipif(not BASE, reason="set HARDLYFUNNY_RUNTIME_URL to a running `cf dev`")

SECURITY_HEADERS = {
    "x-content-type-options": "nosniff",
    "referrer-policy": "strict-origin-when-cross-origin",
    "x-frame-options": "SAMEORIGIN",
    "permissions-policy": "camera=(), microphone=(), geolocation=(), interest-cohort=()",
    # The same HSTS WordPress.com sent, so moving the domain doesn't weaken it.
    "strict-transport-security": "max-age=31536000",
}
IMMUTABLE = "public, max-age=31536000, immutable"


# Browser Integrity Check challenges requests without a User-Agent on proxied hosts.
HEADERS = {"User-Agent": "hardlyfunny-runtime-tests"}
_local = threading.local()


def _connect():
    parts = urlsplit(BASE)
    if parts.scheme == "https":
        return http.client.HTTPSConnection(parts.hostname, parts.port or 443, timeout=10)
    return http.client.HTTPConnection(parts.hostname, parts.port or 80, timeout=10)


def get(path):
    """One request, redirects not followed: (status, lower-cased headers, body).

    Reuses a keep-alive connection per thread: a fresh TLS handshake per request made the
    full suite take ~27 minutes against the real edge.
    """
    reused = getattr(_local, "conn", None) is not None
    try:
        return _send(path)
    except (http.client.HTTPException, ConnectionError, TimeoutError):
        _local.conn.close()
        _local.conn = None
        if not reused:
            raise
    # The server closed an idle connection; retry once on a fresh one.
    try:
        return _send(path)
    except (http.client.HTTPException, ConnectionError, TimeoutError):
        _local.conn.close()
        _local.conn = None
        raise


def _send(path):
    if getattr(_local, "conn", None) is None:
        _local.conn = _connect()
    _local.conn.request("GET", path, headers=HEADERS)
    res = _local.conn.getresponse()
    return res.status, {k.lower(): v for k, v in res.getheaders()}, res.read()


# Cloudflare Web Analytics, which the site keeps on, injects one beacon tag before </body> on
# every HTML page served on the zone. Strip exactly that, then compare bytes as before.
BEACON_HOST = b"static.cloudflareinsights.com"
BEACON = re.compile(rb'<script(?:\s+(?!src=)[\w-]+(?:="[^"]*"|=\'[^\']*\')?)*\s+src="https://static\.cloudflareinsights\.com/beacon\.min\.js[^"]*"[^>]*></script>\s*(?=</body>)')


def without_beacon(headers, body):
    """The body as the build wrote it: HTML may carry one beacon right before </body>, nothing else may."""
    count = body.count(BEACON_HOST)
    if not headers.get("content-type", "").startswith("text/html"):
        assert count == 0, f"analytics in a non-HTML response ({headers.get('content-type')})"
        return body
    assert count <= 1, f"{count} analytics references in one page"
    return BEACON.sub(b"", body, count=1)


def location(headers):
    """Location as a path, whether the runtime sends it relative or absolute."""
    loc = urlsplit(headers.get("location", ""))
    return loc.path + (f"?{loc.query}" if loc.query else "")


def assert_lands(path, dest):
    """`path` 301s straight to `dest`, and `dest` is a page (no second hop)."""
    status, headers, _ = get(path)
    assert (status, location(headers)) == (301, dest), path
    status, _, _ = get(dest)
    assert status == 200, f"{path} -> {dest} -> {status}"


def assert_all_land(pairs):
    """`assert_lands` for every (path, dest), 8 at a time, reporting every failure at once."""
    def check(pair):
        try:
            assert_lands(*pair)
        except AssertionError as e:
            return f"{pair[0]}: {e}"
    with ThreadPoolExecutor(max_workers=8) as pool:
        failures = [f for f in pool.map(check, pairs) if f]
    assert not failures, f"{len(failures)} of {len(pairs)} failed:\n" + "\n".join(failures[:20])


def test_runtime_serves_the_same_build(built):
    """Guards every other test: a stale `_site` behind the server would make them meaningless."""
    status, _, body = get("/_redirects")
    assert status == 404
    status, headers, body = get(urls.FEED)
    assert status == 200 and without_beacon(headers, body) == (built / urls.output_path(urls.FEED)).read_bytes()


def test_feed_is_served_as_atom_without_the_beacon(built):
    # The feed is built as feed/index.html. If the _headers override ever failed, the edge would send
    # it as HTML and add the beacon, which without_beacon would quietly strip, so check the raw response.
    status, headers, body = get(urls.FEED)
    assert status == 200
    assert headers["content-type"] == "application/atom+xml; charset=utf-8"
    assert BEACON_HOST not in body
    assert body == (built / urls.output_path(urls.FEED)).read_bytes()


def test_every_static_rule_matches_the_python_model(built):
    pairs = [(source, dest) for source, dest, _ in rules(built) if "*" not in source]
    for source, dest in pairs:
        assert follow(built, source) == (dest, 301)
    assert_all_land(pairs)


def test_every_splat_rule_matches_the_python_model(built):
    paths = [path for source, _, _ in rules(built) if source.endswith("/*")
             for path in (source[:-1] + "anything/deeper/", source[:-1])]
    assert_all_land([(path, follow(built, path)[0]) for path in paths])


@pytest.mark.parametrize("variant", VARIANTS)
def test_every_old_post_url_lands_on_its_comic(built, site, variant):
    assert_all_land([(VARIANTS[variant](entry["post"]), urls.comic(site.comics[entry["number"] - 1])) for entry in OLD])


def test_every_old_url_lands_on_a_real_page(site):
    assert_all_land(list(old_urls(site).items()))


def test_redirects_keep_the_query_string():
    status, headers, _ = get("/feed.xml?utm_source=x")
    assert (status, location(headers)) == (301, "/feed/?utm_source=x")
    status, _, _ = get("/feed/?utm_source=x")
    assert status == 200


def test_new_urls_are_pages_with_security_headers(site):
    for path in ["/", urls.ARCHIVE, urls.ABOUT, urls.RANDOM, urls.TOPICS, *(urls.topic(t) for t in site.topics),
                 *(urls.comic(c) for c in site.comics)]:
        status, headers, _ = get(path)
        assert status == 200, path
        assert headers["content-type"].startswith("text/html"), path
        assert {k: headers.get(k) for k in SECURITY_HEADERS} == SECURITY_HEADERS, path


def test_slashless_page_urls_reach_the_page():
    # auto-trailing-slash: /about must not 404 now that Pages' own handling is gone.
    for path in ["/about", "/archive", "/comics/infinite-recursion", "/feed"]:
        status, headers, _ = get(path)
        assert status in (301, 307, 308) and location(headers) == path + "/", path


@pytest.mark.parametrize("path", ["/nope/", "/comics/no-such-comic/", "/_redirects", "/_headers",
                                  "/wrangler.config.ts", "/cloudflare.config.ts", "/package.json"])
def test_missing_and_config_paths_get_the_site_404(built, path):
    status, headers, body = get(path)
    assert status == 404, path
    assert without_beacon(headers, body) == (built / "404.html").read_bytes(), path
    assert {k: headers.get(k) for k in SECURITY_HEADERS} == SECURITY_HEADERS, path


def test_cache_and_content_type_rules_apply(built):
    font = next((built / "fonts").iterdir()).name
    image = next(p for p in (built / "images").rglob("*") if p.is_file()).relative_to(built)
    expected = {
        "/site.css?v=abc": IMMUTABLE,
        "/site.js": IMMUTABLE,
        f"/fonts/{font}": IMMUTABLE,
        f"/{image}": "public, max-age=604800",
    }
    for path, cache in expected.items():
        status, headers, _ = get(path)
        assert (status, headers.get("cache-control")) == (200, cache), path
    status, headers, _ = get("/")
    assert "immutable" not in headers.get("cache-control", ""), "HTML must not be cached forever"
    # Exact value measured on workers.dev; a zone setting like Browser Cache TTL could change it on the domain.
    assert headers.get("cache-control") == "public, max-age=0, must-revalidate"
    status, headers, _ = get(urls.FEED)
    assert headers["content-type"] == "application/atom+xml; charset=utf-8"


def test_robots_txt_is_the_one_the_build_writes(built):
    # A zone's managed robots.txt would replace ours on the custom domain.
    status, headers, body = get("/robots.txt")
    assert (status, without_beacon(headers, body)) == (200, (built / "robots.txt").read_bytes())


def test_sitemap_xml_is_the_one_the_build_writes(built):
    # Search engines find the comic images through it, so a stale sitemap hides new ones.
    status, headers, body = get(urls.SITEMAP)
    assert (status, without_beacon(headers, body)) == (200, (built / urls.output_path(urls.SITEMAP)).read_bytes())


def test_build_marker_is_not_published():
    status, _, _ = get("/.hardlyfunny-build")
    assert status == 404


def test_every_splat_prefix_without_its_slash_matches_the_python_model(built):
    # `follow` says `/x/*` also matches `/x`. Nothing else checks that claim against the runtime,
    # and every other test trusts `follow` for what the edge does.
    failures = []
    for source, _, _ in rules(built):
        path = source[:-2]
        if source.endswith("/*") and not any(s == path for s, _, _ in rules(built)):
            dest, _ = follow(built, path)
            status, headers, _ = get(path)
            got = (status, location(headers) or None)
            if got != ((301, dest) if dest else (404, None)):
                failures.append(f"{path}: model says {dest or 404}, runtime gave {got}")
    assert not failures, "\n".join(failures)


@pytest.mark.parametrize("path", ["/2012/99/", "/2012/01/02/no-such-post/", "/2015/", "/2012/01/03/",
                                  "/2012/page/999/", "/wp-login.php", "/xmlrpc.php", "/ads.txt"])
def test_paths_wordpress_never_served_get_the_site_404(built, path):
    status, headers, body = get(path)
    assert status == 404, path
    assert without_beacon(headers, body) == (built / "404.html").read_bytes(), path
