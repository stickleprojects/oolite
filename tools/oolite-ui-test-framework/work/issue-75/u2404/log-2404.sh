#!/bin/bash
# #75 before-check: 2 releases x 3 launches on Ubuntu 24.04 GNOME 46 (headless), measured by GNOME and screenshotted.
mkdir -p /tmp/.X11-unix; chmod 1777 /tmp/.X11-unix; mkdir -p /run/dbus; dbus-daemon --system --fork 2>/dev/null
python3 -m dbusmock --system --template logind >/tmp/mock.log 2>&1 & sleep 2
cat > /tmp/user.sh <<'IN'
export XDG_RUNTIME_DIR=/tmp/xdg-ubuntu; mkdir -p -m 700 $XDG_RUNTIME_DIR; export LIBGL_ALWAYS_SOFTWARE=1 HOME=/home/ubuntu
[ -z "$DBUS_SESSION_BUS_ADDRESS" ] && exec dbus-run-session -- bash "$0"
E=$HOME/.local/share/gnome-shell/extensions/unsafe@oolite-uitest; mkdir -p $E
cat > $E/metadata.json <<'J'
{"uuid":"unsafe@oolite-uitest","name":"uitest unsafe mode","description":"lets the UI tests measure windows","shell-version":["46"]}
J
cat > $E/extension.js <<'J'
import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';
export default class UnsafeMode extends Extension { enable() { global.context.unsafe_mode = true; } disable() { global.context.unsafe_mode = false; } }
J
gsettings set org.gnome.shell disable-user-extensions false; gsettings set org.gnome.shell enabled-extensions "['unsafe@oolite-uitest']"
gnome-shell --headless --wayland --virtual-monitor 1920x1080 --wayland-display wayland-gnome >/tmp/gs.log 2>&1 &
sleep 20
echo "shell: $(gnome-shell --version)  unsafe-eval: $(gdbus call --session -d org.gnome.Shell -o /org/gnome/Shell -m org.gnome.Shell.Eval '"ok"' 2>&1 | head -1)"
ev() { gdbus call --session -d org.gnome.Shell -o /org/gnome/Shell -m org.gnome.Shell.Eval "$1"; }
ev 'Main.overview.hide(); "ok"' >/dev/null
export WAYLAND_DISPLAY=wayland-gnome XDG_SESSION_TYPE=wayland XDG_CURRENT_DESKTOP=ubuntu:GNOME
export DISPLAY=:$(ls /tmp/.X11-unix | sed -n 's/^X//p' | head -1) XAUTHORITY=$(ls $XDG_RUNTIME_DIR/.mutter-Xwaylandauth.* | head -1)
measure() {  # variant run
  ev 'JSON.stringify(global.display.list_all_windows().filter(w=>/Oolite/.test(w.get_title()||"")).map(w=>{let f=w.get_frame_rect();return (w.get_client_type()==0?"wayland":"x11")+" frame="+f.width+"x"+f.height}))' | sed 's/^(true, .//; s/.)$//'
}
SDL_LOGGING='video=info' APPIMAGE_EXTRACT_AND_RUN=1 /app/new.AppImage >/tmp/g.out 2>&1 &
sleep 35; grep -iE 'fifo|XWayland|wayland|x11' /tmp/g.out | grep -viE 'GL_|EGL' | head -5; pkill -x oolite
IN
chmod 755 /tmp/user.sh; mkdir -p /out; chmod 777 /out; runuser -u ubuntu -- bash /tmp/user.sh
