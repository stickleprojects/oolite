#!/bin/bash
# launch-linux.sh [--game native|x11] [--window WxH] [APPIMAGE]: start the game as a player would, in the background.
#   --game native  SDL picks the video driver (native Wayland when the session offers it). Default.
#          x11     SDL_VIDEODRIVER=x11: an X11 client, so through XWayland in a Wayland session.
#   --window WxH   saved window size written to GameData/oolite.plist first (default 1280x720), so the window's size is known
#                  and does not depend on what an earlier run saved.
#   APPIMAGE       default $UITEST_APPIMAGE, else /app/oolite.AppImage.
# The AppImage runs from a fresh copy of its folder (it reads the GameData folder next to it), with APPIMAGE_EXTRACT_AND_RUN=1
# because a container has no FUSE. Saves GAME_PID, GAME_DIR, GAME_MODE, GAME_WINDOW and GAME_OUT for later stages.
. "$UITEST_STAGES/common/lib.sh"
mode=native window=1280x720 app=${UITEST_APPIMAGE:-/app/oolite.AppImage}
while [ $# -gt 0 ]; do
    case $1 in
        --game) mode=$2; shift 2 ;;
        --window) window=$2; shift 2 ;;
        -*) die "unknown option $1" ;;
        *) app=$1; shift ;;
    esac
done
case $mode in native|x11) ;; *) die "--game must be native or x11, not '$mode'" ;; esac
[[ $window =~ ^[0-9]+x[0-9]+$ ]] || die "--window must be WxH, not '$window'"
[ -f "$app" ] || die "no AppImage at $app"
[ -n "$GAME_PID" ] && kill -0 "$GAME_PID" 2>/dev/null && die "a game is already running (pid $GAME_PID): stage.sh tidyup first"

dir=$(mktemp -d /tmp/uitest/run.XXXXXX)
src=$(dirname "$(realpath "$app")")
for f in "$src"/*; do case $f in *.AppImage) ;; *) cp -a "$f" "$dir/" ;; esac; done
cp "$app" "$dir/oolite.AppImage"; chmod +x "$dir/oolite.AppImage"
mkdir -p "$dir/GameData"
plist=$dir/GameData/oolite.plist
[ -f "$plist" ] || printf '{\n}\n' > "$plist"
w=${window%x*} h=${window#*x}
sed -i -E '/"?window_(width|height)"?[[:space:]]*=/d' "$plist"
sed -i "0,/^}/s//    \"window_width\" = $w;\n    \"window_height\" = $h;\n}/" "$plist"

if [ "$mode" = x11 ]; then export SDL_VIDEODRIVER=x11; else unset SDL_VIDEODRIVER; fi
out=$UITEST_LOGS/game.out
( cd "$dir" && APPIMAGE_EXTRACT_AND_RUN=1 exec setsid ./oolite.AppImage ) >"$out" 2>&1 &
state_set GAME_PID $!
state_set GAME_DIR "$dir"
state_set GAME_MODE "$mode"
state_set GAME_WINDOW "$window"
state_set GAME_OUT "$out"
echo "launched: $(basename "$app") --game $mode --window $window (pid $GAME_PID, folder $dir, SDL_VIDEODRIVER=${SDL_VIDEODRIVER:-unset})"
