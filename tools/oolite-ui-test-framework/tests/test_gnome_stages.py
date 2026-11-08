"""Kind "stages" environments (#80 step 2a): observe.sh's JSON read by window_probes.parse_observe, the GNOME probe and backend, the
stages state file, the registry entries, the docker command and the RESULT fields. No Docker, no game, no GNOME: the samples below
are observe.sh's real output from Ubuntu 26.04 GNOME 50 (pre-#81 build and #81 build, game native and x11)."""
import json
import subprocess

import pytest

from oolite_ui_test_framework import hostrun, plugin, registry, session, window_probes
from oolite_ui_test_framework.window_probes import ObserveError, parse_observe


def win(**kw):
    w = {"title": "Oolite v1.93", "client": "wayland", "decorated": False, "frame": [320, 196, 1280, 720], "buffer": [320, 196, 1280, 720],
         "content": [320, 196, 1280, 720], "title_bar": 0, "focus": True, "fullscreen": False, "maximized": False}
    w.update(kw); return w


def doc(*wins, game=True, screen=(1920, 1080)):
    return json.dumps({"screen": list(screen), "windows": list(wins), "game": game})


OLD_NATIVE = doc(win())
NEW_NATIVE = doc(win(frame=[316, 176, 1288, 760], buffer=[320, 212, 1280, 720], content=[320, 212, 1280, 720], title_bar=36))
X11 = doc(win(client="x11", decorated=True, frame=[320, 196, 1280, 757], buffer=[295, 171, 1330, 807], content=[320, 233, 1280, 720], title_bar=37))


@pytest.mark.parametrize("text, framed, outer, client", [
    (OLD_NATIVE, 0, (320, 196, 1280, 720), (320, 196, 1280, 720)),     # #75: no title bar
    (NEW_NATIVE, 1, (316, 176, 1288, 760), (320, 212, 1280, 720)),     # libdecor draws one (#81)
    (X11, 1, (320, 196, 1280, 757), (320, 233, 1280, 720))])           # mutter draws one for an X11 client
def test_observe_output_to_obs(text, framed, outer, client):
    o = parse_observe(text)
    assert (o.framed, o.focused, o.outer, o.client, o.mon, o.fullscreen, o.source) == (framed, 1, outer, client, (0, 0, 1920, 1080), 0, "compositor")


def test_no_game_window_or_one_not_placed_yet_is_none():
    assert parse_observe(doc(win(title="Files"), game=False)) is None
    assert parse_observe(doc(win(frame=[0, 0, 0, 0]))) is None    # GNOME lists a new window as 0x0 at 0,0 before placing it


def test_the_focused_game_window_is_the_one_measured():
    o = parse_observe(doc(win(focus=False, frame=[1, 1, 10, 10]), win(focus=True, frame=[2, 2, 20, 20])))
    assert o.outer == (2, 2, 20, 20)
    assert parse_observe(doc(win(focus=False, frame=[1, 1, 10, 10]), win(focus=False, frame=[2, 2, 20, 20]))).outer == (1, 1, 10, 10)


@pytest.mark.parametrize("text, msg", [
    ("", "not JSON"), ("[1]", "not a JSON object"), (json.dumps({"screen": [1, 1], "windows": []}), "no 'game' field"),
    (doc(win(), screen=(0, 1)), "screen is"), (json.dumps({"screen": [1, 1], "windows": [], "game": 1}), "game is 1"),
    (json.dumps({"screen": [1, 1], "windows": {}, "game": True}), "windows is"), (doc(game=True), "windows is empty"),
    (doc(win(client="mir")), "windows[0].client"), (doc(win(focus=1)), "windows[0].focus is 1"),
    (doc(win(title_bar=-1)), "windows[0].title_bar"), (doc(win(title_bar=True)), "windows[0].title_bar"),
    (doc(win(frame=[1, 2, 3])), "windows[0].frame"), (doc(win(content=[1, 2, 3, 4.5])), "windows[0].content"),
    (doc(win(buffer=[1, 2, 3, True])), "windows[0].buffer"), (doc(win(), "x"), "windows[1] is")])
def test_malformed_observe_output_names_the_field(text, msg):
    with pytest.raises(ObserveError) as e: parse_observe(text)
    assert msg in str(e.value)


def fake_run(stdout="", stderr="", rc=0, calls=None):
    def run(cmd, **kw):
        if calls is not None: calls.append((cmd, kw["env"]))
        return subprocess.CompletedProcess(cmd, rc, stdout, stderr)
    return run


def test_probe_runs_one_look_of_observe_for_a_game_it_did_not_launch():
    calls = []
    p = window_probes.GnomeProbe({"UITEST_STAGES": "/s"}, run=fake_run("stage observe: ...\n" + X11 + "\n", calls=calls))
    assert p.observe().framed == 1
    cmd, env = calls[0]
    assert cmd == ["/s/bin/stage.sh", "observe", "--wait", "0", "--settle", "0"] and env["UITEST_GAME_EXTERNAL"] == "1"


def test_probe_reports_a_silent_or_hung_observe():
    with pytest.raises(ObserveError, match=r"printed nothing \(exit 1\): observe.sh: GNOME Shell is not answering"):
        window_probes.GnomeProbe({}, run=fake_run(stderr="observe.sh: GNOME Shell is not answering", rc=1)).observe()

    def hung(cmd, **kw): raise subprocess.TimeoutExpired(cmd, 30)
    with pytest.raises(ObserveError, match="did not answer in 30 s"):
        window_probes.GnomeProbe({}, run=hung).observe()


def test_backend_finds_the_window_through_the_probe():
    assert window_probes.GnomeBackend(window_probes.GnomeProbe({}, run=fake_run(OLD_NATIVE))).find_window() == 1
    gone = window_probes.GnomeBackend(window_probes.GnomeProbe({}, run=fake_run(doc(win(), game=False), rc=1)))
    assert gone.find_window() is None and gone.grab(1) is None


def test_window_shot_reads_the_png_observe_wrote(tmp_path):
    from oolite_ui_test_framework import png

    def run(cmd, **kw):
        png.write_png(cmd[cmd.index("--window-shot") + 1], 2, 1, b"\x01\x02\x03\x04\x05\x06")
        return subprocess.CompletedProcess(cmd, 0, X11, "")
    assert window_probes.GnomeProbe({}, run=run).window_shot() == (2, 1, b"\x01\x02\x03\x04\x05\x06")
    failed = window_probes.GnomeProbe({}, run=fake_run(X11, "observe.sh: the window screenshot failed", rc=1))
    with pytest.raises(ObserveError, match="the window screenshot failed"): failed.window_shot()


def test_state_file_values_come_back_as_bash_reads_them(tmp_path):
    f = tmp_path / "state.env"
    script = 'printf "export %s=%q\\n" A "a b" B "it\'s \\$x" C ""'
    f.write_text(subprocess.run(["bash", "-c", script], capture_output=True, text=True).stdout)
    assert session.read_state(str(f)) == {"A": "a b", "B": "it's $x", "C": ""}
    (tmp_path / "empty.env").write_text("")
    assert session.read_state(str(tmp_path / "empty.env")) == {}


def test_state_file_problems_say_what_writes_it(tmp_path):
    with pytest.raises(session.SessionError, match="cannot read the stages state file .*`stage.sh start` writes it"):
        session.read_state(str(tmp_path / "none.env"))
    (tmp_path / "bad.env").write_text("export A='unclosed\n")
    with pytest.raises(session.SessionError, match="bash cannot read the stages state file"):
        session.read_state(str(tmp_path / "bad.env"))


@pytest.mark.parametrize("missing", ["UITEST_STAGES", "UITEST_DISTRO", "UITEST_DESKTOP", "UITEST_SESSION"])
def test_session_outside_its_container_says_so(monkeypatch, missing):
    for v in ("UITEST_STAGES", "UITEST_DISTRO", "UITEST_DESKTOP", "UITEST_SESSION"): monkeypatch.setenv(v, "x")
    monkeypatch.delenv(missing)
    s = session.Session(registry.load()[0]["gnome-wayland-native"], "1920x1080")
    with pytest.raises(session.SessionError, match=missing + " is not set"): s._start_stages()


def test_shipped_gnome_entries():
    envs = registry.load()[0]
    n, x = envs["gnome-wayland-native"], envs["gnome-wayland-x11"]
    assert n.kind == x.kind == "stages" and n.cell == x.cell == ["ubuntu-26.04", "gnome", "wayland"]
    assert (n.game, n.session, x.game, x.session) == ("native", "Wayland native", "x11", "XWayland")
    assert n.sees_window_state and n.keys_na    # input comes in step 2b


def stages_env(**kw):
    e = {"family": "gnome", "session": "XWayland", "kind": "stages", "cell": ["ubuntu-26.04", "gnome", "wayland"], "game": "x11"}
    e.update(kw); return {k: v for k, v in e.items() if v is not None}


@pytest.mark.parametrize("entry, msg", [
    (stages_env(image="ubuntu"), "takes no image or start"), (stages_env(start=["x"]), "takes no image or start"),
    (stages_env(cell=None), "needs cell = [distro, desktop, session]"), (stages_env(cell=["ubuntu-26.04", "gnome"]), "needs cell"),
    (stages_env(cell=["ubuntu-26.04", "", "wayland"]), "needs cell"), (stages_env(game="wayland"), 'needs game = "native" or "x11"'),
    (stages_env(game=None), "needs game")])
def test_stages_entry_errors(entry, msg):
    with pytest.raises(registry.RegistryError) as e: registry.parse({"images": {}, "env": {"bad": entry}})
    assert msg in str(e.value)


def test_docker_command_runs_pytest_as_player_and_copies_the_output(tmp_path):
    a = tmp_path / "x.AppImage"; a.write_bytes(b"\x7fELF")
    r = hostrun.Runner(hostrun.build_parser().parse_args(["x:%s" % a, "--out", str(tmp_path), "--name", "n1"]), ("x", str(a)))
    e = registry.load()[0]["gnome-wayland-x11"]
    cmd = r.stages_command(e, "c1", ["-v", "m:/m"], [], r.pytest_args("gnome-wayland-x11", "1920x1080", "p.raw", "/app/x.AppImage", out="/tmp/out"))
    i = cmd.index("oolite-stages-ubuntu-26.04")
    assert cmd[:6] == ["docker", "run", "--rm", "--init", "--name", "c1"] and "--user" not in cmd
    assert {"UITEST_STAGES=/uitest/stages", "UITEST_DISTRO=ubuntu-26.04", "UITEST_DESKTOP=gnome", "UITEST_SESSION=wayland"} <= set(cmd[:i])
    script = cmd[i + 3]
    assert cmd[i + 1:i + 3] == ["bash", "-c"] and "mkdir -p /tmp/out/n1.parts" in script and "sudo cp -r --no-preserve=all /tmp/out/. /out/" in script
    assert "/tmp/out/n1.parts/p.raw" in cmd and "--ui-env" in cmd


def test_result_lines_name_the_cell():
    e = registry.load()[0]["gnome-wayland-native"]
    assert plugin.cell_fields(e) == {"distro": "ubuntu-26.04", "desktop": "gnome", "session": "wayland", "game": "native"}
