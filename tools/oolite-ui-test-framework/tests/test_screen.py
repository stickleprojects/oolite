import os

from oolite_ui_test_framework import render, screen

DATA = os.path.join(os.path.dirname(__file__), "fixtures")


def test_png_reader_matches_writer(tmp_path):
    rgb = bytes(range(256)) * 3 * 3
    p = str(tmp_path / "a.png"); render.write_png(p, 16, 16, rgb[:16 * 16 * 3])
    assert render.read_png(p) == (16, 16, rgb[:16 * 16 * 3])


def test_real_screenshot_loads():
    w, h, rgb = render.read_png(os.path.join(DATA, "title-menu-1280x720.png"))
    assert (w, h, len(rgb)) == (1280, 720, 1280 * 720 * 3)


def test_crop_and_region():
    s = screen.Shot(*render.read_png(os.path.join(DATA, "title-menu-1280x720.png")))
    c = s.crop(0.35, 0.75, 0.65, 1.0)
    assert (c.w, c.h) == (384, 180) and len(c.rgb) == c.w * c.h * 3
    assert s.region(0.5, 0.5, 1, 1) == (640, 360, 1280, 720)
