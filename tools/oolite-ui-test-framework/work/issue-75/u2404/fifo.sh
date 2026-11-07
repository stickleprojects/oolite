apt-get install -y -qq wayland-utils >/dev/null 2>&1 || (apt-get update -qq >/dev/null 2>&1; apt-get install -y -qq wayland-utils >/dev/null 2>&1)
mkdir -p /tmp/.X11-unix; chmod 1777 /tmp/.X11-unix; mkdir -p /run/dbus; dbus-daemon --system --fork 2>/dev/null
python3 -m dbusmock --system --template logind >/tmp/mock.log 2>&1 & sleep 2
cat > /tmp/u.sh <<'IN'
export XDG_RUNTIME_DIR=/tmp/xdg-ubuntu; mkdir -p -m 700 $XDG_RUNTIME_DIR; export LIBGL_ALWAYS_SOFTWARE=1 HOME=/home/ubuntu
[ -z "$DBUS_SESSION_BUS_ADDRESS" ] && exec dbus-run-session -- bash "$0"
gnome-shell --headless --wayland --virtual-monitor 1920x1080 --wayland-display wayland-gnome >/tmp/gs.log 2>&1 &
sleep 15
echo "$(gnome-shell --version): fifo-v1 offered: $(WAYLAND_DISPLAY=wayland-gnome wayland-info 2>/dev/null | grep -c 'wp_fifo_manager_v1')  commit-timing: $(WAYLAND_DISPLAY=wayland-gnome wayland-info 2>/dev/null | grep -c 'wp_commit_timing_manager_v1')  total interfaces: $(WAYLAND_DISPLAY=wayland-gnome wayland-info 2>/dev/null | grep -c 'interface:')"
IN
chmod 755 /tmp/u.sh; runuser -u ubuntu -- bash /tmp/u.sh
