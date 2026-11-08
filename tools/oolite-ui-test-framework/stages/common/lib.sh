# Sourced by every stage script. Stages hand over through the state file: a stage that sets up something later stages need
# (WAYLAND_DISPLAY, DISPLAY, the game's pid ...) saves it with state_set, and every stage starts by sourcing the file.
# So any stage can be run by hand, in any shell in the container, after the ones before it.
#
# Error rule for every stage: say WHAT is wrong and HOW to fix it, naming the exact command.
#
# set -u catches a misspelled variable; pipefail makes a failing first command of a pipe count. set -e is NOT used on purpose:
# wait_for and the optional steps (a screenshot, cleaning up a process that is already gone) rely on non-zero returns. Each
# precondition is checked by hand and ends in die.
set -u -o pipefail
: "${UITEST_STAGES:?UITEST_STAGES is not set. Stages run inside the container started by \`uitest stages shell DISTRO DESKTOP SESSION --build APPIMAGE\`, through \`stage.sh NAME\`}"
UITEST_STATE=${UITEST_STATE:-/tmp/uitest/state.env}
UITEST_LOGS=${UITEST_LOGS:-/tmp/uitest/logs}
UITEST_OUT=${UITEST_OUT:-/out}

die() { echo "$(basename "$0"): $*" >&2; exit 1; }

# state_check: succeed if the state file is a list of `export NAME=value` lines that bash can read; else print what is wrong.
state_check() {
    local bad
    bad=$(grep -nvE '^(export [A-Za-z_][A-Za-z0-9_]*=.*)?$' "$UITEST_STATE" | head -1)
    [ -z "$bad" ] || { echo "line ${bad%%:*} is not 'export NAME=value': ${bad#*:}"; return 1; }
    bad=$(bash -n "$UITEST_STATE" 2>&1 | head -1)
    [ -z "$bad" ] || { echo "$bad"; return 1; }
    ( set +u; . "$UITEST_STATE" ) >/dev/null 2>&1 || { echo "bash cannot read it"; return 1; }
    return 0
}

mkdir -p "$(dirname "$UITEST_STATE")" "$UITEST_LOGS" 2>/dev/null ||
    die "cannot create $(dirname "$UITEST_STATE") or $UITEST_LOGS: make them writable, or point UITEST_STATE and UITEST_LOGS at a folder you can write"
touch "$UITEST_STATE" 2>/dev/null || die "cannot write $UITEST_STATE: fix its permissions, or delete it and run \`stage.sh start\`"
if ! why=$(state_check 2>&1); then
    # tidyup --all sets UITEST_LENIENT: it is the way out of a broken file, so it clears the file instead of stopping
    if [ -n "${UITEST_LENIENT:-}" ]; then
        echo "$(basename "$0"): state file $UITEST_STATE is malformed ($why): clearing it" >&2; : > "$UITEST_STATE"
    else
        die "state file $UITEST_STATE is malformed ($why): delete it, or run \`stage.sh tidyup --all\`"
    fi
fi
set +u; . "$UITEST_STATE"; set -u

# state_set NAME VALUE: export it now and save it for later stages (replacing an earlier value). %q quotes any value.
state_set() {
    [[ ${1:-} =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]] || die "state_set: '${1:-}' is not a variable name"
    export "$1=${2-}"
    sed -i "/^export $1=/d" "$UITEST_STATE"
    printf 'export %s=%q\n' "$1" "${2-}" >> "$UITEST_STATE"
}

# state_unset NAME: remove it now and for later stages
state_unset() { unset "$1"; sed -i "/^export $1=/d" "$UITEST_STATE"; }

# wait_for SECONDS COMMAND...: run COMMAND every 0.5 s until it succeeds; fail after SECONDS
wait_for() {
    local n=$(( $1 * 2 )); shift
    while (( n-- > 0 )); do "$@" >/dev/null 2>&1 && return 0; sleep 0.5; done
    return 1
}

# need_cmd NAME...: every tool must be installed (a stage run on the host instead of in the container lacks them)
need_cmd() {
    local c
    for c in "$@"; do
        command -v "$c" >/dev/null || die "'$c' is not installed: stages run inside the container (\`uitest stages shell DISTRO DESKTOP SESSION --build APPIMAGE\`), not on the host"
    done
}

# need_desktop DISPLAYVAR: the desktop must have been started (by \`stage.sh start\`) and still be alive.
# DISPLAYVAR is the variable that start saves for this kind of session: WAYLAND_DISPLAY for wayland, DISPLAY for x11.
need_desktop() {
    local v=$1 pid
    [ -n "${!v:-}" ] || die "no desktop running ($v not set in $UITEST_STATE): run \`stage.sh start\` first"
    pid=${DESKTOP_PIDS:-}; pid=${pid%% *}
    [ -n "$pid" ] || die "no desktop running (DESKTOP_PIDS not set in $UITEST_STATE): run \`stage.sh tidyup --all\`, then \`stage.sh start\`"
    kill -0 "$pid" 2>/dev/null || die "the desktop has died (pid $pid is gone; see ${UITEST_LOGS}/): run \`stage.sh tidyup --all\`, then \`stage.sh start\`"
}

# session_var: the display variable of this run's session type
session_var() { if [ "${UITEST_SESSION:-}" = x11 ]; then echo DISPLAY; else echo WAYLAND_DISPLAY; fi; }

# check_appimage PATH: die unless PATH is a readable regular file that starts with the ELF magic (an AppImage is an ELF file)
check_appimage() {
    local f=$1 magic
    [ -e "$f" ] || die "no AppImage at $f: pass the path of a built Oolite AppImage (\`stage.sh launch-linux PATH\`; with \`uitest stages shell\` it is /app/oolite.AppImage)"
    [ -d "$f" ] && die "$f is a folder, not an AppImage: pass the .AppImage file"
    [ -f "$f" ] || die "$f is not a regular file: pass the .AppImage file"
    [ -r "$f" ] || die "$f is not readable: fix its permissions"
    magic=$(LC_ALL=C head -c 4 "$f" | od -An -tx1 | tr -d ' \n')
    [ "$magic" = 7f454c46 ] || die "$f is not an AppImage (it does not start with the ELF magic 7f454c46; it starts with ${magic:-nothing, the file is empty}): build the AppImage again, or pass the right file"
}
