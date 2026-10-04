"""The runtime suite's HTTP client (`get`, `assert_all_land`) against local fake servers.

The runtime tests only prove the edge is right if their client neither hides failures nor
mixes up responses. Keep-alive reuse, the retry, and the thread pool are each a way to get
that wrong, and none of it runs unless HARDLYFUNNY_RUNTIME_URL is set, so it's pinned here.
"""

import http.client
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from tests import test_cloudflare_runtime as rt


class Server(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, handler):
        super().__init__(("127.0.0.1", 0), handler)
        self.connections = 0
        self.requests = []
        self.lock = threading.Lock()


class Handler(BaseHTTPRequestHandler):
    """`/from/<x>` 301s to `/to/<x>`, `/to/<x>` is a page whose body names it, `/500` errors."""

    protocol_version = "HTTP/1.1"  # keep-alive, like the edge
    close_after_each = False  # drop the connection without `Connection: close`, as idle timeouts do

    def setup(self):
        super().setup()
        with self.server.lock:
            self.server.connections += 1

    def log_message(self, *args):
        pass

    def do_GET(self):
        with self.server.lock:
            self.server.requests.append(self.path)
        if self.path.startswith("/from/"):
            self.reply(301, b"", {"Location": "/to/" + self.path[len("/from/"):]})
        elif self.path.startswith("/to/") and not self.path.endswith("/missing"):
            self.reply(200, self.path.encode())
        else:
            self.reply(int(self.path[1:]) if self.path[1:].isdigit() else 404, b"nope")
        if self.close_after_each:
            self.close_connection = True

    def reply(self, status, body, headers=()):
        self.send_response(status)
        for k, v in dict(headers).items():
            self.send_header(k, v)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


@pytest.fixture
def serve(monkeypatch):
    """Start a fake runtime and point the client at it, with no connection left over from other tests."""
    servers = []

    def start(handler=Handler):
        server = Server(handler)
        threading.Thread(target=server.serve_forever, args=(0.05,), daemon=True).start()
        servers.append(server)
        monkeypatch.setattr(rt, "BASE", f"http://127.0.0.1:{server.server_address[1]}")
        return server

    monkeypatch.setattr(rt._local, "conn", None, raising=False)
    yield start
    for server in servers:
        server.shutdown()
        server.server_close()


def test_get_reuses_one_connection_per_thread(serve):
    server = serve()
    for i in range(5):
        status, _, body = rt.get(f"/to/{i}")
        assert (status, body) == (200, f"/to/{i}".encode())
    assert server.connections == 1


def test_get_recovers_when_the_server_drops_an_idle_connection(serve):
    class Dropping(Handler):
        close_after_each = True

    server = serve(Dropping)
    for i in range(5):
        status, _, body = rt.get(f"/to/{i}")
        assert (status, body) == (200, f"/to/{i}".encode())
    assert server.requests == [f"/to/{i}" for i in range(5)]  # each request answered exactly once
    assert server.connections == 5


def test_get_raises_when_the_server_never_answers(serve):
    # A runtime that hangs up on every request must fail the test, not be retried into a pass.
    class HangUp(Handler):
        def handle(self):
            self.request.close()

    server = serve(HangUp)
    with pytest.raises((http.client.HTTPException, ConnectionError)):
        rt.get("/to/x")
    assert server.connections == 1  # a fresh connection that fails is not retried


def test_get_raises_when_nothing_listens(serve, monkeypatch):
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    monkeypatch.setattr(rt, "BASE", f"http://127.0.0.1:{port}")
    with pytest.raises(ConnectionRefusedError):
        rt.get("/")


def test_get_returns_error_statuses_without_retrying(serve):
    server = serve()
    assert rt.get("/500")[0] == 500
    assert server.requests == ["/500"]


def test_get_sends_a_user_agent(serve):
    seen = []

    class Recording(Handler):
        def do_GET(self):
            seen.append(self.headers.get("User-Agent"))
            super().do_GET()

    serve(Recording)
    rt.get("/to/x")
    assert seen == [rt.HEADERS["User-Agent"]]


def test_assert_all_land_passes_when_every_path_lands(serve):
    server = serve()
    pairs = [(f"/from/{i}", f"/to/{i}") for i in range(200)]
    rt.assert_all_land(pairs)
    assert sorted(server.requests) == sorted(p for pair in pairs for p in pair)


def test_assert_all_land_never_crosses_responses_between_threads(serve, monkeypatch):
    # Every 301 names its own path, so a connection shared between threads would hand one
    # request another's Location and fail here. The retry turns http.client's own
    # "connection busy" errors into fresh attempts, so check the ownership directly too.
    server = serve()
    seen = []
    owners = {}
    real = rt.get

    def checked(path):
        status, headers, body = real(path)
        owners.setdefault(id(rt._local.conn), set()).add(threading.get_ident())
        seen.append((path, status, headers.get("location"), body))
        return status, headers, body

    monkeypatch.setattr(rt, "get", checked)
    rt.assert_all_land([(f"/from/{i}", f"/to/{i}") for i in range(400)])
    for path, status, loc, body in seen:
        if path.startswith("/from/"):
            assert (status, loc) == (301, "/to/" + path[len("/from/"):]), path
        else:
            assert (status, body) == (200, path.encode()), path
    assert len(seen) == 800
    assert all(len(threads) == 1 for threads in owners.values()), "a connection was used by two threads"
    assert server.connections <= 8, "one keep-alive connection per worker"
    assert len(server.requests) == 800, "no request needed a retry"


def test_assert_all_land_reports_every_failure_not_just_the_first(serve):
    serve()
    pairs = [(f"/from/{i}", f"/to/{i}") for i in range(50)]
    pairs[3] = ("/from/3", "/to/wrong")  # redirects somewhere else
    pairs[17] = ("/from/missing", "/to/missing")  # lands on a 404
    pairs[40] = ("/nowhere", "/to/40")  # doesn't redirect at all
    with pytest.raises(AssertionError) as e:
        rt.assert_all_land(pairs)
    msg = str(e.value)
    assert msg.startswith("3 of 50 failed:")
    assert "/from/3:" in msg and "/from/missing:" in msg and "/nowhere:" in msg
    assert "-> 404" in msg


def test_assert_all_land_does_not_swallow_connection_errors(serve, monkeypatch):
    # Only assertion failures are collected; a broken runtime must still error the test.
    serve()

    def broken(path):
        raise ConnectionResetError("runtime went away")

    monkeypatch.setattr(rt, "get", broken)
    with pytest.raises(ConnectionResetError):
        rt.assert_all_land([("/from/1", "/to/1")])


def test_assert_all_land_stops_once_the_runtime_stops_answering(serve, monkeypatch):
    # Against a runtime that accepts connections but never answers, each `get` costs one
    # 10s timeout. If the pool kept draining its queue after the first error, the 2,316-URL
    # test would hang ~1.6 hours before failing; `map` cancels the queued pairs instead.
    serve()
    calls = []

    def hung(path):
        calls.append(path)
        time.sleep(0.01)
        raise TimeoutError("timed out")

    monkeypatch.setattr(rt, "get", hung)
    with pytest.raises(TimeoutError):
        rt.assert_all_land([(f"/from/{i}", f"/to/{i}") for i in range(200)])
    assert len(calls) < 100, f"{len(calls)} requests sent after the runtime stopped answering"


# The beacon Cloudflare Web Analytics injected on the rehearsal domain (2026-10-04).
BEACON_TAG = (b'<script type="module" src="https://static.cloudflareinsights.com/beacon.min.js/v31edd6df95cf4e85bb4c19e7a9bdbcba1788362987495" '
              b'integrity="sha512-x" data-cf-beacon=\'{"version":"2024.11.0","token":"t","r":1,"spa":2}\' crossorigin="anonymous"></script>\n')
PAGE = b'<!doctype html>\n<p>hi</p>\n<script src="/site.js?v=1" defer></script>\n</body>\n</html>\n'
HTML = {"content-type": "text/html"}


def with_beacon(page, tag=BEACON_TAG):
    return page.replace(b"</body>", tag + b"</body>")


def test_without_beacon_removes_the_one_cloudflare_injects():
    assert rt.without_beacon(HTML, with_beacon(PAGE)) == PAGE


def test_without_beacon_leaves_a_page_without_one_alone():
    assert rt.without_beacon(HTML, PAGE) == PAGE


def test_without_beacon_rejects_two_beacons():
    with pytest.raises(AssertionError):
        rt.without_beacon(HTML, with_beacon(with_beacon(PAGE)))


def test_without_beacon_keeps_a_beacon_anywhere_but_right_before_body_end():
    elsewhere = PAGE.replace(b"<p>hi</p>", BEACON_TAG + b"<p>hi</p>")
    assert rt.without_beacon(HTML, elsewhere) != PAGE


def test_without_beacon_rejects_analytics_outside_html():
    with pytest.raises(AssertionError):
        rt.without_beacon({"content-type": "application/atom+xml"}, b"<feed>" + BEACON_TAG + b"</feed>")
    assert rt.without_beacon({"content-type": "text/plain"}, b"User-agent: *\n") == b"User-agent: *\n"
