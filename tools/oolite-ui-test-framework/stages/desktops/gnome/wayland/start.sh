#!/bin/bash
# start.sh: GNOME Shell as a headless Wayland session (gnome-shell --headless --wayland), on a virtual monitor of
# $UITEST_SCREEN (default 1920x1080), with software rendering. XWayland comes up for X11 clients (the game in x11 mode).
# Needs logind: in a container a combo's start.sh provides a fake one, then runs this.
# Saves the session's variables (WAYLAND_DISPLAY, DISPLAY, XAUTHORITY, DBUS_SESSION_BUS_ADDRESS ...) for later stages.
. "$UITEST_STAGES/common/lib.sh"
. "$UITEST_STAGES/desktops/gnome/wayland/gnome.sh"
screen=${UITEST_SCREEN:-1920x1080}
[[ $screen =~ ^[0-9]+x[0-9]+$ ]] || die "UITEST_SCREEN must be WxH, e.g. 1920x1080, not '$screen'"
need_cmd gnome-shell dbus-daemon gdbus python3
shell_js 'String("up")' >/dev/null 2>&1 && die "GNOME Shell is already running: run \`stage.sh tidyup --all\` first"

rt=/tmp/uitest/xdg; mkdir -p "$rt"; chmod 700 "$rt"
state_set XDG_RUNTIME_DIR "$rt"
state_set XDG_SESSION_TYPE wayland
state_set XDG_CURRENT_DESKTOP "${UITEST_XDG_CURRENT_DESKTOP:-GNOME}"
state_set LIBGL_ALWAYS_SOFTWARE 1
# the session bus (Ubuntu 26.04 has no dbus-launch; dbus-daemon prints its address, then its pid)
{ read -r addr; read -r bus_pid; } < <(dbus-daemon --session --fork --print-address --print-pid) || die "dbus-daemon did not start a session bus: check that dbus-daemon runs in this container"
state_set DBUS_SESSION_BUS_ADDRESS "$addr"

gnome-shell --headless --wayland --virtual-monitor "$screen" --unsafe-mode --wayland-display uitest-wl \
    >"$UITEST_LOGS/gnome-shell.log" 2>&1 &
state_set DESKTOP_PIDS "$! $bus_pid"
state_set WAYLAND_DISPLAY uitest-wl
wait_for 90 shell_js 'String("up")' || die "GNOME Shell did not come up in 90 s (log $UITEST_LOGS/gnome-shell.log: $(tail -5 "$UITEST_LOGS/gnome-shell.log" | tr '\n' ' ')): run \`stage.sh tidyup --all\`, then \`stage.sh start\` again"
# a new session opens the overview (and may show a welcome banner) over the windows
shell_js 'Main.overview.hide(); Main.messageTray._bannerBin.hide(); String("ok")' >/dev/null

# XWayland: mutter makes the X socket and its auth file at start (the X server itself starts when the first X11 client connects)
wait_for 30 compgen -G "$rt/.mutter-Xwaylandauth.*" || die "no XWayland auth file in $rt: XWayland did not start (is the xwayland package installed?). Run \`stage.sh tidyup --all\`, then \`stage.sh start\`"
state_set XAUTHORITY "$(compgen -G "$rt/.mutter-Xwaylandauth.*" | head -1)"
state_set DISPLAY ":$(ls /tmp/.X11-unix | sed -n 's/^X//p' | sort -n | head -1)"
echo "started: $(gnome-shell --version), Wayland $WAYLAND_DISPLAY, XWayland $DISPLAY, screen $screen"
