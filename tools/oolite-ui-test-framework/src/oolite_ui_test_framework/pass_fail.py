"""Test-level outcomes from a launch record. Pure functions: (outcome, reason) with outcome 'passed' | 'failed' | 'skipped'.
The game tests (the tests folder next to the framework) are one line each: they call one of these and enforce() the result with pytest."""
from . import geometry

PASSED, FAILED, SKIPPED = "passed", "failed", "skipped"


def _v(rec, k):
    v = rec.get(k)
    return None if v in (None, "NA", "") else str(v)


def _flag(rec, key, what):
    if _v(rec, "exited") == "1": return FAILED, "the game window was gone (game exited)"
    v = _v(rec, key)
    if v is None: return SKIPPED, "NOT MEASURABLE: %s cannot be observed in this environment" % what
    return (PASSED, "") if v == "1" else (FAILED, None)


def check_frame(rec):
    o, why = _flag(rec, "frame", "the window frame")
    return (o, why if why is not None else "no frame: the window's X parent is the root window")


def check_focus(rec):
    o, why = _flag(rec, "focus", "keyboard focus")
    return (o, why if why is not None else "the game window is not the active window (no focus)")


def check_window_centred(rec):
    if _v(rec, "exited") == "1": return FAILED, "the game window was gone (game exited)"
    c = _v(rec, "centred")
    if c is None: return SKIPPED, "NOT MEASURABLE: window position cannot be observed in this environment"
    if c == "1": return PASSED, ""
    return FAILED, "off centre by dx=%s dy=%s (tolerance %s px)" % (_v(rec, "dx"), _v(rec, "dy"), rec.get("tol", geometry.DEFAULT_TOL))


def check_splash_centred(rec):
    if _v(rec, "exited") == "1" and _v(rec, "splash_dx") is None: return FAILED, "the game window was gone (game exited)"
    c = _v(rec, "splash_centred")
    if c is None: return SKIPPED, "NOT MEASURABLE: the splash window was not observed"
    if c == "1": return PASSED, ""
    return FAILED, "splash off centre by dx=%s dy=%s (tolerance %s px)" % (_v(rec, "splash_dx"), _v(rec, "splash_dy"), rec.get("tol", geometry.DEFAULT_TOL))


def check_f12_toggle(rec):
    """windowed -> fullscreen -> windowed with F12: the window changed size, and is framed, focused and centred again."""
    if _v(rec, "t_ok") is None: return SKIPPED, "NOT TESTED: toggle not run in this data (no --ui-toggle)"
    if rec.get("t_ok") in (0, "0"): return FAILED, "F12 did not change the window size (%s)" % rec.get("t_method", "key")
    bad = [n for n, k in (("frame", "t_frame"), ("focus", "t_focus"), ("centred", "t_centred")) if _v(rec, k) == "0"]
    return (FAILED, "after the round trip the window lost: " + ", ".join(bad)) if bad else (PASSED, "")


TESTS = {"test_has_frame": check_frame, "test_gets_focus": check_focus, "test_splash_centred": check_splash_centred,
         "test_game_window_centred": check_window_centred, "test_f12_toggle": check_f12_toggle}


def case_id(env, run, session=""):
    """readable test id, e.g. 'marco-x11-run3' (the session slug is left out when the env name already ends with it)"""
    slug = {"wayland native": "native"}.get(session.lower(), session.lower().replace(" ", "-")) if session else ""
    parts = [env] + ([slug] if slug and not env.endswith(slug) else []) + ["run%d" % run]
    return "-".join(parts)


def apply_outcomes(rec, outcomes):
    """RESULT-compatible record from a launch record and the pytest outcomes {test: (outcome, reason)}: skipped = NA, failed = 0, passed = 1."""
    out = dict(rec)
    for test, key in (("test_has_frame", "frame"), ("test_gets_focus", "focus"), ("test_game_window_centred", "centred"), ("test_title_menu_is_displayed", "renders")):
        if test in outcomes:
            o = outcomes[test][0]; out[key] = 1 if o == PASSED else 0 if o == FAILED else None
    return out
