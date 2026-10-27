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


def test_helper_backend_parses_xtool_json(monkeypatch):
    calls = []
    def fake(cmd, env=None, **k):
        calls.append(cmd)
        return {"observe": '{"win": 9, "framed": 1, "focused": 0, "outer": [1, 2, 3, 4], "client": [2, 3, 1, 2]}', "monitors": "[[0, 0, 2560, 1440, true]]"}.get(cmd[-1], "")
    monkeypatch.setattr(window_probes, "sh", fake)
    b = window_probes.HelperBackend("ct", ":0")
    o = window_probes.make_probe("x11", backend=b).observe()
    assert (o.win, o.framed, o.focused, o.outer) == (9, 1, 0, (1, 2, 3, 4)) and b.monitors() == [(0, 0, 2560, 1440, True)]
    b.send_key("F12", 9)
    assert calls[-1][-4:] == ["oolite_ui_test_framework.xtool", "key", "F12", "9"] and calls[0][:3] == ["docker", "exec", "-e"]


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
