"""The game's own logs (Latest.log, and out.log for what it printed), read in one place.

What they are used for, and what not:
  - evidence that an input ARRIVED: key presses, with key logging turned on by scenarios.add_key_logging (Oolite's own
    input.keyMapping.keyPress log class, no game change). Used to explain a failure ("the game logged 0 key presses") and to decide
    what the harness does next (send the fallback F12 only if the game never saw the first).
  - what the game ASKED for: the window size it requested, and GL errors it reported.
  - never the verdict on what the player sees. Whether the window is framed, focused, centred, full screen or showing the menu is judged
    from the window manager and the screenshot: in #773 the game logged nothing wrong while it had no title bar and no focus.
The game writes Latest.log about every 2 s, so a line can lag the event by that much."""
import os

SCANCODE = {"F12": 69, "Down": 81, "Up": 82, "Return": 40, "Escape": 41}   # SDL scancodes, as the game logs them


def texts(game, names=("Latest.log",)):
    """[(file name, text)] of the game's logs in its run folder, [] without one."""
    d = getattr(game, "dir", None); out = []
    if not d: return out
    for root, _, files in os.walk(d):
        for f in files:
            if f in names:
                try: out.append((f, open(os.path.join(root, f), errors="replace").read()))
                except OSError: pass
    return out


def keydowns(game, key=None):
    """Key presses the game has logged so far (all, or only `key`, a name from SCANCODE), None without a game log."""
    t = [x for n, x in texts(game) if n == "Latest.log"]
    if not t: return None
    want = "Keydown scancode = %d," % SCANCODE[key] if key else "Keydown scancode"
    return sum(want in line for line in t[0].splitlines())
