"""game_log: reading the game's own logs from its run folder."""
from oolite_ui_test_framework import game_log


def test_keydowns_counts_all_or_one_key_and_none_without_a_log(tmp_path):
    (tmp_path / "Logs").mkdir()
    (tmp_path / "Logs" / "Latest.log").write_text("a: Keydown scancode = 69, unicode = 327\nb: Keydown scancode = 81, unicode = 269\n"
                                                  "c: Keyup scancode = 81, unicode = 269\n")
    (tmp_path / "out.log").write_text("printed\n")
    g = type("G", (), {"dir": str(tmp_path)})()
    assert game_log.keydowns(g) == 2 and game_log.keydowns(g, "F12") == 1 and game_log.keydowns(g, "Down") == 1
    assert [n for n, _ in game_log.texts(g, ("out.log", "Latest.log"))].count("out.log") == 1
    assert game_log.keydowns(object()) is None and game_log.texts(object()) == []
