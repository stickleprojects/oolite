"""Keys and the mouse for compositors where XTEST (xdotool) events never reach clients: one process, fed commands on stdin, kept running
because the compositor releases whatever a client still holds when it disconnects. Two injectors, built into the wayland image, with the
same commands (`keys` in environments.toml picks one):
  fakeinput  uitest-fakeinput, KWin's fake-input protocol (docker/fakeinput.c): headless KWin
  virtual    uitest-wlrinput, the standard virtual-keyboard and virtual-pointer protocols (docker/wlrinput.c): sway (native Wayland)"""
import subprocess
import time

BINARY = "uitest-fakeinput"
BINARIES = {"fakeinput": BINARY, "virtual": "uitest-wlrinput"}   # keys mode -> injector
BTN_LEFT = 0x110

# xdotool key names -> Linux evdev codes
CODES = {"Escape": 1, "Return": 28, "space": 57, "Up": 103, "Left": 105, "Right": 106, "Down": 108, "Tab": 15, "BackSpace": 14,
         **{"F%d" % i: 58 + i for i in range(1, 11)}, "F11": 87, "F12": 88,
         **{c: n for c, n in zip("1234567890", range(2, 12))}}

_proc = None
_binary = BINARY


def select(mode):
    """Use the injector for `keys` mode `mode` (a key of BINARIES) from the next command on."""
    global _binary
    if BINARIES[mode] != _binary: close(); _binary = BINARIES[mode]


def code(key):
    if key not in CODES: raise ValueError("fake input: no evdev code for key %r" % key)
    return CODES[key]


def send(command, popen=subprocess.Popen):
    """One command line to the running injector (started on first use); returns once the compositor has it."""
    global _proc
    if _proc is None or _proc.poll() is not None:
        _proc = popen([_binary], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, start_new_session=True)
    _proc.stdin.write(command + "\n"); _proc.stdin.flush()
    reply = _proc.stdout.readline().strip()
    if reply != "ok": raise RuntimeError("%s: %r -> %r" % (_binary, command, reply or "exited"))


def close():
    """Stop the process; KWin releases anything it still holds."""
    global _proc
    if _proc is not None:
        try: _proc.stdin.close(); _proc.wait(timeout=2)
        except (OSError, subprocess.TimeoutExpired): _proc.kill()
        _proc = None


def key_down(key, **kw):
    send("press %d" % code(key), **kw)


def key_up(key, **kw):
    send("release %d" % code(key), **kw)


def tap(key, hold=0.15, sleep=time.sleep, **kw):
    key_down(key, **kw); sleep(hold); key_up(key, **kw)


def mouse_move(x, y, **kw):
    """Pointer to (x, y) in compositor output coordinates."""
    send("move %d %d" % (x, y), **kw)


def mouse_down(**kw):
    send("down %d" % BTN_LEFT, **kw)


def mouse_up(**kw):
    send("up %d" % BTN_LEFT, **kw)
