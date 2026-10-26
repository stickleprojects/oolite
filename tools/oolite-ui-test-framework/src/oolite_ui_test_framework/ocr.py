"""Optional OCR of a small cropped screenshot (one line of text) using the tesseract command-line tool. Standalone: depends only on
oolite_ui_test_framework.png (PNG writer) and the standard library. No Python packages are needed.

    ocr = oolite_ui_test_framework.ocr.make_ocr()          # None when tesseract is not installed: callers must SKIP the text check, never fail it
    text = ocr(shot)                  # shot = oolite_ui_test_framework.screen.Shot (w, h, rgb); returns the text read, e.g. "Game Options"

Pre-processing matters more than anything else for accuracy: Oolite draws light text on black, and black text on a red bar for the selected
row. Tesseract wants dark text on white, so each crop is converted to pure black text on white (no greys): the predominant colour is found,
every pixel that differs clearly from it is marked as text, and the marked pixels are redrawn black on white, scaled up, with a white border."""
import difflib
import os
import shutil
import subprocess
import tempfile

from . import png
from .screen import Shot

SCALE = 3
PAD = 8


DIFFERENT_COLOUR_THRESHOLD = 150    # how far (sum of the R, G and B differences) a pixel must be from the predominant colour to count as 'different'


def _get_predominant_colour(shot):
    """The single colour (an (R, G, B) tuple) that covers most of the crop: black for a plain row, red for the selected row. Sampled, and rounded to the middle of its bucket."""
    counts = {}
    for i in range(0, shot.w * shot.h, max(1, shot.w * shot.h // 4000)):
        bucket = (shot.rgb[3 * i] >> 5, shot.rgb[3 * i + 1] >> 5, shot.rgb[3 * i + 2] >> 5)
        counts[bucket] = counts.get(bucket, 0) + 1
    return tuple(c * 32 + 16 for c in max(counts, key=counts.get))


def _get_two_tone_mask(shot, predominant):
    """Two-tone version of the crop, one byte per pixel: 1 where the pixel differs clearly from `predominant` (the text), 0 where it is similar (everything else)."""
    rgb = shot.rgb
    return bytearray(1 if abs(rgb[3 * i] - predominant[0]) + abs(rgb[3 * i + 1] - predominant[1]) + abs(rgb[3 * i + 2] - predominant[2]) > DIFFERENT_COLOUR_THRESHOLD else 0
                     for i in range(shot.w * shot.h))


def _get_black_and_white_image(mask, w, h, scale, pad):
    """Pure black-and-white image (no greys) from a two-tone mask: 1 -> black, 0 -> white, each mask pixel drawn scale x scale pixels big, with a white border of `pad` pixels."""
    W, H = w * scale + 2 * pad, h * scale + 2 * pad
    page = bytearray(b"\xff" * (W * H * 3))
    for y in range(h):
        for x in range(w):
            if mask[y * w + x]:
                for dy in range(scale):
                    o = 3 * ((pad + y * scale + dy) * W + pad + x * scale)
                    page[o:o + 3 * scale] = bytes(3 * scale)
    return Shot(W, H, bytes(page))


def prepare(shot, scale=SCALE, pad=PAD):
    """Make a crop readable for tesseract, which wants dark text on white: take the crop's predominant colour, mark every pixel that differs from it (the text), then redraw
    those pixels black on white, scaled up. Works for both light-on-black rows and the black-on-red selected row. Pure (no tesseract needed)."""
    mask = _get_two_tone_mask(shot, _get_predominant_colour(shot))
    return _get_black_and_white_image(mask, shot.w, shot.h, scale, pad)


def make_ocr(tesseract=None, runner=subprocess.run, which=shutil.which, timeout=15):
    """Returns ocr(shot) -> str, or None when tesseract is not available. `runner` and `which` can be replaced in tests."""
    exe = tesseract or which("tesseract")
    if not exe: return None

    def ocr(shot):
        p = prepare(shot)
        with tempfile.TemporaryDirectory(prefix="uitest-ocr.") as d:
            path = os.path.join(d, "line.png"); png.write_png(path, p.w, p.h, p.rgb)
            r = runner([exe, path, "-", "--psm", "7"], capture_output=True, text=True, timeout=timeout)
        return (r.stdout or "").strip() if r.returncode == 0 else ""
    return ocr


def same_text(read, expected, min_ratio=0.85):
    """Tolerant comparison: ignores case and spacing, allows an occasional misread character."""
    a = "".join(read.lower().split()); b = "".join(expected.lower().split())
    return bool(a) and difflib.SequenceMatcher(None, a, b).ratio() >= min_ratio
