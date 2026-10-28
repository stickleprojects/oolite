# oolite-ui-test-framework

The tool behind the Oolite UI tests: the `uitest` command, the Docker images, the list of test environments and the pytest plugin the
tests are written with.

**New here? Start with [`tests/ui/README.md`](../../tests/ui/README.md).** It explains the kinds of test run and which command to use.
This page is the reference: every option, the output files, exit codes, adding an environment, writing tests, and how it works.

The host needs only **python3 3.11 or newer (standard library)** and **Docker** (host mode also makes a venv of its own with pytest, see
[Host mode](#host-mode)); pytest, python-xlib and the window managers live in
pinned Docker images. `uitest` is plain stdlib Python, so it can later be hooked into `mk.sh` or CI.

## What is in this folder

| Path | What it is |
|---|---|
| `uitest` | the command |
| `environments.toml` | the test environments: one `[env.<name>]` table per window manager or compositor |
| `docker/` | one Dockerfile per family of environments (see its README) |
| `src/oolite_ui_test_framework/` | the framework itself (see its README) |
| `tests/` | the framework's own offline tests (see its README) |
| `examples/` | an example report |
| `results/` | where runs write their results (not in git) |

The tests of the game are in [`tests/ui/`](../../tests/ui/) at the repo root.

## Running

Three layers, each usable on its own:

1. **Tests**: pytest with the plugin, against **one** AppImage in **one** environment. Runs inside the Docker images; it knows nothing
   about other builds: `pytest tests/ui --ui-env marco --ui-app=/app/Oolite.AppImage --ui-label mine`.
2. **Run** (`uitest run`): the coordinator. Tests one AppImage in every requested environment x screen and writes one **result set**
   (`results/<name>.raw` with a `SET` header line naming the AppImage, its label, sha256, build date, environments and tool version,
   plus `.md`, `-env.txt`, `.shots/`, `.logs/`). It never compares.
3. **Compare** (`uitest compare`): takes saved result sets, one as the control, and gives the verdicts (FIXED, REGRESSED, ...).

        ./uitest run base:/path/Base.AppImage --name base            # one result set per build ...
        ./uitest run fix:/path/Fix.AppImage --name fix
        ./uitest compare --control results/base --candidate results/fix   # ... compared afterwards (results/compare-<date>-fix.md)
        ./uitest base:/path/Base.AppImage fix:/path/Fix.AppImage        # shorthand: run each build, then compare; the first is the control
        ./uitest --list                                                  # the environments

Each build is `label:path`. Every run needs `--desc`; it is left out of the examples on this page. The shorthand with several builds
writes `results/<name>-<label>.*` per build and the comparison as `results/<name>.*`. `uitest compare` takes `--candidate` more than
once, `--report PATH`, `--desc`, `--minruns`, `--strict` and `-q`; a result set is given as `results/<name>` or `results/<name>.raw`.

| Option | What it does |
|---|---|
| `--desc TEXT` / `--desc-file PATH` | **required**: what the run is for; shown as Purpose at the top of the report |
| `--name NAME` | name of the result files (`results/NAME.*`); default `uitest-<date>-<label>` (`uitest-<date>-<candidates>` for the shorthand) |
| `--note LABEL=TEXT` | a note for one build in the report's Builds table (repeatable) |
| `--env A,B` | environments to run (default: the six X11 window managers; `./uitest --list` shows all) |
| `--wayland` | also the headless Wayland compositors |
| `--host` | also your own desktop (see [Host mode](#host-mode)); `--env ""` runs only that |
| `--toggle` | also run the F12 fullscreen round trip |
| `--tests a,b` | only these tests (the `test_` prefix is optional); the report then says PARTIAL RUN |
| `--quick` | smoke preset: 1 run, first screen size, only `game_launches,title_menu_is_displayed` unless `--tests` is given |
| `--runs N` | runs per environment and build (default 10); `--host-runs N` for your desktop (default 5) |
| `--screens WxH,2head` | screen sizes (default `3840x1080`; `2head` = two 1920x1080 monitors) |
| `-q` | print only `PASS` or `FAIL`; errors go to stderr; the report files are still written |
| `--strict` | SUSPECT and STILL BROKEN also count as FAIL |
| `--control L` / `--candidates L,M` / `--equiv L` | who is compared with whom (default: first build is the control, the rest are candidates); an `--equiv` build is expected to behave like the control, so differences show as DIFFERS |
| `--minruns N` / `--tol PX` | runs needed for a verdict (default 10) / centring tolerance in pixels (default 40) |
| `--out DIR` / `--report PATH` | results directory / exact report path (the other files take the same stem) |
| `--report-only RAW` | re-make a report from an existing `.raw` file, e.g. with another `--tol`, without re-running |
| `--no-prompt` | host mode: do not ask questions; unanswerable checks are recorded as not tested |

Images are built on first use (1-2 GB each, a few minutes; the build log goes into the results directory). AppImages run with
`APPIMAGE_EXTRACT_AND_RUN=1`, so FUSE is not needed. Without Docker, Docker environments are reported as "not available"; `--host`
still works.

**Headed KWin.** `--env kwin-xwayland-headed` runs KWin as a window on your desktop (the GPU and your X display are passed into the
container), so screenshots include KWin's own title bars; the F12 test saves before / fullscreen / after screenshots. It is not part of
`--wayland`. Do not touch the mouse or keyboard while it runs.

## Output files (`results/<name>.*`)

| File | Contents |
|---|---|
| `<name>.md` | the report: Purpose, Builds, headline, **What ran where** (environment x test grid: passed / measured runs, `–` = not run, then each skip reason and where it applied), verdicts, counts per environment, live-desktop table |
| `<name>.raw` | one RESULT line per run (with `start`, a UTC timestamp, and `startup_secs`), one TEST line per test (outcome, `start`, `secs` over setup + call + teardown, reason), plus WMVER / HOSTENV / SKIP lines |
| `<name>-env.txt` | the machine and tool versions |
| `<name>.parts/` | raw output and JUnit XML per container |
| `<name>.logs/` | the game's `Latest.log` for every launch (key presses are logged) |
| `<name>.shots/` | screenshots |

The console ends with `Result: N passed, M failed` (one build) or the number of REGRESSED cells (comparison), then `PASS` or `FAIL`.
NOT TESTED and NOT MEASURABLE are never failures.

**Exit codes (stable):**
- `0` PASS: one build: every test passed; comparison: nothing REGRESSED (SUSPECT, STILL BROKEN and NEEDS MORE RUNS show in the report but do not fail).
- `1` FAIL: one build: a test failed; comparison: something REGRESSED, or with `--strict` is SUSPECT or STILL BROKEN.
- `2` could not run: bad arguments or AppImage path, Docker unusable while Docker environments were requested (the report is still
  written, with "not available" rows), or nothing was measured.

## Environments

`environments.toml` lists them; its header comment documents every key. Kinds:

- **x11**: an X server (Xvfb, or Xorg with two dummy monitors for `2head`) plus the window manager.
- **wayland**: a compositor; with session `XWayland` the game uses its Xwayland, with `Wayland native` it uses SDL's Wayland driver.
  `headed = true` runs it as a window on your desktop.
- **host**: your own desktop; nothing is started.

How each environment is observed is set by `probes`: `x11` (python-xlib, or xwininfo/xprop/xdotool), `kwin` (KWin scripting over
D-Bus), `sway` (IPC), `ask` (yes/no questions), `none`. How keys are sent is set by `keys`: X11 key events (default), or `fakeinput`
(KWin's fake-input protocol, needed under KWin on Wayland, where X11 key events never reach the game).

**Add a window manager** (no test changes): add its package to the right Dockerfile, then a table such as

    [env.fvwm]
    family = "fvwm"
    session = "X11"
    image = "arch"
    kind = "x11"
    start = ["fvwm"]
    version_cmd = "fvwm --version"
    probes = ["x11"]

and run `./uitest mine:/path/Oolite.AppImage --env fvwm`. A compositor uses `kind = "wayland"`, a `start` command with `{w}`/`{h}`
for the screen size, and optionally `files`, `env`, `ready_socket` and `probes = ["kwin:framed,focused", "x11"]`. The unit tests
check that the file parses.

## Add a test

Add a function to a file in [`tests/ui/`](../../tests/ui/) (`app/`, `window/` or `screen/`), plus, if it needs a new rule, a small check
function in `src/oolite_ui_test_framework/pass_fail.py`. It runs for every environment x run of the one build under test, with ids like
`test_gets_focus[marco-x11-run3]`. Select with `-k` or the markers `-m family_kwin`, `-m session_xwayland`, `-m env_marco`;
`@pytest.mark.only_wm("marco")` limits a test to some environments.

**Launch rules: fixtures are opt-in.**
- `launched_game`: share one launch. Read-only checks (frame, focus, centred) use it; the game starts once per (environment, build,
  run) and every such test inspects that record.
- `fresh_game`: a launch of your own, for tests that change game state (the F12 toggle: `fresh_game.toggle()`).
- `app`: a launch of your own as a scenario handle (wait for a screen, look at it, press keys); see `app.py` and `ui/pages/`.
- `env_session` or `case` alone: no game, for tests such as "the environment started" or "the AppImage is readable". Mark them
  `@pytest.mark.once_per_build` to run once.
- `@pytest.mark.needs_toggle`, `needs_x11`, `needs_keys` and `needs_mouse` skip with a reason when the run or environment cannot support the test.

pytest decides: each test passes or fails; `pytest.skip(reason)` means NOT TESTED / NOT MEASURABLE, and the reason appears in the report.
The plugin writes the raw file (RESULT, TEST, WMVER, HARD lines) and a pass-rate summary; `report.py` makes the report from it.

**Sharing the running game.**
- pytest reorders the tests so all tests of one (environment, build, run) share one launch; then the game is stopped and the next starts.
- A test that uses `launched_game` must leave the game as it found it. To change state and put it back, use a restoring construct, never
  code at the end of the test body:

      def test_survives_resize(launched_game):
          with launched_game.temporarily(lambda: resize(launched_game, 800, 600), lambda: resize(launched_game, 1280, 720)):
              assert still_runs()          # the restore runs even if this assert fails

- After every such test a quick check compares the game with its baseline (alive, same geometry and fullscreen state, same focus). If it
  differs, the game is relaunched and the report warns "state not restored by test_x".
- When in doubt, use `fresh_game`.
- Tests run one at a time on purpose: one display and one window manager per container, and focus and timing are global. pytest-xdist
  with more than one worker is refused.

## How it works

- `uitest` calls `hostrun.py`, which builds the images and starts one container per (environment, screen size). The framework is
  mounted at `/uitest` and the game tests at `/gametests`.
- Inside, pytest runs the game tests with the plugin (`plugin.py`). `session.py` starts the display server and window manager and
  waits until it is ready (`_NET_SUPPORTING_WM_CHECK`, or the Wayland socket).
- `scenarios.py` launches the game, samples the window every 0.5 s, takes a sample 2 s after the first size change, and stops once
  the window has not changed for 3 s after that (`--ui-settle`, 0 = always 14 s) or at 14 s; then it runs the F12 round trip. It only records; `geometry.py` and `pass_fail.py` judge.
- `report.py` turns the raw file into the report (one-sided Fisher test between control and candidate).
- The raw results keep the `wm=` field name (the environment) so that older results stay readable.

## Host mode

`--host` runs the game **on your desktop** (your libraries and drivers) with **the same pytest tests** as the Docker environments:
startup checks, title menu, keys, mouse clicks and, with `--toggle`, the F12 round trip.

- **pytest comes from a venv of its own**, `tools/oolite-ui-test-framework/.venv-host/` (not in git), made on first use with
  `python3 -m venv` and pytest 9.0.2 from PyPI (needs the network once; log in `results/host-venv.log`). Nothing is installed into the
  host's own python. If the venv cannot be made, only the startup checks run and the report warns which tests did not.
- **X11 and XWayland:** the game runs on the host; window state, screenshots, keys and clicks go through one long-lived
  `xtool serve` in a helper container that shares your X display (`xtool.py`), so python-xlib and xdotool need not be on the host. Key
  repeat is switched off for the run (a held key must be one press, as in the containers) and switched back on afterwards.
- **Native Wayland:** measured through KWin D-Bus or sway IPC where available; otherwise you are asked up to three yes/no questions
  (`--no-prompt`: recorded as not tested). There are no screenshots there, so the screen tests are NOT MEASURABLE, as in the headless
  native environments.

On KDE under XWayland, frame and focus are cross-checked with KWin. About 20 s per startup run, plus about 20 s for each screen test;
the pointer moves and keys are pressed on your desktop, so do not touch the mouse or keyboard.

## Time and machine load

About 30-70 s per run, depending on the tests (startup sampling alone takes 14 s). Runs = environments x screen sizes x builds x
`--runs`, so a default comparison (6 window managers x 2 builds x 10 runs) takes several hours per screen size. The game renders in
software and the bug is a race, so do not load the machine while a long run is going.

## Licence

GPL-2.0-or-later, like Oolite. The framework only runs the AppImage as a separate program.
