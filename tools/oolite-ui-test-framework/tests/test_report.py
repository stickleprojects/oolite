"""report: statistics and the Markdown report made from raw result files (fixtures/ and small raw files written to tmp_path).
Includes the module's own --selftest."""
import re
import os

from oolite_ui_test_framework import registry, report

DATA = os.path.join(os.path.dirname(__file__), "fixtures")


def render(tmp_path, raw, **kw):
    out = str(tmp_path / "r.md")
    argv = [os.path.join(DATA, raw), out, "--control", kw.pop("control", "base"), "--minruns", str(kw.pop("minruns", 5)), "--registry", registry.DEFAULT_PATH]
    for k, v in kw.items(): argv += ["--" + k.replace("_", "-"), str(v)]
    rc = report.main(argv)
    return rc, open(out).read()


def test_selftest():
    assert report.selftest() == 0


def test_marco_is_fixed_by_candidate(tmp_path):
    rc, md = render(tmp_path, "matrix2-arch.raw", candidates="opt1")
    assert rc == 0
    head = md.split("## Environment")[0]
    assert "- FIXED: marco" in head and "base (control) fails on:" in head and "NOT TESTED" in head
    cov = [l for l in head.splitlines() if l.startswith("| marco")][0]
    assert "FIXED" in cov and "WORKS" in cov          # frame/focus FIXED, centred WORKS


def test_wayland_spike_na_is_not_a_failure(tmp_path):
    rc, md = render(tmp_path, "wayland-spike.raw", minruns=3)
    assert rc == 0
    row = [l for l in md.split("## Coverage")[1].splitlines() if l.startswith("| weston ") and "Wayland native" in l][0]
    assert row.count("NOT MEASURABLE") == 5 and "FAIL" not in row


def test_rows_sorted_family_then_session_host_last(tmp_path):
    _, md = render(tmp_path, "matrix3-debian.raw")
    sec = md.split("## Failure counts per cell")[1].split("## Results per cell")[0]
    fams = [l.split("|")[1].split()[0] for l in sec.splitlines() if l.startswith("| kwin") or l.startswith("| mutter")]
    assert fams and fams == sorted(fams)


def test_regression_gives_exit_code_1(tmp_path):
    raw = tmp_path / "x.raw"
    rows = ["RESULT wm=marco build=%s screen=3840x1080 run=%d frame=%d focus=1 dx=0 dy=0 centred=1 exited=0 tol=40" % (b, i, 0 if b == "cand" else 1)
            for b in ("base", "cand") for i in range(1, 11)]
    raw.write_text("\n".join(rows) + "\n")
    out = str(tmp_path / "o.md")
    assert report.main([str(raw), out, "--control", "base", "--candidates", "cand", "--minruns", "10"]) == 1
    head = open(out).read().split("## Coverage")[0]
    assert "**FAIL**" in head and "REGRESSED" in head


def test_tolerance_rejudges_recorded_geometry(tmp_path):
    raw = tmp_path / "t.raw"
    rows = ["RESULT wm=marco build=%s screen=3840x1080 run=%d frame=1 focus=1 dx=57 dy=0 centred=0 exited=0 tol=40 outer=1280x720+1337+200 mon=3840x1080+0+0" % (b, i)
            for b in ("base",) for i in range(1, 6)]
    raw.write_text("\n".join(rows) + "\n")
    cells40, _ = report.load(str(raw), 40); cells60, _ = report.load(str(raw), 60)
    f40 = report.fails(cells40[("marco", "3840x1080", "base")])["centred"]; f60 = report.fails(cells60[("marco", "3840x1080", "base")])["centred"]
    assert f40 == (5, 5) and f60 == (0, 5)


def test_outcome_words_per_criterion():
    co = lambda *a: report.crit_outcome(*a)[0]
    assert co(0, 10, 0, 10, 10) == "WORKS" and co(0, 5, 0, 5, 10) == "NEEDS MORE RUNS"
    assert co(10, 10, 0, 10, 10) == "FIXED" and co(10, 10, 10, 10, 10) == "STILL BROKEN"
    assert co(0, 10, 6, 10, 10) == "REGRESSED" and co(0, 3, 3, 3, 10) == "SUSPECT" and co(0, 0, 0, 0, 5) == "NOT MEASURABLE"
    assert "tested 5 runs, all passed, below 10 needed" in report.crit_outcome(0, 5, 0, 5, 10)[1]


def test_untested_environments_listed_with_reason(tmp_path):
    raw = tmp_path / "s.raw"
    raw.write_text("SKIP wm=kwin screen=3840x1080 build=cand reason=not available: docker missing\n"
                   "RESULT wm=marco build=base screen=3840x1080 run=1 frame=1 focus=1 dx=0 dy=0 centred=1 exited=0 tol=40\n"
                   "RESULT wm=marco build=cand screen=3840x1080 run=1 frame=1 focus=1 dx=0 dy=0 centred=1 exited=0 tol=40\n")
    out = str(tmp_path / "o.md"); report.main([str(raw), out, "--control", "base", "--minruns", "5", "--registry", registry.DEFAULT_PATH])
    md = open(out).read()
    assert [l for l in md.splitlines() if l.startswith("| kwin") and "NOT TESTED" in l and "docker missing" in l]
    assert [l for l in md.splitlines() if l.startswith("| marco") and "NEEDS MORE RUNS" in l]


def test_clean_runs_score(tmp_path):
    rc, md = render(tmp_path, "matrix2-arch.raw", candidates="opt1")
    assert "## Runs with every measured criterion passing" in md
    assert "Control failures are baseline results, not candidate failures" in md
    assert "pytest's failed count includes tests from both builds" in md
    assert re.search(r"- Runs with every measured criterion passing: .*\d+/\d+", md)
    from oolite_ui_test_framework import report
    ok = {"wm": "m", "screen": "s", "build": "b", "frame": "1", "focus": "1", "exited": "0"}
    assert report.clean_runs([ok, dict(ok, focus="0"), ok]) == (2, 3)
