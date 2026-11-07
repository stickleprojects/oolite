# Ubuntu 26.04 with the full desktop package set (as the installer's extended selection), for the #75 repro
FROM ubuntu:26.04
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y ubuntu-desktop python3-dbusmock 2>&1 | tail -1
RUN useradd -m player
