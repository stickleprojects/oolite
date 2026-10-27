"""raw_results: RESULT / SKIP line formatting and parsing, including NA values and lines written by older versions (fixtures/)."""
import os

from oolite_ui_test_framework import raw_results

DATA = os.path.join(os.path.dirname(__file__), "fixtures")


def test_roundtrip_and_na():
    rec = {"wm": "marco", "build": "base", "screen": "3840x1080", "run": 1, "frame": 0, "focus": None, "dx": None, "centred": 0, "exited": 0, "tol": 40, "outer": "1x1+0+0"}
    line = raw_results.format_result(rec)
    assert line.startswith("RESULT wm=marco build=base screen=3840x1080 run=1 frame=0 focus=NA dx=NA")
    kind, d = raw_results.parse_line(line)
    assert kind == "RESULT" and d["focus"] == "NA" and d["outer"] == "1x1+0+0"


def test_old_lines_parse():
    for ln in open(os.path.join(DATA, "matrix3-debian.raw")):
        if ln.startswith("RESULT"):
            k, d = raw_results.parse_line(ln); assert d["wm"] in ("kwin", "mutter") and "t_ok" in d


def test_skip_line_reason_with_spaces():
    k, d = raw_results.parse_line(raw_results.format_skip("marco", "3840x1080", "base", "not available: docker missing"))
    assert k == "SKIP" and d["reason"] == "not available: docker missing" and d["wm"] == "marco"
