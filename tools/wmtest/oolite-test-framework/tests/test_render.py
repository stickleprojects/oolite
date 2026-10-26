import os
import random

from oolite_test_framework import outcomes, render


def img(fn, w=64, h=48):
    return bytes(c for y in range(h) for x in range(w) for c in fn(x, y)), w, h


def test_black_blank_uniform_are_rejected():
    assert render.analyse(*img(lambda x, y: (0, 0, 0)))["verdict"] == "black"
    assert render.analyse(*img(lambda x, y: (255, 255, 255)))["verdict"] == "blank"
    assert render.analyse(*img(lambda x, y: (40, 90, 160)))["verdict"] == "uniform"


def test_flat_image_without_texture_is_rejected():
    assert render.analyse(*img(lambda x, y: ((0, 0, 0) if x < 32 else (20, 20, 20))))["verdict"] in ("flat", "black")
    assert render.analyse(*img(lambda x, y: ((200, 0, 0) if x < 32 else (0, 0, 200))))["verdict"] == "flat"      # two colours only


def test_textured_content_passes():
    rnd = random.Random(1)
    noisy = img(lambda x, y: (rnd.randrange(256), rnd.randrange(256), rnd.randrange(256)))
    gradient = img(lambda x, y: (x * 4 % 256, y * 5 % 256, (x + y) * 3 % 256))
    assert render.analyse(*noisy)["verdict"] == "ok" and render.analyse(*gradient)["verdict"] == "ok"


def test_mostly_black_space_scene_with_stars_and_a_ship_passes():
    rnd = random.Random(2)
    def scene(x, y):
        if 20 <= x < 44 and 15 <= y < 33: return (60 + (x * 7) % 150, 80 + (y * 11) % 120, 120 + (x * y) % 100)     # a lit ship
        return (255, 255, 255) if rnd.random() < 0.01 else (0, 0, 8)
    assert render.analyse(*img(scene, 160, 120))["verdict"] == "ok"


def test_png_writer_and_bgrx(tmp_path):
    rgb, w, h = img(lambda x, y: (x, y, 7), 8, 4)
    p = tmp_path / "a.png"; render.write_png(str(p), w, h, rgb)
    d = p.read_bytes(); assert d.startswith(b"\x89PNG") and b"IDAT" in d and d.endswith(b"IEND\xaeB`\x82")
    assert render.bgrx_to_rgb(bytes([3, 2, 1, 0] * 4), 2, 2) == bytes([1, 2, 3] * 4)


def test_gl_log_scan():
    n, first = render.scan_logs([("out.log", "ok\nCould not make OpenGL context current: x\n"), ("Latest.log", "fine\nGL error 1282\n")])
    assert n == 2 and "Could not make OpenGL context current" in first
    assert render.scan_logs([("out.log", "all quiet\n")]) == (0, "")


def test_check_renders_outcomes():
    assert outcomes.check_renders({"render": "ok", "gl_errors": 0, "exited": 0}) == ("passed", "")
    assert outcomes.check_renders({"render": "black", "gl_errors": 0, "exited": 0, "render_colours": 1, "render_std": 0})[0] == "failed"
    assert outcomes.check_renders({"render": "ok", "gl_errors": 2, "gl_first": "out.log: GL error"})[0] == "failed"
    assert outcomes.check_renders({"render": "NA", "gl_errors": 0, "exited": 0})[0] == "skipped"


def test_changed_share_detects_a_frozen_window():
    a = bytes([10, 20, 30] * 4000)
    assert render.changed_share(a, a) == 0.0
    b = bytes([10, 20, 30] * 2000 + [200, 20, 30] * 2000)
    assert 0.4 < render.changed_share(a, b) < 0.6
    assert render.changed_share(a, a[:-3]) is None


def test_check_renders_fails_a_frozen_window_but_ignores_missing_data():
    frozen = {"render": "ok", "gl_errors": 0, "exited": 0, "render_changed": 0.0, "render_gap": 3}
    assert outcomes.check_renders(frozen)[0] == "failed" and "frozen" in outcomes.check_renders(frozen)[1]
    assert outcomes.check_renders({"render": "ok", "gl_errors": 0, "exited": 0, "render_changed": 0.31})[0] == "passed"
    assert outcomes.check_renders({"render": "ok", "gl_errors": 0, "exited": 0})[0] == "passed"      # old raw files have no render_changed
