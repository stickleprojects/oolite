"""Environment registry: environments.toml -> Environment objects. One table per window manager / compositor."""
import os
import tomllib
from dataclasses import dataclass, field

DEFAULT_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "environments.toml")
SESSIONS = ("X11", "XWayland", "Wayland native", "live desktop")
KINDS = ("x11", "wayland", "host")
PROBES = ("x11", "kwin", "sway", "ask", "none")


class RegistryError(ValueError):
    pass


@dataclass
class Environment:
    name: str
    family: str
    session: str
    image: str
    kind: str
    start: list = field(default_factory=list)
    probes: list = field(default_factory=lambda: ["x11"])
    version_cmd: str = ""
    version_re: str = r"[0-9][0-9.]+"
    settle: float = 4.0            # trial.sh: sleep 4 after starting the WM
    settle_after: float = 3.0      # trial.sh: sleep 3 after the WM check succeeds
    ready_timeout: int = 20        # trial.sh: up to 20 polls, 1 s apart
    ready_socket: str = "wl0"
    files: dict = field(default_factory=dict)
    env: dict = field(default_factory=dict)
    post_start: list = field(default_factory=list)
    focus_na: bool = False
    keys: str = "xtest"            # how keys and the mouse are injected: xtest (xdotool) | fakeinput (KWin fake-input, for headless kwin)
    keys_na: bool = False          # injected (XTEST) keys never reach X clients, e.g. headless kwin-xwayland
    headed: bool = False           # the compositor runs as a window on the host X display (GPU passed in); $UITEST_HOST_DISPLAY names it
    where: str = "docker"

    @property
    def probe_specs(self):
        """[(probe name, fields or None)] from "name[:field,field]"."""
        out = []
        for p in self.probes:
            n, _, f = p.partition(":")
            out.append((n, tuple(f.split(",")) if f else None))
        return out

    @property
    def mouse_na(self):
        """No way to inject mouse events: the mouse goes the same way as the keys (XTEST, or KWin fake-input)."""
        return self.keys_na


def parse(data):
    """dict from tomllib -> ({name: Environment}, {image name: {dockerfile, tag}}). Validates every entry."""
    images = data.get("images", {})
    envs = {}
    for name, e in data.get("env", {}).items():
        for req in ("family", "session", "image", "kind"):
            if req not in e: raise RegistryError("env.%s: missing '%s'" % (name, req))
        if e["session"] not in SESSIONS: raise RegistryError("env.%s: session must be one of %s" % (name, ", ".join(SESSIONS)))
        if e["kind"] not in KINDS: raise RegistryError("env.%s: kind must be one of %s" % (name, ", ".join(KINDS)))
        if e["image"] not in images: raise RegistryError("env.%s: unknown image '%s'" % (name, e["image"]))
        if e["kind"] != "host" and not e.get("start"): raise RegistryError("env.%s: needs a start command" % name)
        known = {f for f in Environment.__dataclass_fields__}
        extra = set(e) - known
        if extra: raise RegistryError("env.%s: unknown key(s) %s" % (name, ", ".join(sorted(extra))))
        env = Environment(name=name, **e)
        for n, _ in env.probe_specs:
            if n not in PROBES: raise RegistryError("env.%s: unknown probe '%s'" % (name, n))
        envs[name] = env
    return envs, images


def load(path=None):
    with open(path or DEFAULT_PATH, "rb") as f:
        return parse(tomllib.load(f))


def display_info(envs):
    """{name: {family, session, where}} for the report (report.py)."""
    return {n: {"family": e.family, "session": e.session, "where": e.where} for n, e in envs.items()}
