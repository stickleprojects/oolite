"""pass_fail: the (outcome, reason) a game test gets from a launch record. Records are plain dicts written by hand, as the plugin
would record them; old records with missing fields must give skipped or passed, never failed."""
from oolite_ui_test_framework import pass_fail




def test_saved_size():
    w = (1280, 720); c = pass_fail.check_saved_size
    assert c({"client": "1280x720+0+30", "outer": "1296x784+0+0"}, w)[0] == pass_fail.PASSED
    assert c({"client": "800x600+0+30"}, w) == (pass_fail.FAILED, "client area 800x600, saved size 1280x720")
    assert c({"outer": "1290x750+0+0"}, w)[0] == pass_fail.PASSED and c({"outer": "1920x1080+0+0"}, w)[0] == pass_fail.FAILED
    assert c({"requested_w": 800, "requested_h": 600, "client": "800x600+0+0"}, w) == (pass_fail.FAILED, "the game asked for 800x600, not the saved 1280x720")
    assert c({"outer": "NA"}, w)[0] == pass_fail.SKIPPED and c({"exited": 1}, w)[0] == pass_fail.FAILED


def test_f12_failure_says_how_it_was_judged_and_a_round_trip_must_end_windowed():
    from oolite_ui_test_framework.pass_fail import FAILED, PASSED
    assert pass_fail.check_f12_toggle({"t_ok": 0, "t_method": "key", "t_judged_by": "state"}) == (FAILED, "F12 did not put the window in full-screen state (key)")
    assert pass_fail.check_f12_toggle({"t_ok": 0, "t_method": "key"})[1] == "F12 did not change the window size (key)"
    assert pass_fail.check_f12_toggle({"t_ok": 1, "t_fs_after": 1}) == (FAILED, "the window was still full screen after the second F12")
    assert pass_fail.check_f12_toggle({"t_ok": 1, "t_fs_after": 0, "t_frame": 1, "t_focus": 1, "t_centred": 1})[0] == PASSED
