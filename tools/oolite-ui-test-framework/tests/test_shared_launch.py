"""shared_launch: one game launch shared by several tests, dirty detection, relaunch and the warning in the report. FakeGame stands in
for the game; no pytest plugin, display or game."""
import types

import pytest

from oolite_ui_test_framework import shared_launch, report


class FakeGame:
    """A fake running game: window state and liveness can be changed by 'tests'."""
    def __init__(self): self.launches = 0; self.state = ("1280x720+0+0", 1, 1); self.alive = True; self.stopped = []

    def start(self):
        self.launches += 1; h = self.launches; self.state = ("1280x720+0+0", 1, 1); self.alive = True
        return h, {"frame": 1, "focus": 1, "launch": h}

    def make(self, warns):
        return shared_launch.SharedLaunch(self.start, lambda h: self.stopped.append(h), lambda h: self.alive, lambda: self.state, warns.append)


def test_clean_test_leaves_launch_alone():
    g = FakeGame(); warns = []; sl = g.make(warns)
    assert sl.verify("test_has_frame") and not sl.ensure_clean() and g.launches == 1 and warns == []


def test_dirty_launch_is_detected_warned_and_relaunched_before_next_test():
    g = FakeGame(); warns = []; sl = g.make(warns)
    g.state = ("3840x1080+0+0", 1, 0)                 # a test left the game fullscreen
    assert not sl.verify("test_goes_fullscreen")
    assert warns == ["state not restored by test_goes_fullscreen"] and sl.dirty_by == "test_goes_fullscreen"
    assert sl.ensure_clean() and g.launches == 2 and g.stopped == [1] and sl["launch"] == 2 and sl.dirty_by is None
    assert sl.verify("test_next") and sl.relaunches == 1


def test_game_that_died_is_dirty():
    g = FakeGame(); warns = []; sl = g.make(warns); g.alive = False
    assert not sl.verify("test_crashes_it") and "test_crashes_it" in warns[0]


def test_focus_change_counts_as_dirty():
    g = FakeGame(); warns = []; sl = g.make(warns); g.state = ("1280x720+0+0", 0, 1)
    assert not sl.verify("test_steals_focus")


def test_temporarily_restores_even_when_the_test_fails():
    g = FakeGame(); sl = g.make([]); log = []
    with pytest.raises(RuntimeError):
        with sl.temporarily(lambda: log.append("change"), lambda: log.append("restore")):
            raise RuntimeError("test failed")
    assert log == ["change", "restore"]


def test_restored_state_is_not_dirty():
    g = FakeGame(); sl = g.make([])
    def change(): g.state = ("3840x1080+0+0", 1, 0)
    def restore(): g.state = ("1280x720+0+0", 1, 1)
    with sl.temporarily(change, restore): pass
    assert sl.verify("test_ok")


def test_xdist_with_several_workers_is_refused():
    cfg = lambda n: types.SimpleNamespace(option=types.SimpleNamespace(numprocesses=n))
    shared_launch.check_no_xdist(cfg(None)); shared_launch.check_no_xdist(cfg(0)); shared_launch.check_no_xdist(cfg(1))
    for n in (2, 4, "auto"):
        with pytest.raises(pytest.UsageError, match="sequentially"):
            shared_launch.check_no_xdist(cfg(n))


def test_warning_reaches_the_report(tmp_path):
    raw = tmp_path / "w.raw"
    raw.write_text("WARN wm=marco build=opt1c run=2 text=state not restored by test_goes_fullscreen\n"
                   + "\n".join("RESULT wm=marco build=%s screen=3840x1080 run=%d frame=1 focus=1 dx=0 dy=0 centred=1 exited=0 tol=40" % (b, i)
                               for b in ("base", "opt1c") for i in range(1, 4)) + "\n")
    out = tmp_path / "o.md"; report.main([str(raw), str(out), "--control", "base", "--minruns", "3"])
    md = out.read_text()
    assert "## Warnings" in md and "state not restored by test_goes_fullscreen" in md and md.index("## Warnings") < md.index("## Coverage")


def test_suspend_stops_the_game_and_the_next_shared_test_relaunches_it():
    """A private launch suspends the shared game so only one game runs; the next test that uses the shared launch gets it back."""
    g = FakeGame(); sl = g.make([])
    sl.suspend()
    assert sl.handle is None and len(g.stopped) == 1
    assert sl.ensure_clean() is True and sl.handle is not None and g.launches == 2
    sl.suspend(); sl.close()
    assert len(g.stopped) == 2          # close after suspend does not stop twice
