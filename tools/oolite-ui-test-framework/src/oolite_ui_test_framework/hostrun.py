"""Host side of uitest: needs only python3 stdlib and docker. Three layers, each usable alone:
  tests      pytest + the plugin, against ONE AppImage in ONE environment (run inside the containers);
  run        `uitest run LABEL:APPIMAGE`: the coordinator. Builds images, runs the tests in each environment x screen, collects one result
             set (<name>.raw with a SET header, .md, -env.txt, .shots/, .logs/). It never compares;
  compare    `uitest compare --control SET --candidate SET`: verdicts (FIXED / REGRESSED ...) from result sets made by separate runs.
`uitest A:path B:path` (several builds) still works: it runs each build, then compares them. Host mode (--host) runs the same pytest tests
ON THE HOST (the game uses the host's libraries and drivers), with pytest from a venv of its own (.venv-host/, made on first use); X is
measured by a helper container sharing the live X display. Without that venv only the startup checks run, and the report says so."""
import argparse
import contextlib
import hashlib
import io
import json
import datetime
import os
import shutil
import socket
import re
import shlex
import subprocess
import sys
import tempfile
import time

from . import envinfo, raw_results, registry, scenarios, report
from .session import Session, SessionError

PKG = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))      # the framework folder (holds src/, docker/, environments.toml)
GAME_TESTS = os.path.join(os.path.dirname(os.path.dirname(PKG)), "tests", "ui")             # the tests of the game: tests/ui/ at the repo root
DEFAULT_ENVS = "marco,openbox,xfwm4,muffin,kwin,mutter"
WAYLAND_ENVS = "kwin-xwayland,kwin-native,sway-xwayland,sway-native,mutter-xwayland,mutter-native,weston-xwayland,weston-native"


QUICK_TESTS = "game_launches,title_menu_is_displayed"   # --quick: the shared launch plus one title-menu launch per environment
HOST_VENV = os.path.join(PKG, ".venv-host")   # host mode's pytest; never installed into the host's own python
HOST_PYTEST = "pytest==9.0.2"


def give_back_output(name, uid=None, gid=None):
    """Container command prefix: run the rest under dbus-run-session, then chown this run's output (/out/<name>.*) to the host user,
    so results/ never holds root-owned files. The containers stay root (window managers and dbus expect it)."""
    uid = os.getuid() if uid is None else uid; gid = os.getgid() if gid is None else gid
    script = 'dbus-run-session -- "$@"; rc=$?; chown -R %d:%d /out/%s.* 2>/dev/null; exit $rc' % (uid, gid, shlex.quote(name))
    return ["sh", "-c", script, "sh"]

def test_selector(names):
    """'has_frame, test_gets_focus' -> pytest -k expression 'test_has_frame or test_gets_focus' ('' = all tests)."""
    ids = []
    for n in (x.strip() for x in (names or "").split(",")):
        if n: ids.append(n if n.startswith("test_") else "test_" + n)
    return " or ".join(ids)


EXIT_PASS, EXIT_FAIL, EXIT_ERROR = 0, 1, 2   # stable, documented in the README
_QUIET = False


def say(*a):
    if not _QUIET: print(raw_results.stamp(), *a)


def _die(msg):
    print("uitest: " + msg, file=sys.stderr); raise SystemExit(2)


def docker_state():
    """(usable, reason)."""
    if not shutil.which("docker"): return False, "docker missing"
    try:
        if subprocess.run(["docker", "info"], capture_output=True, timeout=60).returncode != 0:
            return False, "docker daemon not reachable (not running, or no permission: try the docker group)"
    except (OSError, subprocess.SubprocessError):
        return False, "docker not usable"
    return True, ""


def parse_build(b):
    """'label:path' -> (label, realpath), or exit 2."""
    label, _, path = b.partition(":")
    if not label or not path or not os.path.isfile(path): _die("AppImage not found or bad label:path '%s'" % b)
    return label, os.path.realpath(path)


def parse_notes(a, labels):
    notes = {}
    for n in a.note:
        k, _, v = n.partition("=")
        if not v: _die("--note needs LABEL=TEXT, got '%s'" % n)
        if k not in labels: _die("--note for unknown label '%s'" % k)
        notes[k] = v
    return notes


def safe_name(name):
    return "".join(c if c.isalnum() or c in "+-_." else "_" for c in name)


def output_stem(a, default):
    """(out dir, name) from --report PATH, else --out / --name, else results/<default>."""
    if a.report:
        md = os.path.abspath(a.report); return os.path.dirname(md), safe_name(os.path.basename(md)[:-3] if md.endswith(".md") else os.path.basename(md))
    return os.path.abspath(a.out or os.path.join(PKG, "results")), safe_name(a.name or default)


def stamp():
    return datetime.datetime.now().strftime("%Y%m%d-%H%M%S")


def purpose_of(a):
    if a.desc_file:
        try: return open(a.desc_file, encoding="utf-8").read().strip()
        except OSError as e: _die("cannot read --desc-file: %s" % e)
    text = (a.desc or "").strip()
    if a.tests:   # a partial run must never be read as a full pass
        text = (text + "\n\n" if text else "") + "PARTIAL RUN: only these tests ran: %s%s" % (test_selector(a.tests).replace(" or ", ", "), " (--quick)" if a.quick else "")
    return text



class Runner:
    """The coordinator for ONE AppImage: every requested environment x screen, one result set. It never compares."""
    def __init__(self, a, build, name=None, note=""):
        self.a = a; self.envs, self.images = registry.load(a.registry or None)
        report.set_registry(self.envs)
        self.label, self.path = build
        self.out, self.name = output_stem(a, "uitest-%s-%s" % (stamp(), self.label))
        if name: self.name = safe_name(name)
        self.stem = os.path.join(self.out, self.name); self.md = self.stem + ".md"; self.parts = self.stem + ".parts"
        os.makedirs(self.parts, exist_ok=True)
        self.raw = self.stem + ".raw"; open(self.raw, "w").close()
        self.purpose = self.read_purpose()
        h = hashlib.sha256()
        with open(self.path, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""): h.update(chunk)
        sha = h.hexdigest()[:12]
        envs = [x for x in a.env.split(",") if x] + (WAYLAND_ENVS.split(",") if a.wayland else []) + (["host"] if a.host else [])
        self.add("SET " + json.dumps({"name": self.name, "label": self.label, "app": self.path, "file": os.path.basename(self.path), "sha256": sha,
                                      "built": datetime.datetime.fromtimestamp(os.path.getmtime(self.path)).isoformat(timespec="seconds"),
                                      "envs": envs, "screens": a.screens.split(","), "runs": a.runs, "toggle": bool(a.toggle),
                                      "tests": a.tests, "uitest_version": self.version(), "made": datetime.datetime.now().isoformat(timespec="seconds")}))
        self.add("PURPOSE " + json.dumps(self.purpose))
        self.add("BUILD " + json.dumps({"label": self.label, "file": os.path.basename(self.path), "sha256": sha, "note": note}))
        self.docker_ok, self.docker_why = docker_state()
        self.img_ok = {}
        if not self.docker_ok: say("NOTE: Docker parts will be skipped: " + self.docker_why)

    def read_purpose(self):
        return purpose_of(self.a)

    def add(self, line):
        with open(self.raw, "a") as f: f.write(line + "\n")

    def skip(self, wm, screen, why):
        self.add(raw_results.format_skip(wm, screen, self.label, why))
        say("  skipped %s (%s): %s" % (wm, screen, why))

    def ensure_image(self, image):
        if image in self.img_ok: return self.img_ok[image]
        spec = self.images[image]; tag = spec["tag"]
        ok = subprocess.run(["docker", "image", "inspect", tag], capture_output=True).returncode == 0
        if not ok:
            log = os.path.join(self.out, "build-%s.log" % tag)
            say("Building Docker image %s (first use only; several minutes). Log: %s" % (tag, log))
            with open(log, "w") as lf:
                ok = subprocess.run(["docker", "build", "-f", os.path.join(PKG, spec["dockerfile"]), "-t", tag, PKG], stdout=lf, stderr=subprocess.STDOUT).returncode == 0
            if not ok: say("  image build FAILED (see log)")
        self.img_ok[image] = ok; return ok

    def pytest_args(self, env, screen, part, app, python="python3", tests="/gametests", reg="/uitest/environments.toml", out="/out"):
        """The pytest command; the defaults are the paths inside the containers, host mode passes the host's own."""
        o = "%s/%s" % (out, self.name)
        c = [python, "-m", "pytest", "-q", "-c", tests + "/pytest.ini", tests, "--rootdir", tests,
             "--ui-registry", reg, "--ui-env", env, "--ui-screen", screen, "--ui-runs", str(self.runs_for(env)),
             "--ui-raw", "%s.parts/%s" % (o, part), "--junitxml", "%s.parts/%s.xml" % (o, part), "--ui-shots", o + ".shots", "--ui-logs", o + ".logs", "--ui-tol", str(self.a.tol)]
        if self.a.toggle: c.append("--ui-toggle")
        if self.a.tests: c += ["-k", test_selector(self.a.tests)]
        c += ["--ui-app=" + app, "--ui-label=" + self.label]
        return c

    def runs_for(self, env):
        return self.a.host_runs if self.envs[env].kind == "host" else self.a.runs

    def run_container(self, env, screen, extra=(), user=None):
        e = self.envs[env]; part = "%s-%s.raw" % (env, screen.replace(":", "_"))
        open(os.path.join(self.parts, part), "w").close()
        mounts = ["-v", "%s:/uitest:ro" % PKG, "-v", "%s:/gametests:ro" % GAME_TESTS, "-v", "%s:/out" % self.out, "-e", "PYTHONPATH=/uitest/src",
                  "-v", "%s:/app:ro" % os.path.dirname(self.path)]
        app = "/app/" + os.path.basename(self.path)
        # --init: the container's first process passes signals on, so stopping uitest stops the container (a shell as PID 1 ignored them)
        cmd = ["docker", "run", "--rm", "--init"] + mounts + list(extra) + [self.images[e.image]["tag"]] + give_back_output(self.name) + self.pytest_args(env, screen, part, app)
        self.collect(env, screen, part, *self.follow(cmd, part))

    def follow(self, cmd, part, poll=2.0, **kw):
        """Run one pytest (container or host) and copy its raw part into the result set as its lines arrive, so <name>.raw grows during
        the run and a run that is stopped keeps what it measured. Stopping uitest stops the pytest too (SIGTERM, which `docker run`
        passes on to the container). -> (CompletedProcess, bytes of the part already copied)."""
        path = os.path.join(self.parts, part); done = 0
        with tempfile.TemporaryFile("w+") as out, tempfile.TemporaryFile("w+") as err:
            p = subprocess.Popen(cmd, stdout=out, stderr=err, text=True, **kw)
            try:
                while p.poll() is None:
                    done = self.copy_part(path, done); time.sleep(poll)
            finally:
                if p.poll() is None:
                    p.terminate()
                    try: p.wait(30)
                    except subprocess.TimeoutExpired: p.kill()
            done = self.copy_part(path, done); out.seek(0); err.seek(0)
            return subprocess.CompletedProcess(cmd, p.returncode, out.read(), err.read()), done

    def copy_part(self, path, done):
        """Append the whole lines of the part file past byte `done` to the result set -> the new `done`."""
        try:
            with open(path, "rb") as f: f.seek(done); data = f.read()
        except OSError: return done
        data = data[:data.rfind(b"\n") + 1]
        if data:
            with open(self.raw, "ab") as f: f.write(data)
        return done + len(data)

    def collect(self, env, screen, part, r, done=0):
        """After one pytest run (container or host): its output's last line, the rest of its raw part into the result set (follow() copied
        the lines that came earlier), or a SKIP row if it never ran."""
        tail = [l for l in r.stdout.splitlines() if l.strip()][-1:] or [r.stderr.strip()[-200:]]
        say("  %s" % tail[0])
        # a failed pytest (hard failure) leaves a SKIP row with the reason
        data = open(os.path.join(self.parts, part)).read()
        rest = open(os.path.join(self.parts, part), "rb").read()[done:]
        if rest: open(self.raw, "ab").write(rest)
        # failing tests are measurements (pytest rc 1); hard failures are HARD lines in the raw file (report.py lists them) or an unusable pytest run
        if r.returncode not in (0, 1, 5) and "RESULT" not in data and "HARD" not in data:
            self.skip(env, screen, "hard failure: pytest rc=%d: %s" % (r.returncode, (r.stdout.strip().splitlines() or r.stderr.strip().splitlines() or [""])[-1][:160]))

    # ------------------------------------------------------------ the three groups
    def docker_cells(self, env_names, screens):
        for env in env_names:
            if env not in self.envs: say("unknown environment '%s' (see environments.toml)" % env); continue
            e = self.envs[env]
            for sc in screens:
                if e.kind == "wayland" and not sc[0].isdigit(): sc = "3840x1080"
                if not self.docker_ok: self.skip(env, sc, "not available: " + self.docker_why); continue
                if not self.ensure_image(e.image): self.skip(env, sc, "not available: Docker image %s could not be built" % self.images[e.image]["tag"]); continue
                extra = device_args(e)   # a missing device is not passed; the render_device precondition test then fails inside
                if e.headed:
                    h, why = headed_args(); extra = list(h) + extra
                    if why: self.skip(env, sc, "not available: " + why); continue
                    say("WARNING: %s opens a KWin window on THIS desktop; do not touch the mouse or keyboard while it runs." % env)
                say("== %s %s (%s, %d runs) %s" % (env, sc, self.label, self.runs_for(env), time.strftime("%T")))
                self.run_container(env, sc, extra)

    def host(self):
        st = os.environ.get("XDG_SESSION_TYPE", "unknown"); h = envinfo.detect_host()
        self.add("HOSTENV " + " ".join("%s=%s" % kv for kv in h.items()))
        say("== host: session=%s desktop=%s DISPLAY=%s WAYLAND_DISPLAY=%s" % (st, h["desktop"], os.environ.get("DISPLAY", "unset"), os.environ.get("WAYLAND_DISPLAY", "unset")))
        say("WARNING: host mode opens real Oolite windows on THIS desktop (about 20 s each), presses keys and moves the pointer.\n"
              "         Do not touch the mouse or keyboard during the automated runs.")
        if not self.a.no_prompt and sys.stdin.isatty():
            if input("Continue with host mode? [y/N] ").strip().lower()[:1] != "y": self.skip("host-" + h["desktop"].lower(), "host", "not run: declined at the confirmation"); return
        else: time.sleep(5)
        scr = envinfo.screen_size(); names = ["host-x11"] if st != "wayland" else ["host-xwayland", "host-native"]
        if not os.environ.get("DISPLAY") and not os.environ.get("WAYLAND_DISPLAY"):
            for n in names: self.skip(n, scr, "not available: no desktop session"); return
        for n in names:
            e = self.envs[n]
            if e.session == "Wayland native": self.host_cell(n, scr); continue
            if not os.environ.get("DISPLAY"): self.skip(n, scr, "not available: no DISPLAY (X11/XWayland) in this session"); continue
            helper = None
            if self.docker_ok and self.ensure_image(e.image): helper = self.start_helper(e)
            elif not all(shutil.which(t) for t in ("xwininfo", "xprop", "xdotool", "xrandr")):
                self.skip(n, scr, "not available: X tools missing on host and no helper container (%s)" % (self.docker_why or "image build failed")); continue
            say("== %s: game on the host, X measured %s (%d runs) %s" % (n, "in helper container " + helper if helper else "with host tools", self.a.host_runs, time.strftime("%T")))
            try: self.host_cell(n, scr, helper)
            finally:
                if helper: subprocess.run(["docker", "rm", "-f", helper], capture_output=True)

    def start_helper(self, e):
        """Helper container: python-xlib + X tools, sharing the host X display. Only measures; the game runs on the host."""
        name = "uitest-helper"; subprocess.run(["docker", "rm", "-f", name], capture_output=True)
        xa = os.environ.get("XAUTHORITY") or os.path.expanduser("~/.Xauthority")
        cmd = ["docker", "run", "-d", "--rm", "--name", name, "--net=host", "-e", "DISPLAY=" + os.environ["DISPLAY"], "-v", "/tmp/.X11-unix:/tmp/.X11-unix",
               "-v", "%s:/uitest:ro" % PKG, "-e", "PYTHONPATH=/uitest/src"]
        if os.path.exists(xa): cmd += ["-v", xa + ":/tmp/hostxauth:ro", "-e", "XAUTHORITY=/tmp/hostxauth"]
        cmd += [self.images[e.image]["tag"], "sleep", "infinity"]
        return name if subprocess.run(cmd, capture_output=True).returncode == 0 else None

    def host_cell(self, env, scr, helper=None):
        """One host environment: every pytest test, run here on the host with the venv's pytest; without the venv only the startup checks."""
        py, why = host_python(os.path.join(self.out, "host-venv.log"))
        if py is None:
            say("  NOTE: %s; only the startup checks run (frame, focus, centring)" % why)
            self.add("WARN wm=%s build=%s run=0 text=only the startup checks ran (frame, focus, centring): %s, so the screen, key, mouse and F12 tests did not" % (env, self.label, why))
            return self.host_inprocess(env, scr, helper)
        part = "%s-%s.raw" % (env, scr.replace(":", "_")); open(os.path.join(self.parts, part), "w").close()
        cmd = self.pytest_args(env, scr, part, self.path, python=py, tests=GAME_TESTS, reg=self.a.registry or registry.DEFAULT_PATH, out=self.out)
        cmd += ["--ui-helper", helper] if helper else []
        cmd += ["--ui-no-prompt"] if self.a.no_prompt else []
        # output captured as for the containers; the ask probe's questions still reach the user, it talks to /dev/tty directly
        self.collect(env, scr, part, *self.follow(cmd, part, env=dict(os.environ, PYTHONPATH=os.path.join(PKG, "src"), PYTHONDONTWRITEBYTECODE="1")))

    def host_inprocess(self, env, scr, helper=None):
        """Runs ON THE HOST (host libraries and drivers), pure stdlib. X rows: measured through the helper container; native Wayland:
        KWin D-Bus / sway IPC probes, else y/n questions. Under XWayland on KDE the KWin probe cross-checks frame/focus."""
        e = self.envs[env]
        s = Session(e, scr, probe_kw={"no_prompt": self.a.no_prompt}, helper=helper)
        try: s.start()
        except SessionError as ex: self.skip(env, scr, "not available: %s" % ex); return
        opts = scenarios.Opts(tol=self.a.tol)
        try:
            say("== %s %s (%d runs) %s" % (self.label, env, self.a.host_runs, time.strftime("%T")))
            for n in range(1, self.a.host_runs + 1):
                g = scenarios.Game(self.path, [], s.game_env).start()
                try:
                    if not self.a.no_prompt: say(">> Run %d: the Oolite window is open now. Please look at it (do not close it)." % n)
                    rec = scenarios.record(s, g, env, self.label, scr, n, opts)
                finally: g.stop()
                self.add(raw_results.format_result(rec))
        finally: s.stop()

    def report(self):
        """The single-build report of this result set (no verdicts against another build)."""
        hdr = self.stem + "-env.txt"; open(hdr, "w").write(envinfo.header(self.version()) + "\npurpose: %s\n" % (self.purpose or "not given") +
                                                          "build %s: %s\n" % (self.label, os.path.basename(self.path))); md = self.md
        argv = [self.raw, md, "--control", self.label, "--minruns", str(self.a.minruns), "--host-minruns", str(self.a.host_runs), "--tol", str(self.a.tol), "--header", hdr]
        rc = report.main(argv)
        say("Report: %s\n(raw: %s, environment: %s; send these files)" % (md, self.raw, hdr)); return rc

    def version(self):
        try: return subprocess.run(["git", "describe", "--always", "--dirty"], cwd=PKG, capture_output=True, text=True).stdout.strip() or "unversioned"
        except OSError: return "unversioned"


def build_parser():
    p = argparse.ArgumentParser(prog="uitest", description="Window frame / focus / centring tests for Oolite builds. `uitest run LABEL:APPIMAGE` tests one build; "
                                "`uitest compare --control SET --candidate SET` compares saved result sets; with several builds the FIRST label is the control.")
    p.add_argument("builds", nargs="*", help="label:path/to/Oolite.AppImage (`uitest run` takes exactly one)")
    p.add_argument("--env", "--wm", dest="env", default=DEFAULT_ENVS, help="environment names from environments.toml (default: the X11 window managers)")
    p.add_argument("--screens", default="3840x1080", help="WxH or 2head, comma separated")
    p.add_argument("--runs", type=int, default=10); p.add_argument("--toggle", action="store_true")
    p.add_argument("--wayland", action="store_true", help="also the headless Wayland compositors (XWayland and native)")
    p.add_argument("--host", action="store_true", help="also the live desktop (opens windows on your screen)")
    p.add_argument("--host-runs", type=int, default=5); p.add_argument("--no-prompt", action="store_true")
    p.add_argument("--out"); p.add_argument("--name"); p.add_argument("--control"); p.add_argument("--candidates", default="")
    p.add_argument("--tests", default="", help="run only these tests, comma separated, with or without the test_ prefix (e.g. has_frame,gets_focus); see the tests folder next to the framework")
    p.add_argument("--quick", action="store_true", help="smoke run: 1 run, first screen size only, and (unless --tests is given) only %s" % QUICK_TESTS)
    p.add_argument("--minruns", type=int, default=10); p.add_argument("--tol", type=int, default=40); p.add_argument("--equiv", default="")
    p.add_argument("--registry", default=""); p.add_argument("--list", action="store_true", help="list the registry and exit")
    p.add_argument("--report", metavar="PATH", help="markdown report path (raw and env files take the same stem); default results/uitest-<date>-<label>.md")
    p.add_argument("--desc", default="", help="REQUIRED (or --desc-file): what this run is for (shown as Purpose at the top of the report)")
    p.add_argument("--desc-file", metavar="PATH", help="same, from a (markdown) file")
    p.add_argument("--note", action="append", default=[], metavar="LABEL=TEXT", help="note for a build, shown in the Builds table (repeatable)")
    p.add_argument("-q", "--quiet", action="store_true", help="print only PASS or FAIL (errors on stderr); the report files are still written")
    p.add_argument("--strict", action="store_true", help="SUSPECT and STILL BROKEN also count as FAIL")
    p.add_argument("--selftest", action="store_true", help="run the verdict self-test and exit")
    p.add_argument("--report-only", metavar="RAW", help="render a report from an existing raw file and exit")
    return p


def host_python(log, venv=None, run=subprocess.run):
    """(python of the host-mode venv, '') or (None, why). Made on first use with `python3 -m venv` and HOST_PYTEST from PyPI (log: `log`);
    pytest is never installed into the host's own python."""
    venv = venv or HOST_VENV; py = os.path.join(venv, "bin", "python")
    want = HOST_PYTEST.split("==")[1]
    def has_pytest():
        return os.path.exists(py) and run([py, "-c", "import pytest; print(pytest.__version__)"], capture_output=True, text=True).stdout.strip() == want
    if has_pytest(): return py, ""
    say("Making the host-mode venv %s with %s (first use only). Log: %s" % (venv, HOST_PYTEST, log))
    with open(log, "w") as lf:
        for c in ([sys.executable, "-m", "venv", venv], [py, "-m", "pip", "install", "-q", HOST_PYTEST]):
            if run(c, stdout=lf, stderr=subprocess.STDOUT).returncode != 0:
                return None, "could not make the host-mode venv (%s failed; see %s)" % (" ".join(c[:4]), log)
    return (py, "") if has_pytest() else (None, "the host-mode venv has no %s (see %s)" % (HOST_PYTEST, log))


def device_args(e, exists=os.path.exists):
    """docker run options for the host devices an environment declares (`devices`), the ones the host has."""
    return [a for d in e.devices if exists(d) for a in ("--device", d)]


def headed_args(environ=None, exists=os.path.exists, hostname=socket.gethostname):
    """docker run options for a headed environment: the host X socket (only that one, so the compositor's XWayland display stays
    inside the container), the X cookie (matched by hostname), the GPU (a nested kwin_wayland needs a render node). -> (args, why-not)."""
    environ = os.environ if environ is None else environ
    m = re.fullmatch(r"(?:unix)?:(\d+)(?:\.\d+)?", environ.get("DISPLAY", ""))
    if not m: return (), "headed needs a local host X display (DISPLAY is %r)" % environ.get("DISPLAY", "")
    sock = "/tmp/.X11-unix/X" + m[1]
    if not exists(sock): return (), "headed: no X socket %s" % sock
    if not exists("/dev/dri"): return (), "headed needs /dev/dri (GPU) on the host"
    args = ["--device", "/dev/dri", "--hostname", hostname(), "-v", "%s:%s" % (sock, sock), "-e", "UITEST_HOST_DISPLAY=:" + m[1]]
    xa = environ.get("XAUTHORITY") or os.path.expanduser("~/.Xauthority")
    if exists(xa): args += ["-v", xa + ":/tmp/hostxauth:ro", "-e", "UITEST_HOST_XAUTHORITY=/tmp/hostxauth"]
    return args, ""


def failed_tests(raw):
    """['test (env)'] for every TEST line of the raw file that failed. The verdict counts only the RESULT criteria, so a single-build run needs this."""
    out = []
    try: lines = open(raw).read().splitlines()
    except OSError: return out
    for ln in lines:
        m = re.match(r"TEST wm=(\S+) .*? test=(\S+) outcome=failed", ln)
        if m: out.append("%s (%s)" % (m[2], m[1]))
    return out


def compare_parser():
    p = argparse.ArgumentParser(prog="uitest compare", description="Verdicts (FIXED / REGRESSED / ...) from result sets written by separate `uitest run`s.")
    p.add_argument("--control", required=True, metavar="SET", help="the control's result set: results/<name> or results/<name>.raw")
    p.add_argument("--candidate", action="append", required=True, metavar="SET", help="a candidate's result set (repeatable)")
    p.add_argument("--report", metavar="PATH", help="markdown report path; default results/compare-<date>-<candidates>.md")
    p.add_argument("--desc", default="", help="what this comparison is for (default: the control run's purpose)")
    p.add_argument("--minruns", type=int, default=10); p.add_argument("--host-minruns", type=int, default=5); p.add_argument("--tol", type=int, default=40)
    p.add_argument("--equiv", default=""); p.add_argument("--registry", default="")
    p.add_argument("-q", "--quiet", action="store_true"); p.add_argument("--strict", action="store_true")
    return p


def read_set(path):
    """A result set -> (raw path, label, lines). Accepts results/<name>, results/<name>.raw or results/<name>.md."""
    stem = re.sub(r"\.(raw|md)$", "", path); raw = stem + ".raw"
    try: lines = open(raw).read().splitlines()
    except OSError: _die("result set not found: %s" % raw)
    labels = []
    for ln in lines:
        if ln.startswith("SET "): labels.append(json.loads(ln[4:])["label"])
    if not labels:   # older raw files have no SET header: the builds of their BUILD lines
        labels = [json.loads(ln[6:])["label"] for ln in lines if ln.startswith("BUILD ")]
    if len(set(labels)) != 1: _die("%s is not a single-build result set (builds: %s); make one per build with `uitest run`" % (raw, ", ".join(labels) or "none"))
    return raw, labels[0], lines


def compare_sets(control, candidates, stem, desc=""):
    """Join the result sets into <stem>.raw (one PURPOSE line, every set's other lines) -> (raw path, control label, candidate labels)."""
    sets = [read_set(control)] + [read_set(c) for c in candidates]
    labels = [l for _, l, _ in sets]
    if len(set(labels)) != len(labels): _die("two result sets have the same build label (%s): rename one with uitest run's label" % ", ".join(labels))
    purpose = desc
    if not purpose:
        for ln in sets[0][2]:
            if ln.startswith("PURPOSE "): purpose = json.loads(ln[8:])
    out = ["PURPOSE " + json.dumps(purpose)]
    for raw, _, lines in sets:
        out += ["SOURCE " + json.dumps({"set": raw})] + [ln for ln in lines if not ln.startswith("PURPOSE ")]
    os.makedirs(os.path.dirname(stem) or ".", exist_ok=True)
    open(stem + ".raw", "w").write("\n".join(out) + "\n")
    hdr = stem + "-env.txt"
    with open(hdr, "w") as f:
        for raw, label, _ in sets:
            env = raw[:-4] + "-env.txt"
            f.write("== %s (%s)\n" % (label, raw) + (open(env).read() if os.path.exists(env) else "(no environment file)\n") + "\n")
    return stem + ".raw", labels[0], labels[1:]


def exit_code(L, md, quiet=False, strict=False, failed=None):
    """EXIT_* from report.LAST; `failed` (single-build runs) = failed tests, which fail the run even without a verdict."""
    if not L.get("measured"):
        print("uitest: error: nothing was measured (see %s)" % md, file=sys.stderr); return EXIT_ERROR
    if L["regressed"] or (strict and (L["suspect"] or L["still_broken"])): return EXIT_FAIL
    if failed:
        if not quiet: print("FAILED TESTS: " + "; ".join(failed))
        return EXIT_FAIL
    return EXIT_PASS


def finish(rc, md, quiet):
    if quiet and rc != EXIT_ERROR: print("PASS" if rc == EXIT_PASS else "FAIL")
    elif not quiet: print({EXIT_PASS: "PASS", EXIT_FAIL: "FAIL", EXIT_ERROR: "ERROR (could not run)"}[rc] + "  report: " + md)
    return rc


def compare_main(argv):
    a = compare_parser().parse_args(argv)
    envs = registry.load(a.registry or None)[0]; report.set_registry(envs)
    out, name = output_stem(argparse.Namespace(report=a.report, out=None, name=None), "compare-%s-%s" % (stamp(), "+".join(read_set(c)[1] for c in a.candidate)))
    stem = os.path.join(out, name)
    raw, control, cands = compare_sets(a.control, a.candidate, stem, a.desc)
    md = stem + ".md"
    with contextlib.redirect_stdout(io.StringIO()) if a.quiet else contextlib.nullcontext():
        report.main([raw, md, "--control", control, "--candidates", ",".join(cands), "--minruns", str(a.minruns), "--host-minruns", str(a.host_minruns),
                     "--tol", str(a.tol), "--equiv", a.equiv, "--header", stem + "-env.txt", "--registry", a.registry or registry.DEFAULT_PATH])
    return finish(exit_code(report.LAST, md, a.quiet, a.strict), md, a.quiet)


def run_one(a, build, name=None, note=""):
    """The coordinator for one build -> (Runner, rc). rc is None when the run itself is fine (the caller decides from the report)."""
    r = Runner(a, build, name, note)
    names = [x for x in a.env.split(",") if x] + ([x for x in WAYLAND_ENVS.split(",")] if a.wayland else [])
    r.docker_cells(names, a.screens.split(","))
    if a.host: r.host()
    r.report()
    want_docker = any(n in r.envs and r.envs[n].kind != "host" for n in names)
    if want_docker and not r.docker_ok:
        print("uitest: error: %s (docker environments were requested)" % r.docker_why, file=sys.stderr); return r, EXIT_ERROR
    return r, None


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv[:1] == ["compare"]:
        try: return compare_main(argv[1:])
        except SystemExit as e: return e.code if isinstance(e.code, int) else EXIT_ERROR
    single = argv[:1] == ["run"]
    a = build_parser().parse_args(argv[1:] if single else argv)
    if a.quick:
        a.runs, a.host_runs, a.minruns = 1, 1, 1
        a.screens = a.screens.split(",")[0]
        a.tests = a.tests or QUICK_TESTS
    if a.selftest: return report.main(["--selftest"])
    if a.report_only:
        return report.main([a.report_only, a.report or a.report_only[:-4] + ".md" if a.report_only.endswith(".raw") else a.report or "report.md",
                            "--control", a.control or "base", "--candidates", a.candidates, "--minruns", str(a.minruns),
                            "--host-minruns", str(a.host_runs), "--tol", str(a.tol), "--registry", a.registry or registry.DEFAULT_PATH])
    if a.list:
        envs, _ = registry.load(a.registry or None)
        for n, e in envs.items(): say("%-18s %-8s %-15s %-8s image=%s" % (n, e.family, e.session, e.kind, e.image))
        return 0
    if not a.builds: build_parser().print_usage(file=sys.stderr); return EXIT_ERROR
    if single and len(a.builds) != 1: print("uitest: error: `uitest run` takes exactly one LABEL:APPIMAGE (compare runs with `uitest compare`)", file=sys.stderr); return EXIT_ERROR
    if not (a.desc.strip() or a.desc_file):
        print("uitest: error: --desc TEXT (or --desc-file PATH) is required: say what this run is for, it heads the report", file=sys.stderr)
        return EXIT_ERROR
    global _QUIET
    _QUIET = a.quiet
    sink = io.StringIO() if a.quiet else None
    try:
        with contextlib.redirect_stdout(sink) if a.quiet else contextlib.nullcontext():
            builds = [parse_build(b) for b in a.builds]
            if len({l for l, _ in builds}) != len(builds): _die("two builds have the same label")
            notes = parse_notes(a, [l for l, _ in builds])
            if len(builds) == 1:
                r, rc = run_one(a, builds[0], note=notes.get(builds[0][0], ""))
                if rc is None: rc = exit_code(report.LAST, r.md, a.quiet, a.strict, failed_tests(r.raw))
                md = r.md
            else:   # several builds: one `run` per build (results/<name>-<label>), then `compare` into results/<name>
                control = a.control or builds[0][0]
                if control not in [l for l, _ in builds]: _die("--control '%s' is not one of the labels" % control)
                out, name = output_stem(a, "uitest-%s-%s" % (stamp(), "+".join(l for l, _ in builds if l != control)))
                sets = {}; rc = None
                for b in builds:
                    r, brc = run_one(a, b, "%s-%s" % (name, b[0]), notes.get(b[0], ""))
                    sets[b[0]] = r.stem; rc = brc if brc is not None else rc
                cands = [c for c in (a.candidates.split(",") if a.candidates else [l for l, _ in builds if l != control]) if c]
                md = os.path.join(out, name + ".md")
                if rc is None:
                    raw, _, _ = compare_sets(sets[control], [sets[c] for c in cands], os.path.join(out, name), purpose_of(a))
                    report.main([raw, md, "--control", control, "--candidates", ",".join(cands), "--minruns", str(a.minruns), "--host-minruns", str(a.host_runs),
                                 "--tol", str(a.tol), "--equiv", a.equiv, "--header", os.path.join(out, name + "-env.txt")])
                    say("Report: %s (per-build result sets: %s)" % (md, ", ".join(sets[l] + ".raw" for l, _ in builds)))
                    rc = exit_code(report.LAST, md, a.quiet, a.strict)
    except SystemExit as e:
        return e.code if isinstance(e.code, int) else EXIT_ERROR
    finally:
        _QUIET = False
    return finish(rc, md, a.quiet)
