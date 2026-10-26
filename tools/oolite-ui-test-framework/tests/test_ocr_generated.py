"""Does the OCR read text on the colours Oolite uses? Draw each string from ocr_strings.STRINGS on each colour pair (with PIL), run it through the
same crop -> prepare -> tesseract path the game tests use, and compare. Needs tesseract AND Pillow, else skipped (they are in the Docker images).
Run: docker/run-ocr-tests.sh   To cover another string or colour, edit tests/unit/ocr_strings.py only."""
import glob
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))
from ocr_strings import COLOUR_PAIRS, FONT_SIZES, STRINGS
from oolite_ui_test_framework import ocr, screen

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    Image = None

read = ocr.make_ocr()
pytestmark = pytest.mark.skipif(read is None or Image is None, reason="needs tesseract and Pillow ((both are in the Docker images))")


def _font(size):
    for pat in ("/usr/share/fonts/**/DejaVuSans-Bold.ttf", "/usr/share/fonts/**/DejaVuSans.ttf"):
        found = glob.glob(pat, recursive=True)
        if found: return ImageFont.truetype(found[0], size)
    pytest.skip("no DejaVu font installed")


def draw(text, fg, bg, size):
    """A crop like the game's: the text on a solid background, with some margin, as a Shot."""
    font = _font(size); l, t, r, b = font.getbbox(text)
    img = Image.new("RGB", (r - l + 24, b - t + 12), bg)
    ImageDraw.Draw(img).text((12 - l, 6 - t), text, font=font, fill=fg)
    return screen.Shot(img.width, img.height, img.tobytes())


@pytest.mark.parametrize("size", FONT_SIZES)
@pytest.mark.parametrize("pair", COLOUR_PAIRS, ids=[p[0] for p in COLOUR_PAIRS])
def test_text_is_read_on_this_colour_pair(pair, size):
    name, fg, bg = pair
    wrong = []
    for text in STRINGS:
        got = read(draw(text, fg, bg, size))
        if not ocr.same_text(got, text): wrong.append("%r read as %r" % (text, got))
    assert not wrong, "%s at %dpx: %s" % (name, size, "; ".join(wrong))


def test_a_different_string_is_not_accepted_as_the_expected_one():
    assert not ocr.same_text(read(draw("Load Commander", (255, 255, 0), (0, 0, 0), 24)), "Game Options")
