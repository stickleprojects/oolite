# Oolite game tests

Tests **of the game**, written with [oolite-test-framework](../oolite-test-framework/README.md). Each test checks the AppImage it is given;
it never knows about other builds. Comparing two builds happens afterwards, in the report, when `wmtest` is given two AppImages
(see [the wmtest README](../README.md)).

| Folder | What it tests | Needs screenshots? |
|---|---|---|
| `app/` | the app itself: AppImage is a readable file, the game launches without crashing | no |
| `environments/` | window-manager behaviour (issue 773): title bar, keyboard focus, centred splash and window, F12 toggle | no (uses X11 probes) |
| `ui/` | what the player sees, via page objects: render checks, key response, title menu items and selection | yes |

`conftest.py` loads the framework plugin; `pytest.ini` puts the framework `src/` on the path.

## Run
Through the `wmtest` command, which runs them in a Docker image per environment (from `oolite-test-framework/`):

    ./wmtest mine:/path/Oolite.AppImage --env marco --quick --desc "smoke test"
    ./wmtest mine:/path/Oolite.AppImage --env marco --tests title_menu_shown_and_keys_move_selection --runs 1 --desc "menu test"

[The wmtest README](../README.md) lists the other kinds of run (all window managers, comparing builds, headed, your desktop).

Test names are used by the report, so do not rename a test function without updating `oolite_test_framework/outcomes.py`.
To add a test, add a function to the folder that fits and use the `launched_game`, `fresh_game`, `app` or `env_session` fixtures (see the framework README, "Add a test").
