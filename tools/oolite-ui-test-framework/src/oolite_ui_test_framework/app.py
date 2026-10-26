"""The running game as seen by a test (page-object style): the App holds the window, screenshots, waiting and key sending;
the screens live in ui/pages/. A scenario-style handle on a running game: launch, wait for a screen, look at it, press keys. Tests read like the steps a person takes.

    def test_title_menu(app):
        menu = app.title_menu.wait_until_displayed().menu
        assert menu.selected_item == "Start New Commander"
        menu.select("View Ship Library")

Driving is by X key events and the check is on what is actually drawn in the window, so a game that believes it is showing a menu
while the window is blank, frozen or transparent fails here. Waits return as soon as the condition is true (no fixed sleeps)."""
import os
import time

from . import png, render_check, screen
from .ui import pages


class ScenarioFailed(AssertionError):
    pass


class NotMeasurable(Exception):
    """The environment cannot grab window contents (e.g. native Wayland): the test is skipped, never failed."""


class App:
    def __init__(self, session, game, shots_dir="", name="shot", poll=0.25, timeout=20.0, clock=time, ocr=None):
        self.session, self.game, self.shots_dir, self.name = session, game, shots_dir, name
        self.poll, self.timeout, self.clock, self.ocr = poll, timeout, clock, ocr
        self.last = None; self._n = 0

    # ---- pages (one per game screen, see ui/pages/)
    @property
    def title_menu(self):
        return pages.TitleMenuPage(self)

    # ---- looking
    def _grab(self):
        b = self.session.backend; grab = getattr(b, "grab", None)
        if grab is None: raise NotMeasurable("no screenshot support in this environment")
        w = self.session.window_id()
        return screen.Shot.from_grab(grab(w)) if w else None

    def screenshot(self, label=None):
        """The window as drawn now (None while there is no window). Saved as PNG when a shots directory is set."""
        s = self._grab()
        if s is not None:
            self.last = s
            if self.shots_dir and label:
                os.makedirs(self.shots_dir, exist_ok=True)
                png.write_png(os.path.join(self.shots_dir, "%s-%s.png" % (self.name, label)), s.w, s.h, s.rgb)
        return s

    def describe(self):
        """What the last screenshot looked like, for failure messages."""
        s = self.last
        if s is None: return "no game window was found"
        a = render_check.analyse(s.rgb, s.w, s.h)
        return "the window looks %s (colours=%s, std=%s)" % (a["verdict"], a["colours"], a["std"])

    # ---- waiting
    def wait_until(self, cond, what, timeout=None):
        """Poll cond() until it is true; fail with `what` and the last screen description after the timeout. Returns the seconds it took."""
        t0 = self.clock.monotonic(); limit = self.timeout if timeout is None else timeout
        while True:
            if cond(): return self.clock.monotonic() - t0
            if self.game.proc is not None and self.game.proc.poll() is not None: raise ScenarioFailed("the game exited while waiting for: %s" % what)
            if self.clock.monotonic() - t0 >= limit: raise ScenarioFailed("timed out after %.0f s waiting for: %s (%s)" % (limit, what, self.describe()))
            self.clock.sleep(self.poll)

    # ---- driving
    def send_keys(self, *keys, gap=0.3):
        # no target window: the key goes through XTEST to whatever has keyboard focus, like a real keypress (a window without focus gets nothing)
        for k in keys:
            self.session.send_key(k); self.clock.sleep(gap)

    def hold_key(self, key, seconds):
        """Hold `key` down for `seconds`, then release it. The game reads the keyboard once per frame (slow with software rendering), so a tap
        shorter than a frame is missed, and holding for too long starts the key repeat (about 1 s is one menu step in the Docker images)."""
        self.session.key_down(key)
        try:
            self.clock.sleep(self.session.hold_time(seconds))
        finally:
            self.session.key_up(key)
