from __future__ import annotations

from html.parser import HTMLParser
from pathlib import Path

import pytest

from hardlyfunny.build import CONTENT, build
from hardlyfunny.content import load


@pytest.fixture(scope="session")
def site():
    return load(CONTENT / "comics.json")


@pytest.fixture(scope="session")
def built(tmp_path_factory):
    """Build the whole site once for every test that inspects output."""
    out = tmp_path_factory.mktemp("site")
    build(out)
    return out


class Page(HTMLParser):
    """Just enough of an HTML document to assert on: tags with attributes, headings, text."""

    VOID = {"meta", "link", "img", "br", "input", "hr", "source"}

    def __init__(self, html: str):
        super().__init__(convert_charrefs=True)
        self.elements: list[tuple[str, dict]] = []
        self.headings: list[tuple[str, str]] = []
        self.title = ""
        self._stack: list[str] = []
        self._heading: list | None = None
        self._in_title = False
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        self.elements.append((tag, dict(attrs)))
        if tag == "title":
            self._in_title = True
        if tag in {"h1", "h2", "h3"}:
            self._heading = [tag, ""]
        if tag not in self.VOID:
            self._stack.append(tag)

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False
        if self._heading and tag == self._heading[0]:
            self.headings.append((self._heading[0], self._heading[1].strip()))
            self._heading = None
        if self._stack and self._stack[-1] == tag:
            self._stack.pop()

    def handle_data(self, data):
        if self._in_title:
            self.title += data
        if self._heading:
            self._heading[1] += data

    def all(self, tag: str, **match) -> list[dict]:
        return [a for t, a in self.elements if t == tag and all(a.get(k) == v for k, v in match.items())]

    def meta(self, key: str) -> str | None:
        for attrs in self.all("meta"):
            if attrs.get("property") == key or attrs.get("name") == key:
                return attrs.get("content")
        return None


@pytest.fixture
def parse():
    return lambda path: Page(Path(path).read_text())
