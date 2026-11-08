#!/usr/bin/env python3
"""stages-run.py --game native,x11 --runs N --label LABEL [--out /out]: inside the container, run the stages in order and print one
RESULT line per run.
  stage.sh start (once); then for every game mode and run: launch-linux, observe, collect, tidyup; at the end tidyup --all.
Per run it writes <out>/<mode>-<run>.json (what observe saw), .png (screenshot) and a folder of logs. A run whose game window never
appears is a RESULT with found=0 and a why= field, not a skip. Standard library only: it runs in the container's python3."""
from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional, Sequence


class GameMode(str, Enum):
    """How the game picks its video driver. Same values as stages.py on the host (a test compares them)."""
    NATIVE = "native"
    X11 = "x11"


class Session(str, Enum):
    WAYLAND = "wayland"
    X11 = "x11"


class Client(str, Enum):
    """What the game really ran as, as the desktop reports it. NONE: no game window."""
    WAYLAND = "wayland"
    X11 = "x11"
    NONE = "none"


DEFAULT_WINDOW = "1280x720"
TOKEN = re.compile(r"^[A-Za-z0-9_.+-]+$")        # a distro, desktop or build label: safe in a file name and a RESULT field
SIZE = re.compile(r"^([0-9]+)x([0-9]+)$")


class ResultError(ValueError):
    """A RESULT line that is not well formed."""


@dataclass(frozen=True)
class Result:
    """One RESULT line. format() writes it, parse() reads it back and rejects anything malformed.
    wm is not a field: it is always <desktop>-<session>-<game>, so it cannot disagree with them. titlebar is the frame height minus the
    window height asked for: 0 means nothing drew a title bar. why says what went wrong when found is False."""
    distro: str
    desktop: str
    session: Session
    game: GameMode
    build: str
    run: int
    client: Client
    frame: tuple[int, int]
    titlebar: int
    focus: bool
    found: bool
    why: Optional[str] = None

    def __post_init__(self) -> None:
        for name in ("distro", "desktop", "build"):
            if not TOKEN.match(getattr(self, name)):
                raise ResultError("%s '%s' must be letters, digits and _ . + - only" % (name, getattr(self, name)))
        if self.run < 1:
            raise ResultError("run must be at least 1, not %d" % self.run)
        if self.why is not None and not TOKEN.match(self.why):
            raise ResultError("why '%s' must have no spaces" % self.why)

    @property
    def wm(self) -> str:
        return "%s-%s-%s" % (self.desktop, self.session.value, self.game.value)

    def format(self) -> str:
        line = ("RESULT wm=%s distro=%s desktop=%s session=%s game=%s build=%s run=%d client=%s frame=%dx%d titlebar=%d focus=%d found=%d"
                % (self.wm, self.distro, self.desktop, self.session.value, self.game.value, self.build, self.run, self.client.value,
                   self.frame[0], self.frame[1], self.titlebar, int(self.focus), int(self.found)))
        return line + (" why=" + self.why if self.why else "")

    @classmethod
    def parse(cls, line: str) -> "Result":
        words = line.split()
        if not words or words[0] != "RESULT":
            raise ResultError("not a RESULT line: '%s'" % line.strip())
        kv: dict[str, str] = {}
        for w in words[1:]:
            k, sep, v = w.partition("=")
            if not sep or not k or not v:
                raise ResultError("field '%s' is not name=value" % w)
            if k in kv:
                raise ResultError("field '%s' is given twice" % k)
            kv[k] = v
        want = ["wm", "distro", "desktop", "session", "game", "build", "run", "client", "frame", "titlebar", "focus", "found"]
        missing = [k for k in want if k not in kv]
        extra = [k for k in kv if k not in want + ["why"]]
        if missing: raise ResultError("missing field(s): %s" % ", ".join(missing))
        if extra: raise ResultError("unknown field(s): %s" % ", ".join(extra))
        m = SIZE.match(kv["frame"])
        if not m: raise ResultError("frame '%s' is not WxH" % kv["frame"])
        for k in ("focus", "found"):
            if kv[k] not in ("0", "1"): raise ResultError("%s must be 0 or 1, not '%s'" % (k, kv[k]))
        try:
            res = cls(distro=kv["distro"], desktop=kv["desktop"], session=Session(kv["session"]), game=GameMode(kv["game"]),
                      build=kv["build"], run=int(kv["run"]), client=Client(kv["client"]), frame=(int(m[1]), int(m[2])),
                      titlebar=int(kv["titlebar"]), focus=kv["focus"] == "1", found=kv["found"] == "1", why=kv.get("why"))
        except ValueError as e:                    # a bad enum value or integer; ResultError is a ValueError too
            raise ResultError(str(e)) from e
        if res.wm != kv["wm"]:
            raise ResultError("wm '%s' does not match desktop, session and game (%s)" % (kv["wm"], res.wm))
        return res

    @classmethod
    def from_observation(cls, text: str, *, returncode: int, distro: str, desktop: str, session: Session, game: GameMode,
                         build: str, run: int, window: str = DEFAULT_WINDOW) -> "Result":
        """The result of one run from what `stage.sh observe` printed (last line = JSON) and its exit code. Nothing raises:
        output that is missing, empty, not JSON or lacks keys gives found=0 and a why=, so the run still counts."""
        def none(why: str) -> "Result":
            return cls(distro, desktop, session, game, build, run, Client.NONE, (0, 0), 0, False, False, why)
        lines = [l for l in text.strip().splitlines() if l.strip()]
        if not lines:
            return none("observe_printed_nothing_exit_%d" % returncode)
        try:
            obs: Any = json.loads(lines[-1])
        except ValueError:
            return none("observe_output_not_json")
        if not isinstance(obs, dict):
            return none("observe_json_not_an_object")
        for key in ("game", "windows"):
            if key not in obs: return none("observe_json_missing_%s" % key)
        wins = obs["windows"]
        if not obs["game"] or not isinstance(wins, list) or not wins:
            return none("no_game_window")
        w = wins[0]
        if not isinstance(w, dict): return none("observe_window_not_an_object")
        for key in ("client", "frame", "focus"):
            if key not in w: return none("observe_window_missing_%s" % key)
        try:
            client = Client(w["client"])
            fw, fh = int(w["frame"][2]), int(w["frame"][3])
        except (ValueError, TypeError, IndexError, KeyError):
            return none("observe_window_bad_client_or_frame")
        m = SIZE.match(window) or SIZE.match(DEFAULT_WINDOW)
        assert m is not None
        return cls(distro, desktop, session, game, build, run, client, (fw, fh), fh - int(m[2]), bool(w["focus"]), True)


def enum_names(cls: type[Enum]) -> str:
    return ", ".join(str(m.value) for m in cls)


def game_modes(text: str) -> list[GameMode]:
    """argparse type for --game: a comma list of GameMode values, each at most once."""
    out: list[GameMode] = []
    for part in text.split(","):
        try:
            m = GameMode(part)
        except ValueError:
            raise argparse.ArgumentTypeError("invalid game mode '%s' (choose from %s, comma-separated)" % (part, enum_names(GameMode))) from None
        if m in out: raise argparse.ArgumentTypeError("game mode '%s' is listed twice" % part)
        out.append(m)
    return out


def positive_int(text: str) -> int:
    try:
        n = int(text)
    except ValueError:
        raise argparse.ArgumentTypeError("invalid number '%s'" % text) from None
    if n < 1: raise argparse.ArgumentTypeError("must be at least 1, not %d" % n)
    return n


def label(text: str) -> str:
    if not TOKEN.match(text):
        raise argparse.ArgumentTypeError("invalid label '%s' (letters, digits and _ . + - only)" % text)
    return text


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="stages-run.py")
    p.add_argument("--game", type=game_modes, default=list(GameMode), metavar="MODES", help="comma-separated game modes: %s (default: both)" % enum_names(GameMode))
    p.add_argument("--runs", type=positive_int, default=3)
    p.add_argument("--label", type=label, required=True, help="name of the build under test (the build= field)")
    p.add_argument("--out", default="/out")
    return p.parse_args(argv)


def stage(*args: str, **kw: Any) -> "subprocess.CompletedProcess[Any]":
    return subprocess.run(["stage.sh", *args], **kw)


def state_value(path: str, name: str) -> Optional[str]:
    """A value from the stages' state file (lines: export NAME=value, value quoted by bash's printf %q). None if absent or unreadable."""
    try:
        with open(path) as f:
            for line in f:
                if line.startswith("export %s=" % name):
                    parts = shlex.split(line.split("=", 1)[1])
                    return parts[0] if parts else ""
    except (OSError, ValueError):
        pass
    return None


def environment() -> tuple[str, str, Session]:
    """(distro, desktop, session) from the container's UITEST_* variables; exit 2 with the fix if they are wrong."""
    got = {k: os.environ.get("UITEST_" + k.upper(), "") for k in ("distro", "desktop", "session")}
    unset = [("UITEST_" + k.upper()) for k, v in got.items() if not v]
    if unset:
        sys.exit("stages-run.py: %s not set. It runs inside the container started by `uitest stages run DISTRO DESKTOP SESSION --build LABEL:PATH`, which sets them" % ", ".join(unset))
    try:
        session = Session(got["session"])
    except ValueError:
        sys.exit("stages-run.py: UITEST_SESSION is '%s'; it must be one of: %s" % (got["session"], enum_names(Session)))
    for k in ("distro", "desktop"):
        if not TOKEN.match(got[k]): sys.exit("stages-run.py: UITEST_%s is '%s'; letters, digits and _ . + - only" % (k.upper(), got[k]))
    return got["distro"], got["desktop"], session


def main(argv: Optional[Sequence[str]] = None) -> int:
    a = parse_args(sys.argv[1:] if argv is None else argv)
    distro, desktop, session = environment()
    if shutil.which("stage.sh") is None:
        print("stages-run.py: stage.sh is not on PATH: run it in the container (PATH includes /stages/bin), or add the stages/bin folder to PATH", file=sys.stderr)
        return 2
    state = os.environ.get("UITEST_STATE", "/tmp/uitest/state.env")
    try:
        os.makedirs(a.out, exist_ok=True)
    except OSError as e:
        print("stages-run.py: cannot create the output folder %s (%s): give a writable one with --out" % (a.out, e.strerror), file=sys.stderr)
        return 2
    if stage("start").returncode != 0:
        print("stages-run.py: stage `start` failed (its message is above; its log is in /tmp/uitest/logs). Fix that, run `stage.sh tidyup --all`, then run this again", file=sys.stderr)
        stage("tidyup", "--all")
        return 2
    rc = 0
    try:
        for mode in a.game:
            for run in range(1, a.runs + 1):
                stem = os.path.join(a.out, "%s-%d" % (mode.value, run))
                if stage("launch-linux", "--game", mode.value).returncode != 0:
                    print("stages-run.py: `launch-linux --game %s` failed (its message is above); no RESULT for %s run %d" % (mode.value, mode.value, run), file=sys.stderr)
                    rc = 2
                    stage("tidyup")
                    continue
                window = state_value(state, "GAME_WINDOW") or DEFAULT_WINDOW
                r = stage("observe", "--screenshot", stem + ".png", stdout=subprocess.PIPE, text=True)
                with open(stem + ".json", "w") as f: f.write(r.stdout)
                print(Result.from_observation(r.stdout, returncode=r.returncode, distro=distro, desktop=desktop, session=session, game=mode,
                                              build=a.label, run=run, window=window).format(), flush=True)
                stage("collect", stem)
                stage("tidyup")
    finally:
        stage("tidyup", "--all")
    return rc


if __name__ == "__main__":
    sys.exit(main())
