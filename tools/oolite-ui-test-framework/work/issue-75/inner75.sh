#!/bin/bash
set -x
pacman -Syu --noconfirm
pacman -Q libdecor || echo "libdecor not yet installed"
ShellScripts/Linux/install_packages_root.sh --appimage || exit 1
pacman -Q libdecor
git config --global --add safe.directory /work
rm -rf build/appimage
./mk.sh build deployment && ./mk.sh pkg-appimage deployment
rc=$?
chown -R 1000:1000 /work
exit $rc
