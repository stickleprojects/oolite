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
    with pytest.raises(appmod.ScenarioFailed, match="highlight did not leave row 1") as e:
        a.title_menu.wait_until_displayed().menu.move_down(2)
    assert a.session.keys == ["Down"] and "key presses" not in str(e.value)      # held up to the cap once; no game log, no key count


def test_a_key_is_released_as_soon_as_the_highlight_moves():
    a = make([with_bar(1280, 720, 1)]); a.session.after = [with_bar(1280, 720, 2)]
    t = []; down = a.session.key_down
    a.session.key_down = lambda k: (t.append(a.clock.t), down(k)); a.session.key_up = lambda k: t.append(a.clock.t)
    a.title_menu.wait_until_displayed().menu.move_down()
    assert a.session.keys == ["Down"] and t[1] - t[0] < 0.1       # released on the first look after the highlight moved, not after a fixed hold


def test_highlight_bar_next_to_a_row_does_not_merge_with_it():
    """Exit Game highlighted: the red bar is taller than the text and came within the row gap of Manage Expansion Packs, so the two read as
    one row (5 rows, nothing selected) and a key test that overshot to the last row failed (#42)."""
    import os
    from oolite_ui_test_framework import png
    a = make([screen.Shot(*png.read_png(os.path.join(os.path.dirname(__file__), "fixtures", "title-menu-exit-selected-1280x720.png")))])
    assert a.title_menu.menu.visible_count == 6 and a.title_menu.selected_item == "Exit Game"


def test_where_a_look_is_slower_than_the_game_repeat_the_key_is_tapped():
    """Native KWin: a grab takes about a second, so holding the key until the highlight is seen to move ran it past the row (#38 smoke).
    Each press is a short tap, looked at after; a tap the game did not see (no move) is repeated."""
    a = make([with_bar(1280, 720, 1)]); a.session.after = [with_bar(1280, 720, 1), with_bar(1280, 720, 2)]
    grab = a.session.backend.grab
    a.session.backend.grab = lambda w: (setattr(a.clock, "t", a.clock.t + 0.6), grab(w))[1]      # every look takes 0.6 s
    t = []; down = a.session.key_down
    a.session.key_down = lambda k: (t.append(("down", a.clock.t)), down(k)); a.session.key_up = lambda k: t.append(("up", a.clock.t))
    a.title_menu.wait_until_displayed().menu.move_down()
    assert a.title_menu.selected_item == "Load Commander" and a.session.keys == ["Down", "Down"]   # the first tap moved nothing
    holds = [u[1] - d[1] for d, u in zip(t[0::2], t[1::2])]
    assert all(h < appmod.App.GAME_KEY_REPEAT for h in holds), holds                              # never held into the game's repeat


def test_a_tap_the_game_did_not_see_is_held_longer_and_remembered():
    """sway, 3836x1053: a frame takes longer than a 0.08 s tap, so down and up arrive in one frame and the game never sees the key (#42).
    Each tap the game ignored is held twice as long; the one that worked is where the next press starts."""
    a = make([with_bar(1280, 720, 1)])
    grab = a.session.backend.grab
    a.session.backend.grab = lambda w: (setattr(a.clock, "t", a.clock.t + 0.6), grab(w))[1]      # slow looks: tapping
    holds = []; t = {}; frame = 0.3                                                              # the game sees a key held >= one frame
    a.session.key_down = lambda k: t.update(d=a.clock.t)
    def up(k):
        holds.append(round(a.clock.t - t["d"], 2))
        if holds[-1] >= frame: a.session.backend.frames = [with_bar(1280, 720, len([h for h in holds if h >= frame]) + 1)]
    a.session.key_up = up
    page = a.title_menu.wait_until_displayed()
    page.menu.move_down()
    assert holds == [0.08, 0.16, 0.32] and page.selected_item == "Load Commander"
    page.menu.move_down()
    assert holds[3:] == [0.32] and page.selected_item == "View Ship Library"                  # started at the tap that worked


def test_no_key_reached_the_game_says_so(tmp_path):
    a = make([with_bar(1280, 720, 1)]); a.game.dir = str(tmp_path)
    (tmp_path / "GameData").mkdir(); (tmp_path / "GameData" / "Latest.log").write_text("Opening log for Oolite\n")
    with pytest.raises(appmod.ScenarioFailed, match="logged no key presses at all"):
        a.title_menu.wait_until_displayed().menu.move_down()
    (tmp_path / "GameData" / "Latest.log").write_text("Keydown scancode = 81, unicode = 269\n" * 3)
    with pytest.raises(appmod.ScenarioFailed, match="logged 3 key presses"):
        a.title_menu.menu.move_down()


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


def test_lit_ship_hull_above_the_menu_is_not_a_row():
    """The rotating ship's hull, lit white, dips into the menu region (kwin-native, #37): it must not count as a seventh row."""
    import os
    from oolite_ui_test_framework import png
    a = make([screen.Shot(*png.read_png(os.path.join(os.path.dirname(__file__), "fixtures", "title-menu-lit-hull-1280x720.png")))])
    assert a.title_menu.menu.visible_count == 6 and a.title_menu.selected_item == "Start New Commander"


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


class MouseSession(Session):
    """a session that can click: pressing the button over a row draws that row highlighted (rows found by MenuList on with_bar screens)"""
    def __init__(self, backend, win=7, works=True):
        super().__init__(backend, win); self.clicks = []; self.at = None; self.works = works
    def mouse_ok(self): return True
    def mouse_move(self, x, y): self.at = (x, y)
    def mouse_down(self):
        self.clicks.append(self.at)
        if self.works: self.backend.frames = [with_bar(1280, 720, round(((self.at[1] / 720) - 0.795) * 30) + 1)]
    def mouse_up(self): pass


def test_select_clicks_the_row_where_the_mouse_works():
    a = appmod.App(MouseSession(Backend([with_bar(1280, 720, 1)])), Game(), clock=Clock())
    a.title_menu.select("Game Options")
    (x, y), = a.session.clicks
    assert a.session.keys == [] and abs(y - round((0.795 + 3 / 30) * 720)) <= 1 and 0.43 * 1280 < x < 0.57 * 1280   # on row 4, once


def test_select_by_keys_still_works_where_the_mouse_works():
    a = appmod.App(MouseSession(Backend([with_bar(1280, 720, 1)])), Game(), clock=Clock())
    a.session.after = [with_bar(1280, 720, 2), with_bar(1280, 720, 3), with_bar(1280, 720, 4)]
    a.title_menu.select("Game Options", by="keys")
    assert a.session.keys == ["Down", "Down", "Down"] and a.session.clicks == []


def test_a_click_that_does_not_move_the_highlight_fails():
    a = appmod.App(MouseSession(Backend([with_bar(1280, 720, 1)]), works=False), Game(), clock=Clock())
    with pytest.raises(appmod.ScenarioFailed, match="clicking row 4 left the highlight on row 1"):
        a.title_menu.select("Game Options")


def test_no_click_in_a_window_resized_from_what_the_game_asked_for(tmp_path):
    (tmp_path / "Latest.log").write_text("[display.initGL]: Requested a new surface of 1024 x 576, windowed.\n")
    game = Game(); game.dir = str(tmp_path)
    a = appmod.App(MouseSession(Backend([with_bar(1280, 720, 1)])), game, clock=Clock())
    with pytest.raises(appmod.preconditions.PreconditionFailed, match="window_size_as_requested: the game asked for a 1024x576 window"):
        a.title_menu.select("Game Options")
    assert a.session.clicks == []
    (tmp_path / "Latest.log").write_text("[display.initGL]: Requested a new surface of 1280 x 720, windowed.\n")
    a.title_menu.select("Game Options")
    assert len(a.session.clicks) == 1


def test_settled_item_waits_for_a_highlight_that_is_still_moving():
    a = make([with_bar(1280, 720, 1)] * 3)
    assert a.title_menu.wait_until_displayed().settled_item() == "Start New Commander"
    a = make([with_bar(1280, 720, 2), with_bar(1280, 720, 3)] + [with_bar(1280, 720, 4)] * 12)
    assert a.title_menu.settled_item() == "Game Options"


def test_keys_follow_pointer_puts_the_pointer_on_the_game_first():
    """Headless weston gives no window keyboard focus (PointerRoot): keys go to the window under the pointer, so it goes to the game's
    middle before each key. Elsewhere the pointer is left alone (#47)."""
    import types
    from oolite_ui_test_framework import session as sessmod

    class XBackend:
        def __init__(self): self.calls = []
        def find_window(self): return 42
        def abs_geom(self, w): return (1472, 92, 1280, 720)
        def mouse_move(self, w, x, y): self.calls.append(("move", w, x, y))
        def key_down(self, k): self.calls.append(("down", k))
        def send_key(self, k, w=None): self.calls.append(("key", k))

    for follow, want in ((True, [("move", 42, 640, 360), ("down", "Down"), ("move", 42, 640, 360), ("key", "F12")]), (False, [("down", "Down"), ("key", "F12")])):
        s = sessmod.Session(types.SimpleNamespace(kind="wayland", keys="xtest", keys_follow_pointer=follow))
        s.backend = XBackend()
        s.key_down("Down"); s.send_key("F12")
        assert s.backend.calls == want


def test_keys_follow_pointer_puts_the_pointer_on_the_game_first():
    """Headless weston gives no window keyboard focus (PointerRoot): keys go to the window under the pointer, so it goes to the game's
    middle before each key. Elsewhere the pointer is left alone (#47)."""
    import types
    from oolite_ui_test_framework import session as sessmod

    class XBackend:
        def __init__(self): self.calls = []
        def find_window(self): return 42
        def abs_geom(self, w): return (1472, 92, 1280, 720)
        def mouse_move(self, w, x, y): self.calls.append(("move", w, x, y))
        def key_down(self, k): self.calls.append(("down", k))
        def send_key(self, k, w=None): self.calls.append(("key", k))

    for follow, want in ((True, [("move", 42, 640, 360), ("down", "Down"), ("move", 42, 640, 360), ("key", "F12")]), (False, [("down", "Down"), ("key", "F12")])):
        s = sessmod.Session(types.SimpleNamespace(kind="wayland", keys="xtest", keys_follow_pointer=follow))
        s.backend = XBackend()
        s.key_down("Down"); s.send_key("F12")
        assert s.backend.calls == want
