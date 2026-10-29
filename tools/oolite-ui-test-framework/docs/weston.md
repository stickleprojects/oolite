# What the UI tests can and cannot test on weston

weston is the reference Wayland compositor. We run it headless in two environments: **weston-xwayland** (the game through XWayland)
and **weston-native** (the game as a native Wayland client). Both come with limits that the other compositors do not have. This page
says what is covered, what is not, why, and what would close each gap.

Every report also lists the gaps it actually hit, under **"What cannot be tested where"**. That table is built from the run's own results,
so a gap that is fixed disappears from it without anyone editing a list.

## Coverage at a glance (2026-10-29)

| Test | weston-xwayland | weston-native |
|---|---|---|
| game launches | ✅ | ✅ |
| window fits the screen | ✅ | ✅ |
| window size as requested | ✅ | ❌ no probe sees the window |
| has a frame | ✅ | ❌ no probe |
| game window centred | ✅ | ❌ no probe |
| splash centred | ✅ | ❌ no probe |
| saved window size restored | ✅ | ❌ no probe |
| **gets keyboard focus** | ❌ **no window ever gets focus** | ❌ no probe |
| title menu displayed (screenshot + OCR) | ✅ | ❌ no screenshots |
| keys move the menu | ✅ *with the pointer on the game first* | ❌ no way to send keys |
| click a menu item | ✅ | ❌ no way to send clicks |
| F12 full screen and back (both variants) | ✅ | ❌ no probe, no keys |

weston-xwayland: pr774, 10 runs with `--toggle`, every measurable test passed (`results/weston-noidle-pr774b.*`).
weston-native: only the launch and the screen-size check run.

## Why: headless weston has no input devices

weston's **headless backend** has no screen and no input hardware, so its seat has **no keyboard and no pointer**. That one fact
explains most of the gaps:

- **No keyboard focus, ever.** In Wayland, focus belongs to the seat's keyboard. weston's window manager for X windows activates a window
  (sets `_NET_ACTIVE_WINDOW` and the X focus) only when keyboard focus moves to it. In a running weston-xwayland, `_NET_ACTIVE_WINDOW`
  stays `0x0` and the X focus is `PointerRoot`. Measuring focus anyway gave focus=0 in every run, while keys still worked. So
  `gets_focus` is NOT MEASURABLE (`focus_na`), deliberately and with that evidence.
- **Keys on weston-xwayland work only because they bypass weston.** We inject them with XTEST inside XWayland. With focus on
  PointerRoot, XWayland sends each key to the window under its pointer. The keys test failed in run 1 of every stock run until the
  pointer was put on the game first (`keys_follow_pointer`). The keyboard is still really tested; the pointer is the workaround.
- **weston-native has no way in at all.** There is no X server to inject into, and headless weston offers no protocol for fake input
  (KWin has fake-input, sway has the virtual-keyboard and virtual-pointer protocols). Hence `keys_na`.
- **weston-native has no probe.** weston has no IPC that reports windows (no KWin script, no sway tree), and without an X server the
  X11 tools see nothing. So frame, position, size, splash and F12 cannot be observed there.
- **No screenshots on weston-native**, for the same reason: no X grab, no compositor screenshot API we can reach headless.

## Found along the way

- **weston goes idle after 300 s.** Injected input goes to XWayland, never to weston, so weston saw no activity, went idle 5 minutes in,
  and from then on every new window opened at (0,0). It looked like "1 run in 5" (the 5th run started after 5 minutes) and was suspected
  to be a PR #774 regression. Fixed with `--idle-time=0` (#47).
- **stock does not centre the window on weston** (+1472+92 on 3840x1080, every run); PR #774 does (+1248+148). That is the expected
  baseline, not a test problem.

## Closing the gaps: the VNC backend spike (#53)

weston's **VNC backend** is headless too, but creates a real seat with a keyboard and pointer, fed by a VNC client. A VNC connection
would give keys, clicks and screenshots (the framebuffer), and real focus. The spike found:

- The backend needs `neatvnc`, an optional dependency not in the image (easy to add).
- `--disable-transport-layer-security` works, but every login method needs a **username and password**, checked through PAM
  (`/etc/pam.d/weston-remote-access` is in the image) against the user weston runs as.
- **Apple Remote Desktop login (type 30) aborts weston** (exit 134) the moment a client picks it: weston 15.0.1 with neatvnc 1.0.3,
  every time. ARD would have needed a ~60-line client.
- **RSA-AES login (types 5 and 129) works**, but then encrypts the whole session with AES-EAX. Python's `cryptography` has no EAX
  mode, so a client is roughly 250 lines of careful protocol code before the first key.

Options, in #53: write the RSA-AES client; find a scriptable client library that speaks it; report the ARD abort upstream and use ARD
once fixed; or build weston's own test plugin (`weston_test` protocol) from source.

Even with VNC, **weston-native would still lack a window probe** (#45): clicks would have to find the game in the screenshot, and frame,
position, size and F12 would stay out of reach.

## Related

- Issues: #47 (idle timeout, fixed), #53 (a real seat for weston), #44 (screenshots on native sessions), #45 (window observation on
  native sessions), #46 (splash on native sessions).
- [LESSONS.md](../LESSONS.md): the weston rows in the environments table.
