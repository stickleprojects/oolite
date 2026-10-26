"""render_check: the did-it-render image heuristic, the frozen-window comparison and the GL error scan of the game logs, on invented
images and log text. No display or game needed."""
import random

from oolite_ui_test_framework import render_check


def img(fn, w=64, h=48):
    return bytes(c for y in range(h) for x in range(w) for c in fn(x, y)), w, h


def test_black_blank_uniform_are_rejected():
    assert render_check.analyse(*img(lambda x, y: (0, 0, 0)))["verdict"] == "black"
    assert render_check.analyse(*img(lambda x, y: (255, 255, 255)))["verdict"] == "blank"
    assert render_check.analyse(*img(lambda x, y: (40, 90, 160)))["verdict"] == "uniform"


def test_flat_image_without_texture_is_rejected():
    assert render_check.analyse(*img(lambda x, y: ((0, 0, 0) if x < 32 else (20, 20, 20))))["verdict"] in ("flat", "black")
    assert render_check.analyse(*img(lambda x, y: ((200, 0, 0) if x < 32 else (0, 0, 200))))["verdict"] == "flat"      # two colours only


def test_textured_content_passes():
    rnd = random.Random(1)
    noisy = img(lambda x, y: (rnd.randrange(256), rnd.randrange(256), rnd.randrange(256)))
    gradient = img(lambda x, y: (x * 4 % 256, y * 5 % 256, (x + y) * 3 % 256))
    assert render_check.analyse(*noisy)["verdict"] == "ok" and render_check.analyse(*gradient)["verdict"] == "ok"


def test_mostly_black_space_scene_with_stars_and_a_ship_passes():
    rnd = random.Random(2)
    def scene(x, y):
        if 20 <= x < 44 and 15 <= y < 33: return (60 + (x * 7) % 150, 80 + (y * 11) % 120, 120 + (x * y) % 100)     # a lit ship
        return (255, 255, 255) if rnd.random() < 0.01 else (0, 0, 8)
    assert render_check.analyse(*img(scene, 160, 120))["verdict"] == "ok"


def test_gl_log_scan():
    n, first = render_check.scan_logs([("out.log", "ok\nCould not make OpenGL context current: x\n"), ("Latest.log", "fine\nGL error 1282\n")])
    assert n == 2 and "Could not make OpenGL context current" in first
    assert render_check.scan_logs([("out.log", "all quiet\n")]) == (0, "")


def test_changed_share_detects_a_frozen_window():
    a = bytes([10, 20, 30] * 4000)
    assert render_check.changed_share(a, a) == 0.0
    b = bytes([10, 20, 30] * 2000 + [200, 20, 30] * 2000)
    assert 0.4 < render_check.changed_share(a, b) < 0.6
    assert render_check.changed_share(a, a[:-3]) is None
