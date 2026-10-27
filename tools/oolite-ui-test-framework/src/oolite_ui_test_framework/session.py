"""Sessions: start/stop a display server + window manager (or compositor) from a registry entry, with a readiness check."""
import glob
import os
import re
import subprocess
import time

from . import fakeinput, window_probes


class SessionError(RuntimeError):
    """Hard failure: the environment could not be started (asserted by the tests, not recorded as a measurement)."""


def parse_screen(screen):
    """'3840x1080' -> (3840, 1080); '2head' -> (3840, 1080)."""
    if screen == "2head": return 3840, 1080
    m = re.fullmatch(r"(\d+)x(\d+)", screen or "")
    if not m: raise SessionError("bad screen '%s' (use WxH or 2head)" % screen)
    return int(m[1]), int(m[2])


DUMMY_CONF = """Section "Device"
  Identifier "d"
  Driver "dummy"
  VideoRam 256000
EndSection
Section "Screen"
  Identifier "s"
  Device "d"
  DefaultDepth 24
  SubSection "Display"
    Depth 24
    Virtual 3840 1080
  EndSubSection
EndSection
"""


class Session:
    def __init__(self, env, screen="3840x1080", sleep=time.sleep, log_dir="/tmp", probe_kw=None, helper=None):
        self.env = env; self.screen = screen; self.sleep = sleep; self.log_dir = log_dir; self.probe_kw = probe_kw or {}; self.helper = helper
        self.w, self.h = (0, 0) if env.kind == "host" else parse_screen(screen)
        self.procs = []; self.probes = []; self.backend = None; self.primary = None; self.version = ""
        self.saved = dict(os.environ)
        self.game_env = {}

    # ---- helpers
    def _popen(self, cmd, log):
        p = subprocess.Popen(cmd, shell=isinstance(cmd, str), stdout=open(os.path.join(self.log_dir, log), "w"), stderr=subprocess.STDOUT,
                             env=dict(os.environ), start_new_session=True)
        self.procs.append(p); return p

    def _run(self, cmd):
        return subprocess.run(cmd, shell=isinstance(cmd, str), capture_output=True, text=True, env=dict(os.environ)).stdout

    def _tail(self, log):
        try: return "".join(open(os.path.join(self.log_dir, log), errors="replace").readlines()[-3:])
        except OSError: return ""

    # ---- X server
    def _start_x_server(self):
        os.environ["DISPLAY"] = ":9"
        if self.screen == "2head":
            with open("/tmp/dummy.conf", "w") as f: f.write(DUMMY_CONF)
            self._popen("Xorg :9 -config /tmp/dummy.conf -noreset", "xorg.log"); self.sleep(4)
            mode = self._run("cvt 1920 1080 60").splitlines()[1].replace("Modeline ", "").replace('"', "").split()
            for c in (["xrandr", "--newmode"] + mode, ["xrandr", "--addmode", "DUMMY0", mode[0]], ["xrandr", "--addmode", "DUMMY1", mode[0]],
                      ["xrandr", "--fb", "3840x1080", "--output", "DUMMY0", "--mode", mode[0], "--pos", "0x0",
                       "--output", "DUMMY1", "--mode", mode[0], "--pos", "1920x0", "--primary"]):
                subprocess.run(c, capture_output=True, env=dict(os.environ))
        else:
            self._popen("Xvfb :9 -screen 0 %dx%dx24 +extension RANDR" % (self.w, self.h), "xvfb.log"); self.sleep(2)

    # ---- start
    def start(self):
        e = self.env
        if e.kind == "x11":
            os.environ["XDG_SESSION_TYPE"] = "x11"
            self._start_x_server()
            self._start_cmds()
            self.backend = window_probes.x_backend(dict(os.environ))
            self.sleep(e.settle)
            chk = None
            for _ in range(e.ready_timeout):
                chk = self.backend.wm_check()
                if chk: break
                self.sleep(1)
            if not chk: raise SessionError("%s failed to start (no _NET_SUPPORTING_WM_CHECK): %s" % (e.name, self._tail("wm.log")))
            self.sleep(e.settle_after)
            # A held key is then ONE press. With autorepeat each repeat is a release + press pair: the game takes every pair as a new
            # press (its own 0.2 s repeat never applies), and pairs queued during a slow frame move the menu after the key is released.
            # Set after the WM is up, which may apply its own repeat settings.
            self.backend.autorepeat_off()
            self.game_env = {"SDL_VIDEODRIVER": "x11"}
            self.primary = window_probes.primary_monitor(self.backend.monitors())
        elif e.kind == "wayland":
            rt = "/tmp/xdg"; os.makedirs(rt, exist_ok=True); os.chmod(rt, 0o700)
            os.environ.update({"XDG_RUNTIME_DIR": rt, "XDG_SESSION_TYPE": "wayland", "WAYLAND_DISPLAY": "wl0"})
            os.environ.update(e.env)
            for path, text in e.files.items():
                with open(path, "w") as f: f.write(text.format(w=self.w, h=self.h))
            self._start_cmds()
            sock = os.path.join(rt, e.ready_socket)
            for _ in range(30):
                if os.path.exists(sock): break
                self.sleep(0.5)
            self.sleep(e.settle)
            if not os.path.exists(sock): raise SessionError("%s failed to start (no wayland socket %s): %s" % (e.name, e.ready_socket, self._tail("wm.log")))
            for c in e.post_start: self._run(c)
            self.primary = (0, 0, self.w, self.h)
            if e.session == "XWayland":
                disp = None
                for _ in range(20):
                    skip = {"77", os.environ.get("UITEST_HOST_DISPLAY", "").lstrip(":")}   # headed: the host's socket is mounted here too
                    xs = sorted(x[1:] for x in os.listdir("/tmp/.X11-unix") if re.fullmatch(r"X\d+", x) and x[1:] not in skip) if os.path.isdir("/tmp/.X11-unix") else []
                    if xs: disp = xs[0]; break
                    self.sleep(0.5)
                if disp is None: raise SessionError("%s: no XWayland display appeared" % e.name)
                os.environ["DISPLAY"] = ":" + disp
                xa = glob.glob(os.path.join(rt, ".mutter-Xwaylandauth.*"))
                if xa: os.environ["XAUTHORITY"] = xa[0]
                self.game_env = {"SDL_VIDEODRIVER": "x11"}
            else:
                os.environ.pop("DISPLAY", None)
                self.game_env = {"SDL_VIDEODRIVER": "wayland"}
        else:   # host: the live desktop, nothing is started
            self.game_env = {"SDL_VIDEODRIVER": "wayland" if e.session == "Wayland native" else "x11"}
            if os.environ.get("DISPLAY") and e.session != "Wayland native":
                self.backend = window_probes.HelperBackend(self.helper) if self.helper else window_probes.x_backend(dict(os.environ))
                self.primary = window_probes.primary_monitor(self.backend.monitors())
        if e.version_cmd:
            m = re.search(e.version_re, self._run(e.version_cmd + " 2>&1") or "")
            self.version = m[0] if m else ""
        self._make_probes()
        if e.session == "XWayland" and self.backend is not None:
            # XWayland generates the key repeat itself (from KWin's fake-input keys too), as release + press pairs: off, as in the X11 sessions
            self.backend.autorepeat_off()
        if e.headed and self.backend is not None:   # the host window manager may resize KWin's window: the output is what XWayland reports
            self.primary = window_probes.primary_monitor(self.backend.monitors()) or self.primary
        return self

    def grab_screen(self):
        """(w, h, rgb) of the whole compositor output including its decorations: KWin's window on the host display (headed only), else None."""
        host = os.environ.get("UITEST_HOST_DISPLAY")
        if not self.env.headed or not host: return None
        env = dict(os.environ, DISPLAY=host)
        if os.environ.get("UITEST_HOST_XAUTHORITY"): env["XAUTHORITY"] = os.environ["UITEST_HOST_XAUTHORITY"]
        pid = self._run("pgrep -x kwin_wayland").split()
        ids = subprocess.run(["xdotool", "search", "--pid", pid[0]], capture_output=True, text=True, env=env).stdout.split() if pid else []
        if not ids: return None
        saved = os.environ.get("XAUTHORITY"); os.environ["XAUTHORITY"] = env.get("XAUTHORITY", "")   # python-xlib reads the cookie from os.environ
        try: return window_probes.XlibBackend(env).grab(int(ids[0]))
        except Exception: return None
        finally:
            if saved is None: os.environ.pop("XAUTHORITY", None)
            else: os.environ["XAUTHORITY"] = saved

    def _start_cmds(self):
        for c in self.env.start:
            self._popen(c.format(w=self.w, h=self.h), "wm.log")

    def _make_probes(self):
        env = dict(os.environ); self.probes = []
        for name, fields in self.env.probe_specs:
            if name == "x11" and self.backend is None:
                if not os.environ.get("DISPLAY"): continue
                self.backend = window_probes.x_backend(env)
            self.probes.append((window_probes.make_probe(name, env, backend=self.backend, **(self.probe_kw if name == "ask" else {})), fields))

    # ---- observation
    def observe(self, cheap_only=False):
        """Merge the probes (first non-None field wins, restricted by 'name:fields'). None if the window is not there."""
        res = window_probes.Obs(); seen = False
        for p, fields in self.probes:
            if cheap_only and not p.cheap: continue
            if p.name == "ask":
                miss = [f for f in ("framed", "focused", "centred") if getattr(res, f) is None]
                o = p.observe(missing=miss)
            else:
                o = p.observe()
            if o is None: continue
            seen = True; res.merge(o, fields)
        if self.env.focus_na: res.focused = None
        return res if seen else None

    def window_present(self, game):
        if self.backend is not None and any(p.name == "x11" for p, _ in self.probes): return self.backend.find_window() is not None
        return game.alive()

    def window_id(self):
        return self.backend.find_window() if self.backend else None

    def send_key(self, key, window=None):
        if self.env.keys == "fakeinput": return fakeinput.tap(key)
        (self.backend or window_probes.XToolsBackend(dict(os.environ))).send_key(key, window)

    def key_down(self, key):
        if self.env.keys == "fakeinput": return fakeinput.key_down(key)
        (self.backend or window_probes.XToolsBackend(dict(os.environ))).key_down(key)

    def key_up(self, key):
        if self.env.keys == "fakeinput": return fakeinput.key_up(key)
        (self.backend or window_probes.XToolsBackend(dict(os.environ))).key_up(key)

    # ---- mouse (XTEST through xdotool, or KWin fake-input where the keys need it)
    def mouse_ok(self):
        return not self.env.mouse_na

    def mouse_move(self, x, y):
        """Put the pointer at (x, y) in the game window's own pixels, the same coordinates as a screenshot of it."""
        if self.env.keys == "fakeinput":   # fake-input takes output coordinates: the window's position on the output plus (x, y)
            g = self.backend.abs_geom(self.window_id()) if self.backend else None
            if not g: raise SessionError("fake input: cannot find the game window's position for a mouse move")
            return fakeinput.mouse_move(g[0] + x, g[1] + y)
        (self.backend or window_probes.XToolsBackend(dict(os.environ))).mouse_move(self.window_id(), x, y)

    def mouse_down(self):
        if self.env.keys == "fakeinput": return fakeinput.mouse_down()
        (self.backend or window_probes.XToolsBackend(dict(os.environ))).mouse_down()

    def mouse_up(self):
        if self.env.keys == "fakeinput": return fakeinput.mouse_up()
        (self.backend or window_probes.XToolsBackend(dict(os.environ))).mouse_up()

    def stop(self):
        if self.env.keys == "fakeinput": fakeinput.close()
        for p, _ in self.probes: p.close()
        for p in reversed(self.procs):
            try: os.killpg(p.pid, 15)
            except (OSError, ProcessLookupError): pass
        self.sleep(1)
        for p in self.procs:
            try: os.killpg(p.pid, 9)
            except (OSError, ProcessLookupError): pass
        os.environ.clear(); os.environ.update(self.saved)
