# Sourced by the GNOME stage scripts (not a stage itself). GNOME Shell's Eval runs JavaScript inside the shell; it needs
# gnome-shell --unsafe-mode. That is how windows are observed: GNOME's own view, the one the player gets.

# shell_js JS: print the string JS evaluates to (not a bare string literal: Eval reports a ReferenceError for "up"; use String("up")); fail if the shell is not up or the JS threw
shell_js() {
    local r
    r=$(gdbus call --session -d org.gnome.Shell -o /org/gnome/Shell -m org.gnome.Shell.Eval "$1" 2>/dev/null) || return 1
    # gdbus prints a GVariant tuple: (true, 'result') on success, (false, 'error') if the JavaScript threw
    python3 -c '
import ast, json, sys
t = sys.argv[1].strip()
ok = t.startswith("(true,")
s = ast.literal_eval("(" + t[t.index(",") + 1:].strip())
s = s[0] if isinstance(s, tuple) else s
# GNOME 50 returns the value JSON-encoded: a string comes back in double quotes with its own quotes escaped
if ok and s.startswith("\"") and s.endswith("\""): s = json.loads(s)
print(s) if ok else print(s, file=sys.stderr)
sys.exit(0 if ok else 1)' "$r"
}

# shell_screenshot PATH: a screenshot of the whole screen, through GNOME Shell's own Screenshot D-Bus API
shell_screenshot() {
    gdbus call --session -d org.gnome.Shell.Screenshot -o /org/gnome/Shell/Screenshot \
        -m org.gnome.Shell.Screenshot.Screenshot false false "$1" >/dev/null
}

# shell_screenshot_area X Y W H PATH: a screenshot of that part of the screen (screen coordinates), through the same API
shell_screenshot_area() {
    gdbus call --session -d org.gnome.Shell.Screenshot -o /org/gnome/Shell/Screenshot \
        -m org.gnome.Shell.Screenshot.ScreenshotArea "$1" "$2" "$3" "$4" false "$5" >/dev/null
}
