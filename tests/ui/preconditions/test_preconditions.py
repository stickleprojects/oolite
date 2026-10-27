"""Preconditions, each as its own result: what the other tests rely on from the environment (oolite_ui_test_framework/preconditions.py
says where each was learnt). A failure here explains a failure elsewhere; the tests that rely on one also check it before they run."""
import pytest

from oolite_ui_test_framework import preconditions as pre

pytestmark = pytest.mark.game


@pytest.mark.once_per_build
def test_input_tool_present(env_session):
    pre.require("input_tool", pre.input_tool(env_session.env))


@pytest.mark.once_per_build
def test_fake_input_offered(env_session):
    pre.require("fake_input_offered", pre.fake_input_offered(env_session.env))


@pytest.mark.once_per_build
def test_key_repeat_off(env_session):
    pre.require("key_repeat_off", pre.key_repeat_off(env_session))


@pytest.mark.once_per_build
def test_screenshot_support(env_session):
    pre.require("screenshot_support", pre.screenshot_support(env_session))


@pytest.mark.once_per_build
def test_gpu_present(env_session):
    pre.require("gpu_present", pre.gpu_present(env_session.env))


def test_window_fits_screen(launched_game, env_session):
    """The game's windowed size fits the screen it opens on. Not a gate for F12: that still runs, so a build that copes with a small
    screen and one that does not stay distinguishable (#10)."""
    w, h = launched_game.get("requested_w"), launched_game.get("requested_h")
    if not w: pytest.skip("NOT MEASURABLE: the game's log did not say what window size it asked for")
    pre.require("window_fits_screen", pre.window_fits_screen((w, h), env_session.primary))
