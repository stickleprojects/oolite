"""Host mode (#15): the pytest tests run on the host with a venv's pytest, X measured by the helper container. No desktop, no Docker:
the helper, the venv commands and pytest are replaced by fakes."""
import os

import pytest

from oolite_ui_test_framework import hostrun, registry, session as sessmod, window_probes


class FakeHelper:
    """The helper container's view of the host display."""
    def __init__(self, container, repeat=True):
        self.container = container; self.repeat = repeat; self.calls = []; self.closed = False
    def monitors(self): return [(0, 0, 2560, 1440, True)]
    def autorepeat_on(self): return self.repeat
    def autorepeat_off(self): self.calls.append("off"); self.repeat = False
    def autorepeat_restore(self): self.calls.append("restore"); self.repeat = True
    def observe(self): return None
    def close(self): self.closed = True


def host_session(monkeypatch, name, repeat=True):
    monkeypatch.setenv("DISPLAY", ":0")
    helpers = []
    def make(ct):
        h = FakeHelper(ct, repeat); helpers.append(h); return h
    monkeypatch.setattr(window_probes, "HelperBackend", make)
    monkeypatch.setattr(window_probes, "make_probe", lambda *a, **k: window_probes.NullProbe())
    s = sessmod.Session(registry.load()[0][name], "host", sleep=lambda s: None, helper="uitest-helper").start()
    return s, helpers[0]


def test_host_session_turns_the_desktops_key_repeat_off_and_back_on(monkeypatch):
    s, h = host_session(monkeypatch, "host-x11")
    assert h.container == "uitest-helper" and s.primary == (0, 0, 2560, 1440) and h.calls == ["off"]
    s.stop()
    assert h.calls == ["off", "restore"] and h.repeat and h.closed


def test_host_session_leaves_key_repeat_off_if_it_was_off(monkeypatch):
    s, h = host_session(monkeypatch, "host-x11", repeat=False)
    s.stop()
    assert h.calls == [] and not h.repeat


def test_host_python_makes_the_venv_once_and_never_uses_the_hosts_pip(tmp_path):
    venv = str(tmp_path / "v"); ran = []; made = []
    class R:
        def __init__(self, out="", rc=0): self.stdout = out; self.returncode = rc
    def run(cmd, **k):
        ran.append(cmd)
        if cmd[1:3] == ["-m", "venv"]: os.makedirs(os.path.join(venv, "bin")); open(os.path.join(venv, "bin", "python"), "w").close()
        if "pip" in cmd: made.append(1)
        return R(hostrun.HOST_PYTEST.split("==")[1] if made and cmd[1] == "-c" else "")
    py, why = hostrun.host_python(str(tmp_path / "log"), venv, run)
    assert (py, why) == (os.path.join(venv, "bin", "python"), "")
    pip = [c for c in ran if "pip" in c][0]
    assert pip[0] == py and pip[-1] == hostrun.HOST_PYTEST   # pip of the venv, not of the host
    ran.clear()
    assert hostrun.host_python(str(tmp_path / "log"), venv, run)[0] == py and len(ran) == 1   # second use: only the version check


def test_host_python_says_why_when_the_venv_cannot_be_made(tmp_path):
    class R:
        stdout = ""; returncode = 1
    py, why = hostrun.host_python(str(tmp_path / "log"), str(tmp_path / "v"), lambda cmd, **k: R())
    assert py is None and "could not make the host-mode venv" in why


def runner(tmp_path, *extra):
    a = tmp_path / "Oolite.AppImage"; a.write_bytes(b"x")
    return hostrun.Runner(hostrun.build_parser().parse_args(["x:%s" % a, "--out", str(tmp_path / "res"), "--host-runs", "2", "--toggle"] + list(extra)), ("x", str(a)))


class FakePopen:
    """pytest as seen by Runner.follow: it writes its raw part a line and a half at a time while running, then exits 0."""
    def __init__(self, r, part, seen, cmd, stdout, stderr, text, **kw):
        seen["cmd"] = cmd; seen["env"] = kw.get("env"); stdout.write("3 passed\n")
        self.r, self.part, self.seen, self.n, self.returncode, self.terminated = r, os.path.join(r.parts, part), seen, 0, None, False
    def poll(self):
        self.n += 1
        if self.n == 1: open(self.part, "a").write("RESULT wm=host-x11 build=x run=1\nTEST wm=host-x11 bu")   # second line half written
        elif self.n == 2:
            self.seen["raw_mid_run"] = open(self.r.raw).read(); open(self.part, "a").write("ild=x run=1 test=t outcome=passed\n")
        else: self.returncode = 0
        return self.returncode
    def terminate(self): self.terminated = True; self.returncode = -15
    def wait(self, t=None): return self.returncode


def fake_popen(monkeypatch, r, part, seen):
    monkeypatch.setattr(hostrun.time, "sleep", lambda s: None)
    monkeypatch.setattr(hostrun.subprocess, "Popen", lambda cmd, **k: seen.setdefault("p", FakePopen(r, part, seen, cmd, **k)))


def test_host_cell_runs_every_pytest_test_on_the_host(tmp_path, monkeypatch):
    r = runner(tmp_path, "--no-prompt"); seen = {}
    monkeypatch.setattr(hostrun, "host_python", lambda log: ("/venv/bin/python", ""))
    fake_popen(monkeypatch, r, "host-x11-2560x1440.raw", seen)
    r.host_cell("host-x11", "2560x1440", "uitest-helper")
    c = seen["cmd"]
    assert c[:3] == ["/venv/bin/python", "-m", "pytest"] and hostrun.GAME_TESTS in c and "--ui-toggle" in c and "--ui-no-prompt" in c
    assert c[c.index("--ui-helper") + 1] == "uitest-helper" and c[c.index("--ui-runs") + 1] == "2" and "--ui-app=" + r.path in c
    assert c[c.index("--ui-raw") + 1] == os.path.join(r.out, "%s.parts/host-x11-2560x1440.raw" % r.name)
    assert seen["env"]["PYTHONPATH"] == os.path.join(hostrun.PKG, "src") and seen["env"]["PYTHONDONTWRITEBYTECODE"] == "1"   # no __pycache__ in tests/ui
    assert "RESULT wm=host-x11" in open(r.raw).read()


def test_results_reach_the_result_set_while_pytest_runs(tmp_path, monkeypatch):
    """Whole lines are copied in as they appear, a half-written line waits, and nothing is copied twice."""
    r = runner(tmp_path); seen = {}
    fake_popen(monkeypatch, r, "p.raw", seen); open(os.path.join(r.parts, "p.raw"), "w").close()
    res, done = r.follow(["pytest"], "p.raw")
    r.collect("host-x11", "2560x1440", "p.raw", res, done)
    assert "RESULT wm=host-x11 build=x run=1" in seen["raw_mid_run"] and "TEST" not in seen["raw_mid_run"]
    raw = open(r.raw).read()
    assert raw.count("RESULT wm=host-x11") == 1 and raw.count("TEST wm=host-x11 build=x run=1 test=t outcome=passed\n") == 1
    assert res.returncode == 0 and res.stdout == "3 passed\n"


def test_stopping_uitest_stops_its_pytest(tmp_path, monkeypatch):
    """Ctrl-C in uitest: the pytest (docker run, which passes the signal to the container) is terminated, and what it wrote is kept."""
    r = runner(tmp_path); seen = {}
    fake_popen(monkeypatch, r, "p.raw", seen); open(os.path.join(r.parts, "p.raw"), "w").close()
    def interrupt(s): raise KeyboardInterrupt
    monkeypatch.setattr(hostrun.time, "sleep", interrupt)
    with pytest.raises(KeyboardInterrupt): r.follow(["pytest"], "p.raw")
    assert seen["p"].terminated and "RESULT wm=host-x11" in open(r.raw).read()


def test_host_cell_without_the_venv_runs_the_startup_checks_and_says_so(tmp_path, monkeypatch):
    r = runner(tmp_path); ran = []
    monkeypatch.setattr(hostrun, "host_python", lambda log: (None, "no network"))
    monkeypatch.setattr(hostrun.Runner, "host_inprocess", lambda self, env, scr, helper=None: ran.append((env, helper)))
    r.host_cell("host-x11", "2560x1440", "uitest-helper")
    assert ran == [("host-x11", "uitest-helper")]
    warn = [l for l in open(r.raw).read().splitlines() if l.startswith("WARN ")]
    assert len(warn) == 1 and "only the startup checks ran" in warn[0] and "no network" in warn[0]
