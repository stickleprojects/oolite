"""Preconditions: what a test relies on from the environment rather than the game. When one does not hold the test fails as
"PRECONDITION <name>: <what was expected, what was found>", never with its own (misleading) assertion. Each check returns None if the
precondition holds, else the reason; checks that do not apply in an environment return None. Each was learnt the hard way:

  input_tool          the image lacks uitest-fakeinput / xdotool (a failed image build left every Wayland env without it, #29)
  fake_input_offered  KWin started without KWIN_WAYLAND_NO_PERMISSION_CHECKS=1 offers no fake-input, so keys and clicks go nowhere (#30)
  key_repeat_off      X / XWayland key repeat turns one held key into many presses (F12 toggled about 10 times)
  screenshot_support  an X session without python-xlib cannot grab the window, which used to look like "no screenshot support"
  render_device       KWin needs a render device: /dev/dri for headed kwin, the `devices` of an environment (headless kwin: /dev/udmabuf,
                      no GPU needed). Without one KWin crashes on every screenshot (KDE 527906, WONTFIX: unsupported configuration)
  window_fits_screen  the game asks for a window larger than the screen; the WM fits or maximises it, which changes F12 and clicks (#10)
  point_on_screen     a click target outside the visible screen (native kwin showed the game taller than the output)
"""
import os
import re
import shutil
import subprocess

import pytest

from . import fakeinput

REQUESTED = re.compile(r"Requested a new surface of (\d+) x (\d+), windowed")


class PreconditionFailed(AssertionError):
    pass


def require(name, reason):
    """Fail as PRECONDITION <name> if `reason` (a check's result) is set."""
    if reason: pytest.fail("PRECONDITION %s: %s" % (name, reason), pytrace=False)


def check(name, reason):
    """Like require() but raises PreconditionFailed, for code outside a test (e.g. App.click_until)."""
    if reason: raise PreconditionFailed("PRECONDITION %s: %s" % (name, reason))


def input_tool(env, which=shutil.which):
    if env.keys_na or env.kind == "host": return None
    tool = fakeinput.BINARY if env.keys == "fakeinput" else "xdotool"
    return None if which(tool) else "%s is not installed in this image (needed to send keys and clicks in %s)" % (tool, env.name)


def fake_input_offered(env, run=subprocess.run):
    """Asks uitest-fakeinput to do nothing: it exits 3 if the compositor offers no org_kde_kwin_fake_input."""
    if env.keys != "fakeinput": return None
    try: p = run([fakeinput.BINARY, "sleep", "0"], capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired) as e: return "could not run %s: %s" % (fakeinput.BINARY, e)
    if p.returncode == 0: return None
    why = (p.stderr or p.stdout).strip() or "exit %d" % p.returncode
    return "%s (KWin must be started with KWIN_WAYLAND_NO_PERMISSION_CHECKS=1)" % why


def key_repeat_off(session):
    """Only where the session switched it off (X11 and XWayland); None where it cannot be read."""
    if session.backend is None or not hasattr(session.backend, "autorepeat_on"): return None
    on = session.backend.autorepeat_on()
    return "X key repeat is on, so a held key reaches the game as many presses" if on else None


def screenshot_support(session):
    """An X session can always grab the game window with python-xlib; without it the screenshot tests cannot run."""
    if session.backend is None: return None
    if getattr(session.backend, "grab", None) is None:
        return "this X session cannot grab the game window (python-xlib missing: the XTools backend has no grab)"
    return None


def render_device(env, exists=os.path.exists):
    need = (["/dev/dri"] if env.headed else []) + list(env.devices)
    missing = [d for d in need if not exists(d)]
    if not missing: return None
    hint = " (on the host: sudo modprobe udmabuf)" if "/dev/udmabuf" in missing else ""
    return "%s needs a render device but %s is missing%s" % (env.name, ", ".join(missing), hint)


def requested_window(log_text):
    """The first windowed size the game asked for, from its log: (w, h) or None."""
    m = REQUESTED.search(log_text or "")
    return (int(m[1]), int(m[2])) if m else None


def window_fits_screen(requested, screen):
    """requested: (w, h) from the game's log; screen: (x, y, w, h) of the monitor it opens on."""
    if not requested or not screen: return None
    (w, h), (sw, sh) = requested, screen[2:4]
    if w <= sw and h <= sh: return None
    return ("the game asks for a %dx%d window but the screen is %dx%d, so the window manager fits or maximises it "
            "(F12 and click results then depend on that)" % (w, h, sw, sh))


def point_on_screen(x, y, screen):
    """(x, y) in screen coordinates; screen: (x, y, w, h)."""
    if not screen: return None
    sx, sy, sw, sh = screen
    if sx <= x < sx + sw and sy <= y < sy + sh: return None
    return "the point to click (%d, %d) is off the %dx%d screen (the game window does not fit on it)" % (x, y, sw, sh)
