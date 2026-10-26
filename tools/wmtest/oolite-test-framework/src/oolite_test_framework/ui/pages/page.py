"""Base class of every page object: a game screen that can recognise itself on screen."""


class Page:
    NAME = "page"

    def __init__(self, app):
        self.app = app

    def is_displayed(self):
        raise NotImplementedError

    def wait_until_displayed(self, timeout=None):
        self.app.wait_until(self.is_displayed, "the %s to be drawn in the game window" % self.NAME, timeout)
        self.app.screenshot(self.NAME.replace(" ", "-"))
        return self
