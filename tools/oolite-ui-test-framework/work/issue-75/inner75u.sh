#!/bin/bash
set -x
apt update
apt install -y git curl ca-certificates
(cd / && git config --global --add safe.directory '*')
cd /work
rm -rf build/appimage build/meson_deployment build/libobjc2 build/libs-base build/tools-make
ShellScripts/Linux/install_packages_root.sh --core+appimage || exit 1
dpkg -l | grep -i libdecor
git config --global -l; env | grep -i -E "home|git"; ls -la /root/.gitconfig; git --version
ShellScripts/Linux/build_gnustep.sh system || exit 1
echo "/usr/local/lib" | tee -a /etc/ld.so.conf
ldconfig
ShellScripts/Linux/install_mozilla_js.sh system || exit 1
./mk.sh build deployment && ./mk.sh pkg-appimage deployment
rc=$?
chown -R 1000:1000 /work
exit $rc
