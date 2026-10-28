# Oolite UI tests

These tests check the game **from the outside, the way a player sees it**: they start an Oolite AppImage under many window managers
and Wayland compositors and check that the window gets a title bar and keyboard focus, is centred, survives the F12 fullscreen round
trip, and that the title menu is drawn and responds to keys. They were written for
[OoliteProject/oolite#773](https://github.com/OoliteProject/oolite/issues/773), where the window behaves differently depending on the
window manager.

They are separate from the game-logic tests (JavaScript run inside the game through the debug console, OoliteProject/oolite#772):
those check what the game does; these check what ends up on the screen.

## What to read

1. **This page**: the kinds of test run, which one to use and how to run it. Enough to run any test.
2. [`tools/oolite-ui-test-framework/README.md`](../../tools/oolite-ui-test-framework/README.md): the reference (every option, output
   files, exit codes, adding a window manager, writing tests). Read it when you need a detail or want to write a test.

## Before you start

- Linux with **Docker** and **python3 3.11 or newer**. Nothing else is installed on your machine: the window managers, pytest and the
  measuring tools live in Docker images, built automatically on first use (1-2 GB each, a few minutes).
- Run every command from `tools/oolite-ui-test-framework/`.
- Every run needs `--desc "what this run is for"`. It heads the report, so a results file always says why it exists.
- Give each run a `--name`; the results are then `tools/oolite-ui-test-framework/results/<name>.*`.

## Which run do I want?

| I want to know... | Run | Roughly |
|---|---|---|
| Does my build start and draw? (smoke test) | `./uitest mine:/path/Oolite.AppImage --env marco --quick --desc "..." --name smoke` | 1 min |
| Does the title menu appear and respond to keys and clicks? | `./uitest mine:/path/Oolite.AppImage --env marco --tests title_menu_is_displayed,title_menu_responds_to_keys,title_menu_item_can_be_clicked --runs 1 --desc "..." --name menu` | 1 min |
| Does my build behave under every window manager? | `./uitest mine:/path/Oolite.AppImage --toggle --desc "..." --name all-wms` (add `--wayland` for the Wayland compositors) | about 1 min per run; 10 runs per environment by default |
| Does my change fix the bug without breaking anything? | `./uitest base:/path/Base.AppImage fix:/path/Fix.AppImage --toggle --desc "..." --name fix-vs-base` | the above, twice |
| What does KWin actually draw (title bars, fullscreen)? | `./uitest mine:/path/Oolite.AppImage --env kwin-xwayland-headed --tests f12_toggle --toggle --runs 1 --desc "..." --name kwin-look` (opens a window on your desktop) | 1 min |
| Does it work on my own desktop, with my drivers? | `./uitest mine:/path/Oolite.AppImage --env "" --host --toggle --desc "..." --name my-desktop` (opens game windows and presses keys; `--env ""` = no Docker environments; the same tests as in Docker) | about 1 min per run, 5 runs |
| I changed the framework itself: is it still right? | `python3 -m pytest tests -q` (no Docker, no game) | 40 s |

`--env` takes one or more environment names (`./uitest --list` shows them all). `--tests` picks tests by name. `--runs` sets how
many times each environment is repeated. The last line of the output is `PASS` or `FAIL`; `-q` prints only that.

## Why there are several kinds of run

They answer three different questions, with the same command and the same tests:

1. **Does this build work?** Give one AppImage. Each test passes or fails, and the run ends with `Result: N passed, M failed`.
2. **Does it work everywhere?** The #773 bug depends on the window manager and on timing (it is a race), so the same tests are repeated
   in many environments and several times in each. A single passing run proves little; the default is 10 runs per environment.
3. **Did my change fix it, and did it break anything?** Give two AppImages; the first is the control (normally the unmodified build).
   For each environment and test the report says WORKS, FIXED, STILL BROKEN or REGRESSED, using a statistical test on the repeated
   runs, so one unlucky run does not count as a regression. The run fails only if the candidate REGRESSED.

## Where the game runs: headless, headed or your desktop

| | Headless (default) | Headed (`kwin-xwayland-headed`) | Your desktop (`--host`) |
|---|---|---|---|
| Where | inside Docker, on a virtual screen | inside Docker; KWin shows as a window on your desktop | directly on your desktop |
| Use it for | all routine and long runs: unattended, any screen size, repeatable, anyone with Docker gets the same result | seeing what KWin draws: screenshots include KWin's own title bars (before, during and after F12) | checking with real drivers and your own desktop |
| Needs | Docker | Docker, an X11 desktop, a GPU (`/dev/dri`) | your desktop, Docker for the measuring helper; pytest in a venv of its own (made on first use); it may ask you yes/no questions |
| Limits | KWin's own decorations cannot be screenshotted (headless KWin crashes on screenshot requests), so the title bar is checked by asking KWin instead | do not touch the mouse or keyboard while it runs; the screen size is limited by your desktop (panels shrink it) | do not touch the mouse or keyboard; only your one desktop |

Use headless by default and headed when a headless result needs a look. Results from different kinds are not directly comparable
(different screen sizes and rendering).

Keys are sent the way each environment accepts them: X11 key events in X11 environments, KWin's fake-input protocol under KWin on
Wayland (X11 key events never reach the game there). This is chosen automatically.

## Reading the results

Everything is in `tools/oolite-ui-test-framework/results/`:

- `<name>.md`: the report. Purpose and builds first, then the headline, then **What ran where**: a grid of environment x test
  (`3/3` passed, `1/3 ✗` failed, `–` not run) with the reason for every test that did not run, then the verdicts and counts.
- `<name>.raw`: one line per run and per test (`grep "outcome=failed" <name>.raw` lists failures with their reason).
- `<name>.logs/`: the game's own log for every launch. Key presses are logged, so you can see whether a key reached the game.
- `<name>.shots/`: screenshots, where the run takes them.

NOT TESTED and NOT MEASURABLE are never failures; the report gives the reason.

## In GitHub Actions

The **UI tests** workflow (`.github/workflows/ui-tests.yaml`) is separate from the main build pipeline and never blocks a build:

- **Framework tests** run on every push or pull request that changes `tests/ui/` or `tools/oolite-ui-test-framework/` (about 1 min).
- **UI tests** run headless against the Linux AppImage from the main build: automatically after each successful build of `master`
  (1 run per environment), or by hand under *Actions > UI tests > Run workflow*, where you choose the build, the AppImage flavour and
  the number of runs. There is one job per Docker image (X11 window managers on Arch, KWin and mutter on Debian, the XWayland
  compositors); each job's report is in its summary and the full results (raw lines, game logs, screenshots) are kept as an artifact.

Headed KWin and host mode need a desktop and a GPU, so they only run on your machine. CI machines are slower than a desktop and the
#773 bug is a race, so treat a single CI run as a smoke test; use 10 runs for a real comparison.

## The tests in this folder

| Folder | What it checks | Needs screenshots? |
|---|---|---|
| `app/` | the AppImage is a valid file and the game starts without crashing | no |
| `window/` | what the window manager does with the window: title bar, keyboard focus, centred splash and window, F12 round trip | no |
| `screen/` | what the player sees: the window draws, keys change the screen, the title menu is shown and its selection moves | yes |

Tests that need screenshots are reported as NOT MEASURABLE where none can be taken (the native Wayland environments).
`conftest.py` loads the framework's pytest plugin and `pytest.ini` puts the framework on the Python path.

**Adding a test:** add a function to the folder that fits, using the fixtures described under "Add a test" in the
[framework README](../../tools/oolite-ui-test-framework/README.md#add-a-test). Test names appear in the report, so do not rename a test
function without updating `oolite_ui_test_framework/pass_fail.py`.

Open work is tracked in the fork's GitHub issues.
