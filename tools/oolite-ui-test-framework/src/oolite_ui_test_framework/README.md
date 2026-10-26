# oolite_ui_test_framework (Python package)

How the parts fit together is described under "How it works" in the [framework README](../../README.md#how-it-works).

| Module | What it does |
|---|---|
| `hostrun.py` | behind the `uitest` command: Docker images, containers, the report |
| `plugin.py` | the pytest plugin: `--ui-*` options, fixtures (`launched_game`, `fresh_game`, `app`, `env_session`), result recording |
| `registry.py` | reads `../../environments.toml` |
| `session.py` | starts and stops the display server and window manager or compositor |
| `window_probes.py` | observes the game window (X11, KWin, sway, questions) |
| `fakeinput.py` | keys through KWin's fake-input protocol |
| `scenarios.py` | the game launch, startup sampling and the F12 round trip |
| `geometry.py` | window geometry: frame, focus, centring offsets added to the raw records |
| `pass_fail.py` | each game test's outcome (passed, failed or skipped, with a reason) from a launch record |
| `shared_launch.py` | one game launch shared by several tests, and the check that each test left it unchanged |
| `raw_results.py` | the raw result lines (RESULT, SKIP, ...) |
| `report.py` | statistics over many runs and the Markdown report |
| `app.py` | scenario-style handle on a running game (launch, wait for a screen, press keys) |
| `screen.py`, `png.py` | screenshots and crops; PNG reading and writing |
| `render_check.py` | did the game render: image check, frozen-window check, GL errors in the log |
| `ocr.py` | optional OCR of a cropped screenshot |
| `ui/components/`, `ui/pages/` | what is drawn: one module per screen component (e.g. `menu_list.py`) and per game screen (e.g. `title_menu.py`) |
| `envinfo.py`, `xtool.py`, `pytest_helpers.py` | machine details for the report, X tools for host mode, `enforce()` |
