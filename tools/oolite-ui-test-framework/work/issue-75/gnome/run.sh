#!/bin/bash
# Manual repro for #75: Ubuntu 26.04 GNOME 50 (headless), launch the AppImage as a player would, screenshot, report the window.
mkdir -p /run/dbus; dbus-daemon --system --fork 2>/dev/null
python3 -m dbusmock --system --template logind >/tmp/mock.log 2>&1 & sleep 2
cat > /tmp/player.sh <<'IN'
export XDG_RUNTIME_DIR=/tmp/xdg-player; mkdir -p -m 700 $XDG_RUNTIME_DIR; export LIBGL_ALWAYS_SOFTWARE=1 HOME=/home/player
eval $(dbus-launch --sh-syntax)
gnome-shell --headless --wayland --virtual-monitor 1920x1080 --unsafe-mode >/tmp/gs.log 2>&1 &
sleep 15
ev() { gdbus call --session -d org.gnome.Shell -o /org/gnome/Shell -m org.gnome.Shell.Eval "$1"; }
ev 'Main.overview.hide(); Main.messageTray._bannerBin.hide(); "ok"' >/dev/null
export WAYLAND_DISPLAY=wayland-0 DISPLAY=:0 XAUTHORITY=$(ls $XDG_RUNTIME_DIR/.mutter-Xwaylandauth.* 2>/dev/null | head -1) XDG_SESSION_TYPE=wayland XDG_CURRENT_DESKTOP=ubuntu:GNOME
echo "session: WAYLAND_DISPLAY=$WAYLAND_DISPLAY DISPLAY=$DISPLAY XAUTHORITY=$XAUTHORITY SDL_VIDEODRIVER=${SDL_VIDEODRIVER:-unset}"
cd /tmp; APPIMAGE_EXTRACT_AND_RUN=1 /app/oolite.AppImage >/tmp/game.out 2>&1 &
sleep 50
PID=$(pgrep -f "/oolite$|oolite.app/oolite|usr/bin/oolite" | head -1); [ -z "$PID" ] && PID=$(pgrep -n oolite)
echo "game pid: $PID ($(cat /proc/$PID/comm 2>/dev/null))"
echo "libdecor loaded: $(grep -c libdecor /proc/$PID/maps 2>/dev/null)  libdecor files: $(grep -o '/[^ ]*libdecor[^ ]*' /proc/$PID/maps 2>/dev/null | sort -u | tr '\n' ' ')"
echo "wayland client: $(grep -c libwayland-client /proc/$PID/maps 2>/dev/null)  x11 client: $(grep -c libX11.so /proc/$PID/maps 2>/dev/null)"
echo "--- windows (GNOME's view)"
ev 'JSON.stringify(global.display.list_all_windows().map(w=>({title:w.get_title(),type:w.get_client_type()==0?"wayland":"x11",decorated:w.decorated,frame:w.get_frame_rect(),buffer:w.get_buffer_rect(),focus:w.has_focus()})))'
gdbus call --session -d org.gnome.Shell.Screenshot -o /org/gnome/Shell/Screenshot -m org.gnome.Shell.Screenshot.Screenshot false false /out/screen.png >/dev/null && echo "screenshot: /out/screen.png"
LOG=$(find /home/player /tmp -name Latest.log 2>/dev/null | head -1); echo "--- game log ($LOG), video lines:"; grep -iE "sdl|video|wayland|x11|window|surface" "$LOG" 2>/dev/null | head -12
echo "--- game stdout tail"; tail -5 /tmp/game.out
IN
chmod 755 /tmp/player.sh; chmod 777 /out; runuser -u player -- bash /tmp/player.sh
