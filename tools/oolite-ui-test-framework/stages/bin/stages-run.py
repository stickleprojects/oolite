#!/usr/bin/env python3
"""stages-run.py --game native,x11 --runs N --label LABEL [--out /out]: inside the container, run the stages in order and print one
RESULT line per run.
  stage.sh start (once); then for every game mode and run: launch-linux, observe, collect, tidyup; at the end tidyup --all.
Per run it writes <out>/<mode>-<run>.json (what observe saw), .png (screenshot) and a folder of logs. A run whose game window never
appears is a RESULT with found=0, not a skip."""
import argparse
import json
import os
import subprocess
import sys


def parse_args(argv):
    p = argparse.ArgumentParser(prog="stages-run.py")
    p.add_argument("--game", default="native,x11", help="comma-separated game modes: native, x11")
    p.add_argument("--runs", type=int, default=3)
    p.add_argument("--label", required=True, help="name of the build under test (the build= field)")
    p.add_argument("--out", default="/out")
    a = p.parse_args(argv)
    a.modes = [m for m in a.game.split(",") if m]
    bad = [m for m in a.modes if m not in ("native", "x11")]
    if bad or not a.modes: p.error("--game takes native and/or x11, not '%s'" % a.game)
    if a.runs < 1: p.error("--runs must be at least 1")
    return a


def result_line(obs, env, mode, label, run, window):
    """The RESULT line for one run. obs is observe's JSON (or None if it printed none); window is the "WxH" the game was asked for.
    titlebar is the frame height minus the requested window height: 0 means nothing drew a title bar."""
    head = "RESULT wm=%s-%s-%s distro=%s desktop=%s session=%s game=%s build=%s run=%d" % (
        env["desktop"], env["session"], mode, env["distro"], env["desktop"], env["session"], mode, label, run)
    wins = (obs or {}).get("windows") or []
    if not obs or not obs.get("game") or not wins:
        return head + " client=none frame=0x0 titlebar=0 focus=0 found=0"
    w = wins[0]
    fw, fh = int(w["frame"][2]), int(w["frame"][3])
    want_h = int(window.split("x")[1])
    return head + " client=%s frame=%dx%d titlebar=%d focus=%d found=1" % (w["client"], fw, fh, fh - want_h, 1 if w["focus"] else 0)


def stage(*args, **kw):
    return subprocess.run(["stage.sh"] + list(args), **kw)


def state_value(path, name):
    """A value from the stages' state file (lines: export NAME=value)."""
    try:
        for line in open(path):
            if line.startswith("export %s=" % name):
                return line.split("=", 1)[1].strip().strip("'\"")
    except OSError:
        pass
    return None


def main(argv=None):
    a = parse_args(sys.argv[1:] if argv is None else argv)
    env = {k: os.environ.get("UITEST_" + k.upper(), "") for k in ("distro", "desktop", "session")}
    state = os.environ.get("UITEST_STATE", "/tmp/uitest/state.env")
    os.makedirs(a.out, exist_ok=True)
    if stage("start").returncode != 0:
        print("stages-run.py: stage start failed", file=sys.stderr); return 2
    rc = 0
    try:
        for mode in a.modes:
            for run in range(1, a.runs + 1):
                stem = os.path.join(a.out, "%s-%d" % (mode, run))
                if stage("launch-linux", "--game", mode).returncode != 0:
                    print("stages-run.py: launch-linux failed", file=sys.stderr); rc = 2; stage("tidyup"); continue
                window = state_value(state, "GAME_WINDOW") or "1280x720"
                r = stage("observe", "--screenshot", stem + ".png", stdout=subprocess.PIPE, text=True)
                with open(stem + ".json", "w") as f: f.write(r.stdout)
                try: obs = json.loads(r.stdout.strip().splitlines()[-1])
                except (ValueError, IndexError): obs = None
                print(result_line(obs, env, mode, a.label, run, window), flush=True)
                stage("collect", stem)
                stage("tidyup")
    finally:
        stage("tidyup", "--all")
    return rc


if __name__ == "__main__":
    sys.exit(main())
