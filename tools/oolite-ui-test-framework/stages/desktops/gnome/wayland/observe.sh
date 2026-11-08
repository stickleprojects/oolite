#!/bin/bash
# observe.sh [--wait SECONDS] [--settle SECONDS] [--screenshot PATH]: GNOME's view of the game's windows, as one JSON line:
#   {"screen": [w, h], "windows": [{"title", "client": "wayland"|"x11", "decorated", "frame": [x, y, w, h],
#                                   "buffer": [x, y, w, h], "focus", "fullscreen", "maximized"}]}
# The game's windows are the ones whose title contains "oolite" (any case).
#   --wait     wait up to SECONDS for a game window (default 60); exit 1 if none appears (the JSON then lists every window)
#   --settle   once one is there, wait SECONDS more before measuring (default 5), so it has its final size and place
#   --screenshot PATH  also save a screenshot of the whole screen
# frame is the window as GNOME places it, including its title bar however it is drawn (by mutter for an X11 client, by the
# game through libdecor for a native Wayland one: GNOME draws none for Wayland clients, #75). A title bar shows as frame
# height minus the window height the game asked for (GAME_WINDOW).
. "${UITEST_STAGES:?UITEST_STAGES is not set: run stages through \`stage.sh NAME\` inside the container started by \`uitest stages shell DISTRO DESKTOP SESSION --build APPIMAGE\`}/common/lib.sh"
. "$UITEST_STAGES/desktops/gnome/wayland/gnome.sh"
wait=60 settle=5 shot=
while [ $# -gt 0 ]; do
    case $1 in
        --wait) [ $# -ge 2 ] || die "--wait needs a value: seconds"; wait=$2; shift 2 ;;
        --settle) [ $# -ge 2 ] || die "--settle needs a value: seconds"; settle=$2; shift 2 ;;
        --screenshot) [ $# -ge 2 ] || die "--screenshot needs a value: the PNG path"; shot=$2; shift 2 ;;
        *) die "unknown option $1. Usage: observe.sh [--wait SECONDS] [--settle SECONDS] [--screenshot PNG]" ;;
    esac
done
[[ $wait =~ ^[0-9]+$ ]] || die "--wait must be a whole number of seconds, not '$wait'"
[[ $settle =~ ^[0-9]+$ ]] || die "--settle must be a whole number of seconds, not '$settle'"
if [ -n "$shot" ]; then
    [ -d "$(dirname "$shot")" ] || die "cannot save the screenshot: folder $(dirname "$shot") does not exist; create it, or give another --screenshot path"
    [ -w "$(dirname "$shot")" ] || die "cannot save the screenshot: folder $(dirname "$shot") is not writable; give another --screenshot path, e.g. /tmp/shot.png"
fi
need_desktop WAYLAND_DISPLAY
[ -n "${GAME_PID:-}" ] || die "no game launched (GAME_PID not set in $UITEST_STATE): run \`stage.sh launch-linux\` first"
kill -0 "$GAME_PID" 2>/dev/null || echo "observe.sh: the game (pid $GAME_PID) has exited; see ${GAME_OUT:-$UITEST_LOGS/game.out}. Run \`stage.sh tidyup\` and \`stage.sh launch-linux\` to start it again" >&2
need_cmd gdbus python3
js='(() => {
  const r = x => [x.x, x.y, x.width, x.height];
  const all = global.display.list_all_windows().map(w => ({title: w.get_title() || "", client: w.get_client_type() == 0 ? "wayland" : "x11",
    decorated: w.decorated, frame: r(w.get_frame_rect()), buffer: r(w.get_buffer_rect()), focus: w.has_focus(),
    fullscreen: w.is_fullscreen(), maximized: w.is_maximized()}));
  const game = all.filter(w => /oolite/i.test(w.title));
  const [sw, sh] = global.display.get_size();
  return JSON.stringify({screen: [sw, sh], windows: game.length ? game : all, game: game.length > 0});
})()'
game_up() { local out; out=$(shell_js "$js") && [[ $out == *'"game":true'* ]]; }
found=1
if wait_for "$wait" game_up; then sleep "$settle"; else found=0; fi
shell_js "$js" || die "GNOME Shell is not answering (see $UITEST_LOGS/gnome-shell.log): run \`stage.sh tidyup --all\`, then \`stage.sh start\`"
[ -n "$shot" ] && { shell_screenshot "$shot" || echo "observe.sh: screenshot failed" >&2; }
[ $found = 1 ] || { echo "observe.sh: no game window after ${wait} s (all windows listed). Is the game running? See ${GAME_OUT:-$UITEST_LOGS/game.out}; \`stage.sh tidyup\` then \`stage.sh launch-linux\` starts it again" >&2; exit 1; }
