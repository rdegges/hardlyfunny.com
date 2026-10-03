"""The link checker's rules, without touching the network."""

import importlib.util
import socket
import sys
import urllib.error

import pytest

from hardlyfunny.build import ROOT

spec = importlib.util.spec_from_file_location("check_links", ROOT / "scripts" / "check_links.py")
check_links = importlib.util.module_from_spec(spec)
sys.modules["check_links"] = check_links  # dataclasses look their module up here
spec.loader.exec_module(check_links)


@pytest.mark.parametrize("status, outcome", [
    (200, "ok"), (301, "ok"),
    (404, "fail"), (410, "fail"), (400, "fail"),
    (403, "warn"), (429, "warn"), (999, "warn"),  # bot blocking / rate limits
    (500, "warn"), (503, "warn"),  # server trouble may be temporary
])
def test_statuses(status, outcome):
    assert check_links.classify(status)[0] == outcome


def test_dead_domains_fail_but_flaky_connections_only_warn():
    dns = urllib.error.URLError(socket.gaierror(-2, "Name or service not known"))
    assert check_links.classify(None, dns) == ("fail", "domain doesn't resolve")
    assert check_links.classify(None, urllib.error.URLError(ConnectionRefusedError()))[0] == "fail"
    assert check_links.classify(None, TimeoutError())[0] == "warn"


def test_redirect_loops_fail():
    loop = urllib.error.HTTPError("http://x", 302, "The HTTP server returned a redirect error that would lead to an infinite loop", {}, None)
    assert check_links.classify(None, loop)[0] == "fail"


def test_extracts_every_external_link_from_notes_and_about():
    links = check_links.extract()
    assert len(links) >= 30
    assert all(l.url.startswith(("http://", "https://")) for l in links)
    assert any("web.archive.org" in l.url for l in links)


def test_broken_links_fail_the_run(monkeypatch):
    fake = {"https://ok.example/": (200, None), "https://gone.example/": (404, None), "https://blocked.example/": (403, None)}
    monkeypatch.setattr(check_links, "extract", lambda: [check_links.Link("#1 Test", u) for u in fake])
    monkeypatch.setattr(check_links, "fetch", lambda url: fake[url])
    monkeypatch.setattr(check_links.time, "sleep", lambda s: None)
    assert check_links.main() == 1
    del fake["https://gone.example/"]
    assert check_links.main() == 0  # a bot-blocked link warns but doesn't fail
