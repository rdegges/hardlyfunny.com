from urllib.parse import parse_qs, urlparse

from hardlyfunny import share

URL = "https://hardlyfunny.com/comics/infinite-recursion/"


def query(link):
    return {k: v[0] for k, v in parse_qs(urlparse(link.href).query).items()}


def test_offers_every_network_with_an_intent_url():
    links = {l.network: l for l in share.links(URL, "Infinite Recursion", "Hardly Funny")}
    assert set(links) == {"x", "bluesky", "facebook", "linkedin", "reddit", "ycombinator"}
    assert urlparse(links["x"].href).netloc == "x.com"
    assert urlparse(links["ycombinator"].href).path == "/submitlink"


def test_every_link_carries_the_page_url_so_the_og_image_is_used():
    for link in share.links(URL, "Infinite Recursion", "Hardly Funny"):
        values = query(link).values()
        # Bluesky's composer only takes text; it builds the link card from the first URL in it.
        assert URL in values or any(v.endswith(URL) for v in values), link.network


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


def test_bluesky_opens_the_composer_with_the_post_and_link():
    link = next(l for l in share.links(URL, "Infinite Recursion", "Hardly Funny") if l.network == "bluesky")
    assert link.href.startswith("https://bsky.app/intent/compose?text=")
    text = query(link)["text"]
    assert "Infinite Recursion" in text and text.endswith(" " + URL)
    assert len(text) <= 300, "Bluesky posts are capped at 300 characters"


def test_each_mode_gets_its_own_networks():
    sides = {l.network: l.side for l in share.links(URL, "Infinite Recursion", "Hardly Funny")}
    assert [n for n, s in sides.items() if s == "samantha"] == ["x", "facebook"]  # plus Instagram, in the template
    assert [n for n, s in sides.items() if s == "randall"] == ["bluesky", "linkedin", "reddit", "ycombinator"]
