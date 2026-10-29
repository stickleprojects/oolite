"""Preconditions: what a test relies on from the environment rather than the game. When one does not hold the test fails as
"PRECONDITION <name>: <what was expected, what was found>", never with its own (misleading) assertion. Each check returns None if the
precondition holds, else the reason; checks that do not apply in an environment return None. Each was learnt the hard way:

  input_tool          the image lacks uitest-fakeinput / uitest-wlrinput / xdotool (a failed image build left every Wayland env without it, #29)
  fake_input_offered  KWin started without KWIN_WAYLAND_NO_PERMISSION_CHECKS=1 offers no fake-input, so keys and clicks go nowhere (#30)
  key_repeat_off      X / XWayland key repeat turns one held key into many presses (F12 toggled about 10 times); on native Wayland
                      the game repeats keys itself at the rate the compositor advertises (KWin: kcminputrc KeyRepeat), which
                      scrolled the title menu past the row the keys test was waiting for
  screenshot_support  an X session without python-xlib cannot grab the window, which used to look like "no screenshot support"
  render_device       KWin needs a render device: /dev/dri for headed kwin, the `devices` of an environment (headless kwin: /dev/udmabuf,
                      no GPU needed). Without one KWin crashes on every screenshot (KDE 527906, WONTFIX: unsupported configuration)
  window_fits_screen  the game asks for a window larger than the screen; the WM fits or maximises it, which changes F12 and clicks (#10)
  point_on_screen     a click target outside the visible screen (native kwin showed the game taller than the output)
  window_size_as_requested  the window manager gave the window another size than the game asked for (sway tiling stretched it to the
                      output): the game still maps the pointer with the size it asked for, so clicks select the wrong rows (#42)
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
    tool = fakeinput.BINARIES.get(env.keys, "xdotool")
    return None if which(tool) else "%s is not installed in this image (needed to send keys and clicks in %s)" % (tool, env.name)


def fake_input_offered(env, run=subprocess.run):
    """Asks the injector to do nothing: it exits 3 if the compositor does not offer its protocol (uitest-fakeinput: KWin's
    org_kde_kwin_fake_input; uitest-wlrinput: the virtual-keyboard and virtual-pointer managers)."""
    tool = fakeinput.BINARIES.get(env.keys)
    if tool is None: return None
    try: p = run([tool, "sleep", "0"], capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired) as e: return "could not run %s: %s" % (tool, e)
    if p.returncode == 0: return None
    why = (p.stderr or p.stdout).strip() or "exit %d" % p.returncode
    if env.keys == "fakeinput": why += " (KWin must be started with KWIN_WAYLAND_NO_PERMISSION_CHECKS=1)"
    return why


def key_repeat_off(session, run=subprocess.run):
    """X11 and XWayland: the X server's auto-repeat, which the session switches off. Native Wayland where keys reach the game (fake-input):
    the repeat rate the compositor advertises, read with wayland-info (no "keyboard repeat rate" line, or 0, = off). None where it cannot be read."""
    e = session.env
    if session.backend is not None and hasattr(session.backend, "autorepeat_on"):
        on = session.backend.autorepeat_on()
        return "X key repeat is on, so a held key reaches the game as many presses" if on else None
    if e.kind != "wayland" or e.session != "Wayland native" or e.keys not in fakeinput.BINARIES: return None
    try: p = run(["wayland-info"], capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired): return None
    m = re.search(r"keyboard repeat rate: (\d+)", p.stdout) if p.returncode == 0 else None
    if p.returncode != 0 or not m or int(m[1]) == 0: return None
    return ("the compositor advertises key repeat (%s/s), so the game repeats a held key itself (KWin: KeyRepeat=nothing in "
            "~/.config/kcminputrc; sway: repeat_rate 0 for type:keyboard; see environments.toml)" % m[1])


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


def window_size_as_requested(requested, size, tol=2):
    """requested: (w, h) from the game's log; size: (w, h) of the game window as drawn (its client area)."""
    if not requested or not size: return None
    (w, h), (cw, ch) = requested, size
    if abs(cw - w) <= tol and abs(ch - h) <= tol: return None
    return ("the game asked for a %dx%d window but the window manager made it %dx%d (a tiling layout?); the game still maps the pointer "
            "with the size it asked for, so clicks land on the wrong rows (#42; sway: float the window, see environments.toml)" % (w, h, cw, ch))


def point_on_screen(x, y, screen):
    """(x, y) in screen coordinates; screen: (x, y, w, h)."""
    if not screen: return None
    sx, sy, sw, sh = screen
    if sx <= x < sx + sw and sy <= y < sy + sh: return None
    return "the point to click (%d, %d) is off the %dx%d screen (the game window does not fit on it)" % (x, y, sw, sh)
