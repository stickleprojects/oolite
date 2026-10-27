"""Scenarios, written once and run in every environment. They only RECORD raw observations (a dict per run, RESULT fields);
geometry.apply() turns geometry into dx/dy/centred later. Startup samples every 0.5 s: splash = first sighting, post = first sample 2 s
after the window size first changes, end = the state once it has not changed for `settle` s after post (at most 14 s, as trial.sh)."""
import os
import re
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
    settle: float = 3.0   # stop sampling once post is taken and the window has not changed for this long; 0 = always sample for `wait`
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


WINDOW = (1280, 720)          # the windowed size a test asks for where it fits the screen
SMALL_WINDOW = (800, 600)     # otherwise
FRAME_ROOM = (16, 64)         # left on the screen for the window manager's borders and title bar
OVERSIZE = 256                # how much larger than the screen the 'saved window larger than the screen' case asks for (#10)


def window_size_for(screen, oversize=False):
    """The windowed size a test sets as the game's saved size, so results do not depend on whatever a previous real run saved in
    GameData/oolite.plist: WINDOW where it fits `screen` (x, y, w, h) with room for a frame, else SMALL_WINDOW. oversize: larger than
    the screen on purpose, as for a player who saved a window on a bigger screen."""
    if not screen: return WINDOW
    sw, sh = screen[2:4]
    if oversize: return (sw + OVERSIZE, sh + OVERSIZE)
    fits = WINDOW[0] + FRAME_ROOM[0] <= sw and WINDOW[1] + FRAME_ROOM[1] <= sh
    return WINDOW if fits else SMALL_WINDOW


def set_window_size(run_dir, size):
    """Write size as the saved window size in the run folder's GameData/oolite.plist (an old-style plist), keeping the other keys."""
    path = os.path.join(run_dir, "GameData", "oolite.plist")
    text = open(path).read() if os.path.exists(path) else "{\n}\n"
    for key, v in (("window_width", size[0]), ("window_height", size[1])):
        entry = '"%s" = %d;' % (key, v)
        text, n = re.subn(r'"?%s"?\s*=\s*\d+;' % key, entry, text)
        if not n: text = text[:text.rindex("}")] + "    %s\n}" % entry + text[text.rindex("}") + 1:]
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f: f.write(text)


class Game:
    """The AppImage in a fresh copy of its folder (other AppImages left out), so GameData is per run.
    keep_log: path to copy the game's Latest.log to on stop (the run folder is deleted)."""
    def __init__(self, app, args=(), env=None, keep_log=None, window=None):
        self.app = os.path.realpath(app); self.args = list(args); self.env = env or {}; self.dir = None; self.proc = None; self.keep_log = keep_log
        self.window = window   # (w, h) written as the saved window size before the game starts, or None to keep GameData's

    def start(self):
        self.dir = tempfile.mkdtemp(prefix="uitest-run.", dir="/tmp")
        src = os.path.dirname(self.app)
        for n in os.listdir(src):
            if n.endswith(".AppImage"): continue
            p = os.path.join(src, n)
            shutil.copytree(p, os.path.join(self.dir, n)) if os.path.isdir(p) else shutil.copy2(p, self.dir)
        shutil.copy2(self.app, self.dir)
        add_key_logging(self.dir)
        if self.window: set_window_size(self.dir, self.window)
        env = dict(os.environ); env.update(self.env); env["APPIMAGE_EXTRACT_AND_RUN"] = "1"
        self.log = open(os.path.join(self.dir, "out.log"), "w")
        self.proc = subprocess.Popen(["./" + os.path.basename(self.app)] + self.args, cwd=self.dir, env=env, stdout=self.log, stderr=subprocess.STDOUT,
                                     start_new_session=True)
        return self

    def alive(self):
        return subprocess.run(["pgrep", "-f", "appimage_extracted"], capture_output=True).returncode == 0

    def stop(self, sleep=time.sleep, cap=2.0, poll=0.1):
        """Ask the game to quit, wait until it has gone (at most `cap` seconds), then kill whatever is left. Gone means the game AND our
        child, the AppImage runtime, which deletes its extracted copy after the game exits: a game started during that clean-up got its
        keys late (title-menu tests failed)."""
        for pat in ("appimage_extracted", r"/tmp/uitest-run\."): subprocess.run(["pkill", "-f", pat], capture_output=True)
        for _ in range(int(cap / poll)):
            if (self.proc is None or self.proc.poll() is not None) and not self.alive(): break
            sleep(poll)
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


def _toggle_size(o):
    """Size of the game's own (client) area where the probe reports it, else of the outer window. F12 must be judged on the client: a
    maximised window's frame already covers the screen, so going fullscreen only drops the title bar and the outer size stays the same
    (opt2fix with a saved window larger than the screen, #10)."""
    g = None if o is None else (o.client or o.outer)
    return None if g is None else (g[2], g[3])


def run_startup(session, game, opts=Opts(), clock=Clock):
    """Sample until the window has settled (at most opts.wait seconds), then take the final observation. Returns the raw record
    (geometry strings; no dx/dy yet)."""
    t0 = clock.monotonic(); fsize = None; chg = None; spl = None; post = None; last = None; since = 0
    while True:
        el = (clock.monotonic() - t0) * 1000
        if el >= opts.wait * 1000: break
        o = session.observe(cheap_only=True)
        now = None if o is None else (o.outer, o.focused, o.framed)
        if now != last: last = now; since = el
        if opts.settle and post is not None and el - since >= opts.settle * 1000: break
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
    session.key_down(key); clock.sleep(seconds); session.key_up(key)


def run_toggle(session, game, opts=Opts(), clock=Clock, shoot=lambda stage: None):
    """F12 = toggleScreenMode: windowed -> fullscreen -> windowed, then measure again. Returns t_* fields (geometry in t_outer).
    shoot(stage) is called at "before", "fullscreen" and "after" (screenshots)."""
    ok = 0; method = "key"; t = {}
    win = session.window_id()
    if win is not None:
        s0 = _toggle_size(session.observe(cheap_only=True)); shoot("before")
        _hold(session, "F12", clock); clock.sleep(3); s1 = _toggle_size(session.observe(cheap_only=True))
        if s1 == s0:
            session.send_key("F12", win); method = "sendevent"; clock.sleep(3); s1 = _toggle_size(session.observe(cheap_only=True))
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
