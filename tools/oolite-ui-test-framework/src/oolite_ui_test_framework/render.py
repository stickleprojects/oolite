"""Did the game actually render? Image heuristic (pure, stdlib), PNG writer, and the GL log scan.
An image is 'ok' when it is not blank, not black, not uniform and has textured content (enough distinct colours and variance)."""
import re
import struct
import zlib

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


def write_png(path, w, h, rgb):
    raw = b"".join(b"\x00" + rgb[y * w * 3:(y + 1) * w * 3] for y in range(h))
    def chunk(t, d): return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    with open(path, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(raw, 6)) + chunk(b"IEND", b""))


def read_png(path):
    """(w, h, rgb bytes) of an 8-bit RGB/RGBA, non-interlaced PNG (what write_png and the screenshot tools produce)."""
    data = open(path, "rb").read()
    if data[:8] != b"\x89PNG\r\n\x1a\n": raise ValueError("not a PNG: %s" % path)
    pos = 8; idat = b""; w = h = ct = None
    while pos < len(data):
        n, t = struct.unpack(">I4s", data[pos:pos + 8]); body = data[pos + 8:pos + 8 + n]; pos += 12 + n
        if t == b"IHDR":
            w, h, depth, ct, _, _, il = struct.unpack(">IIBBBBB", body)
            if depth != 8 or ct not in (2, 6) or il: raise ValueError("unsupported PNG (need 8-bit RGB/RGBA, not interlaced)")
        elif t == b"IDAT": idat += body
    bpp = 3 if ct == 2 else 4; stride = w * bpp; raw = zlib.decompress(idat); out = bytearray(); prev = bytearray(stride)
    for y in range(h):
        f = raw[y * (stride + 1)]; line = bytearray(raw[y * (stride + 1) + 1:(y + 1) * (stride + 1)])
        for i in range(stride):
            a = line[i - bpp] if i >= bpp else 0; b = prev[i]; c = prev[i - bpp] if i >= bpp else 0
            if f == 1: line[i] = (line[i] + a) & 255
            elif f == 2: line[i] = (line[i] + b) & 255
            elif f == 3: line[i] = (line[i] + ((a + b) >> 1)) & 255
            elif f == 4:
                p = a + b - c; pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                line[i] = (line[i] + (a if pa <= pb and pa <= pc else b if pb <= pc else c)) & 255
        out += line; prev = line
    if bpp == 4:
        rgb = bytearray(w * h * 3)
        for c in range(3): rgb[c::3] = out[c::4]
        return w, h, bytes(rgb)
    return w, h, bytes(out)


def bgrx_to_rgb(data, w, h):
    out = bytearray(w * h * 3); out[0::3] = data[2::4][:w * h]; out[1::3] = data[1::4][:w * h]; out[2::3] = data[0::4][:w * h]
    return bytes(out)


def scan_logs(texts):
    """texts = [(name, content)] -> (count, first matching line) of GL problems."""
    hits = []
    for name, t in texts:
        for ln in t.splitlines():
            if any(re.search(p, ln) for p in GL_ERROR_PATTERNS): hits.append("%s: %s" % (name, ln.strip()[:160]))
    return len(hits), (hits[0] if hits else "")
