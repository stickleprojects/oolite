"""preconditions: each check's verdict and reason, with fakes (no compositor or X server needed)."""
import subprocess
import types

import pytest

from oolite_ui_test_framework import preconditions as pre


def env(**kw):
    d = dict(name="kwin-xwayland", kind="wayland", keys="fakeinput", keys_na=False, headed=False)
    d.update(kw); return types.SimpleNamespace(**d)


def test_require_fails_as_a_named_precondition():
    pre.require("x", None)
    with pytest.raises(pytest.fail.Exception, match=r"^PRECONDITION input_tool: missing"):
        pre.require("input_tool", "missing")
    with pytest.raises(pre.PreconditionFailed, match="PRECONDITION point_on_screen: off"):
        pre.check("point_on_screen", "off")


def test_input_tool_names_the_tool_this_environment_needs():
    assert pre.input_tool(env(), which=lambda t: "/usr/local/bin/" + t) is None
    assert "uitest-fakeinput is not installed" in pre.input_tool(env(), which=lambda t: None)
    assert "xdotool is not installed" in pre.input_tool(env(keys="xtest"), which=lambda t: None)
    assert pre.input_tool(env(keys_na=True), which=lambda t: None) is None          # no input by design: NOT MEASURABLE, not this


def test_fake_input_offered_reports_the_missing_global_and_the_fix():
    done = lambda rc, err="": (lambda *a, **kw: subprocess.CompletedProcess(a, rc, "", err))
    assert pre.fake_input_offered(env(), run=done(0)) is None
    why = pre.fake_input_offered(env(), run=done(3, "no org_kde_kwin_fake_input global\n"))
    assert "no org_kde_kwin_fake_input global" in why and "KWIN_WAYLAND_NO_PERMISSION_CHECKS=1" in why
    assert pre.fake_input_offered(env(keys="xtest"), run=done(3)) is None


def session(on=None, grab=True, kind="x11"):
    b = types.SimpleNamespace(autorepeat_on=lambda: on)
    if grab: b.grab = lambda w: None
    return types.SimpleNamespace(backend=b, env=env(kind=kind))


def test_key_repeat_off():
    assert pre.key_repeat_off(session(on=False)) is None
    assert "key repeat is on" in pre.key_repeat_off(session(on=True))
    assert pre.key_repeat_off(session(on=None)) is None                                # cannot tell: no verdict
    assert pre.key_repeat_off(types.SimpleNamespace(backend=None, env=env())) is None  # native Wayland: no X


def test_screenshot_support_only_where_an_x_session_should_grab():
    assert pre.screenshot_support(session()) is None
    assert "python-xlib missing" in pre.screenshot_support(session(grab=False))
    assert pre.screenshot_support(types.SimpleNamespace(backend=None, env=env())) is None


def test_gpu_present_only_for_headed_environments():
    assert pre.gpu_present(env(), exists=lambda p: False) is None
    assert "/dev/dri is missing" in pre.gpu_present(env(headed=True), exists=lambda p: False)


def test_requested_window_comes_from_the_game_log():
    log = ("21:54:46 [display.initGL]: Requested a new surface of 1280 x 720, windowed.\n"
           "21:54:50 [display.initGL]: Requested a new surface of 1024 x 768, fullscreen.\n")
    assert pre.requested_window(log) == (1280, 720)
    assert pre.requested_window("nothing") is None


def test_window_fits_screen():
    assert pre.window_fits_screen((1280, 720), (0, 0, 1920, 1080)) is None
    why = pre.window_fits_screen((1280, 720), (0, 0, 1024, 768))
    assert "1280x720 window but the screen is 1024x768" in why
    assert pre.window_fits_screen(None, (0, 0, 1024, 768)) is None


def test_point_on_screen():
    assert pre.point_on_screen(642, 681, (0, 0, 1280, 720)) is None
    assert "off the 1280x720 screen" in pre.point_on_screen(642, 740, (0, 0, 1280, 720))
    assert pre.point_on_screen(1100, 10, (1024, 0, 1024, 768)) is None                # second head
