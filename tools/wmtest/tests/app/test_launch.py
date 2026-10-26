"""Tests of the app itself, no screenshots: the AppImage is a readable file and the game starts without crashing. Fast and robust."""
import os

import pytest

pytestmark = pytest.mark.game


@pytest.mark.once_per_build
def test_appimage_is_executable_file(case):
    assert os.path.isfile(case.app) and os.access(case.app, os.R_OK), "AppImage not readable: %s" % case.app


def test_game_launches(launched_game):
    assert not launched_game.get("crashed"), "the game crashed at start (see out.log); no measurement possible"
