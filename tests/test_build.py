import pytest

from hardlyfunny.build import ROOT, build


def test_refuses_to_delete_the_repo_or_unrelated_directories(tmp_path):
    with pytest.raises(SystemExit):
        build(ROOT)
    precious = tmp_path / "photos"
    precious.mkdir()
    (precious / "wedding.jpg").write_bytes(b"x")
    with pytest.raises(SystemExit):
        build(precious)
    assert (precious / "wedding.jpg").exists()


def test_rebuilding_into_a_previous_build_is_allowed(tmp_path):
    out = tmp_path / "site"
    build(out, portable=True)
    build(out, portable=True)
    assert (out / "index.html").exists()
