"""registry: reading environments.toml, its validation errors, and a check that the shipped file is consistent with the Dockerfiles."""
import os
import tomllib

import pytest

from oolite_ui_test_framework import registry

TOML = registry.DEFAULT_PATH


def test_shipped_registry_parses_and_is_consistent():
    envs, images = registry.load(TOML)
    assert {"marco", "xfwm4", "openbox", "muffin", "kwin", "mutter", "kwin-xwayland", "sway-native", "host-native"} <= set(envs)
    for e in envs.values():
        assert e.image in images and os.path.exists(os.path.join(os.path.dirname(TOML), images[e.image]["dockerfile"]))
        assert e.session in registry.SESSIONS


def test_old_raw_names_are_preserved():
    envs, _ = registry.load(TOML)
    assert envs["kwin"].session == "X11" and envs["kwin-xwayland"].session == "XWayland" and envs["mutter-native"].session == "Wayland native"


def test_probe_specs_with_field_restriction():
    envs, _ = registry.load(TOML)
    assert envs["kwin-xwayland"].probe_specs == [("kwin", ("framed", "focused")), ("x11", None)]
    assert envs["marco"].probe_specs == [("x11", None)]


def test_adding_a_wm_is_one_entry():
    data = tomllib.load(open(TOML, "rb"))
    before = len(registry.parse(data)[0])
    data["env"]["fvwm"] = {"family": "fvwm", "session": "X11", "image": "arch", "kind": "x11", "start": ["fvwm"]}
    envs, _ = registry.parse(data)
    assert len(envs) == before + 1 and envs["fvwm"].settle == 4.0 and envs["fvwm"].probes == ["x11"]


@pytest.mark.parametrize("patch,msg", [({"session": "Mir"}, "session"), ({"kind": "vm"}, "kind"), ({"image": "nope"}, "unknown image"),
                                        ({"probes": ["telepathy"]}, "unknown probe"), ({"bogus": 1}, "unknown key"), ({"start": []}, "start command")])
def test_validation_errors(patch, msg):
    data = tomllib.load(open(TOML, "rb"))
    e = {"family": "f", "session": "X11", "image": "arch", "kind": "x11", "start": ["f"]}; e.update(patch)
    data["env"]["bad"] = e
    with pytest.raises(registry.RegistryError, match=msg):
        registry.parse(data)


def test_missing_required_key():
    with pytest.raises(registry.RegistryError, match="missing 'family'"):
        registry.parse({"images": {"arch": {}}, "env": {"x": {"session": "X11", "image": "arch", "kind": "x11"}}})
