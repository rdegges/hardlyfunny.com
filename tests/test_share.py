from urllib.parse import parse_qs, urlparse

from hardlyfunny import share

URL = "https://hardlyfunny.com/comics/infinite-recursion/"


def query(link):
    return {k: v[0] for k, v in parse_qs(urlparse(link.href).query).items()}


def test_offers_every_network_with_an_intent_url():
    links = {l.network: l for l in share.links(URL, "Infinite Recursion", "Hardly Funny")}
    assert set(links) == {"x", "facebook", "linkedin", "reddit", "ycombinator"}
    assert urlparse(links["x"].href).netloc == "x.com"
    assert urlparse(links["ycombinator"].href).path == "/submitlink"


def test_every_link_carries_the_page_url_so_the_og_image_is_used():
    for link in share.links(URL, "Infinite Recursion", "Hardly Funny"):
        assert URL in query(link).values(), link.network


def test_titles_are_prefilled_where_the_network_supports_it():
    links = {l.network: query(l) for l in share.links(URL, "Infinite Recursion", "Hardly Funny")}
    assert "Infinite Recursion" in links["x"]["text"]
    assert links["reddit"]["title"] == "Hardly Funny: Infinite Recursion"
    assert links["ycombinator"]["t"] == "Hardly Funny: Infinite Recursion"
