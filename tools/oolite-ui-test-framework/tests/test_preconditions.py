"""preconditions: each check's verdict and reason, with fakes (no compositor or X server needed)."""
import subprocess
import types

import pytest

from oolite_ui_test_framework import preconditions as pre


def env(**kw):
    d = dict(name="kwin-xwayland", kind="wayland", session="XWayland", keys="fakeinput", keys_na=False, headed=False, devices=[])
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
    assert "uitest-wlrinput is not installed" in pre.input_tool(env(keys="virtual"), which=lambda t: None)   # sway native (#44)


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


def test_key_repeat_off_on_native_wayland_reads_the_advertised_rate():
    native = lambda **kw: types.SimpleNamespace(backend=None, env=env(name="kwin-native", session="Wayland native", **kw))
    info = lambda out, code=0: (lambda *a, **k: types.SimpleNamespace(returncode=code, stdout=out))
    on = "\tcapabilities: keyboard\n\tkeyboard repeat rate: 25\n\tkeyboard repeat delay: 600\n"
    assert "advertises key repeat (25/s)" in pre.key_repeat_off(native(), run=info(on))
    assert pre.key_repeat_off(native(), run=info("\tcapabilities: keyboard\n")) is None          # KeyRepeat=nothing: no rate sent
    assert pre.key_repeat_off(native(), run=info("\tkeyboard repeat rate: 0\n")) is None
    assert pre.key_repeat_off(native(), run=info(on, code=1)) is None                              # cannot tell: no verdict
    assert pre.key_repeat_off(native(keys="xtest"), run=info(on)) is None                          # keys cannot reach the game anyway


def test_screenshot_support_only_where_an_x_session_should_grab():
    assert pre.screenshot_support(session()) is None
    assert "python-xlib missing" in pre.screenshot_support(session(grab=False))
    assert pre.screenshot_support(types.SimpleNamespace(backend=None, env=env())) is None


def test_render_device_for_headed_and_declared_devices():
    assert pre.render_device(env(), exists=lambda p: False) is None
    assert "/dev/dri is missing" in pre.render_device(env(headed=True), exists=lambda p: False)
    assert "modprobe udmabuf" in pre.render_device(env(devices=["/dev/udmabuf"]), exists=lambda p: False)
    assert pre.render_device(env(devices=["/dev/udmabuf"]), exists=lambda p: True) is None


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


def test_window_size_as_requested():
    assert pre.window_size_as_requested((1280, 720), (1280, 720)) is None
    assert pre.window_size_as_requested((1280, 720), (1281, 719)) is None
    assert "1280x720 window but the window manager made it 3836x1053" in pre.window_size_as_requested((1280, 720), (3836, 1053))
    assert pre.window_size_as_requested(None, (3836, 1053)) is None and pre.window_size_as_requested((1280, 720), None) is None


def test_point_on_screen():
    assert pre.point_on_screen(642, 681, (0, 0, 1280, 720)) is None
    assert "off the 1280x720 screen" in pre.point_on_screen(642, 740, (0, 0, 1280, 720))
    assert pre.point_on_screen(1100, 10, (1024, 0, 1024, 768)) is None                # second head


def test_window_size_for_fits_the_screen_or_is_deliberately_larger():
    from oolite_ui_test_framework import scenarios as sc
    assert sc.window_size_for((0, 0, 1920, 1080)) == (1280, 720)
    assert sc.window_size_for((0, 0, 1024, 768)) == (800, 600)                        # 1280x720 does not fit
    assert sc.window_size_for((0, 0, 1280, 720)) == (800, 600)                        # fits only without a frame
    assert sc.window_size_for((1024, 0, 1024, 768), oversize=True) == (1280, 1024)
    assert sc.window_size_for(None) == (1280, 720)


def test_set_window_size_rewrites_the_saved_size_and_keeps_the_rest(tmp_path):
    from oolite_ui_test_framework import scenarios as sc
    gd = tmp_path / "GameData"; gd.mkdir()
    (gd / "oolite.plist").write_text('{\n    fullscreen = 0;\n    "volume_control" = "0.5";\n    "window_height" = 720;\n    "window_width" = 1280;\n}')
    sc.set_window_size(str(tmp_path), (800, 600))
    t = (gd / "oolite.plist").read_text()
    assert '"window_width" = 800;' in t and '"window_height" = 600;' in t and "fullscreen = 0;" in t and "1280" not in t
    fresh = tmp_path / "fresh"; fresh.mkdir()
    sc.set_window_size(str(fresh), (800, 600))                                          # no plist yet: one is written
    t = (fresh / "GameData" / "oolite.plist").read_text()
    assert t.strip().startswith("{") and t.strip().endswith("}") and '"window_width" = 800;' in t


def test_the_wlroots_injector_is_checked_like_fake_input_without_the_kwin_hint():
    done = lambda rc, err="": (lambda *a, **kw: subprocess.CompletedProcess(a, rc, "", err))
    why = pre.fake_input_offered(env(keys="virtual"), run=done(3, "missing zwp_virtual_keyboard_manager_v1"))
    assert why == "missing zwp_virtual_keyboard_manager_v1"
    assert pre.fake_input_offered(env(keys="xtest"), run=done(3)) is None
