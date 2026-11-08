#!/bin/bash
# resolve.sh DISTRO DESKTOP SESSION STAGE: print the script that runs STAGE for that run, from the most specific folder that has it:
#   combos/<distro>+<desktop>/<session>/  ->  desktops/<desktop>/<session>/  ->  sessions/<session>/  ->  common/
# The first hit wins. Exit 1 (and print nothing) if no folder has it. The tree is this script's folder, or $UITEST_STAGES.
[ $# -eq 4 ] || { echo "usage: resolve.sh DISTRO DESKTOP SESSION STAGE" >&2; exit 2; }
root=${UITEST_STAGES:-$(cd "$(dirname "$0")" && pwd)}
for dir in "combos/$1+$2/$3" "desktops/$2/$3" "sessions/$3" common; do
    if [ -f "$root/$dir/$4.sh" ]; then echo "$root/$dir/$4.sh"; exit 0; fi
done
exit 1
