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
. "$UITEST_STAGES/common/lib.sh"
. "$UITEST_STAGES/desktops/gnome/wayland/gnome.sh"
wait=60 settle=5 shot=
while [ $# -gt 0 ]; do
    case $1 in
        --wait) wait=$2; shift 2 ;;
        --settle) settle=$2; shift 2 ;;
        --screenshot) shot=$2; shift 2 ;;
        *) die "unknown option $1" ;;
    esac
done
js='(() => {
  const r = x => [x.x, x.y, x.width, x.height];
  const all = global.display.list_all_windows().map(w => ({title: w.get_title() || "", client: w.get_client_type() == 0 ? "wayland" : "x11",
    decorated: w.decorated, frame: r(w.get_frame_rect()), buffer: r(w.get_buffer_rect()), focus: w.has_focus(),
    fullscreen: w.is_fullscreen(), maximized: w.is_maximized()}));
  const game = all.filter(w => /oolite/i.test(w.title));
  const [sw, sh] = global.display.get_size();
  return JSON.stringify({screen: [sw, sh], windows: game.length ? game : all, game: game.length > 0});
})()'
game_up() { shell_js "$js" | grep -q '"game":true'; }
found=1
if wait_for "$wait" game_up; then sleep "$settle"; else found=0; fi
shell_js "$js" || die "GNOME Shell is not answering"
[ -n "$shot" ] && { shell_screenshot "$shot" || echo "observe.sh: screenshot failed" >&2; }
[ $found = 1 ] || { echo "observe.sh: no game window after ${wait} s (all windows listed)" >&2; exit 1; }
