"""Scenarios, written once and run in every environment. They only RECORD raw observations (a dict per run, RESULT fields);
checks.apply() turns geometry into dx/dy/centred later. Timing is the same as trial.sh: sample every 0.5 s for 14 s,
splash = first sighting, post = first sample 2 s after the window size first changes, end = state at 14 s."""
import os
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass

from . import checks
from .probes import Obs


@dataclass
class Opts:
    wait: float = 14.0
    sample: float = 0.5
    post_delay: float = 2.0
    tol: int = checks.DEFAULT_TOL
    toggle: bool = False


class Clock:
    monotonic = staticmethod(time.monotonic)
    sleep = staticmethod(time.sleep)


class Game:
    """The AppImage in a fresh copy of its folder (other AppImages left out), so GameData is per run."""
    def __init__(self, app, args=(), env=None):
        self.app = os.path.realpath(app); self.args = list(args); self.env = env or {}; self.dir = None; self.proc = None

    def start(self):
        self.dir = tempfile.mkdtemp(prefix="wmtrun.", dir="/tmp")
        src = os.path.dirname(self.app)
        for n in os.listdir(src):
            if n.endswith(".AppImage"): continue
            p = os.path.join(src, n)
            shutil.copytree(p, os.path.join(self.dir, n)) if os.path.isdir(p) else shutil.copy2(p, self.dir)
        shutil.copy2(self.app, self.dir)
        env = dict(os.environ); env.update(self.env); env["APPIMAGE_EXTRACT_AND_RUN"] = "1"
        self.log = open(os.path.join(self.dir, "out.log"), "w")
        self.proc = subprocess.Popen(["./" + os.path.basename(self.app)] + self.args, cwd=self.dir, env=env, stdout=self.log, stderr=subprocess.STDOUT,
                                     start_new_session=True)
        return self

    def alive(self):
        return subprocess.run(["pgrep", "-f", "appimage_extracted"], capture_output=True).returncode == 0

    def stop(self, sleep=time.sleep):
        for pat in ("appimage_extracted", r"/tmp/wmtrun\."): subprocess.run(["pkill", "-f", pat], capture_output=True)
        sleep(2)
        subprocess.run(["pkill", "-9", "-f", "appimage_extracted"], capture_output=True)
        if self.dir: shutil.rmtree(self.dir, ignore_errors=True)


def _size(o):
    return None if o is None or o.outer is None else (o.outer[2], o.outer[3])


def run_startup(session, game, opts=Opts(), clock=Clock):
    """Sample for opts.wait seconds, then take the final observation. Returns the raw record (geometry strings; no dx/dy yet)."""
    t0 = clock.monotonic(); fsize = None; chg = None; spl = None; post = None
    while True:
        el = (clock.monotonic() - t0) * 1000
        if el >= opts.wait * 1000: break
        o = session.observe(cheap_only=True)
        if o is not None and o.outer is not None:
            if spl is None: spl = o.outer; fsize = _size(o)
            if chg is None and _size(o) != fsize: chg = el
            if chg is not None and post is None and el >= chg + opts.post_delay * 1000: post = o.outer
        clock.sleep(opts.sample)
    rec = {"tol": opts.tol}
    if not session.window_present(game):
        rec.update(frame=0, focus=0, centred=0, exited=1, dx=None, dy=None)
        return rec
    o = session.observe() or Obs()
    mon = o.mon or session.primary
    rec.update(frame=o.framed, focus=o.focused, exited=0, outer=checks.fmt_geom(o.outer), mon=checks.fmt_geom(mon),
               splash_outer=checks.fmt_geom(spl), post_outer=checks.fmt_geom(post), centred=o.centred, source=o.source or None)
    rec["client"] = checks.fmt_geom(o.client) if o.client else None
    if o.asked: rec["asked"] = ",".join("%s:%s" % (k, v) for k, v in o.asked.items())
    return rec


def _hold(session, key, clock, seconds=1.0):
    """Press `key` and hold it for about one frame of the slow software-GL game (a tap shorter than a frame is never seen by it)."""
    session.key_down(key); clock.sleep(seconds); session.key_up(key)


def _hold_until_resized(session, key, clock, was, limit=4.0, step=0.1):
    """Hold `key` until the window size differs from `was`, then release at once. A key held for a fixed time autorepeats, and the game
    toggles on every repeat, so how many times it toggled (odd or even) would decide the result."""
    session.key_down(key); end = clock.monotonic() + limit
    while clock.monotonic() < end:
        clock.sleep(step)
        if _size(session.observe(cheap_only=True)) != was: break
    session.key_up(key)


def run_toggle(session, game, opts=Opts(), clock=Clock):
    """F12 = toggleScreenMode: windowed -> fullscreen -> windowed, then measure again. Returns t_* fields (geometry in t_outer)."""
    ok = 0; method = "key"; t = {}
    win = session.window_id()
    if win is not None:
        s0 = _size(session.observe(cheap_only=True))
        _hold_until_resized(session, "F12", clock, s0); clock.sleep(3); s1 = _size(session.observe(cheap_only=True))
        if s1 == s0:
            session.send_key("F12", win); method = "sendevent"; clock.sleep(3); s1 = _size(session.observe(cheap_only=True))
        if s1 != s0:
            ok = 1
            if method == "sendevent": session.send_key("F12", win)
            else: _hold_until_resized(session, "F12", clock, s1)
            clock.sleep(4)
    t["t_ok"] = ok; t["t_method"] = method
    o = session.observe(cheap_only=True) if ok else None
    if ok and o is not None:
        t.update(t_frame=o.framed, t_focus=o.focused, t_outer=checks.fmt_geom(o.outer))
    else:
        t.update(t_frame=0, t_focus=0, t_dx=None, t_dy=None, t_centred=0)
    return t


def record(session, game, wm, build, screen, run, opts=Opts(), clock=Clock):
    """One full run -> final RESULT record (with checks applied at opts.tol). The caller starts and stops the game."""
    rec = run_startup(session, game, opts, clock)
    if opts.toggle and session.backend is not None and not rec.get("exited"): rec.update(run_toggle(session, game, opts, clock))
    elif opts.toggle and session.backend is not None: rec.update(t_ok=0, t_method="key", t_frame=0, t_focus=0, t_dx=None, t_dy=None, t_centred=0)
    rec.update(wm=wm, build=build, screen=screen, run=run)
    rec.setdefault("dx", None); rec.setdefault("dy", None)
    if rec.get("exited"): rec.setdefault("splash_dx", None); rec.setdefault("post_dx", None)
    return checks.apply(rec, opts.tol)
