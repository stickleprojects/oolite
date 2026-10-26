"""Sessions: start/stop a display server + window manager (or compositor) from a registry entry, with a readiness check."""
import glob
import os
import re
import shutil
import subprocess
import time

from . import checks, probes


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
            self.backend = probes.x_backend(dict(os.environ))
            self.sleep(e.settle)
            chk = None
            for _ in range(e.ready_timeout):
                chk = self.backend.wm_check()
                if chk: break
                self.sleep(1)
            if not chk: raise SessionError("%s failed to start (no _NET_SUPPORTING_WM_CHECK): %s" % (e.name, self._tail("wm.log")))
            self.sleep(e.settle_after)
            self.game_env = {"SDL_VIDEODRIVER": "x11"}
            self.primary = probes.primary_monitor(self.backend.monitors())
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
                    xs = sorted(x[1:] for x in os.listdir("/tmp/.X11-unix") if re.fullmatch(r"X\d+", x) and x[1:] != "77") if os.path.isdir("/tmp/.X11-unix") else []
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
                self.backend = probes.HelperBackend(self.helper) if self.helper else probes.x_backend(dict(os.environ))
                self.primary = probes.primary_monitor(self.backend.monitors())
        if e.version_cmd:
            m = re.search(e.version_re, self._run(e.version_cmd + " 2>&1") or "")
            self.version = m[0] if m else ""
        self._make_probes()
        return self

    def _start_cmds(self):
        for c in self.env.start:
            self._popen(c.format(w=self.w, h=self.h), "wm.log")

    def _make_probes(self):
        env = dict(os.environ); self.probes = []
        for name, fields in self.env.probe_specs:
            if name == "x11" and self.backend is None:
                if not os.environ.get("DISPLAY"): continue
                self.backend = probes.x_backend(env)
            self.probes.append((probes.make_probe(name, env, backend=self.backend, **(self.probe_kw if name == "ask" else {})), fields))

    # ---- observation
    def observe(self, cheap_only=False):
        """Merge the probes (first non-None field wins, restricted by 'name:fields'). None if the window is not there."""
        res = probes.Obs(); seen = False
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
        (self.backend or probes.XToolsBackend(dict(os.environ))).send_key(key, window)

    def key_down(self, key):
        (self.backend or probes.XToolsBackend(dict(os.environ))).key_down(key)

    def key_up(self, key):
        (self.backend or probes.XToolsBackend(dict(os.environ))).key_up(key)

    def stop(self):
        for p, _ in self.probes: p.close()
        for p in reversed(self.procs):
            try: os.killpg(p.pid, 15)
            except (OSError, ProcessLookupError): pass
        self.sleep(1)
        for p in self.procs:
            try: os.killpg(p.pid, 9)
            except (OSError, ProcessLookupError): pass
        os.environ.clear(); os.environ.update(self.saved)
