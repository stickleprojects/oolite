"""Window-manager behaviour (issue 773): does the game window get a title bar, keyboard focus and a centred position in this environment
(X11 window managers, Wayland compositors, one or two monitors)? One launch is shared by the read-only checks; F12 gets its own launch.
Each test is one line: pick a check from oolite_ui_test_framework.pass_fail and enforce() it."""
import pytest

from oolite_ui_test_framework import pass_fail
from oolite_ui_test_framework.pytest_helpers import enforce

pytestmark = pytest.mark.game


@pytest.mark.once_per_build
def test_environment_started(env_session):
    """The display server and the WM / compositor came up (a failure to start is already a hard error in env_session)."""
    assert env_session.primary is not None or env_session.env.kind == "host", "no primary monitor reported"


def test_has_frame(launched_game):
    enforce(pass_fail.check_frame(launched_game))


def test_gets_focus(launched_game):
    enforce(pass_fail.check_focus(launched_game))


def test_splash_centred(launched_game):
    enforce(pass_fail.check_splash_centred(launched_game))


def test_game_window_centred(launched_game):
    enforce(pass_fail.check_window_centred(launched_game))


@pytest.mark.needs_toggle
@pytest.mark.needs_x11
@pytest.mark.needs_keys
def test_f12_toggle(fresh_game):
    enforce(pass_fail.check_f12_toggle(fresh_game.toggle()))


@pytest.mark.needs_toggle
@pytest.mark.needs_x11
@pytest.mark.needs_keys
@pytest.mark.saved_window_larger_than_screen
def test_f12_toggle_with_saved_window_larger_than_screen(fresh_game):
    """A player whose saved window is larger than the screen (e.g. moved to a smaller monitor): F12 must still toggle. How the window
    manager fits the oversized window differs between environments (#10: mutter fits it and opt2fix then ignored F12)."""
    enforce(pass_fail.check_f12_toggle(fresh_game.toggle()))
