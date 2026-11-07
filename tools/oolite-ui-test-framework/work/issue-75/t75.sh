#!/bin/bash
apt-get update >/dev/null; apt-get install -y git ca-certificates >/dev/null 2>&1
git config --global --add safe.directory '*'
cd /work/build; rm -rf ttt
git clone --filter=blob:none --no-checkout https://github.com/gnustep/libobjc2.git ttt 2>&1 | tail -3
git -C ttt checkout fab3df291a37fefdcc7b774c507ffb2ad5db6fb8 --quiet 2>&1 | tail -3
ls ttt | head -3; git --version; rm -rf ttt
