"""The production domain's edge: www goes to the naked domain, and http goes to https.

Only meaningful against the real custom domain, so it skips for `cf dev` (localhost) and
*.workers.dev. The www redirect is a zone Single Redirect rule, not part of `_redirects`.
"""

import http.client
import os
from urllib.parse import urljoin, urlsplit

import pytest

BASE = os.environ.get("HARDLYFUNNY_RUNTIME_URL", "")
HOST = urlsplit(BASE).hostname or ""
pytestmark = pytest.mark.skipif(
    urlsplit(BASE).scheme != "https" or HOST in ("localhost", "127.0.0.1") or HOST.endswith(".workers.dev"),
    reason="set HARDLYFUNNY_RUNTIME_URL to the https custom domain",
)

HEADERS = {"User-Agent": "hardlyfunny-runtime-tests"}
OLD_POST = "/2013/05/15/infinite-recursion/"


def head(url):
    """One request, redirects not followed: (status, raw Location header)."""
    parts = urlsplit(url)
    cls = http.client.HTTPSConnection if parts.scheme == "https" else http.client.HTTPConnection
    conn = cls(parts.hostname, timeout=10)
    try:
        conn.request("GET", parts.path + (f"?{parts.query}" if parts.query else ""), headers=HEADERS)
        res = conn.getresponse()
        res.read()
        return res.status, res.getheader("location")
    finally:
        conn.close()


def test_www_goes_to_the_naked_domain_keeping_path_and_query():
    assert head(f"https://www.{HOST}{OLD_POST}?q=1") == (301, f"https://{HOST}{OLD_POST}?q=1")


def test_http_www_reaches_the_naked_https_url_in_two_hops_at_most():
    url, hops = f"http://www.{HOST}{OLD_POST}?q=1", 0
    while hops < 2:
        status, location = head(url)
        assert status in (301, 308), f"{url} -> {status}"
        url, hops = urljoin(url, location), hops + 1
        if url == f"https://{HOST}{OLD_POST}?q=1":
            return
    pytest.fail(f"http://www.{HOST}{OLD_POST}?q=1 ended at {url} after {hops} hops")


def test_http_goes_to_https():
    assert head(f"http://{HOST}/x") == (301, f"https://{HOST}/x")


WORKERS_DEV = "https://hardlyfunny.randall-degges.workers.dev/"


def test_workers_dev_does_not_serve_a_second_copy_of_the_site():
    parts = urlsplit(WORKERS_DEV)
    conn = http.client.HTTPSConnection(parts.hostname, timeout=10)
    try:
        conn.request("GET", parts.path, headers=HEADERS)
        res = conn.getresponse()
        body = res.read()
    finally:
        conn.close()
    assert res.status == 404, WORKERS_DEV
    assert b"Hardly Funny" not in body, "workers.dev serves a site page"
