"""png: write_png, read_png and bgrx_to_rgb on small invented images and the sample screenshot in fixtures/. No display needed."""
import os

from oolite_ui_test_framework import png

DATA = os.path.join(os.path.dirname(__file__), "fixtures")


def test_png_writer_and_bgrx(tmp_path):
    w, h = 8, 4; rgb = bytes(c for y in range(h) for x in range(w) for c in (x, y, 7))
    p = tmp_path / "a.png"; png.write_png(str(p), w, h, rgb)
    d = p.read_bytes(); assert d.startswith(b"\x89PNG") and b"IDAT" in d and d.endswith(b"IEND\xaeB`\x82")
    assert png.bgrx_to_rgb(bytes([3, 2, 1, 0] * 4), 2, 2) == bytes([1, 2, 3] * 4)


def test_png_reader_matches_writer(tmp_path):
    rgb = bytes(range(256)) * 3 * 3
    p = str(tmp_path / "a.png"); png.write_png(p, 16, 16, rgb[:16 * 16 * 3])
    assert png.read_png(p) == (16, 16, rgb[:16 * 16 * 3])


def test_real_screenshot_loads():
    w, h, rgb = png.read_png(os.path.join(DATA, "title-menu-1280x720.png"))
    assert (w, h, len(rgb)) == (1280, 720, 1280 * 720 * 3)
