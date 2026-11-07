#!/bin/bash
# #75 check 2 + 3: (A) as-is with LD_DEBUG=libs; (B) extracted, with the system libdecor copied into the bundle's lib/.
chmod 1777 /tmp/.X11-unix 2>/dev/null; mkdir -p /run/dbus; dbus-daemon --system --fork 2>/dev/null
python3 -m dbusmock --system --template logind >/tmp/mock.log 2>&1 & sleep 2
cat > /tmp/user.sh <<'IN'
export XDG_RUNTIME_DIR=/tmp/xdg-ubuntu; mkdir -p -m 700 $XDG_RUNTIME_DIR; export LIBGL_ALWAYS_SOFTWARE=1 HOME=/home/ubuntu
[ -z "$DBUS_SESSION_BUS_ADDRESS" ] && exec dbus-run-session -- bash "$0"
gnome-shell --headless --wayland --virtual-monitor 1920x1080 --unsafe-mode --wayland-display wayland-gnome >/tmp/gs.log 2>&1 &
sleep 20
ev() { gdbus call --session -d org.gnome.Shell -o /org/gnome/Shell -m org.gnome.Shell.Eval "$1"; }
ev 'Main.overview.hide(); "ok"' >/dev/null
export WAYLAND_DISPLAY=wayland-gnome XDG_SESSION_TYPE=wayland XDG_CURRENT_DESKTOP=ubuntu:GNOME
win() { ev 'JSON.stringify(global.display.list_all_windows().map(w=>{let f=w.get_frame_rect(),b=w.get_buffer_rect();return {title:w.get_title(),frame:[f.x,f.y,f.width,f.height],buffer:[b.x,b.y,b.width,b.height]}}))'; }
shot() { gdbus call --session -d org.gnome.Shell.Screenshot -o /org/gnome/Shell/Screenshot -m org.gnome.Shell.Screenshot.Screenshot false false /out/$1.png >/dev/null && echo "screenshot /out/$1.png"; }
echo "=== C: AppImage as-is, SDL_VIDEODRIVER=x11"
export DISPLAY=:$(ls /tmp/.X11-unix | sed -n 's/^X//p' | head -1) XAUTHORITY=$(ls $XDG_RUNTIME_DIR/.mutter-Xwaylandauth.* | head -1)
echo "DISPLAY=$DISPLAY"
cd /tmp; SDL_VIDEODRIVER=x11 APPIMAGE_EXTRACT_AND_RUN=1 /app/oolite.AppImage >/tmp/C.out 2>&1 &
sleep 45; PID=$(pgrep -n -x oolite); echo "game pid: $PID"
ev 'JSON.stringify(global.display.list_all_windows().map(w=>{let f=w.get_frame_rect(),b=w.get_buffer_rect();return {title:w.get_title(),type:w.get_client_type()==0?"wayland":"x11",decorated:w.decorated,frame:[f.x,f.y,f.width,f.height],buffer:[b.x,b.y,b.width,b.height]}}))'
shot C; tail -3 /tmp/C.out
IN
chmod 755 /tmp/user.sh; mkdir -p /out; chmod 777 /out; runuser -u ubuntu -- bash /tmp/user.sh
