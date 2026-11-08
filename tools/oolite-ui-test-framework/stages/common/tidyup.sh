#!/bin/bash
# tidyup.sh [--all]: stop the game and delete its run folder, so the next launch starts clean.
#   --all  also stop the desktop (every process this container's stages started) and clear the state file.
#          It is also the way out of a malformed state file: it clears the file instead of refusing to read it.
# With nothing running it says so and exits 0. The game is stopped with SIGTERM, then SIGKILL after 5 s. "Gone" includes the
# AppImage runtime, which deletes its extracted copy after the game exits: a game launched during that clean-up got its keys late
# (see scenarios.Game.stop).
all=0
for a in "$@"; do
    case $a in --all) all=1 ;; *) echo "tidyup.sh: unknown option '$a'. Usage: tidyup.sh [--all]" >&2; exit 1 ;; esac
done
[ $all = 1 ] && UITEST_LENIENT=1
. "${UITEST_STAGES:?UITEST_STAGES is not set: run stages through \`stage.sh NAME\` inside the container started by \`uitest stages shell DISTRO DESKTOP SESSION --build APPIMAGE\`}/common/lib.sh"
pid=${GAME_PID:-} dir=${GAME_DIR:-} dpids=${DESKTOP_PIDS:-}
if [ -z "$pid" ] && [ -z "$dir" ] && { [ $all = 0 ] || [ -z "$dpids" ]; }; then
    [ $all = 1 ] && : > "$UITEST_STATE"
    what="game"; [ $all = 1 ] && what="game and no desktop"
    echo "nothing to tidy up: no $what running according to $UITEST_STATE"
    exit 0
fi
[ -n "$pid" ] && kill -TERM -- "-$pid" 2>/dev/null
pkill -f appimage_extracted 2>/dev/null
for _ in $(seq 10); do
    { [ -z "$pid" ] || ! kill -0 "$pid" 2>/dev/null; } && ! pgrep -f appimage_extracted >/dev/null && break
    sleep 0.5
done
[ -n "$pid" ] && kill -KILL -- "-$pid" 2>/dev/null
pkill -9 -f appimage_extracted 2>/dev/null
[ -n "$dir" ] && rm -rf "$dir"
for v in GAME_PID GAME_DIR GAME_MODE GAME_WINDOW GAME_OUT; do state_unset $v; done
if [ $all = 1 ]; then
    # shellcheck disable=SC2086  # DESKTOP_PIDS is a space-separated list
    [ -n "$dpids" ] && kill $dpids 2>/dev/null
    : > "$UITEST_STATE"
    echo "tidied up: game and desktop stopped"
else
    echo "tidied up: game stopped"
fi
exit 0
