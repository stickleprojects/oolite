"""Scenarios, written once and run in every environment. They only RECORD raw observations (a dict per run, RESULT fields);
geometry.apply() turns geometry into dx/dy/centred later. Timing is the same as trial.sh: sample every 0.5 s for 14 s,
splash = first sighting, post = first sample 2 s after the window size first changes, end = state at 14 s."""
import os
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass

from . import geometry
from .window_probes import Obs


@dataclass
class Opts:
    wait: float = 14.0
    sample: float = 0.5
    post_delay: float = 2.0
    tol: int = geometry.DEFAULT_TOL
    toggle: bool = False


class Clock:
    monotonic = staticmethod(time.monotonic)
    sleep = staticmethod(time.sleep)


# Turns on the game's own key-press log lines ("Keydown scancode = ..."), so <name>.logs/ shows whether a key reached the game.
# A loose logcontrol.plist in an AddOns folder overrides the built-in log settings (src/Core/OOLogging.m).
KEY_LOGGING_PLIST = "{\n\tinput.keyMapping.keyPress = yes;\n}\n"


def add_key_logging(run_dir):
    """Write GameData/AddOns/logcontrol.plist into the run folder (the AppImage uses the GameData folder next to it), unless one exists."""
    path = os.path.join(run_dir, "GameData", "AddOns", "logcontrol.plist")
    if os.path.exists(path): return
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f: f.write(KEY_LOGGING_PLIST)


class Game:
    """The AppImage in a fresh copy of its folder (other AppImages left out), so GameData is per run.
    keep_log: path to copy the game's Latest.log to on stop (the run folder is deleted)."""
    def __init__(self, app, args=(), env=None, keep_log=None):
        self.app = os.path.realpath(app); self.args = list(args); self.env = env or {}; self.dir = None; self.proc = None; self.keep_log = keep_log

    def start(self):
        self.dir = tempfile.mkdtemp(prefix="uitest-run.", dir="/tmp")
        src = os.path.dirname(self.app)
        for n in os.listdir(src):
            if n.endswith(".AppImage"): continue
            p = os.path.join(src, n)
            shutil.copytree(p, os.path.join(self.dir, n)) if os.path.isdir(p) else shutil.copy2(p, self.dir)
        shutil.copy2(self.app, self.dir)
        add_key_logging(self.dir)
        env = dict(os.environ); env.update(self.env); env["APPIMAGE_EXTRACT_AND_RUN"] = "1"
        self.log = open(os.path.join(self.dir, "out.log"), "w")
        self.proc = subprocess.Popen(["./" + os.path.basename(self.app)] + self.args, cwd=self.dir, env=env, stdout=self.log, stderr=subprocess.STDOUT,
                                     start_new_session=True)
        return self

    def alive(self):
        return subprocess.run(["pgrep", "-f", "appimage_extracted"], capture_output=True).returncode == 0

    def stop(self, sleep=time.sleep):
        for pat in ("appimage_extracted", r"/tmp/uitest-run\."): subprocess.run(["pkill", "-f", pat], capture_output=True)
        sleep(2)
        subprocess.run(["pkill", "-9", "-f", "appimage_extracted"], capture_output=True)
        if self.dir and self.keep_log: self.save_log(self.keep_log)
        if self.dir: shutil.rmtree(self.dir, ignore_errors=True)

    def save_log(self, dest):
        for root, _, files in os.walk(self.dir):
            if "Latest.log" in files:
                try:
                    os.makedirs(os.path.dirname(dest) or ".", exist_ok=True); shutil.copy2(os.path.join(root, "Latest.log"), dest)
                except OSError: pass
                return


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
    rec.update(frame=o.framed, focus=o.focused, exited=0, outer=geometry.fmt_geom(o.outer), mon=geometry.fmt_geom(mon),
               splash_outer=geometry.fmt_geom(spl), post_outer=geometry.fmt_geom(post), centred=o.centred, source=o.source or None)
    rec["client"] = geometry.fmt_geom(o.client) if o.client else None
    if o.asked: rec["asked"] = ",".join("%s:%s" % (k, v) for k, v in o.asked.items())
    return rec


def _hold(session, key, clock, seconds=1.0):
    """Press `key` and hold it for about one frame of the slow software-GL game (a tap shorter than a frame is never seen by it)."""
    session.key_down(key); clock.sleep(session.hold_time(seconds)); session.key_up(key)


def run_toggle(session, game, opts=Opts(), clock=Clock, shoot=lambda stage: None):
    """F12 = toggleScreenMode: windowed -> fullscreen -> windowed, then measure again. Returns t_* fields (geometry in t_outer).
    shoot(stage) is called at "before", "fullscreen" and "after" (screenshots)."""
    ok = 0; method = "key"; t = {}
    win = session.window_id()
    if win is not None:
        s0 = _size(session.observe(cheap_only=True)); shoot("before")
        _hold(session, "F12", clock); clock.sleep(3); s1 = _size(session.observe(cheap_only=True))
        if s1 == s0:
            session.send_key("F12", win); method = "sendevent"; clock.sleep(3); s1 = _size(session.observe(cheap_only=True))
        if s1 != s0:
            ok = 1; shoot("fullscreen")
            if method == "sendevent": session.send_key("F12", win)
            else: _hold(session, "F12", clock)
            clock.sleep(4)
    t["t_ok"] = ok; t["t_method"] = method
    if ok: shoot("after")
    # a full observation, as after startup: on XWayland only the compositor probe sees the frame (the X11 probe needs reparenting)
    o = session.observe() if ok else None
    if ok and o is not None:
        t.update(t_frame=o.framed, t_focus=o.focused, t_outer=geometry.fmt_geom(o.outer))
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
    return geometry.apply(rec, opts.tol)
