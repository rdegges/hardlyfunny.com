#!/usr/bin/env python3
"""Check every external link in the comic notes and the About page.

    python3 scripts/check_links.py

Exits 1 when a link is definitely broken (404/410, a domain that no longer
resolves, other client errors), so CI fails before a broken link ships. Links a
script can't verify are reported as warnings instead of failures: sites like
Reddit and news sites answer automated requests with 403s, bot challenges or rate
limits while working fine in a browser, and servers have bad days.

When a link dies, replace it with an Internet Archive snapshot taken near the
comic's date: https://archive.org/wayback/available?url=<url>&timestamp=<YYYYMMDD>
"""

from __future__ import annotations

import json
import os
import re
import socket
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15"
TIMEOUT = 30
ATTEMPTS = 3

# Statuses that mean "a script can't tell", not "the page is gone".
UNVERIFIABLE = {401, 403, 405, 406, 418, 429, 451, 999}


@dataclass(frozen=True)
class Link:
    where: str  # e.g. "#57 Waza" or "About"
    url: str


@dataclass(frozen=True)
class Result:
    link: Link
    outcome: str  # "ok", "warn" or "fail"
    detail: str


def extract(content_path: Path = ROOT / "content" / "comics.json") -> list[Link]:
    data = json.loads(content_path.read_text(encoding="utf-8"))
    found = [Link(f"#{c['number']} {c['title']}", h)
             for c in data["comics"] for h in re.findall(r'href="([^"]+)"', c["note_html"])]
    found += [Link("About", h) for h in re.findall(r'href="([^"]+)"', data["site"]["about_html"])]
    return [l for l in found if l.url.startswith(("http://", "https://"))]


def classify(status: int | None, error: BaseException | None = None) -> tuple[str, str]:
    """Turn an HTTP status or a network error into (outcome, detail)."""
    if error is not None:
        reason = getattr(error, "reason", error)
        if isinstance(reason, socket.gaierror):
            return "fail", "domain doesn't resolve"
        if isinstance(reason, ConnectionRefusedError):
            return "fail", "connection refused"
        if isinstance(error, urllib.error.HTTPError) and "redirect" in str(error).lower():
            return "fail", "redirect loop"
        return "warn", f"couldn't connect ({type(reason).__name__})"
    if status is None:
        return "warn", "no response"
    if status < 400:
        return "ok", str(status)
    if status in (404, 410):
        return "fail", f"{status} (page is gone)"
    if status in UNVERIFIABLE:
        return "warn", f"{status} (site blocks automated checks; check it in a browser)"
    if status >= 500:
        return "warn", f"{status} (server error; may be temporary)"
    return "fail", str(status)


def fetch(url: str) -> tuple[int | None, BaseException | None]:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "text/html,*/*"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            return resp.status, None
    except urllib.error.HTTPError as e:
        if e.code and 400 <= e.code < 600:
            return e.code, None
        return None, e  # a 3xx raised as an error is a redirect loop
    except Exception as e:  # DNS failure, timeout, TLS, refused…
        return None, e


def check(link: Link) -> Result:
    outcome, detail = "warn", "not checked"
    for attempt in range(ATTEMPTS):
        status, error = fetch(link.url)
        outcome, detail = classify(status, error)
        if outcome == "ok" or (outcome == "fail" and detail != "connection refused"):
            break  # definite answers don't need retries
        time.sleep(2 * (attempt + 1))
    return Result(link, outcome, detail)


def report(results: list[Result]) -> None:
    in_actions = os.environ.get("GITHUB_ACTIONS") == "true"
    for r in results:
        label = {"ok": "ok  ", "warn": "WARN", "fail": "FAIL"}[r.outcome]
        print(f"{label} {r.detail:>58}  {r.link.where}: {r.link.url}")
        if in_actions and r.outcome != "ok":
            kind = "error" if r.outcome == "fail" else "warning"
            print(f"::{kind} file=content/comics.json,title=Link {r.outcome}: {r.link.where}::{r.link.url} → {r.detail}")
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        rows = [r for r in results if r.outcome != "ok"]
        lines = ["## Link check", "",
                 f"{sum(r.outcome == 'ok' for r in results)} ok, "
                 f"{sum(r.outcome == 'warn' for r in results)} warnings, "
                 f"{sum(r.outcome == 'fail' for r in results)} broken", ""]
        if rows:
            lines += ["| | Where | Link | Result |", "| --- | --- | --- | --- |"]
            lines += [f"| {'❌' if r.outcome == 'fail' else '⚠️'} | {r.link.where} | {r.link.url} | {r.detail} |" for r in rows]
        with open(summary, "a", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")


def main() -> int:
    links = extract()
    unique = {l.url: l for l in links}  # check each URL once
    with ThreadPoolExecutor(max_workers=8) as pool:
        by_url = {r.link.url: r for r in pool.map(check, unique.values())}
    results = [Result(l, by_url[l.url].outcome, by_url[l.url].detail) for l in links]
    report(results)
    broken = sum(r.outcome == "fail" for r in results)
    warned = sum(r.outcome == "warn" for r in results)
    print(f"\n{len(results)} links: {broken} broken, {warned} couldn't be verified.")
    return 1 if broken else 0


if __name__ == "__main__":
    sys.exit(main())
