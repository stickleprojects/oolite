"""PNG reading and writing (stdlib only): enough for screenshots (8-bit RGB / RGBA, no interlacing) and the OCR crops."""
import struct
import zlib


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
