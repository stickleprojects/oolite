"""`uitest stages shell|run DISTRO DESKTOP SESSION`: run the stage scripts (stages/) in one container for one build.
  shell  an interactive bash in the container, with `stage.sh` on PATH, to run stages one at a time by hand;
  run    stages-run.py in the container (start, then launch/observe/collect/tidyup per game mode and run), results in
         results/stages-<date>-<label>/ .
The container gets the stages folder (read-only), the AppImage (read-only) and an output folder. Nothing else of the host is
mounted: no X socket, no home. Only results/ is written on the host.

Everything is checked before Docker is started (distro, desktop, session, build, game modes, runs), and each failure says what is
wrong and how to fix it."""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from enum import Enum
from typing import Callable, Optional, Sequence

from . import hostrun

STAGES: str = hostrun.PKG + "/stages"
ELF_MAGIC = b"\x7fELF"
NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]*$")      # a distro, desktop or session folder name
LABEL = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.+-]*$")    # a build label: safe in a file name
REQUIRED_STAGES = ("start", "observe", "launch-linux")

# hostrun is not type-annotated; these are its helpers with the types this module relies on
_docker_state: Callable[[], tuple[bool, str]] = hostrun.docker_state
_safe_name: Callable[[str], str] = hostrun.safe_name
_stamp: Callable[[], str] = hostrun.stamp
_image_hash: Callable[..., str] = hostrun.image_hash


class GameMode(str, Enum):
    """How the game picks its video driver. Same values as stages/bin/stages-run.py (a test compares them)."""
    NATIVE = "native"
    X11 = "x11"


class Session(str, Enum):
    WAYLAND = "wayland"
    X11 = "x11"


class Action(str, Enum):
    SHELL = "shell"
    RUN = "run"


class StagesError(Exception):
    """A problem with the arguments or the host, whose message says what is wrong and how to fix it."""


def enum_names(cls: type[Enum]) -> str:
    return ", ".join(str(m.value) for m in cls)


def enum_arg(cls: type[Enum]) -> Callable[[str], Enum]:
    """argparse `type=` for an enum: the usual 'invalid ... (choose from ...)' error."""
    def convert(text: str) -> Enum:
        try:
            return cls(text)
        except ValueError:
            raise argparse.ArgumentTypeError("invalid %s '%s' (choose from %s)" % (cls.__name__.lower(), text, enum_names(cls))) from None
    convert.__name__ = cls.__name__.lower()
    return convert


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


def folder_name(text: str) -> str:
    if not NAME.match(text) or ".." in text:
        raise argparse.ArgumentTypeError("invalid name '%s' (letters, digits and _ . + - only, no '/')" % text)
    return text


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="uitest stages", description=(__doc__ or "").split("\n")[0])
    p.add_argument("action", type=enum_arg(Action), metavar="{shell,run}")
    p.add_argument("distro", type=folder_name, help="a folder in stages/distros/ that has a Dockerfile, e.g. ubuntu-26.04")
    p.add_argument("desktop", type=folder_name, help="e.g. gnome")
    p.add_argument("session", type=enum_arg(Session), metavar="{wayland,x11}", help="wayland or x11")
    p.add_argument("--build", required=True, help="shell: PATH of the AppImage; run: LABEL:PATH")
    p.add_argument("--game", type=game_modes, default=list(GameMode), metavar="MODES", help="run: game modes, comma-separated (native, x11)")
    p.add_argument("--runs", type=positive_int, default=3, help="run: runs per game mode (at least 1)")
    p.add_argument("--out", help="run: output folder (default results/stages-<date>-<label>)")
    return p


# ---- validation: everything here runs before Docker is started, and raises StagesError with the fix

def distros(root: str = STAGES) -> list[str]:
    """The distros that can be built: a folder in distros/ with a non-empty Dockerfile."""
    base = os.path.join(root, "distros")
    if not os.path.isdir(base): return []
    return sorted(d for d in os.listdir(base) if os.path.isfile(os.path.join(base, d, "Dockerfile")) and os.path.getsize(os.path.join(base, d, "Dockerfile")) > 0)


def check_distro(distro: str, root: str = STAGES) -> None:
    folder = os.path.join(root, "distros", distro)
    have = ", ".join(distros(root)) or "none"
    rel = os.path.relpath(folder, os.path.dirname(root))
    if not os.path.isdir(folder):
        raise StagesError("no distro '%s': there is no folder %s. Use one of: %s, or add a distro (see stages/README.md, Add a distro)" % (distro, rel, have))
    dockerfile = os.path.join(folder, "Dockerfile")
    if not os.path.isfile(dockerfile):
        raise StagesError("%s has no Dockerfile: add one (see stages/README.md, Add a distro) or use one of: %s" % (rel, have))
    if os.path.getsize(dockerfile) == 0:
        raise StagesError("%s/Dockerfile is empty: write it (see stages/README.md, Add a distro) or use one of: %s" % (rel, have))
    with open(dockerfile, errors="replace") as f:
        if not any(l.strip().upper().startswith("FROM ") for l in f):
            raise StagesError("%s/Dockerfile has no FROM line, so it is not a Dockerfile: fix it (see stages/README.md, Add a distro) or use one of: %s" % (rel, have))


def resolve_stage(distro: str, desktop: str, session: str, stage: str, root: str = STAGES) -> Optional[str]:
    """The script that runs `stage` for this cell, or None. Asks the same resolve.sh the container uses."""
    env = {**os.environ, "UITEST_STAGES": root}
    r = subprocess.run([os.path.join(root, "resolve.sh"), distro, desktop, session, stage], capture_output=True, text=True, env=env)
    return r.stdout.strip() if r.returncode == 0 else None


def known_cells(distro: str, root: str = STAGES) -> list[str]:
    """'desktop session' pairs under desktops/ (and combos/<distro>+*/) that have every required stage for this distro."""
    cand: set[tuple[str, str]] = set()
    for sub, prefix in (("desktops", ""), ("combos", distro + "+")):
        base = os.path.join(root, sub)
        if not os.path.isdir(base): continue
        for d in os.listdir(base):
            if not d.startswith(prefix) or not os.path.isdir(os.path.join(base, d)): continue
            for s in os.listdir(os.path.join(base, d)):
                if os.path.isdir(os.path.join(base, d, s)): cand.add((d[len(prefix):], s))
    return sorted("%s %s" % c for c in cand if all(resolve_stage(distro, c[0], c[1], st, root) for st in REQUIRED_STAGES))


def check_cell(distro: str, desktop: str, session: str, root: str = STAGES) -> None:
    missing = [s for s in REQUIRED_STAGES if not resolve_stage(distro, desktop, session, s, root)]
    if missing:
        cells = known_cells(distro, root)
        raise StagesError(
            "no '%s' stage for %s %s %s (looked in combos/%s+%s/%s, desktops/%s/%s, sessions/%s, common). Desktop and session pairs that work for %s: %s. "
            "To add one see stages/README.md, Add a desktop" % ("', '".join(missing), distro, desktop, session, distro, desktop, session, desktop, session,
                                                               session, distro, "; ".join(cells) or "none"))


def appimage_problem(path: str) -> Optional[str]:
    """Why `path` is not an AppImage (exists, regular file, starts with the ELF magic), or None if it is."""
    if not os.path.exists(path): return "does not exist"
    if os.path.isdir(path): return "is a folder, not a file"
    if not os.path.isfile(path): return "is not a regular file"
    try:
        with open(path, "rb") as f:
            head = f.read(4)
    except OSError as e:
        return "cannot be read (%s)" % e.strerror
    if head != ELF_MAGIC:
        return "is not an AppImage: it does not start with the ELF magic 7f454c46, it starts with %s" % (head.hex() or "nothing (empty file)")
    return None


def parse_build(action: Action, build: str) -> tuple[str, str]:
    """(label, path) from --build, checked. shell takes a PATH (label 'shell'); run takes LABEL:PATH."""
    if action is Action.SHELL:
        label, path = "shell", build
        if not os.path.exists(path) and ":" in path:
            raise StagesError("--build for `shell` is a PATH, not LABEL:PATH (got '%s'): use --build %s" % (build, path.partition(":")[2]))
    else:
        label, sep, path = build.partition(":")
        if not sep or not label or not path:
            raise StagesError("--build for `run` is LABEL:PATH, e.g. --build master:appimages/master.AppImage (got '%s')" % build)
        if not LABEL.match(label):
            raise StagesError("build label '%s' must be letters, digits and _ . + - only (it becomes part of file names): e.g. --build master:%s" % (label, path))
    why = appimage_problem(path)
    if why: raise StagesError("--build %s: %s %s. Pass the path of a built Oolite .AppImage" % (build, path, why))
    return label, path


def validate(a: argparse.Namespace) -> tuple[str, str]:
    """All the checks that need no Docker. Returns (label, path)."""
    check_distro(a.distro)
    check_cell(a.distro, a.desktop, a.session.value)
    return parse_build(a.action, a.build)


# ---- docker

def image_tag(distro: str) -> str:
    return "oolite-stages-" + distro


def dockerfile_hash(path: str) -> str:
    """Stamp of an image's sources: the distro's Dockerfile (the whole folder is its build context)."""
    return _image_hash(os.path.relpath(path, hostrun.PKG), root=hostrun.PKG, with_docker_dir=False)


def ensure_image(distro: str, say: Callable[[str], None] = print) -> bool:
    """Build oolite-stages-<distro> unless an image labelled with the current Dockerfile hash exists. True if it is usable."""
    try:
        check_distro(distro)
    except StagesError as e:
        print("uitest stages: " + str(e), file=sys.stderr)
        return False
    folder = os.path.join(STAGES, "distros", distro)
    want = dockerfile_hash(os.path.join(folder, "Dockerfile")); tag = image_tag(distro)
    r = subprocess.run(["docker", "image", "inspect", "-f", '{{index .Config.Labels "uitest.hash"}}', tag], capture_output=True, text=True)
    if r.returncode == 0 and r.stdout.strip() == want: return True
    say("Building Docker image %s (about 5 GB; 10-20 min the first time)" % tag)
    return subprocess.run(["docker", "build", "--label", "uitest.hash=" + want, "-t", tag, folder]).returncode == 0


def docker_cmd(a: argparse.Namespace, app: str, outdir: str, interactive: bool) -> list[str]:
    """The docker run command. app and outdir are absolute host paths."""
    cmd = ["docker", "run", "--rm", "--init"] + (["-it"] if interactive else [])
    cmd += ["-v", "%s:/stages:ro" % STAGES, "-v", "%s:/app/oolite.AppImage:ro" % app, "-v", "%s:/out" % outdir,
            "-e", "UITEST_DISTRO=" + a.distro, "-e", "UITEST_DESKTOP=" + a.desktop, "-e", "UITEST_SESSION=" + a.session.value,
            image_tag(a.distro)]
    return cmd


def main(argv: Sequence[str]) -> int:
    a = parser().parse_args(argv)
    try:
        label, path = validate(a)
        ok, why = _docker_state()
        if not ok:
            raise StagesError("Docker is not usable: %s. uitest stages needs Docker: install it (https://docs.docker.com/engine/install/), start it (`sudo systemctl start docker`) "
                              "and make sure your user is in the docker group" % why)
    except StagesError as e:
        print("uitest stages: " + str(e), file=sys.stderr)
        return 2
    if not ensure_image(a.distro):
        print("uitest stages: image build failed (the Docker output is above): fix the Dockerfile in stages/distros/%s/ and run this again" % a.distro, file=sys.stderr)
        return 2
    app = os.path.realpath(path)
    if a.action is Action.SHELL:
        outdir = os.path.join(hostrun.PKG, "results", "stages-shell")
        os.makedirs(outdir, exist_ok=True)
        # /out is writable by `player` only if the host filesystem honours permissions; otherwise `sudo cp` into it
        return subprocess.run(docker_cmd(a, app, os.path.abspath(outdir), True) + ["bash", "-c", "sudo chmod 777 /out 2>/dev/null; exec bash -l"]).returncode
    return run(a, label, app)


def run(a: argparse.Namespace, label: str, app: str) -> int:
    safe = _safe_name(label)
    outdir = os.path.abspath(a.out or os.path.join(hostrun.PKG, "results", "stages-%s-%s" % (_stamp(), safe)))
    try:
        os.makedirs(outdir, exist_ok=True)
    except OSError as e:
        print("uitest stages: cannot create the output folder %s (%s): give a writable one with --out" % (outdir, e.strerror), file=sys.stderr)
        return 2
    raw = os.path.join(outdir, "stages-%s.raw" % safe)
    modes = ",".join(m.value for m in a.game)
    # The stages run as `player` and write to /tmp/res. /out is the host's folder: on a filesystem that ignores permissions (NTFS)
    # `player` cannot write there, so root copies the results over at the end and hands them to the host user (as give_back_output does).
    script = ('mkdir -p /tmp/res; stages-run.py "$@" --out /tmp/res; rc=$?; sudo cp -r --no-preserve=all /tmp/res/. /out/; '
              'sudo chown -R %d:%d /out 2>/dev/null; exit $rc' % (os.getuid(), os.getgid()))
    cmd = docker_cmd(a, app, outdir, False) + ["bash", "-c", script, "stages", "--game", modes, "--runs", str(a.runs), "--label", safe]
    lines: list[str] = []
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, text=True)
    assert p.stdout is not None
    with open(raw, "w") as rf:
        for line in p.stdout:
            sys.stdout.write(line); sys.stdout.flush()
            if line.startswith("RESULT "): lines.append(line.strip()); rf.write(line)
    rc = p.wait()
    print(summary(lines, [m.value for m in a.game], a.runs))
    print("Results: %s" % outdir)
    return 0 if rc == 0 and len(lines) == a.runs * len(a.game) else 1


def parse_result(line: str) -> dict[str, str]:
    return dict(f.split("=", 1) for f in line.split()[1:] if "=" in f)


def summary(lines: Sequence[str], modes: Sequence[str], runs: int) -> str:
    """One line per game mode: runs seen, window found, client, title-bar heights."""
    out = ["Summary (%d RESULT lines, %d expected):" % (len(lines), len(modes) * runs)]
    recs = [parse_result(l) for l in lines]
    for m in modes:
        rs = [r for r in recs if r.get("game") == m]
        out.append("  %-6s runs=%d found=%d client=%s titlebar=%s" % (
            m, len(rs), sum(r.get("found") == "1" for r in rs), "/".join(sorted({r.get("client", "?") for r in rs})) or "-",
            ",".join(r.get("titlebar", "?") for r in rs) or "-"))
    return "\n".join(out)
