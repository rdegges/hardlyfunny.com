"""scripts/make_x_header.py and the social/x-header.png it draws.

The PNG is committed, so these tests prove it is still what the script draws today (a
changed banner or script without a regenerated header fails here), that the art keeps out
of the spot X covers with the avatar, and that the build never publishes social/. The
script writes next to its own ROOT, so each run uses a copy in tmp_path, never the repo.
"""

import runpy
import shutil
import subprocess
import sys

import pytest
from PIL import Image

from hardlyfunny.build import CONTENT, ROOT

HEADER = ROOT / "social" / "x-header.png"
SCRIPT = ROOT / "scripts" / "make_x_header.py"


def copy_script(root, with_banner=True):
    (root / "scripts").mkdir(parents=True)
    shutil.copy2(SCRIPT, root / "scripts" / SCRIPT.name)
    if with_banner:
        (root / "content" / "brand").mkdir(parents=True)
        shutil.copy2(CONTENT / "brand" / "banner.png", root / "content" / "brand" / "banner.png")
    return root / "scripts" / SCRIPT.name


def run_script(root, with_banner=True):
    return subprocess.run([sys.executable, "-I", str(copy_script(root, with_banner))],
                          capture_output=True, text=True, timeout=120)


@pytest.fixture(scope="module")
def drawn(tmp_path_factory):
    root = tmp_path_factory.mktemp("header")
    result = run_script(root)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "social/x-header.png"
    return root / "social" / "x-header.png"


def test_committed_header_is_x_size():
    with Image.open(HEADER) as img:
        assert img.format == "PNG"
        assert img.size == (1500, 500)  # X's 3:1 header
        assert img.mode == "RGB"  # no alpha: X flattens it onto an unknown colour


def test_committed_header_is_what_the_script_draws(drawn):
    with Image.open(HEADER) as committed, Image.open(drawn) as fresh:
        assert fresh.size == committed.size
        assert fresh.convert("RGB").tobytes() == committed.convert("RGB").tobytes(), (
            "social/x-header.png is stale: run python -I scripts/make_x_header.py and commit it")


def test_script_draws_the_same_pixels_every_run(drawn, tmp_path):
    result = run_script(tmp_path)
    assert result.returncode == 0, result.stderr
    with Image.open(drawn) as first, Image.open(tmp_path / "social" / "x-header.png") as second:
        assert first.tobytes() == second.tobytes()


def test_script_fails_loudly_without_the_banner_and_writes_nothing(tmp_path):
    result = run_script(tmp_path, with_banner=False)
    assert result.returncode != 0
    assert "banner.png" in result.stderr
    assert not (tmp_path / "social").exists()


def test_banner_art_stays_out_of_the_avatar(tmp_path, monkeypatch):
    # X web shows the header at 600x200 with a 134px avatar, 16px from the left, centred on
    # the header's bottom edge. At 1500x500 that is a circle centred (207, 500), radius 167.
    # The script runs in-process so the check uses the banner and spot it really composites.
    placed = []
    composite = Image.Image.alpha_composite
    monkeypatch.setattr(Image.Image, "alpha_composite",
                        lambda self, im, dest=(0, 0), source=(0, 0): placed.append((im.copy(), dest))
                        or composite(self, im, dest, source))
    runpy.run_path(str(copy_script(tmp_path)), run_name="__main__")
    assert len(placed) == 1
    banner, (x0, y0) = placed[0]
    alpha = banner.getchannel("A")
    hidden = [(x + x0, y + y0) for y in range(banner.height) for x in range(banner.width)
              if alpha.getpixel((x, y)) and (x + x0 - 207) ** 2 + (y + y0 - 500) ** 2 <= 167 ** 2]
    assert hidden == []
    assert x0 >= 0 and y0 >= 0 and x0 + banner.width <= 1500 and y0 + banner.height <= 500, "banner is cropped"


def test_build_does_not_publish_social_art(built):
    header = HEADER.read_bytes()
    assert not (built / "social").exists()
    published = [p for p in built.rglob("*") if p.is_file() and p.stat().st_size == len(header)
                 and p.read_bytes() == header]
    assert published == []
    assert not list(built.rglob("x-header*"))


def test_social_art_is_outside_content():
    # content/ PNGs need archive/ twins (tests/test_images.py); the header has none.
    assert not list(CONTENT.rglob("x-header*"))
