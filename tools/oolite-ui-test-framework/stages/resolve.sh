#!/bin/bash
# resolve.sh DISTRO DESKTOP SESSION STAGE: print the script that runs STAGE for that run, from the most specific folder that has it:
#   combos/<distro>+<desktop>/<session>/  ->  desktops/<desktop>/<session>/  ->  sessions/<session>/  ->  common/
# The first hit wins. The tree is this script's folder, or $UITEST_STAGES.
# Exit 0 and print the script; exit 1 and print nothing if no folder has the stage; exit 2 (with a message on stderr) if the
# arguments are wrong: not four of them, an empty one, or one with '/' or '..' in it (it would reach outside the tree).
[ $# -eq 4 ] || { echo "resolve.sh: needs 4 arguments, got $#. Usage: resolve.sh DISTRO DESKTOP SESSION STAGE" >&2; exit 2; }
for a in "$@"; do
    case $a in
        ''|*/*|*..*) echo "resolve.sh: bad name '$a': names are not empty and have no '/' or '..'. Usage: resolve.sh DISTRO DESKTOP SESSION STAGE" >&2; exit 2 ;;
    esac
done
root=${UITEST_STAGES:-$(cd "$(dirname "$0")" && pwd)}
[ -d "$root" ] || { echo "resolve.sh: stages folder '$root' does not exist: unset UITEST_STAGES, or point it at the stages/ folder" >&2; exit 2; }
for dir in "combos/$1+$2/$3" "desktops/$2/$3" "sessions/$3" common; do
    if [ -f "$root/$dir/$4.sh" ]; then echo "$root/$dir/$4.sh"; exit 0; fi
done
exit 1
