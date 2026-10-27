"""RESULT / SKIP / WMVER / HOSTENV raw lines. The key=value fields of RESULT are the same as the bash harness wrote, plus extras at the end."""
import time

ORDER = ["wm", "build", "screen", "run", "frame", "focus", "dx", "dy", "centred", "exited", "splash_dx", "splash_dy", "post_dx", "post_dy", "tol",
         "t_ok", "t_method", "t_frame", "t_focus", "t_dx", "t_dy", "t_centred"]


def stamp(t=None):
    """UTC timestamp for raw lines and progress output: 2026-10-27T05:40:12Z."""
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(t))


def fmt(v):
    return "NA" if v is None else str(int(v)) if isinstance(v, bool) else str(v).replace(" ", "_")


def format_result(rec):
    keys = [k for k in ORDER if k in rec] + sorted(k for k in rec if k not in ORDER)
    return "RESULT " + " ".join("%s=%s" % (k, fmt(rec[k])) for k in keys)


def parse_line(line):
    """'KEY a=b c=d' -> (KEY, {a: b, c: d}); SKIP's reason= takes the rest of the line."""
    head, _, why = line.rstrip("\n").partition(" reason=")
    parts = head.split()
    d = dict(kv.split("=", 1) for kv in parts[1:] if "=" in kv)
    if why: d["reason"] = why
    return (parts[0] if parts else ""), d


def format_kv(kind, **kw):
    return kind + " " + " ".join("%s=%s" % (k, fmt(v)) for k, v in kw.items())


def format_skip(wm, screen, build, reason):
    return "SKIP wm=%s screen=%s build=%s reason=%s" % (wm, screen, build, reason)
