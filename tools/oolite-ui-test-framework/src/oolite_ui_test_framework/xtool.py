"""xtool: the measuring tool that runs INSIDE the helper container (python-xlib / X tools) against the host's X display.
Used by host mode so the game itself runs on the host. Usage: python3 -m oolite_ui_test_framework.xtool observe | monitors | wmname | key KEY [WINDOW]"""
import json
import sys

from . import window_probes


def observe(backend):
    o = window_probes.X11Probe(backend).observe()
    return None if o is None else {"win": o.win, "framed": o.framed, "focused": o.focused, "outer": o.outer, "client": o.client}


def main(argv=None):
    a = sys.argv[1:] if argv is None else argv
    b = window_probes.x_backend(None)
    if a[:1] == ["observe"]: print(json.dumps(observe(b)))
    elif a[:1] == ["monitors"]: print(json.dumps(b.monitors()))
    elif a[:1] == ["wmname"]: print(b.wm_name())
    elif a[:1] == ["key"] and len(a) >= 2: b.send_key(a[1], int(a[2]) if len(a) > 2 else None)
    elif a[:1] == ["keydown"] and len(a) == 2: b.key_down(a[1])
    elif a[:1] == ["keyup"] and len(a) == 2: b.key_up(a[1])
    else: print("usage: xtool observe|monitors|wmname|key KEY [WINDOW]|keydown KEY|keyup KEY", file=sys.stderr); return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
