# Ubuntu 24.04 with the full desktop package set (as a user's install), for the #75 "before" check
FROM ubuntu:24.04
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y ubuntu-desktop python3-dbusmock 2>&1 | tail -1
