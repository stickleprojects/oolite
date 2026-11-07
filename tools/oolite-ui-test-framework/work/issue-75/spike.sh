set -e
apt-get update -qq >/dev/null
apt-get install -y -qq gnome-shell dbus dbus-x11 xwayland libgl1-mesa-dri x11-utils >/tmp/apt.log 2>&1 || { tail -20 /tmp/apt.log; exit 1; }
gnome-shell --version; mutter --version 2>/dev/null | head -1

gnome-shell --help 2>&1 | grep -iE "headless|unsafe|virtual|wayland" || true
export XDG_RUNTIME_DIR=/tmp/xdg; mkdir -p -m 700 $XDG_RUNTIME_DIR; export LIBGL_ALWAYS_SOFTWARE=1
eval $(dbus-launch --sh-syntax)
(gnome-shell --headless --wayland --virtual-monitor 1920x1080 --unsafe-mode --no-x11 >/tmp/gs.log 2>&1 || gnome-shell --headless --virtual-monitor 1920x1080 --unsafe-mode >/tmp/gs.log 2>&1) &
sleep 15
echo "--- log"; grep -iE "schema|error|critical" /tmp/gs.log | head -12; tail -5 /tmp/gs.log
echo "--- introspect"; gdbus call --session -d org.gnome.Shell.Introspect -o /org/gnome/Shell/Introspect -m org.gnome.Shell.Introspect.GetWindows 2>&1 | head -c 400; echo
echo "--- eval"; gdbus call --session -d org.gnome.Shell -o /org/gnome/Shell -m org.gnome.Shell.Eval 'global.display.list_all_windows().length + " " + global.context.unsafe_mode' 2>&1
echo "--- screenshot"; gdbus call --session -d org.gnome.Shell.Screenshot -o /org/gnome/Shell/Screenshot -m org.gnome.Shell.Screenshot.Screenshot false false /tmp/s.png 2>&1; ls -la /tmp/s.png 2>&1
