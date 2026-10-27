"""Host side of uitest: needs only python3 stdlib and docker. Builds images, runs pytest inside the right containers, collects the raw
files, renders the report. Host mode (--host) runs pytest in a helper container against the live X display; native Wayland runs here."""
import argparse
import hashlib
import json
import datetime
import os
import shutil
import socket
import re
import shlex
import subprocess
import sys
import time

from . import envinfo, raw_results, registry, scenarios, report
from .session import Session, SessionError

PKG = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))      # the framework folder (holds src/, docker/, environments.toml)
GAME_TESTS = os.path.join(os.path.dirname(os.path.dirname(PKG)), "tests", "ui")             # the tests of the game: tests/ui/ at the repo root
DEFAULT_ENVS = "marco,openbox,xfwm4,muffin,kwin,mutter"
WAYLAND_ENVS = "kwin-xwayland,kwin-native,sway-xwayland,sway-native,mutter-xwayland,mutter-native,weston-xwayland,weston-native"


QUICK_TESTS = "game_launches,title_menu_is_displayed"   # --quick: the shared launch plus one title-menu launch per environment


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
    if not _QUIET: print(*a)


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


class Runner:
    def __init__(self, a):
        self.a = a; self.envs, self.images = registry.load(a.registry or None)
        report.set_registry(self.envs)
        self.builds = []
        for b in a.builds:
            label, _, path = b.partition(":")
            if not path or not os.path.isfile(path): _die("AppImage not found or bad label:path '%s'" % b)
            self.builds.append((label, os.path.realpath(path)))
        self.control = a.control or self.builds[0][0]
        cands = [l for l, _ in self.builds if l != self.control] or [self.control]
        if a.report:
            md = os.path.abspath(a.report); self.out = os.path.dirname(md); self.name = os.path.basename(md)[:-3] if md.endswith(".md") else os.path.basename(md)
        else:
            self.out = os.path.abspath(a.out or os.path.join(PKG, "results"))
            self.name = a.name or "uitest-%s-%s" % (datetime.datetime.now().strftime("%Y%m%d-%H%M%S"), "+".join(cands))
        self.name = "".join(c if c.isalnum() or c in "+-_." else "_" for c in self.name)
        self.stem = os.path.join(self.out, self.name); self.md = self.stem + ".md"; self.parts = self.stem + ".parts"
        os.makedirs(self.parts, exist_ok=True)
        self.raw = self.stem + ".raw"; open(self.raw, "w").close()
        self.purpose = self.read_purpose()
        notes = {}
        for n in a.note:
            k, _, v = n.partition("=")
            if not v: _die("--note needs LABEL=TEXT, got '%s'" % n)
            notes[k] = v
        for k in notes:
            if k not in [l for l, _ in self.builds]: _die("--note for unknown label '%s'" % k)
        self.add("PURPOSE " + json.dumps(self.purpose))
        for label, path in self.builds:
            h = hashlib.sha256()
            with open(path, "rb") as f:
                for chunk in iter(lambda: f.read(1 << 20), b""): h.update(chunk)
            self.add("BUILD " + json.dumps({"label": label, "file": os.path.basename(path), "sha256": h.hexdigest()[:12], "note": notes.get(label, "")}))
        self.docker_ok, self.docker_why = docker_state()
        self.img_ok = {}
        if not self.docker_ok: say("NOTE: Docker parts will be skipped: " + self.docker_why)

    def read_purpose(self):
        a = self.a
        if a.desc_file:
            try: return open(a.desc_file, encoding="utf-8").read().strip()
            except OSError as e: _die("cannot read --desc-file: %s" % e)
        text = (a.desc or "").strip()
        if a.tests:   # a partial run must never be read as a full pass
            text = (text + "\n\n" if text else "") + "PARTIAL RUN: only these tests ran: %s%s" % (test_selector(a.tests).replace(" or ", ", "), " (--quick)" if a.quick else "")
        return text

    def add(self, line):
        with open(self.raw, "a") as f: f.write(line + "\n")

    def skip(self, wm, screen, why):
        for label, _ in self.builds: self.add(raw_results.format_skip(wm, screen, label, why))
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

    def pytest_args(self, env, screen, part, apps, host_dir=None):
        c = ["python3", "-m", "pytest", "-q", "-c", "/gametests/pytest.ini", "/gametests", "--rootdir", "/gametests",
             "--ui-registry", "/uitest/environments.toml", "--ui-env", env, "--ui-screen", screen, "--ui-runs", str(self.runs_for(env)),
             "--ui-raw", "/out/%s.parts/%s" % (self.name, part), "--junitxml", "/out/%s.parts/%s.xml" % (self.name, part), "--ui-shots", "/out/%s.shots" % self.name, "--ui-logs", "/out/%s.logs" % self.name, "--ui-tol", str(self.a.tol)]
        if self.a.toggle: c.append("--ui-toggle")
        if self.a.tests: c += ["-k", test_selector(self.a.tests)]
        for label, mnt in apps: c += ["--ui-app", "%s=%s" % (label, mnt)]
        return c

    def runs_for(self, env):
        return self.a.host_runs if self.envs[env].kind == "host" else self.a.runs

    def run_container(self, env, screen, extra=(), user=None):
        e = self.envs[env]; part = "%s-%s.raw" % (env, screen.replace(":", "_"))
        open(os.path.join(self.parts, part), "w").close()
        mounts = ["-v", "%s:/uitest:ro" % PKG, "-v", "%s:/gametests:ro" % GAME_TESTS, "-v", "%s:/out" % self.out, "-e", "PYTHONPATH=/uitest/src"]; apps = []
        for i, (label, path) in enumerate(self.builds):
            mounts += ["-v", "%s:/apps/%s:ro" % (os.path.dirname(path), label)]; apps.append((label, "/apps/%s/%s" % (label, os.path.basename(path))))
        cmd = ["docker", "run", "--rm"] + mounts + list(extra) + [self.images[e.image]["tag"]] + give_back_output(self.name) + self.pytest_args(env, screen, part, apps)
        r = subprocess.run(cmd, capture_output=True, text=True)
        tail = [l for l in r.stdout.splitlines() if l.strip()][-1:] or [r.stderr.strip()[-200:]]
        say("  %s" % tail[0])
        # copy the parts in; a failed pytest (hard failure) leaves a SKIP row with the reason
        data = open(os.path.join(self.parts, part)).read()
        if data: open(self.raw, "a").write(data)
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
                extra = ()
                if e.headed:
                    extra, why = headed_args()
                    if why: self.skip(env, sc, "not available: " + why); continue
                    say("WARNING: %s opens a KWin window on THIS desktop; do not touch the mouse or keyboard while it runs." % env)
                say("== %s %s (%s builds x %d runs) %s" % (env, sc, len(self.builds), self.runs_for(env), time.strftime("%T")))
                self.run_container(env, sc, extra)

    def host(self):
        st = os.environ.get("XDG_SESSION_TYPE", "unknown"); h = envinfo.detect_host()
        self.add("HOSTENV " + " ".join("%s=%s" % kv for kv in h.items()))
        say("== host: session=%s desktop=%s DISPLAY=%s WAYLAND_DISPLAY=%s" % (st, h["desktop"], os.environ.get("DISPLAY", "unset"), os.environ.get("WAYLAND_DISPLAY", "unset")))
        say("WARNING: host mode opens real Oolite windows on THIS desktop (each run about 17 s) and may press F12 (--toggle).\n"
              "         Do not touch the mouse or keyboard during the automated runs.")
        if not self.a.no_prompt and sys.stdin.isatty():
            if input("Continue with host mode? [y/N] ").strip().lower()[:1] != "y": self.skip("host-" + h["desktop"].lower(), "host", "not run: declined at the confirmation"); return
        else: time.sleep(5)
        scr = envinfo.screen_size(); names = ["host-x11"] if st != "wayland" else ["host-xwayland", "host-native"]
        if not os.environ.get("DISPLAY") and not os.environ.get("WAYLAND_DISPLAY"):
            for n in names: self.skip(n, scr, "not available: no desktop session"); return
        for n in names:
            e = self.envs[n]
            if e.session == "Wayland native": self.host_inprocess(n, scr); continue
            if not os.environ.get("DISPLAY"): self.skip(n, scr, "not available: no DISPLAY (X11/XWayland) in this session"); continue
            helper = None
            if self.docker_ok and self.ensure_image(e.image): helper = self.start_helper(e)
            elif not all(shutil.which(t) for t in ("xwininfo", "xprop", "xdotool", "xrandr")):
                self.skip(n, scr, "not available: X tools missing on host and no helper container (%s)" % (self.docker_why or "image build failed")); continue
            say("== %s: game on the host, X measured %s (%d runs per build) %s" % (n, "in helper container " + helper if helper else "with host tools", self.a.host_runs, time.strftime("%T")))
            try: self.host_inprocess(n, scr, helper)
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

    def host_inprocess(self, env, scr, helper=None):
        """Runs ON THE HOST (host libraries and drivers), pure stdlib. X rows: measured through the helper container; native Wayland:
        KWin D-Bus / sway IPC probes, else y/n questions. Under XWayland on KDE the KWin probe cross-checks frame/focus."""
        e = self.envs[env]
        s = Session(e, scr, probe_kw={"no_prompt": self.a.no_prompt}, helper=helper)
        try: s.start()
        except SessionError as ex: self.skip(env, scr, "not available: %s" % ex); return
        opts = scenarios.Opts(tol=self.a.tol)
        try:
            for label, path in self.builds:
                say("== %s %s (%d runs) %s" % (label, env, self.a.host_runs, time.strftime("%T")))
                for n in range(1, self.a.host_runs + 1):
                    g = scenarios.Game(path, [], s.game_env).start()
                    try:
                        if not self.a.no_prompt: say(">> Run %d: the Oolite window is open now. Please look at it (do not close it)." % n)
                        rec = scenarios.record(s, g, env, label, scr, n, opts)
                    finally: g.stop()
                    self.add(raw_results.format_result(rec))
        finally: s.stop()

    def report(self):
        hdr = self.stem + "-env.txt"; open(hdr, "w").write(envinfo.header(self.version()) + "\npurpose: %s\n" % (self.purpose or "not given") + "".join(
            "build %s: %s\n" % (b[0], b[1]) for b in [(l, os.path.basename(p)) for l, p in self.builds])); md = self.md
        argv = [self.raw, md, "--control", self.control, "--candidates", self.a.candidates, "--minruns", str(self.a.minruns), "--host-minruns", str(self.a.host_runs),
                "--tol", str(self.a.tol), "--equiv", self.a.equiv, "--header", hdr]
        rc = report.main(argv)
        say("Report: %s\n(raw: %s, environment: %s; send these files)" % (md, self.raw, hdr)); return rc

    def version(self):
        try: return subprocess.run(["git", "describe", "--always", "--dirty"], cwd=PKG, capture_output=True, text=True).stdout.strip() or "unversioned"
        except OSError: return "unversioned"


def build_parser():
    p = argparse.ArgumentParser(prog="uitest", description="Window frame / focus / centring matrix for Oolite builds. The FIRST label is the control.")
    p.add_argument("builds", nargs="*", help="label:path/to/Oolite.AppImage")
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
    p.add_argument("--report", metavar="PATH", help="markdown report path (raw and env files take the same stem); default results/uitest-<date>-<candidates>.md")
    p.add_argument("--desc", default="", help="REQUIRED (or --desc-file): what this run is for (shown as Purpose at the top of the report)")
    p.add_argument("--desc-file", metavar="PATH", help="same, from a (markdown) file")
    p.add_argument("--note", action="append", default=[], metavar="LABEL=TEXT", help="note for a build, shown in the Builds table (repeatable)")
    p.add_argument("-q", "--quiet", action="store_true", help="print only PASS or FAIL (errors on stderr); the report files are still written")
    p.add_argument("--strict", action="store_true", help="SUSPECT and STILL BROKEN also count as FAIL")
    p.add_argument("--selftest", action="store_true", help="run the verdict self-test and exit")
    p.add_argument("--report-only", metavar="RAW", help="render a report from an existing raw file and exit")
    return p


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


def main(argv=None):
    a = build_parser().parse_args(argv)
    if a.quick:
        a.runs, a.host_runs, a.minruns = 1, 1, 1
        a.screens = a.screens.split(",")[0]
        a.tests = a.tests or QUICK_TESTS
    if a.selftest: return report.main(["--selftest"])
    if a.report_only:
        return report.main([a.report_only, a.out or "report.md", "--control", a.control or "base", "--candidates", a.candidates, "--minruns", str(a.minruns),
                             "--host-minruns", str(a.host_runs), "--tol", str(a.tol), "--registry", a.registry or registry.DEFAULT_PATH])
    if a.list:
        envs, _ = registry.load(a.registry or None)
        for n, e in envs.items(): say("%-18s %-8s %-15s %-8s image=%s" % (n, e.family, e.session, e.kind, e.image))
        return 0
    if not a.builds: build_parser().print_usage(file=sys.stderr); return EXIT_ERROR
    if not (a.desc.strip() or a.desc_file):
        print("uitest: error: --desc TEXT (or --desc-file PATH) is required: say what this run is for, it heads the report", file=sys.stderr)
        return EXIT_ERROR
    global _QUIET
    _QUIET = a.quiet
    import contextlib, io
    sink = io.StringIO() if a.quiet else None
    try:
        with contextlib.redirect_stdout(sink) if a.quiet else contextlib.nullcontext():
            r = Runner(a)
            names = [x for x in a.env.split(",") if x] + ([x for x in WAYLAND_ENVS.split(",")] if a.wayland else [])
            r.docker_cells(names, a.screens.split(","))
            if a.host: r.host()
            r.report()
    except SystemExit as e:
        return e.code if isinstance(e.code, int) else EXIT_ERROR
    finally:
        _QUIET = False
    L = report.LAST
    want_docker = any(n in r.envs and r.envs[n].kind != "host" for n in names)
    if want_docker and not r.docker_ok:
        print("uitest: error: %s (docker environments were requested)" % r.docker_why, file=sys.stderr); rc = EXIT_ERROR
    elif not L.get("measured"):
        print("uitest: error: nothing was measured (see %s)" % r.md, file=sys.stderr); rc = EXIT_ERROR
    elif L["regressed"] or (a.strict and (L["suspect"] or L["still_broken"])): rc = EXIT_FAIL
    else: rc = EXIT_PASS
    if rc == EXIT_PASS and len(a.builds) == 1:
        failed = failed_tests(r.raw)
        if failed:
            rc = EXIT_FAIL
            if not a.quiet: print("FAILED TESTS: " + "; ".join(failed))
    if a.quiet and rc != EXIT_ERROR: print("PASS" if rc == EXIT_PASS else "FAIL")
    elif not a.quiet: print({EXIT_PASS: "PASS", EXIT_FAIL: "FAIL", EXIT_ERROR: "ERROR (could not run)"}[rc] + "  report: " + r.md)
    return rc
