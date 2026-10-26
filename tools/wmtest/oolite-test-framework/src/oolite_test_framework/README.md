# oolite_test_framework (package)

- `plugin.py` pytest plugin: options (`--wmt-*`), fixtures (`launched_game`, `fresh_game`, `app`, `env_session`), result recording. `pytest_helpers.py`: `enforce()`.
- `hostrun.py` the orchestrator behind `./wmtest` (Docker, mounts, report). `verdict.py` statistics and report. `rawfmt.py` raw result format. `registry.py` + `../../environments.toml` the environments.
- `session.py`, `probes.py`, `scenarios.py`, `checks.py`, `outcomes.py` start the display/WM, observe the window, record launches, judge the results.
- `app.py` scenario-style handle on a running game. `screen.py`, `render.py`, `ocr.py` screenshots, PNG reading and optional OCR.
- `ui/components/` one module per component (reads what is drawn, e.g. `menu_list.py`). `ui/pages/` one module per game screen (expected content, e.g. `title_menu.py`).
