"""OCR with the REAL tesseract on a real title-screen screenshot. Skipped where tesseract is not installed, so the normal unit run is unaffected.
Run it inside any image with: ./docker/run-ocr-tests.sh [image]   (default oolite-uitest-debian)"""
import os

import pytest

from oolite_ui_test_framework import ocr, png, screen
from oolite_ui_test_framework.ui import pages

DATA = os.path.join(os.path.dirname(__file__), "fixtures", "title-menu-1280x720.png")
read = ocr.make_ocr()
pytestmark = pytest.mark.skipif(read is None, reason="tesseract is not installed in this environment")


class Still:
    """just enough of App to let the title page read a saved screenshot"""
    def __init__(self, shot, ocr): self.shot, self.ocr = shot, ocr
    def screenshot(self, label=None): return self.shot


def shot(): return screen.Shot(*png.read_png(DATA))


def title_page():
    return pages.TitleMenuPage(Still(shot(), read))


def test_every_menu_row_is_read_correctly():
    p = title_page(); texts = p.menu.texts()
    assert len(texts) == 6
    bad = [(t, e) for t, e in zip(texts, p.EXPECTED_ITEMS) if not ocr.same_text(t, e)]
    assert not bad, "misread rows (read, expected): %s" % bad


def test_selected_row_black_on_red_is_read_too():
    p = title_page(); first = p.menu.rows[0]
    assert ocr.same_text(read(shot().crop_box(first["box"])), "Start New Commander")


def test_title_page_accepts_the_real_screen():
    assert title_page().shows_expected_items() == (True, "")


def test_a_wrong_screen_is_rejected_by_the_text():
    p = title_page(); p.app.ocr = lambda crop: "Credits"
    ok, why = p.shows_expected_items()
    assert not ok and "menu text read as" in why


def test_descenders_are_not_cut_off_kwin_x11():
    """KWin X11 rendering where the row box ended above the tail of the "p": tesseract read "Game Gntions", outside the tolerance (#42).
    With room above and below every row is read."""
    s = screen.Shot(*png.read_png(os.path.join(os.path.dirname(__file__), "fixtures", "title-menu-kwin-x11-1280x720.png")))
    assert pages.TitleMenuPage(Still(s, read)).shows_expected_items() == (True, "")
