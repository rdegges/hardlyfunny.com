#!/usr/bin/env python3
"""Report the HTTP status of every link in the comic notes and the About page.

    python3 scripts/check_links.py

Links rot over time. When one dies, replace it with an Internet Archive snapshot
taken near the comic's date: https://archive.org/wayback/available?url=<url>&timestamp=<YYYYMMDD>
Some sites (Reddit, news sites) block scripts with 403s while working fine in a browser.
"""

from __future__ import annotations

import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15"


def links() -> list[tuple[str, str]]:
    data = json.loads((ROOT / "content" / "comics.json").read_text(encoding="utf-8"))
    found = [(f"#{c['number']} {c['title']}", h) for c in data["comics"] for h in re.findall(r'href="([^"]+)"', c["note_html"])]
    found += [("About", h) for h in re.findall(r'href="([^"]+)"', data["site"]["about_html"])]
    return found


def status(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return str(resp.status)
    except urllib.error.HTTPError as e:
        return str(e.code)
    except Exception as e:  # DNS failure, timeout, TLS…
        return type(e).__name__


def main() -> int:
    bad = 0
    for where, url in links():
        code = status(url)
        ok = code.startswith(("2", "3"))
        bad += not ok
        print(f"{'ok ' if ok else 'BAD'} {code:>14}  {where}: {url}")
    print(f"\n{bad} link(s) need a look.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
