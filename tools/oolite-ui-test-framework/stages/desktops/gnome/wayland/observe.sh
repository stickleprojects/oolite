#!/bin/bash
# observe.sh [--wait SECONDS] [--settle SECONDS] [--screenshot PATH] [--window-shot PATH]: GNOME's view of the game's windows, as one JSON line.
# The format is fixed (stages/README.md, "observe.sh output"; window_probes.parse_observe reads it):
#   {"screen": [w, h], "game": true|false,
#    "windows": [{"title", "client": "wayland"|"x11", "decorated", "frame": [x, y, w, h], "buffer": [x, y, w, h],
#                 "content": [x, y, w, h], "title_bar", "focus", "fullscreen", "maximized"}]}
# The game's windows are the ones whose title contains "oolite" (any case); "game" says whether there is one. Without one,
# "windows" lists every window, for the error message.
#   --wait     wait up to SECONDS for a game window (default 60; 0 = look once); exit 1 if none appears
#   --settle   once one is there, wait SECONDS more before measuring (default 5), so it has its final size and place
#   --screenshot PATH  also save a screenshot of the whole screen
#   --window-shot PATH also save a screenshot of the game window's content (the focused game window, else the first); exit 1 if
#                      there is no game window or the screenshot fails
# frame is the window as GNOME places it, including its title bar however it is drawn (by mutter for an X11 client, by the
# game through libdecor for a native Wayland one: GNOME draws none for Wayland clients, #75). content is the game's own
# drawing area: mutter's client rectangle for a window it decorates, else the window's buffer. title_bar is how far content
# starts below the top of frame, in pixels: 0 when nothing is drawn above the game.
# The game is the one `stage.sh launch-linux` started (GAME_PID). The test framework starts the game itself and sets
# UITEST_GAME_EXTERNAL=1, which skips that check.
. "${UITEST_STAGES:?UITEST_STAGES is not set: run stages through \`stage.sh NAME\` inside the container started by \`uitest stages shell DISTRO DESKTOP SESSION --build APPIMAGE\`}/common/lib.sh"
. "$UITEST_STAGES/desktops/gnome/wayland/gnome.sh"
wait=60 settle=5 shot= wshot=
while [ $# -gt 0 ]; do
    case $1 in
        --wait) [ $# -ge 2 ] || die "--wait needs a value: seconds"; wait=$2; shift 2 ;;
        --settle) [ $# -ge 2 ] || die "--settle needs a value: seconds"; settle=$2; shift 2 ;;
        --screenshot) [ $# -ge 2 ] || die "--screenshot needs a value: the PNG path"; shot=$2; shift 2 ;;
        --window-shot) [ $# -ge 2 ] || die "--window-shot needs a value: the PNG path"; wshot=$2; shift 2 ;;
        *) die "unknown option $1. Usage: observe.sh [--wait SECONDS] [--settle SECONDS] [--screenshot PNG] [--window-shot PNG]" ;;
    esac
done
[[ $wait =~ ^[0-9]+$ ]] || die "--wait must be a whole number of seconds, not '$wait'"
[[ $settle =~ ^[0-9]+$ ]] || die "--settle must be a whole number of seconds, not '$settle'"
for s in "$shot" "$wshot"; do
    [ -n "$s" ] || continue
    [ -d "$(dirname "$s")" ] || die "cannot save the screenshot: folder $(dirname "$s") does not exist; create it, or give another path"
    [ -w "$(dirname "$s")" ] || die "cannot save the screenshot: folder $(dirname "$s") is not writable; give another path, e.g. /tmp/shot.png"
done
need_desktop WAYLAND_DISPLAY
if [ -z "${UITEST_GAME_EXTERNAL:-}" ]; then
    [ -n "${GAME_PID:-}" ] || die "no game launched (GAME_PID not set in $UITEST_STATE): run \`stage.sh launch-linux\` first"
    kill -0 "$GAME_PID" 2>/dev/null || echo "observe.sh: the game (pid $GAME_PID) has exited; see ${GAME_OUT:-$UITEST_LOGS/game.out}. Run \`stage.sh tidyup\` and \`stage.sh launch-linux\` to start it again" >&2
fi
need_cmd gdbus python3
js='(() => {
  const r = x => [x.x, x.y, x.width, x.height];
  const all = global.display.list_all_windows().map(w => {
    const frame = w.get_frame_rect();
    const content = w.decorated ? w.frame_rect_to_client_rect(frame) : w.get_buffer_rect();
    return {title: w.get_title() || "", client: w.get_client_type() == 0 ? "wayland" : "x11", decorated: w.decorated,
      frame: r(frame), buffer: r(w.get_buffer_rect()), content: r(content), title_bar: Math.max(0, content.y - frame.y),
      focus: w.has_focus(), fullscreen: w.is_fullscreen(), maximized: w.is_maximized()};
  });
  const game = all.filter(w => /oolite/i.test(w.title));
  const [sw, sh] = global.display.get_size();
  return JSON.stringify({screen: [sw, sh], windows: game.length ? game : all, game: game.length > 0});
})()'
game_up() { local out; out=$(shell_js "$js") && [[ $out == *'"game":true'* ]]; }
found=1
if wait_for "$wait" game_up; then sleep "$settle"; else found=0; fi
out=$(shell_js "$js") || die "GNOME Shell is not answering (see $UITEST_LOGS/gnome-shell.log): run \`stage.sh tidyup --all\`, then \`stage.sh start\`"
echo "$out"
[ -n "$shot" ] && { shell_screenshot "$shot" || echo "observe.sh: screenshot failed" >&2; }
if [ -n "$wshot" ]; then
    [ $found = 1 ] || die "no game window to take a --window-shot of: is the game running?"
    # the content rectangle of the focused game window, else the first (as window_probes.parse_observe picks it)
    area=$(python3 -c 'import json, sys
ws = json.loads(sys.argv[1])["windows"]; w = next((w for w in ws if w["focus"]), ws[0]); print(*w["content"])' "$out") ||
        die "cannot read the game window's content rectangle from the JSON above"
    shell_screenshot_area $area "$wshot" || die "the window screenshot failed (GNOME Shell's ScreenshotArea for $area): see $UITEST_LOGS/gnome-shell.log"
fi
[ $found = 1 ] || { echo "observe.sh: no game window after ${wait} s (all windows listed). Is the game running? See ${GAME_OUT:-$UITEST_LOGS/game.out}; \`stage.sh tidyup\` then \`stage.sh launch-linux\` starts it again" >&2; exit 1; }
