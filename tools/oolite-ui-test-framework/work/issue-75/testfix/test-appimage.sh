#!/bin/bash
# Usage: test-appimage.sh /abs/path/X.AppImage OUTDIR
# Runs the AppImage 3x natively (Wayland) on Ubuntu 26.04 GNOME 50 headless; prints RESULT lines; screenshots to OUTDIR.
# Pass: every RESULT shows "wayland frame=1280x7xx" with height > 720 (a title bar), libdecor-loaded > 0, and the screenshot shows a title bar.
set -e; A="$1"; O="$2"; mkdir -p "$O"; chmod +x "$A"
docker run --rm -v /tmp/claude-1000/-mnt-NTFSData-code-oolite/82807571-8b57-430c-afa7-f9ea86743c03/scratchpad/testfix/run.sh:/run.sh:ro -v "$A":/app/test.AppImage:ro -v "$O":/out oolite-repro-ubuntu-headed bash /run.sh 2>&1 | grep "^RESULT"
