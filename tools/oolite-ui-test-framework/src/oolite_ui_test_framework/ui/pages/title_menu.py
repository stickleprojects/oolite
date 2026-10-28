"""Page objects: one class per game screen. A page knows how to recognise itself on screen, what it SHOULD contain and what you can do on it.
Tests talk to pages (app.title_menu.select("Game Options")), never to pixels, key names or timings. Anything specific to one screen (where its list
is, how its highlight looks, which items are expected) is configured here, on that page. What is actually drawn is read by the components
(ui/components/, one module per component) from the screenshot, not from what the game reports, so a blank or frozen window fails."""
from ... import ocr as ocrmod
from ..components import MenuList
from .page import Page


class TitleMenuPage(Page):
    NAME = "title menu"
    EXPECTED_ITEMS = ["Start New Commander", "Load Commander", "View Ship Library", "Game Options", "Manage Expansion Packs", "Exit Game"]

    def __init__(self, app):
        super().__init__(app)
        # menu block at the bottom centre; highlighted row = black text on a red bar, other rows = yellow text. Text is yellow only (little
        # blue): the rotating ship above the menu can dip into this region, and its lit hull is white or grey, so "any bright pixel" counted
        # it as an extra row (7 rows, highlight on row 2) in every environment
        self.menu = MenuList(app, x=(0.35, 0.65), y=(0.75, 1.0),
                             is_highlight=lambda r, g, b: r > 200 and g < 40 and b < 40,
                             is_text=lambda r, g, b: max(r, g) > 120 and b < min(r, g) // 2)

    def is_displayed(self):
        return self.menu.is_visible()

    def shows_expected_items(self):
        """(ok, reason): as many rows are drawn as expected; with OCR also the text of each. Without OCR the text part is not checked."""
        n = self.menu.visible_count
        if n != len(self.EXPECTED_ITEMS): return False, "%d menu rows are drawn, expected %d" % (n, len(self.EXPECTED_ITEMS))
        t = self.menu.texts()
        if t is not None:
            bad = [(r, e) for r, e in zip(t, self.EXPECTED_ITEMS) if not ocrmod.same_text(r, e)]
            if bad: return False, "menu text read as %s, expected %s" % ([r for r, _ in bad], [e for _, e in bad])
        return True, ""

    @property
    def selected_item(self):
        """Name of the highlighted item (by position among the expected items), None if nothing is highlighted or the row count is wrong."""
        i = self.menu.selected_index
        return self.EXPECTED_ITEMS[i - 1] if i is not None and self.menu.visible_count == len(self.EXPECTED_ITEMS) else None

    def settled_item(self):
        """Like selected_item, but only once the highlight has stopped moving (see MenuList.settled_index)."""
        i = self.menu.settled_index()
        return self.EXPECTED_ITEMS[i - 1] if i is not None and self.menu.visible_count == len(self.EXPECTED_ITEMS) else None

    def select(self, item, timeout=5, by=None):
        """Highlight `item` with the mouse where the environment can click, else with the keys; by="mouse" or by="keys" chooses."""
        self.menu.select_index(self.EXPECTED_ITEMS.index(item) + 1, timeout, by=by)
        return self
