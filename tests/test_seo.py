import dataclasses
import json

from hardlyfunny import seo


def test_jsonld_cannot_break_out_of_its_script_element(site):
    nasty = dataclasses.replace(site.comics[0], title="</script><!--<script>", transcript=("Randall: <b>&</b>",))
    block = seo.comic_jsonld(site, nasty)
    assert "<" not in block and ">" not in block and "&" not in block
    assert json.loads(block)["name"] == "</script><!--<script>"


def test_keywords_are_omitted_when_a_comic_has_no_tags(site):
    untagged = dataclasses.replace(site.comics[0], tags=())
    assert "keywords" not in json.loads(seo.comic_jsonld(site, untagged))
