## Finding: how the missing title bar came about (timeline)

Oolite's AppImage has disabled libdecor since the move to SDL3 and quick-sharun (May 2026), so SDL3 cannot draw a title bar under GNOME Wayland. This stays hidden on older GNOME: SDL3 only uses native Wayland when the compositor offers the `fifo-v1` protocol ([SDL 3.4.18 `Wayland_IsPreferred`](https://github.com/libsdl-org/SDL/blob/release-3.4.18/src/video/wayland/SDL_waylandvideo.c#L523-L546)); otherwise it runs through XWayland, where GNOME draws the title bar. GNOME 46 (Ubuntu 24.04) doesn't offer `fifo-v1`; GNOME 50 (Ubuntu 26.04) does.

| Date | Change | Where | Effect on the title bar |
|---|---|---|---|
| 2026-01-22 | quick-sharun starts disabling libdecor in AppImages that don't bundle it | pkgforge-dev/Anylinux-AppImages [`de193d4`](https://github.com/pkgforge-dev/Anylinux-AppImages/commit/de193d4), [`d259eaf`](https://github.com/pkgforge-dev/Anylinux-AppImages/commit/d259eaf) | None for Oolite yet (not used) |
| 2026-03-19 | **1.92.1.0** released: SDL 1.2 (through SDL2), packaged without quick-sharun, libdecor bundled | release AppImage | Title bar on Ubuntu 24.04 (see runs below) |
| 2026-04-22 | Oolite moves from SDL 1.2 to SDL3 | `627fdf561` (build dependencies follow in `0788cbb7e`, 2026-04-28) | SDL3 uses native Wayland where the compositor offers `fifo-v1`; there, on GNOME, it needs libdecor for a title bar |
| 2026-05-01 | AppImage packaging moves to quick-sharun; libdecor is not installed on the build machine and `DEPLOY_SDL` is not set, so libdecor is not bundled | OoliteProject/oolite#615 (`626c8d98a`) | quick-sharun disables libdecor in the bundle |
| 2026-06-27 | quick-sharun disables unbundled libdecor by renaming `libdecor-0.so` inside bundled libraries to a non-existent name | Anylinux-AppImages [`b3a9e985`](https://github.com/pkgforge-dev/Anylinux-AppImages/commit/b3a9e985) | Same effect, different method |
| 2026-07-12 | **1.93.1-192**, first release since SDL3: SDL3 3.4.12, quick-sharun, libdecor not bundled, renamed reference present in `libSDL3` | release AppImage | Expected: no title bar on GNOME with `fifo-v1` (from its contents; this release was not run) |
| 2026-11-05 | **1.93.1-253** (latest): SDL3 3.4.18, same packaging, same renamed reference | release AppImage | Ubuntu 24.04: title bar (SDL3 uses XWayland). Ubuntu 26.04: **no title bar** |

**Release contents checked** (extracted each AppImage):

| Release | SDL | Packaging | libdecor bundled | libdecor reference in SDL |
|---|---|---|---|---|
| 1.92.1.0 | SDL 1.2 + SDL2 | pre-quick-sharun | yes | original |
| 1.93.1-192 | SDL3 3.4.12 | quick-sharun | no | renamed |
| 1.93.1-253 | SDL3 3.4.18 | quick-sharun | no | renamed |

**Runs on Ubuntu 26.04, GNOME 50.1, full `ubuntu-desktop` install** (3 launches each, window measured by GNOME):

| AppImage / launch | Session | Window frame | Title bar |
|---|---|---|---|
| 1.93.1-253, default | Wayland | 1280×720 | none |
| 1.93.1-253, `SDL_VIDEODRIVER=x11` | X11 (XWayland) | 1280×759 | yes, drawn by GNOME |
| 1.93.1-253, libdecor added and reference restored by hand | Wayland | 1280×757 | yes, drawn by Ubuntu's GTK libdecor plugin |

1.92.1.0 does not start on Ubuntu 26.04 for an unrelated reason (OoliteProject/oolite#769, bundled `libsystemd`).

**Runs on Ubuntu 24.04.5, GNOME 46.0, full `ubuntu-desktop` install, default (Wayland) session** (3 launches each):

| AppImage | Runs as | SDL | libdecor loaded | Window frame | Title bar |
|---|---|---|---|---|---|
| 1.92.1.0 | X11 (XWayland) | SDL 1.2 + SDL2 | yes | 1280×757 | yes, drawn by GNOME |
| 1.93.1-253 | X11 (XWayland) | SDL3 | no | 1280×757 | yes, drawn by GNOME |

**Why SDL3 behaves differently** (`wayland-info` against each headless GNOME):

| | GNOME 46.0 (Ubuntu 24.04) | GNOME 50.1 (Ubuntu 26.04) |
|---|---|---|
| `wp_fifo_manager_v1` offered | no | yes |
| SDL3 chooses | XWayland | native Wayland |

So the bug appears on GNOME versions that offer `fifo-v1`: confirmed on GNOME 50, absent on 46, versions 47–49 not tested.

None of the changes above were made in this fork.
