"""pass_fail: the (outcome, reason) a game test gets from a launch record. Records are plain dicts written by hand, as the plugin
would record them; old records with missing fields must give skipped or passed, never failed."""
from oolite_ui_test_framework import pass_fail


def test_check_renders_outcomes():
    assert pass_fail.check_renders({"render": "ok", "gl_errors": 0, "exited": 0}) == ("passed", "")
    assert pass_fail.check_renders({"render": "black", "gl_errors": 0, "exited": 0, "render_colours": 1, "render_std": 0})[0] == "failed"
    assert pass_fail.check_renders({"render": "ok", "gl_errors": 2, "gl_first": "out.log: GL error"})[0] == "failed"
    assert pass_fail.check_renders({"render": "NA", "gl_errors": 0, "exited": 0})[0] == "skipped"


def test_check_renders_fails_a_frozen_window_but_ignores_missing_data():
    frozen = {"render": "ok", "gl_errors": 0, "exited": 0, "render_changed": 0.0, "render_gap": 3}
    assert pass_fail.check_renders(frozen)[0] == "failed" and "frozen" in pass_fail.check_renders(frozen)[1]
    assert pass_fail.check_renders({"render": "ok", "gl_errors": 0, "exited": 0, "render_changed": 0.31})[0] == "passed"
    assert pass_fail.check_renders({"render": "ok", "gl_errors": 0, "exited": 0})[0] == "passed"      # old raw files have no render_changed


def test_responds_to_keys():
    assert pass_fail.check_responds_to_keys({"input_changed": 0.2})[0] == pass_fail.PASSED
    assert pass_fail.check_responds_to_keys({"input_changed": 0.0})[0] == pass_fail.FAILED
    assert pass_fail.check_responds_to_keys({})[0] == pass_fail.SKIPPED
    assert pass_fail.check_responds_to_keys({"exited": 1, "input_changed": 0.3})[0] == pass_fail.FAILED
