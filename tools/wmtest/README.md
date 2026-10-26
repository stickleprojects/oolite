# wmtest: automated tests of the Oolite game window

These tests start an Oolite AppImage under many window managers and Wayland compositors and check what a player would notice:
the window gets a title bar and keyboard focus, it is centred, it survives the F12 fullscreen round trip, the title menu is drawn and
responds to keys. They were built for [OoliteProject/oolite#773](https://github.com/OoliteProject/oolite/issues/773), where the window
behaves differently depending on the window manager.

## What to read

1. **This page**: what the kinds of test run are, which one to use, and how to run it. Enough to run any test.
2. [`tests/README.md`](tests/README.md): if you want to write or change a test of the game.
3. [`oolite-test-framework/README.md`](oolite-test-framework/README.md): reference (every option, output files, exit codes, adding a window
   manager, test fixtures). Read it only when you need a detail.

## Before you start

- Linux with **Docker** and **python3 3.11 or newer**. Nothing else is installed on your machine: the window managers, pytest and
  the measuring tools live in Docker images, built automatically on first use (1-2 GB each, a few minutes).
- Run every command from `oolite-test-framework/`.
- Every run needs `--desc "what this run is for"`. It heads the report, so a results file always says why it exists.
- Give each run a `--name`; the results are then `oolite-test-framework/results/<name>.*`.

## Which run do I want?

| I want to know... | Run | Roughly |
|---|---|---|
| Does my build start and draw? (smoke test) | `./wmtest mine:/path/Oolite.AppImage --env marco --quick --desc "..." --name smoke` | 1 min |
| Does the title menu appear and respond to keys? | `./wmtest mine:/path/Oolite.AppImage --env marco --tests title_menu_shown_and_keys_move_selection --runs 1 --desc "..." --name menu` | 1 min |
| Does my build behave under every window manager? | `./wmtest mine:/path/Oolite.AppImage --toggle --desc "..." --name all-wms` (add `--wayland` for the Wayland compositors) | about 1 min per run; 10 runs per environment by default |
| Does my change fix the bug without breaking anything? | `./wmtest base:/path/Base.AppImage fix:/path/Fix.AppImage --toggle --desc "..." --name fix-vs-base` | the above, twice |
| What does KWin actually draw (title bars, fullscreen)? | `./wmtest mine:/path/Oolite.AppImage --env kwin-xwayland-headed --tests f12_toggle --toggle --runs 1 --desc "..." --name kwin-look` (opens a window on your desktop) | 1 min |
| Does it work on my own desktop, with my drivers? | `./wmtest mine:/path/Oolite.AppImage --env "" --host --desc "..." --name my-desktop` (opens game windows; don't touch; `--env ""` = no Docker environments) | about 20 s per run, 5 runs |
| I changed the framework itself: is it still right? | `python3 -m pytest tests -q` (no Docker, no game) | 40 s |

`--env` takes one or more environment names (`./wmtest --list` shows them all). `--tests` picks tests by name. `--runs` sets how
many times each environment is repeated. The last line of the output is `PASS` or `FAIL`; `-q` prints only that.

## Why there are several kinds of run

They answer three different questions, all with the same command and the same tests:

1. **Does this build work?** Give one AppImage. Each test passes or fails, and the run ends with `Result: N passed, M failed`.
2. **Does it work everywhere?** The #773 bug depends on the window manager and on timing (it is a race), so the same tests are repeated
   in many environments and several times in each. A single passing run proves little; the default is 10 runs per environment.
3. **Did my change fix it, and did it break anything?** Give two AppImages; the first is the control (normally the unmodified build).
   For each environment and test the report says WORKS, FIXED, STILL BROKEN or REGRESSED, using a statistical test on the repeated
   runs, so one unlucky run does not count as a regression. The run fails only if the candidate REGRESSED.

The tests of the game are in three groups (see [`tests/README.md`](tests/README.md)):

- **app**: the AppImage is valid and the game starts.
- **environments**: what the window manager does with the window: title bar, focus, centring, F12 round trip.
- **ui**: what the player sees, read from screenshots: the title menu is drawn and the selection moves when keys are pressed. These need
  screenshots of the game window, so they are reported as NOT MEASURABLE where that is impossible (the native Wayland environments).

## Where the game runs: headless, headed or your desktop

| | Headless (default) | Headed (`kwin-xwayland-headed`) | Your desktop (`--host`) |
|---|---|---|---|
| Where | inside Docker, on a virtual screen | inside Docker; KWin shows as a window on your desktop | directly on your desktop |
| Use it for | all routine and long runs: unattended, any screen size, repeatable, anyone with Docker gets the same result | seeing what KWin draws: screenshots include KWin's own title bars (before, during and after F12) | checking with real drivers and your own desktop |
| Needs | Docker | Docker, an X11 desktop, a GPU (`/dev/dri`) | your desktop; it may ask you yes/no questions |
| Limits | KWin's own decorations cannot be screenshotted (headless KWin crashes on screenshot requests), so the title bar is checked by asking KWin instead | do not touch the mouse or keyboard while it runs; the screen size is limited by your desktop (panels shrink it) | do not touch the mouse or keyboard; only your one desktop |

Use headless by default and headed when a headless result needs a look. Results from different kinds are not directly comparable
(different screen sizes and rendering).

Keys are sent the way each environment accepts them: X11 key events in X11 environments, KWin's fake-input protocol under KWin on
Wayland (X11 key events never reach the game there). This is chosen automatically per environment.

## Reading the results

Everything is in `oolite-test-framework/results/`:

- `<name>.md`: the report. Purpose and builds first, then the headline, then counts per environment and test.
- `<name>.raw`: one line per run and per test (`grep "outcome=failed" <name>.raw` lists failures with their reason).
- `<name>.logs/`: the game's own log for every launch (key presses are logged, so you can see whether a key reached the game).
- `<name>.shots/`: screenshots, where the run takes them.

NOT TESTED and NOT MEASURABLE are never failures; the report gives the reason.

## Folders

- `oolite-test-framework/`: the `wmtest` command, the Docker images, the list of environments (`environments.toml`) and the
  framework's own tests.
- `tests/`: the tests of the game.

Open work is tracked in this fork's GitHub issues.
