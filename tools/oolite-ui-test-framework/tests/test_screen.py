"""screen.Shot: crops and regions as window fractions, on the sample title-screen screenshot in fixtures/."""
import os

from oolite_ui_test_framework import png, screen

DATA = os.path.join(os.path.dirname(__file__), "fixtures")


def test_crop_and_region():
    s = screen.Shot(*png.read_png(os.path.join(DATA, "title-menu-1280x720.png")))
    c = s.crop(0.35, 0.75, 0.65, 1.0)
    assert (c.w, c.h) == (384, 180) and len(c.rgb) == c.w * c.h * 3
    assert s.region(0.5, 0.5, 1, 1) == (640, 360, 1280, 720)
