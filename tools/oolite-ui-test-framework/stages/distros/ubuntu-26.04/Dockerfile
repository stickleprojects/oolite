# Ubuntu 26.04 with the standard desktop package set, as a player who installed Ubuntu Desktop has it (ubuntu-desktop: GNOME 50,
# libdecor and its GTK plugin, XWayland ...). Plus what the stages need in a container: python3-dbusmock (a fake logind for
# gnome-shell), sudo (the stages run as the user `player`; only the fake logind's system bus needs root).
# Large (about 5 GB). Build context: this folder.
FROM ubuntu:26.04
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y ubuntu-desktop python3-dbusmock sudo && rm -rf /var/lib/apt/lists/*
# pytest: the framework's tests run in this image for the kind "stages" environments (environments.toml). Its own layer, so adding
# it did not rebuild the desktop layer above.
RUN apt-get update && apt-get install -y python3-pytest && rm -rf /var/lib/apt/lists/*
RUN useradd -m -s /bin/bash player && echo 'player ALL=(ALL) NOPASSWD: ALL' > /etc/sudoers.d/player && chmod 440 /etc/sudoers.d/player
# mutter (as player) makes XWayland's socket here
RUN mkdir -p /tmp/.X11-unix && chmod 1777 /tmp/.X11-unix
ENV UITEST_STAGES=/stages PATH=/stages/bin:$PATH
USER player
WORKDIR /home/player
