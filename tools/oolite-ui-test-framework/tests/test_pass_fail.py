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
