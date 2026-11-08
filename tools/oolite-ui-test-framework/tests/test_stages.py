"""stages/: the resolver (which script runs a stage), stages-run's argument parsing and RESULT line, and uitest stages' docker command.
No Docker, no game."""
import importlib.machinery
import importlib.util
import os
import subprocess

import pytest

from oolite_ui_test_framework import hostrun, stages

STAGES = os.path.join(hostrun.PKG, "stages")


def resolve(root, *args):
    r = subprocess.run([os.path.join(STAGES, "resolve.sh")] + list(args), capture_output=True, text=True, env={**os.environ, "UITEST_STAGES": str(root)})
    return r.returncode, r.stdout.strip()


def touch(root, rel):
    p = root / rel; p.parent.mkdir(parents=True, exist_ok=True); p.write_text("#!/bin/bash\n"); return str(p)


def test_combo_beats_desktop_beats_session_beats_common(tmp_path):
    common = touch(tmp_path, "common/start.sh")
    assert resolve(tmp_path, "d", "de", "wl", "start") == (0, common)
    session = touch(tmp_path, "sessions/wl/start.sh")
    assert resolve(tmp_path, "d", "de", "wl", "start") == (0, session)
    desktop = touch(tmp_path, "desktops/de/wl/start.sh")
    assert resolve(tmp_path, "d", "de", "wl", "start") == (0, desktop)
    combo = touch(tmp_path, "combos/d+de/wl/start.sh")
    assert resolve(tmp_path, "d", "de", "wl", "start") == (0, combo)


def test_other_distro_desktop_session_do_not_match_the_combo(tmp_path):
    desktop = touch(tmp_path, "desktops/de/wl/start.sh")
    touch(tmp_path, "combos/d+de/wl/start.sh")
    assert resolve(tmp_path, "other", "de", "wl", "start") == (0, desktop)
    assert resolve(tmp_path, "d", "de", "x11", "start")[0] == 1


def test_missing_stage_exits_1_and_prints_nothing(tmp_path):
    assert resolve(tmp_path, "d", "de", "wl", "start") == (1, "")


def test_wrong_argument_count_exits_2(tmp_path):
    assert resolve(tmp_path, "d", "de")[0] == 2


@pytest.mark.parametrize("stage, where", [
    ("start", "combos/ubuntu-26.04+gnome/wayland/start.sh"),
    ("observe", "desktops/gnome/wayland/observe.sh"),
    ("launch-linux", "common/launch-linux.sh"),
    ("collect", "common/collect.sh"),
    ("tidyup", "common/tidyup.sh"),
])
def test_shipped_tree_resolves_ubuntu_gnome_wayland(stage, where):
    rc, path = resolve(STAGES, "ubuntu-26.04", "gnome", "wayland", stage)
    assert rc == 0 and path == os.path.join(STAGES, where) and os.path.isfile(path)


def test_shipped_scripts_are_valid_bash():
    for d, _, fs in os.walk(STAGES):
        for f in fs:
            if f.endswith(".sh") or d.endswith("/bin") and f == "stage":
                assert subprocess.run(["bash", "-n", os.path.join(d, f)], capture_output=True).returncode == 0, f


# stages-run (a Python script without .py)
def load_stages_run():
    path = os.path.join(STAGES, "bin", "stages-run")
    loader = importlib.machinery.SourceFileLoader("stages_run", path)
    spec = importlib.util.spec_from_loader("stages_run", loader)
    m = importlib.util.module_from_spec(spec); loader.exec_module(m); return m


sr = load_stages_run()
ENV = {"distro": "ubuntu-26.04", "desktop": "gnome", "session": "wayland"}


def obs(client="wayland", frame=(0, 0, 1280, 757), focus=True, game=True):
    return {"screen": [1920, 1080], "windows": [{"title": "Oolite", "client": client, "frame": list(frame), "focus": focus}], "game": game}


def test_result_line_fields():
    line = sr.result_line(obs(), ENV, "native", "pr81", 2, "1280x720")
    assert line == ("RESULT wm=gnome-wayland-native distro=ubuntu-26.04 desktop=gnome session=wayland game=native build=pr81 run=2 "
                    "client=wayland frame=1280x757 titlebar=37 focus=1 found=1")


def test_result_line_no_title_bar_and_no_focus():
    line = sr.result_line(obs(frame=(0, 0, 1280, 720), focus=False, client="x11"), ENV, "x11", "b", 1, "1280x720")
    assert "client=x11 frame=1280x720 titlebar=0 focus=0 found=1" in line


def test_result_line_missing_window_is_found_0():
    for o in (None, {"windows": [], "game": False}, obs(game=False)):
        assert sr.result_line(o, ENV, "native", "b", 1, "1280x720").endswith("found=0")


def test_result_line_parses_back():
    rec = stages.parse_result(sr.result_line(obs(), ENV, "x11", "b", 3, "1280x720"))
    assert rec["game"] == "x11" and rec["run"] == "3" and rec["titlebar"] == "37" and rec["wm"] == "gnome-wayland-x11"


def test_stages_run_args():
    a = sr.parse_args(["--game", "native,x11", "--runs", "2", "--label", "L"])
    assert (a.modes, a.runs, a.label, a.out) == (["native", "x11"], 2, "L", "/out")
    assert sr.parse_args(["--label", "L"]).modes == ["native", "x11"]
    for bad in (["--label", "L", "--game", "wayland"], ["--label", "L", "--runs", "0"], ["--game", "native"]):
        with pytest.raises(SystemExit): sr.parse_args(bad)


def test_state_value(tmp_path):
    f = tmp_path / "s.env"; f.write_text("export A=1\nexport GAME_WINDOW=1280x720\n")
    assert sr.state_value(str(f), "GAME_WINDOW") == "1280x720" and sr.state_value(str(f), "NOPE") is None


# uitest stages
def test_docker_cmd_mounts_only_stages_app_and_out():
    a = stages.parser().parse_args(["run", "ubuntu-26.04", "gnome", "wayland", "--build", "x:y"])
    cmd = stages.docker_cmd(a, "/b/oolite.AppImage", "/r/out", False)
    mounts = [cmd[i + 1] for i, c in enumerate(cmd) if c == "-v"]
    assert mounts == [STAGES + ":/stages:ro", "/b/oolite.AppImage:/app/oolite.AppImage:ro", "/r/out:/out"]
    assert "-it" not in cmd and cmd[-1] == "oolite-stages-ubuntu-26.04"
    assert "UITEST_SESSION=wayland" in cmd and not any(".X11-unix" in c for c in cmd)
    assert "-it" in stages.docker_cmd(a, "/b", "/o", True)


def test_summary_counts():
    lines = [sr.result_line(obs(), ENV, "native", "b", i, "1280x720") for i in (1, 2)]
    s = stages.summary(lines, ["native", "x11"], 2)
    assert "2 RESULT lines, 4 expected" in s and "native runs=2 found=2 client=wayland titlebar=37,37" in s and "x11    runs=0" in s


def test_main_dispatches_stages(monkeypatch):
    monkeypatch.setattr(stages, "main", lambda argv: 7)
    assert hostrun.main(["stages", "x"]) == 7


def test_unknown_distro_has_no_image(capsys):
    assert stages.ensure_image("no-such-distro") is False
    assert "no Dockerfile" in capsys.readouterr().err
