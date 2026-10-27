"""fakeinput: evdev codes and the start/stop of the key-holding process (no compositor needed)."""
import io
import signal

import pytest

from oolite_ui_test_framework import fakeinput


def test_key_names_map_to_evdev_codes():
    assert [fakeinput.code(k) for k in ("F12", "F11", "Down", "Return", "F1")] == [88, 87, 108, 28, 59]
    with pytest.raises(ValueError): fakeinput.code("NoSuchKey")


class P:
    pid = 4242
    stdout = io.BytesIO(b"down\n")


def test_down_starts_the_holder_and_up_stops_it(tmp_path, monkeypatch):
    monkeypatch.setattr(fakeinput, "PIDS", str(tmp_path / "k%d.pid"))
    started = []
    fakeinput.key_down("F12", popen=lambda cmd, **kw: started.append(cmd) or P(), sleep=lambda s: None)
    assert started == [["uitest-fakekey", "88"]]
    killed = []
    fakeinput.key_up("F12", kill=lambda pid, sig: killed.append((pid, sig)))
    assert killed == [(4242, signal.SIGTERM)]
    fakeinput.key_up("F12", kill=lambda *a: killed.append("again"))          # already released: nothing to do
    assert killed == [(4242, signal.SIGTERM)]
