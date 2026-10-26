"""Keys for compositors where XTEST (xdotool) keys never reach clients, e.g. headless kwin: a `uitest-fakekey` process holds the key down
through KWin's fake-input protocol until it is stopped (docker/fakekey.c, built into the wayland image)."""
import os
import signal
import subprocess
import time

BINARY = "uitest-fakekey"
PIDS = "/tmp/uitest-fakekey-%d.pid"

# xdotool key names -> Linux evdev codes
CODES = {"Escape": 1, "Return": 28, "space": 57, "Up": 103, "Left": 105, "Right": 106, "Down": 108, "Tab": 15, "BackSpace": 14,
         **{"F%d" % i: 58 + i for i in range(1, 11)}, "F11": 87, "F12": 88,
         **{c: n for c, n in zip("1234567890", range(2, 12))}}


def code(key):
    if key not in CODES: raise ValueError("fake input: no evdev code for key %r" % key)
    return CODES[key]


def key_down(key, popen=subprocess.Popen, sleep=time.sleep):
    c = code(key)
    key_up(key)
    p = popen([BINARY, str(c)], stdout=subprocess.PIPE, start_new_session=True)
    with open(PIDS % c, "w") as f: f.write(str(p.pid))
    p.stdout.readline()                                   # "down": the press has been sent
    sleep(0.05)
    return p


def key_up(key, kill=os.kill):
    path = PIDS % code(key)
    try:
        pid = int(open(path).read()); os.remove(path)
        kill(pid, signal.SIGTERM)
    except (OSError, ValueError):
        pass


def tap(key, hold=0.15, sleep=time.sleep, **kw):
    key_down(key, **kw); sleep(hold); key_up(key)
