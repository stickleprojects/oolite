# MenuList: a vertical list of text rows with one highlighted (see ui/components/__init__.py for the package)
"""Reusable page components. A component is a part of a screen that reads ITSELF from a screenshot (what is actually there) and can be operated.
It is configured by the page that owns it (where it is, what the highlight looks like); the page, not the component, holds what is EXPECTED."""


class MenuList:
    """A vertical list of text rows, one of them highlighted. It reports what is really drawn:
      rows            -> the text rows found in the region (top to bottom), each {y, highlighted}
      visible_count   -> how many rows are drawn
      selected_index  -> 1-based position of the highlighted row (None when nothing is highlighted)
      texts()         -> the text of each row, only when an OCR function is available (else None); OCR is optional.
    A row = a run of pixels that are `is_text` or `is_highlight` across the region; it is highlighted when much of it is `is_highlight`."""

    def __init__(self, app, x, y, is_highlight, is_text, min_row_pixels=8, max_gap=3, highlight_share=0.25):
        self.app, self.x, self.y, self.is_highlight, self.is_text = app, x, y, is_highlight, is_text
        self.min_row_pixels, self.max_gap, self.highlight_share = min_row_pixels, max_gap, highlight_share

    # ---- reading
    def rows_in(self, shot):
        if shot is None: return []
        x0, y0, x1, y1 = shot.region(self.x[0], self.y[0], self.x[1], self.y[1])
        scan = []                                   # per pixel row: (text pixels, highlight pixels)
        for y in range(y0, y1):
            t = hl = 0
            for x in range(x0, x1):
                p = shot.pixel(x, y)
                if self.is_highlight(*p): hl += 1; t += 1
                elif self.is_text(*p): t += 1
            scan.append((t, hl))
        bands = []; start = last = None
        for i, (t, _) in enumerate(scan):
            if t >= self.min_row_pixels:
                if start is None: start = i
                elif i - last > self.max_gap + 1: bands.append((start, last)); start = i
                last = i
        if start is not None: bands.append((start, last))
        rows = []
        for a, b in bands:
            t = sum(scan[i][0] for i in range(a, b + 1)); hl = sum(scan[i][1] for i in range(a, b + 1))
            rows.append({"y": (y0 + (a + b) / 2) / shot.h, "highlighted": t > 0 and hl / t >= self.highlight_share, "box": (x0, y0 + a, x1, y0 + b + 1)})
        return rows

    @property
    def rows(self):
        return self.rows_in(self.app.screenshot())

    @property
    def visible_count(self):
        return len(self.rows)

    @property
    def selected_index(self):
        hl = [i for i, r in enumerate(self.rows, 1) if r["highlighted"]]
        return hl[0] if len(hl) == 1 else None

    def is_visible(self):
        return self.selected_index is not None

    def texts(self):
        """Text of each visible row via the app's OCR function, or None when there is no OCR (callers must then skip, not fail)."""
        ocr = getattr(self.app, "ocr", None); shot = self.app.screenshot()
        if ocr is None or shot is None: return None
        return [ocr(shot.crop_box(r["box"])) for r in self.rows_in(shot)]

    # ---- operating
    def move_down(self, times=1):
        for _ in range(times): self._step("Down")
        return self

    def move_up(self, times=1):
        for _ in range(times): self._step("Up")
        return self

    def settled_index(self, quiet=1.5, step=0.25, limit=15.0):
        """Highlighted row once it has stayed on the same row for `quiet` seconds. A held key keeps repeating after it is released (the game works
        through it one frame at a time), so the highlight is still moving for a while; a read taken then is not the answer. None if it never settles."""
        need, seen, last, waited = round(quiet / step), 0, object(), 0.0
        while waited < limit:
            cur = self.selected_index
            seen = seen + 1 if cur is not None and cur == last else 0
            if seen >= need: return cur
            last = cur; self.app.clock.sleep(step); waited += step
        return None

    def _step(self, key, cap=3.0):
        """Move the highlight off its row: hold the key only until the highlight has moved (see App.press_until), then let it settle.
        It can still move one row too far on a slow frame, so select_index() looks at where it ended up."""
        from ...app import ScenarioFailed       # imported here: app.py imports the pages, which import this module
        before = self.settled_index()
        self.app.press_until(key, lambda: self.selected_index not in (None, before), cap)
        after = self.settled_index()
        if after is not None and after != before: return
        n = self.app.keys_received()
        why = "" if n is None else "; the game logged no key presses at all (does its window have keyboard focus?)" if n == 0 else \
              "; the game logged %d key presses" % n
        raise ScenarioFailed("the highlight did not leave row %s after %s was held for up to %.1f s%s" % (before, key, cap, why))

    def wait_until_selected_index(self, index, timeout=5):
        self.app.wait_until(lambda: self.selected_index == index, "row %d to be the highlighted row (now %s of %d visible)" % (index, self.selected_index, self.visible_count), timeout)
        self.app.screenshot("selected-row-%d" % index)
        return self

    def select_index(self, index, timeout=5, max_steps=12):
        """Press Up/Down until row `index` is highlighted, looking at the screen after every press (a press can move more than one row)."""
        for _ in range(max_steps):
            cur = self.settled_index()
            if cur is None: raise AssertionError("the list is not visible, cannot select row %d" % index)
            if cur == index: break
            (self.move_down if index > cur else self.move_up)()
        return self.wait_until_selected_index(index, timeout)
