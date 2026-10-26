# Oolite game tests

Tests **of the game**, written with [oolite-test-framework](../oolite-test-framework/README.md). They test whatever AppImage they are given.
They do not compare builds; comparing is a separate step (see issue #1).

| Folder | What it tests | Needs screenshots? |
|---|---|---|
| `app/` | the app itself: AppImage is a readable file, the game launches without crashing | no |
| `environments/` | window-manager behaviour (issue 773): title bar, keyboard focus, centred splash and window, F12 toggle | no (uses X11 probes) |
| `ui/` | what the player sees, via page objects: render checks, key response, title menu items and selection | yes |

`conftest.py` loads the framework plugin; `pytest.ini` puts the framework `src/` on the path.

## Run
Normally through the framework command, which runs them in a Docker image per environment:

    ../oolite-test-framework/wmtest base:../appimages/base.AppImage fix:../appimages/fix.AppImage --env marco --quick

Test names are used by the report, so do not rename a test function without updating `oolite_test_framework/outcomes.py`.
To add a test, add a function to the folder that fits and use the `launched_game`, `fresh_game`, `app` or `env_session` fixtures (see the framework README, "Add a test").
