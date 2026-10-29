"""pytest plugin: the uitest test layer.

* tests ONE AppImage (--ui-app, named by --ui-label) in ONE environment; comparing builds is done later from the raw files (uitest compare)
* options (--ui-*), the registry-driven `case` parameter (env x run, ids like marco-x11-run3), markers per env / family / session
* fixtures: `session_mgr` (display server + WM, started once), `launched_game` (ONE launch per case, shared by the read-only tests),
  `fresh_game` and `app` (a launch of their own, for tests that change game state or drive screens)
* collects pytest's outcomes per test and case, writes the raw file (RESULT lines, plus TEST lines with skip reasons, WMVER and HARD lines)
  and a k6-style summary of pass rates. Statistics and the report are made from that raw file by oolite_ui_test_framework/report.py (host side)."""
import collections
import os
import re
import time

import pytest

from . import game_log, geometry, pass_fail, preconditions, raw_results, registry, scenarios, shared_launch, session as sessmod

Case = collections.namedtuple("Case", "env label app run")


class State:
    def __init__(self):
        self.launches = {}; self.toggles = {}; self.outcomes = collections.defaultdict(dict); self.hard = []; self.wmver = {}; self.screen = ""; self.warnings = []
        self.timing = {}   # (env, build, run, test) -> [start, seconds over setup + call + teardown]


STATE = State()


def pytest_addoption(parser):
    g = parser.getgroup("uitest")
    g.addoption("--ui-registry", default=registry.DEFAULT_PATH, help="environments.toml")
    g.addoption("--ui-env", default="", help="environment name from the registry")
    g.addoption("--ui-screen", default="3840x1080", help="WxH or 2head")
    g.addoption("--ui-app", default="", help="path/to/Oolite.AppImage: the one build these tests run against")
    g.addoption("--ui-label", default="", help="the build's name in the raw file and the report (default: the AppImage's file name)")
    g.addoption("--ui-runs", type=int, default=10)
    g.addoption("--ui-raw", default="", help="write RESULT/TEST/WMVER/HARD lines to this file")
    g.addoption("--ui-toggle", action="store_true", help="also run test_f12_toggle (fullscreen round trip)")
    g.addoption("--ui-tol", type=int, default=40)
    g.addoption("--ui-wait", type=float, default=14.0)
    g.addoption("--ui-sample", type=float, default=0.5)
    g.addoption("--ui-settle", type=float, default=3.0, help="end startup sampling once the window has not changed for this long (0 = sample for --ui-wait)")
    g.addoption("--ui-shots", default="", help="save game-window screenshots (PNG) in this directory")
    g.addoption("--ui-game-arg", action="append", default=[], help="extra argument for the game (repeatable)")
    g.addoption("--ui-logs", default="", help="keep each launch's game log (Latest.log) in this directory")
    g.addoption("--ui-helper", default="", help="host environments: the helper container that measures the host's X display (uitest starts it)")
    g.addoption("--ui-no-prompt", action="store_true", help="host environments: never ask the user; what only they could answer is not tested")


def _game(cfg, case, s, what, oversize=False):
    """A Game for this case; with --ui-logs its Latest.log is kept as <env>-<screen>-<build>-run<N>-<what>.log. Its saved window size is
    set to one that fits the screen (scenarios.window_size_for), or larger than the screen on purpose with oversize."""
    d = cfg.getoption("--ui-logs")
    keep = os.path.join(d, "%s-%s-%s-run%d-%s.log" % (case.env, cfg.getoption("--ui-screen").replace(":", "_"), case.label, case.run, what)) if d else None
    return scenarios.Game(case.app, cfg.getoption("--ui-game-arg"), s.game_env, keep_log=keep, window=scenarios.window_size_for(s.primary, oversize))


def _slug(s):
    return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")


def pytest_configure(config):
    config.pluginmanager.register(SharedLaunchFirst(), "uitest-shared-launch-first")
    config.addinivalue_line("markers", "only_wm(*names): run only in the named environments / families (WM-specific tests)")
    config.addinivalue_line("markers", "game: needs a display server and the AppImage")
    config.addinivalue_line("markers", "needs_toggle: run only with --ui-toggle (reason recorded as NOT TESTED)")
    config.addinivalue_line("markers", "needs_keys: needs injected keys to reach the game (else NOT MEASURABLE where the environment cannot deliver them)")
    config.addinivalue_line("markers", "needs_mouse: needs injected mouse clicks to reach the game (else NOT MEASURABLE where the environment cannot deliver them)")
    config.addinivalue_line("markers", "needs_x11: needs an X11 probe in the environment (else NOT MEASURABLE)")
    config.addinivalue_line("markers", "saved_window_larger_than_screen: start the game (fresh_game) with a saved window size larger than the screen")
    config.addinivalue_line("markers", "once_per_build: run for run 1 only (environment / AppImage sanity checks)")
    try: envs = registry.load(config.getoption("--ui-registry"))[0]
    except Exception: envs = {}
    for e in envs.values():
        for m in ("env_" + _slug(e.name), "family_" + _slug(e.family), "session_" + _slug(e.session)):
            config.addinivalue_line("markers", "%s: select with -m" % m)
    shared_launch.check_no_xdist(config)
    STATE.__init__(); STATE.screen = config.getoption("--ui-screen")


def _env(config):
    name = config.getoption("--ui-env")
    envs = registry.load(config.getoption("--ui-registry"))[0]
    return envs.get(name)


def pytest_generate_tests(metafunc):
    if "case" not in metafunc.fixturenames: return
    cfg = metafunc.config; env = _env(cfg); app = cfg.getoption("--ui-app")
    if env is None or not app:
        metafunc.parametrize("case", [pytest.param(None, marks=pytest.mark.skip(reason="no --ui-env / --ui-app given"))], ids=["none"], scope="session")
        return
    label = build_label(cfg)
    # The same Case objects for every test function: pytest 7 (Debian image) reuses a session fixture only for the identical param
    # (`is`), so new but equal Cases tore launched_game down and relaunched the game before every test.
    if not hasattr(cfg, "_uitest_cases"):
        cfg._uitest_cases = [Case(env.name, label, os.path.abspath(app), n) for n in range(1, cfg.getoption("--ui-runs") + 1)]
    cases = cfg._uitest_cases
    metafunc.parametrize("case", cases, ids=[pass_fail.case_id(c.env, c.run, env.session) for c in cases], scope="session")


def build_label(cfg):
    """--ui-label, else the AppImage's file name without .AppImage (e.g. 'pr774')."""
    name = cfg.getoption("--ui-label") or os.path.basename(cfg.getoption("--ui-app"))
    return re.sub(r"\.AppImage$", "", name, flags=re.I) or "app"


def pytest_collection_modifyitems(config, items):
    env = _env(config)
    drop = [i for i in items if i.get_closest_marker("once_per_build") and getattr(i, "callspec", None) and i.callspec.params.get("case") and i.callspec.params["case"].run > 1]
    if drop:
        config.hook.pytest_deselected(items=drop); items[:] = [i for i in items if i not in drop]
    for item in items:
        if item.get_closest_marker("needs_toggle") and not config.getoption("--ui-toggle"):
            item.add_marker(pytest.mark.skip(reason="NOT TESTED: toggle not run in this data (no --ui-toggle)"))
        if item.get_closest_marker("needs_keys") and env is not None and env.keys_na:
            item.add_marker(pytest.mark.skip(reason="NOT MEASURABLE: injected keys do not reach the game in %s" % env.name))
        if item.get_closest_marker("needs_mouse") and env is not None and env.mouse_na:
            item.add_marker(pytest.mark.skip(reason="NOT MEASURABLE: injected mouse clicks do not reach the game in %s" % env.name))
        if item.get_closest_marker("needs_x11") and env is not None and not any(n == "x11" for n, _ in env.probe_specs):
            item.add_marker(pytest.mark.skip(reason="NOT MEASURABLE: no X11 probe for F12 in %s" % env.name))
        if env is not None:
            item.add_marker(getattr(pytest.mark, "env_" + _slug(env.name)))
            item.add_marker(getattr(pytest.mark, "family_" + _slug(env.family)))
            item.add_marker(getattr(pytest.mark, "session_" + _slug(env.session)))
        for m in item.iter_markers("only_wm"):
            if env is None or (env.name not in m.args and env.family not in m.args):
                item.add_marker(pytest.mark.skip(reason="only for %s" % ", ".join(m.args)))


class SharedLaunchFirst:
    """Within a run, the tests on the shared launch first: a private launch (app, fresh_game) suspends it, so a shared test after one
    relaunched the game (about 18 s). A plugin of its own so it can run last, after pytest's reordering by parametrised fixture."""
    @pytest.hookimpl(trylast=True)
    def pytest_collection_modifyitems(self, items):
        items.sort(key=lambda i: (_run(i), "launched_game" not in getattr(i, "fixturenames", ())))


def _run(item):
    cs = getattr(item, "callspec", None); c = cs.params.get("case") if cs else None
    return c.run if c is not None else 0


# ---------------------------------------------------------------- fixtures
class SessionManager:
    def __init__(self, env, screen, label, helper="", no_prompt=False):
        self.env = env; self.screen = screen; self.label = label; self.session = None; self.helper = helper; self.no_prompt = no_prompt

    def get(self):
        """The started environment, started on first use and kept for the whole pytest session."""
        if self.session is not None: return self.session
        s = sessmod.Session(self.env, self.screen, probe_kw={"no_prompt": self.no_prompt}, helper=self.helper or None)
        try: s.start()
        except sessmod.SessionError as e:
            s.stop(); STATE.hard.append((self.env.name, self.screen, self.label, str(e)))
            pytest.fail("environment %s did not start: %s" % (self.env.name, e), pytrace=False)
        self.session = s
        if s.version: STATE.wmver[self.env.name] = s.version
        return s

    def stop(self):
        if self.session is not None: self.session.stop()
        self.session = None


@pytest.fixture(scope="session")
def session_mgr(request):
    env = _env(request.config)
    if env is None: pytest.skip("no --ui-env given")
    c = request.config
    m = SessionManager(env, c.getoption("--ui-screen"), build_label(c), c.getoption("--ui-helper"), c.getoption("--ui-no-prompt"))
    yield m
    m.stop()


@pytest.fixture(scope="session")
def opts(request):
    c = request.config
    return scenarios.Opts(wait=c.getoption("--ui-wait"), sample=c.getoption("--ui-sample"), settle=c.getoption("--ui-settle"), tol=c.getoption("--ui-tol"), toggle=c.getoption("--ui-toggle"))


def _launch(request, case, session_mgr, opts, with_toggle):
    cfg = request.config; assert os.path.isfile(case.app), "AppImage not found: %s" % case.app
    s = session_mgr.get()
    _only_this_game()
    game = _game(cfg, case, s, "toggle" if with_toggle else "startup").start()
    try:
        rec = scenarios.run_startup(s, game, opts)
        crashed = int(game.proc.poll() not in (None, 0) and rec.get("exited") == 1)
        if with_toggle and not rec.get("exited"): rec.update(scenarios.run_toggle(s, game, opts))
    finally:
        game.stop()
    rec.update(wm=case.env, build=case.label, screen=cfg.getoption("--ui-screen"), run=case.run, crashed=crashed)
    rec.setdefault("dx", None); rec.setdefault("dy", None)
    return geometry.apply(rec, opts.tol)


@pytest.fixture(scope="session")
def env_session(case, session_mgr):
    """The started environment (display server + WM / compositor). Request this alone for tests that need no game."""
    return session_mgr.get()


RENDER_GAP = 3   # seconds between the two screenshots
RENDER_WAIT = 10   # a compositor (KWin on XWayland) can hand out an all-black window until the first frame is presented: look again for this long


def _render_fields(s, game, rec, cfg, case):
    """Screenshot of the game window (python-xlib) + scan of the game's logs, taken while the game is still running."""
    from . import png, render_check
    out = {"render": None, "gl_errors": 0}
    texts = game_log.texts(game, ("out.log", "Latest.log"))
    n, first = render_check.scan_logs(texts); out["gl_errors"] = n
    req = next((r for r in (preconditions.requested_window(t) for f, t in texts if f == "Latest.log") if r), None)
    if req: out["requested_w"], out["requested_h"] = req
    if first: out["gl_first"] = first
    grab = getattr(s.backend, "grab", None); w = s.window_id() if s.backend is not None else None
    shot = grab(w) if grab and w else None
    t0 = time.monotonic()
    while shot and render_check.analyse(shot[2], shot[0], shot[1])["verdict"] != "ok" and time.monotonic() - t0 < RENDER_WAIT:
        time.sleep(1); shot = grab(w) or shot
    if shot:
        a = render_check.analyse(shot[2], shot[0], shot[1]); out.update(render=a["verdict"], render_colours=a["colours"], render_std=a["std"])
        time.sleep(RENDER_GAP)
        shot2 = grab(w)
        ch = render_check.changed_share(shot[2], shot2[2]) if shot2 and (shot2[0], shot2[1]) == (shot[0], shot[1]) else None
        if ch is not None: out.update(render_changed=ch, render_gap=RENDER_GAP)
        d = cfg.getoption("--ui-shots")
        if d:
            os.makedirs(d, exist_ok=True); png.write_png(os.path.join(d, "%s-%s-run%d.png" % (case.env, case.label, case.run)), shot[0], shot[1], shot[2])
    return out


@pytest.fixture(scope="session")
def launched_game(request, case, session_mgr, opts):
    """Opt-in SHARED launch: ONE game start per (env, build, run), kept running for every test that requests it. The record is a dict
    (the checks inspect it). Read-only by default; see oolite_ui_test_framework/shared_launch.py for the restore rules and the dirty check after every test."""
    cfg = request.config; assert os.path.isfile(case.app), "AppImage not found: %s" % case.app
    key = (case.env, case.label, case.run); s = session_mgr.get()

    def start():
        t0 = time.time(); game = _game(cfg, case, s, "shared").start()
        rec = scenarios.run_startup(s, game, opts); t1 = time.time()
        crashed = int(game.proc.poll() not in (None, 0) and rec.get("exited") == 1)
        rec.update(wm=case.env, build=case.label, screen=cfg.getoption("--ui-screen"), run=case.run, crashed=crashed)
        rec.setdefault("dx", None); rec.setdefault("dy", None)
        rec.update(_render_fields(s, game, rec, cfg, case))
        rec.update(start=raw_results.stamp(t0), startup_secs=round(t1 - t0, 1), render_secs=round(time.time() - t1, 1))
        rec = geometry.apply(rec, opts.tol)
        STATE.launches.setdefault(key, rec)          # the first launch is the RESULT line; a relaunch only adds a warning
        return game, rec

    def state():
        o = s.observe(cheap_only=True)
        return None if o is None else (o.outer, o.focused, o.framed)

    sl = shared_launch.SharedLaunch(start, lambda g: g.stop(), lambda g: s.window_present(g) or g.alive(), state,
                              warn=lambda t: STATE.warnings.append((case.env, case.label, case.run, t)))
    SHARED.append(sl)
    yield sl
    SHARED.remove(sl); sl.close()


SHARED = []   # shared launches that are open; a private launch suspends them so only one game runs at a time


def _only_this_game():
    """Before a private launch: stop any shared game (it relaunches before the next test that uses it). Two games at once compete for the
    CPU (key presses stall) and for focus, and stopping either one kills both."""
    for sl in SHARED: sl.suspend()


@pytest.fixture(autouse=True)
def _share_guard(request):
    """Around every test that uses launched_game: relaunch first if the previous test left it dirty, check the baseline afterwards."""
    if "launched_game" not in request.fixturenames:
        yield; return
    lg = request.getfixturevalue("launched_game")
    if hasattr(lg, "ensure_clean"): lg.ensure_clean()
    yield
    if hasattr(lg, "verify"): lg.verify(request.node.originalname)


def _require_preconditions(request, s):
    """Check what a game test's markers rely on (oolite_ui_test_framework/preconditions.py) before its game starts, so a broken environment
    fails as PRECONDITION <name> rather than as the test's own assertion. Called by the real launch fixtures, which have a session."""
    marks = {m for m in ("needs_keys", "needs_mouse") if request.node.get_closest_marker(m)}
    if not marks: return
    preconditions.require("input_tool", preconditions.input_tool(s.env))
    preconditions.require("fake_input_offered", preconditions.fake_input_offered(s.env))
    if "needs_keys" in marks: preconditions.require("key_repeat_off", preconditions.key_repeat_off(s))


class FreshGame:
    """A launch of its own for tests that change game state. .rec is the startup record; .toggle() runs F12 and returns the record with t_* fields."""
    def __init__(self, request, case, mgr, opts):
        self.request, self.case, self.mgr, self.opts = request, case, mgr, opts
        self.session = mgr.get()
        _require_preconditions(request, self.session)
        _only_this_game()
        oversize = request.node.get_closest_marker("saved_window_larger_than_screen") is not None
        t0 = time.time(); self.game = _game(request.config, case, self.session, request.node.originalname, oversize).start()
        self.rec = scenarios.run_startup(self.session, self.game, opts)
        self.rec.update(start=raw_results.stamp(t0), startup_secs=round(time.time() - t0, 1))
        self.crashed = int(self.game.proc.poll() not in (None, 0) and self.rec.get("exited") == 1)

    def toggle(self):
        if not self.rec.get("exited"): self.rec.update(scenarios.run_toggle(self.session, self.game, self.opts, shoot=self.shoot))
        else: self.rec.update(t_ok=0, t_method="key")
        return self.finish()

    def shoot(self, stage):
        """With --ui-shots: <env>-<build>-run<N>-<test>-<stage>.png of the whole compositor output (headed), else of the game window. The
        test is in the name because two tests run F12 in the same run (#42)."""
        from . import png
        d = self.request.config.getoption("--ui-shots")
        if not d: return
        s = self.session; shot = s.grab_screen()
        if shot is None:
            grab = getattr(s.backend, "grab", None); w = s.window_id() if s.backend is not None else None
            shot = grab(w) if grab and w else None
        if shot:
            os.makedirs(d, exist_ok=True); c = self.case
            test = self.request.node.originalname.replace("test_", "", 1)
            png.write_png(os.path.join(d, "%s-%s-run%d-%s-%s.png" % (c.env, c.label, c.run, test, stage)), shot[0], shot[1], shot[2])

    def finish(self):
        cfg = self.request.config; c = self.case
        self.rec.update(wm=c.env, build=c.label, screen=cfg.getoption("--ui-screen"), run=c.run, crashed=self.crashed)
        self.rec.setdefault("dx", None); self.rec.setdefault("dy", None)
        self.rec = geometry.apply(self.rec, self.opts.tol); STATE.toggles[(c.env, c.label, c.run)] = self.rec
        return self.rec


@pytest.fixture
def fresh_game(request, case, session_mgr, opts):
    """Opt-in PRIVATE launch (function scope) for tests that change game state, e.g. the F12 toggle."""
    assert os.path.isfile(case.app), "AppImage not found: %s" % case.app
    fg = FreshGame(request, case, session_mgr, opts)
    try:
        yield fg
    finally:
        fg.game.stop()


@pytest.fixture
def app(request, case, session_mgr):
    """Opt-in PRIVATE launch for scenario tests (oolite_ui_test_framework/app.py): the game is started and returned at once, the test waits for the screens
    it cares about. Skips (NOT MEASURABLE) where window contents cannot be grabbed."""
    from . import app as appmod, ocr as ocrmod
    assert os.path.isfile(case.app), "AppImage not found: %s" % case.app
    s = session_mgr.get()
    _require_preconditions(request, s)
    preconditions.require("screenshot_support", preconditions.screenshot_support(s))
    if getattr(s.backend, "grab", None) is None: pytest.skip("NOT MEASURABLE: no screenshot support in this environment")
    _only_this_game()
    game = _game(request.config, case, s, request.node.originalname).start()
    try:
        yield appmod.App(s, game, request.config.getoption("--ui-shots"), "%s-%s-run%d" % (case.env, case.label, case.run), ocr=ocrmod.make_ocr())
    finally:
        game.stop()


# ---------------------------------------------------------------- outcomes -> raw file
def _reason(report):
    lr = report.longrepr
    if isinstance(lr, tuple): return str(lr[2]).replace("Skipped: ", "", 1)
    return str(lr).strip().splitlines()[-1][:200] if lr else ""


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    out = yield
    rep = out.get_result(); cs = getattr(item, "callspec", None)
    case = cs.params.get("case") if cs else None
    if case is None: return
    key = (case.env, case.label, case.run); name = item.originalname
    t = STATE.timing.setdefault(key + (name,), [call.start, 0.0]); t[1] += call.duration
    if rep.when == "call" or (rep.when == "setup" and rep.outcome == "skipped"):
        STATE.outcomes[key][name] = (rep.outcome, _reason(rep) if rep.outcome != "passed" else "")
    elif rep.when == "setup" and rep.outcome == "failed" and _reason(rep).startswith("PRECONDITION"):
        STATE.outcomes[key][name] = ("failed", _reason(rep))
    elif rep.when == "setup" and rep.outcome == "failed":
        STATE.hard.append((case.env, STATE.screen, case.label, _reason(rep) or "setup failed"))


def pytest_sessionfinish(session, exitstatus):
    path = session.config.getoption("--ui-raw")
    if not path: return
    lines = [raw_results.format_kv("WMVER", wm=k, version=v) for k, v in STATE.wmver.items()]
    for key in sorted(set(STATE.launches) | set(STATE.toggles) | set(STATE.outcomes), key=lambda k: (k[1], k[2])):
        if key in STATE.launches or key in STATE.toggles:
            rec = dict(STATE.launches.get(key) or STATE.toggles[key])
            if key in STATE.toggles: rec.update({k: v for k, v in STATE.toggles[key].items() if k.startswith("t_")})
            lines.append(raw_results.format_result(pass_fail.apply_outcomes(rec, STATE.outcomes.get(key, {}))))
        else:   # only `app` tests ran for this case: a RESULT line with just their criteria, so the report counts them
            rec = dict(wm=key[0], build=key[1], screen=STATE.screen, run=key[2], exited=None, dx=None, dy=None)
            lines.append(raw_results.format_result(pass_fail.apply_outcomes(rec, STATE.outcomes[key])))
        for test, (o, why) in sorted(STATE.outcomes.get(key, {}).items()):
            start, secs = STATE.timing.get(key + (test,), (None, None))
            lines.append("TEST wm=%s build=%s run=%d test=%s outcome=%s start=%s secs=%s reason=%s" % (key[0], key[1], key[2], test, o,
                         raw_results.stamp(start) if start else "NA", "NA" if secs is None else round(secs, 1), why.replace("\n", " ")))
    for env, build, run, text in STATE.warnings: lines.append("WARN wm=%s build=%s run=%d text=%s" % (env, build, run, text))
    for env, screen, build, why in STATE.hard: lines.append("HARD wm=%s screen=%s build=%s reason=%s" % (env, screen, build, why.replace("\n", " ")[:300]))
    with open(path, "a") as f: f.write("\n".join(lines) + "\n")


def pytest_terminal_summary(terminalreporter):
    """k6-style checks: pass rate per environment x build x test."""
    rates = collections.defaultdict(lambda: [0, 0, 0])
    for (env, build, run), d in STATE.outcomes.items():
        for test, (o, _) in d.items():
            r = rates[(env, build, test)]; r[0 if o == "passed" else 1 if o == "failed" else 2] += 1
    if not rates: return
    clean = collections.defaultdict(lambda: [0, 0])
    for (env, build, run), d in STATE.outcomes.items():
        o = [x[0] for x in d.values() if x[0] != "skipped"]
        if o: c = clean[(env, build)]; c[1] += 1; c[0] += all(x == "passed" for x in o)
    terminalreporter.section("uitest checks")
    for (env, build), (p, n) in sorted(clean.items()):
        terminalreporter.write_line("%-34s %-12s %-26s %d/%d%s" % (env, build, "RUNS WITH ALL TESTS PASSING", p, n, "   OK" if p == n else ""))
    for (env, build, test), (p, f, s) in sorted(rates.items()):
        terminalreporter.write_line("%-34s %-12s %-26s %s passed, %d failed, %d skipped%s" % (env, build, test, p, f, s, "" if f or not p or s else "   OK"))
