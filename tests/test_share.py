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


def test_spaces_are_percent_encoded_not_plus_signs():
    # Hacker News shows "Hardly+Funny:+Being+Thoughtful" when spaces are encoded as "+".
    for link in share.links(URL, "Being Thoughtful", "Hardly Funny"):
        query_string = urlparse(link.href).query
        assert "+" not in query_string, link.href
        assert "%20" in query_string or link.network in ("facebook", "linkedin"), link.href


def test_hacker_news_title_round_trips():
    link = next(l for l in share.links(URL, "Being Thoughtful", "Hardly Funny") if l.network == "ycombinator")
    assert "t=Hardly%20Funny%3A%20Being%20Thoughtful" in link.href
