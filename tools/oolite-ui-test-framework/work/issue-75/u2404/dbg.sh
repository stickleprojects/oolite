chmod 1777 /tmp/.X11-unix 2>/dev/null; mkdir -p /run/dbus; dbus-daemon --system --fork 2>/dev/null
python3 -m dbusmock --system --template logind >/tmp/mock.log 2>&1 & sleep 2
sed -n '/^cat > \/tmp\/user.sh/,/^IN$/p' /run.sh | sed '1d;$d' | sed '/^sleep 20$/,$d' > /tmp/u.sh; echo 'sleep 15; echo "--- gs.log"; grep -vE "^\s*$" /tmp/gs.log | grep -iE "error|critical|warn|fail|abort" | head -15; pgrep -a gnome-shell | head -2' >> /tmp/u.sh
chmod 755 /tmp/u.sh; runuser -u ubuntu -- bash /tmp/u.sh
