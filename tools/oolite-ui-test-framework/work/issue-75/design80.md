## Design (agreed 2026-11-07)

A run is **distro × desktop × session × game mode**. Each script comes from the most specific folder that has it:
`combos/<distro>+<desktop>/<session>/` → `desktops/<desktop>/<session>/` → `sessions/<session>/` → `common/`. The first hit wins.

- **Distro**: packages only (one Dockerfile per distro version, with the standard desktop package set a user would have).
- **Desktop + session**: how to start the desktop, observe windows and inject input.
- **Game mode** (launch option): `native` (SDL picks; Wayland when available) or `x11` (forced, so through XWayland on a Wayland desktop).
- **Combos**: only real exceptions for one distro+desktop.

### Why X11 and Wayland scale differently

| | X11 | Wayland |
|---|---|---|
| Who draws the title bar | always the window manager | depends on the compositor. KDE draws it; GNOME makes the app draw it (libdecor), see #75 |
| Observe windows | one generic way (xprop/xdotool) for every WM | no standard: GNOME Eval, KWin script, sway IPC; weston none |
| Inject keys/clicks | one generic way (XTEST) | per compositor |

A new X11 desktop is one `start.sh`. A new Wayland desktop needs `start`, `observe` and `input`.

### Folder tree

```
common/
  launch-linux.sh        game-mode switch: native | x11 (SDL_VIDEODRIVER=x11)
  launch-windows.ps1
  collect.sh  tidyup.sh

sessions/                          what all desktops of one session type share
  x11/
    start-xserver.sh               Xvfb / Xephyr
    observe.sh                     xprop/xdotool: title bar, focus, position (any X11 WM)
    input.sh                       XTEST (any X11 WM)
  wayland/
    start-xwayland.sh              lets X11 apps (or the game in x11 mode) run inside
    observe-xwayland.sh            sessions/x11/observe.sh, on the game's X11 window
    (no generic observe/input: each Wayland desktop brings its own)

desktops/
  gnome/
    wayland/  start.sh             gnome-shell --headless --wayland
              observe.sh           GNOME Eval (windows, decorated, focus); Screenshot D-Bus
              input.sh             mutter virtual input device (to prove)
    x11/      start.sh             gnome-shell --x11 (older distros only: GNOME 50 dropped X11)
  kde/
    wayland/  start.sh  observe.sh (KWin script)  input.sh (fake-input)
    x11/      start.sh             kwin_x11
  sway/
    wayland/  start.sh  observe.sh (sway IPC)  input.sh (virtual keyboard/pointer)
  weston/
    wayland/  start.sh             no observe/input exists: launch only (#45)
  xfce/  mate/  cinnamon/  openbox/
    x11/      start.sh

distros/
  ubuntu-26.04/  Dockerfile        apt: ubuntu-desktop …
  fedora-44/     Dockerfile        dnf: @workstation …
  debian-12/  arch/   Dockerfile
  windows/       runner/VM notes   (no Docker; launch-windows.ps1, Win32 observe)

combos/
  ubuntu-26.04+gnome/wayland/start.sh     fake logind (needed in a container)
```

### Example: #75

```
uitest run  ubuntu-26.04  gnome  wayland  --game native     what the player has
uitest run  ubuntu-26.04  gnome  wayland  --game x11        same desktop, game through XWayland
uitest run  ubuntu-24.04  gnome  x11      --game native     the "works on 24.04" side
```

The first run resolves to: Dockerfile `distros/ubuntu-26.04/`, start `combos/ubuntu-26.04+gnome/wayland/`, observe and input `desktops/gnome/wayland/`, launch `common/launch-linux.sh --game native`.

### Coverage today vs what players run

```
                 GNOME/mutter   KDE/KWin   xfwm4   marco   muffin   openbox   sway   weston
Arch (wayland)   X  N           X  N       .       .       .        .         X  N   X  N
Arch (x11)       .              .          X       X       X        X         .      .
Debian 12        X(old X11)     X          .       .       .        .         .      .
Ubuntu 26.04     .              .          .       .       .        X (#74)   .      .
Fedora 44        .              .          .       .       .        X (#74)   .      .
Windows          no UI tests
X = game as X11 app   N = game as native Wayland app   . = not tested
```

Biggest gaps: GNOME on Ubuntu and Fedora (the default desktop for most players there), and Windows.
