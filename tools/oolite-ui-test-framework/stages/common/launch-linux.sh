#!/bin/bash
# launch-linux.sh [--game native|x11] [--window WxH] [APPIMAGE]: start the game as a player would, in the background.
#   --game native  SDL picks the video driver (native Wayland when the session offers it). Default.
#          x11     SDL_VIDEODRIVER=x11: an X11 client, so through XWayland in a Wayland session.
#   --window WxH   saved window size written to GameData/oolite.plist first (default 1280x720), so the window's size is known
#                  and does not depend on what an earlier run saved.
#   APPIMAGE       default $UITEST_APPIMAGE, else /app/oolite.AppImage.
# The AppImage runs from a fresh copy of its folder (it reads the GameData folder next to it), with APPIMAGE_EXTRACT_AND_RUN=1
# because a container has no FUSE. Saves GAME_PID, GAME_DIR, GAME_MODE, GAME_WINDOW and GAME_OUT for later stages.
. "${UITEST_STAGES:?UITEST_STAGES is not set: run stages through \`stage.sh NAME\` inside the container started by \`uitest stages shell DISTRO DESKTOP SESSION --build APPIMAGE\`}/common/lib.sh"
mode=native window=1280x720 app=${UITEST_APPIMAGE:-/app/oolite.AppImage}
while [ $# -gt 0 ]; do
    case $1 in
        --game) [ $# -ge 2 ] || die "--game needs a value: native or x11"; mode=$2; shift 2 ;;
        --window) [ $# -ge 2 ] || die "--window needs a value: WxH, e.g. 1280x720"; window=$2; shift 2 ;;
        -*) die "unknown option $1. Usage: launch-linux.sh [--game native|x11] [--window WxH] [APPIMAGE]" ;;
        *) app=$1; shift ;;
    esac
done
case $mode in native|x11) ;; *) die "--game must be native or x11, not '$mode'" ;; esac
[[ $window =~ ^[0-9]+x[0-9]+$ ]] || die "--window must be WxH, e.g. 1280x720, not '$window'"
need_cmd sed realpath setsid mktemp od
need_desktop "$(session_var)"
check_appimage "$app"
if [ -n "${GAME_PID:-}" ] && kill -0 "$GAME_PID" 2>/dev/null; then die "a game is already running (pid $GAME_PID): run \`stage.sh tidyup\` first"; fi

mkdir -p /tmp/uitest || die "cannot create /tmp/uitest"
dir=$(mktemp -d /tmp/uitest/run.XXXXXX) || die "cannot create a run folder in /tmp/uitest: free some disk space"
src=$(dirname "$(realpath "$app")")
for f in "$src"/*; do
    [ -e "$f" ] || continue
    case $f in *.AppImage) ;; *) cp -a "$f" "$dir/" || die "cannot copy $f to $dir: free some disk space" ;; esac
done
cp "$app" "$dir/oolite.AppImage" && chmod +x "$dir/oolite.AppImage" || die "cannot copy the AppImage to $dir: free some disk space"
mkdir -p "$dir/GameData"
plist=$dir/GameData/oolite.plist
[ -f "$plist" ] || printf '{\n}\n' > "$plist"
w=${window%x*} h=${window#*x}
sed -i -E '/"?window_(width|height)"?[[:space:]]*=/d' "$plist"
sed -i "0,/^}/s//    \"window_width\" = $w;\n    \"window_height\" = $h;\n}/" "$plist"

if [ "$mode" = x11 ]; then export SDL_VIDEODRIVER=x11; else unset SDL_VIDEODRIVER; fi
out=$UITEST_LOGS/game.out
( cd "$dir" && APPIMAGE_EXTRACT_AND_RUN=1 exec setsid ./oolite.AppImage ) >"$out" 2>&1 &
pid=$!
sleep 1
kill -0 "$pid" 2>/dev/null || { rm -rf "$dir"; die "the game exited at once (see $out): $(tail -3 "$out" 2>/dev/null | tr '\n' ' ')"; }
state_set GAME_PID "$pid"
state_set GAME_DIR "$dir"
state_set GAME_MODE "$mode"
state_set GAME_WINDOW "$window"
state_set GAME_OUT "$out"
echo "launched: $(basename "$app") --game $mode --window $window (pid $pid, folder $dir, SDL_VIDEODRIVER=${SDL_VIDEODRIVER:-unset})"
