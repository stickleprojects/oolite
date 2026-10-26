# Test Migration Plan: moving the wmtest-py tests to readable, fast, screen-verified scenario tests

Goal: tests that read like the scenario (launch, wait for the splash, wait for the menu, check the screen, press keys, check again),
drive the game by a fast reliable mechanism, and *independently verify* what is on screen (cropped screenshot + OCR), because the game can
believe the menu is showing while the window is blank or frozen (a failure seen on real hardware; today's render/keys tests pass 160/160 on base too).

## Problems with the current tests (evidence: the 2026-10-26 X11 matrix run, results/*-render-x11.*)
1. `test_game_renders` / `test_game_responds_to_keys` cannot fail on a bad build: only "some pixels changed". They cannot tell a frozen or blank window from a working one.
2. Steps are hidden in fixtures, `oolite_test_framework/outcomes.py`, `scenarios.py` and `plugin.py`; a test body is one `enforce(...)` line.
3. Fixed waits: 14 s startup sampling, 2 s stop x3, 3 s render gap. About 68 s per run, so the X11 matrix is ~8.4 h.
4. F12 toggle fails 120/160 on both builds (harness problem, not diagnosed); the report calls it "not run".
5. Debian image has no `cvt`, so mutter/kwin 2head never ran (fix in docker/Dockerfile.debian, image not rebuilt).

## Target API (what a test looks like)
```python
def test_title_menu_is_displayed_and_responds(game):
    app = game.launch()
    app.wait_until_ready("splash")                   # driver: fast, pluggable
    app.wait_until_ready("title menu", timeout=10)
    app.verify_screen("title menu")                  # optional OCR on a cropped screenshot; SKIP with reason if no OCR
    assert app.window.is_framed and app.window.has_focus
    app.send_keys("Down", "Down")
    app.verify_screen("title menu", selected=3)      # optional
    assert app.screen_changed()                      # pixel-change fallback, always available
```
Two layers, kept apart:
- **Driver** (always on, fast): X key events (xdotool/python-xlib), Debug Console `guiScreen` (port 8563, as upstream tests/launch_snapshot.py), log lines.
  Chosen per environment; `wait_until_ready` returns as soon as the state is true (replaces fixed waits).
- **Verifier** (optional): crop the window screenshot to a named region, OCR with tesseract, compare to expected text/selected row.
  Missing tesseract = SKIPPED with a reason, never a failure.

## Phases (each ends green on `python3 -m pytest tests/unit` and a 1-run `--quick` smoke)
Rule: do not edit the harness while a queue/run is using it.

1. **Prep (no behaviour change).** Rebuild `wmtest-py-debian` (xcvt) and confirm mutter/kwin 2head start. Add `tesseract-ocr` (+ language data) to the three Dockerfiles; no new Python packages (call the CLI). Keep PNG decode in stdlib `oolite_test_framework/render.py`.
2. **Calibrate crops.** From saved screenshots (results/*.shots, results/hw-shots) define named regions (`title menu`, `splash`) as fractions of the window, one table in `oolite_test_framework/regions.py`. Prove OCR reads the menu entries on base screenshots at 1280x720 and one other size; prove the selected row is detectable (row brightness/colour vs OCR) and record the method.
3. **Driver layer.** Add `oolite_test_framework/driver.py` (`wait_until_ready`, `send_keys`) with X-key and Debug-Console backends; unit-test with fakes like test_scenarios.py. Measure that it removes the 14 s wait (target: run time ~68 s to ~35 s).
4. **Verifier layer.** `oolite_test_framework/verify.py`: `verify_screen(region, expect_text=None, selected=None)` returning (outcome, reason); SKIP when tesseract is missing. Unit-test with the saved PNGs (positive cases) and a blank/frozen/splash-only PNG (must FAIL).
5. **Negative control (the point of all this).** Run the new menu test against a build known to show a frozen or transparent window and against a known-good build: it MUST fail on the first and pass on the second. If it passes on the bad build, the test is not good enough; do not proceed.
6. **Migrate the tests one at a time**, old and new side by side until the new one passes the negative control:
   `test_game_renders` -> `test_title_menu_is_displayed`; `test_game_responds_to_keys` -> `test_title_menu_responds_to_keys`;
   then has_frame/gets_focus/centred to use `wait_until_ready` instead of the 14 s sample (keep the 14 s sampling only as a fallback cap).
   Remove each old test only after its replacement is green. Update README ("Add a test") and the example report.
7. **F12 toggle.** Diagnose why it fails on every build tested (key not delivered? wrong window? timing), fix or mark NOT MEASURABLE with the real reason; fix the report so "toggle not run" is only printed when it was not run. Re-check mutter 2head.
8. **Speed.** Stop the game by waiting for process exit (cap 2 s) instead of a fixed sleep; share one launch where possible.
9. **Validate and re-baseline.** 1-run smoke per environment, then the matrix (X11, then Wayland) with the new tests. Re-run the control-vs-candidate comparison; archive old results as `*-old-framework`. Record in STATUS.md and REMAINING.md.
10. **Game-code support (see "adjustments to game code").** Phase 3's driver should read the new screen-change and keypress log lines as its fast readiness signal, and the splash tests (steps 3-4 there) depend on the splash timeout and wait-for-keypress options. Land and review the game changes first; they must be off by default so normal play is unchanged, and the harness must SKIP (not fail) on builds without them.
11. **Hardware parity.** Run the same scenario test on the live desktop (`--host`) so the manual hardware checklist and the automated test agree; a checklist item that cannot be automated stays in the checklist.


## adjustments to game code
### To support measuring the splash
1. add option to wait for keypress on splash (so we can fast fwd through it after verify)
2. add option set timeout on splash (so we can make it longer and take screenshots)
3. add specific test "splash appears and disappears after timeout", and use the timeout setting to verify it appears, wait until timeout (say 3 secs) and verify menu appears. verify via screenshots
4. add specific test "splash appears and keypress dismisses it to main menu" and use the wait-for-keypress setting, verify splash appears wait for some time and verify it disappears after keypress. verify with screenshots

### augment logging for keypresses and active screens
1. add logs for gui or enhance the debugs telemetry for keypresses and menu items
2. add logs or telemtry when switching screens and ideally record from/to but at least record the name or type of the new screen


## Definition of done
- New menu tests FAIL on the known-bad build and PASS on a known-good build (negative control), in Docker and on hardware.
- Matrix run time at least ~40% lower than 68 s/run, with the same frame/focus/centred verdicts as the old tests on the control and candidate builds.
- Unit tests green; README and report text updated; old tests removed.

## Risks / unknowns
- OCR on Oolite's font and the spinning-ship background may be unreliable: mitigate by cropping to the menu strip and thresholding; fall back to row-highlight detection; verifier stays optional.
- Selected row is not exposed to JS (src/Core/GuiDisplayGen.m `selectedRow`); the game-code changes below (screen/keypress logging) give the tests a way to read it, so a separate hook is no longer needed.
- Game-code changes touch the game itself: keep them default-off, small and separately reviewable, and test that default behaviour (splash length, no extra log noise) is unchanged.
- Debug Console needs the DebugOXP in the AppImage and an open port; unverified inside the AppImage and under Wayland. X key events remain the default driver.
- Native Wayland has no X key injection or window grab in the harness; those environments may only support the verifier via compositor screenshots, or stay NOT MEASURABLE.
- Tesseract adds image size; the Wayland image is already 4 GB.


## Issue: separate running tests from comparing builds (scope creep in wmtest)
**Problem.** `wmtest` takes several builds in one command (`base:... opt2fix:...`, `--control`, `--candidates`) and its pytest plugin parametrises every test over builds. Running tests and comparing two builds are fused: the control/candidate idea leaks into the plugin (`case.label`, per-build session restarts), the raw file format and the run loop. A test should only test the AppImage it is given; comparison is an extra on top.

**Target: three layers, each usable alone**
1. **Tests** (`tests/`): pytest, run against ONE AppImage in ONE environment, no knowledge of other builds, controls or candidates. `pytest tests --wmt-app path/to/X.AppImage --wmt-env marco --wmt-screen 3840x1080` works with no coordinator. Output: pass/fail/skip per test and one results file for that run.
2. **Coordinator** (`wmtest run`): takes ONE AppImage and a list of environments x screens x runs, starts each environment, runs the tests layer in it, and collects everything into one result set (a folder, e.g. `results/<name>/` with the raw lines and screenshots). It never compares. It can be run many times, once per AppImage, each with its own result set name.
3. **Comparison** (`wmtest compare`): takes two (or more) existing result sets, one marked as the control, and produces the verdicts (WORKS/FIXED/STILL BROKEN/REGRESSED...). `oolite_test_framework/verdict.py` is already close to this (it reads raw files); it must stop depending on anything from the run.

**Work**
- Plugin: drop build labels from test ids and fixtures; one `--wmt-app`; the case id is env + screen + run. Remove per-build session restarts from `SessionManager` (one build per invocation).
- Result set format: a self-describing folder or file with a header (app path, label, build date, environment, tool version). Keep the current RESULT/TEST/WMVER/HARD lines inside it, so `verdict.py` and the unit tests keep working; the label comes from the header, not from every line.
- Coordinator (`hostrun.py`): single app, `--name` names the result set. Convenience wrapper `wmtest run-all A B C` may loop the coordinator, but only as a loop.
- Compare command: `wmtest compare --control results/base --candidate results/opt2fix [--registry ...]`; the report text now in the run summary moves here. Queue scripts (`opt2fix-queue2.sh`) become: run base, run opt2fix, compare.
- README: three sections (write a test, run tests, compare runs). CLI: keep `./wmtest base:... opt2fix:...` working for a deprecation period by mapping it to run + run + compare.
- Tests: unit tests for each layer separately (plugin with one app; coordinator with a fake runner; compare from two saved result sets). The existing verdict tests become the compare tests.

**Done when:** a test run produces a result set with no mention of control or candidate; two result sets from separate invocations compare to the same verdicts the combined run gave on the saved 2026-10-26 data (`results/opt2fix-render-x11.*`); the plugin has no code path that handles more than one build. Do not edit the harness while a queue is running.
