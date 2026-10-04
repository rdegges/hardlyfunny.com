"""python -m hardlyfunny build | serve [--portable]"""

from __future__ import annotations

import argparse
import functools
import http.server
from pathlib import Path

from . import urls
from .build import ROOT, build


class Handler(http.server.SimpleHTTPRequestHandler):
    """Serves the feed as Atom, as Cloudflare does via _headers, though it's built as an index.html."""

    def guess_type(self, path):
        feed = Path(self.directory) / urls.output_path(urls.FEED)
        if Path(path).resolve() == feed.resolve():
            return "application/atom+xml; charset=utf-8"
        return super().guess_type(path)


def main() -> None:
    parser = argparse.ArgumentParser(prog="hardlyfunny", description="Build the Hardly Funny static site.")
    parser.add_argument("command", choices=["build", "serve"])
    parser.add_argument("--out", type=Path, default=ROOT / "_site", help="output directory (default: _site)")
    parser.add_argument("--site-url", help="override the canonical site URL, e.g. for a preview deploy")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--portable", action="store_true",
                        help="relative links, so the build also works opened straight from disk")
    args = parser.parse_args()

    site = build(args.out, args.site_url, portable=args.portable)
    print(f"Built {len(site.comics)} comics into {args.out}")
    if args.command == "serve":
        handler = functools.partial(Handler, directory=str(args.out))
        print(f"Serving on http://localhost:{args.port}/")
        http.server.ThreadingHTTPServer(("", args.port), handler).serve_forever()


if __name__ == "__main__":
    main()
