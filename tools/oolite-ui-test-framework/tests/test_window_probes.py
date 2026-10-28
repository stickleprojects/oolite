"""window_probes: parsing what the X tools, KWin and sway report, and the ask probe. Subprocess calls (`sh`) are monkeypatched with
recorded output; no display needed."""
from oolite_ui_test_framework import window_probes


def test_primary_monitor_rules():
    assert window_probes.primary_monitor([(0, 0, 1920, 1080, False), (1920, 0, 1920, 1080, True)]) == (1920, 0, 1920, 1080)
    assert window_probes.primary_monitor([(5, 5, 10, 10, False)]) == (5, 5, 10, 10) and window_probes.primary_monitor([]) is None


def test_kwin_row():
    o = window_probes.parse_kwin_row("1 0 640 180 1280 720 0 0 2560 1440")
    assert (o.framed, o.focused, o.outer, o.mon) == (1, 0, (640, 180, 1280, 720), (0, 0, 2560, 1440))
    assert window_probes.parse_kwin_row("1 1 0 0 10 10 NA NA NA NA").mon is None and window_probes.parse_kwin_row("junk") is None
    c = window_probes.parse_kwin_row("1 1 630 150 1300 750 NA NA NA NA 640 180 1280 720")
    assert c.mon is None and c.client == (640, 180, 1280, 720) and o.client is None


SHOT_REPLY = "({'format': <uint32 16>, 'height': <uint32 2>, 'scale': <1.0>, 'stride': <uint32 12>, 'type': <'raw'>, 'width': <uint32 3>},)"


def test_shot_meta_from_gdbus_reply():
    assert window_probes.parse_shot_meta(SHOT_REPLY) == {"width": 3, "height": 2, "stride": 12, "format": 16, "scale": 1.0}
    assert window_probes.parse_shot_meta("Error: GDBus.Error:org.freedesktop.DBus.Error.NoReply") is None


def test_crop_reads_rgbx_and_bgrx_rows_and_clips_to_the_image():
    meta = window_probes.parse_shot_meta(SHOT_REPLY)                     # 3 x 2 pixels, pixel n = (n, 10 + n, 20 + n, 255)
    data = bytes(v for n in range(6) for v in (n, 10 + n, 20 + n, 255))
    assert window_probes.crop_rgba(data, meta, (1, 0, 2, 2)) == (2, 2, bytes([1, 11, 21, 2, 12, 22, 4, 14, 24, 5, 15, 25]))
    assert window_probes.crop_rgba(data, dict(meta, format=4), (0, 1, 1, 1)) == (1, 1, bytes([23, 13, 3]))
    assert window_probes.crop_rgba(data, meta, (2, 1, 5, 5)) == (1, 1, bytes([5, 15, 25]))       # clipped
    assert window_probes.crop_rgba(data, meta, (5, 5, 2, 2)) is None and window_probes.crop_rgba(data, dict(meta, format=3), (0, 0, 1, 1)) is None
    assert window_probes.crop_rgba(data[:10], meta, (0, 0, 1, 1)) is None                          # short read


def test_kwin_backend_finds_places_and_grabs_through_kwin():
    class Probe:
        n = 0; obs = window_probes.Obs(outer=(0, 0, 4, 3), client=(1, 1, 2, 1))
        def observe(self): self.n += 1; return self.obs
    meta = {"width": 4, "height": 3, "stride": 16, "format": 16, "scale": 1.0}
    data = bytes(v for n in range(12) for v in (n, n, n, 0))               # pixel n = grey n
    t = [0.0]; p = Probe()
    b = window_probes.KWinBackend(p, clock=lambda: t[0], capture=lambda env: (data, meta))
    assert b.find_window() == 1 and b.abs_geom(1) == (1, 1, 2, 1) and p.n == 1      # one KWin round trip for both
    assert b.grab(1) == (2, 1, bytes([5, 5, 5, 6, 6, 6]))
    t[0] = 2.0; b.find_window(); assert p.n == 2                                        # stale: asked again
    p.obs = window_probes.Obs(); t[0] = 4.0
    assert b.find_window() is None and b.grab(None) is None                             # no window: no capture attempted


def test_sway_tree():
    tree = {"nodes": [{"nodes": [{"pid": 7, "app_id": "", "window_properties": {"class": "Oolite"}, "rect": {"x": 1, "y": 2, "width": 3, "height": 4},
                                 "deco_rect": {"height": 0}, "current_border_width": 2, "focused": True}]}], "floating_nodes": []}
    o = window_probes.parse_sway_tree(tree, [{"focused": True, "rect": {"x": 0, "y": 0, "width": 3840, "height": 1080}}])
    assert (o.framed, o.focused, o.outer, o.mon) == (1, 1, (1, 2, 3, 4), (0, 0, 3840, 1080))
    assert window_probes.parse_sway_tree({"nodes": []}) is None


def test_x_tools_backend_parsing(monkeypatch):
    out = {"xwininfo -root": "xwininfo: Window id: 0x2a \"root\"", "xdotool search": "100\n", "xdotool getwindowfocus": "100\n",
           "xprop -root _NET_ACTIVE_WINDOW": "_NET_ACTIVE_WINDOW(WINDOW): window id # 0x64",
           "xwininfo -id 100 -children": "  Parent window id: 0x2a (the root)", "xwininfo -id 100": "  Absolute upper-left X:  1280\n  Absolute upper-left Y:  180\n  Width: 1280\n  Height: 720\n",
           "xrandr": "Monitors: 1\n 0: +*DUMMY0 3840/0x1080/0+0+0  DUMMY0"}
    monkeypatch.setattr(window_probes, "sh", lambda cmd, env=None, **k: next((v for key, v in out.items() if " ".join(cmd).startswith(key)), ""))
    b = window_probes.XToolsBackend(); o = window_probes.X11Probe(b).observe()
    assert o.framed == 0 and o.focused == 1 and o.outer == (1280, 180, 1280, 720) and o.win == 100
    assert b.monitors() == [(0, 0, 3840, 1080, True)]


def test_x11_probe_framed_uses_parent_geometry():
    class B:
        def find_window(self): return 10
        def abs_geom(self, w): return {10: (101, 120, 1280, 720), 20: (100, 100, 1282, 740)}[w]
        def parent_id(self, w): return 20
        def root_id(self): return 1
        def active_id(self): return 10
        def focus_id(self): return 0
    o = window_probes.X11Probe(B()).observe()
    assert o.framed == 1 and o.outer == (100, 100, 1282, 740) and o.focused == 1


def test_ask_probe_answers_and_no_prompt():
    qs = []
    p = window_probes.AskProbe(ask=lambda q: (qs.append(q), "y")[1])
    o = p.observe(missing=["framed", "centred"])
    assert (o.framed, o.centred, o.asked, o.source) == (1, 1, {"framed": "y", "centred": "y"}, "user") and len(qs) == 2
    assert window_probes.AskProbe(no_prompt=True).observe(missing=["framed"]).framed is None
    assert window_probes.AskProbe(ask=lambda q: None).observe(missing=["focused"]).focused is None


def test_merge_respects_field_restriction():
    a = window_probes.Obs(); b = window_probes.Obs(framed=1, focused=1, outer=(1, 2, 3, 4))
    a.merge(b, ("framed", "focused"))
    assert a.framed == 1 and a.outer is None
    a.merge(window_probes.Obs(outer=(1, 2, 3, 4)))
    assert a.outer == (1, 2, 3, 4)


class _HostX:
    """What xtool sees in the helper container: a game window 9 on the host display."""
    def __init__(self): self.keys = []; self.repeat = True
    def find_window(self): return 9
    def abs_geom(self, w): return (1, 2, 3, 4)
    def parent_id(self, w): return 5
    def root_id(self): return 1
    def active_id(self): return 9
    def focus_id(self): return 9
    def monitors(self): return [(0, 0, 2560, 1440, True)]
    def wm_name(self): return "KWin"
    def send_key(self, key, window=None): self.keys.append((key, window))
    def autorepeat_on(self): return self.repeat
    def autorepeat_off(self): self.repeat = False
    def autorepeat_restore(self): self.repeat = True
    def grab(self, w): return 2, 1, b"\x01\x02\x03\x04\x05\x06"


def _serving(x, started):
    """A Popen stand-in that runs xtool.serve on x for each line written, the way the helper container's `xtool serve` would."""
    import io
    from oolite_ui_test_framework import xtool
    class Proc:
        def __init__(self, cmd, **k):
            self.cmd = cmd; self.stdin = self; self.stdout = io.BytesIO(); self.dead = None; started.append(self)
        def write(self, b): self.line = b
        def flush(self):
            pos = self.stdout.tell(); self.stdout.seek(0, 2); xtool.serve(x, [self.line.decode()], self.stdout); self.stdout.seek(pos)
        def poll(self): return self.dead
        def close(self): pass
        def wait(self, timeout=None): return 0
    return Proc


def test_helper_backend_talks_to_one_xtool_serve():
    x = _HostX(); started = []
    b = window_probes.HelperBackend("ct", ":0", popen=_serving(x, started))
    o = window_probes.make_probe("x11", backend=b).observe()
    assert (o.win, o.framed, o.focused, o.outer) == (9, 1, 1, (1, 2, 3, 4)) and b.monitors() == [(0, 0, 2560, 1440, True)]
    assert b.abs_geom(9) == (1, 2, 3, 4) and b.grab(9) == (2, 1, b"\x01\x02\x03\x04\x05\x06")
    b.send_key("F12", 9); b.send_key("Down")
    assert x.keys == [("F12", 9), ("Down", None)]
    assert b.autorepeat_on() is True and (b.autorepeat_off(), x.repeat) == (None, False) and (b.autorepeat_restore(), x.repeat) == (None, True)
    assert len(started) == 1 and started[0].cmd[:3] == ["docker", "exec", "-i"] and started[0].cmd[-2:] == ["oolite_ui_test_framework.xtool", "serve"]


def test_helper_backend_restarts_a_dead_helper_and_reads_errors_as_none():
    x = _HostX(); started = []
    b = window_probes.HelperBackend("ct", ":0", popen=_serving(x, started))
    assert b.find_window() == 9
    started[0].dead = 1
    assert b.find_window() == 9 and len(started) == 2
    x.grab = lambda w: 1 / 0   # an exception in the helper is an error answer, not a broken helper
    assert b.grab(9) is None and b.find_window() == 9 and len(started) == 2


def test_xtool_observe_uses_x11_probe():
    from oolite_ui_test_framework import xtool
    class B:
        def find_window(self): return 3
        def abs_geom(self, w): return (0, 0, 10, 10)
        def parent_id(self, w): return 1
        def root_id(self): return 1
        def active_id(self): return 0
        def focus_id(self): return 0
    d = xtool.observe(B())
    assert d["win"] == 3 and d["framed"] == 0 and d["focused"] == 0
