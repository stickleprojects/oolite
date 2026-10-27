"""What the player sees on the title screen, checked on the screenshot (not on what the game reports), driven through page objects."""
import pytest

pytestmark = pytest.mark.game


def test_title_menu_is_displayed(app):
    """After the splash the title menu is really drawn in the window, has the expected items and starts on the first one."""
    page = app.title_menu.wait_until_displayed()
    ok, why = page.shows_expected_items()
    assert ok, why
    first = page.settled_item()
    assert first == "Start New Commander", "expected the first item selected at first, got %s" % first


@pytest.mark.needs_keys
def test_title_menu_responds_to_keys(app):
    """The keyboard reaches the game: pressing keys on the title menu moves the highlight to another item."""
    page = app.title_menu.wait_until_displayed()
    page.select("Game Options")
    assert page.settled_item() == "Game Options"
