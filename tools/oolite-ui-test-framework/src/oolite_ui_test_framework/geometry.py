"""Pure checks over raw observations. No I/O: the verdict step calls these so tolerances can change without re-running the game.

Geometry strings are 'WxH+X+Y' (outer window = the WM frame when there is one). A monitor is the same format."""
import re

DEFAULT_TOL = 40
_G = re.compile(r"^(\d+)x(\d+)([+-]\d+)([+-]\d+)$")


def parse_geom(s):
    """'WxH+X+Y' -> (x, y, w, h), or None for NA / missing / malformed."""
    m = _G.match(s or "")
    return (int(m[3]), int(m[4]), int(m[1]), int(m[2])) if m else None


def fmt_geom(g):
    return "NA" if g is None else "%dx%d%+d%+d" % (g[2], g[3], g[0], g[1])


def offsets(outer, mon):
    """(dx, dy): outer window centre minus monitor centre. Integer halves as in trial.sh. None if either is missing."""
    if outer is None or mon is None: return None
    return (outer[0] + outer[2] // 2 - (mon[0] + mon[2] // 2), outer[1] + outer[3] // 2 - (mon[1] + mon[3] // 2))


def centred(dx, dy, tol=DEFAULT_TOL):
    """1 if |dx| and |dy| <= tol, 0 if not, None if not measurable."""
    if dx is None or dy is None: return None
    return int(abs(dx) <= tol and abs(dy) <= tol)


def framed(parent_is_root):
    """frame check: the window's X parent is not the root window."""
    return None if parent_is_root is None else int(not parent_is_root)


def focused(active_id, focus_id, win_id):
    """focus check: the window is _NET_ACTIVE_WINDOW or the X input focus."""
    return int(win_id is not None and win_id in (active_id, focus_id))


def _num(v):
    try: return int(v)
    except (TypeError, ValueError): return None


def apply(rec, tol=DEFAULT_TOL):
    """Recompute dx/dy/centred (and the splash/post/toggle variants) of a raw record from its recorded geometry with `tol`.
    Records without geometry (older raw files) keep their stored dx/dy/centred values, only centred is re-judged from dx/dy."""
    out = dict(rec); mon = parse_geom(rec.get("mon"))
    for pre, key in (("", "outer"), ("splash_", "splash_outer"), ("post_", "post_outer"), ("t_", "t_outer")):
        o = parse_geom(rec.get(key))
        if o is not None and mon is not None:
            dx, dy = offsets(o, mon); out[pre + "dx"], out[pre + "dy"] = str(dx), str(dy)
        if pre in ("", "t_"):
            c = centred(_num(out.get(pre + "dx")), _num(out.get(pre + "dy")), tol)
            if c is not None: out[pre + "centred"] = str(c)
    sdx, sdy = _num(out.get("splash_dx")), _num(out.get("splash_dy"))
    sc = centred(sdx, sdy, tol)
    out["splash_centred"] = "NA" if sc is None else str(sc)
    out["tol"] = str(tol)
    return out
