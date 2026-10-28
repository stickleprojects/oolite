"""hostrun (the `uitest` command): options, test selection, report names and exit codes. Docker is replaced by recorded RESULT lines
(fake_cells) and monkeypatched helpers; files go to tmp_path. No Docker or game."""
import re
import subprocess

import pytest

from oolite_ui_test_framework import hostrun


def app(tmp_path):
    a = tmp_path / "Oolite.AppImage"; a.write_text("x"); return a


def lines(build, n, fails_frame=0, fails_focus=0):
    return ["RESULT wm=marco build=%s screen=3840x1080 run=%d frame=%d focus=%d dx=0 dy=0 centred=1 exited=0 tol=40"
            % (build, i, 0 if i <= fails_frame else 1, 0 if i <= fails_focus else 1) for i in range(1, n + 1)]


def fake_cells(monkeypatch, base, cand, runs=10):
    """Replace the Docker part with recorded RESULT lines; docker is 'available'."""
    monkeypatch.setattr(hostrun, "docker_state", lambda: (True, ""))
    def cells(self, names, screens):   # each Runner tests one build: it records only that build's lines
        for ln in lines(self.label, runs, *(base if self.label == "base" else cand)): self.add(ln)
    monkeypatch.setattr(hostrun.Runner, "docker_cells", cells)


def run(tmp_path, *extra):
    a = app(tmp_path)
    return hostrun.main(["base:%s" % a, "new:%s" % a, "--env", "marco", "--out", str(tmp_path / "res"), "--minruns", "10", "--desc", "unit test"] + list(extra))


def test_exit_pass(tmp_path, monkeypatch, capsys):
    fake_cells(monkeypatch, (0, 0), (0, 0)); assert run(tmp_path) == 0
    assert capsys.readouterr().out.strip().splitlines()[-1].startswith("PASS  report: ")



def test_exit_fail_on_regression(tmp_path, monkeypatch):
    fake_cells(monkeypatch, (0, 0), (6, 0)); assert run(tmp_path) == 1


def test_suspect_passes_unless_strict(tmp_path, monkeypatch):
    fake_cells(monkeypatch, (0, 0), (2, 0), runs=3)      # fails where control passes, too few runs: SUSPECT
    assert run(tmp_path) == 0
    assert run(tmp_path, "--strict") == 1


def test_still_broken_fails_only_when_strict(tmp_path, monkeypatch):
    fake_cells(monkeypatch, (10, 0), (10, 0)); assert run(tmp_path) == 0 and run(tmp_path, "--strict") == 1


def test_quiet_prints_only_pass_or_fail(tmp_path, monkeypatch, capsys):
    fake_cells(monkeypatch, (0, 0), (0, 0)); assert run(tmp_path, "-q") == 0
    assert capsys.readouterr().out == "PASS\n"
    fake_cells(monkeypatch, (0, 0), (6, 0)); assert run(tmp_path, "--quiet") == 1
    assert capsys.readouterr().out == "FAIL\n"


def test_generated_report_name_and_files(tmp_path, monkeypatch):
    fake_cells(monkeypatch, (0, 0), (0, 0)); run(tmp_path, "-q")
    md = sorted(p.name for p in (tmp_path / "res").iterdir() if p.suffix == ".md")
    cmp = [m for m in md if re.fullmatch(r"uitest-\d{8}-\d{6}-new\.md", m)]
    assert len(md) == 3 and len(cmp) == 1, md      # the comparison, plus one result set per build
    stem = (tmp_path / "res" / cmp[0]).with_suffix("")
    assert sorted(set(md) - set(cmp)) == [stem.name + "-base.md", stem.name + "-new.md"]
    assert stem.with_suffix(".raw").exists() and (stem.parent / (stem.name + "-env.txt")).exists()


def test_report_option_sets_the_stem(tmp_path, monkeypatch):
    fake_cells(monkeypatch, (0, 0), (0, 0)); target = tmp_path / "mine" / "run1.md"
    assert run(tmp_path, "--report", str(target), "-q") == 0
    assert target.exists() and (tmp_path / "mine" / "run1.raw").exists() and (tmp_path / "mine" / "run1-env.txt").exists()


def test_no_docker_with_docker_envs_is_exit_2_but_report_written(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(hostrun, "docker_state", lambda: (False, "docker missing"))
    assert run(tmp_path, "-q") == 2
    cap = capsys.readouterr()
    assert cap.out == "" and "docker missing" in cap.err
    md = next((tmp_path / "res").glob("*-base.md")).read_text()
    assert "docker missing" in md and "**NOT TESTED**" in md


def test_nothing_measured_is_exit_2(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(hostrun, "docker_state", lambda: (True, ""))
    monkeypatch.setattr(hostrun.Runner, "docker_cells", lambda self, n, s: None)
    assert run(tmp_path, "-q") == 2 and "nothing was measured" in capsys.readouterr().err


def run_single(tmp_path, monkeypatch, fails_frame):
    monkeypatch.setattr(hostrun, "docker_state", lambda: (True, ""))
    monkeypatch.setattr(hostrun.Runner, "docker_cells", lambda self, n, s: [self.add(l) for l in lines("only", 3, fails_frame)])
    return hostrun.main(["only:%s" % app(tmp_path), "--env", "marco", "--out", str(tmp_path / "res"), "--minruns", "3", "--desc", "unit test"])


def test_single_build_passes_without_a_candidate(tmp_path, monkeypatch, capsys):
    assert run_single(tmp_path, monkeypatch, 0) == 0
    out = capsys.readouterr().out
    assert "Result: 3 passed" in out and "(control)" not in out


def test_single_build_with_a_failing_test_that_is_not_a_criterion_exits_1(tmp_path, monkeypatch, capsys):
    def cells(self, n, s):
        for l in lines("only", 3): self.add(l)
        self.add("TEST wm=marco build=only run=1 test=test_f12_toggle outcome=failed reason=F12 did not change the window size")
    monkeypatch.setattr(hostrun, "docker_state", lambda: (True, ""))
    monkeypatch.setattr(hostrun.Runner, "docker_cells", cells)
    assert hostrun.main(["only:%s" % app(tmp_path), "--env", "marco", "--out", str(tmp_path / "res"), "--minruns", "3", "--desc", "unit test"]) == 1
    assert "FAILED TESTS: test_f12_toggle (marco)" in capsys.readouterr().out


def test_single_build_failures_exit_1(tmp_path, monkeypatch):
    assert run_single(tmp_path, monkeypatch, 2) == 1


def test_bad_appimage_is_exit_2_on_stderr_only(tmp_path, capsys):
    assert hostrun.main(["base:/nonexistent.AppImage", "-q", "--out", str(tmp_path), "--desc", "unit test"]) == 2
    c = capsys.readouterr(); assert c.out == "" and "not found" in c.err


def test_bad_arguments_exit_2(tmp_path):
    with pytest.raises(SystemExit) as e:
        hostrun.main(["--no-such-flag"])
    assert e.value.code == 2
    assert hostrun.main([]) == 2


def test_purpose_and_build_notes_in_report_raw_and_env(tmp_path, monkeypatch):
    fake_cells(monkeypatch, (0, 0), (0, 0)); a = app(tmp_path)
    rc = hostrun.main(["base:%s" % a, "new:%s" % a, "--env", "marco", "--out", str(tmp_path / "res"), "--name", "cmp", "-q", "--desc", "opt1: bordered window from creation",
                       "--note", "base=unmodified 1.93.1-229", "--note", "new=opt1 + bordered"])
    res = tmp_path / "res"; md = (res / "cmp.md").read_text(); raw = (res / "cmp.raw").read_text(); env = (res / "cmp-env.txt").read_text()
    assert md.index("## Purpose") < md.index("## Headline") and "opt1: bordered window from creation" in md
    assert "| base (control) | Oolite.AppImage |" in md and "unmodified 1.93.1-229" in md and "opt1 + bordered" in md
    assert "PURPOSE " in raw and raw.count("BUILD ") == 2 and "purpose: opt1: bordered window from creation" in env
    assert re.search(r"\| [0-9a-f]{12} \|", md)


def test_desc_is_required_and_desc_file_works(tmp_path, monkeypatch, capsys):
    fake_cells(monkeypatch, (0, 0), (0, 0)); a = app(tmp_path)
    assert hostrun.main(["base:%s" % a, "--env", "marco", "--out", str(tmp_path / "res")]) == 2
    assert "--desc" in capsys.readouterr().err and not (tmp_path / "res").exists()
    assert hostrun.main(["base:%s" % a, "--env", "marco", "--out", str(tmp_path / "res"), "--desc", "  "]) == 2
    f = tmp_path / "d.md"; f.write_text("Longer **markdown** purpose\n\n- point")
    hostrun.main(["base:%s" % a, "new:%s" % a, "--env", "marco", "--out", str(tmp_path / "res"), "-q", "--desc-file", str(f), "--report", str(tmp_path / "x.md")])
    assert "Longer **markdown** purpose" in (tmp_path / "x.md").read_text()


def test_note_for_unknown_label_is_exit_2(tmp_path, monkeypatch, capsys):
    fake_cells(monkeypatch, (0, 0), (0, 0))
    assert run(tmp_path, "-q", "--note", "nope=x") == 2 and "unknown label" in capsys.readouterr().err


def test_test_selector():
    assert hostrun.test_selector("") == ""
    assert hostrun.test_selector("has_frame, test_gets_focus") == "test_has_frame or test_gets_focus"


def test_tests_option_becomes_a_k_expression(tmp_path):
    a = app(tmp_path)
    r = hostrun.Runner(hostrun.build_parser().parse_args(["x:%s" % a, "--tests", "has_frame,gets_focus", "--out", str(tmp_path)]), ("x", str(a)))
    c = r.pytest_args("marco", "3840x1080", "p.raw", "/app/a")
    assert c[c.index("-k") + 1] == "test_has_frame or test_gets_focus"
    assert "--ui-app=/app/a" in c and "--ui-label=x" in c and sum(1 for x in c if x.startswith("--ui-app")) == 1   # one build per pytest
    assert "PARTIAL RUN" in r.read_purpose()
    r2 = hostrun.Runner(hostrun.build_parser().parse_args(["x:%s" % a, "--out", str(tmp_path)]), ("x", str(a)))
    assert "-k" not in r2.pytest_args("marco", "3840x1080", "p.raw", "/app/a")


def single_set(tmp_path, monkeypatch, label, fails_frame, runs=10):
    """`uitest run LABEL:APP` with recorded lines -> the result set's stem."""
    monkeypatch.setattr(hostrun, "docker_state", lambda: (True, ""))
    monkeypatch.setattr(hostrun.Runner, "docker_cells", lambda self, n, s: [self.add(l) for l in lines(self.label, runs, fails_frame)])
    hostrun.main(["run", "%s:%s" % (label, app(tmp_path)), "--env", "marco", "--out", str(tmp_path / "res"), "--name", label, "--desc", "unit test", "-q"])
    return str(tmp_path / "res" / label)


def test_run_writes_a_self_describing_set_with_no_control_or_candidate(tmp_path, monkeypatch):
    import json
    raw = open(single_set(tmp_path, monkeypatch, "base", 0) + ".raw").read()
    head = json.loads(next(l for l in raw.splitlines() if l.startswith("SET "))[4:])
    assert head["label"] == "base" and head["app"].endswith("Oolite.AppImage") and head["envs"] == ["marco"] and head["built"] and head["uitest_version"]
    assert "control" not in raw.lower() and "candidate" not in raw.lower()


def test_run_takes_exactly_one_build(tmp_path, capsys):
    a = app(tmp_path)
    assert hostrun.main(["run", "a:%s" % a, "b:%s" % a, "--desc", "x"]) == 2 and "exactly one" in capsys.readouterr().err


def test_compare_of_separate_runs_gives_the_combined_runs_verdict(tmp_path, monkeypatch):
    from oolite_ui_test_framework import report
    base = single_set(tmp_path, monkeypatch, "base", 0); new = single_set(tmp_path, monkeypatch, "new", 8)
    assert hostrun.main(["compare", "--control", base, "--candidate", new + ".raw", "--report", str(tmp_path / "cmp.md"), "-q"]) == 1   # REGRESSED
    separate = dict(report.LAST)
    fake_cells(monkeypatch, (0, 0), (8, 0)); run(tmp_path, "--report", str(tmp_path / "both.md"), "-q")
    assert {k: separate[k] for k in ("regressed", "measured")} == {k: report.LAST[k] for k in ("regressed", "measured")} and separate["regressed"]
    assert "REGRESSED" in (tmp_path / "cmp.md").read_text()


def test_compare_refuses_a_multi_build_raw_and_duplicate_labels(tmp_path, monkeypatch, capsys):
    base = single_set(tmp_path, monkeypatch, "base", 0)
    mixed = tmp_path / "mixed.raw"; mixed.write_text('BUILD {"label": "a"}\nBUILD {"label": "b"}\n')
    assert hostrun.main(["compare", "--control", base, "--candidate", str(mixed)]) == 2 and "not a single-build result set" in capsys.readouterr().err
    assert hostrun.main(["compare", "--control", base, "--candidate", base]) == 2 and "same build label" in capsys.readouterr().err


def test_quick_is_one_run_one_screen_and_two_tests(tmp_path, monkeypatch):
    seen = {}
    monkeypatch.setattr(hostrun, "docker_state", lambda: (True, ""))
    def cells(self, names, screens):
        seen.update(runs=self.a.runs, screens=screens, tests=self.a.tests, minruns=self.a.minruns)
        for ln in lines("base", 1) + lines("new", 1): self.add(ln)
    monkeypatch.setattr(hostrun.Runner, "docker_cells", cells)
    a = app(tmp_path)
    hostrun.main(["base:%s" % a, "new:%s" % a, "--env", "marco", "--screens", "3840x1080,1920x1080", "--quick", "--out", str(tmp_path / "res"), "--desc", "unit test"])
    assert seen == {"runs": 1, "screens": ["3840x1080"], "tests": hostrun.QUICK_TESTS, "minruns": 1}


def test_headed_args_share_only_the_host_x_socket_the_cookie_and_the_gpu():
    ok = lambda p: True
    args, why = hostrun.headed_args({"DISPLAY": ":0.0", "XAUTHORITY": "/home/k/.Xauthority"}, exists=ok, hostname=lambda: "box")
    assert why == "" and args[:4] == ["--device", "/dev/dri", "--hostname", "box"]
    assert "/tmp/.X11-unix/X0:/tmp/.X11-unix/X0" in args and "UITEST_HOST_DISPLAY=:0" in args and "/home/k/.Xauthority:/tmp/hostxauth:ro" in args
    assert hostrun.headed_args({"DISPLAY": "remote:10.0"}, exists=ok)[1]
    assert hostrun.headed_args({"DISPLAY": ":0"}, exists=lambda p: p != "/dev/dri")[1]


def test_container_output_is_given_back_to_the_host_user(tmp_path):
    cmd = hostrun.give_back_output("my run", uid=1000, gid=1001)
    assert cmd[:2] == ["sh", "-c"] and cmd[3] == "sh"
    assert 'dbus-run-session -- "$@"' in cmd[2] and "chown -R 1000:1001 /out/'my run'.*" in cmd[2] and cmd[2].endswith("exit $rc")
    # the wrapper keeps pytest's exit code and chowns only this run's output
    out = tmp_path / "out"; out.mkdir(); (out / "my run.logs").mkdir()
    script = cmd[2].replace("dbus-run-session -- ", "").replace("/out/", str(out) + "/").replace("chown -R 1000:1001", "touch -c")
    assert subprocess.run(["sh", "-c", script, "sh", "sh", "-c", "exit 1"]).returncode == 1


def test_device_args_pass_only_the_declared_devices_the_host_has():
    e = lambda d: type("E", (), {"devices": d})()
    assert hostrun.device_args(e(["/dev/udmabuf"]), exists=lambda p: True) == ["--device", "/dev/udmabuf"]
    assert hostrun.device_args(e(["/dev/udmabuf"]), exists=lambda p: False) == [] and hostrun.device_args(e([])) == []
