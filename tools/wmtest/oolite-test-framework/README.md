# oolite-test-framework: reference

**New here? Start with [the wmtest README](../README.md)**: it explains the kinds of test run and which command to use. This page is the
reference: every option, the output files, exit codes, adding a window manager or compositor, and how tests use the running game.

Nothing is installed on your machine. The host needs only **python3 (stdlib)** and **Docker**; pytest and python-xlib live inside the
pinned images. The entry `./wmtest` is stdlib Python in the style of upstream's `tests/launch_snapshot.py`, so it can later be hooked
into `mk.sh` / their CI.

## Layout
- `src/oolite_test_framework/`: the framework (see its README). `tests/`: tests of the framework. `docker/`: images. `environments.toml`: the registry.
- `../tests/` (next to this folder): the tests of the game, split into `app/`, `environments/`, `ui/`.

## Run
    ./wmtest mine:/path/Oolite.AppImage                                                # one build, the X11 window managers
    ./wmtest base:/path/Oolite-base.AppImage fix:/path/Oolite-pr.AppImage            # compare two builds
    ./wmtest base:A fix:B --wayland --host --toggle                                    # + headless Wayland compositors + your live desktop
    ./wmtest base:A fix:B --env marco,mutter --runs 10 --screens 3840x1080,2head
    ./wmtest --list                                                                    # the environments
Every run needs `--desc "what this run is for"` (or `--desc-file PATH`); it is left out of the examples here for width.
`--env kwin-xwayland-headed` runs KWin as a window on your desktop (GPU passed in) so screenshots include KWin's title bars; F12 toggle runs save
before/fullscreen/after screenshots in `<name>.shots/`. It is not part of `--wayland`; name it with `--env`.
With two or more builds the first label is the control. Images are built on first use (1-2 GB each, minutes; logs in the output dir). AppImages run with
`APPIMAGE_EXTRACT_AND_RUN=1`, so FUSE is not needed. No Docker: those cells become "not available: docker missing" rows; `--host` still works.
`--host` opens real game windows on your desktop (about 17 s per run): do not touch mouse/keyboard; it asks first (`--no-prompt` skips the
question and waits 5 s, and records unanswerable native-Wayland checks as "not tested").

## Quick runs
    ./wmtest base:A fix:B --env marco --quick                 # 1 run, first screen, launches + renders only (about 1 min)
    ./wmtest base:A fix:B --env marco,mutter --tests has_frame,game_responds_to_keys
`--env` takes one or more environment names. `--tests` takes test names (prefix `test_` optional) and `--quick` is a preset
(`game_launches,game_renders`, 1 run, `--minruns 1`). A partial run adds a "PARTIAL RUN" line to the report so it is never read as a full pass.

## Read the output (`results/<name>.*`)
`<name>.md` (headline PASS / FAIL / NEEDS MORE RUNS, summary, per-cell counts, verdicts, live-desktop table), `<name>.raw` (one RESULT line per
run, one TEST line per test with its outcome and reason, plus WMVER/HOSTENV/SKIP lines), `<name>-env.txt`, `<name>.parts/` (per-container raw
output and JUnit XML), `<name>.logs/` (the game's Latest.log for every launch), `<name>.shots/` (screenshots).
The console ends with `Result: N passed, M failed` for one build, or the number of REGRESSED cells when comparing, then `PASS` or `FAIL`. NA / not tested is never a failure. Exit status 1 only if a candidate REGRESSED.
Because the verdict step re-judges recorded geometry (`outer=`, `mon=` fields), a different tolerance needs no re-run:
`./wmtest --report-only X.raw --out X.md --tol 60`.

## Describing a run
    ./wmtest base:A opt1:B --desc "opt1: window created bordered+resizable; checks the splash is centred and the game gets focus" \
        --note base="unmodified 1.93.1-229" --note opt1="opt1 + bordered/resizable window from creation"
`--desc-file PATH` takes longer markdown. The report starts with a **Purpose** section (`--desc` or `--desc-file` is required, so every results file says what it was for) and a **Builds**
table (label, AppImage file, short sha256, note). The same text is stored in the `.raw` (`PURPOSE` / `BUILD` lines) and `-env.txt`, so a returned
results file is self-describing; in `--quiet` mode it only goes into the files.

## Using it from scripts
    ./wmtest base:A fix:B -q            # prints only PASS or FAIL; report files still written; errors go to stderr only
    ./wmtest base:A fix:B --strict -q   # SUSPECT and STILL BROKEN also fail
The report is written to `results/wmtest-<YYYYmmdd-HHMMSS>-<candidates>.md` (with `.raw` and `-env.txt` of the same stem, and `.parts/`
for per-container raw output); `--report PATH` overrides the path (the stem follows), `--out DIR` changes only the directory. The path is
printed at the end in normal mode. **Exit codes (stable):**
- `0` PASS: nothing REGRESSED (SUSPECT, STILL BROKEN and NEEDS MORE RUNS do not fail; they show in the report).
- `1` FAIL: any REGRESSED; with `--strict` also any SUSPECT or STILL BROKEN.
- `2` could not run: bad arguments or AppImage path, Docker missing/unusable while Docker environments were requested (the report is still
  written, with "not available" rows), or nothing was measured at all.

## How it is built
- `environments.toml`: the registry. **One `[env.<name>]` table per window manager / compositor.**
- `src/oolite_test_framework/session.py` starts/stops the display server + WM (readiness: `_NET_SUPPORTING_WM_CHECK`, or the Wayland socket).
- `src/oolite_test_framework/probes.py`: one interface (`observe()` -> framed / focused / outer geometry / monitor): `x11` (python-xlib, xwininfo/xprop/xdotool fallback),
  `kwin` (scripting over D-Bus), `sway` (IPC), `ask` (y/n questions), `none` (NA).
- `src/oolite_test_framework/scenarios.py`: startup sampling and the F12 toggle, written once. They only record. `src/oolite_test_framework/checks.py`: pure frame/focus/centred functions.
- the game tests in `../tests/` (app/, environments/, ui/) + `src/oolite_test_framework/plugin.py`: one pytest function per behaviour (has_frame, gets_focus, splash_centred, game_window_centred, f12_toggle, ...); see Add a test.
- `src/oolite_test_framework/verdict.py`: statistics and the report (ported from the bash harness' verdict.py). `src/oolite_test_framework/hostrun.py`: the stdlib orchestrator.
- Timing: 0.5 s sampling for 14 s, post sample 2 s after the first size change, tolerance 40 px. One container per (environment, screen)
  runs all builds, with a fresh session per build; the toggle is skipped on environments without an X11 probe.
- Keys: X11 key events (XTEST) by default; `keys = "fakeinput"` in an environment sends them through KWin's fake-input protocol instead,
  because XTEST keys never reach clients under headless KWin.

## Add a window manager (one entry, no test changes)
Add its package to the image Dockerfile, then in `environments.toml`:

    [env.fvwm]
    family = "fvwm"
    session = "X11"
    image = "arch"
    kind = "x11"
    start = ["fvwm"]
    version_cmd = "fvwm --version"
    probes = ["x11"]

Then `./wmtest base:A fix:B --env fvwm`. A compositor adds `kind = "wayland"`, `start` with `{w}`/`{h}`, optional `files`, `env`, `ready_socket`,
`probes = ["kwin:framed,focused", "x11"]` (see the file's header comment). Unit tests check the registry parses.

## Add a test
One function in a file under `../tests/` (app/, environments/ or ui/) (plus, if it needs a new rule, a small check function in `src/oolite_test_framework/outcomes.py`). It runs for every
environment x build x run with ids like `test_gets_focus[marco-x11-opt1-run3]`; select with `-k` or the markers `-m family_kwin`,
`-m session_xwayland`, `-m env_marco`. WM-specific tests: `@pytest.mark.only_wm("marco")`.

**Launch rules (fixtures are opt-in): request `launched_game` to share one launch; request `fresh_game` to get your own; request neither for no launch.**
- Read-only checks (frame, focus, centred) take `launched_game`: the game is started ONCE per (env, build, run) and they all inspect that record.
- A test that changes game state (the F12 toggle) takes `fresh_game`, which launches the game for that test alone (`fresh_game.toggle()`).
- Tests that need no game (environment up, monitors, AppImage readable) request only `env_session` or `case`; mark them `@pytest.mark.once_per_build`
  to run for run 1 only. `@pytest.mark.needs_toggle` / `needs_x11` / `needs_keys` skip with a reason when the data/environment can't support them.

pytest is the source of truth: **pass / fail per item; `pytest.skip(reason)` means NOT TESTED / NOT MEASURABLE and the reason text is reused in the
report.** Container runs also write JUnit XML (`<stem>.parts/*.xml`) for CI. The plugin (`src/oolite_test_framework/plugin.py`) writes the raw file (RESULT lines,
RESULT-compatible, plus TEST lines with outcomes and skip reasons, WMVER, HARD) and a k6-style pass-rate summary; the host-side report
(`src/oolite_test_framework/verdict.py`) compares candidate and control per test (columns of the coverage table are the test names). Old raw files can still be re-reported.
Offline unit tests of the framework: `python3 -m pytest tests -q` from this folder (fake launch fixtures, no display, no Docker).

## Sharing the running game
Fixtures are opt-in, and `conftest.py` makes them visible to every test below it (`src/oolite_test_framework/plugin.py` is loaded from the root `conftest.py`).
- **One launch per env x build x run.** `launched_game` is module-scoped and parametrized by `case`; pytest reorders the tests so all tests of one
  case run together, then the game is stopped and the next case starts. Tests that don't request it never launch a game (`env_session`/`case` only).
- **Read-only by default.** Checks just look at the shared record: `def test_gets_focus(launched_game): enforce(outcomes.check_focus(launched_game))`.
- **A sharing test MAY change game state if it puts it back**, but only through a restoring construct, never "at the end of the test body":

      def test_survives_resize(launched_game):
          with launched_game.temporarily(lambda: resize(launched_game, 800, 600), lambda: resize(launched_game, 1280, 720)):
              assert still_runs()          # the restore runs even if this assert fails

  (or a `yield` fixture / `request.addfinalizer`).
- **Dirty detection.** After every test that used `launched_game`, a cheap baseline check runs: game alive, same window geometry / fullscreen
  state, same focus. If it differs, the launch is marked dirty, relaunched before the next test, and the report gets a warning
  "state not restored by test_x" (`WARN` raw line, "Warnings" section). Nothing is skewed silently.
- **When in doubt use `fresh_game`**: it launches the game for that one test (`fresh_game.toggle()` for F12). Use it when a change cannot be undone
  reliably (fullscreen toggles, quitting, anything that touches the splash/startup path).
- **No fixture = no launch.**
- **Tests run sequentially, on purpose.** Do not use pytest-xdist: each container has one display and one window manager, and focus and timing are
  global; running tests in parallel would disturb the very thing measured. `-n 2` or more is refused with an error.

## Requirements, cost
Docker + python3 >= 3.11. About 30-70 s per run depending on the tests (startup sampling alone is 14 s); a run is one environment x screen x
build x `--runs`, so the default comparison (6 window managers x 2 builds x 10 runs) takes several hours per screen size.
Software GL: do not load the machine meanwhile, the Marco bug is a race.

## Host mode
The game runs **on the host** (your libraries and drivers), started by the stdlib orchestrator. For X11 and XWayland rows only the measuring
tools (python-xlib, xprop, xdotool, xrandr; `python3 -m oolite_test_framework.xtool`) run in a helper container that shares your X display
(`--net=host`, X socket, xauth): nothing is installed on the host, and if the host already has the X tools they are used instead
when Docker is unavailable. Native Wayland rows are measured by KWin D-Bus or sway IPC where available, otherwise 3 y/n questions
(`--no-prompt`: "not tested"). Under XWayland on KDE, frame/focus are cross-checked with KWin.

## Licence
GPL-2.0-or-later (Oolite is GPL v2; source headers "or any later version"). It only runs the AppImage as a separate program.
