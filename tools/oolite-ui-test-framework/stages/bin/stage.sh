#!/bin/bash
# stage.sh NAME [ARGS]: run one stage for this container's run ($UITEST_DISTRO, $UITEST_DESKTOP, $UITEST_SESSION).
# stage.sh which NAME: only print which script that would be.
# stage.sh list: print the stages that exist for this run.
# A stage is a *.sh file that starts with a #! line; lib.sh and gnome.sh are sourced helpers, not stages.
# No set -e: this script reports each problem itself, with the command that fixes it.
set -u
usage="usage: stage.sh NAME [ARGS] | stage.sh which NAME | stage.sh list"
for v in UITEST_STAGES UITEST_DISTRO UITEST_DESKTOP UITEST_SESSION; do
    [ -n "${!v:-}" ] || { echo "stage.sh: $v is not set. stage.sh runs inside the container started by \`uitest stages shell DISTRO DESKTOP SESSION --build APPIMAGE\`, which sets UITEST_STAGES, UITEST_DISTRO, UITEST_DESKTOP and UITEST_SESSION" >&2; exit 2; }
done
[ -x "$UITEST_STAGES/resolve.sh" ] || { echo "stage.sh: no resolve.sh in UITEST_STAGES=$UITEST_STAGES: it must be the stages/ folder (mounted at /stages in the container)" >&2; exit 2; }

# stages_here: the stage names that resolve for this run, one per line
stages_here() {
    local d f n
    for d in "combos/$UITEST_DISTRO+$UITEST_DESKTOP/$UITEST_SESSION" "desktops/$UITEST_DESKTOP/$UITEST_SESSION" "sessions/$UITEST_SESSION" common; do
        for f in "$UITEST_STAGES/$d"/*.sh; do
            [ -f "$f" ] && [ "$(head -c2 "$f")" = '#!' ] && { n=$(basename "$f" .sh); echo "$n"; }
        done
    done | sort -u
}

[ $# -ge 1 ] || { echo "stage.sh: no stage given. $usage. Stages for $UITEST_DISTRO $UITEST_DESKTOP $UITEST_SESSION: $(stages_here | tr '\n' ' ')" >&2; exit 2; }
if [ "$1" = list ]; then stages_here; exit 0; fi
show=0; if [ "$1" = which ]; then show=1; shift; fi
[ $# -ge 1 ] || { echo "stage.sh: which needs a stage name: stage.sh which NAME" >&2; exit 2; }
name=$1; shift
f=$("$UITEST_STAGES/resolve.sh" "$UITEST_DISTRO" "$UITEST_DESKTOP" "$UITEST_SESSION" "$name" 2>/dev/null) || {
    echo "stage.sh: no stage '$name' for $UITEST_DISTRO $UITEST_DESKTOP $UITEST_SESSION. Stages that exist for this run: $(stages_here | tr '\n' ' ')" >&2
    exit 2
}
if [ $show = 1 ]; then echo "$f"; exit 0; fi
echo "stage $name: ${f#"$UITEST_STAGES"/}" >&2
exec bash "$f" "$@"
