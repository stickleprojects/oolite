## Fix and testing done

**Summary.** The game window has no title bar on Ubuntu 26.04 because the AppImage does not bundle libdecor. When libdecor is not bundled, quick-sharun disables it: it renames SDL3's `libdecor-0.so` reference to a library that does not exist. GNOME does not draw title bars for native Wayland apps, so SDL3 needs libdecor to draw its own. SDL3 only uses native Wayland when the compositor offers `fifo-v1`. GNOME 50 (Ubuntu 26.04) offers it, GNOME 46 (Ubuntu 24.04) does not, so on 24.04 the game runs through XWayland and GNOME draws the title bar. Details: [reproduction](https://github.com/stickleprojects/oolite/issues/75#issuecomment-6700614287), [cause](https://github.com/stickleprojects/oolite/issues/75#issuecomment-6700835714), [timeline](https://github.com/stickleprojects/oolite/issues/75#issuecomment-6701639280).

### Options, each tested

| Option | What it is | Needs a new build | Result |
|---|---|---|---|
| Workaround | Launch with `SDL_VIDEODRIVER=x11`: the game runs through XWayland and GNOME draws the title bar | no | title bar, 3/3 launches |
| Fix | Install libdecor on the build machine, set `DEPLOY_SDL=1` so quick-sharun bundles it with SDL3, and pin quick-sharun to a known commit (`7cb538a0`) instead of `main` | yes | title bar, 3/3 launches on each build path |

The pin is part of the fix, not a separate option: quick-sharun is downloaded from `main` at build time, and the libdecor handling has changed there twice this year (see the timeline). Pinning means the build we tested is the build we ship.

Fix PR: #81 (three build-script changes).

### Testing done

All runs on a full `ubuntu-desktop` install in a container, default (Wayland) session. The window frame was measured by GNOME (`org.gnome.Shell.Eval`); a frame taller than the 720 px game area means a title bar.

**Ubuntu 26.04.1, GNOME 50.1** (3 launches each):

| AppImage | Built on | SDL3 ran on | libdecor loaded | Window frame | Title bar |
|---|---|---|---|---|---|
| 1.93.1-253 (release) | release | native Wayland | no | 1280×720 | **none** |
| 1.93.1-253, `SDL_VIDEODRIVER=x11` | release | XWayland | no | 1280×759 | yes, drawn by GNOME |
| Fix, release build path | Arch (`oolite-builddeps`) | native Wayland | yes, with GTK plugin | 1280×757 | yes, drawn by libdecor |
| Fix, CI build path | `ubuntu:26.04` (the image the Ubuntu CI job uses) | native Wayland | yes | 1280×805 | yes, drawn by libdecor |

The release AppImage and the Arch-built fix were also run headed (GNOME in the mutter devkit viewer) and checked by eye: no title bar before, title bar after.

**Ubuntu 24.04.5, GNOME 46.0** (3 launches each):

| AppImage | Ran on | Window frame | Title bar |
|---|---|---|---|
| 1.92.1.0 | XWayland | 1280×757 | yes, drawn by GNOME |
| 1.93.1-253 | XWayland | 1280×757 | yes, drawn by GNOME |

This is why the bug was not seen on 24.04: both releases run through XWayland there.

**Fixed AppImage contents** (both build paths): `libdecor-0.so.0` is bundled, `libSDL3` refers to it by its original name, and no bundled library has the renamed reference.

### Not tested

- GNOME 47 to 49 (Ubuntu 24.10 to 25.10). Expected to show the bug wherever GNOME offers `fifo-v1`.
- Other distributions' GNOME, and KDE or sway with the fixed build. KDE and sway draw title bars for Wayland apps themselves, so the fix should not change them, but that has not been checked.
- The Ubuntu-built window is 48 px taller than the Arch-built one (805 against 757). The title bar is there in both; the cause of the extra height (SDL3 3.4.2 on Ubuntu against 3.4.18 on Arch, or the build) has not been looked into.
- Only packaging and running were tested, not the rest of the CI job (its test step, the dev-build compile check).
