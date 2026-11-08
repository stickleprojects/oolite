# stages: the UI-test steps as scripts you can run by hand

Issue #80. Each step of a run is one bash script: start the desktop, launch the game, observe its window, collect logs, tidy up.
Any stage can be run alone, in a container, for one build. `stages-run.py` (and `uitest stages run`) run the same scripts in order.

Only one cell is covered so far: Ubuntu 26.04, GNOME, Wayland, with the game in `native` or `x11` mode.

## Stages

| Stage | What it does |
|---|---|
| `start` | Starts the desktop and saves its environment variables (`WAYLAND_DISPLAY`, `DISPLAY`, the D-Bus address ...). |
| `launch-linux [--game native\|x11] [--window WxH] [APPIMAGE]` | Starts the game in the background. `x11` sets `SDL_VIDEODRIVER=x11`, so the game goes through XWayland. |
| `observe [--wait S] [--settle S] [--screenshot PNG]` | Prints one JSON line with the game's windows as the desktop sees them (frame, client type, focus). Exit 1 if no game window appears. |
| `collect [DEST]` | Copies whatever exists of the stage logs, the game's output, `Latest.log` and the state file to DEST. Prints one `missing:` line per item that is not there, with the stage that creates it. Exit 0 if it collected anything, 1 if nothing. |
| `tidyup [--all]` | Stops the game and deletes its folder. `--all` also stops the desktop and clears the state file. With nothing running it says so and exits 0. |

`stage.sh list` prints the stages that exist for the current run. A stage is a `*.sh` file that starts with `#!`; `lib.sh` and `gnome.sh` are helpers that the stages source.

## Which script runs a stage

`resolve.sh DISTRO DESKTOP SESSION STAGE` prints the script. It looks in these folders, in this order, and the first hit wins:

1. `combos/<distro>+<desktop>/<session>/<stage>.sh`
2. `desktops/<desktop>/<session>/<stage>.sh`
3. `sessions/<session>/<stage>.sh`
4. `common/<stage>.sh`

It exits 1 and prints nothing if no folder has the stage, and exits 2 with a message if an argument is empty or has `/` or `..` in it. `stage.sh which NAME` shows the choice for the current container.
A combo is only for a real exception of one distro and desktop (today: the fake logind that GNOME needs in a container).

## The state file

Stages hand over through `/tmp/uitest/state.env`. A stage saves what later stages need with `state_set NAME VALUE`
(from `common/lib.sh`); every stage starts by sourcing the file. So `stage.sh observe` works in any shell of the container
after `stage.sh start` and `stage.sh launch-linux`, even a second shell. Stage logs go to `/tmp/uitest/logs/`.

## Errors

Every failure says what is wrong and how to fix it, with the exact command. Each stage checks its preconditions from the state file first:

| Stage | Needs | If not |
|---|---|---|
| `observe` | a started desktop (`WAYLAND_DISPLAY` and a live `DESKTOP_PIDS`) and a launched game | `no desktop running (WAYLAND_DISPLAY not set in /tmp/uitest/state.env): run \`stage.sh start\` first` |
| `launch-linux` | a started desktop and an AppImage: it exists, is a regular file and starts with the ELF magic | says what it found (missing, a folder, the first bytes) |
| `collect` | nothing; it copies what exists | `missing:` lines, and exit 1 with instructions if nothing was there |
| `tidyup` | nothing | `nothing to tidy up`, exit 0 |

A state file with a line that is not `export NAME=value`, or that bash cannot read, is reported with its line number. Delete it, or run `stage.sh tidyup --all`, which clears it.
`stage.sh` without `UITEST_STAGES`, `UITEST_DISTRO`, `UITEST_DESKTOP` and `UITEST_SESSION` explains that it runs inside the container from `uitest stages shell`. An unknown stage lists the stages that exist for the run.
The scripts use `set -u` and `pipefail`, not `set -e`: `wait_for` and the optional steps (a screenshot, stopping a process that is already gone) rely on non-zero returns, so each precondition is checked by hand.

## What `uitest stages` checks before it starts Docker

| Argument | Rule |
|---|---|
| distro | `stages/distros/<distro>/` exists and has a non-empty `Dockerfile` with a `FROM` line |
| desktop, session | the resolver finds `start`, `observe` and `launch-linux`; the session is `wayland` or `x11` |
| `--build` | `run`: `LABEL:PATH` with a label of letters, digits and `_ . + -`; `shell`: `PATH`. The file exists, is a regular file and starts with the ELF magic |
| `--game` | a comma list of `native` and `x11`, each once |
| `--runs` | at least 1 |
| Docker | installed, and the daemon answers |

A bad value gives the usual argparse error with the choices, or `uitest stages: ...` with the fix and the list of what does exist.

## Run one stage by hand

```
uitest stages shell ubuntu-26.04 gnome wayland --build path/to/Oolite.AppImage
```

This opens bash in a container (the image is built the first time: about 5 GB, 10 to 20 minutes). The stages are on `PATH`.

```
stage.sh start
stage.sh launch-linux --game native
stage.sh observe --screenshot /out/shot.png
stage.sh collect /out/mine
stage.sh tidyup --all
```

`/out` is `results/stages-shell/` on the host. The shell is `player`, and `uitest stages shell` makes `/out` writable for it. On a host filesystem that ignores permissions (NTFS) that does not work: write to `/tmp` and copy with `sudo cp`. `stage.sh which observe` shows which script a stage resolves to.

## Run them in order

```
uitest stages run ubuntu-26.04 gnome wayland --build pr81:path/to/Oolite.AppImage --game native,x11 --runs 3
```

Writes `results/stages-<date>-<label>/` with the RESULT lines (`stages-<label>.raw`) and, for each run,
`<game>-<run>.json` (what observe saw), `.png` and a folder of logs. Nothing on the host is mounted except the stages folder
and the AppImage (both read-only) and that output folder. No X socket is shared.

## RESULT line

One line per run, with separate fields:

```
RESULT wm=gnome-wayland-native distro=ubuntu-26.04 desktop=gnome session=wayland game=native build=pr81 run=1 client=wayland frame=1280x757 titlebar=37 focus=1 found=1
```

| Field | Meaning |
|---|---|
| `wm` | `<desktop>-<session>-<game>` |
| `distro` `desktop` `session` `game` | the cell; `game` is `native` or `x11` |
| `build` | the label you gave the AppImage |
| `client` | `wayland` or `x11`: what the game really ran as (`none` if no window) |
| `frame` | the window's frame as the desktop reports it, including the title bar |
| `titlebar` | frame height minus the window height asked for (`--window`, default 1280x720). 0 means no title bar |
| `focus` | 1 if the window has focus |
| `found` | 0 if no game window appeared. That is a result, not a skip |
| `why` | only when `found=0`: the reason, e.g. `no_game_window`, `observe_printed_nothing_exit_1`, `observe_output_not_json`, `observe_json_missing_windows` |

observe output that is empty, not JSON or lacks keys gives `found=0` and a `why=`, never an exception. `stages-run.py` builds and reads the line with its `Result` class (`Result.parse` rejects malformed lines).

## Add a desktop or a distro

A new desktop: make `desktops/<desktop>/<session>/` with `start.sh` and `observe.sh`. `observe.sh` prints the same JSON as the GNOME
one (`{"screen": [w, h], "windows": [{"title", "client", "frame": [x, y, w, h], "focus", ...}], "game": true|false}`) and exits 1 when
no game window appears. Source `common/lib.sh`, save variables with `state_set`, write why each step is there.
If a stage is the same for every desktop of a session type, put it in `sessions/<session>/` instead.

A new distro: make `distros/<distro>/Dockerfile` with that distro's standard desktop packages, plus `sudo` and the user `player`
(see the Ubuntu one). Set `ENV UITEST_STAGES=/stages PATH=/stages/bin:$PATH`. If the distro needs a different start, add
`combos/<distro>+<desktop>/<session>/start.sh`.

An empty folder is not a distro. `uitest stages run ubuntu-23 gnome wayland ...` with an empty `distros/ubuntu-23/` stops before Docker with
`stages/distros/ubuntu-23 has no Dockerfile: add one (see stages/README.md, Add a distro) or use one of: ubuntu-26.04`.
An empty Dockerfile, or one with no `FROM` line, is rejected the same way. A desktop folder without `start.sh` and `observe.sh` is not a
desktop: the error names the missing stage and lists the desktop and session pairs that work.
