"""app.App and the title-menu page object, against a fake session, game, clock and screenshot backend (invented frames plus the
sample screenshot in fixtures/): waits, key holding, selection and the failures a test should report. No display or game."""
import pytest

from oolite_ui_test_framework import app as appmod, screen
from oolite_ui_test_framework.ui import pages


class Clock:
    def __init__(self): self.t = 0.0
    def monotonic(self): return self.t
    def sleep(self, d): self.t += d


class Proc:
    def __init__(self, code=None): self.code = code
    def poll(self): return self.code


class Backend:
    """grab() returns what the fake game 'draws'; Down presses move the highlight unless frozen"""
    def __init__(self, frames): self.frames = frames; self.i = 0
    def grab(self, w):
        s = self.frames[min(self.i, len(self.frames) - 1)]; self.i += 1
        return (s.w, s.h, s.rgb)


class Session:
    def __init__(self, backend, win=7): self.backend = backend; self.win = win; self.keys = []
    def window_id(self): return self.win
    after = None
    def send_key(self, k, w=None):
        self.keys.append(k)
        if self.after: self.backend.frames = [self.after.pop(0)] if len(self.after) > 1 else self.after   # one screen per key press
    def key_down(self, k): self.send_key(k)
    def hold_time(self, s): return s
    def key_up(self, k): pass


class Game:
    def __init__(self, code=None): self.proc = Proc(code)


def make(frames, code=None, win=7):
    return appmod.App(Session(Backend(frames), win), Game(code), clock=Clock())


def with_bar(w, h, row, n=6):
    """title-menu look: n yellow text rows from 0.795 of the height, 1/30 apart; row `row` is black text on a red bar"""
    rgb = bytearray(w * h * 3)
    for i in range(1, n + 1):
        cy = round((0.795 + (i - 1) / 30) * h)
        for y in range(cy - h // 120, cy + h // 120):
            for x in range(int(w * 0.43), int(w * 0.57)): rgb[3 * (y * w + x):3 * (y * w + x) + 3] = b"\xff\x00\x00" if i == row else b"\xff\xff\x00"
    return screen.Shot(w, h, bytes(rgb))


def blank(): return screen.Shot(1280, 720, bytes(1280 * 720 * 3))


def test_wait_for_menu_returns_when_drawn():
    a = make([blank(), blank(), with_bar(1280, 720, 1)])
    assert a.title_menu.wait_until_displayed().selected_item == "Start New Commander"


def test_menu_never_drawn_fails_with_what_was_seen():
    a = make([blank()])
    with pytest.raises(appmod.ScenarioFailed, match="title menu.*blank|title menu.*black|window looks"):
        a.title_menu.wait_until_displayed(timeout=2)


def test_no_window_fails():
    a = make([blank()], win=None)
    with pytest.raises(appmod.ScenarioFailed, match="no game window"):
        a.title_menu.wait_until_displayed(timeout=1)


def test_game_exit_is_reported_at_once():
    a = make([blank()], code=1)
    with pytest.raises(appmod.ScenarioFailed, match="exited"):
        a.title_menu.wait_until_displayed(timeout=5)


def test_frozen_window_does_not_move_selection():
    a = make([with_bar(1280, 720, 1)])
    with pytest.raises(appmod.ScenarioFailed, match="highlight did not leave row 1"):
        a.title_menu.wait_until_displayed().menu.move_down(2)
    assert a.session.keys == ["Down", "Down"]      # held again once, then gave up


def test_no_grab_support_is_not_measurable():
    a = appmod.App(Session(object()), Game(), clock=Clock())
    with pytest.raises(appmod.NotMeasurable):
        a.screenshot()


def test_title_menu_reads_every_row_at_other_sizes():
    for w, h in ((1280, 720), (1920, 1080), (800, 600)):
        for row in range(1, 7):
            a = make([with_bar(w, h, row)] * 3)
            assert a.title_menu.selected_item == pages.TitleMenuPage.EXPECTED_ITEMS[row - 1], (w, h, row)


def test_real_title_screenshot():
    import os
    from oolite_ui_test_framework import png
    a = make([screen.Shot(*png.read_png(os.path.join(os.path.dirname(__file__), "fixtures", "title-menu-1280x720.png")))])
    assert a.title_menu.selected_item == "Start New Commander"


def test_wrong_number_of_rows_is_reported_and_has_no_selected_item():
    a = make([with_bar(1280, 720, 1, n=4)] * 3)
    ok, why = a.title_menu.shows_expected_items()
    assert not ok and "4 menu rows" in why and a.title_menu.selected_item is None


def test_expected_items_ok_and_select_by_name():
    a = make([with_bar(1280, 720, 1)])
    assert a.title_menu.shows_expected_items() == (True, "")
    a.session.after = [with_bar(1280, 720, 2), with_bar(1280, 720, 3), with_bar(1280, 720, 4)]      # what is drawn after each key press
    a.title_menu.select("Game Options")
    assert a.session.keys == ["Down", "Down", "Down"]


def test_settled_item_waits_for_a_highlight_that_is_still_moving():
    a = make([with_bar(1280, 720, 1)] * 3)
    assert a.title_menu.wait_until_displayed().settled_item() == "Start New Commander"
    a = make([with_bar(1280, 720, 2), with_bar(1280, 720, 3)] + [with_bar(1280, 720, 4)] * 12)
    assert a.title_menu.settled_item() == "Game Options"
