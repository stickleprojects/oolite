#!/usr/bin/env bash
# Unattended full comparison (the #14 re-baseline): every environment x screen x build, then one compare report.
#
#   ./run_unattended.sh                        # defaults below; results in results/unattended-<date>/
#   OUT=results/unattended-20261029 ./run_unattended.sh    # same folder again = resume: finished cells are not rerun
#   RUNS=3 BUILDS="stock:appimages/stock.AppImage pr774:appimages/pr774.AppImage" ./run_unattended.sh
#
# Built not to stop part-way: each build x environment x screen is its own `uitest run` (a crash or hang loses that cell only), uitest
# stops a container that runs past CELL_TIMEOUT (--cell-timeout) and `timeout` stops a uitest that hangs anyway, nothing is fatal
# (no set -e), the session is kept from suspending (systemd-inhibit) and the script ignores SIGHUP, so closing the terminal is safe.
# Progress: tail -f <OUT>/run.log; one line per cell in <OUT>/cells.tsv.
set -u
SELF=$(readlink -f "$0"); cd "$(dirname "$SELF")"   # paths below (BUILDS, OUT) are relative to the framework folder

BUILDS=${BUILDS:-"stock:appimages/stock.AppImage pr774:appimages/pr774.AppImage"}   # label:path; the first is the control
RUNS=${RUNS:-5}
X11_ENVS=${X11_ENVS:-"marco openbox xfwm4 muffin kwin mutter"}
WAYLAND_ENVS=${WAYLAND_ENVS:-"kwin-xwayland kwin-native sway-xwayland sway-native mutter-xwayland mutter-native weston-xwayland weston-native"}
X11_SCREENS=${X11_SCREENS:-"3840x1080 2head 1920x1080"}
WAYLAND_SCREENS=${WAYLAND_SCREENS:-"3840x1080 1920x1080"}   # the headless compositors have one output: no 2head
CELL_TIMEOUT=${CELL_TIMEOUT:-60}   # minutes for one environment x screen (5 runs take about 10)
SMOKE=${SMOKE:-1}                  # 1 = first a 1-run --quick smoke per environment and build (results in <OUT>/smoke)
OUT=${OUT:-results/unattended-$(date +%Y%m%d-%H%M)}
DESC=${DESC:-"Re-baseline (#14): every environment, --toggle, $RUNS runs, screens X11 [$X11_SCREENS] Wayland [$WAYLAND_SCREENS]"}

# keep the machine awake: re-run this script under systemd-inhibit once
if [ -z "${UNATTENDED_INHIBITED:-}" ] && command -v systemd-inhibit >/dev/null && systemd-inhibit --what=idle:sleep:handle-lid-switch true 2>/dev/null; then
    export UNATTENDED_INHIBITED=1 OUT
    exec systemd-inhibit --what=idle:sleep:handle-lid-switch --who=uitest --why="unattended UI test run" "$SELF" "$@"
fi
trap '' HUP

mkdir -p "$OUT/cells" "$OUT/smoke"
LOG="$OUT/run.log"; TSV="$OUT/cells.tsv"
[ -f "$TSV" ] || printf "when\tbuild\tenv\tscreen\trc\tminutes\n" > "$TSV"
log() { echo "$(date '+%F %T') $*" | tee -a "$LOG"; }

for b in $BUILDS; do
    [ -f "${b#*:}" ] || { log "MISSING build ${b#*:}: fix BUILDS and rerun"; exit 2; }
done
log "== unattended run: OUT=$OUT RUNS=$RUNS CELL_TIMEOUT=${CELL_TIMEOUT}m BUILDS=[$BUILDS]"
log "   framework $(git describe --always --dirty 2>/dev/null)"

# one `uitest run`; never fails the script. $1 = result folder, $2 = set name, $3 = label:path, rest = uitest options
cell() {
    local dir=$1 name=$2 build=$3; shift 3
    local t0=$SECONDS rc
    timeout --kill-after=2m "$((CELL_TIMEOUT + 10))m" ./uitest run "$build" --out "$dir" --name "$name" --no-prompt \
        --cell-timeout "$CELL_TIMEOUT" --desc "$DESC" "$@" >> "$LOG" 2>&1
    rc=$?
    [ $rc -eq 124 ] || [ $rc -eq 137 ] && log "   uitest itself TIMED OUT ($rc): $name"
    printf "%s\t%s\t%s\t%s\t%s\t%s\n" "$(date '+%F %T')" "${build%%:*}" "$ENV" "$SCREEN" "$rc" "$(( (SECONDS - t0) / 60 ))" >> "$TSV"
    log "   done $name rc=$rc in $(( (SECONDS - t0) / 60 )) min"
}

# a cell is finished if its result set has a RESULT, SKIP or HARD line (a resumed run skips it), except a cell that timed out before
# its first run: that one is tried again
finished() {
    grep -qsE '^(RESULT|SKIP) ' "$1.raw" && return 0
    grep -qs '^HARD ' "$1.raw" && ! grep -qs '^HARD .*reason=timed out' "$1.raw"
}

if [ "$SMOKE" = 1 ]; then
    log "== stage 1: smoke (--quick, 1 run)"
    for b in $BUILDS; do for ENV in $X11_ENVS $WAYLAND_ENVS; do
        SCREEN=smoke; n="${b%%:*}-$ENV"
        finished "$OUT/smoke/$n" && continue
        log "-- smoke $n"; cell "$OUT/smoke" "$n" "$b" --env "$ENV" --quick
    done; done
fi

log "== stage 2: full cells"
for b in $BUILDS; do
    for ENV in $X11_ENVS $WAYLAND_ENVS; do
        case " $WAYLAND_ENVS " in *" $ENV "*) screens=$WAYLAND_SCREENS ;; *) screens=$X11_SCREENS ;; esac
        for SCREEN in $screens; do
            n="${b%%:*}-$ENV-$SCREEN"
            if finished "$OUT/cells/$n"; then log "-- $n already done, skipped"; continue; fi
            log "-- $n"; cell "$OUT/cells" "$n" "$b" --env "$ENV" --screens "$SCREEN" --runs "$RUNS" --toggle
        done
    done
done

log "== stage 3: one result set per build, then the comparison"
sets=()
for b in $BUILDS; do
    l=${b%%:*}; set="$OUT/$l"
    { python3 -c 'import json,sys; print("PURPOSE " + json.dumps(sys.argv[1]))' "$DESC"
      cat "$OUT"/cells/"$l"-*.raw 2>/dev/null | grep -v '^PURPOSE '; } > "$set.raw"
    for f in "$OUT"/cells/"$l"-*-env.txt; do [ -f "$f" ] && { echo "== $(basename "$f")"; cat "$f"; echo; }; done > "$set-env.txt"
    ./uitest --report-only "$set.raw" --control "$l" --minruns "$RUNS" >> "$LOG" 2>&1 || true
    log "   $l: $set.md"
    sets+=("$set")
done
if [ ${#sets[@]} -ge 2 ]; then
    cands=(); for s in "${sets[@]:1}"; do cands+=(--candidate "$s"); done
    ./uitest compare --control "${sets[0]}" "${cands[@]}" --minruns "$RUNS" --desc "$DESC" --report "$OUT/compare.md" >> "$LOG" 2>&1
    log "   compare rc=$?: $OUT/compare.md"
fi
log "== finished. Cells: $TSV. Any rc other than 0/1 or a TIMED OUT above is worth a look."
