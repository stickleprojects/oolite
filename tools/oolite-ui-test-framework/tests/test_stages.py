"""stages/: the resolver, the stage scripts' error handling, stages-run.py (arguments, RESULT line, observe output) and uitest stages'
validation and docker command. No Docker, no game: the bash stages run for real, against a temp state file."""
import dataclasses
import importlib.machinery
import importlib.util
import json
import os
import shutil
import subprocess
import sys

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
            if f.endswith(".sh"):
                assert subprocess.run(["bash", "-n", os.path.join(d, f)], capture_output=True).returncode == 0, f


def test_resolve_rejects_bad_names(tmp_path):
    for bad in ("../x", "a/b", "", "x..y"):
        for pos in range(4):
            args = ["d", "de", "wl", "start"]; args[pos] = bad
            assert resolve(tmp_path, *args)[0] == 2, (pos, bad)


def test_resolve_missing_root_exits_2(tmp_path):
    assert resolve(tmp_path / "nope", "d", "de", "wl", "start")[0] == 2


# ---- the bash stages, run for real against a temp state file
BASH_ENV_KEYS = ("UITEST_STATE", "UITEST_LOGS", "UITEST_OUT", "UITEST_STAGES", "UITEST_LENIENT")


@pytest.fixture
def box(tmp_path):
    """Env for running stages with their state and logs inside tmp_path."""
    env = {k: v for k, v in os.environ.items() if k not in BASH_ENV_KEYS}
    env.update(UITEST_STAGES=STAGES, UITEST_STATE=str(tmp_path / "state.env"), UITEST_LOGS=str(tmp_path / "logs"), UITEST_OUT=str(tmp_path / "out"),
               UITEST_DISTRO="ubuntu-26.04", UITEST_DESKTOP="gnome", UITEST_SESSION="wayland")
    for k in ("WAYLAND_DISPLAY", "DISPLAY"): env.pop(k, None)     # the stages must not mistake the developer's own desktop for theirs
    return env


def bash(env, script, *args):
    r = subprocess.run(["bash", script, *args], capture_output=True, text=True, env=env)
    return r.returncode, r.stdout + r.stderr


def stage_script(rel):
    return os.path.join(STAGES, rel)


def test_state_set_round_trips_awkward_values(box):
    values = ["a b", "it's", 'say "hi"', "$HOME `id` $(id)", "back\\slash", "", "line1\nline2", "  lead", "x=y"]
    lines = "\n".join('state_set V%d %s' % (i, "'" + v.replace("'", "'\\''") + "'") for i, v in enumerate(values))
    r = subprocess.run(["bash", "-c", '. "$UITEST_STAGES/common/lib.sh"\n' + lines], capture_output=True, text=True, env=box)
    assert r.returncode == 0, r.stderr
    echo = "\n".join('printf "%%s\\0" "$V%d"' % i for i in range(len(values)))
    r = subprocess.run(["bash", "-c", '. "$UITEST_STAGES/common/lib.sh"\n' + echo], capture_output=True, text=True, env=box)
    assert r.stdout.split("\0")[:-1] == values


def test_state_set_replaces_and_unsets(box):
    script = '. "$UITEST_STAGES/common/lib.sh"; state_set A 1; state_set A 2; state_set B x; state_unset B; echo "A=$A B=${B:-gone}"; cat "$UITEST_STATE"'
    r = subprocess.run(["bash", "-c", script], capture_output=True, text=True, env=box)
    assert r.stdout.splitlines() == ["A=2 B=gone", "export A=2"]


def test_state_set_rejects_a_bad_name(box):
    r = subprocess.run(["bash", "-c", '. "$UITEST_STAGES/common/lib.sh"; state_set "a b" 1'], capture_output=True, text=True, env=box)
    assert r.returncode == 1 and "not a variable name" in r.stderr


@pytest.mark.parametrize("content, line", [("garbage\n", "line 1"), ("export A=1\nrm -rf x\n", "line 2"), ("export A='unclosed\n", "")])
def test_malformed_state_file_is_reported_with_the_fix(box, tmp_path, content, line):
    (tmp_path / "state.env").write_text(content)
    rc, out = bash(box, stage_script("common/collect.sh"))
    assert rc == 1 and "malformed" in out and line in out
    assert "delete it, or run `stage.sh tidyup --all`" in out


def test_tidyup_all_clears_a_malformed_state_file(box, tmp_path):
    (tmp_path / "state.env").write_text("garbage\n")
    rc, out = bash(box, stage_script("common/tidyup.sh"), "--all")
    assert rc == 0 and "clearing it" in out and (tmp_path / "state.env").read_text() == ""


def test_plain_tidyup_with_a_malformed_state_file_points_at_all(box, tmp_path):
    (tmp_path / "state.env").write_text("garbage\n")
    rc, out = bash(box, stage_script("common/tidyup.sh"))
    assert rc == 1 and "tidyup --all" in out


def test_stage_without_uitest_stages_says_how_to_run_it(box):
    box.pop("UITEST_STAGES")
    r = subprocess.run(["bash", stage_script("common/collect.sh")], capture_output=True, text=True, env=box)
    assert r.returncode != 0 and "UITEST_STAGES is not set" in r.stderr and "uitest stages shell" in r.stderr


def test_collect_with_nothing_prints_instructions_and_exits_1(box, tmp_path):
    rc, out = bash(box, stage_script("common/collect.sh"), str(tmp_path / "dest"))
    assert rc == 1
    for item in ("stage logs", "game.out", "Latest.log", "state.env"):
        assert "missing: " + item in out
    assert "`stage.sh start`" in out and "`stage.sh launch-linux`" in out
    assert not (tmp_path / "dest").exists()


def test_collect_copies_what_exists_and_names_what_is_missing(box, tmp_path):
    (tmp_path / "logs").mkdir()
    (tmp_path / "logs" / "gnome-shell.log").write_text("shell")
    (tmp_path / "state.env").write_text("export WAYLAND_DISPLAY=uitest-wl\n")
    rc, out = bash(box, stage_script("common/collect.sh"), str(tmp_path / "dest"))
    assert rc == 0, out
    assert (tmp_path / "dest/logs/gnome-shell.log").read_text() == "shell" and (tmp_path / "dest/state.env").exists()
    assert "missing: game.out" in out and "missing: Latest.log" in out and "missing: stage logs" not in out
    assert "collected:" in out


def test_collect_finds_the_games_latest_log_and_notes_a_gone_folder(box, tmp_path):
    game = tmp_path / "run"; (game / "x").mkdir(parents=True); (game / "x/Latest.log").write_text("log")
    (tmp_path / "logs").mkdir(); (tmp_path / "logs/game.out").write_text("out")
    (tmp_path / "state.env").write_text("export GAME_DIR=%s\n" % game)
    rc, out = bash(box, stage_script("common/collect.sh"), str(tmp_path / "d1"))
    assert rc == 0 and (tmp_path / "d1/logs/Latest.log").read_text() == "log" and (tmp_path / "d1/logs/game.out").read_text() == "out"
    shutil.rmtree(game)
    rc, out = bash(box, stage_script("common/collect.sh"), str(tmp_path / "d2"))
    assert rc == 0 and "game folder" in out and "is gone" in out


def test_collect_into_an_unwritable_place_says_what_to_do(box, tmp_path):
    (tmp_path / "state.env").write_text("export A=1\n")
    blocker = tmp_path / "file"; blocker.write_text("x")
    rc, out = bash(box, stage_script("common/collect.sh"), str(blocker / "dest"))
    assert rc == 1 and "cannot create" in out and "stage.sh collect /tmp/mine" in out


def test_tidyup_with_nothing_running_says_so_and_exits_0(box):
    rc, out = bash(box, stage_script("common/tidyup.sh"))
    assert rc == 0 and "nothing to tidy up" in out
    rc, out = bash(box, stage_script("common/tidyup.sh"), "--all")
    assert rc == 0 and "nothing to tidy up" in out


def test_tidyup_rejects_an_unknown_option(box):
    rc, out = bash(box, stage_script("common/tidyup.sh"), "--everything")
    assert rc == 1 and "unknown option" in out and "Usage: tidyup.sh [--all]" in out


def test_observe_and_launch_before_start_say_to_run_start(box, tmp_path):
    app = tmp_path / "ok.AppImage"; app.write_bytes(b"\x7fELF" + b"\0" * 8)
    for script, args in (("desktops/gnome/wayland/observe.sh", []), ("common/launch-linux.sh", [str(app)])):
        rc, out = bash(box, stage_script(script), *args)
        assert rc == 1 and "no desktop running (WAYLAND_DISPLAY not set in %s)" % (tmp_path / "state.env") in out, out
        assert "run `stage.sh start` first" in out


def test_launch_x11_session_asks_for_display(box, tmp_path):
    box["UITEST_SESSION"] = "x11"
    app = tmp_path / "ok.AppImage"; app.write_bytes(b"\x7fELF")
    rc, out = bash(box, stage_script("common/launch-linux.sh"), str(app))
    assert rc == 1 and "DISPLAY not set" in out


def test_dead_desktop_is_reported(box, tmp_path):
    (tmp_path / "state.env").write_text("export WAYLAND_DISPLAY=w\nexport DESKTOP_PIDS=999999\n")
    rc, out = bash(box, stage_script("desktops/gnome/wayland/observe.sh"))
    assert rc == 1 and "the desktop has died" in out and "tidyup --all" in out


def started(tmp_path):
    """A state file for a desktop that looks started: its pid is this test process."""
    (tmp_path / "state.env").write_text("export WAYLAND_DISPLAY=w\nexport DESKTOP_PIDS=%d\n" % os.getpid())


@pytest.mark.parametrize("content, found", [
    (None, "no AppImage at"), (b"", "empty"), (b"#!/bin/sh\n", "starts with 23212f62"), (b"PK\x03\x04", "starts with 504b0304"), ("dir", "is a folder")])
def test_launch_checks_the_appimage(box, tmp_path, content, found):
    started(tmp_path)
    app = tmp_path / "x.AppImage"
    if content == "dir": app.mkdir()
    elif content is not None: app.write_bytes(content)
    rc, out = bash(box, stage_script("common/launch-linux.sh"), str(app))
    assert rc == 1 and found in out, out


@pytest.mark.parametrize("args, msg", [
    (["--game", "wayland"], "--game must be native or x11"), (["--game"], "--game needs a value"), (["--window", "big"], "--window must be WxH"),
    (["--window"], "--window needs a value"), (["--nope"], "unknown option --nope")])
def test_launch_option_errors(box, tmp_path, args, msg):
    rc, out = bash(box, stage_script("common/launch-linux.sh"), *args)
    assert rc == 1 and msg in out


@pytest.mark.parametrize("args, msg", [
    (["--wait", "soon"], "--wait must be a whole number"), (["--settle", "-1"], "--settle must be a whole number"), (["--wait"], "--wait needs a value"),
    (["--screenshot", "/no/such/dir/x.png"], "folder /no/such/dir does not exist"), (["--nope"], "unknown option --nope"),
    (["--window-shot"], "--window-shot needs a value"), (["--window-shot", "/no/such/dir/x.png"], "folder /no/such/dir does not exist")])
def test_observe_option_errors(box, args, msg):
    rc, out = bash(box, stage_script("desktops/gnome/wayland/observe.sh"), *args)
    assert rc == 1 and msg in out


def test_observe_needs_a_launched_game(box, tmp_path):
    started(tmp_path)
    rc, out = bash(box, stage_script("desktops/gnome/wayland/observe.sh"))
    assert rc == 1 and "no game launched (GAME_PID not set" in out and "stage.sh launch-linux" in out


def test_observe_skips_the_game_check_for_a_game_the_framework_started(box, tmp_path):
    """UITEST_GAME_EXTERNAL=1 (set by the framework's kind stages session): no GAME_PID needed; it goes on to ask GNOME."""
    started(tmp_path)
    rc, out = bash({**box, "UITEST_GAME_EXTERNAL": "1"}, stage_script("desktops/gnome/wayland/observe.sh"), "--wait", "0")
    assert rc == 1 and "no game launched" not in out and ("GNOME Shell is not answering" in out or "is not installed" in out), out


@pytest.mark.parametrize("seconds, command, rc, tries", [("0", "true", 0, 1), ("0", "false", 1, 1), ("1", "false", 1, 2)])
def test_wait_for_tries_at_least_once(box, tmp_path, seconds, command, rc, tries):
    """wait_for 0 is one check (observe.sh --wait 0, which the GNOME probe uses); before, it gave up without looking."""
    log = tmp_path / "tries"
    script = '. "$UITEST_STAGES/common/lib.sh"; try() { echo x >> "%s"; %s; }; wait_for %s try' % (log, command, seconds)
    r = subprocess.run(["bash", "-c", script], capture_output=True, text=True, env=box)
    assert r.returncode == rc and log.read_text().count("x") == tries


def stage_sh(env, *args, **over):
    r = subprocess.run(["bash", stage_script("bin/stage.sh"), *args], capture_output=True, text=True, env={**env, **over})
    return r.returncode, r.stdout + r.stderr


@pytest.mark.parametrize("missing", ["UITEST_STAGES", "UITEST_DISTRO", "UITEST_DESKTOP", "UITEST_SESSION"])
def test_stage_sh_needs_its_environment(box, missing):
    box.pop(missing)
    rc, out = stage_sh(box, "start")
    assert rc == 2 and missing + " is not set" in out and "uitest stages shell" in out


def test_stage_sh_unknown_stage_lists_the_ones_that_exist(box):
    rc, out = stage_sh(box, "nope")
    assert rc == 2 and "no stage 'nope'" in out
    for name in ("collect", "launch-linux", "observe", "start", "tidyup"):
        assert name in out.split("exist for this run:")[1].split()
    assert "lib" not in out.split("exist for this run:")[1].split() and "gnome" not in out.split("exist for this run:")[1].split()


def test_stage_sh_rejects_a_path_as_stage_name(box):
    rc, out = stage_sh(box, "../resolve")
    assert rc == 2 and "no stage" in out


def test_stage_sh_which_and_list_and_no_args(box):
    rc, out = stage_sh(box, "which", "observe")
    assert rc == 0 and out.strip() == stage_script("desktops/gnome/wayland/observe.sh")
    rc, out = stage_sh(box, "list")
    assert rc == 0 and out.split() == ["collect", "launch-linux", "observe", "start", "tidyup"]
    rc, out = stage_sh(box)
    assert rc == 2 and "no stage given" in out and "usage:" in out
    assert stage_sh(box, "which")[0] == 2


def test_stage_sh_on_an_unknown_cell_lists_only_what_resolves(box):
    rc, out = stage_sh(box, "list", UITEST_DESKTOP="kde")
    assert rc == 0 and out.split() == ["collect", "launch-linux", "tidyup"]


def test_stage_sh_runs_the_resolved_script(box, tmp_path):
    rc, out = stage_sh(box, "tidyup")
    assert rc == 0 and "stage tidyup: common/tidyup.sh" in out and "nothing to tidy up" in out


# ---- stages-run.py
def load_stages_run():
    path = os.path.join(STAGES, "bin", "stages-run.py")
    loader = importlib.machinery.SourceFileLoader("stages_run", path)
    spec = importlib.util.spec_from_loader("stages_run", loader)
    m = importlib.util.module_from_spec(spec)
    sys.modules["stages_run"] = m          # dataclasses looks the module up here
    loader.exec_module(m)
    return m


sr = load_stages_run()


def result(**kw):
    base = dict(distro="ubuntu-26.04", desktop="gnome", session=sr.Session.WAYLAND, game=sr.GameMode.NATIVE, build="pr81", run=2,
                client=sr.Client.WAYLAND, frame=(1280, 757), titlebar=37, focus=True, found=True)
    return sr.Result(**{**base, **kw})


def observed(text, rc=0, **kw):
    args = dict(returncode=rc, distro="ubuntu-26.04", desktop="gnome", session=sr.Session.WAYLAND, game=sr.GameMode.NATIVE, build="b", run=1)
    return sr.Result.from_observation(text, **{**args, **kw})


def obs(client="wayland", frame=(0, 0, 1280, 757), focus=True, game=True):
    return json.dumps({"screen": [1920, 1080], "windows": [{"title": "Oolite", "client": client, "frame": list(frame), "focus": focus}], "game": game})


GOOD = ("RESULT wm=gnome-wayland-native distro=ubuntu-26.04 desktop=gnome session=wayland game=native build=pr81 run=2 "
        "client=wayland frame=1280x757 titlebar=37 focus=1 found=1")


def test_result_format_matches_the_documented_line():
    assert result().format() == GOOD


def test_result_round_trips():
    for r in (result(), result(game=sr.GameMode.X11, client=sr.Client.X11, titlebar=0, focus=False),
              result(client=sr.Client.NONE, frame=(0, 0), titlebar=0, focus=False, found=False, why="no_game_window")):
        assert sr.Result.parse(r.format()) == r
    assert sr.Result.parse(GOOD) == result()


@pytest.mark.parametrize("line", [
    "", "hello", "RESULT", "RESULT wm=gnome-wayland-native", GOOD.replace("RESULT ", "RESULTS "),
    GOOD.replace("session=wayland", "session=mir"), GOOD.replace("game=native", "game=wayland"), GOOD.replace("client=wayland", "client=tty"),
    GOOD.replace("frame=1280x757", "frame=1280"), GOOD.replace("run=2", "run=two"), GOOD.replace("run=2", "run=0"), GOOD.replace("focus=1", "focus=yes"),
    GOOD.replace("found=1", "found=2"), GOOD.replace("wm=gnome-wayland-native", "wm=kde-wayland-native"), GOOD + " extra=1", GOOD + " found=1",
    GOOD.replace(" focus=1", ""), GOOD.replace("build=pr81", "build="), GOOD.replace("titlebar=37", "titlebar=big"), GOOD + " naked"])
def test_result_parse_rejects_malformed_lines(line):
    with pytest.raises(sr.ResultError):
        sr.Result.parse(line)


def test_result_rejects_unsafe_values():
    for kw in ({"build": "a b"}, {"build": "a/b"}, {"distro": ""}, {"run": 0}, {"why": "has space"}):
        with pytest.raises(sr.ResultError): result(**kw)


def test_result_is_frozen():
    with pytest.raises(dataclasses.FrozenInstanceError): result().run = 3


def test_observation_with_a_window():
    r = observed(obs(), window="1280x720")
    assert (r.client, r.frame, r.titlebar, r.focus, r.found, r.why) == (sr.Client.WAYLAND, (1280, 757), 37, True, True, None)
    r = observed(obs(client="x11", frame=(0, 0, 1280, 720), focus=False), window="1280x720")
    assert (r.client, r.titlebar, r.focus, r.found) == (sr.Client.X11, 0, False, True)


def test_observation_uses_the_last_line_and_the_asked_window_size():
    r = observed("noise\n" + obs(frame=(0, 0, 800, 637)) + "\n", window="800x600")
    assert r.found and r.titlebar == 37


def test_observation_with_a_bad_window_size_falls_back_to_the_default():
    assert observed(obs(), window="garbage").titlebar == 37


@pytest.mark.parametrize("text, rc, why", [
    ("", 1, "observe_printed_nothing_exit_1"), ("  \n\n", 0, "observe_printed_nothing_exit_0"), ("GNOME Shell is not answering", 1, "observe_output_not_json"),
    ("{broken", 0, "observe_output_not_json"), ("[1, 2]", 0, "observe_json_not_an_object"), ('"text"', 0, "observe_json_not_an_object"), ("{}", 0, "observe_json_missing_game"),
    ('{"game": true}', 0, "observe_json_missing_windows"), ('{"game": false, "windows": [{}]}', 1, "no_game_window"), ('{"game": true, "windows": []}', 0, "no_game_window"),
    ('{"game": true, "windows": ["x"]}', 0, "observe_window_not_an_object"), ('{"game": true, "windows": [{"client": "x11"}]}', 0, "observe_window_missing_frame"),
    ('{"game": true, "windows": [{"client": "x11", "frame": [0, 0, 1, 2]}]}', 0, "observe_window_missing_focus"),
    ('{"game": true, "windows": [{"client": "tty", "frame": [0, 0, 1, 2], "focus": true}]}', 0, "observe_window_bad_client_or_frame"),
    ('{"game": true, "windows": [{"client": "x11", "frame": [0, 0], "focus": true}]}', 0, "observe_window_bad_client_or_frame"),
    ('{"game": true, "windows": [{"client": "x11", "frame": [0, 0, "a", "b"], "focus": true}]}', 0, "observe_window_bad_client_or_frame")])
def test_unusable_observe_output_is_found_0_with_a_reason(text, rc, why):
    r = observed(text, rc=rc)
    assert (r.found, r.client, r.frame, r.titlebar, r.focus, r.why) == (False, sr.Client.NONE, (0, 0), 0, False, why)
    assert r.format().endswith("found=0 why=" + why) and sr.Result.parse(r.format()) == r


def test_stages_run_args():
    a = sr.parse_args(["--game", "native,x11", "--runs", "2", "--label", "L"])
    assert (a.game, a.runs, a.label, a.out) == ([sr.GameMode.NATIVE, sr.GameMode.X11], 2, "L", "/out")
    assert sr.parse_args(["--label", "L"]).game == list(sr.GameMode)


@pytest.mark.parametrize("bad", [["--label", "L", "--game", "wayland"], ["--label", "L", "--game", "native,native"], ["--label", "L", "--game", ""],
                                 ["--label", "L", "--runs", "0"], ["--label", "L", "--runs", "x"], ["--game", "native"], ["--label", "a b"], ["--label", "a/b"]])
def test_stages_run_rejects_bad_args(bad, capsys):
    with pytest.raises(SystemExit) as e: sr.parse_args(bad)
    assert e.value.code == 2
    assert "error:" in capsys.readouterr().err


def test_stages_run_bad_game_names_the_choices(capsys):
    with pytest.raises(SystemExit): sr.parse_args(["--label", "L", "--game", "foo"])
    assert "choose from native, x11" in capsys.readouterr().err


def test_state_value(tmp_path):
    f = tmp_path / "s.env"; f.write_text("export A=1\nexport GAME_WINDOW=1280x720\nexport SP=a\\ b\nexport Q=''\n")
    assert sr.state_value(str(f), "GAME_WINDOW") == "1280x720" and sr.state_value(str(f), "NOPE") is None
    assert sr.state_value(str(f), "SP") == "a b" and sr.state_value(str(f), "Q") == ""
    assert sr.state_value(str(tmp_path / "missing"), "A") is None
    f.write_text("export A='unclosed\n")
    assert sr.state_value(str(f), "A") is None


def test_stages_run_environment_errors(monkeypatch):
    for k in ("UITEST_DISTRO", "UITEST_DESKTOP", "UITEST_SESSION"): monkeypatch.delenv(k, raising=False)
    with pytest.raises(SystemExit) as e: sr.environment()
    assert "UITEST_DISTRO, UITEST_DESKTOP, UITEST_SESSION not set" in str(e.value) and "uitest stages run" in str(e.value)
    monkeypatch.setenv("UITEST_DISTRO", "d"); monkeypatch.setenv("UITEST_DESKTOP", "de"); monkeypatch.setenv("UITEST_SESSION", "mir")
    with pytest.raises(SystemExit) as e: sr.environment()
    assert "UITEST_SESSION is 'mir'" in str(e.value) and "wayland, x11" in str(e.value)
    monkeypatch.setenv("UITEST_SESSION", "x11")
    assert sr.environment() == ("d", "de", sr.Session.X11)


def test_host_and_container_enums_agree():
    for name in ("GameMode", "Session"):
        assert [m.value for m in getattr(sr, name)] == [m.value for m in getattr(stages, name)]


# ---- uitest stages: validation (all before Docker)
def parse(*extra, cell=("ubuntu-26.04", "gnome", "wayland"), build="x:" + __file__):
    return stages.parser().parse_args(["run", *cell, "--build", build, *extra])


def test_docker_cmd_mounts_only_stages_app_and_out():
    a = parse()
    cmd = stages.docker_cmd(a, "/b/oolite.AppImage", "/r/out", False)
    mounts = [cmd[i + 1] for i, c in enumerate(cmd) if c == "-v"]
    assert mounts == [STAGES + ":/stages:ro", "/b/oolite.AppImage:/app/oolite.AppImage:ro", "/r/out:/out"]
    assert "-it" not in cmd and cmd[-1] == "oolite-stages-ubuntu-26.04"
    assert "UITEST_SESSION=wayland" in cmd and not any(".X11-unix" in c for c in cmd)
    assert "-it" in stages.docker_cmd(a, "/b", "/o", True)


def test_summary_counts():
    lines = [result(run=i).format() for i in (1, 2)]
    s = stages.summary(lines, ["native", "x11"], 2)
    assert "2 RESULT lines, 4 expected" in s and "native runs=2 found=2 client=wayland titlebar=37,37" in s and "x11    runs=0" in s


def test_main_dispatches_stages(monkeypatch):
    monkeypatch.setattr(stages, "main", lambda argv: 7)
    assert hostrun.main(["stages", "x"]) == 7


@pytest.fixture
def tree(tmp_path, monkeypatch):
    """A temp copy of the stages tree, so tests can add folders without touching the real one."""
    root = tmp_path / "tree" / "stages"
    shutil.copytree(STAGES, root, ignore=shutil.ignore_patterns("__pycache__"))
    monkeypatch.setattr(stages, "STAGES", str(root))
    return root


def test_the_shipped_distro_passes():
    stages.check_distro("ubuntu-26.04")
    assert stages.distros() == ["ubuntu-26.04"]


def test_empty_distro_folder_is_rejected_with_the_fix(tree):
    (tree / "distros" / "ubuntu-23").mkdir()
    with pytest.raises(stages.StagesError) as e: stages.check_distro("ubuntu-23")
    assert str(e.value) == ("stages/distros/ubuntu-23 has no Dockerfile: add one (see stages/README.md, Add a distro) or use one of: ubuntu-26.04")
    assert stages.distros() == ["ubuntu-26.04"]


def test_empty_dockerfile_and_one_without_from_are_rejected(tree):
    d = tree / "distros" / "ubuntu-23"; d.mkdir()
    (d / "Dockerfile").write_text("")
    with pytest.raises(stages.StagesError, match="Dockerfile is empty"): stages.check_distro("ubuntu-23")
    (d / "Dockerfile").write_text("# nothing here\nRUN true\n")
    with pytest.raises(stages.StagesError, match="no FROM line"): stages.check_distro("ubuntu-23")
    (d / "Dockerfile").write_text("FROM ubuntu:23.04\n")
    stages.check_distro("ubuntu-23")


def test_a_dockerfile_that_is_a_folder_is_rejected(tree):
    d = tree / "distros" / "ubuntu-23"; (d / "Dockerfile").mkdir(parents=True)
    with pytest.raises(stages.StagesError, match="has no Dockerfile"): stages.check_distro("ubuntu-23")


def test_unknown_distro_lists_the_known_ones(tree):
    with pytest.raises(stages.StagesError) as e: stages.check_distro("nope")
    assert "no distro 'nope'" in str(e.value) and "ubuntu-26.04" in str(e.value)


def test_ensure_image_refuses_a_distro_without_a_dockerfile(tree, capsys):
    (tree / "distros" / "ubuntu-23").mkdir()
    assert stages.ensure_image("ubuntu-23") is False
    assert "has no Dockerfile" in capsys.readouterr().err


def test_unknown_distro_has_no_image(capsys):
    assert stages.ensure_image("no-such-distro") is False
    assert "no distro" in capsys.readouterr().err


def test_the_shipped_cell_passes_and_unknown_ones_list_the_pairs(tree):
    stages.check_cell("ubuntu-26.04", "gnome", "wayland")
    for desktop, session in (("kde", "wayland"), ("gnome", "x11")):
        with pytest.raises(stages.StagesError) as e: stages.check_cell("ubuntu-26.04", desktop, session)
        msg = str(e.value)
        assert "no 'start', 'observe' stage" in msg and "pairs that work for ubuntu-26.04: gnome wayland" in msg and "Add a desktop" in msg


def test_a_desktop_with_only_start_names_what_is_missing(tree):
    d = tree / "desktops" / "kde" / "wayland"; d.mkdir(parents=True); (d / "start.sh").write_text("#!/bin/bash\n")
    with pytest.raises(stages.StagesError) as e: stages.check_cell("ubuntu-26.04", "kde", "wayland")
    assert "no 'observe' stage" in str(e.value) and "'start'" not in str(e.value)
    (d / "observe.sh").write_text("#!/bin/bash\n")
    stages.check_cell("ubuntu-26.04", "kde", "wayland")
    assert "kde wayland" in stages.known_cells("ubuntu-26.04")


def test_an_empty_desktop_folder_is_not_a_cell(tree):
    (tree / "desktops" / "kde" / "wayland").mkdir(parents=True)
    assert stages.known_cells("ubuntu-26.04") == ["gnome wayland"]


def make_app(tmp_path, content=b"\x7fELF\x02\x01", name="app.AppImage"):
    p = tmp_path / name; p.write_bytes(content); return str(p)


def test_build_forms_for_run(tmp_path):
    app = make_app(tmp_path)
    assert stages.parse_build(stages.Action.RUN, "master:" + app) == ("master", app)
    for bad, msg in (("nocolon", "LABEL:PATH"), (":" + app, "LABEL:PATH"), ("master:", "LABEL:PATH"), ("a b:" + app, "must be letters, digits"),
                     ("a/b:" + app, "must be letters, digits"), ("-x:" + app, "must be letters, digits"),
                     ("m:" + str(tmp_path / "missing"), "does not exist"), ("m:" + str(tmp_path), "is a folder"),
                     ("m:" + make_app(tmp_path, b"#!/bin/sh\n", "sh.AppImage"), "starts with 23212f62"), ("m:" + make_app(tmp_path, b"", "empty.AppImage"), "empty file")):
        with pytest.raises(stages.StagesError) as e: stages.parse_build(stages.Action.RUN, bad)
        assert msg in str(e.value), (bad, str(e.value))


def test_build_form_for_shell(tmp_path):
    app = make_app(tmp_path)
    assert stages.parse_build(stages.Action.SHELL, app) == ("shell", app)
    with pytest.raises(stages.StagesError, match="PATH, not LABEL:PATH"): stages.parse_build(stages.Action.SHELL, "x:" + app)
    with pytest.raises(stages.StagesError, match="does not exist"): stages.parse_build(stages.Action.SHELL, str(tmp_path / "nope"))


def test_appimage_problem_on_a_fifo_and_unreadable(tmp_path):
    fifo = tmp_path / "f"; os.mkfifo(fifo)
    assert "not a regular file" in stages.appimage_problem(str(fifo))
    if os.geteuid() != 0:
        p = tmp_path / "locked"; p.write_bytes(b"\x7fELF"); p.chmod(0)
        assert "cannot be read" in stages.appimage_problem(str(p))


def test_bad_arguments_get_argparses_error_with_the_choices(capsys):
    for argv, msg in ((["run", "ubuntu-26.04", "gnome", "mir", "--build", "x:y"], "choose from wayland, x11"),
                      (["run", "ubuntu-26.04", "gnome", "wayland", "--build", "x:y", "--game", "gnome"], "choose from native, x11"),
                      (["run", "ubuntu-26.04", "gnome", "wayland", "--build", "x:y", "--runs", "0"], "must be at least 1"),
                      (["run", "../etc", "gnome", "wayland", "--build", "x:y"], "invalid name"),
                      (["fly", "ubuntu-26.04", "gnome", "wayland", "--build", "x:y"], "choose from shell, run"),
                      (["run", "ubuntu-26.04", "gnome", "wayland"], "--build")):
        with pytest.raises(SystemExit) as e: stages.parser().parse_args(argv)
        assert e.value.code == 2 and msg in capsys.readouterr().err, argv


def test_parser_returns_enums():
    a = parse("--game", "x11")
    assert a.action is stages.Action.RUN and a.session is stages.Session.WAYLAND and a.game == [stages.GameMode.X11] and a.runs == 3


def run_main(argv, capsys):
    rc = stages.main(argv)
    return rc, capsys.readouterr().err


def test_main_checks_everything_before_docker(tree, tmp_path, monkeypatch, capsys):
    """Docker is made to explode if touched: every one of these must stop first."""
    def boom(*a, **k): raise AssertionError("docker was reached")
    monkeypatch.setattr(stages, "_docker_state", boom)
    monkeypatch.setattr(subprocess, "run", subprocess.run)    # the resolver still runs
    app = make_app(tmp_path)
    (tree / "distros" / "ubuntu-23").mkdir()
    cases = [(["run", "ubuntu-23", "gnome", "wayland", "--build", "x:" + app], "stages/distros/ubuntu-23 has no Dockerfile"),
             (["shell", "ubuntu-23", "gnome", "wayland", "--build", app], "stages/distros/ubuntu-23 has no Dockerfile"),
             (["run", "ubuntu-26.04", "kde", "wayland", "--build", "x:" + app], "no 'start', 'observe' stage"),
             (["run", "ubuntu-26.04", "gnome", "x11", "--build", "x:" + app], "pairs that work"),
             (["run", "ubuntu-26.04", "gnome", "wayland", "--build", "nocolon"], "LABEL:PATH"),
             (["run", "ubuntu-26.04", "gnome", "wayland", "--build", "x:" + str(tmp_path / "missing")], "does not exist"),
             (["run", "ubuntu-26.04", "gnome", "wayland", "--build", "x:" + make_app(tmp_path, b"text")], "ELF magic")]
    for argv, msg in cases:
        rc, err = run_main(argv, capsys)
        assert rc == 2 and msg in err, (argv, err)


def test_main_reports_docker_missing(tree, tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(stages, "_docker_state", lambda: (False, "docker missing"))
    rc, err = run_main(["run", "ubuntu-26.04", "gnome", "wayland", "--build", "x:" + make_app(tmp_path)], capsys)
    assert rc == 2 and "Docker is not usable: docker missing" in err and "install it" in err and "systemctl start docker" in err


def test_main_stops_when_the_image_cannot_be_built(tree, tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(stages, "_docker_state", lambda: (True, ""))
    monkeypatch.setattr(stages, "ensure_image", lambda d: False)
    rc, err = run_main(["run", "ubuntu-26.04", "gnome", "wayland", "--build", "x:" + make_app(tmp_path)], capsys)
    assert rc == 2 and "image build failed" in err and "stages/distros/ubuntu-26.04/" in err


def test_run_reports_an_unwritable_output_folder(tmp_path, capsys):
    blocker = tmp_path / "f"; blocker.write_text("x")
    a = parse("--out", str(blocker / "out"))
    assert stages.run(a, "x", "/app") == 2
    assert "cannot create the output folder" in capsys.readouterr().err
