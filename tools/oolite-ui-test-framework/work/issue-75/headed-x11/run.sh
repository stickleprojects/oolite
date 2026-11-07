#!/bin/bash
# Headed repro for #75: GNOME 50 on a full Ubuntu 26.04 desktop install, shown in a mutter-devkit window on the host's X display.
chmod 1777 /tmp/.X11-unix; mkdir -p /run/dbus; dbus-daemon --system --fork 2>/dev/null
python3 -m dbusmock --system --template logind >/tmp/mock.log 2>&1 & sleep 2
cat > /tmp/user.sh <<'IN'
export XDG_RUNTIME_DIR=/tmp/xdg-ubuntu; mkdir -p -m 700 $XDG_RUNTIME_DIR; export LIBGL_ALWAYS_SOFTWARE=1 HOME=/home/ubuntu
[ -z "$DBUS_SESSION_BUS_ADDRESS" ] && exec dbus-run-session -- bash "$0"
pipewire >/tmp/pw.log 2>&1 & sleep 1; wireplumber >/tmp/wp.log 2>&1 & sleep 2
DISPLAY=:0 XAUTHORITY=/host-xauth gnome-shell --wayland --devkit --unsafe-mode --wayland-display wayland-gnome >/tmp/gs.log 2>&1 &
sleep 20
ev() { gdbus call --session -d org.gnome.Shell -o /org/gnome/Shell -m org.gnome.Shell.Eval "$1"; }
ev 'Main.overview.hide(); "ok"' >/dev/null
XW=$(ls $XDG_RUNTIME_DIR/.mutter-Xwaylandauth.* 2>/dev/null | head -1); XD=:$(ls /tmp/.X11-unix | sed -n 's/^X//p' | grep -v '^0$' | head -1)
echo "gnome-shell running: $(pgrep -c gnome-shell)   devkit viewer: $(pgrep -c mutter-devkit)"
export WAYLAND_DISPLAY=wayland-gnome DISPLAY=$XD XAUTHORITY=$XW XDG_SESSION_TYPE=wayland XDG_CURRENT_DESKTOP=ubuntu:GNOME
echo "game env: WAYLAND_DISPLAY=$WAYLAND_DISPLAY DISPLAY=$DISPLAY SDL_VIDEODRIVER=x11"
cd /tmp; SDL_VIDEODRIVER=x11 APPIMAGE_EXTRACT_AND_RUN=1 /app/oolite.AppImage >/tmp/game.out 2>&1 &
sleep 45
PID=$(pgrep -n -x oolite); echo "game pid: $PID"
echo "libdecor loaded: $(grep -o '/[^ ]*libdecor[^ ]*' /proc/$PID/maps 2>/dev/null | sort -u | tr '\n' ' ')"
gdbus call --session -d org.gnome.Shell.Screenshot -o /org/gnome/Shell/Screenshot -m org.gnome.Shell.Screenshot.Screenshot false false /out/headed.png >/dev/null && echo "screenshot saved"
echo "READY: look at the 'Mutter Development Kit' window. Container stays up 15 min (docker stop oolite-75-headed)."
sleep 900
IN
chmod 755 /tmp/user.sh; mkdir -p /out; chmod 777 /out; runuser -u ubuntu -- bash /tmp/user.sh
