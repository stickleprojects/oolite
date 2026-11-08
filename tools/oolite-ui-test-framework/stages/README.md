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
| `collect [DEST]` | Copies the stage logs, the game's output, `Latest.log` and the state file to DEST. |
| `tidyup [--all]` | Stops the game and deletes its folder. `--all` also stops the desktop and clears the state file. |

## Which script runs a stage

`resolve.sh DISTRO DESKTOP SESSION STAGE` prints the script. It looks in these folders, in this order, and the first hit wins:

1. `combos/<distro>+<desktop>/<session>/<stage>.sh`
2. `desktops/<desktop>/<session>/<stage>.sh`
3. `sessions/<session>/<stage>.sh`
4. `common/<stage>.sh`

It exits 1 and prints nothing if no folder has the stage. `stage.sh which NAME` shows the choice for the current container.
A combo is only for a real exception of one distro and desktop (today: the fake logind that GNOME needs in a container).

## The state file

Stages hand over through `/tmp/uitest/state.env`. A stage saves what later stages need with `state_set NAME VALUE`
(from `common/lib.sh`); every stage starts by sourcing the file. So `stage.sh observe` works in any shell of the container
after `stage.sh start` and `stage.sh launch-linux`, even a second shell. Stage logs go to `/tmp/uitest/logs/`.

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

## Add a desktop or a distro

A new desktop: make `desktops/<desktop>/<session>/` with `start.sh` and `observe.sh`. `observe.sh` prints the same JSON as the GNOME
one (`{"screen": [w, h], "windows": [{"title", "client", "frame": [x, y, w, h], "focus", ...}], "game": true|false}`) and exits 1 when
no game window appears. Source `common/lib.sh`, save variables with `state_set`, write why each step is there.
If a stage is the same for every desktop of a session type, put it in `sessions/<session>/` instead.

A new distro: make `distros/<distro>/Dockerfile` with that distro's standard desktop packages, plus `sudo` and the user `player`
(see the Ubuntu one). Set `ENV UITEST_STAGES=/stages PATH=/stages/bin:$PATH`. If the distro needs a different start, add
`combos/<distro>+<desktop>/<session>/start.sh`.
