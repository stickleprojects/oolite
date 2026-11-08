#!/bin/bash
# collect.sh [DEST]: copy the run's logs (stage logs, the game's output and Latest.log) and the state file to DEST
# (default $UITEST_OUT). Safe to run at any point, and more than once.
. "$UITEST_STAGES/common/lib.sh"
dest=${1:-$UITEST_OUT}
mkdir -p "$dest/logs"
cp -a "$UITEST_LOGS"/. "$dest/logs/" 2>/dev/null
cp "$UITEST_STATE" "$dest/state.env"
if [ -n "$GAME_DIR" ] && [ -d "$GAME_DIR" ]; then
    find "$GAME_DIR" -name Latest.log -exec cp {} "$dest/logs/Latest.log" \; 2>/dev/null
fi
echo "collected: $dest ($(ls "$dest/logs" | tr '\n' ' '))"
