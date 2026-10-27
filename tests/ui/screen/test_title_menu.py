"""What the player sees on the title screen, checked on the screenshot (not on what the game reports), driven through page objects."""
import pytest

from oolite_ui_test_framework import pass_fail
from oolite_ui_test_framework.pytest_helpers import enforce

pytestmark = pytest.mark.game


def test_game_renders(launched_game):
    """After the splash the window shows real content (screenshot heuristic, PNG saved beside the report) and the logs have no GL errors."""
    enforce(pass_fail.check_renders(launched_game))


@pytest.mark.needs_keys
def test_game_responds_to_keys(fresh_game):
    """Press Down twice on the title menu: the window must change."""
    fresh_game.rec.update(fresh_game.input_responds())
    enforce(pass_fail.check_responds_to_keys(fresh_game.finish()))


@pytest.mark.needs_keys
def test_title_menu_shown_and_keys_move_selection(app):
    """The menu is really drawn in the window, has the expected items, starts on the first, and the keyboard can move the highlight to another item."""
    page = app.title_menu.wait_until_displayed()
    ok, why = page.shows_expected_items()
    assert ok, why
    first = page.settled_item()
    assert first == "Start New Commander", "expected the first item selected at first, got %s" % first
    page.select("Game Options")
    assert page.settled_item() == "Game Options"
