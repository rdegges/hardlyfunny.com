"""Share links for each comic.

X, Facebook, LinkedIn, Reddit and Hacker News have "intent" URLs that open a
prefilled post. They all take the page URL, and each network then pulls the comic
image from the page's og:image tag, so the post shows the comic.

Instagram has no web intent at all. The page offers it through the browser's
native share sheet with the image attached (site.js), which reaches the Instagram
app on phones.
"""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import quote, urlencode


@dataclass(frozen=True)
class ShareLink:
    network: str  # also the icon file name
    label: str
    href: str


def _query(params: dict[str, str]) -> str:
    # %20 for spaces, not "+": Hacker News (and some others) show a literal "+" in the title.
    return urlencode(params, quote_via=quote)


def links(page_url: str, title: str, site_title: str) -> list[ShareLink]:
    text = f"“{title}” from {site_title}, a webcomic about being married to a programmer"
    return [
        ShareLink("x", "X", "https://x.com/intent/post?" + _query({"text": text, "url": page_url})),
        ShareLink("facebook", "Facebook", "https://www.facebook.com/sharer/sharer.php?" + _query({"u": page_url})),
        ShareLink("linkedin", "LinkedIn", "https://www.linkedin.com/sharing/share-offsite/?" + _query({"url": page_url})),
        ShareLink("reddit", "Reddit", "https://www.reddit.com/submit?" + _query({"url": page_url, "title": f"{site_title}: {title}"})),
        ShareLink("ycombinator", "Hacker News", "https://news.ycombinator.com/submitlink?" + _query({"u": page_url, "t": f"{site_title}: {title}"})),
    ]
