#!/bin/bash
# #75 before-check: 2 releases x 3 launches on Ubuntu 24.04 GNOME 46 (headless), measured by GNOME and screenshotted.
chmod 1777 /tmp/.X11-unix 2>/dev/null; mkdir -p /run/dbus; dbus-daemon --system --fork 2>/dev/null
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
