"""Host environment header and live-desktop detection (stdlib only; no host names or user names)."""
import datetime
import glob
import os
import platform
import re
import shutil
import subprocess


def _run(cmd, timeout=5):
    try: return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout).stdout
    except (OSError, subprocess.SubprocessError): return ""


def distro():
    try:
        d = dict(l.rstrip().split("=", 1) for l in open("/etc/os-release") if "=" in l)
        return d.get("PRETTY_NAME", "unknown").strip('"')
    except OSError: return "unknown"


def gpu():
    lines = [re.sub(r"^\S+ ", "", l) for l in _run(["lspci"]).splitlines() if re.search("vga|3d|display", l, re.I)][:2]
    drv = []
    for d in sorted(glob.glob("/sys/class/drm/card[0-9]")):
        p = os.path.join(d, "device/driver")
        if os.path.exists(p): drv.append("%s (%s)" % (os.path.basename(os.readlink(p)), os.path.basename(d)))
    return "; ".join(lines) or "unknown", ", ".join(drv) or "unknown"


def x_wm_name():
    if not os.environ.get("DISPLAY") or not shutil.which("xprop"): return ""
    m = re.search(r"0x[0-9a-f]+", _run(["xprop", "-root", "_NET_SUPPORTING_WM_CHECK"]))
    return _run(["xprop", "-id", m[0], "_NET_WM_NAME"]).split("=", 1)[-1].strip().strip('"') if m else ""


def header(version="unknown", sdl=""):
    g, drv = gpu()
    rows = [("date", datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%MZ")), ("distro", distro()), ("kernel", platform.release()),
            ("arch", platform.machine()), ("desktop", os.environ.get("XDG_CURRENT_DESKTOP", "unknown")),
            ("session_type", os.environ.get("XDG_SESSION_TYPE", "unknown")),
            ("display", "DISPLAY=%s WAYLAND_DISPLAY=%s" % (os.environ.get("DISPLAY", "unset"), os.environ.get("WAYLAND_DISPLAY", "unset")))]
    if x_wm_name(): rows.append(("x_window_manager", x_wm_name()))
    rows += [("gpu", g), ("gpu_driver", drv)]
    if shutil.which("glxinfo"):
        m = re.search(r"OpenGL renderer string: (.*)", _run(["glxinfo", "-B"])); rows.append(("gl_renderer", m[1] if m else "unknown"))
    rows += [("sdl_video_driver", sdl or "x11 for X11/XWayland rows, wayland for native rows (set per environment)"),
             ("docker", _run(["docker", "--version"]).strip() or "not installed"), ("python3", platform.python_version()), ("uitest_version", version)]
    return "\n".join("%-16s %s" % r for r in rows) + "\n"


def screen_size():
    """Live desktop size without spaces: '2560x1440' or '2heads:1920x1080+2560x1440' or 'unknown' (xrandr, kscreen-doctor, wlr-randr)."""
    m = []
    if os.environ.get("DISPLAY") and shutil.which("xrandr"):
        for l in _run(["xrandr", "--listmonitors"]).splitlines()[1:]:
            g = re.search(r"(\d+)/\d+x(\d+)/\d+\+", l)
            if g: m.append("%sx%s" % g.groups())
    if not m and shutil.which("kscreen-doctor"):
        m = re.findall(r"Geometry:\s+\S+\s+(\d+x\d+)", re.sub(r"\x1b\[[0-9;]*m", "", _run(["kscreen-doctor", "-o"])))
    if not m and shutil.which("wlr-randr"):
        m = re.findall(r"(\d+x\d+) px.*current", _run(["wlr-randr"])) or re.findall(r"^\s+(\d+x\d+) px.*\bcurrent", _run(["wlr-randr"]), re.M)
    return "unknown" if not m else m[0] if len(m) == 1 else "%dheads:%s" % (len(m), "+".join(m))


def detect_host():
    """{desktop, session, wm, version} of the live desktop, for the HOSTENV raw line."""
    st = os.environ.get("XDG_SESSION_TYPE", "unknown"); desk = os.environ.get("XDG_CURRENT_DESKTOP", "unknown")
    wm = ""; ver = ""
    if st == "wayland" and "kde" in desk.lower():
        wm = "kwin_wayland"; ver = (re.search(r"[0-9][0-9.]+", _run(["kwin_wayland", "--version"])) or [""])[0] if shutil.which("kwin_wayland") else ""
    else:
        hay = (x_wm_name() + " " + desk).lower()
        for c in ("mutter", "sway", "marco", "xfwm4", "openbox", "muffin", "kwin_x11"):
            if c.split("_")[0] in hay:
                wm = c
                if shutil.which(c): ver = (re.search(r"[0-9][0-9.]+", _run([c, "--version"])) or [""])[0]
                break
    return {"desktop": desk.replace(" ", "_"), "session": st, "wm": (wm or x_wm_name() or "unknown").replace(" ", "_"), "version": ver or "unknown"}
