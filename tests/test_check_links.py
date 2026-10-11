"""The link checker's rules, without touching the network."""

import importlib.util
import json
import math
import re
import socket
import sys
import threading
import time
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


def test_mailto_links_are_not_fetched(tmp_path):
    content = tmp_path / "comics.json"
    about = '<a href="mailto:someone@example.com?subject=Hi">Ask</a> <a href="https://example.com/">Site</a>'
    content.write_text(json.dumps({"site": {"about_html": about}, "comics": []}), encoding="utf-8")
    assert [l.url for l in check_links.extract(content)] == ["https://example.com/"]


def test_broken_links_fail_the_run(monkeypatch):
    fake = {"https://ok.example/": (200, None), "https://gone.example/": (404, None), "https://blocked.example/": (403, None)}
    monkeypatch.setattr(check_links, "extract", lambda: [check_links.Link("#1 Test", u) for u in fake])
    monkeypatch.setattr(check_links, "fetch", lambda url: fake[url])
    monkeypatch.setattr(check_links.time, "sleep", lambda s: None)
    assert check_links.main() == 1
    del fake["https://gone.example/"]
    assert check_links.main() == 0  # a bot-blocked link warns but doesn't fail


def test_a_hung_link_warns_instead_of_stalling_the_run(monkeypatch):
    stuck = threading.Event()

    def hang(url):
        stuck.wait()
        return 200, None

    monkeypatch.setattr(check_links, "fetch", hang)
    link = check_links.Link("#23 W.o.W.", "http://www.ubuntu.com/")
    try:
        assert check_links.check_within(link, deadline=0.2) == check_links.Result(link, "warn", "no answer in 0.2s")
    finally:
        stuck.set()


@pytest.fixture
def hung_fetch(monkeypatch):
    """fetch() that never answers until the test ends, then lets the leaked threads go."""
    release = threading.Event()

    def hang(url):
        release.wait()
        return 200, None

    monkeypatch.setattr(check_links, "fetch", hang)
    monkeypatch.setattr(check_links.time, "sleep", lambda s: None)
    yield hang
    release.set()


def short_deadline(monkeypatch, seconds):
    # check_within binds DEADLINE as a default at import, so patching the constant does nothing.
    monkeypatch.setattr(check_links.check_within, "__defaults__", (seconds,))


def run_main(limit=10):
    # Runs main() on a daemon thread so a regression fails here instead of hanging the suite.
    exit_code = []
    worker = threading.Thread(target=lambda: exit_code.append(check_links.main()), daemon=True)
    worker.start()
    worker.join(limit)
    assert exit_code, f"main() still running after {limit}s"
    return exit_code[0]


def test_a_quick_answer_does_not_wait_for_the_deadline(monkeypatch):
    monkeypatch.setattr(check_links, "fetch", lambda url: (404, None))
    link = check_links.Link("#1 Test", "https://gone.example/")
    started = time.monotonic()
    assert check_links.check_within(link, deadline=30) == check_links.Result(link, "fail", "404 (page is gone)")
    assert time.monotonic() - started < 5


def test_a_hung_link_only_warns_and_a_broken_one_still_fails_the_run(monkeypatch, hung_fetch, capsys):
    answers = {"https://ok.example/": (200, None), "https://gone.example/": (404, None)}
    hung = "http://www.ubuntu.com/"
    monkeypatch.setattr(check_links, "fetch", lambda url: answers[url] if url in answers else hung_fetch(url))
    monkeypatch.setattr(check_links, "extract", lambda: [check_links.Link("#1 Test", u) for u in [*answers, hung]])
    short_deadline(monkeypatch, 0.2)

    assert run_main() == 1
    out = capsys.readouterr().out
    assert any(line.startswith("WARN") and "no answer in 0.2s" in line and hung in line for line in out.splitlines())
    assert "3 links: 1 broken, 1 couldn't be verified." in out

    del answers["https://gone.example/"]
    assert run_main() == 0  # the hung link alone must not fail the run


def test_hung_links_are_timed_out_in_parallel(monkeypatch, hung_fetch):
    links = [check_links.Link("#1 Test", f"https://hung{i}.example/") for i in range(32)]
    monkeypatch.setattr(check_links, "extract", lambda: links)
    short_deadline(monkeypatch, 0.3)
    started = time.monotonic()
    assert run_main() == 0
    assert time.monotonic() - started < 3  # serially this would take 32 x 0.3 s = 9.6 s


def test_every_real_link_hanging_still_fits_the_job_timeout(monkeypatch, hung_fetch):
    # Measures how many DEADLINE rounds main() needs for today's links, then scales that to the
    # real DEADLINE. Fails when the link count outgrows the worker pool, before CI starts timing out.
    workflow = (ROOT / ".github" / "workflows" / "links.yml").read_text(encoding="utf-8")
    job_minutes = int(re.search(r"timeout-minutes:\s*(\d+)", workflow).group(1))
    probe = 0.2
    short_deadline(monkeypatch, probe)
    started = time.monotonic()
    assert run_main() == 0
    rounds = math.ceil((time.monotonic() - started) / probe - 0.25)
    setup_allowance = 120  # checkout and setup-python
    assert rounds * check_links.DEADLINE + setup_allowance < job_minutes * 60, \
        f"{rounds} rounds of {check_links.DEADLINE}s won't fit in {job_minutes} min"


@pytest.mark.filterwarnings("ignore::pytest.PytestUnhandledThreadExceptionWarning")
@pytest.mark.xfail(strict=False, reason="PROPOSED CONTRACT: a crash inside check() is reported as a 60 s timeout")
def test_proposed_contract_a_crash_is_not_reported_as_a_timeout(monkeypatch):
    def boom(url):
        raise RuntimeError("bug in the checker")

    monkeypatch.setattr(check_links, "check", lambda link: boom(link.url))
    link = check_links.Link("#1 Test", "https://ok.example/")
    started = time.monotonic()
    try:
        result = check_links.check_within(link, deadline=30)
    except RuntimeError:
        return  # re-raising, as main() did before check_within, is fine
    assert time.monotonic() - started < 5  # the dead worker must not cost the full deadline
    assert "no answer" not in result.detail
