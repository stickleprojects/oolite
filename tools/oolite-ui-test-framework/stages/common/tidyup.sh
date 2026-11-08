#!/bin/bash
# tidyup.sh [--all]: stop the game and delete its run folder, so the next launch starts clean.
#   --all  also stop the desktop (every process this container's stages started) and clear the state file.
# The game is stopped with SIGTERM, then SIGKILL after 5 s. "Gone" includes the AppImage runtime, which deletes its extracted copy
# after the game exits: a game launched during that clean-up got its keys late (see scenarios.Game.stop).
. "$UITEST_STAGES/common/lib.sh"
[ -n "$GAME_PID" ] && kill -TERM -- "-$GAME_PID" 2>/dev/null
pkill -f appimage_extracted 2>/dev/null
for _ in $(seq 10); do
    { [ -z "$GAME_PID" ] || ! kill -0 "$GAME_PID" 2>/dev/null; } && ! pgrep -f appimage_extracted >/dev/null && break
    sleep 0.5
done
[ -n "$GAME_PID" ] && kill -KILL -- "-$GAME_PID" 2>/dev/null
pkill -9 -f appimage_extracted 2>/dev/null
[ -n "$GAME_DIR" ] && rm -rf "$GAME_DIR"
for v in GAME_PID GAME_DIR GAME_MODE GAME_WINDOW GAME_OUT; do state_unset $v; done
if [ "$1" = --all ]; then
    [ -n "$DESKTOP_PIDS" ] && kill $DESKTOP_PIDS 2>/dev/null
    : > "$UITEST_STATE"
    echo "tidied up: game and desktop stopped"
else
    echo "tidied up: game stopped"
fi
