"""geometry: parsing 'WxH+X+Y' strings, frame and focus flags, and apply() adding dx/dy/centred to raw records. Pure functions, no
fakes needed."""
from oolite_ui_test_framework import geometry


def test_parse_and_format_geometry():
    assert geometry.parse_geom("1280x720+1280+180") == (1280, 180, 1280, 720)
    assert geometry.parse_geom("100x50-10-20") == (-10, -20, 100, 50)
    assert geometry.parse_geom("NA") is None and geometry.parse_geom(None) is None
    assert geometry.fmt_geom((1280, 180, 1280, 720)) == "1280x720+1280+180"


def test_offsets_primary_centre():
    mon = (0, 0, 3840, 1080)
    assert geometry.offsets((1280, 180, 1280, 720), mon) == (0, 0)
    assert geometry.offsets((1537, 200, 1280, 720), mon) == (257, 20)      # the openbox "keeps the splash's left edge" case
    assert geometry.offsets(None, mon) is None


def test_centred_boundary_and_na():
    assert geometry.centred(40, -40, 40) == 1 and geometry.centred(41, 0, 40) == 0
    assert geometry.centred(None, 0, 40) is None


def test_frame_and_focus():
    assert geometry.framed(False) == 1 and geometry.framed(True) == 0 and geometry.framed(None) is None
    assert geometry.focused(5, 0, 5) == 1 and geometry.focused(0, 5, 5) == 1 and geometry.focused(0, 0, 5) == 0


def test_tolerance_can_change_without_rerun():
    rec = {"outer": "1280x720+1337+200", "mon": "3840x1080+0+0", "tol": "40", "centred": "1", "dx": "57", "dy": "20"}
    assert geometry.apply(rec, 40)["centred"] == "0"      # |dx| = 97? 1337+640-1920 = 57 > 40
    assert geometry.apply(rec, 60)["centred"] == "1"


def test_apply_keeps_old_records_without_geometry():
    old = {"frame": "1", "dx": "257", "dy": "0", "centred": "0", "tol": "40"}
    assert geometry.apply(old, 40)["centred"] == "0" and geometry.apply(old, 300)["centred"] == "1"
    na = {"frame": "NA", "dx": "NA", "dy": "NA", "centred": "NA", "exited": "0"}
    assert geometry.apply(na, 40)["centred"] == "NA"


def test_apply_splash_post_and_toggle_variants():
    rec = {"outer": "1280x720+1280+180", "mon": "3840x1080+0+0", "splash_outer": "768x768+1536+156", "post_outer": "NA",
           "t_outer": "1280x720+1300+180"}
    out = geometry.apply(rec)
    assert (out["dx"], out["dy"]) == ("0", "0") and out["splash_dx"] == "0" and "post_dx" not in out
    assert out["t_dx"] == "20" and out["t_centred"] == "1"
