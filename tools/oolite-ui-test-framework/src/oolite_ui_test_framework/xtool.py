"""xtool: the measuring tool that runs INSIDE the helper container (python-xlib / X tools) against the host's X display.
Used by host mode so the game itself runs on the host. Usage: python3 -m oolite_ui_test_framework.xtool observe | monitors | wmname | key KEY [WINDOW] | mousemove WINDOW X Y | mousedown | mouseup
`serve` keeps one process (and one X connection) for a whole host run: it reads one JSON command list per line on stdin and answers each
with one JSON line {"r": result} or {"error": text}; a grab answer {"r": [w, h], "n": N} is followed by N bytes of RGB. A `docker exec`
per call took about 0.2 s, too slow for the tests that hold a key down while they look at the screen."""
import json
import sys

from . import window_probes


def observe(backend):
    o = window_probes.X11Probe(backend).observe()
    return None if o is None else {"win": o.win, "framed": o.framed, "focused": o.focused, "outer": o.outer, "client": o.client}


def call(b, cmd, args):
    """One command -> its JSON-able result (bytes for grab)."""
    if cmd == "observe": return observe(b)
    if cmd == "monitors": return b.monitors()
    if cmd == "wmname": return b.wm_name()
    if cmd == "find": return b.find_window()
    if cmd == "geom": return b.abs_geom(int(args[0]))
    if cmd == "key": return b.send_key(args[0], int(args[1]) if len(args) > 1 and args[1] else None)
    if cmd == "keydown": return b.key_down(args[0])
    if cmd == "keyup": return b.key_up(args[0])
    if cmd == "mousemove": return b.mouse_move(int(args[0]), int(args[1]), int(args[2]))
    if cmd == "mousedown": return b.mouse_down()
    if cmd == "mouseup": return b.mouse_up()
    if cmd == "repeat": return b.autorepeat_on()
    if cmd == "repeat_off": return b.autorepeat_off()
    if cmd == "repeat_on": return b.autorepeat_restore()
    if cmd == "grab": return b.grab(int(args[0])) if hasattr(b, "grab") else None
    raise ValueError("unknown command %r" % cmd)


def serve(b, inp, out):
    for line in inp:
        try:
            req = json.loads(line); r = call(b, req[0], req[1:])
            if req[0] == "grab" and r is not None:
                w, h, rgb = r
                out.write(json.dumps({"r": [w, h], "n": len(rgb)}).encode() + b"\n" + bytes(rgb))
            else:
                out.write(json.dumps({"r": r}).encode() + b"\n")
        except Exception as e:   # one bad command must not end the run's helper
            out.write(json.dumps({"error": "%s: %s" % (type(e).__name__, e)}).encode() + b"\n")
        out.flush()
    return 0


def main(argv=None):
    a = sys.argv[1:] if argv is None else argv
    b = window_probes.x_backend(None)
    if a[:1] == ["serve"]: return serve(b, sys.stdin, sys.stdout.buffer)
    if a[:1] == ["observe"]: print(json.dumps(observe(b)))
    elif a[:1] == ["monitors"]: print(json.dumps(b.monitors()))
    elif a[:1] == ["wmname"]: print(b.wm_name())
    elif a[:1] == ["key"] and len(a) >= 2: b.send_key(a[1], int(a[2]) if len(a) > 2 else None)
    elif a[:1] == ["keydown"] and len(a) == 2: b.key_down(a[1])
    elif a[:1] == ["keyup"] and len(a) == 2: b.key_up(a[1])
    elif a[:1] == ["mousemove"] and len(a) == 4: b.mouse_move(int(a[1]), int(a[2]), int(a[3]))
    elif a[:1] == ["mousedown"]: b.mouse_down()
    elif a[:1] == ["mouseup"]: b.mouse_up()
    else: print("usage: xtool serve|observe|monitors|wmname|key KEY [WINDOW]|keydown KEY|keyup KEY|mousemove WINDOW X Y|mousedown|mouseup", file=sys.stderr); return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
