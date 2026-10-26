"""Unit tests for oolite_test_framework.components.menu_list.MenuList. It is tested on an invented screen (green highlight, white text, different place): it reads what is drawn and knows nothing about the title screen."""
from oolite_test_framework import screen
from oolite_test_framework.ui.components import menu_list as components


class FakeApp:
    ocr = None
    class clock:
        @staticmethod
        def sleep(s): pass
    def __init__(self, shot): self.shot = shot; self.after = None; self.keys = []
    def screenshot(self, label=None): return self.shot
    def send_keys(self, *k):
        self.keys += k
        if self.after: self.shot = self.after.pop(0) if isinstance(self.after, list) else self.after
    def hold_key(self, key, seconds): self.send_keys(key)
    def wait_until(self, cond, what, timeout=None):
        if not cond(): raise AssertionError(what)


def draw(n, selected, w=1000, h=800, pitch=0.1, first=0.30):
    """n white text rows, row `selected` (1-based, 0 = none) drawn as a green bar"""
    rgb = bytearray(w * h * 3)
    for i in range(1, n + 1):
        cy = round((first + (i - 1) * pitch) * h)
        for y in range(cy - 8, cy + 8):
            for x in range(int(w * 0.2), int(w * 0.5)):
                rgb[3 * (y * w + x):3 * (y * w + x) + 3] = b"\x00\xff\x00" if i == selected else b"\xff\xff\xff"
    return screen.Shot(w, h, bytes(rgb))


def menu(shot):
    return components.MenuList(FakeApp(shot), x=(0.1, 0.6), y=(0.2, 0.9), is_highlight=lambda r, g, b: g > 200 and r < 40 and b < 40,
                               is_text=lambda r, g, b: max(r, g, b) > 120)


def test_reports_what_is_drawn():
    for n in (1, 4, 6):
        for sel in range(1, n + 1):
            m = menu(draw(n, sel)); assert (m.visible_count, m.selected_index, m.is_visible()) == (n, sel, True), (n, sel)


def test_row_count_does_not_depend_on_spacing_or_window_size():
    assert menu(draw(5, 2, w=1920, h=1080, pitch=0.07)).visible_count == 5
    assert menu(draw(3, 3, w=640, h=480, pitch=0.12)).selected_index == 3


def test_rows_but_nothing_highlighted():
    m = menu(draw(4, 0)); assert (m.visible_count, m.selected_index, m.is_visible()) == (4, None, False)


def test_empty_blank_and_solid_windows():
    assert menu(screen.Shot(1000, 800, bytes(1000 * 800 * 3))).visible_count == 0
    m = menu(screen.Shot(100, 100, bytes([0, 255, 0]) * 10000)); assert m.visible_count == 1 and m.selected_index == 1 or m.visible_count == 0


def test_two_highlighted_rows_is_not_a_valid_selection():
    shot = draw(3, 1); other = draw(3, 3)
    rgb = bytearray(shot.rgb)
    for y in range(0, shot.h):
        for x in range(0, shot.w): 
            if other.rgb[3 * (y * shot.w + x)] == 0 and other.rgb[3 * (y * shot.w + x) + 1] == 255: rgb[3 * (y * shot.w + x):3 * (y * shot.w + x) + 3] = b"\x00\xff\x00"
    assert menu(screen.Shot(shot.w, shot.h, bytes(rgb))).selected_index is None


def test_select_index_presses_the_right_keys():
    m = menu(draw(4, 2)); m.app.after = [draw(4, 3), draw(4, 4)]
    m.select_index(4); assert m.app.keys == ["Down", "Down"]
    m = menu(draw(4, 3)); m.app.after = [draw(4, 2), draw(4, 1)]
    m.select_index(1); assert m.app.keys == ["Up", "Up"]


def test_select_fails_if_the_highlight_does_not_follow():
    m = menu(draw(4, 1))
    try: m.select_index(3)
    except AssertionError as e: assert "did not leave" in str(e)
    else: raise AssertionError("expected a failure")


def test_texts_need_ocr_and_use_it_when_present():
    m = menu(draw(2, 1)); assert m.texts() is None
    m.app.ocr = lambda crop: "row"; assert m.texts() == ["row", "row"]
