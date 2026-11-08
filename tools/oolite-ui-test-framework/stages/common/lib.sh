# Sourced by every stage script. Stages hand over through the state file: a stage that sets up something later stages need
# (WAYLAND_DISPLAY, DISPLAY, the game's pid ...) saves it with state_set, and every stage starts by sourcing the file.
# So any stage can be run by hand, in any shell in the container, after the ones before it.
UITEST_STATE=${UITEST_STATE:-/tmp/uitest/state.env}
UITEST_LOGS=${UITEST_LOGS:-/tmp/uitest/logs}
UITEST_OUT=${UITEST_OUT:-/out}
mkdir -p "$(dirname "$UITEST_STATE")" "$UITEST_LOGS"; touch "$UITEST_STATE"
. "$UITEST_STATE"

die() { echo "$(basename "$0"): $*" >&2; exit 1; }

# state_set NAME VALUE: export it now and save it for later stages (replacing an earlier value)
state_set() {
    export "$1=$2"
    sed -i "/^export $1=/d" "$UITEST_STATE"
    printf 'export %s=%q\n' "$1" "$2" >> "$UITEST_STATE"
}

# state_unset NAME: remove it now and for later stages
state_unset() { unset "$1"; sed -i "/^export $1=/d" "$UITEST_STATE"; }

# wait_for SECONDS COMMAND...: run COMMAND every 0.5 s until it succeeds; fail after SECONDS
wait_for() {
    local n=$(( $1 * 2 )); shift
    while (( n-- > 0 )); do "$@" >/dev/null 2>&1 && return 0; sleep 0.5; done
    return 1
}
