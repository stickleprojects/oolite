## Cause: theory and evidence

**Summary:** the AppImage's SDL3 *can* draw a title bar on GNOME Wayland, but our packaging tool disables that. `quick-sharun.sh` renames the libdecor library that SDL3 asks for to a name that doesn't exist, because our build doesn't bundle libdecor.

### Why only GNOME on Wayland
- **X11** (any desktop): the window manager draws every window's title bar.
- **Wayland on KDE or sway**: the compositor draws it if the app asks (`xdg-decoration` protocol). This is from documentation; not tested here.
- **Wayland on GNOME**: GNOME doesn't implement `xdg-decoration`, so the app must draw its own title bar. SDL3 does that with **libdecor** ([SDL3 Wayland README](https://docs.rs/crate/sdl3-src/latest/source/SDL/docs/README-wayland.md): "If this library is not installed, the decorations will be missing").
- SDL3 prefers Wayland by default, and GNOME 50 (Ubuntu 26.04) is Wayland-only, so every player on default Ubuntu 26.04 takes this path.

### Evidence (upstream `Oolite-1.93.1-253-deployment-x86_64.AppImage`, Ubuntu 26.04 `ubuntu-desktop`, GNOME 50.1)
| Check | Result |
|---|---|
| Default launch | Native Wayland, **no title bar** (confirmed by eye, screenshot above); GNOME frame 1280×720 = content |
| `SDL_VIDEODRIVER=x11` | XWayland, **title bar present** (confirmed by eye); GNOME frame 1280×**759** (39 px title bar) |
| libdecor on the system | Installed by `ubuntu-desktop`: `libdecor-0-0` and `libdecor-0-plugin-1-gtk` 0.2.5 |
| libdecor loaded by the game | No (`/proc/<pid>/maps`) |
| What SDL3 tried to load (`LD_DEBUG=libs`) | Not `libdecor-0.so.0` but a **renamed file that doesn't exist** (see below); not found anywhere |
| libdecor copied into the extracted AppImage | Still not loaded, no title bar (SDL3 never asks for that name) |

### Where the rename comes from
- The release AppImage is built on Arch (`build-all.yaml`). `install_packages_root.sh` installs Arch's `sdl3` (3.4.18), and `create_appimage_fn.sh` packages it with `quick-sharun.sh`, **downloaded from the main branch of pkgforge-dev/Anylinux-AppImages at build time (not pinned)**.
- Arch's own `libSDL3.so.0.4.18` lists `libdecor-0.so.0` among the libraries it loads at run time. The copy in the AppImage has the same list, except that one name is replaced.
- quick-sharun does this on purpose ([lines 4701–4749](https://github.com/pkgforge-dev/Anylinux-AppImages/blob/7cb538a024588e29de89c2cea19cee8c9eca31c7/useful-tools/quick-sharun.sh#L4701-L4749)). If `libdecor-0.so*` was not deployed into the AppImage, it rewrites the string `libdecor-0.so` in every bundled library to a placeholder name (a profanity aimed at GNOME, so not repeated here). The comment above the code explains: without libdecor bundled, the app must not load the host's.
- libdecor is only deployed when `DEPLOY_SDL=1` is set **and** libdecor is installed on the build machine ([lines 1251–1259](https://github.com/pkgforge-dev/Anylinux-AppImages/blob/7cb538a024588e29de89c2cea19cee8c9eca31c7/useful-tools/quick-sharun.sh#L1251-L1259)). Our build does neither: `DEPLOY_SDL` isn't set, and Arch's `sdl3` doesn't depend on `libdecor`.
- When libdecor *is* deployed, quick-sharun adds a start-up hook that, on GNOME Wayland only, points libdecor at the **host's** decoration plugins, e.g. the GTK plugin Ubuntu installs ([lines 2316–2363](https://github.com/pkgforge-dev/Anylinux-AppImages/blob/7cb538a024588e29de89c2cea19cee8c9eca31c7/useful-tools/quick-sharun.sh#L2316-L2363)). Its comments object to GNOME requiring client-side decorations.
- (Line numbers are for quick-sharun commit `7cb538a`, 2026-11-06. The 1.93.1-253 build (2026-11-05) used whatever was on main then; the rename is visible in its SDL3.)

### Options (none proven yet: each will be tested before we suggest it)
1. **Bundle libdecor via quick-sharun's own switch**: install `libdecor` on the Arch build machine for AppImage builds, and set `DEPLOY_SDL=1` in `create_appimage_fn.sh`. Expected: no rename; SDL3 loads the bundled libdecor, which uses the host's GTK plugin on GNOME Wayland.
2. **Players' workaround**: launch with `SDL_VIDEODRIVER=x11` (shown working above). Not a fix.
3. **Pin `quick-sharun.sh`** to a commit (already suggested in OoliteProject/oolite#777). It doesn't fix this by itself, but without it, behaviour like this rename can change between builds with no change on our side.

Note: quick-sharun doesn't support Fedora's `/usr/lib64` layout (OoliteProject/oolite#777, OoliteProject/oolite#782), which is why AppImages are no longer built on Fedora. Option 1 only touches the Arch (and Ubuntu CI) AppImage builds.

**Next:** prove option 1 on the existing 1.93.1-253 AppImage first (restore the name in its SDL3 and add libdecor to the bundle, then run headed on the same Ubuntu 26.04 GNOME setup). Then try a real build with the change. After that, ask the upstream maintainers for input.
