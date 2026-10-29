"""Probes: one interface for observing the game window. observe() -> Obs (None if the window is not there).
Fields a probe cannot measure stay None (reported as NA, never as a failure).

  X11Probe    X11 / XWayland: python-xlib, or xwininfo/xprop/xdotool subprocesses when python-xlib is missing
  KWinProbe   KWin (X11 or Wayland) through its scripting D-Bus API (read-only script, loaded and unloaded)
  SwayProbe   sway IPC (swaymsg get_tree)
  AskProbe    asks the user y/n questions for whatever is still unknown (interactive, host mode)
  NullProbe   measures nothing (compositors with no outside view)
"""
import glob
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from typing import Optional

from . import geometry


@dataclass
class Obs:
    framed: Optional[int] = None
    focused: Optional[int] = None
    outer: Optional[tuple] = None        # (x, y, w, h) of the outer window (WM frame if any)
    client: Optional[tuple] = None
    win: Optional[int] = None
    mon: Optional[tuple] = None          # monitor the window should be centred on, if the probe knows it
    centred: Optional[int] = None        # only for answers given by the user
    fullscreen: Optional[int] = None     # 1 if the window manager has the window in full-screen state (_NET_WM_STATE_FULLSCREEN etc.)
    source: str = ""
    asked: dict = field(default_factory=dict)   # {check: 'y'|'n'}

    def merge(self, other, fields=None):
        """Fill our None fields from `other` (restricted to `fields` if given)."""
        for f in ("framed", "focused", "outer", "client", "win", "mon", "centred", "fullscreen"):
            if fields and f not in fields and not (f in ("outer", "client", "win") and "geometry" in fields): continue
            if getattr(self, f) is None and getattr(other, f) is not None: setattr(self, f, getattr(other, f))
        self.asked.update(other.asked)
        if other.source and not self.source: self.source = other.source


def sh(cmd, env=None, timeout=15, input=None):
    """stdout of a command ('' on any failure)."""
    try:
        return subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=timeout, input=input).stdout
    except (OSError, subprocess.SubprocessError):
        return ""


# ---------------------------------------------------------------- X11 backends
class XToolsBackend:
    """xwininfo / xprop / xdotool / xrandr subprocesses (the original harness' method)."""
    def __init__(self, env=None, cls="oolite"):
        self.env = env; self.cls = cls; self._root = None

    def root_id(self):
        if self._root is None:
            m = re.search(r"Window id: (0x[0-9a-f]+)", sh(["xwininfo", "-root"], self.env)); self._root = int(m[1], 16) if m else 0
        return self._root

    def find_window(self):
        out = sh(["xdotool", "search", "--class", self.cls], self.env).split()
        return int(out[0]) if out else None

    def parent_id(self, w):
        m = re.search(r"Parent window id: (0x[0-9a-f]+)", sh(["xwininfo", "-id", str(w), "-children"], self.env))
        return int(m[1], 16) if m else None

    def abs_geom(self, w):
        t = sh(["xwininfo", "-id", str(w)], self.env)
        try:
            g = {k: int(re.search(p, t)[1]) for k, p in (("w", r"Width: (\d+)"), ("h", r"Height: (\d+)"),
                                                          ("x", r"Absolute upper-left X:\s+(-?\d+)"), ("y", r"Absolute upper-left Y:\s+(-?\d+)"))}
        except TypeError:
            return None
        return (g["x"], g["y"], g["w"], g["h"])

    def active_id(self):
        m = re.search(r"0x[0-9a-f]+", sh(["xprop", "-root", "_NET_ACTIVE_WINDOW"], self.env)); return int(m[0], 16) if m else 0

    def fullscreen(self, w):
        """1 / 0 from the window's _NET_WM_STATE, None if it cannot be read."""
        out = sh(["xprop", "-id", str(w), "_NET_WM_STATE"], self.env)
        if "_NET_WM_STATE" not in out: return None
        return int("_NET_WM_STATE_FULLSCREEN" in out)

    def focus_id(self):
        o = sh(["xdotool", "getwindowfocus"], self.env).strip(); return int(o) if o.isdigit() else None

    def wm_check(self):
        m = re.search(r"0x[0-9a-f]+", sh(["xprop", "-root", "_NET_SUPPORTING_WM_CHECK"], self.env)); return int(m[0], 16) if m else None

    def wm_name(self):
        c = self.wm_check()
        return sh(["xprop", "-id", str(c), "_NET_WM_NAME"], self.env).split("=", 1)[-1].strip().strip('"') if c else ""

    def monitors(self):
        out = []
        for ln in sh(["xrandr", "--listmonitors"], self.env).splitlines()[1:]:
            m = re.search(r"^\s*\d+:\s+\+(\*?)\S+\s+(\d+)/\d+x(\d+)/\d+\+(-?\d+)\+(-?\d+)", ln)
            if m: out.append((int(m[4]), int(m[5]), int(m[2]), int(m[3]), bool(m[1])))
        return out

    def send_key(self, key, window=None):
        sh(["xdotool", "key"] + (["--window", str(window)] if window else []) + [key], self.env)

    def key_down(self, key):
        sh(["xdotool", "keydown", key], self.env)

    def key_up(self, key):
        sh(["xdotool", "keyup", key], self.env)

    def mouse_move(self, window, x, y):
        sh(["xdotool", "mousemove", "--window", str(window), str(x), str(y)], self.env)

    def mouse_down(self):
        sh(["xdotool", "mousedown", "1"], self.env)

    def mouse_up(self):
        sh(["xdotool", "mouseup", "1"], self.env)

    def autorepeat_off(self):
        sh(["xset", "r", "off"], self.env)

    def autorepeat_restore(self):
        sh(["xset", "r", "on"], self.env)

    def autorepeat_on(self):
        """True / False, or None if xset could not tell."""
        m = re.search(r"auto repeat:\s+(on|off)", sh(["xset", "q"], self.env))
        return None if not m else m[1] == "on"


class XlibBackend:
    """python-xlib, one persistent connection. Same interface as XToolsBackend (keys and the mouse still use xdotool)."""
    def __init__(self, env=None, cls="oolite"):
        from Xlib import display
        self.env = env; self.cls = cls.lower()
        self.d = display.Display((env or {}).get("DISPLAY")); self.root = self.d.screen().root

    def _atom(self, n):
        return self.d.intern_atom(n)

    def autorepeat_off(self):
        from Xlib import X
        self.d.change_keyboard_control(auto_repeat_mode=X.AutoRepeatModeOff); self.d.sync()

    def autorepeat_restore(self):
        from Xlib import X
        self.d.change_keyboard_control(auto_repeat_mode=X.AutoRepeatModeOn); self.d.sync()

    def autorepeat_on(self):
        try: return bool(self.d.get_keyboard_control().global_auto_repeat)
        except Exception: return None

    def root_id(self):
        return self.root.id

    def _walk(self, w, depth=0):
        try: kids = w.query_tree().children
        except Exception: return
        for k in kids:
            yield k
            if depth < 4: yield from self._walk(k, depth + 1)

    def find_window(self):
        for w in self._walk(self.root):
            try: c = w.get_wm_class()
            except Exception: c = None
            if c and any(self.cls in x.lower() for x in c): return w.id
        return None

    def _win(self, wid):
        return self.d.create_resource_object("window", wid)

    def parent_id(self, w):
        try: return self._win(w).query_tree().parent.id
        except Exception: return None

    def abs_geom(self, w):
        try:
            win = self._win(w); g = win.get_geometry(); t = self.root.translate_coords(w, 0, 0)
            return (t.x, t.y, g.width, g.height)
        except Exception: return None

    def _prop(self, win, name):
        p = win.get_full_property(self._atom(name), 0)
        return p.value if p is not None else None

    def active_id(self):
        v = self._prop(self.root, "_NET_ACTIVE_WINDOW"); return int(v[0]) if v is not None and len(v) else 0

    def fullscreen(self, w):
        """1 / 0 from the window's _NET_WM_STATE (no property = not full screen), None if the window cannot be read."""
        try: v = self._prop(self._win(w), "_NET_WM_STATE")
        except Exception: return None
        return int(v is not None and self._atom("_NET_WM_STATE_FULLSCREEN") in list(v))

    def focus_id(self):
        try:
            f = self.d.get_input_focus().focus
            return f.id if hasattr(f, "id") else None
        except Exception: return None

    def wm_check(self):
        v = self._prop(self.root, "_NET_SUPPORTING_WM_CHECK"); return int(v[0]) if v is not None and len(v) else None

    def wm_name(self):
        c = self.wm_check()
        if not c: return ""
        v = self._prop(self._win(c), "_NET_WM_NAME")
        return bytes(v).decode("utf-8", "replace") if v is not None else ""

    def monitors(self):
        try:
            return [(m.x, m.y, m.width_in_pixels, m.height_in_pixels, bool(m.primary)) for m in self.root.xrandr_get_monitors().monitors]
        except Exception:
            return XToolsBackend(self.env).monitors()

    def send_key(self, key, window=None):
        XToolsBackend(self.env).send_key(key, window)

    def key_down(self, key):
        XToolsBackend(self.env).key_down(key)

    def key_up(self, key):
        XToolsBackend(self.env).key_up(key)

    def mouse_move(self, window, x, y):
        XToolsBackend(self.env).mouse_move(window, x, y)

    def mouse_down(self):
        XToolsBackend(self.env).mouse_down()

    def mouse_up(self):
        XToolsBackend(self.env).mouse_up()

    def grab(self, w):
        """(width, height, rgb bytes) of window w as drawn on screen (python-xlib get_image), or None."""
        from Xlib import X
        from . import png
        try:
            win = self._win(w); g = win.get_geometry()
            img = win.get_image(0, 0, g.width, g.height, X.ZPixmap, 0xFFFFFFFF)
            return g.width, g.height, png.bgrx_to_rgb(img.data, g.width, g.height)
        except Exception:
            return None


def x_backend(env=None, prefer="auto"):
    """python-xlib if importable and the display opens, else the subprocess tools."""
    if prefer in ("auto", "xlib"):
        try: return XlibBackend(env)
        except Exception:
            if prefer == "xlib": raise
    return XToolsBackend(env)


def primary_monitor(mons):
    """trial.sh: the monitor flagged primary (the last such), else the first. (x, y, w, h) or None."""
    if not mons: return None
    flagged = [m for m in mons if m[4]]
    return (flagged[-1] if flagged else mons[0])[:4]


# ---------------------------------------------------------------- probes
class Probe:
    name = "probe"
    cheap = False          # cheap enough to call every 0.5 s while sampling

    def observe(self, missing=None):
        return None

    def monitors(self):
        return []

    def close(self):
        pass


class NullProbe(Probe):
    name = "none"

    def observe(self, missing=None):
        return Obs()


class X11Probe(Probe):
    name = "x11"; cheap = True

    def __init__(self, backend):
        self.b = backend

    def observe(self, missing=None):
        w = self.b.find_window()
        if w is None: return None
        client = self.b.abs_geom(w)
        if client is None: return None
        parent = self.b.parent_id(w); root = self.b.root_id()
        fr = geometry.framed(None if parent is None else parent == root)
        outer = self.b.abs_geom(parent) if fr and parent else client
        fs = self.b.fullscreen(w) if hasattr(self.b, "fullscreen") else None
        return Obs(framed=fr, focused=geometry.focused(self.b.active_id(), self.b.focus_id(), w), outer=outer or client, client=client, win=w,
                   fullscreen=fs, source="x11")

    def monitors(self):
        return self.b.monitors()

    def wm_name(self):
        return self.b.wm_name()


KWIN_SCRIPT = r"""
var r = "none";
try {
  var l = workspace.windowList();
  for (var i = 0; i < l.length; i++) { var w = l[i];
    if (/oolite/i.test(w.resourceClass + " " + w.resourceName + " " + w.caption)) {
      var g = w.frameGeometry, c = w.clientGeometry, o = "NA NA NA NA";
      try { var q = w.output.geometry; o = Math.round(q.x) + " " + Math.round(q.y) + " " + Math.round(q.width) + " " + Math.round(q.height); } catch (e2) {}
      r = "OOPROBE " + (w.noBorder ? 0 : 1) + " " + (w.active ? 1 : 0) + " " + Math.round(g.x) + " " + Math.round(g.y) + " " + Math.round(g.width) + " " + Math.round(g.height) + " " + o +
          " " + Math.round(c.x) + " " + Math.round(c.y) + " " + Math.round(c.width) + " " + Math.round(c.height) + " " + (w.fullScreen ? 1 : 0); } }
} catch (e) { r = "ERR " + e; }
callDBus("org.oolite.probe", "/p", "org.oolite.probe", "report", r);
"""


def parse_kwin_row(row):
    """'fr fo x y w h [ox oy ow oh [cx cy cw ch [fs]]]' -> Obs (output, client geometry and full-screen state optional; the output may be NA)."""
    f = row.split()
    if len(f) < 6: return None
    o = Obs(framed=int(f[0]), focused=int(f[1]), outer=(int(f[2]), int(f[3]), int(f[4]), int(f[5])), source="compositor")
    if len(f) >= 10 and all(re.fullmatch(r"-?\d+", x) for x in f[6:10]):
        o.mon = (int(f[6]), int(f[7]), int(f[8]), int(f[9]))
    if len(f) >= 14 and all(re.fullmatch(r"-?\d+", x) for x in f[10:14]):
        o.client = (int(f[10]), int(f[11]), int(f[12]), int(f[13]))
    if len(f) >= 15 and f[14] in ("0", "1"): o.fullscreen = int(f[14])
    return o


class KWinProbe(Probe):
    """KWin scripting over D-Bus. The script's callDBus goes to a service that does not exist; dbus-monitor sees the call."""
    name = "kwin"

    def __init__(self, env=None, settle=0.7):
        self.env = env; self.settle = settle; self.ok = bool(shutil.which("dbus-send") and shutil.which("dbus-monitor"))
        self.mon = None; self.proc = None; self.js = None
        if self.ok:
            fd, self.js = tempfile.mkstemp(suffix=".js"); os.write(fd, KWIN_SCRIPT.encode()); os.close(fd)
            fd2, self.mon = tempfile.mkstemp(); os.close(fd2)
            self.proc = subprocess.Popen(["dbus-monitor"], env=env, stdout=open(self.mon, "w"), stderr=subprocess.STDOUT)

    def _count(self):
        try: return open(self.mon, errors="replace").read().count("OOPROBE")
        except OSError: return 0

    def observe(self, missing=None):
        if not self.ok: return Obs()
        n0 = self._count(); sid = "kp%d" % int(time.time() * 1000)
        out = sh(["dbus-send", "--session", "--print-reply", "--dest=org.kde.KWin", "/Scripting", "org.kde.kwin.Scripting.loadScript",
                  "string:" + self.js, "string:" + sid], self.env)
        m = re.search(r"int32 (\d+)", out)
        if not m: return Obs()
        sh(["dbus-send", "--session", "--print-reply", "--dest=org.kde.KWin", "/Scripting/Script" + m[1], "org.kde.kwin.Script.run"], self.env)
        time.sleep(self.settle)
        row = ""
        if self._count() != n0:
            ln = [x for x in open(self.mon, errors="replace").read().splitlines() if "OOPROBE" in x][-1]
            row = ln.split("OOPROBE", 1)[1].strip().rstrip('"')
        sh(["dbus-send", "--session", "--print-reply", "--dest=org.kde.KWin", "/Scripting", "org.kde.kwin.Scripting.unloadScript", "string:" + sid], self.env)
        return (parse_kwin_row(row) if row else None) or Obs()

    def close(self):
        if self.proc: self.proc.terminate()
        for f in (self.js, self.mon):
            if f:
                try: os.unlink(f)
                except OSError: pass


def parse_shot_meta(out):
    """gdbus' reply to a ScreenShot2 capture -> {width, height, stride, format, scale}, or None. format is a QImage::Format number."""
    meta = {}
    for k in ("width", "height", "stride", "format"):
        m = re.search(r"'%s': <uint32 (\d+)>" % k, out)
        if not m: return None
        meta[k] = int(m[1])
    m = re.search(r"'scale': <([0-9.]+)>", out); meta["scale"] = float(m[1]) if m else 1.0
    return meta


def crop_rgba(data, meta, box):
    """Rows of a raw ScreenShot2 image -> rgb bytes of box (x, y, w, h, in image pixels), clipped to the image. -> (w, h, rgb) or None.
    QImage formats 16-18 (RGBX/RGBA8888) are R G B A in memory; 4-6 (RGB32/ARGB32) are B G R A on little-endian machines."""
    W, H, stride, fmt = meta["width"], meta["height"], meta["stride"], meta["format"]
    if fmt not in (4, 5, 6, 16, 17, 18) or len(data) < stride * H: return None
    x0, y0 = max(0, box[0]), max(0, box[1]); x1, y1 = min(W, box[0] + box[2]), min(H, box[1] + box[3])
    if x1 <= x0 or y1 <= y0: return None
    w, h = x1 - x0, y1 - y0
    rows = b"".join(data[y * stride + 4 * x0: y * stride + 4 * x1] for y in range(y0, y1))
    if fmt in (4, 5, 6):
        from . import png
        return w, h, png.bgrx_to_rgb(rows, w, h)
    out = bytearray(w * h * 3); out[0::3] = rows[0::4]; out[1::3] = rows[1::4]; out[2::3] = rows[2::4]
    return w, h, bytes(out)


def kwin_capture(env=None, timeout=15):
    """The whole KWin workspace through D-Bus org.kde.KWin.ScreenShot2 (needs KWIN_SCREENSHOT_NO_PERMISSION_CHECKS=1 on kwin_wayland and
    a render device: /dev/udmabuf or a GPU node, KDE 527906). KWin writes the raw image into the pipe we pass as the handle.
    -> (data, meta) or None."""
    import threading
    r, w = os.pipe(); chunks = []
    reader = threading.Thread(target=lambda: chunks.extend(iter(lambda: os.read(r, 1 << 20), b"")), daemon=True); reader.start()
    try:
        p = subprocess.run(["gdbus", "call", "--session", "--dest", "org.kde.KWin", "--object-path", "/org/kde/KWin/ScreenShot2",
                            "--method", "org.kde.KWin.ScreenShot2.CaptureWorkspace", "{}", str(w)],
                           pass_fds=(w,), env=env, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired):
        p = None
    finally:
        os.close(w)
    reader.join(timeout); os.close(r)
    meta = parse_shot_meta(p.stdout) if p is not None and p.returncode == 0 else None
    return (b"".join(chunks), meta) if meta else None


class KWinBackend:
    """Native Wayland under KWin, where there is no X display: the game window is found and placed through the KWin probe, and grabbed
    with ScreenShot2 (the workspace, cropped to the game's client area, like the X11 grab). Keys and the mouse go through fake-input."""
    def __init__(self, probe, env=None, max_age=1.0, clock=time.monotonic, capture=kwin_capture):
        self.probe = probe; self.env = env; self.max_age = max_age; self.clock = clock; self.capture = capture
        self._obs = None; self._t = None

    def _observe(self):
        """The last KWin observation, re-taken when older than max_age (each one costs a script round trip of about 0.7 s)."""
        if self._t is None or self.clock() - self._t > self.max_age:
            self._obs = self.probe.observe(); self._t = self.clock()
        return self._obs

    def find_window(self):
        o = self._observe()
        return 1 if o is not None and o.client is not None else None

    def abs_geom(self, w):
        o = self._observe()
        return o.client if o is not None else None

    def grab(self, w):
        """(width, height, rgb bytes) of the game's client area as drawn on screen, or None."""
        g = self.abs_geom(w); shot = self.capture(self.env) if g else None
        if not shot: return None
        data, meta = shot; s = meta["scale"]
        return crop_rgba(data, meta, tuple(int(round(v * s)) for v in g))


def grim_capture(box, env=None, run=subprocess.run):
    """(w, h, rgb bytes) of box (x, y, w, h) in output coordinates, grabbed with grim (wlroots screencopy) as a binary PPM, or None."""
    x, y, w, h = box
    try: p = run(["grim", "-t", "ppm", "-g", "%d,%d %dx%d" % (x, y, w, h), "-"], capture_output=True, env=env, timeout=15)
    except (OSError, subprocess.TimeoutExpired): return None
    m = re.match(rb"P6\s+(\d+)\s+(\d+)\s+255\s", p.stdout) if p.returncode == 0 else None
    if not m: return None
    pw, ph = int(m[1]), int(m[2]); data = p.stdout[m.end():m.end() + pw * ph * 3]
    return (pw, ph, data) if len(data) == pw * ph * 3 else None


class SwayBackend(KWinBackend):
    """Native Wayland under sway: the window found and placed through the sway probe (its tree), grabbed with grim. Keys and the mouse go
    through the virtual-keyboard and virtual-pointer protocols (keys = "virtual")."""
    def __init__(self, probe, env=None, max_age=1.0, clock=time.monotonic, capture=grim_capture):
        super().__init__(probe, env, max_age, clock, capture)

    def grab(self, w):
        g = self.abs_geom(w)
        return self.capture(g, self.env) if g else None


def parse_sway_tree(tree, outputs=None):
    """sway get_tree JSON (dict) -> Obs for the oolite window, or None."""
    def walk(n):
        yield n
        for k in n.get("nodes", []) + n.get("floating_nodes", []): yield from walk(k)
    for n in walk(tree):
        if n.get("pid") and re.search("oolite", (n.get("app_id") or "") + (n.get("window_properties") or {}).get("class", ""), re.I):
            r = n["rect"]
            fr = int((n.get("deco_rect") or {}).get("height", 0) > 0 or n.get("current_border_width", 0) > 0)
            o = Obs(framed=fr, focused=int(bool(n.get("focused"))), outer=(r["x"], r["y"], r["width"], r["height"]),
                    fullscreen=int((n.get("fullscreen_mode") or 0) > 0), source="compositor")
            w = n.get("window_rect")   # the client area, relative to rect
            if w: o.client = (r["x"] + w["x"], r["y"] + w["y"], w["width"], w["height"])
            for out in outputs or []:
                if out.get("focused") or o.mon is None: q = out["rect"]; o.mon = (q["x"], q["y"], q["width"], q["height"])
            return o
    return None


class SwayProbe(Probe):
    name = "sway"; cheap = True

    def __init__(self, env=None):
        self.env = env or os.environ

    def _msg(self, t):
        socks = glob.glob(os.path.join(self.env.get("XDG_RUNTIME_DIR", "/run/user/%d" % os.getuid()), "sway-ipc.*.sock"))
        if not socks or not shutil.which("swaymsg"): return None
        try: return json.loads(sh(["swaymsg", "-s", socks[0], "-t", t], dict(self.env)))
        except ValueError: return None

    def observe(self, missing=None):
        tree = self._msg("get_tree")
        return (parse_sway_tree(tree, self._msg("get_outputs")) if tree else None) or Obs()


QUESTIONS = {"framed": "Does the game window have a title bar / frame?",
             "focused": "Do keys respond (press an arrow key or Space: does the game react)?",
             "centred": "Is the window centred on the screen?"}


class AskProbe(Probe):
    """Asks y/n for what is still unknown. `ask(question)` -> 'y' | 'n' | None (skip); default reads /dev/tty; no_prompt -> never asks."""
    name = "ask"

    def __init__(self, ask=None, no_prompt=False):
        self.ask = ask or self._tty; self.no_prompt = no_prompt

    @staticmethod
    def _tty(q):
        try: tty = open("/dev/tty", "r+")
        except OSError: return None
        while True:
            tty.write("%s [y/n/s=skip] " % q); tty.flush()
            a = tty.readline().strip().lower()
            if a in ("y", "yes"): return "y"
            if a in ("n", "no"): return "n"
            if a in ("s", ""): return None

    def observe(self, missing=None):
        o = Obs()
        if self.no_prompt: return o
        for f in missing or ():
            if f in QUESTIONS:
                a = self.ask(QUESTIONS[f])
                if a: setattr(o, f, 1 if a == "y" else 0); o.asked[f] = a; o.source = "user"
        return o


class HelperBackend:
    """Host mode: the game runs on the host; X is measured in a helper container sharing the host's X display, by one long-lived
    `python3 -m oolite_ui_test_framework.xtool serve` (see xtool.py). Same interface as the X backends, screenshots and key repeat included."""
    def __init__(self, container, display=None, popen=subprocess.Popen):
        self.ct = container; self.display = display or os.environ.get("DISPLAY", ":0"); self.popen = popen; self.proc = None

    def _start(self):
        self.proc = self.popen(["docker", "exec", "-i", "-e", "DISPLAY=" + self.display, self.ct, "python3", "-u", "-m", "oolite_ui_test_framework.xtool", "serve"],
                               stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)

    def _call(self, *cmd):
        """The command's result; None if the helper failed (it is restarted on the next call)."""
        for _ in range(2):
            if self.proc is None or self.proc.poll() is not None: self._start()
            try:
                self.proc.stdin.write(json.dumps(list(cmd)).encode() + b"\n"); self.proc.stdin.flush()
                d = json.loads(self.proc.stdout.readline() or b"null")
            except (OSError, ValueError):
                self.close(); continue
            if not d or "error" in d: return None
            if "n" in d: return d["r"][0], d["r"][1], self.proc.stdout.read(d["n"])
            return d["r"]
        return None

    def close(self):
        if self.proc is not None:
            try: self.proc.stdin.close(); self.proc.wait(timeout=5)
            except (OSError, subprocess.SubprocessError): self.proc.kill()
        self.proc = None

    def observe(self):
        d = self._call("observe")
        if not d: return None
        t = lambda v: tuple(v) if v else None
        return Obs(framed=d["framed"], focused=d["focused"], outer=t(d["outer"]), client=t(d["client"]), win=d["win"], fullscreen=d.get("fullscreen"),
                   source="x11")

    def find_window(self):
        return self._call("find")

    def abs_geom(self, w):
        g = self._call("geom", w); return tuple(g) if g else None

    def grab(self, w):
        return self._call("grab", w)

    def monitors(self):
        return [tuple(m) for m in self._call("monitors") or []]

    def wm_name(self):
        return self._call("wmname") or ""

    def send_key(self, key, window=None):
        self._call("key", key, window or 0)

    def key_down(self, key):
        self._call("keydown", key)

    def key_up(self, key):
        self._call("keyup", key)

    def mouse_move(self, window, x, y):
        self._call("mousemove", window, x, y)

    def mouse_down(self):
        self._call("mousedown")

    def mouse_up(self):
        self._call("mouseup")

    def autorepeat_on(self):
        return self._call("repeat")

    def autorepeat_off(self):
        self._call("repeat_off")

    def autorepeat_restore(self):
        self._call("repeat_on")


class HelperX11Probe(Probe):
    name = "x11"; cheap = True

    def __init__(self, backend):
        self.b = backend

    def observe(self, missing=None):
        return self.b.observe()

    def monitors(self):
        return self.b.monitors()


def make_probe(name, env=None, backend=None, **kw):
    if name == "x11": return HelperX11Probe(backend) if isinstance(backend, HelperBackend) else X11Probe(backend or x_backend(env))
    if name == "kwin": return KWinProbe(env)
    if name == "sway": return SwayProbe(env)
    if name == "ask": return AskProbe(**kw)
    return NullProbe()
