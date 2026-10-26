"""Did the game actually render? Image heuristic (pure, stdlib) and the GL log scan. PNG reading and writing is in png.py.
An image is 'ok' when it is not blank, not black, not uniform and has textured content (enough distinct colours and variance)."""
import re

GL_ERROR_PATTERNS = [r"Could not make OpenGL context current", r"\bGL error\b", r"OpenGL error", r"glGetError", r"GL_INVALID_(OPERATION|ENUM|VALUE)", r"Failed to create OpenGL context"]


def analyse(rgb, w, h, min_colours=24, min_std=12.0):
    """rgb = bytes of w*h*3. Returns {verdict, colours, std, mean, top_share}; verdict: ok | blank | black | uniform | flat."""
    n = w * h
    if n == 0 or len(rgb) < n * 3: return {"verdict": "blank", "colours": 0, "std": 0.0, "mean": 0.0, "top_share": 1.0}
    step = max(1, n // 20000)                                  # sample at most ~20000 pixels
    counts = {}; s = s2 = 0.0; m = 0
    for i in range(0, n, step):
        r, g, b = rgb[3 * i], rgb[3 * i + 1], rgb[3 * i + 2]
        q = (r >> 4, g >> 4, b >> 4); counts[q] = counts.get(q, 0) + 1
        y = 0.299 * r + 0.587 * g + 0.114 * b; s += y; s2 += y * y; m += 1
    mean = s / m; std = max(0.0, s2 / m - mean * mean) ** 0.5; top = max(counts.values()) / m
    colours = sum(1 for c in counts.values() if c >= max(2, m // 10000))        # colours that matter, not single noisy pixels
    if top > 0.995 or colours <= 1: v = "black" if mean < 8 else "blank" if mean > 247 else "uniform"
    elif mean < 3 and std < 3: v = "black"
    elif colours < min_colours or (std < min_std and top > 0.98): v = "flat"
    else: v = "ok"
    return {"verdict": v, "colours": colours, "std": round(std, 1), "mean": round(mean, 1), "top_share": round(top, 3)}


def changed_share(rgb1, rgb2):
    """Share (0..1) of sampled pixels that differ between two frames of the same size. The title screen animates, so a window that never
    changes between two grabs seconds apart is not being drawn to (this is what a frozen splash frame looks like). None if sizes differ."""
    if len(rgb1) != len(rgb2) or not rgb1: return None
    n = len(rgb1) // 3; step = max(1, n // 20000); diff = m = 0
    for i in range(0, n, step):
        j = 3 * i; m += 1
        if rgb1[j:j + 3] != rgb2[j:j + 3]: diff += 1
    return round(diff / m, 4)


def scan_logs(texts):
    """texts = [(name, content)] -> (count, first matching line) of GL problems."""
    hits = []
    for name, t in texts:
        for ln in t.splitlines():
            if any(re.search(p, ln) for p in GL_ERROR_PATTERNS): hits.append("%s: %s" % (name, ln.strip()[:160]))
    return len(hits), (hits[0] if hits else "")
