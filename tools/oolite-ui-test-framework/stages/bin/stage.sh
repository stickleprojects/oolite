#!/bin/bash
# stage.sh NAME [ARGS]: run one stage for this container's run ($UITEST_DISTRO, $UITEST_DESKTOP, $UITEST_SESSION).
# stage.sh which NAME: only print which script that would be.
[ $# -ge 1 ] || { echo "usage: stage.sh NAME [ARGS] | stage.sh which NAME" >&2; exit 2; }
show=0; [ "$1" = which ] && { show=1; shift; }
name=$1; shift
f=$("$UITEST_STAGES/resolve.sh" "$UITEST_DISTRO" "$UITEST_DESKTOP" "$UITEST_SESSION" "$name") ||
    { echo "stage.sh: no '$name' script for $UITEST_DISTRO $UITEST_DESKTOP $UITEST_SESSION" >&2; exit 2; }
[ $show = 1 ] && { echo "$f"; exit 0; }
echo "stage $name: ${f#"$UITEST_STAGES"/}" >&2
exec bash "$f" "$@"
