# UI tests: what we learnt, and the tweaks that made them reliable

A running list of the investigations behind the UI tests: what went wrong, why, and what changed. Read it before "fixing" something
that looks odd in the framework, because most odd-looking choices are here for a reason.

**Keep it updated.** When an investigation finds a cause, or a change works around an environment quirk, add an entry in the same PR:
symptom, cause, fix, and where (PR / issue). Open questions go under [Still open](#still-open) and move up when they are settled.

## Environments: compositor and window manager quirks

| Symptom | Cause | Fix | Where |
|---|---|---|---|
| weston-xwayland: game window at (0,0) "about 1 run in 5" | weston's default idle timeout (300 s). Injected input goes to XWayland, not weston, so weston went idle 5 minutes in and every later window opened at (0,0). Both builds; the "1 in 5" was the 5th run starting after 5 minutes | `weston --idle-time=0` on both weston environments (verified 2026-10-29: 10 runs each, stock and pr774, none at (0,0)) | #47 |
| sway: clicks select the wrong menu rows (rows 3 and 5 never) | sway tiles: it stretched the 1280x720 window to 3836x1053, and the game still maps the pointer with the size it asked for. The stock build does the same, so not a #774 regression | sway floats every window (`for_window [shell=".*"] floating enable`), so the game gets the size it asks for | #42, #51 |
| sway: keys missed, held keys and clicks needed about 1 s | Software rendering (llvmpipe) at 3836x1053: about 1 fps tiled, 5 fps floating at 1280x720. A press shorter than a frame is never seen | Floating (above); `press_until` taps longer when a tap is ignored | #42, #48 |
| A desktop that resizes the window would fail clicks for an unclear reason | as above | Precondition `window_size_as_requested`: its own test, and checked before every click | #42 |
| kwin: crashes on screenshots / exits at start headless | KWin needs a render device (KDE bug 527906, WONTFIX) | `/dev/udmabuf` passed in (`devices`), no GPU needed; precondition `render_device` (on the host: `sudo modprobe udmabuf`) | #37 |
| kwin-xwayland: screenshots black, so render/menu/F12 failed | The compositor hands out a black window until the first frame is presented | Look again for up to 10 s (`RENDER_WAIT`); later the ScreenShot2 path | #4 |
| headless KWin: XTEST clicks and keys never reach the game | Headless KWin ignores XTEST | KWin's fake-input protocol (`uitest-fakeinput`), started with `KWIN_WAYLAND_NO_PERMISSION_CHECKS=1`; precondition `fake_input_offered` | #30, #28 |
| kwin-native: no screenshots | No X display | KWin ScreenShot2 over D-Bus, cropped to the game's client area | #37 |
| kwin-native: keys test failed about 2 in 5 (the menu ran past the row) | KWin advertised key repeat (25/s after 600 ms), so the game repeated a held key itself | `kcminputrc` with `KeyRepeat=nothing`; precondition `key_repeat_off` reads the advertised rate with `wayland-info` | #39 |
| X11 / XWayland: one held key became many presses (F12 toggled about 10 times) | X autorepeat | Autorepeat off in every session (and on the host for a host run); precondition `key_repeat_off` | #26 |
| weston (headless): `gets_focus` NOT MEASURABLE | Headless weston has no keyboard, so it never activates a window: in a running weston-xwayland `_NET_ACTIVE_WINDOW` stays `0x0` and the X input focus is PointerRoot (`1`). Measuring it anyway (focus_na off) gave focus=0 every run while keys still worked. Not a detection bug | `focus_na = true` kept, now with that evidence in `environments.toml` | #45 |
| weston-xwayland: keys test fails in run 1 only (3 stock runs in a row) | With PointerRoot focus, keys go to the window under the pointer. Our keys never pass through weston: XTEST creates them inside XWayland. The keys test runs before the click test, so in run 1 the pointer was not on the game yet; later runs inherited the pointer the previous click test left over it | `keys_follow_pointer = true` (a setting of its own, not hidden behind `focus_na`): keys are still tested, with the pointer put on the middle of the game window before each key (verified: stock keys passed run 1 in 3/3 runs). Stopgap: #53 gives weston a real seat (VNC backend or weston's test plugin) | #47, #53 |
| F12 not tested on any native Wayland session | The F12 tests were gated on an X11 probe, from when F12 was judged by window size. Since #42 it is judged by full-screen state, which the KWin and sway probes report too | Gate `needs_window_probe` (X11, KWin or sway). kwin-native: both F12 tests pass 3/3 (1280x720 -> 3840x1080 -> 1280x720). sway-, mutter- and weston-native set `keys_na`: they have no way to inject keys (no X server, no fake-input), which the old gate had hidden | #43 |
| A partial run with only the F12 tests reported `centred` failing | Both F12 tests share one record per run, so the RESULT line took the oversized-window launch's geometry. The TEST lines were right | Recorded | #55 |
| sway-native: no keys, clicks or screenshots | No X server for XTEST or for the X11 grab | `uitest-wlrinput` (`docker/wlrinput.c`), the standard virtual-keyboard and virtual-pointer protocols, `keys = "virtual"`; screenshots with `grim` cropped to the client area from sway's tree (`window_rect`); `repeat_rate 0` for the virtual keyboard. Verified 3 runs: title menu, keys, clicks and F12 pass | #44 |
| sway-native: keys test failed in run 1 only ("the game logged no key presses") | The first key from a new virtual keyboard makes it the seat's keyboard and sends the game its keymap; that key was lost. Later runs reuse the running injector | `uitest-wlrinput` taps Shift once when it starts | #44 |
| sway-native: F12 with a saved window larger than the screen fails `centred` in run 1 only | Not known. The window is 4096x1336 in every run; sway's tree after the round trip reports 4100x1338 in run 1 and 3844x1082 later | Open | #57 |
| kwin-xwayland: window 36 px lower after the F12 round trip | About KWin's title-bar height; within the 40 px tolerance | Not fixed, recorded | #11 (open) |
| mutter 2head: F12 did nothing (no focus) | Harness problem in both builds, not a game difference | Re-checked once the Debian image had `cvt` | #10 |
| kwin X11 did not start | kglobalaccel crashed | Recorded in the run; later runs start | #36 |

## The game and how it reads input

- **The game reads keys and the mouse once per frame.** A tap shorter than a frame is lost (down and up in the same frame). The
  harness holds a key only until the screenshot shows the change, and where a look is slow it taps, doubling the tap when the game
  ignored it and remembering the tap that worked (#26, #39, #42).
- **A held key moves a menu once per frame**, so fixed holds (1 s, 1.5 s) moved 0 rows or several depending on the frame rate. Selecting
  by clicking the row is steadier where the mouse works (#26, #28).
- **The first mouse motion after the game warps the pointer is ignored**, so a click moves twice (x+1, then x) and settles first (#28).
- **The game's log is evidence that input arrived, never the verdict.** In #773 the game logged nothing wrong while it had no title
  bar and no focus. Wait on what the window manager and the screenshot show; read the log to explain a failure ("the game logged 0 key
  presses") or to decide whether to send a fallback F12. The log is written about every 2 s (#42, `game_log.py`).
- **F12 is judged by full-screen state**, not size: X11 `_NET_WM_STATE`, KWin `fullScreen`, sway `fullscreen_mode` (#42).
- **The saved window size** is restored by #774 (upstream #775); the test reads both the window and the size the game asked for (#36).

## Screens and OCR

- The old render and keys tests passed on broken builds. They were replaced by screen-verified title-menu tests (OCR on the window),
  with a negative control proving they fail on a broken build (#6, #9, #20).
- OCR crops are padded (a share of the row height, capped at half the gap to the next row), because tight crops lost letters (#42).
- Menu rows are split where lines switch between the highlight bar and text; "Exit Game" used to merge with the row above (#42).
- A settled highlight is read by waiting for it to stop moving, not with a fixed sleep (#7).

## Harness and runner

- **Preconditions fail with their own reason**, `PRECONDITION <name>: <expected, found>`, instead of a misleading assertion. Each one in
  `preconditions.py` says how it was learnt (#32).
- **Results are written as each run finishes**, and copied into `<name>.raw` every 2 s, so a long run shows progress and a stopped run
  keeps what it measured (#52).
- **`docker run --init`**: the container's PID 1 was a shell, which ignores signals it has no handler for, so stopping uitest left the
  container running. With `--init`, stopping uitest stops the container (#47 work).
- **Container output is chowned back** to the host user; the containers still run as root because the window managers and dbus expect
  it (#12, #19).
- **One shared game launch per run** for the read-only tests; pytest 7 relaunched it before every test until the same `Case` objects
  were reused. Tests that change state get a private launch, and shared-launch tests run first (#7, #25).
- **Wait for readiness, not fixed sleeps**: about half the time per matrix (#7, #25).
- **Host mode** runs every test with pytest from its own venv; the helper container serves one long-lived `xtool serve` because a
  `docker exec` per call (0.2 s) was too slow for hold-and-look (#15, #35).
- **The wayland image once failed to build** (wrong `COPY` path), and every Wayland environment was then skipped as "not available".
  The `input_tool` precondition now catches a missing tool (#29).
- **Images rebuild when their sources change.** uitest built an image only when it was missing, so a new injector in `docker/` never
  reached an existing image (sway-native failed every input test with `PRECONDITION input_tool`). Images are labelled with a hash of
  their Dockerfile and `docker/`, and rebuilt on a mismatch (#44).
- **A partial run says so**: `--tests` adds "PARTIAL RUN" to the purpose so it is never read as a full pass.

## Coverage write-ups

- [docs/weston.md](docs/weston.md): what can and cannot be tested on weston, why (headless weston has no input devices), and the VNC
  spike (#53).
- Every report has a **"What cannot be tested where"** table, built from the run's own skip reasons: a limit that is fixed drops off
  by itself.

## Rules of thumb

- **Never mount `/tmp/.X11-unix`**; mount only the X0 socket file. A compositor container once replaced the host's socket.
- **Compare against stock.** Several "regressions" were the environment or an existing game bug (the sway clicks, the weston (0,0)).
  Run the stock build under the same probe before blaming a PR.
- **Look at timing when failures cluster.** The weston (0,0) looked random until the run start times showed a 5-minute cliff.
- **Software rendering hides timing**: every headless environment uses llvmpipe; frame times are not what users see (#48).

## Still open

- **weston input**: `keys_follow_pointer` is a stopgap. #53 moves weston to a real seat (VNC backend, already in the image, or weston's test plugin), which would make focus measurable and let weston-native run the keys, mouse and screenshot tests.
- **Coverage gaps**, tracked as issues: F12 on native Wayland (#43: done for kwin- and sway-native), screenshots on mutter/weston native (#44: done for sway-native), window observation on
  mutter/weston native (#45), splash on native Wayland (#46), software rendering only, and headed sway does not start (#48), nothing
  past the title menu (#49), precondition reasons inside a test (#50). A full re-baseline is #14; real desktops #13.
- **#27**: on kwin, openbox and xfwm4 the game sometimes ignored or delayed a key press it had received (closed; reopen if it returns).
