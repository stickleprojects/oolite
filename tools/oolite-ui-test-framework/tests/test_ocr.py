"""OCR support, tested without tesseract installed: pre-processing is pure; the tesseract call is replaced by a fake runner.
SAMPLE: how to unit-test a component that reads text (see also components/test_menu_list.py::test_texts_need_ocr_and_use_it_when_present)."""
import types

from oolite_ui_test_framework import ocr, screen
from oolite_ui_test_framework.ui import pages
from test_app import make, with_bar


def shot_of(rows):
    """w x h shot from rows of characters: '#' = yellow text, ' ' = black background"""
    w, h = len(rows[0]), len(rows)
    rgb = b"".join(b"\xff\xff\x00" if c == "#" else b"\x00\x00\x00" for r in rows for c in r)
    return screen.Shot(w, h, rgb)


def test_prepare_gives_dark_text_on_white_scaled_up_with_border():
    p = ocr.prepare(shot_of(["    ", " ## ", " ## ", "    "]), scale=2, pad=3)
    assert (p.w, p.h) == (4 * 2 + 6, 4 * 2 + 6)
    px = lambda x, y: p.rgb[3 * (y * p.w + x)]
    assert px(0, 0) == 255 and px(3 + 2 * 1, 3 + 2 * 1) == 0          # border is white, the text pixel is black


def test_prepare_handles_selected_row_black_text_on_red_bar():
    red = screen.Shot(4, 3, (b"\xff\x00\x00" * 4) + (b"\xff\x00\x00\x00\x00\x00\x00\x00\x00\xff\x00\x00") + (b"\xff\x00\x00" * 4))
    p = ocr.prepare(red, scale=1, pad=0)
    assert [p.rgb[3 * (1 * 4 + x)] for x in range(4)] == [255, 0, 0, 255]     # the black text is the ink, the red bar is the background


def test_make_ocr_is_none_without_tesseract():
    assert ocr.make_ocr(which=lambda name: None) is None


def test_make_ocr_runs_tesseract_on_a_png_and_returns_the_text(tmp_path):
    seen = {}
    def fake_run(cmd, **kw):
        seen["cmd"] = cmd; seen["png_ok"] = open(cmd[1], "rb").read(8) == b"\x89PNG\r\n\x1a\n"
        return types.SimpleNamespace(returncode=0, stdout="  Game Options\n")
    read = ocr.make_ocr(which=lambda n: "/usr/bin/tesseract", runner=fake_run)
    assert read(shot_of(["  # ", " ## "])) == "Game Options"
    assert seen["cmd"][0] == "/usr/bin/tesseract" and seen["cmd"][-2:] == ["--psm", "7"] and seen["png_ok"]


def test_tesseract_failure_reads_as_empty_text():
    read = ocr.make_ocr(which=lambda n: "t", runner=lambda *a, **k: types.SimpleNamespace(returncode=1, stdout="x"))
    assert read(shot_of(["# "])) == ""


def test_same_text_tolerates_a_misread_but_not_a_wrong_screen():
    assert ocr.same_text("Game Options", "Game Options")
    assert ocr.same_text(" game  optlons", "Game Options")
    assert not ocr.same_text("", "Game Options")
    assert not ocr.same_text("Load Commander", "Game Options")


def test_title_page_checks_each_row_text_with_ocr():
    a = make([with_bar(1280, 720, 1)] * 10)
    names = iter(pages.TitleMenuPage.EXPECTED_ITEMS)
    a.ocr = lambda crop: next(names)
    assert a.title_menu.shows_expected_items() == (True, "")
    a.ocr = lambda crop: "Something else"
    ok, why = a.title_menu.shows_expected_items()
    assert not ok and "menu text read as" in why


def test_title_page_without_ocr_does_not_check_text():
    a = make([with_bar(1280, 720, 1)] * 3); a.ocr = None
    assert a.title_menu.shows_expected_items() == (True, "")


# ---- the three steps of prepare(), each on its own
def solid(colour, w=8, h=8):
    return screen.Shot(w, h, bytes(colour) * (w * h))


def test_predominant_colour_is_the_one_covering_most_of_the_crop():
    mostly_black = shot_of(["        ", " #      ", "        ", "        "])
    assert ocr._get_predominant_colour(mostly_black) == (16, 16, 16)           # black, rounded to the middle of its bucket
    r, g, b = ocr._get_predominant_colour(solid((255, 0, 0)))
    assert r > 200 and g < 40 and b < 40                                        # red


def test_predominant_colour_of_the_selected_row_is_the_bar_not_the_text():
    red_bar = screen.Shot(6, 2, (b"\xff\x00\x00" * 5 + b"\x00\x00\x00") * 2)    # mostly red, one black text pixel per line
    r, g, b = ocr._get_predominant_colour(red_bar)
    assert r > 200 and g < 40 and b < 40


def test_two_tone_mask_marks_only_pixels_that_differ_from_the_predominant_colour():
    shot = shot_of(["  # ", "    "])
    assert list(ocr._get_two_tone_mask(shot, (16, 16, 16))) == [0, 0, 1, 0, 0, 0, 0, 0]


def test_two_tone_mask_ignores_small_colour_differences():
    nearly_black = screen.Shot(2, 1, b"\x10\x10\x10" + b"\x20\x20\x20")        # difference 48 < threshold
    assert list(ocr._get_two_tone_mask(nearly_black, (16, 16, 16))) == [0, 0]


def test_black_and_white_image_has_only_black_and_white_pixels():
    img = ocr._get_black_and_white_image(bytearray([0, 1, 0, 0]), 2, 2, scale=2, pad=1)
    assert (img.w, img.h) == (6, 6)
    assert set(img.rgb) == {0, 255}
    px = lambda x, y: img.rgb[3 * (y * img.w + x)]
    assert [px(x, 1) for x in range(6)] == [255, 255, 255, 0, 0, 255]           # the marked pixel is a 2x2 black block
    assert [px(x, 0) for x in range(6)] == [255] * 6                             # top border is white


def test_black_and_white_image_of_an_empty_mask_is_all_white():
    img = ocr._get_black_and_white_image(bytearray(4), 2, 2, scale=1, pad=0)
    assert set(img.rgb) == {255}
