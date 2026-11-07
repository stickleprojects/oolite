FROM oolite-uitest-ubuntu:latest
RUN apt-get update && apt-get install -y gnome-shell python3-dbusmock xwayland 2>&1 | tail -1
RUN useradd -m player
