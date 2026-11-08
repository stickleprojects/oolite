"""`uitest stages shell|run DISTRO DESKTOP SESSION`: run the stage scripts (stages/) in one container for one build.
  shell  an interactive bash in the container, with `stage` on PATH, to run stages one at a time by hand;
  run    stages-run in the container (start, then launch/observe/collect/tidyup per game mode and run), results in
         results/stages-<date>-<label>/ .
The container gets the stages folder (read-only), the AppImage (read-only) and an output folder. Nothing else of the host is
mounted: no X socket, no home. Only results/ is written on the host."""
import argparse
import os
import subprocess
import sys

from . import hostrun

STAGES = os.path.join(hostrun.PKG, "stages")


def parser():
    p = argparse.ArgumentParser(prog="uitest stages", description=__doc__.split("\n")[0])
    p.add_argument("action", choices=["shell", "run"])
    p.add_argument("distro", help="a folder in stages/distros/, e.g. ubuntu-26.04")
    p.add_argument("desktop", help="e.g. gnome")
    p.add_argument("session", help="wayland or x11")
    p.add_argument("--build", required=True, help="shell: PATH of the AppImage; run: LABEL:PATH")
    p.add_argument("--game", default="native,x11", help="run: game modes, comma-separated (native, x11)")
    p.add_argument("--runs", type=int, default=3, help="run: runs per game mode")
    p.add_argument("--out", help="run: output folder (default results/stages-<date>-<label>)")
    return p


def image_tag(distro):
    return "oolite-stages-" + distro


def dockerfile_hash(path):
    """Stamp of an image's sources: the distro's Dockerfile (the whole folder is its build context)."""
    return hostrun.image_hash(os.path.relpath(path, hostrun.PKG), root=hostrun.PKG, with_docker_dir=False)


def ensure_image(distro, say=print):
    """Build oolite-stages-<distro> unless an image labelled with the current Dockerfile hash exists. True if it is usable."""
    folder = os.path.join(STAGES, "distros", distro)
    dockerfile = os.path.join(folder, "Dockerfile")
    if not os.path.isfile(dockerfile):
        known = sorted(os.listdir(os.path.join(STAGES, "distros")))
        print("uitest stages: no Dockerfile for distro '%s' (have: %s)" % (distro, ", ".join(known)), file=sys.stderr); return False
    want = dockerfile_hash(dockerfile); tag = image_tag(distro)
    r = subprocess.run(["docker", "image", "inspect", "-f", '{{index .Config.Labels "uitest.hash"}}', tag], capture_output=True, text=True)
    if r.returncode == 0 and r.stdout.strip() == want: return True
    say("Building Docker image %s (about 5 GB; 10-20 min the first time)" % tag)
    return subprocess.run(["docker", "build", "--label", "uitest.hash=" + want, "-t", tag, folder]).returncode == 0


def docker_cmd(a, app, outdir, interactive):
    """The docker run command. app and outdir are absolute host paths."""
    cmd = ["docker", "run", "--rm", "--init"] + (["-it"] if interactive else [])
    cmd += ["-v", "%s:/stages:ro" % STAGES, "-v", "%s:/app/oolite.AppImage:ro" % app, "-v", "%s:/out" % outdir,
            "-e", "UITEST_DISTRO=" + a.distro, "-e", "UITEST_DESKTOP=" + a.desktop, "-e", "UITEST_SESSION=" + a.session,
            image_tag(a.distro)]
    return cmd


def resolves(a):
    """The stage scripts the run needs exist for this distro/desktop/session (the resolver finds start and observe)."""
    for s in ("start", "observe", "launch-linux"):
        r = subprocess.run([os.path.join(STAGES, "resolve.sh"), a.distro, a.desktop, a.session, s], capture_output=True)
        if r.returncode != 0:
            print("uitest stages: no '%s' stage for %s %s %s" % (s, a.distro, a.desktop, a.session), file=sys.stderr); return False
    return True


def main(argv):
    a = parser().parse_args(argv)
    if a.runs < 1: print("uitest stages: --runs must be at least 1", file=sys.stderr); return 2
    if a.action == "shell":
        label, path = "shell", a.build
    else:
        label, _, path = a.build.partition(":")
        if not label or not path: print("uitest stages: run needs --build LABEL:PATH", file=sys.stderr); return 2
    if not os.path.isfile(path): print("uitest stages: AppImage not found: %s" % path, file=sys.stderr); return 2
    if not resolves(a): return 2
    ok, why = hostrun.docker_state()
    if not ok: print("uitest stages: " + why, file=sys.stderr); return 2
    if not ensure_image(a.distro): print("uitest stages: image build failed", file=sys.stderr); return 2
    app = os.path.realpath(path)
    if a.action == "shell":
        outdir = os.path.join(hostrun.PKG, "results", "stages-shell")
        os.makedirs(outdir, exist_ok=True)
        # /out is writable by `player` only if the host filesystem honours permissions; otherwise `sudo cp` into it
        return subprocess.run(docker_cmd(a, app, os.path.abspath(outdir), True) + ["bash", "-c", "sudo chmod 777 /out 2>/dev/null; exec bash -l"]).returncode
    return run(a, label, app)


def run(a, label, app):
    safe = hostrun.safe_name(label)
    outdir = os.path.abspath(a.out or os.path.join(hostrun.PKG, "results", "stages-%s-%s" % (hostrun.stamp(), safe)))
    os.makedirs(outdir, exist_ok=True)
    raw = os.path.join(outdir, "stages-%s.raw" % safe)
    # The stages run as `player` and write to /tmp/res. /out is the host's folder: on a filesystem that ignores permissions (NTFS)
    # `player` cannot write there, so root copies the results over at the end and hands them to the host user (as give_back_output does).
    script = ('mkdir -p /tmp/res; stages-run "$@" --out /tmp/res; rc=$?; sudo cp -r --no-preserve=all /tmp/res/. /out/; '
              'sudo chown -R %d:%d /out 2>/dev/null; exit $rc' % (os.getuid(), os.getgid()))
    cmd = docker_cmd(a, app, outdir, False) + ["bash", "-c", script, "stages", "--game", a.game, "--runs", str(a.runs), "--label", safe]
    lines = []
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, text=True)
    with open(raw, "w") as rf:
        for line in p.stdout:
            sys.stdout.write(line); sys.stdout.flush()
            if line.startswith("RESULT "): lines.append(line.strip()); rf.write(line)
    rc = p.wait()
    print(summary(lines, a.game.split(","), a.runs))
    print("Results: %s" % outdir)
    return 0 if rc == 0 and len(lines) == a.runs * len(a.game.split(",")) else 1


def parse_result(line):
    return dict(f.split("=", 1) for f in line.split()[1:] if "=" in f)


def summary(lines, modes, runs):
    """One line per game mode: runs seen, window found, client, title-bar heights."""
    out = ["Summary (%d RESULT lines, %d expected):" % (len(lines), len(modes) * runs)]
    recs = [parse_result(l) for l in lines]
    for m in modes:
        rs = [r for r in recs if r.get("game") == m]
        out.append("  %-6s runs=%d found=%d client=%s titlebar=%s" % (
            m, len(rs), sum(r.get("found") == "1" for r in rs), "/".join(sorted({r.get("client", "?") for r in rs})) or "-",
            ",".join(r.get("titlebar", "?") for r in rs) or "-"))
    return "\n".join(out)
