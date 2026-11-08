#!/bin/bash
# start.sh for Ubuntu 26.04 + GNOME, Wayland: gnome-shell needs logind, which a container does not have, so start a system bus
# with python-dbusmock's logind, then GNOME's own start.sh. Also sets Ubuntu's XDG_CURRENT_DESKTOP (ubuntu:GNOME).
# Whether GNOME on other distros needs the same is checked when they are added (#80 step 4); if so, the fake logind moves to
# desktops/gnome/wayland/ (or a helper shared by the containers) and this combo shrinks to the XDG_CURRENT_DESKTOP line.
. "$UITEST_STAGES/common/lib.sh"
[ -S /run/dbus/system_bus_socket ] || { sudo mkdir -p /run/dbus && sudo dbus-daemon --system --fork; } || die "no system bus"
if ! gdbus introspect --system -d org.freedesktop.login1 -o /org/freedesktop/login1 >/dev/null 2>&1; then
    sudo python3 -m dbusmock --system --template logind >"$UITEST_LOGS/logind-mock.log" 2>&1 &
    wait_for 15 gdbus introspect --system -d org.freedesktop.login1 -o /org/freedesktop/login1 ||
        die "fake logind did not start: $(tail -3 "$UITEST_LOGS/logind-mock.log")"
fi
UITEST_XDG_CURRENT_DESKTOP=ubuntu:GNOME exec bash "$UITEST_STAGES/desktops/gnome/wayland/start.sh" "$@"
