"""The pytest layer, exercised with pytester: the real game tests (app/ and window/) against FAKE launch fixtures (no display, no game)."""
import os

import pytest

from oolite_ui_test_framework import pass_fail

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GAME_TESTS = os.path.join(os.path.dirname(os.path.dirname(ROOT)), "tests", "ui")

CONFTEST = '''
import sys, types, os
import pytest
sys.path.insert(0, %r + '/src')
pytest_plugins = ["oolite_ui_test_framework.plugin"]
LOG = %r

def _rec(case, **kw):
    r = dict(wm=case.env, build=case.label, run=case.run, screen="3840x1080", frame=1, focus=1, exited=0, dx=0, dy=0, centred=1, splash_dx=0, splash_dy=0, tol=40,
             outer="1280x720+1280+180", mon="3840x1080+0+0", splash_outer="768x768+1536+156")
    if case.label == "new": r.update(frame=0)                    # the candidate has no frame
    if case.label == "na": r.update(focus="NA")                  # focus cannot be observed
    r.update(kw); return r

@pytest.fixture(scope="module")
def launched_game(case):
    open(LOG, "a").write("launch %%s %%s\\n" %% (case.label, case.run))
    from oolite_ui_test_framework import geometry, plugin
    rec = geometry.apply(_rec(case)); plugin.STATE.launches[(case.env, case.label, case.run)] = rec
    return rec

@pytest.fixture(scope="module")
def env_session(case):
    return types.SimpleNamespace(primary=(0, 0, 3840, 1080), env=types.SimpleNamespace(kind="x11"))

class Fresh:
    def __init__(self, case): self.case = case
    def toggle(self):
        open(LOG, "a").write("fresh %%s %%s\\n" %% (self.case.label, self.case.run))
        from oolite_ui_test_framework import geometry, plugin
        rec = geometry.apply(_rec(self.case, t_ok=1, t_method="key", t_frame=1, t_focus=1, t_dx=0, t_dy=0, t_centred=1))
        plugin.STATE.toggles[(self.case.env, self.case.label, self.case.run)] = rec
        return rec

@pytest.fixture
def fresh_game(case): return Fresh(case)
'''


@pytest.fixture
def project(pytester, tmp_path):
    log = str(tmp_path / "launches.log")
    pytester.makeconftest(CONFTEST % (ROOT, log))
    src = "".join(open(os.path.join(GAME_TESTS, d, f)).read() + "\n" for d, f in (("app", "test_launch.py"), ("window", "test_window_manager.py")))
    pytester.makepyfile(test_gamecopy=src)
    app = tmp_path / "Oolite.AppImage"; app.write_text("x")
    args = ["--ui-env", "marco", "--ui-runs", "2", "--ui-app", "base=%s" % app, "--ui-app", "new=%s" % app, "--ui-app", "na=%s" % app,
            "--ui-raw", str(tmp_path / "out.raw"), "--junitxml", str(tmp_path / "j.xml"), "-p", "no:randomly"]
    return pytester, args, tmp_path


def test_ids_outcomes_and_skip_reasons(project):
    pt, args, tmp = project
    r = pt.runpytest("-v", "-rs", *args)
    out = r.stdout.str()
    assert "test_gets_focus[marco-x11-base-run1] PASSED" in out
    assert "test_has_frame[marco-x11-new-run2] FAILED" in out
    assert "test_gets_focus[marco-x11-na-run1] SKIPPED" in out and "SKIPPED [2] " in out and "NOT MEASURABLE: keyboard focus cannot be observed" in out
    assert "test_f12_toggle[marco-x11-base-run1] SKIPPED" in out and "NOT TESTED: toggle not run in this data" in out        # no --ui-toggle


def test_one_launch_per_case_and_once_per_build_checks(project):
    pt, args, tmp = project
    r = pt.runpytest("-v", *args)
    launches = open(tmp / "launches.log").read().splitlines()
    assert len(launches) == 6 and len(set(launches)) == 6            # 3 builds x 2 runs: shared by 5 read-only tests each
    out = r.stdout.str()
    assert "test_environment_started[marco-x11-base-run1]" in out and "test_environment_started[marco-x11-base-run2]" not in out


def test_toggle_gets_its_own_launch(project):
    pt, args, tmp = project
    pt.runpytest("--ui-toggle", *args)
    log = open(tmp / "launches.log").read().splitlines()
    assert sum(1 for l in log if l.startswith("fresh")) == 6 and sum(1 for l in log if l.startswith("launch")) == 6


def test_raw_file_is_result_compatible_and_has_test_lines(project):
    pt, args, tmp = project
    pt.runpytest("--ui-toggle", *args)
    raw = open(tmp / "out.raw").read().splitlines()
    res = [l for l in raw if l.startswith("RESULT")]
    assert len(res) == 6 and any("build=new run=1 screen=3840x1080 frame=0" in l or ("build=new" in l and "frame=0" in l) for l in res)
    na = [l for l in res if "build=na" in l][0]
    assert "focus=NA" in na and "t_ok=1" in na
    tests = [l for l in raw if l.startswith("TEST")]
    assert any("test=test_gets_focus outcome=skipped reason=NOT MEASURABLE" in l for l in tests)
    assert any("test=test_has_frame outcome=failed" in l and "build=new" in l for l in tests)
    assert os.path.exists(tmp / "j.xml")


def test_app_only_runs_still_get_a_result_line(project):
    """A run of only `app` tests (no shared launch) still writes RESULT lines, with the title-menu outcome as the renders criterion."""
    pt, args, tmp = project
    pt.makepyfile(test_gamecopy="def test_title_menu_is_displayed(case):\n    assert case.label != 'new'\n")
    pt.runpytest(*args)
    res = [l for l in open(tmp / "out.raw").read().splitlines() if l.startswith("RESULT")]
    assert len(res) == 6 and all("exited=NA" in l for l in res)
    assert all(("renders=0" in l) == ("build=new" in l) for l in res)


@pytest.mark.parametrize("sel,name,count", [(["-m", "family_marco"], "test_has_frame", 6), (["-m", "family_kwin"], "test_has_frame", 0),
                                             (["-m", "session_x11"], "test_has_frame", 6), (["-k", "test_gets_focus and new"], "test_gets_focus", 2)])
def test_markers_and_k_select(project, sel, name, count):
    pt, args, tmp = project
    assert pt.runpytest(*sel, "--collect-only", "-q", *args).stdout.str().count(name + "[") == count


def test_report_from_the_raw_file(project):
    from oolite_ui_test_framework import report
    pt, args, tmp = project
    pt.runpytest("--ui-toggle", *args)
    md = tmp / "r.md"
    report.main([str(tmp / "out.raw"), str(md), "--control", "base", "--candidates", "new", "--minruns", "2", "--registry", os.path.join(ROOT, "environments.toml")])
    text = md.read_text()
    assert "has_frame" in text and "gets_focus" in text and "game_window_centred" in text and "f12_toggle" in text   # columns are the test names


def test_case_ids():
    assert pass_fail.case_id("marco", "opt1", 3, "X11") == "marco-x11-opt1-run3"
    assert pass_fail.case_id("kwin-xwayland", "base", 1, "XWayland") == "kwin-xwayland-base-run1"
    assert pass_fail.case_id("mutter-native", "base", 1, "Wayland native") == "mutter-native-base-run1"


def test_outcome_checks_map_to_skip_fail_pass():
    ok = {"frame": "1", "exited": "0"}
    assert pass_fail.check_frame(ok)[0] == "passed" and pass_fail.check_frame({"frame": "0", "exited": "0"})[0] == "failed"
    assert pass_fail.check_frame({"frame": "NA", "exited": "0"}) == ("skipped", "NOT MEASURABLE: the window frame cannot be observed in this environment")
    assert pass_fail.check_frame({"frame": "0", "exited": "1"})[0] == "failed"
    assert pass_fail.check_f12_toggle({"t_ok": "0"})[0] == "failed" and pass_fail.check_f12_toggle({})[0] == "skipped"
    assert pass_fail.check_f12_toggle({"t_ok": "1", "t_frame": "1", "t_focus": "0", "t_centred": "1"})[1].endswith("focus")


def test_a_black_first_screenshot_is_looked_at_again(monkeypatch, tmp_path):
    """KWin on XWayland can give an all-black window until the first frame is presented: that must not count as 'renders = black'."""
    import types
    from oolite_ui_test_framework import plugin
    black = (64, 64, bytes(64 * 64 * 3))
    lit = (64, 64, bytes((i * 37) % 256 for i in range(64 * 64 * 3)))
    shots = iter([black, black, lit, lit, lit])
    backend = types.SimpleNamespace(grab=lambda w: next(shots))
    session = types.SimpleNamespace(backend=backend, window_id=lambda: 5)
    cfg = types.SimpleNamespace(getoption=lambda name: "")
    monkeypatch.setattr(plugin.time, "sleep", lambda s: None)
    out = plugin._render_fields(session, types.SimpleNamespace(dir=str(tmp_path)), {}, cfg, types.SimpleNamespace(env="e", label="b", run=1))
    assert out["render"] == "ok"


def test_a_window_that_stays_black_is_still_reported_black(monkeypatch, tmp_path):
    import types
    from oolite_ui_test_framework import plugin
    black = (64, 64, bytes(64 * 64 * 3))
    clock = iter(range(0, 1000, 3))
    monkeypatch.setattr(plugin.time, "sleep", lambda s: None)
    monkeypatch.setattr(plugin.time, "monotonic", lambda: next(clock))
    session = types.SimpleNamespace(backend=types.SimpleNamespace(grab=lambda w: black), window_id=lambda: 5)
    out = plugin._render_fields(session, types.SimpleNamespace(dir=str(tmp_path)), {}, types.SimpleNamespace(getoption=lambda n: ""), types.SimpleNamespace(env="e", label="b", run=1))
    assert out["render"] == "black"


def test_key_driven_tests_run_on_kwin_xwayland_through_fake_input(project):
    pt, args, tmp = project
    args = [a if a != "marco" else "kwin-xwayland" for a in args] + ["--ui-toggle"]
    out = pt.runpytest("-v", "-rs", *args).stdout.str()
    assert "test_f12_toggle[kwin-xwayland" in out and "NOT MEASURABLE: injected keys" not in out
