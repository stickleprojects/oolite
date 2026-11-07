Mirror of upstream OoliteProject/oolite#793. A player (oocube) reports that the Oolite game window has no window decorations (title bar or frame) on Ubuntu 26.04. On Ubuntu 24.04 it does. mcarans asked whether our test platform reproduces it.

**Goal:** reproduce it in the UI-test framework on an Ubuntu 26.04 GNOME setup, then find the cause.

## What Ubuntu 26.04's desktop is (checked in `oolite-uitest-ubuntu`, 26.04.1 LTS)
- `ubuntu-desktop-minimal` pulls in `gnome-shell` 50.1, which depends on `gir1.2-mutter-18`. The compositor is **mutter 50.1** (`libmutter-18-0`).
- No X11 GNOME session package is on offer, and `gnome-session` depends on `xwayland`. GNOME 50 is Wayland-only, so X11 apps run under XWayland.
- Ubuntu 24.04 has mutter 46.2.
- For comparison, our Arch `wayland` image has mutter 51.1 and libdecor 0.2.5, but our `mutter-*` environments do not run on Ubuntu.

## Hypotheses (none of these has been tested)
1. **SDL3 picks its Wayland driver, and the window gets no client-side decorations.** mutter does not draw server-side decorations for Wayland clients, so SDL3 needs libdecor to draw them. The release and master AppImages bundle libSDL3 0.4.18 without libdecor. Only `fedora-built.AppImage` has `libdecor-0.so.0`. If the window is decorated or not, it depends on whether SDL finds a libdecor on the host, and on whether that libdecor has a working GTK plugin.
2. **XWayland path:** with `SDL_VIDEODRIVER=x11`, mutter 50 should frame the window itself. If it does not, the cause is related to OoliteProject/oolite#773 (the window loses its title bar after the splash screen).
3. **Why 24.04 is fine:** the user may have been on an X11 session, which 24.04 still offers. Or mutter 46 behaves differently. We need to ask which session they used.

## Plan
- [ ] Add mutter environments on the Ubuntu image (`mutter-ubuntu-xwayland`, `mutter-ubuntu-native`, `distro = "Ubuntu 26.04"`), using the same start lines as `mutter-xwayland`/`mutter-native`. They build on #74.
- [ ] Run the release and master AppImages there. Record which SDL video driver gets picked (`SDL_VIDEODRIVER` unset, `wayland`, `x11`) and whether libdecor gets loaded (`LD_DEBUG=libs` or `/proc/<pid>/maps`).
- [ ] Decide "framed" on XWayland with the existing `framed` probe. On mutter-native we have no window probe (#45) and no screenshots (#44), so decorations there cannot be judged yet. That gap is part of this issue. Close it, don't skip it.
- [ ] Compare with Ubuntu 24.04 (mutter 46) to confirm the "not on 24" half of the report.
- [ ] Report the findings on OoliteProject/oolite#793 (ask the user which session they use and what `echo $XDG_SESSION_TYPE` prints).

Related: #74 (Ubuntu/Fedora hosts), OoliteProject/oolite#773 and OoliteProject/oolite#774 (title bar lost after the splash on X11), #44, #45 (mutter-native observation gaps), OoliteProject/oolite#769 (1.92.1 AppImage on Ubuntu 26.04).
