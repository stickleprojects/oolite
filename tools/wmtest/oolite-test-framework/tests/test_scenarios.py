"""Scenarios against a scripted fake session and a fake clock: no display, no game."""
from oolite_test_framework import checks, probes, rawfmt, registry, scenarios


class FakeClock:
    def __init__(self): self.t = 0.0
    def monotonic(self): return self.t
    def sleep(self, s): self.t += s


class FakeSession:
    """observe() returns the scripted Obs for the current fake time."""
    def __init__(self, clock, script, present=True, toggle_sizes=None):
        self.clock = clock; self.script = script; self.present = present; self.primary = (0, 0, 3840, 1080); self.backend = object(); self.keys = []
        self.env = registry.Environment(name="fake", family="fake", session="X11", image="arch", kind="x11", start=["x"])
    def observe(self, cheap_only=False):
        o = None
        for t, ob in self.script:
            if self.clock.t >= t: o = ob
        return o
    def window_present(self, game): return self.present
    def window_id(self): return 7
    def send_key(self, key, window=None):
        self.keys.append((key, window))
        if self.toggle: self.script.append((self.clock.t, self.toggle.pop(0)))
    def key_down(self, key): self.send_key(key)
    def key_up(self, key): pass
    toggle = None


def norm(rec):
    return {k: rawfmt.fmt(v) for k, v in rec.items()}


def splash(): return probes.Obs(framed=0, focused=0, outer=(1536, 156, 768, 768))


def game(): return object()


def test_startup_samples_splash_post_end():
    clk = FakeClock()
    final = probes.Obs(framed=1, focused=1, outer=(1280, 180, 1280, 720), client=(1281, 200, 1280, 700), source="x11")
    s = FakeSession(clk, [(0.0, None), (1.0, splash()), (4.0, probes.Obs(framed=1, focused=1, outer=(1270, 170, 1300, 740))), (7.0, final)])
    rec = scenarios.run_startup(s, game(), scenarios.Opts(), clk)
    assert rec["outer"] == "1280x720+1280+180" and rec["splash_outer"] == "768x768+1536+156"
    assert rec["post_outer"] == "1300x740+1270+170"        # first sample >= 2 s after the first size change (at 4.0)
    full = checks.apply(dict(rec, wm="m", build="b", screen="s", run=1))
    assert full["dx"] == "0" and full["centred"] == "1" and full["splash_dx"] == "0"
    assert clk.t >= 14


def test_exited_run_fails_all_and_has_no_geometry():
    clk = FakeClock(); s = FakeSession(clk, [], present=False)
    rec = scenarios.record(s, game(), "marco", "base", "3840x1080", 3, scenarios.Opts(), clk)
    r = norm(rec)
    assert (r["frame"], r["focus"], r["centred"], r["exited"]) == ("0", "0", "0", "1") and r["dx"] == "NA"


def test_unmeasurable_fields_are_na_not_failures():
    clk = FakeClock(); s = FakeSession(clk, [(0, probes.Obs())])
    rec = scenarios.record(s, game(), "mutter-native", "base", "3840x1080", 1, scenarios.Opts(), clk)
    r = norm(rec)
    assert r["frame"] == "NA" and r["focus"] == "NA" and r["centred"] == "NA" and r["dx"] == "NA" and r["exited"] == "0"


def test_toggle_round_trip_ok():
    clk = FakeClock(); win = probes.Obs(framed=1, focused=1, outer=(1280, 180, 1280, 720))
    s = FakeSession(clk, [(0, win)]); s.toggle = [probes.Obs(framed=0, focused=1, outer=(0, 0, 3840, 1080)), win]
    t = scenarios.run_toggle(s, game(), scenarios.Opts(toggle=True), clk)
    assert t["t_ok"] == 1 and t["t_method"] == "key" and t["t_outer"] == "1280x720+1280+180" and [k for k, _ in s.keys] == ["F12", "F12"]


def test_toggle_ignored_falls_back_then_fails():
    clk = FakeClock(); win = probes.Obs(framed=0, focused=0, outer=(0, 0, 768, 768))
    s = FakeSession(clk, [(0, win)]); s.toggle = []
    t = scenarios.run_toggle(s, game(), scenarios.Opts(toggle=True), clk)
    assert t["t_ok"] == 0 and t["t_method"] == "sendevent" and s.keys == [("F12", None), ("F12", 7)] and t["t_centred"] == 0


def test_timing_constants_match_trial_sh():
    o = scenarios.Opts()
    assert (o.wait, o.sample, o.post_delay, o.tol) == (14.0, 0.5, 2.0, 40)
