"""`python -m hardlyfunny serve`: the local server must send the feed the way the edge does.

The feed is built as feed/index.html so Cloudflare serves it at /feed/, and `_headers` makes it
Atom there. Locally, the stock handler would guess text/html from the file name; a feed reader
pointed at the dev server would then see a web page. This pins the override and its scope.
"""

import http.client
import sys
import threading
from http.server import ThreadingHTTPServer
from types import SimpleNamespace

import pytest

from hardlyfunny import __main__ as cli
from hardlyfunny import urls

ATOM = "application/atom+xml; charset=utf-8"


@pytest.fixture(scope="module")
def server(built):
    class Quiet(cli.Handler):
        def log_message(self, *args):
            pass

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), lambda *a: Quiet(*a, directory=str(built)))
    httpd.daemon_threads = True
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield httpd.server_address[1]
    httpd.shutdown()
    httpd.server_close()


def fetch(port, path, method="GET"):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    try:
        conn.request(method, path)
        r = conn.getresponse()
        return r.status, {k.lower(): v for k, v in r.getheaders()}, r.read()
    finally:
        conn.close()


@pytest.mark.parametrize("path", [urls.FEED, urls.FEED + "index.html", urls.FEED + "?utm_source=x"])
def test_feed_is_served_as_atom(server, built, path):
    status, headers, body = fetch(server, path)
    assert status == 200, path
    assert headers["content-type"] == ATOM, path
    assert body == (built / urls.output_path(urls.FEED)).read_bytes()


def test_feed_head_request_is_atom_too(server):
    # Feed readers and link checkers often probe with HEAD first.
    status, headers, body = fetch(server, urls.FEED, method="HEAD")
    assert (status, headers["content-type"], body) == (200, ATOM, b"")


def test_slashless_feed_redirects_to_the_feed(server):
    status, headers, _ = fetch(server, urls.FEED.rstrip("/"))
    assert status == 301 and headers["location"] == urls.FEED


@pytest.mark.parametrize("path", [urls.HOME, urls.ARCHIVE, urls.ABOUT, "/comics/infinite-recursion/", "/404.html"])
def test_other_index_pages_stay_html(server, path):
    # The override must match the feed file only, not every index.html.
    status, headers, _ = fetch(server, path)
    assert status == 200, path
    assert headers["content-type"].startswith("text/html"), (path, headers["content-type"])


@pytest.mark.parametrize("path, prefix", [("/site.css", "text/css"), ("/robots.txt", "text/plain"),
                                          (urls.SITEMAP, ("application/xml", "text/xml"))])
def test_other_files_keep_their_normal_types(server, path, prefix):
    status, headers, _ = fetch(server, path)
    assert status == 200 and headers["content-type"].startswith(prefix), (path, headers["content-type"])


def test_dot_segments_cannot_dodge_or_borrow_the_feed_type(server, built):
    # translate_path normalises the path before guess_type sees it, so these still reach the right file.
    status, headers, body = fetch(server, "/about/../feed/")
    assert (status, headers["content-type"]) == (200, ATOM)
    status, headers, _ = fetch(server, "/feed/../about/")
    assert status == 200 and headers["content-type"].startswith("text/html")


def test_serve_command_hands_the_server_this_handler_bound_to_out(monkeypatch, tmp_path):
    # Wiring, without building or binding a real port: main() must not fall back to the stock handler.
    seen = {}

    class FakeServer:
        def __init__(self, address, handler):
            seen["address"], seen["handler"] = address, handler

        def serve_forever(self):
            seen["served"] = True

    monkeypatch.setattr(cli, "build", lambda out, site_url, portable: SimpleNamespace(comics=[]))
    monkeypatch.setattr(cli.http.server, "ThreadingHTTPServer", FakeServer)
    monkeypatch.setattr(sys, "argv", ["hardlyfunny", "serve", "--out", str(tmp_path), "--port", "8123"])
    cli.main()
    assert seen["served"] and seen["address"] == ("", 8123)
    assert seen["handler"].func is cli.Handler
    assert seen["handler"].keywords == {"directory": str(tmp_path)}
