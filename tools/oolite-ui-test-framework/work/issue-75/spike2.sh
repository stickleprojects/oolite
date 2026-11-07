apt-get update -qq >/dev/null; apt-get install -y -qq gnome-shell dbus-x11 x11-utils x11-apps python3-dbusmock >/tmp/apt.log 2>&1 || { tail -5 /tmp/apt.log; exit 1; }
mkdir -p /run/dbus; dbus-daemon --system --fork 2>/dev/null; python3 -m dbusmock --system --template logind >/tmp/mock.log 2>&1 & sleep 2
export XDG_RUNTIME_DIR=/tmp/xdg; mkdir -p -m 700 $XDG_RUNTIME_DIR; export LIBGL_ALWAYS_SOFTWARE=1
eval $(dbus-launch --sh-syntax)
gnome-shell --headless --wayland --virtual-monitor 1920x1080 --unsafe-mode >/tmp/gs.log 2>&1 &
sleep 20
echo "--- alive?"; pgrep -a gnome-shell || { grep -B2 -A8 "JS ERROR" /tmp/gs.log | head -30; }
grep -iE "critical|warning" /tmp/gs.log | sort | uniq -c | sort -rn | head -8
echo "--- introspect"; gdbus call --session -d org.gnome.Shell.Introspect -o /org/gnome/Shell/Introspect -m org.gnome.Shell.Introspect.GetWindows 2>&1 | head -c 300; echo
echo "--- eval"; gdbus call --session -d org.gnome.Shell -o /org/gnome/Shell -m org.gnome.Shell.Eval 'global.display.list_all_windows().length + " unsafe=" + global.context.unsafe_mode' 2>&1
echo "--- xwayland client"; ls $XDG_RUNTIME_DIR; (DISPLAY=:0 xlogo &) ; sleep 4
gdbus call --session -d org.gnome.Shell -o /org/gnome/Shell -m org.gnome.Shell.Eval 'JSON.stringify(global.display.list_all_windows().map(w=>({t:w.get_title(),c:w.get_wm_class(),dec:w.decorated,frame:w.get_frame_rect(),buf:w.get_buffer_rect(),x11:w.get_client_type(),focus:w.has_focus()})))' 2>&1 | head -c 800; echo
echo "--- screenshot"; gdbus call --session -d org.gnome.Shell.Screenshot -o /org/gnome/Shell/Screenshot -m org.gnome.Shell.Screenshot.Screenshot false false /tmp/s.png 2>&1; ls -la /tmp/s.png 2>&1
