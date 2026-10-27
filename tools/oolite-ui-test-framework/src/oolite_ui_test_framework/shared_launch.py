"""A game launch shared by several tests (fixture `launched_game`), with dirty detection.

Tests that share the launch are read-only by default. A test MAY change game state if the change is undone by a fixture / context manager
(`with launched_game.temporarily(change, restore): ...`) that restores even when the test fails. After every test the shared launch runs a cheap
baseline check (game alive, same window geometry / fullscreen state, same focus). If it differs the launch is DIRTY: it is relaunched before the
next test and a warning naming the guilty test goes into the report, so a leftover state never skews later tests silently.
Pure logic: no pytest, no display (callables are injected), so it is unit-tested with fakes."""
import contextlib


class SharedLaunch(dict):
    """dict = the startup record (what the checks inspect). Callables: start() -> (handle, record); stop(handle); alive(handle) -> bool;
    state() -> hashable snapshot of the window (geometry, focus) or None when it cannot be observed; warn(text)."""
    def __init__(self, start, stop, alive, state, warn=lambda t: None):
        super().__init__()
        self._start, self._stop, self._alive, self._state, self._warn = start, stop, alive, state, warn
        self.handle = None; self.baseline = None; self.dirty_by = None; self.relaunches = 0
        self.launch()

    def launch(self):
        self.handle, rec = self._start()
        self.clear(); self.update(rec)
        self.baseline = self._state()

    def ok(self):
        """The baseline check: alive, and the observable window state equals the baseline."""
        return bool(self._alive(self.handle)) and self._state() == self.baseline

    def verify(self, test):
        """After a test: mark dirty (and warn) if the baseline check fails. Returns True when still clean."""
        if self.ok(): return True
        self.dirty_by = test; self._warn("state not restored by %s" % test)
        return False

    def suspend(self):
        """Stop the game so a private launch (fresh_game, app) runs alone; the next test that uses it relaunches it (ensure_clean)."""
        if self.handle is not None: self._stop(self.handle); self.handle = None

    def ensure_clean(self):
        """Before a test: relaunch if the game was suspended or the previous test left it dirty."""
        if self.handle is None: self.relaunches += 1; self.dirty_by = None; self.launch(); return True
        if self.dirty_by is None: return False
        self._stop(self.handle); self.relaunches += 1; self.dirty_by = None; self.launch()
        return True

    @contextlib.contextmanager
    def temporarily(self, change, restore):
        """Change state for the body of the with-block and ALWAYS restore (also when the test fails)."""
        try:
            change(); yield self
        finally:
            restore()

    def close(self):
        self.suspend()


def check_no_xdist(config):
    """uitest tests run sequentially: one display / WM per container, focus and timing are global. Refuse xdist with more than one worker."""
    n = getattr(config.option, "numprocesses", None)
    if n not in (None, 0, 1, "0", "1"):
        import pytest
        raise pytest.UsageError("uitest tests must run sequentially (one display and one window manager per container; focus and timing are global): "
                                "do not use pytest-xdist (-n %s)" % n)
