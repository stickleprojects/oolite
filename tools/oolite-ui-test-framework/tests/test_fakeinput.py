"""fakeinput: evdev codes and the commands sent to the uitest-fakeinput process (no compositor needed)."""
import io

import pytest

from oolite_ui_test_framework import fakeinput


def test_key_names_map_to_evdev_codes():
    assert [fakeinput.code(k) for k in ("F12", "F11", "Down", "Return", "F1")] == [88, 87, 108, 28, 59]
    with pytest.raises(ValueError): fakeinput.code("NoSuchKey")


class P:
    """A uitest-fakeinput that answers every command with `reply`."""
    def __init__(self, reply="ok\n"):
        self.stdin = io.StringIO(); self.reply = reply; self.alive = True
    @property
    def stdout(self): return io.StringIO(self.reply)
    def poll(self): return None if self.alive else 0


@pytest.fixture
def started(monkeypatch):
    monkeypatch.setattr(fakeinput, "_proc", None)
    calls = []
    yield calls
    monkeypatch.setattr(fakeinput, "_proc", None)


def test_one_process_takes_keys_and_mouse(started):
    p = P()
    popen = lambda cmd, **kw: started.append(cmd) or p
    fakeinput.key_down("F12", popen=popen); fakeinput.key_up("F12", popen=popen)
    fakeinput.mouse_move(640.4, 360, popen=popen); fakeinput.mouse_down(popen=popen); fakeinput.mouse_up(popen=popen)
    assert started == [["uitest-fakeinput"]]                                   # started once, reused
    assert p.stdin.getvalue().splitlines() == ["press 88", "release 88", "move 640 360", "down 272", "up 272"]


def test_a_dead_process_is_restarted(started):
    first, second = P(), P()
    procs = iter([first, second])
    popen = lambda cmd, **kw: started.append(cmd) or next(procs)
    fakeinput.key_down("Down", popen=popen)
    first.alive = False
    fakeinput.key_up("Down", popen=popen)
    assert len(started) == 2 and second.stdin.getvalue() == "release 108\n"


def test_an_error_reply_raises(started):
    with pytest.raises(RuntimeError, match="no absolute motion"):
        fakeinput.mouse_move(1, 2, popen=lambda cmd, **kw: P("error fake_input has no absolute motion (needs v2)\n"))


def test_session_moves_the_pointer_to_the_window_position_plus_the_point(monkeypatch):
    import types
    from oolite_ui_test_framework import session as sessmod
    s = sessmod.Session.__new__(sessmod.Session)
    s.env = types.SimpleNamespace(keys="fakeinput")
    s.backend = types.SimpleNamespace(find_window=lambda: 7, abs_geom=lambda w: (100, 50, 800, 600) if w == 7 else None)
    s.primary = (0, 0, 1280, 720)
    sent = []
    monkeypatch.setattr(fakeinput, "send", lambda c, **kw: sent.append(c))
    s.mouse_move(10, 20); s.mouse_down(); s.mouse_up()
    assert sent == ["move 110 70", "down 272", "up 272"]


def test_virtual_mode_uses_the_wlroots_injector_with_the_same_commands(started, monkeypatch):
    """keys = "virtual" (sway native, #44): uitest-wlrinput takes the same commands; switching mode stops the other process."""
    monkeypatch.setattr(fakeinput, "_binary", fakeinput.BINARY)
    p = P(); p.wait = lambda timeout=None: 0; popen = lambda cmd, **kw: started.append(cmd) or p
    fakeinput.select("virtual"); fakeinput.key_down("F12", popen=popen)
    fakeinput.select("virtual"); fakeinput.mouse_move(10, 20, popen=popen)
    assert started == [["uitest-wlrinput"]] and p.stdin.getvalue().splitlines() == ["press 88", "move 10 20"]
    fakeinput.select("fakeinput"); assert fakeinput._proc is None and fakeinput._binary == "uitest-fakeinput"
