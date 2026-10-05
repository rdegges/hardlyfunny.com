"""compress_pngs.py's safety guard, with zopflipng and oxipng replaced by stand-ins.

CI installs neither tool, so these tests feed the guard candidates we control: it must keep
the smallest candidate that decodes to the same mode, size and pixels and keeps every color
chunk, and never write anything else over a content PNG.
"""

import importlib.util
import io
import sys
import types

import pytest
from PIL import Image, PngImagePlugin

from hardlyfunny.build import ROOT


@pytest.fixture
def compress_pngs(monkeypatch):
    fake = types.ModuleType("oxipng")
    fake.StripChunks = types.SimpleNamespace(safe=lambda: "safe")
    fake.optimize = lambda src, dst, **kw: None  # each test replaces this
    monkeypatch.setitem(sys.modules, "oxipng", fake)
    spec = importlib.util.spec_from_file_location("compress_pngs", ROOT / "scripts" / "compress_pngs.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def png(img: Image.Image, *, gamma: bool = False, text: str = "", optimize: bool = False) -> bytes:
    info = PngImagePlugin.PngInfo()
    if gamma:
        info.add(b"gAMA", (45455).to_bytes(4, "big"))
    if text:
        info.add_text("Software", text)
    buf = io.BytesIO()
    img.save(buf, "PNG", pnginfo=info, optimize=optimize)
    return buf.getvalue()


def picture() -> Image.Image:
    img = Image.new("RGBA", (40, 40), (255, 255, 255, 255))
    for x in range(40):
        img.putpixel((x, x), (0, 0, 0, 255))
    return img


def use_candidates(monkeypatch, module, zop: bytes, oxi: bytes):
    def run(cmd, **kw):
        open(cmd[-1], "wb").write(zop)
    monkeypatch.setattr(module.subprocess, "run", run)
    monkeypatch.setattr(module.oxipng, "optimize", lambda src, dst, **kw: open(dst, "wb").write(oxi))


def test_keeps_the_smallest_candidate_that_decodes_the_same(compress_pngs, monkeypatch, tmp_path):
    src = tmp_path / "a.png"
    src.write_bytes(png(picture(), text="x" * 2000))
    smaller, smallest = png(picture(), text="x" * 100), png(picture(), optimize=True)
    use_candidates(monkeypatch, compress_pngs, zop=smaller, oxi=smallest)
    work = tmp_path / "work"
    work.mkdir()
    assert compress_pngs.compress(src, work)[0] == "oxipng"
    assert src.read_bytes() == smallest


@pytest.mark.parametrize("bad", ["one pixel", "alpha", "mode", "size", "lost gAMA"])
def test_never_writes_a_smaller_candidate_that_decodes_differently_or_drops_a_color_chunk(compress_pngs, monkeypatch, tmp_path, bad):
    original = png(picture(), gamma=True, text="x" * 5000)
    changed = picture()
    if bad == "one pixel":
        changed.putpixel((5, 0), (0, 0, 0, 255))
    elif bad == "alpha":
        changed.putpixel((5, 0), (255, 255, 255, 0))
    elif bad == "size":
        changed = changed.crop((0, 0, 40, 39))
    candidate = png(changed, gamma=bad != "lost gAMA")
    if bad == "mode":
        candidate = png(changed.convert("RGB"), gamma=True)
    assert len(candidate) < len(original)
    src = tmp_path / "a.png"
    src.write_bytes(original)
    use_candidates(monkeypatch, compress_pngs, zop=candidate, oxi=candidate)
    work = tmp_path / "work"
    work.mkdir()
    assert compress_pngs.compress(src, work) == ("original", len(original), len(original))
    assert src.read_bytes() == original


def test_leaves_the_file_alone_when_nothing_is_smaller(compress_pngs, monkeypatch, tmp_path):
    original = png(picture(), optimize=True)
    src = tmp_path / "a.png"
    src.write_bytes(original)
    bigger = png(picture(), text="x" * 100)
    use_candidates(monkeypatch, compress_pngs, zop=bigger, oxi=bigger)
    work = tmp_path / "work"
    work.mkdir()
    assert compress_pngs.compress(src, work)[0] == "original"
    assert src.read_bytes() == original


def test_main_fails_when_there_are_no_pngs(compress_pngs, monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(compress_pngs, "CONTENT", tmp_path)
    assert compress_pngs.main() == 1
    assert "no PNGs" in capsys.readouterr().out
