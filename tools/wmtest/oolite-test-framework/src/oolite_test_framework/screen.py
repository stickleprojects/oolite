"""Generic screenshot access (no knowledge of any game screen): pixels, regions as window fractions, crops (what an OCR step is given)."""
from dataclasses import dataclass


@dataclass
class Shot:
    w: int
    h: int
    rgb: bytes

    @classmethod
    def from_grab(cls, g):
        return None if g is None else cls(g[0], g[1], g[2])

    def pixel(self, x, y):
        i = 3 * (y * self.w + x)
        return self.rgb[i], self.rgb[i + 1], self.rgb[i + 2]

    def region(self, x0, y0, x1, y1):
        """(x, y) pixel bounds of a region given as fractions of the window."""
        return int(self.w * x0), int(self.h * y0), int(self.w * x1), int(self.h * y1)

    def crop_box(self, box):
        """Cropped Shot from a pixel box (x0, y0, x1, y1)."""
        a, b, c, d = box
        return Shot(c - a, d - b, b"".join(self.rgb[3 * (y * self.w + a):3 * (y * self.w + c)] for y in range(b, d)))

    def crop(self, x0, y0, x1, y1):
        """Cropped Shot; the arguments are fractions of the window (what an OCR step would be given)."""
        a, b, c, d = self.region(x0, y0, x1, y1)
        return Shot(c - a, d - b, b"".join(self.rgb[3 * (y * self.w + a):3 * (y * self.w + c)] for y in range(b, d)))
