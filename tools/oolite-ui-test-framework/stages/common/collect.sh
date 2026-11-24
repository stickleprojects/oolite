#!/bin/bash
# collect.sh [DEST]: copy whatever exists of the run's output to DEST (default $UITEST_OUT, /out in the container):
#   logs/<stage logs>   written by start and the other stages, in $UITEST_LOGS
#   logs/game.out       the game's stdout and stderr (launch-linux)
#   logs/Latest.log     the game's own log, found in the game's run folder (launch-linux, once the game has started)
#   state.env           the state file
# Safe to run at any point, and more than once. For each item that is not there it prints one line with the reason and the stage
# that creates it. Exit 0 if anything was collected; exit 1 if nothing was (with what to run first).
. "${UITEST_STAGES:?UITEST_STAGES is not set: run stages through \`stage.sh NAME\` inside the container started by \`uitest stages shell DISTRO DESKTOP SESSION --build APPIMAGE\`}/common/lib.sh"
case ${1:-} in -*) die "unknown option $1. Usage: collect.sh [DEST]" ;; esac
dest=${1:-$UITEST_OUT}
got=() missing=()

stage_logs=$(find "$UITEST_LOGS" -maxdepth 1 -type f ! -name game.out 2>/dev/null | head -1)
[ -n "$stage_logs" ] && got+=(stage-logs) || missing+=("stage logs: none in $UITEST_LOGS; run \`stage.sh start\` to get them")
[ -s "$UITEST_LOGS/game.out" ] && got+=(game.out) || missing+=("game.out: the game has not been launched (or printed nothing); run \`stage.sh launch-linux\` to get it")
latest=
if [ -n "${GAME_DIR:-}" ] && [ -d "$GAME_DIR" ]; then latest=$(find "$GAME_DIR" -name Latest.log 2>/dev/null | head -1); fi
if [ -n "$latest" ]; then got+=(Latest.log)
elif [ -z "${GAME_DIR:-}" ]; then missing+=("Latest.log: no game folder in the state file; run \`stage.sh launch-linux\` to get it")
elif [ ! -d "$GAME_DIR" ]; then missing+=("Latest.log: the game folder $GAME_DIR is gone (tidyup deletes it); collect before \`stage.sh tidyup\`, or run \`stage.sh launch-linux\` again")
else missing+=("Latest.log: the game has not written one in $GAME_DIR yet; wait for it to start, then run \`stage.sh collect\` again")
fi
[ -s "$UITEST_STATE" ] && got+=(state.env) || missing+=("state.env: $UITEST_STATE is empty; run \`stage.sh start\` to fill it")

for m in "${missing[@]}"; do echo "missing: $m"; done
if [ ${#got[@]} -eq 0 ]; then
    echo "collect.sh: nothing to collect. Run \`stage.sh start\` (the desktop), then \`stage.sh launch-linux\` (the game), then \`stage.sh collect $dest\`" >&2
    exit 1
fi
mkdir -p "$dest/logs" 2>/dev/null || die "cannot create $dest/logs: pass a folder you can write, e.g. \`stage.sh collect /tmp/mine\`"
for item in "${got[@]}"; do
    case $item in
        stage-logs) find "$UITEST_LOGS" -maxdepth 1 -type f ! -name game.out -exec cp -a {} "$dest/logs/" \; ;;
        game.out) cp -a "$UITEST_LOGS/game.out" "$dest/logs/" ;;
        Latest.log) cp "$latest" "$dest/logs/Latest.log" ;;
        state.env) cp "$UITEST_STATE" "$dest/state.env" ;;
    esac || die "cannot write to $dest: pass a folder you can write, e.g. \`stage.sh collect /tmp/mine\`"
done
echo "collected: $dest (${got[*]})"
